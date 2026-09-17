"""Tests for src/person_identity.py — synthetic embeddings only, no model
downloads, no boxmot import needed (embeddings are injected)."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from person_identity import IdentityIndex  # noqa: E402

DIM = 8


def unit(i: int) -> np.ndarray:
    v = np.zeros(DIM, np.float32)
    v[i] = 1.0
    return v


def near(i: int, noise: float = 0.03) -> np.ndarray:
    v = unit(i) + noise * np.random.default_rng(i).standard_normal(DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def mix(i: int, j: int) -> np.ndarray:
    """Vector with equal cosine ~0.707 to two orthogonal units (margin ambiguity)."""
    v = unit(i) + unit(j)
    return v / np.linalg.norm(v)


def body_enabled_index(path) -> IdentityIndex:
    """Index with body merging explicitly re-enabled (legacy 0.35/0.12 bar).

    Measured calibration (tests/test_body_calibration.py) showed OSNet body
    same/cross-person cosine distributions OVERLAP on this footage, so the
    default index ships with body matching disabled (BODY_MATCH_DISABLED).
    These constants are used here only to exercise the merge/margin/persist
    mechanism.
    """
    return IdentityIndex(path=path, body_match_threshold=0.35, body_margin=0.12)


class PersonIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "clusters.json"
        self.index = IdentityIndex(path=self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_body_matching_disabled_no_merge(self):
        """Calibrated default: identical embeddings never merge on body evidence."""
        c1 = self.index.register(1, unit(0), frame_index=1)[1]
        c2 = self.index.register(2, unit(0), frame_index=900)[2]
        self.assertNotEqual(c1, c2)
        self.assertEqual(self.index.clusters(), [1, 2])
        self.assertEqual(self.index.body_match_threshold, float("inf"))

    def test_default_body_disabled_face_binding_still_works(self):
        """Face-binding-only mode: a fresh cluster binds via bind_face (0.47 bar)."""
        cid = self.index.register(1, unit(0))[1]
        self.assertTrue(self.index.bind_face(cid, "playerF", similarity=0.9))
        self.assertEqual(self.index.get(cid)["player_id"], "playerF")

    def test_first_registration_creates_cluster(self):
        out = self.index.register(101, unit(0), frame_index=10)
        self.assertEqual(out, {101: 1})
        self.assertEqual(self.index.get(1)["last_seen_frame"], 10)
        self.assertEqual(self.index.get(1)["samples"], 1)
        self.assertIsNone(self.index.get(1)["player_id"])

    def test_near_identical_second_track_merges(self):
        """Cross-exit merge mechanism (body matching explicitly enabled)."""
        idx = body_enabled_index(self.path)
        idx.register(1, unit(0), frame_index=10)
        out = idx.register(2, near(0), frame_index=900)
        self.assertEqual(out, {2: 1})
        g = idx.get(1)
        self.assertEqual(g["samples"], 2)
        self.assertEqual(g["last_seen_frame"], 900)

    def test_orthogonal_track_gets_new_cluster(self):
        self.index.register(1, unit(0), frame_index=10)
        out = self.index.register(2, unit(1), frame_index=20)
        self.assertEqual(out, {2: 2})
        self.assertEqual(self.index.clusters(), [1, 2])

    def test_margin_ambiguity_rejected_new_cluster(self):
        """Best >= body MATCH but best - second < body MARGIN -> new cluster."""
        idx = body_enabled_index(self.path)
        idx.register(1, unit(0), frame_index=1)
        idx.register(2, unit(1), frame_index=2)
        v = mix(0, 1)  # ~0.707 to both clusters
        out = idx.register(3, v, frame_index=3)
        self.assertEqual(out, {3: 3})
        self.assertEqual(idx.clusters(), [1, 2, 3])

    def test_face_bind_once_then_no_rebinding(self):
        cid = self.index.register(1, unit(0), face_embedding=unit(DIM - 1)) [1]
        self.assertTrue(self.index.bind_face(cid, "playerA", similarity=0.9, evidence="crop f12"))
        self.assertEqual(self.index.get(cid)["player_id"], "playerA")
        self.assertEqual(self.index.get(cid)["bound_evidence"]["source"], "bind_face")
        # low similarity rejected
        self.assertFalse(self.index.bind_face(cid, "playerB", similarity=0.2, evidence="weak"))
        # confident but late -> no auto-rebinding
        self.assertFalse(self.index.bind_face(cid, "playerB", similarity=0.99, evidence="crop f50"))
        self.assertEqual(self.index.get(cid)["player_id"], "playerA")

    def test_seed_override_wins(self):
        cid = self.index.register(1, unit(0))[1]
        self.index.explicit_assign(cid, "playerS", reason="scoreboard")
        self.assertEqual(self.index.get(cid)["player_id"], "playerS")
        self.assertEqual(self.index.get(cid)["bound_evidence"]["source"], "explicit_assign")
        self.assertFalse(self.index.bind_face(cid, "playerX", similarity=0.99, evidence="late"))
        self.assertEqual(self.index.get(cid)["player_id"], "playerS")

    def test_persistence_roundtrip(self):
        idx = body_enabled_index(self.path)
        cid = idx.register(1, unit(0), face_embedding=unit(7), frame_index=5)[1]
        idx.explicit_assign(cid, "playerP")
        # fresh index over the same file
        idx2 = body_enabled_index(self.path)
        self.assertEqual(idx2.clusters(), [cid])
        g = idx2.get(cid)
        self.assertEqual(g["player_id"], "playerP")
        self.assertEqual(g["last_seen_frame"], 5)
        self.assertTrue(np.allclose(idx2._clusters[cid].bank[0], unit(0)))
        self.assertTrue(np.allclose(idx2._clusters[cid].face, unit(7)))
        # loaded cluster still participates in re-association
        self.assertEqual(idx2.register(9, near(0), frame_index=6), {9: cid})
        self.assertEqual(idx2._next_id, 2)

    def test_dim_mismatch_rejected(self):
        self.index.register(1, unit(0))
        with self.assertRaises(ValueError):
            self.index.register(2, np.ones(4, np.float32))
        with self.assertRaises(ValueError):
            self.index.update([{"track_id": 3, "embedding": np.ones(16, np.float32)}])
        self.assertEqual(self.index.clusters(), [1])

    def test_update_seam_and_idempotent_track(self):
        idx = body_enabled_index(self.path)
        out = idx.update(
            [
                {"track_id": 1, "embedding": unit(0), "frame_index": 1, "timestamp": 0.1},
                {"track_id": 2, "embedding": near(0), "frame_index": 2, "timestamp": 0.2},
            ]
        )
        self.assertEqual(out, {1: 1, 2: 1})
        # same track_id re-registered -> same cluster, no new cluster
        again = idx.update([{"track_id": 2, "embedding": near(0), "frame_index": 3}])
        self.assertEqual(again, {2: 1})
        self.assertEqual(idx.get(1)["samples"], 3)

    def test_bank_bound_and_persist_cap(self):
        for i in range(40):
            self.index.register(1, near(0, noise=0.01 * (i % 5) - 0.02), frame_index=i)
        c = self.index._clusters[1]
        self.assertLessEqual(len(c.bank), 32)
        self.index.save()
        import json
        rec = json.loads(self.path.read_text())["1"]
        self.assertEqual(len(rec["body_bank"]), 8)


if __name__ == "__main__":
    unittest.main()
