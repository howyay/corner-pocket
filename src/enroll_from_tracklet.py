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

Two paths, same gates. `plan_for_cluster(root, cluster_id, ...)` is the fast one:
it plans from identity evidence the pipeline already stored and never re-decodes
video; a stored face must clear the same quality gates, and a single stored face is
reported as `cross_checked=False` because one face cannot be cross-checked.
`plan_for_selection(root, dataset, frame_index, bbox)` is the slow one: it samples
the frames nearest the click first and stops as soon as it has K crops with a
consistency check, so a preview costs a handful of inferred frames instead of the
whole window. `preview_payload` carries `evidence {source, crops, cross_checked,
purity}` so the operator sees which of the two they are confirming.

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

In-process interface. The annotator server uses six names and no others. It imports
them inside its two enrolment handlers (annotator/unified_server.py), where one
handler only reads and the next one writes:

- `plan_for_cluster(root, cluster_id, ...)` -> `Selection` or `Refusal`: the fast
  path, built from evidence the identity index already stored.
- `plan_for_selection(root, dataset, frame_index, bbox, ...)` -> `Selection` or
  `Refusal`: the slow path, built from the frame the operator clicked.
- `Selection`: the plan the preview holds. It carries `dataset`, `track_id`,
  `frames_scanned`, and `enrollment` with its `crops` and `evidence`.
- `preview_payload(plan, *, root, dataset)` -> a JSON-safe dict. The crops travel
  as data URLs and an `ok` payload carries the confirmation `token`. It reads only.
- `confirm_enrollment(root, plan, token, player_name, *, scratch_root, dataset,
  store)` -> the one write on this path. It recomputes the token first.
- `EnrollmentTokenError`: the typed refusal `confirm_enrollment` raises in place of
  a write. `to_dict()` is already the payload the server returns.

No name is missing from that list. The server tests build a `Selection` out of
`Candidate`, `Enrollment`, `plan_enrollment` and `enrollment_token`, and they read
the roster with `load_state`. Those names belong to the same seam.

Import weight. An import of this module must not load the vision stack or a command
line parser. It imports numpy and src.face_id only, and src.face_id itself imports
the standard library and numpy alone. `cv2` and `src.person_pipeline` (which brings
`torch`) load inside `scan_frames`, `scan_nearest`, `crop_jpeg`, `render_sheet`,
`_crop_image`, `_infer` and `bench`; `argparse` loads inside `main` and
`_bench_main`. A fresh interpreter therefore prints `False False` for:
  python -c "import sys, src.enroll_from_tracklet; print('cv2' in sys.modules, 'argparse' in sys.modules)"
`REPO` is the only value the interface needs at import time, so this module keeps
its own copy of it.
"""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.atomic_write import write_atomic
from src.datasets import STATIC
from src.face_id import MIN_DET_SCORE, MIN_EYE_PX
from src.ops_event_log import trim

# The repository root. The value equals src.person_pipeline.REPO, and the same
# expression is used there, but this module keeps its own copy: an import of
# src.person_pipeline loads torch and cv2 at its top level.
REPO = Path(__file__).resolve().parents[1]

#: The built-in recordings this module can enroll from: id -> media path relative to
#: the repository root.  ``src.datasets.STATIC`` owns the file names and this module
#: only prefixes the folder its call sites join onto a root.
DATASETS = {key: str(Path("data") / value[1]) for key, value in STATIC.items()}
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
    "no_stored_evidence",   # the identity index holds no usable face for that cluster
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


def load_state(root=REPO, store=None) -> dict:
    """The operations document: from `store` (a src.store Store) when given, else the
    state.json file under `root` ({} when it does not exist).

    The two answers differ only where nothing reads them: a missing file gives {} and
    the store gives its default document. Both carry an empty `players` list, and that
    list is the only field the enrolment reads (see `_player_id_from_name`)."""
    if store is not None:
        return store.get()
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
            "no_stored_evidence": "no stored face for this person yet: the frames have to be scanned",
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
    payload["events"] = trim(payload.get("events", []) + [event])
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
    from src.person_pipeline import PersonPipeline
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

    def dump(stream) -> None:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")

    # The temp file is <name>.tmp<pid> beside the target, and a failed write leaves
    # it: the behavior this writer always had (no fsync, no cleanup).
    write_atomic(path, dump, temp_name="{name}.tmp{pid}", encoding="utf-8",
                 remove_on_failure=False)


# --------------------------------------------------------------------------
# the operator seam: click a person, see the crops, confirm with a name
# --------------------------------------------------------------------------

CROP_PAD = 0.6            # padding around the face box, as a fraction of its size
CROP_SCALE = 4            # nearest-neighbour upscale for the preview
CROP_QUALITY = 85         # JPEG quality; ~15-25 KB per crop at 4x
CROP_MAX_BYTES = 40_000   # the per-crop budget the UI was promised
PREVIEW_CROPS = 5
SELECTION_IOU_MIN = 0.2   # a click must overlap the person box at least this much
NEAREST_MAX_FRAMES = 6    # hard cap on inferred frames per preview
NEAREST_SPAN_S = 5        # window half-width in seconds for the slow path


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
    """What the operator's click locked onto: one IoU track plus its enrolment.

    `source` says where the evidence came from ("cluster_face" = a stored face, no
    inference; "window_scan" = frames were inferred) and `cross_checked` says
    whether more than one face backs it — a single stored face cannot be
    cross-checked and the payload must not imply otherwise.
    """
    dataset: str | None
    frame_index: int | None
    track_id: int
    selection_iou: float
    frames_seen: int
    enrollment: Enrollment
    source: str = "window_scan"
    frames_scanned: int | None = None
    context: dict = field(default_factory=dict, repr=False)   # observations, for rendering

    @property
    def ok(self) -> bool:
        return True

    @property
    def cross_checked(self) -> bool:
        return len(self.enrollment.crops) > 1

    def to_dict(self) -> dict:
        return {"ok": True, "dataset": self.dataset, "frame_index": self.frame_index,
                "track_id": self.track_id, "selection_iou": round(float(self.selection_iou), 4),
                "frames_seen": self.frames_seen, "source": self.source,
                "cross_checked": self.cross_checked, "frames_scanned": self.frames_scanned,
                "enrollment": self.enrollment.to_dict()}


def plan_for_selection(root, dataset, frame_index, bbox, *, observations=None,
                       scan="nearest", window_s=180, span_s=NEAREST_SPAN_S,
                       max_frames=NEAREST_MAX_FRAMES, min_crops=MIN_KEPT_DEFAULT,
                       stride=30, min_selection_iou=SELECTION_IOU_MIN,
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
        engines = {key: value for key, value in kwargs.items()
                   if key in ("detector", "engine", "log")}
        if scan == "nearest":
            # stop as soon as the click's person has `min_crops` mutually
            # consistent crops; K is the cap, not a requirement to keep sampling
            clicked = {"track_id": None}

            def enough(scanned):
                if clicked["track_id"] is None:
                    scored = sorted(((iou(bbox, person["bbox"]), int(person["track_id"]))
                                     for person in scanned[0].get("persons", [])), reverse=True)
                    if not scored or scored[0][0] < min_selection_iou:
                        return True
                    clicked["track_id"] = scored[0][1]
                candidates = collect_face_candidates(scanned, clicked["track_id"])
                if len(candidates) < min_crops:
                    return False
                return plan_enrollment(candidates, track_id=clicked["track_id"],
                                       player_name="probe", min_kept=min_crops).ok

            observations = scan_nearest(root, dataset, from_frame, span_frames=span_s * 30,
                                        stride=stride, stop_when=enough, max_frames=max_frames,
                                        **engines)
        else:
            observations = scan_frames(root, dataset, max(0, from_frame - window_s * 30),
                                       from_frame + window_s * 30, stride, **engines)
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
                     source="window_scan", frames_scanned=len(observations),
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
            "evidence": {"source": selection.source, "crops": len(crops),
                         "cross_checked": selection.cross_checked,
                         "purity": evidence.get("purity"),
                         "frames_scanned": selection.frames_scanned},
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
        "evidence": {"source": "window_scan", "crops": len(crops), "cross_checked": False},
        "detail": {key: value for key, value in detail.items() if key != "track_id"}})


def confirm_enrollment(root, plan, token, player_name, *, scratch_root=None, dataset=None,
                       state=None, created_at=None, store=None) -> dict:
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
    if state is None:
        state = load_state(root) if store is None else load_state(root, store=store)
    preview = plan.enrollment.evidence or {}
    enrollment = plan_enrollment(plan.enrollment.crops, track_id=plan.track_id,
                                 player_name=player_name, state=state, created_at=created_at,
                                 k=preview.get("k", K_DEFAULT),
                                 min_kept=preview.get("min_kept", MIN_KEPT_DEFAULT))
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


# --------------------------------------------------------------------------
# identity groups + the sheets the operator confirms from
# --------------------------------------------------------------------------

def identity_groups(observations, track_ids=None, *, consistency=CONSISTENCY_COSINE) -> dict:
    """Greedy clustering of every usable face: which tracks are the same person.

    One cluster per person, seeded by the best face and grown at `consistency`
    cosine (the same bar the enrolment uses). Each track is assigned to the group
    holding most of its faces. This is what makes "bind this player's other faces
    and not the other player's" measurable without human labels; it is
    face-derived, so it measures internal consistency, not true identity.
    """
    if track_ids is None:
        track_ids = [row["track_id"] for row in persistent_tracks(observations)]
    medoids, members = [], []
    for track_id in track_ids:
        for candidate in collect_face_candidates(observations, track_id):
            for index, medoid in enumerate(medoids):
                if cosine(candidate.embedding, medoid) >= consistency:
                    members[index].append((track_id, candidate))
                    break
            else:
                medoids.append(candidate.embedding)
                members.append([(track_id, candidate)])
    votes = {}
    for index, rows in enumerate(members):
        for track_id, _candidate in rows:
            votes.setdefault(track_id, {})
            votes[track_id][index] = votes[track_id].get(index, 0) + 1
    return {"groups": len(medoids),
            "faces_per_group": [len(rows) for rows in members],
            "track_group": {track_id: max(counts, key=counts.get) for track_id, counts in votes.items()},
            "members": members}


def bind_counts(observations, enrollment, groups, *, bar=None) -> dict:
    """'Binds its own faces, not the other player's' for one enrolment.

    own: probes from the same identity group in other tracks. other: probes from
    every other group (and tracks the grouping never saw a face for).
    """
    from src.face_id import DEFAULT_BIND_BAR
    bar = DEFAULT_BIND_BAR if bar is None else float(bar)
    gallery = [np.asarray(entry["embedding"], np.float32)
               for entry in list(enrollment.store_json.values())[0]]
    track_group = groups["track_group"]
    my_group = track_group.get(enrollment.track_id)
    own, foreign = [], []
    for track_id in {row["track_id"] for row in persistent_tracks(observations)}:
        if track_id == enrollment.track_id:
            continue
        for candidate in collect_face_candidates(observations, track_id):
            similarity = max(cosine(candidate.embedding, entry) for entry in gallery)
            (own if track_group.get(track_id) == my_group else foreign).append(similarity)
    return {"own": {"n": len(own), "bound": sum(1 for value in own if value >= bar),
                    "stats": stats(own), "bar": bar},
            "other": {"n": len(foreign), "clearing": sum(1 for value in foreign if value >= bar),
                      "stats": stats(foreign), "bar": bar}}


def render_sheet(path, header_lines, crops, *, label_height=26, header_pad=8, line_height=22,
                 background=(24, 24, 24), foreground=(240, 240, 240)) -> str:
    """One contact sheet: the kept crops side by side, labelled, under a header.

    `crops` is a list of (bgr_image, label) pairs. Pure cv2/numpy; writes a JPEG.
    """
    import cv2
    images = [image for image, _label in crops]
    if not images:
        raise ValueError("a sheet needs at least one crop")
    height = max(image.shape[0] for image in images)
    cells = []
    for image, label in crops:
        canvas = np.full((height + label_height, image.shape[1], 3), background, np.uint8)
        canvas[:image.shape[0], :image.shape[1]] = image
        cv2.putText(canvas, label, (4, height + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                    foreground, 1, cv2.LINE_AA)
        cv2.line(canvas, (0, 0), (0, canvas.shape[0] - 1), (90, 90, 90), 1)
        cells.append(canvas)
    strip = np.hstack(cells)
    header = np.full((header_pad * 2 + line_height * len(header_lines), strip.shape[1], 3),
                     background, np.uint8)
    for index, line in enumerate(header_lines):
        cv2.putText(header, line, (6, header_pad + 16 + index * line_height),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, foreground, 1, cv2.LINE_AA)
    sheet = np.vstack([header, strip])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError("sheet encode failed")
    path.write_bytes(encoded.tobytes())
    return str(path)


def _crop_image(root, dataset, candidate, *, scale=CROP_SCALE, pad=CROP_PAD):
    import cv2
    jpeg = crop_jpeg(root, dataset, candidate.frame_index, candidate.bbox, scale=scale, pad=pad)
    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)


def render_sheets(root=REPO, directory=None, dataset="vod30", *, fps=30.0, log=print) -> dict:
    """Write out/enroll-eval/sheets/track-<id>.jpg and index.md for every enrolment."""
    directory = Path(directory) if directory is not None else Path(root) / "out" / "enroll-eval"
    observations = json.loads((directory / "observations.json").read_text(encoding="utf-8"))
    groups = identity_groups(observations)
    sheets_dir = directory / "sheets"
    rows = []
    for track in persistent_tracks(observations):
        result = plan_for_track(observations, track["track_id"],
                                player_name=f"track-{track['track_id']}", state={})
        if not result.ok:
            continue
        counts = bind_counts(observations, result, groups)
        evidence = result.evidence
        first_s = track["first_frame"] / fps
        last_s = track["last_frame"] / fps
        header = [
            f"track {track['track_id']}  group {groups['track_group'].get(track['track_id'])}  "
            f"frames {track['frames']}  first seen {int(first_s // 60)}:{first_s % 60:04.1f}  "
            f"last {int(last_s // 60)}:{last_s % 60:04.1f}",
            f"kept {evidence['kept']}/{evidence['usable_faces']} usable  "
            f"purity {evidence['purity']} over {evidence['purity_probes']} probes  "
            f"own {counts['own']['bound']}/{counts['own']['n']} bound  "
            f"other {counts['other']['clearing']}/{counts['other']['n']} clearing {counts['own']['bar']}",
        ]
        crops = [(_crop_image(root, dataset, candidate),
                  f"f{candidate.frame_index} det {candidate.det_score:.2f} eye {candidate.eye_px:.1f}")
                 for candidate in result.crops]
        path = sheets_dir / f"track-{track['track_id']}.jpg"
        render_sheet(path, header, crops)
        rows.append({"track_id": track["track_id"], "group": groups["track_group"].get(track["track_id"]),
                     "frames": track["frames"], "first_frame": track["first_frame"],
                     "first_s": round(first_s, 1), "kept": evidence["kept"],
                     "usable": evidence["usable_faces"], "purity": evidence["purity"],
                     "purity_probes": evidence["purity_probes"],
                     "own_bound": counts["own"]["bound"], "own_n": counts["own"]["n"],
                     "other_clearing": counts["other"]["clearing"], "other_n": counts["other"]["n"],
                     "sheet": str(path.relative_to(directory))})
        log(f"sheet {path.name}: own {counts['own']['bound']}/{counts['own']['n']} "
            f"other {counts['other']['clearing']}/{counts['other']['n']}", flush=True)
    lines = ["# Enrolment sheets", "",
             f"{len(rows)} enrolable tracks in {len(persistent_tracks(observations))} IoU tracks "
             f"({groups['groups']} identity groups) over {len(observations)} sampled frames.", "",
             "Open a sheet and name the person: the crops are the faces that would be enrolled, "
             "labelled with their detection score and eye distance.", "",
             "| track | group | first seen | frames | kept | purity | own faces bound | other clearing bar | sheet |",
             "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        first = f"{int(row['first_s'] // 60)}:{row['first_s'] % 60:04.1f}"
        purity = "n/a" if row["purity"] is None else f"{row['purity']:.2f} ({row['purity_probes']})"
        lines.append(f"| {row['track_id']} | {row['group']} | {first} | {row['frames']} | "
                     f"{row['kept']}/{row['usable']} | {purity} | "
                     f"{row['own_bound']}/{row['own_n']} | {row['other_clearing']}/{row['other_n']} | "
                     f"[jpg]({row['sheet']}) |")
    lines += ["", "Notes:",
              "- `purity` = share of this track's other usable faces that agree with the kept set "
              "(`n/a` means the track had no other face to check, so purity was not measurable).",
              "- `own faces bound` / `other clearing bar` are face-group derived: `own` counts faces "
              "of tracks in the same identity group, `other` counts faces the grouping placed in a "
              "different group. The grouping itself is face-based, so `other` can include the same "
              "person in a track it split - treat that column as an upper bound on the risk, and "
              "the sheets as the tie-breaker."]
    (sheets_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"sheets": len(rows), "rows": rows, "index": str(sheets_dir / "index.md"),
            "groups": groups["groups"]}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="enrol a regular from a person track")
    parser.add_argument("command", choices=("sheets", "bench"))
    parser.add_argument("--dir", default=None)
    parser.add_argument("--root", default=str(REPO))
    parser.add_argument("--dataset", default="vod30")
    args = parser.parse_args(argv)
    if args.command == "sheets":
        report = render_sheets(args.root, args.dir, args.dataset)
        print(json.dumps({"sheets": report["sheets"], "groups": report["groups"],
                          "index": report["index"]}, indent=1))
    return 0


def _main(argv=None):                                   # pragma: no cover - CLI wrapper
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == "bench":
        return _bench_main(_sys.argv[2:])
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(main())


# --------------------------------------------------------------------------
# fast path: plan from identity evidence the pipeline already stored
# --------------------------------------------------------------------------

CLUSTER_INDEX = Path("out") / "identity" / "clusters.json"
CLUSTER_MIN_KEPT = 1      # a stored face is one crop: no consistency evidence


def load_cluster_evidence(root=REPO, cluster_id=None, *, path=None) -> dict:
    """Stored identity evidence per cluster, read-only from the identity index.

    Reads what `IdentityIndex.save()` writes (`out/identity/clusters.json`) plus
    the additive fields the fast path needs: a `face` embedding with its quality
    numbers (`face_eye_px`, `face_det_score`, `face_bbox`, `face_frame_index`), or
    a `face_samples` list of such records. A bare embedding is NOT enough to
    enrol — the quality gates cannot be checked without its eye distance and
    detection score, and this module never weakens them.

    Returns {cluster_id: {"player_id", "last_seen_frame", "samples": [...],
    "faces": n}}, or one cluster's record (or None) when `cluster_id` is given.
    """
    index_path = Path(path) if path is not None else Path(root) / CLUSTER_INDEX
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    records = {}
    for key, entry in (raw.items() if isinstance(raw, dict) else []):
        if not isinstance(entry, dict):
            continue
        samples = []
        for sample in entry.get("face_samples") or []:
            if isinstance(sample, dict) and sample.get("embedding") is not None:
                samples.append({"embedding": sample["embedding"],
                                "eye_px": sample.get("eye_px"),
                                "det_score": sample.get("det_score"),
                                "bbox": sample.get("bbox") or sample.get("face_bbox"),
                                "frame_index": sample.get("frame_index"),
                                "source": sample.get("source") or "cluster_face"})
        if entry.get("face") is not None:
            samples.append({"embedding": entry["face"],
                            "eye_px": entry.get("face_eye_px"),
                            "det_score": entry.get("face_det_score"),
                            "bbox": entry.get("face_bbox"),
                            "frame_index": entry.get("face_frame_index",
                                                     entry.get("last_seen_frame")),
                            "source": "cluster_face"})
        try:
            cid = int(key)
        except (TypeError, ValueError):
            continue
        records[cid] = {"player_id": entry.get("player_id"),
                        "last_seen_frame": entry.get("last_seen_frame"),
                        "samples": samples, "faces": len(samples)}
    if cluster_id is None:
        return records
    return records.get(int(cluster_id), {"player_id": None, "last_seen_frame": None,
                                         "samples": [], "faces": 0})


def usable_cluster_candidates(evidence, *, min_eye_px=MIN_EYE_PX, min_det_score=MIN_DET_SCORE) -> list:
    """Stored samples that clear BOTH quality gates and can be rendered.

    Gated out (never weakened): no eye distance, eye < min_eye_px, det < min_det_score,
    or no face box / frame to render a crop from. Returns Candidates best-ranked first.
    """
    usable = []
    for sample in (evidence or {}).get("samples", []):
        eye, det = sample.get("eye_px"), sample.get("det_score")
        if eye is None or float(eye) < min_eye_px:
            continue
        if det is None or float(det) < min_det_score:
            continue
        if sample.get("bbox") is None or sample.get("frame_index") is None:
            continue
        usable.append(Candidate(frame_index=int(sample["frame_index"]), t=None,
                                bbox=[round(float(v), 2) for v in sample["bbox"]],
                                person_bbox=[round(float(v), 2) for v in sample["bbox"]],
                                det_score=float(det), eye_px=float(eye),
                                embedding=np.asarray(sample["embedding"], np.float32),
                                face_iou=1.0))
    usable.sort(key=lambda candidate: candidate.rank, reverse=True)
    return usable


def plan_for_cluster(root, cluster_id, *, dataset=None, frame_index=None, bbox=None,
                     fallback=False, observations=None, window_s=5, stride=30,
                     player_name=None, state=None, index_path=None, **kwargs):
    """Fast path: plan the enrolment from evidence the pipeline already stored.

    No inference: reads the identity index, checks the stored face against the same
    quality gates, and (when it passes) returns a Selection whose crops are rendered
    from the stored face box/frame — one crop, `cross_checked=False`, source
    `cluster_face`. A stored face that fails a gate, or an index without face
    evidence, refuses with `no_stored_evidence`; with `fallback=True` and a click
    (dataset + frame_index + bbox) it falls through to the window scan instead, so
    the caller can offer the button either way.
    """
    evidence = load_cluster_evidence(root, cluster_id, path=index_path)
    candidates = usable_cluster_candidates(evidence)
    if candidates:
        planned = plan_enrollment(candidates, track_id=int(cluster_id),
                                  player_name=player_name or f"cluster-{cluster_id}",
                                  k=K_DEFAULT, min_kept=CLUSTER_MIN_KEPT,
                                  state=state)
        if planned.ok:
            planned.evidence["evidence_source"] = "cluster_face"
            planned.evidence["cross_checked"] = len(planned.crops) > 1
            planned.evidence["stored_samples"] = evidence.get("faces", len(candidates))
            return Selection(dataset=dataset, frame_index=candidates[0].frame_index,
                             track_id=int(cluster_id), selection_iou=1.0,
                             frames_seen=len(candidates), enrollment=planned,
                             source="cluster_face", frames_scanned=0,
                             context={"observations": None})
    detail = {"cluster_id": int(cluster_id), "dataset": dataset, "frame_index": frame_index,
              "stored_faces": evidence.get("faces", 0),
              "usable_faces": len(candidates),
              "reason_detail": ("the index has no face evidence for this cluster"
                                if not evidence.get("faces") else
                                "the stored face(s) do not clear the quality gates "
                                f"(eye >= {MIN_EYE_PX}, det >= {MIN_DET_SCORE})")
              if not candidates else "the stored faces were rejected by the plan",
              "fallback": bool(fallback)}
    if fallback and dataset is not None and frame_index is not None and bbox is not None:
        planned = plan_for_selection(root, dataset, frame_index, bbox,
                                     observations=observations, window_s=window_s,
                                     stride=stride, player_name=player_name, state=state,
                                     **kwargs)
        if planned.ok:
            planned.enrollment.evidence["evidence_source"] = "window_scan"
            planned.enrollment.evidence["cross_checked"] = len(planned.enrollment.crops) > 1
            planned.enrollment.evidence["fast_path_skipped"] = detail
            planned.context = {**planned.context, "source": "window_scan",
                               "cross_checked": len(planned.enrollment.crops) > 1}
        else:
            planned.detail = {**planned.detail, "fast_path": detail}
            planned.context = {**(planned.context or {}), "dataset": dataset}
        return planned
    return Refusal("no_stored_evidence", detail, context={"dataset": dataset})


# --------------------------------------------------------------------------
# slow path: nearest-first, early-exit window scan
# --------------------------------------------------------------------------

class _IouTracker:
    """Greedy IoU tracking shared by both scans (PersonPipeline._IOU_MATCH rule)."""

    def __init__(self, stride, max_age=TRACK_MAX_AGE):
        self.stride = max(1, int(stride))
        self.grace = self.stride * max_age
        self.tracks = {}
        self.next_id = 1

    def assign(self, frame_index, boxes):
        live = {tid: value for tid, value in self.tracks.items()
                if frame_index - value[0] <= self.grace}
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
                best = self.next_id
                self.next_id += 1
            taken.add(best)
            free.append((best, bbox, float(box.get("conf", 0.0))))
        self.tracks = dict(live)
        for tid, bbox, _conf in free:
            self.tracks[tid] = (frame_index, bbox)
        return free


def _observation(frame_index, fps, free, faces) -> dict:
    return {"frame_index": int(frame_index), "t": round(frame_index / fps, 3),
            "persons": [{"track_id": tid, "bbox": bbox, "conf": round(conf, 4)}
                        for tid, bbox, conf in free],
            "faces": [{"bbox": [round(float(v), 2) for v in face["bbox"]],
                       "eye_px": None if face.get("eye_px") is None else round(float(face["eye_px"]), 2),
                       "det_score": round(float(face["det_score"]), 4),
                       "embedding": (None if float(face["det_score"]) < MIN_DET_SCORE
                                     else [round(float(v), 4) for v in np.asarray(face["embedding"], np.float32)])}
                      for face in faces]}


def _infer(root, detector, engine, dataset):
    import cv2
    from src.person_pipeline import PersonPipeline
    pipeline = PersonPipeline(root)
    detector = detector or pipeline._get_detector()
    if engine is None:
        from src.face_id import get_face_engine
        engine = get_face_engine()
    cap = cv2.VideoCapture(str(Path(root) / DATASETS[dataset]))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {Path(root) / DATASETS[dataset]}")
    return cap, detector, engine


def scan_nearest(root, dataset, frame_index, *, span_frames=150, stride=30,
                 stop_when=None, max_frames=NEAREST_MAX_FRAMES, detector=None,
                 engine=None, log=print) -> list:
    """Sample the frames nearest the click first, stopping as soon as `stop_when`.

    Random access (one seek per sample, not a sequential walk) so the order is by
    distance from the click: 0, +stride, -stride, +2*stride, ... Frames are only
    inferred until `stop_when(observations)` says the plan is ready, `max_frames`
    is reached, or the window is exhausted; the returned list is ordered
    nearest-first and its length is how many frames were actually inferred.
    """
    import cv2
    frame_index = int(frame_index)
    offsets = [0]
    for step in range(1, int(span_frames) // max(1, int(stride)) + 1):
        offsets += [step * stride, -step * stride]
    wanted = [frame_index + offset for offset in offsets if frame_index + offset >= 0]
    cap, detector, engine = _infer(root, detector, engine, dataset)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    tracker = _IouTracker(stride)
    observations = []
    try:
        for index in wanted:
            if max_frames is not None and len(observations) >= max_frames:
                break
            if not cap.set(cv2.CAP_PROP_POS_FRAMES, index):
                continue
            ok, frame = cap.read()
            if not ok:
                continue
            faces = engine.analyze(frame)
            free = tracker.assign(index, detector(frame))
            observations.append(_observation(index, fps, free, faces))
            log(f"nearest f{index} t={index / fps:.1f}s persons={len(free)} faces={len(faces)}",
                flush=True)
            if stop_when is not None and stop_when(observations):
                break
    finally:
        cap.release()
    return observations


# --------------------------------------------------------------------------
# bench: coverage of the fast path, and the slow path's before/after
# --------------------------------------------------------------------------

def bench(root=REPO, directory=None, *, dataset="vod30", frame_index=None, bbox=None,
          track_id=None, span_s=NEAREST_SPAN_S, stride=30, log=print) -> dict:
    """Measure the two paths on a real window: coverage, fast-path cost, slow-path cost.

    Fast-path coverage = of the enrolable tracks in `<dir>/observations.json`, how
    many have usable stored evidence in the identity index today. Slow-path
    before/after = the same clicked person planned by scanning the whole window
    versus the nearest-first early-exit scan.
    """
    import time
    directory = Path(directory) if directory is not None else Path(root) / "out" / "enroll-eval"
    observations = json.loads((directory / "observations.json").read_text(encoding="utf-8"))
    tracks = [row for row in persistent_tracks(observations)
              if plan_for_track(observations, row["track_id"], player_name="probe", state={}).ok]
    index = load_cluster_evidence(root)
    stored = {cluster: record["faces"] for cluster, record in index.items() if record["faces"]}
    report = {"index_clusters": len(index), "index_clusters_with_faces": len(stored),
              "enrolable_tracks": len(tracks), "tracks_with_stored_evidence": 0,
              "coverage": "0/%d" % len(tracks),
              "why": ("no cluster stores a face with its quality numbers: "
                      "PersonPipeline.process_frame passes face_embedding=None "
                      "(src/person_pipeline.py) and IdentityIndex.save() writes face:null, "
                      "so the fast path has nothing to read yet")}
    target = track_id or (tracks[0]["track_id"] if tracks else None)
    if target is not None and frame_index is None:
        planned = plan_for_track(observations, target, player_name="probe", state={})
        if planned.ok:
            frame_index = planned.crops[0].frame_index
            bbox = planned.crops[0].person_bbox
    if frame_index is not None and bbox is not None:
        from src.person_pipeline import PersonPipeline
        from src.face_id import get_face_engine
        detector = PersonPipeline(root)._get_detector()
        engine = get_face_engine()
        started = time.time()
        old = scan_frames(root, dataset, max(0, frame_index - span_s * 30),
                          frame_index + span_s * 30, stride, detector=detector, engine=engine,
                          log=lambda *a, **k: None)
        old_plan = plan_for_selection(root, dataset, frame_index, bbox, observations=old,
                                      player_name="probe", state={})
        before_s = round(time.time() - started, 1)
        started = time.time()
        new_plan = plan_for_selection(root, dataset, frame_index, bbox, scan="nearest",
                                      span_s=span_s, stride=stride, max_frames=None,
                                      detector=detector, engine=engine, player_name="probe",
                                      state={})
        after_s = round(time.time() - started, 1)
        inferred = len((new_plan.context or {}).get("observations") or [])
        started = time.time()
        refusal = plan_for_cluster(root, next(iter(index), 1), dataset=dataset)
        fast_s = round(time.time() - started, 4)
        report.update({
            "clicked": {"frame_index": frame_index, "bbox": bbox, "track_id": target},
            "slow_path_before": {"frames_inferred": len(old), "seconds": before_s,
                                 "ok": old_plan.ok},
            "slow_path_after": {"frames_inferred": inferred, "seconds": after_s,
                                "ok": new_plan.ok,
                                "crops": len(new_plan.enrollment.crops) if new_plan.ok else 0},
            "fast_path_without_evidence": {"seconds": fast_s, "reason": refusal.reason},
        })
    return report


def _bench_main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="measure the enrolment paths")
    parser.add_argument("--dir", default=None)
    parser.add_argument("--root", default=str(REPO))
    parser.add_argument("--frame", type=int, default=None)
    parser.add_argument("--bbox", default=None)
    parser.add_argument("--track", type=int, default=None)
    parser.add_argument("--stride", type=int, default=30)
    args = parser.parse_args(argv)
    bbox = [float(v) for v in args.bbox.split(",")] if args.bbox else None
    report = bench(args.root, args.dir, frame_index=args.frame, bbox=bbox, track_id=args.track,
                   stride=args.stride)
    print(json.dumps(report, indent=1))
    return 0
