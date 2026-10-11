"""src/store_import.py: files -> Postgres, idempotent and verified.

The comparison helper is checked everywhere; the import itself runs only when
POOL_DATABASE_URL is set, each test in its own scratch schema (dropped afterwards),
on a temp root. The production files are read from a COPY, never opened in place.
"""
import json
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

import numpy as np

from src import db
from src.store_import import first_difference, md5, run

HAVE_DB = bool(os.environ.get(db.ENV))
REPO = Path(__file__).resolve().parents[1]


class Comparison(unittest.TestCase):
    def test_ints_equal_floats_but_bools_do_not(self):
        self.assertIsNone(first_difference({"t": 68}, {"t": 68.0}))
        self.assertIsNotNone(first_difference({"flag": True}, {"flag": 1}))
        self.assertIsNotNone(first_difference({"a": 1}, {"a": 2}))

    def test_the_first_difference_names_its_path(self):
        self.assertEqual(first_difference({"p": [{"n": "A"}, {"n": "B"}]}, {"p": [{"n": "A"}, {"n": "C"}]}),
                         "$.p[1].n: file 'B' != database 'C'")
        self.assertIn("missing in the database", first_difference({"a": 1, "b": 2}, {"a": 1}))
        self.assertIn("2 items", first_difference([1, 2], [1]))


def fixture(root: Path):
    """A workspace holding every data set, shaped like the production files."""
    out = root / "out"
    rng = np.random.RandomState(4)

    def vec(n):
        v = rng.standard_normal(n)
        return [round(float(x), 4) for x in v / np.linalg.norm(v)]

    def save(relative, data):
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")

    state = {
        "revision": 7,
        "players": [{"id": "p1", "name": "Ana", "joinedAt": "2026-09-01T10:00:00+00:00", "rating": 610,
                     "status": "Active", "notes": "left-handed"},
                    {"id": "p2", "name": "Bo", "joinedAt": "2026-09-02T10:00:00+00:00", "rating": 0,
                     "status": "Visitor"}],
        "tournament": {"id": "t2", "name": "Friday", "format": "singles", "tables": 2, "raceTo": 3,
                       "entrants": [{"id": "e1", "members": [{"pid": "p1", "name": "Ana"}]},
                                    {"id": "e2", "members": [{"pid": None, "name": "Walk-in"}], "absent": True}],
                       "matches": [{"id": "m1", "round": 1, "sides": ["e1", "e2"], "score": [1, 0], "table": 1,
                                    "status": "live", "winnerId": None, "absent": [], "sources": []},
                                   {"id": "m2", "round": 2, "sides": [None, None], "score": [0, 0], "table": None,
                                    "status": "pending", "winnerId": None, "absent": [], "sources": ["m1"]}],
                       "status": "active"},
        "history": [{"id": "t1", "name": "Thursday", "format": "doubles", "tables": 1, "raceTo": 1,
                     "entrants": [{"id": "e9", "members": [{"pid": "p1", "name": "Ana"}, {"pid": "p2", "name": "Bo"}]}],
                     "matches": [{"id": "m9", "round": 1, "sides": ["e9", None], "score": [0, 0], "table": None,
                                  "status": "complete", "winnerId": "e9", "absent": [], "sources": [],
                                  "result": "bye"}],
                     "status": "complete", "archivedAt": "2026-09-03T01:00:00+00:00"},
                    # tournament_hide (7285584): the key is absent until a hide, then true or false
                    {"id": "t0", "name": "Hidden", "format": "singles", "tables": 1, "raceTo": 1, "entrants": [],
                     "matches": [], "status": "complete", "archivedAt": "2026-09-02T01:00:00+00:00", "hidden": True},
                    {"id": "t00", "name": "Unhidden", "format": "singles", "tables": 1, "raceTo": 1, "entrants": [],
                     "matches": [], "status": "complete", "archivedAt": "2026-09-01T01:00:00+00:00", "hidden": False}],
        "settings": {"shotClock": 30, "autoFrame": False, "clothColor": "#1d5c44", "lampGlow": 0.22,
                     "showDiamonds": True},
        "notes": [{"id": "n1", "text": "cloth replaced", "createdAt": "2026-09-04T10:00:00+00:00"}],
        "sources": [{"id": "s1", "url": "https://www.twitch.tv/examplechannel", "kind": "channel",
                     "channel": "examplechannel"}],
        "events": [{"id": f"ev{n}", "createdAt": "2026-09-05T10:00:00+00:00", "revision": n,
                    "action": "note_add", "context": {"id": "n1"} if n % 2 else {}} for n in range(1, 8)],
    }
    save("corner-pocket/state.json", state)
    save("identity/clusters.json", {
        "1": {"player_id": "p1", "body_bank": [vec(128), vec(128)], "face": vec(512), "last_seen_frame": 40,
              "face_samples": [{"embedding": vec(512), "eye_px": 12.3, "det_score": 0.912,
                                "bbox": [1.5, 2.0, 30.25, 40.0], "frame_index": 40}]},
        "2": {"player_id": None, "body_bank": [vec(128)], "face": None, "last_seen_frame": 12},
        "3": {"player_id": None, "body_bank": [], "face": None, "last_seen_frame": None, "face_samples": []}})
    save("corner-pocket/face_embeddings.json", {
        "p1": [{"embedding": vec(512), "eye_px": 10.4, "det_score": 0.912, "created_at": "2026-09-05T10:00:00+00:00",
                "source": "6"}, {"embedding": vec(512), "eye_px": None, "det_score": 0.5,
                                 "created_at": "2026-09-05T10:00:01+00:00", "source": None}],
        "gone-player": [{"embedding": vec(512), "eye_px": 9.0, "det_score": 0.7,
                         "created_at": "2026-09-05T10:00:02+00:00", "source": "x.png"}]})
    save("pid_seed.json", {"seeds": {"1:68-94": {"win": "68-94", "t": 68, "track_id": 1, "label": "A",
                                                 "custom": "keep"},
                                     "2:68-94": {"win": "68-94", "t": 70.5, "track_id": 2, "label": "Guest Name"}}})
    save("scan30/annotations.json", {"16": {"verdict": "unsure", "note": "", "shooter": "",
                                            "updated_at": "2026-09-23T21:27:12.922718+00:00"},
                                     "9001": {"verdict": "wrong", "custom": 9}})
    save("unlabeled_crops/labels.json", {"/abs/unlabeled_crops/a.png": 4, "/abs/unlabeled_crops/b.png": "u",
                                         "legacy-other": 15})
    save("scan30/frame_results/2100/correction.json", {"dataset": "vod30", "frame_index": 2100, "boxes": [],
                                                       "table_polygon": None, "source": "manual",
                                                       "saved_at": "2026-09-23T20:58:05+00:00"})
    save("pid_anchors_vod30.json", {"anchors": {"70.0": [[10.5, 20.0]] * 6}})


@unittest.skipUnless(HAVE_DB, f"{db.ENV} is not set (docs/postgres.md)")
class Import(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.schema = f"test_import_{uuid.uuid4().hex[:12]}"
        self.conn = db.connect()
        self.conn.execute(f"CREATE SCHEMA {self.schema}")
        self.conn.execute(f"SET search_path TO {self.schema}")
        db.migrate(self.conn)

    def tearDown(self):
        self.conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
        self.conn.close()

    def files(self):
        return {str(p.relative_to(self.root)): md5(p) for p in sorted(self.root.rglob("*.json"))}

    def by_name(self, reports):
        return {r["dataset"]: r for r in reports}

    def test_every_data_set_imports_verified_and_a_second_run_changes_nothing(self):
        fixture(self.root)
        before = self.files()
        first = self.by_name(run(self.conn, self.root))
        self.assertEqual({name: r["status"] for name, r in first.items()},
                         {"operations": "imported", "identity": "imported", "faces": "imported",
                          "seeds": "imported", "verdicts": "imported", "labels": "imported",
                          "corrections": "imported", "anchors": "imported"}, first)
        self.assertEqual(first["operations"]["actual"],
                         {"ops_meta": 1, "players": 2, "tournaments": 4, "entrants": 3, "entrant_members": 4,
                          "matches": 3, "notes": 1, "sources": 1, "ops_events": 7})
        # hidden: absent, true and false survive as written (kept in tournaments.extra)
        from src.store_import import OperationsSet
        rendered = {t["id"]: t.get("hidden", "absent") for t in OperationsSet().render(self.conn)["history"]}
        self.assertEqual(rendered, {"t1": "absent", "t0": True, "t00": False})
        self.assertEqual(sorted(self.conn.execute("SELECT id, extra FROM tournaments WHERE archived_at IS NOT NULL")
                                .fetchall()), [("t0", {"hidden": True}), ("t00", {"hidden": False}), ("t1", {})])
        self.assertEqual(first["identity"]["actual"], {"identity_clusters": 3, "identity_face_samples": 1})
        self.assertEqual(first["faces"]["actual"], {"face_embeddings": 3})
        self.assertEqual(first["labels"]["actual"], {"ball_labels": 3})
        self.assertIn("1 cluster(s) written before face samples (no face_samples key)", first["identity"]["notes"])
        self.assertTrue(all(r["files_unchanged"] for r in first.values()))
        self.assertEqual(self.files(), before, "the import only reads the files")
        second = self.by_name(run(self.conn, self.root))
        self.assertEqual({r["status"] for r in second.values()}, {"unchanged"}, second)
        self.assertEqual(self.files(), before)

    def test_a_dry_run_verifies_everything_and_leaves_the_database_empty(self):
        fixture(self.root)
        reports = run(self.conn, self.root, dry_run=True)
        self.assertEqual({r["status"] for r in reports}, {"verified"}, reports)
        for table in ("ops_meta", "players", "identity_clusters", "face_embeddings", "ball_labels"):
            self.assertEqual(self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0, table)

    def test_different_data_already_in_the_database_is_refused_unless_replace(self):
        fixture(self.root)
        run(self.conn, self.root, ["operations"])
        state_path = self.root / "out" / "corner-pocket" / "state.json"
        state = json.loads(state_path.read_text())
        state["revision"] = 8
        state["notes"].append({"id": "n2", "text": "later", "createdAt": "2026-09-06T10:00:00+00:00"})
        state_path.write_text(json.dumps(state))
        refused = run(self.conn, self.root, ["operations"])[0]
        self.assertEqual(refused["status"], "refused")
        self.assertIn("database revision 7, file revision 8", refused["error"])
        self.assertEqual(self.conn.execute("SELECT revision FROM ops_meta").fetchone()[0], 7, "nothing written")
        replaced = run(self.conn, self.root, ["operations"], replace=True)[0]
        self.assertEqual(replaced["status"], "imported")
        self.assertEqual(replaced["actual"]["notes"], 2)

    def test_a_cluster_bound_to_an_id_off_the_roster_fails_its_set_only(self):
        fixture(self.root)
        path = self.root / "out" / "identity" / "clusters.json"
        clusters = json.loads(path.read_text())
        clusters["2"]["player_id"] = "typo"
        path.write_text(json.dumps(clusters))
        reports = self.by_name(run(self.conn, self.root))
        self.assertEqual(reports["identity"]["status"], "failed")
        self.assertIn("'typo'", reports["identity"]["error"])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM identity_clusters").fetchone()[0], 0,
                         "the failed set rolled back")
        self.assertEqual(reports["faces"]["status"], "imported", "other sets are independent")

    def test_the_production_files_round_trip_exactly_from_a_copy(self):
        """The real out/ files, copied first: every present data set verifies (dry run)."""
        copied = []
        for relative in ("corner-pocket/state.json", "identity/clusters.json", "corner-pocket/face_embeddings.json",
                         "pid_seed.json", "scan30/annotations.json", "scan_highlight/annotations.json",
                         "unlabeled_crops/labels.json", "unlabeled_crops2/labels.json",
                         "vod30_event_crops/labels.json", "pid_anchors_vod30.json"):
            source = REPO / "out" / relative
            if source.is_file():
                target = self.root / "out" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied.append(relative)
        if not copied:
            self.skipTest("no production files in this checkout")
        for report in run(self.conn, self.root, dry_run=True):
            self.assertIn(report["status"], ("verified", "unchanged", "absent"), report)


class FaceRow(unittest.TestCase):
    """The face_embeddings row and its one owner, with no PostgreSQL.

    Round 74 measured two writers of that table and one disagreement: the import
    wrote the embedding as the JSON file spells it, and the console wrote a
    float32 view, cut to EMBEDDING_DIM and rounded to four decimals.  The column
    list and the seven-parameter statement stood twice, once per writer.

    Both writers call ``src.store_import.face_row`` and execute
    ``src.store_import.FACE_INSERT`` now.  The cases below run both of them on one
    input through a recording connection: no server, no schema, no skip.
    """

    def console(self, additions):
        """``PostgresStore.faces_add`` over a recording connection."""
        from src.store_pg import PostgresStore
        statements, bound = [], []

        class Cursor:
            def __init__(self, rows):
                self.rows = rows

            def fetchone(self):
                return self.rows[0]

            def fetchall(self):
                return self.rows

        class Connection:
            def execute(self, statement, params=None):
                text = " ".join(statement.split())
                if text.startswith("SELECT coalesce(max(position)"):
                    return Cursor([[0]])      # the position of the first row of an empty table
                if text.startswith("SELECT"):
                    return Cursor([])         # the table is empty, so render reads no row
                statements.append(text)
                bound.append(tuple(params or ()))   # the LOCK statement binds nothing
                return Cursor([])

        class Transaction:
            def __enter__(self):
                return Connection()

            def __exit__(self, *exc):
                return False

        store = object.__new__(PostgresStore)
        held = PostgresStore._write
        PostgresStore._write = lambda self: Transaction()
        self.addCleanup(setattr, PostgresStore, "_write", held)
        return store.faces_add(additions), statements, bound

    def importer(self, doc):
        """``FacesSet.write`` over a recording connection."""
        from src.store_import import FacesSet
        statements, bound = [], []

        class Connection:
            def execute(self, statement, params=None):
                statements.append(" ".join(statement.split()))
                bound.append(tuple(params))

        FacesSet().write(Connection(), doc)
        return statements, bound

    def row(self, **changed):
        import numpy as np
        from src.face_id import EMBEDDING_DIM
        entry = {"embedding": [0.0] * EMBEDDING_DIM, "eye_px": [10.0, 20.0],
                 "det_score": 0.9, "created_at": "2026-01-01T00:00:00+00:00",
                 "source": "manual"}
        entry["embedding"][0] = 0.1234567890123456
        entry.update(changed)
        return entry

    def test_the_two_writers_bind_one_statement_and_one_value(self):
        from src.store_import import FACE_INSERT
        entry = self.row()
        imported = self.importer({"p1": [entry]})[1][0]
        _, statements, bound = self.console({"p1": [entry]})
        self.assertEqual(imported, bound[-1],
                         "the two writers of face_embeddings bind one input differently")
        self.assertEqual(statements[-1], " ".join(FACE_INSERT.split()),
                         "the console writer no longer executes the one statement")
        self.assertEqual(len(imported), " ".join(FACE_INSERT.split()).count("%s"),
                         "the bound values and the parameters of the one statement disagree")
        self.assertEqual(len(imported), 7, "one face_embeddings row binds player_id plus six columns")

    def test_the_statement_is_the_one_statement_of_the_row(self):
        from src.store_import import FACE_INSERT
        statements, bound = self.importer({"p1": [self.row()]})
        self.assertEqual(statements, [" ".join(FACE_INSERT.split())],
                         "the import no longer executes the one statement of the row")
        self.assertEqual(len(bound[0]), len(statements[0].split("VALUES")[1].split("%s")) - 1,
                         "the parameter count and the placeholder count disagree")

    def test_the_written_value_is_the_console_value(self):
        import numpy as np
        from src.store_import import face_row
        entry = self.row()
        embedding = face_row(entry)[0]
        self.assertEqual(len(embedding), 512)
        self.assertNotEqual(embedding[0], entry["embedding"][0],
                            "the stored value must be the float32 value, not the JSON text")
        self.assertEqual(embedding[0], 0.1235)
        self.assertEqual(embedding[1], 0.0)
        self.assertIsInstance(embedding, list)
        self.assertIsNotNone(np.asarray(embedding, np.float32))

    def test_the_row_of_the_import_is_a_face_row(self):
        from src.store_import import FACE_COLUMNS, face_row
        self.assertEqual(tuple(FACE_COLUMNS[-1:]), ("position",),
                         "position is the last bound value of a row, and not a value of face_row")
        self.assertEqual(len(face_row(self.row())), len(FACE_COLUMNS) - 1,
                         "face_row binds every column except the position of the caller")


if __name__ == "__main__":
    unittest.main()
