"""Table corner fitting v4 (HOM-1): boundary-LINE based quad for 720p.

v3 failed because minAreaRect's angle is ambiguous by 90° and the mask often
loses one rail, biasing median-based sides. v4:
1. tight cloth mask (hue-anchored) -> largest component boundary,
2. minAreaRect -> un-rotate by the LONG-axis angle (fixes the 90° flip),
3. EM side assignment (init at 1%/99% extrema) with per-side robust line fits,
4. side-line intersection -> corners; geometric + coverage gates.

A side with too few points (occluded rail) yields None -> caller skips the
frame; the segment-level builder then takes a MAD-filtered temporal median
(camera is static).
"""
from __future__ import annotations

import cv2
import numpy as np

from quad_fit import _anchor_hue, cloth_mask_tight


def _line_yx(points, ang_tol_deg=18.0):
    """Robust fit of x = a*y + b over 2D points (vertical-ish line family)."""
    pts = np.asarray(points, np.float64)
    if len(pts) < 12:
        return None
    best = None
    rng = np.random.default_rng(11)
    for _ in range(80):
        i, j = rng.choice(len(pts), 2, replace=False)
        dy = pts[j, 1] - pts[i, 1]
        dx = pts[j, 0] - pts[i, 0]
        if abs(dx) <= abs(dy) * np.tan(np.deg2rad(ang_tol_deg)):
            continue  # require mostly-vertical (small dx per dy)
        if abs(dy) < 4:
            continue
        a = dx / dy
        b = pts[i, 0] - a * pts[i, 1]
        d = np.abs(a * pts[:, 1] + b - pts[:, 0]) / np.hypot(a, 1)
        nin = int((d < 1.5).sum())
        if best is None or nin > best[0]:
            best = (nin, (a, b))
    if best is None or best[0] < 0.3 * len(pts):
        return None
    a, b = best[1]
    d = np.abs(a * pts[:, 1] + b - pts[:, 0]) / np.hypot(a, 1)
    inl = pts[d < 1.5]
    if len(inl) >= 12:
        A = np.column_stack([inl[:, 1], np.ones(len(inl))])
        a, b = np.linalg.lstsq(A, inl[:, 0], rcond=None)[0]
    return a, b


def _line_xy(points, ang_tol_deg=18.0):
    """Robust fit of y = a*x + b (horizontal-ish line family)."""
    pts = np.asarray(points, np.float64)
    if len(pts) < 12:
        return None
    best = None
    rng = np.random.default_rng(13)
    for _ in range(80):
        i, j = rng.choice(len(pts), 2, replace=False)
        dx = pts[j, 0] - pts[i, 0]
        dy = pts[j, 1] - pts[i, 1]
        if abs(dy) > abs(dx) * np.tan(np.deg2rad(ang_tol_deg)):
            continue
        if abs(dx) < 4:
            continue
        a = dy / dx
        b = pts[i, 1] - a * pts[i, 0]
        d = np.abs(a * pts[:, 0] + b - pts[:, 1]) / np.hypot(a, 1)
        nin = int((d < 1.5).sum())
        if best is None or nin > best[0]:
            best = (nin, (a, b))
    if best is None or best[0] < 0.3 * len(pts):
        return None
    a, b = best[1]
    d = np.abs(a * pts[:, 0] + b - pts[:, 1]) / np.hypot(a, 1)
    inl = pts[d < 1.5]
    if len(inl) >= 12:
        A = np.column_stack([inl[:, 0], np.ones(len(inl))])
        a, b = np.linalg.lstsq(A, inl[:, 1], rcond=None)[0]
    return a, b


def _boundary_angle(flat):
    """Dominant orientation of a boundary point set (deg, 0..180)."""
    v = np.diff(flat, axis=0)
    ln = np.hypot(v[:, 0], v[:, 1])
    ln[ln < 1e-6] = 0
    ang = np.degrees(np.arctan2(v[:, 1], v[:, 0])) % 180.0
    hist, _ = np.histogram(ang, bins=180, range=(0, 180), weights=ln)
    k = np.ones(7) / 7
    hist = np.convolve(hist, k, mode='same')
    best = float(np.argmax(hist))
    # perpendicular family should carry similar weight: refine with both
    return best


def _fit_at_angle(flat, cen, theta_deg, min_frac=0.05):
    """Rotate points by -theta, EM side assignment w/ line refits; returns
    (quad_in_image or None, mean_residual)."""
    ang = np.deg2rad(theta_deg)
    ca, sa = np.cos(-ang), np.sin(-ang)
    p = flat - cen
    pr = np.column_stack([p[:, 0] * ca - p[:, 1] * sa, p[:, 0] * sa + p[:, 1] * ca])

    def to_img(q):
        q = np.asarray(q, np.float64).reshape(-1, 2)
        return np.column_stack([q[:, 0] * ca + q[:, 1] * sa,
                                -q[:, 0] * sa + q[:, 1] * ca]) + cen

    x0, x1 = np.percentile(pr[:, 0], 1), np.percentile(pr[:, 0], 99)
    y0, y1 = np.percentile(pr[:, 1], 1), np.percentile(pr[:, 1], 99)
    n = len(pr)
    lines = {'L': (0.0, x0), 'R': (0.0, x1), 'T': (y0, 0.0), 'B': (y1, 0.0)}
    for _ in range(12):
        dL = np.abs(lines['L'][0] * pr[:, 1] + lines['L'][1] - pr[:, 0]) / np.hypot(lines['L'][0], 1)
        dR = np.abs(lines['R'][0] * pr[:, 1] + lines['R'][1] - pr[:, 0]) / np.hypot(lines['R'][0], 1)
        dT = np.abs(lines['T'][0] * pr[:, 0] + lines['T'][1] - pr[:, 1]) / np.hypot(lines['T'][0], 1)
        dB = np.abs(lines['B'][0] * pr[:, 0] + lines['B'][1] - pr[:, 1]) / np.hypot(lines['B'][0], 1)
        D = np.column_stack([dL, dR, dT, dB])
        sid = D.argmin(1)
        new = {}
        bad = False
        for key, idx in (('L', 0), ('R', 1), ('T', 2), ('B', 3)):
            sel = pr[sid == idx]
            if len(sel) < min_frac * n:
                bad = True
                break
            fit = _line_yx(sel) if key in ('L', 'R') else _line_xy(sel)
            if fit is None:
                bad = True
                break
            new[key] = fit
        if bad:
            return None, 1e9
        lines = new
    resid = np.minimum.reduce([
        np.abs(lines['L'][0] * pr[:, 1] + lines['L'][1] - pr[:, 0]) / np.hypot(lines['L'][0], 1),
        np.abs(lines['R'][0] * pr[:, 1] + lines['R'][1] - pr[:, 0]) / np.hypot(lines['R'][0], 1),
        np.abs(lines['T'][0] * pr[:, 0] + lines['T'][1] - pr[:, 1]) / np.hypot(lines['T'][0], 1),
        np.abs(lines['B'][0] * pr[:, 0] + lines['B'][1] - pr[:, 1]) / np.hypot(lines['B'][0], 1),
    ])
    mean_resid = float(resid.mean())
    def inter_vh(vline, hline):
        av, bv = vline
        ah, bh = hline
        if abs(av * ah - 1) < 1e-6:
            return None
        y = (ah * bv + bh) / (1 - av * ah)
        return np.array([av * y + bv, y])
    tl = inter_vh(lines['L'], lines['T'])
    tr = inter_vh(lines['R'], lines['T'])
    br = inter_vh(lines['R'], lines['B'])
    bl = inter_vh(lines['L'], lines['B'])
    if any(c is None for c in (tl, tr, br, bl)):
        return None, mean_resid
    quad = np.array([to_img(tl), to_img(tr), to_img(br), to_img(bl)], np.float32)
    return quad, mean_resid


def fit_quad_lines(bgr):
    mask, hue = cloth_mask_tight(bgr)
    if mask is None:
        return None
    h, w = bgr.shape[:2]
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    big = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(big) < 40000:
        return None
    flat = big.reshape(-1, 2).astype(np.float64)
    rect = cv2.minAreaRect(big)
    cen = np.array(rect[0])
    # robust orientation: boundary-angle histogram +/- grid refinement
    theta0 = _boundary_angle(flat)
    # try both theta0 and theta0+90 for the 'long' direction, refine +-6 deg
    cands = []
    for base in (theta0 % 180.0, (theta0 + 90.0) % 180.0):
        for dth in range(-6, 7, 2):
            cands.append((base + dth) % 180.0)
    best_q, best_r = None, 1e9
    for th in cands:
        q, r = _fit_at_angle(flat, cen, th)
        if q is not None and r < best_r:
            best_q, best_r = q, r
    if best_q is None:
        return None
    quad = np.asarray(best_q, np.float32).reshape(4, 2)
    if not cv2.isContourConvex(quad.astype(np.int32).reshape(-1, 1, 2)):
        return None
    if np.any(quad < -25) or np.any(quad[:, 0] > w + 25) or np.any(quad[:, 1] > h + 25):
        return None
    return quad


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.datasets import media_path
    from src.vod30_corners import load as load_vod30_corners
    which = sys.argv[1] if len(sys.argv) > 1 else "v30"
    if which == "v30":
        VIDEO = str(media_path(ROOT, "vod30"))
        REF = load_vod30_corners()
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
        q = fit_quad_lines(f)
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
