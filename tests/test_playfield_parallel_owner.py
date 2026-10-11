"""One parallelism reading, one reduction: the check owns it and the tool reads it.

``src/playfield.py`` measures two pair angles and reduces them with ``min``, because the rule
needs *one* pair of opposite edges to read parallel.  ``tools/playfield_quad_evidence.py``
measured the same two angles and reduced them again with ``max``, then named a side from that
number.  On the venue quad of ``tests/test_playfield.py`` the two readers disagreed: the check
answered ``ok True, reasons [], best_parallel_deg 0.0`` while the tool read ``8.161`` against
``PARALLEL_TOL_DEG 3.0`` and blamed the tolerance for a quad the service accepts.

These cases hold the repaired shape: the tool takes the reading and the tolerance from the
check, its classification agrees with the check's own verdict for the venue quad and for a
quad that fails the tolerance, and a planted second reduction is reported.

Round 72 gave the cross-product sign of a quad the same treatment.  The rule stood twice, once
in the check and once in the tool, and ``src/playfield.quad_signs`` is the one owner now.  The
tool keeps the name ``convexity_signs`` and reads the owner.
"""
import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.playfield import (PARALLEL_TOL_DEG, check_quad, parallelism,
                           quad_signs)

EVIDENCE_NAME = 'tools/playfield_quad_evidence.py'
TEST_NAME = 'tests/test_playfield.py'
#: The cases the two readers disagreed on: the venue quad, and a quad refused for its pairs.
VENUE_CASE = 'test_a_view_down_one_axis_keeps_that_pair_parallel'
REFUSED_CASE = 'test_a_quad_with_no_parallel_pair_is_refused'
#: The case whose quad the check refuses for its corners and not for its pairs.  Round 72 gave
#: the cross-product sign one owner, ``src.playfield.quad_signs``, and this quad is the one that
#: shows the reason ``not-convex`` and the signs of the owner are one answer.
FOLDED_CASE = 'test_a_folded_quad_is_refused'
#: The failing case needs a tighter threshold, or its second reason hides the pair refusal.
REFUSED_TOL = 1.0
#: The verdict of a quad that the check accepts: the tool has no side to blame.
NO_SIDE_AT_FAULT = 'unclear'
#: The verdict of a refused quad whose reading is far outside its tolerance.
DETECTOR_AT_FAULT = 'detector: edges are not the table edges'
#: The label of a refused quad whose reading lies inside three times its tolerance.  This is the
#: label the tool gave the venue quad before the repair, when it read the larger pair angle.
TOLERANCE_AT_FAULT = 'check: parallel within the detector noise, tolerance may be too tight'


def load_tool():
    """The evidence tool as a module, imported by path with the video decoder blocked.

    ``tools`` is not a package, so a tool loads by path.  An import runs the module body, and
    that body must define names only and open no recording.  The block makes a guard that goes
    missing fail in a moment instead of decoding a VOD, and the saved module goes back before
    any other test can see the block.
    """
    saved = sys.modules.get('cv2')
    blocked = types.ModuleType('cv2')

    def no_vod(*args, **kwargs):
        raise RuntimeError('the import of %s must not open a VOD' % EVIDENCE_NAME)

    blocked.VideoCapture = no_vod
    sys.modules['cv2'] = blocked
    try:
        spec = importlib.util.spec_from_file_location('playfield_quad_evidence_owner_test',
                                                      ROOT / EVIDENCE_NAME)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop('cv2', None)
        else:
            sys.modules['cv2'] = saved
    return module


def quad_from_case(module_name, case_name):
    """The quad literal of one test case, read from the test source with Python's own parse.

    The cases below must measure the quads of ``tests/test_playfield.py`` and not a copy of
    them in this file, so this reads the literal out of that file.
    """
    tree = ast.parse('\n'.join((ROOT / TEST_NAME).read_text(encoding='utf-8').splitlines()))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != module_name:
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != case_name:
                continue
            for step in ast.walk(item):
                if isinstance(step, ast.Assign) and isinstance(step.value, ast.List) \
                        and len(step.value.elts) == 4:
                    return [tuple(ast.literal_eval(point)) for point in step.value.elts]
            # A case may state its quad in the call itself, as the folded quad of round 72
            # does.  The list argument of the first ``check_quad(...)`` call answers then.
            for step in ast.walk(item):
                if not isinstance(step, ast.Call) or not step.args:
                    continue
                if getattr(step.func, 'id', None) != 'check_quad':
                    continue
                first = step.args[0]
                if isinstance(first, ast.List) and len(first.elts) == 4:
                    return [tuple(ast.literal_eval(point)) for point in first.elts]
    raise AssertionError('%s: no 4-point quad literal in %s' % (TEST_NAME, case_name))


def fake_check(quad, parallel_tol=PARALLEL_TOL_DEG):
    """A planted second reading: it reduces the pair angles with ``max``, as the tool did.

    The planted function answers in the shape of the check, so it fits in the check's own
    place.  Its number is the larger pair angle, and a reduction of that number is the defect
    these cases report.
    """
    par = parallelism(quad)
    best = round(max(par.values()), 2)
    return {'ok': best <= parallel_tol,
            'reasons': [] if best <= parallel_tol else ['no-parallel-pair'],
            'metrics': {'best_parallel_deg': best, 'parallel_tol_deg': round(float(parallel_tol), 2)}}


def with_planted_reading(call):
    """Run one call with the tool's ``check_quad`` name replaced by the planted reading.

    The tool calls the check through that module name, so this is the reduction the tool would
    use if the defect came back.  The name goes back before any other test can see it.
    """
    saved = TOOL.check_quad
    TOOL.check_quad = fake_check
    try:
        return call()
    finally:
        TOOL.check_quad = saved


def owner_reading(quad, parallel_tol=PARALLEL_TOL_DEG):
    """What the check itself answers for the quad, and the number it reduced to."""
    verdict = check_quad(quad, parallel_tol=parallel_tol)
    return verdict, verdict['metrics']['best_parallel_deg']


def tool_answer(quad, parallel_tol=PARALLEL_TOL_DEG):
    """The tool's verdict for one quad, through the tool's own functions.

    ``best_check`` reads the verdict, ``parallel_pair_reading`` takes the owner's reading and
    the owner's tolerance out of it, and ``classify`` names the side.  This is the path the
    tool's ``main`` walks, so a second reduction inside any of the three shows up here.
    """
    verdict = TOOL.best_check(quad, parallel_tol=parallel_tol)
    signs = TOOL.convexity_signs(quad)
    angles = TOOL.interior_angles(quad)
    par, par_tol = TOOL.parallel_pair_reading(verdict)
    return TOOL.classify(signs, angles, par, par_tol), par, par_tol


def refused_by(answer):
    """True when a tool verdict says the quad was refused: every verdict but ``unclear``."""
    return answer != NO_SIDE_AT_FAULT


TOOL = load_tool()
VENUE_QUAD = quad_from_case('PlayfieldConstraint', VENUE_CASE)
REFUSED_QUAD = quad_from_case('PlayfieldConstraint', REFUSED_CASE)
FOLDED_QUAD = quad_from_case('PlayfieldConstraint', FOLDED_CASE)


class TheReductionHasOneOwnerTests(unittest.TestCase):
    """The check reduces the pair angles; the tool reads the result and reduces nothing."""

    def test_the_check_records_the_tolerance_it_reduced_with(self):
        """A reader of the verdict must not read a second threshold from its own code."""
        verdict = check_quad(VENUE_QUAD)
        self.assertEqual(verdict['metrics']['parallel_tol_deg'], PARALLEL_TOL_DEG,
                         'the check must record the tolerance it used')
        self.assertEqual(verdict['metrics']['best_parallel_deg'], 0.0,
                         'the venue quad keeps its long pair parallel')
        self.assertLess(verdict['metrics']['best_parallel_deg'],
                        verdict['metrics']['parallel_deg']['short'],
                        'the record keeps the reduced number and the reading apart')

    def test_the_tool_takes_the_reading_and_the_tolerance_from_the_check(self):
        """The tool's number must be the number the check reduced, not a second reduction."""
        verdict = check_quad(VENUE_QUAD)
        par, par_tol = TOOL.parallel_pair_reading(verdict)
        self.assertEqual((par, par_tol),
                         (verdict['metrics']['best_parallel_deg'],
                          verdict['metrics']['parallel_tol_deg']),
                         'the tool must take the reading and the tolerance from the check')
        self.assertEqual(TOOL.parallel_pair_reading({'ok': False, 'reasons': [], 'metrics': {}}),
                         (None, None),
                         'a verdict without the fields must answer with nothing, not a guess')

    def test_a_planted_second_reading_is_reported(self):
        """A reduction with ``max`` inside the tool's path must change the answer it gives.

        The planted check reads the larger pair angle and calls it the best one.  On the venue
        quad that number is outside the tolerance of the same call, and the label names the
        tolerance - for a quad the check accepts.  A guard that reads only the tool's text and
        not its path cannot see this.
        """
        owner_par = check_quad(VENUE_QUAD)['metrics']['best_parallel_deg']
        planted = with_planted_reading(lambda: TOOL.best_check(VENUE_QUAD))
        par, par_tol = TOOL.parallel_pair_reading(planted)
        answer = TOOL.classify(TOOL.convexity_signs(VENUE_QUAD),
                               TOOL.interior_angles(VENUE_QUAD), par, par_tol)
        self.assertEqual(par_tol, PARALLEL_TOL_DEG)
        self.assertGreater(par, par_tol, 'the planted reading calls the venue quad a failure')
        self.assertNotEqual(par, owner_par,
                            'the planted reduction must disagree with the check on this quad')
        self.assertEqual(answer, TOLERANCE_AT_FAULT,
                         'the planted reduction must be visible in the tool answer')

    def test_the_sign_of_a_quad_has_one_owner(self):
        """The check, the tool and the verdict read one sign reader.

        Round 72 measured the tool's copy of this walk on 2026-10-11: it answered
        the same four signs as the check for the ten recorded picks of
        ``out/playfield_quad_evidence.json``, for these three quads and for 20000
        random quads, so one home changes no value.  The folded quad is the one
        that ties the signs to the reason of the verdict, because it is the only
        quad of the three that the check refuses for its corners.
        """
        self.assertEqual(quad_signs(VENUE_QUAD), TOOL.convexity_signs(VENUE_QUAD),
                         'the tool must read the sign of the owner')
        venue = quad_signs(VENUE_QUAD)
        self.assertEqual(len(set(venue)), 1,
                         'every corner of a convex quad turns the same way: %r' % (venue,))
        refused = quad_signs(REFUSED_QUAD)
        self.assertEqual(len(set(refused)), 1,
                         'this quad fails its pairs, and its corners keep one sign: %r'
                         % (refused,))
        folded = quad_signs(FOLDED_QUAD)
        self.assertEqual(len(set(folded)), 2,
                         'a folded quad turns both ways: %r' % (folded,))
        self.assertIn('not-convex', check_quad(FOLDED_QUAD)['reasons'])
        for _name, quad in (('venue', VENUE_QUAD), ('refused', REFUSED_QUAD),
                            ('folded', FOLDED_QUAD)):
            signs = quad_signs(quad)
            self.assertEqual('not-convex' in check_quad(quad)['reasons'],
                             not (set(signs) <= {1} or set(signs) <= {-1}),
                             'the reason of the verdict and the signs are one answer: %r'
                             % (signs,))


class TheToolAgreesWithTheCheckTests(unittest.TestCase):
    """The tool's classification must agree with the verdict the check itself gave."""

    def test_the_venue_quad_agrees_with_the_check(self):
        """The quad of ``tests/test_playfield.py`` is accepted, so the tool cannot blame it."""
        verdict, owner_par = owner_reading(VENUE_QUAD)
        answer, par, par_tol = tool_answer(VENUE_QUAD)
        self.assertTrue(verdict['ok'], verdict['reasons'])
        self.assertEqual(par, owner_par, 'the tool and the check read different numbers')
        self.assertEqual(par, 0.0, 'the venue quad keeps its long pair parallel')
        self.assertEqual(par_tol, PARALLEL_TOL_DEG)
        self.assertEqual(answer, NO_SIDE_AT_FAULT,
                         'the tool answers %r for a quad the check accepts' % (answer,))

    def test_a_quad_that_fails_the_tolerance_agrees_with_the_check(self):
        """A refused quad needs the side at fault, and the tool must read the check's numbers.

        This quad's reading lies inside three times its tolerance, so the label names the
        tolerance - for a quad that the check refuses.  The tool once printed that same label
        for the accepted venue quad because it read the larger pair angle.
        """
        verdict, owner_par = owner_reading(REFUSED_QUAD)
        answer, par, par_tol = tool_answer(REFUSED_QUAD)
        self.assertFalse(verdict['ok'])
        self.assertIn('no-parallel-pair', verdict['reasons'])
        self.assertEqual(par, owner_par, 'the tool and the check read different numbers')
        self.assertEqual(par_tol, PARALLEL_TOL_DEG)
        self.assertTrue(refused_by(answer), 'a refused quad must not read as accepted')
        self.assertLess(par, 3 * par_tol,
                        'this case needs a reading inside three times its tolerance')
        self.assertEqual(answer, TOLERANCE_AT_FAULT,
                         'the label must follow the reading the check reduced')

    def test_the_tool_reads_the_tolerance_the_check_used(self):
        """A caller with another tolerance must get the verdict of that tolerance."""
        verdict, owner_par = owner_reading(REFUSED_QUAD, parallel_tol=REFUSED_TOL)
        answer, par, par_tol = tool_answer(REFUSED_QUAD, parallel_tol=REFUSED_TOL)
        self.assertFalse(verdict['ok'])
        self.assertEqual(par_tol, REFUSED_TOL,
                         'the tool must read the tolerance of the call, not its own constant')
        self.assertEqual(par, owner_par)
        self.assertGreater(par, 3 * par_tol,
                           'this case needs a reading three times outside its tolerance')
        self.assertEqual(answer, DETECTOR_AT_FAULT)

    def test_each_answer_follows_the_reading_the_check_reduced(self):
        """The tool's label must be the label of the check's own number, for both quads.

        The venue quad is accepted, so its label names no side.  The refused quad reads 3.19
        against a tolerance of 3.0, inside three times the tolerance, so its label names the
        tolerance - and the check refuses it.  Before the repair the tool read the larger pair
        angle, 8.161 for the venue quad, and printed the same label for a quad the service
        accepts.  A return of the ``max`` reduction fails the first row in one line.
        """
        for name, quad, tol in (('venue', VENUE_QUAD, PARALLEL_TOL_DEG),
                                ('refused', REFUSED_QUAD, PARALLEL_TOL_DEG)):
            with self.subTest(quad=name):
                verdict, owner_par = owner_reading(quad, parallel_tol=tol)
                answer, par, _ = tool_answer(quad, parallel_tol=tol)
                self.assertEqual(par, owner_par, '%s: two readings of one quad' % name)
                self.assertEqual(bool(verdict['ok']), not refused_by(answer),
                                 '%s: the tool and the check must agree on this quad' % name)
                wanted = NO_SIDE_AT_FAULT if verdict['ok'] else (
                    DETECTOR_AT_FAULT if owner_par > 3 * tol else TOLERANCE_AT_FAULT)
                self.assertEqual(answer, wanted, '%s: the label must follow the reading' % name)

    def test_a_quad_with_one_pair_reading_keeps_the_value_the_tool_printed(self):
        """Where the two pair angles agree, the old reduction and the new one read the same.

        A parallelogram has both pairs parallel, so ``min`` and ``max`` of its pair angles are
        one number.  The record keeps that number, as it did before the repair, and the verdict
        stays ``unclear``.
        """
        square = [(0.0, 0.0), (600.0, 0.0), (600.0, 600.0), (0.0, 600.0)]
        pairs = parallelism(square)
        old = round(float(max(pairs.values())), 2)
        entry = TOOL.pick_entry('square.mp4', 30, 30.0, square,
                                {'ok': False, 'reasons': ['aspect-too-square'], 'metrics': None})
        self.assertEqual(pairs['long'], pairs['short'],
                         'this case needs two pairs that read the same angle')
        self.assertEqual(entry['edge_pair_angle_deg'], old,
                         'an agreeing reduction must keep the value the tool printed')
        self.assertEqual(entry['verdict'], NO_SIDE_AT_FAULT,
                         'the pair rule is not what refuses a square claim')

    def test_the_record_entry_carries_the_check_reading_and_the_check_verdict(self):
        """One pick of the record, built without a recording, as the tool builds it now.

        The entry is the tool's own function for one pick, and ``payload`` is the field set the
        served stage publishes beside the quad.  Before the repair this entry held the larger
        pair angle and the tolerance verdict for the venue quad.
        """
        payload = {'ok': True, 'reasons': [],
                   'best_parallel_deg': 0.0, 'aspect': 1.727}
        entry = TOOL.pick_entry('fixture.mp4', 30, 30.0, VENUE_QUAD, payload)
        self.assertEqual(entry['edge_pair_angle_deg'], 0.0,
                         'the entry must carry the number the check reduced')
        self.assertEqual(entry['parallel_tol_deg'], PARALLEL_TOL_DEG)
        self.assertEqual(entry['verdict'], NO_SIDE_AT_FAULT,
                         'the entry must not blame the tolerance for an accepted quad')
        self.assertEqual(entry['check_ok'], payload['ok'])
        self.assertEqual(entry['reasons'], payload['reasons'])
        self.assertEqual(sorted(entry),
                         ['at', 'check_ok', 'convexity', 'edge_pair_angle_deg',
                          'interior_angles', 'metrics', 'parallel_tol_deg', 'quad', 'reasons',
                          't_s', 'verdict', 'vod'],
                         'the record must keep the fields it held before the repair')


if __name__ == '__main__':
    unittest.main()
