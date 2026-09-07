"""Full PoC pipeline: single-camera frame -> SAM3 ball segmentation ->
homography -> 2D top-down recreation.

For each selected timestamp of the VOD:
  1. classical table detection (cloth quad) -> homography H (image -> canonical)
  2. SAM3 open-vocab text prompt "billiard ball" -> instance masks
  3. filter / classify balls (color, cue/solid/stripe)
  4. project ball centers through H into canonical table coordinates
  5. render: original+masks | bird's-eye rectified table | schematic 2D recreation
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ball_detect import BALL_COLORS, detect_ball_candidates
from sam3_cpu import load_sam3_image_model, make_processor
from table_detect import detect_table

# Rasson Victory III, 9 ft: playing surface 2540 x 1270 mm (100" x 50", WPA).
# Canonical frame is in MILLIMETRES, portrait: width 1270 (x, left-right),
# length 2540 (y, head at top, foot at bottom) -- matches the camera view.
CANON_W, CANON_H = 1270, 2540  # mm
CANON_BALL_R = 28.6  # mm (57.15 mm ball)
POCKET_R = 24
MIN_SCORE = 0.62

# BGR renders for ball colors
RENDER_COLORS = {
    "white": (245, 245, 245),
    "yellow": (0, 210, 250),
    "blue": (230, 110, 30),
    "red": (60, 60, 235),
    "purple": (200, 80, 150),  # this set: pink
    "pink": (180, 105, 235),
    "brown": (30, 65, 120),
    "orange": (20, 140, 255),
    "green": (60, 180, 60),
    "maroon": (40, 40, 130),
    "black": (25, 25, 25),
}
SOLID_MAP = ["white", "yellow", "blue", "red", "purple", "orange", "green", "maroon", "black"]


def extract_frame(video_path: str, t_sec: float) -> np.ndarray:
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, t_sec * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"could not read frame at t={t_sec}")
    return frame


def homography_to_canonical(corners: np.ndarray) -> np.ndarray:
    """Map the cloth quad [TL, TR, BR, BL] to the canonical table.

    The canonical frame is width x length = CANON_W x CANON_H, oriented like
    the camera view: head rail at the top, foot rail at the bottom, left long
    rail on the left.  TL -> (0,0) [head-left], TR -> (W,0) [head-right],
    BR -> (W,H) [foot-right], BL -> (0,H) [foot-left].  The long rails run
    vertically (x=0 and x=W) and the side pockets sit at their midpoints.
    """
    dst = np.array(
        [[0, 0], [CANON_W - 1, 0], [CANON_W - 1, CANON_H - 1], [0, CANON_H - 1]],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(corners.astype(np.float32), dst)


def classify_ball(bgr: np.ndarray, mask: np.ndarray) -> dict:
    """Classify a ball mask region: dominant color + cue/solid/stripe.

    Sampling is biased to the inner 60% of the disc to avoid cloth/shadow
    contamination at the mask border.  Style is decided from the white/colored
    pixel fractions: stripes have a large white area (base ball colour),
    solids are mostly coloured, the cue ball is white, the 8-ball is dark.
    """
    ys, xs = np.where(mask > 0)
    if len(xs) < 30:
        return {"color": "unknown", "style": "unknown"}
    cx, cy = xs.mean(), ys.mean()
    r = max(2.0, np.sqrt(len(xs) / np.pi))
    yy, xx = np.mgrid[0:mask.shape[0], 0:mask.shape[1]]
    inner = ((xx - cx) ** 2 + (yy - cy) ** 2) <= (0.6 * r) ** 2
    inner &= mask > 0
    if inner.sum() < 20:
        inner = mask > 0

    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    roi = bgr[y0:y1, x0:x1]
    m_roi = inner[y0:y1, x0:x1]
    if roi.size == 0 or m_roi.sum() == 0:
        return {"color": "unknown", "style": "unknown"}
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    px = hsv[m_roi]
    h, s, v = px[:, 0].astype(int), px[:, 1].astype(int), px[:, 2].astype(int)
    n = max(1, len(h))

    frac_white = float(((s < 65) & (v > 150)).sum()) / n
    frac_black = float(((v < 70) & (s < 70)).sum()) / n
    colored = (s >= 65) & (v >= 60)
    frac_colored = float(colored.sum()) / n

    # 8-ball / dark balls
    if frac_black > 0.2 and frac_colored < 0.15:
        return {"color": "black", "style": "solid"}
    # cue ball
    if frac_white > 0.55 and frac_colored < 0.25:
        return {"color": "white", "style": "cue"}

    if colored.sum() < 12:
        return {"color": "unknown", "style": "unknown"}
    hc = h[colored]
    mean_v = float(v[colored].mean())

    buckets = {
        "yellow": int(((hc >= 15) & (hc <= 38)).sum()),
        "blue": int(((hc >= 90) & (hc <= 125)).sum()),
        "red": int(((hc < 10) | (hc >= 170)).sum()),
        "pink": int(((hc >= 155) & (hc < 170)).sum()),
        "purple": int(((hc >= 125) & (hc < 155)).sum()),
        "orange": int(((hc >= 8) & (hc <= 24)).sum()),
        "green": int(((hc >= 40) & (hc <= 80)).sum()),
        "brown": int(((hc >= 5) & (hc <= 25)).sum()),
        "maroon": int(((hc < 5) & (hc >= 0)).sum()),
    }
    color = max(buckets, key=buckets.get)
    if buckets[color] == 0:
        return {"color": "unknown", "style": "unknown"}
    if color in ("red", "maroon"):
        color = "maroon" if mean_v < 115 else "red"
    if color == "brown" and mean_v > 150:
        color = "orange"

    # style from white/coloured fractions
    if frac_white > 0.28 and 0.15 < frac_colored < 0.78:
        style = "stripe"
    elif frac_colored > 0.55:
        style = "solid"
    elif frac_white > 0.4:
        style = "cue"
    else:
        style = "solid"
    return {"color": color, "style": style}


def ball_center(mask: np.ndarray) -> tuple[float, float, float]:
    """Return (cx, cy, r) via min enclosing circle of the mask contour."""
    m = (mask > 0).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return float(mask.shape[1] / 2), float(mask.shape[0] / 2), 1.0
    c = max(cnts, key=cv2.contourArea)
    (x, y), r = cv2.minEnclosingCircle(c)
    return float(x), float(y), float(r)


def filter_instances(state, cloth_mask, bgr) -> list[dict]:
    masks = state["masks"].cpu().numpy()
    boxes = state["boxes"].cpu().numpy()
    scores = state["scores"].cpu().numpy()
    cloth = cloth_mask > 0
    out = []
    for i in range(len(scores)):
        if scores[i] < MIN_SCORE:
            continue
        m = np.squeeze(masks[i])
        area = float(m.sum())
        if area < 60 or area > 6000:
            continue
        cx, cy, r = ball_center(m)
        # require most of the mask to lie on the cloth (tolerant of mask
        # bleeding onto neighbouring balls in a tight rack)
        overlap = float((m & cloth).sum()) / max(1.0, area)
        if overlap < 0.5:
            continue
        x0, y0, x1, y1 = boxes[i]
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0 or not (0.5 < h / w < 1.6):
            continue
        if r < 4.0 or r > 60.0:
            continue
        cls = classify_ball(bgr, m)
        out.append(
            {
                "cx": cx,
                "cy": cy,
                "r": r,
                "score": float(scores[i]),
                "area": area,
                **cls,
            }
        )
    return out


def render_panels(bgr, corners, masks_overlay, balls, H, out_dir, t_sec):
    # left: original + masks
    left = bgr.copy()
    for b in masks_overlay:
        m = b["mask"]
        color = RENDER_COLORS.get(b["color"], (0, 255, 0))
        left[m] = (left[m] * 0.5 + np.array(color, dtype=np.uint8) * 0.5).astype(np.uint8)
        cv2.circle(left, (int(b["cx"]), int(b["cy"])), int(b["r"]), color, 2)
    cv2.polylines(left, [corners.astype(np.int32)], True, (0, 0, 255), 3)
    cv2.putText(left, f"t={t_sec}s  {len(balls)} balls",
                (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 255), 3)

    # middle: bird's-eye rectified table
    rect = cv2.warpPerspective(bgr, H, (CANON_W, CANON_H))
    for b in balls:
        cv2.circle(rect, (int(b["tx"]), int(b["ty"])), int(b["tr"]), (0, 0, 255), 2)
    cv2.putText(rect, "bird's-eye (rectified)", (30, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)

    # right: schematic 2D recreation
    rec = draw_recreation(balls)

    canvas = np.hstack([cv2.resize(left, (640, 360)), cv2.resize(rect, (640, 360)),
                        cv2.resize(rec, (640, 360))])
    path = Path(out_dir) / f"panel_{t_sec:06.1f}s.png"
    cv2.imwrite(str(path), canvas)
    return path


def draw_recreation(balls) -> np.ndarray:
    rec = np.full((CANON_H, CANON_W, 3), (90, 160, 90), dtype=np.uint8)
    # pockets
    pts = [(0, 0), (CANON_W - 1, 0), (CANON_W - 1, CANON_H - 1), (0, CANON_H - 1),
           (0, CANON_H // 2), (CANON_W - 1, CANON_H // 2)]
    for p in pts:
        cv2.circle(rec, p, POCKET_R, (10, 10, 10), -1)
    cv2.rectangle(rec, (0, 0), (CANON_W - 1, CANON_H - 1), (40, 40, 40), 6)

    for b in balls:
        x, y, r = int(b["tx"]), int(b["ty"]), int(b["tr"])
        color = RENDER_COLORS.get(b["color"], (200, 200, 200))
        if b.get("style") == "stripe" and b["color"] != "white":
            cv2.circle(rec, (x, y), r, (245, 245, 245), -1)
            band = int(r * 0.55)
            cv2.rectangle(rec, (x - r, y - band), (x + r, y + band), color, -1)
        elif b["color"] == "black":
            cv2.circle(rec, (x, y), r, (25, 25, 25), -1)
            cv2.circle(rec, (x, y), int(r * 0.8), (60, 60, 60), -1)
        else:
            cv2.circle(rec, (x, y), r, color, -1)
            cv2.circle(rec, (x - int(r * 0.3), y - int(r * 0.3)), max(1, int(r * 0.25)),
                       (255, 255, 255), -1)
        cv2.circle(rec, (x, y), r, (20, 20, 20), 1)
    cv2.putText(rec, "2D recreation (projected)", (30, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.3, (240, 240, 240), 3)
    return rec


def process_frame(video_path, t_sec, model, proc, out_dir, fixed_corners=None) -> dict | None:
    bgr = extract_frame(video_path, t_sec)
    tab = detect_table(bgr)
    # the table must actually be visible (guards intro/outro scenes)
    if int(tab["mask"].sum()) < 0.01 * bgr.shape[0] * bgr.shape[1]:
        return None
    if fixed_corners is not None:
        corners = np.asarray(fixed_corners, dtype=np.float32)
    else:
        if tab["corners"] is None:
            return None
        corners = tab["corners"]
    H = homography_to_canonical(corners)

    from PIL import Image
    state = proc.set_image(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
    state = proc.set_text_prompt("billiard ball", state)

    balls = filter_instances(state, tab["mask"], bgr)
    # project ball centers through the homography into canonical table coords.
    # A top-down recreation must use a constant ball radius (perspective makes
    # near balls look bigger in the image); 57.15mm on a 2540mm-wide table.
    CANON_BALL_R = 28.6  # mm
    result_balls = []
    for b in balls:
        p = H @ np.array([b["cx"], b["cy"], 1.0])
        tx, ty = p[0] / p[2], p[1] / p[2]
        b["tx"], b["ty"], b["tr"] = float(tx), float(ty), CANON_BALL_R
        result_balls.append(b)

    masks_all = state["masks"].cpu().numpy()
    masks_overlay = [
        {"mask": np.squeeze(masks_all[i]) > 0, "cx": b["cx"], "cy": b["cy"],
         "r": b["r"], "color": b["color"]}
        for i, b in enumerate(balls)
    ]

    panel_path = render_panels(bgr, corners, masks_overlay, result_balls, H, out_dir, t_sec)
    return {
        "t": t_sec,
        "corners": corners.tolist(),
        "balls": [
            {"color": b["color"], "style": b["style"], "score": b["score"],
             "img": [round(b["cx"], 1), round(b["cy"], 1)],
             "table": [round(b["tx"], 1), round(b["ty"], 1)]}
            for b in result_balls
        ],
        "panel": str(panel_path),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="data/vod_250725_break_run.mp4")
    ap.add_argument("--out", default="out/run1")
    ap.add_argument("--every", type=float, default=20.0)
    ap.add_argument("--start", type=float, default=5.0)
    ap.add_argument("--end", type=float, default=375.0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--corners", default=None, help="JSON file with fixed table corners (camera is static)")
    args = ap.parse_args()

    torch.set_num_threads(args.threads)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    fixed_corners = None
    if args.corners:
        fixed_corners = json.load(open(args.corners))["corners"]
        print("using fixed corners:", fixed_corners, flush=True)

    model = load_sam3_image_model("data/sam3.safetensors")
    model.float()
    proc = make_processor(model)

    times = np.arange(args.start, args.end + 1e-9, args.every).tolist()
    results = []
    for t_sec in times:
        t0 = time.time()
        try:
            r = process_frame(args.video, t_sec, model, proc, out_dir, fixed_corners)
            if r is None:
                print(f"t={t_sec}: NO TABLE", flush=True)
                continue
            results.append(r)
            nb = len(r["balls"])
            print(f"t={t_sec}: {nb} balls in {time.time()-t0:.0f}s", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"t={t_sec}: ERROR {type(e).__name__}: {e}", flush=True)
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=1)
    print(f"done: {len(results)} frames -> {out_dir}", flush=True)


if __name__ == "__main__":
    main()
