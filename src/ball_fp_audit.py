"""Adjudicate the student's held-out false positives with a *third* measurement.

The problem this solves.  ``src/tiny_ball_net.py`` reports F1 0.927 on the frozen
held-out set, but its truth is SAM3, which is a **teacher, not ground truth**.  So
the 15 held-out detections with no label are ambiguous by construction: either the
student hallucinated a ball, or SAM3 missed a real one and the student found it.
Nothing in that report can tell the two apart, and asking a human to eyeball 15
crops is the wrong shape of answer.

The third measurement.  Every label in the caches was written with the production
score cut (0.62) already applied -- ``min(stored score) >= 0.6245`` across all 194
frames -- so a teacher instance the student found *below* 0.62 is simply absent
from the labels, not refuted by them.  This tool re-runs SAM3 on the disputed
frames with the processor's confidence floor lowered to 0.15, keeps **every**
instance it returns, and asks the only question that actually separates the two
stories:

    is there an SAM3 instance, inside the teacher's own ball gate, within
    ``CANDIDATE_RADIUS_PX`` of the disputed point, at a score the production
    cut (0.62) would have thrown away?

If yes, the label was never there because production deleted it -- the student is
recalling a ball the teacher saw and the pipeline discarded (``teacher_recall``).
If SAM3 at 0.20 has nothing there either, the student invented it
(``student_hallucination``).  An instance that fails the gate -- wrong area,
wrong radius, off the cloth -- is neither, and is reported as ``unresolved``
rather than being quietly rounded to one side.

**What this does and does not prove.**  The adjudicator is now independent of the
*student*, which is what the F1 number needed; it is still SAM3, so this is a
second opinion from the same family of evidence, not human ground truth.  A
``teacher_recall`` verdict means "the teacher saw it too", not "a human says a
ball is there".  The rendered crops under ``out/ball-fp-audit/`` exist so a human
can overturn any verdict in seconds -- the automated answer is the thing to
check, not the thing to trust.

**Cost.**  SAM3 is CPU-only on this box: ~70 s to load, ~30-45 s per frame, and it
returns every instance in one forward pass, so the four sweep thresholds are
free.  Only the frames that carry a false positive are run (~14), cached in
``out/ball-fp-audit/sam3_sweep.json`` and written after every frame, so an
interrupted run is still usable and a re-run costs nothing.  The false negatives
cost no SAM3 at all: their teacher instance and score are already in the labels.

Nothing here writes to the queue, the gates or any production artifact.  The
teacher caches are read-only inputs.

    PYTHONPATH=. .venv/bin/python src/ball_fp_audit.py cases
    PYTHONPATH=. .venv/bin/python src/ball_fp_audit.py sam3 --budget-s 1500
    PYTHONPATH=. .venv/bin/python src/ball_fp_audit.py verdicts
    PYTHONPATH=. .venv/bin/python src/ball_fp_audit.py crops
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = ROOT / "out" / "tiny_ball_probe"
AUDIT = ROOT / "out" / "ball-fp-audit"
BITMAP = PROBE / "960x540-scratch.pt"
REPORT = PROBE / "report_960x540.json"
CENSUS = ROOT / "out" / "scan30" / "sam3_census.json"
RESULTS = ROOT / "out" / "scan30" / "sam3_results.json"   # the app's own 56 frames

CASES_OUT = AUDIT / "cases.json"
SWEEP_OUT = AUDIT / "sam3_sweep.json"
VERDICTS_OUT = AUDIT / "verdicts.json"
TABLE_OUT = AUDIT / "verdicts.md"

# ------------------------------------------------------------------ constants --
# The production cut.  A teacher instance below this score was never stored, so a
# label missing here is production recall that was thrown away, not a refutation.
PRODUCTION_CUT = 0.62
# What the sweep reports.  0.20 is the floor the audit is willing to call a ball;
# everything above 0.62 is teacher recall that production already kept.
SWEEP_THRESHOLDS = (0.20, 0.35, 0.50, 0.62)
# The processor's own confidence floor.  It must sit *below* the lowest sweep
# threshold or the 0.20 row would be a clipped measurement rather than a real one.
SAM3_FLOOR = 0.15
# "within a small radius of the false positive" -- a real ball 10 px away is the
# same ball; a student peak this far from a teacher miss is the recall story.
CANDIDATE_RADIUS_PX = 10.0
# The match tolerance the held-out report itself used, so "recovered" means the
# same thing here as "true positive" there.
MATCH_TOL_PX = 6.0
# Sweep thresholds identical to the frozen report's 0.05 + 0.025 i grid, so the
# FN recovery counts line up with the precision/recall cost already measured.
FN_THRESHOLDS = tuple(round(0.05 + 0.025 * i, 3) for i in range(38))

# Mirrors of ``src.sam3_ball_cache``'s admission gate.  Copied rather than
# imported so this module stays importable without cv2/the table detector; a test
# asserts they have not drifted from the module that owns them.
BALL_MIN_AREA, BALL_MAX_AREA = 60, 9000
BALL_MIN_R, BALL_MAX_R = 4.0, 60.0
BALL_AREA_RANGE = (BALL_MIN_AREA, BALL_MAX_AREA)
BALL_R_RANGE = (BALL_MIN_R, BALL_MAX_R)


def _log(text: str) -> None:
    print(text, flush=True)


# ------------------------------------------------------------- pure decisions --

def instances_near(instances: list, x: float, y: float, radius: float) -> list:
    """``[(distance_px, instance), ...]`` within ``radius``, nearest first.

    The measurement is a *list* of candidates, not a yes/no, because a near-miss
    has to stay visible: an instance 9 px away at 0.58 is a different finding
    from one 1 px away at 0.58, and the report carries the offset so the reader
    can tell them apart.
    """
    rows = []
    for inst in instances or ():
        d = math.hypot(float(inst["x"]) - float(x), float(inst["y"]) - float(y))
        if d <= radius:
            rows.append((d, inst))
    rows.sort(key=lambda row: row[0])
    return rows


def admit(inst: dict) -> tuple:
    """``(admitted, reason)`` -- would ``sam3_ball_cache`` have stored this ball?

    The gate is the teacher's own definition of a ball (area, equivalent radius,
    on the cloth).  An instance that fails it is still *reported*, but it cannot
    by itself settle the case, because "SAM3 emitted a blob here" is not the same
    claim as "a billiard ball is here".
    """
    area = float(inst.get("area") or 0.0)
    if area < BALL_MIN_AREA:
        return False, "area_too_small"
    if area > BALL_MAX_AREA:
        return False, "area_too_large"
    radius = float(inst.get("r") or 0.0)
    if radius < BALL_MIN_R:
        return False, "radius_too_small"
    if radius > BALL_MAX_R:
        return False, "radius_too_large"
    if not inst.get("in_cloth", True):
        return False, "off_cloth"
    return True, "admitted"


def adjudicate_fp(case: dict, instances: list, radius: float = CANDIDATE_RADIUS_PX,
                  thresholds: tuple = SWEEP_THRESHOLDS,
                  production_cut: float = PRODUCTION_CUT) -> dict:
    """The three-way verdict for one student false positive.

    ``teacher_recall``   an admitted instance sits inside ``radius`` at a score
                         at least the lowest sweep threshold; the numbers say
                         whether it was below the production cut (thrown away) or
                         at/above it (a near-miss on a ball production kept).
    ``student_hallucination`` nothing between the lowest threshold and the floor.
    ``unresolved``      instances exist but none clears the gate, or the frame was
                         never measured.  Silence is never read as a hallucination.
    """
    x, y = float(case["x"]), float(case["y"])
    floor = min(thresholds)
    near = instances_near(instances, x, y, radius)
    above = [(d, i) for d, i in near if float(i["score"]) >= floor]
    best = None
    for d, inst in above:
        ok, _reason = admit(inst)
        if ok:
            best = (d, inst)
            break

    row = dict(case)
    row["measured"] = instances is not None
    row["radius_px"] = radius
    row["instances_within_radius"] = len(near)
    row["nearest_offset_px"] = round(near[0][0], 2) if near else None
    row["nearest_offset_score"] = round(float(near[0][1]["score"]), 3) if near else None
    row["instances"] = [
        {"offset_px": round(d, 2), "score": round(float(i["score"]), 3),
         "x": round(float(i["x"]), 1), "y": round(float(i["y"]), 1),
         "r": round(float(i.get("r") or 0.0), 1), "area": round(float(i.get("area") or 0.0), 1),
         "in_cloth": bool(i.get("in_cloth", True)),
         "admitted": admit(i)[0], "gate": admit(i)[1],
         "above_production_cut": round(float(i["score"]), 3) >= production_cut}
        for d, i in near
    ]

    if not row["measured"]:
        row["verdict"] = "unresolved"
        row["reason"] = "frame_not_measured"
        return row
    if best is None:
        row["verdict"] = "unresolved" if near else "student_hallucination"
        if not near:
            row["reason"] = "no_instance_within_radius_at_any_threshold"
        elif above:
            row["reason"] = "instance_present_but_failed_gate"
        else:
            row["reason"] = "only_instances_below_the_lowest_sweep_threshold"
        return row

    d, inst = best
    score = float(inst["score"])
    row["verdict"] = "teacher_recall"
    row["reason"] = ("instance_at_or_above_production_cut" if score >= production_cut
                     else "instance_below_production_cut")
    row["found_offset_px"] = round(d, 2)
    row["found_score"] = round(score, 3)
    row["found_r"] = round(float(inst.get("r") or 0.0), 1)
    # which sweep thresholds this instance is still present at.  The highest one is
    # the actionable number: "production would have to drop to X to keep this ball".
    row["present_at_thresholds"] = [t for t in sorted(thresholds) if score >= t]
    row["highest_threshold_present"] = (max(row["present_at_thresholds"])
                                        if row["present_at_thresholds"] else None)
    return row


def recover_fn(fn: dict, peaks: list, tol_px: float = MATCH_TOL_PX) -> dict:
    """Does a student peak at this threshold come back to the missed label?"""
    best_d, best = None, None
    for (px, py, score) in peaks or ():
        d = math.hypot(px - float(fn["x"]), py - float(fn["y"]))
        if best_d is None or d < best_d:
            best_d, best = d, score
    row = dict(fn)
    row["nearest_peak_px"] = round(best_d, 2) if best_d is not None else None
    row["nearest_peak_score"] = round(float(best), 3) if best is not None else None
    row["recovered"] = bool(best_d is not None and best_d <= tol_px)
    return row


def percentile(values: list, q: float) -> float:
    """Nearest-rank percentile: no numpy in the decision layer, one definition."""
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return float("nan")
    rank = max(0, min(len(ordered) - 1, int(math.ceil(q / 100.0 * len(ordered))) - 1))
    return ordered[rank]


def recovery_by_threshold(fn_rows: list, peaks_by_t: dict, thresholds: tuple) -> tuple:
    """Per threshold: how many missed labels come back, and how well placed.

    ``peaks_by_t`` is ``{threshold: {t: [(x, y, score), ...]}}`` in native pixels.
    Returns ``(rows, entry)`` where ``entry`` maps a missed label to the **highest**
    student threshold that still recovers it -- that is "how far would production
    have to lower the threshold to keep this ball", which is the actionable number;
    a plain "it comes back somewhere" would be true at 0.05 for almost anything.
    """
    rows, entry = [], {}
    for threshold in sorted(thresholds):
        per_t = peaks_by_t.get(threshold, {})
        recovered, errors = 0, []
        for fn in fn_rows:
            row = recover_fn(fn, per_t.get(round(float(fn["t"]), 3), []))
            if row["recovered"]:
                recovered += 1
                errors.append(row["nearest_peak_px"])
                entry[fn["id"]] = threshold          # ascending, so the last wins
        rows.append({
            "threshold": threshold,
            "recovered": recovered,
            "of": len(fn_rows),
            "localisation_px_median": round(percentile(errors, 50), 2) if errors else None,
            "localisation_px_p90": round(percentile(errors, 90), 2) if errors else None,
        })
    return rows, entry


def verdict_counts(rows: list) -> dict:
    counts = {"teacher_recall": 0, "student_hallucination": 0, "unresolved": 0}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return counts


def headline(fp_rows: list, fn_rows: list, recovery: list) -> dict:
    """The counts a reader acts on, computed once so the doc cannot drift."""
    counts = verdict_counts(fp_rows)
    below = sum(1 for row in fp_rows
                if row["verdict"] == "teacher_recall"
                and row.get("reason") == "instance_below_production_cut")
    at_or_above = counts["teacher_recall"] - below
    operational = next((row for row in recovery
                        if abs(row["threshold"] - 0.425) < 1e-9), None)
    best = max(recovery, key=lambda row: row["recovered"]) if recovery else None
    return {
        "fp_total": len(fp_rows),
        "teacher_recall": counts["teacher_recall"],
        "teacher_recall_below_cut": below,
        "teacher_recall_at_or_above_cut": at_or_above,
        "student_hallucination": counts["student_hallucination"],
        "unresolved": counts["unresolved"],
        "fn_total": len(fn_rows),
        "fn_recovered_at_operating_threshold": (operational or {}).get("recovered"),
        "fn_recovered_best": (best or {}).get("recovered"),
        "fn_recovered_best_threshold": (best or {}).get("threshold"),
    }


# -------------------------------------------------------------------- report ---

def markdown_table(fp_rows: list, fn_rows: list, entry: dict) -> str:
    """The verdict table, generated from the JSON so it cannot drift from it."""
    lines = ["## Per-case verdicts: the 15 false positives", "",
             "| case | t (s) | student | offset to nearest SAM3 inst | inst score | inst r | gate "
             "| verdict | why |",
             "|---|---|---|---|---|---|---|---|---|"]
    for row in fp_rows:
        lines.append("| {id} | {t:.1f} | {s:.2f} | {off} | {sc} | {r} | {gate} | **{v}** | {why} |"
                     .format(id=row["id"], t=row["t"], s=row["student_score"],
                             off=(f"{row['nearest_offset_px']:.1f} px"
                                  if row["nearest_offset_px"] is not None else "-"),
                             sc=(f"{row['nearest_offset_score']:.2f}"
                                 if row["nearest_offset_score"] is not None else "-"),
                             r=(f"{row.get('found_r'):.1f} px" if row.get("found_r") is not None
                                else (f"{row['instances'][0]['r']:.1f} px"
                                      if row["instances"] else "-")),
                             gate=(row["instances"][0]["gate"] if row["instances"] else "-"),
                             v=row["verdict"], why=row["reason"]))
    lines += ["", "## Per-case mirror test: the 22 false negatives", "",
              "| case | t (s) | teacher score | offset to nearest student peak at 0.425 "
              "| student threshold that recovers it | localisation at recovery |",
              "|---|---|---|---|---|---|"]
    for row in fn_rows:
        first = entry.get(row["id"])
        lines.append("| {id} | {t:.1f} | {s:.2f} | {op} | {thr} | {loc} |".format(
            id=row["id"], t=row["t"], s=row["teacher_score"],
            op=("-" if row.get("nearest_peak_px_at_operating") is None
                else f"{row['nearest_peak_px_at_operating']:.1f} px"),
            thr=("-" if first is None else f"{first:.3f}"),
            loc=("-" if row.get("recovered_at") is None
                 else f"{row['recovered_at']:.2f} px")))
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------- student passes ---

def held_frames() -> list:
    return [round(float(t), 3) for t in
            json.loads((PROBE / "held_frozen.json").read_text())["held"]]


def student_pass(size: tuple, times: list, device: str = "auto"):
    """Heatmaps plus the label set, for ``times`` only -- the student is cheap."""
    import torch

    torch.set_num_threads(8)
    from src import tiny_ball_net as T

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _saved = T.load_checkpoint(BITMAP, size)
    model = model.to(device)
    heats = T.predict(model, T.VIDEO, sorted(times), device=device, size=size, batch=2)
    return T, heats, device


def case_times(cases: dict) -> list:
    return sorted({round(float(row["t"]), 3) for row in cases["fp"] + cases["fn"]})


# ----------------------------------------------------------------- commands ---

def cmd_cases(args) -> int:
    """Rebuild the FP/FN lists from the checkpoint and freeze them as cases."""
    import torch

    torch.set_num_threads(8)
    from src import tiny_ball_net as T

    size = T.parse_size(args.size)
    labels = T.load_labels()
    _train, held = T.split_for_rounds(labels)
    model, _saved = T.load_checkpoint(args.bitmap, size)
    device = "cuda" if (args.device == "auto" and torch.cuda.is_available()) else (
        args.device if args.device != "auto" else "cpu")
    model = model.to(device)
    heats = T.predict(model, T.VIDEO, held, device=device, size=size, batch=2)
    scale = T.NATIVE_WH[0] / size[0]

    # the operating threshold is read from the frozen report, not re-chosen here:
    # the audit adjudicates the report's errors, it does not get to move them
    frozen = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    threshold = float((frozen.get("operating") or {}).get("threshold") or args.threshold)
    quad = T.reference_quad()

    fp_rows, fn_rows = [], []
    matched_ids = {}
    for t in sorted(heats):
        pred = T.pick_peaks(heats[t], threshold)
        truth = labels.get(round(t, 3), [])
        result = T.match_rows_native(pred, truth, args.tol_px, scale)
        matched_ids[t] = {id(ball) for ball in truth} - {id(b) for b in result["missed"]}
        frames_labels = [[round(float(b["x"]), 1), round(float(b["y"]), 1),
                          round(float(b.get("r") or 0.0), 1)] for b in truth]
        for ball in result["missed"]:
            fn_rows.append({
                "id": f"fn{len(fn_rows) + 1:02d}", "t": t,
                "x": round(float(ball["x"]), 1), "y": round(float(ball["y"]), 1),
                "teacher_score": round(float(ball.get("score") or 0.0), 3),
                "r": round(float(ball.get("r") or 0.0), 1),
                "edge_px": (round(float(T.cloth_edge_distance(quad, ball["x"], ball["y"])), 1)
                            if quad is not None else None),
                "labels_in_frame": frames_labels,
            })
        for (px, py, score) in result["extra"]:
            x, y = px * scale, py * scale
            nearest, nearest_d = None, None
            for ball in truth:
                d = math.hypot(ball["x"] - x, ball["y"] - y)
                if nearest_d is None or d < nearest_d:
                    nearest, nearest_d = ball, d
            fp_rows.append({
                "id": f"fp{len(fp_rows) + 1:02d}", "t": t,
                "x": round(float(x), 1), "y": round(float(y), 1),
                "student_score": round(float(score), 3),
                # a duplicate of a label another peak already claimed is a
                # *different* story from a hallucination, and this is the field
                # that makes it visible instead of letting the verdict imply it
                "nearest_label_px": round(nearest_d, 2) if nearest_d is not None else None,
                "nearest_label_score": (round(float(nearest.get("score") or 0.0), 3)
                                        if nearest is not None else None),
                "nearest_label_already_matched": bool(
                    nearest is not None and id(nearest) in matched_ids[t]),
                "labels_in_frame": frames_labels,
            })

    AUDIT.mkdir(parents=True, exist_ok=True)
    payload = {
        "provenance": {
            "bitmap": str(BITMAP), "size": list(size), "device": device,
            "threshold": threshold, "tol_px": args.tol_px, "held_frames": len(held),
            "labels_frames": len(labels), "label_sources": _label_sources(labels),
            "reproduced": {"fp": len(fp_rows), "fn": len(fn_rows)},
            "frozen_report": {"fp": (frozen.get("operating") or {}).get("fp"),
                              "fn": (frozen.get("operating") or {}).get("fn"),
                              "f1": (frozen.get("operating") or {}).get("f1")},
        },
        "fp": fp_rows, "fn": fn_rows,
    }
    payload["provenance"]["case_frames"] = len(case_times(payload))
    CASES_OUT.write_text(json.dumps(payload, indent=1))
    _log(json.dumps({"fp": len(fp_rows), "fn": len(fn_rows),
                     "case_frames": payload["provenance"]["case_frames"],
                     "threshold": threshold,
                     "frozen": payload["provenance"]["frozen_report"]}, indent=1))
    if payload["provenance"]["frozen_report"]["fp"] not in (None, len(fp_rows)):
        _log(f"WARNING: the frozen report counts "
             f"{payload['provenance']['frozen_report']['fp']} FPs, this pass found "
             f"{len(fp_rows)}; the audit is not adjudicating the published errors")
        return 1
    return 0


def _label_sources(labels: dict) -> dict:
    sources = {}
    for balls in labels.values():
        for ball in balls:
            key = ball.get("source", "teacher-cache")
            sources[key] = sources.get(key, 0) + 1
    return sources


# ---------------------------------------------------------------- SAM3 sweep --

def measure_frame(t, floor: float = SAM3_FLOOR) -> dict:
    """One SAM3 forward pass on ``t``: every instance at or above ``floor``.

    The four sweep thresholds come out of this single pass, which is why the
    sweep is free once a frame is bought.  Coordinates are native pixels: the
    processor interpolates the masks back to ``original_height/width``.
    """
    import cv2
    import numpy as np
    from PIL import Image

    from src import sam3_cpu
    from src.sam3_ball_cache import cloth_mask, reference_quad
    from src.pipeline import ball_center

    video = ROOT / "data" / "vod_30min_260815.mp4"
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
    ok, bgr = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"no frame at t={t}")

    proc = _processor()
    proc.confidence_threshold = floor
    started = time.time()
    state = proc.set_image(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
    state = proc.set_text_prompt("billiard ball", state)
    seconds = time.time() - started

    masks = state["masks"].cpu().float().numpy()
    scores = state["scores"].cpu().float().numpy()
    cloth, filter_used = cloth_mask(bgr, reference=reference_quad())
    instances = []
    for index in range(len(scores)):
        mask = np.squeeze(masks[index])
        area = float(mask.sum())
        cx, cy, radius = ball_center(mask)
        inside = bool(0 <= int(cy) < cloth.shape[0] and 0 <= int(cx) < cloth.shape[1]
                      and cloth[int(cy), int(cx)])
        instances.append({
            "x": round(float(cx), 1), "y": round(float(cy), 1),
            "score": round(float(scores[index]), 4),
            "area": round(area, 1), "r": round(float(radius), 1),
            "in_cloth": inside,
        })
    instances.sort(key=lambda row: -row["score"])
    return {"seconds": round(seconds, 1), "count": len(instances),
            "cloth_filter": filter_used, "instances": instances}


_PROCESSOR = None


def _processor():
    """One model load for the whole run: 70 s of the budget is the load, not a frame."""
    global _PROCESSOR
    if _PROCESSOR is None:
        from src import sam3_cpu
        started = time.time()
        model = sam3_cpu.load_sam3_image_model(str(ROOT / "data" / "sam3.safetensors"))
        _PROCESSOR = sam3_cpu.make_processor(model)
        _PROCESSOR._load_seconds = round(time.time() - started, 1)
        _log(f"SAM3 loaded in {_PROCESSOR._load_seconds}s")
    return _PROCESSOR


def cached_frames() -> dict:
    """The teacher's own caches, keyed by rounded time -- read-only, for cross-check."""
    out = {}
    for path in (CENSUS, RESULTS):
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        frames = payload.get("frames") if isinstance(payload, dict) and "frames" in payload \
            else payload
        for key, balls in (frames or {}).items():
            out[round(float(key), 3)] = balls
    return out


def cache_agreement(t: float, instances: list, cached: dict) -> dict:
    """Did this run reproduce the teacher cache's admitted instances at the cut?

    A free honesty check on the whole sweep: the cache holds only scores >= 0.62,
    so if this run's admitted instances at >= 0.62 do not match the stored row,
    the low-threshold numbers below it are suspect too.
    """
    if round(float(t), 3) not in cached:
        return {"cached_row": None}
    stored = [{"x": float(b["img"][0]), "y": float(b["img"][1])}
              for b in cached[round(float(t), 3)] if b.get("img")]
    mine = [i for i in instances
            if i["score"] >= PRODUCTION_CUT and admit(i)[0]]
    unmatched = 0
    for ball in stored:
        if not any(math.hypot(ball["x"] - i["x"], ball["y"] - i["y"]) <= 1.0 for i in mine):
            unmatched += 1
    extra = 0
    for inst in mine:
        if not any(math.hypot(ball["x"] - inst["x"], ball["y"] - inst["y"]) <= 1.0
                   for ball in stored):
            extra += 1
    return {"cached_row": len(stored), "measured_admitted_at_cut": len(mine),
            "cached_unmatched": unmatched, "measured_extra": extra,
            "agrees": unmatched == 0 and extra == 0}


def cmd_measure(args) -> int:
    """Buy SAM3 frames for the disputed points, cached after every frame."""
    cases = json.loads(CASES_OUT.read_text())
    wanted = sorted({round(float(row["t"]), 3) for row in cases["fp"]})
    cached = json.loads(SWEEP_OUT.read_text()) if SWEEP_OUT.exists() else {}
    frames = cached.get("frames", {})
    todo = [t for t in wanted if str(t) not in frames]
    if args.max_frames:
        todo = todo[:args.max_frames]
    _log(f"{len(wanted)} FP frames, {len(wanted) - len(todo)} already measured, "
         f"{len(todo)} to buy")
    if not todo:
        _log("nothing to buy")
        return 0

    cached_teacher = cached_frames()
    started = time.time()
    spent = []
    for t in todo:
        elapsed = time.time() - started
        if args.budget_s and spent and elapsed + args.estimate_s > args.budget_s:
            _log(f"budget stop: {elapsed:.0f}s spent, next frame would cost ~"
                 f"{args.estimate_s:.0f}s, budget {args.budget_s}s")
            break
        try:
            row = measure_frame(t)
        except Exception as exc:                     # one bad frame must not lose the run
            _log(f"t={t}: FAILED {type(exc).__name__}: {exc}")
            frames[str(t)] = {"error": f"{type(exc).__name__}: {exc}"}
            _write_sweep(frames, started, cached)
            continue
        row["agreement"] = cache_agreement(t, row["instances"], cached_teacher)
        frames[str(t)] = row
        spent.append(row["seconds"])
        _log(f"t={t}: {row['count']} instances, {row['seconds']}s, "
             f"cache agrees={row['agreement'].get('agrees')}")
        _write_sweep(frames, started, cached)
    _log(json.dumps({"frames_run": len(spent),
                     "seconds_per_frame_mean": round(sum(spent) / len(spent), 1)
                     if spent else None,
                     "wall_clock_s": round(time.time() - started, 1)}, indent=1))
    return 0


def _write_sweep(frames: dict, started: float, cached: dict) -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    meta = dict(cached.get("meta") or {})
    meta.update({"model": "data/sam3.safetensors", "device": "cpu", "floor": SAM3_FLOOR,
                 "production_cut": PRODUCTION_CUT, "thresholds": list(SWEEP_THRESHOLDS),
                 "radius_px": CANDIDATE_RADIUS_PX,
                 "note": "scores are raw SAM3 object scores; the production caches keep "
                         "only >= 0.62, which is why this sweep needs its own pass"})
    SWEEP_OUT.write_text(json.dumps({"meta": meta, "frames": frames}, indent=1))


def _sweep_instances(frames: dict, t: float) -> list:
    row = frames.get(str(round(float(t), 3)))
    if not row or "instances" not in row:
        return None
    return row["instances"]


# --------------------------------------------------------------- adjudicate ---

def cmd_verdicts(args) -> int:
    """Turn the bought frames and the student mirror test into verdicts + a table."""
    import torch

    torch.set_num_threads(8)
    from src import tiny_ball_net as T

    cases = json.loads(CASES_OUT.read_text())
    size = tuple(cases["provenance"]["size"])
    sweep = json.loads(SWEEP_OUT.read_text()) if SWEEP_OUT.exists() else {"frames": {}}
    threshold = float(cases["provenance"]["threshold"])

    fp_rows = [adjudicate_fp(case, _sweep_instances(sweep["frames"], case["t"]))
               for case in cases["fp"]]

    # --- the mirror test: the student at a lower output threshold, no SAM3 cost
    fn_times = sorted({round(float(row["t"]), 3) for row in cases["fn"]})
    fp_times = sorted({round(float(row["t"]), 3) for row in cases["fp"]})
    times = sorted(set(fn_times) | set(fp_times))
    _log(f"student pass over {len(times)} case frames")
    started = time.time()
    T_mod, heats, device = student_pass(size, times, args.device)
    _log(f"student pass {time.time() - started:.1f}s on {device}")
    scale = T_mod.NATIVE_WH[0] / size[0]

    peaks_by_t = {}
    for thr in FN_THRESHOLDS:
        peaks_by_t[thr] = {t: [(x * scale, y * scale, s)
                               for (x, y, s) in T_mod.pick_peaks(heats[t], thr)]
                           for t in heats}
    recovery, entry = recovery_by_threshold(cases["fn"], peaks_by_t, FN_THRESHOLDS)
    fn_rows = []
    for case in cases["fn"]:
        row = dict(case)
        op_peaks = peaks_by_t.get(threshold, {}).get(round(float(case["t"]), 3), [])
        row["nearest_peak_px_at_operating"] = recover_fn(case, op_peaks)["nearest_peak_px"]
        first = entry.get(case["id"])
        row["first_recovered_at"] = first
        if first is not None:
            candidates = peaks_by_t[first].get(round(float(case["t"]), 3), [])
            rec = recover_fn(case, candidates)
            row["recovered_at"] = rec["nearest_peak_px"] if rec["recovered"] else None
            row["recovered_at_score"] = rec["nearest_peak_score"]
        else:
            row["recovered_at"] = None
            row["recovered_at_score"] = None
        fn_rows.append(row)

    # the global cost of lowering the threshold comes from the frozen report's own
    # sweep, so recovery counts and precision/recall cost are the same measurement
    frozen_sweep = {round(float(r["threshold"]), 3): r
                    for r in json.loads(REPORT.read_text())["sweep"]}
    cost = []
    for r in sorted(recovery, key=lambda r: -r["threshold"]):
        if not r["recovered"] and r["threshold"] != threshold:
            continue
        if r["threshold"] not in frozen_sweep:
            continue
        frozen_row = frozen_sweep[r["threshold"]]
        cost.append({"threshold": r["threshold"], "fn_recovered": r["recovered"],
                     "of": r["of"], "tp": frozen_row["tp"], "fp": frozen_row["fp"],
                     "fn": frozen_row["fn"], "precision": frozen_row["precision"],
                     "recall": frozen_row["recall"], "f1": frozen_row["f1"],
                     "localisation_px_p90": frozen_row["localisation_px_p90"],
                     "recovered_localisation_median_px": r["localisation_px_median"]})

    head = headline(fp_rows, fn_rows, recovery)
    measured = sum(1 for t in {round(float(r["t"]), 3) for r in cases["fp"]}
                   if _sweep_instances(sweep["frames"], t) is not None)
    payload = {"headline": head, "cost": cost, "entry_threshold": entry,
               "sweep_cost": {"fp_frames_wanted": len({round(float(r['t']), 3)
                                                       for r in cases['fp']}),
                              "fp_frames_measured": measured,
                              "sam3_floor": SAM3_FLOOR,
                              "production_cut": PRODUCTION_CUT,
                              "fn_frames_without_sam3": len(fn_times),
                              "note": "FN frames need no SAM3 pass: their teacher instance "
                                      "and score are already in the labels"},
               "fp": fp_rows, "fn": fn_rows, "recovery": recovery}
    AUDIT.mkdir(parents=True, exist_ok=True)
    VERDICTS_OUT.write_text(json.dumps(payload, indent=1))
    table = markdown_table(fp_rows, fn_rows, entry)
    TABLE_OUT.write_text(table)
    _log(json.dumps(head, indent=1))
    _log(table)
    return 0


# -------------------------------------------------------------------- crops ---

def crop_bounds(x: float, y: float, half: int, shape: tuple) -> tuple:
    """A native-pixel window around ``(x, y)``, clamped to the frame."""
    h, w = shape[:2]
    x0 = max(0, min(w - 1, int(x) - half))
    y0 = max(0, min(h - 1, int(y) - half))
    x1 = min(w, x0 + 2 * half)
    y1 = min(h, y0 + 2 * half)
    return x0, y0, x1, y1


def render_case(bgr, case: dict, half: int, scale: int, title: str, subtitle: str,
                student_peaks: list, teacher_labels: list, instances: list,
                extra_peaks: list = ()) -> "object":
    """One crop per case: the dispute, the student, the teacher and the sweep.

    The picture is the *checkable* artifact: a human should be able to confirm or
    overturn the automated verdict in it without reading the JSON.
    """
    import cv2
    import numpy as np

    x, y = float(case["x"]), float(case["y"])
    x0, y0, x1, y1 = crop_bounds(x, y, half, bgr.shape)
    crop = bgr[y0:y1, x0:x1].copy()
    crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    to_px = lambda px, py: (int((px - x0) * scale), int((py - y0) * scale))  # noqa: E731

    # teacher labels (green): what the student was scored against
    for (lx, ly, lr) in teacher_labels:
        if not (x0 - lr <= lx <= x1 + lr and y0 - lr <= ly <= y1 + lr):
            continue
        centre = to_px(lx, ly)
        cv2.circle(crop, centre, max(8, int(lr * scale)), (0, 200, 0), 2)
        cv2.putText(crop, "teacher", (centre[0] + 6, centre[1] - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 0), 1, cv2.LINE_AA)
    # SAM3 instances from this sweep (cyan below the production cut, orange above)
    for inst in instances or ():
        ix, iy = float(inst["x"]), float(inst["y"])
        if not (x0 <= ix <= x1 and y0 <= iy <= y1):
            continue
        colour = (0, 200, 255) if inst["score"] < PRODUCTION_CUT else (255, 160, 0)
        centre = to_px(ix, iy)
        cv2.circle(crop, centre, max(5, int(float(inst.get("r") or 5) * scale)),
                   colour, 1 if inst["score"] < PRODUCTION_CUT else 2)
        cv2.putText(crop, f"sam3 {inst['score']:.2f}", (centre[0] + 6, centre[1] + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, colour, 1, cv2.LINE_AA)
    # the student's own peaks at the operating threshold (red)
    for (px, py, s) in student_peaks:
        if not (x0 <= px <= x1 and y0 <= py <= y1):
            continue
        centre = to_px(px, py)
        cv2.circle(crop, centre, 10, (0, 0, 255), 2)
        cv2.putText(crop, f"student {s:.2f}", (centre[0] + 6, centre[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 255), 1, cv2.LINE_AA)
    # extra peaks (blue): the student after the output threshold is lowered
    for (px, py, s) in extra_peaks or ():
        if not (x0 <= px <= x1 and y0 <= py <= y1):
            continue
        centre = to_px(px, py)
        cv2.circle(crop, centre, 14, (255, 0, 0), 2)
        cv2.putText(crop, f"student@low {s:.2f}", (centre[0] + 6, centre[1] + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 0, 0), 1, cv2.LINE_AA)

    # a context thumbnail so the crop is locatable on the table.  It is sized from
    # the crop, not fixed: a case near the frame edge has a narrow crop (the bounds
    # clamp) and a fixed 192 px thumbnail would not fit into it.
    h, w = crop.shape[:2]
    thumb_w = max(1, min(192, w // 2))
    thumb_h = max(1, int(round(thumb_w * bgr.shape[0] / float(bgr.shape[1]))))
    if thumb_h <= h:
        thumb = cv2.resize(bgr, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
        cv2.rectangle(thumb,
                      (int(x0 * thumb_w / bgr.shape[1]), int(y0 * thumb_h / bgr.shape[0])),
                      (int(x1 * thumb_w / bgr.shape[1]), int(y1 * thumb_h / bgr.shape[0])),
                      (0, 255, 255), 1)
        cv2.drawMarker(thumb,
                       (int(x * thumb_w / bgr.shape[1]), int(y * thumb_h / bgr.shape[0])),
                       (0, 0, 255), cv2.MARKER_CROSS, 7, 1)
        crop[0:thumb_h, w - thumb_w:w] = thumb

    band = np.zeros((74, w, 3), np.uint8)
    cv2.putText(band, title, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1,
                cv2.LINE_AA)
    cv2.putText(band, subtitle[:110], (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.46,
                (200, 255, 200), 1, cv2.LINE_AA)
    cv2.putText(band, "red = student  green = teacher label  cyan/orange = SAM3 now "
                      "(cyan < 0.62 cut)  blue = student at a lower threshold",
                (8, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1, cv2.LINE_AA)
    return np.concatenate([band, crop], axis=0)


def native_frame(t: float):
    """The frame at native resolution: the crop is checked at the size the ball is."""
    import cv2

    cap = cv2.VideoCapture(str(ROOT / "data" / "vod_30min_260815.mp4"))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
    ok, bgr = cap.read()
    cap.release()
    return bgr if ok else None


def cmd_crops(args) -> int:
    """One PNG per case, so the automated verdict can be checked in seconds."""
    import cv2

    cases = json.loads(CASES_OUT.read_text())
    verdicts = json.loads(VERDICTS_OUT.read_text()) if VERDICTS_OUT.exists() else None
    sweep = json.loads(SWEEP_OUT.read_text()) if SWEEP_OUT.exists() else {"frames": {}}
    size = tuple(cases["provenance"]["size"])
    threshold = float(cases["provenance"]["threshold"])
    low = float(args.low_threshold)

    times = case_times(cases)
    T_mod, heats, device = student_pass(size, times, args.device)
    scale = T_mod.NATIVE_WH[0] / size[0]
    _log(f"student pass on {device}; rendering {len(times)} frames")

    by_t = {}
    for t, heat in heats.items():
        by_t[t] = {
            "op": [(x * scale, y * scale, s) for (x, y, s) in T_mod.pick_peaks(heat, threshold)],
            "low": [(x * scale, y * scale, s) for (x, y, s) in T_mod.pick_peaks(heat, low)],
        }
    fp_by_id = {row["id"]: row for row in (verdicts or {}).get("fp", [])}
    fn_by_id = {row["id"]: row for row in (verdicts or {}).get("fn", [])}

    AUDIT.mkdir(parents=True, exist_ok=True)
    written = []
    for case in cases["fp"]:
        t = round(float(case["t"]), 3)
        verdict = fp_by_id.get(case["id"], {})
        bgr = native_frame(t)
        if bgr is None:
            _log(f"{case['id']}: no frame, skipped")
            continue
        near = [i for i in (sweep["frames"].get(str(t), {}).get("instances") or [])
                if abs(i["x"] - case["x"]) <= 70 and abs(i["y"] - case["y"]) <= 70]
        title = (f"{case['id']}  FP  t={t:.1f}s  student {case['student_score']:.2f}  =>  "
                 f"{verdict.get('verdict', 'unmeasured')}")
        bits = []
        if verdict.get("nearest_offset_px") is not None:
            bits.append(f"nearest SAM3 inst {verdict['nearest_offset_px']:.1f} px "
                        f"@ {verdict['nearest_offset_score']:.2f}")
        if verdict.get("found_score") is not None:
            bits.append(f"admitted @ {verdict['found_score']:.2f} (cut {PRODUCTION_CUT})")
        if case.get("nearest_label_px") is not None:
            bits.append(f"nearest label {case['nearest_label_px']:.1f} px")
        subtitle = verdict.get("reason", "") + " | " + " | ".join(bits)
        image = render_case(bgr, case, args.half, args.scale, title, subtitle,
                            by_t[t]["op"], case["labels_in_frame"], near)
        path = AUDIT / f"{case['id']}_t{t:.1f}s.png"
        cv2.imwrite(str(path), image)
        written.append(str(path))

    for case in cases["fn"]:
        t = round(float(case["t"]), 3)
        verdict = fn_by_id.get(case["id"], {})
        bgr = native_frame(t)
        if bgr is None:
            continue
        first = verdict.get("first_recovered_at")
        title = (f"{case['id']}  FN  t={t:.1f}s  teacher {case['teacher_score']:.2f}  =>  "
                 + (f"recovers at student {first:.3f}" if first is not None
                    else f"no recovery down to {min(FN_THRESHOLDS):.2f}"))
        subtitle = (f"nearest student peak at the operating threshold "
                    f"{verdict.get('nearest_peak_px_at_operating')} px"
                    + (f" | at recovery {verdict['recovered_at']:.2f} px"
                       if verdict.get("recovered_at") is not None else ""))
        image = render_case(bgr, case, args.half, args.scale, title, subtitle,
                            by_t[t]["op"], case["labels_in_frame"],
                            [], extra_peaks=by_t[t]["low"])
        path = AUDIT / f"{case['id']}_t{t:.1f}s.png"
        cv2.imwrite(str(path), image)
        written.append(str(path))

    _log(json.dumps({"crops": len(written), "dir": str(AUDIT),
                     "half_px": args.half, "zoom": args.scale}, indent=1))
    return 0


# ----------------------------------------------------------------------- CLI ---

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("cases", help="rebuild the FP/FN lists and freeze them")
    p.add_argument("--bitmap", default=str(BITMAP))
    p.add_argument("--size", default="960x540")
    p.add_argument("--device", default="auto")
    p.add_argument("--threshold", type=float, default=0.425,
                   help="only used when the frozen report is absent")
    p.add_argument("--tol-px", type=float, default=MATCH_TOL_PX)
    p.set_defaults(func=cmd_cases)

    p = sub.add_parser("sam3", help="buy SAM3 frames for the disputed points")
    p.add_argument("--budget-s", type=float, default=1500.0)
    p.add_argument("--max-frames", type=int, default=0)
    p.add_argument("--estimate-s", type=float, default=45.0,
                   help="cost estimate used to refuse a frame that will not fit the budget")
    p.set_defaults(func=cmd_measure)

    p = sub.add_parser("verdicts", help="adjudicate the FPs and mirror-test the FNs")
    p.add_argument("--device", default="auto")
    p.set_defaults(func=cmd_verdicts)

    p = sub.add_parser("crops", help="render one crop per case")
    p.add_argument("--device", default="auto")
    p.add_argument("--half", type=int, default=90)
    p.add_argument("--scale", type=int, default=3)
    p.add_argument("--low-threshold", type=float, default=0.15)
    p.set_defaults(func=cmd_crops)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
