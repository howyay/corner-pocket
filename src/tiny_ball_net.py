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
under ``out/tiny_ball_probe/overlays/`` (probe) and ``overlays2/`` (production pass),
which a human has to look at.

Nothing here writes to the queue, the gates or any production artifact.

**The production pass** (``rounds``) scales the probe along the two axes the probe's own
section 6 named: resolution (640x360 halves the ball to 9.4 px, and the 64 held-out
misses were small/rail-adjacent balls at 6.9 px median radius) and data volume (the
193 teacher frames come from ``out/tiny_ball_probe/new_labels.json`` when the labeller
has written them).  Each round reports held-out F1 and localisation, and the operating
point is chosen as the best F1 **subject to p90 localisation <= 4 px**, not the best F1
alone -- a detector that finds balls 8 px away from where they are is not a detector.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.datasets import media_path  # noqa: E402

OUT = ROOT / "out" / "tiny_ball_probe"
CENSUS = ROOT / "out" / "scan30" / "sam3_census.json"
RESULTS = ROOT / "out" / "scan30" / "sam3_results.json"
VIDEO = media_path(ROOT, "vod30")
CORNERS = ROOT / "out" / "scan30" / "corners.json"
QUAD_SEGMENTS = ROOT / "out" / "calib_vod30_segments.json"

_FRAME_CACHE: dict = {}       # (size, index) -> resized frame, so an epoch re-decodes nothing
TRAIN_WH = (640, 360)           # probe resolution: the ball is 9.4 px across here
PROD_WH = (960, 540)            # production minimum: 3x the probe's pixels, ball 14.2 px
NATIVE_WH = (1280, 720)
SIGMA_PX = 2.5                  # target Gaussian sigma at TRAIN_WH
STACK = 3                       # frames per sample: (t-1, t, t+1)
SPLIT_GAP_S = 5.0               # no two frames within this across train/held-out
TEACHER_MIN_SCORE = 0.62        # what the existing caches were filtered at
NEW_LABEL_MIN_SCORE = 0.30      # the labeller records raw teacher score down to here
LOC_BAR_PX = 4.0                # p90 localisation bar for the production operating point
F1_BAR = 0.90                   # held-out F1 bar
FPS_BAR = 30.0                  # near-real-time bar: <= 33.3 ms/frame end to end

RESOLUTIONS = {"640x360": (640, 360), "960x540": (960, 540), "1280x720": (1280, 720)}


def parse_size(text: str) -> tuple:
    """``960x540`` -> ``(960, 540)``; a bare name is looked up in ``RESOLUTIONS``."""
    if text in RESOLUTIONS:
        return RESOLUTIONS[text]
    width, _, height = text.lower().partition("x")
    return (int(width), int(height))


def sigma_for(size: tuple) -> float:
    """The target sigma at ``size``, scaled so the Gaussian keeps the ball's shape.

    The probe fixed sigma at 2.5 px for a 640-wide frame, where the ball is 9.4 px
    across; a fixed sigma at 960x540 would make the target narrower than the ball and
    the resolution gain would not reach the target.
    """
    return round(SIGMA_PX * size[0] / TRAIN_WH[0], 4)


# ------------------------------------------------------------------ labels ----

def load_labels(root=None, extra=()) -> dict:
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
                                 "color": ball.get("color"), "source": "teacher-cache"})
    for path in (root / "out" / "tiny_ball_probe" / "new_labels.json", *extra):
        path = Path(path)
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        for t, balls in payload.items():
            rows = labels.setdefault(round(float(t), 3), [])
            rows.extend(dict(ball, source=ball.get("source", "teacher-new"))
                        for ball in balls)
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


FROZEN_HELD = OUT / "held_frozen.json"


def split_for_rounds(labels: dict, freeze: bool = True) -> tuple:
    """Train/held-out with the held-out set **frozen** the first time it is computed.

    Adding labels must not move the validation set.  ``split_blocks`` groups labels
    into contiguous blocks, so a few hundred new labels in the gaps merge blocks and
    re-index every block after them -- round 2 would then be scored on a different 40
    frames than round 1 and the "curve" would be two unrelated measurements.  The
    first call writes ``out/tiny_ball_probe/held_frozen.json``; every later call uses
    it, and training frames are everything at least ``SPLIT_GAP_S`` away from it.
    """
    times = sorted(labels)
    if FROZEN_HELD.exists():
        held = sorted(round(float(t), 3) for t in
                      json.loads(FROZEN_HELD.read_text())["held"])
    else:
        _train, held, _dropped = split_blocks(times)
        if freeze:
            FROZEN_HELD.parent.mkdir(parents=True, exist_ok=True)
            FROZEN_HELD.write_text(json.dumps(
                {"held": held, "source_frames": len(times),
                 "note": "frozen so that later label additions cannot move the "
                         "held-out set between training rounds"}, indent=1))
    held_set = set(held)
    train_t = [t for t in times if t not in held_set
               and all(abs(t - h) >= SPLIT_GAP_S for h in held)]
    return sorted(train_t), held


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


def read_frames(video, indices: list, size: tuple = TRAIN_WH) -> dict:
    """The wanted frames, resized to ``size``: sequential read when dense, seeks when sparse.

    The label times are ~1 Hz over 1800 s, so a sequential sweep decodes the whole
    VOD for every epoch (~70 s of pure decode).  Seeking costs ~15 ms per frame, so
    past a 4x sparsity the seeks win by an order of magnitude.

    The cache is keyed by ``(size, index)``: a 960x540 round must not be served the
    640x360 frames a previous round left behind, or every resolution measures the same
    picture at the same size and the round-to-round curve is a lie.
    """
    want = sorted(set(int(i) for i in indices))
    if not want:
        return {}
    size = tuple(size)
    key = lambda i: (size, i)
    out = {i: _FRAME_CACHE[key(i)] for i in want if key(i) in _FRAME_CACHE}
    fresh = [i for i in want if i not in out]
    if not fresh:
        return out
    cap = cv2.VideoCapture(str(video))
    raw = {}
    try:
        span = fresh[-1] - fresh[0] + 1
        # a seek into this 690 MB h264 costs ~70 ms, a sequential decode ~4 ms, so the
        # crossover is far wider than the 4x this started at: a 1-in-3 scan of a 60 s
        # window was 5x slower on the seek path
        if span <= 8 * len(fresh):
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, fresh[0]))
            index = max(0, fresh[0])
            last = fresh[-1]
            pending = set(fresh)
            while index <= last:
                ok, bgr = cap.read()
                if not ok:
                    break
                if index in pending:
                    raw[index] = bgr
                    pending.discard(index)
                index += 1
        else:
            for index in fresh:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, bgr = cap.read()
                if ok:
                    raw[index] = bgr
    finally:
        cap.release()
    for i, bgr in raw.items():
        _FRAME_CACHE[key(i)] = cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
        out[i] = bgr                      # still native size: stack_for fits it
    return out


def stack_for(frames: dict, index: int, size: tuple = TRAIN_WH) -> np.ndarray:
    """The 3-frame input stack, resized to ``size``, as float 0..1.

    ``read_frames`` has already resized every frame it was asked for into
    ``_FRAME_CACHE``, so the cache is consulted first: resizing the native frame again
    costs ~4 ms of INTER_AREA per plane, and at three planes per sample that was
    ~12 ms/frame of the measured end-to-end number doing work that was already done.
    """
    size = tuple(size)
    planes = []
    for k in (-1, 0, 1):
        small = _FRAME_CACHE.get((size, index + k))
        if small is None:
            bgr = frames.get(index + k)
            if bgr is None:
                bgr = frames.get(index)
            if bgr is None:
                return None
            small = bgr if tuple(bgr.shape[1::-1]) == size else cv2.resize(
                bgr, size, interpolation=cv2.INTER_AREA)
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

def make_batch(frames: dict, times: list, labels: dict, augment=True, rng=None,
               size: tuple = TRAIN_WH, sigma: float | None = None):
    import torch
    rng = rng or random.Random(0)
    size = tuple(size)
    sigma = sigma if sigma is not None else sigma_for(size)
    xs, ys = [], []
    scale = size[0] / TRAIN_WH[0]
    for t in times:
        index = frame_index(VIDEO, t)
        stack = stack_for(frames, index, size=size)
        if stack is None:
            continue
        target = heatmap_target((size[1], size[0]), labels.get(round(t, 3), []),
                                sigma=sigma)
        if augment:
            if rng.random() < 0.5:                      # horizontal flip
                stack = stack[:, ::-1, :]
                target = target[:, ::-1]
            if rng.random() < 0.5:                      # vertical flip
                stack = stack[::-1, :, :]
                target = target[::-1, :]
            # translation scales with the frame: 8 px of a 640-wide frame is 16 px at
            # 1280, and a fixed 8 px shift at native resolution is a different
            # augmentation than the one the probe validated
            shift = rng.choice([-1, 0, 1]) * int(round(8 * scale))
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
          lr: float = 2e-3, device: str = "auto", progress=print, seed: int = 0,
          size: tuple = TRAIN_WH, base: int = 16, init: dict | None = None):
    import torch
    torch.manual_seed(seed)
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    size = tuple(size)
    model = build_model(base=base).to(device)
    if init:
        model.load_state_dict(init)
    optimiser = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    times = sorted(train_times)
    indices = [frame_index(VIDEO, t) for t in times]
    progress(f"device {device}; {len(times)} training frames; "
             f"{count_params(model)} parameters; {size} input; sigma {sigma_for(size)}")
    started = time.time()
    history = []
    for epoch in range(epochs):
        frames = read_frames(video, [i + k for i in indices for k in (-1, 0, 1)], size=size)
        rng = random.Random(seed + epoch)
        order = times[:]
        rng.shuffle(order)
        total, seen = 0.0, 0
        for start in range(0, len(order), batch):
            chunk = order[start:start + batch]
            x, y = make_batch(frames, chunk, labels, augment=True, rng=rng, size=size)
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
            "loss": history, "params": count_params(model), "size": list(size),
            "sigma": sigma_for(size)}


def predict(model, video, times: list, device: str = "cpu", batch: int = 2,
            size: tuple = TRAIN_WH, decode: bool = True):
    """Heatmaps for ``times``.  ``decode=False`` skips the frame read (speed probes)."""
    import torch
    size = tuple(size)
    model.eval()
    times = sorted(times)
    indices = [frame_index(VIDEO, t) for t in times]
    frames = read_frames(video, [i + k for i in indices for k in (-1, 0, 1)],
                         size=size) if decode else None
    outs = {}
    with torch.no_grad():
        for start in range(0, len(times), batch):
            chunk = times[start:start + batch]
            if decode:
                x, _y = make_batch(frames, chunk, {}, augment=False, size=size)
            else:
                # CHW, not HWC: the frame-backed path transposes in make_batch
                x = torch.from_numpy(np.stack([
                    np.zeros((STACK * 3, size[1], size[0]), np.float32) for _ in chunk]))
            if x is None:
                continue
            logits = model(x.to(device)).cpu().numpy()[:, 0]
            for t, heat in zip(chunk, logits):
                outs[round(t, 3)] = heat
    return outs


def _subpixel(heat: np.ndarray, x: int, y: int) -> tuple:
    """Quadratic peak refinement: the heatmap peak sits between pixels.

    At 960x540 one train pixel is 1.33 native pixels, so the integer argmax alone
    cannot clear a 4 px p90 localisation bar; the 3-point parabolic fit on each axis
    costs nothing and removes that quantisation floor.
    """
    h, w = heat.shape
    dx = dy = 0.0
    if 1 <= x < w - 1:
        left, centre, right = (float(heat[y, x - 1]), float(heat[y, x]),
                               float(heat[y, x + 1]))
        denom = 2.0 * centre - left - right
        if denom > 1e-9:
            dx = max(-0.5, min(0.5, 0.5 * (right - left) / denom))
    if 1 <= y < h - 1:
        up, centre, down = (float(heat[y - 1, x]), float(heat[y, x]),
                            float(heat[y + 1, x]))
        denom = 2.0 * centre - up - down
        if denom > 1e-9:
            dy = max(-0.5, min(0.5, 0.5 * (down - up) / denom))
    return x + dx, y + dy


def pick_peaks(heat: np.ndarray, threshold: float, nms_px: float = 4.0,
               subpixel: bool = True) -> list:
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
        if subpixel:
            fx, fy = _subpixel(heat, x, y)
        else:
            fx, fy = float(x), float(y)
        kept.append((fx, fy, float(scores[i])))
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


# ------------------------------------------------------- evaluation & rounds --

def operating_point(sweep: list, loc_bar: float = LOC_BAR_PX) -> tuple:
    """Best F1 overall, and best F1 whose p90 localisation clears the bar.

    The production point is the second one: a detector that finds balls 8 px from where
    they are satisfies neither a player nor a trajectory.  When nothing clears the bar
    the honest answer is the best F1 plus the localisation it actually has, so both are
    returned and both are reported.
    """
    if not sweep:
        return None, None
    best_f1 = max(sweep, key=lambda row: row["f1"])
    within = [row for row in sweep
              if row.get("localisation_px_p90") is not None
              and row["localisation_px_p90"] <= loc_bar]
    return (max(within, key=lambda row: row["f1"]) if within else None), best_f1


def evaluate_held(model, labels: dict, held: list, size: tuple, device: str,
                  tol_px: float = 6.0, batch: int = 2) -> dict:
    """The held-out sweep, the operating points and the heatmaps behind them."""
    heats = predict(model, VIDEO, held, device=device, size=size, batch=batch)
    scale = NATIVE_WH[0] / size[0]
    thresholds = [round(0.05 + 0.025 * i, 3) for i in range(38)]
    sweep = []
    for threshold in thresholds:
        tp = fp = fn = 0
        errors = []
        for t, heat in heats.items():
            pred = [(x, y, s) for (x, y, s) in pick_peaks(heat, threshold)]
            truth = labels.get(round(t, 3), [])
            m = match(pred, truth, tol_px=tol_px, scale=scale)
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
    chosen, best_f1 = operating_point(sweep)
    return {"sweep": sweep, "best_f1": best_f1, "operating": chosen or best_f1,
            "tol_px": tol_px, "scale_native_per_train_px": scale, "heats": heats}


# --------------------------------------------------------------- disagreement --

def cloth_edge_distance(quad, x: float, y: float) -> float:
    """Distance from ``(x, y)`` to the reference quad's boundary; negative outside."""
    if quad is None:
        return float("nan")
    return float(cv2.pointPolygonTest(np.asarray(quad, np.float32), (float(x), float(y)), True))


def disagreement(heats: dict, labels: dict, held: list, size: tuple, threshold: float,
                 tol_px: float = 6.0, quad=None, edge_px: float = 25.0) -> dict:
    """Who disagrees with whom, and which side looks wrong.

    The teacher is not ground truth, so this cannot settle anything by itself; what it
    can do is say *which way* each error leans.  A missed label with a high teacher
    score and a normal radius is a student error; a missed label the teacher itself
    scored 0.63 is closer to a teacher guess.  A student detection near the rail with
    no label is where the teacher's known recall weakness lives.
    """
    scale = NATIVE_WH[0] / size[0]
    fn_rows, fp_rows = [], []
    for t in sorted(heats):
        heat = heats[t]
        pred = pick_peaks(heat, threshold)
        truth = labels.get(round(t, 3), [])
        result = match_rows_native(pred, truth, tol_px, scale)
        for ball in result["missed"]:
            fn_rows.append({"t": t, "score": ball.get("score"), "r": ball.get("r"),
                            "edge_px": cloth_edge_distance(quad, ball["x"], ball["y"])})
        for (px, py, score) in result["extra"]:
            x, y = px * scale, py * scale
            fp_rows.append({"t": t, "score": round(float(score), 3), "x": round(x, 1),
                            "y": round(y, 1), "edge_px": cloth_edge_distance(quad, x, y)})
    scores = [row["score"] for row in fn_rows if row["score"] is not None]
    radii = [row["r"] for row in fn_rows if row.get("r") is not None]
    edges = [row["edge_px"] for row in fn_rows if row["edge_px"] == row["edge_px"]]
    fp_edges = [row["edge_px"] for row in fp_rows if row["edge_px"] == row["edge_px"]]
    median = lambda values: round(float(np.median(values)), 2) if values else None
    return {
        "threshold": threshold,
        "fn": len(fn_rows),
        "fn_teacher_score_median": median(scores),
        "fn_teacher_score_min": round(min(scores), 3) if scores else None,
        "fn_radius_median_px": median(radii),
        "fn_near_cloth_edge": sum(1 for row in edges if abs(row) <= edge_px),
        "fn_edge_distance_median_px": median([abs(row) for row in edges]),
        "fp": len(fp_rows),
        "fp_inside_cloth": sum(1 for row in fp_edges if row > 0),
        "fp_near_cloth_edge": sum(1 for row in fp_edges if abs(row) <= edge_px),
        "fp_peak_score_median": median([row["score"] for row in fp_rows]),
        "reading": reading_for(len(fn_rows), scores, fn_rows, fp_rows, edges),
    }


def reading_for(fn: int, scores: list, fn_rows: list, fp_rows: list, edges: list) -> str:
    if not fn and not fp_rows:
        return "no disagreement at this operating point"
    confident = sum(1 for s in scores if s is not None and s >= 0.8)
    near_edge = sum(1 for e in edges if abs(e) <= 25.0)
    return (f"{fn} missed labels, {confident} of them the teacher itself scored >=0.8 "
            f"(student-side recall error), {near_edge} within 25 px of the cloth edge; "
            f"{len(fp_rows)} detections with no label, which is either a student false "
            f"positive or a teacher miss and needs eyes to settle")


def match_rows_native(pred: list, truth: list, tol_px: float, scale: float) -> dict:
    """``match`` plus the two lists of leftovers, for the disagreement report."""
    used = set()
    matched = 0
    missed, extra = [], []
    for (px, py, score) in pred:
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
        else:
            extra.append((px, py, score))
    missed = [ball for i, ball in enumerate(truth) if i not in used]
    return {"matched": matched, "missed": missed, "extra": extra}


def reference_quad():
    try:
        from src.sam3_ball_cache import reference_quad as load_quad
        return load_quad()
    except Exception:
        return None


# ----------------------------------------------------------------------- CLI --

def load_checkpoint(path, size: tuple):
    import torch
    payload = torch.load(str(path), map_location="cpu", weights_only=True)
    model = build_model()
    model.load_state_dict(payload["state"])
    return model, payload.get("size") or list(size)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("describe", help="what labels exist and how they split")
    p.set_defaults(func=cmd_describe)

    p = sub.add_parser("train", help="train at one resolution")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--size", default="960x540")
    p.add_argument("--device", default="auto")
    p.add_argument("--bitmap", default=str(OUT / "tiny_ball_net.pt"))
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("evaluate", help="held-out F1, localisation, speed, overlays")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--size", default="960x540")
    p.add_argument("--device", default="auto")
    p.add_argument("--overlay-count", type=int, default=20)
    p.add_argument("--overlay-dir", default=str(OUT / "overlays2"))
    p.add_argument("--probe-out", default=str(OUT / "probe.json"))
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("rounds", help="the scaling curve: a train+evaluate round per plan entry")
    p.add_argument("--plan", default="960x540:20,1280x720:20,960x540:8",
                   help="comma-separated WxH:epochs[:warm] entries; 'warm' continues "
                        "the previous round's weights (same resolution only)")
    p.add_argument("--device", default="auto")
    p.add_argument("--out", default=str(OUT / "rounds.json"))
    p.add_argument("--overlay-count", type=int, default=20)
    p.add_argument("--max-train", type=int, default=0,
                   help="cap the training frames (evenly spaced in time).  The frame "
                        "cache holds 3 uint8 frames per training frame, so 421 frames at "
                        "960x540 is ~2 GB of host RAM and this box OOM-killed the round "
                        "that used it; 0 means no cap")
    p.add_argument("--extra-labels", default="",
                   help="comma-separated extra label files (e.g. the student's "
                        "pre-labels); they are added to the teacher's, never mixed "
                        "silently -- every row carries its source")
    p.set_defaults(func=cmd_rounds)

    p = sub.add_parser("report", help="held-out curve + overlays + disagreement from a "
                                     "saved checkpoint (no retraining)")
    p.add_argument("--bitmap", default=str(OUT / "960x540-scratch.pt"))
    p.add_argument("--size", default="960x540")
    p.add_argument("--device", default="auto")
    p.add_argument("--overlay-count", type=int, default=20)
    p.add_argument("--dir", dest="overlay_dir", default=str(OUT / "overlays2"))
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("overlays", help="re-render overlays from a saved checkpoint")
    p.add_argument("--bitmap", default=str(OUT / "tiny_ball_net.pt"))
    p.add_argument("--size", default="960x540")
    p.add_argument("--threshold", type=float, default=0.1)
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--dir", dest="overlay_dir", default=str(OUT / "overlays2"))
    p.set_defaults(func=cmd_overlays)

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


def pick_device(requested: str) -> str:
    import torch
    if requested != "auto":
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


def cmd_train(args) -> int:
    import torch
    torch.set_num_threads(8)
    size = parse_size(args.size)
    labels = load_labels()
    train_t, held = split_for_rounds(labels)
    out = train(VIDEO, labels, train_t, epochs=args.epochs, device=pick_device(args.device),
                size=size)
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({"state": out["model"].state_dict(), "train": train_t, "held": held,
                "size": list(size), "sigma": out["sigma"]}, args.bitmap)
    print(json.dumps({"params": out["params"], "device": out["device"],
                      "size": out["size"], "sigma": out["sigma"],
                      "seconds": out["seconds"], "epochs": args.epochs,
                      "final_loss": out["loss"][-1], "train_frames": len(train_t)},
                     indent=1))
    return 0


def render_overlays(model, labels, held, size, device, threshold, count, directory,
                    tag: str) -> list:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    scale = NATIVE_WH[0] / size[0]
    paths = []
    chosen = held[:count]
    heats = predict(model, VIDEO, chosen, device=device, size=size, batch=2)
    for i, t in enumerate(chosen):
        if t not in heats:
            continue
        index = frame_index(VIDEO, t)
        bgr = read_frames(VIDEO, [index], size=size).get(index)
        if bgr is None:
            continue
        pred = pick_peaks(heats[t], threshold)
        image = render_overlay(bgr, pred, labels.get(round(t, 3), []), scale, threshold,
                               note=f"{tag} t={t:.1f}s")
        path = directory / f"{i + 1:02d}_t{t:07.1f}s.png"
        cv2.imwrite(str(path), image)
        paths.append(str(path))
    return paths


def cmd_evaluate(args) -> int:
    import torch
    torch.set_num_threads(8)
    size = parse_size(args.size)
    device = pick_device(args.device)
    labels = load_labels()
    train_t, held = split_for_rounds(labels)
    out = train(VIDEO, labels, train_t, epochs=args.epochs, device=device, size=size)
    model = out["model"]
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({"state": model.state_dict(), "train": train_t, "held": held,
                "size": list(size), "sigma": out["sigma"]}, OUT / "tiny_ball_net.pt")

    result = evaluate_held(model, labels, held, size, device)
    operating = result["operating"]
    heat = result.pop("heats")

    speed_times = held[:12]
    started = time.time()
    _ = predict(model, VIDEO, speed_times, device=device, size=size)
    per_frame = (time.time() - started) / max(1, len(speed_times))
    # and the model alone, so a decode-bound number cannot masquerade as an inference cost
    started = time.time()
    _ = predict(model, VIDEO, speed_times, device=device, size=size, decode=False)
    inference_only = (time.time() - started) / max(1, len(speed_times))

    paths = render_overlays(model, labels, held, size, device, operating["threshold"],
                            args.overlay_count, args.overlay_dir,
                            tag=f"{size[0]}x{size[1]}")
    report = disagreement(heat, labels, held, size, operating["threshold"],
                          quad=reference_quad())

    payload = {
        "labels": {"frames": len(labels), "instances": sum(len(v) for v in labels.values()),
                   "train_frames": len(train_t), "held_frames": len(held),
                   "teacher_min_score": TEACHER_MIN_SCORE,
                   "tightest_gap_s": round(tightest_gap(train_t, held), 2)},
        "model": {"params": out["params"], "input": list(size), "stack": STACK,
                  "sigma": out["sigma"], "device": out["device"],
                  "seconds": out["seconds"], "epochs": args.epochs,
                  "final_loss": out["loss"][-1]},
        "held_out": result,
        "speed": {"ms_per_frame_end_to_end": round(per_frame * 1000, 1),
                  "ms_per_frame_inference_only": round(inference_only * 1000, 1),
                  "fps_end_to_end": round(1.0 / max(1e-9, per_frame), 1),
                  "vod_minutes": round(per_frame * 54206 / 60, 1)},
        "disagreement": report,
        "overlays": paths,
        "bars": {"f1": F1_BAR, "p90_localisation_px": LOC_BAR_PX, "fps": FPS_BAR,
                 "f1_met": operating["f1"] >= F1_BAR,
                 "p90_met": (operating["localisation_px_p90"] or 99) <= LOC_BAR_PX,
                 "fps_met": (1.0 / max(1e-9, per_frame)) >= FPS_BAR},
    }
    Path(args.probe_out).write_text(json.dumps(payload, indent=1))
    print(json.dumps({k: payload[k] for k in ("labels", "model", "speed", "bars")}, indent=1))
    print(json.dumps(operating, indent=1))
    print(json.dumps(report, indent=1))
    print("overlays:", len(paths), "in", args.overlay_dir)
    return 0


def cmd_rounds(args) -> int:
    import torch
    torch.set_num_threads(8)
    device = pick_device(args.device)
    extra = [Path(part.strip()) for part in args.extra_labels.split(",") if part.strip()]
    labels = load_labels(extra=extra)
    train_t, held = split_for_rounds(labels)
    if args.max_train and len(train_t) > args.max_train:
        step = len(train_t) / args.max_train
        train_t = [train_t[min(len(train_t) - 1, int(round(i * step)))]
                   for i in range(args.max_train)]
        train_t = sorted(set(train_t))
    sources = {}
    for balls in labels.values():
        for ball in balls:
            sources[ball.get("source", "teacher-cache")] = sources.get(
                ball.get("source", "teacher-cache"), 0) + 1
    print(json.dumps({"label_sources": sources, "frames": len(labels),
                      "train_frames": len(train_t), "held_frames": len(held)}), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    curve, previous = [], None
    for entry in args.plan.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        size = parse_size(parts[0])
        epochs = int(parts[1]) if len(parts) > 1 else 20
        warm = len(parts) > 2 and parts[2].strip().lower() in ("warm", "1", "true")
        init = None
        if warm:
            if previous is None:
                raise SystemExit("a warm round needs a previous round")
            if tuple(previous["size"]) != tuple(size):
                raise SystemExit("cannot warm-start across resolutions: the head's "
                                 "resolution changed")
            init = previous["state"]
        name = f"{size[0]}x{size[1]}-{'warm' if warm else 'scratch'}"
        print(f"=== round {name} epochs {epochs} ===", flush=True)
        out = train(VIDEO, labels, train_t, epochs=epochs, device=device, size=size,
                    init=init)
        model = out["model"]
        result = evaluate_held(model, labels, held, size, device)
        operating = result["operating"]
        best_f1 = result["best_f1"]
        result.pop("heats")
        speed_times = held[:12]
        end_to_end = inference_only = None
        try:
            started = time.time()
            _ = predict(model, VIDEO, speed_times, device=device, size=size)
            end_to_end = (time.time() - started) / max(1, len(speed_times))
            started = time.time()
            _ = predict(model, VIDEO, speed_times, device=device, size=size, decode=False)
            inference_only = (time.time() - started) / max(1, len(speed_times))
        except Exception as exc:                      # never lose a trained round to a stopwatch
            print(f"  speed measurement failed: {type(exc).__name__}: {exc}", flush=True)
        row = {"round": name, "size": list(size), "epochs": epochs, "warm": warm,
               "labels": {"frames": len(labels), "instances":
                          sum(len(v) for v in labels.values()),
                          "train_frames": len(train_t), "held_frames": len(held)},
               "params": out["params"], "train_seconds": out["seconds"],
               "final_loss": out["loss"][-1],
               "f1": operating["f1"], "precision": operating["precision"],
               "recall": operating["recall"], "threshold": operating["threshold"],
               "localisation_px_median": operating["localisation_px_median"],
               "localisation_px_p90": operating["localisation_px_p90"],
               "best_f1_any_threshold": best_f1["f1"],
               "best_f1_threshold": best_f1["threshold"],
               "best_f1_p90": best_f1["localisation_px_p90"],
               "ms_per_frame_end_to_end": (round(end_to_end * 1000, 1)
                                           if end_to_end else None),
               "ms_per_frame_inference_only": (round(inference_only * 1000, 1)
                                               if inference_only else None),
               "fps_end_to_end": round(1.0 / end_to_end, 1) if end_to_end else None,
               "f1_met": operating["f1"] >= F1_BAR,
               "p90_met": (operating["localisation_px_p90"] or 99) <= LOC_BAR_PX,
               "fps_met": (1.0 / end_to_end >= FPS_BAR) if end_to_end else None}
        curve.append(row)
        previous = {"size": list(size), "state": {k: v.clone() for k, v in
                                                  model.state_dict().items()},
                    "name": name}
        torch.save({"state": previous["state"], "train": train_t, "held": held,
                    "size": list(size), "sigma": out["sigma"], "round": name},
                   OUT / f"{name}.pt")
        Path(args.out).write_text(json.dumps(curve, indent=1))
        print(json.dumps(row, indent=1), flush=True)
        del model, out
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
    print(json.dumps([{k: row[k] for k in ("round", "size", "f1", "localisation_px_p90",
                                           "ms_per_frame_end_to_end")} for row in curve],
                     indent=1))
    return 0


def cmd_report(args) -> int:
    """Everything a trained checkpoint has to say, without training it again."""
    import torch
    torch.set_num_threads(8)
    size = parse_size(args.size)
    device = pick_device(args.device)
    labels = load_labels()
    _train, held = split_for_rounds(labels)
    model, _saved = load_checkpoint(args.bitmap, size)
    model = model.to(device)
    result = evaluate_held(model, labels, held, size, device)
    operating = result["operating"]
    heat = result.pop("heats")
    paths = render_overlays(model, labels, held, size, device, operating["threshold"],
                            args.overlay_count, args.overlay_dir,
                            tag=f"{size[0]}x{size[1]}")
    report = disagreement(heat, labels, held, size, operating["threshold"],
                          quad=reference_quad())
    speed = {}
    try:
        speed_times = held[:12]
        started = time.time()
        _ = predict(model, VIDEO, speed_times, device=device, size=size)
        end_to_end = (time.time() - started) / max(1, len(speed_times))
        started = time.time()
        _ = predict(model, VIDEO, speed_times, device=device, size=size, decode=False)
        inference_only = (time.time() - started) / max(1, len(speed_times))
        speed = {"ms_per_frame_end_to_end": round(end_to_end * 1000, 1),
                 "ms_per_frame_inference_only": round(inference_only * 1000, 1),
                 "fps_end_to_end": round(1.0 / end_to_end, 1),
                 "fps_inference_only": round(1.0 / inference_only, 1)}
    except Exception as exc:                      # a stopwatch must not lose the report
        print(f"speed measurement failed: {type(exc).__name__}: {exc}", flush=True)
    payload = {"checkpoint": str(args.bitmap), "size": list(size), "device": device,
               "held_frames": len(held), "operating": operating, "speed": speed,
               "best_f1_any_threshold": result["best_f1"],
               "sweep": result["sweep"], "disagreement": report, "overlays": paths,
               "bars": {"f1": F1_BAR, "p90_localisation_px": LOC_BAR_PX,
                        "f1_met": operating["f1"] >= F1_BAR,
                        "p90_met": (operating["localisation_px_p90"] or 99) <= LOC_BAR_PX}}
    out = Path(args.out) if args.out else OUT / f"report_{size[0]}x{size[1]}.json"
    out.write_text(json.dumps(payload, indent=1))
    print(json.dumps(operating, indent=1))
    print(json.dumps(report, indent=1))
    print(json.dumps({"overlays": len(paths), "dir": args.overlay_dir, "out": str(out)},
                     indent=1))
    return 0


def cmd_overlays(args) -> int:
    size = parse_size(args.size)
    labels = load_labels()
    _train, held = split_for_rounds(labels)
    model, saved = load_checkpoint(args.bitmap, size)
    paths = render_overlays(model, labels, held, size, "cpu", args.threshold, args.count,
                            args.overlay_dir, tag=f"{size[0]}x{size[1]}")
    print(json.dumps({"overlays": len(paths), "dir": args.overlay_dir,
                      "checkpoint_size": saved}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
