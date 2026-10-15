"""One owner for the route literals of the legacy review tool.

The legacy review tool is one page pair and one server.  The pages
``annotator/index.html`` and ``annotator/label.html`` call the server.  A route
literal stands on each side: once in a page, and once in the dispatch of
``annotator/server.py``.  Two files state one fact.  A rename on one side gives a
404 answer or an empty table, and no case reads a page route against the
dispatch.  So a case cannot see the drift.

A page cannot import a server name, and the server cannot import a page name.
This module is the closure.  It reads the three files as text and holds the two
sides equal.

Rule 1, the one-way rule.  Every route literal a page calls must be served by
the dispatch of ``annotator/server.py``.  The failure message is
``file:line route``, so a reader sees the unserved call.

Rule 2, the report rule.  A route the dispatch serves and no page calls is
reported, not failed.  The legacy tool serves two page routes that no page
literal holds.

The two prefix rules of the dispatch serve a family: ``/ctx/`` and ``/crops/``.
A page literal that starts with one of those strings is served.  A page template
such as ``/ctx/${c.ctx}`` stands for many values, so this module also names one
value of it for the message.

This module never edits a page and never edits the server.  The three production
files are read only.
"""
import re
import tempfile
import unittest
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]

PAGES = ('annotator/index.html', 'annotator/label.html')
SERVER = 'annotator/server.py'

# One route-shaped run of page text, with the value of a template expression.
PAGE_RUN = re.compile(r"(/(?:api|ctx|crops)/)\$\{[^}]*\}|(/(?:api|ctx|crops)/[A-Za-z0-9._-]{0,40})")

# One comparison of the dispatch against a route literal.
DISPATCH_STEP = re.compile(
    r"self\.path\s*(?:(==|!=)\s*(['\"])(/[^'\"]*)\2"
    r"|\.startswith\(\s*(['\"])(/[^'\"]*)\4)"
)

DEF_STEP = re.compile(r"^\s*def\s+(do_GET|do_POST)\s*\(")
REUSE_STEP = re.compile(r"^\s*elif\b")

PAGE_VALUE = '1'

# One small page for the planted cases.  It calls one route the dispatch serves,
# and its line 64 holds the route the plant renames.
PAGE_SAMPLE = (
    "const routes = [];\n"
    * 63
    + "routes.push('/api/actors');\n"
)


class Route(NamedTuple):
    """One route name, the first page line that calls it, and that page line."""

    name: str
    line: int
    value: str


class DispatchRule(NamedTuple):
    """One dispatch step: its route name, its server line, and its kind."""

    name: str
    line: int
    kind: str


def page_runs(text):
    """Every route-shaped run of one page text, in file order, as (line, run)."""
    found = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for match in PAGE_RUN.finditer(line):
            found.append((line_number, match.group(0)))
    return found


def page_route_records(name, text):
    """Every route one page calls, with its first line.  One route stands once."""
    routes = {}
    for line_number, run in page_runs(text):
        route_name = run.replace('${c.ctx}', '${value}').replace('${cropName}', '${value}')
        if route_name not in routes:
            routes[route_name] = Route(route_name, line_number, run)
    return tuple(routes[key] for key in sorted(routes))


def page_routes(path):
    """Every route one page file calls, with its path, its line, and its text."""
    return tuple(
        (path, route, read(path))
        for route in page_route_records(path, read(path))
    )


def dispatch_rules(name, text):
    """Every route the dispatch of one server text names, with its line and kind.

    An equality step is an exact route.  A ``startswith`` step is a prefix rule,
    and it serves the family of its literal.  A ``!=`` step refuses every other
    path, so it serves the one route it names, as a guard.
    """
    rules = []
    method = None
    for line_number, line in enumerate(text.splitlines(), 1):
        step = DEF_STEP.match(line)
        if step:
            method = step.group(1)
            continue
        if method is None:
            continue
        if REUSE_STEP.match(line) and not DISPATCH_STEP.search(line):
            continue
        for match in DISPATCH_STEP.finditer(line):
            if match.group(1) == '==':
                rules.append(DispatchRule(match.group(3), line_number, 'exact'))
            elif match.group(1) == '!=':
                rules.append(DispatchRule(match.group(3), line_number, 'guard'))
            elif match.group(4):
                rules.append(DispatchRule(match.group(5), line_number, 'prefix'))
    return tuple(rules)


def dispatch_route(rules, route):
    """The server line that serves one page route, or None.

    A page template becomes one value.  ``/ctx/${c.ctx}`` gives the value
    ``/ctx/1``, and the prefix rule ``/ctx/`` serves it.
    """
    value = route.value.replace('${c.ctx}', PAGE_VALUE).replace('${cropName}', PAGE_VALUE)
    for rule in rules:
        if rule.kind in ('exact', 'guard') and rule.name == route.name:
            return rule
    for rule in rules:
        if rule.kind == 'prefix' and value.startswith(rule.name) and len(rule.name) < len(value):
            return rule
    return None


def read(path):
    """The text of one file of this repository."""
    return (ROOT / path).read_text(encoding='utf-8')


def page_route_list():
    """Every route both pages call, in file order."""
    routes = []
    for name in PAGES:
        routes.extend(page_routes(name))
    return tuple(routes)


def unserved(pages, rules):
    """Every route of ``pages`` that no rule of ``rules`` serves, as file:line route."""
    return tuple(
        f'{path}:{route.line} {route.name}'
        for path, route, _ in pages
        if dispatch_route(rules, route) is None
    )


def served_without_page(pages, rules):
    """Every dispatch route that no page route calls, as file:line route."""
    called = {route.name for _, route, _ in pages}
    out = []
    for rule in rules:
        if rule.kind == 'prefix':
            if any(value.startswith(rule.name) for value in called):
                continue
        elif rule.name in called:
            continue
        out.append(f'{SERVER}:{rule.line} {rule.name}')
    return tuple(out)


def _link(rule):
    """The server line of one rule, as file:line."""
    return f'{SERVER}:{rule.line}'


class LegacyRouteCases(unittest.TestCase):
    """The two-way guard on the route literals of the legacy review tool."""

    def test_dispatch_parser_reads_the_two_verbs(self):
        """The parser reads the route literal and its line from each verb."""
        rules = dispatch_rules(SERVER, read(SERVER))
        seen = {(rule.name, rule.line) for rule in rules}
        self.assertIn(('/api/events', 67), seen)
        self.assertIn(('/api/ball_label', 130), seen)
        self.assertIn(('/api/annotate', 144), seen)
        kinds = {rule.name: rule.kind for rule in rules}
        self.assertEqual('guard', kinds['/api/annotate'])
        self.assertTrue(seen, 'the parser read no dispatch rule of ' + SERVER)
        for rule in rules:
            self.assertIn(rule.kind, ('exact', 'guard', 'prefix'))
            self.assertTrue(rule.name.startswith('/'))
        self.assertEqual(len(seen), len(rules), 'the parser read one dispatch step twice')

    def test_dispatch_parser_keeps_the_two_prefix_rules(self):
        """The two prefix rules of the dispatch stay prefix rules."""
        rules = dispatch_rules(SERVER, read(SERVER))
        prefixes = {rule.name for rule in rules if rule.kind == 'prefix'}
        self.assertEqual({'/ctx/', '/crops/'}, prefixes)

    def test_page_scan_reads_both_pages(self):
        """The scan reads a route literal of each page."""
        routes = page_route_list()
        names = {route.name for _, route, _ in routes}
        self.assertIn('/api/events', names)
        self.assertIn('/api/annotate', names)
        self.assertIn('/api/crops', names)
        self.assertIn('/api/ball_label', names)
        self.assertIn('/ctx/${value}', names)
        self.assertIn('/crops/${value}', names)
        for _, route, _ in routes:
            self.assertTrue(route.line > 0)
            self.assertTrue(route.name.startswith('/'))

    def test_every_page_route_has_a_server_line(self):
        """Every route a page calls is served by the dispatch, and the line is real."""
        pages = page_route_list()
        rules = dispatch_rules(SERVER, read(SERVER))
        server_text = read(SERVER).splitlines()
        for path, route, _ in pages:
            rule = dispatch_route(rules, route)
            self.assertIsNotNone(
                rule,
                f'{path}:{route.line} {route.name} has no dispatch rule in {SERVER}',
            )
            self.assertIn(
                'self.path', server_text[rule.line - 1],
                f'{_link(rule)} does not read self.path for {route.name}',
            )

    def test_no_page_route_stands_unserved(self):
        """The guard of this round: no page route is unserved."""
        pages = page_route_list()
        rules = dispatch_rules(SERVER, read(SERVER))
        self.assertEqual(
            (),
            unserved(pages, rules),
            'route literal of a page with no dispatch rule in ' + SERVER,
        )

    def test_planted_dead_route_names_its_file_and_line(self):
        """A planted dead route gives the file and the line, not only the route."""
        self.assertEqual(64, len(PAGE_SAMPLE.splitlines()), 'the sample page moved its plant line')
        page = PAGE_SAMPLE.replace('/api/actors', '/api/actors_2')
        self.assertNotEqual(PAGE_SAMPLE, page, 'the plant did not land in the sample page')
        records = tuple(
            ('annotator/index.html', route, page)
            for route in page_route_records('annotator/index.html', page)
        )
        rules = dispatch_rules(SERVER, read(SERVER))
        red = unserved(records, rules)
        self.assertEqual(('annotator/index.html:64 /api/actors_2',), red)
        self.assertIn(':64 ', red[0])
        self.assertTrue(red[0].endswith(' /api/actors_2'))

    def test_planted_dead_route_in_a_copy_of_the_page(self):
        """The same report stands for a copy of the page in another directory."""
        page = PAGE_SAMPLE.replace('/api/actors', '/api/actors_2')
        with tempfile.TemporaryDirectory() as work:
            target = Path(work) / 'annotator'
            target.mkdir(parents=True)
            (target / 'index.html').write_text(page, encoding='utf-8')
            fake = Path(work).as_posix() + '/annotator/index.html'
            records = tuple(
                (fake, route, page)
                for route in page_route_records(fake, page)
            )
            rules = dispatch_rules(SERVER, read(SERVER))
            red = unserved(records, rules)
        self.assertEqual(1, len(red), 'the page scan missed the planted route')
        self.assertEqual(f'{fake}:64 /api/actors_2', red[0])
        self.assertIn('/annotator/index.html:64 ', red[0])
        self.assertTrue(red[0].endswith(' /api/actors_2'))

    def test_reports_a_route_the_dispatch_serves_alone(self):
        """The second report is a report, not a failure."""
        records = tuple(
            ('annotator/index.html', route, PAGE_SAMPLE)
            for route in page_route_records('annotator/index.html', PAGE_SAMPLE)
        )
        rules = dispatch_rules(SERVER, read(SERVER))
        alone = served_without_page(records, rules)
        self.assertIn(f'{SERVER}:88 /label', alone)
        self.assertIn(f'{SERVER}:115 /label.html', alone)
        self.assertNotIn('/api/actors', ' '.join(alone))

    def test_reports_the_routes_no_page_calls(self):
        """Report the routes the dispatch serves with no page call.  Do not fail."""
        pages = page_route_list()
        rules = dispatch_rules(SERVER, read(SERVER))
        alone = served_without_page(pages, rules)
        print('routes the dispatch serves with no page call:')
        for item in alone:
            print('  ' + item)
        print(f'{len(pages)} page routes, {len(rules)} dispatch rules')
        self.assertIsInstance(alone, tuple)


if __name__ == '__main__':
    unittest.main()
