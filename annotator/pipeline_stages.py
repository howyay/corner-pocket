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
long as the frame says so and says how old it is.  The registry owns ``ran`` and
``age_frames``; a hook adds names beside them and cannot replace them.  A hook that
returns something other than a dict, or that raises, never stops a frame: its entry
carries ``evidence_error`` instead, because provenance that failed must still be
visible rather than absent.

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
from dataclasses import dataclass

#: The evidence keys the registry owns.  A stage's ``evidence`` hook adds names
#: beside these two; a hook that returns them is refused and its entry says so.
REGISTRY_KEYS = ('ran', 'age_frames')

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
            entry = dict(ran=True, age_frames=0)
            if callable(hook):
                try:
                    extra = hook(results[name])
                except Exception as exc:            # a hook never stops a frame
                    entry['evidence_error'] = ('the evidence hook of stage %s raised %s: %s'
                                               % (name, type(exc).__name__, exc))
                else:
                    if isinstance(extra, dict):
                        claimed = sorted(key for key in extra if key in REGISTRY_KEYS)
                        if claimed:
                            # The registry's own answer is not the stage's to replace: a hook
                            # that answers `ran` could make the frame claim the stage did not
                            # run while its timing sample sits in timings[name].
                            entry['evidence_error'] = ('the evidence hook of stage %s returned the '
                                                       'registry keys %s' % (name, ', '.join(claimed)))
                        entry.update({key: value for key, value in extra.items()
                                      if key not in REGISTRY_KEYS})
                    else:
                        entry['evidence_error'] = ('the evidence hook of stage %s returned %s, not a dict'
                                                   % (name, type(extra).__name__))
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

    def _playfield(self, polygon):
        """The table's own geometry, checked on the polygon this stage is about to publish.

        Round 17, owner item 5: a 9 ft playfield is 100 x 50 inches and keeps at least one pair of
        edges parallel at this venue. The verdict rides with the quad, so a consumer can say why a
        polygon does not match the table instead of throwing a detection away silently. It never
        raises: a constraint must not be able to stop a frame.
        """
        try:
            from src.playfield import check_quad
            pts = [[float(a), float(b)] for a, b in list(polygon or [])][:4]
            if len(pts) != 4:
                return None
            ordered = [[pts[0], pts[1], pts[2], pts[3]], [pts[1], pts[2], pts[3], pts[0]]]
            verdicts = [check_quad(q) for q in ordered]
            best = min(verdicts, key=lambda v: (not v['ok'], len(v['reasons'])))
            return {'ok': bool(best['ok']), 'reasons': list(best['reasons']),
                    'best_parallel_deg': best['metrics'].get('best_parallel_deg'),
                    'aspect': best['metrics'].get('aspect')}
        except Exception as exc:                    # a constraint never stops a frame
            return {'ok': True, 'reasons': [], 'error': str(exc)}

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
                    'table_reference_size': list(reference), 'table_segment': segment.as_dict(),
                    'table_playfield': self._playfield(scaled)}
        if self._measured is None or self._measured_at is None or \
                context.frame_number % self.measure_every_n == 0:
            self._measured = infer_frame(frame, ['table'], self.root)
            self._measured_at = context.frame_number
        result = dict(self._measured)
        result.update(table_source='measured', table_age_frames=context.frame_number - self._measured_at,
                      table_measured_at=self._measured_at, table_reference_size=[width, height],
                      table_playfield=self._playfield(result.get('table_polygon')))
        return result

    def evidence(self, result):
        if not isinstance(result, dict):
            return {}
        return {key: result.get(key) for key in
                ('table_source', 'table_age_frames', 'table_measured_at', 'table_reference_size',
                 'table_playfield')}

    def quad(self, result):
        """The cloth polygon a consumer would use, or None when the stage produced none."""
        return result.get('table_polygon') if isinstance(result, dict) else None


def check_ball_weights(root, checkpoint=None):
    """The trained ball weights under ``root``, or ``FileNotFoundError`` naming the path.

    Exists so a *start* can refuse before any thread runs: a stage the caller asked
    for that silently never executes is worse than a refused start, because every
    downstream number would then look like a measurement of "no ball".  Checks
    existence and a non-empty file only - the weights are loaded lazily on the first
    frame, so a corrupt checkpoint still fails loudly, just later.
    """
    from pathlib import Path
    path = Path(root) / (checkpoint or BALL_CHECKPOINT)
    if not path.is_file():
        raise FileNotFoundError('ball detector weights are not on disk: %s' % path)
    if path.stat().st_size < 1024:
        raise FileNotFoundError('ball detector weights at %s are empty' % path)
    return path


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
    torch, the weights, or a GPU; ``input_for()`` is the seam a bit-identity check
    compares against the previous input path.
    """

    name = 'ball'
    checkpoint = BALL_CHECKPOINT
    threshold = BALL_THRESHOLD
    size = BALL_SIZE
    stack = BALL_STACK

    def __init__(self, root, checkpoint=None, threshold=None, size=None, device='auto',
                 nms_px=4.0, max_balls=12, every_n_frames=1, model=None):
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
        self._device_u8 = None       # resident uint8 planes, (stack, H, W, 3)
        self._device_in = None       # resident float32 input, (1, stack*3, H, W)
        self._device_f64 = None      # staging for the double-rounded /255

    def verify(self):
        """Raise unless the trained weights are readable here, naming the path."""
        return check_ball_weights(self.root, self.checkpoint)

    def _load(self):
        """Load the trained weights once; raise (not return empty) if they are absent."""
        if self._loaded:
            return
        from src.tiny_ball_net import load_checkpoint, pick_device
        path = self.verify()
        model, saved = load_checkpoint(path, self.size)
        device = self._device
        model.to(device)
        model.eval()
        self._model = model
        self._loaded = True
        self._loaded_from = dict(path=str(path), saved_size=list(saved), device=device)

    def heatmap(self, tensor):
        """The net's heatmap for the resident input tensor. Overridden in tests.

        ``tensor`` is the ``(1, stack*3, H, W)`` float32 tensor ``input_for`` built, so
        the model call needs no conversion and no host-to-device copy of its own.
        """
        import torch
        with torch.no_grad():
            out = self._model(tensor).cpu().numpy()
        return out[0, 0]

    @property
    def _device(self):
        """Resolved once: ``torch.cuda.is_available()`` is not worth paying per frame."""
        if self._resolved_device is None:
            from src.tiny_ball_net import pick_device
            self._resolved_device = pick_device(self.device)
        return self._resolved_device

    def _small(self, frame):
        """The frame at the net's input size, one resize (none when it already is)."""
        import cv2
        height, width = frame.shape[:2]
        if (width, height) == self.size:
            return frame
        # INTER_AREA for the normal case (the pipeline caps at exactly this size); a
        # *smaller* source is the one case that needs upscaling, and INTER_AREA
        # degrades to nearest there - a real stream at 640x360 should not be fed a
        # nearest-neighbour blow-up of two thirds of the net's expected pixels.
        return cv2.resize(frame, self.size,
                          interpolation=cv2.INTER_AREA if width >= self.size[0]
                          else cv2.INTER_LINEAR)

    def _planes(self, frame, context):
        """The stack's RGB planes, oldest first, each converted once per frame.

        A frame is converted to RGB on the call that first sees it and then reused as
        the older plane of the next two calls, so three calls convert three planes and
        not nine.  The opening frames of a run repeat the oldest available plane - the
        net needs three and the stream has given fewer - and the evidence reports how
        many were real.
        """
        import cv2
        self._history.append((context.frame_number,
                              cv2.cvtColor(self._small(frame), cv2.COLOR_BGR2RGB)))
        planes = [entry[1] for entry in self._history]
        while len(planes) < self.stack:
            planes.insert(0, planes[0])
        return planes

    def input_for(self, frame, context):
        """The exact tensor ``process`` hands the net for this frame.

        Public because it is the seam the bit-identity check in
        ``tests/ball_stack_ab.py`` compares against the old input path.
        """
        return self.input_tensor(self._planes(frame, context))

    def input_tensor(self, planes):
        """The CNN input, assembled without a CPU-side stack copy or a float H2D copy.

        The previous path, per frame: concatenate three RGB planes into a
        ``960x540x9`` uint8 array (~4.7 MB), ``astype(np.float32)`` and ``/255``
        (~18.7 MB), ``transpose(2, 0, 1)`` + ``ascontiguousarray`` (another ~18.7 MB),
        then copy 18.7 MB of float32 to the device.  This path copies the three planes
        to the device as **uint8** (4.7 MB, and only one of the three actually
        changed), expands them to float32 in a resident device tensor, and divides in
        place.  Nothing is allocated per frame after the first.

        **The division goes through float64 on purpose.** The old path's values came
        from numpy, which divides ``float32(x) / 255.0`` with the scalar promoted to
        double: the quotient is rounded to double and only then to float32 (double
        rounding).  Torch on CUDA divides in float32 (single rounding) and disagrees
        with numpy on **126 of the 256 possible uint8 values**, by 1 ULP
        (~6e-8 at 0.5) - measured, not assumed, and it failed the bit-identity check
        the first time this path was written.  ``uint8 -> float64 -> /255 -> float32``
        reproduces numpy's rounding exactly on both devices, so the tensor the net
        sees is the tensor it saw before.  Same pixels, same RGB order, same float32
        division by 255 - the claim is only worth anything if it is measured
        element by element, which ``tests/ball_stack_ab.py`` does.
        """
        import numpy as np
        import torch
        height, width = self.size[1], self.size[0]
        shape = (self.stack, height, width, 3)
        if self._device_u8 is None or tuple(self._device_u8.shape) != shape:
            device = self._device
            self._device_u8 = torch.empty(shape, dtype=torch.uint8, device=device)
            self._device_in = torch.empty((1, self.stack * 3, height, width),
                                          dtype=torch.float32, device=device)
            self._device_f64 = torch.empty((1, self.stack * 3, height, width),
                                           dtype=torch.float64, device=device)
        for slot, plane in enumerate(planes):
            self._device_u8[slot].copy_(torch.from_numpy(np.ascontiguousarray(plane)))
        stacked = self._device_u8.permute(0, 3, 1, 2).reshape(1, self.stack * 3,
                                                              height, width)
        self._device_f64.copy_(stacked)      # uint8 -> float64, exact
        self._device_f64.div_(255.0)         # the same double-rounded quotient numpy had
        self._device_in.copy_(self._device_f64)   # float64 -> float32, one rounding
        return self._device_in

    def process(self, frame, context):
        import numpy as np
        from src.tiny_ball_net import pick_peaks

        self._load()
        height, width = frame.shape[:2]
        heat = np.asarray(self.heatmap(self.input_for(frame, context)))
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


@dataclass(frozen=True)
class Detector:
    """One detector the pipeline can run, and every way a caller may name it.

    ``name`` is the stage's own ``Stage.name`` and the detector's identity: two rows
    never share it, and ``spellings`` may hold more than one name for the same row.
    A caller that uses another spelling of an existing detector gets that detector -
    never a second implementation of it, and never silence.

    ``stage_class`` is the stage the live pipeline builds for this detector.
    ``frame_name`` is the spelling the per-frame route runs it under
    (``src/frame_inference.py``), so the two call paths can share one vocabulary
    while each keeps its own implementation.  ``build`` constructs the stage; every
    builder takes the same four values and ignores the ones its stage does not need.
    """

    name: str
    spellings: tuple
    stage_class: type
    frame_name: str
    build: object


def _build_table(root, _dataset, table_measure_every_n, _ball_every_n):
    return TableStage(root, dataset=_dataset, measure_every_n=table_measure_every_n)


def _build_person(root, _dataset, _table_measure_every_n, _ball_every_n):
    return PersonStage(root)


def _build_ball(root, _dataset, _table_measure_every_n, ball_every_n):
    return BallStage(root, every_n_frames=ball_every_n)


#: The detector vocabulary: one row per detector, one shared constant.
#: ``'balls'`` is the SAM3 spelling the per-frame route runs; ``'ball'`` is the
#: causal stage the live pipeline builds.  They are one detector in two spellings,
#: which is exactly what a caller could not tell before this table existed.
DETECTORS = (
    Detector('table', ('table',), TableStage, 'table', _build_table),
    Detector('person', ('person',), PersonStage, 'person', _build_person),
    Detector('ball', ('ball', 'balls'), BallStage, 'balls', _build_ball),
)


def detector_names():
    """Every accepted detector spelling, in table order."""
    return tuple(name for row in DETECTORS for name in row.spellings)


def resolve_detector(name):
    """The row ``name`` spells.  ``ValueError`` for a name outside the table."""
    for row in DETECTORS:
        if name in row.spellings:
            return row
    raise ValueError('unknown detector %r; accepted names: %s'
                     % (name, ', '.join(detector_names())))


def resolve_detectors(names):
    """The rows ``names`` asks for, one per detector, in pipeline order.

    A name the vocabulary knows resolves to its row; a name it does not know raises
    ``ValueError`` instead of being dropped.  Naming one detector twice - ``['ball',
    'balls']`` - resolves to one row, and the result follows the table, so the stage
    order never depends on the caller's list order.  ``[]`` resolves to ``()``.
    """
    if isinstance(names, str) or not hasattr(names, '__iter__'):
        raise ValueError('detectors must be a list of detector names, not %r' % (names,))
    wanted = {resolve_detector(name).name for name in names}
    return tuple(row for row in DETECTORS if row.name in wanted)


def frame_detectors(names):
    """The spellings ``src/frame_inference.py`` runs for a frame request, in request order.

    The per-frame route accepts every spelling of :data:`DETECTORS` and translates
    here before it calls ``infer_frame``, which knows only ``frame_name``: handed
    ``'ball'`` it matches no branch and returns silently as if nothing was requested.
    A request that is not a non-empty unique list of known spellings raises
    ``ValueError`` naming every accepted spelling.
    """
    if (isinstance(names, str) or not isinstance(names, (list, tuple)) or not names
            or any(not isinstance(name, str) for name in names)
            or len(set(names)) != len(names)):
        raise ValueError('detectors must be a nonempty unique list of %s'
                         % ', '.join(detector_names()))
    return [resolve_detector(name).frame_name for name in names]


def default_stages(detectors, root, dataset=None, table_measure_every_n=30, ball_every_n=1):
    """Registry for the live pipeline's detectors, in inference order (table first).

    :data:`DETECTORS` owns the names, and this factory builds one stage per detector
    ``detectors`` names, in table order.  A name the vocabulary does not know raises
    ``ValueError`` listing the accepted spellings - never a shorter pipeline: a run
    that quietly drops a detector it was asked for publishes frames that look
    complete and are not.  Both ball spellings build the one causal ball stage.

    ``dataset`` lets the table stage answer from that dataset's saved segment
    reference instead of measuring a static quad again on every frame; without it
    (a live stream) the stage measures on ``table_measure_every_n``'s cadence and
    labels the age of what it serves.

    ``ball`` appends the trained detector last (it is the most expensive stage, and a
    consumer reading box results in order should not wait behind it).  Its cadence is
    the caller's decision, so it is a parameter here exactly like the table's: the
    default runs it on every frame - the most accurate and most expensive setting -
    and the cost of each cadence under a real 30 fps source is measured in
    ``docs/live-processing-verification.md`` rather than guessed at here.
    """
    return [row.build(root, dataset, table_measure_every_n, ball_every_n)
            for row in resolve_detectors(detectors)]


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
