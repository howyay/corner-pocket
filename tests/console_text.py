"""The console text that repeats a refusal sentence: one row per exception, one home.

Two test modules used to state the same two facts in three containers:

* ``tests/test_refusal_identity.py`` held two containers,
  ``CONSOLE_WORDS_THAT_REPEAT_A_REFUSAL`` and
  ``CONSOLE_SENTENCES_THAT_CONTAIN_A_REFUSAL``.
* ``tests/test_job_refusal_identity.py`` held one container, ``ALLOWED_CONSOLE_HINTS``.

The two facts are these:

* the console word pair ``placeholderName`` of ``annotator/ops.js`` repeats a refusal
  sentence, because the enroll form shows that sentence for a bye placeholder;
* the longer line of ``annotator/app.js`` contains the words of the refusal sentence
  ``JPEG encoding failed``, and that line is the message of the live panel.

Each fact is a decision about a javascript file that a scan finds.  A fact that three
containers state can disagree with itself.  This module owns the facts.  It holds one
row per exception, and the two test modules read the rows through the derived views
below.  Neither test module holds a literal of either fact, and one case in
``tests/test_refusal_identity.py`` fails when a test module declares one of the three
names again.  One case here states the record of the move: the three derived views
equal the literals the two test modules held at 7a5021a.  That record must live beside
the rows, because a test module may not hold those literals again.

This is the form ``tests/dom_stubs.js`` uses for the javascript doubles and the form
``tests/dataset_id_cases.py`` uses for the dataset cases: a sibling module owns the
data, and a test module imports it.
"""
import unittest
from typing import NamedTuple

from annotator import refusals

# The one module that may declare the names below.
OWNER = 'console_text.py'

# The three container names the two test modules used before this module owned the facts.
DECLARATIONS = ('CONSOLE_WORDS_THAT_REPEAT_A_REFUSAL', 'CONSOLE_SENTENCES_THAT_CONTAIN_A_REFUSAL',
                'ALLOWED_CONSOLE_HINTS')

# The console word pair of annotator/ops.js:10.  That pair repeats the Chinese sentence of the
# refusal row "A bye is added by the draw; type the guest's real name".  The console shows the
# pair for its own form check, so the pair stays.  A new copy of a refusal sentence in
# javascript fails the scan in tests/test_refusal_identity.py.
OPS_WORDS_FILE = 'annotator/ops.js'
OPS_WORD_KEY = 'placeholderName'
OPS_WORDS_TEXT = '轮空由抽签自动安排，请输入访客的真实姓名。'
OPS_REFUSAL_SENTENCE = "A bye is added by the draw; type the guest's real name"

# annotator/app.js:2046, the message of the live panel.  That longer line contains the words of
# the refusal row 'JPEG encoding failed'.  The line has its own purpose and its own longer text,
# so the line stays.  A pair is (file, sentence): the scan in tests/test_refusal_identity.py is a
# plain substring search, so a new copy of a refusal sentence in javascript still fails it.
APP_LINE_FILE = 'annotator/app.js'
APP_LINE_TEXT = 'JPEG encoding failed'


class ConsoleException(NamedTuple):
    """One javascript text that repeats a refusal sentence on purpose.

    file    the javascript file a scan reads, as a path from the repository root
    text    the text the scan finds in that file
    word    the console word key of the pair, or None when the text is a line
    refusal the refusal sentence the text repeats
    """
    file: str
    text: str
    word: str | None
    refusal: str


# One row per exception.  A new exception is a new row here, and nothing else.
CONSOLE_EXCEPTION_ROWS = (
    ConsoleException(OPS_WORDS_FILE, OPS_WORDS_TEXT, OPS_WORD_KEY, OPS_REFUSAL_SENTENCE),
    ConsoleException(APP_LINE_FILE, APP_LINE_TEXT, None, APP_LINE_TEXT),
)

# The two texts the scan may find in a javascript file, one per fact.
CONSOLE_EXCEPTION_TEXTS = tuple(row.text for row in CONSOLE_EXCEPTION_ROWS)


def word_pair_rows():
    """The rows whose text is a console word pair, in row order."""
    return tuple(row for row in CONSOLE_EXCEPTION_ROWS if row.word)


def line_rows():
    """The rows whose text is a longer line, in row order."""
    return tuple(row for row in CONSOLE_EXCEPTION_ROWS if not row.word)


def words_that_repeat_a_refusal():
    """{file: {word key: the Chinese sentence the pair shows}} for the word pairs.

    The words of the pair and the refusal sentence are one string: the row names that
    fact once, and the scan of the javascript files reads this view.
    """
    held = {}
    for row in word_pair_rows():
        held.setdefault(row.file, {})[row.word] = row.text
    return held


def sentences_that_contain_a_refusal():
    """{(file, sentence)} for the longer lines: the pairs the substring scan skips."""
    return {(row.file, row.refusal) for row in line_rows()}


def allowed_console_hints():
    """{file: {text the scan finds}} for every row: the whole allow list of the scan.

    Both facts are here, and the refusal sentence is the lookup key of the row: a
    rewording of either fact fails here, and it cannot pass by accident.
    """
    held = {}
    for row in CONSOLE_EXCEPTION_ROWS:
        # A row whose sentence has no row in annotator/refusals.py would KeyError here.
        # That is the wanted failure: the fact this module states must stay a fact.
        assert row.refusal in refusals.REFUSALS, f'no refusal row names {row.refusal!r}'
        held.setdefault(row.file, set()).add(row.text)
    return held


class ConsoleExceptionFactsTest(unittest.TestCase):
    def test_the_views_are_the_values_the_two_modules_held_at_7a5021a(self):
        """The derived views equal the literals the two test modules held before the move.

        The values below are the literals of ``tests/test_refusal_identity.py`` and
        ``tests/test_job_refusal_identity.py`` at 7a5021a: the word pair the first module held,
        the pair set the first module held, and the allow list the second module held.  They are
        written here as literals, in the record of the move, so a row that changes shows up as a
        diff in this case.  The two test modules cannot hold this record: this case fails when
        either one states one of those literals again.
        """
        self.assertEqual(2, len(CONSOLE_EXCEPTION_ROWS),
                         'the console exceptions are no longer the two this round moved')
        self.assertEqual({'annotator/ops.js': {'placeholderName': '轮空由抽签自动安排，请输入访客的真实姓名。'}},
                         words_that_repeat_a_refusal(),
                         'the console word pair that repeats a refusal sentence changed')
        self.assertEqual({('annotator/app.js', 'JPEG encoding failed')},
                         sentences_that_contain_a_refusal(),
                         'the console line that contains a refusal sentence changed')
        self.assertEqual({'annotator/ops.js': {'轮空由抽签自动安排，请输入访客的真实姓名。'},
                          'annotator/app.js': {'JPEG encoding failed'}},
                         allowed_console_hints(),
                         'the two facts the scan allows no longer match what this round moved')


if __name__ == '__main__':
    unittest.main()
