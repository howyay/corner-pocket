"""The name of the fixed-corners file has one owner.

The walk of round 108 found the basename ``fixed_corners.json`` in six live
modules and in one home:

  * ``src/calib_segments.py`` answers it as the ``file`` entry of
    ``CORNERS_SPEC``, the record that describes the artifact,
  * and five readers joined the same basename to an output directory of their
    own: ``src/eval_table_detect.py``, ``src/audit_calib.py``, ``src/quad_fit.py``,
    ``src/quad_fit_lines.py`` and ``src/calib_mapping_audit.py`` (two sites).

Only the tests wrote the file, so a renamed artifact was silent: a reader that
kept the old basename read a stale path and the suite stayed green.

This module holds every reader to one owner,
``src.calib_segments.CORNERS_SPEC["file"]``:

  * the entry and the line of the owner, read from the imported module and from
    the text of the owner module,
  * the line of every reader, so the report names the reader that spells the
    basename itself,
  * every string literal of a reader, read from the syntax tree, so a quoted
    spelling fails with ``path:line`` and the text of that line,
  * a walk over the .py files of the shipped packages, so no third module holds
    a literal copy of the basename,
  * and the value the shipped readers answer for the entry, so this owner name is
    the basename the readers open.

The owner is ``src/calib_segments.py`` because that module describes the
artifact: it holds the key, the table flag and the refresh cadence of the same
file.  The name belongs beside that record, and a reader holds no copy.

Run: ``./scripts/pool-test.sh python test_corners_spec_owner``

What this case does not see
--------------------------
* it reads the text of a string literal, not the value a name holds at run
  time.  The value case below closes that gap for the shipped readers;
* a document or a console script quotes the basename as prose.  Those files are
  no .py module of the shipped packages, so this walk does not read them;
* it does not run the detector.  Each reader joins the basename to its own
  output directory at import time, so the value case needs no frame.

Do not weaken a check to make a change pass.
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

from src import calib_segments  # noqa: E402

#: The owner module, as a path from the repository root.
OWNER = "src/calib_segments.py"
#: The owner name, read from the imported module and from no copy of the text.
OWNER_NAME = "CORNERS_SPEC"
#: The key of the entry that holds the basename.
OWNER_KEY = "file"
#: The basename the readers open.  Round 108 read it from the owner entry; a
#: later round may move it, and case 1 reports that move with its line.
BASENAME = "fixed_corners.json"
#: Every reader of the entry: its module and the line that joins the basename to
#: an output directory of its own.
READERS = (
    ("src/eval_table_detect.py", 79),
    ("src/audit_calib.py", 86),
    ("src/quad_fit.py", 154),
    ("src/quad_fit_lines.py", 214),
    ("src/calib_mapping_audit.py", 435),
    ("src/calib_mapping_audit.py", 606),
)
#: Every spelling of the owner name this module accepts as a read of the owner.
OWNER_SPELLINGS = (OWNER_NAME, f"calib_segments.{OWNER_NAME}")
#: The one home of the basename in the shipped tree, as ``relative:line``.
HOME = "src/calib_segments.py:182"
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


def entry_value() -> str:
    """The basename the owner answers for its ``file`` entry.

    The module read is deliberate.  The entry of the module that is loaded now
    answers, so a guard that plants a new entry is answered by that entry.
    """
    spec = getattr(calib_segments, OWNER_NAME, None)
    if not isinstance(spec, dict) or not isinstance(spec.get(OWNER_KEY), str) \
            or not spec[OWNER_KEY]:
        raise AssertionError(f"{OWNER}:{OWNER_NAME} holds no {OWNER_KEY!r} string: {spec!r}")
    return spec[OWNER_KEY]


def literal_basename_sites(text: str, where: str) -> list:
    """Every string literal that holds the basename, as (line, written).

    The walk reads the syntax tree, so a comment that quotes the basename is no
    site of it.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value == BASENAME:
            found.append((node.lineno, ast.unparse(node)))
    return sorted(found)


def literal_offences(relative: str, text: str) -> list:
    """Every report line for a quoted spelling of the basename in one module."""
    lines = text.splitlines()
    return [report(relative, line, lines[line - 1],
                   f"{written} is a quoted spelling of the basename; write "
                   f'{OWNER_NAME}["{OWNER_KEY}"] of {OWNER} instead')
            for line, written in literal_basename_sites(text, relative)]


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
    """Every module of the shipped tree that holds the basename as a literal."""
    return [offence for relative in source_files()
            for offence in literal_offences(relative, source_text(relative))]


class OwnerTests(unittest.TestCase):
    """The owner entry, its value and the line of the module that holds it."""

    def test_the_owner_answers_the_shipped_basename(self):
        sites = owner_sites()
        self.assertEqual(1, len(sites),
                         f"{OWNER} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
        number, text = sites[0]
        self.assertEqual(BASENAME, entry_value(),
                         report(OWNER, number, text,
                                f"{OWNER_NAME}[{OWNER_KEY!r}] moved away from the shipped "
                                f"basename {BASENAME!r}, which every reader opens"))

    def test_the_owner_line_of_the_module_carries_the_shipped_basename(self):
        """The line of the owner module that holds the value, with its number.

        This case pins the entry at ``path:line``.  The value the module answers
        and the value the text of the module shows must be one basename, so a
        reader of the report can open that line and see it.
        """
        number, text = owner_sites()[0]
        self.assertIn(f'"{OWNER_KEY}": "{entry_value()}"', text,
                      report(OWNER, number, text,
                             f"the line does not hold {entry_value()!r} under "
                             f"{OWNER_KEY!r}"))

    def test_the_owner_is_the_only_live_literal(self):
        """The owner line is the only literal of the basename in the tree."""
        homes = literal_homes()
        self.assertEqual(1, len(homes),
                         "the basename has more than one home:\n" + "\n".join(homes))
        self.assertTrue(homes[0].startswith(f"{HOME}: "),
                        f"the one home is not the owner entry {HOME}: {homes[0]}")

    def test_the_walk_reads_the_source_tree(self):
        files = source_files()
        self.assertGreaterEqual(len(files), MIN_WALK_FILES,
                                f"the home walk read {len(files)} .py files")

    def test_the_walk_reports_a_planted_second_home(self):
        """A second module with the literal is reported with its file and line."""
        planted = ("def probe(path):\n"
                   f'    return path / "out" / "{BASENAME}"\n')
        offenders = literal_offences(READERS[0][0], planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith(f"{READERS[0][0]}:2: "), offenders[0])
        self.assertIn(BASENAME, offenders[0])
        self.assertIn(OWNER_NAME, offenders[0])


class ReaderTests(unittest.TestCase):
    """Every reader reads the owner entry, and it holds no copy of the basename."""

    def test_every_reader_reads_the_owner_name(self):
        """The anti-vacuity case: each line must name the owner entry.

        A line that joins a literal, and a line that joins the entry, satisfy
        the ban below in the same way.  This case holds every reader line to the
        owner name, so the ban has a real site to protect.
        """
        offenders = []
        for relative, number in READERS:
            text = source_lines(relative)[number - 1]
            if f'{OWNER_NAME}["{OWNER_KEY}"]' not in text:
                offenders.append(report(relative, number, text,
                                        f"the line does not read "
                                        f'{OWNER_NAME}["{OWNER_KEY}"] of {OWNER}'))
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_every_reader_line_is_the_line_this_module_pins(self):
        """The pinned line numbers, so a moved reader fails here and not in silence."""
        moved = [f"{relative}:{number} should be "
                 f"{number}: {source_lines(relative)[number - 1].strip()}"
                 for relative, number in READERS
                 if OWNER_NAME not in source_lines(relative)[number - 1]]
        self.assertEqual([], moved, "\n".join(moved))

    def test_no_reader_spells_the_basename_as_a_literal(self):
        """A string that holds the basename is a second home of the fact.

        The agreement case above holds each reader to the owner *name*.  A plain
        literal earns that case whenever its value equals the owner value today,
        and the same literal is a second home tomorrow: the owner moves, this
        string stays, and no case reads both.  So this case holds the basename
        to the owner *name*.
        """
        offenders = [offence for relative, _ in READERS
                     for offence in literal_offences(relative, source_text(relative))]
        self.assertEqual([], offenders,
                         "a reader spells the basename as a literal outside its "
                         "owner:\n" + "\n".join(offenders))

    def test_a_planted_literal_in_a_reader_is_reported(self):
        """A planted literal is reported as ``path:line`` with the text of that line."""
        planted = ("def probe(root):\n"
                   f'    return root / "out" / "{BASENAME}"\n')
        offenders = literal_offences(READERS[2][0], planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith(f"{READERS[2][0]}:2: "), offenders[0])
        self.assertIn(f'"{BASENAME}"', offenders[0])
        self.assertIn(OWNER_NAME, offenders[0])


class AnswerTests(unittest.TestCase):
    """The shipped readers answer one basename for the owner entry."""

    def test_the_detector_module_answers_the_owner_basename(self):
        """The shipped import of ``src.eval_table_detect`` holds the joined path."""
        from src import eval_table_detect

        number, text = owner_sites()[0]
        self.assertEqual(entry_value(), eval_table_detect.FIXED_CORNERS.name,
                         report(OWNER, number, text,
                                f"src/eval_table_detect.py joined {entry_value()!r} to its "
                                f"output directory and answered "
                                f"{eval_table_detect.FIXED_CORNERS.name!r}"))

    def test_every_reader_module_imports_the_owner(self):
        """The shipped import of each reader must not raise and must see one owner."""
        import importlib

        for relative, _ in READERS:
            module = relative[:-3].replace("/", ".")
            loaded = importlib.import_module(module)
            self.assertIs(calib_segments, getattr(loaded, "calib_segments", calib_segments),
                          f"{module} imports another module named calib_segments")


if __name__ == "__main__":
    unittest.main()
