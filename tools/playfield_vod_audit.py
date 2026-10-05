"""Does the playfield check hold on the historical VODs, end to end?

Run it with the project's interpreter:

    .venv/bin/python tools/playfield_vod_audit.py

For every VOD in ``data/vods`` it takes frames at 10%, 50% and 90%, runs the real
``TableStage`` on them - no saved calibration artifact exists for any ``tw-*`` dataset,
so this is the measured path the console falls back to - and records the playfield
verdict with its reasons and metrics.

Two corrections shaped this tool.  A stage carries its measurement, so one stage per
event is required: a reused stage reported the same quad for ten picks and an earlier
run claimed 42 passes where the measured number is 24.  And the events that refuse
everywhere are not refusing a real table: their cloth mask is a band across a rail (the
probe on tw-2860883221 fitted a quad with an aspect of 8.345 against the 2.0 that a
100x50 inch playfield has), so the detector is what those events need - not a looser
tolerance.  They are named at the bottom instead of being averaged away.

``out/playfield_vod_audit.json`` holds the last run for a comparison.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
from annotator.pipeline_stages import TableStage, StageContext

root = Path(__file__).resolve().parents[1]
vods = sorted((root / 'data/vods').glob('*.mp4'))
# One stage per VOD: a reused stage carries its measurement across events, which made every
# event after the first report the same quad.  The audit measures each event on its own.
STAGE_NOTE = 'one stage per VOD, no saved calibration: measure, like live'
report, counts = [], {'ok': 0, 'refused': 0, 'no_quad': 0, 'unreadable': 0}
for vp in vods:
    stage = TableStage(root, dataset=None, measure_every_n=30)
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
                 'aspect': None if not pf else pf.get('aspect'),
                 'best_parallel_deg': None if not pf else pf.get('best_parallel_deg'),
                 'quad': [[round(float(q[0]), 1), round(float(q[1]), 1)]
                          for q in (res.get('table_polygon') or [])],
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
    ok_flags = [p.get('ok') for p in row['picks']]
    row['verdict'] = ('pass' if all(f is True for f in ok_flags)
                      else 'refuse' if all(f is False for f in ok_flags)
                      # Every pick read but no table came out of any of them: that is not "mixed",
                      # and calling it that hid seven events behind one word.
                      else 'no_quad' if all(f is None for f in ok_flags) else 'mixed')
    report.append(row)
    print('%-24s %-7s %s' % (vp.name, row['verdict'], ' '.join(
        'ok' if p.get('ok') else ('refused' if p.get('ok') is False else 'no-quad')
        for p in row['picks'])), flush=True)
full_pass = sorted(r['vod'] for r in report if r['verdict'] == 'pass')
print('SUMMARY', json.dumps(counts), flush=True)
print('PASS-AT-EVERY-FRAME', json.dumps(full_pass), flush=True)
out_file = root / 'out/playfield_vod_audit.json'
out_file.parent.mkdir(parents=True, exist_ok=True)
out_file.write_text(json.dumps({'counts': counts, 'passing': full_pass,
                                'measured': '2026-10-05, one stage per VOD', 'report': report}, indent=1))
# The replay test reads the fixture, so the recorded quads travel with the repository.
fixture = root / 'tests/fixtures/playfield_quads.json'
fixture.parent.mkdir(parents=True, exist_ok=True)
fixture.write_text(json.dumps({
    'measured': '2026-10-05, one stage per VOD',
    'counts': counts,
    'passing': full_pass,
    'picks': [{'vod': r['vod'], 'at': pick['at'], 'quad': pick.get('quad'),
               'ok': pick.get('ok'), 'reasons': pick.get('reasons'),
               'aspect': pick.get('aspect'),
               'best_parallel_deg': pick.get('best_parallel_deg')}
              for r in report for pick in r['picks'] if pick.get('quad')]}, indent=1))
# Two locks, both measured.  The floor is how many events pass at every sampled frame; the
# exceptions are the events that do not, each named with what its measurement actually was.  An
# event that refuses everywhere and is not named is a regression, so the run fails.
FLOOR = 8
KNOWN_REFUSED = {
    # The cloth mask is a band across a rail, so the fit collapses and no table is reported.
    'tw-2860883221.mp4': 'cloth mask is a band: the ordered fit collapses (aspect 8.345)',
    'tw-2871819680.mp4': 'cloth mask is a band: the ordered fit collapses',
    'tw-2885294870.mp4': 'cloth mask is a band: the ordered fit collapses',
    'tw-2890340436.mp4': 'cloth mask is a band: the ordered fit collapses',
    'tw-2890514774.mp4': 'cloth mask is a band: the ordered fit collapses',
    # A quad is measured and the check refuses it.
    'tw-2252489073.mp4': 'measured quad refused: no-parallel-pair',
    'tw-2467528195.mp4': 'measured quad refused: no-parallel-pair',
    'tw-2784932919.mp4': 'measured quad refused: no-parallel-pair',
    'tw-2796131568.mp4': 'measured quad refused: no-parallel-pair',
    # No table comes out at all.
    'tw-2251161439.mp4': 'no quad measured',
    'tw-2638346864.mp4': 'no quad measured',
}
unexpected = sorted(r['vod'] for r in report
                    if r['verdict'] != 'pass' and r['vod'] not in KNOWN_REFUSED)
if unexpected:
    print('THRESHOLD FAIL: events that refuse everywhere and are not named: %s' % (unexpected,), flush=True)
    raise SystemExit(1)
print('EXCEPTIONS OK: %d named, %d not passing'
      % (len(KNOWN_REFUSED), sum(1 for r in report if r['verdict'] != 'pass')), flush=True)
if len(full_pass) < FLOOR:
    print('THRESHOLD FAIL: %d events pass at every frame, floor is %d' % (len(full_pass), FLOOR), flush=True)
    raise SystemExit(1)
print('THRESHOLD OK: %d events pass at every frame (floor %d)' % (len(full_pass), FLOOR), flush=True)
