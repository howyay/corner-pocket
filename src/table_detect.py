"""Detect the pool table playing surface (blue cloth) in a single camera frame.

Strategy: HSV segmentation of the dominant cloth color -> largest connected
component -> quadrilateral fit -> 4 ordered corners.  The playing surface is
assumed to be a rectangle in world space (pool table bed), so we fit the
closest quadrilateral to the cloth mask boundary.
"""
from __future__ import annotations

import cv2
import numpy as np


def detect_cloth_mask(
    bgr: np.ndarray,
    h_low: int = 80,
    h_high: int = 130,
    s_min: int = 60,
    v_min: int = 50,
) -> np.ndarray:
    """Return a binary mask of the blue playing cloth (largest component)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (h_low, s_min, v_min), (h_high, 255, 255))
    # fill small holes (balls create holes in the cloth mask)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return mask
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (labels == largest).astype(np.uint8)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points TL, TR, BR, BL (clockwise from top-left)."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)


MIN_CORNER_GAP_PX = 2.0


def corners_are_distinct(quad: np.ndarray) -> bool:
    """Four corners are four points; a fit that repeats one is not a quadrilateral.

    ``cv2.approxPolyDP`` repeats a point when the contour it approximates is a sliver.  On the
    historical VODs that came out as a thin wedge hugging one rail, with one corner listed twice,
    which the playfield check then refused as ``not-convex`` - correctly, but the pipeline had
    already reported it as a measured table.  Refusing the fit here keeps a failed segmentation
    from being published as a measurement.  A sliver whose four corners do survive approximation
    is not caught by this test.
    """
    pts = np.asarray(quad, dtype=np.float32).reshape(4, 2)
    for i in range(4):
        for j in range(i + 1, 4):
            if float(np.linalg.norm(pts[i] - pts[j])) < MIN_CORNER_GAP_PX:
                return False
    return True


def fit_quadrilateral(mask: np.ndarray) -> np.ndarray | None:
    """Fit a 4-corner quadrilateral to the cloth mask; return ordered corners."""
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    peri = cv2.arcLength(c, True)
    quad = None
    # search for the epsilon that gives exactly 4 corners
    for eps in np.linspace(0.005, 0.06, 40):
        approx = cv2.approxPolyDP(c, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx) and corners_are_distinct(approx):
            quad = approx
            break
    if quad is None:
        hull = cv2.convexHull(c)
        quad = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
        if len(quad) != 4 or not corners_are_distinct(quad):
            return None
    ordered = _order_corners(quad.reshape(4, 2))
    # The ordering itself can collapse two corners onto one index (a point can be the extreme of
    # both the sum and the difference), and a collapsed ordering is not a table either.  The probe
    # on tw-2860883221 showed exactly this: four distinct fit points, one repeated after ordering.
    return ordered if corners_are_distinct(ordered) else None


def detect_table(bgr: np.ndarray) -> dict:
    """Full table detection. Returns corners, mask, and a debug image."""
    mask = detect_cloth_mask(bgr)
    corners = fit_quadrilateral(mask)
    debug = bgr.copy()
    if corners is not None:
        cv2.polylines(
            debug,
            [corners.astype(np.int32)],
            True,
            (0, 0, 255),
            3,
        )
        for i, (x, y) in enumerate(corners):
            cv2.circle(debug, (int(x), int(y)), 8, (0, 255, 255), -1)
            cv2.putText(
                debug, str(i), (int(x) + 10, int(y) + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2,
            )
    return {"corners": corners, "mask": mask, "debug": debug}


if __name__ == "__main__":
    import sys
    img = cv2.imread(sys.argv[1])
    res = detect_table(img)
    if res["corners"] is not None:
        print("corners:\n", res["corners"])
    else:
        print("NO QUAD")
    cv2.imwrite(sys.argv[2], res["debug"])
