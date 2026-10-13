"""The load harness reads the board's poll interval from the file that owns it.

``annotator/board.js:15`` states the pace of the public board:

    const POLL_MS = 3000, STALE_MS = 15000, TIMEOUT_MS = 8000;

``tests/load_public_board.py`` re-typed that number in four places: ``--interval`` carried
``default=3.0``, the help text said "(default 3)", the module docstring said "every 3 s",
and ``poll()``'s docstring said "a 3 s interval".  A copy cannot follow an edit of
``POLL_MS``: the harness would poll at the old rate, every load number it reports would
belong to a rate no phone uses, and the python suite would stay green.  No case named the
harness, so nothing reported the drift.

The harness now reads ``annotator/board.js`` as text -- it must not import a browser
module -- and the ``--interval`` default and its help text take ``POLL_MS / 1000`` from that
read.  The cases below hold the read in place:

1. the owner states one ``POLL_MS = <number>`` binding, on the line a report names;
2. the harness default is the owner's value in seconds, and the ``--interval`` argument
   takes that default from the reader and from no number;
3. the harness holds no second literal of the interval, in code or in prose;
4. a number planted in memory moves the default, and the report names the owner's file and
   its line;
5. the row of ``docs/public-board-load.md`` that drives the load like the page states the
   owner's number, so the document cannot drift from the board unnoticed.

``docs/public-board-load.md:12`` states ``POLL_MS = 3000`` and 3 s; the owner agrees, so
that row is the record of a measured run and not a copy to repair.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import load_public_board as harness  # noqa: E402  (the module under guard)

#: The harness, the owner it must read, and the document that drives the load like the page.
HARNESS = ROOT / "tests" / "load_public_board.py"
OWNER = ROOT / "annotator" / "board.js"
DOCUMENT = ROOT / "docs" / "public-board-load.md"
HARNESS_SHOWN = "tests/load_public_board.py"
OWNER_SHOWN = "annotator/board.js"
#: The document row that states the pace: docs/public-board-load.md:12.
DOCUMENT_ROW = 12
#: The one binding the harness must read, written as the owner writes it.
BINDING = re.compile(r"\bPOLL_MS\s*=\s*(\d+(?:\.\d+)?)")
#: The reader the --interval argument must call for its default.
READER = "poll_seconds"


def line_of(text, index):
    """The 1-based line number that holds a character index of `text`."""
    return text.count("\n", 0, index) + 1


def argument_source(text, flag):
    """The source of one add_argument call, and the line the call starts on.

    The call holds a nested call in its help text, so the scan counts parentheses and does
    not stop at the first closing one.
    """
    start = text.find('add_argument("%s"' % flag)
    if start < 0:
        return None, None
    depth, index = 0, text.index("(", start)
    while index < len(text):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return text[start:index + 1], line_of(text, start)
        index += 1
    return text[start:], line_of(text, start)


class IntervalOwnerTest(unittest.TestCase):
    """The read of annotator/board.js: what the harness states, and where it states it."""

    @classmethod
    def setUpClass(cls):
        cls.harness_text = HARNESS.read_text(encoding="utf-8")
        cls.owner_text = OWNER.read_text(encoding="utf-8")
        cls.bindings = [(line_of(cls.owner_text, match.start()), match.group(1))
                        for match in BINDING.finditer(cls.owner_text)]

    def owner_binding(self):
        """The owner's one line and the number on it, for the cases below."""
        self.assertEqual(1, len(self.bindings),
                         "%s states %d `POLL_MS = <number>` bindings %s; the poll interval "
                         "must have one owner" % (OWNER_SHOWN, len(self.bindings), self.bindings))
        return self.bindings[0]

    def test_the_owner_states_one_poll_ms_binding(self):
        """The reader below needs one binding, and the report must name its line."""
        line, milliseconds = self.owner_binding()
        self.assertGreater(float(milliseconds), 0.0,
                           "%s:%d states POLL_MS = %s" % (OWNER_SHOWN, line, milliseconds))
        self.assertIn("POLL_MS = %s" % milliseconds, self.owner_text.splitlines()[line - 1],
                      "%s:%d must hold the binding the report names" % (OWNER_SHOWN, line))

    def test_the_harness_default_is_the_owners_poll_ms_in_seconds(self):
        line, milliseconds = self.owner_binding()
        seconds = float(milliseconds) / 1000.0
        citation = "%s:%d" % (OWNER_SHOWN, line)
        statement, at = argument_source(self.harness_text, "--interval")
        self.assertIsNotNone(statement, "%s states no --interval argument" % HARNESS_SHOWN)
        self.assertNotRegex(statement, r"default\s*=\s*[0-9]",
                            "%s:%d re-types the poll interval as a number; %s owns "
                            "POLL_MS = %s" % (HARNESS_SHOWN, at, citation, milliseconds))
        self.assertRegex(statement, r"default\s*=\s*%s\(\)" % READER,
                         "%s:%d must take the --interval default from the reader of %s: %s"
                         % (HARNESS_SHOWN, at, citation, statement))
        answered = harness.poll_seconds()
        self.assertEqual(seconds, answered,
                         "%s:%d answers a %s s default; %s states POLL_MS = %s (%s s)"
                         % (HARNESS_SHOWN, at, answered, citation, milliseconds, seconds))
        self.assertEqual(OWNER.resolve(), Path(harness.BOARD_JS).resolve(),
                         "the harness reads %s for the interval, not %s"
                         % (harness.BOARD_JS, OWNER))

    def test_the_harness_holds_no_second_literal_of_the_interval(self):
        line, milliseconds = self.owner_binding()
        seconds = "%g" % (float(milliseconds) / 1000.0)
        copies = (
            (r"\b%s\s*s\b" % re.escape(seconds), "the seconds next to the unit s"),
            (r"\b%g\b" % (float(milliseconds),), "the milliseconds"),
            (r"default\s*=\s*%s(?:\.\d+)?\b" % re.escape(seconds), "a numeric default"),
        )
        for pattern, shape in copies:
            hits = ["%s:%d states %r (%s)"
                    % (HARNESS_SHOWN, line_of(self.harness_text, match.start()),
                       match.group(0), shape)
                    for match in re.finditer(pattern, self.harness_text)]
            self.assertEqual([], hits, "\n".join(
                hits + ["%s:%d owns POLL_MS = %s; the harness must read it and not re-type it"
                        % (OWNER_SHOWN, line, milliseconds)]))

    def test_a_planted_number_moves_the_default_and_the_report_names_the_line(self):
        line, _milliseconds = self.owner_binding()
        planted = BINDING.sub("POLL_MS = 4500", self.owner_text, count=1)
        self.assertNotEqual(self.owner_text, planted, "the planted edit must reach the binding")
        self.assertIn("POLL_MS = 4500", planted.splitlines()[line - 1],
                      "the planted binding must stay on %s:%d" % (OWNER_SHOWN, line))
        answered, citation = harness.board_poll(planted)
        self.assertEqual("%s:%d" % (OWNER_SHOWN, line), citation,
                         "the report must name the owner's file and its line; it answered %s"
                         % citation)
        self.assertEqual(4.5, answered,
                         "the harness must read the planted POLL_MS = 4500 as 4.5 s; it "
                         "answered %s s" % answered)
        moved = harness.poll_seconds(planted)
        self.assertEqual(4.5, moved,
                         "the --interval default must follow the planted value at %s; it "
                         "answered %s s" % (citation, moved))

    def test_the_document_row_states_the_owners_number(self):
        line, milliseconds = self.owner_binding()
        row = DOCUMENT.read_text(encoding="utf-8").splitlines()[DOCUMENT_ROW - 1]
        self.assertIn("POLL_MS = %s" % milliseconds, row,
                      "docs/public-board-load.md:%d must state POLL_MS = %s of %s:%d; it "
                      "states %r" % (DOCUMENT_ROW, milliseconds, OWNER_SHOWN, line, row))
        seconds = "%g" % (float(milliseconds) / 1000.0)
        self.assertRegex(row, r"every\s+%s\s*s\b" % re.escape(seconds),
                         "docs/public-board-load.md:%d must state the %s s pace that %s:%d sets"
                         % (DOCUMENT_ROW, seconds, OWNER_SHOWN, line))


if __name__ == "__main__":
    unittest.main()
