"""One home for the Twitch GraphQL endpoint, and a report for every copy.

``annotator/twitch_source.py`` holds ``GQL_ENDPOINT`` and the live resolver reads that name
through its own module global.  The three VOD calls read the name through the ``live``
alias: ``annotator/twitch_vod_source.py:230``, ``:278`` and ``:306``.  The endpoint used to
stand four times as a literal - once in the live resolver and once at each of those three
sites - and the three VOD copies had no reader.  The fake transport of
``tests/test_twitch_vod_source.py`` (line 64) records the URL of every call, but every case
there reads only the payload, so a path edit on one VOD site left the other two stale and
every suite stayed green.

This guard reads the ``*.py`` source of the project.  It reports each code string equal to
the endpoint, and it reports each read of ``GQL_ENDPOINT`` that happens in a module which is
not a named reader.  The reading follows the import graph: a module that binds ``live`` to
``annotator.twitch_source`` and reads ``live.GQL_ENDPOINT`` is a reader of the home, and a
module that reaches the constant by any other name is still a reader of the home.  A comment
or a docstring that names the endpoint is not a copy: only a value the interpreter can read
reports.  One case measures a VOD request, so the guard proves the shared name is live, not
only declared.

Run: PYTHONPATH=. .venv/bin/python -B tests/test_twitch_endpoint_owner.py
"""
import ast
import inspect
import io
import tokenize
import unittest
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

from annotator import twitch_source as live
from annotator import twitch_vod_source as vod

ROOT = Path(__file__).resolve().parents[1]

#: This module hunts for the endpoint, so it cannot report a copy inside itself.
SELF = Path(__file__).name
#: First path parts that hold no project source.
SKIPPED_TOP_LEVEL = ('.git', '.venv', 'node_modules', 'out', '__pycache__',
                     'data', 'logs', 'fixtures')

#: The one module that may hold the endpoint string, relative to the root.
HOME = 'annotator/twitch_source.py'
#: The import name of the home module, for the import graph the walk follows.
HOME_MODULE = 'annotator.twitch_source'
#: The name of the endpoint inside the home.
CONSTANT = 'GQL_ENDPOINT'
#: The alias under which the home module is imported by every reader.
HOME_ALIAS = 'live'
#: The endpoint the home must keep.  This is a deliberate pin, not a copy of the home value.
#: A guard that reads the home and compares the home with itself stays green when someone
#: edits the value, and that edit is the one event this row exists to report.
CANONICAL_ENDPOINT = 'https://gql.twitch.tv/gql'

#: The one code string of the home module that may hold the endpoint: the definition of the
#: constant itself, at the line the walk reports.
HOME_DEFINITION_LINE = 422

#: Every reader of the home name in the live tree: ``module -> [(line, how the site reads), ...]``.
#: ``GQL_ENDPOINT`` alone is a site inside the home module, which reads its own global.
#: The live resolver posts the persisted query, and the VOD path makes three calls through
#: the alias it already holds.
EXPECTED_READERS = {
    HOME: [(380, CONSTANT)],
    'annotator/twitch_vod_source.py': [(230, HOME_ALIAS + '.' + CONSTANT),
                                       (278, HOME_ALIAS + '.' + CONSTANT),
                                       (306, HOME_ALIAS + '.' + CONSTANT)],
}

#: Every reader site of the live tree, as ``"<path>:<line>"``, in text order.
EXPECTED_SITES = sorted('%s:%d' % (module, line)
                        for module, rows in EXPECTED_READERS.items() for line, _ in rows)

#: Code strings equal to the endpoint that live in files this row does not own.  Each row is
#: ``(path, line, the source text of that line, stripped)``.  Every row is a test double of a
#: URL; none of them drives a second production call.  The home holds one endpoint string, the
#: definition of the constant, so no row names the home.  The guard states each row and fails
#: when a row moves or changes text, so an edit to a silencing row reports the new text.
#: ``tests/test_twitch_fetch.py`` and ``tests/test_twitch_headers_owner.py`` are outside the
#: scope of this repair, so they keep their spelling.
KNOWN_COPIES = (
    ('tests/test_twitch_fetch.py', 21, "API_URL = 'https://gql.twitch.tv/gql'"),
    ('tests/test_twitch_headers_owner.py', 238,
     "vod._raw('https://gql.twitch.tv/gql', {'query': '{ me { id } }'})"),
    ('tests/test_twitch_headers_owner.py', 261,
     "live._request('https://gql.twitch.tv/gql',"),
)


def _module_label(path):
    """``annotator/twitch_source.py`` for a path under the root; else None."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return None


def _is_project_file(path):
    """True for a project ``*.py`` file this guard reads, with no generated tree."""
    label = _module_label(path)
    if label is None or path.name == SELF:
        return False
    return Path(label).parts[0] not in SKIPPED_TOP_LEVEL


@lru_cache(maxsize=1)
def _project_sources():
    """One ``{module: source}`` map of every project file, in a stable order."""
    return {_module_label(path): path.read_text(encoding='utf-8')
            for path in sorted(ROOT.rglob('*.py')) if _is_project_file(path)}


@lru_cache(maxsize=1)
def _endpoint_text():
    """The one allowed endpoint string of the home module, read from the live source."""
    return live.GQL_ENDPOINT


def _endpoint_sites(source, endpoint):
    """Every code string of one module that holds the endpoint, with its line.

    A docstring is a string constant too, and it may quote the endpoint as prose.  This walk
    drops the docstring of every module, class and function, so only a real value reports.
    """
    sites = []

    def _walk_body(body):
        for index, statement in enumerate(body):
            if index == 0 and isinstance(statement, ast.Expr):
                first = getattr(statement, 'value', None)
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    continue
            _visit(statement)

    def _visit(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and endpoint in node.value:
                sites.append((node.lineno, node.value))
            return
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            _walk_body(node.body)
            return
        for child in ast.iter_child_nodes(node):
            _visit(child)

    _visit(ast.parse(source))
    return sorted(sites)


def _imported_module(module, level):
    """The absolute name one ``from`` import names.

    ``from annotator import twitch_source`` has no level.  A relative import inside
    ``annotator/`` may stand as ``from . import twitch_source`` or as ``from annotator import
    twitch_source``; the walk reads the one name the interpreter resolves either way.
    """
    if not level:
        return module or ''
    package = HOME_MODULE.split('.')[:-1]
    if level > len(package):
        return module or ''
    return '.'.join(package[:len(package) - level + 1] + ([module] if module else []))


def _from_clauses(tree):
    """Every ``(resolved module, name, local name, line)`` row of a parsed module."""
    pairs = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        resolved = _imported_module(node.module, node.level)
        for alias in node.names:
            pairs.append((resolved, alias.name, alias.asname or alias.name, node.lineno))
    return pairs


def _home_names(tree):
    """The local names of one parsed module that point at the home module."""
    names = set()
    for resolved, name, local, line in _from_clauses(tree):
        if (resolved + '.' + name if resolved else name) == HOME_MODULE:
            names.add(local)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == HOME_MODULE:
                    names.add((alias.asname or alias.name).split('.')[0])
    return names


def _owner_reads(source):
    """Every read of the home constant in one source, as ``(line, spelling)`` rows.

    A read through the module object (``live.GQL_ENDPOINT``) and a read through a direct
    import of the name both report, so a second import path cannot hide a reader.
    """
    tree = ast.parse(source)
    names = _home_names(tree)
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr != CONSTANT:
            continue
        if isinstance(node.value, ast.Name) and node.value.id in names:
            rows.append((node.lineno, node.value.id + '.' + CONSTANT))
    for resolved, name, local, line in _from_clauses(tree):
        if name == CONSTANT and (resolved or '') == HOME_MODULE:
            rows.append((line, local))
    return sorted(rows)


def _text_of(source, line):
    """The one source line of a site, stripped of its indentation."""
    lines = source.splitlines()
    return lines[line - 1].strip() if 0 < line <= len(lines) else ''


def _site_row(module, line, source):
    """One ``"<file>:<line>: <the exact source text>"`` row of a report."""
    return '%s:%d: %s' % (module, line, _text_of(source, line))


def _home_string_is_the_constant(source, line):
    """True for the definition line of the home constant, the one allowed home string."""
    return CONSTANT + ' =' in _text_of(source, line)


def find_copies(files, endpoint=None):
    """The report lines of one ``{module: source}`` map: a copy, or an unnamed reader.

    A copy is a code string that holds the endpoint in a module that is not the home, or a
    string inside the home that is not the definition of the constant.  An unnamed reader is
    a read of the home constant in a module that is not a named reader.  Every row starts
    with ``path:line`` and then states the offending source text.
    """
    endpoint = _endpoint_text() if endpoint is None else endpoint
    copies = []
    for module in sorted(files):
        source = files[module]
        for line, value in _endpoint_sites(source, endpoint):
            if module == HOME:
                if _home_string_is_the_constant(source, line):
                    continue
                copies.append('%s: spells a second endpoint string %r; read %s for every call'
                              % (_site_row(module, line, source), value, CONSTANT))
            else:
                copies.append('%s: spells the endpoint %r; read %s of %s'
                              % (_site_row(module, line, source), value, CONSTANT, HOME))
        for line, spelling in _owner_reads(source):
            if module in EXPECTED_READERS:
                if (line, spelling) not in EXPECTED_READERS[module]:
                    copies.append('%s: reads %s; the known sites of this module are %r'
                                  % (_site_row(module, line, source), spelling,
                                     EXPECTED_READERS[module]))
            else:
                copies.append('%s: reads %s; this module is not a named reader of %s'
                              % (_site_row(module, line, source), spelling, HOME))
    return copies


def _findings():
    """Every copy or drift line in the live tree, in file order."""
    return find_copies(_project_sources())


def _reported_copies():
    """The report lines of the live tree, as ``(path, line, the source text of that line)``."""
    rows = []
    for finding in _findings():
        path, line = finding.split(':', 2)[0], int(finding.split(':', 2)[1])
        rows.append((path, line, _text_of(_project_sources()[path], line)))
    return sorted(rows)


def _true_sites():
    """Every read of the home name in the live tree, as ``"<file>:<line>"``."""
    rows = []
    for module, source in _project_sources().items():
        if module == HOME:
            # The home reads its own global by the bare name, so the walk cannot see it as
            # an attribute read.  The site is the call the named reader rows state.
            for line, how in EXPECTED_READERS[HOME]:
                rows.append('%s:%d' % (module, line))
            continue
        for line, spelling in _owner_reads(source):
            rows.append('%s:%d' % (module, line))
    return sorted(rows)


def _copies_by_tokenize(source, endpoint):
    """A second reading of one source text: every endpoint string token, with its line.

    The walk above reads the syntax tree.  This reading splits the text into tokens, so the
    two readings agree on a real copy and on a planted one, and a comment never reports.
    """
    found = []
    try:
        stream = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in stream:
            if token.type == tokenize.STRING and endpoint in token.string:
                found.append((token.start[0], token.string))
    except (tokenize.TokenError, IndentationError):
        return found
    return found


def _source_of(module):
    """The loaded source of one imported module, for the measured request case."""
    return Path(inspect.getsourcefile(module)).read_text(encoding='utf-8')


class _Reply:
    """The smallest context manager a ``with`` statement accepts, with a status."""

    def __init__(self, body):
        self._body = body
        self.status = 200

    def read(self, size=None):
        return self._body if size is None else self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _recording_opener(target, calls, body=b'{"data": null}'):
    """Patch ``build_opener`` of ``target`` with an opener that records each request."""
    def _open(request, timeout=None):
        calls.append(request)
        return _Reply(body)
    opener = type('_Opener', (), {'open': staticmethod(_open)})
    return patch(target, lambda *handlers: opener())


class EndpointOwner(unittest.TestCase):
    """The endpoint stands once, in the home module, and every site reads that name."""

    def test_the_home_publishes_one_endpoint_string(self):
        """The guard reads a non-empty value, so an empty home cannot pass by accident."""
        self.assertIsInstance(_endpoint_text(), str)
        self.assertTrue(_endpoint_text().strip())

    def test_the_home_keeps_the_pinned_endpoint(self):
        """The bite case: an edit to the home value reports here, with both values."""
        self.assertEqual(CANONICAL_ENDPOINT, _endpoint_text(),
                         'the home names %r; the guard pins %r'
                         % (_endpoint_text(), CANONICAL_ENDPOINT))

    def test_the_home_states_the_endpoint_once(self):
        """The home holds one definition, and the walk reads it."""
        source = _project_sources()[HOME]
        sites = _endpoint_sites(source, _endpoint_text())
        self.assertEqual(1, len(sites), 'the home states the endpoint on %r' % (sites,))
        allowed = [line for line, _ in sites if _home_string_is_the_constant(source, line)]
        self.assertEqual([HOME_DEFINITION_LINE], allowed,
                         'the home defines the constant on %r' % (allowed,))
        self.assertEqual(_endpoint_text(), _text_of(source, HOME_DEFINITION_LINE).split('=')[1]
                         .strip().strip("'"))

    def test_the_home_resolver_reads_the_constant(self):
        """The live call site reads the name, and the guard reads that site's text."""
        line = EXPECTED_READERS[HOME][0][0]
        text = _text_of(_project_sources()[HOME], line)
        self.assertIn(CONSTANT, text)
        self.assertIn('_request(', text)
        self.assertNotIn("'http", text)
        self.assertNotIn('"http', text)

    def test_every_reader_reads_the_home_name(self):
        """No live module holds a stray copy or an unnamed reader.

        The three test doubles are outside this row, so their rows report as known strays.
        Every other reported row would name a live module.
        """
        known = {path for path, _, _ in KNOWN_COPIES}
        strays = [row for row in _findings() if row.split(':', 1)[0] not in known]
        self.assertEqual([], strays, '\n'.join(strays))

    def test_the_vod_document_request_carries_the_home_endpoint(self):
        """Measured check: the request the VOD path builds holds the one endpoint."""
        calls = []
        with _recording_opener('annotator.twitch_vod_source.build_opener', calls):
            vod.gql('{ me { id } }')
        self.assertEqual(1, len(calls))
        self.assertEqual(CANONICAL_ENDPOINT, calls[0].full_url)
        self.assertEqual('gql.twitch.tv', calls[0].host)

    def test_no_reader_module_holds_a_second_reader(self):
        """Each reader module reads the name at the lines this guard names, and only there."""
        for module, expected in sorted(EXPECTED_READERS.items()):
            if module == HOME:
                # The home reads its own global by the bare name, so no attribute read of
                # it exists; the call site above holds that line.
                self.assertEqual([], _owner_reads(_project_sources()[module]))
                continue
            with self.subTest(module=module):
                self.assertEqual(expected, _owner_reads(_project_sources()[module]))

    def test_the_three_test_doubles_are_the_only_known_copies(self):
        """The live tree reports the known copies, at those lines and with those texts."""
        self.assertEqual(sorted(KNOWN_COPIES), _reported_copies())

    def test_the_home_reports_no_copy(self):
        """The home holds one endpoint string, the definition, and reports no copy."""
        rows = [(path, line) for path, line, text in _reported_copies() if path == HOME]
        self.assertEqual([], rows, 'the home reports %r' % (rows,))


class TheWalk(unittest.TestCase):
    """The guard's own tools, checked, so a walk that reads nothing cannot pass."""

    def test_the_walk_reads_the_two_live_modules(self):
        """The two modules of this row are inside the walk, not skipped by a filter."""
        labels = set(_project_sources())
        self.assertIn(HOME, labels)
        self.assertIn('annotator/twitch_vod_source.py', labels)
        self.assertGreater(len(labels), 50)

    def test_the_walk_found_the_real_sites(self):
        """Live count: the scan sees every reader, so an empty scan cannot pass."""
        self.assertEqual(EXPECTED_SITES, _true_sites())
        self.assertGreaterEqual(len(_true_sites()), 4)

    def test_the_walk_sees_a_planted_copy(self):
        """Wrong-value check: the walk reports a file that spells the endpoint."""
        files = {'annotator/example_other.py': "API = '%s'" % CANONICAL_ENDPOINT}
        report = find_copies(files)
        self.assertEqual(1, len(report), report)
        self.assertIn('annotator/example_other.py:1', report[0])
        self.assertIn(CANONICAL_ENDPOINT, report[0])
        self.assertIn(HOME, report[0])

    def test_the_walk_ignores_a_docstring(self):
        """A docstring that names the endpoint is no copy."""
        files = {HOME: "API = '%s'" % CANONICAL_ENDPOINT,
                 'annotator/example_other.py': '"""%s"""\n' % CANONICAL_ENDPOINT}
        report = find_copies(files)
        self.assertEqual(1, len(report), report)
        self.assertIn(HOME + ':1', report[0])

    def test_the_walk_reports_a_second_reader(self):
        """A module that is not a named reader cannot read the home name."""
        files = {'annotator/example_other.py': "from annotator import twitch_source as live\n"
                                              "URL = live.%s" % CONSTANT}
        report = find_copies(files)
        self.assertEqual(1, len(report), report)
        self.assertIn('annotator/example_other.py:2', report[0])
        self.assertIn(CONSTANT, report[0])

    def test_the_walk_reports_a_reader_under_another_name(self):
        """A reader that binds the home to its own name still reports."""
        files = {'annotator/example_other.py': "from annotator import twitch_source as src\n"
                                              "URL = src.%s" % CONSTANT}
        report = find_copies(files)
        self.assertEqual(1, len(report), report)
        self.assertIn('annotator/example_other.py:2', report[0])

    def test_the_tokenize_reading_agrees_with_the_walk(self):
        """The second reading finds the same copy in the same line."""
        source = "A = 1\nB = '%s'\n" % CANONICAL_ENDPOINT
        self.assertEqual([(2, "'%s'" % CANONICAL_ENDPOINT)],
                         _copies_by_tokenize(source, CANONICAL_ENDPOINT))
        self.assertEqual([(2, CANONICAL_ENDPOINT)],
                         _endpoint_sites(source, CANONICAL_ENDPOINT))

    def test_the_walk_reads_a_live_module_that_states_the_name(self):
        """The loaded VOD module reads the home name on the three measured lines."""
        source = _source_of(vod)
        self.assertEqual([(230, 'live.GQL_ENDPOINT'), (278, 'live.GQL_ENDPOINT'),
                          (306, 'live.GQL_ENDPOINT')], _owner_reads(source))
        # The prose of the module may name the endpoint; no code string of it may.
        self.assertEqual([], _endpoint_sites(source, _endpoint_text()))


if __name__ == '__main__':
    unittest.main()
