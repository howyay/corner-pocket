"""The tiny-ball probe directory and the three artifact names have one home.

Round 105 measured the defect.  The probe directory ``out/tiny_ball_probe``, the
checkpoint name ``960x540-scratch.pt`` and the frozen held-out name
``held_frozen.json`` stood in five live readers at once: the pipeline stage
(``annotator/pipeline_stages.py``), the trainer (``src/tiny_ball_net.py``), the
labeller (``src/fast_ball_labels.py``), the false-positive audit
(``src/ball_fp_audit.py``) and the held-out stack probe (``tests/ball_stack_ab.py``).
A second copy drifted in silence, because no case read two copies: a rename of one
file had to land in five files at once.

Round 106 measured the same defect on a fourth name, the labeller output
``new_labels.json``: the labeller wrote it and the trainer read it, each from its own
quoted spelling.  The round-106 repair moves that name into the same home.

The repair gives the four names one home, ``src/tiny_ball_probe.py``, and each
reader joins those names to its own root.  The file system root therefore stays
local to each reader and the owner states no root of its own.

The cases below hold that shape in seven ways:

1. one case reads the three values from the module and proves that the module
   states each one as its own statement, at the line measured on 2026-10-14;
2. one case proves that the module imports the standard library alone, so the
   light pipeline stage can read it without making ``cv2``, ``numpy`` or ``torch``
   a dependency;
3. one ``ast`` walk over the five reader files reports a constant that spells a
   probe name again, and one case proves that the walk reports a planted copy;
4. one case reads every declared read site and every command default that answers
   the checkpoint path, and compares each value against the path the owner builds;
5. one case reads the five copies that stand outside the write scope of the
   repair -- three test files whose own cases state the probe path -- and fails
   when one drifts.  A planted drift proves that the report names the file and the
   line.
6. three cases hold the fourth name, the labeller output of round 106: one reads
   that name from the owner and proves that both readers build from it, one pins
   the shipped file name against the owner line, and one walks every ``.py`` file
   under ``src/`` and reports a quoted spelling outside the owner.

The walk of the copies found eleven copies.  Their live lines are
``annotator/pipeline_stages.py:78``, ``src/tiny_ball_net.py:189``,
``src/tiny_ball_net.py:792``, ``src/fast_ball_labels.py:268``,
``src/fast_ball_labels.py:408``, ``src/fast_ball_labels.py:417``,
``src/fast_ball_labels.py:418``, ``src/ball_fp_audit.py:86``,
``src/ball_fp_audit.py:434``, ``tests/ball_stack_ab.py:380`` and
``tests/ball_stack_ab.py:383``.  The repair added import lines above those files,
so the numbers of the walk moved.  The numbers here are the live ones.

What this module cannot see, and therefore does not claim:

* it reads text and module values, not behaviour.  A path built at run time from
  parts no constant holds stays invisible to the constant scan;
* prose may name the path.  A docstring or a bare string statement is a comment,
  and the walk skips it.  Only a constant that a reader could use is an offence;
* the four names are held by value.  A reader that renames its own local binding
  of an owner name passes, because the case reads the value each module holds;
* the copies outside the write scope are pinned by line number, measured on
  2026-10-14.  An edit above one of those lines moves the line and fails the case:
  that failure names the file, the line and the text it holds now.

Run: ``./scripts/pool-test.sh python test_tiny_ball_probe_path_owner``
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The one module that states the probe directory and the two artifact names.
OWNER = "src/tiny_ball_probe.py"

#: The three names of the owner, in the order of its text.
OWNER_NAMES = ("PROBE_DIR_NAME", "CHECKPOINT_NAME", "HELD_FROZEN_NAME")

#: The line of the owner that states each name, and the kind of value it holds.
#: The values themselves are read from the module; no case spells one again.
OWNER_LINES = {"PROBE_DIR_NAME": 28, "CHECKPOINT_NAME": 33, "HELD_FROZEN_NAME": 37}
OWNER_KINDS = {"PROBE_DIR_NAME": Path, "CHECKPOINT_NAME": str, "HELD_FROZEN_NAME": str}

#: The statement the owner must make of each name, filled with the value the
#: module holds.  A reader that edits the statement of a name fails this form.
OWNER_FORMS = {
    "PROBE_DIR_NAME": 'PROBE_DIR_NAME = Path("%s")',
    "CHECKPOINT_NAME": 'CHECKPOINT_NAME = "%s"',
    "HELD_FROZEN_NAME": 'HELD_FROZEN_NAME = "%s"',
}

#: The module a reader imports the names from.
OWNER_MODULE = "src.tiny_ball_probe"

#: The five reader files of the write scope.  Each one imports the owner.
READER_FILES = (
    "annotator/pipeline_stages.py",
    "src/tiny_ball_net.py",
    "src/fast_ball_labels.py",
    "src/ball_fp_audit.py",
    "tests/ball_stack_ab.py",
)
READER_FILE_COUNT = 5

#: The line of each reader that joins an owner name to its own root, and the owner
#: names that line must read.  Each line was measured on 2026-10-14, after the
#: repair, so the numbers are the live ones.
READ_SITES = (
    ("annotator/pipeline_stages.py", 78, ("PROBE_DIR_NAME", "CHECKPOINT_NAME")),
    ("src/tiny_ball_net.py", 61, ("PROBE_DIR_NAME",)),
    ("src/tiny_ball_net.py", 129, ("PROBE_DIR_NAME",)),
    ("src/tiny_ball_net.py", 189, ("HELD_FROZEN_NAME",)),
    ("src/tiny_ball_net.py", 792, ("CHECKPOINT_NAME",)),
    ("src/fast_ball_labels.py", 62, ("PROBE_DIR_NAME",)),
    ("src/fast_ball_labels.py", 268, ("PROBE_DIR_NAME", "HELD_FROZEN_NAME")),
    ("src/fast_ball_labels.py", 408, ("PROBE_DIR_NAME", "CHECKPOINT_NAME")),
    ("src/fast_ball_labels.py", 417, ("PROBE_DIR_NAME",)),
    ("src/fast_ball_labels.py", 418, ("PROBE_DIR_NAME",)),
    ("src/ball_fp_audit.py", 84, ("PROBE_DIR_NAME",)),
    ("src/ball_fp_audit.py", 86, ("CHECKPOINT_NAME",)),
    ("src/ball_fp_audit.py", 434, ("HELD_FROZEN_NAME",)),
    ("tests/ball_stack_ab.py", 380, ("PROBE_DIR_NAME", "CHECKPOINT_NAME")),
    ("tests/ball_stack_ab.py", 383, ("PROBE_DIR_NAME",)),
)
READ_SITE_COUNT = 15

#: The command defaults that answer with the probe checkpoint path.  The trainer
#: declares ``--bitmap`` three times; only the report subcommand answers the probe
#: checkpoint, so the case takes the one default that names an owner name.
DEFAULT_SITES = (
    ("src/fast_ball_labels.py", "--bitmap"),
    ("src/tiny_ball_net.py", "--bitmap"),
    ("tests/ball_stack_ab.py", "--checkpoint"),
)
DEFAULT_SITE_COUNT = 3

#: The five copies that stand outside the write scope of the repair.  Each entry
#: is the file, the line measured on 2026-10-14, and the verb of the owner value
#: the line must spell: ``FULL`` is the directory joined to the checkpoint name,
#: ``NAME`` is the checkpoint name alone, and ``PARTS`` is every part of the
#: directory.  No case edits these three files; the case reads them.
OUTSIDE_SITES = (
    ("tests/test_pipeline_stages.py", 405, "FULL"),
    ("tests/test_pipeline_stages.py", 471, "NAME"),
    ("tests/test_live_processing.py", 51, "FULL"),
    ("tests/test_live_processing.py", 84, "FULL"),
    ("tests/test_ball_fp_audit.py", 98, "PARTS"),
)
OUTSIDE_SITE_COUNT = 5

#: The bite site: the line a text edit turns red, and the proof case reads.
BITE_SITE = ("tests/test_live_processing.py", 51)

#: The fourth name of the owner: the labeller's output file inside the probe
#: directory.  Round 106 gave this name one home, because the labeller wrote it
#: and the trainer read it as a second, silent copy.  The value itself is read
#: from the module; no case spells it again.
LABELS_NAME = "LABELS_NAME"

#: The line of the owner that states the labels name, and the shape of that
#: statement.  The line was measured on 2026-10-13, after the round-106 repair.
LABELS_LINE = 42
LABELS_FORM = 'LABELS_NAME = "%s"'

#: The line of the labeller that builds its output path from the labels name.
LABELS_OUT_SITE = ("src/fast_ball_labels.py", 62)

#: The two modules of the round-106 repair.  Each one reads the labels name from
#: the owner: the labeller builds its output path from it, and the trainer reads
#: the file by it.
LABELS_READERS = ("src/fast_ball_labels.py", "src/tiny_ball_net.py")
LABELS_READER_COUNT = 2

#: The line of each reader that must read the labels name.
LABELS_SITES = (
    LABELS_OUT_SITE,
    ("src/tiny_ball_net.py", 129),
)
LABELS_SITE_COUNT = 2

#: The files a quoted spelling of the labels name must not stand in.  The walk
#: takes every ``.py`` file under ``src/`` and skips the owner alone, so a third
#: home fails the case.  The floor holds the walk open: a walk that reads an
#: almost empty tree must not pass for a clean one.
SRC_MODULE_FLOOR = 200

#: The shortest reader text this module accepts.  A scan that reads an empty file
#: reports no offence, and no offence must not pass for a clean tree.
SHORTEST_READER = 500

#: The ``path:line: <text>`` shape of every report this module makes.
LOCATION = re.compile(r"^(?P<path>[^\s:]+):(?P<line>\d+): (?P<text>.*)$")


def read(relative):
    """The text of one file of this checkout, with its line endings kept."""
    return (ROOT / relative).read_text(encoding="utf-8")


def owner_values():
    """The three values the owner module itself holds, read by import."""
    from src import tiny_ball_probe as owner
    return {name: getattr(owner, name) for name in OWNER_NAMES}


def owner_needles(values):
    """The three texts a second home must not spell: the directory and the names."""
    return (values["PROBE_DIR_NAME"].name, values["CHECKPOINT_NAME"],
            values["HELD_FROZEN_NAME"])


def owner_statement(name, value):
    """The statement the owner must make of one name, as its own text."""
    text = value.as_posix() if isinstance(value, Path) else str(value)
    return OWNER_FORMS[name] % text


def line_text(text, number):
    """The stripped text of one line, or None when the text holds no such line."""
    lines = text.splitlines()
    if 0 < number <= len(lines):
        return lines[number - 1].strip()
    return None


def line_constants(text, number):
    """Every string constant that starts on one line of a source text."""
    found = []
    for node in ast.walk(ast.parse(text, filename="<line>")):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.lineno == number:
            found.append(node.value)
    return found


def imported_roots(text):
    """Every module name one source text imports, at its root."""
    found = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            found.add(node.module.split(".")[0])
    return found


def named_imports(text):
    """Every module one source text names in a ``from ... import`` statement."""
    found = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def prose_ids(tree):
    """The id of every string constant that is prose, not a value.

    A docstring is the leading bare string statement of a module, a class or a
    function, and a bare string statement inside a body is a note.  Neither is a
    value a reader can use, so the walk of the copies skips both.
    """
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            found.add(id(node.value))
    return found


def spelled_copies(label, text, needles):
    """Every constant of one source text that spells a probe name again.

    One offending constant gives one entry, as ``path:line: <text> spells <name>
    again; read <owner>``.  The entry repeats the line, so a reader sees why the
    line failed without opening the file.
    """
    tree = ast.parse(text, filename=str(label))
    prose = prose_ids(tree)
    found = []
    for node in ast.walk(tree):
        if id(node) in prose:
            continue
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        for needle in needles:
            if needle and needle in node.value:
                line = line_text(text, node.lineno) or ""
                found.append("%s:%d: %s spells %s again; read %s"
                             % (label, node.lineno, line, needle, OWNER))
                break
    return found


def site_reports(texts, sites):
    """The read sites whose line does not read the owner names it must read.

    Each report is ``path:line: <text> does not read <names>``.  A site whose line
    is gone is reported as such.  When another line of the file reads every name
    of the site, the report adds that line, so a moved site is named by its live
    line as well.
    """
    found = []
    for path, number, names in sites:
        text = texts[path]
        line = line_text(text, number)
        if line is None:
            found.append("%s:%d: the line is absent; the site moved" % (path, number))
            continue
        missing = [name for name in names if name not in line]
        if not missing:
            continue
        found.append("%s:%d: %s does not read %s" % (path, number, line, ", ".join(missing)))
        for other, other_line in enumerate(text.splitlines(), start=1):
            if other == number:
                continue
            if all(name in other_line for name in names):
                found.append("%s:%d: %s reads %s; the site moved"
                             % (path, other, other_line.strip(), ", ".join(names)))
    return found


def site_values(values):
    """The owner text each verb of the outside sites must spell."""
    return {
        "FULL": ((values["PROBE_DIR_NAME"] / values["CHECKPOINT_NAME"]).as_posix(),),
        "NAME": (values["CHECKPOINT_NAME"],),
        "PARTS": tuple(values["PROBE_DIR_NAME"].parts),
    }


def outside_reports(values, texts, sites):
    """The pinned copies that no longer spell the owner text they must spell.

    Each report is ``path:line: <text> does not hold <value>``, with the line's own
    text, so a reader sees the drift and where it stands.
    """
    wanted = site_values(values)
    found = []
    for path, number, verb in sites:
        text = texts[path]
        line = line_text(text, number)
        if line is None:
            found.append("%s:%d: the line is absent; the copy moved" % (path, number))
            continue
        held = line_constants(text, number)
        expected = wanted[verb]
        if all(part in held for part in expected):
            continue
        found.append("%s:%d: %s does not hold %s" % (path, number, line, " + ".join(expected)))
    return found


def labels_value():
    """The labels file name the owner module itself holds, read by import."""
    from src import tiny_ball_probe as owner
    return getattr(owner, LABELS_NAME, None)


def labels_site_reports(texts):
    """The reader lines that do not read the labels name of the owner.

    Each report is ``path:line: <text> does not read LABELS_NAME``.  When another
    line of the same file reads the name, the report adds that line, so a moved
    site is named by its live line as well.
    """
    found = []
    for path, number in LABELS_SITES:
        text = texts[path]
        line = line_text(text, number)
        if line is None:
            found.append("%s:%d: the line is absent; the site moved" % (path, number))
            continue
        if LABELS_NAME in line:
            continue
        found.append("%s:%d: %s does not read %s" % (path, number, line, LABELS_NAME))
        for other, other_line in enumerate(text.splitlines(), start=1):
            if other != number and LABELS_NAME in other_line:
                found.append("%s:%d: %s reads %s; the site moved"
                             % (path, other, other_line.strip(), LABELS_NAME))
    return found


def labels_import_reports(texts):
    """The reader that does not take the labels name from the owner module.

    Each report is ``path:line: <text> does not take LABELS_NAME from <owner>``,
    so the import line that lost the name is named with its own text.
    """
    found = []
    for path in LABELS_READERS:
        text = texts[path]
        nodes = [node for node in ast.walk(ast.parse(text, filename=path))
                 if isinstance(node, ast.ImportFrom) and node.module == OWNER_MODULE]
        if not nodes:
            found.append("%s: the reader imports no name of %s" % (path, OWNER_MODULE))
            continue
        if any(LABELS_NAME in {alias.name for alias in node.names} for node in nodes):
            continue
        node = nodes[0]
        found.append("%s:%d: %s does not take %s from %s"
                     % (path, node.lineno, line_text(text, node.lineno), LABELS_NAME,
                        OWNER_MODULE))
    return found


def src_modules():
    """Every ``.py`` file under ``src/``, as a path from the repository root."""
    return sorted(path.relative_to(ROOT).as_posix()
                  for path in (ROOT / "src").rglob("*.py"))


def default_expressions(text, option):
    """Every ``default=`` expression of the ``add_argument`` calls of one option."""
    found = []
    for node in ast.walk(ast.parse(text, filename="<default>")):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value != option:
            continue
        for keyword in node.keywords:
            if keyword.arg == "default":
                found.append((node.lineno, keyword.value))
    return found


def module_binding(text, name):
    """The value node of one module-level binding of a source text, or None."""
    for node in ast.parse(text, filename="<binding>").body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == name:
            return node.value
    return None


def evaluated(node, namespace):
    """The value of one expression node, against the names of its own reader."""
    return eval(compile(ast.Expression(body=node), "<default>", "eval"), {}, namespace)


def names_of(node):
    """Every name one expression node reads."""
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
    return found


def reader_namespace(text, values):
    """The names one reader holds, for reading its own default expressions.

    The three owner names are the owner's own values.  The reader's own module
    bindings (its probe directory) are evaluated from its own text, so a default
    that names ``OUT`` is read as that reader builds it.  ``ROOT`` stays the root
    of this checkout: every reader of the write scope joins to the same root.
    """
    namespace = dict(values)
    namespace.update({"ROOT": ROOT, "Path": Path, "str": str})
    for name in ("OUT", "PROBE"):
        node = module_binding(text, name)
        if node is not None:
            namespace[name] = evaluated(node, namespace)
    return namespace


class TheProbePathHasOneHome(unittest.TestCase):
    """The owner states the three names; each reader of them reads the owner."""

    @classmethod
    def setUpClass(cls):
        cls.values = owner_values()
        cls.labels = labels_value()
        cls.owner_text = read(OWNER)
        cls.reader_texts = {path: read(path) for path in READER_FILES}
        cls.outside_texts = {path: read(path) for path in sorted(
            {path for path, _number, _verb in OUTSIDE_SITES})}

    def test_the_owner_states_the_three_names(self):
        """Each name stands once, as its own statement, at its measured line."""
        self.assertEqual(len(set(OWNER_NAMES)), len(OWNER_NAMES), "a name stands twice in the list")
        offenders = []
        for name in OWNER_NAMES:
            value = self.values[name]
            if not isinstance(value, OWNER_KINDS[name]):
                offenders.append("%s: %s holds %s, not %s" % (OWNER, name,
                                                              type(value).__name__,
                                                              OWNER_KINDS[name].__name__))
                continue
            if not str(value):
                offenders.append("%s: %s holds an empty value" % (OWNER, name))
                continue
            number = OWNER_LINES[name]
            line = line_text(self.owner_text, number)
            statement = owner_statement(name, value)
            if line != statement:
                offenders.append("%s:%d: %s, not %s" % (OWNER, number, line, statement))
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_the_owner_imports_the_standard_library_alone(self):
        """The module costs no heavy import: a light stage can read it."""
        roots = imported_roots(self.owner_text)
        heavy = sorted(roots - set(sys.stdlib_module_names))
        self.assertEqual(heavy, [],
                         "%s imports outside the standard library: %s" % (OWNER, heavy))
        self.assertEqual(sorted(roots & {"numpy", "cv2", "torch"}), [],
                         "%s imports a heavy reader: %s" % (OWNER, sorted(roots)))

    def test_every_read_site_reads_the_owner(self):
        """Each declared line joins an owner name to its own root."""
        reports = site_reports(self.reader_texts, READ_SITES)
        self.assertEqual(reports, [], "\n".join(reports))

    def test_no_write_scope_file_spells_a_probe_name_again(self):
        """No constant of the five readers holds a probe name of its own."""
        needles = owner_needles(self.values)
        self.assertEqual(sorted(needles), sorted(set(needles)), "two needles are one text")
        self.assertTrue(all(needles), "a needle is empty")
        offenders = []
        for path, text in self.reader_texts.items():
            offenders.extend(spelled_copies(path, text, needles))
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_the_five_readers_import_the_owner(self):
        """Every reader of the write scope reads the owner module by name."""
        holders = sorted(path for path, text in self.reader_texts.items()
                         if OWNER_MODULE in named_imports(text))
        self.assertEqual(holders, sorted(READER_FILES),
                         "the readers of the owner moved: %s" % holders)
        self.assertEqual(len(holders), READER_FILE_COUNT,
                         "the live copy count moved: %d" % len(holders))

    def test_every_default_answers_the_owner_path(self):
        """Each command default prints the same text as the literal it replaces."""
        expected = (self.values["PROBE_DIR_NAME"] / self.values["CHECKPOINT_NAME"]).as_posix()
        offenders = []
        seen = 0
        for path, option in DEFAULT_SITES:
            text = self.reader_texts[path]
            namespace = reader_namespace(text, self.values)
            for number, node in default_expressions(text, option):
                if not set(OWNER_NAMES) & names_of(node):
                    continue
                seen += 1
                value = evaluated(node, namespace)
                where = "%s:%d: %s" % (path, number, line_text(text, number))
                if not isinstance(value, str):
                    offenders.append("%s: the default is not a text: %r" % (where, value))
                    continue
                try:
                    printed = Path(value).relative_to(ROOT).as_posix()
                except ValueError:
                    offenders.append("%s: the default answers %s, outside the root" % (where, value))
                    continue
                if printed != expected:
                    offenders.append("%s prints %s, not %s" % (where, printed, expected))
        self.assertEqual(offenders, [], "\n".join(offenders))
        self.assertEqual(seen, DEFAULT_SITE_COUNT,
                         "the case read %d of %d defaults" % (seen, DEFAULT_SITE_COUNT))

    def test_the_shipped_readers_bind_the_owner_path(self):
        """Each light reader holds the same path the owner builds."""
        from annotator.pipeline_stages import BALL_CHECKPOINT, BallStage
        from src import ball_fp_audit, fast_ball_labels
        expected = (self.values["PROBE_DIR_NAME"] / self.values["CHECKPOINT_NAME"]).as_posix()
        self.assertEqual(BALL_CHECKPOINT, expected, "the pipeline stage checkpoint moved")
        self.assertEqual(str(BallStage.checkpoint), expected, "the stage checkpoint moved")
        self.assertEqual(ball_fp_audit.PROBE, ROOT / self.values["PROBE_DIR_NAME"],
                         "the audit probe directory moved")
        self.assertEqual(ball_fp_audit.BITMAP, ROOT / self.values["PROBE_DIR_NAME"]
                         / self.values["CHECKPOINT_NAME"], "the audit bitmap moved")
        self.assertEqual(fast_ball_labels.LABELS_OUT.parent, ROOT / self.values["PROBE_DIR_NAME"],
                         "the labeller output directory moved")

    def test_the_home_states_the_labels_name(self):
        """The owner states the labels file name; both readers build from it."""
        from src import fast_ball_labels
        value = self.labels
        number = LABELS_LINE
        line = line_text(self.owner_text, number)
        statement = LABELS_FORM % (value if isinstance(value, str) else "")
        offenders = []
        if not isinstance(value, str) or not value:
            offenders.append("%s:%d: %s, not %s" % (OWNER, number, line, statement))
        elif line != statement:
            offenders.append("%s:%d: %s, not %s" % (OWNER, number, line, statement))
        offenders.extend(labels_site_reports(self.reader_texts))
        offenders.extend(labels_import_reports(self.reader_texts))
        if isinstance(value, str) and value:
            path, out_number = LABELS_OUT_SITE
            where = "%s:%d: %s" % (path, out_number,
                                   line_text(self.reader_texts[path], out_number))
            if fast_ball_labels.LABELS_OUT.name != value:
                offenders.append("%s: the labeller output names %s, not %s"
                                 % (where, fast_ball_labels.LABELS_OUT.name, value))
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_no_src_module_spells_the_labels_name_again(self):
        """No ``.py`` file under ``src/``, the owner alone, states the name again."""
        value = self.labels
        self.assertIsInstance(value, str, "the owner holds no labels name")
        self.assertTrue(value, "the labels name is empty")
        statement = LABELS_FORM % value
        line = line_text(self.owner_text, LABELS_LINE)
        self.assertEqual(line, statement,
                         "%s:%d: %s, not %s" % (OWNER, LABELS_LINE, line, statement))
        paths = src_modules()
        self.assertIn(OWNER, paths, "the walk lost the owner")
        self.assertGreaterEqual(len(paths), SRC_MODULE_FLOOR,
                                "the walk read %d files, below %d" % (len(paths),
                                                                      SRC_MODULE_FLOOR))
        for path in LABELS_READERS:
            self.assertIn(path, paths, "%s is no module under src/" % path)
        offenders = []
        for path in paths:
            if path == OWNER:
                continue
            offenders.extend(spelled_copies(path, read(path), (value,)))
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_the_five_copies_outside_the_write_scope_hold_the_path(self):
        """Each pinned copy still spells the value the owner holds."""
        reports = outside_reports(self.values, self.outside_texts, OUTSIDE_SITES)
        self.assertEqual(reports, [], "\n".join(reports))

    def test_a_planted_copy_in_a_write_scope_file_is_reported(self):
        """A planted constant in a reader text is reported as ``path:line: <text>``."""
        path = "src/fast_ball_labels.py"
        planted = 'PROBE_X = Path("%s")\n' % self.values["PROBE_DIR_NAME"].as_posix()
        text = self.reader_texts[path] + planted
        line = text.count("\n")
        offenders = spelled_copies(path, text, owner_needles(self.values))
        hit = [entry for entry in offenders if entry.startswith("%s:%d:" % (path, line))]
        self.assertEqual(1, len(hit),
                         "%s: the walk lost the inline form %r: %s" % (path, planted, offenders))
        match = LOCATION.match(hit[0])
        self.assertIsNotNone(match, "the report shape moved: %s" % hit[0])
        self.assertEqual(match.group("path"), path)
        self.assertEqual(int(match.group("line")), line)
        self.assertIn(self.values["PROBE_DIR_NAME"].name, match.group("text"),
                      "the entry hides the copy: %s" % hit[0])
        self.assertIn(OWNER, hit[0], "the entry does not name the owner: %s" % hit[0])

    def test_a_planted_drift_outside_the_write_scope_is_reported(self):
        """A drift at the bite site is reported with that file and that line."""
        path, number = BITE_SITE
        values = site_values(self.values)
        expected = values["FULL"][0]
        drifted = expected.replace(".pt", "_X.pt")
        self.assertNotEqual(drifted, expected, "the planted drift is not a drift")
        text = self.outside_texts[path].replace(expected, drifted)
        self.assertNotEqual(text, self.outside_texts[path], "the planted drift did not land")
        reports = outside_reports(self.values, {path: text},
                                  ((path, number, "FULL"),))
        self.assertEqual(1, len(reports), "the drift is not reported: %s" % reports)
        self.assertTrue(reports[0].startswith("%s:%d: " % (path, number)),
                        "the report hides the site: %s" % reports[0])
        self.assertIn(drifted, reports[0], "the report hides the drift: %s" % reports[0])
        match = LOCATION.match(reports[0])
        self.assertIsNotNone(match, "the report shape moved: %s" % reports[0])

    def test_the_scan_reads_the_live_files(self):
        """The counts hold the scan open: a scan that reads nothing cannot pass."""
        self.assertTrue((ROOT / OWNER).is_file(), "the owner file is absent")
        self.assertEqual(len(READER_FILES), READER_FILE_COUNT,
                         "the reader list moved: %s" % (READER_FILES,))
        self.assertEqual(len(set(READER_FILES)), READER_FILE_COUNT, "a reader stands twice")
        self.assertEqual(len(self.reader_texts), READER_FILE_COUNT, "a reader is unread")
        self.assertEqual(len(READ_SITES), READ_SITE_COUNT,
                         "the read site count moved: %d" % len(READ_SITES))
        self.assertEqual(len(OUTSIDE_SITES), OUTSIDE_SITE_COUNT,
                         "the outside site count moved: %d" % len(OUTSIDE_SITES))
        self.assertEqual(len(LABELS_READERS), LABELS_READER_COUNT,
                         "the labels reader count moved: %d" % len(LABELS_READERS))
        self.assertEqual(len(set(LABELS_READERS)), LABELS_READER_COUNT,
                         "a labels reader stands twice")
        self.assertEqual(len(LABELS_SITES), LABELS_SITE_COUNT,
                         "the labels site count moved: %d" % len(LABELS_SITES))
        self.assertEqual({path for path, _number in LABELS_SITES}, set(LABELS_READERS),
                         "a labels site stands outside the two readers")
        for path, text in self.reader_texts.items():
            self.assertGreater(len(text), SHORTEST_READER, "%s is almost empty" % path)
        for path, _number, _verb in OUTSIDE_SITES:
            self.assertTrue((ROOT / path).is_file(), "%s is absent" % path)
            self.assertGreater(len(self.outside_texts[path]), SHORTEST_READER,
                               "%s is almost empty" % path)
        for path in {path for path, _number, _names in READ_SITES}:
            self.assertIn(path, self.reader_texts, "%s is not a reader of the scope" % path)

    def test_the_home_names_the_shipped_labels_file(self):
        """The shipped file name stands in the owner; a value of the moment fails.

        The cases above read the owner value and compare the two readers against
        it, so a moved value moves both sides and leaves them green.  This case
        pins the name itself, and its failure names the owner line and its text.
        """
        shipped = "new_labels.json"
        line = line_text(self.owner_text, LABELS_LINE)
        self.assertEqual(self.labels, shipped,
                         "%s:%d: %s, not %s"
                         % (OWNER, LABELS_LINE, line, LABELS_FORM % shipped))


if __name__ == "__main__":
    unittest.main()
