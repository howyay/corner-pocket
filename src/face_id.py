"""Face identification (insightface buffalo_l) for player enrollment + matching.

Singleton FaceEngine lazily loads the buffalo_l pack already present under
~/.insightface (CPUExecutionProvider, det_size 640x640, ctx_id=-1). It never
downloads: tests inject a fake analyzer instead of touching the model.

Biometric embeddings are persisted to out/corner-pocket/face_embeddings.json,
deliberately separate from the operations state.json so face data stays out of
the auditable operations record (privacy: biometrics are not match events).

Threshold rationale, measured on real VOD 1280x720 frames:
  same-person, 1s apart:  cosine median 0.958, p05 0.644
  cross-person, same frame: median 0.077, p05 -0.04
  inter-eye distance: median ~10.4px, max 15.9
  -> DEFAULT_THRESHOLD=0.35 sits midway between the cross-person p05 and the
     same-person p05: same-person probes keep ~0.29 of headroom below their
     p05, cross-person impostors would need a +0.39 jump above theirs.
  -> DEFAULT_MARGIN=0.12 (~2 sigma of the cross-person score spread) requires
     the runner-up player to trail by that much, rejecting ambiguous probes
     (two players within 0.12) that a bare threshold would accept.
  -> MIN_EYE_PX=8 keeps the body of the eye-distance distribution (median
     10.4px) and drops only the sub-detection-floor tail: at det_size 640 an
     8px inter-eye distance is ~4px in the detector input, where SCRFD kps
     stop being reliable.

Pure stdlib + insightface + numpy (no torch).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FACE_STORE = ROOT / "out" / "corner-pocket" / "face_embeddings.json"

MIN_EYE_PX = 8.0
MIN_DET_SCORE = 0.4
DEFAULT_THRESHOLD = 0.35
DEFAULT_MARGIN = 0.12
EMBEDDING_DIM = 512

_engine = None


class FaceEngine:
    """Lazy buffalo_l wrapper. Pass analyzer=<fake .get()> to test without models."""

    def __init__(self, analyzer=None):
        self._analyzer = analyzer

    def _create_analyzer(self):
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(
            name="buffalo_l",
            root=str(Path.home() / ".insightface"),
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))
        return app

    def analyze(self, frame):
        """BGR frame -> [{bbox [x1,y1,x2,y2], eye_px, det_score, embedding}].

        embedding: np.float32 512-d, l2-normalized. eye_px: distance between
        the two eye keypoints in original frame pixels, None if kps missing.
        """
        if self._analyzer is None:
            self._analyzer = self._create_analyzer()
        faces = []
        for f in self._analyzer.get(frame):
            emb = getattr(f, "normed_embedding", None)
            if emb is None:
                emb = getattr(f, "embedding", None)
            if emb is None:
                continue
            emb = np.asarray(emb, np.float32).ravel()
            norm = float(np.linalg.norm(emb))
            if norm > 0:
                emb = emb / norm
            kps = getattr(f, "kps", None)
            eye_px = None
            if kps is not None and len(kps) >= 2:
                eye_px = float(np.linalg.norm(np.asarray(kps[1], np.float32) - np.asarray(kps[0], np.float32)))
            faces.append({
                "bbox": [float(v) for v in np.asarray(f.bbox).ravel()[:4]],
                "eye_px": eye_px,
                "det_score": float(np.asarray(f.det_score).ravel()[0]),
                "embedding": emb,
            })
        return faces

    def analyze_resilient(self, frame):
        """analyze() with padding + upscaling retries for tight face crops.

        SCRFD misses faces that fill a tiny crop (e.g. a 65x83 enrollment
        photo): tight crops lack context. If the native-size analysis finds
        nothing, retry with a 50% border pad plus x2/x4/x8 upscale and map
        boxes and eye distances back to original frame pixels so the quality
        gate stays consistent.
        """
        import cv2
        faces = self.analyze(frame)
        if faces:
            return faces
        height, width = frame.shape[:2]
        for scale in (2, 4, 8):
            if max(height, width) * scale > 3000:
                break
            pad_h, pad_w = height // 2, width // 2
            padded = cv2.copyMakeBorder(frame, pad_h, pad_h, pad_w, pad_w,
                                        cv2.BORDER_CONSTANT, value=(24, 24, 24))
            padded_h, padded_w = padded.shape[:2]
            resized = (cv2.resize(padded, (padded_w * scale, padded_h * scale),
                                  interpolation=cv2.INTER_CUBIC) if scale > 1 else padded)
            found = self.analyze(resized)
            if found:
                for face in found:
                    x1, y1, x2, y2 = face["bbox"]
                    face["bbox"] = [(x1 - pad_w * scale) / scale, (y1 - pad_h * scale) / scale,
                                    (x2 - pad_w * scale) / scale, (y2 - pad_h * scale) / scale]
                    if face["eye_px"] is not None:
                        face["eye_px"] = face["eye_px"] / scale
                return found
        return []

    def quality(self, face):
        return quality(face)

    def best_match(self, emb, gallery, threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN):
        return best_match(emb, gallery, threshold=threshold, margin=margin)


def get_face_engine():
    """Process-wide singleton; the model loads on first analyze(), not here."""
    global _engine
    if _engine is None:
        _engine = FaceEngine()
    return _engine


def quality(face):
    """Usable for enrollment/matching: eye_px >= MIN_EYE_PX and det_score >= MIN_DET_SCORE."""
    eye = face.get("eye_px")
    if eye is None or eye < MIN_EYE_PX:
        return False
    return float(face.get("det_score") or 0.0) >= MIN_DET_SCORE


def _cosine(a, b):
    a = np.asarray(a, np.float32).ravel()
    b = np.asarray(b, np.float32).ravel()
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _gallery_items(gallery):
    """Yield (player_id, embedding) from {pid: [entry, ...]} or [{player_id, embedding}]."""
    if isinstance(gallery, dict):
        items = gallery.items()
    else:
        items = [(e.get("player_id"), e) for e in gallery]
    for pid, val in items:
        entries = val if isinstance(val, list) else [val]
        for entry in entries:
            emb = entry.get("embedding") if isinstance(entry, dict) else entry
            if emb is not None:
                yield pid, emb


def best_match(emb, gallery, threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN):
    """Best gallery match for embedding `emb`, or None.

    Returns {'player_id', 'similarity', 'margin'} where margin is the gap to
    the best *other* player (inf with a single-player gallery). Rejects when
    similarity < threshold (no real match) or margin < margin (ambiguous
    between players). Accepts gallery as {pid: [entries]} or flat
    [{player_id, embedding}] lists.
    """
    if emb is None or not gallery:
        return None
    per_player = {}
    for pid, g in _gallery_items(gallery):
        sim = _cosine(emb, g)
        if pid not in per_player or sim > per_player[pid]:
            per_player[pid] = sim
    if not per_player:
        return None
    pid = max(per_player, key=per_player.get)
    sim = per_player[pid]
    others = [s for p, s in per_player.items() if p != pid]
    gap = sim - max(others) if others else float("inf")
    if sim < threshold or gap < margin:
        return None
    return {"player_id": pid, "similarity": sim, "margin": gap}


@dataclass
class FaceRecord:
    embedding: np.ndarray  # float32 512-d, l2-normalized
    bbox: list  # [x1, y1, x2, y2] floats
    eye_px: float | None
    det_score: float
    source: str | None = None


def embed_image(image, source=None):
    """Image path or BGR ndarray -> list[FaceRecord] for every detected face.

    No quality filtering here; callers gate with quality() before enrolling.
    """
    engine = get_face_engine()
    if isinstance(image, (str, os.PathLike)):
        image = os.fspath(image)
        import cv2

        frame = cv2.imread(image)
        if frame is None:
            raise FileNotFoundError(f"cannot read image: {image}")
        if source is None:
            source = image
    else:
        frame = image
    return [
        FaceRecord(
            embedding=f["embedding"],
            bbox=f["bbox"],
            eye_px=f["eye_px"],
            det_score=f["det_score"],
            source=source,
        )
        for f in engine.analyze(frame)
    ]


def store_faces(path, gallery):
    """Atomically write {player_id: [face entries]} as JSON; returns stored dict.

    Entries may carry ndarray or list embeddings; they are stored as
    4dp-rounded floats. created_at is filled (UTC ISO) when absent.
    """
    path = Path(path)
    stored = {}
    for pid, entries in gallery.items():
        rows = []
        for entry in entries:
            emb = np.asarray(entry["embedding"], np.float32).ravel()
            rows.append({
                "embedding": [round(float(v), 4) for v in emb[:EMBEDDING_DIM]],
                "eye_px": entry.get("eye_px"),
                "det_score": entry.get("det_score"),
                "created_at": entry.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "source": entry.get("source"),
            })
        stored[pid] = rows
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_text(json.dumps(stored, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return stored


def load_faces(path):
    """Load the gallery; {} on missing or corrupted file (tolerant by design)."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}