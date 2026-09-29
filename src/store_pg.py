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

import json

from src import db
from src.store import BALL_SETS, JsonStore, StoreConstraintError
from src.store_files import dataset_dir, dump, fmt_of, get_document, put_document

MAX_EVENTS = 500
STATE = "out/corner-pocket/state.json"


def _doc_path(kind: str, key: str) -> str:
    """The file a document-backed record set lives in (same names as JsonStore)."""
    if kind == "seeds":
        return "out/pid_seed.json"
    if kind == "verdicts":
        return f"{dataset_dir(key)}/annotations.json"
    if kind == "labels":
        return f"out/{key}/labels.json"
    if kind == "anchors":
        return f"out/pid_anchors_{key}.json"
    raise ValueError(kind)


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
        """One write transaction. A constraint the 0002 projection enforces (FK, CHECK,
        unique) that the application rules let through rolls the whole write back and
        raises StoreConstraintError naming it - never a silent success."""
        import psycopg
        conn = self._conn()
        try:
            with conn.transaction():
                yield conn
        except psycopg.errors.IntegrityError as error:
            diag = error.diag
            raise StoreConstraintError(diag.constraint_name,
                                       f"{type(error).__name__}: {(diag.message_primary or str(error)).strip()}"
                                       + (f" ({diag.message_detail})" if diag.message_detail else "")) from error

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
        """The operations document: the stored state.json text (key order as written,
        0003); before anything was imported, the default document Operations creates
        for a missing state.json (it is written by the first post)."""
        text = get_document(conn, STATE)
        if text is not None:
            return json.loads(text)
        if conn.execute("SELECT 1 FROM ops_meta").fetchone() is not None:
            raise RuntimeError("operations rows exist without their document (imported before migration 0003?); "
                               "re-run `python -m src.store_import --only operations --replace`")
        from annotator.operations import Operations
        return Operations(self.root / "nonexistent-root")._load()   # its state.json never exists

    def _save(self, conn, doc, action, context):
        """Operations._commit, in the caller's transaction: advance the revision, append
        the event (the document keeps the last 500, the table keeps every one), store the
        document in _commit's exact format, and rewrite the row projection from it
        (players are upserted so their identity bindings survive)."""
        from annotator.operations import timestamp, uid
        from src.store_import import OperationsSet
        doc["revision"] += 1
        event = dict(id=uid(), createdAt=timestamp(), revision=doc["revision"], action=action, context=context)
        doc["events"] = (doc.get("events", []) + [event])[-MAX_EVENTS:]
        for table in ("matches", "entrant_members", "entrants", "tournaments", "notes", "sources", "ops_meta"):
            conn.execute(f"DELETE FROM {table}")
        OperationsSet().write(conn, dict(doc, events=[]))  # ops_meta, players, tournaments, notes, sources
        conn.execute("INSERT INTO ops_events (revision, id, created_at, action, context) VALUES (%s, %s, %s, %s, %s)",
                     (event["revision"], event["id"], event["createdAt"], action, _jsonb(context)))
        put_document(conn, STATE, dump(doc, fmt_of(STATE)))
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
        """Replace the identity index with `clusters` (the IdentityIndex.save payload).
        A cluster bound to an id that is not on the roster is refused by the reviewed
        foreign key (identity_clusters_player_id_fkey) with StoreConstraintError."""
        from src.store_import import IdentitySet, Mismatch
        spec = IdentitySet()
        with self._write() as conn:
            spec.clear(conn)
            try:
                spec.write(conn, clusters)
            except Mismatch as error:        # the importer's check for the same foreign key
                raise StoreConstraintError("identity_clusters_player_id_fkey", str(error)) from error

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

    # -- seeds and operator records: documents (0003) + their row projection ------
    # Each write is JsonStore's read-modify-write of the same file, on the stored
    # document, under a per-document advisory lock; the document is stored in the
    # writer's exact format, and the 0002 rows of that set are rewritten from it in
    # the same transaction (their constraints check every write).

    def _load_doc(self, conn, path, default):
        text = get_document(conn, path)
        return default if text is None else json.loads(text)

    def _store_doc(self, conn, path, value, project):
        put_document(conn, path, dump(value, fmt_of(path)))
        project(conn)

    @staticmethod
    def _lock_doc(conn, path):
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("pool:doc:" + path,))

    def seeds_get(self, dataset: str) -> dict:
        return self.seed_file(dataset).get("seeds", {})

    def seed_file(self, dataset: str) -> dict:
        """The whole pid_seed.json document, as stored."""
        self._seeds_dataset(dataset)
        with self._read() as conn:
            return self._load_doc(conn, _doc_path("seeds", dataset), {"seeds": {}})

    def seed_put(self, dataset: str, key: str, record: dict | None) -> dict:
        from src.store_import import SeedsSet
        self._seeds_dataset(dataset)
        path = _doc_path("seeds", dataset)
        with self._write() as conn:
            self._lock_doc(conn, path)
            saved = self._load_doc(conn, path, {"seeds": {}})
            seeds = saved.setdefault("seeds", {})
            if record is None:
                seeds.pop(key, None)
            else:
                seeds[key] = dict(seeds.get(key, {}), **record)

            def project(c):
                c.execute("DELETE FROM track_seeds WHERE dataset = 'vod30'")
                SeedsSet().write(c, saved)
            self._store_doc(conn, path, saved, project)
            return seeds

    @staticmethod
    def _seeds_dataset(dataset):
        if dataset != "vod30":
            raise ValueError("seeds exist for vod30 only")

    def _dataset(self, dataset):
        """The registry's rule, exactly as JsonStore._scan applies it: a dataset is known
        when src.datasets.lookup resolves it under this root - a built-in recording, or
        an imported VOD that out/vods/index.json lists (existence, not only format)."""
        from src.datasets import lookup
        if lookup(self.root, dataset) is None:
            raise ValueError(f"unknown dataset: {dataset}")

    def verdicts_get(self, dataset: str) -> dict:
        self._dataset(dataset)
        with self._read() as conn:
            return self._load_doc(conn, _doc_path("verdicts", dataset), {})

    def verdict_put(self, dataset: str, event_id, fields: dict) -> dict:
        from datetime import datetime, timezone
        from src.store_import import VerdictsSet
        self._dataset(dataset)
        path, key = _doc_path("verdicts", dataset), str(event_id)
        with self._write() as conn:
            self._lock_doc(conn, path)
            annotations = self._load_doc(conn, path, {})
            record = dict(annotations.get(key, {}), **fields)
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            annotations[key] = record

            def project(c):
                c.execute("DELETE FROM event_verdicts WHERE dataset = %s", (dataset,))
                VerdictsSet().write(c, {dataset: annotations})
            self._store_doc(conn, path, annotations, project)
            return record

    @staticmethod
    def _crop_set(crop_set):
        if crop_set not in BALL_SETS:
            raise ValueError(f"unknown ball set: {crop_set}")

    def labels_get(self, crop_set: str) -> dict:
        self._crop_set(crop_set)
        with self._read() as conn:
            return self._load_doc(conn, _doc_path("labels", crop_set), {})

    def label_put(self, crop_set: str, crop_file: str, label, new_key: str | None = None) -> None:
        """Set or clear (None) one crop's label, matched by basename; an existing key keeps
        its original spelling and a new key (`new_key`, else the basename) is appended -
        JsonStore.label_put exactly."""
        from src.store_import import LabelsSet
        self._crop_set(crop_set)
        path = _doc_path("labels", crop_set)
        with self._write() as conn:
            self._lock_doc(conn, path)
            labels = self._load_doc(conn, path, {})
            keys = [k for k in labels if Path(k).name == crop_file]
            key = keys[0] if keys else (new_key or crop_file)
            for old in keys:
                labels.pop(old)
            if label is not None:
                labels[key] = label

            def project(c):
                c.execute("DELETE FROM ball_labels WHERE crop_set = %s", (crop_set,))
                LabelsSet().write(c, {crop_set: labels})
            self._store_doc(conn, path, labels, project)

    def correction_get(self, dataset: str, frame_index: int) -> dict | None:
        self._dataset(dataset)
        with self._read() as conn:
            return self._load_doc(conn, self._correction_path(dataset, frame_index), None)

    def correction_put(self, dataset: str, frame_index: int, payload: dict) -> None:
        self._dataset(dataset)
        path = self._correction_path(dataset, frame_index)
        with self._write() as conn:
            def project(c):
                c.execute("INSERT INTO frame_corrections (dataset, frame_index, payload, saved_at) "
                          "VALUES (%s, %s, %s, %s) ON CONFLICT (dataset, frame_index) DO UPDATE SET "
                          "payload = EXCLUDED.payload, saved_at = EXCLUDED.saved_at",
                          (dataset, int(frame_index), _jsonb(payload), (payload or {}).get("saved_at")))
            self._store_doc(conn, path, payload, project)

    @staticmethod
    def _correction_path(dataset, frame_index):
        return f"{dataset_dir(dataset)}/frame_results/{int(frame_index)}/correction.json"

    def anchors_get(self, dataset: str) -> dict:
        self._dataset(dataset)
        with self._read() as conn:
            return self._load_doc(conn, _doc_path("anchors", dataset), {"anchors": {}})

    def anchors_put(self, dataset: str, t_key: str, pts: list) -> None:
        from src.store_import import AnchorsSet
        self._dataset(dataset)
        path = _doc_path("anchors", dataset)
        with self._write() as conn:
            self._lock_doc(conn, path)
            saved = self._load_doc(conn, path, {"anchors": {}})
            key = next((k for k in saved["anchors"] if float(k) == float(t_key)), str(t_key))
            saved["anchors"][key] = pts

            def project(c):
                c.execute("DELETE FROM pocket_anchors WHERE dataset = %s", (dataset,))
                AnchorsSet().write(c, {dataset: saved})
            self._store_doc(conn, path, saved, project)

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
