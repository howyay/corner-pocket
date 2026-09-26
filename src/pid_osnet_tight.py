"""PID-4 v3: OSNet separation on SAM3 MASK-TIGHT person crops.

Uses out/pid_masks/{meta.json,tight/*} (13 frames across the two tracklet
windows). Each YOLO track sample at time t is matched to the SAM3 person with
max bbox IoU; its tight crop is embedded. Reports intra/inter cosine for the
two colour-separated tracks per window and compares with the full-crop run.
"""
import json
import os
import sys

import cv2
import numpy as np
import torch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src", "reid"))
import osnet as O  # noqa

META = json.load(open(os.path.join(REPO, "out", "pid_masks", "meta.json")))
TR = json.load(open(os.path.join(REPO, "out", "pid2_tracklets.json")))
W = os.path.join(REPO, "src", "reid", "weights", "osnet_x0_25_msmt17.pth")
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

model = O.osnet_x0_25(pretrained=False, num_classes=1000)
sd = torch.load(W, map_location="cpu", weights_only=False)
sd = sd.get("state_dict", sd)
model.load_state_dict({k: v for k, v in sd.items()
                       if not k.startswith("classifier")}, strict=False)
model.eval()


def iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def embed_file(path):
    img = cv2.imread(path)
    if img is None:
        return None
    img = cv2.resize(img, (128, 256))
    rgb = img[:, :, ::-1].astype(np.float32) / 255.0
    rgb = (rgb - MEAN) / STD
    x = torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0)
    with torch.no_grad():
        return model(x)[0].numpy()


def persons_at(t):
    return META.get(str(int(round(t))), [])


def analyse(win):
    tls = TR[win]["tracklets"]
    by_id = {t["id"]: t["samples"] for t in tls}
    # colour-separated selection as before (quick torso means via tight crops absent -> reuse saved picks from pid_osnet_tracks run)
    col = []
    for i, samples in by_id.items():
        got = []
        for t, box in samples:
            for p in persons_at(t):
                if iou(box, p["bbox"]) > 0.3:
                    got.append(p)
                    break
        if got:
            col.append((i, got))
    if len(col) < 2:
        print(f"{win}: <2 tracks with tight crops")
        return None
    # choose pair with max mean-colour distance from tight crops
    def mean_rgb(got):
        cols = []
        for p in got:
            img = cv2.imread(p["file"])
            if img is None:
                continue
            nz = np.argwhere(np.any(img > 12, axis=2))
            if len(nz) < 50:
                continue
            y0, x0 = nz.min(0)
            y1, x1 = nz.max(0)
            cols.append(img[y0:y1 + 1, x0:x1 + 1].reshape(-1, 3).mean(axis=0)[::-1])
        return np.mean(cols, axis=0) if cols else None
    best = None
    for i in range(len(col)):
        for j in range(i + 1, len(col)):
            ri, rj = mean_rgb(col[i][1]), mean_rgb(col[j][1])
            if ri is None or rj is None:
                continue
            d = np.linalg.norm(ri - rj)
            if best is None or d > best[0]:
                best = (d, col[i][0], col[j][0])
    if best is None:
        return None
    dcol, ida, idb = best
    embs = {}
    for tid, got in col:
        if tid not in (ida, idb):
            continue
        es = []
        for p in got:
            e = embed_file(p["file"])
            if e is not None:
                es.append(e)
        if len(es) >= 3:
            embs[tid] = np.array(es)
    if len(embs) < 2:
        return None
    A, B = embs[ida], embs[idb]
    A /= np.linalg.norm(A, axis=1, keepdims=True) + 1e-9
    B /= np.linalg.norm(B, axis=1, keepdims=True) + 1e-9
    offA = (A @ A.T)[np.triu_indices(len(A), 1)] if len(A) > 1 else np.array([1.0])
    offB = (B @ B.T)[np.triu_indices(len(B), 1)] if len(B) > 1 else np.array([1.0])
    inter = float((A @ B.T).mean())
    res = {"win": win, "tracks": [ida, idb], "colour_dist": round(dcol, 0),
           "nA": len(A), "nB": len(B),
           "intraA": round(float(offA.mean()), 3), "intraB": round(float(offB.mean()), 3),
           "inter": round(inter, 3)}
    print(res)
    return res


if __name__ == "__main__":
    out = []
    for w in ["68-94", "330-356"]:
        r = analyse(w)
        if r:
            out.append(r)
    json.dump(out, open(os.path.join(REPO, "out", "pid_osnet_tight.json"), "w"), indent=1)
    print("wrote out/pid_osnet_tight.json")
