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
import re
import unittest
from pathlib import Path

from src.store_files import BALL_SETS, document_paths

ROOT = Path(__file__).resolve().parents[1]
OWNER = "src/store_files.py"
MIGRATION = ROOT / "db" / "migrations" / "0002_user_data.sql"
# The modules that import the vocabulary from its owner. They must hold no copy.
IMPORTERS = ("src/store.py", "src/store_import.py", "src/store_pg.py",
             "annotator/unified_server.py")
# Files that spell crop-set names for a reason, and the reason. Every other file that
# spells two or more names on one line fails the scan below.
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
    """Fail by file and line when a module spells the vocabulary again."""

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
            for line, names in spelling_lines(path):
                self.fail(f"{relative}:{line} spells the crop-set name(s) {names}. "
                          f"Import BALL_SETS from {OWNER} instead of writing the names.")

    def test_no_other_source_file_repeats_the_vocabulary(self):
        offenders = [f"{path.relative_to(ROOT).as_posix()}:{line} spells {names}"
                     for path in source_files()
                     if path.relative_to(ROOT).as_posix() not in ALLOWED_SPELLINGS
                     for line, names in spelling_lines(path) if len(names) >= 2]
        self.assertEqual(offenders, [],
                         f"these lines spell the crop-set vocabulary a second time; import "
                         f"BALL_SETS from {OWNER}: " + "; ".join(offenders))

    def test_every_allowed_file_still_spells_a_crop_set_name(self):
        """A stale entry hides a whole file from the scan above."""
        for relative, reason in ALLOWED_SPELLINGS.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), f"{relative} is in the allowlist but is gone ({reason})")
            self.assertTrue(spelling_lines(path),
                            f"{relative} no longer spells a crop-set name ({reason}); "
                            f"remove it from ALLOWED_SPELLINGS")


if __name__ == "__main__":
    unittest.main()
