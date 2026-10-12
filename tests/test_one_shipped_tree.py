"""One home for the shipped package tree and for the two test-tree readers.

Round 61 measured two duplications in this tree, and round 69 measured a third,
and none of the three is visible to ``tests/test_duplicate_bodies.py``: that walk
reads the source trees of ``src/`` and ``annotator/`` only.

1. The package tree this repository ships was declared four times by hand, in
   four orders and two quoting styles, and the scanner over it stood twice.
   ``tests/_shipped.py`` is the one home now; the four guards read ``SHIPPED``
   and ``shipped_modules`` from it.

2. The reader of a dotted name stood four times, and the four bodies were not
   one body.  ``tests/_shipped.py`` is the one home now, and the four guards read
   ``dotted_name`` from it.

3. The reader of the string literals of a tree stood twice, at
   ``tests/test_events_document.py`` and ``tests/test_sam3_artifact.py``, and the
   two bodies were one body, byte for byte.  ``tests/_shipped.py`` is the one home
   now, and the two guards read ``code_strings`` from it.

4. Eight helper families of the test tree stood in two or three modules each, byte
   for byte, and none of the copies named an owner.  Round 72 measured them; the
   bodies are ``parse``, ``is_number``, ``is_length``, ``stated_maximum`` and
   ``bare_bounds``, with the two names ``bindings`` and ``owner_bindings`` of one
   body, and ``body_fingerprint``.  ``tests/_shipped.py`` is the one home now, and
   ``HELPER_NAMES`` below is the list.  ``source_files`` stayed in its two modules,
   because it reads a module-local ``SOURCE_TREES`` and not its arguments.

5. Two loopback-port helpers of the console fixtures stood in three modules each,
   byte for byte.  ``free_port`` stood at ``tests/console_fixture_build.py:77`` and
   ``tests/console_shots.py:117``; ``port_is_free`` stood at those two sites and at
   ``tests/smoke_rating_fixture.py:100``.  No one of the three files is a
   ``test_*.py`` file, so the name walk of this guard never read one of them and no
   record row named them.  Round 79 moved both bodies to ``tests/_shipped.py``, and
   the walk of this file reads every ``*.py`` file of ``tests/`` now.

The cases below hold the five homes in place:

* the four modules of the tree read the owner name, and none of them declares
  the tree again;
* no other ``*.py`` file of ``tests/`` defines ``shipped_modules``, ``_dotted`` or
  ``_code_strings``, apart from the module the walk excludes;
* a planted copy, under a name the walk reads, makes the walk report that file;
* the code-string reader drops the docstrings of a tree and keeps every other
  literal, with its line;
* the expressions the guards read keep their one answer, and the recursive
  reader and the stack reader agree on every ``Call`` of the test tree;
* the eight helper families are defined in the one home, and no other ``*.py``
  file of ``tests/`` defines one of them at its top level;
* the two loopback-port helpers of the console fixtures are defined in the one
  home with the body of round 79, no other ``*.py`` file of ``tests/`` holds one of
  those bodies, and the three fixture modules read both names from the home.

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

#: The two modules that held a copy of the code-string reader until round 69, and
#: the name the walk of the guard reads.
CODE_READERS = (
    'test_events_document.py',
    'test_sam3_artifact.py',
)

#: The names with one home.  A ``test_*.py`` file that defines one of these names
#: holds a second copy of a reader, and the walk reports that file.  The last nine
#: names are the helper families of round 72: they stood in two or three test
#: modules each, with no declared owner.  A name of the list may stand in another
#: module with a different body and a different question -- ``bindings(tree)`` of
#: ``tests/test_bound_owner_reads.py:78`` reads module-level and class-level
#: bindings, and ``is_number(node)`` of ``tests/test_playfield_harness.py:48``
#: reads the fallback rate 30 -- so a later copy of those two is a different
#: reader and not a second home of this one.
WATCHED = ('shipped_modules', '_dotted', '_code_strings',
           'parse', 'is_number', 'is_length', 'stated_maximum', 'bare_bounds',
           'bindings', 'owner_bindings', 'body_fingerprint')


#: The nine helper families of round 72 that now have one home.  They read their
#: arguments and the standard library only, so the body is the same reader in
#: every module that needs it.  ``source_files`` of ``tests/test_ball_scale.py``
#: and ``tests/test_guest_name.py`` is **not** in this list: it reads a
#: module-local ``SOURCE_TREES``, so its scope belongs to the module that states
#: it, and the two copies are two answers about two trees.
HELPER_NAMES = ('parse', 'is_number', 'is_length', 'stated_maximum', 'bare_bounds',
                'bindings', 'owner_bindings', 'body_fingerprint')


#: The two loopback-port helpers the three console fixtures shared until round 79.
#: ``free_port`` and ``port_is_free`` stood byte for byte in
#: ``tests/console_fixture_build.py``, ``tests/console_shots.py`` and
#: ``tests/smoke_rating_fixture.py``, and no one of the three files is a
#: ``test_*.py`` file.  The two names are **not** in ``WATCHED``: a name walk would
#: report ``free_port`` of ``tests/test_public_board.py:285``, a different reader
#: whose body binds the socket under the local name ``sock``.  The rule below reads
#: the body of the function and not its name.
PORT_HELPERS = ('free_port', 'port_is_free')

#: The body key of each port helper, measured in round 79 with
#: ``_shipped.body_fingerprint``: the ``ast`` text of the body with the docstring
#: dropped, so the docstrings of the one home do not move the key.  A later change
#: to one of the two bodies re-measures this table.
PORT_KEYS = {
    'free_port': 'ea2100430737a68737f8c81a18206b045f231511',
    'port_is_free': 'c2b7012d76d055967ec4f13dfa659b7c439b32ad',
}

#: The three modules that read the two port helpers from the one home.
PORT_READERS = (
    'console_fixture_build.py',
    'console_shots.py',
    'smoke_rating_fixture.py',
)


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

    The walk reads every ``*.py`` file of the folder, and not the ``test_*.py``
    files only: the two port helpers of round 79 stood in three fixture modules
    that no ``test_*.py`` name reaches.  It leaves the one helper module out.  The
    answer is a mapping: one list of ``file:line`` sites for each watched name.  An
    empty mapping means the watched readers have one home only."""
    found = {}
    for path in sorted(folder.glob('*.py')):
        if path.stem == HELPER:
            continue
        for name, line in function_defs(path):
            if name in WATCHED:
                found.setdefault(name, []).append(f'{path.name}:{line}')
    return found


def port_body_sites(folder: Path):
    """Every site under ``folder`` whose function body is one of the port bodies.

    The walk reads every ``*.py`` file of the folder, and it reads every function of
    every depth, because a second copy may stand in a class or in another function.
    The one helper module is read as well: the answer holds the two sites of the one
    home, and every other site is a second copy of one of the two bodies.  The answer
    maps ``file:line name`` to the name of the body the site matched."""
    from _shipped import body_fingerprint
    keys = {key: name for name, key in PORT_KEYS.items()}
    found = {}
    for path in sorted(folder.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            key = body_fingerprint(node)
            if key in keys:
                found[f'{path.name}:{node.lineno} {node.name}'] = keys[key]
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


def planted_port(path: Path) -> Path:
    """Write one file that holds the body of ``free_port``, under a name the walk reads."""
    path.write_text('"""A second copy of one port helper, for the case below."""\n'
                    '\n'
                    'import socket\n'
                    '\n'
                    'def free_port():\n'
                    '    with socket.socket() as probe:\n'
                    "        probe.bind(('127.0.0.1', 0))\n"
                    '        return probe.getsockname()[1]\n', encoding='utf-8')
    return path


def chain_root(node: ast.AST) -> ast.AST:
    """The last base of an attribute chain: the node below its attributes."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node


class OneHomeTest(unittest.TestCase):
    """The three readers of tests/_shipped.py have one home each."""

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

    def test_the_two_code_readers_import_the_reader(self):
        """Each former site names the owner, and none of them spells the body again."""
        for name in CODE_READERS:
            path = TESTS / name
            self.assertTrue(path.is_file(), f'the reader of the code strings must exist: {path}')
            text = path.read_text(encoding='utf-8')
            self.assertIn(f'from {HELPER} import code_strings', text,
                          f'{name} must read the code strings from {HELPER}.py')
            self.assertNotIn('\ndef _code_strings(', text,
                             f'{name} must not declare the code-string reader a second time')

    def test_the_shared_helpers_have_one_home(self):
        """Every helper family of round 72 is defined here, and nowhere else.

        The nine names below stood in two or three test modules at once until
        round 72, byte for byte in every copy.  The case reads the one home and
        the walk of the test tree: a name the home does not define, or a name a
        ``test_*.py`` file defines at its top level, is a fault of this list.
        """
        defined = {name for name, _line in function_defs(TESTS / f'{HELPER}.py')}
        missing = [name for name in HELPER_NAMES if name not in defined]
        self.assertEqual(missing, [],
                         f'the one home tests/{HELPER}.py must define: {missing}')
        unseen = [name for name in HELPER_NAMES if name not in WATCHED]
        self.assertEqual(unseen, [],
                         f'the walk WATCHED must read every helper family: {unseen}')
        found = {name: sites for name, sites in scanned_nodes(TESTS).items()
                 if name in HELPER_NAMES}
        self.assertEqual(found, {},
                         f'the nine helpers have one home, tests/{HELPER}.py; the walk of '
                         f'tests/*.py found a second definition at: {found}')

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

    def test_the_walk_reports_a_planted_code_reader(self):
        """A planted copy of the code-string reader is reported, with its line."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            planted('_code_strings', root / 'test_planted_code_copy.py')
            found = scanned_nodes(root)
        self.assertEqual(list(found), ['_code_strings'],
                         f'the walk must report the planted name: {found}')
        self.assertEqual(found['_code_strings'], ['test_planted_code_copy.py:4'],
                         f'the walk must report the file and the line of the copy: {found}')

    def test_the_code_reader_drops_docstrings_and_keeps_every_other_literal(self):
        """The one answer of the reader the two code guards depend on.

        The two guards compare each literal with a list of paths they own, so the
        reader answers the value as written and never the text it would format.
        """
        from _shipped import code_strings
        tree = ast.parse('"""Module docs."""\n'
                         'def f():\n'
                         '    """Call docs."""\n'
                         '    return "kept", "out/scan30/kept.json"\n')
        self.assertEqual([line for line, _ in code_strings(tree)], [4, 4],
                         'the answer holds one site for each literal, and no docstring')
        self.assertEqual([text for _, text in code_strings(tree)],
                         ['kept', 'out/scan30/kept.json'],
                         'the two docstrings are dropped, and the values come back as written')

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

    def test_the_two_port_helpers_have_one_home(self):
        """Both port helpers stand in the one home, with the body of round 79.

        The three fixture modules that held a copy are not ``test_*.py`` files, so
        the name walk above never read one of them.  This case reads a body instead:
        the two keys of ``PORT_KEYS`` were measured on those three copies, and a
        ``*.py`` file of ``tests/`` that holds one of the two bodies again is a
        second home of the same rule.  A copy inside the one home is a fault too,
        because a second ``def`` of one name shadows the first.
        """
        from _shipped import body_fingerprint
        home = TESTS / f'{HELPER}.py'
        tree = ast.parse(home.read_text(encoding='utf-8'), filename=str(home))
        seen = {}
        for node in ast.walk(tree):
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name in PORT_HELPERS):
                seen.setdefault(node.name, []).append((node.lineno, body_fingerprint(node)))
        counted = {name: len(sites) for name, sites in seen.items()}
        self.assertEqual(counted, {'free_port': 1, 'port_is_free': 1},
                         f'the one home tests/{HELPER}.py must define each port helper '
                         f'once: {counted}')
        measured = {name: sites[0][1] for name, sites in seen.items()}
        self.assertEqual(measured, PORT_KEYS,
                         f'the one home must hold the two bodies of round 79; re-measure '
                         f'PORT_KEYS against tests/{HELPER}.py: {measured}')
        found = port_body_sites(TESTS)
        allowed = {f'{HELPER}.py:{line} {name}'
                   for name, sites in seen.items() for line, _key in sites}
        extra = {site: key for site, key in found.items() if site not in allowed}
        self.assertEqual(extra, {},
                         f'the two port helpers have one home, tests/{HELPER}.py; the walk '
                         f'of tests/*.py found a second body at: {extra}')

    def test_the_three_fixture_modules_read_the_port_helpers(self):
        """Each former site reads both names from the one home."""
        for name in PORT_READERS:
            path = TESTS / name
            self.assertTrue(path.is_file(), f'the fixture module must exist: {path}')
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            taken = set()
            for node in tree.body:
                if isinstance(node, ast.ImportFrom) and node.module == HELPER:
                    taken |= {alias.name for alias in node.names}
            missing = [helper for helper in PORT_HELPERS if helper not in taken]
            self.assertEqual(missing, [],
                             f'{name} must read {missing} from tests/{HELPER}.py')

    def test_the_body_walk_reports_a_planted_port_copy(self):
        """A planted copy of one port body is reported, with its file and its line.

        The planted file is not named ``test_*.py``: the walk of this rule reads
        every ``*.py`` file, and this case holds that.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            planted_port(root / 'console_planted_copy.py')
            found = port_body_sites(root)
        self.assertEqual(found, {'console_planted_copy.py:5 free_port': 'free_port'},
                         f'the walk must report the planted body, with its line: {found}')
