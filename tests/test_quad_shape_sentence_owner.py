"""The refusal of a quad of the wrong shape has one owner.

The walk of round 108 found the sentence ``expected a 4x2 quad, got `` in three
live sites and in one home:

  * ``src/calib_segments.py`` answers it as ``QUAD_SHAPE_ERROR``, and its two
    raises of ``parse_quad`` append the shape they received,
  * and ``src/motion_scan.py`` read the same words for the dict that
    ``load_quad`` answers for a frame whose quad has the wrong shape.

Two raises of one module are one fact.  A reworded sentence in one raise left
the other raise and the reader on the old text, and the suite stayed green.

This module holds every raise to one owner,
``src.calib_segments.QUAD_SHAPE_ERROR``:

  * the value and the line of the owner, read from the imported module and from
    the text of the owner module,
  * the line of every raise and of the reader, so the report names the site that
    spells the sentence itself,
  * every string literal of a site, read from the syntax tree, so a quoted
    spelling fails with ``path:line`` and the text of that line,
  * a walk over the .py files of the shipped packages, so no third module holds
    a literal copy of the sentence,
  * and the message of the shipped raise, so this owner name is the text the
    caller reads.

The owner is ``src/calib_segments.py`` because that module owns ``parse_quad``,
the one function that refuses a quad of the wrong shape.  The wording belongs
beside that function, and a caller holds no copy.

Round 108 held one exception while it ran: ``src/motion_scan.py`` held the same
literal, and another writer owned that file.  That writer has since made the
reader take the owner name, so the exception is closed.  The walk below reads
the reader as well, and a quoted spelling returns as ``path:line``.

Run: ``./scripts/pool-test.sh python test_quad_shape_sentence_owner``

What this case does not see
--------------------------
* it reads the text of a string literal, not the value a name holds at run
  time.  The message case below closes that gap for the shipped raise;
* a document or a console script quotes the sentence as prose.  Those files are
  no .py module of the shipped packages, so this walk does not read them;
* it does not run the detector.  ``parse_quad`` refuses a shape before any frame
  is read, so the message case needs no frame.

Do not weaken a check to make a change pass.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import calib_segments  # noqa: E402

#: The owner module, as a path from the repository root.
OWNER = "src/calib_segments.py"
#: The owner name, read from the imported module and from no copy of the text.
OWNER_NAME = "QUAD_SHAPE_ERROR"
#: The refusal the owner holds.  The console and the served documents carry it,
#: so a later round may move it, and case 1 reports that move with its line.
SENTENCE = "expected a 4x2 quad, got "
#: Every raise of the owner module that refuses a quad of the wrong shape: its
#: module and its line.  Both raises read the owner name.
OWNER_SITES = (
    ("src/calib_segments.py", 555),
    ("src/calib_segments.py", 559),
)
#: The module of the round-108 exception.  Another writer owns it, so this
#: module reads its literal from the tree and holds no copy of its line.
READER = "src/motion_scan.py"
#: The reader site the walk accepts, as a path alone: the first string literal of
#: the reader.  The line number comes from the tree, because that file changes
#: this round.
READER_SITE = "src/motion_scan.py"
#: The one home of the sentence in the shipped tree, as ``relative:line``.
HOME = "src/calib_segments.py:369"
#: The shape ``read`` receives in the message cases: a value that cannot become
#: an (n, 2) array, and a value that holds three points.  Each case names the
#: shape text the raise appends.
WRONG_SCALAR = 5
WRONG_SHAPE = [[0, 0], [1, 1], [2, 2]]
SHAPE_TEXTS = ("()", "(3, 2)")
#: The shipped packages the home walk reads.
WALK_DIRS = ("src", "annotator", "tools", "scripts")
#: The floor that fails a home walk which reads no file at all.
MIN_WALK_FILES = 250
#: The shape of the line that defines the owner in its module.
NAME_RE = re.compile(rf"^\s*{OWNER_NAME}\s*=")


def source_text(relative: str) -> str:
    """The text of one source file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one source file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(relative: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return f"{relative}:{line}: {text.strip()}  <- {why}"


def owner_sites() -> list:
    """Every line of the owner module that defines the owner name."""
    return [(number, text) for number, text in enumerate(source_lines(OWNER), start=1)
            if NAME_RE.match(text)]


def owner_sentence() -> str:
    """The refusal the owner answers, read from the imported module.

    The module read is deliberate.  ``getattr`` answers the value of the module
    that is loaded now, so a guard that plants a new value in
    ``calib_segments.QUAD_SHAPE_ERROR`` is answered by that value.
    """
    value = getattr(calib_segments, OWNER_NAME, None)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{OWNER}:{OWNER_NAME} is not a non-empty string: {value!r}")
    return value


def sentence_literal_sites(text: str, where: str) -> list:
    """Every string literal that holds the sentence, as (line, written, value).

    The walk reads the syntax tree, so a comment that quotes the sentence is no
    site of it.  A part of an f-string is a literal too.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value == SENTENCE:
            found.append((node.lineno, ast.unparse(node), node.value))
    return sorted(found)


def literal_offences(relative: str, text: str) -> list:
    """Every report line for a quoted spelling of the sentence in one module."""
    lines = text.splitlines()
    return [report(relative, line, lines[line - 1],
                   f"{written} is a quoted spelling of the refusal; write {OWNER_NAME} "
                   f"of {OWNER} instead")
            for line, written, value in sentence_literal_sites(text, relative)]


def source_files() -> list:
    """The .py files of the shipped packages, as paths from the root."""
    found = []
    for base in WALK_DIRS:
        for path in sorted((ROOT / base).rglob("*.py")):
            if any(part == "__pycache__" or part.startswith(".") for part in path.parts):
                continue
            found.append(path.relative_to(ROOT).as_posix())
    return found


def literal_homes() -> list:
    """Every module of the shipped tree that holds the sentence as a literal."""
    return [offence for relative in source_files()
            for offence in literal_offences(relative, source_text(relative))]


def accepted_homes() -> dict:
    """The ``relative:line`` sites of the sentence this round accepts, with why.

    The home of the owner, and every literal of the reader of the round-108
    exception.  The reader line comes from the tree: another writer owns that
    file, so a pinned line of it would go stale in this module and not in that
    file.  A third home is no accepted site and fails case 5.
    """
    accepted = {HOME: "the owner of the fact"}
    for number, written, value in sentence_literal_sites(source_text(READER), READER):
        accepted[f"{READER}:{number}"] = ("the reader of the round-108 exception, "
                                          "which another writer owns")
    return accepted


class OwnerTests(unittest.TestCase):
    """The owner name, its value and the line of the module that holds it."""

    def test_the_owner_answers_the_shipped_refusal(self):
        sites = owner_sites()
        self.assertEqual(1, len(sites),
                         f"{OWNER} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
        number, text = sites[0]
        self.assertEqual(SENTENCE, owner_sentence(),
                         report(OWNER, number, text,
                                f"{OWNER_NAME} moved away from the shipped refusal "
                                f"{SENTENCE!r}, which the raises and the reader carry"))

    def test_the_owner_line_of_the_module_carries_the_shipped_refusal(self):
        """The line of the owner module that holds the value, with its number.

        This case pins the owner at ``path:line``.  The value the module
        answers and the value the text of the module shows must be one sentence,
        so a reader of the report can open that line and see it.
        """
        number, text = owner_sites()[0]
        self.assertIn(f'{OWNER_NAME} = "{owner_sentence()}"', text,
                      report(OWNER, number, text,
                             f"the line does not assign {owner_sentence()!r} to "
                             f"{OWNER_NAME}"))

    def test_the_owner_line_is_the_home_this_module_pins(self):
        """The home line number, so a moved owner fails here and not in silence."""
        number = owner_sites()[0][0]
        self.assertEqual(HOME, f"{OWNER}:{number}",
                         report(OWNER, number, source_lines(OWNER)[number - 1],
                                f"the owner moved to {OWNER}:{number}; update HOME"))


class SiteTests(unittest.TestCase):
    """Every site refuses the shape through the owner name."""

    def test_the_owner_raises_read_the_owner_name(self):
        """The anti-vacuity case: both raises of the owner must name the owner.

        A line that holds the literal, and a line that reads the name, satisfy
        the ban below in the same way.  This case holds the two raises to the
        name, so the ban has a real site to protect.
        """
        offenders = []
        for relative, number in OWNER_SITES:
            text = source_lines(relative)[number - 1]
            if OWNER_NAME not in text:
                offenders.append(report(relative, number, text,
                                        f"the line does not read {OWNER_NAME} of {OWNER}"))
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_no_owner_raise_spells_the_refusal_as_a_literal(self):
        """A string that holds the sentence is a second home of the fact.

        The agreement case above holds each raise to the owner *name*.  A plain
        literal earns that case whenever its value equals the owner value today,
        and the same literal is a second home tomorrow: the owner moves, this
        string stays, and no case reads both.  So this case holds the sentence
        to the owner *name*.
        """
        sites = sorted({relative for relative, _ in OWNER_SITES} | {READER})
        offenders = [offence for relative in sites
                     for offence in literal_offences(relative, source_text(relative))]
        accepted = [offence for offence in offenders
                    if offence.split(": ")[0] != READER
                    and offence.split(": ")[0] not in accepted_homes()]
        self.assertEqual([], accepted,
                         "a site spells the refusal as a literal outside its owner "
                         f"{accepted_homes()}:\n" + "\n".join(offenders))

    def test_the_reader_takes_the_owner_name(self):
        """The reader reads the owner name, so no second spelling stands there.

        Round 108 held this case as a tripwire while another writer owned
        ``src/motion_scan.py``.  That writer has since made the reader take the
        name, so the case holds the closed state: a quoted spelling returns here
        with its ``path:line`` and the text of that line.
        """
        offenders = literal_offences(READER, source_text(READER))
        self.assertEqual(0, len(offenders),
                         f"{READER} holds {len(offenders)} literals of the sentence; "
                         f"the reader must read {OWNER_NAME} of {OWNER}:\n"
                         + "\n".join(offenders))
        readers = [number for number, line in enumerate(source_text(READER).splitlines(), 1)
                   if OWNER_NAME in line]
        self.assertEqual(1, len(readers),
                         f"{READER} must read {OWNER_NAME} at one site, not at {readers}")

    def test_a_planted_literal_is_reported(self):
        """A planted literal is reported as ``path:line`` with the text of that line."""
        planted = ("def probe(value):\n"
                   "    if value is None:\n"
                   f'        raise ValueError("{SENTENCE}" + str(value))\n')
        offenders = literal_offences(READER, planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith(f"{READER}:3: "), offenders[0])
        self.assertIn(f'"{SENTENCE}"', offenders[0])
        self.assertIn(OWNER_NAME, offenders[0])


class HomeWalkTests(unittest.TestCase):
    """One module of the shipped tree holds the sentence as a literal."""

    def test_the_walk_reads_the_source_tree(self):
        files = source_files()
        self.assertGreaterEqual(len(files), MIN_WALK_FILES,
                                f"the home walk read {len(files)} .py files")

    def test_the_refusal_has_one_home_and_one_reader(self):
        """The owner line and the reader of the other writer are the only homes."""
        homes = literal_homes()
        self.assertTrue(homes, f"no .py file of the tree holds {SENTENCE!r}")
        accepted = accepted_homes()
        strangers = [offence for offence in homes
                     if offence.split(": ")[0] not in accepted]
        self.assertEqual([], strangers,
                         "the refusal has a third home beyond the owner and the "
                         f"round-108 reader {READER}:\n" + "\n".join(homes))
        numbers = [offence.split(": ")[0] for offence in homes]
        self.assertIn(HOME, numbers,
                      f"the home {HOME} holds no literal of the refusal: {homes}")

    def test_the_walk_reports_a_planted_second_home(self):
        """A second module with the literal is reported with its file and line."""
        planted = ("def probe(value):\n"
                   f'    return "{SENTENCE}" + str(value)\n')
        offenders = literal_offences(READER, planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith(f"{READER}:2: "), offenders[0])
        self.assertIn(SENTENCE, offenders[0])


class MessageTests(unittest.TestCase):
    """The shipped raises answer the owner sentence."""

    def read_message(self, value) -> str:
        """The message ``read`` raises, in strict mode, for one corners value."""
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "probe.json"
            path.write_text(json.dumps({"corners": value}), encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                calib_segments.read(path, strict=True)
        return str(caught.exception)

    def test_the_shipped_raise_answers_the_owner_sentence(self):
        """Both raises carry the owner sentence and the shape they received.

        The first raise answers a value that cannot become an (n, 2) array, the
        second a value of fewer than four points.  The two messages must share
        one wording, and that wording is the owner.
        """
        number, text = owner_sites()[0]
        cases = ((WRONG_SCALAR, SHAPE_TEXTS[0]), (WRONG_SHAPE, SHAPE_TEXTS[1]))
        for value, shape in cases:
            message = self.read_message(value)
            self.assertEqual(f"{owner_sentence()}{shape}", message,
                             report(OWNER, number, text,
                                    f"the raise answered {message!r}, not "
                                    f"{owner_sentence() + shape!r}"))


if __name__ == "__main__":
    unittest.main()
