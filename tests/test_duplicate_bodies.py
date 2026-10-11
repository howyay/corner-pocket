"""One home for every module-level body that two modules of src/ wrote twice.

Two module-level functions of two modules are one copy when their bodies are the
same statements.  A change to one copy then changes one caller only, and nothing
tells a reader that the other copy exists.  The walk of round 51 measured four
such bodies:

* the box-overlap rule, held by ``src/box_geometry.py iou`` and by
  ``src/person_pipeline.py _iou``.  The rule has its own guard in
  ``tests/test_box_geometry.py``, which also records the near miss
  ``src/enroll_from_tracklet.py:153 face_area_iou`` (a name that ends in ``iou``
  and a body that differs);
* the scalar coercion, held by ``src/event_gates.py num_or_none`` and by
  ``src/ball_census.py _num``.  One home: event_gates, and the census imports it;
* the psycopg JSON wrapper, held by ``src/store_import.py jsonb`` and by
  ``src/store_pg.py _jsonb``.  One home: store_import, and the store imports it;
* the six-number summary of one list, held by ``src/enroll_from_tracklet.py
  stats`` and by ``src/eval_faces.py pair_stats``.  This is the one recorded
  exception, ``APART_ON_PURPOSE`` below.

The walk compares syntax trees and not text.  It removes the docstring of each
function, unparses the statements that remain with ``ast.unparse``, and hashes
them.  So a copy is found whatever its name is, the spacing does not matter, and
one changed name or term makes the two bodies differ.

Run: ``./scripts/pool-test.sh python test_duplicate_bodies``
"""
from __future__ import annotations

import ast
import hashlib
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SRC = ROOT / 'src'
VENDORED = SRC / 'sam3'

# The pairs that stay apart, keyed by the sha1 of the body.  An entry names the
# two files, the two function names, the body hash and the reason.  An entry must
# fail when the pair changes: see the two cases below.
APART_ON_PURPOSE = {
    'df02f87e2fc190ef51b10bdd2b80367dc5c1cdc9': (
        ('enroll_from_tracklet.py', 'stats'),
        ('eval_faces.py', 'pair_stats'),
        'Both functions answer n/min/p05/median/p95/max of one list of numbers, so the two '
        'bodies are one body.  Round 51 wrote both files outside its write scope, so the pair '
        'is recorded here and not changed.  A later change that owns both files gives one of '
        'them the body and the other the import.',
    ),
}


@dataclass(frozen=True)
class SharedBody:
    """One body that several modules read, and the readers of it."""
    owner: str               # the module under src/ that holds the body
    name: str                # the name of the function in the owner
    readers: tuple           # (module under src/, the name it binds from the owner)


# The pairs of round 51 that got one home.  The owner holds the body, each reader
# imports the name from the owner, and no other module of src/ holds the body.
SHARED = (
    SharedBody('box_geometry.py', 'iou',
               (('person_pipeline.py', 'iou'), ('recut_crops.py', 'iou'))),
    SharedBody('event_gates.py', 'num_or_none', (('ball_census.py', 'num_or_none'),)),
    SharedBody('store_import.py', 'jsonb', (('store_pg.py', 'jsonb'),)),
)


def body_fingerprint(node):
    """The sha1 of one function's statements, with its docstring and layout removed.

    A docstring names the body; it is not the body.  ``ast.unparse`` writes the
    statements back in one shape, so two copies that differ only in spacing or in
    a comment hash the same, and two bodies that differ in one name or one term
    hash apart.
    """
    body = list(node.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return hashlib.sha1(ast.unparse(body).encode('utf-8')).hexdigest()


def module_bodies(module):
    """The module-level functions of one module of src/, as (name, line, fingerprint).

    A nested ``def`` and a method of a class are local helpers, so they do not
    count here.
    """
    path = SRC / module
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    return [(node.name, node.lineno, body_fingerprint(node))
            for node in tree.body if isinstance(node, ast.FunctionDef)]


def bodies_per_module():
    """{body fingerprint: [(module, function name, line), ...]} for every module of src/."""
    found = {}
    for path in sorted(SRC.glob('*.py')):
        for name, line, digest in module_bodies(path.name):
            found.setdefault(digest, []).append((path.name, name, line))
    return found


def in_two_modules(entries):
    """The entries of one body that live in two modules or more."""
    return len({module for module, _, _ in entries}) > 1


def imported_names(module, owner):
    """{bound name: imported name} for the module-level imports of one owner module."""
    path = SRC / module
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == owner:
            for alias in node.names:
                found[alias.asname or alias.name] = alias.name
    return found


def where(entries):
    """The sites of one body, as ``module:line name``."""
    return ', '.join('%s:%d %s' % (module, line, name) for module, name, line in entries)


class DuplicateBodiesTest(unittest.TestCase):
    """Every module-level body of src/ has one home, and the walk proves it."""

    def test_the_walk_reaches_the_modules_of_src(self):
        """A walk over too few modules proves nothing."""
        modules = sorted(SRC.glob('*.py'))
        self.assertGreater(len(modules), 60,
                           'the walk reached %d modules of src/, too few to prove the homes'
                           % len(modules))
        self.assertNotIn(VENDORED, modules, 'the vendored tree is not our module')

    def test_no_two_modules_hold_one_body(self):
        """One body, one module: a copy under another name fails here."""
        found = bodies_per_module()
        duplicates = {digest: entries for digest, entries in found.items()
                      if in_two_modules(entries) and digest not in APART_ON_PURPOSE}
        self.assertEqual(
            {}, duplicates,
            'these bodies of src/ live in two modules, so one of them must read the other: '
            + '; '.join('%s %s' % (digest[:12], where(entries))
                        for digest, entries in sorted(duplicates.items())))

    def test_every_recorded_exception_is_still_the_same_pair_of_bodies(self):
        """A recorded pair fails when a file, a name or a body moves."""
        found = bodies_per_module()
        for digest, (first, second, reason) in APART_ON_PURPOSE.items():
            with self.subTest(pair='%s %s' % first):
                self.assertTrue(reason.strip(), 'the exception must state why the pair stays apart')
                entries = found.get(digest, [])
                self.assertEqual(sorted([first, second]),
                                 sorted((module, name) for module, name, _ in entries),
                                 'the recorded pair of body %s is now %s, so the record is stale'
                                 % (digest[:12], where(entries) or 'gone'))

    def test_every_shared_helper_has_one_home(self):
        """The owner holds the body, the readers import it, and nobody else copies it."""
        found = bodies_per_module()
        for record in SHARED:
            with self.subTest(helper=record.name):
                digest = next((digest for name, _, digest in module_bodies(record.owner)
                               if name == record.name), None)
                self.assertIsNotNone(digest, '%s does not define %s' % (record.owner, record.name))
                holders = sorted({module for module, _, _ in found.get(digest, [])})
                self.assertEqual([record.owner], holders,
                                 'the body of %s lives in %s, and its one home is %s'
                                 % (record.name, holders, record.owner))
                for module, bound in record.readers:
                    self.assertIn(bound, imported_names(module, 'src.' + record.owner[:-3]),
                                  'src/%s does not import %s from the owner src/%s'
                                  % (module, bound, record.owner))

    def test_the_readers_bind_the_owner_object_at_run_time(self):
        """The imports point at one object, and not at a second body that agrees today."""
        from src import ball_census, event_gates, store_import, store_pg
        self.assertIs(event_gates.num_or_none, ball_census.num_or_none,
                      'the census holds a second coercion body, not the owner name')
        self.assertIs(store_import.jsonb, store_pg.jsonb,
                      'the store holds a second JSON wrapper, not the owner name')
        self.assertIsNone(ball_census.num_or_none(True), 'a bool is not a number')
