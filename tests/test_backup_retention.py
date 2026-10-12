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
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pool-postgres-backup.sh"
SERVICE = ROOT / "deploy" / "systemd" / "pool-postgres-backup.service"
DOC = ROOT / "docs" / "postgres.md"
VERIFY_SERVICE = ROOT / "deploy" / "systemd" / "pool-postgres-verify.service"

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


if __name__ == '__main__':
    unittest.main()
