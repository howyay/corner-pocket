"""Feasibility probe: can a small appearance net find these balls, fast enough?

The difference-based line is exhausted on this footage -- a single frame pair catches
24 % of known moving balls in the best channel, track-before-detect 8 %, and every
track it confirms sits on an occlusion.  This probe asks the next question with the
smallest possible experiment: train a tiny TrackNet-style heatmap regressor on the
SAM3 labels that already exist, and measure held-out F1, localisation error and
inference speed.

Epistemics, stated up front: **SAM3 is the teacher, not ground truth**.  A small
localisation error against it measures distillation fidelity, not accuracy.  The only
accuracy evidence here that does not come from the teacher is the rendered overlays
under ``out/tiny_ball_probe/overlays/``, which a human has to look at.

Nothing here writes to the queue, the gates or any production artifact.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

OUT = ROOT / "out" / "tiny_ball_probe"
CENSUS = ROOT / "out" / "scan30" / "sam3_census.json"
RESULTS = ROOT / "out" / "scan30" / "sam3_results.json"
VIDEO = ROOT / "data" / "vod_30min_260815.mp4"
CORNERS = ROOT / "out" / "scan30" / "corners.json"
QUAD_SEGMENTS = ROOT / "out" / "calib_vod30_segments.json"

_FRAME_CACHE: dict = {}       # resized frames, so an epoch does not re-decode the VOD
TRAIN_WH = (640, 360)           # training resolution: the ball is 9.4 px across here
NATIVE_WH = (1280, 720)
SIGMA_PX = 2.5                  # target Gaussian sigma at TRAIN_WH
STACK = 3                       # frames per sample: (t-1, t, t+1)
SPLIT_GAP_S = 5.0               # no two frames within this across train/held-out
TEACHER_MIN_SCORE = 0.62        # what the existing caches were filtered at
NEW_LABEL_MIN_SCORE = 0.30      # the probe records raw score down to here


# ------------------------------------------------------------------ labels ----

def load_labels(root=None) -> dict:
    """Every SAM3 label available, keyed by time, with its raw score kept.

    The two caches were written with the production score cut (0.62), so every stored
    score is at or above it -- that is the teacher's recall ceiling as delivered, and
    the probe reports it rather than silently re-filtering.
    """
    root = Path(root or ROOT)
    labels: dict[float, list] = {}
    for path, key in ((root / "out" / "scan30" / "sam3_census.json", "frames"),
                      (root / "out" / "scan30" / "sam3_results.json", None)):
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        frames = payload.get(key) if key else payload
        for t, balls in (frames or {}).items():
            rows = labels.setdefault(round(float(t), 3), [])
            for ball in balls:
                if ball.get("img"):
                    rows.append({"x": float(ball["img"][0]), "y": float(ball["img"][1]),
                                 "r": float(ball.get("r") or 0.0),
                                 "score": float(ball.get("score") or 0.0),
                                 "color": ball.get("color")})
    extra = root / "out" / "tiny_ball_probe" / "new_labels.json"
    if extra.exists():
        payload = json.loads(extra.read_text())
        for t, balls in payload.items():
            rows = labels.setdefault(round(float(t), 3), [])
            rows.extend(balls)
    return labels


def split_blocks(times: list, block_s: float = 30.0, held_every: int = 4,
                 gap_s: float = SPLIT_GAP_S) -> tuple:
    """Train/held-out by contiguous time block, with a real gap between them.

    The labels are sampled at ~1 Hz in bursts, so a per-frame gap rule (hold every
    frame 5 s away from a training frame) throws away most of the set: with 193 frames
    spanning 1800 s it left 18 training frames.  Splitting into contiguous ~30 s blocks
    and holding out every fourth one keeps the sets large *and* keeps the gap honest,
    because a held block is bounded by training blocks on both sides; frames within
    ``gap_s`` of a block boundary are dropped from both sides, so no held frame is
    within 5 s of any training frame.
    """
    times = sorted(times)
    if not times:
        return [], [], []
    blocks, current = [], [times[0]]
    for t in times[1:]:
        if t - current[-1] > 3.0 or t - current[0] >= block_s:
            blocks.append(current)
            current = [t]
        else:
            current.append(t)
    blocks.append(current)

    held, train, dropped = [], [], []
    for i, block in enumerate(blocks):
        boundary = (i == 0 or i == len(blocks) - 1
                    or any(abs(t - blocks[i - 1][-1]) < gap_s for t in block[:1])
                    or any(abs(t - blocks[i + 1][0]) < gap_s for t in block[-1:]))
        target = held if i % held_every == held_every - 1 else train
        for t in block:
            near_edge = (t - block[0] < gap_s) or (block[-1] - t < gap_s)
            if boundary and near_edge:
                dropped.append(t)
            else:
                target.append(t)
    # a floor on the gap: drop anything closer than gap_s across the split
    keep_train = [t for t in train if all(abs(t - h) >= gap_s for h in held)]
    dropped += [t for t in train if t not in set(keep_train)]
    return sorted(keep_train), sorted(held), sorted(dropped)


def tightest_gap(a: list, b: list) -> float:
    if not a or not b:
        return float("inf")
    return min(abs(x - y) for x in a for y in b)


# ------------------------------------------------------------------- frames ----

def load_frame(video, t: float) -> tuple:
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
    ok, bgr = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"no frame at t={t}")
    return bgr, int(cap.get(cv2.CAP_PROP_POS_FRAMES))


def frame_index(video, t: float, fps: float = 30.0003) -> int:
    return int(round(t * fps))


def read_frames(video, indices: list) -> dict:
    """The wanted frames: sequential read when dense, seeks when sparse.

    The label times are ~1 Hz over 1800 s, so a sequential sweep decodes the whole
    VOD for every epoch (~70 s of pure decode).  Seeking costs ~15 ms per frame, so
    past a 4x sparsity the seeks win by an order of magnitude.
    """
    want = sorted(set(int(i) for i in indices))
    if not want:
        return {}
    out = {i: _FRAME_CACHE[i] for i in want if i in _FRAME_CACHE}
    want = [i for i in want if i not in out]
    if not want:
        return out
    cap = cv2.VideoCapture(str(video))
    try:
        span = want[-1] - want[0] + 1
        if span <= 4 * len(want):
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, want[0]))
            index = max(0, want[0])
            last = want[-1]
            pending = set(want)
            while index <= last:
                ok, bgr = cap.read()
                if not ok:
                    break
                if index in pending:
                    out[index] = bgr
                    pending.discard(index)
                index += 1
        else:
            for index in want:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, bgr = cap.read()
                if ok:
                    out[index] = bgr
    finally:
        cap.release()
    for i, bgr in out.items():
        _FRAME_CACHE[i] = cv2.resize(bgr, TRAIN_WH, interpolation=cv2.INTER_AREA)
    return out


def stack_for(frames: dict, index: int) -> np.ndarray:
    """The 3-frame input stack, resized to the training size, as float 0..1."""
    planes = []
    for k in (-1, 0, 1):
        bgr = frames.get(index + k)
        if bgr is None:
            bgr = frames.get(index)
        if bgr is None:
            return None
        small = bgr if bgr.shape[1::-1] == TRAIN_WH else cv2.resize(
            bgr, TRAIN_WH, interpolation=cv2.INTER_AREA)
        planes.append(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    return np.concatenate(planes, axis=2).astype(np.float32) / 255.0      # H,W,9


def heatmap_target(bgr_hw: tuple, balls: list, sigma: float = SIGMA_PX) -> np.ndarray:
    """A Gaussian per labelled ball, at the training resolution."""
    h, w = bgr_hw
    target = np.zeros((h, w), np.float32)
    sx, sy = w / NATIVE_WH[0], h / NATIVE_WH[1]
    radius = int(3 * sigma)
    for ball in balls:
        cx, cy = ball["x"] * sx, ball["y"] * sy
        x0, x1 = max(0, int(cx) - radius), min(w, int(cx) + radius + 1)
        y0, y1 = max(0, int(cy) - radius), min(h, int(cy) + radius + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        xs = np.arange(x0, x1)[None, :] - cx
        ys = np.arange(y0, y1)[:, None] - cy
        patch = np.exp(-(xs ** 2 + ys ** 2) / (2 * sigma ** 2))
        np.maximum(target[y0:y1, x0:x1], patch, out=target[y0:y1, x0:x1])
    return target


# -------------------------------------------------------------------- model ----

def build_model(stack: int = STACK, base: int = 16):
    import torch
    import torch.nn as nn

    class TinyTrackNet(nn.Module):
        """3 frames in, one heatmap out.  Small on purpose: this is a probe."""

        def __init__(self):
            super().__init__()

            def block(cin, cout):
                return nn.Sequential(nn.Conv2d(cin, cout, 3, padding=1), nn.ReLU(),
                                     nn.Conv2d(cout, cout, 3, padding=1), nn.ReLU())

            self.e1 = block(stack * 3, base)
            self.e2 = block(base, base * 2)
            self.e3 = block(base * 2, base * 4)
            self.bottleneck = block(base * 4, base * 4)
            self.u3 = block(base * 8, base * 2)
            self.u2 = block(base * 4, base)
            self.head = nn.Conv2d(base * 2, 1, 1)
            self.pool = nn.MaxPool2d(2)
            self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)

        def forward(self, x):
            a = self.e1(x)                     # 1/1
            b = self.e2(self.pool(a))          # 1/2
            c = self.e3(self.pool(b))          # 1/4
            d = self.bottleneck(self.pool(c))  # 1/8
            def up_to(tensor, like):
                # interpolate to the skip's own size: an odd input height makes a
                # plain 2x upsample land one pixel off and the concat fails
                return torch.nn.functional.interpolate(
                    tensor, size=like.shape[-2:], mode="bilinear", align_corners=False)

            u = self.u3(torch.cat([up_to(d, c), c], 1))
            u = self.u2(torch.cat([up_to(u, b), b], 1))
            return self.head(torch.cat([up_to(u, a), a], 1))

    return TinyTrackNet()


def count_params(model) -> int:
    return int(sum(p.numel() for p in model.parameters()))


# ------------------------------------------------------------------ training --

def make_batch(frames: dict, times: list, labels: dict, augment=True, rng=None):
    import torch
    rng = rng or random.Random(0)
    xs, ys = [], []
    for t in times:
        index = frame_index(VIDEO, t)
        stack = stack_for(frames, index)
        if stack is None:
            continue
        target = heatmap_target(TRAIN_WH[::-1], labels.get(round(t, 3), []))
        if augment:
            if rng.random() < 0.5:                      # horizontal flip
                stack = stack[:, ::-1, :]
                target = target[:, ::-1]
            if rng.random() < 0.5:                      # vertical flip
                stack = stack[::-1, :, :]
                target = target[::-1, :]
            shift = rng.choice([-1, 0, 1]) * 8          # small translation
            if shift:
                stack = np.roll(stack, shift, axis=1)
                target = np.roll(target, shift, axis=1)
            gain = 1.0 + rng.uniform(-0.15, 0.15)       # brightness / colour jitter
            stack = np.clip(stack * gain, 0.0, 1.0)
        xs.append(stack.transpose(2, 0, 1))
        ys.append(target[None, :, :])
    if not xs:
        return None, None
    return (torch.from_numpy(np.stack(xs)), torch.from_numpy(np.stack(ys)))


def train(video, labels: dict, train_times: list, epochs: int = 40, batch: int = 4,
          lr: float = 2e-3, device: str = "auto", progress=print, seed: int = 0):
    import torch
    torch.manual_seed(seed)
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_model().to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    times = sorted(train_times)
    indices = [frame_index(VIDEO, t) for t in times]
    progress(f"device {device}; {len(times)} training frames; "
             f"{count_params(model)} parameters; {TRAIN_WH} input")
    started = time.time()
    history = []
    for epoch in range(epochs):
        frames = read_frames(video, [i + k for i in indices for k in (-1, 0, 1)])
        rng = random.Random(seed + epoch)
        order = times[:]
        rng.shuffle(order)
        total, seen = 0.0, 0
        for start in range(0, len(order), batch):
            chunk = order[start:start + batch]
            x, y = make_batch(frames, chunk, labels, augment=True, rng=rng)
            if x is None:
                continue
            x, y = x.to(device), y.to(device)
            optimiser.zero_grad()
            out = model(x)
            loss = loss_fn(out, y)
            loss.backward()
            optimiser.step()
            total += float(loss.item()) * x.shape[0]
            seen += x.shape[0]
        history.append(round(total / max(1, seen), 6))
        if epoch % 5 == 0 or epoch == epochs - 1:
            progress(f"  epoch {epoch + 1}/{epochs} loss {history[-1]:.5f} "
                     f"({time.time() - started:.0f}s)")
    return {"model": model, "device": device, "seconds": round(time.time() - started, 1),
            "loss": history, "params": count_params(model)}


def predict(model, video, times: list, device: str = "cpu", batch: int = 2):
    import torch
    model.eval()
    times = sorted(times)
    indices = [frame_index(VIDEO, t) for t in times]
    frames = read_frames(video, [i + k for i in indices for k in (-1, 0, 1)])
    outs = {}
    with torch.no_grad():
        for start in range(0, len(times), batch):
            chunk = times[start:start + batch]
            x, _y = make_batch(frames, chunk, {}, augment=False)
            if x is None:
                continue
            logits = model(x.to(device)).cpu().numpy()[:, 0]
            for t, heat in zip(chunk, logits):
                outs[round(t, 3)] = heat
    return outs


def pick_peaks(heat: np.ndarray, threshold: float, nms_px: float = 4.0) -> list:
    """Local maxima above ``threshold``, greedily thinned by distance."""
    kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(heat, kernel)
    peaks = np.argwhere((heat >= threshold) & (heat >= dilated - 1e-9))
    if peaks.size == 0:
        return []
    scores = heat[peaks[:, 0], peaks[:, 1]]
    order = np.argsort(-scores)
    kept = []
    for i in order:
        y, x = int(peaks[i, 0]), int(peaks[i, 1])
        if any((x - kx) ** 2 + (y - ky) ** 2 < nms_px ** 2 for kx, ky, _ in kept):
            continue
        kept.append((x, y, float(scores[i])))
    return kept


def match(pred: list, truth: list, tol_px: float, scale: float) -> dict:
    """Greedy one-to-one matching in native pixels."""
    used = set()
    errors = []
    matched = 0
    for (px, py, _s) in pred:
        best, best_d = None, None
        for i, ball in enumerate(truth):
            if i in used:
                continue
            d = math.hypot(px * scale - ball["x"], py * scale - ball["y"])
            if best_d is None or d < best_d:
                best, best_d = i, d
        if best is not None and best_d <= tol_px:
            used.add(best)
            matched += 1
            errors.append(best_d)
    return {"matched": matched, "errors": errors,
            "fp": len(pred) - matched, "fn": len(truth) - matched}


def f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


# ------------------------------------------------------------------- overlays --

def render_overlay(bgr, pred: list, truth: list, scale: float, threshold: float,
                   note: str = "") -> np.ndarray:
    out = bgr.copy()
    for ball in truth:
        cv2.circle(out, (int(ball["x"]), int(ball["y"])), int(max(6, ball["r"] * 2.2)),
                   (0, 255, 0), 1)
    for (x, y, s) in pred:
        cx, cy = int(x * scale), int(y * scale)
        cv2.circle(out, (cx, cy), 14, (0, 0, 255), 2)
        cv2.putText(out, f"{s:.2f}", (cx + 10, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 0, 255), 1, cv2.LINE_AA)
    cv2.rectangle(out, (0, 0), (out.shape[1], 26), (0, 0, 0), -1)
    cv2.putText(out, f"{note}  green = SAM3 label (teacher), red = student  "
                     f"threshold {threshold:.2f}", (8, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("describe", help="what labels exist and how they split")
    p.set_defaults(func=cmd_describe)
    p = sub.add_parser("train", help="train the probe")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--device", default="auto")
    p.set_defaults(func=cmd_train)
    p = sub.add_parser("evaluate", help="held-out F1, localisation, speed, overlays")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--device", default="auto")
    p.set_defaults(func=cmd_evaluate)

    args = ap.parse_args(argv)
    return args.func(args)


def cmd_describe(args) -> int:
    labels = load_labels()
    times = sorted(labels)
    train_t, held, dropped = split_blocks(times)
    instances = sum(len(v) for v in labels.values())
    print(json.dumps({
        "frames": len(times), "instances": instances,
        "train_frames": len(train_t), "held_frames": len(held),
        "dropped_for_gap": len(dropped),
        "tightest_gap_s": round(tightest_gap(train_t, held), 2),
        "held_times": held,
    }, indent=1))
    return 0


def cmd_train(args) -> int:
    labels = load_labels()
    train_t, held, _ = split_blocks(sorted(labels))
    import torch
    torch.set_num_threads(8)
    out = train(VIDEO, labels, train_t, epochs=args.epochs, device=args.device)
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({"state": out["model"].state_dict(), "train": train_t, "held": held},
               OUT / "tiny_ball_net.pt")
    print(json.dumps({"params": out["params"], "device": out["device"],
                      "seconds": out["seconds"], "epochs": args.epochs,
                      "final_loss": out["loss"][-1], "train_frames": len(train_t)},
                     indent=1))
    return 0


def cmd_evaluate(args) -> int:
    import torch
    torch.set_num_threads(8)
    labels = load_labels()
    train_t, held, _ = split_blocks(sorted(labels))
    device = "cuda" if (args.device == "auto" and torch.cuda.is_available()) else (
        "cpu" if args.device == "auto" else args.device)
    out = train(VIDEO, labels, train_t, epochs=args.epochs, device=device)
    model = out["model"]
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({"state": model.state_dict(), "train": train_t, "held": held},
               OUT / "tiny_ball_net.pt")
    heats = predict(model, VIDEO, held, device=device)
    scale = NATIVE_WH[0] / TRAIN_WH[0]

    thresholds = [round(0.05 + 0.025 * i, 3) for i in range(38)]
    sweep = []
    for threshold in thresholds:
        tp = fp = fn = 0
        errors = []
        for t, heat in heats.items():
            pred = [(x, y, s) for (x, y, s) in pick_peaks(heat, threshold)]
            truth = labels.get(round(t, 3), [])
            m = match(pred, truth, tol_px=6.0, scale=scale)
            tp += m["matched"]; fp += m["fp"]; fn += m["fn"]
            errors.extend(m["errors"])
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        sweep.append({"threshold": threshold, "tp": tp, "fp": fp, "fn": fn,
                      "precision": round(precision, 3), "recall": round(recall, 3),
                      "f1": round(f1(precision, recall), 3),
                      "localisation_px_median": (round(float(np.median(errors)), 2)
                                                 if errors else None),
                      "localisation_px_p90": (round(float(np.percentile(errors, 90)), 2)
                                              if errors else None)})
    best = max(sweep, key=lambda row: row["f1"])

    # inference speed at the chosen operating point
    speed_times = held[:12]
    started = time.time()
    _ = predict(model, VIDEO, speed_times, device=device)
    per_frame = (time.time() - started) / max(1, len(speed_times))
    on_cpu = None
    if device != "cpu":
        # the model has to move with the input, not just the input with the device
        import copy
        cpu_model = copy.deepcopy(model).to("cpu")
        started = time.time()
        _ = predict(cpu_model, VIDEO, speed_times[:6], device="cpu")
        on_cpu = (time.time() - started) / max(1, len(speed_times[:6]))

    overlay_dir = OUT / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, t in enumerate(held[:10]):
        index = frame_index(VIDEO, t)
        frames = read_frames(VIDEO, [index])
        bgr = frames.get(index)
        if bgr is None:
            continue
        pred = pick_peaks(heats[t], best["threshold"])
        image = render_overlay(bgr, pred, labels.get(round(t, 3), []), scale,
                               best["threshold"], note=f"t={t:.1f}s")
        path = overlay_dir / f"{i + 1:02d}_t{t:07.1f}s.png"
        cv2.imwrite(str(path), image)
        paths.append(str(path))

    payload = {
        "labels": {"frames": len(labels), "instances": sum(len(v) for v in labels.values()),
                   "train_frames": len(train_t), "held_frames": len(held),
                   "teacher_min_score": TEACHER_MIN_SCORE,
                   "tightest_gap_s": round(tightest_gap(train_t, held), 2)},
        "model": {"params": out["params"], "input": list(TRAIN_WH), "stack": STACK,
                  "device": out["device"], "seconds": out["seconds"],
                  "epochs": args.epochs, "final_loss": out["loss"][-1]},
        "held_out": {"sweep": sweep, "best": best,
                     "tol_px": 6.0, "scale_native_per_train_px": scale},
        "speed": {"ms_per_frame_sampled": round(per_frame * 1000, 1),
                  "ms_per_frame_cpu": round(on_cpu * 1000, 1) if on_cpu else None,
                  "vod_minutes": round(per_frame * 54206 / 60, 1)},
        "overlays": paths,
    }
    (OUT / "probe.json").write_text(json.dumps(payload, indent=1))
    print(json.dumps({k: payload[k] for k in ("labels", "model", "speed")}, indent=1))
    print(json.dumps(best, indent=1))
    print("overlays:", paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
