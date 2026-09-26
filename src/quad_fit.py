"""Robust pool-table quad fitting v3 (HOM-1).

The 720p stream over-segments blue cloth (walls/clothing share hue), so we:
1. anchor the cloth hue from the image centre band,
2. build a tight mask around that hue (high saturation, narrow hue window),
3. take the largest component, un-rotate by minAreaRect and fit the four side
   lines with iterative nearest-line assignment over the FULL boundary,
4. geometrically gate the result (coverage gates).

Contract: return None when the table boundary is not recoverable; callers use
the segment median homography (camera is static).
"""
from __future__ import annotations

import cv2
import numpy as np


def _anchor_hue(bgr):
    h, w = bgr.shape[:2]
    cx, cy, rw, rh = w // 2, h // 2, int(w * 0.18), int(h * 0.28)
    roi = bgr[cy - rh:cy + rh, cx - rw:cx + rw]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1]
    sel = hsv[s > 120].reshape(-1, 3)
    if len(sel) < 100:
        sel = hsv.reshape(-1, 3)
    return int(np.median(sel[:, 0]))


def cloth_mask_tight(bgr, hwin=16, smin=105, vmin=55, close=19, open_k=9):
    hue = _anchor_hue(bgr)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lo = (max(0, hue - hwin), smin, vmin)
    hi = (min(179, hue + hwin), 255, 255)
    mask = cv2.inRange(hsv, lo, hi)
    kc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close))
    ko = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kc, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, ko, iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None, hue
    order = np.argsort(-stats[1:, cv2.CC_STAT_AREA])
    comp = None
    for take in (1, 2):
        merged = np.zeros_like(mask)
        for i in order[:take]:
            merged[labels == i + 1] = 255
        if int(merged.sum()) > 60000:
            comp = merged
            break
    return comp, hue


def fit_quad_v3(bgr):
    mask, hue = cloth_mask_tight(bgr)
    if mask is None:
        return None
    h, w = bgr.shape[:2]
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    big = max(cnts, key=cv2.contourArea)
    rect = cv2.minAreaRect(big)
    rw_, rh_ = rect[1]
    lo, hi = sorted((rw_, rh_))
    if hi / max(lo, 1) > 3.6 or lo < 120:
        return None
    flat = big.reshape(-1, 2).astype(np.float64)
    ang = np.deg2rad(rect[2])
    ca, sa = np.cos(-ang), np.sin(-ang)
    cen = np.array(rect[0])
    p = flat - cen
    pr = np.column_stack([p[:, 0] * ca - p[:, 1] * sa, p[:, 0] * sa + p[:, 1] * ca])
    x0, x1 = pr[:, 0].min(), pr[:, 0].max()
    y0, y1 = pr[:, 1].min(), pr[:, 1].max()
    dx, dy = (x1 - x0), (y1 - y0)

    # iterative assignment: 0 top, 1 bottom, 2 left, 3 right (rotated frame)
    l_top, l_bot = y0 + 0.05 * dy, y1 - 0.05 * dy
    l_left, l_right = x0 + 0.05 * dx, x1 - 0.05 * dx
    for _ in range(8):
        d_top = np.abs(pr[:, 1] - l_top)
        d_bot = np.abs(pr[:, 1] - l_bot)
        d_left = np.abs(pr[:, 0] - l_left)
        d_right = np.abs(pr[:, 0] - l_right)
        D = np.column_stack([d_top, d_bot, d_left, d_right])
        sid = D.argmin(1)
        ntop = float(np.median(pr[sid == 0, 1]))
        nbot = float(np.median(pr[sid == 1, 1]))
        nleft = float(np.median(pr[sid == 2, 0]))
        nright = float(np.median(pr[sid == 3, 0]))
        if abs(ntop - l_top) + abs(nbot - l_bot) + abs(nleft - l_left) + abs(nright - l_right) < 0.05:
            l_top, l_bot, l_left, l_right = ntop, nbot, nleft, nright
            break
        l_top, l_bot, l_left, l_right = ntop, nbot, nleft, nright
    else:
        pass

    def to_img(q):
        return np.column_stack([q[:, 0] * ca + q[:, 1] * sa,
                                -q[:, 0] * sa + q[:, 1] * ca]) + cen

    quad_r = np.array([[l_left, l_top], [l_right, l_top],
                       [l_right, l_bot], [l_left, l_bot]], np.float32)
    quad = to_img(quad_r).astype(np.float32)
    if not cv2.isContourConvex(quad.astype(np.int32).reshape(-1, 1, 2)):
        return None
    if np.any(quad < -25) or np.any(quad[:, 0] > w + 25) or np.any(quad[:, 1] > h + 25):
        return None
    poly = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(poly, quad.reshape(-1, 1, 2).astype(np.int32), 1)
    cover = float((mask > 0)[poly > 0].mean())
    out_frac = float((mask > 0)[poly == 0].mean()) if (poly == 0).any() else 0.0
    if cover < 0.55 or out_frac > 0.25:
        return None
    return quad


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    which = sys.argv[1] if len(sys.argv) > 1 else "v30"
    if which == "v30":
        VIDEO = str(ROOT / "data" / "vod_30min_260815.mp4")
        REF = np.array(json.load(open(ROOT / "out" / "corners_30min.json"))["corners"], np.float32)
        TIMES = list(range(60, 1741, 120))
    else:
        VIDEO = str(ROOT / "data" / "vod_highlight.mp4")
        REF = np.array(json.load(open(ROOT / "out" / "fixed_corners.json"))["corners"], np.float32)
        TIMES = [5, 28, 60, 90, 150, 200]
    cap = cv2.VideoCapture(VIDEO)
    errs, fails = [], []
    for t in TIMES:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, f = cap.read()
        if not ok:
            continue
        q = fit_quad_v3(f)
        if q is None:
            fails.append(t)
            print(f"t={t}: FAIL")
            continue
        e = float(np.linalg.norm(q - REF, axis=1).mean())
        errs.append(e)
        print(f"t={t}: ok mean_px_err={e:.1f}")
    cap.release()
    if errs:
        errs.sort()
        print(f"summary: ok {len(errs)}/{len(TIMES)} median={errs[len(errs)//2]:.1f}px "
              f"p90={errs[int(len(errs)*0.9)]:.1f}px fails={fails}")
