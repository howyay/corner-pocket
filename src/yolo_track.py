"""PID-2 v0: person tracklets via YOLOv8n detections at 1 fps over shot windows.

Association: greedy nearest-center (<=90 px) with IoU backup; tracks that
disappear >6 s are closed (occlusion => gap). Windows chosen around shots with
SAM3 person anchors inside for agreement checks.
"""
import json
import os
import sys
import time

import cv2

os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/yolo-cfg")
os.environ.setdefault("ULTRALYTICS_SAFE_LOAD", "1")  # weights-only YOLO load (audit D-2)
from ultralytics import YOLO

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO = os.path.join(REPO, "data", "vod_30min_260815.mp4")
MODEL = YOLO("yolov8n.pt")

SAM3 = {}
for p in [os.path.join(REPO, "out", "pid1_persons", "report.json"),
          os.path.join(REPO, "out", "pid1_persons2", "report2.json")]:
    if not os.path.exists(p):
        continue
    for r in json.load(open(p)):
        hits = r.get("hits", r.get("persons", []))
        if r.get("prompt", "person") != "person":
            continue
        SAM3.setdefault(round(r["t"], 1), []).extend(h["bbox"] for h in hits)


def iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def track_window(t0, t1):
    cap = cv2.VideoCapture(VIDEO)
    tracks = {}
    rows = []
    tid_seq = 0
    t = t0
    while t <= t1:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, bgr = cap.read()
        if not ok:
            break
        res = MODEL.predict(bgr, conf=0.35, classes=[0], verbose=False)
        dets = []
        if res[0].boxes is not None:
            dets = [[int(v) for v in b] for b in res[0].boxes.xyxy.cpu().numpy()]
        used = set()
        row = []
        for tid, tr in sorted(tracks.items()):
            lb = tr["box"]
            lbc = [(lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2]
            best, bd = None, 1e9
            for di, d in enumerate(dets):
                if di in used:
                    continue
                dc = [(d[0] + d[2]) / 2, (d[1] + d[3]) / 2]
                dist = ((dc[0] - lbc[0]) ** 2 + (dc[1] - lbc[1]) ** 2) ** 0.5
                if dist < 90 or iou(lb, d) > 0.15:
                    if dist < bd:
                        bd, best = dist, di
            if best is not None:
                used.add(best)
                tr["box"] = dets[best]
                tr["seen"] = t
                row.append([tid, t, dets[best]])
        for di, d in enumerate(dets):
            if di in used:
                continue
            tid_seq += 1
            tracks[tid_seq] = {"box": d, "born": t, "seen": t}
            row.append([tid_seq, t, d])
        for tid in [k for k, v in tracks.items() if t - v["seen"] > 6]:
            del tracks[tid]
        rows.append(row)
        t += 1.0
    cap.release()
    segs = {}
    for row in rows:
        for tid, t, box in row:
            segs.setdefault(tid, []).append([round(t, 1), box])
    tls = [{"track_id": k, "duration_s": round(v[-1][0] - v[0][0], 1), "n": len(v),
            "samples": v} for k, v in segs.items() if len(v) >= 2]
    return sorted(tls, key=lambda x: -x["duration_s"])


def sam3_agreement(window_tls, t0, t1):
    res = []
    for t, boxes in sorted(SAM3.items()):
        if not (t0 - 0.6 <= t <= t1 + 0.6):
            continue
        matched = 0
        for sb in boxes:
            for tl in window_tls:
                hit = any(abs(s - t) < 1.2 and iou(sb, box) > 0.1 for s, box in tl["samples"])
                if hit:
                    matched += 1
                    break
        res.append((t, matched, len(boxes)))
    return res


def main():
    windows = [(68, 94), (187, 212), (330, 356), (378, 398)]
    out = {}
    for (a, b) in windows:
        t0 = time.time()
        tls = track_window(a, b)
        dt = time.time() - t0
        out[f"{a}-{b}"] = {
            "n_tracklets": len(tls),
            "runtime_s": round(dt, 1),
            "tracklets": [{"id": x["track_id"], "dur": x["duration_s"], "n": x["n"],
                           "samples": x["samples"]} for x in tls],
        }
        print(f"window {a}-{b}: {len(tls)} tracklets in {dt:.0f}s")
        for x in tls[:8]:
            print(f"   tid {x['track_id']}: dur {x['duration_s']}s n={x['n']}")
        for (t, m, n) in sam3_agreement(tls, a, b):
            print(f"   SAM3 t={t}: yolo matched {m}/{n}")
    json.dump(out, open(os.path.join(REPO, "out", "pid2_tracklets.json"), "w"), indent=1)
    print("wrote out/pid2_tracklets.json")


if __name__ == "__main__":
    main()
