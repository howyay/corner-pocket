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
