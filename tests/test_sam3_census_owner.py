"""The census file has one owner, and no other module of ``src/`` names it.

The SAM3 census file ``out/scan30/sam3_census.json`` has one writer,
``src/sam3_ball_cache.py``, and that writer names it once, as ``OWN_CACHE``.  Six
reader sites in five other modules of ``src/`` spelled the name again before this
round:

* ``src/tiny_ball_net.py``, as the module constant ``CENSUS`` and again inside
  ``load_labels``, as the last part of the path it takes from ``root``;
* ``src/candidate_scan.py``, inside ``write_plan``, as the last part of the path
  it takes from ``out_dir``;
* ``src/motion_scan.py``, inside ``load_census``, under the folder names that
  function derives from the dataset name;
* ``src/ball_fp_audit.py`` and ``src/fast_ball_labels.py``, which row 1 of this
  round gave to other writers.

A rename of the file in the writer moved the writer alone and left those readers
on the old name, in silence: three of them hide the miss behind ``if
path.exists()``.  This module states the rule and it reports every site that
breaks it:

1. ``report`` reads one module and returns the line and the text of every
   non-docstring string that states the census file name, or a part of it;
2. the three readers of this round are clean, and they bind the owner's name;
3. the walk of the shipped tree reports no site outside the owner;
4. ``report`` sees a planted copy in a scratch file, and it sees a path built
   from parts, so a green answer of point 3 cannot come from a blind walk.

The cases read source text with the helpers of ``tests/_shipped.py``.  They do
not decode a video, do not run SAM3, and do not write under ``out/``.

Run: ``./scripts/pool-test.sh python test_sam3_census_owner``
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from _shipped import code_strings, shipped_modules  # noqa: E402

#: The owner of the census path, the name it binds, and the parts of its file name.
OWNER = "src/sam3_ball_cache.py"
OWNER_NAME = "OWN_CACHE"
CENSUS_NAME = "sam3_census.json"
CENSUS_STEM = "sam3_census"
CENSUS_SUFFIX = ".json"

#: The readers of the census that this writer changed.
MY_READERS = ("src/tiny_ball_net.py", "src/candidate_scan.py", "src/motion_scan.py")


def relative(path) -> str:
    """One path, as this repository reports it: under the root, without the root."""
    return Path(path).relative_to(ROOT).as_posix()


def tree_of(module) -> ast.AST:
    """The syntax tree of one module, given as a path or as a name under ``src/``."""
    path = ROOT / module if isinstance(module, str) else Path(module)
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def literal_findings(module) -> list:
    """(line, text) for every non-docstring string of one module that states the census name.

    ``tests/_shipped.py`` holds the walk of the string literals, so this module
    keeps one rule: a literal that holds ``sam3_census`` states the file name,
    in the whole name or in a part of it.
    """
    return [("literal", line, text) for line, text in code_strings(tree_of(module))
            if CENSUS_STEM in text]


def built_findings(module) -> list:
    """(line, text) for every site of one module that adds string values, when the sum is a census name.

    A name built from parts holds no literal of the whole file name, so the walk
    of the literals cannot see it.  This reader sees it: it joins the string
    constants of one ``+`` expression and asks whether the answer states the
    census name.  A sum of other names is not a finding, so a plain
    ``name + '.json'`` stays quiet.
    """
    found = []
    for node in ast.walk(tree_of(module)):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)):
            continue
        parts = [part.value for part in ast.walk(node)
                 if isinstance(part, ast.Constant) and isinstance(part.value, str)]
        if CENSUS_NAME in "".join(parts) or CENSUS_STEM in "".join(parts):
            found.append(("built", node.lineno, ast.unparse(node)))
    return found


def report(module) -> list:
    """(line, text) for every site of one module that states the census file name, or a part."""
    return literal_findings(module) + built_findings(module)


def binds_owner(module) -> bool:
    """True when one module imports the owner's name from the owner."""
    for node in ast.walk(tree_of(module)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == Path(OWNER).stem:
            if any(alias.name == OWNER_NAME for alias in node.names):
                return True
    return False


class TheRule(unittest.TestCase):
    """Points 1 and 4: the reader of the rule sees a plain copy and a built path."""

    maxDiff = None

    def scratch_module(self, text: str, name: str = "planted.py") -> Path:
        """Write one module under a temporary directory and return its path."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_reader_that_spells_the_name_again_is_reported(self):
        planted = self.scratch_module(
            "CENSUS = ROOT / 'out' / 'scan30' / 'sam3_census.json'\n"
            "for path in (root / 'out' / 'scan30' / 'sam3_census.json',):\n"
            "    pass\n")
        lines = [line for _, line, _ in report(planted)]
        self.assertEqual(lines, [1, 2], "both hand-spelled sites must be reported")

    def test_a_path_built_from_parts_is_reported(self):
        planted = self.scratch_module(
            "name = 'sam3_' + 'census' + '.json'\n"
            "path = root / 'out' / 'scan30' / name\n")
        built = [(line, text) for kind, line, text in report(planted) if kind == "built"]
        self.assertNotEqual(built, [], "a name built from parts must be reported")

    def test_a_module_that_reads_the_owner_is_quiet(self):
        planted = self.scratch_module(
            "from src.sam3_ball_cache import OWN_CACHE\n"
            "path = root / OWN_CACHE\n")
        self.assertEqual(report(planted), [], "a reader of the owner must pass the rule")

    def test_a_comment_that_names_the_file_is_not_a_finding(self):
        planted = self.scratch_module("# the census is out/scan30/sam3_census.json\nvalue = 1\n")
        self.assertEqual(report(planted), [], "a comment states no path of the code")


class MyReaders(unittest.TestCase):
    """Point 2: the three readers of this round are clean, and they read the owner."""

    maxDiff = None

    def test_the_three_readers_state_no_census_name(self):
        for module in MY_READERS:
            with self.subTest(module=module):
                self.assertEqual(report(module), [], f"{module} states the census file name again")

    def test_the_three_readers_bind_the_owner(self):
        missing = [module for module in MY_READERS if not binds_owner(module)]
        self.assertEqual(missing, [], f"these readers do not bind {OWNER_NAME}: {missing}")


class TheShippedTree(unittest.TestCase):
    """Point 3: the walk of the shipped packages reports no site outside the owner."""

    maxDiff = None

    def test_no_shipped_module_outside_the_owner_names_the_census(self):
        offenders = {relative(module): report(module) for module in shipped_modules()
                     if relative(module) != OWNER and report(module)}
        self.assertEqual(offenders, {},
                         f"these modules state the census file name again: {sorted(offenders)}")

    def test_the_owner_states_the_name_once(self):
        hits = [line for _, line, text in literal_findings(OWNER) if CENSUS_NAME in text]
        self.assertEqual(len(hits), 1, "the owner states the whole census file name one time")


if __name__ == "__main__":
    unittest.main()
