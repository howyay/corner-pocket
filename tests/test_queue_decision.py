"""The queue decision: what is served, where the evidence lives, what is never written.

The served queue was emptied by owner decision after the motion scan measured
every event as occlusion-explained.  An empty queue is a result, so these tests
pin the parts a reader would otherwise have to trust: the artifacts keep the
events, and no code path writes a human verdict.
"""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]


def _md5(path):
    import hashlib
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


class VerdictFilesAreReadOnly(unittest.TestCase):
    """A verdict file is an input to every report and an output of none."""

    def test_owner_verdicts_reads_without_writing(self):
        from src.eval_events import agreement, owner_verdicts
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotations.json"
            path.write_text(json.dumps({"16": {"verdict": "correct", "note": "kept", "updated_at": 1}}))
            before = _md5(path)
            verdicts = owner_verdicts([path])
            rows = [{"id": 16, "verdict": {"status": "confirmed", "reasons": []}}]
            agreement(rows, verdicts)
            self.assertEqual(_md5(path), before, "reading verdicts must not rewrite the file")
            self.assertEqual(verdicts["16"]["verdict"], "correct")

    def test_a_queue_event_never_carries_an_owner_verdict(self):
        from src.event_gates import dedupe, GateConfig, ShotEvidence, judge
        from src.eval_events import to_queue_event
        claim = {"type": "shot", "t": 483.4, "color": "black",
                 "from_mm": [307.9, 702.8], "to_mm": [321.8, 269.7]}
        group = dedupe([claim], GateConfig())[0]
        evidence = ShotEvidence(available=True, disp_mm=1837, geometry_gap_px=29.0,
                                from_in_cloth_px=34.7, to_in_cloth_px=12.0,
                                start_hits=17, end_hits=7, stable_hits=3, anchor_tries=3)
        group["evidence"] = dict(evidence.__dict__)
        group["verdict"] = judge(group["event"], evidence, GateConfig()).as_dict()
        event = to_queue_event(group, previous_ids={})
        self.assertNotIn("owner_verdict", event)
        self.assertEqual(event["verified"], False)
        # The gate block is the tool's own measurement, never a human label.
        self.assertEqual(event["gate"]["status"], "confirmed")

    def test_the_verdict_paths_are_only_ever_read(self):
        source = (ROOT / "src" / "eval_events.py").read_text()
        for line in source.splitlines():
            if "HUMAN_VERDICT_FILES" in line or "annotations.json" in line:
                for writer in ("write_text", r"open\(.*w", "unlink", "mkdir"):
                    self.assertNotRegex(line, writer,
                                        f"a verdict path must not be written: {line.strip()}")


class QueueArtifactShape(unittest.TestCase):
    """The queue keeps its schema when it is empty, and the evidence stays put."""

    QUEUE = ROOT / "out" / "scan30" / "events.json"

    def test_the_queue_is_a_json_array(self):
        if not self.QUEUE.exists():
            self.skipTest("no queue artifact in this tree")
        events = json.loads(self.QUEUE.read_text())
        self.assertIsInstance(events, list)
        for event in events:
            self.assertIn("id", event)
            self.assertIn("gate", event)

    def test_an_empty_queue_keeps_its_events_in_the_report_artifacts(self):
        if not self.QUEUE.exists():
            self.skipTest("no queue artifact in this tree")
        events = json.loads(self.QUEUE.read_text())
        if events:
            self.skipTest("the queue is not empty in this tree")
        report = ROOT / "out" / "scan30" / "eval_regen.json"
        sidecar = ROOT / "out" / "scan30" / "gate_report.json"
        measured = json.loads(report.read_text()).get("events", []) if report.exists() else []
        not_confirmed = json.loads(sidecar.read_text()).get("not_confirmed", []) if sidecar.exists() else []
        self.assertTrue(measured or not_confirmed,
                        "an empty queue must leave its events in the report artifacts, not delete them")


if __name__ == "__main__":
    unittest.main()


class DenseQueueHonesty(unittest.TestCase):
    """The first queue a human reviews: what it may and may not claim."""

    #: What the queue carried before this gate run: two shots whose moves the new
    #: gate now refuses, and the pot-shaped unknown it keeps.
    PREVIOUS = [{"id": 9001, "type": "shot", "provenance": {"ball_id": "t125-white"}},
                {"id": 9002, "type": "shot", "provenance": {"ball_id": "t193-blue"}},
                {"id": 9003, "type": "shot", "provenance": {"ball_id": "t256-blue"}},
                {"id": 9004, "type": "pot", "provenance": {"ball_id": "t265-blue"}}]

    def _artifact(self, tmp, pot_verdict="unknown"):
        import numpy as np
        quad = np.array([[399.0, 242.25], [600.0, 243.0], [747.75, 426.75], [288.0, 422.25]],
                        float).tolist()
        shot = {"kind": "shot", "ball_id": "t193-blue", "onset_frame_index": 47404,
                "onset_t": 1580.117301, "onset": [579.03, 298.05], "peak_speed_px_s": 491.63,
                "duration_s": 0.733326, "path_length_px": 159.86, "net_displacement_px": 159.1,
                "rest_window_measured_s": 9.73, "ends_in_pocket": False, "end_distance_px": 29.44,
                "group_id": "onset-1",
                "thresholds": {"min_net_displacement_px": 27.6,
                               "min_net_displacement_diameters": 2.0,
                               "net_uncertainty_px": 5.119, "localisation_error_px": 3.62},
                "samples_used": [{"frame_index": 47404, "t": 1580.117301, "x": 579.03, "y": 298.05,
                                  "confidence": 0.8, "occluded": False},
                                 {"frame_index": 47426, "t": 1580.850626, "x": 427.6, "y": 249.24,
                                  "confidence": 0.63, "occluded": False}]}

        def pot(ball_id, **over):
            row = {"kind": "pot", "ball_id": ball_id, "verdict": pot_verdict,
                   "reason": "cloth_occluded_at_disappearance", "pocket": "left-side",
                   "pocket_px": [365.1, 297.22], "radius_px": 14.46, "radius_mm": 100.0,
                   "distance_px": 9.62, "distance_mm": 148.48, "distance_mm_uncertainty": 54.11,
                   "verdict_mm": "ambiguous", "inside_px": True, "inside_mm": False,
                   "pocket_test": "mm", "pocket_test_disagrees_px_vs_mm": True,
                   "last_frame_index": 49156, "last_t": 1638.516708, "last": [368.3, 306.3],
                   "last_speed_px_s": 734.15, "gap_s": 11.43, "persistence_s": 1.0,
                   "occlusion_status": "occluded", "identity_swap_suspected": False,
                   "parked_in_jaws_possible": False,
                   "thresholds": {"pocket_r_mm": 100.0, "occlusion_threshold": 0.3},
                   "samples_used": [{"frame_index": 49156, "t": 1638.516708, "x": 368.3, "y": 306.3,
                                     "confidence": 0.55, "occluded": False}]}
            row.update(over)
            return row

        # An occluded unknown that was still moving (never carded), one that was
        # parked (never carded), and one the queue already carried.
        parked = pot("t170-black", last_t=1497.184809, last=[500.0, 300.0],
                     distance_mm=128.07, distance_mm_uncertainty=45.41, last_speed_px_s=0.3,
                     verdict_mm="ambiguous", inside_px=False, inside_mm=False,
                     pocket_test_disagrees_px_vs_mm=False, samples_used=[])
        moving = pot("t202-blue", last_t=1554.584226, last=[450.0, 320.0], pocket="left-side",
                     distance_mm=84.47, distance_mm_uncertainty=30.9, last_speed_px_s=211.32,
                     inside_px=False, inside_mm=True, samples_used=[])
        rejection = lambda ball_id, net, dia: {  # noqa: E731
            "kind": "rejection", "code": "oscillation_no_net_travel", "ball_id": ball_id,
            "reason": "a sustained run whose net displacement does not clear the bar",
            "numbers": {"net_displacement_px": net, "net_displacement_diameters": dia,
                        "net_uncertainty_px": 5.119, "bar_minus_net_px": 27.6 - net,
                        "path_length_px": 80.557, "peak_speed_px_s": 303.59, "duration_s": 0.267}}

        def unresolved(ball_id, net):
            return {"kind": "unresolved", "code": "oscillation_unresolved", "ball_id": ball_id,
                    "reason": "inside the localisation error of the bar", "t": 1351.786284,
                    "frame_index": 40554,
                    "numbers": {"net_displacement_px": net, "net_displacement_diameters": net / 13.8,
                                "net_uncertainty_px": 5.119, "bar_minus_net_px": 27.6 - net,
                                "path_length_px": net, "peak_speed_px_s": 165.6}}

        artifact = {"segment": {"start_s": 1350.0, "seconds": 300.0, "frames_decoded": 9000},
                    "samples": {"balls": 19534}, "tracks": {"n": 245},
                    "occlusion": {"source": "motion_scan.probe_pair occ_dense"},
                    "thresholds": {"cloth_quad": quad, "motion_speed_px_s": 40.0,
                                   "pocket_r_mm": 100.0, "min_net_displacement_diameters": 2.0,
                                   "ball_diameter_px": None, "localisation_error_px": 3.62,
                                   "persistence_s": 1.0},
                    "gate": {"shots": [shot], "pots": [pot("t265-blue"), parked, moving],
                             "rejections": [rejection("t125-white", 0.202, 0.015),
                                            rejection("t256-blue", 19.696, 1.427)],
                             "unresolved": [unresolved("t009-blue", 23.582),
                                            unresolved("t242-red", 31.632)],
                             "counts": {"tracks": 245, "shots": 1, "pots": 0, "unknowns": 3,
                                        "rejections": 2, "breaks": 0, "unresolved": 2}},
                    "rejection_codes": {"oscillation_no_net_travel": 2,
                                        "disappeared_outside_pocket": 165}}
        path = Path(tmp) / "artifact.json"
        path.write_text(json.dumps(artifact))
        return path

    def _build(self, tmp, previous=None, pot_verdict="unknown", queue_name="events.json",
               ledger_name="retired.json"):
        """Build the queue the way the tool is run: old queue supplies ids, ledger the dead ones."""
        from src.dense_queue import build
        queue, report = Path(tmp) / queue_name, Path(tmp) / "report.json"
        previous_path = None
        if previous is not None:
            previous_path = Path(tmp) / "previous.json"
            previous_path.write_text(json.dumps(previous))
        build(str(self._artifact(tmp, pot_verdict=pot_verdict)), str(queue), str(report),
              None if previous_path is None else str(previous_path),
              str(Path(tmp) / ledger_name))
        return json.loads(queue.read_text()), json.loads(report.read_text()), queue

    @staticmethod
    def _pot(events, ball_id="t265-blue"):
        return next(event for event in events
                    if event["type"] == "pot"
                    and event["provenance"]["ball_id"] == ball_id)

    def test_every_entry_says_it_is_machine_made(self):
        with TemporaryDirectory() as tmp:
            events, _, _ = self._build(tmp, previous=self.PREVIOUS)
            self.assertEqual(len(events), 3)
            for event in events:
                provenance = event["provenance"]
                self.assertTrue(provenance["machine_produced"])
                self.assertFalse(provenance["human_confirmed"])
                self.assertIn("no human has confirmed", provenance["statement"])
                self.assertIn("dense-track", provenance["detector"])
                self.assertEqual(provenance["run"]["identities"], 245)

    def test_the_pot_shaped_entry_is_not_a_pot(self):
        with TemporaryDirectory() as tmp:
            events, _, _ = self._build(tmp, previous=self.PREVIOUS)
            pot = self._pot(events)
            self.assertEqual(pot["gate"]["status"], "unconfirmed")
            self.assertIn("cloth_occluded_at_disappearance", pot["gate"]["reasons"])
            self.assertNotEqual(pot["gate"]["status"], "confirmed")
            self.assertIsNone(pot["tier"], "no tier: a tier grades a claim, and this has none")
            self.assertFalse(pot["verified"])

    def test_no_tier_is_invented_and_none_is_upgraded(self):
        with TemporaryDirectory() as tmp:
            events, _, _ = self._build(tmp, previous=self.PREVIOUS)
            for event in events:
                if event["type"] == "shot":
                    self.assertEqual(event["tier"], "window",
                                     "a dense event has no separate claim to verify against")
                    self.assertIn("window_grade_no_claim_to_check", event["gate"]["reasons"])
                self.assertNotEqual(event["tier"], "geometry")

    def test_ids_cannot_collide_with_a_recorded_verdict(self):
        from src.dense_queue import ID_BASE
        with TemporaryDirectory() as tmp:
            events, _, _ = self._build(tmp, previous=self.PREVIOUS)
            ids = [event["id"] for event in events]
            self.assertTrue(all(event_id >= ID_BASE for event_id in ids), ids)
            recorded = set(json.loads((ROOT / ANNOTATIONS).read_text())) \
                if (ROOT / ANNOTATIONS).exists() else {"16"}
            self.assertFalse({str(event_id) for event_id in ids} & recorded,
                             "a served id must never collide with a recorded verdict's id")

    def test_a_verdict_keeps_pointing_at_the_id_it_was_recorded_against(self):
        """The gate changed under the queue; the ids of what stayed must not."""
        with TemporaryDirectory() as tmp:
            events, report, _ = self._build(tmp, previous=self.PREVIOUS)
            self.assertEqual({event["provenance"]["ball_id"]: event["id"] for event in events},
                             {"t193-blue": 9002, "t265-blue": 9004, "t202-blue": 9005})
            self.assertEqual(report["id_changes"]["departed"], {"t125-white": 9001,
                                                                "t256-blue": 9003})
            self.assertEqual(report["id_changes"]["added"], {"t202-blue": 9005},
                             "the class rule adds; it never renumbers what stayed")

    def _with_extra_shot(self, tmp, ball_id="t999-blue"):
        artifact = json.loads(self._artifact(tmp).read_text())
        extra = dict(artifact["gate"]["shots"][0])
        extra.update({"ball_id": ball_id, "onset_t": 1600.0, "group_id": "onset-2"})
        artifact["gate"]["shots"].append(extra)
        path = Path(tmp) / "artifact.json"
        path.write_text(json.dumps(artifact))
        return path

    def test_a_retired_id_is_never_handed_to_another_ball(self):
        from src.dense_queue import build
        with TemporaryDirectory() as tmp:
            path = self._with_extra_shot(tmp)
            previous = Path(tmp) / "previous.json"
            previous.write_text(json.dumps(self.PREVIOUS))
            queue = Path(tmp) / "events.json"
            build(str(path), str(queue), str(Path(tmp) / "report.json"), str(previous),
                  str(Path(tmp) / "retired.json"))
            by_ball = {event["provenance"]["ball_id"]: event["id"]
                       for event in json.loads(queue.read_text())}
            self.assertEqual(by_ball["t193-blue"], 9002)
            self.assertEqual(by_ball["t265-blue"], 9004)
            self.assertEqual(by_ball["t202-blue"], 9005)
            self.assertGreater(by_ball["t999-blue"], 9005,
                               "a new ball starts above every id ever issued here")
            self.assertNotIn(by_ball["t999-blue"], (9001, 9003))

    def test_a_shrunk_queue_never_reissues_a_retired_id(self):
        """The ledger, not the queue, is what keeps a dead id dead."""
        from src.dense_queue import build
        with TemporaryDirectory() as tmp:
            # Run 1 retires 9001 and 9003 (the two rejected runs) into the ledger.
            _, first, _ = self._build(tmp, previous=self.PREVIOUS)
            self.assertEqual(first["id_changes"]["reserved_never_reissued"], [9001, 9003])
            ledger = json.loads((Path(tmp) / "retired.json").read_text())
            self.assertEqual({row["id"] for row in ledger.values()}, {9001, 9003})
            self.assertTrue(all(row["code"] == "oscillation_no_net_travel"
                                for row in ledger.values()))
            # Run 2: the queue has shrunk to 9002 alone.  A new ball must not take
            # 9003 back just because nothing holds it any more.
            shrunk = [entry for entry in self.PREVIOUS if entry["id"] == 9002]
            queue = Path(tmp) / "shrunk.json"
            build(str(self._with_extra_shot(tmp)), str(queue), str(Path(tmp) / "report2.json"),
                  None, str(Path(tmp) / "retired.json"))
            shrunk_path = Path(tmp) / "previous-shrunk.json"
            shrunk_path.write_text(json.dumps(shrunk))
            queue2 = Path(tmp) / "shrunk2.json"
            build(str(self._artifact(tmp)), str(queue2), str(Path(tmp) / "report3.json"),
                  str(shrunk_path), str(Path(tmp) / "retired.json"))
            ids = {event["provenance"]["ball_id"]: event["id"]
                   for event in json.loads(queue2.read_text())}
            self.assertEqual(ids["t193-blue"], 9002, "the one still served keeps its id")
            for ball_id in ("t265-blue", "t202-blue"):
                self.assertNotIn(ids[ball_id], (9001, 9003),
                                 "a retired id is dead even when nothing holds it")
                self.assertGreaterEqual(ids[ball_id], 9001)
            self.assertEqual(len(set(ids.values())), len(ids), "ids stay unique")

    def test_regenerating_from_the_same_gate_output_changes_nothing(self):
        with TemporaryDirectory() as tmp:
            first_events, first_report, queue = self._build(tmp, previous=self.PREVIOUS)
            first = queue.read_bytes()
            events, report2, _ = self._build(tmp, previous=self.PREVIOUS)
            self.assertEqual(queue.read_bytes(), first)
            self.assertEqual([event["id"] for event in events],
                             [event["id"] for event in first_events])
            self.assertEqual(report2["queue"]["md5_before"], report2["queue"]["md5_after"])
            self.assertEqual(report2["id_changes"]["served_before"],
                             first_report["id_changes"]["served_before"])

    def test_the_unknown_keeps_its_millimetre_distance_and_error_bar(self):
        with TemporaryDirectory() as tmp:
            events, _, _ = self._build(tmp, previous=self.PREVIOUS)
            numbers = self._pot(events)["gate"]["numbers"]
            self.assertAlmostEqual(numbers["vanish_dist_mm"], 148.48, places=2)
            self.assertAlmostEqual(numbers["vanish_dist_mm_uncertainty"], 54.11, places=2)
            self.assertEqual(numbers["vanish_verdict_mm"], "ambiguous")
            self.assertLess(numbers["vanish_dist_mm_lo"], numbers["vanish_radius_mm"])
            self.assertGreater(numbers["vanish_dist_mm_hi"], numbers["vanish_radius_mm"])
            self.assertIn("±", numbers["vanish_distance_text"])
            self.assertIn("too uncertain to call", numbers["vanish_distance_text"])
            self.assertIn("无法判定", numbers["vanish_distance_text_zh"])

    def test_the_pocket_test_disagreement_is_reported(self):
        with TemporaryDirectory() as tmp:
            events, _, _ = self._build(tmp, previous=self.PREVIOUS)
            pot = self._pot(events)                      # t265-blue: px inside, mm outside
            numbers = pot["gate"]["numbers"]
            self.assertFalse(numbers["pocket_test_agrees"])
            self.assertIn("pocket_test_disagrees_px_vs_mm", pot["gate"]["codes"])
            # inside the gate's pixel radius, outside the project's 100 mm one
            self.assertLessEqual(numbers["vanish_dist_px"], numbers["vanish_radius_px"])
            self.assertGreater(numbers["vanish_dist_mm"], numbers["pocket_r_mm"])
            self.assertFalse(numbers["vanish_inside_mm"])
            self.assertTrue(numbers["vanish_inside_px"])
            self.assertIn("pocket_distance_ambiguous_mm", pot["gate"]["codes"])
            # the operator sentence is in the notes row the rail prints, and the
            # machine-readable codes stay available beside it
            self.assertTrue(set(pot["gate"]["codes"]) <= set(pot["gate"]["reasons"]))
            self.assertTrue(any("±" in reason for reason in pot["gate"]["reasons"]))

    def test_the_moving_class_is_served_and_the_parked_unknowns_are_not(self):
        """The owner's rule: a disappearance that was still moving is a candidate."""
        with TemporaryDirectory() as tmp:
            events, report, _ = self._build(tmp, previous=self.PREVIOUS)
            served = {event["provenance"]["ball_id"] for event in events}
            self.assertEqual(served, {"t193-blue", "t265-blue", "t202-blue"})
            self.assertEqual(report["not_served"]["pots_confirmed"], 0)
            self.assertEqual(report["not_served"]["pots_unknown_in_channel"], 3)
            self.assertEqual(report["not_served"]["unknowns_served"], ["t265-blue", "t202-blue"])
            not_carded = report["not_served"]["unknowns_not_carded"]
            self.assertEqual([row["ball_id"] for row in not_carded], ["t170-black"],
                             "a near-stationary disappearance is a dropout, not a candidate")
            for row in not_carded:
                self.assertEqual(row["verdict_mm"], "ambiguous")
                self.assertIsNotNone(row["distance_mm"])
                self.assertIsNotNone(row["distance_mm_uncertainty"])
                self.assertLess(row["last_speed_px_s"], 100.0)
            channel = report["channels"]["occluded_unknowns"]
            self.assertEqual(channel["count"], 3)
            self.assertEqual([row["ball_id"] for row in channel["served"]],
                             ["t265-blue", "t202-blue"])
            self.assertEqual(channel["verdict_mm_counts"], {"ambiguous": 3})
            self.assertEqual(channel["moving_at_last_sighting"]["threshold_px_s"], 100.0)
            self.assertEqual([row["ball_id"]
                              for row in channel["moving_at_last_sighting"]["moving"]],
                             ["t265-blue", "t202-blue"])
            self.assertEqual(channel["moving_at_last_sighting"]["parked"], 1)

    def test_the_class_rule_serves_a_still_moving_unknown_the_queue_never_carried(self):
        with TemporaryDirectory() as tmp:
            events, report, _ = self._build(tmp)          # no previous queue at all
            by_ball = {event["provenance"]["ball_id"]: event for event in events}
            self.assertEqual(set(by_ball), {"t193-blue", "t265-blue", "t202-blue"})
            self.assertNotIn("t170-black", by_ball, "the parked one is never served")
            for ball_id in ("t202-blue", "t265-blue"):
                self.assertIn("still moving", by_ball[ball_id]["provenance"]["served_because"])
                self.assertEqual(by_ball[ball_id]["provenance"]["unknowns_in_channel"], 1)
            for event in events:
                if event["type"] != "pot":
                    continue
                self.assertEqual(event["gate"]["status"], "unconfirmed")
                self.assertIsNone(event["tier"])
                self.assertIn("±", event["gate"]["numbers"]["vanish_distance_text"])
                self.assertEqual(event["gate"]["numbers"]["vanish_verdict_mm"], "ambiguous")

    def test_the_serving_rule_is_written_down_in_words(self):
        with TemporaryDirectory() as tmp:
            _, report, _ = self._build(tmp, previous=self.PREVIOUS)
            rule = report["serving_rule"]
            self.assertEqual(rule["moving_threshold_px_s"], 100.0)
            joined = " ".join(rule["serve"] + rule["never_serve"])
            self.assertIn("vanished while still moving", joined)
            self.assertIn("at rest", joined)
            self.assertIn("unresolved", joined)
            self.assertIn("honestly", rule["why"])

    def test_the_unresolved_runs_are_counted_and_not_carded(self):
        with TemporaryDirectory() as tmp:
            events, report, _ = self._build(tmp, previous=self.PREVIOUS)
            unresolved = report["channels"]["unresolved"]
            self.assertEqual(unresolved["count"], 2)
            self.assertEqual(unresolved["served"], [])
            self.assertNotIn(unresolved["code"],
                             {event["gate"]["status"] for event in events})
            sides = {row["ball_id"]: row["side"] for row in unresolved["rows"]}
            self.assertEqual(sides, {"t009-blue": "short_of_bar", "t242-red": "clears_bar"})
            for row in unresolved["rows"]:
                self.assertTrue(row["inside_own_error_bar"],
                                "an unresolved run is one the error bar straddles")
                self.assertNotIn(row["ball_id"],
                                 {event["provenance"]["ball_id"] for event in events})

    def test_the_rejected_runs_leave_the_queue_and_are_reported(self):
        with TemporaryDirectory() as tmp:
            events, report, _ = self._build(tmp, previous=self.PREVIOUS)
            self.assertNotIn("t125-white", {e["provenance"]["ball_id"] for e in events})
            self.assertNotIn("t256-blue", {e["provenance"]["ball_id"] for e in events})
            departed = {row["ball_id"]: row for row in report["channels"]["departed_entries"]}
            self.assertEqual(set(departed), {"t125-white", "t256-blue"})
            for row in departed.values():
                self.assertEqual(row["code"], "oscillation_no_net_travel")
                self.assertIsNotNone(row["numbers"]["net_displacement_diameters"])
                self.assertEqual(row["bar_px"], 27.6)
            self.assertEqual(departed["t125-white"]["was_id"], 9001)
            self.assertEqual(departed["t256-blue"]["was_id"], 9003)
            self.assertGreater(len(report["channels"]["oscillation_rejections"]["served_before"]), 0)

    def test_a_pot_the_gate_confirmed_is_served_without_a_previous_queue(self):
        from src.dense_queue import build
        with TemporaryDirectory() as tmp:
            artifact = json.loads(self._artifact(tmp).read_text())
            artifact["gate"]["pots"][0]["verdict"] = "confirmed"      # t265-blue only
            artifact["gate"]["counts"]["pots"] = 1
            path = Path(tmp) / "artifact.json"
            path.write_text(json.dumps(artifact))
            queue = Path(tmp) / "events.json"
            build(str(path), str(queue), str(Path(tmp) / "report.json"))
            served = [event["provenance"]["ball_id"] for event in json.loads(queue.read_text())]
            self.assertEqual(served, ["t202-blue", "t193-blue", "t265-blue"],
                             "the confirmed pot is served without being carried; the two "
                             "moving unknowns come in by the class rule")

    def test_the_verdict_file_never_gains_the_dense_ids(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotations.json"
            path.write_text(json.dumps({"16": {"verdict": "unsure"}}))
            before = _md5(path)
            self._build(tmp, previous=self.PREVIOUS)
            self.assertEqual(_md5(path), before)
            self.assertEqual(json.loads(path.read_text()), {"16": {"verdict": "unsure"}})


from src.dense_queue import ANNOTATIONS  # noqa: E402
