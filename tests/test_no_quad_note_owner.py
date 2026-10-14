"""The note of a frame with no verified quad has one owner.

The walk of round 107 found the sentence ``no quad found`` in two live modules
and in no case:

  * ``src/calib_segments.py`` answered it as the ``note`` of the ``Reference``
    that ``resolve`` writes when no step of the chain holds a quad,
  * ``src/motion_scan.py`` wrote the same sentence into the dict that
    ``load_quad`` answers for the same state,
  * and ``git grep -F 'no quad found' -- tests/`` answered no line.

The drift was silent.  A reworded sentence in the resolver left the reader on
the old text, the console showed two notes for one state, and the suite stayed
green.

This module holds the reader to one owner,
``src.calib_segments.NOTE_NO_QUAD``:

  * the value and the line of the owner, read from the imported module and from
    the text of the owner module,
  * every string literal of the reader, read from the syntax tree, so a quoted
    spelling fails with ``path:line`` and the text of that line,
  * the ``note`` entry of every dict literal of the reader, so the reader
    spells the owner name and not its own copy of the words,
  * a walk over the .py files of the shipped packages, so no third module
    holds a literal copy of the sentence,
  * and the answer of the shipped resolver and of the shipped reader on a root
    with no artifact, so this owner name is the note the console receives.

The owner is ``src/calib_segments.py`` because that module owns the
``Reference`` type and its ``note`` field.  The value belongs beside the record
that carries it, and the reader holds no copy.

Run: ``./scripts/pool-test.sh python test_no_quad_note_owner``

What this case does not see
---------------------------
* it reads the text of a string literal, not the value a name holds at run
  time.  The two answer cases below close that gap for the shipped reader;
* a document or a console script quotes the sentence as prose.  Those files are
  no .py module of the shipped packages, so this walk does not read them;
* it does not run the detector.  A frame with no quad takes one branch whether
  a video is present or not, so the answer cases need no frame.

Do not weaken a check to make a change pass.
"""
from __future__ import annotations

import ast
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
OWNER_NAME = "NOTE_NO_QUAD"
#: The sentence the owner holds.  The console and the served documents carry it,
#: so a later round may move it, and case 1 reports that move with its line.
NOTE = "no quad found"
#: The one module that answers the note for a frame with no quad.
READER = "src/motion_scan.py"
#: Every spelling of the owner name this module accepts as a read of the owner.
OWNER_SPELLINGS = (OWNER_NAME, f"calib_segments.{OWNER_NAME}",
                   f"src.calib_segments.{OWNER_NAME}")
#: The key of a record that carries the note.
NOTE_KEY = "note"
#: The dataset the answer cases ask for.  The root holds no artifact, so the
#: chain finds no quad and the note of that state answers.
DATASET = "vod30"
#: The shipped packages the home walk reads.
WALK_DIRS = ("src", "annotator", "tools", "scripts")
#: The floor that fails a home walk which reads no file at all.
MIN_WALK_FILES = 250
#: The shape of the line that defines the owner in its module.
NAME_RE = re.compile(rf"^\s*{OWNER_NAME}\s*=")


def owner_note() -> str:
    """The value of the owner constant, read from the imported module.

    The module read is deliberate.  ``getattr`` answers the value of the module
    that is loaded now, so a guard that plants a new value in
    ``calib_segments.NOTE_NO_QUAD`` is answered by that value.
    """
    value = getattr(calib_segments, OWNER_NAME, None)
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


def owner_sites() -> list:
    """Every line of the owner module that defines the owner name."""
    return [(number, text) for number, text in enumerate(source_lines(OWNER), start=1)
            if NAME_RE.match(text)]


def literal_note_sites(text: str, where: str) -> list:
    """Every string literal that holds the sentence, as (line, written, value).

    The walk reads the syntax tree, so a comment that quotes the sentence is no
    site of it.  A part of an f-string is a literal too.
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


def note_entries(text: str, where: str) -> list:
    """Every ``note`` value of a dict literal or of a call, as (line, written).

    The value is None when the entry is not a string literal, which is the
    shape of a read of the owner.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == NOTE_KEY:
                    found.append((value.lineno, ast.unparse(value)))
        elif isinstance(node, ast.Call):
            for word in node.keywords:
                if word.arg == NOTE_KEY:
                    found.append((word.value.lineno, ast.unparse(word.value)))
    return sorted(found)


def imported_owner_lines(text: str, where: str) -> list:
    """Every line of one module that imports the owner module or its name."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "src.calib_segments" \
                    or (module == "src" and any(a.name == "calib_segments"
                                                for a in node.names)):
                found.append(node.lineno)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.calib_segments":
                    found.append(node.lineno)
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


class OwnerTests(unittest.TestCase):
    """The owner name, its value and the line of the module that holds it."""

    def test_the_owner_names_the_shipped_note(self):
        number, text = owner_sites()[0]
        self.assertEqual(NOTE, owner_note(),
                         report(OWNER, number, text,
                                f"{OWNER_NAME} moved away from the shipped note "
                                f"{NOTE!r}, which the console and the served "
                                f"documents carry"))

    def test_the_owner_line_of_the_module_carries_the_shipped_note(self):
        """The line of the owner module that holds the value, with its number.

        This case pins the owner at ``path:line``.  The value the module
        answers and the value the text of the module shows must be one
        sentence, so a reader of the report can open that line and see the
        shipped note.
        """
        sites = owner_sites()
        self.assertEqual(1, len(sites),
                         f"{OWNER} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
        number, text = sites[0]
        self.assertIn(f'{OWNER_NAME} = "{owner_note()}"', text,
                      report(OWNER, number, text,
                             f"the line does not assign {owner_note()!r} to {OWNER_NAME}"))

    def test_the_owner_defines_the_name_once(self):
        """A second definition in the owner would answer its own value."""
        offenders = [report(OWNER, line, source_lines(OWNER)[line - 1],
                            f"the second definition of {name}")
                     for line, name in defined_owner_names(source_text(OWNER), OWNER)[1:]]
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_owner_note_is_a_sentence_of_text(self):
        value = owner_note()
        self.assertEqual(value, value.strip(), f"{OWNER}:{OWNER_NAME} = {value!r}")
        self.assertTrue(value[:1].isalpha(), f"{OWNER}:{OWNER_NAME} = {value!r}")


class ReaderTests(unittest.TestCase):
    """The reader reads the owner, and it holds no copy of the note."""

    def test_the_reader_reads_the_owner_name(self):
        """The anti-vacuity case: the scan must find the note at the real site.

        A scan that reads nothing passes the ban below.  This case holds the
        reader to one ``note`` entry that names the owner, and to one import of
        the owner module.
        """
        text = source_text(READER)
        lines = source_lines(READER)
        owned = [(line, written) for line, written in note_entries(text, READER)
                 if any(spelling in written for spelling in OWNER_SPELLINGS)]
        self.assertTrue(owned,
                        f"{READER} reads no {NOTE_KEY!r} entry through "
                        f"{'/'.join(OWNER_SPELLINGS)}; the note of a frame with no "
                        f"verified quad would leave its owner")
        for line, written in owned:
            self.assertTrue(any(spelling in lines[line - 1] for spelling in OWNER_SPELLINGS),
                            report(READER, line, lines[line - 1],
                                   f"the write does not reach the owner name {OWNER_NAME}"))
        bindings = imported_owner_lines(text, READER)
        self.assertTrue(bindings,
                        f"{READER} imports no {OWNER_NAME} and no {OWNER}")

    def test_no_reader_spells_the_note_as_a_literal(self):
        """A string that holds the sentence is a second home of the fact.

        The agreement case above holds the reader to the owner *name*.  A plain
        literal earns that case whenever its value equals the owner value
        today, and the same literal is a second home tomorrow: the owner moves,
        this string stays, and no case reads both.  So this case holds the
        sentence to the owner *name*.
        """
        offenders = literal_offences(READER, source_text(READER))
        self.assertEqual([], offenders,
                         "the reader spells the note as a literal outside its "
                         "owner:\n" + "\n".join(offenders))

    def test_no_reader_holds_a_second_definition_of_the_owner_name(self):
        """A reader that defines the name answers its own copy, not the owner."""
        offenders = [report(READER, line, source_lines(READER)[line - 1],
                            f"the second definition of {name}; the owner is {OWNER}")
                     for line, name in defined_owner_names(source_text(READER), READER)]
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_scan_reports_a_planted_literal(self):
        """A planted literal is reported as ``path:line`` with the text of that line.

        The planted line holds the sentence and no name of the owner, so the
        detector holds the sentence and not a word of the owner.
        """
        planted = ("def probe(frame):\n"
                   "    if not frame:\n"
                   f'        return {{"{NOTE_KEY}": "{NOTE}", "verified": False}}\n')
        offenders = literal_offences(READER, planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith(f"{READER}:3: "), offenders[0])
        self.assertIn(f'"{NOTE}"', offenders[0])
        self.assertIn(OWNER_NAME, offenders[0])
        self.assertIn(OWNER, offenders[0])

    def test_the_reader_answers_the_owner_note_for_a_frame_with_no_quad(self):
        """The shipped reader, run on a root with no artifact, answers the owner.

        The other cases read the text.  This case runs the real call chain and
        holds the answer to the owner name, so a value that moves at run time
        fails here as well.
        """
        from src import motion_scan

        with tempfile.TemporaryDirectory() as root:
            answer = motion_scan.load_quad(DATASET, root=root)
        number, text = owner_sites()[0]
        self.assertEqual(NOTE, answer.get(NOTE_KEY),
                         report(OWNER, number, text,
                                f"the reader answered {answer.get(NOTE_KEY)!r} for a "
                                f"frame with no quad, not {OWNER_NAME}"))
        self.assertFalse(answer.get("verified"), answer)
        self.assertIsNone(answer.get("quad_px"), answer)


class HomeWalkTests(unittest.TestCase):
    """One module of the shipped tree holds the sentence as a literal."""

    def test_the_walk_reads_the_source_tree(self):
        files = source_files()
        self.assertGreaterEqual(len(files), MIN_WALK_FILES,
                                f"the home walk read {len(files)} .py files")

    def test_the_note_has_one_live_home(self):
        """The owner line is the only literal of the sentence in the tree."""
        homes = literal_homes()
        self.assertEqual(1, len(homes),
                         "the sentence has more than one home:\n" + "\n".join(homes))
        number = owner_sites()[0][0]
        self.assertTrue(homes[0].startswith(f"{OWNER}:{number}: "),
                        f"the one home is not the owner line {OWNER}:{number}: {homes[0]}")

    def test_the_walk_reports_a_planted_second_home(self):
        """A second module with the literal is reported with its file and line."""
        planted = ("def probe(frame):\n"
                   f'    note = "{NOTE}"\n')
        offenders = literal_offences(READER, planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith(f"{READER}:2: "), offenders[0])
        self.assertIn(NOTE, offenders[0])


class ResolveTests(unittest.TestCase):
    """The shipped resolver answers the owner note for the same state."""

    def test_the_resolver_answers_the_owner_note(self):
        with tempfile.TemporaryDirectory() as root:
            reference = calib_segments.resolve(DATASET, root=root)
        number, text = owner_sites()[0]
        self.assertFalse(reference.found, reference)
        self.assertEqual(NOTE, reference.note,
                         report(OWNER, number, text,
                                f"the resolver answered {reference.note!r} for a frame "
                                f"with no quad, not {OWNER_NAME}"))


if __name__ == "__main__":
    unittest.main()
