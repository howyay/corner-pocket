"""Cloth-boundary detector contract: confidence/reason, refinement, no crash.

The synthetic frames here build a blue bed inside a dark rail so the detector has
a boundary to find without any VOD on disk; the recorded-reference test is skipped
when ``out/corners_30min_v2.json`` is absent (it is an artifact, not source).
"""
import json
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.table_detect import detect_table
from src.table_refine import (detect_table_refined, load_priors, prior_for, refine_quad_edges)

ROOT = Path(__file__).resolve().parent.parent


def bed_frame(quad=None, occlude=None, cloth_hue=106):
    """Synthetic 640x360 frame shaped like the vod30 geometry.

    The bed covers ~9.5% of the frame, the same fraction the saved vod30 quad
    covers, so the app's quad-sanity rules (2%-90% area, inside the frame) behave
    here exactly as they do on the recording.
    """
    w, h = 640, 360
    frame = np.full((h, w, 3), (40, 40, 42), dtype=np.uint8)
    if quad is None:
        quad = np.array([[102, 124], [372, 124], [472, 279], [102, 279]], dtype=np.int32)
    colour = cv2.cvtColor(np.uint8([[[cloth_hue, 160, 120]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
    cv2.fillConvexPoly(frame, quad.astype(np.int32), tuple(int(v) for v in colour))
    if occlude is not None:
        for rect in occlude:
            cv2.rectangle(frame, rect[0], rect[1], (60, 60, 60), -1)
    return frame, quad.astype(np.float32)


class DetectorContractTests(unittest.TestCase):
    corners = np.array([[102, 124], [372, 124], [472, 279], [102, 279]], dtype=np.float32)

    def test_dict_contract_is_superset_of_the_naive_one(self):
        frame, quad = bed_frame()
        result = detect_table_refined(frame)
        for key in ('corners', 'mask', 'debug'):
            self.assertIn(key, result)
        for key in ('confidence', 'reason', 'source', 'refined', 'prior', 'debug_info'):
            self.assertIn(key, result)
        self.assertEqual(result['confidence'], 0.4)
        self.assertEqual(result['reason'], 'no_prior')
        self.assertFalse(result['refined'])
        self.assertEqual(result['source'], 'naive')

    def test_dark_frame_is_refused_with_a_reason_not_a_guess(self):
        frame = np.full((360, 640, 3), 12, dtype=np.uint8)
        result = detect_table_refined(frame, prior=self.corners)
        self.assertIsNone(result['corners'])
        self.assertEqual(result['confidence'], 0.0)
        self.assertIn(result['reason'], ('low_cloth_area', 'no_boundary_evidence', 'prior_disagreement'))
        self.assertIsInstance(result['debug_info'], dict)

    def test_blank_frame_without_prior_reports_no_cloth(self):
        frame = np.full((360, 640, 3), 250, dtype=np.uint8)
        result = detect_table_refined(frame)
        self.assertIsNone(result['corners'])
        self.assertEqual(result['reason'], 'no_cloth_area')

    def test_refinement_recovers_a_perturbed_prior(self):
        frame, quad = bed_frame()
        # a prior 12 px out on the two long sides: the refinement pulls both back
        prior = quad + np.array([[0, -12], [0, -12], [0, 12], [0, 12]], dtype=np.float32)
        result = detect_table_refined(frame, prior=prior)
        self.assertIsNotNone(result['corners'], 'a clean synthetic bed must refine')
        self.assertTrue(result['refined'])
        self.assertLess(float(np.linalg.norm(result['corners'] - quad, axis=1).mean()), 6.0)
        self.assertGreater(result['confidence'], 0.0)
        self.assertLessEqual(result['confidence'], 1.0)

    def test_falls_back_to_the_naive_quad_when_the_prior_sees_nothing(self):
        """A prior on the wrong object must not get copied through: the naive
        quad is tried as its own search centre and reported as such."""
        frame, quad = bed_frame()
        far = np.array([[10, 10], [70, 10], [70, 50], [10, 50]], dtype=np.float32)
        result = detect_table_refined(frame, prior=far)
        self.assertIsNotNone(result['corners'])
        self.assertEqual(result['source'], 'refined_naive')
        self.assertLess(float(np.linalg.norm(result['corners'] - quad, axis=1).mean()), 8.0)

    def test_refuses_a_dark_frame_even_with_a_matching_prior(self):
        frame = np.full((360, 640, 3), 15, dtype=np.uint8)
        result = detect_table_refined(frame, prior=self.corners)
        self.assertIsNone(result['corners'])
        self.assertEqual(result['confidence'], 0.0)
        self.assertIn(result['reason'], ('low_cloth_area', 'no_boundary_evidence', 'prior_disagreement'))

    def test_occlusion_leaves_the_untouched_sides_measured(self):
        frame, quad = bed_frame(occlude=[((120, 250), (520, 300))])  # bottom rail covered
        result = detect_table_refined(frame, prior=quad)
        self.assertIsNotNone(result['corners'])
        held = result['debug_info'].get('held_sides') or []
        self.assertTrue(all(entry['side'] in (0, 1, 2, 3) for entry in held))
        self.assertLessEqual(len(held), 3, 'at least one side must be measured')

    def test_prior_is_never_returned_unchecked(self):
        frame, _ = bed_frame()
        prior = np.array([[4, 4], [636, 4], [636, 356], [4, 356]], dtype=np.float32)
        quad, info = refine_quad_edges(frame, prior)
        self.assertIsNone(quad)
        self.assertEqual(info['confidence'], 0.0)
        self.assertIsNotNone(info['reason'])

    def test_priors_load_with_provenance(self):
        priors = load_priors()
        self.assertIn('vod30', priors)
        self.assertIn('highlight', priors)
        for entry in priors.values():
            if entry['quad'] is not None:
                self.assertEqual(np.asarray(entry['quad']).shape, (4, 2))
                self.assertTrue(entry['source'])

    def test_naive_detector_is_unchanged(self):
        """The other callers keep the old dict; detect_table must still work."""
        frame, _ = bed_frame()
        plain = detect_table(frame)
        self.assertEqual(set(plain), {'corners', 'mask', 'debug'})
        self.assertIsNotNone(plain['corners'])


class RecordedReferenceTests(unittest.TestCase):
    """The vod30 improvement, pinned on the recorded artifact when present."""

    def setUp(self):
        if not (ROOT / 'out' / 'corners_30min_v2.json').is_file():
            self.skipTest('out/corners_30min_v2.json is not present')
        video = ROOT / 'data' / 'vod_30min_260815.mp4'
        if not video.is_file():
            self.skipTest('vod30 is not present')
        self.video = video

    def frame_at(self, t):
        cap = cv2.VideoCapture(str(self.video))
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            self.skipTest(f'cannot decode vod30 at t={t}')
        return frame

    def test_refinement_beats_the_naive_quad_on_a_recorded_frame(self):
        with open(ROOT / 'out' / 'corners_30min_v2.json') as handle:
            reference = np.asarray(json.load(handle)['corners'], np.float32)
        frame = self.frame_at(70)
        naive = np.asarray(detect_table(frame)['corners'], np.float32)
        refined = detect_table_refined(frame, prior=prior_for('vod30'))
        self.assertIsNotNone(refined['corners'])
        naive_err = float(np.linalg.norm(naive - reference, axis=1).mean())
        refined_err = float(np.linalg.norm(refined['corners'] - reference, axis=1).mean())
        self.assertLess(refined_err, naive_err)
        self.assertLess(refined_err, 20.0)


if __name__ == '__main__':
    unittest.main()
