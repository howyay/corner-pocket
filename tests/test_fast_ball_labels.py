"""fast_ball_labels contract: the device move, the instance reading, the agreement.

Everything here is synthetic.  The SAM3 model is 3.4 GB and the hybrid path needs the
ROCm GPU, so what is pinned is the part that decides whether a labelling run is
trustworthy: how a nested backbone output crosses devices, how instances are read out of
a processor state, how two modes are compared, and which peaks the persistence filter
throws away.  The measured CPU-vs-hybrid agreement lives in
``out/fast_ball_labels/agreement.json``, not in a unit test.
"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from src.fast_ball_labels import (MODES, agreement, existing_times, instances_from_state,
                                  match_rows, persistence_filter, to_device)


class FakeNested:
    """The one shape in the backbone output that has no ``.to()``."""

    def __init__(self, tensors, mask=None):
        self.tensors = tensors
        self.mask = mask


class ToDeviceTest(unittest.TestCase):
    def test_a_nested_structure_moves_whole(self):
        payload = {"a": [torch.zeros(2)], "b": FakeNested(torch.ones(3), torch.ones(3)),
                   "c": (torch.zeros(1),)}
        moved = to_device(payload, "cpu")
        self.assertEqual(moved["a"][0].device.type, "cpu")
        self.assertEqual(moved["b"].tensors.device.type, "cpu")
        self.assertEqual(moved["c"][0].device.type, "cpu")

    def test_a_nested_tensor_with_no_mask_keeps_none(self):
        moved = to_device(FakeNested(torch.ones(2)), "cpu")
        self.assertIsNone(moved.mask)

    def test_a_plain_value_passes_through(self):
        self.assertEqual(to_device({"h": 720, "w": 1280}, "cpu"), {"h": 720, "w": 1280})


class InstancesTest(unittest.TestCase):
    @staticmethod
    def state(scores, masks):
        return {"scores": torch.tensor(scores, dtype=torch.float32),
                "masks": torch.tensor(masks, dtype=torch.bool)}

    def test_the_score_cut_is_applied(self):
        masks = np.zeros((2, 1, 20, 20), bool)
        masks[0, 0, 8:12, 8:12] = True
        masks[1, 0, 2:6, 2:6] = True
        rows = instances_from_state(self.state([0.9, 0.4], masks), min_score=0.62)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["score"], 0.9, places=6)

    def test_the_centre_and_radius_come_from_the_mask(self):
        masks = np.zeros((1, 1, 40, 40), bool)
        masks[0, 0, 18:23, 18:23] = True          # a 5x5 disc at (20, 20)
        rows = instances_from_state(self.state([0.8], masks))
        self.assertAlmostEqual(rows[0]["x"], 20.0, delta=0.6)
        self.assertAlmostEqual(rows[0]["y"], 20.0, delta=0.6)
        self.assertGreater(rows[0]["r"], 2.0)

    def test_an_empty_state_gives_no_instances(self):
        masks = np.zeros((0, 1, 20, 20), bool)
        self.assertEqual(instances_from_state(self.state([], masks)), [])


class MatchRowsTest(unittest.TestCase):
    def test_a_shifted_detection_still_matches_inside_the_gate(self):
        reference = [{"x": 100.0, "y": 100.0, "r": 9.0, "score": 0.9}]
        candidate = [{"x": 103.0, "y": 100.0, "r": 9.0, "score": 0.8}]
        result = match_rows(reference, candidate, tol_px=6.0)
        self.assertEqual(result["matched"], 1)
        self.assertTrue(result["counts_agree"])

    def test_matching_is_one_to_one(self):
        reference = [{"x": 100.0, "y": 100.0, "r": 9.0, "score": 0.9}]
        candidate = [{"x": 100.0, "y": 100.0, "r": 9.0, "score": 0.8},
                     {"x": 101.0, "y": 100.0, "r": 9.0, "score": 0.7}]
        result = match_rows(reference, candidate, tol_px=6.0)
        self.assertEqual(result["matched"], 1)
        self.assertFalse(result["counts_agree"])


class AgreementTest(unittest.TestCase):
    def frame(self, n_cpu, n_other, offset=0.0):
        cpu = [{"x": 100.0 + 40 * i, "y": 100.0, "r": 9.0, "score": 0.9} for i in range(n_cpu)]
        other = [{"x": 100.0 + 40 * i + offset, "y": 100.0, "r": 9.0, "score": 0.9}
                 for i in range(n_other)]
        return {"cpu": cpu, "other": other}

    def test_equal_counts_are_reported_per_frame(self):
        report = agreement({"4.1": self.frame(10, 10), "4.6": self.frame(9, 9)})
        self.assertEqual(report["frames"], 2)
        self.assertEqual(report["frames_with_equal_counts"], 2)
        self.assertEqual(report["frames_fully_matched"], 2)

    def test_a_missing_instance_is_not_counted_as_agreeing(self):
        report = agreement({"4.1": self.frame(10, 9)})
        self.assertEqual(report["frames_with_equal_counts"], 0)
        self.assertEqual(report["frames_fully_matched"], 0)
        self.assertEqual(report["per_frame"][0]["count_cpu"], 10)
        self.assertEqual(report["per_frame"][0]["count_other"], 9)

    def test_the_same_count_in_the_wrong_place_is_not_agreement(self):
        report = agreement({"4.1": self.frame(2, 2, offset=50.0)})
        self.assertEqual(report["frames_with_equal_counts"], 1)
        self.assertEqual(report["frames_fully_matched"], 0)


class PersistenceFilterTest(unittest.TestCase):
    def series(self):
        return {0: [(100.0, 100.0, 0.9), (500.0, 500.0, 0.8)],
                1: [(101.0, 100.0, 0.9)],
                2: [(102.0, 101.0, 0.9)],
                3: [(103.0, 101.0, 0.9)],
                4: [(104.0, 102.0, 0.9)]}

    def test_a_peak_that_reappears_next_frame_survives(self):
        result = persistence_filter(self.series(), radius_px=12.0, min_support=0.6)
        positions = [(row["x"], row["y"]) for row in result["kept"][0]]
        self.assertIn((100.0, 100.0), positions)

    def test_a_single_frame_peak_is_sent_to_review(self):
        result = persistence_filter(self.series(), radius_px=12.0, min_support=0.6)
        dropped = [(row["x"], row["y"]) for row in result["dropped"][0]]
        self.assertIn((500.0, 500.0), dropped)

    def test_support_is_recorded_so_the_queue_can_be_sorted(self):
        result = persistence_filter(self.series(), radius_px=12.0, min_support=0.6)
        row = next(r for r in result["kept"][0] if r["x"] == 100.0)
        self.assertAlmostEqual(row["support"], 1.0, places=6)

    def test_the_last_frame_still_gets_a_verdict(self):
        result = persistence_filter(self.series())
        self.assertIn(4, result["kept"])


class ExistingTimesTest(unittest.TestCase):
    def test_times_from_both_caches_are_read_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out" / "scan30").mkdir(parents=True)
            (root / "out" / "scan30" / "sam3_census.json").write_text(
                json.dumps({"frames": {"4.1": [], "4.6": []}}))
            (root / "out" / "scan30" / "sam3_results.json").write_text(
                json.dumps({"4.6": [], "5.1": []}))
            self.assertEqual(existing_times(root), {4.1, 4.6, 5.1})

    def test_a_missing_cache_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(existing_times(Path(tmp)), set())


class ModeListTest(unittest.TestCase):
    def test_both_documented_modes_exist(self):
        self.assertIn("cpu", MODES)
        self.assertIn("hybrid", MODES)


if __name__ == "__main__":
    unittest.main()
