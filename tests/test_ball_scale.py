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
# The binding walk and its support have one home, tests/_shipped.py.
from _shipped import bindings, parse

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
# The frame the readers bind, and the two integers they derive from it.  A reader
# states ``WORKING_FRAME``, or it derives the two integers at module level.
WORKING_FRAME_NAME = 'WORKING_FRAME'
# The frames the owner states, in the order the cases name them.  A frame is two
# integers, and the walk below covers both of them.
FRAME_PAIRS = (ball_scale.WORKING_FRAME, ball_scale.NATIVE_FRAME)
FRAME_INTEGERS = frozenset(number for pair in FRAME_PAIRS for number in pair)
WIDTH_NAMES = frozenset(('W', 'WIDTH', 'W_PX', 'WIDTH_PX'))
HEIGHT_NAMES = frozenset(('H', 'HEIGHT', 'H_PX', 'HEIGHT_PX'))
# The one binding outside the owner whose numbers agree by coincidence.  The record
# holds the line and the exact mapping, so the case below fails when either moves.
# A lookup entry is not a frame the module binds: no length of this repository
# scales with it, and the other two entries of that table are not frames at all.
FRAME_FACTS = (
    ('src/tiny_ball_net.py', 'RESOLUTIONS', 73,
     (('640x360', (640, 360)), ('960x540', (960, 540)), ('1280x720', (1280, 720)))),
)
# The one pair literal that is a guard, not data.  ``tests/test_ball_scale.py``
# states the native pair as the thing the owner must agree with.  That literal is
# the expectation of a case, and no length of this repository is computed from it.
FRAME_EXPECTATIONS = (('tests/test_ball_scale.py', 'test_the_owner_holds_the_measurement',
                       ball_scale.NATIVE_FRAME),)
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


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


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


def frame_bindings(path):
    """Every assignment of one module whose value is two number literals.

    A frame is two integers, for example ``SMALL_W, SMALL_H = 960, 540``.  A pair
    of any other values, for example ``(x, y) = (px * scale, py * scale)``, is not
    a frame and this walk skips it.
    """
    found = []
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if isinstance(value, (ast.Tuple, ast.List)) and frame_pair(value) is not None:
            found.append((node.lineno, targets, value))
    return found


def bound_names(targets):
    """The names one assignment binds: a target name, or every name of a pair."""
    names = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Tuple):
            names.update(elt.id for elt in target.elts if isinstance(elt, ast.Name))
    return names


def frame_pair(tree):
    """The two numbers of one frame literal, or ``None`` when it is not one.

    A frame is two positive integers.  ``(720, 1280)`` is not a frame, and neither
    is a pair of floats, so a swapped or a fractional pair does not pass the walk.
    """
    if not isinstance(tree, (ast.Tuple, ast.List)) or len(tree.elts) != 2:
        return None
    numbers = []
    for element in tree.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, int):
            return None
        if isinstance(element.value, bool) or element.value <= 0:
            return None
        numbers.append(element.value)
    return tuple(numbers)


def frame_literals(path):
    """Every frame literal of one module, with the line it sits on.

    Both frames of the owner count: a literal pair is a second statement of the
    frame, whichever of the two it copies.
    """
    found = []
    for node in ast.walk(parse(path)):
        pair = frame_pair(node)
        if pair in FRAME_PAIRS:
            found.append((node.lineno, 'literal', ast.unparse(node)))
    return found


def frame_number_sites(path):
    """Every site of one module that binds one integer of a frame under its own name.

    ``W, H = 1280, 720`` is a second statement of the pair, but it is not one
    tuple.  This walk reads the names: a name that says width must not hold the
    width of a frame, and a name that says height must not hold its height.
    """
    found = []
    for line, name, value in bindings(path):
        if not isinstance(value, ast.Constant) or not isinstance(value.value, int):
            continue
        if isinstance(value.value, bool):
            continue
        words = name.upper().strip('_').split('_')
        if value.value in (ball_scale.NATIVE_FRAME[0], ball_scale.WORKING_FRAME[0]):
            if words[-1] in WIDTH_NAMES:
                found.append((line, (name,), 'number', '%s = %d' % (name, value.value)))
        elif value.value in (ball_scale.NATIVE_FRAME[1], ball_scale.WORKING_FRAME[1]):
            if words[-1] in HEIGHT_NAMES:
                found.append((line, (name,), 'number', '%s = %d' % (name, value.value)))
    return found


def frame_mappings(path):
    """Every name of one module bound to a table of constant keys, with its span.

    The exception of ``FRAME_FACTS`` is a row of such a table.  This walk reports
    the whole table once, and the site walk skips the rows inside it, so one
    recorded fact answers one site.
    """
    found = []
    for node in ast.walk(parse(path)):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not isinstance(value, ast.Dict) or not value.keys:
            continue
        if any(not isinstance(key, ast.Constant) for key in value.keys):
            continue
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            found.append((node.lineno, node.end_lineno, node.targets[0].id, value,
                          ast.unparse(value)))
    return found


def table_pairs(value):
    """The frame pairs one table holds, with the key that holds each one."""
    found = []
    for key, row in zip(value.keys, value.values):
        pair = frame_pair(row)
        if pair in FRAME_PAIRS and isinstance(key, ast.Constant):
            found.append((key.value, pair))
    return found


def frame_sites(path):
    """Every site of one module that states a frame a second time.

    The owner states both frames, and every other module reads them.  A reader may
    alias the owner's object, derive an integer from it, or call the owner's
    conversion: all three read one home.  A literal pair, or a width under a width
    name, is a second home.
    """
    found = []
    spans = []
    for start, end, name, value, _written in frame_mappings(path):
        pairs = table_pairs(value)
        if not pairs:
            continue
        spans.append((start, end))
        found.append((start, (name,), 'mapping',
                      '%s = %s' % (name, '  '.join('%s: %s' % pair for pair in pairs))))
    for line, targets, value in frame_bindings(path):
        if frame_pair(value) not in FRAME_PAIRS:
            continue
        if reads_owner(path, value):
            continue
        written = ast.unparse(targets[0]) if len(targets) == 1 else ', '.join(
            ast.unparse(target) for target in targets)
        found.append((line, tuple(sorted(bound_names(targets))), 'assignment',
                      '%s = %s' % (written, ast.unparse(value))))
    found.extend(frame_number_sites(path))
    for line, kind, term in frame_literals(path):
        if any(start <= line <= end for start, end in spans):
            continue
        found.append((line, (), kind, term))
    return found



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

    def test_no_second_module_binds_a_frame_size(self):
        """The owner holds both frames, and no other module binds either again.

        A reader binds ``WORKING_FRAME`` or ``NATIVE_FRAME``, or it derives the two
        integers from one of them, or it calls ``scale_between``.  A bare
        ``(960, 540)`` or ``(1280, 720)`` pair outside the owner is a second home:
        the ball's pixel size scales with the frame, so the facts move together and
        the copy drifts first.

        One binding of this tree holds numbers that agree with a frame and state
        another fact: the ``"1280x720"`` row of ``RESOLUTIONS``.  That row is a
        lookup entry of a size-string table.  ``FRAME_FACTS`` records the whole
        table with its line and its value, so the case fails when the entry moves,
        changes or vanishes -- a stale record is not a pass.
        """
        recorded = {(module, name) for module, name, _, _ in FRAME_FACTS}
        found = []
        for path in source_files():
            module = relative(path)
            if module == OWNER:
                continue
            for line, names, kind, term in frame_sites(path):
                if any((module, name) in recorded for name in names):
                    continue
                found.append('%s:%d: %s, %s' % (module, line, kind, term))
        self.assertEqual([], found,
                         'a second module binds the working frame %s or the native frame %s.  '
                         '%s owns both, so import a name of the owner or call scale_between:\n%s'
                         % (repr(ball_scale.WORKING_FRAME), repr(ball_scale.NATIVE_FRAME), OWNER,
                            '\n'.join(found)))

    def test_every_recorded_frame_fact_still_matches(self):
        """The one recorded exception is the table it claims, on the line it claims."""
        for module, name, line, value in FRAME_FACTS:
            sites = [(at, tuple(ast.literal_eval(
                         ast.parse(written, mode='eval').body).items()))
                     for at, _, bound, _tree, written in frame_mappings(ROOT / module)
                     if bound == name]
            self.assertEqual([(line, value)], sites,
                             '%s:%s is the recorded exception of the frames.  The module now '
                             'binds %r.  A recorded exception that moves, changes or vanishes '
                             'must not pass this case.'
                             % (module, name, sites or 'nothing'))

    def test_every_recorded_frame_expectation_is_still_in_the_guard(self):
        """The literal pair the guard compares the owner with is still there.

        ``tests/test_ball_scale.py`` states the native pair, because a guard that
        reads both sides from the owner proves nothing: it would pass when the owner
        moves.  This case holds that literal below its case, so the literal cannot
        vanish or become a name the owner gives.
        """
        for module, function, pair in FRAME_EXPECTATIONS:
            tree = parse(ROOT / module)
            line = next((node.lineno for node in ast.walk(tree)
                         if isinstance(node, ast.FunctionDef) and node.name == function), None)
            self.assertIsNotNone(line, '%s must hold the case %s' % (module, function))
            below = [term for at, kind, term in frame_literals(ROOT / module) if at > line]
            expected = ast.unparse(ast.Tuple(elts=[ast.Constant(value=number)
                                                   for number in pair], ctx=ast.Load()))
            self.assertIn(expected, ' '.join(below),
                          '%s must state %s as a literal pair below %s.  Without it the case '
                          'reads both sides from %s' % (module, expected, function, OWNER))

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

    def test_the_walk_understands_a_second_copy(self):
        """One scratch module per form of a second copy, and the walk finds each one.

        The walk reads syntax, not a line number, so this case is the proof that it
        can see a copy it never saw before.  It writes each scratch module into
        ``src/`` and removes it in a ``finally`` block.
        """
        copies = (
            ('ALIAS_NATIVE = (1280, 720)\n', 'src/scratch_frames.py', 'assignment'),
            ('ALIAS_FULL = [960, 540]\n', 'src/scratch_frames.py', 'assignment'),
            ('ALIAS_W, ALIAS_H = 1280, 720\n', 'src/scratch_frames.py', 'assignment'),
            ('ALIAS_W = 1280\n', 'src/scratch_frames.py', 'number'),
            ('ALIAS_H = 720\n', 'src/scratch_frames.py', 'number'),
            ('ALIAS = {"1280x720": (1280, 720)}\n', 'src/scratch_frames.py', 'mapping'),
        )
        for text, module, kind in copies:
            path = ROOT / module
            try:
                path.write_text(text, encoding='utf-8')
                found = [site for site in frame_sites(path) if site[2] == kind]
            finally:
                path.unlink()
            self.assertEqual(1, len(found),
                             '%s must read as one %s of a frame: %r'
                             % (text.strip(), kind, found))

    def test_the_walk_accepts_every_form_that_reads_the_owner(self):
        """An alias, a derived integer and the owner's call are not second copies."""
        reads = ('ALIAS_NATIVE = NATIVE_FRAME\n',
                 'ALIAS_W = NATIVE_FRAME[0]\n',
                 'ALIAS_H = ball_scale.NATIVE_FRAME[1]\n',
                 'ALIAS_SMALL = scale_between(NATIVE_FRAME, ball_scale.WORKING_FRAME)\n',
                 'ALIAS_LIST = list(NATIVE_FRAME)\n')
        path = ROOT / 'src' / 'scratch_frames.py'
        header = 'from src.ball_scale import NATIVE_FRAME, scale_between\nfrom src import ball_scale\n'
        try:
            path.write_text(header + ''.join(reads), encoding='utf-8')
            found = frame_sites(path)
        finally:
            path.unlink()
        self.assertEqual([], found,
                         'every line below reads the owner, so the walk must find no second '
                         'copy:\n%s' % '\n'.join(reads))


if __name__ == '__main__':
    unittest.main()
