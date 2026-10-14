"""The SAM3 ball text prompt has one owner, and every site reads it.

`src/weight_pins.py` owns the SAM3 ball text prompt.  The prompt is the
open-vocabulary text that tells SAM3 which instances to return.  Before round
102, eleven sites in nine shipped modules spelled the string `billiard ball`.
No module owned the string, and no case read it.  One edit to one copy made one
module select another instance set, and no case failed.

The string now stands once, as `SAM3_BALL_PROMPT` in `src/weight_pins.py`.  Every
site reads that name.

This module states three rules:

* every site that states the prompt holds the owner value;
* no shipped module spells the prompt string outside the owner;
* the owner value is the measured string of round 102.

The scan reads the four shipped packages through `SHIPPED`.  It reads the
argument of a `set_text_prompt` call: the keyword `prompt` when it stands there,
and the first positional argument when it does not.  It reads the `default`
argument of an `add_argument` call for the flag `--prompt`.  The vendored SAM3
source under `src/sam3/` is not our code, so the scan skips it.

A scan that finds nothing is green, and a broken scan finds nothing.  Three
cases feed small sources to the same scan: a planted literal, a planted default
of the prompt flag, and a clean reader of the owner.  One case states the
measured ground of the eleven sites, so the green run has a meaning.

Run: ``./scripts/pool-test.sh python test_sam3_prompt_owner``
"""
import ast
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _shipped import SHIPPED, shipped_modules  # noqa: E402
from src import weight_pins  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
#: The one file that may state the prompt string.
OWNER = ROOT / "src" / "weight_pins.py"
#: Vendored upstream code, not ours to change.  One exclusion, one tree.
VENDORED = ROOT / "src" / "sam3"
#: The owner name that every site reads.
OWNER_NAME = "SAM3_BALL_PROMPT"
#: The name of the SAM3 call that takes the prompt.
PROMPT_CALL = "set_text_prompt"
#: The command-line flag that carries the prompt in `src/multiplex_demo.py`.
PROMPT_FLAG = "--prompt"

#: The prompt as round 102 measured it at the eleven sites.  The owner holds this
#: string, and every site reads the owner.  A change to the owner value alone is a
#: change to the class of every mask the ball paths write, so this case fails.
DOCUMENTED_PROMPT = "billiard ball"

#: The measured ground of round 102: each site that states the prompt, by path and
#: line.  `src/fast_ball_labels.py` holds two sites, and `src/sam3_ball_cache.py`
#: holds two, so eleven sites stand in nine files.  Round 105 added a three-line
#: import above the sites of `src/ball_fp_audit.py` and `src/fast_ball_labels.py`,
#: so the round moved those three numbers by +3.
SITES = (
    ("src/ball_fp_audit.py", 578),
    ("src/collect2.py", 47),
    ("src/fast_ball_labels.py", 233),
    ("src/fast_ball_labels.py", 239),
    ("src/frame_inference.py", 225),
    ("src/multiplex_demo.py", 159),
    ("src/pipeline.py", 270),
    ("src/recut_crops.py", 96),
    ("src/sam3_ball_cache.py", 172),
    ("src/sam3_ball_cache.py", 260),
    ("src/scan_events.py", 153),
)


def _literal(node):
    """The text of a string constant, or None for any other node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _name(node):
    """The dotted name of a Name or an Attribute node, or None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _name(node.value)
        return f"{head}.{node.attr}" if head else node.attr
    return None


def _value(node):
    """How one argument states the prompt: (kind, stated value).

    Three kinds reach this scan: `literal` for a string, `name` for a name, and
    `other` for an expression that states neither.
    """
    text = _literal(node)
    if text is not None:
        return ("literal", text)
    name = _name(node)
    if name is not None:
        return ("name", name)
    return ("other", "")


def _reads_the_owner_name(stated):
    """True when a name reaches the owner constant."""
    return stated == OWNER_NAME or stated.endswith("." + OWNER_NAME)


def _prompt_arguments(call):
    """The arguments of one call that state the prompt, as a list.

    A `set_text_prompt` call states the prompt in its `prompt` keyword, or in its
    first positional argument when the keyword does not stand there.
    """
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == PROMPT_CALL):
        return []
    for keyword in call.keywords:
        if keyword.arg == "prompt":
            return [keyword.value]
    return call.args[:1]


def _prompt_defaults(call):
    """The `default` of an `add_argument` call for the prompt flag, as a list."""
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "add_argument"):
        return []
    flags = [text for text in (_literal(arg) for arg in call.args) if text is not None]
    if PROMPT_FLAG not in flags:
        return []
    for keyword in call.keywords:
        if keyword.arg == "default":
            return [keyword.value]
    return []


def prompt_sites(source):
    """Every site of `source` that states the prompt.

    One site is a tuple of the line number, the text of that line, and the value
    that the site states.
    """
    lines = source.splitlines()
    sites = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        for argument in _prompt_arguments(node) + _prompt_defaults(node):
            line = lines[argument.lineno - 1].strip()
            sites.append((argument.lineno, line, _value(argument)))
    sites.sort()
    return sites


def _reason(value, owner_value):
    """Why one site does not hold the owner value, or None when it does."""
    kind, stated = value
    if kind == "literal":
        if stated == owner_value:
            return None
        return f"the literal {stated!r} is not the owner value {owner_value!r}"
    if kind == "name":
        if _reads_the_owner_name(stated):
            return None
        return f"the name {stated} is not {OWNER_NAME}"
    return f"the argument states no literal and no name"


def report(name, source_or_sites, owner_value):
    """The offender lines of one file, as "path:line (text): reason"."""
    sites = source_or_sites if isinstance(source_or_sites, list) else prompt_sites(source_or_sites)
    offenders = []
    for line, text, value in sites:
        reason = _reason(value, owner_value)
        if reason:
            offenders.append(f"{name}:{line} ({text}): {reason}")
    return offenders


def _shipped_sites():
    """The prompt sites of the shipped tree, as (path, line, text, value)."""
    sites = []
    for path in shipped_modules():
        if VENDORED in path.parents:
            continue
        name = path.relative_to(ROOT).as_posix()
        for line, text, value in prompt_sites(path.read_text(encoding="utf-8")):
            sites.append((name, line, text, value))
    sites.sort()
    return sites


class ScanTest(unittest.TestCase):
    def test_the_scan_finds_the_eleven_measured_sites(self):
        """The prompt stands at eleven sites of nine shipped files.

        The scan finds the real prompt, because a scan that finds nothing would
        pass every other case of this module without a meaning.
        """
        sites = _shipped_sites()
        found = [(name, line) for name, line, _text, _value_ in sites]
        self.assertGreaterEqual(
            len(sites), len(SITES),
            f"the scan found {len(sites)} prompt sites, and round 102 measured "
            f"{len(SITES)}: {found}. A scan that finds no site must not pass.")
        self.assertEqual(
            found, list(SITES),
            f"the scan found {len(sites)} prompt sites at {found}, and the measured "
            f"ground of round 102 is {list(SITES)}.")

    def test_every_site_holds_the_owner_value(self):
        """Eleven copies made eleven owners.  One name makes one owner."""
        owner_value = weight_pins.SAM3_BALL_PROMPT
        offenders = []
        for path in shipped_modules():
            if VENDORED in path.parents:
                continue
            name = path.relative_to(ROOT).as_posix()
            offenders += report(name, path.read_text(encoding="utf-8"), owner_value)
        self.assertEqual(
            offenders, [],
            f"every prompt site must read {OWNER_NAME}, and {len(offenders)} site(s) "
            f"do not: " + "; ".join(offenders))

    def test_no_shipped_module_spells_the_prompt_outside_the_owner(self):
        """A string literal outside the owner is a second owner of the fact."""
        owner_value = weight_pins.SAM3_BALL_PROMPT
        copies = []
        for path in shipped_modules():
            if VENDORED in path.parents or path == OWNER:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if _literal(node) == owner_value:
                    copies.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
        self.assertEqual(
            copies, [],
            f"the prompt {owner_value!r} stands in {len(copies)} code string(s) outside "
            f"the owner: {', '.join(copies) or 'none'}. It must stand in "
            f"{OWNER.relative_to(ROOT)} alone.")

    def test_the_owner_holds_the_measured_prompt(self):
        """One edit to the owner moves every path, so the value needs the ground."""
        sites = _shipped_sites()
        where = ", ".join(f"{name}:{line}" for name, line, _text, _value_ in sites)
        self.assertEqual(
            weight_pins.SAM3_BALL_PROMPT, DOCUMENTED_PROMPT,
            f"round 102 measured the prompt {DOCUMENTED_PROMPT!r}; "
            f"{OWNER.relative_to(ROOT)} states {weight_pins.SAM3_BALL_PROMPT!r}, and the "
            f"{len(sites)} site(s) that read that name moved with it: {where}.")

    def test_the_scan_scope_is_the_four_shipped_packages(self):
        """The guard reads the tree that ships, and it does not read the suite."""
        self.assertEqual(SHIPPED, ('src', 'annotator', 'tools', 'scripts'))
        self.assertTrue(shipped_modules(), "the walk of the shipped tree answered nothing.")


class PlantedTest(unittest.TestCase):
    def test_a_planted_literal_is_reported_with_its_line_and_text(self):
        """A site that spells another string is a second owner.  The report names it."""
        planted = weight_pins.SAM3_BALL_PROMPT + "x"
        source = ('def run(proc, state):\n'
                  f'    return proc.set_text_prompt("{planted}", state)\n')
        sites = prompt_sites(source)
        self.assertEqual(len(sites), 1,
                         f"the scan reports one site of the planted source, and it reported "
                         f"{len(sites)}: {sites}.")
        line, text, value = sites[0]
        self.assertEqual(line, 2, f"the planted call stands on line 2, not {line}.")
        self.assertEqual(text, f'return proc.set_text_prompt("{planted}", state)')
        offenders = report("scratch.py", sites, weight_pins.SAM3_BALL_PROMPT)
        self.assertEqual(len(offenders), 1,
                         f"the planted literal is one offender, and the report holds "
                         f"{len(offenders)}: {offenders}.")
        self.assertEqual(
            offenders[0],
            f"scratch.py:2 ({text}): the literal {planted!r} is not the owner "
            f"value {weight_pins.SAM3_BALL_PROMPT!r}")

    def test_a_planted_default_of_the_prompt_flag_is_reported(self):
        """The flag default is a site too.  A copy there moves one path alone."""
        source = ('import argparse\n'
                  'ap = argparse.ArgumentParser()\n'
                  f'ap.add_argument("--prompt", default="{weight_pins.SAM3_BALL_PROMPT}x")\n')
        sites = prompt_sites(source)
        self.assertEqual(len(sites), 1,
                         f"the scan reports the default of the prompt flag, and it reported "
                         f"{len(sites)} site(s): {sites}.")
        offenders = report("scratch.py", sites, weight_pins.SAM3_BALL_PROMPT)
        self.assertEqual(len(offenders), 1, f"the planted default is one offender: {offenders}.")

    def test_a_clean_reader_of_the_owner_is_not_reported(self):
        """A site that reads the owner holds no copy, so the report is empty."""
        source = (f'from src.weight_pins import {OWNER_NAME}\n'
                  'def run(proc, state):\n'
                  f'    return proc.set_text_prompt({OWNER_NAME}, state)\n')
        sites = prompt_sites(source)
        self.assertEqual(len(sites), 1, f"the clean source holds one site: {sites}.")
        self.assertEqual(
            report("scratch.py", sites, weight_pins.SAM3_BALL_PROMPT), [],
            "a reader of the owner holds no copy of the prompt.")
        self.assertEqual(
            report("scratch.py", sites, weight_pins.SAM3_BALL_PROMPT + "x"), [],
            "the owner name reaches the owner value, and the scan reads the name, not "
            "the text beside it.")


if __name__ == "__main__":
    unittest.main()
