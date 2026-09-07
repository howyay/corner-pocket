"""PID-4 v2: OSNet self-consistency along YOLO tracklets.

For windows with two long-lived tracks (the two players), embed sampled crops
per track (every ~2 s) and report intra-track vs inter-track cosine separation:
this measures whether the tracker + embedder keep the two identities apart.
"""
import json
import sys

import cv2
import numpy as np
import torch

sys.path.insert(0, "/home/operator/projects/pool/src/reid")
import osnet as O  # noqa

VIDEO = "/home/operator/projects/pool/data/vod_30min_260815.mp4"
TR = json.load(open("/home/operator/projects/pool/out/pid2_tracklets.json"))
W = "/home/operator/projects/pool/src/reid/weights/osnet_x0_25_msmt17.pth"
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

model = O.osnet_x0_25(pretrained=False, num_classes=1000)
sd = torch.load(W, map_location="cpu", weights_only=False)
sd = sd.get("state_dict", sd)
sd = {k: v for k, v in sd.items() if not k.startswith("classifier")}
model.load_state_dict(sd, strict=False)
model.eval()


def embed(bgr, bb, mode="full"):
    x0, y0, x1, y1 = bb
    pad = 15
    h, w = bgr.shape[:2]
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
    crop = bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    if mode == "torso":
        hh = crop.shape[0]
        crop = crop[int(hh * 0.1):int(hh * 0.85), :]
        if crop.size == 0:
            return None
    crop = cv2.resize(crop, (128, 256))
    rgb = crop[:, :, ::-1].astype(np.float32) / 255.0
    rgb = (rgb - MEAN) / STD
    x = torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0)
    with torch.no_grad():
        return model(x)[0].numpy()


def analyze(win_key, mode):
    tls = TR[win_key]["tracklets"]
    if len(tls) < 2:
        print(f"{win_key}: <2 tracks")
        return None
    by_id = {t["id"]: t["samples"] for t in tls}
    # mean torso colour per track (>=8 samples), pick the two most different
    cap0 = cv2.VideoCapture(VIDEO)
    tcol = {}
    for i, t in by_id.items():
        cols = []
        for tt, box in t[:: max(1, len(t) // 10)]:
            cap0.set(cv2.CAP_PROP_POS_MSEC, tt * 1000.0)
            ok0, f0 = cap0.read()
            if not ok0:
                continue
            x0, y0, x1, y1 = box
            hh = y1 - y0
            band = f0[int(y0 + 0.15 * hh):int(y0 + 0.5 * hh), x0:x1]
            if band.size:
                cols.append(band.reshape(-1, 3).mean(axis=0)[::-1])
        if len(cols) >= 8:
            tcol[i] = np.mean(cols, axis=0)
    cap0.release()
    if len(tcol) < 2:
        print(f"{win_key}: <2 coloured tracks")
        return None
    ids = None
    bd = -1
    ks = list(tcol)
    for a in range(len(ks)):
        for b in range(a + 1, len(ks)):
            d = np.linalg.norm(tcol[ks[a]] - tcol[ks[b]])
            if d > bd:
                bd, ids = d, (ks[a], ks[b])
    ids = list(ids)
    print(f"{win_key}: colour-separated tracks {ids} (dist {bd:.0f})")
    cap = cv2.VideoCapture(VIDEO)
    embs = {i: [] for i in ids}
    for i in ids:
        prev_t = None
        for t, box in by_id[i]:
            if prev_t is not None and t - prev_t < 1.8:
                continue
            prev_t = t
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, bgr = cap.read()
            if not ok:
                continue
            e = embed(bgr, box, mode)
            if e is not None:
                embs[i].append(e)
    cap.release()
    A = np.array(embs[ids[0]])
    B = np.array(embs[ids[1]])
    if len(A) < 3 or len(B) < 3:
        print(f"{win_key}: too few samples {len(A)}/{len(B)}")
        return None
    A /= np.linalg.norm(A, axis=1, keepdims=True) + 1e-9
    B /= np.linalg.norm(B, axis=1, keepdims=True) + 1e-9
    S = A @ B.T
    inter = float(S.mean())
    # cleaner intra: off-diagonal mean
    offA = (A @ A.T)[np.triu_indices(len(A), 1)]
    offB = (B @ B.T)[np.triu_indices(len(B), 1)]
    print(f"{win_key} [{mode}]: nA={len(A)} nB={len(B)}  "
          f"intraA={offA.mean():.3f} intraB={offB.mean():.3f} inter={inter:.3f} "
          f"gap={min(offA.mean(), offB.mean()) - inter:.3f}")
    return {"win": win_key, "mode": mode, "nA": len(A), "nB": len(B),
            "intraA": round(float(offA.mean()), 3), "intraB": round(float(offB.mean()), 3),
            "inter": round(inter, 3)}


if __name__ == "__main__":
    out = []
    for w in ["68-94", "330-356"]:
        for mode in ("full", "torso"):
            r = analyze(w, mode)
            if r:
                out.append(r)
    json.dump(out, open("/home/operator/projects/pool/out/pid_osnet_tracks.json", "w"), indent=1)
    print("wrote out/pid_osnet_tracks.json")
