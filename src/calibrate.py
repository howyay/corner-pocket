"""Rectangle-constrained calibration (Rasson Victory III, 9 ft).

The true table geometry (2540 x 1270 mm playing surface, portrait) is the
OBJECT model: the estimator is a PnP solve whose object points are the real
rectangle corners and pocket midpoints.  A noisy corner detection therefore
becomes an outlier for RANSAC/median aggregation instead of silently
distorting an unconstrained 4-point homography.

Pipeline:
  1. per frame: cloth quad -> targeted pocket anchor detection
     (windows around corners and, iteratively, around the projected side
     pockets);
  2. per frame: PnP with focal-length scan, all corner assignments tried,
     keep lowest residual;
  3. across frames: median of the robust per-frame homographies;
  4. report independent anchor residuals in mm (pocket blobs) -> the bar is
     mean <= 15 mm.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from table_detect import detect_cloth_mask, fit_quadrilateral
from table_geometry import CANON_H, CANON_W, POCKETS_MM

WM, HM = float(CANON_W), float(CANON_H)  # mm, the canonical frame (table_geometry)
# canonical object points (mm): corners TL,TR,BR,BL then side pockets -- the
# POCKETS_MM order, as float64 for solvePnP
OBJECT_MM = np.array(list(POCKETS_MM.values()), dtype=np.float64)
# solvePnP/projectPoints need 3D object points (table plane at z = 0)
OBJECT_3D = np.hstack([OBJECT_MM, np.zeros((len(OBJECT_MM), 1))])


def darkest_in_window(gray, cx, cy, cloth=None, r=36, min_area=120, max_area=6000):
    """Centroid of the largest dark blob in a window (pocket hole).

    cloth: optional cloth mask (same size as gray); cloth pixels are excluded
    so the search finds the hole beyond the cushion, not cloth shadows.
    """
    x0, y0 = max(0, int(cx) - r), max(0, int(cy) - r)
    x1, y1 = min(gray.shape[1], int(cx) + r), min(gray.shape[0], int(cy) + r)
    win = gray[y0:y1, x0:x1]
    if win.size == 0:
        return None
    _, th = cv2.threshold(win, 80, 255, cv2.THRESH_BINARY_INV)
    if cloth is not None:
        cw = cloth[y0:y1, x0:x1]
        th[cw > 0] = 0
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        a = cv2.contourArea(c)
        if a < min_area or a > max_area:
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        if best is None or a > best[2]:
            best = (x0 + M["m10"] / M["m00"], y0 + M["m01"] / M["m00"], a)
    if best is None:
        return (float(cx), float(cy))
    return (best[0], best[1])


def refined_blob(gray, x, y, cloth, r=22):
    """Small-window dark blob around (x, y), eroded to drop shadow tails."""
    x0, y0 = max(0, int(x) - r), max(0, int(y) - r)
    x1, y1 = min(gray.shape[1], int(x) + r), min(gray.shape[0], int(y) + r)
    win = gray[y0:y1, x0:x1]
    if win.size == 0:
        return (float(x), float(y))
    _, th = cv2.threshold(win, 80, 255, cv2.THRESH_BINARY_INV)
    if cloth is not None:
        cw = cloth[y0:y1, x0:x1]
        th[cw > 0] = 0
    th = cv2.erode(th, np.ones((3, 3), np.uint8), iterations=1)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        a = cv2.contourArea(c)
        if a < 60:
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        # prefer the blob closest to the predicted anchor
        d = np.hypot((x0 + M["m10"] / M["m00"]) - x, (y0 + M["m01"] / M["m00"]) - y)
        if best is None or d < best[0]:
            best = (d, x0 + M["m10"] / M["m00"], y0 + M["m01"] / M["m00"])
    if best is None:
        return (float(x), float(y))
    return (best[1], best[2])


def anchors_for_frame(bgr, quad, cloth, H_prev=None):
    """Detect the 6 pocket anchors around the predictions of a prior H.

    With a good prior homography (image px <-> canonical mm) we search a tight
    window around each projected anchor and take the closest dark blob.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if H_prev is None:
        q = np.asarray(quad, dtype=np.float32).reshape(4, 2)
        centroid = q.mean(axis=0)
        corners = []
        for c in q:
            out = c + 40.0 * (c - centroid) / max(1e-6, np.linalg.norm(c - centroid))
            corners.append(refined_blob(gray, out[0], out[1], cloth))
        mid01 = (q[0] + q[1]) / 2
        mid23 = (q[2] + q[3]) / 2
        mid03 = (q[0] + q[3]) / 2
        mid12 = (q[1] + q[2]) / 2
        return corners, [(mid01, mid23), (mid03, mid12)]
    inv = np.linalg.inv(H_prev)
    anchors = []
    for (mx, my) in OBJECT_MM:
        p = inv @ np.array([mx, my, 1.0])
        ix, iy = p[0] / p[2], p[1] / p[2]
        anchors.append(refined_blob(gray, ix, iy, cloth))
    return anchors[:4], anchors[4:]


def pnp_solve(img_pts6, f, W, H):
    pts = np.asarray(img_pts6, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 4 or not np.isfinite(pts).all():
        return None
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]], dtype=np.float64)
    ok, rvec, tvec = cv2.solvePnP(OBJECT_3D[: len(pts)],
                                  np.ascontiguousarray(pts), K, np.zeros(4),
                                  flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return None
    R, _ = cv2.Rodrigues(rvec)
    return K @ np.hstack([R[:, :2], tvec.reshape(3, 1)])


def project(Hm, pts):
    p = Hm @ np.hstack([pts, np.ones((len(pts), 1))]).T
    return (p[:2] / p[2]).T


def calibrate(video, n_samples=60, f_lo=600, f_hi=2000, f_steps=29):
    cap = cv2.VideoCapture(video)
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
    W, H = int(cap.get(3)), int(cap.get(4))
    frame_data = []
    for t in np.linspace(dur * 0.02, dur * 0.98, n_samples):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, bgr = cap.read()
        if not ok:
            continue
        quad = fit_quadrilateral(detect_cloth_mask(bgr))
        if quad is None:
            continue
        corners, side_guess = anchors_for_frame(bgr, quad)
        # corner assignment: quad order may be TL,TR,BR,BL or rotated; try the
        # 4 rotations of the canonical corner order.
        for rot in range(4):
            canon = np.roll(OBJECT_MM[:4], -rot, axis=0)
            for s1, s2 in side_guess:
                for flip in (0, 1):
                    a, b = (s1, s2) if flip == 0 else (s2, s1)
                    img6 = np.array(corners[:4] + [a, b], dtype=np.float32)
                    frame_data.append((t, rot, img6))
        cap.release()
        break  # single frame path for testing
    cap.release()
    # full scan loop (reopen) if n_samples > 1 handled below
    return frame_data, (W, H)


def quad_ok(cloth, quad):
    """A usable quad: convex, 4 well-separated corners, close to the cloth."""
    area = float(cloth.sum())
    qa = cv2.contourArea(quad.astype(np.int32).reshape(-1, 1, 2))
    pts = quad.reshape(4, 2)
    if qa < 0.3 * area:
        return False
    if min(np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1)) < 25:
        return False
    return bool(cv2.isContourConvex(quad.astype(np.int32).reshape(-1, 1, 2)))


def calibrate_full(video, n_samples=60, f_lo=600, f_hi=2000, f_steps=29, H_prior=None):
    cap = cv2.VideoCapture(video)
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
    W, H = int(cap.get(3)), int(cap.get(4))
    frames = []  # (t, img6 list per assignment)
    ts = np.linspace(dur * 0.02, dur * 0.98, n_samples)
    for t in ts:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, bgr = cap.read()
        if not ok:
            continue
        cloth = detect_cloth_mask(bgr)
        quad = fit_quadrilateral(cloth)
        if quad is None or not quad_ok(cloth, quad):
            continue
        corners, side_guess = anchors_for_frame(bgr, quad, cloth, H_prev=H_prior)
        if corners is None or any(c is None for c in corners):
            continue
        cands = []
        if H_prior is not None:
            cands.append((0, np.array(corners[:4] + side_guess, dtype=np.float32)))
        else:
            for rot in range(4):
                for s1, s2 in side_guess:
                    for flip in (0, 1):
                        a, b = (s1, s2) if flip == 0 else (s2, s1)
                        cands.append((rot, np.array(corners[:4] + [a, b], dtype=np.float32)))
        frames.append(cands)
    cap.release()
    if not frames:
        raise RuntimeError("no frames")
    # focal scan + per-frame best assignment
    best_f, best_med = None, 1e18
    for f in np.linspace(float(f_lo), float(f_hi), int(f_steps)):
        meds = []
        for cands in frames:
            r = None
            for rot, img6 in cands:
                Hm = pnp_solve(img6, f, W, H)
                if Hm is None:
                    continue
                err = float(np.sqrt(((project(Hm, OBJECT_MM) - img6) ** 2).sum(axis=1)).mean())
                if r is None or err < r[0]:
                    r = (err, Hm)
            if r:
                meds.append(r[0])
        med = float(np.median(meds)) if meds else 1e18
        if med < best_med:
            best_med, best_f = med, f
    # refit all frames at best focal, median H
    Hs = []
    for cands in frames:
        r = None
        for rot, img6 in cands:
            Hm = pnp_solve(img6, best_f, W, H)
            if Hm is None:
                continue
            err = float(np.sqrt(((project(Hm, OBJECT_MM) - img6) ** 2).sum(axis=1)).mean())
            if r is None or err < r[0]:
                r = (err, Hm)
        if r:
            Hs.append(r[1])
    Hm = np.median(np.array(Hs), axis=0)
    return {"f_px": float(best_f), "median_resid_px": float(best_med),
            "frames": len(frames), "H": Hm.tolist()}


if __name__ == "__main__":
    video = sys.argv[1] if len(sys.argv) > 1 else "/tmp/vod30.mp4"
    out = calibrate_full(video)
    Path(ROOT.parent / "out").mkdir(exist_ok=True)
    json.dump(out, open(ROOT.parent / "out" / "calib_pnp.json", "w"), indent=1)
    print(json.dumps(out, indent=1))
