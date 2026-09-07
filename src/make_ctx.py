"""Generate context images for each unlabeled ball crop.

Each crop was cut from data/vod_highlight.mp4 at time t. We relocate the crop
inside its original frame with cv2.matchTemplate (exact pixels => score ~1.0),
then render an enlarged window around the ball with a highlight ring so a human
can identify the ball from neighbouring balls / cloth position (rack cases).

Outputs out/unlabeled_crops/ctx/ctx_<crop>.png + ctx.json (crop -> ctx file).
"""
import json
import os
import sys
import glob
from pathlib import Path

import cv2
import numpy as np

VIDEO = Path("/home/operator/projects/pool/data/vod_highlight.mp4")
CROP_DIR = Path("/home/operator/projects/pool/out/unlabeled_crops")
META = CROP_DIR / "meta.json"
CTX_DIR = CROP_DIR / "ctx"
OUT_JSON = CROP_DIR / "ctx.json"

cap = cv2.VideoCapture(str(VIDEO))
fps = cap.get(cv2.CAP_PROP_FPS)
print("fps", fps, file=sys.stderr)

meta = json.loads(META.read_text())
os.makedirs(CTX_DIR, exist_ok=True)

result = {}
cache = {}
problems = []


def frames_near(t, r=6):
    """Yield (frame_index, bgr) around time t; POS_MSEC can land a frame off,
    which matters when balls are moving (break shots)."""
    if t in cache:
        return cache[t]
    base = int(round(t * fps))  # t is in seconds
    out = []
    for idx in range(base - r, base + r + 1):
        if idx < 0:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, bgr = cap.read()
        if ok:
            out.append((idx, bgr))
    cache[t] = out
    return out


for row in meta:
    t = float(row["t"])
    crop_path = Path(row["file"])
    name = crop_path.name
    ctx_name = "ctx_" + name.replace(".jpg", ".png")
    out_path = CTX_DIR / ctx_name
    result[crop_path.as_posix()] = str(out_path)
    if out_path.exists():
        continue
    crop = cv2.imread(str(crop_path))
    if crop is None:
        problems.append((name, "crop unreadable"))
        continue
    H, W = -1, -1
    ch, cw = crop.shape[:2]
    best = None  # (score, frame_idx, frame, top-left)
    for idx, frame in frames_near(t):
        H, W = frame.shape[:2]
        if cw >= W or ch >= H:
            continue
        res = cv2.matchTemplate(frame, crop, cv2.TM_CCOEFF_NORMED)
        _, mxv, _, mxl = cv2.minMaxLoc(res)
        if best is None or mxv > best[0]:
            best = (mxv, idx, frame, mxl)
    if best is None:
        problems.append((name, "frame not available"))
        continue
    mxv, idx, frame, mxl = best
    if mxv < 0.9:
        problems.append((name, f"no match ({mxv:.2f})"))
        continue
    H, W = frame.shape[:2]
    cx = mxl[0] + cw // 2
    cy = mxl[1] + ch // 2
    # window: square, ~9x the ball bbox (tight crop is ball+10px pad)
    half = int(max(cw, ch) * 4.5)
    half = max(half, 180)
    half = min(half, min(H, W) // 2 - 4)
    x0, y0 = cx - half, cy - half
    x1, y1 = cx + half, cy + half
    # pad with reflection when window exceeds frame
    win = frame[max(y0, 0):min(y1, H), max(x0, 0):min(x1, W)]
    px0, py0 = max(0, -x0), max(0, -y0)
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
        win = cv2.copyMakeBorder(win, py0, max(0, y1 - H), px0, max(0, x1 - W),
                                 cv2.BORDER_REPLICATE)
    # highlight ring around the located ball bbox
    bx0, by0 = mxl[0] - x0 + px0, mxl[1] - y0 + py0
    bx1, by1 = bx0 + cw, by0 + ch
    cv2.rectangle(win, (bx0, by0), (bx1, by1), (0, 0, 255), max(2, min(win.shape[:2]) // 220))
    cv2.circle(win, ((bx0 + bx1) // 2, (by0 + by1) // 2),
               max(2, (bx1 - bx0) // 2), (0, 0, 255), max(1, min(win.shape[:2]) // 260))
    up = 2
    win = cv2.resize(win, (win.shape[1] * up, win.shape[0] * up), interpolation=cv2.INTER_LINEAR)
    cv2.imwrite(str(out_path), win)
    print(f"{name}: frame={idx} match={mxv:.3f} window={x0},{y0}->{x1},{y1}", file=sys.stderr)

cap.release()
OUT_JSON.write_text(json.dumps(result, indent=1))
print("ctx files:", len(result))
print("problems:", problems)
print("DONE")
