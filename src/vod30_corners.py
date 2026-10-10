"""One owner for the hand-measured vod30 reference quad.

The quad is a hand-made input, not a pipeline output.  It lives in the tracked
file ``annotator/corners_30min.json``.  Five calibration tools read it, so the
path and the parser live here and nowhere else.  A test scans those five
readers and fails when a second hard-coded corner path appears in one of them.

The path resolves from the top of the repository, not from the working
directory of the caller.  Pass ``root`` to name a different repository top,
which a test uses to load the quad from a copy that has no ``out/`` directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# The tracked data file, relative to the top of the repository.
FILENAME = "corners_30min.json"
RELATIVE = Path("annotator") / FILENAME

# The array the readers expect: four corners, x and y in video pixels.
REF_DTYPE = np.float32
REF_SHAPE = (4, 2)


def reference_path(root=None) -> Path:
    """The absolute path of the tracked reference quad."""
    top = Path(__file__).resolve().parents[1] if root is None else Path(root)
    return top / RELATIVE


def load(root=None) -> np.ndarray:
    """The reference quad as a (4, 2) float32 array, in video pixels.

    The order is top-left, top-right, bottom-right, bottom-left.
    """
    path = reference_path(root)
    quad = np.asarray(json.loads(path.read_text())["corners"], dtype=REF_DTYPE)
    if quad.shape != REF_SHAPE:
        raise ValueError(f"{path} holds shape {quad.shape}, not {REF_SHAPE}")
    return quad
