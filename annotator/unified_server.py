#!/usr/bin/env python3
"""One-origin review API. Run: python3 annotator/unified_server.py --port 8130.

Only allowlisted dataset/media files are exposed. Optional OpenCV and the seed
model are imported on demand, never while importing this HTTP module.
"""
import argparse
import base64
import binascii
from collections import OrderedDict
import json
import math
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATASETS = {"vod30": ("scan30", "vod_30min_260815.mp4"),
            "highlight": ("scan_highlight", "vod_highlight.mp4")}
BALL_SETS = ("unlabeled_crops", "unlabeled_crops2", "vod30_event_crops")
# Enroll image guard: dispatch caps POST bodies at 64KB, but the backend method
# is also callable directly (tests, larger transports), so bound the decoded image.
_MAX_ENROLL_BYTES = 8 * 1024 * 1024


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def atomic_save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def number(value, low, high, name):
    if isinstance(value, bool):
        raise APIError(f"invalid {name}")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise APIError(f"invalid {name}")
    if not math.isfinite(value) or not low <= value <= high:
        raise APIError(f"{name} must be finite and within {low}..{high}")
    return value


def _number(value, name, allow_none=False):
    if value is None:
        if allow_none:
            return None
        raise APIError(f"invalid {name}")
    return number(value, -1e9, 1e9, name)


def safe_file(base, name):
    if not name or Path(name).name != name or name in (".", ".."):
        raise APIError("invalid media path", 404)
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise APIError("media not found", 404)
    return path


class Backend:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.out = self.root / "out"
        self.lock = threading.RLock()
        self.job = {"status": "idle", "error": None}
        self.inference_jobs = {}
        self.inference_busy = False
        self.video_cache = {}
        self._clip_semaphore = threading.Semaphore(2)
        self._operations = None
        self._live = None
        self._identity_pipeline = None
        self._identity_error = None
        self._identity_lock = threading.Lock()
        self._unified_cache = OrderedDict()

    def live_processor(self):
        with self.lock:
            if self._live is None:
                from annotator.live_processing import LiveProcessor
                self._live = LiveProcessor(self.root)
            return self._live

    def close(self):
        if self._live is not None:
            self._live.stop()

    def live_action(self, payload):
        action = payload.get("action")
        if action not in ("start", "stop"):
            raise APIError("action must be start or stop")
        allowed = {"action", "source", "detectors"} if action == "start" else {"action"}
        if set(payload) - allowed:
            raise APIError("unsupported live option")
        try:
            processor = self.live_processor()
            return processor.start(payload.get("source"), payload.get("detectors")) if action == "start" else processor.stop()
        except ValueError as exc:
            raise APIError(str(exc)) from exc
        except RuntimeError as exc:
            raise APIError(str(exc), 409) from exc

    def operations(self):
        # Keep operations optional until requested; annotation-only fixtures remain usable.
        with self.lock:
            if self._operations is None:
                from annotator.operations import Operations
                self._operations = Operations(self.root)
            return self._operations

    # -- identity pipeline (constructed lazily on first identity API use) ----

    _PERSON_FIELDS = ("track_id", "bbox", "cluster_id", "player_id", "face_sim", "bound_evidence")

    def identity_pipeline(self):
        """Construct the PersonPipeline once. Defaults load real YOLO/OSNet/
        buffalo_l weights on first use, not here, but a construction failure
        (missing model files -> RuntimeError) is cached: later requests fail
        fast with 503 instead of retrying the load."""
        if self._identity_pipeline is not None:
            return self._identity_pipeline
        with self.lock:
            if self._identity_error is not None:
                raise APIError(f"identity models unavailable: {self._identity_error}", 503)
            if self._identity_pipeline is None:
                try:
                    from src.person_pipeline import PersonPipeline
                    self._identity_pipeline = PersonPipeline(self.root)
                except RuntimeError as exc:
                    self._identity_error = str(exc)
                    raise APIError(f"identity models unavailable: {exc}", 503) from exc
            return self._identity_pipeline

    def identity_frame(self, dataset, frame_index):
        """Run the person pipeline on one decoded VOD frame.

        Stateful: the tracker and identity index persist across requests, so
        frames must be processed in ascending order for meaningful tracks.
        Re-requesting a frame is safe — it is simply processed again and the
        tracker dedups by track continuity. Pipeline calls are serialized with
        a dedicated lock (the pipeline itself is single-threaded).
        """
        frame, meta = self.decode_frame(dataset, frame_index)
        try:
            with self._identity_lock:
                result = self.identity_pipeline().process_frame(
                    frame, meta["frame_index"], meta["timestamp_seconds"])
        except RuntimeError as exc:
            raise APIError(f"identity models unavailable: {exc}", 503) from exc
        return {"frame_index": meta["frame_index"],
                "timestamp_seconds": meta["timestamp_seconds"],
                "timestamp_kind": meta["timestamp_kind"],
                "persons": [{key: person[key] for key in self._PERSON_FIELDS}
                            for person in result["persons"]],
                "events": result["events"]}

    def identity_enroll(self, payload):
        """Enroll a face image (base64-encoded bytes) for a player id."""
        player_id = payload.get("player_id")
        if not isinstance(player_id, str) or not player_id.strip():
            raise APIError("player_id must be a non-empty string")
        encoded = payload.get("image_base64")
        if not isinstance(encoded, str):
            raise APIError("image_base64 must be a base64 string")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise APIError("image_base64 is not valid base64") from exc
        if len(raw) > _MAX_ENROLL_BYTES:
            raise APIError("image_base64 decodes past the 8MB limit")
        import numpy as np
        import cv2
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise APIError("image_base64 is not a decodable image")
        try:
            with self._identity_lock:
                enrolled = self.identity_pipeline().enroll_face(player_id, image)
        except RuntimeError as exc:
            raise APIError(f"identity models unavailable: {exc}", 503) from exc
        return {"enrolled": enrolled, "player_id": player_id}

    def identity_status(self):
        pipeline = self.identity_pipeline()
        try:
            with self._identity_lock:
                identity = pipeline.identity
                clusters = list(identity.clusters())
                states = {cluster: identity.get(cluster) for cluster in clusters}
                tracks = len(pipeline._tracks)
        except RuntimeError as exc:
            raise APIError(f"identity models unavailable: {exc}", 503) from exc
        return {"tracks": tracks, "clusters": len(clusters),
                "bound": [{"cluster_id": cluster, "player_id": state["player_id"]}
                          for cluster, state in states.items() if state["player_id"] is not None]}

    def identity_seed(self, payload):
        cluster_id = payload.get("cluster_id")
        player_id = payload.get("player_id")
        if isinstance(cluster_id, bool) or not isinstance(cluster_id, int):
            raise APIError("cluster_id must be an integer")
        if not isinstance(player_id, str) or not player_id.strip():
            raise APIError("player_id must be a non-empty string")
        try:
            with self._identity_lock:
                self.identity_pipeline().explicit_seed(cluster_id, player_id)
        except RuntimeError as exc:
            raise APIError(f"identity models unavailable: {exc}", 503) from exc
        return {"seeded": True}

    # -- unified viewer: one overlay payload per frozen frame ---------------

    _UNIFIED_CACHE_MAX = 24

    def unified(self, dataset, frame_index):
        """Everything the unified viewer overlays on one decoded frame: table
        quad, ball candidates, pockets via inverse homography, persons with
        cluster/player identity, and info-complete events near the frame time.
        Detection is cached per (dataset, frame); identity degrades to
        persons=[] with a persons_error note when its models are missing."""
        meta = self.frame_metadata(dataset, frame_index)
        index = meta['frame_index']
        frame, meta = self.decode_frame(dataset, index)
        corners, balls = self._unified_detection(dataset, index, frame)
        persons, persons_error = self._unified_persons(frame, index, meta['timestamp_seconds'])
        return {'frame_index': index,
                'timestamp_seconds': meta['timestamp_seconds'],
                'timestamp_kind': meta['timestamp_kind'],
                'width': meta['width'], 'height': meta['height'],
                'table_corners': corners,
                'table_quad': self._unified_quad(dataset, index),
                'balls': balls,
                'pockets': self._unified_pockets(corners),
                'persons': persons,
                'persons_error': persons_error,
                'events': self._unified_events(dataset, meta['timestamp_seconds'])}

    def _prior_for(self, dataset):
        """Table geometry the app path searches around for a dataset, or None.

        Resolved by ``src.frame_inference.app_prior_for``: the dataset's hand-placed
        anchors when it has them (the geometry this viewer clears the quad against,
        so the detection and the check describe the same boundary), else None - the
        refinement-derived reference ``out/corners_30min_v2.json`` is a measured-bad
        seed and is never searched around again (docs/app-path-refusal.md).  Cached
        per dataset: the reference is a file on disk and the viewer asks for it on
        every unified frame.  A missing or unreadable reference returns None rather
        than raising - the detector then falls back to the naive quad.
        """
        cache = getattr(self, '_prior_cache', None)
        if cache is None:
            cache = self._prior_cache = {}
        if dataset in cache:
            return cache[dataset]
        try:
            from src.frame_inference import app_prior_for
            value = app_prior_for(dataset, root=self.root)
        except Exception:
            value = None
        cache[dataset] = value
        return value

    def _unified_detection(self, dataset, frame_index, frame):
        """Table quad + ball candidates in full-res frame pixels. Detection
        runs on a 2x-downscaled copy (candidates, corners, homography live in
        that space during scans) and scales results back; an LRU keyed by
        (dataset, frame) keeps scrubbing cheap."""
        key = (dataset, frame_index)
        with self.lock:
            cached = self._unified_cache.get(key)
            if cached is not None:
                self._unified_cache.move_to_end(key)
                return cached['corners'], cached['balls']
        import cv2
        import numpy as np
        from src.table_detect import detect_table
        from src.frame_inference import (app_prior_source, detect_table_for_frame,
                                         table_quad_note)
        from src.ball_detect import detect_ball_candidates
        scale = 2.0
        small = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2), interpolation=cv2.INTER_AREA)
        # The cloth-boundary detector needs a static-camera prior for this dataset;
        # the prior is a full-res quad, so the search centre is scaled into the
        # detection space.  Without one (or when the refinement is refused) the
        # naive detect_table call is what runs - the same function, and the same
        # seam, the callers and tests already patch, including the mask the ball
        # candidates are filtered with.
        saved = self._prior_for(dataset)
        refused = None
        if saved is None:
            table = detect_table(small)
        else:
            prior = np.asarray(saved, np.float32) / scale
            refined = detect_table_for_frame(small, prior=prior)
            if refined.get('corners') is None:
                table = detect_table(small)
                refused = refined
            else:
                table = refined
        # The operator cannot see why a frame has no quad unless the reason travels
        # with the payload: corners=null alone is a silent absence.  Additive field,
        # localized in the viewer.
        note = table_quad_note(table, seed_file=app_prior_source(dataset, root=self.root),
                               refused=refused)
        corners, balls = None, []
        if table.get('corners') is not None:
            quad = np.asarray(table['corners'], np.float32) * scale
            corners = [[round(float(x), 1), round(float(y), 1)] for x, y in quad]
            balls = [{'cx': round(c['cx'] * scale, 1), 'cy': round(c['cy'] * scale, 1),
                      'r': round(c['r'] * scale, 1), 'color': c['color']}
                     for c in detect_ball_candidates(small, table.get('mask'))]
        with self.lock:
            cache = self._unified_cache
            cache[key] = {'corners': corners, 'balls': balls, 'quad': note}
            cache.move_to_end(key)
            while len(cache) > self._UNIFIED_CACHE_MAX:
                cache.popitem(last=False)
        return corners, balls

    def _unified_quad(self, dataset, frame_index):
        """Refusal/acceptance note for the last ``_unified_detection`` call.

        Additive payload field (``table_quad``): a refused frame used to reach the
        viewer as ``table_corners: null`` with no reason at all
        (docs/app-path-refusal.md).  Read from the detection cache, so it describes
        the exact result the payload's corners came from.
        """
        with self.lock:
            cached = self._unified_cache.get((dataset, frame_index))
            return None if cached is None else cached.get('quad')

    def _unified_pockets(self, corners):
        """Six physical pockets mapped back to frame pixels through the inverse
        table homography. POCKETS_MM is the canonical-millimeter geometry the
        event scan uses; a homography or import failure yields no pockets."""
        if not corners:
            return []
        try:
            import numpy as np
            from src.pipeline import homography_to_canonical
            from src.scan_events import POCKETS_MM
            inverse = np.linalg.inv(homography_to_canonical(np.array(corners, np.float32)))
            points = []
            for name, (mm_x, mm_y) in POCKETS_MM.items():
                x, y, w = inverse @ np.array([float(mm_x), float(mm_y), 1.0])
                points.append({'name': name, 'cx': round(float(x / w), 1), 'cy': round(float(y / w), 1)})
            return points
        except Exception:
            return []

    def _unified_persons(self, frame, frame_index, timestamp):
        """Identity overlay degrades instead of failing the frame: missing
        models return ([], note) so balls/table/pockets stay reviewable."""
        try:
            with self._identity_lock:
                result = self.identity_pipeline().process_frame(frame, frame_index, timestamp)
            return [{key: person.get(key) for key in self._PERSON_FIELDS}
                    for person in result['persons']], None
        except Exception as exc:
            return [], f'identity unavailable: {exc}'

    def _unified_events(self, dataset, timestamp):
        """Info-complete scan candidates within ±3s of the frame time."""
        window = []
        for event in load(self.dataset(dataset) / 'events.json', []):
            if isinstance(event.get('t'), (int, float)) and abs(event['t'] - timestamp) <= 3.0:
                window.append(event)
        return window

    def dataset(self, dataset):
        if dataset not in DATASETS:
            raise APIError("unknown dataset", 404)
        return self.out / DATASETS[dataset][0]

    def crops(self, name):
        if name not in BALL_SETS:
            raise APIError("unknown ball set", 404)
        return self.out / name

    def video(self, dataset):
        self.dataset(dataset)
        return safe_file(self.root / "data", DATASETS[dataset][1])

    def frame(self, t, dataset="vod30"):
        import cv2
        cap = cv2.VideoCapture(str(self.video(dataset)))
        try:
            if not cap.isOpened():
                raise APIError("cannot open VOD", 503)
            fps = cap.get(cv2.CAP_PROP_FPS)
            count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if not fps or not count:
                raise APIError("cannot read VOD metadata", 503)
            t = number(t, 0, (count - 1) / fps, "t")
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                raise APIError("cannot decode frame", 503)
            return frame
        finally:
            cap.release()

    def frame_jpeg(self, t, dataset="vod30"):
        import cv2
        ok, buf = cv2.imencode(".jpg", self.frame(t, dataset))
        if not ok:
            raise APIError("cannot encode frame", 503)
        return buf.tobytes()

    def video_metadata(self, dataset):
        path = self.video(dataset)
        import cv2
        stamp = (path.stat().st_mtime_ns, path.stat().st_size)
        with self.lock:
            cached = self.video_cache.get(dataset)
            if cached and cached[0] == stamp:
                return dict(cached[1])
        cap = cv2.VideoCapture(str(path))
        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if not cap.isOpened() or not math.isfinite(fps) or fps <= 0 or count <= 0 or min(width, height) <= 0:
                raise APIError('video metadata unavailable', 422)
            meta = dict(dataset=dataset, fps=fps, frame_count=count, duration=count/fps,
                        width=width, height=height, timestamp_kind='nominal_cfr')
            with self.lock:
                self.video_cache[dataset] = (stamp, meta)
            return dict(meta)
        finally:
            cap.release()

    def frame_metadata(self, dataset, frame_index):
        meta = self.video_metadata(dataset)
        value = number(frame_index, 0, meta['frame_count'] - 1, 'frame_index')
        if not value.is_integer():
            raise APIError('frame_index must be an integer')
        return dict(dataset=dataset, frame_index=int(value), timestamp_seconds=value/meta['fps'],
                    timestamp_kind='nominal_cfr', width=meta['width'], height=meta['height'])

    def decode_frame(self, dataset, frame_index):
        meta = self.frame_metadata(dataset, frame_index)
        import cv2
        cap = cv2.VideoCapture(str(self.video(dataset)))
        try:
            if not cap.set(cv2.CAP_PROP_POS_FRAMES, meta['frame_index']):
                raise APIError('frame seek failed', 422)
            ok, frame = cap.read()
            if not ok:
                raise APIError('frame decode failed', 422)
            meta.update(width=frame.shape[1], height=frame.shape[0])
            return frame, meta
        finally:
            cap.release()

    def indexed_jpeg(self, dataset, frame_index):
        import cv2
        frame, meta = self.decode_frame(dataset, frame_index)
        ok, image = cv2.imencode('.jpg', frame)
        if not ok:
            raise APIError('JPEG encoding failed', 500)
        return image.tobytes(), meta

    def frame_path(self, dataset, frame_index, kind):
        return self.dataset(dataset) / 'frame_results' / str(frame_index) / (kind + '.json')

    @staticmethod
    def _ffmpeg():
        import shutil
        found = shutil.which('ffmpeg')
        if found:
            return found
        from pathlib import Path as _P
        candidates = [p for p in _P('/nix/store').glob('*-ffmpeg-headless-*-bin/bin/ffmpeg') if p.is_file()]
        if candidates:
            return str(max(candidates, key=lambda p: p.stat().st_mtime))
        raise APIError('ffmpeg is unavailable on this host', 503)

    def event_clip(self, dataset, t, before, after):
        """Real short H.264 fragment around the event time, cached and bounded."""
        meta = self.video_metadata(dataset)
        if not isinstance(t, (int, float)) or isinstance(t, bool) or not math.isfinite(t) or not 0 <= t <= meta['duration']:
            raise APIError('t must be seconds inside the video')
        before = min(max(float(before if before is not None else 1.5), 0.25), 5.0)
        after = min(max(float(after if after is not None else 2.5), 0.25), 5.0)
        t0 = max(0.0, t - before)
        duration = min(before + after, meta['duration'] - t0)
        if duration < 0.2:
            raise APIError('clip window is empty at the end of the video')
        cache = self.out / 'clip-cache'
        cache.mkdir(parents=True, exist_ok=True)
        name = cache / f"{dataset}-{int(round(t * 1000))}-{round(before, 2)}-{round(after, 2)}.mp4"
        if not (name.exists() and name.stat().st_size > 0):
            source = self.video(dataset)
            with self._clip_semaphore:
                if not (name.exists() and name.stat().st_size > 0):
                    tmp = name.with_suffix('.part.mp4')
                    self._encode_clip(self._ffmpeg(), source, tmp, t0, duration)
                    tmp.replace(name)
            self._prune_clip_cache(cache)
        return name

    def _encode_clip(self, ffmpeg, source, destination, t0, duration):
        import subprocess
        command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-ss', f'{t0:.3f}',
                   '-i', str(source), '-t', f'{duration:.3f}',
                   '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                   '-vf', 'scale=960:-2', '-movflags', '+faststart', '-an', '-y', str(destination)]
        try:
            result = subprocess.run(command, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            raise APIError('clip encoding timed out', 504) from exc
        if result.returncode != 0 or not destination.exists() or destination.stat().st_size == 0:
            raise APIError('clip encoding failed', 500)

    @staticmethod
    def _prune_clip_cache(cache):
        clips = sorted(cache.glob('*.mp4'), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in clips[24:]:
            try:
                old.unlink()
            except OSError:
                pass

    def frame_result(self, dataset, frame_index):
        meta = self.frame_metadata(dataset, frame_index)
        index = meta['frame_index']
        return dict(meta, inference=load(self.frame_path(dataset, index, 'inference')),
                    correction=load(self.frame_path(dataset, index, 'correction')))

    def save_frame_correction(self, data):
        meta = self.frame_metadata(data.get('dataset'), data.get('frame_index'))
        width, height = meta['width'], meta['height']
        boxes = data.get('boxes', [])
        if not isinstance(boxes, list) or len(boxes) > 200:
            raise APIError('boxes must be a list with at most 200 entries')
        cleaned = []
        for box in boxes:
            if not isinstance(box, dict) or box.get('label') not in ('person', 'ball', 'cue', 'solid', 'stripe', 'eight'):
                raise APIError('invalid box label')
            coords = box.get('bbox')
            if not isinstance(coords, list) or len(coords) != 4:
                raise APIError('bbox must be [x1,y1,x2,y2]')
            x1, y1, x2, y2 = [number(v, 0, width if i % 2 == 0 else height, 'coordinate') for i, v in enumerate(coords)]
            if x2 <= x1 or y2 <= y1:
                raise APIError('box must have positive width and height')
            cleaned.append(dict(label=box['label'], bbox=[x1, y1, x2, y2], center=[(x1+x2)/2, (y1+y2)/2]))
        polygon = data.get('table_polygon')
        if polygon is not None:
            if not isinstance(polygon, list) or len(polygon) != 4:
                raise APIError('table_polygon must have four points')
            if any(not isinstance(p, list) or len(p) != 2 for p in polygon):
                raise APIError('invalid table point')
            polygon = [[number(p[0], 0, width, 'x'), number(p[1], 0, height, 'y')] for p in polygon]
            area = abs(sum(polygon[i][0]*polygon[(i+1)%4][1] - polygon[(i+1)%4][0]*polygon[i][1] for i in range(4)))
            if area <= 0:
                raise APIError('table_polygon must have nonzero area')
        correction = dict(meta, boxes=cleaned, table_polygon=polygon, source='manual', saved_at=now())
        with self.lock:
            atomic_save(self.frame_path(meta['dataset'], meta['frame_index'], 'correction'), correction)
        return dict(ok=True, correction=correction)

    def inference_status(self, dataset):
        self.dataset(dataset)
        with self.lock:
            return dict(self.inference_jobs.get(dataset, dict(dataset=dataset, status='idle')))

    def start_inference(self, data):
        meta = self.frame_metadata(data.get('dataset'), data.get('frame_index'))
        detectors = data.get('detectors', ['table', 'person'])
        if not isinstance(detectors, list) or not detectors or any(not isinstance(d, str) or d not in ('table', 'person', 'balls') for d in detectors) or len(set(detectors)) != len(detectors):
            raise APIError('detectors must be a nonempty unique list of table, person, balls')
        dataset = meta['dataset']
        job = dict(meta, detectors=detectors, status='running', stage='queued', error=None, started_at=now())
        with self.lock:
            if self.inference_busy:
                raise APIError('another frame inference job is running', 409)
            self.inference_busy = True
            self.inference_jobs[dataset] = job
        def progress(stage):
            with self.lock:
                job['stage'] = stage
        def work():
            try:
                from src.frame_inference import infer_frame
                progress('decoding selected frame')
                frame, decoded = self.decode_frame(dataset, meta['frame_index'])
                # ``dataset`` selects the app path's static-camera seed, so the
                # frozen-frame polygon comes from the same refinement the unified
                # overlay uses.  Without it this path saved the naive detector's
                # quad (131 px from the saved anchors at t=427.8 on vod30) and
                # app.js painted it.
                result = dict(infer_frame(frame, detectors, self.root, progress, dataset=dataset),
                              **decoded, source='inferred', saved_at=now())
                atomic_save(self.frame_path(dataset, meta['frame_index'], 'inference'), result)
                with self.lock:
                    job.update(status='completed', stage='completed', result=result)
            except Exception as exc:
                with self.lock:
                    job.update(status='failed', stage='failed', error=str(exc))
            finally:
                with self.lock:
                    job['finished_at'] = now()
                    self.inference_busy = False
        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception:
            with self.lock:
                self.inference_busy = False
                job.update(status='failed', stage='failed', error='could not start worker')
            raise
        with self.lock:
            return dict(job)

    def anchor_info(self, t):
        t = number(t, 0, 1800, "t")
        frame = self.frame(t)
        height, width = frame.shape[:2]
        saved = load(self.out / "pid_anchors_vod30.json", {"anchors": {}})
        points = next((v for k, v in saved["anchors"].items() if float(k) == t), None)
        suggested = None
        calib = load(self.out / "calib_vod30.json", {})
        if "H" in calib:
            # Same ordering as calibrate.OBJECT_MM: TL, TR, BR, BL, left/right side.
            from importlib import import_module
            sys.path.insert(0, str(self.root / "src"))
            module = import_module("calibrate")
            import numpy as np
            suggested = module.project(np.array(calib["H"]), module.OBJECT_MM).tolist()
        return {"t": t, "pts": points, "suggested_pts": suggested,
                "width": width, "height": height, "suggested_times": [70, 200, 350]}

    def event_frame(self, dataset, event_id):
        events = load(self.dataset(dataset) / "events.json", [])
        event = next((e for e in events if str(e["id"]) == str(event_id)), None)
        if event is None:
            raise APIError("unknown event", 404)
        return self.frame_jpeg(event["t"], dataset)

    def predictions(self):
        valid = {f'{tk["id"]}:{win}' for win, window in self.tracks().items() for tk in window["tracklets"]}
        labels = {key: seed["label"] for key, seed in self.seeds()["seeds"].items()
                  if key in valid and seed.get("label") in ("A", "B", "ignore")}
        prediction = load(self.out / "pid_seed_tracks.json", {})
        if not {"A", "B"}.issubset(set(labels.values())) or prediction.get("seed_labels") != labels:
            return {"map": {}, "detail": {}, "stale": True,
                    "reason": "Rebuild required with current explicit A and B seeds"}
        return dict(prediction, stale=False)

    def tracks(self):
        return load(self.out / "pid2_tracklets.json", {})

    def seeds(self):
        return load(self.out / "pid_seed.json", {"seeds": {}})

    def get(self, parts, query):
        if parts == ['api', 'operations']:
            return self.operations().get()
        dataset = query.get('dataset', ['vod30'])[0]
        frame_index = query.get('frame', [None])[0]
        if parts == ['api', 'identity', 'frame']:
            return self.identity_frame(dataset, frame_index)
        if parts == ['api', 'unified']:
            return self.unified(dataset, frame_index)
        if parts == ['api', 'identity', 'status']:
            return self.identity_status()
        if parts == ['api', 'video']:
            return self.video_metadata(dataset)
        if parts == ['api', 'frame-result']:
            return self.frame_result(dataset, frame_index)
        if parts == ['api', 'inference']:
            return self.inference_status(dataset)
        if parts == ["api", "datasets"]:
            return {"datasets": [{"id": k, "label": k} for k in DATASETS],
                    "ball_sets": [{"id": k, "label": k} for k in BALL_SETS]}
        if len(parts) == 4 and parts[:2] == ["api", "balls"] and parts[3] == "meta":
            base = self.crops(parts[2])
            labels = load(base / "labels.json", {})
            ctx = load(base / "ctx.json", {})
            items = []
            for row in load(base / "meta.json", []):
                item = dict(row, file=Path(row["file"]).name)
                item["ctx"] = Path(ctx[row["file"]]).name if ctx.get(row["file"]) else None
                items.append(item)
            return {"items": items, "labels": {Path(k).name: v for k, v in labels.items()}}
        if len(parts) != 3 or parts[0] != "api":
            raise APIError("route not found", 404)
        _, dataset, route = parts
        base = self.dataset(dataset)
        if route == "events":
            events = load(base / "events.json", [])
            actors = {}
            if dataset == "vod30":
                raw = load(self.out / "events_actors.json", [])
                for event in events:
                    match = next((a for a in raw if abs(a["t"] - event["t"]) < 0.01), None)
                    if match:
                        actors[str(event["id"])] = match
            return {"events": events, "annotations": load(base / "annotations.json", {}), "actors": actors}
        if dataset != "vod30":
            raise APIError("feature only available for vod30", 404)
        if route == "anchors":
            return self.anchor_info(query.get("t", [70])[0])
        if route == "seeds":
            return self.seeds()
        if route == "rebuild":
            with self.lock:
                return dict(self.job)
        if route == "tracklets":
            return {"windows": [{"win": win, "tracks": value["tracklets"]} for win, value in self.tracks().items()],
                    "seeds": self.seeds()["seeds"],
                    "predictions": self.predictions()}
        if route == "tracks":
            win = query.get("win", [""])[0]
            t = number(query.get("t", [None])[0], 0, 1800, "t")
            windows = self.tracks()
            if win not in windows:
                raise APIError("unknown window", 404)
            seeds = self.seeds()["seeds"]
            tracks = []
            for track in windows[win]["tracklets"]:
                if not track["samples"]:
                    continue
                tt, box = min(track["samples"], key=lambda sample: abs(sample[0] - t))
                if abs(tt - t) <= 1.1:
                    tracks.append({"id": track["id"], "box": box,
                                   "label": seeds.get(f'{track["id"]}:{win}', {}).get("label")})
            return {"win": win, "t": t, "tracks": tracks}
        raise APIError("route not found", 404)

    def post(self, parts, payload):
        if not isinstance(payload, dict):
            raise APIError("JSON object required")
        if parts == ['api', 'operations']:
            from annotator.operations import ConflictError
            try:
                return self.operations().post(payload)
            except ConflictError as error:
                raise APIError(str(error), 409) from error
            except ValueError as error:
                raise APIError(str(error)) from error
        if parts == ['api', 'inference']:
            return self.start_inference(payload)
        if parts == ['api', 'frame-correction']:
            return self.save_frame_correction(payload)
        if parts == ['api', 'identity', 'enroll']:
            return self.identity_enroll(payload)
        if parts == ['api', 'identity', 'seed']:
            return self.identity_seed(payload)
        with self.lock:
            return self._post(parts, payload)

    def _post(self, parts, p):
        if len(parts) == 4 and parts[:2] == ["api", "balls"] and parts[3] == "label":
            base = self.crops(parts[2])
            rows = load(base / "meta.json", [])
            row = next((r for r in rows if Path(r["file"]).name == p.get("file")), None)
            if row is None:
                raise APIError("unknown crop")
            if "label" not in p:
                raise APIError("label required; use null to clear")
            label = p["label"]
            if isinstance(label, bool) or not (label in (None, "u", "clear", -1, -2) or type(label) is int and 0 <= label <= 15):
                raise APIError("invalid ball label")
            labels = load(base / "labels.json", {})
            keys = [k for k in labels if Path(k).name == p["file"]]
            key = keys[0] if keys else row["file"]
            for old in keys:
                labels.pop(old)
            if label not in (None, "clear", -2):
                labels[key] = "u" if label == -1 else label
            atomic_save(base / "labels.json", labels)
            return {"ok": True}
        if len(parts) != 3 or parts[0] != "api":
            raise APIError("route not found", 404)
        _, dataset, route = parts
        base = self.dataset(dataset)
        if route == "annotate":
            key = str(p.get("event_id"))
            if not any(str(e["id"]) == key for e in load(base / "events.json", [])):
                raise APIError("unknown event")
            if "verdict" in p and p["verdict"] not in ("correct", "wrong", "unsure"):
                raise APIError("invalid verdict")
            if "shooter" in p and p["shooter"] not in ("A", "B", "?", ""):
                raise APIError("invalid shooter")
            if "note" in p and (not isinstance(p["note"], str) or len(p["note"]) > 10000):
                raise APIError("invalid note")
            annotations = load(base / "annotations.json", {})
            record = dict(annotations.get(key, {}))
            record.update({k: p[k] for k in ("verdict", "note", "shooter") if k in p})
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            annotations[key] = record
            atomic_save(base / "annotations.json", annotations)
            return {"ok": True, "annotation": record}
        if dataset != "vod30":
            raise APIError("feature only available for vod30", 404)
        if route == "anchors":
            info = self.anchor_info(p.get("t"))
            pts = p.get("pts")
            if not isinstance(pts, list) or len(pts) != 6:
                raise APIError("six anchor points required")
            clean = []
            for point in pts:
                if not isinstance(point, list) or len(point) != 2:
                    raise APIError("each anchor must be [x,y]")
                clean.append([number(point[0], 0, info["width"] - 1, "x"), number(point[1], 0, info["height"] - 1, "y")])
            path = self.out / "pid_anchors_vod30.json"
            saved = load(path, {"anchors": {}})
            key = next((k for k in saved["anchors"] if float(k) == info["t"]), str(info["t"]))
            saved["anchors"][key] = clean
            atomic_save(path, saved)
            return {"ok": True, "t": info["t"], "pts": clean}
        if route == "seeds":
            if self.job["status"] == "running":
                raise APIError("cannot edit seeds during rebuild", 409)
            win, tid = p.get("win"), p.get("track_id")
            if not isinstance(win, str) or type(tid) is not int:
                raise APIError("invalid window or track")
            window = self.tracks().get(win, {})
            track = next((tk for tk in window.get("tracklets", []) if tk["id"] == tid), None)
            if not track or not track["samples"]:
                raise APIError("unknown track")
            t = number(p.get("t"), min(s[0] for s in track["samples"]), max(s[0] for s in track["samples"]), "t")
            if "label" not in p or p["label"] not in ("A", "B", "ignore", None):
                raise APIError("explicit A/B/ignore label required")
            saved = self.seeds()
            key = f"{tid}:{win}"
            if p["label"] is None:
                saved["seeds"].pop(key, None)
            else:
                saved["seeds"][key] = dict(saved["seeds"].get(key, {}), win=win, t=t, track_id=tid, label=p["label"])
            atomic_save(self.out / "pid_seed.json", saved)
            return {"ok": True, "seeds": saved["seeds"]}
        if route == "rebuild":
            if self.job["status"] == "running":
                raise APIError("rebuild already running", 409)
            self.job = {"status": "running", "error": None}
            threading.Thread(target=self._rebuild, daemon=True).start()
            return dict(self.job)
        raise APIError("route not found", 404)

    def _rebuild(self):
        try:
            result = subprocess.run([sys.executable, str(self.root / "src" / "pid_seed_rebuild.py"), "--root", str(self.root)],
                                    capture_output=True, text=True, timeout=1800)
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout or f"exit {result.returncode}")[-4000:])
            with self.lock:
                self.job = {"status": "completed", "error": None, "output": result.stdout[-4000:]}
        except Exception as exc:
            with self.lock:
                self.job = {"status": "failed", "error": str(exc)}

    def media(self, parts):
        if len(parts) == 4 and parts[:2] == ["media", "balls"]:
            base = self.crops(parts[2])
            allowed = {Path(r["file"]).name for r in load(base / "meta.json", [])}
            if parts[3] not in allowed:
                raise APIError("unknown crop", 404)
            return safe_file(base, parts[3])
        if len(parts) == 5 and parts[:2] == ["media", "balls"] and parts[3] == "ctx":
            base = self.crops(parts[2])
            allowed = {Path(v).name for v in load(base / "ctx.json", {}).values() if v}
            if parts[4] not in allowed:
                raise APIError("unknown context", 404)
            return safe_file(base / "ctx", parts[4])
        if len(parts) == 4 and parts[0] == "media" and parts[2] == "evidence":
            base = self.dataset(parts[1])
            allowed = {e.get("evidence") for e in load(base / "events.json", [])}
            if parts[3] not in allowed:
                raise APIError("unknown evidence", 404)
            return safe_file(base, parts[3])
        if len(parts) == 3 and parts[0] == "media" and parts[2] == "video":
            return self.video(parts[1])
        raise APIError("route not found", 404)


def make_handler(backend):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type="application/json", headers=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if not urlsplit(self.path).path.startswith('/media/'):
                # Application code/data changes on every deploy; stale browser
                # caches mixed old loaders with new endpoints and broke Vision.
                self.send_header('Cache-Control', 'no-store')
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def json(self, status, data):
            self.send(status, json.dumps(data, allow_nan=False).encode())

        def file(self, path):
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            header = self.headers.get("Range")
            if header:
                import re
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
                if not match or not any(match.groups()):
                    raise APIError("invalid byte range", 416)
                a, b = match.groups()
                if a:
                    start = int(a)
                    end = min(int(b), end) if b else end
                else:
                    start = max(0, size - int(b))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            if path.suffix != '.mp4':
                # Static app assets may change on every deploy; media benefits from local caching.
                self.send_header("Cache-Control", "no-store")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def dispatch(self, post=False):
            try:
                parsed = urlsplit(self.path)
                path = unquote(parsed.path)
                parts = path.strip("/").split("/")
                query = parse_qs(parsed.query)
                if post:
                    # Reject cross-origin browser writes; no permissive CORS headers.
                    origin = self.headers.get("Origin")
                    if origin and origin not in ("http://" + self.headers.get("Host", ""), "https://" + self.headers.get("Host", "")):
                        raise APIError("cross-origin write rejected", 403)
                    size = int(self.headers.get("Content-Length", "0"))
                    limit = 12 * 1024 * 1024 if parts[:3] == ["api", "identity", "enroll"] else 65536
                    if not 0 < size <= limit:
                        raise APIError("invalid request size", 413)
                    payload = json.loads(self.rfile.read(size))
                    if parts == ['api', 'live']:
                        if not isinstance(payload, dict):
                            raise APIError('object required')
                        return self.json(200, backend.live_action(payload))
                    return self.json(202 if parts == ['api', 'inference'] else 200, backend.post(parts, payload))
                if path in ('/app.html', '/ops.html'):
                    return self.send(308, b'', 'text/plain', {'Location': '/'})
                if path == '/api/review-template':
                    return self.json(200, {'html': (backend.root / 'annotator' / 'app.html').read_text()})
                if path == '/api/live':
                    return self.json(200, backend.live_processor().status())
                if path == '/api/live/frame':
                    frame = backend.live_processor().latest_jpeg()
                    if frame is None:
                        raise APIError('no live frame ready', 404)
                    raw, meta = frame
                    return self.send(200, raw, 'image/jpeg', {
                        'X-Live-Sequence': str(meta['seq']),
                        'X-Live-Metadata': json.dumps(meta, separators=(',', ':'), allow_nan=False)})
                if path == '/api/clip':
                    clip = backend.event_clip(query.get('dataset', ['vod30'])[0],
                                              _number(query.get('t', [None])[0], 't'),
                                              _number(query.get('before', [1.5])[0], 'before', allow_none=True),
                                              _number(query.get('after', [2.5])[0], 'after', allow_none=True))
                    return self.file(clip)
                if path == '/api/frame':
                    raw, meta = backend.indexed_jpeg(query.get('dataset', ['vod30'])[0], query.get('frame', [None])[0])
                    return self.send(200, raw, 'image/jpeg', {
                        'X-Frame-Index': str(meta['frame_index']),
                        'X-Timestamp-Seconds': str(meta['timestamp_seconds']),
                        'X-Timestamp-Kind': meta['timestamp_kind'],
                        'X-Frame-Width': str(meta['width']), 'X-Frame-Height': str(meta['height'])})
                if path in ("/favicon.svg", "/favicon-32.png", "/favicon-16.png", "/favicon.ico"):
                    return self.file(safe_file(backend.root / "annotator", path[1:]))
                if path in ("/", "/app.html", "/app.css", "/app.js", "/ops.html", "/ops.css", "/ops.js", "/vision-stage.js"): 
                    return self.file(safe_file(backend.root / "annotator", "ops.html" if path == "/" else path[1:]))
                if len(parts) == 4 and parts[0] == "media" and parts[2] == "event-frame":
                    return self.send(200, backend.event_frame(parts[1], parts[3]), "image/jpeg")
                if parts == ["media", "vod30", "frame"]:
                    return self.send(200, backend.frame_jpeg(query.get("t", [None])[0]), "image/jpeg")
                if parts[0] == "api":
                    return self.json(200, backend.get(parts, query))
                return self.file(backend.media(parts))
            except APIError as exc:
                self.json(exc.status, {"error": str(exc)})
            except (ValueError, TypeError, KeyError) as exc:
                self.json(400, {"error": str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                self.json(500, {"error": str(exc)})

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch(True)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8130)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    backend = Backend(args.root)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(backend))
    print(f"Unified annotator: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backend.close()
        server.server_close()


if __name__ == "__main__":
    main()
