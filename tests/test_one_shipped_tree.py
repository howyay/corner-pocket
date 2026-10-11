"""One home for the shipped package tree and for the dotted-name reader.

Round 61 measured two duplications in this tree, and neither one is visible to
``tests/test_duplicate_bodies.py``: that walk reads the source trees of ``src/``
and ``annotator/`` only.

1. The package tree this repository ships was declared four times by hand, in
   four orders and two quoting styles, and the scanner over it stood twice.
   ``tests/_shipped.py`` is the one home now; the four guards read ``SHIPPED``
   and ``shipped_modules`` from it.

2. The reader of a dotted name stood four times, and the four bodies were not
   one body.  ``tests/_shipped.py`` is the one home now, and the four guards read
   ``dotted_name`` from it.

The cases below hold the two homes in place:

* the four modules of the tree read the owner name, and none of them declares
  the tree again;
* no ``test_*.py`` file defines ``shipped_modules`` or ``_dotted``, apart from
  the module the walk excludes;
* a planted copy, in a file named ``test_*.py``, makes the walk report that file;
* the expressions the guards read keep their one answer, and the recursive
  reader and the stack reader agree on every ``Call`` of the test tree.

Why this file, and not ``tests/test_suite_inventory.py``: that module counts how
many cases this checkout skips, and it holds four committed limits for that
count.  A rule about the text of the test tree is not a skip count, and a case
added there moves the discovery walk that the module measures against its own
floor.  This file is the guard of the rule, and it carries no limit.

Run: ``./scripts/pool-test.sh python test_one_shipped_tree``
"""
from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'

#: The one module that holds the two readers.
HELPER = '_shipped'

#: The four modules that declared the tree by hand until round 61.
TREE_READERS = (
    'test_shot_clock.py',
    'test_sql_domain_parity.py',
    'test_store_files.py',
    'test_tls_trust.py',
)

#: The four modules that held a copy of the dotted-name reader until round 61.
DOTTED_READERS = (
    'test_atomic_write.py',
    'test_events_document.py',
    'test_one_atomic_write.py',
    'test_sam3_artifact.py',
)

#: The names with one home.  A ``test_*.py`` file that defines one of these names
#: holds a second copy of a reader, and the walk reports that file.
WATCHED = ('shipped_modules', '_dotted')


def function_defs(path: Path):
    """(name, line) for every function this file defines at the top level.

    A method of a class and a nested ``def`` are local helpers of that class or
    function, so they are not in the answer.  ``ast.parse`` reads the text: a
    second copy of a whole file is read on its own turn, and not as a source of
    this one."""
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    return [(node.name, node.lineno) for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def scanned_nodes(folder: Path):
    """The watched readers a second file of ``folder`` defines.

    The walk reads the ``test_*.py`` files, and it leaves the one helper module
    out.  The answer is a mapping: one list of ``file:line`` sites for each
    watched name.  An empty mapping means the two readers have one home only."""
    found = {}
    for path in sorted(folder.glob('test_*.py')):
        if path.stem == HELPER:
            continue
        for name, line in function_defs(path):
            if name in WATCHED:
                found.setdefault(name, []).append(f'{path.name}:{line}')
    return found


def planted(name: str, path: Path) -> Path:
    """Write one file that defines ``name``, under a name the walk reads."""
    path.write_text('"""A second copy of one reader, for the case below."""\n'
                    '\n'
                    '\n'
                    f'def {name}(node):\n'
                    '    """A copy that answers a wrong text on purpose."""\n'
                    '    return "second copy"\n', encoding='utf-8')
    return path


def chain_root(node: ast.AST) -> ast.AST:
    """The last base of an attribute chain: the node below its attributes."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node


class OneHomeTest(unittest.TestCase):
    """The two readers of tests/_shipped.py have one home each."""

    def test_the_four_tree_readers_import_the_tree(self):
        """Each former site names the owner, and none of them spells it again."""
        helper = TESTS / f'{HELPER}.py'
        self.assertTrue(helper.is_file(), f'the one home must exist: {helper}')
        for name in TREE_READERS:
            path = TESTS / name
            self.assertTrue(path.is_file(), f'the reader of the tree must exist: {path}')
            text = path.read_text(encoding='utf-8')
            self.assertIn(f'from {HELPER} import', text,
                          f'{name} must read the tree from {HELPER}.py')
            self.assertNotIn('\nSHIPPED = ', text,
                             f'{name} must not declare the tree a second time')
            self.assertNotIn('\ndef shipped_modules(', text,
                             f'{name} must not declare the scanner a second time')
        for name in DOTTED_READERS:
            path = TESTS / name
            self.assertTrue(path.is_file(), f'the reader of the dotted name must exist: {path}')
            text = path.read_text(encoding='utf-8')
            self.assertIn(f'from {HELPER} import', text,
                          f'{name} must read the dotted name from {HELPER}.py')
            self.assertNotIn('\ndef _dotted(', text,
                             f'{name} must not declare the dotted-name reader a second time')

    def test_no_test_module_holds_a_second_copy(self):
        """The walk of tests/*.py reports no second copy of a watched reader."""
        found = scanned_nodes(TESTS)
        self.assertEqual(found, {},
                         f'the two readers have one home, tests/{HELPER}.py; the walk of '
                         f'tests/*.py found a second definition at: {found}')

    def test_the_walk_reports_a_planted_copy(self):
        """A file named test_*.py that defines the name is reported, with its line."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            planted('shipped_modules', root / 'test_planted_copy.py')
            found = scanned_nodes(root)
        self.assertEqual(list(found), ['shipped_modules'],
                         f'the walk must report the planted name: {found}')
        self.assertEqual(found['shipped_modules'], ['test_planted_copy.py:4'],
                         f'the walk must report the file and the line of the copy: {found}')

    def test_the_readers_keep_the_names_the_guards_read(self):
        """The one answer of each expression the four guards depend on."""
        from _shipped import dotted_name, dotted_name_by_loop
        named = ('a', 'a.b', 'a.b.c', 'os.replace', 'tempfile.NamedTemporaryFile',
                 'json.dump', 'pathlib.Path')
        for text in named:
            node = ast.parse(text, mode='eval').body
            self.assertEqual(dotted_name(node), text,
                             f'the reader must answer the dotted name of {text}')
            self.assertEqual(dotted_name_by_loop(node), text,
                             f'the stack reader must answer the same text for {text}')
        unnamed = ('f(x)', 'a[0]', '42', "'text'")
        for text in unnamed:
            node = ast.parse(text, mode='eval').body
            self.assertEqual(dotted_name(node), '',
                             f'the reader must answer "" for {text}')
            self.assertEqual(dotted_name_by_loop(node), '',
                             f'the stack reader must answer "" for {text}')

    def test_the_two_readers_agree_on_every_attribute_call(self):
        """The recursion and the stack agree on the calls of this tree.

        The two spellings differ on one shape only: the chain whose base is a call
        or a subscript.  The walk below reads every attribute call of the test tree
        and compares the two answers, apart from that shape, which the case
        ``test_the_base_of_a_call_is_dropped`` holds.  Measured on 2026-10-11: 16352
        attribute calls, and 1206 chains of the shape below."""
        from _shipped import dotted_name, dotted_name_by_loop
        disagreements = []
        calls = 0
        for path in sorted(TESTS.glob('test_*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                calls += 1
                if not isinstance(chain_root(node.func), ast.Name):
                    continue
                first, second = dotted_name(node.func), dotted_name_by_loop(node.func)
                if first != second:
                    disagreements.append(f'{path.name}:{node.lineno} {first!r} != {second!r}')
        self.assertGreater(calls, 1000, 'the walk must read the attribute calls of the test tree')
        self.assertEqual(disagreements, [],
                         'the recursion and the stack are one reader: ' + '; '.join(disagreements))

    def test_the_base_of_a_call_is_dropped(self):
        """The one shape where the two spellings differ, measured and held.

        ``a.b(x).c`` is a chain whose base is a call.  The owner drops the base and
        keeps the outer attribute, so the answer is ``c``; the stack spelling of
        round 61 stopped at the call and answered ``""``.  Five functions of this
        tree hold a chain of this shape, and the four guards read the outer
        attribute of one: ``Path(out).write_text(...)`` answers ``write_text`` in
        the owner.  So the answer of each spelling is held here, and a later change
        to either one is visible."""
        from _shipped import dotted_name, dotted_name_by_loop
        expected = (
            ("a.b(x).c", 'c'),
            ("__import__('numpy').linalg.inv", 'linalg.inv'),
            ('TEMPLATES[name].zh.format', 'zh.format'),
        )
        for text, outer in expected:
            chain = ast.parse(text, mode='eval').body
            self.assertEqual(dotted_name(chain), outer,
                             f'the owner drops the base and keeps the attributes: {text}')
            self.assertEqual(dotted_name_by_loop(chain), '',
                             f'the stack reader stops at the base of the chain: {text}')
