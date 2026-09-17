import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from annotator.live_processing import LiveProcessor


class Capture:
    def __init__(self, count=5, fps=200, opened=True):
        self.count, self.fps, self.opened = count, fps, opened
        self.index = 0
        self.released = False

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return self.fps

    def read(self):
        if self.index >= self.count:
            return False, None
        self.index += 1
        return True, np.full((16, 16, 3), self.index, dtype=np.uint8)

    def release(self):
        self.released = True


def infer(frame, detectors, root):
    return {'pixel': int(frame[0, 0, 0])}


class LiveProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        (self.root / 'data/vod_30min_260815.mp4').touch()
        state = self.root / 'out/corner-pocket/state.json'
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({'sources': [dict(id='saved', kind='channel', channel='pool',
                                                     url='https://www.twitch.tv/pool')]}))
        self.source = dict(kind='dataset', dataset='vod30')

    def processor(self, **kwargs):
        kwargs.setdefault('infer', infer)
        processor = LiveProcessor(self.root, **kwargs)
        self.addCleanup(processor.stop)
        return processor

    def wait_for(self, processor, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status = processor.status()
            if predicate(status):
                return status
            time.sleep(.002)
        self.fail('Timed out: ' + repr(processor.status()))

    def finished(self, processor):
        return self.wait_for(processor, lambda s: not s['decoder_alive'] and not s['worker_alive'])

    def test_large_frames_are_scaled_with_paired_coordinates(self):
        capture = Capture(count=1)
        original = capture.read
        def read():
            ok, frame = original()
            return (ok, np.zeros((1080, 1920, 3), dtype=np.uint8)) if ok else (ok, frame)
        capture.read = read
        processor = self.processor(capture_factory=lambda media: capture)
        processor.start(self.source)
        self.finished(processor)
        jpeg, metadata = processor.latest_jpeg()
        self.assertEqual((metadata['width'], metadata['height']), (960, 540))
        self.assertEqual((metadata['source_width'], metadata['source_height']), (1920, 1080))
        self.assertEqual(cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR).shape[:2], (540, 960))

    def test_invalid_frame_shape_is_rejected_before_inference(self):
        capture = Capture(count=1)
        capture.read = lambda: (True, np.zeros((1, 3841, 3), dtype=np.uint8))
        processor = self.processor(capture_factory=lambda media: capture)
        processor.start(self.source)
        status = self.finished(processor)
        self.assertEqual(status['state'], 'error')
        self.assertEqual(status['frames_processed'], 0)
        self.assertIn('3840', status['error'])
        self.assertTrue(capture.released)

    def test_lifecycle_eos_pairing_and_restart(self):
        captures = []
        def factory(media):
            capture = Capture()
            captures.append(capture)
            return capture
        processor = self.processor(capture_factory=factory)
        self.assertEqual(processor.status()['state'], 'idle')
        self.assertIsNone(processor.latest_jpeg())
        processor.start(self.source)
        status = self.finished(processor)
        self.assertEqual(status['state'], 'eos')
        self.assertEqual(status['frames_received'], 5)
        self.assertEqual(status['frames_processed'] + status['frames_skipped'], 5)
        jpeg, metadata = processor.latest_jpeg()
        self.assertEqual(metadata['seq'], 5)
        self.assertEqual((metadata['width'], metadata['height']), (16, 16))
        self.assertGreaterEqual(metadata['receive_to_result_ms'], metadata['receive_to_process_ms'])
        self.assertGreaterEqual(metadata['receive_to_result_ms'], metadata['inference_ms'])
        self.assertEqual(metadata['detections']['pixel'], 5)
        self.assertEqual(int(cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)[0, 0, 0]), 5)
        self.assertIsNone(status['upstream_delay_ms'])
        self.assertGreaterEqual(status['frame_age_ms'], 0)
        self.assertTrue(captures[0].released)
        metadata['detections']['pixel'] = -1
        self.assertEqual(processor.latest_jpeg()[1]['detections']['pixel'], 5)
        self.assertEqual(processor.stop()['state'], 'stopped')
        self.assertEqual(processor.start(self.source)['generation'], 2)
        self.finished(processor)

    def test_latest_only_backpressure(self):
        entered, unblock = threading.Event(), threading.Event()
        self.addCleanup(unblock.set)
        def slow(frame, detectors, root):
            entered.set()
            unblock.wait(2)
            return infer(frame, detectors, root)
        processor = self.processor(capture_factory=lambda _: Capture(count=30), infer=slow)
        processor.start(self.source, ['table'])
        self.assertTrue(entered.wait(1))
        self.wait_for(processor, lambda s: not s['decoder_alive'])
        self.assertGreater(processor.status()['frames_skipped'], 20)
        unblock.set()
        status = self.finished(processor)
        self.assertEqual(status['frames_processed'], 2)
        self.assertEqual(status['latest']['seq'], 30)
        self.assertEqual(status['frames_processed'] + status['frames_skipped'], 30)

    def test_replay_paces_and_stop_interrupts_wait(self):
        processor = self.processor(capture_factory=lambda _: Capture(count=10, fps=2))
        processor.start(self.source)
        self.wait_for(processor, lambda s: s['frames_processed'] == 1)
        time.sleep(.06)
        self.assertEqual(processor.status()['frames_received'], 1)
        started = time.monotonic()
        self.assertEqual(processor.stop()['state'], 'stopped')
        self.assertLess(time.monotonic() - started, .3)

    def test_blocked_capture_prevents_overlap_and_stale_publish(self):
        entered, unblock = threading.Event(), threading.Event()
        class BlockingCapture(Capture):
            def read(self):
                entered.set()
                unblock.wait(2)
                return super().read()
        capture = BlockingCapture()
        processor = self.processor(capture_factory=lambda _: capture, stop_timeout=.02)
        self.addCleanup(unblock.set)
        processor.start(self.source)
        self.assertTrue(entered.wait(1))
        started = time.monotonic()
        self.assertEqual(processor.stop()['state'], 'stopping')
        self.assertLess(time.monotonic() - started, .2)
        with self.assertRaises(RuntimeError):
            processor.start(self.source)
        unblock.set()
        self.finished(processor)
        self.assertTrue(capture.released)
        self.assertIsNone(processor.latest_jpeg())
        self.assertEqual(processor.start(self.source)['generation'], 2)
        self.finished(processor)

    def test_blocked_inference_prevents_restart_and_late_output(self):
        entered, unblock = threading.Event(), threading.Event()
        def blocked(*args):
            entered.set()
            unblock.wait(2)
            return {}
        processor = self.processor(capture_factory=lambda _: Capture(1), infer=blocked, stop_timeout=.01)
        self.addCleanup(unblock.set)
        processor.start(self.source)
        self.assertTrue(entered.wait(1))
        self.assertEqual(processor.stop()['state'], 'stopping')
        with self.assertRaises(RuntimeError):
            processor.start(self.source)
        unblock.set()
        self.finished(processor)
        self.assertIsNone(processor.latest_jpeg())

    def test_failures_are_safe(self):
        def failure(*args):
            raise RuntimeError('https://secret.example/?token=private')
        for kwargs in [dict(capture_factory=failure),
                       dict(capture_factory=lambda _: Capture(opened=False)),
                       dict(capture_factory=lambda _: Capture(), infer=failure),
                       dict(resolver=failure)]:
            with self.subTest(kwargs=kwargs):
                processor = self.processor(**kwargs)
                processor.start(dict(kind='twitch', source_id='saved') if 'resolver' in kwargs else self.source)
                status = self.finished(processor)
                self.assertEqual(status['state'], 'error')
                self.assertNotIn('private', json.dumps(status))
                self.assertNotIn('secret.example', json.dumps(status))

    def test_public_twitch_unavailability_is_actionable(self):
        from annotator.twitch_source import TwitchSourceError
        processor = self.processor()
        with patch('annotator.twitch_source.resolve_twitch', side_effect=TwitchSourceError('Twitch channel is offline or has no public playable stream')):
            processor.start(dict(kind='twitch', source_id='saved'))
            status = self.finished(processor)
        self.assertEqual(status['state'], 'error')
        self.assertIn('offline', status['error'])
        self.assertNotIn('Streamlink', status['error'])

    def test_default_capture_configures_ffmpeg_timeouts(self):
        from annotator.live_processing import _capture
        with patch.object(cv2, 'VideoCapture', return_value=Capture()) as constructor:
            _capture('trusted-media')
        constructor.assert_called_once_with('trusted-media', cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000])

    def test_capture_read_and_release_failures_are_sanitized(self):
        class BrokenCapture(Capture):
            def read(self):
                raise RuntimeError('token=secret')
            def release(self):
                self.released = True
                raise RuntimeError('token=secret')
        capture = BrokenCapture()
        processor = self.processor(capture_factory=lambda _: capture)
        processor.start(self.source)
        status = self.finished(processor)
        self.assertTrue(capture.released)
        self.assertEqual(status['state'], 'error')
        self.assertNotIn('secret', json.dumps(status))

    def test_saved_twitch_resolution_and_stream_end(self):
        seen = []
        def resolver(url):
            seen.append(url)
            return 'https://private.example/?token=secret'
        def factory(media):
            self.assertEqual(media, 'https://private.example/?token=secret')
            return Capture(2)
        processor = self.processor(resolver=resolver, capture_factory=factory)
        processor.start(dict(kind='twitch', source_id='saved'))
        status = self.finished(processor)
        self.assertEqual(seen, ['https://www.twitch.tv/pool'])
        self.assertEqual(status['state'], 'error')
        self.assertIn('stream ended', status['error'])
        self.assertNotIn('secret', json.dumps(status))

    def test_validation_and_symlink_escape(self):
        processor = self.processor()
        for source in [dict(kind='twitch', url='http://127.0.0.1'),
                       dict(kind='twitch', source_id='unknown'),
                       dict(kind='dataset', dataset='../private'),
                       dict(kind='dataset', dataset=[]),
                       dict(kind='dataset', dataset='vod30', url='https://example.com')]:
            with self.assertRaises(ValueError):
                processor.start(source)
        for detectors in [[], ['balls'], ['unknown'], 'table', [None]]:
            with self.assertRaises(ValueError):
                processor.start(self.source, detectors)
        path = self.root / 'data/vod_30min_260815.mp4'
        path.unlink()
        path.symlink_to(self.root / 'out/corner-pocket/state.json')
        with self.assertRaises(ValueError):
            processor.start(self.source)

    def test_injected_clock_metrics(self):
        processor = self.processor(capture_factory=lambda _: Capture(1), clock=lambda: 100., wall_clock=lambda: 1234.)
        processor.start(self.source)
        status = self.finished(processor)
        self.assertEqual(status['last_received_at'], 1234.)
        self.assertEqual(status['latest']['inference_ms'], 0)
        self.assertEqual(status['latest']['receive_to_process_ms'], 0)
        self.assertEqual(status['frame_age_ms'], 0)


if __name__ == '__main__':
    unittest.main()
