"""Pins for the app path's search centre: anchors only, never a reference file.

The viewer clears the automatic cloth quad against the dataset's hand-placed
anchors with a 40 px bar, so the app path has to search around the same geometry
and must never be seeded from ``out/corners_30min_v2.json`` again - that file is
the reference the refinement used to be scored against *and* the seed, which made
both the viewer's refusal total and the offline score circular
(docs/app-path-refusal.md).
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from annotator.unified_server import Backend
from src.frame_inference import app_prior_for, detect_table_for_frame

ANCHORS = [[532.0, 323.0], [800.0, 324.0], [997.0, 569.0], [384.0, 563.0],
           [700.0, 200.0], [560.0, 500.0]]
REFERENCE_QUAD = [[454.9, 307.8], [799.5, 319.4], [1023.8, 573.1], [449.6, 563.5]]


class PriorResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'out').mkdir()

    def save(self, name, payload):
        (self.root / 'out' / name).write_text(json.dumps(payload))

    def test_anchors_are_the_seed_and_the_first_four_points_are_the_quad(self):
        self.save('pid_anchors_vod30.json', {'anchors': {'70.0': ANCHORS}})
        quad = app_prior_for('vod30', root=self.root)
        self.assertEqual(np.asarray(quad).shape, (4, 2))
        self.assertEqual(sorted(np.asarray(quad).round(1).tolist()),
                         sorted(np.asarray(ANCHORS[:4]).round(1).tolist()))

    def test_the_reference_quad_is_never_used_as_a_seed(self):
        """The measured-bad reference file alone must not seed the app path."""
        self.save('corners_30min_v2.json', {'corners': REFERENCE_QUAD})
        self.assertIsNone(app_prior_for('vod30', root=self.root))

    def test_anchors_win_over_a_reference_file_and_earliest_time_is_used(self):
        self.save('corners_30min_v2.json', {'corners': REFERENCE_QUAD})
        self.save('pid_anchors_vod30.json',
                  {'anchors': {'120.0': [[1, 2], [3, 4], [5, 6], [7, 8]],
                               '70.0': ANCHORS}})
        quad = np.asarray(app_prior_for('vod30', root=self.root)).round(1).tolist()
        self.assertEqual(sorted(quad), sorted(np.asarray(ANCHORS[:4]).round(1).tolist()))

    def test_no_anchors_no_seed_and_a_broken_file_is_not_a_seed(self):
        self.assertIsNone(app_prior_for('vod30', root=self.root))
        (self.root / 'out' / 'pid_anchors_vod30.json').write_text('{not json')
        self.assertIsNone(app_prior_for('vod30', root=self.root))
        self.save('pid_anchors_vod30.json', {'anchors': {'70.0': [[1, 2], [3, 4]]}})
        self.assertIsNone(app_prior_for('vod30', root=self.root),
                          'four corners are required for a quad')

    def test_detect_table_for_frame_searches_around_that_seed(self):
        self.save('pid_anchors_vod30.json', {'anchors': {'70.0': ANCHORS}})
        seen = {}
        wanted = app_prior_for('vod30', root=self.root)

        def fake(frame, prior=None, prev_quad=None):
            seen['prior'] = prior
            return {'corners': None, 'mask': None, 'confidence': 0.0, 'reason': 'fixture'}

        with patch('src.table_refine.detect_table_refined', side_effect=fake):
            detect_table_for_frame(np.zeros((360, 640, 3), np.uint8), dataset='vod30', root=self.root)
        np.testing.assert_allclose(seen['prior'], wanted)
        # an explicit prior still wins, and no dataset keeps the naive fallback
        with patch('src.table_refine.detect_table_refined', side_effect=fake):
            detect_table_for_frame(np.zeros((360, 640, 3), np.uint8), dataset='vod30',
                                   prior=np.zeros((4, 2), np.float32), root=self.root)
        self.assertEqual(np.asarray(seen['prior']).shape, (4, 2))
        self.assertTrue(np.all(np.asarray(seen['prior']) == 0))

    def test_backend_caches_the_resolved_seed_once_per_dataset(self):
        self.save('pid_anchors_vod30.json', {'anchors': {'70.0': ANCHORS}})
        backend = Backend(self.root)
        calls = []
        import src.frame_inference as frame_inference
        original = frame_inference.app_prior_for

        def counting(dataset, root=None):
            calls.append(dataset)
            return original(dataset, root=root)

        with patch.object(frame_inference, 'app_prior_for', side_effect=counting):
            first = backend._prior_for('vod30')
            second = backend._prior_for('vod30')
        self.assertEqual(calls, ['vod30'], 'the reference is read once per dataset')
        np.testing.assert_allclose(np.asarray(first), np.asarray(second))
        self.assertIsNone(backend._prior_for('highlight'))

    def test_the_offline_harness_resolves_the_prior_like_the_server(self):
        """check_app_quad must not invent its own search centre."""
        import src.check_app_quad as check_app_quad
        import src.frame_inference as frame_inference
        self.assertIs(check_app_quad.app_prior_for, frame_inference.app_prior_for)


class AppPathScaleTests(unittest.TestCase):
    """The 2x detection space is the one coordinate seam the app path has."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'out').mkdir()
        (self.root / 'out' / 'pid_anchors_vod30.json').write_text(
            json.dumps({'anchors': {'70.0': ANCHORS}}))
        self.backend = Backend(self.root)

    def test_unified_detection_halves_the_seed_and_doubles_the_corners(self):
        frame = np.zeros((720, 1280, 3), np.uint8)
        captured = {}
        small_corners = np.array([[100, 80], [540, 76], [540, 280], [100, 284]], np.float32)

        def fake(frame_arg, dataset=None, prior=None, root=None):
            captured['prior'] = prior
            captured['shape'] = frame_arg.shape
            return {'corners': small_corners, 'mask': None, 'confidence': 0.5, 'reason': None}

        with patch('src.frame_inference.detect_table_for_frame', side_effect=fake), \
                patch('src.ball_detect.detect_ball_candidates', return_value=[]):
            corners, balls = self.backend._unified_detection('vod30', 7, frame)
        self.assertEqual(captured['shape'], (360, 640, 3), 'the detector runs on the 2x copy')
        np.testing.assert_allclose(captured['prior'],
                                   np.asarray(app_prior_for('vod30', root=self.root)) / 2.0,
                                   atol=1e-4)
        np.testing.assert_allclose(np.asarray(corners), small_corners * 2.0, atol=1e-4)
        self.assertEqual(balls, [])


if __name__ == '__main__':
    unittest.main()
