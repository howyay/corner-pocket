"""Measure whether a served event's timestamp actually carries ball motion.

The owner's report was "none of the event time stamps actually have any of the
ball movement detected".  That is a claim about *time*, not about census drops
or claim-vs-measured geometry, and nothing in this repo had measured it.  This
tool answers exactly three questions, in this order:

1. **Motion proxy per window.**  For each served event, decode the window
   ``[t - before, t + after]`` through the *frame-index* path (the authority:
   ``frame_index / fps``), sample it at ``--sample-fps``, and measure per-pair
   absolute difference restricted to the cloth plus Farneback optical-flow
   magnitude on the cloth.  Report the peak, the median, and *where* the peak
   sits relative to ``t``.  A still table gives a near-zero floor; a real shot
   spikes.  Controls (data-driven quiet windows, or explicit ``--controls``)
   establish that floor on the same VOD, so the numbers are comparable.

2. **Two-timebase cross-check.**  Decode the still at
   ``frame_index = round(t * fps)`` (the app's frame path) and, in a *fresh*
   ``cv2.VideoCapture``, seek to ``currentTime = t`` (the stage's seek path),
   then compare the two pictures (SSIM / mean absolute difference) and report
   how many frames apart the two seeks land.  ``--drift`` additionally walks
   the whole file reading each frame's real PTS (``CAP_PROP_POS_MSEC``) against
   its nominal ``index / fps``, which is what tells us whether the nomina-
   timestamp contract in ``docs/unified-workbench.md`` holds on this VOD.

3. **Classification** per event: ``motion at served time`` /
   ``motion elsewhere in window`` (with its offset in seconds) /
   ``no motion anywhere in window``.

Read-only with respect to every production artifact: it reads the queue, the
video and the quad, and writes only its own report (``--report``).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from src.event_window import AT_TOL_S, EVENT_AFTER_S, EVENT_BEFORE_S

SMALL_W, SMALL_H = 960, 540          # the census working size (src/eval_events.py)
# The span the console clips.  The two names stay, because tests/test_timing_verify.py
# holds annotator/app.js to them; the numbers come from src/event_window.py.
CLIP_BEFORE_S, CLIP_AFTER_S = EVENT_BEFORE_S, EVENT_AFTER_S
SAMPLE_FPS = 5.0
FLOW_WIDTH = 320                     # flow runs on the cloth crop at this width

# A peak has to clear this many times the *still* floor (and the absolute margin
# below) before it counts as motion at all.  Both live here, not inline, so a
# test can pin them.
#
# The floor is a per-window quantile, not a window peak: this VOD is a busy room
# (people walk through the whole frame), so a control window's *peak* is often
# itself a person crossing the cloth.  Its low quantile is what "still cloth"
# looks like on this video, and that is the number a shot has to beat.
MOTION_FLOOR_RATIO = 3.0
MOTION_FLOOR_ABSOLUTE = 3.0          # 8-bit gray levels, cloth-mean
STILL_QUANTILE = 0.25                # per-window still floor = this quantile of its pairs
CONTROL_QUANTILE = 0.5               # the VOD's still floor = this quantile of the controls
MOTION_AT_SERVED_S = AT_TOL_S        # |peak offset| <= this is "at the served time"
CHANGED_LEVEL = 12                   # a cloth pixel counts as "changed" above this

# Ball-scale vs occlusion.  At 960x540 the cloth spans ~350 px for a 2540 mm
# table, so a 57 mm ball is ~8 px across (~50 px^2, a few hundred with motion
# blur).  A change blob that big is a ball; a blob of thousands of pixels is a
# person walking between the camera and the cloth -- measured on this VOD, that
# is what dominates the naive cloth-mean difference.
BALL_BLOB_MAX_PX = 3000              # a blob at or below this is ball-scale
OCCLUSION_BLOB_MIN_PX = 3000         # a blob at or above this is occlusion

# The project's own ball detector was tried here as a third channel and
# deliberately dropped: at 5 fps its greedy candidate matching paired different
# objects in every sample (11-18 "moved" pairs out of 20 in *every* window,
# including a still table), because a person crossing the cloth rebuilds the
# candidate set each frame.  A metric that fires everywhere measures nothing.
BALL_FOOTPRINT_MAX = 0.02            # <= 2 % of the cloth changed: ball-scale footprint
BALL_PEAK_RATIO = 1.5                # ball-scale peak vs the same statistic on controls
BALL_PEAK_MIN = 60.0                 # 8-bit levels: a ball appearing/vacating a spot


# ------------------------------------------------------------------ inputs

def load_events(queue_path, limit=None):
    """The served queue: a list of events, each with a nominal time ``t``."""
    data = json.loads(Path(queue_path).read_text())
    if isinstance(data, dict):
        for key in ("events", "queue", "served"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError(f"{queue_path}: expected a list of events")
    rows = []
    for position, event in enumerate(data):
        if not isinstance(event, dict):
            continue
        try:
            t = float(event["t"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append(dict(position=position, id=event.get("id"), t=t, kind=event.get("type") or event.get("kind"),
                         source=event.get("source"), origin=event.get("origin"),
                         window_s=event.get("window_s")))
    rows.sort(key=lambda r: r["t"])
    return rows[:limit] if limit else rows


def load_quad(quad_path, anchors_path=None):
    """The cloth quad in 1280x720 scan pixels, or None.

    The first file that carries a quad wins: the scan's own corners, then the hand
    anchors.  ``src.calib_segments.read`` names the entry inside the file, so this
    tool does not hold the artifact layout.
    """
    from src import calib_segments

    for path, key in ((quad_path, "corners"), (anchors_path, "anchors")):
        if not path:
            continue
        reference = calib_segments.read(path, key)
        if reference.found:
            return np.asarray(reference.quad, np.float32)
    return None


def cloth_mask(quad, width=SMALL_W, height=SMALL_H, scan_width=1280.0):
    """A 0/1 mask of the cloth at the small working size."""
    mask = np.zeros((height, width), np.uint8)
    if quad is None:
        return mask
    scaled = np.asarray(quad, np.float32) * (width / scan_width)
    cv2.fillPoly(mask, [np.round(scaled).astype(np.int32)], 1)
    return mask


# ------------------------------------------------------------------ decoding

def open_video(path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {path}")
    return cap


def video_meta(cap):
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    return fps, count, count / fps


def small_gray(frame, width=SMALL_W, height=SMALL_H):
    if frame.shape[1] != width or frame.shape[0] != height:
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def sample_window(cap, t, fps, before=CLIP_BEFORE_S, after=CLIP_AFTER_S, sample_fps=SAMPLE_FPS):
    """Sequential decode of ``[t - before, t + after]`` through frame indexes.

    Returns ``[(nominal_t, frame_index, bgr_small, pts_seconds), ...]``.  The
    index stride is ``fps / sample_fps``; every sample is a real decoded frame
    from the frame-index path, and its container PTS is recorded next to it so
    a caller can see both timebases for the same picture.
    """
    first = max(0, int(round((t - before) * fps)))
    last = int(round((t + after) * fps))
    stride = max(1, int(round(fps / sample_fps)))
    if not cap.set(cv2.CAP_PROP_POS_FRAMES, first):
        return []
    out = []
    index = first
    while index <= last:
        ok, frame = cap.read()
        if not ok:
            break
        if frame.shape[1] != SMALL_W or frame.shape[0] != SMALL_H:
            frame = cv2.resize(frame, (SMALL_W, SMALL_H), interpolation=cv2.INTER_AREA)
        out.append((index / fps, index, frame, cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0))
        for _ in range(stride - 1):
            if not cap.grab():
                break
        index += stride
    return out


def frame_at_index(video, index):
    """The app's frame path: seek by frame index, return (gray, index, pts)."""
    cap = open_video(video)
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = cap.read()
        if not ok:
            return None
        return small_gray(frame), int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1, cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
    finally:
        cap.release()


def frame_at_time(video, t):
    """The stage's path: seek by container time (what ``video.currentTime`` does)."""
    cap = open_video(video)
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(t)) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            return None
        return small_gray(frame), int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1, cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
    finally:
        cap.release()


# ------------------------------------------------------------------ measures

def ssim(a, b, block=16):
    """Block-wise SSIM mean on two same-shape 8-bit gray images."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    height = (a.shape[0] // block) * block
    width = (a.shape[1] // block) * block
    if height == 0 or width == 0:
        return float("nan")
    a = a[:height, :width].reshape(height // block, block, width // block, block).transpose(0, 2, 1, 3)
    b = b[:height, :width].reshape(height // block, block, width // block, block).transpose(0, 2, 1, 3)
    a = a.reshape(-1, block * block)
    b = b.reshape(-1, block * block)
    mu_a, mu_b = a.mean(1), b.mean(1)
    var_a, var_b = a.var(1), b.var(1)
    cov = ((a - mu_a[:, None]) * (b - mu_b[:, None])).mean(1)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    score = ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (var_a + var_b + c2))
    return float(np.mean(score))


def compare_pictures(a, b):
    if a is None or b is None:
        return dict(ssim=None, mean_abs_diff=None)
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return dict(ssim=round(ssim(a, b), 5), mean_abs_diff=round(float(diff.mean()), 4))


def motion_pair(a, b, cloth, flow_width=FLOW_WIDTH):
    """Per-pair motion on the cloth.

    Returns ``(mean_diff, changed_frac, p99, ball_proxy, occlusion_frac, n_ball, flow)``.
    ``ball_proxy`` is the cloth-mean difference *contributed only by ball-scale
    change blobs*, which is what survives when a person walks in front of the
    cloth and swamps the plain cloth mean; ``occlusion_frac`` is the share of
    the cloth covered by large change blobs.
    """
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    inside = cloth > 0
    cloth_px = max(1, int(inside.sum()))
    mean_diff = float(diff[inside].mean()) if inside.any() else float("nan")
    peak_diff = float(diff[inside].max()) if inside.any() else float("nan")
    changed = float(np.count_nonzero(diff[inside] > CHANGED_LEVEL) / cloth_px)
    p99 = float(np.percentile(diff[inside], 99)) if inside.any() else float("nan")

    binary = np.where(inside & (diff > CHANGED_LEVEL), 1, 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    ball_sum = 0.0
    n_ball = 0
    big_area = 0
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= OCCLUSION_BLOB_MIN_PX:
            big_area += area
            continue
        if area <= BALL_BLOB_MAX_PX:
            x, y = int(stats[label, cv2.CC_STAT_LEFT]), int(stats[label, cv2.CC_STAT_TOP])
            w, h = int(stats[label, cv2.CC_STAT_WIDTH]), int(stats[label, cv2.CC_STAT_HEIGHT])
            patch = labels[y:y + h, x:x + w] == label
            ball_sum += float(diff[y:y + h, x:x + w][patch].sum())
            n_ball += 1
    ball_proxy = ball_sum / cloth_px
    occlusion = big_area / cloth_px

    flow_mag = float("nan")
    ys, xs = np.nonzero(cloth)
    if len(xs) > 32:
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        scale = flow_width / float(max(1, x1 - x0))
        size = (max(8, int((x1 - x0) * scale)), max(8, int((y1 - y0) * scale)))
        ca = cv2.resize(a[y0:y1, x0:x1], size, interpolation=cv2.INTER_AREA)
        cb = cv2.resize(b[y0:y1, x0:x1], size, interpolation=cv2.INTER_AREA)
        cmask = cv2.resize(cloth[y0:y1, x0:x1], size, interpolation=cv2.INTER_NEAREST)
        flow = cv2.calcOpticalFlowFarneback(ca, cb, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        keep = cmask > 0
        if keep.any():
            flow_mag = float(mag[keep].mean())
    return mean_diff, peak_diff, changed, p99, ball_proxy, occlusion, n_ball, flow_mag


def window_profile(samples, cloth):
    """Per-pair motion over a sampled window, plus its peak/median/shape.

    The shape is what answers "is the movement at the served time": ``peak_at``
    and ``peak_offset_s`` say where the strongest change is, ``onset``/
    ``finish`` bound the excursion above the window's own still floor, and
    ``centroid`` is the motion-weighted mean time.  Two peaks are tracked: the
    raw cloth mean (``peak``, blind to what moved) and ``ball_peak``, which
    only counts ball-scale change blobs and is robust to a person walking in
    front of the cloth.
    """
    rows = []
    for first, second in zip(samples, samples[1:]):
        mean_diff, peak_diff, changed, p99, ball_proxy, occlusion, n_ball, flow_mag = motion_pair(
            small_gray(first[2]), small_gray(second[2]), cloth)
        rows.append(dict(
            t_from=round(first[0], 4), t_to=round(second[0], 4),
            index_from=first[1], index_to=second[1],
            dt=round(second[0] - first[0], 4),
            diff=round(mean_diff, 4) if mean_diff == mean_diff else None,
            maxdiff=round(peak_diff, 2) if peak_diff == peak_diff else None,
            ball=round(ball_proxy, 4) if ball_proxy == ball_proxy else None,
            balls=n_ball,
            occlusion=round(occlusion, 5),
            changed_frac=round(changed, 5) if changed == changed else None,
            p99=round(p99, 3) if p99 == p99 else None,
            flow=round(flow_mag, 4) if flow_mag == flow_mag else None,
        ))
    diffs = [r["diff"] for r in rows if r["diff"] is not None]
    flows = [r["flow"] for r in rows if r["flow"] is not None]
    empty = dict(pairs=rows, peak=None, median=None, still_floor=None, ball_peak=None,
                 ball_median=None, ball_still_floor=None, ball_at=None, ball_offset_ratio=None,
                 flow_peak=None, flow_median=None, peak_at=None, flow_peak_at=None,
                 changed_frac=None, p99=None, occlusion=None, onset=None, finish=None,
                 centroid=None, excess_ratio=None)
    if not diffs:
        return empty
    balls = [r["ball"] for r in rows if r["ball"] is not None]
    peak_index = int(np.argmax(diffs))
    still_floor = float(np.quantile(diffs, STILL_QUANTILE))
    total = float(sum(max(0.0, d - still_floor) for d in diffs))
    rows_over = [i for i, d in enumerate(diffs) if d > max(still_floor * 2.0, still_floor + 1.0)]
    centroid = None
    if total > 0:
        weights = [max(0.0, d - still_floor) for d in diffs]
        centroid = float(sum(r["t_from"] * w for r, w in zip(rows, weights)) / total)
    ball_floor = float(np.quantile(balls, STILL_QUANTILE)) if balls else None
    return dict(
        pairs=rows, peak=round(max(diffs), 4), median=round(float(np.median(diffs)), 4),
        still_floor=round(still_floor, 4),
        ball_peak=round(max(balls), 4) if balls else None,
        ball_median=round(float(np.median(balls)), 4) if balls else None,
        ball_still_floor=round(ball_floor, 4) if ball_floor is not None else None,
        ball_at=round(rows[int(np.argmax(balls))]["t_from"], 4) if balls else None,
        ball_offset_ratio=round(max(balls) / ball_floor, 2) if balls and ball_floor else None,
        flow_peak=round(max(flows), 4) if flows else None,
        flow_median=round(float(np.median(flows)), 4) if flows else None,
        peak_at=round(rows[peak_index]["t_from"], 4),
        flow_peak_at=round(rows[int(np.argmax(flows))]["t_from"], 4) if flows else None,
        changed_frac=rows[peak_index]["changed_frac"], p99=rows[peak_index]["p99"],
        occlusion=max(r["occlusion"] for r in rows),
        onset=round(rows[rows_over[0]]["t_from"], 4) if rows_over else None,
        finish=round(rows[rows_over[-1]]["t_to"], 4) if rows_over else None,
        centroid=round(centroid, 4) if centroid is not None else None,
        excess_ratio=round(max(diffs) / still_floor, 2) if still_floor > 0 else None,
    )


def footprint_split(profile, limit=BALL_FOOTPRINT_MAX):
    """The strongest *local* change in the window that still has a ball-scale footprint.

    The cloth-mean difference cannot see a ball at all: at this working size the
    cloth is ~70 000 px and a struck 57 mm ball changes a few hundred of them by
    ~150 gray levels, which is a cloth mean of ~0.7 - the same order as the
    still floor.  A person crossing the camera changes 20-77 % of the cloth and
    contributes 40+.  The cloth mean therefore measures people.

    What a ball does show up in is the *peak* pixel change on the cloth: a ball
    appearing or vacating a spot changes that spot by 100-200 levels, while a
    still cloth peaks at compression noise.  Taking the largest peak change
    among pairs whose changed footprint stays under ``limit`` therefore answers
    "did a ball move here" without being able to answer "a person walked".
    """
    small = [row for row in profile["pairs"]
             if row.get("changed_frac") is not None and row["changed_frac"] <= limit
             and row.get("maxdiff") is not None]
    if not small:
        return dict(ball_scale_peak=None, ball_scale_mean=None, ball_scale_change=None,
                    ball_scale_at=None, ball_scale_pairs=0)
    winner = max(small, key=lambda row: row["maxdiff"])
    return dict(ball_scale_peak=winner["maxdiff"], ball_scale_mean=winner["diff"],
                ball_scale_change=winner["changed_frac"], ball_scale_at=winner["t_from"],
                ball_scale_pairs=len(small))


def apply_footprint(profile, t, floor=None, ratio=BALL_PEAK_RATIO, absolute=BALL_PEAK_MIN):
    """Add the ball-scale read to a profile, with its own offset and verdict.

    ``floor`` is the same statistic measured on the control windows.  When even
    those (near-frozen) windows produce a local peak at or above the absolute
    bar, the statistic cannot separate a ball from everything else that flickers
    inside the quad, and the honest verdict is that the signal is not separable
    - not that no ball moved.  Saying the latter would turn an insensitive
    measurement into a negative result.
    """
    split = footprint_split(profile)
    profile.update(split)
    threshold = max((floor or 0.0) * ratio, absolute)
    profile["ball_scale_threshold"] = round(threshold, 2)
    offset = None
    if floor is not None and floor >= absolute:
        profile["ball_scale_verdict"] = "ball-scale signal not separable from controls"
    elif split["ball_scale_at"] is None or (split["ball_scale_peak"] or 0) < threshold:
        profile["ball_scale_verdict"] = "no ball-scale motion in window"
    else:
        offset = round(split["ball_scale_at"] - t, 3)
        if abs(offset) <= MOTION_AT_SERVED_S:
            profile["ball_scale_verdict"] = "ball-scale motion at the served time"
        else:
            profile["ball_scale_verdict"] = "ball-scale motion elsewhere in window"
    profile["ball_scale_offset_s"] = offset
    return profile


def records_motion_check(records_path, events, reach_s=5.0):
    """The scan's own trigger signal around each event, from its per-sample records.

    ``out/scan30/records.json`` carries the ``motion`` scalar the scan itself
    used to propose candidates.  If that scalar peaks at the served time, the
    detector fired on *a real change at the right moment* and the question is
    what changed; if it peaks seconds away, the timestamp itself is wrong.  The
    records are sampled at 1 Hz, so an offset under a second is within the
    sampling, not a drift - reported, not smoothed away.
    """
    try:
        data = json.loads(Path(records_path).read_text())
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        data = data.get("records") or data.get("frames") or []
    samples = []
    for row in data:
        try:
            samples.append((float(row["t"]), float(row.get("motion") or 0.0), row.get("n_classical")))
        except (KeyError, TypeError, ValueError):
            continue
    if not samples:
        return None
    samples.sort()
    times = np.array([s[0] for s in samples])
    motions = np.array([s[1] for s in samples])
    rows = []
    for event in events:
        t = event["t"]
        window = np.abs(times - t) <= reach_s
        if not window.any():
            rows.append(dict(t=t, in_reach=False))
            continue
        local = times[window]
        values = motions[window]
        peak = int(np.argmax(values))
        nearest = int(np.argmin(np.abs(local - t)))
        rows.append(dict(
            t=t, in_reach=True, samples=int(window.sum()),
            nearest_t=round(float(local[nearest]), 3),
            nearest_motion=round(float(values[nearest]), 3),
            nearest_offset_s=round(float(local[nearest] - t), 3),
            peak_t=round(float(local[peak]), 3), peak_motion=round(float(values[peak]), 3),
            peak_offset_s=round(float(local[peak] - t), 3),
            all_below_nearest=bool((values <= values[nearest]).all()),
        ))
    offsets = [abs(r["peak_offset_s"]) for r in rows if r.get("in_reach")]
    return dict(path=str(records_path), sample_count=len(samples),
                step_s=round(float(np.median(np.diff(times))), 3) if len(times) > 1 else None,
                reach_s=reach_s, events=rows,
                max_abs_peak_offset_s=max(offsets) if offsets else None,
                nearest_is_peak=sum(1 for r in rows if r.get("in_reach") and r["all_below_nearest"]))


def classify_event(metrics, t, floor, ratio=MOTION_FLOOR_RATIO, absolute=MOTION_FLOOR_ABSOLUTE,
                   at_served=MOTION_AT_SERVED_S):
    """The three-way verdict the owner's claim needs."""
    peak = metrics.get("peak")
    if peak is None:
        return "no frames decoded", None
    threshold = max((floor or 0.0) * ratio, absolute)
    if peak < threshold:
        return "no motion anywhere in window", None
    offset = None if metrics.get("peak_at") is None else round(metrics["peak_at"] - t, 3)
    if offset is not None and abs(offset) <= at_served:
        return "motion at the served time", offset
    return "motion elsewhere in window", offset


# ------------------------------------------------------------------ cross-checks

def cross_check(video, times, fps, tolerance_s=0.002):
    """Frame-index seek vs container-time seek, picture by picture."""
    rows = []
    for t in times:
        index = int(round(t * fps))
        by_index = frame_at_index(video, index)
        by_time = frame_at_time(video, t)
        if by_index is None or by_time is None:
            rows.append(dict(t=t, error="decode failed"))
            continue
        same = np.array_equal(by_index[0], by_time[0])
        rows.append(dict(
            t=round(t, 4), frame_index=index,
            index_path=dict(index=by_index[1], pts=round(by_index[2], 4)),
            time_path=dict(index=by_time[1], pts=round(by_time[2], 4)),
            frames_apart=by_time[1] - index,
            time_gap_s=round(by_time[2] - t, 4),
            drift_s=round(by_index[2] - index / fps, 4),
            identical=bool(same),
            **compare_pictures(by_index[0], by_time[0]),
        ))
    agree = [r for r in rows if "identical" in r]
    return dict(rows=rows,
                all_identical=bool(agree) and all(r["identical"] for r in agree),
                max_abs_drift_s=max([abs(r["drift_s"]) for r in agree], default=None),
                max_abs_frames_apart=max([abs(r["frames_apart"]) for r in agree], default=None),
                tolerance_s=tolerance_s)


def drift_scan(video, step_s=30.0, fps=None):
    """Real PTS minus nominal ``index / fps`` across the whole file."""
    cap = open_video(video)
    try:
        reported_fps, count, duration = video_meta(cap)
        fps = fps or reported_fps
        step = max(1, int(round(step_s * fps)))
        rows = []
        for index in list(range(0, count, step)) + [count - 1]:
            if not cap.set(cv2.CAP_PROP_POS_FRAMES, index):
                continue
            ok, _ = cap.read()
            if not ok:
                continue
            pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            rows.append(dict(index=index, nominal=round(index / fps, 4), pts=round(pts, 4),
                             drift=round(pts - index / fps, 4)))
        drifts = [r["drift"] for r in rows]
        return dict(fps=reported_fps, frame_count=count, duration=round(duration, 4), step_s=step_s,
                    samples=rows, max_abs_drift_s=max([abs(d) for d in drifts], default=None),
                    last_drift_s=drifts[-1] if drifts else None)
    finally:
        cap.release()


# ------------------------------------------------------------------ controls

def spread_controls(events, duration, count=12, margin_s=20.0, before=CLIP_BEFORE_S, after=CLIP_AFTER_S):
    """Uniformly spread quiet candidates that stay clear of every served event."""
    if count <= 1:
        return [duration * 0.5]
    near = sorted(e["t"] for e in events)
    out = []
    for step in range(count):
        t = duration * (step + 1) / (count + 1)
        if any(abs(t - e) <= margin_s for e in near):
            continue
        if t - before < 0 or t + after > duration:
            continue
        out.append(round(t, 3))
    return out


def measure_controls(cap, times, cloth, fps):
    rows = []
    for t in times:
        samples = sample_window(cap, t, fps)
        if len(samples) < 3:
            continue
        profile = window_profile(samples, cloth)
        split = footprint_split(profile)
        rows.append(dict(t=round(t, 4), peak=profile["peak"], median=profile["median"],
                         still_floor=profile["still_floor"], flow_peak=profile["flow_peak"],
                         flow_median=profile["flow_median"],
                         ball_scale_peak=split["ball_scale_peak"]))
    return rows


def control_floor(rows, quantile=CONTROL_QUANTILE):
    """What a still cloth measures on this VOD: the low quantile of the controls'
    own still floors.  A control's *peak* is not usable as a floor here - the
    room is busy and a person often crosses a control window too."""
    floors = sorted(r["still_floor"] for r in rows if r.get("still_floor") is not None)
    if not floors:
        return None
    return float(np.quantile(floors, quantile))


# ------------------------------------------------------------------ cli

def parse_times(value):
    if not value:
        return []
    return [float(part) for part in str(value).replace(" ", "").split(",") if part]


def analyze(video, queue, quad_path=None, anchors_path=None, before=CLIP_BEFORE_S, after=CLIP_AFTER_S,
            sample_fps=SAMPLE_FPS, controls=None, control_count=12, drift_step=30.0,
            cross_times=None, records_path="out/scan30/records.json", limit=None, progress=None):
    events = load_events(queue, limit=limit)
    quad = load_quad(quad_path, anchors_path)
    cloth = cloth_mask(quad)
    cap = open_video(video)
    try:
        fps, count, duration = video_meta(cap)
    finally:
        cap.release()

    timing = dict(fps=fps, frame_count=count, duration=round(duration, 4),
                  timestamp_kind="nominal CFR (index/fps)")

    controls = list(controls) if controls else spread_controls(events, duration, count=control_count,
                                                               before=before, after=after)
    cap = open_video(video)
    try:
        control_rows = measure_controls(cap, controls, cloth, fps)
        floor = control_floor(control_rows)
        ball_peaks = sorted(r["ball_scale_peak"] for r in control_rows
                            if r.get("ball_scale_peak") is not None)
        ball_floor = float(np.quantile(ball_peaks, CONTROL_QUANTILE)) if ball_peaks else None
        rows = []
        for event in events:
            samples = sample_window(cap, event["t"], fps, before=before, after=after, sample_fps=sample_fps)
            if len(samples) < 3:
                rows.append(dict(**event, error="too few frames decoded"))
                continue
            profile = window_profile(samples, cloth)
            apply_footprint(profile, event["t"], floor=ball_floor)
            verdict, offset = classify_event(profile, event["t"], floor)
            rows.append(dict(
                **{k: event[k] for k in ("id", "t", "kind", "source", "origin", "position")},
                window=[round(event["t"] - before, 3), round(event["t"] + after, 3)],
                peak=profile["peak"], median=profile["median"], still_floor=profile["still_floor"],
                flow_peak=profile["flow_peak"], flow_median=profile["flow_median"],
                peak_at=profile["peak_at"], peak_offset_s=offset,
                centroid=profile["centroid"], onset=profile["onset"], finish=profile["finish"],
                excess_ratio=profile["excess_ratio"], changed_frac=profile["changed_frac"],
                p99=profile["p99"], occlusion=profile["occlusion"],
                ball_scale_peak=profile["ball_scale_peak"], ball_scale_at=profile["ball_scale_at"],
                ball_scale_pairs=profile["ball_scale_pairs"],
                ball_scale_offset_s=profile["ball_scale_offset_s"],
                ball_scale_verdict=profile["ball_scale_verdict"],
                samples=len(samples), pairs=len(profile["pairs"]),
                verdict=verdict,
            ))
            if progress:
                progress(event, rows[-1])
    finally:
        cap.release()

    records = records_motion_check(records_path, events) if records_path else None

    cross_times = cross_times if cross_times else [60.0, 300.0, 900.0, 1700.0]
    cross = cross_check(video, cross_times, fps)
    event_cross = cross_check(video, [max(0.0, e["t"] - before) for e in events[:6]], fps)
    drift = drift_scan(video, step_s=drift_step, fps=fps)

    floor_flow = None
    flows = sorted(r["flow_peak"] for r in control_rows if r.get("flow_peak") is not None)
    if flows:
        floor_flow = float(np.quantile(flows, 0.5))

    return dict(
        video=str(video), queue=str(queue), quad=str(quad_path) if quad_path else None,
        timing=timing, window=dict(before=before, after=after, sample_fps=sample_fps),
        threshold=dict(ratio=MOTION_FLOOR_RATIO, absolute=MOTION_FLOOR_ABSOLUTE,
                       at_served_s=MOTION_AT_SERVED_S, still_quantile=STILL_QUANTILE,
                       control_quantile=CONTROL_QUANTILE,
                       peak=max((floor or 0.0) * MOTION_FLOOR_RATIO, MOTION_FLOOR_ABSOLUTE)),
        controls=dict(times=controls, rows=control_rows, floor_peak=floor, floor_flow=floor_flow,
                      ball_floor=ball_floor,
                      still_floors=sorted(r["still_floor"] for r in control_rows
                                          if r.get("still_floor") is not None),
                      ball_peaks=ball_peaks),
        events=rows,
        records_motion=records,
        cross_check=cross,
        event_window_start_cross_check=event_cross,
        drift_scan=drift,
        counts=dict(
            total=len(rows),
            at_served=sum(1 for r in rows if r.get("verdict") == "motion at the served time"),
            elsewhere=sum(1 for r in rows if r.get("verdict") == "motion elsewhere in window"),
            none=sum(1 for r in rows if r.get("verdict") == "no motion anywhere in window"),
            ball_at_served=sum(1 for r in rows
                               if r.get("ball_scale_verdict") == "ball-scale motion at the served time"),
            ball_elsewhere=sum(1 for r in rows
                               if r.get("ball_scale_verdict") == "ball-scale motion elsewhere in window"),
            ball_none=sum(1 for r in rows if r.get("ball_scale_verdict") == "no ball-scale motion in window"),
            ball_not_separable=sum(1 for r in rows
                                   if r.get("ball_scale_verdict") == "ball-scale signal not separable from controls"),
            large_footprint_peaks=sum(1 for r in rows
                                      if (r.get("changed_frac") or 0) > BALL_FOOTPRINT_MAX),
        ),
    )


def print_report(report):
    timing = report["timing"]
    print(f"video {report['video']}")
    print(f"  {timing['fps']:.6f} fps · {timing['frame_count']} frames · "
          f"{timing['duration']:.3f} s · {timing['timestamp_kind']}")
    print(f"window ±{-report['window']['before']}/{report['window']['after']} s at "
          f"{report['window']['sample_fps']:g} fps · cloth-mean gray diff")
    threshold = report["threshold"]
    print(f"motion threshold: peak >= {threshold['peak']:.3f} "
          f"(control still floor {report['controls']['floor_peak']} x {threshold['ratio']}, "
          f"min {threshold['absolute']})")
    still = report["controls"]["still_floors"]
    print(f"controls ({len(report['controls']['rows'])}): still floor min {still[0] if still else None} · "
          f"median {report['controls']['floor_peak']} · max {still[-1] if still else None} · "
          f"flow median {report['controls']['floor_flow']}")
    print()
    header = (f"{'t (s)':>9} {'kind':>6} {'peak':>8} {'med':>6} {'chg%':>6} {'occ':>6} "
              f"{'at':>8} {'off':>7} {'flowpk':>7} {'ballpk':>7} {'ball@':>8}   verdict / footprint")
    print(header)
    print("-" * len(header))
    for row in report["events"]:
        if row.get("error"):
            print(f"{row['t']:9.3f} {str(row.get('kind')):>6}  {row['error']}")
            continue
        print(f"{row['t']:9.3f} {str(row.get('kind')):>6} {row['peak']:8.3f} {row['median']:6.2f} "
              f"{100 * (row['changed_frac'] or 0):6.1f} {row['occlusion']:6.3f} {str(row['peak_at']):>8} "
              f"{str(row['peak_offset_s']):>7} {row['flow_peak']:7.2f} {str(row['ball_scale_peak']):>7} "
              f"{str(row['ball_scale_at']):>8}   {row['ball_scale_verdict']}")
    counts = report["counts"]
    print()
    print(f"cloth-motion proxy: at served time {counts['at_served']} · elsewhere in window {counts['elsewhere']} "
          f"· no motion anywhere {counts['none']} (of {counts['total']})")
    print(f"footprint at the peak pair: large (person-scale) on {counts['large_footprint_peaks']} "
          f"of {counts['total']} events (threshold {BALL_FOOTPRINT_MAX:.0%} of the cloth)")
    print(f"ball-scale peak threshold: {BALL_PEAK_MIN:g} levels "
          f"(control floor for the same statistic {report['controls']['ball_floor']})")
    print(f"ball-scale read: at served time {counts['ball_at_served']} · elsewhere "
          f"{counts['ball_elsewhere']} · none in window {counts['ball_none']} · "
          f"NOT SEPARABLE from controls {counts['ball_not_separable']} (of {counts['total']})")
    print()
    cross = report["cross_check"]
    print("two-timebase cross-check (frame-index seek vs container-time seek):")
    print(f"{'t (s)':>9} {'index':>7} {'idx path':>9} {'time path':>10} {'frames apart':>13} "
          f"{'time gap s':>11} {'drift s':>9} {'SSIM':>7} {'ident':>6}")
    for row in cross["rows"]:
        if row.get("error"):
            print(f"{row['t']:9.3f}  {row['error']}")
            continue
        print(f"{row['t']:9.3f} {row['frame_index']:7d} {row['index_path']['index']:9d} "
              f"{row['time_path']['index']:10d} {row['frames_apart']:13d} {row['time_gap_s']:11.4f} "
              f"{row['drift_s']:9.4f} {row['ssim']:7.5f} {str(row['identical']):>6}")
    print(f"  all identical: {cross['all_identical']} · max |drift|: {cross['max_abs_drift_s']} s · "
          f"max frames apart: {cross['max_abs_frames_apart']}")
    records = report.get("records_motion")
    if records:
        print()
        print(f"the scan's own trigger signal ({records['path']}, {records['sample_count']} samples, "
              f"{records['step_s']:g} s step, reach ±{records['reach_s']:g} s):")
        print(f"  {'t (s)':>9} {'nearest':>8} {'motion':>8} {'off':>7} {'peak at':>8} {'peak':>8} {'off':>7}   nearest is local peak")
        for row in records["events"]:
            if not row.get("in_reach"):
                print(f"  {row['t']:9.3f}  outside the records")
                continue
            print(f"  {row['t']:9.3f} {row['nearest_t']:8.3f} {row['nearest_motion']:8.3f} "
                  f"{row['nearest_offset_s']:7.3f} {row['peak_t']:8.3f} {row['peak_motion']:8.3f} "
                  f"{row['peak_offset_s']:7.3f}   {row['all_below_nearest']}")
        print(f"  the nearest sample is the local maximum for {records['nearest_is_peak']} of "
              f"{len(records['events'])} events · max |peak offset| {records['max_abs_peak_offset_s']} s")
    drift = report["drift_scan"]
    print(f"drift scan over {drift['frame_count']} frames ({len(drift['samples'])} samples, "
          f"{drift['step_s']:g} s step): max |PTS - nominal| = {drift['max_abs_drift_s']} s, "
          f"last = {drift['last_drift_s']} s")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", default="data/vod_30min_260815.mp4")
    ap.add_argument("--queue", default="out/scan30/events.json", help="served queue artifact")
    ap.add_argument("--quad", default="out/scan30/corners.json")
    ap.add_argument("--anchors", default="out/pid_anchors_vod30.json")
    ap.add_argument("--before", type=float, default=CLIP_BEFORE_S)
    ap.add_argument("--after", type=float, default=CLIP_AFTER_S)
    ap.add_argument("--sample-fps", type=float, default=SAMPLE_FPS)
    ap.add_argument("--controls", default=None, help="explicit control timestamps, comma separated")
    ap.add_argument("--control-count", type=int, default=12)
    ap.add_argument("--drift-step", type=float, default=30.0)
    ap.add_argument("--cross-times", default=None, help="cross-check timestamps, comma separated")
    ap.add_argument("--records", default="out/scan30/records.json",
                    help="the scan's own per-sample records, for the trigger check")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--report", default="out/scan30/timing_verify.json")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    started = time.time()

    def progress(event, row):
        if not args.quiet:
            print(f"  measured t={row['t']:9.3f} peak={row['peak']} offset={row['peak_offset_s']} "
                  f"{row['verdict']}", file=sys.stderr)

    report = analyze(args.video, args.queue, quad_path=args.quad, anchors_path=args.anchors,
                     before=args.before, after=args.after, sample_fps=args.sample_fps,
                     controls=parse_times(args.controls), control_count=args.control_count,
                     drift_step=args.drift_step, cross_times=parse_times(args.cross_times),
                     limit=args.limit, progress=progress)
    report["seconds"] = round(time.time() - started, 2)
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
    if not args.quiet:
        print_report(report)
        print(f"\nreport: {args.report} ({report['seconds']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
