"""Cross-exit person identity index.

Associates the same human across repeated exits/entries of the camera view and
binds an enrolled face identity to a cluster. Body embeddings come from a
boxmot ReID encoder (boxmot.reid.create_reid_encoder(...).encode() returns one
[N, D] float32 tensor per frame); this module never downloads weights and is
not tied to the boxmot API — the tracker wiring passes plain numpy vectors
through :meth:`IdentityIndex.update`.

Calibration is per embedding space; the two bars must not be confused:
- FACE (buffalo_l 512-d, measured on this footage): same-person 1s-apart
  cosine median 0.958 (p05 0.644) vs cross-person same-frame 0.077
  (p05 -0.04) -> threshold 0.35 / margin 0.12. The bar bind_face() applies is
  the composed one, DEFAULT_BIND_BAR = 0.47 (threshold + margin); 0.35 alone
  never binds.
- BODY (vendored OSNet x0.25 128-d, measured by tests/test_body_calibration.py
  on frames 8000-12000 of data/vod_30min_260815.mp4 with IoU>=0.6 short-gap
  pseudo-ground-truth): same-person <=1s cosine p05 0.755 / median 0.830 vs
  cross-person same-frame p95 0.882 / median 0.811 — the distributions
  overlap in both directions (different people in one frame reached 0.983;
  one person vs themselves 1s apart dropped to 0.678). Body-only clustering
  cannot separate these players at 1280x720, so BODY matching is DISABLED by
  default (BODY_MATCH_THRESHOLD = BODY_MATCH_DISABLED): every unknown track
  opens its own cluster (face-binding-only mode). Re-association across
  exits still happens through faces: a returning track is a fresh cluster
  that binds to the same player_id via bind_face(). Pass explicit
  body_match_threshold/body_margin to re-enable body merging.

Identity policy (small club, clusters never expire):
- a new track_id starts fresh; with body matching enabled its first embedding
  is compared against all existing clusters: if best cosine >= body threshold
  and best - second_best >= body margin it joins that cluster (cross-exit
  re-association), otherwise it gets a new one;
- explicit_assign() is the authoritative override (player_id, reason);
- bind_face() sets a player binding only when the effective FACE bar is met —
  similarity >= bind_bar (0.47 with the defaults) and, when the runner-up
  similarity is supplied, that runner-up trailing by >= margin — and the
  cluster is unbound. First confident face match wins, never auto-rebound.
  best_match() and bind_face() call the same src.face_id.accept_match() rule,
  so the binding path is never more permissive than the matcher.

Enrolment-face evidence contract: `record_face_sample()` stores the face the
pipeline already computed for a tracked person (embedding + eye distance +
detection score + face box + frame). It is memory only, deliberately separate from
the body bank (no dim guard for a 512-d face), bounded to `face_samples_max` best
samples by det_score * eye_px, and never an identity decision: no player_id, no
evidence, no save. The samples reach JSON only when the index is written anyway
for a real reason (bind_face / explicit_assign), so the read-only rule holds -
a page load or a frame read still cannot rewrite the file.

Persistence contract: register()/update() change memory only — they run while
frames are observed, which includes read requests (GET /api/identity/frame,
GET /api/unified), and a read must not write the index file. The file is written
by bind_face() and explicit_assign(), where a durable decision is actually made
(each save() writes the whole in-memory index, so observation accumulated since
the last write goes out with the next real change), and by an explicit save().
"""
from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

try:  # package import (src.person_identity); tests may load this as a flat module
    from src.face_id import DEFAULT_BIND_BAR, DEFAULT_MARGIN, DEFAULT_THRESHOLD, accept_match
except ImportError:  # pragma: no cover - tests/test_person_identity.py adds src/ to sys.path
    from face_id import DEFAULT_BIND_BAR, DEFAULT_MARGIN, DEFAULT_THRESHOLD, accept_match

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "out" / "identity" / "clusters.json"
BANK_SIZE = 32          # internal body-embedding bank bound per cluster
PERSIST_BANK = 8        # body_bank entries written to JSON (spec: max 8)
PERSIST_FACES = 3       # enrolment face samples kept per cluster (memory + JSON)
FACE_SAMPLE_DECIMALS = 4  # face embeddings are stored rounded, like the face store

# Body (OSNet 128-d) match bar. Calibrated on real footage by
# tests/test_body_calibration.py (real YOLO boxes + vendored OSNet,
# cross-person = same-frame pairs, same-person = IoU>=0.6 links <=1s):
# same-person p05 0.755 / median 0.830 vs cross-person p95 0.882 / median
# 0.811 — overlapping distributions, so NO threshold separates the players
# (a mid-gap 0.35 from the FACE calibration merged 41 tracks into 1 cluster;
# any body threshold that keeps true same-person pairs also merges different
# people measured at up to 0.983 cosine). Body merging is therefore disabled
# by default: identity binding runs on faces only.
BODY_MATCH_DISABLED = float("inf")  # sentinel: never merge on body evidence
BODY_MATCH_THRESHOLD = BODY_MATCH_DISABLED
BODY_MARGIN = 0.0


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _sample_rank(sample: dict[str, Any]) -> float:
    """det_score * eye_px, the same ranking the enrolment module uses."""
    if sample.get("eye_px") is None or sample.get("det_score") is None:
        return 0.0
    return float(sample["det_score"]) * float(sample["eye_px"])


def _vec(embedding: Any, name: str) -> np.ndarray:
    v = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if v.size == 0:
        raise ValueError(f"{name}: empty embedding")
    return v


class _Cluster:
    __slots__ = ("cid", "bank", "face", "faces", "player_id", "evidence", "last_seen_frame")

    def __init__(self, cid: int):
        self.cid = cid
        self.bank: deque[np.ndarray] = deque(maxlen=BANK_SIZE)
        self.face: np.ndarray | None = None
        # Enrolment evidence, deliberately NOT the body bank: 512-d face samples
        # never meet the body dim guard (see record_face_sample). Bounded list,
        # kept in memory, written to JSON only when the index is written anyway.
        self.faces: list[dict[str, Any]] = []
        self.player_id: str | None = None
        self.evidence: dict[str, Any] | None = None
        self.last_seen_frame: int | None = None

    @property
    def summary(self) -> np.ndarray:
        """Running mean of the body bank (comparison summary)."""
        return np.mean(np.stack(self.bank), axis=0)

    def add(self, v: np.ndarray, frame_index: int | None) -> None:
        self.bank.append(v)
        if frame_index is not None:
            self.last_seen_frame = int(frame_index)


class IdentityIndex:
    def __init__(
        self,
        path: str | os.PathLike = DEFAULT_PATH,
        match_threshold: float = DEFAULT_THRESHOLD,
        margin: float = DEFAULT_MARGIN,
        body_match_threshold: float = BODY_MATCH_THRESHOLD,
        body_margin: float = BODY_MARGIN,
        bind_bar: float | None = None,
        face_samples_max: int = PERSIST_FACES,
        store: Any = None,
    ):
        self.path = Path(path)
        # Where the index is persisted: None = the JSON file at `path` (default, as
        # always); a src.store Store = its identity_load / identity_save (the server
        # passes its store, so the index follows it to Postgres).
        self.store = store
        # FACE bar (face_embedding binding via bind_face). The number bind_face
        # actually applies is bind_bar; None keeps the composed default
        # (match_threshold + margin = 0.47), so tuning the matcher threshold
        # moves the binding bar with it. Pass bind_bar explicitly to pin the
        # bar on its own (src.face_id.CANDIDATE_BIND_BAR is the measured
        # candidate; see docs/face-identification-assessment.md).
        self.match_threshold = float(match_threshold)
        self.margin = float(margin)
        self.bind_bar = None if bind_bar is None else float(bind_bar)
        # BODY bar (OSNet cross-exit cluster merging); inf by default -> body
        # matching disabled, one cluster per tracker track (see module docstring)
        self.body_match_threshold = float(body_match_threshold)
        self.body_margin = float(body_margin)
        # Enrolment face evidence bound (top-K by det_score * eye_px, K small):
        # this is enrolment evidence, never an identity decision.
        self.face_samples_max = max(1, int(face_samples_max))
        self._clusters: dict[int, _Cluster] = {}
        self._next_id = 1
        self._track_to_cluster: dict[int, int] = {}
        self._dim: int | None = None
        self._load()

    @property
    def effective_bind_bar(self) -> float:
        """The similarity bind_face() requires: bind_bar, else threshold + margin.

        Defaults to DEFAULT_BIND_BAR (0.47). This is the number to quote when
        tuning the binding behaviour; 0.35 never binds on its own.
        """
        if self.bind_bar is not None:
            return self.bind_bar
        return round(self.match_threshold + self.margin, 4)

    # -- registration ------------------------------------------------------

    def register(
        self,
        track_id: int,
        body_embedding: Any,
        face_embedding: Any | None = None,
        frame_index: int | None = None,
        timestamp: float | None = None,
    ) -> dict[int, int]:
        """Admit one track embedding; return {track_id: cluster_id}.

        Re-registering a known track_id is idempotent (same cluster, bank
        refresh). An unknown track joins an existing cluster on a confident
        best-vs-second-best cosine match, else opens a new one.
        """
        v = _vec(body_embedding, f"track {track_id} body_embedding")
        self._check_dim(v)
        cid = self._track_to_cluster.get(track_id)
        if cid is None:
            cid = self._match_or_new(v)
            self._track_to_cluster[track_id] = cid
        cluster = self._clusters[cid]
        cluster.add(v, frame_index)
        if face_embedding is not None and cluster.face is None:
            fv = _vec(face_embedding, f"track {track_id} face_embedding")
            self._check_dim(fv)
            cluster.face = fv
        # No save() here, on purpose. register() runs on the read path (every
        # observed frame goes process_frame -> update -> register, including
        # GET /api/identity/frame and GET /api/unified), and a read must not
        # rewrite the index file: a read-only verification can then compare
        # bytes, and concurrent readers cannot race on the path. What a tracker
        # update changes is rebuildable observation (clusters, banks), not a
        # decision - the index is persisted where a durable change happens,
        # i.e. in bind_face() / explicit_assign(), which write the whole
        # in-memory index (so accumulated observation goes out with them).
        return {track_id: cid}

    def record_face_sample(self, cluster_id: int, embedding: Any, *, eye_px: Any = None,
                           det_score: Any = None, bbox: Any = None,
                           frame_index: int | None = None) -> dict[str, Any]:
        """Record enrolment evidence for one cluster: MEMORY ONLY, never a decision.

        A 512-d face embedding goes into `_Cluster.faces`, a separate list that is
        never compared against the body bank, so the 128-d dim guard is not
        consulted and a face can never be mistaken for a body embedding. This
        writes no player_id, no evidence and no file: it is what the operator's
        "click the person" button reads later, and a stored face still has to
        clear the quality gates before it may be enrolled. Samples are kept
        bounded, best first by det_score * eye_px (missing numbers rank 0, so a
        sample without them can be evicted but never promoted).
        """
        cluster = self._require(cluster_id)
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if vector.size == 0:
            raise ValueError("face sample embedding is empty")
        sample = {"embedding": vector,
                  "eye_px": None if eye_px is None else float(eye_px),
                  "det_score": None if det_score is None else float(det_score),
                  "bbox": None if bbox is None else [float(v) for v in bbox],
                  "frame_index": None if frame_index is None else int(frame_index)}
        sample["rank"] = _sample_rank(sample)
        cluster.faces.append(sample)
        cluster.faces.sort(key=lambda row: row["rank"], reverse=True)
        del cluster.faces[self.face_samples_max:]
        return {"cluster_id": cluster.cid, "samples": len(cluster.faces),
                "kept": any(row is sample for row in cluster.faces),
                "rank": round(sample["rank"], 4)}

    def face_samples(self, cluster_id: int) -> list[dict[str, Any]]:
        """The cluster's stored enrolment samples, best first (read-only view)."""
        return list(self._require(cluster_id).faces)

    def update(self, tracks: list[dict[str, Any]]) -> dict[int, int]:
        """Seam for tracker wiring: list of dicts with keys track_id,
        embedding (or body_embedding), optional face_embedding, frame_index,
        timestamp. Returns {track_id: cluster_id}."""
        out: dict[int, int] = {}
        for t in tracks:
            body = t.get("embedding", t.get("body_embedding"))
            if body is None:
                raise ValueError(f"track {t.get('track_id')}: no embedding")
            out.update(
                self.register(
                    int(t["track_id"]),
                    body,
                    face_embedding=t.get("face_embedding"),
                    frame_index=t.get("frame_index"),
                    timestamp=t.get("timestamp"),
                )
            )
        return out

    # -- identity bindings -------------------------------------------------

    def explicit_assign(self, cluster_id: int, player_id: str, reason: str = "seed") -> None:
        """Authoritative override: sets player_id regardless of any binding."""
        cluster = self._require(cluster_id)
        cluster.player_id = player_id
        cluster.evidence = {"source": "explicit_assign", "reason": reason, "player_id": player_id}
        self.save()

    def link_track(self, track_id: int, cluster_id: int) -> dict[str, Any]:
        """Associate a tracker track with an identity cluster (operator decision).

        The review panel calls this when an operator says "this body track is that
        identity". The track's own cluster is merged into the target: its body
        bank, its stored face and its enrolment samples move across, every track
        that already pointed at the merged cluster points at the target, and the
        track itself resolves to the target on every later frame, because
        register() reads the same map.

        Two refusals, both deliberate:

        - a cluster bound to a player is never swallowed by a link. One click
          would otherwise move a finished identity into another player's record;
          the caller unbinds it first.
        - an unknown cluster_id is an error, not a new cluster. A link names an
          identity that already exists.

        A link is a real decision, so it saves the index. The link itself lives in
        the running index (tracker ids are session state); the merge it performs
        is persisted in the target cluster.
        """
        tid = int(track_id)
        cid = int(cluster_id)
        target = self._require(cid)
        current = self._track_to_cluster.get(tid)
        if current == cid:
            return {"track_id": tid, "cluster_id": cid, "merged": None, "moved_tracks": 0,
                    "player_id": target.player_id, "already": True}
        merged: int | None = None
        moved = 0
        if current is not None:
            source = self._require(current)
            if source.player_id is not None:
                raise ValueError(
                    f"cluster {current} is bound to {source.player_id!r}; unbind it before linking")
            for value in list(source.bank):
                target.bank.append(value)
            if target.face is None and source.face is not None:
                target.face = source.face
            for sample in source.faces:
                target.faces.append(sample)
            target.faces.sort(key=_sample_rank, reverse=True)
            del target.faces[self.face_samples_max:]
            if source.last_seen_frame is not None:
                target.last_seen_frame = max(target.last_seen_frame or 0, source.last_seen_frame)
            del self._clusters[current]
            for key, value in list(self._track_to_cluster.items()):
                if value == current:
                    self._track_to_cluster[key] = cid
                    moved += 1
            merged = current
        self._track_to_cluster[tid] = cid
        self.save()
        return {"track_id": tid, "cluster_id": cid, "merged": merged,
                "moved_tracks": moved, "player_id": target.player_id, "already": False}

    def bind_face(self, cluster_id: int, player_id: str, similarity: float, evidence: Any = None,
                  runner_up: float | None = None, persist: bool = True) -> bool:
        """Bind player via face match; first confident match only.

        The accept decision is src.face_id.accept_match(), the same rule
        best_match() applies, with bind=True: similarity must reach
        effective_bind_bar (0.47 = match_threshold + margin by default, or an
        explicit bind_bar), and when `runner_up` — the best *other* enrollee's
        cosine, as best_match() reports in its 'runner_up' field — is supplied,
        that runner-up must trail by >= margin. Before this rule was shared, the
        binding path checked only the similarity, so a probe whose runner-up was
        inside the margin could bind (measured consequence: 2 of 35 impostor
        faces at 0.60/0.55 off one enrolment photo, docs/face-identification-
        assessment.md). runner_up=None means no competing enrolment (the
        single-player gallery case).

        Returns True on new binding, False when rejected (no rebinding ever).
        persist=True writes the index here. The person pipeline passes
        persist=False because it binds while serving reads (GET /api/unified,
        GET /api/identity/frame) and a GET never writes: the bind then lives in
        memory and is written by the next genuine mutation (explicit_assign, an
        enrolment, forget), which saves the whole index.
        """
        cluster = self._require(cluster_id)
        if cluster.player_id is not None:
            return False
        if not accept_match(similarity, runner_up, threshold=self.match_threshold,
                            margin=self.margin, bind=True, bind_bar=self.bind_bar):
            return False
        cluster.player_id = player_id
        cluster.evidence = {
            "source": "bind_face",
            "similarity": float(similarity),
            "runner_up": None if runner_up is None else float(runner_up),
            "bind_bar": self.effective_bind_bar,
            "evidence": evidence,
            "player_id": player_id,
        }
        if persist:
            self.save()
        return True

    def get(self, cluster_id: int) -> dict[str, Any]:
        cluster = self._require(cluster_id)
        return {
            "player_id": cluster.player_id,
            "bound_evidence": cluster.evidence,
            "last_seen_frame": cluster.last_seen_frame,
            "samples": len(cluster.bank),
        }

    def clusters(self) -> list[int]:
        return sorted(self._clusters)

    def tracks_of(self, cluster_id: int) -> list[int]:
        """The tracker tracks that resolve to this cluster, ascending (read view)."""
        self._require(cluster_id)
        return sorted(t for t, c in self._track_to_cluster.items() if c == int(cluster_id))

    def track_cluster(self, track_id: int) -> int | None:
        """The cluster a track resolves to, or None when the track is unseen."""
        return self._track_to_cluster.get(int(track_id))

    def forget_player(self, player_id: str) -> dict[str, int]:
        """Remove a player's face data from the index and unbind their clusters.

        Every cluster bound to `player_id` loses its binding, its stored face and its
        enrolment face samples (the 512-d biometrics); the body bank (128-d OSNet,
        not a face) and the cluster itself stay, so tracking is unaffected. Saves
        once when anything changed. Returns what was removed.
        """
        removed = {"clusters_unbound": 0, "face_samples": 0, "faces": 0}
        for cluster in self._clusters.values():
            if cluster.player_id != player_id:
                continue
            removed["clusters_unbound"] += 1
            removed["face_samples"] += len(cluster.faces)
            removed["faces"] += int(cluster.face is not None)
            cluster.player_id = None
            cluster.evidence = None
            cluster.face = None
            cluster.faces = []
        if removed["clusters_unbound"]:
            self.save()
        return removed

    # -- internals ---------------------------------------------------------

    def _check_dim(self, v: np.ndarray) -> None:
        if self._dim is None:
            self._dim = v.shape[0]
        elif v.shape[0] != self._dim:
            raise ValueError(f"embedding dim mismatch: got {v.shape[0]}, expected {self._dim}")

    def _match_or_new(self, v: np.ndarray) -> int:
        sims = {cid: _cos(v, c.summary) for cid, c in self._clusters.items()} if self._clusters else {}
        if sims and self.body_match_threshold != BODY_MATCH_DISABLED:
            ranked = sorted(sims.items(), key=lambda kv: kv[1], reverse=True)
            (best_cid, best) = ranked[0]
            second = ranked[1][1] if len(ranked) > 1 else -1.0
            if best >= self.body_match_threshold and best - second >= self.body_margin:
                return best_cid
        cid = self._next_id
        self._next_id += 1
        self._clusters[cid] = _Cluster(cid)
        return cid

    def _require(self, cluster_id: int) -> _Cluster:
        try:
            return self._clusters[int(cluster_id)]
        except KeyError:
            raise KeyError(f"unknown cluster_id {cluster_id}") from None

    # -- persistence -------------------------------------------------------

    def save(self) -> None:
        payload = {}
        for cid, c in self._clusters.items():
            payload[str(cid)] = {
                "player_id": c.player_id,
                "body_bank": [b.tolist() for b in list(c.bank)[-PERSIST_BANK:]],
                "face": None if c.face is None else c.face.tolist(),
                # Additive: bounded enrolment evidence (top-K by quality). Written
                # here, i.e. only when the index is written for a real reason -
                # never by an observation, so a read cannot rewrite this file.
                "face_samples": [
                    {"embedding": [round(float(v), FACE_SAMPLE_DECIMALS) for v in sample["embedding"]],
                     "eye_px": sample["eye_px"], "det_score": sample["det_score"],
                     "bbox": sample["bbox"], "frame_index": sample["frame_index"]}
                    for sample in c.faces
                ],
                "last_seen_frame": c.last_seen_frame,
            }
        if self.store is not None:
            self.store.identity_save(payload)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
        os.replace(tmp, self.path)  # atomic

    def _load(self) -> None:
        if self.store is not None:
            raw = self.store.identity_load()
        elif not self.path.exists():
            return
        else:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        for cid_s, rec in raw.items():
            cid = int(cid_s)
            c = _Cluster(cid)
            c.player_id = rec.get("player_id")
            c.evidence = None  # not part of the persisted schema
            c.last_seen_frame = rec.get("last_seen_frame")
            for b in rec.get("body_bank", []):
                c.bank.append(np.asarray(b, dtype=np.float32))
            if c.bank:
                self._dim = c.bank[0].shape[0]
            face = rec.get("face")
            if face is not None:
                c.face = np.asarray(face, dtype=np.float32)
            for sample in rec.get("face_samples") or []:
                if not isinstance(sample, dict) or sample.get("embedding") is None:
                    continue
                restored = {"embedding": np.asarray(sample["embedding"], dtype=np.float32),
                            "eye_px": sample.get("eye_px"), "det_score": sample.get("det_score"),
                            "bbox": sample.get("bbox"), "frame_index": sample.get("frame_index")}
                restored["rank"] = _sample_rank(restored)
                c.faces.append(restored)
            c.faces.sort(key=lambda row: row["rank"], reverse=True)
            del c.faces[self.face_samples_max:]
            self._clusters[cid] = c
        if self._clusters:
            self._next_id = max(self._clusters) + 1
