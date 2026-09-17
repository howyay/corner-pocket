"""Info-complete gate and matched-ball diff tests; no model loads."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.info_complete_scan import (GateConfig, ICState, gate_reason,  # noqa: E402
                                    match_balls, to_table_mm, _pair_candidates,
                                    _quad_box_overlap_area)
from src.pipeline import homography_to_canonical, CANON_W, CANON_H  # noqa: E402

CORNERS = np.array([[0, 0], [640, 0], [640, 360], [0, 360]], np.float32)
H = homography_to_canonical(CORNERS)


def ball(color, cx, cy, r=10.0):
    return {'color': color, 'cx': float(cx), 'cy': float(cy), 'r': r}


class GateTests(unittest.TestCase):
    def setUp(self):
        self.state = ICState()
        self.state.cloth_ref = 150000.0
        self.state.last_brightness = 100.0
        self.state.census = [5] * 12
        self.mask = np.zeros((540, 960), np.uint8)
        self.mask[100:400, 200:700] = 1

    def test_clean_frame_is_info_complete(self):
        self.assertIsNone(gate_reason(self.state, None, None, self.mask,
                                      persons_on_table=False, n_balls=5,
                                      brightness=101.0, cfg=GateConfig()))

    def test_person_on_table_blocks(self):
        self.assertEqual(gate_reason(self.state, None, None, self.mask, True, 5,
                                     100.0, GateConfig()), 'person_on_table')

    def test_cloth_area_shrink_blocks(self):
        small = self.mask.copy()
        small[200:400, 300:650] = 0  # drop far beyond 10% band
        reason = gate_reason(self.state, None, None, small, False, 5, 100.0, GateConfig())
        self.assertEqual(reason, 'cloth_area_out_of_band')

    def test_exposure_shift_blocks(self):
        reason = gate_reason(self.state, None, None, self.mask, False, 5, 112.0, GateConfig())
        self.assertEqual(reason, 'exposure_shift')

    def test_ball_census_off_blocks(self):
        # one-sided rule: only a FALLING count (occlusion) blocks the gate
        reason = gate_reason(self.state, None, None, self.mask, False, 1, 100.0, GateConfig())
        self.assertEqual(reason, 'ball_census_off')
        self.assertIsNone(gate_reason(self.state, None, None, self.mask, False, 9, 100.0, GateConfig()))

    def test_warming_up_until_cloth_reference(self):
        state = ICState()
        reason = gate_reason(state, None, None, self.mask, False, 5, 100.0, GateConfig())
        self.assertEqual(reason, 'warming_up')


class MatchTests(unittest.TestCase):
    def test_same_color_nearest_match(self):
        prev = [ball('solid', 100, 100), ball('solid', 400, 300), ball('stripe', 200, 200)]
        cur = [ball('solid', 130, 100), ball('solid', 430, 300), ball('stripe', 205, 200)]
        matched, gone, appeared = match_balls(prev, cur, radius_px=60.0)
        self.assertEqual(len(matched), 3)
        self.assertIn((100.0, 130.0), [(m[0]['cx'], m[1]['cx']) for m in matched])
        self.assertEqual(gone, [])
        self.assertEqual(appeared, [])

    def test_ambiguous_same_color_leftovers_stay_unmatched(self):
        prev = [ball('solid', 100, 100), ball('solid', 140, 100)]
        cur = [ball('solid', 300, 100), ball('solid', 400, 100)]
        matched, gone, appeared = match_balls(prev, cur, radius_px=60.0)
        # two same-color leftovers on each side: assignment is ambiguous
        self.assertEqual(matched, [])
        self.assertEqual(len(gone), 2)
        self.assertEqual(len(appeared), 2)

    def test_unique_color_leftovers_match_at_range(self):
        prev = [ball('solid', 100, 100)]
        cur = [ball('solid', 400, 100)]
        matched, gone, appeared = match_balls(prev, cur, radius_px=60.0)
        self.assertEqual(len(matched), 1)
        self.assertGreater(matched[0][2], 60.0)

    def test_colors_never_cross_match(self):
        prev = [ball('solid', 100, 100)]
        cur = [ball('stripe', 105, 100)]
        matched, gone, appeared = match_balls(prev, cur, radius_px=60.0)
        self.assertEqual(matched, [])


class CandidateTests(unittest.TestCase):
    def test_long_displacement_becomes_shot_candidate(self):
        prev = {'t': 10.0, 'frame_index': 300, 'cands': [{**ball('solid', 100, 100), '_streak': 3}]}
        cur = {'t': 10.5, 'frame_index': 315, 'cands': [{**ball('solid', 460, 100), '_streak': 3}]}
        shots, vanished = _pair_candidates(prev, cur, H, GateConfig(), gap=0.5)
        self.assertEqual(len(shots), 1)
        self.assertGreaterEqual(shots[0]['disp_mm'], 150)
        self.assertGreater(shots[0]['speed_mm_s'], 500)
        self.assertLess(shots[0]['speed_mm_s'], 15000)
        self.assertEqual(vanished, [])

    def test_vanished_ball_becomes_pot_candidate(self):
        prev = {'t': 20.0, 'frame_index': 600, 'cands': [{**ball('solid', 100, 100), '_streak': 4}]}
        cur = {'t': 20.5, 'frame_index': 615, 'cands': []}
        shots, vanished = _pair_candidates(prev, cur, H, GateConfig(), gap=0.5)
        self.assertEqual(shots, [])
        self.assertEqual([v['color'] for v in vanished], ['solid'])
        self.assertIn('color', vanished[0])
        self.assertEqual(vanished[0]['mm'][0], vanished[0]['mm'][0])  # mm mapped
        self.assertNotIn('pairs_missing', vanished[0])  # caller owns persistence state

    def test_small_drift_yields_no_candidate(self):
        prev = {'t': 30.0, 'frame_index': 900, 'cands': [{**ball('solid', 100, 100), '_streak': 3}]}
        cur = {'t': 30.5, 'frame_index': 915, 'cands': [{**ball('solid', 108, 102), '_streak': 3}]}
        shots, vanished = _pair_candidates(prev, cur, H, GateConfig(), gap=0.5)
        self.assertEqual(shots, [])
        self.assertEqual(vanished, [])


class GeometryTests(unittest.TestCase):
    def test_quad_box_overlap_measures_intersection(self):
        quad = np.array([[0, 0], [640, 0], [640, 360], [0, 360]], np.float32)
        inside = np.array([[100, 100], [300, 100], [300, 200], [100, 200]], np.float32)
        outside = np.array([[700, 100], [900, 100], [900, 200], [700, 200]], np.float32)
        self.assertGreater(_quad_box_overlap_area(quad, inside), 0)
        self.assertEqual(_quad_box_overlap_area(quad, outside), 0.0)

    def test_table_mm_maps_inside_canonical(self):
        mm = to_table_mm(H, 320, 180)
        self.assertIsNotNone(mm)
        self.assertTrue(0 <= mm[0] <= CANON_W)
        self.assertTrue(0 <= mm[1] <= CANON_H)


if __name__ == '__main__':
    unittest.main()
