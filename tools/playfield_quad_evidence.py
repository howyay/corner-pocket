"""What do the refused quads actually look like? Evidence before a fix.

Five historical VODs get refused at every sampled frame with ``not-convex`` and
``no-parallel-pair`` together.  This tool prints the measured quad, its convexity, its
interior angles, its edge-pair angles and the check's own metrics, and draws the quad on
the frame - so the next step follows from what is on the screen, not from a guess.

    .venv/bin/python tools/playfield_quad_evidence.py

It writes ``out/playfield_quad_evidence.json`` and one PNG per pick under
``out/playfield_evidence/``.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from annotator.pipeline_stages import TableStage, StageContext
from src.playfield import PARALLEL_TOL_DEG, check_quad, parallelism

REFUSED = [
    'tw-2860883221', 'tw-2871819680', 'tw-2885294870', 'tw-2890340436', 'tw-2890514774',
]
FRACTIONS = (0.10, 0.50)


def convexity_signs(quad):
    """Cross product of each consecutive edge pair; a convex polygon keeps one sign."""
    pts = [(float(x), float(y)) for x, y in quad]
    signs = []
    for i in range(4):
        a, b, c = pts[i], pts[(i + 1) % 4], pts[(i + 2) % 4]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        signs.append(1 if cross > 0 else -1 if cross < 0 else 0)
    return signs


def interior_angles(quad):
    pts = [np.array([float(x), float(y)]) for x, y in quad]
    out = []
    for i in range(4):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % 4]
        u, v = a - b, c - b
        cos = float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9))
        out.append(round(math.degrees(math.acos(max(-1.0, min(1.0, cos)))), 2))
    return out


def classify(signs, angles, parallel):
    """Name the side the evidence points at: the detector, or the tolerance."""
    if 0 in signs or len(set(signs)) > 1:
        return 'detector: not a convex quad'
    if min(angles) < 20 or max(angles) > 160:
        return 'detector: corner order or corner pick is wrong'
    if parallel > 3 * PARALLEL_TOL_DEG:
        return 'detector: edges are not the table edges'
    if parallel > PARALLEL_TOL_DEG:
        return 'check: parallel within the detector noise, tolerance may be too tight'
    return 'unclear'


def main():
    root = Path(__file__).resolve().parents[1]
    out_dir = root / 'out/playfield_evidence'
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = TableStage(root, dataset=None, measure_every_n=30)
    report = []
    for name in REFUSED:
        vp = root / 'data/vods' / f'{name}.mp4'
        if not vp.exists():
            print(f'{name}: no file')
            continue
        cap = cv2.VideoCapture(str(vp))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 30.0
        for frac in FRACTIONS:
            idx = int(n * frac)
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                continue
            ctx = StageContext({}, frame_number=idx, frame_index=idx, time_s=idx / fps)
            res = stage.process(frame, ctx) or {}
            poly = res.get('table_polygon')
            pf = res.get('table_playfield') or {}
            if not poly:
                print(f'{name} @{frac:.0%}: no quad measured')
                continue
            quad = [(round(float(p[0]), 1), round(float(p[1]), 1)) for p in poly]
            signs = convexity_signs(quad)
            angles = interior_angles(quad)
            par_raw = parallelism(quad)
            par = round(float(max(v for v in par_raw.values() if isinstance(v, (int, float)))),
                        2) if isinstance(par_raw, dict) else round(float(par_raw), 2)
            verdict = classify(signs, angles, par)
            entry = {
                'vod': name, 'at': idx, 't_s': round(idx / fps, 1), 'quad': quad,
                'convexity': signs, 'interior_angles': angles, 'edge_pair_angle_deg': par,
                'parallel_tol_deg': PARALLEL_TOL_DEG,
                'check_ok': pf.get('ok'), 'reasons': pf.get('reasons'),
                'metrics': pf.get('metrics'), 'verdict': verdict,
            }
            report.append(entry)
            print(f'{name} @{frac:.0%} frame {idx}')
            print(f'   quad       {quad}')
            print(f'   convexity  {signs}  angles {angles}  edge-pair {par} deg (tol {PARALLEL_TOL_DEG})')
            print(f'   reasons    {pf.get("reasons")}  metrics {pf.get("metrics")}')
            print(f'   verdict    {verdict}')
            drawn = frame.copy()
            pts = np.array(quad, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(drawn, [pts], True, (0, 0, 255), 4)
            for i, (x, y) in enumerate(quad):
                cv2.circle(drawn, (int(x), int(y)), 9, (0, 255, 255), -1)
                cv2.putText(drawn, str(i), (int(x) + 12, int(y) - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
            cv2.imwrite(str(out_dir / f'{name}-{int(frac * 100)}.png'), drawn)
        cap.release()
    (root / 'out/playfield_quad_evidence.json').write_text(json.dumps(report, indent=1))
    verdicts = {}
    for r in report:
        verdicts[r['verdict']] = verdicts.get(r['verdict'], 0) + 1
    print('\npicks:', len(report), verdicts)


if __name__ == '__main__':
    main()
