"""src/db.py: the migration files and the missing-variable error are checked everywhere;
the database tests run only when POOL_DATABASE_URL is set (docs/postgres.md).

Each database test works in its own scratch schema, dropped afterwards, so the suite
never touches the application tables and leaves nothing behind.
"""
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from src import db

HAVE_DB = bool(os.environ.get(db.ENV))


def write(directory, files):
    for name, sql in files.items():
        (Path(directory) / name).write_text(sql)


class MigrationFiles(unittest.TestCase):
    def test_repo_migrations_are_well_formed_and_start_with_the_ledger(self):
        found = db.migrations()
        self.assertEqual(found[0][:2], (1, "0001_schema_migrations"))
        self.assertIn("CREATE TABLE IF NOT EXISTS schema_migrations", found[0][2])
        self.assertNotRegex("\n".join(sql for _, _, sql in found).upper(), r"\b(BEGIN|COMMIT)\s*;")

    def test_order_is_numeric_and_bad_names_or_duplicate_versions_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {"0010_c.sql": "c", "0002_b.sql": "b", "0001_a.sql": "a"})
            self.assertEqual([n for _, n, _ in db.migrations(Path(d))], ["0001_a", "0002_b", "0010_c"])
            write(d, {"0002_again.sql": "x"})
            with self.assertRaisesRegex(ValueError, "share version 0002"):
                db.migrations(Path(d))
        with tempfile.TemporaryDirectory() as d:
            write(d, {"1_short.sql": "x"})
            with self.assertRaisesRegex(ValueError, "NNNN_name.sql"):
                db.migrations(Path(d))

    def test_a_missing_url_is_a_clear_error(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(db.ENV, None)
            with self.assertRaisesRegex(db.DatabaseNotConfigured, "POOL_DATABASE_URL is not set"):
                db.connect()
            with self.assertRaises(db.DatabaseNotConfigured):
                with db.transaction():
                    pass


@unittest.skipUnless(HAVE_DB, f"{db.ENV} is not set (docs/postgres.md)")
class Database(unittest.TestCase):
    def setUp(self):
        self.schema = f"test_db_{uuid.uuid4().hex[:12]}"
        self.conn = db.connect()
        self.conn.execute(f"CREATE SCHEMA {self.schema}")
        self.conn.execute(f"SET search_path TO {self.schema}")

    def tearDown(self):
        self.conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
        self.conn.close()

    def exists(self, table):
        return self.conn.execute("SELECT to_regclass(%s)", (f"{self.schema}.{table}",)).fetchone()[0] is not None

    def ledger(self):
        return self.conn.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version").fetchall()

    def test_connects_as_the_configured_role(self):
        user, one = self.conn.execute("SELECT current_user, 1").fetchone()
        self.assertEqual((user, one), (self.conn.info.user, 1))
        self.assertGreaterEqual(self.conn.info.server_version, 160000)

    def test_migrations_apply_once_and_a_second_run_is_a_no_op(self):
        every = [v for v, _, _ in db.migrations()]
        self.assertEqual(db.migrate(self.conn), every)
        first = self.ledger()
        self.assertEqual([v for v, _, _ in first], every)
        self.assertEqual(db.migrate(self.conn), [])
        self.assertEqual(self.ledger(), first)

    def test_a_new_file_is_picked_up_and_an_edited_applied_file_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {"0001_schema_migrations.sql": (db.MIGRATIONS / "0001_schema_migrations.sql").read_text()})
            self.assertEqual(db.migrate(self.conn, Path(d)), [1])
            write(d, {"0002_two_tables.sql": "CREATE TABLE a (id int);\nCREATE TABLE b (id int);\n"})
            self.assertEqual(db.migrate(self.conn, Path(d)), [2])
            self.assertTrue(self.exists("a") and self.exists("b"))
            self.assertEqual(db.migrate(self.conn, Path(d)), [])
            write(d, {"0002_two_tables.sql": "CREATE TABLE a (id int);\n"})
            with self.assertRaisesRegex(RuntimeError, "0002_two_tables changed after it was applied"):
                db.migrate(self.conn, Path(d))

    def test_a_failing_migration_applies_nothing_from_that_run(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {"0001_schema_migrations.sql": (db.MIGRATIONS / "0001_schema_migrations.sql").read_text(),
                      "0002_ok.sql": "CREATE TABLE ok (id int);",
                      "0003_broken.sql": "SELECT 1 / 0;"})
            with self.assertRaises(Exception):
                db.migrate(self.conn, Path(d))
            self.assertFalse(self.exists("schema_migrations"))
            self.assertFalse(self.exists("ok"))

    def test_a_rolled_back_transaction_leaves_nothing_behind(self):
        self.conn.execute("CREATE TABLE kept (v text)")
        with self.assertRaises(ZeroDivisionError):
            with db.transaction() as tx:
                tx.execute(f"INSERT INTO {self.schema}.kept VALUES ('gone')")
                tx.execute(f"CREATE TABLE {self.schema}.also_gone (v text)")
                self.assertEqual(tx.execute(f"SELECT count(*) FROM {self.schema}.kept").fetchone()[0], 1)
                1 / 0
        self.assertEqual(self.conn.execute("SELECT count(*) FROM kept").fetchone()[0], 0)
        self.assertFalse(self.exists("also_gone"))
        with db.transaction() as tx:
            tx.execute(f"INSERT INTO {self.schema}.kept VALUES ('kept')")
        self.assertEqual(self.conn.execute("SELECT v FROM kept").fetchall(), [("kept",)])

    def test_0002_user_data_schema_applies_and_enforces_the_reviewed_rules(self):
        import psycopg   # the driver is only needed when a database is configured
        db.migrate(self.conn)
        for table in ("ops_meta", "players", "tournaments", "entrants", "entrant_members", "matches",
                      "notes", "sources", "ops_events", "identity_clusters", "identity_face_samples",
                      "face_embeddings", "track_seeds", "event_verdicts", "ball_labels",
                      "frame_corrections", "pocket_anchors"):
            self.assertTrue(self.exists(table), table)
        run = self.conn.execute
        # the name backstop is on name_key, the application's casefold key (written by the store)
        run("INSERT INTO players (id, name, status, rating, position, name_key) VALUES ('p1', 'Ana', 'Active', 0, 0, 'ana')")
        with self.assertRaises(psycopg.errors.UniqueViolation), self.conn.transaction():
            run("INSERT INTO players (id, name, status, rating, position, name_key) VALUES ('p2', 'ANA', 'Active', 0, 1, 'ana')")
        with self.assertRaises(psycopg.errors.NotNullViolation), self.conn.transaction():
            run("INSERT INTO players (id, name, status, rating, position) VALUES ('p3', 'Cy', 'Active', 0, 2)")
        # reviewed FK: a cluster can only name a roster player, and deleting the player unbinds it
        with self.assertRaises(psycopg.errors.ForeignKeyViolation), self.conn.transaction():
            run("INSERT INTO identity_clusters (cluster_id, player_id, body_bank) VALUES (9, 'typo', '{}')")
        run("INSERT INTO identity_clusters (cluster_id, player_id, body_bank) VALUES (1, 'p1', '{}')")
        run("DELETE FROM players WHERE id = 'p1'")
        self.assertIsNone(run("SELECT player_id FROM identity_clusters WHERE cluster_id = 1").fetchone()[0])
        # the embeddings round-trip exactly (double precision, not real)
        run("INSERT INTO face_embeddings (player_id, embedding, eye_px, det_score, created_at, position) "
            "VALUES ('p9', %s, 10.4, 0.912, 't', 0)", ([0.9120] * 512,))
        emb, eye, det = run("SELECT embedding, eye_px, det_score FROM face_embeddings").fetchone()
        self.assertEqual((emb[0], eye, det), (0.912, 10.4, 0.912))
        with self.assertRaises(psycopg.errors.CheckViolation), self.conn.transaction():
            run("INSERT INTO face_embeddings (player_id, embedding, created_at, position) VALUES ('p9', %s, 't', 1)",
                ([0.1] * 128,))
        # one current tournament, one match per live table, ball label vocabulary
        run("INSERT INTO tournaments (id, name, format, tables, race_to, status) VALUES ('t1', '', 'singles', 1, 1, 'registration')")
        with self.assertRaises(psycopg.errors.UniqueViolation), self.conn.transaction():
            run("INSERT INTO tournaments (id, name, format, tables, race_to, status) VALUES ('t2', '', 'singles', 1, 1, 'registration')")
        for bad in ('16', '"x"', '-1'):
            with self.assertRaises(psycopg.errors.CheckViolation), self.conn.transaction():
                run("INSERT INTO ball_labels (crop_set, crop_key, crop_file, label) "
                    "VALUES ('unlabeled_crops', %s, 'f', %s::jsonb)", ("k" + bad, bad))


if __name__ == "__main__":
    unittest.main()
