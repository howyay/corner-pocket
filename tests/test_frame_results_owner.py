"""One home of the frame evidence folder name, and no second spelling.

The per-frame evidence folder name is one fact, and it has one home: ``FRAME_RESULTS`` in
``src/store_files.py``, the module that already discovers the documents under it.  Six code
sites spelled ``"frame_results"`` before round 119, in three shapes: the joined path
(``src/store_files.py:191``, ``annotator/unified_server.py:1969``, ``src/motion_scan.py:1542``),
the textual partition (``src/store_files.py:165`` checks the same name as a path part, and
``src/store_check.py:63`` cuts a stored path at it) and the SQL ``LIKE`` pattern
(``src/store_import.py:715``).  A guard that read only whole constants would miss the last
two shapes and let two of the six sites drift away, so the walk below names every code
constant that *holds* the folder name as a path part, not only the constants equal to it.

The home stands at the end of ``src/store_files.py``, below ``CTX_DOCUMENT`` (``:275``),
``META_DOCUMENT`` (``:276``) and ``crops_dir`` (``:279``): the append moved no pinned
number.  The readers joined an existing import line, and the one module that had no edge
to the home -- ``src/motion_scan.py`` -- traded a blank line of its import block for the
new line at ``src/motion_scan.py:63``, so it keeps its 2535 lines and every pin above and
below that line.

Three prose sites keep the word and are no constant: the docstring at
``src/motion_scan.py:1537`` and the report note at ``src/motion_scan.py:1555``, both held
by the case ``test_the_prose_of_the_round_keeps_its_lines``, and the docstring at
``src/store_files.py:196``.  A fourth form -- the private constant
``"SELECT path FROM json_documents WHERE path LIKE %s"`` of the same module -- is half of
the statement, not the folder name, so the read leaves it alone.

The walk below reads every python file of ``src/`` and ``annotator/``, skips ``src/sam3/``,
drops the string node of a module, class or function docstring, and answers every code
constant that holds the folder name as a path part while reading no home.  A floor keeps a
walk that read nothing from passing in silence.

Run: ``./scripts/pool-test.sh python test_frame_results_owner``
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from _shipped import code_strings  # noqa: E402
from src.store_files import FRAME_RESULTS  # noqa: E402

#: The home of the folder name, as a path under the repository root, and its name.
HOME = "src/store_files.py"
NAME = "FRAME_RESULTS"
MODULE = "src.store_files"
VALUE = "frame_results"
#: The line of the home, pinned by number and by text, with the two lines that say why this
#: module owns the name.
HOME_LINE = 290
HOME_FORM = 'FRAME_RESULTS = "frame_results"'
HOME_COMMENTS = {
    288: "# The frame folder name has one home here: the discovery, the checker and the stores",
    289: "# read this name, so one change lands in one file.",
}
#: The two homes of the same module that stood above the append, and the last line of the
#: document helper below it: the append moved no one of them.
CTX_LINE = 275
CTX_FORM = 'CTX_DOCUMENT = "ctx.json"'
META_LINE = 276
META_FORM = 'META_DOCUMENT = "meta.json"'
CROPS_LAST_LINE = 287
CROPS_LAST_FORM = 'return f"out/{set_name}"'
#: Every code site that reads the home, as `path:line`, with the text of that line.
SITES = {
    HOME: {
        165: "and parts[-3] == FRAME_RESULTS:",
        191: ('return f"{folder}/{FRAME_RESULTS}/'
              "{'*' if frame == '*' else int(frame)}/correction.json\""),
    },
    "annotator/unified_server.py": {
        1969: "return self.dataset(dataset) / FRAME_RESULTS / str(frame_index) / (kind + '.json')",
    },
    "src/motion_scan.py": {
        1542: 'base = root / "out" / STATIC_OUT[BUILT_IN_DATASET] / FRAME_RESULTS',
    },
    "src/store_check.py": {
        63: 'folder, marker, rest = path.partition("/" + FRAME_RESULTS + "/")',
    },
    "src/store_import.py": {
        715: ('"SELECT path FROM json_documents WHERE path LIKE %s", '
              '("%/" + FRAME_RESULTS + "/%%",)).fetchall()]'),
    },
}
#: Every import line that binds the home, as `path:line`, with the text of that line.  The
#: readers joined an existing import, and src/motion_scan.py traded a blank line at :63.
BINDINGS = {
    "annotator/unified_server.py": {
        72: "from src.store_files import (BALL_SETS, CTX_DOCUMENT, FACE_STORE,"
            " FRAME_RESULTS, crops_dir,  # noqa: E402",
    },
    "src/store_check.py": {
        29: "from src.store_files import (FRAME_RESULTS, SEED_DOCUMENT, STATE_DOCUMENT,"
            " dataset_of_dir,",
    },
    "src/store_import.py": {
        49: "from src.store_files import (BALL_SETS, DOCUMENT_SETS, FACE_STORE,"
            " FRAME_RESULTS, IDENTITY_DOCUMENT,",
    },
    "src/motion_scan.py": {
        63: "from src.store_files import FRAME_RESULTS  # noqa: E402",
    },
}
#: The modules that read the home: the owner module itself, and the four other readers.
READERS = (HOME, "annotator/unified_server.py", "src/motion_scan.py", "src/store_check.py",
           "src/store_import.py")
#: The test that reads the fact through the store, pinned by number and text.
READER_TEST = "tests/test_store_files.py"
READER_TEST_LINES = {
    375: '(vod / "frame_results" / "12").mkdir(parents=True)',
    376: '(vod / "frame_results" / "12" / "correction.json").write_text("{}",'
         ' encoding="utf-8")',
    402: '"out/scan30/frame_results/12/verdict.json"):',
}
#: The prose of the round: the word stands in the text of a docstring or of a note, and
#: none of these lines is a constant that holds the name as a path part.
PROSE = {
    "src/motion_scan.py": {
        1537: "``out/scan30/frame_results/*/inference.json`` carries person boxes but only for",
        1555: '"note": "out/scan30/frame_results holds 2 inference files on this dataset "',
    },
    HOME: {
        196: "are discovered under frame_results when a root is given).\"\"\"",
    },
}
#: The trees the walk reads, the subtree it skips, and the floor that keeps a walk that read
#: nothing from passing in silence.  With `src/sam3` left out the tree holds 113 python
#: modules, so the floor stands below that count and far above a walk that broke.
WALKED = ("src/**/*.py", "annotator/*.py")
SKIP = ("src/sam3",)
FILE_FLOOR = 100
#: The planted modules of the honesty cases.
PLANTED = "src/planted_frame_results.py"
PLANTED_LINES = (6, 7, 9)
PLANTED_TEXT = ('"""A planted module that spells the frame folder name three ways."""\n'
                "\n"
                "\n"
                "def rows(folder, frame):\n"
                '    """Joins the name, partitions it, and builds a LIKE pattern."""\n'
                '    joined = f"{folder}/frame_results/{frame}/correction.json"\n'
                '    folder, marker, rest = joined.partition("/frame_results/")\n'
                '    query = ("SELECT path FROM json_documents WHERE path LIKE %s",\n'
                '             ("%/frame_results/%",))\n'
                "    return rows_of(query)\n")
QUIET = "src/quiet_frame_results.py"
QUIET_TEXT = ('"""A planted module that names the folder in prose and in a report note."""\n'
              "\n"
              "\n"
              "def row():\n"
              '    """The frame folder holds frame_results/7/correction.json here."""\n'
              '    return {"note": "out/scan30/frame_results holds 2 inference files"}\n')


def text_of(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one file of this repository."""
    return text_of(relative).splitlines()


def walked_files() -> list:
    """Every walked python file, the generated subtree left out."""
    found = []
    for path in sorted(one for pattern in WALKED for one in ROOT.glob(pattern)):
        relative = path.relative_to(ROOT).as_posix()
        if "__pycache__" in path.parts or relative.startswith(SKIP):
            continue
        found.append(path)
    return found


def spells_the_folder(relative: str, lines: list) -> dict:
    """Every walked code constant that holds the folder name as a path part, by line.

    The joined path holds it after a ``/``, the textual partition and the SQL pattern hold
    it between two of them.  A report note that only starts with an unrelated folder is no
    holder, and neither is the statement that ends in ``LIKE %s``.
    """
    found = {}
    for line, value in code_strings(ast.parse(text_of(relative))):
        if not isinstance(value, str):
            continue
        parts = value.split("/")
        if VALUE not in parts:
            continue
        if len(parts) == 1 or parts[-1] == "%s":
            continue
        if relative != HOME and parts[0] == "out" and len(parts) > 3:
            continue
        if relative == HOME and line == HOME_LINE:
            continue
        found[line] = lines[line - 1].strip()
    return found


def analyze() -> list:
    """Every line that holds the folder name while reading no home."""
    offenders = []
    for path in walked_files():
        relative = path.relative_to(ROOT).as_posix()
        sites = spells_the_folder(relative, source_lines(relative))
        for line in sorted(sites):
            offenders.append("%s:%d: 'frame_results' spells the frame folder name; read"
                             " %s.%s" % (relative, line, MODULE, NAME))
    return offenders


def planted_copy(relative: str, text: str) -> list:
    """Write one planted module, run the walk, and remove the module."""
    path = ROOT / relative
    path.write_text(text, encoding="utf-8")
    try:
        return analyze()
    finally:
        path.unlink()


class HomeTests(unittest.TestCase):
    """The home answers the folder name, and its line is pinned."""

    def test_the_home_answers_the_folder_name(self):
        self.assertEqual(VALUE, FRAME_RESULTS,
                         f"{HOME}.{NAME} must answer the frame evidence folder name")
        self.assertIn(NAME, text_of(HOME), "the home must stand in its own module")

    def test_the_home_line_is_pinned_by_number_and_text(self):
        lines = source_lines(HOME)
        self.assertEqual(HOME_FORM, lines[HOME_LINE - 1].strip(),
                         f"{HOME}:{HOME_LINE} no longer holds the home; it reads"
                         f" {lines[HOME_LINE - 1].strip()!r}")
        for number, form in sorted(HOME_COMMENTS.items()):
            self.assertEqual(form, lines[number - 1].strip(),
                             f"{HOME}:{number} must say why this module owns the name")

    def test_the_append_moved_no_pinned_number(self):
        lines = source_lines(HOME)
        self.assertEqual(CTX_FORM, lines[CTX_LINE - 1].strip(),
                         f"{HOME}:{CTX_LINE} must keep the context document name")
        self.assertEqual(META_FORM, lines[META_LINE - 1].strip(),
                         f"{HOME}:{META_LINE} must keep the metadata document name")
        self.assertEqual(CROPS_LAST_FORM, lines[CROPS_LAST_LINE - 1].strip(),
                         f"{HOME}:{CROPS_LAST_LINE} must keep the last line of the helper"
                         " above the append")


class SiteTests(unittest.TestCase):
    """Every code site and every import line keeps its number and its text."""

    def test_every_site_is_pinned_by_number_and_text(self):
        for relative, pinned in SITES.items():
            with self.subTest(reader=relative):
                lines = source_lines(relative)
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer reads the home")

    def test_every_import_line_keeps_its_number(self):
        for relative, pinned in BINDINGS.items():
            with self.subTest(reader=relative):
                lines = source_lines(relative)
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer binds the home")

    def test_every_reader_reads_the_home(self):
        for relative in READERS:
            with self.subTest(reader=relative):
                self.assertIn(NAME, text_of(relative),
                              f"{relative} no longer reads {HOME}.{NAME}")

    def test_the_reader_test_keeps_its_lines(self):
        lines = source_lines(READER_TEST)
        for number, form in sorted(READER_TEST_LINES.items()):
            self.assertEqual(form, lines[number - 1].strip(),
                             f"{READER_TEST}:{number} no longer reads the folder of a"
                             " frame through the store")

    def test_the_prose_of_the_round_keeps_its_lines(self):
        for relative, pinned in PROSE.items():
            with self.subTest(prose=relative):
                lines = source_lines(relative)
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer holds its prose")
                self.assertEqual([], [one for one in analyze() if one.startswith(relative)],
                                 f"the prose of {relative} is no code site of the folder")


class WalkTests(unittest.TestCase):
    """The walk names every second home, of all three shapes, and prose stays silent."""

    def test_no_file_spells_the_folder_name(self):
        offenders = analyze()
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_walk_reads_the_shipped_tree(self):
        """A walk that read no file would pass the case above for no reason."""
        read = [path.relative_to(ROOT).as_posix() for path in walked_files()]
        self.assertGreaterEqual(len(read), FILE_FLOOR, f"the walk read {len(read)} files")
        self.assertIn(HOME, read, "the walk must read the home")
        self.assertEqual([], [one for one in read if one.startswith("src/sam3")],
                         "the walk must skip src/sam3")

    def test_the_walk_finds_the_three_textual_forms(self):
        """A planted copy becomes an offender, in the joined, partition and LIKE shape."""
        offenders = planted_copy(PLANTED, PLANTED_TEXT)
        found = tuple(int(one.split(":")[1]) for one in offenders)
        self.assertEqual(PLANTED_LINES, found,
                         "the walk must name all three textual forms:\n"
                         + "\n".join(offenders))
        self.assertEqual([], [one for one in offenders
                              if not one.startswith("%s:" % PLANTED)], offenders)

    def test_the_walk_ignores_prose(self):
        self.assertEqual([], planted_copy(QUIET, QUIET_TEXT))


if __name__ == "__main__":
    unittest.main()
