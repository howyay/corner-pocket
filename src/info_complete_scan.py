"""Info-complete gated event scan.

A frame is "info complete" (IC) only when the table and its balls are fully
observable: no person intersecting the cloth, stable exposure, cloth area in
band, and a ball census matching the recent mode. All transient inference
(shot/pot candidates) derives from diffs of TEMPORALLY ADJACENT IC frames —
pairs with a larger gap are skipped, because balls may have moved while the
table was occluded.

Evidence per candidate: matched same-color ball displacement in table
millimeters via the calibrated homography (shots), or a matched ball that
vanishes from the cloth (pots). No accuracy claims: these are candidates for
human review, same as the rest of the workbench.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import sys
import time
from typing import Iterator

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import homography_to_canonical, CANON_W, CANON_H  # noqa: E402
from src.table_detect import detect_table  # noqa: E402
from src.ball_detect import detect_ball_candidates  # noqa: E402

SHOT_SPEED_MM_S = 500.0   # candidate: matched ball speed >= 0.5 m/s
SHOT_DISP_MM = 150.0      # absolute floor against pixel jitter
MAX_SPEED_MM_S = 11000.0  # above this the 'match' is two different balls
POT_REFRACT_S = 3.0       # same color near same spot within 3s = one pot
POT_PERSIST_PAIRS = 3     # vanish must survive this many consecutive pairs
CLOTH_BAND = (0.85, 1.15)
BRIGHTNESS_DELTA_MAX = 6.0
BALL_BAND = 2
PERSON_EVERY = 5
PERSON_HOLD = 8
PAIR_GAP = (0.0, 2.0)
MATCH_RADIUS_FACTOR = 3.0
MIN_BALL_AREA = 14.0
MAX_BALL_AREA = 9000.0


@dataclass
class GateConfig:
    person_every: int = PERSON_EVERY
    person_hold: int = PERSON_HOLD
    cloth_band: tuple = CLOTH_BAND
    brightness_delta_max: float = BRIGHTNESS_DELTA_MAX
    ball_band: int = BALL_BAND
    census_window: int = 30
    pair_gap: tuple = PAIR_GAP
    match_radius_factor: float = MATCH_RADIUS_FACTOR
    pot_persist_pairs: int = POT_PERSIST_PAIRS
    pot_refract_s: float = POT_REFRACT_S
    min_ball_area: float = MIN_BALL_AREA
    max_ball_area: float = MAX_BALL_AREA


@dataclass
class ICState:
    """Rolling gate state across the scan."""
    last_gray: np.ndarray | None = None
    last_brightness: float | None = None
    cloth_ref: float | None = None
    census: list = field(default_factory=list)
    person_hold_frames: int = 0
    last_ic: dict | None = None
    last_ic_t: float | None = None
    frame_index: int = 0
    pot_pending: list = field(default_factory=list)
    last_cands: list = field(default_factory=list)


def person_boxes_fn():
    """Lazy YOLO person detector on the full frame; returns xyxy boxes."""
    from ultralytics import YOLO
    model = YOLO(str(ROOT / 'yolov8n.pt'))

    def detect(bgr):
        result = model.predict(bgr, classes=[0], device='cuda' if __import__('torch').cuda.is_available() else 'cpu', verbose=False)[0]
        return result.boxes.xyxy.cpu().tolist()
    return detect


def gate_reason(state: ICState, bgr, small, cloth_mask, persons_on_table: bool,
                n_balls: int, brightness: float, cfg: GateConfig) -> str | None:
    """Return None when the frame is info complete, else the blocking reason."""
    if persons_on_table:
        return 'person_on_table'
    if state.cloth_ref is None:
        return 'warming_up'
    area = float(cloth_mask.sum())
    if not cfg.cloth_band[0] * state.cloth_ref <= area <= cfg.cloth_band[1] * state.cloth_ref:
        return 'cloth_area_out_of_band'
    if state.last_brightness is not None and abs(brightness - state.last_brightness) > cfg.brightness_delta_max:
        return 'exposure_shift'
    if state.census:
        mode = float(np.median(state.census[-cfg.census_window:]))
        if n_balls < mode - cfg.ball_band:
            # Only a falling count can mean occlusion; extra candidates are
            # shadows/reflections and never hide the truth.
            return 'ball_census_off'
    return None


def match_balls(prev_cands, cur_cands, radius_px: float) -> tuple[list, list, list]:
    """Match balls between two IC frames in two stages.

    Stage 1: greedy same-color nearest-neighbor within radius_px — tracks
    stationary and slow balls. Stage 2: same-color leftovers match when the
    assignment is unambiguous (exactly one leftover of that color on each
    side) regardless of distance — a fast ball travels far more than its own
    radius between frames, and the pair still measures its displacement.
    Returns (matched [(prev, cur, dist_px)], unmatched_prev, unmatched_cur).
    """
    matched, used_prev, used_cur = [], set(), set()
    pairs = []
    for i, p in enumerate(prev_cands):
        for j, c in enumerate(cur_cands):
            if p['color'] != c['color']:
                continue
            d = math.hypot(p['cx'] - c['cx'], p['cy'] - c['cy'])
            if d <= radius_px:
                pairs.append((d, i, j))
    for d, i, j in sorted(pairs):
        if i in used_prev or j in used_cur:
            continue
        matched.append((prev_cands[i], cur_cands[j], d))
        used_prev.add(i)
        used_cur.add(j)
    prev_left = [p for i, p in enumerate(prev_cands) if i not in used_prev]
    cur_left = [c for j, c in enumerate(cur_cands) if j not in used_cur]
    for p in prev_left:
        same = [c for c in cur_left if c['color'] == p['color']]
        # Only genuinely unique colors may match at range: the white class
        # covers the cue ball AND stripe whites, so counts > 1 are ambiguous.
        if len(same) != 1:
            continue
        if sum(1 for q in prev_cands if q['color'] == p['color']) != 1:
            continue
        if sum(1 for q in cur_cands if q['color'] == p['color']) != 1:
            continue
        c = same[0]
        matched.append((p, c, math.hypot(p['cx'] - c['cx'], p['cy'] - c['cy'])))
        cur_left.remove(c)
    unmatched_prev = [p for p in prev_left if all(m[0] is not p for m in matched)]
    return (matched, unmatched_prev, cur_left)


def to_table_mm(H, cx, cy):
    p = H @ np.array([cx, cy, 1.0], np.float64)
    if abs(p[2]) < 1e-9:
        return None
    return [float(p[0] / p[2]), float(p[1] / p[2])]


def scan_info_complete(video: str, corners: np.ndarray, cfg: GateConfig = GateConfig(),
                       frame_stride: int = 1, max_frames: int | None = None,
                       persons=None, progress=lambda step, detail: None) -> dict:
    """Scan the video; return candidates and honest gate statistics.

    persons: injectable person-box detector (tests); default lazy YOLO.
    """
    state = ICState()
    if persons is None:
        persons = person_boxes_fn()
    # Work in 960x540 space throughout: candidates, corners, homography.
    # The stored corners files predate the per-axis scaling fix, so self-estimate.
    corners_list = []
    H = None
    reject = {}
    candidates = []
    ic_frames = 0
    total = 0
    pair_count = 0

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    t_start = time.time()
    while True:
        ok, bgr = cap.read()
        if not ok or (max_frames is not None and total >= max_frames):
            break
        if state.frame_index % frame_stride:
            state.frame_index += 1
            continue
        t = state.frame_index / fps
        total += 1
        small = cv2.resize(bgr, (960, 540))
        tab = detect_table(small)
        cloth_mask = tab['mask']
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        cands = detect_ball_candidates(small, cloth_mask, cfg.min_ball_area, cfg.max_ball_area)
        if tab['corners'] is not None:
            corners_list.append(np.array(tab['corners'], np.float32))
            if H is None and len(corners_list) >= 30:
                median = np.median(np.array(corners_list), axis=0)
                H = homography_to_canonical(median)

        if H is None and len(corners_list) >= 30:
            H = homography_to_canonical(np.median(np.array(corners_list), axis=0))
        if H is None:
            reject['warming_up'] = reject.get('warming_up', 0) + 1
            state.frame_index += 1
            continue

        person_on_table = False
        if state.frame_index % cfg.person_every == 0 or state.person_hold_frames > 0:
            if state.frame_index % cfg.person_every == 0:
                boxes = persons(bgr)
                if tab['corners'] is not None:
                    quad = np.array(tab['corners'], np.float32)
                    sx, sy = bgr.shape[1] / 960, bgr.shape[0] / 540
                    for x1, y1, x2, y2 in boxes:
                        box = np.array([[x1 / sx, y1 / sy], [x2 / sx, y1 / sy],
                                        [x2 / sx, y2 / sy], [x1 / sx, y2 / sy]], np.float32)
                        inter = _quad_box_overlap_area(quad, box)
                        if inter > 0.02 * cv2.contourArea(np.array(quad, np.int32)):
                            person_on_table = True
                            break
            state.person_hold_frames = cfg.person_hold if person_on_table else max(0, state.person_hold_frames - 1)
        else:
            person_on_table = state.person_hold_frames > 0

        reason = gate_reason(state, bgr, small, cloth_mask, person_on_table, len(cands), brightness, cfg)
        if state.cloth_ref is None and tab['corners'] is not None and not person_on_table:
            state.cloth_ref = float(cloth_mask.sum())
        if reason is None:
            if state.cloth_ref is not None:
                state.cloth_ref = 0.95 * state.cloth_ref + 0.05 * float(cloth_mask.sum())
            state.census.append(len(cands))
            # Streak continuity: a candidate seen within radius of the same
            # color last IC frame inherits its streak; brand-new ones start 1.
            for c in cands:
                best = None
                for pc in state.last_cands:
                    if pc['color'] == c['color']:
                        d = math.hypot(pc['cx'] - c['cx'], pc['cy'] - c['cy'])
                        if d <= 60.0 and (best is None or d < best[0]):
                            best = (d, pc)
                c['_streak'] = (best[1]['_streak'] + 1) if best else 1
            state.last_cands = cands
            ic_frames += 1
            snapshot = {'t': t, 'frame_index': state.frame_index, 'cands': cands}
            if state.last_ic is not None:
                gap = t - state.last_ic_t
                if cfg.pair_gap[0] <= gap <= cfg.pair_gap[1]:
                    pair_count += 1
                    shots, vanished = _pair_candidates(state.last_ic, snapshot, H, cfg, gap)
                    candidates.extend(shots)
                    for v in vanished:
                        v['pairs_missing'] = 1
                        state.pot_pending.append(v)
                    still_pending = []
                    for v in state.pot_pending:
                        reappeared = [c for c in cands if c['color'] == v['color']
                                      and math.hypot(c['cx'] - v['_px'], c['cy'] - v['_py']) <= cfg.match_radius_factor * max(c['r'], 8.0)]
                        if reappeared:
                            continue  # detection flicker, not a pot
                        v['pairs_missing'] += 1
                        if v['pairs_missing'] >= cfg.pot_persist_pairs:
                            dup = any(p_['color'] == v['color']
                                      and math.hypot(p_['last_mm'][0] - v['mm'][0], p_['last_mm'][1] - v['mm'][1]) < 60.0
                                      and v['t'] - p_['t'] < cfg.pot_refract_s
                                      for p_ in candidates if p_['type'] == 'pot')
                            if not dup:
                                candidates.append({'type': 'pot', 't': round(v['t'], 2),
                                                   'color': v['color'],
                                                   'last_mm': [round(v['mm'][0], 1), round(v['mm'][1], 1)],
                                                   'last_frame': v['frame']})
                        else:
                            still_pending.append(v)
                    state.pot_pending = still_pending
                state.last_ic = snapshot
                state.last_ic_t = t
            else:
                state.last_ic = snapshot
                state.last_ic_t = t
        else:
            reject[reason] = reject.get(reason, 0) + 1
            # Occlusion breaks adjacency: a hidden interval may hide ball motion.
            if reason in ('person_on_table', 'cloth_area_out_of_band', 'ball_census_off'):
                state.last_ic = None
                state.last_ic_t = None
        state.last_brightness = brightness
        state.frame_index += 1
        if total % 2000 == 0:
            progress('scanning', f'{state.frame_index}/{total_frames} frames, {ic_frames} IC, {len(candidates)} candidates')
    cap.release()
    return {
        'candidates': candidates,
        'stats': {
            'frames_processed': total,
            'frames_total': total_frames,
            'ic_frames': ic_frames,
            'pairs': pair_count,
            'reject_reasons': reject,
            'seconds': round(time.time() - t_start, 1),
            'fps_effective': round(total / max(0.1, time.time() - t_start), 1),
        },
    }


def _on_table(mm, margin=30.0):
    return -margin <= mm[0] <= CANON_W + margin and -margin <= mm[1] <= CANON_H + margin


def _quad_box_overlap_area(quad, box) -> float:
    inter = np.zeros((1, 1), np.float32)
    quad_i = quad.astype(np.int32)
    box_i = box.astype(np.int32)
    # Rasterize both masks on the bounding canvas — exact enough for a gate.
    x0 = int(min(quad_i[:, 0].min(), box_i[:, 0].min()))
    y0 = int(min(quad_i[:, 1].min(), box_i[:, 1].min()))
    x1 = int(max(quad_i[:, 0].max(), box_i[:, 0].max()))
    y1 = int(max(quad_i[:, 1].max(), box_i[:, 1].max()))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return 0.0
    qm = np.zeros((h, w), np.uint8)
    bm = np.zeros((h, w), np.uint8)
    cv2.fillPoly(qm, [quad_i - [x0, y0]], 1)
    cv2.fillPoly(bm, [box_i - [x0, y0]], 1)
    return float((qm & bm).sum())


def _pair_candidates(prev: dict, cur: dict, H, cfg: GateConfig, gap: float) -> tuple[list, list]:
    radius = cfg.match_radius_factor * max(
        [c['r'] for c in prev['cands'] + cur['cands']] or [10.0])
    matched, gone, appeared = match_balls(prev['cands'], cur['cands'], radius)
    out = []
    best = None
    for p, c, _ in matched:
        # Flicker guard: both endpoints must be established observations.
        if p.get('_streak', 1) < 2 or c.get('_streak', 1) < 2:
            continue
        a = to_table_mm(H, p['cx'], p['cy'])
        b = to_table_mm(H, c['cx'], c['cy'])
        if a is None or b is None:
            continue
        d = math.hypot(a[0] - b[0], a[1] - b[1])
        if best is None or d > best['disp_mm']:
            best = {'type': 'shot', 't': round((prev['t'] + cur['t']) / 2, 2),
                    'gap_s': round(gap, 2), 'disp_mm': round(d),
                    'speed_mm_s': round(d / gap),
                    'color': p['color'],
                    'from_mm': [round(a[0], 1), round(a[1], 1)],
                    'to_mm': [round(b[0], 1), round(b[1], 1)],
                    'from_frame': prev['frame_index'], 'to_frame': cur['frame_index']}
    if best and best['disp_mm'] >= SHOT_DISP_MM and best['speed_mm_s'] >= SHOT_SPEED_MM_S:
        if _on_table(best['from_mm']) and _on_table(best['to_mm']) and best['speed_mm_s'] <= MAX_SPEED_MM_S:
            out.append(best)
    vanished = []
    if len(gone) >= 3:
        return out, []  # simultaneous multi-vanish = setup/occlusion chaos
    for ball in gone:
        if ball.get('_streak', 1) < 3:
            continue  # never established: detection flicker, not a pot
        pos = to_table_mm(H, ball['cx'], ball['cy'])
        if pos is None or not _on_table(pos):
            continue
        vanished.append({'color': ball['color'], 'mm': pos, 'frame': prev['frame_index'], 't': cur['t'],
                         '_px': ball['cx'], '_py': ball['cy']})
    return out, vanished


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--video', default='data/vod_30min_260815.mp4')
    ap.add_argument('--corners', default='out/scan30/corners.json')
    ap.add_argument('--out', default='out/scan-ic')
    ap.add_argument('--stride', type=int, default=2, help='process every Nth frame')
    ap.add_argument('--max-frames', type=int, default=None)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    corners = np.array(json.load(open(args.corners))['corners'], np.float32)
    result = scan_info_complete(args.video, corners, frame_stride=args.stride,
                                max_frames=args.max_frames,
                                progress=lambda step, detail: print(f'{step}: {detail}', flush=True))
    shots = [c for c in result['candidates'] if c['type'] == 'shot']
    pots = [c for c in result['candidates'] if c['type'] == 'pot']
    (out_dir / 'events.json').write_text(json.dumps(result['candidates'], indent=1))
    (out_dir / 'stats.json').write_text(json.dumps(result['stats'], indent=1))
    print(json.dumps(result['stats'], indent=1))
    print(f'candidates: {len(shots)} shots, {len(pots)} pots -> {out_dir}')


if __name__ == '__main__':
    main()
