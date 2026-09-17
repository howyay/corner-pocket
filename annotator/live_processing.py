"""Bounded, latest-frame live inference. Receive age is NOT source latency.

Sources: {'kind': 'dataset', 'dataset': 'vod30' | 'highlight'} or
{'kind': 'twitch', 'source_id': <saved Operations channel id>}.
No caller-provided media URLs, files, stream credentials, or detector models.
"""
import copy
import json
import math
from pathlib import Path
import re
import threading
import time

from src.frame_inference import infer_frame


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
    """One decoder + one detector, one pending frame + one paired result.

    Injected capture_factory(media) returns an OpenCV-compatible capture;
    resolver(canonical_url) returns media; infer(frame, detectors, root) returns
    detections. A timed-out stop stays stopping and prevents overlapping starts.
    """

    def __init__(self, root, *, capture_factory=None, resolver=None, infer=None,
                 clock=time.monotonic, wall_clock=time.time, stop_timeout=2.0):
        self.root = Path(root).resolve()
        self._capture_factory = capture_factory or _capture
        self._resolver = resolver or _resolve_twitch
        self._infer = infer or infer_frame
        self._clock, self._wall_clock = clock, wall_clock
        self._stop_timeout = stop_timeout
        self._condition = threading.Condition(threading.RLock())
        self._decoder = self._worker = None
        self._generation = 0
        self._state = 'idle'
        self._source = None
        self._detectors = []
        self._error = None
        self._pending = self._latest = None
        self._received = self._processed = self._skipped = 0
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
            self._generation += 1
            generation = self._generation
            self._source, self._detectors = safe_source, list(dict.fromkeys(detectors))
            self._state, self._error = 'starting', None
            self._pending = self._latest = None
            self._received = self._processed = self._skipped = 0
            self._last_received = None
            self._done = False
            self._stop = threading.Event()
            self._decoder = threading.Thread(target=self._decode, args=(generation, media), daemon=True)
            self._worker = threading.Thread(target=self._process, args=(generation,), daemon=True)
            self._decoder.start()
            self._worker.start()
            return self.status()

    def _fail(self, generation, message):
        with self._condition:
            if generation == self._generation and not self._stop.is_set():
                self._state, self._error = 'error', message
                self._stop.set()
                if self._pending is not None:
                    self._skipped += 1
                    self._pending = None
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
            while not self._stop.is_set():
                if replay and self._stop.wait(max(0, deadline - self._clock())):
                    break
                ok, frame = capture.read()
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
                    self._received += 1
                    self._last_received = received_at
                    if self._pending is not None:
                        self._skipped += 1
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
                started = self._clock()
                # Bound live CPU cost; JPEG and detections share this resized coordinate space.
                source_height, source_width = frame.shape[:2]
                scale = min(1.0, 960 / source_width, 540 / source_height)
                if scale < 1:
                    frame = cv2.resize(frame, (max(1, round(source_width * scale)), max(1, round(source_height * scale))), interpolation=cv2.INTER_AREA)
                # Encode before inference so even an in-place detector cannot change the paired image.
                ok, jpeg = cv2.imencode('.jpg', frame)
                if not ok:
                    raise RuntimeError('JPEG encoding failed')
                inference_started = self._clock()
                detections = self._infer(frame, self._detectors, self.root)
                finished = self._clock()
                metadata = dict(seq=seq, detections=detections, received_at=received_at,
                                width=int(frame.shape[1]), height=int(frame.shape[0]),
                                source_width=int(source_width), source_height=int(source_height),
                                processed_at=self._wall_clock(),
                                receive_to_process_ms=max(0, started - received) * 1000,
                                receive_to_result_ms=max(0, finished - received) * 1000,
                                inference_ms=max(0, finished - inference_started) * 1000,
                                upstream_delay_ms=None)
                with self._condition:
                    if generation == self._generation and not self._stop.is_set():
                        self._processed += 1
                        self._latest = (jpeg.tobytes(), metadata, received)
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
                self._skipped += 1
                self._pending = None
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
                        upstream_delay_ms=None)

    def latest_jpeg(self):
        """Return (bytes, metadata) from the same sequence, or None before output."""
        with self._condition:
            return (self._latest[0], copy.deepcopy(self._latest[1])) if self._latest else None
