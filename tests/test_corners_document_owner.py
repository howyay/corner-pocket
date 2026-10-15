"""The scan cloth quad document has one home: ``src/calib_segments.py``.

Round 115 walked the document name ``corners.json``.  ``git grep -F "corners.json"`` over
``src``, ``annotator``, ``tools`` and ``scripts`` answered 17 lines in eight files, with
five live code sites:

1. ``src/calib_segments.py:221``  ``SCAN_CORNERS``, which embedded the name in the whole
   path ``"out/scan30/corners.json"``;
2. ``src/scan_events.py:136``     the reader, ``json.load(open(out_dir / "corners.json"))``;
3. ``src/scan_events.py:289``     the writer, ``json.dump(..., open(out_dir / "corners.json", "w"))``;
4. ``src/eval_faces.py:175``      ``path = REPO / "out" / name / "corners.json"``;
5. ``annotator/unified_server.py:1594`` ``_EVENT_QUADS = (('corners.json', 'scan cloth quad'),)``,
   read at ``:1382`` by the events document walk.

A rename of the file then needed one edit at each site, and a site that missed the edit
read a path that no longer exists.  The home is the module that already owns the scan
corners path::

    src/calib_segments.py:220: CORNERS_DOCUMENT = "corners.json"

Round 115 put the name above :data:`SCAN_CORNERS` and rewrote sites 2 to 5 to read it.
Every site keeps its shape, and the events document keeps its tuple and its human label.

The path below the name composes it with the scan folder home, and the guard of the path
moved with it.  ``tests/test_scan_corners_owner.py`` (``test_the_owner_states_the_name_once``)
asked for exactly one code string of ``src/calib_segments.py`` that equals ``SCAN_CORNERS``,
so a composed path answers no such string.  Round 115 changed that case to read every kind
of finding and to count the name instead.  Measured: with the whole literal the owner
answered one ``'spells'`` finding; with the composition it answers none, and the case now
holds no finding and one ``CORNERS_DOCUMENT = "`` line.

Every site of ``fixed_corners.json`` is a DIFFERENT document: the calibration corners
spec of the highlight, owned by ``tests/test_corners_spec_owner.py``.  That name holds
the bare name as its tail and is never equal to it, so the walk never flags it.  It
stays, and this guard pins each site with its reason:

* ``src/calib_segments.py:183``  ``CORNERS_SPEC`` states the spec document, not this one.
* ``src/calib_segments.py:202`` and ``src/calib_mapping_audit.py:422`` are docstring
  sentences, outside the walk.
* ``src/calib_mapping_audit.py:569`` prints the highlight reference of the audit run.
* ``src/eval_table_detect.py:30`` is a docstring of the table detector.

The walk below reads every python file of ``src/`` and ``annotator/``, skips ``src/sam3/``
and the byte-code trees, drops the string node of a module, class or function docstring,
and answers every code constant equal to the bare name that is neither the home nor a
pinned line.  Two floors keep a walk that read nothing from passing in silence.

Run: ``./scripts/pool-test.sh python test_corners_document_owner``
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from src import calib_segments  # noqa: E402
from _shipped import code_strings  # noqa: E402

#: The home module, the name it holds the document under, and the value of that name.
HOME = "src/calib_segments.py"
DOCUMENT_NAME = "CORNERS_DOCUMENT"
DOCUMENT_VALUE = "corners.json"
#: The path the checkout reads, and the module-level name that answers it.
PATH_NAME = "SCAN_CORNERS"
PATH_VALUE = "out/scan30/corners.json"
#: The two lines of the home, pinned by number and text.  They are the last pinned
#: lines of the module: tests/test_quad_shape_sentence_owner.py pins the two raises at
#: :555 and :559, so a line added above them moves those numbers.
HOME_LINE = 220
HOME_FORM = '%s = "%s"' % (DOCUMENT_NAME, DOCUMENT_VALUE)
PATH_LINE = 221
PATH_FORM = 'SCAN_CORNERS = f"out/{STATIC_OUT[BUILT_IN_DATASET]}/{CORNERS_DOCUMENT}"'
#: The modules that read the name home instead of spelling it.
READERS = ("src/scan_events.py", "src/eval_faces.py", "annotator/unified_server.py")
#: The directories the walk reads, the subtree it skips, and the floors that keep a
#: vacuous walk from passing.
WALKED = ("src/**/*.py", "annotator/*.py")
SKIP = ("src/sam3",)
FILE_FLOOR = 200
SCANNED_FLOOR = 100
#: The bare name, spelled once here so a case can measure the home against it.
WORDS = (DOCUMENT_VALUE,)
#: The sites this guard accepts as a copy of the bare name, as the reason each one holds
#: it.  The home states the name, so it is never an offender.
PINNED = {
    HOME: (),  # the home itself is the owner, never an offender
}
#: The sites of the other document, ``fixed_corners.json``, whose owner is
#: tests/test_corners_spec_owner.py.  Each line keeps its reason in the docstring.
OTHER_DOCUMENT = "fixed_corners.json"
OTHER_GUARD = "tests/test_corners_spec_owner.py"
OTHER_PINNED = {
    "src/calib_segments.py": (183, 202),
    "src/calib_mapping_audit.py": (422, 569),
    "src/eval_table_detect.py": (30,),
}
#: The lines that name the document in prose, outside the walk.  A rename of the file
#: must reach them too, so each one is pinned by number.
PROSE = {
    "annotator/unified_server.py": (457, 1585),
    "src/calib_mapping_audit.py": (9, 363, 394),
    "src/document_stamp.py": (86,),
    "src/sam3_artifact.py": (11,),
}
#: Planted modules of the honesty cases.
PLANTED = "src/planted_corners.py"
PLANTED_COPY_LINE = 6
PLANTED_TEXT = ('"""A planted module that names corners.json in its docstring."""\n'
                "\n"
                "\n"
                "def row():\n"
                '    """The docstring names the document in words, which is no constant."""\n'
                '    return "%s"\n' % DOCUMENT_VALUE)
QUIET = "src/quiet_corners.py"
QUIET_TEXT = ('"""A planted module that names corners.json in its docstring."""\n'
              "\n"
              "\n"
              "def row():\n"
              '    """The docstring names the document in words, which is no constant."""\n'
              "    return 1\n")
#: The probe that reads the home in a fresh interpreter of this venv.
PROBE = ("import src.calib_segments as module; "
         "print(repr(module.%s), repr(module.%s))" % (DOCUMENT_NAME, PATH_NAME))


def source_lines(relative: str) -> list:
    """The lines of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8").splitlines()


def walked_files() -> list:
    """Every walked python file, the generated subtree left out."""
    found = sorted(path for pattern in WALKED for path in ROOT.glob(pattern)
                   if "__pycache__" not in path.parts
                   and not any(part in SKIP for part in path.relative_to(ROOT).parts))
    return found


def planted_copy(relative: str, text: str) -> list:
    """Write one planted module, run the walk, and remove it."""
    path = ROOT / relative
    path.write_text(text, encoding="utf-8")
    try:
        return analyze()
    finally:
        path.unlink()


def analyze() -> list:
    """Every walked code constant of the bare name that is no home and no pin."""
    offenders = []
    for path in walked_files():
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, value in code_strings(tree):
            if value not in WORDS:
                continue
            if relative == HOME or line in PINNED.get(relative, ()):
                continue
            offenders.append("%s:%d: %r spells the scan cloth quad document; read %s.%s"
                             % (relative, line, value, HOME, DOCUMENT_NAME))
    return offenders


class HomeTests(unittest.TestCase):
    """The home holds the bare name, and the four sites read it."""

    def test_the_home_names_the_shipped_document(self):
        answer = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.splitlines()
        self.assertEqual(answer[0], "%r %r" % (DOCUMENT_VALUE, PATH_VALUE))

    def test_the_home_line_carries_the_shipped_name(self):
        self.assertEqual(source_lines(HOME)[HOME_LINE - 1].strip(), HOME_FORM)
        self.assertLessEqual(HOME_LINE, 220, "the pinned lines of the scan corners module moved")

    def test_the_path_composes_the_name_and_the_folder(self):
        # The reason is in the module docstring: the owner composes the path from this
        # home's name and the scan folder home of src/datasets.py, and the guard of the
        # path now reads every kind of finding, so the owner holds no whole-path literal.
        self.assertEqual(source_lines(HOME)[PATH_LINE - 1].strip(), PATH_FORM)
        self.assertLessEqual(PATH_LINE, 221, "the pinned lines of the scan corners module moved")

    def test_every_reader_reads_the_name_home(self):
        for relative in READERS:
            text = "\n".join(source_lines(relative))
            self.assertTrue(DOCUMENT_NAME in text,
                            "%s no longer reads %s of %s" % (relative, DOCUMENT_NAME, HOME))

    def test_the_other_document_keeps_its_owner(self):
        self.assertEqual(calib_segments.CORNERS_SPEC["file"], OTHER_DOCUMENT,
                         "CORNERS_SPEC no longer names the calibration corners spec")
        self.assertTrue((ROOT / OTHER_GUARD).is_file(),
                        "%s no longer guards %s" % (OTHER_GUARD, OTHER_DOCUMENT))


class WalkTests(unittest.TestCase):
    """The walk names every copy that is no home and no pin."""

    def test_no_file_spells_the_bare_name(self):
        offenders = analyze()
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_walk_reads_the_shipped_tree(self):
        files = walked_files()
        self.assertGreaterEqual(len(files), FILE_FLOOR)
        parsed = 0
        for path in files:
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            parsed += 1
        self.assertGreaterEqual(parsed, SCANNED_FLOOR)

    def test_the_walk_finds_a_planted_copy(self):
        offenders = planted_copy(PLANTED, PLANTED_TEXT)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("%s:%d" % (PLANTED, PLANTED_COPY_LINE)),
                        offenders[0])

    def test_the_walk_ignores_prose(self):
        self.assertEqual([], planted_copy(QUIET, QUIET_TEXT))

    def test_every_pin_names_a_live_line(self):
        for relative, lines in PINNED.items():
            text = source_lines(relative)
            for line in lines:
                self.assertIn(WORDS[0], text[line - 1],
                              "%s:%d no longer spells the document name" % (relative, line))
        for relative, lines in OTHER_PINNED.items():
            text = source_lines(relative)
            for line in lines:
                self.assertIn(OTHER_DOCUMENT, text[line - 1],
                              "%s:%d no longer spells %s" % (relative, line, OTHER_DOCUMENT))

    def test_the_prose_sites_still_name_the_document(self):
        for relative, lines in PROSE.items():
            text = source_lines(relative)
            for line in lines:
                self.assertIn(DOCUMENT_VALUE, text[line - 1],
                              "%s:%d no longer names the document in prose" % (relative, line))


if __name__ == "__main__":
    unittest.main()
