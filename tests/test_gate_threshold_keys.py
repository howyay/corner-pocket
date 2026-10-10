"""The gate owns the threshold names that the queue serves.

``src/shot_pot_gate.py`` defines ``GateThresholds`` and three tuples beside it:
``RAIL_THRESHOLD_KEYS``, ``REPORT_EXTRA_THRESHOLD_KEYS`` and
``REPORT_THRESHOLD_KEYS``.  ``src/dense_queue.py`` reads those tuples in
``provenance`` and in ``build``.

Before this contract each consumer spelled the names again as string literals.
A renamed field then made the payload answer ``None``, and no check failed.
Nothing connected the two lists either, so a reader could not say what they were
for.

This module holds four limits:

1. every served name is a field of ``GateThresholds``;
2. the run report serves the rail names plus ``REPORT_EXTRA_THRESHOLD_KEYS``;
3. the two real payloads hold exactly the frozen names, in the frozen order;
4. no string literal in the two consumer functions spells a served name.
   That sweep reads ``src/dense_queue.py`` and names the offending line.

The frozen names below are the contract.  They repeat the owner on purpose: a
dropped name keeps limit 1 and limit 2 true, and only this copy catches it.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import dense_queue  # noqa: E402
from src.shot_pot_gate import (GateThresholds, RAIL_THRESHOLD_KEYS,  # noqa: E402
                               REPORT_EXTRA_THRESHOLD_KEYS, REPORT_THRESHOLD_KEYS)

#: The file the sweep reads.
CONSUMER_FILE = ROOT / "src" / "dense_queue.py"
#: The two functions that serve a threshold payload.  The sweep reads only these.
CONSUMER_FUNCTIONS = ("provenance", "build")
#: The names the rail payload holds, in the order the payload prints them.
EXPECTED_RAIL_NAMES = ("motion_speed_px_s", "pocket_r_mm",
                       "min_net_displacement_diameters", "localisation_error_px")
#: The names the run report holds, in the order the run report prints them.
EXPECTED_REPORT_NAMES = ("min_net_displacement_diameters", "ball_diameter_px",
                         "localisation_error_px", "pocket_r_mm",
                         "motion_speed_px_s", "persistence_s")
#: The reference cloth quad of the dense run, in work-frame pixels.
REFERENCE_QUAD = [[63.0, 62.0], [726.0, 88.0], [717.0, 331.0], [75.0, 340.0]]


def _owner_tuples():
    """The three owner tuples, as the gate writes them."""
    return (tuple(RAIL_THRESHOLD_KEYS), tuple(REPORT_EXTRA_THRESHOLD_KEYS),
            tuple(REPORT_THRESHOLD_KEYS))


def _served_names():
    """Every name the owner serves, with no repeat."""
    names = []
    for owner in _owner_tuples():
        for name in owner:
            if name not in names:
                names.append(name)
    return tuple(names)


def _stub_artifact():
    """A small artifact, made with the real threshold writer, with no events."""
    thresholds = GateThresholds(frame_size=[960, 540], cloth_quad=REFERENCE_QUAD)
    return {"segment": {"start_s": 1350.0, "seconds": 300.0, "frames_decoded": 9000},
            "samples": {"balls": 0}, "tracks": {"n": 0},
            "occlusion": {"source": "test stub"}, "rejection_codes": {},
            "thresholds": thresholds.as_dict(),
            "gate": {"shots": [], "pots": [], "breaks": [],
                     "counts": {"tracks": 0, "rejections": 0, "breaks": 0}}}


class OwnerNames(unittest.TestCase):
    """Limit 1 and limit 2: what the owner says the served names are."""

    def test_every_served_name_is_a_gate_threshold_field(self):
        fields = {item.name for item in dataclasses.fields(GateThresholds)}
        for name in _served_names():
            self.assertIn(name, fields,
                          "%r is served as a threshold but is not a GateThresholds field; "
                          "the payload would print null" % (name,))

    def test_the_owner_holds_every_name_once(self):
        for owner in _owner_tuples():
            self.assertEqual(sorted(owner), sorted(set(owner)),
                             "an owner tuple holds a duplicate threshold name")
        names = _served_names()
        self.assertEqual(sorted(names), sorted(set(names)),
                         "the owner serves a duplicate threshold name")

    def test_the_rail_names_hold_the_frozen_names(self):
        self.assertEqual(tuple(RAIL_THRESHOLD_KEYS), EXPECTED_RAIL_NAMES)

    def test_the_report_names_hold_the_frozen_names(self):
        self.assertEqual(tuple(REPORT_THRESHOLD_KEYS), EXPECTED_REPORT_NAMES)

    def test_the_report_names_are_the_rail_names_plus_the_extras(self):
        rail = set(RAIL_THRESHOLD_KEYS)
        extra = set(REPORT_EXTRA_THRESHOLD_KEYS)
        report = set(REPORT_THRESHOLD_KEYS)
        self.assertTrue(rail.issubset(report),
                        "the run report drops a rail name")
        self.assertEqual(report, rail | extra,
                         "the run report is not the rail names plus the extras")
        self.assertEqual(extra, report - rail,
                         "the extras are not the report names the rail does not serve")


class ConsumerSource(unittest.TestCase):
    """Limit 4: the consumers read the owner, and they do not spell a name."""

    def _consumer_nodes(self):
        tree = ast.parse(CONSUMER_FILE.read_text(encoding="utf-8"),
                         filename=str(CONSUMER_FILE))
        found = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in CONSUMER_FUNCTIONS:
                    found[node.name] = node
        return found

    def test_the_consumer_file_holds_the_two_functions(self):
        found = self._consumer_nodes()
        for name in CONSUMER_FUNCTIONS:
            self.assertIn(name, found,
                          "%s no longer holds %s(); the sweep would read nothing"
                          % (CONSUMER_FILE, name))

    def test_no_consumer_function_spells_a_served_name_as_a_literal(self):
        served = set(_served_names())
        found = self._consumer_nodes()
        offences = []
        for name in CONSUMER_FUNCTIONS:
            node = found.get(name)
            if node is None:
                continue
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                        and sub.value in served):
                    offences.append("%s:%d: %s() spells the served threshold name %r "
                                    "as a literal; import it from src.shot_pot_gate"
                                    % (CONSUMER_FILE, sub.lineno, name, sub.value))
        self.assertEqual([], offences, "\n".join(offences))


class Payloads(unittest.TestCase):
    """Limit 3: the real payloads hold the owner names, in the owner order."""

    def test_the_rail_payload_serves_the_owner_names(self):
        payload = dense_queue.provenance(_stub_artifact(), {"ball_id": "t001-red"})
        served = payload["run"]["gate_thresholds"]
        self.assertEqual(tuple(served), tuple(RAIL_THRESHOLD_KEYS))

    def test_the_run_report_payload_serves_the_owner_names(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            artifact = work / "artifact.json"
            artifact.write_text(json.dumps(_stub_artifact()))
            report = dense_queue.build(str(artifact), str(work / "events.json"),
                                      str(work / "report.json"), None,
                                      str(work / "ledger.json"))
        served = report["generated_from"]["gate_thresholds"]
        self.assertEqual(tuple(served), tuple(REPORT_THRESHOLD_KEYS))

    def test_the_payloads_hold_the_frozen_names(self):
        payload = dense_queue.provenance(_stub_artifact(), {"ball_id": "t001-red"})
        self.assertEqual(tuple(payload["run"]["gate_thresholds"]), EXPECTED_RAIL_NAMES)


if __name__ == "__main__":
    unittest.main()
