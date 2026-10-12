"""One home for the cloth-contour preamble of the two quad fitters.

Round 76 measured the same eight statements in two modules: ``fit_quad_v3`` in
``src/quad_fit.py`` and ``fit_quad_lines`` in ``src/quad_fit_lines.py`` read the
tight cloth mask, took the largest external contour, and read the frame size by
hand.  The two copies could disagree, and one of them did: the copy in
``src/quad_fit_lines.py`` imported ``_anchor_hue`` and never used it.

The preamble now stands once, in ``cloth_contours`` of ``src/quad_fit.py``.
``src/quad_fit_lines.py`` reads that function.  Each fitter keeps its own gate:
``fit_quad_v3`` refuses a rectangle whose long side is more than 3.6 times its
short side, and ``fit_quad_lines`` refuses a contour below 40000 pixels.

Run: ``./scripts/pool-test.sh python test_cloth_contour_owner``
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
# the two fitters read each other by bare name (``from quad_fit import ...``),
# as their scripts do, so the case reads them the same way
sys.path.insert(0, str(ROOT / "src"))
OWNER = ROOT / "src" / "quad_fit.py"
FITTERS = (
    ("src/quad_fit.py", "fit_quad_v3"),
    ("src/quad_fit_lines.py", "fit_quad_lines"),
)
# the two calls that only the owner may make
OWNER_CALLS = ("cloth_mask_tight", "findContours")


def function_body(path, name):
    """The statements of one function, without its docstring."""
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = list(node.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            return body
    return None


def calls_in(path, function):
    """Every name called inside one function: a bare name or an attribute."""
    names = set()
    for node in function_body(path, function) or ():
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                if isinstance(sub.func, ast.Name):
                    names.add(sub.func.id)
                elif isinstance(sub.func, ast.Attribute):
                    names.add(sub.func.attr)
    return names


def preamble_offenders(path, function, reads_owner=True):
    """The reasons one fitter spells the preamble by hand, as text lines."""
    names = calls_in(path, function)
    found = [f"{Path(path).name}: {function} calls {call} of its own"
             for call in OWNER_CALLS if call in names]
    if reads_owner and "cloth_contours" not in names:
        found.append(f"{Path(path).name}: {function} does not read cloth_contours")
    return found


def old_preamble(bgr):
    """The preamble the two fitters spelled by hand before round 76.

    The case keeps this text on purpose: it is the copy the repair removed, and
    it must answer the same contour as the owner for one fixture mask.
    """
    from quad_fit import cloth_mask_tight

    mask, _hue = cloth_mask_tight(bgr)
    if mask is None:
        return None
    h, w = bgr.shape[:2]
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    return mask, max(cnts, key=cv2.contourArea), h, w


class ClothContourOwnerTests(unittest.TestCase):
    """The owner answers the contour, and each fitter keeps its own gate."""

    def setUp(self):
        self.frame = np.full((240, 320, 3), 30, np.uint8)
        self.mask = np.zeros((240, 320), np.uint8)
        cv2.rectangle(self.mask, (60, 50), (240, 190), 255, -1)
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def patch_mask(self, mask):
        """Give the owner a fixture mask in the place of the cloth reader."""
        import quad_fit

        original = quad_fit.cloth_mask_tight
        quad_fit.cloth_mask_tight = lambda bgr, *a, **k: (mask, 100)
        self.addCleanup(setattr, quad_fit, "cloth_mask_tight", original)

    def test_the_owner_and_the_old_preamble_answer_the_same_contour(self):
        from quad_fit import cloth_contours

        self.patch_mask(self.mask)
        found = cloth_contours(self.frame)
        old = old_preamble(self.frame)
        self.assertIsNotNone(found, "the owner answered None for the fixture mask")
        self.assertIsNotNone(old, "the old preamble answered None for the fixture mask")
        mask, big, h, w = found
        old_mask, old_big, old_h, old_w = old
        self.assertTrue(np.array_equal(mask, old_mask), "the two masks differ")
        self.assertTrue(np.array_equal(big, old_big), "the two contours differ")
        self.assertEqual((h, w), (old_h, old_w))
        self.assertEqual((h, w), self.frame.shape[:2])
        self.assertEqual(cv2.contourArea(big), cv2.contourArea(old_big))
        self.assertEqual(len(found), 4)

    def test_both_fitters_read_the_one_owner(self):
        import quad_fit
        import quad_fit_lines

        self.assertIs(quad_fit_lines.cloth_contours, quad_fit.cloth_contours,
                      "the two fitters do not read the same function")
        offenders = []
        for path, function in FITTERS:
            offenders += preamble_offenders(ROOT / path, function)
        self.assertEqual(offenders, [], "fitters that spell the preamble: " + ", ".join(offenders))

    def test_the_v3_fitter_keeps_its_own_ratio_gate(self):
        from quad_fit import fit_quad_v3
        from quad_fit_lines import fit_quad_lines

        # a long thin rectangle: v3 refuses it on its own 3.6 ratio gate
        thin = np.zeros((240, 320), np.uint8)
        cv2.rectangle(thin, (10, 110), (310, 130), 255, -1)
        self.patch_mask(thin)
        self.assertIsNone(fit_quad_v3(self.frame), "v3 answered a quad for a thin rectangle")

    def test_the_lines_fitter_keeps_its_own_area_gate(self):
        from quad_fit_lines import fit_quad_lines

        # a small square: v4 refuses it below its own 40000 pixel gate
        small = np.zeros((240, 320), np.uint8)
        cv2.rectangle(small, (100, 100), (140, 140), 255, -1)
        self.patch_mask(small)
        self.assertLess(cv2.contourArea(max(cv2.findContours(small, cv2.RETR_EXTERNAL,
                                                             cv2.CHAIN_APPROX_SIMPLE)[0],
                                             key=cv2.contourArea)), 40000)
        self.assertIsNone(fit_quad_lines(self.frame), "v4 answered a quad below 40000 pixels")

    def test_the_scan_sees_a_planted_copy(self):
        planted = Path(self.tmp.name) / "planted_preamble.py"
        planted.write_text(
            "import cv2\n"
            "\n"
            "\n"
            "def planted(bgr):\n"
            "    mask, hue = cloth_mask_tight(bgr)\n"
            "    if mask is None:\n"
            "        return None\n"
            "    h, w = bgr.shape[:2]\n"
            "    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)\n"
            "    if not cnts:\n"
            "        return None\n"
            "    big = max(cnts, key=cv2.contourArea)\n"
            "    return big\n"
        )
        found = preamble_offenders(planted, "planted", reads_owner=False)
        self.assertEqual(len(found), 2, "the scan did not see the planted calls: " + str(found))
        self.assertTrue(any("cloth_mask_tight" in line for line in found), str(found))
        self.assertTrue(any("findContours" in line for line in found), str(found))


if __name__ == "__main__":
    unittest.main()
