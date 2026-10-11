"""The five merge rules of the two stores have one home, and this module guards it.

The walk of round 56 measured the statements that `JsonStore` (src/store.py) and
`PostgresStore` (src/store_pg.py) held twice, in the bodies of the four mutators
`seed_put`, `verdict_put`, `label_put` and `anchors_put`.  Six statements of each
class were copies of one of five rules:

  * the merge of one stored record with one incoming record: `src/store.py:288`
    with `src/store_pg.py:288` (seed_put), and `src/store.py:301` with
    `src/store_pg.py:322` (verdict_put);
  * the delete of one record: `src/store.py:286` with `src/store_pg.py:286`;
  * the clear of one crop: `src/store.py:325` with `src/store_pg.py:354`;
  * the lookup of a key by basename: `src/store.py:323` with `src/store_pg.py:352`;
  * the float spelling of one anchor time: `src/store.py:353` with
    `src/store_pg.py:396`.

A measurement of the raw statement lists of that revision counted 17 shared
statements over the four mutators.  Only the five rules above are the copy: the
other statements are plumbing that both bodies must hold (`return seeds`,
`seeds = saved.setdefault('seeds', {})`, the clock stamp, and the two `if` and
`for` headers of the label rule).

`src/store_rules.py` is the one home of those rules now.  It holds pure functions
and no store, so both classes import it and neither class holds a copy.

The guard that compares the two backends (`tests/test_store_contract.py`) cannot
see a copy in a default run: `PostgresContract` carries
`@unittest.skipUnless(HAVE_DB, ...)`, the machine of round 56 answers an unset
`POOL_DATABASE_URL`, and the `JsonContract` cases then run alone.  This module
reads the source, so it runs on every machine, with no database.

The module holds five checks:
  * the walk finds the two classes and the four mutators (a walk of an empty set
    proves nothing);
  * no class body holds a statement of one of the five rules again - the failure
    names the site `src/store_pg.py:NNN`;
  * the owner answers the merge, the delete, the clear and the float key, and it
    keeps the behaviour of the old bodies;
  * the two backends write one document for one sequence of edits, so a later edit
    of one class alone fails here;
  * both classes read the name `src/store_rules.py` at run time, so the classes
    call the owner and hold no second body that agrees today.

`RulePlantingTest` plants the pre-repair `PostgresStore.label_put` body in a walk
of this module, so the reader knows that the walk of the case above can see a copy.

Run: ``./scripts/pool-test.sh python test_store_merge_rules``
"""
from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The classes that held the four copies.  The walk reads the file of each entry.
STORES = (
    ('src/store.py', 'JsonStore'),
    ('src/store_pg.py', 'PostgresStore'),
)

#: The mutators whose bodies held the shared statements.
MUTATORS = ('seed_put', 'verdict_put', 'label_put', 'anchors_put')

#: The owner of the rules, as a dotted name and as a file.
RULES_MODULE = 'src.store_rules'
RULES_FILE = 'src/store_rules.py'

#: The five rules of the owner.  Each entry holds the rule name, the number of
#: pre-repair sites of that rule, the exact text of the statement that held the rule
#: at each site, and the owner function that holds the rule now.  A statement of a
#: class body with that exact text is a second copy of a rule.
FROZEN_RULES = (
    ('the merge of one record', 3, "seeds[key] = dict(seeds.get(key, {}), **record)", "merge_record"),
    ('the merge of one record', 3, "record = dict(annotations.get(key, {}), **fields)", "merge_record"),
    ('the delete of one record', 2, "seeds.pop(key, None)", "drop_key"),
    ('the clear of one record', 2, "for old in keys:\n    labels.pop(old)", "clear_keys"),
    ('the lookup of a key by basename', 2,
     "keys = [k for k in labels if Path(k).name == crop_file]", "keys_for_basename"),
    ('the float spelling of one anchor time', 2,
     "key = next((k for k in saved['anchors'] if float(k) == float(t_key)), str(t_key))", "spelled_time"),
)

#: The site of the worst drift of the walk of round 56, for the failure message.
DRIFT_SITE = 'src/store_pg.py:352'

#: The four documents one sequence of edits writes: the seed document, the verdict
#: document, the label document and the anchor document.  The paths are the paths of
#: JsonStore, and they are also the document names of PostgresStore (`_doc_path`).
DOCUMENTS = (
    'out/pid_seed.json',
    'out/scan30/annotations.json',
    'out/unlabeled_crops/labels.json',
    'out/pid_anchors_vod30.json',
)


@dataclass(frozen=True)
class ClassAt:
    """One class of one store file, with its module, its path and its parse tree."""
    path: str                       # the module, from the root
    name: str                       # the class name
    file: Path                      # the file of the module
    node: ast.ClassDef              # the class node of the parse of that file

    def method(self, name):
        """The one function called `name` in the class body, or None."""
        for child in self.node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == name:
                return child
        return None


def parse_module(path):
    """The parse tree of one module, as ``(tree, source text)``."""
    file = ROOT / path
    text = file.read_text(encoding='utf-8')
    return ast.parse(text, filename=str(file)), text


def class_at(path, name):
    """One class of one module, bound to its file and its node."""
    tree, _ = parse_module(path)
    for node in tree.body:
        if (isinstance(node, ast.ClassDef) and node.name == name
                and node.end_lineno > node.lineno):
            return ClassAt(path, name, ROOT / path, node)
    raise AssertionError('%s holds no class %s' % (path, name))


def held_classes():
    """The two classes, as objects of this run, so the walk and the code cannot drift."""
    from src.store import JsonStore
    from src.store_pg import PostgresStore
    return {
        'src/store.py': JsonStore,
        'src/store_pg.py': PostgresStore,
    }


def is_docstring(statement):
    """True for a bare string statement, which is a docstring."""
    return (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str))


def method_nodes(node):
    """Every function of one class body, and every function inside one of them."""
    for child in ast.walk(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield child


def without_docstring(function):
    """The statements of one function, with its docstring removed."""
    body = list(function.body)
    if body and is_docstring(body[0]):
        body = body[1:]
    return body


def edit_statements(function):
    """Every statement of one method that can hold an edit rule.

    The walk reads the method body and the bodies of the `if`, `for` and `while`
    statements inside it, because one rule sat in a `for` body at the site
    `src/store_pg.py:354` (`for old in keys:`) and its body `labels.pop(old)` sat at
    `src/store_pg.py:355`.  The walk does not enter a `with` body: that body holds
    the lock and the writes, and those differ between the two backends.
    """
    def of(statements):
        for statement in statements:
            yield statement
            if isinstance(statement, ast.With):
                continue
            for field in ('body', 'orelse', 'finalbody'):
                yield from of(getattr(statement, field, None) or [])
    return of(without_docstring(function))


def statement_texts(function):
    """One statement text per edit statement of one method, with the docstring removed."""
    return [' '.join(ast.unparse(statement).split()) for statement in without_docstring(function)]


def rule_shapes():
    """The rule shapes, as the exact statement text of the pre-repair bodies held them."""
    shapes = {}
    for rule, _sites, text, _owner in FROZEN_RULES:
        shapes[' '.join(text.split())] = rule
    return shapes


#: One class body whose call sites name the owner, and whose rule bodies stay home.
#: The walk must find no copy in it: a guard that fails on this body refuses the
#: repair itself.
REPAIRED_LABEL_PUT = (
    'def label_put(self, crop_set, crop_file, label, new_key=None):\n'
    '    labels = _read(path, {})\n'
    '    keys = store_rules.keys_for_basename(labels, crop_file)\n'
    '    key = keys[0] if keys else (new_key or crop_file)\n'
    '    store_rules.clear_keys(labels, keys)\n'
    '    if label is not None:\n'
    '        labels[key] = label\n'
)


def rule_copies(klass, shapes=None):
    """The sites in one class that hold the exact text of one rule again.

    The answer holds ``(path, line, the method name, the rule)`` for every copy.  The
    compare uses the AST, so the spacing of the source does not matter.
    """
    shapes = rule_shapes() if shapes is None else shapes
    found = []
    for function in method_nodes(klass.node):
        for statement in edit_statements(function):
            text = ' '.join(ast.unparse(statement).split())
            if text in shapes:
                found.append((klass.path, statement.lineno, function.name, shapes[text]))
    return sorted(found)


def site_listing(sites):
    """The sites of one set of copies, as ``module:line``, or ``nowhere``."""
    return ', '.join('%s:%d' % (path, line) for path, line, _name, _rule in sites) or 'nowhere'


def dotted_name(node):
    """The dotted name of one attribute chain, or None for another expression."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return '.'.join(reversed(parts + [node.id]))


def first_imported_name(tree, module):
    """The local name one module is bound to by an import, or None.

    The walk reads the top level of the module alone: every store imports the owner
    there, next to its other imports.
    """
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    return alias.asname or alias.name
        if isinstance(node, ast.ImportFrom) and node.module == module:
            if node.names:
                return node.names[0].asname or node.names[0].name
    return None


def owner_calls(klass):
    """The owner functions one class calls, as ``rule name`` pairs, sorted and unique."""
    local = first_imported_name(ast.parse(klass.file.read_text(encoding='utf-8')), RULES_MODULE)
    called = set()
    for function in method_nodes(klass.node):
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            name = dotted_name(node.func)
            if not name:
                continue
            if local is None:
                called.add('(no import of %s)' % RULES_MODULE)
            elif name.startswith(local + '.'):
                called.add('%s %s' % (name[len(local) + 1:], name))
    return sorted(called)


class FakeConnection:
    """The one connection a sink store needs: it records the statements and answers None."""

    ignored = ()
    closed = False
    read_only = None

    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        """Record one statement, and answer a cursor that holds no row."""
        self.statements.append((' '.join(sql.split()), params))
        return self

    def fetchone(self):
        return None

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *error):
        return False


class FakeDriver:
    """The one name the write path reads from psycopg: its error class."""

    class errors:
        """The error names of the driver.  No case here raises one."""

        class Error(Exception):
            """The base error of the driver."""

        class IntegrityError(Error):
            """A constraint the database refused."""


def document_sink(root, documents=None):
    """A PostgresStore whose document lives in a dict, and never in a database.

    Every line of the store runs unchanged, `_store_doc` and `_load_doc` included,
    so the document of this store is the document of a real one.  Only `_conn` and
    the `psycopg` name of the write path are replaced, so this needs no database and
    no POOL_DATABASE_URL.
    """
    from src.store_pg import PostgresStore
    documents = {} if documents is None else documents
    postgres = PostgresStore(root, 'postgresql://sink/no-connection')
    postgres._conn = FakeConnection

    def store_doc(conn, path, value, project):
        from src.store_files import dump, fmt_of
        documents[path] = dump(value, fmt_of(path))

    def load_doc(conn, path, default):
        text = documents.get(path)
        return default if text is None else json.loads(text)

    postgres._store_doc = store_doc
    postgres._load_doc = load_doc
    return postgres, documents


def seed_documents(root):
    """The four documents of one run, as the text of the same documents JsonStore reads.

    One sequence of edits reads every one of these paths.  The label document starts
    with two stored keys, so the basename lookup and the clear run on the first
    `label_put` call of either backend.
    """
    return {path: (root / path).read_text() for path in DOCUMENTS if (root / path).is_file()}


def without_clock(document):
    """One document with the wall-clock stamp of each record replaced by a fixed word.

    `verdict_put` stamps `updated_at` from the clock, so the two backends run at two
    different instants.  The stamp is not one of the five merge rules, so this
    function replaces it and the compare reads every other byte of the document.
    """
    return {path: re.sub(r'"updated_at": "[^"]*"', '"updated_at": "<clock>"', text)
            for path, text in document.items()}


def operations(store):
    """One sequence of edits, run through the real rule bodies of one store.

    Every argument is a plain value, so the two backends take the same path through
    their own body.  The label rule gets an existing absolute key, a second crop
    under a `new_key`, and a clear, so the basename lookup and the clear both run.
    """
    store.seed_put('vod30', '1:68-94', {'win': '68-94', 't': 68, 'label': 'A'})
    store.seed_put('vod30', '1:68-94', {'label': 'B'})
    store.seed_put('vod30', '1:68-94', None)
    store.verdict_put('vod30', 16, {'verdict': 'wrong', 'note': 'x'})
    store.verdict_put('vod30', 16, {'shooter': 'A'})
    store.label_put('unlabeled_crops', 'crop1.png', 7)
    store.label_put('unlabeled_crops', 'crop2.png', 'u', '/abs/meta/crop2.png/meta.json')
    store.label_put('unlabeled_crops', 'legacy.png', None)
    store.anchors_put('vod30', '70.0', [[1, 2]] * 6)
    store.anchors_put('vod30', '70.000', [[3, 4]] * 6)


class StoreMergeRulesTest(unittest.TestCase):
    """One home for the merge rules of the two stores, and the walk that proves it."""

    def test_the_walk_finds_the_two_classes_and_the_four_mutators(self):
        """A walk of an empty set of classes proves nothing."""
        classes = held_classes()
        self.assertEqual(['src/store.py', 'src/store_pg.py'], sorted(classes),
                         'the walk reads %s, and it must read the two store modules' % sorted(classes))
        total = 0
        for path, name in STORES:
            with self.subTest(module=path):
                klass = class_at(path, name)
                self.assertEqual((path[:-3].replace('/', '.'), name),
                                 (classes[path].__module__, classes[path].__name__),
                                 'the walk reads another class than the class of this run')
                for mutator in MUTATORS:
                    method = klass.method(mutator)
                    self.assertIsNotNone(method, '%s %s holds no %s' % (path, name, mutator))
                    statements = statement_texts(method)
                    self.assertTrue(statements,
                                    '%s %s %s holds no statement' % (path, name, mutator))
                    total += len(statements)
        self.assertGreaterEqual(total, 20,
                                'the walk read %d statements of the four mutators, too few to prove the walks'
                                % total)

    def test_neither_class_holds_a_shared_rule_again(self):
        """One rule, one home: a second copy in a class body fails here."""
        shapes = rule_shapes()
        self.assertEqual(len(FROZEN_RULES), len(shapes),
                         'two frozen rules hold one statement text, so the walk cannot tell them apart')
        for path, name in STORES:
            with self.subTest(module=path):
                klass = class_at(path, name)
                copies = rule_copies(klass, shapes)
                detail = '; '.join('%s:%d %s holds %r' % (site, line, method, rule)
                                   for site, line, method, rule in copies)
                self.assertEqual(
                    [], copies,
                    'these statements of %s hold a rule again, so the rule must move to %s: %s '
                    '(the worst drift of round 56 was %s)'
                    % (path, RULES_FILE, detail or 'none found', DRIFT_SITE))

    def test_the_owner_answers_the_merge_the_delete_the_clear_and_the_float_key(self):
        """The owner is pure, and the rules keep the behaviour of the old bodies."""
        from src import store_rules as owner
        for rule, _sites, _text, name in FROZEN_RULES:
            with self.subTest(rule=rule):
                self.assertTrue(callable(getattr(owner, name, None)),
                                'the frozen rule %r names the owner function %s, and the owner has no '
                                'such function' % (rule, name))
        stored = {'t': 68, 'label': 'A'}
        merged = owner.merge_record(stored, {'label': 'B'})
        self.assertEqual({'t': 68, 'label': 'B'}, merged, 'the incoming field must win the merge')
        self.assertEqual({'t': 68, 'label': 'A'}, stored, 'the merge must not change the stored record')
        owner.drop_key(merged, 'label')
        self.assertEqual({'t': 68}, merged, 'the delete must remove the one key')
        owner.drop_key(merged, 'absent')
        self.assertEqual({'t': 68}, merged, 'the delete must be quiet for an absent key')
        planted = {'/abs/crop1.png': 4, 'crop1.png': 5, 'legacy.png': 8}
        keys = owner.keys_for_basename(planted, 'crop1.png')
        self.assertEqual(['/abs/crop1.png', 'crop1.png'], keys,
                         'the lookup must answer every key of that basename, in the order of the mapping')
        owner.clear_keys(planted, keys)
        self.assertEqual({'legacy.png': 8}, planted, 'the clear must remove every key of the sequence')
        owner.clear_keys(planted, ['absent'])
        self.assertEqual({'legacy.png': 8}, planted, 'the clear must be quiet for an absent key')
        self.assertEqual('70.0', owner.spelled_time({'70.0': [], '71.0': []}, '70.000'),
                         'a stored key must keep its own spelling')
        self.assertEqual('70.0', owner.spelled_time({}, '70.0'),
                         'a missing key must answer str(t_key)')

    def test_the_two_backends_write_one_document_for_one_sequence_of_edits(self):
        """The repair survives a later edit of one class: one sequence, one document.

        Both stores start from the same four documents, one of them the label document
        with two stored keys already in it, so the `label_put` path exercises the
        basename lookup and the clear on both backends.
        """
        from src.store import JsonStore
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        labels_path = root / 'out' / 'unlabeled_crops' / 'labels.json'
        labels_path.parent.mkdir(parents=True)
        labels_path.write_text('{"/abs/path/crop1.png": 4, "legacy.png": 8}')
        files = JsonStore(root)
        sink, sink_documents = document_sink(root, seed_documents(root))
        with mock.patch.dict(sys.modules, {'psycopg': FakeDriver}):
            operations(files)
            operations(sink)
        json_document = {path: (root / path).read_text() for path in DOCUMENTS}
        self.assertEqual(without_clock(json_document), without_clock(sink_documents),
                         'the two backends hold a different document for one sequence of edits')

    def test_both_classes_read_the_owner_name(self):
        """The owner is one module, and the classes bind that module at run time."""
        from src import store as store_module
        from src import store_pg as store_pg_module
        from src import store_rules as owner
        bound = (store_module.store_rules, store_pg_module.store_rules)
        self.assertEqual(2, len(bound), 'two modules must bind the owner')
        for module in bound:
            self.assertIs(owner, module,
                          'a store holds a second rules object, not the owner %s' % RULES_MODULE)
        expected = {'%s store_rules.%s' % (rule, rule)
                    for rule in ('merge_record', 'drop_key', 'clear_keys',
                                 'keys_for_basename', 'spelled_time')}
        for path, name in STORES:
            with self.subTest(module=path):
                klass = class_at(path, name)
                self.assertEqual(expected, set(owner_calls(klass)),
                                 '%s %s calls %s, and it must call the five rules of %s'
                                 % (path, name, owner_calls(klass), RULES_MODULE))


class RulePlantingTest(unittest.TestCase):
    """The walk of the case above sees a copy, and it finds none in a repaired body.

    The first case plants the pre-repair `PostgresStore.label_put` body and proves the
    walk fails on it at the line of the copy.  The other two cases hold the other side:
    the walk finds no copy in a body that calls the owner, and it finds none in the
    real class bodies.
    """

    PRE_REPAIR_LABEL_PUT = (
        'def label_put(self, crop_set, crop_file, label, new_key=None):\n'
        '    labels = _read(path, {})\n'
        '    keys = [k for k in labels if Path(k).name == crop_file]\n'
        '    key = keys[0] if keys else (new_key or crop_file)\n'
        '    for old in keys:\n'
        '        labels.pop(old)\n'
        '    if label is not None:\n'
        '        labels[key] = label\n'
    )

    def test_the_walk_finds_a_planted_copy_in_a_class_body(self):
        """One planted copy of the lookup rule must fail this walk at its line."""
        tree = ast.parse(self.PRE_REPAIR_LABEL_PUT)
        planted = ClassAt('src/store_pg.py', 'PostgresStore', ROOT / 'src' / 'store_pg.py', tree)
        found = rule_copies(planted)
        self.assertEqual(['the clear of one record', 'the lookup of a key by basename'],
                         sorted(rule for _path, _line, _method, rule in found),
                         'the walk of a planted class body found %s, and it must find two copies'
                         % found)
        self.assertIn('src/store_pg.py:5', site_listing(found),
                      'the failure must name the site of the clear, and it names %s'
                      % site_listing(found))

    def test_the_walk_finds_no_copy_in_a_body_that_calls_the_owner(self):
        """The repair itself must pass: a body of call sites holds no rule of its own."""
        tree = ast.parse(REPAIRED_LABEL_PUT)
        repaired = ClassAt('src/store.py', 'JsonStore', ROOT / 'src' / 'store.py', tree)
        found = rule_copies(repaired)
        self.assertEqual([], found,
                         'the walk of a repaired body found a copy at %s, and it must find none'
                         % site_listing(found))

    def test_a_cosmetic_change_of_the_owner_keeps_the_walk_green(self):
        """The call site is the check that holds a cosmetic owner body.

        The walk compares the statements of the class bodies, so an edit inside
        `src/store_rules.py` does not fail the walk while the classes call the owner.
        The bite of round 56 measured that gap: a changed merge body of the owner left
        the walk green.  `test_both_classes_read_the_owner_name` closes it, because it
        reads the call sites and not the owner body.
        """
        tree = ast.parse(REPAIRED_LABEL_PUT)
        repaired = ClassAt('src/store.py', 'JsonStore', ROOT / 'src' / 'store.py', tree)
        self.assertEqual([], rule_copies(repaired),
                         'the walk must not fail on the spelling of one owner body')
        from src import store_rules as owner
        self.assertTrue(callable(owner.merge_record),
                        'the call site of the class body names a function the owner must hold')

    def test_the_pre_repair_postgres_label_put_body_holds_the_two_rules(self):
        """The copy of this case is the body that stood in the file before the repair."""
        tree = ast.parse(self.PRE_REPAIR_LABEL_PUT)
        planted = ClassAt('src/store_pg.py', 'PostgresStore', ROOT / 'src' / 'store_pg.py', tree)
        self.assertEqual(
            ['the clear of one record', 'the lookup of a key by basename'],
            sorted(rule for _path, _line, _method, rule in rule_copies(planted)),
            'the planted body is not the body of the walk of round 56')
        self.assertEqual([], rule_copies(class_at('src/store_pg.py', 'PostgresStore')),
                         'the real class body still holds a rule, so the walk must fail on it')
        self.assertTrue(DRIFT_SITE.endswith('352'),
                        'the recorded drift site must be the site of round 56')
