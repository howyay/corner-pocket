"""One home of the two person report paths, and no second spelling in a reader.

The two paths have one home: `PERSON_REPORT_PATHS` in `src/store.py`, beside
`SHARED_ARTIFACT_NAMES`.  Two readers join that name with their own root:
`src/pid_identity.py` builds `str(ROOT / rel)`, and `src/yolo_track.py` builds
`os.path.join(REPO, rel)`.  Before round 107 each reader spelled both paths in full, so
the two files held four copies of the pair.

The cases below read the home, count the spelling sites under `src/`, read the two
reader sites, plant the old spelling in the text of one reader, and read the report of
that spelling.  The report names the path and the line of the spelling.
"""
from __future__ import annotations

import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.store import PERSON_REPORT_PATHS  # noqa: E402

#: The owner module of the two paths, as a path under the repository root.
OWNER = "src/store.py"
#: The dotted name of the owner, as an import names it.
MODULE = "src.store"
#: The name of the home.
HOME_NAME = "PERSON_REPORT_PATHS"
#: The two readers, with the root that each one joins to the home.
READERS = (("src/pid_identity.py", "ROOT"), ("src/yolo_track.py", "REPO"))
#: The two paths that the home must answer, in order.
PATHS = ("out/pid1_persons/report.json", "out/pid1_persons2/report2.json")
#: The directory names and the file names of the pair.  A reader may not spell one.
SEGMENTS = ("pid1_persons", "pid1_persons2", "report.json", "report2.json")
#: The number of files under src/ that spell a part of the pair, and the number of
#: sites that the owner holds.
SPELLING_FILE_COUNT = 1
SPELLING_SITE_COUNT = 2
#: The number of sites of one reader that join the home to its own root.
BUILD_SITE_COUNT = 1
#: The number of import lines of one reader that take the home from the owner.
IMPORT_SITE_COUNT = 1


def text_of(relative: str) -> str:
    """The text of one file, as a path under the repository root."""
    return (ROOT / relative).read_text(encoding="utf-8")


def report(relative: str, number: int, line: str, why: str) -> str:
    """The message of one site: the path, the line, the text, and the reason."""
    return f"{relative}:{number}: {line.strip()}\n  {why}"


def literals_of(text: str) -> list[tuple[int, str]]:
    """Every string literal of one module, with the line that holds it."""
    found = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((node.lineno, node.value))
    return found


def spelling_sites(relative: str, text: str | None = None) -> list[str]:
    """The sites of one file that spell a path of the pair, or one of its parts."""
    body = text if text is not None else text_of(relative)
    found = []
    for number, value in literals_of(body):
        if value in PATHS or value in SEGMENTS:
            why = (f'the pair spells "{value}" in place of {OWNER}.{HOME_NAME};'
                   " read the owner's name")
            found.append(report(relative, number, body.splitlines()[number - 1], why))
    return found


def build_sites(relative: str, root_name: str) -> list[str]:
    """The sites of one reader that join the home to the root of that reader."""
    home = re.compile(r"\b%s\b" % HOME_NAME)
    root = re.compile(r"\b%s\b" % root_name)
    return [report(relative, number, line,
                   f"this line joins {HOME_NAME} to {root_name}")
            for number, line in enumerate(text_of(relative).splitlines(), 1)
            if home.search(line) and root.search(line)]


def import_sites(relative: str) -> list[str]:
    """The import lines of one reader that take the home from the owner."""
    found = []
    for node in ast.walk(ast.parse(text_of(relative))):
        if isinstance(node, ast.ImportFrom) and node.module == MODULE:
            for alias in node.names:
                if alias.name == HOME_NAME:
                    found.append(report(relative, node.lineno,
                                        text_of(relative).splitlines()[node.lineno - 1],
                                        f"this line takes {HOME_NAME} from {MODULE}"))
    return found


def repo_sites(relative):
    """Report every line of a reader that names REPO.  A failure then names a line."""
    found = []
    for number, line in enumerate(text_of(relative).splitlines(), start=1):
        if "REPO" in line:
            found.append(report(relative, number, line,
                                "this line names REPO, and the build site did not read the home"))
    return found


class StoreReportPathsOwner(unittest.TestCase):
    """One home of the two person report paths, and no second spelling."""

    def test_the_home_answers_the_two_paths(self):
        self.assertEqual(PATHS, tuple(PERSON_REPORT_PATHS),
                         "the home must answer the two paths in one order")
        for path in PERSON_REPORT_PATHS:
            self.assertTrue(path.startswith("out/"), path)
            self.assertTrue(path.endswith(".json"), path)
        self.assertEqual(2, len(set(PERSON_REPORT_PATHS)), "the two paths must differ")
        self.assertIn(HOME_NAME, text_of(OWNER), "the home must stand in the owner")

    def test_a_part_of_the_pair_stands_in_one_file_under_src(self):
        found = {}
        for path in sorted((ROOT / "src").glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            sites = spelling_sites(relative)
            if sites:
                found[relative] = sites
        self.assertEqual(SPELLING_FILE_COUNT, len(found),
                         "one file under src/ may spell a part of the pair:"
                         f" {sorted(found)}")
        self.assertEqual([OWNER], sorted(found),
                         "the owner of the pair must be the only file that spells it")
        self.assertEqual(SPELLING_SITE_COUNT, len(found[OWNER]),
                         "the owner must hold the two paths:\n" + "\n".join(found[OWNER]))

    def test_every_reader_reads_the_home(self):
        for relative, root_name in READERS:
            with self.subTest(reader=relative):
                self.assertEqual([], spelling_sites(relative),
                                 "a reader must not spell a part of the pair again")
                self.assertEqual(IMPORT_SITE_COUNT, len(import_sites(relative)),
                                 "a reader must take the home from the owner:\n"
                                 + "\n".join(import_sites(relative)))
                named = build_sites(relative, root_name) or repo_sites(relative)
                self.assertEqual(BUILD_SITE_COUNT, len(build_sites(relative, root_name)),
                                 f"a reader must join the home to {root_name}:\n"
                                 + "\n".join(named))

    def test_a_planted_spelling_is_reported_with_its_file_and_line(self):
        original = text_of(READERS[0][0])
        old = ('    for p in [str(ROOT / "out" / "pid1_persons" / "report.json"),\n'
               '              str(ROOT / "out" / "pid1_persons2" / "report2.json")]:')
        current = ("    for p in [str(ROOT / rel) for rel in %s]:" % HOME_NAME)
        self.assertTrue(current in original,
                        f"the live reader must hold {current.strip()}")
        planted_text = original.replace(current, old)
        self.assertTrue(planted_text != original, "the plant must change the text")
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_pid_identity.py"
            planted.write_text(planted_text, encoding="utf-8")
            number = next(number for number, line in
                          enumerate(planted_text.splitlines(), 1) if "pid1_persons" in line)
            found = spelling_sites(str(planted), planted_text)
        self.assertGreaterEqual(len(found), 2, found)
        self.assertIn(f"{planted}:{number}:", found[0])
        self.assertIn('"pid1_persons"', found[0])
        self.assertIn(f"{OWNER}.{HOME_NAME}", found[0])


if __name__ == "__main__":
    unittest.main()
