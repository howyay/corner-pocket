"""PID-3 v0 + identity binding: per-shot actor selection (geometry + colour).

For every shot in events_v2:
  frame at t-1.2 s -> YOLO persons (table zone) -> torso colour cluster
  (A = light, B = dark, from pid_identity prototypes);
  if the shot is verified (ball_from mm) project the cue-ball position through
  the vod30 calibration and score each person by distance(person bottom-center,
  cue ball) -> actor = nearest; else actor = colour-identified person with the
  largest area (fallback) or unknown.

Outputs out/events_actors.json + summary stats for review against the
shooter-A/B ground truth the annotator collects.
"""
import json
import os
import sys

import cv2
import numpy as np

os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/yolo-cfg")
os.environ.setdefault("ULTRALYTICS_SAFE_LOAD", "1")  # weights-only YOLO load (audit D-2)
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from pid_identity import torso_color, in_table_zone

REPO = os.path.dirname(ROOT)
VIDEO = os.path.join(REPO, "data", "vod_30min_260815.mp4")
MODEL = YOLO("yolov8n.pt")
EVENTS = json.load(open(os.path.join(REPO, "out", "scan30", "events_v2.json")))
CAL = json.load(open(os.path.join(REPO, "out", "calib_vod30.json")))
H = np.array(CAL["H"])  # mm -> px
QUAD = np.array(json.load(open(os.path.join(REPO, "out", "corners_30min_v2.json")))["corners"], np.float32)

ID = json.load(open(os.path.join(REPO, "out", "pid_identity_v0.json")))
centers_bgr = np.array(ID["centers_bgr"])
# cluster labels: 0/1 from pid_identity; brightness decides A(light)/B(dark)
order = np.argsort(centers_bgr.mean(axis=1))  # dim -> bright
B_CLUSTER = int(order[0])
A_CLUSTER = int(order[1])
print(f"clusters: A(light)=c{A_CLUSTER} {centers_bgr[A_CLUSTER].round(0)} "
      f"B(dark)=c{B_CLUSTER} {centers_bgr[B_CLUSTER].round(0)}", flush=True)


def mm_to_px(x, y):
    p = H @ np.array([x, y, 1.0])
    return np.array([p[0] / p[2], p[1] / p[2]])


def classify(rgb):
    dA = np.linalg.norm(np.array(rgb) - centers_bgr[A_CLUSTER][::-1])
    dB = np.linalg.norm(np.array(rgb) - centers_bgr[B_CLUSTER][::-1])
    return "A" if dA <= dB else "B"


def main():
    cap = cv2.VideoCapture(VIDEO)
    shots = [e for e in EVENTS if e["type"] == "shot"]
    out = []
    n_geom, n_col, n_any = 0, 0, 0
    for e in shots:
        t = e["t"]
        frame_t = max(0.0, t - 1.2)
        cap.set(cv2.CAP_PROP_POS_MSEC, frame_t * 1000.0)
        ok, bgr = cap.read()
        if not ok:
            continue
        res = MODEL.predict(bgr, conf=0.35, classes=[0], verbose=False)
        persons = []
        if res[0].boxes is not None:
            for b in res[0].boxes.xyxy.cpu().numpy():
                bb = [int(v) for v in b]
                if in_table_zone(bb):
                    persons.append(bb)
        cue_px = None
        if e.get("ball_from"):
            cue_px = mm_to_px(*e["ball_from"])
        cands = []
        for bb in persons:
            rgb = torso_color(bgr, bb)
            if rgb is None:
                continue
            bottom = np.array([(bb[0] + bb[2]) / 2, bb[3]])
            dist = float(np.linalg.norm(bottom - cue_px)) if cue_px is not None else None
            area = (bb[2] - bb[0]) * (bb[3] - bb[1])
            cands.append({"bbox": bb, "rgb": [round(v, 1) for v in rgb],
                          "cluster": classify(rgb), "dist_cue_px": dist,
                          "area": int(area)})
        if not cands:
            out.append({"t": t, "actor": None, "reason": "no person"})
            continue
        n_any += 1
        if cue_px is not None:
            actor = min(cands, key=lambda c: c["dist_cue_px"])
            n_geom += 1
        else:
            actor = max(cands, key=lambda c: c["area"])
        n_col += 1
        out.append({"t": t, "actor": actor["cluster"], "dist_cue_px":
                    round(actor["dist_cue_px"], 1) if actor["dist_cue_px"] is not None else None,
                    "n_persons": len(cands),
                    "cands": [{k: v for k, v in c.items() if k != "bbox"} for c in cands]})
    cap.release()
    seq = "".join("A" if o["actor"] == "A" else ("B" if o["actor"] == "B" else "?") for o in out)
    print(f"shots: {len(shots)} | actor assigned {sum(1 for o in out if o['actor'])} "
          f"(geometry {n_geom}, colour-only {n_any - n_geom}) | no-person {sum(1 for o in out if o['actor'] is None)}")
    print("actor sequence:", seq)
    # switches
    sw = sum(1 for i in range(1, len(seq)) if seq[i] in "AB" and seq[i - 1] in "AB" and seq[i] != seq[i - 1])
    print("A/B switches:", sw)
    json.dump(out, open(os.path.join(REPO, "out", "events_actors.json"), "w"), indent=1)
    print("wrote out/events_actors.json")


if __name__ == "__main__":
    main()
