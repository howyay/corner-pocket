"""The five clock numbers of the operator document must answer their owners.

The document ``docs/corner-pocket-operations.md`` is the page an operator reads.  It
states five clock numbers, and every one of them lives in code:

======================  ===========================  ===================================
document line           document words                owner
======================  ===========================  ===================================
``:21``                 ``20/30/45/60``               ``annotator/ops.js:902``
``:46``                 ``a heartbeat every 15 s``    ``annotator/shot_clock.py:41``
``:47``                 ``30 s pass``                 ``annotator/clock-sync.js:53``
``:47``                 ``**every 1 s**``             ``annotator/clock-sync.js:49``
``:48``                 ``After 10 s``                ``annotator/clock-sync.js:62``
======================  ===========================  ===================================

The three client numbers stand in milliseconds and the document states them in
seconds, so this module holds the unit of a site as well as its owner.

Round 98 measured that no case read the document for those five numbers.  An edit to
``SHOT_PRESETS``, ``HEARTBEAT_S``, ``HEARTBEAT_TIMEOUT_MS``, ``POLL_MS`` or
``OFFLINE_AFTER_MS`` left the operator document stale, and nothing failed.
``tests/test_pipeline_note_owner.py`` already reads the document, but its case holds
the expiry sentence only.

Every case here reads the number out of the document text and compares it with the
owner text of that number.  A mismatch names the document line and both numbers.  A
number that stands twice in the document is refused: a second spelling is the drift
these cases exist to stop.

The document cites no ``file:line`` pair for a clock number, so no case demands one.
Two cases hold the other direction of the same fact: the line of an owner must still
hold the binding that the table above names, and the words of the document must still
stand on the line that the table above names.

Limits: the reader reads text and no meaning.  It anchors on the words it names below,
so a reworded document line fails the case loudly and a person must teach the reader
the new words.  It cannot see a number a build step writes into the document, and it
cannot see a view of a number, such as the product of a number.

The second class holds the note of round 98: the prose above ``HEARTBEAT_S`` stated
the client timeout as a copy of the number, and it now names the owner constant.  The
file keeps its line count, because ``docs/console-redesign.md:8098`` cites
``annotator/shot_clock.py:40``.

Run: ``./scripts/pool-test.sh python test_clock_document_owner``
"""
from __future__ import annotations

import re
import sys
import unittest
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from annotator import shot_clock  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = 'docs/corner-pocket-operations.md'
OPS = 'annotator/ops.js'
CLOCK_SYNC = 'annotator/clock-sync.js'
SHOT_CLOCK = 'annotator/shot_clock.py'

#: One (path, line, binding) of an owner, and the name of the value that stands there.
PRESETS_OWNER = (OPS, 902, 'SHOT_PRESETS')
HEARTBEAT_OWNER = (SHOT_CLOCK, 41, 'HEARTBEAT_S')
TIMEOUT_OWNER = (CLOCK_SYNC, 53, 'HEARTBEAT_TIMEOUT_MS')
POLL_OWNER = (CLOCK_SYNC, 49, 'POLL_MS')
OFFLINE_OWNER = (CLOCK_SYNC, 62, 'OFFLINE_AFTER_MS')

#: One unit of an owner: a divisor that gives seconds, and the words of that unit.
Unit = namedtuple('Unit', 'divisor words')
SECONDS = Unit(1, 's')
MILLISECONDS = Unit(1000, 'ms')

#: The words line 47 uses for the timeout.  The words are the rule and the number
#: beside them is the copy this module refuses.  A client cannot read its own file,
#: so no case here asks it to.
MISSED_HEARTBEATS = ('two missed', 'heartbeats')

#: The name of the client constant that owns the client timeout.
TIMEOUT_NAME = 'HEARTBEAT_TIMEOUT_MS'

#: The two comment lines of annotator/shot_clock.py that hold the note of round 98.
NOTE_LINES = (38, 40)

#: A sentence a person may write above HEARTBEAT_S without restating a number.
REPAIRED = ('# The client stops trusting the stream after the timeout named\n'
            '# HEARTBEAT_TIMEOUT_MS in annotator/clock-sync.js, and it then polls.\n')

#: The one (path, line) outside this module that cites a line of the note prose.
CENSUS_CITATION = ('docs/console-redesign.md', 8098, SHOT_CLOCK, 40)

#: One site of the document: the name of the value, the words that name it in the
#: document, the words the number stands between, the unit of that number, and the
#: owner of the number.
Site = namedtuple('Site', 'kind words markers unit owner')

SITES = (
    Site('presets', 'presets', ('whoever presses Start, Pause, Reset or ',
                                ' sets the clock'), SECONDS, PRESETS_OWNER),
    Site('heartbeat', 'heartbeat cadence', ('plus a heartbeat every ', ' s.'),
         SECONDS, HEARTBEAT_OWNER),
    Site('timeout', 'reconnect timeout', ('or ', ' s pass with no heartbeat'),
         MILLISECONDS, TIMEOUT_OWNER),
    Site('poll', 'poll interval', ('**every ', ' s**'), MILLISECONDS, POLL_OWNER),
    Site('offline', 'offline bar', ('After ', ' s with no answer'),
         MILLISECONDS, OFFLINE_OWNER),
)
SITE_BY_NAME = {site.kind: site for site in SITES}
SITE_BY_OWNER = {site.owner: site for site in SITES}

QUOTED = re.compile(r'`([^`]*)`')
#: A slash list of whole numbers, the shape the document uses for the presets.
LIST = re.compile(r'\b\d+(?:\s*/\s*\d+)+\b')


def read(name):
    """The text of one file of the repository."""
    return (ROOT / name).read_text(encoding='utf-8')


def numbers(text):
    """The whole numbers one text spells, in order."""
    return [int(part) for part in re.findall(r'\d+', text)]


def quoted_numbers(text):
    """The whole numbers of the backtick spans of one text, in order.

    The document states the presets as ``20/30/45/60`` inside one span, and a route as
    ``GET /api/clock`` inside another.  Only the first kind holds a number.
    """
    found = []
    for span in QUOTED.findall(text):
        found.extend(numbers(span))
    return found


def between(line, before, after):
    """The numbers between two markers of one line, or None when a marker is absent."""
    if before not in line or after not in line:
        return None
    inside = line.split(before, 1)[1].split(after, 1)[0]
    return numbers(inside)


def document_text():
    """The text of the operator document, the one document this module reads."""
    return read(DOCUMENT)


def document_lines(text):
    """The document as a list of lines."""
    return text.splitlines()


def line_number(text, fragment):
    """The 1-based number of the one line that holds a fragment.

    The reader finds its own site, so no case stores a line number that a document
    edit above the site would move.
    """
    found = [number for number, line in enumerate(text.splitlines(), start=1)
             if fragment in line]
    if len(found) != 1:
        raise AssertionError('%s holds %d line(s) with %r, and the reader needs one'
                             % (DOCUMENT, len(found), fragment))
    return found[0]


def site_lines(text, name):
    """The 1-based numbers of the lines that hold the anchor words of one site."""
    after = SITE_BY_NAME[name].markers[1]
    return [number for number, line in enumerate(text.splitlines(), start=1)
            if after in line]


def site_line(text, name):
    """The line of one site of the document, found by the words of that site."""
    return line_number(text, SITE_BY_NAME[name].markers[1])


def owner_value(owner):
    """The value one owner holds at the line the table above names."""
    name, line, binding = owner
    body = read(name).splitlines()[line - 1]
    if binding not in body:
        raise AssertionError('%s:%d holds no %s' % (name, line, binding))
    if name == SHOT_CLOCK:
        return getattr(shot_clock, binding)
    found = re.findall(r'\b%s\s*=\s*(\d+)\b' % binding, body)
    if not found:
        found = re.findall(r'\b%s\s*=\s*\[\s*([\d\s,]+)\]' % binding, body)
        if not found:
            raise AssertionError('%s:%d gives no number to %s' % (name, line, binding))
        return [int(part) for part in re.findall(r'\d+', found[0])]
    if len(set(found)) != 1:
        raise AssertionError('%s:%d gives %s more than one number: %s'
                             % (name, line, binding, found))
    return int(found[0])


def owner_seconds(site):
    """The value of one owner in the unit the document states."""
    value = owner_value(site.owner)
    divisor = site.unit.divisor
    if divisor == 1:
        return value
    if isinstance(value, list):
        return [part // divisor for part in value]
    return value // divisor


def scaled(value, divisor):
    """One value as the seconds the document states, for a report line."""
    if divisor == 1:
        return '%d' % value
    if isinstance(value, list):
        return '%s ms (%s s)' % (value, [part // divisor for part in value])
    return '%d ms (%d s)' % (value, value // divisor)


def found_number(value):
    """A number or a list of numbers as one text."""
    if isinstance(value, list):
        return '/'.join(str(part) for part in value)
    return str(value)


def reading_findings(text, name):
    """Every way one document site fails to answer the owner of that site.

    Each finding names the document line and both numbers.
    """
    site = SITE_BY_NAME[name]
    path, owner_line, binding = site.owner
    stated = site_lines(text, name)
    if len(stated) != 1:
        return ['%s states the %s on %d lines (%s), and one number has one site in this '
                'document: %s:%d' % (DOCUMENT, site.words, len(stated), stated,
                                     path, owner_line)]
    line = stated[0]
    divisor = site.unit.divisor
    fact = owner_seconds(site)
    body = document_lines(text)[line - 1]
    if site.kind == 'presets':
        stated = [span.strip() for span in QUOTED.findall(body) if LIST.search(span)]
        plain = ['/'.join(str(part) for part in numbers(part))
                 for part in LIST.findall(body)]
        if len(stated) + len(plain) != 1:
            return ['%s:%d states %d slash lists of presets (%s), and %s:%d gives %s'
                    % (DOCUMENT, line, len(stated) + len(plain), stated + plain,
                       path, owner_line, found_number(fact))]
        seen = numbers(stated[0]) if stated else numbers(plain[0])
        if seen != fact:
            return ['%s:%d states the presets as %s, and %s in %s:%d gives %s'
                    % (DOCUMENT, line, found_number(seen), binding, path, owner_line,
                       found_number(fact))]
        return []
    before, after = site.markers
    found = between(body, before, after)
    if found is None:
        return ['%s:%d states no %s between %r and %r, so this case cannot hold it to '
                '%s:%d' % (DOCUMENT, line, site.words, before, after, path, owner_line)]
    if len(found) != 1:
        return ['%s:%d states the %s as %d numbers (%s), and %s:%d gives one number'
                % (DOCUMENT, line, site.words, len(found), found, path, owner_line)]
    if found[0] != fact:
        return ['%s:%d states the %s as %d s, and %s:%d gives %s'
                % (DOCUMENT, line, site.words, found[0], path, owner_line,
                   scaled(owner_value(site.owner), divisor))]
    return []


def split_reading_findings(text):
    """Every way the document fails to state the timeout as two heartbeats."""
    line = line_number(text, MISSED_HEARTBEATS[0])
    body = document_lines(text)[line - 1]
    missing = [word for word in MISSED_HEARTBEATS if word not in body]
    if missing:
        return ['%s:%d states the timeout without %s, and the rule is two heartbeats of '
                '%s.HEARTBEAT_S' % (DOCUMENT, line, missing, SHOT_CLOCK)]
    return []


def document_findings(text):
    """Every way the document disagrees with an owner, for every site.

    ``read`` may be replaced for one call, so a case can move an owner in memory only.
    """
    findings = []
    for name in sorted(SITE_BY_NAME):
        findings.extend(reading_findings(text, name))
    findings.extend(split_reading_findings(text))
    return findings


def moved_owner_findings(text, path, planted):
    """The findings of a document against one owner text that stands in memory only."""
    real_read = globals()['read']

    def reads(name, _path=path, _planted=planted, _real=real_read):
        """The planted owner text, or the file on disk."""
        return _planted if name == _path else _real(name)

    globals()['read'] = reads
    try:
        return document_findings(text)
    finally:
        globals()['read'] = real_read


def substitute_line(text, line, before, after, old, new):
    """One document line with one number replaced by another."""
    lines = document_lines(text)
    if line > len(lines):
        raise AssertionError('%s holds %d lines' % (DOCUMENT, len(lines)))
    body = lines[line - 1]
    if before not in body or after not in body:
        raise AssertionError('%s:%d holds no %r and %r' % (DOCUMENT, line, before, after))
    if str(old) not in body:
        raise AssertionError('%s:%d holds no %s' % (DOCUMENT, line, old))
    lines[line - 1] = body.replace(str(old), str(new), 1)
    if lines[line - 1] == body:
        raise AssertionError('%s:%d did not change' % (DOCUMENT, line))
    return '\n'.join(lines) + '\n'


def spells_number(source, lines):
    """True when one of the named lines of a source spells a number."""
    body = source.splitlines()
    if max(lines) > len(body):
        return False
    return any(numbers(body[number - 1]) for number in lines)


class ClockDocumentOwnerTests(unittest.TestCase):
    """Every clock number of the document answers the module that owns it."""

    def test_the_document_agrees_with_every_clock_owner(self):
        self.assertEqual([], document_findings(document_text()),
                         'every clock number of the document must answer its owner')

    def test_every_owner_line_holds_the_clock_value_it_owns(self):
        for name, site in sorted(SITE_BY_NAME.items()):
            path, line, binding = site.owner
            body = read(path).splitlines()[line - 1]
            self.assertIn(binding, body,
                          '%s:%d must hold %s, the owner of the %s'
                          % (path, line, binding, site.words))

    def test_every_site_of_the_reader_is_one_the_document_states(self):
        text = document_text()
        for name, site in sorted(SITE_BY_NAME.items()):
            self.assertEqual([], reading_findings(text, name),
                             'the %s site of the reader must read a value of the document'
                             % name)
            self.assertIn(site.markers[1], text,
                          'the document must hold the words the %s reader anchors on'
                          % name)
            site_line(text, name)

    def test_the_reader_names_the_document_line_and_both_numbers(self):
        text = document_text()
        site = SITE_BY_NAME['heartbeat']
        line = site_line(text, 'heartbeat')
        fact = owner_value(site.owner)
        planted = substitute_line(text, line, *site.markers, old=fact, new=99)
        self.assertEqual([], document_findings(text), 'the document must agree first')
        findings = document_findings(planted)
        self.assertEqual(1, len(findings),
                         'a planted number must give exactly one finding: %s' % findings)
        finding = findings[0]
        self.assertIn('%s:%d' % (DOCUMENT, line), finding,
                      'the finding must name the document line: %s' % finding)
        self.assertIn('99', finding, 'the finding must name the planted number: %s' % finding)
        self.assertIn(str(fact), finding,
                      'the finding must name the owner number: %s' % finding)

    def test_a_planted_preset_is_named(self):
        text = document_text()
        site = SITE_BY_NAME['presets']
        line = site_line(text, 'presets')
        path, owner_line, binding = site.owner
        planted = substitute_line(text, line, *site.markers, old=60, new=61)
        self.assertEqual([], document_findings(text), 'the document must agree first')
        findings = document_findings(planted)
        self.assertEqual(1, len(findings),
                         'a planted preset must give exactly one finding: %s' % findings)
        finding = findings[0]
        self.assertIn('%s:%d' % (DOCUMENT, line), finding,
                      'the finding must name the document line: %s' % finding)
        self.assertIn('61', finding, 'the finding must name the planted number: %s' % finding)
        self.assertIn(binding, finding,
                      'the finding must name the owner value: %s' % finding)
        self.assertIn('%s:%d' % (path, owner_line), finding,
                      'the finding must name the owner line: %s' % finding)

    def test_a_second_site_of_one_number_is_refused(self):
        text = document_text()
        line = site_line(text, 'offline')
        extra = '- After 7 s with no answer the label stays the same.\n'
        self.assertEqual([], document_findings(text), 'the document must agree first')
        findings = document_findings(text + extra)
        self.assertEqual(1, len(findings),
                         'a second spelling must give exactly one finding: %s' % findings)
        self.assertIn('2 lines', findings[0],
                      'the finding must name the count of the second site: %s' % findings[0])
        self.assertIn(str(line), findings[0],
                      'the finding must name the first line of the site: %s' % findings[0])

    def test_an_owner_that_moves_alone_is_reported(self):
        text = document_text()
        path, line, binding = TIMEOUT_OWNER
        source = read(path)
        planted = source.replace('const %s = ' % binding, 'const %s = 40000; // ' % binding, 1)
        self.assertNotEqual(source, planted,
                            'the plant must move %s:%d' % (path, line))
        findings = moved_owner_findings(text, path, planted)
        self.assertTrue(findings, 'a moved owner with a stale document must fail the case')
        self.assertTrue(any('%s:%d' % (path, line) in finding for finding in findings),
                        'a finding must name the owner site: %s' % findings)
        self.assertTrue(any('%d ms' % 40000 in finding for finding in findings),
                        'a finding must name the moved owner number in its unit: %s'
                        % findings)
        site = SITE_BY_OWNER[TIMEOUT_OWNER]
        other = [finding for finding in findings
                 if '%s:%d' % (path, line) not in finding]
        self.assertEqual(document_findings(text), other,
                         'the five other numbers of the document are held by their own '
                         'owners, so one moved owner must report one site: %s' % findings) 

    def test_the_readers_cannot_agree_by_accident(self):
        owned = {owner: owner_value(owner) for owner in SITE_BY_OWNER}
        self.assertEqual(5, len(owned), 'the document states five clock numbers')
        self.assertEqual(5, len(set(map(found_number, owned.values()))),
                         'the five numbers of this document differ today, so a reader that '
                         'answers the wrong owner cannot pass: %s' % owned)

    def test_the_census_of_the_note_prose_names_the_line_that_changed(self):
        path, line, cited_path, cited_line = CENSUS_CITATION
        body = read(path).splitlines()[line - 1]
        self.assertIn('%s:%d' % (cited_path, cited_line), body,
                      '%s:%d must cite the note prose of round 98' % (path, line))
        self.assertIn('prose line', body,
                      '%s:%d must state that its census counts a prose line' % (path, line))


class ClockNoteCommentTests(unittest.TestCase):
    """The prose above HEARTBEAT_S names the owner and restates no number."""

    def test_the_note_prose_names_the_timeout_owner(self):
        source = read(SHOT_CLOCK)
        for number in NOTE_LINES:
            body = source.splitlines()[number - 1]
            self.assertTrue(body.lstrip().startswith('#'),
                            '%s:%d must stay a comment line' % (SHOT_CLOCK, number))
        note = '\n'.join(source.splitlines()[NOTE_LINES[0] - 1:NOTE_LINES[1]])
        self.assertIn(TIMEOUT_NAME, note,
                      'the note must name %s, the owner of the timeout' % TIMEOUT_NAME)
        self.assertIn(CLOCK_SYNC, note,
                      'the note must name the file of that owner')

    def test_the_note_prose_restates_no_number(self):
        source = read(SHOT_CLOCK)
        self.assertFalse(spells_number(source, NOTE_LINES),
                         '%s:%s must name the owner and state no number'
                         % (SHOT_CLOCK, list(NOTE_LINES)))

    def test_the_file_keeps_the_lines_other_files_cite(self):
        source = read(SHOT_CLOCK)
        lines = source.splitlines()
        self.assertEqual(259, len(lines),
                         '%s must keep the line count that other files cite' % SHOT_CLOCK)
        for number, binding in ((HEARTBEAT_OWNER[1], 'HEARTBEAT_S'),
                                (NOTE_LINES[0], None), (NOTE_LINES[1], None)):
            if binding:
                self.assertIn(binding, lines[number - 1],
                              '%s:%d must stay the line of %s, because the document cites it'
                              % (SHOT_CLOCK, number, binding))
            else:
                self.assertTrue(lines[number - 1].lstrip().startswith('#'),
                                '%s:%d must stay a comment line' % (SHOT_CLOCK, number))

    def test_a_planted_number_in_the_note_is_refused(self):
        source = read(SHOT_CLOCK)
        self.assertFalse(spells_number(source, NOTE_LINES),
                         'the note must state no number before this plant')
        lines = source.splitlines()
        lines[NOTE_LINES[1] - 1] = '# nothing for 30 s falls back to polling.'
        planted = '\n'.join(lines) + '\n'
        self.assertNotEqual(source, planted, 'the plant must change the note')
        self.assertTrue(spells_number(planted, NOTE_LINES),
                        'the rule must see a planted number in the note')

    def test_a_comment_that_names_the_owner_is_accepted(self):
        self.assertIn(TIMEOUT_NAME, REPAIRED,
                      'the repaired comment must name the owner of the timeout')
        self.assertIn(CLOCK_SYNC, REPAIRED,
                      'the repaired comment must name the file of that owner')
        self.assertFalse(spells_number(REPAIRED, NOTE_LINES),
                         'a note that names an owner must not restate a number')


if __name__ == '__main__':
    unittest.main()
