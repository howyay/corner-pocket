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
_PEAK_FLOOR = 0.6        # band mask peak below which a side has no cloth evidence
_EDGE_MARGIN_PX = 1.5    # a crossing this close to the band edge is not a measurement
_SCAN_MIN_INLIERS = 7    # accepted scan-line samples needed for the ramp fallback
_SCAN_MAD_MAX = 6.0      # px: scan-line spread allowed for the ramp fallback
_CONVERGED_PX = 0.75     # px: stop iterating when no side moves more than this
_INHERIT_AGREE_PX = 3.0  # px: weak evidence this close to the prior may inherit it
_INHERIT_DIFFUSE_PX = 8.0  # px: a diffuse crossing this close may still inherit the prior
_INNER_FLOOR = 0.55      # cloth coverage just inside a crossing must reach this
_DROP_MIN = 0.20         # occupancy fall across a crossing must reach this
_RAIL_CONTRAST_MIN = 25.0  # gray levels: dark rail band then bright outside
_RAIL_BAND_PX = 26.0     # px: width of the rail strip sampled outside a crossing
_SIG_SCALE_NUM, _SIG_SCALE_DEN = 1, 4   # signature checks run at quarter resolution
_SIG_SCALE = _SIG_SCALE_NUM / _SIG_SCALE_DEN
_SIG_MIN_SEP = 1.5       # px at signature scale (== 6 px full resolution)
# Measured on vod30: the brightness-edge probe below agrees with the mask crossing
# on the head/foot rails (mad ~2 px) but scatters on the right/bottom rails where a
# player or the rail highlight dominates (mad 10-27 px), so it is reported as a
# diagnostic only and never verifies a side.

_DATASET_PRIOR = {
    # Each entry names a saved static-camera reference *and* how many of its points
    # are the cloth quad.  The prior is only a search centre, but a wrong centre is
    # not harmless: seeding vod30 from ``corners_30min_v2.json`` puts a vertical
    # left rail at x=450 while the cloth edge slants x=520 (y=330) -> x=381 (y=560),
    # so the refinement searched 70 px of carpet.  The six hand anchors (their first
    # four points are the cloth corners) track the same edge within 6-13 px, so they
    # are the seed.
    "vod30": {"file": "pid_anchors_vod30.json", "key": "anchors", "points": 4,
              "note": "first four of the six hand pocket anchors at t=70 "
                      "(measured within 6-13 px of the visible cloth edge); "
                      "corners_30min_v2.json is NOT used - its left rail is ~70 px "
                      "outside the cloth at the top and ~70 px inside at the bottom"},
    "highlight": {"file": "fixed_corners.json", "key": "corners", "points": 4,
                  "note": "highlight reference (docs/state.md: 2.0 px median vs the cloth quad)"},
}


def prior_for(dataset: str, t: float | None = None, root=None):
    """Saved reference quad for a dataset, or None when there is none.

    ``t`` selects the recorded anchor frame (vod30 anchors exist at t=70 only);
    ``root`` overrides where the reference is read from, so a caller pointed at its
    own tree (a test fixture, another checkout) never picks up this one's artifacts.

    When a measured segment artifact exists (``out/calib_<dataset>_segments.json``,
    see ``src/calib_segments``) it decides: calibration is per segment, and the
    segment that covers ``t`` owns the reference for it.  Without the artifact the
    saved prior below is used unchanged, so nothing that runs today changes.
    """
    from src import calib_segments

    segments = calib_segments.load(dataset, root=root)
    if segments is not None:
        seg = segments.resolve(t)
        if seg is not None:
            return _order(seg.quad)

    spec = _DATASET_PRIOR.get(str(dataset))
    if not spec:
        return None
    path = Path(root) / "out" / spec["file"] if root is not None else ROOT / "out" / spec["file"]
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        raw = data[spec["key"]]
        if spec["key"] == "anchors":              # {"anchors": {"70.0": [[x, y], ...]}}
            if not raw:
                return None
            key = None
            if t is not None:
                for candidate in (f"{float(t)}", f"{float(t):.1f}", str(int(t)) if float(t).is_integer() else None):
                    if candidate and candidate in raw:
                        key = candidate
                        break
            if key is None:
                key = sorted(raw, key=float)[0]
            raw = raw[key]
        pts = np.asarray(raw, np.float32).reshape(-1, 2)[:spec["points"]]
    except Exception:
        return None
    if pts.shape != (4, 2):
        return None
    return _order(pts)


def _order(pts):
    from src.table_detect import _order_corners
    return _order_corners(np.asarray(pts, np.float32))


def prior_provenance(dataset: str, t: float | None = None, root=None) -> dict:
    """Where ``prior_for`` got the reference: the segment, or the saved prior."""
    from src import calib_segments

    segments = calib_segments.load(dataset, root=root)
    if segments is not None:
        seg = segments.resolve(t)
        if seg is not None:
            return {"dataset": dataset, "kind": "segment", "id": seg.id,
                    "source": seg.source, "t_start": seg.t_start, "t_end": seg.t_end,
                    "clamped": seg.clamped, "clamp_reason": seg.clamp_reason,
                    "detail": seg.source_detail, "artifact": str(segments.path) if segments.path else None}
    spec = _DATASET_PRIOR.get(str(dataset))
    if not spec:
        return {"dataset": dataset, "kind": "none", "source": None}
    return {"dataset": dataset, "kind": "saved_prior", "id": None,
            "source": spec["file"], "detail": spec["note"]}


def load_priors() -> dict:
    """Every saved prior the harness can use, with provenance."""
    out = {}
    for dataset, spec in _DATASET_PRIOR.items():
        q = prior_for(dataset)
        prov = prior_provenance(dataset)
        out[dataset] = {"quad": None if q is None else np.asarray(q, float).round(1).tolist(),
                        "source": prov.get("source") if prov["kind"] == "segment" else spec["file"],
                        "kind": prov["kind"],
                        "note": prov.get("detail") if prov["kind"] == "segment" else spec["note"]}
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


def _side_evidence(gray, mm, a, b, nrm, band=_BAND_PX, bounds=None, mask_scale=1.0):
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
            edge = float(ts[i]) + (0.25 if i + 1 < n_t else 0.0)
            # A sample at the outer limit of the band means the cloth continues past
            # the search: clamp it inside, so a rail that was never reached is not
            # reported as sitting on the band edge.
            edge = min(edge, float(ts[-1]) - _EDGE_MARGIN_PX)
            offsets.append(max(edge, float(ts[0]) + _EDGE_MARGIN_PX))
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
        # ``ts`` is in mask units but the ramp was located on the full-res frame,
        # so the offset has to be expressed in mask units here: the caller converts
        # mask px -> real px exactly once.
        offsets.append(float(ts[i]) / mask_scale)
        rises.append(step)
        kinds.append("edge")
    return np.asarray(offsets, float), np.asarray(rises, float), kinds


def intensity_band_offset(gray, a, b, nrm, band_px, n=_N_SAMPLES, min_drop=25.0):
    """Independent evidence for one side: the strongest bright->dark intensity step.

    The cloth mask is hue-based, and on vod30 the carpet and the rail shadow share
    the cloth hue, so the mask crossing on the left rail is diffuse (coverage ramps
    from 0.5 to 1.0 over ~20 px) and cannot verify anything on its own.  Brightness
    does separate cloth from shadow, so this scans perpendicular to the side on the
    full-resolution gray frame and reports the median position of the sharpest
    sustained fall, plus how many scan lines agreed.

    Returns ``(offset_px, mad_px, n_lines)`` with offset in real pixels and
    ``(None, None, 0)`` when no line shows a step of at least ``min_drop``.
    """
    gray = np.asarray(gray, np.float32)
    h, w = gray.shape[:2]
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    nrm = np.asarray(nrm, float)
    ts = np.arange(-band_px, band_px + 0.5, 0.5)
    fracs = np.linspace(0.10, 0.90, n)
    p0 = a[None, :] + (b - a)[None, :] * fracs[:, None]
    xs = np.rint(p0[:, 0][None, :] + nrm[0] * ts[:, None]).astype(int)
    ys = np.rint(p0[:, 1][None, :] + nrm[1] * ts[:, None]).astype(int)
    ok = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    if ok.sum() < 12:
        return None, None, 0
    vals = np.full(xs.shape, np.nan, np.float32)
    vals[ok] = gray[ys[ok], xs[ok]]
    offs = []
    for j in range(xs.shape[1]):
        col, okj = vals[:, j], ok[:, j]
        valid = np.where(okj)[0]
        if len(valid) < 10:
            continue
        best_t, best_drop = None, min_drop
        for i in range(valid[0] + 2, valid[-1] - 3):
            if not (okj[i - 2:i + 1].all() and okj[i + 2:i + 6].all()):
                continue
            drop = float(col[i - 2:i + 1].mean() - col[i + 2:i + 6].mean())
            if drop > best_drop:
                best_drop, best_t = drop, float(ts[i])
        if best_t is not None:
            offs.append(best_t)
    if len(offs) < 8:
        return None, None, len(offs)
    offs = np.asarray(offs, float)
    med = float(np.median(offs))
    mad = float(np.median(np.abs(offs - med)) * 1.4826)
    inl = offs[np.abs(offs - med) <= max(3.0, 2.5 * mad)]
    if len(inl) >= 6:
        med = float(np.median(inl))
        mad = float(np.median(np.abs(inl - med)) * 1.4826)
    return med, mad, len(offs)


def rail_band_check(gray, a, b, nrm, offset_px, band_px, n=13, min_sep=6.0):
    """Is the thing just outside this crossing a pool-table rail?

    A cushion edge has a signature: cloth, then a *dark* band (the rail's shadowed
    nose), then the bright outside (carpet, floor, wall).  A crossing whose outside
    is a smooth dark field with no rail band at all is not the table boundary - it
    is a player's body, a shadow or an occluder that happens to sit on the cloth,
    which is the class of mistake this detector must not make.

    Returns ``(rail_dark, outside_bright, n)``: the darkest brightness of the band
    strip, the brightness further out, and how many scan lines voted.  ``None``
    when the geometry leaves the frame.
    """
    gray = np.asarray(gray, np.float32)
    h, w = gray.shape[:2]
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    nrm = np.asarray(nrm, float)
    # The rail is ~20-40 px wide at these resolutions, so the strip and the outside
    # sample have to sit that far beyond the crossing.  The previous version sampled
    # only ~10 px out, which is still cloth, so every crossing looked like it had no
    # rail - the check never fired in either direction.
    rail_px = max(4.0, band_px * (_RAIL_BAND_PX / _BAND_PX))
    t0 = max(min_sep, offset_px + min_sep / 2.0)
    near = t0 + rail_px
    far = near + rail_px
    mids = np.linspace(t0, near, 5)
    outs = np.linspace(near + 2.0, far + 2.0, 3)
    fracs = np.linspace(0.14, 0.86, n)
    darks, brights = [], []
    for frac in fracs:
        p0 = a + (b - a) * frac
        def sample(t):
            p = p0 + nrm * t
            x, y = int(round(p[0])), int(round(p[1]))
            return gray[y, x] if 0 <= x < w and 0 <= y < h else None
        band_vals = [sample(t) for t in mids]
        out_vals = [sample(t) for t in outs]
        band_vals = [v for v in band_vals if v is not None]
        out_vals = [v for v in out_vals if v is not None]
        if len(band_vals) >= 3 and len(out_vals) >= 2:
            darks.append(min(band_vals))
            brights.append(max(out_vals))
    if len(darks) < 6:
        return None, None, len(darks)
    import os
    if os.environ.get("RAIL_DEBUG"):
        print("RAIL_DEBUG offset", round(offset_px,2), "t0", round(t0,1), "near", round(near,1), "far", round(far,1),
              "dark", round(float(np.median(darks)),1), "out", round(float(np.median(brights)),1),
              "mids", [round(float(x),1) for x in mids], "outs", [round(float(x),1) for x in outs])
    return float(np.median(darks)), float(np.median(brights)), len(darks)


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
    """Where the mean occupancy falls through ``thresh``, walking from the inside.

    Returns ``None`` when the curve never gets there.  Also reports the occupancy
    just inside and just outside the crossing and the drop across it, because
    "the curve fell through 0.5" alone is not evidence of a boundary: a partial
    mask (a hole, an occluded rail) crosses 0.5 gently and in the wrong place,
    while a real cloth edge drops nearly a full unit in a couple of pixels.
    """
    valid = np.isfinite(occ)
    if valid.sum() < 8:
        return None
    tsv, occv = ts[valid], occ[valid]
    # Walk from the inside (the end that is covered) outwards.
    if occv[0] < occv[-1]:
        tsv, occv = tsv[::-1], occv[::-1]
    for i in range(len(occv) - 1):
        if occv[i] >= thresh > occv[i + 1]:
            span = occv[i] - occv[i + 1]
            f = 0.0 if span <= 1e-6 else (occv[i] - thresh) / span
            crossing = float(tsv[i] + f * (tsv[i + 1] - tsv[i]))
            inner = float(np.mean(occv[max(0, i - 3):i + 1]))
            outer = float(np.mean(occv[i + 1:min(len(occv), i + 5)]))
            return {"crossing_px": crossing, "inner": inner, "outer": outer,
                    "drop": inner - outer}
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


def refine_quad_edges(frame, prior, band_px=_BAND_PX, iters=_ITERS, band_scales=(1.0, 2.0, 3.0)):
    """Refine ``prior`` against frame evidence; return ``(quad, info)``.

    The search band widens across ``band_scales`` passes: a rail whose boundary
    sits outside the narrow band is not measurable at that width, and refusing the
    frame there would be a coverage loss, not honesty.  Widening keeps the rule
    intact - every pass still requires in-band evidence with the band-edge
    rejection - so a side that is unverified at 3x the band is genuinely
    unmeasurable and the frame is refused.
    """
    last = None
    for scale in band_scales:
        quad, info = _refine_once(frame, prior, band_px=band_px * scale, iters=iters)
        info["band_scale"] = scale
        if quad is not None or scale == band_scales[-1]:
            return quad, info
        last = info
        # Widening is only a *search* fallback for a prior that found nothing.  A
        # prior that verified a strict subset of its sides is self-contradictory
        # (part of the frame agrees with it, part does not): widening that one
        # would let the agreeing rails pull the others far past the boundary, which
        # is exactly the confident-wrong-quad case.  Those refuse as they are.
        verified = info.get("verified_sides", 0)
        if verified:
            return None, info
    return None, last or {"confidence": 0.0, "reason": "no_boundary_evidence"}


def _refine_once(frame, prior, band_px=_BAND_PX, iters=_ITERS):
    """One refinement pass at a fixed band width.

    Each iteration measures, per side, the mask-occupancy crossing plus the
    per-scan-line offsets, and moves the side to the consensus.

    Verification rule (a side is *verified* only when the frame shows its
    boundary inside the search band):

    * the occupancy crossing exists AND the band's mask peak is >= ``_PEAK_FLOOR``
      AND the crossing sits at least ``_EDGE_MARGIN_PX`` inside the band edge -
      a crossing *at* the band edge means the search never reached a boundary and
      the side is merely following the prior, not measuring it; or
    * the per-scan-line consensus has >= 7 inliers with MAD <= ``_SCAN_MAD_MAX``
      (the intensity ramp, used where the mask retracts).

    If ANY side fails, no corners are returned: ``quad`` is None, ``reason`` is
    ``low_cloth_area`` / ``no_boundary_evidence`` / ``prior_disagreement``, and
    ``unverified_sides`` carries the per-side code.  A side kept at its prior
    position is not a verified measurement, so it can never be reported as a
    confident quad - that is the failure class this project deletes from the UI.
    """
    from src.table_detect import _order_corners
    prior = _order_corners(np.asarray(prior, np.float32))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    # Signature checks run on a quarter-resolution gray image (measured ~4x cheaper
    # than the full one and still resolving a 26 px rail band).
    gray_small = cv2.resize(gray, (max(1, gray.shape[1] * _SIG_SCALE_NUM // _SIG_SCALE_DEN),
                                   max(1, gray.shape[0] * _SIG_SCALE_NUM // _SIG_SCALE_DEN)),
                            interpolation=cv2.INTER_AREA)
    cands = _mask_candidates(frame, prior)
    if not cands:
        return None, {"confidence": 0.0, "reason": "low_cloth_area", "mask": "no_candidate"}
    mm, mask_note = _pick_mask(cands, prior)
    if mm is None:
        return None, {"confidence": 0.0, "reason": "low_cloth_area",
                      "mask": "no_candidate_covers_prior",
                      "candidates": [c["name"] for c in cands]}
    # The boundary is measured on a half-resolution mask (one resize, and the mask
    # edge spans several pixels so the halving is invisible), but the step that
    # moves a side is applied in real pixels: the old code divided by the scale
    # instead of multiplying, so an iteration advanced only half the offset it had
    # just measured.  ``mask_scale`` is applied exactly once, at each measured
    # offset, and offset units are documented at every producer.
    # The boundary is measured on the FULL-resolution mask.  Half resolution is
    # cheaper, but the resample moves the mask edge by ~1.5 px, and that shows up as
    # a constant offset between what the detector measures and what it writes (the
    # 1.011 applied/reported ratio the verifier caught, and the residual of a
    # one-iteration step).  Full resolution removes the bias; the occupancy profile
    # is O(1) per sample through the integral image, so the cost is bounded.
    mask_scale = 1.0
    band_mask = band_px * mask_scale
    mm_small = mm
    integral = _integral(mm)
    quad = prior.astype(np.float64).copy()
    side_reports, side_state, movements = [], {}, []
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
                                                   band=band_mask, bounds=(mh, mw),
                                                   mask_scale=mask_scale)
            ts, occ = _side_occupancy(mm_small, a_s, b_s, nrm, band=band_mask, integral=integral)
            crossing_info = _occupancy_crossing(ts, occ)
            crossing = None if crossing_info is None else crossing_info["crossing_px"]
            rail_dark, rail_out, rail_n = (None, None, 0)
            if crossing is not None:
                # The rail band is ~26 px wide and the outside sample sits ~80 px
                # out, so a quarter-resolution gray image resolves it fine and keeps
                # this off the profile of the frame.
                rail_dark, rail_out, rail_n = rail_band_check(
                    gray_small, a * _SIG_SCALE, b * _SIG_SCALE, nrm, crossing * _SIG_SCALE,
                    band_px * _SIG_SCALE, min_sep=_SIG_MIN_SEP)
            peak, width = _band_quality(ts, occ)
            med, mad, n_in = _robust_offset(offsets)
            reports.append({"side": s, "n": int(len(offsets)), "n_inliers": n_in,
                            "mask_offset_px": None if crossing is None else round(crossing, 2),
                            "mask_inner_occupancy": (None if crossing_info is None
                                                     else round(crossing_info["inner"], 2)),
                            "mask_edge_drop": (None if crossing_info is None
                                               else round(crossing_info["drop"], 2)),
                            "mask_band_peak": None if peak is None else round(peak, 2),
                            "mask_band_width_px": None if width is None else round(width, 2),
                            "scan_offset_px": None if med is None else round(med, 2),
                            "scan_mad_px": None if mad is None else round(mad, 2),
                            "rail_dark": None if rail_dark is None else round(rail_dark, 1),
                            "rail_outside": None if rail_out is None else round(rail_out, 1),
                            "rail_lines": rail_n,
                            "kinds": {k: kinds.count(k) for k in sorted(set(kinds))},
                            "rise_median": round(float(np.median(rises)) if len(rises) else 0.0, 1)})
        # Verify each side against the frame before letting it move the quad.
        offsets_mask, unverified = {}, {}
        for r in reports:
            cross = r["mask_offset_px"]
            peak = r["mask_band_peak"] or 0.0
            inner = r["mask_inner_occupancy"]
            drop = r["mask_edge_drop"]
            at_band_edge = cross is not None and abs(cross) >= band_mask - _EDGE_MARGIN_PX
            # A real cloth edge has cloth covering the inside of the crossing and a
            # sharp fall across it.  A partial mask (hole, occluded rail) crosses at
            # a low inner occupancy and/or a shallow drop, which is not a boundary
            # measurement - that is how a confident wrong quad got out before.
            # A real boundary needs the rail signature outside it: a dark band
            # followed by a brighter outside.  Without it the crossing is something
            # lying on the cloth (a body, a shadow), which must not verify a side.
            rail_ok = (r["rail_dark"] is not None and r["rail_outside"] is not None
                       and r["rail_lines"] >= 6
                       and (r["rail_outside"] - r["rail_dark"]) >= _RAIL_CONTRAST_MIN)
            measured_edge = (inner is not None and inner >= _INNER_FLOOR
                             and drop is not None and drop >= _DROP_MIN and rail_ok)
            if peak < _PEAK_FLOOR and not measured_edge:
                unverified[r["side"]] = "low_cloth_area"
            elif cross is not None and not at_band_edge and measured_edge:
                offsets_mask[r["side"]] = cross * mask_scale
            elif r["scan_offset_px"] is not None and r["n_inliers"] >= _SCAN_MIN_INLIERS \
                    and (r["scan_mad_px"] or 99.0) <= _SCAN_MAD_MAX \
                    and abs(r["scan_offset_px"]) < band_mask - _EDGE_MARGIN_PX:
                offsets_mask[r["side"]] = r["scan_offset_px"] * mask_scale
            elif (r["scan_offset_px"] is not None and r["n_inliers"] >= _SCAN_MIN_INLIERS
                  and (r["scan_mad_px"] or 99) <= _SCAN_MAD_MAX
                  and abs(r["scan_offset_px"]) < band_mask - _EDGE_MARGIN_PX):
                offsets_mask[r["side"]] = r["scan_offset_px"] * mask_scale
            elif at_band_edge:
                # The curve only fell through 0.5 at the edge of the band: the real
                # boundary is somewhere outside the search, so this side is not
                # verified and must not be dragged toward the band edge.
                unverified[r["side"]] = "boundary_outside_band"
            else:
                unverified[r["side"]] = "no_boundary_evidence"

        # Explicit inheritance for a side whose own evidence is weak but not
        # contradictory: the mask is diffuse there (the vod30 left rail shares its
        # hue with the carpet, so coverage ramps rather than steps), yet the weak
        # evidence still agrees with where the prior put the side within
        # ``_INHERIT_AGREE_PX``.  Such a side stays at the prior position and is
        # reported as inherited, never as verified: confidence is penalised and the
        # caller can see exactly which sides rest on the prior.  A side whose weak
        # evidence points somewhere else is a disagreement and refuses the frame.
        inherited = {}
        if unverified:
            for side, code in list(unverified.items()):
                r = next(x for x in reports if x["side"] == side)
                # A diffuse crossing (no step at all across the threshold) carries no
                # position information: its offset is dominated by how wide the ramp
                # is, not by where the edge sits, so it is not a disagreement.
                diffuse = (r["mask_offset_px"] is not None
                           and (r["mask_edge_drop"] or 1.0) < _DROP_MIN
                           and abs(r["mask_offset_px"]) * mask_scale <= _INHERIT_DIFFUSE_PX)
                # Contradictory evidence (a crossing far from the prior *and* a scan
                # consensus in the same direction) can never inherit.
                contradicting = [v for v in (r["mask_offset_px"], r["scan_offset_px"])
                                 if v is not None and abs(v) * mask_scale > _BAND_PX / 2.0]
                if len(contradicting) >= 2:
                    continue
                weak = [] if diffuse else [v for v in (r["mask_offset_px"], r["scan_offset_px"])
                                           if v is not None]
                # ``weak`` empty means the frame showed *nothing* for this side, and
                # nothing is not agreement: inheriting there would report the prior
                # as if the frame had supported it.
                if (weak or diffuse) and all(abs(v) <= _INHERIT_AGREE_PX / mask_scale for v in weak):
                    inherited[side] = {"reason": code, "diffuse_crossing": bool(diffuse),
                                       "weak_offsets_px": [round(float(v) * mask_scale, 2) for v in weak]}
                    offsets_mask[side] = 0.0
                    del unverified[side]
        side_state = dict(unverified)
        n_verified = 4 - len(unverified) - len(inherited)
        for r in reports:
            r["verified"] = r["side"] not in unverified
            r["inherited"] = r["side"] in inherited
            if r["side"] in unverified:
                r["reason"] = unverified[r["side"]]
            elif r["side"] in inherited:
                r["reason"] = "side_inherited"
        if unverified:
            reason = ("low_cloth_area"
                      if all(v == "low_cloth_area" for v in unverified.values())
                      else "boundary_outside_band"
                      if all(v in ("low_cloth_area", "boundary_outside_band") for v in unverified.values())
                      else "no_boundary_evidence")
            return None, {"confidence": 0.0, "reason": reason, "mask": mask_note,
                          "iteration": it, "sides": reports,
                          "verified_sides": n_verified,
                          "unverified_sides": [dict(side=s, reason=unverified[s]) for s in sorted(unverified)],
                          "inherited_sides": [dict(side=s, **inherited[s]) for s in sorted(inherited)],
                          "candidates": [c["name"] for c in cands]}
        moved_mask = np.array([offsets_mask[s] for s in range(4)], float)      # mask px
        moved_px = moved_mask / mask_scale                                     # real px
        if float(np.median(np.abs(moved_px - np.median(moved_px)))) > 45.0:
            return None, {"confidence": 0.0, "reason": "prior_disagreement", "mask": mask_note,
                          "iteration": it, "sides": reports,
                          "unverified_sides": [dict(side=s, reason="prior_disagreement") for s in range(4)]}
        for s in range(4):
            # One iteration advances the FULL measured offset, clipped to the cap.
            # The cap is expressed in real pixels: an unbounded step lets one rail
            # (the 1080p bottom rail, whose cloth rolls into a shadow band) swallow
            # the frame's dark edge.
            _shift_side(quad, s, float(np.clip(moved_px[s], -_MAX_MOVE_PX, _MAX_MOVE_PX)))
        movements.append(round(float(np.mean(np.abs(np.clip(moved_px, -_MAX_MOVE_PX, _MAX_MOVE_PX)))), 2))
        side_reports = reports
        if float(np.max(np.abs(moved_px))) < _CONVERGED_PX:
            break
    quad = _order_corners(quad.astype(np.float32))
    ok, why = _plausible(quad, prior, frame.shape[1], frame.shape[0])
    if not ok:
        return None, {"confidence": 0.0, "reason": why, "mask": mask_note,
                      "iteration": it, "sides": side_reports}
    # Every side was verified this iteration (an unverified one returns above), so
    # confidence grades how clean those measurements were, not how many there were.
    peaks = [r["mask_band_peak"] if r["mask_band_peak"] is not None else 0.0 for r in side_reports]
    widths = [r["mask_band_width_px"] for r in side_reports if r["mask_band_width_px"] is not None]
    spreads = [r["scan_mad_px"] for r in side_reports if r["scan_mad_px"] is not None]

    def _unit(v, lo, hi):
        return max(0.0, min(1.0, (v - lo) / (hi - lo)))

    comp_peak = _unit(float(np.min(peaks)), _PEAK_FLOOR, 0.9)
    comp_width = 1.0 - _unit(float(np.median(widths)) if widths else 25.0, 8.0, 30.0)
    comp_spread = 1.0 - _unit(float(np.median(spreads)) if spreads else 8.0, 4.0, 14.0)
    confidence = round(0.40 * comp_peak + 0.30 * comp_width + 0.30 * comp_spread, 3)
    # An inherited side was not measured on this frame, so the quad cannot claim
    # the confidence a fully measured one earns.
    if inherited:
        confidence = round(confidence * (1.0 - 0.25 * len(inherited)), 3)
    # The table's own geometry, applied where a quad is accepted (round 17, owner item 5): a 9 ft
    # playfield is 100 x 50 inches, and at this venue at least one pair of its edges still reads
    # parallel in the image. A quad that breaks either is not thrown away - the cloth boundary was
    # still measured - but it is reported as such and cannot claim a fully measured confidence.
    try:
        from src.playfield import check_quad
        ordered = _order(quad)
        candidates = [ordered, [ordered[1], ordered[2], ordered[3], ordered[0]]]
        verdicts = [check_quad([[float(p[0]), float(p[1])] for p in c]) for c in candidates]
        playfield = min(verdicts, key=lambda v: (not v["ok"], len(v["reasons"])))
    except Exception as exc:                      # a constraint must never break a detection
        playfield = {"ok": True, "reasons": [], "metrics": {}, "error": str(exc)}
    if not playfield["ok"]:
        confidence = round(confidence * 0.6, 3)
    info = {"confidence": confidence, "reason": None, "mask": mask_note,
            "iterations": len(movements), "side_moves_px": movements,
            "verified_sides": 4 - len(inherited), "unverified_sides": [],
            "inherited_sides": [dict(side=s, **inherited[s]) for s in sorted(inherited)],
            "reason": "side_inherited" if inherited else None,
            "side_peak_occupancy": round(float(np.min(peaks)), 2),
            "edge_width_px": round(float(np.median(widths)) if widths else -1.0, 2),
            "scan_mad_px": round(float(np.median(spreads)) if spreads else -1.0, 2),
            "move_px": round(float(np.linalg.norm(quad - prior, axis=1).mean()), 2),
            "sides": side_reports, "playfield": playfield}
    if not playfield["ok"] and not inherited:
        info["reason"] = "playfield:" + ",".join(playfield["reasons"])
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
