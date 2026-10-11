"""One home for the summary of one list, and one home for the percentile rule.

Round 60 measured four local summaries of "the median and a high percentile of
this list", in ``src/enroll_from_tracklet.py``, ``src/eval_faces.py``,
``src/calib_mapping_audit.py`` and ``src/eval_table_detect.py``.  Two of them
were one body.  The round also measured one percentile rule with two owners,
``src/ball_association_audit.py`` and ``src/ball_association_ab.py``.

One home per rule.  ``src/stats.py summary`` holds the summary body and every
reader reads it.  ``src/ball_association_audit.py _percentile`` holds the
percentile body and the second module reads it.

The four old bodies were not one answer.  Each one held its own keys, its own
empty answer and its own precision.  ``summary`` states those three things as
two named arguments, and this module holds the record of the arguments each
reader passes.

The module holds three rules:

1. the one owner answers the contract for every input a reader meets;
2. every reader answers the owner's contract, and every reader holds a
   reference to the one owner function and not a second body;
3. one body of each rule stands under the source trees, and the walk finds a
   planted copy.

Run: ``./scripts/pool-test.sh python test_stats``
"""
from __future__ import annotations

import ast
import hashlib
import math
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import (  # noqa: E402
    ball_association_ab,
    ball_association_audit,
    calib_mapping_audit,
    enroll_from_tracklet,
    eval_faces,
    eval_table_detect,
    stats,
)

#: The source trees the walk reads, under ``src/``.
TREES = (ROOT / 'src',)

#: Another person's code, as in ``tests/test_duplicate_bodies.py``.
VENDORED = ('sam3',)

#: The one module that holds the body of the summary of one list.
OWNER = 'src/stats.py'

#: The one function of that module that holds the body.
OWNER_NAME = 'summary'

#: The one module that holds the body of the percentile rule.
PERCENTILE_OWNER = 'src/ball_association_audit.py'

#: The one function of that module that holds the body.
PERCENTILE_NAME = '_percentile'

#: The six keys of the pair that held one body, and its precision.
PAIR_KEYS = ('n', 'min', 'p05', 'median', 'p95', 'max')
PAIR_DIGITS = 4

#: The keys and the precision of the two audits that held their own bodies.
OFFSET_KEYS = ('n', 'min', 'p10', 'median', 'p90', 'max')
ERROR_KEYS = ('n', 'median', 'p90', 'max', 'min')
AUDIT_DIGITS = 2

#: One reader: the module that reads the summary, and the name it reads it under.
READERS = (
    ('src/enroll_from_tracklet.py', 'stats'),
    ('src/eval_faces.py', 'pair_stats'),
    ('src/calib_mapping_audit.py', '_stats'),
    ('src/eval_table_detect.py', '_stats'),
)

#: The two modules that read the percentile rule, and the name each one binds.
PERCENTILE_READERS = (
    ('src/ball_association_audit.py', '_percentile'),
    ('src/ball_association_ab.py', '_percentile'),
)

#: The file name the walk reads for that text.
PLANTED_MODULE = 'src/planted_copy.py'

#: The planted name of the owner body.
PLANTED_NAME = 'summary_copy'


def planted_source(source):
    """The owner's own function under another name.

    The body is the owner's body, and only ``def`` line differs.  So the case
    below proves that the fingerprint of the body and not the name decides.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == OWNER_NAME:
            text = ast.get_source_segment(source, node)
            return textwrap.dedent(text.replace('def %s(' % OWNER_NAME,
                                                'def %s(' % PLANTED_NAME, 1))
    raise AssertionError('%s holds no function named %s' % (OWNER, OWNER_NAME))


def body_fingerprint(node):
    """The sha1 of one function's statements, with its docstring removed.

    The walk of ``tests/test_duplicate_bodies.py`` reads a body this way, so this
    module and that one find the same two bodies.
    """
    body = list(node.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return hashlib.sha1(ast.unparse(body).encode('utf-8')).hexdigest()


def module_paths():
    """Every module file under the source trees, the vendored tree left out."""
    found = []
    for tree in TREES:
        for path in sorted(tree.rglob('*.py')):
            if tree.name == 'src' and path.relative_to(tree).parts[0] in VENDORED:
                continue
            found.append(path)
    return found


def named_relative(path):
    """One path of a source tree, as ``src/x.py``."""
    return path.relative_to(ROOT).as_posix()


def body_sites(source, module):
    """(module, line, name, fingerprint) of every function of one body of text."""
    tree = ast.parse(source, filename=module)
    return [(module, node.lineno, node.name, body_fingerprint(node))
            for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]


def sites():
    """(module, line, name, fingerprint) of every function under the source trees."""
    return [site for path in module_paths()
            for site in body_sites(path.read_text(encoding='utf-8'), named_relative(path))]


def digest_of_one_function(module, name):
    """The fingerprint of one function of one module of a source tree."""
    path = ROOT / module
    for site_module, _, site_name, digest in body_sites(
            path.read_text(encoding='utf-8'), module):
        if site_name == name:
            return digest
    raise AssertionError('%s holds no function named %s' % (module, name))


def source_of_one_function(module, name):
    """The body of one function of one module, as ``ast.unparse`` writes it."""
    path = ROOT / module
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=module)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise AssertionError('%s holds no function named %s' % (module, name))


def holders(digest, all_sites):
    """The sites that hold one fingerprint, as ``module name``, in one order."""
    return sorted('%s %s' % (module, name)
                  for module, _, name, found in all_sites if found == digest)


def holding_modules(digest, all_sites):
    """The modules that hold one fingerprint, in one order."""
    return sorted({module for module, _, _, found in all_sites if found == digest})


def reader(module, name):
    """One reader function, named by its module path and its function name."""
    module_name = module[:-3].replace('/', '.')
    return getattr(sys.modules[module_name], name)


def check_agrees_with_owner(case, answer, keys, digits, values):
    """The answer is the owner's answer for the reader's keys and digits.

    A precision test alone cannot fail on a number that already holds fewer
    digits than the reader asks for.  This test compares the two answers as
    they are, so a reader that asks the owner for another precision, or that
    holds a second body, answers a different record.
    """
    want = stats.summary(values, keys=keys, digits=digits)
    case.assertEqual(repr(want), repr(answer),
                     'the reader must answer the owner with %r, and it answered %r'
                     % (repr(want), repr(answer)))


def check_keys(case, answer, keys):
    """Every key of ``keys`` is in one answer, and no other key is."""
    case.assertEqual(sorted(keys), sorted(answer),
                     'the answer holds %s, and this reader answers %s'
                     % (sorted(answer), sorted(keys)))


def check_digits(case, answer, digits, values):
    """Every number of the answer is the owner's number at the reader's digits.

    The owner answers the same keys at full precision, and this test rounds
    that answer to the reader's precision.  So a number that carries another
    precision, or a wrong number, fails the test.  ``n`` counts the list.
    """
    for key, value in answer.items():
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue                      # a list with nan answers nan, as numpy does
        if key == 'n':
            case.assertEqual(len(values), value, 'n must count the list')
            continue
        exact = stats.summary(values, keys=(key,), digits=15)[key]
        case.assertEqual(float(value), round(exact, digits),
                         '%s of %s must be %r at %d digits, and it is %r'
                         % (key, values, round(exact, digits), digits, value))


class TheOwnerAnswersTheContractTest(unittest.TestCase):
    """One case per input a reader meets, plus one for the name of a bad key."""

    def test_an_empty_list_answers_n_zero_and_none_for_every_other_key(self):
        answer = stats.summary([])
        self.assertEqual(0, answer['n'])
        for key in stats.SUMMARY_KEYS:
            if key != 'n':
                self.assertIsNone(answer[key], '%s of an empty list must be None' % key)

    def test_one_value_answers_that_value_five_times(self):
        answer = stats.summary([7.5])
        for key in ('min', 'p05', 'p10', 'median', 'p90', 'p95', 'max'):
            self.assertEqual(7.5, answer[key], '%s of one value must be that value' % key)

    def test_an_even_count_averages_the_two_middle_values(self):
        answer = stats.summary([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(4, answer['n'])
        self.assertEqual(2.5, answer['median'])
        self.assertEqual(1.0, answer['min'])
        self.assertEqual(4.0, answer['max'])
        self.assertLess(answer['p05'], answer['p95'])

    def test_an_odd_count_answers_the_middle_value(self):
        answer = stats.summary([0.0, 0.25, 0.5, 0.75, 1.0])
        self.assertEqual(5, answer['n'])
        self.assertEqual(0.5, answer['median'])
        self.assertEqual(0.05, answer['p05'])
        self.assertEqual(0.95, answer['p95'])

    def test_a_list_with_nan_answers_nan_and_not_an_error(self):
        answer = stats.summary([float('nan'), 1.0, 2.0])
        self.assertEqual(3, answer['n'])
        for key in ('min', 'p05', 'p10', 'median', 'p90', 'p95', 'max'):
            self.assertTrue(math.isnan(answer[key]),
                            '%s of a list with nan must be nan' % key)

    def test_a_negative_number_keeps_its_sign(self):
        answer = stats.summary([-4.0, -1.0, 0.0])
        self.assertEqual(-4.0, answer['min'])
        self.assertEqual(0.0, answer['max'])
        self.assertEqual(-1.0, answer['median'])

    def test_a_key_that_is_not_a_key_of_the_summary_is_refused(self):
        with self.assertRaises(ValueError):
            stats.summary([1.0], keys=('n', 'p99'))

    def test_the_precision_argument_decides_the_digits_of_the_answer(self):
        """A list whose quantiles need four digits proves that ``digits`` counts."""
        values = [0.190873, -0.20768, -0.09401, 0.477832]
        for key in ('p05', 'p10', 'median', 'p90', 'p95'):
            with self.subTest(key=key):
                four = stats.summary(values, keys=(key,), digits=4)[key]
                three = stats.summary(values, keys=(key,), digits=3)[key]
                two = stats.summary(values, keys=(key,), digits=2)[key]
                self.assertNotEqual(four, three,
                                    '%s must keep a fourth digit' % key)
                self.assertNotEqual(three, two,
                                    '%s must keep a third digit' % key)

    def test_the_keys_the_readers_name_are_keys_of_the_summary(self):
        for keys in (PAIR_KEYS, OFFSET_KEYS, ERROR_KEYS):
            with self.subTest(keys=keys):
                self.assertEqual(sorted(keys), sorted(set(keys) & set(stats.SUMMARY_KEYS)))


class TheReadersAnswerTheContractTest(unittest.TestCase):
    """One case per reader: the same lists under the reader's own keys."""

    #: The lists every reader answers.  Keys of one reader are a subset of the
    #: keys of a pair, and an empty list is the one answer that differs.  The
    #: last list holds quantiles that need four digits, so a reader that rounds
    #: to fewer digits answers a different number.
    LISTS = ([], [7.5], [1.0, 2.0, 3.0, 4.0], [0.0, 0.25, 0.5, 0.75, 1.0],
             [float('nan'), 1.0, 2.0], [-4.0, -1.0, 0.0],
             [0.190873, -0.20768, -0.09401, 0.477832])

    def cases(self, module, name):
        """(keys, digits) of one reader.  The ``name`` is not read."""
        if module == 'src/enroll_from_tracklet.py':
            return PAIR_KEYS, PAIR_DIGITS
        if module == 'src/eval_faces.py':
            return PAIR_KEYS, PAIR_DIGITS
        if module == 'src/calib_mapping_audit.py':
            return OFFSET_KEYS, AUDIT_DIGITS
        return ERROR_KEYS, AUDIT_DIGITS

    #: The two answers of no value, each with the reader that holds it.  The
    #: audit answered ``{'n': 0}`` and the error summary answered ``None``
    #: before round 60, and both readers keep their own answer.
    NO_VALUE = {'src/enroll_from_tracklet.py': 'every key',
                'src/eval_faces.py': 'every key',
                'src/calib_mapping_audit.py': 'the count only',
                'src/eval_table_detect.py': 'none'}

    def test_every_reader_answers_its_own_keys_for_every_list(self):
        for module, name in READERS:
            keys, digits = self.cases(module, name)
            read = reader(module, name)
            for values in self.LISTS:
                with self.subTest(reader=module, values=values):
                    answer = read(values)
                    if not values:
                        self.check_no_value(module, answer, keys)
                        continue
                    check_keys(self, answer, keys)
                    check_digits(self, answer, digits, values)
                    check_agrees_with_owner(self, answer, keys, digits, values)

    def check_no_value(self, module, answer, keys):
        """The answer of an empty list is the answer this reader held."""
        want = self.NO_VALUE[module]
        if want == 'none':
            self.assertIsNone(answer, '%s must answer None for no value' % module)
            return
        self.assertIsNotNone(answer, '%s must answer a record and not None' % module)
        if want == 'the count only':
            self.assertEqual({'n': 0}, answer,
                             '%s of no value holds the count only' % module)
            return
        check_keys(self, answer, keys)
        self.assertEqual(0, answer['n'], '%s must answer n = 0' % module)
        for key, value in answer.items():
            if key != 'n':
                self.assertIsNone(value, '%s of an empty list must be None' % key)

    def test_every_reader_is_in_the_record_of_the_answers_of_no_value(self):
        self.assertEqual(sorted(module for module, _ in READERS), sorted(self.NO_VALUE),
                         'the record of this case must name every reader')

    def test_the_two_pair_readers_answer_an_empty_list_with_every_key(self):
        """The old body of the pair answered six keys for an empty list.

        It answered ``{"n": 0, "min": None, ...}`` and not ``{"n": 0}``, so the
        answer of an empty list keeps all six keys.
        """
        names = ((READERS[0][0], READERS[0][1]), (READERS[1][0], READERS[1][1]))
        for module, name in names:
            with self.subTest(reader=module):
                answer = reader(module, name)([])
                self.assertEqual(0, answer['n'])
                self.assertEqual(sorted(PAIR_KEYS), sorted(answer))

    def test_a_reader_answers_the_owner_for_a_list_of_one_value(self):
        for module, name in READERS:
            with self.subTest(reader=module):
                answer = reader(module, name)([3.0])
                self.assertEqual(3.0, answer['median'])
                self.assertEqual(3.0, answer['min'])
                self.assertEqual(3.0, answer['max'])

    def test_a_reader_answers_nan_and_not_an_error(self):
        for module, name in READERS:
            with self.subTest(reader=module):
                answer = reader(module, name)([float('nan'), 1.0])
                self.assertTrue(math.isnan(answer['median']),
                                '%s must pass nan through the answer' % module)

    def test_the_p99_key_of_the_old_audit_body_is_gone(self):
        """The old body held p10; the keys of every reader are named above."""
        for module, name in READERS:
            with self.subTest(reader=module):
                answer = reader(module, name)([1.0, 2.0])
                self.assertNotIn('p99', answer, '%s answers a key nobody reads' % module)

    def test_every_reader_holds_the_one_owner_function_and_not_a_copy(self):
        for module, name in READERS:
            with self.subTest(reader=module):
                self.assertIs(stats.summary, reader(module, name).__globals__[OWNER_NAME],
                              '%s holds a second body of the summary, not the owner name'
                              % module)

    def test_the_two_names_of_the_pair_are_one_function_object(self):
        """src/enroll_from_tracklet.py stats and src/eval_faces.py pair_stats.

        Neither name holds a wrapper around the owner: both names are the
        owner's one reader of the pair keys, so a change to it reaches both.
        """
        self.assertIs(enroll_from_tracklet.stats, eval_faces.pair_stats)
        self.assertIs(stats.read_pair, enroll_from_tracklet.stats)

    def test_every_reader_names_the_owner_in_its_source(self):
        wanted = {'src/enroll_from_tracklet.py': 'from src.stats import read_pair as stats',
                  'src/eval_faces.py': 'from src.stats import read_pair',
                  'src/calib_mapping_audit.py': 'from src.stats import summary',
                  'src/eval_table_detect.py': 'from src.stats import summary'}
        self.assertEqual(sorted(wanted), sorted(module for module, _ in READERS),
                         'the record of this case must name every reader')
        for module, line in wanted.items():
            with self.subTest(reader=module):
                source = (ROOT / module).read_text(encoding='utf-8')
                self.assertIn(line, source,
                              '%s must read the one owner of the summary' % module)


class ThePercentileHasOneOwnerTest(unittest.TestCase):
    """One body of the percentile rule, and the second module reads it."""

    def test_the_audit_holds_the_one_body_of_the_percentile(self):
        digest = digest_of_one_function(PERCENTILE_OWNER, PERCENTILE_NAME)
        found = holders(digest, sites())
        self.assertEqual(['%s %s' % (PERCENTILE_OWNER, PERCENTILE_NAME)], found,
                         'the percentile rule must stand in one module, and it stands in %s'
                         % found)

    def test_the_second_reader_holds_the_owner_and_not_a_copy(self):
        self.assertIs(ball_association_audit._percentile,
                      ball_association_ab._percentile,
                      'src/ball_association_ab.py holds a second percentile body')

    def test_the_percentile_reader_answers_the_owner(self):
        for values, fraction, want in (([], .9, None),
                                       ([5.0], .9, 5.0),
                                       ([1.0, 2.0, 3.0, 4.0], .9, 4.0),
                                       ([4.0, 3.0, 2.0, 1.0], .9, 4.0),
                                       ([-3.0, -2.0, -1.0], .5, -2.0)):
            with self.subTest(values=values, fraction=fraction):
                self.assertEqual(want, ball_association_ab._percentile(values, fraction))

    def test_the_second_reader_names_the_audit_in_its_source(self):
        source = (ROOT / 'src/ball_association_ab.py').read_text(encoding='utf-8')
        self.assertIn('_percentile = audit._percentile', source,
                      'src/ball_association_ab.py must read the audit name')


class OneBodyUnderTheTreesTest(unittest.TestCase):
    """One body of the summary and one body of the percentile, and a planted copy."""

    def test_one_body_of_the_summary_stands_under_the_source_trees(self):
        digest = digest_of_one_function(OWNER, OWNER_NAME)
        found = holders(digest, sites())
        self.assertEqual(['%s %s' % (OWNER, OWNER_NAME)], found,
                         'the summary body lives in %s, and its one home is %s %s'
                         % (found, OWNER, OWNER_NAME))

    def test_one_body_of_the_percentile_stands_under_the_source_trees(self):
        digest = digest_of_one_function(PERCENTILE_OWNER, PERCENTILE_NAME)
        found = holding_modules(digest, sites())
        self.assertEqual([PERCENTILE_OWNER], found,
                         'the percentile body lives in %s, and its one home is %s'
                         % (found, PERCENTILE_OWNER))

    def test_the_walk_of_the_summary_body_is_not_empty(self):
        """A walk over no module proves nothing, so the owner must appear."""
        digest = digest_of_one_function(OWNER, OWNER_NAME)
        self.assertTrue(holders(digest, sites()),
                        'the walk found no body of the summary, so it proves nothing')

    def test_the_walk_finds_a_planted_copy_of_the_summary_body(self):
        """A second body under another name is found by its statements.

        The planted text is the owner's own body under the name
        ``summary_copy``.  The fingerprint of the body and not the name of the
        function decides, so the walk sees the copy.  The owner keeps its own
        home, because the walk reports two sites and not one.
        """
        digest = digest_of_one_function(OWNER, OWNER_NAME)
        source = (ROOT / OWNER).read_text(encoding='utf-8')
        planted = body_sites(planted_source(source), PLANTED_MODULE)
        self.assertEqual(1, len(planted), 'the planted text holds one function')
        self.assertEqual(digest, planted[0][3],
                         'the planted copy is not the owner body, so this case proves nothing')
        self.assertNotEqual(OWNER_NAME, planted[0][2],
                            'the planted name must differ from the owner name')
        found = holders(planted[0][3], sites() + planted)
        self.assertEqual(sorted(['%s %s' % (OWNER, OWNER_NAME),
                                 '%s %s' % (PLANTED_MODULE, planted[0][2])]),
                         found,
                         'the walk found %s, and it must find the owner and the copy' % found)


if __name__ == '__main__':
    unittest.main()
