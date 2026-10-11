"""Guard for the one owner of the homogeneous-division rule.

The rule was stated eight times in seven modules, with two thresholds and two
answers.  ``src/projection.py`` now holds it once, as ``project_point``, and
every reader calls it.  This module holds that state in five ways:

1. one ``ast`` walk over the site modules, which fails with the site list when
   a bare ``abs(...) < 1e-9`` or ``abs(...) < 1e-12`` stands again in a reader,
   or when a reader stops calling the owner;
2. one case per behaviour of the owner, at both tolerances, including the two
   borders (``abs(w) < t`` is false at ``w == t``, so the point divides);
3. one case that a refused point reaches no ``nan`` coordinate through the
   eight readers;
4. one case that plants a copy in a temporary module under a ``src`` directory
   and proves the walk sees it;
5. one case that pins the two tolerance values, so a later edit of the owner
   must change this module too.

The walk reads the site modules only.  A module outside that list keeps its own
helpers: ``abs(m[pivot][col]) < 1e-12`` is a Gaussian-elimination pivot test in
``src/shot_pot_gate.py``, and it is not a homogeneous division.  The walk
exempts a private helper in a site module for the same reason.
"""
import ast
import math
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from src.projection import (DEFAULT_TOLERANCE, PIXEL_TOLERANCE,  # noqa: E402
                            as_array, as_list, project_point)

ROOT = Path(__file__).resolve().parents[1]

#: The eight sites the rule stood at, with the tolerance each one passes.
#: ``None`` means the site keeps the owner's default tolerance.  The brief of
#: round 59 names the two pixel readers of ``src/eval_events.py`` as
#: ``Reference.px`` and ``Reference.claim_px``.  The class in the tree is
#: ``Probe``; the site count is eight, and the file is the brief's file.
SITES = [
    ('annotator/unified_server.py', 'Backend._project', 'PIXEL_TOLERANCE'),
    ('src/calib_mapping_audit.py', 'project', None),
    ('src/calib_mapping_audit.py', 'unproject', None),
    ('src/dense_queue.py', 'to_mm', 'PIXEL_TOLERANCE'),
    ('src/eval_events.py', 'Probe.px', 'PIXEL_TOLERANCE'),
    ('src/eval_events.py', 'Probe.claim_px', 'PIXEL_TOLERANCE'),
    ('src/info_complete_scan.py', 'to_table_mm', 'PIXEL_TOLERANCE'),
    ('src/shot_pot_gate.py', 'project', 'GATE_TOLERANCE'),
]

#: The modules the walk reads: the seven that held the rule, and the owner.
MODULES = sorted({site[0] for site in SITES} | {'src/projection.py'})

#: The names a reader may put in the owner call.  A number is not one of them.
NAMED_TOLERANCES = ('PIXEL_TOLERANCE', 'GATE_TOLERANCE')

#: The two thresholds the rule used before the repair.  Both followed
#: ``abs(...) <``.
BARE_THRESHOLDS = (1e-9, 1e-12)

#: The functions that hold a different rule with one of those numbers, keyed by
#: ``(module, function)``.  The Gaussian pivot of the solver turns on
#: ``abs(m[pivot][col]) < 1e-12``, and that threshold belongs to the solver, not
#: to the projection rule.  A name here is a decision, and the case
#: ``test_the_walk_leaves_the_pivot_test_of_the_solver_alone`` holds it.
OWN_NUMBERS = {
    ('src/shot_pot_gate.py', '_solve'): 'the Gaussian pivot of the solver',
}

def _functions(module, dotted):
    """The function nodes of one dotted name: ``name`` or ``Class.name``.

    The name is matched inside the class, so two classes that hold the same
    method name cannot answer for each other.
    """
    parts = dotted.split('.')
    if len(parts) == 1:
        return [node for node in module.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == parts[0]]
    holder = next((node for node in module.body
                   if isinstance(node, ast.ClassDef) and node.name == parts[0]), None)
    if holder is None:
        return []
    return [node for node in holder.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == parts[1]]


def _is_bare_threshold(node):
    """True when a node is ``abs(...) < 1e-9`` or ``abs(...) < 1e-12``.

    A pivot test has this shape too, so the caller of this function decides
    which enclosing functions are readers.
    """
    if not isinstance(node, ast.Compare):
        return False
    if not node.ops or not isinstance(node.ops[0], ast.Lt):
        return False
    left = node.left
    if not (isinstance(left, ast.Call) and getattr(left.func, 'id', None) == 'abs'):
        return False
    right = node.comparators[0]
    return (isinstance(right, ast.Constant) and isinstance(right.value, float)
            and right.value in BARE_THRESHOLDS)


def _reader_names(module):
    """Every site function name of one module, as the walk knows it."""
    return {dotted.split('.')[-1] for name, dotted, _tolerance in SITES if name == module}


def _bare_threshold_sites(path, module, relative=None):
    """(line, source line) of each bare threshold in a function of one module.

    The walk reads **every** function, so a new function that spells the
    threshold again is reported, in a site module as well as in another module.
    ``OWN_NUMBERS`` names the functions that hold a different rule with one of
    those numbers.  ``relative`` lets a case answer for a module of the tree
    without writing that module.
    """
    relative = _relative(path) if relative is None else relative
    lines = path.read_text(encoding='utf-8').splitlines()
    found = []
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef):
            continue
        if (relative, node.name) in OWN_NUMBERS:
            continue
        for child in ast.walk(node):
            if _is_bare_threshold(child):
                found.append((child.lineno, lines[child.lineno - 1].strip()))
    return sorted(set(found))


def _relative(path):
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _owner_calls(node):
    """Every owner call inside one function body, with its stated tolerance.

    ``tolerance`` is ``None`` when the call keeps the owner's default, the
    attribute name when the call names one, and the literal's ``repr`` when the
    call passes a number.  A call whose first argument is itself a call is a
    reader that computes its own denominator, which is a second copy of the
    rule.
    """
    calls = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', None)
        if name != 'project_point':
            continue
        tolerance = None
        stated = False
        for keyword in child.keywords:
            if keyword.arg == 'tolerance':
                stated = True
                value = keyword.value
                tolerance = (value.attr if isinstance(value, ast.Attribute)
                             else getattr(value, 'id', None))
                if tolerance is None:
                    tolerance = repr(getattr(value, 'value', value))
        calls.append({'line': child.lineno,
                      'tolerance': tolerance,
                      'stated': stated,
                      'own_denominator': bool(child.args) and isinstance(child.args[0], ast.Call)})
    return calls


def _read_sites(root=ROOT):
    """The reader calls of the eight sites, or the faults that replace them."""
    found = {}
    faults = []
    for name in MODULES:
        path = root / name
        module = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for line, source in _bare_threshold_sites(path, module):
            faults.append('%s:%d: a bare threshold stands again: %s' % (name, line, source))
        for _file, dotted, allowed in [site for site in SITES if site[0] == name]:
            calls = []
            for node in _functions(module, dotted):
                calls.extend(_owner_calls(node))
            if not calls:
                faults.append('%s: %s reads no owner rule: it holds its own answer'
                              % (name, dotted))
                continue
            if any(call['own_denominator'] for call in calls):
                faults.append('%s:%d: %s computes its own denominator'
                              % (name, calls[0]['line'], dotted))
            for call in calls:
                if not call['stated']:
                    if allowed is not None:
                        faults.append('%s:%d: %s keeps the default, but the site declared %s'
                                      % (name, call['line'], dotted, allowed))
                    continue
                if call['tolerance'] not in NAMED_TOLERANCES:
                    faults.append('%s:%d: %s passes tolerance %s, which is not a named value'
                                  % (name, call['line'], dotted, call['tolerance']))
                elif call['tolerance'] != allowed:
                    faults.append('%s:%d: %s passes %s, but the site declared %s'
                                  % (name, call['line'], dotted, call['tolerance'], allowed))
            found[(name, dotted)] = calls
    return found, faults


def _answer_of(reader):
    """One reader's answer, or the sentence of the refusal it states."""
    try:
        return reader()
    except ValueError as exc:
        return 'ValueError: %s' % exc


class TheWalkSeesEightReaders(unittest.TestCase):
    """Case 1 and case 4: the static state of the tree."""

    def test_the_eight_sites_read_the_owner_and_no_bare_threshold_stands(self):
        found, faults = _read_sites()
        self.assertEqual(faults, [], '\n'.join(faults))
        self.assertEqual(sorted(found), sorted((name, dotted) for name, dotted, _t in SITES))

    def test_the_walk_sees_a_planted_copy_in_a_temporary_module(self):
        planted = textwrap.dedent('''
            """A planted copy of the rule, for the guard's own check."""


            def planted(w):
                return None if abs(w) < 1e-9 else 1.0
            ''')
        with tempfile.TemporaryDirectory(prefix='projection-guard-') as tmp:
            new_src = Path(tmp) / 'src'
            new_src.mkdir()
            path = new_src / 'planted_projection.py'
            path.write_text(planted, encoding='utf-8')
            seen = _bare_threshold_sites(path, ast.parse(planted, filename=str(path)))
        self.assertEqual(len(seen), 1, 'the walk must see the planted threshold: %r' % (seen,))
        self.assertIn('abs(w) < 1e-9', seen[0][1])

    def test_the_walk_sees_a_planted_copy_inside_a_site_module(self):
        """A new function of a site module may not spell the threshold again.

        The walk read the declared readers of a site module only, so a planted
        helper beside ``to_mm`` stayed invisible.  The Lead's bite of round 59
        found that hole: the planted helper answered ``13 tests OK``.
        """
        real = ROOT / 'src' / 'dense_queue.py'
        planted = real.read_text(encoding='utf-8') + textwrap.dedent('''

            def helper(w):
                return None if abs(w) < 1e-9 else 1.0
            ''')
        with tempfile.TemporaryDirectory(prefix='projection-guard-') as tmp:
            path = Path(tmp) / 'dense_queue.py'
            path.write_text(planted, encoding='utf-8')
            seen = _bare_threshold_sites(path, ast.parse(planted, filename=str(path)),
                                         relative='src/dense_queue.py')
        self.assertEqual(len(seen), 1, 'the helper of a site module must be seen: %r' % (seen,))
        self.assertIn('abs(w) < 1e-9', seen[0][1])

    def test_the_walk_leaves_the_pivot_test_of_the_solver_alone(self):
        """The exemption is tested against the real file, not a copy."""
        path = ROOT / 'src/shot_pot_gate.py'
        module = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        seen = _bare_threshold_sites(path, module)
        self.assertEqual(seen, [], 'the pivot test of _solve is not a reader: %r' % (seen,))
        raw = [node for node in ast.walk(module) if _is_bare_threshold(node)]
        self.assertTrue(raw, 'the pivot test must still be in the file for this case to bite')
        self.assertIn(('src/shot_pot_gate.py', '_solve'), OWN_NUMBERS,
                      'the pivot exemption must stay named, or the walk reads the solver')


class TheOwnerAnswers(unittest.TestCase):
    """Case 2 and case 5: one answer per behaviour, and the pinned thresholds."""

    def test_the_default_tolerance_refuses_every_unanswerable_w(self):
        cases = {
            float('nan'): None,
            float('inf'): None,
            float('-inf'): None,
            0.0: None,
            1e-13: None,
            1e-10: (2.0e10, 4.0e10),
            1e-12: (2.0e12, 4.0e12),   # the border: abs(w) < 1e-12 is False here
            1.0: (2.0, 4.0),
        }
        for w, want in cases.items():
            got = project_point(2.0, 4.0, w)
            if want is None:
                self.assertIsNone(got, 'w=%r answered %r, not None' % (w, got))
                continue
            self.assertIsNotNone(got, 'w=%r answered None' % w)
            self.assertAlmostEqual(got[0] / want[0], 1.0, places=12)
            self.assertAlmostEqual(got[1] / want[1], 1.0, places=12)

    def test_the_pixel_tolerance_refuses_a_smaller_w(self):
        # 2.0 / 1e-9 is 1999999999.9999998 in binary floating point, so the
        # check is on the ratio, not on the last bit of the quotient.
        cases = {
            float('nan'): None,
            0.0: None,
            1e-10: None,               # the pixel group refuses this one
            1e-9: (2.0e9, 4.0e9),      # abs(w) < 1e-9 is False at w == 1e-9
            1.0: (2.0, 4.0),
        }
        for w, want in cases.items():
            got = project_point(2.0, 4.0, w, tolerance=PIXEL_TOLERANCE)
            if want is None:
                self.assertIsNone(got, 'w=%r answered %r, not None' % (w, got))
                continue
            self.assertIsNotNone(got, 'w=%r answered None' % w)
            self.assertAlmostEqual(got[0] / want[0], 1.0, places=12)
            self.assertAlmostEqual(got[1] / want[1], 1.0, places=12)

    def test_a_non_finite_numerator_is_refused_too(self):
        self.assertIsNone(project_point(float('nan'), 1.0, 1.0))
        self.assertIsNone(project_point(1.0, float('inf'), 1.0))

    def test_a_projection_answers_the_same_numbers_as_the_old_division(self):
        self.assertEqual(project_point(3.0, 6.0, 2.0), (1.5, 3.0))

    def test_the_two_tolerances_are_pinned(self):
        """Change the owner's tolerance and this case fails, and only then."""
        self.assertEqual(DEFAULT_TOLERANCE, 1e-12)
        self.assertEqual(PIXEL_TOLERANCE, 1e-9)
        self.assertLess(DEFAULT_TOLERANCE, PIXEL_TOLERANCE)
        self.assertLess(PIXEL_TOLERANCE, 1.0)

    def test_the_two_point_shapes_never_hold_a_nan(self):
        self.assertIsNone(as_array(None))
        self.assertIsNone(as_list(None))
        self.assertEqual(as_array(project_point(2.0, 4.0, 1.0)).tolist(), [2.0, 4.0])
        self.assertEqual(as_list(project_point(2.0, 4.0, 1.0)), [2.0, 4.0])


class ARefusalReachesNoNan(unittest.TestCase):
    """Case 3: the eight readers, on a map with no answer."""

    @classmethod
    def setUpClass(cls):
        from annotator import unified_server
        from src import (calib_mapping_audit, dense_queue, eval_events,
                         info_complete_scan, shot_pot_gate)

        cls.broken = np.array([[1.0, 0.0, 0.0],
                               [0.0, 1.0, 0.0],
                               [0.0, 0.0, float('nan')]])
        cls.flat_broken = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, float('nan')]
        cls.identity = np.eye(3)
        cls.flat_identity = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]

        def probe(matrix):
            return eval_events.Probe('no-such-video.mp4', matrix, matrix, None)

        cls.refused = {
            'annotator/unified_server.py:Backend._project':
                lambda: unified_server.Backend._project(cls.broken, [10.0, 20.0]),
            'src/calib_mapping_audit.py:project':
                lambda: calib_mapping_audit.project(cls.broken, [10.0, 20.0]),
            'src/calib_mapping_audit.py:unproject':
                lambda: calib_mapping_audit.unproject(cls.broken, [10.0, 20.0]),
            'src/dense_queue.py:to_mm':
                lambda: dense_queue.to_mm(cls.broken, 10.0, 20.0),
            'src/eval_events.py:Probe.px':
                lambda: probe(cls.broken).px([10.0, 20.0]),
            'src/eval_events.py:Probe.claim_px':
                lambda: probe(cls.broken).claim_px([10.0, 20.0]),
            'src/info_complete_scan.py:to_table_mm':
                lambda: info_complete_scan.to_table_mm(cls.broken, 10.0, 20.0),
            'src/shot_pot_gate.py:project':
                lambda: shot_pot_gate.project(cls.flat_broken, (10.0, 20.0)),
        }
        cls.normal = {
            'annotator/unified_server.py:Backend._project':
                lambda: unified_server.Backend._project(cls.identity, [10.0, 20.0]),
            'src/calib_mapping_audit.py:project':
                lambda: calib_mapping_audit.project(cls.identity, [10.0, 20.0]),
            'src/calib_mapping_audit.py:unproject':
                lambda: calib_mapping_audit.unproject(cls.identity, [10.0, 20.0]),
            'src/dense_queue.py:to_mm':
                lambda: dense_queue.to_mm(cls.identity, 10.0, 20.0),
            'src/eval_events.py:Probe.px':
                lambda: probe(cls.identity).px([10.0, 20.0]),
            'src/eval_events.py:Probe.claim_px':
                lambda: probe(cls.identity).claim_px([10.0, 20.0]),
            'src/info_complete_scan.py:to_table_mm':
                lambda: info_complete_scan.to_table_mm(cls.identity, 10.0, 20.0),
            'src/shot_pot_gate.py:project':
                lambda: shot_pot_gate.project(cls.flat_identity, (10.0, 20.0)),
        }
        cls.eight = {'%s:%s' % (name, dotted) for name, dotted, _t in SITES}

    def test_the_readers_are_the_eight_sites(self):
        self.assertEqual(set(self.refused), self.eight)
        self.assertEqual(set(self.normal), self.eight)

    def test_every_reader_refuses_or_states_the_refusal(self):
        for name, reader in sorted(self.refused.items()):
            with self.subTest(reader=name):
                answer = _answer_of(reader)
                if isinstance(answer, str):
                    self.assertEqual(answer, 'ValueError: point maps to infinity', name)
                    continue
                self.assertIsNone(answer, '%s answered %r, not None' % (name, answer))

    def test_no_reader_hands_back_a_nan_coordinate(self):
        for name, reader in sorted(self.refused.items()):
            with self.subTest(reader=name):
                answer = _answer_of(reader)
                if isinstance(answer, str):
                    continue
                if answer is None:
                    continue
                values = answer.tolist() if hasattr(answer, 'tolist') else list(answer)
                for value in values:
                    self.assertFalse(math.isnan(float(value)),
                                     '%s answered %r' % (name, answer))

    #: The answer of each reader on the identity map.  ``to_mm`` is the one
    #: reader that scales its input first: src/ball_scale.py owns the working
    #: frame, and 1280/960 is 4/3.
    NORMAL_WANT = {
        'annotator/unified_server.py:Backend._project': [10.0, 20.0],
        'src/calib_mapping_audit.py:project': [10.0, 20.0],
        'src/calib_mapping_audit.py:unproject': [10.0, 20.0],
        'src/dense_queue.py:to_mm': [13.3, 26.7],
        'src/eval_events.py:Probe.px': [10.0, 20.0],
        'src/eval_events.py:Probe.claim_px': [10.0, 20.0],
        'src/info_complete_scan.py:to_table_mm': [10.0, 20.0],
        'src/shot_pot_gate.py:project': [10.0, 20.0],
    }

    def test_every_reader_still_answers_a_normal_map(self):
        self.assertEqual(sorted(self.NORMAL_WANT), sorted(self.normal))
        for name, reader in sorted(self.normal.items()):
            with self.subTest(reader=name):
                answer = _answer_of(reader)
                self.assertIsNotNone(answer, name)
                values = answer.tolist() if hasattr(answer, 'tolist') else list(answer)
                self.assertEqual([float(value) for value in values],
                                 self.NORMAL_WANT[name], name)


if __name__ == '__main__':
    unittest.main()
