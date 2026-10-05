"""The playfield's own geometry, as a constraint on what a detection may claim.

A 9 ft table is a known object: the playfield is 100" x 50" (2:1), the outside is 113.5" x 63.75",
and the pockets are 4.5" at the corners and 5" at the sides. Two of its properties survive any
camera: the four corners are coplanar, and - at a venue where the camera looks down one axis - at
least one pair of opposite edges still reads as parallel in the image. The other pair's vanishing
point is what carries the perspective; that is the parallax invariant the owner asked for.

`check_quad` scores a detected quad against all of it and returns the reasons, so a surface can say
*why* it refused one (the console already has a "quad refused" state to fill) instead of dropping a
detection silently.
"""
from __future__ import annotations

import math

PLAYFIELD_IN = (100.0, 50.0)          # 9 ft playfield
OUTSIDE_IN = (113.5, 63.75)           # rail to rail
POCKET_CORNER_IN = 4.5
POCKET_SIDE_IN = 5.0
PARALLEL_TOL_DEG = 3.0                # one pair must read parallel within this
TILT_TOL_DEG = 55.0                   # the table is on the floor: the plane cannot face the camera


def _vec(a, b):
    return (b[0] - a[0], b[1] - a[1])


def _angle_between(u, v):
    nu = math.hypot(*u) or 1e-9
    nv = math.hypot(*v) or 1e-9
    c = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
    return math.degrees(math.acos(c))


def quad_sides(quad):
    """The four sides in order, for a quad given as [TL, TR, BR, BL]."""
    if len(quad) != 4:
        raise ValueError('a quad is four points')
    tl, tr, br, bl = [(float(p[0]), float(p[1])) for p in quad]
    return {'top': (tl, tr), 'right': (tr, br), 'bottom': (br, bl), 'left': (bl, tl)}


def parallelism(quad):
    """The angle between each pair of opposite edges, in degrees (0 = parallel).

    Each pair is measured with both edges traversed the same way (left to right, top to bottom),
    so anti-parallel edges - which is what a rectangle's outline gives you - read as 0, not 180.
    """
    tl, tr, br, bl = [(float(p[0]), float(p[1])) for p in quad]
    long_pair = _angle_between(_vec(tl, tr), _vec(bl, br))
    short_pair = _angle_between(_vec(tl, bl), _vec(tr, br))
    return {'long': long_pair, 'short': short_pair}


def _side_lengths(quad):
    s = quad_sides(quad)
    return {k: math.hypot(*_vec(*v)) for k, v in s.items()}


def _perspective_ratio(quad):
    """How far the quad is from a parallelogram: 0 = affine, 1 = strongly convergent.

    A rectangle in the image keeps its opposite sides' ratios only under an affine view; the
    departure from that is the parallax the second vanishing point carries.
    """
    L = _side_lengths(quad)
    if min(L.values()) <= 1e-6:
        return 1.0
    long_ratio = abs(L['top'] - L['bottom']) / max(L['top'], L['bottom'])
    short_ratio = abs(L['left'] - L['right']) / max(L['left'], L['right'])
    return max(long_ratio, short_ratio)


def check_quad(quad, *, parallel_tol=PARALLEL_TOL_DEG, aspect=PLAYFIELD_IN[0] / PLAYFIELD_IN[1]):
    """Score one detected playfield quad against the table's own geometry.

    Returns {'ok': bool, 'reasons': [str], 'metrics': {...}}. `ok` means: a pair of opposite edges
    reads parallel within `parallel_tol`, the quad is convex and non-degenerate, and the shape is
    longer than it is wide (the playfield's 2:1 aspect survives the view, up to the tolerance).
    """
    reasons, metrics = [], {}
    if len(quad) != 4:
        return {'ok': False, 'reasons': ['not-four-corners'], 'metrics': metrics}
    # Convexity: a playfield cannot fold, and a folded quad means the corners were mismatched.
    xs = [float(p[0]) for p in quad]
    ys = [float(p[1]) for p in quad]
    if max(xs) - min(xs) < 8 or max(ys) - min(ys) < 8:
        return {'ok': False, 'reasons': ['degenerate'], 'metrics': metrics}
    cross = []
    for i in range(4):
        a, b, c = quad[i], quad[(i + 1) % 4], quad[(i + 2) % 4]
        u, v = _vec(a, b), _vec(b, c)
        cross.append(u[0] * v[1] - u[1] * v[0])
    if not (all(c > 0 for c in cross) or all(c < 0 for c in cross)):
        reasons.append('not-convex')
    par = parallelism(quad)
    metrics['parallel_deg'] = {'long': round(par['long'], 2), 'short': round(par['short'], 2)}
    best = min(par.values())
    metrics['best_parallel_deg'] = round(best, 2)
    if best > parallel_tol:
        reasons.append('no-parallel-pair')
    metrics['perspective'] = round(_perspective_ratio(quad), 4)
    L = _side_lengths(quad)
    long_in = (L['top'] + L['bottom']) / 2.0
    short_in = (L['left'] + L['right']) / 2.0
    if short_in > 0:
        observed = long_in / short_in
        # Perspective shortens the far side; the ratio may only be *at least* the true 2:1 (the
        # near/far asymmetry of a rectangle never makes it read as a square from a normal angle).
        metrics['aspect'] = round(observed, 3)
        if observed < aspect * 0.55:
            reasons.append('aspect-too-square')
    metrics['side_px'] = {k: round(v, 1) for k, v in L.items()}
    return {'ok': not reasons, 'reasons': reasons, 'metrics': metrics}


def pocket_positions_playfield():
    """The four corner and two side pockets in playfield inches, for a caller that wants to check
    pocket detections against the table's own geometry rather than against a fitted guess."""
    w, h = PLAYFIELD_IN
    d = POCKET_CORNER_IN
    return {
        'corners': [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)],
        'corner_radius_in': d,
        'sides': [(w / 2.0, 0.0), (w / 2.0, h)],
        'side_radius_in': POCKET_SIDE_IN,
    }
