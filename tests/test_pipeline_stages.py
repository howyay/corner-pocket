import json
import threading
import time
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np

from annotator.pipeline_stages import (CallableStage, LatencyWindow, Stage, StageRegistry,
                                       TableStage, default_stages, merge_detections)


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

    def test_every_frame_runs_every_stage_and_records_evidence(self):
        calls = []
        stage = Recorder('ball', calls)
        registry = StageRegistry([stage])
        runs = [registry.run('frame') for _ in range(3)]
        self.assertEqual(calls, ['ball'] * 3)
        self.assertEqual([run.ran for run in runs], [['ball']] * 3)
        for index, run in enumerate(runs):
            self.assertEqual(run.evidence['ball'], dict(ran=True, age_frames=0))
            self.assertIn('ball', run.results)
            self.assertIn('ball', run.timings_ms)
        self.assertEqual(runs[1].frame_number, 1)
        self.assertEqual(registry.frames, 3)

    def test_stage_provenance_is_merged_into_evidence(self):
        class Provenance(Stage):
            name = 'table'

            def process(self, frame, context):
                return {'boxes': [], 'source': 'saved:seg-1'}

            def evidence(self, result):
                return {'source': result.get('source')}

        run = StageRegistry([Provenance()]).run('frame')
        self.assertEqual(run.evidence['table'], dict(ran=True, age_frames=0, source='saved:seg-1'))


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

    def test_table_stage_is_wired_with_the_dataset_reference(self):
        self.assertEqual(default_stages(['table'], self.root)[0].dataset, None)
        self.assertEqual(default_stages(['table'], self.root, dataset='vod30')[0].dataset, 'vod30')
        self.assertEqual(default_stages(['table'], self.root, dataset='vod30')[0].name, 'table')


if __name__ == '__main__':
    unittest.main()
