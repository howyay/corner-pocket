"""Demo: world-state ball permanence on a VOD segment.

Renders an annotated clip where every known ball keeps a slot in table
millimetres.  The slot survives a miss (COAST), an occluder (OCCLUDED), and even
a long gap (LOST); only pocket evidence retires it.  Observations come from the
trained YOLO11n-seg ball model; occluders come from YOLOv8n person boxes.

Usage:
  PYTHONPATH=. .venv/bin/python tools/ball_world_demo.py \
      --video data/vod_30min_260815.mp4 --start 1055 --seconds 30 --fps 15 \
      --weights /tmp/dshsess/yolo_runs/yolo11n-seg-ball/weights/best.pt \
      --out out/ball_world_demo
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

from src.ball_world import (ACTIVE, COAST, LOST, OCCLUDED, POTTED, Observation,
                            Table, World)
import src.frame_inference as fi
from src.frame_rate import FPS_FALLBACK
from src.color_names import UNKNOWN
from src import table_geometry, weight_pins

STATUS_COLOR = {ACTIVE: (0, 200, 0), COAST: (0, 215, 255), OCCLUDED: (0, 140, 255),
                LOST: (0, 0, 255), POTTED: (140, 140, 140)}
STATUS_MARK = {ACTIVE: "", COAST: "~", OCCLUDED: "?", LOST: "x", POTTED: "."}

#: A coarse palette in BGR.  A 13-px ball carries no reliable hue histogram:
#: the white cue ball reflects the blue cloth, and a red ball's white number
#: pulls its mean toward magenta.  Brightness-normalised nearest palette is the
#: robust read at this size; names are display and identity hints, not truth.
PALETTE = (("white", (235, 235, 235)), ("black", (35, 35, 35)),
           ("red", (45, 45, 175)), ("orange", (50, 145, 230)),
           ("yellow", (50, 205, 230)), ("green", (70, 165, 70)),
           ("blue", (185, 105, 50)), ("purple", (150, 80, 135)),
           ("maroon", (50, 35, 105)), ("pink", (150, 150, 230)))


def colour_name(bgr_samples: np.ndarray) -> str:
    """Nearest palette entry to the ball's mean colour, brightness-normalised."""
    if bgr_samples.size == 0:
        return UNKNOWN
    mean = bgr_samples.reshape(-1, 3).astype(np.float64).mean(axis=0)
    peak = float(mean.max()) or 1.0
    unit = mean / peak
    best_name, best_d = UNKNOWN, 1e9
    for name, bgr in PALETTE:
        ref = np.asarray(bgr, np.float64)
        ref = ref / (float(ref.max()) or 1.0)
        d = float(np.linalg.norm(unit - ref))
        if d < best_d:
            best_name, best_d = name, d
    return best_name


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Order four image points as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    order = pts[np.argsort(ang)]
    start = int(np.argmin(order.sum(axis=1)))
    order = np.roll(order, -start, axis=0)
    if order[1][0] < order[0][0]:          # ensure a consistent wind direction
        order = order[[0, 3, 2, 1]]
    return order


def ball_observations(result, frame, H):
    """Detections in image pixels -> table observations."""
    out = []
    if result.masks is None or result.boxes is None:
        return out
    polys = result.masks.xy
    confs = result.boxes.conf.cpu().numpy()
    for poly, conf in zip(polys, confs):
        if poly is None or len(poly) < 3:
            continue
        mask = np.zeros(frame.shape[:2], np.uint8)
        cv2.fillPoly(mask, [poly.astype(np.int32)], 255)
        inner = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
        ys, xs = np.where(inner > 0)
        if len(xs) < 4:
            continue
        samples = frame[ys, xs]
        name = colour_name(samples)
        cx, cy = float(poly[:, 0].mean()), float(poly[:, 1].mean())
        mm = cv2.perspectiveTransform(np.array([[[cx, cy]]], np.float32), H)[0][0]
        out.append(Observation(x_mm=float(mm[0]), y_mm=float(mm[1]),
                               color=name, conf=float(conf)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="data/vod_30min_260815.mp4")
    ap.add_argument("--start", type=float, default=1055.0)
    ap.add_argument("--seconds", type=float, default=40.0)
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--out", default="out/ball_world_demo")
    ap.add_argument("--person-weights", default=weight_pins.YOLO)
    ap.add_argument("--dataset", default="vod30")
    ap.add_argument("--seed-frames", type=int, default=10)
    ap.add_argument("--ball-conf", type=float, default=0.25)
    ap.add_argument("--gate-mm", type=float, default=55.0)
    ap.add_argument("--gate-slack", type=float, default=0.35)
    ap.add_argument("--bootstrap-gate-mm", type=float, default=90.0)
    args = ap.parse_args()

    from ultralytics import YOLO

    table = Table()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit("cannot open " + args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or FPS_FALLBACK
    cap.set(cv2.CAP_PROP_POS_MSEC, args.start * 1000.0)
    ok, frame0 = cap.read()
    if not ok:
        raise SystemExit("cannot read at start")

    detected = fi.detect_table_for_frame(frame0, dataset=args.dataset, root=".")
    if detected.get("corners") is None:
        raise SystemExit("no table quad on the first frame")
    raw = np.asarray(detected["corners"], np.float32).reshape(4, 2)
    # The refined detector returns TL, TR, BR, BL; keep that order when it holds,
    # otherwise rebuild it from the point angles.
    top_left, top_right, bottom_right, bottom_left = raw
    ordered = (top_left[1] <= max(bottom_left[1], bottom_right[1])
               and top_right[1] <= max(bottom_left[1], bottom_right[1])
               and top_left[0] < top_right[0])
    quad = raw if ordered else order_quad(raw)
    # TL, TR, BR, BL of the cloth map to the head rail at the top: the owner's destination.
    mm_rect = table_geometry.canonical_destination()
    H = cv2.getPerspectiveTransform(quad.astype(np.float32), mm_rect)
    H_inv = np.linalg.inv(H)
    far_scale = math.hypot(*(mm_rect[1] - mm_rect[0])) / math.hypot(*(quad[1] - quad[0]))
    near_scale = math.hypot(*(mm_rect[2] - mm_rect[3])) / math.hypot(*(quad[2] - quad[3]))
    print(json.dumps({"quad": quad.round(1).tolist(),
                      "mm_per_px_far": round(far_scale, 2),
                      "mm_per_px_near": round(near_scale, 2)}), flush=True)

    ball_model = YOLO(args.weights)
    person_model = YOLO(args.person_weights)
    # Warm both models: the first ROCm forward pays a kernel-autotune minute.
    ball_model.predict(frame0, imgsz=1280, conf=args.ball_conf, device=0, verbose=False)
    person_model.predict(frame0, imgsz=960, conf=0.3, classes=[0], device=0, verbose=False)
    print(json.dumps({"warm": True}), flush=True)

    world = World(table=table, gate_mm=args.gate_mm, gate_slack=args.gate_slack,
                  bootstrap_gate_mm=args.bootstrap_gate_mm)
    seeded = False
    seed_pool = []
    writer = None
    keep_every = max(1, int(round(fps / args.fps)))
    frame_i = 0
    rendered = 0
    rows = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_i % keep_every:
            frame_i += 1
            continue
        t = args.start + frame_i / fps
        frame_i += 1
        if t - args.start >= args.seconds:
            break

        rb = ball_model.predict(frame, imgsz=1280, conf=args.ball_conf, device=0, verbose=False)[0]
        rp = person_model.predict(frame, imgsz=960, conf=0.3, classes=[0], device=0, verbose=False)[0]
        person_boxes = [b.xyxy[0].tolist() for b in (rp.boxes or [])] if rp.boxes is not None else []

        def occluded(x_mm, y_mm, tt, _boxes=person_boxes):
            px = cv2.perspectiveTransform(np.array([[[x_mm, y_mm]]], np.float32), H_inv)[0][0]
            for x0, y0, x1, y1 in _boxes:
                if x0 - 4 <= px[0] <= x1 + 4 and y0 - 4 <= px[1] <= y1 + 4:
                    return True
            return False

        observations = ball_observations(rb, frame, H)
        if not seeded:
            # Seed from a short window: a ball behind a player on the first frame
            # still enters the known set.  Dedupe by table distance.
            for o in observations:
                if all(math.hypot(o.x_mm - p.x_mm, o.y_mm - p.y_mm) > 45.0 for p in seed_pool):
                    seed_pool.append(o)
            if rendered >= args.seed_frames and len(seed_pool) >= 1:
                world.seed(t, seed_pool)
                seeded = True
                print(json.dumps({"seeded_slots": len(world.slots), "t": round(t, 2),
                                  "colors": [o.color for o in seed_pool]}), flush=True)
            else:
                rendered += 1
                if writer is None:
                    writer = cv2.VideoWriter(str(out / "demo.mp4"),
                                             cv2.VideoWriter_fourcc(*"mp4v"),
                                             float(args.fps), (frame.shape[1], frame.shape[0]))
                vis0 = frame.copy()
                cv2.polylines(vis0, [quad.astype(np.int32)], True, (60, 60, 60), 1)
                cv2.putText(vis0, f"seeding {len(seed_pool)} balls  t={t:.1f}s", (8, 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
                writer.write(vis0)
                continue
        state = world.observe(t, observations, occluded)

        vis = frame.copy()
        cv2.polylines(vis, [quad.astype(np.int32)], True, (60, 60, 60), 1)
        for (px_mm, py_mm) in table.pockets:
            p = cv2.perspectiveTransform(np.array([[[px_mm, py_mm]]], np.float32), H_inv)[0][0]
            cv2.circle(vis, (int(p[0]), int(p[1])), 10, (90, 90, 90), 1)
        for slot in world.slots:
            if slot.status == POTTED:
                continue
            colour = STATUS_COLOR.get(slot.status, (255, 255, 255))
            trail = slot.history[-45:]
            if len(trail) > 1:
                pts = cv2.perspectiveTransform(
                    np.array([[[x, y] for _, x, y in trail]], np.float32), H_inv)[0].astype(np.int32)
                cv2.polylines(vis, [pts], False, colour, 1, cv2.LINE_AA)
            p = cv2.perspectiveTransform(np.array([[[slot.x, slot.y]]], np.float32), H_inv)[0][0]
            centre = (int(p[0]), int(p[1]))
            rad = 12 if slot.status == ACTIVE else 14
            cv2.circle(vis, centre, rad, colour, 2 if slot.status == ACTIVE else 3)
            label = f"{slot.index}{STATUS_MARK.get(slot.status, '')}"
            cv2.putText(vis, label, (centre[0] + 8, centre[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1, cv2.LINE_AA)
        counts = Counter(slot.status for slot in world.slots)
        hud = (f"t={t:6.1f}s  balls={len(world.slots)}  "
               f"active={counts.get(ACTIVE, 0)} coast={counts.get(COAST, 0)} "
               f"occluded={counts.get(OCCLUDED, 0)} lost={counts.get(LOST, 0)} "
               f"potted={counts.get(POTTED, 0)}")
        cv2.rectangle(vis, (0, 0), (vis.shape[1], 26), (0, 0, 0), -1)
        cv2.putText(vis, hud, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
        if writer is None:
            writer = cv2.VideoWriter(str(out / "demo.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                     min(args.fps, 15.0), (vis.shape[1], vis.shape[0]))
        writer.write(vis)
        rendered += 1
        rows.append({"t": round(t, 2), "observations": len(observations),
                     "statuses": {str(k): int(v) for k, v in counts.items()},
                     "events": len(world.events)})

    cap.release()
    if writer is not None:
        writer.release()
    summary = {"rendered": rendered, "start": args.start, "seconds": args.seconds,
               "fps": args.fps, "world": world.summary(),
               "events": world.events}
    (out / "metrics.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["world"], indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
