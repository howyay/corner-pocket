"""The VOD import job (annotator/vod_import.py) and its endpoints, with Twitch and ffmpeg stubbed.

Nothing here touches the network or the repository: each test gets a temporary root,
a stub twitch_vod_source, and a fake ffmpeg (a small Python script that prints
``-progress`` lines and writes the output file it was given).
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import threading
import time
from types import SimpleNamespace
import unittest

from annotator.unified_server import APIError, Backend, BoundedHTTPServer, make_handler
from annotator.vod_import import (PROTOCOLS, RECENT_LIMIT, REFUSED_CHANNEL, VodImporter, VodImportError,
                                   redact, seconds_done, thumb_path)

OWN, OTHER = "1000000001", "1111111111"
SIGNED = "https://d2nvs31859zcd8.cloudfront.net/abc/720p30/index-dvr.m3u8?sig=SECRET&token=TOKEN"
THUMB_CDN = ("https://static-cdn.jtvnw.net/cf_vods/d2nvs31859zcd8/abc_examplechannel/thumb/thumb0-320x180.jpg")


class TwitchError(RuntimeError):
    pass


def twitch_stub(calls):
    def vod_id_of(value):
        text = str(value).strip().rstrip("/").split("/")[-1].lstrip("v")
        if not text.isdigit():
            raise TwitchError("Expected a Twitch VOD id or https://www.twitch.tv/videos/<id> URL")
        return text

    def vod_info(vod_id):
        calls.append(("info", vod_id))
        channel = "examplechannel" if vod_id == OWN else "someoneelse"
        return {"id": vod_id, "channel": channel, "title": "260918", "length_s": 13397,
                "created_at": "2026-09-26T06:46:33Z"}

    def resolve_vod(vod_id):
        calls.append(("resolve", vod_id))
        return {"vod_id": vod_id, "media_url": SIGNED, "signature": "SIG", "value": "TOKEN",
                "variant": {"height": 720, "bandwidth": 3_000_000, "fps": 30.0, "url": None}}

    def channel_recent_vods(channel, limit):
        calls.append(("recent", channel, limit))
        if channel == "brokenchannel":
            raise TwitchError("Twitch API request failed (HTTP 500)")
        return [{"id": OWN, "title": "260918", "length_s": 13397, "created_at": "2026-09-26T06:46:33Z",
                 "channel": channel, "broadcast_type": "ARCHIVE", "thumbnail": THUMB_CDN}]

    def vod_thumbnail(vod_id):
        calls.append(("thumb", vod_id))
        if vod_id != OWN:
            raise TwitchError("Twitch has no such video")
        return "image/jpeg", b"\xff\xd8\xff\xe0" + b"0" * 256

    return SimpleNamespace(TwitchVodError=TwitchError, vod_id_of=vod_id_of, vod_info=vod_info,
                           resolve_vod=resolve_vod, channel_recent_vods=channel_recent_vods,
                           vod_thumbnail=vod_thumbnail)


FAKE_FFMPEG = textwrap.dedent('''
    import sys, time
    args = sys.argv[1:]
    out = args[-1]
    mode = open(sys.argv[0] + ".mode").read().strip()
    total = float(args[args.index("-t") + 1]) if "-t" in args else 60.0
    with open(out, "wb") as stream:
        stream.write(b"partial")
    steps = 40 if mode == "slow" else 3
    for step in range(1, steps + 1):
        done = total * step / steps
        print(f"out_time_us={int(done * 1e6)}\\ntotal_size={step * 1000}\\nspeed=5.0x\\nprogress=continue", flush=True)
        time.sleep(0.25 if mode == "slow" else 0.01)
    if mode == "fail":
        print("https://d2nvs31859zcd8.cloudfront.net/x/index-dvr.m3u8?sig=SECRET: Server returned 403", file=sys.stderr)
        sys.exit(1)
    print("progress=end", flush=True)
''')


def archive_row(vod_id, title="260918", length_s=13397, channel="examplechannel"):
    return {"id": vod_id, "title": title, "length_s": length_s, "created_at": "2026-09-26T06:46:33Z",
            "channel": channel, "broadcast_type": "ARCHIVE", "thumbnail": THUMB_CDN}


def archive_stub(calls, vods, broken=()):
    """``twitch_stub`` for a channel with several archives: the queue's order needs a list.

    ``vods`` is read at every call, so a test can append a broadcast and watch the rescan find
    it. An id in ``broken`` fails at playback resolution, like a broadcast Twitch has dropped.
    """
    stub = twitch_stub(calls)
    base_info, base_resolve = stub.vod_info, stub.resolve_vod
    rows = {str(vod["id"]): vod for vod in vods}

    def vod_info(vod_id):
        if str(vod_id) not in rows:
            return base_info(vod_id)
        calls.append(("info", str(vod_id)))
        row = rows[str(vod_id)]
        return {"id": vod_id, "channel": row.get("channel", "examplechannel"), "title": row["title"],
                "length_s": row["length_s"], "created_at": "2026-09-26T06:46:33Z"}

    def resolve_vod(vod_id):
        if str(vod_id) in broken:
            calls.append(("resolve", str(vod_id)))
            raise TwitchError("Twitch has no such video")
        return base_resolve(vod_id)

    def channel_recent_vods(channel, limit):
        calls.append(("recent", channel, limit))
        if channel == "brokenchannel":
            raise TwitchError("Twitch API request failed (HTTP 500)")
        return list(vods)

    stub.vod_info, stub.resolve_vod, stub.channel_recent_vods = vod_info, resolve_vod, channel_recent_vods
    return stub


class ImporterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.calls = []
        self.sources = [{"id": "s1", "kind": "channel", "channel": "examplechannel",
                         "url": "https://www.twitch.tv/examplechannel"}]
        self.script = self.root / "fake_ffmpeg.py"
        self.script.write_text(FAKE_FFMPEG)
        self.mode("ok")
        self.free = 10**12
        self.importer = self.make()

    def make(self, **kwargs):
        options = dict(twitch=twitch_stub(self.calls), ffmpeg=lambda: [sys.executable, str(self.script)],
                       probe=lambda path: {"fps": 30.0, "frames": 9000, "width": 1280, "height": 720},
                       disk_usage=lambda path: SimpleNamespace(free=self.free))
        options.update(kwargs)
        return VodImporter(self.root, lambda: {"sources": self.sources}, **options)

    def mode(self, mode):
        Path(str(self.script) + ".mode").write_text(mode)

    def wait(self, importer=None, states=("done", "error", "cancelled")):
        importer = importer or self.importer
        deadline = time.monotonic() + 30
        while importer.job()["state"] not in states:
            self.assertLess(time.monotonic(), deadline, importer.job())
            time.sleep(0.02)
        return importer.job()

    def index(self):
        return json.loads((self.root / "out" / "vods" / "index.json").read_text())["vods"]

    def wait_until(self, check, importer=None):
        """Poll the queue view until ``check(view)`` holds. Reads the same route the console does."""
        importer = importer or self.importer
        deadline = time.monotonic() + 30
        while True:
            view = importer.auto_queue()
            if check(view):
                return view
            self.assertLess(time.monotonic(), deadline, view)
            time.sleep(0.02)

    def test_a_range_imports_with_real_progress_and_a_clean_entry(self):
        job = self.importer.start({"vod": f"https://www.twitch.tv/videos/{OWN}", "start_s": 3600, "duration_s": 300})
        self.assertEqual((job["state"], job["id"], job["total_s"]), ("running", f"tw-{OWN}-3600-3900", 300))
        self.assertEqual(job["estimate_bytes"], 3_000_000 * 300 // 8)
        job = self.wait()
        self.assertEqual(job["state"], "done", job)
        self.assertEqual((job["percent"], job["done_s"], job["bytes"]), (100.0, 300.0, 7))
        media = self.root / "data" / "vods" / f"tw-{OWN}-3600-3900.mp4"
        self.assertEqual(media.read_bytes(), b"partial")
        self.assertFalse(media.with_name(media.name + ".part").exists())
        entry = self.index()[f"tw-{OWN}-3600-3900"]
        self.assertEqual((entry["channel"], entry["start_s"], entry["end_s"], entry["frames"], entry["fps"]),
                         ("examplechannel", 3600, 3900, 9000, 30.0))
        text = (self.root / "out" / "vods" / "index.json").read_text() + json.dumps(job)
        for secret in ("SECRET", "TOKEN", "SIG", "cloudfront", "m3u8"):
            self.assertNotIn(secret, text)

    def test_the_ffmpeg_command_is_an_argument_list_with_the_protocol_allowlist(self):
        plan = {"range": {"start_s": 3600, "end_s": 3900, "whole": False}}
        command = self.importer.command(SIGNED, plan, Path("/x/tw-1-3600-3900.mp4.part"))
        self.assertIsInstance(command, list)
        self.assertEqual(command[command.index("-protocol_whitelist") + 1], PROTOCOLS)
        self.assertEqual(PROTOCOLS, "file,http,https,tcp,tls,crypto")
        for flag, value in (("-ss", "3600"), ("-t", "300"), ("-c", "copy"), ("-bsf:a", "aac_adtstoasc"),
                            ("-movflags", "+faststart"), ("-progress", "pipe:1"), ("-i", SIGNED)):
            self.assertEqual(command[command.index(flag) + 1], value, flag)
        self.assertIn("-nostats", command)
        self.assertLess(command.index("-protocol_whitelist"), command.index("-i"))
        whole = self.importer.command(SIGNED, {"range": {"start_s": 0, "end_s": 60, "whole": True}}, Path("/x/p"))
        self.assertNotIn("-ss", whole)
        self.assertNotIn("-t", whole)

    def test_a_vod_of_another_channel_is_refused_before_any_playback_token(self):
        with self.assertRaises(VodImportError) as caught:
            self.importer.start({"vod": OTHER})
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(str(caught.exception), REFUSED_CHANNEL.format(channel="someoneelse"))
        self.assertEqual(str(caught.exception), "This VOD belongs to someoneelse. Only saved channels can be "
                                                "analysed; add the channel under Source first.")
        self.assertNotIn(("resolve", OTHER), self.calls)
        self.assertFalse((self.root / "data").exists())
        self.sources = []                                       # no saved channel at all
        with self.assertRaises(VodImportError):
            self.importer.start({"vod": OWN})

    def test_a_second_import_is_409_while_one_runs(self):
        self.mode("slow")
        self.importer.start({"vod": OWN, "start_s": 0, "duration_s": 60})
        with self.assertRaises(VodImportError) as caught:
            self.importer.start({"vod": OWN, "start_s": 100, "duration_s": 60})
        self.assertEqual(caught.exception.status, 409)
        self.importer.cancel({"confirm": True})

    def test_cancel_stops_ffmpeg_and_removes_the_partial_file(self):
        self.mode("slow")
        job = self.importer.start({"vod": OWN, "start_s": 0, "duration_s": 60})
        part = self.root / "data" / "vods" / (job["id"] + ".mp4.part")
        deadline = time.monotonic() + 10
        while not (part.exists() and self.importer.job()["done_s"] > 0):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        with self.assertRaises(VodImportError):
            self.importer.cancel({})                            # confirm is required
        job = self.importer.cancel({"confirm": True})
        self.assertEqual(job["state"], "cancelled")
        self.assertFalse(part.exists())
        self.assertFalse((self.root / "out" / "vods" / "index.json").exists())
        with self.assertRaises(VodImportError) as caught:
            self.importer.cancel({"confirm": True})
        self.assertEqual(caught.exception.status, 409)

    def test_close_kills_a_running_import(self):
        self.mode("slow")
        job = self.importer.start({"vod": OWN, "start_s": 0, "duration_s": 60})
        self.importer.close()
        self.assertEqual(self.importer.job()["state"], "cancelled")
        self.assertFalse((self.root / "data" / "vods" / (job["id"] + ".mp4.part")).exists())

    def test_low_disk_space_is_refused_with_the_numbers(self):
        self.free = 3 * 10**9
        with self.assertRaises(VodImportError) as caught:
            self.importer.start({"vod": OWN})                    # whole VOD: 3 Mb/s x 13397 s = 5.0 GB
        self.assertEqual(caught.exception.status, 507)
        message = str(caught.exception)
        self.assertIn("needs 8.0 GB", message)
        self.assertIn("about 5.0 GB estimated", message)
        self.assertIn("3.0 GB is free", message)
        self.assertFalse((self.root / "data" / "vods").exists())

    def test_ffmpeg_failure_is_honest_and_never_echoes_the_signed_url(self):
        self.mode("fail")
        self.importer.start({"vod": OWN, "start_s": 0, "duration_s": 60})
        job = self.wait()
        self.assertEqual(job["state"], "error")
        self.assertIn("ffmpeg stopped (exit 1)", job["error"])
        self.assertIn("Server returned 403", job["error"])
        self.assertNotIn("SECRET", job["error"])
        self.assertNotIn("cloudfront", job["error"])
        self.assertFalse(list((self.root / "data" / "vods").iterdir()))

    def test_a_stale_partial_file_is_removed_when_the_same_import_starts(self):
        stale = self.root / "data" / "vods" / f"tw-{OWN}-0-60.mp4.part"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"stale bytes from a crash")
        self.importer.start({"vod": OWN, "start_s": 0, "duration_s": 60})
        self.assertEqual(self.wait()["state"], "done")
        self.assertFalse(stale.exists())

    def test_delete_keeps_operator_corrections_and_says_so(self):
        self.importer.start({"vod": OWN, "start_s": 0, "duration_s": 60})
        self.wait()
        key = f"tw-{OWN}-0-60"
        correction = self.root / "out" / "vods" / key / "frame_results" / "5" / "correction.json"
        correction.parent.mkdir(parents=True)
        correction.write_text("{}")
        with self.assertRaises(VodImportError):
            self.importer.delete({"id": key})                    # confirm is required
        result = self.importer.delete({"id": key, "confirm": True})
        self.assertEqual((result["entry_removed"], result["media_removed"], result["kept"]["files"]), (True, True, 1))
        self.assertIn("corrections under out/vods/tw-1000000001-0-60/ are kept", result["message"])
        self.assertTrue(correction.is_file())
        self.assertFalse((self.root / "data" / "vods" / f"{key}.mp4").exists())
        self.assertEqual(self.index(), {})
        with self.assertRaises(VodImportError) as caught:
            self.importer.delete({"id": key, "confirm": True})
        self.assertEqual(caught.exception.status, 404)
        for bad in ({"id": "../x", "confirm": True}, {"id": "vod30", "confirm": True}):
            with self.assertRaises(VodImportError):
                self.importer.delete(bad)

    def test_the_archive_window_is_the_very_number_the_console_lists(self):
        """One window, in one place: what Records shows is what this asks Twitch for."""
        self.importer.recent()
        self.assertEqual([call for call in self.calls if call[0] == "recent"],
                         [("recent", "examplechannel", RECENT_LIMIT)])
        self.assertGreaterEqual(RECENT_LIMIT, 50)      # a weekly club's year, not a fortnight

    def test_a_full_window_is_reported_as_such_because_nothing_paginates(self):
        self.importer.tw.channel_recent_vods = lambda channel, limit: [
            {"id": str(2000000000 + n), "title": "night %d" % n, "length_s": 3600,
             "created_at": "2026-09-26T06:46:33Z", "broadcast_type": "HIGHLIGHT",
             "thumbnail": THUMB_CDN} for n in range(limit)]
        rows = {row["channel"]: row for row in self.importer.recent()["channels"]}
        self.assertEqual(len(rows["examplechannel"]["vods"]), RECENT_LIMIT)
        self.assertIs(rows["examplechannel"]["more"], True)     # the window filled: there may be older

    def test_recent_lists_each_saved_channel_caches_in_memory_and_reports_errors(self):
        self.sources.append({"id": "s2", "kind": "channel", "channel": "brokenchannel"})
        self.sources.append({"id": "s3", "kind": "video", "video": "5"})
        first = self.importer.recent()
        rows = {row["channel"]: row for row in first["channels"]}
        self.assertEqual(list(rows), ["examplechannel", "brokenchannel"])
        self.assertEqual(rows["examplechannel"]["vods"][0]["id"], OWN)
        self.assertEqual(rows["examplechannel"]["vods"][0]["imported"], [])
        # The console is handed a path on this server, never the image CDN's URL.
        self.assertEqual(rows["examplechannel"]["vods"][0]["thumb"],
                         "/api/vods/thumb?channel=examplechannel&id=" + OWN)
        # What Twitch calls it travels with the row, so the console can name it without a rule.
        self.assertEqual(rows["examplechannel"]["vods"][0]["broadcast_type"], "ARCHIVE")
        # One row is not a full window, so this list is not claiming to be a window at all.
        self.assertIs(rows["examplechannel"]["more"], False)
        self.assertIsNone(rows["brokenchannel"]["vods"])           # an error, never a pretend-empty list
        self.assertEqual(rows["brokenchannel"]["error"], "Twitch API request failed (HTTP 500)")
        # The window is the importer's own constant (see the test above); this test is about
        # which channel is asked and what is cached, not about how wide the window is.
        self.assertIn(("recent", "examplechannel", RECENT_LIMIT), self.calls)
        self.importer.recent()
        self.assertEqual(self.calls.count(("recent", "examplechannel", RECENT_LIMIT)), 1)   # served from memory
        self.assertEqual(self.calls.count(("recent", "brokenchannel", RECENT_LIMIT)), 2)  # errors are not cached

    def test_a_picture_is_served_for_a_saved_channel_only(self):
        content_type, body = self.importer.thumbnail("examplechannel", OWN)
        self.assertEqual(content_type, "image/jpeg")
        self.assertTrue(body.startswith(b"\xff\xd8\xff"))
        self.assertIn(("thumb", OWN), self.calls)
        before = list(self.calls)
        with self.assertRaises(VodImportError) as refused:
            self.importer.thumbnail("someoneelse", OWN)
        self.assertEqual(refused.exception.status, 403)
        self.assertEqual(self.calls, before)                 # refused before Twitch was asked
        with self.assertRaises(VodImportError) as unknown:
            self.importer.thumbnail("examplechannel", OTHER)
        self.assertEqual(unknown.exception.status, 502)      # Twitch's own safe sentence

    def test_the_picture_path_is_empty_when_twitch_sent_nothing(self):
        self.assertEqual(thumb_path("examplechannel", {"id": OWN, "thumbnail": ""}), "")
        self.assertEqual(thumb_path("examplechannel", {"id": OWN}), "")
        self.assertEqual(thumb_path("not a channel", {"id": OWN, "thumbnail": THUMB_CDN}), "")
        self.assertEqual(thumb_path("examplechannel", {"id": "abc", "thumbnail": THUMB_CDN}), "")
        self.assertEqual(thumb_path("examplechannel", {"id": OWN, "thumbnail": THUMB_CDN}),
                         "/api/vods/thumb?channel=examplechannel&id=" + OWN)

    def test_parsing_and_redaction(self):
        self.assertEqual(seconds_done({"out_time_us": "1500000"}), 1.5)
        self.assertEqual(seconds_done({"out_time_us": "N/A", "out_time": "00:01:02.500000"}), 62.5)
        self.assertIsNone(seconds_done({"out_time_us": "N/A"}))
        self.assertEqual(redact("open " + SIGNED + " failed"), "open <media URL> failed")
        for bad in ({"vod": OWN, "start_s": -1}, {"vod": OWN, "start_s": 1.5}, {"vod": OWN, "duration_s": 0},
                    {"vod": OWN, "start_s": 13397}, {"vod": "nope"}, {}, {"vod": OWN, "extra": 1}):
            with self.assertRaises(VodImportError, msg=repr(bad)):
                self.importer.start(bad)

    def test_reads_never_write(self):
        self.importer.start({"vod": OWN, "start_s": 0, "duration_s": 60})
        self.wait()
        stamp = {str(p): (hashlib.md5(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                 for p in self.root.rglob("*") if p.is_file()}
        self.importer.recent()
        self.importer.job()
        self.importer.estimate({"vod": OWN, "start_s": "3600", "duration_s": "300"})
        self.assertEqual({str(p): (hashlib.md5(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                          for p in self.root.rglob("*") if p.is_file()}, stamp)

    # -- the automatic download: scan, queue, drain -------------------------------------------
    def test_the_scan_queues_every_broadcast_the_archive_does_not_have(self):
        second = "1000000002"
        self.importer._twitch = archive_stub(self.calls, [archive_row(OWN, title="261001"),
                                                          archive_row(second, title="260924")])
        self.importer.auto({"action": "off"})                 # fill the queue, do not download it
        view = self.importer.scan()
        self.assertEqual(view["queued"], [{"id": OWN, "channel": "examplechannel", "title": "261001",
                                           "length_s": 13397, "state": "queued", "error": None},
                                          {"id": second, "channel": "examplechannel", "title": "260924",
                                           "length_s": 13397, "state": "queued", "error": None}])
        self.assertIsNone(view["current"])
        self.assertEqual((view["done"], view["skipped"], view["error"]), ([], [], None))
        self.assertIsNotNone(view["last_scan"])
        self.assertEqual(self.calls, [("recent", "examplechannel", RECENT_LIMIT)])
        self.assertEqual(self.importer.scan()["queued"], view["queued"])   # no duplicate on a rescan

    def test_a_broadcast_the_archive_already_has_is_never_queued_again(self):
        second = "1000000002"
        self.importer.start({"vod": OWN, "start_s": 0, "duration_s": 60})   # a real entry first
        self.assertEqual(self.wait()["id"], f"tw-{OWN}-0-60")
        self.importer._twitch = archive_stub(self.calls, [archive_row(OWN), archive_row(second)])
        self.importer.auto({"action": "off"})
        self.assertEqual([row["id"] for row in self.importer.scan()["queued"]], [second])

    def test_the_queue_drains_in_order_through_the_ordinary_job_route(self):
        ids = [OWN, "1000000002", "1000000003"]
        self.importer._twitch = archive_stub(self.calls, [archive_row(vod_id) for vod_id in ids])
        view = self.importer.auto({"action": "on", "seconds": 60})     # the whole pipeline, 60 s each
        self.assertTrue(view["enabled"])
        view = self.wait_until(lambda seen: not seen["queued"] and seen["current"] is None)
        self.assertEqual([row["id"] for row in view["done"]], ids)     # FIFO: the arrival order
        self.assertEqual(view["skipped"], [])
        self.assertEqual(sorted(self.index()), [f"tw-{vod_id}-0-60" for vod_id in ids])
        self.assertEqual(self.importer.job()["state"], "done")
        for vod_id in ids:                                            # each one went through start()
            self.assertIn(("info", vod_id), self.calls)
            self.assertEqual((self.root / "data" / "vods" / f"tw-{vod_id}-0-60.mp4").read_bytes(),
                             b"partial")
        self.assertFalse(list((self.root / "data" / "vods").glob("*.part")))

    def test_a_refused_disk_skips_the_item_with_the_sentence_and_the_queue_moves_on(self):
        ids = [OWN, "1000000002"]
        self.importer._twitch = archive_stub(self.calls, [archive_row(vod_id) for vod_id in ids])
        self.free = 10**9                                     # under the 2 GB reserve alone
        view = self.importer.auto({"action": "scan"})
        view = self.wait_until(lambda seen: not seen["queued"] and seen["current"] is None)
        self.assertEqual([row["id"] for row in view["skipped"]], ids)
        self.assertEqual(view["done"], [])
        for row in view["skipped"]:
            self.assertEqual(row["state"], "skipped")
            self.assertIn("Not enough free disk space", row["error"])
            self.assertIn("needs 2.0 GB", row["error"])       # _disk(0): the reserve is the gate
            self.assertIn("1.0 GB is free", row["error"])
        self.assertNotIn(("info", OWN), self.calls)           # refused before any plan or token
        self.assertFalse((self.root / "data" / "vods").exists())
        self.assertFalse((self.root / "out" / "vods" / "index.json").exists())

    def test_one_broken_broadcast_is_skipped_and_the_next_one_still_imports(self):
        good = "1000000002"
        self.importer._twitch = archive_stub(self.calls, [archive_row(OWN), archive_row(good)],
                                            broken=(OWN,))
        view = self.importer.auto({"action": "on", "seconds": 60})
        view = self.wait_until(lambda seen: not seen["queued"] and seen["current"] is None)
        self.assertEqual([row["id"] for row in view["done"]], [good])
        self.assertEqual([row["id"] for row in view["skipped"]], [OWN])
        self.assertEqual(view["skipped"][0]["error"], "Twitch has no such video")
        self.assertEqual(list(self.index()), [f"tw-{good}-0-60"])
        self.assertFalse((self.root / "data" / "vods" / f"tw-{OWN}-0-60.mp4").exists())

    def test_the_seconds_knob_is_the_only_bounded_range_and_it_is_capped(self):
        self.importer._twitch = archive_stub(self.calls, [archive_row(OWN)])
        self.assertEqual(self.importer.auto({"seconds": 3600})["seconds"], 3600)
        for bad in (0, 3601, True, "60", 1.5, None):
            with self.assertRaises(VodImportError) as caught:
                self.importer.auto({"seconds": bad})
            self.assertEqual(str(caught.exception),
                             "seconds must be a whole number of seconds from 1 to 3600")
        with self.assertRaises(VodImportError) as caught:
            self.importer.auto({"seconds": 60, "turbo": True})
        self.assertEqual(str(caught.exception), "unsupported auto option: turbo")
        with self.assertRaises(VodImportError) as caught:
            self.importer.auto({"action": "later"})
        self.assertEqual(str(caught.exception), 'action must be "on", "off" or "scan"')
        with self.assertRaises(VodImportError):
            self.importer.auto(["scan"])
        self.assertEqual(self.importer.auto({})["seconds"], 3600)   # "scan" keeps the operator's knob
        self.importer.close()                     # the first scan already started an import
        self.wait(states=("done", "error", "cancelled", "idle"))

    def test_twitch_being_down_is_a_sentence_and_an_idle_worker(self):
        self.sources = [{"id": "s1", "kind": "channel", "channel": "brokenchannel"}]
        view = self.importer.auto({"action": "on"})
        self.assertEqual(view["queued"], [])
        self.assertIsNone(view["current"])
        self.assertIsNotNone(view["last_scan"])
        self.assertEqual(view["error"], "brokenchannel: Twitch API request failed (HTTP 500)")
        self.assertEqual(self.importer.job()["state"], "idle")
        self.assertTrue(self.importer.auto_queue()["enabled"])          # a read is not a crash
        self.assertGreaterEqual(self.calls.count(("recent", "brokenchannel", RECENT_LIMIT)), 1)

    def test_off_stops_the_downloads_and_on_starts_them_again(self):
        self.importer._twitch = archive_stub(self.calls, [archive_row(OWN)])
        off = self.importer.auto({"action": "off"})
        self.assertEqual((off["enabled"], off["queued"]), (False, []))
        self.assertEqual([row["id"] for row in self.importer.scan()["queued"]], [OWN])
        time.sleep(0.15)
        waiting = self.importer.auto_queue()                            # a read does not override off
        self.assertEqual((waiting["enabled"], [row["id"] for row in waiting["queued"]]), (False, [OWN]))
        self.assertIsNone(waiting["current"])
        self.assertFalse((self.root / "data").exists())
        on = self.importer.auto({"action": "on"})
        self.assertTrue(on["enabled"])
        view = self.wait_until(lambda seen: not seen["queued"] and seen["current"] is None)
        self.assertEqual([row["id"] for row in view["done"]], [OWN])     # the FIFO survived the off

    def test_the_periodic_rescan_finds_a_broadcast_that_appeared_later(self):
        vods = []
        self.importer = self.make(twitch=archive_stub(self.calls, vods), auto_interval_s=0.05)
        self.importer.auto({"action": "on"})
        self.assertEqual(self.importer.auto_queue()["queued"], [])
        vods.append(archive_row(OWN))                          # the broadcast ends 20 s later
        view = self.wait_until(lambda seen: len(seen["done"]) == 1)
        self.assertEqual([row["id"] for row in view["done"]], [OWN])
        self.assertGreaterEqual(self.calls.count(("recent", "examplechannel", RECENT_LIMIT)), 2)
        self.assertEqual(view["interval_s"], 0.05)
        self.assertEqual(list(self.index()), [f"tw-{OWN}"])            # no knob: the whole broadcast
        self.importer.close()
        self.assertFalse(self.importer.auto_queue()["enabled"])         # close stops the beat

    def test_the_disk_gate_reads_the_live_free_space_before_every_item(self):
        ids = [OWN, "1000000002"]
        self.importer._twitch = archive_stub(self.calls, [archive_row(vod_id) for vod_id in ids])
        self.free = 10**9
        self.importer.auto({"action": "scan"})
        self.wait_until(lambda seen: not seen["queued"] and seen["current"] is None)
        self.free = 10**12                                     # space appears: a scan retries them
        view = self.importer.auto({"action": "scan"})
        view = self.wait_until(lambda seen: not seen["queued"] and seen["current"] is None)
        self.assertEqual([row["id"] for row in view["done"]], ids)
        self.assertEqual(len(self.index()), 2)


class ProbeTests(unittest.TestCase):
    """A stream-copied range keeps pre-roll behind an edit list: the probe counts what decodes."""

    def test_a_stream_copied_range_reports_its_decodable_frames(self):
        import shutil as sh
        from annotator.unified_server import Backend as ServerBackend
        from annotator.vod_import import probe_media
        try:
            ffmpeg = ServerBackend._ffmpeg()
        except APIError:
            self.skipTest("ffmpeg is unavailable on this host")
        with tempfile.TemporaryDirectory() as temp:
            source, cut = Path(temp) / "source.mp4", Path(temp) / "cut.mp4"
            import subprocess
            subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=96x64:rate=30:duration=6",
                            "-c:v", "libx264", "-g", "60", "-bf", "2", "-pix_fmt", "yuv420p", "-y", str(source)],
                           check=True, timeout=120)
            subprocess.run([ffmpeg, "-v", "error", "-protocol_whitelist", "file", "-ss", "2.5", "-i", str(source),
                            "-t", "2", "-c", "copy", "-movflags", "+faststart", "-f", "mp4", "-y", str(cut)],
                           check=True, timeout=120)
            import cv2
            cap = cv2.VideoCapture(str(cut))
            container = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            decodable = 0
            while cap.read()[0]:
                decodable += 1
            cap.release()
            meta = probe_media(cut, [ffmpeg])
            self.assertEqual(meta["frames"], decodable)
            self.assertGreater(container, decodable)             # the pre-roll the edit list hides
            self.assertEqual((meta["width"], meta["height"]), (96, 64))
            self.assertIsNotNone(sh.which(ffmpeg) or ffmpeg)


class EndpointTests(unittest.TestCase):
    """The routes, through the real handler: same-origin, size limits and error bodies."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.calls = []
        script = self.root / "fake_ffmpeg.py"
        script.write_text(FAKE_FFMPEG)
        Path(str(script) + ".mode").write_text("ok")
        self.backend = Backend(self.root)
        self.backend._vod_importer = VodImporter(
            self.root, lambda: {"sources": [{"kind": "channel", "channel": "examplechannel"}]},
            twitch=twitch_stub(self.calls), ffmpeg=lambda: [sys.executable, str(script)],
            probe=lambda path: {"fps": 30.0, "frames": 1800, "width": 1280, "height": 720},
            disk_usage=lambda path: SimpleNamespace(free=10**12))
        handler = type("Quiet", (make_handler(self.backend),), {"log_message": lambda *a: None})
        self.httpd = BoundedHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.addCleanup(self.backend.close)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=20)
        try:
            data = None if body is None else json.dumps(body).encode()
            headers = dict(headers or {}, **({"Content-Type": "application/json"} if data else {}))
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read() or b"null")
        finally:
            connection.close()

    def test_import_browse_and_delete_over_http(self):
        status, job = self.request("POST", "/api/vods/import", {"vod": OWN, "start_s": 60, "duration_s": 60})
        self.assertEqual((status, job["state"]), (200, "running"))
        deadline = time.monotonic() + 30
        while self.request("GET", "/api/vods/job")[1]["state"] == "running":
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.05)
        self.assertEqual(self.request("GET", "/api/vods/job")[1]["state"], "done")
        key = f"tw-{OWN}-60-120"
        status, listed = self.request("GET", "/api/datasets")
        self.assertEqual([row["id"] for row in listed["datasets"]], ["vod30", "highlight", key])
        self.assertEqual(self.request("GET", f"/api/{key}/events"),
                         (200, {"events": [], "annotations": {}, "analysed": False}))
        self.assertEqual(self.request("GET", f"/api/{key}/anchors")[0], 404)   # vod30-only stays gated
        status, recent = self.request("GET", "/api/vods/recent")
        self.assertEqual(recent["channels"][0]["vods"][0]["imported"], [key])
        status, estimate = self.request("GET", f"/api/vods/estimate?vod={OWN}&start_s=3600&duration_s=300")
        self.assertEqual((status, estimate["id"], estimate["estimate_bytes"]), (200, f"tw-{OWN}-3600-3900", 112500000))
        status, result = self.request("POST", "/api/vods/delete", {"id": key, "confirm": True})
        self.assertEqual((status, result["media_removed"]), (200, True))
        self.assertEqual(self.request("GET", f"/api/{key}/events")[0], 404)

    def test_the_picture_route_is_binary_and_refuses_other_channels(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=20)
        try:
            connection.request("GET", "/api/vods/thumb?channel=examplechannel&id=" + OWN)
            response = connection.getresponse()
            body = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "image/jpeg")
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertTrue(body.startswith(b"\xff\xd8\xff"))
        finally:
            connection.close()
        status, error = self.request("GET", "/api/vods/thumb?channel=someoneelse&id=" + OWN)
        self.assertEqual(status, 403)
        self.assertIn("Only saved channels", error["error"])
        status, error = self.request("GET", "/api/vods/thumb?channel=examplechannel&id=" + OTHER)
        self.assertEqual(status, 502)
        self.assertIn("no such video", error["error"])
        self.assertEqual(self.request("GET", "/api/vods/thumb")[0], 403)

    def test_refusals_are_plain_json_errors(self):
        status, body = self.request("POST", "/api/vods/import", {"vod": OTHER})
        self.assertEqual((status, body), (400, {"error": REFUSED_CHANNEL.format(channel="someoneelse")}))
        status, body = self.request("POST", "/api/vods/import", {"vod": OWN},
                                    headers={"Origin": "http://evil.example"})
        self.assertEqual((status, body["error"]), (403, "cross-origin write rejected"))
        status, body = self.request("POST", "/api/vods/cancel", {"confirm": True})
        self.assertEqual((status, body["error"]), (409, "No import is running."))
        status, body = self.request("POST", "/api/vods/delete", {"id": "../../etc", "confirm": True})
        self.assertEqual(status, 400)
        self.assertEqual(self.request("GET", "/api/vods/nope")[0], 404)
        self.assertNotIn(("resolve", OTHER), self.calls)

    def test_the_queue_route_downloads_by_itself_and_auto_refuses_a_typo(self):
        status, queue = self.request("GET", "/api/vods/queue")
        self.assertEqual(status, 200)
        self.assertEqual(set(queue), {"enabled", "scanning", "interval_s", "seconds", "queued",
                                      "current", "done", "skipped", "last_scan", "error"})
        self.assertEqual((queue["enabled"], [row["id"] for row in queue["queued"] or [queue["current"]]
                                             if row]), (True, [OWN]))
        self.assertIsNotNone(queue["last_scan"])
        self.assertIsNone(queue["seconds"])
        deadline = time.monotonic() + 30                              # one read, no click, downloads
        while not self.request("GET", "/api/vods/queue")[1]["done"]:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.05)
        queue = self.request("GET", "/api/vods/queue")[1]
        self.assertEqual([row["id"] for row in queue["done"]], [OWN])
        self.assertEqual((queue["queued"], queue["current"], queue["skipped"]), ([], None, []))
        self.assertEqual(self.request("GET", "/api/vods/job")[1]["id"], f"tw-{OWN}")
        status, listed = self.request("GET", "/api/datasets")
        self.assertIn(f"tw-{OWN}", [row["id"] for row in listed["datasets"]])
        status, body = self.request("POST", "/api/vods/auto", {"action": "off", "seconds": 60})
        self.assertEqual((status, body["enabled"], body["seconds"]), (200, False, 60))
        self.assertEqual(self.request("GET", "/api/vods/queue")[1]["enabled"], False)
        status, body = self.request("POST", "/api/vods/auto", {"seconds": 5000})
        self.assertEqual((status, body["error"]),
                         (400, "seconds must be a whole number of seconds from 1 to 3600"))
        status, body = self.request("POST", "/api/vods/auto", {"aciton": "on"})
        self.assertEqual((status, body["error"]), (400, "unsupported auto option: aciton"))
        status, body = self.request("POST", "/api/vods/auto", {"action": "on"})
        self.assertEqual((status, body["enabled"]), (200, True))
        self.assertEqual(self.request("GET", "/api/vods/queue")[1]["enabled"], True)


if __name__ == "__main__":
    unittest.main()
