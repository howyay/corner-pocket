"""SAM 3.1 Object Multiplex dense ball tracking demo on the pool VOD clip.

Text-prompt once ("billiard ball") on frame 0, then track every ball through
the whole clip with stable object IDs (shared-memory multiplex inference).
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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "sam3"))
sys.path.insert(0, str(ROOT))

BPE = ROOT / "sam3" / "sam3" / "assets" / "bpe_simple_vocab_16e6.txt.gz"


def load_predictor(checkpoint_path: str, max_objects: int = 16, fp32: bool = False):
    from sam3.model_builder import build_sam3_multiplex_video_predictor

    import os

    if os.environ.get("MUX_FP32"):
        fp32 = True
    if fp32:
        # run everything in fp32: skip the bf16 autocast entered by the predictor
        from sam3.model.sam3_multiplex_video_predictor import Sam3MultiplexVideoPredictor

        _orig_init = Sam3MultiplexVideoPredictor.__init__

        def _init_fp32(self, model, *a, **kw):
            _orig_init(self, model, *a, **kw)
            try:
                self.bf16_context.__exit__(None, None, None)
            except Exception:
                pass
            model.float()

        Sam3MultiplexVideoPredictor.__init__ = _init_fp32

    return build_sam3_multiplex_video_predictor(
        checkpoint_path=checkpoint_path,
        bpe_path=str(BPE),
        max_num_objects=max_objects,
        multiplex_count=16,
        use_fa3=False,
        use_rope_real=True,
        compile=False,
        warm_up=False,
        async_loading_frames=False,
    )


def propagate(predictor, session_id, direction="forward", max_frames=None):
    """Collect outputs per frame from a propagation pass."""
    out = {}
    req = dict(
        type="propagate_in_video",
        session_id=session_id,
        propagation_direction=direction,
    )
    if max_frames is not None:
        req["max_frame_num_to_track"] = max_frames
    try:
        for resp in predictor.handle_stream_request(request=req):
            out[resp["frame_index"]] = resp["outputs"]
            print(f"  [prop] frame {resp['frame_index']} collected (total {len(out)})", flush=True)
    except RuntimeError as e:
        # the multiplex code currently raises on the final frame of the range;
        # treat it as end-of-clip and keep the frames collected so far
        print(f"  [prop] propagation ended early: {str(e)[:100]}", flush=True)
    return out


def parse_outputs(outputs) -> tuple[np.ndarray, np.ndarray, list] | None:
    """Extract (masks, scores, obj_ids) from a frame's outputs dict."""
    if outputs is None:
        return None
    masks = None
    scores = None
    ids = None
    for key in ("out_binary_masks", "masks", "pred_masks", "video_res_masks"):
        if key in outputs and outputs[key] is not None:
            v = outputs[key]
            if torch.is_tensor(v):
                masks = v.detach().cpu().numpy()
                break
            elif isinstance(v, np.ndarray):
                masks = v
                break
            else:
                print(f"  [parse] {key} is {type(v).__name__}", flush=True)
    if masks is None:
        print(f"  [parse] no mask tensor; keys={list(outputs.keys())}", flush=True)
        return None
    masks = np.squeeze(masks)
    if masks.ndim != 3:
        print(f"  [parse] masks ndim={masks.ndim} shape={masks.shape}", flush=True)
        return None
    for key in ("out_probs", "scores", "object_score_logits"):
        if key in outputs and outputs[key] is not None:
            s = outputs[key]
            if torch.is_tensor(s):
                scores = s.detach().cpu().numpy().ravel()
                break
            elif isinstance(s, np.ndarray):
                scores = s.ravel()
                break
    if "out_obj_ids" in outputs and outputs["out_obj_ids"] is not None:
        ids = [int(x) for x in np.asarray(outputs["out_obj_ids"]).ravel()]
    return masks > 0.5, scores, ids


def ball_centers(mask: np.ndarray) -> tuple[float, float, float]:
    m = (mask > 0).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return mask.shape[1] / 2, mask.shape[0] / 2, 1.0
    c = max(cnts, key=cv2.contourArea)
    (x, y), r = cv2.minEnclosingCircle(c)
    return float(x), float(y), float(r)


def render_frame(bgr, per_obj, out_h=540):
    """Draw each tracked object with its id; return image."""
    img = bgr.copy()
    colors = [
        (0, 200, 250), (255, 100, 50), (60, 200, 60), (250, 60, 200),
        (50, 150, 255), (200, 250, 50), (100, 100, 250), (250, 200, 50),
        (60, 250, 250), (250, 60, 60), (150, 250, 150), (250, 150, 250),
    ]
    for i, (oid, m) in enumerate(sorted(per_obj.items())):
        if m.sum() < 40:
            continue
        cx, cy, r = ball_centers(m)
        col = colors[i % len(colors)]
        overlay = img.copy()
        cv2.drawContours(overlay, [np.argwhere(m)[:, ::-1].reshape(-1, 1, 2)], -1, col, -1)
        img = cv2.addWeighted(overlay, 0.35, img, 0.65, 0)
        cv2.circle(img, (int(cx), int(cy)), max(4, int(r)), col, 2)
        cv2.putText(img, f"id{oid}", (int(cx) + 6, int(cy) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", default="data/clip_break")
    ap.add_argument("--ckpt", default="/tmp/sam3.1_multiplex_fp16.safetensors")
    ap.add_argument("--out", default="out/multiplex_break")
    ap.add_argument("--prompt", default="billiard ball")
    ap.add_argument("--prompt-frame", type=int, default=0)
    ap.add_argument("--max-frames", type=int, default=0, help="0 = all")
    ap.add_argument("--points", default=None, help="'x1,y1;x2,y2' absolute px point prompts (overrides text)")
    ap.add_argument("--frames", type=int, default=0, help="0 = all frames")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("building multiplex predictor...", flush=True)
    predictor = load_predictor(args.ckpt)
    print(f"predictor ready in {time.time()-t0:.0f}s", flush=True)

    resp = predictor.handle_request(
        request=dict(
            type="start_session",
            resource_path=args.clip,
            offload_video_to_cpu=True,
        )
    )
    session_id = resp["session_id"]
    print(f"session {session_id[:8]} on {args.clip}", flush=True)

    torch.cuda.empty_cache()

    if args.points:
        # point-prompt mode: one object per point, relative coords
        pts = [tuple(map(float, s.split(","))) for s in args.points.split(";")]
        img0 = cv2.imread(str(sorted(Path(args.clip).glob("*.jpg"))[0]))
        H0, W0 = img0.shape[:2]
        for oid, (px, py) in enumerate(pts, start=2):
            pts_t = torch.tensor([[px / W0, py / H0]], dtype=torch.float32)
            lbls = torch.tensor([1], dtype=torch.int32)
            resp = predictor.handle_request(
                request=dict(
                    type="add_prompt",
                    session_id=session_id,
                    frame_index=args.prompt_frame,
                    points=pts_t,
                    point_labels=lbls,
                    obj_id=oid,
                )
            )
            o = resp.get("outputs")
            print(f"  point {oid}: out_obj_ids={o.get('out_obj_ids') if isinstance(o, dict) else '?'}", flush=True)
        print("point prompts added:", len(pts), flush=True)
    else:
        resp = predictor.handle_request(
            request=dict(
                type="add_prompt",
                session_id=session_id,
                frame_index=args.prompt_frame,
                text=args.prompt,
            )
        )
        print("init outputs keys:", list(resp["outputs"].keys()) if isinstance(resp["outputs"], dict) else type(resp["outputs"]), flush=True)

    t1 = time.time()
    frames_out = propagate(
        predictor, session_id, direction="forward",
        max_frames=(args.max_frames if args.max_frames > 0 else None),
    )
    if frames_out:
        k0 = frames_out[sorted(frames_out)[0]]
        print("prop outputs keys:", list(k0.keys()) if isinstance(k0, dict) else type(k0), flush=True)
    dt = time.time() - t1
    print(f"propagated {len(frames_out)} frames in {dt:.1f}s = {len(frames_out)/dt:.2f} fps", flush=True)

    # derive object ids: from init state
    try:
        st = predictor._all_inference_states[session_id]["state"]
        obj_ids = list(st["obj_ids"])
    except Exception:
        obj_ids = list(range(16))
    print("obj ids:", obj_ids[:20], flush=True)

    results = {}
    for fidx in sorted(frames_out):
        parsed = parse_outputs(frames_out[fidx])
        if parsed is None:
            continue
        masks, scores, ids = parsed
        n = masks.shape[0]
        if ids is None:
            ids = obj_ids[:n]
        results[int(fidx)] = {
            "masks": masks.astype(bool),
            "scores": scores if scores is not None else np.ones(n),
            "ids": [int(x) for x in ids][:n],
        }

    # render frames
    frame_paths = sorted(Path(args.clip).glob("*.jpg"))
    rendered = []
    for i, p in enumerate(frame_paths):
        bgr = cv2.imread(str(p))
        if i not in results:
            continue
        r = results[i]
        per_obj = {int(oid): r["masks"][j] for j, oid in enumerate(r["ids"])}
        img = render_frame(bgr, per_obj)
        out_p = out_dir / f"tracked_{i:05d}.jpg"
        cv2.imwrite(str(out_p), img)
        rendered.append((i, out_p))
        # centers for JSON
        centers = {}
        for oid, m in per_obj.items():
            if m.sum() < 40:
                continue
            cx, cy, rad = ball_centers(m)
            centers[str(oid)] = [round(cx, 1), round(cy, 1), round(rad, 1)]
        results[i]["centers"] = centers

    json.dump(
        {
            "fps": len(frames_out) / dt,
            "n_frames": len(frames_out),
            "obj_ids": [int(x) for x in obj_ids],
            "prompt": args.prompt,
        },
        open(out_dir / "meta.json", "w"),
        indent=1,
    )
    np.savez(out_dir / "masks.npz", **{
        str(k): v["masks"] for k, v in results.items() if "masks" in v
    })
    # compact json without masks
    slim = {
        str(k): {"centers": v["centers"], "scores": [round(float(s), 3) for s in v["scores"]],
                "ids": [int(x) for x in v["ids"]]}
        for k, v in results.items()
    }
    json.dump(slim, open(out_dir / "tracking.json", "w"), indent=1)
    print(f"rendered {len(rendered)} frames -> {out_dir}", flush=True)


if __name__ == "__main__":
    main()
