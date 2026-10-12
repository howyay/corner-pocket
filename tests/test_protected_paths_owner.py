"""The protected-path list has one owner: `PROTECTED` in src/eval_faces.py.

The files the demo must never write were held by three lists that disagreed.
`PROTECTED` of `src/enroll_from_tracklet.py` held two paths and no reader read
it, so the enrolment flow promised protection and gave none.  The live list was
`PROTECTED` of `src/eval_faces.py:92` with five paths, read by `md5_files` at
`src/eval_faces.py:722` around the demo.  A third hand-written copy stood in the
protection cases of `tests/test_enroll_from_tracklet.py`.

Round 80 gave the list one binding.  `src/eval_faces.py` owns it, the enrolment
module holds no copy, and the protection cases of the enrolment test read the
owner.  The three cases here hold that decision:

1. `test_the_owner_holds_the_binding` reads the owner module itself: one
   `PROTECTED` binding stands at its top level, and when it is not there the
   module has no name to read.  A quiet deletion fails this case.
2. `test_no_other_module_holds_the_binding` walks the shipped packages
   (``tests/_shipped.py:SHIPPED``) and the test modules, and reports every
   `PROTECTED` binding outside the owner.  A third copy fails this case.
3. `test_the_enrolment_test_reads_the_owner` reads the source of the enrolment
   test: it takes the name from the owner and uses it.  A test that states the
   paths again, and binds the name itself, fails here.

The two enrolment paths stay literals below.  A case that states an expectation
must not read the value it checks: `DEFAULT_STATE` of the enrolment module would
agree with its own `write_enrollment`.

Run: ``./scripts/pool-test.sh python test_protected_paths_owner``
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

from src import eval_faces  # noqa: E402

#: The owner module of the list and the name of the list.
OWNER = "src/eval_faces.py"
NAME = "PROTECTED"

#: The two paths the enrolment flow must never write, as whole strings.
ENROLMENT_PATHS = ("out/corner-pocket/state.json",
                   "out/corner-pocket/face_embeddings.json")

#: The reader that takes the name from the owner instead of stating the paths.
ENROLMENT_TEST = "tests/test_enroll_from_tracklet.py"


def protected_bindings(paths) -> list[str]:
    """One ``path:line`` entry for every top-level binding of the name in `paths`.

    A binding is an assignment statement whose target is the plain name, so
    ``PROTECTED = (...)`` answers and ``eval_faces.PROTECTED`` does not.  The walk
    reads ``tree.body`` only: the owner states the list at the top level, where
    both readers can import it, and an inner assignment is a local variable.
    """
    found = []
    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == NAME
                    for target in node.targets):
                found.append(f"{path}:{node.lineno}")
    return sorted(found)


class ProtectedPathsOwnerTest(unittest.TestCase):
    """One list of protected paths, one binding, and both readers on the owner."""

    def test_the_owner_holds_the_binding(self):
        """The owner binds the name at its top level, and the list holds both paths."""
        sites = protected_bindings([ROOT / OWNER])
        self.assertEqual(1, len(sites),
                         f"{OWNER} must bind {NAME} once at the top level; the walk found "
                         + (", ".join(sites) if sites else "no binding"))
        for path in ENROLMENT_PATHS:
            self.assertIn(path, eval_faces.PROTECTED,
                          f"{OWNER}: the list must hold {path}")

    def test_no_other_module_holds_the_binding(self):
        """The walk names every binding outside the owner, in the shipped tree and the tests."""
        owner_site = protected_bindings([ROOT / OWNER])[0]
        walk = shipped_modules() + sorted((ROOT / "tests").glob("test_*.py"))
        self.assertEqual([owner_site], [site for site in protected_bindings(walk)
                                        if site == owner_site],
                         f"the walk must see the one binding of {OWNER}")
        self.assertTrue(any(path.name == "test_protected_paths_owner.py" for path in walk),
                        "the walk must read the test modules too")
        outside = [site for site in protected_bindings(walk)
                   if not site.startswith(f"{ROOT / OWNER}:")]
        self.assertEqual([], outside,
                         f"`{NAME}` has one owner, {OWNER}; read the name from the owner "
                         "and delete the binding below: " + "; ".join(outside))

    def test_the_enrolment_test_reads_the_owner(self):
        """The enrolment test imports the name, uses it, and binds it nowhere."""
        path = ROOT / ENROLMENT_TEST
        source = path.read_text(encoding="utf-8")
        self.assertIn(f"from src.eval_faces import {NAME}", source,
                      f"{ENROLMENT_TEST} must import the name from {OWNER}")
        self.assertIn(NAME, {node.id for node in ast.walk(ast.parse(source, filename=str(path)))
                             if isinstance(node, ast.Name)},
                      f"{ENROLMENT_TEST} must read the name it imports")
        self.assertEqual([], protected_bindings([path]),
                         f"{ENROLMENT_TEST} must not bind the name again")

    def test_the_walk_reports_a_planted_binding(self):
        """A copy must answer its own site, so the case above cannot pass in silence."""
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted.py"
            planted.write_text(f"{NAME} = ('out/planted.json',)\n", encoding="utf-8")
            self.assertEqual([f"{planted}:1"], protected_bindings([planted]),
                             "the walk must name the line of a planted binding")
            reader = Path(folder) / "reader.py"
            reader.write_text(f"from src.eval_faces import {NAME}\nprint({NAME})\n",
                              encoding="utf-8")
            self.assertEqual([], protected_bindings([reader]),
                             "a reader that imports the name binds nothing")


if __name__ == "__main__":
    unittest.main()
