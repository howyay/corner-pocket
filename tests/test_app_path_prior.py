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


class UnifiedQuadNoteTests(unittest.TestCase):
    """Why a frame has no quad must travel with the payload the viewer renders.

    A refused frame used to arrive as ``table_corners: null`` and nothing else, so the
    operator saw a silent absence instead of "the cloth is hidden"
    (docs/app-path-refusal.md).
    """

    META = {"dataset": "vod30", "frame_index": 150, "timestamp_seconds": 5.0,
            "timestamp_kind": "nominal_cfr", "width": 1280, "height": 720}
    REFUSAL = {"corners": None, "mask": None, "confidence": 0.0, "reason": "low_cloth_area",
               "refined": False, "source": "naive", "used_prior": True,
               "debug_info": {"tried": [{"prior_source": "saved_prior", "info": {
                   "reason": "low_cloth_area", "verified_sides": 2, "unverified_sides": [
                       {"side": 0, "reason": "low_cloth_area"}, {"side": 2, "reason": "low_cloth_area"}],
                   "sides": [{"side": 0, "verified": False, "reason": "low_cloth_area"},
                             {"side": 1, "verified": True},
                             {"side": 2, "verified": False, "reason": "low_cloth_area"},
                             {"side": 3, "verified": True}]}}]}}
    ACCEPTED = {"corners": np.array([[266, 161], [400, 162], [498, 284], [192, 281]], np.float32),
                "mask": None, "confidence": 0.71, "reason": None, "refined": True,
                "source": "refined_saved_prior", "debug_info": {
                    "reason": "side_inherited", "verified_sides": 3, "sides": [
                        {"side": 0, "verified": True},
                        {"side": 1, "verified": True, "inherited": True, "reason": "side_inherited"},
                        {"side": 2, "verified": True}, {"side": 3, "verified": True}]}}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'out').mkdir()
        (self.root / 'out' / 'pid_anchors_vod30.json').write_text(
            json.dumps({'anchors': {'70.0': ANCHORS}}))
        self.backend = Backend(self.root)

    def start_patches(self, *pairs):
        for target, replacement in pairs:
            patcher = patch(target, **replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def meta(self, refined):
        frame = np.zeros((720, 1280, 3), np.uint8)
        self.start_patches(('annotator.unified_server.Backend.video_metadata',
                            {'new': lambda *a, **k: {"fps": 30.0, "frame_count": 330,
                                                     "width": 1280, "height": 720}}),
                           ('annotator.unified_server.Backend.decode_frame',
                            {'new': lambda *a, **k: (frame, dict(self.META))}),
                   ('src.frame_inference.detect_table_for_frame', {'return_value': refined}),
                   ('src.table_detect.detect_table', {'return_value': {'corners': None, 'mask': None}}),
                   ('src.ball_detect.detect_ball_candidates', {'return_value': []}))
        return self.backend.unified('vod30', 150)

    def test_a_refusal_carries_its_reason_and_per_side_evidence(self):
        data = self.meta(self.REFUSAL)
        self.assertIsNone(data['table_corners'])
        note = data['table_quad']
        self.assertEqual(note['state'], 'naive_fallback')
        self.assertEqual(note['reason'], 'low_cloth_area')
        self.assertEqual(note['verified_sides'], 2)
        self.assertEqual([side['state'] for side in note['sides']],
                         ['unverified', 'verified', 'unverified', 'verified'])
        self.assertEqual(note['sides'][0]['reason'], 'low_cloth_area')
        self.assertTrue(note['seed_file'].endswith('pid_anchors_vod30.json'))
        # the note describes the cached detection the payload's corners came from
        self.assertEqual(self.backend._unified_quad('vod30', 150), note)
        self.assertIsNone(self.backend._unified_quad('vod30', 999))

    def test_an_accepted_quad_reports_confidence_and_inherited_sides(self):
        data = self.meta(self.ACCEPTED)
        self.assertIsNotNone(data['table_corners'])
        note = data['table_quad']
        self.assertEqual(note['state'], 'refined')
        self.assertIsNone(note['reason'])
        self.assertEqual(note['confidence'], 0.71)
        self.assertEqual([side['state'] for side in note['sides']],
                         ['verified', 'inherited', 'verified', 'verified'])

    def test_without_a_seed_the_note_says_so_instead_of_inventing_a_reason(self):
        (self.root / 'out' / 'pid_anchors_vod30.json').unlink()
        self.start_patches(('annotator.unified_server.Backend.video_metadata',
                            {'new': lambda *a, **k: {"fps": 30.0, "frame_count": 330,
                                                     "width": 1280, "height": 720}}),
                           ('annotator.unified_server.Backend.decode_frame',
                            {'new': lambda *a, **k: (np.zeros((720, 1280, 3), np.uint8),
                                                     dict(self.META))}),
                   ('src.table_detect.detect_table',
                    {'return_value': {'corners': np.array([[100, 80], [540, 76], [540, 280], [100, 284]],
                                                          np.float32), 'mask': None}}),
                   ('src.ball_detect.detect_ball_candidates', {'return_value': []}))
        note = self.backend.unified('vod30', 150)['table_quad']
        self.assertEqual(note['state'], 'no_seed')
        self.assertIsNone(note['seed_file'])


if __name__ == '__main__':
    unittest.main()
