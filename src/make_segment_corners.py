"""Build a robust per-segment corner reference from temporal median (static cam).

Samples frames every N seconds, fits a loose cloth quad per frame, keeps quads
whose corners agree with the running median (MAD gate), then reports the median
corner set + residual stats. Writes out/corners_<tag>_v2.json.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, '/home/operator/projects/pool/src')
from table_detect import detect_cloth_mask, fit_quadrilateral


def loose_quad(bgr):
    m = detect_cloth_mask(bgr)
    return fit_quadrilateral(m)


def build(video, tag, every_s=6.0, max_frames=400, mad_px=6.0):
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, int(every_s * fps))
    quads = []
    idx = 0
    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx * step)
        ok, f = cap.read()
        if not ok:
            break
        q = loose_quad(f)
        if q is not None:
            quads.append(q.reshape(-1))
        idx += 1
        if idx >= max_frames:
            break
    cap.release()
    if len(quads) < 8:
        print(f'{tag}: only {len(quads)} quads, abort')
        return None
    Q = np.array(quads)  # (N,8)
    # iterative MAD filter per corner coordinate
    cur = np.median(Q, axis=0)
    for _ in range(4):
        d = np.abs(Q - cur).reshape(len(Q), 4, 2)
        d = d.max(axis=(1, 2))
        keep = d <= mad_px * 3
        if keep.sum() < 8:
            break
        Q = Q[keep]
        cur = np.median(Q, axis=0)
    d = np.abs(Q - cur).reshape(len(Q), 4, 2)
    per_corner = d.max(axis=0)
    corners = cur.reshape(4, 2)
    resid = np.linalg.norm(Q.reshape(-1, 4, 2) - corners, axis=2)
    out = {
        "tag": tag,
        "video": video,
        "n_frames": idx,
        "n_accepted": int(len(Q)),
        "corners": np.round(corners, 2).tolist(),
        "per_corner_mad_px": np.round(per_corner, 2).tolist(),
        "per_frame_max_px": np.round(resid.max(axis=1), 2).tolist(),
        "median_frame_px": float(np.round(np.median(resid.max(axis=1)), 2)),
        "p90_frame_px": float(np.round(np.percentile(resid.max(axis=1), 90), 2)),
    }
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "30min"
    video = sys.argv[2] if len(sys.argv) > 2 else \
        "/home/operator/projects/pool/data/vod_30min_260815.mp4"
    res = build(video, tag)
    if res:
        Path(f"/home/operator/projects/pool/out/corners_{tag}_v2.json").write_text(
            json.dumps(res, indent=1))
        print("wrote out/corners_%s_v2.json" % tag)
