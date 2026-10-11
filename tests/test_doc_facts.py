"""Two live documents must state the ball size that one module owns.

Why this case exists
--------------------
``docs/research-video-world-models.md`` stated a cloth scale of about 2.8 mm/px at
the working frame and a ball of about 20 px.  It cited the comment in
``src/ball_census.py`` that held that sentence.  Round 50 made ``src/ball_scale.py``
the one owner of the ball's measured size.  The owner states the median diameter of
its run at the native frame, and ``diameter_px(WORKING_FRAME)`` answers the width at
the working frame.  Round 50 deleted the census comment, so the cited line holds
other text today, and it re-derived the queue's 2.0-diameter bar.  ``docs/state.md``
repeated the retired working-frame rule and the retired bar.  No case read a
document, so two copies of one fact differed by 41 % and nothing failed.

Three rules, one pass over two files:

1. **owner rule** - each document names ``src/ball_scale.py``, and holds the owner's
   native and working-frame diameters as text.  This file formats both strings from
   the module at run time.  It states no measurement of its own.
2. **retired rule** - the retired working-frame rule ``18.4 px x`` and the retired
   bar ``27.6 px bar`` may appear only near a word that marks them as history.  A
   document that states either one as the rule of today fails.
3. **citation rule** - every ``path.ext:NN`` a document states must resolve to a
   file, and line NN of that file must hold a letter or a digit.  The shape is the
   one ``tests/test_citation_lines.py`` uses for the code side.  That case holds
   ``docs`` in its ``SKIP_PARTS``, so the document side had no reader at all.

What this case does not see
---------------------------
* it reads two documents **by name**.  A third document that states the ball size,
  or the retired rule, is invisible to it.  A new document joins the rule only when
  a reader adds it to ``DOCS``;
* it reads text and not meaning.  A document can hold the owner's number in an
  unrelated sentence and pass.  A document that states the retired rule in other
  words ("the old bar near 28 px") passes too;
* the citation rule proves that a reader finds a line with text on it.  It never
  proves that the line holds the fact the document names.  A citation to a line of
  other text passes;
* it does not measure the ball.  ``tests/test_ball_scale.py`` holds that
  measurement.  This case only asks the two documents to agree with the owner.
"""
import re
import unittest
from pathlib import Path

from src.ball_scale import DIAMETER_NATIVE_PX, WORKING_FRAME, diameter_px

ROOT = Path(__file__).resolve().parents[1]

#: The documents this case reads.  A document that states the ball size but is not
#: in this tuple is invisible to the three rules below.
DOCS = (
    ROOT / 'docs' / 'research-video-world-models.md',
    ROOT / 'docs' / 'state.md',
)

#: The one module that owns the ball's measured size.
OWNER = 'src/ball_scale.py'

#: The two strings the retired rule reads: the working-frame rule and the bar of the
#: rounds before round 50.  Round 50 replaced both.
RETIRED_STRINGS = ('18.4 px x', '27.6 px bar')

#: A word near a retired string that makes it history instead of the rule of today.
RETIRED_MARKERS = ('retired', 'round 50', 'superseded', 'no longer holds', 'replaced')

#: How many lines either side of an occurrence the marker may sit on.
MARKER_WINDOW = 3

# A citation is a path with one of the three extensions, a colon and a number.  The
# lookbehind refuses a citation inside a URL or a longer word.
CITATION = re.compile(r'(?<![\w/:.-])([A-Za-z0-9_./-]+\.(?:py|js|css)):(\d+)')

# The directories that hold the file a citation may name with a bare name.
RESCUE_DIRS = ('', 'src', 'annotator', 'tests', 'db', 'scripts', 'tools')

# The two documents held 4 citations when this case was written.  The floor fails a
# scan that reads no citation at all, which would make the rule below pass for free.
MIN_CITATIONS = 2


def native_diameter_text():
    """The owner's native diameter, as the documents must state it."""
    return '%.1f' % DIAMETER_NATIVE_PX


def working_diameter_text():
    """The owner's working-frame diameter, as the documents must state it."""
    return '%.3f' % diameter_px(WORKING_FRAME)


def read(path):
    """The text of one document."""
    return path.read_text(encoding='utf-8', errors='replace')


def name_of(path):
    """The path of one document inside the repository."""
    return path.relative_to(ROOT).as_posix()


def owner_findings(text, name):
    """Every way one document fails to state the size its owner holds."""
    bad = []
    if OWNER not in text:
        bad.append('%s: names no owner for the ball size (%s)' % (name, OWNER))
    for frame, wanted in (('native', native_diameter_text()),
                          ('working-frame', working_diameter_text())):
        if wanted not in text:
            bad.append('%s: states no %s diameter of the owner (%s px)' % (name, frame, wanted))
    return bad


def retired_findings(text, name, window=MARKER_WINDOW):
    """Every way one document states a retired number as the rule of today."""
    lines = text.splitlines()
    bad = []
    for number, line in enumerate(lines, start=1):
        for token in RETIRED_STRINGS:
            if token not in line:
                continue
            first = max(0, number - 1 - window)
            last = min(len(lines), number + window)
            near = '\n'.join(lines[first:last]).lower()
            if not any(marker in near for marker in RETIRED_MARKERS):
                bad.append('%s:%d states the retired rule as live: %r' % (name, number, token))
    return bad


def resolve(target):
    """The file a citation names, or None.  A bare name reads the module dirs."""
    for base in RESCUE_DIRS:
        candidate = ROOT / base / target
        if candidate.is_file():
            return candidate
    return None


def holds_text(line):
    """True when the line holds a letter or a digit, so a reader finds a fact."""
    return any(char.isalnum() for char in line)


def citation_findings(text, name):
    """Every citation of one document that a reader cannot follow."""
    bad = []
    for match in CITATION.finditer(text):
        line = text[:match.start()].count('\n') + 1
        target = resolve(match.group(1))
        if target is None:
            bad.append('%s:%d -> %s (no such file)' % (name, line, match.group(0)))
            continue
        lines = read(target).splitlines()
        number = int(match.group(2))
        if number < 1 or number > len(lines):
            bad.append('%s:%d -> %s (the file holds %d lines)'
                       % (name, line, match.group(0), len(lines)))
        elif not holds_text(lines[number - 1]):
            bad.append('%s:%d -> %s (the line holds no text)' % (name, line, match.group(0)))
    return bad


def citations_of(text):
    """Every citation one document states."""
    return list(CITATION.finditer(text))


def document_findings():
    """Every finding of the three rules over the two documents."""
    bad = []
    for path in DOCS:
        text = read(path)
        bad.extend(owner_findings(text, name_of(path)))
        bad.extend(retired_findings(text, name_of(path)))
        bad.extend(citation_findings(text, name_of(path)))
    return bad


class DocFactsTests(unittest.TestCase):
    """The two live documents agree with the ball's one owner."""

    def test_the_rule_reads_its_numbers_from_the_owner(self):
        """The two strings come from the module, and they are two different values."""
        self.assertRegex(native_diameter_text(), r'^\d+\.\d$')
        self.assertRegex(working_diameter_text(), r'^\d+\.\d{3}$')
        self.assertNotEqual(native_diameter_text(), working_diameter_text(),
                            'the native and the working-frame diameter differ, so a document '
                            'that states one of them does not state the other')

    def test_the_two_documents_state_the_size_of_their_owner(self):
        """The owner rule: both live documents state the owner and its two diameters."""
        for path in DOCS:
            text = read(path)
            self.assertEqual([], owner_findings(text, name_of(path)),
                             'a live document lost the ball size of %s' % OWNER)

    def test_no_document_states_a_retired_number_as_live(self):
        """The retired rule: either string is refused unless a word marks it as history."""
        found = []
        for path in DOCS:
            found.extend(retired_findings(read(path), name_of(path)))
        self.assertEqual([], found,
                         'a document states a retired number as the rule of today')

    def test_every_citation_of_the_two_documents_is_readable(self):
        """The citation rule: each cited line of each document holds text."""
        found = []
        for path in DOCS:
            found.extend(citation_findings(read(path), name_of(path)))
        self.assertEqual([], found, 'a citation must name a line that holds text')

    def test_the_scan_reads_the_citations_of_the_two_documents(self):
        """The floor: a scan that reads no citation would pass the rule above for free."""
        total = sum(len(citations_of(read(path))) for path in DOCS)
        self.assertGreaterEqual(total, MIN_CITATIONS,
                                'the scan must read the citations of the two documents')

    def test_the_three_rules_are_clean_on_the_two_live_documents(self):
        """One live failure, with all three rules in it, instead of one failure per rule."""
        self.assertEqual([], document_findings(),
                         'the live documents must agree with %s' % OWNER)

    # --- one deliberate bite per rule -------------------------------------------

    def test_a_document_without_the_owner_number_is_refused(self):
        """Bite of the owner rule: a document that states no size of the owner."""
        text = 'The cloth is fine and the ball is round.\n'
        self.assertEqual(
            ['probe.md: names no owner for the ball size (%s)' % OWNER,
             'probe.md: states no native diameter of the owner (%s px)'
             % native_diameter_text(),
             'probe.md: states no working-frame diameter of the owner (%s px)'
             % working_diameter_text()],
            owner_findings(text, 'probe.md'))

    def test_a_document_that_states_the_retired_bar_as_live_is_refused(self):
        """Bite of the retired rule: the gate bar of the rounds before round 50."""
        text = 'A shot must travel 2 diameters, which is the 27.6 px bar of this gate.\n'
        self.assertEqual(["probe.md:1 states the retired rule as live: '27.6 px bar'"],
                         retired_findings(text, 'probe.md'))

    def test_a_document_that_states_the_retired_frame_rule_as_live_is_refused(self):
        """Bite of the retired rule: the working-frame rule the census comment held."""
        text = 'ball_diameter_px = 18.4 px x frame_size[0]/1280\n'
        self.assertEqual(["probe.md:1 states the retired rule as live: '18.4 px x'"],
                         retired_findings(text, 'probe.md'))

    def test_a_document_that_names_the_retired_pair_as_history_passes(self):
        """The other side of the bite: a retired number with a marker is honest."""
        text = ('The 27.6 px bar below is retired; round 50 re-derived the bar to %s px.\n'
                % working_diameter_text())
        self.assertEqual([], retired_findings(text, 'probe.md'))

    def test_a_citation_to_a_line_without_text_is_refused(self):
        """Bite of the citation rule: a cited line that gives the reader nothing."""
        target = ROOT / 'tests' / 'test_doc_facts.py'
        lines = read(target).splitlines()
        blank = next(number for number, line in enumerate(lines, 1) if not line.strip())
        text = 'See tests/test_doc_facts.py:%d for the rule.\n' % blank
        self.assertEqual(['probe.md:1 -> tests/test_doc_facts.py:%d (the line holds no text)'
                          % blank],
                         citation_findings(text, 'probe.md'))

    def test_a_citation_to_a_missing_file_is_refused(self):
        """Bite of the citation rule: a file that does not exist."""
        text = 'See no_such_module.py:3 for the rule.\n'
        self.assertEqual(['probe.md:1 -> no_such_module.py:3 (no such file)'],
                         citation_findings(text, 'probe.md'))


if __name__ == '__main__':
    unittest.main()
