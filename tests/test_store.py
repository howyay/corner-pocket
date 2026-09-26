"""src/store.py: the Store interface and its JSON implementation (the default).

JsonStore is today's file storage behind one interface: the same paths, the same
file formats, the same semantics (docs/postgres-design.md section 7.1). These tests
pin that contract on temp roots; nothing here touches the repository's out/.
A Postgres implementation arrives later and must pass the same contract.
"""
import hashlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from annotator.operations import ConflictError, Operations
from src import store as store_module
from src.store import JsonStore, Store, open_store


def stamp(path):
    path = Path(path)
    return hashlib.md5(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns


def unit(seed, dim=512):
    rng = np.random.RandomState(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.out = self.root / "out"
        self.store = JsonStore(self.root)


class Selection(StoreTestCase):
    def test_json_is_the_default_and_postgres_is_chosen_only_by_the_variable(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("POOL_DATABASE_URL", None)
            chosen = open_store(self.root)
        self.assertIsInstance(chosen, JsonStore)
        self.assertIsInstance(chosen, Store)
        with mock.patch.dict(os.environ, {"POOL_DATABASE_URL": "postgresql://u@127.0.0.1:1/x"}):
            chosen = open_store(self.root)     # constructing it connects to nothing
        from src.store_pg import PostgresStore
        self.assertIsInstance(chosen, PostgresStore)
        self.assertIsInstance(chosen, Store)

    def test_constructing_a_store_writes_nothing(self):
        self.assertFalse(self.out.exists())


class OperationsContract(StoreTestCase):
    def test_the_document_and_its_revision_contract_are_the_operations_module(self):
        first = self.store.ops_get()
        self.assertEqual(first["revision"], 0)
        saved = self.store.ops_post({"action": "player_save", "revision": 0, "name": "Ada"})
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(self.store.ops_get(), saved)
        self.assertEqual(Operations(self.root).get(), saved, "same file, same format as Operations")
        with self.assertRaises(ConflictError):
            self.store.ops_post({"action": "note_add", "revision": 0, "text": "stale"})

    def test_enrol_player_goes_through_the_revisioned_store(self):
        self.store.ops_post({"action": "note_add", "revision": 0, "text": "kept"})
        state = self.store.enroll_player({"id": "p1", "name": "Ana"}, {"player_id": "p1", "name": "Ana"})
        self.assertEqual([p["name"] for p in state["players"]], ["Ana"])
        self.assertEqual([n["text"] for n in state["notes"]], ["kept"])
        self.assertEqual(state["events"][-1]["action"], "player_enroll_from_tracklet")


class IdentityContract(StoreTestCase):
    def test_faces_merge_and_forget_per_player(self):
        self.assertEqual(self.store.faces_load(), {})
        self.store.faces_add({"A": [{"embedding": unit(1), "eye_px": 12.0, "det_score": 0.9}]})
        self.store.faces_add({"B": [{"embedding": unit(2), "eye_px": 11.0, "det_score": 0.8}]})
        gallery = self.store.faces_load()
        self.assertEqual(sorted(gallery), ["A", "B"])
        self.assertEqual(self.store.faces_remove("A"), 1)
        self.assertEqual(sorted(self.store.faces_load()), ["B"])
        self.assertEqual(self.store.faces_remove("nobody"), 0)
        path = self.out / "corner-pocket" / "face_embeddings.json"
        self.assertEqual(json.loads(path.read_text()), self.store.faces_load())

    def test_identity_index_is_the_clusters_file(self):
        self.assertEqual(self.store.identity_load(), {})
        path = self.out / "identity" / "clusters.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"3": {"player_id": None, "body_bank": [], "face": None,
                                          "last_seen_frame": 7}}))
        self.assertEqual(self.store.identity_load()["3"]["last_seen_frame"], 7)
        self.assertEqual(self.store.identity_path(), path)

    def test_seeds_put_and_clear_keep_other_keys(self):
        path = self.out / "pid_seed.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"seeds": {"1:68-94": {"win": "68-94", "t": 68, "track_id": 1,
                                                          "label": "A", "custom": "keep"}}, "custom": True}))
        seeds = self.store.seed_put("vod30", "2:68-94", {"win": "68-94", "t": 69, "track_id": 2, "label": "B"})
        self.assertEqual(sorted(seeds), ["1:68-94", "2:68-94"])
        self.assertEqual(self.store.seeds_get("vod30")["1:68-94"]["custom"], "keep")
        self.assertEqual(sorted(self.store.seed_put("vod30", "1:68-94", None)), ["2:68-94"])
        self.assertTrue(json.loads(path.read_text())["custom"], "top-level keys survive")


class OperatorRecordsContract(StoreTestCase):
    def test_verdicts_merge_per_event_and_datasets_stay_apart(self):
        record = self.store.verdict_put("vod30", 16, {"verdict": "wrong", "note": "x"})
        self.assertEqual(record["verdict"], "wrong")
        self.assertIn("updated_at", record)
        merged = self.store.verdict_put("vod30", 16, {"shooter": "A"})
        self.assertEqual((merged["verdict"], merged["shooter"], merged["note"]), ("wrong", "A", "x"))
        self.assertEqual(self.store.verdicts_get("highlight"), {})
        self.assertEqual(list(self.store.verdicts_get("vod30")), ["16"])
        self.assertTrue((self.out / "scan30" / "annotations.json").is_file())

    def test_ball_labels_keep_the_original_key_and_clear(self):
        crops = self.out / "unlabeled_crops"
        crops.mkdir(parents=True)
        (crops / "labels.json").write_text(json.dumps({"/abs/path/crop1.png": 4, "legacy": 8}))
        self.store.label_put("unlabeled_crops", "crop1.png", 7)
        self.store.label_put("unlabeled_crops", "crop2.png", "u")
        labels = self.store.labels_get("unlabeled_crops")
        self.assertEqual(labels, {"/abs/path/crop1.png": 7, "legacy": 8, "crop2.png": "u"})
        self.store.label_put("unlabeled_crops", "crop1.png", None)
        self.assertNotIn("/abs/path/crop1.png", self.store.labels_get("unlabeled_crops"))
        with self.assertRaises(ValueError):
            self.store.labels_get("not-a-set")

    def test_frame_corrections_and_anchors(self):
        self.assertIsNone(self.store.correction_get("vod30", 2100))
        self.store.correction_put("vod30", 2100, {"boxes": [], "saved_at": "t"})
        self.assertEqual(self.store.correction_get("vod30", 2100)["saved_at"], "t")
        self.assertTrue((self.out / "scan30" / "frame_results" / "2100" / "correction.json").is_file())
        self.assertEqual(self.store.anchors_get("vod30"), {"anchors": {}})
        self.store.anchors_put("vod30", "70.0", [[1, 2]] * 6)
        self.assertEqual(self.store.anchors_get("vod30")["anchors"]["70.0"], [[1, 2]] * 6)


class PrecomputedReads(StoreTestCase):
    def test_artifacts_queue_window_and_tracklets_read_the_files(self):
        scan = self.out / "scan30"
        scan.mkdir(parents=True)
        (scan / "events.json").write_text(json.dumps([{"id": 1, "t": 5.0}, {"id": 2, "t": 30.0},
                                                      {"id": 3, "t": 7.5}]))
        self.assertEqual([e["id"] for e in self.store.queue("vod30")], [1, 2, 3])
        self.assertEqual([e["id"] for e in self.store.queue_window("vod30", 4.0, 8.0)], [1, 3])
        (self.out / "pid2_tracklets.json").write_text(json.dumps({"68-94": {"tracklets": []}}))
        self.assertEqual(self.store.tracklets("vod30"), {"68-94": {"tracklets": []}})
        (self.out / "calib_vod30_segments.json").write_text(json.dumps({"segments": [1]}))
        self.assertEqual(self.store.artifact("calibration_segments", "vod30"), {"segments": [1]})
        self.assertIsNone(self.store.artifact("calibration", "vod30"))
        self.assertIsNone(self.store.frame_detections("vod30", 150), "JSON has no precomputed overlays")
        with self.assertRaises(ValueError):
            self.store.artifact("unknown-kind", "vod30")


class ReadOnlyContract(StoreTestCase):
    """A GET never writes: every read method leaves every file's bytes, size and mtime."""

    def test_every_read_leaves_every_file_alone(self):
        self.store.ops_post({"action": "player_save", "revision": 0, "name": "Ada"})
        self.store.faces_add({"A": [{"embedding": unit(1), "eye_px": 12.0, "det_score": 0.9}]})
        self.store.seed_put("vod30", "1:68-94", {"win": "68-94", "t": 68, "track_id": 1, "label": "A"})
        self.store.verdict_put("vod30", 1, {"verdict": "correct"})
        self.store.label_put("unlabeled_crops", "c.png", 3)
        self.store.correction_put("vod30", 5, {"boxes": []})
        self.store.anchors_put("vod30", "70.0", [[0, 0]] * 6)
        (self.out / "scan30" / "events.json").write_text(json.dumps([{"id": 1, "t": 5.0}]))
        files = sorted(p for p in self.out.rglob("*") if p.is_file())
        before = {p: stamp(p) for p in files}
        for read in (lambda s: s.ops_get(), lambda s: s.faces_load(), lambda s: s.identity_load(),
                     lambda s: s.seeds_get("vod30"), lambda s: s.verdicts_get("vod30"),
                     lambda s: s.verdicts_get("highlight"), lambda s: s.labels_get("unlabeled_crops"),
                     lambda s: s.correction_get("vod30", 5), lambda s: s.correction_get("vod30", 6),
                     lambda s: s.anchors_get("vod30"), lambda s: s.queue("vod30"),
                     lambda s: s.queue_window("vod30", 0, 10), lambda s: s.tracklets("vod30"),
                     lambda s: s.artifact("queue_report", "vod30"), lambda s: s.frame_detections("vod30", 1)):
            read(self.store)
        self.assertEqual(sorted(p for p in self.out.rglob("*") if p.is_file()), files, "no file appears")
        self.assertEqual({p: stamp(p) for p in files}, before, "no file changes")


class Concurrency(StoreTestCase):
    def test_concurrent_verdicts_on_different_events_are_all_kept(self):
        barrier = threading.Barrier(8)

        def worker(n):
            barrier.wait()
            self.store.verdict_put("vod30", n, {"verdict": "correct"})

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(self.store.verdicts_get("vod30"), key=int), [str(n) for n in range(8)])


if __name__ == "__main__":
    unittest.main()
