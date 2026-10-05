"""Held-out checks on the live ball stage: stack layout, and recall against speed.

The tiny ball net was trained on ``(t-1, t, t+1)`` (``src/tiny_ball_net.py``,
``STACK = 3``).  A live pipeline has only the past, so ``BallStage`` feeds it
``(t-2, t-1, t)`` instead - the same three frames, one frame earlier.  That is a
domain shift nobody had measured, and the held-out labels can measure it: same 47
held-out frames, same preprocessing code path as the stage, two stack layouts.

The centred column is also the stage's correctness check.  It is the layout the
published operating point was measured on (F1 0.927 / P 0.940 / R 0.914 at
threshold 0.425), so if it does not reproduce those numbers the stage's resize,
stack and decode differ from the probe's and the causal column is meaningless.

The second question is why dense tracks can still contain no sustained motion: a
ball crossing 300 px in half a second blurs over 10-20 px per frame, so the
detector may simply lose it.  ``causal_recall_by_speed`` bins every labelled
held-out ball by its own measured speed (nearest label in time, native px/s) and
reports what share of each bin the net finds.  A collapse in the fast bins is the
detector's recall, not the gate's thresholds.

Run: PYTHONPATH=. .venv/bin/python -B tests/ball_stack_ab.py
Writes out/tiny_ball_probe/stack_ab.json (out/ is gitignored).
"""
import argparse
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

SWEEP = [round(0.05 + 0.025 * i, 3) for i in range(38)]
TOL_PX = 6.0
#: the gate's own motion bar (src/shot_pot_gate.GateThresholds.motion_speed_px_s)
MOTION_BAR_PX_S = 40.0
SPEED_BINS = ((0.0, MOTION_BAR_PX_S), (MOTION_BAR_PX_S, 200.0), (200.0, 600.0),
              (600.0, float('inf')))


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


def stack_of(frames, index, offsets):
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


def heats_for(model, stacks, device):
    import numpy as np
    import torch
    out = {}
    for key, stack in stacks.items():
        x = torch.from_numpy(np.ascontiguousarray(stack.transpose(2, 0, 1)))[None].to(device)
        with torch.no_grad():
            out[key] = model(x).cpu().numpy()[0, 0]
    return out


def sweep(heats, labels, scale):
    """The reference metric: greedy one-to-one match at 6 px, per threshold."""
    import numpy as np
    from src.tiny_ball_net import f1, match, pick_peaks
    rows = []
    for th in SWEEP:
        tp = fp = fn = 0
        errors = []
        for key, heat in heats.items():
            m = match(pick_peaks(heat, th), labels.get(round(key, 3), []),
                      tol_px=TOL_PX, scale=scale)
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
    return rows


def greedy_pairs(first, second):
    """1:1 nearest-first assignment between two frames' labelled balls.

    A plain "nearest ball in the next frame" is the wrong estimator for speed: a
    ball that has moved 150 px has a *stationary neighbour* 20 px from where it was,
    so nearest-without-a-claim pins a moving ball to a still one and reports ~40 px/s.
    Assigning nearest pairs first and removing both sides fixes that: the racked
    pairs (0-3 px) are taken first, so the ball that actually moved is left with its
    own counterpart however far it went.
    """
    candidates = sorted(
        ((math.hypot(a['x'] - b['x'], a['y'] - b['y']), i, j)
         for i, a in enumerate(first) for j, b in enumerate(second)))
    used_i, used_j, pairs = set(), set(), []
    for distance, i, j in candidates:
        if i in used_i or j in used_j:
            continue
        used_i.add(i); used_j.add(j)
        pairs.append((i, j, distance))
    return pairs


def labelled_speeds(labels, times, span_s=2.0):
    """Each labelled ball's own speed, native px/s, from the nearest label in time.

    Balls with no 1:1 counterpart inside ``span_s`` (a ball that appeared or
    vanished, or a frame with no neighbour) are dropped rather than guessed, and the
    count of those is reported - they are not still balls, they are unmeasured ones.
    """
    ordered = sorted(times)
    index = {t: i for i, t in enumerate(ordered)}
    out = {}
    for t in ordered:
        row = labels.get(round(t, 3), [])
        speeds = [None] * len(row)
        for shift in (-1, 1):
            i = index[t] + shift
            if not 0 <= i < len(ordered):
                continue
            other = ordered[i]
            if abs(other - t) > span_s:
                continue
            dt = abs(other - t)
            for a, b, distance in greedy_pairs(row, labels.get(round(other, 3), [])):
                speed = distance / dt
                if speeds[a] is None or speed < speeds[a]:
                    speeds[a] = speed
        out[round(t, 3)] = speeds
    return out


def recall_by_speed(heats, labels, speeds, scale, threshold):
    """Of the labelled balls in each speed bin, what share did the net find?"""
    from src.tiny_ball_net import match_rows_native, pick_peaks
    bins = [dict(low=low, high=(None if high == float('inf') else high), n=0, found=0,
                 recall=None, example_px_s=None) for low, high in SPEED_BINS]
    for key, heat in heats.items():
        t = round(key, 3)
        truth = labels.get(t, [])
        if not truth:
            continue
        result = match_rows_native(pick_peaks(heat, threshold), truth, tol_px=TOL_PX, scale=scale)
        missed = {id(ball) for ball in result['missed']}
        for ball, speed in zip(truth, speeds.get(t, [None] * len(truth))):
            if speed is None:
                continue
            for entry in bins:
                if entry['low'] <= speed < (entry['high'] if entry['high'] is not None else float('inf')):
                    entry['n'] += 1
                    entry['found'] += int(id(ball) not in missed)
                    if entry['example_px_s'] is None:
                        entry['example_px_s'] = round(speed, 1)
                    break
    for entry in bins:
        entry['recall'] = round(entry['found'] / entry['n'], 3) if entry['n'] else None
    return bins


def stage_cost(frames, size, threshold=0.425, repeats=40):
    """What ``BallStage.process`` costs *besides* the forward pass.

    The real stage is used, with its ``heatmap`` replaced by zeros so no torch call
    happens: what remains is the stage's own work - resize to the net's size, the
    3-plane RGB stack, the ``/255`` cast and the peak search.  The envelope matrix
    shows the whole stage at 56-72 ms while a synced forward is 25 ms, and this says
    where the rest goes rather than leaving it as an inference.
    """
    import time as clock
    import cv2
    import numpy as np
    from annotator.pipeline_stages import BallStage, StageContext
    stage = BallStage(ROOT, threshold=threshold, size=size, model=object())
    stage.heatmap = lambda stack: np.zeros((size[1], size[0]), np.float32)
    order = sorted(frames)
    if len(order) < 3:
        return None
    work = [frames[index] for index in order]
    times = []
    for step in range(len(work)):
        context = StageContext({}, frame_number=step)
        started = clock.perf_counter()
        stage.process(work[step], context)
        times.append((clock.perf_counter() - started) * 1000)
    warm = times[2:]                      # the first two frames fill the 3-plane history
    return dict(repeats=len(warm), ms_p50=round(float(np.median(warm)), 2),
                ms_min=round(float(np.min(warm)), 2), ms_max=round(float(np.max(warm)), 2))


def reference_input(planes_bgr, size):
    """The **old** input path, verbatim, as the bit-identity reference.

    This is what ``BallStage.process`` did before the CHW-fill resident-tensor change:
    concatenate three BGR planes converted to RGB, cast to float32, divide by 255,
    transpose to CHW, make it contiguous.  It is kept here, not in the stage, because
    it is a measurement reference and not a code path anybody should use.
    """
    import cv2
    import numpy as np
    stack = np.concatenate([cv2.cvtColor(plane, cv2.COLOR_BGR2RGB) for plane in planes_bgr],
                           axis=2).astype(np.float32) / 255.0
    return np.ascontiguousarray(stack.transpose(2, 0, 1))


def sha256(array):
    import hashlib
    import numpy as np
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def bit_identity(frames, order, size, threshold=0.425, device='cpu'):
    """Element by element: does the new input path produce the *same* tensor?

    Real frames, the real ``BallStage`` fill, the real reference expression, compared
    as raw bytes (sha256) and element by element.  Nothing here is a metric: if one
    float differs, the change is wrong rather than merely different, and no timing
    number computed on top of it means anything.
    """
    import numpy as np
    from annotator.pipeline_stages import BallStage, StageContext

    stage = BallStage(ROOT, threshold=threshold, size=size, device=device, model=object())
    stage.heatmap = lambda tensor: np.zeros((size[1], size[0]), np.float32)
    seen, rows = [], []
    for index in order:
        frame = frames[index]
        tensor = stage.input_for(frame, StageContext({}, frame_number=index))
        got = tensor.cpu().numpy()[0]
        seen.append(frame)
        trio = seen[-stage.stack:]
        while len(trio) < stage.stack:
            trio.insert(0, trio[0])
        want = reference_input(trio, size)
        rows.append(dict(frame_number=index, shape=list(got.shape), dtype=str(got.dtype),
                         byte_identical=sha256(got) == sha256(want),
                         element_identical=bool(np.array_equal(got, want)),
                         max_abs_difference=float(np.abs(got.astype(np.float64)
                                                         - want.astype(np.float64)).max()),
                         sha256=sha256(got)))
    return dict(device=device, checked_frames=len(rows), stack=stage.stack,
                all_byte_identical=all(row['byte_identical'] for row in rows),
                all_element_identical=all(row['element_identical'] for row in rows),
                max_abs_difference=max(row['max_abs_difference'] for row in rows),
                frames=rows)


def input_path_cost(frames, order, size, device, repeats=40):
    """Old input path vs new, timed as a unit on the same frames and device.

    "Old" is the reference stack build plus the float32 tensor it had to copy; "new"
    is ``BallStage.input_for``.  Both include the host-to-device move their path
    needs, because that move is part of the thing under test.
    """
    import time as clock
    import numpy as np
    import torch
    from annotator.pipeline_stages import BallStage, StageContext

    stage = BallStage(ROOT, threshold=0.425, size=size, device=device, model=object())
    stage.heatmap = lambda tensor: np.zeros((size[1], size[0]), np.float32)
    trio = [frames[index] for index in order[-stage.stack:]]
    while len(trio) < stage.stack:
        trio.insert(0, trio[0])
    resolved = stage._device
    stage.input_for(frames[order[-1]], StageContext({}, frame_number=order[-1]))

    def timed(call, count):
        call()
        samples = []
        for _ in range(count):
            started = clock.perf_counter()
            call()
            samples.append((clock.perf_counter() - started) * 1000)
        return dict(n=len(samples), p50=round(float(np.median(samples)), 2),
                    p95=round(float(np.percentile(samples, 95)), 2),
                    min=round(float(np.min(samples)), 2))

    def old():
        return torch.from_numpy(reference_input(trio, size))[None].to(resolved)

    def new():
        return stage.input_for(frames[order[-1]], StageContext({}, frame_number=order[-1]))

    return dict(device=resolved, old=timed(old, repeats), new=timed(new, repeats))


def whole_process_cost(video, size, device, frame_index, threshold=0.425, repeats=25,
                       samples=6):
    """``BallStage.process`` end to end with the **real** model - the figure §7 said was missing.

    Every earlier timing measured a piece: the stage with the forward stubbed, or a
    forward whose input was built outside the timed region.  This times the call the
    pipeline actually makes, including whichever input path is current.
    """
    import time as clock
    import cv2
    import numpy as np
    from annotator.pipeline_stages import BallStage, StageContext

    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    frames = []
    for _ in range(samples):
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(cv2.resize(bgr, size, interpolation=cv2.INTER_AREA))
    cap.release()
    stage = BallStage(ROOT, threshold=threshold, size=size, device=device)
    stage.process(frames[0], StageContext({}, frame_number=0))     # weights + kernels
    times = []
    for step in range(1, repeats + 1):
        frame = frames[step % len(frames)]
        started = clock.perf_counter()
        stage.process(frame, StageContext({}, frame_number=step))
        times.append((clock.perf_counter() - started) * 1000)
    return dict(n=len(times), p50=round(float(np.median(times)), 2),
                p95=round(float(np.percentile(times, 95)), 2),
                min=round(float(np.min(times)), 2), device=stage._device,
                checkpoint=BallStage.checkpoint,
                note='whole process(): input build + forward + peak search, one call')


def main():
    import numpy as np
    import torch
    from src import tiny_ball_net as tn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', default='960x540')
    parser.add_argument('--checkpoint', default=str(ROOT / 'out/tiny_ball_probe/960x540-scratch.pt'))
    parser.add_argument('--device', default='auto')
    parser.add_argument('--threshold', type=float, default=0.425)
    parser.add_argument('--output', default=str(ROOT / 'out/tiny_ball_probe/stack_ab.json'))
    parser.add_argument('--no-sweep', action='store_true', help='skip the 38-point F1 sweep')
    parser.add_argument('--identity-frames', type=int, default=12,
                        help='real frames compared element by element against the old '
                             'input path (three ways: cpu, device, cadence 2)')
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
    stacks = {name: {} for name in layouts}
    for t in held:
        index = tn.frame_index(tn.VIDEO, t)
        for name, offsets in layouts.items():
            stack = stack_of(frames, index, offsets)
            if stack is not None:
                stacks[name][round(t, 3)] = stack
    heats = {name: heats_for(model, stacks[name], device) for name in layouts}

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
              'threshold_used': args.threshold,
              'labelled_frames': {name: len(rows) for name, rows in stacks.items()},
              'forward_ms_p50': round(float(np.median(times)), 2),
              'forward_ms_min': round(float(np.min(times)), 2)}
    if not args.no_sweep:
        for name in layouts:
            rows = sweep(heats[name], labels, tn.NATIVE_WH[0] / size[0])
            operating = next(row for row in rows if row['threshold'] == args.threshold)
            result[name] = dict(layout_rows=rows, operating=operating,
                                best=max(rows, key=lambda row: row['f1']))
        result['delta_f1_operating'] = round(result['causal']['operating']['f1']
                                             - result['centred']['operating']['f1'], 3)
    speeds = labelled_speeds(labels, sorted(labels))
    result['labelled_balls'] = sum(len(rows) for rows in speeds.values())
    result['labelled_balls_with_a_speed'] = sum(1 for rows in speeds.values()
                                                for speed in rows if speed is not None)
    result['causal_recall_by_speed'] = recall_by_speed(heats['causal'], labels, speeds,
                                                       tn.NATIVE_WH[0] / size[0],
                                                       args.threshold)
    # a short consecutive run of real frames, for the stage's own cost
    anchor = tn.frame_index(tn.VIDEO, held[len(held) // 2])
    run_frames = decode_spans(tn.VIDEO, list(range(anchor, anchor + 60)), size)
    result['stage_cost_ms'] = stage_cost(run_frames, size, threshold=args.threshold)

    # --- the input path: identity first, then cost.  Order is the point. ----------
    run_order = sorted(run_frames)[:args.identity_frames]
    result['bit_identity_cpu'] = bit_identity(run_frames, run_order, size,
                                              args.threshold, device='cpu')
    result['bit_identity_device'] = bit_identity(run_frames, run_order, size,
                                                 args.threshold, device=device)
    # cadence 2: the planes that land in the ring are not consecutive source frames
    result['bit_identity_cadence2'] = bit_identity(run_frames, run_order[::2], size,
                                                   args.threshold, device=device)
    result['input_path_ms'] = input_path_cost(run_frames, run_order, size, device)
    result['process_ms'] = whole_process_cost(tn.VIDEO, size, device, anchor,
                                              threshold=args.threshold)
    result['reading'] = (
        'centred reproduces the published operating point; the causal stack is what a '
        'live pipeline can feed. delta_f1_operating is the cost of that, measured on the '
        'same frames with the same code path. recall_by_speed says whether the net loses '
        'fast balls, which is the one detector-side explanation for a dense track with no '
        'sustained motion. bit_identity_* compare the input tensor the stage builds today '
        'with the one it built before the CHW-fill/resident-tensor change: byte for byte, '
        'on real frames, on the CPU path, on the device path and at cadence 2.')
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=1))
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('centred', 'causal')}, indent=1))
    for name in layouts:
        if args.no_sweep:
            continue
        op, best = result[name]['operating'], result[name]['best']
        print('%-8s @%.3f  F1 %.3f  P %.3f  R %.3f  tp/fp/fn %d/%d/%d  med %.2f px  p90 %.2f px'
              % (name, op['threshold'], op['f1'], op['precision'], op['recall'],
                 op['tp'], op['fp'], op['fn'], op['localisation_px_median'],
                 op['localisation_px_p90']))
        print('%-8s best-F1 %.3f at %.3f' % (name, best['f1'], best['threshold']))
    print('recall by labeled speed (causal, threshold %.3f):' % args.threshold)
    for entry in result['causal_recall_by_speed']:
        print('   %6.0f-%-6s px/s  n=%-4d found=%-4d recall=%s'
              % (entry['low'], '-' if entry['high'] is None else '%.0f' % entry['high'],
                 entry['n'], entry['found'], entry['recall']))
    print('stage cost without the forward:', json.dumps(result['stage_cost_ms']))
    for name in ('bit_identity_cpu', 'bit_identity_device', 'bit_identity_cadence2'):
        entry = result[name]
        print('%-24s frames=%-3d bytes_identical=%-5s elements_identical=%-5s max|diff|=%g'
              % (name, entry['checked_frames'], entry['all_byte_identical'],
                 entry['all_element_identical'], entry['max_abs_difference']))
    print('input path ms: old p50 %s / new p50 %s (device %s)'
          % (result['input_path_ms']['old']['p50'], result['input_path_ms']['new']['p50'],
             result['input_path_ms']['device']))
    print('whole process():', json.dumps(result['process_ms']))
    print('wrote', args.output)
    failed = [name for name in ('bit_identity_cpu', 'bit_identity_device',
                                'bit_identity_cadence2')
              if not result[name]['all_element_identical']]
    if failed:
        print('BIT-IDENTITY FAILED for: %s - the change is WRONG, not merely different'
              % ', '.join(failed))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
