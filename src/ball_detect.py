"""Candidate ball detection on the pool table cloth (classical color/geometry).

This is the *detector* stage of the pipeline: it proposes ball bounding boxes
that SAM3 then refines into precise masks.  Working on the cloth-masked image
avoids false positives from the background.
"""
from __future__ import annotations

import cv2
import numpy as np

# color name -> (name, HSV lower, HSV upper)
BALL_COLORS: dict[str, tuple[np.ndarray, np.ndarray]] = {
    "white": (np.array([0, 0, 150]), np.array([180, 60, 255])),
    "yellow": (np.array([15, 90, 110]), np.array([38, 255, 255])),
    "blue": (np.array([90, 80, 80]), np.array([125, 255, 255])),
    "red": (np.array([0, 120, 90]), np.array([10, 255, 255])),
    "red2": (np.array([170, 120, 90]), np.array([180, 255, 255])),
    "purple": (np.array([125, 60, 80]), np.array([155, 255, 255])),
    "orange": (np.array([8, 130, 130]), np.array([24, 255, 255])),
    "green": (np.array([40, 90, 90]), np.array([80, 255, 255])),
    "maroon": (np.array([0, 100, 40]), np.array([14, 255, 120])),
    # black 8-ball: dark AND desaturated (colored shadows on blue cloth stay saturated)
    "black": (np.array([0, 0, 0]), np.array([180, 70, 70])),
}


def detect_ball_candidates(
    bgr: np.ndarray,
    cloth_mask: np.ndarray,
    min_area: float = 40.0,
    max_area: float = 9000.0,
    circularity_thr: float = 0.55,
) -> list[dict]:
    """Return candidate balls as dicts with cx, cy, r, color, contour area."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    candidates: list[dict] = []
    for color, (lo, hi) in BALL_COLORS.items():
        m = cv2.inRange(hsv, lo, hi)
        m = cv2.bitwise_and(m, cloth_mask)  # only on the playing surface
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area < min_area or area > max_area:
                continue
            peri = cv2.arcLength(c, True)
            if peri == 0:
                continue
            circ = 4 * np.pi * area / (peri * peri)
            if circ < circularity_thr:
                continue
            (x, y), r = cv2.minEnclosingCircle(c)
            candidates.append(
                {
                    "cx": float(x),
                    "cy": float(y),
                    "r": float(r),
                    "color": color,
                    "area": float(area),
                    "circularity": float(circ),
                }
            )

    # Non-max suppression: merge candidates whose circles overlap heavily,
    # keeping the one with the best circularity (stripe balls trigger several
    # color masks at once).
    keep = []
    for cand in sorted(candidates, key=lambda d: -d["circularity"]):
        dup = False
        for k in keep:
            d = np.hypot(cand["cx"] - k["cx"], cand["cy"] - k["cy"])
            if d < 0.6 * (cand["r"] + k["r"]):
                dup = True
                break
        if not dup:
            keep.append(cand)
    return keep


def classify_ball_style(
    bgr: np.ndarray, cand: dict, cloth_mask: np.ndarray
) -> str:
    """Classify cue / solid / stripe from color coverage inside the disc."""
    x0, x1 = int(cand["cx"] - cand["r"]), int(cand["cx"] + cand["r"])
    y0, y1 = int(cand["cy"] - cand["r"]), int(cand["cy"] + cand["r"])
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(bgr.shape[1], x1), min(bgr.shape[0], y1)
    if x1 <= x0 or y1 <= y0:
        return "unknown"
    roi = bgr[y0:y1, x0:x1]
    if roi.size == 0:
        return "unknown"
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, (0, 0, 170), (180, 70, 255))
    total = roi.shape[0] * roi.shape[1]
    frac_white = white.sum() / 255 / total
    if cand["color"] == "white":
        return "cue" if frac_white > 0.5 else "unknown"
    if frac_white > 0.55:
        return "stripe"
    if frac_white < 0.35:
        return "solid"
    return "stripe"


def draw_candidates(bgr: np.ndarray, cands: list[dict]) -> np.ndarray:
    out = bgr.copy()
    for c in cands:
        cv2.circle(out, (int(c["cx"]), int(c["cy"])), int(c["r"]), (0, 255, 0), 2)
        cv2.putText(
            out, c["color"], (int(c["cx"]) - 20, int(c["cy"]) - int(c["r"]) - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
        )
    return out


if __name__ == "__main__":
    import sys

    sys.path.insert(0, "src")
    from table_detect import detect_table

    img = cv2.imread(sys.argv[1])
    t = detect_table(img)
    cands = detect_ball_candidates(img, t["mask"])
    print(f"{len(cands)} candidates")
    for c in cands:
        print(c["color"], round(c["cx"]), round(c["cy"]), round(c["r"], 1))
    cv2.imwrite(sys.argv[2], draw_candidates(img, cands))
