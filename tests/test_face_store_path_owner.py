"""The face store path has one owner: `FACE_STORE` in src/store_files.py.

The face store is the one user-data file that holds biometric data.  The path
`out/corner-pocket/face_embeddings.json` stood as a bare literal in five shipped
places: the format table of the owner module, twice in one line of
src/store_export.py, in the row-file list of that module, in src/store_import.py,
and in the PROTECTED list of src/eval_faces.py.  Its two siblings, the operations
document and the seed document, were names.  A rename would make the importer
read a file that is not there and make the measurement tool protect a file that
nobody writes.  No case held the three sites together.

`FACE_STORE` is the one home of the path now.  Every reader imports the name.

The checks here read four different things on purpose:

1. the source text of the shipped packages (tests/_shipped.py), through an `ast`
   walk that names every code site that holds the literal again.  The walk
   leaves docstrings out, so a module may name the path in words;
2. the value of the owner constant and the two tables that read it;
3. the import or the use of the name at every reader, so a reader that stops
   reading the owner fails this module;
4. a copy that is not the owner assignment, written into a temporary tree, so
   check 1 cannot pass in silence.

A test that states the path as an independent fact cannot import the owner for
it: the case would agree with a wrong owner.  The literal below stays a literal
for that reason.  The walk reads the shipped packages and never the test tree.

Run: ``./scripts/pool-test.sh python test_face_store_path_owner``
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

from src import eval_faces, store_export, store_import, store_files  # noqa: E402
from src.store_files import FACE_STORE, FORMATS, INDENT1, STATE_DOCUMENT, fmt_of  # noqa: E402

#: The owner module of the name and the name itself.
OWNER = "src/store_files.py"
NAME = "FACE_STORE"

#: The path, as one whole string.  A test states this fact on purpose, so the
#: check cannot agree with a wrong owner by reading that owner.
LITERAL = "out/corner-pocket/face_embeddings.json"

#: The shipped modules that read the face store path.  Each one must take the
#: name from the owner.  A new reader belongs in this tuple.
READERS = ("src/store_files.py", "src/store_export.py", "src/store_import.py",
           "src/eval_faces.py")


def literal_sites(paths) -> list[str]:
    """One `path:line` entry for every code site of `paths` that holds the literal.

    ``code_strings`` of tests/_shipped.py answers the strings of one tree, and it
    drops the docstrings.  A docstring names the path in words; the rule of the
    owner module allows that.  The paths report under the repository root.
    """
    return sorted(f"{str(path).replace(str(ROOT) + '/', '')}:{number}"
                  for path in paths
                  for number, value in code_strings(ast.parse(path.read_text(encoding="utf-8"),
                                                               filename=str(path)))
                  if value == LITERAL)


def assignment_lines(path: Path) -> list[int]:
    """The lines of `path` that assign the name at the top level of the module."""
    return [node.lineno for node in ast.parse(path.read_text(encoding="utf-8"),
                                              filename=str(path)).body
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == NAME
                                                    for target in node.targets)]


def assignment_line(path: Path) -> int:
    """The one line of `path` that assigns the name, or an error for any other count.

    The walk reads the assignment site itself, so a comment above the name moves
    no expectation.  A planted copy that is not an assignment answers no line
    here, and the literal walk reports that copy as its own site.
    """
    found = assignment_lines(path)
    if len(found) != 1:
        raise AssertionError(f"{path}: the assignment of {NAME} must stand once at the top level, "
                             f"and it stands {len(found)} times")
    return found[0]


def reads_the_name(path: Path) -> bool:
    """True when the module takes the name from its owner: an import, or a use.

    An import of the name is one whole answer.  A use of the name is the other:
    a reader that defines its own name and reads it passes here, and check 1
    reports its literal when the module holds one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == NAME for alias in node.names):
            return True
        if isinstance(node, ast.Name) and node.id == NAME:
            return True
    return False


class FaceStorePathOwnerTest(unittest.TestCase):
    """One path, one name, and one code site in the shipped tree."""

    def test_the_owner_holds_the_path_and_both_tables_read_the_name(self):
        owner = ROOT / OWNER
        self.assertEqual(LITERAL, FACE_STORE, f"{OWNER}: the owner must hold the face store path")
        self.assertEqual([assignment_line(owner)], assignment_lines(owner),
                         f"{OWNER}: one top-level assignment holds the path")
        self.assertNotEqual(STATE_DOCUMENT, FACE_STORE,
                            f"{OWNER}: the face store is not the operations document")
        self.assertIn(FACE_STORE, FORMATS, f"{OWNER}: the format table must read the name")
        self.assertEqual(INDENT1, fmt_of(FACE_STORE),
                         "the face store keeps its writer's format, indent=1")
        self.assertIn(FACE_STORE, store_export.ROW_FILES,
                      "the row-file list of src/store_export.py must read the name")

    def test_no_shipped_module_holds_the_literal_again(self):
        """The walk reports every code site outside the owner, with its line."""
        expected = f"{OWNER}:{assignment_line(ROOT / OWNER)}"
        sites = literal_sites(shipped_modules())
        self.assertIn(expected, sites, f"the walk must see the owner site, {expected}")
        self.assertEqual([expected], sites,
                         f"the face store path has one owner, {OWNER}; the sites below hold a copy, "
                         "so import FACE_STORE from the owner: "
                         + "; ".join(site for site in sites if site != expected))

    def test_every_reader_takes_the_name_from_the_owner(self):
        for relative in READERS:
            path = ROOT / relative
            self.assertTrue(path.is_file(), f"a reader must stand at {relative}")
            self.assertTrue(reads_the_name(path),
                            f"{relative} must import or read {NAME} from {OWNER}")
        self.assertIs(FACE_STORE, store_files.FACE_STORE, f"{OWNER} holds the name")
        for module in (store_export, store_import, eval_faces):
            self.assertIs(FACE_STORE, module.FACE_STORE,
                          f"{module.__name__} must bind the name of the owner")
        self.assertIn(FACE_STORE, eval_faces.PROTECTED,
                      "the PROTECTED list of src/eval_faces.py must read the name")

    def test_the_walk_reports_a_planted_copy(self):
        """A copy must answer its own site, so the case above cannot pass in silence."""
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "face_store_copy.py"
            planted.write_text("COPY = " + repr(LITERAL) + "\n", encoding="utf-8")
            self.assertEqual([], assignment_lines(planted),
                             "a plain copy is not the assignment of the owner name")
            self.assertEqual([f"{planted}:1"], literal_sites([planted]),
                             "the walk must name the line of a planted copy")
            owner_site = f"{OWNER}:{assignment_line(ROOT / OWNER)}"
            self.assertNotIn(owner_site, literal_sites([planted]),
                             "the planted tree holds no site of the owner")


if __name__ == "__main__":
    unittest.main()
