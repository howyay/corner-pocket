"""Tests for src/person_identity.py — synthetic embeddings only, no model
downloads, no boxmot import needed (embeddings are injected)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from person_identity import IdentityIndex  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.face_id import (  # noqa: E402
    CANDIDATE_BIND_BAR,
    DEFAULT_BIND_BAR,
    DEFAULT_MARGIN,
    DEFAULT_THRESHOLD,
    accept_match,
    best_match,
)

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
        self.assertEqual(self.index.effective_bind_bar, DEFAULT_BIND_BAR)
        self.assertTrue(self.index.bind_face(cid, "playerF", similarity=0.9))
        self.assertEqual(self.index.get(cid)["player_id"], "playerF")

    # -- the binding bar is the composed one, and it enforces the margin ----

    def test_effective_bind_bar_is_threshold_plus_margin(self):
        """0.35 alone never binds: the bar is threshold + margin (0.47)."""
        self.assertEqual(DEFAULT_THRESHOLD, 0.35)
        self.assertEqual(DEFAULT_BIND_BAR, 0.47)
        self.assertEqual(self.index.effective_bind_bar, 0.47)
        cid = self.index.register(1, unit(0))[1]
        self.assertFalse(self.index.bind_face(cid, "playerA", similarity=0.46),
                         "0.46 clears the 0.35 threshold but not the 0.47 bar")
        self.assertTrue(self.index.bind_face(cid, "playerA", similarity=0.47))

    def test_bind_bar_rule_follows_configured_threshold_and_margin(self):
        """The rule (bar = threshold + margin), not the number, is pinned."""
        idx = IdentityIndex(path=self.path, match_threshold=0.4, margin=0.2)
        self.assertEqual(idx.effective_bind_bar, 0.6)
        cid = idx.register(1, unit(0))[1]
        self.assertFalse(idx.bind_face(cid, "playerA", similarity=0.5999))
        self.assertTrue(idx.bind_face(cid, "playerA", similarity=0.6),
                        "the bar is exactly threshold + margin, no float drift")

    def test_explicit_bind_bar_overrides_the_composition(self):
        """A pinned bind_bar is used as-is, so a candidate can be tried without
        moving the matching threshold (default stays the deployed 0.47)."""
        idx = IdentityIndex(path=self.path, bind_bar=CANDIDATE_BIND_BAR)
        self.assertEqual(idx.effective_bind_bar, CANDIDATE_BIND_BAR)
        self.assertEqual(CANDIDATE_BIND_BAR, 0.65)
        cid = idx.register(1, unit(0))[1]
        self.assertFalse(idx.bind_face(cid, "playerA", similarity=0.649))
        self.assertTrue(idx.bind_face(cid, "playerA", similarity=0.65))
        self.assertEqual(IdentityIndex(path=self.path).effective_bind_bar, DEFAULT_BIND_BAR)

    def test_bind_rejects_a_runner_up_inside_the_margin(self):
        """Defect proof: best match clears the bar, runner-up inside the margin."""
        cid = self.index.register(1, unit(0))[1]
        # 0.80 >= 0.47 bar, but the other enrolled player is only 0.10 behind
        self.assertFalse(self.index.bind_face(cid, "playerA", similarity=0.80, runner_up=0.70),
                         "an ambiguous probe must not bind")
        self.assertIsNone(self.index.get(cid)["player_id"])
        # same similarity, runner-up clear of the margin -> binds
        self.assertTrue(self.index.bind_face(cid, "playerA", similarity=0.80, runner_up=0.68))
        self.assertEqual(self.index.get(cid)["player_id"], "playerA")

    def test_bind_margin_boundary_is_inclusive(self):
        cid = self.index.register(1, unit(0))[1]
        self.assertFalse(self.index.bind_face(cid, "playerA", similarity=0.80, runner_up=0.68001))
        self.assertTrue(self.index.bind_face(cid, "playerA", similarity=0.80, runner_up=0.68))

    def test_bind_without_a_runner_up_means_no_competing_enrolment(self):
        """runner_up=None is the single-player gallery case best_match reports
        as an infinite margin; supplying it is what turns the margin on."""
        cid = self.index.register(1, unit(0))[1]
        self.assertTrue(self.index.bind_face(cid, "playerA", similarity=0.9))
        self.assertIsNone(self.index.get(cid)["bound_evidence"]["runner_up"])
        self.assertEqual(self.index.get(cid)["bound_evidence"]["bind_bar"], 0.47)

    def test_bind_records_the_runner_up_and_bar_it_used(self):
        cid = self.index.register(1, unit(0))[1]
        self.assertTrue(self.index.bind_face(cid, "playerA", similarity=0.82, runner_up=0.61))
        evidence = self.index.get(cid)["bound_evidence"]
        self.assertAlmostEqual(evidence["runner_up"], 0.61, places=6)
        self.assertEqual(evidence["bind_bar"], 0.47)

    def test_shared_rule_is_the_same_for_matching_and_binding(self):
        """best_match() and bind_face() call the one accept_match() rule."""
        self.assertTrue(accept_match(0.4, None, bind=False))
        self.assertFalse(accept_match(0.4, None, bind=True), "0.4 is under the 0.47 bar")
        self.assertTrue(accept_match(0.47, None, bind=True))
        self.assertFalse(accept_match(0.80, 0.70, bind=True), "margin 0.10 < 0.12")
        self.assertTrue(accept_match(0.80, 0.68, bind=True))
        # best_match carries the runner-up so the binding path can re-check it
        probe = unit(0)
        gallery = {"P1": [{"embedding": probe.tolist()}],
                   "P2": [{"embedding": (probe + unit(1)).tolist()}]}  # ~0.707 to the probe
        match = best_match(probe, gallery, threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN)
        self.assertIsNotNone(match)
        self.assertEqual(match["player_id"], "P1")
        self.assertIsNotNone(match["runner_up"])
        self.assertAlmostEqual(match["similarity"] - match["runner_up"], match["margin"], places=6)

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

    def test_tracking_updates_never_write_the_index_file(self):
        """register()/update() run on the read path: every observed frame goes
        process_frame -> update -> register, including GET /api/identity/frame
        and GET /api/unified. A tracker update is observation, not a decision, so
        it must not rewrite the file - otherwise no read-only verification can
        compare bytes and concurrent readers can race on the path. The write
        belongs to the binding, and it writes the accumulated state with it."""
        self.assertFalse(self.path.exists(), "a fresh index persists nothing")
        self.index.update([{"track_id": 1, "embedding": unit(0), "frame_index": 1},
                           {"track_id": 2, "embedding": unit(3), "frame_index": 1}])
        self.assertFalse(self.path.exists(), "update()/register() must not create the index")
        self.assertTrue(self.index.bind_face(1, "playerQ", 0.99), "the face binding is accepted")
        self.assertTrue(self.path.exists(), "a binding is persisted where it is made")
        self.assertEqual(json.loads(self.path.read_text())["1"]["player_id"], "playerQ")
        bytes_before, mtime_before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.index.update([{"track_id": 3, "embedding": unit(5), "frame_index": 2}])
        self.assertEqual(self.path.read_bytes(), bytes_before, "later tracking leaves the bytes alone")
        self.assertEqual(self.path.stat().st_mtime_ns, mtime_before, "and never touches the mtime")
        # The mutation that follows still persists everything accumulated.
        self.index.explicit_assign(3, "playerR", reason="unbind")
        self.assertNotEqual(self.path.read_bytes(), bytes_before, "an explicit change still writes")

    def test_bank_bound_and_persist_cap(self):
        for i in range(40):
            self.index.register(1, near(0, noise=0.01 * (i % 5) - 0.02), frame_index=i)
        c = self.index._clusters[1]
        self.assertLessEqual(len(c.bank), 32)
        self.index.save()
        rec = json.loads(self.path.read_text())["1"]
        self.assertEqual(len(rec["body_bank"]), 8)


if __name__ == "__main__":
    unittest.main()
