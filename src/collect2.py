"""Collect mask-only ball crops + highlighted context from a NEW set of frames.

Usage: collect2.py <video> <out_dir> <t1> <t2> ...
Writes out_dir/{tNNNNN_bNN.jpg (mask-only crop), ctx/ctx_*.png, meta.json, ctx.json}
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))            # the repo root, for the src.* imports
from PIL import Image
from sam3_cpu import load_sam3_image_model, make_processor
from src.ball_gate import (SAM3_BALL_MAX_AREA_PX, SAM3_BALL_MIN_AREA_PX,
                           SAM3_BALL_MIN_SCORE)

VIDEO = Path(sys.argv[1])
OUT = Path(sys.argv[2])
TIMES = [float(x) for x in sys.argv[3:]]
CTX = OUT / 'ctx'
OUT.mkdir(parents=True, exist_ok=True)
CTX.mkdir(exist_ok=True)

print('loading SAM3...', flush=True)
model = load_sam3_image_model(str(ROOT / 'data' / 'sam3.safetensors'), device='cpu')
model.float()
proc = make_processor(model, device='cpu')

cap = cv2.VideoCapture(str(VIDEO))
meta = []
ctx_map = {}
for t in TIMES:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
    ok, bgr = cap.read()
    if not ok:
        print(f't={t}: no frame', flush=True)
        continue
    H, W = bgr.shape[:2]
    st = proc.set_image(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
    st = proc.set_text_prompt('billiard ball', st)
    masks = st['masks'].cpu().numpy()
    scores = st['scores'].cpu().numpy()
    kept = 0
    for i in range(len(scores)):
        if scores[i] < SAM3_BALL_MIN_SCORE:
            continue
        m = np.squeeze(masks[i])
        area = float(m.sum())
        if area < SAM3_BALL_MIN_AREA_PX or area > SAM3_BALL_MAX_AREA_PX:
            continue
        ys, xs = np.where(m > 0)
        y0, y1 = int(ys.min()), int(ys.max())
        x0, x1 = int(xs.min()), int(xs.max())
        # mask-only tight crop
        pad = 6
        cy0, cy1 = max(0, y0 - pad), min(H, y1 + pad)
        cx0, cx1 = max(0, x0 - pad), min(W, x1 + pad)
        mm = (m[cy0:cy1, cx0:cx1] > 0).astype(np.uint8)
        roi = bgr[cy0:cy1, cx0:cx1].copy()
        roi[mm == 0] = 0
        name = f't{int(t):05d}_b{kept:02d}.jpg'
        cv2.imwrite(str(OUT / name), roi)
        # context window
        half = int(max(x1 - x0, y1 - y0) * 4.2)
        half = min(max(half, 200), min(H, W) // 2 - 4)
        wx0, wy0 = (x0 + x1) // 2 - half, (y0 + y1) // 2 - half
        wx1, wy1 = wx0 + 2 * half, wy0 + 2 * half
        win = bgr[max(wy0, 0):min(wy1, H), max(wx0, 0):min(wx1, W)].copy()
        px0, py0 = max(0, -wx0), max(0, -wy0)
        if wx0 < 0 or wy0 < 0 or wx1 > W or wy1 > H:
            win = cv2.copyMakeBorder(win, py0, max(0, wy1 - H), px0, max(0, wx1 - W),
                                     cv2.BORDER_REPLICATE)
        tmask = m[max(wy0, 0):min(wy1, H), max(wx0, 0):min(wx1, W)]
        cnts, _ = cv2.findContours((tmask > 0).astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(win, cnts, -1, (0, 0, 255), 2)
        win = cv2.resize(win, (win.shape[1] * 2, win.shape[0] * 2), interpolation=cv2.INTER_LINEAR)
        ctx_name = 'ctx_' + name.replace('.jpg', '.png')
        cv2.imwrite(str(CTX / ctx_name), win)
        meta.append({'t': t, 'file': str(OUT / name), 'score': round(float(scores[i]), 3)})
        ctx_map[str(OUT / name)] = str(CTX / ctx_name)
        kept += 1
    print(f't={t}: {kept} balls', flush=True)
cap.release()
(OUT / 'meta.json').write_text(json.dumps(meta, indent=1))
(OUT / 'ctx.json').write_text(json.dumps(ctx_map, indent=1))
print('DONE total', len(meta))
