"""The seed document path has one owner: `SEED_DOCUMENT` in src/store_files.py.

The module that states the one-owner rule held the sibling path `STATE_DOCUMENT`
alone.  The seed path stood as a literal in seven shipped modules, in eight
spellings: two whole-string spellings at the owner module, one whole-string
spelling at each of src/store_check.py, src/store_import.py, src/store_pg.py and
src/eval_faces.py, and two path-part spellings, at src/store.py and
src/pid_seed_ui.py.  A rename or a move of the seed document split the writer from
the readers with no error.

`SEED_DOCUMENT` is the one home of that path now.  Every reader imports it, so
the path stands once in the code.

The three checks here read three different things on purpose:

1. the value of the owner constant, and the writers that take the file name from
   its last part;
2. the source text of the shipped tree, through an `ast` walk that names every
   `file:line` site that spells the literal again;
3. a planted copy, which proves that the walk of check 2 reports a second
   spelling instead of passing in silence.

A test of this tree spells the path as an independent fact: it holds the owner to
the path, and a test that imported the owner could not do that.  So the walk below
reads the shipped packages (tests/_shipped.py) and never the test tree.

Run: ``./scripts/pool-test.sh python test_seed_document_owner``
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from _shipped import shipped_modules  # noqa: E402

from src.store import JsonStore  # noqa: E402
from src.store_files import (SEED_DOCUMENT, STATE_DOCUMENT, document_paths,  # noqa: E402
                             fmt_of, is_document_path)
from src.store_pg import _doc_path  # noqa: E402

#: The owner module of the name, and its assignment line, `SEED_DOCUMENT = ...`.
OWNER = "src/store_files.py"
ASSIGNMENT = "SEED_DOCUMENT ="

#: The path, as one whole string.  A test states this fact on purpose, so the
#: check cannot agree with a wrong owner by reading that owner.
LITERAL = "out/pid_seed.json"


def spelled_strings(path: Path) -> list[tuple[int, str]]:
    """(line number, value) for every string any expression of `path` spells.

    The walk reads docstrings and constants alike: a manifest, a JSON document of
    this shape, or a call the name is spread across.  A module that computes the
    path from parts spells no one whole string, and the value check below treats
    it as a reader of the name instead."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        for value in ast.walk(node):
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.append((value.lineno, value.value))
    return sorted(set(found))


def spelling_sites(paths) -> list[str]:
    """One `path:line` entry for every string of `paths` that spells the path."""
    return [f"{path}:{number}"
            for path in paths
            for number, value in spelled_strings(path)
            if value == LITERAL]


def shipped_sites() -> list[str]:
    """The same entries over the shipped tree, under the repository root."""
    return [site.replace(str(ROOT) + "/", "") for site in spelling_sites(shipped_modules())]


def assignment_line() -> int:
    """The line of the owner module that assigns the name, whatever its number.

    The check reads the line from the assignment itself, so a comment above the
    name moves no expectation, and a second spelling still fails the case."""
    lines = (ROOT / OWNER).read_text(encoding="utf-8").splitlines()
    found = [number for number, line in enumerate(lines, 1) if line.startswith(f"{ASSIGNMENT} ")]
    if len(found) != 1:
        raise AssertionError(f"{OWNER}: the assignment must stand once, and it stands {len(found)} times")
    return found[0]


class SeedDocumentOwnerTest(unittest.TestCase):
    """One path, one name, and one `file:line` site in the shipped tree."""

    def test_the_owner_holds_the_path_and_every_writer_reads_the_name(self):
        self.assertEqual(LITERAL, SEED_DOCUMENT, f"{OWNER}: the owner must hold the seed path")
        self.assertNotEqual(STATE_DOCUMENT, SEED_DOCUMENT,
                            f"{OWNER}: the two document paths are two paths")
        self.assertEqual([SEED_DOCUMENT], document_paths("seeds"),
                         "document_paths must answer the name of the owner")
        self.assertTrue(is_document_path(SEED_DOCUMENT),
                        f"the owner path must be a document path: {SEED_DOCUMENT}")
        self.assertEqual(fmt_of(SEED_DOCUMENT), fmt_of(STATE_DOCUMENT),
                         "the two documents share one format")
        self.assertEqual(SEED_DOCUMENT, _doc_path("seeds", "vod30"),
                         "the PostgreSQL store must answer the name of the owner")
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(Path(folder) / LITERAL, JsonStore(Path(folder))._seeds_path("vod30"),
                             "the JSON store must build the path of the owner under its root")

    def test_no_shipped_module_spells_the_path_again(self):
        sites = shipped_sites()
        expected = f"{OWNER}:{assignment_line()}"
        self.assertEqual([expected], sites,
                         "the seed path has one owner, " + OWNER
                         + "; import SEED_DOCUMENT from it: " + "; ".join(sites))

    def test_the_walk_reports_a_planted_copy(self):
        """A copy must answer its own site, so the case above cannot pass in silence."""
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "store_files.py"
            text = (ROOT / OWNER).read_text(encoding="utf-8")
            line = len(text.splitlines()) + 2
            planted.write_text(text + f'\nCOPY = "{LITERAL}"\n', encoding="utf-8")
            sites = spelling_sites([planted])
            self.assertIn(f"{planted}:{line}", sites,
                          "the walk must name the line of a planted copy")
            self.assertEqual(2, len(sites),
                             "the walk must see the owner spelling and the copy: " + "; ".join(sites))


if __name__ == "__main__":
    unittest.main()
