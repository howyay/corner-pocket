"""The ball key ``ball_id`` has one home, and four files read it.

The walk of round 110 found the key of one ball spelled again and again: the gate
wrote it into every row it returned, and the queue and the two association audits
read the row back by the bare string.

* ``src/shot_pot_gate.py`` - the four writers of a row (a shot, a pot, a
  rejection, an unresolved event), each at its own ``as_dict``;
* ``src/dense_queue.py`` - 29 sites, the writer of the queue and its readers;
* ``src/ball_association_audit.py`` - 5 readers of the two audits;
* ``src/ball_association_ab.py`` - the driver that rebuilds a gate row.

No case named the key.  ``git grep -F '"ball_id"' -- tests/`` answered only rows
of other cases, so a rename of the served key stayed silent in every reader.

The home is ``src/shot_pot_gate.py:895``::

    BALL_ID_KEY = "ball_id"

The home sits beside the row classes of the gate, because the gate writes those
four row shapes.  The value never moves: a queue document on disk already carries
``"ball_id"``, and a reader must still find it.  One case writes such a document
and feeds it to the reader of the queue, so the bytes prove the identity of the
key, and one case pins the literal that the cases of ``tests/`` still write.

Weight.  ``src/ball_association_audit.py`` is the lightest reader of the house,
so it takes the name inside the three functions that read the key, and not at the
top of the module.  The reason is a cycle, not taste: ``src/shot_pot_gate.py:86``
imports ``NEAREST_DISTANCE_PX_KEY`` from the audit, so a top-level import of the
gate closes a cycle.  Two cases hold that fact: one reads the module body of the
audit, and one measures in a fresh interpreter that the audit alone pulls neither
the gate nor numpy.  ``src/dense_queue.py:81`` and ``src/ball_association_ab.py:36``
carry no cycle, so both name the home at the top of the module.

Every case reads its copy, and pins the NAME of the home, not only the value: the
45 live sites of the four files, the text of each line, and the run-time binding
of the name.

Run: ``./scripts/pool-test.sh python test_ball_id_key_owner``

Measured 2026-10-14, Python 3.14.6: the anti-copy walk reads 291 python files, 14
pages and 3 shell files under ``src/``, ``annotator/``, ``tools/`` and
``scripts/``, and the four files of the row carry 45 sites.
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

#: The shipped value of the key.  The guard spells it once, so a case can pin it.
SHIPPED_KEY = "ball_id"
#: The home module, and the name it holds the key under.
HOME = "src/shot_pot_gate.py"
HOME_NAME = "BALL_ID_KEY"
#: The line of the home statement, at the state the home landed in, and its text.
HOME_LINE = 895
HOME_FORM = '%s = "%s"' % (HOME_NAME, SHIPPED_KEY)
#: The two comment lines above the home, and the facts they must state.
COMMENT_LINES = (893, 894)
COMMENT_WORDS = ("one ball", "queue", "audit")
#: The line regex of the definition, for the case that pins the home line.
NAME_RE = re.compile(r"\s*%s\s*=" % HOME_NAME)
#: Every live site of the home name, as ``(line, kind)`` per module.  The kind is
#: ``home`` for the definition, ``import`` for the import of the home, ``dict``
#: for a key of a written row, ``get`` for a lookup and ``lookup`` for a
#: subscript that reads a row back.  A line holds two sites when it writes a row
#: and reads a row at once.  A moved, a new or a lost site must restate itself.
SITES = {
    HOME: ((895, "home"), (929, "dict"), (999, "dict"), (1045, "dict"),
           (1076, "dict")),
    "src/dense_queue.py": (
        (81, "import"), (189, "lookup"), (208, "lookup"), (218, "lookup"),
        (225, "dict"), (225, "lookup"), (262, "get"), (328, "lookup"),
        (342, "lookup"), (343, "dict"), (343, "lookup"), (399, "get"),
        (422, "get"), (459, "lookup"), (471, "lookup"), (479, "lookup"),
        (503, "get"), (510, "dict"), (527, "dict"), (527, "get"),
        (547, "dict"), (547, "get"), (559, "get"), (609, "lookup"),
        (643, "lookup"), (650, "lookup"), (661, "lookup"), (712, "lookup"),
        (713, "dict"), (713, "lookup")),
    "src/ball_association_audit.py": (
        (77, "import"), (85, "lookup"), (89, "lookup"), (91, "lookup"),
        (122, "import"), (126, "lookup"), (360, "import"), (363, "lookup")),
    "src/ball_association_ab.py": ((36, "import"), (183, "dict")),
}
#: The text of each of the four writer sites of the gate: the row shape itself.
WRITER_FORM = "%s: self.ball_id" % HOME_NAME
WRITERS = (929, 999, 1045, 1076)
#: The module each reader of the row takes the home from.
IMPORTS = {
    "src/dense_queue.py": "src.shot_pot_gate",
    "src/ball_association_audit.py": "src.shot_pot_gate",
    "src/ball_association_ab.py": "src.shot_pot_gate",
}
#: The light reader defers the import into its three functions, because the gate
#: imports the audit at the top of its own module.  A cycle is the reason.
DEFERRED = {"src/ball_association_audit.py": (77, 122, 360)}
#: The two readers that close no cycle take the name at the top of the module.
AT_TOP = {"src/dense_queue.py": 81, "src/ball_association_ab.py": 36}
#: The import of the gate that closes the cycle, and the name it takes.
AUDIT = "src/ball_association_audit.py"
AUDIT_MODULE = "src.ball_association_audit"
CYCLE_LINE = 86
CYCLE_NAME = "NEAREST_DISTANCE_PX_KEY"
#: The directories the anti-copy walk reads, and the floors that keep a vacuous
#: walk from passing.
PY_WALKED = ("src/**/*.py", "annotator/**/*.py", "tools/**/*.py",
             "scripts/**/*.py")
PAGE_WALKED = ("annotator/**/*.html", "annotator/**/*.js", "annotator/**/*.css")
SH_WALKED = ("scripts/**/*.sh", "tools/**/*.sh")
PY_FILE_FLOOR = 200
PAGE_FILE_FLOOR = 9
SH_FILE_FLOOR = 2
#: The cases of the house that write a row with the literal of the bytes.  A
#: rename of the value moves them with the home.
LITERAL_HOLDERS = ("tests/test_queue_decision.py", "tests/test_gate_threshold_keys.py")
#: The probes, each run in a fresh interpreter of this venv.
BIND_PROBE = "import src.shot_pot_gate as module; print(repr(module.%s))" % HOME_NAME
CYCLE_PROBE = ("import sys, src.ball_association_audit; "
               "print('src.shot_pot_gate' in sys.modules, 'numpy' in sys.modules, "
               "'cv2' in sys.modules)")
#: A previous queue document that carries the key as the literal of the bytes,
#: fed to the reader of the queue.  The document on disk is never rewritten, so a
#: rename of the value reddens this case.
PREVIOUS_PROBE = (
    "import json, pathlib, tempfile\n"
    "import src.dense_queue as queue\n"
    "row = [{'id': 9001, 'type': 'shot', 'provenance': {'ball_id': 't125-white'}}]\n"
    "path = pathlib.Path(tempfile.mkdtemp()) / 'previous.json'\n"
    "path.write_text(json.dumps(row))\n"
    "print(sorted(queue._previous_ids(path).items()))\n"
)


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
    imports numpy through ``src.motion_scan``, and this guard must not pull it
    into its own process to answer a string.  One case proves the run-time
    binding with a fresh interpreter instead.
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

    A site of the home name is a definition, an import of the name, a dict key of
    a written row, a lookup that reads a row back, or a subscript of a row.  A
    comment that names the name is no site of it, so the walk is the honest count.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == HOME_NAME or alias.asname == HOME_NAME
                   for alias in node.names):
                found.append((node.lineno, "import"))
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == HOME_NAME
                   for target in node.targets):
                found.append((node.lineno, "home"))
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None and ast.unparse(key) == HOME_NAME:
                    found.append((key.lineno, "dict"))
        elif isinstance(node, ast.Call):
            if node.args and ast.unparse(node.args[0]) == HOME_NAME:
                found.append((node.args[0].lineno, "get"))
        elif isinstance(node, ast.Subscript):
            if ast.unparse(node.slice) == HOME_NAME:
                found.append((node.slice.lineno, "lookup"))
    return sorted(set(found))


def imported_names(text: str, where: str, module: str) -> list:
    """Every local name one module imports from another, as ``(line, name)``."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                if alias.name == HOME_NAME:
                    found.append((node.lineno, alias.asname or alias.name))
    return sorted(found)


def body_imports(text: str, where: str, module: str) -> list:
    """Every module-level import of one module, as a line number."""
    tree = ast.parse(text, filename=where)
    return sorted(node.lineno for node in tree.body
                  if isinstance(node, ast.ImportFrom) and node.module == module)


def quoted_offences(relative: str, text: str, allowed_lines=()) -> list:
    """Every line of a file that spells the key as a quoted literal.

    A line of ``allowed_lines`` is the one home of that file, so it may spell the
    key.  Every other line that spells it is a copy, and the answer names it.
    """
    offenders = []
    for number, line in enumerate(text.splitlines(), start=1):
        if number in allowed_lines:
            continue
        if '"%s"' % SHIPPED_KEY in line or "'%s'" % SHIPPED_KEY in line:
            offenders.append(report(relative, number, line,
                                    "%r is a bare copy of the key; read %s of %s"
                                    % (SHIPPED_KEY, HOME_NAME, HOME)))
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
    """The one home of the key, and its value."""

    def test_the_home_names_the_shipped_key(self):
        """The constant of the home is the key of the served rows."""
        self.assertEqual(SHIPPED_KEY, home_value(),
                         report(HOME, HOME_LINE, source_lines(HOME)[HOME_LINE - 1],
                                "the home holds another value than %r" % SHIPPED_KEY))

    def test_the_home_line_of_the_module_carries_the_shipped_key(self):
        """One line defines the name, at the pinned number, with the pinned text."""
        lines = source_lines(HOME)
        found = home_sites()
        offenders = [report(HOME, number, text, "the home line must read %r" % HOME_FORM)
                     for number, text in found if text != HOME_FORM]
        if not found:
            offenders.append(report(HOME, HOME_LINE, lines[HOME_LINE - 1],
                                    "no line of the module defines %s" % HOME_NAME))
        elif [number for number, _ in found] != [HOME_LINE]:
            offenders.append(report(HOME, HOME_LINE, lines[HOME_LINE - 1],
                                    "the home lies at %s, not %d"
                                    % ([number for number, _ in found], HOME_LINE)))
        self.assertEqual([], offenders,
                         "the home of the key moved:\n" + "\n".join(offenders))

    def test_the_comment_above_the_home_names_the_one_ball(self):
        """The two comment lines state what the key names and who carries it."""
        lines = source_lines(HOME)
        text = " ".join(lines[number - 1] for number in COMMENT_LINES)
        offenders = [report(HOME, number, lines[number - 1],
                            "the comment above the home does not say %r; it says %r"
                            % (word, text))
                     for word in COMMENT_WORDS if word not in text]
        offenders.extend(report(HOME, number, lines[number - 1],
                                "the line above the home is no comment")
                         for number in COMMENT_LINES
                         if not lines[number - 1].lstrip().startswith("#"))
        self.assertEqual([], offenders,
                         "the comment above the home does not hold:\n"
                         + "\n".join(offenders))

    def test_the_home_binds_the_name_at_run_time(self):
        """A fresh interpreter answers the shipped value of the served key."""
        self.assertEqual(repr(SHIPPED_KEY), run_probe(BIND_PROBE),
                         "the import of the home does not bind %s to %r"
                         % (HOME_NAME, SHIPPED_KEY))

    def test_the_home_name_can_be_the_key_of_a_row(self):
        """The name is a string constant, so it can key a written row."""
        planted = ('def row(shot):\n'
                   '    return {%s: shot.ball_id}\n' % HOME_NAME)
        self.assertEqual([(2, "dict")], name_sites(planted, "src/planted.py"))


class SiteTests(unittest.TestCase):
    """Every site that writes or reads the key names the home."""

    def test_the_live_sites_are_the_ones_the_report_names(self):
        """45 sites in four files.  A move or a new site must state itself."""
        offenders = []
        total = 0
        for relative, pinned in sorted(SITES.items()):
            lines = source_lines(relative)
            found = name_sites(source_text(relative), relative)
            total += len(found)
            if sorted(pinned) != found:
                number = found[0][0] if found else 1
                offenders.append(report(relative, number, lines[number - 1],
                                        "the live sites are %s, not the pinned %s"
                                        % (found, sorted(pinned))))
        if total != 45:
            offenders.append(report(HOME, HOME_LINE, source_lines(HOME)[HOME_LINE - 1],
                                    "the four files carry %d sites, not 45" % total))
        self.assertEqual([], offenders,
                         "the live sites of the key moved:\n" + "\n".join(offenders))

    def test_every_site_reads_the_name_of_the_home(self):
        """The line of each site names the home, so the value has one spelling."""
        offenders = []
        for relative in sorted(SITES):
            lines = source_lines(relative)
            for number, kind in SITES[relative]:
                if kind == "home":
                    continue
                if HOME_NAME not in lines[number - 1]:
                    offenders.append(report(relative, number, lines[number - 1],
                                            "the site does not read %s of %s"
                                            % (HOME_NAME, HOME)))
        self.assertEqual([], offenders,
                         "a site of the key does not read the home:\n"
                         + "\n".join(offenders))

    def test_the_writers_of_the_row_carry_the_key_of_the_home(self):
        """The four row shapes of the gate write the name as the row key."""
        lines = source_lines(HOME)
        offenders = [report(HOME, number, lines[number - 1],
                            "the writer does not write %r" % WRITER_FORM)
                     for number in WRITERS if WRITER_FORM not in lines[number - 1]]
        self.assertEqual([], offenders,
                         "a writer of the gate does not carry the key:\n"
                         + "\n".join(offenders))


class ImportTests(unittest.TestCase):
    """Each reader takes the name from the home, and no cycle closes."""

    def test_every_reader_imports_the_home(self):
        """Every file of the row imports the name, and not a copy of it."""
        offenders = []
        for relative, module in sorted(IMPORTS.items()):
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
        self.assertEqual([], offenders,
                         "a reader does not import the home:\n" + "\n".join(offenders))

    def test_the_gate_names_the_audit_so_the_cycle_is_real(self):
        """The gate reads a name of the audit at the top, so the audit defers."""
        lines = source_lines(HOME)
        found = [node for node in ast.walk(ast.parse(source_text(HOME), filename=HOME))
                 if isinstance(node, ast.ImportFrom) and node.module == AUDIT_MODULE]
        offenders = []
        if not found:
            offenders.append(report(HOME, CYCLE_LINE, lines[CYCLE_LINE - 1],
                                    "the gate imports no name of %s, so the audit "
                                    "could take the gate at the top" % AUDIT))
        for node in found:
            names = [alias.name for alias in node.names]
            if CYCLE_NAME not in names:
                offenders.append(report(HOME, node.lineno, lines[node.lineno - 1],
                                        "the import of %s carries %s, not %s"
                                        % (AUDIT, names, CYCLE_NAME)))
        self.assertEqual([], offenders,
                         "the cycle that defers the import of the audit is gone:\n"
                         + "\n".join(offenders))

    def test_the_audit_defers_the_import_of_the_gate(self):
        """The body of the audit holds no import of the gate, and each local
        import names the reason."""
        lines = source_lines(AUDIT)
        text = source_text(AUDIT)
        offenders = []
        for number in body_imports(text, AUDIT, "src.shot_pot_gate"):
            offenders.append(report(AUDIT, number, lines[number - 1],
                                    "the import sits in the module body, and the top "
                                    "closes a cycle"))
        found = [number for number, _ in imported_names(text, AUDIT, "src.shot_pot_gate")]
        if found != list(DEFERRED[AUDIT]):
            number = found[0] if found else 1
            offenders.append(report(AUDIT, number, lines[number - 1],
                                    "the local imports are at %s, not the pinned %s"
                                    % (found, list(DEFERRED[AUDIT]))))
        for number in found:
            if "# local:" not in lines[number - 1]:
                offenders.append(report(AUDIT, number, lines[number - 1],
                                        "the local import does not name the reason "
                                        "in a '# local: <why>' comment"))
        self.assertEqual([], offenders,
                         "the audit does not defer the import of the gate:\n"
                         + "\n".join(offenders))

    def test_the_audit_alone_pulls_neither_the_gate_nor_numpy(self):
        """The lightness of the audit is measured, not asserted."""
        self.assertEqual("False False False", run_probe(CYCLE_PROBE),
                         "the audit alone pulls the gate, numpy or cv2")

    def test_the_readers_without_a_cycle_take_the_name_at_the_top(self):
        """The queue and the driver name the home in the module body."""
        offenders = []
        for relative, line in sorted(AT_TOP.items()):
            lines = source_lines(relative)
            found = body_imports(source_text(relative), relative, "src.shot_pot_gate")
            if line not in found:
                number = found[0] if found else 1
                offenders.append(report(relative, number, lines[number - 1],
                                        "the import of the home is at %s, not at the "
                                        "top of the module (%d)" % (found, line)))
        self.assertEqual([], offenders,
                         "a reader without a cycle defers the import:\n"
                         + "\n".join(offenders))


class ValueTests(unittest.TestCase):
    """The value of the key does not move, because the bytes on disk carry it."""

    def test_a_shipped_row_of_the_literal_key_still_answers_the_queue(self):
        """A queue document with the literal key feeds the reader of the queue."""
        answer = run_probe(PREVIOUS_PROBE)
        self.assertIn("t125-white", answer,
                      "the reader of the queue lost the row of the literal key: %r"
                      % answer)
        self.assertIn("9001", answer,
                      "the reader of the queue lost the id of the row: %r" % answer)

    def test_the_cases_of_the_house_still_spell_the_shipped_key(self):
        """A rename of the value must move the rows those cases write."""
        offenders = []
        for relative in LITERAL_HOLDERS:
            text = source_text(relative)
            if '"%s"' % SHIPPED_KEY not in text:
                offenders.append(report(relative, 1, source_text(relative).splitlines()[0],
                                        "the case spells no %r, so the value of the "
                                        "home moved alone" % SHIPPED_KEY))
        self.assertEqual([], offenders,
                         "the value of the key moved and the house did not:\n"
                         + "\n".join(offenders))


class WalkTests(unittest.TestCase):
    """The anti-copy walk of the tree, with its planted proofs."""

    def test_no_file_spells_the_key_again(self):
        """One home, and every other spelling of the key is an offender."""
        offenders = []
        groups = ((PY_WALKED, PY_FILE_FLOOR, "python"),
                  (PAGE_WALKED, PAGE_FILE_FLOOR, "page"),
                  (SH_WALKED, SH_FILE_FLOOR, "shell"))
        for patterns, floor, what in groups:
            files = walked(patterns)
            self.assertGreater(len(files), floor,
                               "the walk read %d %s files; it is not the tree"
                               % (len(files), what))
            for path in files:
                relative = path.relative_to(ROOT).as_posix()
                allowed = (HOME_LINE,) if relative == HOME else ()
                offenders.extend(quoted_offences(
                    relative, path.read_text(encoding="utf-8", errors="replace"),
                    allowed))
        self.assertEqual([], offenders,
                         "a second home of the key stands in the tree:\n"
                         + "\n".join(offenders))

    def test_the_walk_reports_a_planted_copy(self):
        """Honesty: a planted copy of the key becomes an offender, named."""
        planted = ('def row(shot):\n'
                   '    return {"kind": "shot", "%s": shot.ball_id}\n' % SHIPPED_KEY)
        offenders = quoted_offences("src/planted.py", planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("src/planted.py:2:", offenders[0])
        self.assertIn(SHIPPED_KEY, offenders[0])
        self.assertIn("shot.ball_id", offenders[0])

    def test_the_walk_accepts_the_home_spelling(self):
        """The home spelling is no copy, and the walk reads it as a site."""
        planted = ('def row(shot):\n'
                   '    return {%s: shot.ball_id}\n' % HOME_NAME)
        self.assertEqual([], quoted_offences("src/planted.py", planted),
                         "the home spelling counts as a bare literal")
        self.assertEqual([(2, "dict")], name_sites(planted, "src/planted.py"))


if __name__ == "__main__":
    unittest.main()
