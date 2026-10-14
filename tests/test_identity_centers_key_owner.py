"""One home for the identity artifact key: `src/pid_identity.py` holds it.

The fact is the key that carries the BGR prototypes of the two colour clusters
in the identity document.  The writer builds the document, and the two shooters
read the key from the document at import time.

The three live copies at the round-107 walk were:

* `src/pid_identity.py:195` — the writer row of the document, and the key as a
  quoted literal;
* `src/pid_shooter.py:52` — the reader indexes the identity document with it;
* `src/pid_shooter2.py:40` — the second reader does the same.

Round 107 W4 gave the name one home, `CENTERS_BGR_KEY` in `src/pid_identity.py`,
and all three sites read it.  The key itself did not change: the identity
document on disk carries the text `centers_bgr`, and the value pin below holds
that shipped text.

This module holds the name once, as `NAME`.  The value pin must read the
shipped value, because a case that reads both sides from the same home stays
green when the home value moves.

The cases:

* the owner holds one definition of the name, as a module-level string;
* the owner writes the reference through the home, and the quoted name stands
  once in that file, on the home line;
* each shooter imports the home and reads the document through it, and holds no
  quoted name;
* the three sites name the same text, so one home moves the writer and the two
  readers at once;
* the walk over the tracked trees answers no copy;
* the walk is honest: a planted copy in a shooter is an offender with its path
  and line, and a moved value in the owner fails the value pin.

Run: ``./scripts/pool-test.sh python test_identity_centers_key_owner``
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The fact this module guards: the shipped key of the BGR prototypes.
NAME = "centers_bgr"
OWNER = "src/pid_identity.py"
OWNER_NAME = "CENTERS_BGR_KEY"
#: The two modules that read the key from the identity document.
READERS = ("src/pid_shooter.py", "src/pid_shooter2.py")
#: The trees the walk reads.
WALK_DIRS = ("src", "annotator", "tests", "tools", "scripts")
#: This module, which holds the pin line.
PIN_MODULE = "tests/test_identity_centers_key_owner.py"


def read_text(rel: str) -> str:
    """The text of one tracked file, as UTF-8."""
    return (ROOT / rel).read_text(encoding="utf-8")


def quoted_name_lines(text: str) -> list[tuple[int, str]]:
    """Every line that spells the name as a quoted literal, with its number."""
    out = []
    for number, line in enumerate(text.splitlines(), start=1):
        if f'"{NAME}"' in line or f"'{NAME}'" in line:
            out.append((number, line))
    return out


def walk_offenders(pairs) -> list[str]:
    """Every quoted spelling of the name outside the home of the owner.

    `pairs` holds `(path, text)` rows.  The answer is a list of
    `path:line: <the line text>` rows, so a failure names its site.
    """
    offenders = []
    for rel, text in pairs:
        for number, line in quoted_name_lines(text):
            if rel == OWNER and line.strip().startswith(f"{OWNER_NAME} ="):
                continue  # the home of the owner
            if rel == PIN_MODULE and line.strip().startswith("NAME = "):
                continue  # the pin of this module
            offenders.append(f"{rel}:{number}: {line.strip()}")
    return offenders


def owner_value(text: str) -> str | None:
    """The value of the home assignment in the owner module, or None."""
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == OWNER_NAME:
                    if isinstance(node.value, ast.Constant):
                        return str(node.value.value)
    return None


def tracked_pairs() -> list[tuple[str, str]]:
    """The text of every tracked python file of the walked trees."""
    pairs = []
    for tree in WALK_DIRS:
        for path in sorted((ROOT / tree).rglob("*.py")):
            rel = str(path.relative_to(ROOT))
            pairs.append((rel, path.read_text(encoding="utf-8")))
    return pairs


class IdentityCentersKeyOwnerTests(unittest.TestCase):
    def test_the_owner_holds_one_definition_of_the_name(self):
        owner_text = read_text(OWNER)
        tree = ast.parse(owner_text)
        home_lines = []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == OWNER_NAME:
                        home_lines.append(node.lineno)
        self.assertEqual(len(home_lines), 1,
                         f"the owner holds {len(home_lines)} definitions of {OWNER_NAME}")
        self.assertEqual(owner_value(owner_text), NAME,
                         f"{OWNER}:{home_lines[0]}: the home value is not the shipped name")

    def test_the_owner_writes_the_reference_through_the_home(self):
        owner_text = read_text(OWNER)
        writer = [number for number, line in enumerate(owner_text.splitlines(), start=1)
                  if line.strip().startswith(f"{OWNER_NAME}:")]
        self.assertEqual(len(writer), 1,
                         f"the owner writes the reference at {len(writer)} sites, not 1")
        self.assertEqual(walk_offenders([(OWNER, owner_text)]), [],
                         "the owner spells the name outside the home line")

    def test_each_reader_takes_the_name_from_the_home(self):
        for rel in READERS:
            text = read_text(rel)
            self.assertIn(f"from pid_identity import (", text,
                          f"{rel}: the reader does not import from the owner module")
            self.assertIn(OWNER_NAME, text,
                          f"{rel}: the reader does not import {OWNER_NAME}")
            reads = [number for number, line in enumerate(text.splitlines(), start=1)
                     if f"ID[{OWNER_NAME}]" in line]
            self.assertEqual(len(reads), 1,
                             f"{rel}: the reader reads ID[{OWNER_NAME}] at {len(reads)} sites, not 1")
            self.assertEqual(walk_offenders([(rel, text)]), [],
                             f"{rel}: the reader spells the name as a literal")

    def test_the_three_sites_name_the_same_text(self):
        owner_value_text = owner_value(read_text(OWNER))
        for rel in READERS:
            self.assertIn(f"ID[{OWNER_NAME}]", read_text(rel),
                          f"{rel}: the reader does not read the key through the home name")
        self.assertEqual(owner_value_text, NAME,
                         "the writer and the two readers no longer agree on the key")

    def test_the_walk_over_the_tracked_trees_answers_no_copy(self):
        offenders = walk_offenders(tracked_pairs())
        self.assertEqual(offenders, [],
                         "the walk found a quoted spelling outside the home:\n"
                         + "\n".join(offenders))

    def test_the_walk_is_honest(self):
        planted = read_text(READERS[0]).replace(f"ID[{OWNER_NAME}]", f'ID["{NAME}"]')
        offenders = walk_offenders([(READERS[0], planted)])
        self.assertEqual(len(offenders), 1,
                         f"the walk missed a planted copy in {READERS[0]}: {offenders}")
        self.assertTrue(offenders[0].startswith(f"{READERS[0]}:"),
                        f"the walk names no line: {offenders[0]}")
        self.assertIn(NAME, offenders[0], f"the walk names no text: {offenders[0]}")
        moved = read_text(OWNER).replace(f'{OWNER_NAME} = "{NAME}"',
                                         f'{OWNER_NAME} = "{NAME}_x"')
        self.assertNotEqual(owner_value(moved), NAME,
                            "the value pin follows a moved home value")


if __name__ == "__main__":
    unittest.main()
