"""Tests for the SAM3 cache's cloth filter and its re-measure bookkeeping.

The filter is the fix for a measured failure: `detect_table`'s per-frame mask
zeroed a frame that held ten balls (t=487.3 of vod30).  These tests pin that the
verified reference geometry decides, that the choice is recorded, and that a
frame measured through a filter later shown to be wrong goes back on the list.
"""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np

import data_guard

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.sam3_ball_cache import (cloth_mask, load_cache, load_filters,  # noqa: E402
                                 pending_times, reference_quad, save_cache)


class ClothMaskTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((720, 1280, 3), 90, np.uint8)
        self.quad = np.array([[400, 300], [900, 300], [950, 600], [350, 600]], np.float32)

    def test_the_reference_quad_decides_and_says_so(self):
        mask, source = cloth_mask(self.frame, reference=self.quad)
        self.assertEqual(source, "reference_quad")
        self.assertGreater(int(mask.sum()), 0)
        # a point inside the quad is cloth, a point far outside is not
        self.assertTrue(mask[450, 600])
        self.assertFalse(mask[50, 50])

    def test_without_a_reference_it_falls_back_and_says_so(self):
        # The workspace has calibration, so the fallback is exercised by taking
        # the reference away rather than by pointing at a missing file.
        from src import sam3_ball_cache as module
        original = module.reference_quad
        module.reference_quad = lambda *args, **kwargs: None
        try:
            mask, source = cloth_mask(self.frame, reference=None)
        finally:
            module.reference_quad = original
        self.assertEqual(source, "frame_mask")
        self.assertEqual(mask.shape, self.frame.shape[:2])

    def test_the_reference_quad_wins_over_a_broken_frame_mask(self):
        # A frame whose per-frame estimate would collapse: the reference still
        # accepts the ball positions inside it.
        mask, source = cloth_mask(self.frame, reference=self.quad)
        self.assertTrue(mask[450, 600])
        self.assertEqual(source, "reference_quad")

    def test_reference_quad_prefers_the_calibration_segment(self):
        # Any one of the three sources reference_quad() falls back through will do.
        data_guard.require_any(data_guard.ROOT / "out" / "calib_vod30_segments.json",
                               data_guard.ROOT / "out" / "pid_anchors_vod30.json",
                               data_guard.ROOT / "out" / "scan30" / "corners.json")
        quad = reference_quad()
        self.assertIsNotNone(quad)
        self.assertEqual(np.asarray(quad).shape, (4, 2))


class PendingTests(unittest.TestCase):
    def test_uncached_times_are_pending(self):
        self.assertEqual(pending_times([1.0, 2.0], cached=[1.0]), [2.0])

    def test_refetch_puts_a_cached_frame_back_on_the_list(self):
        self.assertEqual(pending_times([1.0, 2.0], cached=[1.0, 2.0], refetch=[2.0]), [2.0])

    def test_rounding_matches_the_cache_keys(self):
        # The cache is keyed by the rounded time, so 1.25 and 1.24 both resolve
        # to the key "1.2" and neither is measured twice.
        self.assertEqual(pending_times([1.25], cached=[1.2]), [])
        self.assertEqual(pending_times([1.24], cached=[1.2]), [])
        self.assertEqual(pending_times([1.26], cached=[1.2]), [1.3])


class CacheFilterMapTests(unittest.TestCase):
    def test_the_filter_that_produced_a_frame_is_stored_with_it(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            save_cache(path, {1.0: [{"score": 0.9}], 2.0: []}, {"1.0": 12.0}, "video.mp4",
                       {"1.0": "reference_quad", "2.0": "frame_mask"})
            self.assertEqual(load_filters(path), {"1.0": "reference_quad", "2.0": "frame_mask"})
            self.assertEqual(sorted(load_cache(path)), [1.0, 2.0])

    def test_a_cache_without_the_map_reports_none(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            path.write_text(json.dumps({"frames": {"1.0": []}}))
            self.assertEqual(load_filters(path), {})


if __name__ == "__main__":
    unittest.main()
