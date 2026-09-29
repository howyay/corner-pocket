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


def status_finished(status):
    """Both pipeline threads have exited (the source ended or failed)."""
    return not status['decoder_alive'] and not status['worker_alive'] and status['state'] in ('eos', 'error')


class LiveDetectorRequestTests(unittest.TestCase):
    """`ball` is requestable at runtime, and an un-runnable request is refused."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        (self.root / 'data/vod_30min_260815.mp4').touch()
        self.source = dict(kind='dataset', dataset='vod30')

    def weights(self, size=2048):
        path = self.root / 'out/tiny_ball_probe/960x540-scratch.pt'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x' * size)
        return path

    def processor(self, **kwargs):
        kwargs.setdefault('capture_factory', lambda _: Capture(count=0))
        kwargs.setdefault('frame_budget_ms', 1000)
        processor = LiveProcessor(self.root, **kwargs)
        self.addCleanup(processor.stop)
        return processor

    def test_ball_is_requested_through_the_normal_start_and_is_in_the_registry(self):
        self.weights()
        processor = self.processor()
        status = processor.start(self.source, ['table', 'person', 'ball'])
        self.assertEqual(status['detectors'], ['table', 'person', 'ball'])
        stages = processor.status()['stages']
        self.assertEqual([stage['name'] for stage in stages], ['table', 'person', 'ball'])
        self.assertEqual(stages[2]['every_n_frames'], 1)       # every frame unless asked

    def test_ball_cadence_is_the_callers_choice(self):
        self.weights()
        processor = self.processor(ball_every_n=3)
        processor.start(self.source, ['ball'])
        self.assertEqual(processor.status()['stages'][0]['every_n_frames'], 3)

    def test_missing_weights_refuse_the_start_and_name_the_path(self):
        processor = self.processor()
        with self.assertRaises(ValueError) as caught:
            processor.start(self.source, ['ball'])
        message = str(caught.exception)
        self.assertIn("'ball'", message)
        self.assertIn('out/tiny_ball_probe/960x540-scratch.pt', message)
        # Refused, not degraded: nothing started and nothing is left half-set.
        status = processor.status()
        self.assertEqual(status['state'], 'idle')
        self.assertEqual(status['detectors'], [])
        self.assertFalse(status['decoder_alive'])
        self.assertFalse(status['worker_alive'])
        self.assertIsNone(processor.latest_jpeg())

    def test_empty_weights_file_is_refused_too(self):
        self.weights(size=0)
        processor = self.processor()
        with self.assertRaises(ValueError) as caught:
            processor.start(self.source, ['ball'])
        self.assertIn('empty', str(caught.exception))

    def test_a_requested_ball_without_a_ball_stage_is_refused(self):
        # The legacy single-detector path builds one 'detect' stage: a caller asking
        # for ball there would get a pipeline that never produces a ball result.
        self.weights()
        processor = self.processor(infer=infer)
        with self.assertRaises(ValueError) as caught:
            processor.start(self.source, ['ball'])
        self.assertIn('no stage', str(caught.exception))
        self.assertEqual(processor.status()['state'], 'idle')

    def test_unknown_detector_names_are_refused(self):
        self.weights()
        for detectors in (['balls'], ['sam3'], ['BALL'], ['table', 'ball', 'balls'], [], 'ball'):
            processor = self.processor()
            with self.assertRaises(ValueError, msg=repr(detectors)):
                processor.start(self.source, detectors)
            self.assertEqual(processor.status()['state'], 'idle', detectors)


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
        # This suite pins supersession, frame shape, pacing and failure hygiene. Its
        # Capture feeds a fake 200 fps source, which would make the derived frame
        # budget 5 ms and turn these cases into budget cases; budget enforcement is
        # pinned by test_live_processing_stages.py, and by the last test below.
        kwargs.setdefault('budget_enforcement', False)
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

    def test_a_stopped_error_is_history_and_a_new_start_clears_it(self):
        """``error`` describes the current session only (ship14: a stopped session's error
        read as "Live start failed" on every fresh page load)."""
        from annotator.twitch_source import TwitchSourceError
        processor = self.processor(wall_clock=lambda: 1790506028.5)
        with patch('annotator.twitch_source.resolve_twitch', side_effect=TwitchSourceError('Twitch channel is offline')):
            processor.start(dict(kind='twitch', source_id='saved'))
            status = self.finished(processor)
        # While the session is in error, the error is current and nothing is history yet.
        self.assertEqual((status['state'], status['last_error']), ('error', None))
        self.assertIn('offline', status['error'])
        status = processor.stop()
        self.assertEqual(status['state'], 'stopped')
        self.assertIsNone(status['error'])
        self.assertIn('offline', status['last_error'])
        self.assertEqual(status['last_error_at'], 1790506028.5)
        # A second stop keeps that history; it never invents or loses one.
        self.assertIn('offline', processor.stop()['last_error'])
        processor = self.processor(capture_factory=lambda media: Capture(count=1))
        processor._last_error, processor._last_error_at = 'earlier', 1.0
        status = processor.start(self.source)
        self.assertEqual((status['error'], status['last_error'], status['last_error_at']), (None, None, None))
        self.finished(processor)

    def test_default_capture_configures_ffmpeg_timeouts(self):
        from annotator.live_processing import _capture
        with patch.object(cv2, 'VideoCapture', return_value=Capture()) as constructor:
            _capture('trusted-media')
        constructor.assert_called_once_with('trusted-media', cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000])
        with patch.object(cv2, 'VideoCapture', return_value=Capture()) as live:
            _capture('live-media', read_timeout_ms=20000)
        live.assert_called_once_with('live-media', cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 20000])

    def test_read_timeout_follows_the_source_kind(self):
        """A live segment gap must not be read as 'the stream ended' (measured 2026-09-26)."""
        with patch('annotator.live_processing._capture', return_value=Capture(count=1)) as opener:
            processor = self.processor(resolver=lambda url: 'https://media.ttvnw.net/live.m3u8')
            processor.start(dict(kind='twitch', source_id='saved'))
            self.finished(processor)
        self.assertEqual(opener.call_args.kwargs, {'read_timeout_ms': 20000})
        with patch('annotator.live_processing._capture', return_value=Capture(count=1)) as opener:
            processor = self.processor()
            processor.start(self.source)
            self.finished(processor)
        self.assertEqual(opener.call_args.kwargs, {'read_timeout_ms': 2000})

    def test_a_subclass_capture_factory_is_honoured_and_an_unknown_kind_is_not_live(self):
        """The decoder opens through ``_capture_factory`` even when none was injected.

        4a9654b let a processor built with ``capture_factory=None`` bypass the attribute and
        call ``_capture`` itself, so a factory installed later (the vod-replay mixin's) was
        silently skipped.  A kind this file does not know is refused, not treated as live.
        """
        processor = self.processor()
        opened = []
        processor._capture_factory = lambda media: opened.append(media) or Capture(count=2)
        with patch('annotator.live_processing._capture') as plain:
            processor.start(self.source)
            status = self.finished(processor)
        plain.assert_not_called()
        self.assertEqual(len(opened), 1)
        self.assertEqual((status['state'], status['frames_received']), ('eos', 2))
        processor._source = dict(kind='future')
        with self.assertRaises(RuntimeError):
            processor._live()

    def test_live_burst_is_published_without_a_notify_storm(self):
        """The decoder may outrun a live source; the worker must not be woken per frame.

        A 200-frame instant burst stands in for ffmpeg draining its buffered segments.  The
        clock is injected and advances a fixed tiny step per call, so how much *clock* time
        the burst covers is a property of the code, not of the machine: under load a real
        clock let the burst span more than one 33 ms frame period and the notify count moved
        with it (0/3 under load ~8 on a clean export of 3b65543).  With a scripted clock the
        count is exact.
        """
        class StepClock:
            """Monotone clock: a fixed step per call, never sleeps, never reads wall time."""

            def __init__(self, start=1000.0, step=1e-7):
                self.value, self.step = start, step

            def __call__(self):
                self.value += self.step
                return self.value

        release = threading.Event()
        self.addCleanup(release.set)

        class BurstThenHold(Capture):
            """200 instant frames, then hold the stream open until the test says go.

            Without the hold, the burst and the end-of-stream failure race the worker, so
            whether anything is published at all is a coin toss - that, not the notify
            count, is what made the original version of this test flaky.
            """

            def read(self):
                if self.index >= self.count:
                    release.wait(5)
                    return False, None
                return super().read()

        processor = self.processor(capture_factory=lambda _: BurstThenHold(count=200),
                                   resolver=lambda url: 'https://media.ttvnw.net/live.m3u8',
                                   clock=StepClock(), wall_clock=StepClock(start=1.7e9))
        notifies = []
        original = processor._condition.notify_all
        processor._condition.notify_all = lambda: (notifies.append(1), original())[1]
        processor.start(dict(kind='twitch', source_id='saved'))
        self.wait_for(processor, lambda status: status['frames_processed'] >= 1)
        release.set()
        status = self.finished(processor)
        self.assertEqual(status['frames_received'], 200)
        # Exactly three wakeups: the one due publish, the end-of-stream failure notification
        # and the done flag.  One per frame would be 200.
        self.assertEqual(len(notifies), 3)
        self.assertLess(len(notifies) * 10, status['frames_received'])
        # While the decoder is held, the worker publishes exactly the one frame it was woken
        # for; *which* sequence it wins is a scheduling race (the burst is still filling the
        # slot when it wakes), so that is not asserted here - the notify count is.
        self.assertEqual(status['frames_processed'], 1)
        self.assertIsNotNone(status['latest'])
        self.assertEqual(status['frames_processed'] + sum(status['drop_reasons'].values()), 200)

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
        # A replay has no upstream to be behind: the delay stays None and says so.
        self.assertIsNone(status['upstream_delay_ms'])
        self.assertIsNone(status['latest']['upstream_delay_ms'])
        self.assertIsNone(status['upstream_clock'])


class UpstreamDelayTests(unittest.TestCase):
    """upstream_delay_ms is computed in-process from the live playlist, or stays None."""

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

    def live_playlist(self, lag_s):
        import datetime
        now = time.time()
        duration, segments = 2.0, 3
        start = now - lag_s - duration - (segments - 1) * duration
        lines = ['#EXTM3U', '#EXT-X-VERSION:3', '#EXT-X-TARGETDURATION:2', '#EXT-X-MEDIA-SEQUENCE:99']
        for index in range(segments):
            stamp = datetime.datetime.fromtimestamp(start + index * duration, datetime.timezone.utc)
            lines += ['#EXT-X-PROGRAM-DATE-TIME:' + stamp.isoformat().replace('+00:00', 'Z'),
                      '#EXTINF:%.3f,' % duration, 'https://cdn.ttvnw.net/seg%d.ts' % index]
        return '\n'.join(lines) + '\n'

    def processor(self, **kwargs):
        kwargs.setdefault('infer', infer)
        kwargs.setdefault('budget_enforcement', False)
        processor = LiveProcessor(self.root, **kwargs)
        self.addCleanup(processor.stop)
        return processor

    def wait_for(self, processor, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = processor.status()
            if predicate(status):
                return status
            time.sleep(.002)
        self.fail('Timed out: ' + repr(processor.status()))

    def test_live_playlist_gives_a_labelled_delay_per_frame(self):
        gate = threading.Event()
        self.addCleanup(gate.set)

        class Gated(Capture):
            """Holds the second frame until the test releases it, so a frame arriving after
            the probe's first reading can be asserted without any timing assumption."""

            def read(self):
                if self.index >= 1 and not gate.is_set():
                    gate.wait(5)
                return super().read()

        with patch('annotator.live_processing._fetch_playlist', return_value=self.live_playlist(1.5)):
            processor = self.processor(capture_factory=lambda _: Gated(count=3, fps=30),
                                       resolver=lambda url: 'https://cdn.ttvnw.net/live.m3u8')
            processor.start(dict(kind='twitch', source_id='saved'))
            status = self.wait_for(processor, lambda s: s['upstream_delay_ms'] is not None)
            self.assertAlmostEqual(status['upstream_delay_ms'], 1500, delta=700)
            self.assertEqual(status['upstream_clock'], 'broadcaster')
            gate.set()
            status = self.wait_for(processor, lambda s: (s['latest'] or {}).get('upstream_delay_ms') is not None)
            self.assertAlmostEqual(status['latest']['upstream_delay_ms'], 1500, delta=700)
            self.assertEqual(status['latest']['upstream_clock'], 'broadcaster')
            status = self.wait_for(processor, lambda s: status_finished(s))
        # A live source that stops delivering is an error here, by design.
        self.assertIn('stream ended', status['error'])

    def test_playlist_without_program_date_time_stays_none(self):
        plain = '#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\nhttps://cdn.ttvnw.net/a.ts\n'
        with patch('annotator.live_processing._fetch_playlist', return_value=plain):
            processor = self.processor(capture_factory=lambda _: Capture(count=6, fps=30),
                                       resolver=lambda url: 'https://cdn.ttvnw.net/live.m3u8')
            processor.start(dict(kind='twitch', source_id='saved'))
            status = self.wait_for(processor, lambda s: status_finished(s))
        self.assertIsNone(status['upstream_delay_ms'])
        self.assertIsNone(status['upstream_clock'])

    def test_unreachable_playlist_stays_none_and_never_invents(self):
        def broken(url):
            raise RuntimeError('unreachable')
        with patch('annotator.live_processing._fetch_playlist', side_effect=broken):
            processor = self.processor(capture_factory=lambda _: Capture(count=6, fps=30),
                                       resolver=lambda url: 'https://cdn.ttvnw.net/live.m3u8')
            processor.start(dict(kind='twitch', source_id='saved'))
            status = self.wait_for(processor, lambda s: status_finished(s))
        self.assertIsNone(status['upstream_delay_ms'])
        self.assertIsNone(status['upstream_clock'])

    def test_dataset_source_never_starts_a_probe(self):
        with patch('annotator.live_processing._fetch_playlist') as fetch:
            processor = self.processor(capture_factory=lambda _: Capture(count=3))
            processor.start(self.source)
            status = self.wait_for(processor, lambda s: status_finished(s))
        self.assertFalse(fetch.called)
        self.assertIsNone(status['upstream_delay_ms'])
        self.assertIsNone(processor._upstream_probe)


if __name__ == '__main__':
    unittest.main()
