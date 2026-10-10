"""Import the user-data JSON files into Postgres, verified (docs/postgres-design.md 7.3).

    PYTHONPATH=. .venv/bin/python -m src.db                        # apply migrations first
    PYTHONPATH=. .venv/bin/python -m src.store_import --dry-run    # verify, write nothing
    PYTHONPATH=. .venv/bin/python -m src.store_import [--only operations,identity] [--replace]

Per data set, in its own transaction: read the file(s) once, read-only; render what
the database holds for that set; then
  * equal           -> "unchanged": nothing is written, so a second run is a no-op;
  * database empty  -> the rows are inserted;
  * different       -> "refused", unless --replace: the database may already be the
                       live store, and older files must not overwrite its writes.
Before commit the set is rendered back to the files' JSON shape and must match
(a) the expected row count of every table and (b) the file record by record; the
first differing path is reported and the set rolls back.  A file that changed while
it was being imported also rolls its set back.  --dry-run does everything and rolls
back.  Files are only read; their md5 is reported, and they stay the backup.

Equality is strict JSON equality, with these exceptions - each one a case the
application itself already treats as the same value:
  * an int equals a float of the same value (a double precision column returns 68
    as 68.0); a bool never equals a number;
  * a face-store player with an empty list equals an absent player;
  * a missing annotations / labels / anchors file equals the empty default the
    server reads it with.
Operations and operator-record files are also stored as their exact text
(json_documents, migration 0003), and a set whose stored text differs from its file
is not "unchanged"; the export (src/store_export.py) writes that text back, so the
file -> database -> file round trip is byte-exact (tests/test_store_roundtrip.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from annotator.operations import name_key
# BALL_SETS (the crop-set vocabulary) is imported from its one owner, src.store_files,
# so this import tool and the store cannot hold two different lists of set names.
from src.store_files import (BALL_SETS, DOCUMENT_SETS, dataset_dirs, document_paths, get_document,
                             has_documents_table, put_document)

REPO = Path(__file__).resolve().parent.parent
DATASETS = {"vod30": "scan30", "highlight": "scan_highlight"}
MAX_EVENTS = 500                       # annotator/operations.py keeps the last 500 events
OK = ("imported", "unchanged", "absent", "verified")


class Refused(Exception):
    pass


class Mismatch(Exception):
    pass


class _DryRun(Exception):
    pass


def _jsonb(value):
    from psycopg.types.json import Jsonb
    return Jsonb(value)


def _floats(values):
    return None if values is None else [float(v) for v in values]


def md5(path: Path) -> str | None:
    return hashlib.md5(path.read_bytes()).hexdigest() if path.is_file() else None


def first_difference(file_value, db_value, path="$"):
    """None when the two JSON values are equal, else the first differing path."""
    if isinstance(file_value, bool) or isinstance(db_value, bool):
        same = type(file_value) is type(db_value) and file_value == db_value
        return None if same else f"{path}: file {file_value!r} != database {db_value!r}"
    if isinstance(file_value, (int, float)) and isinstance(db_value, (int, float)):
        return None if file_value == db_value else f"{path}: file {file_value!r} != database {db_value!r}"
    if type(file_value) is not type(db_value):
        return f"{path}: file {type(file_value).__name__} != database {type(db_value).__name__}"
    if isinstance(file_value, dict):
        for key in sorted(set(file_value) | set(db_value), key=str):
            if key not in db_value:
                return f"{path}.{key}: missing in the database"
            if key not in file_value:
                return f"{path}.{key}: not in the file"
            found = first_difference(file_value[key], db_value[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(file_value, list):
        if len(file_value) != len(db_value):
            return f"{path}: file has {len(file_value)} items, database {len(db_value)}"
        for index, (a, b) in enumerate(zip(file_value, db_value)):
            found = first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
        return None
    return None if file_value == db_value else f"{path}: file {file_value!r} != database {db_value!r}"


class Snapshot:
    """Reads each file once and remembers the md5 and the exact text it parsed."""

    def __init__(self, root):
        self.root = Path(root)
        self.md5s: dict[str, str | None] = {}
        self.texts: dict[str, str] = {}

    def json(self, relative: str, default=None):
        path = self.root / relative
        if not path.is_file():
            self.md5s[relative] = None
            return default
        data = path.read_bytes()
        self.md5s[relative] = hashlib.md5(data).hexdigest()
        self.texts[relative] = data.decode("utf-8")
        return json.loads(data)

    def changed(self) -> list[str]:
        return [rel for rel, digest in self.md5s.items() if md5(self.root / rel) != digest]


def _count(conn, table, where="", params=()):
    return conn.execute(f"SELECT count(*) FROM {table} {where}", params).fetchone()[0]


class DataSet:
    name = ""
    tables: tuple = ()                 # in insert order; cleared in reverse

    def load(self, snap):              # -> (document or None when there is nothing, notes)
        raise NotImplementedError

    def write(self, conn, doc):
        raise NotImplementedError

    def render(self, conn):
        raise NotImplementedError

    def expected(self, doc) -> dict:
        raise NotImplementedError

    def actual(self, conn) -> dict:
        return {table: _count(conn, table) for table in self.tables}

    def clear(self, conn):
        for table in reversed(self.tables):
            conn.execute(f"DELETE FROM {table}")


# -- operations (design section 2) ---------------------------------------------
class OperationsSet(DataSet):
    name = "operations"
    tables = ("ops_meta", "players", "tournaments", "entrants", "entrant_members", "matches",
              "notes", "sources", "ops_events")
    TOP = {"revision", "players", "tournament", "history", "settings", "notes", "sources", "events"}
    PLAYER = {"id", "name", "status", "rating", "joinedAt", "notes"}
    TOURNAMENT = {"id", "name", "format", "tables", "raceTo", "status", "entrants", "matches", "archivedAt"}
    ENTRANT = {"id", "members", "absent"}
    MATCH = {"id", "round", "sides", "score", "table", "status", "winnerId", "absent", "sources",
             "result", "completedAt"}

    def load(self, snap):
        return snap.json("out/corner-pocket/state.json"), []

    def actual(self, conn):
        counts = super().actual(conn)
        # the database keeps every event; the document (like the file) shows the last 500
        counts["ops_events"] = min(counts["ops_events"], MAX_EVENTS)
        return counts

    def clear(self, conn):
        # players are upserted in write(): deleting them would unbind identity clusters
        for table in ("ops_events", "matches", "entrant_members", "entrants", "tournaments",
                      "notes", "sources", "ops_meta"):
            conn.execute(f"DELETE FROM {table}")

    def write(self, conn, s):
        conn.execute("INSERT INTO ops_meta (id, revision, settings, extra) VALUES (true, %s, %s, %s)",
                     (s.get("revision"), _jsonb(s.get("settings")),
                      _jsonb({k: v for k, v in s.items() if k not in self.TOP})))
        players = s.get("players", [])
        # players are upserted, not recreated: a delete would unbind their identity clusters
        conn.execute("DELETE FROM players WHERE NOT (id = ANY(%s::text[]))", ([p.get("id") for p in players],))
        conn.execute("UPDATE players SET position = -1 - position")        # free the positions
        # a rename can move a name key between two players in one write (A->B, B->A):
        # park every kept player's key on its id first, as the positions are parked.
        # ' parked:' starts with a space, which no real key has (names are trimmed).
        conn.execute("UPDATE players SET name_key = ' parked:' || id")
        for position, p in enumerate(players):
            name = p.get("name")
            conn.execute(
                "INSERT INTO players (id, name, status, rating, joined_at, notes, position, extra, name_key) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET "
                "name = EXCLUDED.name, status = EXCLUDED.status, rating = EXCLUDED.rating, "
                "joined_at = EXCLUDED.joined_at, notes = EXCLUDED.notes, position = EXCLUDED.position, "
                "extra = EXCLUDED.extra, name_key = EXCLUDED.name_key",
                (p.get("id"), name, p.get("status"), p.get("rating"), p.get("joinedAt"),
                 p.get("notes"), position, _jsonb({k: v for k, v in p.items() if k not in self.PLAYER}),
                 name_key(name) if isinstance(name, str) else name))
        tournaments = [(s.get("tournament"), None)] + [(t, i) for i, t in enumerate(s.get("history", []))]
        for t, position in tournaments:
            self._tournament(conn, t, position)
        for position, n in enumerate(s.get("notes", [])):
            conn.execute("INSERT INTO notes (id, text, created_at, position) VALUES (%s, %s, %s, %s)",
                         (n.get("id"), n.get("text"), n.get("createdAt"), position))
        for position, src in enumerate(s.get("sources", [])):
            conn.execute("INSERT INTO sources (id, url, kind, channel, video, position) "
                         "VALUES (%s, %s, %s, %s, %s, %s)",
                         (src.get("id"), src.get("url"), src.get("kind"), src.get("channel"),
                          src.get("video"), position))
        for e in s.get("events", []):
            conn.execute("INSERT INTO ops_events (revision, id, created_at, action, context) "
                         "VALUES (%s, %s, %s, %s, %s)",
                         (e.get("revision"), e.get("id"), e.get("createdAt"), e.get("action"),
                          _jsonb(e.get("context"))))

    def _tournament(self, conn, t, position):
        conn.execute(
            "INSERT INTO tournaments (id, name, format, tables, race_to, status, archived_at, position, extra) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (t.get("id"), t.get("name"), t.get("format"), t.get("tables"), t.get("raceTo"), t.get("status"),
             t.get("archivedAt"), position, _jsonb({k: v for k, v in t.items() if k not in self.TOURNAMENT})))
        for index, e in enumerate(t.get("entrants", [])):
            conn.execute("INSERT INTO entrants (id, tournament_id, position, absent, extra) "
                         "VALUES (%s, %s, %s, %s, %s)",
                         (e.get("id"), t.get("id"), index, e.get("absent"),
                          _jsonb({k: v for k, v in e.items() if k not in self.ENTRANT})))
            for member_index, m in enumerate(e.get("members", [])):
                conn.execute("INSERT INTO entrant_members (entrant_id, position, player_id, name) "
                             "VALUES (%s, %s, %s, %s)", (e.get("id"), member_index, m.get("pid"), m.get("name")))
        for index, m in enumerate(t.get("matches", [])):
            sides, score, sources = m.get("sides") or [None, None], m.get("score") or [None, None], m.get("sources") or []
            if len(sides) != 2 or len(score) != 2 or len(sources) > 2:
                raise Mismatch(f"match {m.get('id')}: sides/score must have 2 items and sources at most 2")
            conn.execute(
                "INSERT INTO matches (id, tournament_id, position, round, side_a, side_b, score_a, score_b, "
                "table_no, status, winner_id, result, completed_at, source_a, source_b, absent, extra) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::text[], %s)",
                (m.get("id"), t.get("id"), index, m.get("round"), sides[0], sides[1], score[0], score[1],
                 m.get("table"), m.get("status"), m.get("winnerId"), m.get("result"), m.get("completedAt"),
                 sources[0] if sources else None, sources[1] if len(sources) > 1 else None,
                 m.get("absent", []), _jsonb({k: v for k, v in m.items() if k not in self.MATCH})))

    def render(self, conn):
        row = conn.execute("SELECT revision, settings, extra FROM ops_meta").fetchone()
        if row is None:
            return None
        revision, settings, extra = row
        players = []
        for pid, name, status, rating, joined_at, notes, p_extra in conn.execute(
                "SELECT id, name, status, rating, joined_at, notes, extra FROM players ORDER BY position").fetchall():
            player = {"id": pid, "name": name, "status": status, "rating": rating}
            if joined_at is not None:
                player["joinedAt"] = joined_at
            if notes is not None:
                player["notes"] = notes
            players.append({**player, **p_extra})
        current = [self._render_tournament(conn, t) for t in conn.execute(
            "SELECT id, name, format, tables, race_to, status, archived_at, extra FROM tournaments "
            "WHERE archived_at IS NULL").fetchall()]
        history = [self._render_tournament(conn, t) for t in conn.execute(
            "SELECT id, name, format, tables, race_to, status, archived_at, extra FROM tournaments "
            "WHERE archived_at IS NOT NULL ORDER BY position").fetchall()]
        notes = [{"id": i, "text": text, "createdAt": created} for i, text, created in conn.execute(
            "SELECT id, text, created_at FROM notes ORDER BY position").fetchall()]
        sources = []
        for sid, url, kind, channel, video in conn.execute(
                "SELECT id, url, kind, channel, video FROM sources ORDER BY position").fetchall():
            source = {"id": sid, "url": url, "kind": kind}
            if channel is not None:
                source["channel"] = channel
            if video is not None:
                source["video"] = video
            sources.append(source)
        events = [{"id": i, "createdAt": created, "revision": rev, "action": action, "context": context}
                  for i, created, rev, action, context in conn.execute(
                      "SELECT id, created_at, revision, action, context FROM (SELECT * FROM ops_events "
                      "ORDER BY revision DESC LIMIT %s) last ORDER BY revision", (MAX_EVENTS,)).fetchall()]
        return {"revision": revision, "players": players, "tournament": current[0] if current else None,
                "history": history, "settings": settings, "notes": notes, "sources": sources,
                "events": events, **extra}

    def _render_tournament(self, conn, row):
        tid, name, fmt, tables, race_to, status, archived_at, extra = row
        entrants = []
        for eid, absent, e_extra in conn.execute(
                "SELECT id, absent, extra FROM entrants WHERE tournament_id = %s ORDER BY position", (tid,)).fetchall():
            members = [{"pid": pid, "name": name_} for pid, name_ in conn.execute(
                "SELECT player_id, name FROM entrant_members WHERE entrant_id = %s ORDER BY position",
                (eid,)).fetchall()]
            entrant = {"id": eid, "members": members}
            if absent is not None:
                entrant["absent"] = absent
            entrants.append({**entrant, **e_extra})
        matches = []
        for (mid, rnd, side_a, side_b, score_a, score_b, table_no, m_status, winner, result, completed,
             source_a, source_b, absent, m_extra) in conn.execute(
                "SELECT id, round, side_a, side_b, score_a, score_b, table_no, status, winner_id, result, "
                "completed_at, source_a, source_b, absent, extra FROM matches WHERE tournament_id = %s "
                "ORDER BY position", (tid,)).fetchall():
            match = {"id": mid, "round": rnd, "sides": [side_a, side_b], "score": [score_a, score_b],
                     "table": table_no, "status": m_status, "winnerId": winner, "absent": list(absent),
                     "sources": [s for s in (source_a, source_b) if s is not None]}
            if result is not None:
                match["result"] = result
            if completed is not None:
                match["completedAt"] = completed
            matches.append({**match, **m_extra})
        tournament = {"id": tid, "name": name, "format": fmt, "tables": tables, "raceTo": race_to,
                      "entrants": entrants, "matches": matches, "status": status}
        if archived_at is not None:
            tournament["archivedAt"] = archived_at
        return {**tournament, **extra}

    def expected(self, s):
        tours = [s.get("tournament") or {}] + list(s.get("history", []))
        return {"ops_meta": 1, "players": len(s.get("players", [])), "tournaments": len(tours),
                "entrants": sum(len(t.get("entrants", [])) for t in tours),
                "entrant_members": sum(len(e.get("members", [])) for t in tours for e in t.get("entrants", [])),
                "matches": sum(len(t.get("matches", [])) for t in tours),
                "notes": len(s.get("notes", [])), "sources": len(s.get("sources", [])),
                "ops_events": len(s.get("events", []))}


# -- identity and enrolment (design section 3) ---------------------------------
class IdentitySet(DataSet):
    name = "identity"
    tables = ("identity_clusters", "identity_face_samples")

    def load(self, snap):
        raw = snap.json("out/identity/clusters.json")
        if raw is None:
            return None, []
        bare = sum(1 for rec in raw.values() if "face_samples" not in rec)
        return raw, ([f"{bare} cluster(s) written before face samples (no face_samples key)"] if bare else [])

    def write(self, conn, doc):
        roster = {row[0] for row in conn.execute("SELECT id FROM players").fetchall()}
        orphans = sorted({rec.get("player_id") for rec in doc.values()
                          if rec.get("player_id") is not None and rec.get("player_id") not in roster})
        if orphans:
            raise Mismatch(f"clusters are bound to ids that are not on the roster: {orphans} "
                           "(import operations first, or unbind them in the index)")
        for cid, rec in doc.items():
            bank = rec.get("body_bank") or []
            dim = len(bank[0]) if bank else None
            if any(len(vector) != dim for vector in bank):
                raise Mismatch(f"cluster {cid}: body_bank vectors differ in length")
            conn.execute(
                "INSERT INTO identity_clusters (cluster_id, player_id, body_bank, body_dim, face, last_seen_frame, "
                "has_face_samples) VALUES (%s, %s, %s::double precision[], %s, %s::double precision[], %s, %s)",
                (int(cid), rec.get("player_id"), [float(v) for vector in bank for v in vector], dim,
                 _floats(rec.get("face")), rec.get("last_seen_frame"), "face_samples" in rec))
            for rank, sample in enumerate(rec.get("face_samples") or []):
                conn.execute(
                    "INSERT INTO identity_face_samples (cluster_id, rank, embedding, eye_px, det_score, bbox, "
                    "frame_index) VALUES (%s, %s, %s::double precision[], %s, %s, %s::double precision[], %s)",
                    (int(cid), rank, _floats(sample.get("embedding")), sample.get("eye_px"),
                     sample.get("det_score"), _floats(sample.get("bbox")), sample.get("frame_index")))

    def render(self, conn):
        samples: dict = {}
        for cid, embedding, eye_px, det_score, bbox, frame_index in conn.execute(
                "SELECT cluster_id, embedding, eye_px, det_score, bbox, frame_index FROM identity_face_samples "
                "ORDER BY cluster_id, rank").fetchall():
            samples.setdefault(cid, []).append({"embedding": embedding, "eye_px": eye_px, "det_score": det_score,
                                                "bbox": bbox, "frame_index": frame_index})
        doc = {}
        for cid, player_id, bank, dim, face, last_seen, has_samples in conn.execute(
                "SELECT cluster_id, player_id, body_bank, body_dim, face, last_seen_frame, has_face_samples "
                "FROM identity_clusters ORDER BY cluster_id").fetchall():
            vectors = [bank[i:i + dim] for i in range(0, len(bank), dim)] if dim else []
            # IdentityIndex.save's key order; an index written before face samples existed
            # has no face_samples key, and keeps that layout
            record = {"player_id": player_id, "body_bank": vectors, "face": face}
            if has_samples:
                record["face_samples"] = samples.get(cid, [])
            record["last_seen_frame"] = last_seen
            doc[str(cid)] = record
        return doc

    def expected(self, doc):
        return {"identity_clusters": len(doc),
                "identity_face_samples": sum(len(rec.get("face_samples") or []) for rec in doc.values())}


class FacesSet(DataSet):
    name = "faces"
    tables = ("face_embeddings",)
    ROW = {"embedding", "eye_px", "det_score", "created_at", "source"}

    def load(self, snap):
        raw = snap.json("out/corner-pocket/face_embeddings.json")
        if raw is None:
            return None, []
        empty = [pid for pid, rows in raw.items() if not rows]
        doc = {pid: rows for pid, rows in raw.items() if rows}
        return doc, ([f"{len(empty)} player(s) with an empty list compared as absent"] if empty else [])

    def write(self, conn, doc):
        for player_id, rows in doc.items():
            for position, row in enumerate(rows):
                unknown = set(row) - self.ROW
                if unknown:
                    raise Mismatch(f"face row {player_id}[{position}] has fields the table cannot hold: {sorted(unknown)}")
                conn.execute(
                    "INSERT INTO face_embeddings (player_id, embedding, eye_px, det_score, created_at, source, position) "
                    "VALUES (%s, %s::double precision[], %s, %s, %s, %s, %s)",
                    (player_id, _floats(row.get("embedding")), row.get("eye_px"), row.get("det_score"),
                     row.get("created_at"), row.get("source"), position))

    def render(self, conn):
        doc: dict = {}
        for player_id, embedding, eye_px, det_score, created_at, source in conn.execute(
                "SELECT player_id, embedding, eye_px, det_score, created_at, source FROM face_embeddings "
                "ORDER BY player_id, position").fetchall():
            doc.setdefault(player_id, []).append({"embedding": embedding, "eye_px": eye_px, "det_score": det_score,
                                                  "created_at": created_at, "source": source})
        return doc

    def expected(self, doc):
        return {"face_embeddings": sum(len(rows) for rows in doc.values())}


class SeedsSet(DataSet):
    name = "seeds"
    tables = ("track_seeds",)
    SEED = {"win", "t", "track_id", "label"}

    def load(self, snap):
        return snap.json("out/pid_seed.json"), []

    def write(self, conn, doc):
        unknown = set(doc) - {"seeds"}
        if unknown:
            raise Mismatch(f"pid_seed.json has top-level keys the table cannot hold: {sorted(unknown)}")
        for key, rec in (doc.get("seeds") or {}).items():
            conn.execute(
                "INSERT INTO track_seeds (dataset, win, track_id, t, label, seed_key, extra) "
                "VALUES ('vod30', %s, %s, %s, %s, %s, %s)",
                (rec.get("win"), rec.get("track_id"), rec.get("t"), rec.get("label"), key,
                 _jsonb({k: v for k, v in rec.items() if k not in self.SEED})))

    def render(self, conn):
        seeds = {}
        for key, win, track_id, t, label, extra in conn.execute(
                "SELECT seed_key, win, track_id, t, label, extra FROM track_seeds WHERE dataset = 'vod30' "
                "ORDER BY seed_key").fetchall():
            record = {"win": win, "track_id": track_id, "label": label}
            if t is not None:
                record["t"] = t
            seeds[key] = {**record, **extra}
        return {"seeds": seeds}

    def expected(self, doc):
        return {"track_seeds": len(doc.get("seeds") or {})}


# -- operator records (design section 4) ---------------------------------------
class VerdictsSet(DataSet):
    name = "verdicts"
    tables = ("event_verdicts",)
    FIELDS = {"verdict", "shooter", "note", "updated_at"}

    def load(self, snap):
        # the built-in scans (always, {} when absent) and every imported VOD folder that
        # has verdicts (out/vods/<id>/annotations.json) - render() lists the same keys
        doc = {}
        for ds, folder in dataset_dirs(snap.root).items():
            if ds in DATASETS or (snap.root / folder / "annotations.json").is_file():
                doc[ds] = snap.json(f"{folder}/annotations.json", {})
        return doc, []

    def write(self, conn, doc):
        for dataset, annotations in doc.items():
            for event_id, rec in annotations.items():
                conn.execute(
                    "INSERT INTO event_verdicts (dataset, event_id, verdict, shooter, note, updated_at, extra) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (dataset, str(event_id), rec.get("verdict"), rec.get("shooter"), rec.get("note"),
                     rec.get("updated_at"), _jsonb({k: v for k, v in rec.items() if k not in self.FIELDS})))

    def render(self, conn):
        doc = {ds: {} for ds in DATASETS}
        for dataset, event_id, verdict, shooter, note, updated_at, extra in conn.execute(
                "SELECT dataset, event_id, verdict, shooter, note, updated_at, extra FROM event_verdicts "
                "ORDER BY dataset, event_id").fetchall():
            record = {key: value for key, value in (("verdict", verdict), ("shooter", shooter), ("note", note),
                                                    ("updated_at", updated_at)) if value is not None}
            doc.setdefault(dataset, {})[event_id] = {**record, **extra}
        return doc

    def expected(self, doc):
        return {"event_verdicts": sum(len(annotations) for annotations in doc.values())}


class LabelsSet(DataSet):
    name = "labels"
    tables = ("ball_labels",)

    def load(self, snap):
        return {crop_set: snap.json(f"out/{crop_set}/labels.json", {}) for crop_set in BALL_SETS}, []

    def write(self, conn, doc):
        for crop_set, labels in doc.items():
            for key, label in labels.items():
                conn.execute("INSERT INTO ball_labels (crop_set, crop_key, crop_file, label) VALUES (%s, %s, %s, %s)",
                             (crop_set, key, Path(key).name, _jsonb(label)))

    def render(self, conn):
        doc = {crop_set: {} for crop_set in BALL_SETS}
        for crop_set, key, label in conn.execute(
                "SELECT crop_set, crop_key, label FROM ball_labels ORDER BY crop_set, crop_key").fetchall():
            doc.setdefault(crop_set, {})[key] = label
        return doc

    def expected(self, doc):
        return {"ball_labels": sum(len(labels) for labels in doc.values())}


class CorrectionsSet(DataSet):
    name = "corrections"
    tables = ("frame_corrections",)

    def load(self, snap):
        doc = {}
        for dataset, folder in dataset_dirs(snap.root).items():
            found = {}
            for path in sorted((snap.root / folder / "frame_results").glob("*/correction.json")):
                frame = path.parent.name
                if not frame.isdigit():
                    raise Mismatch(f"{path}: the frame directory is not a frame index")
                found[frame] = snap.json(str(path.relative_to(snap.root)))
            if dataset in DATASETS or found:        # render() lists the same keys
                doc[dataset] = found
        return doc, []

    def write(self, conn, doc):
        for dataset, frames in doc.items():
            for frame, payload in frames.items():
                conn.execute("INSERT INTO frame_corrections (dataset, frame_index, payload, saved_at) "
                             "VALUES (%s, %s, %s, %s)",
                             (dataset, int(frame), _jsonb(payload), (payload or {}).get("saved_at")))

    def render(self, conn):
        doc = {ds: {} for ds in DATASETS}
        for dataset, frame, payload in conn.execute(
                "SELECT dataset, frame_index, payload FROM frame_corrections ORDER BY dataset, frame_index").fetchall():
            doc.setdefault(dataset, {})[str(frame)] = payload
        return doc

    def expected(self, doc):
        return {"frame_corrections": sum(len(frames) for frames in doc.values())}


class AnchorsSet(DataSet):
    name = "anchors"
    tables = ("pocket_anchors",)

    def load(self, snap):
        return {ds: snap.json(f"out/pid_anchors_{ds}.json", {"anchors": {}}) for ds in DATASETS}, []

    def write(self, conn, doc):
        for dataset, saved in doc.items():
            unknown = set(saved) - {"anchors"}
            if unknown:
                raise Mismatch(f"pid_anchors_{dataset}.json has top-level keys the table cannot hold: {sorted(unknown)}")
            for t_key, pts in (saved.get("anchors") or {}).items():
                conn.execute("INSERT INTO pocket_anchors (dataset, t_key, t, pts) VALUES (%s, %s, %s, %s)",
                             (dataset, t_key, float(t_key), _jsonb(pts)))

    def render(self, conn):
        doc = {ds: {"anchors": {}} for ds in DATASETS}
        for dataset, t_key, pts in conn.execute(
                "SELECT dataset, t_key, pts FROM pocket_anchors ORDER BY dataset, t").fetchall():
            doc.setdefault(dataset, {"anchors": {}})["anchors"][t_key] = pts
        return doc

    def expected(self, doc):
        return {"pocket_anchors": sum(len(saved.get("anchors") or {}) for saved in doc.values())}


SETS = {s.name: s for s in (OperationsSet(), IdentitySet(), FacesSet(), SeedsSet(), VerdictsSet(),
                            LabelsSet(), CorrectionsSet(), AnchorsSet())}
ORDER = tuple(SETS)                    # operations first: identity binds to its players


def import_set(conn, spec: DataSet, root, *, replace=False) -> dict:
    """Import one data set in one transaction (a savepoint when run() holds an outer
    dry-run transaction); returns its report and never raises for bad data."""
    import psycopg
    snap = Snapshot(root)
    report = {"dataset": spec.name}
    try:
        doc, notes = spec.load(snap)
    except (ValueError, Mismatch) as error:
        return dict(report, status="failed", error=f"cannot read the file: {error}", files=snap.md5s,
                    files_unchanged=not snap.changed())
    report.update(files=dict(snap.md5s), notes=notes)
    if doc is None:
        return dict(report, status="absent", files_unchanged=not snap.changed())
    documented = spec.name in DOCUMENT_SETS and has_documents_table(conn)
    texts = {rel: text for rel, text in snap.texts.items()} if documented else {}
    try:
        with conn.transaction():
            status = "unchanged"
            stored = {rel: get_document(conn, rel) for rel in texts}
            if first_difference(doc, spec.render(conn)) is not None or any(
                    stored[rel] is not None and stored[rel] != text for rel, text in texts.items()):
                held = sum(spec.actual(conn).values())
                if held and not replace:
                    detail = ""
                    if spec.name == "operations":
                        revision = conn.execute("SELECT revision FROM ops_meta").fetchone()
                        detail = (f" (database revision {revision[0] if revision else None}, "
                                  f"file revision {doc.get('revision')})")
                    raise Refused(f"the database already holds different {spec.name} data{detail}; "
                                  "--replace overwrites it with the file")
                spec.clear(conn)
                spec.write(conn, doc)
                status = "imported"
            if documented:
                # the exact text of each file: the byte-exact source for reads and the export;
                # a document whose file no longer exists is removed (absent = the default)
                if spec.name == "corrections":
                    known = [row[0] for row in conn.execute(
                        "SELECT path FROM json_documents WHERE path LIKE %s", ("%/frame_results/%",)).fetchall()]
                elif spec.name == "verdicts":         # the built-in scans and any imported VOD's
                    known = [row[0] for row in conn.execute(
                        "SELECT path FROM json_documents WHERE path LIKE %s", ("%/annotations.json",)).fetchall()]
                else:
                    known = document_paths(spec.name)
                for rel in known:
                    if rel not in texts and get_document(conn, rel) is not None:
                        conn.execute("DELETE FROM json_documents WHERE path = %s", (rel,))
                        status = "imported"
                for rel, text in texts.items():
                    if get_document(conn, rel) != text:
                        put_document(conn, rel, text)
                        status = "imported"
                for rel, text in texts.items():
                    if get_document(conn, rel) != text:
                        raise Mismatch(f"{rel}: the stored document is not the file's exact text")
            expected, actual = spec.expected(doc), spec.actual(conn)
            report.update(expected=expected, actual=actual)
            if expected != actual:
                raise Mismatch(f"row counts {actual} != expected {expected}")
            difference = first_difference(doc, spec.render(conn))
            if difference:
                raise Mismatch(f"round trip differs at {difference}")
            changed = snap.changed()
            if changed:
                raise Mismatch(f"changed while it was being imported: {changed}; run again")
        report["status"] = status
    except Refused as error:
        report.update(status="refused", error=str(error))
    except Mismatch as error:
        report.update(status="failed", error=str(error))
    except psycopg.Error as error:
        report.update(status="failed", error=f"{type(error).__name__}: {str(error).splitlines()[0]}")
    report["files_unchanged"] = not snap.changed()
    return report


def run(conn, root, names=ORDER, *, replace=False, dry_run=False) -> list[dict]:
    """Import the named data sets, operations first.  A dry run imports and verifies
    them all inside one outer transaction (each set a savepoint, so identity sees the
    players operations brought) and rolls everything back."""
    unknown = [name for name in names if name not in SETS]
    if unknown:
        raise ValueError(f"unknown data set(s) {unknown}; choose from {list(ORDER)}")
    chosen = [SETS[name] for name in ORDER if name in names]
    if not dry_run:
        return [import_set(conn, spec, root, replace=replace) for spec in chosen]
    reports = []
    try:
        with conn.transaction():
            reports = [import_set(conn, spec, root, replace=replace) for spec in chosen]
            raise _DryRun
    except _DryRun:
        pass
    for report in reports:
        report["dry_run"] = True
        if report["status"] == "imported":
            report["status"] = "verified"
    return reports


def main(argv=None) -> int:
    from src import db
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(REPO), help="workspace root holding out/ (default: the repo)")
    parser.add_argument("--only", default=",".join(ORDER), help="comma-separated data sets, default all")
    parser.add_argument("--replace", action="store_true", help="overwrite database data that differs from the files")
    parser.add_argument("--dry-run", action="store_true", help="import and verify, then roll everything back")
    parser.add_argument("--json", action="store_true", help="print the full reports as JSON")
    args = parser.parse_args(argv)
    names = [name.strip() for name in args.only.split(",") if name.strip()]
    try:
        with db.connect() as conn:
            if conn.execute("SELECT to_regclass('ops_meta')").fetchone()[0] is None:
                print("the user-data schema is not applied: run `python -m src.db` first", file=sys.stderr)
                return 2
            reports = run(conn, Path(args.root), names, replace=args.replace, dry_run=args.dry_run)
    except db.DatabaseNotConfigured as error:
        print(error, file=sys.stderr)
        return 2
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(reports, indent=1))
    else:
        for r in reports:
            rows = " ".join(f"{t}={n}" for t, n in (r.get("actual") or {}).items())
            files = "files unchanged" if r.get("files_unchanged") else "FILES CHANGED"
            print(f"{r['dataset']:<12} {r['status']:<10} {rows}  [{files}]")
            for note in r.get("notes") or []:
                print(f"{'':<12} note: {note}")
            if r.get("error"):
                print(f"{'':<12} error: {r['error']}")
    good = all(r["status"] in OK and r.get("files_unchanged") for r in reports)
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
