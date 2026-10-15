"""The module docstring of annotator/server.py must name the true endpoint count.

annotator/server.py:4 says "Serves the static app (index.html) plus six API endpoints:".
That count is a claim about the router below it.  This walk reads the count word out of the
docstring and counts the distinct `/api/` paths the handler compares `self.path` against.
The two numbers must agree, so a new route reddens the claim.

The record of round 110 measured the defect: the docstring said two, the file answered six.
"""
from __future__ import annotations

import ast
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER = ROOT / "annotator" / "server.py"
WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve")


def docstring_of(path: pathlib.Path) -> str:
    return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""


def claimed_count(text: str):
    """Answer (count, None) or (None, why the claim cannot be read)."""
    match = re.search(r"plus ([a-z]+) API endpoints", text)
    if match is None:
        return None, "the docstring does not state the count of the API endpoints"
    word = match.group(1)
    if word not in WORDS:
        return None, f"the docstring states an unknown count word: {word}"
    return WORDS.index(word), None


def routed_paths(source: str) -> set:
    """The distinct /api/ path constants compared against self.path."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if not (isinstance(left, ast.Attribute) and left.attr == "path"):
            continue
        for comparator in node.comparators:
            for part in ast.walk(comparator):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    if part.value.startswith("/api/"):
                        found.add(part.value)
    return found


class ServerEndpointCountTest(unittest.TestCase):
    def test_the_docstring_names_the_count_of_the_router(self):
        claimed, why = claimed_count(docstring_of(SERVER))
        paths = routed_paths(SERVER.read_text(encoding="utf-8"))
        self.assertIsNone(why)
        self.assertEqual(
            claimed, len(paths),
            "annotator/server.py:4 states %s API endpoints; the router compares self.path "
            "against %d: %s" % (claimed, len(paths), sorted(paths)))

    def test_the_router_serves_the_six_measured_paths(self):
        self.assertEqual(
            {"/api/actors", "/api/annotate", "/api/annotations", "/api/ball_label",
             "/api/crops", "/api/events"},
            routed_paths(SERVER.read_text(encoding="utf-8")))

    def test_the_walk_reads_the_file_it_names(self):
        self.assertGreaterEqual(len(SERVER.read_text(encoding="utf-8").splitlines()), 150,
                                "the walk must read the shipped server and not a stub")

    def test_a_planted_wrong_count_reddens(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = pathlib.Path(tmp) / "server.py"
            copy.write_text(SERVER.read_text(encoding="utf-8").replace(
                "plus six API endpoints", "plus five API endpoints"), encoding="utf-8")
            claimed, why = claimed_count(docstring_of(copy))
            self.assertIsNone(why)
            self.assertEqual(5, claimed)
            self.assertNotEqual(claimed, len(routed_paths(copy.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    unittest.main()
