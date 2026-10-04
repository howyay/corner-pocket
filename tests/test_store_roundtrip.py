"""Files -> Postgres -> files, byte for byte (docs/postgres-design.md 7.3, 7.4).

Each case builds a workspace of user-data files in a temp dir, imports it into a
throwaway schema, exports into another temp dir, and compares every file byte for
byte (the first differing offset is the failure message), with row counts per
table. Runs only when POOL_DATABASE_URL is set; never touches the live tables.

The operations document is produced by the real annotator.operations code, so it
carries every key the application writes today: players from player_save (their own
key order), a second-chance draw that was undone and redrawn (revival with attempt,
revival_draws), an archived night that is hidden, a shown doubles pairing from a
solo pool (pool, pairing, null pids) and matches with null sides.
"""
import json
import os
import shutil
import tempfile
import unittest
import unittest.mock
import uuid
from pathlib import Path

import numpy as np

from src import db

HAVE_DB = bool(os.environ.get(db.ENV))
REPO = Path(__file__).resolve().parents[1]


def operations_state(root: Path) -> Path:
    from annotator.operations import Operations
    ops = Operations(root)

    def post(action, **fields):
        return ops.post(dict(action=action, revision=ops.get()["revision"], **fields))

    post("player_save", name="Ana", rating=600, notes="left-handed")
    post("player_save", name="Bo")
    post("tournament_setup", raceTo=1, tables=4, name="Friday")
    for name in ("Cy", "Di", "Ed", "Fa", "Gi"):
        post("entrant_add", members=[{"name": name}])
    state = post("tournament_start")
    for match in [m for m in state["tournament"]["matches"] if m["round"] == 1 and all(m["sides"])]:
        post("match_schedule", id=match["id"])
        post("match_score", id=match["id"], score=[1, 0])
        post("match_complete", id=match["id"])
    post("revival_draw", confirm=True)
    post("revival_undo", confirm=True)
    post("revival_draw", confirm=True)                     # attempt 2, revival_draws 2
    archived = post("tournament_new", confirm=True)["history"][-1]
    post("tournament_hide", id=archived["id"], hidden=True, confirm=True)
    post("tournament_setup", raceTo=1, format="doubles", name="Doubles")
    for name in ("Ha", "Io"):
        post("solo_add", member={"name": name})
    post("pair_draw")                                      # a pairing shown, not accepted
    post("note_add", text="cloth replaced")
    # Round 11 (owner, m07044): the broadcast-to-night relation. Two rows for the archived night -
    # the same night covered by two broadcasts - so the import proves the join table survives
    # Postgres in ops_meta.extra and comes back with its numbers, not just its keys.
    post("vod_link", vodId="2274501933", eventId=archived["id"], startS=3600, endS=11400,
         title="Wednesday 8-Ball Open", channel="cornerpocket", length_s=13800,
         created_at="2026-09-30T05:50:00+00:00")
    post("vod_link", vodId="2884327358", eventId=archived["id"], title="260918")
    return ops.path


def workspace(root: Path) -> None:
    """Every user-data file, in the exact format its application writer produces."""
    from src.face_id import store_faces
    from src.person_identity import IdentityIndex
    from src.store import JsonStore
    state = json.loads(operations_state(root).read_text())
    players = {p["name"]: p["id"] for p in state["players"]}
    index = IdentityIndex(root / "out" / "identity" / "clusters.json")
    rng = np.random.RandomState(9)
    for cid in (1, 2, 3):
        index.register(cid, rng.standard_normal(128).astype(np.float32), frame_index=cid)
    face = rng.standard_normal(512).astype(np.float32)
    index.record_face_sample(1, face / np.linalg.norm(face), eye_px=12.3, det_score=0.91,
                             bbox=[1.5, 2.0, 30.25, 40.0], frame_index=1)
    index.explicit_assign(1, players["Ana"])               # saves: IdentityIndex.save's format
    store_faces(root / "out" / "corner-pocket" / "face_embeddings.json",
                {players["Ana"]: [{"embedding": face / np.linalg.norm(face), "eye_px": 10.4, "det_score": 0.912,
                                   "source": "6"}]})
    files = JsonStore(root)                               # the server's own writers for the rest
    files.seed_put("vod30", "1:68-94", {"win": "68-94", "t": 68.0, "track_id": 1, "label": "A"})
    files.seed_put("vod30", "2:68-94", {"win": "68-94", "t": 70.5, "track_id": 2, "label": "Guest"})
    files.verdict_put("vod30", 16, {"verdict": "unsure", "note": "", "shooter": ""})
    files.verdict_put("vod30", 9001, {"shooter": "A"})
    files.verdict_put("vod30", 9001, {"verdict": "wrong"})  # merged: keeps its first keys first
    files.label_put("unlabeled_crops", "b.png", "u")
    files.label_put("unlabeled_crops", "a.png", 4)         # not sorted: file order is write order
    files.correction_put("vod30", 2100, {"dataset": "vod30", "frame_index": 2100, "boxes": [],
                                         "table_polygon": None, "source": "manual", "saved_at": "t"})
    files.anchors_put("vod30", "70.0", [[10.5, 20.0]] * 6)


@unittest.skipUnless(HAVE_DB, f"{db.ENV} is not set (docs/postgres.md)")
class RoundTrip(unittest.TestCase):
    def setUp(self):
        from src.store_import import run
        self.run = run
        self.source = Path(tempfile.mkdtemp())
        self.target = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.source, True)
        self.addCleanup(shutil.rmtree, self.target, True)
        self.schema = f"test_roundtrip_{uuid.uuid4().hex[:12]}"
        self.conn = db.connect()
        self.conn.execute(f"CREATE SCHEMA {self.schema}")
        self.conn.execute(f"SET search_path TO {self.schema}")
        db.migrate(self.conn)

    def tearDown(self):
        self.conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
        self.conn.close()

    def files(self, root):
        return sorted(str(p.relative_to(root)) for p in (root / "out").rglob("*.json"))

    def assert_round_trip(self, ignore=()):
        """`ignore`: files in the source that are not user data (never imported)."""
        from src.store_export import compare, export, row_counts
        before = {rel: (self.source / rel).read_bytes() for rel in self.files(self.source)}
        reports = self.run(self.conn, self.source)
        self.assertTrue(all(r["status"] in ("imported", "unchanged", "absent") for r in reports), reports)
        again = self.run(self.conn, self.source)
        self.assertEqual({r["status"] for r in again} - {"absent"}, {"unchanged"}, "a second import changes nothing")
        written = export(self.conn, self.target)
        self.assertEqual(sorted(written), sorted(set(before) - set(ignore)), "exactly the source files are exported")
        for row in compare(self.target, self.source, written):
            self.assertTrue(row["identical"], f"{row['file']} differs at byte {row.get('offset')}: {row.get('reason')}")
        self.assertEqual({rel: (self.source / rel).read_bytes() for rel in before}, before, "the source is only read")
        return row_counts(self.conn)

    def test_every_user_data_file_round_trips_byte_for_byte(self):
        workspace(self.source)
        state = json.loads((self.source / "out/corner-pocket/state.json").read_text())
        archived = state["history"][-1]
        self.assertEqual((archived["hidden"], archived["revival_draws"], archived["revival"]["attempt"]), (True, 2, 2))
        self.assertEqual(state["tournament"]["pairing"]["teams"][0][0]["pid"], None)
        self.assertIn(None, [side for m in archived["matches"] for side in m["sides"]])
        rows = self.assert_round_trip()
        self.assertEqual({t: rows[t] for t in ("ops_meta", "players", "tournaments", "identity_clusters",
                                               "identity_face_samples", "face_embeddings", "track_seeds",
                                               "event_verdicts", "ball_labels", "frame_corrections", "pocket_anchors")},
                         {"ops_meta": 1, "players": 2, "tournaments": 2, "identity_clusters": 3,
                          "identity_face_samples": 1, "face_embeddings": 1, "track_seeds": 2, "event_verdicts": 2,
                          "ball_labels": 2, "frame_corrections": 1, "pocket_anchors": 1})
        self.assertEqual(rows["ops_events"], state["revision"])

    def test_writes_through_the_postgres_store_export_what_the_json_store_writes(self):
        """The same mutations through JsonStore and through PostgresStore give the same bytes."""
        from src.store import JsonStore
        from src.store_export import export
        from src.store_pg import PostgresStore
        json_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, json_root, True)
        stores = [JsonStore(json_root), PostgresStore(self.source, search_path=self.schema)]
        self.addCleanup(stores[1].close)
        for store in stores:
            state = store.ops_post({"action": "player_save", "revision": 0, "name": "Ana"})
            store.ops_post({"action": "note_add", "revision": state["revision"], "text": "kept"})
            store.seed_put("vod30", "1:68-94", {"win": "68-94", "t": 68, "track_id": 1, "label": "A"})
            store.verdict_put("vod30", 9001, {"shooter": "A"})
            store.label_put("unlabeled_crops", "b.png", "u")
            store.label_put("unlabeled_crops", "a.png", 4)
            store.anchors_put("vod30", "70.0", [[1.5, 2]] * 6)
            store.correction_put("vod30", 5, {"boxes": [], "saved_at": "t"})
        export(self.conn, self.target)
        # generated ids and timestamps differ between the two runs; compare everything else
        def normal(text):
            value = json.loads(text)
            for key in ("id", "createdAt", "joinedAt", "updated_at"):
                value = _blank(value, key)
            return json.dumps(value, indent=2)
        for rel in self.files(json_root):
            original, exported = (json_root / rel).read_text(), (self.target / rel).read_text()
            self.assertEqual(normal(exported), normal(original), rel)
            self.assertEqual(len(exported.splitlines()), len(original.splitlines()), f"{rel}: same layout")

    def test_an_imported_vods_correction_and_verdict_round_trip_byte_for_byte(self):
        """out/vods/<id>/frame_results/<n>/correction.json and out/vods/<id>/annotations.json,
        written by the server's own JSON store, go files -> import -> export unchanged. The
        index itself (out/vods/index.json) is catalogue data vod_import writes, not user
        data: it is read, never imported, and stays a file."""
        from src.store import JsonStore
        dataset = "tw-1000000001-3600-3900"
        index = self.source / "out" / "vods" / "index.json"
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(json.dumps({"vods": {dataset: {"vod_id": "1000000001", "channel": "examplechannel"}}}))
        files = JsonStore(self.source)
        files.correction_put(dataset, 120, {"dataset": dataset, "frame_index": 120, "boxes": [{"label": "ball"}],
                                            "table_polygon": None, "source": "manual", "saved_at": "t"})
        files.verdict_put(dataset, 7, {"shooter": "A"})
        files.verdict_put(dataset, 7, {"verdict": "wrong"})
        self.assertTrue((self.source / "out/vods" / dataset / "frame_results/120/correction.json").is_file())
        self.assertTrue((self.source / "out/vods" / dataset / "annotations.json").is_file())
        rows = self.assert_round_trip(ignore=("out/vods/index.json",))
        self.assertEqual((rows["frame_corrections"], rows["event_verdicts"]), (1, 1))

    def test_a_fresh_copy_of_production_round_trips_byte_for_byte(self):
        copied = 0
        for rel in ("corner-pocket/state.json", "identity/clusters.json", "corner-pocket/face_embeddings.json",
                    "pid_seed.json", "scan30/annotations.json", "scan_highlight/annotations.json",
                    "unlabeled_crops/labels.json", "unlabeled_crops2/labels.json", "vod30_event_crops/labels.json",
                    "pid_anchors_vod30.json"):
            src = REPO / "out" / rel
            if src.is_file():
                dst = self.source / "out" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
        if not copied:
            self.skipTest("no production files in this checkout")
        self.assert_round_trip()

    def test_a_rollback_export_over_old_files_cannot_bring_deleted_faces_back(self):
        """After the last player's faces are deleted in the database, the face store has
        no rows, so the export writes no face file. Exported over the old out/ (the
        rollback), --prune must delete the stale face file, or the deleted biometrics
        would return."""
        from src.store_export import main as export_main
        from src.store_pg import PostgresStore
        workspace(self.source)
        self.assertTrue(all(r["status"] != "failed" for r in self.run(self.conn, self.source)))
        rollback_target = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, rollback_target, True)
        shutil.copytree(self.source / "out", rollback_target / "out")        # the old files
        faces = "out/corner-pocket/face_embeddings.json"
        self.assertTrue((rollback_target / faces).is_file())
        store = PostgresStore(self.source, search_path=self.schema)
        self.addCleanup(store.close)
        for player in list(store.faces_load()):
            store.faces_remove(player)                                        # forget, through the store
        with unittest.mock.patch.dict(os.environ, {"PGOPTIONS": f"-c search_path={self.schema}"}):
            code = export_main(["--to", str(rollback_target), "--prune"])
        self.assertEqual(code, 0)
        self.assertFalse((rollback_target / faces).exists(), "the deleted face data did not come back")
        self.assertTrue((rollback_target / "out/corner-pocket/state.json").is_file())


def _blank(value, key):
    if isinstance(value, dict):
        return {k: ("*" if k == key else _blank(v, key)) for k, v in value.items()}
    if isinstance(value, list):
        return [_blank(v, key) for v in value]
    return value


if __name__ == "__main__":
    unittest.main()
