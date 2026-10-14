"""Raw-candidate generation tests: thresholds, pruning, ranking, SAM3 plan.

No video, no model: ``src.candidate_scan.raw_candidates``/``prune``/``plan_sam3``
are pure functions over frame records, so the generation rules are pinned on
synthetic records.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.candidate_scan import (ScanConfig, plan_sam3, pot_strength, prune,  # noqa: E402
                                raw_candidates, shot_strength)
from src.pipeline import homography_to_canonical  # noqa: E402

# 640x360 px covers the 1270x2540 mm canonical table: x is ~2 mm/px, y ~7 mm/px.
CORNERS = np.array([[0, 0], [640, 0], [640, 360], [0, 360]], np.float32)
H = homography_to_canonical(CORNERS)
CFG = ScanConfig()


def ball(color, cx, cy, r=10.0, streak=3):
    return {"color": color, "cx": float(cx), "cy": float(cy), "r": r, "_streak": streak}


def record(t, cands, n=None, cloth_area=150000, brightness=100.0, motion=1.0,
           person_share=0.0):
    return {"t": round(t, 3), "frame": int(t * 30), "n": len(cands) if n is None else n,
            "cloth_area": cloth_area, "brightness": brightness, "motion": motion,
            "person_share": person_share, "cands": cands}


def steady(count=10, start=0.0, step=0.0667, colour="white", frames=45, **kwargs):
    """A rack of ``count`` balls, one per 40 px, in ``frames`` samples."""
    return [record(start + index * step,
                   [ball(colour, 60 + slot * 40, 100) for slot in range(count)], **kwargs)
            for index in range(frames)]


class ShotGenerationTests(unittest.TestCase):
    def test_a_matched_pair_over_the_threshold_is_a_shot(self):
        # The white ball is established at 100 px, jumps to 300 px in one
        # sample (the blobs never see it move) and is still there afterwards.
        records = [record(0.0, [ball("white", 100, 100), ball("blue", 300, 200)]),
                   record(0.0667, [ball("white", 100, 100), ball("blue", 300, 200)]),
                   record(0.1334, [ball("white", 300, 100), ball("blue", 300, 200)]),
                   record(0.2001, [ball("white", 300, 100), ball("blue", 300, 200)])]
        shots = [c for c in raw_candidates(records, H, CFG) if c["source"] == "pair"]
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["type"], "shot")
        self.assertEqual(shots[0]["color"], "white")
        self.assertGreaterEqual(shots[0]["disp_mm"], CFG.shot_min_disp_mm)
        self.assertTrue(shots[0]["from_mm"] and shots[0]["to_mm"])

    def test_an_arrival_that_vanishes_at_once_is_not_a_shot(self):
        # The ball jumps and is gone in the next sample: a flicker or a ball
        # that was potted, not a shot the queue should carry.
        records = [record(0.0, [ball("white", 100, 100), ball("blue", 300, 200)]),
                   record(0.0667, [ball("white", 100, 100), ball("blue", 300, 200)]),
                   record(0.1334, [ball("white", 300, 100), ball("blue", 300, 200)]),
                   record(0.2001, [ball("blue", 300, 200)])]
        self.assertEqual([c for c in raw_candidates(records, H, CFG) if c["source"] == "pair"], [])

    def test_a_fresh_detection_is_not_a_shot(self):
        records = [record(0.0, [ball("white", 100, 100, streak=1)]),
                   record(0.0667, [ball("white", 300, 100, streak=1)])]
        self.assertEqual(raw_candidates(records, H, CFG), [])

    def test_a_slow_roll_is_not_a_shot(self):
        records = [record(0.0, [ball("white", 100, 100)]),
                   record(0.0667, [ball("white", 110, 100)])]
        self.assertEqual([c for c in raw_candidates(records, H, CFG) if c["source"] == "pair"], [])

    def test_motion_spike_becomes_a_shot_with_geometry_from_the_lookback(self):
        records = [record(0.0, [ball("white", 100, 100), ball("red", 400, 200)], motion=1.0),
                   record(0.5, [ball("white", 100, 100), ball("red", 400, 200)], motion=1.0),
                   record(1.0, [ball("white", 300, 100), ball("red", 400, 200)], motion=25.0)]
        motion = [c for c in raw_candidates(records, H, CFG) if c["source"] == "motion"]
        self.assertEqual(len(motion), 1)
        self.assertEqual(motion[0]["color"], "white")
        self.assertGreaterEqual(motion[0]["disp_mm"], CFG.shot_min_disp_mm)
        self.assertGreaterEqual(motion[0]["motion"], CFG.motion_shot)

    def test_motion_spike_without_a_stable_census_is_ignored(self):
        # The count is falling at the spike: that is a pot, not a shot.
        records = steady(10, frames=5) + steady(6, start=1.0, frames=6)
        records[5]["motion"] = 30.0
        self.assertEqual([c for c in raw_candidates(records, H, CFG)
                          if c["source"] == "motion"], [])


class ShotSpeedWindowTests(unittest.TestCase):
    """Strong 2: one home for the window, and each of its two ends decides.

    ``ScanConfig.shot_speed_mm_s`` and ``ScanConfig.max_speed_mm_s`` read the two
    names ``src/info_complete_scan`` owns, so the two scanners cannot part.  The
    pair rule of ``src/candidate_scan.py:209-210`` refuses a speed below the floor
    or above the ceiling.  The longest gap a pair may span is 0.2 s and the
    displacement floor is 300 mm, so the 500 mm/s floor cannot bind with the
    default config (300 mm / 0.2 s = 1500 mm/s).  The cases below lower the
    displacement floor to measure the speed floor on its own.
    """

    GAP = 0.066                    # two rounded sample times of the 30 fps cadence

    def _pair_at(self, speed_mm_s, **config):
        """The pair candidates for one matched ball that travels at ``speed_mm_s``.

        ``to_table_mm`` is replaced by a ruler this case owns: 2 mm per pixel in
        x.  The measured speed is then exact for the gap above.
        """
        span_px = speed_mm_s * self.GAP / 2.0
        records = [record(0.0, [ball("white", 100.0, 100.0), ball("blue", 300.0, 200.0)]),
                   record(self.GAP, [ball("white", 100.0, 100.0), ball("blue", 300.0, 200.0)]),
                   record(2 * self.GAP, [ball("white", 100.0 + span_px, 100.0),
                                         ball("blue", 300.0, 200.0)]),
                   record(3 * self.GAP, [ball("white", 100.0 + span_px, 100.0),
                                         ball("blue", 300.0, 200.0)])]

        def ruler(_h, cx, cy):
            return (cx * 2.0, cy * 7.0)

        with mock.patch("src.candidate_scan.to_table_mm", ruler):
            return [c for c in raw_candidates(records, H, ScanConfig(**config))
                    if c["source"] == "pair"]

    def test_the_scan_config_reads_the_info_complete_speed_window(self):
        from src.info_complete_scan import MAX_SPEED_MM_S as OWNED_CEILING
        from src.info_complete_scan import SHOT_SPEED_MM_S as OWNED_FLOOR
        self.assertEqual(ScanConfig().shot_speed_mm_s, OWNED_FLOOR)
        self.assertEqual(ScanConfig().max_speed_mm_s, OWNED_CEILING)

    def test_the_window_keeps_the_measured_values(self):
        # 500 mm/s: the matched ball moves, it does not jitter.  11000 mm/s: above
        # this the match joins two different balls.  No case named the ceiling
        # before round 71, so a moved ceiling failed nothing.
        self.assertEqual(ScanConfig().shot_speed_mm_s, 500.0)
        self.assertEqual(ScanConfig().max_speed_mm_s, 11000.0)

    def test_the_ceiling_refuses_a_pair_just_above_it(self):
        ceiling = ScanConfig().max_speed_mm_s
        at_the_bar = self._pair_at(ceiling)
        self.assertEqual(len(at_the_bar), 1, "a pair at the ceiling must stand")
        self.assertAlmostEqual(at_the_bar[0]["speed_mm_s"], ceiling, delta=1.0)
        self.assertEqual(self._pair_at(ceiling + 1.0), [])

    def test_the_floor_refuses_a_pair_just_below_it(self):
        floor = ScanConfig().shot_speed_mm_s
        at_the_bar = self._pair_at(floor, shot_min_disp_mm=0.0)
        self.assertEqual(len(at_the_bar), 1, "a pair at the floor must stand")
        self.assertAlmostEqual(at_the_bar[0]["speed_mm_s"], floor, delta=1.0)
        self.assertEqual(self._pair_at(floor - 1.0, shot_min_disp_mm=0.0), [])


class PotGenerationTests(unittest.TestCase):
    def test_a_held_census_drop_becomes_a_pot_naming_the_ball_by_a_pocket(self):
        # Foot-right is (1270, 2540) mm -> (640, 360) px.
        rack = [ball("white", 60 + slot * 40, 100) for slot in range(8)]
        rack.append(ball("black", 636.0, 358.0))
        records = [record(index * 0.0667, list(rack)) for index in range(45)]
        after = [ball("white", 60 + slot * 40, 100) for slot in range(8)]
        records += [record(3.0 + index * 0.0667, list(after)) for index in range(12)]
        pots = [c for c in raw_candidates(records, H, CFG) if c["type"] == "pot"]
        self.assertEqual(len(pots), 1)
        self.assertEqual(pots[0]["color"], "black")
        self.assertEqual(pots[0]["pocket"], "foot-right")
        self.assertLessEqual(pots[0]["pocket_dist_mm"], 100)
        self.assertEqual(pots[0]["missing_count"], 1)

    def test_a_drop_that_recovers_is_not_a_pot(self):
        rack = [ball("white", 60 + slot * 40, 100) for slot in range(10)]
        records = [record(index * 0.0667, list(rack)) for index in range(45)]
        records.append(record(3.0, [ball("white", 60 + slot * 40, 100) for slot in range(9)]))
        records += [record(3.07 + index * 0.0667, list(rack)) for index in range(6)]
        self.assertEqual([c for c in raw_candidates(records, H, CFG) if c["type"] == "pot"], [])

    def test_a_collapse_is_ranked_below_a_single_ball_near_a_pocket(self):
        single = {"type": "pot", "census_drop": 1, "pocket_dist_mm": 60, "missing_count": 1}
        collapse = {"type": "pot", "census_drop": 14, "pocket_dist_mm": 40, "missing_count": 12}
        self.assertGreater(pot_strength(single), pot_strength(collapse))
        self.assertLess(pot_strength(collapse), 0)

    def test_shot_strength_prefers_a_real_matched_pair(self):
        from src.candidate_scan import shot_strength
        paired = {"type": "shot", "disp_mm": 900, "from_mm": [1, 1], "motion": 25, "source": "pair"}
        motion = {"type": "shot", "disp_mm": 900, "from_mm": [1, 1], "motion": 25, "source": "motion"}
        self.assertGreater(shot_strength(paired), shot_strength(motion))

    def test_a_pair_without_cloth_motion_ranks_below_one_with_it(self):
        from src.candidate_scan import shot_strength
        moving = {"type": "shot", "disp_mm": 600, "from_mm": [1, 1], "source": "pair",
                  "record": {"motion": 14.0}}
        chance = {"type": "shot", "disp_mm": 733, "from_mm": [1, 1], "source": "pair",
                  "record": {"motion": 1.2}}
        self.assertGreater(shot_strength(moving), shot_strength(chance))


class PruneTests(unittest.TestCase):
    def _shot(self, t, person=0.0, cloth=150000, motion=25.0):
        return {"type": "shot", "source": "motion", "t": t, "color": "white",
                "disp_mm": 700, "from_mm": [100.0, 100.0], "to_mm": [500.0, 900.0],
                "motion": motion,
                "record": {"t": t, "n": 10, "cloth_area": cloth, "brightness": 100.0,
                           "motion": motion, "person_share": person}}

    def test_a_person_on_the_cloth_drops_the_candidate(self):
        records = [record(index * 0.0667, [ball("white", 60, 100)] * 1) for index in range(60)]
        result = prune([self._shot(1.0, person=0.35), self._shot(2.0)], records, CFG, dedup_s=0.0)
        self.assertEqual([c["t"] for c in result["kept"]], [2.0])
        self.assertEqual(result["dropped"][0]["drop_reasons"], ["person_on_cloth"])

    def test_a_cloth_area_collapse_drops_the_candidate(self):
        records = [record(index * 0.0667, [ball("white", 60, 100)], cloth_area=150000)
                   for index in range(60)]
        records[30] = record(30 * 0.0667, [ball("white", 60, 100)], cloth_area=20000)
        result = prune([self._shot(records[30]["t"])], records, CFG, dedup_s=0.0)
        self.assertEqual(result["kept"], [])
        self.assertIn("cloth_area_out_of_band", result["dropped"][0]["drop_reasons"])

    def test_same_act_candidates_are_deduped_and_ranked(self):
        records = [record(index * 0.0667, [ball("white", 60, 100)]) for index in range(60)]
        weak = self._shot(1.0, motion=20.0)
        strong = self._shot(2.0, motion=40.0)
        other = {"type": "shot", "source": "pair", "t": 30.0, "color": "blue",
                 "disp_mm": 400, "from_mm": [10.0, 10.0], "to_mm": [400.0, 500.0],
                 "record": dict(weak["record"], t=30.0)}
        result = prune([weak, strong, other], records, CFG, dedup_s=4.0)
        self.assertEqual(result["counts"]["after_dedup"], 2)
        self.assertEqual(result["kept"][0]["t"], 2.0)          # strongest first
        self.assertEqual(result["kept"][0].get("duplicates", 1), 2)


class PersonShareOwnerTests(unittest.TestCase):
    """The person-share gate has one home: the ``ScanConfig`` field of this module."""

    def test_motion_scan_reads_the_gate_from_this_owner(self):
        from src import motion_scan
        self.assertEqual(motion_scan.person_share_max(), ScanConfig.person_share)
        with mock.patch.object(ScanConfig, "person_share", 0.75):
            self.assertEqual(motion_scan.person_share_max(), 0.75,
                             "motion_scan copied the number instead of reading it")

    def test_the_enforcement_site_reads_the_gate_from_its_config(self):
        records = [record(index * 0.0667, [ball("white", 60, 100)]) for index in range(60)]
        shot = {"type": "shot", "source": "motion", "t": 1.0, "color": "white",
                "disp_mm": 700, "from_mm": [100.0, 100.0], "to_mm": [500.0, 900.0],
                "motion": 25.0,
                "record": {"t": 1.0, "n": 10, "cloth_area": 150000, "brightness": 100.0,
                           "motion": 25.0, "person_share": 0.03}}
        result = prune([shot], records, ScanConfig(person_share=0.05), dedup_s=0.0)
        self.assertEqual(result["dropped"], [], "0.03 overlap is under the 0.05 gate")
        result = prune([shot], records, ScanConfig(person_share=0.01), dedup_s=0.0)
        self.assertEqual(result["dropped"][0]["drop_reasons"], ["person_on_cloth"])


class PlanTests(unittest.TestCase):
    def test_every_window_gets_both_sides_and_cached_frames_are_free(self):
        kept = [{"type": "pot", "t": 100.0, "census_drop": 1, "pocket_dist_mm": 50, "missing_count": 1},
                {"type": "shot", "t": 200.0, "disp_mm": 800, "from_mm": [1, 1], "to_mm": [2, 2]}]
        plan = plan_sam3(kept, top_pots=1, top_shots=1, cached=[98.75, 99.5])
        self.assertEqual([f["t"] for f in plan["frames"]],
                         [98.75, 99.5, 100.8, 101.6, 199.0, 199.5, 200.6, 201.6])
        self.assertEqual([f["t"] for f in plan["frames"] if f["cached"]], [98.75, 99.5])
        self.assertEqual(plan["to_buy"], [100.8, 101.6, 199.0, 199.5, 200.6, 201.6])
        self.assertEqual(plan["pot_windows"], 1)
        self.assertEqual(plan["shot_windows"], 1)

    def test_a_weak_collapse_is_not_planned(self):
        kept = [{"type": "pot", "t": 10.0, "census_drop": 12, "pocket_dist_mm": 40,
                 "missing_count": 11},
                {"type": "pot", "t": 20.0, "census_drop": 1, "pocket_dist_mm": 90,
                 "missing_count": 1}]
        plan = plan_sam3(kept, top_pots=2, top_shots=0)
        self.assertEqual([entry["t"] for entry in plan["plan"]], [20.0, 10.0])


class SelectionTests(unittest.TestCase):
    def test_selected_candidates_carry_ids_above_the_served_range(self):
        from src.candidate_scan import select_for_gating
        pot = {"type": "pot", "t": 100.0, "census_drop": 1, "pocket_dist_mm": 50,
               "missing_count": 1, "source": "census", "last_mm": [10.0, 10.0]}
        shot = {"type": "shot", "t": 200.0, "disp_mm": 800, "from_mm": [1, 1], "to_mm": [2, 2],
                "source": "motion"}
        spare = dict(shot, t=300.0, source="pair")
        plan = plan_sam3([pot, shot, spare], top_pots=1, top_shots=1)
        selected = select_for_gating([pot, shot, spare], plan, controls=1)
        self.assertEqual(sorted(c["measured"] for c in selected), ["classical", "sam3", "sam3"])
        for candidate in selected:
            self.assertGreater(candidate["id"], 1000)
            self.assertEqual(candidate["source"], "info-complete")   # queue schema
            self.assertIn(candidate["origin"], ("census", "motion", "pair"))
            self.assertEqual(len(candidate["window_s"]), 2)

    def test_frames_already_cached_are_not_bought_again(self):
        pot = {"type": "pot", "t": 100.0, "census_drop": 1, "pocket_dist_mm": 50,
               "missing_count": 1, "source": "census"}
        plan = plan_sam3([pot], top_pots=1, top_shots=0, cached=[98.75])
        self.assertNotIn(98.75, plan["to_buy"])
        self.assertEqual(len(plan["to_buy"]), 3)


if __name__ == "__main__":
    unittest.main()
