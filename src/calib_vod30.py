"""Vod30 full calibration with rect-constrained PnP (HOM-1 bar) + per-anchor mm.

Uses calibrate.py machinery: H_prior = corners_30min_v2 quad -> portrait mm
(1270 x 2540, calibrate convention). Runs the 6-pocket-anchor PnP pipeline over
~200 spread frames, then computes per-anchor residual tables in px AND mm
(numerical local scale), corner vs side-pocket breakdown, mean/median per frame.

Bar (per prior sessions): mean anchor reprojection <= 15 mm.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from calibrate import (OBJECT_MM, pnp_solve, project, refined_blob,
                       anchors_for_frame, quad_ok)
from table_detect import detect_cloth_mask, fit_quadrilateral
from table_geometry import canonical_destination

VIDEO = ROOT.parent / "data" / "vod_30min_260815.mp4"
CORNERS = ROOT.parent / "out" / "corners_30min_v2.json"
N_SAMPLES = 200
DST = canonical_destination()  # px -> mm, the canonical portrait frame


def main():
    corners = np.array(json.load(open(CORNERS))["corners"], np.float32)
    H_prior = cv2.getPerspectiveTransform(corners, DST)  # px -> mm (portrait)

    cap = cv2.VideoCapture(str(VIDEO))
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
    W, H = int(cap.get(3)), int(cap.get(4))

    # focal scan on a subset (fast) then full pass at best f
    ts_all = np.linspace(dur * 0.02, dur * 0.98, N_SAMPLES)

    def collect(ts):
        out = []
        for t in ts:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, bgr = cap.read()
            if not ok:
                continue
            cloth = detect_cloth_mask(bgr)
            quad = fit_quadrilateral(cloth)
            if quad is None or not quad_ok(cloth, quad):
                continue
            corners6, sides = anchors_for_frame(bgr, quad, cloth, H_prev=H_prior)
            if corners6 is None or any(c is None for c in corners6) or len(sides) != 2:
                continue
            img6 = np.array(list(corners6) + list(sides), dtype=np.float32)
            out.append((t, img6))
        return out

    sub = collect(ts_all[::2])
    best_f, best_med = None, 1e18
    for f in np.linspace(600, 2000, 41):
        meds = []
        for _, img6 in sub:
            Hm = pnp_solve(img6, f, W, H)
            if Hm is None:
                continue
            meds.append(float(np.sqrt(((project(Hm, OBJECT_MM) - img6) ** 2).sum(axis=1)).mean()))
        if meds:
            m = float(np.median(meds))
            if m < best_med:
                best_med, best_f = m, f
    print(f"best f={best_f:.0f} median resid {best_med:.2f}px over {len(sub)} frames", flush=True)

    full = collect(ts_all)
    per_frame_px = []
    anchor_px = {i: [] for i in range(6)}
    for t, img6 in full:
        Hm = pnp_solve(img6, best_f, W, H)
        if Hm is None:
            continue
        proj = project(Hm, OBJECT_MM)
        res = np.linalg.norm(proj - img6, axis=1)
        per_frame_px.append(float(res.mean()))
        for i in range(6):
            anchor_px[i].append(float(res[i]))
    cap.release()
    print(f"frames used: {len(per_frame_px)}")
    names = ["TL", "TR", "BR", "BL", "left-side", "right-side"]

    # mm scale per anchor: numeric local px-per-mm from the MEDIAN H
    Hs = []
    for t, img6 in full:
        Hm = pnp_solve(img6, best_f, W, H)
        if Hm is not None:
            Hs.append(Hm)
    Hmed = np.median(np.array(Hs), axis=0)

    def mm_of_anchor(i, px_err):
        if px_err is None:
            return None
        o = OBJECT_MM[i]
        p0 = project(Hmed, o.reshape(1, -1))[0]
        # px travel for +-1 mm in x and y
        sx = np.linalg.norm(project(Hmed, (o + [1, 0]).reshape(1, -1))[0] - p0)
        sy = np.linalg.norm(project(Hmed, (o + [0, 1]).reshape(1, -1))[0] - p0)
        s = (sx + sy) / 2
        return px_err / max(s, 1e-9)

    anchor_mm = {}
    print("\nper-anchor residual (px -> mm):")
    for i in range(6):
        arr = sorted(anchor_px[i])
        med_px = arr[len(arr) // 2]
        med_mm = mm_of_anchor(i, med_px)
        anchor_mm[names[i]] = round(med_mm, 1)
        print(f"  {names[i]:>10}: median {med_px:.2f} px = {med_mm:.1f} mm  (n={len(arr)})")

    # ---- bias-corrected holdout (like the highlight pipeline): split frames,
    # learn per-anchor bias (detected - projected) on train, residual on test
    full2 = [(t, img6) for t, img6 in full]
    Hs2 = []
    for t, img6 in full2:
        Hm = pnp_solve(img6, best_f, W, H)
        if Hm is not None:
            Hs2.append(Hm)
    n = len(full2)
    half = n // 2
    biases = {}
    for i in range(6):
        diffs = []
        for (t, img6), Hm in zip(full2[:half], Hs2[:half]):
            proj = project(Hm, OBJECT_MM)
            diffs.append(img6[i] - proj[i])
        biases[i] = np.median(np.array(diffs), axis=0) if diffs else np.zeros(2)
    test_mm = []
    for (t, img6), Hm in zip(full2[half:], Hs2[half:]):
        proj = project(Hm, OBJECT_MM)
        errs = [np.linalg.norm((img6[i] - biases[i]) - proj[i]) for i in range(6)]
        test_mm.append(float(np.mean([mm_of_anchor(i, errs[i]) for i in range(6)])))
    holdout = {"mean_mm": round(float(np.mean(test_mm)), 1),
               "median_mm": round(float(np.median(test_mm)), 1),
               "n_test": len(test_mm),
               "bias_px": {names[i]: np.round(biases[i], 2).tolist() for i in range(6)}}
    print("bias-corrected holdout:", json.dumps(holdout, indent=1))
    per_frame_mm = test_mm
    out = {
        "f_px": round(best_f, 1),
        "frames": len(per_frame_px),
        "per_anchor_median_mm": anchor_mm,
        "mean_mm": round(float(np.mean(per_frame_mm)), 1),
        "median_mm": round(float(np.median(per_frame_mm)), 1),
        "mean_px": round(float(np.mean(per_frame_px)), 2),
    "holdout": holdout,
    }
    out["H"] = np.round(Hmed, 6).tolist()
    Path(ROOT.parent / "out" / "calib_vod30.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    print("bar: mean <= 15 mm ->", "MET" if out["mean_mm"] <= 15 else "NOT MET")


if __name__ == "__main__":
    main()
