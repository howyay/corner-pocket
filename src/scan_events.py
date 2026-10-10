"""Scan a long VOD for SHOTS and POTS and produce an event timeline.

Phase 1 (fast): every `--every` seconds, detect the table + classical ball
candidates at reduced resolution; record ball count, positions (canonical mm)
and table-region motion energy between samples.

Phase 2 (accurate): run SAM3 on single frames bracketing each candidate event
to confirm it and to measure real ball displacement (shots) or the vanished
ball + nearest pocket (pots).  Outputs events.json + annotated evidence JPEGs.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))     # the repo root, for the src.* imports

from ball_detect import detect_ball_candidates
from src.table_geometry import (CANON_H, CANON_W, POCKETS_MM, homography_to_canonical,
                                nearest_pocket)
from table_detect import detect_table
from src.ball_gate import (CLASSICAL_BALL_MAX_AREA_960X540_PX, SAM3_BALL_MAX_AREA_PX,
                           SAM3_BALL_MIN_AREA_PX, SAM3_BALL_MIN_SCORE)

# physical geometry (Rasson Victory III 9ft, 2540 x 1270 mm): the canonical
# frame and the pocket table live in table_geometry.py, their only definition
# site, so this scan writes the same millimetres the gates and the server use.

SHOT_DISP_MM = 300.0    # confirmed shot: fastest ball moves > 300 mm
MOTION_THRESH = 4.5     # table-region frame diff for a shot candidate
MIN_BALL_AREA_720 = 14.0
MAX_BALL_AREA_720 = CLASSICAL_BALL_MAX_AREA_960X540_PX


def motion_energy(gray_now: np.ndarray, gray_prev: np.ndarray, mask) -> float:
    if gray_prev is None:
        return 0.0
    d = np.abs(gray_now.astype(np.int16) - gray_prev.astype(np.int16))
    if mask is not None:
        d = d[mask > 0]
    return float(d.mean())


def classical_scan(video: str, every: float) -> tuple[list, np.ndarray]:
    """Phase 1: coarse scan. Candidate centers and median corners use source pixels."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    records = []
    corners_list = []
    gray_prev = None
    t = 0.0
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, (960, 540))
        scale_x = frame.shape[1] / small.shape[1]
        scale_y = frame.shape[0] / small.shape[0]
        tab = detect_table(small)
        if tab["corners"] is not None:
            corners_list.append(np.array(tab["corners"]) * [scale_x, scale_y])
        cands = detect_ball_candidates(
            small, tab["mask"],
            min_area=MIN_BALL_AREA_720, max_area=MAX_BALL_AREA_720,
        )
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        me = motion_energy(gray, gray_prev, tab["mask"])
        gray_prev = gray
        records.append({
            "t": round(t, 1),
            "n_classical": len(cands),
            "motion": round(me, 2),
            "cloth_area": int(tab["mask"].sum()),
            "cands": [[round(c["cx"] * scale_x, 1), round(c["cy"] * scale_y, 1)] for c in cands],
        })
        t += every
    cap.release()
    med = np.median(np.array(corners_list), axis=0) if corners_list else None
    return records, med


def sam3_confirm(video: str, times: list[float], out_dir: Path):
    """Phase 2: SAM3 on the given timestamps; returns ball lists per time."""
    import torch
    from PIL import Image

    from pipeline import detect_table, ball_center
    from sam3_cpu import load_sam3_image_model, make_processor

    torch.set_num_threads(8)
    model = load_sam3_image_model(str(ROOT.parent / "data" / "sam3.safetensors"))
    model.float()
    proc = make_processor(model)

    fixed = np.array(json.load(open(out_dir / "corners.json"))["corners"], dtype=np.float32)
    H = homography_to_canonical(fixed)

    results_path = out_dir / "sam3_results.json"
    results = {}
    if results_path.exists():
        results = {float(k): v for k, v in json.loads(results_path.read_text()).items()}
    cap = cv2.VideoCapture(video)
    for t in times:
        if round(t, 1) in results:
            continue
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, bgr = cap.read()
        if not ok:
            continue
        tab = detect_table(bgr)
        st = proc.set_image(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
        st = proc.set_text_prompt("billiard ball", st)
        masks = st["masks"].cpu().float().numpy()
        scores = st["scores"].cpu().float().numpy()
        cloth = tab["mask"] > 0
        balls = []
        for i in range(len(scores)):
            if scores[i] < SAM3_BALL_MIN_SCORE:
                continue
            m = np.squeeze(masks[i])
            area = float(m.sum())
            if area < SAM3_BALL_MIN_AREA_PX or area > SAM3_BALL_MAX_AREA_PX:
                continue
            cx, cy, r = ball_center(m)
            if not (0 <= int(cy) < cloth.shape[0] and 0 <= int(cx) < cloth.shape[1]):
                continue
            if not cloth[int(cy), int(cx)]:
                continue
            if r < 4.0 or r > 60.0:
                continue
            p = H @ np.array([cx, cy, 1.0])
            balls.append({
                "score": float(scores[i]),
                "img": [round(cx, 1), round(cy, 1)],
                "r": round(float(r), 1),
                "table_mm": [round(p[0] / p[2], 1), round(p[1] / p[2], 1)],
            })
        balls.sort(key=lambda b: b["table_mm"])
        results[round(t, 1)] = balls
        # annotated evidence frame
        ev = bgr.copy()
        for b in balls:
            cv2.circle(ev, (int(b["img"][0]), int(b["img"][1])), max(5, int(b["r"])),
                       (0, 200, 255), 2)
        cv2.putText(ev, f"t={t:.1f}s  {len(balls)} balls", (30, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)
        cv2.imwrite(str(out_dir / f"evidence_t{int(t):05d}.jpg"), ev)
        results[round(t, 1)] = balls
        results_path.write_text(json.dumps(results))
    cap.release()
    return results


def build_events(records, sam3, motion_thr=MOTION_THRESH, shot_disp=SHOT_DISP_MM):
    events = []
    # shots: motion spikes in the classical scan
    for i, rec in enumerate(records):
        if rec["motion"] >= motion_thr:
            events.append({"t": rec["t"], "type": "shot", "src": "motion"})
    # pots: SAM3-count drops with persistence across adjacent samples
    times = sorted(sam3)
    counts = {t: len(balls) for t, balls in sam3.items()}
    for i, t in enumerate(times):
        if i + 1 >= len(times):
            break
        t2 = times[i + 1]
        if counts[t2] < counts[t]:
            events.append({"t": t2, "type": "pot", "src": "count",
                           "dropped": counts[t] - counts[t2]})
    events.sort(key=lambda e: e["t"])
    # dedupe nearby events of the same type
    deduped = []
    for e in events:
        if deduped and e["t"] - deduped[-1]["t"] < 4.0 and e["type"] == deduped[-1]["type"]:
            continue
        deduped.append(e)
    return deduped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="data/vod_30min_260815.mp4")
    ap.add_argument("--out", default="out/scan30")
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("--corners", default=None, help="precomputed corners JSON (do not re-estimate)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("phase 1: classical scan...", flush=True)
    t0 = time.time()
    records, med_corners = classical_scan(args.video, args.every)
    json.dump(records, open(out_dir / "records.json", "w"))
    print(f"phase 1 done in {time.time()-t0:.0f}s, {len(records)} samples", flush=True)
    if args.corners:
        med_corners = np.array(json.load(open(args.corners))["corners"], dtype=np.float32)
        print("using precomputed corners:", med_corners.astype(int).tolist(), flush=True)
    else:
        print("corners estimated:", None if med_corners is None else med_corners.astype(int).tolist(), flush=True)
        if med_corners is None:
            print("NO TABLE FOUND", flush=True)
            return
    json.dump({"corners": med_corners.tolist()}, open(out_dir / "corners.json", "w"))

    # cluster motion candidates: peaks above (mean + 4*std), merged within 6 s
    motions = np.array([r["motion"] for r in records])
    thr = float(motions.mean() + 4.0 * motions.std())
    peaks = [r["t"] for r in records if r["motion"] >= max(MOTION_THRESH, thr)]
    clusters = []
    for t in peaks:
        if clusters and t - clusters[-1][-1] <= 6.0:
            clusters[-1].append(t)
        else:
            clusters.append([t])
    conf_times = set()
    for cl in clusters:
        c = float(np.median(cl))
        conf_times.add(round(c, 1))
        conf_times.add(round(c + 2.0, 1))  # displacement evidence
    # pot counts: sample every 60 s (persistent drops are caught at this rate)
    for t in range(30, int(records[-1]["t"]), 60):
        conf_times.add(float(t))
    conf_times = sorted(t for t in conf_times if t >= 0)
    print(f"motion thr={thr:.2f}, {len(clusters)} shot clusters, "
          f"{len(conf_times)} confirmation timestamps", flush=True)

    print(f"phase 2: SAM3 confirmation of {len(conf_times)} timestamps (2 workers)...", flush=True)
    t0 = time.time()
    # threads instead of mp (sandbox lacks /dev/shm for SemLock)
    from concurrent.futures import ThreadPoolExecutor
    chunks = [list(c) for c in np.array_split(conf_times, 2) if len(c)]
    with ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(lambda c: sam3_confirm(args.video, c, out_dir), chunks))
    sam3 = {}
    for r in results:
        sam3.update(r)
    print(f"phase 2 done in {time.time()-t0:.0f}s", flush=True)

    # refine shot events: displacement of the fastest ball between bracketing SAM3 frames
    times = sorted(sam3)
    events = []
    for i in range(len(times) - 1):
        t1, t2 = times[i], times[i + 1]
        if t2 - t1 > 3.5:
            continue
        b1, b2 = sam3[t1], sam3[t2]
        if not b1 or not b2:
            continue
        best = None
        for a in b1:
            for c in b2:
                d = np.hypot(a["table_mm"][0] - c["table_mm"][0],
                             a["table_mm"][1] - c["table_mm"][1])
                if best is None or d > best[0]:
                    best = (d, a, c)
        if best and best[0] >= SHOT_DISP_MM:
            events.append({
                "t": round((t1 + t2) / 2, 1),
                "type": "shot",
                "disp_mm": round(best[0]),
                "speed_m_s": round(best[0] / max(0.01, t2 - t1) / 1000.0, 1),
                "ball_from": best[1]["table_mm"],
                "ball_to": best[2]["table_mm"],
            })
    # pot events: count drops between adjacent SAM3-confirmed samples, with
    # OCCLUSION AWARENESS: a sample is untrustworthy when a person blocks the
    # table (cloth area collapses).  Drops touching an occluded sample are not
    # pots; the running minimum is only updated from trustworthy samples, so a
    # ball hidden for one or more samples does not register as potted.
    counts = {t: len(b) for t, b in sam3.items()}
    rec_by_t = {r["t"]: r for r in records}
    area_ref = float(np.median([r["cloth_area"] for r in records]))

    def occluded(t):
        r = rec_by_t.get(round(t, 1)) or rec_by_t.get(round(t))
        if r is None:
            return False
        return r["cloth_area"] < 0.7 * area_ref

    prev_min = 1e18
    for i in range(len(times) - 1):
        t1, t2 = times[i], times[i + 1]
        if occluded(t1) or occluded(t2):
            continue  # count unknown while a person blocks the view
        # recovery guard: a REAL pot never comes back.  If any of the next 3
        # samples rises above the dropped level, treat as occlusion noise.
        c2 = counts[t2]
        recovers = any(counts[tt] > c2 for tt in times[i + 2:i + 5])
        if c2 < prev_min and not recovers:
            prev_min = counts[t2]
            # greedy nearest-neighbour matching, k = drop size
            k = counts[t1] - counts[t2]
            unmatched = list(sam3[t2])
            dists = []
            for b in sam3[t1]:
                if not unmatched:
                    dists.append((1e9, b)); continue
                ds = [np.hypot(b["table_mm"][0] - c["table_mm"][0],
                               b["table_mm"][1] - c["table_mm"][1]) for c in unmatched]
                j = int(np.argmin(ds))
                dists.append((ds[j], b))
                unmatched.pop(j)
            dists.sort(key=lambda z: -z[0])
            for _, b in dists[:k]:
                pocket, dist = nearest_pocket(*b["table_mm"])
                events.append({
                    "t": round((t1 + t2) / 2, 1),
                    "type": "pot",
                    "window_s": [round(t1, 1), round(t2, 1)],
                    "ball_table_mm": b["table_mm"],
                    "nearest_pocket": pocket,
                    "pocket_dist_mm": round(dist),
                })
        else:
            prev_min = min(prev_min, counts[t2])
    events.sort(key=lambda e: e["t"])
    for i, e in enumerate(events):
        e["id"] = i + 1
        e["evidence"] = f"evidence_t{int(round(e['t'])):05d}.jpg"
    json.dump(events, open(out_dir / "events.json", "w"), indent=1)
    print(f"{len(events)} events -> {out_dir / 'events.json'}", flush=True)
    for e in events:
        print(e, flush=True)


if __name__ == "__main__":
    main()
