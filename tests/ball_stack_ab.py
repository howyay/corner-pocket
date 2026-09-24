"""Is the live (causal) stack as good as the trained (centred) one?

The tiny ball net was trained on ``(t-1, t, t+1)`` (``src/tiny_ball_net.py``,
``STACK = 3``).  A live pipeline has only the past, so ``BallStage`` feeds it
``(t-2, t-1, t)`` instead - the same three frames, one frame earlier.  That is a
domain shift nobody has measured, and the held-out labels can measure it: same 47
held-out frames, same preprocessing code path as the stage, two stack layouts.

This is also the stage's correctness check.  The centred column is the layout the
published operating point was measured on (F1 0.927 / P 0.940 / R 0.914 at
threshold 0.425), so if it does not reproduce those numbers the stage's resize,
stack and decode differ from the probe's and the causal column is meaningless.

Run: PYTHONPATH=. .venv/bin/python -B tests/ball_stack_ab.py
Writes out/tiny_ball_probe/stack_ab.json (out/ is gitignored).
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

SWEEP = [round(0.05 + 0.025 * i, 3) for i in range(38)]
TOL_PX = 6.0


def decode_spans(video, indices, size):
    """Native frames for ``indices``, one seek per cluster, then downscaled.

    Deliberately not ``tiny_ball_net.read_frames``: that fills a module-level cache
    with every frame it touches, and this probe must not pay for or pollute it.
    """
    import cv2
    wanted = sorted(set(int(i) for i in indices))
    out = {}
    cap = cv2.VideoCapture(str(video))
    try:
        for index in wanted:
            if index in out:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, bgr = cap.read()
            if not ok:
                continue
            out[index] = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
    finally:
        cap.release()
    return out


def stack_of(frames, index, offsets, size):
    """The stage's own stack build: RGB planes, concatenated, /255."""
    import cv2
    import numpy as np
    planes = []
    for k in offsets:
        small = frames.get(index + k)
        if small is None:
            return None
        planes.append(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    return np.concatenate(planes, axis=2).astype(np.float32) / 255.0


def sweep(model, stacks, labels, scale, device, sizes, threshold=0.425):
    """The reference metric: greedy one-to-one match at 6 px, per threshold."""
    import numpy as np
    import torch
    from src.tiny_ball_net import f1, match, pick_peaks
    heats = {}
    for key, stack in stacks.items():
        x = torch.from_numpy(np.ascontiguousarray(stack.transpose(2, 0, 1)))[None].to(device)
        with torch.no_grad():
            heats[key] = model(x).cpu().numpy()[0, 0]
    rows = []
    for th in SWEEP:
        tp = fp = fn = 0
        errors = []
        for key, heat in heats.items():
            pred = pick_peaks(heat, th)
            truth = labels.get(round(key, 3), [])
            m = match(pred, truth, tol_px=TOL_PX, scale=scale)
            tp += m['matched']; fp += m['fp']; fn += m['fn']
            errors.extend(m['errors'])
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        rows.append(dict(threshold=th, tp=tp, fp=fp, fn=fn,
                         precision=round(precision, 3), recall=round(recall, 3),
                         f1=round(f1(precision, recall), 3),
                         localisation_px_median=(round(float(np.median(errors)), 2)
                                                 if errors else None),
                         localisation_px_p90=(round(float(np.percentile(errors, 90)), 2)
                                              if errors else None)))
    best = max(rows, key=lambda row: row['f1'])
    at = next(row for row in rows if row['threshold'] == threshold)
    return dict(layout_rows=rows, best=best, operating=at)


def main():
    import numpy as np
    import torch
    from src import tiny_ball_net as tn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', default='960x540')
    parser.add_argument('--checkpoint', default=str(ROOT / 'out/tiny_ball_probe/960x540-scratch.pt'))
    parser.add_argument('--device', default='auto')
    parser.add_argument('--threshold', type=float, default=tn.__dict__.get('BALL_THRESHOLD', 0.425))
    parser.add_argument('--output', default=str(ROOT / 'out/tiny_ball_probe/stack_ab.json'))
    args = parser.parse_args()

    size = tn.parse_size(args.size)
    labels = tn.load_labels()
    _train, held = tn.split_for_rounds(labels, freeze=True)
    held = sorted(held)
    device = tn.pick_device(args.device)
    model, saved = tn.load_checkpoint(args.checkpoint, size)
    model.to(device).eval()
    frames = decode_spans(tn.VIDEO, [tn.frame_index(tn.VIDEO, t) + k
                                     for t in held for k in (-2, -1, 0, 1)], size)
    layouts = {'centred': (-1, 0, 1), 'causal': (-2, -1, 0)}
    stacks = {'centred': {}, 'causal': {}}
    for t in held:
        index = tn.frame_index(tn.VIDEO, t)
        for name, offsets in layouts.items():
            stack = stack_of(frames, index, offsets, size)
            if stack is not None:
                stacks[name][round(t, 3)] = stack
    # warm the kernels before timing, then time the plain forward.  The result is
    # copied to host inside the timed region: a ROCm kernel launch is asynchronous,
    # so timing ``model(x)`` alone measures queueing (~1.5 ms), not the forward.
    probe = next(iter(stacks['causal'].values()))
    x = torch.from_numpy(np.ascontiguousarray(probe.transpose(2, 0, 1)))[None].to(device)
    with torch.no_grad():
        model(x).cpu()
        times = []
        for _ in range(20):
            started = time.perf_counter()
            model(x).cpu()
            times.append((time.perf_counter() - started) * 1000)
    result = {'checkpoint': args.checkpoint, 'saved_size': saved, 'size': list(size),
              'device': device, 'held_frames': len(held),
              'labelled_frames': {name: len(rows) for name, rows in stacks.items()},
              'threshold_used': args.threshold,
              'forward_ms_p50': round(float(np.median(times)), 2),
              'forward_ms_min': round(float(np.min(times)), 2)}
    for name in layouts:
        result[name] = sweep(model, stacks[name], labels, tn.NATIVE_WH[0] / size[0],
                             device, size, threshold=args.threshold)
    result['delta_f1_operating'] = round(result['causal']['operating']['f1']
                                         - result['centred']['operating']['f1'], 3)
    result['reading'] = (
        'centred reproduces the published operating point; the causal stack is what a '
        'live pipeline can feed. delta_f1_operating is the cost of that, measured on the '
        'same frames with the same code path.')
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=1))
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('centred', 'causal')}, indent=1))
    for name in layouts:
        op, best = result[name]['operating'], result[name]['best']
        print('%-8s @%.3f  F1 %.3f  P %.3f  R %.3f  tp/fp/fn %d/%d/%d  med %.2f px  p90 %.2f px'
              % (name, op['threshold'], op['f1'], op['precision'], op['recall'],
                 op['tp'], op['fp'], op['fn'], op['localisation_px_median'],
                 op['localisation_px_p90']))
        print('%-8s best-F1 %.3f at %.3f' % (name, best['f1'], best['threshold']))
    print('wrote', args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
