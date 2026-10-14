"""The calibration side-mapping keys have one home, and four modules read it.

A refinement of one quad reports the boundary of each side, and four keys carry
that report into the segment recording.  Round 109 found the words written in
four live modules:

* ``src/table_refine.py`` - the refinement writes each key into the info dict it
  answers: the count of verified sides, the per-side codes, and the per-side mask
  offset;
* ``src/calib_segment_measure.py`` - the measurement copies the refinement report
  into its own artifact;
* ``src/calib_segment_fit.py`` - the fit reads the report back and writes its own
  witnesses;
* ``src/calib_mapping_audit.py`` - the audit reads the report of both mappings.

No case named a key.  ``git grep -F verified_sides -- tests/`` answered only rows
built by hand, so a rename of the key stayed silent in every reader.

The home is ``src/calib_segments.py``::

    VERIFIED_SIDES_KEY = "verified_sides"

That module already describes the calibration recording: it owns
``CORNERS_SPEC``, ``STATIC_REFERENCES`` and the segment artifact name.  It holds
no top-level python import of its own, so every writer and every reader of the
row takes the name at the top of its module and no cycle starts.

Why a home and not four literals.  The keys cross a module boundary: one module
writes the row and three modules read it.  A rename in the writer alone leaves
three readers looking for a key that no row carries, and a reader that finds
nothing answers None where it answered a count before.  A name that four modules
import cannot drift.

The served contract does not change.  Each value stays byte-identical, so the
documents on disk keep their keys.  ``annotator/app.js:1167`` and
``annotator/vision-stage.js:328`` read ``verified_sides`` of a quad of the page
and cannot import a python name, so this module holds those two lines too: a
moved value reddens the page walk.

What this case does not see
--------------------------
* ``src/eval_events.py`` writes the same keys and is owned by another writer this
  round.  Plus ``src/event_gates.py:523`` and ``src/frame_inference.py:163`` read
  the key of the row.  Those eight sites stay exactly as they are, and the walk
  below names each one: a new bare site fails the walk, and a lost one reddens
  the document of the round;
* ``supported_sides`` and ``mask_offsets_px`` repeat the same story: two writers
  each, and no home.  They are the next family for a round with free hands;
* a key that moves in the home moves every reader at once, and the case on the
  binding measures that in the run-time modules instead of against the text.

Run: ``./scripts/pool-test.sh python test_calib_mapping_keys_owner``

Measured 2026-10-14, Python 3.14.6: the walk reads about 300 python files under
``src/``, ``annotator/``, ``tools/`` and ``scripts/`` in about 3 s; the four
run-time probes take about 2 s.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The home module.
HOME = "src/calib_segments.py"
#: Every shipped key, the name of the home that holds it, and its value.  The
#: guard spells each value once, so a case can pin it against the home.
KEYS = {
    "VERIFIED_SIDES_KEY": "verified_sides",
    "UNVERIFIED_SIDES_KEY": "unverified_sides",
    "INHERITED_SIDES_KEY": "inherited_sides",
    "MASK_OFFSET_PX_KEY": "mask_offset_px",
}
#: The line of every home statement, at the state the home landed in.  A moved
#: home must restate this map and the report of the round that moved it.
HOME_LINES = {
    "VERIFIED_SIDES_KEY": 386,
    "UNVERIFIED_SIDES_KEY": 387,
    "INHERITED_SIDES_KEY": 388,
    "MASK_OFFSET_PX_KEY": 389,
}
#: The shape of a home statement of this house.
HOME_FORM = '%s = "%s"'
#: A module-level name in upper case, the shape of a constant of this house.
CONSTANT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
#: The line regex of the definition of one home name.
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*\s*=")
#: Every live site of each home name, as ``(path, line, kind, name)``.  The kind
#: is ``dict`` for a key of a written row, ``get`` for a lookup that reads a row
#: back, and ``sub`` for a lookup with a subscript.  A moved, a new or a lost
#: site must restate itself here.
SITES = (
    # The refinement writes every key, and reads two of them back.
    ("src/table_refine.py", 758, "get", "VERIFIED_SIDES_KEY"),
    ("src/table_refine.py", 850, "dict", "MASK_OFFSET_PX_KEY"),
    ("src/table_refine.py", 867, "sub", "MASK_OFFSET_PX_KEY"),
    ("src/table_refine.py", 919, "sub", "MASK_OFFSET_PX_KEY"),
    ("src/table_refine.py", 921, "sub", "MASK_OFFSET_PX_KEY"),
    ("src/table_refine.py", 924, "sub", "MASK_OFFSET_PX_KEY"),
    ("src/table_refine.py", 928, "sub", "MASK_OFFSET_PX_KEY"),
    ("src/table_refine.py", 955, "dict", "VERIFIED_SIDES_KEY"),
    ("src/table_refine.py", 956, "dict", "UNVERIFIED_SIDES_KEY"),
    ("src/table_refine.py", 957, "dict", "INHERITED_SIDES_KEY"),
    ("src/table_refine.py", 964, "dict", "UNVERIFIED_SIDES_KEY"),
    ("src/table_refine.py", 1013, "dict", "UNVERIFIED_SIDES_KEY"),
    ("src/table_refine.py", 1013, "dict", "VERIFIED_SIDES_KEY"),
    ("src/table_refine.py", 1014, "dict", "INHERITED_SIDES_KEY"),
    # The measurement copies the report into its own artifact.
    ("src/calib_segment_measure.py", 223, "get", "UNVERIFIED_SIDES_KEY"),
    ("src/calib_segment_measure.py", 224, "get", "INHERITED_SIDES_KEY"),
    ("src/calib_segment_measure.py", 232, "dict", "MASK_OFFSET_PX_KEY"),
    ("src/calib_segment_measure.py", 232, "get", "MASK_OFFSET_PX_KEY"),
    ("src/calib_segment_measure.py", 275, "get", "VERIFIED_SIDES_KEY"),
    ("src/calib_segment_measure.py", 286, "get", "VERIFIED_SIDES_KEY"),
    # The fit reads the report and writes its own witnesses.
    ("src/calib_segment_fit.py", 78, "get", "MASK_OFFSET_PX_KEY"),
    ("src/calib_segment_fit.py", 79, "sub", "MASK_OFFSET_PX_KEY"),
    ("src/calib_segment_fit.py", 95, "sub", "VERIFIED_SIDES_KEY"),
    ("src/calib_segment_fit.py", 191, "sub", "MASK_OFFSET_PX_KEY"),
    ("src/calib_segment_fit.py", 192, "get", "MASK_OFFSET_PX_KEY"),
    ("src/calib_segment_fit.py", 194, "dict", "VERIFIED_SIDES_KEY"),
    ("src/calib_segment_fit.py", 194, "get", "VERIFIED_SIDES_KEY"),
    ("src/calib_segment_fit.py", 195, "get", "UNVERIFIED_SIDES_KEY"),
    ("src/calib_segment_fit.py", 196, "get", "INHERITED_SIDES_KEY"),
    ("src/calib_segment_fit.py", 202, "sub", "VERIFIED_SIDES_KEY"),
    ("src/calib_segment_fit.py", 237, "sub", "MASK_OFFSET_PX_KEY"),
    # The audit reads the report of both mappings.
    ("src/calib_mapping_audit.py", 274, "dict", "VERIFIED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 274, "get", "VERIFIED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 275, "dict", "INHERITED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 275, "get", "INHERITED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 276, "get", "VERIFIED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 277, "get", "INHERITED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 279, "get", "UNVERIFIED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 281, "get", "INHERITED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 282, "get", "MASK_OFFSET_PX_KEY"),
    ("src/calib_mapping_audit.py", 461, "get", "UNVERIFIED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 464, "get", "MASK_OFFSET_PX_KEY"),
    ("src/calib_mapping_audit.py", 465, "sub", "MASK_OFFSET_PX_KEY"),
    ("src/calib_mapping_audit.py", 588, "get", "INHERITED_SIDES_KEY"),
    ("src/calib_mapping_audit.py", 588, "get", "VERIFIED_SIDES_KEY"),
)
#: The module each reader imports the home names from.
IMPORT_SOURCE = "src.calib_segments"
#: The line of every home statement, as ``(path, line)``.  The walk allows the
#: value on these lines and on no other line of the tree.
ALLOWED_HOME_LITERALS = tuple((HOME, line) for line in sorted(HOME_LINES.values()))
#: Every bare spelling of a key outside this round's scope, as
#: ``(path, line, value)``.  They stay byte-identical, and the walk names each
#: one: a new bare site fails the walk, and a lost one reddens this document.
#: A later round that takes these sites to the home must delete its row here.
OUTSIDE_LITERALS = (
    ("src/eval_events.py", 452, "unverified_sides"),
    ("src/eval_events.py", 453, "inherited_sides"),
    ("src/eval_events.py", 456, "verified_sides"),
    ("src/eval_events.py", 457, "inherited_sides"),
    ("src/eval_events.py", 459, "verified_sides"),
    ("src/eval_events.py", 460, "verified_sides"),
    ("src/event_gates.py", 522, "verified_sides"),
    ("src/frame_inference.py", 163, "verified_sides"),
)
#: The two javascript readers of the page.  No python name reaches a page, so
#: this module holds their lines and their text.
PAGES = (("annotator/app.js", 1167, "verified_sides"),
         ("annotator/vision-stage.js", 328, "verified_sides"))
#: What a page line must hold: the key, read as a property of the quad.
PAGE_READS = "quad?.%s"
#: The directories the anti-home walk reads, and the floor that fails a walk
#: which reads no file at all.
WALK_DIRS = ("src", "annotator", "tools", "scripts")
MIN_WALK_FILES = 200
#: The modules whose run-time binding this case measures in a fresh interpreter.
BIND_MODULES = ("src.table_refine", "src.calib_segment_fit", "src.calib_mapping_audit",
                "src.calib_segment_measure")
#: The pair a probe prints, and the template that names one module.
KEYS_PROBE = ", ".join("m.%s" % name for name in KEYS)
BIND_PROBE = "import %s as m; print(repr((%s,)))" % ("%s", KEYS_PROBE)
#: The lines that stand outside the home, once read.  The walk fills this map.
stripped = {}


def source_text(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(relative: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return "%s:%d: %s  <- %s" % (relative, line, (text or "").strip(), why)


def reported(relative: str, line: int, why: str) -> str:
    """One offender of a pinned line, with the text of that line."""
    lines = source_lines(relative)
    text = lines[line - 1] if 0 < line <= len(lines) else ""
    return report(relative, line, text, why)


def home_sites() -> list:
    """Every line of the home module that assigns a module-level constant."""
    return [(number, text) for number, text in enumerate(source_lines(HOME), start=1)
            if NAME_RE.match(text)]


def home_value(name: str) -> str:
    """The value of one home constant, read from the syntax tree of the home.

    The read is a read of the shipped text and not of an import: the home module
    reaches cv2 through its function bodies, and this guard must not pull a heavy
    library into its own process to answer a string.  A case proves the run-time
    binding with fresh interpreters instead.
    """
    for node in ast.walk(ast.parse(source_text(HOME), filename=HOME)):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return ""


def imported_names(text: str, where: str, module: str) -> list:
    """Every local name one module imports from another, as ``(line, name)``."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                found.append((node.lineno, alias.asname or alias.name))
    return sorted(found)


def name_sites(text: str, where: str) -> list:
    """Every site of a home name, as ``(line, kind, name)``.

    A site is a dict key of a written row, a lookup that reads a row back, or a
    lookup with a subscript.  A comment or a docstring that names the key is no
    site of it, so this walk is the honest count of the wiring.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None:
                    written = ast.unparse(key)
                    if written in KEYS:
                        found.append((key.lineno, "dict", written))
        elif isinstance(node, ast.Call):
            if node.args:
                written = ast.unparse(node.args[0])
                if written in KEYS:
                    found.append((node.args[0].lineno, "get", written))
        elif isinstance(node, ast.Subscript):
            written = ast.unparse(node.slice)
            if written in KEYS:
                found.append((node.slice.lineno, "sub", written))
    return sorted(set(found))


def literal_sites(text: str, where: str) -> list:
    """Every string constant of one module whose value is a shipped key."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value in KEYS.values():
            found.append((node.lineno, node.value))
    return sorted(set(found))


def walked() -> list:
    """Every python file of the shipped packages, without the caches."""
    files = []
    for folder in WALK_DIRS:
        files.extend(sorted((ROOT / folder).rglob("*.py")))
    return [path for path in files if "__pycache__" not in path.parts]


def run_probe(module: str) -> str:
    """The keys one module answers at run time, from a fresh interpreter."""
    code = BIND_PROBE % module
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=600)
    if done.returncode != 0:
        raise AssertionError("the probe of %s failed:\n%s" % (module, done.stderr))
    return done.stdout.strip()


class HomeTests(unittest.TestCase):
    """The home name, its value, its line and its run-time binding."""

    def test_every_key_has_one_home_statement(self):
        """One assignment of each home name, and no other assignment of it."""
        offenders = []
        for name, value in sorted(KEYS.items()):
            form = HOME_FORM % (name, value)
            sites = [(number, text) for number, text in home_sites()
                     if re.match(r"^%s\s*=" % name, text)]
            if len(sites) != 1:
                offenders.append(report(HOME, sites[0][0] if sites else 1,
                                        sites[0][1] if sites else "",
                                        "%s stands %d times; the home holds it once"
                                        % (name, len(sites))))
                continue
            number, text = sites[0]
            if form not in text:
                offenders.append(report(HOME, number,
                                        text, "the line does not assign %r to %s"
                                        % (value, name)))
        self.assertEqual([], offenders,
                         "a home statement of a calibration key is wrong:\n"
                         + "\n".join(offenders))

    def test_the_home_lines_are_the_ones_the_report_names(self):
        """The case that pins each home at ``path:line``."""
        offenders = []
        lines = source_lines(HOME)
        for name, number in sorted(HOME_LINES.items()):
            text = lines[number - 1] if 0 < number <= len(lines) else ""
            if name not in text:
                offenders.append(report(HOME, number, text,
                                        "%s is no longer at line %d; a move must "
                                        "restate HOME_LINES" % (name, number)))
        self.assertEqual([], offenders,
                         "a home line moved:\n" + "\n".join(offenders))

    def test_the_home_holds_the_value_of_every_shipped_key(self):
        """The value of each name, read from the home module itself."""
        offenders = []
        for name, value in sorted(KEYS.items()):
            found = home_value(name)
            if found != value:
                offenders.append(reported(HOME, HOME_LINES[name],
                                          "%s answers %r, and the shipped key is %r"
                                          % (name, found, value)))
        self.assertEqual([], offenders,
                         "a key of the home is not the shipped key:\n" + "\n".join(offenders))

    def test_the_home_names_can_be_the_keys_of_a_row(self):
        """A constant name is an identifier, and a key of a row is a string."""
        for name, value in sorted(KEYS.items()):
            self.assertTrue(CONSTANT_NAME_RE.match(name), "%s is not a constant name" % name)
            self.assertTrue(value.isidentifier(), "%r is not a valid key of a row" % value)

    def test_the_home_binds_every_name_at_run_time(self):
        """Every reader answers the keys when a fresh interpreter imports it."""
        expected = str(tuple(KEYS[name] for name in KEYS))
        for module in BIND_MODULES:
            self.assertEqual(expected, run_probe(module),
                             "%s does not answer %s when a reader imports it"
                             % (module, expected))


class ReaderTests(unittest.TestCase):
    """Four modules write and read the keys through the home."""

    def test_every_reader_imports_the_home(self):
        """Each of the four modules takes every home name at its top."""
        offenders = []
        for relative in sorted({path for path, _line, _kind, _name in SITES}):
            text = source_text(relative)
            names = {name for _line, name in imported_names(text, relative, IMPORT_SOURCE)}
            missing = sorted(set(KEYS) - names)
            if missing:
                offenders.append(report(relative, 1, source_lines(relative)[0],
                                        "the module imports no %s from %s"
                                        % (", ".join(missing), IMPORT_SOURCE)))
        self.assertEqual([], offenders,
                         "a reader does not import the home:\n" + "\n".join(offenders))

    def test_the_live_sites_are_the_ones_the_report_names(self):
        """Every pinned site stands, and it is the kind the report names."""
        offenders = []
        for relative, line, kind, name in SITES:
            found = name_sites(source_text(relative), relative)
            if (line, kind, name) not in found:
                offenders.append(reported(relative, line,
                                          "the pinned site (%d, %s, %s) is gone; the "
                                          "live sites are %s" % (line, kind, name, found)))
        self.assertEqual([], offenders,
                         "a site of a calibration key moved:\n" + "\n".join(offenders))

    def test_every_site_of_a_reader_is_a_pinned_site(self):
        """A site that is not pinned is a second home in the making."""
        pinned = {(path, line, kind, name) for path, line, kind, name in SITES}
        offenders = []
        for relative in sorted({path for path, _line, _kind, _name in SITES}):
            for site in name_sites(source_text(relative), relative):
                if (relative,) + site not in pinned:
                    offenders.append(reported(relative, site[0],
                                              "the site is not in SITES; a new site of "
                                              "a key must restate itself"))
        self.assertEqual([], offenders,
                         "a live site of a calibration key is not pinned:\n"
                         + "\n".join(offenders))

    def test_no_reader_spells_a_key_as_a_literal(self):
        """A bare literal in a reader is the copy the home replaces."""
        offenders = []
        for relative in sorted({path for path, _line, _kind, _name in SITES}):
            for line, value in literal_sites(source_text(relative), relative):
                offenders.append(reported(relative, line,
                                          "%r is a bare copy of the key; read the name "
                                          "of %s" % (value, HOME)))
        self.assertEqual([], offenders,
                         "a reader spells a calibration key itself:\n" + "\n".join(offenders))

    def test_the_walk_reads_a_planted_copy(self):
        """A planted literal is reported as ``path:line`` with its text."""
        planted = ('def row(info):\n'
                   '    return {"verified_sides": info.get("verified_sides")}\n')
        offenders = literal_sites(planted, "src/planted.py")
        self.assertEqual([(2, "verified_sides")], offenders,
                         "the walk answered %s" % (offenders,))
        found = report("src/planted.py", 2,
                       '    return {"verified_sides": info.get("verified_sides")}',
                       "'verified_sides' is a bare copy of the key")
        self.assertEqual('src/planted.py:2: return {"verified_sides": '
                         'info.get("verified_sides")}  <- \'verified_sides\' is a bare '
                         'copy of the key', found)

    def test_the_walk_accepts_the_home_spelling(self):
        """The name of the home is no literal, and it is a dict site."""
        planted = ('def row(info):\n'
                   '    return {VERIFIED_SIDES_KEY: info.get(VERIFIED_SIDES_KEY)}\n')
        self.assertEqual([], literal_sites(planted, "src/planted.py"),
                         "the home spelling counts as a bare literal")
        self.assertEqual([(2, "dict", "VERIFIED_SIDES_KEY"),
                          (2, "get", "VERIFIED_SIDES_KEY")],
                         name_sites(planted, "src/planted.py"))

    def test_the_walk_accepts_a_subscript_of_the_home_name(self):
        """A lookup with a subscript is a site of the third kind."""
        planted = ('def row(info):\n'
                   '    return info[MASK_OFFSET_PX_KEY]\n')
        self.assertEqual([(2, "sub", "MASK_OFFSET_PX_KEY")],
                         name_sites(planted, "src/planted.py"))


class WalkTests(unittest.TestCase):
    """The walk of the shipped packages, and the two pages."""

    def walk_outside_lines(self):
        """Read every named line outside the home, and keep its text."""
        offenders = []
        for relative, line, value in OUTSIDE_LITERALS:
            lines = source_lines(relative)
            text = lines[line - 1] if 0 < line <= len(lines) else ""
            stripped[(relative, line)] = text.strip()
            if value not in text:
                offenders.append(report(relative, line, text,
                                        "%r is no longer at this line; a move must "
                                        "restate OUTSIDE_LITERALS" % value))
        return offenders

    def test_the_lines_outside_the_home_are_the_ones_the_report_names(self):
        """Each named site outside the home stands, and its text is kept."""
        self.assertEqual([], self.walk_outside_lines(),
                         "a spelling outside the home moved")
        self.assertEqual(len(OUTSIDE_LITERALS), len(stripped),
                         "the case read no line of the tree")

    def test_the_anti_home_walk_names_a_second_home(self):
        """The home holds each value, and the named lines carry the rest."""
        if not stripped:
            self.walk_outside_lines()
        self.assertTrue(stripped, "the case of the named lines did not run")
        allowed = set(ALLOWED_HOME_LITERALS) | {(path, line) for path, line, _v
                                                in OUTSIDE_LITERALS}
        offenders = []
        files = walked()
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            for line, value in literal_sites(path.read_text(encoding="utf-8"), relative):
                if (relative, line) in allowed:
                    continue
                offenders.append(report(relative, line,
                                        source_lines(relative)[line - 1],
                                        "%r is a second home of the key; %s holds it"
                                        % (value, HOME)))
        self.assertGreater(len(files), MIN_WALK_FILES,
                           "the walk read %d files; it is not the tree" % len(files))
        self.assertEqual([], offenders,
                         "an unnamed line spells a calibration key:\n" + "\n".join(offenders))

    def test_the_pages_read_the_keys_of_the_home(self):
        """Two javascript readers of the page read the value of the home."""
        offenders = []
        for relative, line, name in PAGES:
            lines = source_lines(relative)
            text = lines[line - 1] if 0 < line <= len(lines) else ""
            if PAGE_READS % name not in text:
                offenders.append(report(relative, line, text,
                                        "the page reader does not read %r; a value that "
                                        "moves must move this line too" % name))
            if name not in KEYS.values():
                offenders.append(report(relative, line, text,
                                        "%r is no key of the home" % name))
        self.assertEqual([], offenders,
                         "a page reader of a calibration key moved:\n" + "\n".join(offenders))

    def test_the_page_walk_finds_the_value_of_the_home(self):
        """A page holds no python name, so its line holds the value."""
        text = source_text(PAGES[0][0])
        self.assertIn(PAGE_READS % home_value("VERIFIED_SIDES_KEY"), text,
                      "%s does not read the value of VERIFIED_SIDES_KEY" % PAGES[0][0])


if __name__ == "__main__":
    unittest.main()
