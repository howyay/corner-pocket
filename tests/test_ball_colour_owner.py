"""One list of ball colour words, held by both pages that spell the words out.

Two files name the colour of a ball in words:

* ``annotator/label.html`` holds ``const NAMES``, the labelling page's map from a
  ball number to the word that the operator reads.  Entry 0 is the cue ball,
  entries 1 to 8 are the solids, and entries 9 to 15 are the stripes.
* ``annotator/ops.js`` holds the two comment lines above ``const ballPalette``,
  the comment that names the hue of each ball number.

The two lists must agree, word for word, in order.  The stripe entries must
carry the same words as the solid entries.  A copy can drift from its neighbour
with nothing to report it, so this module reads both files and names every
mismatch as ``file:line word``.

Nothing here holds a colour word of its own.  The map and the comment are the
two sources, and the cases below plant a word that no side holds, so the report
of a mismatch stays measured.
"""
import re
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: The labelling page: its ``NAMES`` map names ball 0 to ball 15.
MAP_FILE = "annotator/label.html"
#: The console page: its palette comment names ball 1 to ball 15.
COMMENT_FILE = "annotator/ops.js"
#: The one name that starts the map.
MAP_NAME = "NAMES"
#: The one statement that the colour comment introduces.
PALETTE_NAME = "ballPalette"
#: Ball 0 is the cue ball; ball 15 is the last ball the service accepts.
BALL_FIRST = 0
BALL_LAST = 15
#: Ball 8 is the last solid; ball 9 is the first stripe.
SOLID_LAST = 8
#: How many hues the stripes repeat: the colours of balls 1 to 7.
HUE_COUNT = 7
#: A word is a run of letters, so the parser stays simple.
WORD_RE = re.compile(r"[A-Za-z]+")
#: A token of a comment line: a number or a word.  The parser needs both, since
#: the ball number and the hue word stand in the same line.
TOKEN_RE = re.compile(r"[A-Za-z]+|[0-9]+")
#: A run of digits, read as a ball number.
NUMBER_RE = re.compile(r"[0-9]+")
#: A comment line of the palette block, after the two slash marks are dropped.
COMMENT_RE = re.compile(r"^//(.*)$")
#: One entry of the map: the key, the colon, then the value in single quotes.
#: The value holds no quote and no newline, so the map body stays readable.
MAP_ENTRY_RE = re.compile(r"([0-9]+)\s*:\s*'([^'\n]*)'")
#: A solid entry: the ball number, then the hue word.
SOLID_WORD_RE = re.compile(r"^\s*\d+\s+([a-z]+)\s*$")
#: A stripe entry: the ball number, the hue word, then the word ``str``.
STRIPE_WORD_RE = re.compile(r"^\s*\d+\s+([a-z]+)\s+str\s*$")
#: The first number of a comment line, and the words that follow it.  The head
#: of the line names the ball, and the first word after that number is its hue.
HEAD_RE = re.compile(r"^[^0-9]*([0-9]+)(.*)$")
#: A colour word of a comment line is a word, and ``the``, ``same``, ``hues``,
#: ``as`` and ``str`` are the words of the sentence around it.
STOP_WORDS = frozenset({"the", "same", "hues", "as", "str"})


def _report(rel, line, word):
    """The report of one entry, in the shape ``file:line word``."""
    return "%s:%d %s" % (rel, line, word)


def _by_ball(entries):
    """The entries of one source, keyed by ball number."""
    return {ball: (line, word) for ball, line, word in entries}


def _text(rel):
    """The text of one project file, or None when the file is absent."""
    path = ROOT / rel
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _source_text(rel):
    """The text of one project file, read once for the whole module."""
    return _text(rel)


def _line_of(text, position):
    """The 1-based line number of one character position."""
    return text.count("\n", 0, position) + 1


def _words(text):
    """Every word of a line, in order, each one lowered."""
    return [m.group(0).lower() for m in WORD_RE.finditer(text)]


def _named_entries(text, start_line=1):
    """The map entries of the text, as ``(key, line, value)``, keyed in order.

    The scan reads the body of ``MAP_NAME`` once, keeps each value in single
    quotes, and reads the key that stands before each value.  A key that stands
    twice keeps its first line.
    """
    head = re.search(r"\b%s\s*=\s*\{" % MAP_NAME, text)
    if not head:
        return []
    body_start = head.end()
    stop = text.find("}", body_start)
    body = text[body_start:] if stop < 0 else text[body_start:stop]
    found = {}
    for match in MAP_ENTRY_RE.finditer(body):
        key = int(match.group(1))
        if key in found:
            continue
        found[key] = (_line_of(text, body_start + match.start(1)), match.group(2))
    return [(key, found[key][0], found[key][1]) for key in sorted(found)]


def names_map_entries(text=None):
    """The colour entry of each ball, from the map of the labelling page."""
    if text is None:
        text = _source_text(MAP_FILE)
    if text is None:
        return []
    return _named_entries(text)


def ball_palette_comment_entries(text=None):
    """The hue word of each ball number, from the palette comment of the console.

    The block is the run of comment lines that ends at the line which holds
    ``const ballPalette``.  The first number of a line names one ball, and the
    word that follows that number is the hue of the ball.  A later number in the
    same line names the next ball.
    """
    if text is None:
        text = _source_text(COMMENT_FILE)
    if text is None:
        return []
    lines = text.split("\n")
    end = None
    for index, line in enumerate(lines):
        if re.search(r"\bconst\s+%s\b" % PALETTE_NAME, line):
            end = index
            break
    if end is None:
        return []
    start = end
    while start > 0 and COMMENT_RE.match(lines[start - 1]):
        start -= 1
    # The comment names its balls in the shape "1 yellow, 2 blue": a number,
    # then the hue of that ball.  The first number of a line selects the ball
    # of that line; a later number in the same line selects the next ball.  A
    # line without a number keeps the ball of the line before it, so the
    # sentence under the list does not invent a ball.
    ball = None
    hue_pending = False
    found = {}
    for index in range(start, end):
        body = COMMENT_RE.match(lines[index]).group(1)
        head = HEAD_RE.match(body)
        if head is None:
            continue
        ball = int(head.group(1))
        hue_pending = True
        for token in TOKEN_RE.findall(head.group(2).lower()):
            if NUMBER_RE.match(token):
                ball = int(token)
                hue_pending = True
                continue
            if token in STOP_WORDS:
                continue
            if hue_pending and ball is not None and ball not in found:
                found[ball] = (index + 1, token)
            hue_pending = False
    return [(ball, found[ball][0], found[ball][1]) for ball in sorted(found)]


def _hue_of(value):
    """The hue word of one map value.

    A solid entry holds the ball number and the hue word.  A stripe entry adds
    the word ``str``.  A value that reads as neither (entry 0, ``cue/white``)
    answers None: the cue ball is not one of the fifteen colours.
    """
    for pattern in (SOLID_WORD_RE, STRIPE_WORD_RE):
        match = pattern.match(value)
        if match:
            return match.group(1)
    return None


class BallColourOwnerTest(unittest.TestCase):
    """The map and the comment hold one list of colour words."""

    def setUp(self):
        """Read the two sources, and state which file answers nothing."""
        self.map_entries = names_map_entries()
        self.comment_entries = ball_palette_comment_entries()
        self.assertIsNotNone(_text(MAP_FILE), "%s: the file is absent" % MAP_FILE)
        self.assertIsNotNone(_text(COMMENT_FILE), "%s: the file is absent" % COMMENT_FILE)
        self.assertTrue(self.map_entries, "%s: no named entry" % MAP_FILE)
        self.assertTrue(self.comment_entries, "%s: no named entry" % COMMENT_FILE)
        #: The line of the first map entry, the fallback report of a missing key.
        self.map_start = self.map_entries[0][1]
        #: The line of the first comment entry, the same fallback for the comment.
        self.comment_start = self.comment_entries[0][1]

    def _map_word(self, ball, entries=None):
        """The report of one ball of the map: the file, the line and the word."""
        table = _by_ball(self.map_entries if entries is None else entries)
        entry = table.get(ball)
        if entry is None:
            return (MAP_FILE, self.map_start, "<ball %d>" % ball)
        word = _hue_of(entry[1])
        if word is None:
            return (MAP_FILE, entry[0], "<word>")
        return (MAP_FILE, entry[0], word)

    def _comment_word(self, ball, entries=None):
        """The report of one ball of the comment: the file, the line and the word."""
        table = _by_ball(self.comment_entries if entries is None else entries)
        entry = table.get(ball)
        if entry is None:
            return (COMMENT_FILE, self.comment_start, "<ball %d>" % ball)
        return (COMMENT_FILE, entry[0], entry[1])

    def _disagreement(self, map_entries=None, comment_entries=None):
        """Every solid ball whose two words differ, as ``file:line word`` text."""
        report = []
        for ball in range(1, SOLID_LAST + 1):
            here = self._map_word(ball, map_entries)
            there = self._comment_word(ball, comment_entries)
            if here[2] != there[2]:
                report.append("ball %d: %s; %s" % (ball, _report(*here), _report(*there)))
        return report

    def test_the_map_and_the_comment_hold_one_list_in_order(self):
        """The solid words of the map equal the words of the comment, in order."""
        report = self._disagreement()
        self.assertEqual(
            report,
            [],
            "the map and the comment disagree:\n" + "\n".join(report),
        )

    def test_the_map_holds_sixteen_entries_and_the_stripes_repeat_the_solids(self):
        """The map covers ball 0 to ball 15, and each stripe repeats its solid."""
        self.assertEqual(
            sorted(_by_ball(self.map_entries)),
            list(range(BALL_FIRST, BALL_LAST + 1)),
            "%s: the map must hold ball 0 to ball 15" % MAP_FILE,
        )
        report = []
        for ball in range(SOLID_LAST + 1, BALL_LAST + 1):
            here = self._map_word(ball)
            # Ball 9 repeats ball 1, so the solid of a stripe stands eight
            # balls before it: the number of the last solid.
            there = self._map_word(ball - SOLID_LAST)
            if here[2] != there[2]:
                report.append("ball %d: %s; %s" % (ball, _report(*here), _report(*there)))
        self.assertEqual(
            report,
            [],
            "a stripe does not repeat its solid:\n" + "\n".join(report),
        )

    def test_a_planted_word_in_the_comment_is_reported(self):
        """A colour word that the map does not hold must reach the report.

        The stub keeps the line count, so the line of the report is the line
        number that a reader finds in the real file.
        """
        text = _text(COMMENT_FILE)
        planted = text.replace("pink", "teal")
        self.assertEqual(
            text.count("pink"), planted.count("teal"), "the planted word did not land"
        )
        entries = ball_palette_comment_entries(planted)
        report = self._disagreement(comment_entries=entries)
        self.assertTrue(report, "the guard hid a planted word")
        self.assertIn("teal", "\n".join(report), "the report does not name the planted word")
        line = _by_ball(entries)[4][0]
        self.assertIn(
            _report(COMMENT_FILE, line, "teal"),
            "\n".join(report),
            "the report does not name the file and the line",
        )

    def test_a_planted_word_in_the_map_is_reported(self):
        """The reverse plant: a colour word of the map that the comment lacks."""
        text = _text(MAP_FILE)
        planted = text.replace("blue", "teal")
        self.assertEqual(
            text.count("blue"), planted.count("teal"), "the planted word did not land"
        )
        entries = names_map_entries(planted)
        report = self._disagreement(map_entries=entries)
        self.assertTrue(report, "the guard hid a planted word")
        self.assertIn("teal", "\n".join(report), "the report does not name the planted word")
        line = _by_ball(entries)[2][0]
        self.assertIn(
            _report(MAP_FILE, line, "teal"),
            "\n".join(report),
            "the report does not name the file and the line",
        )


if __name__ == "__main__":
    unittest.main()
