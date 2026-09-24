"""TBD contract: the accumulator finds a coherent mover and rejects a plateau.

The synthetic tests build response stacks directly, so the geometry of the search is
pinned without a video: a spot that moves on a line must outscore the same spot
standing still, a plateau must fail the local-maximum test, and a hypothesis that
leaves the frame must be dropped rather than wrapped.
"""
import math
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.track_before_detect import (SPEEDS, TBDConfig, _prepare, evaluate_stack,
                                     patch_stack, score_mesh, search_tracks,
                                     velocity_grid)

H, W = 720, 1280


def stack_with_track(vx, vy, x0=600, y0=380, n=9, level=120.0, spot=9) -> np.ndarray:
    stack = np.zeros((n, H, W), np.float32)
    for i in range(n):
        x = int(round(x0 + vx * i))
        y = int(round(y0 + vy * i))
        stack[i, max(0, y - spot):y + spot, max(0, x - spot):x + spot] = level
    return stack


class VelocityGridTest(unittest.TestCase):
    def test_the_grid_spans_the_ball_plausible_speeds(self):
        grid = velocity_grid(TBDConfig())
        speeds = np.hypot(grid[:, 0], grid[:, 1])
        self.assertAlmostEqual(float(speeds.min()), min(SPEEDS), places=6)
        self.assertAlmostEqual(float(speeds.max()), max(SPEEDS), places=6)
        self.assertEqual(grid.shape[0], len(SPEEDS) * TBDConfig().n_directions)

    def test_directions_are_evenly_spread(self):
        angles = sorted(math.degrees(math.atan2(v, u)) % 360
                        for u, v in velocity_grid(TBDConfig(n_directions=12))
                        if abs(math.hypot(u, v) - SPEEDS[0]) < 1e-9)
        self.assertEqual(len(angles), 12)
        gaps = [(b - a) % 360 for a, b in zip(angles, angles[1:] + angles[:1])]
        for gap in gaps:
            self.assertAlmostEqual(gap, 30.0, places=6)


class AccumulatorTest(unittest.TestCase):
    def test_a_spot_moving_on_a_line_scores_higher_than_a_still_one(self):
        prepared = stack_with_track(0.0, 0.0)
        moving = _prepare(stack_with_track(24.0, 0.0))
        still = score_mesh(prepared, [(600, 380)], velocity_grid(TBDConfig()), H, W)[0]
        track = score_mesh(moving, [(600, 380)], velocity_grid(TBDConfig()), H, W)[0]
        self.assertGreater(track.max(), 100.0)
        self.assertGreater(track.max(), still.max())

    def test_the_best_hypothesis_reproduces_the_injected_velocity(self):
        prepared = _prepare(stack_with_track(0.0, 36.0))
        grid = velocity_grid(TBDConfig())
        scores = score_mesh(prepared, [(600, 380)], grid, H, W)[0]
        best = grid[int(np.argmax(scores))]
        # the grid's nearest direction/speed to a straight 36 px/frame fall
        self.assertAlmostEqual(float(np.hypot(*best)), 36.0, delta=1e-6)
        self.assertAlmostEqual(float(math.degrees(math.atan2(best[1], best[0]))), 90.0,
                               delta=1e-6)

    def test_a_hypothesis_that_leaves_the_frame_scores_minus_one(self):
        prepared = _prepare(stack_with_track(0.0, 0.0))
        grid = np.asarray([[60.0, 0.0]])
        scores = score_mesh(prepared, [(1270, 380)], grid, H, W)
        self.assertEqual(float(scores[0, 0]), -1.0)

    def test_the_median_subtraction_removes_a_globally_busy_frame(self):
        busy = np.full((5, H, W), 40.0, np.float32)
        prepared = _prepare(busy)
        self.assertLess(float(prepared.max()), 1e-6)

    def test_without_the_subtraction_a_flat_frame_would_accumulate(self):
        busy = np.full((5, H, W), 40.0, np.float32)
        grid = velocity_grid(TBDConfig())
        raw = score_mesh(busy, [(600, 380)], grid, H, W)[0].max()
        self.assertAlmostEqual(float(raw), 40.0, places=3)


class SearchTest(unittest.TestCase):
    def test_a_coherent_track_is_a_local_maximum(self):
        prepared = _prepare(stack_with_track(0.0, 24.0))
        hit = search_tracks(prepared, None, None, TBDConfig(), centre=(600, 380))
        self.assertTrue(hit["local_max"])
        self.assertAlmostEqual(hit["speed_px_frame"], 24.0, places=3)
        self.assertLess(math.hypot(hit["x"] - 600, hit["y"] - 380), 12.0)

    def test_a_plateau_is_not_claimed_as_a_detection(self):
        """A constant stack has no peak: every direction scores the same, so the
        local-maximum test must refuse it."""
        flat = np.zeros((9, H, W), np.float32)
        flat[:, 300:500, 500:800] = 20.0
        hit = search_tracks(_prepare(flat), None, None, TBDConfig(), centre=(650, 400))
        self.assertFalse(hit["local_max"])

    def test_the_local_search_stays_inside_its_radius(self):
        prepared = _prepare(stack_with_track(0.0, 0.0, x0=600, y0=380))
        hit = search_tracks(prepared, None, None, TBDConfig(search_radius_px=24.0),
                            centre=(600, 380))
        self.assertLessEqual(math.hypot(hit["x"] - 600, hit["y"] - 380), 24.0 + 1e-6)

    def test_explicit_seeds_are_used_as_given(self):
        prepared = _prepare(stack_with_track(0.0, 0.0, x0=700, y0=300))
        hit = search_tracks(prepared, None, None, TBDConfig(), seeds=[(700.0, 300.0)])
        self.assertEqual((hit["x"], hit["y"]), (700.0, 300.0))

    def test_a_centre_or_seeds_is_required(self):
        with self.assertRaises(ValueError):
            search_tracks(np.zeros((3, H, W), np.float32), None, None, TBDConfig())


class MultiNTest(unittest.TestCase):
    def test_every_n_is_scored_from_one_stack(self):
        prepared = _prepare(stack_with_track(0.0, 24.0))
        hits = evaluate_stack(prepared, None, None, TBDConfig(n_frames=9), [3, 5, 7, 9],
                              centre=(600, 380))
        self.assertEqual(sorted(hits), [3, 5, 7, 9])
        for n in (3, 5, 7, 9):
            self.assertIsNotNone(hits[n]["score"])

    def test_an_n_longer_than_the_stack_is_reported_as_none(self):
        prepared = _prepare(stack_with_track(0.0, 24.0, n=5))
        hits = evaluate_stack(prepared, None, None, TBDConfig(n_frames=5), [3, 9],
                              centre=(600, 380))
        self.assertIsNone(hits[9]["score"])


class SyntheticVideoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = str(Path(cls.tmp.name) / "clip.avi")
        writer = cv2.VideoWriter(cls.path, cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (W, H))
        if not writer.isOpened():
            cls.tmp.cleanup()
            raise unittest.SkipTest("this OpenCV build cannot write MJPG avi")
        for i in range(16):
            frame = np.zeros((H, W, 3), np.uint8)
            x = 600 + 24 * i                      # 24 px/frame: on the grid
            frame[370:390, x:x + 20, 0] = 200     # blue only
            writer.write(frame)
        writer.release()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    def test_patch_stack_returns_one_map_per_frame_pair(self):
        from src.motion_scan import MotionConfig, cloth_context
        cfg = MotionConfig()
        ctx = cloth_context([[420.0, 240.0], [1140.0, 240.0], [1140.0, 520.0], [420.0, 520.0]], cfg)
        stack, dense, times = patch_stack(self.path, list(range(2, 11)), ctx, cfg)
        self.assertEqual(stack.shape[0], 9)
        self.assertEqual(len(dense), 9)
        self.assertEqual(len(times), 9)
        self.assertGreater(float(stack.max()), 100.0)

    def test_the_detector_finds_the_injected_track(self):
        from src.motion_scan import MotionConfig, cloth_context
        cfg = MotionConfig()
        ctx = cloth_context([[420.0, 240.0], [1140.0, 240.0], [1140.0, 520.0], [420.0, 520.0]], cfg)
        stack, dense, times = patch_stack(self.path, list(range(2, 11)), ctx, cfg)
        prepared = _prepare(stack)
        hit = search_tracks(prepared, ctx, cfg, TBDConfig(), centre=(700.0, 380.0))
        self.assertLess(hit["direction_deg"], 20.0)          # forward, as injected
        self.assertGreaterEqual(hit["speed_px_frame"], 12.0)  # in the ball band
        self.assertGreater(hit["score"], 50.0)

    def test_the_velocity_estimate_is_biased_low_on_a_smeared_track(self):
        """Pinned, not hidden: a 17 px footprint smears a 24 px/frame mover along its
        own direction, so the accumulator settles on a slower track that stays inside
        the smear.  The detector's speed is therefore a lower bound, not a measurement."""
        from src.motion_scan import MotionConfig, cloth_context
        cfg = MotionConfig()
        ctx = cloth_context([[420.0, 240.0], [1140.0, 240.0], [1140.0, 520.0], [420.0, 520.0]], cfg)
        stack, _dense, _times = patch_stack(self.path, list(range(2, 11)), ctx, cfg)
        hit = search_tracks(_prepare(stack), ctx, cfg, TBDConfig(), centre=(700.0, 380.0))
        self.assertLess(hit["speed_px_frame"], 24.0)


if __name__ == "__main__":
    unittest.main()
