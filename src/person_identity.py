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


def _vec(embedding: Any, name: str) -> np.ndarray:
    v = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if v.size == 0:
        raise ValueError(f"{name}: empty embedding")
    return v


class _Cluster:
    __slots__ = ("cid", "bank", "face", "player_id", "evidence", "last_seen_frame")

    def __init__(self, cid: int):
        self.cid = cid
        self.bank: deque[np.ndarray] = deque(maxlen=BANK_SIZE)
        self.face: np.ndarray | None = None
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
    ):
        self.path = Path(path)
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

    def bind_face(self, cluster_id: int, player_id: str, similarity: float, evidence: Any = None,
                  runner_up: float | None = None) -> bool:
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
        Persists here and not in register(): an automatic match may happen while
        serving a read, but the binding is a durable decision, so it is written
        where it is made rather than by whichever request comes later.
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
                "last_seen_frame": c.last_seen_frame,
            }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
        os.replace(tmp, self.path)  # atomic

    def _load(self) -> None:
        if not self.path.exists():
            return
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
            self._clusters[cid] = c
        if self._clusters:
            self._next_id = max(self._clusters) + 1
