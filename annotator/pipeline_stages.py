"""Per-frame stages: an ordered registry, a rolling latency window, a frame budget.

The decode loop owns *when* a frame is taken; a stage owns *what* is computed from
it.  The contract is one method and three facts::

    class BallStage(Stage):
        name = 'ball'              # unique, used as the metadata/latency key
        every_n_frames = 2         # run on 1 of every N frames; absent (never stale) in between
        def process(self, frame, context):
            table = context.result('table')      # read an earlier stage, or None
            return {'balls': [...]}              # any JSON-able result

``context`` exists so a stage that needs an upstream result (the ball detector
needs the cloth polygon the table stage already found) does not recompute it; a
stage that needs nothing ignores the argument.  Registration order is execution
order, and results merge into the frame metadata in that same order.

**Cadence (``every_n_frames``).**  A partitioned stage runs on 1 frame of every N
and is *absent* on the others: no ``process`` call, no result, no timing sample,
so a consumer can never mistake "did not run" for "found nothing" or for the
previous frame's answer.  Every frame carries ``StageRun.evidence`` - one entry per
registered stage - naming ``ran`` and ``age_frames``, so missing evidence stays
missing and identifiable rather than silently reused.

**Provenance (``Stage.evidence``).**  A stage may report what its result was made
of (measured now, read from a saved reference, cached N frames ago).  That is the
opposite situation from a skipped stage: geometry such as the cloth quad *is* a
property of the camera, not of the frame, so serving a saved quad is correct - as
long as the frame says so and says how old it is.

Nothing here queues or retries.  Metrics are a fixed-size rolling window
(count/p50/p95/max/last) per step, and budget enforcement is deliberately the
caller's decision: this module only *reports* which stage first exceeded its
ceiling (``StageRun.overrun_stage``) plus what it spent, so the pipeline can drop
the frame and say why.  Every stage that runs keeps running after another stage has
already overrun, because a half-measured profile of a late frame is useless.
"""
import math
import threading
import time
from collections import deque

#: The trained ball detector (``src/tiny_ball_net.py``, round ``960x540-scratch``,
#: 300 train frames / 20 epochs) and the operating point its held-out sweep chose:
#: 960x540, threshold 0.425, held-out F1 0.927 (P 0.940 / R 0.914) with median
#: 1.48 px and p90 3.62 px localisation over 47 held-out frames.  The checkpoint
#: path is relative to the pipeline root; ``out/`` is gitignored, so the weights
#: are a local artifact and a root without them gets an error naming the path.
BALL_CHECKPOINT = 'out/tiny_ball_probe/960x540-scratch.pt'
BALL_THRESHOLD = 0.425
BALL_SIZE = (960, 540)
#: Frames per sample the net was trained on: (t-1, t, t+1).
BALL_STACK = 3


def _percentile(ordered, fraction):
    """Nearest-rank percentile of an already-sorted non-empty sample list."""
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _positive_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError('%s must be a positive integer' % label)
    return value


class Stage:
    """One unit of per-frame work. Subclass and override ``name``/``process``.

    Duck typing is enough: any object with a non-empty ``name``, a callable
    ``process``, an optional numeric ``budget_ms`` and an optional integer
    ``every_n_frames`` registers as a stage.
    """

    name = 'stage'
    budget_ms = None
    every_n_frames = 1

    def process(self, frame, context):
        """Return this stage's result for ``frame``; may read ``context.result(name)``."""
        raise NotImplementedError

    def evidence(self, result):
        """What ``result`` was made of, as JSON-able keys merged into the frame's evidence.

        The registry always contributes ``ran``/``age_frames``; a stage overrides this
        only to add provenance (e.g. the table stage's ``source`` and the age of the
        measurement its quad came from).  Must be cheap: it runs once per executed stage.
        """
        return {}


class StageContext:
    """Live read-only view of the results earlier stages produced for this frame."""

    __slots__ = ('_results', 'seq', 'source', 'frame_number', 'frame_index', 'time_s')

    def __init__(self, results, seq=None, source=None, frame_number=0, frame_index=None, time_s=None):
        self._results = results
        self.seq = seq
        self.source = source
        # frame_number: 0-based index since this pipeline run started (never None).
        # frame_index: position in the source media when the decoder can report one.
        # time_s: that position in seconds, which is what a per-segment calibration
        # resolves against.
        self.frame_number = frame_number
        self.frame_index = frame_index
        self.time_s = time_s

    def result(self, name, default=None):
        """Result of an already-executed stage, or ``default`` if it has not run."""
        return self._results.get(name, default)


class StageRun:
    """One frame through the registry: results, per-stage ms, evidence, first overrun."""

    __slots__ = ('results', 'timings_ms', 'total_ms', 'overrun_stage', 'overrun_ms', 'budget_ms',
                 'evidence', 'ran', 'skipped', 'frame_number')

    def __init__(self, results, timings_ms, total_ms, overrun_stage, overrun_ms, budget_ms,
                 evidence, ran, skipped, frame_number):
        self.results = results
        self.timings_ms = timings_ms
        self.total_ms = total_ms
        self.overrun_stage = overrun_stage
        self.overrun_ms = overrun_ms
        self.budget_ms = budget_ms
        self.evidence = evidence      # {stage name: {'ran', 'age_frames', ...provenance}}
        self.ran = ran                # names that executed this frame, in registry order
        self.skipped = skipped        # names whose cadence skipped this frame
        self.frame_number = frame_number


class StageRegistry:
    """Ordered stages: registered order is execution order, duplicates refused.

    ``run`` measures every stage that its cadence lets run, with the injected
    ``clock`` (the pipeline passes its own clock), and flags the first stage that
    either exceeded its own ``budget_ms`` or pushed the whole frame past
    ``frame_budget_ms`` - counting the time already spent before the stages
    (``elapsed_ms``: decode, scale, encode) against that same frame budget.
    ``frame_budget_ms=None`` measures without enforcing.
    """

    def __init__(self, stages=(), clock=time.perf_counter):
        self._clock = clock
        self._stages = []
        self._frame = 0
        self._last_ran = {}
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
        _positive_int(cadence if (cadence := getattr(stage, 'every_n_frames', 1)) is not None else 1,
                      'Stage %s every_n_frames' % name)
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

    @property
    def frames(self):
        """Frames this registry has been asked to run (its own cadence counter)."""
        return self._frame

    def run(self, frame, *, elapsed_ms=0.0, frame_budget_ms=None, seq=None, source=None,
            frame_index=None, time_s=None):
        results = {}
        timings = {}
        evidence = {}
        ran, skipped = [], []
        context = StageContext(results, seq=seq, source=source, frame_number=self._frame,
                               frame_index=frame_index, time_s=time_s)
        total = max(0.0, float(elapsed_ms))
        overrun = None  # (stage name, measured ms, ceiling ms)
        for stage in self._stages:
            name = stage.name
            every = getattr(stage, 'every_n_frames', 1)
            every = 1 if every is None else every
            last = self._last_ran.get(name)
            if self._frame % every:
                # Absent, not stale: nothing ran, so there is no result to merge and no
                # timing sample to dilute the window's percentiles.
                skipped.append(name)
                evidence[name] = dict(ran=False, age_frames=None if last is None else self._frame - last)
                continue
            started = self._clock()
            results[name] = stage.process(frame, context)
            taken = max(0.0, self._clock() - started) * 1000
            timings[name] = taken
            total += taken
            ran.append(name)
            self._last_ran[name] = self._frame
            hook = getattr(stage, 'evidence', None)
            extra = hook(results[name]) if callable(hook) else None
            entry = dict(ran=True, age_frames=0)
            if isinstance(extra, dict):
                entry.update(extra)
            evidence[name] = entry
            if overrun is not None:
                continue
            ceiling = stage.budget_ms if stage.budget_ms is not None else frame_budget_ms
            if ceiling is not None and taken > ceiling:
                overrun = (name, taken, ceiling)
            elif frame_budget_ms is not None and total > frame_budget_ms:
                # The frame's budget is a whole-frame ceiling: the pre-stage time
                # (decode, scale, encode) counts against it too.
                overrun = (name, total, frame_budget_ms)
        name, measured, ceiling = overrun if overrun else (None, None, None)
        run = StageRun(results, timings, total, name, measured, ceiling, evidence, ran, skipped,
                       self._frame)
        self._frame += 1
        return run


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
    """Cloth quad for the frame: the saved segment reference first, else measured on a cadence.

    A static camera makes the quad a property of the *time segment*, not of the frame,
    so this stage does not run a per-frame detection.  With a saved artifact
    (``src/calib_segments.load(dataset, root)``) the quad is resolved for the frame's
    time, scaled from the artifact's reference frame size to the working frame, and
    served with evidence ``source='saved:<segment id>'`` - the reference is the
    operator's human geometry, not a per-frame guess.  Without one (a live stream has
    no saved calibration) the quad is measured from pixels at most once every
    ``measure_every_n`` frames and served from that measurement in between, labelled
    ``source='measured'`` with the age of the measurement in frames.

    ``every_n_frames`` stays 1 on purpose: this stage must *answer* on every frame, and
    only its measurement is cached.  Serving last-known geometry is correct here
    (the camera does not move) precisely because the frame says so and says how old it
    is - unlike a motion stage, where a frame without evidence must stay unknown.
    """

    name = 'table'
    every_n_frames = 1

    def __init__(self, root, dataset=None, measure_every_n=30, segments=None):
        from pathlib import Path
        self.root = Path(root)
        self.dataset = dataset
        self.measure_every_n = _positive_int(measure_every_n, 'measure_every_n')
        self._segments = segments
        self._loaded = segments is not None
        self._measured = None
        self._measured_at = None

    def _reference(self):
        """The dataset's segment artifact, loaded at most once per stage."""
        if not self._loaded:
            self._loaded = True
            if isinstance(self.dataset, str) and self.dataset:
                try:
                    from src.calib_segments import load
                    self._segments = load(self.dataset, root=self.root)
                except Exception:
                    self._segments = None
        return self._segments

    def _saved(self, context):
        """(scaled quad, segment, source label) from the saved reference, or (None, None, None)."""
        segments = self._reference()
        if segments is None or context.time_s is None:
            return None, None, None
        segment = segments.resolve(context.time_s)
        if segment is None:
            return None, None, None
        quad = [[round(float(x), 2), round(float(y), 2)] for x, y in segment.quad]
        return quad, segment, ('saved-clamped:%s' % segment.id if segment.clamped else 'saved:%s' % segment.id)

    def process(self, frame, context):
        from src.frame_inference import infer_frame
        quad, segment, source = self._saved(context)
        height, width = frame.shape[:2]
        if quad is not None:
            reference = (self._reference().payload.get('frame_size') or [width, height])
            try:
                scale_x, scale_y = width / float(reference[0]), height / float(reference[1])
            except (TypeError, ValueError, ZeroDivisionError):
                scale_x = scale_y = 1.0
            scaled = [[round(x * scale_x, 2), round(y * scale_y, 2)] for x, y in quad]
            return {'boxes': [], 'table_polygon': scaled, 'table_source': source,
                    'table_age_frames': 0, 'table_measured_at': None,
                    'table_reference_size': list(reference), 'table_segment': segment.as_dict()}
        if self._measured is None or self._measured_at is None or \
                context.frame_number % self.measure_every_n == 0:
            self._measured = infer_frame(frame, ['table'], self.root)
            self._measured_at = context.frame_number
        result = dict(self._measured)
        result.update(table_source='measured', table_age_frames=context.frame_number - self._measured_at,
                      table_measured_at=self._measured_at, table_reference_size=[width, height])
        return result

    def evidence(self, result):
        if not isinstance(result, dict):
            return {}
        return {key: result.get(key) for key in
                ('table_source', 'table_age_frames', 'table_measured_at', 'table_reference_size')}

    def quad(self, result):
        """The cloth polygon a consumer would use, or None when the stage produced none."""
        return result.get('table_polygon') if isinstance(result, dict) else None


class BallStage(Stage):
    """The trained ball detector (``src/tiny_ball_net.py``) as a per-frame stage.

    The net is a 3-frame-in / heatmap-out CNN: it sees ``(t-1, t, t+1)`` during
    training, and a live pipeline only ever has the past.  This stage therefore
    feeds a **causal** stack - the last three frames it was given, ending at the
    current one - and says so in its evidence (``ball_stack='causal'``), because the
    trained layout is a domain the live one cannot reproduce.  Its result is the
    peaks found in the current frame, in the *working frame's* pixels: a frame whose
    cadence skipped the stage produces nothing at all, never the previous frame's
    answer (see the module docstring on ``every_n_frames``).

    Cadence interacts with the stack and the evidence names it: at
    ``every_n_frames=N`` the stage only sees 1 frame in N, so three planes span
    ``2N`` source frames (``ball_stack_span_frames``).  That is a property of
    partitioning a temporal detector, not a bug to hide.

    Weights are loaded lazily on the first ``process`` call (importing torch at
    module import time would make every consumer of this module pay for it) from
    ``checkpoint`` under ``root``.  A missing checkpoint raises ``FileNotFoundError``
    naming the path - never a silent empty result, which would read as "no ball".
    ``model=``/``heatmap()`` exist so a test can exercise the contract without
    torch, the weights, or a GPU.
    """

    name = 'ball'
    checkpoint = BALL_CHECKPOINT
    threshold = BALL_THRESHOLD
    size = BALL_SIZE
    stack = BALL_STACK

    def __init__(self, root, checkpoint=None, threshold=None, size=None, device='auto',
                 nms_px=4.0, max_balls=6, every_n_frames=1, model=None):
        from pathlib import Path
        self.root = Path(root)
        self.checkpoint = checkpoint or self.checkpoint
        self.threshold = float(self.threshold if threshold is None else threshold)
        self.size = tuple(self.size if size is None else size)
        self.device = device
        self.nms_px = float(nms_px)
        self.max_balls = _positive_int(max_balls, 'max_balls')
        self.every_n_frames = _positive_int(
            every_n_frames if every_n_frames is not None else 1, 'every_n_frames')
        self._model = model
        self._loaded = model is not None
        self._history = deque(maxlen=self.stack)
        self._loaded_from = None
        self._resolved_device = None

    def _load(self):
        """Load the trained weights once; raise (not return empty) if they are absent."""
        if self._loaded:
            return
        from src.tiny_ball_net import build_model, load_checkpoint, pick_device
        path = self.root / self.checkpoint
        if not path.is_file():
            raise FileNotFoundError('Ball stage weights are not on disk: %s' % path)
        model, saved = load_checkpoint(path, self.size)
        device = self._device
        model.to(device)
        model.eval()
        self._model = model
        self._loaded = True
        self._loaded_from = dict(path=str(path), saved_size=list(saved), device=device)

    def heatmap(self, stack):
        """The net's heatmap for one ``H x W x 9`` float stack. Overridden in tests."""
        import numpy as np
        import torch
        tensor = torch.from_numpy(np.ascontiguousarray(stack.transpose(2, 0, 1)))[None]
        with torch.no_grad():
            out = self._model(tensor.to(self._device)).cpu().numpy()
        return out[0, 0]

    @property
    def _device(self):
        """Resolved once: ``torch.cuda.is_available()`` is not worth paying per frame."""
        if self._resolved_device is None:
            from src.tiny_ball_net import pick_device
            self._resolved_device = pick_device(self.device)
        return self._resolved_device

    def process(self, frame, context):
        import cv2
        import numpy as np
        from src.tiny_ball_net import pick_peaks

        self._load()
        height, width = frame.shape[:2]
        small = frame if (width, height) == self.size else cv2.resize(
            frame, self.size, interpolation=cv2.INTER_AREA)
        self._history.append((context.frame_number, small))
        planes = [entry[1] for entry in self._history]
        while len(planes) < self.stack:
            # Opening frames of a run: the net needs three planes and the stream has
            # given fewer, so the oldest available frame is repeated.  Recorded, not
            # hidden - the evidence reports how many planes were real.
            planes.insert(0, planes[0])
        stack = np.concatenate([cv2.cvtColor(plane, cv2.COLOR_BGR2RGB) for plane in planes],
                               axis=2).astype(np.float32) / 255.0
        heat = np.asarray(self.heatmap(stack))
        peaks = pick_peaks(heat, self.threshold, nms_px=self.nms_px)[:self.max_balls]
        scale_x, scale_y = width / float(self.size[0]), height / float(self.size[1])
        balls = [{'x': round(px * scale_x, 2), 'y': round(py * scale_y, 2),
                  'score': round(float(score), 4)}
                 for px, py, score in sorted(peaks, key=lambda peak: -peak[2])]
        frames = [entry[0] for entry in self._history]
        return {'balls': balls, 'boxes': [], 'ball_threshold': self.threshold,
                'ball_stack': 'causal', 'ball_size': list(self.size),
                'ball_stack_planes': len(frames), 'ball_warm': len(frames) < self.stack,
                'ball_stack_span_frames': (None if len(frames) < 2
                                           else frames[-1] - frames[0]),
                'ball_from': dict(self._loaded_from or {})}

    def evidence(self, result):
        if not isinstance(result, dict):
            return {}
        entry = {key: result.get(key) for key in
                 ('ball_threshold', 'ball_stack', 'ball_size', 'ball_stack_planes',
                  'ball_warm', 'ball_stack_span_frames')}
        entry['ball_count'] = len(result.get('balls') or [])
        return entry

    def positions(self, result):
        """Ball positions for the frame: ``[{x, y, score}]``.

        ``[]`` means the stage ran and found nothing; ``None`` means it produced no
        result for this frame at all (cadence skipped it), which is a different fact.
        """
        if result is None or not isinstance(result, dict):
            return None
        return list(result.get('balls') or [])


class CallableStage(Stage):
    """Adapter for an injected ``infer(frame, detectors, root)``-style callable."""

    def __init__(self, name, call, detectors=(), root=None):
        self.name = name
        self.call = call
        self.detectors = list(detectors)
        self.root = root

    def process(self, frame, context):
        return self.call(frame, self.detectors, self.root)


def default_stages(detectors, root, dataset=None, table_measure_every_n=30):
    """Registry for the live pipeline's detectors, in inference order (table first).

    ``dataset`` lets the table stage answer from that dataset's saved segment
    reference instead of measuring a static quad again on every frame; without it
    (a live stream) the stage measures on ``table_measure_every_n``'s cadence and
    labels the age of what it serves.
    """
    stages = []
    if 'table' in detectors:
        stages.append(TableStage(root, dataset=dataset, measure_every_n=table_measure_every_n))
    if 'person' in detectors:
        stages.append(PersonStage(root))
    return stages


def merge_detections(results, detectors):
    """Fold per-stage results into the single detections payload the app expects.

    Boxes concatenate in stage order; the first non-empty cloth polygon wins (only
    the table stage produces one today); an unknown/absent note falls back to the
    historical single-frame note so the metadata contract is unchanged.

    ``balls`` is additive and carries the ball stage's positions for *this* frame.
    The key is present only when a stage actually produced a ball result: a frame
    whose cadence skipped the ball stage has no ``balls`` key at all, so a consumer
    can never read "the detector did not run" as "the detector found nothing" - the
    per-frame ``stage_evidence`` entry says which it was.  Ball rows are deliberately
    NOT appended to ``boxes``: the published box list is what the app draws, and
    injecting detections the app's own detector list never asked for is a contract
    change nobody requested.
    """
    boxes, polygon, note = [], None, None
    balls = None
    for result in results.values():
        if not isinstance(result, dict):
            continue
        boxes.extend(result.get('boxes') or [])
        if result.get('table_polygon') is not None:
            polygon = result['table_polygon']
        if 'balls' in result:
            balls = list(result['balls']) if balls is None else balls + list(result['balls'])
        note = result.get('event_note') or note
    payload = {'boxes': boxes, 'table_polygon': polygon, 'detectors': list(detectors),
               'events_supported': False,
               'event_note': note or 'Single frames cannot infer shots or events; time-window inference is deferred.'}
    if balls is not None:
        payload['balls'] = balls
    return payload
