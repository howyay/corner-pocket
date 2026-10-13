"""The note of a shot with no bracketing geometry has one owner.

The walk of round 106 found the sentence ``claim carries no bracketing geometry``
in two live producers and in no case:

  * ``src/eval_events.py`` built ``ShotEvidence`` with the sentence as a plain
    literal, for a claim that holds no ``from_mm``/``to_mm`` pair,
  * ``src/segment_calib_report.py`` built the same record with the same literal,
  * and ``grep -rn "bracketing geometry" tests/`` answered no line.

The drift was silent.  A reworded sentence in one producer left the other
producer on the old text, the console showed two notes for one state, and the
suite stayed green.

This module holds both producers to one owner,
``src/event_gates.NOTE_NO_BRACKETING_GEOMETRY``:

  * the value and the line of the owner, read from the imported module and from
    the text of the owner module,
  * every string literal of the two producers, read from the syntax tree, so a
    quoted spelling fails with ``path:line`` and the text of that line,
  * every ``note=`` keyword of the two producers, so both read the owner name,
  * and a walk over the .py files of ``src/`` and ``annotator/``, so no third
    module holds a literal copy of the sentence.

Not in this guard: ``src/eval_events.py`` also writes the note ``no video probe
available`` for a missing probe, and ``tests/test_event_gates.py`` pins that
other note.  It is a different fact, and it stays.

Run: ``./scripts/pool-test.sh python test_bracketing_note_owner``
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import event_gates  # noqa: E402

#: The owner module, as a path from the repository root.
OWNER = "src/event_gates.py"
#: The owner name, read from the imported module and from no copy of the text.
OWNER_NAME = "NOTE_NO_BRACKETING_GEOMETRY"
#: The sentence the owner holds.  A later round may reword it, and case 1
#: reports the move with the line of the owner.
NOTE = "claim carries no bracketing geometry"
#: The two modules that build ``ShotEvidence`` for a claim with no bracketing.
PRODUCERS = ("src/eval_events.py", "src/segment_calib_report.py")
#: Every spelling of the owner name this module accepts as a read of the owner.
OWNER_SPELLINGS = (OWNER_NAME, f"event_gates.{OWNER_NAME}",
                   f"src.event_gates.{OWNER_NAME}")
#: The keyword of a record display that carries the note.
NOTE_KEYWORD = "note"
#: The directories the home walk reads.
WALK_DIRS = ("src", "annotator")
#: The floor that fails a home walk which reads no file at all.
MIN_WALK_FILES = 250
#: The shape of the line that defines the owner in its module.
NAME_RE = re.compile(rf"^\s*{OWNER_NAME}\s*=")


def owner_note() -> str:
    """The value of the owner constant, read from the imported module.

    The module read is deliberate.  ``getattr`` answers the value of the module
    that is loaded now, so a guard that plants a new value in
    ``event_gates.NOTE_NO_BRACKETING_GEOMETRY`` is answered by that value.
    """
    value = getattr(event_gates, OWNER_NAME, None)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{OWNER}:{OWNER_NAME} is not a non-empty string: {value!r}")
    return value


def source_text(relative: str) -> str:
    """The text of one source file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one source file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(relative: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return f"{relative}:{line}: {text.strip()}  <- {why}"


def literal_note_sites(text: str, where: str) -> list:
    """Every string literal that holds the sentence, as (line, written, value).

    The walk reads the syntax tree, so a comment or a docstring that quotes the
    sentence is no site of it.  A part of an f-string is a literal too.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value == NOTE:
            found.append((node.lineno, ast.unparse(node), node.value))
    return sorted(found)


def literal_offences(relative: str, text: str) -> list:
    """Every report line for a quoted spelling of the sentence in one module."""
    lines = text.splitlines()
    return [report(relative, line, lines[line - 1],
                   f"{written} is a quoted spelling of the note; write {OWNER_NAME} "
                   f"of {OWNER} instead")
            for line, written, value in literal_note_sites(text, relative)]


def note_keyword_sites(text: str, where: str) -> list:
    """Every ``note=`` keyword of a call, as (line, written argument, value).

    The value is None when the argument is not a string literal, which is the
    shape of a read of the owner.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if not isinstance(node, ast.Call):
            continue
        for word in node.keywords:
            if word.arg != NOTE_KEYWORD:
                continue
            if isinstance(word.value, ast.Constant) and isinstance(word.value.value, str):
                found.append((word.value.lineno, ast.unparse(word.value), word.value.value))
            else:
                found.append((word.value.lineno, ast.unparse(word.value), None))
    return sorted(found)


def imported_owner_names(text: str, where: str) -> list:
    """Every local name one module imports from the owner module."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom) and node.module == "src.event_gates":
            for alias in node.names:
                if alias.name == OWNER_NAME:
                    found.append((node.lineno, alias.asname or alias.name))
    return sorted(found)


def defined_owner_names(text: str, where: str) -> list:
    """Every assignment that defines the owner name in one module."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == OWNER_NAME:
                found.append((node.lineno, target.id))
    return sorted(found)


def source_files() -> list:
    """The .py files of ``src/`` and ``annotator/``, as paths from the root."""
    found = []
    for base in WALK_DIRS:
        for path in sorted((ROOT / base).rglob("*.py")):
            if any(part == "__pycache__" or part.startswith(".") for part in path.parts):
                continue
            found.append(path.relative_to(ROOT).as_posix())
    return found


def literal_homes() -> list:
    """Every module of the source tree that holds the sentence as a literal."""
    return [offence for relative in source_files()
            for offence in literal_offences(relative, source_text(relative))]


class OwnerTests(unittest.TestCase):
    """The owner name, its value and the line of the module that holds it."""

    def test_the_owner_names_the_shipped_note(self):
        self.assertEqual(owner_note(), NOTE,
                         f"{OWNER}:{OWNER_NAME} moved; both producers must move with it")

    def test_the_owner_line_of_the_module_carries_the_shipped_note(self):
        """The line of the owner module that holds the value, with its number.

        This case pins the owner at ``path:line``.  The value the module answers
        and the value the text of the module shows must be one sentence, so a
        reader of the report can open that line and see the shipped note.
        """
        owner = owner_note()
        lines = source_lines(OWNER)
        sites = [(number, text) for number, text in enumerate(lines, start=1)
                 if NAME_RE.match(text)]
        self.assertEqual(1, len(sites),
                         f"{OWNER} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
        number, text = sites[0]
        self.assertIn(f'{OWNER_NAME} = "{owner}"', text,
                      report(OWNER, number, text,
                             f"the line does not assign {owner!r} to {OWNER_NAME}"))

    def test_the_owner_note_is_a_sentence_of_text(self):
        value = owner_note()
        self.assertEqual(value, value.strip(), f"{OWNER}:{OWNER_NAME} = {value!r}")
        self.assertTrue(value[:1].isalpha(), f"{OWNER}:{OWNER_NAME} = {value!r}")


class ProducerTests(unittest.TestCase):
    """Both producers read the owner, and neither holds a copy of it."""

    def test_every_producer_reads_the_owner_name(self):
        """The anti-vacuity case: the scan must find the note at the real sites.

        A scan that reads nothing passes the ban below.  This case holds each
        producer to one ``note=`` keyword that names the owner, and to one
        import of the owner name from the owner module.
        """
        for relative in PRODUCERS:
            text = source_text(relative)
            lines = source_lines(relative)
            owned = [(line, written) for line, written, value in note_keyword_sites(text, relative)
                     if written in OWNER_SPELLINGS]
            self.assertTrue(owned,
                            f"{relative} reads no {NOTE_KEYWORD}= keyword through "
                            f"{'/'.join(OWNER_SPELLINGS)}; the note of a claim with no "
                            f"bracketing geometry would leave its owner")
            for line, written in owned:
                self.assertTrue(any(spelling in lines[line - 1] for spelling in OWNER_SPELLINGS),
                                report(relative, line, lines[line - 1],
                                       f"the write does not reach the owner name {OWNER_NAME}"))
            bindings = imported_owner_names(text, relative)
            self.assertTrue(bindings,
                            f"{relative} imports no {OWNER_NAME} from {OWNER}")

    def test_no_producer_spells_the_note_as_a_literal(self):
        """A string that holds the sentence is a second home of the fact.

        The agreement case above holds each producer to the owner *name*.  A
        plain literal earns that case whenever its value equals the owner value
        today, and the same literal is a second home tomorrow: the owner moves,
        this string stays, and no case reads both.  So this case holds the
        sentence to the owner *name*.
        """
        offenders = []
        for relative in PRODUCERS:
            offenders.extend(literal_offences(relative, source_text(relative)))
        self.assertEqual([], offenders,
                         "a producer spells the note as a literal outside its "
                         "owner:\n" + "\n".join(offenders))

    def test_no_producer_holds_a_second_definition_of_the_owner_name(self):
        """A producer that defines the name answers its own copy, not the owner."""
        offenders = []
        for relative in PRODUCERS:
            for line, name in defined_owner_names(source_text(relative), relative):
                offenders.append(report(relative, line, source_lines(relative)[line - 1],
                                        f"the second definition of {name}; the owner is {OWNER}"))
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_scan_reports_a_planted_literal(self):
        """A planted literal is reported as ``path:line`` with the text of that line.

        The planted line holds the sentence and no name of the owner, so the
        detector holds the sentence and not a word of the owner.
        """
        planted = ("def probe(claim):\n"
                   "    return ShotEvidence(available=False,\n"
                   f'                        note="{NOTE}")\n')
        offenders = literal_offences("src/eval_events.py", planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("src/eval_events.py:3: "), offenders[0])
        self.assertIn(f'note="{NOTE}"', offenders[0])
        self.assertIn(OWNER_NAME, offenders[0])
        self.assertIn(OWNER, offenders[0])


class HomeWalkTests(unittest.TestCase):
    """One module of the source tree holds the sentence as a literal."""

    def test_the_walk_reads_the_source_tree(self):
        files = source_files()
        self.assertGreaterEqual(len(files), MIN_WALK_FILES,
                                f"the home walk read {len(files)} .py files")

    def test_the_note_has_one_live_home(self):
        """The owner line is the only literal of the sentence in the tree."""
        homes = literal_homes()
        self.assertEqual(1, len(homes),
                         "the sentence has more than one home:\n" + "\n".join(homes))
        lines = source_lines(OWNER)
        number = next(number for number, text in enumerate(lines, start=1) if NAME_RE.match(text))
        self.assertTrue(homes[0].startswith(f"{OWNER}:{number}: "),
                        f"the one home is not the owner line {OWNER}:{number}: {homes[0]}")

    def test_the_walk_reports_a_planted_second_home(self):
        """A second module with the literal is reported with its file and line."""
        planted = ("def probe(claim):\n"
                   f'    note = "{NOTE}"\n')
        offenders = literal_offences("src/motion_scan.py", planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("src/motion_scan.py:2: "), offenders[0])
        self.assertIn(NOTE, offenders[0])


if __name__ == "__main__":
    unittest.main()
