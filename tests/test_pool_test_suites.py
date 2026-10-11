"""The javascript suites the documents state are the suites `scripts/pool-test.sh` runs.

`PRODUCT.md` once named two javascript suites beside a `node --test` command that collects
no test here, while the runner ran three.  Nothing read the sentence, so the drift was
invisible.  This module reads both sides: the runner's own loop is the list, and every
document that `PRODUCT.md` names as a source and that runs a suite must name every suite of
it.  A fourth suite on disk needs one edit in the runner; the report below then names the
document that fell behind.

The walk reads the markdown sources of the status sentence of `PRODUCT.md`.  It does not
read the documents of one past run, such as `docs/tonight-stage9-proof.md` and
`docs/public-board.md`.  Those lines are a record of the suites that ran, not a command for
the next reader.
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

#: The sentence of `PRODUCT.md` that names the documents behind it.
SOURCES = re.compile(r'^.*Status truth is .*$', re.M)

#: A suite name in prose is a path, so the search is anchored on the separator.
PATH = re.compile(r'tests/[^\s;`]+\.js')

#: A markdown path inside the sources sentence, in backticks.  The sentence also names
#: `annotator/ops.js`, and a code file holds no document command.
DOC = re.compile(r'`(?P<path>[^`\s]+\.md)`')


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


def named_documents():
    """The markdown documents the sources sentence of `PRODUCT.md` names."""
    sentence = SOURCES.search(PRODUCT.read_text())
    if sentence is None:
        raise AssertionError('PRODUCT.md holds no sentence about its sources: %s' % (PRODUCT,))
    return DOC.findall(sentence.group(0))


def suite_lines(text):
    """The line number and the suites of every line of one text that runs a suite.

    A line runs a suite when it starts with the word ``node`` and names a
    ``tests/*.js`` path.
    """
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.lstrip().startswith('node'):
            continue
        suites = PATH.findall(line)
        if suites:
            found.append((number, suites))
    return found


def behind_reports(name, text, named):
    """The report of every suite line of one document that misses a suite of the runner."""
    found = []
    for number, suites in suite_lines(text):
        if suites != named:
            found.append('%s:%d: names %r, the runner runs %r' % (name, number, suites, named))
    return found


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

    def test_every_source_document_that_runs_a_suite_names_them_all(self):
        named = runner_suites()
        found = []
        for name in named_documents():
            found += behind_reports(name, (ROOT / name).read_text(encoding='utf-8'), named)
        self.assertEqual([], found,
                         'these documents fell behind the runner: %r' % (found,))

    def test_the_walk_reads_the_two_documents_that_run_a_suite(self):
        read = [name for name in named_documents()
                if suite_lines((ROOT / name).read_text(encoding='utf-8'))]
        self.assertEqual(['docs/handoff.md', 'docs/corner-pocket-operations.md'], read,
                         'the PRODUCT.md sources that run a javascript suite')

    def test_the_walk_sees_a_planted_document(self):
        named = runner_suites()
        planted = '## setup\n\n```sh\nnode tests/test_ops.js\n```\n'
        self.assertEqual(
            ["planted.md:4: names ['tests/test_ops.js'], the runner runs %r" % (named,)],
            behind_reports('planted.md', planted, named),
            'the walk of the case above must see a document that misses a suite')
        whole = planted.replace('node tests/test_ops.js', 'node ' + ' && node '.join(named))
        self.assertEqual([], behind_reports('planted.md', whole, named),
                         'a document that names every suite answers nothing')


if __name__ == '__main__':
    unittest.main()
