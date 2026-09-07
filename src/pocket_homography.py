"""Robust homography from the 6 pocket anchors (Rasson Victory III, 9 ft).

The playing field is 2540 x 1270 mm.  The 6 pocket openings are high-contrast
dark blobs at the cloth boundary: 4 at the corners, 2 at the physical
midpoints of the long rails.  We detect dark blobs along the cloth boundary,
then search the 8 cyclic corner assignments for the one whose 6-point
homography minimizes reprojection error onto the canonical pocket positions.
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

W_MM, H_MM = 1270.0, 2540.0  # playing surface (Rasson Victory III 9 ft)
CANON_POCKETS = np.array([
    [0.0, 0.0], [W_MM, 0.0], [W_MM, H_MM], [0.0, H_MM],   # corners TL TR BR BL
    [0.0, H_MM / 2], [W_MM, H_MM / 2],                     # side pockets (long rails)
], dtype=np.float32)


def detect_pocket_blobs(bgr: np.ndarray, quad: np.ndarray) -> list[tuple[float, float, float]]:
    """Dark round blobs near the cloth boundary (pocket openings)."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 70, 255, cv2.THRESH_BINARY_INV)
    mask = detect_cloth_mask(bgr)
    boundary = cv2.dilate(mask, np.ones((25, 25), np.uint8))
    th = cv2.bitwise_and(th, cv2.bitwise_not(boundary))  # only outside the cloth
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 80 or area > 4000:
            continue
        peri = cv2.arcLength(c, True)
        if peri <= 0:
            continue
        circ = 4 * np.pi * area / (peri * peri)
        if circ < 0.4:
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx, cy = M["m10"] / M["m00"], M["m01"] / M["m00"]
        out.append((float(cx), float(cy), float(area)))
    return out


def fit_homography_from_pockets(blobs: list[tuple[float, float, float]],
                                quad: np.ndarray) -> tuple[np.ndarray, np.ndarray, float] | None:
    """Try cyclic corner assignments; return (H, assigned_blobs, error_mm)."""
    q = np.asarray(quad, dtype=np.float32).reshape(4, 2)
    if len(blobs) < 6:
        return None
    best = None
    # corner blob candidates: nearest blob to each quad corner
    corner_cands = []
    for c in q:
        ds = [np.hypot(b[0] - c[0], b[1] - c[1]) for b in blobs]
        i = int(np.argmin(ds))
        corner_cands.append((blobs[i], ds[i]))
    # side-pocket candidates: blobs not used as corners
    used = {id(cb) for cb, _ in corner_cands}
    side_cands = [b for b in blobs if id(b) not in used]
    if len(side_cands) < 2:
        return None
    # quad cyclic orders: corners are assigned to canonical TL,TR,BR,BL in
    # cyclic order; try the 4 rotations of the canonical corner list, and for
    # each, the 2 possible assignments of the side pockets.
    for rot in range(4):
        canon_corners = np.roll(CANON_POCKETS[:4], -rot, axis=0)
        # side pockets canonical positions for this rotation: edges of the quad
        # are (q[i], q[i+1]); canonical edge endpoints are (canon[i], canon[i+1])
        for flip in (0, 1):
            side1, side2 = side_cands[0], side_cands[1]
            if flip:
                side1, side2 = side2, side1
            # try both side-pocket pairings onto the two long rails
            for pair in (((0, 1), (2, 3)), ((2, 3), (0, 1))):
                e1, e2 = pair
                mid1 = (canon_corners[e1[0]] + canon_corners[e1[1]]) / 2
                mid2 = (canon_corners[e2[0]] + canon_corners[e2[1]]) / 2
                src = np.array([[cb[0], cb[1]] for cb, _ in corner_cands] +
                               [[side1[0], side1[1]], [side2[0], side2[1]]],
                              dtype=np.float32)
                dst = np.vstack([canon_corners, mid1, mid2]).astype(np.float32)
                H, _ = cv2.findHomography(src, dst, method=0)
                if H is None:
                    continue
                # reprojection error in mm
                p = H @ np.hstack([src, np.ones((len(src), 1))]).T
                p = p[:2] / p[2]
                err = float(np.sqrt(((p.T - dst) ** 2).sum(axis=1)).mean())
                if best is None or err < best[3]:
                    best = (H, src, dst, err)
    return best


def estimate_corners_30min(video: str, n_samples: int = 90) -> np.ndarray:
    """Median pocket-anchored homography over the video -> returns H."""
    cap = cv2.VideoCapture(video)
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
    hs = []
    ts = np.linspace(dur * 0.05, dur * 0.95, n_samples)
    for t in ts:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, f = cap.read()
        if not ok:
            continue
        quad = fit_quadrilateral(detect_cloth_mask(f))
        if quad is None:
            continue
        blobs = detect_pocket_blobs(f, quad)
        res = fit_homography_from_pockets(blobs, quad)
        if res is not None:
            hs.append(res[0])
    cap.release()
    if not hs:
        raise RuntimeError("no pocket homography could be fitted")
    return np.median(np.array(hs), axis=0)


if __name__ == "__main__":
    video = sys.argv[1] if len(sys.argv) > 1 else "data/vod_30min_260828.mp4"
    H = estimate_corners_30min(video)
    json.dump({"H": H.tolist()}, open("out/pocket_H_30min.json", "w"))
    print("H saved:", H)
