"""motion_scan contract: two channels, a calibrated floor, and an onset detector.

No VOD is needed for the signal and detector tests -- they build synthetic frames
and synthetic series, so the contract (a ball-sized change raises the ball channel
while a body-sized change raises the occlusion channel, the threshold is above
every control frame, onsets separate at min_gap_s) is pinned without a 690 MB
recording on disk.  The one video test writes a tiny synthetic clip to a temp dir
and is skipped if this OpenCV build cannot write it.
"""
import json
import math
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

import data_guard

from src.motion_scan import (BALL_K_NATIVE, FLOOR_MARGIN, SCAN_H, SCAN_W, WORK_H, WORK_W,
                             ClothContext, MotionConfig, OnsetConfig, ScanReport,
                             ball_area, ball_radius, clip_motion, cloth_context,
                             cloth_mask, config_for, decay_shape, detect_onsets,
                             channel_planes, enforce_gap, freeze, load_quad, load_scan,
                             moving_ball_instances, noise_floor, onset_signal,
                             probe_pair, rolling_baseline, sample_window, save_scan,
                             series_fields, window_bounds, window_profile)

ROOT = Path(__file__).resolve().parent.parent

# A quad whose four rails sit well inside the frame, so a change placed outside it
# is farther than one ball footprint from every cloth pixel.
QUAD = [[320.0, 240.0], [960.0, 240.0], [960.0, 560.0], [320.0, 560.0]]


def frames(delta=None, rect=None, level=0, size=(SCAN_W, SCAN_H)) -> tuple:
    """A (native, work) grayscale pair, with an optional bright rectangle added to
    the *second* frame.  ``rect`` is in native pixels as ``(x, y, w, h)``."""
    native = np.full((size[1], size[0]), 40, np.uint8)
    work = cv2.cvtColor(cv2.resize(cv2.cvtColor(native, cv2.COLOR_GRAY2BGR),
                                   (WORK_W, WORK_H)), cv2.COLOR_BGR2GRAY)
    if rect is not None:
        x, y, w, h = rect
        native = native.copy()
        native[y:y + h, x:x + w] = np.uint8(min(255, 40 + (delta or 150)))
        work = cv2.cvtColor(cv2.resize(cv2.cvtColor(native, cv2.COLOR_GRAY2BGR),
                                       (WORK_W, WORK_H)), cv2.COLOR_BGR2GRAY)
    return native, work


def flat_native():
    return np.full((SCAN_H, SCAN_W), 40, np.uint8), np.full((WORK_H, WORK_W), 40, np.uint8)


class ClothGeometryTest(unittest.TestCase):
    def test_mask_area_matches_polygon_area(self):
        mask = cloth_mask(QUAD, WORK_W, WORK_H)
        poly = (np.asarray(QUAD, np.float64) *
                np.array([WORK_W / SCAN_W, WORK_H / SCAN_H])).astype(np.int32)
        area = float(cv2.contourArea(poly))
        # fillConvexPoly has no antialiasing, so the rasterised mask differs from the
        # exact polygon by its perimeter: bound it at 1 % and at the perimeter itself
        perimeter = float(cv2.arcLength(poly.reshape(-1, 1, 2), True))
        self.assertLess(abs(float(mask.sum()) - area), max(0.01 * area, perimeter))
        self.assertGreater(float(mask.sum()), 0.9 * area)

    def test_cloth_pixels_are_inside_the_quad(self):
        ctx = cloth_context(QUAD)
        ys, xs = np.divmod(ctx.idx, WORK_W)
        for x, y in zip(xs, ys):
            self.assertTrue(0 <= x < WORK_W and 0 <= y < WORK_H)
        # the mask never includes a pixel outside the quad's bounding box
        x0, y0, x1, y1 = ctx.bbox
        self.assertTrue((xs >= x0).all() and (xs <= x1).all())
        self.assertTrue((ys >= y0).all() and (ys <= y1).all())

    def test_quad_scales_to_the_working_resolution(self):
        ctx = cloth_context(QUAD)
        # 0.75 x 0.75 of the native area, within the polygon's own discretisation
        self.assertAlmostEqual(ctx.n_pixels / ctx.n_pixels_native, 0.5625, delta=0.01)

    def test_context_is_a_dataclass_with_the_grid(self):
        ctx = cloth_context(QUAD)
        self.assertIsInstance(ctx, ClothContext)
        self.assertEqual(ctx.n_cells, ctx.grid_rows * ctx.grid_cols)
        self.assertEqual(int(ctx.cell_counts.sum()), ctx.n_pixels)


class ClothRestrictedSignalTest(unittest.TestCase):
    """The signal must measure the cloth and nothing else."""

    def setUp(self):
        self.ctx = cloth_context(QUAD)
        self.cfg = MotionConfig()

    def test_motion_outside_the_quad_is_invisible(self):
        prev_native, prev_work = flat_native()
        native, work = frames(rect=(40, 40, 200, 200), level=150)   # far outside
        m = clip_motion(prev_native, native, prev_work, work, self.ctx, self.cfg)
        self.assertEqual(m["occ_share"], 0.0)
        self.assertEqual(m["occ_dense"], 0.0)
        self.assertEqual(m["ball17"], 0.0)
        self.assertEqual(m["ball13w"], 0.0)

    def test_motion_inside_the_quad_is_visible(self):
        prev_native, prev_work = flat_native()
        native, work = frames(rect=(620, 380, 40, 40), level=150)   # inside
        m = clip_motion(prev_native, native, prev_work, work, self.ctx, self.cfg)
        self.assertGreater(m["ball17"], 40.0)
        self.assertGreater(m["occ_share"], 0.0)

    def test_no_change_gives_no_signal(self):
        prev_native, prev_work = flat_native()
        m = clip_motion(prev_native, prev_native, prev_work, prev_work, self.ctx, self.cfg)
        self.assertEqual(m["ball17"], 0.0)
        self.assertEqual(m["mean"], 0.0)
        self.assertEqual(m["occ_share"], 0.0)
        self.assertEqual(m["cell"], -1)

    def test_the_occlusion_channels_ignore_everything_outside_the_quad(self):
        """occ_share and occ_dense are cloth-restricted by construction, so a change
        just outside the rail (where the box filter would otherwise straddle it) is
        not counted."""
        prev_native, prev_work = flat_native()
        native, work = frames(rect=(400, 564, 260, 40), level=150)  # 4 px below the rail
        m = clip_motion(prev_native, native, prev_work, work, self.ctx, self.cfg)
        self.assertEqual(m["occ_share"], 0.0)
        self.assertEqual(m["occ_dense"], 0.0)

    def test_the_ball_channel_has_a_half_footprint_halo_outside_the_rail(self):
        """Documented property, not a bug: a box filter whose centre is on the cloth
        reaches k/2 outside it, exactly as a ball half off the rail would."""
        prev_native, prev_work = flat_native()
        near_native, near_work = frames(rect=(400, 564, 200, 20), level=150)
        near = clip_motion(prev_native, near_native, prev_work, near_work,
                           self.ctx, self.cfg)
        self.assertGreater(near["ball17"], 0.0)
        far_native, far_work = frames(rect=(400, 620, 200, 20), level=150)  # > k/2 away
        far = clip_motion(prev_native, far_native, prev_work, far_work,
                          self.ctx, self.cfg)
        self.assertEqual(far["ball17"], 0.0)


class BallVersusOcclusionTest(unittest.TestCase):
    """The two channels must have different jobs."""

    def setUp(self):
        self.ctx = cloth_context(QUAD)
        self.cfg = MotionConfig()
        self.prev_native, self.prev_work = flat_native()

    def test_a_ball_sized_change_raises_ball17_without_occlusion(self):
        side = int(round(math.sqrt(math.pi) * 9.45))      # equivalent-area square
        native, work = frames(rect=(620, 380, side, side), level=150)
        m = clip_motion(self.prev_native, native, self.prev_work, work, self.ctx, self.cfg)
        self.assertGreater(m["ball17"], 60.0)
        self.assertLess(m["occ_dense"], 0.10)
        self.assertLess(m["occ_share"], 0.02)

    def test_a_body_sized_change_raises_occlusion_not_a_ball(self):
        native, work = frames(rect=(380, 260, 200, 120), level=150)
        m = clip_motion(self.prev_native, native, self.prev_work, work, self.ctx, self.cfg)
        self.assertGreater(m["occ_dense"], 0.9)
        self.assertGreater(m["occ_share"], 0.05)

    def test_a_ball_footprint_beats_the_same_change_spread_thin(self):
        """A ball change and a wide thin change can carry the same total energy; the
        footprint mean separates them, which is why the detector uses it."""
        native, work = frames(rect=(620, 380, 19, 19), level=150)
        ball = clip_motion(self.prev_native, native, self.prev_work, work,
                           self.ctx, self.cfg)
        native2, work2 = frames(rect=(410, 265, 400, 3), level=150)   # a thin streak
        streak = clip_motion(self.prev_native, native2, self.prev_work, work2,
                             self.ctx, self.cfg)
        self.assertGreater(ball["ball17"], streak["ball17"])

    def test_footprints_agree_on_a_full_cover_and_scale_down_when_diluted(self):
        native, work = frames(rect=(600, 360, 30, 30), level=150)
        m = clip_motion(self.prev_native, native, self.prev_work, work, self.ctx, self.cfg)
        self.assertGreaterEqual(m["ball9"], m["ball25"])
        self.assertGreater(m["ball25"], 20.0)


class RollingBaselineTest(unittest.TestCase):
    def test_tracks_a_step_and_ignores_a_spike(self):
        v = np.full(3000, 5.0)
        v[1500:] = 40.0
        v[1000] = 900.0                       # an outlier must not move a median
        base = rolling_baseline(v, dt=1 / 30.0, window_s=20.0, block_s=5.0)
        self.assertAlmostEqual(float(base[100]), 5.0, delta=0.5)
        self.assertGreater(float(base[-1]), 30.0)

    def test_empty_and_short_inputs_do_not_crash(self):
        self.assertEqual(rolling_baseline(np.zeros(0), 1 / 30.0, 20.0, 5.0).size, 0)
        short = rolling_baseline(np.array([1.0, 2.0, 3.0]), 1 / 30.0, 20.0, 5.0)
        self.assertEqual(short.size, 3)


class OnsetDetectorTest(unittest.TestCase):
    """Synthetic rise/fall, noise floor, gap separation, merge."""

    @staticmethod
    def series(values, dt=1 / 30.0):
        values = np.asarray(values, np.float64)
        return np.arange(values.size) * dt, values

    def test_a_rise_above_the_threshold_is_one_onset_at_the_rise(self):
        v = np.full(300, 1.0)
        v[120:135] = 50.0
        t, v = self.series(v)
        out = detect_onsets(t, v, OnsetConfig(threshold=10.0))
        self.assertEqual(len(out["onsets"]), 1)
        onset = out["onsets"][0]
        self.assertEqual(onset["frame"], 120)
        self.assertAlmostEqual(onset["t_onset"], 120 / 30.0, places=3)
        self.assertAlmostEqual(onset["peak"], 50.0, places=3)
        self.assertEqual(onset["n_frames"], 15)

    def test_a_rise_and_fall_inside_the_threshold_is_not_an_onset(self):
        v = np.full(300, 1.0)
        v[120:140] = 9.9
        t, v = self.series(v)
        self.assertEqual(detect_onsets(t, v, OnsetConfig(threshold=10.0))["onsets"], [])

    def test_noise_below_the_threshold_yields_no_onsets(self):
        rng = np.random.default_rng(7)
        v = 1.0 + rng.normal(0.0, 2.0, 4000)
        t, v = self.series(v)
        self.assertEqual(detect_onsets(t, v, OnsetConfig(threshold=10.0))["onsets"], [])

    def test_noise_above_a_too_low_threshold_is_caught_by_the_threshold(self):
        rng = np.random.default_rng(7)
        v = 1.0 + rng.normal(0.0, 2.0, 4000)
        t, v = self.series(v)
        loose = detect_onsets(t, v, OnsetConfig(threshold=1.0, merge_s=0.0, min_gap_s=0.0))
        self.assertGreater(len(loose["onsets"]), 100)

    def test_two_events_further_apart_than_min_gap_stay_two(self):
        v = np.full(600, 1.0)
        v[100:105] = 50.0
        v[300:305] = 40.0
        t, v = self.series(v)
        out = detect_onsets(t, v, OnsetConfig(threshold=10.0, min_gap_s=1.0))
        self.assertEqual([o["frame"] for o in out["onsets"]], [100, 300])

    def test_two_events_closer_than_min_gap_collapse_to_the_stronger_peak(self):
        v = np.full(600, 1.0)
        v[100:103] = 50.0
        v[112:115] = 40.0              # 12 frames = 0.4 s later
        t, v = self.series(v)
        out = detect_onsets(t, v, OnsetConfig(threshold=10.0, min_gap_s=1.0))
        self.assertEqual(len(out["onsets"]), 1)
        self.assertEqual(out["onsets"][0]["frame"], 100)

    def test_a_dip_shorter_than_merge_keeps_one_event(self):
        v = np.full(600, 1.0)
        v[100:110] = 50.0
        v[110] = 0.0                   # 1 frame = 0.033 s below threshold
        v[111:121] = 45.0
        t, v = self.series(v)
        out = detect_onsets(t, v, OnsetConfig(threshold=10.0, merge_s=0.25, min_gap_s=1.0))
        self.assertEqual(len(out["onsets"]), 1)
        self.assertEqual(out["onsets"][0]["frame"], 100)

    def test_a_dip_longer_than_merge_splits_the_event(self):
        v = np.full(600, 1.0)
        v[100:110] = 50.0
        v[110:130] = 0.0               # 20 frames = 0.67 s below threshold
        v[130:140] = 45.0
        t, v = self.series(v)
        out = detect_onsets(t, v, OnsetConfig(threshold=10.0, merge_s=0.25, min_gap_s=1.0))
        self.assertEqual([o["frame"] for o in out["onsets"]], [100, 130])

    def test_the_reported_threshold_is_the_one_used(self):
        v = np.full(200, 1.0)
        v[50:60] = 30.0
        t, v = self.series(v)
        out = detect_onsets(t, v, OnsetConfig(threshold=20.0))
        self.assertEqual(out["threshold"], 20.0)
        self.assertEqual(out["onsets"][0]["threshold"], 20.0)
        self.assertAlmostEqual(out["onsets"][0]["excess_ratio"], 1.5, places=3)

    def test_empty_series_is_not_an_error(self):
        out = detect_onsets(np.zeros(0), np.zeros(0), OnsetConfig(threshold=5.0))
        self.assertEqual(out["onsets"], [])
        self.assertEqual(out["n"], 0)

    def test_enforce_gap_keeps_the_strongest_of_a_close_pair(self):
        rows = [{"t_peak": 1.0, "peak": 5.0}, {"t_peak": 1.4, "peak": 9.0},
                {"t_peak": 5.0, "peak": 2.0}]
        kept = enforce_gap(rows, 1.0)
        self.assertEqual([r["t_peak"] for r in kept], [1.4, 5.0])


class FloorCalibrationTest(unittest.TestCase):
    """The threshold is derived from the controls, and no control frame may fire."""

    def setUp(self):
        self.t = np.arange(0, 100, 1 / 30.0)
        self.v = np.full(self.t.size, 3.0)
        self.v[self.t > 50] = 6.0

    def test_overlapping_control_times_merge_into_one_window(self):
        windows = window_bounds([10.0, 11.0, 40.0], half_s=2.5)
        self.assertEqual(windows, [[7.5, 13.5], [37.5, 42.5]])

    def test_the_floor_reports_a_distribution_not_a_single_number(self):
        floor = noise_floor(self.t, self.v, [10.0, 60.0], half_s=2.5)
        for key in ("median", "p90", "p99", "max", "threshold", "n"):
            self.assertIn(key, floor)
        self.assertGreater(floor["n"], 100)

    def test_the_threshold_sits_above_every_control_frame(self):
        floor = noise_floor(self.t, self.v, [10.0, 60.0], half_s=2.5)
        self.assertAlmostEqual(floor["threshold"], floor["max"] * FLOOR_MARGIN, places=4)
        # and it is a real bar, not one the controls themselves cross
        self.assertGreater(floor["threshold"], floor["max"])

    def test_a_control_window_with_a_real_event_raises_the_floor(self):
        quiet = noise_floor(self.t, self.v, [10.0], half_s=2.5)
        busy_v = self.v.copy()
        busy_v[(self.t > 60) & (self.t <= 62)] = 80.0
        busy = noise_floor(self.t, busy_v, [60.0], half_s=2.5)
        self.assertGreater(busy["max"], quiet["max"])

    def test_no_onsets_inside_the_controls_at_the_calibrated_threshold(self):
        floor = noise_floor(self.t, self.v, [10.0, 60.0], half_s=2.5)
        out = detect_onsets(self.t, self.v, OnsetConfig(threshold=floor["threshold"]))
        for onset in out["onsets"]:
            inside = any(start <= onset["t_peak"] <= end
                         for start, end in floor["times"])
            self.assertFalse(inside, f"onset {onset} fired inside a control window")


class BlobShapeTest(unittest.TestCase):
    """The size cross-check on the occlusion-density channel."""

    def _blob(self, rect, level=150):
        import tempfile

        from src.motion_scan import blob_shape
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "clip.avi")
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 30.0,
                                     (SCAN_W, SCAN_H))
            if not writer.isOpened():
                self.skipTest("this OpenCV build cannot write MJPG avi")
            for i in range(3):
                frame = np.full((SCAN_H, SCAN_W, 3), 60, np.uint8)
                if i == 2:
                    x, y, w, h = rect
                    frame[y:y + h, x:x + w] = np.uint8(60 + level)
                writer.write(frame)
            writer.release()
            return blob_shape(path, 2, cloth_context(QUAD))

    def test_a_ball_sized_change_is_one_ball(self):
        side = int(round(math.sqrt(math.pi) * 9.45))
        info = self._blob((620, 380, side, side))
        self.assertLessEqual(info["largest_area"], 532)
        self.assertIn("can be a single ball", info["verdict"])

    def test_a_limb_sized_change_is_not_one_ball(self):
        info = self._blob((880, 400, 28, 101))     # the shape measured on this VOD
        self.assertGreater(info["largest_area"], 532)
        self.assertNotIn("can be a single ball", info["verdict"])
        self.assertGreater(info["aspect"], 2.0)

    def test_nothing_changed_is_reported_as_such(self):
        info = self._blob((0, 0, 0, 0))
        self.assertEqual(info["largest_area"], 0)
        self.assertIn("nothing changed", info["verdict"])


class WindowProfileTest(unittest.TestCase):
    def setUp(self):
        self.t = np.arange(0, 30, 1 / 30.0)
        self.v = np.full(self.t.size, 2.0)

    def test_peak_at_t_is_reported_at_t(self):
        self.v[np.abs(self.t - 10.0) < 0.2] = 90.0
        profile = window_profile(self.t, self.v, 10.0, floor=20.0)
        self.assertTrue(profile["verdict"].startswith("ball-scale motion at t"))
        self.assertLessEqual(abs(profile["peak_offset_s"]), 0.5)

    def test_peak_elsewhere_reports_the_offset(self):
        self.v[360:362] = 90.0        # frames 360-361 == t 12.00-12.03 s
        profile = window_profile(self.t, self.v, 10.0, floor=20.0)
        self.assertTrue(profile["verdict"].startswith("only elsewhere"))
        self.assertAlmostEqual(profile["peak_offset_s"], 2.0, delta=0.15)

    def test_nothing_above_the_floor_is_not_separable(self):
        profile = window_profile(self.t, self.v, 10.0, floor=20.0)
        self.assertEqual(profile["verdict"], "none separable from floor")

    def test_the_window_is_sampled_at_the_stated_rate(self):
        profile = window_profile(self.t, self.v, 10.0, floor=1.0, sample_hz=10.0)
        self.assertEqual(profile["n"], 41)                 # [-1.5, +2.5] at 10 Hz
        samples = sample_window(self.t, self.v, 10.0, 1.5, 2.5, 10.0)
        self.assertAlmostEqual(samples["times"][0], 8.5, places=3)
        self.assertAlmostEqual(samples["times"][-1], 12.5, places=3)


class DecayShapeTest(unittest.TestCase):
    """Physics is reported as a hypothesis, never baked into the signal."""

    def setUp(self):
        self.t = np.arange(0, 4, 1 / 30.0)

    def test_a_monotone_decay_reads_as_a_rolling_ball(self):
        v = 100.0 * np.exp(-3.0 * self.t)
        shape = decay_shape(self.t, v, 0.0, window_s=1.5)
        self.assertIn("consistent with a rolling ball", shape["verdict"])
        self.assertIsNotNone(shape["half_peak_after_s"])
        self.assertIsNotNone(shape["active_s"])

    def test_a_few_frame_spike_is_not_a_rolling_ball(self):
        """A struck ball rolls for about a second; an on/off flicker does not."""
        v = np.full(self.t.size, 2.0)
        v[0:4] = 150.0
        shape = decay_shape(self.t, v, 0.0, window_s=1.5)
        self.assertIn("spike", shape["verdict"])
        self.assertLessEqual(shape["active_s"], 0.25)

    def test_an_on_off_signal_that_never_reaches_a_quarter_is_not_monotone(self):
        v = np.zeros(self.t.size)
        for k in range(0, 30, 4):
            v[k] = 100.0                 # alternating on/off, like a codec flicker
        shape = decay_shape(self.t, v, 0.0, window_s=1.5)
        self.assertNotIn("consistent with a rolling ball", shape["verdict"])

    def test_a_flat_signal_reads_as_persisting(self):
        v = np.full(self.t.size, 50.0)
        shape = decay_shape(self.t, v, 0.0, window_s=1.5)
        self.assertIn("persists", shape["verdict"])
        self.assertIsNone(shape["half_peak_after_s"])

    def test_the_shape_reports_levels_without_claiming_a_model(self):
        v = 100.0 * np.exp(-1.0 * self.t)
        shape = decay_shape(self.t, v, 0.0)
        self.assertIn("level_at_+0.5s", shape)
        self.assertIn("decreasing_step_share", shape)
        self.assertNotIn("friction", shape)
        self.assertNotIn("deceleration_mm_s2", shape)


class LoadQuadTest(unittest.TestCase):
    def test_reads_the_verified_per_segment_calibration(self):
        path = ROOT / "out" / "calib_vod30_segments.json"
        if not path.exists():
            self.skipTest("segment calibration artifact not present")
        quad = load_quad("vod30")
        self.assertEqual(quad["source"], str(path))
        self.assertTrue(quad["verified"])
        self.assertEqual(len(quad["quad_px"]), 4)

    def test_falls_back_to_the_hand_anchors_when_the_segments_are_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
                {"anchors": {"70.0": [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12]]}}))
            quad = load_quad("vod30", root=root)
            self.assertEqual(quad["quad_px"], [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])

    def test_reports_honestly_when_there_is_no_quad(self):
        with tempfile.TemporaryDirectory() as tmp:
            quad = load_quad("vod30", root=Path(tmp))
            self.assertIsNone(quad["quad_px"])


class PersistenceTest(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        arrays = {"t": np.arange(5, dtype=np.float64),
                  "ball17": np.array([0.0, 1.5, 2.5, 3.5, 4.5]),
                  "occ_dense": np.zeros(5)}
        report = ScanReport(dataset="unit", video="none", fps=30.0, frame_count=5,
                            frames_scanned=5, resolution=[WORK_W, WORK_H],
                            native_resolution=[SCAN_W, SCAN_H], quad_px=QUAD,
                            quad_source="", quad_verified=True,
                            config=asdict(MotionConfig()),
                            cost={"ms_per_frame": 0.0, "wall_s": 0.0})
        with tempfile.TemporaryDirectory() as tmp:
            paths = save_scan(report, arrays, {"source": "unit-test", "verified": True}, tmp)
            self.assertTrue(Path(paths["json"]).exists())
            loaded, loaded_arrays = load_scan(tmp, "unit")
            self.assertEqual(loaded["dataset"], "unit")
            self.assertEqual(loaded["quad_source"], "unit-test")
            self.assertTrue(loaded["quad_verified"])
            np.testing.assert_allclose(loaded_arrays["ball17"], arrays["ball17"])
            for name in arrays:
                self.assertIn(name, loaded["series"]["fields"])


class ResolutionTest(unittest.TestCase):
    """The tool must follow the frames, not carry 720p pixel counts to 1080p."""

    def test_the_reference_configuration_is_unchanged(self):
        cfg = MotionConfig()
        self.assertEqual((cfg.scan_w, cfg.scan_h), (1280, 720))
        self.assertEqual(series_fields(cfg),
                         ("t", "ball17", "ball9", "ball25", "ball13w", "occ_share",
                          "occ_dense", "mean", "cell", "cell_share"))
        self.assertEqual(onset_signal(cfg), "ball17")

    def test_a_bigger_frame_scales_the_footprints(self):
        small = freeze(MotionConfig())
        full = freeze(MotionConfig(scan_w=1920, scan_h=1080, width=1440, height=810,
                                   ball_radius_px=15.4, ball_area_px=745.1))
        self.assertGreater(full.ball_k, small.ball_k)
        self.assertGreater(full.occ_dense_k, small.occ_dense_k)
        self.assertGreater(ball_area(full), 2 * ball_area(small))
        self.assertNotEqual(series_fields(full), series_fields(small))
        self.assertEqual(onset_signal(full), f"ball{full.ball_k}")

    def test_the_measured_radius_wins_over_the_scaled_one(self):
        self.assertAlmostEqual(ball_radius(MotionConfig(scan_w=1920, ball_radius_px=15.4)),
                               15.4, places=3)
        self.assertAlmostEqual(ball_radius(MotionConfig(scan_w=1920)), 9.45 * 1.5, places=2)

    def test_the_occlusion_bar_is_resolution_independent(self):
        """OCC_DENSE_MIN is a ratio of a window that scales with the ball, so a ball
        fills the same share of it at any resolution."""
        small = freeze(MotionConfig())
        full = freeze(MotionConfig(scan_w=1920, scan_h=1080, ball_radius_px=15.4))
        self.assertAlmostEqual(ball_area(small) / small.occ_dense_k ** 2,
                               ball_area(full) / full.occ_dense_k ** 2, delta=0.03)

    def test_the_working_mask_scales_from_its_own_frame_size(self):
        """A 1920x1080 quad scaled by the 1280x720 reference ratio lands in the wrong
        corner of the frame, and every occlusion reading taken on it is meaningless."""
        quad = [[722.0, 452.0], [1177.0, 449.0], [1433.0, 844.0], [467.0, 849.0]]
        cfg = freeze(MotionConfig(scan_w=1920, scan_h=1080, width=1440, height=810,
                                  ball_radius_px=15.4))
        ctx = cloth_context(quad, cfg)
        ys, xs = np.divmod(ctx.idx, cfg.width)
        self.assertAlmostEqual(xs.min(), 467 * 0.75, delta=2)
        self.assertAlmostEqual(xs.max(), 1433 * 0.75, delta=2)
        self.assertAlmostEqual(ys.min(), 449 * 0.75, delta=2)
        self.assertAlmostEqual(ys.max(), 849 * 0.75, delta=2)
        self.assertAlmostEqual(ctx.idx.size / ctx.native_idx.size, 0.5625, delta=0.01)

    def test_a_quad_from_the_wrong_frame_size_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "fixed_corners.json").write_text(json.dumps(
                {"corners": [[722, 452], [1177, 449], [1433, 844], [467, 849]]}))
            self.assertIsNotNone(load_quad("highlight", root=root,
                                           frame_size=(1920, 1080))["quad_px"])
            wrong = load_quad("highlight", root=root, frame_size=(1280, 720))
            self.assertIsNone(wrong["quad_px"])
            self.assertTrue(any("does not fit" in line for line in wrong["rejected"]))

    def test_vod30_anchors_are_not_used_for_another_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
                {"anchors": {"70.0": [[1, 2], [3, 4], [5, 6], [7, 8]]}}))
            self.assertEqual(load_quad("vod30", root=root)["quad_px"],
                             [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
            self.assertIsNone(load_quad("highlight", root=root)["quad_px"])

    def test_a_real_dataset_config_comes_from_its_own_frames(self):
        path = data_guard.require(ROOT / "data" / "vod_highlight.mp4")
        # highlight has no hand anchors, so its quad comes from the dataset's own
        # reference file (or a measured segment): without one the quad is None.
        data_guard.require_any(ROOT / "out" / "fixed_corners.json",
                               ROOT / "out" / "calib_highlight_segments.json")
        cfg = config_for(path, "highlight")
        self.assertEqual((cfg.scan_w, cfg.scan_h), (1920, 1080))
        self.assertEqual((cfg.width, cfg.height), (1440, 810))
        self.assertGreater(cfg.ball_k, BALL_K_NATIVE)
        quad = load_quad("highlight", frame_size=(cfg.scan_w, cfg.scan_h))
        self.assertIsNotNone(quad["quad_px"])
        self.assertLess(max(p[0] for p in quad["quad_px"]), 1920)


class ChromaChannelTest(unittest.TestCase):
    """The ball channel can run on the colour planes, and they are not the luma one."""

    def setUp(self):
        self.cfg = MotionConfig(channels=("luma", "B", "R", "BR"))
        self.ctx = cloth_context(QUAD, self.cfg)

    def _pair(self, plane, level=200):
        prev = np.zeros((SCAN_H, SCAN_W, 3), np.uint8)
        cur = prev.copy()
        if plane == "B":
            cur[380:400, 620:640, 0] = level
        elif plane == "R":
            cur[380:400, 620:640, 2] = level
        elif plane == "luma":
            cur[380:400, 620:640, :] = level
        return prev, cur

    def test_a_blue_only_change_shows_in_B_and_BR_not_in_R(self):
        prev, cur = self._pair("B")
        r = probe_pair(prev, cur, self.ctx, self.cfg)
        self.assertGreater(r["ball_B"], 150)
        self.assertGreater(r["ball_BR"], 150)
        self.assertLess(r["ball_R"], 5)

    def test_a_red_only_change_shows_in_R_and_BR(self):
        prev, cur = self._pair("R")
        r = probe_pair(prev, cur, self.ctx, self.cfg)
        self.assertGreater(r["ball_R"], 150)
        self.assertGreater(r["ball_BR"], 150)
        self.assertLess(r["ball_B"], 5)

    def test_BR_takes_whichever_plane_is_distinct(self):
        prev, cur = self._pair("B")
        blue = probe_pair(prev, cur, self.ctx, self.cfg)["ball_BR"]
        prev, cur = self._pair("R")
        red = probe_pair(prev, cur, self.ctx, self.cfg)["ball_BR"]
        self.assertAlmostEqual(blue, red, delta=1.0)

    def test_a_colour_change_can_beat_luma_reads(self):
        """A ball distinct in colour but not in brightness: luma sees little."""
        prev = np.zeros((SCAN_H, SCAN_W, 3), np.uint8)
        cur = prev.copy()
        cur[380:400, 620:640, 0] = 180          # blue up, red unchanged
        r = probe_pair(prev, cur, self.ctx, self.cfg)
        self.assertGreater(r["ball_B"] / max(1.0, r["ball_luma"]), 2.0)

    def test_the_probe_reads_at_a_given_point_not_only_the_maximum(self):
        prev, cur = self._pair("B")
        r = probe_pair(prev, cur, self.ctx, self.cfg, points=[(630, 390), (400, 300)])
        self.assertGreater(r["ball_B_at"][0], 150)      # on the change
        self.assertLess(r["ball_B_at"][1], 5)           # elsewhere on the cloth
        for key in ("ball_B_at_small", "ball_B_at_wide"):
            self.assertIn(key, r)

    def test_channel_planes_rejects_an_unknown_name(self):
        with self.assertRaises(ValueError):
            channel_planes(np.zeros((4, 4, 3), np.uint8), ("Y",))


class MovingBallTest(unittest.TestCase):
    """The census pairing: same colour, mutual nearest, real displacement."""

    def test_a_moving_same_colour_ball_becomes_an_instance(self):
        census = {"1.0": [{"color": "red", "img": [100, 100], "r": 9}],
                  "1.5": [{"color": "red", "img": [140, 100], "r": 9}]}
        rows = moving_ball_instances(census, min_move_px=5.0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["moved_px"], 40.0)
        self.assertEqual(rows[0]["color"], "red")

    def test_a_stationary_ball_is_not_an_instance(self):
        census = {"1.0": [{"color": "red", "img": [100, 100]}],
                  "1.5": [{"color": "red", "img": [101, 100]}]}
        self.assertEqual(moving_ball_instances(census, min_move_px=5.0), [])

    def test_an_unknown_colour_is_dropped_rather_than_guessed(self):
        census = {"1.0": [{"color": "unknown", "img": [100, 100]}],
                  "1.5": [{"color": "unknown", "img": [200, 100]}]}
        self.assertEqual(moving_ball_instances(census, min_move_px=5.0), [])

    def test_the_colour_with_the_smaller_move_is_matched(self):
        """Two blues move; each must take its own nearest, not the other's."""
        census = {"1.0": [{"color": "blue", "img": [100, 100]},
                          {"color": "blue", "img": [500, 500]}],
                  "1.5": [{"color": "blue", "img": [110, 100]},
                          {"color": "blue", "img": [400, 500]}]}
        rows = moving_ball_instances(census, min_move_px=5.0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(round(r["moved_px"]) for r in rows), [10, 100])


class SyntheticVideoTest(unittest.TestCase):
    """End-to-end: decode -> channels -> an onset at a known frame."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = str(Path(cls.tmp.name) / "clip.avi")
        writer = cv2.VideoWriter(cls.path, cv2.VideoWriter_fourcc(*"MJPG"), 30.0,
                                 (WORK_W, WORK_H))
        if not writer.isOpened():
            cls.tmp.cleanup()
            raise unittest.SkipTest("this OpenCV build cannot write MJPG avi")
        cls.onset_frame = 40
        for i in range(80):
            frame = np.full((WORK_H, WORK_W, 3), 60, np.uint8)
            if i >= cls.onset_frame:
                # a ball-sized bright patch that jumps one diameter per frame on the
                # cloth: the strongest thing this detector is meant to see
                x = 300 + 14 * (i - cls.onset_frame)
                frame[300:314, x:x + 14] = 220
            writer.write(frame)
        writer.release()
        cls.quad_work = [[150.0, 150.0], [750.0, 150.0], [750.0, 450.0], [150.0, 450.0]]

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    def test_the_scan_finds_the_onset_of_a_moving_patch(self):
        from src.motion_scan import scan
        quad_native = [[x * SCAN_W / WORK_W, y * SCAN_H / WORK_H] for x, y in self.quad_work]
        cfg = MotionConfig(native=False)      # the synthetic clip has no native twin
        report, arrays = scan(self.path, quad_native, cfg, "unit")
        self.assertEqual(report.frames_scanned, 80)
        self.assertGreater(float(arrays["ball13w"].max()), 40.0)
        quiet = float(np.median(arrays["ball13w"][: self.onset_frame - 5]))
        self.assertLess(quiet, 5.0)
        peaks = np.flatnonzero(arrays["ball13w"] >= 40.0)
        self.assertGreaterEqual(int(peaks[0]), self.onset_frame - 1)

    def test_the_strip_is_written_and_is_legible(self):
        from src.motion_scan import frame_detail, render_strip, scan
        quad_native = [[x * SCAN_W / WORK_W, y * SCAN_H / WORK_H] for x, y in self.quad_work]
        cfg = MotionConfig(native=False)
        _report, arrays = scan(self.path, quad_native, cfg, "unit")
        ctx = cloth_context(quad_native, cfg)
        onset = {"frame": self.onset_frame + 3, "t_onset": (self.onset_frame + 3) / 30.0,
                 "peak": 60.0, "threshold": 40.0, "baseline": 0.0}
        out = Path(self.tmp.name) / "onsets" / "strip.png"
        render_strip(self.path, onset, ctx, arrays, out, cfg, threshold=40.0,
                     occlusion=False, signal="ball13w")
        self.assertTrue(out.exists())
        image = cv2.imread(str(out))
        self.assertGreater(image.shape[0], 300)          # tiles + chart
        self.assertGreater(image.shape[1], 1000)
        detail = frame_detail(self.path, self.onset_frame + 3, ctx, cfg)
        self.assertIn("ball_peak_box", detail)
        self.assertEqual(len(detail["cell_counts"]), ctx.n_cells)


if __name__ == "__main__":
    unittest.main()
