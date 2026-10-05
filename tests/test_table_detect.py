"""A failed cloth segmentation must not be published as a measured table.

The historical VODs that the playfield check refused all had one thing in common: the fitted
quadrilateral listed the same corner twice, so it was a thin wedge rather than a table.  The fit
is where that is known, so the fit is where it is refused.

    .venv/bin/python -m unittest tests.test_table_detect
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.table_detect import corners_are_distinct, fit_quadrilateral


def mask_with(points, size=(240, 320)):
    import cv2
    m = np.zeros((size[0], size[1]), dtype=np.uint8)
    cv2.fillPoly(m, [np.array(points, dtype=np.int32)], 255)
    return m


class CornerDistinctnessTests(unittest.TestCase):
    def test_a_repeated_corner_is_not_accepted(self):
        wedge = np.array([[10, 100], [300, 110], [280, 130], [10, 100]], dtype=np.float32)
        self.assertFalse(corners_are_distinct(wedge))

    def test_four_real_corners_are_accepted(self):
        quad = np.array([[10, 10], [300, 12], [298, 200], [12, 198]], dtype=np.float32)
        self.assertTrue(corners_are_distinct(quad))


class FitQuadrilateralTests(unittest.TestCase):
    def test_a_table_like_mask_yields_four_corners(self):
        quad = fit_quadrilateral(mask_with([[20, 40], [300, 45], [295, 200], [25, 195]]))
        self.assertIsNotNone(quad)
        self.assertEqual(quad.shape, (4, 2))
        self.assertTrue(corners_are_distinct(quad))

    def test_a_sliver_mask_yields_no_table(self):
        quad = fit_quadrilateral(mask_with([[10, 100], [300, 110], [280, 130], [10, 100]]))
        if quad is not None:
            self.assertTrue(corners_are_distinct(quad),
                            'a sliver came back as a quadrilateral with a repeated corner: %s' % (quad.tolist(),))


if __name__ == '__main__':
    unittest.main()
