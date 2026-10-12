"""One owner for a served pot's reason: the gate answers it, the queue repeats it.

Round 81.  The served pot's code list opened with
`codes = ["cloth_occluded_at_disappearance"]` (src/dense_queue.py:247 at HEAD
3f0b9a7d6e0da2ba04414d621482ee35fba3e92c) -- the answer for *one* of the
situations the gate can report, handed to every pot the queue served -- while
src/shot_pot_gate.py:1515-1517 computed the pot's real reason and shipped it as
`gate.pots[i].reason`.  annotator/vision-stage.js turns that code into a sentence,
so the queue answering for the gate told the operator "a person covered the cloth
when the ball vanished" for a ball whose occlusion channel was merely silent.  The
probe over the tests/test_queue_decision.py fixture row (only `reason` varied)
printed the cloth code as the first served code all four times while
`provenance.gate_reason` held the input.

What this module holds:

* **the gate owns the vocabulary.**  It is derived here from the gate's own
  `PotEvent(...)` calls -- the reason argument, following the one name they pass --
  so a reason the gate learns to produce enters this guard the moment it can.
  Nothing in this file lists the vocabulary by hand;
* **src/dense_queue.py spells none of it.**  The queue repeats
  `gate.pots[i].reason`; it does not answer the question, and it does not branch on
  the vocabulary either;
* **the served code and the provenance are one read.**  `gate.codes[0]` is
  `provenance.gate_reason`, for every pot the queue serves.

Both walks are checked against planted copies -- the removed line put back
(PlantReportedCopies) and a varied reason driven through a real gate artifact
(TheServedCodeIsTheGatesReason) -- so a guard that stopped looking fails instead of
passing quietly.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GATE = ROOT / "src" / "shot_pot_gate.py"
QUEUE = ROOT / "src" / "dense_queue.py"
#: The run src/dense_queue.py's own docstring names as its input.
GATE_ARTIFACT = ROOT / "out" / "dense-events" / "segment-1350-1650.gate2.json"

#: A reason code, not a sentence (the shape tests/test_console_reason_table.py reads).
CODE = re.compile(r"^[a-z][a-z0-9_]*$")

#: The line round 81 removed.  If it comes back, the walk has to say so.
HOUSE_DEFAULT = 'codes = ["cloth_occluded_at_disappearance"]'


def _call_name(func) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _assigned_values(tree: ast.AST) -> dict:
    """name -> every value this module or function assigns to it."""
    names: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value, targets = node.value, node.targets
        elif isinstance(node, ast.AnnAssign):
            value, targets = node.value, [node.target]
        else:
            continue
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                names.setdefault(target.id, []).append(value)
    return names


def _strings(node: ast.AST, assigned: dict, depth: int = 3) -> set:
    """Every string constant this expression can take, following one name hop.

    A reason is a literal, a chain of conditional expressions over literals, or a name
    holding one of those (src/shot_pot_gate.py:1515 assigns the ternary to `reason` and
    hands the name to PotEvent at :1518).  The expression's own structure is followed
    all the way down -- the depth counts *name hops*, not nesting, so a conditional
    inside a conditional keeps every branch -- and a sentence is a string too, so the
    caller filters with CODE.
    """
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.IfExp):
        return (_strings(node.body, assigned, depth)
                | _strings(node.orelse, assigned, depth))
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out: set = set()
        for element in node.elts:
            out |= _strings(element, assigned, depth)
        return out
    if isinstance(node, ast.BoolOp):
        out = set()
        for value in node.values:
            out |= _strings(value, assigned, depth)
        return out
    if isinstance(node, ast.Name):
        if depth <= 0:
            return set()
        out = set()
        for value in assigned.get(node.id, ()):
            out |= _strings(value, assigned, depth - 1)
        return out
    return set()


def _reason_argument(call: ast.Call):
    """The reason a PotEvent call carries: the fourth argument, or the keyword."""
    value = call.args[3] if len(call.args) >= 4 else None
    for keyword in call.keywords:
        if keyword.arg == "reason":
            value = keyword.value
    return value


def gate_pot_reasons(source: str | None = None) -> set:
    """The codes the gate can set as a pot's reason, read out of the gate itself."""
    tree = ast.parse(GATE.read_text() if source is None else source)
    assigned = _assigned_values(tree)
    reasons: set = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node.func) != "PotEvent":
            continue
        value = _reason_argument(node)
        if value is not None:
            reasons |= _strings(value, assigned)
    return {reason for reason in reasons if CODE.match(reason)}


def spell_reports(source: str, vocabulary=None) -> list:
    """The lines of a queue source that spell one of the gate's pot reasons."""
    words = gate_pot_reasons() if vocabulary is None else vocabulary
    reports = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and node.value in words):
            reports.append(
                f"line {node.lineno}: the queue spells the gate's pot reason "
                f"{node.value!r}; a served code must be read from gate.pots[i].reason")
    return reports


class TheGateOwnsTheReasonVocabulary(unittest.TestCase):
    """The vocabulary has one home, and the queue holds no second copy of it."""

    def test_the_gate_vocabulary_is_visible_and_not_empty(self):
        reasons = gate_pot_reasons()
        # The three codes the gate reaches through the name it assigns at
        # src/shot_pot_gate.py:1515: two spellings and the deepest branch of the
        # chain.  Declared here so a walk that lost one cannot pass as complete.
        for reason in ("cloth_occluded_at_disappearance", "occlusion_channel_silent",
                       "pocket_distance_within_uncertainty"):
            self.assertIn(reason, reasons, "the gate's three-way choice must be read whole")
        self.assertGreaterEqual(len(reasons), 4, f"the vocabulary shrank: {sorted(reasons)}")
        for reason in reasons:
            self.assertRegex(reason, CODE, "a reason is a code, not a sentence")

    def test_the_queue_spells_no_pot_reason(self):
        reports = spell_reports(QUEUE.read_text())
        self.assertEqual([], reports, "src/dense_queue.py must repeat the gate's reason:\n"
                                      + "\n".join(reports))

    def test_every_pot_event_names_a_reason_the_walk_can_read(self):
        """A reason this derivation cannot see is a hole in the guard, not a pass."""
        tree = ast.parse(GATE.read_text())
        assigned = _assigned_values(tree)
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and _call_name(node.func) == "PotEvent"]
        self.assertGreaterEqual(len(calls), 4, "the gate shapes pots somewhere, or nothing is checked")
        for call in calls:
            value = _reason_argument(call)
            readable = {reason for reason in _strings(value, assigned) if CODE.match(reason)}
            self.assertTrue(readable,
                            f"src/shot_pot_gate.py:{call.lineno}: this PotEvent's reason is "
                            f"outside the walk's reach, so the vocabulary would miss it")

    def test_a_conditional_inside_a_conditional_keeps_every_branch(self):
        """The gate's own shape (a three-way choice assigned to a name) must come
        out whole; a walk that lost the deepest branch would pass a queue that
        spelled that branch's code, and the whole point is to catch exactly that."""
        source = ('reason = ("cloth_occluded_at_disappearance" if occ == "occluded"\n'
                  '          else "occlusion_channel_silent" if occ == "silent"\n'
                  '          else "pocket_distance_within_uncertainty")\n'
                  'pots.append(PotEvent("pot", ball_id, "unknown", reason, pocket))\n')
        self.assertEqual(
            {"cloth_occluded_at_disappearance", "occlusion_channel_silent",
             "pocket_distance_within_uncertainty"},
            gate_pot_reasons(source))


class PlantReportedCopies(unittest.TestCase):
    """A planted copy is reported, so the walk above cannot pass by looking away."""

    def test_a_planted_house_default_is_reported(self):
        text = QUEUE.read_text()
        planted = text.rstrip("\n") + "\n" + HOUSE_DEFAULT + "\n"
        planted_line = planted.splitlines().index(HOUSE_DEFAULT) + 1
        reports = spell_reports(planted)
        self.assertEqual(1, len(reports), "\n".join(reports))
        self.assertTrue(reports[0].startswith(f"line {planted_line}:"), reports[0])
        self.assertIn("cloth_occluded_at_disappearance", reports[0])

    def test_the_real_queue_source_is_clean(self):
        self.assertEqual([], spell_reports(QUEUE.read_text()))


class TheServedCodeIsTheGatesReason(unittest.TestCase):
    """A pot's code is whatever reason the gate shipped for that ball."""

    def _serve(self, tmp, reason):
        artifact = json.loads(GATE_ARTIFACT.read_text())
        self.assertTrue(artifact["gate"]["pots"], "the artifact must carry a pot")
        for row in artifact["gate"]["pots"]:
            row["reason"] = reason
        probe = Path(tmp) / "artifact.json"
        probe.write_text(json.dumps(artifact))
        from src.dense_queue import build
        build(str(probe), str(Path(tmp) / "events.json"), str(Path(tmp) / "report.json"),
              None, str(Path(tmp) / "retired.json"))
        return json.loads((Path(tmp) / "events.json").read_text())

    def test_a_non_cloth_reason_is_served_as_itself(self):
        if not GATE_ARTIFACT.exists():
            self.fail("no dense gate artifact in this tree; build it before this guard")
        for reason in ("occlusion_channel_silent", "pocket_distance_within_uncertainty"):
            with self.subTest(reason=reason), TemporaryDirectory() as tmp:
                events = self._serve(tmp, reason)
                pots = [event for event in events if event["type"] == "pot"]
                self.assertTrue(pots, "the probe must serve a pot, or it proves nothing")
                for pot in pots:
                    ball_id = pot["provenance"]["ball_id"]
                    self.assertEqual(pot["gate"]["codes"][0], reason,
                                     f"{ball_id} must carry the gate's reason, not a default")
                    self.assertEqual(pot["gate"]["codes"][0], pot["provenance"]["gate_reason"],
                                     f"{ball_id}: the served code and the provenance are one read")
                    self.assertNotIn("cloth_occluded_at_disappearance", pot["gate"]["codes"])

    def test_a_pot_without_a_gate_reason_is_refused(self):
        """The queue has no answer of its own to fall back on: it says so."""
        if not GATE_ARTIFACT.exists():
            self.fail("no dense gate artifact in this tree; build it before this guard")
        artifact = json.loads(GATE_ARTIFACT.read_text())
        for row in artifact["gate"]["pots"]:
            row.pop("reason", None)
        with TemporaryDirectory() as tmp:
            probe = Path(tmp) / "artifact.json"
            probe.write_text(json.dumps(artifact))
            from src.dense_queue import build
            with self.assertRaises(ValueError) as caught:
                build(str(probe), str(Path(tmp) / "events.json"), str(Path(tmp) / "report.json"),
                      None, str(Path(tmp) / "retired.json"))
            self.assertIn("will not answer one itself", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
