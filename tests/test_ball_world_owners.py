"""The ball world and its demo read three facts from their owners.

Round 128 walked the tree after the ball-permanence round and found three facts that
``src/ball_world.py`` and ``tools/ball_world_demo.py`` spelled by hand:

1. The colour name of an unread ball, ``"unknown"``.  The census already held it
   (``src/ball_census.py``), but nothing else read it, and the world and the demo
   wrote it on seven lines.  A missed site turns the old word into a colour of no
   group, and a settled slot then refuses every match without an error.
   ``src/color_names.py`` now owns ``UNKNOWN``; the census, the world and the demo
   read it there.
2. The table plane.  The world built its six pockets by hand, and the demo typed
   ``"2540x1270"`` and built its own millimetre rectangle.  That rectangle put the
   1270 mm head rail on x = 2540 mm, so the side pockets fell on the short rails.
   ``src/table_geometry.py`` owns the frame (``CANON_W``, ``CANON_H``,
   ``canonical_destination``) and the pocket table (``POCKETS_MM``); the world and
   the demo read them.
3. The person weight.  The demo defaulted to the bare file name ``"yolov8n.pt"``
   instead of ``weight_pins.YOLO``, so a moved pin would load an unpinned file.

The existing owner walks read ``src/`` only, so a tool could spell any of these facts
again in silence.  This guard reads the world, the demo, and every other tracked
Python file under ``tools/``.  A floor keeps a walk that read nothing from passing.

Run: ``./scripts/pool-test.sh python test_ball_world_owners``
"""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import color_names, table_geometry, weight_pins  # noqa: E402

WORLD = "src/ball_world.py"
DEMO = "tools/ball_world_demo.py"
#: The census readers that compare a colour with the unread word (round 129).
CENSUS_READERS = ("src/eval_events.py", "src/motion_scan.py", "src/ball_census.py")
#: The bare file name of the pinned person weight.
YOLO_NAME = Path(weight_pins.YOLO).name


def tracked(pattern):
    out = subprocess.run(["git", "ls-files", pattern], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line.endswith(".py")]


def code_constants(rel):
    """Every str and number constant of a file, minus the docstrings, with its line."""
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and id(node) not in docstrings]


class TheBallWorldReadsItsOwnersTests(unittest.TestCase):

    def files(self):
        files = sorted(set([WORLD, DEMO] + tracked("tools/*.py") + list(CENSUS_READERS)))
        self.assertGreaterEqual(len(files), 9, "the walk read the world, the demo, the tools and the census readers")
        return files

    def test_no_file_spells_the_unread_colour(self):
        self.assertEqual(color_names.UNKNOWN, "unknown")
        found = [f"{rel}:{line}" for rel in self.files() for line, value in code_constants(rel)
                 if value == color_names.UNKNOWN and rel != "tools/playfield_vod_audit.py"]
        self.assertEqual(found, [], "these sites spell the unread colour; read src.color_names.UNKNOWN")

    def test_the_census_reads_the_same_word(self):
        from src import ball_census
        from src import ball_world
        self.assertIs(ball_census.UNKNOWN, color_names.UNKNOWN)
        self.assertIs(ball_world.UNKNOWN, color_names.UNKNOWN)
        self.assertEqual([f"{line}" for line, value in code_constants("src/ball_census.py")
                          if value == color_names.UNKNOWN], [], "the census reads the word, it does not spell it")

    def test_no_file_spells_the_table_size(self):
        sides = (table_geometry.CANON_W, table_geometry.CANON_H)
        sizes = {*sides, *(float(side) for side in sides)}
        found = [f"{rel}:{line} {value!r}" for rel in self.files() for line, value in code_constants(rel)
                 if (isinstance(value, (int, float)) and not isinstance(value, bool) and value in sizes)
                 or (isinstance(value, str) and any(f"{a}x{b}" in value for a in sides for b in sides))]
        self.assertEqual(found, [], "these sites spell the table size; read src.table_geometry")

    def test_the_world_reads_the_owner_frame_and_pockets(self):
        from src.ball_world import Table
        table = Table()
        self.assertEqual((table.width_mm, table.height_mm),
                         (float(table_geometry.CANON_W), float(table_geometry.CANON_H)))
        self.assertEqual(table.pockets, tuple(table_geometry.POCKETS_MM.values()))
        source = (ROOT / DEMO).read_text(encoding="utf-8")
        self.assertIn("table_geometry.canonical_destination()", source,
                      "the demo maps the cloth quad with the owner's destination")

    def test_no_file_spells_the_person_weight(self):
        found = [f"{rel}:{line}" for rel in self.files() for line, value in code_constants(rel)
                 if isinstance(value, str) and Path(value).name == YOLO_NAME]
        self.assertEqual(found, [], "these sites spell the person weight; read src.weight_pins.YOLO")
        self.assertIn("default=weight_pins.YOLO", (ROOT / DEMO).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
