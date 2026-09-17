"""face_id tests: fake analyzer only — never loads the buffalo_l model, never downloads."""
import json
import math
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.face_id import (
    DEFAULT_FACE_STORE,
    DEFAULT_MARGIN,
    DEFAULT_THRESHOLD,
    MIN_DET_SCORE,
    MIN_EYE_PX,
    FaceEngine,
    FaceRecord,
    _cosine,
    best_match,
    embed_image,
    get_face_engine,
    load_faces,
    quality,
    store_faces,
)

DIM = 512


def unit_probe(seed=7):
    rng = np.random.RandomState(seed)
    v = rng.standard_normal(DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def vec_at(probe, sim, seed):
    """Unit 512-d vector whose cosine with probe is ~sim (float32 exact enough)."""
    rng = np.random.RandomState(seed)
    v = rng.standard_normal(DIM).astype(np.float32)
    v = v - float(v @ probe) * probe
    v = v / np.linalg.norm(v)
    g = sim * probe + math.sqrt(max(1.0 - sim * sim, 0.0)) * v
    return (g / np.linalg.norm(g)).astype(np.float32)


def gallery(probe, sims_by_pid, as_list=False):
    """{pid: [entry]} (store_faces shape) or flat [{player_id, embedding}] (best_match list shape)."""
    entries, flat = {}, []
    for i, (pid, sims) in enumerate(sims_by_pid.items()):
        rows = [{"embedding": vec_at(probe, s, seed=i * 10 + j).tolist()} for j, s in enumerate(sims)]
        entries[pid] = rows
        flat.extend({"player_id": pid, "embedding": r["embedding"]} for r in rows)
    return (flat if as_list else entries)


class FakeFace:
    def __init__(self, bbox, kps=None, det_score=0.9, normed=None, raw=None):
        self.bbox = np.asarray(bbox, np.float32)
        self.kps = None if kps is None else np.asarray(kps, np.float32)
        self.det_score = det_score
        if normed is not None:
            self.normed_embedding = normed
        if raw is not None:
            self.embedding = raw


class FakeAnalyzer:
    def __init__(self, faces):
        self.faces = faces
        self.frames = []

    def get(self, frame):
        self.frames.append(frame)
        return list(self.faces)


class AnalyzeContract(unittest.TestCase):
    def test_wrapper_fields_and_no_model_load(self):
        probe = unit_probe()
        unnormalized = np.full(DIM, 2.0, np.float32)  # tests fallback l2-normalization
        faces = [
            FakeFace([10, 20, 110, 140], kps=[[15, 25], [25, 25], [20, 40], [15, 50], [25, 50]],
                     det_score=0.97, normed=probe),
            FakeFace([0, 0, 50, 50], det_score=0.5, raw=unnormalized),   # no kps, no normed_embedding
            FakeFace([5, 5, 55, 55], kps=[[1, 1], [2, 1]], det_score=0.6, normed=probe),
        ]
        engine = FaceEngine(analyzer=FakeAnalyzer(faces))
        with patch.object(FaceEngine, "_create_analyzer", side_effect=AssertionError("model load attempted")):
            frame = np.zeros((72, 128, 3), np.uint8)
            out = engine.analyze(frame)

        self.assertEqual(len(out), 3)
        f0 = out[0]
        self.assertEqual(f0["bbox"], [10.0, 20.0, 110.0, 140.0])
        self.assertTrue(all(isinstance(v, float) for v in f0["bbox"]))
        self.assertEqual(f0["eye_px"], 10.0)
        self.assertEqual(f0["det_score"], 0.97)
        self.assertIsInstance(f0["embedding"], np.ndarray)
        self.assertEqual(f0["embedding"].dtype, np.float32)
        self.assertEqual(f0["embedding"].shape, (DIM,))
        self.assertAlmostEqual(float(np.linalg.norm(f0["embedding"])), 1.0, places=5)
        self.assertAlmostEqual(float(f0["embedding"] @ probe), 1.0, places=5)

        self.assertIsNone(out[1]["eye_px"])                       # kps missing -> None
        self.assertAlmostEqual(float(np.linalg.norm(out[1]["embedding"])), 1.0, places=5)  # normalized fallback

        # frame passed through untouched; injected analyzer reused (no _create_analyzer)
        self.assertEqual(len(engine._analyzer.frames), 1)
        self.assertIs(engine._analyzer.frames[0], frame)

    def test_face_skipped_without_any_embedding(self):
        engine = FaceEngine(analyzer=FakeAnalyzer([FakeFace([1, 2, 3, 4], det_score=0.9)]))
        self.assertEqual(engine.analyze(np.zeros((8, 8, 3), np.uint8)), [])

    def test_singleton_lazy(self):
        with patch.object(FaceEngine, "_create_analyzer", side_effect=AssertionError("model load attempted")):
            engine = get_face_engine()
            self.assertIsInstance(engine, FaceEngine)
            self.assertIs(engine, get_face_engine())  # lazy: no analyzer built, still one instance


class QualityGate(unittest.TestCase):
    def test_boundaries_inclusive(self):
        self.assertTrue(quality({"eye_px": MIN_EYE_PX, "det_score": MIN_DET_SCORE}))
        self.assertFalse(quality({"eye_px": MIN_EYE_PX - 0.01, "det_score": 0.9}))
        self.assertFalse(quality({"eye_px": 12.0, "det_score": MIN_DET_SCORE - 0.01}))
        self.assertTrue(quality({"eye_px": 10.4, "det_score": 0.4}))  # median real-VOD face

    def test_missing_fields_reject(self):
        self.assertFalse(quality({"eye_px": None, "det_score": 0.9}))
        self.assertFalse(quality({"eye_px": 10.0}))
        self.assertFalse(quality({"eye_px": None, "det_score": None}))
        self.assertFalse(quality({}))

    def test_engine_method_delegates(self):
        engine = FaceEngine(analyzer=FakeAnalyzer([]))
        self.assertEqual(engine.quality({"eye_px": 10.0, "det_score": 0.5}),
                         quality({"eye_px": 10.0, "det_score": 0.5}))


class BestMatch(unittest.TestCase):
    def setUp(self):
        self.probe = unit_probe()
        self.engine = FaceEngine(analyzer=FakeAnalyzer([]))

    def test_clear_match_dict_and_list_shapes(self):
        for g in (gallery(self.probe, {"P1": [0.55], "P2": [0.30]}, as_list=True),
                  gallery(self.probe, {"P1": [0.55], "P2": [0.30]})):
            m = best_match(self.probe, g, threshold=0.4, margin=0.12)
            self.assertEqual(m["player_id"], "P1")
            self.assertAlmostEqual(m["similarity"], 0.55, places=4)
            self.assertAlmostEqual(m["margin"], 0.25, places=4)

    def test_margin_rejects_ambiguous(self):
        g = gallery(self.probe, {"P1": [0.55], "P2": [0.50]})  # gap 0.05 < 0.12
        self.assertIsNone(best_match(self.probe, g, threshold=0.4, margin=0.12))
        self.assertIsNone(self.engine.best_match(self.probe, g, threshold=0.4))
        # same scores, wider margin budget -> accepted
        self.assertIsNotNone(best_match(self.probe, g, threshold=0.4, margin=0.04))

    def test_margin_boundary(self):
        probe = unit_probe()
        g1, g2 = vec_at(probe, 0.55, seed=1), vec_at(probe, 0.40, seed=2)
        gap = _cosine(probe, g1) - _cosine(probe, g2)  # actual achieved gap
        g = {"P1": [{"embedding": g1.tolist()}], "P2": [{"embedding": g2.tolist()}]}
        self.assertIsNotNone(best_match(probe, g, threshold=0.3, margin=gap))  # >= margin passes
        self.assertIsNone(best_match(probe, g, threshold=0.3, margin=gap + 1e-5))

    def test_threshold_boundary(self):
        probe = unit_probe()
        g1 = vec_at(probe, 0.55, seed=1)
        s = _cosine(probe, g1)  # actual achieved similarity
        g = {"P1": [{"embedding": g1.tolist()}]}
        self.assertIsNone(best_match(probe, g, threshold=s + 1e-5))
        self.assertIsNotNone(best_match(probe, g, threshold=s))  # >= threshold passes
        self.assertIsNone(best_match(probe, g, threshold=s + 0.05))

    def test_multiple_entries_per_player_take_best(self):
        g = gallery(self.probe, {"P1": [0.30, 0.55], "P2": [0.45]})
        m = best_match(self.probe, g, threshold=0.4, margin=0.05)
        self.assertEqual(m["player_id"], "P1")
        self.assertAlmostEqual(m["similarity"], 0.55, places=4)
        self.assertAlmostEqual(m["margin"], 0.10, places=4)  # best_other = P2 0.45
        self.assertIsNone(best_match(self.probe, g, threshold=0.4, margin=0.12))  # gap 0.10 too small
        g = gallery(self.probe, {"P1": [0.30, 0.55], "P2": [0.45]})
        m = best_match(self.probe, g, threshold=0.4, margin=0.05)
        self.assertEqual(m["player_id"], "P1")
        self.assertAlmostEqual(m["similarity"], 0.55, places=4)
        self.assertAlmostEqual(m["margin"], 0.10, places=4)  # best_other = P2 0.45

    def test_single_player_gallery_has_inf_margin(self):
        m = best_match(self.probe, gallery(self.probe, {"P1": [0.55]}), threshold=0.4, margin=1e9)
        self.assertEqual(m["player_id"], "P1")
        self.assertEqual(m["margin"], float("inf"))

    def test_defaults_reject_weak_and_accept_strong(self):
        self.assertIsNotNone(best_match(self.probe, gallery(self.probe, {"P1": [0.9]})))
        self.assertIsNone(best_match(self.probe, gallery(self.probe, {"P1": [0.2]})))
        self.assertEqual(DEFAULT_THRESHOLD, 0.35)
        self.assertEqual(DEFAULT_MARGIN, 0.12)

    def test_empty_and_none(self):
        self.assertIsNone(best_match(self.probe, {}))
        self.assertIsNone(best_match(self.probe, []))
        self.assertIsNone(best_match(None, gallery(self.probe, {"P1": [0.9]})))


class Persistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "face_embeddings.json"
        self.probe = unit_probe()

    def entry(self, **over):
        e = {"embedding": vec_at(self.probe, 0.9, seed=3),
             "eye_px": 10.4, "det_score": 0.912, "source": "vod_30min_260815.png"}
        e.update(over)
        return e

    def test_roundtrip(self):
        stored = store_faces(self.path, {"P1": [self.entry()]})
        self.assertEqual(stored, load_faces(self.path))  # write == read
        row = stored["P1"][0]
        emb = row["embedding"]
        self.assertEqual(len(emb), 512)
        self.assertTrue(all(v == round(v, 4) for v in emb))  # 4dp-rounded
        self.assertAlmostEqual(float(np.linalg.norm(np.asarray(emb, np.float32))), 1.0, places=2)
        self.assertEqual(row["eye_px"], 10.4)
        self.assertEqual(row["det_score"], 0.912)
        self.assertEqual(row["source"], "vod_30min_260815.png")
        self.assertTrue(datetime.fromisoformat(row["created_at"]))  # valid ISO timestamp

    def test_store_accepts_embedding_lists_and_fills_created_at_once(self):
        first = store_faces(self.path, {"P1": [{"embedding": self.entry()["embedding"].tolist(),
                                                "eye_px": None, "det_score": 0.5}]})
        ts = first["P1"][0]["created_at"]
        self.assertEqual(load_faces(self.path), first)
        # re-store same entry: created_at was persisted, not regenerated
        again = store_faces(self.path, load_faces(self.path))
        self.assertEqual(again["P1"][0]["created_at"], ts)

    def test_atomic_no_tmp_files_and_overwrite(self):
        store_faces(self.path, {"P1": [self.entry()]})
        store_faces(self.path, {"P2": [self.entry()]})
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["face_embeddings.json"])
        self.assertEqual(set(load_faces(self.path)), {"P2"})

    def test_corrupted_and_missing_tolerated(self):
        for content in ("{not json", "", "[1, 2, 3]", "null"):
            self.path.write_text(content, encoding="utf-8")
            self.assertEqual(load_faces(self.path), {})
        self.assertEqual(load_faces(Path(self.tmp.name) / "missing.json"), {})

    def test_default_store_location_is_not_operations_state(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(DEFAULT_FACE_STORE, root / "out" / "corner-pocket" / "face_embeddings.json")
        self.assertNotEqual(DEFAULT_FACE_STORE.name, "state.json")


class EmbedImage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_ndarray_branch_returns_all_faces_unfiltered(self):
        probe = unit_probe()
        engine = FaceEngine(analyzer=FakeAnalyzer([
            FakeFace([0, 0, 80, 80], kps=[[10, 10], [20, 10]], det_score=0.95, normed=probe),
            FakeFace([200, 200, 260, 260], kps=[[210, 210], [220, 210]], det_score=0.2, normed=probe),
        ]))
        with patch("src.face_id.get_face_engine", return_value=engine):
            records = embed_image(np.zeros((300, 300, 3), np.uint8))
        self.assertEqual(len(records), 2)  # low-quality second face kept; caller gates with quality()
        self.assertIsInstance(records[0], FaceRecord)
        self.assertEqual(records[0].bbox, [0.0, 0.0, 80.0, 80.0])
        self.assertEqual(records[0].eye_px, 10.0)
        self.assertEqual(records[0].det_score, 0.95)
        self.assertIsNone(records[0].source)
        self.assertAlmostEqual(float(np.linalg.norm(records[1].embedding)), 1.0, places=5)
        self.assertTrue(quality({"eye_px": records[0].eye_px, "det_score": records[0].det_score}))
        self.assertFalse(quality({"eye_px": records[1].eye_px, "det_score": records[1].det_score}))

    def test_missing_path_raises(self):
        with patch("cv2.imread", return_value=None):  # no imread warning noise
            with patch("src.face_id.get_face_engine", return_value=FaceEngine(analyzer=FakeAnalyzer([]))):
                with self.assertRaises(FileNotFoundError):
                    embed_image(Path(self.tmp.name) / "missing.jpg")


if __name__ == "__main__":
    unittest.main()