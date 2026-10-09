#!/usr/bin/env python3
"""Measure a table-boundary detector against the saved references.

Every detector is scored against **both** vod30 references and the text output
marks which one is authoritative, because the two answer different questions:

* ``app-anchors`` - ``out/pid_anchors_vod30.json``, the first four of the six
  hand-placed pocket anchors.  This is the geometry the viewer clears the quad
  against (``annotator/app.js`` ``validateCloth``, 40 px) and the geometry the app
  path now searches around.  **Authoritative**: it is hand-placed ground truth, and
  it tracks the visible cloth boundary within 6-13 px.  A detector seeded from it
  scores a *drift* number, so a small value is not by itself independence.
* ``corners30-v2`` - ``out/corners_30min_v2.json``, the 300-frame temporal median of
  strip-refined quads.  **Circular, measured-bad**: it is refinement-derived (52-90
  px off the visible cloth on its left rail) and it used to be both the detector's
  search centre and the scoring reference, so the old "median 4.38 px, accept 100 %"
  headline measured how far the refinement moved from its own seed
  (docs/app-path-refusal.md).  It is printed for continuity only; do not quote it as
  accuracy.

No detector mode seeds from ``prior_for`` any more: seeds come from
``src.frame_inference.app_prior_for`` (the hand anchors) and
:func:`assert_seed_is_measurable` fails loudly if a seed ever comes from a reference
that is not authoritative - a detector scored against its own seed can only report
itself.

References
----------
vod30 (1280x720, t=0..1806): the anchors above (authoritative) + ``corners30-v2``
(circular).  highlight (1920x1080): ``fixed-corners`` - ``out/fixed_corners.json``,
the dataset's saved reference (authoritative for this dataset; the viewer has no
clearance reference for highlight and paints the quad unverified).

Usage
-----
    PYTHONPATH=. .venv/bin/python -m src.eval_table_detect --detector naive
    PYTHONPATH=. .venv/bin/python -m src.eval_table_detect --detector refined
    PYTHONPATH=. .venv/bin/python -m src.eval_table_detect --detector app
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.datasets import media_path  # noqa: E402

OUT_DIR = ROOT / "out" / "table-detect-eval"
VOD30 = media_path(ROOT, "vod30")
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
    """Return {dataset: [{name, corners, width, height, note, source_file, quality}]}.

    ``quality`` is ``authoritative`` (hand-placed or the dataset's own saved
    reference: what a detector is allowed to be judged by) or ``circular`` (a
    refinement-derived reference that was also a detector seed).  A detector must
    never be seeded from a ``circular`` file - see :func:`assert_seed_is_measurable`.
    """
    anchors = json.load(open(ANCHORS))["anchors"]
    refs = {"vod30": [], "highlight": []}
    for key in sorted(anchors, key=float):
        pts = _order(anchors[key][:4])
        refs["vod30"].append({
            "name": f"app-anchors@{key}s", "corners": pts,
            "width": 1280, "height": 720, "anchors_key": key,
            "source_file": str(ANCHORS), "quality": "authoritative",
            "note": "first 4 of 6 hand-placed pocket anchors: the viewer's clearance "
                    "geometry and the app path's seed; hand-placed ground truth",
        })
    v2 = json.load(open(CORNERS_V2))
    refs["vod30"].append({
        "name": "corners30-v2", "corners": _order(v2["corners"]),
        "width": 1280, "height": 720,
        "source_file": str(CORNERS_V2), "quality": "circular",
        "note": (f"{v2.get('method', 'strip-refine')}; "
                 f"{v2.get('frames_accepted')}/{v2.get('frames_total')} frames accepted. "
                 "CIRCULAR: refinement-derived, 52-90 px off the visible cloth on its left "
                 "rail, and it used to be the detector's seed as well as the scoring "
                 "reference - printed for continuity, never as accuracy"),
    })
    fixed = json.load(open(FIXED_CORNERS))["corners"]
    refs["highlight"].append({
        "name": "fixed-corners", "corners": _order(fixed),
        "width": 1920, "height": 1080,
        "source_file": str(FIXED_CORNERS), "quality": "authoritative",
        "note": "highlight's saved reference (per docs/state.md 2.0 px median vs the cloth quad); "
                "the viewer has no clearance reference for this dataset and paints unverified",
    })
    return refs


def authoritative_reference(refs):
    """Name of the one reference a detector may be judged by, or None."""
    return next((ref["name"] for ref in refs if ref["quality"] == "authoritative"), None)


def assert_seed_is_measurable(dataset, seed_file, refs):
    """Refuse to score a detector that was seeded from a non-authoritative reference.

    Seeding a detector from a file that is also a scoring reference turns the score
    into a self-measurement; that is exactly how vod30's "median 4.38 px, accept
    100 %" was produced.  Called by every detector mode, so a future mode that
    re-introduces ``prior_for`` as a seed fails loudly instead of reporting itself.
    """
    scored = {ref["source_file"] for ref in refs if ref["quality"] != "authoritative"}
    if seed_file is not None and str(seed_file) in scored:
        raise AssertionError(
            f"refusing to score {dataset}: the detector was seeded from {seed_file}, "
            "which is not an authoritative reference (a detector scored against its "
            "own seed measures only itself - docs/app-path-refusal.md)")


# -- detectors ----------------------------------------------------------------

def _detector_naive(frame, dataset, t, refs):
    """Baseline: src.table_detect.detect_table as it ships today. No seed."""
    from src.table_detect import detect_table
    assert_seed_is_measurable(dataset, None, refs)
    t0 = time.perf_counter()
    res = detect_table(frame)
    return res["corners"], {"source": "naive", "confidence": None, "reason": None,
                            "ms": (time.perf_counter() - t0) * 1000.0,
                            "refined": False, "seed_file": None}


def _detector_refined(frame, dataset, t, refs):
    """The refined detector at full resolution, seeded exactly as the app seeds it."""
    from src.frame_inference import app_prior_for, app_prior_source, detect_table_for_frame
    seed_file = app_prior_source(dataset)
    assert_seed_is_measurable(dataset, seed_file, refs)
    t0 = time.perf_counter()
    res = detect_table_for_frame(frame, dataset=dataset, prior=app_prior_for(dataset))
    res = dict(res)
    res["ms"] = (time.perf_counter() - t0) * 1000.0
    res["seed_file"] = None if seed_file is None else str(seed_file)
    return res["corners"], res


def _detector_app(frame, dataset, t, refs):
    """The viewer's own path: detection on the 2x-downscaled copy, corners scaled back.

    ``annotator/unified_server.Backend._unified_detection`` resizes to w//2 x h//2,
    halves the seed, runs ``detect_table_for_frame`` and multiplies the corners by
    2.  Reproduced here so the harness and the browser cannot disagree by
    construction; the seed comes from the same resolver they both use.
    """
    import cv2
    from src.frame_inference import app_prior_for, app_prior_source, detect_table_for_frame
    from src.table_detect import detect_table
    seed_file = app_prior_source(dataset)
    assert_seed_is_measurable(dataset, seed_file, refs)
    scale = 2.0
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    prior = app_prior_for(dataset)
    t0 = time.perf_counter()
    refined = detect_table_for_frame(small, prior=None if prior is None else prior / scale)
    table = detect_table(small) if refined.get("corners") is None else refined
    ms = (time.perf_counter() - t0) * 1000.0
    corners = None if table.get("corners") is None else np.asarray(table["corners"], np.float32) * scale
    info = dict(table)
    info.update({"ms": ms, "seed_file": None if seed_file is None else str(seed_file),
                 "refined": refined.get("corners") is not None,
                 "source": ("refined_saved_prior" if refined.get("corners") is not None
                            else "naive_fallback")})
    return corners, info


DETECTORS = {"naive": _detector_naive, "refined": _detector_refined, "app": _detector_app}

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
            corners, info = detector(frame, dataset, t, refs)
        except Exception as exc:  # a detector crash is a row, not an aborted run
            corners, info = None, {"source": "crash", "confidence": None,
                                   "reason": f"crash: {exc}", "ms": 0.0}
        row.update({k: v for k, v in info.items()
                    if k not in ("corners", "mask", "debug") and not isinstance(v, np.ndarray)})
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
               "authoritative_reference": authoritative_reference(refs),
               "seeded_from": next((r["seed_file"] for r in rows if r.get("seed_file")), None),
               "references": {}}
    ms = [r.get("ms") for r in rows if r.get("ms") is not None]
    if ms:
        summary["ms_per_frame"] = _stats(ms)
    conf = [r["confidence"] for r in rows if r.get("confidence") is not None]
    if conf:
        summary["confidence"] = _stats(conf)
    sources = {}
    for r in rows:
        if r.get("source"):
            sources[r["source"]] = sources.get(r["source"], 0) + 1
    summary["sources"] = sources
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
            "quality": ref["quality"],
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
             f"frames={summary['frames']} wall={summary['wall_seconds']}s "
             f"seed={summary.get('seeded_from') or 'none (naive)'}"]
    if "ms_per_frame" in summary:
        m = summary["ms_per_frame"]
        lines.append(f"  ms/frame: median {m['median']} p90 {m['p90']} max {m['max']}")
    if summary["refusal_reasons"]:
        lines.append(f"  refusals: {summary['refusal_reasons']}")
    if summary.get("sources"):
        lines.append(f"  sources: {summary['sources']}")
    if summary.get("confidence"):
        c = summary["confidence"]
        lines.append(f"  confidence: median {c['median']} p90 {c['p90']} min {c['min']}")
    # The authoritative reference is printed first and named as the headline: it is
    # the one number a detector may be quoted on.  Everything else is labelled.
    order = sorted(summary["references"], key=lambda n: summary["references"][n]["quality"] != "authoritative")
    for name in order:
        ref = summary["references"][name]
        e = ref["error_px"]
        mark = ("[authoritative]" if ref["quality"] == "authoritative"
                else "[circular - refinement-derived and once the detector's seed: do not quote]")
        lines.append(f"  vs {name} {mark}: mean-px median {e['median'] if e else None} "
                     f"p90 {e['p90'] if e else None} max {e['max'] if e else None} "
                     f"accept {ref['accept_rate'] * 100:.1f}% states={ref['states']}")
    headline = summary["references"].get(summary.get("authoritative_reference") or "")
    if headline and headline["error_px"]:
        lines.append(f"  HEADLINE vs {summary['authoritative_reference']}: median "
                     f"{headline['error_px']['median']} px, p90 {headline['error_px']['p90']} px, "
                     f"accept@40 {headline['accept_rate'] * 100:.1f}%")
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
              "authoritative_reference_by_dataset": {
                  dataset: authoritative_reference(refs[dataset]) for dataset in refs},
              "reference_note": (
                  "Each detector is scored against BOTH vod30 references. The hand anchors "
                  "(out/pid_anchors_vod30.json) are authoritative: hand-placed ground truth, "
                  "the geometry the viewer clears the quad against and the geometry the app "
                  "path is seeded from, tracking the visible cloth boundary within 6-13 px. "
                  "corners30-v2 (out/corners_30min_v2.json) is circular and measured-bad: it is "
                  "refinement-derived, 52-90 px off the visible cloth on its left rail, and it "
                  "used to be the detector's seed as well as the scoring reference - the old "
                  "'median 4.38 px / 100 % accept' headline measured how far the refinement "
                  "moved from its own seed. Quote the authoritative number only. "
                  "No detector mode seeds from prior_for any more; assert_seed_is_measurable "
                  "fails loudly if a seed ever comes from a non-authoritative reference. "
                  "See docs/app-path-refusal.md."),
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
