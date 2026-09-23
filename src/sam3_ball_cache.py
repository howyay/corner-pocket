"""Targeted, cached SAM3 ball frames -- bounded spend, reusable results.

SAM3 is the only detector in this repo that sees a whole rack (10 balls on the
cloth where the classical colour census holds 1-3), but on this machine it costs
~45 s per frame on CPU after an ~86 s model load, so it cannot be run over a
30-minute VOD.  This tool runs it on a *bounded, named* list of timestamps --
the bracketing frames of the candidates that matter -- appends the results to
``out/scan30/sam3_census.json`` (gitignored, written after every frame so an
interrupted run is still usable) and reuses anything already cached there or in
the app's own ``out/scan30/sam3_results.json``.

The stored row keeps the app's schema (``score``/``img``/``r``/``table_mm``) and
adds the colour sampled at the detection, so the fused census does not have to
re-decode the frame later.  ``--budget-s`` is a hard wall-clock stop: frames
are attempted in the order given, and the run reports exactly which timestamp
each second went to.

    PYTHONPATH=. .venv/bin/python src/sam3_ball_cache.py \
        --times 26.25,26.75,27.25 --budget-s 2400
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ball_census import classify_ball_color  # noqa: E402
from src.table_detect import detect_table  # noqa: E402

APP_CACHE = "out/scan30/sam3_results.json"      # the app's own 56 frames: read-only
OWN_CACHE = "out/scan30/sam3_census.json"       # added by this tool: written
MIN_SCORE = 0.62
MIN_AREA, MAX_AREA = 60, 9000
MIN_R, MAX_R = 4.0, 60.0


def load_cache(path) -> dict:
    """Frames already measured, keyed by rounded time (both cache files)."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return {}
    frames = data.get("frames") if isinstance(data, dict) and "frames" in data else data
    if not isinstance(frames, dict):
        return {}
    return {round(float(key), 1): value for key, value in frames.items()}


def load_costs(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return {}
    return data.get("cost", {}) if isinstance(data, dict) else {}


def save_cache(path, frames: dict, costs: dict, video: str, filters: dict | None = None) -> None:
    """Write the cache; ``filters`` records which cloth geometry kept each frame.

    A frame measured before the reference-quad fix cannot be told from one
    measured after it by its ball list alone, so the filter that produced it is
    stored next to it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": 1, "generated_by": "src/sam3_ball_cache.py", "video": video,
        "note": "targeted SAM3 ball frames; read by src.eval_events via src.ball_census",
        "cost": costs,
        "filter": dict(filters or {}),
        "frames": {f"{t:.1f}": frames[t] for t in sorted(frames)},
    }, indent=1))


def load_filters(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return {}
    return data.get("filter", {}) if isinstance(data, dict) else {}


def cloth_mask(bgr, reference=None, corners_path="out/scan30/corners.json"):
    """The cloth a ball is allowed to sit on, and which geometry decided it.

    ``detect_table`` estimates the cloth per frame, and that estimate collapses
    onto the wall panels or balloons over the whole frame when a player stands at
    the table; filtering balls through it zeroed a frame that held ten of them
    (t=487.3 of the reference VOD).  The verified reference geometry -- the
    calibration segment's human quad, or the hand anchors -- is stable, so it is
    the filter; the per-frame mask stays a *reported* signal (see
    ``src.sam3_frame_audit``), never a silent veto.  The per-frame mask is only
    used when no reference geometry exists at all, and the caller is told so.
    """
    if reference is None:
        reference = reference_quad(corners_path)
    if reference is not None:
        mask = np.zeros(bgr.shape[:2], np.uint8)
        cv2.fillPoly(mask, [np.round(np.asarray(reference, np.float32)).astype(np.int32)], 1)
        return mask > 0, "reference_quad"
    return detect_table(bgr)["mask"] > 0, "frame_mask"


def detect_frame(video, time_s, model_proc, corners_path, progress=lambda text: None,
                 reference=None) -> tuple:
    """SAM3 balls on one frame; returns ``(balls, filter_used)``.

    The filter is the verified reference quad, not the per-frame table mask: a
    mask failure must never silently zero the census (see ``cloth_mask``).
    """
    from PIL import Image

    from src.pipeline import ball_center, homography_to_canonical

    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(time_s) * 1000.0)
    ok, bgr = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"no frame at t={time_s}")
    fixed = np.array(json.loads(Path(corners_path).read_text())["corners"], dtype=np.float32)
    H = homography_to_canonical(fixed)
    cloth, filter_used = cloth_mask(bgr, reference=reference, corners_path=corners_path)
    state = model_proc.set_image(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
    state = model_proc.set_text_prompt("billiard ball", state)
    masks = state["masks"].cpu().float().numpy()
    scores = state["scores"].cpu().float().numpy()
    balls = []
    for index in range(len(scores)):
        if scores[index] < MIN_SCORE:
            continue
        mask = np.squeeze(masks[index])
        area = float(mask.sum())
        if area < MIN_AREA or area > MAX_AREA:
            continue
        cx, cy, radius = ball_center(mask)
        if not (0 <= int(cy) < cloth.shape[0] and 0 <= int(cx) < cloth.shape[1]):
            continue
        if not cloth[int(cy), int(cx)]:
            continue
        if radius < MIN_R or radius > MAX_R:
            continue
        point = H @ np.array([cx, cy, 1.0])
        balls.append({
            "score": float(scores[index]),
            "img": [round(cx, 1), round(cy, 1)],
            "r": round(radius, 1),
            "table_mm": [round(point[0] / point[2], 1), round(point[1] / point[2], 1)],
            # Sampled from the ball's core: the disc must not be swamped by the
            # cloth around it, or every ball comes back "unknown".
            "color": classify_ball_color(bgr, cx, cy, max(radius * 0.5, 2.5)),
        })
    balls.sort(key=lambda ball: ball["table_mm"])
    progress(f"t={time_s}: {len(balls)} balls ({filter_used})")
    return balls, filter_used


def reference_quad(corners_path="out/scan30/corners.json", dataset="vod30"):
    """The verified cloth quad SAM3's balls are allowed to sit on.

    The per-frame ``detect_table`` mask is estimated from the frame and collapses
    (or balloons onto the wall panels) under occlusion; the reference quad is
    human-clicked geometry and is stable.  Preference: the calibration segment,
    then the hand anchors, then the scan's own naive corners as a last resort.
    """
    try:
        from src.calib_segments import load as load_segments
        segments = load_segments(dataset)
        if segments is not None:
            for segment in segments.segments:
                if segment.source == "human_anchors":
                    return np.array(segment.quad, np.float32)
    except Exception:
        pass
    for path, key in ((f"out/pid_anchors_{dataset}.json", "anchors"), (corners_path, "corners")):
        try:
            data = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        if key == "anchors":
            first = next(iter(data.get("anchors", {}).values()), None)
            if first:
                return np.array(first[:4], np.float32)
        elif data.get("corners"):
            return np.array(data["corners"], np.float32)
    return None


def diagnose_frame(video, time_s, model_proc, corners_path, reference=None,
                   progress=lambda text: None) -> dict:
    """Run SAM3 on one frame and report every filter stage.

    A zero-ball frame is only evidence of an empty cloth if SAM3 really found
    nothing: if it found ten balls and the per-frame ``detect_table`` mask threw
    them away, the zero is a filter failure, not an observation.  This returns
    the counts at each stage (raw -> score -> area -> radius -> cloth) under both
    cloth tests, so the two causes are distinguishable without guessing.
    """
    from PIL import Image

    from src.pipeline import ball_center

    if reference is None:
        reference = reference_quad(corners_path)
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(time_s) * 1000.0)
    ok, bgr = cap.read()
    decoded_t = round(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0, 3)
    cap.release()
    if not ok:
        return {"t": time_s, "ok": False}
    table = detect_table(bgr)
    cloth = table["mask"] > 0
    reference_mask = None
    if reference is not None and np.asarray(reference).shape == (4, 2):
        reference_mask = np.zeros(cloth.shape, np.uint8)
        cv2.fillPoly(reference_mask, [np.round(np.asarray(reference, np.float32)).astype(np.int32)], 1)
        reference_mask = reference_mask > 0
    state = model_proc.set_image(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
    state = model_proc.set_text_prompt("billiard ball", state)
    masks = state["masks"].cpu().float().numpy()
    scores = state["scores"].cpu().float().numpy()
    stages = {"raw": int(len(scores)), "score": 0, "area": 0, "radius": 0,
              "cloth_frame_mask": 0, "cloth_reference": 0}
    for index in range(len(scores)):
        if scores[index] < MIN_SCORE:
            continue
        stages["score"] += 1
        mask = np.squeeze(masks[index])
        area = float(mask.sum())
        if area < MIN_AREA or area > MAX_AREA:
            continue
        stages["area"] += 1
        cx, cy, radius = ball_center(mask)
        if radius < MIN_R or radius > MAX_R:
            continue
        stages["radius"] += 1
        inside = 0 <= int(cy) < cloth.shape[0] and 0 <= int(cx) < cloth.shape[1]
        if inside and cloth[int(cy), int(cx)]:
            stages["cloth_frame_mask"] += 1
        if reference_mask is not None and inside and reference_mask[int(cy), int(cx)]:
            stages["cloth_reference"] += 1
    if stages["raw"] == 0:
        verdict = "no detections at all"
    elif stages["radius"] and not stages["cloth_frame_mask"]:
        verdict = "mask filtered the balls"
    elif stages["cloth_frame_mask"]:
        verdict = "balls kept"
    else:
        verdict = "nothing reached the cloth test"
    progress(f"t={time_s}: {verdict} {stages}")
    return {"t": round(float(time_s), 3), "ok": True, "decoded_t": decoded_t,
            "cloth_area": int(cloth.sum()), "reference_area": int(reference_mask.sum())
            if reference_mask is not None else None,
            "scores": [round(float(s), 3) for s in sorted(scores)[::-1][:12]],
            "stages": stages, "verdict": verdict}


def pending_times(times, cached=(), refetch=()) -> list:
    """Which timestamps still need measuring: uncached ones plus ``refetch``.

    A frame measured through a filter that has since been shown to zero real
    balls is not evidence, so it goes back on the list rather than being trusted.
    """
    cached = {f"{round(float(t), 1):.1f}" for t in cached}
    again = {f"{round(float(t), 1):.1f}" for t in refetch}
    out = []
    for t in times:
        key = f"{round(float(t), 1):.1f}"
        if key not in cached or key in again:
            out.append(round(float(t), 1))
    return out


def run(video, times, out_path=OWN_CACHE, app_path=APP_CACHE, corners_path="out/scan30/corners.json",
        budget_s=2400.0, checkpoint="data/sam3.safetensors", progress=print, refetch=()) -> dict:
    """Run the pending timestamps in order under a wall-clock budget.

    ``refetch`` names timestamps to re-measure even though a cache holds them:
    a frame measured through a filter that has since been shown to zero real
    balls is not evidence, so it has to be bought again rather than trusted.
    """
    app_frames = load_cache(app_path)
    own_frames = load_cache(out_path)
    frames = {**app_frames, **own_frames}
    costs = load_costs(out_path)
    filters = load_filters(out_path)
    again = {round(float(t), 1) for t in refetch}
    pending = pending_times(times, cached=frames, refetch=again)
    report = {"requested": len(list(times)), "already_cached": len(list(times)) - len(pending),
              "pending": len(pending), "refetch": sorted(again), "done": [],
              "skipped_budget": [], "load_s": None, "filter": None, "seconds": 0.0}
    if not pending:
        progress("nothing to do: every requested frame is cached")
        return report

    started = time.time()
    from src.sam3_cpu import load_sam3_image_model, make_processor

    import torch
    torch.set_num_threads(8)
    reference = reference_quad(corners_path)
    if reference is None:
        progress("no reference geometry found: falling back to the per-frame cloth mask, "
                 "which is known to zero frames under occlusion")
    model = load_sam3_image_model(str(ROOT / checkpoint))
    model.float()
    processor = make_processor(model)
    report["load_s"] = round(time.time() - started, 1)
    progress(f"model loaded in {report['load_s']}s; {len(pending)} frames pending; "
             f"budget {budget_s:.0f}s")

    try:
        for time_s in pending:
            spent = time.time() - started
            if spent >= budget_s:
                report["skipped_budget"].append(time_s)
                progress(f"budget reached ({spent:.0f}s) -- {time_s} skipped")
                continue
            frame_started = time.time()
            try:
                own_frames[time_s], filter_used = detect_frame(
                    video, time_s, processor, corners_path,
                    progress=lambda text: progress(f"  {text}"), reference=reference)
            except Exception as error:                      # keep the loop alive
                progress(f"  t={time_s} failed: {error}")
                continue
            filters[f"{time_s:.1f}"] = filter_used
            report["filter"] = filter_used
            costs[f"{time_s:.1f}"] = round(time.time() - frame_started, 1)
            # Written after every frame: an interrupted run keeps what it paid for.
            save_cache(out_path, own_frames, costs, str(video), filters)
            report["done"].append({"t": time_s, "seconds": costs[f"{time_s:.1f}"],
                                   "filter": filter_used})
            progress(f"  cached t={time_s} in {costs[f'{time_s:.1f}']}s ({filter_used}) "
                     f"({len(report['done'])}/{len(pending)}, {time.time() - started:.0f}s wall)")
    finally:
        report["seconds"] = round(time.time() - started, 1)
        save_cache(out_path, own_frames, costs, str(video), filters)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", default="data/vod_30min_260815.mp4")
    ap.add_argument("--times", default="", help="comma-separated timestamps, in priority order")
    ap.add_argument("--times-file", default=None,
                    help="JSON list (or one timestamp per line); overrides --times")
    ap.add_argument("--out", default=OWN_CACHE)
    ap.add_argument("--app-cache", default=APP_CACHE)
    ap.add_argument("--corners", default="out/scan30/corners.json")
    ap.add_argument("--budget-s", type=float, default=2400.0)
    args = ap.parse_args()

    if args.times_file:
        text = Path(args.times_file).read_text().strip()
        times = (json.loads(text) if text.startswith("[")
                 else [float(line) for line in text.split() if line.strip()])
    else:
        times = [float(part) for part in args.times.split(",") if part.strip()]
    report = run(args.video, times, out_path=args.out, app_path=args.app_cache,
                 corners_path=args.corners, budget_s=args.budget_s)
    print(json.dumps(report["done"], indent=1), flush=True)
    total = sum(item["seconds"] for item in report["done"])
    print(f"done {len(report['done'])} frames in {report['seconds']}s wall "
          f"({total:.0f}s in SAM3, load {report['load_s']}s); "
          f"cached already {report['already_cached']}, skipped {len(report['skipped_budget'])} "
          f"-> {args.out}")


if __name__ == "__main__":
    main()
