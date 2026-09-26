"""PostgresStore: the Store interface (src/store.py) on the pool database.

Selected by open_store() when POOL_DATABASE_URL is set.  Schema: db/migrations
0001-0002 (docs/postgres-design.md sections 2-4); migrate before use
(`python -m src.db`).  Nothing calls it yet - the server still reads the files.

How it keeps the contracts of JsonStore (tests/test_store_contract.py runs the
same cases against both):
  * operations: every mutation is one transaction that locks the single ops_meta
    row (SELECT ... FOR UPDATE, design 2.3), checks the revision (ConflictError =
    409 when stale), runs the application's own Operations._apply on the document
    and writes the changed document back.  The tournament rules live in one place.
    The event log keeps every event; ops_get returns the last 500, like the file.
  * every read method runs in a READ ONLY transaction, so a read cannot write
    (design 7.2); PostgreSQL refuses any write inside one.
  * floats are double precision, so every value the files hold round-trips exactly.
  * precomputed artifacts (design 5, 6) are NOT in the database yet: artifact(),
    queue(), queue_window() and tracklets() read the same JSON files JsonStore does,
    and frame_detections() has no table yet (None = compute live).

The document <-> rows mapping is src.store_import.OperationsSet (the import uses
the same code), so what the store writes is what the import verifies.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

from src import db
from src.store import BALL_SETS, DATASETS, JsonStore

MAX_EVENTS = 500


class PostgresStore:
    def __init__(self, root, url: str | None = None, *, search_path: str | None = None):
        self.root = Path(root).resolve()
        self._url = url or db.database_url()
        self._search_path = search_path          # tests: a throwaway schema
        self._files = JsonStore(root)            # precomputed artifacts only (see module doc)
        self._local = threading.local()

    # -- connections ----------------------------------------------------------
    def _conn(self):
        """One connection per thread, reused; the store is shared across request threads."""
        conn = getattr(self._local, "conn", None)
        if conn is None or conn.closed:
            conn = db.connect(self._url)
            if self._search_path:
                conn.execute("SELECT set_config('search_path', %s, false)", (self._search_path,))
            self._local.conn = conn
        return conn

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    @contextmanager
    def _write(self):
        conn = self._conn()
        with conn.transaction():
            yield conn

    @contextmanager
    def _read(self):
        """A READ ONLY transaction: any write inside it is refused by PostgreSQL."""
        conn = self._conn()
        conn.read_only = True
        try:
            with conn.transaction():
                yield conn
        finally:
            conn.read_only = None

    # -- operations (design 2) ------------------------------------------------
    def _document(self, conn):
        """The operations document; before anything was imported, the default document
        Operations would create for a missing state.json (it is written by the first post)."""
        from src.store_import import OperationsSet
        doc = OperationsSet().render(conn)
        if doc is None:
            from annotator.operations import Operations
            empty = Operations(self.root / "nonexistent-root")   # its state.json never exists
            return empty._load()
        return doc

    def _save(self, conn, doc, action, context):
        """Write the mutated document and append its event, in the caller's transaction.
        Every table but players and ops_events is rewritten from the document (players
        are upserted so their identity bindings survive); the event log only grows."""
        from annotator.operations import timestamp, uid
        from src.store_import import OperationsSet
        doc["revision"] += 1
        event = dict(id=uid(), createdAt=timestamp(), revision=doc["revision"], action=action, context=context)
        spec = OperationsSet()
        for table in ("matches", "entrant_members", "entrants", "tournaments", "notes", "sources", "ops_meta"):
            conn.execute(f"DELETE FROM {table}")
        spec.write(conn, dict(doc, events=[]))             # ops_meta, players, tournaments, notes, sources
        conn.execute("INSERT INTO ops_events (revision, id, created_at, action, context) VALUES (%s, %s, %s, %s, %s)",
                     (event["revision"], event["id"], event["createdAt"], action, _jsonb(context)))
        doc["events"] = (doc.get("events", []) + [event])[-MAX_EVENTS:]
        return doc

    def _locked(self, conn):
        """Serialise operations writers for this transaction (design 2.3).

        The ops_meta row lock alone cannot serialise the very first write: before
        anything was imported there is no row to lock, so concurrent first posts all
        pass the revision check (measured: 7 of 8 then failed on the ops_meta key
        instead of getting a 409). A transaction-scoped advisory lock taken first
        serialises every writer, row or no row; FOR UPDATE then pins the row."""
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('pool:ops_meta'))")
        row = conn.execute("SELECT revision FROM ops_meta FOR UPDATE").fetchone()
        return None if row is None else row[0]

    def ops_get(self) -> dict:
        with self._read() as conn:
            return self._document(conn)

    def ops_post(self, payload: dict) -> dict:
        from annotator.operations import ConflictError, Operations
        if not isinstance(payload, dict):
            raise ValueError("JSON object required")
        ops = Operations.__new__(Operations)              # the rules only; no file, no lock
        with self._write() as conn:
            self._locked(conn)
            doc = self._document(conn)
            if type(payload.get("revision")) is not int:
                raise ValueError("integer revision required")
            if payload["revision"] != doc["revision"]:
                raise ConflictError("State changed; reload before retrying")
            return self._apply_and_save(conn, ops, doc, payload)

    def _apply_and_save(self, conn, ops, doc, payload):
        from annotator.operations import default_name
        if payload.get("action") in ("tournament_start", "tournament_new"):
            t = doc["tournament"]
            if not t["name"].strip() and (payload["action"] == "tournament_start" or t["entrants"] or t["matches"]):
                t["name"] = default_name()
        context = ops._event_context(doc, payload)
        ops._apply(doc, payload)
        if payload.get("action") not in ("tournament_new", "tournament_delete"):
            context.update(ops._event_context(doc, payload))
        return self._save(conn, doc, payload["action"], context)

    def enroll_player(self, player: dict, context: dict) -> dict:
        from annotator.operations import text, timestamp
        with self._write() as conn:
            self._locked(conn)
            doc = self._document(conn)
            if not any(existing.get("id") == player["id"] for existing in doc["players"]):
                name = text(player.get("name"), "name")
                if any(existing["name"].casefold() == name.casefold() for existing in doc["players"]):
                    raise ValueError("Player name already exists")
                doc["players"].append({"joinedAt": timestamp(), "rating": 0, "status": "Active",
                                       **player, "name": name})
            return self._save(conn, doc, "player_enroll_from_tracklet", context)

    # -- identity (design 3) ----------------------------------------------------
    def identity_load(self) -> dict:
        from src.store_import import IdentitySet
        with self._read() as conn:
            return IdentitySet().render(conn)

    def identity_save(self, clusters: dict) -> None:
        """Replace the identity index with `clusters` (the IdentityIndex.save payload)."""
        from src.store_import import IdentitySet
        spec = IdentitySet()
        with self._write() as conn:
            spec.clear(conn)
            spec.write(conn, clusters)

    def faces_load(self) -> dict:
        from src.store_import import FacesSet
        with self._read() as conn:
            return FacesSet().render(conn)

    def faces_add(self, additions: dict) -> dict:
        from src.face_id import EMBEDDING_DIM
        from src.store_import import FacesSet
        from datetime import datetime, timezone
        import numpy as np
        with self._write() as conn:
            conn.execute("LOCK TABLE face_embeddings IN SHARE ROW EXCLUSIVE MODE")
            for player_id, entries in additions.items():
                start = conn.execute("SELECT coalesce(max(position) + 1, 0) FROM face_embeddings WHERE player_id = %s",
                                     (str(player_id),)).fetchone()[0]
                for offset, entry in enumerate(entries):
                    embedding = [round(float(v), 4) for v in np.asarray(entry["embedding"], np.float32).ravel()[:EMBEDDING_DIM]]
                    conn.execute(
                        "INSERT INTO face_embeddings (player_id, embedding, eye_px, det_score, created_at, source, position) "
                        "VALUES (%s, %s::double precision[], %s, %s, %s, %s, %s)",
                        (str(player_id), embedding, entry.get("eye_px"), entry.get("det_score"),
                         entry.get("created_at") or datetime.now(timezone.utc).isoformat(), entry.get("source"),
                         start + offset))
            return FacesSet().render(conn)

    def faces_remove(self, player_id: str) -> int:
        with self._write() as conn:
            return conn.execute("DELETE FROM face_embeddings WHERE player_id = %s", (str(player_id),)).rowcount

    def seeds_get(self, dataset: str) -> dict:
        self._seeds_dataset(dataset)
        from src.store_import import SeedsSet
        with self._read() as conn:
            return SeedsSet().render(conn)["seeds"]

    def seed_put(self, dataset: str, key: str, record: dict | None) -> dict:
        self._seeds_dataset(dataset)
        from src.store_import import SeedsSet
        with self._write() as conn:
            if record is None:
                conn.execute("DELETE FROM track_seeds WHERE dataset = 'vod30' AND seed_key = %s", (key,))
            else:
                old = conn.execute("SELECT win, track_id, t, label, extra FROM track_seeds WHERE dataset = 'vod30' "
                                   "AND seed_key = %s FOR UPDATE", (key,)).fetchone()
                merged = {}
                if old:
                    win, track_id, t, label, extra = old
                    merged = {**extra, "win": win, "track_id": track_id, "label": label}
                    if t is not None:
                        merged["t"] = t
                merged.update(record)
                conn.execute("DELETE FROM track_seeds WHERE dataset = 'vod30' AND seed_key = %s", (key,))
                SeedsSet().write(conn, {"seeds": {key: merged}})
            return SeedsSet().render(conn)["seeds"]

    @staticmethod
    def _seeds_dataset(dataset):
        if dataset != "vod30":
            raise ValueError("seeds exist for vod30 only")

    # -- operator records (design 4) --------------------------------------------
    @staticmethod
    def _dataset(dataset):
        if dataset not in DATASETS:
            raise ValueError(f"unknown dataset: {dataset}")

    def verdicts_get(self, dataset: str) -> dict:
        self._dataset(dataset)
        from src.store_import import VerdictsSet
        with self._read() as conn:
            return VerdictsSet().render(conn).get(dataset, {})

    def verdict_put(self, dataset: str, event_id, fields: dict) -> dict:
        from datetime import datetime, timezone
        from src.store_import import VerdictsSet
        self._dataset(dataset)
        key = str(event_id)
        with self._write() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('event_verdicts:' || %s || ':' || %s))", (dataset, key))
            current = VerdictsSet().render(conn).get(dataset, {}).get(key, {})
            record = dict(current, **fields)
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            conn.execute("DELETE FROM event_verdicts WHERE dataset = %s AND event_id = %s", (dataset, key))
            VerdictsSet().write(conn, {dataset: {key: record}})
            return record

    @staticmethod
    def _crop_set(crop_set):
        if crop_set not in BALL_SETS:
            raise ValueError(f"unknown ball set: {crop_set}")

    def labels_get(self, crop_set: str) -> dict:
        self._crop_set(crop_set)
        with self._read() as conn:
            return {key: label for key, label in conn.execute(
                "SELECT crop_key, label FROM ball_labels WHERE crop_set = %s ORDER BY crop_key", (crop_set,)).fetchall()}

    def label_put(self, crop_set: str, crop_file: str, label) -> None:
        self._crop_set(crop_set)
        with self._write() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('ball_labels:' || %s || ':' || %s))", (crop_set, crop_file))
            keys = [row[0] for row in conn.execute(
                "SELECT crop_key FROM ball_labels WHERE crop_set = %s AND crop_file = %s ORDER BY crop_key",
                (crop_set, crop_file)).fetchall()]
            key = keys[0] if keys else crop_file
            conn.execute("DELETE FROM ball_labels WHERE crop_set = %s AND crop_file = %s", (crop_set, crop_file))
            if label is not None:
                conn.execute("INSERT INTO ball_labels (crop_set, crop_key, crop_file, label) VALUES (%s, %s, %s, %s)",
                             (crop_set, key, crop_file, _jsonb(label)))

    def correction_get(self, dataset: str, frame_index: int) -> dict | None:
        self._dataset(dataset)
        with self._read() as conn:
            row = conn.execute("SELECT payload FROM frame_corrections WHERE dataset = %s AND frame_index = %s",
                               (dataset, int(frame_index))).fetchone()
            return None if row is None else row[0]

    def correction_put(self, dataset: str, frame_index: int, payload: dict) -> None:
        self._dataset(dataset)
        with self._write() as conn:
            conn.execute("INSERT INTO frame_corrections (dataset, frame_index, payload, saved_at) VALUES (%s, %s, %s, %s) "
                         "ON CONFLICT (dataset, frame_index) DO UPDATE SET payload = EXCLUDED.payload, "
                         "saved_at = EXCLUDED.saved_at",
                         (dataset, int(frame_index), _jsonb(payload), (payload or {}).get("saved_at")))

    def anchors_get(self, dataset: str) -> dict:
        self._dataset(dataset)
        with self._read() as conn:
            return {"anchors": {t_key: pts for t_key, pts in conn.execute(
                "SELECT t_key, pts FROM pocket_anchors WHERE dataset = %s ORDER BY t", (dataset,)).fetchall()}}

    def anchors_put(self, dataset: str, t_key: str, pts: list) -> None:
        self._dataset(dataset)
        with self._write() as conn:
            conn.execute("INSERT INTO pocket_anchors (dataset, t_key, t, pts) VALUES (%s, %s, %s, %s) "
                         "ON CONFLICT (dataset, t) DO UPDATE SET pts = EXCLUDED.pts, updated_at = now()",
                         (dataset, str(t_key), float(t_key), _jsonb(pts)))

    # -- precomputed (design 5, 6): still the JSON files, see the module doc --
    def artifact(self, kind: str, dataset: str):
        return self._files.artifact(kind, dataset)

    def queue(self, dataset: str) -> list:
        return self._files.queue(dataset)

    def queue_window(self, dataset: str, t0: float, t1: float) -> list:
        return self._files.queue_window(dataset, t0, t1)

    def tracklets(self, dataset: str) -> dict:
        return self._files.tracklets(dataset)

    def frame_detections(self, dataset: str, frame_index: int):
        return None


def _jsonb(value):
    from psycopg.types.json import Jsonb
    return Jsonb(value)
