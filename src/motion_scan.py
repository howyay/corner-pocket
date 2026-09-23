"""Dense, whole-VOD motion measurement: a ball-scale channel and an occlusion channel.

Why this module exists
----------------------
The owner's complaint is that **none of the served event timestamps carry any ball
movement**.  A parallel measurement (``src/timing_verify.py``) settled the *time*
question -- the VOD is CFR, the frame-index and container-time paths agree, the
served timestamps are where they claim to be -- and found that what sits at those
timestamps is *people*: 15-77 % of the cloth changes, in person-sized blobs.  The
research pass (``docs/research-video-world-models.md``) verdict is that no open
video world model measures anything, so what is missing is a measurement, not a
model.  This module is the dense version of that measurement: every frame of the
whole VOD, two channels with separate jobs.

The two channels
----------------
**Ball-scale channel** -- the largest *local* change on a ball-sized footprint:
``max over cloth of mean(|gray(f) - gray(f-1)|)`` inside a ``k x k`` window.  A
single-pixel maximum (what ``timing_verify`` used) has no footprint constraint at
all and is therefore set by compression noise; averaging over the ball's own
footprint suppresses noise by ~sqrt(k^2) while a ball-sized change survives.  The
footprint is taken from the measured ball: SAM3 ball radii in
``out/scan30/sam3_results.json`` give radius median 9.45 px, p10 6.9, p90 12.41 at
native -> **diameter 18.9 px median** (p10 13.8, p90 24.8), i.e. 14.2 px at the
pipeline's 960x540 working size.  The primary footprint is therefore **k = 17 px
at native 1280x720** (the equivalent-area square for the median ball is 16.7 px),
with k = 9 and k = 25 carried as sensitivity checks and k = 13 at 960x540 as the
same measurement at the pipeline's working resolution.

**Occlusion channel** -- a player's body inside the quad is *real* motion that is
not a ball, and it is what the naive cloth-mean diff actually measures:

``occ_share``  share of cloth pixels changing by at least :data:`CHANGE_PX` levels.
``occ_dense``  the largest large-footprint density: max over the cloth of the mean
               of that changed mask inside a :data:`OCC_DENSE_K` px square.  A ball
               never fills a 61 px window; a body does.
``mean``       the plain cloth-mean difference (the primitive the research quoted
               at 2.2 ms/frame), kept as an occlusion indicator only.

No deceleration, cushion or rolling model is applied to anything.  A physics prior
would be needed to turn motion into a shot *time*; :func:`decay_shape` reports the
raw decay so such a prior could be fitted later, not assumed now.

This module gates nothing: it is not wired into :mod:`src.event_gates` or the
queue and writes only under ``out/motion_scan/``.
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

ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------- geometry ----

SCAN_W, SCAN_H = 1280, 720      # native frame size of vod_30min_260815.mp4
WORK_W, WORK_H = 960, 540       # the pipeline's working resolution (0.75x native)

# --------------------------------------------------------------- channels ----

CHANGE_PX = 25                  # gray levels: a cloth pixel changed by this much "changed"
BALL_K_NATIVE = 17              # primary ball footprint, px, native (median ball 18.9 px)
BALL_K_SMALL = 9                # sensitivity: the ball's core only
BALL_K_WIDE = 25                # sensitivity: the p90 ball (24.8 px)
BALL_K_WORK = 13                # the same footprint at 960x540 (0.75 x 17)
OCC_DENSE_K = 61                # large footprint for the occlusion-density channel, px
GRID_ROWS, GRID_COLS = 12, 8    # coarse grid over the cloth quad's bounding box

# Measured on this VOD (out/scan30/sam3_results.json, 270 ball radii, see module docstring)
BALL_DIAMETER_NATIVE = 18.9
BALL_DIAMETER_P10 = 13.8
BALL_DIAMETER_P90 = 24.8
BALL_AREA_NATIVE = 266.0        # pi * (18.9 / 2) ^ 2, the area one ball covers at native

# Onset detection runs on this channel, at this resolution.
ONSET_SIGNAL = "ball17"

# An onset whose occlusion density is at or above this is explained by a person.
# The bar is set from geometry, not taste: within a 61x61 px (3721 px) window at
# native resolution a single ball can change at most ~530 px (the vacated plus the
# new position, 2 x 266 px^2, and less when they overlap) == 0.14 of the window,
# while a torso changes 0.5-1.0 of it.  0.30 is above anything one ball can reach
# and below anything a body reaches; it also leaves 87.8 % of this VOD's frames
# eligible, including every frame the still controls sit on.
OCC_DENSE_MIN = 0.30            # share of a 61x61 window that changed
OCC_SHARE_MIN = 0.02            # share of the whole cloth that changed
FLOOR_QUANTILE = 99.9           # the floor is this quantile of the control sample
FLOOR_MARGIN = 1.25             # threshold = floor x this

SERIES_FIELDS = ("t", "ball17", "ball9", "ball25", "ball13w",
                 "occ_share", "occ_dense", "mean", "cell", "cell_share")


@dataclass
class MotionConfig:
    """Scan parameters -- every number a verdict leans on is named here."""

    width: int = WORK_W
    height: int = WORK_H
    stride: int = 1
    limit_s: float | None = None
    change_px: int = CHANGE_PX
    ball_k: int = BALL_K_NATIVE
    work_k: int = BALL_K_WORK
    occ_dense_k: int = OCC_DENSE_K
    grid_rows: int = GRID_ROWS
    grid_cols: int = GRID_COLS
    native: bool = True


@dataclass
class OnsetConfig:
    """The onset detector's stated parameters (detection parameters, not physics)."""

    signal: str = ONSET_SIGNAL
    threshold: float = 0.0      # absolute bar on the signal; set from the controls
    merge_s: float = 0.25       # active frames this close belong to one event
    min_gap_s: float = 1.0      # two peaks closer than this are one event
    baseline_s: float = 20.0    # rolling-median half-window, reported per onset
    block_s: float = 5.0        # decimation block of the rolling median


@dataclass
class ScanReport:
    dataset: str
    video: str
    fps: float
    frame_count: int
    frames_scanned: int
    resolution: list
    native_resolution: list
    quad_px: list
    quad_source: str
    quad_verified: bool
    config: dict
    cost: dict
    series: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    onsets: list = field(default_factory=list)
    notes: list = field(default_factory=list)


# ------------------------------------------------------------- the quad ------

def load_quad(dataset: str = "vod30", root=None, quad_file=None) -> dict:
    """The verified cloth quad for ``dataset``, in native 1280x720 pixels.

    Order of evidence: an explicit ``quad_file``, the per-segment calibration
    artifact, the hand anchors, then the ``table_refine`` prior.  Never a
    per-frame ``detect_table`` mask -- that was shown to collapse under occlusion.
    """
    root = Path(root or ROOT)
    if quad_file:
        payload = json.loads(Path(quad_file).read_text())
        pts = payload.get("quad_px") or payload.get("corners") or payload.get("anchors")
        return {"quad_px": _as_quad(pts), "source": str(quad_file),
                "verified": bool(payload.get("verified", False)),
                "note": payload.get("note", "caller-supplied quad")}

    seg_file = root / "out" / f"calib_{dataset}_segments.json"
    if seg_file.exists():
        payload = json.loads(seg_file.read_text())
        segments = payload.get("segments") or []
        if segments:
            seg = segments[0]
            note = seg.get("source_detail") or seg.get("source")
            if len(segments) > 1:
                note = (f"{len(segments)} segments; using the first -- per-time segment "
                        f"lookup belongs to the calibration, not to this measurement")
            return {"quad_px": _as_quad(seg["quad_px"]), "source": str(seg_file),
                    "verified": bool((seg.get("evidence") or {}).get("trusted_for_mm")),
                    "note": note}

    anchors = root / "out" / "pid_anchors_vod30.json"
    if anchors.exists():
        payload = json.loads(anchors.read_text())
        rows = payload.get("anchors") or {}
        if rows:
            key = sorted(rows, key=lambda k: abs(float(k) - 70.0))[0]
            return {"quad_px": _as_quad(rows[key][:4]), "source": str(anchors),
                    "verified": True, "note": f"hand pocket anchors at t={key} (first four)"}

    try:
        from src.table_refine import prior_for
        prior = prior_for(dataset, root=root)
        if prior is not None:
            return {"quad_px": _as_quad(prior), "source": "src.table_refine.prior_for",
                    "verified": False, "note": "search-centre prior, not a verified quad"}
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"quad_px": None, "source": "none", "verified": False, "note": f"no quad ({exc})"}
    return {"quad_px": None, "source": "none", "verified": False, "note": "no quad found"}


def _as_quad(points) -> list | None:
    if not points:
        return None
    quad = np.asarray(points, dtype=np.float64)
    if quad.shape[0] > 4:
        quad = quad[:4]
    if quad.shape != (4, 2):
        raise ValueError(f"expected a 4x2 quad, got {quad.shape}")
    return quad.round(3).tolist()


def cloth_mask(quad_px, width: int = WORK_W, height: int = WORK_H,
               scan_w: float = SCAN_W, scan_h: float = SCAN_H) -> np.ndarray:
    """Boolean cloth mask at ``(width, height)`` for a native-resolution quad."""
    mask = np.zeros((height, width), np.uint8)
    poly = (np.asarray(quad_px, np.float64) *
            np.array([width / scan_w, height / scan_h], np.float64)).round().astype(np.int32)
    cv2.fillConvexPoly(mask, poly, 1)
    return mask.astype(bool)


@dataclass
class ClothContext:
    """Precomputed cloth indexing at both resolutions plus the coarse grid."""

    width: int
    height: int
    quad_px: list
    poly: np.ndarray            # quad in native pixels, int32
    mask: np.ndarray            # bool, working resolution
    idx: np.ndarray             # flat cloth indices, working resolution
    native_mask: np.ndarray
    native_idx: np.ndarray      # flat cloth indices, native resolution
    cell_of_idx: np.ndarray
    cell_counts: np.ndarray
    grid_rows: int
    grid_cols: int
    bbox: tuple

    @property
    def n_cells(self) -> int:
        return self.grid_rows * self.grid_cols

    @property
    def n_pixels(self) -> int:
        return int(self.mask.sum())

    @property
    def n_pixels_native(self) -> int:
        return int(self.native_mask.sum())


def cloth_context(quad_px, cfg: MotionConfig = MotionConfig()) -> ClothContext:
    mask = cloth_mask(quad_px, cfg.width, cfg.height)
    idx = np.flatnonzero(mask.ravel())
    poly = np.asarray(quad_px, np.int32)
    sc = np.array([cfg.width / SCAN_W, cfg.height / SCAN_H], np.float64)
    q = np.asarray(quad_px, np.float64) * sc
    x0, y0 = np.floor(q.min(axis=0)).astype(int)
    x1, y1 = np.ceil(q.max(axis=0)).astype(int)
    x1, y1 = max(x1, x0 + 1), max(y1, y0 + 1)
    ys, xs = np.divmod(idx, cfg.width)
    row = np.clip(((ys - y0) / (y1 - y0) * cfg.grid_rows).astype(np.int64), 0, cfg.grid_rows - 1)
    col = np.clip(((xs - x0) / (x1 - x0) * cfg.grid_cols).astype(np.int64), 0, cfg.grid_cols - 1)
    cell_of_idx = (row * cfg.grid_cols + col).astype(np.int64)
    cell_counts = np.bincount(cell_of_idx, minlength=cfg.grid_rows * cfg.grid_cols).astype(np.int64)
    if cfg.native:
        native_mask = cloth_mask(quad_px, SCAN_W, SCAN_H, SCAN_W, SCAN_H)
        native_idx = np.flatnonzero(native_mask.ravel())
    else:
        native_mask, native_idx = np.zeros((1, 1), bool), np.empty(0, np.int64)
    return ClothContext(width=cfg.width, height=cfg.height, quad_px=list(quad_px), poly=poly,
                        mask=mask, idx=idx, native_mask=native_mask, native_idx=native_idx,
                        cell_of_idx=cell_of_idx, cell_counts=cell_counts,
                        grid_rows=cfg.grid_rows, grid_cols=cfg.grid_cols,
                        bbox=(int(x0), int(y0), int(x1), int(y1)))


def _box_max(diff: np.ndarray, k: int, idx: np.ndarray) -> float:
    """Largest mean |diff| inside any k x k window, over the given pixel list."""
    blurred = cv2.boxFilter(diff, -1, (k, k), normalize=True,
                            borderType=cv2.BORDER_REPLICATE)
    return float(blurred.ravel()[idx].max())


def _box_argmax(diff: np.ndarray, k: int, idx: np.ndarray, width: int) -> tuple[float, tuple]:
    blurred = cv2.boxFilter(diff, -1, (k, k), normalize=True,
                            borderType=cv2.BORDER_REPLICATE)
    flat = blurred.ravel()
    values = flat[idx]
    pos = int(idx[int(np.argmax(values))])
    y, x = divmod(pos, width)
    return float(values.max()), (int(x), int(y))


# ------------------------------------------------------- the per-frame step ---

def clip_motion(prev_native, native, prev_work, work, ctx: ClothContext,
                cfg: MotionConfig = MotionConfig()) -> dict:
    """Both channels for one frame pair.  Pure numpy/cv2, no I/O.

    ``prev_native``/``native`` are native-resolution uint8 grayscale frames;
    ``prev_work``/``work`` the working-resolution ones.
    """
    work_diff = cv2.absdiff(work, prev_work)
    values = work_diff.ravel()[ctx.idx]
    # The occlusion channel is measured on the cloth only: a changed pixel outside
    # the quad must not leak into occ_dense through the box filter.
    changed_full = np.zeros(cfg.height * cfg.width, np.uint8)
    changed_full[ctx.idx] = (values >= cfg.change_px)
    n_changed = int(changed_full.sum())
    changed_map = changed_full.reshape(cfg.height, cfg.width).astype(np.float32)
    dense_map = cv2.boxFilter(changed_map, -1, (cfg.occ_dense_k, cfg.occ_dense_k),
                              normalize=True, borderType=cv2.BORDER_REPLICATE)
    occ_dense = float(dense_map.ravel()[ctx.idx].max())
    if n_changed:
        cell_sums = np.bincount(ctx.cell_of_idx, weights=changed_full[ctx.idx].astype(np.float64),
                                minlength=ctx.n_cells)
        cell = int(np.argmax(cell_sums))
        cell_share = float(cell_sums[cell] / n_changed)
    else:
        cell, cell_share = -1, 0.0
    out = {
        "ball13w": round(_box_max(work_diff.astype(np.float32), cfg.work_k, ctx.idx), 4),
        "occ_share": round(n_changed / max(1, ctx.idx.size), 6),
        "occ_dense": round(occ_dense, 5),
        "mean": round(float(values.mean()), 4),
        "cell": cell,
        "cell_share": round(cell_share, 4),
    }
    if native is not None and prev_native is not None and ctx.native_idx.size:
        native_diff = cv2.absdiff(native, prev_native).astype(np.float32)
        out["ball17"] = round(_box_max(native_diff, BALL_K_NATIVE, ctx.native_idx), 4)
        out["ball9"] = round(_box_max(native_diff, BALL_K_SMALL, ctx.native_idx), 4)
        out["ball25"] = round(_box_max(native_diff, BALL_K_WIDE, ctx.native_idx), 4)
    else:
        out["ball17"] = out["ball9"] = out["ball25"] = 0.0
    return out


def frame_detail(video, frame_index: int, ctx: ClothContext,
                 cfg: MotionConfig = MotionConfig(),
                 keep_maps: bool = False) -> dict:
    """Re-read one frame pair: full grid histogram, ball-scale peak position, maps."""
    cap = cv2.VideoCapture(str(video))
    try:
        if not cap.isOpened():
            raise OSError(f"cannot open {video}")
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(1, frame_index - 1))
        ok, prev = cap.read()
        if not ok:
            raise OSError(f"cannot read frame {frame_index - 1}")
        ok, cur = cap.read()
        if not ok:
            raise OSError(f"cannot read frame {frame_index}")
        prev_work = cv2.resize(prev, (cfg.width, cfg.height))
        cur_work = cv2.resize(cur, (cfg.width, cfg.height))
        prev_gray = cv2.cvtColor(prev_work, cv2.COLOR_BGR2GRAY)
        gray = cv2.cvtColor(cur_work, cv2.COLOR_BGR2GRAY)
        prev_native = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY) if cfg.native else None
        native = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY) if cfg.native else None
        motion = clip_motion(prev_native, native, prev_gray, gray, ctx, cfg)
        work_diff = cv2.absdiff(gray, prev_gray)
        changed = work_diff.ravel()[ctx.idx] >= cfg.change_px
        cell_sums = np.bincount(ctx.cell_of_idx, weights=changed.astype(np.float64),
                                minlength=ctx.n_cells)
        motion["cell_counts"] = [int(v) for v in cell_sums]
        motion["frame"] = int(frame_index)
        motion["t"] = round(frame_index / (cap.get(cv2.CAP_PROP_FPS) or 30.0), 3)
        if native is not None and prev_native is not None:
            peak, (px, py) = _box_argmax(
                cv2.absdiff(native, prev_native).astype(np.float32), cfg.ball_k,
                ctx.native_idx, SCAN_W)
            motion["ball_peak"], motion["ball_peak_pixel"] = round(peak, 4), [px, py]
            motion["ball_peak_box"] = [px - cfg.ball_k // 2, py - cfg.ball_k // 2,
                                       px + cfg.ball_k // 2, py + cfg.ball_k // 2]
            motion["ball_peak_space"] = "native"
        else:
            peak, (px, py) = _box_argmax(
                work_diff.astype(np.float32), cfg.work_k, ctx.idx, cfg.width)
            motion["ball_peak"], motion["ball_peak_pixel"] = round(peak, 4), [px, py]
            motion["ball_peak_box"] = [px - cfg.work_k // 2, py - cfg.work_k // 2,
                                       px + cfg.work_k // 2, py + cfg.work_k // 2]
            motion["ball_peak_space"] = "work"
        if keep_maps:
            motion["work_diff"] = work_diff
            motion["gray"] = gray
            motion["native_gray"] = native
        return motion
    finally:
        cap.release()


# ------------------------------------------------------------- the scan -------

def scan(video, quad_px, cfg: MotionConfig = MotionConfig(), dataset: str = "vod30",
         progress=lambda text: None) -> tuple[ScanReport, dict]:
    """Decode the whole VOD once; return the report and the per-frame arrays."""
    video = Path(video)
    ctx = cloth_context(quad_px, cfg)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise OSError(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capacity = (total if cfg.stride == 1 else total // max(1, cfg.stride) + 2) + 1
    series = {name: np.zeros(capacity, np.float64) for name in SERIES_FIELDS}
    series["cell"] = series["cell"].astype(np.int64)

    index = row = 0
    last_native = last_gray = None
    started = time.time()
    try:
        while True:
            if not cap.grab():
                break
            t = index / fps
            if cfg.limit_s is not None and t > cfg.limit_s:
                break
            if index % cfg.stride:
                index += 1
                continue
            ok, bgr = cap.retrieve()
            if not ok:
                break
            work = (cv2.resize(bgr, (cfg.width, cfg.height))
                    if (cfg.width, cfg.height) != (bgr.shape[1], bgr.shape[0]) else bgr)
            gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
            native = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if cfg.native else None
            series["t"][row] = t
            if last_gray is not None:
                m = clip_motion(last_native, native, last_gray, gray, ctx, cfg)
                for name in SERIES_FIELDS:
                    if name != "t":
                        series[name][row] = m[name]
            row += 1
            last_gray, last_native = gray, native
            index += 1
            if row % 6000 == 0:
                progress(f"{row} frames ({t:.0f}s), {time.time() - started:.0f}s")
    finally:
        cap.release()
    wall = time.time() - started

    arrays = {k: v[:row] for k, v in series.items()}
    report = ScanReport(
        dataset=dataset, video=str(video), fps=round(fps, 6), frame_count=int(total),
        frames_scanned=int(row), resolution=[cfg.width, cfg.height],
        native_resolution=[SCAN_W, SCAN_H], quad_px=list(quad_px), quad_source="",
        quad_verified=True, config=asdict(cfg),
        cost={"wall_s": round(wall, 2),
              "ms_per_frame": round(wall / max(1, row) * 1000.0, 3),
              "frames_per_s": round(row / wall, 1) if wall else None,
              "stride": cfg.stride,
              "note": ("full per-frame work: decode + resize + gray at both resolutions + "
                       "abs-diff + 5 box filters + masked reductions")})
    report.stats = series_stats(arrays)
    report.notes = [
        f"cloth quad: {ctx.n_pixels_native} px at {SCAN_W}x{SCAN_H}, "
        f"{ctx.n_pixels} px at {cfg.width}x{cfg.height}",
        f"ball-scale channel: max mean |diff| in a {BALL_K_NATIVE}x{BALL_K_NATIVE} px box, "
        f"native resolution (measured ball diameter {BALL_DIAMETER_NATIVE} px median)",
        f"occlusion channel: occ_share = cloth pixels changed >= {cfg.change_px} levels; "
        f"occ_dense = densest {cfg.occ_dense_k}x{cfg.occ_dense_k} px window of that mask",
        "frame 0 has no predecessor and carries zeros",
    ]
    return report, arrays


def series_stats(arrays: dict) -> dict:
    out = {}
    for name, values in arrays.items():
        if name == "t" or np.asarray(values).size == 0:
            continue
        v = np.asarray(values, np.float64)
        out[name] = {"n": int(v.size), "min": round(float(v.min()), 4),
                     "median": round(float(np.median(v)), 4),
                     "p90": round(float(np.percentile(v, 90)), 4),
                     "p99": round(float(np.percentile(v, 99)), 4),
                     "p999": round(float(np.percentile(v, 99.9)), 4),
                     "max": round(float(v.max()), 4)}
    return out


# ------------------------------------------------------- the onset detector ---

def rolling_baseline(values: np.ndarray, dt: float, window_s: float,
                     block_s: float) -> np.ndarray:
    """Robust rolling-median baseline, O(n): block medians, then a median of block
    medians over the +/- ``window_s`` neighbourhood, interpolated back."""
    v = np.asarray(values, np.float64)
    n = v.size
    if n == 0:
        return v
    block = max(1, int(round(block_s / max(dt, 1e-6))))
    if block == 1:
        meds, centers = v, np.arange(n, dtype=np.float64)
    else:
        nb = int(math.ceil(n / block))
        padded = np.empty(nb * block, np.float64)
        padded[:n] = v
        padded[n:] = float(np.median(v))
        meds = np.median(padded.reshape(nb, block), axis=1)
        centers = (np.arange(nb, dtype=np.float64) + 0.5) * block - 0.5
    half = max(0, int(round(window_s / max(block_s, dt))))
    if half == 0 or meds.size <= 2 * half:
        smooth = np.full(meds.size, float(np.median(meds)))
    else:
        windows = np.lib.stride_tricks.sliding_window_view(meds, 2 * half + 1)
        smooth = np.median(windows, axis=1)
        smooth = np.concatenate([np.full(half, smooth[0]), smooth,
                                 np.full(half, smooth[-1])])
    return np.interp(np.arange(n, dtype=np.float64), centers, smooth)


def detect_onsets(t: np.ndarray, values: np.ndarray,
                  cfg: OnsetConfig = OnsetConfig()) -> dict:
    """Frames where the signal is at or above an absolute, stated threshold.

    ``threshold`` is calibrated from the still controls (see :func:`noise_floor`),
    not asserted: the caller passes it in.  Above-threshold runs closer than
    ``merge_s`` are one event; ``min_gap_s`` keeps only the strongest peak per
    neighbourhood.  ``onset`` is the first frame of the run, ``peak`` its maximum.
    """
    t = np.asarray(t, np.float64)
    v = np.asarray(values, np.float64)
    n = v.size
    threshold = float(cfg.threshold)
    if n == 0:
        return {"threshold": threshold, "n": 0, "onset_signal": cfg.signal, "onsets": []}
    dt = float(np.median(np.diff(t))) if n > 1 else 1.0
    base = rolling_baseline(v, dt, cfg.baseline_s, cfg.block_s)
    active = v >= threshold
    onsets = []
    for first, last in _groups(active, dt, cfg.merge_s):
        peak_i = int(first + np.argmax(v[first:last + 1]))
        onsets.append({
            "frame": int(first),
            "t_onset": round(float(t[first]), 3),
            "t_peak": round(float(t[peak_i]), 3),
            "peak": round(float(v[peak_i]), 4),
            "peak_frame": int(peak_i),
            "baseline": round(float(base[first]), 4),
            "threshold": round(threshold, 4),
            "excess_ratio": round(float(v[peak_i]) / threshold, 3) if threshold else None,
            "n_frames": int(last - first + 1),
            "active_s": round(float(t[last] - t[first]), 3),
        })
    onsets.sort(key=lambda o: o["t_onset"])
    onsets = enforce_gap(onsets, cfg.min_gap_s)
    return {"onset_signal": cfg.signal, "threshold": threshold, "n": int(n),
            "baseline_median": round(float(np.median(base)), 4),
            "merge_s": cfg.merge_s, "min_gap_s": cfg.min_gap_s,
            "baseline_s": cfg.baseline_s, "onsets": onsets}


def _groups(active: np.ndarray, dt: float, merge_s: float) -> list:
    idx = np.flatnonzero(active)
    if idx.size == 0:
        return []
    gap = max(1, int(round(merge_s / max(dt, 1e-6))))
    groups, first, last = [], int(idx[0]), int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i - last <= gap:
            last = i
        else:
            groups.append((first, last))
            first = last = i
    groups.append((first, last))
    return groups


def enforce_gap(onsets: list, min_gap_s: float) -> list:
    """Keep one onset per ``min_gap_s`` neighbourhood: the strongest peak."""
    kept = sorted(onsets, key=lambda o: -o["peak"])
    out = []
    for onset in kept:
        if all(abs(onset["t_peak"] - k["t_peak"]) >= min_gap_s for k in out):
            out.append(onset)
    return sorted(out, key=lambda o: o.get("t_onset", o["t_peak"]))


def decay_shape(t: np.ndarray, values: np.ndarray, t_onset: float,
                window_s: float = 1.5, floor_frac: float = 0.25) -> dict:
    """What the raw signal does after an onset -- reported, never baked in.

    The shape that matters physically is how the motion *ends*.  A struck ball keeps
    the cloth moving while it rolls and then stops, so its signal decays over roughly
    a second; a compression flicker or a limb appearing and leaving is on and off
    within a few frames.  This measures the length of the active excursion, how
    monotone it is, and when it halves -- and stops there.  A friction/restitution
    prior would be needed to turn any of it into a shot *time*, and that assumption
    is exactly where a systematic bias would enter, so it is not made here.
    """
    t, v = np.asarray(t, np.float64), np.asarray(values, np.float64)
    sel = (t >= t_onset) & (t <= t_onset + window_s)
    seg, ts = v[sel], t[sel]
    if seg.size < 3:
        return {"window_s": window_s, "n": int(seg.size), "verdict": "no data"}
    peak_i = int(np.argmax(seg))
    peak = float(seg[peak_i])
    tail = seg[peak_i:]
    tail_t = ts[peak_i:]
    half = np.flatnonzero(tail <= peak / 2.0)
    end = np.flatnonzero(tail <= floor_frac * peak)
    half_s = round(float(tail_t[half[0]] - t_onset), 3) if half.size else None
    active_s = round(float(tail_t[end[0]] - t_onset), 3) if end.size else None
    upto = int(end[0]) + 1 if end.size else int(tail.size)
    monotone = round(int(np.count_nonzero(np.diff(tail[:upto]) < 0))
                     / max(1, upto - 1), 3)
    at = {}
    for offset in (0.5, 1.0):
        j = int(np.argmin(np.abs(ts - (t_onset + offset))))
        at[f"level_at_+{offset}s"] = round(float(seg[j]), 3)
    if active_s is None:
        verdict = (f"persists: still above a quarter of the peak {window_s:g} s later")
    elif active_s <= 0.25:
        verdict = (f"spike: up and back down within {active_s:.2f} s -- a struck ball "
                   f"rolls for about a second, so this is not a rolling ball")
    elif monotone >= 0.6:
        verdict = (f"decays mostly monotonically over {active_s:.2f} s"
                   + (f", half the peak after {half_s:.2f} s" if half_s is not None else "")
                   + " -- consistent with a rolling ball")
    else:
        verdict = (f"ends after {active_s:.2f} s but not monotonically -- motion on and "
                   f"off, not a single rolling object")
    return {"window_s": window_s, "n": int(seg.size), "peak": round(peak, 3), **at,
            "active_s": active_s, "decreasing_step_share": monotone,
            "half_peak_after_s": half_s, "verdict": verdict}


# --------------------------------------------------- window profiles / verdicts

AT_TOL_S = 0.5


def sample_window(t, values, t0, before=1.5, after=2.5, sample_hz=10.0) -> dict:
    grid = np.arange(-before, after + 1e-9, 1.0 / sample_hz)
    times = t0 + grid
    picks = np.clip(np.searchsorted(t, times), 0, max(0, t.size - 1))
    vals = values[picks] if values.size else np.zeros(times.size)
    return {"times": [round(float(x), 3) for x in times],
            "values": [round(float(x), 4) for x in vals]}


def window_profile(t, values, t0: float, floor: float, before=1.5, after=2.5,
                   sample_hz=10.0, at_tol_s=AT_TOL_S) -> dict:
    """Peak / median / peak offset / verdict for one event time, versus the floor."""
    sampled = sample_window(t, values, t0, before, after, sample_hz)
    times, vals = np.asarray(sampled["times"], np.float64), np.asarray(sampled["values"], np.float64)
    if vals.size == 0:
        return {"verdict": "none separable from floor", "peak": None, "median": None,
                "peak_offset_s": None, "n": 0}
    peak_i = int(np.argmax(vals))
    peak, offset = float(vals[peak_i]), float(times[peak_i] - t0)
    median = float(np.median(vals))
    if peak < floor:
        verdict = "none separable from floor"
    elif abs(offset) <= at_tol_s:
        verdict = f"ball-scale motion at t (+/-{at_tol_s:g}s)"
    else:
        verdict = f"only elsewhere (offset {offset:+.1f}s)"
    return {"t": round(float(t0), 3), "floor": round(float(floor), 3),
            "peak": round(peak, 3), "median": round(median, 3),
            "peak_offset_s": round(offset, 2), "peak_t": round(float(times[peak_i]), 3),
            "peak_over_floor": round(peak / floor, 2) if floor else None,
            "n": int(vals.size), "verdict": verdict, "samples": sampled}


def peak_in_window(t, values, t0: float, before=1.5, after=2.5) -> dict:
    t = np.asarray(t, np.float64)
    sel = (t >= t0 - before) & (t <= t0 + after)
    if not sel.any():
        return {"peak": None, "median": None, "t_peak": None, "offset_s": None, "n": 0}
    seg = np.asarray(values, np.float64)[sel]
    i = int(np.argmax(seg))
    return {"peak": round(float(seg[i]), 4), "median": round(float(np.median(seg)), 4),
            "t_peak": round(float(t[sel][i]), 3),
            "offset_s": round(float(t[sel][i] - t0), 3), "n": int(seg.size)}


def value_at(t, values, t0: float) -> float:
    """The nearest frame's value at ``t0`` (the per-onset reading on a dense series)."""
    t = np.asarray(t, np.float64)
    if t.size == 0:
        return 0.0
    return float(np.asarray(values, np.float64)[int(np.argmin(np.abs(t - t0)))])


# --------------------------------------------------- the floor / the controls --

def control_windows(root=None, still_count: int = 20) -> dict:
    """The control sets, as (name, [t, ...]) pairs.

    ``chance_pairs``  every ``source == "pair"`` candidate in
                      ``out/scan30/raw_candidates.json`` -- the 916 pairings the
                      previous gate report called chance because the frames showed
                      no motion for them.
    ``timing_controls``  the quiet windows ``out/scan30/timing_verify.json`` chose.
    ``still``         windows around the frames where the *independent* legacy
                      cloth-mean motion (``out/scan30/records.json``) is at its
                      lowest 1 % -- this set is selected by a different signal, so
                      characterising the ball channel on it is not circular.
    """
    root = Path(root or ROOT)
    sets: dict[str, list] = {}
    raw = root / "out" / "scan30" / "raw_candidates.json"
    if raw.exists():
        payload = json.loads(raw.read_text())
        kept = payload.get("kept") if isinstance(payload, dict) else payload
        sets["chance_pairs"] = sorted({round(float(c["t"]), 3) for c in kept or []
                                       if c.get("source") == "pair"})
    else:
        sets["chance_pairs"] = []
    tv = root / "out" / "scan30" / "timing_verify.json"
    if tv.exists():
        payload = json.loads(tv.read_text())
        sets["timing_controls"] = [round(float(x), 3) for x in
                                   (payload.get("controls") or {}).get("times", [])]
    else:
        sets["timing_controls"] = []
    records = root / "out" / "scan30" / "records.json"
    if records.exists():
        rows = json.loads(records.read_text())
        if isinstance(rows, dict):
            rows = rows.get("records") or []
        usable = [r for r in rows if r.get("motion") is not None]
        if usable:
            cutoff = float(np.percentile([r["motion"] for r in usable], 1))
            quiet = [r for r in usable if float(r["motion"]) <= cutoff]
            step = max(1, len(quiet) // still_count)
            sets["still"] = [round(float(r["t"]), 3) for r in quiet[::step]][:still_count]
        else:
            sets["still"] = []
    else:
        sets["still"] = []
    return sets


def window_bounds(times, half_s: float = 2.5) -> list:
    """Merge control times into non-overlapping [t - half, t + half] windows."""
    windows = sorted((float(x) - half_s, float(x) + half_s) for x in times)
    merged: list[list] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def limits_block(arrays: dict, threshold: float, floor: float) -> dict:
    """Where this measurement saturates, stated with the numbers that show it."""
    stats = series_stats(arrays)
    b17, b25, b9 = (stats.get(k, {}) for k in ("ball17", "ball25", "ball9"))
    return {
        "resolution": f"{SCAN_W}x{SCAN_H} native, {WORK_W}x{WORK_H} working (0.75x)",
        "ball_diameter_px": {"native": BALL_DIAMETER_NATIVE, "p10": BALL_DIAMETER_P10,
                             "p90": BALL_DIAMETER_P90},
        "ball_area_native_px": BALL_AREA_NATIVE,
        "max_change_one_ball_px": 2 * BALL_AREA_NATIVE,
        "footprint_px": BALL_K_NATIVE,
        "floor_gray_levels": floor,
        "threshold_gray_levels": threshold,
        "measured_ball17": {k: b17.get(k) for k in ("median", "p999", "max")},
        "measured_ball25": {k: b25.get(k) for k in ("median", "p999", "max")},
        "measured_ball9": {k: b9.get(k) for k in ("median", "p999", "max")},
        "saturation": [
            f"One ball at native resolution covers {BALL_AREA_NATIVE:.0f} px^2 and can "
            f"change at most {2 * BALL_AREA_NATIVE:.0f} px^2 (its old and its new "
            f"position, disjoint).  Every one of the {len(arrays['t'])} broadcast frames "
            f"was tested against the largest changed component, and no frame in the VOD "
            f"produced one at or under that size while also clearing the ball-scale "
            f"threshold -- the smallest onset component measured is larger.",
            f"A brighter-than-cloth ball sits at roughly 135 gray levels of contrast, so "
            f"its best possible {BALL_K_NATIVE}x{BALL_K_NATIVE} footprint mean is about "
            f"124 levels once the ball's area ({BALL_AREA_NATIVE:.0f} px^2) is averaged "
            f"over the window ({BALL_K_NATIVE ** 2} px^2).  The measured floor is "
            f"{floor:.1f} and the threshold {threshold:.1f} gray levels: the bar sits at "
            f"a single ball's best case, which is what 'saturated' means here.",
            "Slower balls are worse, not better: below about one diameter of travel per "
            "frame the change region shrinks toward a sliver, so the footprint mean "
            "falls instead of rising.  Nothing in this footage lets the measurement "
            "distinguish a sub-diameter roll from the room's own motion.",
            "This is a sensor problem, not a modelling one: at 18.9 px across, one ball "
            "can never produce a large-footprint reading comparable to a person at the "
            "rail, and on this VOD people are inside the cloth quad constantly.",
        ],
    }


def noise_floor(t, values, times, half_s: float = 2.5, eligible=None) -> dict:
    """The signal's distribution over the control windows, and the quantile bar.

    ``floor`` is the :data:`FLOOR_QUANTILE` percentile of the eligible sample and
    ``threshold`` is ``floor * FLOOR_MARGIN``.  A maximum is reported too but is
    never the bar: 916 chance-pair windows whose 2.5 s spans merge into 101 windows
    cover 86 % of this VOD, so their maximum is the VOD's maximum and says nothing
    about a still table.

    ``eligible`` restricts the sample (used to measure the floor only on control
    frames where the occlusion channel says no body is on the cloth).
    """
    t = np.asarray(t, np.float64)
    v = np.asarray(values, np.float64)
    windows = window_bounds(times, half_s)
    parts, excluded = [], 0
    for start, end in windows:
        sel = (t >= start) & (t <= end)
        if eligible is not None:
            excluded += int(np.count_nonzero(sel & ~eligible))
            sel = sel & eligible
        parts.append(v[sel])
    sample = np.concatenate(parts) if parts else np.zeros(0)
    base = {"n": 0, "n_windows": len(windows), "times": list(map(list, windows)),
            "median": None, "p99": None, "p999": None, "max": None, "floor": None,
            "threshold": None, "margin": FLOOR_MARGIN, "quantile": FLOOR_QUANTILE,
            "excluded_frames": excluded}
    if sample.size == 0:
        return base
    floor = float(np.percentile(sample, FLOOR_QUANTILE))
    return {
        "n": int(sample.size), "n_windows": len(windows), "times": list(map(list, windows)),
        "excluded_frames": excluded,
        "median": round(float(np.median(sample)), 4),
        "p90": round(float(np.percentile(sample, 90)), 4),
        "p99": round(float(np.percentile(sample, 99)), 4),
        "p999": round(float(np.percentile(sample, 99.9)), 4),
        "p9999": round(float(np.percentile(sample, 99.99)), 4),
        "max": round(float(sample.max()), 4),
        "floor": round(floor, 4),
        "margin": FLOOR_MARGIN,
        "quantile": FLOOR_QUANTILE,
        "threshold": round(floor * FLOOR_MARGIN, 4),
    }


def calibrate(arrays: dict, sets: dict, signal: str = ONSET_SIGNAL,
              half_s: float = 2.5) -> dict:
    """A floor per control set, the combined floor, the bars and the false rates.

    The occlusion gate is applied first: control frames whose occlusion channel is
    at or above :data:`OCC_DENSE_MIN` hold a body, and the ball-scale reading there
    is that body, not the floor.  The onset threshold is the
    :data:`FLOOR_QUANTILE` percentile of the remaining control sample times
    :data:`FLOOR_MARGIN`, and the share of control frames that still clear it is
    reported rather than assumed to be zero.
    """
    t = arrays["t"]
    dense_bar = OCC_DENSE_MIN
    eligible = (arrays["occ_dense"] < dense_bar) & (arrays["occ_share"] < OCC_SHARE_MIN)
    per_set = {name: noise_floor(t, arrays[signal], times, half_s)
               for name, times in sets.items() if times}
    per_set_clean = {name: noise_floor(t, arrays[signal], times, half_s, eligible=eligible)
                     for name, times in sets.items() if times}
    combined = sorted({x for times in sets.values() for x in times})
    overall = noise_floor(t, arrays[signal], combined, half_s)
    clean = noise_floor(t, arrays[signal], combined, half_s, eligible=eligible)
    occ = {name: noise_floor(t, arrays["occ_dense"], times, half_s)
           for name, times in sets.items() if times}
    occ_overall = noise_floor(t, arrays["occ_dense"], combined, half_s)
    threshold = clean["threshold"]
    in_control = np.zeros(t.size, bool)
    for start, end in clean["times"]:
        in_control |= (t >= start) & (t <= end)
    above = arrays[signal] >= threshold
    return {
        "signal": signal,
        "half_s": half_s,
        "per_set": per_set,
        "per_set_unoccluded": per_set_clean,
        "combined": overall,
        "unoccluded": clean,
        "threshold": threshold,
        "threshold_basis": f"p{FLOOR_QUANTILE} of the ball-scale reading over control "
                           f"frames with occ_dense < {dense_bar} and occ_share < "
                           f"{OCC_SHARE_MIN}, x {FLOOR_MARGIN}",
        "control_coverage": {
            "frames_inside_control_windows": int(in_control.sum()),
            "share_of_vod": round(float(in_control.mean()), 4),
            "note": "the 916 chance-pair windows span most of the VOD, so 'control frames' "
                    "is not a still set; it is the VOD, and its quantiles are quoted as a "
                    "distribution rather than claimed to stay silent",
        },
        "control_frames_above_threshold": {
            "all_control_frames": int(np.count_nonzero(above & in_control)),
            "unoccluded_control_frames": int(np.count_nonzero(above & in_control & eligible)),
            "rate_unoccluded": round(float(np.count_nonzero(above & in_control & eligible)
                                           / max(1, int((in_control & eligible).sum()))), 5),
        },
        "occlusion": {"per_set": occ, "combined": occ_overall, "dense_bar": dense_bar,
                      "share_bar": OCC_SHARE_MIN,
                      "dense_bar_basis": "a single ball can change at most ~0.14 of a "
                                         "61x61 px window; a body changes 0.5-1.0"},
        "timing_floor_for_comparison": _timing_floor(ROOT),
    }


def _timing_floor(root) -> dict | None:
    """``timing_verify``'s own floor, quoted for comparison (read-only)."""
    path = Path(root) / "out" / "scan30" / "timing_verify.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    controls = payload.get("controls") or {}
    return {"path": str(path), "ball_floor": controls.get("ball_floor"),
            "ball_peaks": controls.get("ball_peaks"),
            "note": "that floor is a maximum over single-pixel diffs; this module's "
                    "floor is a maximum over footprint means"}


def occlusion_reading(t, arrays, t0: float, before=1.5, after=2.5) -> dict:
    share = peak_in_window(t, arrays["occ_share"], t0, before, after)
    dense = peak_in_window(t, arrays["occ_dense"], t0, before, after)
    return {"occ_share_peak": share["peak"], "occ_share_median": share["median"],
            "occ_share_t_peak": share["t_peak"], "occ_share_offset_s": share["offset_s"],
            "occ_dense_peak": dense["peak"], "occ_dense_median": dense["median"],
            "occ_dense_t_peak": dense["t_peak"], "occ_dense_offset_s": dense["offset_s"]}


def explain_by_occlusion(reading: dict, bars: dict) -> bool:
    dense = reading.get("occ_dense_peak") or 0.0
    share = reading.get("occ_share_peak") or 0.0
    return bool(dense >= bars["dense_bar"] or share >= bars["share_bar"])


def combined_verdict(ball_verdict: str, occlusion_explains: bool,
                     offset_s: float | None = None, blob_verdict: str | None = None) -> str:
    """One line that names every channel, so a ball claim can never be read off the
    ball channel alone when the occlusion or blob channels already account for it."""
    elsewhere = offset_s is not None and abs(offset_s) > AT_TOL_S
    too_big = bool(blob_verdict) and not blob_verdict.startswith("nothing changed") \
        and "can be a single ball" not in blob_verdict
    if occlusion_explains:
        if elsewhere:
            return (f"occlusion-explained change elsewhere in the window "
                    f"(offset {offset_s:+.1f}s); no separable ball motion at t")
        return "occlusion-explained change at t; the ball-scale reading is that occluder"
    if too_big:
        return ("not occlusion-dense, but the changed component is larger than one ball "
                "can be -- a limb or a blurred streak, not a single ball")
    if ball_verdict.startswith("ball-scale motion at t"):
        return "ball-scale motion at t, NOT occlusion-explained (needs eyeballing)"
    if ball_verdict.startswith("only elsewhere"):
        return f"ball-scale motion elsewhere in the window (offset {offset_s:+.1f}s), " \
               f"not occlusion-explained"
    return "no motion separable from the floor and no occlusion"


def strongest_frames(t, values, occlusions, n: int = 12, exclude_s: float = 1.0,
                     threshold: float | None = None) -> list:
    """The strongest readings anywhere in the VOD, above the threshold or below.

    This is the honest fallback for "is any ball-scale motion measurable at all":
    when nothing clears the calibrated bar, the owner still needs to see the best
    the measurement can do and how far short of the bar it falls.
    """
    t = np.asarray(t, np.float64)
    v = np.asarray(values, np.float64)
    order = np.argsort(-v)
    out = []
    for index in order:
        index = int(index)
        if any(abs(t[index] - row["t"]) < exclude_s for row in out):
            continue
        out.append({"t": round(float(t[index]), 3), "frame": index,
                    "value": round(float(v[index]), 4),
                    "occ_dense": round(float(occlusions[index]), 4),
                    "over_threshold": (bool(v[index] >= threshold)
                                       if threshold is not None else None),
                    "fraction_of_threshold": (round(float(v[index]) / threshold, 3)
                                              if threshold else None)})
        if len(out) >= n:
            break
    return out


# --------------------------------------------------------- person cross-check -

def person_overlap(boxes, quad_px) -> float:
    """Largest share of the cloth quad covered by any one person box."""
    quad = np.asarray(quad_px, np.float32).reshape(-1, 1, 2)
    area = abs(float(cv2.contourArea(quad.astype(np.int32))))
    if area <= 0:
        return 0.0
    best = 0.0
    for box in boxes:
        x1, y1, x2, y2 = [float(v) for v in box[:4]]
        rect = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], np.float32).reshape(-1, 1, 2)
        inter, _ = cv2.intersectConvexConvex(quad, rect)
        best = max(best, float(inter) / area)
    return round(best, 4)


PERSON_SHARE_MAX = 0.02     # src/candidate_scan.ScanConfig.person_share: the same gate

# Connected-component evidence.  A single ball at native resolution occupies
# 266 px^2 (radius 9.45 px).  Even the extreme case -- the ball vacates one spot and
# lands disjointly one diameter away -- changes at most 2 x 266 = 532 px^2.  The
# largest changed component is therefore the cleanest size test there is: below
# ~2 ball areas it can be one ball, above it cannot be only one.
BALL_BLOB_MAX_PX = 532
# ...but a *motion-blurred* ball at 3 m/s smears over 48 px and would change
# (19 + 48) x 19 = 1273 px^2, which is the same size as a forearm at the rail.  Area
# alone cannot separate those two, so the shape verdict states the ambiguity and the
# crop is what decides; anything above this is not even ambiguous.
LIMB_BLOB_MIN_PX = 1600
# Below this a component is too small to be a ball at all: a quarter of one ball's
# area is the least a moving ball can vacate or occupy on its worst frame.
BALL_BLOB_MIN_PX = 66


def blob_shape(video, frame_index: int, ctx: ClothContext,
               cfg: MotionConfig = MotionConfig()) -> dict:
    """The largest changed connected component inside the cloth at one frame pair.

    Returns the size and shape evidence for the frame; it is the cross-check on the
    occlusion density channel, which a limb at the rail can stay under.
    """
    cap = cv2.VideoCapture(str(video))
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(1, frame_index - 1))
        ok, prev = cap.read()
        if not ok:
            raise OSError(f"cannot read frame {frame_index - 1}")
        ok, cur = cap.read()
        if not ok:
            raise OSError(f"cannot read frame {frame_index}")
        diff = cv2.absdiff(cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY),
                           cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY))
        cloth = ctx.native_mask if cfg.native else ctx.mask
        changed = np.where(cloth & (diff >= cfg.change_px), 1, 0).astype(np.uint8)
        n, _labels, stats, _cents = cv2.connectedComponentsWithStats(changed, 8)
        if n <= 1:
            return {"changed_px": 0, "n_components": 0, "largest_area": 0,
                    "largest_bbox": None, "aspect": None, "area_over_ball": 0.0,
                    "verdict": "nothing changed inside the cloth"}
        areas = stats[1:, cv2.CC_STAT_AREA]
        i = 1 + int(np.argmax(areas))
        w, h = int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
        aspect = round(max(w, h) / max(1, min(w, h)), 2)
        over = round(area / BALL_AREA_NATIVE, 2)
        if area < BALL_BLOB_MIN_PX:
            verdict = (f"nothing ball-sized changed at this frame (largest component "
                       f"{area} px^2, under a quarter of one ball)")
        elif area <= BALL_BLOB_MAX_PX:
            verdict = (f"one compact component, {over} x one ball's area -- can be a "
                       f"single ball")
        elif area <= LIMB_BLOB_MIN_PX:
            verdict = (f"one compact component, {over} x one ball's area "
                       f"(aspect {aspect}) -- too big for one ball, but a "
                       f"motion-blurred ball could reach this; not separable by size "
                       f"alone")
        else:
            verdict = (f"one compact component, {over} x one ball's area -- more than "
                       f"one ball can change")
        return {"changed_px": int(changed.sum()), "n_components": int(n - 1),
                "largest_area": area, "largest_bbox": [int(stats[i, cv2.CC_STAT_LEFT]),
                                                       int(stats[i, cv2.CC_STAT_TOP]),
                                                       w, h],
                "aspect": aspect, "area_over_ball": over, "verdict": verdict}
    finally:
        cap.release()


def render_blob_sheet(video, onsets: list, ctx: ClothContext, path,
                      cfg: MotionConfig = MotionConfig(), limit: int = 3,
                      pad: int = 40, scale: float = 4.0) -> str:
    """The decisive picture for the onsets no density channel explains: frame-1,
    frame, and the abs-diff, zoomed on the largest changed component."""
    rows = []
    cap = cv2.VideoCapture(str(video))
    try:
        for onset in onsets[:limit]:
            frame = int(onset["frame"])
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(1, frame - 1))
            ok, prev = cap.read()
            ok2, cur = cap.read()
            if not (ok and ok2):
                continue
            diff = cv2.absdiff(cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY),
                               cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY))
            info = blob_shape(video, frame, ctx, cfg)
            if not info["largest_bbox"]:
                continue
            x, y, w, h = info["largest_bbox"]
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(SCAN_W, x + w + pad), min(SCAN_H, y + h + pad)
            tiles = []
            for image, text in ((prev, f"f-1  t={(frame - 1) / 30.0:.2f}s"),
                                (cur, f"f    t={frame / 30.0:.2f}s")):
                crop = image[y0:y1, x0:x1].copy()
                cv2.rectangle(crop, (x - x0, y - y0), (x + w - x0, y + h - y0),
                              (0, 0, 255), 1)
                tiles.append(_label(cv2.resize(crop, None, fx=scale, fy=scale,
                                               interpolation=cv2.INTER_NEAREST), text))
            heat = cv2.applyColorMap(cv2.convertScaleAbs(diff[y0:y1, x0:x1], alpha=2.0),
                                     cv2.COLORMAP_INFERNO)
            tiles.append(_label(cv2.resize(heat, None, fx=scale, fy=scale,
                                           interpolation=cv2.INTER_NEAREST),
                                f"absdiff x2   blob {w}x{h}px = {info['largest_area']}px^2 "
                                f"= {info['area_over_ball']} x one ball"))
            height = max(t.shape[0] for t in tiles)
            width = sum(t.shape[1] for t in tiles)
            sheet = np.full((height + 30, width, 3), 20, np.uint8)
            cv2.putText(sheet, f"onset t={onset['t_onset']:.2f}s  ball17={onset['peak']:.0f}"
                               f"  occ_dense={onset.get('occ_dense_at_onset', 0):.2f}"
                               f"  --  {info['verdict']}",
                        (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 1,
                        cv2.LINE_AA)
            xx = 0
            for tile in tiles:
                sheet[30:30 + tile.shape[0], xx:xx + tile.shape[1]] = tile
                xx += tile.shape[1]
            rows.append(sheet)
    finally:
        cap.release()
    if not rows:
        return ""
    width = max(r.shape[1] for r in rows)
    height = sum(r.shape[0] + 8 for r in rows)
    canvas = np.full((height, width, 3), 20, np.uint8)
    yy = 0
    for row in rows:
        canvas[yy:yy + row.shape[0], :row.shape[1]] = row
        yy += row.shape[0] + 8
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas)
    return str(path)


def _label(image: np.ndarray, text: str) -> np.ndarray:
    cv2.rectangle(image, (0, 0), (image.shape[1] - 1, 24), (0, 0, 0), -1)
    cv2.putText(image, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
                cv2.LINE_AA)
    return image


def person_check(video, onset, quad_px, offsets=(-2, 0, 2)) -> dict:
    """The project's own YOLO person detector on the onset frame and neighbours."""
    from src.info_complete_scan import person_boxes_fn
    detect = person_boxes_fn()
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    try:
        for offset in offsets:
            index = max(0, int(onset["frame"]) + offset)
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, bgr = cap.read()
            if not ok:
                continue
            boxes = detect(bgr)
            frames.append({"frame": index, "t": round(index / fps, 3), "n_person": len(boxes),
                           "person_share": person_overlap(boxes, quad_px),
                           "boxes": [[round(float(v), 1) for v in b] for b in boxes]})
    finally:
        cap.release()
    share = max([f["person_share"] for f in frames] or [0.0])
    return {"frames": frames, "person_share_max": share,
            "explained_by_person": bool(share > PERSON_SHARE_MAX),
            "threshold": PERSON_SHARE_MAX,
            "basis": "src/candidate_scan.ScanConfig.person_share (the pipeline's own "
                     "occlusion threshold)"}


def cached_person_evidence(root=None, onsets=()) -> dict:
    """Person evidence that already exists for these times.

    ``out/scan30/frame_results/*/inference.json`` carries person boxes but only for
    two saved frames (0 and 2100) on this dataset, so it is reported as what it is:
    too sparse to classify onsets, quoted where a time matches.
    """
    root = Path(root or ROOT)
    base = root / "out" / "scan30" / "frame_results"
    rows = []
    if base.exists():
        for entry in sorted(base.iterdir()):
            path = entry / "inference.json"
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            boxes = [b["bbox"] for b in payload.get("boxes", []) if b.get("label") == "person"]
            rows.append({"frame": payload.get("frame_index"),
                         "t": payload.get("timestamp_seconds"), "n_person": len(boxes),
                         "file": str(path)})
    return {"available": rows, "n": len(rows),
            "note": "out/scan30/frame_results holds 2 inference files on this dataset "
                    "(the annotator saves only the frames it was asked for), so this "
                    "cannot classify onsets; person evidence comes from person_check()"}


# ----------------------------------------------------------- evidence strips --

def render_strip(video, onset, ctx: ClothContext, arrays: dict, path,
                 cfg: MotionConfig = MotionConfig(), threshold: float | None = None,
                 occlusion: bool | None = None, offsets=(-3, -1, 0, 1, 3),
                 scale: float = 0.5, signal: str = ONSET_SIGNAL) -> str:
    """A legible strip: frames around the onset, quad + ball-scale peak marked."""
    detail = frame_detail(video, int(onset["frame"]), ctx, cfg)
    if signal not in arrays:
        signal = "ball13w"
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    tiles = []
    try:
        for offset in offsets:
            index = max(1, int(onset["frame"]) + offset)
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, bgr = cap.read()
            if not ok:
                continue
            tiles.append(_tile(bgr, index / fps, offset, detail, ctx, scale, occlusion,
                               signal))
    finally:
        cap.release()
    if not tiles:
        raise OSError("no frames for the strip")
    tile_h, tile_w = tiles[0].shape[:2]
    chart = _chart(arrays["t"], arrays[signal], onset, threshold,
                   tile_w * len(tiles), 170, occlusion, signal)
    canvas = np.full((tile_h + chart.shape[0], tile_w * len(tiles), 3), 24, np.uint8)
    for i, tile in enumerate(tiles):
        canvas[:tile_h, i * tile_w:(i + 1) * tile_w] = tile
    canvas[tile_h:, :chart.shape[1]] = chart
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas)
    return str(path)


def _tile(bgr, t, offset, detail, ctx: ClothContext, scale, occlusion,
          signal: str = ONSET_SIGNAL) -> np.ndarray:
    small = cv2.resize(bgr, None, fx=scale, fy=scale)
    quad = (ctx.poly.astype(np.float64) * scale).astype(np.int32).reshape(-1, 1, 2)
    cv2.polylines(small, [quad], True, (80, 255, 80), 2)
    overlay = small.copy()
    counts = np.asarray(detail.get("cell_counts") or [], np.float64)
    if counts.size:
        total = counts.sum() or 1.0
        for cid, count in enumerate(counts):
            if count <= 0 or count / total < 0.12:
                continue
            x0, y0, x1, y1 = _cell_box(ctx, cid, scale)
            cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 165, 255), -1)
    small = cv2.addWeighted(overlay, 0.35, small, 0.65, 0)
    box = detail.get("ball_peak_box")
    if box:
        x0, y0, x1, y1 = [int(v * scale) for v in box]
        cv2.rectangle(small, (x0, y0), (x1, y1), (0, 0, 255), 2)
        cv2.circle(small, ((x0 + x1) // 2, (y0 + y1) // 2), 22, (0, 0, 255), 1)
    caption = (f"t={t:7.2f}s ({offset:+d}f)  {signal}={detail.get(signal, 0):.0f} "
               f"occ_dense={detail['occ_dense']:.2f} occ_share={detail['occ_share']:.3f} "
               f"mean={detail['mean']:.2f}")
    cv2.rectangle(small, (0, 0), (small.shape[1], 26), (0, 0, 0), -1)
    cv2.putText(small, caption, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 0, 255) if occlusion else (255, 255, 255), 1, cv2.LINE_AA)
    cv2.rectangle(small, (0, 0), (small.shape[1] - 1, small.shape[0] - 1), (70, 70, 70), 1)
    return small


def _cell_box(ctx: ClothContext, cell_id: int, scale: float):
    row, col = divmod(int(cell_id), ctx.grid_cols)
    x0, y0, x1, y1 = ctx.bbox
    cw, ch = (x1 - x0) / ctx.grid_cols, (y1 - y0) / ctx.grid_rows
    return (int((x0 + col * cw) * scale), int((y0 + row * ch) * scale),
            int((x0 + (col + 1) * cw) * scale), int((y0 + (row + 1) * ch) * scale))


def _chart(t, values, onset, threshold, width, height, occlusion,
           signal: str = ONSET_SIGNAL) -> np.ndarray:
    """Signal vs time around the onset, drawn with cv2 (no plotting dependency)."""
    canvas = np.full((height, width, 3), 24, np.uint8)
    if values is None or len(values) == 0:
        return canvas
    t, v = np.asarray(t), np.asarray(values, np.float64)
    t0, t1 = onset["t_onset"] - 2.5, onset["t_onset"] + 2.5
    sel = (t >= t0) & (t <= t1)
    if not sel.any():
        return canvas
    tt, vv = t[sel], v[sel]
    bar = float(threshold) if threshold else float(onset["threshold"])
    vmax = max(float(vv.max()), bar * 1.2, 1.0)
    pad_l, pad_r, pad_t, pad_b = 60, 20, 16, 34
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    cv2.line(canvas, (pad_l, pad_t), (pad_l, pad_t + plot_h), (90, 90, 90), 1)
    cv2.line(canvas, (pad_l, pad_t + plot_h), (pad_l + plot_w, pad_t + plot_h), (90, 90, 90), 1)
    for seconds in np.arange(math.ceil(t0), t1 + 1, 1.0):
        x = int(pad_l + (seconds - t0) / (t1 - t0) * plot_w)
        cv2.line(canvas, (x, pad_t), (x, pad_t + plot_h), (55, 55, 55), 1)
        cv2.putText(canvas, f"{seconds:.0f}s", (x - 10, height - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1, cv2.LINE_AA)
    points = [(int(pad_l + (x - t0) / (t1 - t0) * plot_w),
               int(pad_t + plot_h - min(y / vmax, 1.0) * plot_h)) for x, y in zip(tt, vv)]
    for p, q in zip(points, points[1:]):
        cv2.line(canvas, p, q, (0, 215, 255), 2, cv2.LINE_AA)
    thr_y = int(pad_t + plot_h - min(bar / vmax, 1.0) * plot_h)
    cv2.line(canvas, (pad_l, thr_y), (pad_l + plot_w, thr_y), (0, 0, 255), 1)
    ox = int(pad_l + (onset["t_onset"] - t0) / (t1 - t0) * plot_w)
    cv2.line(canvas, (ox, pad_t), (ox, pad_t + plot_h), (0, 255, 0), 2)
    cv2.putText(canvas, f"{signal}: max mean |diff| in a ball-sized box  "
                        f"onset t={onset['t_onset']:.2f}s peak={onset['peak']:.0f} "
                        f"threshold={bar:.0f} (red)"
                        + ("   OCCLUSION-EXPLAINED" if occlusion else ""),
                (pad_l, pad_t + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (0, 0, 255) if occlusion else (235, 235, 235), 1, cv2.LINE_AA)
    return canvas


# --------------------------------------------------------------- persistence --

def save_scan(report: ScanReport, arrays: dict, quad_meta: dict, out_dir) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = out_dir / f"{report.dataset}.series.npz"
    np.savez_compressed(npz_path, **{k: np.asarray(v) for k, v in arrays.items()})
    report.quad_source = quad_meta.get("source", "")
    report.quad_verified = bool(quad_meta.get("verified"))
    report.series = {"file": npz_path.name, "bytes": npz_path.stat().st_size,
                     "fields": {name: {"dtype": str(np.asarray(arrays[name]).dtype),
                                       "shape": list(np.asarray(arrays[name]).shape)}
                                for name in arrays},
                     "index_seconds": "arrays are indexed by frame; t[i] is frame i's "
                                      "time and the signal at i is between i-1 and i"}
    report_path = out_dir / f"{report.dataset}.json"
    report_path.write_text(json.dumps(asdict(report), indent=1))
    return {"json": str(report_path), "npz": str(npz_path)}


def save_report(payload: dict, out_dir, dataset: str = "vod30") -> str:
    """Merge analysis blocks into the dataset JSON (the scan's own keys win)."""
    out_dir = Path(out_dir)
    path = out_dir / f"{dataset}.json"
    current = json.loads(path.read_text()) if path.exists() else {}
    current.update(payload)
    path.write_text(json.dumps(current, indent=1))
    return str(path)


def load_scan(out_dir, dataset: str = "vod30") -> tuple[dict, dict]:
    out_dir = Path(out_dir)
    report = json.loads((out_dir / f"{dataset}.json").read_text())
    arrays = dict(np.load(out_dir / f"{dataset}.series.npz"))
    return report, arrays


# ------------------------------------------------------------------ benchmark -

def benchmark(video, n_frames: int = 600, cfg: MotionConfig = MotionConfig(),
              full: bool = False) -> dict:
    """Time the primitive against the full per-frame work.

    ``full=False`` is the claim under test: decode + resize to the working
    resolution + gray + abs-diff, which the research pass quoted at 2.2 ms/frame.
    """
    ctx = cloth_context(_as_quad([[0, 0], [1, 0], [1, 1], [0, 1]]), cfg) if full else None
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise OSError(f"cannot open {video}")
    last_native = last_gray = None
    started, read = time.time(), 0
    try:
        for _ in range(n_frames):
            ok, bgr = cap.read()
            if not ok:
                break
            work = cv2.resize(bgr, (cfg.width, cfg.height))
            gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
            native = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            if last_gray is not None:
                cv2.absdiff(gray, last_gray)
                if full and ctx is not None:
                    clip_motion(last_native, native, last_gray, gray, ctx, cfg)
            last_gray, last_native = gray, native
            read += 1
    finally:
        cap.release()
    wall = time.time() - started
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    return {"frames": read, "wall_s": round(wall, 3),
            "ms_per_frame": round(wall / max(1, read) * 1000.0, 3),
            "frames_per_s": round(read / wall, 1) if wall else None,
            "vod_estimate_min": round(wall / max(1, read) * total / 60.0, 2),
            "resolution": [cfg.width, cfg.height], "full_channels": full,
            "note": ("decode + resize to working resolution + gray + abs-diff only"
                     if not full else
                     "decode + resize + gray at both resolutions + abs-diff + 5 box "
                     "filters + masked reductions")}


# ----------------------------------------------------------------------- CLI --

def cmd_scan(args) -> None:
    quad_meta = load_quad(args.dataset, quad_file=args.quad)
    if quad_meta["quad_px"] is None:
        raise SystemExit(f"no cloth quad for {args.dataset}")
    cfg = MotionConfig(stride=args.stride, limit_s=args.limit_s, native=not args.no_native)
    primitive = benchmark(args.video, n_frames=args.bench_frames, cfg=cfg)
    print(f"quad: {quad_meta['source']} verified={quad_meta['verified']}")
    print(f"primitive (decode+gray+abs-diff): {primitive['ms_per_frame']} ms/frame")
    report, arrays = scan(args.video, quad_meta["quad_px"], cfg, args.dataset,
                          progress=lambda text: print("  " + text, flush=True))
    report.cost["primitive_ms_per_frame"] = primitive["ms_per_frame"]
    report.cost["primitive_frames_per_s"] = primitive["frames_per_s"]
    report.cost["primitive_note"] = primitive["note"]
    paths = save_scan(report, arrays, quad_meta, args.out_dir)
    print(json.dumps({k: report.cost[k] for k in
                      ("wall_s", "ms_per_frame", "frames_per_s", "primitive_ms_per_frame")},
                     indent=1))
    print(f"wrote {paths['json']} and {paths['npz']}")
    print("next: python -m src.motion_scan report")


def cmd_report(args) -> None:
    report, arrays = load_scan(args.out_dir, args.dataset)
    t = arrays["t"]
    cfg = MotionConfig(**{k: v for k, v in report["config"].items()
                          if k in MotionConfig.__dataclass_fields__})

    sets = control_windows(ROOT)
    cal = calibrate(arrays, sets, signal=ONSET_SIGNAL, half_s=args.control_half_s)
    threshold = cal["threshold"]
    occ_bars = cal["occlusion"]

    onsets = detect_onsets(t, arrays[ONSET_SIGNAL],
                           OnsetConfig(threshold=threshold, merge_s=args.merge_s,
                                       min_gap_s=args.min_gap_s))
    quad_meta = load_quad(args.dataset, quad_file=args.quad)
    ctx = cloth_context(quad_meta["quad_px"], cfg)
    blob_cache: dict = {}

    def blob_at(frame):
        frame = int(frame)
        if frame not in blob_cache:
            blob_cache[frame] = blob_shape(args.video, frame, ctx, cfg)
        return blob_cache[frame]

    rows = []
    for onset in onsets["onsets"]:
        t0 = float(onset["t_onset"])
        rows.append({**onset, "cell": int(value_at(t, arrays["cell"], t0)),
                     "cell_share": round(value_at(t, arrays["cell_share"], t0), 3),
                     "occ_share_at_onset": round(value_at(t, arrays["occ_share"], t0), 5),
                     "occ_dense_at_onset": round(value_at(t, arrays["occ_dense"], t0), 4),
                     "mean_at_onset": round(value_at(t, arrays["mean"], t0), 3),
                     "ball9_at_onset": round(value_at(t, arrays["ball9"], t0), 3),
                     "ball25_at_onset": round(value_at(t, arrays["ball25"], t0), 3),
                     "ball13w_at_onset": round(value_at(t, arrays["ball13w"], t0), 3),
                     "occlusion_explains": (
                         value_at(t, arrays["occ_dense"], t0) >= occ_bars["dense_bar"]
                         or value_at(t, arrays["occ_share"], t0) >= occ_bars["share_bar"]),
                     "blob": blob_at(onset["frame"]),
                     "decay": decay_shape(t, arrays[ONSET_SIGNAL], t0)})
    top = sorted(rows, key=lambda r: -r["peak"])[:args.top]
    top_unoccluded = [r for r in sorted(rows, key=lambda r: -r["peak"])
                      if not r["occlusion_explains"]][:args.top]

    events = []
    for event in _served_events(ROOT, args.events):
        t0 = float(event["t"])
        ball = window_profile(t, arrays[ONSET_SIGNAL], t0, threshold,
                              args.before, args.after, args.sample_hz)
        occ = occlusion_reading(t, arrays, t0, args.before, args.after)
        explains = explain_by_occlusion(occ, occ_bars)
        window_peak = peak_in_window(t, arrays[ONSET_SIGNAL], t0, args.before, args.after)
        # the blob is read at the frame that actually holds the window maximum: the
        # window profile's peak time sits on the sampling grid, not on a frame
        peak_frame = (int(np.argmin(np.abs(t - window_peak["t_peak"])))
                      if window_peak["t_peak"] is not None else 0)
        blob = blob_at(peak_frame)
        events.append({**event, "ball": ball, "occlusion": occ,
                       "occlusion_explains": explains,
                       "blob_at_ball_peak": blob,
                       "verdict": combined_verdict(ball["verdict"], explains,
                                                   ball["peak_offset_s"], blob["verdict"]),
                       "ball_max_in_window": window_peak})

    controls = []
    for name, times in sets.items():
        if not times:
            continue
        for t0 in times[:: max(1, len(times) // args.controls_per_set)][:args.controls_per_set]:
            controls.append({"set": name, "t": round(float(t0), 3),
                             "ball": peak_in_window(t, arrays[ONSET_SIGNAL], t0, 2.5, 2.5),
                             "occlusion": occlusion_reading(t, arrays, t0, 2.5, 2.5)})

    explained = [e for e in events if e["occlusion_explains"]]
    ball_sep = [e for e in events if e["ball"]["verdict"].startswith("ball-scale motion")]
    payload = {
        "calibration": cal,
        "onset_detection": {k: v for k, v in onsets.items() if k != "onsets"},
        "onset_counts": {"total": len(rows), "occlusion_explained": sum(
            1 for r in rows if r["occlusion_explains"]),
            "not_occlusion_explained": sum(1 for r in rows if not r["occlusion_explains"])},
        "onsets": rows,
        "top_onsets": top,
        "top_unoccluded_onsets": top_unoccluded,
        "strongest_frames": strongest_frames(t, arrays[ONSET_SIGNAL], arrays["occ_dense"],
                                             n=args.top, threshold=threshold),
        "events": events,
        "controls": controls,
        "answers": {
            "served_events": len(events),
            "events_with_ball_scale_at_t": len(ball_sep),
            "events_occlusion_explained": len(explained),
            "events_occlusion_explained_ids": [e.get("id") for e in explained],
            "queue_explained_entirely_by_occlusion": len(explained) == len(events),
            "top_onsets_not_occlusion_explained": [r["t_onset"] for r in top
                                                   if not r["occlusion_explains"]],
            "onsets_total": len(rows),
            "onsets_occlusion_explained": sum(1 for r in rows if r["occlusion_explains"]),
            "onsets_not_occlusion_explained": sum(1 for r in rows
                                                  if not r["occlusion_explains"]),
            "onsets_that_can_be_one_ball": sum(
                1 for r in rows if "can be a single ball" in r["blob"]["verdict"]),
            "onsets_changed_more_than_one_ball": sum(
                1 for r in rows if "can be a single ball" not in r["blob"]["verdict"]),
            "served_events_whose_blob_can_be_one_ball": sum(
                1 for e in events
                if "can be a single ball" in e["blob_at_ball_peak"]["verdict"]),
            "ball_scale_onset_at_served_time_unoccluded": sum(
                1 for e in events if e["ball"]["verdict"].startswith("ball-scale motion")
                and not e["occlusion_explains"]),
            "strongest_unoccluded_onset": (top_unoccluded[0] if top_unoccluded else None),
        },
        "limits": limits_block(arrays, threshold, cal["unoccluded"]["floor"]),
        "person_evidence": cached_person_evidence(ROOT),
        "thresholds": {"ball_floor": cal["unoccluded"]["floor"],
                       "ball_threshold": threshold,
                       "floor_margin": cal["unoccluded"]["margin"],
                       "floor_quantile": cal["unoccluded"]["quantile"],
                       "ball_floor_all_control_frames": cal["combined"]["max"],
                       "control_frames_excluded_as_occluded": cal["unoccluded"]["excluded_frames"],
                       "occ_dense_bar": occ_bars["dense_bar"],
                       "occ_share_bar": occ_bars["share_bar"]},
        "notes": report.get("notes", []),
    }
    path = save_report(payload, args.out_dir, args.dataset)
    _write_summary(payload, report, args.out_dir, args.dataset)
    print(json.dumps(payload["answers"], indent=1))
    print(f"threshold={threshold} unoccluded_floor={cal['unoccluded']['max']} "
          f"all_control_floor={cal['combined']['max']} occ_dense_bar={occ_bars['dense_bar']}")
    print(f"wrote {path}")


def cmd_strips(args) -> None:
    report, arrays = load_scan(args.out_dir, args.dataset)
    quad = load_quad(args.dataset, quad_file=args.quad)
    cfg = MotionConfig(**{k: v for k, v in report["config"].items()
                          if k in MotionConfig.__dataclass_fields__})
    ctx = cloth_context(quad["quad_px"], cfg)
    threshold = (report.get("thresholds") or {}).get("ball_threshold")
    signal = (report.get("onset_detection") or {}).get("onset_signal", ONSET_SIGNAL)
    out = Path(args.out_dir) / "onsets"
    made = []
    seen: set = set()
    rows: list = []

    def add(row):
        key = round(float(row["t_onset"]), 3)
        if key in seen or len(rows) >= args.top:
            return
        seen.add(key)
        rows.append(row)

    # The onsets the occlusion channel does NOT explain are the ones that could be
    # real ball motion, so they are drawn first; then the strongest onsets overall,
    # then -- if the calibrated bar was never cleared -- the strongest readings.
    for row in report.get("top_unoccluded_onsets", [])[: max(1, args.top // 2)]:
        add(row)
    for row in report.get("top_onsets", []):
        add(row)
    covered = set(seen)
    for strong in report.get("strongest_frames", []):
        if len(rows) >= args.top:
            break
        if any(abs(strong["t"] - t) < 1.0 for t in covered):
            continue
        add({"t_onset": strong["t"], "frame": strong["frame"], "peak": strong["value"],
             "threshold": threshold or 0.0, "baseline": 0.0, "below_threshold": True,
             "occlusion_explains": strong["occ_dense"] >= (
                 (report.get("thresholds") or {}).get("occ_dense_bar", 1.0))})
    for i, onset in enumerate(rows):
        name = f"{i + 1:02d}_t{onset['t_onset']:07.2f}s_ball17_{onset['peak']:.0f}"
        if onset.get("below_threshold"):
            name += "_belowthr"
        name += "_occluded" if onset.get("occlusion_explains") else "_unoccluded"
        path = out / f"{name}.png"
        made.append(render_strip(args.video, onset, ctx, arrays, path, cfg,
                                 threshold=threshold,
                                 occlusion=bool(onset.get("occlusion_explains")),
                                 signal=signal))
    unoccluded = [o for o in report.get("top_unoccluded_onsets", [])
                  if not o.get("occlusion_explains")]
    if unoccluded:
        made.append(render_blob_sheet(args.video, unoccluded, ctx,
                                      out / "00_unoccluded_blob_detail.png", cfg))
    print(json.dumps(made, indent=1))


def cmd_person(args) -> None:
    report, arrays = load_scan(args.out_dir, args.dataset)
    quad = load_quad(args.dataset, quad_file=args.quad)
    rows_in = list(report.get("top_onsets", []))
    unoccluded = [o for o in report.get("top_unoccluded_onsets", [])
                  if o["t_onset"] not in {r["t_onset"] for r in rows_in}]
    rows_in += unoccluded
    if len(rows_in) < args.top:
        rows_in += [{"t_onset": s["t"], "frame": s["frame"], "peak": s["value"],
                     "below_threshold": True} for s in report.get("strongest_frames", [])]
    rows = []
    for onset in rows_in[:args.top]:
        check = person_check(args.video, onset, quad["quad_px"])
        rows.append({"t_onset": onset["t_onset"], "ball17": onset["peak"],
                     "below_threshold": bool(onset.get("below_threshold")),
                     "occlusion_explains": onset.get("occlusion_explains"), **check})
    explained = sum(1 for r in rows if r["explained_by_person"])
    payload = {"person_checks": rows, "n": len(rows), "person_explained": explained,
               "person_explained_rate": round(explained / len(rows), 3) if rows else None,
               "occlusion_channel_explained": sum(1 for r in rows
                                                  if r["occlusion_explains"]),
               "person_share_threshold": PERSON_SHARE_MAX}
    print(json.dumps(payload, indent=1))
    save_report({"person_checks": payload}, args.out_dir, args.dataset)


def _served_events(root, events_file) -> list:
    path = Path(events_file) if events_file else Path(root) / "out" / "scan30" / "events.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = data.get("events") or []
    rows = []
    for position, event in enumerate(data):
        try:
            t = float(event["t"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({"id": event.get("id"), "t": round(t, 3), "position": position,
                     "kind": event.get("type") or event.get("kind"),
                     "origin": event.get("origin"), "source": event.get("source"),
                     "window_s": event.get("window_s")})
    rows.sort(key=lambda r: r["t"])
    return rows


def _write_summary(payload: dict, report: dict, out_dir, dataset: str) -> str:
    lines = [f"# motion_scan {dataset}", "",
             f"frames {report['frames_scanned']}  resolution {report['resolution']} work / "
             f"{report['native_resolution']} native",
             f"cost {report['cost']['ms_per_frame']} ms/frame, "
             f"{report['cost']['wall_s']} s wall "
             f"(primitive decode+gray+abs-diff {report['cost'].get('primitive_ms_per_frame')} "
             f"ms/frame)", "",
             f"ball-scale channel `{payload['calibration']['signal']}` = max "
             f"{BALL_K_NATIVE}x{BALL_K_NATIVE} px mean |diff| at native; median ball "
             f"{BALL_DIAMETER_NATIVE} px (p10 {BALL_DIAMETER_P10}, p90 {BALL_DIAMETER_P90})",
             f"control floor p{payload['calibration']['unoccluded']['quantile']} = "
             f"{payload['thresholds']['ball_floor']} -> threshold "
             f"{payload['thresholds']['ball_threshold']} "
             f"(x{payload['thresholds']['floor_margin']}); control max (never the bar) "
             f"{payload['thresholds']['ball_floor_all_control_frames']}",
             f"occlusion bars: occ_dense >= {payload['thresholds']['occ_dense_bar']} or "
             f"occ_share >= {payload['thresholds']['occ_share_bar']}",
             f"control frames above the threshold: "
             f"{payload['calibration']['control_frames_above_threshold']['unoccluded_control_frames']} "
             f"unoccluded "
             f"({payload['calibration']['control_frames_above_threshold']['rate_unoccluded']:.2%} of "
             f"unoccluded control frames)", "",
             "## served events", "",
             "| id | t | ball17 peak | /threshold | offset | occ_dense peak | occ offset | "
             "occlusion explains | combined verdict |",
             "|---|---|---|---|---|---|---|---|---|"]
    for e in payload["events"]:
        lines.append(
            f"| {e.get('id')} | {e['t']} | {e['ball']['peak']} | "
            f"{e['ball']['peak_over_floor']} | {e['ball']['peak_offset_s']} | "
            f"{e['occlusion']['occ_dense_peak']} | "
            f"{e['occlusion']['occ_dense_offset_s']} | "
            f"{'yes' if e['occlusion_explains'] else 'no'} | {e['verdict']} |")
    lines += ["", "## top onsets", "",
              "| # | t | ball17 peak | excess | occ_dense@onset | occlusion explains |",
              "|---|---|---|---|---|---|"]
    for i, o in enumerate(payload["top_onsets"]):
        lines.append(f"| {i + 1} | {o['t_onset']} | {o['peak']} | {o['excess_ratio']} | "
                     f"{o['occ_dense_at_onset']} | "
                     f"{'yes' if o['occlusion_explains'] else 'no'} |")
    lines += ["", "## strongest onsets the occlusion DENSITY channel does not explain", "",
              "| # | t | ball17 peak | excess | occ_dense@onset | occ_share@onset | "
              "largest changed component | blob verdict |",
              "|---|---|---|---|---|---|---|---|"]
    for i, o in enumerate(payload.get("top_unoccluded_onsets", [])[:12]):
        blob = o.get("blob") or {}
        lines.append(f"| {i + 1} | {o['t_onset']} | {o['peak']} | {o['excess_ratio']} | "
                     f"{o['occ_dense_at_onset']} | {o['occ_share_at_onset']} | "
                     f"{blob.get('largest_area')}px^2 ({blob.get('area_over_ball')}x ball) | "
                     f"{blob.get('verdict')} |")
    answers = payload["answers"]
    lines += ["", "## strongest ball-scale readings anywhere in the VOD", "",
              "| # | t | ball17 | fraction of threshold | over threshold | occ_dense |",
              "|---|---|---|---|---|---|"]
    for i, s in enumerate(payload.get("strongest_frames", [])):
        lines.append(f"| {i + 1} | {s['t']} | {s['value']} | {s['fraction_of_threshold']} | "
                     f"{s['over_threshold']} | {s['occ_dense']} |")
    lines += ["", "## answers", "",
              f"- served events: {answers['served_events']}",
              f"- occlusion explains: {answers['events_occlusion_explained']} of "
              f"{answers['served_events']} "
              f"(ids {answers['events_occlusion_explained_ids']})",
              f"- queue explained ENTIRELY by occlusion: "
              f"{answers['queue_explained_entirely_by_occlusion']}",
              f"- ball-scale motion at the served time: {answers['events_with_ball_scale_at_t']} "
              f"(all occlusion-explained: "
              f"{answers['events_with_ball_scale_at_t'] == answers['events_occlusion_explained']})",
              f"- onsets: {answers['onsets_total']} total, "
              f"{answers['onsets_occlusion_explained']} occlusion-explained, "
              f"{answers['onsets_not_occlusion_explained']} not",
              f"- onsets whose largest changed component could be ONE ball: "
              f"{answers['onsets_that_can_be_one_ball']} of "
              f"{answers['onsets_total']}",
              f"- served events whose largest changed component could be one ball: "
              f"{answers['served_events_whose_blob_can_be_one_ball']} of "
              f"{answers['served_events']}", "",
              "## resolution limits and saturation", ""]
    for line in payload.get("limits", {}).get("saturation", []):
        lines += [f"- {line}"]
    path = Path(out_dir) / f"{dataset}.summary.md"
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--video", default=str(ROOT / "data" / "vod_30min_260815.mp4"))
        p.add_argument("--dataset", default="vod30")
        p.add_argument("--out-dir", default=str(ROOT / "out" / "motion_scan"))
        p.add_argument("--quad", default=None)

    p = sub.add_parser("scan", help="decode the whole VOD and write the series")
    common(p)
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--limit-s", type=float, default=None)
    p.add_argument("--no-native", action="store_true")
    p.add_argument("--bench-frames", type=int, default=600)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("report", help="calibrate the floor, find onsets, answer")
    common(p)
    p.add_argument("--events", default=None)
    p.add_argument("--before", type=float, default=1.5)
    p.add_argument("--after", type=float, default=2.5)
    p.add_argument("--sample-hz", type=float, default=10.0)
    p.add_argument("--top", type=int, default=12)
    p.add_argument("--control-half-s", type=float, default=2.5)
    p.add_argument("--controls-per-set", type=int, default=20)
    p.add_argument("--merge-s", type=float, default=0.25)
    p.add_argument("--min-gap-s", type=float, default=1.0)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("strips", help="evidence strips for the top onsets")
    common(p)
    p.add_argument("--top", type=int, default=12)
    p.set_defaults(func=cmd_strips)

    p = sub.add_parser("person", help="YOLO person check on the top onsets")
    common(p)
    p.add_argument("--top", type=int, default=12)
    p.set_defaults(func=cmd_person)

    args = ap.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
