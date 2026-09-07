"""Holdout evaluation of the rectangle-constrained calibration.

Fit the table homography on a subset of frames (PnP over 6 pocket anchors,
robust median over per-frame fits, outlier frames rejected) and measure the
generalization residual on HELD-OUT frames, reported in mm per anchor using
the local mm<->px scale at each anchor.

Bar: mean pocket-anchor error <= 15 mm on >= 5 held-out frames.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import calibrate
from calibrate import (OBJECT_MM, anchors_for_frame, pnp_solve, project)
from pipeline import homography_to_canonical
from table_detect import detect_cloth_mask, fit_quadrilateral


def collect_frames(video: str, every: float = 45.0):
    cap = cv2.VideoCapture(video)
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
    corners_ref = np.array(
        json.load(open(ROOT.parent / "out" / "corners_30min.json"))["corners"],
        dtype=np.float32,
    )
    H_prior = homography_to_canonical(corners_ref)
    frames = []
    t = 30.0
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, bgr = cap.read()
        if ok:
            cloth = detect_cloth_mask(bgr)
            quad = fit_quadrilateral(cloth)
            if quad is not None and calibrate.quad_ok(cloth, quad):
                corners6, sides = anchors_for_frame(bgr, quad, cloth, H_prev=H_prior)
                img6 = np.array(corners6 + sides, dtype=np.float32)
                if img6.shape == (6, 2) and np.isfinite(img6).all():
                    frames.append({"t": t, "img6": img6})
        t += every
    cap.release()
    return frames, H_prior


def local_mm_per_px(Hm, canon_pt):
    """mm per pixel at a canonical point, from the H Jacobian (approx)."""
    d = 1.0  # 1 mm in canonical x
    p0 = project(Hm, np.array([canon_pt]))
    p1 = project(Hm, np.array([[canon_pt[0] + d, canon_pt[1]]]))
    return float(np.hypot(p1[0][0] - p0[0][0], p1[0][1] - p0[0][1]) / d)  # px per mm


def main():
    video = sys.argv[1] if len(sys.argv) > 1 else "data/vod_30min_260815.mp4"
    frames, _ = collect_frames(video)
    print(f"{len(frames)} usable frames", flush=True)
    if len(frames) < 10:
        print("not enough frames", flush=True)
        return
    W, H = 1280, 720
    # split: odd = fit, even = holdout
    fit_frames = [f for i, f in enumerate(frames) if i % 2 == 0]
    hold_frames = [f for i, f in enumerate(frames) if i % 2 == 1]
    # focal scan on fit frames
    best = None
    for f in np.linspace(1200, 4000, 29):
        res = []
        for fr in fit_frames:
            Hm = pnp_solve(fr["img6"], f, W, H)
            if Hm is None:
                continue
            err = float(np.sqrt(((project(Hm, OBJECT_MM) - fr["img6"]) ** 2).sum(axis=1)).mean())
            res.append(err)
        med = float(np.median(res)) if res else 1e18
        if best is None or med < best[0]:
            best = (med, f)
    f_opt = best[1]
    print(f"focal (fit set): {f_opt:.0f} px, median residual {best[0]:.2f} px", flush=True)

    # robust per-frame fits at f_opt on the FIT set; reject outlier frames
    fits = []
    for fr in fit_frames:
        Hm = pnp_solve(fr["img6"], f_opt, W, H)
        if Hm is None:
            continue
        err = float(np.sqrt(((project(Hm, OBJECT_MM) - fr["img6"]) ** 2).sum(axis=1)).mean())
        fits.append((err, Hm))
    errs = np.array([e for e, _ in fits])
    med = float(np.median(errs))
    good = [Hm for e, Hm in fits if e <= med * 1.6]  # keep within 1.6x median
    H_final = np.median(np.array(good), axis=0)
    print(f"fit frames: {len(fits)}, kept: {len(good)} (median resid {med:.2f} px)", flush=True)

    # HOLD-OUT evaluation in mm (local scale per anchor)
    mm_errs = []
    for fr in hold_frames:
        proj = project(H_final, OBJECT_MM)
        px_err = np.sqrt(((proj - fr["img6"]) ** 2).sum(axis=1))
        for i in range(6):
            spp = local_mm_per_px(H_final, OBJECT_MM[i])
            mm_errs.append(px_err[i] / spp)  # px / (px per mm) = mm
    mm_errs = np.array(mm_errs)
    print(f"HOLD-OUT ({len(hold_frames)} frames):")
    print(f"  per-anchor mean mm error: {mm_errs.mean():.1f}")
    print(f"  per-anchor median mm error: {np.median(mm_errs):.1f}")
    # per-frame mean (each frame's 6 anchors averaged)
    per_frame_mm = []
    for fr in hold_frames:
        proj = project(H_final, OBJECT_MM)
        px_err = np.sqrt(((proj - fr["img6"]) ** 2).sum(axis=1))
        spp = np.array([local_mm_per_px(H_final, OBJECT_MM[i]) for i in range(6)])
        per_frame_mm.append((px_err / spp).mean())
    per_frame_mm = np.array(per_frame_mm)
    print(f"  per-frame mean mm: {per_frame_mm.mean():.1f} (min {per_frame_mm.min():.1f}, "
          f"max {per_frame_mm.max():.1f})")
    json.dump({
        "f_opt": f_opt, "n_fit": len(good), "n_holdout": len(hold_frames),
        "mean_mm": round(float(mm_errs.mean()), 1),
        "median_mm": round(float(np.median(mm_errs)), 1),
        "per_frame_mean_mm": round(float(per_frame_mm.mean()), 1),
        "H": H_final.tolist(),
    }, open(ROOT.parent / "out" / "calib_holdout.json", "w"), indent=1)
    print("saved out/calib_holdout.json", flush=True)


if __name__ == "__main__":
    main()
