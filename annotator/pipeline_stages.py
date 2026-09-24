"""Per-frame stages: an ordered registry, a rolling latency window, a frame budget.

The decode loop owns *when* a frame is taken; a stage owns *what* is computed from
it.  The contract is one method and two facts::

    class BallStage(Stage):
        name = 'ball'          # unique, used as the metadata/latency key
        budget_ms = 15.0       # optional per-stage ceiling; None borrows the frame budget
        def process(self, frame, context):
            table = context.result('table')      # read an earlier stage, or None
            return {'boxes': [...]}              # any JSON-able result

``context`` exists so a stage that needs an upstream result (the ball detector
needs the cloth polygon the table stage already found) does not recompute it; a
stage that needs nothing ignores the argument.  Registration order is execution
order, and results merge into the frame metadata in that same order.

Nothing here queues or retries.  Metrics are a fixed-size rolling window
(count/p50/p95/max/last) per step, and budget enforcement is deliberately the
caller's decision: this module only *reports* which stage first exceeded its
ceiling (``StageRun.overrun_stage``) plus what it spent, so the pipeline can drop
the frame and say why.  Every stage of a frame always runs, even after one has
already overrun, because a half-measured profile of a late frame is useless.
"""
import math
import threading
import time
from collections import deque


def _percentile(ordered, fraction):
    """Nearest-rank percentile of an already-sorted non-empty sample list."""
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


class Stage:
    """One unit of per-frame work. Subclass and override ``name``/``process``.

    Duck typing is enough: any object with a non-empty ``name``, a callable
    ``process`` and an optional numeric ``budget_ms`` registers as a stage.
    """

    name = 'stage'
    budget_ms = None

    def process(self, frame, context):
        """Return this stage's result for ``frame``; may read ``context.result(name)``."""
        raise NotImplementedError


class StageContext:
    """Live read-only view of the results earlier stages produced for this frame."""

    __slots__ = ('_results', 'seq', 'source')

    def __init__(self, results, seq=None, source=None):
        self._results = results
        self.seq = seq
        self.source = source

    def result(self, name, default=None):
        """Result of an already-executed stage, or ``default`` if it has not run."""
        return self._results.get(name, default)


class StageRun:
    """One frame through the registry: results, per-stage ms, first overrun."""

    __slots__ = ('results', 'timings_ms', 'total_ms', 'overrun_stage', 'overrun_ms', 'budget_ms')

    def __init__(self, results, timings_ms, total_ms, overrun_stage, overrun_ms, budget_ms):
        self.results = results
        self.timings_ms = timings_ms
        self.total_ms = total_ms
        self.overrun_stage = overrun_stage
        self.overrun_ms = overrun_ms
        self.budget_ms = budget_ms


class StageRegistry:
    """Ordered stages: registered order is execution order, duplicates refused.

    ``run`` measures every stage with the injected ``clock`` (the pipeline passes
    its own clock) and flags the first stage that either exceeded its own
    ``budget_ms`` or pushed the whole frame past ``frame_budget_ms`` - counting
    the time already spent before the stages (``elapsed_ms``: decode, scale,
    encode) against that same frame budget.  ``frame_budget_ms=None`` measures
    without enforcing.
    """

    def __init__(self, stages=(), clock=time.perf_counter):
        self._clock = clock
        self._stages = []
        for stage in stages:
            self.add(stage)

    def add(self, stage):
        name = getattr(stage, 'name', None)
        if not isinstance(name, str) or not name:
            raise ValueError('A stage needs a non-empty string name')
        if not callable(getattr(stage, 'process', None)):
            raise ValueError('Stage %s needs a callable process(frame, context)' % name)
        budget = getattr(stage, 'budget_ms', None)
        if budget is not None and (isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0):
            raise ValueError('Stage %s budget_ms must be a positive number or None' % name)
        if any(existing.name == name for existing in self._stages):
            raise ValueError('Duplicate stage name: %s' % name)
        self._stages.append(stage)
        return stage

    def __iter__(self):
        return iter(self._stages)

    def __len__(self):
        return len(self._stages)

    def names(self):
        return [stage.name for stage in self._stages]

    def run(self, frame, *, elapsed_ms=0.0, frame_budget_ms=None, seq=None, source=None):
        results = {}
        timings = {}
        context = StageContext(results, seq=seq, source=source)
        total = max(0.0, float(elapsed_ms))
        overrun = None  # (stage name, measured ms, ceiling ms)
        for stage in self._stages:
            started = self._clock()
            results[stage.name] = stage.process(frame, context)
            taken = max(0.0, self._clock() - started) * 1000
            timings[stage.name] = taken
            total += taken
            if overrun is not None:
                continue
            ceiling = stage.budget_ms if stage.budget_ms is not None else frame_budget_ms
            if ceiling is not None and taken > ceiling:
                overrun = (stage.name, taken, ceiling)
            elif frame_budget_ms is not None and total > frame_budget_ms:
                # The frame's budget is a whole-frame ceiling: the pre-stage time
                # (decode, scale, encode) counts against it too.
                overrun = (stage.name, total, frame_budget_ms)
        name, measured, ceiling = overrun if overrun else (None, None, None)
        return StageRun(results, timings, total, name, measured, ceiling)


class LatencyWindow:
    """Fixed-size rolling latency samples per step, summarised as p50/p95/max/last.

    Thread-safe: the decoder thread records ``decode``/``inter_frame`` while the
    worker thread records the stages and the frame totals.  Percentiles are
    nearest-rank over the retained samples - honest for a window, and stated as
    such rather than interpolated into a number the samples never showed.
    """

    def __init__(self, size=120):
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise ValueError('Latency window size must be a positive integer')
        self.size = size
        self._lock = threading.Lock()
        self._samples = {}

    def add(self, name, ms):
        value = float(ms)
        if not math.isfinite(value):
            return
        with self._lock:
            samples = self._samples.get(name)
            if samples is None:
                samples = self._samples[name] = deque(maxlen=self.size)
            samples.append(max(0.0, value))

    def names(self):
        with self._lock:
            return sorted(self._samples)

    def summary(self, name):
        with self._lock:
            samples = list(self._samples.get(name, ()))
        if not samples:
            return dict(count=0, p50_ms=None, p95_ms=None, max_ms=None, last_ms=None)
        ordered = sorted(samples)
        return dict(count=len(ordered), p50_ms=round(_percentile(ordered, .5), 2),
                    p95_ms=round(_percentile(ordered, .95), 2), max_ms=round(ordered[-1], 2),
                    last_ms=round(samples[-1], 2))

    def snapshot(self):
        return {name: self.summary(name) for name in self.names()}


class PersonStage(Stage):
    """GPU YOLOv8n person boxes on the scaled frame."""

    name = 'person'

    def __init__(self, root):
        from pathlib import Path
        self.root = Path(root)

    def process(self, frame, context):
        from src.frame_inference import infer_frame
        return infer_frame(frame, ['person'], self.root)


class TableStage(Stage):
    """Cloth polygon from the frame's own pixels (live path has no dataset prior)."""

    name = 'table'

    def __init__(self, root):
        from pathlib import Path
        self.root = Path(root)

    def process(self, frame, context):
        from src.frame_inference import infer_frame
        return infer_frame(frame, ['table'], self.root)


class CallableStage(Stage):
    """Adapter for an injected ``infer(frame, detectors, root)``-style callable."""

    def __init__(self, name, call, detectors=(), root=None):
        self.name = name
        self.call = call
        self.detectors = list(detectors)
        self.root = root

    def process(self, frame, context):
        return self.call(frame, self.detectors, self.root)


def default_stages(detectors, root):
    """Registry for the live pipeline's detectors, in inference order (table first)."""
    stages = []
    if 'table' in detectors:
        stages.append(TableStage(root))
    if 'person' in detectors:
        stages.append(PersonStage(root))
    return stages


def merge_detections(results, detectors):
    """Fold per-stage results into the single detections payload the app expects.

    Boxes concatenate in stage order; the first non-empty cloth polygon wins (only
    the table stage produces one today); an unknown/absent note falls back to the
    historical single-frame note so the metadata contract is unchanged.
    """
    boxes, polygon, note = [], None, None
    for result in results.values():
        if not isinstance(result, dict):
            continue
        boxes.extend(result.get('boxes') or [])
        if result.get('table_polygon') is not None:
            polygon = result['table_polygon']
        note = result.get('event_note') or note
    return {'boxes': boxes, 'table_polygon': polygon, 'detectors': list(detectors),
            'events_supported': False,
            'event_note': note or 'Single frames cannot infer shots or events; time-window inference is deferred.'}
