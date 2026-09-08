"""PID-6 rebuild: OSNet prototypes from person-seeded tracks + propagation.

Reads out/pid_seed.json (written by pid_seed_ui.py):
  {"seeds": {"<track_id>:<win>": {"win","t","track_id"}}}
For each seed: that track becomes identity A; the colour-most-different long
track in the same window becomes B.  All samples of both tracks are embedded
(full crops, pad 15) -> per-identity mean embedding (L2-normalised).
Propagation: every track in every window is embedded and assigned A/B/? by
cosine margin (>0.02) -> out/pid_seed_tracks.json.

Outputs:
  out/pid_seed_protos.json  {"A": [...], "B": [...], "n_per_identity": {...}}
  out/pid_seed_tracks.json  {"map": {"<track_id>:<win>": "A"|"B"|"?"}, "detail": ...}
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reid"))
import osnet as O  # noqa

VIDEO = ROOT.parent / "data" / "vod_30min_260815.mp4"
TR = ROOT.parent / "out" / "pid2_tracklets.json"
SEED = ROOT.parent / "out" / "pid_seed.json"
PROTO = ROOT.parent / "out" / "pid_seed_protos.json"
TRK = ROOT.parent / "out" / "pid_seed_tracks.json"
W = ROOT / "reid" / "weights" / "osnet_x0_25_msmt17.pth"
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
MARGIN = 0.02

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


def torso_col(bgr, box):
    x0, y0, x1, y1 = box
    h = y1 - y0
    band = bgr[max(0, y0 + int(0.15 * h)):y0 + int(0.5 * h), x0:x1]
    if band.size < 100:
        return None
    return band.reshape(-1, 3).mean(axis=0)[::-1]


def run():
    tr = json.load(open(TR))
    seeds = json.loads(SEED.read_text())["seeds"] if SEED.exists() else {}
    if not seeds:
        raise SystemExit("no seeds recorded")

    cap = cv2.VideoCapture(str(VIDEO))
    emb_cache = {}

    def track_embeddings(win, tid):
        key = f"{tid}:{win}"
        if key in emb_cache:
            return emb_cache[key]
        tk = next(t for t in tr[win]["tracklets"] if t["id"] == tid)
        es, cols = [], []
        for tt, box in tk["samples"][::2]:
            cap.set(cv2.CAP_PROP_POS_MSEC, tt * 1000.0)
            ok, bgr = cap.read()
            if not ok:
                continue
            e = embed(bgr, box)
            if e is not None:
                es.append(e)
            c = torso_col(bgr, box)
            if c is not None:
                cols.append(c)
        out = (np.array(es), np.mean(cols, axis=0) if cols else None)
        emb_cache[key] = out
        return out

    protoA, protoB = [], []
    for key, s in seeds.items():
        win, tid = s["win"], s["track_id"]
        tk = next(t for t in tr[win]["tracklets"] if t["id"] == tid)
        # B = longest other track with most-different torso colour
        ea, ca = track_embeddings(win, tid)
        if len(ea) < 5 or ca is None:
            continue
        best, bd = None, -1
        for other in tr[win]["tracklets"]:
            if other["id"] == tid or other["n"] < 8:
                continue
            eb, cb = track_embeddings(win, other["id"])
            if cb is None or len(eb) < 5:
                continue
            d = float(np.linalg.norm(ca - cb))
            if d > bd:
                bd, best = d, (other["id"], eb)
        if best is None:
            continue
        obid, eb = best
        protoA.append(ea.mean(axis=0))
        protoB.append(eb.mean(axis=0))

    if not protoA:
        raise SystemExit("no usable seeds")
    A = np.mean(protoA, axis=0)
    A /= np.linalg.norm(A) + 1e-9
    B = np.mean(protoB, axis=0)
    B /= np.linalg.norm(B) + 1e-9
    PROTO.write_text(json.dumps({
        "A": A.tolist(), "B": B.tolist(),
        "n_per_identity": {"A": len(protoA), "B": len(protoB)}}))

    # propagate to every track in every window
    mapping, detail = {}, []
    for win in tr:
        for tk in tr[win]["tracklets"]:
            if tk["n"] < 4:
                continue
            e, _ = track_embeddings(win, tk["id"])
            if len(e) < 3:
                continue
            m = e.mean(axis=0)
            m /= np.linalg.norm(m) + 1e-9
            ca, cb = float(m @ A), float(m @ B)
            ident = "?" if abs(ca - cb) < MARGIN else ("A" if ca > cb else "B")
            mapping[f"{tk['id']}:{win}"] = ident
            detail.append({"win": win, "track": tk["id"], "n": tk["n"],
                           "cosA": round(ca, 3), "cosB": round(cb, 3),
                           "identity": ident})
    TRK.write_text(json.dumps({"map": mapping, "detail": detail}, indent=1))
    cap.release()
    return {"map": mapping, "n": len(mapping)}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
