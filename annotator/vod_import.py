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

The automatic download (``scan``, ``auto``, ``auto_queue``) sits on top of that
job and changes nothing below it: a FIFO of waiting broadcasts, one drain thread
that calls ``start`` one item at a time, and a periodic rescan.  Every item that
does not import lands in ``skipped`` with its reason, and the queue moves on.
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
import threading
import time
from urllib.parse import urlencode

from annotator.ffmpeg_bin import MediaBinaryMissing, resolve_ffmpeg, resolve_ffprobe
from annotator.refusals import (CHANNEL_REFUSAL, FFMPEG_FAILED, SCAN_CHANNEL, channel_refusal,
                                disk_refusal, filled_refusal, gb, job_identity)
from src.atomic_write import write_atomic
from src.datasets import INDEX, clock, imported_id, parse_imported_id, read_index

# How many broadcasts one channel contributes to the archive. The Twitch GraphQL `videos`
# connection exposes no working cursor - measured 2026-10-03 on a channel with hundreds of
# archives: pageInfo.endCursor is null on every page, and passing an edge's own cursor as
# `after:` returns an empty page, `sort: TIME` or not - so the only lever is `first:`, and this
# is the window. 60 covers a weekly club's year; the picker and the Records archive read the
# same list, and neither claims to be complete beyond it.
RECENT_LIMIT = 60
RECENT_TTL_S = 180
# The automatic download's beat: one rescan this often, this many finished and refused rows
# kept for the console, and the longest rehearsal range an operator may ask for. 900 s is long
# next to one import, so the rescan's Twitch traffic is invisible, and short enough that a
# broadcast ending while nobody watches is queued the same morning.
AUTO_INTERVAL_S = 900
AUTO_KEEP = 10
AUTO_MAX_SECONDS = 3600
#: The actions the automatic download's switch takes in ``VodImporter.auto``, and the
#: tuple that handler refuses every other name with. The write registry
#: (annotator/unified_server.py, the 'vod_auto' row) imports it, so the verbs
#: POST /api/actions publishes are the verbs this handler takes.
AUTO_ACTIONS = ('on', 'off', 'scan')
#: Free space an import must leave: the estimate x 1.2, plus 2 GB for everything else.
HEADROOM = 1.2
RESERVE_BYTES = 2 * 10**9
#: FFmpeg may open only these protocols (the operator's private audit record,
#: not published; finding B-6): HLS over HTTPS.
PROTOCOLS = "file,http,https,tcp,tls,crypto"
#: The channel refusal sentence.  ``annotator/refusals.py`` owns the identity beside it: the
#: code, the Chinese sentence, and the channel field.  Fill it with ``channel_refusal``.
REFUSED_CHANNEL = CHANNEL_REFUSAL.en
_URL = re.compile(r"(?:https?|file|tcp|tls|crypto)://\S+|/\S*\.m3u8\S*")


def thumb_path(channel, vod):
    """This server's own path to one broadcast's preview picture.

    Never Twitch's URL: the console asks this server, which validates the picture's host
    against its allowlist and fetches it, so a browser rendering the console never talks
    to the image CDN.  A broadcast whose picture Twitch did not send gets ``""``.
    """
    vod_id = vod.get("id") if isinstance(vod, dict) else None
    if not (isinstance(channel, str) and re.fullmatch(r"[a-z0-9_]{1,25}", channel or "")):
        return ""
    if not (isinstance(vod_id, str) and vod_id.isdigit()) or not (vod or {}).get("thumbnail"):
        return ""
    return "/api/vods/thumb?" + urlencode({"channel": channel, "id": vod_id})


class VodImportError(Exception):
    """A refusal or failure with the sentence the operator reads and an HTTP status.

    ``identity`` holds the code and the named facts of a refusal, or nothing when the failure
    carries none.  ``annotator/unified_server.py`` copies it into the response body beside
    ``error``, and the console reads it there.
    """

    def __init__(self, message, status=400, identity=None):
        super().__init__(message)
        self.status = status
        self.identity = dict(identity or {})


def failure_identity(exc):
    """The code and the named facts of one failure, or nothing when it carries none.

    Only a refusal carries them.  Any other exception is a failure: it adds no code, so the
    console falls back to its generic line.
    """
    return dict(exc.identity) if isinstance(exc, VodImportError) else {}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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

    def dump(stream):
        json.dump(document, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")

    write_atomic(path, dump, fsync=True)


_INDEX_LOCKS = {}
_INDEX_GUARD = threading.Lock()


def _index_lock(path):
    with _INDEX_GUARD:
        return _INDEX_LOCKS.setdefault(str(Path(path).resolve()), threading.Lock())


class VodImporter:
    """The single-flight import job of one workspace root."""

    def __init__(self, root, ops_get, *, twitch=None, ffmpeg=None, probe=None,
                 disk_usage=shutil.disk_usage, public_error=None, monotonic=time.monotonic,
                 auto_interval_s=AUTO_INTERVAL_S):
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
        # The automatic download. ``enabled`` is on from the start: the owner asked the box to
        # download by itself, so nothing has to be switched on after a restart. The queue and
        # its history live in memory only - losing them on restart costs one rescan, and the
        # index, not this, stays the record of what was imported.
        self._auto_interval_s = auto_interval_s
        self._auto = {"enabled": True, "scanning": False, "seconds": None, "queue": [],
                      "current": None, "done": [], "skipped": [], "last_scan": None,
                      "_scan_at": None, "error": None}
        self._auto_stop = threading.Event()          # the server is closing; never an ``off``
        self._worker_guard = threading.Lock()
        self._worker = self._rescan = None

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
    def _channel_vods(self, channel, force=False):
        """(``(fetched_at_monotonic, vods, clock, more)``, error) for one saved channel.

        The memory cache is what keeps two console reads a few seconds apart from costing two
        Twitch calls (``RECENT_TTL_S``). The queue asks with ``force=True``: it runs on a 900 s
        beat, and a broadcast that ended since the cached list was fetched must not stay
        invisible for the rest of the cache's life. A Twitch error is never cached, so the next
        read tries again (an error row in ``recent`` proves the retry).
        """
        with self._lock:
            cached = self._recent.get(channel)
        if force or cached is None or self._monotonic() - cached[0] > RECENT_TTL_S:
            try:
                vods = self.tw.channel_recent_vods(channel, RECENT_LIMIT)
            except self.tw.TwitchVodError as exc:
                return None, str(exc)
            cached = (self._monotonic(), vods, now_iso(), len(vods) >= RECENT_LIMIT)
            with self._lock:
                self._recent[channel] = cached
        return cached, None

    def recent(self):
        """Each saved channel's videos, newest first (<= ``RECENT_LIMIT``), or Twitch's error.

        Each row's ``thumb`` is a path on **this** server, not Twitch's URL: the console
        draws pictures through the allowlisted proxy (``/api/vods/thumb``) so a browser
        never talks to the image CDN itself, and a row whose picture Twitch did not send
        carries an empty string rather than a broken link. Each channel also carries
        ``more``: true when the answer filled the window, which is the only honest way to
        say "there may be older VODs than these" (nothing here paginates).
        """
        listed = read_index(self.root)[0]
        rows = []
        for channel in self.saved_channels():
            cached, error = self._channel_vods(channel)
            if error is not None:
                rows.append({"channel": channel, "vods": None, "more": False,
                             "error": error, "fetched_at": None})
                continue
            rows.append({"channel": channel, "error": None, "fetched_at": cached[2], "more": cached[3], "vods": [
                {"id": vod.get("id"), "title": vod.get("title"), "created_at": vod.get("created_at"),
                 "length_s": vod.get("length_s"), "thumb": thumb_path(channel, vod),
                 "broadcast_type": vod.get("broadcast_type"),
                 "imported": sorted(key for key in listed if parse_imported_id(key)[0] == vod.get("id"))}
                for vod in cached[1]]})
        return {"channels": rows, "saved_channels": self.saved_channels(), "cache_s": RECENT_TTL_S}

    def thumbnail(self, channel, vod_id):
        """One saved channel's broadcast preview picture, as a JPEG, or a safe error.

        The channel is checked against the saved sources before Twitch is asked anything:
        an id alone must not turn this server into a picture proxy for the whole platform.
        """
        name = str(channel or "").lower()
        if name not in self.saved_channels():
            sentence, identity = channel_refusal(name)
            raise VodImportError(sentence, 403, identity)
        content_type, body = self._twitch_call(self.tw.vod_thumbnail, vod_id)
        return content_type, body

    def _plan(self, vod, start_s, duration_s):
        try:
            vod_id = self.tw.vod_id_of(vod)
        except self.tw.TwitchVodError as exc:
            raise VodImportError(str(exc)) from None
        info = self._twitch_call(self.tw.vod_info, vod_id)
        channel = str(info.get("channel") or "").lower()
        if not channel or channel not in self.saved_channels():
            sentence, identity = channel_refusal(channel)
            raise VodImportError(sentence, identity=identity)
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
        if disk["ok"]:
            disk["refusal"], disk["identity"] = None, {}
        else:
            # One builder writes the sentence the operator reads and the identity the console
            # reads beside it, so a rewording here cannot drop the code or the numbers.
            disk["refusal"], disk["identity"] = disk_refusal(needed, estimate, free)
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
        """The record the console polls: the sentence, and the refusal identity beside it."""
        with self._lock:
            view = {key: value for key, value in self._job.items() if not key.startswith("_")}
            identity = dict(self._job.get("_identity") or {})
        view.update(identity)
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
            raise VodImportError("An import is already starting; wait for it or cancel it first.", 409,
                                 job_identity("already_starting"))
        try:
            with self._lock:
                if self._job["state"] == "running":
                    raise VodImportError(f"An import is already running ({self._job['id']}); "
                                         "wait for it or cancel it first.", 409,
                                         job_identity("already_running", id=self._job["id"]))
            self._index_document()                  # a damaged index is refused before any download
            plan = self._plan(payload["vod"], payload.get("start_s"), payload.get("duration_s"))
            if plan["id"] in read_index(self.root)[0] and self._media(plan["id"]).is_file():
                raise VodImportError(f"{plan['id']} is already imported; delete it first to import it again.",
                                     409, job_identity("already_imported", id=plan["id"]))
            media_url, variant, estimate = self._resolve(plan)
            disk = self._disk(estimate)
            if not disk["ok"]:
                raise VodImportError(disk["refusal"], 507, disk["identity"])
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
                       finished_at=None, error=None, message=None, _t0=self._monotonic(),
                       _identity={})
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

    def _finish(self, identity=None, **fields):
        """Close the job: the outcome fields, and the refusal identity beside the sentence.

        An import that ends with no refusal clears the identity, so a stale code cannot
        outlive the failure it belongs to.
        """
        with self._lock:
            self._job.update(fields, finished_at=now_iso(),
                             elapsed_s=round(self._monotonic() - self._job["_t0"], 1),
                             _identity=dict(identity or {}))

    def _job_identity(self):
        """The code and the named facts the job record carries beside its sentence, if any."""
        with self._lock:
            return dict(self._job.get("_identity") or {})

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
                # The sentence and its identity come from the table: the job record then names
                # the code, the Chinese line, the exit code and the detail, not the text alone.
                sentence, identity = filled_refusal(FFMPEG_FAILED, exit_code=code, detail=detail)
                return self._finish(identity=identity, state="error", error=sentence)
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
            self._finish(identity=failure_identity(exc), state="error",
                         error=f"{text}. The partial file was removed.")

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
        with self._lock:
            self._auto["enabled"] = False
        self._auto_stop.set()          # first, so the drain thread requeues instead of starting
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

    # -- the automatic download ---------------------------------------------
    def _auto_view(self):
        """The queue as the console reads it: the switch, the FIFO, and the last few endings."""
        with self._lock:
            auto = self._auto
            return {"enabled": auto["enabled"], "scanning": auto["scanning"],
                    "interval_s": self._auto_interval_s, "seconds": auto["seconds"],
                    "queued": [dict(row) for row in auto["queue"]],
                    "current": dict(auto["current"]) if auto["current"] else None,
                    "done": [dict(row) for row in auto["done"]],
                    "skipped": [dict(row) for row in auto["skipped"]],
                    "last_scan": auto["last_scan"], "error": auto["error"]}

    def _scan_due(self):
        """One scan per interval: a console polling the route must not become Twitch traffic."""
        with self._lock:
            at = self._auto["_scan_at"]
        return at is None or self._monotonic() - at >= self._auto_interval_s

    def _auto_enqueue(self, channel, vod, archived):
        """Add one broadcast to the FIFO, unless the index or the queue already has it."""
        vod_id = vod.get("id")
        if not (isinstance(vod_id, str) and vod_id.isdigit()):
            return                              # without a usable id there is nothing to fetch
        with self._lock:
            if vod_id in archived:
                return
            pending = [row["id"] for row in self._auto["queue"]]
            if self._auto["current"] is not None:
                pending.append(self._auto["current"]["id"])
            if vod_id in pending:
                return
            self._auto["queue"].append({"id": vod_id, "channel": channel, "title": vod.get("title"),
                                        "length_s": vod.get("length_s"), "state": "queued",
                                        "error": None})

    def _auto_take(self):
        """The head of the FIFO, marked current, or None: the order is the order it arrived."""
        with self._lock:
            if not self._auto["enabled"]:       # "off" leaves the FIFO alone and stops the drain
                return None
            if self._auto["current"] is not None or not self._auto["queue"]:
                return None
            row = self._auto["queue"].pop(0)
            row["state"] = "importing"
            self._auto["current"] = row
            return row

    def _auto_finish(self, row, state, error=None, identity=None):
        """Move the current item to ``done`` or ``skipped``, and keep only the last few.

        ``identity`` is the code and the named facts of the refusal, copied into the row beside
        the sentence the console shows.
        """
        row["state"] = state
        row["error"] = error
        row.update(identity or {})
        with self._lock:
            self._auto["current"] = None
            bucket = self._auto["done" if state == "done" else "skipped"]
            bucket.append(row)
            del bucket[:-AUTO_KEEP]

    def _auto_requeue(self, row):
        """Put an item back at the head of the FIFO: a shutdown interrupted its wait."""
        row["state"] = "queued"
        row["error"] = None
        with self._lock:
            self._auto["current"] = None
            self._auto["queue"].insert(0, row)

    def _auto_run(self, row):
        """Import one queued broadcast through the ordinary ``start``, and record how it ended.

        One item never unwinds the queue: a refused disk, a Twitch refusal, an ffmpeg failure
        and a missing file all end as that item's sentence in ``skipped``, and the drain thread
        takes the next one. Nothing here deletes anything.
        """
        if self._auto_stop.is_set():
            return self._auto_requeue(row)
        disk = self._disk(0)                    # the 2 GB reserve alone: is even that too much?
        if not disk["ok"]:
            return self._auto_finish(row, "skipped", disk["refusal"], identity=disk["identity"])
        # An operator's own import holds the single-flight slot. Waiting for it is honest;
        # spending the item on a 409 would drop a broadcast that is already in the queue.
        while not self._auto_stop.is_set():
            with self._lock:
                running, thread = self._job["state"] == "running", self._thread
            if not running:
                break
            if thread is None:
                time.sleep(0.1)
            else:
                thread.join(timeout=0.5)
        if self._auto_stop.is_set():
            return self._auto_requeue(row)
        with self._lock:
            seconds = self._auto["seconds"]
        payload = {"vod": row["id"]}
        if seconds:
            payload.update(start_s=0, duration_s=seconds)    # the rehearsal range, 1..3600 s
        try:
            started = self.start(payload)
        except VodImportError as exc:
            return self._auto_finish(row, "skipped", str(exc), identity=exc.identity)
        except Exception as exc:                # one item must never kill the drain thread
            return self._auto_finish(row, "skipped", self._public_error(exc))
        with self._lock:
            thread, job_id = self._thread, self._job.get("id")
        if thread is not None:
            thread.join()
        final = self.job()
        if final.get("id") == job_id:
            done = final.get("state") == "done"
            error = final.get("error") or final.get("message")
            identity = self._job_identity()
        else:
            # Another import replaced the status in the instant between ours ending and this
            # read; the index is then the only honest record of how ours ended.
            done = started["id"] in read_index(self.root)[0]
            error = None if done else "the import ended as another one started; it is not in the index"
            identity = {}
        self._auto_finish(row, "done" if done else "skipped", None if done else error,
                          identity=None if done else identity)

    def _auto_wake(self):
        """Make sure one drain thread runs, unless auto is off or the server is closing."""
        with self._lock:
            enabled = self._auto["enabled"]
        if not enabled or self._auto_stop.is_set():
            return                              # "off" means the queue waits, it does not download
        with self._worker_guard:
            if self._worker is not None and self._worker.is_alive():
                return                          # a drain thread is already on its way
            thread = threading.Thread(target=self._auto_drain, daemon=True, name="vod-auto")
            self._worker = thread
        thread.start()

    def _auto_drain(self):
        """The one drain thread: import the head of the FIFO, then the next, until it is empty.

        It holds no timer and polls nothing: an empty queue costs nothing, and a broadcast
        arrives by being enqueued, which starts this thread again.
        """
        while not self._auto_stop.is_set():
            row = self._auto_take()
            if row is None:
                break
            self._auto_run(row)
        with self._worker_guard:
            self._worker = None
        with self._lock:
            waiting = bool(self._auto["queue"])
        if waiting and not self._auto_stop.is_set():
            self._auto_wake()                   # something arrived while this thread was leaving

    def _auto_arm(self, enable=True):
        """Start the periodic beat, once, and turn the switch on unless asked not to.

        The beat is one thread for the life of the importer: it sleeps through an interval even
        while auto is off, so an off/on pair cannot leave the box without a rescan thread. Only
        ``close`` stops it. The startup path and the switch pass ``enable=True``; the queue route
        passes ``False``, so reading the queue never overrides an operator's ``off``.
        """
        if self._auto_stop.is_set():
            return                              # the server is closing: no new work
        with self._lock:
            if enable:
                self._auto["enabled"] = True
            enabled = self._auto["enabled"]
        if not enabled:
            return                              # "off": nothing beats until an operator says on
        with self._worker_guard:
            if self._rescan is not None and self._rescan.is_alive():
                return
            thread = threading.Thread(target=self._auto_rescan, daemon=True, name="vod-auto-scan")
            self._rescan = thread
        thread.start()

    def _auto_disarm(self):
        """Stop the automatic downloads. An import already running is left for ``cancel``."""
        with self._lock:
            self._auto["enabled"] = False

    def _auto_rescan(self):
        """Scan every interval while auto is on. The floor stops a bad knob spinning."""
        while not self._auto_stop.wait(timeout=max(float(self._auto_interval_s), 0.05)):
            with self._lock:
                enabled = self._auto["enabled"]
            if enabled:                         # off only sleeps the beat, it does not kill it
                self.scan()

    def scan(self):
        """Queue every recent broadcast of every saved channel that the archive does not have.

        The list comes from the same Twitch path the picker uses. An id is skipped when the
        index already lists it, or when it is already waiting or running. A channel Twitch
        refuses contributes its sentence to ``error`` and the other channels are still scanned:
        a request and the rescan thread both call this, so it never raises.
        """
        with self._lock:
            self._auto["scanning"] = True
        errors = []
        try:
            listed, damage = read_index(self.root)
            if damage:
                # An index that cannot be read makes every broadcast look missing. One honest
                # sentence is better than re-downloading the archive or churning the whole queue.
                raise VodImportError(damage)
            archived = {parsed[0] for key in listed
                        if (parsed := parse_imported_id(key)) is not None}
            for channel in self.saved_channels():
                cached, error = self._channel_vods(channel, force=True)
                if error is not None:
                    # The channel and the reason are facts.  The sentence comes from the table
                    # (SCAN_CHANNEL in annotator/refusals.py), so the console has a code and a
                    # Chinese sentence for it.  The body of /api/vods/queue carries exactly the
                    # ten keys the console reads, so the identity of this joined text has no key
                    # to travel in; the table owns it until that contract changes.
                    sentence, _ = filled_refusal(SCAN_CHANNEL, channel=channel, message=error)
                    errors.append(sentence)
                    continue
                for vod in cached[1]:
                    self._auto_enqueue(channel, vod, archived)
        except VodImportError as exc:
            errors.append(str(exc))
        except Exception as exc:                # anything else must not stop the scan either
            errors.append(self._public_error(exc))
        with self._lock:
            self._auto["last_scan"] = now_iso()
            self._auto["_scan_at"] = self._monotonic()
            self._auto["error"] = "; ".join(errors) or None
            self._auto["scanning"] = False
        self._auto_wake()
        return self._auto_view()

    def auto_queue(self):
        """The queue, and the lazy trigger: this read starts the beat and scans when one is due.

        The console shows the queue without a click, so the first read after a restart has to
        do the work; the interval keeps a polling console from becoming Twitch traffic. The read
        never turns auto back on: an operator's ``off`` stands. Twitch being down or unauthorised
        only fills ``error`` - nothing here raises.
        """
        self._auto_arm(enable=False)
        if self._scan_due():
            return self.scan()
        self._auto_wake()
        return self._auto_view()

    def auto(self, payload):
        """The automatic download's switch and its one knob.

        ``{"action": "on"}`` arms the periodic rescan and scans at once when nothing has been
        scanned yet; ``"off"`` stops the downloads and leaves the queue where it is; ``"scan"``
        scans now and leaves the switch alone. ``seconds`` (1..``AUTO_MAX_SECONDS``) bounds every
        queued import to a rehearsal range: 1 h at 3 Mb/s is 1.35 GB, small enough to watch end
        to end.
        """
        if not isinstance(payload, dict):
            raise VodImportError("JSON object required")
        extra = sorted(set(payload) - {"action", "seconds"})
        if extra:
            raise VodImportError("unsupported auto option: " + ", ".join(extra))
        action = payload.get("action", "scan")
        if action not in AUTO_ACTIONS:
            raise VodImportError('action must be "on", "off" or "scan"')
        if "seconds" in payload:
            seconds = payload["seconds"]
            if isinstance(seconds, bool) or not isinstance(seconds, int) \
                    or not 1 <= seconds <= AUTO_MAX_SECONDS:
                raise VodImportError("seconds must be a whole number of seconds from 1 to "
                                     f"{AUTO_MAX_SECONDS}")
            with self._lock:
                self._auto["seconds"] = seconds
        if action == "off":
            self._auto_disarm()
            return self._auto_view()
        self._auto_arm(enable=action == "on")
        if action == "scan" or self._auto["last_scan"] is None:
            return self.scan()
        self._auto_wake()
        return self._auto_view()
