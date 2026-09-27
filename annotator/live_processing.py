"""Bounded, latest-frame live inference. Receive age is NOT source latency.

Sources: {'kind': 'dataset', 'dataset': 'vod30' | 'highlight'} or
{'kind': 'twitch', 'source_id': <saved Operations channel id>}.
No caller-provided media URLs, files, stream credentials, or detector models.

Detectors: ``table``, ``person`` and ``ball`` (the trained tiny ball net).  The
``balls`` (SAM3) detector of the offline frame scan remains excluded - it is a
different, much more expensive measurement with no live stage.

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
                                       check_ball_weights, default_stages, merge_detections)

_DROP_REASONS = ('no_frame_ready', 'stage_overrun', 'stale')

#: Detectors a caller may ask for.  ``ball`` is the trained tiny ball net
#: (``annotator.pipeline_stages.BallStage``); the SAM3 ``balls`` detector is NOT
#: this one and is still excluded - it is a separate offline scan, not a live stage.
LIVE_DETECTORS = ('table', 'person', 'ball')


_DATASETS = {'vod30': 'vod_30min_260815.mp4', 'highlight': 'vod_highlight.mp4'}


class _SourceError(RuntimeError):
    pass


def _check_requested_ball(detectors, stages):
    """Refuse a start that asked for the ball detector but cannot run it.

    A requested detector whose stage is absent, or whose weights are missing, would
    otherwise produce a pipeline that runs, publishes frames and quietly contains no
    ball result at all - every downstream number would read as "the detector found
    nothing".  Raises ``ValueError`` naming the detector and, for weights, the full
    expected path.  An injected stage that brings its own weights (a test stub, the
    envelope harness) has no ``verify`` and is trusted as given.
    """
    if 'ball' not in detectors:
        return
    ball = next((stage for stage in stages if getattr(stage, 'name', None) == 'ball'), None)
    if ball is None:
        raise ValueError("Requested detector 'ball' has no stage in this pipeline; "
                         "pass a BallStage with stages= or drop it from detectors")
    verify = getattr(ball, 'verify', None)
    if not callable(verify):
        return
    try:
        verify()
    except FileNotFoundError as exc:
        raise ValueError("Requested detector 'ball' cannot run: %s" % exc) from None


def _resolve_twitch(url):
    from annotator.twitch_source import TwitchSourceError, resolve_twitch
    try:
        return resolve_twitch(url)
    except TwitchSourceError as error:
        raise _SourceError(str(error)) from None


def _capture(media, *, open_timeout_ms=5000, read_timeout_ms=2000):
    """OpenCV capture with explicit timeouts.

    The defaults suit a local file.  A live HLS stream needs a much larger read
    timeout: its segments arrive on the broadcaster's cadence (2-12 s), so a 2 s
    read deadline turns a normal segment gap into a decoder failure - measured on
    the owner's live channel as ``Live stream ended or read timed out`` after ~200 s
    (docs/live-processing-verification.md, 2026-09-26).
    """
    import cv2
    return cv2.VideoCapture(media, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, open_timeout_ms,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, read_timeout_ms,
    ])


def _fetch_playlist(media_url):
    """The live media playlist text (module-level so a test can stand in for the network)."""
    from annotator.twitch_source import playlist_text
    return playlist_text(media_url)


class _UpstreamDelayProbe:
    """Age of the live edge, from ``#EXT-X-PROGRAM-DATE-TIME`` + ``#EXTINF``.

    The media playlist is the only thing that says when the broadcast produced what we
    receive, so the probe reads it on a cadence and reports ``now - (newest segment start
    + its duration)``: how long ago the newest segment finished being produced.  Between
    refreshes the age keeps advancing (the segment's end is a fixed instant), which is what
    makes it usable per frame.

    It never invents a value: a playlist without ``PROGRAM-DATE-TIME``, a recording
    (``PLAYLIST-TYPE``/``ENDLIST``) or an unreachable playlist leaves ``delay_ms()`` None.
    ``PROGRAM-DATE-TIME`` is the broadcaster's encoder clock, so the number carries that
    clock's error - the status payload therefore labels it ``upstream_clock: 'broadcaster'``.
    Fetching is a plain GET; nothing here writes.
    """

    def __init__(self, media_url, *, fetch=None, clock=time.time, refresh_s=5.0):
        self.media_url = media_url
        self._fetch = fetch or _fetch_playlist
        self._clock = clock
        self.refresh_s = max(0.5, float(refresh_s))
        self._lag_s = None
        self._fetched_at = None
        self._newest_end = None

    def refresh(self):
        """Fetch and re-read the playlist; returns the current delay in ms or None."""
        now = self._clock()
        self._fetched_at = now
        try:
            text = self._fetch(self.media_url)
        except Exception:
            # Unreachable or unsafe playlist: say nothing rather than repeat an old number.
            self._lag_s = self._newest_end = None
            return None
        lag = _playlist_lag(text, now=now)
        if lag is None:
            self._lag_s = self._newest_end = None
            return None
        self._lag_s = lag['lag_s']
        self._newest_end = lag['newest_segment_end']
        return max(0.0, self._lag_s) * 1000.0

    def delay_ms(self):
        """Current delay, or None when the playlist cannot say."""
        if self._lag_s is None or self._fetched_at is None:
            return None
        return max(0.0, self._lag_s + (self._clock() - self._fetched_at)) * 1000.0

    def label(self):
        return 'broadcaster' if self._lag_s is not None else None


def _playlist_lag(text, *, now):
    from annotator.twitch_source import playlist_lag
    return playlist_lag(text, now=now)


class LiveProcessor:
    """One decoder + one ordered stage registry, one pending frame + one result.

    Injected capture_factory(media) returns an OpenCV-compatible capture;
    resolver(canonical_url) returns media; infer(frame, detectors, root) runs the
    historical single detector call, stages=[Stage(...)] replaces it with an
    ordered per-frame pipeline (see annotator/pipeline_stages.py; pass one of the
    two, not both). A timed-out stop stays stopping and prevents overlapping
    starts.

    Detectors are ``table``, ``person`` and ``ball``; ``ball`` is the trained tiny
    ball net and its weights are checked before anything starts, so a request that
    cannot run is refused with the expected path rather than served by a pipeline
    that silently omits the stage. ``ball_every_n`` is that stage's cadence, the
    same way ``table_measure_every_n`` is the table's.

    ``frame_budget_ms`` is the whole-frame ceiling: unset means 1000/source fps
    (33.3 ms at 30 fps). ``budget_enforcement=False`` measures without dropping,
    for offline profiling only. A frame that overruns is dropped, counted under
    ``drop_reasons`` and reported in ``last_drop`` - never queued, never published
    late.
    """

    def __init__(self, root, *, capture_factory=None, resolver=None, infer=None, stages=None,
                 clock=time.monotonic, wall_clock=time.time, stop_timeout=2.0,
                 frame_budget_ms=None, budget_enforcement=True, latency_window=120,
                 table_measure_every_n=30, ball_every_n=1, live_read_timeout_ms=20000,
                 upstream_refresh_s=5.0):
        if infer is not None and stages is not None:
            raise ValueError('Pass either infer or stages, not both')
        self.root = Path(root).resolve()
        # callable returning the operations document (the server sets its store's
        # ops_get); None = read out/corner-pocket/state.json, as before
        self.operations_document = None
        self._capture_factory = capture_factory or _capture
        self._default_capture = capture_factory is None
        self._live_read_timeout_ms = live_read_timeout_ms
        self._resolver = resolver or _resolve_twitch
        self._infer = infer
        self._stage_spec = None if stages is None else list(stages)
        self._legacy_detector = False
        self._table_measure_every_n = table_measure_every_n
        self._ball_every_n = ball_every_n
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
        self._stage_runs = {}
        self._stage_skips = {}
        self._stage_evidence = {}
        self._fps = None
        self._last_published = None
        self._upstream_probe = None
        self._upstream_delay_ms = None
        self._upstream_clock = None
        self._upstream_refresh_s = upstream_refresh_s
        self._probe_thread = None
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
                # the saved channel is in the operations document: the server's store
                # when one was given, else the state.json file under root
                state = (self.operations_document() if self.operations_document is not None
                         else json.loads((self.root / 'out/corner-pocket/state.json').read_text()))
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
                any(not isinstance(d, str) or d not in LIVE_DETECTORS for d in detectors)):
            raise ValueError('Live detectors must be table, person and/or ball; SAM balls are not supported')
        safe_source, media = self._source_media(source)
        with self._condition:
            if any(t and t.is_alive() for t in (self._decoder, self._worker, self._probe_thread)):
                raise RuntimeError('Previous live processing threads have not exited; stop and retry')
            requested = list(dict.fromkeys(detectors))
            if self._stage_spec is not None:
                stages, self._legacy_detector = list(self._stage_spec), False
            elif self._infer is not None:
                stages = [CallableStage('detect', self._infer, requested, self.root)]
                self._legacy_detector = True
            else:
                stages = default_stages(requested, self.root,
                                        dataset=safe_source.get('dataset') if safe_source.get('kind') == 'dataset' else None,
                                        table_measure_every_n=self._table_measure_every_n,
                                        ball_every_n=self._ball_every_n)
                self._legacy_detector = False
            # Before anything is mutated or started: a requested detector that cannot
            # run is a refused start, never a pipeline that quietly omits it.
            _check_requested_ball(requested, stages)
            self._detectors = requested
            registry = StageRegistry(stages, clock=self._clock)
            self._generation += 1
            generation = self._generation
            self._source = safe_source
            self._state, self._error = 'starting', None
            self._pending = self._latest = None
            self._received = self._processed = self._skipped = 0
            self._dropped = {reason: 0 for reason in _DROP_REASONS}
            self._last_drop = None
            self._stage_runs = {stage.name: 0 for stage in stages}
            self._stage_skips = {stage.name: 0 for stage in stages}
            self._stage_evidence = {stage.name: None for stage in stages}
            self._fps = None
            self._previous_received = None
            self._last_published = None
            self._upstream_probe = None
            self._upstream_delay_ms = None
            self._upstream_clock = None
            self._probe_thread = None
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

    def _probe_upstream(self, generation, probe):
        """Refresh the live-edge age on its own cadence, off the frame path.

        A playlist fetch is a network round trip; doing it in the decoder or the worker
        would stall frames, so it gets its own thread and only the *value* crosses back.
        """
        while not self._stop.is_set():
            delay = probe.refresh()
            with self._condition:
                if generation != self._generation or self._stop.is_set():
                    return
                # Publish the reading even when frames are not flowing, so status() reports
                # the current live-edge age; the worker refreshes it per received frame.
                self._upstream_delay_ms = delay
                self._upstream_clock = probe.label()
            if self._stop.wait(probe.refresh_s):
                return

    def _start_upstream_probe(self, generation, media):
        """Start the live-edge probe for a Twitch source; nothing for a replay.

        The playlist itself decides: a recording, a playlist without
        ``#EXT-X-PROGRAM-DATE-TIME`` or an unreachable one leaves the delay None, and only
        a live playlist with timing tags ever produces a number.
        """
        if self._source.get('kind') != 'twitch' or not isinstance(media, str):
            return None
        probe = _UpstreamDelayProbe(media, refresh_s=self._upstream_refresh_s)
        with self._condition:
            if self._stop.is_set() or generation != self._generation:
                return None
            self._upstream_probe = probe
            self._probe_thread = threading.Thread(target=self._probe_upstream,
                                                  args=(generation, probe), daemon=True)
            self._probe_thread.start()
        return probe

    def _decode(self, generation, media):
        capture = None
        try:
            import cv2
            replay = self._source['kind'] == 'dataset'
            if not replay:
                media = self._resolver(media)
            if self._stop.is_set():
                return
            capture = self._capture_factory(media) if not self._default_capture else _capture(
                media, read_timeout_ms=2000 if replay else self._live_read_timeout_ms)
            if not capture.isOpened():
                raise _SourceError('Could not open the selected media source')
            if not replay:
                # Live-edge age, measured in-process from the playlist's own timing tags.
                self._start_upstream_probe(generation, media)
            fps = float(capture.get(cv2.CAP_PROP_FPS)) if replay else 0
            fps = fps if math.isfinite(fps) and fps > 0 else 30.0
            deadline = self._clock()
            with self._condition:
                if not self._stop.is_set():
                    self._state = 'running'
                # The frame budget is the source's own frame period unless overridden.
                self._frame_budget_ms = self._configured_budget if self._configured_budget is not None else 1000.0 / fps
                self._fps = fps
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
                # The media position is what a per-segment calibration resolves against;
                # a live stream has none, so both stay None there.
                frame_index = None
                if replay:
                    try:
                        position = float(capture.get(cv2.CAP_PROP_POS_FRAMES))
                        frame_index = int(position) - 1 if position >= 1 else None
                    except Exception:
                        frame_index = None
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
                    self._pending = (self._received, frame, received, received_at, frame_index)
                    # A live decoder can outrun the source: ffmpeg drains the segments it has
                    # buffered at hundreds of frames per second, and an unconditional notify
                    # per frame then starves the worker in lock contention - measured on the
                    # live channel as 2.4 fps published with 1.1-1.9 s frame age while each
                    # frame cost 20 ms.  Publish the slot (always the newest frame) but wake
                    # the worker at most once per source frame period.
                    if replay or self._last_published is None or \
                            (received - self._last_published) >= 1.0 / fps:
                        self._last_published = received
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
                    seq, frame, received, received_at, frame_index = self._pending
                    self._pending = None
                    budget_ms = self._frame_budget_ms if self._enforce_budget else None
                    fps = self._fps
                started = self._clock()
                # The live-edge age is read per frame, at receive time, so a consumer can
                # pair a frame with the delay that applied when it arrived.  None unless a
                # live playlist with PROGRAM-DATE-TIME has actually answered.
                if self._upstream_probe is not None:
                    self._upstream_delay_ms = self._upstream_probe.delay_ms()
                    self._upstream_clock = self._upstream_probe.label()
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
                run = self._registry.run(
                    frame, elapsed_ms=max(0, encoded - received) * 1000, frame_budget_ms=budget_ms,
                    seq=seq, source=self._source, frame_index=frame_index,
                    time_s=frame_index / fps if frame_index is not None and fps else None)
                finished = self._clock()
                self._latency.add('resize', (resized - started) * 1000)
                self._latency.add('encode', (encoded - resized) * 1000)
                for name, elapsed in run.timings_ms.items():
                    self._latency.add(name, elapsed)
                self._latency.add('receive_to_process', (started - received) * 1000)
                self._latency.add('receive_to_result', (finished - received) * 1000)
                with self._condition:
                    for name in run.ran:
                        self._stage_runs[name] = self._stage_runs.get(name, 0) + 1
                    for name in run.skipped:
                        self._stage_skips[name] = self._stage_skips.get(name, 0) + 1
                    self._stage_evidence.update({name: copy.deepcopy(entry)
                                                 for name, entry in run.evidence.items()})
                if run.overrun_stage is not None:
                    self._drop('stage_overrun', seq, stage=run.overrun_stage, ms=run.overrun_ms,
                               budget_ms=run.budget_ms)
                    continue
                detections = run.results.get('detect') if self._legacy_detector else \
                    merge_detections(run.results, self._detectors)
                metadata = dict(seq=seq, detections=detections, received_at=received_at,
                                width=int(frame.shape[1]), height=int(frame.shape[0]),
                                source_width=int(source_width), source_height=int(source_height),
                                source_frame_index=frame_index,
                                processed_at=self._wall_clock(),
                                receive_to_process_ms=max(0, started - received) * 1000,
                                receive_to_result_ms=max(0, finished - received) * 1000,
                                inference_ms=run.total_ms,
                                stage_ms={name: round(elapsed, 2) for name, elapsed in run.timings_ms.items()},
                                # Per-frame provenance: which stages ran, which were
                                # skipped by cadence (evidence absent, not stale) and
                                # what each executed stage's result was made of.
                                stage_evidence=copy.deepcopy(run.evidence),
                                upstream_delay_ms=self._upstream_delay_ms,
                                upstream_clock=self._upstream_clock)
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
            threads = (self._decoder, self._worker, self._probe_thread)
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
                        upstream_delay_ms=self._upstream_delay_ms,
                        # Which clock that delay is measured on: the broadcaster's own,
                        # because #EXT-X-PROGRAM-DATE-TIME is stamped by its encoder.  None
                        # whenever there is no live playlist timing to read.
                        upstream_clock=self._upstream_clock,
                        # Additive: per-stage rolling latency in registry order, the
                        # same window for the non-stage steps, and why frames went.
                        # Each stage also carries its cadence, how often it actually
                        # ran and the provenance of its last result, so a consumer can
                        # tell measured from cached and a skipped frame from an empty one.
                        stages=[dict(name=stage.name, budget_ms=stage.budget_ms,
                                     every_n_frames=getattr(stage, 'every_n_frames', 1) or 1,
                                     runs=self._stage_runs.get(stage.name, 0),
                                     skips=self._stage_skips.get(stage.name, 0),
                                     evidence=copy.deepcopy(self._stage_evidence.get(stage.name)),
                                     **self._latency.summary(stage.name)) for stage in self._registry],
                        latency_ms=self._latency.snapshot(),
                        drop_reasons=dict(self._dropped), last_drop=copy.deepcopy(self._last_drop),
                        frame_budget_ms=self._frame_budget_ms, budget_enforcement=self._enforce_budget,
                        latency_window=self._latency.size, source_fps=self._fps)

    def latest_jpeg(self):
        """Return (bytes, metadata) from the same sequence, or None before output."""
        with self._condition:
            return (self._latest[0], copy.deepcopy(self._latest[1])) if self._latest else None
