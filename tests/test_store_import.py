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


if __name__ == "__main__":
    unittest.main()
