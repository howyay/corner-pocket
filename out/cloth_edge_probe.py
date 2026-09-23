#!/usr/bin/env python3
"""Where is the cloth, really? Scanline runs of the cloth hue vs both references.

The app refuses the refined quad because it sits ~43 px from the first four hand
anchors.  Two incompatible explanations survive: the anchors are pocket jaws
*inside* the cloth (the detector is right, the reference is wrong), or the
detector's mask boundary is on the carpet *outside* the cloth (the anchors are
right, the detector is wrong).  This script measures the frame itself: it
classifies each pixel with the detector's own cloth rule (adaptive hue +-16,
S>=105, V>=55) and prints, for the rows through the disputed corners, the runs
of cloth pixels, next to where the anchors, the saved reference quad
(``corners_30min_v2``) and the detector's final mask put their edges.

Usage: PYTHONPATH=. .venv/bin/python out/cloth_edge_probe.py [--t 61.0 183.3]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.eval_table_detect import VOD30, load_references  # noqa: E402
from src.quad_fit import _anchor_hue  # noqa: E402
from src.table_detect import detect_cloth_mask  # noqa: E402
from src.table_refine import detect_table_refined, prior_for  # noqa: E402

MIN_RUN = 25


def runs(flags, lo=0, hi=None):
    """Contiguous True runs of length >= MIN_RUN as (start, end) x ranges."""
    hi = len(flags) if hi is None else hi
    out, start = [], None
    for i in range(lo, hi):
        if flags[i] and start is None:
            start = i
        elif not flags[i] and start is not None:
            if i - start >= MIN_RUN:
                out.append((start, i - 1))
            start = None
    if start is not None and hi - start >= MIN_RUN:
        out.append((start, hi - 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--t', type=float, nargs='+', default=[61.0, 183.3, 468.6])
    args = ap.parse_args()

    refs = load_references()['vod30']
    anchors = next(r for r in refs if r['name'].startswith('app-anchors'))['corners']
    cloth_ref = next(r for r in refs if r['name'] == 'corners30-v2')['corners']
    prior = np.asarray(prior_for('vod30'), np.float64)
    report = {}
    for t in args.t:
        cap = cv2.VideoCapture(str(VOD30))
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        cap.release()
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        centre = tuple(np.rint(prior.mean(axis=0)).astype(int))
        patch = hsv[max(0, centre[1] - 40):centre[1] + 41, max(0, centre[0] - 40):centre[0] + 41].reshape(-1, 3)
        bed_hue = int(np.median(patch[:, 0]))
        anchor_hue = int(_anchor_hue(frame))
        mask = detect_cloth_mask(frame)
        mask = None if mask is None else (np.asarray(mask) > 0)
        refined = detect_table_refined(frame, prior=prior_for('vod30'))
        quad = None if refined['corners'] is None else np.asarray(refined['corners'], np.float64)

        rows = {}
        for y in (int(anchors[0][1]), int(prior[0][1]), int(prior[3][1]), int(anchors[3][1])):
            hue_ok = (np.abs(hsv[y, :, 0].astype(int) - anchor_hue) <= 16) & (hsv[y, :, 1] >= 105) & (hsv[y, :, 2] >= 55)
            bed_ok = (np.abs(hsv[y, :, 0].astype(int) - bed_hue) <= 16) & (hsv[y, :, 1] >= 105) & (hsv[y, :, 2] >= 55)
            entry = {'cloth_hue_runs_in_300_1100': runs(hue_ok, 300, 1100),
                     'bed_hue_runs_in_300_1100': runs(bed_ok, 300, 1100),
                     'stock_mask_runs_in_300_1100': None if mask is None else runs(mask[y], 300, 1100)}
            rows[y] = entry
        report[t] = {
            'anchor_hue': anchor_hue, 'bed_median_hue': bed_hue,
            'anchors': [[round(float(x), 1), round(float(y), 1)] for x, y in anchors],
            'corners30_v2': [[round(float(x), 1), round(float(y), 1)] for x, y in cloth_ref],
            'prior': [[round(float(x), 1), round(float(y), 1)] for x, y in prior],
            'refined': None if quad is None else [[round(float(x), 1), round(float(y), 1)] for x, y in quad],
            'rows': rows,
        }
        print(f"== t={t}  anchor_hue={anchor_hue}  bed_hue={bed_hue}  refined={report[t]['refined']}")
        for y, entry in rows.items():
            print(f"  y={y:4d} cloth-hue runs {entry['cloth_hue_runs_in_300_1100']}")
            print(f"        stock-mask runs {entry['stock_mask_runs_in_300_1100']}")
    Path(ROOT / 'out' / 'cloth-edge-probe.json').write_text(json.dumps(report, indent=1))
    print('wrote out/cloth-edge-probe.json')


if __name__ == '__main__':
    main()
