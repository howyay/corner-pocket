"""Gate tests: dedup merge, pot persistence, off-cloth rejection, verdict shape.

No video, no model: ``src.event_gates`` is pure, and the eval tool's measuring
half is exercised through its pure report builders with synthetic evidence.
"""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.event_gates import (GateConfig, GateResult, PotEvidence, ShotEvidence,  # noqa: E402
                             dedupe, judge, nearest_pocket, normalize)


def pot(t, color, mm, kind="pot", **extra):
    return {"type": kind, "t": t, "color": color, "last_mm": list(mm), "last_frame": 100,
            "pocket_dist_mm": 10, **extra}


def shot(t, color, from_mm, to_mm, disp=400, **extra):
    return {"type": "shot", "t": t, "color": color, "from_mm": list(from_mm), "to_mm": list(to_mm),
            "disp_mm": disp, "speed_mm_s": disp / 0.07, "gap_s": 0.07, "from_frame": 10,
            "to_frame": 12, **extra}


class DedupeTests(unittest.TestCase):
    def test_same_act_trio_collapses_to_the_earliest(self):
        # the measured vod30 pre-break case: three pots, one blue ball, 0.27 s wide
        trio = [pot(5.6, "blue", (1146.2, 2547.9)),
                pot(5.67, "blue", (1188.2, 592.0)),
                pot(5.87, "blue", (1072.9, 2556.4))]
        groups = dedupe(trio)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["event"]["t"], 5.6)
        self.assertEqual(groups[0]["count"], 3)
        self.assertEqual(groups[0]["colors"], ["blue"])

    def test_distinct_acts_are_kept_apart(self):
        # different colour and a different part of the table seconds later
        groups = dedupe([pot(5.6, "blue", (1146.2, 2547.9)), pot(20.0, "black", (200.0, 300.0))])
        self.assertEqual(len(groups), 2)

    def test_second_colour_of_the_same_shot_is_merged_by_time_and_place(self):
        same_moment = [shot(136.5, "white", (109.3, 1949.4), (140.0, 2000.0)),
                       shot(136.8, "blue", (110.0, 1950.0), (150.0, 2020.0))]
        groups = dedupe(same_moment)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 2)

    def test_shots_and_pots_never_merge(self):
        groups = dedupe([pot(5.6, "blue", (1146.2, 2547.9)),
                         shot(5.6, "blue", (1146.2, 2547.9), (1200.0, 2500.0))])
        self.assertEqual(len(groups), 2)


class PotGateTests(unittest.TestCase):
    claim = normalize(pot(27.7, "black", (1210.0, 2421.0)))

    def evidence(self, **overrides):
        fields = dict(available=True, census_pre=5.0, census_post=1.5, census_post_max=2.0,
                      color_census_pre=3.5, color_census_post=0.0, motion_max=20.6,
                      vanish=[{"color": "black", "mm": [1210, 2421], "pocket": "foot-right",
                               "dist_mm": 60, "pre_hits": 4, "approach_mm": 330.0}])
        fields.update(overrides)
        return PotEvidence(**fields)

    def test_corroborated_pot_is_confirmed(self):
        result = judge(self.claim, self.evidence())
        self.assertEqual((result.status, result.tier), ("confirmed", "geometry"))

    def test_census_that_does_not_drop_is_rejected(self):
        result = judge(self.claim, self.evidence(census_pre=2.0, census_post=2.0))
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reasons, ["census_did_not_drop"])

    def test_census_too_sparse_to_decide_is_unconfirmed(self):
        # measured on vod30: most windows hold 1-3 detections, so a missing drop
        # is a missing measurement, never a contradiction
        result = judge(self.claim, self.evidence(census_pre=1.0, census_post=1.0))
        self.assertEqual(result.status, "unconfirmed")
        self.assertEqual(result.reasons, ["census_too_sparse"])

    def test_census_that_comes_back_is_rejected(self):
        # the t=9.4 park-in-the-jaws case: the count returns to its old level
        result = judge(self.claim, self.evidence(census_pre=3.0, census_post=2.0, census_post_max=3.0))
        self.assertEqual(result.reasons, ["census_recovered"])

    def test_ball_still_on_the_cloth_is_not_a_pot(self):
        result = judge(self.claim, self.evidence(vanish=[{"color": "black", "mm": [800, 1800],
                                                          "pocket": "foot-right", "dist_mm": 739,
                                                          "pre_hits": 5, "approach_mm": None}]))
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reasons, ["vanished_ball_not_at_pocket"])

    def test_missing_vanished_ball_is_unconfirmed_not_rejected(self):
        result = judge(self.claim, self.evidence(vanish=[]))
        self.assertEqual(result.status, "unconfirmed")
        self.assertEqual(result.reasons, ["no_vanished_ball_measured"])

    def test_unavailable_probe_is_unconfirmed(self):
        result = judge(self.claim, PotEvidence(available=False, note="no video probe available"))
        self.assertEqual(result.status, "unconfirmed")
        self.assertIn("no video probe available", result.reasons)

    def test_approach_away_from_the_pocket_is_rejected(self):
        result = judge(self.claim, self.evidence(vanish=[{"color": "black", "mm": [1210, 2421],
                                                          "pocket": "foot-right", "dist_mm": 58,
                                                          "pre_hits": 3, "approach_mm": -15.1}]))
        self.assertEqual(result.reasons, ["no_approach_to_pocket"])


class ShotGateTests(unittest.TestCase):
    claim = normalize(shot(82.5, "white", (423.1, 612.9), (700.0, 900.0)))

    def evidence(self, **overrides):
        fields = dict(available=True, disp_mm=777.0, disp_color="white", start_px=[938.7, 566.7],
                      geometry_gap_px=40.0, window_motion=16.9, from_in_cloth_px=29.6,
                      to_in_cloth_px=42.8, start_hits=3, end_hits=6, observations_needed=2)
        fields.update(overrides)
        return ShotEvidence(**fields)

    def test_corroborated_shot_with_matching_geometry(self):
        result = judge(self.claim, self.evidence())
        self.assertEqual((result.status, result.tier), ("confirmed", "geometry"))

    def test_geometry_mismatch_is_confirmed_but_flagged(self):
        result = judge(self.claim, self.evidence(geometry_gap_px=386.5))
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.tier, "window")
        self.assertIn("geometry_mismatch", result.reasons)

    def test_off_cloth_projection_is_rejected(self):
        # the t=6.0 case: the claim projects onto the wall behind the far rail
        result = judge(self.claim, self.evidence(from_in_cloth_px=-40.0))
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reasons, ["off_cloth"])

    def test_claim_without_bracketing_geometry_is_unconfirmed(self):
        bare = normalize({"type": "shot", "t": 6.0, "color": "blue", "disp_mm": 172})
        result = judge(bare, ShotEvidence(available=True, disp_mm=5.0, from_in_cloth_px=None,
                                          to_in_cloth_px=None))
        self.assertEqual(result.status, "unconfirmed")
        self.assertEqual(result.reasons, ["claim_not_projectable"])

    def test_small_re_measured_displacement_is_rejected(self):
        # the t=6.0 measurement: the same colour moved 9 mm, not 172 mm
        result = judge(self.claim, self.evidence(disp_mm=9.0))
        self.assertEqual(result.reasons, ["displacement_not_corroborated"])

    def test_pair_sighted_once_is_rejected_as_a_mismatch(self):
        result = judge(self.claim, self.evidence(start_hits=1, end_hits=9))
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reasons, ["displacement_unobserved_elsewhere"])


class VerdictShapeTests(unittest.TestCase):
    def test_verdict_shape_is_stable(self):
        result = judge(normalize(shot(82.5, "white", (10.0, 10.0), (20.0, 20.0))),
                       ShotEvidence(available=False, note="no video probe available"))
        payload = result.as_dict()
        self.assertEqual(sorted(payload), ["gate", "numbers", "reasons", "status"])
        json.dumps(payload)                       # must be JSON-serialisable
        self.assertEqual(payload["status"], "unconfirmed")

    def test_threshold_values_are_pinned(self):
        cfg = GateConfig()
        self.assertEqual(cfg.shot_min_disp_mm, 300.0)
        self.assertEqual(cfg.pot_pocket_r_mm, 100.0)
        self.assertEqual(cfg.dedup_window_s, 2.0)
        self.assertEqual(cfg.off_cloth_tol_px, -2.0)
        self.assertEqual(cfg.shot_stable_anchors, 2)
        self.assertEqual(cfg.pot_min_census, 2.0)

    def test_weak_calibration_is_a_reported_warning_not_a_verdict(self):
        claim = normalize(shot(82.5, "white", (423.1, 612.9), (700.0, 900.0)))
        evidence = ShotEvidence(available=True, disp_mm=777.0, disp_color="white",
                                start_px=[938.7, 566.7], geometry_gap_px=40.0,
                                from_in_cloth_px=29.6, to_in_cloth_px=42.8,
                                start_hits=3, end_hits=6, calibration_frac=0.42)
        result = judge(claim, evidence)
        self.assertEqual(result.status, "confirmed")
        self.assertIn("calibration_weak_at_time", result.reasons)
        self.assertEqual(result.numbers["calibration_frac"], 0.42)

    def test_pocket_geometry_matches_the_scan_frame(self):
        self.assertEqual(nearest_pocket(1200.0, 2500.0)[0], "foot-right")
        self.assertEqual(nearest_pocket(0.0, 1270.0)[0], "left-side")


class EvalToolTests(unittest.TestCase):
    """The measuring half: report builders stay pure and video-free."""

    def setUp(self):
        from src import eval_events
        self.tool = eval_events

    def test_queue_event_carries_gate_numbers_additively(self):
        groups = dedupe([pot(5.6, "blue", (1146.2, 2547.9)), pot(5.67, "blue", (1188.2, 592.0))])
        group = groups[0]
        group["evidence"] = {"available": True, "census_pre": 3.0, "census_post": 2.0,
                             "census_post_max": 3.0, "color_census_pre": 2.0,
                             "color_census_post": 2.0, "vanish": [], "motion_max": 1.8}
        group["verdict"] = judge(group["event"], PotEvidence(**group["evidence"])).as_dict()
        event = self.tool.to_queue_event(group, previous_ids={("pot", 5.6): 7})
        self.assertEqual(event["id"], 7)
        self.assertEqual(event["dup_count"], 2)
        self.assertEqual(event["gate"]["status"], "rejected")
        self.assertEqual(event["gate"]["numbers"]["census_pre"], 3.0)
        json.dumps(event)

    def test_queue_event_carries_the_tier_and_keeps_the_claim_geometry(self):
        # The owner serves every confirmed shot, so the queue must say which tier
        # it was confirmed at and whether the claim's own start survived the
        # re-measurement -- without rewriting what the scan claimed.
        from src.event_gates import GateConfig, ShotEvidence, judge
        claim = {"type": "shot", "t": 1799.1, "color": "white",
                 "from_mm": [712.3, 1813.0], "to_mm": [915.6, 1214.7]}
        groups = dedupe([claim])
        group = groups[0]
        evidence = ShotEvidence(available=True, disp_mm=318, disp_color="white",
                                geometry_gap_px=263.2, window_motion=52.87,
                                from_in_cloth_px=69.6, to_in_cloth_px=55.4,
                                start_hits=2, end_hits=2, stable_hits=2, anchor_tries=3,
                                calibration_frac=0.351)
        group["evidence"] = dict(evidence.__dict__)
        group["verdict"] = judge(group["event"], evidence, GateConfig()).as_dict()
        event = self.tool.to_queue_event(group, previous_ids={})
        self.assertEqual(event["tier"], "window")
        self.assertFalse(event["geometry_check"]["matches"])
        self.assertEqual(event["geometry_check"]["gap_px"], 263.2)
        self.assertEqual(event["geometry_check"]["tol_px"], 60.0)
        self.assertEqual(event["geometry_check"]["claim_start_mm"], [712.3, 1813.0])
        self.assertEqual(event["ball_from"], [712.3, 1813.0])      # claim kept as-is
        self.assertEqual(event["ball_to"], [915.6, 1214.7])
        json.dumps(event)

    def test_a_geometry_tier_event_reports_that_the_claim_matched(self):
        from src.event_gates import GateConfig, ShotEvidence, judge
        claim = {"type": "shot", "t": 483.4, "color": "black",
                 "from_mm": [307.9, 702.8], "to_mm": [321.8, 269.7]}
        group = dedupe([claim])[0]
        evidence = ShotEvidence(available=True, disp_mm=1837, disp_color="black",
                                geometry_gap_px=29.0, window_motion=57.48,
                                from_in_cloth_px=34.7, to_in_cloth_px=12.0,
                                start_hits=17, end_hits=7, stable_hits=3, anchor_tries=3,
                                calibration_frac=0.812)
        group["evidence"] = dict(evidence.__dict__)
        group["verdict"] = judge(group["event"], evidence, GateConfig()).as_dict()
        event = self.tool.to_queue_event(group, previous_ids={})
        self.assertEqual(event["tier"], "geometry")
        self.assertTrue(event["geometry_check"]["matches"])
        self.assertEqual(event["gate"]["numbers"]["disp_mm"], 1837)

    def test_summary_counts_duplicates_and_no_corroboration(self):
        rows = [
            {"id": 1, "kind": "pot", "t": 1.0, "color": "blue", "dup_count": 3,
             "verdict": {"status": "rejected", "reasons": ["census_recovered"]},
             "evidence": {"vanish": []}},
            {"id": 2, "kind": "shot", "t": 2.0, "color": "white", "dup_count": 1,
             "verdict": {"status": "unconfirmed", "reasons": ["no_matched_ball_measured"]},
             "evidence": {"window_motion": 3.0, "disp_mm": 220}},
            {"id": 3, "kind": "shot", "t": 3.0, "color": "black", "dup_count": 1,
             "verdict": {"status": "confirmed", "reasons": ["displacement_corroborated"],
                         "tier": "geometry"},
             "evidence": {"disp_mm": 634, "window_motion": 24.8}},
        ]
        summary = self.tool.summarize(rows)
        self.assertEqual(summary["duplicates_collapsed"], 2)
        self.assertEqual(summary["no_corroboration"], 1)
        self.assertEqual(summary["confirmed"], 1)
        self.assertEqual(summary["gate_precision_estimate"], 1.0)
        # the unconfirmed shot moved 220 mm -- worth a human look, kept out of the queue
        self.assertEqual([miss["id"] for miss in summary["near_misses"]], [2])

    def test_agreement_reads_verdicts_without_writing(self):
        rows = [{"id": 1, "verdict": {"status": "rejected", "reasons": ["census_did_not_drop"]},
                 "evidence": {}},
                {"id": 2, "verdict": {"status": "rejected", "reasons": ["displacement_not_corroborated"]},
                 "evidence": {}}]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotations.json"
            path.write_text(json.dumps({"1": {"verdict": "wrong"}, "2": {"verdict": "unsure"}}))
            before = path.read_bytes()
            agree = self.tool.agreement(rows, self.tool.owner_verdicts([path]))
            self.assertEqual(path.read_bytes(), before)          # read-only
        self.assertEqual(agree["reported"], 2)
        self.assertEqual(agree["comparable"], 1)
        self.assertEqual(agree["agreement"], 1)
        self.assertEqual(agree["unsure_rejected_by_gates"], 1)


if __name__ == "__main__":
    unittest.main()
