"""Rebuild scan results with the calibrated homography.

The SAM3 confirmation results store image coordinates; table_mm were computed
with the older median-quad homography.  This rebuilds table_mm with the
calibrated rectangle-constrained H (out/calib_final.json) and regenerates the
shot/pot events and causality links.

The ball artifact belongs to `src/sam3_artifact.py`.  This module reads it
through that owner and writes it through that owner, with the producer
`REBUILD_CALIBRATED`: every table_mm value of the file is the work of this
module after the call, so the stamp of every ball row becomes that producer.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))     # the repo root, for the src.* import
from scan_events import nearest_pocket  # reuse pocket geometry
from src import events_document, sam3_artifact

SAM3 = sam3_artifact.artifact_path()
EVENTS = events_document.document_path()
CAL = ROOT.parent / "out" / "calib_final.json"


def main():
    cal = json.load(open(CAL))
    H = np.array(cal["H_mm_to_px"])          # mm -> px
    Hinv = np.linalg.inv(H)                  # px -> mm
    sam3 = {float(k): v for k, v in sam3_artifact.read(SAM3).frames.items()}

    for t, balls in sam3.items():
        for b in balls:
            p = Hinv @ np.array([b["img"][0], b["img"][1], 1.0])
            b["table_mm"] = [round(p[0] / p[2], 1), round(p[1] / p[2], 1)]
    sam3_artifact.write(SAM3, sam3, producer=sam3_artifact.REBUILD_CALIBRATED, indent=1)

    times = sorted(sam3)
    counts = {t: len(b) for t, b in sam3.items()}

    # shots: SAM3-verified displacements (pair gap <= 3.5 s, >= 300 mm)
    verified = {}
    for i in range(len(times) - 1):
        t1, t2 = times[i], times[i + 1]
        if t2 - t1 > 3.5:
            continue
        b1, b2 = sam3[t1], sam3[t2]
        if not b1 or not b2:
            continue
        best = None
        for a in b1:
            for c in b2:
                d = np.hypot(a["table_mm"][0] - c["table_mm"][0],
                             a["table_mm"][1] - c["table_mm"][1])
                if best is None or d > best[0]:
                    best = (d, a, c)
        if best and best[0] >= 300:
            verified[round((t1 + t2) / 2, 1)] = best

    # shots: motion peaks (records.json), linked to verified displacements
    import json as _j
    recs = _j.load(open(ROOT.parent / "out" / "scan30" / "records.json"))
    t_all = np.array([r["t"] for r in recs])
    m_all = np.array([r["motion"] for r in recs])
    peaks = [i for i in range(1, len(t_all) - 1)
             if m_all[i] > m_all[i - 1] and m_all[i] > m_all[i + 1] and m_all[i] >= 15.0]
    clusters = []
    for i in peaks:
        if clusters and t_all[i] - t_all[clusters[-1][-1]] <= 6:
            clusters[-1].append(i)
        else:
            clusters.append([i])
    shots = []
    for cl in clusters:
        pk = float(t_all[cl[int(np.argmax(m_all[cl]))]])
        v = next((x for vt, x in verified.items() if abs(vt - pk) <= 3), None)
        shots.append({
            "t": round(float(np.median(t_all[cl])), 1), "type": "shot",
            "peak_t": round(pk, 1), "motion": round(float(m_all[cl].max()), 1),
            "verified": v is not None,
            **({"disp_mm": round(v[0]), "avg_speed_m_s": round(v[0] / 2.0 / 1000, 2),
                "ball_from": v[1]["table_mm"], "ball_to": v[2]["table_mm"]} if v else {}),
        })

    # pots: running-minimum count drops, occlusion-aware (cloth area)
    rec_by_t = {r["t"]: r for r in recs}
    has_area = any("cloth_area" in r for r in recs)
    area_ref = float(np.median([r["cloth_area"] for r in recs])) if has_area else None

    def occluded(t):
        if not has_area:
            return False  # records predate the occlusion patch
        r = rec_by_t.get(round(t, 1)) or rec_by_t.get(round(t))
        return bool(r and r["cloth_area"] < 0.7 * area_ref)

    pots = []
    prev_min = 1e18
    for i in range(1, len(times)):
        t1, t2 = times[i - 1], times[i]
        if occluded(t1) or occluded(t2):
            continue
        if counts[t2] >= prev_min:
            prev_min = min(prev_min, counts[t2])
            continue
        prev_min = counts[t2]
        k = counts[t1] - counts[t2]
        unmatched = list(sam3[t2])
        dists = []
        for b in sam3[t1]:
            if not unmatched:
                dists.append((1e9, b))
                continue
            ds = [np.hypot(b["table_mm"][0] - c["table_mm"][0],
                           b["table_mm"][1] - c["table_mm"][1]) for c in unmatched]
            j = int(np.argmin(ds))
            dists.append((ds[j], b))
            unmatched.pop(j)
        dists.sort(key=lambda z: -z[0])
        for _, b in dists[:k]:
            pocket, dist = nearest_pocket(*b["table_mm"])
            pots.append({
                "t": round((t1 + t2) / 2, 1), "type": "pot",
                "window_s": [round(t1, 1), round(t2, 1)],
                "ball_table_mm": b["table_mm"], "nearest_pocket": pocket,
                "pocket_dist_mm": round(dist),
                "count_before": counts[t1], "count_after": counts[t2],
            })

    for p in pots:
        cand = [s for s in shots if s["t"] <= p["window_s"][1]
                and p["window_s"][1] - s["t"] <= 60]
        if cand:
            p["linked_shot_t"] = max(cand, key=lambda s: s["t"])["t"]
            p["t"] = p["linked_shot_t"]  # causality: pot at its shot

    events = sorted(shots + pots, key=lambda e: e["t"])
    for i, e in enumerate(events):
        e["id"] = i + 1
        e["evidence"] = (f"evidence_t{int(round(e['window_s'][1])):05d}.jpg"
                         if e["type"] == "pot"
                         else f"evidence_t{int(round(e['peak_t'])):05d}.jpg")
    events_document.write(EVENTS, events, producer=events_document.REBUILD_CALIBRATED)
    viol = [p for p in pots if p.get("linked_shot_t") is not None and p["t"] < p["linked_shot_t"]]
    print(f"{len(shots)} shots, {len(pots)} pots, {len(events)} events; "
          f"causality violations: {len(viol)}")
    print(f"pot coverage: {sum(1 for p in pots if 'linked_shot_t' in p)}/{len(pots)} linked")


if __name__ == "__main__":
    main()
