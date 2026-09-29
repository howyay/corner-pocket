"""Stage-harness tests: the live loop's drop-and-report behaviour and its metrics.

Harness shape: a synthetic stage stands in for the ball detector that does not
exist yet, the injected capture is a fake source with a chosen frame rate, and
every assertion is about what the pipeline *published*, what it *dropped* and why.
Run: PYTHONPATH=. .venv/bin/python -m unittest tests.test_live_processing_stages
"""
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
from annotator.pipeline_stages import BallStage, Stage, TableStage


class Capture:
    def __init__(self, count=5, fps=30, opened=True):
        self.count, self.fps, self.opened = count, fps, opened
        self.index = 0
        self.released = False

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return self.fps if prop == cv2.CAP_PROP_FPS else self.index

    def read(self):
        if self.index >= self.count:
            return False, None
        self.index += 1
        return True, np.full((32, 32, 3), self.index, dtype=np.uint8)

    def release(self):
        self.released = True


class PositionCapture(Capture):
    """Capture that reports a real media position, like a decoder over a file."""

    def __init__(self, count=3, fps=30, start=0, shape=(32, 32, 3)):
        super().__init__(count=count, fps=fps)
        self.start = start
        self.shape = shape

    def read(self):
        if self.index >= self.count:
            return False, None
        self.index += 1
        return True, np.full(self.shape, self.index, dtype=np.uint8)

    def get(self, prop):
        if prop == cv2.CAP_PROP_POS_FRAMES:
            return self.start + self.index          # position of the *next* frame
        return super().get(prop)


class Sleepy(Stage):
    """Synthetic slow stage: the ball detector's placeholder."""

    def __init__(self, name='ball', delay=0.06, budget_ms=None, calls=None, result=None):
        self.name = name
        self.delay = delay
        self.budget_ms = budget_ms
        self.calls = calls if calls is not None else []
        self.result = {'name': name} if result is None else result

    def process(self, frame, context):
        self.calls.append(self.name)
        if self.delay:
            time.sleep(self.delay)
        return self.result


class Reader(Stage):
    name = 'reader'

    def __init__(self, seen):
        self.seen = seen

    def process(self, frame, context):
        self.seen.append(context.result('first'))
        return {'boxes': [{'label': 'person'}]}


class StubBallStage(BallStage):
    """The real stage with a stub net: one bright pixel at a model-space point.

    No weights and no GPU: the contract under test is the stage's, not the CNN's (the
    net itself is measured by tests/ball_stack_ab.py and the envelope run).  The input
    build still runs for real, on the CPU, because that is part of the stage.
    """

    def __init__(self, root, peak=(480, 270), **kwargs):
        kwargs.setdefault('device', 'cpu')
        super().__init__(root, model=object(), **kwargs)
        self.peak = peak

    def heatmap(self, stack):
        heat = np.zeros((self.size[1], self.size[0]), np.float32)
        heat[int(self.peak[1]), int(self.peak[0])] = 0.9
        return heat


class LiveStageHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        (self.root / 'data/vod_30min_260815.mp4').touch()
        state = self.root / 'out/corner-pocket/state.json'
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({'sources': []}))
        self.source = dict(kind='dataset', dataset='vod30')

    def processor(self, **kwargs):
        kwargs.setdefault('capture_factory', lambda _: Capture())
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

    def finished(self, processor):
        return self.wait_for(processor, lambda s: not s['decoder_alive'] and not s['worker_alive'])

    def assert_partition(self, status):
        """Every received frame is either published or dropped under one reason."""
        self.assertEqual(status['frames_processed'] + sum(status['drop_reasons'].values()),
                         status['frames_received'])
        self.assertEqual(status['frames_skipped'], sum(status['drop_reasons'].values()))
        self.assertEqual(set(status['drop_reasons']), {'no_frame_ready', 'stage_overrun', 'stale'})

    def test_slow_stage_drops_every_frame_and_says_why(self):
        # Four fps keeps the decoder from superseding frames, so the only reason
        # available to the pipeline is the stage overrun itself.
        calls = []
        stage = Sleepy('ball', delay=.06, calls=calls)
        processor = self.processor(capture_factory=lambda _: Capture(count=3, fps=4), stages=[stage],
                                   frame_budget_ms=33.333)
        status = processor.start(self.source)
        self.assertTrue(status['budget_enforcement'])
        self.assertEqual(status['frame_budget_ms'], 33.333)
        status = self.finished(processor)
        self.assertEqual(status['frames_processed'], 0)
        self.assertEqual(status['drop_reasons']['stage_overrun'], 3)
        self.assertEqual(status['drop_reasons']['no_frame_ready'], 0)
        self.assertEqual(status['drop_reasons']['stale'], 0)
        self.assertEqual(status['last_drop']['reason'], 'stage_overrun')
        self.assertEqual(status['last_drop']['stage'], 'ball')
        self.assertGreater(status['last_drop']['ms'], status['last_drop']['budget_ms'])
        self.assertEqual(calls, ['ball'] * 3)  # every stage of a late frame still runs
        self.assertIsNone(processor.latest_jpeg())
        self.assert_partition(status)

    def test_derived_frame_budget_follows_the_source_fps(self):
        # The decoder learns the source rate when the capture opens; until then the
        # processor reports the configured value (None here) rather than guessing.
        processor = self.processor(capture_factory=lambda _: Capture(count=1, fps=60),
                                   stages=[Sleepy('ball', delay=0)])
        processor.start(self.source)
        status = self.finished(processor)
        self.assertAlmostEqual(status['frame_budget_ms'], 1000 / 60, places=3)

    def test_fast_stage_publishes_every_frame_with_its_own_timing(self):
        calls = []
        stage = Sleepy('ball', delay=0, calls=calls, result={'boxes': [{'label': 'ball'}]})
        processor = self.processor(capture_factory=lambda _: Capture(count=4, fps=30), stages=[stage],
                                   frame_budget_ms=1000)
        processor.start(self.source)
        status = self.finished(processor)
        self.assertEqual(status['frames_processed'], 4)
        self.assertEqual(sum(status['drop_reasons'].values()), 0)
        self.assertIsNone(status['last_drop'])
        jpeg, metadata = processor.latest_jpeg()
        self.assertEqual(metadata['seq'], 4)
        self.assertEqual(list(metadata['stage_ms']), ['ball'])
        self.assertEqual(metadata['detections']['boxes'], [{'label': 'ball'}])
        self.assertEqual(metadata['detections']['detectors'], ['table', 'person'])
        self.assertGreaterEqual(metadata['inference_ms'], 0)
        self.assert_partition(status)

    def test_stage_order_and_upstream_context_in_the_live_loop(self):
        seen = []
        first = Sleepy('first', delay=0, calls=[], result={'boxes': [{'label': 'table'}],
                                                          'table_polygon': [[0, 0], [1, 0], [1, 1], [0, 1]]})
        processor = self.processor(capture_factory=lambda _: Capture(count=1, fps=200),
                                   stages=[first, Reader(seen)], frame_budget_ms=1000)
        status = processor.start(self.source)
        self.assertEqual([stage['name'] for stage in status['stages']], ['first', 'reader'])
        status = self.finished(processor)
        self.assertEqual(seen, [{'boxes': [{'label': 'table'}], 'table_polygon': [[0, 0], [1, 0], [1, 1], [0, 1]]}])
        jpeg, metadata = processor.latest_jpeg()
        self.assertEqual(list(metadata['stage_ms']), ['first', 'reader'])
        self.assertEqual([box['label'] for box in metadata['detections']['boxes']], ['table', 'person'])
        self.assertEqual(metadata['detections']['table_polygon'], [[0, 0], [1, 0], [1, 1], [0, 1]])
        self.assert_partition(status)

    def test_superseded_frames_are_counted_as_no_frame_ready(self):
        stage = Sleepy('ball', delay=.05)
        processor = self.processor(capture_factory=lambda _: Capture(count=30, fps=200), stages=[stage],
                                   budget_enforcement=False)
        processor.start(self.source)
        self.wait_for(processor, lambda s: not s['decoder_alive'])
        status = self.finished(processor)
        self.assertGreater(status['drop_reasons']['no_frame_ready'], 20)
        self.assertEqual(status['drop_reasons']['stage_overrun'], 0)
        self.assertGreaterEqual(status['frames_processed'], 1)
        self.assertLess(status['frames_processed'], 30)
        self.assertEqual(status['drop_reasons']['no_frame_ready'],
                         status['frames_received'] - status['frames_processed'])
        self.assertEqual(status['drop_reasons']['stale'], 0)
        self.assertEqual(status['latest']['seq'], 30)
        self.assert_partition(status)

    def test_frames_older_than_the_budget_are_stale_and_never_reach_a_stage(self):
        calls = []
        stage = Sleepy('ball', delay=0, calls=calls)
        processor = self.processor(capture_factory=lambda _: Capture(count=4, fps=30), stages=[stage],
                                   frame_budget_ms=0.0)
        processor.start(self.source)
        status = self.finished(processor)
        self.assertEqual(status['frames_processed'], 0)
        self.assertEqual(status['drop_reasons']['stale'], 4)
        self.assertEqual(status['last_drop']['reason'], 'stale')
        self.assertEqual(status['last_drop']['stage'], None)
        self.assertEqual(calls, [])
        self.assert_partition(status)

    def test_stop_abandons_the_in_flight_frame_as_stale(self):
        entered, unblock = threading.Event(), threading.Event()
        self.addCleanup(unblock.set)

        class Blocked(Stage):
            name = 'blocked'

            def process(self, frame, context):
                entered.set()
                unblock.wait(2)
                return {}

        processor = self.processor(capture_factory=lambda _: Capture(count=1, fps=200),
                                   stages=[Blocked()], stop_timeout=.02, budget_enforcement=False)
        processor.start(self.source)
        self.assertTrue(entered.wait(1))
        self.assertEqual(processor.stop()['state'], 'stopping')
        unblock.set()
        status = self.finished(processor)
        self.assertEqual(status['frames_processed'], 0)
        self.assertEqual(status['drop_reasons']['stale'], 1)
        self.assertIsNone(processor.latest_jpeg())
        self.assert_partition(status)

    def test_status_exposes_the_rolling_latency_window(self):
        processor = self.processor(capture_factory=lambda _: Capture(count=5, fps=200),
                                   stages=[Sleepy('ball', delay=0)], frame_budget_ms=1000, latency_window=3)
        status = processor.start(self.source)
        self.assertEqual(status['latency_window'], 3)
        self.assertEqual(status['latency_ms'], {})
        self.assertEqual(status['stages'][0]['count'], 0)
        status = self.finished(processor)
        for name in ('decode', 'inter_frame', 'resize', 'encode', 'ball',
                     'receive_to_process', 'receive_to_result'):
            summary = status['latency_ms'][name]
            self.assertIsNotNone(summary['p50_ms'], name)
            self.assertGreaterEqual(summary['p95_ms'], summary['p50_ms'], name)
            self.assertGreaterEqual(summary['max_ms'], summary['p95_ms'], name)
            self.assertEqual(summary['last_ms'], summary['max_ms'] if summary['count'] == 1 else summary['last_ms'])
        self.assertEqual(status['stages'][0]['name'], 'ball')
        self.assertEqual(status['stages'][0]['count'], status['latency_ms']['ball']['count'])
        self.assertLessEqual(status['latency_ms']['decode']['count'], 3)

    def test_infer_and_stages_are_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            LiveProcessor(self.root, infer=lambda *args: {}, stages=[Sleepy()])

    def test_configured_budget_overrides_the_source_fps(self):
        processor = self.processor(capture_factory=lambda _: Capture(count=2, fps=200),
                                   stages=[Sleepy('ball', delay=.06)], frame_budget_ms=500)
        status = processor.start(self.source)
        self.assertEqual(status['frame_budget_ms'], 500)
        status = self.finished(processor)
        self.assertEqual(status['frames_processed'], 2)
        self.assertEqual(sum(status['drop_reasons'].values()), 0)

    def test_real_jpeg_is_published_with_the_stage_timings(self):
        processor = self.processor(capture_factory=lambda _: Capture(count=1, fps=200),
                                   stages=[Sleepy('ball', delay=0)], frame_budget_ms=1000)
        processor.start(self.source)
        self.finished(processor)
        jpeg, metadata = processor.latest_jpeg()
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(image.shape[:2], (32, 32))
        self.assertEqual(int(image[0, 0, 0]), 1)
        self.assertEqual(metadata['width'], 32)
        self.assertEqual(metadata['receive_to_result_ms'] >= metadata['inference_ms'], True)

    def published(self, processor, count):
        """Every distinct published frame's metadata, keyed by sequence."""
        seen = {}
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            pair = processor.latest_jpeg()
            if pair is not None:
                seen[pair[1]['seq']] = pair[1]
            status = processor.status()
            if len(seen) >= count and not status['worker_alive']:
                break
            if len(seen) >= count and status['frames_received'] >= count:
                break
            time.sleep(.002)
        return seen

    def test_partitioned_stage_is_absent_not_stale_on_skipped_frames(self):
        stage = Sleepy('ball', delay=0, result={'boxes': [{'label': 'ball'}]})
        stage.every_n_frames = 2
        processor = self.processor(capture_factory=lambda _: Capture(count=6, fps=30), stages=[stage],
                                   frame_budget_ms=1000)
        processor.start(self.source)
        seen = self.published(processor, 6)
        self.assertEqual(sorted(seen), [1, 2, 3, 4, 5, 6])
        for seq, metadata in seen.items():
            evidence = metadata['stage_evidence']['ball']
            if seq % 2:                                  # frames 1, 3, 5 ran
                self.assertEqual(evidence, dict(ran=True, age_frames=0), seq)
                self.assertEqual(metadata['detections']['boxes'], [{'label': 'ball'}], seq)
                self.assertIn('ball', metadata['stage_ms'], seq)
            else:                                        # 2, 4, 6 skipped
                self.assertEqual(evidence, dict(ran=False, age_frames=1), seq)
                self.assertEqual(metadata['detections']['boxes'], [], seq)
                self.assertNotIn('ball', metadata['stage_ms'], seq)
        status = self.finished(processor)
        self.assertEqual(status['frames_processed'], 6)

    def test_ball_stage_publishes_positions_for_the_frames_it_runs_on(self):
        """The real BallStage class through the real live loop, with a stub net.

        No assertion here is a function of scheduling. The host is shared, so how
        many of six frames reach `frames_processed` depends on whether the decoder
        superseded one before the worker took it - that is the pipeline's documented
        behaviour and this test does not pretend it is not. What is asserted is the
        invariant: at cadence 1 every published frame ran the ball stage, so every
        one carries `balls`, its evidence, and its timing, and the positions are in
        the working frame's pixels.
        """
        stage = StubBallStage(self.root, peak=(480, 270))
        processor = self.processor(capture_factory=lambda _: Capture(count=6, fps=30),
                                   stages=[stage], frame_budget_ms=1000)
        processor.start(self.source)
        seen = self.published(processor, 3)
        status = self.finished(processor)
        self.assertGreaterEqual(len(seen), 1)
        for seq, metadata in seen.items():
            evidence = metadata['stage_evidence']['ball']
            self.assertEqual(evidence['ran'], True, seq)
            self.assertEqual(evidence['ball_stack'], 'causal', seq)
            self.assertEqual(evidence['ball_count'], 1, seq)
            # A square 32x32 working frame from the net's 960x540: the two axes scale
            # independently (32/960 on x, 32/540 on y).
            self.assertEqual(metadata['detections']['balls'],
                             [{'x': 16.0, 'y': 16.0, 'score': 0.9}], seq)
            self.assertEqual(metadata['detections']['boxes'], [], seq)
            self.assertIn('ball', metadata['stage_ms'], seq)
        self.assertEqual(status['stages'][0]['every_n_frames'], 1)
        self.assertGreaterEqual(status['stages'][0]['runs'], 1)
        self.assertEqual(status['stages'][0]['skips'], 0)

    def test_ball_stage_is_absent_exactly_when_it_did_not_run(self):
        """The `balls` key is present exactly when the stage ran - never stale.

        Read as an invariant over whatever frames the host let through rather than
        as a count: `ran`, the `balls` key in the payload and the `ball` entry in
        `stage_ms` have to agree on every frame, and a skipped frame must report the
        age of the result it did not reuse. The deterministic, thread-free version of
        this property is `test_a_skipped_frame_has_no_ball_result_at_all` in
        tests/test_pipeline_stages.py, which drives the registry directly; this one
        proves the same property survives the real decode loop.
        """
        stage = StubBallStage(self.root, peak=(480, 270), every_n_frames=2)
        seen, holder = {}, {}

        class Lockstep(Capture):
            """Hands over the next frame only once the previous one is published, and records
            each published payload, so every frame reaches the stage in order.  Under load a
            stalled worker let the decoder supersede them all (0 published, measured).  The
            budget is a different contract, pinned by the budget tests above; it is off here
            so a slow host cannot drop the evidence under test."""
            def read(self):
                if self.index:
                    deadline = time.monotonic() + 30
                    while holder['p'].status()['frames_processed'] < self.index and time.monotonic() < deadline:
                        time.sleep(.002)
                    pair = holder['p'].latest_jpeg()
                    if pair is not None:
                        seen[pair[1]['seq']] = pair[1]
                return super().read()

        processor = holder['p'] = self.processor(capture_factory=lambda _: Lockstep(count=6, fps=30),
                                                 stages=[stage], budget_enforcement=False)
        processor.start(self.source)
        status = self.wait_for(processor, lambda s: not s['decoder_alive'] and not s['worker_alive'], timeout=60)
        seen[status['latest']['seq']] = status['latest']
        self.assertEqual((status['frames_received'], status['frames_processed']), (6, 6), status['drop_reasons'])
        self.assertEqual(sorted(seen), [1, 2, 3, 4, 5, 6], 'every frame was published and read')
        # Cadence 2 on six frames: the stage ran on exactly half, alternating.
        self.assertEqual([seen[seq]['stage_evidence']['ball']['ran'] for seq in range(1, 7)],
                         [True, False, True, False, True, False])
        for seq, metadata in seen.items():
            evidence = metadata['stage_evidence']['ball']
            self.assertEqual('balls' in metadata['detections'], bool(evidence['ran']), seq)
            self.assertEqual('ball' in metadata['stage_ms'], bool(evidence['ran']), seq)
            if not evidence['ran']:
                self.assertGreaterEqual(evidence['age_frames'], 1, seq)
                self.assertNotIn('balls', metadata['detections'], seq)
        entry = status['stages'][0]
        self.assertEqual(entry['every_n_frames'], 2)
        self.assertGreaterEqual(entry['runs'], 1)
        if status['frames_processed'] >= 2:
            self.assertGreaterEqual(entry['skips'], 1)       # cadence 2: half the frames
        # The pipeline's own partition, which no amount of load may break.
        self.assertEqual(status['frames_processed'] + sum(status['drop_reasons'].values()),
                         status['frames_received'])

    def test_status_reports_cadence_runs_skips_and_evidence(self):
        stage = Sleepy('ball', delay=0, result={'boxes': [{'label': 'ball'}]})
        stage.every_n_frames = 3
        processor = self.processor(capture_factory=lambda _: Capture(count=6, fps=30), stages=[stage],
                                   frame_budget_ms=1000)
        processor.start(self.source)
        status = self.finished(processor)
        entry = status['stages'][0]
        self.assertEqual(entry['every_n_frames'], 3)
        self.assertEqual((entry['runs'], entry['skips']), (2, 4))
        self.assertEqual(entry['runs'] + entry['skips'], status['frames_processed'])
        self.assertEqual(entry['count'], 2)              # only executed frames feed the window
        self.assertEqual(entry['evidence'], dict(ran=False, age_frames=2))

    def test_invalid_cadence_is_refused_at_start(self):
        stage = Sleepy('ball', delay=0)
        stage.every_n_frames = 0
        processor = self.processor(capture_factory=lambda _: Capture(count=1), stages=[stage])
        with self.assertRaises(ValueError):
            processor.start(self.source)

    def test_saved_table_reference_travels_with_the_published_frame(self):
        quad = [[532.0, 323.0], [800.0, 324.0], [997.0, 569.0], [384.0, 563.0]]
        (self.root / 'out/calib_vod30_segments.json').write_text(json.dumps({
            'dataset': 'vod30', 'frame_size': [1280, 720], 'segmentation_verdict': 'single_segment',
            'segments': [dict(id='seg-1', t_start=0.0, t_end=100.0, source='human_anchors',
                              quad_px=quad)]}))
        stage = TableStage(self.root, dataset='vod30')
        processor = self.processor(capture_factory=lambda _: PositionCapture(count=2, fps=30, shape=(36, 64, 3)),
                                   stages=[stage], frame_budget_ms=1000)
        processor.start(self.source)
        self.finished(processor)
        jpeg, metadata = processor.latest_jpeg()
        evidence = metadata['stage_evidence']['table']
        self.assertEqual(evidence['table_source'], 'saved:seg-1')
        self.assertEqual(evidence['table_age_frames'], 0)
        self.assertEqual(evidence['table_reference_size'], [1280, 720])
        self.assertEqual(evidence['ran'], True)
        self.assertEqual(metadata['source_frame_index'], 1)      # second frame of the file
        # 64x36 working frame from a 1280x720 reference: 0.05 scale on both axes.
        self.assertEqual(metadata['detections']['table_polygon'][0], [26.6, 16.15])
        status = processor.status()
        self.assertEqual(status['stages'][0]['evidence']['table_source'], 'saved:seg-1')
        self.assertEqual(status['source_fps'], 30.0)
        self.assertEqual(status['latency_ms']['table']['count'], 2)

    def test_measured_table_is_labelled_and_aged_without_a_reference(self):
        measured = {'boxes': [], 'table_polygon': [[1.0, 1.0], [2.0, 1.0], [2.0, 2.0], [1.0, 2.0]]}
        stage = TableStage(self.root, dataset=None, measure_every_n=2)
        processor = self.processor(capture_factory=lambda _: PositionCapture(count=4, fps=30),
                                   stages=[stage], frame_budget_ms=1000)
        with patch('src.frame_inference.infer_frame', return_value=measured) as infer:
            processor.start(self.source)
            status = self.finished(processor)
        self.assertEqual(infer.call_count, 2)                    # frames 0 and 2
        entry = status['stages'][0]
        self.assertEqual((entry['runs'], entry['skips']), (4, 0))  # it answers every frame
        self.assertEqual(entry['evidence']['table_source'], 'measured')
        self.assertEqual(entry['evidence']['table_age_frames'], 1)  # last frame reuses frame 2's quad
        self.assertEqual(status['frames_processed'], 4)


if __name__ == '__main__':
    unittest.main()
