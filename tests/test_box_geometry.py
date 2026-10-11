"""One home for the intersection over union of two boxes.

Four modules of src/ defined this rule themselves, in two spellings that compute
the same number: ``src/enroll_from_tracklet.py`` and ``src/eval_faces.py`` wrote
one, ``src/pid_osnet_tight.py`` and ``src/yolo_track.py`` wrote the other.  A
change to one copy changed the behaviour of one tracker only, and nothing told a
reader that the other three copies existed.

``src/box_geometry.py`` owns the rule now, and the four modules import it.  Three
cases hold that home:

1. the owner answers the documented numbers.  Each number below is written as a
   literal and comes from the rule itself: overlap area divided by the sum of the
   two areas less the overlap, and 0.0 when the union is not positive.  The case
   also computes each pair from the two areas and the intersection, so the
   literals are checked against the rule and not only against the owner.
2. the two old spellings agree with the owner.  The case calls the owner and both
   spellings, copied here as local functions, over a table of box pairs, and
   requires one answer.  Every number is an exact float of the same arithmetic,
   so equality and not ``assertAlmostEqual`` is the right test.
3. one owner.  The scan reads the source with ``ast`` and never imports a module,
   because two of the four readers open a checkpoint or a model at import time.
   It looks at the module-level function definitions of ``src/*.py`` only, and at
   the owner import the four readers carry.

``src/sam3/`` is out of scope: it is the vendored upstream checkout, not our
code, and it carries its own ``iou_tracklets``, ``iou_masklets`` and ``iou_loss``.

Run: ``./scripts/pool-test.sh python test_box_geometry``
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import box_geometry  # noqa: E402

SRC = ROOT / 'src'
VENDORED = SRC / 'sam3'
RULE_NAME = 'iou'
# The four modules that used to define the rule, and the import that replaces the
# local definition in each one.
READERS = ('enroll_from_tracklet.py', 'eval_faces.py', 'pid_osnet_tight.py', 'yolo_track.py')
OWNER_MODULE = 'src.box_geometry'

# The two spellings of the rule, copied from HEAD 71adf6e.  The first is the text
# ``src/enroll_from_tracklet.py`` and ``src/eval_faces.py`` held at that commit,
# and the second is the text ``src/pid_osnet_tight.py`` and ``src/yolo_track.py``
# held there.  Spelling 1 clips the intersection width and height at 0.0,
# spelling 2 clips the two intersection coordinates at 0.  The answers are the
# same on every input, which is the case below.
SPELLING_1 = '''
def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
'''
SPELLING_2 = '''
def iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0
'''

# The numbers the owner must answer.  A name is the kind of pair; the number is
# the rule applied to it by hand.
DOCUMENTED = (
    ('the same box', (0, 0, 10, 10), (0, 0, 10, 10), 1.0),
    ('an overlap of a quarter of each box', (0, 0, 10, 10), (5, 5, 15, 15), 25.0 / 175.0),
    ('boxes that overlap in x only', (0, 0, 10, 10), (5, 20, 15, 30), 0.0),
    ('a contained box', (0, 0, 10, 10), (2, 2, 4, 4), 4.0 / 100.0),
    ('a contained box of half the width', (0, 0, 40, 60), (10, 20, 30, 40), 4.0 / 24.0),
    ('a pair that touches on an edge, width only', (0, 0, 10, 10), (10, 0, 20, 10), 0.0),
    ('a pair that touches on an edge, height only', (0, 0, 10, 10), (0, 10, 10, 20), 0.0),
    ('a pair that touches at one corner', (0, 0, 10, 10), (10, 10, 20, 20), 0.0),
    ('a disjoint pair, apart in x and in y', (0, 0, 10, 10), (50, 50, 60, 60), 0.0),
    ('a disjoint pair, apart in y only', (20, 60, 40, 90), (30, 0, 60, 30), 0.0),
    ('an overlap that is not symmetric in y', (0, 0, 10, 10), (5, 5, 15, 12), 25.0 / 145.0),
    ('a box of zero width', (10, 10, 10, 20), (0, 0, 20, 20), 0.0),
    ('a box of zero height', (10, 10, 20, 10), (0, 0, 20, 20), 0.0),
    ('two boxes of zero area', (0, 0, 0, 0), (5, 5, 5, 5), 0.0),
    ('negative coordinates', (-10, -10, 0, 0), (-5, -5, 5, 5), 25.0 / 175.0),
)

# The table the two spellings and the owner must agree on.  It holds the
# documented pairs and pairs that exercise the two clips of each spelling.
AGREEMENT_TABLE = DOCUMENTED + (
    ('one box inside the other, same corner', (0, 0, 10, 10), (0, 0, 4, 4), 16.0 / 100.0),
    ('a box that overlaps across the whole width', (0, 0, 10, 10), (2, 2, 8, 40), 48.0 / 100.0),
    ('a tall thin box and a wide flat box', (0, 0, 2, 20), (0, 8, 20, 12), 8.0 / 108.0),
    ('boxes that share one edge and overlap in the other axis', (0, 0, 10, 10), (10, 5, 20, 15), 0.0),
    ('floats', (0.5, 0.5, 2.5, 2.5), (1.5, 1.5, 3.5, 3.5), 1.0 / 7.0),
    ('an overlap of one pixel', (0, 0, 10, 10), (9, 9, 20, 20), 1.0 / 199.0),
)


def spelling_1(a, b):
    """The rule as ``src/enroll_from_tracklet.py`` and ``src/eval_faces.py`` wrote it."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def spelling_2(a, b):
    """The rule as ``src/pid_osnet_tight.py`` and ``src/yolo_track.py`` wrote it."""
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def legacy_spelling(source):
    """The ``iou`` one source text defines, as a callable."""
    namespace = {}
    exec(compile(ast.parse(source), '<spelling>', 'exec'), namespace)
    return namespace[RULE_NAME]


def spelled_iou_definitions(path):
    """The line numbers of the module-level functions named ``iou`` in one module.

    The walk reads the module body only.  A nested ``def iou`` or a local name
    ``iou`` inside a function is a local helper and not a second owner of the
    rule, so it does not count here.
    """
    tree = ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))
    return [node.lineno for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == RULE_NAME]


def owner_binding(path):
    """The names one module imports from ``src.box_geometry`` at module level.

    The walk reads the import and never runs the module: ``src/pid_osnet_tight.py``
    opens a checkpoint and ``src/yolo_track.py`` loads a model at import time, so a
    reader case that imported them would cost a model load.
    """
    tree = ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == OWNER_MODULE:
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def documented_rule(a, b):
    """The documented number of one pair, computed from the two areas and the overlap."""
    inter = (max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
             * max(0.0, min(a[3], b[3]) - max(a[1], b[1])))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class BoxGeometryTest(unittest.TestCase):
    """The owner, its two old spellings, and the walk that proves it is alone."""

    def test_the_owner_answers_the_documented_numbers(self):
        """Every kind of pair answers the number the rule gives it."""
        for name, a, b, expected in DOCUMENTED:
            with self.subTest(pair=name):
                self.assertEqual(expected, box_geometry.iou(a, b),
                                 '%s: %r against %r' % (name, a, b))

    def test_each_documented_number_is_the_rule_applied_to_the_pair(self):
        """The literals come from the rule, not from a recorded run of the owner."""
        for name, a, b, expected in DOCUMENTED:
            with self.subTest(pair=name):
                self.assertEqual(expected, documented_rule(a, b),
                                 '%s: the literal is not the rule applied by hand' % name)

    def test_the_pair_of_boxes_does_not_change_the_answer(self):
        """The rule reads both boxes alike, so no call site can depend on the order."""
        for name, a, b, expected in DOCUMENTED:
            with self.subTest(pair=name):
                self.assertEqual(expected, box_geometry.iou(b, a),
                                 '%s: the answer changed when the two boxes swapped' % name)

    def test_the_two_spellings_agree_with_the_owner(self):
        """Spelling 1, spelling 2 and the owner answer one number for every pair."""
        first, second = legacy_spelling(SPELLING_1), legacy_spelling(SPELLING_2)
        for name, a, b, _ in AGREEMENT_TABLE:
            with self.subTest(pair=name):
                owner = box_geometry.iou(a, b)
                self.assertEqual(owner, first(a, b),
                                 '%s: spelling 1 differs from the owner' % name)
                self.assertEqual(owner, second(a, b),
                                 '%s: spelling 2 differs from the owner' % name)

    def test_the_four_readers_import_the_owner_function(self):
        """A reader reads the rule from the owner, so the copies cannot come back."""
        for name in READERS:
            with self.subTest(reader=name):
                self.assertIn(RULE_NAME, owner_binding(SRC / name),
                              'src/%s does not import iou from %s' % (name, OWNER_MODULE))

    def test_no_other_module_under_src_defines_iou(self):
        """One owner: only src/box_geometry.py defines the module-level rule."""
        modules = sorted(SRC.glob('*.py'))
        self.assertGreater(len(modules), 60,
                           'the walk reached %d modules of src/, too few to prove the home'
                           % len(modules))
        self.assertNotIn(VENDORED, modules, 'the vendored tree is not our module')
        found = [path.name for path in modules if spelled_iou_definitions(path)]
        self.assertEqual(['box_geometry.py'], found,
                         'these modules of src/ define their own iou: %s' % ', '.join(found))
