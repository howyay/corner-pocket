"""Cross-segment homography/projection audit (HOM-1 / PROJ-1 first cut).

For each video segment, detect the cloth quad at sampled frames, fit the
Rasson-rect homography, and measure:
  - corner px stability vs the segment's reference corners (fixed median),
  - implied physical error: reprojection of each frame's quad into mm through
    the per-frame H vs the reference H (mm at the 4 corners),
  - drift trend across time.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, '/home/operator/projects/pool/src')
from table_detect import detect_cloth_mask, fit_quadrilateral

TABLE_W, TABLE_H = 2540.0, 1270.0  # Rasson Victory III playing surface (mm)
DST = np.array([[0, 0], [TABLE_W, 0], [TABLE_W, TABLE_H], [0, TABLE_H]], np.float32)


def fit_h(corners):
    return cv2.getPerspectiveTransform(corners.reshape(4, 2).astype(np.float32), DST)


def audit(video, ref_corners, times, tag):
    ref = np.array(ref_corners, np.float32)
    H_ref = fit_h(ref)
    cap = cv2.VideoCapture(video)
    rows = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, bgr = cap.read()
        if not ok:
            continue
        mask = detect_cloth_mask(bgr)
        quad = fit_quadrilateral(mask)
        if quad is None:
            rows.append({"t": t, "error": "no quad"})
            continue
        px_err = float(np.linalg.norm(quad - ref, axis=1).mean())
        H = fit_h(quad)
        # physical corner deviation: map quad corners through H (mm) vs ideal rect
        mm_corners = cv2.perspectiveTransform(quad.reshape(1, 4, 2), H).reshape(4, 2)
        ideal = DST
        mm_err = float(np.linalg.norm(mm_corners - ideal, axis=1).mean())
        # relative to reference mapping: reproject ref corners through H_ref^-1 H ?
        Href_inv = np.linalg.inv(H_ref)
        proj = cv2.perspectiveTransform(quad.reshape(1, 4, 2), Href_inv @ H)
        proj_err_mm = float(np.linalg.norm(proj.reshape(4, 2) - DST, axis=1).mean())
        rows.append({"t": t, "px_err_vs_ref": round(px_err, 2),
                     "mm_err_vs_ideal": round(mm_err, 1),
                     "mm_err_rel": round(proj_err_mm, 1)})
    cap.release()
    ok_rows = [r for r in rows if "px_err_vs_ref" in r]
    print(f"\n== {tag} ({video.split('/')[-1]}) frames={len(rows)} ok={len(ok_rows)}")
    for r in rows:
        print("  ", r)
    if ok_rows:
        import statistics
        for k in ("px_err_vs_ref", "mm_err_vs_ideal", "mm_err_rel"):
            vals = sorted(r[k] for r in ok_rows)
            print(f"   {k}: median={statistics.median(vals)} p90={vals[int(len(vals)*0.9)]:.2f}")
    return rows


HL = "/home/operator/projects/pool/data/vod_highlight.mp4"
V30 = "/home/operator/projects/pool/data/vod_30min_260815.mp4"
fixed_hl = json.load(open("/home/operator/projects/pool/out/fixed_corners.json"))["corners"]
fixed_30 = json.load(open("/home/operator/projects/pool/out/corners_30min.json"))["corners"]

hl_times = [5, 28, 60, 90, 150, 200]
v30_times = list(range(60, 1741, 120))
out = {
    "highlight_1080p": audit(HL, fixed_hl, hl_times, "HIGHLIGHT 1080p"),
    "vod30_720p": audit(V30, fixed_30, v30_times, "VOD30 720p"),
}
Path("/home/operator/projects/pool/out/audit_homography.json").write_text(json.dumps(out, indent=1))
print("\nwrote out/audit_homography.json")
