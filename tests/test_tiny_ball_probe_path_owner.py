"""The tiny-ball probe directory and the two artifact names have one home.

Round 105 measured the defect.  The probe directory ``out/tiny_ball_probe``, the
checkpoint name ``960x540-scratch.pt`` and the frozen held-out name
``held_frozen.json`` stood in five live readers at once: the pipeline stage
(``annotator/pipeline_stages.py``), the trainer (``src/tiny_ball_net.py``), the
labeller (``src/fast_ball_labels.py``), the false-positive audit
(``src/ball_fp_audit.py``) and the held-out stack probe (``tests/ball_stack_ab.py``).
A second copy drifted in silence, because no case read two copies: a rename of one
file had to land in five files at once.

The repair gives the three names one home, ``src/tiny_ball_probe.py``, and each
reader joins those names to its own root.  The file system root therefore stays
local to each reader and the owner states no root of its own.

The cases below hold that shape in five ways:

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
* the three names are held by value.  A reader that renames its own local binding
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
        for path, text in self.reader_texts.items():
            self.assertGreater(len(text), SHORTEST_READER, "%s is almost empty" % path)
        for path, _number, _verb in OUTSIDE_SITES:
            self.assertTrue((ROOT / path).is_file(), "%s is absent" % path)
            self.assertGreater(len(self.outside_texts[path]), SHORTEST_READER,
                               "%s is almost empty" % path)
        for path in {path for path, _number, _names in READ_SITES}:
            self.assertIn(path, self.reader_texts, "%s is not a reader of the scope" % path)


if __name__ == "__main__":
    unittest.main()
