"""The Store contract, run against every backend (docs/postgres-design.md 7.1, 7.2).

`Contract` holds the cases once. `JsonContract` runs them on the JSON files of a
temp root, always. `PostgresContract` runs them on a PostgresStore in a fresh
throwaway schema (migrated, dropped afterwards), only when POOL_DATABASE_URL is
set - it never touches the tables that production data may be imported into.
"""
import os
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

import numpy as np

from annotator.operations import ConflictError
from src import db
from src.store import JsonStore

HAVE_DB = bool(os.environ.get(db.ENV))


def unit(seed, dim=512):
    rng = np.random.RandomState(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def face(seed, **extra):
    return dict({"embedding": unit(seed), "eye_px": 12.0, "det_score": 0.9}, **extra)


class Contract:
    """Mixed into a TestCase that provides self.store (and self.root)."""

    # -- operations: the revisioned document ---------------------------------
    def post(self, action, **fields):
        return self.store.ops_post(dict(action=action, revision=self.store.ops_get()["revision"], **fields))

    def test_a_fresh_store_has_the_default_document(self):
        doc = self.store.ops_get()
        self.assertEqual((doc["revision"], doc["players"], doc["history"], doc["events"]), (0, [], [], []))
        self.assertEqual(doc["tournament"]["status"], "registration")

    def test_the_revision_advances_and_a_stale_one_is_a_conflict_that_writes_nothing(self):
        saved = self.store.ops_post({"action": "player_save", "revision": 0, "name": "Ada"})
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(self.store.ops_get(), saved)
        with self.assertRaises(ConflictError):
            self.store.ops_post({"action": "note_add", "revision": 0, "text": "stale"})
        self.assertEqual(self.store.ops_get(), saved, "a refused post leaves the document as it was")
        with self.assertRaises(ValueError):
            self.store.ops_post({"action": "player_save", "revision": 1, "name": "ADA"})   # casefold duplicate
        self.assertEqual(self.store.ops_get(), saved, "a rule refusal writes nothing either")

    def test_a_whole_night_round_trips_through_the_store(self):
        self.post("tournament_setup", raceTo=2, tables=2, name="Friday")
        for name in ("Ana", "Bo", "Cy"):
            self.post("entrant_add", members=[{"name": name}])
        state = self.post("tournament_start")
        first = next(m for m in state["tournament"]["matches"] if all(m["sides"]) and m["status"] == "scheduled")
        self.post("match_schedule", id=first["id"])
        self.post("match_score", id=first["id"], score=[2, 1])
        state = self.post("match_complete", id=first["id"])
        self.assertEqual(self.store.ops_get(), state)
        self.assertEqual([e["revision"] for e in state["events"]], list(range(1, state["revision"] + 1)))
        self.assertEqual(next(m for m in state["tournament"]["matches"] if m["id"] == first["id"])["result"], "played")

    def test_delete_is_refused_once_a_result_is_signed_and_writes_nothing(self):
        self.post("tournament_setup", raceTo=1)
        for name in ("Ana", "Bo"):
            self.post("entrant_add", members=[{"name": name}])
        state = self.post("tournament_start")
        match = state["tournament"]["matches"][0]
        self.post("match_schedule", id=match["id"])
        self.post("match_score", id=match["id"], score=[1, 0])
        signed = self.post("match_complete", id=match["id"])
        with self.assertRaises(ValueError):
            self.post("tournament_delete", id=signed["tournament"]["id"], confirm=True)
        self.assertEqual(self.store.ops_get(), signed)

    def test_delete_of_an_unsigned_event_resets_it_and_hide_changes_only_the_flag(self):
        self.post("tournament_setup", raceTo=1, name="Mistake")
        self.post("entrant_add", members=[{"name": "Ana"}])
        current = self.store.ops_get()["tournament"]["id"]
        deleted = self.post("tournament_delete", id=current, confirm=True)
        self.assertNotEqual(deleted["tournament"]["id"], current)
        self.assertEqual((deleted["tournament"]["entrants"], deleted["tournament"]["status"]), ([], "registration"))
        # archive a signed night, then hide and unhide it
        self.post("tournament_setup", raceTo=1)
        for name in ("Ana", "Bo"):
            self.post("entrant_add", members=[{"name": name}])
        match = self.post("tournament_start")["tournament"]["matches"][0]
        self.post("match_schedule", id=match["id"])
        self.post("match_score", id=match["id"], score=[1, 0])
        self.post("match_complete", id=match["id"])
        archived = self.post("tournament_new", confirm=True)["history"][-1]
        self.assertNotIn("hidden", archived, "the key is absent until a hide")
        hidden = self.post("tournament_hide", id=archived["id"], hidden=True, confirm=True)
        self.assertEqual(hidden["history"][-1], dict(archived, hidden=True), "only the flag changed")
        shown = self.post("tournament_hide", id=archived["id"], hidden=False, confirm=True)
        self.assertIs(shown["history"][-1]["hidden"], False, "false stays false, not absent")
        self.assertEqual(self.store.ops_get(), shown)

    def test_enrol_player_is_one_revision_and_keeps_concurrent_writes(self):
        self.post("note_add", text="kept")
        state = self.store.enroll_player({"id": "p1", "name": "Ana"}, {"player_id": "p1", "name": "Ana"})
        self.assertEqual((state["revision"], [p["name"] for p in state["players"]]), (2, ["Ana"]))
        self.assertEqual([n["text"] for n in state["notes"]], ["kept"])
        self.assertEqual(state["events"][-1]["action"], "player_enroll_from_tracklet")
        again = self.store.enroll_player({"id": "p1", "name": "Ana"}, {"player_id": "p1", "name": "Ana"})
        self.assertEqual(len(again["players"]), 1, "an existing regular gains no second row")
        with self.assertRaises(ValueError):
            self.store.enroll_player({"id": "p2", "name": "ANA"}, {"player_id": "p2", "name": "ANA"})
        self.assertEqual(self.store.ops_get(), again, "the refused enrolment wrote nothing")

    def test_eight_concurrent_posts_at_one_revision_one_wins_seven_conflict(self):
        barrier, results = threading.Barrier(8), []

        def worker(n):
            barrier.wait()
            try:
                self.store.ops_post({"action": "note_add", "revision": 0, "text": f"n{n}"})
                results.append("ok")
            except ConflictError:
                results.append("conflict")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), ["conflict"] * 7 + ["ok"])
        self.assertEqual((self.store.ops_get()["revision"], len(self.store.ops_get()["notes"])), (1, 1))

    # -- identity and faces ----------------------------------------------------
    def test_faces_merge_per_player_and_forget_removes_one_player(self):
        self.assertEqual(self.store.faces_load(), {})
        self.store.faces_add({"A": [face(1, source="a1")]})
        self.store.faces_add({"B": [face(2, source="b1")]})
        merged = self.store.faces_add({"A": [face(3, source="a2")]})
        self.assertEqual({pid: [r["source"] for r in rows] for pid, rows in merged.items()},
                         {"A": ["a1", "a2"], "B": ["b1"]})
        self.assertEqual(self.store.faces_load(), merged)
        row = merged["A"][0]
        self.assertEqual(len(row["embedding"]), 512)
        self.assertTrue(all(v == round(v, 4) for v in row["embedding"]), "stored at 4 decimals")
        self.assertEqual(self.store.faces_remove("A"), 2)
        self.assertEqual(list(self.store.faces_load()), ["B"])
        self.assertEqual(self.store.faces_remove("nobody"), 0)

    def test_eight_concurrent_face_adds_lose_nothing(self):
        barrier = threading.Barrier(8)

        def worker(n):
            barrier.wait()
            self.store.faces_add({f"T{n}": [face(n, source=f"t{n}")]})

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(self.store.faces_load()), sorted(f"T{n}" for n in range(8)))

    def test_the_identity_index_saves_and_loads_including_a_bind(self):
        self.store.enroll_player({"id": "p1", "name": "Ana"}, {"player_id": "p1"})
        clusters = {"1": {"player_id": "p1", "body_bank": [[0.5] * 128, [0.25] * 128], "face": [0.1] * 512,
                          "last_seen_frame": 40,
                          "face_samples": [{"embedding": [0.2] * 512, "eye_px": 12.3, "det_score": 0.912,
                                            "bbox": [1.5, 2.0, 30.25, 40.0], "frame_index": 40}]},
                    "2": {"player_id": None, "body_bank": [], "face": None, "last_seen_frame": None,
                          "face_samples": []}}
        self.store.identity_save(clusters)
        self.assertEqual(self.store.identity_load(), clusters)
        clusters["2"]["player_id"] = "p1"                  # the bind path: a new binding is saved
        self.store.identity_save(clusters)
        self.assertEqual(self.store.identity_load()["2"]["player_id"], "p1")

    # -- seeds and operator records --------------------------------------------
    def test_seeds_put_merges_and_clears_one_key(self):
        self.store.seed_put("vod30", "1:68-94", {"win": "68-94", "t": 68, "track_id": 1, "label": "A"})
        seeds = self.store.seed_put("vod30", "2:68-94", {"win": "68-94", "t": 69.5, "track_id": 2, "label": "Guest"})
        self.assertEqual(sorted(seeds), ["1:68-94", "2:68-94"])
        merged = self.store.seed_put("vod30", "1:68-94", {"label": "B"})
        self.assertEqual((merged["1:68-94"]["label"], merged["1:68-94"]["t"]), ("B", 68))
        self.assertEqual(sorted(self.store.seed_put("vod30", "1:68-94", None)), ["2:68-94"])
        self.assertEqual(self.store.seeds_get("vod30"), self.store.seed_put("vod30", "9:1-2", None))
        with self.assertRaises(ValueError):
            self.store.seeds_get("highlight")

    def test_verdicts_merge_per_event_and_stay_per_dataset(self):
        self.assertEqual(self.store.verdict_put("vod30", 16, {"verdict": "wrong", "note": "x"})["verdict"], "wrong")
        merged = self.store.verdict_put("vod30", 16, {"shooter": "A"})
        self.assertEqual((merged["verdict"], merged["shooter"], merged["note"]), ("wrong", "A", "x"))
        self.assertIn("updated_at", merged)
        self.assertEqual(self.store.verdicts_get("vod30"), {"16": merged})
        self.assertEqual(self.store.verdicts_get("highlight"), {})

    def test_eight_concurrent_verdict_writers_lose_nothing(self):
        barrier = threading.Barrier(8)

        def worker(n):
            barrier.wait()
            self.store.verdict_put("vod30", 100 + n, {"verdict": "correct"})

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(self.store.verdicts_get("vod30")), [str(100 + n) for n in range(8)])

    def test_labels_keep_the_original_key_update_and_clear(self):
        self.store.label_put("unlabeled_crops", "crop1.png", 4)
        self.store.label_put("unlabeled_crops", "crop2.png", "u")
        self.store.label_put("unlabeled_crops", "crop1.png", 7)
        self.assertEqual(self.store.labels_get("unlabeled_crops"), {"crop1.png": 7, "crop2.png": "u"})
        self.store.label_put("unlabeled_crops", "crop1.png", None)
        self.assertEqual(self.store.labels_get("unlabeled_crops"), {"crop2.png": "u"})
        self.assertEqual(self.store.labels_get("unlabeled_crops2"), {})
        with self.assertRaises(ValueError):
            self.store.labels_get("not-a-set")

    def test_corrections_and_anchors(self):
        self.assertIsNone(self.store.correction_get("vod30", 2100))
        self.store.correction_put("vod30", 2100, {"boxes": [], "saved_at": "t1"})
        self.store.correction_put("vod30", 2100, {"boxes": [{"label": "ball"}], "saved_at": "t2"})
        self.assertEqual(self.store.correction_get("vod30", 2100), {"boxes": [{"label": "ball"}], "saved_at": "t2"})
        self.assertEqual(self.store.anchors_get("vod30"), {"anchors": {}})
        self.store.anchors_put("vod30", "70.0", [[1, 2]] * 6)
        self.store.anchors_put("vod30", "70", [[3, 4]] * 6)        # the same time, written another way
        self.assertEqual(self.store.anchors_get("vod30"), {"anchors": {"70.0": [[3, 4]] * 6}})

    # -- the read-only contract (design 7.2) -------------------------------------
    READS = (lambda s: s.ops_get(), lambda s: s.faces_load(), lambda s: s.identity_load(),
             lambda s: s.seeds_get("vod30"), lambda s: s.verdicts_get("vod30"), lambda s: s.verdicts_get("highlight"),
             lambda s: s.labels_get("unlabeled_crops"), lambda s: s.correction_get("vod30", 5),
             lambda s: s.correction_get("vod30", 6), lambda s: s.anchors_get("vod30"),
             lambda s: s.queue("vod30"), lambda s: s.queue_window("vod30", 0, 10), lambda s: s.tracklets("vod30"),
             lambda s: s.artifact("queue_report", "vod30"), lambda s: s.frame_detections("vod30", 1))

    def populate(self):
        self.post("player_save", name="Ada")
        self.store.faces_add({"A": [face(1)]})
        self.store.seed_put("vod30", "1:68-94", {"win": "68-94", "t": 68, "track_id": 1, "label": "A"})
        self.store.verdict_put("vod30", 1, {"verdict": "correct"})
        self.store.label_put("unlabeled_crops", "c.png", 3)
        self.store.correction_put("vod30", 5, {"boxes": []})
        self.store.anchors_put("vod30", "70.0", [[0, 0]] * 6)

    def test_reads_write_nothing(self):
        self.populate()
        before = self.snapshot()
        for read in self.READS:
            read(self.store)
        self.assertEqual(self.snapshot(), before)


class JsonContract(Contract, unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = JsonStore(self.root)

    def snapshot(self):
        import hashlib
        return {str(p): (hashlib.md5(p.read_bytes()).hexdigest(), p.stat().st_size, p.stat().st_mtime_ns)
                for p in sorted(self.root.rglob("*")) if p.is_file()}


@unittest.skipUnless(HAVE_DB, f"{db.ENV} is not set (docs/postgres.md)")
class PostgresContract(Contract, unittest.TestCase):
    def setUp(self):
        from src.store_pg import PostgresStore
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.schema = f"test_contract_{uuid.uuid4().hex[:12]}"
        with db.connect() as conn:
            conn.execute(f"CREATE SCHEMA {self.schema}")
            conn.execute(f"SET search_path TO {self.schema}")
            db.migrate(conn)
        self.addCleanup(self._drop)
        self.store = PostgresStore(self.root, search_path=self.schema)
        self.addCleanup(self.store.close)

    def _drop(self):
        with db.connect() as conn:
            conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")

    def snapshot(self):
        """Every row of every table in the scratch schema, plus the write counters."""
        with db.connect() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY 1", (self.schema,)).fetchall()]
            return {t: sorted(map(repr, conn.execute(f'SELECT * FROM "{self.schema}"."{t}"').fetchall()))
                    for t in tables}

    def test_every_read_runs_in_a_read_only_transaction(self):
        """PostgreSQL itself refuses a write inside any read: each read method runs with
        a statement hook that tries to write, and must see it refused."""
        import psycopg
        self.populate()
        conn = self.store._conn()
        refused = []
        original = self.store._read

        from contextlib import contextmanager

        @contextmanager
        def probing_read():
            with original() as c:
                try:
                    with c.transaction():
                        c.execute("CREATE TEMP TABLE probe_write (a int)")
                except psycopg.errors.ReadOnlySqlTransaction:
                    refused.append(True)
                yield c

        self.store._read = probing_read
        try:
            for read in self.READS[:10]:                   # the database-backed reads
                read(self.store)
        finally:
            self.store._read = original
        self.assertEqual(len(refused), 10, "every database read was read-only")
        self.assertFalse(conn.closed)


if __name__ == "__main__":
    unittest.main()
