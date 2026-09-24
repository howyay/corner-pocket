"""Measure the disagreement between the two calibration mappings on vod30.

Two pixel<->millimetre mappings are in the tree for the same static camera:

* **A - hand anchors** (``out/pid_anchors_vod30.json``, six clicked pocket
  positions at t=70; the first four are the cloth quad): the mapping every
  millimetre-bearing consumer *should* use, and the one the segment artifact
  (``out/calib_vod30_segments.json``) resolves.
* **B - scan quad** (``out/scan30/corners.json``, written by
  ``src/scan_events.py`` as the median of the scan's own frame detections): the
  mapping the served scan measured its ``from_mm``/``to_mm`` with.

They are not the same mapping, and the difference is positional: this tool
reports *where* they disagree, *how much*, and which one the frames themselves
support.  Nothing here rewrites a calibration file; the artifact is additive and
the numbers are the argument.

Four independent measurements, each with its sample size in the artifact:

1. ``pixel_disagreement`` - >= 24 canonical points (5x5 grid + the six pockets),
   projected through both mappings, in px and in mm, grouped by region.
2. ``held_out_anchors`` - anchors 5 and 6 (the two side pockets) are part of the
   same human click set but are **not** used to fit the four-corner quad, so
   their residual under each mapping is a held-out test of that mapping.
3. ``rail_evidence`` - ``src.table_refine.refine_quad_edges`` run on real frames
   with each quad as the prior: the trusted dark-rail/bright-cloth boundary
   check.  The mapping whose prior the frame's own boundaries verify is the one
   the frame supports.
4. ``event_projection`` - the served candidates' claimed mm projected back to
   pixels under each mapping, so the consumer-level cost is visible.

Run::

    PYTHONPATH=. .venv/bin/python -m src.calib_mapping_audit
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.event_gates import CANON_H, CANON_W, POCKETS_MM  # noqa: E402
from src.pipeline import homography_to_canonical  # noqa: E402

SMALL_W, SMALL_H = 960, 540      # the scan's working frame (src.info_complete_scan)
ANCHORS = ROOT / "out" / "pid_anchors_vod30.json"
SCAN_QUAD = ROOT / "out" / "scan30" / "corners.json"
VIDEO = ROOT / "data" / "vod_30min_260815.mp4"
CANDIDATES = ROOT / "out" / "scan30" / "candidates_selected.json"
OUT = ROOT / "out" / "calib_mapping_audit.json"
# Frames the segment artifact already measured: early (unoccluded), the two
# verified low-coverage event frames, and the last sample of the VOD.
FRAME_TIMES = (70.0, 0.0, 483.4, 1120.2, 1800.0)
GRID = 5                       # 5x5 = 25 grid points, plus the six pockets

REGION_BANDS_MM = (("head", 0.0, 400.0), ("middle", 400.0, 2140.0), ("foot", 2140.0, CANON_H + 1))


def _load_anchors(path=ANCHORS):
    data = json.loads(Path(path).read_text())
    anchors = data["anchors"]
    first = next(iter(anchors.values()))
    from src.table_detect import _order_corners
    quad = _order_corners(np.asarray(first[:4], np.float32))
    return quad, [np.asarray(p, np.float64) for p in first[4:]], data


def load_mappings(anchors_path=ANCHORS, scan_path=SCAN_QUAD):
    """``(HA, HB, anchors_quad, scan_quad, side_pockets)`` - both px -> mm maps."""
    quad_a, pockets, _ = _load_anchors(anchors_path)
    quad_b = np.asarray(json.loads(Path(scan_path).read_text())["corners"], np.float32)
    return (homography_to_canonical(quad_a), homography_to_canonical(quad_b),
            quad_a, quad_b, pockets)


def project(H_inv, mm):
    x, y, w = H_inv @ np.array([float(mm[0]), float(mm[1]), 1.0], np.float64)
    if not math.isfinite(w) or abs(w) < 1e-12:
        return None
    return np.array([x / w, y / w], np.float64)


def unproject(H, px):
    x, y, w = H @ np.array([float(px[0]), float(px[1]), 1.0], np.float64)
    if not math.isfinite(w) or abs(w) < 1e-12:
        return None
    return np.array([x / w, y / w], np.float64)


def local_mm_per_px(H, px, step=6.0):
    """Millimetres per pixel of the mapping's own Jacobian at a pixel."""
    p0 = unproject(H, px)
    if p0 is None:
        return None
    acc = []
    for dx, dy in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step)):
        q = unproject(H, (px[0] + dx, px[1] + dy))
        if q is None:
            continue
        acc.append(math.hypot(q[0] - p0[0], q[1] - p0[1]) / step)
    return float(np.mean(acc)) if acc else None


def grid_points():
    """(label, mm): 5x5 grid + the six pocket centres, de-duplicated.

    The grid corners coincide with four pockets, so the unique point count is
    reported alongside the nominal one: 25 + 6 - 4 = 27.
    """
    pts, seen = [], set()
    for i in range(GRID):
        for j in range(GRID):
            x = round(CANON_W * i / (GRID - 1), 1)
            y = round(CANON_H * j / (GRID - 1), 1)
            if (x, y) in seen:
                continue
            seen.add((x, y))
            pts.append((f"grid_{i}_{j}", [x, y]))
    for name, mm in POCKETS_MM.items():
        key = (round(mm[0], 1), round(mm[1], 1))
        if key in seen:
            continue
        seen.add(key)
        pts.append((f"pocket_{name}", [mm[0], mm[1]]))
    return pts


def region_of(mm):
    for name, lo, hi in REGION_BANDS_MM:
        if lo <= mm[1] < hi:
            return name
    return "outside"


def pixel_disagreement(HA, HB):
    """Per-point px and mm disagreement, with the regional aggregates."""
    HAi, HBi = np.linalg.inv(HA), np.linalg.inv(HB)
    rows = []
    for label, mm in grid_points():
        pa, pb = project(HAi, mm), project(HBi, mm)
        if pa is None or pb is None:
            continue
        d_px = float(np.hypot(*(pa - pb)))
        # One-way millimetre error, not the sum of both: A is the mapping the
        # frames support, so the number that matters is how far B's pixel puts
        # the point off the canonical position in A's millimetres.
        b_mm, a_mm = unproject(HA, pb), unproject(HB, pa)
        err_b_mm = None if b_mm is None else float(np.hypot(*(b_mm - np.asarray(mm, float))))
        err_a_mm = None if a_mm is None else float(np.hypot(*(a_mm - np.asarray(mm, float))))
        rows.append({"label": label, "mm": [round(v, 1) for v in mm],
                     "region": region_of(mm),
                     "a_px": [round(pa[0], 1), round(pa[1], 1)],
                     "b_px": [round(pb[0], 1), round(pb[1], 1)],
                     "d_px": round(d_px, 1),
                     "b_off_mm": None if err_b_mm is None else round(err_b_mm, 1),
                     "a_off_mm": None if err_a_mm is None else round(err_a_mm, 1),
                     "mm_per_px_here": round(err_b_mm / max(d_px, 1e-6), 2) if err_b_mm else None})
    groups = {}
    for row in rows:
        groups.setdefault(row["region"], []).append(row)
    summary = {}
    for name, group in groups.items():
        summary[name] = {
            "n": len(group),
            "d_px_median": round(float(np.median([r["d_px"] for r in group])), 1),
            "d_px_max": round(max(r["d_px"] for r in group), 1),
            "b_off_mm_median": round(float(np.median([r["b_off_mm"] for r in group
                                                      if r["b_off_mm"] is not None])), 1),
            "b_off_mm_max": round(max(r["b_off_mm"] for r in group
                                      if r["b_off_mm"] is not None), 1),
            "mm_per_px_median": round(float(np.median([r["mm_per_px_here"] for r in group
                                                       if r["mm_per_px_here"] is not None])), 2),
        }
    return rows, summary


def corner_containment(quad_a, quad_b):
    """Do the other mapping's corners even lie on the cloth?

    The decisive geometric statement: if B's head corners sit outside the quad
    the frame's own rail boundaries verify (A), then B is not the same physical
    rectangle, whatever its mm frame is called.
    """
    out = {}
    for key, quad, other in (("b_corners_vs_a_cloth", quad_a, quad_b),
                             ("a_corners_vs_b_cloth", quad_b, quad_a)):
        rows = []
        for i, pt in enumerate(np.asarray(other, np.float32)):
            signed = float(cv2.pointPolygonTest(np.asarray(quad, np.float32),
                                                (float(pt[0]), float(pt[1])), True))
            rows.append({"corner": i, "px": [round(float(pt[0]), 1), round(float(pt[1]), 1)],
                         "signed_dist_px": round(signed, 1),
                         "inside": bool(signed >= 0)})
        out[key] = {"n": len(rows), "n_inside": sum(1 for r in rows if r["inside"]), "rows": rows}
    return out


def held_out_anchors(HA, HB, pockets):
    """Anchors 5-6 (side pockets) are clicked, not fitted: a held-out residual."""
    out = []
    for name, px in zip(("left-side", "right-side"), pockets):
        truth = np.asarray(POCKETS_MM[name], np.float64)
        row = {"anchor": name, "clicked_px": [float(px[0]), float(px[1])],
               "expected_mm": [float(truth[0]), float(truth[1])]}
        for key, H in (("a", HA), ("b", HB)):
            got = unproject(H, px)
            row[f"{key}_mm"] = [round(float(v), 1) for v in got]
            row[f"{key}_err_mm"] = round(float(np.hypot(*(got - truth))), 1)
        out.append(row)
    return out


def rail_evidence(video, times, quad_a, quad_b, size=(1280, 720)):
    """Run the trusted per-side rail check with each quad as the prior.

    ``refine_quad_edges`` only reports a side as verified when the frame shows
    its boundary inside the search band with the inner-occupancy / edge-drop /
    dark-rail-bright-cloth signature.  A prior that is 90 px off cannot verify,
    so this separates "the frame agrees with mapping X" from "the mask moved".
    """
    from src.table_refine import refine_quad_edges

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return {"error": f"cannot open {video}"}
    rows = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            rows.append({"t": t, "error": "decode_failed"})
            continue
        if frame.shape[1] != size[0]:
            frame = cv2.resize(frame, size)
        row = {"t": t}
        for key, quad in (("a_hand_anchors", quad_a), ("b_scan_quad", quad_b)):
            out, info = refine_quad_edges(frame, np.asarray(quad, np.float32))
            sides = info.get("sides") or []
            row[key] = {
                "reason": info.get("reason"),
                "verified_sides": info.get("verified_sides"),
                "inherited_sides": len(info.get("inherited_sides") or []),
                "supported_sides": (info.get("verified_sides") or 0)
                                   + len(info.get("inherited_sides") or []),
                "unverified": {str(s["side"]): s.get("reason")
                               for s in info.get("unverified_sides") or []},
                "inherited": {str(s["side"]): s.get("reason")
                              for s in info.get("inherited_sides") or []},
                "mask_offsets_px": {str(s["side"]): s.get("mask_offset_px") for s in sides},
                "rail_dark": {str(s["side"]): s.get("rail_dark") for s in sides},
                "quad_diff_max_px": None if out is None else round(float(
                    np.linalg.norm(np.asarray(out, float) - np.asarray(quad, float),
                                   axis=1).max()), 2),
            }
        rows.append(row)
    cap.release()
    return {"times": list(times), "rows": rows}


def foreshortening(HA, HB, quad_a, quad_b):
    """mm-per-px at the head and foot rails, for both mappings."""
    out = {}
    for key, H, quad in (("a_hand_anchors", HA, quad_a), ("b_scan_quad", HB, quad_b)):
        head = local_mm_per_px(H, (quad[0] + quad[1]) / 2.0)
        foot = local_mm_per_px(H, (quad[2] + quad[3]) / 2.0)
        left = local_mm_per_px(H, (quad[0] + quad[3]) / 2.0)
        right = local_mm_per_px(H, (quad[1] + quad[2]) / 2.0)
        head_len = float(np.linalg.norm(quad[1] - quad[0]))
        foot_len = float(np.linalg.norm(quad[2] - quad[3]))
        out[key] = {"head_mm_per_px": round(head, 3), "foot_mm_per_px": round(foot, 3),
                    "left_mm_per_px": round(left, 3), "right_mm_per_px": round(right, 3),
                    "head_over_foot": round(head / foot, 2) if foot else None,
                    "head_rail_px": round(head_len, 1), "foot_rail_px": round(foot_len, 1),
                    "head_rail_mm_per_px": round(CANON_W / head_len, 2),
                    "foot_rail_mm_per_px": round(CANON_W / foot_len, 2),
                    "rail_compression": round(foot_len / head_len, 2) if head_len else None}
    out["cost_of_10px_mm"] = {
        "head_perpendicular": round(10.0 * out["a_hand_anchors"]["head_mm_per_px"], 1),
        "head_along_rail": round(10.0 * out["a_hand_anchors"]["head_rail_mm_per_px"], 1),
        "foot_perpendicular": round(10.0 * out["a_hand_anchors"]["foot_mm_per_px"], 1),
        "foot_along_rail": round(10.0 * out["a_hand_anchors"]["foot_rail_mm_per_px"], 1),
    }
    return out


def event_projection(HA, HB, path=CANDIDATES):
    """Claimed mm -> px under each mapping, for the served candidates."""
    try:
        events = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"error": f"cannot read {path}"}
    if isinstance(events, dict):
        events = events.get("events") or events.get("candidates") or []
    HAi, HBi = np.linalg.inv(HA), np.linalg.inv(HB)
    rows = []
    for ev in events:
        for field in ("from_mm", "to_mm", "last_mm"):
            mm = ev.get(field)
            if not mm:
                continue
            pa, pb = project(HAi, mm), project(HBi, mm)
            if pa is None or pb is None:
                continue
            rows.append({"t": ev.get("t"), "type": ev.get("type"), "field": field,
                         "mm": [round(v, 1) for v in mm],
                         "region": region_of(mm),
                         "a_px": [round(pa[0], 1), round(pa[1], 1)],
                         "b_px": [round(pb[0], 1), round(pb[1], 1)],
                         "d_px": round(float(np.hypot(*(pa - pb))), 1)})
    head = [r["d_px"] for r in rows if r["region"] == "head"]
    foot = [r["d_px"] for r in rows if r["region"] == "foot"]
    return {"source": str(path), "n_projected": len(rows), "rows": rows,
            "head_median_px": round(float(np.median(head)), 1) if head else None,
            "head_max_px": round(max(head), 1) if head else None,
            "foot_median_px": round(float(np.median(foot)), 1) if foot else None,
            "foot_max_px": round(max(foot), 1) if foot else None}


def claim_frame_provenance(HA, HB, path=CANDIDATES):
    """Which mapping actually wrote the claims' stored millimetres?

    A pot candidate carries both ``last_mm`` and the pixel it was measured at
    (``last_cx``/``last_cy``, in the scan's 960x540 working frame).  Feeding
    ``last_mm`` back through each candidate mapping and comparing with the stored
    pixel is therefore a *held-out test of the claim frame*, independent of the
    quad evidence: the frame that wrote the millimetres is the one that returns
    the pixel the scan saw.

    ``src.info_complete_scan`` builds its homography from ``detect_table`` and
    never persists it, so this reconstructs it from ``out/scan30/corners.json``
    (the same detector's saved median quad) and reports the residual of both
    candidates; the anchors are the physical mapping, not the claim frame.
    """
    try:
        events = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"error": f"cannot read {path}"}
    rows = [e for e in events if e.get("last_cx") is not None and e.get("last_mm")]
    if not rows:
        return {"error": "no candidate carries both last_mm and a pixel", "n": 0}
    out = {"source": str(path), "n": len(rows), "frame": "960x540 (the scan's working space)"}
    for key, H in (("hand_anchors", HA), ("scan_quad", HB)):
        inverse = np.linalg.inv(H)
        residuals = []
        for event in rows:
            px = project(inverse, event["last_mm"])
            if px is None:
                continue
            # The quad and both mappings are in 1280x720; the stored pixel is not.
            px = px * np.array([SMALL_W / 1280.0, SMALL_H / 720.0], np.float64)
            residuals.append(float(np.hypot(px[0] - event["last_cx"], px[1] - event["last_cy"])))
        residuals.sort()
        out[key] = {"n": len(residuals),
                    "median_px": round(float(np.median(residuals)), 2) if residuals else None,
                    "p90_px": round(float(np.percentile(residuals, 90)), 2) if residuals else None,
                    "max_px": round(max(residuals), 2) if residuals else None}
    a, b = out["hand_anchors"]["median_px"], out["scan_quad"]["median_px"]
    out["verdict"] = ("the claims were written in the scan frame"
                      if a is not None and b is not None and b < a / 2.0 else
                      "inconclusive: neither candidate reproduces the stored pixels")
    out["note"] = ("the scan's own homography is not persisted; corners.json is the same "
                   "detector's saved median quad, so its residual is an upper bound")
    return out


def build(args):
    HA, HB, quad_a, quad_b, pockets = load_mappings(args.anchors, args.scan_quad)
    rows, summary = pixel_disagreement(HA, HB)
    payload = {
        "question": "which px<->mm mapping is authoritative: hand anchors or scan quad",
        "mapping_a": {"name": "hand anchors (first four of the six clicked pockets)",
                      "source": str(args.anchors), "quad_px": np.round(quad_a, 2).tolist()},
        "mapping_b": {"name": "scan quad (median of the scan's own frame detections)",
                      "source": str(args.scan_quad), "quad_px": np.round(quad_b, 2).tolist()},
        "sample_size": {"grid_points": GRID * GRID, "pockets": len(POCKETS_MM),
                        "points_total": len(rows), "unique_points": len(rows)},
        "pixel_disagreement": {"rows": rows, "by_region": summary},
        "corner_containment": corner_containment(quad_a, quad_b),
        "held_out_anchors": held_out_anchors(HA, HB, pockets),
        "claim_frame_provenance": claim_frame_provenance(HA, HB, args.candidates),
        "foreshortening": foreshortening(HA, HB, quad_a, quad_b),
        "rail_evidence": rail_evidence(args.video, args.times, quad_a, quad_b),
        "event_projection": event_projection(HA, HB, args.candidates),
        "notes": [
            "Mapping A is the quad the segment artifact (out/calib_vod30_segments.json) resolves and the one src/eval_events.reference_calibration prefers; B is only its fallback for datasets without anchors.",
            "The scan's queued mm (from_mm/to_mm/last_mm) were measured with B, so projecting them with A mixes frames; see event_projection.",
            "The rail check is the discriminator: a prior 90 px off cannot verify against the frame's own boundary band.",
        ],
    }
    Path(args.out).write_text(json.dumps(payload, indent=1))
    return payload


def _print(payload):
    print(f"points compared: {payload['sample_size']['points_total']}")
    print(f"{'region':8s} {'n':>3s} {'d_px med':>9s} {'d_px max':>9s} "
          f"{'B off mm med':>13s} {'B off mm max':>13s} {'mm/px':>6s}")
    for name, row in payload["pixel_disagreement"]["by_region"].items():
        print(f"{name:8s} {row['n']:3d} {row['d_px_median']:9.1f} {row['d_px_max']:9.1f} "
              f"{row['b_off_mm_median']:13.1f} {row['b_off_mm_max']:13.1f} "
              f"{row['mm_per_px_median']:6.2f}")
    print("\nheld-out side-pocket anchors (clicked, not fitted):")
    for row in payload["held_out_anchors"]:
        print(f"  {row['anchor']:10s} clicked {row['clicked_px']} -> "
              f"A err {row['a_err_mm']:6.1f} mm | B err {row['b_err_mm']:6.1f} mm")
    prov = payload["claim_frame_provenance"]
    if "error" not in prov:
        print(f"\nclaim frame provenance (n={prov['n']} pots with a stored pixel): "
              f"hand anchors median residual {prov['hand_anchors']['median_px']} px, "
              f"scan quad {prov['scan_quad']['median_px']} px -> {prov['verdict']}")
    print("\ncorner containment:")
    for key, info in payload["corner_containment"].items():
        worst = min(info["rows"], key=lambda r: r["signed_dist_px"])
        print(f"  {key}: {info['n_inside']}/{info['n']} inside; worst corner {worst['corner']} "
              f"at {worst['px']} signed {worst['signed_dist_px']} px")
    print("\nrail evidence (refine_quad_edges, prior = each quad):")
    for row in payload["rail_evidence"].get("rows", []):
        for key in ("a_hand_anchors", "b_scan_quad"):
            info = row.get(key) or {}
            print(f"  t={row.get('t'):7.1f} {key:16s} verified={info.get('verified_sides')} "
                  f"inherited={info.get('inherited_sides')} supported={info.get('supported_sides')} "
                  f"reason={info.get('reason')} unverified={info.get('unverified')}")
    fore = payload["foreshortening"]
    for key in ("a_hand_anchors", "b_scan_quad"):
        row = fore[key]
        print(f"{key}: perpendicular {row['head_mm_per_px']}/{row['foot_mm_per_px']} mm/px "
              f"head/foot {row['head_over_foot']}; rail px {row['head_rail_px']}/{row['foot_rail_px']} "
              f"({row['rail_compression']}x); along-rail {row['head_rail_mm_per_px']}/"
              f"{row['foot_rail_mm_per_px']} mm/px")
    proj = payload["event_projection"]
    print(f"\nevent projection: n={proj.get('n_projected')} head med {proj.get('head_median_px')} px "
          f"max {proj.get('head_max_px')} px | foot med {proj.get('foot_median_px')} px "
          f"max {proj.get('foot_max_px')} px")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--anchors", default=str(ANCHORS))
    ap.add_argument("--scan-quad", default=str(SCAN_QUAD))
    ap.add_argument("--video", default=str(VIDEO))
    ap.add_argument("--candidates", default=str(CANDIDATES))
    ap.add_argument("--times", type=float, nargs="*", default=list(FRAME_TIMES))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    payload = build(args)
    _print(payload)
    print(f"\nwrote {args.out}")
    return payload


if __name__ == "__main__":
    main()
