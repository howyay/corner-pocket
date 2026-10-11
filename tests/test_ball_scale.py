"""One home for the ball's size: the measurement, the conversion, and the guard.

Two modules stated the ball's pixel size and they disagreed: ``src/motion_scan.py``
said 18.9 px at the native frame, and ``src/shot_pot_gate.py`` said 18.4 px.  18.4
matches no file in this tree.  ``src/ball_scale.py`` owns the number now, and the
gate, the scan, the census, the timing walk and the pipeline read it.

Three checks hold that home:

1. the numbers in the owner equal the measurement.  The radii of
   ``out/scan30/sam3_results.json`` are the source, and one case recomputes the
   median and the p10/p90 order statistics from that file, so the constants cannot
   drift from the data they claim.
2. the conversion is right.  18.9 px at the native 1280x720 frame is 14.175 px at
   the working 960x540 frame.  The wrong direction (18.9 / 0.75 = 25.2) is a
   different number, and the old comments said both 20 px and 8 px.
3. no second copy appears.  The walk below reads source, never a line number, and
   it fails when a module binds or compares the measured diameter, the p10/p90
   diameters, the radius or the width outside the owner.

The walk reads source, so it sees a module the runner has not loaded yet.
"""
from __future__ import annotations

import ast
import json
import math
import statistics
import unittest
from pathlib import Path

from src import ball_scale

ROOT = Path(__file__).resolve().parents[1]
SOURCE_TREES = (ROOT / 'src', ROOT / 'annotator')

# The one home of the measured size, and the names every reader imports.
OWNER = 'src/ball_scale.py'
# The measurement the owner claims, and the file it claims it from.  The median
# radius of that file, not a guess: the case below recomputes every number.
MEASUREMENT = ROOT / 'out' / 'scan30' / 'sam3_results.json'
MEDIAN_RADIUS_PX = 9.45

# The value in force, and the value that was wrong.  The gate's length bars are
# multiples of the diameter, so the number changes behaviour.
DIAMETER_NATIVE_PX = 18.9
DIAMETER_WORK = 14.175
WRONG_DIAMETER_PX = 18.4
# The p10 and p90 diameters of the same 270 radii, at the owner's quantile rule.
DIAMETER_P10_NATIVE_PX = 13.8
DIAMETER_P90_NATIVE_PX = 24.8

# The readers that state the working-frame width in a comment next to the value.
WIDTH_READERS = (('src/ball_census.py', '14.175 px'),
                 ('src/timing_verify.py', '14.175 px'))
# The readers that hold a ball-size name, and the owner module that gives it to
# them.  A reader is not a second home: it imports the value.
ALIASES = ('src/motion_scan.py', 'src/pipeline.py', 'src/shot_pot_gate.py')
# The names that hold a ball size, and the value space of the measurement.  A name
# whose value is outside that space is a different quantity: the highlight clip of
# ``src/calib_mapping_audit.py`` ranges over a closer camera and measures 30.8 px,
# which is not the vod30 native scale that this module owns.
SIZE_NAME_MARKS = ('BALL_DIAMETER', 'BALL_RADIUS', 'BALL_WIDTH', 'CANON_BALL_R',
                   'BALL_PX', 'BALL_AREA_NATIVE')
# The functions of the owner that a reader calls for its own value.
OWNER_CALLS = ('diameter_px', 'radius_px', 'area_px2')
# The one reader whose name is not a ball-size name: the census gate.
CENSUS_READER = ('src/ball_census.py', 'TRACK_MATCH_PX')
# One ball-size name that is a different measurement, and not a second copy of this
# one.  ``src/calib_mapping_audit.py`` states the ball at 30.8 px for the highlight
# clip, whose camera is closer to the table: the same run that
# ``out/scan_highlight/sam3_results.json`` measures at a 30.80 px median diameter.
# That file and its module are outside this round, so the name stays where it is.
OTHER_MEASUREMENT = 'src/calib_mapping_audit.py'
# The modules whose live numbers must not move in this round.  A gate bar that is a
# multiple of the diameter moves with the diameter and is re-derived in
# ``tests/test_shot_pot_gate.py``; these are tuned lengths, and a comment can be
# wrong while the number is right.
UNCHANGED = (('src/ball_census.py', 'TRACK_MATCH_PX', 30.0),
             ('src/timing_verify.py', 'BLOB_BAND_BOUNDARY_PX', 3000),
             ('src/motion_scan.py', 'BALL_K_NATIVE', 17),
             ('src/motion_scan.py', 'BALL_K_SMALL', 9),
             ('src/motion_scan.py', 'BALL_K_WIDE', 25),
             ('src/motion_scan.py', 'BALL_K_WORK', 13))


# The unit string of a cloth-scale claim.  A line that holds it must not name a
# module: no module of this tree states a cloth scale in millimetres per pixel.
CLOTH_SCALE_UNITS = 'mm/px'


def source_files():
    """Every module of this repository that could state a ball size."""
    return sorted(path for tree in SOURCE_TREES for path in tree.glob('*.py'))


def parse(path):
    """The syntax tree of one module."""
    return ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


def bindings(path):
    """Every site in one module that binds a name, with the line, the name and the value."""
    found = []
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found.append((node.lineno, target.id, value))
    return found


def owner_value(name, owner=OWNER):
    """The value one module binds under one name at module level, evaluated."""
    found = [value for _, target, value in bindings(ROOT / owner) if target == name]
    if len(found) != 1:
        raise AssertionError('%s binds %s %d times' % (owner, name, len(found)))
    return ast.literal_eval(found[0])


def numeric_sites(path, numbers):
    """Every assignment or comparison site in one module that holds one of ``numbers``.

    An assignment is a site when the value it binds contains the literal.  A
    comparison is a site when one side of it is the literal itself.  A string or a
    comment is not a site: this walk reads syntax, not text.
    """
    found = []
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Assign):
            for literal in [child for child in ast.walk(node)
                            if isinstance(child, ast.Constant) and child.value in numbers]:
                found.append((node.lineno, 'assignment', ast.unparse(node)))
        elif isinstance(node, ast.Compare):
            operands = [node.left] + list(node.comparators)
            if any(isinstance(operand, ast.Constant) and operand.value in numbers
                   for operand in operands):
                found.append((node.lineno, 'comparison', ast.unparse(node)))
    return found


def source_text(module):
    """The text of one module of this repository."""
    return (ROOT / module).read_text(encoding='utf-8')


def quoted_number(text, value):
    """True when one source text states a number as written by the owner.

    ``str(9.45)`` is ``'9.45'`` and ``str(9.450000000000001)`` is not, so a rounded
    restatement of the measurement does not pass this test.
    """
    return repr(float(value)) in text


def median_and_ranks(radii):
    """The median, the p10 and the p90 radius at the owner's nearest-rank rule."""
    ordered = sorted(radii)
    count = len(ordered)

    def rank(p):
        return ordered[max(1, math.ceil(p * count)) - 1]

    return statistics.median(ordered), rank(0.10), rank(0.90)


def owner_imports(path):
    """Every name one module imports from the owner module."""
    names = set()
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.ImportFrom) and node.module == OWNER[:-len('.py')].replace('/', '.'):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def reads_owner(path, value):
    """True when one bound value is built from a name the owner gives this module.

    A reader aliases the owner's value, for example ``REF_BALL_RADIUS =
    RADIUS_NATIVE_PX`` or ``CANON_BALL_R = BALL_WIDTH_MM / 2``.  The name it reads
    comes from the import of the owner, so the value has one home.  A literal, or
    a name the module never imported, is a second home.
    """
    names = {node.id for node in ast.walk(value) if isinstance(node, ast.Name)}
    return bool(names & owner_imports(path))


class BallScaleTest(unittest.TestCase):
    def test_the_owner_holds_the_measurement(self):
        """The owner's constants equal the measurement it claims, in both units."""
        self.assertEqual((1280, 720), ball_scale.NATIVE_FRAME,
                         'the radii of %s were measured in the 1280x720 native recording'
                         % relative(MEASUREMENT))
        self.assertEqual((960, 540), ball_scale.WORKING_FRAME,
                         'the pipeline works at 960x540, which is the native frame at 0.75x')
        self.assertEqual(57.15, ball_scale.BALL_WIDTH_MM,
                         'a pool ball is 57.15 mm (2.25 in) wide.  This is the rule of the '
                         'sport and not a measurement, and every other value follows from it.')
        self.assertAlmostEqual(MEDIAN_RADIUS_PX, ball_scale.RADIUS_NATIVE_PX, delta=1e-9,
                               msg='the owner must state the measured median radius, not 18.4/2')
        self.assertAlmostEqual(MEDIAN_RADIUS_PX,
                               ball_scale.radius_px(ball_scale.NATIVE_FRAME), delta=1e-9,
                               msg='the native radius must be half the measured native diameter')
        self.assertAlmostEqual(DIAMETER_NATIVE_PX, ball_scale.diameter_px(), delta=1e-9)
        self.assertAlmostEqual(DIAMETER_P10_NATIVE_PX, ball_scale.DIAMETER_P10_NATIVE_PX,
                               delta=1e-9)
        self.assertAlmostEqual(DIAMETER_P90_NATIVE_PX, ball_scale.DIAMETER_P90_NATIVE_PX,
                               delta=1e-9)

    def test_the_owner_agrees_with_the_radii_of_the_run(self):
        """The median and the two order statistics of the run equal the owner's numbers."""
        if not MEASUREMENT.is_file():
            self.fail('%s is absent, so the owner\'s numbers cannot be checked against the '
                      'measurement they claim' % relative(MEASUREMENT))
        frames = json.loads(MEASUREMENT.read_text(encoding='utf-8'))
        radii = sorted(float(ball['r']) for frame in frames.values() for ball in frame)
        median, p10, p90 = median_and_ranks(radii)
        self.assertEqual(270, len(radii),
                         'the run holds %d radii of %d frames; the owner states 270 radii of 56 '
                         'frames.  A re-run of the scan changes the measurement, so the owner '
                         'and this test must change together.' % (len(radii), len(frames)))
        self.assertAlmostEqual(MEDIAN_RADIUS_PX, median, delta=1e-9,
                               msg='the median radius of the run moved')
        self.assertAlmostEqual(ball_scale.DIAMETER_NATIVE_PX, 2.0 * median, delta=1e-9,
                               msg='the owner\'s native diameter is not twice the median radius of '
                                   'the run it cites')
        self.assertAlmostEqual(ball_scale.DIAMETER_P10_NATIVE_PX, 2.0 * p10, delta=1e-9,
                               msg='the owner states p10 diameter %r, and the run answers %r at '
                                   'the nearest-rank rule' % (ball_scale.DIAMETER_P10_NATIVE_PX,
                                                              2.0 * p10))
        self.assertAlmostEqual(ball_scale.DIAMETER_P90_NATIVE_PX, 2.0 * p90, delta=1e-9,
                               msg='the owner states p90 diameter %r, and the run answers %r at '
                                   'the nearest-rank rule.  The index int(0.9*n) answers 24.99 px '
                                   'and interpolation answers 24.82 px, so the rule is part of '
                                   'the value.' % (ball_scale.DIAMETER_P90_NATIVE_PX, 2.0 * p90))
        self.assertAlmostEqual(ball_scale.NATIVE_PX_PER_MM, 1.0 / ball_scale.millimetres_per_pixel(),
                               delta=1e-12,
                               msg='millimetres_per_pixel must be the inverse of NATIVE_PX_PER_MM')

    def test_the_conversion_is_right(self):
        """The native diameter converts to the working frame by width, never by the ratio."""
        self.assertAlmostEqual(0.75, ball_scale.scale_between(ball_scale.NATIVE_FRAME,
                                                              ball_scale.WORKING_FRAME), delta=1e-12)
        self.assertAlmostEqual(DIAMETER_WORK, ball_scale.diameter_px(ball_scale.WORKING_FRAME),
                               delta=1e-9,
                               msg='18.9 px at 1280x720 is 14.175 px at 960x540.  The wrong '
                                   'direction (18.9 / 0.75) answers 25.2 px, and the removed '
                                   'comments said 20 px and 8 px.')
        self.assertAlmostEqual(DIAMETER_NATIVE_PX * 0.75,
                               ball_scale.diameter_px(ball_scale.WORKING_FRAME), delta=1e-9,
                               msg='the conversion must be one multiplication by the scale')
        self.assertAlmostEqual(280.55, ball_scale.area_px2(ball_scale.NATIVE_FRAME), delta=0.01,
                               msg='the native area is pi * (18.9 / 2) ** 2.  The dead constant '
                                   'that this round deleted said 266.0, the area of the 18.4 px '
                                   'ball that no file in this tree holds.')
        self.assertAlmostEqual(157.81, ball_scale.area_px2(ball_scale.WORKING_FRAME), delta=0.01)
        self.assertEqual('57.2mm', ball_scale.formatted_width(),
                         'the comment form of the width must be a half-up round to one decimal '
                         'place: 57.15 answers 57.2 and not the 57.1 of round(57.15, 1)')
        self.assertEqual('28.6mm', ball_scale.formatted_width(ball_scale.BALL_WIDTH_MM / 2.0),
                         'a width of 28.575 mm states 28.6mm, the radius the pipeline uses')

    def test_no_module_binds_a_ball_size_outside_the_owner(self):
        """One module binds every ball-size name, and the value in force is the measured one."""
        numbers = (DIAMETER_NATIVE_PX, DIAMETER_WORK, DIAMETER_P10_NATIVE_PX,
                   DIAMETER_P90_NATIVE_PX, MEDIAN_RADIUS_PX, ball_scale.BALL_WIDTH_MM,
                   round(ball_scale.BALL_WIDTH_MM / 2.0, 3))
        sites = []
        for path in source_files():
            if relative(path) == OWNER:
                continue
            for line, kind, code in numeric_sites(path, numbers):
                sites.append('%s:%d: %s' % (relative(path), line, code))
        self.assertEqual([], sites,
                         'a module states the ball\'s measured size as a literal.  Import the '
                         'name from %s instead, so the gate and the scan cannot disagree:\n%s'
                         % (OWNER, '\n'.join(sites)))

    def test_no_second_name_holds_a_ball_size(self):
        """No module outside the owner and its readers binds a name of the measured size.

        A reader aliases the owner's value for its own callers, and that alias is
        not a second home.  A module that binds the name and does not read the
        owner is one: the value it holds is its own, and the gate's length bars are
        multiples of it.
        """
        loose = []
        for path in source_files():
            module = relative(path)
            if module in (OWNER, OTHER_MEASUREMENT):
                continue
            for line, target, value in bindings(path):
                if not any(mark in target for mark in SIZE_NAME_MARKS):
                    continue
                if not (module in ALIASES and reads_owner(path, value)):
                    loose.append('%s:%d: %s = %s' % (module, line, target, ast.unparse(value)))
        self.assertEqual([], loose,
                         'a second name holds a ball size.  %s owns the measurement, and the '
                         'gate reads its names:\n%s' % (OWNER, '\n'.join(loose)))

    def test_no_line_states_a_cloth_scale_beside_a_module_name(self):
        """A comment that states a scale in mm/px must not vouch for a module.

        Strong 2 of the round-51 walk: the docstring of
        :func:`millimetres_per_pixel` sent the reader to ``src/ball_census.py``
        and ``src/timing_verify.py`` for the cloth at "a rounded 2.8 and 7.26
        mm/px".  No line of either module stated one: round 50 had deleted the 2.8
        mm/px comment from the census, and ``git grep '2\\.8' -- src`` answered
        only that sentence.

        This case reads the shape of a line and not the meaning of a sentence.  A
        line that names a module and no unit passes.  A voucher written on the
        next line, or with the unit spelled out, passes.  The two modules that do
        hold a cloth number are named in the owner's docstring, where no line
        holds both parts.
        """
        found = []
        for number, line in enumerate(source_text(OWNER).splitlines(), start=1):
            if CLOTH_SCALE_UNITS in line and '.py' in line:
                found.append('%s:%d: %s' % (OWNER, number, line.strip()))
        self.assertEqual([], found,
                         'a line of the owner states a scale in %s and names a module.  A module '
                         'named this way must state the number, and these did not:\n%s'
                         % (CLOTH_SCALE_UNITS, '\n'.join(found)))

    def test_the_readers_state_the_owner(self):
        """The readers state the measurement, and the census gate keeps its tuned number."""
        for module, states in WIDTH_READERS:
            text = source_text(module)
            self.assertTrue(quoted_number(text, ball_scale.BALL_WIDTH_MM),
                            '%s must state the ball width %r, the number %s owns'
                            % (module, ball_scale.formatted_width(), OWNER))
            self.assertIn(states, text,
                          '%s must state %r, the measured width at the working frame'
                          % (module, states))
            self.assertNotIn(repr(WRONG_DIAMETER_PX), text,
                             '%s still states the diameter %r, and %r matches no file in this '
                             'tree' % (module, WRONG_DIAMETER_PX, WRONG_DIAMETER_PX))
        module, name = CENSUS_READER
        self.assertAlmostEqual(30.0, owner_value(name, module), delta=1e-9,
                               msg='%s:%s is a tuned number about two balls at the working '
                                   'frame.  A comment can be wrong while the number is right, so '
                                   'this round did not change it.' % (module, name))

    def test_the_live_numbers_did_not_move(self):
        """Every bar that is not the diameter keeps the value it had before this round."""
        for module, name, value in UNCHANGED:
            found = owner_value(name, module)
            self.assertEqual(value, found,
                             '%s:%s is %r now and was %r before this round.  The measured '
                             'diameter is the only number this round corrects.'
                             % (module, name, found, value))


if __name__ == '__main__':
    unittest.main()
