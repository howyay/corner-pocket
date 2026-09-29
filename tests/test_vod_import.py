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
from annotator.vod_import import PROTOCOLS, REFUSED_CHANNEL, VodImporter, VodImportError, redact, seconds_done

OWN, OTHER = "1000000001", "1111111111"
SIGNED = "https://d2nvs31859zcd8.cloudfront.net/abc/720p30/index-dvr.m3u8?sig=SECRET&token=TOKEN"


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
                 "channel": channel}]

    return SimpleNamespace(TwitchVodError=TwitchError, vod_id_of=vod_id_of, vod_info=vod_info,
                           resolve_vod=resolve_vod, channel_recent_vods=channel_recent_vods)


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

    def test_recent_lists_each_saved_channel_caches_in_memory_and_reports_errors(self):
        self.sources.append({"id": "s2", "kind": "channel", "channel": "brokenchannel"})
        self.sources.append({"id": "s3", "kind": "video", "video": "5"})
        first = self.importer.recent()
        rows = {row["channel"]: row for row in first["channels"]}
        self.assertEqual(list(rows), ["examplechannel", "brokenchannel"])
        self.assertEqual(rows["examplechannel"]["vods"][0]["id"], OWN)
        self.assertEqual(rows["examplechannel"]["vods"][0]["imported"], [])
        self.assertIsNone(rows["brokenchannel"]["vods"])           # an error, never a pretend-empty list
        self.assertEqual(rows["brokenchannel"]["error"], "Twitch API request failed (HTTP 500)")
        self.assertIn(("recent", "examplechannel", 10), self.calls)
        self.importer.recent()
        self.assertEqual(self.calls.count(("recent", "examplechannel", 10)), 1)   # served from memory
        self.assertEqual(self.calls.count(("recent", "brokenchannel", 10)), 2)  # errors are not cached

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


if __name__ == "__main__":
    unittest.main()
