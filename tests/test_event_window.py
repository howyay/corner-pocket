"""The event window has one owner, and every reader of it names that owner.

``src/event_window.py`` holds the three spans a reading around an event time can use:
the served window (1.5 s before, 2.5 s after), the symmetric calibration half (2.5 s)
and the tolerance (0.5 s).  This suite holds the modules that judge such a reading to
that owner: one assignment, no second literal default, and every default that names a
window equal to the owner's value.

The console's own copy of the served span (``annotator/app.js``,
``CLIP_BEFORE_S``/``CLIP_AFTER_S``) is held to the same numbers by
``tests/test_timing_verify.py``, which reads the two names ``src/timing_verify.py``
keeps for it.
"""
from __future__ import annotations

import ast
import inspect
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import eval_events, motion_scan, timing_verify  # noqa: E402
from src import event_window as ew  # noqa: E402

OWNER = "src/event_window.py"
NAMES = ("EVENT_BEFORE_S", "EVENT_AFTER_S", "CONTROL_HALF_S", "AT_TOL_S")
#: The vendored checkouts under `src/` are other people's code, as in
#: `tests/test_ball_gate.py`.
VENDORED = ("reid", "sam3")
#: Modules this change made read the owner.
READERS = ("src/motion_scan.py", "src/timing_verify.py", "src/eval_events.py")
#: Parameter defaults equal to 1.5 or 2.5 that are NOT a window around an event time.
#: Each entry names the decision its number belongs to, so the sweep below can tell a
#: second owner from an unrelated window.  The suite fails when an exemption is no
#: longer needed.
NOT_A_WINDOW = {
    ("src/motion_scan.py", "decay_shape", "window_s"):
        "the span after an onset over which the raw signal's decay is described",
    ("src/ball_association_audit.py", "prediction_residuals", "max_gap_s"):
        "the largest gap two predictions may have and still be paired",
}


def module_files() -> list:
    """Every .py under the four code folders, the vendored checkouts left out."""
    found = []
    for folder in ("annotator", "src", "tools", "scripts"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            if path.relative_to(ROOT / folder).parts[0] in VENDORED:
                continue
            found.append(path)
    return found


def assigned_names(target) -> list:
    """Every plain name an assignment target binds, tuple and list targets included."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for elt in target.elts for name in assigned_names(elt)]
    return []


def window_defaults(path: Path) -> dict:
    """{(module, function, parameter): value} for parameter defaults of 1.5 or 2.5."""
    rel = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text())
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        defaults = [None] * (len(all_args) - len(args.defaults)) + list(args.defaults)
        for arg, default in zip(all_args, defaults):
            if isinstance(default, ast.Constant) and default.value in (1.5, 2.5):
                found[(rel, node.name, arg.arg)] = default.value
    return found


class OneOwnerTests(unittest.TestCase):
    def test_one_module_assigns_the_window_names(self):
        """No second file assigns a window name: the readers import it."""
        owners = set()
        for path in module_files():
            tree = ast.parse(path.read_text())
            for node in tree.body:
                targets = node.targets if isinstance(node, ast.Assign) else (
                    [node.target] if isinstance(node, ast.AnnAssign) else [])
                for target in targets:
                    if set(assigned_names(target)) & set(NAMES):
                        owners.add(path.relative_to(ROOT).as_posix())
        self.assertEqual(sorted(owners), [OWNER])

    def test_every_reader_imports_the_owner(self):
        for rel in READERS:
            source = (ROOT / rel).read_text()
            self.assertIn("src.event_window", source, f"{rel} must read the owner")

    def test_no_module_re_spells_a_window_as_a_parameter_default(self):
        """A second literal default is a second owner, whatever the module intends."""
        found = {}
        for path in module_files():
            found.update(window_defaults(path))
        unexpected = {key: value for key, value in found.items() if key not in NOT_A_WINDOW}
        self.assertEqual(unexpected, {},
                         "these defaults name a window and must read src/event_window.py")
        self.assertEqual(sorted(found), sorted(NOT_A_WINDOW),
                         "an exemption above is no longer needed")

    def test_no_reader_writes_a_window_number_in_a_cli_default(self):
        for rel in READERS:
            source = (ROOT / rel).read_text()
            hits = re.findall(r"default\s*=\s*(?:1\.5|2\.5)\b", source)
            self.assertEqual(hits, [], f"{rel} must state its CLI window defaults as names")

    def test_every_default_that_names_a_window_reads_the_owner(self):
        cases = [
            (motion_scan.sample_window, "before", ew.EVENT_BEFORE_S),
            (motion_scan.sample_window, "after", ew.EVENT_AFTER_S),
            (motion_scan.window_profile, "before", ew.EVENT_BEFORE_S),
            (motion_scan.window_profile, "after", ew.EVENT_AFTER_S),
            (motion_scan.window_profile, "at_tol_s", ew.AT_TOL_S),
            (motion_scan.window_bounds, "half_s", ew.CONTROL_HALF_S),
            (motion_scan.noise_floor, "half_s", ew.CONTROL_HALF_S),
            (motion_scan.calibrate, "half_s", ew.CONTROL_HALF_S),
            (timing_verify.sample_window, "before", ew.EVENT_BEFORE_S),
            (timing_verify.sample_window, "after", ew.EVENT_AFTER_S),
            (timing_verify.spread_controls, "before", ew.EVENT_BEFORE_S),
            (timing_verify.spread_controls, "after", ew.EVENT_AFTER_S),
            (timing_verify.analyze, "before", ew.EVENT_BEFORE_S),
            (timing_verify.analyze, "after", ew.EVENT_AFTER_S),
        ]
        for func, arg, want in cases:
            got = inspect.signature(func).parameters[arg].default
            self.assertEqual(got, want,
                             f"{func.__module__}.{func.__name__}({arg}=) must be the owner's value")

    def test_the_two_readers_that_keep_their_names_read_the_owner(self):
        self.assertEqual((timing_verify.CLIP_BEFORE_S, timing_verify.CLIP_AFTER_S),
                         (ew.EVENT_BEFORE_S, ew.EVENT_AFTER_S))
        self.assertEqual(timing_verify.MOTION_AT_SERVED_S, ew.AT_TOL_S)
        self.assertEqual((eval_events.POT_PRE_S, eval_events.POT_POST_S),
                         (ew.EVENT_BEFORE_S, ew.EVENT_AFTER_S))
        self.assertEqual(motion_scan.AT_TOL_S, ew.AT_TOL_S)


class TheThreeSensesTests(unittest.TestCase):
    def test_the_served_window_is_asymmetric(self):
        self.assertEqual(ew.EVENT_BEFORE_S, 1.5)
        self.assertEqual(ew.EVENT_AFTER_S, 2.5)
        self.assertEqual(ew.EVENT_BEFORE_S + ew.EVENT_AFTER_S, 4.0)

    def test_the_calibration_half_is_symmetric_and_wider(self):
        self.assertEqual(ew.CONTROL_HALF_S, 2.5)
        self.assertEqual(2 * ew.CONTROL_HALF_S, 5.0)
        self.assertNotEqual(2 * ew.CONTROL_HALF_S, ew.EVENT_BEFORE_S + ew.EVENT_AFTER_S)

    def test_the_two_2_5_s_values_are_one_number_and_two_decisions(self):
        """The owner says the equal values are a coincidence, so nobody merges them."""
        self.assertEqual(ew.CONTROL_HALF_S, ew.EVENT_AFTER_S)
        self.assertIn("coincidence", ew.__doc__)

    def test_the_tolerance_is_not_a_window(self):
        self.assertEqual(ew.AT_TOL_S, 0.5)
        self.assertLess(ew.AT_TOL_S, ew.EVENT_AFTER_S)

    def test_the_owner_records_the_repair_and_the_sites_it_does_not_own(self):
        doc = ew.__doc__
        for needle in ("b87e47e", "judge_window", "annotator/unified_server.py",
                       "--event-half-s", "decay_shape", "prediction_residuals"):
            self.assertIn(needle, doc, f"the owner must record {needle}")


if __name__ == "__main__":
    unittest.main()
