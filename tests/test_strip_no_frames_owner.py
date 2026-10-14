"""The operator sentence ``no frames for the strip`` has one home.

Round 106, writer W2.  The walk found the sentence of the strip reader in two
live copies, and each copy raised it as an ``OSError``:

  * ``src/motion_scan.py:1584`` -- the strip renderer of that module, and
  * ``src/track_before_detect.py:482`` -- the strip renderer of that module.

The bodies around the sentence are the same body.  A rename at one site would
leave the other site with another message, and no case under ``tests/`` named
the sentence at all.

The home is ``src/motion_scan.py:220``::

    NO_FRAMES_FOR_THE_STRIP = "no frames for the strip"

The rule of this module:

  * the owner module keeps one spelling of the sentence, on the home line;
  * each raise site names the home, and holds no spelling of the sentence;
  * ``src/track_before_detect.py`` reads the home through the module alias that
    it imports at ``:47``, so the read adds no import and no cycle;
  * no other file of ``src/`` or ``annotator/`` spells the sentence.

The walk reports every offender as ``path:line: <the line text>``.

Run: ``./scripts/pool-test.sh python test_strip_no_frames_owner``
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

from src import motion_scan  # noqa: E402

#: The owner module, as a path from the repository root.
OWNER = "src/motion_scan.py"
#: The owner name, read from the imported module and from no copy of the text.
OWNER_NAME = "NO_FRAMES_FOR_THE_STRIP"
#: The sentence the owner holds.  This module states it one time, as a fixture.
SENTENCE = "no frames for the strip"
#: The other module that raises the sentence.
READER = "src/track_before_detect.py"
#: The two modules that raise the sentence.
MODULES = (OWNER, READER)
#: The module the reader reads the sentence from.
OWNER_MODULE = "src.motion_scan"
#: The spelling of the name in the definition of the owner, for the line regex.
NAME_RE = re.compile(rf"\s*{OWNER_NAME}\s*=")
#: A module-level name in upper case, the shape of a constant of this house.
CONSTANT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
#: The two trees this walk reads for a copy of the sentence outside the home.
SWEEP = ((ROOT / "src", "*.py"), (ROOT / "annotator", "*.js"))
#: A planted copy of the sentence, three lines below the last line of a file.
PLANTED_BODY = '    return "no frames for the strip"'
PLANTED = f"\n\ndef _planted_copy():\n{PLANTED_BODY}\n"
#: How far the planted body sits below the last live line of a source file.
PLANTED_OFFSET = len(PLANTED.splitlines())


def own_sentence() -> str:
    """The value of the owner name, read from the imported module."""
    value = getattr(motion_scan, OWNER_NAME, None)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{OWNER}:{OWNER_NAME} is not a non-empty string: {value!r}")
    return value


def source_text(relative: str) -> str:
    """The text of one source file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one source file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(where: str, line: int, body: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return f"{where}:{line}: {body.strip()}  <- {why}"


def blame(offenders: list, why: str) -> str:
    """The failure text of a walk: every offender as ``path:line: <line text>``."""
    return "; ".join(report(where, line, body, why) for where, line, body in offenders)


def home_line(text: str, where: str = OWNER) -> int:
    """The number of the one line of the owner that defines the name."""
    sites = [number for number, body in enumerate(text.splitlines(), start=1)
             if NAME_RE.match(body)]
    if len(sites) != 1:
        raise AssertionError(f"{where} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
    return sites[0]


def sentence_sites(text: str, where: str) -> list:
    """Every line that spells the sentence: ``(path, line, the line text)``."""
    return [(where, number, body)
            for number, body in enumerate(text.splitlines(), start=1)
            if SENTENCE in body]


def copies_beyond_the_home(text: str, where: str) -> list:
    """Every spelling of the sentence away from the home line of the owner.

    The owner holds one spelling, on the line that defines the name.  Every
    other spelling is a second home of the fact.  A comment or a docstring that
    spells the sentence counts, because a reader copies it.  The reader module
    holds no home line, so every spelling inside it counts.
    """
    home = home_line(text, where) if where == OWNER else 0
    return [(place, number, body)
            for place, number, body in sentence_sites(text, where)
            if number != home]


def literal_sites(text: str, where: str, value: str) -> list:
    """Every string literal of a value: ``(path, line, the literal written)``."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Constant) and node.value == value:
            found.append((where, node.lineno, ast.unparse(node)))
    return sorted(found, key=lambda site: site[1])


def raise_arguments(text: str, where: str) -> list:
    """Every ``raise`` of an error with an argument: ``(path, line, argument)``."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if not node.exc.args:
            continue
        found.append((where, node.lineno, ast.unparse(node.exc.args[0])))
    return sorted(found, key=lambda site: site[1])


def import_aliases(text: str, where: str, module: str) -> list:
    """Every local name that one module imports another module under.

    The house writes ``from src import motion_scan as ms``, so the walk states
    the ``from`` shape as well as the plain ``import`` shape.
    """
    parts = module.split(".")
    leaf = parts[-1]
    parent = ".".join(parts[:-1])
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    found.append(alias.asname or leaf)
        elif isinstance(node, ast.ImportFrom) and node.module == parent:
            for alias in node.names:
                if alias.name in (leaf, module):
                    found.append(alias.asname or leaf)
    return sorted(set(found))


def imported_modules(text: str, where: str) -> list:
    """Every module name that one module imports."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return sorted(set(found))


class OwnerTests(unittest.TestCase):
    """The one home of the sentence, its value and the shape of its name."""

    def test_the_owner_names_the_shipped_sentence(self):
        self.assertEqual(own_sentence(), SENTENCE,
                         f"{OWNER}:{OWNER_NAME} moved; both raise sites "
                         f"must move with it")

    def test_the_owner_line_of_the_module_carries_the_shipped_sentence(self):
        """The line of the owner module that holds the value, with its number.

        This case pins the home at ``path:line``.  The value the module answers
        and the value that the text of the module shows must be one sentence, so
        a reader of the report can open that line and see the shipped sentence.
        """
        sentence = own_sentence()
        lines = source_lines(OWNER)
        number = home_line(source_text(OWNER))
        body = lines[number - 1]
        self.assertIn(f'{OWNER_NAME} = "{sentence}"', body,
                      report(OWNER, number, body,
                             f"the line does not assign {sentence!r} to {OWNER_NAME}"))

    def test_the_owner_name_has_the_shape_of_a_constant(self):
        self.assertTrue(CONSTANT_NAME_RE.match(OWNER_NAME),
                        f"{OWNER_NAME} is not the name of a constant")
        value = own_sentence()
        self.assertIsInstance(value, str, f"{OWNER}:{OWNER_NAME} = {value!r}")

    def test_the_owner_line_is_the_only_spelling_in_the_owner(self):
        """One spelling lives in the owner, and it stands on the home line."""
        text = source_text(OWNER)
        number = home_line(text)
        found = sentence_sites(text, OWNER)
        self.assertEqual(1, len(found),
                         f"{OWNER} holds {len(found)} spellings of the sentence; "
                         f"the walk wants one: {blame(found, 'one home per fact')}")
        self.assertEqual(number, found[0][1],
                         f"{OWNER} spells the sentence on line {found[0][1]} and "
                         f"not on the home line {number}")


class SiteTests(unittest.TestCase):
    """Both raise sites read the home, and neither holds the sentence."""

    def test_the_owner_module_holds_one_spelling_of_the_sentence(self):
        offenders = copies_beyond_the_home(source_text(OWNER), OWNER)
        self.assertEqual([], offenders,
                         blame(offenders, "a second spelling is a second home"))

    def test_the_other_module_holds_no_spelling_of_the_sentence(self):
        offenders = copies_beyond_the_home(source_text(READER), READER)
        self.assertEqual([], offenders,
                         blame(offenders, "the reader reads the name of the owner"))

    def test_the_owner_raise_site_reads_the_owner_name(self):
        """The strip of the owner raises the sentence through the owner name."""
        text = source_text(OWNER)
        lines = source_lines(OWNER)
        sites = [site for site in raise_arguments(text, OWNER) if OWNER_NAME in site[2]]
        self.assertEqual(1, len(sites),
                         f"{OWNER} holds {len(sites)} raises that name {OWNER_NAME}: "
                         f"{blame(sites, 'the raise must read the home')}")
        _where, number, written = sites[0]
        self.assertEqual(OWNER_NAME, written,
                         report(OWNER, number, lines[number - 1],
                                f"the raise reads {written!r} and not {OWNER_NAME!r}"))

    def test_the_owner_raise_site_holds_no_sentence_literal(self):
        """The raise of the owner holds no string literal of the sentence."""
        text = source_text(OWNER)
        home = home_line(text)
        offenders = [site for site in literal_sites(text, OWNER, SENTENCE)
                     if site[1] != home]
        self.assertEqual([], offenders,
                         blame(offenders, "the raise must not hold the sentence"))

    def test_the_other_module_imports_the_owner_module(self):
        """``src.track_before_detect`` is the module the reader reads from."""
        aliases = import_aliases(source_text(READER), READER, OWNER_MODULE)
        self.assertTrue(aliases,
                        f"{READER} imports no name from {OWNER_MODULE}, so the "
                        f"raise cannot read the home")

    def test_the_other_raise_site_reads_the_owner_under_the_module_alias(self):
        """The second strip raises the sentence through the module alias."""
        text = source_text(READER)
        lines = source_lines(READER)
        aliases = import_aliases(text, READER, OWNER_MODULE)
        expected = {f"{alias}.{OWNER_NAME}" for alias in aliases}
        sites = [site for site in raise_arguments(text, READER) if site[2] in expected]
        self.assertEqual(1, len(sites),
                         f"{READER} holds {len(sites)} raises that name the home "
                         f"as one of {sorted(expected)}: "
                         f"{blame(sites, 'the raise must read the home')}")
        _where, number, written = sites[0]
        self.assertIn(written, expected,
                      report(READER, number, lines[number - 1],
                             f"the raise reads {written!r} and not a spelling of "
                             f"{OWNER_NAME} under {sorted(expected)}"))

    def test_the_owner_module_imports_no_part_of_the_other_module(self):
        """The new read adds no import, so no cycle can appear.

        The direction of the read is ``src/track_before_detect.py`` ->
        ``src.motion_scan``, and that edge exists at ``src/track_before_detect.py:47``.
        This case holds the other direction empty.  The reader reads the home
        through the alias it already has, so the edge count does not move.
        """
        bad = [name for name in imported_modules(source_text(OWNER), OWNER)
               if "track_before_detect" in name]
        self.assertEqual([], bad,
                         f"{OWNER} imports {bad}; the read of the sentence must "
                         f"add no cycle")

    def test_the_walk_answers_no_copy_of_the_two_modules(self):
        """The honest count of the walk over both modules is zero."""
        offenders = [site for where, text in ((OWNER, source_text(OWNER)),
                                              (READER, source_text(READER)))
                      for site in copies_beyond_the_home(text, where)]
        self.assertEqual([], offenders, blame(offenders, "the sentence has one home"))

    def test_no_other_file_of_src_or_annotator_spells_the_sentence(self):
        """The walk of the two trees finds the sentence in no other file."""
        offenders = []
        seen = 0
        for directory, pattern in SWEEP:
            for path in sorted(directory.rglob(pattern)):
                where = path.relative_to(ROOT).as_posix()
                if where == OWNER:
                    continue
                seen += 1
                offenders.extend(sentence_sites(path.read_text(encoding="utf-8"), where))
        self.assertGreater(seen, 200, f"the walk read {seen} files, too few to trust")
        self.assertEqual([], offenders,
                         blame(offenders, "the sentence has one home, in the owner"))


class PlantedTests(unittest.TestCase):
    """The walk is honest: a planted copy reddens the case and names the line."""

    def test_a_planted_copy_in_the_owner_names_the_line(self):
        """A second spelling in the owner is an offender with its path and line."""
        text = source_text(OWNER) + PLANTED
        offenders = copies_beyond_the_home(text, OWNER)
        self.assertEqual(1, len(offenders),
                         f"the walk found {len(offenders)} offenders in the planted "
                         f"owner: {offenders}")
        where, number, _body = offenders[0]
        message = blame(offenders, "a second spelling is a second home")
        self.assertEqual(len(source_lines(OWNER)) + PLANTED_OFFSET, number,
                         f"the walk names line {number}: {message}")
        self.assertIn(f"{where}:{number}: ", message,
                      f"the failure text names no path and line: {message}")
        self.assertIn(SENTENCE, message,
                      f"the failure text quotes no sentence: {message}")

    def test_a_planted_copy_in_the_reader_names_the_line(self):
        """A spelling in the reader is an offender with its path and line."""
        text = source_text(READER) + PLANTED
        offenders = copies_beyond_the_home(text, READER)
        self.assertEqual(1, len(offenders),
                         f"the walk found {len(offenders)} offenders in the planted "
                         f"reader: {offenders}")
        where, number, _body = offenders[0]
        message = blame(offenders, "the reader reads the name of the owner")
        self.assertEqual(len(source_lines(READER)) + PLANTED_OFFSET, number,
                         f"the walk names line {number}: {message}")
        self.assertIn(f"{where}:{number}: ", message,
                      f"the failure text names no path and line: {message}")

    def test_a_planted_copy_moves_the_count_of_the_owner_case(self):
        """The live owner answers one spelling, and the planted owner two.

        This case proves that the count of the owner case moves.  A copy of the
        sentence in the owner is the shape the walk must catch.
        """
        live = sentence_sites(source_text(OWNER), OWNER)
        planted = sentence_sites(source_text(OWNER) + PLANTED, OWNER)
        self.assertEqual(1, len(live), f"the live owner answers {live}")
        self.assertEqual(2, len(planted), f"the planted owner answers {planted}")


if __name__ == "__main__":
    unittest.main()
