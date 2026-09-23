"""Timing invariants for the served event timestamps.

The owner's report was "none of the event time stamps actually have any of the
ball movement detected".  Before anything else that claim needed the *time*
axis measured, and these tests pin the invariants that measurement established,
so a later change cannot quietly break them:

1. **One timebase, not two.**  ``src/timing_verify.cross_check`` decodes the
   still at ``frame_index = round(t * fps)`` (the app's frame path) and, in a
   fresh ``cv2.VideoCapture``, seeks to container time ``t`` (what
   ``video.currentTime`` does), then compares the pictures.  On this VOD they
   are the *same frame* at 60/300/900/1700 s, so the nominal
   ``frame_index / fps`` contract in ``docs/unified-workbench.md`` is exact
   here and the clip we show is the moment the detector measured.
2. **The measured window is the shown window.**  ``annotator/app.js`` seeks the
   stage to ``t - CLIP_BEFORE_S`` and runs to ``t + CLIP_AFTER_S``; the tool
   measures exactly that window, so the two constant pairs must agree.
3. **The nominal convention is used in both producers.**  ``candidate_scan``
   stamps ``t = index / fps`` and the review server derives
   ``timestamp_seconds = frame_index / fps``; if either switched to PTS the
   first invariant would stop holding silently.
4. **The floor is a still floor.**  ``control_floor`` reads the low quantile of
   each control window's pairs, never a window peak: this VOD is a busy room and
   a control peak is usually a person crossing the cloth, which would raise the
   threshold until every real change was "no motion".
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import timing_verify as tv  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "data" / "vod_30min_260815.mp4"
APP_JS = ROOT / "annotator" / "app.js"
SCAN = ROOT / "src" / "candidate_scan.py"
SERVER = ROOT / "annotator" / "unified_server.py"


def synthetic_window(diffs, changed=None):
    """A profile with the given per-pair mean differences, ball-scale extras."""
    pairs = []
    for index, diff in enumerate(diffs):
        pairs.append(dict(t_from=float(index), t_to=index + 0.2, index_from=index, index_to=index + 1,
                          dt=0.2, diff=diff, maxdiff=diff * 4.0, balls=1,
                          occlusion=0.0, changed_frac=(changed or [0.001] * len(diffs))[index],
                          p99=diff * 2.0, flow=diff / 10.0))
    winner = int(np.argmax(diffs))
    return dict(pairs=pairs, peak=float(diffs[winner]), peak_at=float(winner),
                median=float(np.median(diffs)))


class SsimTests(unittest.TestCase):
    def test_identical_images_score_one(self):
        image = (np.arange(64 * 64) % 251).astype(np.uint8).reshape(64, 64)
        self.assertAlmostEqual(tv.ssim(image, image), 1.0, places=9)

    def test_different_images_score_lower(self):
        first = np.zeros((64, 64), np.uint8)
        second = np.full((64, 64), 200, np.uint8)
        self.assertLess(tv.ssim(first, second), 0.5)


class ControlFloorTests(unittest.TestCase):
    """The floor must be a still-cloth quantile, not a control window's peak."""

    def test_floor_ignores_a_busy_control_peak(self):
        rows = [dict(still_floor=0.5, peak=60.0),   # a person crossed this control
                dict(still_floor=0.4, peak=1.2),
                dict(still_floor=0.6, peak=1.4)]
        self.assertLess(tv.control_floor(rows), 1.0)

    def test_empty_controls_have_no_floor(self):
        self.assertIsNone(tv.control_floor([]))


class ClassifyTests(unittest.TestCase):
    """The three-way verdict, plus the ball-scale read with its own floor."""

    def test_motion_at_the_served_time(self):
        profile = synthetic_window([0.5, 0.6, 9.0, 0.7, 0.5])
        verdict, offset = tv.classify_event(profile, 2.4, floor=0.5)
        self.assertEqual(verdict, "motion at the served time")
        self.assertAlmostEqual(offset, 2.0 - 2.4, places=6)

    def test_motion_elsewhere_reports_its_offset(self):
        profile = synthetic_window([9.0, 0.5, 0.6, 0.6, 0.6])
        verdict, offset = tv.classify_event(profile, 3.0, floor=0.5)
        self.assertEqual(verdict, "motion elsewhere in window")
        self.assertAlmostEqual(offset, -3.0, places=6)

    def test_a_still_window_has_no_motion(self):
        profile = synthetic_window([0.4, 0.5, 0.6, 0.5, 0.4])
        verdict, offset = tv.classify_event(profile, 2.0, floor=0.5)
        self.assertEqual(verdict, "no motion anywhere in window")
        self.assertIsNone(offset)

    def test_a_person_sized_footprint_is_not_read_as_ball_scale(self):
        """The pair that carries 54-77 % of the cloth must be excluded."""
        profile = synthetic_window([1.0, 1.0, 42.0, 1.0], changed=[0.01, 0.02, 0.54, 0.01])
        profile["pairs"][2]["maxdiff"] = 190.0
        split = tv.footprint_split(profile)
        self.assertNotEqual(split["ball_scale_at"], 2.0)
        self.assertLessEqual(split["ball_scale_change"], tv.BALL_FOOTPRINT_MAX)

    def test_a_noisy_control_floor_yields_not_separable_not_a_false_negative(self):
        """Still windows on this VOD reach ~167 levels; that is not evidence of no ball."""
        profile = synthetic_window([1.0, 1.0], changed=[0.01, 0.01])
        for pair in profile["pairs"]:
            pair["maxdiff"] = 120.0
        tv.apply_footprint(profile, 0.0, floor=166.5)
        self.assertEqual(profile["ball_scale_verdict"], "ball-scale signal not separable from controls")
        self.assertGreater(profile["ball_scale_threshold"], 120.0)

    def test_a_low_control_floor_can_still_say_no_ball_scale_motion(self):
        profile = synthetic_window([1.0, 1.0], changed=[0.01, 0.01])
        for pair in profile["pairs"]:
            pair["maxdiff"] = 40.0
        tv.apply_footprint(profile, 0.0, floor=10.0)
        self.assertEqual(profile["ball_scale_verdict"], "no ball-scale motion in window")

    def test_ball_scale_verdict_fires_above_the_floor(self):
        profile = synthetic_window([1.0, 1.0], changed=[0.01, 0.01])
        for pair in profile["pairs"]:
            pair["maxdiff"] = 240.0
        tv.apply_footprint(profile, 0.0, floor=10.0)
        self.assertEqual(profile["ball_scale_verdict"], "ball-scale motion at the served time")


class FootprintTests(unittest.TestCase):
    def test_ball_is_small_next_to_the_cloth(self):
        """A 57 mm ball on a 2540 mm table is ~2 % of the cloth at most."""
        self.assertLessEqual(tv.BALL_FOOTPRINT_MAX, 0.02)


class ConstantParityTests(unittest.TestCase):
    """The measured window must be the window the stage plays."""

    def test_app_js_clip_constants_match_the_tool(self):
        self.assertTrue(APP_JS.exists(), APP_JS)
        source = APP_JS.read_text()
        self.assertIn(f"const CLIP_BEFORE_S = {tv.CLIP_BEFORE_S}", source)
        self.assertIn(f"CLIP_AFTER_S = {tv.CLIP_AFTER_S}", source)

    def test_app_js_seeks_the_stage_by_container_time(self):
        source = APP_JS.read_text()
        self.assertIn("video.currentTime = playback.from", source)
        self.assertIn("const from = Math.max(0, at - CLIP_BEFORE_S)", source)

    def test_scan_stamps_nominal_time_from_the_frame_index(self):
        source = SCAN.read_text()
        self.assertIn("t = index / fps", source)
        self.assertIn("cap.get(cv2.CAP_PROP_FPS)", source)

    def test_server_derives_timestamp_seconds_from_the_frame_index(self):
        source = SERVER.read_text()
        self.assertIn("timestamp_seconds=value/meta['fps']", source)
        self.assertIn("cap.set(cv2.CAP_PROP_POS_FRAMES", source)


class RecordsMotionTests(unittest.TestCase):
    """The scan's own trigger signal is read, and its offset is not smoothed."""

    def test_offsets_are_reported_against_the_event_time(self):
        import json
        import tempfile
        records = [{"t": 1.0, "motion": 1.0}, {"t": 2.0, "motion": 9.0}, {"t": 3.0, "motion": 2.0}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.json"
            path.write_text(json.dumps(records))
            report = tv.records_motion_check(path, [dict(t=2.5), dict(t=50.0)], reach_s=5.0)
        self.assertEqual(report["step_s"], 1.0)
        near = report["events"][0]
        self.assertEqual(near["nearest_t"], 2.0)
        self.assertAlmostEqual(near["nearest_offset_s"], -0.5, places=6)
        self.assertEqual(near["peak_t"], 2.0)
        self.assertTrue(near["all_below_nearest"])
        self.assertFalse(report["events"][1]["in_reach"])

    def test_a_missing_records_file_is_not_an_error(self):
        self.assertIsNone(tv.records_motion_check(ROOT / "out" / "no-such-records.json", []))


class LiveVideoTimingTests(unittest.TestCase):
    """The invariant itself, on the VOD: nominal time and container time agree."""

    @classmethod
    def setUpClass(cls):
        if not VIDEO.exists():
            raise unittest.SkipTest("vod_30min_260815.mp4 is not present")
        import cv2
        cap = cv2.VideoCapture(str(VIDEO))
        try:
            cls.fps, cls.frame_count, cls.duration = tv.video_meta(cap)
        finally:
            cap.release()

    def test_frame_index_seek_and_time_seek_land_on_the_same_frame(self):
        report = tv.cross_check(VIDEO, [60.0, 300.0, 900.0], self.fps)
        self.assertTrue(report["all_identical"],
                        [(r["t"], r["frames_apart"], r["ssim"]) for r in report["rows"]])
        self.assertEqual(report["max_abs_frames_apart"], 0)
        self.assertLess(report["max_abs_drift_s"], 0.005)

    def test_nominal_time_does_not_drift_across_the_file(self):
        drift = tv.drift_scan(VIDEO, step_s=300.0, fps=self.fps)
        self.assertLess(abs(drift["max_abs_drift_s"]), 0.005)
        self.assertLess(abs(drift["last_drift_s"]), 0.005)

    def test_the_window_start_is_the_frame_the_app_shows(self):
        """``t - CLIP_BEFORE_S`` is what the stage seeks to; the frame path must agree."""
        report = tv.cross_check(VIDEO, [82.5 - tv.CLIP_BEFORE_S, 998.1 - tv.CLIP_BEFORE_S], self.fps)
        self.assertTrue(report["all_identical"],
                        [(r["t"], r["frames_apart"], r["ssim"]) for r in report["rows"]])

    def test_sample_window_decodes_the_requested_frame_indexes(self):
        cap = tv.open_video(VIDEO)
        try:
            samples = tv.sample_window(cap, 82.5, self.fps)
        finally:
            cap.release()
        self.assertEqual(len(samples), 21)               # 4 s at 5 fps, inclusive
        self.assertEqual(samples[0][1], int(round((82.5 - tv.CLIP_BEFORE_S) * self.fps)))
        self.assertEqual(samples[-1][1], int(round((82.5 + tv.CLIP_AFTER_S) * self.fps)))
        self.assertAlmostEqual(samples[1][0] - samples[0][0], 0.2, places=3)


if __name__ == "__main__":
    unittest.main()
