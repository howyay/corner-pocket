"""Enrol a regular from the person track the operator clicks on screen.

The owner's answer to "how do we fill the roster?" is: point at the person, type a
name. This module is the backend for that flow — collect the faces of one person
track over a frame range, pick the best few, refuse loudly when the track cannot
be enrolled, and hand back the exact JSON that would be written to the roster and
to the face store. It writes nothing outside a scratch root.

Rules this module commits to (each is stated where it is used and pinned by
tests/test_enroll_from_tracklet.py):

- association: a face belongs to a track only if the face's CENTRE is inside that
  person's box — the production rule (src/person_pipeline.py:47-49, used at :182 to
  attach a face to a person) — plus an ambiguity guard: a face claimed by two
  person boxes in the same frame is dropped rather than assigned to both.
  `Candidate.face_iou` (face ∩ person / face area) is recorded as evidence.
- ranking: `det_score * eye_px`. Both factors are already gated (eye >= 8 px,
  det >= 0.4) and the product prefers faces that are confidently detected AND
  large, which is where the face engine is most reliable. Keep up to K = 5.
- consistency: every kept embedding must be at least CONSISTENCY_COSINE (0.5)
  cosine from every other kept one, growing greedily from the best-ranked
  candidate. Measured on this footage: same-person p05 0.405, different people at
  most 0.226 — 0.5 accepts same-person variation and refuses a second person that
  drifted into the same track. An enrolment needs MIN_KEPT = 2 mutually
  consistent faces; a track with a single good face is refused as
  `single_face_only` so the caller can fall back to the single-photo path.
- track purity: the kept faces must also agree with the REST of the track's usable
  faces — at least PURITY_DEFAULT (0.5) of them within `consistency` cosine —
  otherwise the enrolment is refused as `mixed_track`. This was measured, not
  guessed: without it, four tracks in a 180 s window (IoU tracker switching
  between two people) enrolled two mutually consistent faces while matching 0 of
  their own track's other 30+ faces and 90 of the *other* player's faces above the
  bind bar. Purity is only decisive with at least PURITY_PROBES_MIN (2) other
  usable faces — over a single probe the ratio can only be 0 or 1, which is a
  binary vote that would let one intruding face veto an otherwise consistent pair
  that the consistency gate already handles — and with no other usable face it is
  not measurable at all.
- refusals are typed and returned, never an empty list: track_not_found,
  no_face_in_track, face_too_small, face_low_detection, single_face_only,
  inconsistent_faces.

Operator seam (what the UI calls): `plan_for_selection(root, dataset, frame_index,
bbox)` locks the click onto one IoU track and plans the enrolment; `preview_payload()`
returns a JSON-safe payload with up to 5 face crops as base64 data URLs (no file
route needed) plus a `token`; `enrollment_token()` hashes the dataset, track id,
kept frame indices and each crop's JPEG bytes; `confirm_enrollment(root, plan, token,
player_name)` recomputes that token and refuses a mismatch with
`EnrollmentTokenError('token_mismatch')`, so a stale browser tab cannot enrol a
different person than the one it displayed.

Writes: `write_enrollment()` copies the production state into the caller's scratch
root and writes only there. The production roster and face store are never touched;
the caller decides when the enrolment becomes real.
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.face_id import MIN_DET_SCORE, MIN_EYE_PX
from src.person_pipeline import REPO, PersonPipeline

DATASETS = {"vod30": "data/vod_30min_260815.mp4", "highlight": "data/vod_highlight.mp4"}
DEFAULT_STATE = Path("out") / "corner-pocket" / "state.json"
DEFAULT_FACE_STORE = Path("out") / "corner-pocket" / "face_embeddings.json"

K_DEFAULT = 5
CONSISTENCY_COSINE = 0.5
MIN_KEPT_DEFAULT = 2
PURITY_DEFAULT = 0.5          # share of the track's other usable faces that must agree with the kept set
PURITY_PROBES_MIN = 2         # purity is only decisive with >= 2 other usable faces
IOU_TRACK = 0.3            # same person across sampled frames (PersonPipeline._IOU_MATCH)
TRACK_MAX_AGE = 3          # sampled frames a track survives without a detection
SCAN_KEYS = ("frames_with_track", "faces_associated", "ambiguous", "gated_eye", "gated_det")

REFUSAL_REASONS = (
    "track_not_found",      # the track id is not in the observations
    "no_face_in_track",     # the person is there, no face centre inside its box
    "face_too_small",       # associated faces, all below MIN_EYE_PX
    "face_low_detection",   # eye distance fine, all below MIN_DET_SCORE
    "single_face_only",     # one usable face: no consistency evidence
    "inconsistent_faces",   # two or more usable faces that do not agree
    "mixed_track",          # the kept faces disagree with the rest of the track
    "selection_not_matched",  # the click does not overlap any person box in that frame
)

PROTECTED = (str(DEFAULT_STATE), str(DEFAULT_FACE_STORE))


# --------------------------------------------------------------------------
# pure helpers
# --------------------------------------------------------------------------

def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def face_area_iou(face_box, person_box) -> float:
    """face ∩ person / face area: 1.0 when the face is fully inside the person."""
    ix = max(0.0, min(face_box[2], person_box[2]) - max(face_box[0], person_box[0]))
    iy = max(0.0, min(face_box[3], person_box[3]) - max(face_box[1], person_box[1]))
    area = (face_box[2] - face_box[0]) * (face_box[3] - face_box[1])
    return (ix * iy) / area if area > 0 else 0.0


def center_inside(box, person) -> bool:
    """The production association rule (src/person_pipeline.py:_center_inside)."""
    x, y = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    return person[0] <= x <= person[2] and person[1] <= y <= person[3]


def cosine(a, b) -> float:
    a = np.asarray(a, np.float32).ravel()
    b = np.asarray(b, np.float32).ravel()
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0


def rank_score(det_score, eye_px) -> float:
    """det_score * eye_px; a face without keypoints cannot be ranked (0)."""
    if eye_px is None:
        return 0.0
    return float(det_score) * float(eye_px)


def stats(values) -> dict:
    values = [float(v) for v in values]
    if not values:
        return {"n": 0, "min": None, "p05": None, "median": None, "p95": None, "max": None}
    arr = np.asarray(values, float)
    return {"n": len(values), "min": round(float(arr.min()), 4),
            "p05": round(float(np.percentile(arr, 5)), 4),
            "median": round(float(np.median(arr)), 4),
            "p95": round(float(np.percentile(arr, 95)), 4),
            "max": round(float(arr.max()), 4)}


def load_state(root=REPO) -> dict:
    path = Path(root) / DEFAULT_STATE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def md5(path) -> str | None:
    import hashlib
    path = Path(path)
    return hashlib.md5(path.read_bytes()).hexdigest() if path.is_file() else None


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------

@dataclass
class Candidate:
    frame_index: int
    t: float
    bbox: list            # face box in frame pixels
    person_bbox: list
    det_score: float
    eye_px: float | None
    embedding: np.ndarray
    face_iou: float = 0.0

    @property
    def rank(self) -> float:
        return rank_score(self.det_score, self.eye_px)

    def summary(self) -> dict:
        return {"frame_index": self.frame_index, "t": self.t, "bbox": self.bbox,
                "det_score": round(float(self.det_score), 4),
                "eye_px": None if self.eye_px is None else round(float(self.eye_px), 2),
                "face_iou": round(float(self.face_iou), 4),
                "rank": round(self.rank, 4)}

    def store_entry(self, created_at: str, source: str) -> dict:
        """The face_embeddings.json row shape src.face_id.store_faces writes."""
        return {"embedding": [round(float(v), 4) for v in np.asarray(self.embedding, np.float32)],
                "eye_px": None if self.eye_px is None else float(self.eye_px),
                "det_score": round(float(self.det_score), 4),
                "created_at": created_at, "source": source}


@dataclass
class Refusal:
    reason: str
    detail: dict = field(default_factory=dict)
    candidates: list = field(default_factory=list)
    context: dict = field(default_factory=dict, repr=False)   # non-serialised (observations)

    def __post_init__(self):
        if self.reason not in REFUSAL_REASONS:
            raise ValueError(f"unknown refusal reason: {self.reason}")

    @property
    def ok(self) -> bool:
        return False

    def message(self) -> str:
        return {
            "track_not_found": "that person was not seen in the sampled frames",
            "no_face_in_track": "the person was seen, but no face was detected inside their box",
            "face_too_small": f"every face was below the {MIN_EYE_PX}px eye-distance gate",
            "face_low_detection": f"every face was below the {MIN_DET_SCORE} detection gate",
            "single_face_only": "only one usable face: upload a second photo to prove consistency",
            "inconsistent_faces": "the usable faces do not agree: more than one person may be in this track",
            "mixed_track": "the best faces disagree with the rest of this track: the track may have switched people",
            "selection_not_matched": "that click does not overlap a person in this frame: click the person again",
        }[self.reason]

    def to_dict(self) -> dict:
        return {"ok": False, "reason": self.reason, "message": self.message(),
                "detail": self.detail, "candidates": [c.summary() for c in self.candidates]}


@dataclass
class Enrollment:
    track_id: int
    player_id: str
    player_name: str
    crops: list                     # kept Candidate objects, best first
    store_json: dict                # exact face_embeddings.json payload
    roster_json: dict | None        # exact state.json payload (None when state was not supplied)
    evidence: dict
    dropped: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return True

    def to_dict(self) -> dict:
        return {"ok": True, "track_id": self.track_id, "player_id": self.player_id,
                "player_name": self.player_name,
                "crops": [c.summary() for c in self.crops],
                "dropped": self.dropped,
                "store_json": self.store_json, "roster_json": self.roster_json,
                "evidence": self.evidence}


# --------------------------------------------------------------------------
# collection (pure)
# --------------------------------------------------------------------------

def _claimed_by(persons, face_box) -> int:
    return sum(1 for person in persons if center_inside(face_box, person["bbox"]))


def scan_track(observations, track_id) -> dict:
    """Per-track counts that drive the refusals and the operator's message."""
    scan = {key: 0 for key in SCAN_KEYS}
    for observation in observations:
        persons = observation.get("persons", [])
        mine = [p for p in persons if int(p["track_id"]) == int(track_id)]
        if not mine:
            continue
        scan["frames_with_track"] += 1
        person = mine[0]
        for face in observation.get("faces", []):
            if not center_inside(face["bbox"], person["bbox"]):
                continue
            if _claimed_by(persons, face["bbox"]) > 1:
                scan["ambiguous"] += 1
                continue
            scan["faces_associated"] += 1
            eye = face.get("eye_px")
            if eye is None or float(eye) < MIN_EYE_PX:
                scan["gated_eye"] += 1
            elif float(face["det_score"]) < MIN_DET_SCORE:
                scan["gated_det"] += 1
    return scan


def collect_face_candidates(observations, track_id, *, min_eye_px=MIN_EYE_PX,
                            min_det_score=MIN_DET_SCORE) -> list:
    """Every usable face of one track, best-ranked first.

    Association = centre-inside (the production rule) plus the ambiguity guard: a
    face whose centre falls inside two person boxes in the same frame is dropped,
    so one face can never be enrolled for two people.
    """
    candidates = []
    for observation in observations:
        persons = observation.get("persons", [])
        mine = [p for p in persons if int(p["track_id"]) == int(track_id)]
        if not mine:
            continue
        person = mine[0]
        for face in observation.get("faces", []):
            if not center_inside(face["bbox"], person["bbox"]):
                continue
            if _claimed_by(persons, face["bbox"]) > 1:
                continue
            eye = face.get("eye_px")
            if eye is None or float(eye) < min_eye_px:
                continue
            if float(face["det_score"]) < min_det_score:
                continue
            candidates.append(Candidate(
                frame_index=int(observation["frame_index"]), t=float(observation.get("t") or 0.0),
                bbox=[round(float(v), 2) for v in face["bbox"]],
                person_bbox=[round(float(v), 2) for v in person["bbox"]],
                det_score=float(face["det_score"]), eye_px=float(eye),
                embedding=np.asarray(face["embedding"], np.float32),
                face_iou=round(face_area_iou(face["bbox"], person["bbox"]), 4)))
    candidates.sort(key=lambda candidate: candidate.rank, reverse=True)
    return candidates


# --------------------------------------------------------------------------
# planning (pure: no models, no writes)
# --------------------------------------------------------------------------

def new_player(player_name, *, player_id=None, created_at=None) -> dict:
    """The roster record annotator/operations.py writes for a regular."""
    return {"id": player_id or uuid.uuid4().hex, "name": player_name,
            "joinedAt": created_at or datetime.now(timezone.utc).isoformat(),
            "rating": 0, "status": "Active"}


def _player_id_from_name(state, player_name) -> str | None:
    wanted = str(player_name).strip().casefold()
    for player in state.get("players", []):
        if str(player.get("name", "")).casefold() == wanted:
            return player.get("id")
    return None


def plan_enrollment(candidates, *, track_id, player_name, k=K_DEFAULT,
                    consistency=CONSISTENCY_COSINE, min_kept=MIN_KEPT_DEFAULT,
                    min_purity=PURITY_DEFAULT, state=None, created_at=None,
                    scan=None) -> Enrollment | Refusal:
    """Keep up to `k` mutually consistent faces and build the exact JSON.

    Typed refusals: `single_face_only` when fewer than `min_kept` faces are usable,
    `inconsistent_faces` when the usable faces do not agree at `consistency` cosine,
    `mixed_track` when the kept faces disagree with the rest of the track.
    """
    scan = {key: (scan or {}).get(key, 0) for key in SCAN_KEYS}
    if len(candidates) < min_kept:
        return Refusal("single_face_only",
                       {"usable_faces": len(candidates), "min_kept": min_kept, **scan},
                       candidates)
    kept, dropped = [candidates[0]], []
    for candidate in candidates[1:]:
        if len(kept) >= k:
            break
        sims = [cosine(candidate.embedding, other.embedding) for other in kept]
        if min(sims) >= consistency:
            kept.append(candidate)
        else:
            dropped.append({**candidate.summary(), "reason": "inconsistent_with_kept",
                            "worst_kept_cosine": round(float(min(sims)), 4)})
    if len(kept) < min_kept:
        return Refusal("inconsistent_faces",
                       {"usable_faces": len(candidates), "kept": len(kept),
                        "consistency_cosine": consistency, "min_kept": min_kept, **scan},
                       candidates)
    skipped_by_k = len(candidates) - len(kept) - len(dropped)
    rest = [candidate for candidate in candidates if candidate not in kept]
    agreeing = sum(1 for candidate in rest
                   if max(cosine(candidate.embedding, other.embedding) for other in kept) >= consistency)
    purity = (agreeing / len(rest)) if rest else None
    if purity is not None and len(rest) >= PURITY_PROBES_MIN and purity < min_purity:
        return Refusal("mixed_track",
                       {"usable_faces": len(candidates), "kept": len(kept),
                        "purity": round(purity, 4), "purity_probes": len(rest),
                        "agreeing": agreeing, "min_purity": min_purity,
                        "consistency_cosine": consistency, **scan},
                       candidates)
    created = created_at or datetime.now(timezone.utc).isoformat()
    pairwise = [cosine(kept[i].embedding, kept[j].embedding)
                for i in range(len(kept)) for j in range(i + 1, len(kept))]
    player_id = _player_id_from_name(state, player_name) if state else None
    player = ({"id": player_id, "name": str(player_name)} if player_id
              else new_player(player_name, created_at=created))
    frames = sorted(candidate.frame_index for candidate in kept)
    evidence = {
        "track_id": track_id, "player_id": player["id"],
        "usable_faces": len(candidates), "kept": len(kept), "dropped": len(dropped),
        "skipped_by_k": skipped_by_k, "purity": None if purity is None else round(purity, 4),
        "purity_probes": len(rest), "min_purity": min_purity,
        "purity_decisive": len(rest) >= PURITY_PROBES_MIN,
        "k": k, "consistency_cosine": consistency, "min_kept": min_kept,
        "rank_metric": "det_score * eye_px",
        "association": "face centre inside the person box; dropped when two boxes claim it",
        "kept_frame_indices": frames,
        "kept_span_s": round(max(frames) - min(frames), 3) if frames else 0,
        "det_score": stats([candidate.det_score for candidate in kept]),
        "eye_px": stats([candidate.eye_px for candidate in kept]),
        "pairwise_cosine": stats(pairwise),
        "existing_player": bool(player_id),
        **scan,
    }
    store_json = {player["id"]: [candidate.store_entry(created, str(track_id))
                                for candidate in kept]}
    roster_json = _roster_payload(state, player, evidence) if state is not None else None
    return Enrollment(track_id=track_id, player_id=player["id"], player_name=str(player_name),
                      crops=kept, store_json=store_json, roster_json=roster_json,
                      evidence=evidence, dropped=dropped)


def _roster_payload(state, player, evidence) -> dict:
    """state.json with the player added, in the shape Operations writes it."""
    payload = json.loads(json.dumps(state))          # never mutate the caller's state
    players = payload.setdefault("players", [])
    if not any(existing.get("id") == player["id"] for existing in players):
        players.append(player)
    payload["revision"] = int(payload.get("revision", 0)) + 1
    event = {"id": uuid.uuid4().hex, "createdAt": datetime.now(timezone.utc).isoformat(),
             "revision": payload["revision"], "action": "player_enroll_from_tracklet",
             "context": {"player_id": player["id"], "name": player["name"],
                         "track_id": evidence["track_id"], "faces": evidence["kept"],
                         "frames": evidence["kept_frame_indices"]}}
    payload["events"] = (payload.get("events", []) + [event])[-500:]
    return payload


def plan_for_track(observations, track_id, *, player_name, state=None, created_at=None,
                   **kwargs) -> Enrollment | Refusal:
    """Collect then plan, returning the typed refusal the operator must see."""
    scan = scan_track(observations, track_id)
    detail = {**scan, "track_id": track_id}
    if scan["frames_with_track"] == 0:
        return Refusal("track_not_found", detail)
    if scan["faces_associated"] == 0:
        if scan["ambiguous"]:
            detail["note"] = "every associated face was claimed by two person boxes"
        return Refusal("no_face_in_track", detail)
    usable = scan["faces_associated"] - scan["gated_eye"] - scan["gated_det"]
    if usable < 1:
        if scan["gated_eye"] >= scan["gated_det"]:
            return Refusal("face_too_small", detail)
        return Refusal("face_low_detection", detail)
    candidates = collect_face_candidates(observations, track_id)
    return plan_enrollment(candidates, track_id=track_id, player_name=player_name,
                           state=state, created_at=created_at, scan=scan, **kwargs)


# --------------------------------------------------------------------------
# real footage: scan a frame range once, then plan per track
# --------------------------------------------------------------------------

def scan_frames(root, dataset, start_frame, end_frame, stride=30, *, detector=None,
                engine=None, log=print) -> list:
    """Production detector + face engine over a frame range, with IoU tracks.

    Sequential grab/retrieve (no per-frame seek). Person boxes are linked across
    sampled frames at IoU >= IOU_TRACK with a TRACK_MAX_AGE grace, the same greedy
    rule (and the same detector object) PersonPipeline uses. Faces carry their
    embedding (4dp) once they clear the detection gate.
    """
    import cv2
    video = REPO / DATASETS[dataset]
    detector = detector or PersonPipeline(root)._get_detector()
    if engine is None:
        from src.face_id import get_face_engine
        engine = get_face_engine()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    grace = stride * TRACK_MAX_AGE
    observations, tracks, next_id = [], {}, 1
    wanted = list(range(int(start_frame), int(end_frame), max(1, int(stride))))
    try:
        cursor, position = 0, 0
        while position < len(wanted):
            if not cap.grab():
                break
            if cursor != wanted[position]:
                cursor += 1
                continue
            ok, frame = cap.retrieve()
            if ok:
                frame_index = wanted[position]
                boxes = detector(frame)
                faces = engine.analyze(frame)
                live = {tid: value for tid, value in tracks.items()
                        if frame_index - value[0] <= grace}
                free, taken = [], set()
                for box in boxes:
                    bbox = [float(v) for v in box["bbox"]]
                    best, best_iou = None, IOU_TRACK
                    for tid, (_last_frame, last_box) in live.items():
                        if tid in taken:
                            continue
                        value = iou(bbox, last_box)
                        if value >= best_iou:
                            best, best_iou = tid, value
                    if best is None:
                        best = next_id
                        next_id += 1
                    taken.add(best)
                    free.append((best, bbox, float(box.get("conf", 0.0))))
                tracks = dict(live)
                for tid, bbox, _conf in free:
                    tracks[tid] = (frame_index, bbox)
                observations.append({
                    "frame_index": frame_index, "t": round(frame_index / fps, 3),
                    "persons": [{"track_id": tid, "bbox": bbox, "conf": round(conf, 4)}
                                for tid, bbox, conf in free],
                    "faces": [{"bbox": [round(float(v), 2) for v in face["bbox"]],
                               "eye_px": None if face.get("eye_px") is None else round(float(face["eye_px"]), 2),
                               "det_score": round(float(face["det_score"]), 4),
                               "embedding": (None if float(face["det_score"]) < MIN_DET_SCORE
                                             else [round(float(v), 4) for v in np.asarray(face["embedding"], np.float32)])}
                              for face in faces]})
                log(f"{dataset} f{frame_index} t={frame_index / fps:.1f}s "
                    f"persons={len(free)} faces={len(faces)}", flush=True)
            position += 1
            cursor += 1
    finally:
        cap.release()
    return observations


def persistent_tracks(observations, limit=None) -> list:
    """Tracks ranked by how many sampled frames they appear in."""
    counts: dict[int, dict] = {}
    for observation in observations:
        for person in observation.get("persons", []):
            row = counts.setdefault(int(person["track_id"]),
                                    {"track_id": int(person["track_id"]), "frames": 0,
                                     "first_frame": observation["frame_index"],
                                     "last_frame": observation["frame_index"]})
            row["frames"] += 1
            row["last_frame"] = observation["frame_index"]
    ranked = sorted(counts.values(), key=lambda row: (-row["frames"], row["first_frame"]))
    return ranked[:limit] if limit else ranked


# --------------------------------------------------------------------------
# writes: scratch root only
# --------------------------------------------------------------------------

def write_enrollment(scratch_root, enrollment, *, source_root=REPO) -> dict:
    """Copy the production roster into `scratch_root` and write the enrolment there.

    Never writes under source_root: the caller promotes the scratch files into
    production deliberately, or not at all. Returns the paths written.
    """
    scratch_root = Path(scratch_root).resolve()
    source_root = Path(source_root).resolve()
    if scratch_root == source_root or source_root.is_relative_to(scratch_root):
        raise ValueError("scratch root must not contain the production root")
    state_path = scratch_root / DEFAULT_STATE
    if enrollment.roster_json is not None:
        _write_json(state_path, enrollment.roster_json)
    elif not state_path.exists():
        state_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / DEFAULT_STATE, state_path)
    store_path = scratch_root / DEFAULT_FACE_STORE
    _write_json(store_path, enrollment.store_json)
    return {"state": str(state_path), "store": str(store_path)}


def _write_json(path, payload) -> None:
    """json.dump(indent=2) + trailing newline: the format Operations writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# the operator seam: click a person, see the crops, confirm with a name
# --------------------------------------------------------------------------

CROP_PAD = 0.6            # padding around the face box, as a fraction of its size
CROP_SCALE = 4            # nearest-neighbour upscale for the preview
CROP_QUALITY = 85         # JPEG quality; ~15-25 KB per crop at 4x
CROP_MAX_BYTES = 40_000   # the per-crop budget the UI was promised
PREVIEW_CROPS = 5
SELECTION_IOU_MIN = 0.2   # a click must overlap the person box at least this much


class EnrollmentTokenError(Exception):
    """Typed confirmation failure.

    Reasons: `token_mismatch` (a stale tab is confirming a different person or a
    different set of crops) and `player_name_required` (nothing to enrol under).
    """

    def __init__(self, reason: str, detail: dict | None = None):
        if reason not in ("token_mismatch", "player_name_required"):
            raise ValueError(f"unknown confirmation error: {reason}")
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {"ok": False, "reason": self.reason,
                "message": {"token_mismatch": "these crops are not the ones you were shown; reload the frame",
                            "player_name_required": "a name is required to enrol a regular"}[self.reason],
                "detail": self.detail}


@dataclass
class Selection:
    """What the operator's click locked onto: one IoU track plus its enrolment."""
    dataset: str
    frame_index: int
    track_id: int
    selection_iou: float
    frames_seen: int
    enrollment: Enrollment
    context: dict = field(default_factory=dict, repr=False)   # observations, for rendering

    @property
    def ok(self) -> bool:
        return True

    def to_dict(self) -> dict:
        return {"ok": True, "dataset": self.dataset, "frame_index": self.frame_index,
                "track_id": self.track_id, "selection_iou": round(float(self.selection_iou), 4),
                "frames_seen": self.frames_seen, "enrollment": self.enrollment.to_dict()}


def plan_for_selection(root, dataset, frame_index, bbox, *, observations=None,
                       window_s=180, stride=30, min_selection_iou=SELECTION_IOU_MIN,
                       player_name=None, state=None, **kwargs) -> Selection | Refusal:
    """Lock onto the person the operator clicked and plan their enrolment.

    `root`/`dataset` name the recording; `frame_index` + `bbox` are what the UI has
    on screen. The click is matched to the scan's IoU track by overlap with the
    person box in that frame, and the result carries `selection_iou` (how well the
    click matched) and `frames_seen` (how long that track lasts), so the UI can say
    truthfully which person it locked onto. Nothing overlaps -> `selection_not_matched`.

    `player_name=None` is allowed here: the name is not part of the token, and
    `confirm_enrollment` re-plans with the operator's name at confirmation time.
    """
    from_frame = int(frame_index)
    if observations is None:
        observations = scan_frames(root, dataset, max(0, from_frame - window_s * 30),
                                   from_frame + window_s * 30, stride,
                                   **{key: value for key, value in kwargs.items()
                                      if key in ("detector", "engine", "log")})
    frame = next((row for row in observations if int(row["frame_index"]) == from_frame), None)
    if frame is None:
        return Refusal("selection_not_matched",
                       {"detail": "the clicked frame is outside the scanned range",
                        "frame_index": from_frame, "track_id": None})
    scored = sorted(((iou(bbox, person["bbox"]), int(person["track_id"]))
                     for person in frame.get("persons", [])), reverse=True)
    if not scored or scored[0][0] < min_selection_iou:
        return Refusal("selection_not_matched",
                       {"frame_index": from_frame, "bbox": [float(v) for v in bbox],
                        "min_selection_iou": min_selection_iou,
                        "best_overlap": round(float(scored[0][0]), 4) if scored else 0.0},
                       context={"observations": observations})
    selection_iou, track_id = scored[0]
    scan = scan_track(observations, track_id)
    planned = plan_for_track(observations, track_id,
                             player_name=player_name or f"track-{track_id}",
                             state=state, **{key: value for key, value in kwargs.items()
                                             if key not in ("detector", "engine", "log")})
    if not planned.ok:
        planned.detail = {**planned.detail, "frame_index": from_frame,
                          "selection_iou": round(float(selection_iou), 4),
                          "frames_seen": scan["frames_with_track"],
                          "bbox": [float(v) for v in bbox]}
        planned.context = {"observations": observations}
        return planned
    return Selection(dataset=dataset, frame_index=from_frame, track_id=track_id,
                     selection_iou=float(selection_iou),
                     frames_seen=scan["frames_with_track"], enrollment=planned,
                     context={"observations": observations})


def crop_jpeg(root, dataset, frame_index, bbox, *, pad=CROP_PAD, scale=CROP_SCALE,
              quality=CROP_QUALITY) -> bytes:
    """Face crop around `bbox`, padded, upscaled nearest-neighbour, JPEG-encoded.

    Deterministic: the same frame, box and parameters give byte-identical output,
    which is what makes the confirmation token meaningful.
    """
    import cv2
    video = Path(root) / DATASETS[dataset]
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    try:
        if not cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index)):
            raise RuntimeError(f"frame seek failed: {frame_index}")
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"frame decode failed: {frame_index}")
    finally:
        cap.release()
    height, width = frame.shape[:2]
    box_w, box_h = float(bbox[2]) - float(bbox[0]), float(bbox[3]) - float(bbox[1])
    x0 = int(max(0, float(bbox[0]) - box_w * pad))
    y0 = int(max(0, float(bbox[1]) - box_h * pad))
    x1 = int(min(width, float(bbox[2]) + box_w * pad))
    y1 = int(min(height, float(bbox[3]) + box_h * pad))
    crop = frame[y0:max(y0 + 1, y1), x0:max(x0 + 1, x1)]
    if scale > 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    ok, encoded = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return encoded.tobytes()


def crop_data_url(jpeg_bytes) -> str:
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def _crop_bytes(crop) -> bytes:
    """Accept {'jpeg': bytes} or {'jpeg_data_url': '...'} as the browser sends it."""
    import base64
    if isinstance(crop, dict):
        if isinstance(crop.get("jpeg"), (bytes, bytearray)):
            return bytes(crop["jpeg"])
        data_url = crop.get("jpeg_data_url") or crop.get("data_url")
        if isinstance(data_url, str) and "," in data_url:
            return base64.b64decode(data_url.split(",", 1)[1])
    raise ValueError("a crop must carry its JPEG bytes (jpeg) or a data URL (jpeg_data_url)")


def enrollment_token(dataset, track_id, crops) -> str:
    """Hash over exactly the crops shown to the operator.

    Covers the dataset, the track id, and each crop's frame index plus the SHA-256
    of its JPEG bytes, so re-encoding, re-sampling or swapping a crop changes the
    token. `confirm_enrollment` recomputes it and refuses a mismatch.
    """
    import hashlib
    rows = []
    for index, crop in enumerate(crops):
        frame_index = crop.get("frame_index") if isinstance(crop, dict) else None
        payload = _crop_bytes(crop)
        rows.append({"index": index,
                     "frame_index": int(frame_index) if frame_index is not None else None,
                     "sha256": hashlib.sha256(payload).hexdigest()})
    canonical = json.dumps({"dataset": str(dataset), "track_id": int(track_id), "crops": rows},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _crop_record(index, frame_index, t, det_score, eye_px, jpeg) -> dict:
    """Internal crop record: carries the bytes the token hashes plus the data URL."""
    return {"index": int(index), "frame_index": int(frame_index),
            "t": None if t is None else float(t),
            "det_score": None if det_score is None else float(det_score),
            "eye_px": None if eye_px is None else float(eye_px),
            "jpeg": jpeg, "jpeg_data_url": crop_data_url(jpeg)}


def _public_crop(crop) -> dict:
    """What the browser gets: no raw bytes, only the data URL (JSON-safe)."""
    return {key: value for key, value in crop.items() if key != "jpeg"}


def _json_safe(value):
    """Recursively turn numpy scalars / tuples / Paths into plain JSON types."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, Path):
        return str(value)
    return value


def _seen_face_crops(root, dataset, observations, track_id, limit=PREVIEW_CROPS) -> list:
    """Faces associated with a track, gated or not, best-ranked: what we saw."""
    seen = []
    for observation in observations:
        persons = observation.get("persons", [])
        mine = [person for person in persons if int(person["track_id"]) == int(track_id)]
        if not mine:
            continue
        person = mine[0]
        for face in observation.get("faces", []):
            if center_inside(face["bbox"], person["bbox"]):
                seen.append((rank_score(face.get("det_score") or 0.0, face.get("eye_px")),
                             observation, face))
    seen.sort(key=lambda item: item[0], reverse=True)
    crops = []
    for index, (_rank, observation, face) in enumerate(seen[:limit]):
        crops.append(_crop_record(index, observation["frame_index"], observation.get("t"),
                                  face.get("det_score"), face.get("eye_px"),
                                  crop_jpeg(root, dataset, observation["frame_index"], face["bbox"])))
    return crops


def preview_payload(plan_or_refusal, *, root=REPO, dataset=None, player_name=None) -> dict:
    """JSON-safe payload for the browser: crops as data URLs, never a file path.

    An `ok` payload carries the token `confirm_enrollment` needs; a refusal payload
    still carries the faces that were seen, because "here is what I saw and why it
    is not enough" is what the operator needs to re-click.
    """
    root = Path(root)
    if isinstance(plan_or_refusal, Selection):
        selection = plan_or_refusal
        enrollment = selection.enrollment
        crops = [_crop_record(index, candidate.frame_index, candidate.t,
                              candidate.det_score, candidate.eye_px,
                              crop_jpeg(root, selection.dataset, candidate.frame_index, candidate.bbox))
                 for index, candidate in enumerate(enrollment.crops)]
        evidence = enrollment.evidence
        return _json_safe({
            "ok": True, "dataset": selection.dataset, "frame_index": selection.frame_index,
            "track_id": selection.track_id,
            "selection_iou": round(float(selection.selection_iou), 4),
            "frames_seen": selection.frames_seen,
            "crops": [_public_crop(crop) for crop in crops],
            "purity": {"probes": evidence.get("purity_probes"), "agreement": evidence.get("purity")},
            "quality": {"kept": evidence.get("kept"), "usable": evidence.get("usable_faces")},
            "player_id": enrollment.player_id,
            "player_name": player_name or enrollment.player_name,
            "frames": evidence.get("kept_frame_indices"),
            "token": enrollment_token(selection.dataset, selection.track_id, crops)})
    refusal = plan_or_refusal
    detail = refusal.detail or {}
    dataset = dataset or detail.get("dataset")
    crops = []
    observations = (refusal.context or {}).get("observations")
    if observations and dataset and detail.get("track_id") is not None:
        crops = _seen_face_crops(root, dataset, observations, detail["track_id"])
    return _json_safe({
        "ok": False, "reason": refusal.reason, "message": refusal.message(),
        "track_id": detail.get("track_id"), "dataset": dataset,
        "frame_index": detail.get("frame_index"),
        "crops": [_public_crop(crop) for crop in crops],
        "detail": {key: value for key, value in detail.items() if key != "track_id"}})


def confirm_enrollment(root, plan, token, player_name, *, scratch_root=None, dataset=None,
                       state=None, created_at=None) -> dict:
    """Confirm the preview: verify the token, then write through `write_enrollment`.

    The token is recomputed from the plan's crops (re-rendered from the recording,
    so byte-identical) and a mismatch raises
    `EnrollmentTokenError('token_mismatch')` before anything is written — a stale
    tab cannot enrol a different person than the one it displayed. Writes go to
    `scratch_root` only; `root` is read for the roster, never written.
    """
    if not isinstance(plan, Selection):
        raise ValueError("confirm_enrollment needs a Selection from plan_for_selection")
    if not isinstance(player_name, str) or not player_name.strip():
        raise EnrollmentTokenError("player_name_required", {"track_id": plan.track_id})
    dataset = dataset or plan.dataset
    crops = [_crop_record(index, candidate.frame_index, candidate.t,
                          candidate.det_score, candidate.eye_px,
                          crop_jpeg(root, dataset, candidate.frame_index, candidate.bbox))
             for index, candidate in enumerate(plan.enrollment.crops)]
    expected = enrollment_token(dataset, plan.track_id, crops)
    if not isinstance(token, str) or token != expected:
        raise EnrollmentTokenError("token_mismatch",
                                   {"track_id": plan.track_id, "dataset": dataset,
                                    "expected": expected,
                                    "received": token if isinstance(token, str) else None,
                                    "crops": len(crops),
                                    "frame_indices": [crop["frame_index"] for crop in crops]})
    state = state if state is not None else load_state(root)
    enrollment = plan_enrollment(plan.enrollment.crops, track_id=plan.track_id,
                                 player_name=player_name, state=state, created_at=created_at)
    if not enrollment.ok:                                   # pragma: no cover - crops were vetted already
        return {"ok": False, "reason": enrollment.reason, "message": enrollment.message(),
                "detail": enrollment.detail}
    scratch_root = (Path(scratch_root) if scratch_root is not None
                    else Path(root) / "out" / "enroll-eval" / "scratch")
    written = write_enrollment(scratch_root, enrollment, source_root=root)
    roster = enrollment.roster_json
    return {"ok": True, "player_id": enrollment.player_id, "player_name": enrollment.player_name,
            "revision": None if roster is None else roster.get("revision"),
            "embeddings": len(enrollment.crops), "event": "player_enroll_from_tracklet",
            "track_id": plan.track_id, "dataset": dataset, "written": written, "token": expected}
