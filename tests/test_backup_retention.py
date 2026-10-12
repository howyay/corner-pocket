"""The backup retention stands in four places, and one case holds the four together.

Round 59 measured four standings of the retention number:

    scripts/pool-postgres-backup.sh:13   KEEP_DAYS="${POOL_BACKUP_KEEP_DAYS:-14}"   the default
    deploy/systemd/pool-postgres-backup.service:17   Environment=POOL_BACKUP_KEEP_DAYS=14
    deploy/systemd/pool-postgres-backup.service:9    "... 14-day retention"
    docs/postgres.md:205                 "dumps older than 14 days are deleted"

The deletion itself reads the variable, at scripts/pool-postgres-backup.sh:42
(`-mtime +"$KEEP_DAYS"`), so the number has one runtime home.

Round 59 chose this shape: the number keeps its default in the script, and this case compares
every standing against that default.  The script must still run without the variable, because
docs/postgres.md documents the default, so the unit may not become the only home.  The case
fails with the file, the line and the two numbers when one standing moves.

    ./scripts/pool-test.sh python test_backup_retention

Round 93 added a second number of this module: the staleness window, 48 h.

    scripts/pool-postgres-backup.sh:50   [ "$age_h" -le 48 ]   the one runtime read
    deploy/systemd/pool-postgres-verify.service:2   "... older than 48 h ..."
    docs/postgres.md:206                 "... older than 48 h ..."

Only the script enforces the window, and the unit calls the script.  The other
two texts are prose, so three copies of one number can drift in silence.  The
case below holds the three numbers equal to one frozen value.

Round 96 added a third number of this module: the hour and the minute of each
timer.  The same two text holders state the schedule, so one schedule has two
homes:

    deploy/systemd/pool-postgres-backup.timer:6   OnCalendar=*-*-* 05:30:00
    deploy/systemd/pool-postgres-verify.timer:6   OnCalendar=Mon *-*-* 06:00:00
    docs/postgres.md:205                          "daily 05:30 ..."
    docs/postgres.md:206                          "Mondays 06:00"

No other case reads `OnCalendar`, and `tests/test_unit_render.py:55-61` requires
the units to be copied byte for byte, which compares no document row.  So the
document row can state another hour and no run reports it, and a unit that loses
its `OnCalendar` line stops scheduling in silence.

The cases below hold the two sides together:

1. `test_the_document_rows_hold_the_oncalendar_time_of_their_unit` compares the
   day and the time of each row of the document table with the `OnCalendar=`
   value of the unit that the row names.  It fails with the file, the line and
   both texts.
2. `test_a_planted_wrong_time_names_the_file_and_the_line_of_the_row` proves
   case 1 can fail: a temporary document holds one wrong time, and case 1 names
   that file and that line.
3. `test_a_unit_without_an_oncalendar_line_is_reported` proves a unit that
   loses the line cannot pass in silence.

Cases 2 and 3 run case 1 against a temporary tree.  A Python function reads its
module names through its own module object, so `_run_case` plants the two paths
in this module for the run, and restores them after it.
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pool-postgres-backup.sh"
SERVICE = ROOT / "deploy" / "systemd" / "pool-postgres-backup.service"
DOC = ROOT / "docs" / "postgres.md"
VERIFY_SERVICE = ROOT / "deploy" / "systemd" / "pool-postgres-verify.service"
TIMERS = ROOT / "deploy" / "systemd"

# (row in the document table, unit file, weekday token of the OnCalendar value)
# The weekday token is the systemd.time(7) spelling of the day: `daily` means
# every day, and `Mon` means Monday.
TIMER_ROWS = (
    ("the backup row", "pool-postgres-backup.timer", "daily"),
    ("the verify row", "pool-postgres-verify.timer", "Mon"),
)

# systemd.time(7) takes an abbreviated weekday name or a full one.  The document
# spells Monday as `Mondays`, so both sides come to one token before the compare.
DAY_TOKENS = (
    ('mon', ('mon', 'monday')), ('tue', ('tue', 'tuesday')), ('wed', ('wed', 'wednesday')),
    ('thu', ('thu', 'thursday')), ('fri', ('fri', 'friday')), ('sat', ('sat', 'saturday')),
    ('sun', ('sun', 'sunday')),
)


def _day(spelling):
    """The one token of a day, or `*` for every day, or `?` for an unknown word."""
    word = spelling.lower()
    if word in ('*', 'daily'):
        return '*'
    for token, names in DAY_TOKENS:
        if word in names:
            return token
    return '?'

# The day and the time of one systemd calendar event.  The weekday is optional,
# and `daily` is the systemd.time(7) alias of `*-*-*`.
ON_CALENDAR = re.compile(
    r'^OnCalendar=(?:(?P<day>[A-Za-z]+)\s+)?\*-\*-\*\s+'
    r'(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})\s*$')
# A time with an hour and a minute, for example `05:30`.
ROW_CLOCK = re.compile(r'\b(\d{1,2}:\d{2})\b')
# The day cell of a row: `daily` or a weekday name, with or without its `s`.
ROW_DAY = re.compile(r'\b(daily|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|'
                     r'fri(?:day)?|sat(?:urday)?|sun(?:day)?)s?\b', re.IGNORECASE)
# The unit cell of a row: one `NAME.timer` in a backtick pair.
ROW_UNIT = re.compile(r'`([^`]+\.timer)`')
# One cell separator of a document table row.  Only the `when` cell is read, and
# that cell holds no `|` of its own.
CELL_SEPARATOR = re.compile(r'\|')

# (standing name, file, pattern that captures the number)
STANDS = (
    ("the script default", SCRIPT, r'^KEEP_DAYS="\$\{POOL_BACKUP_KEEP_DAYS:-(\d+)\}"'),
    ("the unit environment", SERVICE, r'^Environment=POOL_BACKUP_KEEP_DAYS=(\d+)\s*$'),
    ("the unit description", SERVICE, r"\(pg_dump -Fc, (\d+)-day retention\)"),
    ("the document sentence", DOC, r"dumps older than (\d+) days are deleted"),
)

# (standing name, file, pattern that captures the number) of the staleness window
STALE_STANDS = (
    ("the script limit", SCRIPT, r'\[\s*"\$age_h"\s+-le\s+(\d+)\s*\]'),
    ("the unit comment", VERIFY_SERVICE, r"older than (\d+) h"),
    ("the document row", DOC, r"older than (\d+) h"),
)


def _capture(path, pattern):
    """(number, line number) of the first line of `path` that `pattern` captures, or None."""
    for number, line in enumerate(path.read_text().splitlines(), 1):
        found = re.search(pattern, line)
        if found:
            return int(found.group(1)), number
    return None


def _calendar_rows(path):
    """Return (unit file name, day token, `hour:minute`, line number, the line) per line."""
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        found = ON_CALENDAR.match(line)
        if not found:
            continue
        day = _day(found.group('day') or '*')
        clock = f"{found.group('hour')}:{found.group('minute')}"
        rows.append((path.name, day, clock, number, line.strip()))
    return rows


def _document_rows():
    """Yield (unit file name, day token, `hour:minute`, line number) of each timer row.

    A row of the table has three cells.  The `what` cell holds `|` characters of
    its own, so this reader takes the first cell as the unit and the second cell
    as the `when` text.
    """
    rows = []
    for number, line in enumerate(DOC.read_text().splitlines(), 1):
        if not line.startswith('|'):
            continue
        cells = CELL_SEPARATOR.split(line)
        if len(cells) < 4:
            continue
        unit = ROW_UNIT.search(cells[1])
        when = ROW_DAY.search(cells[2])
        clock = ROW_CLOCK.search(cells[2])
        if not (unit and when and clock):
            continue
        rows.append((unit.group(1).strip(), _day(when.group(1)), clock.group(1), number))
    return rows


def _schedule_problems():
    """Name every row that does not hold the schedule of its unit, or None."""
    units = {}
    for path in sorted(TIMERS.glob('*.timer')):
        for name, day, clock, line, text in _calendar_rows(path):
            units.setdefault(name, []).append((day, clock, line, text))

    problems = []
    document_rows = _document_rows()
    for row, name, day in TIMER_ROWS:
        found = [entry for entry in document_rows if entry[0] == name]
        if not found:
            problems.append(f'{DOC}: {row} lost its line, so the document no longer names '
                            f'{name}; the table states every row of the schedule, and the row '
                            f'must hold the OnCalendar value of {name}')
            continue
        if len(found) > 1:
            problems.append(f'{DOC}:{found[1][3]}: {row} stands twice, so the schedule of '
                            f'{name} has more than one document home')
            continue
        _row, rows_day, rows_clock, line = found[0]
        value = units.get(name, [])
        if not value:
            problems.append(f'{TIMERS / name}: no OnCalendar= line matches, so the unit lost '
                            f'the schedule that {DOC}:{line} states; the line at '
                            f'{DOC}:{line} says {rows_day} {rows_clock}')
            continue
        unit_day, unit_clock, unit_line, unit_text = value[0]
        if unit_day != _day(day):
            problems.append(f'{DOC}:{line}: {row} says {day}, and {TIMERS / name}:'
                            f'{unit_line} says {unit_text}; the unit holds the one schedule, '
                            f'so the row must hold {unit_text}')
        if unit_clock != rows_clock:
            problems.append(f'{DOC}:{line}: {row} says {rows_clock}, and {TIMERS / name}:'
                            f'{unit_line} says {unit_text}; the unit holds the one schedule')
    return problems or None


def _run_case(case_name, doc=None, timers=None):
    """Run one case of this module against alternative paths, and return its failure texts.

    The case runs from this module, so it is the real case.  A Python function
    reads its module names through its own module object, so this helper plants
    the two paths in the module and restores them after the run.  The case must
    therefore read the two paths through this module.
    """
    module = sys.modules[__name__]
    planted = {'DOC': doc or DOC, 'TIMERS': timers or TIMERS}
    kept = {name: module.__dict__[name] for name in planted}
    module.__dict__.update(planted)
    try:
        case = module.BackupRetentionTests(case_name)
        result = unittest.TestResult()
        case.run(result)
        return result.testsRun, [text for _case, text in result.failures]
    finally:
        module.__dict__.update(kept)


class BackupRetentionTests(unittest.TestCase):
    """One number, four standings: scripts, unit environment, unit description, document."""

    def test_every_standing_holds_the_script_default_number(self):
        default = _capture(SCRIPT, STANDS[0][2])
        self.assertIsNotNone(
            default,
            f'{SCRIPT}: no KEEP_DAYS default line matches, so the one home of the retention '
            f'number is gone')
        days, line = default
        problems = []
        for name, path, pattern in STANDS[1:]:
            found = _capture(path, pattern)
            if found is None:
                problems.append(f'{path}: no line matches {pattern!r}, so {name} lost the number; '
                                f'the script default says {days} days')
                continue
            other, other_line = found
            if other != days:
                problems.append(f'{path}:{other_line}: {name} says {other} days, the script default '
                                f'says {days} days (scripts/pool-postgres-backup.sh:{line}); the '
                                f'script default is the one home of the number')
        if problems:
            self.fail('\n'.join(problems))

    def test_the_deletion_reads_the_variable(self):
        prune = [line.strip() for line in SCRIPT.read_text().splitlines()
                 if re.search(r'-mtime \+"\$KEEP_DAYS"', line) and '-delete' in line]
        self.assertEqual(
            1, len(prune),
            f'{SCRIPT}: {len(prune)} lines prune by $KEEP_DAYS, and the number has one runtime '
            f'home; the deletion must read the variable, so a second number cannot stand here')

    def test_every_standing_of_the_staleness_window_holds_one_number(self):
        """The script limit, the unit comment and the document row hold one number."""
        found = []
        for name, path, pattern in STALE_STANDS:
            captured = _capture(path, pattern)
            if captured is None:
                self.fail(
                    f'{path}: no line matches {pattern!r}, so {name} lost the staleness '
                    f'window; the three texts must hold the window')
            found.append((name, path, *captured))

        numbers = {number for _name, _path, number, _line in found}
        if len(numbers) == 1:
            return
        script, script_path, script_number, script_line = found[0]
        self.fail('\n'.join(
            f'{path}:{line}: {name} says {number} h, and the one runtime read '
            f'({script_path.relative_to(ROOT)}:{script_line}, {script}) says {script_number} h'
            for name, path, number, line in found[1:]))

    def test_the_document_rows_hold_the_oncalendar_time_of_their_unit(self):
        """Every row of the table holds the day and the time of its own unit."""
        self.assertIsNone(
            _schedule_problems(),
            f'{DOC}: the table row and the unit must state one schedule; the OnCalendar= '
            f'line of the unit is the one home of the day and the time',
        )

    def test_a_planted_wrong_time_names_the_file_and_the_line_of_the_row(self):
        """A copy of this module reads a table with a planted time, and reports it."""
        real_rows = _document_rows()
        self.assertTrue(real_rows, f'{DOC}: the table holds no timer row to plant')
        _row, _day, clock, real_line = real_rows[0]
        planted_clock = f'{int(clock[:2]):02d}:{int(clock[3:]) + 1:02d}'
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / 'docs').mkdir()
            (tree / 'deploy' / 'systemd').mkdir(parents=True)
            for _row, name, _day in TIMER_ROWS:
                shutil.copy2(TIMERS / name, tree / 'deploy' / 'systemd' / name)
            lines = DOC.read_text().splitlines()
            lines[real_line - 1] = lines[real_line - 1].replace(clock, planted_clock)
            self.assertIn(
                planted_clock, lines[real_line - 1],
                f'{DOC}:{real_line}: the planted line does not hold {planted_clock}',
            )
            document = tree / 'docs' / 'postgres.md'
            document.write_text('\n'.join(lines) + '\n')

            ran, failure_texts = _run_case(
                'test_the_document_rows_hold_the_oncalendar_time_of_their_unit',
                doc=document, timers=tree / 'deploy' / 'systemd')
            self.assertEqual(1, ran, f'{document}: the planted case did not run once')
            self.assertEqual(
                1, len(failure_texts),
                f'{document}: {len(failure_texts)} failures, and the planted line must fail '
                f'the case once',
            )
            self.assertIn(f'{document}:{real_line}', failure_texts[0])
            self.assertIn(planted_clock, failure_texts[0])

    def test_a_unit_without_an_oncalendar_line_is_reported(self):
        """A copy of this module reads a unit without the line, and reports it."""
        with tempfile.TemporaryDirectory() as tmp:
            trees = Path(tmp) / 'deploy' / 'systemd'
            shutil.copytree(TIMERS, trees)
            unit = trees / TIMER_ROWS[0][1]
            whole = unit.read_text().splitlines()
            kept = [line for line in whole if not line.startswith('OnCalendar=')]
            self.assertNotEqual(
                kept, whole,
                f'{unit}: the planted copy kept its OnCalendar= line, so the case below '
                f'cannot show that a unit without the line is reported',
            )
            unit.write_text('\n'.join(kept) + '\n')

            ran, failure_texts = _run_case(
                'test_the_document_rows_hold_the_oncalendar_time_of_their_unit',
                timers=trees)
        self.assertEqual(1, ran, f'{unit}: the planted case did not run once')
        self.assertEqual(
            1, len(failure_texts),
            f'{unit}: {len(failure_texts)} failures, and a unit without the OnCalendar= line '
            f'must fail the case',
        )
        self.assertIn('OnCalendar= line', failure_texts[0])
        self.assertIn(str(unit), failure_texts[0])


if __name__ == '__main__':
    unittest.main()
