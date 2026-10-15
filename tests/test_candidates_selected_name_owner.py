"""The scan document ``candidates_selected.json`` has one home, and three sites read it.

The walk of round 110 found one writer and one reader of the name of a scan
artifact, and no case named it:

* ``src/candidate_scan.py:637`` - the writer, ``write_plan``;
* ``src/calib_mapping_audit.py:80`` - the reader, the ``CANDIDATES`` path;
* ``tests/test_calib_mapping_audit.py:103`` - the skip guard of the provenance case.

``git grep -F candidates_selected -- tests/`` answered one prose sentence and one
path, so a rename of the writer line stayed silent in the reader.

The home is ``src/candidate_scan.py:70``::

    CANDIDATES_NAME = "candidates_selected.json"

The home sits in the writer, because that module writes the document.  The value
stays byte-identical: ``out/scan30/`` carries the document of a shipped run, and a
reader must still find it.

Why the reader may hold a top-level import.  An import of the writer from the
reader is legal only if it closes no cycle.  A case measures the answer in a fresh
interpreter: a process that imports ``src.candidate_scan`` answers False for
``"src.calib_mapping_audit" in sys.modules``.  The home also adds no new heavy
root, because the audit answers numpy, cv2 and torch before the home lands.  A
second case measures that answer too.

The scan30 set.  ``src/calib_mapping_audit.py`` takes the scan folder from the home
``STATIC_OUT`` of ``src/datasets.py``, because the writer takes an ``out_dir``
argument and no reader may spell the folder again.  The folder and the name are two
facts, and each one has a home.  A case pins both reads of the one line, so a round
that spells ``"out" / "scan30"`` again reddens it instead of passing.

The test fixture.  The skip guard of the provenance case reads the same document.
The measurement says that it must read the home: with a bare literal, a rename of
the home would point the guard at a file that does not exist, and the case would
skip instead of reddening.  The guard reads the name from the home, and keeps its
own folder.

Every case reads its copy of the tree, and pins the NAME of the home, not only the
value: the import of each reader, the line of each site, and the run-time binding
of the name.

Run: ``./scripts/pool-test.sh python test_candidates_selected_name_owner``

Measured 2026-10-14, Python 3.14.6: the anti-copy walk reads 309 files under
``src/``, ``annotator/``, ``tools/`` and ``scripts/``, and one line of them spells
the name.
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

#: The shipped value of the name.  The guard spells it once, so a case can pin it.
SHIPPED_NAME = "candidates_selected.json"
#: The home module, and the name it holds the document under.
HOME = "src/candidate_scan.py"
HOME_NAME = "CANDIDATES_NAME"
#: The line of the home statement, at the state the home landed in, and its text.
HOME_LINE = 70
HOME_FORM = '%s = "%s"' % (HOME_NAME, SHIPPED_NAME)
#: The line regex of the definition, for the case that pins the home line.
NAME_RE = re.compile(r"\s*%s\s*=" % HOME_NAME)
#: A module-level name in upper case, the shape of a constant of this house.
CONSTANT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
#: Every live site of the home name, as ``(line, kind)`` per module.  The kind is
#: ``home`` for the definition, ``import`` for the import of the home, and ``load``
#: for a line that reads the name.  A moved, a new or a lost site must restate
#: itself here.
SITES = {
    HOME: ((HOME_LINE, "home"), (637, "load")),
    "src/calib_mapping_audit.py": ((66, "import"), (80, "load")),
    "tests/test_calib_mapping_audit.py": ((102, "import"), (103, "load")),
}
#: The module each reader takes the home from, and whether the import sits at the
#: top of the module.  The test takes the home inside its case, because the audit
#: is heavy and the case runs after its skip guard.
IMPORTS = {
    "src/calib_mapping_audit.py": ("src.candidate_scan", True),
    "tests/test_calib_mapping_audit.py": ("src.candidate_scan", False),
}
#: The reader of the path, the folder home it takes the scan30 folder from, the name
#: home it reads the file name from, and the line that joins the two.  The folder and
#: the name are two facts with two homes, so neither one may fold into the other.
READER = "src/calib_mapping_audit.py"
READER_LINE = 80
READER_FOLDER_HOME = "src.datasets"
READER_FOLDER_NAME = "STATIC_OUT"
READER_FOLDER = "STATIC_OUT[BUILT_IN_DATASET]"
#: The directories and patterns the anti-copy walk reads.
WALKED = ("src/**/*.py", "annotator/**/*.py", "tools/**/*.py", "scripts/**/*.py",
          "annotator/**/*.html", "annotator/**/*.js", "annotator/**/*.css",
          "scripts/**/*.sh", "scripts/**/*.sql")
#: The floor that keeps a vacuous walk from passing.  Measured 309 files.
FILE_FLOOR = 250
#: The probes of the run-time facts, each run in a fresh interpreter of this venv.
BIND_PROBE = "import src.candidate_scan as module; print(module.%s)" % HOME_NAME
#: A cycle would show as the writer pulling the reader into its own import.
CYCLE_PROBE = ("import sys, src.candidate_scan; "
               "print('src.calib_mapping_audit' in sys.modules)")
#: The reader must still answer the home, and the name of its own document.
READER_PROBE = ("import sys, src.calib_mapping_audit as audit; "
                "print('src.candidate_scan' in sys.modules, audit.CANDIDATES.name)")
#: The heavy roots the audit answers for itself, before the home lands in it.
HEAVY_PROBE = ("import sys, src.calib_mapping_audit; "
               "print(' '.join(m for m in ('cv2', 'numpy', 'torch') if m in sys.modules))")


def source_text(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(where: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return "%s:%d: %s  <- %s" % (where, line, (text or "").strip(), why)


def home_sites() -> list:
    """Every line of the home module that defines the name, with its number."""
    return [(number, text) for number, text in enumerate(source_lines(HOME), start=1)
            if NAME_RE.match(text)]


def home_value() -> str:
    """The value of the home constant, read from the syntax tree of the home.

    The read is a read of the shipped text and not of an import: the home module
    imports cv2 and torch, and this guard must not pull them into its own process to
    answer a string.  Three cases prove the run-time binding with a fresh
    interpreter instead.
    """
    for node in ast.walk(ast.parse(source_text(HOME), filename=HOME)):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == HOME_NAME
                for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return ""


def name_sites(text: str, where: str) -> list:
    """Every site of one module that names the home, as ``(line, kind)``.

    A site of the home name is a definition, an import of the name, or a line that
    reads the name.  A comment that names the name is no site of it, so the walk is
    the honest count.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == HOME_NAME or alias.asname == HOME_NAME
                   for alias in node.names):
                found.append((node.lineno, "import"))
        elif isinstance(node, ast.Name) and node.id == HOME_NAME:
            found.append((node.lineno,
                          "home" if isinstance(node.ctx, ast.Store) else "load"))
    return sorted(set(found))


def imported_locals(text: str, where: str, module: str) -> list:
    """Every local name one module imports from another, as ``(line, name)``."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            found.extend((node.lineno, alias.asname or alias.name)
                         for alias in node.names)
    return sorted(found)


def imported_names(text: str, where: str, module: str) -> list:
    """Every local name one module takes from another for the home, as (line, name)."""
    return [(number, name) for number, name in imported_locals(text, where, module)
            if name == HOME_NAME]


def body_imports(text: str, where: str, module: str) -> list:
    """Every module-level import of one module, as a line number."""
    tree = ast.parse(text, filename=where)
    return sorted(node.lineno for node in tree.body
                  if isinstance(node, ast.ImportFrom) and node.module == module)


def quoted_offences(relative: str, text: str, allowed_lines=()) -> list:
    """Every line of a file that spells the name as a quoted literal.

    A line of ``allowed_lines`` is the one home of that file, so it may spell the
    name.  Every other line that spells it is a copy, and the answer names it.
    """
    offenders = []
    for number, line in enumerate(text.splitlines(), start=1):
        if number in allowed_lines:
            continue
        if '"%s"' % SHIPPED_NAME in line or "'%s'" % SHIPPED_NAME in line:
            offenders.append(report(relative, number, line,
                                    "%r is a bare copy of the name; read %s of %s"
                                    % (SHIPPED_NAME, HOME_NAME, HOME)))
    return offenders


def walked(patterns) -> list:
    """Every file of one set of patterns, without the caches."""
    files = []
    for pattern in patterns:
        files.extend(sorted(ROOT.glob(pattern)))
    return [path for path in files if "__pycache__" not in path.parts]


def run_probe(code: str) -> str:
    """The stdout of one probe, run in a fresh interpreter of this venv."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise AssertionError("the probe %r failed:\n%s" % (code, done.stderr))
    return done.stdout.strip()


class HomeTests(unittest.TestCase):
    """The home name, its value, its line and its run-time binding."""

    def test_the_home_names_the_shipped_document(self):
        lines = source_lines(HOME)
        self.assertEqual(SHIPPED_NAME, home_value(),
                         report(HOME, HOME_LINE, lines[HOME_LINE - 1],
                                "the home moved; the writer and the two readers "
                                "must move with it"))

    def test_the_home_line_of_the_module_carries_the_shipped_name(self):
        """The case that pins the home at ``path:line``."""
        sites = home_sites()
        self.assertEqual(1, len(sites),
                         "%s holds %d definitions of %s: %s"
                         % (HOME, len(sites), HOME_NAME, [site[0] for site in sites]))
        number, text = sites[0]
        self.assertIn(HOME_FORM, text,
                      report(HOME, number, text,
                             "the line does not assign %r to %s"
                             % (SHIPPED_NAME, HOME_NAME)))
        self.assertEqual(HOME_LINE, number,
                         report(HOME, number, text,
                                "%s stood at line %d when the home landed; a move "
                                "must restate it in the report" % (HOME_NAME, HOME_LINE)))

    def test_the_home_binds_the_name_at_run_time(self):
        """The shipped module answers the value when a reader imports it."""
        lines = source_lines(HOME)
        self.assertEqual(SHIPPED_NAME, run_probe(BIND_PROBE),
                         report(HOME, HOME_LINE, lines[HOME_LINE - 1],
                                "the home does not answer %s when a reader imports it"
                                % HOME_NAME))

    def test_the_home_name_is_the_name_of_a_constant(self):
        """The name of a constant of this house, and the name of a document."""
        self.assertTrue(CONSTANT_NAME_RE.match(HOME_NAME),
                        "%s is not the name of a constant" % HOME_NAME)
        self.assertTrue(home_value().endswith(".json"),
                        "%r is not the name of a JSON document" % home_value())


class ReaderTests(unittest.TestCase):
    """The audit and the test fixture read the name of the home."""

    def test_every_reader_imports_the_home(self):
        """Every reader takes the name from the home, at the place its kind allows."""
        offenders = []
        for relative, (module, at_top) in sorted(IMPORTS.items()):
            lines = source_lines(relative)
            text = source_text(relative)
            found = imported_names(text, relative, module)
            if not found:
                offenders.append(report(relative, 1, lines[0],
                                        "the file imports no %s from %s"
                                        % (HOME_NAME, module)))
                continue
            for number, name in found:
                if name != HOME_NAME:
                    offenders.append(report(relative, number, lines[number - 1],
                                            "the import is named %s, not %s"
                                            % (name, HOME_NAME)))
            if bool(body_imports(text, relative, module)) != at_top:
                offenders.append(report(relative, found[0][0], lines[found[0][0] - 1],
                                        "the import of %s sits at the top of the "
                                        "module: %s" % (module, at_top)))
        self.assertEqual([], offenders,
                         "a reader does not import the home:\n" + "\n".join(offenders))

    def test_the_writer_and_the_readers_are_the_sites_the_report_names(self):
        """Six sites in three files.  A move or a new site must state itself."""
        offenders = []
        for relative, pinned in sorted(SITES.items()):
            lines = source_lines(relative)
            found = name_sites(source_text(relative), relative)
            if sorted(pinned) != found:
                number = found[0][0] if found else 1
                offenders.append(report(relative, number, lines[number - 1],
                                        "the live sites are %s, not the pinned %s"
                                        % (found, sorted(pinned))))
        self.assertEqual([], offenders,
                         "the live sites of the name moved:\n" + "\n".join(offenders))

    def test_every_reading_site_names_the_home(self):
        """Every site that writes or reads the name goes through the home."""
        offenders = []
        for relative in sorted(SITES):
            lines = source_lines(relative)
            for number, kind in SITES[relative]:
                if kind != "load":
                    continue
                if HOME_NAME not in lines[number - 1]:
                    offenders.append(report(relative, number, lines[number - 1],
                                            "the site does not read %s of %s"
                                            % (HOME_NAME, HOME)))
        self.assertEqual([], offenders,
                         "a site of the name does not read the home:\n"
                         + "\n".join(offenders))

    def test_the_reader_takes_the_scan30_folder_from_its_home(self):
        """The folder and the name are two facts, and each one has a home.

        The writer takes an ``out_dir`` argument, so the folder may not fold into the
        name home.  This case pins the reads of the one line: the folder home
        ``STATIC_OUT`` of ``src/datasets.py``, indexed by the built-in dataset, and the
        name home ``CANDIDATES_NAME`` of the writer.  A line that spells
        ``"out" / "scan30"`` again loses the folder home, and a line that spells the
        file name again loses the name home, so neither shortcut passes.
        """
        line = source_lines(READER)[READER_LINE - 1]
        self.assertIn(READER_FOLDER, line,
                      report(READER, READER_LINE, line,
                             "the reader does not take its scan30 folder from %s of %s"
                             % (READER_FOLDER_NAME, READER_FOLDER_HOME)))
        taken = [name for _, name in imported_locals(source_text(READER), READER,
                                                     READER_FOLDER_HOME)]
        self.assertIn(READER_FOLDER_NAME, taken,
                      report(READER, READER_LINE, line,
                             "the reader does not take %s from %s, so the folder of "
                             "that line is another name"
                             % (READER_FOLDER_NAME, READER_FOLDER_HOME)))
        self.assertIn(HOME_NAME, line,
                      report(READER, READER_LINE, line,
                             "the reader does not read %s of %s" % (HOME_NAME, HOME)))
        self.assertNotIn('"%s"' % SHIPPED_NAME, line,
                         report(READER, READER_LINE, line,
                                "the reader spells the name again instead of reading %s"
                                % HOME_NAME))

    def test_the_reader_reads_the_home_at_run_time(self):
        """The audit answers the home, and its own path carries the value."""
        lines = source_lines(READER)
        self.assertEqual("True %s" % SHIPPED_NAME, run_probe(READER_PROBE),
                         report(READER, READER_LINE, lines[READER_LINE - 1],
                                "the reader does not answer %s from %s"
                                % (SHIPPED_NAME, HOME)))


class WeightTests(unittest.TestCase):
    """Why the reader may import the writer at the top of its module."""

    def test_the_home_closes_no_cycle(self):
        """A process that imports the writer never pulls the reader in.

        The measurement is the licence for the top-level import of the reader.  A
        cycle would show here as True, and the reader would need a local import
        with the comment ``# local: <why>``.
        """
        self.assertEqual("False", run_probe(CYCLE_PROBE),
                         "the writer pulls the reader into its own import; the reader "
                         "must take the home inside a call instead")

    def test_the_home_adds_no_heavy_root_to_the_audit(self):
        """The audit answers the heavy three before the home lands in it."""
        self.assertEqual("cv2 numpy torch", run_probe(HEAVY_PROBE),
                         "the import of %s answers %r; the weight argument of the "
                         "top-level import reads these three roots"
                         % (READER, run_probe(HEAVY_PROBE)))


class WalkTests(unittest.TestCase):
    """The anti-copy walk of the four trees, with its planted proofs."""

    def test_no_other_file_spells_the_name_again(self):
        offenders = []
        files = walked(WALKED)
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            allowed = (HOME_LINE,) if relative == HOME else ()
            offenders.extend(quoted_offences(
                relative, path.read_text(encoding="utf-8", errors="ignore"), allowed))
        self.assertGreater(len(files), FILE_FLOOR,
                           "the walk read %d files; it is not the tree" % len(files))
        self.assertEqual([], offenders,
                         "a second home of the name stands in the source tree:\n"
                         + "\n".join(offenders))

    def test_the_walk_reports_a_planted_copy(self):
        planted = ('def write_plan(out_dir):\n'
                   '    return (Path(out_dir) / "candidates_selected.json").write_text("{}")\n')
        offenders = quoted_offences("src/planted.py", planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("src/planted.py:2:", offenders[0])
        self.assertIn("candidates_selected.json", offenders[0])
        self.assertIn("write_text", offenders[0])
        self.assertIn("CANDIDATES_NAME", offenders[0])

    def test_the_walk_accepts_the_home_spelling(self):
        planted = ('def write_plan(out_dir):\n'
                   '    return (Path(out_dir) / CANDIDATES_NAME).write_text("{}")\n')
        self.assertEqual([], quoted_offences("src/planted.py", planted),
                         "the home spelling counts as a bare literal")
        self.assertEqual([(2, "load")], name_sites(planted, "src/planted.py"))

    def test_the_walk_answers_the_offender_as_path_and_line(self):
        """A planted copy inside the walked tree is reported by ``path:line``."""
        offenders = quoted_offences("tools/planted_tool.py",
                                    'NAME = "candidates_selected.json"\n')
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("tools/planted_tool.py:1:"),
                        offenders[0])


if __name__ == "__main__":
    unittest.main()
