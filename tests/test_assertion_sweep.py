"""A guard against an assertion that cannot fail.

An assertion compares two expressions.  When the two expressions have the same
code shape, the comparison answers the same for every input.  The case then
measures nothing, and it hides a behaviour that nobody wrote down.  Round 41
found two sites of this kind in this tree, and both are now fixed.

This module walks the test modules, reads each one with `ast`, and names every
site it finds.  It does not import the test modules.  The walk reads source, so
it costs no import and it cannot be turned green by a run-time skip.

The walk uses the pattern the runner uses, `tests/test_*.py`.  That set is
larger than the tracked set, because it also covers a new module that is not
committed yet.  A module outside the pattern does not run, so it cannot hold a
vacuous case that matters.

The walk compares code shape and not source text.  The same text can carry
different spacing or a different quote mark.  `ast.dump` reads through those
differences, so the guard sees the defect and not the formatting.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
PATTERN = 'test_*.py'

# The two-argument comparisons that say nothing when both sides have one shape.
COMPARISONS = ('assertEqual', 'assertNotEqual', 'assertIs', 'assertIsNot')

# A floor on the walk.  A broken pattern must not report a clean tree.
MIN_MODULES = 60


def _shape(node):
    """The code shape of one expression.  Spacing and quote style do not enter."""
    return ast.dump(node)


def _sites(path):
    """Every site in one module whose two compared expressions have one shape."""
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        if not isinstance(called, ast.Attribute) or called.attr not in COMPARISONS:
            continue
        if len(node.args) < 2:
            continue
        if _shape(node.args[0]) == _shape(node.args[1]):
            found.append((path.name, node.lineno, ast.unparse(node)))
    return found


def _offenders():
    """Every site in the walked set, in module and line order."""
    found = []
    for path in sorted(TESTS.glob(PATTERN)):
        found.extend(_sites(path))
    return found


def _report(offenders):
    """One line per site, so the failure names the file and the line."""
    return '\n'.join(f'tests/{name}:{line}  {text}' for name, line, text in offenders)


class SelfComparisonSweepTest(unittest.TestCase):
    def test_no_assertion_compares_one_expression_with_itself(self):
        offenders = _offenders()
        self.assertEqual(
            [], offenders,
            'these assertions compare one expression with itself, so they hold for every input '
            'and measure nothing. Compare the value with a neighbour entry, with a member of a '
            'known set, or with a measurement from the same data:\n' + _report(offenders))

    def test_the_walk_reaches_the_test_modules(self):
        """A pattern that matches nothing would report a clean tree."""
        modules = sorted(TESTS.glob(PATTERN))
        self.assertGreaterEqual(
            len(modules), MIN_MODULES,
            f'the walk found {len(modules)} test modules under tests/, under the floor of '
            f'{MIN_MODULES}. Check the pattern in tests/test_assertion_sweep.py before you trust a '
            'clean result from the case above.')

    def test_the_walk_parses_this_module(self):
        """The guard reads its own source, so its own assertions stay honest."""
        names = [path.name for path in sorted(TESTS.glob(PATTERN))]
        self.assertIn(Path(__file__).name, names)
