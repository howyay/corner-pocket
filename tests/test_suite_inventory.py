"""How much of the python suite this checkout did not run.

`scripts/pool-test.sh python` runs exactly one command, from the repository root:

    PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py'

That command ends in `OK (skipped=NN)` and nothing else.  The number is real, but
no file in the suite says which checks it hid, so a recorded `skipped=` number in
docs/ cannot be audited later.  A case leaves the run in three ways, and only the
first is visible without running the suite:

1. A class or a method carries `@unittest.skip`, `skipIf` or `skipUnless`.  The
   decorator sets `__unittest_skip__` on the class or the function at import
   time, and `TestCase.run` reads exactly that attribute.  Discovery can see
   these: 52 cases here, in 7 modules.
2. The body calls `self.skipTest(...)`.  The decision is a run-time one, so only
   the source site is static: 26 sites in 11 modules.
3. The body calls `tests/data_guard.require` or `require_any`, which raise
   `unittest.SkipTest` naming the absent path: 13 sites in 8 modules.

This module walks the discovered suite once, states all three, and holds four
committed limits so none of them can drift silently:

    MIN_DISCOVERED_CASES      1550   a module that stops being collected shrinks the suite
    MAX_VISIBLE_SKIP_CASES      52   cases carrying __unittest_skip__ in this checkout
    MAX_SKIP_TEST_SITES         26   self.skipTest(...) call sites under tests/
    MAX_REQUIRE_SITES           13   data_guard.require/require_any call sites under tests/

Measured 2026-10-09 on Python 3.14.6 in a checkout that has `data/` and `out/`:
1550 cases in 63 modules, discovery 1.5 s, 52 static skip cases in 7 modules.

The static count is checkout-dependent, and this is the part a recorded
`skipped=` number hides.  With `Path.is_file` and `Path.exists` made to report
every path under `data/` and `out/` as absent, the same tree statically skips
**120** cases: 15 `test_calib_mapping_audit` cases and 49 `test_enroll_from_tracklet`
cases are guarded by artifacts that only exist in this working copy (both trees
are gitignored).  So a fresh clone, or any machine that did not run the media
pipeline, is close to a different suite.  Raise `MAX_VISIBLE_SKIP_CASES` there,
and record the new number in this docstring.

What the walk cannot see, and therefore cannot state:

* a skip a shared helper reaches at run time: one site can skip N cases, and
  `require`/`require_any` sites are counted as sites, not as cases;
* a `SkipTest` raised outside `data_guard` (for example by a library);
* a `subTest` skip: the case still counts as run;
* every condition that is False in this checkout and True in another, which is
  why `MAX_VISIBLE_SKIP_CASES` is a limit for this checkout and not a constant.

Raise a limit only in the same change that raises the measured number, and keep
the reason next to it.  The four checks read one discovery walk, so this module
costs one import pass of the suite - about 1.5 s when it runs alone, and almost
nothing inside a full run, where the modules are already imported.
"""
import ast
import sys
import time
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
PATTERN = 'test_*.py'
SELF = Path(__file__).stem

MIN_DISCOVERED_CASES = 1550
MAX_VISIBLE_SKIP_CASES = 52
MAX_SKIP_TEST_SITES = 26
MAX_REQUIRE_SITES = 13
DISCOVERY_SECONDS_BUDGET = 60.0

_SNAPSHOT = None


def _leaves(suite):
    """Every leaf of a discovered suite, in discovery order."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _leaves(item)
        else:
            yield item


def _holder_types():
    """The two wrappers discovery uses instead of raising on a module it cannot import."""
    loader = getattr(unittest, 'loader', None)
    suite = getattr(unittest, 'suite', None)
    found = (getattr(loader, '_FailedTest', None), getattr(suite, '_ErrorHolder', None))
    return tuple(kind for kind in found if kind is not None)


_HOLDERS = _holder_types()


def _is_holder(case):
    return bool(_HOLDERS) and isinstance(case, _HOLDERS)


def _carries_skip(case):
    """`TestCase.run` skips when the class or the bound method sets __unittest_skip__."""
    if bool(getattr(type(case), '__unittest_skip__', False)):
        return True
    name = getattr(case, '_testMethodName', None) or ''
    return bool(getattr(getattr(case, name, None), '__unittest_skip__', False))


def _describe(counter):
    """`name count` pairs, biggest first: the grouping the report needs."""
    pairs = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return ', '.join(f'{name} {count}' for name, count in pairs)


def _guard_names(tree):
    """The local names `data_guard.require`/`require_any` are reachable under in one file."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.asname or a.name for a in node.names if a.name == 'data_guard')
        elif isinstance(node, ast.ImportFrom) and node.module == 'data_guard':
            names.update(a.asname or a.name for a in node.names)
    return names


def _is_guard_call(called, guards):
    if isinstance(called, ast.Attribute):
        return (called.attr in ('require', 'require_any')
                and isinstance(called.value, ast.Name) and called.value.id in guards)
    return isinstance(called, ast.Name) and called.id in guards and called.id in ('require', 'require_any')


def _skip_sites():
    """The run-time-only kinds, counted as source sites in every `tests/*.py`.

    A site is a call, not a case, and this reads source, so it does not depend on
    which artifacts this checkout happens to have.
    """
    skip_test, require = Counter(), Counter()
    for path in sorted(TESTS.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        guards = _guard_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if isinstance(called, ast.Attribute) and called.attr == 'skipTest':
                skip_test[path.name] += 1
            elif _is_guard_call(called, guards):
                require[path.name] += 1
    return skip_test, require


def _shadowed(cases):
    """Cases whose class is not the one its module holds: the module was imported twice."""
    names = set()
    for case in cases:
        owner = sys.modules.get(type(case).__module__)
        bound = getattr(owner, type(case).__name__, None) if owner is not None else None
        if bound is not None and bound is not type(case):
            names.add(f'{type(case).__module__}.{type(case).__name__}')
    return sorted(names)


class _Inventory(object):
    """One discovery walk of the suite, and everything the four checks read from it."""

    def __init__(self, seconds, cases, modules, skipped, skip_test, require, holders, self_cases):
        self.seconds = seconds
        self.cases = cases
        self.modules = modules
        self.skipped = skipped
        self.skip_test = skip_test
        self.require = require
        self.holders = holders
        self.self_cases = self_cases

    def line(self, test_name):
        """One live line per check, shown by the `-v` listing instead of a print call."""
        if test_name == 'test_discovery_walks_the_suite_once':
            return (f'{len(self.cases)} cases in {len(self.modules)} modules, walked in '
                    f'{self.seconds:.2f} s, {len(self.holders)} modules discovery could not import')
        if test_name == 'test_discovered_cases_do_not_shrink':
            return (f'{len(self.cases)} cases discovered (floor {MIN_DISCOVERED_CASES}), this module '
                    f'contributed {self.self_cases} and is excluded')
        if test_name == 'test_static_skip_cases_do_not_grow':
            return (f'{sum(self.skipped.values())} cases carry __unittest_skip__ (limit '
                    f'{MAX_VISIBLE_SKIP_CASES}): {_describe(self.skipped) or "none"}')
        if test_name == 'test_run_time_skip_sites_do_not_grow':
            return (f'{sum(self.skip_test.values())} self.skipTest() sites in {len(self.skip_test)} modules '
                    f'(limit {MAX_SKIP_TEST_SITES}): {_describe(self.skip_test)}; '
                    f'{sum(self.require.values())} require sites (limit {MAX_REQUIRE_SITES})')
        return None


def _measure():
    """Discover the suite as the runner does, walk it once, and count the three kinds."""
    loader = unittest.TestLoader()
    started = time.monotonic()
    suite = loader.discover(str(TESTS), pattern=PATTERN, top_level_dir=str(TESTS))
    seconds = time.monotonic() - started

    cases, modules, skipped = [], Counter(), Counter()
    holders, self_cases = [], 0
    for case in _leaves(suite):
        if _is_holder(case):
            holders.append(str(case).splitlines()[0])
            continue
        module = type(case).__module__.rsplit('.', 1)[-1]
        if module == SELF:
            self_cases += 1
            continue
        cases.append(case)
        modules[module] += 1
        if _carries_skip(case):
            skipped[module] += 1
    skip_test, require = _skip_sites()
    return _Inventory(seconds, cases, modules, skipped, skip_test, require,
                      sorted(holders), self_cases)


class SuiteInventory(unittest.TestCase):
    """One walk of the discovered suite, then four limits on what it left unrun."""

    @classmethod
    def setUpClass(cls):
        global _SNAPSHOT
        if _SNAPSHOT is None:
            _SNAPSHOT = _measure()

    def shortDescription(self):
        """State the live numbers in the `-v` listing, so this module needs no print call."""
        if _SNAPSHOT is None:
            return None
        return _SNAPSHOT.line(self._testMethodName)

    def test_discovery_walks_the_suite_once(self):
        """1 module import pass, and the four checks below read that one walk."""
        snapshot = _SNAPSHOT
        self.assertEqual(
            [], snapshot.holders,
            'discovery could not import these test modules, so this inventory does not describe the '
            'suite the runner would run: ' + '; '.join(snapshot.holders))
        self.assertEqual(
            [], _shadowed(snapshot.cases),
            'these test classes are not the ones their module holds, so a test module was imported '
            'twice and its cases were counted twice')
        self.assertGreaterEqual(
            snapshot.self_cases, 4,
            'the walk did not find the four checks of ' + SELF + ', so the exclusion of this module '
            'from the other three counts is not proven')
        self.assertLess(
            snapshot.seconds, DISCOVERY_SECONDS_BUDGET,
            f'one discovery walk took {snapshot.seconds:.2f} s, over the '
            f'{DISCOVERY_SECONDS_BUDGET:.0f} s budget; it imports every test module, so it should '
            'stay near the measured 1.5 s')

    def test_discovered_cases_do_not_shrink(self):
        """A file that stops being collected shrinks the suite without one failure."""
        snapshot = _SNAPSHOT
        self.assertGreaterEqual(
            len(snapshot.cases), MIN_DISCOVERED_CASES,
            f'the walk found {len(snapshot.cases)} cases in {len(snapshot.modules)} modules, under '
            f'the floor of {MIN_DISCOVERED_CASES}. Discovery stays green when a test file is '
            'renamed, moved or unmatched by the pattern: it simply returns a smaller suite. If the '
            'removal was deliberate, lower MIN_DISCOVERED_CASES in tests/test_suite_inventory.py '
            'and record why; otherwise restore the module.')

    def test_static_skip_cases_do_not_grow(self):
        """The cases the runner will report as skipped without running them."""
        snapshot = _SNAPSHOT
        visible = sum(snapshot.skipped.values())
        self.assertLessEqual(
            visible, MAX_VISIBLE_SKIP_CASES,
            f'{visible} discovered cases carry __unittest_skip__, over the limit of '
            f'{MAX_VISIBLE_SKIP_CASES}, by module: {_describe(snapshot.skipped)}. These cases will '
            'appear as `skipped=` in the runner output without running once. Raise '
            'MAX_VISIBLE_SKIP_CASES in tests/test_suite_inventory.py in the same change and say '
            'why, or remove the decorator. The limit is measured in a checkout that has data/ and '
            'out/: without them this tree statically skips 120 cases.')

    def test_run_time_skip_sites_do_not_grow(self):
        """The skip decisions that only a run reaches, counted as source sites."""
        snapshot = _SNAPSHOT
        kinds = (
            ('self.skipTest() sites', sum(snapshot.skip_test.values()), MAX_SKIP_TEST_SITES,
             snapshot.skip_test),
            ('data_guard.require/require_any sites', sum(snapshot.require.values()),
             MAX_REQUIRE_SITES, snapshot.require),
        )
        for kind, measured, limit, counter in kinds:
            with self.subTest(kind=kind):
                self.assertLessEqual(
                    measured, limit,
                    f'{measured} {kind} under tests/, over the limit of {limit}, in: '
                    f'{_describe(counter)}. Each site is one more branch that can turn a case into '
                    'a skip at run time, and the runner reports the total only as `skipped=`. Raise '
                    'the limit in tests/test_suite_inventory.py in the same change and say why, or '
                    'remove the site.')
