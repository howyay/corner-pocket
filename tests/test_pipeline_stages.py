import threading
import time
import unittest

from annotator.pipeline_stages import (CallableStage, LatencyWindow, Stage, StageRegistry,
                                       default_stages, merge_detections)


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


if __name__ == '__main__':
    unittest.main()
