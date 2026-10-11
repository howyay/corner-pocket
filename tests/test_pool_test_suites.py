"""The javascript suites `PRODUCT.md` states are the suites `scripts/pool-test.sh` runs.

`PRODUCT.md` once named two javascript suites beside a `node --test` command that collects
no test here, while the runner ran three.  Nothing read the sentence, so the drift was
invisible.  This module reads both sides: the runner's own loop is the list, and the
sentence must name every suite of it.  A fourth suite on disk needs one edit in the
runner; the report below then names the sentence that fell behind.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'scripts' / 'pool-test.sh'
PRODUCT = ROOT / 'PRODUCT.md'

#: The loop of the runner that names the javascript suites it runs.  The suite list is
#: every non-blank character before the ``; do``, which is one unambiguous run.
LOOP = re.compile(r'^  for suite in (?P<suites>[^\s;]+(?: [^\s;]+)*); do$', re.M)

#: The sentence of `PRODUCT.md` that names the javascript suites of the project.
SENTENCE = re.compile(r'^\s*- The test suites are .*$', re.M)

#: A suite name in prose is a path, so the search is anchored on the separator.
PATH = re.compile(r'tests/[^\s;`]+\.js')


def runner_suites():
    """The javascript suites of the runner, in the order its loop names them."""
    loop = LOOP.search(RUNNER.read_text())
    if loop is None:
        raise AssertionError('the runner holds no loop over javascript suites: %s' % (RUNNER,))
    return loop.group('suites').split()


def stated_suites():
    """The javascript suites the `PRODUCT.md` sentence names."""
    sentence = SENTENCE.search(PRODUCT.read_text())
    if sentence is None:
        raise AssertionError('PRODUCT.md holds no sentence about the test suites: %s' % (PRODUCT,))
    return PATH.findall(sentence.group(0))


class PoolTestSuiteInventoryTests(unittest.TestCase):
    def test_the_runner_runs_the_three_javascript_suites_of_the_repository(self):
        self.assertEqual(runner_suites(),
                         ['tests/test_ops.js', 'tests/test_board.js',
                          'tests/test_app_timeline.js'])

    def test_the_product_sentence_names_every_suite_the_runner_runs(self):
        named = runner_suites()
        self.assertEqual(stated_suites(), named,
                         'PRODUCT.md names %s; the runner runs %s' % (stated_suites(), named))

    def test_the_report_names_a_planted_suite_and_holds_its_tongue_otherwise(self):
        sentence = '  - The test suites are `PYTHONPATH=. .venv/bin/python -m unittest`.\n'
        self.assertEqual(PATH.findall(sentence), [], 'the report invented a suite')
        planted = sentence + '    The javascript suites are `tests/test_ops.js`.\n'
        self.assertEqual(PATH.findall(planted), ['tests/test_ops.js'],
                         'the report missed a named suite')
        self.assertEqual(SENTENCE.search(planted).group(0), sentence.rstrip('\n'))


if __name__ == '__main__':
    unittest.main()
