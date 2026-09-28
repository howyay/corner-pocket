"""Canonical table geometry: the cloth quad -> canonical millimetre homography.

Only numpy and cv2. The server projects scan millimetres into frame pixels with
this; importing it from src/pipeline.py loaded torch + SAM3 on the first
/api/<dataset>/events after a start. src/pipeline.py re-exports both names.
"""
from __future__ import annotations

import cv2
import numpy as np

# Rasson Victory III, 9 ft: playing surface 2540 x 1270 mm (100" x 50", WPA).
# Canonical frame is in MILLIMETRES, portrait: width 1270 (x, left-right),
# length 2540 (y, head at top, foot at bottom) -- matches the camera view.
CANON_W, CANON_H = 1270, 2540  # mm


def homography_to_canonical(corners: np.ndarray) -> np.ndarray:
    """Map the cloth quad [TL, TR, BR, BL] to the canonical table.

    The canonical frame is width x length = CANON_W x CANON_H, oriented like
    the camera view: head rail at the top, foot rail at the bottom, left long
    rail on the left.  TL -> (0,0) [head-left], TR -> (W,0) [head-right],
    BR -> (W,H) [foot-right], BL -> (0,H) [foot-left].  The long rails run
    vertically (x=0 and x=W) and the side pockets sit at their midpoints.
    """
    dst = np.array(
        [[0, 0], [CANON_W - 1, 0], [CANON_W - 1, CANON_H - 1], [0, CANON_H - 1]],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(corners.astype(np.float32), dst)
