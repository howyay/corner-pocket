"""Body re-ID threshold calibration on real footage for src/person_identity.py.

Why this file exists: docs/live-processing-verification.md finding B — on
frames 8000-12000 of data/vod_30min_260815.mp4 the 0.35 body MATCH threshold
(borrowed from the FACE-embedding calibration) merged 41 tracker tracks into
1 cluster, because cross-person SAME-FRAME OSNet cosines measure 0.79-0.87.

Pseudo-ground-truth (no human labels, production read-only, temp state only):
- cross-person pair: two YOLO person boxes detected in the SAME frame are
  different people (never the same person);
- same-person pair: the same detection box tracked across a SHORT gap
  (<= 1 s, ~30 frames) with IoU >= 0.6 continuity between consecutive
  sampled frames.

Decision rule (midpoint logic): if same-person p05 sits clearly above
cross-person p95, MATCH = midpoint of [cross_p95, same_p05] and MARGIN from
the observed gap; if the distributions overlap, body-only clustering cannot
separate these players at 1280x720 and the honest verdict is
"body matching unreliable here -> face-binding-only mode".

Fast tests (default `python -m unittest`) validate the decision logic and
that the constants in src/person_identity.py match RECORDED below.
Heavy real-model passes (YOLOv8n + vendored OSNet x0.25 on the real video,
temp state only) run only with POOL_BODY_CALIBRATION=1:

  POOL_BODY_CALIBRATION=1 .venv/bin/python tests/test_body_calibration.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.person_identity import BODY_MATCH_DISABLED, IdentityIndex  # noqa: E402
from src.person_pipeline import PersonPipeline, _iou  # noqa: E402

VIDEO = REPO / "data" / "vod_30min_260815.mp4"
FPS = 30.0003
F0 = int(os.environ.get("POOL_BODY_F0", 8000))
F1 = int(os.environ.get("POOL_BODY_F1", 12000))
STEP = int(os.environ.get("POOL_BODY_STEP", 10))  # sampled frames (decode all, embed every STEP)
IOU_LINK = 0.6          # same-person continuity requirement between consecutive samples
MAX_GAP_S = 1.0
MAX_GAP_FRAMES = int(round(MAX_GAP_S * FPS))  # ~30
MIN_GAP = 0.02          # min separation between cross p95 and same p05 to trust a threshold
RUN_REAL = os.environ.get("POOL_BODY_CALIBRATION") == "1"

# Filled from the measured run (kept in-repo so the fast suite pins the
# applied constants to the actual measurement; see test_constants_match_recorded).
# Measured 2026-09-15: frames 8000-12000 step 10 of data/vod_30min_260815.mp4,
# 401 sampled frames / 1183 OSNet embeddings, IoU>=0.6 short-gap pseudo-GT.
RECORDED = {
    "same_person": {"n": 8192, "p05": 0.7549, "median": 0.8300, "p95": 0.9972, "max": 0.9998},
    "cross_person": {"n": 1330, "p05": 0.7473, "median": 0.8107, "p95": 0.8824, "max": 0.983},
    "verdict": "unreliable",
    "threshold": None,
    "margin": None,
}


# ---------------------------------------------------------------- machinery
class StubFaceEngine:
    """No-op face engine for cluster-only spot checks (clustering never reads faces)."""

    def analyze(self, frame):
        return []


def make_pipeline(tmp: Path):
    """Real PersonPipeline in a temp root (production out/ untouched)."""
    shutil.copy2(REPO / "yolov8n.pt", tmp / "yolov8n.pt")
    return PersonPipeline(tmp)


def crop(frame: np.ndarray, bbox) -> np.ndarray:
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in bbox]
    return frame[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]


def collect_samples(video: Path, f0: int, f1: int, step: int, detector, encoder, log=print):
    """Decode [f0, f1]; every `step` frames embed all person crops.

    Returns list of (frame_no, [(embedding, bbox), ...]).
    """
    cap = cv2.VideoCapture(str(video))
    assert cap.isOpened(), f"cannot open {video}"
    cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
    samples: list[tuple[int, list]] = []
    idx = f0
    while idx <= f1:
        ok, frame = cap.read()
        if not ok:
            log(f"  decode ended early at frame {idx}")
            break
        if (idx - f0) % step == 0:
            dets = detector(frame)
            boxes = [d["bbox"] for d in dets]
            embs = encoder([crop(frame, b) for b in boxes]) if boxes else []
            samples.append((idx, list(zip(embs, boxes))))
        idx += 1
    cap.release()
    return samples


def pseudo_gt_pairs(samples, iou_link: float = IOU_LINK,
                    max_gap_frames: int = MAX_GAP_FRAMES):
    """Split embedding pairs into reliable same-person / cross-person groups.

    cross-person: any two embeddings detected in the same sampled frame.
    same-person: embeddings chained by IoU >= iou_link between consecutive
    sampled frames, compared across gaps <= max_gap_frames (~1 s).
    Returns (same, cross): lists of (cosine, gap_frames_or_None).
    """
    same: list[tuple[float, int]] = []
    cross: list[tuple[float, None]] = []
    # incremental tracklets: live = [(last_frame, last_bbox, tracklet_index)]
    tracklets: list[list[tuple[int, np.ndarray]]] = []
    live: list[tuple[int, list, int]] = []
    for fr, items in samples:
        new_live = []
        for emb, bbox in items:
            best_iou, best_t = 0.0, None
            for lf, lb, ti in live:
                i = _iou(lb, bbox)
                if i >= iou_link and i > best_iou:
                    best_iou, best_t = i, ti
            if best_t is None:
                tracklets.append([(fr, emb)])
                ti = len(tracklets) - 1
            else:
                tracklets[ti].append((fr, emb))
            new_live.append((fr, bbox, ti))
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                ea, eb = items[a][0], items[b][0]
                cross.append((float(np.dot(ea, eb)), None))
        live = new_live
    for chain in tracklets:
        n = len(chain)
        for a in range(n):
            for b in range(a + 1, n):
                gap = chain[b][0] - chain[a][0]
                if gap <= max_gap_frames:
                    same.append((float(np.dot(chain[a][1], chain[b][1])), gap))
    return same, cross


def stats(xs) -> dict:
    empty = {"n": 0, "min": None, "p05": None, "median": None, "p95": None, "max": None}
    if not xs:
        return empty
    a = np.asarray([c for c, _ in xs], float)
    return {
        "n": int(a.size),
        "min": round(float(a.min()), 4),
        "p05": round(float(np.percentile(a, 5)), 4),
        "median": round(float(np.median(a)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
        "max": round(float(a.max()), 4),
    }


def decide(same, cross, min_gap: float = MIN_GAP) -> dict:
    """Midpoint rule between cross-person p95 and same-person p05.

    Reliable only when the two distributions do not overlap; otherwise body
    matching is judged unreliable on this footage (face-binding-only mode).
    """
    lo, hi = stats(cross)["p95"], stats(same)["p05"]
    out = {"cross_p95": lo, "same_p05": hi, "gap": None}
    if lo is None or hi is None:
        out.update(
            verdict="unreliable",
            threshold=None,
            margin=None,
            rationale="no measurable pairs on this segment",
        )
        return out
    gap = round(hi - lo, 4)
    out["gap"] = gap
    if gap <= min_gap:
        out.update(
            verdict="unreliable",
            threshold=None,
            margin=None,
            rationale=(
                "same-person p05 does not separate from cross-person p95 "
                f"(gap {gap}): body-only clustering cannot separate these "
                "players at this resolution; face-binding-only mode"
            ),
        )
        return out
    threshold = round((lo + hi) / 2, 3)
    margin = round(min(0.10, max(0.02, 0.25 * gap)), 3)
    cl = np.asarray([c for c, _ in cross], float)
    sl = np.asarray([c for c, _ in same], float)
    out.update(
        verdict="reliable",
        threshold=threshold,
        margin=margin,
        cross_merge_rate_at_threshold=round(float((cl >= threshold).mean()), 4),
        same_miss_rate_at_threshold=round(float((sl < threshold).mean()), 4),
        rationale=(
            f"threshold midpoints the {gap} gap between cross-person p95 ({lo}) "
            f"and same-person p05 ({hi}); margin keeps ~1/4 of the gap"
        ),
    )
    return out


def gap_buckets(same) -> dict:
    out = {}
    for lo, hi in ((0, 10), (10, 20), (20, 30)):
        sel = [c for c, g in same if g is not None and lo < g <= hi]
        out[f"gap_{lo}_{hi}_frames"] = stats([(c, None) for c in sel])
    return out


def spot_check(f0: int = 8000, f1: int = 8300, step: int = 2, log=print) -> dict:
    """A/B cluster counts on a short real run: borrowed 0.35 vs current defaults.

    Real YOLO + OSNet via PersonPipeline; face engine stubbed (cluster counts
    never depend on faces). All state under a temp root.
    """
    tmp = Path(tempfile.mkdtemp(prefix="body-spotcheck-"))
    try:
        p = make_pipeline(tmp)
        log("[spot] warming detector + OSNet...")
        det = p._get_detector()
        enc = p._get_encoder()
        det(np.zeros((720, 1280, 3), np.uint8))
        enc([np.zeros((64, 32, 3), np.uint8)])
        p._face_engine = StubFaceEngine()

        variants = {
            "old_0.35_borrowed_from_face": IdentityIndex(
                path=tmp / "old.json", match_threshold=0.35, margin=0.12,
                body_match_threshold=0.35, body_margin=0.12),
            "current_defaults": IdentityIndex(path=tmp / "new.json"),
        }
        out = {}
        for name, identity in variants.items():
            p.detector, p.body_encoder, p.identity = det, enc, identity
            p._tracks, p._next_id = {}, 1
            cap = cv2.VideoCapture(str(VIDEO))
            cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
            idx, clusters, tracks, no_id = f0, set(), set(), True
            while idx <= f1:
                ok, frame = cap.read()
                assert ok, f"decode failed at {idx}"
                if (idx - f0) % step == 0:
                    res = p.process_frame(frame, idx, idx / FPS)
                    for per in res["persons"]:
                        clusters.add(per["cluster_id"])
                        tracks.add(per["track_id"])
                        if per["player_id"] is not None:
                            no_id = False
                idx += 1
            cap.release()
            out[name] = {"clusters": len(clusters), "tracks": len(tracks),
                         "cluster_ids": sorted(clusters), "no_player_id_without_enrollment": no_id}
            log(f"[spot] {name}: tracks={len(tracks)} clusters={len(clusters)}")
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------ fast unit tests
class DecideLogicTest(unittest.TestCase):
    def test_clear_gap_picks_midpoint(self):
        cross = [(0.80 - 0.01 * i, None) for i in range(100)]
        same = [(0.90 + 0.001 * i, 10) for i in range(100)]
        d = decide(same, cross)
        self.assertEqual(d["verdict"], "reliable")
        self.assertGreater(d["threshold"], 0.80)
        self.assertLess(d["threshold"], 0.90)
        self.assertGreaterEqual(d["margin"], 0.02)
        self.assertLessEqual(d["margin"], 0.10)

    def test_overlap_is_reported_unreliable(self):
        # cross spans 0.70..0.799 (p95 ~0.794), same spans 0.75..0.849
        # (p05 ~0.755): the ranges interleave -> no trustworthy threshold
        cross = [(0.70 + 0.001 * i, None) for i in range(100)]
        same = [(0.75 + 0.001 * i, 10) for i in range(100)]
        d = decide(same, cross)
        self.assertEqual(d["verdict"], "unreliable")
        self.assertIsNone(d["threshold"])

    def test_empty_input_is_unreliable(self):
        self.assertEqual(decide([], [])["verdict"], "unreliable")


class ConstantsContractTest(unittest.TestCase):
    @unittest.skipUnless(RECORDED, "RECORDED calibration not filled in yet")
    def test_constants_match_recorded_calibration(self):
        from src.person_identity import BODY_MARGIN, BODY_MATCH_THRESHOLD
        rec = RECORDED
        if rec["verdict"] == "unreliable":
            self.assertEqual(BODY_MATCH_THRESHOLD, BODY_MATCH_DISABLED)
            self.assertEqual(BODY_MARGIN, 0.0)
        else:
            self.assertGreater(BODY_MATCH_THRESHOLD, rec["cross_p95"])
            self.assertLess(BODY_MATCH_THRESHOLD, rec["same_p05"])
            self.assertGreaterEqual(BODY_MARGIN, 0.02)
            self.assertLessEqual(BODY_MARGIN, 0.10)

    def test_face_calibration_untouched(self):
        """The 0.35/0.12 pair is the FACE calibration and must stay the face bar."""
        with tempfile.TemporaryDirectory() as t:
            idx = IdentityIndex(path=Path(t) / "c.json")
            self.assertEqual(idx.match_threshold, 0.35)
            self.assertEqual(idx.margin, 0.12)


class DefaultBodyModeTest(unittest.TestCase):
    """Pin the default clustering behaviour implied by RECORDED (mechanism covered
    by the explicit-constant cases in test_person_identity.py)."""

    def _idx(self, tmp):
        return IdentityIndex(path=Path(tmp) / "c.json")

    @unittest.skipUnless(RECORDED, "RECORDED calibration not filled in yet")
    def test_default_merge_behaviour(self):
        v = np.zeros(8, np.float32)
        v[0] = 1.0
        with tempfile.TemporaryDirectory() as t:
            idx = self._idx(t)
            c1 = idx.register(1, v)[1]
            c2 = idx.register(2, v)[2]
            if RECORDED["verdict"] == "unreliable":
                self.assertNotEqual(c1, c2,
                                    "body matching disabled by default must not merge")
            else:
                self.assertEqual(c1, c2)

    def test_disabled_sentinel_exists(self):
        from src.person_identity import BODY_MATCH_DISABLED
        self.assertEqual(BODY_MATCH_DISABLED, float("inf"))


# ----------------------------------------------------------- real-footage run
@unittest.skipUnless(RUN_REAL, "real-footage calibration: set POOL_BODY_CALIBRATION=1")
class RealFootageCalibrationTest(unittest.TestCase):
    def test_measure_distributions_and_decision(self):
        with tempfile.TemporaryDirectory() as t:
            p = make_pipeline(Path(t))
            print("[calib] warming detector + OSNet...", flush=True)
            det = p._get_detector()
            enc = p._get_encoder()
            det(np.zeros((720, 1280, 3), np.uint8))
            enc([np.zeros((64, 32, 3), np.uint8)])
            print(f"[calib] frames {F0}-{F1} step {STEP}...", flush=True)
            samples = collect_samples(VIDEO, F0, F1, STEP, det, enc)
            n_emb = sum(len(items) for _, items in samples)
            print(f"[calib] {len(samples)} sampled frames, {n_emb} person embeddings", flush=True)
            same, cross = pseudo_gt_pairs(samples)
            s, c = stats(same), stats(cross)
            d = decide(same, cross)
            report = {
                "video": str(VIDEO.relative_to(REPO)), "frames": [F0, F1], "step": STEP,
                "iou_link": IOU_LINK, "max_gap_frames": MAX_GAP_FRAMES,
                "n_samples": len(samples), "n_embeddings": n_emb,
                "same_person": s, "same_person_by_gap": gap_buckets(same),
                "cross_person": c, "decision": d,
            }
            out = Path(t) / "body_calibration_report.json"
            out.write_text(json.dumps(report, indent=1))
            print(json.dumps(report, indent=1), flush=True)
            print(f"[calib] report: {out}", flush=True)
            # the original bug, pinned: cross-person cosines sit far above the
            # borrowed 0.35, so that threshold merges different people.
            self.assertGreater(c["p05"], 0.35, "cross-person p05 must exceed the old 0.35 bar")
            self.assertGreater(s["n"], 100, "not enough same-person pairs for a verdict")
            self.assertGreater(c["n"], 100, "not enough cross-person pairs for a verdict")

    def test_spot_check_cluster_count_is_sane(self):
        sc = spot_check(log=lambda m: print(m, flush=True))
        old, new = sc["old_0.35_borrowed_from_face"], sc["current_defaults"]
        self.assertTrue(old["no_player_id_without_enrollment"])
        self.assertTrue(new["no_player_id_without_enrollment"])
        self.assertLess(old["clusters"], old["tracks"], "0.35 should over-merge on this footage")
        self.assertGreaterEqual(new["clusters"], 2, "must not be the 1 mega-cluster")
        self.assertLessEqual(new["clusters"], new["tracks"])
        print(f"[spot] old clusters={old['clusters']} vs new clusters={new['clusters']} "
              f"(tracks={new['tracks']})", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
