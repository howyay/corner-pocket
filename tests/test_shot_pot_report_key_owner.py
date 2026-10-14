"""The rejection field ``nearest_distance_px`` has one home, and three sites read it.

The gate writes the field of every ``disappeared_outside_pocket`` rejection:

    "nearest_distance_px": round(near_dist, 2)

and ``src/ball_association_audit.py`` reads it back twice, once as the argument of
a ``.get`` and once as a subscript, to answer how far the last sighting of a
fragmented identity sat from the nearest pocket.  Three spellings of one word, no
owner, was the state of round 105.

The home of the word is ``src/ball_association_audit.py:59``::

    NEAREST_DISTANCE_PX_KEY = "nearest_distance_px"

The home sits in the audit module and not in the gate, and the reason is weight.
The audit module imports the standard library only, and it must stay that way: it
is the tool the associator runs from a shell, and a reader of it must not need
cv2.  The gate is not a light module -- ``src/shot_pot_gate.py:93`` reads
``OCC_DENSE_MIN`` from ``src/motion_scan.py``, which imports cv2 and numpy -- so a
home declared in the gate would pull both libraries into every reader that names
it.  A home declared in the audit module is read by the gate, and the gate is
heavy already, so the weight only travels the safe way.

This module holds four facts, and the walk of each one is written here:

1. the value and the line of the home;
2. the three live sites: the write of the gate and the two reads of the audit;
3. the absence of a second spelling anywhere under ``src/`` or ``annotator/``, so
   a new bare literal fails this guard and the failure names its line;
4. the measured import of the reader: no numpy and no cv2.

Run: ``./scripts/pool-test.sh python test_shot_pot_report_key_owner``

Measured 2026-10-13 on branch ``main``, Python 3.14.6: the anti-duplication walk
reads 285 python files (272 under ``src/``, 13 under ``annotator/``) in 1.8 s.
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

from src import ball_association_audit  # noqa: E402

#: The owner module, as a path from the repository root.  It is the lightest
#: module that already reads the fact: standard library only.
OWNER = "src/ball_association_audit.py"
#: The module that writes the field, and the only importer of the home.
WRITER = "src/shot_pot_gate.py"
#: The owner name, read from the imported module and from no copy of the text.
OWNER_NAME = "NEAREST_DISTANCE_PX_KEY"
#: The two modules that spell the field.  ``src/shot_pot_gate.py`` holds the
#: writer; ``src/ball_association_audit.py`` holds the two readers and the home.
MODULES = (OWNER, WRITER)
#: Every spelling this module accepts as a use of the home: the constant alone,
#: and the constant under the module that imports it.
OWNER_SPELLINGS = (OWNER_NAME, "shot_pot_gate." + OWNER_NAME)
#: The spelling of the constant in its own definition, for the line regex.
NAME_RE = re.compile(rf"\s*{OWNER_NAME}\s*=")
#: A module-level name in upper case, the shape of a constant of this house.
CONSTANT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
#: The three live sites, as ``(line, kind, name as written)`` per module, at the
#: state the home landed in.  A fourth site, or a move, must state itself here.
SITES = {
    OWNER: ((167, "get", OWNER_NAME), (168, "lookup", OWNER_NAME)),
    WRITER: ((1605, "dict", OWNER_NAME),),
}
#: The module and the name the writer imports for the home.
WRITER_IMPORT = ("src.ball_association_audit", OWNER_NAME)
#: The two directories the anti-duplication walk covers.
WALKED = ("src/**/*.py", "annotator/**/*.py")
#: A name that makes the reader heavy, and a name that would make it cyclic.
HEAVY_ROOTS = ("numpy", "cv2", "torch")
#: The probe of the acceptance of this round: the import of the reader, weighed.
LIGHT_PROBE = ("import sys, src.ball_association_audit; "
               "print('numpy' in sys.modules, 'cv2' in sys.modules)")
#: The same probe for the module the home was kept out of.
HEAVY_PROBE = ("import sys, src.shot_pot_gate; "
               "print('numpy' in sys.modules, 'cv2' in sys.modules)")


def own_key() -> str:
    """The value of the home constant, read from the imported module.

    The read is deliberate.  ``getattr`` answers the value of the module that is
    loaded now, so a guard that plants a new value in the module is answered by
    that value.
    """
    value = getattr(ball_association_audit, OWNER_NAME, None)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{OWNER}:{OWNER_NAME} is not a non-empty string: {value!r}")
    return value


def source_text(relative: str) -> str:
    """The text of one source file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one source file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(where: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return f"{where}:{line}: {text.strip()}  <- {why}"


def callee_name(node: ast.Call) -> str:
    """The written name of the function of a call, or an empty string."""
    try:
        return ast.unparse(node.func)
    except Exception:  # pragma: no cover - a node the standard writer cannot print
        return ""


def owned_dict_keys(text: str, where: str) -> list:
    """Every dict key of a display that spells the owner name.

    The answer is ``(line, the key as written, the text of the whole display)``
    per site.  A dict display of a rejection's ``numbers`` is the shape of the
    writer, so this walk finds the write of the gate.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if not isinstance(node, ast.Dict):
            continue
        for key_node in node.keys:
            written = ast.unparse(key_node) if key_node is not None else ""
            if written in OWNER_SPELLINGS:
                found.append((key_node.lineno, written, ast.unparse(node)))
    return sorted(found)


def owned_lookups(text: str, where: str) -> list:
    """Every lookup that reads the field through a spelling of the owner name.

    A lookup is ``<expression>.get(<first argument>)`` or the subscript
    ``<expression>[<index>]``.  The answer is ``(line, the name as written, the
    expression it reads)`` per site.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Call):
            first = node.args[0] if node.args else None
            if isinstance(first, (ast.Name, ast.Attribute, ast.Subscript)):
                written = ast.unparse(first)
                if written in OWNER_SPELLINGS or written.endswith("." + OWNER_NAME):
                    found.append((first.lineno, written, callee_name(node)))
        elif isinstance(node, ast.Subscript):
            index = node.slice
            if isinstance(index, (ast.Name, ast.Attribute)):
                written = ast.unparse(index)
                if written in OWNER_SPELLINGS or written.endswith("." + OWNER_NAME):
                    found.append((index.lineno, written, ast.unparse(node.value)))
    return sorted(found)


def bare_literals(text: str, where: str, key: str, allowed_lines=()) -> list:
    """Every source site that spells the key as a plain literal.

    The node walk answers what a text grep cannot: a docstring is a literal too,
    so the walk reports one, and the one allowed site is the home itself.  The
    answer is ``(line, the literal as written)`` per site.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Constant) and node.value == key \
                and node.lineno not in allowed_lines:
            found.append((node.lineno, ast.unparse(node)))
    return sorted(found)


def imported_roots(text: str, where: str, body_only: bool = False) -> set:
    """The top-level package of every import of one module.

    ``body_only`` answers the imports of the module body, the ones an
    ``import src.<module>`` of a reader runs.  A lazy import inside a function is
    not measured then, because the probe does not run that function.
    """
    tree = ast.parse(text, filename=where)
    roots = set()
    for node in (tree.body if body_only else ast.walk(tree)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def imported_names(text: str, where: str, module: str, name: str = "") -> list:
    """Every local name one module imports from another module, as written.

    ``name`` limits the answer to the imported name of the home, so a rename of
    the import of the writer answers the new name and fails the case that pins it.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                if not name or alias.name == name:
                    found.append(alias.asname or alias.name)
    return sorted(found)


def owned_lines(relative: str, text: str) -> list:
    """Every line of one module that spells the owner name, from the syntax tree.

    The text of a line holds no function body, so the walk is the honest count: a
    comment that names the constant is no site of the constant.
    """
    lines = text.splitlines()
    numbers = []
    for node in ast.walk(ast.parse(text, filename=relative)):
        if isinstance(node, ast.Name) and node.id == OWNER_NAME:
            numbers.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == OWNER_NAME:
            numbers.append(node.lineno)
    return sorted((number, lines[number - 1].strip()) for number in set(numbers))


def walked_files() -> list:
    """Every python file of this repository that the anti-duplication walk reads."""
    files = []
    for pattern in WALKED:
        files.extend(sorted(ROOT.glob(pattern)))
    return [path for path in files if "__pycache__" not in path.parts]


def run_probe(code: str) -> str:
    """The stdout of one import probe, run in a fresh interpreter of this venv."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise AssertionError(f"the probe {code!r} failed:\n{done.stderr}")
    return done.stdout.strip()


class OwnerTests(unittest.TestCase):
    """The home name, its value and the type of that value."""

    def test_the_home_names_the_shipped_field(self):
        self.assertEqual(own_key(), "nearest_distance_px",
                         f"{OWNER}:{OWNER_NAME} moved; the write of {WRITER} and "
                         f"the two reads of the audit must move with it")

    def test_the_home_line_of_the_module_carries_the_shipped_field(self):
        """The line of the owner module that holds the value, with its number.

        This case pins the home at ``path:line``.  The value the module answers
        and the value that the text of the module shows must be one word, so a
        reader of the report can open that line and see the shipped field.
        """
        owner = own_key()
        lines = source_lines(OWNER)
        sites = [(number, text) for number, text in enumerate(lines, start=1)
                 if NAME_RE.match(text)]
        self.assertEqual(1, len(sites),
                         f"{OWNER} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
        number, text = sites[0]
        self.assertIn(f'{OWNER_NAME} = "{owner}"', text,
                      report(OWNER, number, text,
                             f"the line does not assign {owner!r} to {OWNER_NAME}"))
        self.assertEqual(59, number,
                         report(OWNER, number, text,
                                f"{OWNER_NAME} stood at line 59 when the home landed; "
                                f"a move must restate it in the report"))

    def test_the_home_name_has_the_shape_of_a_constant(self):
        self.assertTrue(CONSTANT_NAME_RE.match(OWNER_NAME),
                        f"{OWNER_NAME} is not the name of a constant")
        self.assertIsInstance(own_key(), str, f"{OWNER}:{OWNER_NAME} is not a string")

    def test_no_second_home_of_the_field_exists_in_the_source_tree(self):
        """The literal stands once under ``src/`` and ``annotator/``: here."""
        key = own_key()
        owner_line = next(number for number, text in
                          enumerate(source_lines(OWNER), start=1) if NAME_RE.match(text))
        offenders = []
        walked = 0
        for path in walked_files():
            relative = path.relative_to(ROOT).as_posix()
            walked += 1
            allowed = (owner_line,) if relative == OWNER else ()
            offenders.extend(report(relative, line, source_lines(relative)[line - 1],
                                    f"{written} is a bare spelling of the field "
                                    f"{key!r}; write {OWNER_NAME} of {OWNER} instead")
                             for line, written
                             in bare_literals(path.read_text(encoding="utf-8"),
                                              relative, key, allowed))
        self.assertGreater(walked, 100, f"the walk read {walked} files; it is not the tree")
        self.assertEqual([], offenders,
                         "a second home of the field stands in the source tree:\n"
                         + "\n".join(offenders))


class WriterTests(unittest.TestCase):
    """The gate writes the field through the home of the audit module."""

    def test_the_writer_imports_the_home(self):
        names = imported_names(source_text(WRITER), WRITER,
                               WRITER_IMPORT[0], WRITER_IMPORT[1])
        self.assertEqual([WRITER_IMPORT[1]], names,
                         f"{WRITER} imports {names} from {WRITER_IMPORT[0]}; the "
                         f"guard measures the name under that import")

    def test_the_writer_writes_the_field_through_the_home(self):
        """The key of the rejection's numbers comes from the constant."""
        sites = owned_dict_keys(source_text(WRITER), WRITER)
        self.assertEqual(1, len(sites),
                         f"{WRITER} holds {len(sites)} dict displays that spell "
                         f"{OWNER_NAME}: {[site[0] for site in sites]}")
        line, written, display = sites[0]
        self.assertEqual(OWNER_NAME, written,
                         report(WRITER, line, source_lines(WRITER)[line - 1],
                                f"the display writes {written}, not {OWNER_NAME}"))
        self.assertIn(OWNER_NAME, display,
                      report(WRITER, line, source_lines(WRITER)[line - 1],
                             f"the display {display} does not write {OWNER_NAME}"))
        self.assertIn("round(near_dist, 2)", source_lines(WRITER)[line - 1],
                      report(WRITER, line, source_lines(WRITER)[line - 1],
                             "the write of the nearest pocket distance moved"))

    def test_the_writer_resolves_the_home_at_run_time(self):
        """The gate is the one module that imports the home, and it answers."""
        code = (f"from src import shot_pot_gate; "
                f"print(shot_pot_gate.{OWNER_NAME})")
        self.assertEqual(own_key(), run_probe(code),
                         f"{WRITER} does not answer the home value of {OWNER}")


class ReaderTests(unittest.TestCase):
    """The two reads of the audit module name the home."""

    def test_the_reader_reads_the_field_through_the_home(self):
        """The anti-vacuity case of the reader of the owner module."""
        key = own_key()
        reads = [(line, written) for line, written, _where
                 in owned_lookups(source_text(OWNER), OWNER)]
        self.assertEqual(2, len(reads),
                         f"{OWNER} reads the field {key!r} at {len(reads)} sites: {reads}")
        for line, written in reads:
            self.assertEqual(OWNER_NAME, written,
                             report(OWNER, line, source_lines(OWNER)[line - 1],
                                    f"the read writes {written}, not {OWNER_NAME}"))
            self.assertIn(OWNER_NAME, source_lines(OWNER)[line - 1])

    def test_the_three_live_sites_are_the_ones_the_report_names(self):
        """One write and two reads.  A fourth site must state itself here."""
        offenders = []
        for relative in MODULES:
            lines = source_lines(relative)
            text = source_text(relative)
            sites = []
            for line, written, _display in owned_dict_keys(text, relative):
                sites.append((line, "dict", written))
            for line, written, _where in owned_lookups(text, relative):
                where = lines[line - 1]
                sites.append((line, "get" if ".get(" in where else "lookup", written))
            self.assertEqual(sorted(SITES[relative]), sorted(sites),
                             f"the live sites of {relative} moved")
            for line, _kind, written in sites:
                offenders.extend([]) if written in OWNER_SPELLINGS else offenders.append(
                    report(relative, line, lines[line - 1],
                           f"{written} does not name {OWNER_NAME} of {OWNER}"))
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_reader_names_no_field_of_its_own(self):
        """Every use of the home name in both modules is a use of the constant."""
        offenders = []
        for relative in MODULES:
            for line, text in owned_lines(relative, source_text(relative)):
                if OWNER_NAME in text:
                    continue
                offenders.append(report(relative, line, text,
                                        f"the line names no {OWNER_NAME}"))
        self.assertEqual([], offenders,
                         "a module spells the field without the home:\n"
                         + "\n".join(offenders))


class LightReaderTests(unittest.TestCase):
    """The home keeps the reader light: no numpy and no cv2 in the audit."""

    def test_the_owner_module_body_imports_no_heavy_module(self):
        """The imports the probe runs are the standard library, and no ``src``."""
        roots = imported_roots(source_text(OWNER), OWNER, body_only=True)
        offenders = sorted(roots & (set(HEAVY_ROOTS) | {"src"}))
        self.assertEqual([], offenders,
                         f"the module body of {OWNER} imports {offenders}; the home "
                         f"is here because this reader stays standard-library-only")

    def test_no_line_of_the_owner_module_names_a_heavy_module(self):
        """Even a lazy import of the light reader must not name a heavy module."""
        roots = imported_roots(source_text(OWNER), OWNER)
        offenders = sorted(roots & set(HEAVY_ROOTS))
        self.assertEqual([], offenders,
                         f"{OWNER} names {offenders} in an import; the light reader "
                         f"stays light at every line, top level or lazy")

    def test_the_measured_import_of_the_reader_is_light(self):
        """The probe of the acceptance, run in a fresh interpreter."""
        self.assertEqual("False False", run_probe(LIGHT_PROBE),
                         f"the import of {OWNER} pulls numpy or cv2 into the reader: "
                         f"{run_probe(LIGHT_PROBE)!r}")

    def test_the_module_the_home_was_kept_out_of_stays_heavy(self):
        """Why the home is not in the gate: the gate reads cv2 and numpy already."""
        self.assertEqual("True True", run_probe(HEAVY_PROBE),
                         f"the import of {WRITER} answers {run_probe(HEAVY_PROBE)!r}; "
                         f"a home declared there would make every reader of "
                         f"{OWNER_NAME} heavy, and this round must restate the "
                         f"reason if the weight of the gate changes")


class WalkTests(unittest.TestCase):
    """The walk reports a planted literal with its file and line."""

    def test_the_walk_reports_a_planted_read(self):
        planted = ('def bite_nearest_distance_px(numbers):\n'
                   '    return float(numbers["nearest_distance_px"])\n')
        offenders = [report(OWNER, line, planted.splitlines()[line - 1],
                            f"{written} is a bare spelling of the field")
                     for line, written in bare_literals(planted, "planted.py", own_key())]
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f"{OWNER}:2:", offenders[0])
        self.assertIn("nearest_distance_px", offenders[0])
        self.assertIn("float(numbers", offenders[0])

    def test_the_walk_reports_a_planted_write(self):
        planted = ('def numbers(near_dist):\n'
                   '    return {"nearest_distance_px": round(near_dist, 2)}\n')
        offenders = [report(WRITER, line, planted.splitlines()[line - 1],
                            f"{written} is a bare spelling of the field")
                     for line, written in bare_literals(planted, "planted.py", own_key())]
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f"{WRITER}:2:", offenders[0])
        self.assertEqual([], owned_dict_keys(planted, "planted.py"),
                         "the planted literal counts as a home spelling")

    def test_the_walk_accepts_the_home_spelling(self):
        planted = ('def bite_nearest_distance_px(numbers):\n'
                   '    return (numbers.get(NEAREST_DISTANCE_PX_KEY), '
                   'numbers[NEAREST_DISTANCE_PX_KEY])\n')
        reads = owned_lookups(planted, "planted.py")
        self.assertEqual(2, len(reads), reads)
        self.assertEqual([OWNER_NAME, OWNER_NAME], [read[1] for read in reads])
        self.assertEqual([], bare_literals(planted, "planted.py", own_key()),
                         "the home spelling counts as a bare literal")


if __name__ == "__main__":
    unittest.main()
