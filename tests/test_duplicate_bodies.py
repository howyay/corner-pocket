"""One home for every module-level body that two modules of src/ wrote twice.

Two module-level functions of two modules are one copy when their bodies are the
same statements.  A change to one copy then changes one caller only, and nothing
tells a reader that the other copy exists.  The walk of round 51 measured four
such bodies:

* the box-overlap rule, held by ``src/box_geometry.py iou`` and by
  ``src/person_pipeline.py _iou``.  The rule has its own guard in
  ``tests/test_box_geometry.py``, which also records the near miss
  ``src/enroll_from_tracklet.py:156 face_area_iou`` (a name that ends in ``iou``
  and a body that differs);
* the scalar coercion, held by ``src/event_gates.py num_or_none`` and by
  ``src/ball_census.py _num``.  One home: event_gates, and the census imports it;
* the psycopg JSON wrapper, held by ``src/store_import.py jsonb`` and by
  ``src/store_pg.py _jsonb``.  One home: store_import, and the store imports it.

Round 60 measured a fifth body and gave it one home.  ``src/stats.py summary``
holds the summary of one list of numbers: ``n``, ``min``, ``p05``, ``p10``,
``median``, ``p90``, ``p95`` and ``max``.  Four modules held a body of that
summary before round 60: ``src/enroll_from_tracklet.py stats``,
``src/eval_faces.py pair_stats``, ``src/calib_mapping_audit.py _stats`` and
``src/eval_table_detect.py _stats``.  The first two held the same body, and the
table below recorded that pair.  The two others held fewer keys and a smaller
precision.  The four readers now name the one owner, so the recorded pair is
gone from the table.  ``tests/test_stats.py`` holds that rule.

The walk compares syntax trees and not text.  It removes the docstring of each
function, unparses the statements that remain with ``ast.unparse``, and hashes
them.  So a copy is found whatever its name is, the spacing does not matter, and
one changed name or term makes the two bodies differ.

The walk reads the top level of a module, so a method of a class is not in it.
Round 55 widened the tree: the walk globs the source trees of ``src/`` and
``annotator/``, named in ``TREES``, so a copy that pairs one module of ``src/``
with one module of ``annotator/`` is found too.  Measured on 2026-10-11, that
walk found three module-level bodies of one timestamp function:
``annotator/operations.py timestamp``, ``annotator/unified_server.py now`` and
``annotator/vod_import.py now_iso``.  Round 55 wrote none of those three files, so
the walk records the triple in ``APART_ON_PURPOSE`` and changes no file of it.

Round 53 found the test "is this document named" twice inside two class bodies
(``events_document.py Document.named`` and ``sam3_artifact.py Artifact.named``).
It gave that test one home, ``document_stamp.is_named``, and it added
``NamedPredicateTest`` below, which walks the class bodies of every module of
src/.  Measured on 2026-10-11, four further cross-module pairs of method bodies
stay in class bodies: ``store.py`` with ``store_pg.py`` hold ``frame_detections``
and ``seeds_get``, and ``pid_anchor_ui.py`` with ``pid_seed_ui.py`` hold
``log_message`` and ``_send``.  Round 55 gave ``_send`` one home,
``src/reply_body.py write_reply``, so three of the four pairs stay: the class-body
walk of that body is the case ``test_the_reply_body_has_one_site_in_the_annotator_server``
in ``tests/test_one_reply_body.py``.  A later round owns the three that stay.

Run: ``./scripts/pool-test.sh python test_duplicate_bodies``
"""
from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The body fingerprint has one home, tests/_shipped.py.
from _shipped import body_fingerprint  # noqa: E402

SRC = ROOT / 'src'
VENDORED = SRC / 'sam3'
#: The source trees whose modules this walk reads.  One rule had one owner in src/
#: and three readers in three files, so a walk of src/ alone cannot see a copy that
#: pairs a module of src/ with a module of annotator/.
TREES = (SRC, ROOT / 'annotator')

# The pairs that stay apart, keyed by the sha1 of the body.  An entry names the
# two files, the two function names, the body hash and the reason.  An entry must
# fail when the pair changes: see the two cases below.
@dataclass(frozen=True)
class ApartBody:
    """One body that several sites keep apart on purpose, and why.

    ``sites`` names every site of that body, because a later change that gives the
    body one home must move all of them.  ``where`` writes them for a message.
    """
    sites: tuple             # (module, the name of the function)
    reason: str              # why the sites stay apart

    def named(self):
        """The sites, as ``module name``."""
        return '; '.join('%s %s' % site for site in self.sites)


STAMPED_TRIPLE = (('annotator/operations.py', 'timestamp'),
                  ('annotator/unified_server.py', 'now'),
                  ('annotator/vod_import.py', 'now_iso'))

APART_ON_PURPOSE = {
    '7e1173f55016fa90f33df74173559c5f1c53c334': ApartBody(
        STAMPED_TRIPLE,
        'All three functions answer one timestamp in ISO 8601 with the UTC zone, so the three '
        'bodies are one body.  Round 55 widened the walk from src/ to the two source trees, and '
        'that walk found this triple for the first time.  Round 55 wrote none of the three '
        'files, so the triple is recorded here and not changed.  A later change that owns the '
        'three files gives one of them the body and the other two the import.',
    ),
}


@dataclass(frozen=True)
class SharedBody:
    """One body that several modules read, and the readers of it.

    A module is named by its path from the root, because the walk reads two trees.
    """
    owner: str               # the module that holds the body
    name: str                # the name of the function in the owner
    readers: tuple           # (module, the name it binds from the owner)


# The pairs of round 51 that got one home.  The owner holds the body, each reader
# imports the name from the owner, and no other module of the trees holds the body.
SHARED = (
    SharedBody('src/box_geometry.py', 'iou',
               (('src/person_pipeline.py', 'iou'), ('src/recut_crops.py', 'iou'))),
    SharedBody('src/event_gates.py', 'num_or_none', (('src/ball_census.py', 'num_or_none'),)),
    SharedBody('src/store_import.py', 'jsonb', (('src/store_pg.py', 'jsonb'),)),
)


def walk_paths():
    """The module files of ``TREES``, in one stable order: ``src/x.py``, then ``annotator/y.py``."""
    return tuple(path for tree in TREES for path in sorted(tree.glob('*.py')))


def module_bodies(module):
    """The module-level functions of one module of a tree, as (name, line, fingerprint).

    A nested ``def`` and a method of a class are local helpers, so they do not
    count here.  ``module`` is the path of the file and not a name, because the
    walk reads two trees.
    """
    path = ROOT / module
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    return [(node.name, node.lineno, body_fingerprint(node))
            for node in tree.body if isinstance(node, ast.FunctionDef)]


def bodies_per_module():
    """{body fingerprint: [(module, line, function name), ...]} for every module of the trees."""
    found = {}
    for path in walk_paths():
        module = path.relative_to(ROOT).as_posix()
        for name, line, digest in module_bodies(module):
            found.setdefault(digest, []).append((module, line, name))
    return found


def in_two_modules(entries):
    """The entries of one body that live in two modules or more."""
    return len({module for module, _, _ in entries}) > 1


def imported_names(module, owner):
    """{bound name: imported name} for the imports of one owner module.

    The walk reads the whole tree.  A reader of `src/document_stamp.py` imports
    it inside a ``try`` block, and a walk of the top level misses that import.
    """
    path = ROOT / module
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == owner:
            for alias in node.names:
                found[alias.asname or alias.name] = alias.name
    return found


def where(entries):
    """The sites of one body, as ``module:line name``."""
    return ', '.join('%s:%d %s' % (module, line, name) for module, line, name in entries)


#: The one module of the trees that owns the document stamp protocol.
STAMP_MODULE = 'src/document_stamp'

#: The file of that module.
STAMP_OWNER = STAMP_MODULE + '.py'

#: The one predicate of that protocol that answers "is this document named".
NAMED_PREDICATE = 'is_named'

#: The two readers of the protocol, and the class in each one that answers it.
NAMED_READERS = (('src/events_document.py', 'Document'), ('src/sam3_artifact.py', 'Artifact'))


def names_stamped(node):
    """True when one operand of a comparison names the ``STAMPED`` status."""
    return ((isinstance(node, ast.Name) and node.id == 'STAMPED')
            or (isinstance(node, ast.Attribute) and node.attr == 'STAMPED'))


def stamped_comparisons_in(source, module):
    """(line, text) of every comparison with ``STAMPED`` in one body of source text.

    The walk goes into a class body on purpose.  The two ``named`` methods sat
    there, and the walk of ``module_bodies`` above does not reach them.
    """
    tree = ast.parse(source, filename=module)
    return [(node.lineno, ast.unparse(node)) for node in ast.walk(tree)
            if isinstance(node, ast.Compare)
            and any(names_stamped(operand) for operand in [node.left] + list(node.comparators))]


def stamped_comparisons(module):
    """(line, text) of every comparison with ``STAMPED`` in one module of a tree."""
    path = ROOT / module
    return stamped_comparisons_in(path.read_text(encoding='utf-8'), str(path))


def stamped_comparison_sites():
    """(module, line, text) of every comparison with ``STAMPED`` under the trees."""
    return [(path.relative_to(ROOT).as_posix(), line, text) for path in walk_paths()
            for line, text in stamped_comparisons(path.relative_to(ROOT).as_posix())]


def site_listing(sites):
    """The sites of one comparison, as ``module:line text``."""
    return ', '.join('%s:%d %s' % site for site in sites) or 'nowhere'


def method_statements(module, class_name, method_name):
    """One method of a class body, with its docstring removed."""
    path = ROOT / module
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    klass = next(node for node in tree.body
                 if isinstance(node, ast.ClassDef) and node.name == class_name)
    method = next(node for node in klass.body
                  if isinstance(node, ast.FunctionDef) and node.name == method_name)
    body = list(method.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return method, body


def enclosing_function(tree, line):
    """The innermost function of one module that holds a line, or None."""
    holders = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef)
               and node.lineno <= line <= (node.end_lineno or node.lineno)]
    if not holders:
        return None
    return max(holders, key=lambda node: node.lineno)


class DuplicateBodiesTest(unittest.TestCase):
    """Every module-level body of src/ has one home, and the walk proves it."""

    def test_the_walk_reaches_the_modules_of_src(self):
        """A walk over too few modules proves nothing."""
        modules = walk_paths()
        self.assertGreater(len(modules), 60,
                           'the walk reached %d modules of the trees, too few to prove the homes'
                           % len(modules))
        self.assertEqual([SRC, ROOT / 'annotator'], list(TREES),
                         'the walk reads the trees %s, and it must read both source trees'
                         % [tree.name for tree in TREES])
        self.assertNotIn(
            'sam3', [part for path in modules for part in path.relative_to(ROOT).parts],
            'the vendored tree is not our module')

    def test_no_two_modules_hold_one_body(self):
        """One body, one module: a copy under another name fails here.

        The walk reads two trees, so the pair that fails here can be ``src/x.py`` with
        ``annotator/y.py``, as well as two modules of one tree.
        """
        found = bodies_per_module()
        duplicates = {digest: entries for digest, entries in found.items()
                      if in_two_modules(entries) and digest not in APART_ON_PURPOSE}
        self.assertEqual(
            {}, duplicates,
            'these bodies of the trees live in two modules, so one of them must read the other: '
            + '; '.join('%s %s' % (digest[:12], where(entries))
                        for digest, entries in sorted(duplicates.items())))

    def test_every_recorded_exception_is_still_the_same_body(self):
        """A recorded body fails when a file, a name or a body moves."""
        found = bodies_per_module()
        for digest, record in APART_ON_PURPOSE.items():
            with self.subTest(body=record.named()):
                self.assertTrue(record.reason.strip(),
                                'the exception must state why the body stays apart')
                self.assertGreater(len(record.sites), 1,
                                   'a body that stays apart has two sites or more')
                entries = found.get(digest, [])
                self.assertEqual(sorted(record.sites),
                                 sorted((module, name) for module, _, name in entries),
                                 'the recorded body %s is now %s, so the record is stale'
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
                owner = record.owner[:-3].replace('/', '.')
                for module, bound in record.readers:
                    self.assertIn(bound, imported_names(module, owner),
                                  '%s does not import %s from the owner %s'
                                  % (module, bound, record.owner))

    def test_the_readers_bind_the_owner_object_at_run_time(self):
        """The imports point at one object, and not at a second body that agrees today."""
        from src import ball_census, event_gates, store_import, store_pg
        self.assertIs(event_gates.num_or_none, ball_census.num_or_none,
                      'the census holds a second coercion body, not the owner name')
        self.assertIs(store_import.jsonb, store_pg.jsonb,
                      'the store holds a second JSON wrapper, not the owner name')
        self.assertIsNone(ball_census.num_or_none(True), 'a bool is not a number')


class NamedPredicateTest(unittest.TestCase):
    """One module states the test "a document is named".  The two readers call it.

    The walk of ``DuplicateBodiesTest`` reads the top level of a module only.
    This class walks into class bodies, where the two copies of the test sat.
    """

    def test_one_statement_of_src_compares_a_status_with_stamped(self):
        """The test "a document is named" has one site, in one module, one function."""
        sites = stamped_comparison_sites()
        self.assertEqual(
            [STAMP_OWNER], sorted({module for module, _, _ in sites}),
            'the test "a document is named" lives in %s, and its one home is %s'
            % (site_listing(sites), STAMP_OWNER))
        self.assertEqual(1, len(sites),
                         '%s holds %d comparisons with STAMPED: %s'
                         % (STAMP_OWNER, len(sites), site_listing(sites)))
        module, line, _ = sites[0]
        tree = ast.parse((ROOT / module).read_text(encoding='utf-8'), filename=str(ROOT / module))
        holder = enclosing_function(tree, line)
        self.assertIsNotNone(holder, '%s:%d sits in no function' % (module, line))
        self.assertEqual(NAMED_PREDICATE, holder.name,
                         'the one statement of the test sits in %s, and its name must be %s'
                         % (holder.name, NAMED_PREDICATE))

    def test_the_walk_finds_a_second_copy_inside_a_class_body(self):
        """A class body proves that the walk of the case above is not empty."""
        forged = ('class Document:\n'
                  '    @property\n'
                  '    def named(self) -> bool:\n'
                  '        return self.status == STAMPED\n')
        found = stamped_comparisons_in(forged, 'a class body written for this case')
        self.assertEqual(1, len(found),
                         'the walk of a class body found %d statements, and one must appear'
                         % len(found))

    def test_the_two_named_methods_call_the_one_predicate(self):
        """Each class keeps its method, and each method holds a call only."""
        call = '%s.%s(self.status)' % (STAMP_MODULE.rsplit('/', 1)[-1], NAMED_PREDICATE)
        for module, class_name in NAMED_READERS:
            with self.subTest(module=module):
                method, body = method_statements(module, class_name, 'named')
                self.assertEqual(1, len(body),
                                 '%s %s.named holds %d statements, so it holds a rule of its own'
                                 % (module, class_name, len(body)))
                self.assertIsInstance(body[0], ast.Return,
                                      '%s %s.named must return the answer of the one predicate'
                                      % (module, class_name))
                self.assertEqual(call, ast.unparse(body[0].value),
                                 '%s %s.named must read the status through %s'
                                 % (module, class_name, call))
                self.assertFalse(any(isinstance(node, ast.Compare) for node in ast.walk(method)),
                                 '%s %s.named compares the status itself, and the test has one home'
                                 % (module, class_name))
                self.assertIn(STAMP_MODULE.rsplit('/', 1)[-1], imported_names(module, 'src'),
                              '%s does not import %s' % (module, STAMP_OWNER))

    def test_the_two_readers_answer_from_the_one_predicate_at_run_time(self):
        """The classes read one function object, and not a second body that agrees today."""
        from src import document_stamp, events_document, sam3_artifact
        for module in (events_document, sam3_artifact):
            with self.subTest(module=module.__name__):
                self.assertIs(document_stamp.is_named, module.document_stamp.is_named,
                              '%s holds a second named test, not the owner name' % module.__name__)
        document = events_document.Document(
            path=SRC / 'events.json', rows=[], status=document_stamp.STAMPED)
        artifact = sam3_artifact.Artifact(
            path=SRC / 'sam3_results.json', frames={}, status=document_stamp.STAMPED)
        mixed = events_document.Document(
            path=SRC / 'events.json', rows=[], status=document_stamp.MIXED)
        self.assertTrue(document.named, 'a stamped document must read named')
        self.assertTrue(artifact.named, 'a stamped artifact must read named')
        self.assertFalse(mixed.named, 'a mixed document must not read named')
