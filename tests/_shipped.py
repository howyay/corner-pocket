"""The three readers the test tree shares: the shipped package tree, a dotted name,
and the string literals of a tree.

Round 61 measured two duplications in this tree, and round 69 measured a third.

1. The package tree this repository ships was declared four times by hand, in
   four orders and two quoting styles: ``tests/test_shot_clock.py``,
   ``tests/test_sql_domain_parity.py``, ``tests/test_store_files.py`` and
   ``tests/test_tls_trust.py``.  The scanner over it stood twice, at
   ``tests/test_shot_clock.py`` and ``tests/test_store_files.py``.  A package
   added to one copy alone changed what one guard scans, and the other three
   guards kept the old scope in silence.

2. The reader of a dotted name stood four times: ``tests/test_atomic_write.py``,
   ``tests/test_events_document.py``, ``tests/test_one_atomic_write.py`` and
   ``tests/test_sam3_artifact.py``.  Three of the four bodies were the recursion
   below; the fourth walked the same chain with a stack.

3. The reader of the string literals of a tree stood twice, and the two bodies were
   one body: ``tests/test_events_document.py`` and ``tests/test_sam3_artifact.py``.
   A change to the docstring rule of one copy alone left the other copy reading an
   old rule.

All three readers have one home here.  The four guards of the package tree read
``SHIPPED`` and ``shipped_modules`` from this module, the four guards of the
dotted name read ``dotted_name`` from it, and the two guards of the string
literals read ``code_strings`` from it.  Each caller keeps its own scope: it
adds the file kinds and the exclusions its own rule needs.

Two later rounds moved the helper families of this tree into the same home: the
eight readers of round 72 (``parse``, ``is_number``, ``is_length``,
``stated_maximum``, ``bare_bounds``, ``bindings``, ``owner_bindings``,
``body_fingerprint``), and the two loopback-port helpers of round 79
(``free_port``, ``port_is_free``).

``tests/test_duplicate_bodies.py`` cannot see any of the three duplications: it
reads the source trees of ``src/`` and ``annotator/`` only.  The guard of this
rule is ``tests/test_one_shipped_tree.py``, which walks ``tests/*.py``.

The name starts with an underscore on purpose.  Discovery reads ``test_*.py``
files only, so this module is a helper and not a suite.

Run: ``./scripts/pool-test.sh python test_one_shipped_tree``
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import socket

#: Name of this module, as the walk of the guard reads it.
SELF = Path(__file__).stem

#: The repository root, from this file's own path.
ROOT = Path(__file__).resolve().parents[1]

#: The four first-party python packages this repository ships, in one order for
#: every guard.  The suite is not shipped code: a test that states an expectation
#: is an expectation, and not a second copy inside the application.
SHIPPED = ('src', 'annotator', 'tools', 'scripts')


def shipped_modules() -> list[Path]:
    """Every .py file of the shipped packages, generated trees left out.

    The answer is sorted, so the order of ``SHIPPED`` changes no result.  A
    caller that needs one package only adds the package to ``SHIPPED`` in the
    call site: one scope stays one scope."""
    return sorted(path for name in SHIPPED for path in (ROOT / name).rglob('*.py')
                  if '__pycache__' not in path.parts)


def code_strings(tree: ast.AST) -> list:
    """(line, text) for every string literal of a tree that is not a docstring.

    Round 69 found this body twice, byte for byte, at
    ``tests/test_events_document.py`` and ``tests/test_sam3_artifact.py``.  Both
    callers read the literals of a source module and compare them with a list of
    paths they own, so both of them read this answer and nothing else.

    A docstring is the first statement of a module, a class or a function, and it
    is a constant of type ``str`` like any other literal.  The set below holds the
    identity of each one, so the answer drops them.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def dotted_name(node: ast.AST) -> str:
    """The dotted name of an expression, or "" for any other expression.

    One rule for the four guards: the chain of attributes over one plain name, for
    example ``json.dump`` over the name ``json``.  A base that has no name of its
    own - a call, a subscript - is dropped, and the reader keeps the attribute the
    chain names.  So ``Path(out).write_text`` answers ``write_text``, which is the
    name the scans of the guards read.  The four original bodies of this reader
    answered exactly this text, and the case below holds it.
    """
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f'{base}.{node.attr}' if base else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ''


def dotted_name_by_loop(node: ast.AST) -> str:
    """The same rule as ``dotted_name``, built with a stack and not with a call.

    Round 61 found this spelling at ``tests/test_one_atomic_write.py``, and it
    differs from the other three on one chain.  A chain whose base is a call or a
    subscript answers ``""`` here, and answers the outer attribute in the owner:
    ``a.b(x).c`` gives ``""`` here and ``c`` there.  The walk of the two spellings
    over the test tree measured 16352 attribute calls and 1206 such chains, and
    five cases of the tree hold a chain of the second shape.  The case
    ``test_the_two_readers_agree_on_every_attribute_call`` holds the chains where
    the two agree, and ``test_the_base_of_a_call_is_dropped`` holds the one shape
    where they differ, so a later change to either reader is visible."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ''
    parts.append(node.id)
    return '.'.join(reversed(parts))


# The nine readers below stood in two or three test modules at once, with no
# declared owner.  Round 72 measured six such bodies on 2026-10-11.  The former
# sites are named below by file, because the round removed the definitions and a
# line number would name a different line today:
#
# 1. ``bare_bounds``, at ``tests/test_note_limit.py`` and
#    ``tests/test_guest_name.py`` (body key a9fcea4d9e9c), with the four
#    supports ``parse`` (key 539c148d3ed7), ``is_number`` (38a3d55cf629),
#    ``is_length`` (658d8d8f6b14) and ``stated_maximum`` (b4fba3e5a7e3);
# 2. ``bindings`` at ``tests/test_ball_scale.py`` and ``owner_bindings`` at
#    ``tests/test_guest_name.py``, one body under two names (30a0d7325c52);
# 3. ``body_fingerprint`` three times, at ``tests/test_duplicate_bodies.py``,
#    ``tests/test_stats.py`` and ``tests/test_box_geometry.py`` (54206cd85fb9),
#    and each copy named the other two in its docstring.
#
# A body belongs here when it reads its arguments and the standard library
# only.  ``source_files`` of ``tests/test_ball_scale.py:116`` and
# ``tests/test_guest_name.py:84`` reads a module-local ``SOURCE_TREES``, so the
# scope of that tree belongs to the module that states it and not to this home.
# The guard ``tests/test_one_shipped_tree.py`` reads every name below.
#
# The walk that measured the keys removes the docstring of a function, unparses
# the statements that remain and hashes them, as ``body_fingerprint`` does.  The
# same walk measured 53 bodies in two or more test modules, so the guard watches
# these names and not every duplicate body: a ``setUp`` or a fake of two modules
# is a local shape and not a shared reader.


def parse(path):
    """The syntax tree of one module."""
    return ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))


def is_number(node, value):
    """True when one node is the integer literal of one value."""
    return isinstance(node, ast.Constant) and type(node.value) is int and node.value == value


def is_length(node):
    """True when one node is a ``len(...)`` call."""
    return isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'len'


def stated_maximum(call):
    """The maximum one ``text(...)`` call states, as a node, or None for the default."""
    stated = list(call.args[2:3]) + [word.value for word in call.keywords
                                     if word.arg == 'maximum']
    return stated[0] if stated else None


def bare_bounds(path, limit):
    """Every site of one module that bounds a value with the bare number ``limit``.

    Two shapes are a bound: a comparison of a ``len(...)`` call with the number,
    and a ``text(...)`` call whose maximum is the number.  A reader that imports
    the owner is not such a site: that site holds a name, not a number.
    """
    found = []
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Compare):
            operands = [node.left] + list(node.comparators)
            if any(is_length(operand) for operand in operands):
                if any(is_number(operand, limit) for operand in operands):
                    found.append((node.lineno, ast.unparse(node)))
        elif isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'text':
            stated = stated_maximum(node)
            if stated is not None and is_number(stated, limit):
                found.append((node.lineno, ast.unparse(node)))
    return found


def bindings(path):
    """Every site in one module that binds a name, with the line, the name and the value."""
    found = []
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found.append((node.lineno, target.id, value))
    return found


def owner_bindings(path):
    """The binding walk under the name of the second former site.

    ``tests/test_guest_name.py`` held the body of ``bindings`` under this name.
    One body, so one function, and this name is the alias of it.
    """
    return bindings(path)


def body_fingerprint(node):
    """The sha1 of one function's statements, with its docstring and layout removed.

    A docstring names the body; it is not the body.  ``ast.unparse`` writes the
    statements back in one shape, so two copies that differ only in spacing, in a
    comment or in the name of a local hash the same, and two bodies that differ
    in one name or one term hash apart.  Three test modules wrote this walk
    before round 72: ``tests/test_duplicate_bodies.py``, ``tests/test_stats.py``
    and ``tests/test_box_geometry.py``.
    """
    body = list(node.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return hashlib.sha1(ast.unparse(body).encode('utf-8')).hexdigest()


# Round 79 gave the two loopback-port helpers of the console fixtures one home.
# ``free_port`` stood at ``tests/console_fixture_build.py:77`` and
# ``tests/console_shots.py:117``.  ``port_is_free`` stood at those two modules and
# at ``tests/smoke_rating_fixture.py:100``.  Every copy held the same body, so a
# change to one copy changed one caller and left the others on the old rule.  The
# three fixture modules read the two names from this module now.
#
# ``tests/test_one_shipped_tree.py`` holds the rule with a body walk: it reads
# every ``tests/*.py`` file and reports a site whose body matches one of the two
# bodies below.  A definition of the same name with another body is a different
# reader: ``free_port`` of ``tests/test_public_board.py:285`` binds its socket
# under the local name ``sock``, so it stays the reader of that module.


def free_port():
    """One free loopback port, as the kernel hands it out."""
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def port_is_free(port):
    """True when the loopback port can be bound right now."""
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True
