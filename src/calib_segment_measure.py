"""Measure where the vod30 framing changes, so segmentation is evidence, not a guess.

The served queue's ``calibration_frac`` (share of the reference cloth quad that is
actually cloth-hued at an event's time) drops from ~1.00 early to ~0.80 late.  A
drop like that has three causes that must be told apart before any boundary is
drawn:

1. **a genuine camera move** - the cloth boundary really sits somewhere else, so
   the old quad is off the cloth and a new reference is both necessary and
   obtainable from the frame;
2. **occlusion** - a player or a cue stands on the rail, the mask retracts, and
   the boundary is still exactly where the reference puts it;
3. **exposure / white balance** - the cloth hue drifts out of the adaptive mask
   window, so the *mask* shrinks while the geometry is unchanged.

The discriminator is the per-side refinement evidence in ``src/table_refine``:
a side is only *verified* when the frame shows its boundary inside the search
band (inner occupancy + a sharp drop + the dark-rail/bright-cloth signature), and
a side whose boundary is genuinely elsewhere reports ``boundary_outside_band``
instead of following the prior.  So this tool measures, per sample:

* ``coverage`` - the ``calibration_frac`` metric itself, against each candidate
  reference quad (hand anchors, ``corners_30min_v2``);
* ``refined`` - the quad refined from the reference, with its per-side state;
* ``chained`` - the quad refined from the *previously accepted* quad, which
  tracks a real move and is unaffected by a stale prior;
* ``naive`` / ``v3`` / ``lines`` - independent detections that owe the reference
  nothing;
* the corner disagreement between all of those and the reference.

A camera move shows as a *consistent* offset that ``chained`` follows and
``naive``/``v3``/``lines`` agree with; occlusion shows as a coverage dip with the
verified sides staying put; exposure shows as a coverage dip with the rail and
scan evidence intact but the mask peak low.

Read-only: writes one measurement artifact, rewrites no calibration file.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.datasets import media_path  # noqa: E402

VIDEO = media_path(ROOT, "vod30")
ANCHORS = ROOT / "out" / "pid_anchors_vod30.json"
SCAN_QUAD = ROOT / "out" / "corners_30min_v2.json"
OUT = ROOT / "out" / "calib_vod30_segments.measure.json"

# The candidate windows the gate report flagged, plus a probe either side of the
# reported late candidates so the boundary is located, not assumed.
CANDIDATE_TIMES = (450.0, 450.3, 483.4, 483.7, 941.5, 1119.9, 1120.2, 1120.6, 1200.0)


def anchors_quad():
    """The human reference quad: the first four of the six hand anchors at t=70."""
    from src.table_detect import _order_corners
    data = json.loads(ANCHORS.read_text())
    first = next(iter(data["anchors"].values()))
    return _order_corners(np.asarray(first[:4], np.float32))


def scan_quad():
    data = json.loads(SCAN_QUAD.read_text())
    return np.asarray(data["corners"], np.float32)


def coverage(frame, quad):
    """Share of ``quad`` that is cloth-hued in ``frame`` (the calibration_frac metric)."""
    from src.table_detect import detect_cloth_mask
    mask = detect_cloth_mask(frame)
    poly = np.zeros(mask.shape[:2], np.uint8)
    cv2.fillPoly(poly, [np.round(quad).astype(np.int32)], 1)
    total = int((poly > 0).sum())
    return round(float(((mask > 0) & (poly > 0)).sum()) / max(1, total), 3)


def cloth_stats(frame):
    """Cloth mask mass and the largest component's box, for the framing check."""
    from src.table_detect import detect_cloth_mask
    mask = detect_cloth_mask(frame)
    binary = (mask > 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if n <= 1:
        return {"cloth_px": 0, "largest_px": 0, "largest_box": None}
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    box = [int(stats[idx, cv2.CC_STAT_LEFT]), int(stats[idx, cv2.CC_STAT_TOP]),
           int(stats[idx, cv2.CC_STAT_WIDTH]), int(stats[idx, cv2.CC_STAT_HEIGHT])]
    return {"cloth_px": int(binary.sum()), "largest_px": int(stats[idx, cv2.CC_STAT_AREA]),
            "largest_box": box}


def framing_probe(frame, reference, anchor_gray):
    """Is the *camera* still where it was?  Two reference-free tests.

    ``phase`` is a whole-frame phase correlation against the t=0 anchor: a pan or
    tilt moves every static edge in the frame, so the dominant shift is the camera,
    not the players.  ``cloth_hsv`` is the cloth patch's own colour under the
    reference quad: a uniform move of hue/saturation/value is the exposure and
    white balance drifting, which shrinks the hue mask while the geometry is
    untouched.  ``desaturated`` inside the quad is the occlusion proxy - bodies,
    shadows and the cue are not cloth-hued, and they are what a coverage drop with
    unmoved boundaries looks like.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    shift = None
    if anchor_gray is not None:
        hann = cv2.createHanningWindow((gray.shape[1], gray.shape[0]), cv2.CV_32F)
        try:
            result = cv2.phaseCorrelate(np.float32(anchor_gray), np.float32(gray), hann)
            shift_px, response = result if isinstance(result, tuple) and len(result) == 2 else (result, None)
            shift = [round(float(shift_px[0]), 2), round(float(shift_px[1]), 2)]
            if response is not None and math.isfinite(float(response)):
                shift = shift + [round(float(response), 4)]
        except (cv2.error, TypeError, ValueError, IndexError):
            shift = None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    poly = np.zeros(hsv.shape[:2], np.uint8)
    cv2.fillPoly(poly, [np.round(reference).astype(np.int32)], 1)
    inside = hsv[poly > 0]
    if len(inside) == 0:
        return {"phase_shift_px": shift, "cloth_hsv": None, "desaturated_frac": None}
    return {
        "phase_shift_px": shift,
        "cloth_hsv": {"h": round(float(np.median(inside[:, 0])), 1),
                      "s": round(float(np.median(inside[:, 1])), 1),
                      "v": round(float(np.median(inside[:, 2])), 1)},
        "desaturated_frac": round(float((inside[:, 1] < 90).mean()), 3),
        "dark_frac": round(float((inside[:, 2] < 60).mean()), 3),
    }


def profile_sides(frame, reference, half=40.0, n=21):
    """Per-side rail offset from the raw intensity gradient - no mask, no refinement.

    ``src/table_refine`` measures a side with the cloth mask and a rail-contrast
    check; that is the trusted machinery, but it shares the mask with the proxy
    under test.  This is the third, independent opinion: a straight perpendicular
    intensity profile through the prior side, median-combined over the side's
    length, and the offset of its strongest gradient.  A camera that moved would
    move this number; a body on the cloth barely touches it, because the median
    over 21 stations outvotes a local occluder.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape[:2]
    offsets = np.arange(-half, half + 1e-9, 0.5)
    out = []
    for s in range(4):
        a, b = np.asarray(reference[s], float), np.asarray(reference[(s + 1) % 4], float)
        mid = (a + b) / 2.0
        tangent = b - a
        nlen = float(np.hypot(*tangent))
        if nlen < 1:
            out.append(None)
            continue
        nrm = np.array([-tangent[1], tangent[0]]) / nlen
        if np.dot(nrm, mid - np.asarray(reference, float).mean(axis=0)) < 0:
            nrm = -nrm
        profiles = []
        for frac in np.linspace(0.1, 0.9, n):
            p0 = a + tangent * frac
            vals = []
            for off in offsets:
                p = p0 + nrm * off
                x, y = int(round(p[0])), int(round(p[1]))
                vals.append(gray[y, x] if 0 <= x < w and 0 <= y < h else np.nan)
            profiles.append(vals)
        stack = np.asarray(profiles, float)
        if np.all(np.isnan(stack)):
            out.append(None)
            continue
        prof = np.nanmedian(stack, axis=0)
        grad = np.abs(np.gradient(prof))
        if not np.isfinite(grad).any() or grad.max() < 6.0:
            out.append({"offset_px": None, "gradient": round(float(np.nanmax(grad)), 2)})
            continue
        # Ignore the outermost 4 px: a profile whose strongest edge sits at the end
        # of the window is a boundary outside the search, not a measurement.
        inner = np.zeros_like(grad, bool)
        inner[8:len(grad) - 8] = True
        idx = int(np.argmax(np.where(inner, grad, -1)))
        out.append({"offset_px": round(float(offsets[idx]), 2),
                    "gradient": round(float(grad[idx]), 2)})
    return out


def _disagreement(a, b):
    if a is None or b is None:
        return None
    d = np.linalg.norm(np.asarray(a, np.float64) - np.asarray(b, np.float64), axis=1)
    return {"mean_px": round(float(d.mean()), 2), "max_px": round(float(d.max()), 2),
            "per_corner_px": [round(float(v), 2) for v in d]}


def _side_state(info):
    """Per-side evidence from a refinement pass, in the artifact's vocabulary."""
    sides = info.get("sides") or []
    unverified = {int(s["side"]): s["reason"] for s in info.get("unverified_sides") or []}
    inherited = {int(s["side"]): s for s in info.get("inherited_sides") or []}
    state = []
    for r in sides:
        s = int(r["side"])
        state.append({
            "side": s,
            "state": "unverified" if s in unverified else ("inherited" if s in inherited else "verified"),
            "reason": unverified.get(s) or ("side_inherited" if s in inherited else None),
            "mask_offset_px": r.get("mask_offset_px"),
            "mask_inner_occupancy": r.get("mask_inner_occupancy"),
            "mask_edge_drop": r.get("mask_edge_drop"),
            "mask_band_peak": r.get("mask_band_peak"),
            "scan_offset_px": r.get("scan_offset_px"),
            "scan_mad_px": r.get("scan_mad_px"),
            "scan_inliers": r.get("n_inliers"),
            "rail_dark": r.get("rail_dark"),
            "rail_outside": r.get("rail_outside"),
            "rail_lines": r.get("rail_lines"),
        })
    return state


def measure_frame(frame, reference, chain_prior, anchor_gray=None):
    """Everything measurable about one frame, relative to ``reference``."""
    from src.table_detect import detect_table
    from src.quad_fit import fit_quad_v3
    from src.quad_fit_lines import fit_quad_lines
    from src.table_refine import refine_quad_edges

    row = {"coverage": {"reference": coverage(frame, reference)}}
    row.update(cloth_stats(frame))
    row.update(framing_probe(frame, reference, anchor_gray))
    row["profile_sides"] = profile_sides(frame, reference)

    naive = detect_table(frame).get("corners")
    row["naive"] = None if naive is None else np.round(naive, 2).tolist()
    row["naive_disagreement"] = _disagreement(naive, reference)

    for name, fit in (("v3", fit_quad_v3), ("lines", fit_quad_lines)):
        try:
            q = fit(frame)
        except Exception as exc:                     # a fitting stage may refuse
            q, row[f"{name}_error"] = None, f"{type(exc).__name__}: {exc}"
        row[name] = None if q is None else np.round(np.asarray(q, np.float64), 2).tolist()
        row[f"{name}_disagreement"] = _disagreement(q, reference)

    quad, info = refine_quad_edges(frame, reference)
    row["refined"] = None if quad is None else np.round(quad, 2).tolist()
    row["refined_disagreement"] = _disagreement(quad, reference)
    row["refined_confidence"] = info.get("confidence")
    row["refined_reason"] = info.get("reason")
    row["refined_verified_sides"] = info.get("verified_sides")
    row["refined_sides"] = _side_state(info)
    if quad is not None:
        row["coverage"]["refined"] = coverage(frame, quad)

    if chain_prior is not None:
        cquad, cinfo = refine_quad_edges(frame, chain_prior)
        row["chained"] = None if cquad is None else np.round(cquad, 2).tolist()
        row["chained_disagreement"] = _disagreement(cquad, reference)
        row["chained_confidence"] = cinfo.get("confidence")
        row["chained_reason"] = cinfo.get("reason")
        row["chained_verified_sides"] = cinfo.get("verified_sides")
        row["chained_sides"] = _side_state(cinfo)
        if cquad is not None:
            row["coverage"]["chained"] = coverage(frame, cquad)
    return row


def run(args):
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit(f"cannot open {args.video}")
    times = sorted({round(float(t), 3) for t in
                    list(np.arange(0.0, args.until + args.every, args.every)) + list(args.at)})
    reference = anchors_quad()
    scan = scan_quad()
    rows, chain_prior, chain_from = [], reference, None
    anchor_gray, anchor_t = None, None
    t0 = time.time()
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok:
            rows.append({"t": t, "error": "decode_failed"})
            continue
        if anchor_gray is None:
            anchor_gray, anchor_t = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), t
        row = measure_frame(frame, reference, chain_prior, anchor_gray)
        row["t"] = t
        row["anchor_t"] = anchor_t
        row["coverage"]["scan_quad_v2"] = coverage(frame, scan)
        row["chain_prior_t"] = chain_from
        rows.append(row)
        # A chain step is only extended by a quad the frame verified, so the chain
        # cannot walk off on its own noise; a genuine move shows as a chain restart.
        accepted = row.get("chained") or row.get("refined")
        if accepted is not None:
            chain_prior, chain_from = np.asarray(accepted, np.float32), t
        print(f"t={t:7.1f} cov={row['coverage']['reference']:.3f} "
              f"refined={'-' if row['refined'] is None else row['refined_reason'] or 'ok'}"
              f"({row.get('refined_verified_sides')}) "
              f"phase={row['phase_shift_px']} "
              f"hsv={row['cloth_hsv']} desat={row['desaturated_frac']} "
              f"v3_d={_fmt(row['v3_disagreement'])} "
              f"chain_d={_fmt(row.get('chained_disagreement'))}", flush=True)
    cap.release()
    payload = {
        "video": str(args.video),
        "reference": {"source": "hand anchors t=70 (first four of pid_anchors_vod30.json)",
                      "quad": np.round(reference, 2).tolist()},
        "scan_quad_v2_for_comparison": np.round(scan, 2).tolist(),
        "times": times,
        "sample_every_s": args.every,
        "seconds": round(time.time() - t0, 1),
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1))
    print(f"wrote {args.out} ({len(rows)} samples, {payload['seconds']}s)")
    return payload


def _fmt(d):
    return "-" if not d else f"{d['mean_px']:.1f}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=str(VIDEO))
    ap.add_argument("--every", type=float, default=60.0)
    ap.add_argument("--until", type=float, default=1800.0)
    ap.add_argument("--at", type=float, nargs="*", default=list(CANDIDATE_TIMES))
    ap.add_argument("--out", default=str(OUT))
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
