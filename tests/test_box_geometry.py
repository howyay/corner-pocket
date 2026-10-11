"""One home for the intersection over union of two boxes.

Four modules of src/ defined this rule themselves, in two spellings that compute
the same number: ``src/enroll_from_tracklet.py`` and ``src/eval_faces.py`` wrote
one, ``src/pid_osnet_tight.py`` and ``src/yolo_track.py`` wrote the other.  A
change to one copy changed the behaviour of one tracker only, and nothing told a
reader that the other three copies existed.

``src/box_geometry.py`` owns the rule now, and six modules import it: the four
readers above, ``src/person_pipeline.py`` (its own ``_iou`` held the same five
statements) and ``src/recut_crops.py`` (it wrote the arithmetic inline in a loop).
Four cases hold that home:

1. the owner answers the documented numbers.  Each number below is written as a
   literal and comes from the rule itself: overlap area divided by the sum of the
   two areas less the overlap, and 0.0 when the union is not positive.  The case
   also computes each pair from the two areas and the intersection, so the
   literals are checked against the rule and not only against the owner.
2. the two old spellings agree with the owner.  The case calls the owner and both
   spellings, copied here as local functions, over a table of box pairs, and
   requires one answer.  Every number is an exact float of the same arithmetic,
   so equality and not ``assertAlmostEqual`` is the right test.
3. one name.  The scan reads the source with ``ast`` and never imports a module,
   because two of the four readers open a checkpoint or a model at import time.
   It looks at the module-level function definitions of ``src/*.py`` only, and at
   the owner import the six readers carry.
4. one body, whatever the name is.  A second module-level function whose body
   equals the owner's body fails the walk, because the name rule of case 3 cannot
   see a copy under another name: ``src/person_pipeline.py`` held the same five
   statements under ``_iou``, and ``src/recut_crops.py`` wrote them inline in a
   loop with a local name ``iou``.  The walk compares syntax trees and not text.
   The recorded near miss is ``src/enroll_from_tracklet.py:156 face_area_iou``:
   its name ends in ``iou`` and it clips the same two coordinates, but its last
   statement divides the intersection by the face area alone, so it has no union
   term, its body hash differs, and the rule must not flag it.

Every shared body of ``src/`` is held the same way, for every helper and not only
for this rule, in ``tests/test_duplicate_bodies.py``.

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

# The body fingerprint has one home, tests/_shipped.py.
from _shipped import body_fingerprint  # noqa: E402

from src import box_geometry  # noqa: E402

SRC = ROOT / 'src'
VENDORED = SRC / 'sam3'
RULE_NAME = 'iou'
# The modules that used to write the rule themselves, in a local definition or in
# inline arithmetic, and the import that replaces each one.
READERS = ('enroll_from_tracklet.py', 'eval_faces.py', 'pid_osnet_tight.py', 'yolo_track.py',
           'person_pipeline.py', 'recut_crops.py')
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


def module_level_functions(path):
    """The module-level functions of one module, as (name, line, body fingerprint).

    A nested ``def`` or a method of a class is a local helper and not a second
    owner of a shared rule, so it does not count here.
    """
    tree = ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))
    return [(node.name, node.lineno, body_fingerprint(node))
            for node in tree.body if isinstance(node, ast.FunctionDef)]


def owner_body():
    """The line and the body fingerprint of the owner function, read from its source."""
    for name, line, digest in module_level_functions(SRC / 'box_geometry.py'):
        if name == RULE_NAME:
            return line, digest
    raise AssertionError('src/box_geometry.py does not define %s' % RULE_NAME)


def bound_rule_names(path):
    """The lines of one module that bind the bare name ``iou`` to a local value.

    A parameter, an assignment and a loop target all shadow the owner inside the
    function that holds them.  The owner import binds the name in the module
    namespace and so is not a local value; it does not count here.
    """
    tree = ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
                and node.id == RULE_NAME):
            lines.append(node.lineno)
        elif isinstance(node, ast.arg) and node.arg == RULE_NAME:
            lines.append(node.lineno)
    return sorted(lines)


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

    def test_every_reader_imports_the_owner_function(self):
        """A reader reads the rule from the owner, so the copies cannot come back."""
        for name in READERS:
            with self.subTest(reader=name):
                self.assertIn(RULE_NAME, owner_binding(SRC / name),
                              'src/%s does not import iou from %s' % (name, OWNER_MODULE))

    def test_no_other_module_under_src_holds_the_owners_body(self):
        """One body: a copy of the rule cannot hide under another name.

        The walk reads every module of ``src/`` and compares the body fingerprint
        of each module-level function with the owner's.  Only the owner may hold
        that body, whatever the name of the function is.  ``_iou`` of
        ``src/person_pipeline.py`` was found by this rule and by no other.
        """
        _, digest = owner_body()
        holders = [path.name for path in sorted(SRC.glob('*.py'))
                   if any(other == digest for _, _, other in module_level_functions(path))]
        self.assertEqual(['box_geometry.py'], holders,
                         'these modules of src/ hold the body of the owner %s: %s'
                         % (RULE_NAME, ', '.join(holders)))

    def test_the_recorded_near_miss_is_present_and_its_body_differs(self):
        """The trap of the body rule: a name that ends in ``iou``, a different body.

        ``src/enroll_from_tracklet.py:156 face_area_iou`` clips the same two
        coordinates and then divides the intersection by the face area alone, with
        no union term.  It must stay out of the walk above, so this case pins the
        two facts that make it a near miss and not a second owner: the function is
        present, and its body is not the owner's body.
        """
        _, digest = owner_body()
        trap = [item for item in module_level_functions(SRC / 'enroll_from_tracklet.py')
                if item[0] == 'face_area_iou']
        self.assertEqual(1, len(trap),
                         'the recorded near miss face_area_iou is gone from '
                         'src/enroll_from_tracklet.py; update this case and the module docstring')
        self.assertNotEqual(digest, trap[0][2],
                            'src/enroll_from_tracklet.py:%d face_area_iou now holds the body of '
                            'the owner, so it is a second owner and not a near miss' % trap[0][1])

    def test_no_module_binds_the_rule_name_to_a_local_value(self):
        """The rule name stays free: a local ``iou`` shadows the owner it reads.

        ``src/recut_crops.py`` wrote the arithmetic inline and bound the name
        ``iou`` to it, and ``src/person_pipeline.py`` unpacked a score into a loop
        target ``iou``.  Both sites are gone; this case keeps the name free.
        """
        offenders = ['%s:%d' % (path.name, line)
                     for path in sorted(SRC.glob('*.py')) for line in bound_rule_names(path)]
        self.assertEqual([], offenders,
                         'these sites bind a local %s, so they shadow the owner: %s'
                         % (RULE_NAME, ', '.join(offenders)))

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
