"""Hold the player status vocabulary to the three places that spell it.

A player row holds one of four status values.  ``annotator/operations.py`` owns the list, and
its save guard refuses a value outside it.  The database cannot import Python, so
``db/migrations/0002_user_data.sql`` repeats the names in a CHECK.  The console cannot import
Python either, so ``annotator/ops.js`` holds the same names for the edit form and for the
roster filter.

Round 47 measured the cost of the drift.  The console list held three of the four values, so
the edit form of a ``Prospect`` row showed ``Active``, and one save rewrote the row.

This module reads the three spellings and compares them.  It proves that the console spells
the names once, in one array, and that the Python guard reads the owner tuple.  The round trip
of a ``Prospect`` row through the form is a case of ``tests/test_ops.js``, because that suite
holds the renderer.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from annotator import operations

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'db' / 'migrations' / '0002_user_data.sql'
OPERATIONS = ROOT / 'annotator' / 'operations.py'
CONSOLE = ROOT / 'annotator' / 'ops.js'

# The status column of the players table.  The name travels into the failure text.
SQL_STATUS = re.compile(r"status\s+text\s+NOT NULL\s+CHECK\s*\(status IN \(([^)]*)\)\)")
# A JavaScript array literal on one line.  The comparison below reads the quoted values.
JS_ARRAY = re.compile(r'\[([^\[\]]*)\]')
JS_STRING = re.compile(r"'((?:\\.|[^'\\])*)'")
# The owner tuple, as this repository writes its tuples.
PY_TUPLE = re.compile(r'^PLAYER_STATUSES = \(([^)]*)\)$', re.MULTILINE)


def quoted(value: str) -> list[str]:
    return [match.group(1) for match in JS_STRING.finditer(value)]


def arrays_in(source: str) -> list[list[str]]:
    return [quoted(body) for body in JS_ARRAY.findall(source)]


class PlayerStatusVocabularyTests(unittest.TestCase):
    """The four values reach the database, the guard and the console as one list."""

    def setUp(self):
        self.sql = MIGRATION.read_text()
        self.console = CONSOLE.read_text()

    def test_the_owner_tuple_holds_the_four_values(self):
        self.assertEqual(operations.PLAYER_STATUSES,
                         ('Active', 'Visitor', 'Prospect', 'Inactive'),
                         'annotator/operations.py is the owner of the player status list')

    def test_the_database_check_holds_the_same_values(self):
        match = SQL_STATUS.search(self.sql)
        self.assertIsNotNone(match, 'db/migrations/0002_user_data.sql holds no status CHECK')
        self.assertEqual(sorted(quoted(match.group(1))), sorted(operations.PLAYER_STATUSES),
                         'the players status CHECK and annotator/operations.py disagree; '
                         'a value the guard accepts cannot fail at the database')

    def test_the_console_array_holds_the_same_values(self):
        arrays = [values for values in arrays_in(self.console)
                  if set(values) == set(operations.PLAYER_STATUSES)]
        self.assertEqual(1, len(arrays),
                         'annotator/ops.js must hold the four status values in one array; '
                         f'found {len(arrays)} such arrays')
        self.assertEqual(sorted(arrays[0]), sorted(operations.PLAYER_STATUSES),
                         'the console array and annotator/operations.py disagree')

    def test_the_console_spells_the_names_once(self):
        wanted = set(operations.PLAYER_STATUSES)
        lists = [values for values in arrays_in(self.console) if len(wanted & set(values)) > 1]
        self.assertEqual(1, len(lists),
                         'the console offers the status values in one array only; '
                         f'found {len(lists)} arrays that hold two or more of them: {lists}')

    def test_the_form_and_the_filter_read_that_array(self):
        self.assertIn('editing?PLAYER_STATUSES:', self.console,
                      'the edit form must read the one array; a typed list would drift again')
        self.assertIn("['',...PLAYER_STATUSES]", self.console,
                      'the roster filter must offer every status the form can show')

    def test_the_guard_reads_the_owner_tuple(self):
        source = OPERATIONS.read_text()
        self.assertIn('if status not in PLAYER_STATUSES:', source,
                      'the save guard must read PLAYER_STATUSES, not a second typed tuple')
        match = PY_TUPLE.search(source)
        self.assertIsNotNone(match, 'annotator/operations.py must define PLAYER_STATUSES')
        self.assertEqual(1, source.count(match.group(0)),
                         'annotator/operations.py spells the player status tuple once')


if __name__ == '__main__':
    unittest.main()
