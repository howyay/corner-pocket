"""The font build reads the served file list, so the subset cannot drift from the page.

annotator/unified_server.py holds PAGE_FILES at annotator/unified_server.py:200, the
closed list of the files a browser receives.  annotator/fonts/build_fonts.py held its
own hand copy of that list under the name COPY_FILES.  The copy had already drifted:
the build read five files, and `clock-sync.js` was not one of them.

annotator/clock-sync.js:88 draws two Chinese sentences, and they hold 令, 忙 and 繁.
No file of the old copy list held those three characters.  So a page that shows the
timer message asked the CJK subset for a glyph it does not carry, and the browser
fell back to a system face for it.  No case saw the drift: `grep -rn "COPY_FILES"`
found the tuple and its one reader, and nothing else.

The build now derives its list from PAGE_FILES, in `copy_names` at
annotator/fonts/build_fonts.py:49.  This module holds that derivation true, in both
directions, and it holds the coverage of the CJK subset:

* every script the server serves and the two served documents are the files of
  COPY_FILES, so the hand copy cannot come back;
* every CJK character of those files answers the builder's own subset, so a new
  Chinese sentence cannot arrive without its glyph;
* a synthetic font proves the subset path of the builder: the code points of the
  copy survive `copy_codepoints` at annotator/fonts/build_fonts.py:140 and `build`;
* the three names of the build table COMMON_FACES stand in the two stylesheets that
  declare a -common face, and every -common name of those sheets stands in the table,
  so a name that stands in one home only fails this module;
* the shipped .woff2 files are not read.  The woff2 reader needs the `brotli`
  module, and the project virtual environment does not carry it (the build's own
  docstring names the store path it reads from).  This module proves the source
  side of the subset, which is the side a copy list can drift.

Run: ./scripts/pool-test.sh python test_font_coverage_owner
"""
import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BUILD = "annotator/fonts/build_fonts.py"
SERVER = "annotator/unified_server.py"

#: The two files the server hands to a browser as a document.  No path of PAGE_FILES
#: names them: PAGE_ALIASES answers ops.html for `/`, and the route
#: /api/review-template hands out app.html.  Written here as the contract, so a
#: change of the server's shape meets a reader that does not follow it.
SERVED_DOCUMENTS = ("ops.html", "app.html")

#: The files `copy_names` returns today: the scripts of the served list, in the order
#: of that list, and then the two documents.  The case below pins this tuple, because
#: `copy_names` is the one reader of the served list and a wrong rule there is silent.
EXPECTED_COPY = ("app.js", "ops.js", "vision-stage.js", "clock-sync.js", "duration.js",
                 "ops.html", "app.html")

#: The build table of the common-hanzi files: one home of the three names.
TABLE = "COMMON_FACES"

#: The two stylesheets that declare a -common face.  ops.css declares the three faces of
#: the console; board.css declares the one face of the public board, and
#: tests/test_unified_server.py holds that sheet to BOARD_FONTS (a closed row).
SHEETS = ("annotator/ops.css", "annotator/board.css")

#: The three names of the subset, as words.  A count of them drifts; these names do not.
COMMON_NAMES = ("noto-sans-sc-400-common.woff2", "noto-sans-sc-500-common.woff2",
                "noto-serif-sc-500-common.woff2")

#: The word the three homes spell.  The path is not part of it: ops.css writes a rooted
#: url and board.css a relative one, and the file name is the same word in both.
COMMON_SUFFIX = "-common.woff2"

_COMMON_IN_LINE = re.compile(r"[\w.\[\]-]*" + re.escape(COMMON_SUFFIX))


def sheet_common_sites(text, path):
    """Every -common file name of a stylesheet, as (name, "path:line", line text)."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for name in _COMMON_IN_LINE.findall(line):
            hits.append((name, f"{path}:{number}", line.strip()))
    return hits


def table_common_sites(source, path):
    """Every name the build table writes, as (name, "path:line", line text).

    The scan reads the table of the module source with `ast`.  So a -common word in a
    comment or a docstring is not a face the build makes, and the report carries the
    line of the table itself.
    """
    lines = source.splitlines()
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == TABLE
                   for target in node.targets):
            continue
        return [(element.elts[0].value, f"{path}:{element.lineno}",
                 lines[element.lineno - 1].strip()) for element in node.value.elts]
    raise AssertionError(f"{path} must write {TABLE} = (...): the build loops on it in main")


def one_home_only(table_sites, sheet_sites):
    """Every name that stands in one home only, with the site that holds it."""
    table_names = {name for name, _, _ in table_sites}
    sheet_names = {name for name, _, _ in sheet_sites}
    offenders = [f"{site} writes {name}, and no stylesheet declares it: {line}"
                 for name, site, line in table_sites if name not in sheet_names]
    offenders += [f"{site} declares {name}, and the build table {TABLE} does not write it: {line}"
                  for name, site, line in sheet_sites if name not in table_names]
    return offenders


class FontCoverageOwner(unittest.TestCase):
    """One home for the copy list, and a subset that carries every character of it."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT))
        try:
            from annotator.fonts import build_fonts
            from annotator.unified_server import PAGE_FILES
        finally:
            sys.path.remove(str(ROOT))
        cls.build = build_fonts
        #: The served list, read from the module the server answers with, so the two
        #: readers of this case meet at one value.
        cls.served = PAGE_FILES

    def test_the_build_reads_the_served_list_and_no_copy_of_it(self):
        """A second hand copy of the served list is the defect this round removes."""
        self.assertIs(
            self.build.PAGE_FILES, self.served,
            f"{BUILD} must read PAGE_FILES from {SERVER}:190.  An equal tuple fails this case, "
            "because an equal tuple is a copy, and a copy drifts.")
        self.assertEqual(
            tuple(self.build.COPY_FILES), EXPECTED_COPY,
            f"{BUILD} must take COPY_FILES from copy_names: the scripts of the served list and "
            "the two documents, and no other file.")

    def test_every_served_script_is_in_the_copy_list(self):
        """The page list serves a script, so the subset must read its text."""
        served = [path.lstrip("/") for path in self.served if path.endswith(".js")]
        offenders = [name for name in served if name not in self.build.COPY_FILES]
        self.assertEqual(
            [], offenders,
            f"the copy list at {BUILD} misses {len(offenders)} served script(s): "
            + ", ".join(offenders)
            + f".  The served list stands at {SERVER}:190.  A script of that list holds UI "
              "text, so its Chinese characters must reach the CJK subset.")

    def test_the_two_served_documents_are_in_the_copy_list(self):
        """app.html reaches a browser through a route, not through the page list."""
        offenders = [name for name in SERVED_DOCUMENTS if name not in self.build.COPY_FILES]
        self.assertEqual(
            [], offenders,
            f"the copy list at {BUILD} misses {len(offenders)} served document(s): "
            + ", ".join(offenders)
            + ".  Both files render Chinese text, so the build must read both.")

    def test_the_copy_list_holds_no_file_the_server_does_not_serve(self):
        """A stale entry is dead weight, and the list claims that it is UI text."""
        served = {path.lstrip("/") for path in self.served}
        offenders = [name for name in self.build.COPY_FILES
                     if name not in served and name not in SERVED_DOCUMENTS]
        self.assertEqual(
            [], offenders,
            f"the copy list at {BUILD} holds {len(offenders)} name(s) that the server does "
            "not serve: " + ", ".join(offenders) + f".  Read {SERVER}:190 for the served list.")

    def test_a_served_stylesheet_enters_the_copy_list_never(self):
        """The rule of the derivation, shown on a served list that names a stylesheet.

        The case calls `copy_names` with a planted list.  So it proves the rule of the
        function, and it is not a statement about today's list.
        """
        planted = ("/", "/app.css", "/app.js", "/ops.css", "/ops.js", "/vision-stage.js",
                   "/clock-sync.js", "/duration.js", "/new.css")
        original = self.build.PAGE_FILES
        self.build.PAGE_FILES = planted
        try:
            names = self.build.copy_names()
        finally:
            self.build.PAGE_FILES = original
        self.assertEqual(EXPECTED_COPY, names,
                         "copy_names takes the scripts and the documents, and nothing else")
        for name in names:
            self.assertFalse(name.endswith(".css"),
                             f"{name} is a stylesheet, and a stylesheet holds no UI text")

    def test_every_cjk_character_of_the_copy_answers_the_builders_subset(self):
        """The subset is the answer.  A character outside it falls back to a system face."""
        subset = self.build.copy_codepoints()
        offenders = []
        for name in self.build.COPY_FILES:
            text = (self.build.ANNOTATOR / name).read_text(encoding="utf-8")
            missing = sorted({ch for ch in text
                              if 0x3400 <= ord(ch) <= 0x9FFF and ord(ch) not in subset})
            if missing:
                offenders.append(f"{name} holds {''.join(missing)}")
        self.assertEqual(
            [], offenders,
            f"the CJK subset of {BUILD} does not answer every character of the copy: "
            + "; ".join(offenders) + ".  Add the file of the character to COPY_FILES.")

    def test_the_timer_sentences_of_clock_sync_reach_the_subset(self):
        """The three characters of the round-97 drift, named one by one."""
        text = (self.build.ANNOTATOR / "clock-sync.js").read_text(encoding="utf-8")
        subset = self.build.copy_codepoints()
        for character, line in (("令", 88), ("忙", 89), ("繁", 89)):
            with self.subTest(character=character):
                self.assertIn(character, text,
                              f"annotator/clock-sync.js:{line} must draw {character}")
                self.assertIn(ord(character), subset,
                              f"{character} of annotator/clock-sync.js:{line} has no answer in "
                              f"the subset of {BUILD}.  The browser draws it with a system face.")

    def test_a_synthetic_font_keeps_every_code_point_of_the_copy(self):
        """The real subset path, on a font this case builds: no store, no download.

        The case runs the steps of `build` at annotator/fonts/build_fonts.py:163 with
        the option object of the build.  It writes a .ttf, because the woff2 writer
        needs the `brotli` module and the project virtual environment does not carry
        it.  The flavor is the only step of `build` that the case does not run.
        """
        from fontTools import subset
        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.ttGlyphPen import TTGlyphPen
        from fontTools.ttLib import TTFont
        from tempfile import TemporaryDirectory

        points = self.build.copy_codepoints()
        glyphs = [".notdef"] + [f"u{code:04X}" for code in sorted(points)]
        builder = FontBuilder(1000, isTTF=True)
        builder.setupGlyphOrder(glyphs)
        builder.setupCharacterMap({code: f"u{code:04X}" for code in points})
        builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in glyphs})
        builder.setupHorizontalMetrics({name: (500, 0) for name in glyphs})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupNameTable({"familyName": "CoverageProbe", "styleName": "Regular"})
        builder.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                         usWinAscent=800, usWinDescent=200)
        builder.setupPost()
        builder.setupMaxp()
        with TemporaryDirectory(prefix="font-coverage-") as folder:
            source = Path(folder) / "probe.ttf"
            builder.font.save(str(source))
            options = self.build.options()
            options.flavor = None
            sub = subset.Subsetter(options)
            sub.populate(unicodes=sorted(points))
            out = Path(folder) / "subset.ttf"
            font = TTFont(str(source))
            sub.subset(font)
            font.save(str(out))
            cmap = TTFont(str(out), lazy=True).getBestCmap()
        self.assertEqual(len(points), len(cmap),
                         "the subset must carry one glyph per code point of the copy")
        for character in "令忙繁":
            with self.subTest(character=character):
                self.assertIn(ord(character), cmap,
                              f"the subset dropped {character}, so the timer sentence of "
                              "annotator/clock-sync.js cannot draw it")

    def test_the_build_table_and_the_two_stylesheets_name_one_set_of_common_files(self):
        """One fact, three homes: COMMON_FACES, ops.css and board.css.

        A rename in the build table alone was silent.  The old committed file stays on
        disk, so a case on the file names of the store still passes.  This case reports
        every name that stands in one home only, with the path and the line of the site
        that holds it.
        """
        source = (ROOT / BUILD).read_text(encoding="utf-8")
        table = table_common_sites(source, BUILD)
        self.assertEqual(
            [name for name, _, _ in table], [row[0] for row in self.build.COMMON_FACES],
            f"{BUILD} must resolve {TABLE} to the names its own source writes at the table")
        sheets = [site for path in SHEETS
                  for site in sheet_common_sites((ROOT / path).read_text(encoding="utf-8"), path)]
        offenders = one_home_only(table, sheets)
        self.assertEqual(
            [], offenders,
            f"the names of {BUILD} ({TABLE}) and the -common names of {SHEETS[0]} and "
            f"{SHEETS[1]} must be one set: " + "; ".join(offenders)
            + ".  A table name that no stylesheet declares downloads nothing, and a stylesheet "
              "name that the table does not write serves no file.")

    def test_the_common_scan_finds_the_three_real_names(self):
        """An empty scan cannot pass the case above: the three real names stand in the text.

        The case names the words, not a count of them.  It also holds each stylesheet to at
        least one -common face, so a sheet that loses every one of them is caught here.
        """
        table = {name for name, _, _ in table_common_sites(
            (ROOT / BUILD).read_text(encoding="utf-8"), BUILD)}
        sheets = {}
        for path in SHEETS:
            found = {name for name, _, _ in sheet_common_sites(
                (ROOT / path).read_text(encoding="utf-8"), path)}
            self.assertTrue(found, f"{path} declares no -common face, so the scan is empty")
            sheets[path] = found
        for name in COMMON_NAMES:
            with self.subTest(name=name):
                self.assertIn(name, table, f"{BUILD} ({TABLE}) must write {name}")
                self.assertTrue(any(name in found for found in sheets.values()),
                                f"no stylesheet of {', '.join(SHEETS)} declares {name}")

    def test_a_common_name_that_stands_in_one_home_only_is_reported(self):
        """The planted case: the report rule catches a name of one home in both directions.

        The plants are text, so the module resolves every value.  The last assertion shows
        the rule on today's files, so the rule is not "always red".
        """
        planted_table = table_common_sites(
            f"{TABLE} = (\n"
            "    ('planted-in-the-table-only-common.woff2', 'x/Planted[wght].ttf', 400),\n"
            ")\n", BUILD)
        self.assertEqual([("planted-in-the-table-only-common.woff2", f"{BUILD}:2")],
                         [(name, site) for name, site, _ in planted_table])
        offenders = one_home_only(planted_table, [])
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("planted-in-the-table-only-common.woff2", offenders[0])
        self.assertIn(f"{BUILD}:2", offenders[0])

        planted_sheet = sheet_common_sites(
            "@font-face{font-family:'Noto Sans SC';src:url(/fonts/"
            "planted-in-the-sheet-only-common.woff2) format('woff2')}\n", SHEETS[0])
        offenders = one_home_only([], planted_sheet)
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("planted-in-the-sheet-only-common.woff2", offenders[0])
        self.assertIn(f"{SHEETS[0]}:1", offenders[0])

        table = table_common_sites((ROOT / BUILD).read_text(encoding="utf-8"), BUILD)
        sheets = [site for path in SHEETS
                  for site in sheet_common_sites((ROOT / path).read_text(encoding="utf-8"), path)]
        self.assertEqual([], one_home_only(table, sheets),
                         "the two real homes must report no name of one home only")


if __name__ == "__main__":
    unittest.main()
