"""One home for the face cosine: ``src/face_id.py _cosine``.

Two modules held this body: ``src/face_id.py _cosine`` and ``src/eval_faces.py
_cos``.  Their statements were the same, except for one spelling: the
zero-length test wrote ``0.0`` in the first module and ``0`` in the second.  The
walk of ``tests/test_duplicate_bodies.py`` hashes the text of a body, so the two
digests came out apart and that walk reported nothing.

Round 58 gives the rule one home.  ``src/face_id.py`` holds the body, and
``src/eval_faces.py`` reads it as ``_cos``.  This module holds five checks:

* the two modules answer the same value for a fixed corpus of vector pairs;
* the owner holds the body with its four properties;
* the reader imports the one name and holds no second body;
* one walk of ``src/*.py`` finds one site of the body, and that walk writes
  every number in one shape, so a copy with the other zero spelling is seen;
* a copy planted in a temporary module of ``src/`` makes the walk red.

The same-value check of the first bullet cannot see the old defect on its own,
because the two old bodies agreed on every input.  The absolute answer of each
corpus row is therefore checked as well.

Run: ``./scripts/pool-test.sh python test_face_cosine``
"""
from __future__ import annotations

import ast
import hashlib
import os
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import eval_faces, face_id  # noqa: E402  (after the path fix above)

SRC = ROOT / 'src'
OWNER = SRC / 'face_id.py'
OWNER_NAME = '_cosine'
READER = SRC / 'eval_faces.py'
READER_NAME = '_cos'
OWNER_MODULE = 'src.face_id'

#: The rule of the one body, as text, straight from the round-58 brief.
FLAT_VIEW = ('np.asarray(a, np.float32).ravel()', 'np.asarray(b, np.float32).ravel()')
FLOAT_RESULT = 'return float(np.dot(a, b) / (na * nb))'
ZERO_ANSWER = 'return 0.0'

#: (name, a, b, expected).  ``expected`` is the answer both modules must give.
#: The corpus holds a normal pair, a pair of unit vectors, a zero vector on each
#: side, a negative pair, a pair of integer lists and a pair of nested lists.
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
    ('two float32 arrays', np.array([1.0, 2.0, 3.0], np.float32),
     np.array([3.0, 2.0, 1.0], np.float32), 0.7142857142857143),
)

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


class WholeNumbers(ast.NodeTransformer):
    """Write every number of one body in one shape.

    The two copies of the face cosine differed by the spelling ``0`` against
    ``0.0`` alone.  The walk must see a copy of that body whatever zero it
    writes, so the hash below reads the numbers in one shape.
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


def module_shape_sites(shape):
    """(module, line, name) of every site of one body shape under ``src/*.py``."""
    return [(path.relative_to(ROOT).as_posix(), line, name)
            for path in sorted(SRC.glob('*.py'))
            for line, name, node in module_functions(path) if body_shape(node) == shape]


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


def site_listing(sites):
    """The sites of one body, as ``module:line name``."""
    return ', '.join('%s:%d %s' % site for site in sites) or 'nowhere'


class FaceCosineTest(unittest.TestCase):
    """The face cosine has one body, one home, and two modules that answer alike."""

    def test_the_two_modules_answer_the_same_value_for_a_fixed_corpus(self):
        """Every pair of the corpus gets one answer from both modules."""
        for name, a, b, expected in CORPUS:
            with self.subTest(pair=name):
                owner_answer = face_id._cosine(a, b)
                reader_answer = eval_faces._cos(a, b)
                self.assertEqual(owner_answer, reader_answer,
                                 '%s: src/face_id.py answers %r and src/eval_faces.py answers %r'
                                 % (name, owner_answer, reader_answer))
                self.assertIsInstance(owner_answer, float,
                                      '%s: the answer must be a float, and it is %s'
                                      % (name, type(owner_answer).__name__))
                self.assertAlmostEqual(owner_answer, expected, places=6,
                                       msg='%s: the answer must be %r' % (name, expected))

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

    def test_one_site_of_the_body_stands_in_src(self):
        """One walk of src/*.py finds the body once, whatever zero a copy writes."""
        node = owner_function()
        self.assertIsNotNone(node, '%s does not define %s any more' % (OWNER.name, OWNER_NAME))
        sites = module_shape_sites(body_shape(node))
        self.assertEqual(1, len(sites),
                         'the body of %s stands in %d sites of src/: %s'
                         % (OWNER_NAME, len(sites), site_listing(sites)))
        module, _, name = sites[0]
        self.assertEqual((OWNER.relative_to(ROOT).as_posix(), OWNER_NAME), (module, name),
                         'the one site of the body is %s, and it must be %s %s'
                         % (site_listing(sites), OWNER.relative_to(ROOT).as_posix(), OWNER_NAME))

    def test_the_walk_reports_a_copy_planted_in_a_temporary_module(self):
        """A copy in a temporary module of src/ makes the walk of the case above red."""
        node = owner_function()
        self.assertIsNotNone(node, '%s does not define %s any more' % (OWNER.name, OWNER_NAME))
        shape = body_shape(node)
        planted = SRC / ('_tmp_face_cosine_%d.py' % os.getpid())
        self.addCleanup(planted.unlink, True)
        planted.write_text(PLANTED_COPY, encoding='utf-8')
        sites = module_shape_sites(shape)
        self.assertEqual(
            2, len(sites),
            'the walk found %d sites of the body after a copy was planted in %s, and it must find '
            'two: %s' % (len(sites), planted.name, site_listing(sites)))
        self.assertIn(planted.relative_to(ROOT).as_posix(), [module for module, _, _ in sites],
                      'the walk did not report the planted copy: %s' % site_listing(sites))


if __name__ == '__main__':
    unittest.main()
