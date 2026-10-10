"""Canonical table geometry: the cloth quad -> canonical millimetre homography.

The canonical frame (CANON_W, CANON_H) and the pocket table (POCKETS_MM) have
their only definition site here. Every other module imports them, so the scan,
the gates, the rebuild and the server agree on one frame.

The constants and nearest_pocket use the standard library only. The array
builders (homography_to_canonical, canonical_destination, canonical_pockets)
import numpy (and cv2) inside the function, so importing this module stays
light. The module never imports torch or SAM3: importing it from
src/pipeline.py loaded torch + SAM3 on the first /api/<dataset>/events after a
start. src/pipeline.py re-exports CANON_W and CANON_H.
"""
from __future__ import annotations

import math

# Rasson Victory III, 9 ft: playing surface 2540 x 1270 mm (100" x 50", WPA).
# Canonical frame is in MILLIMETRES, portrait: width 1270 (x, left-right),
# length 2540 (y, head at top, foot at bottom) -- matches the camera view.
CANON_W = 1270  # mm, width (x): left long rail to right long rail
CANON_H = 2540  # mm, length (y): head rail to foot rail

# Pocket centres in the canonical frame: the four corners plus the two side
# pockets at the middle of the long rails. Order settles nearest-pocket ties.
POCKETS_MM = {
    "head-left": (0.0, 0.0),
    "head-right": (float(CANON_W), 0.0),
    "foot-right": (float(CANON_W), float(CANON_H)),
    "foot-left": (0.0, float(CANON_H)),
    "left-side": (0.0, float(CANON_H) / 2),
    "right-side": (float(CANON_W), float(CANON_H) / 2),
}

# The same table read in LANDSCAPE: the length on x, the width on y. It is not a
# second frame, only the transposed view of the one above (src/audit_calib.py
# audits in that reading on purpose). Both readings are defined here.
LANDSCAPE_W = CANON_H  # mm on x: head rail to foot rail
LANDSCAPE_H = CANON_W  # mm on y: left long rail to right long rail


def canonical_destination(landscape: bool = False) -> np.ndarray:
    """The cloth-quad destination of cv2.getPerspectiveTransform, in millimetres.

    Portrait (default) is the canonical frame: [[0,0],[W,0],[W,H],[0,H]] with
    W x H = CANON_W x CANON_H, the orientation of the camera view. landscape=True
    is the transposed reading of the same table (LANDSCAPE_W x LANDSCAPE_H).

    These are the full-extent corners. homography_to_canonical() keeps its own
    1 mm/pixel inset ring instead; that inset is load bearing and unchanged.
    """
    import numpy as np

    w, h = (LANDSCAPE_W, LANDSCAPE_H) if landscape else (CANON_W, CANON_H)
    return np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)


def canonical_pockets() -> np.ndarray:
    """POCKETS_MM as a float32 (6, 2) array, in the POCKETS_MM order."""
    import numpy as np

    return np.array(list(POCKETS_MM.values()), dtype=np.float32)


def nearest_pocket(x_mm: float, y_mm: float) -> tuple[str, float]:
    """Return the closest pocket name and the distance in millimetres."""
    name, best = None, float("inf")
    for pocket, (px, py) in POCKETS_MM.items():
        distance = math.hypot(x_mm - px, y_mm - py)
        if distance < best:
            name, best = pocket, distance
    return name, best


def homography_to_canonical(corners: np.ndarray) -> np.ndarray:
    """Map the cloth quad [TL, TR, BR, BL] to the canonical table.

    The canonical frame is width x length = CANON_W x CANON_H, oriented like
    the camera view: head rail at the top, foot rail at the bottom, left long
    rail on the left.  TL -> (0,0) [head-left], TR -> (W,0) [head-right],
    BR -> (W,H) [foot-right], BL -> (0,H) [foot-left].  The long rails run
    vertically (x=0 and x=W) and the side pockets sit at their midpoints.
    """
    import cv2
    import numpy as np

    dst = np.array(
        [[0, 0], [CANON_W - 1, 0], [CANON_W - 1, CANON_H - 1], [0, CANON_H - 1]],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(corners.astype(np.float32), dst)
