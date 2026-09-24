"""ball_fp_audit contract: the verdict rules, the radius, the mirror test, the crop.

Everything here is synthetic -- instances, peaks, thresholds and a black frame --
so the decision rules that turn a SAM3 sweep into a verdict are pinned without a
70 s model load, a GPU or the 690 MB recording.  The rule that matters most is the
three-way split: an unmeasured frame and a gated-out blob must both come back
``unresolved``, never ``student_hallucination``, because "SAM3 had nothing to say
here" is not the same claim as "SAM3 looked and found no ball".
"""
import json
import math
import unittest
from pathlib import Path

import numpy as np

from src.ball_fp_audit import (AUDIT, BALL_AREA_RANGE, BALL_R_RANGE, CANDIDATE_RADIUS_PX,
                              CASES_OUT, FN_THRESHOLDS, MATCH_TOL_PX, PRODUCTION_CUT,
                              SAM3_FLOOR, SWEEP_THRESHOLDS, _sweep_instances, admit,
                              adjudicate_fp, cache_agreement, case_times, crop_bounds,
                              headline, instances_near, markdown_table, nearest_label,
                              percentile, recover_fn, recovery_by_threshold, render_case,
                              verdict_counts)

ROOT = Path(__file__).resolve().parent.parent


def inst(x, y, score, r=8.0, area=200.0, in_cloth=True):
    return {"x": float(x), "y": float(y), "score": float(score), "r": float(r),
            "area": float(area), "in_cloth": bool(in_cloth)}


def case(x=100.0, y=100.0, t=10.0, case_id="fp01"):
    return {"id": case_id, "t": t, "x": float(x), "y": float(y),
            "student_score": 0.53, "labels_in_frame": []}


class ConstantsTest(unittest.TestCase):
    def test_the_admission_gate_has_not_drifted_from_the_teacher(self):
        """The gate is copied, so it must be checked against the module that owns it."""
        from src.sam3_ball_cache import MAX_AREA, MAX_R, MIN_AREA, MIN_R, MIN_SCORE
        self.assertEqual(BALL_AREA_RANGE, (MIN_AREA, MAX_AREA))
        self.assertEqual(BALL_R_RANGE, (MIN_R, MAX_R))
        self.assertEqual(PRODUCTION_CUT, MIN_SCORE)

    def test_the_processor_floor_sits_below_every_sweep_threshold(self):
        """Otherwise the 0.20 row would be a clipped measurement, not a real one."""
        self.assertLess(SAM3_FLOOR, min(SWEEP_THRESHOLDS))

    def test_the_fn_sweep_contains_the_operating_threshold(self):
        self.assertIn(0.425, FN_THRESHOLDS)

    def test_the_radius_is_the_small_one_the_directive_named(self):
        self.assertEqual(CANDIDATE_RADIUS_PX, 10.0)
        self.assertEqual(MATCH_TOL_PX, 6.0)


class InstancesNearTest(unittest.TestCase):
    def test_nearest_first_and_radius_is_inclusive(self):
        rows = instances_near([inst(105, 100, 0.4), inst(110, 100, 0.3),
                               inst(100, 100, 0.9)], 100, 100, 10.0)
        self.assertEqual([round(d, 3) for d, _ in rows], [0.0, 5.0, 10.0])

    def test_outside_the_radius_is_dropped(self):
        rows = instances_near([inst(110.5, 100, 0.9)], 100, 100, 10.0)
        self.assertEqual(rows, [])

    def test_an_empty_sweep_is_not_an_error(self):
        self.assertEqual(instances_near([], 100, 100, 10.0), [])
        self.assertEqual(instances_near(None, 100, 100, 10.0), [])


class NearestLabelTest(unittest.TestCase):
    """The duplicate flag must only fire inside the match tolerance."""

    def truth(self):
        return [{"x": 100.0, "y": 100.0, "score": 0.8}, {"x": 300.0, "y": 300.0,
                                                        "score": 0.7}]

    def test_a_second_peak_on_a_claimed_ball_is_a_duplicate(self):
        truth = self.truth()
        _label, distance, duplicate = nearest_label(truth, 103.0, 100.0, {id(truth[0])})
        self.assertAlmostEqual(distance, 3.0, places=2)
        self.assertTrue(duplicate)

    def test_a_label_far_away_is_not_a_duplicate_however_matched_it_is(self):
        """The bug this pins: 79 px is a different ball, not an already-claimed one."""
        truth = self.truth()
        _label, distance, duplicate = nearest_label(truth, 179.0, 100.0, {id(truth[0])})
        self.assertAlmostEqual(distance, 79.0, places=2)
        self.assertFalse(duplicate)

    def test_a_label_inside_the_tolerance_that_was_never_matched_is_not_a_duplicate(self):
        truth = self.truth()
        _label, _distance, duplicate = nearest_label(truth, 103.0, 100.0, set())
        self.assertFalse(duplicate)

    def test_exactly_the_tolerance_counts_as_a_duplicate(self):
        truth = self.truth()
        self.assertTrue(nearest_label(truth, 106.0, 100.0, {id(truth[0])})[2])
        self.assertFalse(nearest_label(truth, 106.1, 100.0, {id(truth[0])})[2])

    def test_no_labels_at_all_is_not_a_duplicate(self):
        label, distance, duplicate = nearest_label([], 100.0, 100.0, set())
        self.assertIsNone(label)
        self.assertIsNone(distance)
        self.assertFalse(duplicate)


class AdmitTest(unittest.TestCase):
    def test_a_normal_ball_passes(self):
        self.assertEqual(admit(inst(100, 100, 0.8)), (True, "admitted"))

    def test_each_gate_failure_names_itself(self):
        self.assertEqual(admit(inst(1, 1, 0.8, area=10))[1], "area_too_small")
        self.assertEqual(admit(inst(1, 1, 0.8, area=1e5))[1], "area_too_large")
        self.assertEqual(admit(inst(1, 1, 0.8, r=1.0))[1], "radius_too_small")
        self.assertEqual(admit(inst(1, 1, 0.8, r=90.0))[1], "radius_too_large")
        self.assertEqual(admit(inst(1, 1, 0.8, in_cloth=False))[1], "off_cloth")


class AdjudicateFpTest(unittest.TestCase):
    def test_a_low_score_instance_is_teacher_recall_below_the_cut(self):
        row = adjudicate_fp(case(), [inst(103, 100, 0.58)])
        self.assertEqual(row["verdict"], "teacher_recall")
        self.assertEqual(row["reason"], "instance_below_production_cut")
        self.assertAlmostEqual(row["nearest_offset_px"], 3.0, places=2)
        self.assertAlmostEqual(row["found_score"], 0.58, places=3)
        # present at 0.20/0.35/0.50 but never at the production cut
        self.assertEqual(row["present_at_thresholds"], [0.2, 0.35, 0.5])
        self.assertEqual(row["highest_threshold_present"], 0.5)

    def test_an_instance_above_the_cut_is_still_teacher_recall(self):
        """A near-miss the teacher did store: the label was claimed elsewhere."""
        row = adjudicate_fp(case(), [inst(100, 108, 0.71)])
        self.assertEqual(row["verdict"], "teacher_recall")
        self.assertEqual(row["reason"], "instance_at_or_above_production_cut")
        self.assertEqual(row["highest_threshold_present"], 0.62)

    def test_nothing_at_all_is_a_hallucination(self):
        row = adjudicate_fp(case(), [inst(200, 200, 0.9), inst(100, 140, 0.7)])
        self.assertEqual(row["verdict"], "student_hallucination")
        self.assertEqual(row["reason"], "no_instance_within_radius_at_any_threshold")
        self.assertEqual(row["instances_within_radius"], 0)

    def test_a_gated_out_blob_is_unresolved_not_a_hallucination(self):
        row = adjudicate_fp(case(), [inst(102, 100, 0.55, in_cloth=False)])
        self.assertEqual(row["verdict"], "unresolved")
        self.assertEqual(row["reason"], "instance_present_but_failed_gate")
        self.assertEqual(row["instances"][0]["in_cloth"], False)
        self.assertFalse(row["instances"][0]["admitted"])

    def test_an_unmeasured_frame_is_unresolved_never_a_hallucination(self):
        row = adjudicate_fp(case(), None)
        self.assertEqual(row["verdict"], "unresolved")
        self.assertEqual(row["reason"], "frame_not_measured")
        self.assertFalse(row["measured"])

    def test_below_the_lowest_sweep_threshold_is_unresolved(self):
        """SAM3 emitted something, but the audit refuses to call 0.19 a ball."""
        row = adjudicate_fp(case(), [inst(101, 100, 0.19)])
        self.assertEqual(row["verdict"], "unresolved")
        self.assertEqual(row["reason"], "only_instances_below_the_lowest_sweep_threshold")

    def test_the_best_admitted_instance_wins_over_a_closer_rejected_one(self):
        row = adjudicate_fp(case(), [inst(100.5, 100, 0.9, in_cloth=False),
                                     inst(104, 100, 0.5)])
        self.assertEqual(row["verdict"], "teacher_recall")
        self.assertAlmostEqual(row["found_offset_px"], 4.0, places=2)

    def test_a_close_lower_score_beats_a_far_higher_one(self):
        """Nearest-first: 2 px at 0.30 is the same ball, 9 px at 0.90 may not be."""
        row = adjudicate_fp(case(), [inst(109, 100, 0.90), inst(102, 100, 0.30)])
        self.assertAlmostEqual(row["found_offset_px"], 2.0, places=2)
        self.assertAlmostEqual(row["found_score"], 0.30, places=3)

    def test_the_case_is_carried_through_for_the_crop(self):
        row = adjudicate_fp(case(x=500.0, y=300.0, t=1078.1, case_id="fp09"),
                            [inst(503, 300, 0.4)])
        self.assertEqual(row["id"], "fp09")
        self.assertEqual(row["t"], 1078.1)
        self.assertEqual(row["x"], 500.0)
        for key in ("instances", "nearest_offset_px", "nearest_offset_score", "measured"):
            self.assertIn(key, row)


class RecoverFnTest(unittest.TestCase):
    def fn(self, x=100.0, y=100.0, t=10.0, case_id="fn01"):
        return {"id": case_id, "t": t, "x": x, "y": y, "teacher_score": 0.79, "r": 8.0}

    def test_a_peak_inside_the_tolerance_recovers_it(self):
        row = recover_fn(self.fn(), [(103.0, 100.0, 0.2)])
        self.assertTrue(row["recovered"])
        self.assertAlmostEqual(row["nearest_peak_px"], 3.0, places=2)

    def test_exactly_the_tolerance_recovers_and_just_outside_does_not(self):
        self.assertTrue(recover_fn(self.fn(), [(106.0, 100.0, 0.2)])["recovered"])
        self.assertFalse(recover_fn(self.fn(), [(106.1, 100.0, 0.2)])["recovered"])

    def test_the_nearest_peak_is_the_one_reported(self):
        row = recover_fn(self.fn(), [(140.0, 100.0, 0.9), (112.0, 100.0, 0.1)])
        self.assertAlmostEqual(row["nearest_peak_px"], 12.0, places=2)
        self.assertEqual(row["recovered"], False)

    def test_no_peaks_at_all_is_not_an_error(self):
        row = recover_fn(self.fn(), [])
        self.assertIsNone(row["nearest_peak_px"])
        self.assertFalse(row["recovered"])


class RecoverySweepTest(unittest.TestCase):
    def test_entry_threshold_is_the_highest_one_that_recovers(self):
        rows = [{"id": "fn01", "t": 10.0, "x": 100.0, "y": 100.0},
                {"id": "fn02", "t": 20.0, "x": 50.0, "y": 50.0}]
        # fn01 comes back only at 0.10 and below; fn02 comes back at 0.30 and below
        peaks = {0.1: {10.0: [(100.0, 100.0, 0.3)], 20.0: [(50.0, 50.0, 0.3)]},
                 0.2: {10.0: [(100.0, 100.0, 0.3)], 20.0: [(50.0, 50.0, 0.3)]},
                 0.3: {10.0: [], 20.0: [(50.0, 50.0, 0.3)]},
                 0.4: {10.0: [], 20.0: []}}
        rows_out, entry = recovery_by_threshold(rows, peaks, (0.1, 0.2, 0.3, 0.4))
        self.assertEqual(entry, {"fn01": 0.2, "fn02": 0.3})
        self.assertEqual([r["recovered"] for r in rows_out], [2, 2, 1, 0])
        self.assertEqual(rows_out[0]["of"], 2)

    def test_localisation_is_reported_for_the_recovered_ones(self):
        rows = [{"id": "fn01", "t": 10.0, "x": 100.0, "y": 100.0}]
        peaks = {0.2: {10.0: [(102.0, 100.0, 0.3)]}}
        out, _entry = recovery_by_threshold(rows, peaks, (0.2,))
        self.assertEqual(out[0]["localisation_px_median"], 2.0)
        self.assertEqual(out[0]["localisation_px_p90"], 2.0)

    def test_a_threshold_with_no_recovery_reports_none_not_zero(self):
        rows = [{"id": "fn01", "t": 10.0, "x": 100.0, "y": 100.0}]
        out, _entry = recovery_by_threshold(rows, {0.2: {10.0: []}}, (0.2,))
        self.assertEqual(out[0]["recovered"], 0)
        self.assertIsNone(out[0]["localisation_px_median"])


class CountingTest(unittest.TestCase):
    def rows(self, *verdicts):
        return [{"verdict": v, "reason": ("instance_below_production_cut"
                                          if v == "teacher_recall" else "x")}
                for v in verdicts]

    def test_counts_split_the_three_verdicts(self):
        counts = verdict_counts(self.rows("teacher_recall", "teacher_recall",
                                          "student_hallucination", "unresolved"))
        self.assertEqual(counts, {"teacher_recall": 2, "student_hallucination": 1,
                                  "unresolved": 1})

    def test_headline_separates_below_cut_recall_from_near_misses(self):
        head = headline(self.rows("teacher_recall", "teacher_recall",
                                  "student_hallucination"), [], [])
        self.assertEqual(head["fp_total"], 3)
        self.assertEqual(head["teacher_recall"], 2)
        self.assertEqual(head["teacher_recall_below_cut"], 2)
        self.assertEqual(head["teacher_recall_at_or_above_cut"], 0)
        self.assertEqual(head["student_hallucination"], 1)
        self.assertEqual(head["unresolved"], 0)

    def test_headline_reads_both_operating_and_best_recovery(self):
        recovery = [{"threshold": 0.425, "recovered": 7, "of": 22},
                    {"threshold": 0.3, "recovered": 15, "of": 22}]
        head = headline([], [], recovery)
        self.assertEqual(head["fn_recovered_at_operating_threshold"], 7)
        self.assertEqual(head["fn_recovered_best"], 15)
        self.assertEqual(head["fn_recovered_best_threshold"], 0.3)

    def test_percentile_is_nearest_rank(self):
        values = [float(i) for i in range(1, 11)]
        self.assertEqual(percentile(values, 50), 5.0)
        self.assertEqual(percentile(values, 90), 9.0)
        self.assertEqual(percentile(values, 100), 10.0)
        self.assertTrue(math.isnan(percentile([], 90)))


class TableTest(unittest.TestCase):
    def test_one_row_per_case_and_the_verdict_is_visible(self):
        fp = [adjudicate_fp(case(case_id="fp01"), [inst(101, 100, 0.5)]),
              adjudicate_fp(case(case_id="fp02", x=200.0), [])]
        fn = [{"id": "fn01", "t": 10.0, "teacher_score": 0.79, "x": 1.0, "y": 1.0,
               "nearest_peak_px_at_operating": 12.3, "recovered_at": 2.1}]
        table = markdown_table(fp, fn, {"fn01": 0.3})
        self.assertIn("fp01", table)
        self.assertIn("fp02", table)
        self.assertIn("teacher_recall", table)
        self.assertIn("student_hallucination", table)
        self.assertIn("fn01", table)
        self.assertIn("0.300", table)
        # header + separator + 2 fp rows, then header + separator + 1 fn row
        self.assertEqual(len([l for l in table.splitlines() if l.startswith("| fp")]), 2)
        self.assertEqual(len([l for l in table.splitlines() if l.startswith("| fn")]), 1)

    def test_every_cell_is_present_even_when_the_row_is_empty(self):
        fp = [adjudicate_fp(case(), None)]
        table = markdown_table(fp, [], {})
        for line in table.splitlines():
            if line.startswith("| fp"):
                self.assertEqual(len(line.split("|")), 11)   # 9 cells + 2 edge empties


class SweepLookupTest(unittest.TestCase):
    def test_a_measured_frame_returns_its_instances(self):
        frames = {"10.0": {"instances": [inst(1, 1, 0.5)]}}
        self.assertEqual(len(_sweep_instances(frames, 10.0)), 1)

    def test_a_failed_frame_returns_none_not_an_empty_list(self):
        """An error row must read as 'not measured', or it becomes a hallucination."""
        frames = {"10.0": {"error": "RuntimeError: no frame"}}
        self.assertIsNone(_sweep_instances(frames, 10.0))
        self.assertIsNone(_sweep_instances(frames, 99.0))


class CacheAgreementTest(unittest.TestCase):
    def test_a_reproduced_frame_agrees(self):
        instances = [inst(100.0, 100.0, 0.9), inst(300.0, 200.0, 0.8),
                     inst(400.0, 200.0, 0.5)]          # the 0.5 one is below the cut
        cached = {10.0: [{"img": [100.0, 100.0]}, {"img": [300.0, 200.0]}]}
        row = cache_agreement(10.0, instances, cached)
        self.assertTrue(row["agrees"])
        self.assertEqual(row["measured_admitted_at_cut"], 2)

    def test_a_missing_stored_ball_is_reported(self):
        cached = {10.0: [{"img": [100.0, 100.0]}, {"img": [999.0, 999.0]}]}
        row = cache_agreement(10.0, [inst(100.0, 100.0, 0.9)], cached)
        self.assertFalse(row["agrees"])
        self.assertEqual(row["cached_unmatched"], 1)

    def test_an_extra_admitted_ball_is_reported(self):
        cached = {10.0: [{"img": [100.0, 100.0]}]}
        row = cache_agreement(10.0, [inst(100.0, 100.0, 0.9), inst(500.0, 100.0, 0.7)],
                              cached)
        self.assertFalse(row["agrees"])
        self.assertEqual(row["measured_extra"], 1)

    def test_a_frame_the_teacher_never_cached_is_not_a_failure(self):
        self.assertEqual(cache_agreement(10.0, [], {})["cached_row"], None)


class CasePlumbingTest(unittest.TestCase):
    def test_case_frames_are_deduplicated_and_numeric(self):
        cases = {"fp": [{"t": 10.0}, {"t": 10.0}, {"t": 2.5}],
                 "fn": [{"t": 10.0}, {"t": 20.0}]}
        self.assertEqual(case_times(cases), [2.5, 10.0, 20.0])


class CropTest(unittest.TestCase):
    def test_bounds_clamp_inside_the_frame(self):
        shape = (720, 1280, 3)
        self.assertEqual(crop_bounds(640, 360, 90, shape), (550, 270, 730, 450))
        x0, y0, x1, y1 = crop_bounds(5, 5, 90, shape)
        self.assertEqual((x0, y0), (0, 0))
        self.assertEqual(x1 - x0, 180)
        x0, y0, x1, y1 = crop_bounds(1279, 719, 90, shape)
        self.assertEqual((x1, y1), (1280, 720))

    def test_a_crop_carries_its_case_and_is_written(self):
        bgr = np.zeros((720, 1280, 3), np.uint8)
        bgr[340:380, 620:660] = 200                    # something to look at
        image = render_case(
            bgr, case(x=640.0, y=360.0), half=90, scale=2,
            title="fp01 FP t=10.0s", subtitle="instance_below_production_cut",
            student_peaks=[(640.0, 360.0, 0.53)],
            teacher_labels=[[700.0, 360.0, 8.0]],
            instances=[{"x": 643.0, "y": 360.0, "score": 0.58, "r": 8.0, "area": 200.0,
                        "in_cloth": True}],
            extra_peaks=[(640.0, 362.0, 0.2)])
        self.assertEqual(image.shape[0], 74 + 180 * 2)          # band + cropped height
        self.assertEqual(image.shape[1], 180 * 2)
        self.assertTrue(image[40:60, 8:80].any())              # the title band is drawn

    def test_a_crop_with_nothing_near_it_still_renders(self):
        bgr = np.zeros((720, 1280, 3), np.uint8)
        image = render_case(bgr, case(x=10.0, y=10.0), half=90, scale=1,
                            title="fp02 FP", subtitle="no_instance_within_radius_at_any_threshold",
                            student_peaks=[], teacher_labels=[], instances=[])
        self.assertGreater(image.size, 0)


class FrozenEvidenceTest(unittest.TestCase):
    """If the audit has been run, it must be adjudicating the published errors."""

    def setUp(self):
        if not CASES_OUT.exists():
            self.skipTest("the audit has not been run in this checkout")

    def test_the_reproduced_counts_match_the_frozen_report(self):
        cases = json.loads(CASES_OUT.read_text())
        prov = cases["provenance"]
        report = json.loads((ROOT / "out" / "tiny_ball_probe"
                             / "report_960x540.json").read_text())
        self.assertEqual(len(cases["fp"]), report["operating"]["fp"])
        self.assertEqual(len(cases["fn"]), report["operating"]["fn"])
        self.assertEqual(prov["threshold"], report["operating"]["threshold"])
        self.assertEqual(prov["held_frames"], report["held_frames"])

    def test_every_case_carries_the_geometry_a_crop_needs(self):
        cases = json.loads(CASES_OUT.read_text())
        for row in cases["fp"] + cases["fn"]:
            for key in ("id", "t", "x", "y", "labels_in_frame"):
                self.assertIn(key, row)
            self.assertIsInstance(row["labels_in_frame"], list)

    def test_verdicts_covers_exactly_the_cases(self):
        path = AUDIT / "verdicts.json"
        if not path.exists():
            self.skipTest("verdicts have not been computed")
        cases = json.loads(CASES_OUT.read_text())
        verdicts = json.loads(path.read_text())
        self.assertEqual([r["id"] for r in verdicts["fp"]],
                         [r["id"] for r in cases["fp"]])
        self.assertEqual([r["id"] for r in verdicts["fn"]],
                         [r["id"] for r in cases["fn"]])
        for row in verdicts["fp"]:
            self.assertIn(row["verdict"],
                          ("teacher_recall", "student_hallucination", "unresolved"))
        counts = verdict_counts(verdicts["fp"])
        self.assertEqual(sum(counts.values()), len(cases["fp"]))
        self.assertEqual(counts, {k: verdicts["headline"][k] for k in counts})

    def test_every_unresolved_fp_says_which_kind_of_unresolved_it_is(self):
        path = AUDIT / "verdicts.json"
        if not path.exists():
            self.skipTest("verdicts have not been computed")
        verdicts = json.loads(path.read_text())
        for row in verdicts["fp"]:
            if row["verdict"] == "unresolved":
                self.assertIn(row["reason"], ("frame_not_measured",
                                              "instance_present_but_failed_gate",
                                              "only_instances_below_the_lowest_sweep_threshold"))

    def test_a_teacher_recall_verdict_carries_the_instance_that_justifies_it(self):
        path = AUDIT / "verdicts.json"
        if not path.exists():
            self.skipTest("verdicts have not been computed")
        verdicts = json.loads(path.read_text())
        for row in verdicts["fp"]:
            if row["verdict"] != "teacher_recall":
                continue
            self.assertIsNotNone(row["found_score"])
            self.assertLessEqual(row["found_offset_px"], CANDIDATE_RADIUS_PX)
            self.assertTrue(row["instances"])


if __name__ == "__main__":
    unittest.main()
