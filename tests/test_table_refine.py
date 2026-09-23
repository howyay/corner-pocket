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
from src.table_detect import _order_corners
from src.table_refine import (detect_table_refined, load_priors, prior_for, refine_quad_edges)

ROOT = Path(__file__).resolve().parent.parent


def bed_frame(quad=None, occlude=None, cloth_bgr=(150, 100, 50), rail_px=30):
    """Synthetic 640x360 frame shaped like the vod30 geometry.

    The bed covers ~9.5% of the frame, the same fraction the saved vod30 quad
    covers, so the app's quad-sanity rules (2%-90% area, inside the frame) behave
    here exactly as they do on the recording.  Brightness is ordered the way the
    real frames are - cloth (gray ~93) brighter than the rail band (~55), bright
    outside (~160) - because the detector requires that rail signature before it
    will call a crossing a table boundary.
    """
    w, h = 640, 360
    frame = np.full((h, w, 3), 160, dtype=np.uint8)                 # bright outside
    if quad is None:
        quad = np.array([[102, 124], [372, 124], [472, 279], [102, 279]], dtype=np.int32)
    # A rail band of constant width: offset each side line outward by rail_px and
    # intersect neighbours (a centroid-scaled quad would give a band that is thick
    # on the long sides and thin on the short ones).
    q = quad.astype(np.float64)
    centre = q.mean(axis=0)
    lines = []
    for i in range(4):
        a, b = q[i], q[(i + 1) % 4]
        d = b - a
        d = d / max(float(np.linalg.norm(d)), 1e-9)
        nrm = np.array([-d[1], d[0]])
        if np.dot(nrm, (a + b) / 2.0 - centre) < 0:
            nrm = -nrm
        lines.append((a + nrm * rail_px, d))
    rail = []
    for i in range(4):
        p1, d1 = lines[i]
        p2, d2 = lines[(i + 1) % 4]
        m = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]])
        t = np.linalg.solve(m, p2 - p1)
        rail.append(p1 + t[0] * d1)
    cv2.fillConvexPoly(frame, np.asarray(rail, np.int32), (55, 55, 55))      # dark rail
    cv2.fillConvexPoly(frame, quad.astype(np.int32), tuple(int(v) for v in cloth_bgr))
    if occlude is not None:
        # A body is mid-brightness: it must not look like a rail band, and it must
        # not offer the dark-rail + bright-outside signature either.
        for rect in occlude:
            cv2.rectangle(frame, rect[0], rect[1], (112, 112, 112), -1)
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

    def test_one_iteration_advances_the_measured_offset_in_real_pixels(self):
        """The step size is the measurement, converted once and expressed in real
        pixels (regression: the step was divided by the mask scale, so each
        iteration advanced half of what it had just measured)."""
        from src.table_refine import _MAX_MOVE_PX
        frame, quad = bed_frame()
        offset = 10.0
        prior = quad + np.array([[0, -offset], [0, -offset], [0, offset], [0, offset]], dtype=np.float32)
        one, info = refine_quad_edges(frame, prior, iters=1)
        self.assertIsNotNone(one, f'clean bed refused: {info.get("reason")}')
        moved = abs(float(one[0][1] - prior[0][1]))
        self.assertGreater(moved, min(offset, _MAX_MOVE_PX) - 1.5,
                           f'one iteration moved only {moved:.1f} px of a {offset:.0f} px offset')
        self.assertLessEqual(moved, _MAX_MOVE_PX + 0.01, 'the cap must be the real-pixel cap')
        two, _ = refine_quad_edges(frame, prior, iters=2)
        self.assertLess(float(np.linalg.norm(np.asarray(two) - quad, axis=1).mean()), 1.5,
                        'two iterations must converge on a clean bed')

    def test_a_corner_dragged_off_the_cloth_is_either_refused_or_verified(self):
        """Corner-level damage leaves the side *lines* intact, so a good recovery is
        legitimate - but any accepted quad must account for all four sides, and any
        refusal must carry no corners."""
        frame, quad = bed_frame()
        prior = quad.copy()
        prior[0] += np.array([40, 0], dtype=np.float32)
        prior[2] += np.array([80, 0], dtype=np.float32)
        result = detect_table_refined(frame, prior=prior)
        if result['corners'] is None:
            self.assertEqual(result['confidence'], 0.0)
            self.assertIsNotNone(result['reason'])
            return
        info = result['debug_info']
        info = info if 'verified_sides' in info else (info.get('tried') or [{}])[0].get('info', {})
        self.assertEqual(info.get('verified_sides', 0) + len(info.get('inherited_sides') or []), 4)
        if info.get('inherited_sides'):
            self.assertLess(result['confidence'], 0.8)
        else:
            self.assertLess(float(np.linalg.norm(np.asarray(result['corners']) - quad, axis=1).mean()), 8.0)

    def test_side_verification_is_reported_per_side(self):
        """Every accepted quad names which sides were measured and which inherited
        the prior, and any side that is neither refuses the frame."""
        frame, quad = bed_frame()
        result = detect_table_refined(frame, prior=quad)
        self.assertIsNotNone(result['corners'])
        info = result['debug_info']
        self.assertEqual(info.get('verified_sides'), 4)
        self.assertEqual(info.get('inherited_sides'), [])
        for side in info['sides']:
            self.assertTrue(side.get('verified'))
            self.assertIsNotNone(side.get('mask_band_peak'))

    def test_occlusion_marks_the_covered_side_instead_of_failing(self):
        """A covered side has no evidence of its own and no contradiction, so it
        inherits the prior and is reported - or the frame refuses. What must not
        happen is a silent full-confidence answer."""
        frame, quad = bed_frame(occlude=[((0, 124), (639, 320))])   # bottom rail blocked
        result = detect_table_refined(frame, prior=quad)
        if result['corners'] is None:
            self.assertEqual(result['confidence'], 0.0)
            self.assertIsNotNone(result['reason'])
        else:
            info = result['debug_info']
            self.assertLess(info.get('verified_sides'), 4)
            self.assertTrue(info.get('inherited_sides'))
            self.assertLess(result['confidence'], 0.8)

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

    def test_refinement_agrees_with_the_hand_anchors_on_a_recorded_frame(self):
        """vod30 is seeded from the six hand anchors and scored against them.

        The previous version of this test scored against ``corners_30min_v2.json``
        after seeding from that same file - a self-score.  The anchors track the
        visible cloth edge (left rail x=520 at y=330 -> x=381 at y=560); the v2 left
        rail is a vertical x=450, so agreement with the anchors is the signal.
        """
        with open(ROOT / 'out' / 'pid_anchors_vod30.json') as handle:
            anchors_raw = json.load(handle)['anchors']
        key = sorted(anchors_raw, key=float)[0]
        anchors = _order_corners(np.asarray(anchors_raw[key][:4], np.float32))
        frame = self.frame_at(70)
        naive = np.asarray(detect_table(frame)['corners'], np.float32)
        refined = detect_table_refined(frame, prior=prior_for('vod30'))
        self.assertIsNotNone(refined['corners'])
        naive_err = float(np.linalg.norm(_order_corners(naive) - anchors, axis=1).mean())
        refined_err = float(np.linalg.norm(_order_corners(refined['corners']) - anchors, axis=1).mean())
        self.assertLess(refined_err, naive_err)
        self.assertLess(refined_err, 15.0)
        info = refined['debug_info']
        self.assertEqual(info.get('verified_sides', 0) + len(info.get('inherited_sides') or []), 4)
