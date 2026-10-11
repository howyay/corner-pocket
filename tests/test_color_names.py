"""One home for the detector colour vocabulary, and one reader of it.

Round 56 measured one colour-name rule in two modules.  Each module held its own
copy of the table and its own lookup:

* ``src/ball_census.py COLOR_ALIASES`` and ``src/ball_census.py normalize_color``;
* ``src/event_gates.py COLOR_ALIASES`` and ``src/event_gates.py color_key``.

The two tables held the same two entries, and no test compared them.  A change
to one table then moved one reader only.  The two lookups also answered one
blank input two ways: ``UNKNOWN`` in the census and ``''`` in the gate.

The vocabulary now has one home, ``src/color_names.py``.  That module holds one
table and one canonical function, ``color_key``.  The two callers hold their own
documented step:

* ``src/ball_census.py normalize_color`` answers ``UNKNOWN`` for a blank value;
* ``src/event_gates.py`` reads ``color_key`` directly, and a blank value answers
  ``''``, so two blank values compare equal.

The cases below prove the claim in four ways:

* a walk of the module-level constants of ``src/*.py`` finds the alias table at
  one site only, and that site is the owner module;
* both readers answer from the owner at run time, for a blank value, for
  ``red2``, for ``red1`` and for a name that the table does not hold;
* the walk has a live proof: the case writes a second copy into a temp module
  under ``src/`` and the walk finds that site;
* the blank-value decision of each caller has its own case, so a later edit
  cannot change it in silence.

The two answers of a blank value are the contract that the repair keeps:
``color_key('') == ''`` and ``normalize_color('') == UNKNOWN``.

Run: ``./scripts/pool-test.sh python test_color_names``
"""
from __future__ import annotations

import ast
import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The one module that owns the colour vocabulary.
OWNER = "src/color_names.py"

#: The owner module as a dotted name.
OWNER_MODULE = "src.color_names"

#: The one entry of the vocabulary.  This literal states the rule; it is not a
#: second copy of the table, because this file is not a module of ``src/``.  The
#: case fails when the owner stops holding the red rule.
RED_ENTRIES = {"red1": "red", "red2": "red"}

#: The named module-level constants that the walk of ``src/*.py`` reads.
ALIAS_NAMES = ("COLOR_ALIASES",)

#: One value of each shape, and the answer of each reader.  The census answers a
#: blank value with the name ``UNKNOWN``; the gate answers it with the empty key.
CALLER_CASES = (
    ("", "unknown", ""),
    ("red2", "red", "red"),
    ("red1", "red", "red"),
    ("RED2", "red", "red"),
    ("chartreuse", "chartreuse", "chartreuse"),
)


def module_paths():
    """The module files of ``src/`` in one stable order, with the owner first."""
    paths = sorted((ROOT / "src").glob("*.py"))
    return sorted(paths, key=lambda path: (path.name != Path(OWNER).name, path.name))


def literal_dict(node):
    """The dict of one ``ast.Dict`` node, or None when a value is not a literal."""
    out = {}
    for key, value in zip(node.keys, node.values):
        if not isinstance(key, ast.Constant) or not isinstance(value, ast.Constant):
            return None
        out[key.value] = value.value
    return out


def alias_sites():
    """[(module, line, name, table)] for every named colour table under ``src/``.

    The walk reads the module-level assignments of each module.  One assignment
    counts when its target is a name of ``ALIAS_NAMES`` and its value is a dict
    with literal keys, because the colour vocabulary maps one name to one name.
    """
    found = []
    for path in module_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module = path.relative_to(ROOT).as_posix()
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ALIAS_NAMES:
                    entries = literal_dict(node.value)
                    if entries is not None:
                        found.append((module, node.lineno, target.id, entries))
    return found


def site_listing(sites):
    """The sites of one walk, as ``module:line name``."""
    return ", ".join("%s:%d %s" % (module, line, name) for module, line, name, _ in sites)


def module_of(dotted):
    """One module object, read at run time."""
    return importlib.import_module(dotted)


class AliasTableHomeTests(unittest.TestCase):
    def test_the_alias_table_has_one_site_and_it_is_the_owner(self):
        sites = alias_sites()
        self.assertEqual(1, len(sites),
                         "the colour alias table must stand in one module; the walk found: %s"
                         % (site_listing(sites) or "nowhere"))
        module, line, name, _ = sites[0]
        self.assertEqual(OWNER, module,
                         "the alias table left its owner %s and stands in %s:%d %s"
                         % (OWNER, module, line, name))
        self.assertEqual(("COLOR_ALIASES",), (name,))

    def test_the_owner_holds_the_red_rule(self):
        sites = alias_sites()
        self.assertTrue(sites, "the walk found no colour alias table under src/")
        module, line, name, entries = sites[0]
        for spelling, colour in RED_ENTRIES.items():
            self.assertEqual(colour, entries.get(spelling),
                             "%s:%d %s lost the entry %r" % (module, line, name, spelling))

    def test_the_walk_finds_a_second_copy_planted_in_a_temp_module(self):
        planted = ROOT / "src" / "_color_alias_probe.py"
        planted.write_text('COLOR_ALIASES = {"red2": "red", "red1": "red"}\n',
                           encoding="utf-8")
        try:
            sites = alias_sites()
        finally:
            planted.unlink()
        named = ["%s:%d %s" % (module, line, name) for module, line, name, _ in sites]
        self.assertIn("src/_color_alias_probe.py:1 COLOR_ALIASES", named,
                      "the walk did not see the planted second copy; it found: %s"
                      % (site_listing(sites) or "nowhere"))
        self.assertGreater(len(sites), 1,
                           "a planted second copy must raise the site count")


class ReaderBindingTests(unittest.TestCase):
    def test_each_reader_answers_from_the_owner_function(self):
        owner = module_of(OWNER_MODULE)
        gates = module_of("src.event_gates")
        census = module_of("src.ball_census")
        self.assertIs(owner.color_key, gates.color_key,
                      "src/event_gates.py color_key is not the owner function object")
        for value, census_answer, _ in CALLER_CASES:
            self.assertEqual(census_answer, census.normalize_color(value),
                             "the census answered %r as %r"
                             % (value, census.normalize_color(value)))
        self.assertEqual("src.color_names", gates.color_key.__module__,
                         "the gate key does not come from the owner module")
        self.assertTrue(gates.color_key.__doc__ and "One home" in gates.color_key.__doc__,
                        "the gate key is not the owner function")
        self.assertEqual(RED_ENTRIES,
                         {key: owner.COLOR_ALIASES[key] for key in RED_ENTRIES},
                         "the owner table lost an entry of the red rule")


class CallerAnswerTests(unittest.TestCase):
    def test_the_two_readers_answer_blank_red2_red1_and_an_unknown_name(self):
        census = module_of("src.ball_census")
        gates = module_of("src.event_gates")
        for value, census_answer, gate_answer in CALLER_CASES:
            self.assertEqual(census_answer, census.normalize_color(value),
                             "the census answered %r as %r" % (value, census.normalize_color(value)))
            self.assertEqual(gate_answer, gates.color_key(value),
                             "the gate answered %r as %r" % (value, gates.color_key(value)))

    def test_the_gate_blank_key_compares_equal_to_another_blank_key(self):
        gates = module_of("src.event_gates")
        blank = gates.color_key("")
        self.assertEqual(blank, gates.color_key(None))
        self.assertEqual(blank, gates.color_key("  "))
        self.assertEqual("", blank, "a blank detector value answers the empty key")
        self.assertNotEqual(gates.color_key("white"), blank,
                            "a measured colour key is not the blank key")

    def test_the_census_blank_name_is_the_unknown_name(self):
        census = module_of("src.ball_census")
        self.assertEqual(census.UNKNOWN, census.normalize_color(""))
        self.assertEqual(census.UNKNOWN, census.normalize_color(None))
        self.assertNotEqual(census.UNKNOWN, census.normalize_color("red2"),
                            "a red reading is not the unknown name")
