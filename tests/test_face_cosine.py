"""One home for the face cosine: ``src/face_id.py _cosine``.

Round 58 met the first defect.  Two modules held this body: ``src/face_id.py
_cosine`` and ``src/eval_faces.py _cos``.  Their statements were the same, except
for one spelling: the zero-length test wrote ``0.0`` in the first module and ``0``
in the second.  The walk of ``tests/test_duplicate_bodies.py`` hashes the text of
a body, so the two digests came out apart and that walk reported nothing.
Round 58 gave the rule one home in ``src/face_id.py``, and ``src/eval_faces.py``
reads it as ``_cos``.

Round 90 met the second defect.  Two more bodies stood in the tree, and the walk
of this module could not see either one, because it read ``SRC.glob('*.py')``
alone and held a single body shape:

* ``src/enroll_from_tracklet.py`` held a second body in a ternary until
  round 90 removed it.  Its
  guard was ``if na > 0 and nb > 0``, and on a pair that carries NaN it answered
  ``0.0`` where the owner answers ``nan``.  Two answers for one pair is the
  defect this module exists to refuse.
* ``tests/live_identity_validation.py:138 cosine`` carried the body of the owner
  again, in a second file that the ``src/`` walk never opened.

This module holds one check for each way the rule can leave its home:

* the owner, the reader ``_cos`` and the two readers ``cosine`` answer the same
  value for a fixed corpus of vector pairs, NaN pin included;
* the owner holds the body with its four properties;
* ``src/eval_faces.py`` imports the one name and holds no second body;
* one walk of ``src/*.py``, ``tests/*.py`` and ``annotator/*.py`` finds one site
  of the body, and that walk writes every number in one shape, so a copy with
  another zero spelling is seen;
* every module of the tree that binds a cosine name binds the owner object, and
  no module outside the owner writes the body;
* a copy planted in a temporary module makes the walk red, and the same walk
  answers red for the same copy loaded as a live function.

The last check is the general one, and it is the reason the walk covers three
directories: a fourth body may take any name, so a name check cannot hold the
rule.  Only the body itself can.

Run: ``./scripts/pool-test.sh python test_face_cosine``
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import eval_faces, face_id  # noqa: E402  (after the path fix above)
from src.enroll_from_tracklet import cosine as enroll_cosine  # noqa: E402

SRC = ROOT / 'src'
OWNER = SRC / 'face_id.py'
OWNER_NAME = '_cosine'
READER = SRC / 'eval_faces.py'
READER_NAME = '_cos'
OWNER_MODULE = 'src.face_id'

#: The directories the walk covers.  Round 90 added the last two: the body stood
#: in ``tests/live_identity_validation.py`` and the old walk never opened it.
WALK_ROOTS = ('src', 'tests', 'annotator')

#: The two readers of the rule outside the owner: module, bound name, live object.
READERS = (
    ('src/eval_faces.py', '_cos', eval_faces._cos),
    ('src/enroll_from_tracklet.py', 'cosine', enroll_cosine),
)

#: The rule of the one body, as text, straight from the round-58 brief.
FLAT_VIEW = ('np.asarray(a, np.float32).ravel()', 'np.asarray(b, np.float32).ravel()')
FLOAT_RESULT = 'return float(np.dot(a, b) / (na * nb))'
ZERO_ANSWER = 'return 0.0'

#: (name, a, b, expected).  ``expected`` is the answer every reader must give.
#: The corpus holds a normal pair, a pair of unit vectors, a zero vector on each
#: side, a negative pair, a pair of integer lists, a pair of nested lists, the
#: nan row the owner decides, and a pair of float32 arrays.
CORPUS = (
    ('a normal pair', [0.3, 0.4, 0.5], [0.5, -0.1, 0.2], 0.5422176684690383),
    ('a pair of unit vectors', [1.0, 0.0, 0.0], [0.6, 0.8, 0.0], 0.6),
    ('a zero vector on the left', [0.0, 0.0, 0.0], [0.5, -0.1, 0.2], 0.0),
    ('a zero vector on the right', [0.5, -0.1, 0.2], [0.0, 0.0, 0.0], 0.0),
    ('a zero-length list on the left', [], [0.5, -0.1, 0.2], 0.0),
    ('a zero-length list on the right', [0.5, -0.1, 0.2], [], 0.0),
    ('a negative pair', [-1.0, -2.0, -3.0], [1.0, 2.0, 3.0], -1.0),
    ('a pair of integer lists', [1, 2, 3], [3, 2, 1], 0.7142857142857143),
    ('a pair of nested lists', [[1.0, 2.0], [3.0, 4.0]], [[0.5, 0.5], [0.25, 0.75]],
     0.903696114115064),
    ('a nan on the left', [float('nan'), 1.0], [1.0, 1.0], float('nan')),
    ('a nan on the right', [1.0, 1.0], [float('nan'), 1.0], float('nan')),
    ('a pair of float32 arrays', np.array([1.0, 2.0, 3.0], np.float32),
     np.array([3.0, 2.0, 1.0], np.float32), 0.7142857142857143),
)

#: The names of the rule in the tree: the owner name, the name
#: ``src/eval_faces.py`` reads, and the name the two modules of round 90 read.
RULE_NAMES = ('_cosine', '_cos', 'cosine')

#: The corpus rows without a NaN answer, for a copy the walk must report.
FINITE_CORPUS = tuple(row for row in CORPUS if not math.isnan(row[3]))

#: A copy of the body with the other zero spelling.  The walk must report it.
PLANTED_COPY = '''"""A copy of the face cosine, written by tests/test_face_cosine.py."""
import numpy as np


def planted_cosine(a, b):
    a = np.asarray(a, np.float32).ravel()
    b = np.asarray(b, np.float32).ravel()
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na <= 0 or nb <= 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
'''

#: A copy with the guard of the deleted ``src/enroll_from_tracklet.py`` body: its
#: statements are other statements, so only a run of the rule sees the difference.
PLANTED_TERNARY = '''"""A copy of the face cosine with the deleted ternary guard."""
import numpy as np


def planted_cosine(a, b):
    a = np.asarray(a, np.float32).ravel()
    b = np.asarray(b, np.float32).ravel()
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0
'''


class WholeNumbers(ast.NodeTransformer):
    """Write every number of one body in one shape.

    The copies of the face cosine differed by the spelling ``0`` against ``0.0``
    alone.  The walk must see a copy of that body whatever zero it writes, so the
    hash below reads the numbers in one shape.
    """

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            try:
                node.value = float(node.value)
            except OverflowError:
                pass
        return node


def statements_of(node):
    """The statements of one function, without its docstring."""
    body = list(node.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return body


def body_text(node):
    """The normalized statements of one function, as text."""
    module = ast.Module(body=statements_of(node), type_ignores=[])
    module = ast.fix_missing_locations(WholeNumbers().visit(module))
    return ast.unparse(module)


def body_shape(node):
    """The sha1 of the normalized statements of one function."""
    return hashlib.sha1(body_text(node).encode('utf-8')).hexdigest()


def module_tree(path):
    """The tree of one module file."""
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def module_functions(path):
    """(line, name, body_node) of every module-level function of one file."""
    return [(node.lineno, node.name, node) for node in module_tree(path).body
            if isinstance(node, ast.FunctionDef)]


def module_function_names(path):
    """The names of the module-level functions of one file."""
    return [name for _, name, _ in module_functions(path)]


def walked_files(roots=WALK_ROOTS):
    """Every python file of the named roots, in a stable order."""
    found = []
    for root in roots:
        base = ROOT / root
        if base.is_dir():
            found += sorted(path for path in base.rglob('*.py')
                            if '__pycache__' not in path.parts)
    return found


def shape_sites(shape, roots=WALK_ROOTS):
    """(module, line, name) of every site of one body shape in the named roots."""
    return [(relative(path), line, name)
            for path in walked_files(roots)
            for line, name, node in module_functions(path) if body_shape(node) == shape]


def relative(path):
    """One path under the repository root, as a posix string."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()


def owner_function():
    """The one function of the owner, or None when the owner lost it."""
    return next((node for _, name, node in module_functions(OWNER) if name == OWNER_NAME), None)


def imported_from(path, module_name):
    """{bound name: imported name} for the imports of one file from one module."""
    found = {}
    for node in ast.walk(module_tree(path)):
        if isinstance(node, ast.ImportFrom) and node.module == module_name:
            for alias in node.names:
                found[alias.asname or alias.name] = alias.name
    return found


def cosine_bindings():
    """(module, line, bound name, imported name) of every binding of a cosine name.

    A binding is one of two shapes, and both shapes keep the rule out of a second
    body: ``from src.face_id import _cosine as <name>`` binds the object, and
    ``from src import face_id`` binds the module that holds it.
    """
    found = []
    for path in walked_files():
        for node in ast.walk(module_tree(path)):
            if isinstance(node, ast.ImportFrom) and node.module == OWNER_MODULE:
                for alias in node.names:
                    if alias.name in RULE_NAMES:
                        found.append((relative(path), node.lineno,
                                      alias.asname or alias.name, alias.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == OWNER_MODULE:
                        found.append((relative(path), node.lineno,
                                      alias.asname or alias.name, alias.name))
    return found


def owner_attribute_reads():
    """(module, line, name) of every read of ``<name>._cosine`` of the tree."""
    found = []
    for path in walked_files():
        for node in ast.walk(module_tree(path)):
            if (isinstance(node, ast.Attribute) and node.attr == OWNER_NAME
                    and isinstance(node.value, ast.Name)):
                found.append((relative(path), node.lineno, node.value.id))
    return found


def module_aliases(path):
    """The names one file binds to the owner module with an ``import`` statement.

    ``import src.face_id`` binds ``src.face_id`` itself, and ``from src import
    face_id`` binds the last name alone; both spellings put the object one
    attribute away, so both count.
    """
    short = OWNER_MODULE.rsplit('.', 1)[-1]
    found = set()
    for node in ast.walk(module_tree(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == OWNER_MODULE:
                    found.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == OWNER_MODULE.rsplit('.', 1)[0]:
            for alias in node.names:
                if alias.name == short:
                    found.add(alias.asname or alias.name)
    return found


def site_listing(sites):
    """The sites of one body, as ``module:line name``."""
    return ', '.join('%s:%d %s' % site for site in sites) or 'nowhere'


def same_number(one, other):
    """True when two answers are the same number, NaN included."""
    try:
        return bool(one == other) or (math.isnan(one) and math.isnan(other))
    except TypeError:
        return False


def load_planted(source, directory):
    """Load ``source`` as a module of ``directory`` and return its one function."""
    path = Path(directory) / 'planted_cosine_copy.py'
    path.write_text(source, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('planted_cosine_copy_%d' % id(source), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.planted_cosine


class FaceCosineTest(unittest.TestCase):
    """The face cosine has one body, one home, and four readers that answer alike."""

    def test_the_owner_and_every_reader_answer_the_same_value_for_a_fixed_corpus(self):
        """Every pair of the corpus gets one answer from the owner and every reader."""
        for name, a, b, expected in CORPUS:
            for label, bound, reader in READERS:
                with self.subTest(pair=name, reader=label):
                    owner_answer = face_id._cosine(a, b)
                    reader_answer = reader(a, b)
                    self.assertEqual(
                        same_number(owner_answer, reader_answer), True,
                        '%s: %s answers %r and %s binds %s, which answers %r'
                        % (name, OWNER.name, owner_answer, label, bound, reader_answer))
                    self.assertIsInstance(owner_answer, float,
                                          '%s: the answer must be a float, and it is %s'
                                          % (name, type(owner_answer).__name__))
            with self.subTest(pair=name):
                owner_answer = face_id._cosine(a, b)
                if isinstance(expected, float) and math.isnan(expected):
                    self.assertEqual(
                        math.isnan(owner_answer), True,
                        '%s: the owner must answer nan, and it answers %r'
                        % (name, owner_answer))
                else:
                    self.assertAlmostEqual(owner_answer, expected, places=6,
                                           msg='%s: the answer must be %r' % (name, expected))

    def test_the_owner_answers_nan_for_a_pair_that_carries_nan(self):
        """The NaN answer is the owner's decision, and it must not drift to 0.0.

        Round 90 deleted a copy of the rule whose guard read ``if na > 0 and nb >
        0``.  That guard is False for a NaN norm, so the copy answered ``0.0``.
        The owner guard reads ``if na <= 0.0 or nb <= 0.0``, which is also False
        for a NaN norm, so the owner divides and answers ``nan``.  ``0.0`` would
        read as a real, low similarity; ``nan`` fails every comparison and is
        refused by the threshold of ``best_match``.  The owner decides the rule.
        """
        nan = float('nan')
        for label, a, b in (('a NaN on the left', [nan, 1.0], [1.0, 1.0]),
                            ('a NaN on the right', [1.0, 1.0], [nan, 1.0]),
                            ('a NaN on both sides', [nan, 1.0], [nan, 1.0]),
                            ('a NaN that is not finite', [float('inf'), 1.0], [nan, 1.0])):
            with self.subTest(pair=label):
                answer = face_id._cosine(a, b)
                self.assertIsInstance(answer, float,
                                      '%s: the answer must be a float, and it is %s'
                                      % (label, type(answer).__name__))
                self.assertEqual(math.isnan(answer), True,
                                 '%s: the owner answers %r, and it must answer nan; a guard '
                                 'of `na > 0 and nb > 0` would answer 0.0 here'
                                 % (label, answer))
        self.assertFalse(face_id._cosine([nan, 1.0], [1.0, 1.0]) >= 0.0,
                         'the NaN answer must fail a threshold comparison, not pass it')

    def test_face_id_holds_the_one_body(self):
        """The owner holds the rule: float32 input, the flat view, the float result."""
        node = owner_function()
        self.assertIsNotNone(node, '%s does not define %s any more' % (OWNER.name, OWNER_NAME))
        text = body_text(node)
        for line in FLAT_VIEW + (FLOAT_RESULT, ZERO_ANSWER):
            self.assertIn(line, text,
                          'the body of %s must hold %r, and it holds %s'
                          % (OWNER_NAME, line, text.replace('\n', ' / ')))

    def test_eval_faces_imports_the_one_body(self):
        """The reader imports the name, holds no second body, and reads one object."""
        imports = imported_from(READER, OWNER_MODULE)
        self.assertEqual(OWNER_NAME, imports.get(READER_NAME),
                         '%s binds %s from %s, and it must import %s as %s'
                         % (READER.name, imports.get(READER_NAME), OWNER_MODULE,
                            OWNER_NAME, READER_NAME))
        self.assertNotIn(READER_NAME, module_function_names(READER),
                         '%s defines %s again, so the rule has a second body'
                         % (READER.name, READER_NAME))
        self.assertIs(face_id._cosine, eval_faces._cos,
                      'src/eval_faces.py holds a second body, and not the owner name')

    def test_no_module_outside_the_owner_binds_a_second_body(self):
        """Every module that holds a cosine name imports the owner, and writes no body."""
        bindings = cosine_bindings()
        holders = {(module, name) for module, _, name, _ in bindings}
        for label, bound, reader in READERS:
            with self.subTest(reader=label):
                self.assertIn((label, bound), holders,
                              '%s binds %s, and the walk of the tree finds no import of %s'
                              % (label, bound, OWNER_NAME))
                self.assertIs(face_id._cosine, reader,
                              '%s binds %s, and it must bind the object %s.%s'
                              % (label, bound, OWNER_MODULE, OWNER_NAME))
        for module, line, bound, imported in bindings:
            with self.subTest(module=module, line=line):
                if imported == OWNER_MODULE:
                    continue  # `import src.face_id as <name>`: the object is one attribute away
                self.assertIn(imported, RULE_NAMES,
                              '%s:%d binds %s from %s, and the names of the rule are %s'
                              % (module, line, bound, OWNER_MODULE, ', '.join(sorted(RULE_NAMES))))
        reads = owner_attribute_reads()
        for module, line, alias in reads:
            with self.subTest(module=module, line=line):
                self.assertIn(alias, module_aliases(ROOT / module),
                              '%s:%d reads %s._cosine through %r, and no `import %s` of that '
                              'file binds %r' % (module, line, alias, alias, OWNER_MODULE, alias))

    def test_one_site_of_the_body_stands_in_the_walked_tree(self):
        """One walk of src/, tests/ and annotator/ finds the body once, whatever zero a copy writes."""
        node = owner_function()
        self.assertIsNotNone(node, '%s does not define %s any more' % (OWNER.name, OWNER_NAME))
        sites = shape_sites(body_shape(node))
        self.assertEqual(1, len(sites),
                         'the body of %s stands in %d sites of %s: %s'
                         % (OWNER_NAME, len(sites), ', '.join(WALK_ROOTS), site_listing(sites)))
        module, _, name = sites[0]
        self.assertEqual((OWNER.relative_to(ROOT).as_posix(), OWNER_NAME), (module, name),
                         'the one site of the body is %s, and it must be %s %s'
                         % (site_listing(sites), OWNER.relative_to(ROOT).as_posix(), OWNER_NAME))

    def test_the_walk_reports_a_copy_planted_in_a_root_it_does_not_own(self):
        """A copy in a temporary module makes both the walk and a run of the rule red.

        The temporary module stands in a directory of its own, so the test leaves
        no file inside the repository.  The rule has two shapes and the check
        needs both: the first copy rewrites the statements, and the walk sees it
        wherever it stands.  The second copy keeps the statements of the deleted
        ternary body, so the walk cannot see it, and a run of the rule over the
        corpus must answer for it.
        """
        node = owner_function()
        self.assertIsNotNone(node, '%s does not define %s any more' % (OWNER.name, OWNER_NAME))
        shape = body_shape(node)
        with tempfile.TemporaryDirectory(prefix='face-cosine-') as tmp:
            planted = Path(tmp) / 'planted_cosine_copy.py'
            planted.write_text(PLANTED_COPY, encoding='utf-8')
            sites = shape_sites(shape, (tmp,))
            self.assertEqual(
                1, len(sites),
                'the walk found %d sites of the body after a copy was planted in %s, and it '
                'must find one: %s' % (len(sites), planted.name, site_listing(sites)))
            self.assertIn('planted_cosine', [name for _, _, name in sites],
                          'the walk did not report the planted copy: %s' % site_listing(sites))
            torn = load_planted(PLANTED_TERNARY, tmp)
            for name, a, b, expected in FINITE_CORPUS:
                with self.subTest(pair=name):
                    answer, torn_answer = face_id._cosine(a, b), torn(a, b)
                    self.assertEqual(
                        same_number(answer, torn_answer), True,
                        'the planted copy answers %r where the owner answers %r for %s; a copy '
                        'of the rule outside its home is red here' % (torn_answer, answer, name))


if __name__ == '__main__':
    unittest.main()
