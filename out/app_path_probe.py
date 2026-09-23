#!/usr/bin/env python3
"""Does the app path compute the same quad as the full-resolution detector?

The offline harness (``src/eval_table_detect.py --detector app``) runs
``detect_table_refined`` on the *full-resolution* 1280x720 frame and scores it
against ``out/corners_30min_v2.json``.  The app runs the same detector on a
2x-downscaled 640x360 copy and scales the corners back
(``annotator/unified_server.Backend._unified_detection``), then validates the
result against the first four of ``out/pid_anchors_vod30.json`` (the hand
pocket anchors) with a 40 px mean-corner bar (``annotator/app.js``).

This harness puts the app path and the full-resolution path on the same frames
and prints, per frame:

* the app quad (the real server method, bound to a stub backend) and the
  full-resolution quad, plus the per-corner distance between them,
* each quad's mean corner error against BOTH saved references
  (``out/corners_30min_v2.json`` and the first four hand anchors),
* the app's own verdict (``src/check_app_quad.verdict``: quadSanity then the
  40 px rule) against both references,
* whether the app's quad came from the refined detector or from its naive
  fallback, and why the refined detector refused,
* a scale probe: the per-side displacement ``refine_quad_edges`` actually
  applies, against the offset it reports for that side (2.0 means the reported
  offset is in half-res mask pixels and the applied move is in frame pixels;
  1.0 means a side advances only half the frame-pixel correction).

Two things this project has already been wrong about, so both are pinned here:

* the detector is measured against the *revision* given by ``--refine-rev``
  (default ``HEAD``), not against whatever ``src/table_refine.py`` happens to
  contain: the revision's blob sha1 is stamped into the report.  ``worktree``
  measures the live file instead.
* ``--prior`` selects the search centre: ``saved`` is ``prior_for('vod30')``
  (``out/corners_30min_v2.json``), ``anchors`` is the hand anchor quad the app
  validates against.

Usage:
  PYTHONPATH=. .venv/bin/python out/app_path_probe.py --refine-rev HEAD --prior saved
  PYTHONPATH=. .venv/bin/python out/app_path_probe.py --refine-rev HEAD --prior anchors
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from annotator.unified_server import Backend  # noqa: E402
from src.check_app_quad import verdict  # noqa: E402
from src.eval_table_detect import VOD30, load_references, quad_distance  # noqa: E402
from src.table_detect import _order_corners  # noqa: E402

# 4 frames the refined detector refuses with ``low_cloth_area`` + 11 fresh ones
FRAMES = [849.5, 970.9, 1618.2, 1658.6,
          20.3, 61.0, 101.8, 183.3, 224.0, 264.8, 305.5, 387.0, 427.8, 468.6, 509.3]


class AppBackend(Backend):
    """Real ``Backend`` methods (``_unified_detection`` + ``_prior_for``) on a
    stub with only the state those two touch - no server, no other init."""

    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        self._unified_cache = OrderedDict()


def load_refinement(rev):
    """Import ``src/table_refine`` from ``rev`` and make the app path use it."""
    import src.table_refine as live
    if rev == 'worktree':
        blob = Path(live.__file__).read_bytes()
        return live, hashlib.sha1(blob).hexdigest(), 'worktree'
    blob = subprocess.check_output(['git', 'show', f'{rev}:src/table_refine.py'], cwd=ROOT)
    sha = subprocess.check_output(['git', 'rev-parse', f'{rev}:src/table_refine.py'],
                                  cwd=ROOT).strip().decode()
    path = Path(tempfile.mkdtemp(prefix='refine-rev-')) / 'table_refine_rev.py'
    path.write_bytes(blob)
    spec = importlib.util.spec_from_file_location('table_refine_rev', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The revision's own ROOT points at the temp dir it was written to; the
    # reference files it reads (out/corners_30min_v2.json) live in this tree.
    module.ROOT = ROOT
    # detect_table_for_frame imports these names at call time, so patching the
    # live module's attributes is enough to run the whole app path on the revision.
    for name in ('detect_table_refined', 'refine_quad_edges', 'prior_for', '_side_normal',
                 'draw_debug'):
        setattr(live, name, getattr(module, name))
    return module, sha, rev


def query_prior(name, root):
    """The quad the app path searches around: the saved reference or the anchors."""
    if name == 'auto':
        return np.asarray(AppBackend(root)._prior_for('vod30'), np.float32)
    if name == 'anchors':
        data = json.loads((root / 'out' / 'pid_anchors_vod30.json').read_text())['anchors']
        pts = next(v for k, v in data.items() if float(k) == 70.0)
        return _order_corners(np.asarray(pts[:4], np.float32))
    from src.table_refine import prior_for
    return prior_for('vod30', root=root)


def force_prior(prior):
    """Make the app path's own prior resolution return ``prior``.

    ``Backend._prior_for`` resolves the search centre through
    ``src.frame_inference.app_prior_for`` (it used to go through
    ``src.table_refine.prior_for``), so that is where a different search centre has
    to be injected to measure the counterfactual - patching anything else silently
    measures the real seed while claiming otherwise.
    """
    import src.frame_inference as frame_inference
    frame_inference.app_prior_for = lambda dataset, root=None: prior if str(dataset) == 'vod30' else None


def frame_at(t):
    cap = cv2.VideoCapture(str(VOD30))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f'cannot read vod30 at t={t}')
    return frame


def quad_json(quad):
    return None if quad is None else [[round(float(x), 2), round(float(y), 2)] for x, y in quad]


def corner_deltas(a, b):
    """Per-corner distance after the best cyclic alignment (the app's rule)."""
    return quad_distance(a, b)['distances']


def err(quad, ref):
    return None if quad is None else round(float(quad_distance(quad, ref['corners'])['mean']), 2)


def scale_probe(frame, prior):
    """Applied side displacement vs the reported mask offset (iters=1)."""
    from src.table_refine import _side_normal, refine_quad_edges
    quad, info = refine_quad_edges(frame, prior, iters=1)
    if quad is None:
        return {'reason': info.get('reason')}
    rows = []
    for report in info.get('sides') or []:
        s = report['side']
        if report.get('mask_offset_px') is None or abs(report['mask_offset_px']) < 1.0:
            continue
        nrm = _side_normal(np.asarray(prior, float)[s], np.asarray(prior, float)[(s + 1) % 4],
                           np.asarray(prior, float).mean(axis=0))
        mid = lambda q: (np.asarray(q, float)[s] + np.asarray(q, float)[(s + 1) % 4]) / 2.0
        applied = float(np.dot(mid(quad) - mid(prior), nrm))
        rows.append({'side': s, 'reported_mask_offset_px': report['mask_offset_px'],
                     'applied_px': round(applied, 2),
                     'applied_over_reported': round(applied / report['mask_offset_px'], 3),
                     'held': any(h['side'] == s for h in (info.get('held_sides') or []))})
    return {'band_scale': info.get('band_scale'), 'sides': rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refine-rev', default='HEAD',
                    help="git rev of src/table_refine.py to measure ('worktree' for the live file)")
    ap.add_argument('--prior', default='auto', choices=('auto', 'saved', 'anchors'),
                    help='auto = the app path resolves its own prior; saved/anchors force that '
                         'search centre into the app path and report the counterfactual')
    ap.add_argument('--json', default=None)
    args = ap.parse_args()
    out_json = args.json or str(ROOT / 'out' / f'app-path-probe-{args.prior}.json')

    module, refine_sha, refine_rev = load_refinement(args.refine_rev)
    refs = load_references()['vod30']
    anchors = next(r for r in refs if r['name'].startswith('app-anchors'))
    cloth = next(r for r in refs if r['name'] == 'corners30-v2')
    prior = query_prior(args.prior, ROOT)
    if args.prior != 'auto':
        force_prior(prior)
    app_detect = AppBackend(ROOT)._unified_detection

    rows, probe = [], []
    print(f'refine_rev={refine_rev} blob_sha1={refine_sha[:12]} prior={args.prior} '
          f'{np.asarray(prior).round(1).tolist()}')
    print(f'{"t":>8} {"app<->full":>11} {"app|v2":>8} {"app|anch":>9} '
          f'{"verdict(app|anch)":>18} {"full|v2":>8} {"full|anch":>10} {"branch":>14}')
    for i, t in enumerate(FRAMES):
        frame = frame_at(t)
        h, w = frame.shape[:2]
        scale = 2.0
        small = cv2.resize(frame, (w // 2, h // 2), interpolation=cv2.INTER_AREA)

        # 1. the app path, exactly as the server runs it
        app_corners, _balls = app_detect('vod30', i, frame)
        app_quad = None if app_corners is None else np.asarray(app_corners, np.float32)
        # which branch: refined-at-640x360, or its naive fallback?
        from src.frame_inference import detect_table_for_frame
        refined_small = detect_table_for_frame(small, prior=np.asarray(prior, np.float32) / scale)
        branch = 'refined' if refined_small.get('corners') is not None else 'naive_fallback'
        # the quad the app is handed on this branch: the server falls back to the
        # naive detector when the refinement refuses, then scales both back by 2
        from src.table_detect import detect_table
        handed = refined_small if refined_small.get('corners') is not None else detect_table(small)
        replay = None if handed.get('corners') is None else \
            np.asarray(handed['corners'], np.float32) * scale

        # 2. the full-resolution path the offline harness scores
        refined_full = detect_table_for_frame(frame, prior=np.asarray(prior, np.float32))
        full_quad = None if refined_full.get('corners') is None else np.asarray(refined_full['corners'], np.float32)

        delta = None if (app_quad is None or full_quad is None) else corner_deltas(app_quad, full_quad)
        row = {
            't': t, 'width': w, 'height': h, 'branch': branch,
            'app_quad': quad_json(app_quad), 'full_quad': quad_json(full_quad),
            'app_minus_full_px': delta,
            'app_minus_full_mean': None if delta is None else round(float(np.mean(delta)), 3),
            'app_minus_full_max': None if delta is None else round(float(max(delta)), 3),
            'replay_matches_app': bool(
                (app_quad is None and replay is None)
                or (app_quad is not None and replay is not None
                    and np.allclose(app_quad, replay, atol=0.06))),  # the server rounds to 0.1 px
            'app_refined_half_res_reason': refined_small.get('reason'),
            'full_refined_reason': refined_full.get('reason'),
            'app_err_v2': err(app_quad, cloth), 'app_err_anchors': err(app_quad, anchors),
            'full_err_v2': err(full_quad, cloth), 'full_err_anchors': err(full_quad, anchors),
            'app_verdict_anchors': verdict(app_quad, anchors, w, h),
            'app_verdict_v2': verdict(app_quad, cloth, w, h),
            'full_verdict_anchors': verdict(full_quad, anchors, w, h),
            'full_verdict_v2': verdict(full_quad, cloth, w, h),
        }
        rows.append(row)
        tag = row['app_verdict_anchors'][0] + (f" {row['app_verdict_anchors'][1]:.1f}"
                                              if row['app_verdict_anchors'][1] is not None else '')
        print(f'{t:>8} {row["app_minus_full_mean"]!s:>11} '
              f'{row["app_err_v2"]!s:>8} {row["app_err_anchors"]!s:>9} {tag:>18} '
              f'{row["full_err_v2"]!s:>8} {row["full_err_anchors"]!s:>10} {branch:>14}')
        probe.append({'t': t, **scale_probe(frame, np.asarray(prior, np.float32))})

    def stats(key):
        values = [r[key] for r in rows if r[key] is not None]
        return {'n': len(values),
                'median': None if not values else round(float(np.median(values)), 2),
                'p90': None if not values else round(float(np.percentile(values, 90)), 2),
                'max': None if not values else round(float(max(values)), 2)}

    def accept(key):
        values = [r[key][1] for r in rows if r[key][1] is not None]
        return {'n': len(values),
                'accept_at_40': None if not values else round(
                    sum(1 for v in values if v <= 40.0) / len(rows), 3)}

    summary = {
        'frames': len(rows), 'refine_rev': refine_rev, 'refine_blob_sha1': refine_sha,
        'prior_source': args.prior, 'prior': quad_json(prior),
        'app_vs_full_delta_mean': stats('app_minus_full_mean'),
        'identical_app_vs_full': all(r['app_minus_full_mean'] == 0 for r in rows),
        'replay_matches_app_all': all(r['replay_matches_app'] for r in rows),
        'app_vs_v2': stats('app_err_v2'), 'app_vs_anchors': stats('app_err_anchors'),
        'full_vs_v2': stats('full_err_v2'), 'full_vs_anchors': stats('full_err_anchors'),
        'app_accept_vs_anchors': accept('app_verdict_anchors'),
        'app_accept_vs_v2': accept('app_verdict_v2'),
        'app_states_anchors': {state: sum(1 for r in rows if r['app_verdict_anchors'][0] == state)
                               for state in ('ok', 'off', 'no detection')},
        'app_states_v2': {state: sum(1 for r in rows if r['app_verdict_v2'][0] == state)
                          for state in ('ok', 'off', 'no detection')},
        'branches': {b: sum(1 for r in rows if r['branch'] == b)
                     for b in ('refined', 'naive_fallback')},
        'refusal_reasons': {str(r['app_refined_half_res_reason']): sum(
            1 for x in rows if str(x['app_refined_half_res_reason']) == str(r['app_refined_half_res_reason']))
            for r in rows},
    }
    print('\n' + json.dumps(summary, indent=1))
    ratios = [s['applied_over_reported'] for p in probe for s in p.get('sides', []) if not s['held']]
    if ratios:
        print(f'scale probe: applied/reported per side  median {np.median(ratios):.3f}  '
              f'n={len(ratios)}  (2.0 = reported offset is mask pixels and the applied move is '
              f'frame pixels; 1.0 = a side advances half the correction it measured)')
    Path(out_json).write_text(json.dumps({'summary': summary, 'rows': rows, 'scale_probe': probe}, indent=1))
    print(f'wrote {out_json}')


if __name__ == '__main__':
    main()
