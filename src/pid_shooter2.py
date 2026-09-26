"""PID-3 v1: per-shot actor via white (cue) ball geometry for ALL shots.

For each shot at t: frame at t-0.8 s; find the white ball ON THE CLOTH
(HSV: low saturation, high value, circular, plausible ball area); the actor is
the table-zone person whose bottom-centre is nearest the white ball.
Fallbacks: no white ball -> colour-only largest person; no person -> unknown.

Output: out/events_actors.json (overwrites v0) with method tags.
"""
import json
import os
import sys

import cv2
import numpy as np

os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/yolo-cfg")
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from pid_identity import torso_color, in_table_zone

REPO = os.path.dirname(ROOT)
VIDEO = os.path.join(REPO, "data", "vod_30min_260815.mp4")
MODEL = YOLO("yolov8n.pt")
EVENTS = json.load(open(os.path.join(REPO, "out", "scan30", "events_v2.json")))
ID = json.load(open(os.path.join(REPO, "out", "pid_identity_v0.json")))
centers = np.array(ID["centers_bgr"])  # BGR
order = np.argsort(centers.mean(axis=1))
B_CLUSTER, A_CLUSTER = int(order[0]), int(order[1])


def white_ball(bgr, cloth_mask):
    """Centre of the whitest circular blob on the cloth (cue ball)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    cand = (s < 90) & (v > 160)
    cand[cloth_mask == 0] = False
    cand = cv2.morphologyEx(cand.astype(np.uint8), cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(cand)
    best = None
    for i in range(1, n):
        x, y, w, hh, a = stats[i]
        if a < 80 or a > 7000:
            continue
        r = max(w, hh) / 2.0
        circ = a / (np.pi * r * r)
        if circ < 0.45:
            continue
        if best is None or a > best[0]:
            best = (a, (x + w / 2, y + hh / 2))
    return best[1] if best else None


def classify(rgb):
    da = np.linalg.norm(np.array(rgb) - centers[A_CLUSTER][::-1])
    db = np.linalg.norm(np.array(rgb) - centers[B_CLUSTER][::-1])
    return "A" if da <= db else "B"


def main():
    sys.path.insert(0, ROOT)
    from table_detect import detect_cloth_mask
    cap = cv2.VideoCapture(VIDEO)
    shots = [e for e in EVENTS if e["type"] == "shot"]
    out = []
    stats = {"geometry": 0, "colour": 0, "no_person": 0, "white_found": 0}
    for e in shots:
        t = e["t"]
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t - 0.8) * 1000.0)
        ok, bgr = cap.read()
        if not ok:
            continue
        cloth = detect_cloth_mask(bgr)
        wb = white_ball(bgr, cloth)
        if wb is not None:
            stats["white_found"] += 1
        res = MODEL.predict(bgr, conf=0.35, classes=[0], verbose=False)
        persons = []
        if res[0].boxes is not None:
            for b in res[0].boxes.xyxy.cpu().numpy():
                bb = [int(v) for v in b]
                if in_table_zone(bb):
                    persons.append(bb)
        cands = []
        for bb in persons:
            rgb = torso_color(bgr, bb)
            if rgb is None:
                continue
            bottom = np.array([(bb[0] + bb[2]) / 2, bb[3]])
            dist = float(np.linalg.norm(bottom - np.array(wb))) if wb else None
            cands.append({"rgb": [round(x, 1) for x in rgb],
                          "cluster": classify(rgb), "dist_cue_px": dist,
                          "area": (bb[2] - bb[0]) * (bb[3] - bb[1])})
        if not cands:
            out.append({"t": t, "actor": None, "method": "no-person"})
            stats["no_person"] += 1
            continue
        if wb is not None:
            actor = min(cands, key=lambda c: c["dist_cue_px"])
            stats["geometry"] += 1
            method = "white-ball"
        else:
            actor = max(cands, key=lambda c: c["area"])
            stats["colour"] += 1
            method = "colour"
        out.append({"t": t, "actor": actor["cluster"],
                    "dist_cue_px": round(actor["dist_cue_px"], 1)
                    if actor["dist_cue_px"] is not None else None,
                    "method": method, "n_persons": len(cands)})
    cap.release()
    print(stats)
    seq = "".join("A" if o["actor"] == "A" else ("B" if o["actor"] == "B" else "?") for o in out)
    sw = sum(1 for i in range(1, len(seq))
             if seq[i] in "AB" and seq[i - 1] in "AB" and seq[i] != seq[i - 1])
    print("actor seq:", seq)
    print("A/B switches:", sw)
    json.dump(out, open(os.path.join(REPO, "out", "events_actors.json"), "w"), indent=1)
    print("wrote out/events_actors.json")


if __name__ == "__main__":
    main()
