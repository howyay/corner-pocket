"""The refusal sentence `unknown dataset` has one home, `annotator/refusals.py`.

Round 109 found the sentence in three places: the key of one row of `REFUSALS`, and two
raises of `annotator/unified_server.py` (`enroll_preview` and `registered`).  The row
answers the sentence the API raised, so the three stand or fall together.  The guard
`tests/test_refusal_identity.py` already welds them, because it holds that every row names
a sentence some raise site states.  That weld reads the sentence at runtime; it does not
stop a second literal.

The cases below hold four facts:

1. the home line holds the sentence, and the table row keys it by name;
2. no other module under ``annotator/`` spells the sentence as a string literal;
3. a planted copy answers its own site, so case 2 cannot pass in silence;
4. the two raise sites read the name, so a rename reaches them.

Run: ``./scripts/pool-test.sh python test_unknown_dataset_token_owner``
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from annotator.refusals import REFUSALS, UNKNOWN_DATASET  # noqa: E402

#: The home module is the one module that may hold the sentence as a literal.
HOME = ROOT / "annotator" / "refusals.py"

#: The reader that raises the sentence twice.
READER = ROOT / "annotator" / "unified_server.py"

#: The name the table row and the two raises read.
NAME = "UNKNOWN_DATASET"

SENTENCE = "unknown dataset"


def spelled_strings(path: Path) -> list[tuple[int, str]]:
    """The (line, text) of every string literal of one module, docstrings dropped."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            docstrings.add(id(body[0].value))
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def spelling_sites(paths, sentence: str = SENTENCE) -> list[str]:
    """One `path:line quotes sentence` entry for every literal that spells the sentence."""
    entries = []
    for path in paths:
        for number, value in spelled_strings(path):
            if value == sentence:
                entries.append(f"{path}:{number} quotes {sentence}")
    return sorted(entries)


def modules() -> list[Path]:
    return sorted(ROOT.joinpath("annotator").glob("*.py"))


class UnknownDatasetToken(unittest.TestCase):
    def test_the_home_holds_the_sentence(self):
        tree = ast.parse(HOME.read_text(encoding="utf-8"), filename=str(HOME))
        held = [node.lineno for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == NAME for t in node.targets)
                and isinstance(node.value, ast.Constant) and node.value.value == SENTENCE]
        self.assertEqual(len(held), 1,
                         f"{HOME} must state {NAME} = \"{SENTENCE}\" one time at module level")
        self.assertEqual(UNKNOWN_DATASET, SENTENCE,
                         f"the home answers one sentence: {UNKNOWN_DATASET!r}")

    def test_the_table_row_keys_the_home(self):
        tree = ast.parse(HOME.read_text(encoding="utf-8"), filename=str(HOME))
        keys = [key for node in ast.walk(tree) if isinstance(node, ast.Dict)
                for key in node.keys
                if isinstance(key, ast.Name) and key.id == NAME]
        self.assertEqual(len(keys), 1,
                         f"one row of REFUSALS must key {NAME}, not a literal again")
        self.assertEqual(REFUSALS[SENTENCE].code, "dataset_unknown",
                         "the row of the sentence answers the code dataset_unknown")

    def test_no_other_module_spells_the_sentence(self):
        offenders = [site for site in spelling_sites(modules())
                     if not site.startswith(str(HOME))]
        self.assertEqual(offenders, [],
                         "the sentence has one home, " + str(HOME) + "; read " + NAME
                         + " from it: " + "; ".join(offenders))

    def test_the_reader_reads_the_name(self):
        tree = ast.parse(READER.read_text(encoding="utf-8"), filename=str(READER))
        imports = [alias.name for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.module == "annotator.refusals"
                   for alias in node.names]
        self.assertIn(NAME, imports, f"{READER} raises the sentence and must read {NAME}")

    def test_the_walk_reports_a_planted_copy(self):
        """A copy must answer its own site, so the case above cannot pass in silence."""
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_caller.py"
            planted.write_text(f'RAISE = "{SENTENCE}"\n', encoding="utf-8")
            self.assertEqual(spelling_sites([planted]),
                             [f"{planted}:1 quotes {SENTENCE}"],
                             "the walk must name the line of a planted copy")


if __name__ == "__main__":
    unittest.main()
