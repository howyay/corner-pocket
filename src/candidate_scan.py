"""Raw candidate generation: every motion moment and census drop, ungated.

The info-complete scan refuses to look at a frame unless person, cloth area,
exposure and census all pass, which keeps 806 of 27001 sampled frames (3 %) and
produced 41 candidates -- all of which the fused census then refuted as
occlusion artifacts.  This pass inverts the order: it *records* the gate signals
on every sampled frame and emits every moment that crosses a threshold, with the
signals attached.  Pruning and the expensive SAM3 verification then happen
afterwards, on evidence instead of on faith.

Three candidate kinds, none of them a claim:

* ``shot``   a same-colour ball matched between two sampled frames whose
             displacement crosses the shot threshold, speed inside the band;
* ``motion`` a frame whose cloth-area motion crosses the shot level while the
             census is stable -- a shot the colour blobs lost to motion blur.
             The ball's from/to is recovered by matching back across the window
             (the blobs cannot see the ball *during* the shot, but they can see
             where it was and where it stopped);
* ``pot``    the classical census falling by ``census_drop`` from its running
             median and staying down for ``census_hold`` samples.

Each candidate carries the record that produced it: ball count, cloth area,
brightness, cloth-area motion, the share of the cloth a person covers, and the
vanished ball's last position.  ``prune`` (same module) drops the occluded ones
and ranks the rest, and reports why each was dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
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

from src.datasets import media_relpath  # noqa: E402
from src import events_document  # noqa: E402
from src.ball_detect import detect_ball_candidates  # noqa: E402
from src.info_complete_scan import (GateConfig, _on_table, _quad_box_overlap_area,  # noqa: E402
                                    match_balls, to_table_mm)
from src.pipeline import homography_to_canonical  # noqa: E402
from src.table_detect import detect_table  # noqa: E402

SMALL_W, SMALL_H = 960, 540
# A pair the frames show no motion for is a chance pairing, not a shot.
MOTION_MIN_SHOT = 8.0
MIN_BALL_AREA, MAX_BALL_AREA = 14.0, 9000.0


@dataclass
class ScanConfig:
    """Thresholds that decide what becomes a raw candidate (generation only)."""
    stride: int = 2
    shot_min_disp_mm: float = 300.0
    shot_speed_mm_s: float = 500.0
    max_speed_mm_s: float = 11000.0
    match_radius_factor: float = 3.0
    streak_needed: int = 2          # both ends of a shot pair must be established
    census_window: int = 40         # samples the running median is built from
    census_drop: int = 1
    census_hold: int = 8            # samples the drop must survive to count
    motion_shot: float = 18.0       # cloth motion level that suggests a shot
    lookback_min_s: float = 0.5     # how far back a motion candidate finds from_mm
    lookback_max_s: float = 2.0
    lookback_px: float = 420.0
    person_every: int = 5
    person_share: float = 0.02      # person/cloth overlap that marks a frame occluded
    cloth_band: tuple = (0.55, 1.60)   # vs the running median, for the prune report


# --------------------------------------------------------------- the raw pass

def frame_records(video, cfg: ScanConfig = ScanConfig(), limit_s: float | None = None,
                  progress=lambda text: None, persons=None) -> dict:
    """Decode the VOD once; return per-frame records plus the median cloth quad."""
    from src.info_complete_scan import person_boxes_fn
    if persons is None:
        persons = person_boxes_fn()
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    records, corners = [], []
    last_gray, last_t = None, None
    index, started = 0, time.time()
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        t = index / fps
        if limit_s is not None and t > limit_s:
            break
        if index % cfg.stride:
            index += 1
            continue
        small = cv2.resize(bgr, (SMALL_W, SMALL_H))
        table = detect_table(small)
        cloth = table["mask"] > 0
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        cands = detect_ball_candidates(small, table["mask"], MIN_BALL_AREA, MAX_BALL_AREA)
        motion = None
        if last_gray is not None and cloth.any():
            diff = np.abs(gray.astype(np.int16) - last_gray.astype(np.int16))
            motion = round(float(diff[cloth].mean()), 2)
        person_share = None
        if index % cfg.person_every == 0 and table["corners"] is not None:
            quad = np.array(table["corners"], np.float32)
            area = max(1.0, float(cv2.contourArea(np.array(quad, np.int32))))
            sx, sy = bgr.shape[1] / SMALL_W, bgr.shape[0] / SMALL_H
            share = 0.0
            for x1, y1, x2, y2 in persons(bgr):
                box = np.array([[x1 / sx, y1 / sy], [x2 / sx, y1 / sy],
                                [x2 / sx, y2 / sy], [x1 / sx, y2 / sy]], np.float32)
                share = max(share, _quad_box_overlap_area(quad, box) / area)
            person_share = round(share, 4)
        if table["corners"] is not None:
            corners.append(np.array(table["corners"], np.float32))
        records.append({
            "t": round(t, 3), "frame": index, "n": len(cands),
            "cloth_area": int(cloth.sum()), "brightness": round(float(gray.mean()), 2),
            "motion": motion, "person_share": person_share,
            "cands": [{"color": c["color"], "cx": round(c["cx"], 1), "cy": round(c["cy"], 1),
                       "r": round(c["r"], 1)} for c in cands],
        })
        last_gray, last_t = gray, t
        index += 1
        if len(records) % 3000 == 0:
            progress(f"{index}/{total_frames} frames, {len(records)} sampled, "
                     f"{time.time() - started:.0f}s")
    cap.release()
    quad = np.median(np.array(corners), axis=0) if corners else None
    return {"records": records, "quad": quad.tolist() if quad is not None else None,
            "fps": fps, "frames_processed": index,
            "seconds": round(time.time() - started, 1)}


# --------------------------------------------------- records -> raw candidates

def _streaks(records, cfg: ScanConfig) -> None:
    """In-place: how many consecutive samples have shown this ball."""
    previous: list = []
    for record in records:
        for cand in record["cands"]:
            best = None
            for old in previous:
                if old["color"] != cand["color"]:
                    continue
                distance = math.hypot(old["cx"] - cand["cx"], old["cy"] - cand["cy"])
                if distance <= 60.0 and (best is None or distance < best[0]):
                    best = (distance, old)
            cand["_streak"] = (best[1]["_streak"] + 1) if best else 1
        previous = record["cands"]


def _radius(records, cfg: ScanConfig) -> float:
    radii = [c["r"] for record in records for c in record["cands"]]
    return cfg.match_radius_factor * max(radii or [10.0])


def raw_candidates(records, H, cfg: ScanConfig = ScanConfig()) -> list[dict]:
    """Every threshold crossing in ``records``, ungated and undeduped."""
    _streaks(records, cfg)
    radius = _radius(records, cfg)
    out: list = []
    counts: list = []
    open_drop = None
    for index, record in enumerate(records):
        window = counts[-cfg.census_window:]
        median = float(np.median(window)) if window else None
        counts.append(record["n"])

        # -- shots: a matched same-colour pair between two samples -----------
        if index and record["t"] - records[index - 1]["t"] <= 0.2:
            previous = records[index - 1]
            matched, _, _ = match_balls(previous["cands"], record["cands"], radius)
            for before, after, _ in matched:
                # The ball must have been established *before* the move (a
                # flicker cannot claim one) and must still be there *after* it
                # (a resting place, not a stray blob).
                if before.get("_streak", 1) < cfg.streak_needed:
                    continue
                if not _persists(records, index, after, radius + 20.0):
                    continue
                a = to_table_mm(H, before["cx"], before["cy"])
                b = to_table_mm(H, after["cx"], after["cy"])
                if a is None or b is None or not _on_table(a) or not _on_table(b):
                    continue
                gap = record["t"] - previous["t"]
                displacement = math.hypot(a[0] - b[0], a[1] - b[1])
                speed = displacement / max(gap, 1e-6)
                if displacement < cfg.shot_min_disp_mm or speed < cfg.shot_speed_mm_s \
                        or speed > cfg.max_speed_mm_s:
                    continue
                out.append({"type": "shot", "source": "pair", "t": round((previous["t"] + record["t"]) / 2, 2),
                            "color": before["color"], "disp_mm": round(displacement),
                            "speed_mm_s": round(speed), "gap_s": round(gap, 3),
                            "from_mm": [round(a[0], 1), round(a[1], 1)],
                            "to_mm": [round(b[0], 1), round(b[1], 1)],
                            "from_t": previous["t"], "to_t": record["t"],
                            "record": _record_view(record),
                            "pair_record": _record_view(previous)})

        # -- motion: cloth energy spikes with a stable census -----------------
        if record["motion"] is not None and median is not None \
                and record["motion"] >= cfg.motion_shot and abs(record["n"] - median) <= 1:
            candidate = {"type": "shot", "source": "motion", "t": record["t"],
                         "color": None, "motion": record["motion"],
                         "record": _record_view(record)}
            back = _lookback(records, index, record["t"], cfg)
            if back is not None:
                before, after = back
                a = to_table_mm(H, before["cx"], before["cy"])
                b = to_table_mm(H, after["cx"], after["cy"])
                if a and b and _on_table(a) and _on_table(b):
                    displacement = math.hypot(a[0] - b[0], a[1] - b[1])
                    if displacement >= cfg.shot_min_disp_mm:
                        gap = after["_t"] - before["_t"]
                        candidate.update({"color": before["color"], "disp_mm": round(displacement),
                                          "speed_mm_s": round(displacement / max(gap, 1e-6)),
                                          "gap_s": round(gap, 3),
                                          "from_mm": [round(a[0], 1), round(a[1], 1)],
                                          "to_mm": [round(b[0], 1), round(b[1], 1)],
                                          "from_t": before["_t"], "to_t": after["_t"]})
            out.append(candidate)

        # -- census drops: the count falls and stays down ---------------------
        if median is not None and record["n"] <= median - cfg.census_drop:
            if open_drop is None:
                open_drop = {"start_index": index, "median": median,
                             "gone": _missing_balls(records[index - 1]["cands"] if index else [],
                                                    record["cands"], radius),
                             "record": _record_view(record),
                             "held": 0, "floor": record["n"]}
            else:
                open_drop["held"] += 1
                open_drop["floor"] = min(open_drop["floor"], record["n"])
        elif open_drop is not None:
            if open_drop["held"] >= cfg.census_hold - 1:
                out.append(_pot_candidate(open_drop, records, H, cfg))
            open_drop = None
    if open_drop is not None and open_drop["held"] >= cfg.census_hold - 1:
        out.append(_pot_candidate(open_drop, records, H, cfg))
    return out


def _record_view(record) -> dict:
    return {"t": record["t"], "n": record["n"], "cloth_area": record["cloth_area"],
            "brightness": record["brightness"], "motion": record["motion"],
            "person_share": record["person_share"]}


def _persists(records, index, ball, radius: float) -> bool:
    """Is the ball still at this spot in the next sample?

    A ball that a shot sends across the table cannot inherit a streak by
    proximity -- it jumped -- so the arrival is corroborated the other way:
    it must still be inside ``radius`` of the same place one sample later.
    """
    if index + 1 >= len(records):
        return True                      # end of the scan: nothing to check
    return any(other["color"] == ball["color"]
               and math.hypot(other["cx"] - ball["cx"], other["cy"] - ball["cy"]) <= radius
               for other in records[index + 1]["cands"])


def _missing_balls(before, after, radius: float) -> list:
    """Same-colour balls ``before`` held that ``after`` no longer shows."""
    gone = []
    for cand in before:
        if any(other["color"] == cand["color"]
               and math.hypot(other["cx"] - cand["cx"], other["cy"] - cand["cy"]) <= radius
               for other in after):
            continue
        gone.append({"color": cand["color"], "cx": cand["cx"], "cy": cand["cy"],
                     "streak": cand.get("_streak", 1)})
    return gone


def _pot_candidate(drop, records, H, cfg: ScanConfig) -> dict:
    """One drop episode -> one candidate, naming the ball that left.

    The vanished ball is the missing one *closest to a pocket*: a real pot
    leaves one ball by a pocket, while a detector collapse leaves half the
    table.  ``missing_count`` keeps that difference visible for the ranking.
    """
    from src.event_gates import nearest_pocket

    best = None
    for gone in drop["gone"]:
        mm = to_table_mm(H, gone["cx"], gone["cy"])
        if mm is None or not _on_table(mm):
            continue
        pocket, distance = nearest_pocket(mm[0], mm[1])
        key = (distance, -gone.get("streak", 1))
        if best is None or key < best[0]:
            best = (key, gone, mm, pocket, distance)
    candidate = {"type": "pot", "source": "census",
                 "t": records[drop["start_index"]]["t"],
                 "median_before": drop["median"], "floor": drop["floor"],
                 "census_drop": round(drop["median"] - drop["floor"], 2),
                 "missing_count": len(drop["gone"]),
                 "held_samples": drop["held"] + 1,
                 "record": drop["record"], "color": None, "last_mm": None}
    if best is not None:
        _, gone, mm, pocket, distance = best
        candidate.update({"color": gone["color"],
                          "last_mm": [round(mm[0], 1), round(mm[1], 1)],
                          "last_cx": gone["cx"], "last_cy": gone["cy"],
                          "streak": gone.get("streak", 1),
                          "pocket": pocket, "pocket_dist_mm": round(distance)})
    return candidate


def _lookback(records, index, now, cfg: ScanConfig):
    """A same-colour pair spanning the motion spike: where it was, where it is."""
    best = None
    for back in range(index, max(-1, index - 40), -1):
        record = records[back]
        gap = now - record["t"]
        if gap < cfg.lookback_min_s:
            continue
        if gap > cfg.lookback_max_s:
            break
        for before in record["cands"]:
            for after in records[index]["cands"]:
                if before["color"] != after["color"]:
                    continue
                distance = math.hypot(before["cx"] - after["cx"], before["cy"] - after["cy"])
                if distance > cfg.lookback_px:
                    continue
                if before.get("_streak", 1) < cfg.streak_needed:
                    continue
                if best is None or distance > best[0]:
                    best = (distance, dict(before, _t=record["t"]), dict(after, _t=now))
    return None if best is None else (best[1], best[2])


# ------------------------------------------------------------- prune and rank

def prune(candidates, records, cfg: ScanConfig = ScanConfig(), dedup_s: float = 4.0) -> dict:
    """Drop occluded candidates, dedupe by act, rank by raw evidence strength.

    A candidate is dropped when the cloth was not really observable at its
    frames -- a person covering it, the cloth mask collapsing, or a brightness
    step (the VOD re-frames).  The survivors are one per act, ranked by measured
    displacement, census drop and motion, so the SAM3 budget goes to the front.
    """
    by_time = {round(r["t"], 3): r for r in records}
    medians = _rolling_median(records)
    kept, dropped = [], []
    for candidate in sorted(candidates, key=lambda c: c["t"]):
        reasons = _occlusion_reasons(candidate, by_time, medians, cfg)
        if reasons:
            dropped.append({**candidate, "drop_reasons": reasons})
        else:
            kept.append(candidate)
    ranked, merged = [], []
    for candidate in sorted(kept, key=lambda c: (-_strength(c), c["t"])):
        same = next((other for other in merged
                     if other["type"] == candidate["type"] and abs(other["t"] - candidate["t"]) <= dedup_s
                     and (other.get("from_mm") is None or candidate.get("from_mm") is None
                          or math.hypot(other["from_mm"][0] - candidate["from_mm"][0],
                                        other["from_mm"][1] - candidate["from_mm"][1]) <= 250.0)), None)
        if same is not None:
            same["duplicates"] = same.get("duplicates", 1) + 1
            continue
        candidate["strength"] = round(_strength(candidate), 2)
        merged.append(candidate)
    ranked = sorted(merged, key=lambda c: (-c["strength"], c["t"]))
    return {"kept": ranked, "dropped": dropped,
            "counts": {"raw": len(candidates), "dropped_occluded": len(dropped),
                       "after_dedup": len(ranked),
                       "shots": sum(1 for c in ranked if c["type"] == "shot"),
                       "pots": sum(1 for c in ranked if c["type"] == "pot"),
                       "with_geometry": sum(1 for c in ranked
                                            if c["type"] == "shot" and c.get("from_mm"))}}


def _occlusion_reasons(candidate, by_time, medians, cfg: ScanConfig) -> list:
    reasons = []
    views = [candidate.get("record") or {}, candidate.get("pair_record") or {}]
    for view in views:
        if not view:
            continue
        t = round(view.get("t", 0.0), 3)
        if (view.get("person_share") or 0) > cfg.person_share:
            reasons.append("person_on_cloth")
        record = by_time.get(t)
        if record is None:
            continue
        median = medians.get(t)
        if median and not (cfg.cloth_band[0] * median <= record["cloth_area"] <= cfg.cloth_band[1] * median):
            reasons.append("cloth_area_out_of_band")
    return sorted(set(reasons))


def _rolling_median(records, window: int = 120) -> dict:
    values, out = [], {}
    for record in records:
        window_values = values[-window:]
        out[round(record["t"], 3)] = float(np.median(window_values)) if window_values else record["cloth_area"]
        values.append(record["cloth_area"])
    return out


def pot_strength(candidate) -> float:
    """How much a census drop looks like a pot, before any SAM3 spend.

    A pot leaves *one* ball, at a pocket, and the count stays down.  A detector
    collapse leaves half the table, so a large drop is evidence *against* a pot
    even though the raw count moved more.
    """
    drop = candidate.get("census_drop") or 0
    if drop < 1:
        return 0.0
    score = 1.4 if drop <= 2 else 0.6 if drop <= 4 else -1.0
    if candidate.get("pocket_dist_mm") is not None:
        score += max(0.0, 1.6 * (1.0 - candidate["pocket_dist_mm"] / 300.0))
    else:
        score -= 0.5
    missing = candidate.get("missing_count")
    if missing is not None and missing > 3:
        score -= 0.5 * (missing - 3)
    return score


def _candidate_motion(candidate) -> float:
    """Cloth motion at the candidate's own frame, from either shape."""
    if candidate.get("motion") is not None:
        return float(candidate["motion"])
    return float((candidate.get("record") or {}).get("motion") or 0.0)


def shot_strength(candidate) -> float:
    """How much a motion moment looks like a shot, before any SAM3 spend.

    Measured on vod30: the blob detector's stage-2 match joins two same-colour
    balls at any distance, and the displacement distribution of those pairs is a
    flat plateau from 300 mm to the 733 mm the speed cap allows (11 m/s x the
    0.067 s sample gap) -- 916 pairs, ~100 per 50 mm bin, i.e. chance.  Cloth
    motion at the act's own frame is what separates a shot from a coincidence, so
    a pair with no motion is ranked below every candidate that has some.
    """
    motion = _candidate_motion(candidate)
    score = 0.0
    if candidate.get("disp_mm"):
        score += min(3.0, candidate["disp_mm"] / 500.0)
    if candidate.get("from_mm"):
        score += 0.5
    score += min(1.5, motion / 30.0)
    if candidate.get("source") == "pair" and motion < MOTION_MIN_SHOT:
        score -= 2.5
    if candidate.get("source") == "motion":
        score -= 0.25          # the blobs never saw the ball move: weaker
    return score


def _strength(candidate) -> float:
    return pot_strength(candidate) if candidate["type"] == "pot" else shot_strength(candidate)


def plan_sam3(kept, top_pots: int = 12, top_shots: int = 8, cached=(),
              pot_offsets=(-1.25, -0.5, 0.8, 1.6),
              shot_offsets=(-1.0, -0.5, 0.6, 1.6), served=()) -> dict:
    """The frames worth buying for the strongest candidates, in priority order.

    Every candidate gets its bracketing frames: the census needs both sides of
    the act, so a window bought on one side only cannot decide anything (that is
    what `census_source_mismatch` says afterwards).  Frames already cached are
    free and stay in the plan, so the caller can see the real coverage.
    ``served`` events are planned too: the queue the app already carries must be
    re-measured by the same evidence, not left unmeasured while new candidates
    are bought.
    """
    cached = {round(float(t), 1) for t in cached}
    pots = [c for c in kept if c["type"] == "pot" and (c.get("census_drop") or 0) >= 1]
    pots.sort(key=lambda c: (-pot_strength(c), c["t"]))
    shots = [c for c in kept if c["type"] == "shot" and c.get("from_mm")]
    shots.sort(key=lambda c: (-shot_strength(c), c["t"]))
    # Interleaved by strength across kinds: the budget stops where it stops, and
    # a strong shot must not lose its frames to a weak pot that happened first
    # in the table walk.
    chosen = sorted([{"kind": "pot", "candidate": c, "strength": round(pot_strength(c), 2)}
                     for c in pots[:top_pots]]
                    + [{"kind": "shot", "candidate": c, "strength": round(shot_strength(c), 2)}
                       for c in shots[:top_shots]],
                    key=lambda entry: (-entry["strength"], entry["candidate"]["t"]))
    plan = []
    for entry in chosen:
        candidate, kind = entry["candidate"], entry["kind"]
        offsets = pot_offsets if kind == "pot" else shot_offsets
        plan.append({"kind": kind, "t": candidate["t"], "strength": entry["strength"],
                     "frames": [round(candidate["t"] + offset, 2) for offset in offsets],
                     "candidate": candidate})
    for event in served or ():
        try:
            t = round(float(event.get("t")), 2)
        except (TypeError, ValueError):
            continue
        kind = "pot" if str(event.get("type")) == "pot" else "shot"
        offsets = pot_offsets if kind == "pot" else shot_offsets
        plan.append({"kind": kind, "t": t, "strength": None, "served": True,
                     "frames": [round(t + offset, 2) for offset in offsets],
                     "candidate": dict(event, measured="served")})
    frames, seen = [], set()
    for entry in plan:
        for t in entry["frames"]:
            key = round(t, 1)
            if key in seen or t < 0:
                continue
            seen.add(key)
            frames.append({"t": round(t, 2), "cached": key in cached,
                           "for": f"{entry['kind']}@t={entry['t']}"})
    to_buy = [f["t"] for f in frames if not f["cached"]]
    return {"plan": plan, "frames": frames, "to_buy": to_buy,
            "pot_windows": len(plan) - min(top_shots, len(shots)),
            "shot_windows": min(top_shots, len(shots))}


def select_for_gating(kept, plan, controls: int = 20, served=()) -> list:
    """The candidates worth re-gating: the planned windows plus a control set.

    The planned ones are the candidates whose bracketing frames were bought, so
    the fused census can decide them.  The control set is the next strongest
    candidates that got *no* SAM3 frames: re-gating them shows what the
    classical layer alone still claims, which is how the false-positive classes
    (occlusion, colour mis-assignment, exposure change) get counted instead of
    guessed at.  ``served`` are the events the app is already serving: they are
    re-measured too, so a queue rewrite can keep them instead of silently
    dropping what the owner already has.
    """
    planned = {round(entry["candidate"]["t"], 3) for entry in plan["plan"]}
    selected = [dict(candidate, measured="sam3") for candidate in kept
                if round(candidate["t"], 3) in planned]
    spare = [candidate for candidate in kept if round(candidate["t"], 3) not in planned]
    selected += [dict(candidate, measured="classical") for candidate in spare[:controls]]
    known = {round(float(event.get("t") or 0.0), 3) for event in selected}
    for event in served:
        if round(float(event.get("t") or 0.0), 3) in known:
            continue
        selected.append(dict(event, measured="served", origin="served"))
    for index, candidate in enumerate(selected, start=1001):
        # Ids above the served queue's range: a regenerated candidate must never
        # inherit an id the owner has already voted on.  An event the queue
        # already carries keeps *its* id -- renaming it would orphan the verdicts
        # recorded against it.  ``source`` keeps the queue's own value (the
        # schema the app reads); where the candidate came from goes in the
        # additive ``origin`` field.
        if candidate.get("id") is None:
            candidate["id"] = index
        candidate["origin"] = candidate.get("origin") or candidate.get("source") or "unknown"
        candidate["source"] = "info-complete"
        candidate["window_s"] = [round(candidate["t"] - 1.0, 2), round(candidate["t"] + 2.5, 2)]
    return selected


def _reason_counts(dropped) -> dict:
    """False-positive classes the prune already removed, with counts."""
    counts: dict = {}
    for candidate in dropped:
        for reason in candidate.get("drop_reasons", []):
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def write_plan(scan_path, out_dir="out/scan30", top_pots: int = 12, top_shots: int = 8,
               controls: int = 20, recompute: bool = True) -> dict:
    """Load a raw scan, prune, plan the SAM3 spend, write the artifacts.

    ``recompute`` re-derives the candidates from the stored frame records with
    the current rules: the records are the expensive part (a full-VOD decode),
    the derivation is not, so a rule change never costs another scan.
    """
    payload = json.loads(Path(scan_path).read_text())
    cfg = ScanConfig(**{k: v for k, v in (payload.get("config") or {}).items()
                        if k in ScanConfig.__dataclass_fields__})
    records = payload.get("records") or []
    if recompute and records and payload.get("scan", {}).get("quad"):
        H = homography_to_canonical(np.array(payload["scan"]["quad"], np.float32))
        candidates = raw_candidates(records, H, cfg)
        pruned = prune(candidates, records, cfg)
    else:
        pruned = {"kept": payload["candidates"], "dropped": payload.get("dropped", []),
                  "counts": payload.get("counts", {})}
    cached = {}
    cache_path = Path(out_dir) / "sam3_census.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text()).get("frames", {})
        except ValueError:
            cached = {}
    served = []
    served_path = events_document.document_in(out_dir)
    if served_path.exists():
        try:
            # A document this module cannot read plans nothing (as before).  A
            # document newer than the owner knows is not skipped: the owner
            # raises DocumentVersionError, which is not a ValueError.
            served = events_document.read(served_path).rows
        except ValueError:
            served = []
    plan = plan_sam3(pruned["kept"], top_pots=top_pots, top_shots=top_shots,
                     cached=[float(t) for t in cached], served=served)
    selected = select_for_gating(pruned["kept"], plan, controls=controls, served=served)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "sam3_plan.json").write_text(json.dumps(
        {"frames": plan["frames"], "to_buy": plan["to_buy"], "counts": pruned["counts"],
         "dropped_reasons": _reason_counts(pruned.get("dropped", [])),
         "windows": [{"kind": e["kind"], "t": e["t"], "strength": e["strength"],
                      "candidate": {k: v for k, v in e["candidate"].items()
                                    if k not in ("record", "pair_record")}}
                     for e in plan["plan"]]}, indent=1))
    (Path(out_dir) / "candidates_selected.json").write_text(json.dumps(selected, indent=1))
    return {"plan": plan, "selected": selected, "cfg": cfg, "counts": pruned["counts"]}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", default=media_relpath(ROOT, "vod30"))
    ap.add_argument("--out", default="out/scan30/raw_scan.json")
    ap.add_argument("--limit-s", type=float, default=None)
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--plan-only", action="store_true",
                    help="reuse an existing scan artifact: prune, plan, select")
    ap.add_argument("--top-pots", type=int, default=12)
    ap.add_argument("--top-shots", type=int, default=8)
    ap.add_argument("--controls", type=int, default=20)
    args = ap.parse_args()
    cfg = ScanConfig(stride=args.stride)
    if args.plan_only:
        result = write_plan(args.out, top_pots=args.top_pots, top_shots=args.top_shots,
                            controls=args.controls)
        print(json.dumps({"plan_windows": len(result["plan"]["plan"]),
                          "frames_to_buy": len(result["plan"]["to_buy"]),
                          "selected": len(result["selected"]),
                          "to_buy": result["plan"]["to_buy"]}, indent=1), flush=True)
        return
    scan = frame_records(args.video, cfg, limit_s=args.limit_s,
                         progress=lambda text: print(f"scan: {text}", flush=True))
    H = homography_to_canonical(np.array(scan["quad"], np.float32)) if scan["quad"] else None
    candidates = raw_candidates(scan["records"], H, cfg) if H is not None else []
    pruned = prune(candidates, scan["records"], cfg)
    payload = {"config": asdict(cfg), "scan": {k: v for k, v in scan.items() if k != "records"},
               "records": scan["records"], "candidates": pruned["kept"],
               "dropped": pruned["dropped"], "counts": pruned["counts"]}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=1))
    print(json.dumps(pruned["counts"], indent=1), flush=True)
    print(f"-> {args.out} ({scan['seconds']}s scan)", flush=True)


if __name__ == "__main__":
    main()