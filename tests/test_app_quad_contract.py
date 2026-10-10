"""The contract between the python quad rule and the browser copy in app.js.

``src.eval_table_detect`` owns the rule.  ``annotator/app.js`` holds the browser
copy: ``quadSanity`` rejects a quad, ``clothTolerance`` sets the mean-distance
bar, and ``validateCloth`` applies both.  Nothing ties the two copies together
except the agreement this module tests.  The numbers and the reason words are
therefore read back out of the app.js source text.

The idiom is the one ``tests/test_app_timeline.js`` uses for the live failure
codes: read the other language's source, compare it, never edit it.

Two differences are known and measured.  The last two cases pin them, so that
neither side can move without a failure:

  * the area formula - the shoelace sum of the app.js ``quadSanity`` against
    ``quad_area_px``,
  * the frame-size guard - the app.js ``quadSanity`` frame-size guard against the
    missing guard.

Every other case asserts agreement, and each one was measured before it was
written.
"""
import re
import unittest
from pathlib import Path

import numpy as np

from src import check_app_quad
from src.eval_table_detect import (CLOTH_TOLERANCE_MM_PER_PX, CLOTH_TOLERANCE_PX,
                                   SANITY_AREA_FRACTION_MAX, SANITY_AREA_FRACTION_MIN,
                                   SANITY_EDGE_MARGIN_PX, SANITY_MIN_CORNER_PX,
                                   SANITY_REASONS, cloth_tolerance, quad_area_px,
                                   quad_distance, quad_sanity)

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / 'annotator' / 'app.js'
APP_JS_TEXT = APP_JS.read_text(encoding='utf-8')

# The frame of the vod30 saved reference, and the quad the app compares against
# (out/pid_anchors_vod30.json, the first four of six hand anchors).  The same
# values are literals in tests/test_app_path_prior.py:22.
REF_WIDTH, REF_HEIGHT = 1280, 720
ANCHOR_QUAD = [[532.0, 323.0], [800.0, 324.0], [997.0, 569.0], [384.0, 563.0]]
# The counterexample of docs/table-detect-verification.md:249, which that
# document reports as accepted at 11.67 px mean.
DOC_QUAD = [[531.0, 325.0], [800.0, 322.0], [979.0, 547.0], [385.0, 549.0]]
# A symmetric bowtie: the two diagonals cross at the frame centre.
BOWTIE_QUAD = [[400.0, 200.0], [900.0, 600.0], [900.0, 200.0], [400.0, 600.0]]


def _body(name):
    """Return the source text between the braces of ``function name(``.

    The braces of a template literal are balanced, so a plain depth count is
    enough for the four functions this module reads.
    """
    head = APP_JS_TEXT.index('function ' + name + '(')
    start = APP_JS_TEXT.index('{', head)
    depth = 0
    for i in range(start, len(APP_JS_TEXT)):
        if APP_JS_TEXT[i] == '{':
            depth += 1
        elif APP_JS_TEXT[i] == '}':
            depth -= 1
            if depth == 0:
                return APP_JS_TEXT[start + 1:i]
    raise AssertionError(f'the body of {name} does not close in {APP_JS}')


QUAD_SANITY_BODY = _body('quadSanity')


def _app_reasons():
    """Return the rejection reasons of ``quadSanity``, in source order.

    Only the words are read.  The last reason carries the covered percentage, so
    it is cut at the template placeholder.
    """
    reasons = []
    for value in re.findall(r'return\s+([^;]+);', QUAD_SANITY_BODY):
        value = value.strip()
        if value.startswith("'"):
            reason = value.strip("'")
        elif '`' in value:
            reason = value.split('`')[1].split('${')[0].rstrip()
        else:
            continue
        if reason and (not reasons or reasons[-1] != reason):
            reasons.append(reason)
    return reasons


def _app_shoelace_px(quad):
    """Return the px^2 area of the expression in the app.js ``quadSanity``.

    This is the shoelace sum over the vertices in the order given.  It is here
    to measure the difference against :func:`quad_area_px`, not to replace it.
    """
    return abs(sum(quad[i][0] * quad[(i + 1) % 4][1] - quad[(i + 1) % 4][0] * quad[i][1]
                   for i in range(4))) / 2.0


class AppQuadContractTests(unittest.TestCase):
    """The python rule and the app.js rule must name the same things."""

    def test_app_js_still_holds_the_rule_the_contract_names(self):
        """The rule moved means this module is stale and must be read again."""
        for needle in ('function quadSanity(points, width, height)',
                       'const CLOTH_TOLERANCE_PX = 40;',
                       'function clothTolerance(reference, frameWidth)',
                       'function validateCloth(corners, reference, frameWidth, frameHeight)',
                       'const bad = quadSanity(points, frameWidth, frameHeight);'):
            self.assertIn(needle, APP_JS_TEXT,
                          f'{needle!r} is not in {APP_JS} any more. The rule moved, so this '
                          'contract is stale.')

    def test_rejection_reasons_and_their_order_match(self):
        """app.js must name the same reasons, in the same order, as SANITY_REASONS."""
        self.assertEqual(_app_reasons(), list(SANITY_REASONS))

    def test_python_rule_emits_the_reasons_in_that_order(self):
        """One input per gate. The four inputs are the ones of the browser test."""
        cases = [(None, 'malformed'),
                 ([[1, 2], [3, 4], [5, 6]], 'malformed'),
                 ([[-10, 0], [2000, 0], [2000, 2000], [0, 2000]], 'outside frame'),
                 ([[100, 100], [110, 100], [110, 105], [100, 100]], 'degenerate corner'),
                 ([[10, 10], [20, 10], [20, 20], [10, 20]], 'implausible area')]
        got = []
        for points, _ in cases:
            reason = quad_sanity(points, REF_WIDTH, REF_HEIGHT)
            self.assertIsNotNone(reason, f'{points} must be rejected')
            got.append('implausible area' if reason.startswith('implausible') else reason)
        self.assertEqual(got, [reason for _, reason in cases])

    def test_sanity_numbers_match_app_js(self):
        """The four gates must carry the same numbers on both sides."""
        margin_lo = re.search(r'x < -(\d+)', QUAD_SANITY_BODY)
        margin_hi = re.search(r'x > w \+ (\d+)', QUAD_SANITY_BODY)
        corner = re.search(r'Math\.hypot\(a\[0\] - b\[0\], a\[1\] - b\[1\]\) < (\d+)',
                           QUAD_SANITY_BODY)
        bounds = re.search(r'fraction >= ([\d.]+) && fraction <= ([\d.]+)', QUAD_SANITY_BODY)
        for label, hit in (('margin lo', margin_lo), ('margin hi', margin_hi),
                           ('corner gap', corner), ('area bounds', bounds)):
            self.assertIsNotNone(hit, f'the {label} of quadSanity changed in {APP_JS}')
        self.assertEqual(float(margin_lo.group(1)), SANITY_EDGE_MARGIN_PX)
        self.assertEqual(float(margin_hi.group(1)), SANITY_EDGE_MARGIN_PX)
        self.assertEqual(float(corner.group(1)), SANITY_MIN_CORNER_PX)
        self.assertEqual(float(bounds.group(1)), SANITY_AREA_FRACTION_MIN)
        self.assertEqual(float(bounds.group(2)), SANITY_AREA_FRACTION_MAX)

    def test_cloth_tolerance_is_40_px(self):
        """The mean-distance bar is one number, and both sides must name 40."""
        hit = re.search(r'const CLOTH_TOLERANCE_PX = (\d+);', APP_JS_TEXT)
        self.assertIsNotNone(hit, f'CLOTH_TOLERANCE_PX is not a literal in {APP_JS}')
        self.assertEqual(float(hit.group(1)), CLOTH_TOLERANCE_PX)
        self.assertEqual(CLOTH_TOLERANCE_PX, 40.0)

    def test_scale_is_1_9_mm_per_px(self):
        """The scale exists only in the app.js comment, so it is read from there."""
        self.assertIn('1.9 mm/px', APP_JS_TEXT)
        hit = re.search(r'40 px \(~(\d+) mm at the documented 1\.9 mm/px\)', APP_JS_TEXT)
        self.assertIsNotNone(hit,
                             f'the 40 px comment changed in {APP_JS}, so the scale of the rule '
                             'is no longer stated')
        self.assertEqual(CLOTH_TOLERANCE_MM_PER_PX, 1.9)
        self.assertEqual(round(CLOTH_TOLERANCE_PX * CLOTH_TOLERANCE_MM_PER_PX),
                         float(hit.group(1)))

    def test_wider_frame_threshold_matches_app_js(self):
        """The bar follows the frame width, so a 1920 px frame gets 60 px."""
        body = _body('clothTolerance')
        self.assertIn('CLOTH_TOLERANCE_PX * (width / base)', body)
        self.assertRegex(body, r'Number\.isFinite\(base\) && base > 0')
        self.assertRegex(body, r'Number\.isFinite\(width\) && width > 0')
        self.assertEqual(cloth_tolerance(REF_WIDTH, 1920), 60.0)
        self.assertEqual(cloth_tolerance(REF_WIDTH, REF_WIDTH), CLOTH_TOLERANCE_PX)
        self.assertAlmostEqual(cloth_tolerance(1920, REF_WIDTH),
                               CLOTH_TOLERANCE_PX * (REF_WIDTH / 1920))
        # app.js returns the bare bar when a width is missing or not above 0.
        for bad in (None, 0, -1, float('nan')):
            self.assertEqual(cloth_tolerance(bad, 1920), CLOTH_TOLERANCE_PX)
            self.assertEqual(cloth_tolerance(REF_WIDTH, bad), CLOTH_TOLERANCE_PX)

    def test_the_browser_test_file_pins_the_same_two_numbers(self):
        """tests/test_app_timeline.js is the third witness of 40 px and 60 px."""
        timeline = (ROOT / 'tests' / 'test_app_timeline.js').read_text(encoding='utf-8')
        self.assertIn('assert.strictEqual(T.CLOTH_TOLERANCE_PX, 40);', timeline)
        self.assertIn('assert.strictEqual(T.clothTolerance(reference, 1920), 60);', timeline)
        # That browser case passes a reference 1280 px wide, which is what the
        # 60 implies: 40 * 1920 / 1280.
        self.assertEqual(cloth_tolerance(1280, 1920), 60.0)

    def test_quad_distance_matches_app_js_best_of_four(self):
        """The app scores the best of four cyclic alignments, then their mean."""
        body = _body('quadDistance')
        self.assertIn('for (let shift = 0; shift < 4; shift++)', body)
        self.assertIn('(i + shift) % 4', body)
        self.assertIn('mean < best.mean', body)
        fit = quad_distance(DOC_QUAD, ANCHOR_QUAD)
        self.assertIn(fit['shift'], range(4))
        means = []
        for shift in range(4):
            d = np.linalg.norm(np.asarray(ANCHOR_QUAD)
                               - np.roll(np.asarray(DOC_QUAD), -shift, axis=0), axis=1)
            means.append(float(d.mean()))
        self.assertAlmostEqual(fit['mean'], min(means), places=9)
        self.assertAlmostEqual(fit['max'], max(float(np.linalg.norm(
            np.asarray(ANCHOR_QUAD)[i] - np.asarray(DOC_QUAD)[(i + fit['shift']) % 4], axis=0))
            for i in range(4)), places=9)

    def test_the_documented_counterexample_quad_still_passes(self):
        """docs/table-detect-verification.md:249 gives this quad, :16 accepts it."""
        fit = quad_distance(DOC_QUAD, ANCHOR_QUAD)
        self.assertIsNone(quad_sanity(DOC_QUAD, REF_WIDTH, REF_HEIGHT))
        self.assertLessEqual(fit['mean'], CLOTH_TOLERANCE_PX)
        self.assertAlmostEqual(fit['mean'], 11.6743, places=3)
        self.assertEqual(fit['distances'], [2.2, 2.0, 28.4, 14.0])

    def test_both_python_modules_expose_one_rule(self):
        """check_app_quad applies the owner's rule; it must not hold a copy."""
        self.assertIs(check_app_quad.quad_sanity, quad_sanity)
        self.assertIs(check_app_quad.quad_distance, quad_distance)
        self.assertIs(check_app_quad.CLOTH_TOLERANCE_PX, CLOTH_TOLERANCE_PX)

    def test_area_formula_divergence_is_pinned_not_agreed(self):
        """KNOWN DIVERGENCE. The two sides do not agree here, and this case says so.

        the app.js ``quadSanity`` uses the shoelace sum over the vertices in the order given.
        quad_area_px uses the triangle pair (p0, p1, p3) and (p0, p3, p2).  The
        values agree for a convex quad and differ for a self-intersecting one.
        Fix the python side, or move app.js, and this case must be re-measured.
        """
        self.assertAlmostEqual(_app_shoelace_px(ANCHOR_QUAD), 106735.5, places=1)
        self.assertAlmostEqual(quad_area_px(ANCHOR_QUAD), 106238.0, places=1)
        self.assertAlmostEqual(_app_shoelace_px(ANCHOR_QUAD) / (REF_WIDTH * REF_HEIGHT),
                               0.115815, places=6)
        self.assertAlmostEqual(quad_area_px(ANCHOR_QUAD) / (REF_WIDTH * REF_HEIGHT),
                               0.115276, places=6)
        # A convex quad agrees, so the difference is not a difference of units.
        convex = [[300.0, 200.0], [1000.0, 220.0], [980.0, 600.0], [280.0, 580.0]]
        self.assertAlmostEqual(_app_shoelace_px(convex), quad_area_px(convex), places=6)
        # The bowtie: app.js rejects it, this checkout accepts it.
        self.assertAlmostEqual(_app_shoelace_px(BOWTIE_QUAD), 0.0, places=6)
        self.assertIsNone(quad_sanity(BOWTIE_QUAD, REF_WIDTH, REF_HEIGHT))
        self.assertGreater(quad_area_px(BOWTIE_QUAD) / (REF_WIDTH * REF_HEIGHT), 0.2)

    def test_frame_size_guard_divergence_is_pinned_not_agreed(self):
        """KNOWN DIVERGENCE. app.js guards the frame size first, python does not.

        the app.js ``quadSanity`` returns 'malformed' when the frame width or the
        frame height is not above 0.  quad_sanity has no such guard, so it
        reaches 'outside frame' instead.  Fix the python side, or move app.js,
        and this case must be re-measured.
        """
        self.assertIn("w <= 0 || h <= 0) return 'malformed';", APP_JS_TEXT)
        for width, height in ((0, 0), (REF_WIDTH, 0), (0, REF_HEIGHT),
                              (-REF_WIDTH, REF_HEIGHT)):
            self.assertEqual(quad_sanity(ANCHOR_QUAD, width, height), 'outside frame')


if __name__ == '__main__':
    unittest.main()
