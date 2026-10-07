"""The Store contract, run against every backend (docs/postgres-design.md 7.1, 7.2).

`Contract` holds the cases once. `JsonContract` runs them on the JSON files of a
temp root, always. `PostgresContract` runs them on a PostgresStore in a fresh
throwaway schema (migrated, dropped afterwards), only when POOL_DATABASE_URL is
set - it never touches the tables that production data may be imported into.
"""
import json
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


def before_round_11():
    """A document exactly as a build before round 11 wrote it: one archived night whose
    import line names a broadcast, and neither `vods` nor `links`.  Production found this
    gap on 2026-10-04 - the Postgres store read the raw stored text, so a club there never
    adopted the links its own imports imply (owner, m07044)."""
    return {"revision": 7, "players": [], "notes": [], "sources": [], "settings": {},
            "tournament": {"id": "live", "name": "Live", "entrants": [], "matches": []},
            "history": [{"id": "night1", "name": "Night", "hidden": False,
                         "source": {"vodId": "2274501933", "startS": 3600, "endS": 11400,
                                    "title": "Wednesday 8-Ball Open",
                                    "datasetId": "tw-2274501933-3600-11400"}}]}


class Contract:
    """Mixed into a TestCase that provides self.store (and self.root)."""

    # -- operations: the revisioned document ---------------------------------
    def post(self, action, **fields):
        return self.store.post(dict(action=action, revision=self.store.get()["revision"], **fields))

    def test_a_fresh_store_has_the_default_document(self):
        doc = self.store.get()
        self.assertEqual((doc["revision"], doc["players"], doc["history"], doc["events"]), (0, [], [], []))
        self.assertEqual(doc["tournament"]["status"], "registration")

    # The application's "same name" rule is casefold of the trimmed name; both stores
    # must accept and refuse exactly the same second name (measured before the fix:
    # 'İlker' then 'ilker' was accepted by JsonStore and refused by PostgreSQL's lower()).
    def assert_name_rule(self, first, second, same):
        self.post("player_save", name=first)
        if same:
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.post("player_save", name=second)
            self.assertEqual([p["name"] for p in self.store.get()["players"]], [first])
        else:
            self.post("player_save", name=second)
            self.assertEqual([p["name"] for p in self.store.get()["players"]], [first, second])

    def test_dotted_capital_i_is_another_name_than_plain_i(self):
        self.assertNotEqual("İlker".casefold(), "ilker".casefold())
        self.assert_name_rule("İlker", "ilker", same=False)

    def test_sharp_s_is_the_same_name_as_ss(self):
        self.assertEqual("Straße".casefold(), "STRASSE".casefold())
        self.assert_name_rule("Straße", "STRASSE", same=True)

    def test_full_width_letters_are_another_name_than_ascii(self):
        self.assertNotEqual("ＡＮＡ".casefold(), "ana".casefold())
        self.assert_name_rule("ＡＮＡ", "ana", same=False)

    def test_a_rename_that_swaps_two_players_names_is_one_valid_write(self):
        """Both stores apply the document as a whole: rename B to a free name, A to B's
        old one - the key moves between rows inside one projection rewrite."""
        a = self.post("player_save", name="Ann")["players"][0]["id"]
        b = self.post("player_save", name="Bea")["players"][1]["id"]
        self.post("player_save", id=b, name="Cat")
        state = self.post("player_save", id=a, name="bea")
        self.assertEqual([(p["id"], p["name"]) for p in state["players"]], [(a, "bea"), (b, "Cat")])

    def test_the_revision_advances_and_a_stale_one_is_a_conflict_that_writes_nothing(self):
        saved = self.store.post({"action": "player_save", "revision": 0, "name": "Ada"})
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(self.store.get(), saved)
        with self.assertRaises(ConflictError):
            self.store.post({"action": "note_add", "revision": 0, "text": "stale"})
        self.assertEqual(self.store.get(), saved, "a refused post leaves the document as it was")
        with self.assertRaises(ValueError):
            self.store.post({"action": "player_save", "revision": 1, "name": "ADA"})   # casefold duplicate
        self.assertEqual(self.store.get(), saved, "a rule refusal writes nothing either")

    def test_a_whole_night_round_trips_through_the_store(self):
        self.post("tournament_setup", raceTo=2, tables=2, name="Friday")
        for name in ("Ana", "Bo", "Cy"):
            self.post("entrant_add", members=[{"name": name}])
        state = self.post("tournament_start")
        first = next(m for m in state["tournament"]["matches"] if all(m["sides"]) and m["status"] == "scheduled")
        self.post("match_schedule", id=first["id"])
        self.post("match_score", id=first["id"], score=[2, 1])
        state = self.post("match_complete", id=first["id"])
        self.assertEqual(self.store.get(), state)
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
        self.assertEqual(self.store.get(), signed)

    def test_delete_of_an_unsigned_event_resets_it_and_hide_changes_only_the_flag(self):
        self.post("tournament_setup", raceTo=1, name="Mistake")
        self.post("entrant_add", members=[{"name": "Ana"}])
        current = self.store.get()["tournament"]["id"]
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
        self.assertEqual(self.store.get(), shown)

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
        self.assertEqual(self.store.get(), again, "the refused enrolment wrote nothing")

    def test_eight_concurrent_posts_at_one_revision_one_wins_seven_conflict(self):
        barrier, results = threading.Barrier(8), []

        def worker(n):
            barrier.wait()
            try:
                self.store.post({"action": "note_add", "revision": 0, "text": f"n{n}"})
                results.append("ok")
            except ConflictError:
                results.append("conflict")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), ["conflict"] * 7 + ["ok"])
        self.assertEqual((self.store.get()["revision"], len(self.store.get()["notes"])), (1, 1))

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

    # -- imported VODs (src/datasets.py): the same records under out/vods/<id>/ ----
    IMPORTED = "tw-1000000001-3600-3900"

    def import_vod(self, dataset_id=IMPORTED):
        """List an imported VOD in out/vods/index.json, as annotator/vod_import.py does."""
        from src.datasets import parse_imported_id
        index = self.root / "out" / "vods" / "index.json"
        index.parent.mkdir(parents=True, exist_ok=True)
        vods = json.loads(index.read_text())["vods"] if index.is_file() else {}
        vods[dataset_id] = {"vod_id": parse_imported_id(dataset_id)[0], "channel": "examplechannel"}
        index.write_text(json.dumps({"vods": vods}))

    def test_an_imported_vod_keeps_its_corrections_and_verdicts(self):
        self.import_vod()
        self.assertIsNone(self.store.correction_get(self.IMPORTED, 120))
        self.store.correction_put(self.IMPORTED, 120, {"boxes": [{"label": "ball"}], "saved_at": "t1"})
        self.assertEqual(self.store.correction_get(self.IMPORTED, 120), {"boxes": [{"label": "ball"}], "saved_at": "t1"})
        self.assertIsNone(self.store.correction_get("vod30", 120), "each dataset keeps its own corrections")
        record = self.store.verdict_put(self.IMPORTED, 7, {"verdict": "wrong", "shooter": "A"})
        self.assertEqual(self.store.verdicts_get(self.IMPORTED), {"7": record})
        self.assertEqual(self.store.verdicts_get("vod30"), {})

    def test_a_malformed_or_unlisted_dataset_is_refused_the_same_way_on_both_stores(self):
        """Existence, like JsonStore: an id is usable only while the registry lists it."""
        self.import_vod()
        for bad in ("tw-0123", "tw-1-9-5", "tw-1000000001-3600-3900\n", "../scan30", "vod31",
                    "tw-1000000001"):                      # well-formed, but not imported
            with self.assertRaisesRegex(ValueError, "unknown dataset", msg=repr(bad)):
                self.store.correction_put(bad, 1, {"boxes": []})
            with self.assertRaisesRegex(ValueError, "unknown dataset", msg=repr(bad)):
                self.store.verdict_put(bad, 1, {"verdict": "wrong"})
            with self.assertRaisesRegex(ValueError, "unknown dataset", msg=repr(bad)):
                self.store.correction_get(bad, 1)

    def test_corrections_and_anchors(self):
        self.assertIsNone(self.store.correction_get("vod30", 2100))
        self.store.correction_put("vod30", 2100, {"boxes": [], "saved_at": "t1"})
        self.store.correction_put("vod30", 2100, {"boxes": [{"label": "ball"}], "saved_at": "t2"})
        self.assertEqual(self.store.correction_get("vod30", 2100), {"boxes": [{"label": "ball"}], "saved_at": "t2"})
        self.assertEqual(self.store.anchors_get("vod30"), {"anchors": {}})
        self.store.anchors_put("vod30", "70.0", [[1, 2]] * 6)
        self.store.anchors_put("vod30", "70", [[3, 4]] * 6)        # the same time, written another way
        self.assertEqual(self.store.anchors_get("vod30"), {"anchors": {"70.0": [[3, 4]] * 6}})

    def test_an_unknown_record_set_is_refused_and_the_answer_is_stable(self):
        """Store.place names where a record set lives. Both backings refuse a kind they
        do not keep, and neither answer changes when the records do."""
        with self.assertRaises(ValueError):
            self.store.place("verdicts")
        first = self.store.place("operations")
        self.assertEqual(self.store.place("operations"), first)
        self.store.faces_add({"A": [face(1)]})
        self.store.anchors_put("vod30", "70.0", [[0, 0]] * 6)
        self.assertEqual(self.store.place("operations"), first, "a receipt is a name, not a snapshot")

    # -- the read-only contract (design 7.2) -------------------------------------
    READS = (lambda s: s.get(), lambda s: s.faces_load(), lambda s: s.identity_load(),
             lambda s: s.seeds_get("vod30"), lambda s: s.verdicts_get("vod30"), lambda s: s.verdicts_get("highlight"),
             lambda s: s.labels_get("unlabeled_crops"), lambda s: s.correction_get("vod30", 5),
             lambda s: s.correction_get("vod30", 6), lambda s: s.anchors_get("vod30"),
             lambda s: s.queue("vod30"), lambda s: s.queue_window("vod30", 0, 10), lambda s: s.tracklets("vod30"),
             lambda s: s.artifact("queue_report", "vod30"), lambda s: s.frame_detections("vod30", 1),
             lambda s: s.place("operations"), lambda s: s.place("faces"), lambda s: s.place("anchors", "vod30"))

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

    def test_a_document_file_written_before_round_11_reads_with_its_links(self):
        """The file store's half of the production gap: two keys it never had, and the
        link the night's own import line implies - derived on read, not written to disk."""
        path = self.root / "out" / "corner-pocket" / "state.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(before_round_11()))
        before = self.snapshot()
        doc = self.store.get()
        self.assertEqual([k for k in ("vods", "links") if k in doc], ["vods", "links"])
        self.assertEqual(doc["links"], [{"vodId": "2274501933", "eventId": "night1",
                                         "startS": 3600, "endS": 11400, "at": ""}])
        self.assertEqual([v["id"] for v in doc["vods"]], ["2274501933"])
        self.assertEqual(doc["vods"][0]["title"], "Wednesday 8-Ball Open")
        self.assertEqual(self.snapshot(), before, "reading adopted the link; it did not write it")
        self.assertEqual(self.store.get(), doc, "adoption is idempotent")

    def test_the_receipts_name_the_files_this_backing_writes(self):
        """A file backing answers with a Path. The three answers are the files that the
        operations writer, the face writer and the anchor writer really use."""
        self.assertEqual(self.store.place("operations"), self.root / "out" / "corner-pocket" / "state.json")
        self.assertEqual(self.store.place("faces"), self.root / "out" / "corner-pocket" / "face_embeddings.json")
        self.assertEqual(self.store.place("anchors", "vod30"), self.root / "out" / "pid_anchors_vod30.json")


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
        self._checked_writes = 0
        self._install_projection_check()

    def _install_projection_check(self):
        """After every write, the 0002 rows must equal a fresh projection of the stored
        documents (condition 1 of the 0003 review). src.store_check runs at the end of
        the write's own transaction - it sees exactly that write's documents and rows,
        and a concurrent writer cannot interleave (a check after commit could race one).
        Failures are collected and asserted in the test thread, so a worker thread
        cannot hide one."""
        from contextlib import contextmanager
        from src.store_check import check
        original = self.store._write
        self._projection_problems = []
        self.addCleanup(lambda: self.assertEqual(self._projection_problems, [],
                                                 "the projection must equal the stored documents after every write"))

        @contextmanager
        def checked_write():
            with original() as conn:
                yield conn
                self._projection_problems.extend(check(conn))
                self._checked_writes += 1

        self.store._write = checked_write

    def test_a_stored_document_written_before_round_11_reads_with_its_links(self):
        """The Postgres half: `_document` reads the stored text through `normalise`, the
        same way `Operations._load` reads the file, so the two stores answer alike."""
        from src.store_pg import STATE
        from src.store_files import get_document, put_document
        text = json.dumps(before_round_11())
        with db.connect() as conn:
            conn.execute(f"SET search_path TO {self.schema}")
            put_document(conn, STATE, text)
        doc = self.store.get()
        self.assertEqual([k for k in ("vods", "links") if k in doc], ["vods", "links"])
        self.assertEqual(doc["links"], [{"vodId": "2274501933", "eventId": "night1",
                                         "startS": 3600, "endS": 11400, "at": ""}])
        self.assertEqual([v["id"] for v in doc["vods"]], ["2274501933"])
        with db.connect() as conn:
            conn.execute(f"SET search_path TO {self.schema}")
            stored = get_document(conn, STATE)
        self.assertEqual(stored, text, "reading adopted the link; the stored text is untouched")
        self.assertEqual(self.store.get(), doc, "adoption is idempotent")

    def test_the_receipts_name_the_documents_this_backing_writes(self):
        """The enrolment receipt shows the database name, not a file path. These three
        strings are what the console and the enrolment already display - keep them."""
        self.assertEqual(self.store.place("operations"), "postgres:json_documents/out/corner-pocket/state.json")
        self.assertEqual(self.store.place("faces"), "postgres:face_embeddings")
        self.assertEqual(self.store.place("anchors", "vod30"), "postgres:json_documents/out/pid_anchors_vod30.json")

    def test_the_projection_check_runs_after_every_write_and_catches_drift(self):
        from src.store_check import check
        self.post("player_save", name="Ada")
        self.store.verdict_put("vod30", 1, {"verdict": "correct"})
        self.assertEqual(self._checked_writes, 2, "each write was followed by a projection check")
        with db.connect() as conn:
            conn.execute(f"SET search_path TO {self.schema}")
            conn.execute("UPDATE event_verdicts SET verdict = 'wrong'")          # a projection drifting away
            self.assertTrue(any("event_verdicts" in p for p in check(conn)), "the check reports the drift")

    def test_a_write_the_rules_allow_but_a_constraint_refuses_rolls_back_and_names_it(self):
        """Synthetic: no legitimate input reaches the name backstop any more (it enforces
        the application's own rule), so a rule bug is simulated - Operations._apply is
        patched to append a duplicate name unchecked - and players_name_key must refuse
        it: rolled back, named, a 4xx-class error, never a silent success."""
        from unittest import mock
        from annotator.operations import Operations
        from src.store import StoreConstraintError
        first = self.store.post({"action": "player_save", "revision": 0, "name": "Ana"})

        def buggy_apply(self_ops, state, payload):          # a rule that forgot the name check
            state["players"].append(dict(id="dup", name="ANA", joinedAt="t", rating=0, status="Active"))

        with mock.patch.object(Operations, "_apply", buggy_apply), \
                self.assertRaises(StoreConstraintError) as refused:
            self.store.post({"action": "player_save", "revision": 1, "name": "ignored"})
        self.assertEqual(refused.exception.constraint, "players_name_key")
        self.assertIn("players_name_key", str(refused.exception))
        self.assertIn("nothing was written", str(refused.exception))
        self.assertIsInstance(refused.exception, ValueError, "the server answers it as a 4xx, not a 500")
        self.assertEqual(self.store.get(), first, "the refused write left the document as it was")

    def test_binding_a_cluster_to_an_id_off_the_roster_is_refused_by_the_foreign_key(self):
        """The reviewed FK on identity_clusters.player_id: POST /api/identity/seed with a
        typo used to be stored in the file; on Postgres it is refused, nothing written."""
        import numpy as np
        from src.person_identity import IdentityIndex
        from src.store import StoreConstraintError
        self.store.enroll_player({"id": "p1", "name": "Ana"}, {"player_id": "p1"})
        index = IdentityIndex(self.root / "unused.json", store=self.store)
        index.register(1, np.ones(128, np.float32), frame_index=1)
        index.explicit_assign(1, "p1")
        before = self.store.identity_load()
        with self.assertRaises(StoreConstraintError) as refused:
            index.explicit_assign(1, "no-such-player")
        self.assertEqual(refused.exception.constraint, "identity_clusters_player_id_fkey")
        self.assertIsInstance(refused.exception, ValueError)
        self.assertEqual(self.store.identity_load(), before, "the index kept its last good state")

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
