"""PID-2 note: HOG path NOT viable here (this cv2 5.0 build has no HOGDescriptor/Cascade; kept as record).

Baseline detector = OpenCV HOG people detector (cheap); SAM3 person frames
(out/pid1_persons*/*report*.json) act as sparse high-quality anchors for
evaluation. Outputs per-window tracklets (greedy IoU/centroid association) and
a comparison vs SAM3 anchors when a scan time falls inside a window.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

VIDEO = "/home/operator/projects/pool/data/vod_30min_260815.mp4"
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


def hog_persons(bgr):
    boxes, _ = hog.detectMultiScale(bgr, winStride=(8, 8), padding=(8, 8), scale=1.06)
    out = []
    for (x, y, w, h) in boxes:
        out.append([int(x), int(y), int(x + w), int(y + h)])
    return out


def iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


def track_window(t0, dur_s=30.0, step_s=1.0):
    cap = cv2.VideoCapture(VIDEO)
    fps = cap.get(cv2.CAP_PROP_FPS)
    tracks = {}          # tid -> {last_box, born, seen}
    frame_rows = []
    t = t0
    tid_seq = 0
    while t < t0 + dur_s:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, bgr = cap.read()
        if not ok:
            break
        dets = hog_persons(bgr)
        # greedy associate dets to existing tracks (center distance)
        used = set()
        rows = []
        for tid, tr in sorted(tracks.items()):
            lb = tr["last_box"]
            lbc = np.array([(lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2])
            best, bd = None, 1e9
            for di, d in enumerate(dets):
                if di in used:
                    continue
                dc = np.array([(d[0] + d[2]) / 2, (d[1] + d[3]) / 2])
                dist = float(np.linalg.norm(dc - lbc))
                ov = iou(lb, d)
                if dist < 120 and (ov > 0.1 or dist < 60):
                    if dist < bd:
                        bd, best = dist, di
            if best is not None:
                used.add(best)
                tr["last_box"] = dets[best]
                tr["seen"] = t
                rows.append([tid, t, dets[best]])
        for di, d in enumerate(dets):
            if di in used:
                continue
            tid_seq += 1
            tracks[tid_seq] = {"last_box": d, "born": t, "seen": t}
            rows.append([tid_seq, t, d])
        # prune tracks stale > 6 s (keep them closed in output)
        frame_rows.append({"t": round(t, 1), "dets": rows})
        t += step_s
    cap.release()
    # collapse rows into per-track segments
    segs = {}
    for fr in frame_rows:
        for tid, t, box in fr["dets"]:
            segs.setdefault(tid, []).append([t, box])
    tracklets = [{"track_id": k, "samples": v, "duration_s": round(v[-1][0] - v[0][0], 1)}
                 for k, v in segs.items() if len(v) >= 2]
    tracklets.sort(key=lambda x: -x["duration_s"])
    return tracklets


def compare_sam3(tracklets_by_win, scan_time, sam3_boxes):
    """Fraction of SAM3 person boxes that a HOG tracklet overlaps at scan_time."""
    if scan_time is None:
        return None
    best = None
    for win, tls in tracklets_by_win.items():
        if win[0] <= scan_time <= win[1]:
            best = tls
            break
    if best is None:
        return None
    matched = 0
    for sb in sam3_boxes:
        x0, y0, x1, y1 = sb
        ok = False
        for tl in best:
            for t, box in tl["samples"]:
                if abs(t - scan_time) < 1.2 and iou(box, sb) > 0.1:
                    ok = True
                    break
            if ok:
                break
        matched += int(ok)
    return matched, len(sam3_boxes)


if __name__ == "__main__":
    windows = [(30, 60), (265, 300)]
    sam3 = {}
    for p in ["/home/operator/projects/pool/out/pid1_persons/report.json",
              "/home/operator/projects/pool/out/pid1_persons2/report2.json"]:
        if Path(p).exists():
            for r in json.load(open(p)):
                if r["prompt"] == "person":
                    sam3[r["t"]] = [h["bbox"] for h in r["hits"]]
    results = {}
    for (a, b) in windows:
        tls = track_window(a, dur_s=b - a)
        results[f"{a}-{b}"] = {"n_tracklets": len(tls),
                               "tracklets": [{"id": x["track_id"], "dur": x["duration_s"],
                                              "n": len(x["samples"])} for x in tls[:6]]}
        print(f"window {a}-{b}: {len(tls)} tracklets")
        for x in tls[:6]:
            print("   tid", x["track_id"], "dur", x["duration_s"], "samples", len(x["samples"]))
    # compare at SAM3 anchor times inside windows
    print("SAM3 anchor comparison (matched/total):")
    for t, boxes in sorted(sam3.items()):
        for (a, b) in windows:
            if a <= t <= b:
                m = compare_sam3(results, t, boxes)
                if m:
                    print(f"  t={t}: HOG matched {m[0]}/{m[1]} SAM3 persons")
    Path("/home/operator/projects/pool/out/pid2_tracklets.json").write_text(json.dumps(results, indent=1))
    print("wrote out/pid2_tracklets.json")
