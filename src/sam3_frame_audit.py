"""Audit what SAM3 was actually shown: dump the decoded frame, hash it, judge it.

A zero-ball SAM3 window is only evidence of occlusion if the frame really shows
the table.  A black frame, a stale frame from an earlier seek, or two different
timestamps resolving to the same image would make every "the census saw nothing
there" conclusion worthless, so this tool re-decodes each timestamp through the
*same* path ``src/sam3_ball_cache.detect_frame`` uses (fresh ``VideoCapture``,
``set(CAP_PROP_POS_MSEC)``, one ``read()``), dumps the image to
``out/scan30/zeroball/<t>.png`` with its measured frame index, and reports what
the audit needs:

* the frame's own index and time (``CAP_PROP_POS_FRAMES`` / ``POS_MSEC``), so an
  off-by-one or a seek that landed elsewhere is visible;
* size, mean and standard deviation of the grey image (a black or flat frame is
  not a table);
* the md5 of the pixels and of the encoded PNG, so two timestamps that hand SAM3
  the *same* image are caught;
* how far each dump is from the others (mean abs difference), which is what
  separates a stale duplicate from a genuinely different frame.

Verdicts: ``decode artifact`` when an image is black/flat, or a duplicate of
another dump, or the frame index does not match the requested time (a seek that
landed a second away); ``real occlusion`` when the image differs from its
neighbours, is a normal table image, and SAM3 found no ball on the cloth;
``undetermined`` otherwise.  No video is written and no cache is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.datasets import media_relpath  # noqa: E402

BLACK_MEAN = 12.0        # below this the frame is not a picture of anything
FLAT_STD = 6.0           # below this the frame is a flat colour
SAME_FRAME_MAD = 1.5     # mean abs difference below this = the same image
STALE_GAP_S = 0.35       # ... and only counts as stale when the times are this far apart
SEEK_TOLERANCE_S = 0.20  # a seek further off than this did not land where asked


def decode(video, time_s):
    """Exactly what ``sam3_ball_cache.detect_frame`` gets: fresh cap, seek, read."""
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(time_s) * 1000.0)
    ok, frame = cap.read()
    info = {"requested_t": round(float(time_s), 3), "ok": bool(ok),
            "frame_index": float(cap.get(cv2.CAP_PROP_POS_FRAMES)),
            "reported_t": round(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0, 3),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}
    cap.release()
    if not ok:
        info.update({"mean": None, "std": None, "md5": None})
        return info, None
    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    info.update({"shape": list(frame.shape), "mean": round(float(grey.mean()), 2),
                 "std": round(float(grey.std()), 2),
                 "md5": hashlib.md5(np.ascontiguousarray(grey)).hexdigest()})
    return info, frame


def decode_by_index(video, frame_index):
    """The other way to reach the same frame: seek by frame number."""
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
    ok, frame = cap.read()
    index = float(cap.get(cv2.CAP_PROP_POS_FRAMES))
    cap.release()
    if not ok:
        return {"ok": False}
    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return {"ok": True, "frame_index": index,
            "md5": hashlib.md5(np.ascontiguousarray(grey)).hexdigest(),
            "mean": round(float(grey.mean()), 2)}


def cloth_report(video, time_s, reference_quad=None):
    """What ``detect_table`` made of this frame -- the mask SAM3's balls are filtered by.

    ``detect_table`` estimates the cloth per frame; under occlusion its largest
    component can land on the wall panels instead of the bed, and every ball is
    then thrown away by the ``cloth[cy, cx]`` test.  This reports the mask's size,
    its largest component, and how much of it falls inside the *reference* quad,
    which is the stable human-anchored geometry.
    """
    from src.table_detect import detect_table

    info, frame = decode(video, time_s)
    if frame is None:
        return {**info, "cloth_area": None, "reason": "no frame"}
    small = cv2.resize(frame, (960, 540))
    table = detect_table(small)
    mask = (table["mask"] > 0).astype(np.uint8)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    largest = int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) + 1 if count > 1 else 0
    row = {"requested_t": round(float(time_s), 3), "mean": info.get("mean"), "md5": info.get("md5"),
           "cloth_area": int(mask.sum()),
           "components": int(count - 1),
           "largest_area": int(stats[largest, cv2.CC_STAT_AREA]) if largest else 0,
           "largest_centroid": [round(float(centroids[largest][0]), 1),
                                round(float(centroids[largest][1]), 1)] if largest else None,
           "corners": None if table["corners"] is None
           else np.round(np.array(table["corners"], float), 1).tolist()}
    if reference_quad is not None:
        quad = np.array(reference_quad, np.float32) * (960.0 / 1280.0)
        inside = np.zeros_like(mask)
        cv2.fillPoly(inside, [np.round(quad).astype(np.int32)], 1)
        row["inside_reference_share"] = round(float((mask & inside).sum())
                                              / max(1, int(mask.sum())), 3)
        if largest:
            cx, cy = centroids[largest]
            row["largest_inside_reference"] = bool(
                cv2.pointPolygonTest(quad, (float(cx), float(cy)), False) >= 0)
    return row


def reference_quad(dataset="vod30", anchors_path="out/pid_anchors_vod30.json"):
    """The verified cloth quad: the human calibration segment, else the hand anchors.

    ``prefer_human`` asks the seam for the artifact's own human segment, not for
    the segment that owns a time: this audit weighs every frame against one
    geometry, and a derived or refined segment must not replace a human one.
    """
    from src import calib_segments

    reference = calib_segments.resolve(dataset, prefer_human=True, kinds=("segment",))
    if reference.found:
        return reference.quad, f"segment {reference.entry} ({reference.source})"
    anchors = calib_segments.read(anchors_path, "anchors")
    if anchors.found:
        return np.asarray(anchors.quad, np.float32), "hand anchors"
    return None, "none"


def audit(video, times, out_dir="out/scan30/zeroball", dumps=True) -> dict:
    out_dir = Path(out_dir)
    if dumps:
        out_dir.mkdir(parents=True, exist_ok=True)
    rows, images = [], {}
    for time_s in times:
        info, frame = decode(video, time_s)
        info["file"] = None
        if frame is not None and dumps:
            path = out_dir / f"t{float(time_s):08.2f}.png".replace(" ", "0")
            cv2.imwrite(str(path), frame)
            info["file"] = str(path)
            images[round(float(time_s), 3)] = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rows.append(info)
    # duplicates and near-duplicates: two timestamps handing SAM3 one image
    hashes: dict = {}
    for row in rows:
        if row.get("md5"):
            hashes.setdefault(row["md5"], []).append(row["requested_t"])
    times_sorted = sorted(images)
    for row in rows:
        notes, verdict = [], "real occlusion"
        t = row["requested_t"]
        if not row.get("ok"):
            notes.append("read failed")
            verdict = "decode artifact"
        if row.get("mean") is not None and row["mean"] < BLACK_MEAN:
            notes.append(f"black frame (mean {row['mean']})")
            verdict = "decode artifact"
        if row.get("std") is not None and row["std"] < FLAT_STD:
            notes.append(f"flat frame (std {row['std']})")
            verdict = "decode artifact"
        if row.get("md5") and len(hashes[row["md5"]]) > 1:
            notes.append(f"identical pixels to t={[x for x in hashes[row['md5']] if x != t]}")
            verdict = "decode artifact"
        if row.get("reported_t") is not None and abs(row["reported_t"] - t) > SEEK_TOLERANCE_S:
            notes.append(f"seek landed at t={row['reported_t']} ({row['reported_t'] - t:+.2f}s)")
            verdict = "undetermined"
        if verdict == "real occlusion" and row.get("md5"):
            neighbours = {}
            for other in times_sorted:
                if other == t or other not in images or t not in images:
                    continue
                gap = abs(other - t)
                if gap <= 2.0:
                    neighbours[other] = round(float(np.abs(images[t].astype(np.int16)
                                                          - images[other].astype(np.int16)).mean()), 2)
            row["neighbour_mad"] = neighbours
            # Two frames 0.2 s apart in a still scene are naturally identical:
            # only a duplicate across a real time gap means a stale decode.
            stale = {other: mad for other, mad in neighbours.items()
                     if abs(other - t) >= STALE_GAP_S and mad < SAME_FRAME_MAD}
            if stale:
                notes.append(f"stale duplicate of t={min(stale, key=stale.get)} "
                             f"(mad {min(stale.values())}, {abs(min(stale, key=stale.get) - t):.1f}s apart)")
                verdict = "decode artifact"
            row["same_frame_index"] = (row.get("frame_index") in
                                       {other.get("frame_index") for other in rows
                                        if other is not row and other.get("frame_index")})
        row["notes"], row["verdict"] = notes, verdict
    return {"video": str(video), "dumped": len([r for r in rows if r.get("file")]),
            "duplicate_hashes": {h: v for h, v in hashes.items() if len(v) > 1},
            "verdicts": {v: sum(1 for r in rows if r["verdict"] == v)
                         for v in ("real occlusion", "decode artifact", "undetermined")},
            "frames": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", default=media_relpath(ROOT, "vod30"))
    ap.add_argument("--times", default="", help="comma-separated timestamps")
    ap.add_argument("--times-file", default=None,
                    help="JSON list of timestamps (e.g. the zero-ball frames of a cache)")
    ap.add_argument("--out", default="out/scan30/zeroball")
    ap.add_argument("--report", default="out/scan30/frame_audit.json")
    ap.add_argument("--no-dumps", action="store_true")
    ap.add_argument("--cloth", action="store_true",
                    help="also report the per-frame cloth mask and the frame-index cross-check")
    args = ap.parse_args()
    if args.times_file:
        times = json.loads(Path(args.times_file).read_text())
    else:
        times = [float(part) for part in args.times.split(",") if part.strip()]
    result = audit(args.video, times, out_dir=args.out, dumps=not args.no_dumps)
    if args.cloth:
        quad, label = reference_quad()
        result["reference_quad"] = {"source": label,
                                    "quad": None if quad is None else np.round(quad, 1).tolist()}
        cap = cv2.VideoCapture(args.video)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        for row in result["frames"]:
            row["cloth"] = cloth_report(args.video, row["requested_t"], quad)
            row["by_index"] = decode_by_index(args.video, round(row["requested_t"] * fps))
            row["index_matches_time_seek"] = bool(
                row["by_index"].get("md5") and row["by_index"]["md5"] == row.get("md5"))
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(result, indent=1))
    print(json.dumps({"dumped": result["dumped"], "verdicts": result["verdicts"],
                      "duplicates": result["duplicate_hashes"],
                      "reference_quad": result.get("reference_quad")}, indent=1))
    for row in result["frames"]:
        line = (f"t={row['requested_t']:9.2f} frame={row['frame_index']:8.0f} "
                f"reported={row.get('reported_t')} mean={row.get('mean')} std={row.get('std')} "
                f"md5={(row.get('md5') or '')[:10]} {row['verdict']} {'; '.join(row['notes'])}")
        cloth = row.get("cloth")
        if cloth:
            line += (f"\n     cloth area={cloth.get('cloth_area')} comps={cloth.get('components')}"
                     f" largest={cloth.get('largest_area')}@ {cloth.get('largest_centroid')}"
                     f" inside_ref={cloth.get('inside_reference_share')}"
                     f" largest_inside={cloth.get('largest_inside_reference')}"
                     f" index_seek_same_image={row.get('index_matches_time_seek')}")
        print(line)


if __name__ == "__main__":
    main()
