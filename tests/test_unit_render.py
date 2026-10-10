"""Tests for scripts/pool-render-units.sh, the one renderer of the unit files.

The files under deploy/systemd/ are the source of truth for the user units of
this project.  Two of them are templates and hold @REPO_DIR@, @BACKUP_DIR@ and
@PODMAN@ placeholders.  scripts/pool-render-units.sh replaces those three names
and copies every other file without a change.

This module renders into a temporary directory only.  It never writes the live
user unit directory of this machine.  The refusal of that directory is tested
with a temporary HOME and a temporary XDG_CONFIG_HOME.

The tests here hold four contracts:

1. A full render writes every file, exits 0, and leaves no placeholder.
2. A file that holds no placeholder is copied byte for byte (cmp).
3. A refusal names the cause: an unknown placeholder with its file and line, a
   missing value with its flag.
4. The port in the public board drop-in equals the port default that
   annotator/unified_server.py holds, so a moved default is visible here.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'pool-render-units.sh'
SYSTEMD = ROOT / 'deploy' / 'systemd'
SERVER = ROOT / 'annotator' / 'unified_server.py'
PUBLIC_BOARD = SYSTEMD / 'pool-workbench.service.d' / '40-public-board.conf'

# The three names the renderer supports.  The test reads the same three names
# from the script and compares both sets with the names in the tree.
EXPECTED_PLACEHOLDERS = {'REPO_DIR', 'BACKUP_DIR', 'PODMAN'}

PLACEHOLDER = re.compile(r'@[A-Za-z_][A-Za-z0-9_]*@')
INVENTORY = re.compile(r'@[A-Z_]*@')
SUPPORTED_LINE = re.compile(r'^SUPPORTED_PLACEHOLDERS=\(([^)]*)\)$', re.MULTILINE)

REPO_DIR = '/tmp/pool-test-repo'
BACKUP_DIR = '/tmp/pool-test-backup'
PODMAN = '/run/current-system/sw/bin/podman'

# The five files that hold no placeholder.  A render must copy each one byte for
# byte: the two timers and the three drop-ins.
FILES_WITHOUT_PLACEHOLDER = (
    'pool-postgres-backup.timer',
    'pool-postgres-verify.timer',
    'pool-workbench.service.d/20-postgres.conf',
    'pool-workbench.service.d/30-ffmpeg.conf',
    'pool-workbench.service.d/40-public-board.conf',
)


def run_render(*args, env=None):
    """Run the renderer and return the completed process with text output."""
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def full_args(to_dir):
    """The four arguments of a render that must succeed."""
    return [
        '--to', str(to_dir),
        '--repo-dir', REPO_DIR,
        '--backup-dir', BACKUP_DIR,
        '--podman', PODMAN,
    ]


def relative_files(directory):
    """Every file below directory, as a POSIX path relative to directory."""
    return sorted(
        path.relative_to(directory).as_posix()
        for path in Path(directory).rglob('*')
        if path.is_file()
    )


def count_placeholders(path):
    """The number of @NAME@ occurrences in one file."""
    return len(PLACEHOLDER.findall(Path(path).read_text(encoding='utf-8')))


class UnitRenderTest(unittest.TestCase):
    """The renderer, its refusals, and the port contract."""

    def temporary_directory(self):
        path = Path(tempfile.mkdtemp(prefix='pool-unit-render-'))
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def test_render_writes_every_file_with_no_placeholder(self):
        """One render covers every source file, exits 0, and leaves no name."""
        target = self.temporary_directory() / 'rendered'
        done = run_render(*full_args(target))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(relative_files(SYSTEMD), relative_files(target))
        for name in relative_files(target):
            self.assertEqual(
                0, count_placeholders(target / name),
                f'{name} still holds a placeholder after the render',
            )
            self.assertIn(f'rendered {name} placeholders=0', done.stdout)

    def test_render_copies_the_files_without_a_placeholder_byte_for_byte(self):
        """The two timers and the three drop-ins are byte-identical copies."""
        target = self.temporary_directory() / 'rendered'
        done = run_render(*full_args(target))
        self.assertEqual(0, done.returncode, done.stderr)

        for name in FILES_WITHOUT_PLACEHOLDER:
            source_bytes = (SYSTEMD / name).read_bytes()
            self.assertEqual(0, len(PLACEHOLDER.findall(source_bytes.decode('utf-8'))))
            self.assertEqual(
                source_bytes, (target / name).read_bytes(),
                f'{name} is not a byte-identical copy of its source',
            )

    def test_unknown_placeholder_refuses_and_names_the_file_and_the_line(self):
        """An unknown name stops the render and the message cites file and line."""
        scratch = self.temporary_directory() / 'repo'
        (scratch / 'scripts').mkdir(parents=True)
        shutil.copy2(SCRIPT, scratch / 'scripts' / SCRIPT.name)
        shutil.copytree(SYSTEMD, scratch / 'deploy' / 'systemd')

        unit = scratch / 'deploy' / 'systemd' / 'pool-postgres-verify.service'
        lines = unit.read_text(encoding='utf-8').splitlines(keepends=True)
        lines.insert(2, '# injected by the test: @NOT_A_PLACEHOLDER@\n')
        unit.write_text(''.join(lines), encoding='utf-8')
        injected_line = 3

        target = scratch / 'out'
        done = subprocess.run(
            [
                str(scratch / 'scripts' / SCRIPT.name),
                '--to', str(target),
                '--repo-dir', REPO_DIR,
                '--backup-dir', BACKUP_DIR,
                '--podman', PODMAN,
            ],
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(0, done.returncode, done.stdout)
        self.assertIn(
            f'pool-postgres-verify.service:{injected_line}: '
            'unknown placeholder @NOT_A_PLACEHOLDER@',
            done.stderr,
        )
        self.assertFalse(
            target.exists(),
            'the renderer wrote the target before it refused the unknown name',
        )

    def test_missing_backup_dir_refuses_and_names_the_flag(self):
        """A missing --backup-dir stops the render and the message names it."""
        target = self.temporary_directory() / 'rendered'
        done = run_render(
            '--to', str(target),
            '--repo-dir', REPO_DIR,
            '--podman', PODMAN,
        )

        self.assertNotEqual(0, done.returncode, done.stdout)
        self.assertIn('@BACKUP_DIR@', done.stderr)
        self.assertIn('--backup-dir', done.stderr)
        self.assertFalse(target.exists())

    def test_missing_environment_value_refuses_and_names_the_placeholder(self):
        """A value from no flag and no environment stops the render."""
        target = self.temporary_directory() / 'rendered'
        env = {
            'PATH': '/run/current-system/sw/bin:/usr/bin:/bin',
            'HOME': str(self.temporary_directory()),
            'REPO_DIR': REPO_DIR,
            'BACKUP_DIR': BACKUP_DIR,
        }
        done = run_render('--to', str(target), env=env)

        self.assertNotEqual(0, done.returncode, done.stdout)
        self.assertIn('@PODMAN@', done.stderr)
        self.assertIn('--podman', done.stderr)

    def test_missing_to_flag_prints_the_usage_and_exits_2(self):
        """The renderer needs a target directory and says so."""
        done = run_render('--repo-dir', REPO_DIR,
                          '--backup-dir', BACKUP_DIR, '--podman', PODMAN)

        self.assertEqual(2, done.returncode, done.stdout)
        self.assertIn('usage: pool-render-units.sh --to DIR', done.stderr)
        self.assertIn('--to', done.stderr)

    def test_live_user_unit_directory_is_refused(self):
        """A target that is the live user unit directory of this machine stops."""
        home = self.temporary_directory() / 'home'
        live = home / '.config' / 'systemd' / 'user'
        live.mkdir(parents=True)
        env = {
            'PATH': '/run/current-system/sw/bin:/usr/bin:/bin',
            'HOME': str(home),
            'XDG_CONFIG_HOME': str(home / '.config'),
        }
        done = run_render('--to', str(live), '--repo-dir', REPO_DIR,
                          '--backup-dir', BACKUP_DIR, '--podman', PODMAN, env=env)

        self.assertNotEqual(0, done.returncode, done.stdout)
        self.assertIn('live user unit directory', done.stderr)
        self.assertEqual([], relative_files(live))

    def test_a_placeholder_in_a_value_keeps_the_exit_code_non_zero(self):
        """A value that holds a name leaves that name in the rendered file."""
        target = self.temporary_directory() / 'rendered'
        done = run_render(
            '--to', str(target),
            '--repo-dir', '@WEIRD@',
            '--backup-dir', BACKUP_DIR,
            '--podman', PODMAN,
        )

        self.assertNotEqual(0, done.returncode, done.stdout)
        self.assertIn('placeholder(s) remain after rendering', done.stderr)

    def test_public_board_port_equals_the_server_default(self):
        """The drop-in port and the --port default of the server are one value."""
        unit_line = None
        for line in PUBLIC_BOARD.read_text(encoding='utf-8').splitlines():
            if line.startswith('ExecStart=') and '--port' in line:
                unit_line = line
        self.assertIsNotNone(unit_line, f'{PUBLIC_BOARD} holds no ExecStart with --port')

        unit_match = re.search(r'--port\s+(\d+)', unit_line)
        self.assertIsNotNone(unit_match, f'no numeric --port value in: {unit_line}')

        owner_line = None
        for line in SERVER.read_text(encoding='utf-8').splitlines():
            if 'add_argument("--port"' in line:
                owner_line = line
        self.assertIsNotNone(owner_line, f'{SERVER} holds no --port argument')

        owner_match = re.search(r'default=(\d+)', owner_line)
        self.assertIsNotNone(owner_match, f'no default value in: {owner_line}')

        self.assertEqual(
            owner_match.group(1), unit_match.group(1),
            f'the --port value in {PUBLIC_BOARD.name} differs from the default '
            f'in {SERVER.relative_to(ROOT)}',
        )

    def test_placeholder_names_match_the_script_supported_names(self):
        """The names in the tree and the names in the script are the same three."""
        found = set()
        for path in SYSTEMD.rglob('*'):
            if path.is_file():
                found.update(INVENTORY.findall(path.read_text(encoding='utf-8')))
        names = {name.strip('@') for name in found}

        text = SCRIPT.read_text(encoding='utf-8')
        match = SUPPORTED_LINE.search(text)
        self.assertIsNotNone(match, f'{SCRIPT.name} holds no SUPPORTED_PLACEHOLDERS list')
        supported = set(match.group(1).split())

        self.assertEqual(EXPECTED_PLACEHOLDERS, supported,
                         f'{SCRIPT.name} supports {sorted(supported)}')
        self.assertEqual(
            supported, names,
            f'deploy/systemd/ holds {sorted(names)}, the script supports '
            f'{sorted(supported)}',
        )


if __name__ == '__main__':
    unittest.main()
