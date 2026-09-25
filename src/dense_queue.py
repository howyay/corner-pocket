"""Put the dense-track events into the served queue, with their provenance.

`out/dense-events/segment-1350-1650.after.json` is the first run whose events come
from the trained ball detector on dense tracks (ball stage at cadence 2, 66.7 ms)
rather than from the sparse classical census.  The gate accepted three shots and
left one pot-shaped disappearance `unknown` because the cloth was occluded at
that moment.  This tool copies exactly those four into `out/scan30/events.json`,
which is what the review rail reads, and writes a report beside it with
everything that did *not* go in.

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
* **machine output is labelled as machine output** (`provenance.machine_produced`,
  `human_confirmed: false`), with the detector, the cadence and the run.

Ids are 9001-9004: above every id the eval tool ever issued (<= 1052) and distinct
from the only id `out/scan30/annotations.json` references (16), so no recorded
verdict can be re-pointed by this write.  The verdict file is never opened for
writing, and its md5 is recorded before and after.

    PYTHONPATH=. .venv/bin/python src/dense_queue.py
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


def _md5(path) -> str | None:
    path = Path(path)
    return hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else None


def calibration(artifact) -> tuple:
    """pixels (960x540 work space) -> canonical millimetres.

    The dense run's own cloth quad, which is the verified hand-anchor geometry
    scaled into the work frame, so the millimetres here are the same reference
    the rest of the project measures against.
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


def shot_event(index: int, shot: dict, H, artifact) -> dict:
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
    numbers = {
        "disp_mm": displacement,               # projected, so the rail's own line renders
        "disp_color": shot["ball_id"].split("-", 1)[1],
        "dense_net_displacement_px": shot.get("net_displacement_px"),
        "dense_path_length_px": shot.get("path_length_px"),
        "dense_peak_speed_px_s": shot.get("peak_speed_px_s"),
        "dense_duration_s": shot.get("duration_s"),
        "dense_rest_before_s": shot.get("rest_window_measured_s"),
        "dense_ends_in_pocket": shot.get("ends_in_pocket"),
        "dense_end_distance_px": shot.get("end_distance_px"),
        "dense_frame_range": [min(frames), max(frames)],
    }
    return {
        "id": ID_BASE + index,
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


def pot_event(index: int, pot: dict, H, artifact) -> dict:
    last_mm = to_mm(H, *pot["last"])
    pocket_mm = to_mm(H, *pot["pocket_px"])
    distance_mm = None
    if last_mm and pocket_mm:
        distance_mm = round(float(np.hypot(pocket_mm[0] - last_mm[0], pocket_mm[1] - last_mm[1])))
    samples = pot.get("samples_used") or []
    frames = [int(s["frame_index"]) for s in samples] or [int(pot["last_frame_index"])]
    return {
        "id": ID_BASE + index,
        "t": round(float(pot["last_t"]), 1),
        "type": "pot",
        "verified": False,
        "source": "dense-track",
        "window_s": [round(float(pot["last_t"]) - 1.5, 2), round(float(pot["last_t"]) + 1.5, 2)],
        "color": pot["ball_id"].split("-", 1)[1],
        "nearest_pocket": f"{pot['pocket']} ({distance_mm}mm)" if distance_mm is not None else None,
        "last_mm": last_mm, "last_px": pot["last"],
        "dup_count": 1,
        "tier": None,                            # no tier: a tier describes a claim's grade
        "origin": "dense-track",
        "gate": {"status": "unconfirmed", "gate": "occlusion",
                 "reasons": ["cloth_occluded_at_disappearance",
                             "pocket_test_disagrees_px_vs_mm"
                             if not _pocket_agrees(pot, distance_mm) else "pocket_test_agrees"],
                 "numbers": {
                     "vanish_dist_mm": distance_mm,
                     "pocket_r_mm": artifact["thresholds"].get("pocket_r_mm"),
                     "pocket_test_agrees": _pocket_agrees(pot, distance_mm),
                     "pocket_test_note": (
                         "the dense gate tests a pixel radius (%.2f px at this location); the "
                         "project's pot gate tests %.0f mm against the reference geometry.  The "
                         "ball is inside the pixel radius and %s the millimetre one, because a "
                         "pixel radius does not follow the perspective scale -- both numbers are "
                         "reported so the operator can see it." % (
                             pot.get("radius_px") or 0.0,
                             artifact["thresholds"].get("pocket_r_mm") or 0.0,
                             "inside" if (distance_mm or 1e9) <= (artifact["thresholds"].get("pocket_r_mm") or 0)
                             else "outside")),
                     "vanish_pocket": pot["pocket"],
                     "vanish_dist_px": pot.get("distance_px"),
                     "vanish_radius_px": pot.get("radius_px"),
                     "vanish_last_speed_px_s": pot.get("last_speed_px_s"),
                     "vanish_gap_s": pot.get("gap_s"),
                     "occlusion_status": pot.get("occlusion_status"),
                     "occlusion_source": pot.get("occlusion_source"),
                     "identity_swap_suspected": pot.get("identity_swap_suspected"),
                     "dense_frame_range": [min(frames), max(frames)],
                 },
                 "dup_count": 1, "colors_merged": [pot["ball_id"].split("-", 1)[1]]},
        "provenance": provenance(artifact, {"ball_id": pot["ball_id"],
                                            "gate_reason": pot.get("reason")}),
    }


def _pocket_agrees(pot: dict, distance_mm) -> bool:
    """Do the pixel radius and the reference millimetre radius agree here?

    The dense gate's pocket test is a pixel radius; the project's is a 100 mm
    radius in reference millimetres.  At the side pocket the two disagree, and a
    consumer that reads only one of them would be misled -- so both are kept and
    the disagreement is named.
    """
    if distance_mm is None:
        return False
    radius_px = pot.get("radius_px")
    distance_px = pot.get("distance_px")
    inside_px = radius_px is not None and distance_px is not None and distance_px <= radius_px
    inside_mm = distance_mm <= 100.0
    return inside_px == inside_mm


def provenance(artifact, extra: dict) -> dict:
    """Where the entry came from, in the payload the rail can print verbatim."""
    segment = artifact.get("segment", {})
    return {"detector": DETECTOR,
            "machine_produced": True,
            "human_confirmed": False,
            "statement": "machine-produced candidate; no human has confirmed it",
            "run": {"segment_s": [segment.get("start_s"), segment.get("start_s", 0) + segment.get("seconds", 0)],
                    "frames_decoded": segment.get("frames_decoded"),
                    "ball_samples": artifact.get("samples", {}).get("balls"),
                    "identities": artifact.get("tracks", {}).get("n"),
                    "occlusion_source": artifact.get("occlusion", {}).get("source"),
                    "gate_thresholds": {"motion_speed_px_s": artifact["thresholds"]["motion_speed_px_s"],
                                        "pocket_r_mm": artifact["thresholds"]["pocket_r_mm"]}},
            **extra}


def build(artifact_path: str, queue_path: str, report_path: str) -> dict:
    artifact = json.loads(Path(artifact_path).read_text())
    H, quad = calibration(artifact)
    before = _md5(ANNOTATIONS)
    events = []
    for index, shot in enumerate(artifact["gate"]["shots"]):
        events.append(shot_event(index, shot, H, artifact))
    for index, pot in enumerate(artifact["gate"]["pots"], start=len(events)):
        events.append(pot_event(index, pot, H, artifact))
    events.sort(key=lambda event: event["t"])
    for position, event in enumerate(events, start=1):
        event["id"] = ID_BASE + position - 1
    Path(queue_path).write_text(json.dumps(events, indent=1))
    after = _md5(ANNOTATIONS)
    report = {
        "generated_from": {"artifact": artifact_path, "detector": DETECTOR,
                           "calibration": "the run's own cloth quad (verified hand anchors)"},
        "queue": {"path": queue_path, "events": len(events),
                  "ids": [event["id"] for event in events],
                  "id_rule": f"dense-track ids from {ID_BASE}, above every eval id (<= 1052) and "
                             f"distinct from the ids {ANNOTATIONS} references",
                  "tiers": {str(event["tier"]): sum(1 for other in events
                                                    if other["tier"] == event["tier"])
                            for event in events}},
        "verdict_file": {"path": ANNOTATIONS, "md5_before": before, "md5_after": after,
                         "unchanged": before == after},
        "not_served": {"shots_in_artifact": len(artifact["gate"]["shots"]),
                       "pots_in_artifact": len(artifact["gate"]["pots"]),
                       "identities": artifact.get("tracks", {}).get("n"),
                       "rejections": artifact.get("gate", {}).get("counts", {}).get("rejections"),
                       "rejection_codes": artifact.get("rejection_codes"),
                       "note": "the full rejected-candidate evidence stays in the dense artifact; "
                               "the queue carries only the events the gate shaped as events"},
        "entries": [{"id": event["id"], "t": event["t"], "type": event["type"],
                     "color": event["color"], "tier": event["tier"],
                     "status": event["gate"]["status"], "reasons": event["gate"]["reasons"],
                     "evidence": {k: v for k, v in event["gate"]["numbers"].items()
                                  if k.startswith("dense_") or k.startswith("vanish_")}}
                    for event in events],
    }
    Path(report_path).write_text(json.dumps(report, indent=1))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", default="out/dense-events/segment-1350-1650.after.json")
    ap.add_argument("--queue", default="out/scan30/events.json")
    ap.add_argument("--report", default="out/scan30/dense_queue_report.json")
    args = ap.parse_args()
    report = build(args.artifact, args.queue, args.report)
    print(json.dumps({"queue": report["queue"], "verdict_file": report["verdict_file"],
                      "not_served": report["not_served"]}, indent=1))
    for entry in report["entries"]:
        print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
