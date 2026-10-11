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

``tests/test_duplicate_bodies.py`` cannot see any of the three duplications: it
reads the source trees of ``src/`` and ``annotator/`` only.  The guard of this
rule is ``tests/test_one_shipped_tree.py``, which walks ``tests/*.py``.

The name starts with an underscore on purpose.  Discovery reads ``test_*.py``
files only, so this module is a helper and not a suite.

Run: ``./scripts/pool-test.sh python test_one_shipped_tree``
"""
from __future__ import annotations

import ast
from pathlib import Path

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
