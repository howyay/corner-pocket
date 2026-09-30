"""GET /api/board (annotator/public_board.py): tonight's event, whitelisted field by field.

The fixture document is built through the real Operations rules, then salted
with every kind of private data the operations document holds; none of it may
reach the board. The Postgres case runs only when POOL_DATABASE_URL is set, in a
throwaway schema (the tests/test_store_contract.py pattern).
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import unittest.mock
import uuid

from annotator import public_board
from annotator.operations import Operations
from annotator.unified_server import Backend, BoundedHTTPServer, PublicBoardServer, make_handler, make_public_handler
from src import db

HAVE_DB = bool(os.environ.get(db.ENV))
#: Values that exist only in private parts of the document (a guest's old name included).
PRIVATE_VALUES = ("SECRET-NOTE", "PLAYER-NOTES-TEXT", "twitch.tv", "examplechannel", "secretchannel", "ARCHIVED-NIGHT",
                  "Archived Ann", "Old Guest", "HIDDEN-NIGHT", "Hidden Guest", "Inactive Ivan", "Roster Only Rita",
                  "Guest Gina", "AUDIT-SECRET", "#1f4a70", "Traceback", "/home/")
#: Keys of the private parts, as they would appear in the JSON body.
PRIVATE_KEYS = ("id", "embedding", "faces", "rating", "notes", "sources", "history", "events", "players", "pid",
                "absent", "hidden", "archivedAt", "joinedAt", "winnerId", "entrants", "members", "createdAt",
                "completedAt", "settings", "clothColor", "lampGlow", "shotClock", "autoFrame", "publicBoard",
                "revival", "pool", "pairing", "vision", "identity", "det_score", "eye_px", "context", "action")
PRIVATE_STRINGS = PRIVATE_VALUES + tuple(f'"{key}":' for key in PRIVATE_KEYS)


def post(ops, action, **fields):
    return ops.post(dict(fields, action=action, revision=ops.get()["revision"]))


def rich_root(temp):
    """A night in progress (six entrants, two tables): results, a live match, a queue
    and a held match, plus notes, sources, audit events, faces, ratings, guests,
    player notes, an archived and a hidden night and appearance settings."""
    root = Path(temp)
    ops = Operations(root)
    for name, rating, notes in (("Archived Ann", 900, "archived only"), ("Inactive Ivan", 100, "gone")):
        post(ops, "player_save", name=name, rating=rating, notes=notes)
    post(ops, "tournament_setup", name="ARCHIVED-NIGHT", format="singles", tables=1, raceTo=2)
    ann = next(p["id"] for p in ops.get()["players"] if p["name"] == "Archived Ann")
    post(ops, "entrant_add", members=[{"pid": ann}])
    post(ops, "entrant_add", members=[{"name": "Old Guest"}])
    post(ops, "tournament_start")
    old = ops.get()["tournament"]["matches"][0]["id"]
    post(ops, "match_forfeit", id=old, side=1)
    post(ops, "tournament_new", confirm=True)
    post(ops, "tournament_setup", name="HIDDEN-NIGHT", format="singles", tables=1, raceTo=1)
    post(ops, "entrant_add", members=[{"pid": ann}])
    post(ops, "entrant_add", members=[{"name": "Hidden Guest"}])
    post(ops, "tournament_new", confirm=True)
    post(ops, "tournament_hide", id=ops.get()["history"][-1]["id"], hidden=True, confirm=True)
    ivan = next(p["id"] for p in ops.get()["players"] if p["name"] == "Inactive Ivan")
    post(ops, "player_save", id=ivan, name="Inactive Ivan", status="Inactive")
    post(ops, "player_save", name="Roster Only Rita", rating=777, notes="PLAYER-NOTES-TEXT")
    for name in ("Ana", "Bo", "Cy", "Dee"):
        post(ops, "player_save", name=name, rating=500, notes="PLAYER-NOTES-TEXT")
    post(ops, "tournament_setup", name="Friday 8-Ball", format="singles", tables=2, raceTo=3)
    ids = {p["name"]: p["id"] for p in ops.get()["players"]}
    for name in ("Ana", "Bo", "Cy", "Dee"):
        post(ops, "entrant_add", members=[{"pid": ids[name]}])
    post(ops, "entrant_add", members=[{"name": "Guest Gina"}])
    post(ops, "entrant_add", members=[{"name": "Eve"}])
    post(ops, "guest_promote", name="Guest Gina")  # Gina joins the regulars under her name...
    gina = next(p["id"] for p in ops.get()["players"] if p["name"] == "Guest Gina")
    post(ops, "player_save", id=gina, name="Gina Park")  # ...and is renamed: the board shows the new name
    post(ops, "entrant_absence", id=ops.get()["tournament"]["entrants"][5]["id"], absent=False)
    post(ops, "note_add", text="SECRET-NOTE about the till")
    post(ops, "source_add", url="https://www.twitch.tv/secretchannel")
    post(ops, "settings_update", clothColor="#1f4a70", lampGlow=0.3)
    post(ops, "tournament_start")
    # Six entrants in an 8-bracket: the first two seeds (Ana, Bo) get byes;
    # round 1 is Ana-bye, Bo-bye, Cy-Dee, Gina-Eve.
    t = ops.get()["tournament"]
    r1 = [m for m in t["matches"] if m["round"] == 1]
    post(ops, "match_schedule", id=r1[2]["id"], table=2)  # Cy v Dee on table 2
    post(ops, "match_score", id=r1[2]["id"], score=[3, 1])
    post(ops, "match_complete", id=r1[2]["id"])  # Cy wins 3-1
    post(ops, "match_forfeit", id=r1[3]["id"], side=1)  # Eve forfeits: Gina goes through
    r2 = [m for m in ops.get()["tournament"]["matches"] if m["round"] == 2]
    post(ops, "match_schedule", id=r2[0]["id"], table=1)  # Ana v Bo, live on table 1
    post(ops, "match_score", id=r2[0]["id"], score=[2, 1])
    post(ops, "match_absence", id=r2[1]["id"], side=0, absent=True)  # Cy has stepped out: held
    # Private data the rules do not write through this path: faces, identity, a
    # vision block, an audit event whose context names private things.
    state = json.loads(ops.path.read_text())
    for player in state["players"]:
        player["faces"] = [{"embedding": [0.125] * 8, "eye_px": 12.0, "det_score": 0.9}]
    state["vision"] = {"identity": "AUDIT-SECRET"}
    state["events"].append({"id": "e-secret", "createdAt": "2026-09-29T20:00:00+00:00", "revision": state["revision"],
                            "action": "note_add", "context": {"id": "n", "name": "AUDIT-SECRET"}})
    ops.path.write_text(json.dumps(state, indent=2) + "\n")
    return root, ops


def board_of(state):
    return public_board.build(state)


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root, cls.ops = rich_root(cls.temp.name)
        cls.state = cls.ops.get()
        cls.board = board_of(cls.state)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_no_private_string_or_key_reaches_the_board(self):
        body = public_board.encode(self.board)[1].decode()
        for secret in PRIVATE_STRINGS:
            with self.subTest(secret=secret):
                self.assertNotIn(secret, body)

    def test_no_internal_id_reaches_the_board(self):
        body = public_board.encode(self.board)[1].decode()
        ids = [p["id"] for p in self.state["players"]] + [e["id"] for e in self.state["tournament"]["entrants"]]
        ids += [m["id"] for m in self.state["tournament"]["matches"]] + [self.state["tournament"]["id"]]
        ids += [e["id"] for e in self.state["events"]] + [n["id"] for n in self.state["notes"]]
        ids += [s["id"] for s in self.state["sources"]] + [h["id"] for h in self.state["history"]]
        for ident in ids:
            self.assertNotIn(ident, body)

    def test_only_whitelisted_keys_at_every_level(self):
        allowed = {"board", "revision", "event", "tables", "next", "bracket", "standings", "name", "format",
                   "race_to", "phase", "slot", "round", "sides", "score", "status", "winner", "result", "table",
                   "since", "matches", "won", "lost", "played", "bye", "tbd"}

        def keys(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    yield from keys(item)
            elif isinstance(value, list):
                for item in value:
                    yield from keys(item)
        self.assertLessEqual(set(keys(self.board)), allowed)

    def test_event(self):
        self.assertEqual(self.board["board"], "on")
        self.assertEqual(self.board["revision"], self.state["revision"])
        self.assertEqual(self.board["event"], {"name": "Friday 8-Ball", "format": "singles", "race_to": 3,
                                               "phase": "active"})

    def test_tables_in_play(self):
        live = self.board["tables"]
        self.assertEqual(len(live), 1)
        self.assertEqual(live[0]["table"], 1)
        self.assertEqual(live[0]["sides"], [{"name": "Ana"}, {"name": "Bo"}])
        self.assertEqual(live[0]["score"], [2, 1])
        self.assertEqual(live[0]["status"], "live")
        self.assertEqual(live[0]["slot"], "r2m1")
        scheduled = [e for e in self.state["events"] if e["action"] == "match_schedule"][-1]
        self.assertEqual(live[0]["since"], scheduled["createdAt"])

    def test_next_up_holds_the_queue_and_the_held_match_last(self):
        self.assertEqual([(m["slot"], m["status"]) for m in self.board["next"]], [("r2m2", "delayed")])
        self.assertEqual(self.board["next"][0]["sides"], [{"name": "Cy"}, {"name": "Gina Park"}])
        self.assertNotIn("table", self.board["next"][0])

    def test_bracket(self):
        rounds = self.board["bracket"]
        self.assertEqual([r["round"] for r in rounds], [1, 2, 3])
        r1 = rounds[0]["matches"]
        self.assertEqual(r1[0]["sides"], [{"name": "Ana"}, {"bye": True}])
        self.assertEqual((r1[0]["status"], r1[0]["result"], r1[0]["winner"]), ("complete", "bye", 0))
        self.assertEqual((r1[2]["sides"], r1[2]["score"], r1[2]["winner"], r1[2]["result"]),
                         ([{"name": "Cy"}, {"name": "Dee"}], [3, 1], 0, "played"))
        self.assertEqual((r1[3]["sides"][0], r1[3]["winner"], r1[3]["result"]), ({"name": "Gina Park"}, 0, "forfeit"))
        final = rounds[2]["matches"][0]
        self.assertEqual((final["sides"], final["status"], final["winner"]), ([{"tbd": True}, {"tbd": True}], "pending", None))

    def test_tonights_table(self):
        self.assertEqual(self.board["standings"][:2], [{"name": "Cy", "won": 1, "lost": 0, "played": 1},
                                                       {"name": "Gina Park", "won": 1, "lost": 0, "played": 1}])
        rest = {row["name"]: (row["won"], row["lost"], row["played"]) for row in self.board["standings"][2:]}
        # Byes are not results; a forfeit is a signed loss.
        self.assertEqual(rest, {"Dee": (0, 1, 1), "Eve": (0, 1, 1), "Ana": (0, 0, 0), "Bo": (0, 0, 0)})

    def test_registration_night(self):
        state = Operations(Path(self.temp.name) / "fresh").get()
        board = board_of(state)
        self.assertEqual((board["event"]["phase"], board["tables"], board["next"], board["bracket"], board["standings"]),
                         ("registration", [], [], [], []))

    def test_board_off(self):
        state = json.loads(json.dumps(self.state))
        state["settings"]["publicBoard"] = False
        self.assertEqual(public_board.encode(board_of(state))[1], b'{"board":"off"}')
        state["settings"]["publicBoard"] = True
        self.assertEqual(board_of(state)["board"], "on")

    def test_etag_follows_content_not_time(self):
        etag, body = public_board.encode(self.board)
        again, later = public_board.encode(self.board, now=public_board.datetime(2030, 1, 1,
                                                                                 tzinfo=public_board.timezone.utc))
        self.assertEqual(etag, again)
        self.assertNotEqual(body, later)
        self.assertIn(b'"served_at":"2030-01-01T00:00:00+00:00"', later)
        changed = json.loads(json.dumps(self.board))
        changed["tables"][0]["score"] = [3, 1]
        self.assertNotEqual(public_board.encode(changed)[0], etag)


class Loopback:
    def __init__(self, server_class, handler):
        quiet = type("Quiet", (handler,), {"log_message": lambda self, *args: None})
        self.httpd = server_class(("127.0.0.1", 0), quiet)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response, response.read()
        finally:
            connection.close()


def tree(root):
    return {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


class EndpointTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root, self.ops = rich_root(temp.name)
        self.backend = Backend(self.root)
        self.public = Loopback(PublicBoardServer, make_public_handler(self.backend))
        self.operator = Loopback(BoundedHTTPServer, make_handler(self.backend))
        self.addCleanup(self.public.close)
        self.addCleanup(self.operator.close)

    def fresh(self):
        self.backend._board_cache = None  # skip the one-second cache

    def test_both_ports_serve_the_same_board_and_write_nothing(self):
        before = tree(self.root)
        response, body = self.public.get("/api/board")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(response.getheader("Cache-Control"), "no-cache")
        self.assertEqual(json.loads(body)["tables"][0]["sides"], [{"name": "Ana"}, {"name": "Bo"}])
        self.assertIn("served_at", json.loads(body))
        for secret in PRIVATE_STRINGS:
            self.assertNotIn(secret.encode(), body)
        operator, same = self.operator.get("/api/board")
        self.assertEqual((operator.status, same), (200, body))
        for _ in range(3):
            self.fresh()
            self.public.get("/api/board")
            self.public.get("/api/board?x=1", {"If-None-Match": response.getheader("ETag")})
        self.assertEqual(tree(self.root), before, "a GET wrote to the root")

    def test_etag_and_304(self):
        response, _ = self.public.get("/api/board")
        etag = response.getheader("ETag")
        self.assertRegex(etag, r'^W/"\d+-[0-9a-f]{16}"$')
        for header in (etag, etag.removeprefix("W/"), f'"nope", {etag}'):
            self.fresh()
            not_modified, body = self.public.get("/api/board", {"If-None-Match": header})
            self.assertEqual((not_modified.status, body), (304, b""))
            self.assertEqual(not_modified.getheader("ETag"), etag)
            self.assertIn("default-src 'self'", not_modified.getheader("Content-Security-Policy"))
        post(self.ops, "match_score", id=self.ops.get()["tournament"]["matches"][4]["id"], score=[2, 2])
        self.fresh()
        changed, body = self.public.get("/api/board", {"If-None-Match": etag})
        self.assertEqual(changed.status, 200)
        self.assertNotEqual(changed.getheader("ETag"), etag)
        self.assertEqual(json.loads(body)["tables"][0]["score"], [2, 2])

    def test_cached_for_about_a_second(self):
        with unittest.mock.patch.object(self.backend, "operations", wraps=self.backend.operations) as reads:
            for _ in range(20):
                self.public.get("/api/board")
            self.assertEqual(reads.call_count, 1)
            self.backend._board_cache = (self.backend._board_cache[0] - 1.0,) + self.backend._board_cache[1:]
            self.public.get("/api/board")
            self.assertEqual(reads.call_count, 2)

    def test_board_off_is_all_it_says(self):
        post(self.ops, "settings_update", clothColor="#1d5c44")  # the switch lands in commit 5; set it by hand here
        state = json.loads(self.ops.path.read_text())
        state["settings"]["publicBoard"] = False
        self.ops.path.write_text(json.dumps(state))
        self.fresh()
        response, body = self.public.get("/api/board")
        self.assertEqual((response.status, body), (200, b'{"board":"off"}'))

    def test_a_store_failure_says_nothing_about_it(self):
        with unittest.mock.patch.object(self.backend, "operations", side_effect=RuntimeError("/home/secret dsn=x")), \
                unittest.mock.patch("sys.stderr"):
            self.fresh()
            response, body = self.public.get("/api/board")
        self.assertEqual((response.status, body), (503, b'{"error":"unavailable"}'))
        self.assertEqual(response.getheader("Retry-After"), "3")


class JsonStoreByteIdentityTest(unittest.TestCase):
    def test_state_json_is_byte_identical_after_board_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            root, ops = rich_root(temp)
            before = ops.path.read_bytes(), ops.path.stat().st_mtime_ns
            backend = Backend(root)
            with unittest.mock.patch.dict(os.environ):
                os.environ.pop("POOL_DATABASE_URL", None)
                self.assertEqual(type(backend.store()).__name__, "JsonStore")
                for _ in range(5):
                    backend._board_cache = None
                    backend.public_board()
            self.assertEqual((ops.path.read_bytes(), ops.path.stat().st_mtime_ns), before)


@unittest.skipUnless(HAVE_DB, f"{db.ENV} is not set (docs/postgres.md)")
class PostgresBoardTest(unittest.TestCase):
    """The board through a PostgresStore in a throwaway schema: same payload, no write."""

    def test_same_board_and_no_write(self):
        from src.store_pg import PostgresStore
        with tempfile.TemporaryDirectory() as temp:
            root, ops = rich_root(temp)
            schema = f"test_board_{uuid.uuid4().hex[:12]}"
            with db.connect() as conn:
                conn.execute(f"CREATE SCHEMA {schema}")
                conn.execute(f"SET search_path TO {schema}")
                db.migrate(conn)
            try:
                store = PostgresStore(root, search_path=schema)
                try:
                    from src.store_files import put_document
                    with store._write() as conn:
                        put_document(conn, "out/corner-pocket/state.json", ops.path.read_text())
                    backend = Backend(root)
                    backend._store = store
                    with db.connect() as conn:
                        conn.execute(f"SET search_path TO {schema}")
                        before = conn.execute("SELECT md5(string_agg(t::text, '' ORDER BY t::text)) "
                                              "FROM json_documents t").fetchone()
                    body = json.loads(backend.public_board()[1])
                    self.assertEqual(body["tables"], json.loads(public_board.encode(board_of(ops.get()))[1])["tables"])
                    with db.connect() as conn:
                        conn.execute(f"SET search_path TO {schema}")
                        after = conn.execute("SELECT md5(string_agg(t::text, '' ORDER BY t::text)) "
                                             "FROM json_documents t").fetchone()
                    self.assertEqual(before, after)
                finally:
                    store.close()
            finally:
                with db.connect() as conn:
                    conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


if __name__ == "__main__":
    unittest.main()
