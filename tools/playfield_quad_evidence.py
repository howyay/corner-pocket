"""What do the refused quads actually look like? Evidence before a fix.

Five historical VODs get refused at every sampled frame with ``not-convex`` and
``no-parallel-pair`` together.  This tool prints the measured quad, its convexity, its
interior angles, its edge-pair angles and the check's own metrics, and draws the quad on
the frame - so the next step follows from what is on the screen, not from a guess.

    .venv/bin/python tools/playfield_quad_evidence.py

It writes ``out/playfield_quad_evidence.json`` and one PNG per pick under
``out/playfield_evidence/``.  The recording and the stage come from
``tools/playfield_harness.py``, so this evidence is measured on the same path and the same
cadence as the served console, not on a copy of it.  The refused event ids come from the
audit tool, which holds them together with the reason of each refusal.  This tool keeps no
second list of ids and no second copy of a reason.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from src.playfield import PARALLEL_TOL_DEG, check_quad
from tools.playfield_harness import Recording, frame_context, new_stage
from tools.playfield_vod_audit import CLOTH_BAND_REASON, KNOWN_REFUSED

#: The reason the audit records for the five events this tool examines.  The evidence below
#: explains why that one reason needs to change: the detector, not the tolerance.  The ids
#: come from the audit, which is the one owner of the exceptions and of their reasons.
CLOTH_REASON = CLOTH_BAND_REASON
REFUSED = tuple(sorted(name[:-4] for name, reason in KNOWN_REFUSED.items()
                       if name.endswith('.mp4') and reason.startswith(CLOTH_REASON)))
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


def classify(signs, angles, parallel, parallel_tol):
    """Name the side the evidence points at: the detector, or the tolerance.

    ``parallel`` and ``parallel_tol`` come from the owner of the reading.  The owner answers
    ``ok`` when one pair of opposite edges reads parallel, so its reduction is the smaller of
    the two pair angles, and the test is ``best > parallel_tol``.  This function must not
    reduce the pair again: a second reduction with ``max`` reads the perspective angle as a
    fault and names the tolerance for a quad that the service accepts.
    """
    if 0 in signs or len(set(signs)) > 1:
        return 'detector: not a convex quad'
    if min(angles) < 20 or max(angles) > 160:
        return 'detector: corner order or corner pick is wrong'
    if parallel > 3 * parallel_tol:
        return 'detector: edges are not the table edges'
    if parallel > parallel_tol:
        return 'check: parallel within the detector noise, tolerance may be too tight'
    return 'unclear'


def best_check(quad, parallel_tol=PARALLEL_TOL_DEG):
    """The owner's verdict for the quad, from both rotations of the corner list.

    ``annotator/pipeline_stages.py:403`` checks the polygon as given and once rotated, then
    keeps the better verdict.  This tool reads a quad from the same stage, so it reads the same
    pair of verdicts.  The rotated form is tried second, because a quad that passes is uncommon
    in this evidence and the tool prints one verdict.

    A fault inside a check is not a pass: the caller sees the first verdict with the error.
    """
    rotated = list(quad[1:]) + list(quad[:1])
    try:
        verdicts = [check_quad(quad, parallel_tol=parallel_tol),
                    check_quad(rotated, parallel_tol=parallel_tol)]
    except Exception as exc:
        verdict = check_quad(quad, parallel_tol=parallel_tol)
        verdict['error'] = str(exc)
        return verdict
    return min(verdicts, key=lambda v: (not v['ok'], len(v['reasons'])))


def parallel_pair_reading(verdict):
    """The owner's pair reading and the owner's tolerance, out of the owner's own record.

    The check reduced the two pair angles to ``best_parallel_deg`` and recorded the tolerance
    that it used.  The tool reads those two fields and reduces nothing a second time.
    """
    metrics = verdict.get('metrics') or {}
    return metrics.get('best_parallel_deg'), metrics.get('parallel_tol_deg')


def pick_entry(name, idx, fps, quad, pf):
    """One measured pick, as the record keeps it.

    ``pf`` is the payload the served stage published with this quad.  The entry carries it
    unchanged, so the record's ``check_ok``, ``reasons`` and ``metrics`` are the service's own
    fields.  The pair reading and the tolerance come from the check's verdict for the same
    quad, in the two rotations the service tries, and the verdict names a side from them.
    """
    owner_verdict = best_check(quad)
    par, par_tol = parallel_pair_reading(owner_verdict)
    signs = convexity_signs(quad)
    angles = interior_angles(quad)
    return {
        'vod': name, 'at': idx, 't_s': round(idx / fps, 1), 'quad': quad,
        'convexity': signs, 'interior_angles': angles, 'edge_pair_angle_deg': par,
        'parallel_tol_deg': par_tol,
        'check_ok': pf.get('ok'), 'reasons': pf.get('reasons'),
        'metrics': pf.get('metrics'), 'verdict': classify(signs, angles, par, par_tol),
    }


def main():
    root = Path(__file__).resolve().parents[1]
    out_dir = root / 'out/playfield_evidence'
    out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for name in REFUSED:
        vp = root / 'data/vods' / f'{name}.mp4'
        if not vp.exists():
            print(f'{name}: no file')
            continue
        # One stage per event: a stage carries its measurement, which made every event read the
        # same quad when the tool reused one.
        stage = new_stage(root)
        try:
            recording = Recording(vp)
        except OSError as exc:
            print(f'{name}: {exc}')
            continue
        with recording:
            for frac in FRACTIONS:
                idx, frame = recording.frame_at(frac)
                if frame is None:
                    continue
                ctx = frame_context(idx, recording.fps)
                res = stage.process(frame, ctx) or {}
                poly = res.get('table_polygon')
                pf = res.get('table_playfield') or {}
                if not poly:
                    print(f'{name} @{frac:.0%}: no quad measured')
                    continue
                quad = [(round(float(p[0]), 1), round(float(p[1]), 1)) for p in poly]
                # One reading, one reduction: the check owns the pair angles, so every number
                # this tool reports for the pair comes from its verdict. A second reduction
                # here answered a different question and blamed the tolerance for a quad that
                # the service accepts.
                entry = pick_entry(name, idx, recording.fps, quad, pf)
                par, par_tol = entry['edge_pair_angle_deg'], entry['parallel_tol_deg']
                verdict = entry['verdict']
                report.append(entry)
                print(f'{name} @{frac:.0%} frame {idx}')
                print(f'   quad       {quad}')
                print(f'   convexity  {entry["convexity"]}  angles {entry["interior_angles"]}'
                      f'  edge-pair {par} deg (tol {par_tol})')
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
    (root / 'out/playfield_quad_evidence.json').write_text(json.dumps(report, indent=1))
    verdicts = {}
    for r in report:
        verdicts[r['verdict']] = verdicts.get(r['verdict'], 0) + 1
    print('\npicks:', len(report), verdicts)


if __name__ == '__main__':
    main()
