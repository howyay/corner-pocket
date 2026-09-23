"""Frame-audit tests: decode path, duplicate detection, cloth-mask reporting.

The audit tool exists because a zero-ball frame is only evidence of an empty
cloth if the frame really shows the table.  These tests pin the verdicts on
synthetic videos, so "decode artifact" cannot quietly become "real occlusion".
"""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.sam3_frame_audit import (BLACK_MEAN, FLAT_STD, audit, cloth_report,  # noqa: E402
                                  decode, decode_by_index, reference_quad)


def write_video(path, frames):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0,
                             (frames[0].shape[1], frames[0].shape[0]))
    for frame in frames:
        writer.write(frame)
    writer.release()


class DecodePathTests(unittest.TestCase):
    def test_time_seek_and_index_seek_agree(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            frames = [np.full((64, 64, 3), value, np.uint8) for value in (40, 80, 120, 160)]
            # 4 frames at 30 fps: the times must stay inside them or the read fails
            write_video(path, frames)
            info, frame = decode(path, 2 / 30.0)
            self.assertTrue(info["ok"])
            self.assertIsNotNone(frame)
            by_index = decode_by_index(path, 2)
            self.assertEqual(by_index["md5"], info["md5"])

    def test_two_times_landing_on_one_frame_are_reported(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            write_video(path, [np.full((64, 64, 3), 90, np.uint8) for _ in range(6)])
            result = audit(path, [0.1, 0.12], out_dir=Path(tmp) / "dumps")
            self.assertTrue(result["duplicate_hashes"])
            self.assertTrue(all(row["verdict"] == "decode artifact" for row in result["frames"]))
            self.assertTrue(all(row.get("file") for row in result["frames"]))

    def test_a_black_frame_is_a_decode_artifact(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            frames = [np.zeros((64, 64, 3), np.uint8), np.full((64, 64, 3), 200, np.uint8),
                      np.full((64, 64, 3), 120, np.uint8)]
            write_video(path, frames)
            result = audit(path, [0.0, 1 / 30.0], out_dir=Path(tmp) / "dumps")
            first = result["frames"][0]
            self.assertLess(first["mean"], BLACK_MEAN)
            self.assertEqual(first["verdict"], "decode artifact")
            self.assertIn("black frame", " ".join(first["notes"]))

    def test_a_flat_frame_is_a_decode_artifact(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            # 128x128: at 64x64 the codec's ringing lifts a flat frame's std
            # above the threshold and the test would measure the codec.
            noise = np.random.default_rng(0).integers(0, 255, (128, 128, 3), dtype=np.uint8)
            write_video(path, [noise, np.full((128, 128, 3), 128, np.uint8),
                               np.full((128, 128, 3), 128, np.uint8), noise])
            result = audit(path, [1 / 30.0, 2 / 30.0], out_dir=Path(tmp) / "dumps")
            flat = [row for row in result["frames"]
                    if row.get("std") is not None and row["std"] < FLAT_STD]
            self.assertTrue(flat)                       # std 0.0 is falsy: no `or` here
            self.assertTrue(all(row["verdict"] == "decode artifact" for row in flat))

    def test_a_normal_frame_is_not_called_an_artifact(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            rng = np.random.default_rng(1)
            frames = [rng.integers(0, 255, (64, 64, 3), dtype=np.uint8) for _ in range(8)]
            write_video(path, frames)
            result = audit(path, [0.0, 1 / 30.0, 2 / 30.0, 3 / 30.0], out_dir=Path(tmp) / "dumps")
            self.assertEqual(result["verdicts"]["real occlusion"], 4)
            self.assertFalse(result["duplicate_hashes"])


class ReferenceQuadTests(unittest.TestCase):
    def test_hand_anchors_are_preferred_when_the_segment_is_absent(self):
        with TemporaryDirectory() as tmp:
            anchors = Path(tmp) / "anchors.json"
            anchors.write_text(json.dumps({"anchors": {"70.0": [[1, 2], [3, 4], [5, 6], [7, 8]]}}))
            quad, label = reference_quad(dataset="nothing-here", anchors_path=str(anchors))
            self.assertIsNotNone(quad)
            self.assertEqual(label, "hand anchors")
            self.assertEqual(quad.shape, (4, 2))
            self.assertEqual(quad[0].tolist(), [1.0, 2.0])

    def test_no_calibration_returns_none(self):
        quad, label = reference_quad(dataset="nothing-here",
                                     anchors_path="/nonexistent/anchors.json")
        self.assertIsNone(quad)
        self.assertEqual(label, "none")

    def test_the_cloth_report_names_the_mask_geometry(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            rng = np.random.default_rng(2)
            carry = [rng.integers(0, 255, (360, 640, 3), dtype=np.uint8) for _ in range(2)]
            write_video(path, carry)
            quad, _ = reference_quad(dataset="nothing-here", anchors_path="/nonexistent.json")
            row = cloth_report(path, 0.0, quad)
            self.assertIn("cloth_area", row)
            self.assertIn("largest_centroid", row)


if __name__ == "__main__":
    unittest.main()
