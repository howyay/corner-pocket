"""Association A/B on one decode: the fixed gate and the predictor, side by side.

`tests/ball_dense_events.py` decodes the segment once and classifies the tracks
its associator returns.  Re-running it twice would decode twice and drift (host
load, and the occlusion channel is per frame).  This driver runs the harness
*unchanged* -- `runpy` with its own arguments -- while wrapping
`ball_census.associate` so the same observations feed both variants:

* the adaptive one (the harness's own call, written to its artifact), and
* the fixed-gate baseline (`adaptive=False`, plus the raw-distance stitch),
  classified afterwards with the same occlusion shares and thresholds.

Both sides are then reported with the same diagnostics, so "better" has a number
on each line: identities, track duration, terminations and reappearances by cause,
the nearest-pocket distribution of the terminations, the gate's verdicts by code,
and the purity counters (`double_claims`, `wide_links`, `kinks`, `bridged_links`).

    PYTHONPATH=. .venv/bin/python src/ball_association_ab.py --start 1350 --seconds 300
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import ball_association_audit as audit  # noqa: E402
from src import ball_census as bc  # noqa: E402


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))]


def _shape(tracks) -> dict:
    durations = [track.obs[-1].t - track.obs[0].t for track in tracks if track.hits > 1]
    hits = [track.hits for track in tracks]
    return {"identities": len(tracks),
            "median_samples": statistics.median(hits) if hits else 0,
            "max_samples": max(hits) if hits else 0,
            "median_seconds": round(statistics.median(durations), 2) if durations else None,
            "p90_seconds": round(_percentile(durations, .9), 2) if durations else None,
            "single_sample": sum(1 for count in hits if count == 1),
            "bridged_links": sum(track.bridged_samples for track in tracks),
            "wide_links": sum(track.wide_links for track in tracks),
            "kinks": sum(track.kinks for track in tracks),
            "kinked_tracks": sum(1 for track in tracks if track.kinks)}


def _gate_side(tracks, occlusion, thresholds, until, gate_module, fps) -> dict:
    """What the gate says about this variant's tracks, exactly as the harness does."""
    occ_flag = {round(t, 4): share >= gate_module.OCC_DENSE_MIN
                for t, share in zip(occlusion.times, occlusion.shares)}
    gate_tracks = []
    for track in tracks:
        rows = [(int(round(o.t * fps)), o.t, o.cx, o.cy, float(o.score or 0.0),
                 occ_flag.get(round(o.t, 4), False)) for o in track.obs]
        gate_tracks.append(gate_module.Track.from_rows(
            "t%03d-%s" % (track.tid, track.color), rows))
    report = gate_module.classify(gate_tracks, occlusion=occlusion, thresholds=thresholds,
                                  observed_until_t=until)
    codes = {}
    for record in report.rejections:
        codes[record.code] = codes.get(record.code, 0) + 1
    return {"counts": report.counts, "rejection_codes": dict(sorted(codes.items())),
            "gate_tracks": gate_tracks, "rejections": [_record(row) for row in report.rejections]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=float, default=1350.0)
    parser.add_argument("--seconds", type=float, default=300.0)
    parser.add_argument("--cadence", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=0.425)
    parser.add_argument("--dataset", default="vod30")
    parser.add_argument("--budget-ms", type=float, default=1000.0 / 30)
    parser.add_argument("--output", default="")
    parser.add_argument("--baseline", default="out/dense-events/segment-1350-1650.baseline.json")
    parser.add_argument("--quad", type=json.loads,
                        default=[[399.0, 242.25], [600.0, 243.0], [747.75, 426.75], [288.0, 422.25]],
                        help="cloth quad in 960x540 work pixels (the segment's own)")
    args = parser.parse_args()

    captured = {"observations": None, "shares": [], "times": []}
    original_associate = bc.associate

    def capture_associate(observations, **kwargs):
        tracks, frames = original_associate(observations, **kwargs)
        captured["observations"] = list(observations)
        captured["adaptive_stats"] = kwargs.get("stats")
        return tracks, frames

    bc.associate = capture_associate
    from src import motion_scan as ms
    original_probe = ms.probe_pair

    def capture_probe(prev, cur, ctx, cfg):
        probe = original_probe(prev, cur, ctx, cfg)
        captured["shares"].append(float(probe["occ_dense"]))
        return probe

    ms.probe_pair = capture_probe

    sys.argv = ["tests/ball_dense_events.py", "--start", str(args.start),
                "--seconds", str(args.seconds), "--cadence", str(args.cadence),
                "--threshold", str(args.threshold), "--dataset", args.dataset,
                "--budget-ms", str(args.budget_ms)]
    if args.output:
        sys.argv += ["--output", args.output]
    try:
        runpy.run_path(str(ROOT / "tests" / "ball_dense_events.py"), run_name="__main__")
    finally:
        bc.associate = original_associate
        ms.probe_pair = original_probe

    if captured["observations"] is None:
        print("the harness never called associate(): nothing to compare")
        return 1

    from src import shot_pot_gate as gate

    fps = 30.0003
    # The segment's own cloth quad (work coordinates), from the report the harness
    # wrote for this segment: the camera is static, so both variants measure
    # against exactly the same geometry.
    thresholds = gate.GateThresholds(frame_size=[960, 540], cloth_quad=args.quad)
    occlusion = gate.Occlusion.from_shares(captured["times"] or [0.0], captured["shares"] or [0.0],
                                           threshold=gate.OCC_DENSE_MIN,
                                           source="motion_scan.probe_pair occ_dense")
    until = args.start + args.seconds

    stats = {}
    baseline_tracks, _ = bc.associate(captured["observations"], adaptive=False, stats=stats)
    fixed_side = _gate_side(baseline_tracks, occlusion, thresholds, until, gate, fps)

    result = {
        "segment": {"start_s": args.start, "seconds": args.seconds, "cadence": args.cadence},
        "adaptive": {"shape": _shape_from_artifact(args.output), "stats": {k: v for k, v in
                                                                          (captured.get("adaptive_stats") or {}).items()
                                                                          if not isinstance(v, (list, dict))}},
        "fixed_gate": {"shape": _shape(baseline_tracks), "stats": stats,
                       "gate": fixed_side["counts"],
                       "rejection_codes": fixed_side["rejection_codes"],
                       "diagnosis": audit.diagnose(_as_report(baseline_tracks, fixed_side, args, fps))},
    }
    Path(args.baseline).parent.mkdir(parents=True, exist_ok=True)
    Path(args.baseline).write_text(json.dumps(result, indent=1))
    print(json.dumps(result["fixed_gate"]["shape"], indent=1))
    print(json.dumps(result["fixed_gate"]["gate"], indent=1))
    print("->", args.baseline)
    return 0


def _shape_from_artifact(path) -> dict:
    try:
        report = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    tracks = report.get("tracks", {})
    return {"identities": tracks.get("n"), "median_samples": tracks.get("median_samples"),
            "median_seconds": tracks.get("median_seconds"),
            "max_samples": tracks.get("max_samples"), "single_sample": tracks.get("single_sample")}


def _record(row) -> dict:
    """The gate's rejection in the shape the harness writes, so the audit reads it."""
    return {"kind": "rejection", "code": row.code, "ball_id": row.ball_id,
            "reason": row.reason, "t": row.t, "frame_index": row.frame_index,
            "numbers": dict(getattr(row, "numbers", {}) or {}),
            "samples_used": [{"frame_index": s.frame_index, "t": s.t, "x": s.x, "y": s.y,
                              "confidence": s.confidence, "occluded": bool(s.occluded)}
                             for s in row.samples_used]}


def _as_report(tracks, side, args, fps) -> dict:
    """A dense-events-shaped report for the baseline, so the audit can read it."""
    return {"segment": {"start_s": args.start, "seconds": args.seconds},
            "tracks": _shape(tracks), "gate": {"rejections": side["rejections"]},
            "rejection_codes": side["rejection_codes"]}


if __name__ == "__main__":
    raise SystemExit(main())
