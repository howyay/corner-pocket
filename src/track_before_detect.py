"""Track-before-detect: accumulate the ball-scale channel along hypothesised trajectories.

Why
---
A single frame pair catches only 6 of 25 *known moving* balls in the best channel
(blue, 17x17 footprint at 720p -- ``out/motion_scan/vod30.json``, ``channels_report``),
and the median moving ball reads 0.40-0.93 of the quiet-floor threshold.  The reason
is statistical: the per-frame bar is a maximum over ~200 k cloth pixels, so it is an
extreme-value statistic, while one ball occupies one footprint.  Accumulating along a
trajectory changes what the bar has to beat: a coherent ball adds the *same* reading
at N successive positions on a line, while noise -- and a person, whose change is
diffuse and not linear -- does not stay on the line.

What it does
------------
For each frame pair the ball-scale response is computed exactly as in
:mod:`src.motion_scan` (``max`` over the cloth of the mean ``|delta|`` inside a
ball-sized footprint), but kept as a *map* rather than reduced to a scalar.  A
hypothesis ``(x, y, vx, vy)`` at frame ``t0`` scores the mean of ``R_k(p_k)`` over
``N`` frames, with the per-frame spatial median subtracted so a globally busy frame
lifts nothing, and each frame's own contribution clipped at zero.

Thresholds
----------
Every bar comes from a *null sample*: the same search, run over the same 14 quiet
10 s windows chosen by occlusion density alone, over random seeds.  The detector's
bar is that sample's ``p{TBD_QUANTILE}`` times a stated margin, and the report says
which sample produced it.  The 25 known movers and the 15 events are evaluation sets
and are never used to set a threshold.

Nothing here writes to the queue or the gates; it reads video and artifacts and
writes its own report under ``out/motion_scan/``.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np

from src import motion_scan as ms

ROOT = Path(__file__).resolve().parents[1]

CHANNEL = "B"                   # the best channel measured on this footage
COMPARE_CHANNEL = "luma"        # carried for comparison, as briefed
N_FRAMES = (3, 5, 7, 9)
SPEEDS = (12.0, 18.0, 24.0, 30.0, 36.0, 42.0, 48.0)   # px/frame at 720p, ball-plausible
N_DIRECTIONS = 12               # every 30 degrees
SEARCH_RADIUS_PX = 24.0         # local search half-width for the blind evaluation
SEED_STRIDE_PX = 4              # spatial subsampling of the hypothesis grid
TBD_QUANTILE = 99.9             # the bar is this quantile of the null sample
TBD_MARGIN = 1.25               # ... times this
COHERENCE_MIN = 0.6             # share of track frames that must clear the per-frame median


@dataclass
class TBDConfig:
    channel: str = CHANNEL
    n_frames: int = 5
    speeds: tuple = SPEEDS
    n_directions: int = N_DIRECTIONS
    search_radius_px: float = SEARCH_RADIUS_PX
    seed_stride_px: int = SEED_STRIDE_PX
    clip_negative: bool = True      # subtract the per-frame spatial median
    max_speed_px_frame: float | None = None   # None -> the largest of ``speeds``


def velocity_grid(cfg: TBDConfig) -> np.ndarray:
    """``(n, 2)`` array of ``(vx, vy)`` px/frame hypotheses.

    At 30 fps a ball at 1-3 m/s moves 12-48 px/frame at 720p (the research pass's
    numbers), so the radial grid spans exactly that.  12 directions put adjacent
    hypotheses 30 degrees apart, i.e. a 12 px/frame speed is mis-assigned by at most
    sin(15 deg) = 26 % in direction; over ``N`` frames that is 26 % x N x 12 px of
    lateral drift -- the reason the search is a *local maximum* test rather than a
    single best cell, and the reason the score is also required to fall off around
    the peak.
    """
    velocities = []
    for speed in cfg.speeds:
        for i in range(cfg.n_directions):
            angle = 2.0 * math.pi * i / cfg.n_directions
            velocities.append((speed * math.cos(angle), speed * math.sin(angle)))
    return np.asarray(velocities, np.float64)


def response_map(prev_bgr, bgr, ctx, cfg: ms.MotionConfig, k: int | None = None,
                 channel: str | None = None) -> np.ndarray:
    """The ball-scale response at every pixel of the cloth's bounding box, float32.

    Same statistic as :func:`src.motion_scan.probe_pair` uses, kept as a map so a
    whole trajectory can be scored without re-filtering the frame.
    """
    k = k or ms.resolved_ball_k(cfg)
    channel = channel or CHANNEL
    prev = ms.channel_planes(prev_bgr, (channel,))[channel]
    cur = ms.channel_planes(bgr, (channel,))[channel]
    diff = cv2.absdiff(cur, prev).astype(np.float32)
    return cv2.boxFilter(diff, -1, (k, k), normalize=True,
                         borderType=cv2.BORDER_REPLICATE)


def patch_stack(video, frames: list, ctx, cfg: ms.MotionConfig, k=None,
                channel=None) -> tuple:
    """Response maps for a run of consecutive frames, plus the changed fraction.

    ``frames`` are frame indices; the map at index ``i`` describes the pair
    ``(frames[i]-1, frames[i])``.  Returns ``(stack, occ_dense, times)`` where
    ``stack`` has shape ``(len(frames)-1, H, W)``.
    """
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stack, dense, times = [], [], []
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(1, int(frames[0]) - 1))
        ok, prev = cap.read()
        if not ok:
            return np.zeros((0, cfg.scan_h, cfg.scan_w), np.float32), [], []
        index = max(1, int(frames[0]) - 1)
        while True:
            ok, cur = cap.read()
            if not ok:
                break
            index += 1
            if index > int(frames[-1]):
                break
            if index not in frames:
                prev = cur
                continue
            stack.append(response_map(prev, cur, ctx, cfg, k, channel))
            dense.append(float(ms.probe_pair(prev, cur, ctx, cfg)["occ_dense"]))
            times.append(index / fps)
            prev = cur
    finally:
        cap.release()
    if not stack:
        return np.zeros((0, cfg.scan_h, cfg.scan_w), np.float32), [], []
    return np.stack(stack), dense, times


def _prepare(stack: np.ndarray, clip_negative: bool = True) -> np.ndarray:
    """Subtract each frame's own spatial median, so a busy frame lifts nothing."""
    if not clip_negative:
        return stack
    medians = np.median(stack.reshape(stack.shape[0], -1), axis=1)
    return np.maximum(stack - medians[:, None, None], 0.0)


def score_mesh(prepared: np.ndarray, seeds, velocities: np.ndarray,
               height: int, width: int) -> np.ndarray:
    """``(n_seeds, n_velocities)`` score for every hypothesis at once.

    The whole (space, velocity) grid is evaluated with one fancy-index per frame
    instead of one per hypothesis: the search visits ~10^4 hypotheses per seed and a
    Python loop over them turns a two-minute measurement into a twenty-minute one.
    A hypothesis that leaves the frame on any frame scores -1.
    """
    seeds = np.asarray(seeds, np.float64)
    vx, vy = velocities[:, 0][None, :], velocities[:, 1][None, :]
    sx, sy = seeds[:, 0][:, None], seeds[:, 1][:, None]
    n = prepared.shape[0]
    acc = np.zeros((seeds.shape[0], velocities.shape[0]), np.float64)
    alive = np.ones_like(acc, bool)
    for i in range(n):
        px = np.rint(sx + vx * i).astype(np.int64)
        py = np.rint(sy + vy * i).astype(np.int64)
        alive &= (px >= 0) & (py >= 0) & (px < width) & (py < height)
        np.clip(px, 0, width - 1, out=px)
        np.clip(py, 0, height - 1, out=py)
        acc += prepared[i][py, px]
    acc /= n
    acc[~alive] = -1.0
    return acc


def search_tracks(prepared: np.ndarray, ctx, cfg: ms.MotionConfig, tbd: TBDConfig,
                  centre=None, seeds=None) -> dict:
    """Best hypothesis by score, with the local-maximum test.

    ``centre`` restricts the search to a disc (the blind evaluation around a known
    ball); ``seeds`` gives explicit starting points.  A candidate is accepted only
    when its score is a local maximum: strictly greater than the best score found
    with the speed halved and doubled along the same direction and with the direction
    rotated by +/- 30 degrees, so a broad plateau is not mistaken for a track.
    """
    height, width = prepared.shape[1], prepared.shape[2]
    grid = velocity_grid(tbd)
    if seeds is None:
        if centre is None:
            raise ValueError("either centre or seeds is required")
        r = int(round(tbd.search_radius_px))
        step = max(1, int(tbd.seed_stride_px))
        seeds = [(centre[0] + dx, centre[1] + dy)
                 for dy in range(-r, r + 1, step) for dx in range(-r, r + 1, step)
                 if dx * dx + dy * dy <= r * r]
    scores = score_mesh(prepared, seeds, grid, height, width)
    flat = int(np.argmax(scores))
    si, vi = divmod(flat, scores.shape[1])
    score = float(scores[si, vi])
    if score < 0:
        return {"score": None, "local_max": False, "n_hypotheses": 0}
    x0, y0 = seeds[si]
    vx, vy = float(grid[vi, 0]), float(grid[vi, 1])
    speed = math.hypot(vx, vy)
    direction = math.atan2(vy, vx)
    probes = np.asarray([
        (speed * 0.5 * math.cos(direction), speed * 0.5 * math.sin(direction)),
        (speed * 2.0 * math.cos(direction), speed * 2.0 * math.sin(direction)),
        (speed * math.cos(direction - math.pi / 6), speed * math.sin(direction - math.pi / 6)),
        (speed * math.cos(direction + math.pi / 6), speed * math.sin(direction + math.pi / 6)),
    ], np.float64)
    neighbours = score_mesh(prepared, [seeds[si]], probes, height, width)[0]
    values = []
    for i in range(prepared.shape[0]):
        px = int(round(x0 + vx * i))
        py = int(round(y0 + vy * i))
        values.append(float(prepared[i, py, px]))
    return {"score": score, "x": float(x0), "y": float(y0), "vx": vx, "vy": vy,
            "coherent": bool(np.count_nonzero(np.asarray(values) > 0.5)
                             / max(1, len(values)) >= COHERENCE_MIN),
            "values": [round(v, 3) for v in values],
            "local_max": bool(score > float(neighbours.max())),
            "speed_px_frame": round(speed, 3),
            "direction_deg": round(math.degrees(direction) % 360.0, 1),
            "n_hypotheses": int(np.count_nonzero(scores >= 0)), "seeds": len(seeds)}


def evaluate_stack(prepared: np.ndarray, ctx, cfg: ms.MotionConfig, tbd: TBDConfig,
                   ns, centre=None, seeds=None) -> dict:
    """Best hypothesis for each N, from one stack of response maps.

    The maps for N=3 are a prefix of the maps for N=9, so every N is scored from the
    same decoded frames -- one video read per seed instead of one per (seed, N).
    """
    out = {}
    for n in ns:
        if prepared.shape[0] < n:
            out[int(n)] = {"score": None, "n_hypotheses": 0}
            continue
        sub_cfg = TBDConfig(**{**asdict(tbd), "n_frames": int(n)})
        out[int(n)] = search_tracks(prepared[:n], ctx, cfg, sub_cfg, centre=centre,
                                    seeds=seeds)
    return out


def null_sample(video, ctx, cfg: ms.MotionConfig, windows: list, tbd: TBDConfig,
                seeds_per_window: int = 120, rng=None, n_frames=None,
                stacks_per_window: int = 5) -> dict:
    """The bar's sample: the same search over quiet windows, on random seeds.

    This is a *null* run -- the seeds are random cloth positions, not balls -- so the
    distribution it produces is what the detector reads when nothing is there.  Several
    stacks per window are shared by many random spatial seeds, because the video read
    is the expensive part and the distribution of interest is over hypotheses, not
    over decode calls.
    """
    rng = rng or np.random.default_rng(20260923)
    x0, y0, x1, y1 = ctx.bbox
    ns = [int(n) for n in (n_frames or [tbd.n_frames])]
    longest = max(ns)
    tbd = TBDConfig(**{**asdict(tbd), "n_frames": longest})
    seeds_per_stack = max(1, seeds_per_window // max(1, stacks_per_window))
    scores = {int(n): [] for n in ns}
    for (a, b) in windows:
        for k in range(stacks_per_window):
            mid = a + (b - a) * (k + 0.5) / stacks_per_window
            frames = list(range(int(mid * 30.0) - longest, int(mid * 30.0) + 1))
            stack, dense, times = patch_stack(video, frames, ctx, cfg, channel=tbd.channel)
            if stack.shape[0] < longest:
                continue
            prepared = _prepare(stack, tbd.clip_negative)
            for _ in range(seeds_per_stack):
                centre = (float(rng.uniform(x0 + 30, x1 - 30)),
                          float(rng.uniform(y0 + 30, y1 - 30)))
                hits = evaluate_stack(prepared, ctx, cfg, tbd, ns, centre=centre)
                for n in ns:
                    if hits[int(n)].get("score") is not None:
                        scores[int(n)].append(hits[int(n)]["score"])
    out = {}
    for n in ns:
        arr = np.asarray(scores[int(n)], np.float64)
        if arr.size == 0:
            out[int(n)] = {"n": 0}
            continue
        q = float(np.percentile(arr, TBD_QUANTILE))
        out[int(n)] = {"n": int(arr.size), "median": round(float(np.median(arr)), 4),
                       "p90": round(float(np.percentile(arr, 90)), 4),
                       "p99": round(float(np.percentile(arr, 99)), 4),
                       "p999": round(q, 4), "max": round(float(arr.max()), 4),
                       "quantile": TBD_QUANTILE, "margin": TBD_MARGIN,
                       "bar": round(q * TBD_MARGIN, 4), "channel": tbd.channel,
                       "n_frames": int(n), "stacks_per_window": stacks_per_window,
                       "source": "random spatial seeds inside the cloth, several stacks "
                                 "per quiet window (windows chosen by occ_dense p90 alone)"}
    return out


# ------------------------------------------------------------- evaluation ----

def blind_on_known_movers(video, ctx, cfg, specs: dict, bars: dict, quad_px,
                          max_instances: int = 200) -> list:
    """Run the detector around each known mover without being told where it is.

    The centre of the local search disc is the instance's own midpoint, and the
    search spans the full velocity grid and a +/- ``search_radius_px`` disc of
    starting points -- so the detector has to find the ball's position and its
    velocity itself.  Localisation error is measured against where the census ball
    actually was on the first frame of the stack, and speed error against the
    census displacement divided by its time gap.
    """
    census = ms.load_census("vod30", ROOT)
    instances = ms.moving_ball_instances(census, min_move_px=specs["min_move_px"])
    instances = instances[:max_instances]
    ns = specs["ns"]
    longest = max(ns)
    rows = []
    for item in instances:
        t_mid = 0.5 * (item["t_from"] + item["t_to"])
        centre_frame = int(round(t_mid * 30.0))
        frames = list(range(centre_frame - longest + 1, centre_frame + 1))
        stack, dense, times = patch_stack(video, frames, ctx, cfg,
                                          channel=specs["channel"])
        if stack.shape[0] < longest:
            continue
        prepared = _prepare(stack, specs["clip_negative"])
        centre = (0.5 * (item["p_from"][0] + item["p_to"][0]),
                  0.5 * (item["p_from"][1] + item["p_to"][1]))
        tbd = TBDConfig(channel=specs["channel"], n_frames=longest,
                        search_radius_px=specs["search_radius_px"])
        hits = evaluate_stack(prepared, ctx, cfg, tbd, ns, centre=centre)
        # where the ball was on the first frame of the stack, from the census line
        f = (times[0] - item["t_from"]) / max(1e-6, item["t_to"] - item["t_from"])
        truth = (item["p_from"][0] + (item["p_to"][0] - item["p_from"][0]) * f,
                 item["p_from"][1] + (item["p_to"][1] - item["p_from"][1]) * f)
        row = {**item, "t_mid": round(t_mid, 3), "truth_at_stack_start": [round(truth[0], 1), round(truth[1], 1)],
               "occ_dense_max": round(max(dense), 4) if dense else None, "per_n": {}}
        for n in ns:
            hit = hits[int(n)]
            if hit.get("score") is None:
                row["per_n"][str(n)] = {"score": None, "detected": False}
                continue
            err = math.hypot(hit["x"] - truth[0], hit["y"] - truth[1])
            row["per_n"][str(n)] = {
                "score": round(hit["score"], 3), "bar": bars.get(str(n), {}).get("bar"),
                "detected": bool(hit["score"] > (bars.get(str(n), {}).get("bar") or 1e9)
                                 and hit["local_max"]),
                "localisation_error_px": round(err, 1),
                "speed_error_px_frame": round(abs(hit["speed_px_frame"] - item["px_per_frame"]), 2),
                "speed_px_frame": hit["speed_px_frame"],
                "local_max": hit["local_max"],
                "position": [round(hit["x"], 1), round(hit["y"], 1)],
                "direction_deg": hit["direction_deg"],
                "values": hit["values"],
            }
        rows.append(row)
    return rows


def sweep(video, ctx, cfg, specs: dict, arrays: dict, bars: dict,
          min_gap_s: float = 1.0, floor: float = 20.0, max_seeds: int = 600) -> dict:
    """Whole-VOD sweep: seed times from the single-frame series, verify with TBD.

    The seeds are the frames where the *single-frame* channel is a local maximum at
    least ``min_gap_s`` apart and above ``floor``; the spatial and velocity search is
    the detector's own, over the whole cloth.
    """
    signal = specs["seed_signal"]
    values = np.asarray(arrays[signal], np.float64)
    t = np.asarray(arrays["t"], np.float64)
    order = np.argsort(-values)
    seeds = []
    for index in order:
        index = int(index)
        if values[index] < floor:
            break
        if any(abs(t[index] - s) < min_gap_s for s in seeds):
            continue
        seeds.append(index)
        if len(seeds) >= max_seeds:
            break
    seeds = sorted(seeds)
    ns = specs["ns"]
    longest = max(ns)
    frame_seeds = [(index, float(t[index])) for index in seeds]
    rows = []
    started = time.time()
    for index, tau in frame_seeds:
        frames = list(range(index - longest + 1, index + 1))
        stack, dense, times = patch_stack(video, frames, ctx, cfg, channel=specs["channel"])
        if stack.shape[0] < longest:
            continue
        prepared = _prepare(stack, specs["clip_negative"])
        tbd = TBDConfig(channel=specs["channel"], n_frames=longest,
                        search_radius_px=specs["search_radius_px"])
        hits = evaluate_stack(prepared, ctx, cfg, tbd, ns, seeds=_cloth_seeds(ctx, cfg, tbd))
        best = hits[int(max(ns))]
        rows.append({"t_seed": round(tau, 3), "frame": index,
                     "seed_value": round(float(values[index]), 3),
                     "occ_dense": round(max(dense), 4) if dense else None,
                     "score": best.get("score"), "local_max": best.get("local_max"),
                     "speed_px_frame": best.get("speed_px_frame"),
                     "direction_deg": best.get("direction_deg"),
                     "position": ([round(best["x"], 1), round(best["y"], 1)]
                                  if best.get("score") is not None else None),
                     "verified": bool(best.get("score") is not None
                                      and best["score"] > (bars.get(str(max(ns)), {}).get("bar") or 1e9)
                                      and best["local_max"]),
                     "per_n": {str(n): round(hits[int(n)]["score"], 3)
                               if hits[int(n)].get("score") is not None else None for n in ns}})
    return {"seeds": len(frame_seeds), "swept": len(rows), "seconds": round(time.time() - started, 1),
            "rows": rows}


def _cloth_seeds(ctx, cfg, tbd, stride_px: int = 16) -> list:
    """The spatial hypothesis grid, in the frame's own pixels.

    ``ctx.bbox`` is in working-resolution coordinates while the response maps are
    native, so the grid is built from the quad's native bounding box.  The stride
    trades search resolution for a bounded number of hypotheses: at 16 px on 720p
    this is ~800 starting points x 84 velocities, which keeps one seed's search at a
    few tens of milliseconds.
    """
    quad = np.asarray(ctx.poly, np.float64)
    x0, y0 = quad[:, 0].min(), quad[:, 1].min()
    x1, y1 = quad[:, 0].max(), quad[:, 1].max()
    margin = int(tbd.search_radius_px) + cfg.ball_k
    step = max(1, int(stride_px))
    return [(float(x), float(y))
            for y in range(int(max(0, y0 + margin)), int(y1 - margin) + 1, step)
            for x in range(int(max(0, x0 + margin)), int(x1 - margin) + 1, step)]


def render_track_strip(video, row, ctx, cfg, bars: dict, path, offsets=(-4, -2, 0, 2, 4),
                       scale: float = 0.5) -> str:
    """Frames around a claimed detection with the detected track drawn on them."""
    position = row.get("position")
    speed = row.get("speed_px_frame") or 0.0
    angle = math.radians(row.get("direction_deg") or 0.0)
    vx, vy = speed * math.cos(angle), speed * math.sin(angle)
    centre = int(row["frame"])
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    tiles = []
    try:
        for offset in offsets:
            index = max(1, centre + offset)
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, bgr = cap.read()
            if not ok:
                continue
            small = cv2.resize(bgr, None, fx=scale, fy=scale)
            quad = (ctx.poly.astype(np.float64) * scale).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(small, [quad], True, (80, 255, 80), 2)
            if position:
                pts = []
                for k in range(-8, 9):
                    x = position[0] + vx * (offset - k)
                    y = position[1] + vy * (offset - k)
                    pts.append((int(x * scale), int(y * scale)))
                for a, b in zip(pts, pts[1:]):
                    cv2.line(small, a, b, (0, 0, 255), 1)
                cv2.circle(small, (int(position[0] * scale), int(position[1] * scale)), 14,
                           (0, 255, 255), 2)
            caption = (f"t={index / fps:7.2f}s ({offset:+d}f)  score={row.get('score')} "
                       f"bar={bars.get('5', {}).get('bar')}  v={speed:.1f}px/f "
                       f"occ_dense={row.get('occ_dense')}")
            cv2.rectangle(small, (0, 0), (small.shape[1], 26), (0, 0, 0), -1)
            cv2.putText(small, caption, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (255, 255, 255), 1, cv2.LINE_AA)
            tiles.append(small)
    finally:
        cap.release()
    if not tiles:
        raise OSError("no frames for the strip")
    tile_h, tile_w = tiles[0].shape[:2]
    canvas = np.full((tile_h, tile_w * len(tiles), 3), 24, np.uint8)
    for i, tile in enumerate(tiles):
        canvas[:, i * tile_w:(i + 1) * tile_w] = tile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas)
    return str(path)


# ------------------------------------------------------------------ CLI -------

def _windows_from_report(dataset: str = "vod30", root=None) -> list:
    root = Path(root or ROOT)
    path = root / "out" / "motion_scan" / f"{dataset}.json"
    if not path.exists():
        return []
    report = json.loads(path.read_text())
    blocks = (report.get("channels_report") or {}).get("quiet_blocks") or []
    return [(b["t_start"], b["t_end"]) for b in blocks]


def cmd_null(args) -> None:
    report, arrays = ms.load_scan(args.out_dir, args.dataset)
    cfg = ms.MotionConfig(**{k: v for k, v in report["config"].items()
                             if k in ms.MotionConfig.__dataclass_fields__})
    quad = ms.load_quad(args.dataset, quad_file=args.quad,
                        frame_size=(cfg.scan_w, cfg.scan_h))
    ctx = ms.cloth_context(quad["quad_px"], cfg)
    windows = _windows_from_report(args.dataset)
    tbd = TBDConfig(channel=args.channel, n_frames=max(args.n_frames))
    started = time.time()
    stats = null_sample(args.video, ctx, cfg, windows, tbd,
                        seeds_per_window=args.seeds_per_window, n_frames=args.n_frames,
                        stacks_per_window=args.stacks_per_window)
    seconds = round(time.time() - started, 1)
    for n, row in sorted(stats.items(), key=lambda kv: int(kv[0])):
        row["seconds"] = seconds
        print(f"N={n}: n={row.get('n')} median={row.get('median')} "
              f"p99={row.get('p99')} p999={row.get('p999')} bar={row.get('bar')}",
              flush=True)
    ms.save_report({"tbd_null": {str(k): v for k, v in stats.items()},
                    "tbd_null_seconds": seconds}, args.out_dir, args.dataset)
    print(f"null sample wall time {seconds}s")


def cmd_eval(args) -> None:
    report, arrays = ms.load_scan(args.out_dir, args.dataset)
    cfg = ms.MotionConfig(**{k: v for k, v in report["config"].items()
                             if k in ms.MotionConfig.__dataclass_fields__})
    quad = ms.load_quad(args.dataset, quad_file=args.quad,
                        frame_size=(cfg.scan_w, cfg.scan_h))
    ctx = ms.cloth_context(quad["quad_px"], cfg)
    bars = {k: v for k, v in (report.get("tbd_null") or {}).items()}
    if not bars:
        raise SystemExit("run `track_before_detect null` first: no bars measured")
    ns = sorted(int(k) for k in bars)
    specs = {"channel": args.channel, "ns": ns, "clip_negative": True,
             "search_radius_px": SEARCH_RADIUS_PX, "seed_signal": args.seed_signal,
             "min_move_px": args.min_move_px}

    started = time.time()
    blind = blind_on_known_movers(args.video, ctx, cfg, specs, bars, quad["quad_px"])
    blind_seconds = round(time.time() - started, 1)
    summary = {}
    for n in ns:
        got = [r for r in blind if r["per_n"].get(str(n), {}).get("detected")]
        errs = [r["per_n"][str(n)]["localisation_error_px"] for r in blind
                if r["per_n"].get(str(n), {}).get("detected")]
        serrs = [r["per_n"][str(n)]["speed_error_px_frame"] for r in blind
                 if r["per_n"].get(str(n), {}).get("detected")]
        summary[str(n)] = {
            "instances": len(blind), "detected": len(got),
            "rate": round(len(got) / max(1, len(blind)), 3),
            "bar": bars[str(n)].get("bar"),
            "localisation_error_px_median": round(float(np.median(errs)), 1) if errs else None,
            "speed_error_px_frame_median": round(float(np.median(serrs)), 2) if serrs else None,
        }
    print("blind on known movers:", json.dumps(summary, indent=1), flush=True)

    sweep_out = sweep(args.video, ctx, cfg, specs, arrays, bars,
                      max_seeds=args.max_seeds)
    quiet = _windows_from_report(args.dataset)
    verified = [r for r in sweep_out["rows"] if r["verified"]]
    in_quiet = [r for r in verified if any(a <= r["t_seed"] <= b for a, b in quiet)]
    quiet_minutes = sum(b - a for a, b in quiet) / 60.0
    sweep_summary = {"seeds": sweep_out["seeds"], "swept": sweep_out["swept"],
                     "seconds": sweep_out["seconds"],
                     "verified": len(verified),
                     "verified_in_quiet_windows": len(in_quiet),
                     "quiet_minutes": round(quiet_minutes, 2),
                     "false_positives_per_minute_quiet": round(len(in_quiet) / max(1e-6, quiet_minutes), 3),
                     "verified_list": [{k: r[k] for k in ("t_seed", "score", "speed_px_frame",
                                                          "direction_deg", "occ_dense")}
                                       for r in verified]}
    print("sweep:", json.dumps({k: v for k, v in sweep_summary.items()
                                if k != "verified_list"}, indent=1), flush=True)

    events = []
    for event in ms._served_events(ROOT, args.events, args.dataset):
        t0 = float(event["t"])
        centre_frame = int(round(t0 * 30.0))
        longest = max(ns)
        frames = list(range(centre_frame - longest + 1, centre_frame + 1))
        stack, dense, times = patch_stack(args.video, frames, ctx, cfg, channel=args.channel)
        if stack.shape[0] < longest:
            continue
        prepared = _prepare(stack, True)
        tbd = TBDConfig(channel=args.channel, n_frames=longest,
                        search_radius_px=SEARCH_RADIUS_PX)
        hits = evaluate_stack(prepared, ctx, cfg, tbd, ns, seeds=_cloth_seeds(ctx, cfg, tbd))
        best_n = str(max(ns))
        best = hits[int(max(ns))]
        events.append({**event, "score": best.get("score"), "bar": bars[best_n].get("bar"),
                       "local_max": best.get("local_max"),
                       "speed_px_frame": best.get("speed_px_frame"),
                       "position": ([round(best["x"], 1), round(best["y"], 1)]
                                    if best.get("score") is not None else None),
                       "occ_dense_max": round(max(dense), 4) if dense else None,
                       "track_detected": bool(best.get("score") is not None
                                              and best["score"] > (bars[best_n].get("bar") or 1e9)
                                              and best["local_max"]),
                       "per_n": {str(n): round(hits[int(n)]["score"], 3)
                                 if hits[int(n)].get("score") is not None else None for n in ns}})
    event_summary = {"n": len(events),
                     "track_detected": sum(1 for e in events if e["track_detected"]),
                     "occlusion_explained": sum(1 for e in events
                                                if (e["occ_dense_max"] or 0) >= ms.OCC_DENSE_MIN)}
    print("events:", json.dumps(event_summary), flush=True)

    strips = []
    for i, row in enumerate(verified[:args.strips]):
        try:
            strips.append(render_track_strip(
                args.video, row, ctx, cfg, bars,
                Path(args.out_dir) / "tbd" / f"{i + 1:02d}_t{row['t_seed']:07.2f}s_"
                                             f"score_{row['score']:.0f}.png"))
        except OSError:
            continue
    payload = {"tbd_bars": bars, "tbd_specs": specs,
               "tbd_blind": blind, "tbd_blind_summary": summary,
               "tbd_blind_seconds": blind_seconds,
               "tbd_sweep_summary": sweep_summary,
               "tbd_sweep_rows": sweep_out["rows"],
               "tbd_events": events, "tbd_event_summary": event_summary,
               "tbd_strips": strips,
               "notes": [
                   "bars come from the null sample: the same search on random seeds over "
                   "the quiet windows, chosen by occ_dense p90 alone",
                   "the 25 known movers and the 15 events are evaluation sets and were "
                   "never used to set a threshold",
                   "no physics beyond a constant-velocity straight track",
               ]}
    path = ms.save_report(payload, args.out_dir, args.dataset)
    print(f"strips: {strips}")
    print(f"wrote {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--video", default=None)
        p.add_argument("--dataset", default="vod30")
        p.add_argument("--out-dir", default=str(ROOT / "out" / "motion_scan"))
        p.add_argument("--quad", default=None)

    p = sub.add_parser("null", help="measure the detector's null distribution")
    common(p)
    p.add_argument("--channel", default=CHANNEL)
    p.add_argument("--n-frames", type=int, nargs="+", default=[5])
    p.add_argument("--seeds-per-window", type=int, default=120)
    p.add_argument("--stacks-per-window", type=int, default=5)
    p.set_defaults(func=cmd_null)

    p = sub.add_parser("eval", help="blind movers, whole-VOD sweep, the 15 events")
    common(p)
    p.add_argument("--channel", default=CHANNEL)
    p.add_argument("--seed-signal", default="ball17")
    p.add_argument("--events", default="out/scan30/events.tiered.json")
    p.add_argument("--max-seeds", type=int, default=600)
    p.add_argument("--min-move-px", type=float, default=5.0)
    p.add_argument("--strips", type=int, default=6)
    p.set_defaults(func=cmd_eval)

    args = ap.parse_args(argv)
    if getattr(args, "video", None) is None:
        args.video = str(ms.video_for(args.dataset))
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
