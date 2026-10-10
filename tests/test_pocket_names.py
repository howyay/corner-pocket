"""The pocket name a text states has one owner.

A stored ``nearest_pocket`` value spells a pocket in one of four shapes. Measured
over 774 rows under ``out/``: 735 bare names, 28 with a parenthesis, 4 in the
``mm from`` form and 7 with no value.

Two modules used to answer this question with a rule each. The gate of
src/event_gates.py accepted a bare name. The console backend of
annotator/unified_server.py accepted only the other two spellings, so for the
shape that 735 of the 774 rows use it answered the geometrically nearest pocket,
a name the document does not hold. The rule now lives in src/pocket_names.py.
"""
from __future__ import annotations

import math
import pathlib
import unittest

from annotator.unified_server import Backend
from src.event_gates import normalize
from src.pocket_names import pocket_from_text
from src.table_geometry import POCKETS_MM

ROOT = pathlib.Path(__file__).resolve().parents[1]
# The scan walks the tree, because the owner of a rule is a file on disk and not
# a tracked path: a new file is untracked until its commit lands.
SKIP_DIRS = {".git", ".venv", "node_modules", "out", "data", ".pm"}
NEEDLES = ('split("(")[0]', "split('(')[0]", 'rsplit(" from ", 1)', "rsplit(' from ', 1)")

# The six pockets of src/table_geometry.py, with the count of stored rows each
# bare spelling holds under out/ (220 + 206 + 147 + 102 + 40 + 20 = 735).
BARE_NAMES = {
    "right-side": 220,
    "left-side": 206,
    "head-right": 147,
    "head-left": 102,
    "foot-right": 40,
    "foot-left": 20,
}
# Three of the 28 parenthesised rows; the rest carry the same shape.
PARENTHESIS = {
    "left-side (148 ± 54mm)": "left-side",
    "left-side (84 ± 31mm)": "left-side",
    "right-side (148 ± 54mm)": "right-side",
}
# The two measured rows of the 4 in this shape, and the spelling the console
# backend accepted before this change.
FROM_FORM = {
    "574mm from foot-right": "foot-right",
    "557mm from foot-right": "foot-right",
    "148 mm from right-side": "right-side",
}
NO_VALUE_ROWS = 7
STORED_ROWS = sum(BARE_NAMES.values()) + 28 + 4 + NO_VALUE_ROWS


def spellings():
    """Every (text, name) pair the four measured shapes cover."""
    pairs = [(text, text) for text in BARE_NAMES]
    pairs += list(PARENTHESIS.items()) + list(FROM_FORM.items())
    return pairs


def python_files():
    # This file is skipped: it holds the needles as data, so a scan of itself
    # would report the two spellings it looks for.
    mine = pathlib.Path(__file__).resolve()
    for path in sorted(ROOT.rglob("*.py")):
        if path.resolve() == mine or any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


class SpellingTests(unittest.TestCase):
    def test_every_shape_a_stored_row_uses_answers_its_name(self):
        self.assertEqual(STORED_ROWS, 774, "the census of the stored rows")
        self.assertEqual(sum(BARE_NAMES.values()), 735, "the bare names are the common shape")
        self.assertEqual(len(spellings()), 12, "the spellings this case checks")
        for text, want in spellings():
            self.assertEqual(pocket_from_text(text), want, f"{text!r} names {want!r}")

    def test_every_answer_is_one_of_the_six_pockets(self):
        for text, _ in spellings():
            self.assertIn(pocket_from_text(text), POCKETS_MM, f"{text!r}")


class RefusalTests(unittest.TestCase):
    def test_text_that_names_no_pocket_answers_none(self):
        for value in (None, "", "   ", "None", "nowhere", "left side", "right-side pocket",
                      "5", 5, [], {}):
            self.assertIsNone(pocket_from_text(value), f"{value!r} names no pocket")


class OwnerTests(unittest.TestCase):
    def test_the_parse_of_a_pocket_text_lives_in_one_file(self):
        hits = []
        for path in python_files():
            text = path.read_text()
            for needle in NEEDLES:
                if needle in text:
                    hits.append((str(path.relative_to(ROOT)), needle))
        files = sorted({name for name, _ in hits})
        self.assertEqual(files, ["src/pocket_names.py"],
                         "the rule that reads a pocket name out of a text belongs to "
                         "src/pocket_names.py alone:")
        self.assertEqual(len(hits), 2, "both spellings of the rule, and no third")

    def test_both_readers_ask_the_owner(self):
        gate = (ROOT / "src/event_gates.py").read_text()
        console = (ROOT / "annotator/unified_server.py").read_text()
        for rel, text in (("src/event_gates.py", gate), ("annotator/unified_server.py", console)):
            self.assertIn("from src.pocket_names import pocket_from_text", text,
                          f"{rel} must ask the one owner")
        self.assertNotIn("_pocket_name", gate, "the gate keeps no rule of its own")
        self.assertIn("pocket_from_text(event.get('nearest_pocket'))", console,
                      "the console asks the owner first, then falls back to the table")


class SeamTests(unittest.TestCase):
    """The gate and the console answer the same name for the same stored row."""

    def test_the_two_readers_agree_on_every_spelling(self):
        for text, want in spellings():
            event = {"nearest_pocket": text}
            gate = normalize(event)["pocket"]
            console = Backend._pocket_name(event)
            self.assertEqual(gate, want, f"the gate reads {text!r}")
            self.assertEqual(console, gate,
                             f"the console reads {text!r} as {gate!r}, and answered the nearest "
                             f"pocket before this rule had one owner")

    def test_the_two_readers_agree_on_text_that_names_nothing(self):
        for value in (None, "", "None", "nowhere"):
            event = {"nearest_pocket": value}
            self.assertIsNone(normalize(event)["pocket"], f"the gate reads {value!r}")
            self.assertIsNone(Backend._pocket_name(event), f"the console reads {value!r}")


class FallbackTests(unittest.TestCase):
    """The table answers only when the text names no pocket."""

    def nearest(self, point):
        return min(POCKETS_MM, key=lambda name: math.hypot(point[0] - POCKETS_MM[name][0],
                                                           point[1] - POCKETS_MM[name][1]))

    def test_the_table_answers_when_the_text_names_no_pocket(self):
        event = {"nearest_pocket": "nowhere", "last_mm": [20.0, 20.0]}
        self.assertEqual(Backend._pocket_name(event), "head-left")
        self.assertEqual(self.nearest([20.0, 20.0]), "head-left")
        self.assertIsNone(Backend._pocket_name({"nearest_pocket": "nowhere"}))

    def test_the_name_the_row_holds_wins_over_the_nearest_pocket(self):
        # A measured row: the field says right-side, the ball sits near the head-left
        # corner. The console answered head-left before this rule had one owner.
        event = {"nearest_pocket": "right-side", "last_mm": [20.0, 20.0]}
        self.assertEqual(self.nearest(event["last_mm"]), "head-left")
        self.assertEqual(normalize(event)["pocket"], "right-side")
        self.assertEqual(Backend._pocket_name(event), "right-side")


if __name__ == "__main__":
    unittest.main()
