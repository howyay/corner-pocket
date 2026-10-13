"""The environment names of the two postgres units and the backup script.

Two shipped units start one shipped script:

    deploy/systemd/pool-postgres-backup.service    ExecStart=.../pool-postgres-backup.sh dump
    deploy/systemd/pool-postgres-verify.service    ExecStart=.../pool-postgres-backup.sh verify

Each unit sets the environment names of the script with `Environment=` lines.  The script reads
those names from its own environment.  Nothing held the two sides together, so a rename on one
side was silent.  The name `POOL_BACKUP_DIR` shows the gap:

    deploy/systemd/pool-postgres-backup.service:16   Environment=POOL_BACKUP_DIR=@BACKUP_DIR@
    deploy/systemd/pool-postgres-verify.service:13   Environment=POOL_BACKUP_DIR=@BACKUP_DIR@
    scripts/pool-postgres-backup.sh:20   [ -n "${POOL_BACKUP_DIR:-}" ] || fail "POOL_BACKUP_DIR is not set"
    scripts/pool-postgres-backup.sh:21   DIR="$POOL_BACKUP_DIR"

The script refuses to run without the name.  No case in this suite named that name before this
module: `grep -rn 'POOL_BACKUP' tests/` answered four lines, and all four named the other
variable, `POOL_BACKUP_KEEP_DAYS` (tests/test_backup_retention.py:5, :6, :146, :147).  The one
`Environment=` harvest of the suite reads another file, the ffmpeg drop-in
(tests/test_unit_render.py:269-270, with FFMPEG_DROP_IN at tests/test_unit_render.py:39).

This module harvests both sides from the shipped files and holds them together:

1. `test_every_required_name_has_a_setter` reads every name the script cannot run without, and
   asks for a setter in a unit of this pair.
2. `test_every_setter_is_read` reads every name the units of this pair set, and asks for a read
   in the script.  The name `POOL_BACKUP_CONTAINER` is no violation of this case: no unit sets
   it, and the script holds its own default at scripts/pool-postgres-backup.sh:14.
3. `test_every_required_name_is_read` holds the two harvests of the script together.  A required
   name that the reader of that name does not report would hide case 1.
4. `test_the_pair_meets_the_measured_numbers` pins the numbers of one scan: the unit files, the
   `Environment=` lines, and the names of each side.  A renamed file or a removed line fails
   here, so no case above can pass in silence.
5. `test_the_upstream_lines_still_read_these_names` pins the text of the lines that those
   numbers cover.  A rename inside one line keeps the counts of case 4.
6. `test_the_read_lines_hold_their_measured_names_and_status` pins the line, the name, the
   operator, and the status of every read of an environment name.
7. `test_an_unset_name_is_reported_with_its_file_and_line` runs the two reports of this module
   against a small planted pair.  It shows that each report names its offender with the file and
   the line.

The script opens with `set -euo pipefail` (scripts/pool-postgres-backup.sh:10), so a plain
reference to an unset name stops the script.  This module therefore calls one reference
"required" in two cases: the reference carries `:?`, or the reference stands under the
`[ -n "${NAME:-}" ] || fail` guard.  A reference that carries `:-` and no guard is "defaulted",
because the script runs without the name.  Every other reference is "plain", and `set -u` stops
the script when the name is unset.

This module counts a read in two forms: the brace form `${NAME}` anywhere on a line, and the
plain form `$NAME` outside a string.  A word inside a string is not a read.  For that reason
the plain form at scripts/pool-postgres-backup.sh:21, `DIR="$POOL_BACKUP_DIR"`, is out of the
table of reads.  The guard at scripts/pool-postgres-backup.sh:20 carries the required read of
that name.

Do not assert anything here about the other units of `deploy/systemd/` or about the other
scripts of `scripts/`.

    ./scripts/pool-test.sh python test_backup_env_owner
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / 'deploy' / 'systemd'
SCRIPT = ROOT / 'scripts' / 'pool-postgres-backup.sh'

# The pair: the two shipped units that run the shipped script.  The scan reads these two files
# and this one script, and no other file of the repository.
UNITS = (
    SYSTEMD / 'pool-postgres-backup.service',
    SYSTEMD / 'pool-postgres-verify.service',
)

# One `Environment=` line of a unit.  A `NAME=value` form and a `"NAME=value"` form are both
# valid in a systemd unit, and a trailing comment is not part of the value.
ENVIRONMENT = re.compile(r'^Environment=(?:"(?P<quoted>[A-Za-z_][A-Za-z0-9_]*)=(?P<qvalue>[^"]*)"'
                         r'|(?P<plain>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^#\s]*))')
# One reference of the script to a name: `${NAME}`, `${NAME:-default}`, `${NAME:?message}`.
# The form `${NAME}` of the last alternative carries no operator.
REFERENCE = re.compile(r'\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?P<operator>:-|:\?|\})?')
# A plain reference: `$NAME`, without braces.  The negative lookahead keeps `$(command)` and
# `$((arithmetic))` out of the scan.
PLAIN_REFERENCE = re.compile(r'\$(?![({])(?P<name>[A-Za-z_][A-Za-z0-9_]*)')
# The outer span of one command substitution, `$(...)`.  The pair does not nest a `$(` inside
# another one, so the shortest span from `$(` to the first `)` holds every substitution.
SUBSTITUTION = re.compile(r'\$\((?!\$\()[^)]*\)')
# One string of the script, with the quotes of each side.
QUOTED = re.compile(r'"[^"]*"')
# The name on the left side of a shell assignment: `NAME=value` or `NAME="value"`.
ASSIGNMENT = re.compile(r'^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)=')
# The guard that stops the script when a name is unset:
#     [ -n "${POOL_BACKUP_DIR:-}" ] || fail "POOL_BACKUP_DIR is not set"
GUARD = re.compile(r'\[\s*-n\s+"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*):-\}"\s*\]\s*\|\|\s*fail')

# The status of one read, in the words of every report of this module.
STATUS_LABELS = {
    'required': 'a required read: the script stops without the name',
    'defaulted': 'a defaulted read: the script runs without the name',
    'plain': 'a plain read: `set -u` stops the script when the name is unset',
}

# The numbers and the names that the scan measured.  Each number is a frozen literal, so a
# renamed name or a removed line fails a case of this module.
EXPECTED_UNIT_FILES = 2
EXPECTED_SETTER_LINES = 5
EXPECTED_SCRIPT_READS = 17
EXPECTED_ENVIRONMENT_READS = 6
EXPECTED_UNIT_NAMES = ('PODMAN', 'POOL_BACKUP_DIR', 'POOL_BACKUP_KEEP_DAYS')
EXPECTED_SCRIPT_READ_NAMES = ('CONTAINER', 'DIR', 'PODMAN', 'POOL_BACKUP_CONTAINER',
                              'POOL_BACKUP_DIR', 'POOL_BACKUP_KEEP_DAYS', 'age_h', 'final',
                              'newest', 'tmp')
# `CONTAINER`, `DIR`, `age_h`, `final`, `newest` and `tmp` hold values inside the shell.  A unit
# of the pair does not set them, so the scan counts them apart from the environment names.
EXPECTED_SHELL_NAMES = ('CONTAINER', 'DIR', 'age_h', 'final', 'newest', 'tmp')

# The names that a unit of the pair sets and the script reads.
EXPECTED_ENVIRONMENT_NAMES = ('PODMAN', 'POOL_BACKUP_CONTAINER', 'POOL_BACKUP_DIR',
                              'POOL_BACKUP_KEEP_DAYS')

# Every read of such a name, at its own line.  The four names of the pair stand at these six
# sites.  A name inside a string is not a read of this scan, so the plain form of
# `POOL_BACKUP_DIR` at scripts/pool-postgres-backup.sh:21 is out of the list.
EXPECTED_SCRIPT_READ_LINES = (
    ('scripts/pool-postgres-backup.sh:13', 'POOL_BACKUP_KEEP_DAYS', ':-', 'defaulted'),
    ('scripts/pool-postgres-backup.sh:14', 'POOL_BACKUP_CONTAINER', ':-', 'defaulted'),
    ('scripts/pool-postgres-backup.sh:15', 'PODMAN', ':-', 'defaulted'),
    ('scripts/pool-postgres-backup.sh:20', 'POOL_BACKUP_DIR', ':-', 'required'),
    ('scripts/pool-postgres-backup.sh:36', 'PODMAN', '', 'plain'),
    ('scripts/pool-postgres-backup.sh:51', 'PODMAN', '', 'plain'),
)

# The text of those five lines, with their numbers.
EXPECTED_BACKUP_UPSTREAM = (
    ('scripts/pool-postgres-backup.sh:13', 'KEEP_DAYS="${POOL_BACKUP_KEEP_DAYS:-14}"'),
    ('scripts/pool-postgres-backup.sh:14', 'CONTAINER="${POOL_BACKUP_CONTAINER:-pool-postgres}"'),
    ('scripts/pool-postgres-backup.sh:15', 'PODMAN="${PODMAN:-podman}"'),
    ('scripts/pool-postgres-backup.sh:20',
     '[ -n "${POOL_BACKUP_DIR:-}" ] || fail "POOL_BACKUP_DIR is not set"'),
    ('scripts/pool-postgres-backup.sh:21', 'DIR="$POOL_BACKUP_DIR"'),
)

# The six `Environment=` lines of the two units of the pair, with their text.  The `PODMAN`
# and `POOL_BACKUP_DIR` setters stand in both units, so the same name has two setters.
EXPECTED_SETTERS = (
    ('deploy/systemd/pool-postgres-backup.service:15', 'Environment=PODMAN=@PODMAN@'),
    ('deploy/systemd/pool-postgres-backup.service:16', 'Environment=POOL_BACKUP_DIR=@BACKUP_DIR@'),
    ('deploy/systemd/pool-postgres-backup.service:17', 'Environment=POOL_BACKUP_KEEP_DAYS=14'),
    ('deploy/systemd/pool-postgres-verify.service:12', 'Environment=PODMAN=@PODMAN@'),
    ('deploy/systemd/pool-postgres-verify.service:13', 'Environment=POOL_BACKUP_DIR=@BACKUP_DIR@'),
)


def _read_rows(reads):
    """[(line number, name, operator, status)] of every reported read, in script order."""
    rows = []
    for name, found in reads.items():
        for read in found:
            rows.append((read['line'], name, read['operator'], read['status']))
    return sorted(rows)


class _PlantedFile:
    """A named text that the scan reads in the place of a shipped file.

    A case of this module plants one pair of short texts.  The texts stand in no file of the
    repository, so the class carries the text and the name that the report must state.
    """

    def __init__(self, name, text):
        self.name = name
        self.text = text
        self._lines = text.splitlines()


def _name(source):
    """The name of a file as this module reports it: with the repository root, or absolute.

    A file under the repository loses the root prefix.  A file outside the repository, for
    example a planted file of a case, keeps its absolute path.  A planted text carries its own
    name.
    """
    if isinstance(source, _PlantedFile):
        return source.name
    try:
        return str(Path(source).relative_to(ROOT))
    except ValueError:
        return str(source)


def _text(source):
    """The lines of one file, with their line numbers, as a list of (number, text) pairs."""
    if isinstance(source, _PlantedFile):
        return list(enumerate(source._lines, 1))
    return list(enumerate(Path(source).read_text(encoding='utf-8').splitlines(), 1))


def _harvest_setters(units=UNITS):
    """Every `Environment=` name of the units, as name -> list of (source, line, text, value).

    The list of one name holds one entry per unit line that sets that name, in file order.
    """
    setters = {}
    for source in units:
        for number, line in _text(source):
            found = ENVIRONMENT.match(line)
            if not found:
                continue
            name = found.group('quoted') or found.group('plain')
            value = found.group('qvalue') if found.group('quoted') else found.group('value')
            setters.setdefault(name, []).append((source, number, line.strip(), value))
    return setters


def _reference_status(operator, guarded):
    """The status of one reference: `required`, `defaulted`, or `plain`.

    A required reference stops the script in two ways.  The `[ -n "${NAME:-}" ] || fail` guard
    stops it when the name is empty.  The `:?` form stops it with a message.  A `:-` reference
    that carries no guard carries a default, so the script runs without the name.  A plain
    `$NAME` reference depends on `set -u` at scripts/pool-postgres-backup.sh:10.
    """
    if guarded or operator == ':?':
        return 'required'
    if operator == ':-':
        return 'defaulted'
    return 'plain'


def _blank_spans(line, spans):
    """The line with every character of each span replaced by a space.

    The replacement keeps the length of the line, so the numbers of the columns do not move.
    """
    text = list(line)
    for start, end in spans:
        for index in range(max(0, start), min(len(text), end)):
            text[index] = ' '
    return ''.join(text)


def _mask_strings(line):
    """The line with every string of the script replaced by spaces.

    A string of the script can hold a word that looks like an environment name, for example the
    message `"POOL_BACKUP_DIR is not set"`.  Such a word is not a read.  A string that stands
    inside a command substitution is left alone, because the scan reads a plain reference
    there.
    """
    substitutions = [found.span() for found in SUBSTITUTION.finditer(line)]

    def in_substitution(start, end):
        return any(start >= open_at and end <= close_at for open_at, close_at in substitutions)

    quotes = [found.span() for found in QUOTED.finditer(line)
              if not in_substitution(*found.span())]
    return _blank_spans(line, quotes)


def _is_environment_name(name, setters):
    """True when the name of a read holds a value that the environment can carry.

    The units set names such as `PODMAN` and `POOL_BACKUP_DIR`.  The script also holds names of
    its own, such as `DIR` and `age_h`, and a unit does not set those.  A name that no unit of
    the pair sets is an environment name in one of two cases: the name of the pair holds the
    prefix of the product, or the name is `PODMAN`.
    """
    return name in setters or name.startswith('POOL_') or name == 'PODMAN'


def _harvest_reads(script=SCRIPT, setters=None):
    """Every reference of the script to a name, as name -> list of reads.

    One read is a dict with the keys `source_name`, `line`, `text`, `operator`, `status`,
    `source`, and `environment`.  The key `environment` is true for a name that the environment
    can carry.  A read of an environment name names a value on which the run of the unit
    depends.  A read of a shell name, for example `DIR`, only carries a value inside the script.
    """
    if setters is None:
        setters = _harvest_setters()
    reads = {}
    for number, line in _text(script):
        guarded = {found.group('name') for found in GUARD.finditer(line)}
        references = [(found.group('name'), found.group('operator'))
                      for found in REFERENCE.finditer(line)]
        references += [(found.group('name'), '')
                       for found in PLAIN_REFERENCE.finditer(_mask_strings(line))]
        for name, operator in references:
            reads.setdefault(name, []).append({
                'source_name': _name(script),
                'line': number,
                'text': line.strip(),
                'operator': operator,
                'status': _reference_status(operator, name in guarded),
                'source': f'{_name(script)}:{number}',
                'environment': _is_environment_name(name, setters),
            })
    return reads


def _environment_reads(reads):
    """The reads of a name that the environment can carry."""
    return {name: found for name, found in reads.items()
            if any(read['environment'] for read in found)}


def _missing_setters(setters, reads):
    """One line per name the script needs and no unit of the pair sets."""
    problems = []
    for name, found in sorted(reads.items()):
        if any(read['status'] == 'required' for read in found) and name not in setters:
            first = found[0]
            problems.append(
                f"{first['source']}: {first['text']}  <- the script needs {name} and no unit "
                f"sets it")
    return problems


def _unread_setters(setters, reads):
    """One line per name a unit of the pair sets and the script never reads."""
    problems = []
    for name, found in sorted(setters.items()):
        if name in reads:
            continue
        for source, number, text, _value in found:
            problems.append(f'{_name(source)}:{number}: {text}  <- the unit sets {name} and the '
                            f'script never reads it')
    return problems


def _pair_report(units=UNITS, script=SCRIPT):
    """The numbers of one scan and every disagreement between the two sides.

    The answer has the keys `unit_files`, `setter_lines`, `unit_names`, `script_names`,
    `environment_names`, `shell_names`, `environment_reads`, and `problems`.  Every problem
    names the file, the line, and the text of the offender.
    """
    setters = _harvest_setters(units)
    reads = _harvest_reads(script, setters)
    environment = _environment_reads(reads)
    return {
        'unit_files': sorted({_name(source) for source in units}),
        'setter_lines': [(f'{_name(source)}:{number}', text)
                         for entries in setters.values()
                         for source, number, text, _value in entries],
        'unit_names': tuple(sorted(setters)),
        'script_names': tuple(sorted(reads)),
        'environment_names': tuple(sorted(environment)),
        'shell_names': tuple(sorted(set(reads) - set(environment))),
        'environment_reads': _read_rows(environment),
        'problems': _missing_setters(setters, reads) + _unread_setters(setters, reads),
    }


class BackupEnvOwnerTests(unittest.TestCase):
    """The units and the script must answer one set of environment names."""

    def test_every_required_name_has_a_setter(self):
        """Every name the script cannot run without has a setter in a unit of the pair."""
        problems = _missing_setters(_harvest_setters(), _harvest_reads())
        self.assertEqual(
            [], problems,
            'the script and the units must agree about every name the script needs:\n'
            + '\n'.join(problems))

    def test_every_setter_is_read(self):
        """Every name a unit of the pair sets is read by the script."""
        problems = _unread_setters(_harvest_setters(), _harvest_reads())
        self.assertEqual(
            [], problems,
            'a unit of the pair sets a name that the script never reads:\n'
            + '\n'.join(problems))

    def test_every_required_name_is_read(self):
        """The reader of the script names every name the script requires.

        This case holds the two harvests of the script together.  A required name that the
        reader does not report would hide case 1 above.
        """
        reads = _harvest_reads()
        required = {name for name, found in reads.items()
                    if any(read['status'] == 'required' for read in found)}
        self.assertEqual({'POOL_BACKUP_DIR'}, required,
                         'the script must read one required name, POOL_BACKUP_DIR, with the '
                         'guard at scripts/pool-postgres-backup.sh:20')
        for name in sorted(required):
            with self.subTest(name=name):
                self.assertIn(name, reads, f'the reader of the script does not report {name}')

    def test_the_pair_meets_the_measured_numbers(self):
        """The scan of the pair must hold the numbers that this module measured.

        The numbers mean this:

        * `unit_files` is the number of shipped unit files that the scan read.
        * `setter_lines` is the number of `Environment=` lines in those files.
        * `unit_names` is the list of names that those lines set.
        * `script_reads` is the number of references of the script to a name.
        * `script_names` is the list of those names.
        * `environment_reads` is the number of those references that name a value of the
          environment.  The script also reads names of its own, such as `DIR`.
        * `environment_names` and `shell_names` hold the two groups of names.
        """
        report = _pair_report()
        reads = _harvest_reads(SCRIPT, _harvest_setters())
        measured = {
            'unit_files': len(report['unit_files']),
            'setter_lines': len(report['setter_lines']),
            'unit_names': report['unit_names'],
            'script_reads': len(_read_rows(reads)),
            'script_names': report['script_names'],
            'environment_reads': len(report['environment_reads']),
            'environment_names': report['environment_names'],
            'shell_names': report['shell_names'],
        }
        expected = {
            'unit_files': EXPECTED_UNIT_FILES,
            'setter_lines': EXPECTED_SETTER_LINES,
            'unit_names': EXPECTED_UNIT_NAMES,
            'script_reads': EXPECTED_SCRIPT_READS,
            'script_names': EXPECTED_SCRIPT_READ_NAMES,
            'environment_reads': EXPECTED_ENVIRONMENT_READS,
            'environment_names': EXPECTED_ENVIRONMENT_NAMES,
            'shell_names': EXPECTED_SHELL_NAMES,
        }
        self.assertEqual(
            expected, measured,
            f'the pair changed shape: {measured} against the measured numbers {expected}.  '
            f'unit_files counts the shipped unit files of the pair.  setter_lines counts their '
            f'Environment= lines.  script_reads counts the references of the script to a name, '
            f'and environment_reads counts the references that name a value of the environment.  '
            f'unit_names, script_names, environment_names and shell_names hold the names of each '
            f'group.')

    def test_the_upstream_lines_still_read_these_names(self):
        """Each line of the script and of the units still stands at its measured number.

        The first case pins the two counts.  A rename inside one line keeps both counts, so this
        case pins the text of every line that the counts cover.
        """
        script_lines = dict(_text(SCRIPT))
        for where, text in EXPECTED_BACKUP_UPSTREAM:
            number = int(where.rsplit(':', 1)[1])
            self.assertEqual(
                text, script_lines.get(number),
                f'{where} answers {script_lines.get(number)!r}, and it must answer {text!r}; '
                f'the numbers of this module name the lines of the script')
        setters = {f'{_name(source)}:{number}': line.strip()
                   for entries in _harvest_setters().values()
                   for source, number, line, _value in entries}
        for where, text in EXPECTED_SETTERS:
            self.assertIn(
                where, setters,
                f'{where} is not an Environment= line of a unit of the pair, so the numbers of '
                f'this module no longer name the setters')
            self.assertEqual(
                text, setters[where],
                f'{where} answers {setters[where]!r}, and it must answer {text!r}')

    def test_the_read_lines_hold_their_measured_names_and_status(self):
        """The five lines of the script that read an environment name hold their names and status.

        A name can move to another line and keep every count of the first case.  This case reads
        the line of every reference to an environment name and the status of that reference.
        """
        rows = _pair_report()['environment_reads']
        expected = [(int(where.rsplit(':', 1)[1]), name, operator, status)
                    for where, name, operator, status in EXPECTED_SCRIPT_READ_LINES]
        self.assertEqual(
            expected, rows,
            f'the script reads {rows!r} at the lines of the pair, and it must read '
            f'{expected!r}; POOL_BACKUP_KEEP_DAYS, POOL_BACKUP_CONTAINER and PODMAN carry a '
            f'default, and POOL_BACKUP_DIR carries the guard at '
            f'scripts/pool-postgres-backup.sh:20 and the plain read at '
            f'scripts/pool-postgres-backup.sh:21')

    def test_an_unset_name_is_reported_with_its_file_and_line(self):
        """A planted pair reports its two offenders with the file and the line of each one.

        The planted texts stand in no file of this repository.  The two reports read the three
        names that this case gives them, and nothing else.
        """
        script_text = ('#!/usr/bin/env bash\n'
                       'set -euo pipefail\n'
                       '[ -n "${POOL_BACKUP_DIR:-}" ] || fail "POOL_BACKUP_DIR is not set"\n')
        unit_text = ('[Service]\n'
                     'Environment=POOL_BACKUP_ORPHAN=1\n')
        planted_script = _PlantedFile('planted_script.sh', script_text)
        planted_unit = _PlantedFile('planted_unit.service', unit_text)

        reads = _harvest_reads(script=planted_script, setters={})
        self.assertIn('POOL_BACKUP_DIR', reads,
                      'the reader of the script does not find the planted required read')
        self.assertEqual('required', reads['POOL_BACKUP_DIR'][0]['status'],
                         'the reader does not call the planted guard a required read')
        setters = _harvest_setters(units=[planted_unit])
        self.assertIn('POOL_BACKUP_ORPHAN', setters,
                      'the reader of the units does not find the planted setter')

        missing = _missing_setters(setters, reads)
        unread = _unread_setters(setters, reads)
        self.assertEqual(1, len(missing),
                         'the planted pair must report one name without a setter:\n'
                         + '\n'.join(missing))
        self.assertIn('planted_script.sh:3', missing[0])
        self.assertIn('the script needs POOL_BACKUP_DIR and no unit sets it', missing[0])
        self.assertIn('[ -n "${POOL_BACKUP_DIR:-}" ] || fail "POOL_BACKUP_DIR is not set"',
                      missing[0])
        self.assertEqual(1, len(unread),
                         'the planted pair must report one setter without a read:\n'
                         + '\n'.join(unread))
        self.assertIn('planted_unit.service:2', unread[0])
        self.assertIn('Environment=POOL_BACKUP_ORPHAN=1', unread[0])
        self.assertIn('the unit sets POOL_BACKUP_ORPHAN and the script never reads it', unread[0])
        self.assertNotIn(str(ROOT), missing[0],
                         'the report of a planted file names the repository root')
        self.assertEqual(
            [], _missing_setters({}, {}),
            'the report of an empty pair must hold no problem')


if __name__ == '__main__':
    unittest.main()
