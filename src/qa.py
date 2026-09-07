"""QA over pipeline results: bounds checks, per-frame stats, homography stability."""
from __future__ import annotations

import json
import sys

import numpy as np


def main():
    results = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "out/run1/results.json"))
    print(f"frames: {len(results)}")
    H, W = 500, 1000
    n_out = 0
    corners_list = []
    for r in results:
        t = r["t"]
        balls = r["balls"]
        inside = 0
        for b in balls:
            tx, ty = b["table"]
            if 0 <= tx <= W and 0 <= ty <= H:
                inside += 1
            else:
                n_out += 1
                print(f"  t={t}: ball OUT of bounds: {b}")
        colors = {}
        for b in balls:
            colors.setdefault(f"{b['color']} {b['style']}", 0)
            colors[b["color"] + " " + b["style"]] += 1
        print(f"t={t:6.1f} balls={len(balls):2d} inside={inside} "
              f"set={dict(sorted(colors.items(), key=lambda kv: -kv[1]))}")
        corners_list.append(np.array(r["corners"]))
    if n_out:
        print(f"{n_out} out-of-bounds detections")
    else:
        print("all projected balls inside canonical table bounds")
    corners = np.array(corners_list)
    if len(corners) > 1:
        std = corners.std(axis=0)
        print("corner stability across frames (px std per corner):")
        print(std.round(2))


if __name__ == "__main__":
    main()
