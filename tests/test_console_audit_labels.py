"""The console's audit labels against the operations GET /api/actions publishes.

``annotator/ops.js`` holds one sentence pair per action name in ``auditActions``, and
``auditLine`` falls back to the raw action name when a row is missing, so an operation
without a row reaches the operator as ``vod_link``.  The server publishes its own list at
GET /api/actions out of ``annotator/operations.py``, and nothing compared the two: three
operations the console itself sends - ``vod_link``, ``vod_unlink``, ``entrant_add_late`` -
were missing from the table until this round added them.

The list compared here is the served one, read through the seam
``tests/test_unified_server.py`` uses, ``Backend(Path(self.temp.name))`` and
``self.backend.get(['api', 'actions'], ReadQuery({}))``.  A second copy of the route list
in this module would drift the way the console did, so this module holds none.

The rendering case asks the console itself, through ``node -e``, because a python read of
the table can only restate the table and the claim there is that ``auditLine`` prints the
sentence.  node is required, and the case fails without it rather than skipping: a
run-time skip branch is a budgeted cost in this checkout (``tests/test_suite_inventory.py``
counts the run-time skip call sites under ``tests/`` and holds their number).
"""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from annotator.unified_server import Backend, ReadQuery

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / 'annotator' / 'ops.js'
SERVER = ROOT / 'annotator' / 'unified_server.py'
#: The head of the console's one-line table, and the shape of a row inside it.
TABLE_HEAD = 'const auditActions={'
ROW = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*\[([^\]]*)\]")
LABEL = re.compile(r"'(?:\\.|[^'\\])*'")
#: The three operations this round added to the table, the ones the console sends itself.
ADDED = ('entrant_add_late', 'vod_link', 'vod_unlink')


def console_labels(source=None):
    """The console's rows, ``{action: [english, chinese]}``, read from annotator/ops.js.

    The object body is found by counting braces, so the rows are the ones inside the
    table and not the whole line.  A table that moved or was renamed is a named failure:
    a case that compares two empty sets would pass for the wrong reason.
    """
    text = CONSOLE.read_text(encoding='utf-8') if source is None else source
    if TABLE_HEAD not in text:
        raise AssertionError(f'annotator/ops.js holds no {TABLE_HEAD!r}: the audit-label table '
                             'was renamed or moved, so this module reads nothing')
    start = text.index(TABLE_HEAD) + len(TABLE_HEAD)
    depth, end = 1, start
    while depth and end < len(text):
        depth += {'{': 1, '}': -1}.get(text[end], 0)
        end += 1
    if depth:
        raise AssertionError('the auditActions object in annotator/ops.js does not close')
    rows = {}
    for found in ROW.finditer(text[start:end - 1]):
        rows[found.group(1)] = [ast.literal_eval(label) for label in LABEL.findall(found.group(2))]
    return rows


def rendered_lines(actions):
    """The audit line annotator/ops.js itself prints for each action, per language."""
    node = shutil.which('node')
    if not node:
        raise AssertionError('node is required to ask annotator/ops.js how it renders an audit line')
    done = subprocess.run([node, '-e', NODE_DRIVER % json.dumps(str(CONSOLE))],
                          input=json.dumps({'actions': list(actions)}),
                          capture_output=True, text=True, timeout=60)
    if done.returncode:
        raise AssertionError(f'node could not render the console audit lines:\n{done.stderr}')
    return json.loads(done.stdout)


#: node driver: load the console the way the page loads it, then print the line it prints.
NODE_DRIVER = """
const fs = require('node:fs'), vm = require('node:vm');
globalThis.window = {addEventListener() {}, removeEventListener() {}};
globalThis.localStorage = {getItem: () => null, setItem() {}, removeItem() {}};
globalThis.document = {addEventListener() {}, querySelector: () => null, querySelectorAll: () => []};
globalThis.location = {hash: '', href: 'http://console/', pathname: '/', search: ''};
globalThis.history = {replaceState() {}, pushState() {}};
globalThis.navigator = {userAgent: 'node'};
globalThis.requestAnimationFrame = () => 0;
globalThis.setInterval = () => 0;
globalThis.clearInterval = () => {};
globalThis.setTimeout = () => 0;
globalThis.clearTimeout = () => {};
vm.runInThisContext(fs.readFileSync(%s, 'utf8'));
const ops = globalThis.window.OpsConsole.attach({});
const asked = JSON.parse(fs.readFileSync(0, 'utf8'));
ops.data = {revision: 1, settings: {}, tournament: {raceTo: 7, entrants: [], matches: []}, players: [], history: []};
const answers = {};
for (const lang of ['en', 'zh']) {
  ops.lang = lang;
  answers[lang] = {};
  for (const action of asked.actions) {
    answers[lang][action] = ops.auditLine({action, createdAt: '2026-10-03T05:23:40.400503+00:00', revision: 75});
  }
}
process.stdout.write(JSON.stringify(answers));
"""


class ConsoleLabelCase(unittest.TestCase):
    """One backend and one reading of the console, shared by the cases below."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backend = Backend(Path(self.temp.name))
        self.served = list(self.backend.get(['api', 'actions'], ReadQuery({}))['operations'])
        self.labels = console_labels()


class ServedOperationsTests(ConsoleLabelCase):
    """GET /api/actions names the actions the console has to label."""

    def test_the_console_labels_every_operation_the_server_publishes(self):
        missing = [name for name in self.served if name not in self.labels]
        extra = [name for name in self.labels if name not in self.served]
        self.assertTrue(self.served, 'GET /api/actions published no operation names: the route or its query changed')
        self.assertTrue(self.labels, 'annotator/ops.js holds no audit-label row: the table moved or was renamed')
        self.assertEqual(
            (missing, extra), ([], []),
            'GET /api/actions and the console audit-label table name different actions. '
            f'Missing from annotator/ops.js: {missing}. Named by annotator/ops.js and not served: {extra}. '
            'A missing row prints the raw action name in the audit log; add it to auditActions in '
            'annotator/ops.js, in the style of the rows around it.')


class EveryRowTests(ConsoleLabelCase):
    """A row is a pair of sentences, one per language, and never the enum."""

    def test_every_row_is_two_sentences_and_never_the_action_name(self):
        for action, row in sorted(self.labels.items()):
            self.assertEqual(2, len(row), f'{action} is not a pair of labels: {row!r}')
            self.assertNotIn(action, row,
                             f'{action} is a label of its own row, so the audit log prints the backend enum '
                             f'instead of a sentence: {row!r}')
            for label, language in zip(row, ('en', 'zh')):
                self.assertIsInstance(label, str, f'the {language} label of {action} is not a string: {label!r}')
                self.assertTrue(label.strip(), f'the {language} label of {action} is empty: {row!r}')


class RenderedLineTests(ConsoleLabelCase):
    """The three rows this round added, printed by the console's own auditLine."""

    def test_the_added_actions_read_as_sentences_in_both_languages(self):
        lines = rendered_lines(ADDED)
        for action in ADDED:
            row = self.labels.get(action)
            self.assertIsNotNone(row, f'{action} has no row in the console audit-label table, so its audit line '
                                      'prints the enum')
            for index, language in ((0, 'en'), (1, 'zh')):
                line = lines[language][action]
                self.assertNotIn(action, line, f'the console prints the raw {action} name in {language}: {line}')
                self.assertIn(row[index], line,
                              f'the console does not print the {language} label {row[index]!r} for {action}: {line}')


class RouteCommentTests(unittest.TestCase):
    """The comment on the route that serves the list names the reader that exists."""

    def test_the_actions_route_names_this_module_as_its_reader(self):
        source = SERVER.read_text(encoding='utf-8')
        route = source[source.index("if parts == ['api', 'actions']:"):]
        comment = route[:route.index('return ')]
        self.assertIn(Path(__file__).name, comment,
                      'the GET /api/actions comment no longer names the reader that exists, and no console reads '
                      'that route: tests/test_console_audit_labels.py is the reader')


if __name__ == '__main__':
    unittest.main()
