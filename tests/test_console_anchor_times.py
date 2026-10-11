"""Round 71, Worth 1: the three anchor times the console offers, held to one home.

Ground of the row.  The three suggested anchor times stood as two bare literals and one
published field:

* ``annotator/unified_server.py`` published ``"suggested_times": [70, 200, 350]`` in the
  answer of ``anchor_info``;
* ``annotator/vision-stage.js`` drew the jump row from its own ``[70,200,350]``, so the
  published field had no reader at all;
* ``src/pid_anchor_ui.py`` held the same three seconds twice more: ``SUGGESTED``, which no
  line of that file read, and the ``SUG`` array of the legacy page's own script.

A reader of the field could see times the console never drew, and a change of one literal
left the other two behind.  Round 71 gives the list one home in the service realm,
``SUGGESTED_ANCHOR_TIMES``, publishes it from ``anchor_info``, and makes the console row
draw one button per published value.

What this module reads
----------------------
* The service tuple ``SUGGESTED_ANCHOR_TIMES`` of ``annotator/unified_server.py``, by one
  regex, and the answer line of ``anchor_info`` that publishes it.
* ``annotator/app.js``: ``loadAnchors`` copies the published field into the state, and
  ``snapshot()`` hands the state block to the stage.
* ``annotator/vision-stage.js``: the row of ``anchorBlock`` reads ``s.anchors.times``, and
  no line of the console states the three seconds as a literal.
* ``src/pid_anchor_ui.py``: the ``SUG`` array of the legacy page, which is the second
  realm of these three times.  A browser page cannot read a python name, so that copy is
  on purpose, and this module holds the two lists equal in value and in order.

What this module does not see
-----------------------------
* It reads text and not meaning.  The rendered row is driven in
  ``tests/test_app_timeline.js``, the case that holds the panel; a row that prints the
  published values in a place the operator never sees passes here.
* ``src/pid_anchor_ui.py`` keeps its module-level list ``SUGGESTED``, which no line reads.
  That file cannot be imported by a case (it reads a calibration file and opens the VOD at
  import time), and the round-71 write scope does not hold it.  The guard of that dead name
  belongs to a later round.
* ``annotator/vision-stage.js:1500`` seeks to 70 s as the first jump of a dataset whose
  anchors are not loaded yet.  That number is the first value of the list, and it stays a
  literal of the fallback path.
* The three values are pinned as a tuple and not as a rule.  Which seconds an operator
  should jump to is a product decision; this module holds the two realms equal and the
  console free of a copy.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = 'annotator/unified_server.py'
CONSOLE = 'annotator/app.js'
STAGE = 'annotator/vision-stage.js'
LEGACY = 'src/pid_anchor_ui.py'

SERVICE_TEXT = (ROOT / SERVICE).read_text(encoding='utf-8')
CONSOLE_TEXT = (ROOT / CONSOLE).read_text(encoding='utf-8')
STAGE_TEXT = (ROOT / STAGE).read_text(encoding='utf-8')
LEGACY_TEXT = (ROOT / LEGACY).read_text(encoding='utf-8')

#: The three values the two realms hold today.  The cases freeze them, so a reader can
#: follow the ground of round 71.
TIMES_TODAY = (70, 200, 350)

#: The one line of the service that states the three times.
SERVICE_HOME = re.compile(r'^SUGGESTED_ANCHOR_TIMES = \(([^)]*)\)$', re.MULTILINE)
#: The one line of ``src/pid_anchor_ui.py`` that states the three times for its page.
LEGACY_HOME = re.compile(r'^const SUG = \[([^\]]*)\];$', re.MULTILINE)
#: The answer line of ``anchor_info``: it publishes the name and states no list.
SERVICE_PUBLISH = re.compile(r'"suggested_times": list\(SUGGESTED_ANCHOR_TIMES\)')
#: The console copy of the three times inside the anchors-at row, as a bare list.
STAGE_LITERAL = re.compile(r'\[70\s*,\s*200\s*,\s*350\]')
#: The one console line that reads the published list.  The stage reads it for the row.
STAGE_READ = re.compile(r'\(s\.anchors\.times \|\| \[\]\)\.map\(x => `<button data-vs-action="anchors-at"')
#: The line of ``loadAnchors`` that copies the published field into the state.
CONSOLE_HAND = re.compile(r'times: \(data\.suggested_times \|\| \[\]\)\.slice\(\)')
#: The initial state block: the same list, empty, so a render before the first answer works.
CONSOLE_STATE = re.compile(r'anchors:\{[^}]*\btimes:\[\]')
#: Every read of the published list in the two console files.
TIMES_READ = re.compile(r's\.anchors\.times\b')


def numbers(text):
    """The integers of one comma-separated group of source text, in order."""
    return tuple(int(part) for part in re.findall(r'\d+', text))


def service_times(text):
    """The three seconds of the service tuple, or ``None`` when the line is not there."""
    found = SERVICE_HOME.search(text)
    return None if found is None else numbers(found.group(1))


def legacy_times(text):
    """The three seconds of the legacy page's own array."""
    found = LEGACY_HOME.search(text)
    return None if found is None else numbers(found.group(1))


def stage_literals(text):
    """One ``(line, text)`` entry for each bare list of the three times in the stage."""
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if STAGE_LITERAL.search(line)]


class Round71AnchorTimes(unittest.TestCase):
    """The service owns the three times, and the console reads the published list."""

    def test_the_service_states_the_three_times_on_one_line(self):
        self.assertEqual(TIMES_TODAY, service_times(SERVICE_TEXT),
                         '%s must state the three suggested anchor times once, as '
                         'SUGGESTED_ANCHOR_TIMES = (70, 200, 350)' % SERVICE)

    def test_the_route_publishes_the_service_name(self):
        self.assertTrue(SERVICE_PUBLISH.search(SERVICE_TEXT),
                        'anchor_info of %s must publish "suggested_times": '
                        'list(SUGGESTED_ANCHOR_TIMES) and state no list of its own' % SERVICE)

    def test_the_stage_row_reads_the_published_list(self):
        self.assertTrue(STAGE_READ.search(STAGE_TEXT),
                        'the anchors-at row of %s must draw one button per published '
                        'value, read from s.anchors.times' % STAGE)

    def test_the_console_states_the_three_times_nowhere(self):
        found = stage_literals(STAGE_TEXT)
        self.assertEqual(
            [], found,
            'the console states the three anchor times as a literal, so a change of the '
            'service list cannot reach the row: %s'
            % '; '.join('%s:%d %s' % (STAGE, line, text) for line, text in found))

    def test_the_console_copies_the_published_field_into_the_state(self):
        self.assertTrue(CONSOLE_HAND.search(CONSOLE_TEXT),
                        'loadAnchors of %s must copy data.suggested_times into '
                        'state.anchors.times, because the stage reads the state' % CONSOLE)
        self.assertTrue(CONSOLE_STATE.search(CONSOLE_TEXT),
                        'the initial state of %s must start anchors.times as an empty '
                        'list, so a render before the first answer draws no button' % CONSOLE)

    def test_the_published_list_has_one_reader(self):
        reads = TIMES_READ.findall(STAGE_TEXT) + TIMES_READ.findall(CONSOLE_TEXT)
        self.assertEqual(
            1, len(reads),
            'the published list must have exactly one reader, the row of %s, and no other '
            'line of the console may read or hold it; found %d site(s)' % (STAGE, len(reads)))

    def test_both_realms_state_the_same_times(self):
        self.assertEqual(TIMES_TODAY, service_times(SERVICE_TEXT),
                         'the service tuple drifted from the values of round 71')
        self.assertEqual(
            TIMES_TODAY, legacy_times(LEGACY_TEXT),
            'the legacy page of %s states a different list of anchor times than the '
            'service tuple, and a browser page cannot read the python name' % LEGACY)
        self.assertEqual(service_times(SERVICE_TEXT), legacy_times(LEGACY_TEXT),
                         'the two realms of the three anchor times disagree')

    def test_a_planted_console_list_is_reported(self):
        planted = STAGE_TEXT.replace(
            '${(s.anchors.times || []).map(',
            '${[70,200,350].map(') if STAGE_READ.search(STAGE_TEXT) else STAGE_TEXT
        self.assertNotEqual(STAGE_TEXT, planted, 'the planted text must differ from the file')
        found = stage_literals(planted)
        self.assertEqual(
            1, len(found),
            'a console list of the three times must be reported with its line: %s' % found)
        self.assertIn('anchors-at', found[0][1],
                      'the reported line must be the anchors-at row of the stage')

    def test_a_planted_service_number_is_reported(self):
        planted = SERVICE_TEXT.replace('SUGGESTED_ANCHOR_TIMES = (70, 200, 350)',
                                       'SUGGESTED_ANCHOR_TIMES = (70, 200, 360)')
        self.assertNotEqual(SERVICE_TEXT, planted, 'the planted text must differ from the file')
        self.assertNotEqual(
            TIMES_TODAY, service_times(planted),
            'a changed service tuple must be reported, so the frozen values cannot drift '
            'in silence')


if __name__ == '__main__':
    unittest.main()
