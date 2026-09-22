#!/usr/bin/env python3
"""Measure a table-boundary detector against the saved references.

The Vision stage refuses the model quad when its mean corner distance to the
dataset's saved corners exceeds the app tolerance (annotator/app.js
CLOTH_TOLERANCE_PX = 40, mean over the 4 best-aligned corners).  This harness
reproduces that number offline over sampled frames of both VODs so a detector
change can be scored before it reaches the app.

References
----------
vod30 (1280x720, t=0..1806):
  * ``app-anchors`` - ``out/pid_anchors_vod30.json`` at t=70, the first four of
    the six hand anchors (head-left, head-right, foot-right, foot-left).  This
    is exactly what the app compares against, so it is the app-facing bar.
    A search over neighbouring anchor times is reported as a sensitivity check.
  * ``corners30-v2`` - ``out/corners_30min_v2.json``, the 300-frame temporal
    median of strip-refined quads (163/300 accepted, 3.95 px median jitter).
highlight (1920x1080):
  * ``fixed-corners`` - ``out/fixed_corners.json``.

CIRCULARITY: ``corners30-v2`` was produced by a strip-refinement method, and
this harness scores a strip-refinement detector against it.  A refinement
detector will look better against a refined reference than it deserves.  The
anchor reference has the opposite problem: the anchors are pocket-jaw centres,
not cloth corners, so they sit inside the cloth boundary (measured ~44 px mean
at t=70) and no cloth-boundary detector can match them.  Both numbers are
printed and neither is quietly preferred.

Usage
-----
    PYTHONPATH=. .venv/bin/python -m src.eval_table_detect --detector naive
    PYTHONPATH=. .venv/bin/python -m src.eval_table_detect --detector app
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out" / "table-detect-eval"
VOD30 = ROOT / "data" / "vod_30min_260815.mp4"
HIGHLIGHT = ROOT / "data" / "vod_highlight.mp4"
ANCHORS = ROOT / "out" / "pid_anchors_vod30.json"
CORNERS_V2 = ROOT / "out" / "corners_30min_v2.json"
FIXED_CORNERS = ROOT / "out" / "fixed_corners.json"
TOLERANCE_PX = 40.0


# -- references ---------------------------------------------------------------

def _order(points) -> np.ndarray:
    from src.table_detect import _order_corners
    return _order_corners(np.asarray(points, np.float32))


def load_references() -> dict:
    """Return {dataset: [(name, corners(4,2), width, height, note), ...]}."""
    anchors = json.load(open(ANCHORS))["anchors"]
    refs = {"vod30": [], "highlight": []}
    for key in sorted(anchors, key=float):
        pts = _order(anchors[key][:4])
        refs["vod30"].append({
            "name": f"app-anchors@{key}s", "corners": pts,
            "width": 1280, "height": 720, "anchors_key": key,
            "note": "first 4 of 6 hand pocket anchors: the app's quad check",
        })
    v2 = json.load(open(CORNERS_V2))
    refs["vod30"].append({
        "name": "corners30-v2", "corners": _order(v2["corners"]),
        "width": 1280, "height": 720,
        "note": (f"{v2.get('method', 'strip-refine')}; "
                 f"{v2.get('frames_accepted')}/{v2.get('frames_total')} frames accepted; "
                 "CIRCULAR for any refinement detector"),
    })
    fixed = json.load(open(FIXED_CORNERS))["corners"]
    refs["highlight"].append({
        "name": "fixed-corners", "corners": _order(fixed),
        "width": 1920, "height": 1080,
        "note": "highlight reference; per docs/state.md 2.0 px median vs the cloth quad",
    })
    return refs


# -- metrics (exactly the app's rule) -----------------------------------------

def quad_distance(quad, reference):
    """Best of the four cyclic alignments; mean and max over 4 corners."""
    q = np.asarray(quad, np.float64).reshape(4, 2)
    r = np.asarray(reference, np.float64).reshape(4, 2)
    best = None
    for shift in range(4):
        d = np.linalg.norm(r - np.roll(q, -shift, axis=0), axis=1)
        mean = float(d.mean())
        if best is None or mean < best["mean"]:
            best = {"mean": mean, "max": float(d.max()), "shift": shift,
                    "distances": [round(float(v), 1) for v in d]}
    return best


def quad_sanity(points, width, height):
    """Same rejection rule as annotator/app.js quadSanity."""
    if points is None:
        return "malformed"
    p = np.asarray(points, np.float64)
    if p.shape != (4, 2) or not np.isfinite(p).all():
        return "malformed"
    for x, y in p:
        if x < -2 or y < -2 or x > width + 2 or y > height + 2:
            return "outside frame"
    for i in range(4):
        if np.hypot(*(p[i] - p[(i + 1) % 4])) < 8:
            return "degenerate corner"
    def _cross(a, b):  # numpy>=2 dropped 2-D np.cross
        return float(a[0] * b[1] - a[1] * b[0])
    area = (abs(_cross(p[1] - p[0], p[3] - p[0]))
            + abs(_cross(p[3] - p[0], p[2] - p[0]))) / 2.0
    frac = area / (width * height)
    return None if 0.02 <= frac <= 0.9 else f"implausible area {frac * 100:.1f}%"


# -- detectors ----------------------------------------------------------------

def _detector_naive(frame):
    """Baseline: src.table_detect.detect_table as it ships today."""
    from src.table_detect import detect_table
    t0 = time.perf_counter()
    res = detect_table(frame)
    return res["corners"], {"source": "naive", "confidence": None, "reason": None,
                            "ms": (time.perf_counter() - t0) * 1000.0,
                            "refined": False}


def _detector_app(frame, dataset, t):
    """Improved path: src.table_refine.detect_table_refined with a segment prior."""
    from src.table_refine import detect_table_refined, prior_for
    prior = prior_for(dataset, t)
    t0 = time.perf_counter()
    res = detect_table_refined(frame, prior=prior)
    res["ms"] = (time.perf_counter() - t0) * 1000.0
    return res["corners"], res


DETECTORS = {"naive": _detector_naive, "app": _detector_app}


# -- sampling -----------------------------------------------------------------

def sample_times(dataset, n):
    if dataset == "vod30":
        span = 1806.8
    else:
        span = 377.0
    if n <= 1:
        return [span / 2.0]
    return [round(span * i / (n - 1), 2) for i in range(n)]


def read_frame(cap, t):
    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
    ok, frame = cap.read()
    return frame if ok else None


def evaluate(detector, dataset, n_frames, refs, video):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    rows = []
    for t in sample_times(dataset, n_frames):
        frame = read_frame(cap, t)
        if frame is None:
            rows.append({"t": t, "read": False})
            continue
        h, w = frame.shape[:2]
        row = {"t": t, "read": True, "width": w, "height": h}
        try:
            if detector is _detector_app:
                corners, info = detector(frame, dataset, t)
            else:
                corners, info = detector(frame)
        except Exception as exc:  # a detector crash is a row, not an aborted run
            corners, info = None, {"source": "crash", "confidence": None,
                                   "reason": f"crash: {exc}", "ms": 0.0}
        row.update({k: v for k, v in info.items() if k != "corners"})
        row["sanity"] = quad_sanity(corners, w, h)
        if corners is not None:
            row["corners"] = [[round(float(x), 1), round(float(y), 1)] for x, y in corners]
        verdicts = {}
        for ref in refs:
            entry = {"state": "none", "mean": None}
            if corners is None:
                entry = {"state": "no detection", "mean": None}
            elif row["sanity"]:
                entry = {"state": "invalid geometry", "mean": None,
                         "detail": row["sanity"]}
            elif w != ref["width"] or h != ref["height"]:
                entry = {"state": "size mismatch", "mean": None}
            else:
                fit = quad_distance(corners, ref["corners"])
                entry = {"state": "ok" if fit["mean"] <= TOLERANCE_PX else "off",
                         "mean": round(fit["mean"], 2), "max": round(fit["max"], 2),
                         "shift": fit["shift"], "distances": fit["distances"]}
            verdicts[ref["name"]] = entry
        row["references"] = verdicts
        rows.append(row)
    cap.release()
    return rows


def _stats(values):
    if not values:
        return None
    a = np.asarray(values, np.float64)
    return {"n": int(a.size), "median": round(float(np.median(a)), 2),
            "p90": round(float(np.percentile(a, 90)), 2),
            "max": round(float(a.max()), 2), "min": round(float(a.min()), 2)}


def summarise(rows, refs, detector_name, dataset, wall_s):
    summary = {"detector": detector_name, "dataset": dataset, "frames": len(rows),
               "wall_seconds": round(wall_s, 1), "tolerance_px": TOLERANCE_PX,
               "references": {}}
    ms = [r.get("ms") for r in rows if r.get("ms") is not None]
    if ms:
        summary["ms_per_frame"] = _stats(ms)
    refused = {}
    for r in rows:
        if r.get("reason"):
            refused[r["reason"]] = refused.get(r["reason"], 0) + 1
    summary["refusal_reasons"] = refused
    for ref in refs:
        name = ref["name"]
        entries = [r["references"][name] for r in rows if "references" in r]
        means = [e["mean"] for e in entries if e.get("mean") is not None]
        states = {}
        for e in entries:
            states[e["state"]] = states.get(e["state"], 0) + 1
        usable = [e for e in entries if e["state"] in ("ok", "off")]
        worst = sorted(
            ({"t": r["t"], "mean": r["references"][name]["mean"],
              "max": r["references"][name].get("max"),
              "offsets": r["references"][name].get("distances"),
              "reason": r.get("reason"), "source": r.get("source")}
             for r in rows if "references" in r
             and r["references"][name].get("mean") is not None),
            key=lambda z: -z["mean"])[:10]
        summary["references"][name] = {
            "note": ref["note"], "reference_corners": [
                [round(float(x), 1), round(float(y), 1)] for x, y in ref["corners"]],
            "states": states, "error_px": _stats(means),
            "accept_rate": round(len([e for e in usable if e["state"] == "ok"]) / max(len(entries), 1), 4),
            "accept_rate_of_read": round(
                len([e for e in usable if e["state"] == "ok"]) / max(len([r for r in rows if r.get("read")]), 1), 4),
            "worst_frames": worst}
    return summary


def _table(summary):
    lines = [f"detector={summary['detector']} dataset={summary['dataset']} "
             f"frames={summary['frames']} wall={summary['wall_seconds']}s"]
    if "ms_per_frame" in summary:
        m = summary["ms_per_frame"]
        lines.append(f"  ms/frame: median {m['median']} p90 {m['p90']} max {m['max']}")
    if summary["refusal_reasons"]:
        lines.append(f"  refusals: {summary['refusal_reasons']}")
    for name, ref in summary["references"].items():
        e = ref["error_px"]
        lines.append(f"  vs {name}: mean-px median {e['median'] if e else None} "
                     f"p90 {e['p90'] if e else None} max {e['max'] if e else None} "
                     f"accept {ref['accept_rate'] * 100:.1f}% states={ref['states']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", default="naive", choices=sorted(DETECTORS))
    ap.add_argument("--tag", default=None, help="output stem (default: detector name)")
    ap.add_argument("--frames-vod30", type=int, default=45)
    ap.add_argument("--frames-highlight", type=int, default=21)
    args = ap.parse_args()
    tag = args.tag or args.detector
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    refs = load_references()
    detect = DETECTORS[args.detector]
    report = {"detector": args.detector, "tolerance_px": TOLERANCE_PX,
              "circularity_note": (
                  "corners30-v2 was produced by strip refinement and is scored here against a "
                  "strip-refinement detector: its error is optimistic. The anchor reference is "
                  "pocket-jaw geometry rather than cloth corners: no cloth-boundary detector can "
                  "match it (measured offset ~44 px mean at t=70)."),
              "datasets": {}}
    for dataset, video, n in (("vod30", VOD30, args.frames_vod30),
                              ("highlight", HIGHLIGHT, args.frames_highlight)):
        if not Path(video).is_file():
            report["datasets"][dataset] = {"error": f"missing video {video}"}
            continue
        t0 = time.perf_counter()
        rows = evaluate(detect, dataset, n, refs[dataset], video)
        wall = time.perf_counter() - t0
        summary = summarise(rows, refs[dataset], args.detector, dataset, wall)
        summary["rows"] = rows
        report["datasets"][dataset] = summary
    jpath = OUT_DIR / f"{tag}.json"
    jpath.write_text(json.dumps(report, indent=1))
    tables = []
    for dataset, summary in report["datasets"].items():
        if "error" in summary:
            tables.append(f"{dataset}: {summary['error']}")
        else:
            tables.append(_table(summary))
    tpath = OUT_DIR / f"{tag}.txt"
    tpath.write_text("\n\n".join(tables) + "\n")
    print("\n\n".join(tables))
    print(f"\nwrote {jpath}\nwrote {tpath}")


if __name__ == "__main__":
    main()
