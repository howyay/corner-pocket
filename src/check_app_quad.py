#!/usr/bin/env python3
"""Reproduce the Vision stage's "is the model quad drawable?" check offline.

``annotator/app.js`` refuses the automatic cloth quad when its mean corner
distance to the dataset's saved corners exceeds 40 px (``CLOTH_TOLERANCE_PX``,
* 1.0 for a same-size frame) or when the quad fails ``quadSanity``.  This script
runs that exact rule - same best-of-four-cyclic-alignments distance, same sanity
gates - on the frames of ``src/eval_table_detect``'s sample, for both the naive
detector and the refined one, against both saved vod30 references.

The point is to answer "will the app still refuse?" without a browser:

  * ``app-anchors`` is what the shipped app compares against (first four of the
    six hand anchors).  Those anchors are pocket-jaw centres, not cloth corners,
    so they sit ~44 px inside the cloth boundary; the script prints the best
    achievable mean distance for a cloth-corner quad as the reference floor.
  * ``corners30-v2`` is the recorded cloth reference (its own provenance is a
    refinement method - circularity caveat in the report).

Usage: PYTHONPATH=. .venv/bin/python -m src.check_app_quad [--frames 45]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from src.eval_table_detect import (ANCHORS, CORNERS_V2, HIGHLIGHT, TOLERANCE_PX, VOD30,
                                   load_references, quad_distance, quad_sanity)
from src.frame_inference import app_prior_for
from src.table_detect import detect_table
from src.table_refine import detect_table_refined

OUT = Path(__file__).resolve().parent.parent / 'out' / 'table-detect-eval'


def verdict(corners, reference, width, height):
    """The app's rule, verbatim in spirit: sanity first, then 40 px."""
    bad = quad_sanity(corners, width, height)
    if corners is None:
        return 'no detection', None
    if bad:
        return f'invalid geometry ({bad})', None
    fit = quad_distance(corners, reference['corners'])
    return ('ok' if fit['mean'] <= TOLERANCE_PX else 'off'), fit['mean']


def run(dataset, video, frames, detector):
    refs = load_references()[dataset]
    anchors = [r for r in refs if r['name'].startswith('app-anchors')]
    cloth = [r for r in refs if r['name'] == 'corners30-v2' or r['name'] == 'fixed-corners']
    cap = cv2.VideoCapture(str(video))
    rows = []
    for i in range(frames):
        t = round(1780 * i / max(1, frames - 1), 1) if dataset == 'vod30' else round(370 * i / max(1, frames - 1), 1)
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        # The search centre is resolved exactly as the server resolves it
        # (src.frame_inference.app_prior_for): a harness that picks its own prior
        # reports a different verdict than the browser.
        prior = app_prior_for(dataset)
        if dataset == 'vod30':
            # the app detects on the 2x-downscaled copy then scales back
            small = cv2.resize(frame, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
            prior_small = None if prior is None else np.asarray(prior, np.float32) / 2.0
            corners = detect_table_refined(small, prior=prior_small)['corners']
            naive = detect_table(small)['corners']
            corners = None if corners is None else np.asarray(corners, np.float32) * 2.0
            naive = None if naive is None else np.asarray(naive, np.float32) * 2.0
        else:
            corners = detect_table_refined(frame, prior=prior)['corners']
            naive = detect_table(frame)['corners']
        row = {'t': t}
        for label, quad in (('naive', naive), ('refined', corners)):
            for ref in anchors + cloth:
                if w != ref['width'] or h != ref['height']:
                    continue
                state, mean = verdict(None if quad is None else np.asarray(quad, np.float32),
                                      ref, w, h)
                row[f'{label}|{ref["name"]}|state'] = state
                row[f'{label}|{ref["name"]}|mean'] = None if mean is None else round(float(mean), 1)
        rows.append(row)
    cap.release()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', type=int, default=45)
    args = ap.parse_args()
    report = {'tolerance_px': TOLERANCE_PX,
              'circularity_note': ('corners30-v2 came from a refinement method and is scored '
                                   'against a refinement detector; app-anchors are pocket-jaw '
                                   'points, not cloth corners')}
    refs = load_references()
    for dataset, video in (('vod30', VOD30), ('highlight', HIGHLIGHT)):
        rows = run(dataset, video, args.frames, None)
        summary = {}
        keys = sorted({k for r in rows for k in r if k.endswith('|state')})
        for key in keys:
            label, ref_name = key.split('|')[0], key.split('|')[1]
            states = [r[key] for r in rows]
            means = [r[key.replace('|state', '|mean')] for r in rows
                     if r.get(key.replace('|state', '|mean')) is not None]
            summary[f'{label} vs {ref_name}'] = {
                'ok': states.count('ok'), 'refused': states.count('off'),
                'no_detection': sum(1 for s in states if s == 'no detection'),
                'invalid_geometry': sum(1 for s in states if s.startswith('invalid')),
                'mean_px_median': None if not means else round(float(np.median(means)), 1),
                'worst_mean_px': None if not means else max(means)}
        report[dataset] = {'frames': len(rows), 'verdicts': summary, 'rows': rows}
    path = OUT / 'app-verdict.json'
    path.write_text(json.dumps(report, indent=1))
    for dataset in ('vod30', 'highlight'):
        print(f"== {dataset}  frames={report[dataset]['frames']}  tolerance={TOLERANCE_PX}px")
        for name, v in report[dataset]['verdicts'].items():
            print(f"   {name:34s} ok={v['ok']:3d} refused={v['refused']:3d} "
                  f"no_detection={v['no_detection']:2d} invalid={v['invalid_geometry']:2d} "
                  f"median={v['mean_px_median']} worst={v['worst_mean_px']}")
    print(f"wrote {path}")


if __name__ == '__main__':
    main()
