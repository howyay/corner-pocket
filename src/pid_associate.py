"""PID-5 v0: per-shot actor by OSNet prototype matching + cue geometry.

Prototypes: mean embeddings of the colour-separated track pairs from the two
tracklet windows (pid_osnet_tracks selection logic), named A (brighter torso)
and B (darker).  For each shot: persons at t-0.8 s -> embeddings -> cosine to
A/B prototypes; fusion v0 = person nearest the white (cue) ball when found,
else best prototype match; actor = that person's prototype argmax (margin
recorded).  Output out/events_actors.json (v2 schema: actor, cosA, cosB, margin).
"""
import json
import os
import sys

import cv2
import numpy as np
import torch

os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/yolo-cfg")
from ultralytics import YOLO

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src", "reid"))
import osnet as O  # noqa

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from pid_identity import in_table_zone, torso_color  # noqa

VIDEO = os.path.join(REPO, "data", "vod_30min_260815.mp4")
MODEL = YOLO("yolov8n.pt")
W = os.path.join(REPO, "src", "reid", "weights", "osnet_x0_25_msmt17.pth")
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

model = O.osnet_x0_25(pretrained=False, num_classes=1000)
sd = torch.load(W, map_location="cpu", weights_only=False)
sd = sd.get("state_dict", sd)
model.load_state_dict({k: v for k, v in sd.items() if not k.startswith("classifier")},
                      strict=False)
model.eval()


def embed(bgr, box):
    x0, y0, x1, y1 = box
    pad = 15
    h, w = bgr.shape[:2]
    crop = bgr[max(0, y0 - pad):min(h, y1 + pad), max(0, x0 - pad):min(w, x1 + pad)]
    if crop.size == 0:
        return None
    crop = cv2.resize(crop, (128, 256))
    a = crop[:, :, ::-1].astype(np.float32) / 255.0
    a = (a - MEAN) / STD
    x = torch.from_numpy(a.transpose(2, 0, 1)).unsqueeze(0)
    with torch.no_grad():
        e = model(x)[0].numpy()
    return e / (np.linalg.norm(e) + 1e-9)


def track_colour(bgr, box):
    c = torso_color(bgr, box)
    return c


def build_prototypes():
    """Mean embeddings + names for the two colour-separated track pairs."""
    tr = json.load(open(os.path.join(REPO, "out", "pid2_tracklets.json")))
    cap = cv2.VideoCapture(VIDEO)
    proto = []  # (name, mean_emb, colour)
    for win in ["68-94", "330-356"]:
        tls = {t["id"]: t["samples"] for t in tr[win]["tracklets"]}
        cols = {}
        emb = {}
        for tid, samples in tls.items():
            cc, ee = [], []
            for tt, box in samples[:: max(1, len(samples) // 10)]:
                cap.set(cv2.CAP_PROP_POS_MSEC, tt * 1000.0)
                ok, bgr = cap.read()
                if not ok:
                    continue
                col = track_colour(bgr, box)
                if col is not None:
                    cc.append(col)
                e = embed(bgr, box)
                if e is not None:
                    ee.append(e)
            if len(cc) >= 6 and len(ee) >= 6:
                cols[tid] = np.mean(cc, axis=0)
                emb[tid] = np.mean(ee, axis=0)
        ids = list(cols)
        if len(ids) < 2:
            continue
        a, b = ids[0], ids[1]
        if np.linalg.norm(cols[a] - cols[b]) < 30:
            continue
        (dark, bright) = (a, b) if cols[a].mean() < cols[b].mean() else (b, a)
        proto.append(("A", emb[bright] / (np.linalg.norm(emb[bright]) + 1e-9), cols[bright]))
        proto.append(("B", emb[dark] / (np.linalg.norm(emb[dark]) + 1e-9), cols[dark]))
    cap.release()
    # average A and B across windows
    names = {}
    for name, e, col in proto:
        names.setdefault(name, []).append(e)
    out = {}
    for name, es in names.items():
        m = np.mean(es, axis=0)
        out[name] = m / (np.linalg.norm(m) + 1e-9)
    return out


def main():
    from table_detect import detect_cloth_mask
    proto = build_prototypes()
    print("prototypes:", {k: round(float(v.mean()), 3) for k, v in proto.items()}, flush=True)
    ev = json.load(open(os.path.join(REPO, "out", "scan30", "events_v2.json")))
    shots = [e for e in ev if e["type"] == "shot"]
    cap = cv2.VideoCapture(VIDEO)
    out = []
    n_geo = n_embed = 0
    for e in shots:
        t = e["t"]
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t - 0.8) * 1000.0)
        ok, bgr = cap.read()
        if not ok:
            continue
        cloth = detect_cloth_mask(bgr)
        # white ball
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        cand = (hsv[:, :, 1] < 90) & (hsv[:, :, 2] > 160)
        cand[cloth == 0] = False
        cand = cv2.morphologyEx(cand.astype(np.uint8), cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(cand)
        wb = None
        for i in range(1, n):
            x, y, ww, hh, a = stats[i]
            if a < 80 or a > 7000:
                continue
            r = max(ww, hh) / 2.0
            if a / (np.pi * r * r) < 0.45:
                continue
            if wb is None or a > wb[0]:
                wb = (a, (x + ww / 2.0, y + hh / 2.0))
        wb = wb[1] if wb else None
        res = MODEL.predict(bgr, conf=0.35, classes=[0], verbose=False)
        persons = []
        if res[0].boxes is not None:
            for b in res[0].boxes.xyxy.cpu().numpy():
                bb = [int(v) for v in b]
                if in_table_zone(bb):
                    persons.append(bb)
        best = None
        for bb in persons:
            e = embed(bgr, bb)
            if e is None:
                continue
            cos = {k: float(e @ v) for k, v in proto.items()}
            bottom = np.array([(bb[0] + bb[2]) / 2.0, bb[3]])
            dgeo = float(np.linalg.norm(bottom - np.array(wb))) if wb is not None else None
            if best is None or (dgeo is not None and (best.get("dgeo") is None or dgeo < best["dgeo"])):
                best = {"cos": cos, "dgeo": dgeo, "bbox": bb}
        if best is None:
            out.append({"t": t, "actor": None, "method": "no-person"})
            continue
        cosA, cosB = best["cos"].get("A", 0.0), best["cos"].get("B", 0.0)
        actor = "A" if cosA >= cosB else "B"
        margin = abs(cosA - cosB)
        if best["dgeo"] is not None:
            n_geo += 1
        n_embed += 1
        out.append({"t": t, "actor": actor, "cosA": round(cosA, 3), "cosB": round(cosB, 3),
                    "margin": round(margin, 3), "dgeo_px": best["dgeo"],
                    "method": "osnet-geo" if best["dgeo"] is not None else "osnet"})
    cap.release()
    seq = "".join("A" if o["actor"] == "A" else ("B" if o["actor"] == "B" else "?") for o in out)
    sw = sum(1 for i in range(1, len(seq))
             if seq[i] in "AB" and seq[i - 1] in "AB" and seq[i] != seq[i - 1])
    low = sum(1 for o in out if o.get("margin") is not None and o["margin"] < 0.05)
    print(f"shots {len(shots)} assigned {n_embed} | geo {n_geo} | low-margin {low}")
    print("seq:", seq)
    print("switches:", sw)
    json.dump(out, open(os.path.join(REPO, "out", "events_actors.json"), "w"), indent=1)
    print("wrote out/events_actors.json")


if __name__ == "__main__":
    main()
