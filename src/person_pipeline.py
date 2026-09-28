"""Person pipeline: detector -> OSNet re-ID -> cross-exit identity -> face binding.

Every model component is injectable; defaults load lazily so tests never touch
weights or downloads. Thresholds follow the measured calibrations in
docs/live-processing-verification.md: a face binds at >= 0.47 (the effective
bar = match_threshold 0.35 + margin 0.12; the runner-up must also trail by the
0.12 margin, enforced by best_match and now by bind_face as well — 0.35 alone
never binds); body (OSNet) cross-exit clustering is disabled by default —
measured same/cross-person OSNet cosine distributions overlap on this footage
(BODY_MATCH_THRESHOLD in src/person_identity.py).

Face-stage latency control (buffalo_l full-frame analyze is ~240ms warm, 75%
of the per-frame budget): analyze runs only when BOTH hold --
  1. the rounded person-box signature changed since the last analyze (static
     scenes hit the signature cache and skip analyze entirely), and
  2. this process_frame call is a stride boundary: every `face_stride`-th call
     (default 4, set in __init__).
Between strides the last quality-filtered face observations are reused. Faces
feed binding only (never per-frame tracking), so stale observations keep the
per-frame binding attempt unchanged (same thresholds, best_match still runs
whenever an unbound person has a quality face); fresh observations, and thus
most new bindings, arrive on stride frames. det_size stays 640 (median eye
~10px would not survive a smaller detector input).
"""
import os

import cv2
import numpy as np
from pathlib import Path
import torch

from src.face_id import DEFAULT_FACE_STORE, add_faces, get_face_engine, load_faces
from src.person_identity import IdentityIndex

# YOLO weights load weights-only: ultralytics reads this once, on its first import
# (lazy, in _get_detector); unset, it unpickles checkpoints freely (audit D-2).
os.environ.setdefault('ULTRALYTICS_SAFE_LOAD', '1')

_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)
_IOU_MATCH = 0.3
_MAX_AGE = 30
REPO = Path(__file__).resolve().parents[1]
DETECTOR_WEIGHTS_NAME = 'yolov8n.pt'


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _center_inside(box, person):
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return person[0] <= x <= person[2] and person[1] <= y <= person[3]


class PersonPipeline:
    def __init__(self, root, detector=None, body_encoder=None, face_engine=None, identity=None,
                 face_stride=4, store=None):
        self.root = Path(root)
        self.detector = detector
        self.body_encoder = body_encoder
        self._face_engine = face_engine
        # store: a src.store Store for the identity index and the face gallery; None =
        # the JSON files under root (the default, as always)
        self.store = store
        self.identity = identity or IdentityIndex(self.root / 'out' / 'identity' / 'clusters.json', store=store)
        repo = Path(__file__).resolve().parents[1]
        self.face_store = self.root / Path(DEFAULT_FACE_STORE).relative_to(repo)
        self._gallery = None
        self._tracks = {}
        self._next_id = 1
        self.face_stride = max(1, int(face_stride))
        self._calls = 0
        self._last_analyze = -self.face_stride
        self._face_sig = None
        self._face_obs = []

    def detector_weights(self):
        """Local path of the person detector weights; never a download.

        ultralytics answers a missing weights *path* by fetching the release
        asset from GitHub, which would turn any root that forgot the file into a
        silent 6 MB network dependency (a scratch fixture root, a server started
        from the wrong directory). src/frame_inference.py already refuses to
        download; this mirrors it: root-local weights first, then the repo-local
        copy, otherwise a RuntimeError naming both expected paths.
        """
        candidates = [self.root / DETECTOR_WEIGHTS_NAME, REPO / DETECTOR_WEIGHTS_NAME]
        for path in candidates:
            if path.is_file():
                return path
        raise RuntimeError(
            f"person detector weights not found: looked for {candidates[0]} and {candidates[1]}; "
            f"downloads are disabled - place {DETECTOR_WEIGHTS_NAME} in the pipeline root "
            f"or in the repository root")

    def _get_detector(self):
        if self.detector is None:
            from ultralytics import YOLO
            model = YOLO(str(self.detector_weights()))

            def detector(frame):
                result = model.predict(frame, classes=[0], device='cpu', verbose=False)[0]
                return [{'bbox': [float(v) for v in b], 'conf': float(c)}
                        for b, c in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist())]
            self.detector = detector
        return self.detector

    def _get_encoder(self):
        if self.body_encoder is None:
            model = self._load_osnet()

            def encode(crops):
                batch = torch.stack([torch.from_numpy(self._preprocess(c)).float() for c in crops])
                with torch.no_grad():
                    embs = model.featuremaps(batch).mean(dim=(2, 3)).numpy()
                return [e / (np.linalg.norm(e) + 1e-9) for e in embs]
            self.body_encoder = encode
        return self.body_encoder

    @staticmethod
    def _load_osnet():
        root = Path(__file__).resolve().parents[1]
        from src.reid.osnet import osnet_x0_25
        model = osnet_x0_25(num_classes=4101, pretrained=False)
        state = torch.load(root / 'src' / 'reid' / 'weights' / 'osnet_x0_25_msmt17.pth',
                           map_location='cpu', weights_only=True)
        state = {(k[7:] if k.startswith('module.') else k): v for k, v in state.items()}
        model.load_state_dict(state, strict=True)
        model.eval()
        return model

    @staticmethod
    def _preprocess(crop):
        resized = cv2.resize(crop, (128, 256))
        rgb = resized[:, :, ::-1].astype(np.float32) / 255.0
        return ((rgb - _MEAN) / _STD).transpose(2, 0, 1)

    def _get_engine(self):
        if self._face_engine is None:
            self._face_engine = get_face_engine()
        return self._face_engine

    def _associate(self, boxes):
        track_ids = list(self._tracks)
        candidates = [( _iou(self._tracks[t]['bbox'], b['bbox']), t, i)
                       for t in track_ids for i, b in enumerate(boxes)]
        candidates = [c for c in candidates if c[0] >= _IOU_MATCH]
        candidates.sort(reverse=True)
        assigned, used_boxes = {}, set()
        for iou, tid, bi in candidates:
            if tid in assigned or bi in used_boxes:
                continue
            assigned[tid] = bi
            used_boxes.add(bi)
        return assigned, used_boxes

    @staticmethod
    def _det_signature(detections):
        """Order-insensitive cache key: person boxes rounded to whole pixels."""
        return tuple(sorted(tuple(int(round(v)) for v in d['bbox']) for d in detections))

    def _quality_faces(self, frame, detections):
        """Analyze on first call or signature change, at most once per stride.

        Full-frame buffalo_l analyze runs when boxes changed and at least
        `face_stride` calls passed since the last analyze; every other call
        reuses the last quality observations. face_stride=1 re-analyzes on
        every signature change.
        """
        sig = self._det_signature(detections)
        if not detections:
            self._face_sig, self._face_obs = sig, []
            self._calls += 1
            return []
        first = self._face_sig is None
        changed = sig != self._face_sig
        due = self._calls - self._last_analyze >= self.face_stride
        if first or (changed and due):
            engine = self._get_engine()
            self._face_obs = [f for f in engine.analyze(frame) if engine.quality(f)]
            self._face_sig = sig
            self._last_analyze = self._calls
        self._calls += 1
        return self._face_obs

    def process_frame(self, frame, frame_index=None, timestamp=None):
        events = []
        detections = self._get_detector()(frame)
        assigned, used_boxes = self._associate(detections)
        for tid, bi in assigned.items():
            self._tracks[tid] = {'bbox': detections[bi]['bbox'], 'age': 0}
        for bi, det in enumerate(detections):
            if bi not in used_boxes:
                tid = self._next_id
                self._next_id += 1
                self._tracks[tid] = {'bbox': det['bbox'], 'age': 0}
                assigned[tid] = bi
        for tid in [t for t in self._tracks if t not in assigned]:
            self._tracks[tid]['age'] += 1
            if self._tracks[tid]['age'] > _MAX_AGE:
                del self._tracks[tid]

        quality_faces = self._quality_faces(frame, detections)
        tracks_update = []
        crops = []
        for tid, bi in assigned.items():
            bbox = detections[bi]['bbox']
            crops.append(self._crop(frame, bbox))
            face = next((f for f in quality_faces if _center_inside(f['bbox'], bbox)), None)
            tracks_update.append({'track_id': tid, 'body_embedding': None,
                                  # 512-d buffalo_l face embeddings must not enter the
                                  # 128-d OSNet body index (dim guard would reject);
                                  # face binding goes through best_match + bind_face.
                                  'face_embedding': None,
                                  'frame_index': frame_index, 'face': face, 'bbox': bbox})
        if crops:
            embeddings = self._get_encoder()(crops)
            for item, emb in zip(tracks_update, embeddings):
                item['body_embedding'] = emb
        mapping = self.identity.update(tracks_update)

        persons = []
        for item in tracks_update:
            cluster = mapping[item['track_id']]
            state = self.identity.get(cluster)
            person = {'track_id': item['track_id'], 'bbox': [int(v) for v in item['bbox']],
                      'cluster_id': cluster, 'player_id': state['player_id'],
                      'face_sim': None, 'bound_evidence': state['bound_evidence']}
            face = item['face']
            # Enrolment evidence, never a decision: keep the quality face this
            # frame already produced for this person, in memory only (the 512-d
            # face never meets the 128-d body bank, and nothing is written here).
            # The operator's "click the person" button reads these samples.
            if face is not None and face.get('embedding') is not None:
                self.identity.record_face_sample(cluster, face['embedding'],
                                                 eye_px=face.get('eye_px'),
                                                 det_score=face.get('det_score'),
                                                 bbox=face.get('bbox'),
                                                 frame_index=frame_index)
            # A face without an embedding cannot be matched; never raise on it.
            if (face is not None and person['player_id'] is None
                    and face.get('embedding') is not None):
                match = self._get_engine().best_match(face['embedding'], self._gallery_data())
                # runner_up is passed through so bind_face re-applies the same
                # margin rule best_match used (the binding path used to check
                # only the similarity; see src/person_identity.py:bind_face).
                # .get() keeps a matcher that predates the field (or a test
                # double) working: no runner-up means no competing enrolment.
                # persist=False: process_frame serves GETs, and a GET never
                # writes; the next genuine mutation saves the bind.
                if match and self.identity.bind_face(cluster, match['player_id'],
                                                     match['similarity'],
                                                     {'frame_index': frame_index},
                                                     runner_up=match.get('runner_up'),
                                                     persist=False):
                    person['player_id'] = match['player_id']
                    person['face_sim'] = match['similarity']
                    events.append({'kind': 'bind', 'player_id': match['player_id'],
                                   'cluster_id': cluster, 'similarity': match['similarity'],
                                   'frame_index': frame_index})
            persons.append(person)
        return {'persons': persons, 'events': events}

    def _crop(self, frame, bbox):
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = [int(v) for v in bbox]
        return frame[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]

    def _gallery_data(self):
        if self._gallery is None:
            self._gallery = self.store.faces_load() if self.store is not None else load_faces(self.face_store)
        return self._gallery

    def reload_gallery(self):
        """Forget the cached gallery: the next match reads the store again. Called
        when something else (a confirmed enrolment) has written the store."""
        self._gallery = None

    def enroll_face(self, player_id, image):
        engine = self._get_engine()
        analyze = getattr(engine, 'analyze_resilient', engine.analyze)
        records = [f for f in analyze(image) if engine.quality(f)]
        # merge into the store, never write the cached copy over it
        additions = {str(player_id): records}
        self._gallery = (self.store.faces_add(additions) if self.store is not None
                         else add_faces(self.face_store, additions))
        return len(records)

    def explicit_seed(self, cluster_id, player_id, reason='seed'):
        self.identity.explicit_assign(cluster_id, player_id, reason)
        return True
