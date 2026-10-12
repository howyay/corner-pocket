"""The built-in dataset id has one owner in the registry, and one name in the console.

Round 91 found the id ``vod30`` spelled inside the route paths of ``annotator/app.js``.  Ten
sites built a URL.  One anchors route carried two spellings of the same id:
``/api/vod30/anchors`` and ``/api/${enc('vod30')}/anchors``.  A rename of the recording then
needed one edit at each site.  A site that missed the edit fetched a route that does not exist.

The registry ``src/datasets.py`` owns the word.  :data:`src.datasets.STATIC` holds one key per
built-in recording, and ``src/datasets.py:35`` is that statement.  The console now states the
same word once, in the ``BUILT_IN_DATASET`` constant of ``annotator/app.js``, and reads that
name at every route path of the built-in dataset.  The one service gate for the same word is
the ``_vod30`` method of ``annotator/unified_server.py`` (line 2325).

The cases below hold three statements:

* the console holds one declaration, and that declaration carries the registry key;
* every route path of the built-in dataset answers the URL this console built before the
  repair, byte for byte (``HISTORIC`` is that record, in file order);
* no route path of the console spells the id again, and the scan sees a planted copy.

The scan reads the text of the console file.  A test that states an expectation is not shipped
code, so ``annotator/app.js`` is the only file under test.

Do not weaken a check to make a change pass.
"""
import pathlib
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.datasets import STATIC

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSOLE = 'annotator/app.js'
NAME = 'BUILT_IN_DATASET'
DATASET = 'vod30'
#: The one declaration of the local name, with the value it must carry.
DECLARATION = re.compile(r'^const ' + NAME + r' = (.+);$', re.MULTILINE)
#: A request path of the console: the text from ``/api/`` to the end of the literal.  One
#: ``${...}`` group counts as one unit, so a path that interpolates ``enc('vod30')`` is read as
#: one path and its literal is seen.
PATH = re.compile(r"/api/(?:\$\{[^}\n]*\}|[^\s'\"`])*")

#: The route paths of the built-in dataset, byte for byte as this console built them before
#: round 91, in file order.  Only the id moved.  A reader that answers ``BUILT_IN_DATASET``
#: with the registry key must get these ten URLs back, in this order.  A site that leaves the
#: record fails :meth:`AppRouteOwnerTests.test_every_dataset_route_path_answers_the_historic_url`,
#: and the record is the audit trail of the repair.
HISTORIC = (
    '/api/vod30/anchors?t=${enc(t)}',
    '/api/vod30/tracklets',
    '/api/vod30/tracks?win=${enc(win)}&t=${enc(t)}',
    '/api/vod30/seeds',
    "/api/${enc('vod30')}/anchors?t=${enc(state.anchors.t)}",
    '/api/vod30/seeds',
    '/api/vod30/anchors',
    '/api/vod30/rebuild',
    '/api/vod30/rebuild',
    '/api/vod30/tracklets',
)


def source_of(path=None) -> str:
    """The text under test: the console file, or one planted file."""
    return (pathlib.Path(path) if path else ROOT / CONSOLE).read_text(encoding='utf-8')


def route_paths(source: str) -> list:
    """Every request path of the console, in file order."""
    return PATH.findall(source)


def answered(path: str) -> str:
    """The URL one path builds when the local name answers the registry key.

    The console interpolates the name, alone or through ``enc``.  This reader answers both
    spellings, so a named path and the path of the repair compare as text.
    """
    return (path.replace('${enc(' + NAME + ')}', "${enc('" + DATASET + "')}")
                .replace('${' + NAME + '}', DATASET))


def spelled_problems(source: str) -> list:
    """A line for each request path that spells the built-in id instead of reading the name."""
    problems = []
    for path in route_paths(source):
        if DATASET in path:
            problems.append(f'{path!r} spells {DATASET!r}; the name of the id is {NAME}, in {CONSOLE}')
    return problems


def route_problems(source: str) -> list:
    """A line for each route path of the built-in dataset that moved, in file order.

    The record is read from the paths that name the local name.  A path that spells the id
    instead is no site of this record, so it leaves the record short.  That second defect is
    the subject of :func:`spelled_problems`.
    """
    found = [answered(path) for path in route_paths(source) if NAME in path]
    problems = []
    for index, historic in enumerate(HISTORIC):
        if index >= len(found):
            problems.append(f'site {index + 1} ({historic!r}) is gone')
        elif found[index] != historic:
            problems.append(f'site {index + 1} answers {found[index]!r}, and it built {historic!r}')
    for extra in found[len(HISTORIC):]:
        problems.append(f'the record holds no site for {extra!r}')
    return problems


class AppRouteOwnerTests(unittest.TestCase):
    def test_the_console_holds_the_one_registry_key(self):
        declarations = DECLARATION.findall(source_of())
        expected = "'" + DATASET + "'"
        problems = []
        if declarations != [expected]:
            problems.append(f'{CONSOLE} declares {NAME} as {declarations!r}, and the one '
                            f'declaration of the built-in id is {expected!r}')
        if DATASET not in STATIC:
            problems.append(f'src/datasets.py STATIC holds no {DATASET!r}: {sorted(STATIC)!r}')
        self.assertEqual([], problems,
                         'the local name of the built-in dataset drifted:\n' + '\n'.join(problems))

    def test_no_route_path_spells_the_id_again(self):
        problems = spelled_problems(source_of())
        self.assertEqual([], problems,
                         'a route path of the console spells the built-in id:\n' + '\n'.join(problems))

    def test_every_dataset_route_path_answers_the_historic_url(self):
        problems = route_problems(source_of())
        self.assertEqual([], problems,
                         'a route path of the built-in dataset moved:\n' + '\n'.join(problems))

    def test_the_scan_sees_a_planted_route_path(self):
        with tempfile.TemporaryDirectory() as folder:
            planted = pathlib.Path(folder) / 'reader.js'
            planted.write_text("const u = '/api/vod30/tracklets';\n", encoding='utf-8')
            problems = spelled_problems(source_of(planted))
        self.assertNotEqual([], problems,
                            'the scan did not see a planted path; it answered ' + repr(problems))
        self.assertTrue(any('/api/vod30/tracklets' in problem for problem in problems),
                        'the report does not name the planted path; it answered ' + repr(problems))


if __name__ == '__main__':
    unittest.main()
