"""Does the playfield check hold on the historical VODs, end to end?

Run it with the project's interpreter:

    .venv/bin/python tools/playfield_vod_audit.py

For every VOD in ``data/vods`` it takes frames at 10%, 50% and 90%, runs the real
``TableStage`` on them - no saved calibration artifact exists for any ``tw-*``
dataset, so this is the measured path the console falls back to - and records the
playfield verdict with its reasons.

The audit is deliberately separate from ``tests/``: it runs the table detector, so
it takes minutes and needs the model weights.  ``out/playfield_vod_audit.json``
holds the last run for a comparison.

First run (2026-10-05, 19 VODs, 57 frames): 42 verdicts ok, 15 refused, and the
split is bimodal - 14 VODs pass at every sampled frame, 5 refuse at every sampled
frame with ``not-convex`` and ``no-parallel-pair`` together.  The check is doing
its job; the quads those five events yield are what needs looking at.
"""
"""End-to-end: does the playfield check hold on the historical VODs, on real measured quads?"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
from annotator.pipeline_stages import TableStage, StageContext

root = Path(__file__).resolve().parents[1]
vods = sorted((root / 'data/vods').glob('*.mp4'))
stage = TableStage(root, dataset=None, measure_every_n=30)   # no saved calibration: measure, like live
report, counts = [], {'ok': 0, 'refused': 0, 'no_quad': 0, 'unreadable': 0}
for vp in vods:
    cap = cv2.VideoCapture(str(vp))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 30.0
    row = {'vod': vp.name, 'frames': n, 'fps': round(fps, 3), 'picks': []}
    for frac in (0.10, 0.50, 0.90):
        idx = int(n * frac)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            row['picks'].append({'at': idx, 'read': False}); counts['unreadable'] += 1; continue
        ctx = StageContext({}, frame_number=idx, frame_index=idx, time_s=idx / fps)
        try:
            res = stage.process(frame, ctx) or {}
        except Exception as exc:
            row['picks'].append({'at': idx, 'error': str(exc)[:120]}); counts['unreadable'] += 1; continue
        pf = res.get('table_playfield')
        entry = {'at': idx, 't_s': round(idx / fps, 1),
                 'polygon': bool(res.get('table_polygon')),
                 'ok': None if not pf else bool(pf.get('ok')),
                 'reasons': (pf or {}).get('reasons')}
        if pf is None:
            counts['no_quad'] += 1
        elif pf.get('ok'):
            counts['ok'] += 1
        else:
            counts['refused'] += 1
        row['picks'].append(entry)
    cap.release()
    report.append(row)
    print(vp.name, json.dumps(row['picks']), flush=True)
print('SUMMARY', json.dumps(counts), flush=True)
print('REFUSED', json.dumps([{'vod': r['vod'], 'at': p['at'], 'reasons': p['reasons']}
                             for r in report for p in r['picks'] if p.get('reasons')]), flush=True)
root / 'out' / 'playfield_vod_audit.json'.write_text(json.dumps(report, indent=1))
