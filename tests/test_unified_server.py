"""Fixture-only backend tests; never start a server or touch repository labels."""
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

from annotator.unified_server import APIError, Backend, atomic_save, load, make_handler
from src.pid_seed_rebuild import explicit_seeds, run


def file_stamp(path):
    """Bytes + size + mtime: the three things a read must never change."""
    path = Path(path)
    return (hashlib.md5(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = Backend(self.root)
        self.out = self.root / "out"
        for folder in ("scan30", "scan_highlight"):
            atomic_save(self.out / folder / "events.json", [{"id": 1, "t": 70, "evidence": "frame.jpg"}])
            atomic_save(self.out / folder / "annotations.json", {"1": {"note": folder, "shooter": "B", "custom": 9}})
            (self.out / folder / "frame.jpg").write_bytes(b"jpeg")
        atomic_save(self.out / "events_actors.json", [{"t": 70, "actor": "A"}])
        self.crop = self.out / "unlabeled_crops"
        self.original = str(self.crop / "crop.jpg")
        atomic_save(self.crop / "meta.json", [{"file": self.original, "t": 70}])
        atomic_save(self.crop / "labels.json", {self.original: 4, "legacy-other": 8})
        atomic_save(self.crop / "ctx.json", {self.original: "ctx/context.jpg"})
        (self.crop / "crop.jpg").write_bytes(b"crop")
        (self.crop / "ctx").mkdir()
        (self.crop / "ctx" / "context.jpg").write_bytes(b"context")
        self.tracklets = {"68-94": {"tracklets": [{"id": n, "n": 2, "samples": [[68, [1, 2, 3, 4]], [70, [2, 3, 4, 5]]]} for n in (1, 2, 3)]}}
        atomic_save(self.out / "pid2_tracklets.json", self.tracklets)
        self.legacy = {"win": "68-94", "t": 68, "track_id": 1, "custom": "keep"}
        atomic_save(self.out / "pid_seed.json", {"seeds": {"1:68-94": self.legacy}, "custom": True})

    def test_dataset_isolation_and_annotation_merge(self):
        self.backend.post(["api", "vod30", "annotate"], {"event_id": 1, "verdict": "correct"})
        vod = self.backend.get(["api", "vod30", "events"], {})
        high = self.backend.get(["api", "highlight", "events"], {})
        self.assertEqual(vod["annotations"]["1"]["shooter"], "B")
        self.assertEqual(vod["annotations"]["1"]["custom"], 9)
        self.assertEqual(high["annotations"]["1"]["note"], "scan_highlight")
        self.assertEqual(high["actors"], {})
        self.assertEqual(vod["actors"]["1"]["actor"], "A")
        for payload in ({"event_id": 9}, {"event_id": 1, "verdict": "bad"}, {"event_id": 1, "shooter": "C"}):
            with self.assertRaises(APIError):
                self.backend.post(["api", "vod30", "annotate"], payload)

    def test_event_geometry_projects_millimetres_into_frame_pixels(self):
        # The stage draws in frame pixels, the scan stores canonical millimetres:
        # the projection is additive and the stored fields are never rewritten.
        atomic_save(self.out / "scan30" / "corners.json",
                    {"corners": [[100, 100], [1100, 120], [1120, 620], [90, 600]]})
        atomic_save(self.out / "scan30" / "events.json", [
            {"id": 7, "t": 5.6, "type": "pot", "window_s": [4.6, 8.6],
             "last_mm": [5.0, 1270.0], "nearest_pocket": "left-side (5mm)"},
            {"id": 8, "t": 6.0, "type": "shot", "window_s": [5.0, 9.0], "disp_mm": 172,
             "speed_m_s": 2.6, "ball_from": [100.0, 200.0], "ball_to": [300.0, 400.0]},
        ])
        payload = self.backend.get(["api", "vod30", "events"], {})
        self.assertEqual(payload["geometry"], {"source": "scan cloth quad", "projected": 2, "total": 2})
        pot, shot = payload["events"]
        # Existing fields keep their names and values.
        self.assertEqual(pot["last_mm"], [5.0, 1270.0])
        self.assertEqual(pot["nearest_pocket"], "left-side (5mm)")
        self.assertEqual(pot["window_s"], [4.6, 8.6])
        self.assertEqual(shot["disp_mm"], 172)
        self.assertEqual(shot["speed_m_s"], 2.6)
        # Additive geometry, in frame pixels.
        for point in (pot["last_px"], pot["pocket_px"], shot["from_px"], shot["to_px"]):
            self.assertEqual(len(point), 2)
            self.assertTrue(0 <= point[0] <= 1280 and 0 <= point[1] <= 720, point)
        self.assertEqual(shot["speed_mm_s"], 2600)
        self.assertEqual(pot["pocket_name"], "left-side")
        self.assertEqual(pot["px_source"], "scan cloth quad")
        # The pocket the event names is the pocket it points at: a ball reported
        # 5 mm from the left side pocket must land next to that marker.
        self.assertLess(math.hypot(pot["last_px"][0] - pot["pocket_px"][0],
                                   pot["last_px"][1] - pot["pocket_px"][1]), 20)

    def test_event_geometry_stays_millimetres_only_without_a_calibration(self):
        atomic_save(self.out / "scan30" / "events.json", [
            {"id": 3, "t": 9.4, "type": "pot", "last_mm": [1287.7, 2526.4], "nearest_pocket": "foot-right (22mm)"},
        ])
        payload = self.backend.get(["api", "vod30", "events"], {})
        self.assertIsNone(payload["geometry"])
        event = payload["events"][0]
        self.assertEqual(event["last_mm"], [1287.7, 2526.4])
        self.assertNotIn("last_px", event)
        self.assertNotIn("pocket_px", event)
        self.assertNotIn("px_source", event, "an event without pixels must not claim a projection source")

    def test_ball_legacy_keys_and_context(self):
        route = ["api", "balls", "unlabeled_crops", "label"]
        self.backend.post(route, {"file": "crop.jpg", "label": 15})
        self.assertEqual(load(self.crop / "labels.json"), {self.original: 15, "legacy-other": 8})
        self.backend.post(route, {"file": "crop.jpg", "label": -1})
        self.assertEqual(load(self.crop / "labels.json")[self.original], "u")
        result = self.backend.get(["api", "balls", "unlabeled_crops", "meta"], {})
        self.assertEqual(result["items"][0]["ctx"], "context.jpg")
        self.assertEqual(result["labels"]["crop.jpg"], "u")
        self.backend.post(route, {"file": "crop.jpg", "label": None})
        self.assertEqual(load(self.crop / "labels.json"), {"legacy-other": 8})
        with self.assertRaises(APIError):
            self.backend.post(route, {"file": "other.jpg", "label": 1})
        with self.assertRaises(APIError):
            self.backend.post(route, {"file": "crop.jpg", "label": True})

    def test_media_allowlist_and_symlinks(self):
        self.assertEqual(self.backend.media(["media", "vod30", "evidence", "frame.jpg"]).read_bytes(), b"jpeg")
        self.assertEqual(self.backend.media(["media", "balls", "unlabeled_crops", "ctx", "context.jpg"]).read_bytes(), b"context")
        for parts in (["media", "vod30", "evidence", "annotations.json"], ["media", "vod30", "evidence", "../frame.jpg"], ["media", "balls", "unknown", "crop.jpg"]):
            with self.assertRaises(APIError):
                self.backend.media(parts)
        (self.crop / "crop.jpg").unlink()
        (self.crop / "crop.jpg").symlink_to(self.out / "scan30" / "frame.jpg")
        with self.assertRaises(APIError):
            self.backend.media(["media", "balls", "unlabeled_crops", "crop.jpg"])

    def test_anchors_bounded_atomic_and_preserved(self):
        atomic_save(self.out / "pid_anchors_vod30.json", {"anchors": {"20": [[1, 2]] * 6}, "custom": 3})
        info = {"t": 70, "width": 100, "height": 50}
        with patch.object(self.backend, "anchor_info", return_value=info):
            route = ["api", "vod30", "anchors"]
            for points in ([[1, 2]] * 5, [[float("nan"), 2]] * 6, [[100, 2]] * 6, [[1, float("inf")]] * 6):
                with self.assertRaises(APIError):
                    self.backend.post(route, {"t": 70, "pts": points})
            self.backend.post(route, {"t": 70, "pts": [[99, 49]] * 6})
        saved = load(self.out / "pid_anchors_vod30.json")
        self.assertEqual(saved["anchors"]["20"], [[1, 2]] * 6)
        self.assertEqual(saved["anchors"]["70"], [[99, 49]] * 6)
        self.assertEqual(saved["custom"], 3)
        with self.assertRaises(APIError):
            self.backend.get(["api", "vod30", "anchors"], {"t": ["NaN"]})
        with self.assertRaises(APIError):
            self.backend.get(["api", "highlight", "anchors"], {})

    def test_explicit_seeds_and_tracks(self):
        route = ["api", "vod30", "seeds"]
        base = {"win": "68-94", "t": 70, "track_id": 2}
        with self.assertRaises(APIError):
            self.backend.post(route, base)
        self.backend.post(route, dict(base, label="B"))
        saved = self.backend.seeds()
        self.assertEqual(saved["seeds"]["1:68-94"], self.legacy)
        self.assertTrue(saved["custom"])
        self.assertEqual(explicit_seeds(self.tracklets, saved["seeds"]), {"2:68-94": "B"})
        tracks = self.backend.get(["api", "vod30", "tracks"], {"win": ["68-94"], "t": ["70"]})
        self.assertEqual(tracks["tracks"][1], {"id": 2, "box": [2, 3, 4, 5], "label": "B"})
        self.backend.post(route, dict(base, label="ignore"))
        self.assertEqual(self.backend.seeds()["seeds"]["2:68-94"]["label"], "ignore")
        self.backend.post(route, dict(base, label=None))
        self.assertNotIn("2:68-94", self.backend.seeds()["seeds"])
        with self.assertRaises(APIError):
            self.backend.post(route, dict(base, t=71, label="A"))

    def test_a_guest_name_is_stored_as_the_track_label_and_never_trains_an_identity(self):
        # The rail's second labelling option: the typed name is this track's
        # label in the same seeds store, so the card, the rail and the tracks
        # route all read it back - while the identity rebuild keeps reading
        # exactly the three legacy role values and ignores the name.
        route = ["api", "vod30", "seeds"]
        base = {"win": "68-94", "t": 70, "track_id": 2}
        self.backend.post(route, dict(base, label="  Minh  "))
        self.assertEqual(self.backend.seeds()["seeds"]["2:68-94"]["label"], "Minh")
        tracks = self.backend.get(["api", "vod30", "tracks"], {"win": ["68-94"], "t": ["70"]})
        self.assertEqual(tracks["tracks"][1], {"id": 2, "box": [2, 3, 4, 5], "label": "Minh"})
        self.assertEqual(explicit_seeds(self.tracklets, self.backend.seeds()["seeds"]), {}, "a guest name never enters identity training")
        self.assertTrue(self.backend.predictions()["stale"], "and cannot make the stored prediction look current")
        # The three legacy values still mean what they meant, and Clear still clears.
        for label in ("A", "B", "ignore"):
            self.backend.post(route, dict(base, label=label))
            self.assertEqual(explicit_seeds(self.tracklets, self.backend.seeds()["seeds"]), {"2:68-94": label})
        self.backend.post(route, dict(base, label=None))
        self.assertNotIn("2:68-94", self.backend.seeds()["seeds"])
        for bad in ("", "   ", "x" * 61, 5, ["A"]):
            with self.assertRaises(APIError):
                self.backend.post(route, dict(base, label=bad))
        self.assertNotIn("2:68-94", self.backend.seeds()["seeds"], "a rejected label writes nothing")

    def test_rebuild_without_both_seeds_unknown_no_model_load(self):
        before = (self.out / "pid_seed.json").read_bytes()
        run(self.root)
        result = load(self.out / "pid_seed_tracks.json")
        self.assertEqual(set(result["map"].values()), {"?"})
        self.assertEqual((self.out / "pid_seed.json").read_bytes(), before)
        self.assertIsNone(load(self.out / "pid_seed_protos.json")["B"])

    def test_event_frame_is_dataset_scoped(self):
        with patch.object(self.backend, "frame_jpeg", return_value=b"event-jpeg") as frame:
            handler = self.handler("/media/highlight/event-frame/1")
            handler.do_GET()
            self.assertEqual(handler.status, 200)
            self.assertEqual(handler.wfile.getvalue(), b"event-jpeg")
            frame.assert_called_once_with(70, "highlight")
            for path in ("/media/unknown/event-frame/1", "/media/vod30/event-frame/999"):
                handler = self.handler(path)
                handler.do_GET()
                self.assertEqual(handler.status, 404)

    def test_stale_predictions_suppressed(self):
        path = self.out / "pid_seed_tracks.json"
        atomic_save(path, {"map": {"1:68-94": "A"}, "detail": {}})
        self.assertEqual(self.backend.predictions()["map"], {})
        route = ["api", "vod30", "seeds"]
        for tid, label in ((1, "A"), (2, "B")):
            self.backend.post(route, {"win": "68-94", "t": 70, "track_id": tid, "label": label})
        self.assertTrue(self.backend.predictions()["stale"])
        labels = {"1:68-94": "A", "2:68-94": "B"}
        atomic_save(path, {"map": labels, "detail": {}, "seed_labels": labels})
        self.assertFalse(self.backend.predictions()["stale"])
        self.assertEqual(self.backend.predictions()["map"], labels)
        self.backend.post(route, {"win": "68-94", "t": 70, "track_id": 3, "label": "ignore"})
        self.assertTrue(self.backend.predictions()["stale"])

    def test_raw_frame_has_no_baked_overlays(self):
        # Inject OpenCV at the lazy import seam: only capture/read/encode are allowed.
        from types import SimpleNamespace
        from unittest.mock import Mock
        pixels = object()
        capture = Mock()
        capture.isOpened.return_value = True
        capture.get.side_effect = [25, 2500]
        capture.read.return_value = (True, pixels)
        encoded = Mock()
        encoded.tobytes.return_value = b"raw-jpeg"
        cv = SimpleNamespace(VideoCapture=Mock(return_value=capture),
                             CAP_PROP_FPS=1, CAP_PROP_FRAME_COUNT=2, CAP_PROP_POS_MSEC=3,
                             imencode=Mock(return_value=(True, encoded)))
        with patch.dict("sys.modules", {"cv2": cv}), patch.object(self.backend, "video", return_value=self.root / "video.mp4"):
            self.assertEqual(self.backend.frame_jpeg(70), b"raw-jpeg")
        cv.imencode.assert_called_once_with(".jpg", pixels)
        capture.set.assert_called_once_with(3, 70000)
        capture.release.assert_called_once()

    def test_rebuild_failure_exposed(self):
        with patch("annotator.unified_server.subprocess.run", side_effect=RuntimeError("missing checkpoint")):
            self.backend._rebuild()
        self.assertEqual(self.backend.job, {"status": "failed", "error": "missing checkpoint"})
        self.backend.job = {"status": "running", "error": None}
        with self.assertRaises(APIError) as error:
            self.backend.post(["api", "vod30", "rebuild"], {})
        self.assertEqual(error.exception.status, 409)

    def test_atomic_failed_save_keeps_previous(self):
        path = self.out / "atomic.json"
        atomic_save(path, {"old": True})
        with self.assertRaises(ValueError):
            atomic_save(path, {"bad": float("nan")})
        self.assertEqual(load(path), {"old": True})
        self.assertEqual(list(self.out.glob(".atomic.json*")), [])

    def handler(self, path, headers=None, body=b""):
        handler = make_handler(self.backend).__new__(make_handler(self.backend))
        handler.path = path
        handler.headers = headers or {}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.send_response = lambda status: setattr(handler, "status", status)
        handler.response_headers = {}
        handler.send_header = lambda key, value: handler.response_headers.update({key: value})
        handler.end_headers = lambda: None
        return handler

    def test_live_lazy_singleton_and_shutdown(self):
        from unittest.mock import Mock
        import annotator.unified_server as server
        self.assertIsNone(self.backend._live)
        self.backend.close()
        # The class the backend builds is the vod-replay-capable one; the seam is
        # the factory, so the singleton/lazy/close contract is pinned against it.
        with patch.object(server, 'vod_replay_processor_class') as factory:
            processor = factory.return_value.return_value
            self.assertIs(self.backend.live_processor(), processor)
            self.assertIs(self.backend.live_processor(), processor)
            factory.assert_called_once_with()
            factory.return_value.assert_called_once_with(self.root)
            self.backend.close()
            processor.stop.assert_called_once()

    def test_vod_replay_request_reaches_the_capture_with_its_own_values(self):
        from annotator.unified_server import replay_request, vod_replay_processor_class
        # The request shape: an id or a URL, a start offset and a rate. Anything
        # else is the client's error, and the message says which one.
        self.assertEqual(replay_request({'kind': 'vod-replay', 'vod_id': 'https://www.twitch.tv/videos/12345'}),
                         {'vod_id': '12345', 'start_s': 0.0, 'rate': 1.0})
        self.assertEqual(replay_request({'kind': 'vod-replay', 'vod_id': 7, 'start_s': 30, 'rate': 2}),
                         {'vod_id': '7', 'start_s': 30.0, 'rate': 2.0})
        for bad in ({'kind': 'vod-replay'}, {'kind': 'vod-replay', 'vod_id': 'nope'},
                    {'kind': 'vod-replay', 'vod_id': '1', 'rate': 0},
                    {'kind': 'vod-replay', 'vod_id': '1', 'start_s': -1},
                    {'kind': 'vod-replay', 'vod_id': '1', 'extra': True}):
            with self.assertRaisesRegex(ValueError, '(?i)vod|rate|start_s|unsupported'):
                replay_request(bad)
        processor = vod_replay_processor_class()(self.root)
        seen = {}
        resolved = {'vod_id': '12345', 'title': 't', 'length_s': 10.0, 'channel': 'c', 'master_status': 200,
                    'media_url': 'https://usher.ttvnw.net/vod/12345.m3u8?nauth=secret',
                    'variant': {'height': 720, 'bandwidth': 1}, 'variants': [],
                    'playlist': {'type': 'VOD', 'target_duration_s': 2.0, 'segments_in_head': 3, 'has_endlist': True}}
        class FakeCapture:
            def __init__(self, media, **kwargs):
                seen.update(kwargs, media=media)
        with patch('annotator.twitch_vod_source.resolve_vod', return_value=resolved), \
             patch('annotator.twitch_vod_source.VodRealtimeCapture', FakeCapture):
            safe, media = processor._source_media({'kind': 'vod-replay', 'vod_id': '12345', 'start_s': 12.0, 'rate': 2.0})
            capture = processor._capture_factory(media)
        self.assertEqual(safe, {'kind': 'vod-replay', 'vod_id': '12345', 'start_s': 12.0, 'rate': 2.0})
        self.assertEqual(seen, {'vod_id': '12345', 'start_s': 12.0, 'rate': 2.0, 'media': resolved['media_url']})
        self.assertIsInstance(capture, FakeCapture)
        # status() carries the capture's own honest self-description, with the
        # signed URL redacted out of the resolution evidence.
        self.assertEqual(processor._replay_resolution['media_url_host'], 'usher.ttvnw.net')
        self.assertNotIn('m3u8', json.dumps(processor._replay_resolution), 'the signed URL never leaves the process')
        processor._replay_capture = Mock()
        processor._replay_capture.state.return_value = {'kind': 'vod-replay', 'live': False,
                                                        'vod_id': '12345', 'rate': 2.0, 'drift_s': -1.5}
        payload = processor.status()
        self.assertEqual(payload['replay']['kind'], 'vod-replay')
        self.assertFalse(payload['replay']['live'])
        self.assertEqual(payload['replay']['drift_s'], -1.5)
        self.assertEqual(payload['replay']['resolution']['media_url_host'], 'usher.ttvnw.net')

    def test_a_refused_vod_is_a_refused_start_with_twitchs_own_sentence(self):
        from annotator.twitch_vod_source import TwitchVodError
        from annotator.unified_server import vod_replay_processor_class
        self.backend._live = vod_replay_processor_class()(self.root)
        message = 'Twitch VOD playlist request failed (HTTP 403)'
        with patch('annotator.twitch_vod_source.resolve_vod', side_effect=TwitchVodError(message)):
            with self.assertRaises(APIError) as error:
                self.backend.live_action({'action': 'start', 'source': {'kind': 'vod-replay', 'vod_id': '5'}})
        self.assertEqual(error.exception.status, 502)
        self.assertEqual(str(error.exception), message)
        self.assertEqual(self.backend._live.status()['state'], 'idle')
        self.assertIsNone(self.backend._live.status()['error'])

    def test_live_http_status_frame_and_actions(self):
        from unittest.mock import Mock
        from annotator.live_processing import LiveProcessor
        processor = self.backend._live = Mock(spec=LiveProcessor)
        meta = {'seq': 7, 'detections': {'boxes': []}, 'receive_to_result_ms': 12}
        processor.status.return_value = {'status': 'running', 'latest': meta}
        handler = self.handler('/api/live')
        handler.do_GET()
        self.assertEqual(json.loads(handler.wfile.getvalue())['latest'], meta)
        self.assertEqual(handler.response_headers['Cache-Control'], 'no-store')
        processor.latest_jpeg.return_value = None
        handler = self.handler('/api/live/frame')
        handler.do_GET()
        self.assertEqual(handler.status, 404)
        processor.latest_jpeg.return_value = (b'jpeg', meta)
        handler = self.handler('/api/live/frame')
        handler.do_GET()
        self.assertEqual(handler.wfile.getvalue(), b'jpeg')
        self.assertEqual(handler.response_headers['Content-Type'], 'image/jpeg')
        self.assertEqual(handler.response_headers['X-Live-Sequence'], '7')
        self.assertEqual(json.loads(handler.response_headers['X-Live-Metadata']), meta)
        for action in ('start', 'stop'):
            payload = {'action': action}
            if action == 'start':
                payload.update(source={'kind': 'twitch', 'source_id': 'saved'}, detectors=['table'])
            getattr(processor, action).return_value = {'status': 'running' if action == 'start' else 'stopped'}
            body = json.dumps(payload).encode()
            handler = self.handler('/api/live', {'Content-Length': str(len(body)), 'Host': 'localhost:8130', 'Origin': 'http://localhost:8130'}, body)
            handler.do_POST()
            self.assertEqual(handler.status, 200)
        processor.start.assert_called_once_with({'kind': 'twitch', 'source_id': 'saved'}, ['table'])
        processor.stop.assert_called_once_with()

    def test_live_rejects_cross_origin_invalid_action_and_urls(self):
        from unittest.mock import Mock
        from annotator.live_processing import LiveProcessor
        processor = self.backend._live = Mock(spec=LiveProcessor)
        body = b'{"action":"stop"}'
        handler = self.handler('/api/live', {'Content-Length': str(len(body)), 'Host': 'localhost:8130', 'Origin': 'https://attacker.invalid'}, body)
        handler.do_POST()
        self.assertEqual(handler.status, 403)
        processor.stop.assert_not_called()
        for payload in ({'action': 'bad'}, {'action': 'start', 'url': 'https://arbitrary.invalid'}):
            with self.assertRaises(APIError):
                self.backend.live_action(payload)
        processor.start.side_effect = ValueError('saved channel required')
        with self.assertRaisesRegex(APIError, 'saved channel required'):
            self.backend.live_action({'action': 'start', 'source': {'kind': 'twitch', 'url': 'https://arbitrary.invalid'}})
        processor.start.side_effect = RuntimeError('already running')
        with self.assertRaises(APIError) as error:
            self.backend.live_action({'action': 'start'})
        self.assertEqual(error.exception.status, 409)

    def test_club_roster_does_not_rewrite_video_identities(self):
        seed_path = self.out / 'pid_seed.json'
        anchor_path = self.out / 'pid_anchors_vod30.json'
        atomic_save(seed_path, {'seeds': {'A': ['existing-track']}})
        atomic_save(anchor_path, {'anchors': {'existing-track': 'A'}})
        before = {p: p.read_bytes() for p in (seed_path, anchor_path)}
        state = self.backend.get(['api', 'operations'], {})
        state = self.backend.post(['api', 'operations'], {
            'revision': state['revision'], 'action': 'player_save', 'name': 'Club Regular'})
        self.assertEqual(len(state['players']), 1)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertNotIn('seeds', state)
        self.assertNotIn('anchors', state)

    def test_http_operations_persistence_and_error_isolation(self):
        store = self.out / 'corner-pocket' / 'state.json'
        handler = self.handler('/api/operations')
        handler.dispatch()
        self.assertEqual(handler.status, 200)
        initial = json.loads(handler.wfile.getvalue())
        self.assertEqual(initial['revision'], 0)
        self.assertEqual(initial['players'], [])
        self.assertFalse(store.exists())
        payload = {'action': 'player_save', 'revision': 0, 'name': 'HTTP Player'}
        body = json.dumps(payload).encode()
        headers = {'Host': '127.0.0.1:8130', 'Origin': 'http://127.0.0.1:8130',
                   'Content-Type': 'application/json', 'Content-Length': str(len(body))}
        handler = self.handler('/api/operations', headers, body)
        handler.dispatch(post=True)
        self.assertEqual(handler.status, 200)
        saved = json.loads(handler.wfile.getvalue())
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(saved['players'][0]['name'], 'HTTP Player')
        self.assertEqual(Backend(self.root).get(['api', 'operations'], {}), saved)
        before = store.read_bytes()
        cases = [(body, {}, 409), (b'{', {}, 400), (b'[]', {}, 400),
                 (b'{"action":"note_add","revision":1}', {}, 400),
                 (b'{"action":"unknown","revision":1}', {}, 400),
                 (body, {'Origin': 'https://evil.example'}, 403),
                 (body, {'Content-Length': '65537'}, 413)]
        for raw, overrides, expected in cases:
            with self.subTest(raw=raw, overrides=overrides):
                request_headers = {**headers, 'Content-Length': str(len(raw)), **overrides}
                handler = self.handler('/api/operations', request_headers, raw)
                handler.dispatch(post=True)
                self.assertEqual(handler.status, expected)
                self.assertIn('error', json.loads(handler.wfile.getvalue()))
                self.assertEqual(store.read_bytes(), before)
        handler = self.handler('/api/operations')
        handler.dispatch()
        self.assertEqual(json.loads(handler.wfile.getvalue()), saved)

    def test_http_operations_static_allowlist(self):
        assets = self.root / 'annotator'
        assets.mkdir(exist_ok=True)
        for name in ('ops.js', 'ops.css'):
            (assets / name).write_text('fixture-' + name)
            handler = self.handler('/' + name)
            handler.dispatch()
            self.assertEqual(handler.status, 200, name)
            self.assertEqual(handler.wfile.getvalue(), ('fixture-' + name).encode())
        (assets / 'operations.py').write_text('private implementation')
        for path in ('/operations.py', '/out/corner-pocket/state.json', '/%2e%2e/annotator/operations.py'):
            handler = self.handler(path)
            handler.dispatch()
            self.assertEqual(handler.status, 404, path)

    def test_http_range_and_encoded_traversal(self):
        data = self.root / "data"
        data.mkdir()
        (data / "vod_30min_260815.mp4").write_bytes(b"0123456789")
        for value, expected in (("bytes=2-5", b"2345"), ("bytes=-3", b"789"), ("bytes=8-", b"89")):
            handler = self.handler("/media/vod30/video", {"Range": value})
            handler.do_GET()
            self.assertEqual(handler.status, 206)
            self.assertEqual(handler.wfile.getvalue(), expected)
        handler = self.handler("/media/vod30/video", {"Range": "bytes=20-"})
        handler.do_GET()
        self.assertEqual(handler.status, 416)
        for path in ("/media/vod30/evidence/%2e%2e%2fannotations.json", "/out/scan30/annotations.json", "/api/evil/events"):
            handler = self.handler(path)
            handler.do_GET()
            self.assertEqual(handler.status, 404)

    def test_operations_api_dispatch(self):
        from unittest.mock import Mock
        operations = Mock()
        operations.get.return_value = {"revision": 0, "players": []}
        self.backend._operations = operations
        self.assertEqual(self.backend.get(['api', 'operations'], {}), {"revision": 0, "players": []})
        operations.get.assert_called_once_with()
        handler = self.handler('/api/operations')
        handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertEqual(json.loads(handler.wfile.getvalue()), {"revision": 0, "players": []})

    def test_operations_and_review_share_one_origin(self):
        # Serve real assets through an isolated root, never the production backend.
        assets = Path(__file__).resolve().parents[1] / 'annotator'
        (self.root / 'annotator').symlink_to(assets, target_is_directory=True)
        for path, name in (('/', 'ops.html'), ('/ops.js', 'ops.js'),
                           ('/app.js', 'app.js'), ('/ops.css', 'ops.css'),
                           ('/app.css', 'app.css')):
            with self.subTest(path=path):
                handler = self.handler(path)
                handler.do_GET()
                self.assertEqual(handler.status, 200)
                self.assertEqual(handler.wfile.getvalue(), (assets / name).read_bytes())

    def test_application_responses_are_not_cached(self):
        assets = Path(__file__).resolve().parents[1] / 'annotator'
        (self.root / 'annotator').symlink_to(assets, target_is_directory=True)
        for path in ('/ops.js', '/app.css', '/api/review-template', '/api/live'):
            handler = self.handler(path)
            handler.do_GET()
            self.assertEqual(handler.response_headers.get('Cache-Control'), 'no-store', path)
        handler = self.handler('/api/operations')
        handler.dispatch()
        self.assertEqual(handler.response_headers.get('Cache-Control'), 'no-store')

    def test_legacy_pages_redirect_and_review_template_is_json(self):
        assets = Path(__file__).resolve().parents[1] / 'annotator'
        (self.root / 'annotator').symlink_to(assets, target_is_directory=True)
        for path in ('/app.html', '/ops.html'):
            handler = self.handler(path)
            handler.do_GET()
            self.assertEqual(handler.status, 308)
            self.assertEqual(handler.response_headers['Location'], '/')
        handler = self.handler('/api/review-template')
        handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertEqual(json.loads(handler.wfile.getvalue())['html'], (assets / 'app.html').read_text())

    def test_event_clip_bounded_and_cached(self):
        encoded = []

        def fake_encode(ffmpeg, source, destination, t0, duration):
            encoded.append((round(t0, 3), round(duration, 3)))
            destination.write_bytes(b"fake-mp4")

        self.backend._encode_clip = fake_encode
        self.backend.video_metadata = lambda dataset: dict(dataset=dataset, fps=30.0, frame_count=54206,
                                                           duration=1806.8, width=1280, height=720,
                                                           timestamp_kind='nominal_cfr')
        self.backend.video = lambda dataset: self.root / 'data' / 'vod_30min_260815.mp4'
        clip = self.backend.event_clip('vod30', 30.0, 1.5, 2.5)
        self.assertEqual(encoded, [(28.5, 4.0)])
        self.assertEqual(clip.read_bytes(), b"fake-mp4")
        self.backend.event_clip('vod30', 30.0, 1.5, 2.5)
        self.assertEqual(len(encoded), 1)  # cache hit, no re-encode
        with self.assertRaises(Exception):
            self.backend.event_clip('vod30', 10 ** 6, 1.5, 2.5)
        self.backend.event_clip('vod30', 30.0, 99.0, 2.5)  # clamped, not rejected
        self.assertIn((25.0, 7.5), encoded)

    def test_static_assets_allowlisted(self):
        folder = self.root / "annotator"
        folder.mkdir()
        (folder / 'ops.html').write_text('ops.html')
        for name in ("app.css", "app.js", "ops.css", "ops.js"):
            (folder / name).write_text(name)
            handler = self.handler("/" + name)
            handler.do_GET()
            self.assertEqual(handler.status, 200)
            self.assertEqual(handler.wfile.getvalue(), name.encode())
        handler = self.handler('/')
        handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.wfile.getvalue(), b'ops.html')
        (folder / "secret.txt").write_text("private")
        handler = self.handler("/secret.txt")
        handler.do_GET()
        self.assertEqual(handler.status, 404)

    def test_http_json_errors_and_origin(self):
        for body, headers, expected in ((b"{", {"Content-Length": "1"}, 400), (b"{}", {"Content-Length": "2", "Host": "localhost:8123", "Origin": "https://evil.test"}, 403)):
            handler = self.handler("/api/vod30/annotate", headers, body)
            handler.do_POST()
            self.assertEqual(handler.status, expected)
            self.assertIn("error", json.loads(handler.wfile.getvalue()))

    def _identity_pipeline_stub(self):
        from src.person_pipeline import PersonPipeline
        from unittest.mock import Mock
        pipeline = Mock(spec=PersonPipeline)
        pipeline._tracks = {}
        pipeline.identity = Mock()
        pipeline.identity.clusters.return_value = []
        pipeline.identity.get.return_value = {"player_id": None, "bound_evidence": None}
        self.backend._identity_pipeline = pipeline
        return pipeline

    def test_identity_frame_route_shape_and_re_request(self):
        pipeline = self._identity_pipeline_stub()
        pipeline.process_frame.return_value = {
            "persons": [{"track_id": 1, "bbox": [10, 20, 110, 220], "cluster_id": 3, "player_id": None,
                         "face_sim": None, "bound_evidence": None, "body_embedding": [0.1] * 128}],
            "events": [{"kind": "bind", "player_id": "A", "cluster_id": 3, "similarity": 0.9, "frame_index": 7}]}
        frame = object()
        meta = {"dataset": "vod30", "frame_index": 7, "timestamp_seconds": 0.28, "timestamp_kind": "nominal_cfr"}
        with patch.object(self.backend, "decode_frame", return_value=(frame, meta)) as decode:
            handler = self.handler("/api/identity/frame?dataset=vod30&frame=7")
            handler.do_GET()
            self.assertEqual(handler.status, 200)
            data = json.loads(handler.wfile.getvalue())
            # Re-requesting the same frame just processes again; tracker dedups.
            self.handler("/api/identity/frame?frame=7").do_GET()
        self.assertEqual(decode.call_count, 2)
        decode.assert_called_with("vod30", "7")
        self.assertEqual(data["frame_index"], 7)
        self.assertEqual(data["timestamp_seconds"], 0.28)
        self.assertEqual(data["timestamp_kind"], "nominal_cfr")
        # Internal fields (body_embedding) are stripped from persons.
        self.assertEqual(data["persons"], [{"track_id": 1, "bbox": [10, 20, 110, 220], "cluster_id": 3,
                                            "player_id": None, "face_sim": None, "bound_evidence": None}])
        self.assertEqual(data["events"], [{"kind": "bind", "player_id": "A", "cluster_id": 3,
                                           "similarity": 0.9, "frame_index": 7}])
        self.assertEqual(pipeline.process_frame.call_count, 2)
        pipeline.process_frame.assert_called_with(frame, 7, 0.28)

    def test_identity_enroll_decodes_base64_and_rejects_bad_input(self):
        import base64
        from types import SimpleNamespace
        from unittest.mock import Mock
        pipeline = self._identity_pipeline_stub()
        pipeline.enroll_face.return_value = 2
        pixels = Mock(name="image")
        cv = SimpleNamespace(imdecode=Mock(return_value=pixels), IMREAD_COLOR=1)
        encoded = base64.b64encode(b"png-bytes").decode()
        with patch.dict("sys.modules", {"cv2": cv}):
            result = self.backend.post(["api", "identity", "enroll"], {"player_id": "A", "image_base64": encoded})
            self.assertEqual(result, {"enrolled": 2, "player_id": "A"})
            pipeline.enroll_face.assert_called_once_with("A", pixels)
            for payload in ({"player_id": "A"},
                            {"image_base64": encoded},
                            {"player_id": "A", "image_base64": "!!not-b64!!"},
                            {"player_id": "A", "image_base64": base64.b64encode(b"x" * (8 * 1024 * 1024 + 1)).decode()}):
                with self.subTest(payload=payload):
                    with self.assertRaises(APIError) as error:
                        self.backend.post(["api", "identity", "enroll"], payload)
                    self.assertEqual(error.exception.status, 400)
            cv.imdecode.assert_called_once()  # bad payloads never reach imdecode

    def test_identity_seed_and_status(self):
        pipeline = self._identity_pipeline_stub()
        pipeline._tracks = {1: {}, 2: {}}
        identity = pipeline.identity
        identity.clusters.return_value = [3, 4]
        identity.get.side_effect = lambda c: {"player_id": "B" if c == 3 else None, "bound_evidence": "x"}
        self.assertEqual(self.backend.get(["api", "identity", "status"], {}),
                         {"tracks": 2, "clusters": 2, "bound": [{"cluster_id": 3, "player_id": "B"}]})
        self.assertEqual(self.backend.post(["api", "identity", "seed"], {"cluster_id": 4, "player_id": "A"}),
                         {"seeded": True})
        pipeline.explicit_seed.assert_called_once_with(4, "A")
        with self.assertRaises(APIError):
            self.backend.post(["api", "identity", "seed"], {"cluster_id": "3", "player_id": "A"})
        with self.assertRaises(APIError):
            self.backend.post(["api", "identity", "seed"], {"cluster_id": True, "player_id": "A"})

    def test_identity_unbind_clears_the_binding_and_keeps_the_samples(self):
        # Clear in the review rail is a real undo of "Save": the cluster keeps its
        # evidence, the player id goes back to None so face/body may match again.
        pipeline = self._identity_pipeline_stub()
        self.assertEqual(self.backend.post(["api", "identity", "unbind"], {"cluster_id": 3}), {"unbound": True, "cluster_id": 3})
        pipeline.identity.explicit_assign.assert_called_once_with(3, None, reason="unbind")
        for payload in ({"cluster_id": "3"}, {"cluster_id": True}, {}):
            with self.assertRaises(APIError):
                self.backend.post(["api", "identity", "unbind"], payload)

    def test_identity_unbind_is_origin_protected(self):
        pipeline = self._identity_pipeline_stub()
        body = json.dumps({"cluster_id": 3}).encode()
        headers = {"Host": "127.0.0.1:8130", "Origin": "https://evil.test", "Content-Length": str(len(body))}
        handler = self.handler("/api/identity/unbind", headers, body)
        handler.dispatch(post=True)
        self.assertEqual(handler.status, 403)
        self.assertFalse(pipeline.identity.explicit_assign.called)

    def test_identity_http_post_is_origin_protected(self):
        pipeline = self._identity_pipeline_stub()
        body = json.dumps({"cluster_id": 3, "player_id": "A"}).encode()
        headers = {"Host": "127.0.0.1:8130", "Origin": "http://127.0.0.1:8130", "Content-Length": str(len(body))}
        handler = self.handler("/api/identity/seed", headers, body)
        handler.dispatch(post=True)
        self.assertEqual(handler.status, 200)
        self.assertEqual(json.loads(handler.wfile.getvalue()), {"seeded": True})
        pipeline.explicit_seed.assert_called_once_with(3, "A")
        handler = self.handler("/api/identity/seed", dict(headers, Origin="https://evil.test"), body)
        handler.dispatch(post=True)
        self.assertEqual(handler.status, 403)
        pipeline.explicit_seed.assert_called_once()

    def test_on_the_spot_inference_stores_nothing(self):
        """Run inference on a frame: the result is in the response and nowhere else.

        The endpoint used to atomic_save frame_results/<frame>/inference.json, so
        every look wrote a file. Nothing under frame_results/ may appear or change
        - no file, no directory - and the frame-result read still reports no
        inference for that frame afterwards.
        """
        frames_root = self.out / 'scan30' / 'frame_results'
        before = sorted(str(p.relative_to(frames_root)) for p in frames_root.rglob('*')) if frames_root.exists() else []
        result = {'boxes': [{'label': 'ball', 'bbox': [10, 20, 30, 40], 'score': 0.8}], 'table_polygon': None}
        meta = {'dataset': 'vod30', 'frame_index': 12345, 'timestamp_seconds': 1.0,
                'timestamp_kind': 'nominal_cfr', 'width': 1280, 'height': 720}
        with patch.object(self.backend, 'frame_metadata', return_value=meta), \
             patch.object(self.backend, 'decode_frame', return_value=(object(), meta)), \
             patch('src.frame_inference.infer_frame', return_value=dict(result)), \
             patch('annotator.unified_server.atomic_save') as save:
            job = self.backend.start_inference({'dataset': 'vod30', 'frame_index': 12345, 'detectors': ['balls']})
            self.assertIn(job['status'], ('running', 'completed'), 'the job started')
            deadline = time.time() + 10
            while self.backend.inference_jobs['vod30']['status'] == 'running' and time.time() < deadline:
                time.sleep(0.01)
        done = self.backend.inference_jobs['vod30']
        self.assertEqual(done['status'], 'completed', done)
        self.assertEqual(done['result']['source'], 'inferred')
        self.assertEqual(done['result']['boxes'], result['boxes'])
        self.assertFalse(save.called, 'nothing is written for an inference run')
        after = sorted(str(p.relative_to(frames_root)) for p in frames_root.rglob('*')) if frames_root.exists() else []
        self.assertEqual(after, before, 'no file and no directory appeared under frame_results/')
        self.assertNotIn('12345', ' '.join(after))
        with patch.object(self.backend, 'frame_metadata', return_value=meta):
            self.assertIsNone(self.backend.frame_result('vod30', 12345)['inference'])

    def test_a_stored_inference_file_is_marked_as_an_earlier_run(self):
        """Pre-existing files stay readable evidence, labelled as what they are."""
        path = self.out / 'scan30' / 'frame_results' / '2100' / 'inference.json'
        atomic_save(path, {'boxes': [{'label': 'ball', 'bbox': [1, 2, 3, 4]}], 'table_polygon': None,
                           'source': 'inferred', 'saved_at': '2026-09-23T20:58:05+00:00'})
        meta = {'dataset': 'vod30', 'frame_index': 2100, 'timestamp_seconds': 70.0,
                'timestamp_kind': 'nominal_cfr', 'width': 1280, 'height': 720}
        with patch.object(self.backend, 'frame_metadata', return_value=meta):
            payload = self.backend.frame_result('vod30', 2100)
        self.assertTrue(payload['inference']['stored_inference'], 'a file read is marked as stored')
        self.assertEqual(payload['inference']['saved_at'], '2026-09-23T20:58:05+00:00')
        self.assertEqual(payload['inference']['boxes'], [{'label': 'ball', 'bbox': [1, 2, 3, 4]}])
        # A frame with no file keeps reporting none: the read never invents one.
        with patch.object(self.backend, 'frame_metadata', return_value=dict(meta, frame_index=2101)):
            self.assertIsNone(self.backend.frame_result('vod30', 2101)['inference'])

    def test_enrol_preview_prefers_the_stored_cluster_and_says_which_evidence(self):
        """A cluster id takes the fast path; the payload names the evidence level."""
        from src.enroll_from_tracklet import Candidate, Enrollment, Selection
        calls = {}
        candidate = Candidate(frame_index=2010, t=67.0, bbox=[10, 10, 30, 30], person_bbox=[600, 130, 720, 320],
                              det_score=0.7977, eye_px=12.7, embedding=np.zeros(8, np.float32))
        enrollment = Enrollment(track_id=6, player_id='p', player_name='x', crops=[candidate],
                                store_json={}, roster_json=None,
                                evidence={'kept': 1, 'usable_faces': 1, 'evidence_source': 'cluster_face',
                                          'cross_checked': False, 'purity_probes': 0, 'purity': None,
                                          'kept_frame_indices': [2010]})
        selection = Selection(dataset='vod30', frame_index=2010, track_id=6, selection_iou=1.0, frames_seen=1,
                              enrollment=enrollment, source='cluster_face', frames_scanned=0)
        def fake_cluster(root, cluster_id, **kwargs):
            calls['cluster'] = (cluster_id, kwargs.get('dataset'), kwargs.get('fallback'))
            return selection
        with patch('src.enroll_from_tracklet.plan_for_cluster', side_effect=fake_cluster), \
             patch('src.enroll_from_tracklet.crop_jpeg', return_value=b'jpeg'), \
             patch('src.enroll_from_tracklet.plan_for_selection') as window:
            payload = self.backend.enroll_preview({'dataset': 'vod30', 'frame_index': 2040,
                                                   'bbox': [600, 130, 720, 320], 'cluster_id': 7})
        self.assertTrue(payload['ok'])
        self.assertEqual(calls['cluster'], (7, 'vod30', True), 'the cluster id takes the fast path, with a window-scan fallback')
        self.assertFalse(window.called, 'the scan is not run when the stored evidence answers')
        self.assertEqual(payload['evidence'], {'source': 'cluster_face', 'stored_face': True,
                                               'cross_checked': False, 'crops': 1, 'frames_scanned': 0})
        self.assertIn(payload['token'], self.backend._enroll_plans, 'the plan is held under the token the operator saw')

    def test_enrol_confirm_refuses_a_token_mismatch_without_writing(self):
        """The module re-checks the token against the recording; a mismatch is a
        refusal, not a silent enrolment, and nothing is promoted."""
        from src.enroll_from_tracklet import EnrollmentTokenError
        plan = Mock()
        plan.dataset = 'vod30'
        self.backend._enroll_plans['tok'] = plan
        with patch('src.enroll_from_tracklet.confirm_enrollment',
                   side_effect=EnrollmentTokenError('token_mismatch', {'track_id': 6})), \
             patch.object(self.backend, '_promote_enrollment') as promote:
            result = self.backend.enroll_confirm({'token': 'tok', 'player_name': 'Ana'})
        self.assertEqual(result['ok'], False)
        self.assertEqual(result['reason'], 'token_mismatch')
        self.assertIn('not the ones you were shown', result['message'])
        self.assertFalse(promote.called, 'a refused confirm writes nothing')
        self.assertIn('tok', self.backend._enroll_plans, 'and the plan stays available for another look')
        # An unknown token is refused as expired rather than enrolling anything.
        self.assertEqual(self.backend.enroll_confirm({'token': 'gone', 'player_name': 'Ana'})['reason'], 'preview_expired')

    def test_identity_frame_read_leaves_the_index_file_untouched(self):
        """GET /api/identity/frame runs the tracker over one frame. That is
        observation: the index file used to be rewritten by every register()
        (payload grew by ~10 kB per frame request in the fixture), which made
        read-only verification impossible. The write belongs to the binding."""
        from src.person_identity import IdentityIndex
        path = self.out / 'identity' / 'clusters.json'
        index = IdentityIndex(path)
        index.register(1, [1.0] * 128, frame_index=1)   # memory only
        index.explicit_assign(1, 'playerZ')            # the durable change writes
        before = file_stamp(path)
        pipeline = Mock()
        pipeline.identity = index
        pipeline.process_frame.side_effect = lambda frame, frame_index, timestamp: (
            index.update([{'track_id': 2, 'body_embedding': [1.0] * 128, 'frame_index': frame_index}]),
            {'persons': [], 'events': []})[1]
        self.backend._identity_pipeline = pipeline
        meta = {'dataset': 'vod30', 'frame_index': 7, 'timestamp_seconds': 0.28, 'timestamp_kind': 'nominal_cfr'}
        with patch.object(self.backend, 'decode_frame', return_value=(object(), meta)):
            handler = self.handler('/api/identity/frame?dataset=vod30&frame=7')
            handler.do_GET()
            self.assertEqual(handler.status, 200)
            self.assertEqual(json.loads(handler.wfile.getvalue())['frame_index'], 7)
        self.assertEqual(file_stamp(path), before, 'a read must not rewrite the identity index')
        # GET /api/vod30/tracks, the read that was measured: it never touched the
        # index, and it must keep not touching it.
        self.handler('/api/vod30/tracks?win=68-94&t=70').do_GET()
        self.assertEqual(file_stamp(path), before, 'the tracks read leaves the index alone')
        # The mutation still persists where it happens: cluster 2 was opened by
        # the frame read above and is still unbound.
        self.assertTrue(index.bind_face(2, 'playerY', 0.99), 'an unbound cluster takes the face match')
        self.assertNotEqual(file_stamp(path), before, 'a binding writes at the binding')

    def test_identity_routes_503_when_models_missing(self):
        from unittest.mock import Mock
        factory = Mock(side_effect=RuntimeError("yolov8n.pt missing"))
        with patch("src.person_pipeline.PersonPipeline", factory):
            for _ in range(2):
                handler = self.handler("/api/identity/status")
                handler.do_GET()
                self.assertEqual(handler.status, 503)
                self.assertIn("yolov8n.pt missing", json.loads(handler.wfile.getvalue())["error"])
        self.assertEqual(factory.call_count, 1)  # failure cached: no model retry loop


class UnifiedViewTests(unittest.TestCase):
    """GET /api/unified: one overlay payload per frozen frame, no model loads."""
    FAKE_META = {"dataset": "vod30", "frame_index": 150, "timestamp_seconds": 5.0,
                 "timestamp_kind": "nominal_cfr", "width": 1280, "height": 720}
    # Detection runs on a 2x-downscaled copy (640x360): quad + balls come back
    # in that space and the endpoint must scale them to full-res pixels.
    FAKE_TABLE = {"corners": np.array([[100, 80], [540, 76], [540, 280], [100, 284]], np.float32),
                  "mask": np.ones((360, 640), np.uint8)}
    FAKE_BALLS = [{"cx": 320.0, "cy": 180.0, "r": 7.0, "color": "red", "area": 100.0, "circularity": 0.9}]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = Backend(self.root)
        # /api/unified asks the identity seam for persons. This class is about
        # payload geometry (table, balls, pockets, events, LRU) and promises "no
        # model loads" — but with the real seam, `_unified_persons` built
        # PersonPipeline on this temp root, whose root/yolov8n.pt does not exist,
        # so ultralytics DOWNLOADED yolov8n.pt from GitHub inside the suite: once
        # per test, ~6 MB, and the whole suite stopped being offline-capable.
        # A stub that reports no persons keeps every payload identical (the real
        # detector only ever saw a zero frame) without touching the network.
        # The seam itself stays covered by
        # test_identity_persons_project_only_documented_fields,
        # test_identity_degrades_to_empty_persons_with_error_note and
        # test_unified_read_does_not_write_the_identity_index, which each inject
        # their own pipeline (src/frame_inference.py disables downloads the same
        # way: local weights or RuntimeError).
        stub = Mock()
        stub.process_frame.side_effect = lambda frame, frame_index, timestamp: {
            "persons": [], "events": []}
        self.backend._identity_pipeline = stub
        scan = self.root / "out" / "scan30"
        scan.mkdir(parents=True)
        (scan / "events.json").write_text(json.dumps([
            {"id": 1, "t": 5.5, "type": "pot", "nearest_pocket": "foot-right (124mm)"},
            {"id": 2, "t": 30.0, "type": "shot"},
            {"id": 3, "t": 7.5, "type": "pot", "nearest_pocket": "head-left (10mm)"},
        ]))

    def patch_pipeline(self, table=FAKE_TABLE, balls=FAKE_BALLS):
        frame = np.zeros((720, 1280, 3), np.uint8)
        for target, attribute, replacement in [
            (Backend, "video_metadata", lambda *a, **k: {"fps": 30.0, "frame_count": 330, "width": 1280, "height": 720}),
            (Backend, "decode_frame", lambda *a, **k: (frame, dict(self.FAKE_META))),
            ("src.table_detect.detect_table", None, table),
            ("src.ball_detect.detect_ball_candidates", None, balls),
        ]:
            effect = ({"side_effect": replacement} if callable(replacement)
                      else {"return_value": replacement})
            patcher = (patch.object(target, attribute, **effect) if attribute
                       else patch(target, **effect))
            patcher.start()
            self.addCleanup(patcher.stop)

    def payload(self, route=False):
        self.patch_pipeline()
        if route:
            return self.backend.get(["api", "unified"], {"dataset": ["vod30"], "frame": ["150"]})
        return self.backend.unified("vod30", 150)

    def test_unified_read_does_not_write_the_identity_index(self):
        """The people overlay runs the same tracker seam as /api/identity/frame.
        Drawing a frame is a read: it must leave out/identity/clusters.json
        byte-for-byte alone (it used to rewrite it on every frame)."""
        from src.person_identity import IdentityIndex
        self.patch_pipeline()
        path = self.root / 'out' / 'identity' / 'clusters.json'
        index = IdentityIndex(path)
        index.register(1, [1.0] * 128, frame_index=1)   # memory only
        index.explicit_assign(1, 'playerZ')            # the durable change writes
        before = file_stamp(path)
        persons = [{'track_id': 2, 'bbox': [10, 20, 110, 220], 'cluster_id': 2,
                    'player_id': None, 'face_sim': None, 'bound_evidence': None}]
        pipeline = Mock()
        pipeline.identity = index
        pipeline.process_frame.side_effect = lambda frame, frame_index, timestamp: (
            index.update([{'track_id': 2, 'body_embedding': [1.0] * 128, 'frame_index': frame_index}]),
            {'persons': persons, 'events': []})[1]
        self.backend._identity_pipeline = pipeline
        data = self.backend.get(['api', 'unified'], {'dataset': ['vod30'], 'frame': ['150']})
        self.assertEqual(data['persons'], persons, 'the overlay read really ran the identity seam')
        self.assertIsNone(data['persons_error'])
        self.assertEqual(file_stamp(path), before, 'reading a frame must not rewrite the identity index')

    def test_payload_shape_scales_detection_back_to_full_res(self):
        data = self.payload()
        self.assertEqual(sorted(data), ["balls", "events", "frame_index", "height", "persons",
                                        "persons_error", "pockets", "table_corners", "table_quad",
                                        "timestamp_kind", "timestamp_seconds", "width"])
        # Additive: what the detector decided (no hand anchors in this fixture root, so
        # the naive detector ran) - the viewer renders the reason from it.
        self.assertEqual(data["table_quad"]["state"], "no_seed")
        self.assertIsNone(data["table_quad"]["seed_file"])
        self.assertEqual(data["frame_index"], 150)
        self.assertEqual(data["timestamp_seconds"], 5.0)
        self.assertEqual((data["width"], data["height"]), (1280, 720))
        self.assertEqual(data["table_corners"],
                         [[200.0, 160.0], [1080.0, 152.0], [1080.0, 560.0], [200.0, 568.0]])
        self.assertEqual(data["balls"], [{"cx": 640.0, "cy": 360.0, "r": 14.0, "color": "red"}])

    def test_pockets_via_inverse_homography_land_on_table_corners(self):
        data = self.payload()
        self.assertEqual(len(data["pockets"]), 6)
        by_name = {p["name"]: p for p in data["pockets"]}
        self.assertEqual(set(by_name), {"head-left", "head-right", "foot-right", "foot-left",
                                        "left-side", "right-side"})
        for pocket, corner in zip(["head-left", "head-right", "foot-right", "foot-left"],
                                  data["table_corners"]):
            self.assertAlmostEqual(by_name[pocket]["cx"], corner[0], delta=1.5)
            self.assertAlmostEqual(by_name[pocket]["cy"], corner[1], delta=1.5)
        self.assertAlmostEqual(by_name["left-side"]["cy"],
                               (by_name["head-left"]["cy"] + by_name["foot-left"]["cy"]) / 2, delta=1.5)

    def test_events_window_is_three_seconds_around_frame_time(self):
        data = self.payload()
        self.assertEqual([e["id"] for e in data["events"]], [1, 3],
                         "5.5s and 8.4s are within ±3s of 5.0s, 30s is not")

    def test_events_window_carries_the_same_additive_pixel_geometry(self):
        # The stage's ±3 s event window draws the same projected geometry the cue
        # list carries, so a pot pulse and its cue cannot disagree.
        scan = self.root / "out" / "scan30"
        atomic_save(scan / "corners.json",
                    {"corners": [[100, 100], [1100, 120], [1120, 620], [90, 600]]})
        events = json.loads((scan / "events.json").read_text())
        events[0] = {"id": 1, "t": 5.5, "type": "pot", "last_mm": [5.0, 1270.0],
                     "nearest_pocket": "left-side (5mm)"}
        atomic_save(scan / "events.json", events)
        window = [e for e in self.payload()["events"] if e["id"] == 1]
        self.assertEqual(window[0]["pocket_name"], "left-side")
        self.assertTrue(window[0]["last_px"] and 0 <= window[0]["last_px"][0] <= 1280)

    def test_identity_degrades_to_empty_persons_with_error_note(self):
        def broken(self):
            raise APIError("identity models unavailable: no weights", 503)
        with patch.object(Backend, "identity_pipeline", broken):
            data = self.payload()
        self.assertEqual(data["persons"], [])
        self.assertIn("identity models unavailable", data["persons_error"])

    def test_identity_persons_project_only_documented_fields(self):
        pipeline = type("FakePipeline", (), {})()
        pipeline.process_frame = lambda frame, index, t: {"persons": [
            {"track_id": 3, "bbox": [1, 2, 3, 4], "cluster_id": 9, "player_id": "A",
             "face_sim": 0.5, "bound_evidence": "x", "secret": "drop me"}],
            "events": [{"kind": "bind"}]}
        with patch.object(Backend, "identity_pipeline", lambda self: pipeline):
            data = self.payload()
        self.assertEqual(data["persons_error"], None)
        self.assertEqual(data["persons"], [{"track_id": 3, "bbox": [1, 2, 3, 4], "cluster_id": 9,
                                            "player_id": "A", "face_sim": 0.5, "bound_evidence": "x"}])

    def test_missing_table_yields_no_balls_and_no_pockets(self):
        self.patch_pipeline(table={"corners": None, "mask": None}, balls=[])
        data = self.backend.unified("vod30", 150)
        self.assertEqual(data["table_corners"], None)
        self.assertEqual(data["balls"], [])
        self.assertEqual(data["pockets"], [])

    def test_route_dispatch_and_validation(self):
        data = self.payload(route=True)
        self.assertEqual(data["frame_index"], 150)
        with self.assertRaises(APIError) as ctx:
            self.backend.unified("vod30", 99999)
        self.assertEqual(ctx.exception.status, 400)
        with self.assertRaises(APIError) as ctx:
            self.backend.unified("nope", 0)
        self.assertEqual(ctx.exception.status, 404)

    def test_detection_is_cached_per_frame_with_lru_eviction(self):
        calls = []
        def counting_table(bgr):
            calls.append(1)
            return self.FAKE_TABLE
        self.patch_pipeline(table=counting_table)
        self.backend.unified("vod30", 150)
        self.backend.unified("vod30", 150)
        self.assertEqual(len(calls), 1, "second request must hit the (dataset, frame) cache")
        for frame in range(30):
            self.backend.unified("vod30", frame)  # 30 distinct misses evict 150
        self.assertEqual(len(calls), 31)
        self.assertNotIn(("vod30", 150), self.backend._unified_cache)
        self.backend.unified("vod30", 10)  # still cached: no new detection
        self.assertEqual(len(calls), 31)

    def test_lru_refreshes_recency(self):
        self.patch_pipeline()
        self.backend.unified("vod30", 1)
        self.backend.unified("vod30", 2)
        self.backend.unified("vod30", 1)
        for frame in range(3, 26):
            self.backend.unified("vod30", frame)
        self.assertIn(("vod30", 1), self.backend._unified_cache)
        self.assertNotIn(("vod30", 2), self.backend._unified_cache)


if __name__ == "__main__":
    unittest.main()
