"""Import a past broadcast of a saved channel, so it can be browsed frame by frame.

Scope (the owner's decision): only VODs of a channel saved under Source.  Twitch
ingest stays limited to the owner's own channels; any other VOD is refused with a
plain reason before a playback token is even requested.

One import at a time.  ``start`` validates, resolves the VOD (host-pinned, <=720p,
annotator/twitch_vod_source.resolve_vod), estimates the size from the variant's
BANDWIDTH, checks free disk space, then runs ffmpeg without a shell:
``data/vods/<id>.mp4.part`` is written, probed, and renamed to ``<id>.mp4``; only
then is the entry written to ``out/vods/index.json`` (atomically).  The index and
the job never hold the playback token, its signature, or the media URL.

Reads (``recent``, ``estimate``, ``job``) never write: the recent-broadcast cache
lives in memory only.  ``delete`` removes the media and the list entry and keeps
the operator's corrections under ``out/vods/<id>/``.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time

from annotator.ffmpeg_bin import MediaBinaryMissing, resolve_ffmpeg, resolve_ffprobe
from src.datasets import INDEX, clock, imported_id, parse_imported_id, read_index

RECENT_LIMIT = 10
RECENT_TTL_S = 180
#: Free space an import must leave: the estimate x 1.2, plus 2 GB for everything else.
HEADROOM = 1.2
RESERVE_BYTES = 2 * 10**9
#: FFmpeg may open only these protocols (the operator's private audit record,
#: not published; finding B-6): HLS over HTTPS.
PROTOCOLS = "file,http,https,tcp,tls,crypto"
REFUSED_CHANNEL = ("This VOD belongs to {channel}. Only saved channels can be analysed; "
                   "add the channel under Source first.")
_URL = re.compile(r"(?:https?|file|tcp|tls|crypto)://\S+|/\S*\.m3u8\S*")


class VodImportError(Exception):
    """A refusal or failure with the sentence the operator reads and an HTTP status."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def gb(count):
    return f"{count / 1e9:.1f} GB"


def size_text(count):
    return gb(count) if count >= 1e9 else f"{count / 1e6:.1f} MB"


def redact(text):
    """FFmpeg names its input in errors, and a Twitch media URL is signed: cut it out."""
    return _URL.sub("<media URL>", text)


def _whole(value, name, default):
    """A whole number of seconds, 0 or more (JSON number or query string), or ``default``."""
    if value is None or value == "":
        return default
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            raise VodImportError(f"{name} must be a whole number of seconds") from None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or value < 0 or int(value) != value:
        raise VodImportError(f"{name} must be a whole number of seconds, 0 or more")
    return int(value)


def seconds_done(values):
    """Seconds written so far, from one ``-progress`` block (``out_time_us`` first)."""
    for key in ("out_time_us", "out_time_ms"):                  # both are microseconds
        text = values.get(key, "")
        if text.isdigit():
            return int(text) / 1e6
    match = re.fullmatch(r"(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", values.get("out_time", ""))
    return int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3]) if match else None


def ffprobe_beside(ffmpeg_command):
    """The ffprobe of the same build as the ffmpeg in use, else the one on PATH."""
    try:
        return resolve_ffprobe(beside=ffmpeg_command[0])
    except MediaBinaryMissing as exc:
        raise VodImportError(str(exc), 503) from exc


def default_ffmpeg_command():
    """The ffmpeg command list an import runs (annotator/ffmpeg_bin.py picks the binary)."""
    try:
        return [resolve_ffmpeg()]
    except MediaBinaryMissing as exc:
        raise VodImportError(str(exc), 503) from exc


def probe_media(path, ffmpeg_command):
    """fps, decodable frame count and size of the imported file, as the server decodes it.

    A range is cut by stream copy, which keeps the pre-roll from the keyframe before
    start_s; the MP4 edit list hides it, so frame 0 is exactly start_s (measured by
    pixel match against Twitch: mse 0.0 at 3600 s and 3610 s).  The container still
    counts the hidden samples - 9193 for 9002 decodable frames on a 5-min range - and
    that is the count OpenCV reports.  The decodable count is the video packets the
    edit list does not flag discard, and the last one is decoded to prove it.
    """
    import cv2
    listed = subprocess.run([ffprobe_beside(ffmpeg_command), "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "packet=flags", "-of", "csv=p=0", str(path)],
                            capture_output=True, text=True, timeout=900)
    if listed.returncode != 0:
        raise VodImportError("the imported file cannot be read by ffprobe", 502)
    frames = sum(1 for flags in listed.stdout.split() if "D" not in flags)
    cap = cv2.VideoCapture(str(path))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        ok = cap.isOpened() and frames > 0 and cap.set(cv2.CAP_PROP_POS_FRAMES, frames - 1) and cap.read()[0]
    finally:
        cap.release()
    if not ok or not math.isfinite(fps) or fps <= 0 or min(width, height) <= 0:
        raise VodImportError("the imported file cannot be decoded to its last frame", 502)
    return {"fps": fps, "frames": frames, "width": width, "height": height}


def _atomic_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(document, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


_INDEX_LOCKS = {}
_INDEX_GUARD = threading.Lock()


def _index_lock(path):
    with _INDEX_GUARD:
        return _INDEX_LOCKS.setdefault(str(Path(path).resolve()), threading.Lock())


class VodImporter:
    """The single-flight import job of one workspace root."""

    def __init__(self, root, ops_get, *, twitch=None, ffmpeg=None, probe=None,
                 disk_usage=shutil.disk_usage, public_error=None, monotonic=time.monotonic):
        self.root = Path(root)
        self._ops_get = ops_get
        self._twitch = twitch
        self._ffmpeg = ffmpeg or default_ffmpeg_command
        self._probe = probe or (lambda path: probe_media(path, self._ffmpeg()))
        self._disk_usage = disk_usage
        self._public_error = public_error or (lambda exc: f"internal error ({type(exc).__name__})")
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._recent = {}
        self._job = {"state": "idle", "error": None}
        self._proc = self._thread = None

    # -- facts -------------------------------------------------------------
    @property
    def tw(self):
        return self._twitch or importlib.import_module("annotator.twitch_vod_source")

    def saved_channels(self):
        sources = (self._ops_get() or {}).get("sources") or []
        return list(dict.fromkeys(source["channel"].lower() for source in sources
                                  if isinstance(source, dict) and source.get("kind") == "channel"
                                  and isinstance(source.get("channel"), str) and source["channel"]))

    def _media(self, dataset_id, part=False):
        return self.root / "data" / "vods" / (dataset_id + (".mp4.part" if part else ".mp4"))

    def _twitch_call(self, function, *args):
        try:
            return function(*args)
        except self.tw.TwitchVodError as exc:                # Twitch's own safe sentence
            raise VodImportError(str(exc), 502) from None

    def _index_document(self):
        """The raw index for a write; a damaged one is refused, never overwritten."""
        path = self.root / INDEX
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"vods": {}}
        except (OSError, ValueError):
            document = None
        if not isinstance(document, dict) or not isinstance(document.get("vods"), dict):
            raise VodImportError("out/vods/index.json is damaged, so nothing was changed; "
                                 "repair it or move it aside, then retry.", 409)
        return document

    def _update_index(self, change):
        with _index_lock(self.root / INDEX):
            document = self._index_document()
            change(document["vods"])
            _atomic_json(self.root / INDEX, document)

    # -- reads -------------------------------------------------------------
    def recent(self):
        """Each saved channel's recent broadcasts (<= 10), or Twitch's error for it."""
        listed = read_index(self.root)[0]
        rows = []
        for channel in self.saved_channels():
            with self._lock:
                cached = self._recent.get(channel)
            if cached is None or self._monotonic() - cached[0] > RECENT_TTL_S:
                try:
                    vods = self.tw.channel_recent_vods(channel, RECENT_LIMIT)
                except self.tw.TwitchVodError as exc:
                    rows.append({"channel": channel, "vods": None, "error": str(exc), "fetched_at": None})
                    continue
                cached = (self._monotonic(), vods, now_iso())
                with self._lock:
                    self._recent[channel] = cached
            rows.append({"channel": channel, "error": None, "fetched_at": cached[2], "vods": [
                {"id": vod.get("id"), "title": vod.get("title"), "created_at": vod.get("created_at"),
                 "length_s": vod.get("length_s"),
                 "imported": sorted(key for key in listed if parse_imported_id(key)[0] == vod.get("id"))}
                for vod in cached[1]]})
        return {"channels": rows, "saved_channels": self.saved_channels(), "cache_s": RECENT_TTL_S}

    def _plan(self, vod, start_s, duration_s):
        try:
            vod_id = self.tw.vod_id_of(vod)
        except self.tw.TwitchVodError as exc:
            raise VodImportError(str(exc)) from None
        info = self._twitch_call(self.tw.vod_info, vod_id)
        channel = str(info.get("channel") or "").lower()
        if not channel or channel not in self.saved_channels():
            raise VodImportError(REFUSED_CHANNEL.format(channel=channel or "a channel Twitch did not name"))
        length = info.get("length_s")
        if isinstance(length, bool) or not isinstance(length, int) or length <= 0:
            raise VodImportError("Twitch reports no length for this VOD, so no range can be checked", 502)
        start = _whole(start_s, "start_s", 0)
        if start >= length:
            raise VodImportError(f"start_s is past the end of this VOD (it is {clock(length)} long)")
        duration = _whole(duration_s, "duration_s", length - start)
        if duration < 1:
            raise VodImportError("duration_s must be at least 1 second")
        end = min(start + duration, length)
        whole = start == 0 and end == length
        try:
            dataset_id = imported_id(vod_id) if whole else imported_id(vod_id, start, end)
        except ValueError as exc:
            raise VodImportError(str(exc)) from None
        return {"vod_id": vod_id, "id": dataset_id, "channel": channel, "title": info.get("title"),
                "created_at": info.get("created_at"), "length_s": length,
                "range": {"start_s": start, "end_s": end, "whole": whole}}

    def _resolve(self, plan):
        """(media URL, variant facts, estimated bytes).  The URL never leaves start()."""
        resolved = self._twitch_call(self.tw.resolve_vod, plan["vod_id"])
        variant = resolved.get("variant") or {}
        bandwidth = variant.get("bandwidth")
        if isinstance(bandwidth, bool) or not isinstance(bandwidth, int) or bandwidth <= 0:
            raise VodImportError("Twitch listed no bandwidth for this VOD, so its size cannot be estimated", 502)
        seconds = plan["range"]["end_s"] - plan["range"]["start_s"]
        facts = {"height": variant.get("height"), "fps": variant.get("fps"), "bandwidth": bandwidth}
        return resolved.get("media_url"), facts, int(bandwidth * seconds / 8)

    def _disk(self, estimate):
        folder = self.root / "data" / "vods"
        while not folder.exists():
            folder = folder.parent
        free = int(self._disk_usage(folder).free)
        needed = int(estimate * HEADROOM + RESERVE_BYTES)
        disk = {"free_bytes": free, "needed_bytes": needed, "ok": free >= needed}
        disk["refusal"] = None if disk["ok"] else (
            f"Not enough free disk space: this import needs {gb(needed)} (about {gb(estimate)} "
            f"estimated x 1.2 + 2 GB reserve) and {gb(free)} is free. "
            "Import a shorter range or free some space first.")
        return disk

    def _last_rate(self):
        """Bytes per wall second of the most recent import, or None: the ETA's basis."""
        rows = [entry for entry in read_index(self.root)[0].values()
                if isinstance(entry.get("bytes"), int) and isinstance(entry.get("import_wall_s"), (int, float))
                and entry["import_wall_s"] > 0 and isinstance(entry.get("imported_at"), str)]
        if not rows:
            return None
        latest = max(rows, key=lambda entry: entry["imported_at"])
        return latest["bytes"] / latest["import_wall_s"]

    def estimate(self, query):
        """What an import of this VOD/range would cost, before anything is written."""
        plan = self._plan(query.get("vod"), query.get("start_s"), query.get("duration_s"))
        _url, variant, estimate = self._resolve(plan)
        rate = self._last_rate()
        return dict(plan, variant=variant, estimate_bytes=estimate, disk=self._disk(estimate),
                    already_imported=plan["id"] in read_index(self.root)[0],
                    rate_Bps=rate, eta_s=round(estimate / rate) if rate else None)

    def job(self):
        with self._lock:
            view = {key: value for key, value in self._job.items() if not key.startswith("_")}
        if isinstance(view.get("bytes"), int):
            view["mb"] = round(view["bytes"] / 1e6, 1)
        if view.get("rate_Bps"):
            view["rate_mb_s"] = round(view["rate_Bps"] / 1e6, 2)
        return view

    # -- the job -----------------------------------------------------------
    def command(self, media_url, plan, part):
        span = plan["range"]
        command = [*self._ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error",
                   "-protocol_whitelist", PROTOCOLS, "-rw_timeout", "30000000"]
        if span["start_s"]:
            command += ["-ss", str(span["start_s"])]
        command += ["-i", media_url]
        if not span["whole"]:
            command += ["-t", str(span["end_s"] - span["start_s"])]
        return command + ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-bsf:a", "aac_adtstoasc",
                          "-movflags", "+faststart", "-progress", "pipe:1", "-nostats",
                          "-f", "mp4", "-y", str(part)]

    def start(self, payload):
        if not isinstance(payload, dict):
            raise VodImportError("JSON object required")
        extra = sorted(set(payload) - {"vod", "start_s", "duration_s"})
        if extra:
            raise VodImportError("unsupported import option: " + ", ".join(extra))
        if "vod" not in payload:
            raise VodImportError("vod is required: a Twitch VOD id or https://www.twitch.tv/videos/<id>")
        if not self._start_lock.acquire(blocking=False):
            raise VodImportError("An import is already starting; wait for it or cancel it first.", 409)
        try:
            with self._lock:
                if self._job["state"] == "running":
                    raise VodImportError(f"An import is already running ({self._job['id']}); "
                                         "wait for it or cancel it first.", 409)
            self._index_document()                  # a damaged index is refused before any download
            plan = self._plan(payload["vod"], payload.get("start_s"), payload.get("duration_s"))
            if plan["id"] in read_index(self.root)[0] and self._media(plan["id"]).is_file():
                raise VodImportError(f"{plan['id']} is already imported; delete it first to import it again.", 409)
            media_url, variant, estimate = self._resolve(plan)
            disk = self._disk(estimate)
            if not disk["ok"]:
                raise VodImportError(disk["refusal"], 507)
            part = self._media(plan["id"], part=True)
            part.parent.mkdir(parents=True, exist_ok=True)
            part.unlink(missing_ok=True)            # a stale partial file of the same id
            proc = subprocess.Popen(self.command(media_url, plan, part), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, errors="replace")
            span = plan["range"]
            job = dict(plan, state="running", variant=variant, estimate_bytes=estimate,
                       total_s=span["end_s"] - span["start_s"], done_s=0.0, percent=0.0, bytes=0,
                       rate_Bps=None, speed=None, eta_s=None, elapsed_s=0.0, started_at=now_iso(),
                       finished_at=None, error=None, message=None, _t0=self._monotonic())
            thread = threading.Thread(target=self._run, args=(proc, plan, variant, part), daemon=True)
            with self._lock:
                self._job, self._proc, self._thread = job, proc, thread
            thread.start()
            return self.job()
        finally:
            self._start_lock.release()

    def _progress(self, values):
        done, size = seconds_done(values), values.get("total_size", "")
        speed = re.fullmatch(r"\s*([\d.]+)x", values.get("speed", ""))
        with self._lock:
            job = self._job
            elapsed = self._monotonic() - job["_t0"]
            if done is not None:
                done = min(max(done, 0.0), job["total_s"])
                job.update(done_s=round(done, 1), percent=round(100 * done / job["total_s"], 1),
                           eta_s=round((job["total_s"] - done) * elapsed / done) if done > 0 else None)
            if size.isdigit():
                job.update(bytes=int(size), rate_Bps=int(size) / elapsed if elapsed > 0 else None)
            job.update(elapsed_s=round(elapsed, 1), speed=float(speed[1]) if speed else None)

    def _finish(self, **fields):
        with self._lock:
            self._job.update(fields, finished_at=now_iso(),
                             elapsed_s=round(self._monotonic() - self._job["_t0"], 1))

    def _run(self, proc, plan, variant, part):
        try:
            tail = []
            reader = threading.Thread(target=lambda: tail.append(proc.stderr.read()), daemon=True)
            reader.start()
            values = {}
            for line in proc.stdout:
                key, sep, value = line.strip().partition("=")
                if sep:
                    values[key] = value
                    if key == "progress":
                        self._progress(values)
            code = proc.wait()
            reader.join(timeout=5)
            with self._lock:
                cancelled, reason = self._job.get("_cancel"), self._job.get("_reason")
            if cancelled:
                part.unlink(missing_ok=True)
                return self._finish(state="cancelled", message=f"{reason or 'Cancelled'}; the partial file "
                                    "was removed and nothing was listed.")
            if code != 0:
                part.unlink(missing_ok=True)
                last = [line for line in "".join(tail).splitlines() if line.strip()]
                detail = redact(last[-1].strip())[:300] if last else "no message"
                return self._finish(state="error", error=f"ffmpeg stopped (exit {code}): {detail}. "
                                    "The partial file was removed.")
            meta = self._probe(part)
            final = self._media(plan["id"])
            os.replace(part, final)
            with self._lock:
                wall = self._monotonic() - self._job["_t0"]
            entry = {"vod_id": plan["vod_id"], "channel": plan["channel"], "title": plan["title"],
                     "created_at": plan["created_at"], "length_s": plan["length_s"],
                     "start_s": plan["range"]["start_s"], "end_s": plan["range"]["end_s"],
                     "whole": plan["range"]["whole"], "bytes": final.stat().st_size,
                     "imported_at": now_iso(), "import_wall_s": round(wall, 1), "variant": variant, **meta}
            try:
                self._update_index(lambda vods: vods.__setitem__(plan["id"], entry))
            except Exception:
                final.unlink(missing_ok=True)
                raise
            self._finish(state="done", done_s=float(self._job["total_s"]), percent=100.0, eta_s=0,
                         bytes=entry["bytes"], media=meta,
                         message=f"Imported {plan['id']}: {size_text(entry['bytes'])}, {meta['frames']} frames.")
        except Exception as exc:
            part.unlink(missing_ok=True)
            text = str(exc) if isinstance(exc, VodImportError) else self._public_error(exc)
            self._finish(state="error", error=f"{text}. The partial file was removed.")

    def _stop(self, reason):
        with self._lock:
            if self._job["state"] != "running":
                return False
            self._job.update(_cancel=True, _reason=reason)
            proc, thread, dataset_id = self._proc, self._thread, self._job["id"]
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        thread.join(timeout=15)
        self._media(dataset_id, part=True).unlink(missing_ok=True)
        return True

    def cancel(self, payload):
        if not isinstance(payload, dict) or payload.get("confirm") is not True or set(payload) - {"confirm"}:
            raise VodImportError('Cancelling needs {"confirm": true}: ffmpeg is stopped and the partial file deleted.')
        if not self._stop("Cancelled by the operator"):
            raise VodImportError("No import is running.", 409)
        return self.job()

    def close(self):
        """Server shutdown: stop a running import and remove its partial file."""
        self._stop("Stopped because the server stopped")

    def delete(self, payload):
        if not isinstance(payload, dict) or set(payload) - {"id", "confirm"}:
            raise VodImportError('delete takes {"id": "<imported id>", "confirm": true}')
        dataset_id = payload.get("id")
        if parse_imported_id(dataset_id) is None:
            raise VodImportError("id must be an imported VOD id such as tw-1000000001-3600-3900")
        if payload.get("confirm") is not True:
            raise VodImportError('Deleting needs "confirm": true. The media and its list entry are '
                                 "removed; operator corrections are kept.")
        with self._lock:
            if self._job["state"] == "running" and self._job.get("id") == dataset_id:
                raise VodImportError(f"{dataset_id} is being imported; cancel the import first.", 409)
        media = self._media(dataset_id)
        listed = dataset_id in self._index_document()["vods"]
        present = media.is_file() or media.is_symlink()
        if not listed and not present:
            raise VodImportError(f"No imported VOD {dataset_id}.", 404)
        if listed:
            self._update_index(lambda vods: vods.pop(dataset_id, None))
        if present:
            media.unlink()
        self._media(dataset_id, part=True).unlink(missing_ok=True)   # a crashed import's leftover
        folder = self.root / "out" / "vods" / dataset_id
        kept = sum(1 for path in folder.rglob("*") if path.is_file()) if folder.is_dir() else 0
        return {"deleted": dataset_id, "entry_removed": listed, "media_removed": present,
                "kept": {"folder": f"out/vods/{dataset_id}/", "files": kept},
                "message": f"Deleted {dataset_id}: its media and its list entry. Operator corrections "
                           f"under out/vods/{dataset_id}/ are kept ({kept} file{'' if kept == 1 else 's'})."}
