"""PID-2/PID-4 precursor v0: identity prototypes from SAM3 person anchors.

Inputs: out/pid1_persons/report.json + out/pid1_persons2/report2.json
(persons at 12 shot instants). For each person: torso mean RGB (bbox band) and
table-relative side. Filter to table zone, k-means k=2 into A/B clothing
prototypes, and emit per-instant assignments + a review montage.

This is the research's "HSV clothing histograms as an independent cue" step and
the anchor set for later OSNet embeddings + tracklets. Numbers are honest
cluster stats; identity names come later (user anchor / scoreboard).
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

VIDEO = "/home/operator/projects/pool/data/vod_30min_260815.mp4"
QUAD = np.array(json.load(open("/home/operator/projects/pool/out/corners_30min_v2.json"))["corners"], np.float32)


def torso_color(bgr, bb):
    x0, y0, x1, y1 = bb
    h = y1 - y0
    tx0, tx1 = int(x0 + 0.15 * (x1 - x0)), int(x0 + 0.85 * (x1 - x0))
    ty0, ty1 = int(y0 + 0.15 * h), int(y0 + 0.5 * h)
    ty0, ty1 = max(0, ty0), max(0, ty1)
    tx0, tx1 = max(0, tx0), max(0, tx1)
    if ty1 <= ty0 or tx1 <= tx0:
        return None
    band = bgr[ty0:ty1, tx0:tx1]
    return band.reshape(-1, 3).mean(axis=0)[::-1]  # RGB


def persons():
    out = []
    for p in ["/home/operator/projects/pool/out/pid1_persons/report.json",
              "/home/operator/projects/pool/out/pid1_persons2/report2.json"]:
        if not Path(p).exists():
            continue
        for r in json.load(open(p)):
            hits = r.get("hits", r.get("persons", []))
            if r.get("prompt", "person") != "person":
                continue
            for h in hits:
                out.append({"t": r["t"], "bbox": h["bbox"], "score": h["score"],
                            "area": h["area"]})
    seen = set()
    uniq = []
    for o in out:
        k = (round(o["t"], 1), tuple(o["bbox"]))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(o)
    return uniq


def in_table_zone(bb):
    x0, y0, x1, y1 = bb
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx = QUAD[:, 0]
    qy = QUAD[:, 1]
    return (qx.min() - 90 <= cx <= qx.max() + 90) and (qy.min() - 150 <= cy <= qy.max() + 40)


def main():
    cap = cv2.VideoCapture(VIDEO)
    feats = []
    crops = []
    for p in persons():
        if not in_table_zone(p["bbox"]):
            continue
        cap.set(cv2.CAP_PROP_POS_MSEC, p["t"] * 1000.0)
        ok, bgr = cap.read()
        if not ok:
            continue
        col = torso_color(bgr, p["bbox"])
        if col is None:
            continue
        x0, y0, x1, y1 = p["bbox"]
        cx = (x0 + x1) / 2
        side = "L" if cx < QUAD[:, 0].mean() else "R"
        feats.append({"t": p["t"], "bbox": p["bbox"], "rgb": [round(v, 1) for v in col],
                      "side": side})
        img = bgr[max(0, y0 - 20):y1, max(0, x0 - 20):x1 + 20]
        crops.append((p["t"], side, img))
    cap.release()
    print(f"persons in table zone: {len(feats)}")
    X = np.array([f["rgb"] for f in feats], np.float32)
    # k-means k=2, a few restarts
    best = None
    for _ in range(8):
        _, lab, cen = cv2.kmeans(X, 2, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5),
                                 2, cv2.KMEANS_PP_CENTERS)
        s = float(((X - cen[lab].reshape(-1, 3)) ** 2).sum())
        if best is None or s < best[0]:
            best = (s, lab.ravel(), cen)
    _, lab, cen = best
    cen = cen[:, ::-1]  # RGB->BGR for display
    for f, l in zip(feats, lab):
        f["cluster"] = int(l)
    # separation metric
    d_between = float(np.linalg.norm(cen[0] - cen[1]))
    within = []
    for k in (0, 1):
        pts = X[lab == k]
        if len(pts):
            within.append(float(np.mean(np.linalg.norm(pts - cen[k][::-1].astype(np.float32), axis=1))))
    print(f"cluster centers (BGR): {np.round(cen,0).tolist()}")
    print(f"between={d_between:.0f} within={[round(w,1) for w in within]} "
          f"ratio={d_between/max(1e-6, np.mean(within)):.1f}")
    for f in sorted(feats, key=lambda z: z["t"]):
        print(f"t={f['t']:>7} cluster={f['cluster']} side={f['side']} rgb={f['rgb']} bbox={f['bbox']}")
    # montage: one row per cluster
    rows = []
    for k in (0, 1):
        items = [(f["t"], f["side"], img) for f, img in zip(feats, [c for _, _, c in crops])
                 if f["cluster"] == k][:12]
        # NOTE zip alignment maintained because feats order == crops order
        pass
    by_t = {}
    for f, (t, side, img) in zip(feats, crops):
        by_t.setdefault((round(f["t"], 1), f["cluster"]), []).append(img)
    all_cells = []
    for k in (0, 1):
        cells = []
        for (t, cl), imgs in sorted(by_t.items()):
            if cl != k:
                continue
            for im in imgs:
                im = cv2.resize(im, (140, 260))
                cv2.putText(im, f"t{t}", (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
                cells.append(im)
        if cells:
            row = np.hstack(cells)
            all_cells.append(row)
    if all_cells:
        wmax = max(r.shape[1] for r in all_cells)
        all_cells = [cv2.copyMakeBorder(r, 0, 0, 0, wmax - r.shape[1], cv2.BORDER_CONSTANT,
                                        value=(30, 30, 30)) for r in all_cells]
        mont = np.vstack(all_cells)
        Path("/home/operator/projects/pool/out/pid_identity_montage.png").parent.mkdir(exist_ok=True)
        cv2.imwrite("/home/operator/projects/pool/out/pid_identity_montage.png", mont)
        print("wrote out/pid_identity_montage.png")
    json.dump({"feats": feats,
               "centers_bgr": np.round(cen, 0).tolist(),
               "between": round(d_between, 1), "within": [round(w, 1) for w in within]},
              open("/home/operator/projects/pool/out/pid_identity_v0.json", "w"), indent=1)
    print("wrote out/pid_identity_v0.json")


if __name__ == "__main__":
    main()
