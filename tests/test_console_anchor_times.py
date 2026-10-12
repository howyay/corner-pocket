"""Round 71, Worth 1: the three anchor times the console offers, held to one home.

Ground of the row.  The three suggested anchor times stood as two bare literals and one
published field:

* ``annotator/unified_server.py`` published ``"suggested_times": [70, 200, 350]`` in the
  answer of ``anchor_info``;
* ``annotator/vision-stage.js`` drew the jump row from its own ``[70,200,350]``, so the
  published field had no reader at all;
* ``src/pid_anchor_ui.py`` held the same three seconds twice more: a module-level name,
  which no line of that file read, and the ``SUG`` array of the legacy page's own script.

A reader of the field could see times the console never drew, and a change of one literal
left the other two behind.  Round 71 gives the list one home in the service realm,
``SUGGESTED_ANCHOR_TIMES``, publishes it from ``anchor_info``, and makes the console row
draw one button per published value.

Round 77, Strong 1 adds the first second of that list, 70 s.  It stood as three homes:

* the tuple ``SUGGESTED_ANCHOR_TIMES`` of ``annotator/unified_server.py``, the owner;
* the default of the anchors route, ``query.integer("t", 70)``, in the same file;
* the default of the console state, ``t:70`` in ``annotator/app.js``.

The guard of round 71 held the three times and measured neither default.  Round 77 makes
the route default read the owner by name, and holds each site that must state the second
itself to the owner's first value.  A browser page cannot read a python name, and each of
those two sites runs before the service has answered:

* ``annotator/app.js`` asks the anchors route at mount, before the first answer, and
  ``tests/test_app_timeline.js`` holds the asked path, ``/api/vod30/anchors?t=70``;
* ``annotator/vision-stage.js`` opens a dataset whose anchors are not loaded yet.

What this module reads
----------------------
* The service tuple ``SUGGESTED_ANCHOR_TIMES`` of ``annotator/unified_server.py``, by one
  regex, and the answer line of ``anchor_info`` that publishes it.
* The default of the anchors route of that file.  Round 77: it reads
  ``SUGGESTED_ANCHOR_TIMES[0]`` and states no number of its own.
* ``annotator/app.js``: ``loadAnchors`` copies the published field into the state, and
  ``snapshot()`` hands the state block to the stage.  The state opens with the same second
  the route default answers, because the console asks before the first answer.
* ``annotator/vision-stage.js``: the row of ``anchorBlock`` reads ``s.anchors.times``, no
  line of the console states the three seconds as a literal, and the fallback path of the
  stage states the first second twice, as the number it loads and the number it seeks to.
* ``src/pid_anchor_ui.py``: the ``SUG`` array of the legacy page, which is the second
  realm of these three times.  A browser page cannot read a python name, so that copy is
  on purpose, and this module holds the two lists equal in value and in order.  Round 85
  removed the module-level name ``SUGGESTED``, which stood beside the page and had no
  reader.  That module cannot be imported by a case (it reads a calibration file and opens
  the VOD at import time), so the case below reads the module as text.

What this module does not see
-----------------------------
* It reads text and not meaning.  The rendered row is driven in
  ``tests/test_app_timeline.js``, the case that holds the panel; a row that prints the
  published values in a place the operator never sees passes here.
* A cited line number is not proof of the fact beside it.  ``tests/test_citation_lines.py``
  proves that the cited line of a file holds a letter or a digit.  It does not compare that
  line with the sentence around the citation, so a citation that points at a line which
  holds another fact passes that rule.  The bullet below named line 1500 of the stage until
  round 77, and that line holds the verdict draft of ``verdictBlock``; only a reader who
  opened the file found it.
* ``src/pid_anchor_ui.py`` states the three seconds once, in the ``SUG`` array of the page
  it serves.  A browser page cannot read a python name, so that copy stays on purpose.  The
  module-level name ``SUGGESTED`` stood beside that array until round 85, and no line read
  it; the case below fails when the name returns.
* ``annotator/vision-stage.js:1490`` loads and seeks 70 s as the first jump of a dataset
  whose anchors are not loaded yet.  That number is the first value of the list, and it
  stays a literal of the fallback path.  A case below holds it to the owner, and reports
  the line when the two sides drift apart.
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
#: Round 85 removed the module-level name that stood beside this line.
LEGACY_HOME = re.compile(r'^const SUG = \[([^\]]*)\];$', re.MULTILINE)
#: Round 85: the module-level name of the legacy module, which had no reader.  The name
#: stands on its own line, so no line of the module reads it.  The case below fails when
#: the name returns.
DEAD_NAME = re.compile(r'^SUGGESTED\b', re.MULTILINE)
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

#: Round 77, Strong 1: the default of the anchors route.  It reads the owner of the first
#: suggested second by name, so a change of the tuple reaches the route default.
ROUTE_DEFAULT = re.compile(
    r'self\.anchor_info\(query\.integer\("t",\s*SUGGESTED_ANCHOR_TIMES\[0\]\)\)')
#: A route default that states the first suggested second as a number of its own.
ROUTE_LITERAL = re.compile(r'self\.anchor_info\(query\.integer\("t",\s*(\d+)')
#: The console's own second, inside the initial anchors state block.
CONSOLE_SECOND = re.compile(r'anchors:\{[^}]*?\bt:(\d+)')
#: The fallback path of the stage: the second it loads and the second it seeks to.
STAGE_FALLBACK = re.compile(r'loadAnchors\((\d+)\)[^\n]*?seekTime\((\d+)\)')


def numbers(text):
    """The integers of one comma-separated group of source text, in order."""
    return tuple(int(part) for part in re.findall(r'\d+', text))


def service_times(text):
    """The three seconds of the service tuple, or ``None`` when the line is not there."""
    found = SERVICE_HOME.search(text)
    return None if found is None else numbers(found.group(1))


def legacy_times(text):
    """The three seconds of the legacy page's own array, or ``None`` when it is gone."""
    found = LEGACY_HOME.search(text)
    return None if found is None else numbers(found.group(1))


def stage_literals(text):
    """One ``(line, text)`` entry for each bare list of the three times in the stage."""
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if STAGE_LITERAL.search(line)]


def site(pattern, text):
    """The ``(line, text)`` of the first match of one pattern, or ``None``."""
    for number, line in enumerate(text.splitlines(), 1):
        if pattern.search(line):
            return number, line.strip()
    return None


def owner_site():
    """The ``path:line`` of the service tuple, or the path alone when the line is gone."""
    found = site(SERVICE_HOME, SERVICE_TEXT)
    return SERVICE if found is None else '%s:%d' % (SERVICE, found[0])


def first_second():
    """The first value of the service tuple, or ``None`` when the tuple is not there."""
    times = service_times(SERVICE_TEXT)
    return None if times is None else times[0]


def route_findings(text):
    """One finding for each way the route default of the service leaves the owner."""
    literal = site(ROUTE_LITERAL, text)
    if literal is not None:
        return ['%s:%d states the route default as a number: %s; it must read '
                'SUGGESTED_ANCHOR_TIMES[0]' % (SERVICE, literal[0], literal[1])]
    if not ROUTE_DEFAULT.search(text):
        return ['%s states no default for the anchors route that reads '
                'SUGGESTED_ANCHOR_TIMES[0]' % SERVICE]
    return []


def console_findings(text, first, owner):
    """One finding for each way the console second leaves the first value of the tuple."""
    found = site(CONSOLE_SECOND, text)
    if found is None:
        return ['%s states no second for anchors.t in its anchors state; the console asks '
                'the anchors route at mount, before %s answers' % (CONSOLE, owner)]
    second = int(CONSOLE_SECOND.search(found[1]).group(1))
    if second != first:
        return ['%s:%d states the console second %d, but %s holds '
                'SUGGESTED_ANCHOR_TIMES[0] = %d; the two sides must state one second'
                % (CONSOLE, found[0], second, owner, first)]
    return []


def stage_findings(text, first, owner):
    """One finding for each way the fallback second of the stage leaves the tuple."""
    found = site(STAGE_FALLBACK, text)
    if found is None:
        return ['%s states no fallback that loads and seeks the first suggested second'
                % STAGE]
    loaded, seeked = (int(value) for value in STAGE_FALLBACK.search(found[1]).groups())
    if loaded != seeked:
        return ['%s:%d loads second %d and seeks second %d; the fallback path states one '
                'second' % (STAGE, found[0], loaded, seeked)]
    if loaded != first:
        return ['%s:%d states the fallback second %d, but %s holds '
                'SUGGESTED_ANCHOR_TIMES[0] = %d; the two sides must state one second'
                % (STAGE, found[0], loaded, owner, first)]
    return []


def dead_name_findings(text):
    """One finding for the module-level name of the legacy module, or an empty list."""
    found = site(DEAD_NAME, text)
    if found is None:
        return []
    return ['%s:%d holds the module-level name SUGGESTED, which no line reads; the page '
            'copy in the SUG array is the only copy this module keeps'
            % (LEGACY, found[0])]


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

    def test_the_legacy_page_states_the_three_times(self):
        self.assertEqual(TIMES_TODAY, service_times(SERVICE_TEXT),
                         'the service tuple drifted from the values of round 71')
        self.assertEqual(
            TIMES_TODAY, legacy_times(LEGACY_TEXT),
            'the legacy page of %s states a different list of anchor times than the '
            'service tuple, and a browser page cannot read the python name' % LEGACY)
        self.assertEqual(service_times(SERVICE_TEXT), legacy_times(LEGACY_TEXT),
                         'the page copy of %s and the service tuple disagree' % LEGACY)

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


class Round77FirstSecond(unittest.TestCase):
    """The first suggested second has one owner, and two sites that must state it."""

    def test_the_route_default_reads_the_service_first_second(self):
        found = route_findings(SERVICE_TEXT)
        self.assertEqual(
            [], found,
            'the default of the anchors route of %s must read the owner of the first '
            'suggested second, so that a change of the tuple reaches it: %s'
            % (SERVICE, '; '.join(found)))

    def test_the_console_states_the_owner_first_second(self):
        first = first_second()
        self.assertIsNotNone(first, 'the service tuple must state the first suggested second')
        found = console_findings(CONSOLE_TEXT, first, owner_site())
        self.assertEqual(
            [], found,
            'the console asks the anchors route at mount, before the first answer, so its '
            'state must state the same second as the owner: %s' % '; '.join(found))

    def test_the_stage_fallback_states_the_owner_first_second(self):
        first = first_second()
        self.assertIsNotNone(first, 'the service tuple must state the first suggested second')
        found = stage_findings(STAGE_TEXT, first, owner_site())
        self.assertEqual(
            [], found,
            'the fallback path of %s opens a dataset whose anchors are not loaded yet, so it '
            'must state the same second as the owner: %s' % (STAGE, '; '.join(found)))

    def test_a_planted_route_number_is_reported(self):
        planted = SERVICE_TEXT.replace('SUGGESTED_ANCHOR_TIMES[0]', '100')
        self.assertNotEqual(SERVICE_TEXT, planted, 'the planted text must differ from the file')
        found = route_findings(planted)
        self.assertEqual(1, len(found),
                         'a route default that states the first suggested second as a number '
                         'must be reported with its line')
        self.assertIn(SERVICE + ':', found[0], 'the finding must name the site')
        self.assertIn('100', found[0], 'the finding must name the planted number')

    def test_a_planted_console_second_is_reported(self):
        planted = CONSOLE_TEXT.replace('t:70, times:[]', 't:100, times:[]')
        self.assertNotEqual(CONSOLE_TEXT, planted, 'the planted text must differ from the file')
        found = console_findings(planted, first_second(), owner_site())
        self.assertEqual(1, len(found),
                         'a console second away from the owner must be reported')
        self.assertIn(CONSOLE + ':', found[0], 'the finding must name the site')
        self.assertIn(owner_site(), found[0], 'the finding must name the owner')

    def test_a_planted_stage_number_is_reported_with_the_owner(self):
        planted = STAGE_TEXT.replace('loadAnchors(70)', 'loadAnchors(100)').replace(
            'seekTime(70)', 'seekTime(100)')
        self.assertNotEqual(STAGE_TEXT, planted, 'the planted text must differ from the file')
        found = stage_findings(planted, first_second(), owner_site())
        self.assertEqual(1, len(found),
                         'a fallback second away from the owner must be reported')
        self.assertIn(STAGE + ':', found[0], 'the finding must name the site')
        self.assertIn(owner_site(), found[0], 'the finding must name the owner')

    def test_a_planted_stage_pair_is_reported(self):
        planted = STAGE_TEXT.replace('loadAnchors(70)', 'loadAnchors(100)')
        self.assertNotEqual(STAGE_TEXT, planted, 'the planted text must differ from the file')
        found = stage_findings(planted, first_second(), owner_site())
        self.assertEqual(1, len(found),
                         'a fallback path that loads one second and seeks another must be '
                         'reported')
        self.assertIn(STAGE + ':', found[0], 'the finding must name the site')


class Round85DeadName(unittest.TestCase):
    """The legacy module names the three seconds once, in the page it serves."""

    def test_the_legacy_module_holds_no_dead_name(self):
        found = dead_name_findings(LEGACY_TEXT)
        self.assertEqual(
            [], found,
            'the module-level name SUGGESTED of %s stood beside the page copy and no line '
            'read it, so the name left that file in round 85; restore the name only with a '
            'reader: %s' % (LEGACY, '; '.join(found)))

    def test_the_page_copy_is_the_one_copy_of_the_legacy_module(self):
        self.assertEqual(
            TIMES_TODAY, legacy_times(LEGACY_TEXT),
            'the SUG array of the page that %s serves must state the three anchor times, '
            'because a browser page cannot read a python name' % LEGACY)

    def test_a_planted_dead_name_is_reported(self):
        planted = LEGACY_TEXT.replace(
            'CALIB = ROOT.parent / "out" / "calib_vod30.json"',
            'CALIB = ROOT.parent / "out" / "calib_vod30.json"\n'
            'SUGGESTED = [70, 200, 350]')
        self.assertNotEqual(LEGACY_TEXT, planted, 'the planted text must differ from the file')
        found = dead_name_findings(planted)
        self.assertEqual(
            1, len(found),
            'a module-level name with no reader must be reported with its line, so the name '
            'cannot return in silence: %s' % found)
        self.assertIn(LEGACY + ':', found[0], 'the finding must name the site')


if __name__ == '__main__':
    unittest.main()
