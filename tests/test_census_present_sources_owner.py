"""The census key ``claim_color_present_sources`` has one home, and three readers name it.

The walk of round 107 found four live spellings of one key of the fused census:

* ``src/ball_census.py:925`` - ``window_summary`` writes the key of the summary;
* ``src/eval_events.py:644`` - ``probe_pot`` reads the summary into ``PotEvidence``;
* ``src/eval_events.py:1037`` - the report line of the console reads the key back;
* ``src/event_gates.py:356`` - the row of ``pot_gate`` carries it to the gate report.

No case named the key.  ``git grep -nF '"claim_color_present_sources"' -- tests/``
answered nothing, so a rename of the served key stayed silent in every reader.

The home is ``src/ball_census.py:798``::

    CLAIM_COLOR_PRESENT_SOURCES_KEY = "claim_color_present_sources"

The home sits at the head of the summary block of its writer.  ``window_summary``
writes the summary of one colour claim, and the three readers take the name there.
The five sibling keys of the block stay as they were: this round holds one name.

The cycle.  ``src/ball_census.py:44`` imports ``num_or_none`` of ``src/event_gates``,
so the gate cannot import the home at the top of its own module.  The gate reads the
name with a local import inside ``pot_gate``, and a case proves in a fresh
interpreter that the import of ``src/event_gates`` alone leaves ``src.ball_census``
out of ``sys.modules``.

The field.  ``PotEvidence.claim_color_present_sources`` (``src/event_gates.py:353``)
is the field the gate row copies, and the keyword of ``probe_pot``
(``src/eval_events.py:644``) must keep the same name.  A case holds the pair equal,
because a rename on one side alone would serve an empty number.

Every case reads its copy, and pins the NAME of the home, not only the value: the
import of each reader, the line of each site, and the run-time binding of the name.

Run: ``./scripts/pool-test.sh python test_census_present_sources_owner``

Measured 2026-10-13, Python 3.14.6: the anti-copy walk reads 291 python files of
5082638 characters under ``src/``, ``tools/``, ``scripts/`` and ``annotator/`` in
0.010 s.  The three probes of fresh interpreters cost about 5 s of the module.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The shipped value of the key.  The guard spells it once, so the walk may read it.
SHIPPED_KEY = "claim_color_present_sources"
#: The home module, the name it holds the key under, and the line of the statement.
HOME = "src/ball_census.py"
HOME_NAME = "CLAIM_COLOR_PRESENT_SOURCES_KEY"
HOME_LINE = 794
HOME_FORM = '%s = "%s"' % (HOME_NAME, SHIPPED_KEY)
#: The line regex of the definition, for the case that pins the home line.
NAME_RE = re.compile(r"\s*%s\s*=" % HOME_NAME)
#: Every live site of the home name, as ``(line, kind)`` per module.  The kind is
#: ``home`` for the definition, ``import`` for the import of the home, ``dict``
#: for a key of a written row, ``get`` for a lookup that reads a row back, and
#: ``lookup`` for a subscript of the summary that is written.
SITES = {
    HOME: ((794, "home"), (925, "lookup")),
    "src/eval_events.py": ((48, "import"), (644, "get"), (1037, "get")),
    "src/event_gates.py": ((332, "import"), (352, "dict")),
}
#: The module each reader takes the home from.
IMPORTS = {
    "src/eval_events.py": "src.ball_census",
    "src/event_gates.py": "src.ball_census",
}
#: The gate, the function of its local import, and the line of that import.
GATE = "src/event_gates.py"
GATE_FUNCTION = "pot_gate"
GATE_IMPORT_LINE = 332
#: The reader, the evidence class, and the two lines of the field and its keyword.
READER = "src/eval_events.py"
EVIDENCE_CLASS = "PotEvidence"
FIELD_LINE = 284
FIELD_KEYWORD_LINE = 644
#: The five sibling keys of the summary block.  This round holds one name only, so
#: a case reads them and reports a change of any of them.
SIBLING_KEYS = ("claim_color", "claim_color_present", "claim_color_present_measured",
                "claim_color_present_hits", "claim_color_unique")
#: The directories the anti-copy walk reads.
PY_WALKED = ("src/**/*.py", "tools/**/*.py", "scripts/**/*.py", "annotator/**/*.py")
#: The floor that keeps a vacuous walk from passing.
PY_FILE_FLOOR = 200
#: The probes, each run in a fresh interpreter of this venv.
BIND_PROBE = "import src.ball_census as module; print(module.%s)" % HOME_NAME
CYCLE_PROBE = "import sys, src.event_gates; print('src.ball_census' in sys.modules)"
READER_PROBE = ("import sys, src.eval_events as module; print('src.ball_census' in sys.modules, "
                "module.%s)" % HOME_NAME)
#: The reports a shipped run wrote.  They carry the bytes of the spelling before the
#: home landed, so a reader of them proves the identity against disk and not source.
SERVED_REPORTS = ("out/scan30/eval_events.json", "out/scan30/gate_report.json",
                  "out/scan30/probe_events.json")
SERVED_PAYLOADS = "out/scan30/probe_events.json"


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
    carries the census and pulls heavy libraries, and this guard must not pull them
    into its own process to answer a string.  A case proves the run-time binding in
    a fresh interpreter instead.
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

    A site of the home name is a definition, an import of the name, a key of a
    written row, a lookup that reads a row back, or a subscript of the summary.
    A comment that names the name is no site of it, so the walk is the honest count.
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


def nested_imports(text: str, where: str, module: str) -> list:
    """Every import of the home inside a function, as ``(line, function)``."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.ImportFrom) or child.module != module:
                continue
            if any(alias.name == HOME_NAME for alias in child.names):
                found.append((child.lineno, node.name))
    return sorted(set(found))


def field_line(text: str, where: str, class_name: str, field: str) -> int:
    """The line of one annotated field of a class, or 0 when the class has no such field."""
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name) \
                        and child.target.id == field:
                    return child.target.lineno
    return 0


def keyword_lines(text: str, where: str, function: str, keyword: str) -> list:
    """Every line of a call to one function that passes one keyword, as ``(line, name)``."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == function:
            for kw in node.keywords:
                if kw.arg == keyword:
                    found.append((kw.value.lineno, kw.arg))
    return sorted(found)


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


def key_carrying_dicts(relative: str) -> list:
    """Every dict of one report on disk that carries the shipped key."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if SHIPPED_KEY in node:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads((ROOT / relative).read_text(encoding="utf-8")))
    return found


def payload_summaries(relative: str) -> list:
    """The probe payloads of one report, as ``(name, summary)``, sorted by name."""
    data = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    payloads = data.get("payloads") or {}
    return sorted((name, summary) for name, summary in payloads.items()
                  if isinstance(summary, dict))


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

    def test_the_home_names_the_shipped_key(self):
        """The value is the key a census report on disk carries."""
        self.assertEqual(SHIPPED_KEY, home_value(),
                         "%s:%s moved; a census report on disk carries %r"
                         % (HOME, HOME_NAME, SHIPPED_KEY))

    def test_the_home_line_of_the_module_carries_the_shipped_key(self):
        """The case that pins the home at ``path:line``."""
        sites = home_sites()
        self.assertEqual(1, len(sites),
                         "%s holds %d definitions of %s: %s"
                         % (HOME, len(sites), HOME_NAME, [site[0] for site in sites]))
        number, text = sites[0]
        self.assertIn(HOME_FORM, text,
                      report(HOME, number, text,
                             "the line does not assign %r to %s"
                             % (SHIPPED_KEY, HOME_NAME)))
        self.assertEqual(HOME_LINE, number,
                         report(HOME, number, text,
                                "%s stood at line %d when the home landed; a move "
                                "must restate it in the report" % (HOME_NAME, HOME_LINE)))

    def test_the_home_line_is_the_head_of_the_summary_block(self):
        """The home sits with the writer of the summary, and not in a far module."""
        lines = source_lines(HOME)
        after = [number for number, text in enumerate(lines, start=1)
                 if text.startswith("def window_summary")]
        self.assertTrue(after, "%s holds no window_summary" % HOME)
        self.assertLess(HOME_LINE, after[0],
                        "%s:%d stands after the writer at line %d"
                        % (HOME, HOME_LINE, after[0]))
        self.assertLess(after[0] - HOME_LINE, 40,
                        "%s:%d stands %d lines above the writer; the home left the block"
                        % (HOME, HOME_LINE, after[0] - HOME_LINE))

    def test_the_home_binds_the_name_at_run_time(self):
        """The shipped module answers the value when a reader imports it."""
        self.assertEqual(SHIPPED_KEY, run_probe(BIND_PROBE),
                         "%s does not answer %s when a reader imports it"
                         % (HOME, HOME_NAME))

    def test_the_summary_block_writes_the_key_through_the_home(self):
        """The writer of the summary takes its key from the home."""
        line = source_lines(HOME)[SITES[HOME][1][0] - 1]
        self.assertIn(HOME_NAME, line,
                      report(HOME, SITES[HOME][1][0], line,
                             "the write of the summary does not read %s" % HOME_NAME))
        self.assertIn('presence["sources"]', line,
                      report(HOME, SITES[HOME][1][0], line,
                             "the write no longer stores the sources of the colour claim"))

    def test_the_sibling_keys_of_the_block_stand_as_they_were(self):
        """This round holds one name.  A change of a sibling key must report itself."""
        text = source_text(HOME)
        offenders = []
        for key in SIBLING_KEYS:
            if '"%s"' % key not in text:
                offenders.append(report(HOME, HOME_LINE, "",
                                        "%r left the summary block" % key))
        self.assertEqual([], offenders,
                         "a sibling key of the block moved:\n" + "\n".join(offenders))


class ReaderTests(unittest.TestCase):
    """The two readers of ``src/eval_events.py`` and the gate name the home."""

    def test_every_reader_imports_the_home(self):
        """Every reader takes the name from the home, and the name is the home name."""
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

    def test_the_reader_takes_the_home_at_the_top_of_its_module(self):
        """``src/eval_events.py`` reads the name at the top, and pulls the home."""
        text = source_text(READER)
        lines = source_lines(READER)
        if not body_imports(text, READER, IMPORTS[READER]):
            offenders = [report(READER, 1, lines[0],
                                "the import of %s sits inside a call, not at the top "
                                "of the module" % IMPORTS[READER])]
        else:
            offenders = []
        self.assertEqual([], offenders, "\n".join(offenders))
        self.assertEqual("True %s" % SHIPPED_KEY, run_probe(READER_PROBE),
                         "%s does not read the home name when a reader imports it"
                         % READER)

    def test_the_gate_imports_the_home_inside_its_function(self):
        """Why the gate reads the name locally: a top-level import closes a cycle.

        ``src/ball_census.py:44`` imports ``num_or_none`` of the gate, so the gate
        cannot import the census module at the top.  The case holds the local import,
        the empty top of the gate, and the answer of two fresh interpreters.
        """
        text = source_text(GATE)
        lines = source_lines(GATE)
        self.assertEqual([], body_imports(text, GATE, IMPORTS[GATE]),
                         "%s imports %s at the top of its module, and that closes a "
                         "cycle with %s:44" % (GATE, IMPORTS[GATE], HOME))
        nested = nested_imports(text, GATE, IMPORTS[GATE])
        self.assertEqual([(GATE_IMPORT_LINE, GATE_FUNCTION)], nested,
                         "%s holds the local import at %s, not at (%d, %s)"
                         % (GATE, nested, GATE_IMPORT_LINE, GATE_FUNCTION))
        self.assertIn(HOME_NAME, lines[GATE_IMPORT_LINE - 1],
                      report(GATE, GATE_IMPORT_LINE, lines[GATE_IMPORT_LINE - 1],
                             "the local import does not take %s" % HOME_NAME))
        self.assertEqual("False", run_probe(CYCLE_PROBE),
                         "%s pulls %s at the top of its module"
                         % (GATE, HOME))

    def test_every_site_reads_the_key_through_the_home(self):
        """Every site that writes or reads the key names the home."""
        offenders = []
        for relative in sorted(SITES):
            lines = source_lines(relative)
            for number, kind in SITES[relative]:
                if kind not in ("dict", "get", "lookup"):
                    continue
                if HOME_NAME not in lines[number - 1]:
                    offenders.append(report(relative, number, lines[number - 1],
                                            "the site does not read %s of %s"
                                            % (HOME_NAME, HOME)))
        self.assertEqual([], offenders,
                         "a site of the key does not read the home:\n"
                         + "\n".join(offenders))

    def test_the_live_sites_are_the_ones_the_report_names(self):
        """Seven sites in three files.  A move or a new site must state itself."""
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
                         "the live sites of the key moved:\n" + "\n".join(offenders))

    def test_the_gate_row_carries_the_key_of_the_home(self):
        """The gate builds the row key of the served report from the home.

        The row carries the value, and not the name, because the gate report on disk
        carries the value.  The case reads the number the evidence held under the
        shipped key, so a drift of the value is visible here.
        """
        from src.event_gates import PotEvidence, pot_gate
        row = pot_gate({"color": None}, PotEvidence(available=False, note="no probe frames"))
        self.assertIn(home_value(), row.numbers,
                      "%s does not carry the row key %r" % (GATE, home_value()))
        row = pot_gate({"color": None},
                       PotEvidence(available=False, note="no probe frames",
                                   claim_color_present_sources={"sam3": 5}))
        self.assertEqual({"sam3": 5}, row.numbers.get(home_value()),
                         "%s does not serve the sources of the claim under %r"
                         % (GATE, home_value()))

    def test_the_field_of_the_evidence_keeps_the_shipped_name(self):
        """The field of the evidence and the keyword of the reader keep one name.

        A rename on one side alone leaves the served number empty, and no reader of
        the report would see the sources of the colour claim again.
        """
        text = source_text(GATE)
        lines = source_lines(GATE)
        number = field_line(text, GATE, EVIDENCE_CLASS, SHIPPED_KEY)
        self.assertEqual(FIELD_LINE, number,
                         report(GATE, number or 1, lines[(number or 1) - 1],
                                "the field %s stood at line %d when the home landed"
                                % (SHIPPED_KEY, FIELD_LINE)))
        keywords = keyword_lines(source_text(READER), READER, EVIDENCE_CLASS, SHIPPED_KEY)
        self.assertEqual([(FIELD_KEYWORD_LINE, SHIPPED_KEY)], keywords,
                         "%s passes the keyword at %s, not at (%d, %s)"
                         % (READER, keywords, FIELD_KEYWORD_LINE, SHIPPED_KEY))

    def test_the_report_line_reads_the_number_of_the_home(self):
        """The console line reads the sources of the claim under the shipped key."""
        from src.eval_events import _census_line
        row = {"kind": "pot",
               "verdict": {"numbers": {home_value(): {"sam3": 5},
                                       "claim_color_present": True}}}
        self.assertIn("sam3", _census_line(row),
                      "%s does not read the sources under the shipped key %r"
                      % (READER, home_value()))
        other = {"kind": "pot",
                 "verdict": {"numbers": {HOME_NAME: {"sam3": 5},
                                         "claim_color_present": True}}}
        self.assertNotIn("'sam3': 5", _census_line(other),
                         "%s reads the name %s instead of the value %r"
                         % (READER, HOME_NAME, home_value()))


class IdentityTests(unittest.TestCase):
    """The reports on disk carry the old spelling, and the reader still reads it."""

    def test_the_shipped_reports_still_carry_the_key(self):
        """The three reports of a shipped run carry the key, with the shape it had."""
        offenders = []
        total = 0
        for relative in SERVED_REPORTS:
            rows = key_carrying_dicts(relative)
            total += len(rows)
            for row in rows:
                if not isinstance(row[SHIPPED_KEY], (dict, type(None))):
                    offenders.append(report(relative, 1, "",
                                            "the key carries %r"
                                            % (row[SHIPPED_KEY],)))
        self.assertGreater(total, 30,
                           "the case read %d rows of the shipped reports; it is not "
                           "the shipped set" % total)
        self.assertEqual([], offenders,
                         "a shipped report carries another shape under the key:\n"
                         + "\n".join(offenders))

    def test_a_shipped_payload_still_answers_the_reader(self):
        """The payloads of the probe report were written before the home landed."""
        from src.eval_events import _census_line
        read = 0
        for name, summary in payload_summaries(SERVED_PAYLOADS):
            if SHIPPED_KEY not in summary:
                continue
            read += 1
            numbers = {"claim_color_present": True, home_value(): summary[SHIPPED_KEY]}
            line = _census_line({"kind": "pot", "verdict": {"numbers": numbers}})
            if summary[SHIPPED_KEY]:
                self.assertIn(str(summary[SHIPPED_KEY]), line,
                              "%s reads no sources of the shipped payload %s"
                              % (READER, name))
        self.assertGreater(read, 10,
                           "the case read %d payloads of %s; it is not the shipped set"
                           % (read, SERVED_PAYLOADS))


class WalkTests(unittest.TestCase):
    """The anti-copy walk of the python tree, with its planted proofs."""

    def test_no_python_file_spells_the_key_again(self):
        offenders = []
        files = walked(PY_WALKED)
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            allowed = (HOME_LINE,) if relative == HOME else ()
            offenders.extend(quoted_offences(relative, path.read_text(encoding="utf-8"),
                                             allowed))
        self.assertGreater(len(files), PY_FILE_FLOOR,
                           "the walk read %d files; it is not the tree" % len(files))
        self.assertEqual([], offenders,
                         "a second home of the key stands in the source tree:\n"
                         + "\n".join(offenders))

    def test_the_walk_reports_a_planted_copy(self):
        """A planted dict copy is reported as ``path:line: <text>``."""
        planted = ('def pot_row(claim):\n'
                   '    return {"claim_color_present_sources": claim["sources"]}\n')
        offenders = quoted_offences("src/planted.py", planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("src/planted.py:2:", offenders[0])
        self.assertIn("claim_color_present_sources", offenders[0])
        self.assertIn('claim["sources"]', offenders[0])

    def test_the_walk_accepts_the_home_spelling(self):
        """A reading of the home name counts as no copy."""
        planted = ('def pot_row(claim):\n'
                   '    return {CLAIM_COLOR_PRESENT_SOURCES_KEY: claim["sources"]}\n')
        self.assertEqual([], quoted_offences("src/planted.py", planted),
                         "the home spelling counts as a bare literal")
        self.assertEqual([(2, "dict")], name_sites(planted, "src/planted.py"))


if __name__ == "__main__":
    unittest.main()
