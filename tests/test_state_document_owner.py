"""The operations document path has one owner: `STATE_DOCUMENT` in src/store_files.py.

The module that states the one-owner rule held this path in three shipped places
besides the owner: the whole literal in the serving layer, at
``annotator/live_processing.py:348``; the same path built from parts at
``annotator/operations.py:383``; and the same path built from parts at
``src/enroll_from_tracklet.py:126``.  A rename of the owner would move the writer
and leave the fallback reader of the serving layer on the old file.  Nothing
would raise: the fallback is reached exactly when the normal path is absent, so
the drift appears at the worst moment.

The two sibling names had a tree walk already: ``FACE_STORE`` has
``tests/test_face_store_path_owner.py`` and ``SEED_DOCUMENT`` has
``tests/test_seed_document_owner.py``.  ``STATE_DOCUMENT`` had none, so its three
copies could drift from the owner while every case passed.

`STATE_DOCUMENT` is the one home of the path now.  Every reader imports it, so
the path stands once in the code.

The checks here read four different things on purpose:

1. the value of the owner constant, the tables that read it, and the path the
   operations object builds under its own root;
2. the source text of the shipped tree, through an `ast` walk that names every
   `file:line` site that spells the file name of the path again.  The walk reads
   the file name of the owned path and not the whole string, because a module
   that joins the parts of the path spells the name alone;
3. the import or the use of the name at every reader, so a reader that stops
   reading the owner fails this module;
4. a planted pair, a whole copy and a path built from parts, which proves that
   the walk of check 2 reports both shapes instead of passing in silence.

A test of this tree spells the path as an independent fact: it holds the owner to
the path, and a test that imported the owner could not do that.  So the walk
below reads the shipped packages (tests/_shipped.py) and never the test tree.

Run: ``./scripts/pool-test.sh python test_state_document_owner``
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from _shipped import code_strings, shipped_modules  # noqa: E402

from annotator.operations import Operations  # noqa: E402

from src.store_files import (DOCUMENT_FORMAT, FACE_STORE, SEED_DOCUMENT,  # noqa: E402
                             STATE_DOCUMENT, document_paths, fmt_of, is_document_path)

#: The owner module of the name, the name, and its assignment line.
OWNER = "src/store_files.py"
NAME = "STATE_DOCUMENT"
ASSIGNMENT = NAME + " ="

#: The path, as one whole string.  A test states this fact on purpose, so the
#: check cannot agree with a wrong owner by reading that owner.
LITERAL = "out/corner-pocket/state.json"

#: The file name of the path.  This name is the fact the tree walk holds: a
#: module that joins the parts of the path spells this name, and a module that
#: writes the whole path spells the same name after a slash.
FILE = "state.json"

#: The shipped modules that read the operations document path.  Each one must
#: take the name from the owner.  A new reader belongs in this tuple.
READERS = ("annotator/live_processing.py", "annotator/operations.py",
           "src/enroll_from_tracklet.py")


def spells_the_file_name(value: str) -> bool:
    """True when one code string is the file name of the path, alone or at the end.

    A module that joins the parts of the path holds the bare name, and a module
    that writes the whole path holds the name after a slash.  A docstring or a
    comment may name the path in words: the walk below drops the docstrings, and
    it never reads a comment.
    """
    return value == FILE or value.endswith("/" + FILE)


def copy_sites(paths) -> list[str]:
    """One `path:line` entry for every code string of `paths` that spells the file name.

    ``code_strings`` of tests/_shipped.py answers the strings of one tree, and it
    drops the docstrings.  The paths report under the repository root.
    """
    return sorted(f"{str(path).replace(str(ROOT) + '/', '')}:{number}"
                  for path in paths
                  for number, value in code_strings(ast.parse(path.read_text(encoding="utf-8"),
                                                               filename=str(path)))
                  if spells_the_file_name(value))


def shipped_sites() -> list[str]:
    """The same entries over the shipped tree, under the repository root."""
    return copy_sites(shipped_modules())


def assignment_line() -> int:
    """The line of the owner module that assigns the name, whatever its number.

    The check reads the line from the assignment itself, so a comment above the
    name moves no expectation, and a second spelling still fails the case.
    """
    lines = (ROOT / OWNER).read_text(encoding="utf-8").splitlines()
    found = [number for number, line in enumerate(lines, 1) if line.startswith(f"{ASSIGNMENT} ")]
    if len(found) != 1:
        raise AssertionError(f"{OWNER}: the assignment must stand once, and it stands {len(found)} times")
    return found[0]


def reader_names(path: Path) -> set[str]:
    """Every name one module imports from another module, and every name it reads."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                for alias in node.names}
    read = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    return imported | read


class StateDocumentOwnerTest(unittest.TestCase):
    """One path, one name, and one `file:line` site in the shipped tree."""

    def test_the_owner_holds_the_path_and_the_document_readers_agree_with_it(self):
        self.assertEqual(LITERAL, STATE_DOCUMENT, f"{OWNER}: the owner must hold the document path")
        self.assertEqual([STATE_DOCUMENT], document_paths("operations"),
                         "document_paths must answer the name of the owner")
        self.assertTrue(is_document_path(STATE_DOCUMENT),
                        f"the owner path must be a document path: {STATE_DOCUMENT}")
        self.assertEqual(DOCUMENT_FORMAT, fmt_of(STATE_DOCUMENT),
                         "the operations document keeps the format of the other documents")
        self.assertNotEqual(SEED_DOCUMENT, STATE_DOCUMENT, f"{OWNER}: the two documents are two paths")
        self.assertNotEqual(FACE_STORE, STATE_DOCUMENT, f"{OWNER}: the document is not the face store")
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(Path(folder).resolve() / LITERAL, Operations(Path(folder)).path,
                             "the operations object must build the path of the owner under its root")

    def test_every_reader_takes_the_name_from_the_owner(self):
        for relative in READERS:
            path = ROOT / relative
            self.assertTrue(path.is_file(), f"a reader must stand at {relative}")
            self.assertIn(NAME, reader_names(path),
                          f"{relative} must import or read {NAME} from {OWNER}")

    def test_no_shipped_module_spells_the_file_name_again(self):
        """The walk reports every code site outside the owner, with its line."""
        expected = f"{OWNER}:{assignment_line()}"
        sites = shipped_sites()
        self.assertIn(expected, sites, f"the walk must see the owner site, {expected}")
        self.assertEqual([expected], sites,
                         "the operations document path has one owner, " + OWNER
                         + "; import STATE_DOCUMENT from it: "
                         + "; ".join(site for site in sites if site != expected))

    def test_the_walk_reports_a_planted_copy_and_a_path_built_from_parts(self):
        """A copy must answer its own site, so the case above cannot pass in silence."""
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "state_document_copy.py"
            planted.write_text("COPY = " + repr(LITERAL) + "\n"
                               "JOINED = root / 'out' / 'corner-pocket' / " + repr(FILE) + "\n",
                               encoding="utf-8")
            self.assertEqual([f"{planted}:1", f"{planted}:2"], copy_sites([planted]),
                             "the walk must name the whole copy and the path built from parts")


if __name__ == "__main__":
    unittest.main()
