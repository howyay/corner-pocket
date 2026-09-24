"""tiny_ball_net contract: the label plumbing, the split, the target and the peaks.

Everything here is synthetic -- the labels, the split, the heatmap target and the
peak picker -- so the probe's measurement rules are pinned without a GPU or a 690 MB
recording.  The property that matters most is the split: a held-out frame must never
sit within the gap of a training frame, or the held-out score is a near-duplicate
score.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.tiny_ball_net import (NATIVE_WH, SIGMA_PX, SPLIT_GAP_S, TRAIN_WH, count_params,
                               f1, heatmap_target, load_labels, match, pick_peaks,
                               read_frames, split_blocks, stack_for)

ROOT = Path(__file__).resolve().parent.parent


class LabelLoadingTest(unittest.TestCase):
    def test_labels_come_from_both_caches_with_raw_scores(self):
        labels = load_labels()
        if not labels:
            self.skipTest("no SAM3 caches present")
        self.assertGreater(len(labels), 50)
        instances = [b for balls in labels.values() for b in balls]
        self.assertGreater(len(instances), 200)
        for ball in instances[:50]:
            for key in ("x", "y", "r", "score"):
                self.assertIn(key, ball)
        scores = [b["score"] for b in instances]
        # the delivered caches were cut at the production score, and that is recorded
        self.assertGreaterEqual(min(scores), 0.6)

    def test_a_time_key_is_rounded_the_same_way_everywhere(self):
        labels = load_labels()
        for t in list(labels)[:20]:
            self.assertEqual(float(t), round(float(t), 3))


class SplitTest(unittest.TestCase):
    def test_no_held_frame_is_within_the_gap_of_a_train_frame(self):
        times = [round(i * 0.5, 3) for i in range(800)]
        train, held, _dropped = split_blocks(times, block_s=30.0, held_every=4,
                                             gap_s=SPLIT_GAP_S)
        self.assertTrue(train and held)
        for t in held:
            for u in train:
                self.assertGreaterEqual(abs(t - u), SPLIT_GAP_S)

    def test_the_split_keeps_most_of_a_dense_series(self):
        times = [round(i * 0.5, 3) for i in range(800)]
        train, held, _dropped = split_blocks(times, block_s=30.0, held_every=4)
        self.assertGreaterEqual(len(train), 0.45 * len(times))
        self.assertGreater(len(held), 0.1 * len(times))

    def test_a_bursty_series_still_splits(self):
        times = [round(t, 3) for t in [1, 2, 3, 60, 61, 62, 120, 121, 122, 180, 181, 182]]
        train, held, _dropped = split_blocks(times, block_s=30.0, held_every=2)
        self.assertTrue(train or held)

    def test_an_empty_series_is_not_an_error(self):
        self.assertEqual(split_blocks([]), ([], [], []))


class HeatmapTargetTest(unittest.TestCase):
    def test_a_ball_becomes_a_gaussian_at_the_scaled_position(self):
        target = heatmap_target((TRAIN_WH[1], TRAIN_WH[0]),
                                [{"x": 640.0, "y": 360.0, "r": 9.2}])
        self.assertEqual(target.shape, (TRAIN_WH[1], TRAIN_WH[0]))
        peak = np.unravel_index(int(np.argmax(target)), target.shape)
        self.assertAlmostEqual(peak[1], 320.0, delta=1.5)
        self.assertAlmostEqual(peak[0], 180.0, delta=1.5)
        self.assertAlmostEqual(float(target.max()), 1.0, places=4)

    def test_overlapping_balls_take_the_maximum_not_the_sum(self):
        one = heatmap_target((TRAIN_WH[1], TRAIN_WH[0]), [{"x": 640.0, "y": 360.0, "r": 9}])
        two = heatmap_target((TRAIN_WH[1], TRAIN_WH[0]),
                             [{"x": 640.0, "y": 360.0, "r": 9},
                              {"x": 642.0, "y": 360.0, "r": 9}])
        self.assertLessEqual(float(two.max()), 1.0 + 1e-6)

    def test_the_sigma_matches_the_declared_ball_scale(self):
        radius = 9.2 * TRAIN_WH[0] / NATIVE_WH[0]
        self.assertAlmostEqual(radius, 4.6, delta=0.2)
        self.assertLess(SIGMA_PX, radius)

    def test_no_balls_gives_an_empty_target(self):
        target = heatmap_target((TRAIN_WH[1], TRAIN_WH[0]), [])
        self.assertEqual(float(target.max()), 0.0)


class PeakPickerTest(unittest.TestCase):
    def test_a_single_blob_gives_one_peak(self):
        heat = np.zeros((180, 320), np.float32)
        heat[90, 160] = 0.9
        heat[90, 161] = 0.8
        peaks = pick_peaks(heat, 0.5, nms_px=4.0)
        self.assertEqual(len(peaks), 1)
        self.assertEqual(peaks[0][:2], (160, 90))

    def test_two_separated_blobs_give_two_peaks(self):
        heat = np.zeros((180, 320), np.float32)
        heat[40, 40] = 0.9
        heat[140, 280] = 0.7
        self.assertEqual(len(pick_peaks(heat, 0.5, nms_px=4.0)), 2)

    def test_a_low_threshold_finds_more(self):
        heat = np.zeros((180, 320), np.float32)
        heat[40, 40] = 0.6
        heat[140, 280] = 0.2
        self.assertEqual(len(pick_peaks(heat, 0.5)), 1)
        self.assertEqual(len(pick_peaks(heat, 0.1)), 2)

    def test_an_empty_heatmap_finds_nothing(self):
        self.assertEqual(pick_peaks(np.zeros((180, 320), np.float32), 0.3), [])


class MatchTest(unittest.TestCase):
    def test_a_prediction_on_the_label_matches(self):
        truth = [{"x": 100.0, "y": 200.0, "r": 9.0}]
        result = match([(50, 100, 0.9)], truth, tol_px=6.0, scale=2.0)
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["fp"], 0)
        self.assertEqual(result["fn"], 0)
        self.assertAlmostEqual(result["errors"][0], 0.0, places=6)

    def test_a_prediction_far_away_is_a_false_positive_and_a_miss(self):
        truth = [{"x": 100.0, "y": 200.0, "r": 9.0}]
        result = match([(500, 500, 0.9)], truth, tol_px=6.0, scale=2.0)
        self.assertEqual(result["matched"], 0)
        self.assertEqual(result["fp"], 1)
        self.assertEqual(result["fn"], 1)

    def test_matching_is_one_to_one(self):
        truth = [{"x": 100.0, "y": 200.0, "r": 9.0}]
        result = match([(50, 100, 0.9), (51, 101, 0.8)], truth, tol_px=6.0, scale=2.0)
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["fp"], 1)

    def test_the_localisation_error_is_reported_in_native_pixels(self):
        truth = [{"x": 100.0, "y": 200.0, "r": 9.0}]
        result = match([(52, 100, 0.9)], truth, tol_px=10.0, scale=2.0)
        self.assertAlmostEqual(result["errors"][0], 4.0, places=6)

    def test_f1_is_the_harmonic_mean(self):
        self.assertAlmostEqual(f1(1.0, 1.0), 1.0, places=6)
        self.assertAlmostEqual(f1(0.5, 0.5), 0.5, places=6)
        self.assertEqual(f1(0.0, 0.0), 0.0)


class FrameReadTest(unittest.TestCase):
    def test_reading_a_synthetic_clip_gives_the_wanted_frames(self):
        import cv2
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "clip.avi")
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (320, 180))
            if not writer.isOpened():
                self.skipTest("this OpenCV build cannot write MJPG avi")
            for i in range(60):
                writer.write(np.full((180, 320, 3), i * 4 % 255, np.uint8))
            writer.release()
            frames = read_frames(path, [5, 6, 30, 55])
            self.assertEqual(sorted(frames), [5, 6, 30, 55])
            self.assertTrue(all(f.shape == (180, 320, 3) for f in frames.values()))

    def test_a_missing_frame_is_skipped_not_faked(self):
        self.assertEqual(read_frames("/nonexistent/video.mp4", [1, 2]), {})


class ModelTest(unittest.TestCase):
    def test_the_model_is_small_and_maps_three_frames_to_one_heatmap(self):
        import torch
        from src.tiny_ball_net import STACK, build_model
        model = build_model()
        self.assertLess(count_params(model), 2_000_000)
        out = model(torch.zeros(1, STACK * 3, 180, 320))
        self.assertEqual(tuple(out.shape), (1, 1, 180, 320))


if __name__ == "__main__":
    unittest.main()
