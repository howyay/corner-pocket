"""The report blob key ``channels_report`` has one owner, and every site reads it.

The key of the per-channel blob of the motion-scan report stood three times and
no case in ``tests/`` named it:

  * the writer of ``src/motion_scan.py`` built the blob as a plain literal,
  * the reader of the same file read a second copy of that name as a plain
    literal for its ``--skip-quiet`` path,
  * and ``src/track_before_detect.py`` read a third copy of that name as a plain
    literal to find the quiet windows of the blob.

The drift was silent.  A rename at one site left the reader with no blob.  The
quiet windows of the last run stayed unseen, the scan measured them again, and
the suite stayed green.

This module holds the three sides to one owner,
``src.motion_scan.CHANNELS_REPORT_KEY``:

  * the owner name, its value and its type,
  * the write of the key in the dict display of the writer, read from the syntax
    tree of ``src/motion_scan.py``,
  * the read of the key in both readers, read from the syntax tree,
  * the module that ``src/track_before_detect.py`` reads the name from, and
  * a count of the live spellings, so a new bare literal fails the guard.

The guard reports every offender as ``path:line: <the line text>``.

Run: ``./scripts/pool-test.sh python test_channels_report_key_owner``
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

from src import motion_scan  # noqa: E402

#: The owner module, as a path from the repository root.
OWNER = "src/motion_scan.py"
#: The owner name, read from the imported module and from no copy of the text.
OWNER_NAME = "CHANNELS_REPORT_KEY"
#: The two modules that write or read the key.  ``src/motion_scan.py`` holds the
#: writer and one reader; ``src/track_before_detect.py`` holds the other reader.
MODULES = ("src/motion_scan.py", "src/track_before_detect.py")
#: The module the other reader reads the name from.
READER = "src/track_before_detect.py"
#: Every spelling this module accepts as a use of the owner:
#: the constant alone, and the constant under its module.
OWNER_SPELLINGS = (OWNER_NAME, "ms." + OWNER_NAME)
#: The spelling of the constant in its own definition, for the line regex.
NAME_RE = re.compile(rf"\s*{OWNER_NAME}\s*=")
#: A module-level name in upper case, the shape of a constant of this house.
CONSTANT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def own_key() -> str:
    """The value of the owner constant, read from the imported module.

    The dotted read is deliberate.  ``getattr`` answers the value of the module
    that is loaded now, so a guard that plants a new value in
    ``motion_scan.CHANNELS_REPORT_KEY`` is answered by that value.
    """
    value = getattr(motion_scan, OWNER_NAME, None)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{OWNER}:{OWNER_NAME} is not a non-empty string: {value!r}")
    return value


def source_text(relative: str) -> str:
    """The text of one source file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one source file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(relative: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return f"{relative}:{line}: {text.strip()}  <- {why}"


def first_argument(node: ast.Call):
    """The first argument of a call, or None when the call has no argument."""
    return node.args[0] if node.args else None


def callee_name(node: ast.Call) -> str:
    """The written name of the function of a call, or an empty string."""
    try:
        return ast.unparse(node.func)
    except Exception:  # pragma: no cover - a node the standard writer cannot print
        return ""


def owned_dict_keys(text: str, where: str) -> list:
    """Every dict key of a display that spells the owner name.

    The answer is ``(line, the key as written, the text of the whole display)``
    per site.  A dict display of a report is the shape of a writer, so this walk
    finds the writer site.
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


def bare_dict_keys(text: str, where: str, key: str) -> list:
    """Every dict key of a display that holds the key as a plain literal.

    A plain literal earns the value test today, and the same literal is a second
    home of the fact tomorrow.  The answer is ``(line, the literal as written)``.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if not isinstance(node, ast.Dict):
            continue
        for key_node in node.keys:
            if isinstance(key_node, ast.Constant) and key_node.value == key:
                found.append((key_node.lineno, ast.unparse(key_node)))
    return sorted(found)


def owned_lookups(text: str, where: str) -> list:
    """Every lookup that reads the blob through a spelling of the owner name.

    A lookup is ``<expression>.get(<first argument>)``, a subscript
    ``<expression>[<index>]`` of a string, or the keyword of a call.  The answer
    is ``(line, the name as written, the value, the callee as written)`` per
    site.  A ``get`` of a report is the shape of a reader.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Call):
            first = first_argument(node)
            if isinstance(first, (ast.Name, ast.Attribute, ast.Subscript)):
                written = ast.unparse(first)
                if written in OWNER_SPELLINGS or written.endswith("." + OWNER_NAME):
                    found.append((first.lineno, written, None, callee_name(node)))
        elif isinstance(node, ast.Subscript):
            index = node.slice
            if isinstance(index, (ast.Name, ast.Attribute)):
                written = ast.unparse(index)
                if written in OWNER_SPELLINGS or written.endswith("." + OWNER_NAME):
                    found.append((index.lineno, written, None, ast.unparse(node.value)))
    return sorted(found)


def bare_lookups(text: str, where: str, key: str) -> list:
    """Every lookup that reads the key as a plain literal, and the value of it.

    A ``get`` argument, an index of a subscript, or the keyword of a call: every
    argument that holds the key text and no name of the owner.  The answer is
    ``(line, the literal as written, the value)`` per site.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Call):
            first = first_argument(node)
            if isinstance(first, ast.Constant) and first.value == key:
                found.append((first.lineno, ast.unparse(first), first.value))
            for word in node.keywords:
                if word.arg and isinstance(word.value, ast.Constant) \
                        and word.value.value == key:
                    found.append((word.value.lineno, ast.unparse(word.value),
                                  word.value.value))
        elif isinstance(node, ast.Subscript):
            index = node.slice
            if isinstance(index, ast.Constant) and index.value == key:
                found.append((index.lineno, ast.unparse(index), index.value))
    return sorted(found)


def owner_name_nodes(text: str, where: str) -> list:
    """Every node that spells the owner name, as a parsed name and not as text."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Name) and node.id == OWNER_NAME:
            found.append((node.lineno, node.id))
        elif isinstance(node, ast.Attribute) and node.attr == OWNER_NAME:
            found.append((node.lineno, ast.unparse(node)))
        elif isinstance(node, ast.arg) and node.arg == OWNER_NAME:
            found.append((node.lineno, node.arg))
        elif isinstance(node, ast.keyword) and node.arg == OWNER_NAME:
            found.append((node.lineno, node.arg))
    return sorted(found)


def name_uses(text: str, where: str) -> list:
    """Every line that spells the owner name, read from the syntax tree.

    The text of a line holds no function body, so the walk is the honest count:
    a comment or a docstring that names the constant is no site of the constant.
    """
    lines = text.splitlines()
    return [(number, lines[number - 1].strip()) for number, _written in owner_name_nodes(text, where)]


def import_aliases(text: str, where: str, module: str) -> list:
    """Every local name that one module imports another module under.

    The house writes ``from src import motion_scan as ms``, so the walk states
    the ``from`` shape as well as the plain ``import`` shape.
    """
    parts = module.split(".")
    leaf = parts[-1]
    parent = ".".join(parts[:-1])
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    found.append(alias.asname or leaf)
        elif isinstance(node, ast.ImportFrom) and node.module == parent:
            for alias in node.names:
                if alias.name in (leaf, module):
                    found.append(alias.asname or leaf)
    return sorted(set(found))


class OwnerTests(unittest.TestCase):
    """The owner name, its value and the type of that value."""

    def test_the_owner_names_the_shipped_key(self):
        self.assertEqual(own_key(), "channels_report",
                         f"{OWNER}:{OWNER_NAME} moved; the writer and both readers "
                         f"must move with it")

    def test_the_owner_line_of_the_module_carries_the_shipped_key(self):
        """The line of the owner module that holds the value, with its number.

        This case pins the owner at ``path:line``.  The value the module answers
        and the value that the text of the module shows must be one word, so a
        reader of the report can open that line and see the shipped key.
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

    def test_the_owner_name_has_the_shape_of_a_constant(self):
        self.assertTrue(CONSTANT_NAME_RE.match(OWNER_NAME),
                        f"{OWNER_NAME} is not the name of a constant")
        value = own_key()
        self.assertIsInstance(value, str, f"{OWNER}:{OWNER_NAME} = {value!r}")


class WriterTests(unittest.TestCase):
    """The writer of the owner module writes the key through the owner name."""

    def test_the_blob_key_of_the_writer_comes_from_the_constant(self):
        """The key of the saved blob comes from the constant.

        The display is ``{CHANNELS_REPORT_KEY: payload}``.  This case reads the
        dict display of the writer from the syntax tree and holds its key to the
        owner name, so the saved report shape stays one word.
        """
        sites = owned_dict_keys(source_text(OWNER), OWNER)
        self.assertEqual(1, len(sites),
                         f"{OWNER} holds {len(sites)} dict displays that spell "
                         f"{OWNER_NAME}: {[site[0] for site in sites]}")
        line, written, display = sites[0]
        self.assertEqual(OWNER_NAME, written,
                         report(OWNER, line, source_lines(OWNER)[line - 1],
                                f"the display writes {written}, not {OWNER_NAME}"))
        self.assertIn(OWNER_NAME, display,
                      report(OWNER, line, source_lines(OWNER)[line - 1],
                             f"the display {display} does not write {OWNER_NAME}"))

    def test_no_dict_display_of_the_owner_module_holds_a_bare_key(self):
        """A bare literal is a second home of the key, and this case fails on it."""
        key = own_key()
        offenders = [report(OWNER, line, source_lines(OWNER)[line - 1],
                            f"{written} is a bare spelling of the key {key!r}; "
                            f"write {OWNER_NAME} of {OWNER} instead")
                     for line, written in bare_dict_keys(source_text(OWNER), OWNER, key)]
        self.assertEqual([], offenders,
                         f"{OWNER} writes the blob key as a plain literal:\n"
                         + "\n".join(offenders))

    def test_the_walk_reports_a_planted_writer_key(self):
        """A write of the key as a plain literal is reported with its path and line."""
        key = own_key()
        planted = ('def cmd_report(args):\n'
                   '    payload = {"n": 1}\n'
                   '    return save_report({"' + key + '": payload},\n'
                   '                       args.out_dir, args.dataset)\n')
        offenders = [report(OWNER, line, planted.splitlines()[line - 1],
                            f"{written} is a bare spelling of the key; write "
                            f"{OWNER_NAME} of {OWNER} instead")
                     for line, written in bare_dict_keys(planted, "planted_writer.py", key)]
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f"{OWNER}:3:", offenders[0])
        self.assertIn(key, offenders[0])
        self.assertIn("save_report", planted.splitlines()[2])
        self.assertEqual([], owned_dict_keys(planted, "planted_writer.py"),
                         "the planted literal counts as an owner spelling")


class ReaderTests(unittest.TestCase):
    """Both readers of the key read it through the owner name."""

    def test_no_reader_holds_a_bare_spelling_of_the_key(self):
        """No file holds a second bare spelling of the key."""
        key = own_key()
        offenders = []
        for relative in MODULES:
            for line, written, _value in bare_lookups(source_text(relative), relative, key):
                offenders.append(report(
                    relative, line, source_lines(relative)[line - 1],
                    f"{written} is a bare spelling of the key; read {OWNER_NAME} "
                    f"of {OWNER} instead"))
        self.assertEqual([], offenders,
                         "a reader holds a bare spelling of the blob key:\n"
                         + "\n".join(offenders))

    def test_the_owner_module_reads_the_key_through_the_owner_name(self):
        """The anti-vacuity case of the reader of the owner module."""
        key = own_key()
        reads = [(line, written) for line, written, _value, callee
                 in owned_lookups(source_text(OWNER), OWNER)
                 if callee.endswith(".get")]
        self.assertTrue(reads, f"{OWNER} reads the key {key!r} through no get call")
        for line, written in reads:
            self.assertEqual(OWNER_NAME, written,
                             report(OWNER, line, source_lines(OWNER)[line - 1],
                                    f"the read writes {written}, not {OWNER_NAME}"))
            self.assertIn(OWNER_NAME, source_lines(OWNER)[line - 1])

    def test_the_other_reader_reads_the_key_through_the_owner_module(self):
        """The anti-vacuity case of the reader of the other module."""
        key = own_key()
        reads = [(line, written) for line, written, _value, callee
                 in owned_lookups(source_text(READER), READER)
                 if ".get" in callee]
        self.assertTrue(reads,
                        f"{READER} reads the key {key!r} through no get call; "
                        f"the quiet windows of the last run stay unseen")
        for line, written in reads:
            self.assertTrue(written.endswith("." + OWNER_NAME),
                            report(READER, line, source_lines(READER)[line - 1],
                                   f"the read writes {written}; it must name "
                                   f"{OWNER_NAME} under its module"))
            self.assertIn(OWNER_NAME, source_lines(READER)[line - 1])

    def test_the_walk_reports_a_planted_reader_key(self):
        """A read of the key as a plain literal is reported with its path and line."""
        key = own_key()
        planted = ('def windows(report):\n'
                   '    blocks = (report.get("' + key + '") or {}).get("quiet_blocks")\n'
                   '    return blocks or []\n')
        offenders = [report(READER, line, planted.splitlines()[line - 1],
                            f"{written} is a bare spelling of the key; read "
                            f"{OWNER_NAME} of {OWNER} instead")
                     for line, written, _value in bare_lookups(planted, "planted_reader.py", key)]
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f"{READER}:2:", offenders[0])
        self.assertIn(key, offenders[0])
        self.assertEqual([], owned_lookups(planted, "planted_reader.py"),
                         "the planted literal counts as an owner spelling")


class ModuleBoundaryTests(unittest.TestCase):
    """``src.motion_scan`` is the module the other reader reads the name from."""

    def test_the_other_reader_imports_the_owner_module(self):
        aliases = import_aliases(source_text(READER), READER, "src.motion_scan")
        self.assertEqual(["ms"], aliases,
                         f"{READER} imports {aliases} from src.motion_scan; "
                         f"the guard measures the name under ms")

    def test_the_other_reader_reads_the_name_under_that_import(self):
        """The spelling at the reader site must agree with the import of the file."""
        aliases = import_aliases(source_text(READER), READER, "src.motion_scan")
        self.assertTrue(aliases, f"{READER} imports no name from src.motion_scan")
        key = own_key()
        reads = [(line, written) for line, written, _value, _callee
                 in owned_lookups(source_text(READER), READER)]
        self.assertTrue(reads, f"{READER} holds no read of the key {key!r}")
        bare = [report(READER, line, source_lines(READER)[line - 1],
                       f"{written} is a bare spelling of the key; read "
                       f"{OWNER_NAME} of {OWNER} instead")
                for line, written, _value
                in bare_lookups(source_text(READER), READER, key)]
        self.assertEqual([], bare,
                         f"{READER} reads the key as a plain literal:\n"
                         + "\n".join(bare))
        for line, written in reads:
            self.assertTrue(any(written == f"{alias}.{OWNER_NAME}" for alias in aliases),
                            report(READER, line, source_lines(READER)[line - 1],
                                   f"the read writes {written}; it must name "
                                   f"{OWNER_NAME} under one of {aliases}"))

    def test_no_module_outside_the_owner_defines_the_owner_name(self):
        """A second definition answers its own copy, not the owner."""
        offenders = []
        for relative in MODULES:
            if relative == OWNER:
                continue
            for node in ast.walk(ast.parse(source_text(relative), filename=relative)):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == OWNER_NAME:
                        offenders.append(report(
                            relative, node.lineno, source_lines(relative)[node.lineno - 1],
                            f"the second definition of {OWNER_NAME}; the owner is {OWNER}"))
        self.assertEqual([], offenders, "\n".join(offenders))


class SpellingCountTests(unittest.TestCase):
    """A count of the live spellings, so a new bare literal fails the guard."""

    def test_every_live_spelling_of_the_key_names_the_owner(self):
        """The count and the kind of every site that uses the key today.

        The three sites are known: the write of the blob in ``src/motion_scan.py``
        and the two reads.  This case names the file, the line and the line text
        of each of them, so a new site must come here and state itself.
        """
        expected = {
            "src/motion_scan.py": (
                "dict:{CHANNELS_REPORT_KEY: payload}",
                "get:CHANNELS_REPORT_KEY",
            ),
            "src/track_before_detect.py": (
                "get:ms.CHANNELS_REPORT_KEY",
            ),
        }
        key = own_key()
        offenders = []
        for relative in MODULES:
            lines = source_lines(relative)
            text = source_text(relative)
            sites = []
            numbered = []
            for line, written, display in owned_dict_keys(text, relative):
                sites.append(f"dict:{display}")
                numbered.append((line, written))
            for line, written, _value, callee in owned_lookups(text, relative):
                kind = "get" if callee.endswith(".get") else "lookup"
                sites.append(f"{kind}:{written}")
                numbered.append((line, written))
            for line, written, _value in bare_lookups(text, relative, key):
                offenders.append(report(relative, line, lines[line - 1],
                                        f"{written} is a bare spelling of the "
                                        f"key; write {OWNER_NAME} of {OWNER}"))
            for line, written in bare_dict_keys(text, relative, key):
                offenders.append(report(relative, line, lines[line - 1],
                                        f"{written} is a bare spelling of the "
                                        f"key; write {OWNER_NAME} of {OWNER}"))
            self.assertEqual(sorted(expected[relative]), sorted(sites),
                             f"the live spellings of {relative} moved")
            for line, written in numbered:
                self.assertIn(OWNER_NAME, lines[line - 1],
                              report(relative, line, lines[line - 1],
                                     "the line does not name the owner"))
        self.assertEqual([], offenders,
                         "a live spelling of the key left its owner:\n"
                         + "\n".join(offenders))

    def test_the_count_of_live_spellings_is_three(self):
        """One write and two reads.  A fourth site must state itself here."""
        key = own_key()
        count = 0
        names = []
        for relative in MODULES:
            text = source_text(relative)
            for line, written, _display in owned_dict_keys(text, relative):
                count += 1
                names.append(f"{relative}:{line} dict {written}")
            for line, written, _value, callee in owned_lookups(text, relative):
                count += 1
                names.append(f"{relative}:{line} get {written}")
            for line, written, _value in bare_lookups(text, relative, key):
                count += 1
                names.append(f"{relative}:{line} bare {written}")
            for line, written in bare_dict_keys(text, relative, key):
                count += 1
                names.append(f"{relative}:{line} bare dict {written}")
        self.assertEqual(3, count, f"the key {key!r} has {count} live sites: {names}")
        for name in names:
            self.assertIn(OWNER_NAME, name, name)

    def test_no_spelling_of_the_key_lives_in_a_name_of_the_owner_name(self):
        """Every use of the owner name in both files is a use of the constant."""
        offenders = []
        for relative in MODULES:
            for line, text in name_uses(source_text(relative), relative):
                if OWNER_NAME in text:
                    continue
                offenders.append(report(relative, line, text,
                                        f"the line names no {OWNER_NAME}; the owner "
                                        f"spellings are {'/'.join(OWNER_SPELLINGS)}"))
        self.assertEqual([], offenders,
                         "a file names the blob key outside the owner:\n"
                         + "\n".join(offenders))


class PlantedTests(unittest.TestCase):
    """The detector reports a planted bare literal with its file and line."""

    def test_the_walk_reports_a_planted_writer_key(self):
        """A write of the key as a plain literal is reported with its path and line."""
        planted = ('def cmd_report(args):\n'
                   '    payload = {"n": 1}\n'
                   '    return save_report({"channels_report": payload},\n'
                   '                       args.out_dir, args.dataset)\n')
        key = own_key()
        offenders = [report(OWNER, line, planted.splitlines()[line - 1],
                            f"{written} is a bare spelling of the key; write "
                            f"{OWNER_NAME} of {OWNER} instead")
                     for line, written
                     in bare_dict_keys(planted, "planted_writer.py", key)
                     if written != OWNER_NAME]
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f"{OWNER}:3:", offenders[0])
        self.assertIn("channels_report", offenders[0])
        self.assertIn("save_report", offenders[0])

    def test_the_walk_reports_a_planted_reader_key(self):
        """A read of the key as a plain literal is reported with its path and line."""
        planted = ('def windows(report):\n'
                   '    blocks = (report.get("channels_report") or {}).get("quiet_blocks")\n'
                   '    return blocks or []\n')
        key = own_key()
        offenders = [report(READER, line, planted.splitlines()[line - 1],
                            f"{written} is a bare spelling of the key; read "
                            f"{OWNER_NAME} of {OWNER} instead")
                     for line, written, _value
                     in bare_lookups(planted, "planted_reader.py", key)]
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f"{READER}:2:", offenders[0])
        self.assertIn("channels_report", offenders[0])
        self.assertIn("report.get", offenders[0])

    def test_the_walk_reports_a_planted_owned_read(self):
        """The same walk accepts the owner spelling, so the detector holds the name."""
        planted = ('def windows(report):\n'
                   '    return (report.get(CHANNELS_REPORT_KEY) or {}).get("quiet_blocks")\n')
        key = own_key()
        reads = owned_lookups(planted, "planted_reader.py")
        self.assertEqual(1, len(reads), reads)
        self.assertEqual(OWNER_NAME, reads[0][1], reads)
        self.assertIsNone(reads[0][2], reads)


if __name__ == "__main__":
    unittest.main()
