"""The write-fingerprint proof covers every table the migrations create.

``scripts/pool-write-fingerprint.sql`` holds one hand-written ``SELECT`` branch per user-data
table, and SQL cannot read ``db/migrations``.  The two lists can therefore drift apart, and
nothing else notices: a migration that creates a table leaves the proof printing a
complete-looking list that silently omits it, and no code under ``scripts/``, ``tools/``,
``tests/`` or ``.github/`` runs the file (the only callers are the shell recipe in
docs/postgres.md and a reader's memory).

These tests read the two texts with no database - the way ``tests/test_db.py`` reads a
migration file - and compare them in both directions, so they run in a checkout with no
PostgreSQL.  The comparison itself lives in the tool, not here:

    .venv/bin/python tools/write_fingerprint_coverage.py

``tools/write_fingerprint_coverage.py`` names the one intended exclusion, the migration
ledger ``schema_migrations``, with its reason.  The second class below perturbs copies of
the two files and proves the checker reports a difference, so the agreement asserted here
is not vacuous.  Nothing in this file writes to the checkout.
"""
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from src import db

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "write_fingerprint_coverage.py"
PROOF = ROOT / "scripts" / "pool-write-fingerprint.sql"
#: The proof printed 18 tables when this test was written: one branch per user-data table of
#: db/migrations then. It must not print fewer. Raise this only in a change that adds a table.
MIN_FINGERPRINTED_TABLES = 18


def load_tool():
    """The checker as a module: ``tools`` is not a package, so load it by path."""
    spec = importlib.util.spec_from_file_location("write_fingerprint_coverage_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass reads its own module back out of sys.modules
    spec.loader.exec_module(module)
    return module


CHECK = load_tool()


class TheProofCoversTheSchema(unittest.TestCase):
    """The shipped proof and the shipped migrations agree, with no database."""

    def test_no_table_the_migrations_create_is_missing_from_the_proof(self):
        result = CHECK.coverage()
        self.assertEqual(
            result.missing, (),
            "a table a migration creates is not fingerprinted, so a write to it would pass "
            "the before/after diff unseen. Add a branch to %s: %s"
            % (CHECK.label(CHECK.PROOF), ", ".join(f"{t} ({o})" for t, o in result.missing)))

    def test_no_branch_fingerprints_a_table_no_migration_creates(self):
        result = CHECK.coverage()
        self.assertEqual(
            result.stale, (),
            "the proof fingerprints a table the migrations do not create, so its line can "
            "never be read or trusted: %s" % "; ".join(
                f"{t} at line {line} ({why})" for t, line, why in result.stale))

    def test_every_branch_uses_one_expression(self):
        result = CHECK.coverage()
        self.assertEqual(
            result.problems, (),
            "the branches must fingerprint with one expression, print the name of the table "
            "they read, and fingerprint each table once: %s" % "; ".join(result.problems))

    def test_every_named_exclusion_still_matches_a_created_table(self):
        result = CHECK.coverage()
        self.assertEqual(
            result.unused, (),
            "an exclusion that no longer matches a created table hides the next table of "
            "that name from the scan: %s. Remove it from LEDGER in %s"
            % (result.unused, CHECK.label(TOOL)))

    def test_the_ledger_is_created_and_deliberately_not_fingerprinted(self):
        result = CHECK.coverage()
        self.assertIn("schema_migrations", result.created)
        self.assertNotIn("schema_migrations", result.covered)
        self.assertEqual(result.covered, tuple(sorted(set(result.created) - set(result.excluded))),
                         "the proof must cover exactly the created tables that are not excluded")

    def test_the_proof_never_prints_fewer_tables_than_it_does_today(self):
        result = CHECK.coverage()
        self.assertGreaterEqual(
            len(result.covered), MIN_FINGERPRINTED_TABLES,
            "the proof prints %d tables and must print no less than %d, so dropping a branch "
            "is not a way to make the check pass" % (len(result.covered), MIN_FINGERPRINTED_TABLES))
        text, status = CHECK.report()
        self.assertEqual(status, 0, text)


class TheCheckerSeesADifference(unittest.TestCase):
    """A perturbed copy must be reported, so the agreement above is not vacuous."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="write_fingerprint_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.migrations = self.dir / "migrations"
        shutil.copytree(db.MIGRATIONS, self.migrations)

    def proof_copy(self):
        """A scratch copy of the shipped proof; the checkout copy is only read."""
        copy = self.dir / "proof.sql"
        shutil.copyfile(PROOF, copy)
        return copy

    def test_a_table_a_new_migration_creates_is_reported_missing(self):
        (self.migrations / "0005_scratch.sql").write_text(
            "CREATE TABLE IF NOT EXISTS match_rosters (\n    id text PRIMARY KEY\n);\n",
            encoding="utf-8")
        result = CHECK.coverage(PROOF, self.migrations)
        self.assertEqual([table for table, _ in result.missing], ["match_rosters"])
        self.assertTrue(result.missing[0][1].endswith("0005_scratch.sql:1"), result.missing)
        text, status = CHECK.report(PROOF, self.migrations)
        self.assertEqual(status, 1)
        self.assertIn("MISSING   match_rosters", text)

    def test_a_removed_branch_is_reported_missing(self):
        copy = self.proof_copy()
        lines = copy.read_text(encoding="utf-8").splitlines(keepends=True)
        self.assertEqual(len([line for line in lines if "'pocket_anchors'" in line]), 1,
                         "the shipped proof must fingerprint pocket_anchors in one line")
        copy.write_text("".join(line for line in lines if "'pocket_anchors'" not in line),
                        encoding="utf-8")
        result = CHECK.coverage(copy, self.migrations)
        self.assertEqual([table for table, _ in result.missing], ["pocket_anchors"])
        self.assertEqual([line for line, _, _ in result.stale], [])

    def test_a_branch_for_a_table_nothing_creates_is_reported_stale(self):
        copy = self.proof_copy()
        text = copy.read_text(encoding="utf-8")
        copy.write_text(text.replace("'pocket_anchors'", "'ghost_table'")
                            .replace("FROM pocket_anchors x", "FROM ghost_table x"),
                        encoding="utf-8")
        result = CHECK.coverage(copy, self.migrations)
        self.assertEqual([table for table, _, _ in result.stale], ["ghost_table"])
        self.assertEqual([table for table, _ in result.missing], ["pocket_anchors"])
        text, status = CHECK.report(copy, self.migrations)
        self.assertEqual(status, 1)
        self.assertIn("STALE     ghost_table", text)

    def test_a_branch_that_prints_one_name_and_reads_another_is_reported(self):
        copy = self.proof_copy()
        text = copy.read_text(encoding="utf-8")
        copy.write_text(text.replace("'pocket_anchors'", "'players'"), encoding="utf-8")
        result = CHECK.coverage(copy, self.migrations)
        self.assertTrue(any("prints 'players' but reads FROM pocket_anchors" in problem
                            for problem in result.problems), result.problems)

    def test_a_truncated_proof_is_refused_not_read_as_complete(self):
        copy = self.proof_copy()
        copy.write_text(copy.read_text(encoding="utf-8").replace("ORDER BY 1;", ""),
                        encoding="utf-8")
        with self.assertRaises(CHECK.ProofError):
            CHECK.coverage(copy, self.migrations)


if __name__ == "__main__":
    unittest.main()
