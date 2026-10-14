"""One home of the shot pairing rule: the pair gap and the displacement floor.

The rule "pair gap <= 3.5 s, >= 300 mm" decides which SAM3 displacement verifies
a shot, and which raw candidate is a shot at all.  It has one home: `SHOT_DISP_MM`
and `SHOT_PAIR_GAP_S` in `src/scan_events.py`.  Five reader sites take the two
names there: the interval test in `src/scan_events.py`, in
`src/rebuild_events_v2.py` and in `src/rebuild_events_calibrated.py`, and the floor
default of `src/event_gates.py`, `src/ball_census.py` and `src/candidate_scan.py`.
The floor was a bare literal `300.0` in three modules, and the interval was a bare
literal `3.5` in three modules.

The cases below read the two homes, count the code sites under `src/`, read every
reader site, plant the old lower bound in the text of one reader, and read the
report of that spelling.  The report names the path and the line.
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scan_events import SHOT_DISP_MM, SHOT_PAIR_GAP_S  # noqa: E402

#: The owner module of both homes, as a path under the repository root.
OWNER = "src/scan_events.py"
#: The two names of the rule, with the value that each one must answer.
GAP_HOME, GAP_VALUE = "SHOT_PAIR_GAP_S", 3.5
FLOOR_HOME, FLOOR_VALUE = "SHOT_DISP_MM", 300.0
#: The sites that test the pair interval: the file, the line count, and the shape.
INTERVAL_READERS = (("src/scan_events.py", 1),
                    ("src/rebuild_events_v2.py", 1),
                    ("src/rebuild_events_calibrated.py", 1))
#: The sites that hold the displacement floor as a default value.
FLOOR_READERS = (("src/event_gates.py", 1),
                 ("src/ball_census.py", 1),
                 ("src/candidate_scan.py", 1))
#: The number of files under src/ that spell the interval in code, and the number
#: of code sites that the owner holds.
GAP_FILE_COUNT = 1
GAP_SITE_COUNT = 1


def text_of(relative: str) -> str:
    """The text of one file, as a path under the repository root."""
    return (ROOT / relative).read_text(encoding="utf-8")


def report(relative: str, number: int, line: str, why: str) -> str:
    """The message of one site: the path, the line, the text, and the reason."""
    return f"{relative}:{number}: {line.strip()}\n  {why}"


def docstring_lines(text: str) -> set[int]:
    """The lines of every docstring of one module.  Prose is not a code site."""
    found: set[int] = set()
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            first, last = value.lineno, value.end_lineno or value.lineno
            found.update(range(first, last + 1))
    return found


def number_sites(relative: str, value, text: str | None = None) -> list[str]:
    """The code sites of one file that spell a number of the rule."""
    body = text if text is not None else text_of(relative)
    prose = docstring_lines(body)
    found = []
    for node in ast.walk(ast.parse(body)):
        if not isinstance(node, ast.Constant) or isinstance(node.value, bool):
            continue
        if node.value != value or node.lineno in prose:
            continue
        why = (f"the number stands as {value!r} in place of {OWNER}"
               f".{GAP_HOME} or {OWNER}.{FLOOR_HOME}; read the owner's name")
        found.append(report(relative, node.lineno, body.splitlines()[node.lineno - 1], why))
    return found


def import_lines(text: str) -> set[int]:
    """The lines of every import statement of one module.  An import is not a reader.

    A wrapped import puts names on continuation lines that do not hold the word
    ``import``.  The tree measures the statement, so a wrapped import counts as one
    import and adds no reader site.
    """
    found = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            first, last = node.lineno, node.end_lineno or node.lineno
            found.update(range(first, last + 1))
    return found


def home_sites(relative: str, home: str, forbidden: str) -> list[str]:
    """The sites of one reader that name a home and no bare number of the rule."""
    body = text_of(relative)
    imports = import_lines(body)
    found = []
    for number, line in enumerate(body.splitlines(), 1):
        if number in imports or home not in line:
            continue
        if line.strip().startswith(home + " ="):     # the definition of the home itself
            continue
        if forbidden in line:
            found.append(report(relative, number, line,
                                f"this line names {home} and the bare number again"))
        else:
            found.append(report(relative, number, line, f"this line reads {home}"))
    return found


class ShotPairRuleOwner(unittest.TestCase):
    """One home of the pair gap and the displacement floor, and no second spelling."""

    def test_the_two_homes_answer_the_pair_rule(self):
        self.assertEqual(GAP_VALUE, SHOT_PAIR_GAP_S, "the home must answer the pair gap")
        self.assertEqual(FLOOR_VALUE, SHOT_DISP_MM, "the home must answer the floor")
        self.assertLess(SHOT_PAIR_GAP_S, FLOOR_VALUE, "the two homes must stay distinct values")
        body = text_of(OWNER)
        self.assertIn(GAP_HOME, body, "the gap home must stand in the owner")
        self.assertIn(FLOOR_HOME, body, "the floor home must stand in the owner")

    def test_the_interval_stands_in_one_file_under_src(self):
        found = {}
        for path in sorted((ROOT / "src").glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            sites = number_sites(relative, GAP_VALUE)
            if sites:
                found[relative] = sites
        self.assertEqual([OWNER], sorted(found),
                         "one file under src/ may spell the pair gap in code:"
                         f" {sorted(found)}")
        self.assertEqual(GAP_FILE_COUNT, len(found), sorted(found))
        self.assertEqual(GAP_SITE_COUNT, len(found[OWNER]),
                         "the owner must hold one code site:\n" + "\n".join(found[OWNER]))

    def test_every_interval_site_reads_the_gap_home(self):
        for relative, count in INTERVAL_READERS:
            with self.subTest(reader=relative):
                sites = home_sites(relative, GAP_HOME, "3.5")
                self.assertEqual(count, len(sites),
                                 f"a site must read {GAP_HOME} and no bare 3.5:\n"
                                 + "\n".join(sites))

    def test_every_floor_site_reads_the_floor_home(self):
        for relative, count in FLOOR_READERS:
            with self.subTest(reader=relative):
                sites = home_sites(relative, FLOOR_HOME, "300.0")
                self.assertEqual(count, len(sites),
                                 f"a site must read {FLOOR_HOME} and no bare 300.0:\n"
                                 + "\n".join(sites))

    def test_a_planted_floor_is_reported_with_its_file_and_line(self):
        relative = FLOOR_READERS[1][0]
        original = text_of(relative)
        current = "min_disp_mm: float = %s," % FLOOR_HOME
        self.assertTrue(current in original, f"the live reader must hold {current}")
        planted_text = original.replace(current, "min_disp_mm: float = 300.0,")
        self.assertTrue(planted_text != original, "the plant must change the text")
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_ball_census.py"
            planted.write_text(planted_text, encoding="utf-8")
            found = number_sites(str(planted), FLOOR_VALUE, planted_text)
        self.assertEqual(1, len(found), found)
        self.assertTrue(found[0].startswith(f"{planted}:"), found[0])
        self.assertIn("min_disp_mm: float = 300.0", found[0])
        self.assertIn(f"{OWNER}.{FLOOR_HOME}", found[0])


if __name__ == "__main__":
    unittest.main()
