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
import ast
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


class ReferenceSeamTest(unittest.TestCase):
    """The seam answers with the quad *and* the file and entry it came from.

    A reader must be able to log where its reference came from without opening a
    file again, so the provenance is checked as a value, not as a file read.
    """

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_artifact(self.root / "out", [seg("a", 0.0, 600.0),
                                          seg("b", 600.001, 1800.0, x=80.0, source="derived")])
        (self.root / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
            {"anchors": {"70.0": [[10, 10], [20, 10], [20, 20], [10, 20], [1, 1], [2, 2]]}}))
        (self.root / "out" / "fixed_corners.json").write_text(json.dumps(
            {"corners": [[100, 100], [900, 100], [900, 500], [100, 500]]}))

    def tearDown(self):
        self.tmp.cleanup()

    def reference(self, dataset="vod30", **kwargs):
        return cs.resolve(dataset, root=self.root, use_cache=False, **kwargs)

    def test_the_seam_returns_the_quad_and_the_entry_that_owns_the_time(self):
        reference = self.reference(t=1500.0)
        self.assertTrue(reference.found)
        self.assertEqual(reference.kind, "segment")
        self.assertTrue(reference.per_time, "a segment artifact is a per-time reference")
        self.assertTrue(reference.artifact.endswith("calib_vod30_segments.json"))
        self.assertEqual(reference.entry, "b")
        self.assertEqual(reference.source, "derived")
        self.assertEqual((reference.t_start, reference.t_end), (600.001, 1800.0))
        self.assertFalse(reference.clamped)
        self.assertEqual(reference.quad.tolist(), seg("b", 600.001, 1800.0, x=80.0)["quad_px"])
        logged = reference.as_dict()
        self.assertEqual((logged["artifact"], logged["entry"], logged["per_time"]),
                         (reference.artifact, "b", True))
        self.assertEqual(logged["quad_px"], reference.quad.tolist())
        json.dumps(logged)                      # a reader can log it as it stands

    def test_an_unknown_time_takes_the_entry_the_per_time_rule_names(self):
        reference = self.reference()
        self.assertEqual(reference.entry, "a", "no time takes the first segment")
        self.assertTrue(reference.clamped)
        self.assertEqual(reference.clamp_reason, "no_time")
        self.assertIn("using the first", reference.note)
        self.assertIn("2 segments", reference.note)

    def test_a_saved_reference_file_is_one_static_reference(self):
        reference = self.reference("highlight")
        self.assertTrue(reference.found)
        self.assertEqual(reference.kind, "static")
        self.assertFalse(reference.per_time)
        self.assertTrue(reference.artifact.endswith("fixed_corners.json"))
        self.assertEqual(reference.entry, "corners")
        self.assertEqual(reference.quad.tolist(), [[100.0, 100.0], [900.0, 100.0],
                                                   [900.0, 500.0], [100.0, 500.0]])

    def test_the_hand_anchors_are_named_by_their_own_time_key(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir(parents=True)
            (root / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
                {"anchors": {"70.0": [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12]]}}))
            reference = cs.resolve("vod30", 1500.0, root=root, use_cache=False)
            self.assertEqual(reference.kind, "static")
            self.assertEqual(reference.entry, "70.0", "the anchor key is the entry")
            self.assertEqual(reference.evidence, "hand anchors")
            self.assertEqual(reference.origin,
                             str(root / "out" / "pid_anchors_vod30.json"))

    def test_the_provenance_survives_the_artifact(self):
        reference = self.reference(t=10.0)
        (self.root / "out" / "calib_vod30_segments.json").unlink()
        logged = json.dumps(reference.as_dict())
        self.assertIn("calib_vod30_segments.json", logged)
        self.assertIn('"entry": "a"', logged)

    def test_the_refused_reference_is_never_selected(self):
        refused = self.root / "out" / "corners_30min_v2.json"
        refused.write_text(json.dumps({"corners": [[1, 1], [2, 1], [2, 2], [1, 2]]}))
        reference = self.reference(t=10.0, quad_file=refused)
        self.assertTrue(reference.found)
        self.assertNotIn(cs.REFUSED, reference.artifact or "")
        self.assertEqual(reference.artifact,
                         str(self.root / "out" / "calib_vod30_segments.json"))
        self.assertTrue(any("app-path-refusal.md" in line for line in reference.rejected),
                        "the refusal must be visible to the caller")
        for kind in cs.KINDS:
            self.assertNotIn(cs.REFUSED,
                             self.reference(t=10.0, kinds=(kind,)).artifact or "",
                             f"the {kind} step selected the refused reference")


class OldPathEquivalenceTest(unittest.TestCase):
    """The seam returns the array the old private loaders returned.

    The old rule is rebuilt here from the artifacts themselves: a test may read a
    file, and that is the point -- the readers no longer do.
    """

    @staticmethod
    def old_motion_scan_quad(artifact):
        """What ``motion_scan.load_quad`` returned for a segment artifact."""
        payload = json.loads(Path(artifact).read_text())
        quad = np.asarray(payload["segments"][0]["quad_px"], np.float64)
        return quad[:4].round(3).tolist()

    def test_the_real_artifact_answers_the_same_quad(self):
        if not ARTIFACT.is_file():
            self.skipTest("out/calib_vod30_segments.json not built")
        from src.motion_scan import load_quad
        quad = load_quad("vod30")
        self.assertEqual(quad["quad_px"], self.old_motion_scan_quad(ARTIFACT))
        self.assertEqual(quad["source"], str(ARTIFACT))
        self.assertTrue(quad["verified"])
        self.assertEqual(quad["rejected"], [])

    def test_a_missing_artifact_keeps_the_saved_reference(self):
        from src.motion_scan import load_quad
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            anchors = root / "out" / "pid_anchors_vod30.json"
            anchors.write_text(json.dumps(
                {"anchors": {"70.0": [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12]]}}))
            quad = load_quad("vod30", root=root)
            self.assertEqual(quad["quad_px"], [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
            self.assertEqual(quad["source"], str(anchors))
            self.assertEqual(quad["evidence"], "hand anchors")

    def test_a_quad_from_the_wrong_frame_size_is_still_refused(self):
        from src.motion_scan import load_quad
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "fixed_corners.json").write_text(json.dumps(
                {"corners": [[722, 452], [1177, 449], [1433, 844], [467, 849]]}))
            self.assertIsNotNone(load_quad("highlight", root=root,
                                           frame_size=(1920, 1080))["quad_px"])
            wrong = load_quad("highlight", root=root, frame_size=(1280, 720))
            self.assertIsNone(wrong["quad_px"])
            self.assertTrue(any("does not fit" in line for line in wrong["rejected"]))

    def test_timing_verify_reads_the_same_scan_quad(self):
        from src.timing_verify import load_quad as timing_load_quad
        path = ROOT / "out" / "scan30" / "corners.json"
        if not path.is_file():
            self.skipTest("out/scan30/corners.json is not present")
        old = np.asarray(json.loads(path.read_text())["corners"], np.float32)
        np.testing.assert_array_equal(timing_load_quad(str(path)), old)
        self.assertIsNone(timing_load_quad(None, str(path)),
                          "a corners file carries no anchors entry")

    def test_claim_calibration_projects_the_same_scan_frame(self):
        from src.eval_events import claim_calibration
        from src.pipeline import homography_to_canonical
        path = ROOT / "out" / "scan30" / "corners.json"
        if not path.is_file():
            self.skipTest("out/scan30/corners.json is not present")
        old = np.asarray(json.loads(path.read_text())["corners"], np.float32)
        inverse, label = claim_calibration(str(path))
        np.testing.assert_allclose(inverse, np.linalg.inv(homography_to_canonical(old)))
        self.assertEqual(label, f"scan claim frame ({path})")

    def test_reference_calibration_keeps_the_hand_anchor_mapping(self):
        from src.eval_events import reference_calibration
        from src.pipeline import homography_to_canonical
        anchors = ROOT / "out" / "pid_anchors_vod30.json"
        scan = ROOT / "out" / "scan30" / "corners.json"
        if not (anchors.is_file() and scan.is_file()):
            self.skipTest("the vod30 anchors or the scan quad are not present")
        first = next(iter(json.loads(anchors.read_text())["anchors"].values()))
        old = np.asarray(first[:4], np.float32)
        forward, inverse, label = reference_calibration(str(anchors), str(scan))
        np.testing.assert_allclose(forward, homography_to_canonical(old))
        self.assertEqual(label, "hand anchors on the cloth")

    def test_the_mapping_audit_keeps_its_old_quad_pair(self):
        from src.calib_mapping_audit import load_mappings
        from src.table_detect import _order_corners
        anchors = ROOT / "out" / "pid_anchors_vod30.json"
        scan = ROOT / "out" / "scan30" / "corners.json"
        if not (anchors.is_file() and scan.is_file()):
            self.skipTest("the vod30 anchors or the scan quad are not present")
        first = next(iter(json.loads(anchors.read_text())["anchors"].values()))
        old_a = _order_corners(np.asarray(first[:4], np.float32))
        old_b = np.asarray(json.loads(scan.read_text())["corners"], np.float32)
        _ha, _hb, quad_a, quad_b, pockets = load_mappings()
        np.testing.assert_array_equal(quad_a, old_a)
        np.testing.assert_array_equal(quad_b, old_b)
        self.assertEqual(len(pockets), 2, "the six anchors carry two pocket points")


class ReaderUsesTheSeamTest(unittest.TestCase):
    """Every reader gets its quad from the seam, not from a loader of its own."""

    QUAD = np.array([[100.0, 100.0], [900.0, 110.0], [910.0, 500.0], [90.0, 490.0]],
                    np.float32)

    def test_motion_scan_takes_its_quad_from_the_seam(self):
        from src import calib_segments, motion_scan
        sentinel = calib_segments.Reference(quad=self.QUAD, kind="segment",
                                            origin="sentinel", artifact="sentinel.json",
                                            entry="s1", per_time=True,
                                            note="from the seam", evidence="test")
        seen = {}
        original = calib_segments.resolve

        def fake_resolve(dataset="vod30", t=None, **kwargs):
            seen.update({"dataset": dataset, "t": t}, **kwargs)
            return sentinel

        calib_segments.resolve = fake_resolve
        try:
            quad = motion_scan.load_quad("vod30", root=Path("."), frame_size=(1280, 720), t=5.0)
        finally:
            calib_segments.resolve = original
        self.assertEqual(quad["quad_px"], self.QUAD.tolist())
        self.assertEqual(quad["source"], "sentinel")
        self.assertEqual(quad["note"], "from the seam")
        self.assertTrue(quad["verified"])
        self.assertEqual(seen["dataset"], "vod30")
        self.assertEqual(seen["t"], 5.0)
        self.assertEqual(seen["frame_size"], (1280, 720))

    def test_claim_calibration_takes_its_quad_from_the_seam(self):
        from src import calib_segments
        from src.eval_events import claim_calibration
        from src.pipeline import homography_to_canonical
        seen = {}
        original = calib_segments.read

        def fake_read(path, key=None, **kwargs):
            seen.update({"path": path, "key": key}, **kwargs)
            return calib_segments.Reference(quad=self.QUAD, kind="static", artifact=str(path),
                                            entry=key, origin=str(path))

        calib_segments.read = fake_read
        try:
            inverse, label = claim_calibration("out/scan30/corners.json")
        finally:
            calib_segments.read = original
        self.assertEqual((seen["path"], seen["key"]), ("out/scan30/corners.json", "corners"))
        np.testing.assert_allclose(inverse, np.linalg.inv(homography_to_canonical(self.QUAD)))
        self.assertEqual(label, "scan claim frame (out/scan30/corners.json)")


class NoPrivateLoaderTest(unittest.TestCase):
    """No reader parses a calibration artifact; the source text says so.

    The AST check is the durable half of the seam: a later edit that puts a
    ``json.loads`` back into one of these functions fails here, whatever the
    artifacts on disk happen to hold.
    """

    #: (module, functions that answer "which quad") -- each must call the seam.
    READERS = {
        "src/motion_scan.py": ("load_quad",),
        "src/timing_verify.py": ("load_quad",),
        "src/eval_events.py": ("reference_calibration", "claim_calibration"),
        "src/calib_mapping_audit.py": ("load_mappings", "highlight_reference_check"),
        "src/calib_segment_measure.py": ("anchors_quad", "scan_quad"),
        "src/sam3_frame_audit.py": ("reference_quad",),
        "src/sam3_ball_cache.py": ("reference_quad",),
    }
    #: loaders that rebuilt the chain and must stay deleted.
    GONE = {
        "src/eval_events.py": ("load_quad", "load_segments"),
        "src/calib_mapping_audit.py": ("_load_anchors",),
    }

    @staticmethod
    def functions(path):
        tree = ast.parse((ROOT / path).read_text())
        return {node.name: node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)}

    def test_every_reader_asks_the_seam_and_reads_no_file(self):
        for path, names in self.READERS.items():
            defined = self.functions(path)
            for name in names:
                self.assertIn(name, defined, f"{path}: {name} must stay")
                calls = [ast.unparse(node.func) for node in ast.walk(defined[name])
                         if isinstance(node, ast.Call)]
                self.assertTrue([call for call in calls
                                 if call.startswith("calib_segments.")],
                                f"{path}.{name} no longer calls the seam")
                for banned in ("json.loads", "read_text"):
                    self.assertFalse([call for call in calls if call.endswith(banned)],
                                     f"{path}.{name} parses a file itself: {banned}")

    def test_the_private_loaders_stay_deleted(self):
        for path, names in self.GONE.items():
            defined = self.functions(path)
            for name in names:
                self.assertNotIn(name, defined, f"{path}.{name} must not come back")

    def test_the_report_build_names_the_artifact_once(self):
        build = self.functions("src/segment_calib_report.py")["build"]
        text = ast.unparse(build)
        self.assertIn("calib_segments.resolve", text)
        self.assertNotIn('["segments"]', text, "the payload layout stays in the seam")
        loads = [node for node in ast.walk(build) if isinstance(node, ast.Call)
                 and ast.unparse(node.func).endswith("json.loads")]
        for node in loads:
            self.assertNotIn("args.artifact", ast.unparse(node),
                             "the artifact is read once, by the seam")


if __name__ == "__main__":
    unittest.main()
