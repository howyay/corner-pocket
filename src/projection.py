"""The one owner of the homogeneous-division rule.

A projective map sends a point to ``(x, y, w)``, and the answer is ``(x / w,
y / w)``.  A point whose ``w`` is zero or tiny has no answer.  Before this
module the project stated that rule at eight sites, with two thresholds and two
answers.  Three of the eight sites divided unconditionally, so a ``nan`` or a
zero ``w`` produced a ``nan`` coordinate instead of a refusal:

    abs(nan) < 1e-9      is False     # the bare test lets nan through
    abs(1e-10) < 1e-9    is True      # the pixel group refuses this w
    abs(1e-10) < 1e-12   is False     # the mm group divides it

This module holds the predicate once.  Every reader calls :func:`project` and
holds no threshold of its own.

The two tolerances are one decision, measured on 2026-10-11:

* ``1e-12`` is the physical path, in canonical millimetres.  A ``w`` this small
  is below the precision of the geometry itself.  This value is the default,
  because a refusal is visible and a wrong ``nan`` coordinate is not.
* ``1e-9`` is the pixel path, where a ``w`` below it is far below the
  sub-pixel resolution of any served frame.

Both callers name the tolerance they rely on, so one reader can pass
``PIXEL_TOLERANCE`` and another ``DEFAULT_TOLERANCE`` without a second copy of
the rule.  Change a tolerance here, in one place, and the guard in
``tests/test_projection_guard.py`` fails until its pinned case changes too.
"""
from __future__ import annotations

import math

import numpy as np

#: The physical path, in canonical millimetres.  The default of :func:`project_point`.
DEFAULT_TOLERANCE = 1e-12
#: The pixel path, where a pixel is the smallest unit the answer carries.
PIXEL_TOLERANCE = 1e-9


def project_point(x, y, w, tolerance=DEFAULT_TOLERANCE):
    """``(x / w, y / w)``, or ``None`` when the point has no answer.

    ``None`` means one of these three things:

    * ``w`` is not a finite number, which includes ``nan``, ``inf`` and
      ``-inf``.  Only a finite ``w`` can divide;
    * ``abs(w) < tolerance``.  The point is at the horizon of the map, or the
      map is singular there;
    * ``x`` or ``y`` is not finite, so the division would produce no answer.

    The return value carries no ``nan`` coordinate.  A caller that needs a
    different point type uses :func:`as_array` or :func:`as_list`.
    """
    if not math.isfinite(w):
        return None
    if abs(w) < tolerance:
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return (float(x) / float(w), float(y) / float(w))


def as_array(point):
    """The owner's answer as an ``np.ndarray`` of ``float64``, or ``None``.

    ``np.asarray(None, np.float64)`` gives ``nan``, so every caller that wants
    an array must come through here.  An earlier ``abs(...) < 1e-9`` test made
    that mistake possible at the three bare sites.
    """
    if point is None:
        return None
    return np.asarray(point, np.float64)


def as_list(point):
    """The owner's answer as a new ``list`` of two floats, or ``None``."""
    if point is None:
        return None
    return [point[0], point[1]]
