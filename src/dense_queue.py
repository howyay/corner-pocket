"""Put the dense-track events into the served queue, with their provenance.

The dense run's gate output is the authority for which candidates are events.
This tool copies the events the gate shaped as events into
`out/scan30/events.json` (what the review rail reads) and writes a report beside
it with everything that did *not* go in, including the channels that are neither
an event nor a rejection (`unresolved`) and the disappearances the gate calls
`situational`/unknown.

What the queue is not allowed to claim:

* **no tier is invented and none is upgraded.**  The existing vocabulary is
  `geometry` (the measured move matches a claim's own geometry) and `window` (a
  ball moved, but not the one or where a claim said).  A dense-track event has no
  separate claim to check the move against -- the gate derived the onset from the
  track itself -- so every shot here is `window` grade, and the pot candidate
  carries no tier at all.
* **the pot-shaped event is not a pot.**  It keeps `type: "pot"` (that is how the
  rail routes it to the POTS tab) but its gate status is `unconfirmed` with
  `cloth_occluded_at_disappearance`: the ball vanished while a person covered the
  cloth, so the honest verdict is *unknown*, and the operator watches the window.
* **an ambiguous pocket test is not a pot.**  The gate now decides the pocket in
  reference millimetres and carries the localisation error with it.  When that
  error straddles the pocket radius the gate reports `verdict_mm: "ambiguous"`,
  and the entry repeats the distance *with* its error bar instead of a bare
  number a reader would take as precise.
* **machine output is labelled as machine output** (`provenance.machine_produced`,
  `human_confirmed: false`), with the detector, the cadence and the run.

Ids are stable by identity.  An entry already served keeps the id it was served
with -- `provenance.ball_id` is the key -- because a human verdict may already
point at that id.  Ids of entries that left the queue are retired, never handed
to a different ball.  New ids start above every id ever issued here (>= 9001,
above every eval id (<= 1052) and distinct from the only id
`out/scan30/annotations.json` references (16)).  The verdict file is never opened
for writing, and its md5 is recorded before and after.

    PYTHONPATH=. .venv/bin/python src/dense_queue.py \
        --artifact out/dense-events/segment-1350-1650.gate2.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORK_W, WORK_H = 960, 540
NATIVE_W, NATIVE_H = 1280, 720
#: The detector and cadence the events came from, stated once and copied verbatim
#: into every entry.
DETECTOR = "dense-track · trained 960×540 net @ ball@2"
ID_BASE = 9001
ANNOTATIONS = "out/scan30/annotations.json"
#: Stored pocket keys are pool-table rail terms; the rail shows position words.
#: Any sentence built here has to use the shown word, because the rail only
#: translates the raw key when it renders `nearest_pocket`, not prose.
POCKET_WORDS = {"head-left": "top-left", "head-right": "top-right",
                "foot-left": "bottom-left", "foot-right": "bottom-right",
                "left-side": "left-middle", "right-side": "right-middle"}
POCKET_WORDS_ZH = {"head-left": "左上", "head-right": "右上", "foot-left": "左下",
                   "foot-right": "右下", "left-side": "左中", "right-side": "右中"}
#: "Still travelling at the last sighting" -- the split below is insensitive:
#: the stationary disappearances in this run move at <= 17.4 px/s, the moving
#: ones at >= 211.3 px/s, and the gate's own motion bar is 40 px/s.
MOVING_PX_S = 100.0


def _md5(path) -> str | None:
    path = Path(path)
    return hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else None


def calibration(artifact) -> tuple:
    """pixels (960x540 work space) -> canonical millimetres.

    The dense run's own cloth quad, which is the verified hand-anchor geometry
    scaled into the work frame, so the millimetres here are the same reference
    the rest of the project measures against.  Cross-checked below against the
    gate's own `distance_mm`: they agree within 0.13 mm in this run.
    """
    from src.pipeline import homography_to_canonical

    quad = np.array(artifact["thresholds"]["cloth_quad"], np.float32)
    native = quad * (NATIVE_W / WORK_W)
    return homography_to_canonical(native), quad


def to_mm(H, x, y):
    p = H @ np.array([x * NATIVE_W / WORK_W, y * NATIVE_H / WORK_H, 1.0])
    return None if abs(p[2]) < 1e-9 else [round(float(p[0] / p[2]), 1), round(float(p[1] / p[2]), 1)]


def _window(onset_t: float, duration_s: float) -> list:
    """The window the stage plays: the rest before it is what makes it readable."""
    before, after = 1.0, max(1.0, round(float(duration_s or 0.0) + 1.0, 2))
    return [round(onset_t - before, 2), round(onset_t + after, 2)]


def distance_sentence(distance_mm, uncertainty_mm, radius_mm, pocket, verdict_mm) -> tuple:
    """The pocket test in the words an operator needs, English and Chinese.

    A bare `148 mm` reads as precise and, next to a 100 mm pocket, as "in".  The
    error bar is what makes it honest, so the sentence always carries it.
    """
    if distance_mm is None:
        return None, None
    word, word_zh = POCKET_WORDS.get(pocket, pocket), POCKET_WORDS_ZH.get(pocket, pocket)
    span = f"{float(distance_mm):.0f}" + (f" ± {float(uncertainty_mm):.0f}" if uncertainty_mm is not None else "")
    bar = f"{float(radius_mm):.0f} mm" if radius_mm is not None else "the pocket radius"
    if verdict_mm == "inside":
        tail, tail_zh = f"inside the {bar} radius", f"在{bar}袋口范围内"
    elif verdict_mm == "outside":
        tail, tail_zh = f"outside the {bar} radius", f"在{bar}袋口范围外"
    else:
        tail, tail_zh = ("too uncertain to call -- it straddles the %s radius" % bar,
                         "误差跨过%s袋口范围，无法判定" % bar)
    return (f"{span} mm from the {word} pocket -- {tail}",
            f"距{word_zh}袋 {span} 毫米 —— {tail_zh}")


def shot_event(shot: dict, H, artifact) -> dict:
    start_mm = to_mm(H, *shot["onset"])
    # The move is measured between the onset and the end of the motion stretch:
    # the last sample the gate used, not the peak.
    samples = shot.get("samples_used") or []
    end = samples[-1] if samples else {"x": shot["onset"][0], "y": shot["onset"][1]}
    end_mm = to_mm(H, end["x"], end["y"])
    displacement = None
    if start_mm and end_mm:
        displacement = round(float(np.hypot(end_mm[0] - start_mm[0], end_mm[1] - start_mm[1])))
    frames = [int(s["frame_index"]) for s in samples] or [int(shot["onset_frame_index"])]
    bars = shot.get("thresholds") or {}
    numbers = {
        "disp_mm": displacement,               # projected, so the rail's own line renders
        "disp_color": shot["ball_id"].split("-", 1)[1],
        "dense_net_displacement_px": shot.get("net_displacement_px"),
        "dense_path_length_px": shot.get("path_length_px"),
        "dense_net_bar_px": bars.get("min_net_displacement_px"),
        "dense_net_bar_diameters": bars.get("min_net_displacement_diameters"),
        "dense_net_uncertainty_px": bars.get("net_uncertainty_px"),
        "dense_peak_speed_px_s": shot.get("peak_speed_px_s"),
        "dense_duration_s": shot.get("duration_s"),
        "dense_rest_before_s": shot.get("rest_window_measured_s"),
        "dense_ends_in_pocket": shot.get("ends_in_pocket"),
        "dense_end_distance_px": shot.get("end_distance_px"),
        "dense_frame_range": [min(frames), max(frames)],
    }
    return {
        "t": round(float(shot["onset_t"]), 1),
        "type": "shot",
        "verified": False,                      # no human verdict exists for it
        "source": "dense-track",
        "window_s": _window(shot["onset_t"], shot.get("duration_s")),
        "color": shot["ball_id"].split("-", 1)[1],
        "tier": "window",                       # no claim geometry to verify against
        "origin": "dense-track",
        "from_mm": start_mm, "to_mm": end_mm,
        "ball_from": start_mm, "ball_to": end_mm,
        "dup_count": 1,
        "gate": {"status": "confirmed", "gate": "motion", "tier": "window",
                 "reasons": ["dense_motion_onset", "window_grade_no_claim_to_check"],
                 "codes": ["dense_motion_onset", "window_grade_no_claim_to_check"],
                 "numbers": numbers,
                 "dup_count": 1, "colors_merged": [shot["ball_id"].split("-", 1)[1]]},
        "geometry_check": {"claim_start_mm": None, "claim_end_mm": None,
                           "measured_disp_mm": displacement, "gap_px": None, "tol_px": None,
                           "matches": None,
                           "note": "the onset comes from the track itself; there is no "
                                   "separate claim to check the move against, so this is "
                                   "window grade"},
        "provenance": provenance(artifact, {"ball_id": shot["ball_id"],
                                            "group_id": shot.get("group_id")}),
    }


def pot_event(pot: dict, H, artifact, served_reason: str | None = None,
              siblings_not_served: int | None = None) -> dict:
    last_mm = to_mm(H, *pot["last"])
    pocket_mm = to_mm(H, *pot["pocket_px"])
    projected_mm = None
    if last_mm and pocket_mm:
        projected_mm = round(float(np.hypot(pocket_mm[0] - last_mm[0], pocket_mm[1] - last_mm[1])), 2)

    # The gate's own millimetre measurement is served; the projection above is a
    # cross-check that both use the same reference geometry, and a mismatch is
    # named rather than hidden.
    gate_mm = pot.get("distance_mm")
    uncertainty_mm = pot.get("distance_mm_uncertainty")
    radius_mm = pot.get("radius_mm", artifact["thresholds"].get("pocket_r_mm"))
    verdict_mm = pot.get("verdict_mm")
    if radius_mm is None:
        radius_mm = artifact["thresholds"].get("pocket_r_mm")
    disagreement_mm = (None if gate_mm is None or projected_mm is None
                       else round(projected_mm - float(gate_mm), 2))
    agree = pot.get("pocket_test_disagrees_px_vs_mm")
    recomputed = not _pocket_agrees(pot, gate_mm)
    sentence, sentence_zh = distance_sentence(gate_mm, uncertainty_mm, radius_mm,
                                             pot["pocket"], verdict_mm)
    samples = pot.get("samples_used") or []
    frames = [int(s["frame_index"]) for s in samples] or [int(pot["last_frame_index"])]

    codes = ["cloth_occluded_at_disappearance"]
    if verdict_mm == "ambiguous":
        codes.append("pocket_distance_ambiguous_mm")
    if verdict_mm == "outside":
        codes.append("pocket_distance_outside_mm")
    codes.append("pocket_test_disagrees_px_vs_mm" if agree else "pocket_test_agrees")
    if disagreement_mm is not None and abs(disagreement_mm) > 1.0:
        codes.append("mm_projection_mismatch")
    if recomputed != bool(agree):
        codes.append("pocket_test_flag_mismatch")

    distance_lo = (None if gate_mm is None or uncertainty_mm is None
                   else round(float(gate_mm) - float(uncertainty_mm), 2))
    distance_hi = (None if gate_mm is None or uncertainty_mm is None
                   else round(float(gate_mm) + float(uncertainty_mm), 2))
    numbers = {
        # The distance as the gate measured it, with the bar the gate could not
        # clear: the number the operator has to read with its error.
        "vanish_dist_mm": gate_mm,
        "vanish_dist_mm_uncertainty": uncertainty_mm,
        "vanish_dist_mm_lo": distance_lo,
        "vanish_dist_mm_hi": distance_hi,
        "vanish_radius_mm": radius_mm,
        "vanish_verdict_mm": verdict_mm,
        "vanish_distance_text": sentence,
        "vanish_distance_text_zh": sentence_zh,
        "vanish_dist_mm_projected": projected_mm,
        "vanish_dist_mm_projection_delta": disagreement_mm,
        "vanish_inside_px": pot.get("inside_px"),
        "vanish_inside_mm": pot.get("inside_mm"),
        "vanish_pocket_test": pot.get("pocket_test"),
        "vanish_localisation_error_px": artifact["thresholds"].get("localisation_error_px"),
        "vanish_pocket": pot["pocket"],
        "vanish_dist_px": pot.get("distance_px"),
        "vanish_radius_px": pot.get("radius_px"),
        "vanish_last_speed_px_s": pot.get("last_speed_px_s"),
        "vanish_gap_s": pot.get("gap_s"),
        "vanish_persistence_s": pot.get("persistence_s"),
        "pocket_r_mm": artifact["thresholds"].get("pocket_r_mm"),
        "pocket_test_agrees": not agree,
        "pocket_test_recomputed_agrees": not recomputed,
        "pocket_test_note": (
            "the gate decides the pocket in reference millimetres and carries the "
            "localisation error (%.2f px) through the projection, so %.2f ± %.2f mm "
            "against the %.0f mm radius is %s; the pixel radius (%.2f px) says %s, "
            "because a pixel radius does not follow the perspective scale." % (
                artifact["thresholds"].get("localisation_error_px") or 0.0,
                gate_mm or 0.0, uncertainty_mm or 0.0, radius_mm or 0.0,
                verdict_mm or "unknown",
                pot.get("radius_px") or 0.0,
                "inside" if pot.get("inside_px") else "outside")),
        "occlusion_status": pot.get("occlusion_status"),
        "occlusion_source": pot.get("occlusion_source"),
        "occlusion_occ_dense": (pot.get("thresholds") or {}).get("occlusion_threshold"),
        "identity_swap_suspected": pot.get("identity_swap_suspected"),
        "parked_in_jaws_possible": pot.get("parked_in_jaws_possible"),
        "dense_frame_range": [min(frames), max(frames)],
    }
    return {
        "t": round(float(pot["last_t"]), 1),
        "type": "pot",
        "verified": False,
        "source": "dense-track",
        "window_s": [round(float(pot["last_t"]) - 1.5, 2), round(float(pot["last_t"]) + 1.5, 2)],
        "color": pot["ball_id"].split("-", 1)[1],
        "nearest_pocket": (f"{pot['pocket']} ({float(gate_mm):.0f} ± {float(uncertainty_mm):.0f}mm)"
                           if gate_mm is not None and uncertainty_mm is not None
                           else f"{pot['pocket']} ({gate_mm}mm)" if gate_mm is not None
                           else None),
        "pocket_name": pot["pocket"],
        "last_mm": last_mm, "last_px": pot["last"],
        "dup_count": 1,
        "tier": None,                            # no tier: a tier describes a claim's grade
        "origin": "dense-track",
        "gate": {"status": "unconfirmed", "gate": "occlusion",
                 "reasons": codes + ([sentence] if sentence else []),
                 "codes": codes,
                 "numbers": numbers,
                 "dup_count": 1, "colors_merged": [pot["ball_id"].split("-", 1)[1]]},
        "provenance": provenance(artifact, {"ball_id": pot["ball_id"],
                                           "gate_reason": pot.get("reason"),
                                           "gate_verdict": pot.get("verdict"),
                                           "served_because": served_reason,
                                           "unknowns_in_channel": siblings_not_served}),
    }


def _pocket_agrees(pot: dict, distance_mm) -> bool:
    """Do the pixel radius and the reference millimetre radius agree here?

    The gate's own flag is served; this is the local recomputation used to
    notice a mismatch, so a consumer never has to trust a single flag.
    """
    if distance_mm is None:
        return False
    radius_px = pot.get("radius_px")
    distance_px = pot.get("distance_px")
    inside_px = radius_px is not None and distance_px is not None and distance_px <= radius_px
    radius_mm = pot.get("radius_mm")
    inside_mm = distance_mm <= (100.0 if radius_mm is None else float(radius_mm))
    return inside_px == inside_mm


def provenance(artifact, extra: dict) -> dict:
    """Where the entry came from, in the payload the rail can print verbatim."""
    segment = artifact.get("segment", {})
    thresholds = artifact.get("thresholds", {})
    return {"detector": DETECTOR,
            "machine_produced": True,
            "human_confirmed": False,
            "statement": "machine-produced candidate; no human has confirmed it",
            "run": {"segment_s": [segment.get("start_s"), segment.get("start_s", 0) + segment.get("seconds", 0)],
                    "frames_decoded": segment.get("frames_decoded"),
                    "ball_samples": artifact.get("samples", {}).get("balls"),
                    "identities": artifact.get("tracks", {}).get("n"),
                    "occlusion_source": artifact.get("occlusion", {}).get("source"),
                    "gate_thresholds": {
                        "motion_speed_px_s": thresholds.get("motion_speed_px_s"),
                        "pocket_r_mm": thresholds.get("pocket_r_mm"),
                        "min_net_displacement_diameters": thresholds.get("min_net_displacement_diameters"),
                        "localisation_error_px": thresholds.get("localisation_error_px")}},
            **extra}


def _previous_ids(previous_path) -> dict:
    """ball_id -> id for everything the queue served before, whatever it was."""
    path = Path(previous_path)
    if not path.exists():
        return {}
    try:
        previous = json.loads(path.read_text())
    except ValueError:
        return {}
    if isinstance(previous, dict):
        previous = previous.get("events") or previous.get("items") or []
    held = {}
    for entry in previous if isinstance(previous, list) else []:
        provenance_block = entry.get("provenance") if isinstance(entry, dict) else None
        ball_id = provenance_block.get("ball_id") if isinstance(provenance_block, dict) else None
        if ball_id and isinstance(entry.get("id"), int):
            held[ball_id] = entry["id"]
    return held


def assign_ids(entries: list, previous_path) -> dict:
    """Ids are stable by identity, and a retired id is never handed to another ball.

    A verdict may already point at a served id, so the rule has to survive the
    queue changing shape underneath it: an entry whose ball was served before
    keeps its number, a new ball gets a number above everything ever issued
    here, and a ball that left the queue retires its number for good.
    """
    held = _previous_ids(previous_path)
    used = set(held.values())
    is_new = []
    for entry in entries:                      # already sorted by t
        ball_id = entry["provenance"]["ball_id"]
        if ball_id in held:
            entry["id"] = held[ball_id]
        else:
            is_new.append(entry)
    nxt = max([ID_BASE - 1] + sorted(used)) + 1
    for entry in is_new:
        while nxt in used:
            nxt += 1
        entry["id"] = nxt
        used.add(nxt)
        nxt += 1
    kept = {entry["provenance"]["ball_id"]: entry["id"] for entry in entries}
    return {"served_before": held,
            "reused": {b: i for b, i in held.items() if b in kept},
            "departed": {b: i for b, i in held.items() if b not in kept},
            "added": {entry["provenance"]["ball_id"]: entry["id"] for entry in is_new}}


def _bar_px(numbers: dict) -> float | None:
    """The net-displacement bar, recovered from the row itself: net + shortfall."""
    net, short = numbers.get("net_displacement_px"), numbers.get("bar_minus_net_px")
    return None if net is None or short is None else round(float(net) + float(short), 2)


def gate_ledger(artifact, id_plan: dict) -> dict:
    """The channels the queue does not serve, with their numbers.

    Three of them are easy to conflate and must not be: a *rejection* is the gate
    saying no, an *unresolved* run is the gate saying it cannot tell, and an
    *unknown* disappearance is the gate saying the ball is gone and nobody can
    say where.  Only the first is a decision.
    """
    gate = artifact.get("gate", {})
    rejections = gate.get("rejections") or []
    unresolved = gate.get("unresolved") or []
    pots = gate.get("pots") or []

    by_ball = {}
    for row in rejections:
        by_ball.setdefault(row.get("ball_id"), row)

    departed = []
    for ball_id, old_id in sorted(id_plan["departed"].items(), key=lambda kv: kv[1]):
        row = by_ball.get(ball_id) or {}
        numbers = row.get("numbers") or {}
        departed.append({
            "was_id": old_id, "ball_id": ball_id,
            "now": "rejected" if row else "not an event in this gate run",
            "code": row.get("code"), "reason": row.get("reason"),
            "numbers": {k: numbers.get(k) for k in
                        ("net_displacement_px", "net_displacement_diameters", "path_length_px",
                         "peak_speed_px_s", "bar_minus_net_px", "duration_s")},
            "bar_px": _bar_px(numbers)})

    oscillation = [row for row in rejections if row.get("code") == "oscillation_no_net_travel"]
    unresolved_rows = []
    for row in unresolved:
        numbers = row.get("numbers") or {}
        bar = _bar_px(numbers)
        net = numbers.get("net_displacement_px")
        error = numbers.get("net_uncertainty_px")
        delta = None if net is None or bar is None else round(float(net) - float(bar), 3)
        unresolved_rows.append({
            "ball_id": row.get("ball_id"), "code": row.get("code"), "t": row.get("t"),
            "net_displacement_px": net,
            "net_displacement_diameters": numbers.get("net_displacement_diameters"),
            "bar_px": bar,
            "bar_diameters": artifact["thresholds"].get("min_net_displacement_diameters"),
            "bar_delta_px": delta,
            "side": None if delta is None else ("clears_bar" if delta > 0 else "short_of_bar"),
            "shortfall_px": numbers.get("bar_minus_net_px"),
            "localisation_error_px": artifact["thresholds"].get("localisation_error_px"),
            "net_uncertainty_px": error,
            "inside_own_error_bar": None if delta is None or error is None else bool(abs(delta) < float(error)),
            "peak_speed_px_s": numbers.get("peak_speed_px_s"),
            "path_length_px": numbers.get("path_length_px"),
            "served": False})

    served_balls = set(id_plan["reused"]) | set(id_plan["added"])
    unknown_rows = []
    for row in pots:
        speed = row.get("last_speed_px_s")
        unknown_rows.append({
            "ball_id": row.get("ball_id"), "last_t": row.get("last_t"),
            "pocket": row.get("pocket"),
            "distance_mm": row.get("distance_mm"),
            "distance_mm_uncertainty": row.get("distance_mm_uncertainty"),
            "radius_mm": row.get("radius_mm"),
            "verdict_mm": row.get("verdict_mm"),
            "inside_px": row.get("inside_px"), "inside_mm": row.get("inside_mm"),
            "pocket_test_disagrees_px_vs_mm": row.get("pocket_test_disagrees_px_vs_mm"),
            "last_speed_px_s": speed,
            "gap_s": row.get("gap_s"),
            "moving_at_last_sighting": None if speed is None else bool(speed >= MOVING_PX_S),
            "occlusion_status": row.get("occlusion_status"),
            "served": row.get("ball_id") in served_balls})
    moving = [row for row in unknown_rows if row["moving_at_last_sighting"]]
    parked = [row for row in unknown_rows if row["moving_at_last_sighting"] is False]
    text = [row for row in unknown_rows if row.get("distance_mm") is None]

    return {
        "note": "rejection = the gate said no; unresolved = the gate cannot tell; "
                "unknown = the ball is gone and the gate will not claim a pot",
        "counts": gate.get("counts"),
        "observed_until_t": gate.get("observed_until_t"),
        "conflated_codes": [entry for entry in artifact.get("rejection_codes") or []] or None,
        "oscillation_rejections": {
            "code": "oscillation_no_net_travel",
            "count": len(oscillation),
            "bar_px": _bar_px((oscillation[0].get("numbers") or {})) if oscillation else None,
            "bar_diameters": artifact["thresholds"].get("min_net_displacement_diameters"),
            "note": "a sustained run whose net displacement does not clear the bar the "
                    "ball's own size implies: a ball that ends where it started travelled "
                    "a path without moving to a new place",
            "served_before": [row for row in departed
                              if row.get("code") == "oscillation_no_net_travel"]},
        "unresolved": {
            "code": "oscillation_unresolved", "count": len(unresolved_rows),
            "served": [],
            "why_not_served": "the gate cannot tell a shot from an oscillation here: the gap "
                              "between the run's net travel and the bar -- on either side of it "
                              "-- is smaller than the error the gate puts on that same "
                              "measurement, so the run is neither shaped as an event nor "
                              "rejected (one of the six, t242-red, is numerically over the bar "
                              "and still unresolved: by 4.03 px against a 5.12 px error)",
            "rows": unresolved_rows},
        "occluded_unknowns": {
            "channel": "gate.pots", "count": len(unknown_rows),
            "verdict_mm_counts": {verdict: sum(1 for row in unknown_rows if row["verdict_mm"] == verdict)
                                  for verdict in sorted({row["verdict_mm"] for row in unknown_rows})},
            "served": [row for row in unknown_rows if row["served"]],
            "not_served": [row for row in unknown_rows if not row["served"]],
            "moving_at_last_sighting": {
                "threshold_px_s": MOVING_PX_S,
                "note": "the split is insensitive in this run: the stationary disappearances "
                        "move at <= 17.4 px/s, the moving ones at >= 211.3 px/s",
                "moving": moving, "parked": len(parked)},
            "why_not_served": "every one of these is verdict_mm 'ambiguous': no pocket claim "
                              "survives the error bar, so serving them would ask the operator "
                              "to judge candidates the gate itself cannot call",
            "no_distance_reported": [row["ball_id"] for row in text],
            "rows": unknown_rows},
        "departed_entries": departed,
    }


def build(artifact_path: str, queue_path: str, report_path: str, previous_path: str | None = None) -> dict:
    artifact = json.loads(Path(artifact_path).read_text())
    H, quad = calibration(artifact)
    before = _md5(ANNOTATIONS)
    queue_before = _md5(queue_path)
    held = _previous_ids(previous_path or queue_path)

    # What the queue is allowed to serve:
    # * every shot the gate shaped as an event;
    # * a pot the gate actually *confirmed*;
    # * a pot-shaped *unknown* only if the queue already carried it -- an
    #   unknown the gate cannot call is not a new card, and every one of them in
    #   this run is `verdict_mm ambiguous`, so the seven the previous queue did
    #   not carry stay out and are counted here instead.
    pots = artifact["gate"]["pots"]
    confirmed = [row for row in pots if row.get("verdict") == "confirmed"]
    unknown = [row for row in pots if row.get("verdict") != "confirmed"]
    carried = [row for row in unknown if row["ball_id"] in held]
    dropped = [row for row in unknown if row["ball_id"] not in held]

    entries = [shot_event(shot, H, artifact) for shot in artifact["gate"]["shots"]]
    entries += [pot_event(row, H, artifact) for row in confirmed]
    carried_reason = ("already in the queue from the previous gate run: it stays until a "
                      "human looks at it or the gate confirms it, even though the gate calls "
                      "it unknown")
    entries += [pot_event(row, H, artifact, served_reason=carried_reason,
                          siblings_not_served=len(dropped)) for row in carried]
    entries.sort(key=lambda event: event["t"])
    id_plan = assign_ids(entries, previous_path or queue_path)
    Path(queue_path).write_text(json.dumps(entries, indent=1))
    after = _md5(ANNOTATIONS)
    report = {
        "generated_from": {"artifact": artifact_path, "artifact_md5": _md5(artifact_path),
                           "gate_thresholds": {k: artifact["thresholds"].get(k) for k in
                                               ("min_net_displacement_diameters", "ball_diameter_px",
                                                "localisation_error_px", "pocket_r_mm",
                                                "motion_speed_px_s", "persistence_s")},
                           "detector": DETECTOR,
                           "calibration": "the run's own cloth quad (verified hand anchors)"},
        "queue": {"path": queue_path, "events": len(entries),
                  "md5_before": queue_before, "md5_after": _md5(queue_path),
                  "ids": [event["id"] for event in entries],
                  "id_rule": f"dense-track ids from {ID_BASE}, stable by provenance.ball_id; "
                             f"above every eval id (<= 1052) and distinct from the ids "
                             f"{ANNOTATIONS} references; retired ids are never reused",
                  "tiers": {str(event["tier"]): sum(1 for other in entries
                                                    if other["tier"] == event["tier"])
                            for event in entries}},
        "id_changes": {"served_before": id_plan["served_before"],
                       "kept": id_plan["reused"], "added": id_plan["added"],
                       "departed": id_plan["departed"]},
        "verdict_file": {"path": ANNOTATIONS, "md5_before": before, "md5_after": after,
                         "unchanged": before == after},
        "serving_rule": {
            "serve": ["every shot the gate shaped as an event",
                      "a pot the gate confirmed (verdict 'confirmed')",
                      "a pot-shaped unknown the queue already carried, until a human verdict "
                      "or a gate confirmation moves it"],
            "never_serve": ["an unresolved run (the gate cannot tell a shot from an oscillation)",
                            "a rejected candidate",
                            "a pot-shaped unknown the queue did not already carry"],
            "why": "a card asks the operator for a verdict, so it may only carry a candidate "
                   "the gate can at least shape -- and every occluded unknown in this run is "
                   "'ambiguous' in the millimetre pocket test: the gate itself cannot call it, "
                   "and serving all eight would ask the operator to judge candidates the gate "
                   "refuses to judge"},
        "not_served": {"shots_in_artifact": len(artifact["gate"]["shots"]),
                       "pots_in_artifact": len(pots),
                       "pots_confirmed": len(confirmed),
                       "pots_unknown_in_channel": len(unknown),
                       "unknowns_carried_from_previous_queue": [row["ball_id"] for row in carried],
                       "unknowns_not_carded": [{"ball_id": row["ball_id"], "last_t": row.get("last_t"),
                                                "distance_mm": row.get("distance_mm"),
                                                "distance_mm_uncertainty": row.get("distance_mm_uncertainty"),
                                                "verdict_mm": row.get("verdict_mm"),
                                                "last_speed_px_s": row.get("last_speed_px_s")}
                                               for row in sorted(dropped, key=lambda r: r.get("last_t") or 0)],
                       "identities": artifact.get("tracks", {}).get("n"),
                       "rejections": artifact.get("gate", {}).get("counts", {}).get("rejections"),
                       "rejection_codes": artifact.get("rejection_codes"),
                       "note": "the full rejected-candidate evidence stays in the dense artifact; "
                               "the queue carries only the events the gate shaped as events, plus "
                               "any pot-shaped unknown that was already in the queue"},
        "channels": gate_ledger(artifact, id_plan),
        "entries": [{"id": event["id"], "t": event["t"], "type": event["type"],
                     "color": event["color"], "tier": event["tier"],
                     "status": event["gate"]["status"], "reasons": event["gate"]["reasons"],
                     "evidence": {k: v for k, v in event["gate"]["numbers"].items()
                                  if k.startswith("dense_") or k.startswith("vanish_")}}
                     for event in entries],
    }
    Path(report_path).write_text(json.dumps(report, indent=1))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", default="out/dense-events/segment-1350-1650.gate2.json")
    ap.add_argument("--queue", default="out/scan30/events.json")
    ap.add_argument("--report", default="out/scan30/dense_queue_report.json")
    ap.add_argument("--previous", default=None,
                    help="queue to take stable ids from (defaults to --queue before the write)")
    args = ap.parse_args()
    report = build(args.artifact, args.queue, args.report, args.previous)
    channels = report["channels"]
    print(json.dumps({"queue": report["queue"], "id_changes": report["id_changes"],
                      "verdict_file": report["verdict_file"],
                      "counts": channels["counts"],
                      "oscillation_rejections": {k: v for k, v in channels["oscillation_rejections"].items()
                                                 if k != "served_before"},
                      "unresolved_count": channels["unresolved"]["count"],
                      "occluded_unknowns": channels["occluded_unknowns"]["count"]}, indent=1))
    for entry in report["entries"]:
        print(entry)
    print("departed:", json.dumps(channels["departed_entries"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
