"""eval_faces tests: pure functions and synthetic data — no models, no VOD, no network."""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.eval_faces import (
    DATASETS,
    label_role_probes,
    role_medoid,
    PROTECTED,
    _medoid,
    analyse,
    assign_tracklets,
    box_foot,
    burst_frames,
    center_inside,
    detectability,
    digest,
    end_points,
    evaluate_binding,
    face_crop,
    height_bucket,
    iou,
    load_corners,
    md5_files,
    pair_stats,
    pick_demo_window,
    quality_faces,
    role_pairs,
    scratch_root,
    separation,
    serve,
    table_role,
)

DIM = 512
VOD30_CORNERS = [[459.25762939453125, 268.89312744140625], [803.74755859375, 315.7756652832031],
                 [1023.367431640625, 584.2617797851562], [421.8110046386719, 560.5725708007812]]


def unit(seed=1):
    rng = np.random.RandomState(seed)
    v = rng.standard_normal(DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def at(base, sim, seed=2):
    """Unit vector whose cosine with `base` is `sim`."""
    rng = np.random.RandomState(seed)
    other = rng.standard_normal(DIM).astype(np.float32)
    other -= base * float(np.dot(base, other))
    other /= np.linalg.norm(other)
    return (base * sim + other * math.sqrt(max(0.0, 1.0 - sim * sim))).astype(np.float32)


def face(bbox, eye=12.0, det=0.8, quality=True, embedding=None):
    vector = unit(1) if embedding is None else np.asarray(embedding, np.float32)
    return {"bbox": list(bbox), "eye_px": eye, "det_score": det, "quality": quality,
            "inside": True, "embedding": vector.tolist()}


def record(person, faces, burst=0, frame_index=0, dataset="vod30", tracklet="t1", role="left"):
    return {"dataset": dataset, "burst": burst, "frame_index": frame_index, "t": frame_index / 30.0,
            "person": list(person), "person_score": 0.9, "person_h": person[3] - person[1],
            "role": role, "segment": 0, "tracklet": tracklet, "faces": faces}


class BurstPlanTest(unittest.TestCase):
    def test_anchors_are_evenly_spread_and_sorted(self):
        plan = burst_frames(1000, anchors=4, burst=2, spacing=10, start=100)
        self.assertEqual(plan, sorted(plan))
        self.assertEqual(len(plan), 8)
        self.assertEqual(plan[0], 100)
        self.assertLessEqual(plan[-1], 999)

    def test_burst_frames_spacing_and_no_duplicates(self):
        plan = burst_frames(1000, anchors=2, burst=3, spacing=15, start=0)
        self.assertEqual(len(plan), len(set(plan)))
        self.assertEqual(plan[1] - plan[0], 15)

    def test_out_of_range_tail_is_dropped(self):
        plan = burst_frames(frame_count=25, anchors=1, burst=5, spacing=10, start=0)
        self.assertEqual(plan, [0, 10, 20])

    def test_degenerate_inputs_are_empty(self):
        for args in ((0, 1, 1, 1, 0), (100, 0, 1, 1, 0), (100, 1, 0, 1, 0), (100, 1, 1, 0, 0)):
            self.assertEqual(burst_frames(*args), [])


class GeometryTest(unittest.TestCase):
    def test_iou_identity_and_disjoint(self):
        box = [0, 0, 10, 10]
        self.assertAlmostEqual(iou(box, box), 1.0)
        self.assertEqual(iou(box, [20, 20, 30, 30]), 0.0)

    def test_center_inside_and_foot(self):
        self.assertTrue(center_inside([40, 40, 60, 60], [0, 0, 100, 200]))
        self.assertFalse(center_inside([140, 40, 160, 60], [0, 0, 100, 200]))
        self.assertEqual(box_foot([10, 20, 30, 80]), (20.0, 80.0))

    def test_height_bucket_boundaries(self):
        self.assertEqual(height_bucket(249), "far")
        self.assertEqual(height_bucket(250), "mid")
        self.assertEqual(height_bucket(399.9), "mid")
        self.assertEqual(height_bucket(400), "near")
        self.assertEqual(height_bucket(5000), "near")

    def test_table_role_uses_the_short_edges(self):
        left_end, right_end = end_points(VOD30_CORNERS)
        self.assertLess(left_end[0], right_end[0])
        self.assertEqual(table_role([280, 115, 420, 437], VOD30_CORNERS), "left")
        self.assertEqual(table_role([796, 197, 928, 418], VOD30_CORNERS), "right")

    def test_table_role_without_corners_is_none(self):
        self.assertIsNone(table_role([0, 0, 10, 10], None))
        self.assertIsNone(end_points([[0, 0], [1, 1]]))

    def test_load_corners_returns_the_vod30_quad(self):
        corners = load_corners("scan30")
        self.assertEqual(len(corners), 4)
        self.assertAlmostEqual(corners[0][0], 459.25762939453125)

    def test_face_crop_pads_and_upscales(self):
        frame = np.zeros((200, 200, 3), np.uint8)
        crop = face_crop(frame, [80, 80, 100, 100], pad=0.6)
        # 20px box + 12px pad each side = 44px, upscaled x2
        self.assertEqual(crop.shape[0], 2 * 44)
        self.assertEqual(crop.shape[1], 2 * 44)

    def test_face_crop_clips_at_the_frame_edge(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        crop = face_crop(frame, [0, 0, 10, 10], pad=0.6)
        self.assertEqual(crop.shape[:2], (32, 32))


class TrackletTest(unittest.TestCase):
    def _records(self):
        return [
            record([10, 10, 110, 210], [], frame_index=0),
            record([12, 12, 112, 212], [], frame_index=15),
            record([300, 10, 400, 210], [], frame_index=15),
            record([302, 12, 402, 212], [], frame_index=30),
        ]

    def test_iou_linking_keeps_two_tracklets(self):
        records = self._records()
        self.assertEqual(assign_tracklets(records), 2)
        first = {r["frame_index"]: r["tracklet"] for r in records if r["person"][0] < 200}
        self.assertEqual(len(set(first.values())), 1)

    def test_a_gap_larger_than_max_gap_starts_a_new_tracklet(self):
        records = [record([10, 10, 110, 210], [], frame_index=0),
                   record([11, 11, 111, 211], [], frame_index=500)]
        self.assertEqual(assign_tracklets(records, max_gap=60), 2)

    def test_different_bursts_never_share_a_tracklet(self):
        records = [record([10, 10, 110, 210], [], burst=0, frame_index=0),
                   record([11, 11, 111, 211], [], burst=1, frame_index=15)]
        self.assertEqual(assign_tracklets(records), 2)
        self.assertNotEqual(records[0]["tracklet"], records[1]["tracklet"])


class StatsTest(unittest.TestCase):
    def test_pair_stats_percentiles(self):
        stats = pair_stats([0.0, 0.25, 0.5, 0.75, 1.0])
        self.assertEqual(stats["n"], 5)
        self.assertEqual(stats["median"], 0.5)
        self.assertEqual(stats["min"], 0.0)
        self.assertEqual(stats["max"], 1.0)
        self.assertLess(stats["p05"], stats["p95"])

    def test_pair_stats_empty(self):
        self.assertEqual(pair_stats([])["n"], 0)

    def test_medoid_picks_the_central_point(self):
        base = unit(3)
        points = [(0, 0, ("a",), base), (0, 1, ("b",), at(base, 0.9, 4)),
                  (0, 2, ("c",), at(base, -0.2, 5))]
        # b is closest to the group (0.9 to a, ~-0.18 to c); a loses its -0.2 to c
        self.assertEqual(_medoid(points)[2], ("b",))

    def test_medoid_single_point(self):
        base = unit(3)
        self.assertEqual(_medoid([(0, 0, ("only",), base)])[2], ("only",))


class QualityFaceSelectionTest(unittest.TestCase):
    def test_first_quality_face_inside_the_box_wins(self):
        rec = record([0, 0, 100, 200], [face([10, 10, 30, 30], quality=False),
                                        face([40, 40, 60, 60])])
        self.assertEqual(quality_faces(rec)["bbox"], [40.0, 40.0, 60.0, 60.0])

    def test_a_face_outside_the_person_box_is_not_selected(self):
        rec = record([0, 0, 100, 200], [face([400, 400, 430, 430])])
        self.assertIsNone(quality_faces(rec))

    def test_sub_quality_face_is_not_selected(self):
        rec = record([0, 0, 100, 200], [face([10, 10, 30, 30], quality=False)])
        self.assertIsNone(quality_faces(rec))


class DetectabilityTest(unittest.TestCase):
    def _records(self):
        return [
            # a quality face inside the box, near person
            record([0, 0, 300, 500], [face([100, 100, 130, 140])]),
            # a face detected but below the eye gate
            record([0, 0, 300, 500], [face([100, 100, 120, 125], eye=5.0, quality=False)]),
            # no face at all, far person
            record([0, 0, 120, 200], []),
        ]

    def test_gate_counts_are_per_person_instance(self):
        report = detectability(self._records())
        gate = report["gate_person"]
        self.assertEqual(report["person_instances"], 3)
        self.assertEqual(gate["found_a_face"]["n"], 2)
        self.assertEqual(gate["eye_px_pass"]["n"], 1)
        self.assertEqual(gate["quality_pass"]["n"], 1)
        self.assertEqual(gate["production_selection"]["n"], 1)
        self.assertAlmostEqual(gate["found_a_face"]["rate"], 2 / 3, places=4)

    def test_height_buckets_and_dataset_yield(self):
        report = detectability(self._records())
        self.assertEqual(report["by_height_bucket"]["near"]["person_instances"], 2)
        self.assertEqual(report["by_height_bucket"]["near"]["with_quality_face"], 1)
        self.assertEqual(report["by_dataset"]["vod30"]["person_instances"], 3)

    def test_face_size_distribution_reports_quality_faces(self):
        report = detectability(self._records())
        self.assertEqual(report["face_size_px"]["quality_w"]["n"], 1)
        self.assertEqual(report["face_size_px"]["quality_w"]["median"], 30.0)

    def test_empty_input(self):
        report = detectability([])
        self.assertEqual(report["person_instances"], 0)
        self.assertIsNone(report["gate_person"]["found_a_face"]["rate"])


class SeparationTest(unittest.TestCase):
    def test_within_tracklet_is_high_and_cross_person_is_low(self):
        base = unit(11)
        records = [
            record([0, 0, 100, 200], [face([10, 10, 30, 30], embedding=at(base, 0.9, 12).tolist())],
                   burst=0, frame_index=0, tracklet="a"),
            record([0, 0, 100, 200], [face([10, 10, 30, 30], embedding=at(base, 0.8, 13).tolist())],
                   burst=0, frame_index=15, tracklet="a"),
            record([0, 0, 100, 200], [face([40, 40, 60, 60], embedding=at(base, 0.0, 14).tolist())],
                   burst=0, frame_index=0, tracklet="b"),
        ]
        report = separation(records)
        self.assertEqual(report["within_tracklet"]["n"], 1)
        self.assertGreater(report["within_tracklet"]["median"], 0.6)
        self.assertEqual(report["cross_person_same_frame"]["n"], 1)
        self.assertLess(report["cross_person_same_frame"]["median"], 0.3)

    def test_one_face_claimed_by_two_boxes_is_not_a_cross_person_pair(self):
        shared = face([10, 10, 30, 30])
        records = [
            record([0, 0, 100, 200], [shared], frame_index=0, tracklet="a"),
            record([-50, -50, 150, 250], [shared], frame_index=0, tracklet="b"),
            record([0, 0, 100, 200], [shared], frame_index=15, tracklet="a"),
        ]
        report = separation(records)
        self.assertEqual(report["same_face_pairs_dropped"], 1)
        self.assertEqual(report["cross_person_same_frame"]["n"], 0)
        self.assertEqual(report["faces_claimed_by_both_boxes"], 1)

    def test_accept_rates_against_the_production_threshold(self):
        base = unit(21)
        records = []
        for index, sim in enumerate((0.9, 0.85)):
            records.append(record([0, 0, 100, 200],
                                  [face([10, 10, 30, 30], embedding=at(base, sim, 30 + index).tolist())],
                                  frame_index=index * 15, tracklet="a"))
        reports = separation(records)
        self.assertEqual(reports["accept_rates"]["within_ge_threshold"], 1.0)
        self.assertEqual(reports["accept_rates"]["cross_ge_threshold"], None)
        self.assertEqual(reports["thresholds"]["bind_face_bar"], 0.47)


class RolePairsTest(unittest.TestCase):
    def test_cross_role_same_frame_pairs_the_two_table_ends(self):
        left, right = unit(41), at(unit(41), 0.05, 42)
        records = [
            record([0, 0, 100, 200], [face([10, 10, 30, 30], embedding=left.tolist())],
                   burst=0, frame_index=0, role="left"),
            record([0, 0, 100, 200], [face([40, 40, 60, 60], embedding=right.tolist())],
                   burst=0, frame_index=0, role="right"),
        ]
        report = role_pairs(records)
        self.assertEqual(report["cross_role_same_frame"]["n"], 1)
        self.assertAlmostEqual(report["cross_role_same_frame"]["median"], 0.05, places=3)

    def test_continuity_detects_the_same_person_across_anchors(self):
        base = unit(51)
        records = []
        for burst, sim in ((0, None), (1, 0.8)):
            embedding = base if sim is None else at(base, sim, 52)
            records.append(record([0, 0, 100, 200],
                                  [face([10, 10, 30, 30], embedding=embedding.tolist())],
                                  burst=burst, frame_index=burst * 100, role="left"))
        report = role_pairs(records)
        continuity = report["same_role_consecutive_burst"]
        self.assertEqual(continuity["pairs"], 1)
        self.assertTrue(continuity["rows"][0]["same_person"])
        self.assertAlmostEqual(continuity["rows"][0]["cosine"], 0.8, places=3)

    def test_continuity_reports_a_different_person(self):
        base = unit(61)
        records = [
            record([0, 0, 100, 200], [face([10, 10, 30, 30], embedding=base.tolist())],
                   burst=0, frame_index=0, role="left"),
            record([0, 0, 100, 200], [face([10, 10, 30, 30], embedding=at(base, 0.0, 62).tolist())],
                   burst=1, frame_index=100, role="left"),
        ]
        continuity = role_pairs(records)["same_role_consecutive_burst"]
        self.assertFalse(continuity["rows"][0]["same_person"])
        self.assertEqual(continuity["rate"], 0.0)


class BindingEvaluationTest(unittest.TestCase):
    def _gallery(self):
        left, right = unit(71), unit(72)
        return {"player-left": [{"embedding": left.tolist()}],
                "player-right": [{"embedding": right.tolist()}]}, left, right

    def test_a_clean_same_person_probe_binds(self):
        gallery, left, _right = self._gallery()
        result = evaluate_binding([{"role": "left", "expected": "player-left",
                                    "embedding": at(left, 0.8, 73)}], gallery)
        row = result["rows"][0]
        self.assertEqual(row["matched"], "player-left")
        self.assertTrue(row["accepted_by_best_match"])
        self.assertTrue(row["accepted_by_bind_face"])
        self.assertEqual(result["summary"]["accuracy"], 1.0)

    def test_the_other_player_is_not_bound(self):
        gallery, _left, right = self._gallery()
        result = evaluate_binding([{"expected": "player-left", "role": "right",
                                    "embedding": right}], gallery)
        row = result["rows"][0]
        self.assertEqual(row["matched"], "player-right")
        self.assertNotEqual(row["matched"], row["expected"], "the face never binds as the other player")
        self.assertEqual(result["summary"]["accuracy"], 0.0)
        self.assertEqual(result["summary"]["wrong_player"], 1)

    def test_an_unenrolled_stranger_is_unmatched(self):
        gallery, _left, _right = self._gallery()
        result = evaluate_binding([{"role": "left", "expected": "player-left",
                                    "embedding": unit(90)}], gallery)
        row = result["rows"][0]
        self.assertIsNone(row["matched"], "below the threshold against both players")
        self.assertTrue(row["rejected_below_threshold"])
        self.assertEqual(result["summary"]["unmatched"], 1)

    def test_margin_gate_rejects_an_ambiguous_probe(self):
        gallery, left, _right = self._gallery()
        probe = at(left, 0.5, 75)
        # 0.5 to the left player, 0.4 to the right one: gap 0.1 < 0.12 margin
        del gallery["player-right"]
        gallery["player-right"] = [{"embedding": at(probe, 0.4, 76).tolist()}]
        result = evaluate_binding([{"role": "left", "expected": "player-left", "embedding": probe}], gallery)
        row = result["rows"][0]
        self.assertIsNone(row["matched"])
        self.assertTrue(row["rejected_ambiguous"])
        self.assertFalse(row["accepted_by_bind_face"],
                         "the measured bind gate applies the same margin as best_match")

    def test_measured_bind_gate_is_the_shared_rule(self):
        """evaluate_binding's bind column must not be more permissive than
        IdentityIndex.bind_face: bar = threshold + margin AND the runner-up margin."""
        gallery, left, _right = self._gallery()
        del gallery["player-right"]  # single enrolment: no runner-up at all
        row = evaluate_binding([{"role": "left", "expected": "player-left",
                                 "embedding": at(left, 0.40, 78)}], gallery)["rows"][0]
        self.assertIsNone(row["runner_up"])
        self.assertTrue(row["accepted_by_best_match"], "0.40 clears the 0.35 threshold")
        self.assertFalse(row["accepted_by_bind_face"], "0.40 does not clear the 0.47 bar")
        row = evaluate_binding([{"role": "left", "expected": "player-left",
                                 "embedding": left}], gallery)["rows"][0]
        self.assertTrue(row["accepted_by_bind_face"])
        # two enrolments, same similarity, runner-up inside the margin -> no bind
        gallery, left, _right = self._gallery()
        gallery["player-right"] = [{"embedding": at(left, 0.92, 79).tolist()}]
        row = evaluate_binding([{"role": "left", "expected": "player-left", "embedding": left}], gallery)["rows"][0]
        self.assertIsNotNone(row["runner_up"])
        self.assertLess(row["margin"], 0.12)
        self.assertIsNone(row["matched"])
        self.assertFalse(row["accepted_by_bind_face"])

    def test_the_bind_face_bar_is_higher_than_the_match_threshold(self):
        """The 0.35 threshold and the 0.47 bind_face bar are different gates."""
        gallery, left, _right = self._gallery()
        del gallery["player-right"]
        result = evaluate_binding([{"role": "left", "expected": "player-left",
                                    "embedding": at(left, 0.4, 77)}], gallery)
        row = result["rows"][0]
        self.assertTrue(row["accepted_by_best_match"])
        self.assertFalse(row["accepted_by_bind_face"])
        self.assertEqual(row["similarity"], 0.4)

    def test_no_gallery_means_no_match(self):
        result = evaluate_binding([{"role": "left", "expected": "player-left",
                                    "embedding": unit(78)}], {})
        self.assertIsNone(result["rows"][0]["matched"])
        self.assertEqual(result["summary"]["unmatched"], 1)

    def test_rows_without_an_expected_label_are_not_scored(self):
        gallery, left, _right = self._gallery()
        result = evaluate_binding([{"role": "left", "expected": None, "embedding": at(left, 0.9, 79)}], gallery)
        self.assertEqual(result["summary"]["probes_with_label"], 0)


class RoleMedoidTest(unittest.TestCase):
    def _records(self):
        base = unit(81)
        other = at(base, 0.0, 82)
        return [
            record([0, 0, 100, 200], [face([10, 10, 30, 30], embedding=at(base, 0.9, 83))],
                   burst=6, frame_index=0, role="left"),
            record([0, 0, 100, 200], [face([10, 10, 30, 30], embedding=at(base, 0.85, 84))],
                   burst=6, frame_index=15, role="left"),
            record([0, 0, 100, 200], [face([40, 40, 60, 60], embedding=other)],
                   burst=6, frame_index=30, role="left"),
        ]

    def test_medoid_is_the_recurring_person_not_a_one_off_face(self):
        medoid = role_medoid(self._records(), "vod30", 6, "left")
        self.assertIn(medoid["record"]["frame_index"], (0, 15), "one of the two similar faces")
        self.assertNotEqual(medoid["record"]["frame_index"], 30, "not the orthogonal one-off")
        self.assertEqual(medoid["faces"], 3)

    def test_medoid_of_an_empty_end_is_none(self):
        self.assertIsNone(role_medoid([], "vod30", 6, "left"))
        self.assertIsNone(role_medoid(self._records(), "vod30", 6, "right"))

    def test_probes_label_the_recurring_person_and_the_impostors(self):
        records = self._records() + [
            record([0, 0, 100, 200], [face([10, 10, 30, 30], embedding=at(unit(81), 0.88, 85))],
                   burst=7, frame_index=100, role="left"),
            record([0, 0, 100, 200], [face([40, 40, 60, 60], embedding=at(unit(81), 0.0, 86))],
                   burst=7, frame_index=115, role="left"),
        ]
        probes = label_role_probes(records, "vod30", [7], "left")
        groups = sorted(probe["group"] for probe in probes)
        self.assertEqual(groups, ["impostor_same_end", "same"])
        self.assertEqual([p["expected"] for p in probes if p["group"] == "same"], ["player-left"])

    def test_group_summary_counts_false_matches(self):
        gallery = {"player-left": [{"embedding": unit(91).tolist()}]}
        probes = [{"role": "left", "expected": "player-left", "group": "same", "embedding": unit(91)},
                  {"role": "left", "expected": None, "group": "impostor_same_end", "embedding": unit(91)}]
        summary = evaluate_binding(probes, gallery)["summary"]
        self.assertEqual(summary["by_group"]["same"]["match_rate"], 1.0)
        self.assertEqual(summary["by_group"]["impostor_same_end"]["false_match_rate"], 1.0)


class DemoWindowTest(unittest.TestCase):
    def _analysis(self, rows):
        return {"role_pairs": {"vod30": {"same_role_consecutive_burst": {"rows": rows}}}}

    def test_longest_same_person_run_wins(self):
        rows = [
            {"role": "left", "bursts": [0, 1], "same_person": True},
            {"role": "left", "bursts": [1, 2], "same_person": True},
            {"role": "left", "bursts": [2, 3], "same_person": False},
            {"role": "right", "bursts": [5, 6], "same_person": True},
        ]
        window = pick_demo_window(self._analysis(rows), min_run=3)
        self.assertEqual(window["role"], "left")
        self.assertEqual(window["bursts"], [0, 1, 2])
        self.assertEqual(window["enroll_burst"], 0)
        self.assertEqual(window["holdout_bursts"], [1, 2])

    def test_a_run_shorter_than_min_run_is_refused(self):
        rows = [{"role": "left", "bursts": [0, 1], "same_person": True}]
        self.assertIsNone(pick_demo_window(self._analysis(rows), min_run=3))

    def test_missing_analysis_is_refused(self):
        self.assertIsNone(pick_demo_window({}))
        self.assertIsNone(pick_demo_window({"role_pairs": {}}))


class ScratchIsolationTest(unittest.TestCase):
    def test_md5_files_reports_missing_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            digest_map = md5_files(["nope.json"], root=tmp)
            self.assertIsNone(digest_map["nope.json"])

    def test_md5_changes_with_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.txt"
            path.write_text("one", encoding="utf-8")
            first = md5_files(["a.txt"], root=tmp)["a.txt"]
            path.write_text("two", encoding="utf-8")
            self.assertNotEqual(first, md5_files(["a.txt"], root=tmp)["a.txt"])

    def test_protected_list_covers_the_identity_and_annotation_files(self):
        for name in ("out/corner-pocket/state.json", "out/pid_seed.json",
                     "out/scan30/annotations.json", "out/identity/clusters.json"):
            self.assertIn(name, PROTECTED)

    def test_scratch_root_has_its_own_stores_and_symlinked_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = scratch_root(tmp, fresh=True)
            self.assertTrue((root / "out" / "corner-pocket").is_dir())
            self.assertTrue((root / "out" / "identity").is_dir())
            self.assertTrue((root / "data").is_symlink())
            self.assertFalse((root / "out" / "corner-pocket" / "face_embeddings.json").exists())

    def test_serve_refuses_the_production_root(self):
        with self.assertRaises(SystemExit):
            serve(Path(__file__).resolve().parents[1], port=8133)


class DatasetConfigTest(unittest.TestCase):
    def test_both_vods_are_configured(self):
        self.assertEqual(set(DATASETS), {"vod30", "highlight"})
        for _video, scan_dir, _width in DATASETS.values():
            self.assertTrue(scan_dir.startswith("scan"))

    def test_digest_is_small_and_json_safe(self):
        report = {"sampled_frames": 240, "tracklets": 3, "person_instances": 0, "faces_detected": 0,
                  "detectability": detectability([]), "separation": separation([]),
                  "role_pairs": {}, "recorded_person_instances": 0}
        text = json.dumps(digest(report))
        self.assertIn("sampled_frames", text)
        self.assertLess(len(text), 4000)


class AnalyseRoundTripTest(unittest.TestCase):
    def test_analyse_reads_a_detections_file_and_writes_a_report(self):
        records = [
            record([0, 0, 300, 500], [face([100, 100, 130, 140])], burst=0, frame_index=0, tracklet="a"),
            record([0, 0, 300, 500], [face([100, 100, 130, 140], embedding=at(unit(1), 0.9, 9).tolist())],
                   burst=0, frame_index=15, tracklet="a"),
            record([0, 0, 120, 200], [], burst=0, frame_index=0, tracklet="b", role="right"),
        ]
        payload = {"datasets": {"vod30": {"frames_sampled": 3, "frame_count": 100, "fps": 30.0,
                                          "corners": VOD30_CORNERS}},
                   "records": records, "tracklets": 2, "runtime_s": 1.0}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "detections.json").write_text(json.dumps(payload), encoding="utf-8")
            report = analyse(directory, log=lambda *a, **k: None)
            self.assertTrue((directory / "analysis.json").is_file())
            self.assertEqual(report["recorded_person_instances"], 3)
            self.assertEqual(report["sampled_frames"], 3)
            self.assertEqual(report["detectability"]["gate_person"]["quality_pass"]["n"], 2)
            self.assertEqual(report["separation"]["within_tracklet"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
