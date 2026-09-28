"""Fast ball labelling: the SAM3 teacher at a usable rate, and what it still needs.

Part A of the near-real-time workstream.  The requirement is 33 ms/frame at runtime,
which the 204 k-param TrackNet-style net already meets (15.5 ms/frame on the ROCm GPU).
The *labels* are the bottleneck: on this box SAM3's GPU build returns zero instances
(ROCm 6.4, gfx1201) and its verified CPU path costs ~40-48 s/frame, so 5,000 labels is
~62 CPU hours.  This module is the lever on that number.

**The diagnosis, measured** (see ``out/fast_ball_labels/agreement.json``): the CPU
45 s/frame splits into ~31-37 s of *vision encoder* and ~8-11 s of *grounding head*.
The encoder is the part that wants a GPU and the head is the part that is broken on
this GPU, so the two are separable:

``hybrid``
    the vision backbone on the GPU, the text encoder + grounding head on the CPU.
    The head's arithmetic stays exactly the verified CPU path -- same dtype, same
    kernels, same device -- so the instances it produces are the CPU instances, and
    that is checkable, not asserted (``agreement``).

``cpu``
    the untouched reference: ``src.sam3_cpu`` end to end.  Every hybrid result is
    reported next to this one on the same frames.

Nothing here writes to the queue, the gates or any production artifact.  The teacher
is still not ground truth: these are labels, and the overlays a human has to look at
are the only accuracy evidence.

The second half of the lever is not SAM3 at all -- ``prelabel`` runs the trained
student over many frames and keeps detections that persist across time (a ball is
there in the next frame, a cloth-edge artefact is not), turning the same 15 ms/frame
into a pre-labelled dataset with a review queue instead of a labelling bill.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

OUT = ROOT / "out" / "fast_ball_labels"
LABELS_OUT = ROOT / "out" / "tiny_ball_probe" / "new_labels.json"
CHECKPOINT = ROOT / "data" / "sam3.safetensors"
VIDEO = ROOT / "data" / "vod_30min_260815.mp4"

MIN_SCORE = 0.62                 # the production cut the delivered caches were written at
SPLIT_GAP_S = 5.0                # imported from tiny_ball_net's contract, stated once here
RECORD_MIN_SCORE = 0.30          # the teacher's raw score is recorded down to here
RESOLUTION = 1008                # SAM3's own input resolution; not tuned here
MATCH_TOL_PX = 6.0               # one-to-one gate for "the same instance"

MODES = ("hybrid", "cpu")


# ------------------------------------------------------------------ plumbing --

def to_device(obj, device):
    """Recursively move a nested backbone output onto ``device``.

    ``forward_image`` returns tensors, lists of them, and ``NestedTensor`` wrappers;
    ``.to()`` only exists on two of the three.
    """
    import torch
    if isinstance(obj, torch.Tensor):
        return obj.to(device=device)
    if isinstance(obj, dict):
        return {k: to_device(v, device) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_device(v, device) for v in obj]
    if isinstance(obj, tuple):
        return tuple(to_device(v, device) for v in obj)
    if hasattr(obj, "tensors") and hasattr(obj, "mask"):
        mask = obj.mask.to(device) if obj.mask is not None else None
        return type(obj)(obj.tensors.to(device), mask)
    return obj


def instances_from_state(state, min_score: float = MIN_SCORE) -> list:
    """``(x, y, r, score)`` per kept instance, in native pixels.

    Deliberately the same extraction ``src.sam3_ball_cache.detect_frame`` uses, so a
    count difference between two modes is a difference between the modes and not
    between two readings of the same masks.
    """
    from src.pipeline import ball_center

    scores = state["scores"].cpu().float().numpy()
    masks = state["masks"].cpu().float().numpy()
    rows = []
    for index in range(len(scores)):
        if float(scores[index]) < min_score:
            continue
        mask = np.squeeze(masks[index])
        cx, cy, radius = ball_center(mask)
        rows.append({"x": round(float(cx), 2), "y": round(float(cy), 2),
                     "r": round(float(radius), 2), "score": round(float(scores[index]), 4)})
    return rows


def match_rows(reference: list, candidate: list, tol_px: float = MATCH_TOL_PX) -> dict:
    """Greedy one-to-one match of two instance lists, in native pixels."""
    used = set()
    matched, errors = 0, []
    for row in candidate:
        best, best_d = None, None
        for index, ref in enumerate(reference):
            if index in used:
                continue
            distance = math.hypot(row["x"] - ref["x"], row["y"] - ref["y"])
            if best_d is None or distance < best_d:
                best, best_d = index, distance
        if best is not None and best_d <= tol_px:
            used.add(best)
            matched += 1
            errors.append(best_d)
    return {"matched": matched, "candidate": len(candidate), "reference": len(reference),
            "errors": errors,
            "counts_agree": len(candidate) == len(reference)}


def agreement(per_frame: dict, tol_px: float = MATCH_TOL_PX) -> dict:
    """Per-frame instance counts and positions: does the fast mode reproduce CPU SAM3?

    A frame counts as agreeing when the two modes return the **same number of
    instances**.  Positions are matched one-to-one at ``tol_px``; a mode that returns
    the right count of wrong places is not a labeller.
    """
    rows, agree, counts_ok = [], 0, 0
    for time_key in sorted(per_frame, key=float):
        frame = per_frame[time_key]
        result = match_rows(frame["cpu"], frame["other"], tol_px)
        same = result["counts_agree"]
        counts_ok += 1 if same else 0
        agree += 1 if (same and result["matched"] == result["reference"]) else 0
        rows.append({"t": float(time_key), "count_cpu": len(frame["cpu"]),
                     "count_other": len(frame["other"]), "counts_agree": same,
                     "matched": result["matched"],
                     "median_error_px": (round(float(np.median(result["errors"])), 2)
                                         if result["errors"] else None),
                     "max_error_px": (round(float(max(result["errors"])), 2)
                                      if result["errors"] else None)})
    return {"frames": len(rows), "frames_with_equal_counts": counts_ok,
            "frames_fully_matched": agree, "tol_px": tol_px, "per_frame": rows}


# -------------------------------------------------------------------- teacher --

class Sam3Labeller:
    """SAM3 with the encoder and the head allowed to live on different devices.

    One model instance serves both modes: ``set_mode`` moves the vision backbone and
    the head never moves.  Loading SAM3 twice would cost ~7 GB of host RAM and give
    the two modes two different sets of weights, which is not a comparison.
    """

    def __init__(self, checkpoint=CHECKPOINT, mode: str = "hybrid", resolution: int = RESOLUTION,
                 confidence: float = 0.5, encoder_device: str = "cuda", progress=print):
        import torch

        from src.sam3_cpu import load_sam3_image_model, make_processor

        self.encoder_device = encoder_device
        started = time.time()
        self.model = load_sam3_image_model(str(checkpoint), device="cpu")
        self.processor = make_processor(self.model, device="cpu", resolution=resolution)
        self.processor.confidence_threshold = confidence
        self.mode = None
        self.set_mode(mode)
        self.load_seconds = round(time.time() - started, 1)
        progress(f"SAM3 loaded in {self.load_seconds}s; "
                 f"encoder {self.encoder_device}, head cpu")

    def set_mode(self, mode: str) -> None:
        import torch
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        if mode == "hybrid":
            if not torch.cuda.is_available():
                raise RuntimeError("hybrid labelling needs a CUDA/ROCm device; use mode='cpu'")
            self.model.backbone.vision_backbone = self.model.backbone.vision_backbone.to(
                self.encoder_device)
        else:
            self.model.backbone.vision_backbone = self.model.backbone.vision_backbone.to("cpu")
        # `SAM3Image.device` is a property that reads the model's *first* parameter.
        # Moving the vision backbone to the GPU therefore silently moves the model's
        # idea of its own device with it, and the grounding head -- still on the CPU --
        # starts building GPU prompts.  Pin it back.
        self.model._device = torch.device("cpu")
        self.mode = mode

    def label_frame(self, bgr) -> dict:
        """Raw instances for one BGR frame, plus the time each stage took."""
        import torch
        from PIL import Image
        from torchvision.transforms import v2

        image = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        started = time.time()
        if self.mode == "hybrid":
            with torch.inference_mode():
                tensor = self.processor.transform(
                    v2.functional.to_image(image).to("cpu")).unsqueeze(0)
                backbone_out = self.model.backbone.forward_image(
                    to_device(tensor, self.encoder_device))
            state = {"backbone_out": to_device(backbone_out, "cpu"),
                     "original_height": int(bgr.shape[0]), "original_width": int(bgr.shape[1])}
            encoder_s = time.time() - started
            head_started = time.time()
            state = self.processor.set_text_prompt("billiard ball", state)
            head_s = time.time() - head_started
        else:
            state = self.processor.set_image(image)
            encoder_s = time.time() - started
            head_started = time.time()
            state = self.processor.set_text_prompt("billiard ball", state)
            head_s = time.time() - head_started
        return {"seconds": round(time.time() - started, 3),
                "encoder_s": round(encoder_s, 3), "head_s": round(head_s, 3),
                "instances": instances_from_state(state)}

    def label_times(self, times: list, threshold: float = MIN_SCORE) -> dict:
        rows = {}
        for t in times:
            bgr = frame_at(t)
            if bgr is None:
                continue
            result = self.label_frame(bgr)
            rows[round(float(t), 3)] = {
                "instances": [row for row in result["instances"] if row["score"] >= threshold],
                "all_instances": result["instances"],
                "seconds": result["seconds"], "encoder_s": result["encoder_s"],
                "head_s": result["head_s"]}
        return rows


def frozen_held(root=ROOT) -> list:
    """The held-out times training is scored on, frozen on first use.

    New labels must never land inside it: a labelling run that walked over the
    validation blocks would silently turn a held-out score into a training score.
    """
    from src.tiny_ball_net import SPLIT_GAP_S, split_blocks

    path = Path(root) / "out" / "tiny_ball_probe" / "held_frozen.json"
    if path.exists():
        return sorted(round(float(t), 3) for t in json.loads(path.read_text())["held"])
    times = sorted(existing_times(root))
    if not times:
        return []
    _train, held, _dropped = split_blocks(times, gap_s=SPLIT_GAP_S)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"held": held, "source_frames": len(times)}, indent=1))
    return sorted(held)


def frame_at(time_s: float, video=VIDEO):
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(time_s) * 1000.0)
    ok, bgr = cap.read()
    cap.release()
    return bgr if ok else None


def existing_times(root=ROOT) -> set:
    """Label times already in the caches, rounded the way the caches round them."""
    times = set()
    for name, key in (("sam3_census.json", "frames"), ("sam3_results.json", None)):
        path = Path(root) / "out" / "scan30" / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        frames = payload.get(key) if key else payload
        for t in (frames or {}):
            times.add(round(float(t), 3))
    return times


# ------------------------------------------------------------------ prelabel --

def persistence_filter(peaks_by_frame: dict, radius_px: float = 12.0,
                       stride: int = 1, min_support: float = 0.6,
                       neighbours: int = 2) -> dict:
    """Keep only detections that a neighbouring frame also sees.

    A ball is a physical object: it is in the next frame, within a few pixels of where
    it was.  A cloth-edge response or a single-frame ghost is not.  This is the piece
    of *new* information self-training is allowed to use -- it is not the teacher
    voting again -- and it is what makes a bulk pre-label cheaper than a human.

    ``peaks_by_frame`` maps frame index to a list of ``(x, y, score)`` in native
    pixels; a peak survives when at least ``min_support`` of the frames within
    ``neighbours * stride`` on either side hold a peak within ``radius_px``.
    """
    keys = sorted(peaks_by_frame)
    position = {key: i for i, key in enumerate(keys)}
    kept, dropped = {}, {}
    for key in keys:
        here = peaks_by_frame[key]
        keep_rows, drop_rows = [], []
        for (x, y, score) in here:
            checks, hits = 0, 0
            for step in range(1, neighbours + 1):
                for other in (key - step * stride, key + step * stride):
                    if other not in position:
                        continue
                    checks += 1
                    if any((x - ox) ** 2 + (y - oy) ** 2 <= radius_px ** 2
                           for (ox, oy, _s) in peaks_by_frame[other]):
                        hits += 1
            support = hits / checks if checks else 0.0
            row = {"x": float(x), "y": float(y), "score": float(score),
                   "support": round(support, 3)}
            (keep_rows if support >= min_support else drop_rows).append(row)
        kept[key] = keep_rows
        dropped[key] = drop_rows
    return {"kept": kept, "dropped": dropped}


# ------------------------------------------------------------- student scan --

def student_peaks(model, video, indices: list, size: tuple, device: str = "auto",
                  threshold: float = 0.30, batch: int = 4) -> dict:
    """Heatmap peaks per frame index, in native pixels, from the trained student.

    ``indices`` are VOD frame numbers and are expected to be a strided series; the
    stack is still the true (t-1, t, t+1) triple, so a stride only decides *which*
    frames get labelled, not what the network sees.
    """
    import torch

    from src.tiny_ball_net import NATIVE_WH, STACK, pick_peaks, read_frames

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    wanted = sorted(set(int(i) for i in indices))
    frames = read_frames(video, [i + k for i in wanted for k in (-1, 0, 1)], size=size)
    scale = NATIVE_WH[0] / size[0]
    peaks, times = {}, {}
    model.eval()
    with torch.no_grad():
        for start in range(0, len(wanted), batch):
            chunk = wanted[start:start + batch]
            xs = []
            for index in chunk:
                stack = stack_at(frames, index, size)
                xs.append(stack.transpose(2, 0, 1) if stack is not None
                          else np.zeros((STACK * 3, size[1], size[0]), np.float32))
            heat = model(torch.from_numpy(np.stack(xs)).to(device)).cpu().numpy()[:, 0]
            for index, plane in zip(chunk, heat):
                peaks[index] = [(x * scale, y * scale, float(s))
                                for (x, y, s) in pick_peaks(plane, threshold)]
                times[index] = round(index / 30.0003, 3)
    return {"peaks": peaks, "times": times}


def stack_at(frames: dict, index: int, size: tuple):
    import cv2
    planes = []
    for k in (-1, 0, 1):
        bgr = frames.get(index + k)
        if bgr is None:
            bgr = frames.get(index)          # a neighbour that did not decode
        if bgr is None:
            return None
        small = bgr if tuple(bgr.shape[1::-1]) == tuple(size) else cv2.resize(
            bgr, tuple(size), interpolation=cv2.INTER_AREA)
        planes.append(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    return np.concatenate(planes, axis=2).astype(np.float32) / 255.0


# ----------------------------------------------------------------------- CLI --

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("agreement", help="hybrid vs the CPU reference on the same frames")
    p.add_argument("--frames", type=int, default=6)
    p.add_argument("--times", default="")
    p.add_argument("--resolution", type=int, default=RESOLUTION)
    p.set_defaults(func=cmd_agreement)

    p = sub.add_parser("prelabel", help="student pre-labels + the human-review queue")
    p.add_argument("--bitmap", default=str(ROOT / "out" / "tiny_ball_probe" / "960x540-scratch.pt"))
    p.add_argument("--size", default="960x540")
    p.add_argument("--start-s", type=float, default=0.0)
    p.add_argument("--end-s", type=float, default=1800.0)
    p.add_argument("--stride-s", type=float, default=0.5)
    p.add_argument("--threshold", type=float, default=0.30)
    p.add_argument("--radius-px", type=float, default=14.0)
    p.add_argument("--min-support", type=float, default=0.6)
    p.add_argument("--device", default="auto")
    p.add_argument("--labels-out", default=str(ROOT / "out" / "tiny_ball_probe" / "student_labels.json"))
    p.add_argument("--queue-out", default=str(ROOT / "out" / "tiny_ball_probe" / "review_queue.json"))
    p.set_defaults(func=cmd_prelabel)

    p = sub.add_parser("label", help="teacher-label new frames with the fast mode")
    p.add_argument("--mode", default="hybrid", choices=MODES)
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--stride-s", type=float, default=6.0)
    p.add_argument("--start-s", type=float, default=0.0)
    p.add_argument("--end-s", type=float, default=1800.0)
    p.add_argument("--out", default=str(LABELS_OUT))
    p.add_argument("--progress-every", type=int, default=20)
    p.add_argument("--train-only", action=argparse.BooleanOptionalAction, default=True,
                   help="skip frames inside the frozen held-out blocks (default: on)")
    p.set_defaults(func=cmd_label)

    args = ap.parse_args(argv)
    return args.func(args)


def cmd_agreement(args) -> int:
    """Run both modes on the same frames and report counts and positions.

    Two passes, not interleaved: moving the vision backbone between devices once per
    frame would measure the PCIe transfer and not the mode.
    """
    if args.times:
        times = [float(x) for x in args.times.replace(",", " ").split()]
    else:
        times = [4.1, 4.6, 5.1, 6.3, 10.1, 20.2, 40.3, 60.4][:args.frames]
    frames, per_frame, timings = {}, {}, {"cpu": [], "other": []}
    stages = {"cpu": [], "other": []}
    for t in times:
        bgr = frame_at(t)
        if bgr is not None:
            frames[round(t, 3)] = bgr
    labeller = Sam3Labeller(mode="cpu", resolution=args.resolution)
    for t, bgr in frames.items():
        result = labeller.label_frame(bgr)
        per_frame[t] = {"cpu": result["instances"], "other": []}
        timings["cpu"].append(result["seconds"])
        stages["cpu"].append((result["encoder_s"], result["head_s"]))
    labeller.set_mode("hybrid")
    for t, bgr in frames.items():
        result = labeller.label_frame(bgr)
        per_frame[t]["other"] = result["instances"]
        timings["other"].append(result["seconds"])
        stages["other"].append((result["encoder_s"], result["head_s"]))
    report = agreement(per_frame)
    report["mode"] = "hybrid"
    report["resolution"] = args.resolution
    report["stage_seconds_median"] = {mode: {
        "encoder": round(float(np.median([row[0] for row in rows])), 2),
        "head": round(float(np.median([row[1] for row in rows])), 2)}
        for mode, rows in stages.items()}
    report["seconds_per_frame"] = {
        "cpu": round(float(np.mean(timings["cpu"])), 2),
        "hybrid": round(float(np.mean(timings["other"])), 2)}
    report["seconds_per_frame_median"] = {
        "cpu": round(float(np.median(timings["cpu"])), 2),
        "hybrid": round(float(np.median(timings["other"])), 2)}
    report["frames_per_minute"] = {
        "cpu": round(60.0 / max(1e-6, float(np.mean(timings["cpu"]))), 2),
        "hybrid": round(60.0 / max(1e-6, float(np.mean(timings["other"]))), 2)}
    report["speedup"] = round(float(np.mean(timings["cpu"]))
                              / max(1e-6, float(np.mean(timings["other"]))), 2)
    report["teacher_min_score"] = MIN_SCORE
    report["confidence_threshold"] = 0.5
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "agreement.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in
                      ("frames", "frames_with_equal_counts", "frames_fully_matched",
                       "seconds_per_frame", "seconds_per_frame_median",
                       "frames_per_minute", "speedup")}, indent=1), flush=True)
    print(json.dumps(report["per_frame"], indent=1), flush=True)
    return 0


def cmd_prelabel(args) -> int:
    """Thousands of ball labels in minutes, with the uncertain ones sent to a human.

    The student is cheap (milliseconds per frame) and wrong in a known way, so the
    scan keeps only what survives the persistence filter -- a ball is in the next
    frame, an artefact is not -- and writes everything it dropped to a review queue
    instead of pretending the dataset is complete.  Frames inside the frozen held-out
    blocks are never labelled, so this cannot leak into the score.
    """
    import torch

    from src.tiny_ball_net import build_model, load_labels, parse_size, split_for_rounds

    size = parse_size(args.size)
    ckpt = torch.load(str(args.bitmap), map_location="cpu", weights_only=True)
    model = build_model()
    model.load_state_dict(ckpt["state"])
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device).eval()

    held = frozen_held()
    fps = 30.0003
    _, held_for_train = split_for_rounds(load_labels())
    held = sorted(set(held) | set(held_for_train))
    step = max(1, int(round(args.stride_s * fps)))
    first, last = int(args.start_s * fps), int(args.end_s * fps)
    indices = [i for i in range(first, last, step)
               if all(abs(round(i / fps, 3) - h) >= SPLIT_GAP_S for h in held)]
    print(f"{len(indices)} frames to pre-label at {args.stride_s}s stride "
          f"({len(held)} held-out times excluded)", flush=True)

    started = time.time()
    scanned = student_peaks(model, VIDEO, indices, size, device=device,
                            threshold=args.threshold)
    scan_seconds = time.time() - started
    # the neighbour check must step by the scan's own stride, or it looks for frames
    # that were never sampled and rejects every detection as unsupported
    filtered = persistence_filter(scanned["peaks"], radius_px=args.radius_px,
                                  stride=step, min_support=args.min_support,
                                  neighbours=2)
    labels, queue = {}, {}
    for index, rows in filtered["kept"].items():
        if not rows:
            continue
        labels[str(scanned["times"][index])] = [
            {"x": round(row["x"], 2), "y": round(row["y"], 2),
             "score": round(row["score"], 4), "support": row["support"],
             "source": "student"} for row in rows]
    for index, rows in filtered["dropped"].items():
        if not rows:
            continue
        queue[str(scanned["times"][index])] = rows
    out_path, queue_path = Path(args.labels_out), Path(args.queue_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(labels, indent=1))
    queue_path.write_text(json.dumps(queue, indent=1))
    instances = sum(len(v) for v in labels.values())
    report = {"frames_scanned": len(indices), "scan_seconds": round(scan_seconds, 1),
              "frames_per_minute": round(60.0 * len(indices) / max(1e-6, scan_seconds), 2),
              "frames_per_second": round(len(indices) / max(1e-6, scan_seconds), 2),
              "ms_per_frame": round(1000.0 * scan_seconds / max(1, len(indices)), 1),
              "device": device, "input": list(size), "threshold": args.threshold,
              "labels_frames": len(labels), "labels_instances": instances,
              "review_queue_frames": len(queue),
              "review_queue_instances": sum(len(v) for v in queue.values()),
              "kept_fraction": round(instances / max(1, instances + sum(
                  len(v) for v in queue.values())), 3)}
    (OUT / "prelabel.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1), flush=True)
    return 0


def cmd_label(args) -> int:
    """Teacher labels for frames that have none, written where training can see them.

    Written incrementally: a 6 s/frame teacher over hundreds of frames is an hour of
    machine time, and a run that is killed at 90 % must not lose the 90 %.
    """
    known = existing_times()
    held = frozen_held()
    out_path = Path(args.out)
    if out_path.exists():
        labels = json.loads(out_path.read_text())
    else:
        labels = {}
    step = max(1, int(round(args.stride_s * 30.0003)))
    wanted = []
    index = int(args.start_s * 30.0003)
    last = int(args.end_s * 30.0003)
    fps = 30.0003
    blocked = 0
    while index < last and len(wanted) < args.count:
        t = round(index / fps, 3)
        if t not in known:
            known.add(t)
            if args.train_only and any(abs(t - h) < SPLIT_GAP_S for h in held):
                blocked += 1
            else:
                wanted.append(t)
        index += step
    print(f"{len(wanted)} frames to label, {blocked} skipped inside the frozen held-out "
          f"blocks (gap {SPLIT_GAP_S}s)", flush=True)
    labeller = Sam3Labeller(mode=args.mode)
    started = time.time()
    per_frame_s = []
    for done, t in enumerate(wanted, 1):
        bgr = frame_at(t, VIDEO)
        if bgr is None:
            continue
        result = labeller.label_frame(bgr)
        per_frame_s.append(result["seconds"])
        labels[str(round(t, 3))] = [row for row in result["instances"]
                                    if row["score"] >= RECORD_MIN_SCORE]
        if done % args.progress_every == 0 or done == len(wanted):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(labels, indent=1))
            mean = float(np.mean(per_frame_s))
            print(f"{done}/{len(wanted)} frames  {mean:.2f} s/frame  "
                  f"{60.0 / mean:.2f} frames/min  elapsed {time.time() - started:.0f}s",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
