"""Why a ball identity ends on open cloth: occlusion, or a tracking failure.

`tests/ball_dense_events.py` runs the whole chain (ball stage -> colour ->
`ball_census.associate` -> occlusion -> `shot_pot_gate.classify`) and reports the
gate's rejection codes.  The two codes that decide whether pot detection can ever
work are:

* ``disappeared_outside_pocket`` -- the identity ended on open cloth.  The gate
  reads that as "a detector dropout, not a pot" and it is right to: the last
  sighting sits at a median ~90 px from the nearest pocket.
* ``reappeared_after_gap`` -- the identity came back after a gap, so the gap was
  never a disappearance.

Both are only *fragmentation* if the frames were clean when the identity was
lost.  The occlusion channel is already attached to every sample
(``occluded`` = `motion_scan.probe_pair` ``occ_dense >= 0.30``), so the two
causes separate exactly:

* the identity was lost **while the cloth was occluded** -- a person crossed it,
  the ball is *unknown*, and no downstream consumer may call that a pot;
* the identity was lost on a **clean frame** -- the detector missed a ball that
  was there: a tracking failure, and the thing association has to survive.

This tool only reads a dense-events report and writes the audit next to it.

    PYTHONPATH=. .venv/bin/python src/ball_association_audit.py \
        out/dense-events/segment-1350-1650.json
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: How close in time and space a later identity must start for the pair to be one
#: ball whose path was split.  The segment's own numbers: sampling 66.7 ms, the
#: measured reappearance gaps 0.5-2.0 s (median 0.9 s), and a ball's 17 px
#: footprint at 960x540 -- 60 px is three ball widths, the same scale the
#: associator's own radius uses.
FRAGMENT_GAP_S = 2.5
FRAGMENT_PX = 60.0


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def identity_tails(report) -> dict:
    """Per identity: the samples its own rejections kept as evidence.

    Every rejection carries up to ``evidence_samples`` of the track's samples, so
    a rejection list is a partial view of every identity that was rejected -- and
    every identity here was (721 rejections for 248 identities).
    """
    tails: dict = defaultdict(list)
    for row in report.get("gate", {}).get("rejections", []):
        for sample in row.get("samples_used") or ():
            tails[row["ball_id"]].append(sample)
    out = {}
    for ball_id, samples in tails.items():
        samples.sort(key=lambda s: s["t"])
        out[ball_id] = {"color": ball_id.split("-", 1)[1] if "-" in ball_id else "?",
                        "first": samples[0], "last": samples[-1], "n": len(samples)}
    return out


def _lost_occluded(samples, count: int = 2) -> bool | None:
    """Was the cloth occluded around the loss?  ``None`` when it cannot be told.

    The occlusion verdict is taken from the samples the identity itself kept at
    the end: the harness flags each sample with the occlusion channel of *its*
    frame, so "the last sighting happened under a person" is a measurement, not
    an inference.  A track whose evidence is one sample long is undecidable.
    """
    if not samples:
        return None
    tail = samples[-count:]
    if not tail:
        return None
    return any(bool(s.get("occluded")) for s in tail)


def diagnose(report) -> dict:
    rejections = report.get("gate", {}).get("rejections", [])
    by_code = defaultdict(list)
    for row in rejections:
        by_code[row["code"]].append(row)

    terminations = by_code.get("disappeared_outside_pocket", [])
    reappearances = by_code.get("reappeared_after_gap", [])

    term_causes, term_distances, term_gaps = Counter(), [], []
    for row in terminations:
        samples = row.get("samples_used") or []
        occluded = _lost_occluded(samples)
        term_causes["occlusion" if occluded else "clean_frame" if occluded is False
                      else "undecidable"] += 1
        numbers = row.get("numbers") or {}
        if isinstance(numbers.get("nearest_distance_px"), (int, float)):
            term_distances.append(float(numbers["nearest_distance_px"]))
        if isinstance(numbers.get("gap_s"), (int, float)):
            term_gaps.append(float(numbers["gap_s"]))

    re_causes, re_gaps = Counter(), []
    for row in reappearances:
        samples = row.get("samples_used") or []
        occluded = _lost_occluded(samples)
        re_causes["occlusion" if occluded else "clean_frame" if occluded is False
                   else "undecidable"] += 1
        gap = (row.get("numbers") or {}).get("gap_s")
        if isinstance(gap, (int, float)):
            re_gaps.append(float(gap))

    tails = identity_tails(report)
    links = []
    identities = sorted(tails.items(), key=lambda kv: kv[1]["last"]["t"])
    links_by_radius = {}
    for radius in (20.0, 60.0, 150.0, 300.0):
        found = []
        for ball_id, tail in identities:
            for other_id, other in identities:
                if other_id == ball_id or other["color"] != tail["color"]:
                    continue
                gap = other["first"]["t"] - tail["last"]["t"]
                if not 0.0 < gap <= FRAGMENT_GAP_S:
                    continue
                distance = ((other["first"]["x"] - tail["last"]["x"]) ** 2
                            + (other["first"]["y"] - tail["last"]["y"]) ** 2) ** 0.5
                if distance <= radius:
                    found.append({"ended": ball_id, "started": other_id, "gap_s": round(gap, 3),
                                  "px": round(distance, 1), "color": tail["color"],
                                  "implied_speed_px_s": round(distance / gap)})
        links_by_radius[int(radius)] = found
    links = links_by_radius[int(FRAGMENT_PX)]
    linked = {link["ended"] for link in links}
    # A link is *stationary* when the ball is where it was (a re-detection) and
    # *moving* when the gap is accounted for by motion -- the second kind is what
    # the predictor's gate radius has to cover, and a fixed 30 px cannot.
    wide = links_by_radius[300]
    stationary = [link for link in wide if link["px"] <= 20.0]
    moving = [link for link in wide if link["px"] > 20.0]
    implied = [link["implied_speed_px_s"] for link in moving]

    return {
        "segment": report.get("segment", {}),
        "identities": report.get("tracks", {}).get("n"),
        "sampling_interval_s": report.get("tracks", {}).get("median_dt_s"),
        "terminations": {
            "n": len(terminations),
            "causes": dict(term_causes),
            "nearest_pocket_px": {
                "median": round(statistics.median(term_distances), 1) if term_distances else None,
                "p10": round(_percentile(term_distances, .1), 1) if term_distances else None,
                "p90": round(_percentile(term_distances, .9), 1) if term_distances else None,
                "within_20px": sum(1 for d in term_distances if d <= 20.0),
            },
            "silence_s": {
                "median": round(statistics.median(term_gaps), 2) if term_gaps else None,
                "p10": round(_percentile(term_gaps, .1), 2) if term_gaps else None,
            },
        },
        "reappearances": {
            "n": len(reappearances),
            "causes": dict(re_causes),
            "gap_s": {
                "median": round(statistics.median(re_gaps), 2) if re_gaps else None,
                "p10": round(_percentile(re_gaps, .1), 2) if re_gaps else None,
                "p90": round(_percentile(re_gaps, .9), 2) if re_gaps else None,
                "in_0.5_2.0": sum(1 for g in re_gaps if 0.5 <= g <= 2.0),
            },
        },
        "fragments": {
            "links": len(links),
            "identities_ending_into_a_later_identity": len(linked),
            "max_gap_s": FRAGMENT_GAP_S, "max_px": FRAGMENT_PX,
            "links_by_radius_px": {str(radius): len(found)
                                   for radius, found in links_by_radius.items()},
            "stationary_links_20px": len(stationary),
            "moving_links_over_20px": len(moving),
            "implied_speed_px_s": {
                "median": round(statistics.median(implied)) if implied else None,
                "p90": round(_percentile(implied, .9)) if implied else None,
                "max": max(implied) if implied else None,
            },
            "examples": links[:10],
        },
        "prediction": prediction_residuals(report),
        "rejection_codes": report.get("rejection_codes", {}),
        "gate_counts": report.get("gate", {}).get("counts", {}),
    }


def format_audit(audit) -> str:
    term, re, frag = audit["terminations"], audit["reappearances"], audit["fragments"]
    lines = [
        f"segment {audit['segment'].get('start_s')}s +{audit['segment'].get('seconds')}s  "
        f"identities {audit['identities']}  sampling {audit['sampling_interval_s']} s",
        f"terminations on open cloth: {term['n']}  causes {json.dumps(term['causes'])}",
        f"  nearest pocket px: median {term['nearest_pocket_px']['median']} "
        f"p10 {term['nearest_pocket_px']['p10']} p90 {term['nearest_pocket_px']['p90']} "
        f"within 20 px {term['nearest_pocket_px']['within_20px']}",
        f"  silence before the end, s: median {term['silence_s']['median']} "
        f"p10 {term['silence_s']['p10']}",
        f"reappearances: {re['n']}  causes {json.dumps(re['causes'])}",
        f"  gap s: median {re['gap_s']['median']} p10 {re['gap_s']['p10']} p90 {re['gap_s']['p90']} "
        f"in 0.5-2.0 s {re['gap_s']['in_0.5_2.0']}",
        f"fragment links (<= {frag['max_gap_s']} s, same colour) by radius px: "
        f"{json.dumps(frag['links_by_radius_px'])}",
        f"  stationary (<=20 px) {frag['stationary_links_20px']}  "
        f"moving {frag['moving_links_over_20px']}  implied speed px/s median "
        f"{frag['implied_speed_px_s']['median']} p90 {frag['implied_speed_px_s']['p90']} "
        f"max {frag['implied_speed_px_s']['max']}",
        f"prediction residual, same colour: {json.dumps(audit['prediction']['same_colour'])}",
        f"                    cross colour: {json.dumps(audit['prediction']['cross_colour'])} "
        f"(same-colour share {audit['prediction']['same_colour_share']})",
        f"gate: {json.dumps(audit['gate_counts'])}",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", help="a tests/ball_dense_events.py report")
    ap.add_argument("--out", default=None, help="audit JSON (default: <report>.audit.json)")
    args = ap.parse_args()
    report = json.loads(Path(args.report).read_text())
    audit = diagnose(report)
    out = Path(args.out) if args.out else Path(args.report).with_suffix(".audit.json")
    out.write_text(json.dumps(audit, indent=1))
    print(format_audit(audit))
    print(f"-> {out}")




def prediction_residuals(report, max_gap_s: float = 2.5, max_px: float = 600.0) -> dict:
    """What a constant-velocity prediction has to cover, and what colour adds.

    For every identity that ends and a same-colour identity that starts within
    ``max_gap_s``, extrapolate the ending identity's own velocity across the gap
    and measure the residual against the starting position.  That residual is the
    gate radius the predictor needs; the *angular* error is what is left after
    motion is accounted for.  The same pairs without the colour filter give the
    colour term's value: if a cross-colour pair is as close as the same-colour
    one, colour is doing the disambiguating and cannot be dropped.
    """
    tails = identity_tails(report)
    identities = sorted(tails.items(), key=lambda kv: kv[1]["last"]["t"])
    same, cross = [], []
    for ball_id, tail in identities:
        samples = _tail_samples(report, ball_id)
        velocity = _velocity(samples)
        for other_id, other in identities:
            if other_id == ball_id:
                continue
            gap = other["first"]["t"] - tail["last"]["t"]
            if not 0.0 < gap <= max_gap_s:
                continue
            end, start = tail["last"], other["first"]
            raw = math.hypot(start["x"] - end["x"], start["y"] - end["y"])
            if raw > max_px:
                continue
            if velocity is None:
                residual, angular = raw, None
            else:
                predicted = (end["x"] + velocity[0] * gap, end["y"] + velocity[1] * gap)
                residual = math.hypot(start["x"] - predicted[0], start["y"] - predicted[1])
                travelled = math.hypot(velocity[0] * gap, velocity[1] * gap)
                angular = None if travelled < 1e-6 else residual / travelled
            row = {"ended": ball_id, "started": other_id, "gap_s": round(gap, 3),
                   "raw_px": round(raw, 1), "residual_px": round(residual, 1),
                   "angular": None if angular is None else round(angular, 3)}
            (same if other["color"] == tail["color"] else cross).append(row)

    def summary(rows):
        residuals = [r["residual_px"] for r in rows]
        angular = [r["angular"] for r in rows if r["angular"] is not None]
        return {"n": len(rows),
                "residual_px": {"p50": round(statistics.median(residuals), 1) if residuals else None,
                                "p90": round(_percentile(residuals, .9), 1) if residuals else None,
                                "p99": round(_percentile(residuals, .99), 1) if residuals else None},
                "angular": {"p50": round(statistics.median(angular), 3) if angular else None,
                            "p90": round(_percentile(angular, .9), 3) if angular else None}}

    return {"same_colour": summary(same), "cross_colour": summary(cross),
            "same_colour_share": round(len(same) / max(1, len(same) + len(cross)), 3)}


def _tail_samples(report, ball_id):
    rows = []
    for row in report.get("gate", {}).get("rejections", []):
        if row["ball_id"] != ball_id:
            continue
        rows.extend(row.get("samples_used") or ())
    rows.sort(key=lambda s: s["t"])
    return rows


def _velocity(samples):
    """px/s from the last two samples, or None when there are not two."""
    if len(samples) < 2:
        return None
    a, b = samples[-2], samples[-1]
    dt = b["t"] - a["t"]
    if dt <= 1e-6:
        return None
    return ((b["x"] - a["x"]) / dt, (b["y"] - a["y"]) / dt)
if __name__ == "__main__":
    main()
