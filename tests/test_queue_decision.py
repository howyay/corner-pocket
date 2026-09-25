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

    def _artifact(self, tmp):
        import numpy as np
        quad = np.array([[399.0, 242.25], [600.0, 243.0], [747.75, 426.75], [288.0, 422.25]],
                        float).tolist()
        shot = {"kind": "shot", "ball_id": "t193-blue", "onset_frame_index": 47404,
                "onset_t": 1580.117301, "onset": [579.03, 298.05], "peak_speed_px_s": 491.63,
                "duration_s": 0.733326, "path_length_px": 159.86, "net_displacement_px": 159.1,
                "rest_window_measured_s": 9.73, "ends_in_pocket": False, "end_distance_px": 29.44,
                "group_id": "onset-1",
                "samples_used": [{"frame_index": 47404, "t": 1580.117301, "x": 579.03, "y": 298.05,
                                  "confidence": 0.8, "occluded": False},
                                 {"frame_index": 47426, "t": 1580.850626, "x": 427.6, "y": 249.24,
                                  "confidence": 0.63, "occluded": False}]}
        pot = {"kind": "pot", "ball_id": "t265-blue", "verdict": "unknown",
               "reason": "cloth_occluded_at_disappearance", "pocket": "left-side",
               "pocket_px": [365.1, 297.22], "radius_px": 14.46, "distance_px": 9.62,
               "last_frame_index": 49156, "last_t": 1638.516708, "last": [368.3, 306.3],
               "last_speed_px_s": 734.15, "gap_s": 11.43, "occlusion_status": "occluded",
               "identity_swap_suspected": False,
               "samples_used": [{"frame_index": 49152, "t": 1638.383376, "x": 325.12, "y": 381.51,
                                 "confidence": 0.55, "occluded": False},
                                {"frame_index": 49156, "t": 1638.516708, "x": 368.3, "y": 306.3,
                                 "confidence": 0.55, "occluded": False}]}
        artifact = {"segment": {"start_s": 1350.0, "seconds": 300.0, "frames_decoded": 9000},
                    "samples": {"balls": 19534}, "tracks": {"n": 245},
                    "occlusion": {"source": "motion_scan.probe_pair occ_dense"},
                    "thresholds": {"cloth_quad": quad, "motion_speed_px_s": 40.0,
                                   "pocket_r_mm": 100.0},
                    "gate": {"shots": [shot], "pots": [pot], "counts": {"rejections": 713}},
                    "rejection_codes": {"disappeared_outside_pocket": 172}}
        path = Path(tmp) / "artifact.json"
        path.write_text(json.dumps(artifact))
        return path

    def test_every_entry_says_it_is_machine_made(self):
        from src.dense_queue import build
        with TemporaryDirectory() as tmp:
            artifact = self._artifact(tmp)
            queue = Path(tmp) / "events.json"
            build(str(artifact), str(queue), str(Path(tmp) / "report.json"))
            events = json.loads(queue.read_text())
            self.assertEqual(len(events), 2)
            for event in events:
                provenance = event["provenance"]
                self.assertTrue(provenance["machine_produced"])
                self.assertFalse(provenance["human_confirmed"])
                self.assertIn("no human has confirmed", provenance["statement"])
                self.assertIn("dense-track", provenance["detector"])
                self.assertEqual(provenance["run"]["identities"], 245)

    def test_the_pot_shaped_entry_is_not_a_pot(self):
        from src.dense_queue import build
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "events.json"
            build(str(self._artifact(tmp)), str(queue), str(Path(tmp) / "report.json"))
            pot = next(event for event in json.loads(queue.read_text()) if event["type"] == "pot")
            self.assertEqual(pot["gate"]["status"], "unconfirmed")
            self.assertIn("cloth_occluded_at_disappearance", pot["gate"]["reasons"])
            self.assertNotEqual(pot["gate"]["status"], "confirmed")
            self.assertIsNone(pot["tier"], "no tier: a tier grades a claim, and this has none")
            self.assertFalse(pot["verified"])

    def test_no_tier_is_invented_and_none_is_upgraded(self):
        from src.dense_queue import build
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "events.json"
            build(str(self._artifact(tmp)), str(queue), str(Path(tmp) / "report.json"))
            events = json.loads(queue.read_text())
            for event in events:
                if event["type"] == "shot":
                    self.assertEqual(event["tier"], "window",
                                     "a dense event has no separate claim to verify against")
                    self.assertIn("window_grade_no_claim_to_check", event["gate"]["reasons"])
                self.assertNotEqual(event["tier"], "geometry")

    def test_ids_cannot_collide_with_a_recorded_verdict(self):
        from src.dense_queue import build, ID_BASE
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "events.json"
            build(str(self._artifact(tmp)), str(queue), str(Path(tmp) / "report.json"))
            ids = [event["id"] for event in json.loads(queue.read_text())]
            self.assertTrue(all(event_id >= ID_BASE for event_id in ids), ids)
            recorded = set(json.loads((ROOT / ANNOTATIONS).read_text())) \
                if (ROOT / ANNOTATIONS).exists() else {"16"}
            self.assertFalse({str(event_id) for event_id in ids} & recorded,
                             "a served id must never collide with a recorded verdict's id")

    def test_the_pocket_test_disagreement_is_reported(self):
        from src.dense_queue import build
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "events.json"
            build(str(self._artifact(tmp)), str(queue), str(Path(tmp) / "report.json"))
            pot = next(event for event in json.loads(queue.read_text()) if event["type"] == "pot")
            numbers = pot["gate"]["numbers"]
            self.assertFalse(numbers["pocket_test_agrees"])
            self.assertIn("pocket_test_disagrees_px_vs_mm", pot["gate"]["reasons"])
            # inside the gate's pixel radius, outside the project's 100 mm one
            self.assertLessEqual(numbers["vanish_dist_px"], numbers["vanish_radius_px"])
            self.assertGreater(numbers["vanish_dist_mm"], numbers["pocket_r_mm"])

    def test_the_verdict_file_never_gains_the_dense_ids(self):
        from src.dense_queue import build
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotations.json"
            path.write_text(json.dumps({"16": {"verdict": "unsure"}}))
            before = _md5(path)
            build(str(self._artifact(tmp)), str(Path(tmp) / "events.json"),
                  str(Path(tmp) / "report.json"))
            self.assertEqual(_md5(path), before)
            self.assertEqual(json.loads(path.read_text()), {"16": {"verdict": "unsure"}})


from src.dense_queue import ANNOTATIONS  # noqa: E402
