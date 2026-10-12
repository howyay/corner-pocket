"""One home for the Twitch request header table, and a report for every copy.

``annotator/twitch_source.py`` holds ``USER_AGENT``, ``ACCEPT`` and ``request_headers``.
The Twitch request user agent and the header names used to stand twice: once in the live
resolver (``annotator/twitch_source.py``) and once in the VOD path
(``annotator/twitch_vod_source.py``), so one edit sent two client identities to Twitch and
no case reported it.  ``tests/test_twitch_vod_source.py`` and ``tests/test_vod_import.py``
read behavior, not source, so neither one saw the second copy.

This guard reads the ``*.py`` source of the project, finds each string constant equal to
the pinned user agent, or to a header name of the Twitch table, and names the file and the
line.  The virtual environment, the generated ``out/`` tree and this module are not read.
The home is the one allowed holder, and three cases below check the walk itself: one feeds
it a file that spells the pinned value, one feeds it a file that holds the home path, and
one feeds it a file that spells the header pair.

A comment or a docstring that says ``User-Agent`` is not a copy: only a value the
interpreter can read reports.  The measured check reads the headers of one scripted HTTP
request that the VOD path builds, so this guard proves the shared table is live, not only
declared.
"""
import ast
import unittest
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

from annotator import twitch_source as live
from annotator import twitch_vod_source as vod

ROOT = Path(__file__).resolve().parents[1]

#: This module names the strings it hunts for, so it cannot report a copy inside itself.
SELF = Path(__file__).name
#: First path parts that hold no project source.
SKIPPED_TOP_LEVEL = ('.git', '.venv', 'node_modules', 'out', '__pycache__',
                     'data', 'logs', 'fixtures')

#: The one module that may hold the user agent and the header names, relative to the root.
HOME = 'annotator/twitch_source.py'
#: The user agent the home must keep.  This is a deliberate pin, not a copy of the value at
#: import time.  A guard that reads the home and compares the home with itself stays green
#: when someone edits the value, and that edit is the one event this row exists to report.
#: The pin also names the dead copy in the report, and the home stays the one holder.
CANONICAL_USER_AGENT = 'Mozilla/5.0'


def _module_name(path):
    """``annotator/twitch_source.py`` for a path under the root; else None."""
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return None
    return relative.as_posix()


def _project_files():
    """Every project ``*.py`` file, in a stable order, with no generated tree."""
    for path in sorted(ROOT.rglob('*.py')):
        relative = path.relative_to(ROOT)
        if relative.parts[0] in SKIPPED_TOP_LEVEL:
            continue
        if path.name == SELF:
            continue
        yield _module_name(path), path


@lru_cache(maxsize=1)
def _canonical_user_agent():
    """The pinned user agent.  The home and every caller must spell this value.

    The guard compares the home and the tree against the pin, so an edit to the home value
    reports.  A value read out of the home would make that comparison true by definition.
    """
    return CANONICAL_USER_AGENT


@lru_cache(maxsize=1)
def _header_names():
    """The header names a live request carries today, straight from the home."""
    return tuple(sorted(live.request_headers('*/*')))


def _string_literals(text):
    """Every string constant of one source text: ``(line, value)``, in tree order."""
    out = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((node.lineno, node.value))
    return out


@lru_cache(maxsize=1)
def _spellings():
    """Every string constant of every project file this guard reads.

    The cache is the point: one parse pass answers every case below, and a case that reads
    it twice reports the same list.
    """
    out = {}
    for label, path in _project_files():
        out[label] = tuple(_string_literals(path.read_text(encoding='utf-8')))
    return out


def _find_in(files, value=None):
    """The report lines one ``{module: source}`` map produces, in file order.

    Two rules report.  A module that spells the user agent reports, and the report carries
    the line of the constant and the name of the home.  A module that spells the two header
    names of the Twitch request - ``User-Agent`` and ``Client-ID`` - builds the same table
    by hand, and reports.
    """
    user_agent = _canonical_user_agent() if value is None else value
    rows = []
    for module in sorted(files):
        if module == HOME:
            continue
        literals = _string_literals(files[module])
        spelled = {found for _, found in literals}
        for line, found in literals:
            if found == user_agent:
                rows.append('%s:%d: spells the user agent %r; read USER_AGENT of %s'
                            % (module, line, found, HOME))
            elif found == 'User-Agent' and 'Client-ID' in spelled:
                rows.append('%s:%d: spells the header name %r; read request_headers of %s'
                            % (module, line, found, HOME))
    return rows


def _findings():
    """Every copy of a home name in the live tree, as ``"<file>:<line>: ..."``."""
    return _find_in({module: path.read_text(encoding='utf-8')
                     for module, path in _project_files()})


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


def _recording_opener(target, calls, body=b'body'):
    """Patch ``build_opener`` of ``target`` with an opener that records each request."""
    def _open(request, timeout=None):
        calls.append(request)
        return _Reply(body)
    opener = type('_Opener', (), {'open': staticmethod(_open)})
    return patch(target, lambda *handlers: opener())


class UserAgentOwner(unittest.TestCase):
    """The user agent stands once, in the home module, and no other module spells it."""

    def test_the_home_publishes_one_user_agent_string(self):
        """The guard reads a non-empty value, so an empty home cannot pass by accident."""
        self.assertIsInstance(live.USER_AGENT, str)
        self.assertTrue(live.USER_AGENT.strip())

    def test_the_home_keeps_the_pinned_user_agent(self):
        """The bite case: an edit to the home value reports here, with both values."""
        self.assertEqual(CANONICAL_USER_AGENT, live.USER_AGENT,
                         'the home names %r; the table pins %r'
                         % (live.USER_AGENT, CANONICAL_USER_AGENT))

    def test_user_agent_stands_once_in_the_project(self):
        """A second copy of the user agent is the drift this guard exists to report."""
        self.assertEqual([], [line for line in _findings() if 'user agent' in line])

    def test_the_walk_sees_a_copy_of_the_user_agent(self):
        """Wrong-value check: the walk reports a file that spells the pinned value."""
        files = {'annotator/example_other.py': "UA = '%s'" % CANONICAL_USER_AGENT}
        self.assertEqual(['annotator/example_other.py:1: spells the user agent %r; '
                          'read USER_AGENT of %s' % (CANONICAL_USER_AGENT, HOME)],
                         _find_in(files))

    def test_the_walk_ignores_the_home_itself(self):
        """The home holds the one allowed copy, and the walk passes over that file."""
        files = {HOME: "UA = '%s'" % CANONICAL_USER_AGENT}
        self.assertEqual([], _find_in(files))


class HeaderNameOwner(unittest.TestCase):
    """The header names stand once, in the home module, and no other module spells them."""

    def test_the_home_publishes_the_two_names_of_the_shared_table(self):
        """The shared table carries exactly these two names, with no extra name."""
        self.assertEqual(('Accept', 'User-Agent'), _header_names())

    def test_no_other_module_builds_the_header_table(self):
        """A module with the user agent header name and the client id header name reports."""
        self.assertEqual([], [line for line in _findings() if 'header name' in line])

    def test_the_walk_sees_the_header_pair_of_another_module(self):
        """Wrong-value check: the pair rule fires on a file that holds both names."""
        files = {'annotator/example_other.py':
                 "headers = {'User-Agent': 'x', 'Client-ID': 'y'}"}
        self.assertEqual(['annotator/example_other.py:1: spells the header name '
                          "'User-Agent'; read request_headers of %s" % HOME], _find_in(files))

    def test_the_walk_ignores_a_lone_header_name(self):
        """A module with one of the two names and no user agent value reports nothing."""
        files = {'tests/test_vod_import.py':
                 "headers = {'Content-Type': 'application/json'}"}
        self.assertEqual([], _find_in(files))

    def test_accept_is_the_one_name_a_caller_states(self):
        """The home keeps the Accept name open: each caller passes its own value."""
        self.assertIn('Accept', live.request_headers('*/*'))
        self.assertIn('Accept', live.request_headers('image/*'))


class HeadersAreShared(unittest.TestCase):
    """The two live paths send the home's table, so one edit changes both requests."""

    def test_the_home_answers_a_new_dict_on_every_call(self):
        """A shared dict would let one caller's update reach the other caller."""
        first, second = live.request_headers('*/*'), live.request_headers('*/*')
        self.assertIsNot(first, second)
        first['X-Sentinel'] = 'yes'
        self.assertNotIn('X-Sentinel', second)

    def test_the_vod_document_path_reads_the_home_table(self):
        """Measured check: the one scripted request carries the home's user agent."""
        calls = []
        with _recording_opener('annotator.twitch_vod_source.build_opener', calls):
            vod._raw('https://gql.twitch.tv/gql', {'query': '{ me { id } }'})
        self.assertEqual(1, len(calls))
        headers = calls[0].headers
        self.assertEqual(live.USER_AGENT, headers.get('User-agent'))
        self.assertEqual('*/*', headers.get('Accept'))
        self.assertEqual('application/json', headers.get('Content-type'))

    def test_the_vod_image_path_states_its_own_accept(self):
        """The picture path states ``image/*`` and keeps the home's user agent."""
        calls = []
        with _recording_opener('annotator.twitch_vod_source.build_opener', calls):
            vod._raw_bytes('https://static-cdn.jtvnw.net/thumb0-320x180.jpg')
        self.assertEqual(1, len(calls))
        headers = calls[0].headers
        self.assertEqual(live.USER_AGENT, headers.get('User-agent'))
        self.assertEqual('image/*', headers.get('Accept'))

    def test_the_live_resolver_reads_the_same_home(self):
        """The live path sends the same table, and the tested host is the gql endpoint."""
        calls = []
        with _recording_opener('annotator.twitch_source.build_opener', calls,
                               body=b'{"data": null}'):
            self.assertEqual('{"data": null}',
                             live._request('https://gql.twitch.tv/gql',
                                           {'query': '{ me { id } }'}))
        self.assertEqual(1, len(calls))
        self.assertEqual('gql.twitch.tv', calls[0].host)
        self.assertEqual(live.USER_AGENT, calls[0].headers.get('User-agent'))
        self.assertEqual('*/*', calls[0].headers.get('Accept'))


class TheWalk(unittest.TestCase):
    """The guard's own tools, checked, so a walk that reads nothing cannot pass."""

    def test_the_walk_reads_the_two_live_modules(self):
        """The two modules of this row are inside the walk, not skipped by a filter."""
        labels = set(_spellings())
        self.assertIn('annotator/twitch_source.py', labels)
        self.assertIn('annotator/twitch_vod_source.py', labels)
        self.assertGreater(len(labels), 50)

    def test_today_the_walk_finds_no_copy(self):
        """Live count: one home and no second copy. The message shows any finding."""
        self.assertEqual([], list(_findings()))

    def test_the_home_is_the_one_exempt_module(self):
        """The exemption covers the home file and no other file."""
        self.assertEqual(1, sum(1 for module in _spellings() if module == HOME))

    def test_a_report_line_names_a_file_and_a_line(self):
        """A report a reader cannot locate is not a report."""
        report = _find_in({'annotator/example_other.py':
                           "A = 1\nB = 2\nUA = '%s'" % CANONICAL_USER_AGENT})
        self.assertEqual(['annotator/example_other.py:3: spells the user agent %r; '
                          'read USER_AGENT of %s' % (CANONICAL_USER_AGENT, HOME)], report)


if __name__ == '__main__':
    unittest.main()
