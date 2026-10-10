"""Re-cut ball crops with instance masks so each tight crop contains exactly ONE
ball (masked, neighbours removed) and each context image highlights the exact
segmented instance.

Labels carry over by position: each old crop is relocated in its source frame
by template matching; the new instance with the largest mask-bbox IoU over that
location inherits the old file name (labels.json keys stay valid).

Outputs (same names as before, overwritten):
  out/unlabeled_crops/<old>.jpg   tight mask-only crop, black background
  out/unlabeled_crops/ctx/ctx_<old>.png  context window, target mask highlighted
  out/unlabeled_crops/meta.json   refreshed (same file keys)
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

VIDEO = ROOT / 'data' / 'vod_highlight.mp4'
CROP_DIR = ROOT / 'out' / 'unlabeled_crops'
CTX_DIR = CROP_DIR / 'ctx'
META = CROP_DIR / 'meta.json'
TIMES = [5, 28, 60, 90, 150, 200]

os.makedirs(CTX_DIR, exist_ok=True)

print('loading SAM3 on cpu...', flush=True)
model = load_sam3_image_model(str(ROOT / 'data' / 'sam3.safetensors'), device='cpu')
model.float()
proc = make_processor(model, device='cpu')

cap = cv2.VideoCapture(str(VIDEO))
fps = cap.get(cv2.CAP_PROP_FPS)

old_meta = json.loads(META.read_text())
old_rows = {r['file']: r for r in old_meta}
print('old crops:', len(old_rows), flush=True)


def read_frame(t):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
    ok, bgr = cap.read()
    return bgr if ok else None


def old_locations(frame, old_crop_path):
    """Relocate old tight crop inside the frame; returns (cx, cy, x0, y0, w, h) or None."""
    crop = cv2.imread(str(old_crop_path))
    if crop is None:
        return None
    ch, cw = crop.shape[:2]
    H, W = frame.shape[:2]
    if cw >= W or ch >= H:
        return None
    res = cv2.matchTemplate(frame, crop, cv2.TM_CCOEFF_NORMED)
    _, mxv, _, mxl = cv2.minMaxLoc(res)
    if mxv < 0.8:
        return None
    x0, y0 = mxl
    return (x0 + cw // 2, y0 + ch // 2, x0, y0, cw, ch)


def new_meta_row(t, name, score):
    return {"t": t, "file": str(CROP_DIR / name), "score": round(float(score), 3)}


new_meta = []
warnings = []
ctx_map = {}
for t in TIMES:
    bgr = read_frame(t)
    if bgr is None:
        warnings.append(f't={t}: frame unavailable')
        continue
    H, W = bgr.shape[:2]
    st = proc.set_image(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
    st = proc.set_text_prompt('billiard ball', st)
    masks = st['masks'].cpu().numpy()
    boxes = st['boxes'].cpu().numpy()
    scores = st['scores'].cpu().numpy()
    # collect candidate instances (same filters as original collection)
    insts = []
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
        insts.append({'score': scores[i], 'mask': m, 'bb': (x0, y0, x1, y1)})
    print(f't={t}: {len(insts)} instances', flush=True)

    # old crops for this time
    old_files = sorted([f for f in old_rows if f'{t:g}' == f'{t:g}'
                        and old_rows[f]['t'] == t], key=lambda f: f)
    # NOTE: times compare exactly; fall back below if nothing found
    if not old_files:
        old_files = sorted([f for f in old_rows if abs(float(old_rows[f]['t']) - t) < 0.01],
                           key=lambda f: f)
    used = set()
    for of in old_files:
        loc = old_locations(bgr, Path(of))
        if loc is None:
            warnings.append(f'{Path(of).name}: could not relocate, keeping old crop')
            new_meta.append(old_rows[of])
            continue
        ox0, oy0 = loc[2], loc[3]
        ow, oh = loc[4], loc[5]
        # best instance by bbox IoU with old crop rect
        best_i, best_iou = -1, 0.0
        for i, it in enumerate(insts):
            if i in used:
                continue
            bx0, by0, bx1, by1 = it['bb']
            ix0, iy0 = max(ox0, bx0), max(oy0, by0)
            ix1, iy1 = min(ox0 + ow, bx1), min(oy0 + oh, by1)
            inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
            union = ow * oh + (bx1 - bx0) * (by1 - by0) - inter
            iou = inter / union if union > 0 else 0.0
            if iou > best_iou:
                best_iou, best_i = iou, i
        if best_i < 0 or best_iou < 0.25:
            warnings.append(f'{Path(of).name}: no instance overlap ({best_iou:.2f}), keeping old')
            new_meta.append(old_rows[of])
            continue
        it = insts[best_i]
        used.add(best_i)
        m = it['mask']
        x0, y0, x1, y1 = it['bb']
        pad = 6
        y0, y1 = max(0, y0 - pad), min(H, y1 + pad)
        x0, x1 = max(0, x0 - pad), min(W, x1 + pad)
        mm = (m[y0:y1, x0:x1] > 0).astype(np.uint8)
        roi = bgr[y0:y1, x0:x1].copy()
        roi[mm == 0] = 0  # mask-only crop on black
        # mask-only tight crop (transparent handled by black background)
        name = Path(of).name
        cv2.imwrite(str(CROP_DIR / name), roi)
        new_meta.append(new_meta_row(t, name, it['score']))
        # context window ~9x instance bbox
        half = int(max(x1 - x0, y1 - y0) * 4.2)
        half = min(max(half, 200), min(H, W) // 2 - 4)
        wx0, wy0 = (x0 + x1) // 2 - half, (y0 + y1) // 2 - half
        wx1, wy1 = wx0 + 2 * half, wy0 + 2 * half
        win = bgr[max(wy0, 0):min(wy1, H), max(wx0, 0):min(wx1, W)].copy()
        px0, py0 = max(0, -wx0), max(0, -wy0)
        if wx0 < 0 or wy0 < 0 or wx1 > W or wy1 > H:
            win = cv2.copyMakeBorder(win, py0, max(0, wy1 - H), px0, max(0, wx1 - W),
                                     cv2.BORDER_REPLICATE)
        # overlay: target mask translucent red + contour; others dim
        tmask = m[max(wy0, 0):min(wy1, H), max(wx0, 0):min(wx1, W)]
        for j, oi in enumerate(insts):
            if j in used or j == best_i:
                continue
            om = oi['mask'][max(wy0, 0):min(wy1, H), max(wx0, 0):min(wx1, W)]
            if om is None:
                continue
            win[om > 0] = (win[om > 0] * 0.45).astype(np.uint8)
        ov = win.copy()
        if tmask is not None and tmask.shape == win.shape[:2]:
            ov[tmask > 0] = (0.6 * win[tmask > 0].astype(np.float32) +
                             0.4 * np.array([0, 0, 255], np.float32)).astype(np.uint8)
        win = ov
        cnts, _ = cv2.findContours((tmask > 0).astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(win, cnts, -1, (0, 0, 255), 2)
        up = 2
        win = cv2.resize(win, (win.shape[1] * up, win.shape[0] * up),
                         interpolation=cv2.INTER_LINEAR)
        ctx_name = 'ctx_' + name.replace('.jpg', '.png')
        cv2.imwrite(str(CTX_DIR / ctx_name), win)
        ctx_map[str(CROP_DIR / name)] = str(CTX_DIR / ctx_name)

cap.release()
# append genuinely new instances that matched no old crop (extra balls found)
print('new meta rows:', len(new_meta), flush=True)
META.write_text(json.dumps(new_meta, indent=1))
(CROP_DIR / 'ctx.json').write_text(json.dumps(ctx_map, indent=1))
print('warnings:', len(warnings))
for w in warnings[:30]:
    print(' -', w)
print('DONE')
