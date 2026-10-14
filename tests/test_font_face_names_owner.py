"""The served face file names of the build table have one home, and the sheets read it.

annotator/fonts/build_fonts.py writes the .woff2 files that the two served pages draw:
the ten faces of LATIN_FACES at annotator/fonts/build_fonts.py:73 and the five faces of
CJK_FACES at annotator/fonts/build_fonts.py:87.  The same fifteen names stood again, as
hand copies, in three readers:

* annotator/board.css:14 declares barlow-500.woff2 and three more names in url();
* annotator/ops.css:18 declares all fifteen names in url();
* BOARD_FONTS at annotator/unified_server.py:2692 routes four of them under /fonts/.

`git grep -n 'LATIN_FACES' -- tests/` and `git grep -n 'CJK_FACES' -- tests/` both answered
nothing, so a rename in the build table was silent: the committed file keeps its old name
on disk, the page still draws it, and no case reddens.

The build table stays the home.  FACE_FILES at annotator/fonts/build_fonts.py:121 reads
the output column of the two tables into one readable table.  A stylesheet cannot read a
python name, and annotator/unified_server.py cannot import the build: the build reads
PAGE_FILES from the server, so an import back would close a cycle.  The cases of this
module therefore hold the two sheets and BOARD_FONTS to the table.

The -common files are the other row: their home is COMMON_FACES at
annotator/fonts/build_fonts.py:101, and tests/test_font_coverage_owner.py holds them.
The two rows do not overlap, so every face name of a stylesheet belongs to one row.

The cases:

* FACE_FILES is the output column of LATIN_FACES and CJK_FACES, in order, and the fifteen
  names are written here as words;
* every name of the two sheets is a name of FACE_FILES, and every name of FACE_FILES is a
  name of the sheets, so a name that stands on one side only reports its site;
* every name of BOARD_FONTS is a name of FACE_FILES;
* every name of FACE_FILES is the name of a shipped file under annotator/fonts/, and no
  shipped non-common file is absent from FACE_FILES, so a rename catches both sides;
* the scans are not empty, and a planted name reports `path:line: <line text>`.

Run: ./scripts/pool-test.sh python test_font_face_names_owner
"""
import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BUILD = "annotator/fonts/build_fonts.py"
SERVER = "annotator/unified_server.py"
SHEETS = ("annotator/board.css", "annotator/ops.css")
FONT_DIR = "annotator/fonts"

#: The two build tables that write a served face.  Together they are the home of the
#: fifteen names, and FACE_FILES reads their output column.
TABLES = ("LATIN_FACES", "CJK_FACES")

#: The one readable table of the fifteen served face file names.
HOME = "FACE_FILES"

#: The route list of the public board, a reader of the same names.
BOARD_TABLE = "BOARD_FONTS"

#: The home of the other row: the three -common files.
COMMON_TABLE = "COMMON_FACES"

#: The fifteen names of the two tables, as words.  A count of them drifts; these names do
#: not.  The order is the order of LATIN_FACES and then of CJK_FACES.
FACE_NAMES = (
    "zilla-slab-400.woff2", "zilla-slab-400-italic.woff2", "zilla-slab-500.woff2",
    "zilla-slab-600.woff2", "barlow-400.woff2", "barlow-500.woff2", "barlow-600.woff2",
    "barlow-700.woff2", "dm-mono-400.woff2", "dm-mono-500.woff2",
    "noto-sans-sc-400.woff2", "noto-sans-sc-500.woff2", "noto-serif-sc-400.woff2",
    "noto-serif-sc-500.woff2", "noto-serif-sc-700.woff2")

#: The four non-common names BOARD_FONTS routes.  Its fifth name is a -common file, so it
#: is the fact of the other row.
BOARD_NAMES = ("barlow-500.woff2", "barlow-600.woff2", "barlow-700.woff2",
               "noto-sans-sc-500.woff2")

#: The word that marks a file of the other row.  A stylesheet cannot read a python name,
#: so the two rows split the names of the sheets by this suffix.
COMMON_SUFFIX = "-common.woff2"

_FACE_IN_LINE = re.compile(r"[\w.\[\]-]+\.woff2")


def face_sites(text, path):
    """Every .woff2 name of a text, as (name, "path:line", line text)."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for name in _FACE_IN_LINE.findall(line):
            hits.append((name, f"{path}:{number}", line.strip()))
    return hits


def table_face_sites(source, path, table):
    """Every name a table writes, as (name, "path:line", line text).

    The scan reads the table of the module source with `ast`.  So a face name in a
    comment or in a docstring is not a name the table writes, and the report carries the
    line of the table itself.
    """
    lines = source.splitlines()
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == table
                   for target in node.targets):
            continue
        sites = []
        for element in node.value.elts:
            first = element.elts[0] if isinstance(element, ast.Tuple) else element
            sites.append((first.value, f"{path}:{first.lineno}",
                          lines[first.lineno - 1].strip()))
        return sites
    raise AssertionError(f"{path} must write {table} = (...): the home of the face names")


def non_common(sites):
    """The sites of the names that are not -common files: the fact of this module."""
    return [site for site in sites if not site[0].endswith(COMMON_SUFFIX)]


def offender(site, line, reason):
    """One report line in the house shape: `path:line: <line text>  <- reason`."""
    return f"{site}: {line}  <- {reason}"


def mirror_report(home_names, home_sites, reader_sites, reader):
    """Every name that stands on one side only, in both directions."""
    reader_names = {name for name, _, _ in reader_sites}
    offenders = [offender(site, line,
                          f"{name} stands in {reader}, and {BUILD} ({HOME}) does not write it")
                 for name, site, line in reader_sites if name not in home_names]
    offenders += [offender(site, line,
                           f"{BUILD} ({HOME}) writes {name}, and {reader} does not name it")
                  for name, site, line in home_sites if name not in reader_names]
    return offenders


def subset_report(home_names, board_sites):
    """Every name of the route list that the one readable table does not write."""
    return [offender(site, line,
                     f"{name} stands in {BOARD_TABLE}, and {BUILD} ({HOME}) does not write it")
            for name, site, line in board_sites if name not in home_names]


def build_source():
    return (ROOT / BUILD).read_text(encoding="utf-8")


def table_sites(table):
    """The rows of one table of the build, with their own path:line."""
    return table_face_sites(build_source(), BUILD, table)


def live_home_sites():
    """The fifteen rows of the two tables that write a served face."""
    return [site for table in TABLES for site in table_sites(table)]


def sheet_sites(path):
    """The face names one stylesheet declares."""
    return face_sites((ROOT / path).read_text(encoding="utf-8"), path)


def sheet_reader_sites():
    """The non-common face names of both sheets: the copies this module holds."""
    return [site for path in SHEETS for site in non_common(sheet_sites(path))]


def board_rows():
    """The rows of BOARD_FONTS, read from the source of the server."""
    return table_face_sites((ROOT / SERVER).read_text(encoding="utf-8"), SERVER, BOARD_TABLE)


class FontFaceNamesOwner(unittest.TestCase):
    """One home for the fifteen served face file names, and three readers held to it."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT))
        try:
            from annotator.fonts import build_fonts
            from annotator.unified_server import BOARD_FONTS
        finally:
            sys.path.remove(str(ROOT))
        cls.build = build_fonts
        #: The route list, read from the module the public port answers with, so the two
        #: readers of this case meet at one value.
        cls.board = BOARD_FONTS

    def test_the_two_tables_and_the_one_readable_table_name_the_same_fifteen(self):
        """The home: the output column of the two tables, under one readable name."""
        rows = live_home_sites()
        self.assertEqual(
            [name for name, _, _ in rows], list(FACE_NAMES),
            f"{BUILD} must write the fifteen served face file names, in the order of "
            f"{TABLES[0]} and {TABLES[1]}")
        self.assertEqual(
            tuple(self.build.FACE_FILES), FACE_NAMES,
            f"{BUILD} must resolve {HOME} to the output column of the two tables.  A stylesheet "
            "cannot read a python name, so this table is the one home that a reader can name.")
        for name in FACE_NAMES:
            with self.subTest(name=name):
                self.assertFalse(
                    name.endswith(COMMON_SUFFIX),
                    f"{name} is a -common file.  Its home is {COMMON_TABLE} at {BUILD}:101, and "
                    "tests/test_font_coverage_owner.py holds it.")

    def test_the_two_stylesheets_and_the_home_name_one_set_of_faces(self):
        """One fact, three homes: the two tables, ops.css and board.css.

        A rename in the build table alone was silent: the committed file keeps its old
        name on disk, so a case on the store still passes.  This case reports every name
        that stands on one side only, with the path and the line of the site that holds
        it.
        """
        home = set(self.build.FACE_FILES)
        rows = live_home_sites()
        self.assertEqual(
            {name for name, _, _ in rows}, home,
            f"{HOME} must read the two tables: an equal tuple fails this case only when one of "
            "the two sides moves alone, and this line holds the two sides together.")
        offenders = mirror_report(home, rows, sheet_reader_sites(), "the two stylesheets")
        self.assertEqual(
            [], offenders,
            f"the face file names of {BUILD} ({HOME}) and the names of {SHEETS[0]} and "
            f"{SHEETS[1]} must be one set: " + "; ".join(offenders)
            + ".  A name of the table that no stylesheet declares downloads nothing, and a "
              "name of a stylesheet that the table does not write serves no file.")

    def test_the_board_route_list_names_files_of_the_build_table(self):
        """The route list is a reader of the same names, not a second home of them."""
        rows = board_rows()
        self.assertEqual(
            tuple(self.board), tuple(name for name, _, _ in rows),
            f"{SERVER} must resolve {BOARD_TABLE} to the names its own source writes")
        board = non_common(rows)
        self.assertEqual(
            [name for name, _, _ in board], list(BOARD_NAMES),
            f"{SERVER} ({BOARD_TABLE}) must route the four non-common names of the board")
        offenders = subset_report(set(self.build.FACE_FILES), board)
        self.assertEqual(
            [], offenders,
            f"every name of {SERVER} ({BOARD_TABLE}) must be a name of {BUILD} ({HOME}): "
            + "; ".join(offenders) + ".  A route with no file answers 404, and the page draws "
              "the face of a name the build never wrote.")

    def test_every_name_is_the_name_of_a_shipped_file(self):
        """The name and the file on disk must be one word, in both directions."""
        home = set(self.build.FACE_FILES)
        for name in sorted(home):
            with self.subTest(name=name):
                self.assertTrue(
                    (ROOT / FONT_DIR / name).is_file(),
                    f"{BUILD} ({HOME}) writes {name}, and {FONT_DIR}/{name} is not a shipped "
                    "file: the route would answer 404 and the page would fall back to a system "
                    "face.")
        shipped = {path.name for path in (ROOT / FONT_DIR).glob("*.woff2")
                   if not path.name.endswith(COMMON_SUFFIX)}
        self.assertEqual(
            sorted(shipped), sorted(home),
            f"the shipped non-common .woff2 files of {FONT_DIR} and the names of {HOME} must be "
            "one set.  A rename in the build table alone leaves the old file on disk, and the "
            "page still draws it.")

    def test_the_two_sheets_declare_faces_and_the_scans_are_not_empty(self):
        """An empty scan cannot pass the case above: the real names stand in the text."""
        seen = set()
        for path in SHEETS:
            found = non_common(sheet_sites(path))
            with self.subTest(path=path):
                self.assertTrue(found, f"{path} declares no served face, so the scan is empty")
            seen |= {name for name, _, _ in found}
        self.assertEqual(
            sorted(seen), sorted(FACE_NAMES),
            f"the two sheets together must declare every name of {HOME}: a name that no sheet "
            "draws meets this case.")

    def test_the_common_files_are_the_other_row(self):
        """The 15 names and the 3 -common names are two rows: a name stands in one row only."""
        common_names = {name for name, _, _ in table_sites(COMMON_TABLE)}
        for name in common_names:
            with self.subTest(name=name):
                self.assertTrue(
                    name.endswith(COMMON_SUFFIX),
                    f"{BUILD} ({COMMON_TABLE}) writes {name}, and the name is not a -common file: "
                    f"the row of {COMMON_TABLE} holds -common files only.")
        for name in FACE_NAMES:
            with self.subTest(name=name):
                self.assertNotIn(
                    name, common_names,
                    f"{name} must stand in one row only: {COMMON_TABLE} and {HOME} are two facts")
        sheet_common = {name for path in SHEETS for name, _, _ in sheet_sites(path)
                        if name.endswith(COMMON_SUFFIX)}
        self.assertEqual(
            sorted(sheet_common), sorted(common_names),
            f"the -common names of the two sheets are the row of {BUILD} ({COMMON_TABLE}), which "
            "tests/test_font_coverage_owner.py holds.  This module holds every other name, so no "
            "name of a sheet is held by no case.")

    def test_a_face_name_that_stands_in_one_home_only_is_reported(self):
        """The report rule, on planted text, in both directions and both shapes.

        The plants are text, so the module resolves every value.  The last two assertions
        show the rule on today's files, so the rule is not "always red".
        """
        planted_home = table_face_sites(
            "LATIN_FACES = (\n"
            "    ('planted-home-only.woff2', 'x/Planted.ttf'),\n"
            ")\n", BUILD, "LATIN_FACES")
        self.assertEqual([("planted-home-only.woff2", f"{BUILD}:2")],
                         [(name, site) for name, site, _ in planted_home])
        offenders = mirror_report({"planted-home-only.woff2"}, planted_home, [],
                                  "the two stylesheets")
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f"{BUILD}:2: ", offenders[0])
        self.assertIn("planted-home-only.woff2", offenders[0])

        line = ("@font-face{font-family:'Barlow';src:url(/fonts/planted-sheet-only.woff2) "
                "format('woff2')}")
        planted_sheet = face_sites(line + "\n", SHEETS[1])
        self.assertEqual([("planted-sheet-only.woff2", f"{SHEETS[1]}:1")],
                         [(name, site) for name, site, _ in planted_sheet])
        offenders = mirror_report(set(FACE_NAMES), [], planted_sheet, "the two stylesheets")
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f"{SHEETS[1]}:1: {line}", offenders[0])
        self.assertIn("planted-sheet-only.woff2", offenders[0])

        planted_board = table_face_sites(
            'BOARD_FONTS = (\n    "planted-board-only.woff2",\n)\n', SERVER, BOARD_TABLE)
        self.assertEqual([("planted-board-only.woff2", f"{SERVER}:2")],
                         [(name, site) for name, site, _ in planted_board])
        offenders = subset_report(set(FACE_NAMES), planted_board)
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f'{SERVER}:2: "planted-board-only.woff2",', offenders[0])

        home = set(self.build.FACE_FILES)
        self.assertEqual(
            [], mirror_report(home, live_home_sites(), sheet_reader_sites(), "the two stylesheets"),
            "the two real homes and the two sheets must report no name of one home only")
        self.assertEqual(
            [], subset_report(home, non_common(board_rows())),
            f"the real {BOARD_TABLE} and the real {HOME} must report no name of one home only")


if __name__ == "__main__":
    unittest.main()
