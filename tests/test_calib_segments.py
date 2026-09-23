"""Pins for the per-segment calibration reference.

Two things must hold for a per-segment reference to be safer than the single ``H``
it replaces:

1. **a frame resolves to exactly one segment** - a lookup that can return two
   references, or none, is worse than the status quo it fixes;
2. **an out-of-range frame falls back cleanly** - a time before the first segment,
   after the last, or absent entirely gets a defined reference and a flag, never
   an exception and never silence.

The artifact's shape is pinned too: the consumers (``src/table_refine.prior_for``,
the server's event geometry) read named fields, so a producer that renames or
drops one must fail here rather than silently disable per-segment projection.
"""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import calib_segments as cs  # noqa: E402

ARTIFACT = ROOT / "out" / "calib_vod30_segments.json"


def write_artifact(out, segments, verdict="split_supported"):
    out.mkdir(parents=True, exist_ok=True)
    payload = {"dataset": "vod30", "segmentation_verdict": verdict, "segments": segments}
    (out / "calib_vod30_segments.json").write_text(json.dumps(payload))
    return payload


def seg(seg_id, t_start, t_end, x=100.0, source="human_anchors"):
    return {"id": seg_id, "t_start": t_start, "t_end": t_end, "source": source,
            "quad_px": [[x, 100.0], [x + 500, 110.0], [x + 520, 500.0], [x - 20, 490.0]],
            "coverage": {"median": 0.99}, "evidence": {"trusted_for_mm": True}}


class SegmentLookupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_artifact(self.root / "out", [seg("a", 0.0, 600.0),
                                            seg("b", 600.001, 1800.0, x=80.0, source="derived")])
        self.model = cs.load("vod30", root=self.root, use_cache=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_frame_resolves_to_exactly_one_segment(self):
        for t in (0.0, 1.0, 599.9, 600.0, 600.001, 1200.0, 1800.0):
            seg = self.model.resolve(t)
            self.assertIsNotNone(seg, t)
            matches = [s for s in self.model.segments if s.t_start <= t <= s.t_end]
            self.assertEqual(len(matches), 1, f"t={t} matches {len(matches)} segments")
            self.assertEqual(seg.id, matches[0].id)
            self.assertFalse(seg.clamped, t)
        self.assertEqual(self.model.resolve(300.0).id, "a")
        self.assertEqual(self.model.resolve(300.0).source, "human_anchors")
        self.assertEqual(self.model.resolve(1200.0).id, "b")
        self.assertTrue(self.model.resolve(1200.0).human is False)
        self.assertEqual(self.model.resolve(1200.0).source, "derived")

    def test_out_of_range_frame_falls_back_cleanly(self):
        for t, expected in ((-5.0, "a"), (1800.001, "b"), (1e9, "b")):
            seg = self.model.resolve(t)
            self.assertEqual(seg.id, expected, t)
            self.assertTrue(seg.clamped, t)
            self.assertEqual(seg.clamp_reason, "outside_all_segments")
            self.assertFalse(self.model.in_range(t), t)
            self.assertEqual(len(seg.quad), 4, "a clamped lookup still returns usable geometry")
        for t in (None, float("nan"), "not-a-time"):
            seg = self.model.resolve(t)
            self.assertEqual(seg.id, "a")
            self.assertTrue(seg.clamped)
            self.assertEqual(seg.clamp_reason, "no_time")

    def test_in_range_is_exact_and_clamping_does_not_mutate_the_model(self):
        self.assertTrue(self.model.in_range(300.0))
        self.assertTrue(self.model.in_range(1800.0))
        self.assertFalse(self.model.in_range(1800.5))
        self.assertFalse(self.model.in_range(None))
        before = [s.as_dict() for s in self.model.segments]
        self.model.resolve(99999)
        self.model.resolve(None)
        self.assertEqual([s.as_dict() for s in self.model.segments], before)

    def test_homography_tracks_the_segment_and_round_trips(self):
        forward_a, inverse_a, seg_a = self.model.homographies(10.0)
        forward_b, inverse_b, seg_b = self.model.homographies(1000.0)
        self.assertEqual((seg_a.id, seg_b.id), ("a", "b"))
        for forward, inverse in ((forward_a, inverse_a), (forward_b, inverse_b)):
            px = np.array([300.0, 250.0, 1.0])
            mm = forward @ px
            mm = mm[:2] / mm[2]
            back = inverse @ np.array([mm[0], mm[1], 1.0])
            back = back[:2] / back[2]
            self.assertTrue(np.allclose(back, px[:2], atol=0.5))
        self.assertLess(abs(forward_a[0][2] - forward_b[0][2]), 1e9)
        self.assertNotEqual(self.model.quad_for(10.0).tolist(), self.model.quad_for(1000.0).tolist())

    def test_overlapping_segments_are_reported_and_first_wins(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_artifact(root / "out", [seg("a", 0.0, 700.0), seg("b", 600.0, 1800.0, x=80.0)])
            model = cs.load("vod30", root=root, use_cache=False)
            self.assertTrue(model.warnings, "an overlap must be reported, not silently resolved")
            self.assertTrue(any("overlap" in w for w in model.warnings))
            self.assertEqual(model.resolve(650.0).id, "a")
            self.assertTrue(model.resolve(1000.0).id == "b")

    def test_missing_or_broken_artifact_is_not_an_error(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(cs.load("vod30", root=root, use_cache=False))
            (root / "out").mkdir(parents=True)
            (root / "out" / "calib_vod30_segments.json").write_text("{not json")
            self.assertIsNone(cs.load("vod30", root=root, use_cache=False))
            write_artifact(root / "out", [])
            self.assertIsNone(cs.load("vod30", root=root, use_cache=False),
                              "an artifact with no segments is not a reference")
            write_artifact(root / "out", [{"id": "x", "t_start": 0, "t_end": 10,
                                           "quad_px": [[0, 0], [1, 1]]}])
            self.assertIsNone(cs.load("vod30", root=root, use_cache=False),
                              "a malformed quad must be dropped, not raised")

    def test_gaps_are_reported(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_artifact(root / "out", [seg("a", 0.0, 100.0), seg("b", 200.0, 300.0, x=80.0)])
            model = cs.load("vod30", root=root, use_cache=False)
            self.assertEqual(model.gaps(), [(100.0, 200.0)])
            self.assertEqual(model.resolve(150.0).id, "a", "a gap clamps to the nearest segment")
            self.assertTrue(model.resolve(150.0).clamped)

    def test_prior_for_uses_the_segment_when_one_exists(self):
        from src import table_refine
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_artifact(root / "out", [seg("a", 0.0, 600.0), seg("b", 600.001, 1800.0, x=80.0)])
            (root / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
                {"anchors": {"70.0": [[10, 10], [20, 10], [20, 20], [10, 20], [1, 1], [2, 2]]}}))
            early = table_refine.prior_for("vod30", 100.0, root=root)
            late = table_refine.prior_for("vod30", 1500.0, root=root)
            self.assertIsNotNone(early)
            self.assertIsNotNone(late)
            self.assertNotEqual(np.asarray(early).tolist(), np.asarray(late).tolist(),
                                "the late segment must not reuse the early reference")
            prov = table_refine.prior_provenance("vod30", 1500.0, root=root)
            self.assertEqual((prov["kind"], prov["id"]), ("segment", "b"))
            # ...and without the artifact the saved prior answers exactly as before.
            bare = Path(tmp) / "bare"
            (bare / "out").mkdir(parents=True)
            (bare / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
                {"anchors": {"70.0": [[10, 10], [20, 10], [20, 20], [10, 20], [1, 1], [2, 2]]}}))
            self.assertEqual(np.asarray(table_refine.prior_for("vod30", 1500.0, root=bare)).shape, (4, 2))
            self.assertEqual(table_refine.prior_provenance("vod30", 1500.0, root=bare)["kind"],
                             "saved_prior")


class ArtifactShapeTest(unittest.TestCase):
    """The shipped artifact must carry every field the consumers read."""

    @classmethod
    def setUpClass(cls):
        if not ARTIFACT.is_file():
            raise unittest.SkipTest("out/calib_vod30_segments.json not built")
        cls.payload = json.loads(ARTIFACT.read_text())
        cls.model = cs.load("vod30", path=ARTIFACT, use_cache=False)

    def test_top_level_fields(self):
        for key in ("dataset", "video", "frame_size", "canonical_mm", "segmentation_verdict",
                    "verdict_reason", "framing_test", "segments", "boundary_candidates",
                    "late_window_alternative", "notes"):
            self.assertIn(key, self.payload, key)
        self.assertEqual(self.payload["dataset"], "vod30")
        self.assertEqual(self.payload["frame_size"], [1280, 720])
        self.assertEqual(self.payload["canonical_mm"], {"w": 1270.0, "h": 2540.0})
        self.assertIn(self.payload["segmentation_verdict"], ("single_segment", "split_supported"))

    def test_every_segment_carries_the_required_fields(self):
        self.assertTrue(self.payload["segments"])
        for segment in self.payload["segments"]:
            for key in ("id", "t_start", "t_end", "quad_px", "source", "coverage", "evidence"):
                self.assertIn(key, segment, key)
            self.assertIn(segment["source"], cs.SOURCES)
            self.assertLess(segment["t_start"], segment["t_end"])
            quad = np.asarray(segment["quad_px"], float)
            self.assertEqual(quad.shape, (4, 2))
            self.assertTrue(0 <= quad[:, 0].max() <= 1280 and 0 <= quad[:, 1].max() <= 720)
            self.assertIn("metric", segment["coverage"])
            self.assertIn("median", segment["coverage"])
            self.assertIn("frames_below_gate", segment["coverage"])
            evidence = segment["evidence"]
            self.assertIn("phase_shift_max_px", evidence)
            self.assertIn("per_side_offset_px", evidence)
            self.assertIn("verified_samples", evidence)
            self.assertIn("frames_all_four_sides_verified", evidence)

    def test_the_segment_covers_every_sampled_time(self):
        seg = self.payload["segments"][0]
        sampled = [s["t"] for s in self.payload["framing_test"]["samples"]]
        self.assertTrue(sampled)
        self.assertLessEqual(seg["t_start"], min(sampled))
        self.assertGreaterEqual(seg["t_end"], max(sampled))
        for t in sampled:
            self.assertTrue(self.model.in_range(t), t)

    def test_the_framing_test_did_not_fire_where_coverage_dropped(self):
        """A coverage dip is not a framing change - the whole point of the artifact."""
        below = [b for b in self.payload["boundary_candidates"]
                 if b["cause"] != "coverage_above_gate"]
        self.assertTrue(below, "the measured times the gate flagged must be recorded")
        for boundary in below:
            self.assertIn("framing_change", boundary)
            self.assertIn("coverage", boundary)
            if self.payload["segmentation_verdict"] == "single_segment":
                self.assertFalse(boundary["framing_change"],
                                 f"t={boundary['t']} was called a framing change under a "
                                 f"single-segment verdict")

    def test_late_alternative_is_counterfactual_and_recorded_as_derived(self):
        alt = self.payload["late_window_alternative"]
        self.assertIsNotNone(alt)
        self.assertFalse(alt["used"], "an unsupported split must not be in use")
        self.assertEqual(alt["source"], "derived")
        self.assertEqual(np.asarray(alt["quad_px"], float).shape, (4, 2))
        self.assertIn("agreement_with_segments", alt)
        self.assertIn("max_mm", alt["agreement_with_segments"])
        self.assertIn("per_side_evidence_gate", alt)
        self.assertIn("passed", alt["per_side_evidence_gate"])

    def test_human_source_is_never_claimed_by_a_derived_quad(self):
        for segment in self.payload["segments"]:
            if segment["source"] == "human_anchors":
                self.assertIn("pid_anchors", json.dumps(segment["source_detail"]))


class EventProjectionWiringTest(unittest.TestCase):
    """The server projects an event through its own segment - when there is one.

    Two pins, and the second is the more important one:

    * a ``split_supported`` artifact routes each event through the segment that
      owns its time, so a late-segment event is NOT drawn with the early reference;
    * a ``single_segment`` artifact changes **no pixels** - it only records which
      segment owns the time.  Swapping the drawn geometry there would replace the
      scan's self-consistent mapping with the cloth-quad calibration on evidence
      that says nothing about which the reviewer wants, and on vod30 those two
      disagree by up to 93 px at the head rail.
    """

    QUAD = [[100, 100], [1100, 120], [1120, 620], [90, 600]]
    EVENTS = [
        {"id": 7, "t": 5.6, "type": "pot", "last_mm": [5.0, 1270.0],
         "nearest_pocket": "left-side (5mm)"},
        {"id": 8, "t": 1400.0, "type": "shot", "disp_mm": 172, "ball_from": [100.0, 200.0],
         "ball_to": [300.0, 400.0]},
    ]

    def backend(self, temp, artifact=None):
        from annotator.unified_server import Backend, atomic_save
        out = Path(temp) / "out"
        atomic_save(out / "scan30" / "corners.json", {"corners": self.QUAD})
        atomic_save(out / "scan30" / "events.json", self.EVENTS)
        if artifact is not None:
            atomic_save(out / "calib_vod30_segments.json", artifact)
        return Backend(temp)

    @staticmethod
    def pixels(payload):
        return {event["id"]: (event["type"], event.get("px_source"), event.get("px_segment"),
                              event.get("last_px"), event.get("from_px"), event.get("to_px"))
                for event in payload["events"]}

    def test_single_segment_records_the_segment_without_moving_pixels(self):
        with TemporaryDirectory() as tmp_bare, TemporaryDirectory() as tmp_seg:
            bare = self.backend(tmp_bare)
            write_artifact(Path(tmp_seg) / "out", [seg("s1", 0.0, 1800.0, x=100.0)],
                           verdict="single_segment")
            with_seg = self.backend(tmp_seg, json.loads(
                (Path(tmp_seg) / "out" / "calib_vod30_segments.json").read_text()))
            before = bare.get(["api", "vod30", "events"], {})
            after = with_seg.get(["api", "vod30", "events"], {})
            self.assertEqual(before["geometry"], after["geometry"])
            self.assertEqual(set(self.pixels(before)), set(self.pixels(after)))
            for event_id, cell in self.pixels(before).items():
                drawn = self.pixels(after)[event_id]
                self.assertEqual(drawn[1], cell[1],
                                 "a single-segment artifact must not move an event's pixels")
                self.assertEqual((drawn[3], drawn[4], drawn[5]), (cell[3], cell[4], cell[5]),
                                 event_id)
                self.assertEqual(drawn[2], "s1",
                                 "the segment that owns the time is still recorded")

    def test_split_artifact_projects_a_late_event_with_its_own_segment(self):
        with TemporaryDirectory() as tmp:
            late = seg("late", 600.001, 1800.0, x=400.0, source="derived")
            write_artifact(Path(tmp) / "out", [seg("early", 0.0, 600.0, x=100.0), late])
            backend = self.backend(tmp, json.loads(
                (Path(tmp) / "out" / "calib_vod30_segments.json").read_text()))
            payload = backend.get(["api", "vod30", "events"], {})
            early, late_event = self.pixels(payload)[7], self.pixels(payload)[8]
            self.assertEqual(early[2], "early")
            self.assertEqual(late_event[2], "late")
            self.assertTrue(late_event[1].startswith("segment late"), late_event[1])
            self.assertTrue(late_event[4] and late_event[5])
            # The late event really is projected through the late quad: canonical
            # (100, 200) must land where that quad puts it.
            from src.pipeline import homography_to_canonical
            inverse = np.linalg.inv(homography_to_canonical(
                np.asarray(late["quad_px"], np.float32)))
            x, y, w = inverse @ np.array([100.0, 200.0, 1.0])
            self.assertAlmostEqual(late_event[4][0], round(float(x / w), 1), places=1)
            self.assertAlmostEqual(late_event[4][1], round(float(y / w), 1), places=1)


if __name__ == "__main__":
    unittest.main()
