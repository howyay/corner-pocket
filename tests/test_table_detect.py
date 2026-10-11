"""A failed cloth segmentation must not be published as a measured table.

The historical VODs that the playfield check refused all had one thing in common: the fitted
quadrilateral listed the same corner twice, so it was a thin wedge rather than a table.  The fit
is where that is known, so the fit is where it is refused.

    .venv/bin/python -m unittest tests.test_table_detect
"""
import ast
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.table_detect import corners_are_distinct, fit_quadrilateral

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"


def _returns_the_owner(value):
    """True when this expression calls the one owner of the corner order."""
    for node in ast.walk(value):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "_order_corners":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "_order_corners":
                return True
    return False


def _adapter_functions(tree):
    """Functions whose whole body is an optional import and one return of the owner's result."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = [s for s in node.body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                        and isinstance(s.value.value, str))]
        returns = [s for s in body if isinstance(s, ast.Return)]
        imports = [s for s in body if isinstance(s, (ast.Import, ast.ImportFrom))]
        if len(returns) == 1 and len(imports) == len(body) - 1 and _returns_the_owner(returns[0].value):
            yield node


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


class CornerOrderHomeTests(unittest.TestCase):
    """One home for the corner order: src/table_detect.py `_order_corners` (round 59).

    A two-line adapter stood in src/eval_table_detect.py and src/table_refine.py.  Its body only
    returned the owner's result.  Round 59 deleted both adapters, and the callers read the owner.
    This case fails when an adapter body comes back, under any name.
    """

    # The two modules that the round 59 repair changed.  Each one reads the owner directly.
    MODULES = ("eval_table_detect.py", "table_refine.py")

    def test_no_adapter_body_stands_in_the_two_modules(self):
        adapters = []
        for name in self.MODULES:
            path = SOURCE_DIR / name
            for node in _adapter_functions(ast.parse(path.read_text())):
                adapters.append(f"{path}:{node.lineno}: def {node.name}")
        self.assertEqual(
            [], adapters,
            "an adapter body for the corner order stands here: " + "; ".join(adapters)
            + ".  Make the caller read src.table_detect._order_corners instead.")

    def test_both_modules_read_the_owner_of_the_corner_order(self):
        for name in self.MODULES:
            path = SOURCE_DIR / name
            self.assertIn("from src.table_detect import _order_corners", path.read_text(),
                          f"{path} does not read the owner of the corner order")


if __name__ == '__main__':
    unittest.main()
