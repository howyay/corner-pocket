"""Check synthetic 1080p media. Write text evidence only outside the media directory."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import cv2

from annotator.vod_import import LAST_FRAME_LEAD, VodImportError, _reads_to_last_frame, probe_media


MEDIA = Path(os.environ["MEDIA_DIR"])
EVIDENCE = Path(os.environ["EVIDENCE_DIR"])
MEDIA.mkdir(parents=True, exist_ok=True)
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
if not FFMPEG or not FFPROBE:
    raise RuntimeError("ffmpeg and ffprobe are required")


def run(label, command):
    with (EVIDENCE / f"{label}.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    print(json.dumps({"command": label, "exit_code": result.returncode}), flush=True)
    result.check_returncode()


def decoded(path):
    cap = cv2.VideoCapture(str(path))
    try:
        assert cap.isOpened(), f"cannot open {path.name}"
        count = 0
        while cap.read()[0]:
            count += 1
        return count
    finally:
        cap.release()


source, cut, damaged = (MEDIA / name for name in ("source.mp4", "cut.mp4", "damaged.mp4"))
run("generate-1080p", [FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=1920x1080:rate=30:duration=6", "-c:v", "libx264",
                        "-preset", "veryfast", "-threads", "2", "-crf", "28", "-g", "60",
                        "-bf", "2", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-y", str(source)])
run("cut-1080p", [FFMPEG, "-v", "error", "-protocol_whitelist", "file", "-ss", "2.5", "-i", str(source),
                   "-t", "2", "-c", "copy", "-movflags", "+faststart", "-f", "mp4", "-y", str(cut)])
metadata = {}
for path in (source, cut):
    started = time.monotonic()
    meta = metadata[path] = probe_media(path, [FFMPEG])
    probe_seconds = time.monotonic() - started
    count = decoded(path)
    assert (meta["width"], meta["height"]) == (1920, 1080), meta
    assert meta["fps"] == 30.0, meta
    assert meta["frames"] == count and count > 0, (meta, count)
    if path == source:
        assert count == 180, count
    print(json.dumps({"media": path.name, "probe": meta, "sequential_frames": count,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "probe_s": round(probe_seconds, 3),
                      "probe_and_count_s": round(time.monotonic() - started, 3)}), flush=True)

# Keep the packet table unchanged. Replace the last visible packet with zero bytes.
def visible_packets(path):
    listed = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_packets",
                             "-show_entries", "packet=pos,size,flags", "-of", "json", str(path)],
                            capture_output=True, text=True, check=True, timeout=120)
    return [row for row in json.loads(listed.stdout)["packets"] if "D" not in row.get("flags", "")]


packets = visible_packets(source)
assert len(packets) == 180, len(packets)
last = packets[-1]
start, size = int(last["pos"]), int(last["size"])
content = bytearray(source.read_bytes())
assert 0 < start < start + size <= len(content), (start, size, len(content))
content[start:start + size] = bytes(size)
damaged.write_bytes(content)
packet_count = len(visible_packets(damaged))
decoded_count = decoded(damaged)
if packet_count != 180 or decoded_count >= packet_count:
    raise RuntimeError(f"damaged sample construction failed: packets={packet_count}, decoded={decoded_count}")
started = time.monotonic()
try:
    accepted = probe_media(damaged, [FFMPEG])
except VodImportError as exc:
    print(json.dumps({"media": damaged.name, "bytes": len(content), "damaged_packet_pos": start,
                      "damaged_packet_size": size, "packet_count": packet_count,
                      "sequential_frames": decoded_count,
                      "sha256": hashlib.sha256(content).hexdigest(),
                      "probe_rejected": True, "error": str(exc),
                      "probe_s": round(time.monotonic() - started, 3)}), flush=True)
else:
    raise AssertionError(f"probe accepted damaged media: {accepted}")

# Observe real seek positions. A synthetic offset result is not a backend defect report.
for path in (source, cut):
    start = max(0, metadata[path]["frames"] - LAST_FRAME_LEAD)
    cap = cv2.VideoCapture(str(path))
    try:
        sought = cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        position = cap.get(cv2.CAP_PROP_POS_FRAMES)
        print(json.dumps({"seek_observation": path.name, "requested": start, "set_ok": sought,
                          "reported_position": position}), flush=True)
    finally:
        cap.release()


class EarlyCapture:
    """Model an earlier seek. Do not label this model as an observed backend."""
    def __init__(self, frames, missing):
        self.remaining = frames - missing
        self.missing = missing

    def set(self, _prop, frame):
        self.at = max(0, frame - self.missing)
        return True

    def read(self):
        if self.at >= self.remaining:
            return False, None
        self.at += 1
        return True, None


for missing in (1, 2):
    accepted = _reads_to_last_frame(EarlyCapture(180, missing), 180, cv2)
    print(json.dumps({"hypothetical_early_seek": True, "missing_frames": missing,
                      "accepted": accepted, "observed_backend_defect": False}), flush=True)
print("1080p media checks completed", flush=True)
