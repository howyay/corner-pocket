"""The crop-set vocabulary has one owner: `BALL_SETS` in src/store_files.py.

The vocabulary is the list of sets a crop file can belong to. Five places named it
before this test file existed: four Python modules and the `ball_labels.crop_set`
CHECK of db/migrations/0002_user_data.sql. SQL cannot import Python, so the CHECK
stays a second copy. These tests prove that the two copies name the same sets in the
same order, and that no Python module spells the vocabulary again.

The checks read the names from the owner, so a set that the owner gains is covered
here without a second edit.
"""
import ast
import importlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from src import datasets
from src import store_files
from src.datasets import STATIC_OUT
from src.store_files import (BALL_SETS, DOCUMENT_FORMAT, DOCUMENT_SETS, FORMATS, INDENT1,
                             SCHEMA_RANGE, document_paths, dump, fmt_of, is_document_path)

# The scanner has one home, tests/_shipped.py.  The single-module runner starts in
# tests/, and discovery puts tests/ on sys.path, so the bare module name reaches the
# helper in both.  The tree the scanner reads sits in that same home.  This file
# declared the tree and the scanner by hand until round 61.
from _shipped import code_strings, parse, shipped_modules

ROOT = Path(__file__).resolve().parents[1]
OWNER = "src/store_files.py"
# This file must spell the format names to check them, so the scan below skips it.
CHECKER = "tests/test_store_files.py"
# The imports that take a format name from its owner.  A file with one of them holds
# no copy of the name, so the scan below skips it.
READS_OWNER = ("from src.store_files import", "from src import store_files")
MIGRATION = ROOT / "db" / "migrations" / "0002_user_data.sql"
MIGRATIONS = ROOT / "db" / "migrations"
# The one module that states its schema range in its docstring.  The case reads the
# line and holds it to the files of db/migrations.
PG_STORE = "src/store_pg.py"
# The range statement of that docstring: four digits, a hyphen, four digits.
PG_RANGE = r"(?<!\d)(\d{4})-(\d{4})(?!\d)"
# The modules that import the vocabulary from its owner. They must hold no copy.
IMPORTERS = ("src/store.py", "src/store_import.py", "src/store_pg.py",
             "annotator/unified_server.py")
# Files that spell crop-set names for a reason, and the reason. Every other source
# file that spells one crop-set name in code fails the scan below. A name in a
# docstring or in a comment is prose, so the scan does not read it. A case module is
# not shipped code, so it states the crop set of the row it exercises.
ALLOWED_SPELLINGS = {
    OWNER: "the one owner of the vocabulary",
    "db/migrations/0002_user_data.sql": "the ball_labels CHECK; SQL cannot import Python "
                                        "(the parity test proves it equal to the owner)",
    "tests/serve_vod_fixture.py": "a fixture that copies the crop folders of out/; it lists "
                                  "folder names, not the vocabulary",
    "tests/serve_workbench_fixture.py": "a fixture that links the crop folders of out/; it "
                                        "lists folder names, not the vocabulary",
}
# Directories that hold no source, or generated copies of it.
SKIP_DIRS = {".git", ".venv", "out", "data", "__pycache__", "node_modules", ".pytest_cache"}
#: The map "built-in dataset id -> scan folder under out/" has one owner: `STATIC_OUT`
#: in src/datasets.py.  The readers below take that map from the owner.  A reader that
#: types the map again holds a second copy, and that copy can drift from the owner.
MAP_OWNER = "src/datasets.py"
MAP_READERS = (("src/store_files.py", "STATIC_OUT"), ("src/store_import.py", "STATIC_OUT"))
#: The shipped packages the map scan reads, from the one home in tests/_shipped.py.
#: The suite is not shipped code: a test that states an expected map is an
#: expectation, not a second copy inside the application.  ``SHIPPED`` keeps the
#: comment above it there, and the guard of tests/test_one_shipped_tree.py holds
#: every reader of it to that home.


def bare_names(line: str, suffix: str) -> list[str]:
    """The crop-set names `line` spells as one whole string literal, in order.

    A name inside a longer string (a path such as "out/unlabeled_crops/labels.json")
    is a use of that set, not a second spelling of the vocabulary. SQL uses single
    quotes for text, so double quotes are not read in a .sql file."""
    quoted = "|".join(re.escape(name) for name in BALL_SETS)
    pattern = re.compile(r"'(" + quoted + r")'") if suffix == ".sql" \
        else re.compile(r"([\"'])(" + quoted + r")\1")
    return [match.group(match.lastindex or 1) for match in pattern.finditer(line)]


def spelling_lines(path: Path) -> list[tuple[int, list[str]]]:
    """(line number, names) for every line of `path` that spells a crop-set name."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [(number, names) for number, line in enumerate(text.splitlines(), 1)
            if (names := bare_names(line, path.suffix))]


def source_files() -> list[Path]:
    """Every .py and .sql file of the repository, generated trees left out."""
    return sorted(path for path in ROOT.rglob("*")
                  if path.is_file() and path.suffix in (".py", ".sql")
                  and not any(part in SKIP_DIRS for part in path.parts))


def is_case_module(path: Path) -> bool:
    """True for a unittest case module: a `tests/test_*.py` file.

    The suite is not shipped code; tests/_shipped.py states that rule, and discovery
    reads `test_*.py` files only. A case states the crop set of the row it exercises,
    so its name is an expectation and not a second copy inside the application.
    """
    return (path.parent == ROOT / "tests" and path.suffix == ".py"
            and path.name.startswith("test_"))


def scanned_files() -> list[Path]:
    """Every source file the vocabulary scan reads: the case modules left out."""
    return [path for path in source_files() if not is_case_module(path)]


def code_spelling_lines(path: Path) -> list[tuple[int, list[str]]]:
    """(line number, names) for every line of `path` that spells a crop-set name in code.

    A name is in code when a whole string literal of the module is that name. The
    reader drops every docstring (the rule lives in tests/_shipped.py), and a comment
    holds no literal, so a name in prose cannot fail the scan. A .sql file holds no
    docstring, so the reader of every line answers it.
    """
    if path.suffix == ".sql":
        return spelling_lines(path)
    found: dict[int, list[str]] = {}
    for line, text in code_strings(parse(path)):
        if text in BALL_SETS:
            found.setdefault(line, []).append(text)
    return sorted(found.items())


def label(path: Path) -> str:
    """The name a report prints for `path`: relative to ROOT when it lies under ROOT."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def vocabulary_offenders(paths: list[Path]) -> list[str]:
    """The report of the scan: one line for each site that spells a name in code."""
    return [f"{label(path)}:{line} spells {names}"
            for path in paths
            if label(path) not in ALLOWED_SPELLINGS
            for line, names in code_spelling_lines(path)]


def resolve_rows() -> list[str]:
    """The rows of `ROW_FILES` in src/store_export.py, with every name resolved.

    A row is a double-quoted path, or the name of a path that src/store_files.py
    holds, and the read of the name answers the value of that owner.
    """
    source = (ROOT / "src" / "store_export.py").read_text(encoding="utf-8")
    tokens = re.search(r"^ROW_FILES = \((.*)\)$", source, re.M).group(1).split(",")
    return [getattr(store_files, token) if token.isidentifier() else json.loads(token)
            for token in (part.strip() for part in tokens)]


def typed_map_pairs(path: Path) -> list[tuple[int, dict[str, str]]]:
    """(line number, pairs) for every dict literal of `path` that types an owner pair.

    A pair is one built-in id written next to its scan folder, as one whole string.  A
    longer string that holds the folder ("out/scan30/annotations.json") is a use of the
    dataset, not a second copy of the map.  A table that pairs the id with a richer
    tuple (src/eval_faces.py holds one) answers another question and is not read here.
    """
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8", errors="replace"))):
        if not isinstance(node, ast.Dict):
            continue
        try:
            value = ast.literal_eval(node)
        except (ValueError, SyntaxError, TypeError):
            continue
        pairs = {key: item for key, item in value.items()
                 if isinstance(key, str) and key in STATIC_OUT and item == STATIC_OUT[key]}
        if pairs:
            found.append((node.lineno, pairs))
    return found


class NoRows:
    """A connection that answers no row: the shape `render` reads."""

    def execute(self, *_args, **_kwargs):
        return self

    def fetchall(self):
        return []


def migration_numbers() -> list[int]:
    """The numbers of every migration file of db/migrations, in order.

    The file name is the rule: four digits, then an underscore, then the label."""
    numbers = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        match = re.fullmatch(r"(\d{4})_.*", path.name)
        if match is None:
            raise AssertionError(f"{path}: the name must start with four digits and an underscore")
        numbers.append(int(match.group(1)))
    return numbers


def stated_schema_range() -> tuple[int, int]:
    """The migration range the docstring of the database store states, as two numbers.

    The line must read `NNNN-NNNN` as its own token.  The range is a statement about
    db/migrations, so the case below holds it to the files on disk."""
    docstring = ast.get_docstring(ast.parse((ROOT / PG_STORE).read_text(encoding="utf-8")))
    if docstring is None:
        raise AssertionError(f"{PG_STORE}: no module docstring")
    match = re.search(PG_RANGE, docstring)
    if match is None:
        raise AssertionError(f"{PG_STORE}: the docstring states no 'NNNN-NNNN' migration range")
    return int(match.group(1)), int(match.group(2))


class SchemaRange(unittest.TestCase):
    """The database store names the migrations it needs, and the files answer it."""

    def test_the_stated_range_is_the_range_of_the_files_on_disk(self):
        """One range, three statements: the owner constant, the docstring, and the files.

        ``SCHEMA_RANGE`` names the range the store layer needs, the docstring of
        src/store_pg.py states it, and db/migrations holds it.  A range that the folder
        denies fails here, so the module cannot claim a migration that does not exist."""
        low, high = SCHEMA_RANGE
        self.assertEqual(
            (low, high), stated_schema_range(),
            f"{PG_STORE} must state the range of {OWNER} SCHEMA_RANGE = {SCHEMA_RANGE}")
        numbers = migration_numbers()
        self.assertIn(
            low, numbers,
            f"{OWNER} SCHEMA_RANGE = {SCHEMA_RANGE}, but db/migrations holds {numbers}")
        outside = [number for number in numbers if not low <= number <= high]
        self.assertEqual(
            outside, [],
            f"{OWNER} SCHEMA_RANGE = {SCHEMA_RANGE}, but db/migrations also holds {outside}. "
            f"State the range the store layer needs, or say why it needs no file of it.")


def ball_labels_check(sql: str) -> tuple[list[str], int]:
    """The crop-set names of `ball_labels.crop_set`'s CHECK, and its line number.

    The table body is read first, so a CHECK in another table cannot answer for this
    one. The body must hold exactly one such CHECK, so a new constraint cannot make
    the parity test pass by accident."""
    table = re.search(r"CREATE TABLE ball_labels \((.*?)\n\);", sql, re.S)
    if table is None:
        raise AssertionError(f"{MIGRATION}: no 'CREATE TABLE ball_labels (...);' found")
    checks = list(re.finditer(r"CHECK\s*\(\s*crop_set\s+IN\s*\(([^)]*)\)\s*\)", table.group(1)))
    if len(checks) != 1:
        raise AssertionError(f"{MIGRATION}: ball_labels must hold exactly one "
                             f"'CHECK (crop_set IN (...))'; found {len(checks)}")
    names = re.findall(r"'([^']*)'", checks[0].group(1))
    line = sql.count("\n", 0, table.start() + checks[0].start()) + 1
    return names, line


class VocabularyParity(unittest.TestCase):
    """The one copy that cannot import: the SQL CHECK of ball_labels.crop_set."""

    def test_the_check_names_the_owner_sets_in_the_owner_order(self):
        names, line = ball_labels_check(MIGRATION.read_text(encoding="utf-8"))
        self.assertEqual(
            names, list(BALL_SETS),
            f"the two lists differ. {MIGRATION.name}:{line} ball_labels.crop_set CHECK = "
            f"{names}; {OWNER} BALL_SETS = {list(BALL_SETS)}. Change both sides together.")

    def test_the_check_guards_the_table_the_labels_import_writes(self):
        """The constraint above must be the one that can refuse a crop_set row."""
        from src.store_import import LabelsSet
        self.assertEqual(LabelsSet.tables, ("ball_labels",),
                         "the CHECK read above guards the table the labels set writes")

    def test_every_module_shares_the_owner_object(self):
        """An import shares one object; a copy is equal and is a second spelling."""
        from annotator import unified_server
        from src import store, store_import, store_pg
        for module in (store, store_import, store_pg, unified_server):
            self.assertIs(getattr(module, "BALL_SETS"), BALL_SETS,
                          f"{module.__name__} must import BALL_SETS from {OWNER}")

    def test_the_owner_tuple_has_no_duplicate_name(self):
        self.assertEqual(len(set(BALL_SETS)), len(BALL_SETS), f"{OWNER}: names repeat")

    def test_the_labels_document_paths_follow_the_owner_tuple(self):
        self.assertEqual(document_paths("labels"),
                         [f"out/{name}/labels.json" for name in BALL_SETS])


class SourceGuard(unittest.TestCase):
    """Fail by file and line when a module spells the vocabulary again.

    The scan reads every .py and .sql file of the repository, with the unittest case
    modules left out: a case states the crop set of the row it exercises.
    """

    def test_the_owner_spells_the_vocabulary_exactly_once(self):
        tree = ast.parse((ROOT / OWNER).read_text(encoding="utf-8"))
        assignments = [node for node in ast.walk(tree)
                       if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "BALL_SETS"
                               for target in node.targets)]
        self.assertEqual(len(assignments), 1, f"{OWNER} must assign BALL_SETS once")
        self.assertEqual(tuple(ast.literal_eval(assignments[0].value)), BALL_SETS)

    def test_no_importing_module_spells_a_crop_set_name(self):
        for relative in IMPORTERS:
            path = ROOT / relative
            self.assertTrue(path.is_file(), f"{relative} is gone; update this guard")
            for line, names in code_spelling_lines(path):
                self.fail(f"{relative}:{line} spells the crop-set name(s) {names}. "
                          f"Import BALL_SETS from {OWNER} instead of writing the names.")

    def test_no_other_source_file_repeats_the_vocabulary(self):
        offenders = vocabulary_offenders(scanned_files())
        self.assertEqual(offenders, [],
                         f"these lines spell the crop-set vocabulary a second time; import "
                         f"BALL_SETS from {OWNER}: " + "; ".join(offenders))

    def test_the_scan_reports_one_planted_name_with_its_file_and_line(self):
        """Round 95: a line that held one name stayed invisible to the scan."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "planted.py"
            path.write_text(f'CROP_DIR = ROOT / "out" / "{BALL_SETS[0]}"\n', encoding="utf-8")
            self.assertEqual(vocabulary_offenders([path]),
                             [f"{path.as_posix()}:1 spells ['{BALL_SETS[0]}']"],
                             "one name in code is a finding, with its file and its line")

    def test_a_name_in_a_docstring_or_a_comment_is_no_finding(self):
        """A name in prose names the vocabulary in words; it is not a second copy."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "planted.py"
            path.write_text(f'"""The set "{BALL_SETS[0]}" is the old default."""\n'
                            f'# The scan must not fail on the set "{BALL_SETS[0]}".\n',
                            encoding="utf-8")
            self.assertTrue(spelling_lines(path), "the reader of every line sees both names")
            self.assertEqual(code_spelling_lines(path), [], "a name in prose is not code")

    def test_every_allowed_file_still_spells_a_crop_set_name(self):
        """A stale entry hides a whole file from the scan above."""
        for relative, reason in ALLOWED_SPELLINGS.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), f"{relative} is in the allowlist but is gone ({reason})")
            self.assertTrue(spelling_lines(path),
                            f"{relative} no longer spells a crop-set name ({reason}); "
                            f"remove it from ALLOWED_SPELLINGS")


class FileFormats(unittest.TestCase):
    """The byte format of a user-data file has one owner: `FORMATS` in src/store_files.py.

    Before this class existed the module docstring named a table named `FORMATS` that
    the module did not hold, and `fmt_of` answered indent2+nl for every path it did not
    know, so a new user-data file received a silent default.
    """

    def test_the_docstring_names_the_tables_the_module_holds(self):
        doc = ast.get_docstring(ast.parse((ROOT / OWNER).read_text(encoding="utf-8")))
        self.assertIn("FORMATS", doc, f"the docstring must name the format table of {OWNER}")
        self.assertIn("DOCUMENT_FORMAT", doc, f"the docstring must name the document format")
        self.assertIn("out/identity/clusters.json", FORMATS)

    def test_every_document_path_of_every_set_answers_the_document_format(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        vod = root / "out" / "vods" / "tw-2252489073"
        (vod / "frame_results" / "12").mkdir(parents=True)
        (vod / "frame_results" / "12" / "correction.json").write_text("{}", encoding="utf-8")
        paths = [path for name in DOCUMENT_SETS for path in document_paths(name, root)]
        self.assertGreater(len(paths), 5, "the sweep must cover more than the fixed names")
        self.assertTrue(any(path.startswith("out/vods/tw-2252489073/") for path in paths),
                        "an imported VOD's documents belong to the sweep")
        for path in paths:
            self.assertTrue(is_document_path(path), f"{path} comes from document_paths")
            self.assertEqual(fmt_of(path), DOCUMENT_FORMAT, path)

    def test_a_row_file_answers_indent1_and_reproduces_its_bytes(self):
        for path, fmt in FORMATS.items():
            self.assertEqual(fmt, INDENT1, path)
            self.assertFalse(is_document_path(path), path)
        self.assertEqual(dump({"a": 1}, INDENT1), '{\n "a": 1\n}')
        self.assertEqual(dump({"a": 1}, DOCUMENT_FORMAT), '{\n  "a": 1\n}\n')

    def test_the_export_rows_are_the_rows_of_the_format_table(self):
        # A row of ROW_FILES is a plain string, or the name of a path that the owner
        # holds.  The read of the name answers the value of the owner, so a rename
        # moves the row and this case stays true.
        self.assertEqual(sorted(resolve_rows()), sorted(FORMATS))

    def test_a_path_that_is_no_user_data_file_is_refused(self):
        for path in ("out/unknown.json",
                     "out/vods/tw-2252489073/nope.json",
                     "out/vods/not-a-vod/annotations.json",
                     "out/scan30/frame_results/12/verdict.json"):
            with self.assertRaises(ValueError, msg=path) as caught:
                fmt_of(path)
            self.assertIn(path, str(caught.exception))
        for path in ("out/scan30/annotations.json", "out/corner-pocket/state.json",
                     "out/pid_anchors_vod30.json", "out/pid_seed.json"):
            self.assertEqual(fmt_of(path), DOCUMENT_FORMAT, path)

    def test_no_other_source_file_spells_a_format_name(self):
        names = ("INDENT1", "INDENT2_NL", "DOCUMENT_FORMAT", "indent1", "indent2+nl")
        offenders = []
        for path in source_files():
            relative = path.relative_to(ROOT).as_posix()
            if relative in (OWNER, CHECKER):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(part in text for part in READS_OWNER):
                continue
            offenders += [f"{relative}: {name}" for name in names if name in text]
        self.assertEqual(offenders, [], f"a format name has one owner, {OWNER}")


class DatasetMapTests(unittest.TestCase):
    """One map, "built-in dataset id -> scan folder under out/": `STATIC_OUT` in src/datasets.py.

    The round-47 walk found the map typed three times: at its owner, at
    src/store_files.py:25 and at src/store_import.py:53.  A typed copy is equal today
    and silent tomorrow: the owner can rename a scan folder and the copy stays old.
    These tests hold the shipped code at one spelling, and prove that every reader
    answers the map the owner holds.
    """

    def test_the_owner_names_each_scan_folder_once(self):
        names = [node.value for node in
                 ast.walk(ast.parse((ROOT / MAP_OWNER).read_text(encoding="utf-8")))
                 if isinstance(node, ast.Constant)]
        for dataset, folder in STATIC_OUT.items():
            self.assertEqual(names.count(folder), 1,
                             f"{MAP_OWNER} must name {folder!r} once, as one whole string; "
                             f"found {names.count(folder)}")

    def test_the_map_is_the_first_column_of_the_media_table(self):
        self.assertEqual(STATIC_OUT, {key: value[0] for key, value in datasets.STATIC.items()},
                         f"{MAP_OWNER}: STATIC_OUT must derive from STATIC")

    def test_the_scan_reads_the_shape_this_change_removed(self):
        """The scan must catch the line that typed the map before this change."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "typed.py"
            path.write_text('DATASETS = {"vod30": "scan30", "highlight": "scan_highlight"}\n',
                            encoding="utf-8")
            self.assertEqual(typed_map_pairs(path), [(1, dict(STATIC_OUT))],
                             "the scan must read a typed copy of the map")

    def test_no_other_shipped_module_types_the_map(self):
        offenders = [f"{path.relative_to(ROOT).as_posix()}:{line} types {pairs}"
                     for path in shipped_modules() if path != ROOT / MAP_OWNER
                     for line, pairs in typed_map_pairs(path)]
        self.assertEqual(offenders, [],
                         f"the map has one owner, {MAP_OWNER}; import STATIC_OUT from it: "
                         + "; ".join(offenders))

    def test_every_reader_answers_the_owners_map(self):
        for relative, constant in MAP_READERS:
            module = importlib.import_module(relative[:-3].replace("/", "."))
            self.assertIs(getattr(module, constant, None), STATIC_OUT,
                          f"{relative} must import {constant} from {MAP_OWNER}")
        from src import store_files, store_import
        self.assertEqual(store_files.document_paths("anchors"),
                         [f"out/pid_anchors_{dataset}.json" for dataset in STATIC_OUT])
        for dataset, folder in STATIC_OUT.items():
            self.assertEqual(store_files.dataset_dir(dataset), f"out/{folder}")
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(sorted(store_files.dataset_dirs(Path(folder))), sorted(STATIC_OUT))
        self.assertEqual(store_import.AnchorsSet().render(NoRows()),
                         {dataset: {"anchors": {}} for dataset in STATIC_OUT})


#: The console states the default crop set in its own words: the opening state of the
#: Vision tab and the fallback of `loadDatasets`. A browser cannot import a python name,
#: so the two sites keep the name, and the guard below holds them to the owner.
APP_JS = "annotator/app.js"


def console_vocabulary_sites(text, vocabulary):
    """Every line of the console text that spells a name of the crop-set vocabulary."""
    return [(number, line) for number, line in enumerate(text.splitlines(), 1)
            if any(name in line for name in vocabulary)]


class ConsoleVocabularyTests(unittest.TestCase):
    """The console keeps the first crop-set name; the owner states it once."""

    def test_the_console_states_the_first_crop_set_of_the_owner(self):
        text = (ROOT / APP_JS).read_text(encoding="utf-8")
        sites = console_vocabulary_sites(text, BALL_SETS)
        self.assertTrue(sites, f"{APP_JS} must state its default crop set")
        for number, line in sites:
            self.assertIn(f"'{BALL_SETS[0]}'", line,
                          f"{APP_JS}:{number} spells a crop-set name that is not the first "
                          f"one of {OWNER}: {line.strip()}")

    def test_a_planted_console_name_is_reported(self):
        planted = "  set:'unlabeled_crops2',\n"
        self.assertEqual(console_vocabulary_sites(planted, BALL_SETS),
                         [(1, planted.rstrip("\n"))],
                         "the scan must report the line that holds a planted name")


if __name__ == "__main__":
    unittest.main()
