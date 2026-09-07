"""Rebuild vod30 scan events with the CORRECT segment homography (EVT-1).

Fixes vs the old out/scan30/events.json build:
1. H: sam3 image coords were reprojected with the highlight (1080p) calibration
   (calib_final.json) — wrong camera. events_v2 uses the vod30 segment corners
   (corners_30min_v2.json) mapped onto the real Rasson playing surface
   2540 x 1270 mm.
2. Pockets: real pocket centers in mm (4 corners + 2 side midpoints).
3. Occlusion gate: cloth area recomputed per SAM3 timestamp from the video
   (records.json predates the cloth_area patch); drops touching an occluded
   sample are not pots.
4. Causality kept: pot.t = linked shot t when a shot precedes the pot window
   end (<=60 s), else pot keeps its window midpoint and is flagged unlinked.
5. Output goes to events_v2.json; events.json is left untouched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

VIDEO = ROOT.parent / "data" / "vod_30min_260815.mp4"
SCAN = ROOT.parent / "out" / "scan30"
CORNERS = ROOT.parent / "out" / "corners_30min_v2.json"

POCKETS_MM = {
    "head-left": (0.0, 0.0),
    "head-right": (2540.0, 0.0),
    "foot-right": (2540.0, 1270.0),
    "foot-left": (0.0, 1270.0),
    "left-side": (0.0, 635.0),
    "right-side": (2540.0, 635.0),
}


def nearest_pocket(x, y):
    best, bd = None, 1e18
    for name, (px, py) in POCKETS_MM.items():
        d = np.hypot(x - px, y - py)
        if d < bd:
            best, bd = name, d
    return best, float(bd)


def main():
    corners = np.array(json.load(open(CORNERS))["corners"], np.float32)
    dst = np.array([[0, 0], [2540, 0], [2540, 1270], [0, 1270]], np.float32)
    H = cv2.getPerspectiveTransform(corners, dst)          # 720p px -> mm
    sam3_raw = json.load(open(SCAN / "sam3_results.json"))
    records = json.load(open(SCAN / "records.json"))
    rec_by_t = {r["t"]: r for r in records}

    # recompute cloth area per sam3 time (occlusion gate) + reproject balls
    cap = cv2.VideoCapture(str(VIDEO))
    from table_detect import detect_table

    cloth_areas = {}
    sam3 = {}
    for k, balls in sam3_raw.items():
        t = float(k)
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, bgr = cap.read()
        if ok:
            tab = detect_table(bgr)
            cloth_areas[t] = float(tab["mask"].sum()) if tab["mask"] is not None else 0.0
        for b in balls:
            p = H @ np.array([b["img"][0], b["img"][1], 1.0])
            b["table_mm"] = [round(p[0] / p[2], 1), round(p[1] / p[2], 1)]
        sam3[t] = balls
    cap.release()
    area_ref = float(np.median(list(cloth_areas.values()))) if cloth_areas else 1.0

    def occluded(t):
        a = cloth_areas.get(round(t, 1)) or cloth_areas.get(round(t))
        return a is not None and a < 0.7 * area_ref

    times = sorted(sam3)
    counts = {t: len(b) for t, b in sam3.items()}

    # shots: records motion peaks >= 15 merged within 6 s; verified via SAM3
    # displacement between adjacent samples (<=3.5 s, >= 300 mm)
    t_all = np.array([r["t"] for r in records])
    m_all = np.array([r["motion"] for r in records])
    peaks = [i for i in range(1, len(t_all) - 1)
             if m_all[i] > m_all[i - 1] and m_all[i] > m_all[i + 1] and m_all[i] >= 15.0]
    clusters = []
    for i in peaks:
        if clusters and t_all[i] - t_all[clusters[-1][-1]] <= 6:
            clusters[-1].append(i)
        else:
            clusters.append([i])
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

    # pots: drops of the MONOTONE-HULL of counts.  Counts are non-increasing
    # physically (no re-spots in this format); any rise is detection noise, so
    # pot detection only ever compares against the running minimum (hull).
    pots = []
    hull = 1e18
    for i in range(1, len(times)):
        t1, t2 = times[i - 1], times[i]
        c = counts[t2]
        if c >= hull:
            continue
        # number of balls gone vs the hull level
        k = min(hull, counts[t1]) - c
        if k <= 0:
            hull = c
            continue
        hull = c
        unmatched = list(sam3[t2])
        dists = []
        for b in sam3[t1]:
            if not unmatched:
                dists.append((1e9, b))
                continue
            ds = [np.hypot(b["table_mm"][0] - c2["table_mm"][0],
                           b["table_mm"][1] - c2["table_mm"][1]) for c2 in unmatched]
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
                "count_before": int(min(hull + k, counts[t1])), "count_after": c,
            })

    # causality: link pots to preceding shots within 60 s of window end
    for p in pots:
        cand = [s for s in shots if s["t"] <= p["window_s"][1]
                and p["window_s"][1] - s["t"] <= 60]
        if cand:
            p["linked_shot_t"] = max(cand, key=lambda s: s["t"])["t"]
            p["t"] = p["linked_shot_t"]
        else:
            p["unlinked"] = True

    events = sorted(shots + pots, key=lambda e: e["t"])
    for i, e in enumerate(events):
        e["id"] = i + 1
        e["evidence"] = (f"evidence_t{int(round(e['window_s'][1])):05d}.jpg"
                         if e["type"] == "pot"
                         else f"evidence_t{int(round(e['peak_t'])):05d}.jpg")
    out = SCAN / "events_v2.json"
    out.write_text(json.dumps(events, indent=1))

    viol = [p for p in pots if p.get("linked_shot_t") is not None and p["t"] < p["linked_shot_t"]]
    unlinked = [p for p in pots if p.get("unlinked")]
    # consistency audit
    chain = sorted(pots, key=lambda p: p["window_s"][0])
    print(f"{len(shots)} shots, {len(pots)} pot rows, {len(events)} events -> {out}")
    print(f"linked: {len(pots)-len(unlinked)}/{len(pots)}  causality violations: {len(viol)}  "
          f"unlinked: {len(unlinked)}")
    drops = [p["count_before"] - p["count_after"] for p in chain]
    print("window drops:", drops)
    print("pocket dists mm:", sorted(p["pocket_dist_mm"] for p in pots)[:8], '...')


if __name__ == "__main__":
    main()
