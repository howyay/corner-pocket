"""The table tuple of src/store_export.py holds every table the migrations create.

Round 70, Worth 3: ``row_counts`` of ``src/store_export.py`` counts the tables of the
hand-typed tuple ``TABLES`` (``src/store_export.py:43``).  The migrations create those
tables, so the tuple is a second copy of the created set and the two can drift apart in
silence: a migration that adds a table leaves ``row_counts`` reporting a shorter list,
and no case fails.  The neighbour guard ``tests/test_write_fingerprint.py`` holds the SQL
proof to the same schema, and it does not read this tuple.

One decision stands here and is held: exactly one created table is out of the tuple on
purpose, the migration ledger ``schema_migrations``.  ``NOT_OPERATOR_DATA`` of
``src/store_export.py:38`` names it with its reason.  Every other created table must
stand in ``TABLES``, and every name of ``TABLES`` must be a created table.

The reader of the created names has one home, ``created_tables`` of
``tools/write_fingerprint_coverage.py:147``: it reads the ``CREATE TABLE`` lines of
``db/migrations/*.sql`` and refuses a form it cannot parse.  ``tests/test_write_fingerprint.py``
reads the same reader, so the DDL syntax stays in one place and this module holds no
second copy of it.

Run: ``./scripts/pool-test.sh python test_store_export``
"""
import unittest

from src.store_export import NOT_OPERATOR_DATA, TABLES
from tools.write_fingerprint_coverage import created_tables

#: The tuple held 18 names when this case was written: every created table of
#: db/migrations then, less the ledger.  It must not hold fewer.  A dropped name is not a
#: way to make the case below pass; raise this number only in a change that adds a table.
MIN_TABLES = 18


def differences(tables, created, excluded):
    """(missing, stale) of one table tuple against one created set and its exclusions.

    ``missing`` holds each created table the tuple omits and the exclusions do not name.
    ``stale`` holds each name the tuple holds and no migration creates.
    """
    missing = sorted(set(created) - set(tables) - set(excluded))
    stale = sorted(set(tables) - set(created))
    return missing, stale


class TheTupleHoldsTheSchema(unittest.TestCase):
    """TABLES of src/store_export.py and the CREATE TABLE names of db/migrations agree."""

    def test_the_tuple_and_the_migrations_name_the_same_tables(self):
        """A table the DDL adds and the tuple misses fails here, with both lists."""
        created, files = created_tables()
        missing, stale = differences(TABLES, created, NOT_OPERATOR_DATA)
        self.assertEqual(
            [], missing + stale,
            "src/store_export.py TABLES and db/migrations disagree: %d tables in %d migration "
            "files, %d names in TABLES.  In the DDL and not in TABLES: %s.  In TABLES and in no "
            "migration: %s.  Add the new table to TABLES, or name it in NOT_OPERATOR_DATA with "
            "the reason it is not operator data."
            % (len(created), len(files), len(TABLES), missing, stale))

    def test_the_ledger_is_created_and_deliberately_out_of_the_tuple(self):
        """The one exclusion is a real table, and it stays out of the row count."""
        created, _ = created_tables()
        self.assertIn(
            "schema_migrations", created,
            "db/migrations does not create schema_migrations any more, so the exclusion in "
            "NOT_OPERATOR_DATA outlives its table; remove it")
        self.assertNotIn(
            "schema_migrations", TABLES,
            "TABLES holds schema_migrations, so row_counts prints the migration ledger as "
            "operator data; NOT_OPERATOR_DATA names it out on purpose")

    def test_every_exclusion_is_a_created_table_with_a_reason(self):
        """An exclusion cannot outlive its table, and it cannot stand without a reason."""
        created, _ = created_tables()
        unused = sorted(set(NOT_OPERATOR_DATA) - set(created))
        self.assertEqual(
            [], unused,
            "an exclusion names a table no migration creates: %s.  Remove it from "
            "NOT_OPERATOR_DATA, so it cannot hide the next table of that name." % unused)
        overlap = sorted(set(NOT_OPERATOR_DATA) & set(TABLES))
        self.assertEqual(
            [], overlap,
            "a name stands in TABLES and in NOT_OPERATOR_DATA, so one decision has two "
            "answers: %s" % overlap)
        for table, reason in sorted(NOT_OPERATOR_DATA.items()):
            with self.subTest(table=table):
                self.assertTrue(reason.strip(), f"{table} stands in NOT_OPERATOR_DATA with no reason")

    def test_the_tuple_never_holds_fewer_names_than_it_does_today(self):
        """A dropped name is not a way to make the case above pass."""
        self.assertGreaterEqual(
            len(TABLES), MIN_TABLES,
            "TABLES holds %d names and must hold no less than %d, so the count of row_counts "
            "stays the count of the user-data tables" % (len(TABLES), MIN_TABLES))

    def test_a_table_the_ddl_adds_is_reported_missing(self):
        """The comparison is not vacuous: one planted name and one removed name are seen."""
        created, _ = created_tables()
        planted = dict(created, zz_new_table="db/migrations/0005_zz_new_table.sql:3")
        self.assertEqual((["zz_new_table"], []), differences(TABLES, planted, NOT_OPERATOR_DATA))
        without = {name: site for name, site in created.items() if name != "json_documents"}
        self.assertEqual(([], ["json_documents"]), differences(TABLES, without, NOT_OPERATOR_DATA))
