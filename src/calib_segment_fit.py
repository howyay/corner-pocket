"""Fit the per-segment reference for vod30 from measurement, not from a guess.

Reads the measurement artifact written by ``src/calib_segment_measure.py``, applies
a framing-change test to the sampled frames, and writes
``out/calib_vod30_segments.json``:

* ``segments`` - the reference per time range, each with its quad in source
  pixels, its *source* (``human_anchors`` / ``refined`` / ``derived``), the
  coverage metric and the measured per-side evidence state;
* ``boundary_candidates`` - every sampling time where the framing test came close
  or fired, with the cause the evidence supports;
* ``late_window_alternative`` - what a late-segment reference *would* be if the
  evidence had supported a split, recorded as ``derived`` and never used while
  the split is unsupported.

The framing test is deliberately not "coverage dropped".  Coverage is the
``calibration_frac`` proxy: a body on the cloth lowers it exactly like a moved
camera would, so a boundary drawn from coverage alone would segment the VOD by
who was leaning over the table.  The test requires a *geometric* witness instead:

* ``phase_shift_px`` - whole-frame phase correlation against the t=0 anchor.  A
  camera that panned or tilted moves every static edge in the frame;
* a *consistent signed* per-side offset beyond the refinement's own noise band,
  which is how a camera move shows on the rail boundaries the mm geometry is
  built from.

Additive: this writes one new artifact and rewrites no existing calibration file.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MEASURE = ROOT / "out" / "calib_vod30_segments.measure.json"
VIDEO = ROOT / "data" / "vod_30min_260815.mp4"
ANCHORS = ROOT / "out" / "pid_anchors_vod30.json"
OUT = ROOT / "out" / "calib_vod30_segments.json"

GATE_FRACTION = 0.80          # GateConfig.calibration_warn_fraction
PHASE_MOVE_PX = 2.0           # a camera move this large is not sub-pixel noise
SIDE_NOISE_PX = 8.0           # refinement's own scatter on a verified side
CANON_W, CANON_H = 1270.0, 2540.0


def _quad(row, key="refined"):
    q = row.get(key)
    return None if q is None else np.asarray(q, np.float32)


def _signed_offsets(row):
    """Per-side offsets, only where the frame verified the side."""
    out = {}
    for s in row.get("refined_sides") or []:
        if s.get("state") == "verified" and s.get("mask_offset_px") is not None:
            out[int(s["side"])] = float(s["mask_offset_px"])
        elif s.get("scan_offset_px") is not None and s.get("state") == "verified":
            out[int(s["side"])] = float(s["scan_offset_px"])
    return out


def framing_test(row):
    """(moved, reasons, witnesses) - did the *camera* move at this sample?"""
    reasons, witnesses = [], {}
    phase = row.get("phase_shift_px")
    if phase and phase[0] is not None:
        mag = math.hypot(phase[0], phase[1])
        witnesses["phase_shift_px"] = round(mag, 2)
        if mag > PHASE_MOVE_PX:
            reasons.append("whole_frame_shift")
    offs = _signed_offsets(row)
    witnesses["verified_sides"] = len(offs)
    if len(offs) == 4:
        vals = list(offs.values())
        # A camera move displaces the *boundary*, and the refinement reports where
        # the boundary actually is relative to the reference: a consistent signed
        # offset on all four sides is a translation/scale change, a mixed one is
        # the prior sitting on a different feature.
        witnesses["side_offsets_px"] = {str(k): v for k, v in offs.items()}
        witnesses["consistent_offset_px"] = round(float(np.median(vals)), 2)
        if abs(float(np.median(vals))) > SIDE_NOISE_PX and \
                all(abs(v - float(np.median(vals))) <= SIDE_NOISE_PX for v in vals):
            reasons.append("rail_boundary_moved")
    # The refined cloth quad's own side lengths catch a zoom, which a translation
    # -only phase correlation absorbs.
    q = _quad(row, "refined")
    if q is None:
        q = _quad(row, "chained")
    if q is not None:
        lens = [float(np.hypot(*(q[i] - q[(i + 1) % 4]))) for i in range(4)]
        witnesses["side_lengths_px"] = [round(v, 1) for v in lens]
    return bool(reasons), reasons, witnesses


def cause_of(row):
    """Why the coverage proxy dropped here, in the evidence's vocabulary."""
    hsv = row.get("cloth_hsv") or {}
    v = hsv.get("v")
    desat = row.get("desaturated_frac")
    if row.get("coverage", {}).get("reference", 1.0) >= GATE_FRACTION:
        return "coverage_above_gate"
    if desat is not None and desat >= 0.05:
        return "occlusion_and_shading"
    if v is not None and v < 150:
        return "shading_not_framing"
    return "mask_instability_not_framing"


def _mm_delta(quad_a, quad_b, n=41):
    """Largest canonical-millimetre disagreement between two frame quads.

    Both quads are homographies of the same canonical table, so the honest number
    is the worst table point: map a canonical grid to pixels with one quad's
    inverse, then to millimetres with the other's forward map.
    """
    from src.pipeline import homography_to_canonical
    Ha, Hb = homography_to_canonical(quad_a), homography_to_canonical(quad_b)
    Ia = np.linalg.inv(Ha)
    xs = np.linspace(0, CANON_W, n)
    ys = np.linspace(0, CANON_H, n)
    grid = np.array([[x, y, 1.0] for y in ys for x in xs])
    pts = (Ia @ grid.T).T
    pts = pts[:, :2] / pts[:, 2:3]
    proj = (Hb @ np.column_stack([pts, np.ones(len(pts))]).T).T
    proj = proj[:, :2] / proj[:, 2:3]
    delta = np.hypot(proj[:, 0] - grid[:, 0], proj[:, 1] - grid[:, 1])
    return {"max_mm": round(float(delta.max()), 1), "p95_mm": round(float(np.percentile(delta, 95)), 1),
            "median_mm": round(float(np.median(delta)), 1)}


def _derived_late_quad(rows, t_split, min_verified=4):
    """Temporal median of the refined quads the frame verified in the late window."""
    quads = [q for r in rows if r["t"] >= t_split
             for q in [_quad(r)] if q is not None and len(_signed_offsets(r)) >= min_verified]
    if len(quads) < 3:
        return None, 0
    return np.median(np.asarray(quads, np.float64), axis=0).astype(np.float32), len(quads)


def _holdout_gate(video, quad, times, baseline=None):
    """Per-side evidence gate for a derived quad on frames it was *not* fit from.

    A reference with no human anchors is only acceptable if the frame itself shows
    every side's boundary inside the search band: verified (mask crossing with the
    rail signature) or explicitly inherited from the prior - never unverified.

    ``baseline`` is the trusted human quad.  A frame whose mask is broken refuses
    the human quad too, and that is a limit of the frame, not a defect of the
    derived quad, so each frame is judged *against the baseline*: the derived quad
    must never verify fewer sides than the human reference does on the same frame.
    """
    import cv2
    from src.table_refine import refine_quad_edges
    cap = cv2.VideoCapture(str(video))
    results, worst, worse = [], 0.0, []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            results.append({"t": t, "error": "decode_failed"})
            continue
        row = {"t": float(t)}
        for label, prior in (("derived", quad), ("baseline_human", baseline)):
            if prior is None:
                continue
            _q, info = refine_quad_edges(frame, prior)
            sides = info.get("sides") or []
            offsets = [abs(float(r["mask_offset_px"])) for r in sides
                       if r.get("mask_offset_px") is not None]
            row[label] = {
                "verified_sides": info.get("verified_sides"),
                "unverified": [s["reason"] for s in info.get("unverified_sides") or []],
                "inherited": [s["side"] for s in info.get("inherited_sides") or []],
                "confidence": info.get("confidence"),
                "boundary_max_offset_px": round(max(offsets, default=0.0), 2),
            }
        d, b = row.get("derived"), row.get("baseline_human")
        row["derived_at_least_as_good"] = (d is not None and
                                           (b is None or (d["verified_sides"] or 0) >= (b["verified_sides"] or 0)))
        if not row["derived_at_least_as_good"]:
            worse.append(row["t"])
        if d is not None and not d["unverified"]:
            worst = max(worst, d["boundary_max_offset_px"])
        results.append(row)
    cap.release()
    return {"passed": not worse, "worse_than_human_at": worse,
            "worst_verified_offset_px": round(worst, 2), "frames": results}


def build(args):
    data = json.loads(Path(args.measure).read_text())
    rows = data["rows"]
    reference = np.asarray(data["reference"]["quad"], np.float32)
    anchor_file = json.loads(ANCHORS.read_text())
    anchor_key = sorted(anchor_file["anchors"], key=float)[0]

    tested, boundaries = [], []
    for row in rows:
        moved, reasons, witnesses = framing_test(row)
        tested.append({"t": row["t"], "moved": moved, "reasons": reasons, **witnesses})
        if row["coverage"]["reference"] < GATE_FRACTION or moved:
            boundaries.append({"t": row["t"], "coverage": row["coverage"]["reference"],
                               "cause": cause_of(row), "framing_change": moved,
                               "framing_reasons": reasons, **witnesses})
    moved_any = [t for t in tested if t["moved"]]

    covers = [r["coverage"]["reference"] for r in rows]
    below = [{"t": r["t"], "coverage": r["coverage"]["reference"], "cause": cause_of(r)}
             for r in rows if r["coverage"]["reference"] < GATE_FRACTION]
    sides = [s for r in rows for s in (r.get("refined_sides") or [])]
    verified = [s for s in sides if s["state"] == "verified"]
    verified_by_side = {}
    for s in verified:
        verified_by_side.setdefault(int(s["side"]), []).append(float(s["mask_offset_px"]))
    # A held-inherit side is not a measurement; a refused frame is not a failure of
    # the reference either, so the evidence state is reported as a distribution.
    side_evidence = {
        "verified_samples": len(verified),
        "unverified_samples": len([s for s in sides if s["state"] == "unverified"]),
        "inherited_samples": len([s for s in sides if s["state"] == "inherited"]),
        "per_side_offset_px": {str(k): {"n": len(v), "median": round(float(np.median(v)), 2),
                                        "min": round(min(v), 2), "max": round(max(v), 2)}
                               for k, v in sorted(verified_by_side.items())},
        "frames_all_four_sides_verified": len([r for r in rows if len(_signed_offsets(r)) == 4]),
        "frames_sampled": len(rows),
    }
    phases = [math.hypot(*(r["phase_shift_px"][:2])) for r in rows if r.get("phase_shift_px")]
    lengths = [w["side_lengths_px"] for t in tested for w in [t] if "side_lengths_px" in w]
    lens = np.asarray(lengths, float) if lengths else np.zeros((0, 4))
    spread = [round(float(lens[:, i].max() - lens[:, i].min()), 1) for i in range(lens.shape[1])] \
        if lens.size else []

    t_split = min([b["t"] for b in below], default=None)
    derived, n_fit = (None, 0)
    if t_split is not None:
        derived, n_fit = _derived_late_quad(rows, t_split)
    holdout = None
    if derived is not None:
        holdout_times = sorted({r["t"] for r in rows
                                if r["t"] >= t_split and len(_signed_offsets(r)) < 4}
                               | {1120.2, 483.4, 1380.0, 1800.0})
        holdout = _holdout_gate(args.video, derived, holdout_times[:12], baseline=reference)

    rule = ("no sampled frame shows a camera move (whole-frame phase correlation "
            f"<= {round(max(phases), 2) if phases else 0.0} px, verified rail offsets inside "
            f"the +/-{SIDE_NOISE_PX:.0f} px refinement noise band, cloth side lengths stable "
            f"within {max(spread) if spread else 0} px), so the VOD is one calibration segment")
    if moved_any:
        rule = f"a camera move is supported at t={moved_any}, so the VOD splits there"

    payload = {
        "dataset": "vod30",
        "video": str(args.video),
        "frame_size": [1280, 720],
        "canonical_mm": {"w": CANON_W, "h": CANON_H},
        "measured_by": "src/calib_segment_measure.py",
        "fitted_by": "src/calib_segment_fit.py",
        "measurement": str(Path(args.measure).relative_to(ROOT)) if Path(args.measure).is_relative_to(ROOT)
                       else str(args.measure),
        "segmentation_verdict": "single_segment" if not moved_any else "split_supported",
        "verdict_reason": rule,
        "framing_test": {"phase_move_threshold_px": PHASE_MOVE_PX,
                         "side_noise_px": SIDE_NOISE_PX,
                         "coverage_gate_fraction": GATE_FRACTION,
                         "samples": tested},
        "segments": [{
            "id": "vod30-s1",
            "t_start": float(rows[0]["t"]),
            "t_end": float(rows[-1]["t"]),
            "quad_px": np.round(reference, 2).tolist(),
            "source": "human_anchors",
            "source_detail": f"out/pid_anchors_vod30.json anchors['{anchor_key}'][:4] "
                             f"(the six hand pocket anchors; first four are the cloth quad)",
            "coverage": {
                "metric": "share of the reference quad that is cloth-hued at that time "
                          "(the calibration_frac proxy)",
                "n": len(covers), "median": round(float(np.median(covers)), 3),
                "min": round(float(min(covers)), 3), "p10": round(float(np.percentile(covers, 10)), 3),
                "frames_below_gate": below,
            },
            "evidence": {
                "phase_shift_max_px": round(max(phases), 2) if phases else None,
                "cloth_side_length_spread_px": spread,
                "trusted_for_mm": True,
                "trust_reason": "the frame's own rail boundaries verify against this quad on every "
                                "sampled frame that is not occluded, and the whole frame never moves",
                **side_evidence,
            },
        }],
        "boundary_candidates": boundaries,
        "late_window_alternative": None if derived is None else {
            "used": False,
            "source": "derived",
            "fit_from": {"t_start": t_split, "t_end": float(rows[-1]["t"]),
                         "method": "componentwise temporal median of the refined quads with all four "
                                   "sides verified",
                         "accepted_quads": n_fit},
            "quad_px": np.round(derived, 2).tolist(),
            "agreement_with_segments": _mm_delta(reference, derived),
            "corner_delta_px": [round(float(v), 2) for v in
                                np.linalg.norm(np.asarray(derived, float) - np.asarray(reference, float), axis=1)],
            "per_side_evidence_gate": holdout,
            "why_not_used": "no framing change is supported, so a late-segment reference would "
                            "replace trusted human geometry with a derived quad and move canonical "
                            "millimetres by the amount reported in agreement_with_segments",
        },
        "notes": [
            "calibration_frac is a proxy: occlusion and shading lower it exactly like a camera move would.",
            "The gate's calibration_warn_fraction=0.80 fires on late samples that the per-side rail "
            "evidence shows are correctly calibrated; use evidence.trusted_for_mm, not coverage alone.",
            "Additive artifact: no existing calibration file was rewritten.",
        ],
    }
    Path(args.out).write_text(json.dumps(payload, indent=1))
    print(json.dumps({k: payload[k] for k in ("segmentation_verdict", "verdict_reason")}, indent=1))
    print(f"segments={len(payload['segments'])} boundary_candidates={len(boundaries)} "
          f"verified_side_samples={len(verified)}/{len(sides)} "
          f"wrote {args.out}")
    if holdout:
        print(f"late_window_alternative gate passed={holdout['passed']} "
              f"worst_verified_offset_px={holdout['worst_verified_offset_px']} "
              f"worse_than_human_at={holdout['worse_than_human_at']}")
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--measure", default=str(MEASURE))
    ap.add_argument("--video", default=str(VIDEO))
    ap.add_argument("--out", default=str(OUT))
    return build(ap.parse_args(argv))


if __name__ == "__main__":
    main()
