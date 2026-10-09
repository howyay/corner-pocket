"""What a per-segment reference changes: calibration_frac per frame, and verdicts.

``src/eval_events`` measures every candidate against **one** reference chosen up
front (the hand anchors).  That is the single-`H` reuse ``docs/state.md`` warns
about.  This tool re-measures the same candidates against the reference each
event's own time resolves to (``src/calib_segments``), and against the late-window
derived quad as a counterfactual, then re-judges with ``src.event_gates`` - all
through the existing machinery, without editing either owned module.

Three columns, one per reference:

* ``anchors`` - what the served queue uses today (hand anchors at t=70, one H);
* ``segment`` - the per-segment lookup, the wiring this round adds;
* ``derived_late`` - a split of the VOD at the first below-gate sample, the late
  window taking the derived refined quad.  This is the *counterfactual*: it is
  what the artifact's ``late_window_alternative`` would do if it were used.

Cost is bounded like the gate report's: three passes over the candidates' own
frame neighbourhoods, no full re-scan.  Nothing is written outside this tool's
report; the served queue and the probe cache are never touched.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.datasets import media_path  # noqa: E402

OUT = ROOT / "out" / "segcalib" / "segment_calib_report.json"
CANDIDATES = ROOT / "out" / "scan-ic" / "events.json"
SEGMENT_ARTIFACT = ROOT / "out" / "calib_vod30_segments.json"
VIDEO = media_path(ROOT, "vod30")
SMALL_W, SMALL_H = 960, 540


class ReferenceSet:
    """The three references under comparison, by name."""

    def __init__(self, anchors_quad, segment_model, derived_quad, split_t=None):
        self.anchors = np.asarray(anchors_quad, np.float32)
        self.segment_model = segment_model
        self.derived = None if derived_quad is None else np.asarray(derived_quad, np.float32)
        self.split_t = split_t

    def names(self):
        return ["anchors", "segment"] + (["derived_late"] if self.derived is not None else [])

    def quad_for(self, name, t):
        if name == "anchors":
            return self.anchors
        if name == "derived_late":
            split = self.split_t if self.split_t is not None else 0.0
            return self.derived if (t or 0.0) >= split else self.anchors
        quad = self.segment_model.quad_for(t) if self.segment_model is not None else None
        return self.anchors if quad is None else quad


class PerTimeProbe:
    """``eval_events.Probe`` that swaps its reference per event time.

    Everything measured (``mm``, ``px``, ``cloth_fraction``, the ball mask) reads
    the probe's own ``forward``/``inverse``/``quad``, so re-pointing those three
    attributes between candidates is exactly the per-segment behaviour, using the
    probe's own code paths.
    """

    def __init__(self, video, references, name, sam3=None):
        from src.eval_events import Probe
        from src.pipeline import homography_to_canonical
        self.references, self.name = references, name
        quad = references.quad_for(name, 0.0)
        forward, inverse = self._pair(quad)
        self.inner = Probe(video, forward, inverse, quad, sam3=sam3)
        self.applied = None
        self.homography_to_canonical = homography_to_canonical

    @staticmethod
    def _pair(quad):
        from src.pipeline import homography_to_canonical
        forward = homography_to_canonical(np.asarray(quad, np.float32))
        return forward, np.linalg.inv(forward)

    def open(self):
        return self.inner.open()

    def close(self):
        self.inner.close()

    @property
    def seconds(self):
        return self.inner.seconds

    def use(self, t):
        """Point the probe at the reference that owns ``t``; rebuild its cloth mask."""
        import cv2
        quad = self.references.quad_for(self.name, t)
        if self.applied is None or not np.array_equal(quad, self.applied):
            forward, inverse = self._pair(quad)
            self.inner.forward, self.inner.inverse, self.inner.quad = forward, inverse, quad
            small_quad = (np.asarray(quad, np.float32) * (SMALL_W / 1280.0)).astype(np.float32)
            cloth = np.zeros((SMALL_H, SMALL_W), np.uint8)
            cv2.fillPoly(cloth, [np.round(small_quad).astype(np.int32)], 1)
            self.inner.cloth = cloth
            self.applied = np.asarray(quad, np.float32).copy()
        return self.inner

    def mm(self, cx, cy):
        return self.inner.mm(cx, cy)

    def cloth_fraction(self, t):
        return self.inner.cloth_fraction(t)


def measure_once(candidates, references, name, cfg, video, limit=None, sam3=None):
    """Judge every candidate with one reference; returns rows keyed by (kind, t)."""
    from src.eval_events import _evidence, _key, probe_pot, probe_shot
    from src.event_gates import dedupe, judge

    probe = PerTimeProbe(video, references, name, sam3=sam3)
    if not probe.open():
        raise SystemExit(f"cannot open {video}")
    rows = {}
    started = time.time()
    try:
        for group in dedupe(candidates, cfg)[:limit]:
            claim = group["event"]
            inner = probe.use(claim["t"])
            if claim["kind"] == "shot" and not (claim["from_mm"] and claim["to_mm"]):
                from src.event_gates import ShotEvidence
                payload = asdict(ShotEvidence(available=False,
                                              note="claim carries no bracketing geometry"))
            else:
                payload = asdict(probe_shot(claim, inner) if claim["kind"] == "shot"
                                 else probe_pot(claim, inner))
            rows[_key(claim)] = {
                "id": claim["id"], "kind": claim["kind"], "t": claim["t"], "color": claim["color"],
                "calibration_frac": payload.get("calibration_frac"),
                "census_source": payload.get("census_source"),
                "verdict": judge(claim, _evidence(claim["kind"], payload), cfg).as_dict(),
                "evidence": {"disp_mm": payload.get("disp_mm"),
                             "vanish": [{"color": v.get("color"), "pocket": v.get("pocket"),
                                         "dist_mm": v.get("dist_mm"), "mm": v.get("mm")}
                                        for v in payload.get("vanish") or []],
                             "from_in_cloth_px": payload.get("from_in_cloth_px"),
                             "to_in_cloth_px": payload.get("to_in_cloth_px"),
                             "geometry_gap_px": payload.get("geometry_gap_px")},
            }
    finally:
        probe.close()
    return rows, round(time.time() - started, 1)


def per_sample_frames(rows, references, video, times):
    """``calibration_frac`` at fixed sample times, per reference - the proxy itself."""
    from src.eval_events import Probe
    out = []
    probes = {}
    for name in references.names():
        quad = references.quad_for(name, times[0] if times else 0.0)
        forward, inverse = PerTimeProbe._pair(quad)
        p = Probe(video, forward, inverse, quad)
        if not p.open():
            raise SystemExit(f"cannot open {video}")
        probes[name] = p
    try:
        for t in times:
            row = {"t": t, "calibration_frac": {}}
            for name, p in probes.items():
                probe = PerTimeProbe(video, references, name)
                probe.inner = p
                probe.use(t)
                row["calibration_frac"][name] = p.cloth_fraction(t)
            seg = references.segment_model.resolve(t) if references.segment_model else None
            row["segment"] = None if seg is None else seg.id
            out.append(row)
    finally:
        for p in probes.values():
            p.close()
    return out


def build(args):
    from src import calib_segments
    from src.event_gates import GateConfig

    cfg = GateConfig()
    payload = json.loads(Path(args.artifact).read_text())
    segment_model = calib_segments.load(path=args.artifact, use_cache=False)
    anchors = np.asarray(payload["segments"][0]["quad_px"], np.float32)
    alt = payload.get("late_window_alternative") or {}
    derived = alt.get("quad_px")
    split_t = (alt.get("fit_from") or {}).get("t_start")
    references = ReferenceSet(anchors, segment_model, derived, split_t)

    candidates = json.loads(Path(args.candidates).read_text())
    # One census store for every pass.  The SAM3 cache is read from disk by
    # eval_events.Probe at construction, and the scan's own cache is being written
    # by other work; loading it once per pass makes "the reference changed" and
    # "the file changed underneath us" indistinguishable.  Frozen here, every pass
    # sees the same census, and `anchors_repeat` measures what noise is left.
    from src.eval_events import APP_CACHE, OWN_CACHE, SAM3Store
    sam3 = SAM3Store()
    store_stamp = {str(p): (p.stat().st_mtime_ns, p.stat().st_size)
                   for p in (Path(APP_CACHE), Path(OWN_CACHE)) if Path(p).is_file()}
    columns, seconds = {}, {}
    for name in references.names() + ["anchors_repeat"]:
        source_name = "anchors" if name == "anchors_repeat" else name
        columns[name], seconds[name] = measure_once(candidates, references, source_name, cfg,
                                                    args.video, args.limit, sam3=sam3)

    keys = sorted(columns["anchors"], key=lambda k: columns["anchors"][k]["t"] or 0.0)
    rows, changed = [], []
    for key in keys:
        base = columns["anchors"][key]
        row = {"key": key, "id": base["id"], "kind": base["kind"], "t": base["t"],
               "color": base["color"], "calibration_frac": {}, "verdict": {}, "evidence": {}}
        for name in references.names() + ["anchors_repeat"]:
            cell = columns[name].get(key)
            if cell is None:
                continue
            row["calibration_frac"][name] = cell["calibration_frac"]
            row["verdict"][name] = {"status": cell["verdict"]["status"],
                                    "tier": cell["verdict"].get("tier"),
                                    "reasons": cell["verdict"]["reasons"]}
            row["evidence"][name] = cell["evidence"]
        a, repeat = row["verdict"]["anchors"], row["verdict"].get("anchors_repeat")
        baseline_states = {a["status"]}
        if repeat is not None:
            baseline_states.add(repeat["status"])
        # A status the same reference produced on its own repeat is noise, so a
        # candidate only counts as changed when its status is outside *both*
        # baseline runs.  Without this, a concurrent writer of the SAM3 census
        # would be reported as a calibration effect.
        row["changed"] = [name for name in row["verdict"]
                          if name not in ("anchors", "anchors_repeat")
                          and row["verdict"][name]["status"] not in baseline_states]
        row["statuses"] = {name: value["status"] for name, value in row["verdict"].items()}
        row["calibration_changed"] = [name for name in row["calibration_frac"]
                                      if name not in ("anchors", "anchors_repeat")
                                      and row["calibration_frac"][name] != row["calibration_frac"]["anchors"]]
        if row["changed"] or row["calibration_changed"]:
            changed.append({"t": row["t"], "kind": row["kind"], "id": row["id"],
                            "verdict_changed": row["changed"],
                            "calibration_changed": row["calibration_changed"],
                            "calibration_frac": row["calibration_frac"],
                            "verdict": row["verdict"],
                            "baseline_states": sorted(baseline_states)})
        rows.append(row)

    sample_times = sorted({round(float(t), 1) for t in
                           [0.0, 420.0, 450.0, 483.4, 941.5, 1080.0, 1120.2, 1200.0, 1800.0]})
    frames = per_sample_frames(rows, references, args.video, sample_times)

    counts = {name: {"confirmed": 0, "rejected": 0, "unconfirmed": 0}
              for name in references.names() + ["anchors_repeat"]}
    for row in rows:
        for name, verdict in row["verdict"].items():
            counts[name][verdict["status"]] = counts[name].get(verdict["status"], 0) + 1
    late = [row for row in rows if (row["t"] or 0) >= (split_t or 0)]
    report = {
        "generated_from": {"candidates": str(Path(args.candidates).relative_to(ROOT)),
                           "artifact": str(Path(args.artifact).relative_to(ROOT)),
                           "video": args.video, "gate_config": asdict(cfg)},
        "references": {
            "anchors": {"quad_px": np.round(anchors, 2).tolist(),
                        "detail": "hand anchors at t=70, the single-H reference the queue uses today"},
            "segment": {"verdict": payload.get("segmentation_verdict"),
                        "segments": [{"id": s["id"], "t_start": s["t_start"], "t_end": s["t_end"],
                                      "source": s["source"], "quad_px": s["quad_px"]}
                                     for s in payload["segments"]]},
            "derived_late": {"quad_px": derived, "split_t": split_t,
                             "detail": "counterfactual: split at the first below-gate sample, late "
                                       "window on the derived refined quad (not used)"},
        },
        "per_sample_frame": frames,
        "candidates": rows,
        "changes": changed,
        "summary": {
            "candidates": len(rows), "late_candidates": len(late),
            "late_candidate_times": [row["t"] for row in late],
            "verdicts_by_reference": counts,
            "candidates_whose_verdict_changes": len([c for c in changed if c["verdict_changed"]]),
            "candidates_whose_calibration_frac_changes": len([c for c in changed
                                                              if c["calibration_changed"]]),
            "probe_seconds": seconds,
            "reference_is_identical_to_anchors": all(
                columns["segment"][key]["calibration_frac"] == columns["anchors"][key]["calibration_frac"]
                for key in columns["anchors"] if key in columns["segment"]),
            "candidates_whose_verdict_differs_from_the_same_reference_repeat":
                [row["t"] for row in rows if row["verdict"].get("anchors_repeat") and
                 row["verdict"]["anchors_repeat"]["status"] != row["verdict"]["anchors"]["status"]],
            "census_store": {"files": store_stamp, "frames": len(sam3)},
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(json.dumps(report["summary"], indent=1))
    print(f"wrote {args.out}")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidates", default=str(CANDIDATES))
    ap.add_argument("--artifact", default=str(SEGMENT_ARTIFACT))
    ap.add_argument("--video", default=str(VIDEO))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--limit", type=int, default=None)
    return build(ap.parse_args(argv))


if __name__ == "__main__":
    main()
