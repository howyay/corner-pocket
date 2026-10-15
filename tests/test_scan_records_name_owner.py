"""One home of the scan document name, and no second spelling in a reader.

The scan writes its per-sample document under one name.  That name has one home:
`RECORDS_NAME` in `src/scan_events.py`, beside `BALL_TABLE_MM_KEY`.  Five reader
sites in four tools take the name from that home and join it to their own
directory: `src/rebuild_events_v2.py` joins `SCAN`, `src/rebuild_events_calibrated.py`
joins the scan folder through the home `STATIC_OUT` of `src/datasets.py`,
`src/timing_verify.py` joins `out/scan30` twice (a default parameter and an argparse
default), and `src/motion_scan.py` joins `out/<name>`.
Before round 108 each site spelled the whole file name again.

The cases below read the home, count the spelling sites under `src/`, read every
reader site, plant the old spelling in the text of one reader, and read the report
of that spelling.  The report names the path and the line of the spelling.
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scan_events import RECORDS_NAME  # noqa: E402

#: The owner module of the name, as a path under the repository root.
OWNER = "src/scan_events.py"
#: The dotted name of the owner, as an import names it.
MODULE = "src.scan_events"
#: The name of the home.
HOME_NAME = "RECORDS_NAME"
#: The file name that the home must answer.
FILE_NAME = "records.json"
#: The reader sites: the file, the number of sites, and the directory token that
#: the site joins to the home.  The token is the literal directory of the reader, or
#: the name of the folder home that answers it.  ``src/rebuild_events_calibrated.py``
#: takes its scan folder from ``STATIC_OUT`` of ``src/datasets.py``, so a reader that
#: spells ``"scan30"`` again loses the token and answers no site here.
READERS = (
    ("src/rebuild_events_v2.py", 1, "SCAN"),
    ("src/rebuild_events_calibrated.py", 1, "STATIC_OUT"),
    ("src/timing_verify.py", 2, "out/scan30"),
    ("src/motion_scan.py", 1, "name"),
)
#: The folder home of a reader whose directory token is a home name: the module and
#: the name that the reader must import, so the token of its join is the home of the
#: folder and not a local name of the reader.
FOLDER_HOMES = {
    "src/rebuild_events_calibrated.py": ("src.datasets", "STATIC_OUT"),
}
#: The number of files under src/ that spell the file name in CODE, and the number
#: of code sites that the owner holds.  A docstring may name the file: prose keeps
#: the history of a patch, and it does not read the name.
CODE_FILE_COUNT = 1
CODE_SITE_COUNT = 1


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


def code_sites(relative: str, text: str | None = None) -> list[str]:
    """The code sites of one file that spell the file name of the scan document."""
    body = text if text is not None else text_of(relative)
    prose = docstring_lines(body)
    found = []
    for node in ast.walk(ast.parse(body)):
        if not isinstance(node, ast.Constant) or node.value != FILE_NAME:
            continue
        if node.lineno in prose:
            continue
        why = (f'the file name stands as "{FILE_NAME}" in place of {OWNER}.{HOME_NAME};'
               " read the owner's name")
        found.append(report(relative, node.lineno, body.splitlines()[node.lineno - 1], why))
    return found


def import_sites(relative: str) -> list[str]:
    """The import lines of one reader that take the home from the owner."""
    text = text_of(relative)
    found = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.ImportFrom) and node.module == MODULE:
            for alias in node.names:
                if alias.name == HOME_NAME:
                    found.append(report(relative, node.lineno,
                                        text.splitlines()[node.lineno - 1],
                                        f"this line takes {HOME_NAME} from {MODULE}"))
    return found


def imported_names(relative: str, module: str) -> list[str]:
    """The local names of one reader that it takes from one module."""
    found = []
    for node in ast.walk(ast.parse(text_of(relative))):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                found.append(alias.asname or alias.name)
    return sorted(found)


def build_sites(relative: str, directory: str) -> list[str]:
    """The sites of one reader that join the home to the directory of that reader."""
    return [report(relative, number, line, f"this line joins {HOME_NAME} to {directory}")
            for number, line in enumerate(text_of(relative).splitlines(), 1)
            if HOME_NAME in line and directory in line and "import" not in line]


class ScanRecordsNameOwner(unittest.TestCase):
    """One home of the scan document name, and no second spelling."""

    def test_the_home_answers_the_scan_document_name(self):
        self.assertEqual(FILE_NAME, RECORDS_NAME, "the home must answer the file name")
        self.assertTrue(RECORDS_NAME.endswith(".json"), RECORDS_NAME)
        self.assertIn(HOME_NAME, text_of(OWNER), "the home must stand in the owner")

    def test_the_file_name_stands_in_one_file_under_src(self):
        found = {}
        for path in sorted((ROOT / "src").glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            sites = code_sites(relative)
            if sites:
                found[relative] = sites
        self.assertEqual([OWNER], sorted(found),
                         "one file under src/ may spell the file name in code:"
                         f" {sorted(found)}")
        self.assertEqual(CODE_FILE_COUNT, len(found), sorted(found))
        self.assertEqual(CODE_SITE_COUNT, len(found[OWNER]),
                         "the owner must hold one code site:\n" + "\n".join(found[OWNER]))

    def test_every_reader_reads_the_home(self):
        for relative, count, directory in READERS:
            with self.subTest(reader=relative):
                self.assertEqual([], code_sites(relative),
                                 "a reader must not spell the file name again:\n"
                                 + "\n".join(code_sites(relative)))
                self.assertEqual(1, len(import_sites(relative)),
                                 "a reader must take the home from the owner:\n"
                                 + "\n".join(import_sites(relative)))
                home = FOLDER_HOMES.get(relative)
                if home is not None:
                    module, name = home
                    self.assertIn(name, imported_names(relative, module),
                                  f"a reader must take its scan folder from {module}.{name},"
                                  " and it does not import that name: the token of its "
                                  f"join is another name")
                sites = build_sites(relative, directory)
                self.assertEqual(count, len(sites),
                                 f"a reader must join {HOME_NAME} to {directory}:\n"
                                 + "\n".join(sites or import_sites(relative)))

    def test_a_planted_name_is_reported_with_its_file_and_line(self):
        relative = READERS[0][0]
        original = text_of(relative)
        current = "SCAN / %s" % HOME_NAME
        self.assertTrue(current in original, f"the live reader must hold {current}")
        planted_text = original.replace(current, 'SCAN / "%s"' % FILE_NAME)
        self.assertTrue(planted_text != original, "the plant must change the text")
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_rebuild_events_v2.py"
            planted.write_text(planted_text, encoding="utf-8")
            found = code_sites(str(planted), planted_text)
        self.assertEqual(1, len(found), found)
        self.assertTrue(found[0].startswith(f"{planted}:"), found[0])
        self.assertIn('SCAN / "records.json"', found[0])
        self.assertIn(f"{OWNER}.{HOME_NAME}", found[0])
        self.assertNotIn("predates the cloth_area patch", found[0])


if __name__ == "__main__":
    unittest.main()
