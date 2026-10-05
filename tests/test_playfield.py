"""The playfield's own geometry: what a detection may claim, and why a quad is refused."""
import math
import unittest

from src.playfield import (POCKET_CORNER_IN, POCKET_SIDE_IN, PLAYFIELD_IN, check_quad,
                           parallelism, pocket_positions_playfield, quad_sides)


class PlayfieldConstraint(unittest.TestCase):
    def test_the_published_table_is_the_one_we_constrain_to(self):
        self.assertEqual(PLAYFIELD_IN, (100.0, 50.0))
        self.assertEqual(POCKET_CORNER_IN, 4.5)
        self.assertEqual(POCKET_SIDE_IN, 5.0)

    def test_a_view_down_one_axis_keeps_that_pair_parallel(self):
        # A trapezoid is exactly the shape a perspective view of a rectangle makes when one pair of
        # edges is parallel to the image plane: that pair stays parallel, the other carries the
        # parallax. (Parallel short edges *and* converging long edges is impossible - it forces a
        # parallelogram - which is why the venue quad below keeps the long pair parallel.)
        quad = [(120.0, 60.0), (1080.0, 60.0), (1100.0, 620.0), (60.0, 620.0)]
        par = parallelism(quad)
        self.assertLess(min(par.values()), 3.0, 'one pair reads parallel')
        self.assertGreater(max(par.values()), 1.0, 'and the other pair carries the perspective')
        verdict = check_quad(quad)
        self.assertTrue(verdict['ok'], verdict['reasons'])
        self.assertEqual(verdict['metrics']['best_parallel_deg'], round(min(par.values()), 2))
        self.assertGreater(verdict['metrics']['aspect'], 1.6, 'a 2:1 playfield does not read as a square')

    def test_a_quad_with_no_parallel_pair_is_refused(self):
        quad = [(100.0, 60.0), (1100.0, 140.0), (1040.0, 620.0), (160.0, 500.0)]
        verdict = check_quad(quad, parallel_tol=1.0)
        self.assertFalse(verdict['ok'])
        self.assertIn('no-parallel-pair', verdict['reasons'])

    def test_a_square_claim_is_refused_even_when_it_is_parallel(self):
        verdict = check_quad([(0.0, 0.0), (600.0, 0.0), (600.0, 600.0), (0.0, 600.0)])
        self.assertFalse(verdict['ok'])
        self.assertIn('aspect-too-square', verdict['reasons'])
        self.assertEqual(verdict['metrics']['aspect'], 1.0)

    def test_a_folded_quad_is_refused(self):
        verdict = check_quad([(0.0, 0.0), (600.0, 0.0), (0.0, 600.0), (600.0, 600.0)])
        self.assertFalse(verdict['ok'])
        self.assertIn('not-convex', verdict['reasons'])

    def test_a_degenerate_or_wrong_arity_quad_is_refused_with_a_reason(self):
        self.assertEqual(check_quad([(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)])['reasons'], ['degenerate'])
        self.assertEqual(check_quad([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)])['reasons'], ['not-four-corners'])

    def test_a_projected_playfield_passes_at_a_range_of_poses(self):
        # Project a 100x50 rectangle through a simple pinhole camera, one axis roughly aligned with
        # the image plane, and check the constraint accepts it every time.
        w, h = PLAYFIELD_IN
        f = 700.0
        accepted = 0
        for tilt_deg in (10, 20, 30, 40):
            for height_in in (80, 120, 180):
                t = math.radians(tilt_deg)
                pts = []
                for x_in, y_in in ((0, 0), (w, 0), (w, h), (0, h)):
                    x = (x_in - w / 2) / 100.0
                    y = (y_in - h / 2) / 100.0
                    X = x
                    Y = y * math.cos(t) - (height_in / 100.0) * math.sin(t)
                    Z = y * math.sin(t) + (height_in / 100.0) * math.cos(t)
                    pts.append((f * X / Z + 640, f * Y / Z + 360))
                verdict = check_quad(pts)
                self.assertTrue(verdict['ok'], f'tilt {tilt_deg} height {height_in}: {verdict["reasons"]} {verdict["metrics"]}')
                accepted += 1
        self.assertEqual(accepted, 12)

    def test_the_pocket_layout_is_the_published_one(self):
        pk = pocket_positions_playfield()
        self.assertEqual(pk['corners'], [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)])
        self.assertEqual(pk['sides'], [(50.0, 0.0), (50.0, 50.0)])

    def test_sides_come_back_in_the_order_the_caller_gave_them(self):
        s = quad_sides([(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)])
        self.assertEqual(s['top'], ((0.0, 0.0), (10.0, 0.0)))
        self.assertEqual(s['right'], ((10.0, 0.0), (10.0, 5.0)))
        self.assertEqual(s['bottom'], ((10.0, 5.0), (0.0, 5.0)))
        self.assertEqual(s['left'], ((0.0, 5.0), (0.0, 0.0)))


if __name__ == '__main__':
    unittest.main()
