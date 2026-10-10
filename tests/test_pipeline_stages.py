import json
import threading
import time
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np

from annotator.pipeline_stages import (BallStage, CallableStage, LatencyWindow, Stage,
                                       StageRegistry, TableStage, default_stages,
                                       merge_detections)


class Recorder(Stage):
    """Records the order it ran in; its result names itself."""

    def __init__(self, name, calls, result=None, budget_ms=None, delay=0.0):
        self.name = name
        self.calls = calls
        self.result = {'name': name} if result is None else result
        self.budget_ms = budget_ms
        self.delay = delay

    def process(self, frame, context):
        self.calls.append(self.name)
        if self.delay:
            time.sleep(self.delay)
        return self.result


class ContextStage(Stage):
    name = 'second'

    def __init__(self, calls):
        self.calls = calls

    def process(self, frame, context):
        self.calls.append(context.result('first'))
        return {'upstream': context.result('first'), 'future': context.result('third', 'unset')}


class SlowStage(Stage):
    name = 'slow'

    def __init__(self, delay=0.02, budget_ms=None):
        self.delay = delay
        self.budget_ms = budget_ms

    def process(self, frame, context):
        time.sleep(self.delay)
        return {}


class PipelineStageTests(unittest.TestCase):
    def test_registry_runs_stages_in_registration_order(self):
        calls = []
        stages = [Recorder('a', calls), Recorder('b', calls), Recorder('c', calls)]
        registry = StageRegistry(stages)
        self.assertEqual(registry.names(), ['a', 'b', 'c'])
        run = registry.run('frame')
        self.assertEqual(calls, ['a', 'b', 'c'])
        self.assertEqual(list(run.results), ['a', 'b', 'c'])
        self.assertEqual(list(run.timings_ms), ['a', 'b', 'c'])
        self.assertEqual(set(run.timings_ms), {'a', 'b', 'c'})
        self.assertGreaterEqual(run.total_ms, sum(run.timings_ms.values()) - 1e-6)
        self.assertIsNone(run.overrun_stage)

    def test_context_exposes_earlier_results_only(self):
        seen = []
        registry = StageRegistry([Recorder('first', []), ContextStage(seen), Recorder('third', [])])
        run = registry.run('frame')
        self.assertEqual(seen, [{'name': 'first'}])
        self.assertEqual(run.results['second']['upstream'], {'name': 'first'})
        self.assertEqual(run.results['second']['future'], 'unset')

    def test_malformed_and_duplicate_stages_are_refused(self):
        class Nameless:
            def process(self, frame, context):
                return {}

        class NoProcess:
            name = 'no-process'

        registry = StageRegistry([Recorder('a', [])])
        for stage in [Nameless(), NoProcess(), object(), Recorder('a', []),
                      Recorder('b', [], budget_ms=0), Recorder('c', [], budget_ms=-1),
                      Recorder('d', [], budget_ms=True), Recorder('', [])]:
            with self.assertRaises(ValueError):
                registry.add(stage)

    def test_stage_budget_overrun_is_reported(self):
        registry = StageRegistry([SlowStage(delay=.02, budget_ms=5)])
        run = registry.run('frame')
        self.assertEqual(run.overrun_stage, 'slow')
        self.assertEqual(run.budget_ms, 5)
        self.assertGreater(run.overrun_ms, 5)
        self.assertGreater(run.total_ms, 0)
        generous = StageRegistry([SlowStage(delay=.02, budget_ms=200)]).run('frame')
        self.assertIsNone(generous.overrun_stage)

    def test_frame_budget_counts_time_spent_before_the_stages(self):
        registry = StageRegistry([Recorder('a', [])])
        run = registry.run('frame', elapsed_ms=40, frame_budget_ms=33)
        self.assertEqual(run.overrun_stage, 'a')
        self.assertEqual(run.budget_ms, 33)
        self.assertGreaterEqual(run.overrun_ms, 40)
        within = registry.run('frame', elapsed_ms=10, frame_budget_ms=33)
        self.assertIsNone(within.overrun_stage)

    def test_no_frame_budget_measures_without_enforcing(self):
        run = StageRegistry([SlowStage(delay=.02)]).run('frame', elapsed_ms=500, frame_budget_ms=None)
        self.assertIsNone(run.overrun_stage)
        self.assertIsNone(run.budget_ms)

    def test_latency_window_percentiles_and_rolling_cap(self):
        window = LatencyWindow(100)
        for value in range(1, 101):
            window.add('stage', value)
        summary = window.summary('stage')
        self.assertEqual(summary, dict(count=100, p50_ms=50, p95_ms=95, max_ms=100, last_ms=100))
        self.assertEqual(window.summary('missing'),
                         dict(count=0, p50_ms=None, p95_ms=None, max_ms=None, last_ms=None))
        rolling = LatencyWindow(3)
        for value in (1, 2, 3, 4):
            rolling.add('stage', value)
        self.assertEqual(rolling.summary('stage'),
                         dict(count=3, p50_ms=3, p95_ms=4, max_ms=4, last_ms=4))
        self.assertEqual(rolling.names(), ['stage'])
        self.assertEqual(list(rolling.snapshot()), ['stage'])
        small = LatencyWindow(2)
        small.add('a', 1)
        small.add('a', 3)
        self.assertEqual((small.summary('a')['p50_ms'], small.summary('a')['p95_ms']), (1.0, 3.0))
        for size in (0, -1, 2.5, True, 'four'):
            with self.assertRaises(ValueError):
                LatencyWindow(size)

    def test_latency_window_is_thread_safe_and_ignores_non_finite(self):
        window = LatencyWindow(500)
        def feed(offset):
            for value in range(50):
                window.add('stage', offset + value)
        threads = [threading.Thread(target=feed, args=(index * 50,)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        summary = window.summary('stage')
        self.assertEqual(summary['count'], 200)
        self.assertEqual(summary['max_ms'], 199)
        for value in (float('nan'), float('inf'), -1):
            window.add('other', value)
        self.assertEqual(window.summary('other')['max_ms'], 0.0)

    def test_default_stages_follow_the_detector_list(self):
        self.assertEqual([stage.name for stage in default_stages(['table', 'person'], '/root')],
                         ['table', 'person'])
        self.assertEqual([stage.name for stage in default_stages(['person'], '/root')], ['person'])
        self.assertEqual([stage.name for stage in default_stages(['table'], '/root')], ['table'])
        self.assertEqual(default_stages([], '/root'), [])

    def test_callable_stage_passes_detectors_and_root(self):
        seen = []
        stage = CallableStage('detect', lambda frame, detectors, root: seen.append((frame, detectors, root)) or {'boxes': []},
                              ['person'], '/root')
        run = StageRegistry([stage]).run('frame')
        self.assertEqual(seen, [('frame', ['person'], '/root')])
        self.assertEqual(run.results['detect'], {'boxes': []})

    def test_merge_detections_folds_stage_results_in_order(self):
        results = {'table': {'boxes': [], 'table_polygon': [[0, 0], [1, 0], [1, 1], [0, 1]]},
                   'person': {'boxes': [{'label': 'person'}]}, 'ball': {'boxes': [{'label': 'ball'}]}}
        merged = merge_detections(results, ['table', 'person', 'ball'])
        self.assertEqual(merged['boxes'], [{'label': 'person'}, {'label': 'ball'}])
        self.assertEqual(merged['table_polygon'], [[0, 0], [1, 0], [1, 1], [0, 1]])
        self.assertEqual(merged['detectors'], ['table', 'person', 'ball'])
        self.assertFalse(merged['events_supported'])
        self.assertIn('cannot infer shots', merged['event_note'])
        empty = merge_detections({}, ['table'])
        self.assertEqual(empty['boxes'], [])
        self.assertIsNone(empty['table_polygon'])
        self.assertEqual(empty['detectors'], ['table'])

    def test_cadence_skips_frames_and_reports_absent_evidence(self):
        calls = []
        stage = Recorder('ball', calls)
        stage.every_n_frames = 3
        registry = StageRegistry([stage])
        runs = [registry.run('frame') for _ in range(7)]
        self.assertEqual(calls, ['ball', 'ball', 'ball'])          # frames 0, 3, 6
        self.assertEqual([run.ran for run in runs],
                         [['ball'], [], [], ['ball'], [], [], ['ball']])
        self.assertEqual([run.skipped for run in runs],
                         [[], ['ball'], ['ball'], [], ['ball'], ['ball'], []])
        for index, run in enumerate(runs):
            entry = run.evidence['ball']
            if index % 3 == 0:
                self.assertEqual(entry, dict(ran=True, age_frames=0))
                self.assertIn('ball', run.results)
                self.assertIn('ball', run.timings_ms)
            else:
                # Absent, not stale: no result, no timing sample, an age the consumer can read.
                self.assertEqual(entry, dict(ran=False, age_frames=index % 3))
                self.assertNotIn('ball', run.results)
                self.assertNotIn('ball', run.timings_ms)
        self.assertEqual(runs[1].frame_number, 1)
        self.assertEqual(registry.frames, 7)

    def test_stage_added_mid_run_reports_no_evidence_yet(self):
        registry = StageRegistry([Recorder('a', [])])
        registry.run('frame')
        late = Recorder('late', [])
        late.every_n_frames = 2
        registry.add(late)
        run = registry.run('frame')                                # frame 1: cadence skips it
        self.assertEqual(run.evidence['late'], dict(ran=False, age_frames=None))

    def test_cadence_must_be_a_positive_integer(self):
        for value in (0, -1, 2.5, True, 'two'):
            stage = Recorder('a', [])
            stage.every_n_frames = value
            with self.assertRaises(ValueError):
                StageRegistry([stage])

    def test_registry_accepts_none_cadence_as_every_frame(self):
        stage = Recorder('a', [])
        stage.every_n_frames = None
        registry = StageRegistry([stage])
        self.assertEqual(registry.run('frame').ran, ['a'])

    def test_stage_provenance_is_merged_into_evidence(self):
        class Provenance(Stage):
            name = 'table'

            def process(self, frame, context):
                return {'boxes': [], 'source': 'saved:seg-1'}

            def evidence(self, result):
                return {'source': result.get('source')}

        run = StageRegistry([Provenance()]).run('frame')
        self.assertEqual(run.evidence['table'], dict(ran=True, age_frames=0, source='saved:seg-1'))

    def test_a_hook_cannot_replace_the_registrys_own_answer(self):
        class Claiming(Stage):
            name = 'ball'

            def process(self, frame, context):
                return {'balls': []}

            def evidence(self, result):
                return {'ran': False, 'age_frames': 99, 'ball_source': 'cached'}

        run = StageRegistry([Claiming()]).run('frame')
        entry = run.evidence['ball']
        # The registry's two keys are its own: the timing sample exists, so the frame
        # cannot claim this stage did not run.
        self.assertEqual(entry['ran'], True)
        self.assertEqual(entry['age_frames'], 0)
        self.assertIn('ball', run.timings_ms)
        self.assertEqual(entry['ball_source'], 'cached')
        self.assertIn('age_frames, ran', entry['evidence_error'])

    def test_a_hook_that_returns_no_dict_says_so_instead_of_vanishing(self):
        class Broken(Stage):
            name = 'ball'

            def process(self, frame, context):
                return {'balls': []}

            def evidence(self, result):
                return ['ball_source', 'cached']

        run = StageRegistry([Broken()]).run('frame')
        entry = run.evidence['ball']
        self.assertEqual(entry['ran'], True)
        self.assertEqual(entry['age_frames'], 0)
        self.assertIn('returned list, not a dict', entry['evidence_error'])

    def test_a_hook_that_raises_does_not_stop_the_frame(self):
        class Raising(Stage):
            name = 'ball'

            def process(self, frame, context):
                return {'balls': [1, 2]}

            def evidence(self, result):
                raise RuntimeError('no provenance today')

        run = StageRegistry([Raising(), Recorder('after', [])]).run('frame')
        self.assertEqual(run.ran, ['ball', 'after'])
        self.assertEqual(run.results['ball'], {'balls': [1, 2]})
        self.assertIn('ball', run.timings_ms)
        self.assertIn('RuntimeError: no provenance today', run.evidence['ball']['evidence_error'])
        self.assertEqual(run.evidence['after'], dict(ran=True, age_frames=0))

    def test_a_stage_object_without_a_hook_reports_no_error(self):
        class Plain:
            name = 'plain'
            budget_ms = None

            def process(self, frame, context):
                return {'ok': True}

        run = StageRegistry([Plain()]).run('frame')
        self.assertEqual(run.evidence['plain'], dict(ran=True, age_frames=0))


class TableStageTests(unittest.TestCase):
    """The static-table stage: saved segment reference first, measured cadence second."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'out').mkdir()
        quad = [[532.0, 323.0], [800.0, 324.0], [997.0, 569.0], [384.0, 563.0]]
        (self.root / 'out/calib_vod30_segments.json').write_text(json.dumps({
            'dataset': 'vod30', 'frame_size': [1280, 720], 'segmentation_verdict': 'single_segment',
            'segments': [dict(id='seg-1', t_start=0.0, t_end=100.0, source='human_anchors', quad_px=quad)]}))
        self.frame = np.zeros((540, 960, 3), dtype=np.uint8)

    def test_saved_reference_is_served_scaled_without_measuring(self):
        stage = TableStage(self.root, dataset='vod30')
        with patch('src.frame_inference.infer_frame', side_effect=AssertionError('must not measure')):
            run = StageRegistry([stage]).run(self.frame, time_s=10.0)
        polygon = run.results['table']['table_polygon']
        self.assertEqual(polygon[0], [399.0, 242.25])            # 532*0.75, 323*0.75
        self.assertEqual(polygon[2], [747.75, 426.75])
        evidence = run.evidence['table']
        self.assertEqual(evidence['table_source'], 'saved:seg-1')
        self.assertEqual(evidence['table_age_frames'], 0)
        self.assertEqual(evidence['table_reference_size'], [1280, 720])

    def test_out_of_range_segment_is_labelled_as_clamped(self):
        stage = TableStage(self.root, dataset='vod30')
        run = StageRegistry([stage]).run(self.frame, time_s=500.0)
        self.assertTrue(run.evidence['table']['table_source'].startswith('saved-clamped:seg-1'))

    def test_missing_time_falls_back_to_measuring(self):
        stage = TableStage(self.root, dataset='vod30')
        measured = {'boxes': [], 'table_polygon': [[1, 2], [3, 4], [5, 6], [7, 8]]}
        with patch('src.frame_inference.infer_frame', return_value=measured) as infer:
            run = StageRegistry([stage]).run(self.frame)
        infer.assert_called_once_with(self.frame, ['table'], self.root)
        self.assertEqual(run.results['table']['table_polygon'], measured['table_polygon'])
        self.assertEqual(run.evidence['table']['table_source'], 'measured')
        self.assertEqual(run.evidence['table']['table_age_frames'], 0)

    def test_measured_quad_is_cached_and_its_age_is_labelled(self):
        stage = TableStage(self.root, dataset=None, measure_every_n=3)
        measured = {'boxes': [], 'table_polygon': [[1, 2], [3, 4], [5, 6], [7, 8]]}
        registry = StageRegistry([stage])
        with patch('src.frame_inference.infer_frame', return_value=measured) as infer:
            runs = [registry.run(self.frame) for _ in range(5)]
        self.assertEqual(infer.call_count, 2)                    # frames 0 and 3 only
        ages = [run.evidence['table']['table_age_frames'] for run in runs]
        self.assertEqual(ages, [0, 1, 2, 0, 1])
        for run in runs:
            # The quad keeps answering every frame, and every frame says how old it is.
            self.assertIsNotNone(run.results['table']['table_polygon'])
            self.assertEqual(run.evidence['table']['ran'], True)
        self.assertEqual([run.ran for run in runs], [['table']] * 5)

    def test_table_stage_always_answers_every_frame(self):
        self.assertEqual(TableStage(self.root).every_n_frames, 1)
        self.assertEqual(default_stages(['table'], self.root)[0].dataset, None)
        self.assertEqual(default_stages(['table'], self.root, dataset='vod30')[0].dataset, 'vod30')


class StubBallStage(BallStage):
    """A BallStage whose net is one bright pixel at a chosen model-space point.

    ``device='cpu'`` on purpose: the input build is the same code on both devices, and
    a unit test has no business initialising a GPU context (it cost 20 s of the suite
    when it did).  The CUDA path is checked in tests/ball_stack_ab.py, where the
    bit-identity comparison runs on both.
    """

    def __init__(self, root, peak=(100, 50), **kwargs):
        kwargs.setdefault('device', 'cpu')
        super().__init__(root, model=object(), **kwargs)
        self.peak = peak
        self.stacks = []

    def heatmap(self, stack):
        self.stacks.append(stack)
        heat = np.zeros((self.size[1], self.size[0]), np.float32)
        heat[int(self.peak[1]), int(self.peak[0])] = 0.9
        return heat


class BallStageTests(unittest.TestCase):
    """The detector's contract: positions for the frame, or nothing at all."""

    def setUp(self):
        self.frame = np.zeros((540, 960, 3), np.uint8)

    def test_operating_point_is_the_trained_rounds_checkpoint(self):
        self.assertEqual(BallStage.checkpoint, 'out/tiny_ball_probe/960x540-scratch.pt')
        self.assertEqual(BallStage.threshold, 0.425)
        self.assertEqual(BallStage.size, (960, 540))

    def test_positions_are_reported_in_the_working_frame(self):
        stage = StubBallStage('/root', peak=(100, 50))
        run = StageRegistry([stage]).run(self.frame)
        self.assertEqual(stage.positions(run.results['ball']), [{'x': 100.0, 'y': 50.0, 'score': 0.9}])
        self.assertEqual(run.results['ball']['boxes'], [])
        self.assertEqual(run.evidence['ball']['ball_count'], 1)

    def test_positions_scale_from_the_net_size_to_a_smaller_frame(self):
        stage = StubBallStage('/root', peak=(100, 50), size=(480, 270))
        run = StageRegistry([stage]).run(np.zeros((270, 480, 3), np.uint8))
        self.assertEqual(stage.positions(run.results['ball'])[0]['x'], 100.0)
        stage = StubBallStage('/root', peak=(100, 50))
        run = StageRegistry([stage]).run(np.zeros((270, 480, 3), np.uint8))
        self.assertEqual(stage.positions(run.results['ball']), [{'x': 50.0, 'y': 25.0, 'score': 0.9}])

    def test_a_skipped_frame_has_no_ball_result_at_all(self):
        stage = StubBallStage('/root', every_n_frames=2)
        registry = StageRegistry([stage])
        runs = [registry.run(self.frame) for _ in range(4)]
        for index, run in enumerate(runs):
            merged = merge_detections(run.results, ['table', 'person'])
            if index % 2 == 0:
                self.assertEqual(run.evidence['ball']['ran'], True)
                self.assertEqual(len(merged['balls']), 1)
                self.assertEqual(stage.positions(run.results['ball'])[0]['x'], 100.0)
            else:
                # Absent, never stale: no result to read and no key in the payload.
                self.assertEqual(run.evidence['ball'], dict(ran=False, age_frames=1))
                self.assertNotIn('ball', run.results)
                self.assertNotIn('balls', merged)
                self.assertIsNone(stage.positions(run.results.get('ball')))

    def test_evidence_names_the_causal_stack_and_its_span(self):
        stage = StubBallStage('/root', every_n_frames=3)
        registry = StageRegistry([stage])
        runs = [registry.run(self.frame) for _ in range(7)]
        first, second, third = (runs[0].evidence['ball'], runs[3].evidence['ball'],
                                runs[6].evidence['ball'])
        self.assertEqual(first['ball_stack'], 'causal')
        self.assertEqual([first['ball_stack_planes'], second['ball_stack_planes'],
                          third['ball_stack_planes']], [1, 2, 3])
        self.assertEqual([first['ball_warm'], second['ball_warm'], third['ball_warm']],
                         [True, True, False])
        # Three planes at cadence 3 span 6 source frames - stated, not hidden.
        self.assertIsNone(first['ball_stack_span_frames'])
        self.assertEqual((second['ball_stack_span_frames'], third['ball_stack_span_frames']), (3, 6))
        self.assertEqual(len(stage.stacks), 3)
        # the seam hands the net the CHW tensor the input path built, not an HWC array
        self.assertEqual([tuple(stack.shape) for stack in stage.stacks],
                         [(1, 9, 540, 960)] * 3)
        self.assertEqual({str(stack.dtype) for stack in stage.stacks}, {'torch.float32'})

    def test_cadence_must_be_a_positive_integer(self):
        for value in (0, -1, 2.5, True, 'two'):
            with self.assertRaises(ValueError):
                StubBallStage('/root', every_n_frames=value)

    def test_missing_weights_raise_instead_of_reporting_no_ball(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = BallStage(directory)
            with self.assertRaises(FileNotFoundError) as caught:
                StageRegistry([stage]).run(self.frame)
            self.assertIn('960x540-scratch.pt', str(caught.exception))

    def test_merge_detections_only_carries_balls_when_a_stage_produced_them(self):
        plain = merge_detections({'person': {'boxes': [{'label': 'person'}]}}, ['person'])
        self.assertEqual(plain['boxes'], [{'label': 'person'}])
        self.assertNotIn('balls', plain)
        merged = merge_detections({'person': {'boxes': [{'label': 'person'}]},
                                   'ball': {'boxes': [], 'balls': [{'x': 1, 'y': 2, 'score': 0.9}]}},
                                  ['person'])
        self.assertEqual(merged['boxes'], [{'label': 'person'}])   # ball rows are not boxes
        self.assertEqual(merged['balls'], [{'x': 1, 'y': 2, 'score': 0.9}])


if __name__ == '__main__':
    unittest.main()
