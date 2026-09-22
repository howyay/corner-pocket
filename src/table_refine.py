"""Cloth-boundary detection with a static-camera prior and local refinement.

The naive path in :mod:`src.table_detect` segments blue cloth by hue, takes the
largest component and fits ``approxPolyDP`` to it.  At 720p the carpet, the rail
shadow and passers-by share the cloth hue, so that quad is unusable (measured
72.8 px median / 145 px p90 mean corner error on vod30, 2.3% inside the app's
40 px tolerance).

This module keeps the same dict contract and adds the missing pieces:

* a **prior** for the segment (a saved reference quad, or the previous accepted
  frame - the camera is static),
* **local refinement**: each side is searched perpendicular to itself inside a
  narrow band for the place where the cloth region ends.  The evidence is the
  adaptive-hue cloth mask (interior holes from balls or shadow do not matter,
  because only the outermost mask transition counts) and, where the mask
  retracts, the strongest dark-rail -> bright-cloth intensity ramp.  A side moves
  to the median of its samples, so a player body crossing one rail is outvoted
  instead of dragging the line,
* **honest failure**: when the samples disagree the call reports
  ``confidence``/``reason`` and returns no corners instead of a confident wrong
  quad.

The prior is only ever a search centre: nothing is returned unless the frame
itself supports it inside the band.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

_BAND_PX = 34.0          # half-width of the perpendicular search around a side
_ITERS = 2
_N_SAMPLES = 17
_MIN_SAMPLES = 9         # samples needed before a side is believed
_MAX_SIDE_MAD = 2.5      # px: sample spread around the side's own offset
_MAX_MOVE_PX = 8.0       # px: a side may not teleport in one iteration
_MIN_CONTRAST = 18.0     # gray levels for the intensity fallback

_DATASET_PRIOR = {
    # Saved static-camera references, each with the reason it may serve as a
    # search centre.  A prior is never returned as the answer on its own.
    "vod30": {"file": "corners_30min_v2.json", "key": "corners",
              "note": "300-frame temporal median of strip-refined vod30 quads "
                      "(163/300 accepted, 3.95 px median jitter)"},
    "highlight": {"file": "fixed_corners.json", "key": "corners",
                  "note": "highlight reference (docs/state.md: 2.0 px median vs the cloth quad)"},
}


# --------------------------------------------------------------------------
# priors
# --------------------------------------------------------------------------

def prior_for(dataset: str, t: float | None = None, root=None):
    """Saved reference quad for a dataset, or None when there is none.

    ``t`` is accepted so a future per-segment prior table can key on it; both
    datasets here are single static segments.  ``root`` overrides where the
    reference is read from, so a caller that is pointed at its own tree (a test
    fixture, another checkout) never picks up this one's artifacts: it either
    finds its own ``out/`` copy or gets None and falls back to the naive quad.
    """
    spec = _DATASET_PRIOR.get(str(dataset))
    if not spec:
        return None
    path = Path(root) / "out" / spec["file"] if root is not None else ROOT / "out" / spec["file"]
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        pts = np.asarray(data[spec["key"]], np.float32).reshape(4, 2)
    except Exception:
        return None
    from src.table_detect import _order_corners
    return _order_corners(pts)


def load_priors() -> dict:
    """Every saved prior the harness can use, with provenance."""
    out = {}
    for dataset, spec in _DATASET_PRIOR.items():
        q = prior_for(dataset)
        out[dataset] = {"quad": None if q is None else np.asarray(q, float).round(1).tolist(),
                        "source": spec["file"], "note": spec["note"]}
    return out


# --------------------------------------------------------------------------
# per-side evidence
# --------------------------------------------------------------------------

def _mask_candidates(frame, prior):
    """Cloth-mask candidates, ordered, each with a cheap scoring probe.

    The stock masks keep the *largest* blue component, which on this footage is
    regularly the carpet or a wall panel: a player in the centre band moves the hue
    anchor, and then "largest" is off-table.

    Cost is what makes this tricky.  Building and labelling a full-resolution mask
    costs ~200 ms at 1080p, and rebuilding the hue conversion for every variant
    triples that.  So every candidate here is a *spec*: it names the mask and the
    cleanup it needs, carries a 4x-downsampled probe for scoring, and materialises
    the full mask only when it is chosen.  One HSV conversion serves the whole
    frame.  Returns a list of ``{name, rank, probe_small, build()}``.
    """
    import cv2

    from src.quad_fit import _anchor_hue
    from src.table_detect import detect_cloth_mask

    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    prior = np.asarray(prior, np.float64)
    centre = prior.mean(axis=0)
    seeds = [tuple(np.rint(centre).astype(int))]
    for q in prior:                      # the bed near each corner is usually cloth
        seeds.append(tuple(np.rint(q + (centre - q) * 0.16).astype(int)))
    seeds = [(int(np.clip(x, 0, w - 1)), int(np.clip(y, 0, h - 1))) for x, y in seeds]

    # The probe is computed on a half-resolution BGR frame (one cvtColor, not a
    # resize of the hue channel: hue is circular, so resampling it wraps reds into
    # blues and the thresholds stop meaning what they say).
    small_frame = cv2.resize(frame, (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)
    hsv_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2HSV)

    out = []

    def add_spec(name, rank, hwin, smin, vmin, close, open_k, thin=False):
        """Register one threshold spec with a cheap 4x probe."""

        def probe():
            if hwin is None:                      # the stock broad mask
                lo, hi = (80, 60, 50), (130, 255, 255)
            else:
                hue = hue_of[0]
                lo, hi = (max(0, hue - hwin), smin, vmin), (min(179, hue + hwin), 255, 255)
            return cv2.inRange(hsv_small, lo, hi)

        build = _spec_builder(hsv, hwin, smin, vmin, close, open_k, hue_of, thin)
        if build is None:
            return
        out.append({"name": name, "rank": rank, "probe_small": probe(), "build": build})

        def seed_build(seed=seeds[0]):
            full = build()
            return None if full is None else _local_component(full, seed)

        for seed in seeds:
            out.append({"name": f"{name}@seed{seed[0]}_{seed[1]}", "rank": rank,
                        "probe_small": probe(), "build": seed_build})

    hue_of = [None]

    def _spec_builder(hsv_full, hwin, smin, vmin, close, open_k, hue_box, thin):
        def build():
            if hwin is None:
                raw = detect_cloth_mask(frame)
                return None if raw is None else (raw > 0).astype(np.uint8)
            hue = hue_box[0]
            lo = (max(0, hue - hwin), smin, vmin)
            hi = (min(179, hue + hwin), 255, 255)
            raw = cv2.inRange(hsv_full, lo, hi)
            if thin:
                return (raw > 0).astype(np.uint8)
            kc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close))
            ko = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
            raw = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, kc, iterations=2)
            raw = cv2.morphologyEx(raw, cv2.MORPH_OPEN, ko, iterations=1)
            return (raw > 0).astype(np.uint8)
        return build

    # The adaptive anchor needs the centre band, which is exactly what a player can
    # stand in, so the prior's own pixels get a vote too.
    anchor = _anchor_hue(frame)
    c = seeds[0]
    patch = hsv[max(0, c[1] - 50):c[1] + 51, max(0, c[0] - 70):c[0] + 71].reshape(-1, 3)
    sel = patch[(patch[:, 1] > 60)] if len(patch) else patch
    prior_hue = int(np.median(sel[:, 0])) if len(sel) else anchor
    hue_of[0] = anchor

    add_spec("stock_largest", 0, 16, 105, 55, 19, 9)
    add_spec("broad_hsv", 1, None, 60, 50, 15, 15)
    if abs(prior_hue - anchor) > 4:
        add_spec(f"prior_hue{prior_hue}+-14", 2, 14, 60, 40, 15, 9)
        add_spec(f"prior_hue{prior_hue}+-24", 3, 24, 60, 40, 15, 9)
    return out


def _local_component(mm, seed, pad=90, max_pixels=400000):
    """Component of ``mm`` containing ``seed``, flood-filled inside a crop.

    The crop is clipped to the seed's component bounding box (padded), so the
    walk stays cheap on 1080p frames and cannot leak into a neighbouring carpet
    region that happens to touch the crop border.
    """
    h, w = mm.shape[:2]
    x0, x1 = max(0, seed[0] - pad), min(w, seed[0] + pad)
    y0, y1 = max(0, seed[1] - pad), min(h, seed[1] + pad)
    crop = np.ascontiguousarray(mm[y0:y1, x0:x1])
    if crop.size == 0 or crop[seed[1] - y0, seed[0] - x0] == 0:
        return None
    mask = np.zeros((crop.shape[0] + 2, crop.shape[1] + 2), np.uint8)
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE
    cv2.floodFill(crop.copy(), mask, (seed[0] - x0, seed[1] - y0), 1, 0, 0, flags)
    comp = np.zeros((h, w), np.uint8)
    comp[y0:y1, x0:x1] = mask[1:-1, 1:-1]
    if int(comp.sum()) > max_pixels:
        return None
    return comp


def _components_at(mm, seeds, max_keep=3):
    """Largest components of ``mm``, plus a flood-fill component per seed."""
    out = []
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mm)
    if n < 2:
        return out
    order = np.argsort(-stats[1:, cv2.CC_STAT_AREA])[:max_keep]
    for rank, idx in enumerate(order):
        comp = (lab == idx + 1).astype(np.uint8)
        out.append((comp, f"largest{rank + 1}"))
    for seed in seeds:
        x, y = int(np.clip(seed[0], 0, mm.shape[1] - 1)), int(np.clip(seed[1], 0, mm.shape[0] - 1))
        if lab[y, x] == 0:
            continue
        comp = (lab == lab[y, x]).astype(np.uint8)
        out.append((comp, f"seed{x}_{y}"))
    return out


def _side_normal(a, b, centre):
    nv = np.asarray(a, float) - np.asarray(b, float)
    nlen = float(np.hypot(*nv))
    if nlen < 8.0:
        return None
    nrm = np.array([-nv[1], nv[0]]) / nlen
    if np.dot(nrm, (np.asarray(a, float) + np.asarray(b, float)) / 2.0 - centre) < 0:
        nrm = -nrm
    return nrm


def _sample_grid(a, b, nrm, h, w, band, step, n):
    """Unit-coordinate sampling grid for one side.

    Returns ``(ts, xs, ys, ok)`` where ``xs``/``ys`` are (len(ts), n) integer
    pixel coordinates and ``ok`` marks the samples inside the frame.  Sampling
    vectorized here is what keeps the refinement cheap: the earlier per-sample
    loops cost ~120k numpy reductions per frame.
    """
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    nrm = np.asarray(nrm, float)
    ts = np.arange(-band, band + 0.5, step)
    fracs = np.linspace(0.08, 0.92, n)
    p0 = a[None, :] + (b - a)[None, :] * fracs[:, None]      # (n, 2)
    xs = np.rint(p0[:, 0][None, :] + nrm[0] * ts[:, None]).astype(int)
    ys = np.rint(p0[:, 1][None, :] + nrm[1] * ts[:, None]).astype(int)
    ok = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    return ts, xs, ys, ok


def _side_evidence(gray, mm, a, b, nrm, band=_BAND_PX, bounds=None):
    """Sample one side: per scan line, where does the cloth end?

    Offsets are perpendicular distances from the prior line (+ = outward).  The
    mask transition wins when present (it *is* the cloth boundary); the
    intensity ramp is the fallback where the mask has retracted.
    """
    h, w = bounds if bounds is not None else gray.shape[:2]
    ts, xs, ys, ok = _sample_grid(a, b, nrm, h, w, band, 0.5, _N_SAMPLES)
    if int(ok.sum()) < 8:
        return np.empty(0), np.empty(0), []
    on = np.zeros(xs.shape, bool)
    on[ok] = mm[ys[ok], xs[ok]] > 0
    offsets, rises, kinds = [], [], []
    n_t = len(ts)
    for j in range(xs.shape[1]):
        okj = ok[:, j]
        if okj.sum() < 8:
            continue
        idx = np.where(on[:, j])[0]
        if len(idx):
            i = int(idx[np.argmax(ts[idx])])          # outermost 'on' sample
            offsets.append(float(ts[i]) + (0.25 if i + 1 < n_t else 0.0))
            kinds.append("mask")
            continue
        gh, gw = gray.shape[:2]
        gy = np.clip(ys[:, j], 0, gh - 1)
        gx = np.clip(xs[:, j], 0, gw - 1)
        col = gray[gy, gx].astype(np.float32)
        valid = np.where(okj)[0]
        if valid[-1] - valid[0] < 9:
            continue
        grad = np.abs(np.diff(col))
        grad[~okj[1:]] = 0.0
        i = int(np.argmax(grad[valid[0] + 1:valid[-1]])) + valid[0] + 1
        step = float(grad[i - 1])
        prev = col[max(0, i - 3):i]
        after = col[i + 1:i + 6]
        if step < _MIN_CONTRAST or len(prev) < 2 or len(after) < 2:
            continue
        offsets.append(float(ts[i]))
        rises.append(step)
        kinds.append("edge")
    return np.asarray(offsets, float), np.asarray(rises, float), kinds


def _robust_offset(offsets):
    """Median offset plus the MAD after a 2.5 px inlier window."""
    if len(offsets) == 0:
        return None, None, 0
    med = float(np.median(offsets))
    mad = float(np.median(np.abs(offsets - med)) * 1.4826)
    inl = offsets[np.abs(offsets - med) <= max(2.0, 2.5 * mad)]
    if len(inl) < 3:
        return med, mad, int(len(inl))
    med2 = float(np.median(inl))
    mad2 = float(np.median(np.abs(inl - med2)) * 1.4826)
    return med2, mad2, int(len(inl))


def _integral(mm):
    """Summed-area table of the binary mask (zero-padded), for O(1) 3x3 means."""
    return cv2.integral((mm > 0).astype(np.uint8))


def _pick_mask(cands, prior, band=_BAND_PX, floor=0.5):
    """Build the first candidate that covers the prior bed, in preference order.

    The stock adaptive mask is the boundary this detector was calibrated on, so it
    is tried first; the later candidates exist so a frame where the stock mask
    locked onto the carpet can still be measured.  Candidates are *ranked* on
    2x-downsampled probes (selection only needs to tell a cloth-covered bed from an
    off-table mask) and only the winner is materialised at full resolution, which
    is why a frame costs one mask build in the common case.  A mask whose bed
    occupancy is below the floor describes something other than this table and is
    never allowed to place the boundary.  Returns (mask, note).
    """
    prior = np.asarray(prior, np.float64)
    prior_bed_small = _inset(prior, 12.0) * 0.5
    prior_small = prior * 0.5
    tried = []
    for cand in sorted(cands, key=lambda c: c["rank"]):
        probe = cand.get("probe_small")
        if probe is None and cand.get("lazy"):
            built = cand["build"]()
            if built is None:
                continue
            hh, ww = built.shape[:2]
            probe = cv2.resize((built > 0).astype(np.uint8) * 255, (max(1, ww // 2), max(1, hh // 2)),
                               interpolation=cv2.INTER_NEAREST)
        if probe is None:
            continue
        bed = _quad_occupancy(probe, prior_bed_small)
        cover = _quad_occupancy(probe, prior_small)
        tried.append({"candidate": cand["name"], "bed": round(float(bed), 2),
                      "cover": round(float(cover), 2), "rank": cand["rank"]})
        if bed >= floor:
            mask = cand["build"]()
            if mask is None:
                continue
            return (mask > 0).astype(np.uint8), f"{cand['name']} bed={bed:.2f} cover={cover:.2f}"
    return None, "no_candidate"


def _inset(quad, px):
    """Shrink a quad towards its centroid by ``px`` (the cloth bed, minus rails)."""
    quad = np.asarray(quad, np.float64)
    centre = quad.mean(axis=0)
    out = []
    for p in quad:
        v = centre - p
        n = float(np.linalg.norm(v))
        out.append(p + v / n * px if n > 1e-6 else p)
    return np.asarray(out)


def _quad_occupancy(mm, quad, n=24):
    """Fraction of mask pixels inside the prior quad (sampled on a grid)."""
    h, w = mm.shape[:2]
    quad = np.asarray(quad, np.float64)
    xs = np.linspace(quad[:, 0].min(), quad[:, 0].max(), int(n * 2))
    ys = np.linspace(quad[:, 1].min(), quad[:, 1].max(), n)
    X, Y = np.meshgrid(xs, ys)
    # Convex quad: inside == every edge cross-product shares one sign.
    cross = np.stack([(quad[(i + 1) % 4][0] - quad[i][0]) * (Y - quad[i][1])
                      - (quad[(i + 1) % 4][1] - quad[i][1]) * (X - quad[i][0])
                      for i in range(4)])
    inside = (cross >= 0).all(axis=0) | (cross <= 0).all(axis=0)
    if not inside.any():
        return 0.0
    xi = np.clip(X[inside].astype(int), 0, w - 1)
    yi = np.clip(Y[inside].astype(int), 0, h - 1)
    return float((mm[yi, xi] > 0).mean())


def _band_peaks(mm, prior, band):
    """Mean over sides of the maximum in-band occupancy (mask presence check)."""
    peaks = []
    integral = _integral(mm)
    for s in range(4):
        a, b = prior[s], prior[(s + 1) % 4]
        nrm = _side_normal(a, b, prior.mean(axis=0))
        if nrm is None:
            continue
        ts, occ = _side_occupancy(mm, a, b, nrm, band=band, integral=integral)
        if np.isfinite(occ).any():
            peaks.append(float(np.nanmax(occ)))
    return float(np.mean(peaks)) if peaks else 0.0


def _side_occupancy(mm, a, b, nrm, band=_BAND_PX, step=0.5, n=12, integral=None):
    """Occupancy profile across one side: mean cloth-mask coverage inside a 3x3
    patch at every offset in the band.  Returns (offsets, occupancy).

    Averaging along the whole side is what makes this robust to a single player
    arm or a ball: the crossing still shows up in the mean curve.  The integral
    image keeps this O(1) per sample instead of a per-sample patch mean.
    """
    h, w = mm.shape[:2]
    ts, xs, ys, ok = _sample_grid(a, b, nrm, h, w, band, step, n)
    occ = np.full(ts.shape, np.nan)
    valid = ok.all(axis=1)
    if not valid.any():
        return ts, occ
    ii = _integral(mm) if integral is None else integral
    xv, yv = xs[valid], ys[valid]
    x0, y0 = (xv - 1).clip(0), (yv - 1).clip(0)
    x1, y1 = (xv + 2).clip(0, w), (yv + 2).clip(0, h)
    s = (ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]).astype(np.float64)
    area = ((x1 - x0) * (y1 - y0)).astype(np.float64)
    occ[valid] = (s / np.maximum(area, 1.0)).mean(axis=1)
    return ts, occ


def _occupancy_crossing(ts, occ, thresh=0.5):
    """Signed offset where the mean occupancy falls through ``thresh`` walking
    from inside (positive occupancy) outwards; None when the curve never gets
    there or never leaves."""
    valid = np.isfinite(occ)
    if valid.sum() < 8:
        return None
    tsv, occv = ts[valid], occ[valid]
    if occv.max() < max(thresh + 0.15, 0.6) or occv.min() > thresh - 0.15:
        return None
    # iterate from the inside end outwards, take the first crossing
    for i in range(len(occv) - 1):
        if occv[i] >= thresh > occv[i + 1]:
            span = occv[i] - occv[i + 1]
            f = 0.0 if span <= 1e-6 else (occv[i] - thresh) / span
            return float(tsv[i] + f * (tsv[i + 1] - tsv[i]))
    return None


def _band_quality(ts, occ):
    """max occupancy (is the cloth there at all?) and the 10-90 % width."""
    valid = np.isfinite(occ)
    if valid.sum() < 8:
        return None, None
    occv, tsv = occ[valid], ts[valid]
    hi, lo = float(occv.max()), float(occv.min())
    span = hi - lo
    width = None
    if span > 1e-6:
        def cross(level):
            for i in range(len(occv) - 1):
                if (occv[i] - level) * (occv[i + 1] - level) < 0:
                    f = (occv[i] - level) / (occv[i] - occv[i + 1])
                    return float(tsv[i] + f * (tsv[i + 1] - tsv[i]))
            return None
        a10, a90 = cross(lo + 0.1 * span), cross(lo + 0.9 * span)
        if a10 is not None and a90 is not None:
            width = abs(a10 - a90)
    return hi, width


# --------------------------------------------------------------------------
# refinement
# --------------------------------------------------------------------------

def _shift_side(quad, s, offset):
    nrm = _side_normal(quad[s], quad[(s + 1) % 4], quad.mean(axis=0))
    if nrm is None:
        return
    quad[s] = quad[s] + nrm * offset
    quad[(s + 1) % 4] = quad[(s + 1) % 4] + nrm * offset


def refine_quad_edges(frame, prior, band_px=_BAND_PX, iters=_ITERS):
    """Refine ``prior`` against frame evidence; return ``(quad, info)``.

    Each iteration measures, per side, the mask-occupancy crossing plus the
    per-scan-line offsets, and moves the side to the consensus.  The result is
    accepted only when every side clears the evidence floors; otherwise
    ``quad`` is None and ``reason`` says what was missing.
    """
    from src.table_detect import _order_corners
    prior = _order_corners(np.asarray(prior, np.float32))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    cands = _mask_candidates(frame, prior)
    if not cands:
        return None, {"confidence": 0.0, "reason": "low_cloth_area", "mask": "no_candidate"}
    mm, mask_note = _pick_mask(cands, prior)
    if mm is None:
        return None, {"confidence": 0.0, "reason": "low_cloth_area",
                      "mask": "no_candidate_covers_prior",
                      "candidates": [c["name"] for c in cands]}
    # The boundary is measured on a 2x-downsampled mask: the mask edge spans
    # several pixels, so halving it costs no measurable accuracy while keeping the
    # per-side profiles (the hot loop) four times cheaper on 1080p frames.
    mask_scale = 0.5
    mm_small = cv2.resize(mm * 255, (max(1, mm.shape[1] // 2), max(1, mm.shape[0] // 2)),
                          interpolation=cv2.INTER_NEAREST)
    integral = _integral(mm_small)
    quad = prior.astype(np.float64).copy()
    side_reports, movements = [], []
    it = 0
    for it in range(max(1, iters)):
        reports = []
        for s in range(4):
            a, b = quad[s], quad[(s + 1) % 4]
            nrm = _side_normal(a, b, quad.mean(axis=0))
            if nrm is None:
                return None, {"confidence": 0.0, "reason": "degenerate_prior", "mask": mask_note}
            a_s, b_s = np.asarray(a) * mask_scale, np.asarray(b) * mask_scale
            # Bounds come from the downsampled mask, not from the full frame: the
            # two differ by the mask scale, and sampling with the frame's shape is
            # exactly how an out-of-bounds index got through before.
            mh, mw = mm_small.shape[:2]
            offsets, rises, kinds = _side_evidence(gray, mm_small, a_s, b_s, nrm,
                                                  band=band_px * mask_scale, bounds=(mh, mw))
            ts, occ = _side_occupancy(mm_small, a_s, b_s, nrm, band=band_px * mask_scale,
                                      integral=integral)
            crossing = _occupancy_crossing(ts, occ)
            peak, width = _band_quality(ts, occ)
            med, mad, n_in = _robust_offset(offsets)
            reports.append({"side": s, "n": int(len(offsets)), "n_inliers": n_in,
                            "mask_offset_px": None if crossing is None else round(crossing, 2),
                            "mask_band_peak": None if peak is None else round(peak, 2),
                            "mask_band_width_px": None if width is None else round(width, 2),
                            "scan_offset_px": None if med is None else round(med, 2),
                            "scan_mad_px": None if mad is None else round(mad, 2),
                            "kinds": {k: kinds.count(k) for k in sorted(set(kinds))},
                            "rise_median": round(float(np.median(rises)) if len(rises) else 0.0, 1)})
        # Which offsets are defensible?  The occupancy crossing is a per-side
        # measurement, so a player crossing one rail is outvoted.  A side with no
        # evidence is NOT a refusal: it stays where the prior put it, the move is
        # logged, and the frame's confidence drops.  That is the partial-occlusion
        # case - the other three rails still measure the boundary, and refusing
        # the frame would throw that away.
        chosen, held = {}, []
        for r in reports:
            cross = r["mask_offset_px"]
            if cross is not None and (r["mask_band_peak"] or 0) >= 0.6:
                chosen[r["side"]] = cross * mask_scale
                continue
            if r["scan_offset_px"] is not None and r["n_inliers"] >= 7 and (r["scan_mad_px"] or 99) <= 6.0:
                chosen[r["side"]] = r["scan_offset_px"] * mask_scale
                continue
            held.append({"side": r["side"], "reason": ("low_cloth_area"
                         if (r["mask_band_peak"] or 0) < 0.4 else "no_boundary_evidence"),
                         "peak": r["mask_band_peak"]})
            chosen[r["side"]] = 0.0
        if len(held) == 4:
            return None, {"confidence": 0.0, "reason": "low_cloth_area", "mask": mask_note,
                          "iteration": it, "sides": reports,
                          "held_sides": held,
                          "candidates": [c["name"] for c in cands]}
        moved = np.array([chosen[s] for s in range(4)], float)
        live = np.array([s for s in range(4) if not any(h["side"] == s for h in held)])
        if len(live) >= 2 and float(np.median(np.abs(moved[live] - np.median(moved[live])))) > 45.0:
            return None, {"confidence": 0.0, "reason": "prior_disagreement", "mask": mask_note,
                          "iteration": it, "sides": reports, "held_sides": held}
        for s in range(4):
            # ``chosen`` is in downsampled-mask units: back to full-res pixels.
            # A side may only move a bounded amount per iteration: an unbounded
            # step lets one rail (the 1080p bottom rail, whose cloth rolls into a
            # shadow band) swallow the frame's dark edge.  The cap also keeps the
            # refined quad inside the segment prior's neighbourhood.
            _shift_side(quad, s, float(np.clip(chosen[s], -_MAX_MOVE_PX, _MAX_MOVE_PX)) / mask_scale)
        movements.append(round(float(np.mean([abs(moved[s]) for s in range(4)])), 2))
        side_reports = reports
        all_held = held
        if max(abs(moved[s]) for s in range(4)) < 0.75:
            break
    quad = _order_corners(quad.astype(np.float32))
    ok, why = _plausible(quad, prior, frame.shape[1], frame.shape[0])
    if not ok:
        return None, {"confidence": 0.0, "reason": why, "mask": mask_note,
                      "iteration": it, "sides": side_reports}
    # Confidence: the weakest side caps it (a quad is only as trustworthy as its
    # worst edge), with the typical edge width and per-scan-line spread as the
    # other two components.  Refusals are the gates above; this number only says
    # how comfortable the accepted quad is.
    peaks = [r["mask_band_peak"] if r["mask_band_peak"] is not None else 0.45 for r in side_reports]
    widths = [r["mask_band_width_px"] for r in side_reports if r["mask_band_width_px"] is not None]
    spreads = [r["scan_mad_px"] for r in side_reports if r["scan_mad_px"] is not None]

    def _unit(v, lo, hi):
        return max(0.0, min(1.0, (v - lo) / (hi - lo)))

    comp_peak = _unit(float(np.min(peaks)), 0.6, 0.9)
    comp_width = 1.0 - _unit(float(np.median(widths)) if widths else 25.0, 8.0, 30.0)
    comp_spread = 1.0 - _unit(float(np.median(spreads)) if spreads else 8.0, 4.0, 14.0)
    measured = (4 - len(all_held)) / 4.0
    confidence = round(measured * (0.40 * comp_peak + 0.30 * comp_width + 0.30 * comp_spread), 3)
    info = {"confidence": confidence, "reason": None, "mask": mask_note,
            "iterations": len(movements), "side_moves_px": movements,
            "held_sides": all_held, "measured_sides": 4 - len(all_held),
            "side_peak_occupancy": round(float(np.min(peaks)), 2),
            "edge_width_px": round(float(np.median(widths)) if widths else -1.0, 2),
            "scan_mad_px": round(float(np.median(spreads)) if spreads else -1.0, 2),
            "move_px": round(float(np.linalg.norm(quad - prior, axis=1).mean()), 2),
            "sides": side_reports}
    return quad, info


def _shoelace(p):
    p = np.asarray(p, np.float64)
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def _plausible(quad, prior, w, h):
    """Sanity plus containment: a refined quad stays near its prior."""
    pts = np.asarray(quad, np.float64)
    prior = np.asarray(prior, np.float64)
    if not np.isfinite(pts).all():
        return False, "invalid_geometry"
    for x, y in pts:
        if x < 2 or y < 2 or x > w - 2 or y > h - 2:
            return False, "invalid_geometry"
    for i in range(4):
        if np.hypot(*(pts[i] - pts[(i + 1) % 4])) < 30:
            return False, "invalid_geometry"
    if float(np.linalg.norm(pts - prior, axis=1).mean()) > _BAND_PX * (_ITERS + 1):
        return False, "prior_disagreement"
    area_p, area_q = abs(_shoelace(prior)), abs(_shoelace(pts))
    if area_p <= 0 or not (0.6 <= area_q / area_p <= 1.7):
        return False, "prior_disagreement"
    if _shoelace(pts) * _shoelace(prior) < 0:
        return False, "invalid_geometry"
    return True, None


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------

def detect_table_refined(bgr, prior=None, prev_quad=None):
    """Drop-in replacement for ``detect_table`` with confidence reporting.

    ``corners``, ``mask`` and ``debug`` keep their meaning; ``corners`` is None
    whenever the boundary cannot be defended.  Added: ``confidence``,
    ``reason``, ``source``, ``refined``, ``prior``, ``used_prior``, ``debug_info``.

    ``prev_quad`` (the previous accepted frame) wins over ``prior``: on a static
    camera it is the tighter search centre.
    """
    from src.table_detect import detect_cloth_mask, detect_table

    naive = detect_table(bgr)
    result = dict(naive)
    result.update({"confidence": None, "reason": None, "source": "naive",
                   "refined": False, "prior": None, "used_prior": False,
                   "debug_info": {}, "naive_corners": naive["corners"]})
    centre = prev_quad if prev_quad is not None else prior
    centre_src = ("previous_frame" if prev_quad is not None
                  else ("saved_prior" if prior is not None else None))
    if centre is not None:
        centre = np.asarray(centre, np.float32)
        result["prior"] = np.asarray(centre, np.float32).round(1).tolist()
        quad, info = refine_quad_edges(bgr, centre)
        info["prior_source"] = centre_src
        result["debug_info"] = info
        if quad is not None:
            result.update({"corners": quad, "confidence": info["confidence"], "reason": None,
                           "source": f"refined_{centre_src}", "refined": True,
                           "used_prior": True, "mask": detect_cloth_mask(bgr)})
            result["debug"] = draw_debug(bgr, result)
            return result
        tried = [{"prior_source": centre_src, "info": info}]
        if naive["corners"] is not None:
            quad2, info2 = refine_quad_edges(bgr, naive["corners"])
            info2["prior_source"] = "naive"
            tried.append({"prior_source": "naive", "info": info2})
            if quad2 is not None:
                result.update({"corners": quad2, "confidence": info2["confidence"], "reason": None,
                               "source": "refined_naive", "refined": True,
                               "mask": detect_cloth_mask(bgr), "debug_info": info2})
                result["debug"] = draw_debug(bgr, result)
                return result
        result["corners"] = None
        result["confidence"] = 0.0
        result["reason"] = info.get("reason") or "no_boundary_evidence"
        result["debug_info"] = {"tried": tried}
        result["debug"] = draw_debug(bgr, result)
        return result

    if naive["corners"] is not None:
        result.update({"corners": naive["corners"], "confidence": 0.4,
                       "reason": "no_prior", "refined": False})
        return result
    result.update({"confidence": 0.0, "reason": "no_cloth_area", "corners": None})
    return result


def draw_debug(bgr, result):
    """Debug image: prior (orange), naive (magenta), kept quad (red)."""
    debug = bgr.copy()
    prior = result.get("prior")
    if prior is not None:
        cv2.polylines(debug, [np.asarray(prior, np.int32)], True, (0, 165, 255), 2)
    naive = result.get("naive_corners")
    if naive is not None:
        cv2.polylines(debug, [np.asarray(naive, np.int32)], True, (255, 0, 255), 2)
    corners = result.get("corners")
    if corners is not None:
        cv2.polylines(debug, [np.asarray(corners, np.int32)], True, (0, 0, 255), 3)
        for i, (x, y) in enumerate(corners):
            cv2.circle(debug, (int(x), int(y)), 7, (0, 255, 255), -1)
            cv2.putText(debug, str(i), (int(x) + 10, int(y) + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
    tag = f"{result.get('source')} conf={result.get('confidence')} {result.get('reason') or ''}"
    cv2.putText(debug, tag.strip(), (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return debug


if __name__ == "__main__":
    import sys
    frame = cv2.imread(sys.argv[1])
    prior = None
    if len(sys.argv) > 3:
        prior = json.loads(Path(sys.argv[3]).read_text())["corners"]
    res = detect_table_refined(frame, prior=prior)
    print({k: v for k, v in res.items() if k not in ("mask", "debug")})
