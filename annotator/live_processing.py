"""Bounded, latest-frame live inference. Receive age is NOT source latency.

Sources: {'kind': 'dataset', 'dataset': 'vod30' | 'highlight'} or
{'kind': 'twitch', 'source_id': <saved Operations channel id>}.
No caller-provided media URLs, files, stream credentials, or detector models.

Per-frame work is an ordered list of stages (:mod:`annotator.pipeline_stages`);
the decode loop never changes to add one.  Every step (decode, scale, encode,
each stage, receive-to-result) feeds a rolling latency window exposed on
``status()``, and a frame that misses the frame budget is dropped and counted
under its reason rather than published late or queued.
"""
import copy
import json
import math
from pathlib import Path
import re
import threading
import time

from annotator.pipeline_stages import (CallableStage, LatencyWindow, StageRegistry,
                                       default_stages, merge_detections)

_DROP_REASONS = ('no_frame_ready', 'stage_overrun', 'stale')


_DATASETS = {'vod30': 'vod_30min_260815.mp4', 'highlight': 'vod_highlight.mp4'}


class _SourceError(RuntimeError):
    pass


def _resolve_twitch(url):
    from annotator.twitch_source import TwitchSourceError, resolve_twitch
    try:
        return resolve_twitch(url)
    except TwitchSourceError as error:
        raise _SourceError(str(error)) from None


def _capture(media):
    import cv2
    return cv2.VideoCapture(media, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000,
    ])


class LiveProcessor:
    """One decoder + one ordered stage registry, one pending frame + one result.

    Injected capture_factory(media) returns an OpenCV-compatible capture;
    resolver(canonical_url) returns media; infer(frame, detectors, root) runs the
    historical single detector call, stages=[Stage(...)] replaces it with an
    ordered per-frame pipeline (see annotator/pipeline_stages.py; pass one of the
    two, not both). A timed-out stop stays stopping and prevents overlapping
    starts.

    ``frame_budget_ms`` is the whole-frame ceiling: unset means 1000/source fps
    (33.3 ms at 30 fps). ``budget_enforcement=False`` measures without dropping,
    for offline profiling only. A frame that overruns is dropped, counted under
    ``drop_reasons`` and reported in ``last_drop`` - never queued, never published
    late.
    """

    def __init__(self, root, *, capture_factory=None, resolver=None, infer=None, stages=None,
                 clock=time.monotonic, wall_clock=time.time, stop_timeout=2.0,
                 frame_budget_ms=None, budget_enforcement=True, latency_window=120):
        if infer is not None and stages is not None:
            raise ValueError('Pass either infer or stages, not both')
        self.root = Path(root).resolve()
        self._capture_factory = capture_factory or _capture
        self._resolver = resolver or _resolve_twitch
        self._infer = infer
        self._stage_spec = None if stages is None else list(stages)
        self._legacy_detector = False
        self._clock, self._wall_clock = clock, wall_clock
        self._stop_timeout = stop_timeout
        self._configured_budget = frame_budget_ms
        self._enforce_budget = bool(budget_enforcement)
        self._frame_budget_ms = frame_budget_ms
        self._latency = LatencyWindow(latency_window)
        self._registry = StageRegistry((), clock=clock)
        self._condition = threading.Condition(threading.RLock())
        self._decoder = self._worker = None
        self._generation = 0
        self._state = 'idle'
        self._source = None
        self._detectors = []
        self._error = None
        self._pending = self._latest = None
        self._received = self._processed = self._skipped = 0
        self._dropped = {reason: 0 for reason in _DROP_REASONS}
        self._last_drop = None
        self._previous_received = None
        self._last_received = None
        self._done = False
        self._stop = threading.Event()

    def _source_media(self, source):
        if not isinstance(source, dict):
            raise ValueError('source must be a dataset or saved Twitch channel object')
        if source.get('kind') == 'dataset' and set(source) == {'kind', 'dataset'}:
            name = source['dataset']
            if not isinstance(name, str) or name not in _DATASETS:
                raise ValueError('dataset must be vod30 or highlight')
            path = (self.root / 'data' / _DATASETS[name]).resolve()
            if not path.is_relative_to(self.root / 'data') or not path.is_file():
                raise ValueError('Allowlisted dataset media is unavailable')
            return dict(source), str(path)
        if source.get('kind') == 'twitch' and set(source) == {'kind', 'source_id'}:
            try:
                state = json.loads((self.root / 'out/corner-pocket/state.json').read_text())
            except (OSError, ValueError):
                raise ValueError('Saved Twitch channel is unavailable') from None
            saved = next((item for item in state.get('sources', [])
                          if item.get('id') == source['source_id'] and item.get('kind') == 'channel'), None)
            channel = saved.get('channel') if saved else None
            if not isinstance(channel, str) or not re.fullmatch(r'[a-z0-9_]{1,25}', channel):
                raise ValueError('Select a saved canonical Twitch channel')
            url = 'https://www.twitch.tv/' + channel
            if saved.get('url') != url:
                raise ValueError('Select a saved canonical Twitch channel')
            return {'kind': 'twitch', 'source_id': saved['id'], 'channel': channel}, url
        raise ValueError('Use an allowlisted dataset or saved Twitch source_id, not a URL')

    def start(self, source, detectors=None):
        detectors = ['table', 'person'] if detectors is None else detectors
        if (not isinstance(detectors, (list, tuple)) or not detectors or
                any(not isinstance(d, str) or d not in ('table', 'person') for d in detectors)):
            raise ValueError('Live detectors must be table and/or person; SAM balls are not supported')
        safe_source, media = self._source_media(source)
        with self._condition:
            if any(t and t.is_alive() for t in (self._decoder, self._worker)):
                raise RuntimeError('Previous live processing threads have not exited; stop and retry')
            self._detectors = list(dict.fromkeys(detectors))
            if self._stage_spec is not None:
                stages, self._legacy_detector = list(self._stage_spec), False
            elif self._infer is not None:
                stages = [CallableStage('detect', self._infer, self._detectors, self.root)]
                self._legacy_detector = True
            else:
                stages, self._legacy_detector = default_stages(self._detectors, self.root), False
            registry = StageRegistry(stages, clock=self._clock)
            self._generation += 1
            generation = self._generation
            self._source = safe_source
            self._state, self._error = 'starting', None
            self._pending = self._latest = None
            self._received = self._processed = self._skipped = 0
            self._dropped = {reason: 0 for reason in _DROP_REASONS}
            self._last_drop = None
            self._previous_received = None
            self._last_received = None
            self._frame_budget_ms = self._configured_budget
            self._latency = LatencyWindow(self._latency.size)
            self._registry = registry
            self._done = False
            self._stop = threading.Event()
            self._decoder = threading.Thread(target=self._decode, args=(generation, media), daemon=True)
            self._worker = threading.Thread(target=self._process, args=(generation,), daemon=True)
            self._decoder.start()
            self._worker.start()
            return self.status()

    def _drop(self, reason, seq, *, stage=None, ms=None, budget_ms=None):
        """Count one received frame as dropped, under exactly one reason.

        Reasons: ``no_frame_ready`` (the decoder superseded it in the pending slot
        before the worker took it), ``stage_overrun`` (a stage or the whole frame
        blew the budget), ``stale`` (abandoned without being published: already
        older than the frame budget at pickup, or dropped by stop/error).  The
        buckets partition ``frames_received`` together with ``frames_processed``.
        """
        with self._condition:
            self._dropped[reason] = self._dropped.get(reason, 0) + 1
            self._skipped += 1
            self._last_drop = dict(reason=reason, seq=seq, at=self._wall_clock(), stage=stage,
                                   ms=None if ms is None else round(ms, 2),
                                   budget_ms=None if budget_ms is None else round(budget_ms, 2))

    def _fail(self, generation, message):
        with self._condition:
            if generation == self._generation and not self._stop.is_set():
                self._state, self._error = 'error', message
                self._stop.set()
                if self._pending is not None:
                    dropped, self._pending = self._pending, None
                    self._drop('stale', dropped[0])
                self._condition.notify_all()

    def _decode(self, generation, media):
        capture = None
        try:
            import cv2
            replay = self._source['kind'] == 'dataset'
            if not replay:
                media = self._resolver(media)
            if self._stop.is_set():
                return
            capture = self._capture_factory(media)
            if not capture.isOpened():
                raise _SourceError('Could not open the selected media source')
            fps = float(capture.get(cv2.CAP_PROP_FPS)) if replay else 0
            fps = fps if math.isfinite(fps) and fps > 0 else 30.0
            deadline = self._clock()
            with self._condition:
                if not self._stop.is_set():
                    self._state = 'running'
                # The frame budget is the source's own frame period unless overridden.
                self._frame_budget_ms = self._configured_budget if self._configured_budget is not None else 1000.0 / fps
            while not self._stop.is_set():
                if replay and self._stop.wait(max(0, deadline - self._clock())):
                    break
                read_started = self._clock()
                ok, frame = capture.read()
                decoded = self._clock()
                self._latency.add('decode', (decoded - read_started) * 1000)
                if not ok:
                    if not replay:
                        self._fail(generation, 'Live stream ended or read timed out; restart to reconnect')
                    break
                if frame is None or len(frame.shape) != 3 or frame.shape[2] != 3 or not (0 < frame.shape[0] <= 2160 and 0 < frame.shape[1] <= 3840):
                    raise _SourceError('Decoded frame must be a color image no larger than 3840 × 2160')
                received, received_at = self._clock(), self._wall_clock()
                with self._condition:
                    if generation != self._generation or self._stop.is_set():
                        break
                    if self._previous_received is not None:
                        self._latency.add('inter_frame', (received - self._previous_received) * 1000)
                    self._previous_received = received
                    self._received += 1
                    self._last_received = received_at
                    if self._pending is not None:
                        self._drop('no_frame_ready', self._pending[0])
                    self._pending = (self._received, frame, received, received_at)
                    self._condition.notify_all()
                # Do not burst through a backlog after a decoder stall.
                deadline = max(deadline + 1 / fps, received)
        except _SourceError as exc:
            self._fail(generation, str(exc))
        except Exception:
            # Decoder/resolver exceptions can contain signed media URLs or credentials.
            self._fail(generation, 'Media resolution or decoding failed; check source availability')
        finally:
            try:
                if capture is not None:
                    capture.release()
            except Exception:
                self._fail(generation, 'Media decoder cleanup failed')
            finally:
                with self._condition:
                    if generation == self._generation:
                        self._done = True
                        self._condition.notify_all()

    def _process(self, generation):
        try:
            import cv2
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._stop.is_set() or self._pending is not None or self._done)
                    if self._stop.is_set() or generation != self._generation:
                        break
                    if self._pending is None:
                        break
                    seq, frame, received, received_at = self._pending
                    self._pending = None
                    budget_ms = self._frame_budget_ms if self._enforce_budget else None
                started = self._clock()
                if budget_ms is not None and (started - received) * 1000 > budget_ms:
                    # Older than a whole frame period at pickup: publishing it now
                    # would show a moment the decoder has already moved past.
                    self._drop('stale', seq)
                    continue
                # Bound live CPU cost; JPEG and stages share this resized coordinate space.
                source_height, source_width = frame.shape[:2]
                scale = min(1.0, 960 / source_width, 540 / source_height)
                if scale < 1:
                    frame = cv2.resize(frame, (max(1, round(source_width * scale)), max(1, round(source_height * scale))), interpolation=cv2.INTER_AREA)
                resized = self._clock()
                # Encode before inference so even an in-place stage cannot change the paired image.
                ok, jpeg = cv2.imencode('.jpg', frame)
                encoded = self._clock()
                if not ok:
                    raise RuntimeError('JPEG encoding failed')
                run = self._registry.run(frame, elapsed_ms=max(0, encoded - received) * 1000,
                                         frame_budget_ms=budget_ms, seq=seq, source=self._source)
                finished = self._clock()
                self._latency.add('resize', (resized - started) * 1000)
                self._latency.add('encode', (encoded - resized) * 1000)
                for name, elapsed in run.timings_ms.items():
                    self._latency.add(name, elapsed)
                self._latency.add('receive_to_process', (started - received) * 1000)
                self._latency.add('receive_to_result', (finished - received) * 1000)
                if run.overrun_stage is not None:
                    self._drop('stage_overrun', seq, stage=run.overrun_stage, ms=run.overrun_ms,
                               budget_ms=run.budget_ms)
                    continue
                detections = run.results.get('detect') if self._legacy_detector else \
                    merge_detections(run.results, self._detectors)
                metadata = dict(seq=seq, detections=detections, received_at=received_at,
                                width=int(frame.shape[1]), height=int(frame.shape[0]),
                                source_width=int(source_width), source_height=int(source_height),
                                processed_at=self._wall_clock(),
                                receive_to_process_ms=max(0, started - received) * 1000,
                                receive_to_result_ms=max(0, finished - received) * 1000,
                                inference_ms=run.total_ms,
                                stage_ms={name: round(elapsed, 2) for name, elapsed in run.timings_ms.items()},
                                upstream_delay_ms=None)
                published = False
                with self._condition:
                    if generation == self._generation and not self._stop.is_set():
                        self._processed += 1
                        self._latest = (jpeg.tobytes(), metadata, received)
                        published = True
                if not published and generation == self._generation:
                    self._drop('stale', seq)
        except Exception:
            self._fail(generation, 'Frame inference or JPEG encoding failed; check local detector weights and runtime')
        finally:
            with self._condition:
                if generation == self._generation and self._state != 'error':
                    self._state = 'stopping' if self._stop.is_set() else 'eos'

    def stop(self):
        with self._condition:
            self._stop.set()
            if self._state != 'idle':
                self._state = 'stopping'
            if self._pending is not None:
                dropped, self._pending = self._pending, None
                self._drop('stale', dropped[0])
            self._condition.notify_all()
            threads = (self._decoder, self._worker)
        deadline = time.monotonic() + self._stop_timeout
        for thread in threads:
            if thread is not None:
                thread.join(max(0, deadline - time.monotonic()))
        return self.status()

    def status(self):
        with self._condition:
            decoder_alive = bool(self._decoder and self._decoder.is_alive())
            worker_alive = bool(self._worker and self._worker.is_alive())
            if self._state == 'stopping' and not decoder_alive and not worker_alive:
                self._state = 'stopped'
            latest = copy.deepcopy(self._latest[1]) if self._latest else None
            return dict(state=self._state, generation=self._generation, source=copy.deepcopy(self._source),
                        detectors=list(self._detectors), error=self._error,
                        decoder_alive=decoder_alive, worker_alive=worker_alive,
                        frames_received=self._received, frames_processed=self._processed,
                        frames_skipped=self._skipped, last_received_at=self._last_received,
                        latest=latest, frame_age_ms=max(0, self._clock() - self._latest[2]) * 1000 if self._latest else None,
                        upstream_delay_ms=None,
                        # Additive: per-stage rolling latency in registry order, the
                        # same window for the non-stage steps, and why frames went.
                        stages=[dict(name=stage.name, budget_ms=stage.budget_ms,
                                     **self._latency.summary(stage.name)) for stage in self._registry],
                        latency_ms=self._latency.snapshot(),
                        drop_reasons=dict(self._dropped), last_drop=copy.deepcopy(self._last_drop),
                        frame_budget_ms=self._frame_budget_ms, budget_enforcement=self._enforce_budget,
                        latency_window=self._latency.size)

    def latest_jpeg(self):
        """Return (bytes, metadata) from the same sequence, or None before output."""
        with self._condition:
            return (self._latest[0], copy.deepcopy(self._latest[1])) if self._latest else None
