"""Measure what face identification actually does on the tournament footage.

This is a measurement tool, not a production path. It runs the *existing*
code — src/face_id.py (buffalo_l + quality gates + best_match) and
src/person_pipeline.py (detector -> tracker -> enroll_face / process_frame ->
bind_face) — unchanged, and writes only under ``out/face-eval/`` (the demo's
scratch root included). No production file, queue entry or identity index is
touched, and md5s of the protected files are recorded around the demo.

Three questions, three numbers:

1. detectability (``measure`` + ``analyse``): of the person instances the
   production YOLO detector finds, how many yield a face that passes the
   production quality gates (eye_px >= MIN_EYE_PX, det_score >= MIN_DET_SCORE),
   by face size and by distance proxy (person box height / position from the
   table end);
2. separation (``analyse``): cosine distributions of within-tracklet pairs
   (same person, <=4.5s apart) vs same-frame cross-tracklet pairs (provably
   different people), against the effective binding bar 0.47 = threshold 0.35 +
   margin 0.12 (see src/face_id.py: accept_match / DEFAULT_BIND_BAR);
3. end to end (``demo``): enroll one face photo per player through
   PersonPipeline.enroll_face — the exact function ``POST /api/identity/enroll``
   calls — into an isolated scratch root, then replay held-out frames through
   PersonPipeline.process_frame and report which clusters bound and at what
   similarity.

Sampling is burst based: ``anchors`` anchors spread over the VOD, each one a
burst of ``burst`` frames every ``spacing`` frames (default 15 frames = 0.5s at
30fps, so a burst covers 4.5s). Bursts are what make tracklet linking possible
(IoU >= 0.5 between consecutive sampled frames inside one burst); the anchors
spread the sample over the whole session.

CLI:
  .venv/bin/python -m src.eval_faces measure --dir out/face-eval
  .venv/bin/python -m src.eval_faces analyse --dir out/face-eval
  .venv/bin/python -m src.eval_faces demo    --dir out/face-eval
  .venv/bin/python -m src.eval_faces serve   --root out/face-eval/scratch --port 8133
"""
from __future__ import annotations

import base64
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

from src.face_id import (
    DEFAULT_MARGIN,
    DEFAULT_THRESHOLD,
    MIN_DET_SCORE,
    MIN_EYE_PX,
    accept_match,
    best_match,
    quality,
)
from src.person_identity import IdentityIndex

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DIR = REPO / "out" / "face-eval"

DATASETS = {  # id -> (video path relative to repo, scan dir, frame width)
    "vod30": ("data/vod_30min_260815.mp4", "scan30", 1280),
    "highlight": ("data/vod_highlight.mp4", "scan_highlight", 1920),
}
# Sampling plan defaults: 16 anchors x 10 frames on the 30-minute VOD plus
# 8 x 10 on the short one = 240 frames, ~35 person instances per anchor burst.
DEFAULT_PLAN = {"vod30": {"anchors": 16, "burst": 10, "spacing": 15, "start": 300},
                "highlight": {"anchors": 8, "burst": 10, "spacing": 15, "start": 300}}

IOU_LINK = 0.5           # same person inside a burst (0.5s apart at 30fps)
HEIGHT_BUCKETS = ((0, 250, "far"), (250, 400, "mid"), (400, 10_000, "near"))

# Files the demo must never write. Recorded as md5 before/after.
PROTECTED = (
    "out/corner-pocket/state.json",
    "out/pid_seed.json",
    "out/scan30/annotations.json",
    "out/identity/clusters.json",
    "out/corner-pocket/face_embeddings.json",
)


# --------------------------------------------------------------------------
# geometry helpers (pure)
# --------------------------------------------------------------------------

def burst_frames(frame_count, anchors, burst, spacing, start=0):
    """Frame indices to read: `anchors` anchors, each a `burst`-long run.

    The anchors are evenly spread from `start` to the end of the VOD; inside a
    burst the frames are `spacing` apart (0.5s at 30fps keeps IoU linking of a
    standing player above IOU_LINK). Duplicates are dropped, result is sorted.
    """
    frame_count = int(frame_count)
    anchors, burst, spacing = int(anchors), int(burst), int(spacing)
    if frame_count <= 0 or anchors <= 0 or burst <= 0 or spacing < 1:
        return []
    start = max(0, min(int(start), frame_count - 1))
    span = frame_count - start
    plan = []
    for anchor_index in range(anchors):
        anchor = start + (span * anchor_index) // anchors
        for offset in range(burst):
            index = int(anchor) + offset * spacing
            if index < frame_count:
                plan.append(index)
    return sorted(set(plan))


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def box_center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def box_foot(box):
    """Bottom-centre of a person box: the floor point, nearest to a table end."""
    return ((box[0] + box[2]) / 2.0, float(box[3]))


def center_inside(box, person):
    x, y = box_center(box)
    return person[0] <= x <= person[2] and person[1] <= y <= person[3]


def height_bucket(height):
    for low, high, name in HEIGHT_BUCKETS:
        if low <= height < high:
            return name
    return "far"


def end_points(corners):
    """(left_end, right_end) midpoints of the two short cloth edges.

    Corners follow the repo order [far-left, far-right, near-right, near-left]
    (annotator/app.js POCKET_ANCHOR_ORDER): the far edge is 0-1, the near edge
    2-3, so the short ends are 0-3 (left) and 1-2 (right).
    """
    pts = np.asarray(corners, float)
    if pts.shape != (4, 2):
        return None
    return ((pts[0] + pts[3]) / 2.0, (pts[1] + pts[2]) / 2.0)


def table_role(person_box, corners):
    """"left"/"right" table end this person stands at, by foot-point distance."""
    ends = end_points(corners) if corners is not None else None
    if ends is None:
        return None
    foot = np.asarray(box_foot(person_box), float)
    left, right = ends
    return "left" if np.linalg.norm(foot - left) <= np.linalg.norm(foot - right) else "right"


def load_corners(scan_dir):
    """Cloth quad for a dataset; the highlight VOD reuses the vod30 corners file."""
    for name in (scan_dir, "scan30"):
        path = REPO / "out" / name / "corners.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        corners = data.get("corners") if isinstance(data, dict) else None
        if corners:
            return corners
    return None


# --------------------------------------------------------------------------
# tracklet linking (pure)
# --------------------------------------------------------------------------

def assign_tracklets(records, iou_min=IOU_LINK, max_gap=None):
    """Greedy IoU linking of person boxes inside one burst -> record['tracklet'].

    Only boxes inside the same burst are linked, and only across consecutive
    sampled frames (a gap larger than `max_gap` frames starts a new tracklet),
    so a tracklet never spans the jump between two anchors. Returns the number
    of tracklets created.
    """
    created = 0
    pools = {}      # (dataset, burst) -> [(tracklet, frame_index, box)]
    previous = {}   # (dataset, burst) -> last frame index seen
    for rec in sorted(records, key=lambda r: (r["dataset"], r["burst"], r["frame_index"])):
        key = (rec["dataset"], rec["burst"])
        pool = pools.get(key, [])
        last = previous.get(key)
        if max_gap is not None and last is not None and rec["frame_index"] - last > max_gap:
            pool = []
        matched = None
        scored = [(iou(rec["person"], box), index, tracklet)
                  for index, (tracklet, _frame, box) in enumerate(pool)]
        scored = [item for item in scored if item[0] >= iou_min]
        if scored:
            scored.sort(reverse=True)
            _score, index, matched = scored[0]
            pool = [item for position, item in enumerate(pool) if position != index]
        if matched is None:
            created += 1
            matched = f"{rec['dataset']}#b{rec['burst']}#{created}"
        pool.append((matched, rec["frame_index"], rec["person"]))
        pools[key] = pool
        previous[key] = rec["frame_index"]
        rec["tracklet"] = matched
    return created


# --------------------------------------------------------------------------
# statistics (pure)
# --------------------------------------------------------------------------

def pair_stats(values):
    """n / min / p05 / median / p95 / max of a list of cosines."""
    values = [float(v) for v in values]
    if not values:
        return {"n": 0, "min": None, "p05": None, "median": None, "p95": None, "max": None}
    arr = np.asarray(values, float)
    return {"n": len(values),
            "min": round(float(arr.min()), 4),
            "p05": round(float(np.percentile(arr, 5)), 4),
            "median": round(float(np.median(arr)), 4),
            "p95": round(float(np.percentile(arr, 95)), 4),
            "max": round(float(arr.max()), 4)}


def _cos(a, b):
    a = np.asarray(a, np.float32).ravel()
    b = np.asarray(b, np.float32).ravel()
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na <= 0 or nb <= 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def quality_faces(record):
    """The production-selected face on this instance, or None.

    Mirrors src/person_pipeline.py:_quality_faces + process_frame: among the
    quality-gated faces, the first whose centre falls inside the person box.
    """
    for face in record.get("faces", []):
        if face.get("quality") and center_inside(face["bbox"], record["person"]):
            return face
    return None


def detectability(records, threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN):
    """Per-person-instance face yield, per gate, per size and per distance proxy.

    Every gate is counted per person instance (not per face): `found_a_face` is
    "this person had a face detected at any quality", `production_selection` is
    "process_frame would have had a face to match for this person".
    """
    gate = {"found_a_face": 0, "face_inside_box": 0, "eye_px_pass": 0,
            "det_score_pass": 0, "quality_pass": 0, "production_selection": 0}
    eye_all, eye_quality, det_all, det_quality = [], [], [], []
    size = {"all_w": [], "all_h": [], "quality_w": [], "quality_h": []}
    buckets, datasets, segments = {}, {}, {}
    for rec in records:
        faces = rec.get("faces", [])
        usable = quality_faces(rec)
        gate["found_a_face"] += 1 if faces else 0
        gate["face_inside_box"] += 1 if any(f["inside"] for f in faces) else 0
        gate["eye_px_pass"] += 1 if any(
            f.get("eye_px") is not None and f["eye_px"] >= MIN_EYE_PX for f in faces) else 0
        gate["det_score_pass"] += 1 if any(f["det_score"] >= MIN_DET_SCORE for f in faces) else 0
        gate["quality_pass"] += 1 if any(f["quality"] for f in faces) else 0
        gate["production_selection"] += 1 if usable is not None else 0
        rows = (buckets.setdefault(height_bucket(rec["person_h"]),
                                   {"person_instances": 0, "with_quality_face": 0}),
                datasets.setdefault(rec["dataset"], {"person_instances": 0, "with_quality_face": 0}),
                segments.setdefault(rec.get("segment"), {"person_instances": 0, "with_quality_face": 0}))
        for row in rows:
            row["person_instances"] += 1
            row["with_quality_face"] += 1 if usable is not None else 0
        for face in faces:
            width = face["bbox"][2] - face["bbox"][0]
            height = face["bbox"][3] - face["bbox"][1]
            det_all.append(face["det_score"])
            size["all_w"].append(width)
            size["all_h"].append(height)
            if face.get("eye_px") is not None:
                eye_all.append(face["eye_px"])
            if face.get("quality"):
                det_quality.append(face["det_score"])
                size["quality_w"].append(width)
                size["quality_h"].append(height)
                if face.get("eye_px") is not None:
                    eye_quality.append(face["eye_px"])
    for row in list(buckets.values()) + list(datasets.values()) + list(segments.values()):
        row["yield"] = _rate(row["with_quality_face"], row["person_instances"])
    return {
        "person_instances": len(records),
        "gate_person": {key: {"n": value, "rate": _rate(value, len(records))}
                        for key, value in gate.items()},
        "faces_detected": len(det_all),
        "eye_px": {"all": pair_stats(eye_all), "quality": pair_stats(eye_quality)},
        "det_score": {"all": pair_stats(det_all), "quality": pair_stats(det_quality)},
        "face_size_px": {key: pair_stats(value) for key, value in size.items()},
        "by_height_bucket": buckets,
        "by_dataset": datasets,
        "by_session_segment": {str(key): value for key, value in sorted(
            segments.items(), key=lambda item: (item[0] is None, item[0]))},
        "thresholds": {"eye_px": MIN_EYE_PX, "det_score": MIN_DET_SCORE,
                       "cosine": threshold, "margin": margin},
    }


def _rate(part, whole):
    return round(float(part) / float(whole), 4) if whole else None


def _medoid(points):
    """The point most similar to the others in its group (robust to one outlier)."""
    if len(points) == 1:
        return points[0]
    best, best_score = points[0], -2.0
    for candidate in points:
        score = sum(_cos(candidate[3], other[3]) for other in points if other is not candidate)
        if score > best_score:
            best, best_score = candidate, score
    return best


def separation(records, threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN):
    """Within-tracklet vs same-frame cross-tracklet cosine distributions.

    within: two faces on the same tracklet from different frames (same person,
    <=4.5s apart). cross: two faces from different person boxes *in the same
    frame* — provably different people, no tracking assumption.

    Pairs that point at the *same* detected face are dropped: two overlapping
    person boxes can both contain one face's centre (center_inside is per-box),
    and counting that face against itself would put a cosine of exactly 1.0
    into the cross-person distribution.
    """
    by_frame, by_tracklet = {}, {}
    faces = {}
    for rec in records:
        face = quality_faces(rec)
        if face is None:
            continue
        key = (rec["dataset"], rec["frame_index"], tuple(face["bbox"]))
        point = {"dataset": rec["dataset"], "tracklet": rec["tracklet"], "role": rec.get("role"),
                 "embedding": face["embedding"], "frame": rec["frame_index"], "face_key": key}
        faces[key] = faces.get(key, 0) + 1
        by_frame.setdefault((rec["dataset"], rec["frame_index"]), []).append(point)
        by_tracklet.setdefault(rec["tracklet"], []).append(point)
    shared = sum(1 for count in faces.values() if count > 1)

    within, within_by_dataset = [], {}
    for points in by_tracklet.values():
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                if points[i]["frame"] == points[j]["frame"]:
                    continue
                value = _cos(points[i]["embedding"], points[j]["embedding"])
                within.append(value)
                within_by_dataset.setdefault(points[i]["dataset"], []).append(value)
    cross, cross_by_dataset, duplicate_pairs = [], {}, 0
    for points in by_frame.values():
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                if points[i]["tracklet"] == points[j]["tracklet"]:
                    continue
                if points[i]["face_key"] == points[j]["face_key"]:
                    duplicate_pairs += 1
                    continue
                value = _cos(points[i]["embedding"], points[j]["embedding"])
                cross.append(value)
                cross_by_dataset.setdefault(points[i]["dataset"], []).append(value)
    return {
        "thresholds": {"cosine": threshold, "margin": margin,
                       "bind_face_bar": round(threshold + margin, 4)},
        "within_tracklet": pair_stats(within),
        "cross_person_same_frame": pair_stats(cross),
        "same_face_pairs_dropped": duplicate_pairs,
        "faces_claimed_by_both_boxes": shared,
        "by_dataset": {"within_tracklet": {name: pair_stats(values)
                                           for name, values in within_by_dataset.items()},
                       "cross_person_same_frame": {name: pair_stats(values)
                                                   for name, values in cross_by_dataset.items()}},
        "accept_rates": {
            "within_ge_threshold": _rate(sum(1 for v in within if v >= threshold), len(within)),
            "within_ge_bind_face_bar": _rate(sum(1 for v in within if v >= threshold + margin), len(within)),
            "cross_ge_threshold": _rate(sum(1 for v in cross if v >= threshold), len(cross)),
            "cross_ge_bind_face_bar": _rate(sum(1 for v in cross if v >= threshold + margin), len(cross)),
        },
    }


def role_pairs(records, same_person_cosine=0.5):
    """Table-end roles: are the two players separable, and do they stay put?

    cross_role_same_frame: the two players at the two table ends in one frame —
    provably different people, the "between-track" class. Pairs that point at
    one detected face (two overlapping boxes, or a face the centre test claims
    twice) are dropped.

    same_role_consecutive_burst: cosine between the medoid face of one table end
    in an anchor and the medoid of the next anchor (~112s later on vod30) — how
    often the same person is still at that end, i.e. roster turnover.
    same_role_cross_burst: the raw same-role pair distribution across all
    anchors; bimodal when several different people stand at that end, which is
    what a rotating tournament looks like.
    """
    by_role, by_burst = {}, {}
    for rec in records:
        role = rec.get("role")
        face = quality_faces(rec)
        if role is None or face is None or face.get("embedding") is None:
            continue
        face_key = (rec["dataset"], rec["frame_index"], tuple(face["bbox"]))
        point = (rec["burst"], rec["frame_index"], face_key, face["embedding"])
        by_role.setdefault(role, []).append(point)
        by_burst.setdefault((rec["burst"], role), []).append(point)
    same, cross_burst = [], []
    for role, points in by_role.items():
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                if points[i][0] == points[j][0]:
                    continue
                same.append(_cos(points[i][3], points[j][3]))
    left, right = by_role.get("left", []), by_role.get("right", [])
    for _b1, _f1, key_a, emb_a in left:
        for _b2, _f2, key_b, emb_b in right:
            if key_a == key_b:
                continue
            cross_burst.append(_cos(emb_a, emb_b))
    # per-frame cross-role: the two players standing at the table at that moment
    frames = {}
    for rec in records:
        if rec.get("role") is None:
            continue
        face = quality_faces(rec)
        if face is not None and face.get("embedding") is not None:
            frames.setdefault((rec["burst"], rec["frame_index"]), {})[rec["role"]] = (
                (rec["dataset"], rec["frame_index"], tuple(face["bbox"])), face["embedding"])
    cross_frame = [_cos(roles["left"][1], roles["right"][1]) for roles in frames.values()
                   if "left" in roles and "right" in roles and roles["left"][0] != roles["right"][0]]
    continuity = []
    for role in ("left", "right"):
        bursts = sorted({burst for burst, name in by_burst if name == role})
        for first, second in zip(bursts, bursts[1:]):
            if second - first > 1:
                continue
            first_face = _medoid(by_burst[(first, role)])
            second_face = _medoid(by_burst[(second, role)])
            cosine = _cos(first_face[3], second_face[3])
            continuity.append({"role": role, "bursts": [first, second],
                               "cosine": round(float(cosine), 4),
                               "faces": [len(by_burst[(first, role)]), len(by_burst[(second, role)])],
                               "same_person": bool(cosine >= same_person_cosine)})
    return {
        "cross_role_same_frame": pair_stats(cross_frame),
        "same_role_cross_burst": pair_stats(same),
        "cross_role_cross_burst": pair_stats(cross_burst),
        "same_role_consecutive_burst": {
            "pairs": len(continuity),
            "same_person": sum(1 for row in continuity if row["same_person"]),
            "rate": _rate(sum(1 for row in continuity if row["same_person"]), len(continuity)),
            "same_person_cosine": same_person_cosine,
            "rows": continuity,
        },
        "faces_left": len(left), "faces_right": len(right),
    }


# --------------------------------------------------------------------------
# offline binding evaluation (pure)
# --------------------------------------------------------------------------

def evaluate_binding(probes, gallery, threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN):
    """Run the production gallery matcher over labelled probes.

    probes: [{'role': 'left'|'right', 'embedding': ...}]
    gallery: {player_id: [entry, ...]} as load_faces() returns it
    A probe is 'correct' when best_match names the gallery player enrolled for
    its role. 'accepted_by_bind_face' runs the same accept_match(..., bind=True)
    rule IdentityIndex.bind_face applies — similarity >= threshold + margin AND
    the runner-up trailing by >= margin — so a probe best_match rejected as
    ambiguous is not counted as biddable either.
    """
    rows = []
    for probe in probes:
        match = best_match(probe["embedding"], gallery, threshold=threshold, margin=margin)
        per_player = {pid: max(_cos(probe["embedding"], entry["embedding"] if isinstance(entry, dict) else entry)
                               for entry in (value if isinstance(value, list) else [value]))
                      for pid, value in gallery.items()} if gallery else {}
        ranked = sorted(per_player.items(), key=lambda kv: kv[1], reverse=True)
        best_pid, best_sim = ranked[0] if ranked else (None, 0.0)
        runner_up_value = ranked[1][1] if len(ranked) > 1 else None
        rows.append({
            "role": probe.get("role"),
            "expected": probe.get("expected"),
            "group": probe.get("group"),
            "burst": probe.get("burst"),
            "frame_index": probe.get("frame_index"),
            "matched": None if match is None else match["player_id"],
            "similarity": round(float(best_sim), 4),
            "runner_up": None if runner_up_value is None else round(float(runner_up_value), 4),
            "margin": None if runner_up_value is None else round(float(best_sim - runner_up_value), 4),
            "accepted_by_best_match": match is not None,
            "accepted_by_bind_face": accept_match(best_sim, runner_up_value, threshold=threshold,
                                                  margin=margin, bind=True),
            "rejected_below_threshold": bool(best_sim < threshold),
            "rejected_below_bind_face_bar": bool(best_sim < threshold + margin),
            "rejected_ambiguous": bool(best_sim >= threshold and runner_up_value is not None
                                       and best_sim - runner_up_value < margin),
        })
    expected = [row for row in rows if row["expected"]]
    correct = [row for row in expected if row["matched"] == row["expected"]]
    wrong = [row for row in expected if row["matched"] is not None and row["matched"] != row["expected"]]
    groups = {}
    for row in rows:
        if row.get("group") is None:
            continue
        bucket = groups.setdefault(row["group"], {"n": 0, "similarities": [], "margins": [],
                                                  "matched_any": 0, "matched_expected": 0,
                                                  "accepted_by_bind_face": 0})
        bucket["n"] += 1
        bucket["similarities"].append(row["similarity"])
        if row["margin"] is not None:
            bucket["margins"].append(row["margin"])
        bucket["matched_any"] += 1 if row["matched"] else 0
        bucket["matched_expected"] += 1 if row["expected"] and row["matched"] == row["expected"] else 0
        bucket["accepted_by_bind_face"] += 1 if row["accepted_by_bind_face"] else 0
    for bucket in groups.values():
        bucket["similarity_stats"] = pair_stats(bucket.pop("similarities"))
        bucket["margin_stats"] = pair_stats(bucket.pop("margins"))
        bucket["match_rate"] = _rate(bucket["matched_expected"], bucket["n"])
        bucket["false_match_rate"] = _rate(bucket["matched_any"], bucket["n"])
    by_role = {}
    for row in expected:
        bucket = by_role.setdefault(row["role"], {"n": 0, "correct": 0, "accepted": 0,
                                                  "similarities": [], "margins": []})
        bucket["n"] += 1
        bucket["correct"] += 1 if row["matched"] == row["expected"] else 0
        bucket["accepted"] += 1 if row["accepted_by_bind_face"] else 0
        bucket["similarities"].append(row["similarity"])
        if row["margin"] is not None:
            bucket["margins"].append(row["margin"])
    for bucket in by_role.values():
        bucket["similarity_stats"] = pair_stats(bucket.pop("similarities"))
        bucket["margin_stats"] = pair_stats(bucket.pop("margins"))
        bucket["accuracy"] = _rate(bucket["correct"], bucket["n"])
    return {
        "rows": rows,
        "summary": {
            "probes_with_label": len(expected),
            "correct": len(correct),
            "wrong_player": len(wrong),
            "accuracy": _rate(len(correct), len(expected)),
            "unmatched": len(expected) - len(correct) - len(wrong),
            "by_role": by_role,
            "by_group": groups,
            "thresholds": {"cosine": threshold, "margin": margin,
                           "bind_face_bar": round(threshold + margin, 4)},
        },
    }


def digest(report):
    """Headline numbers of an analysis report, small enough to print."""
    detect = report["detectability"]
    sep = report["separation"]
    return {
        "sampled_frames": report["sampled_frames"],
        "person_instances": detect["person_instances"],
        "faces_detected": detect["faces_detected"],
        "gate_person_yield": detect["gate_person"],
        "face_size_px_quality": detect["face_size_px"]["quality_w"],
        "face_size_px_quality_h": detect["face_size_px"]["quality_h"],
        "eye_px_quality": detect["eye_px"]["quality"],
        "det_score_quality": detect["det_score"]["quality"],
        "by_dataset": detect["by_dataset"],
        "by_height_bucket": detect["by_height_bucket"],
        "separation": sep,
        "role_pairs": report["role_pairs"],
        "tracklets": report["tracklets"],
    }


# --------------------------------------------------------------------------
# model stages (production code paths)
# --------------------------------------------------------------------------

def load_detector(root=REPO):
    """The production person detector (PersonPipeline._get_detector, unchanged)."""
    from src.person_pipeline import PersonPipeline
    return PersonPipeline(root)._get_detector()


def iter_frames(video, plan):
    """Yield (frame_index, frame) for the sorted `plan`, reading sequentially.

    grab()/retrieve() on a monotonically advancing cursor: no per-frame seek,
    which is what makes a 240-frame sample over two VODs cheap.
    """
    import cv2
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    try:
        wanted = sorted(int(i) for i in plan)
        cursor, position = 0, 0
        while position < len(wanted):
            if not cap.grab():
                break
            if cursor == wanted[position]:
                ok, frame = cap.retrieve()
                if ok:
                    yield cursor, frame
                position += 1
            cursor += 1
    finally:
        cap.release()


def instance_records(dataset, burst, frame_index, fps, person_boxes, faces, corners):
    """One record per YOLO person box, with its faces and table-end role."""
    records = []
    for box, score in person_boxes:
        height = float(box[3] - box[1])
        record = {
            "dataset": dataset, "burst": burst, "frame_index": int(frame_index),
            "t": round(frame_index / fps, 3), "person": [round(float(v), 2) for v in box],
            "person_score": round(float(score), 4), "person_h": round(height, 2),
            "role": table_role(box, corners), "segment": int(frame_index / fps // 300),
            "faces": [],
        }
        for face in faces:
            record["faces"].append({
                "bbox": [round(float(v), 2) for v in face["bbox"]],
                "eye_px": None if face.get("eye_px") is None else round(float(face["eye_px"]), 2),
                "det_score": round(float(face["det_score"]), 4),
                "quality": bool(quality(face)),
                "inside": bool(center_inside(face["bbox"], box)),
                "embedding": (None if face["det_score"] < MIN_DET_SCORE
                              else [round(float(v), 4) for v in np.asarray(face["embedding"], np.float32)]),
            })
        records.append(record)
    return records


def measure(directory=DEFAULT_DIR, dataset_ids=("vod30", "highlight"), plan=None, log=print):
    """Run the production detector + face engine over the sampling plan."""
    from src.face_id import get_face_engine
    import cv2
    plan = plan or DEFAULT_PLAN
    detector = load_detector()
    engine = get_face_engine()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"datasets": {}, "records": [], "started_at": None, "runtime_s": None}
    import time
    started = time.time()
    for dataset_id in dataset_ids:
        video_rel, scan_dir, _width = DATASETS[dataset_id]
        video = REPO / video_rel
        cap = cv2.VideoCapture(str(video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        cfg = dict(plan.get(dataset_id, {}))
        frames = burst_frames(frame_count, cfg.get("anchors", 8), cfg.get("burst", 10),
                              cfg.get("spacing", 15), cfg.get("start", 300))
        corners = load_corners(scan_dir)
        payload["datasets"][dataset_id] = {
            "video": video_rel, "frame_count": frame_count, "fps": round(fps, 3),
            "frames_sampled": len(frames), "corners": corners, "plan": cfg, "burst_frames": frames}
        bursts = {}
        for position, index in enumerate(frames):
            bursts[index] = position // max(1, cfg.get("burst", 10))
        for frame_index, frame in iter_frames(video, frames):
            detections = detector(frame)
            persons = [(d["bbox"], d.get("conf", 0.0)) for d in detections]
            faces = engine.analyze(frame)
            records = instance_records(dataset_id, bursts.get(frame_index, 0), frame_index,
                                       fps, persons, faces, corners)
            payload["records"].extend(records)
            log(f"{dataset_id} f{frame_index} t={frame_index / fps:.1f}s "
                f"persons={len(persons)} faces={len(faces)}", flush=True)
    created = assign_tracklets(payload["records"], max_gap=60)
    payload["tracklets"] = created
    payload["runtime_s"] = round(time.time() - started, 1)
    path = directory / "detections.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    log(f"wrote {path}: {len(payload['records'])} person instances, "
        f"{created} tracklets, {payload['runtime_s']}s", flush=True)
    return payload


def analyse(directory=DEFAULT_DIR, log=print):
    """Detectability + separation over a detections.json (no models)."""
    directory = Path(directory).resolve()
    payload = json.loads((directory / "detections.json").read_text(encoding="utf-8"))
    records = payload["records"]
    report = {
        "datasets": {name: {"frames_sampled": meta["frames_sampled"], "frame_count": meta["frame_count"],
                            "fps": meta["fps"]}
                     for name, meta in payload["datasets"].items()},
        "sampled_frames": sum(meta["frames_sampled"] for meta in payload["datasets"].values()),
        "recorded_person_instances": len(records),
        "tracklets": payload.get("tracklets"),
        "detectability": detectability(records),
        "separation": separation(records),
        "role_pairs": {name: role_pairs([r for r in records if r["dataset"] == name])
                       for name in payload["datasets"]},
        "thresholds": {"eye_px": MIN_EYE_PX, "det_score": MIN_DET_SCORE,
                       "cosine": DEFAULT_THRESHOLD, "margin": DEFAULT_MARGIN},
    }
    path = directory / "analysis.json"
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    log(f"wrote {path}")
    return report


# --------------------------------------------------------------------------
# end-to-end demo on an isolated scratch root
# --------------------------------------------------------------------------

def md5_files(paths=PROTECTED, root=REPO):
    import hashlib
    out = {}
    for rel in paths:
        path = Path(root) / rel
        if not path.is_file():
            out[rel] = None
            continue
        digest = hashlib.md5()
        digest.update(path.read_bytes())
        out[rel] = digest.hexdigest()
    return out


def scratch_root(directory=DEFAULT_DIR, fresh=True, name="scratch"):
    """Isolated Backend/PersonPipeline root: symlinked media, own out/ stores.

    Mirrors tests/serve_workbench_fixture.py: annotator/src/data and the YOLO
    weights are read-only symlinks, every identity store lives under the
    scratch out/ so the demo can enroll and bind without touching production.
    """
    directory = Path(directory).resolve()
    root = directory / name
    if fresh and root.exists():
        shutil.rmtree(root)
    (root / "out" / "corner-pocket").mkdir(parents=True, exist_ok=True)
    (root / "out" / "identity").mkdir(parents=True, exist_ok=True)
    for entry in ("annotator", "data", "src", "yolov8n.pt"):
        link = root / entry
        if not link.exists():
            link.symlink_to(REPO / entry)
    return root


def pick_demo_window(analysis, dataset="vod30", min_run=3):
    """The longest run of consecutive anchors where one table end keeps its person.

    Taken from the measured continuity rows of `analyse` (medoid cosine between
    adjacent anchors >= 0.5): the first anchor enrolls, the later anchors of the
    run are the held-out frames. Outside such a run the same table end holds a
    *different* person every other minute (measured turnover), so a demo that
    spans the whole VOD would be testing the roster, not the face matcher.
    """
    try:
        rows = analysis["role_pairs"][dataset]["same_role_consecutive_burst"]["rows"]
    except (KeyError, TypeError):
        return None
    best = None
    for role in ("left", "right"):
        run = None
        for row in rows:
            if row["role"] != role:
                continue
            if not row["same_person"]:
                continue
            if run is not None and row["bursts"][0] == run[-1]:
                run.append(row["bursts"][1])
            else:
                run = list(row["bursts"])
            if best is None or len(run) > len(best["bursts"]):
                best = {"role": role, "bursts": list(run)}
    if best is None or len(best["bursts"]) < min_run:
        return None
    return {"dataset": dataset, "role": best["role"], "bursts": best["bursts"],
            "enroll_burst": best["bursts"][0], "holdout_bursts": best["bursts"][1:]}


def _role_faces(records, dataset, burst, role):
    """(record, face) of every quality face standing at `role` in one anchor."""
    rows = []
    for rec in sorted(records, key=lambda r: r["frame_index"]):
        if rec["dataset"] != dataset or rec["burst"] != burst or rec.get("role") != role:
            continue
        face = quality_faces(rec)
        if face is not None and face.get("embedding") is not None:
            rows.append((rec, face))
    return rows


def role_medoid(records, dataset, burst, role):
    """The person who most consistently holds one table end in one anchor.

    An anchor's burst covers 4.5s; over that window several people can stand
    near the same end (spectators, the opponent getting up). The medoid of the
    quality faces at that end is the recurring person, which is why enrollment
    uses it instead of the first frame's face.
    """
    rows = _role_faces(records, dataset, burst, role)
    if not rows:
        return None
    points = [(rec, np.asarray(face["embedding"], np.float32)) for rec, face in rows]
    best, best_score = points[0], -2.0
    for candidate in points:
        score = sum(_cos(candidate[1], other[1]) for other in points if other is not candidate[0])
        if score > best_score:
            best, best_score = candidate, score
    record, embedding = best
    return {"record": record, "embedding": embedding, "faces": len(rows),
            "spread_cosine": pair_stats([_cos(embedding, other[1]) for other in points])}


def label_role_probes(records, dataset, bursts, role, same_person_cosine=0.6):
    """Held-out probes at one table end, labelled by that anchor's medoid person.

    'same' probes are the faces of the recurring person at that end in their
    burst (the one the continuity rows tracked across anchors); 'other' probes
    are the rest of the faces at that same end — different people standing in
    the same place — plus (when asked) every quality face at the other end.
    """
    probes = []
    for burst in bursts:
        medoid = role_medoid(records, dataset, burst, role)
        if medoid is None:
            continue
        for rec, face in _role_faces(records, dataset, burst, role):
            same = _cos(medoid["embedding"], np.asarray(face["embedding"], np.float32)) >= same_person_cosine
            probes.append({"role": role, "expected": f"player-{role}" if same else None,
                           "group": "same" if same else "impostor_same_end",
                           "burst": burst, "frame_index": rec["frame_index"],
                           "medoid_cosine": round(float(_cos(medoid["embedding"],
                                                            np.asarray(face["embedding"], np.float32))), 4),
                           "embedding": np.asarray(face["embedding"], np.float32)})
    return probes


def _frame_with_role(records, dataset, burst, role, exclude=()):
    """The frame in `burst` whose quality face sits at `role` (first by index)."""
    for rec in sorted(records, key=lambda r: r["frame_index"]):
        if (rec["dataset"] == dataset and rec["burst"] == burst and rec.get("role") == role
                and quality_faces(rec) is not None and rec["frame_index"] not in exclude):
            return rec
    return None


def face_crop(frame, bbox, pad=0.6):
    """Photo-like crop around a face box: `pad` of its size on every side."""
    import cv2
    height, width = frame.shape[:2]
    box_w, box_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x0 = int(max(0, bbox[0] - box_w * pad))
    y0 = int(max(0, bbox[1] - box_h * pad))
    x1 = int(min(width, bbox[2] + box_w * pad))
    y1 = int(min(height, bbox[3] + box_h * pad))
    return cv2.resize(frame[y0:y1, x0:x1], None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)


def demo(directory=DEFAULT_DIR, dataset="vod30", log=print):
    """Enroll one photo per player, then bind held-out faces on a scratch root.

    Ground truth here is *positional*: inside the measured continuity window one
    person holds the chosen table end, so a held-out face at that end is the
    enrolled person and a face at the other end is provably someone else. The
    window comes from `analyse`, and every similarity in the result is reported
    so the reader can see how strong that assumption was.
    """
    import cv2
    from src.person_pipeline import PersonPipeline
    directory = Path(directory).resolve()
    payload = json.loads((directory / "detections.json").read_text(encoding="utf-8"))
    analysis_path = directory / "analysis.json"
    if not analysis_path.is_file():
        raise RuntimeError("run `analyse` first: the demo window comes from the measured continuity")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    corners = payload["datasets"][dataset]["corners"]
    window = pick_demo_window(analysis, dataset=dataset)
    if window is None:
        raise RuntimeError("no continuous table-end run long enough to seed a demo")
    records = payload["records"]

    # the players to enroll: the medoid person of the window role at the first
    # anchor of the run (A) plus the other end in the same anchor (B), so
    # cross-player rejection is testable when that end has a quality face
    enroll_role = window["role"]
    other_role = "right" if enroll_role == "left" else "left"
    enroll_records = [(enroll_role, role_medoid(records, dataset, window["enroll_burst"], enroll_role))]
    other = role_medoid(records, dataset, window["enroll_burst"], other_role)
    if other is not None:
        enroll_records.append((other_role, other))
    enroll_records = [(role, medoid) for role, medoid in enroll_records if medoid is not None]
    if not enroll_records:
        raise RuntimeError("no quality face in the enrollment burst")

    before = md5_files()
    root = scratch_root(directory)
    pipeline = PersonPipeline(root)

    # 1. enroll through the production function POST /api/identity/enroll calls
    enroll_frames = sorted({medoid["record"]["frame_index"] for _role, medoid in enroll_records})
    decoded = dict(iter_frames(REPO / DATASETS[dataset][0], enroll_frames))
    enrolled, enroll_rows = {}, []
    for role, medoid in enroll_records:
        record, face = medoid["record"], quality_faces(medoid["record"])
        crop = face_crop(decoded[record["frame_index"]], face["bbox"])
        player_id = f"player-{role}"
        count = pipeline.enroll_face(player_id, crop)
        enrolled[player_id] = count
        enroll_rows.append({"role": role, "player_id": player_id, "burst": record["burst"],
                            "frame_index": record["frame_index"], "enrolled": count,
                            "eye_px": face["eye_px"], "det_score": face["det_score"],
                            "crop_px": [int(crop.shape[1]), int(crop.shape[0])],
                            "faces_at_that_end": medoid["faces"],
                            "medoid_spread": medoid["spread_cosine"]})
        log(f"enroll {player_id}: {count} face(s) from {dataset} burst "
            f"{record['burst']} frame {record['frame_index']}", flush=True)

    # 2. held-out probes: the recurring person at the enrolled end (same), the
    #    other people standing in that same place (impostors), matched against
    #    the scratch gallery
    gallery = _gallery_from_scratch(root)
    probes = label_role_probes(records, dataset, window["holdout_bursts"], enroll_role)
    probes.extend({"role": rec["role"], "expected": None, "group": "impostor_other_end",
                   "burst": rec["burst"], "frame_index": rec["frame_index"], "medoid_cosine": None,
                   "embedding": np.asarray(face["embedding"], np.float32)}
                  for rec in records
                  if rec["dataset"] == dataset and rec["burst"] in window["holdout_bursts"]
                  and rec.get("role") not in (None, enroll_role)
                  and (face := quality_faces(rec)) is not None and face.get("embedding") is not None)
    offline = evaluate_binding(probes, gallery)

    # 3. end-to-end replay: process_frame -> tracker -> best_match -> bind_face
    holdout_frames = sorted({rec["frame_index"] for rec in records
                             if rec["dataset"] == dataset
                             and rec["burst"] in window["holdout_bursts"]})
    binds, persons_seen = [], []
    for frame_index, frame in iter_frames(REPO / DATASETS[dataset][0], holdout_frames):
        result = pipeline.process_frame(frame, frame_index,
                                        frame_index / payload["datasets"][dataset]["fps"])
        for person in result["persons"]:
            persons_seen.append({"frame_index": frame_index, "track_id": person["track_id"],
                                 "cluster_id": person["cluster_id"],
                                 "role": table_role(person["bbox"], corners),
                                 "player_id": person["player_id"], "face_sim": person["face_sim"]})
        for event in result["events"]:
            binds.append({"frame_index": frame_index, "player_id": event["player_id"],
                          "cluster_id": event["cluster_id"], "similarity": event["similarity"]})
        log(f"replay f{frame_index}: persons={len(result['persons'])} binds={len(result['events'])}",
            flush=True)

    bound = {}
    for person in persons_seen:
        if person["player_id"]:
            bound.setdefault(person["player_id"], set()).add(person["role"])
    replay = {
        "frames_replayed": len(holdout_frames),
        "persons_observed": len(persons_seen),
        "bind_events": binds,
        "bound_players": {pid: sorted(roles) for pid, roles in bound.items()},
        "wrong_role_binds": [b for b in binds if sorted(bound.get(b["player_id"], [])) !=
                             [b["player_id"].split("-")[-1]]],
        "person_rows": persons_seen,
    }
    after = md5_files()
    result = {
        "dataset": dataset,
        "window": window,
        "continuity_rows": [row for row in analysis["role_pairs"][dataset]
                            ["same_role_consecutive_burst"]["rows"]
                            if row["role"] == enroll_role and row["bursts"][0] in window["bursts"]],
        "enrollment": {"rows": enroll_rows, "gallery_players": sorted(gallery),
                       "gallery_entries": {pid: len(entries) for pid, entries in gallery.items()},
                       "store": str((root / "out" / "corner-pocket" / "face_embeddings.json").relative_to(REPO))},
        "offline_binding": offline,
        "replay_binding": replay,
        "md5_before": before, "md5_after": after,
        "protected_unchanged": {key: before[key] == after.get(key) for key in before},
    }
    path = directory / "demo.json"
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    log(f"wrote {path}: enrolled={enrolled} binds={len(binds)} "
        f"accuracy={offline['summary']['accuracy']}", flush=True)
    return result


def _quality_index(record):
    for index, face in enumerate(record["faces"]):
        if face.get("quality") and center_inside(face["bbox"], record["person"]):
            return index
    raise RuntimeError("record has no quality face")


def _gallery_from_scratch(root):
    from src.face_id import load_faces
    return load_faces(Path(root) / "out" / "corner-pocket" / "face_embeddings.json")


# --------------------------------------------------------------------------
# HTTP fixture server (isolated root, port 8133 by default)
# --------------------------------------------------------------------------

def serve(root, port=8133):
    """Serve the unified API against a scratch root (md5-protected reads only).

    Refuses the production root before importing the server, so a mistyped
    --root can never expose a service that writes production identity state.
    """
    root = Path(root).resolve()
    if REPO == root or REPO.is_relative_to(root):
        raise SystemExit(f"refusing to serve {root}: not a scratch root")
    from http.server import ThreadingHTTPServer
    sys.path.insert(0, str(REPO))
    from annotator.unified_server import Backend, make_handler
    backend = Backend(root)
    real = Backend(REPO)
    backend.video = real.video            # decoding stays read-only on the real VOD
    backend.frame = real.frame
    backend.frame_jpeg = real.frame_jpeg
    print(f"face-eval fixture: http://127.0.0.1:{port} root={root}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(backend)).serve_forever()


def _post(port, path, payload):
    import urllib.request
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read())


def _get(port, path):
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=600) as response:
        return json.loads(response.read())


def http_demo(port=8133, directory=DEFAULT_DIR, wait=120.0, max_frames=12, log=print):
    """Drive POST /api/identity/enroll + GET /api/identity/frame over HTTP.

    Assumes `serve` is already running on `port` against a scratch root that is
    still empty, so this checks the *route* wiring (base64 -> cv2.imdecode ->
    enroll_face -> store) and the read path (identity_frame -> process_frame ->
    bind_face) end to end over HTTP, not a second copy of the matching logic.
    """
    import time
    directory = Path(directory).resolve()
    deadline = time.time() + wait
    status = None
    while time.time() < deadline:
        try:
            status = _get(port, "/api/identity/status")
            break
        except Exception:
            time.sleep(2.0)
    if status is None:
        raise RuntimeError(f"fixture on port {port} never answered")
    payload = json.loads((directory / "detections.json").read_text(encoding="utf-8"))
    analysis = json.loads((directory / "analysis.json").read_text(encoding="utf-8"))
    window = pick_demo_window(analysis, dataset="vod30")
    if window is None:
        raise RuntimeError("run `analyse` first")
    dataset = window["dataset"]
    medoid = role_medoid(payload["records"], dataset, window["enroll_burst"], window["role"])
    if medoid is None:
        raise RuntimeError("no medoid face to enroll over HTTP")
    import cv2
    record = medoid["record"]
    result = {"status_before": status, "window": window, "enroll": []}
    for _index, frame in iter_frames(REPO / DATASETS[dataset][0], [record["frame_index"]]):
        crop = face_crop(frame, quality_faces(record)["bbox"])
        ok, encoded = cv2.imencode(".png", crop)
        if not ok:
            raise RuntimeError("PNG encode failed")
        response = _post(port, "/api/identity/enroll",
                         {"player_id": f"player-{window['role']}",
                          "image_base64": base64.b64encode(encoded.tobytes()).decode()})
        result["enroll"].append({"role": window["role"], "frame_index": record["frame_index"],
                                 **response})
        log(f"http enroll player-{window['role']}: {response}", flush=True)
    result["status_after_enroll"] = _get(port, "/api/identity/status")
    holdout = sorted({rec["frame_index"] for rec in payload["records"]
                      if rec["dataset"] == dataset and rec["burst"] in window["holdout_bursts"]})
    result["frames"] = []
    for frame_index in holdout[:max_frames]:
        frame_result = _get(port, f"/api/identity/frame?dataset={dataset}&frame={frame_index}")
        result["frames"].append({"frame_index": frame_index, "events": frame_result.get("events"),
                                 "persons": frame_result.get("persons")})
        log(f"http frame {frame_index}: events={len(frame_result.get('events', []))}", flush=True)
    result["status_after_frames"] = _get(port, "/api/identity/status")
    result["binds"] = [event for frame in result["frames"] for event in frame.get("events") or []]
    path = directory / "http-demo.json"
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    log(f"wrote {path}: binds={len(result['binds'])}", flush=True)
    return result


# --------------------------------------------------------------------------

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("measure", "analyse", "demo", "serve", "http-demo", "md5"))
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    parser.add_argument("--datasets", default="vod30,highlight")
    parser.add_argument("--anchors", type=int, default=None, help="override anchors per dataset")
    parser.add_argument("--burst", type=int, default=None)
    parser.add_argument("--spacing", type=int, default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--name", default="scratch", help="scratch root directory name")
    parser.add_argument("--port", type=int, default=8133)
    args = parser.parse_args(argv)
    if args.command == "measure":
        plan = {name: dict(DEFAULT_PLAN[name]) for name in DEFAULT_PLAN}
        for name, cfg in plan.items():
            for key in ("anchors", "burst", "spacing"):
                value = getattr(args, key)
                if value is not None:
                    cfg[key] = value
        measure(args.dir, tuple(args.datasets.split(",")), plan)
    elif args.command == "analyse":
        report = analyse(args.dir)
        print(json.dumps(digest(report), indent=1))
    elif args.command == "demo":
        demo(args.dir)
    elif args.command == "serve":
        serve(args.root or (Path(args.dir) / "scratch"), args.port)
    elif args.command == "http-demo":
        http_demo(args.port, args.dir)
    elif args.command == "md5":
        print(json.dumps(md5_files(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
