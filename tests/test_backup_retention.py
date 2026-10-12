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

Round 97 added the mode of the backup directory.  One mode rule stands in nine
live places, and no case read them together (the last row holds two words):

    scripts/pool-postgres-backup.sh:11   umask 077                            the owner
    scripts/pool-postgres-backup.sh:23   [ "$(stat -c %a "$DIR")" = 700 ]     the runtime check
    deploy/systemd/pool-postgres-backup.service:5    "mode 700"               the comment
    deploy/systemd/pool-postgres-backup.service:19   UMask=0077               the unit
    deploy/systemd/pool-postgres-verify.service:15   UMask=0077               the unit
    docs/postgres.md:205                 "(dir mode 700, files 600)"          the document row

The script is the owner, so the case does not move the rule.  The case derives
the two directory and file modes from the one `umask` word of the script.  The
umask word sets the mode of every new file and directory, so a second copy of
the number can drift in silence, and one unit can drop the file mode.

Round 97 added two cases of this module:

1. `test_every_mode_word_matches_the_script_umask` reads the nine places, derives
   the directory mode and the file mode from the `umask` word of the script, and
   holds every mode word equal.  It fails with the file, the line, the word and
   the two modes.
2. `test_a_planted_wrong_umask_names_the_file_and_the_line` proves case 1 can
   fail: a copy of one unit holds `UMask=0022`, and case 1 names that file and
   that line.

Cases 2 and 3 of the schedule group run case 1 of that group against a temporary
tree.  A Python function reads its module names through its own module object,
so `_run_case` plants the alternate paths in this module for the run, and
restores them after it.  `_run_case` plants four paths: the document, the timers
directory, the script and the two unit files.
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

# The mode of the backup directory stands in nine places.  The `umask` word of
# the script is the owner, and the eight other places must hold the mode word of
# that umask.  `UMask` and `umask` spell one value in two ways: `0077`, `700` and
# `600` name one rule, because the umask removes the execute bits of a new
# directory and of a new file.
UMASK = re.compile(r'^\s*umask\s+([0-7]{3,4})\s*$')
MODE_CHECK = re.compile(r'stat\s+-c\s+%a\s+"\$DIR"\)"\s*=\s*([0-7]{3,4})\s*\]')
MODE_COMMENT = re.compile(r'mode\s+([0-7]{3,4})')
UMASK_DIRECTIVE = re.compile(r'^\s*UMask=([0-7]{3,4})\s*$')
MODE_DOC_ROW = re.compile(r'dir mode ([0-7]{3,4}), files ([0-7]{3,4})')

def _mode_places(script=SCRIPT, service=SERVICE, verify=VERIFY_SERVICE, doc=DOC):
    """The nine places of the mode rule, each with the pattern that reads its mode word.

    The index 0 names the directory mode, and the index 1 names the file mode.  A
    `umask` kind of line holds the umask itself, and a `directory` or a `file` kind
    of line holds that mode.
    """
    return (
        ("the script umask", script, UMASK, 0, 'umask'),
        ("the script check", script, MODE_CHECK, 0, 'directory'),
        ("the unit comment", service, MODE_COMMENT, 0, 'directory'),
        ("the unit umask", service, UMASK_DIRECTIVE, 0, 'umask'),
        ("the verify unit umask", verify, UMASK_DIRECTIVE, 0, 'umask'),
        ("the document directory mode", doc, MODE_DOC_ROW, 0, 'directory'),
        ("the document file mode", doc, MODE_DOC_ROW, 1, 'file'),
    )

def _capture(path, pattern):
    """(number, line number) of the first line of `path` that `pattern` captures, or None."""
    for number, line in enumerate(path.read_text().splitlines(), 1):
        found = re.search(pattern, line)
        if found:
            return int(found.group(1)), number
    return None


def _capture_mode(path, pattern, index=0):
    """((mode word, line number)) of the first line of `path` that `pattern` captures, or None."""
    for number, line in enumerate(path.read_text().splitlines(), 1):
        found = re.search(pattern, line)
        if found:
            return found.group(index + 1), number
    return None


def _umask_token(mode):
    """The one token of a umask word.  `077` and `0077` name one umask.

    The `umask` command of a shell and the `UMask=` directive of a unit spell one
    value, and the systemd spelling takes a leading zero.  This function reads the
    three rightmost digits, so the two spellings come to one token.
    """
    return mode[-3:].rjust(3, '0')


def _mode_token(mode):
    """The one token of a directory or file mode.  `700`, `0700` and `00700` name one mode.

    A leading zero of a mode removes no permission bit.  The leftmost digit of a
    mode is the execute bit of the owner, so this function keeps three digits and
    a leading zero of a longer spelling does not survive.
    """
    return f'{int(mode, 8):03o}'


def _derived_modes(umask):
    """The (directory mode, file mode) of one umask word.

    The umask removes permission bits, so the modes are the complement of the
    umask.  `077` gives the directory mode `700` and the file mode `600`, because
    a new directory starts at mode `777` and a new file starts at mode `666`.
    """
    octal = int(_umask_token(umask), 8)
    return f'{0o777 & ~octal:03o}', f'{0o666 & ~octal:03o}'


def _mode_problems(script=SCRIPT, service=SERVICE, verify=VERIFY_SERVICE, doc=DOC):
    """The derived (directory mode, file mode) and every place that does not hold them."""
    problems = []
    places = _mode_places(script, service, verify, doc)
    owner = _capture_mode(script, UMASK)
    if owner is None:
        return None, [f'{script}: no umask line matches, so the one owner of the mode '
                      f'rule is gone']
    umask, owner_line = owner
    directory, file_mode = _derived_modes(umask)

    for name, path, pattern, index, kind in places:
        found = _capture_mode(path, pattern, index)
        if found is None:
            problems.append(f'{path}: no line matches {pattern.pattern!r}, so {name} lost the '
                            f'mode word; the umask owner says directory {directory} and files '
                            f'{file_mode} (scripts/pool-postgres-backup.sh:{owner_line})')
            continue
        word, line = found
        # A `UMask=` line and a `stat -c %a` line spell one value in two ways.  The
        # `UMask=` line holds the umask, so the case derives the directory mode of
        # that line.  The `stat` line holds the directory mode itself.
        held = file_mode if kind == 'file' else directory
        measured = _derived_modes(word)[0] if kind == 'umask' else _mode_token(word)
        if measured != held:
            problems.append(
                f'{path}:{line}: {name} says {word}, and the umask {umask} of '
                f'{Path(script).name}:{owner_line} gives the directory mode {directory} and '
                f'the file mode {file_mode}; the umask of the script is the one owner of '
                f'the mode rule')
    return (directory, file_mode), problems


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


def _run_case(case_name, doc=None, timers=None, script=None, service=None, verify=None):
    """Run one case of this module against alternative paths, and return its failure texts.

    The case runs from this module, so it is the real case.  A Python function
    reads its module names through its own module object, so this helper plants
    the named paths in the module and restores them after the run.  The case must
    therefore read the paths through this module.
    """
    module = sys.modules[__name__]
    planted = {'DOC': doc or DOC, 'TIMERS': timers or TIMERS, 'SCRIPT': script or SCRIPT,
               'SERVICE': service or SERVICE, 'VERIFY_SERVICE': verify or VERIFY_SERVICE}
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

    def test_every_mode_word_matches_the_script_umask(self):
        """The umask of the script, the units and the document row hold one mode."""
        modes, problems = _mode_problems()
        self.assertIsNotNone(modes, f'{SCRIPT}: the case did not read the umask of the owner')
        self.assertIsNone(
            problems or None,
            f'the mode of the backup directory must stand in one place; the umask of '
            f'scripts/pool-postgres-backup.sh:11 gives the directory mode {modes[0]} and the '
            f'file mode {modes[1]}, and every other place must hold those two modes',
        )

    def test_a_planted_wrong_umask_names_the_file_and_the_line(self):
        """A planted wrong UMask in a copy of one unit fails the case with its file and line."""
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            self.assertIn(
                'UMask=0077', SERVICE.read_text(),
                f'{SERVICE}: the unit does not hold `UMask=0077`, so the case below cannot '
                f'plant a wrong word',
            )
            copy = tree / SERVICE.relative_to(ROOT)
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_text(SERVICE.read_text().replace('UMask=0077', 'UMask=0022', 1))

            _modes, problems = _mode_problems(service=copy)
            self.assertTrue(
                problems,
                f'{copy}: the planted UMask=0022 did not fail the case, so a moved mode word '
                f'can stand in silence',
            )
            self.assertIn(f'{copy}:19', problems[0])
            self.assertIn('0022', problems[0])
            self.assertIn('700', problems[0])
            self.assertIn('600', problems[0])

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
