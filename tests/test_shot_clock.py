"""The shared shot clock module on its own: intents, idempotence, seq, expiry
without writes, persistence across instances and duration validation. Every
clock lives in a temporary directory; nothing under the repository's out/ is
touched.

The last four cases pin the reconnect delay and the shape of the answer:
annotator/shot_clock.py owns the number as RETRY_MS, the stream preamble carries
it, the snapshot publishes it as retry_ms, a command answers the same shape a
read does, and the client keeps a first-connection default that one case reads
out of the client file to prove the default still equals the owner.

The class below holds the duration rule at its one owner too: the bounds 5 and
300 and the default 30 live in annotator/shot_clock.py, the settings guard of
annotator/operations.py reads them from there, and no shipped module types them
a second time.
"""
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from annotator import shot_clock
from annotator.operations import Operations
from annotator.shot_clock import ShotClock, epoch_ms

#: The shipped packages and the scanner over them have one home, tests/_shipped.py.
#: The single-module runner starts in tests/, and discovery puts tests/ on sys.path,
#: so the bare module name reaches the helper in both.
from _shipped import shipped_modules

#: The repository root, from this file's own path. The binding case reads the
#: client file from here.
ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / 'annotator' / 'clock-sync.js'


def file_stamp(path):
    """Bytes + size + mtime: the three things a read must never change."""
    path = Path(path)
    return (hashlib.md5(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns)


def preamble_from_stream(clock, heartbeat_s=0.05):
    """The `retry:` line serve_events writes, plus the rest of the bytes it wrote.

    `serve_events` runs until the clock closes or the client goes away, and a
    paused clock never wakes it, so this helper closes the clock and the stream
    stops at the next heartbeat. The preamble is the first write either way.
    """
    stream = io.BytesIO()
    serving = threading.Thread(target=clock.serve_events, args=(clock.snapshot, stream, heartbeat_s),
                               daemon=True)
    serving.start()
    clock.close()
    serving.join(5)
    assert not serving.is_alive(), 'close() releases the stream the test started'
    return stream.getvalue().split(b'\n\n', 1)[0]


#: The one owner of the duration rule: the bounds, the default and the docstring live here.
OWNER = ROOT / 'annotator' / 'shot_clock.py'
#: The reader that must take the rule from the owner. Its settings guard wrote `5, 300`
#: and its document default wrote `30` until round 48.
READER = ROOT / 'annotator' / 'operations.py'


def own_nodes(node):
    """Every node of `node` that no nested statement holds.

    The walk stops at a nested statement, because that statement is read on its own
    turn. So one literal is never counted for two statements."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.stmt):
            continue
        yield child
        yield from own_nodes(child)


def names_the_clock(statement):
    """True when `statement` itself names the shot clock."""
    for child in own_nodes(statement):
        if isinstance(child, ast.keyword) and child.arg == 'shotClock':
            return True
        if isinstance(child, ast.Attribute) and child.attr == 'shotClock':
            return True
        if isinstance(child, ast.Name) and child.id == 'shotClock':
            return True
        if (isinstance(child, ast.Constant) and isinstance(child.value, str)
                and child.value == 'shotClock'):
            return True
    return False


def typed_clock_numbers(path):
    """(line number, whole numbers) for every statement of `path` that names the clock.

    A whole number inside such a statement IS the duration rule when the statement is
    the settings guard or the document default. A statement that reads the owner holds
    no such number: it holds the name."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8', errors='replace'))):
        if isinstance(node, ast.stmt) and names_the_clock(node):
            numbers = sorted({child.value for child in own_nodes(node)
                              if isinstance(child, ast.Constant) and type(child.value) is int})
            found.append((node.lineno, numbers))
    return found


class ShotClockTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'corner-pocket' / 'clock.json'

    def persisted(self):
        return json.loads(self.path.read_text())

    def test_first_read_uses_the_settings_duration_and_writes_nothing(self):
        clock = ShotClock(self.path, default_duration=45)
        state = clock.snapshot(now_ms=1_000)
        self.assertEqual(state, dict(duration=45, running=False, deadline_ms=None, remaining_ms=45_000,
                                     seq=0, updated_at=None, expired=False, retry_ms=shot_clock.RETRY_MS))
        self.assertFalse(self.path.exists(), 'a read never creates the file')
        self.assertFalse(self.path.parent.exists())
        # A callable default is read at use time (settings.shotClock can change);
        # anything outside 5-300 s falls back to 30 rather than inventing a clock.
        setting = {'value': 60}
        clock = ShotClock(self.path, default_duration=lambda: setting['value'])
        self.assertEqual(clock.snapshot(now_ms=0)['duration'], 60)
        for bad in (4, 301, True, '45', None, 45.0):
            setting['value'] = bad
            self.assertEqual(clock.snapshot(now_ms=0)['duration'], 30, bad)
        self.assertFalse(self.path.exists())

    def test_explicit_intents_and_idempotence(self):
        clock = ShotClock(self.path, default_duration=30)
        started = clock.apply('start', now_ms=1_000)
        self.assertEqual((started['running'], started['deadline_ms'], started['remaining_ms'], started['seq']),
                         (True, 31_000, None, 1))
        self.assertEqual(self.persisted()['deadline_ms'], 31_000)
        stamp = file_stamp(self.path)
        # Two people pressing Start at once: the second press changes nothing.
        again = clock.apply('start', now_ms=2_000)
        self.assertEqual((again['deadline_ms'], again['seq']), (31_000, 1))
        self.assertEqual(file_stamp(self.path), stamp, 'a no-op start is not written')
        paused = clock.apply('pause', now_ms=11_000)
        self.assertEqual((paused['running'], paused['deadline_ms'], paused['remaining_ms'], paused['seq']),
                         (False, None, 20_000, 2))
        stamp = file_stamp(self.path)
        self.assertEqual(clock.apply('pause', now_ms=12_000)['seq'], 2, 'pause while paused is a no-op')
        self.assertEqual(file_stamp(self.path), stamp)
        resumed = clock.apply('start', now_ms=15_000)
        self.assertEqual((resumed['deadline_ms'], resumed['seq']), (35_000, 3), 'start resumes from what was left')
        reset = clock.apply('reset', now_ms=16_000)
        self.assertEqual((reset['running'], reset['remaining_ms'], reset['duration'], reset['seq']),
                         (False, 30_000, 30, 4))
        stamp = file_stamp(self.path)
        self.assertEqual(clock.apply('reset', now_ms=17_000)['seq'], 4, 'a reset clock is not reset again')
        self.assertEqual(file_stamp(self.path), stamp)
        clock.apply('start', now_ms=18_000)
        changed = clock.apply('set', duration=45, now_ms=19_000)
        self.assertEqual((changed['running'], changed['duration'], changed['remaining_ms'], changed['seq']),
                         (False, 45, 45_000, 6), 'set stops the clock at the new full duration')
        self.assertEqual(clock.apply('set', duration=45, now_ms=20_000)['seq'], 6, 'the same set twice is one change')
        self.assertEqual(clock.apply('set', duration=20, now_ms=21_000)['remaining_ms'], 20_000)
        self.assertEqual(self.persisted(), dict(duration=20, running=False, deadline_ms=None, remaining_ms=20_000,
                                                seq=7, updated_at=self.persisted()['updated_at']))
        self.assertTrue(self.persisted()['updated_at'].startswith('1970-01-01T00:00:21'))

    def test_seq_increases_with_every_real_change_only(self):
        clock = ShotClock(self.path)
        seen = []
        steps = [('start', None), ('start', None), ('pause', None), ('pause', None), ('reset', None),
                 ('reset', None), ('set', 60), ('set', 60), ('start', None), ('set', 20), ('start', None)]
        for i, (action, duration) in enumerate(steps):
            seen.append(clock.apply(action, duration=duration, now_ms=1_000 * (i + 1))['seq'])
        self.assertEqual(seen, [1, 1, 2, 2, 3, 3, 4, 4, 5, 6, 7])
        self.assertTrue(all(b >= a for a, b in zip(seen, seen[1:])))
        self.assertEqual(self.persisted()['seq'], 7)
        self.assertEqual(ShotClock(self.path).seq, 7)

    def test_expiry_is_computed_on_read_and_never_written(self):
        clock = ShotClock(self.path, default_duration=5)
        clock.apply('start', now_ms=10_000)
        stamp = file_stamp(self.path)
        self.assertEqual(clock.snapshot(now_ms=14_999)['running'], True)
        expired = clock.snapshot(now_ms=15_000)
        self.assertEqual((expired['running'], expired['remaining_ms'], expired['expired'], expired['seq']),
                         (False, 0, True, 1))
        for now in range(15_000, 200_000, 997):
            self.assertEqual(clock.snapshot(now_ms=now)['remaining_ms'], 0)
        self.assertEqual(file_stamp(self.path), stamp, 'many reads after expiry leave md5, size and mtime alone')
        self.assertEqual(self.persisted()['running'], True, 'the file still holds the absolute deadline')
        # A pause after expiry changes nothing; a start runs a fresh full shot.
        self.assertEqual(clock.apply('pause', now_ms=20_000)['seq'], 1)
        self.assertEqual(file_stamp(self.path), stamp)
        restarted = clock.apply('start', now_ms=20_000)
        self.assertEqual((restarted['deadline_ms'], restarted['seq']), (25_000, 2))
        clock.apply('pause', now_ms=21_000)
        clock.apply('start', now_ms=22_000)
        # A reset of an expired clock is a real change: it is no longer expired.
        self.assertEqual(clock.apply('reset', now_ms=40_000)['seq'], 5)
        self.assertEqual(clock.snapshot(now_ms=41_000)['remaining_ms'], 5_000)

    def test_a_fresh_instance_keeps_a_running_clock_by_its_absolute_deadline(self):
        now = epoch_ms()
        first = ShotClock(self.path, default_duration=60).apply('start', now_ms=now)
        restarted = ShotClock(self.path, default_duration=20)  # settings changed meanwhile
        later = restarted.snapshot(now_ms=now + 12_345)
        self.assertEqual((later['running'], later['deadline_ms'], later['duration'], later['seq']),
                         (True, first['deadline_ms'], 60, 1), 'the persisted clock wins over the default')
        self.assertEqual(later['deadline_ms'] - (now + 12_345), 47_655)
        paused = restarted.apply('pause', now_ms=now + 20_000)
        self.assertEqual(ShotClock(self.path).snapshot(now_ms=now + 99_000)['remaining_ms'], paused['remaining_ms'])
        # A paused clock does not run down while the server is away.
        self.assertEqual(paused['remaining_ms'], 40_000)

    def test_invalid_intents_and_durations_are_refused_and_nothing_is_written(self):
        clock = ShotClock(self.path)
        for bad in (4, 301, 0, -30, 30.0, 30.5, '30', True, False, None, [30]):
            with self.subTest(duration=bad), self.assertRaises(ValueError):
                clock.apply('set', duration=bad, now_ms=1_000)
        for action in ('toggle', 'START', '', None, 'stop'):
            with self.subTest(action=action), self.assertRaises(ValueError):
                clock.apply(action, now_ms=1_000)
        with self.assertRaises(ValueError):
            clock.apply('start', duration=30, now_ms=1_000)
        self.assertFalse(self.path.exists(), 'a refused request never creates the file')
        clock.apply('set', duration=5, now_ms=1_000)
        clock.apply('set', duration=300, now_ms=2_000)
        stamp = file_stamp(self.path)
        for bad in (4, 301, '45'):
            with self.assertRaises(ValueError):
                clock.apply('set', duration=bad, now_ms=3_000)
        self.assertEqual(file_stamp(self.path), stamp)
        self.assertEqual(clock.snapshot(now_ms=3_000)['duration'], 300)

    def test_a_failed_write_changes_nothing(self):
        clock = ShotClock(self.path)
        clock.apply('start', now_ms=1_000)
        stamp, before = file_stamp(self.path), clock.snapshot(now_ms=2_000)
        with patch('src.atomic_write.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                clock.apply('pause', now_ms=2_000)
        self.assertEqual(file_stamp(self.path), stamp)
        self.assertEqual(clock.snapshot(now_ms=2_000), before, 'memory follows the file, not the attempt')
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ['clock.json'], 'no temp file left')

    def test_a_backwards_server_clock_never_banks_extra_time(self):
        clock = ShotClock(self.path)
        clock.apply('start', now_ms=100_000)
        self.assertEqual(clock.apply('pause', now_ms=90_000)['remaining_ms'], 30_000)

    def test_a_damaged_file_is_refused_not_silently_reset(self):
        cases = ['[]', '{"duration": 3, "running": false, "remaining_ms": 3000, "seq": 1}',
                 '{"duration": 30, "running": true, "deadline_ms": null, "seq": 1}',
                 '{"duration": 30, "running": false, "remaining_ms": 31000, "seq": 1}',
                 '{"duration": 30, "running": "yes", "remaining_ms": 1000, "seq": 1}',
                 '{"duration": 30, "running": false, "remaining_ms": 1000, "seq": -1}', 'not json']
        self.path.parent.mkdir(parents=True)
        for raw in cases:
            self.path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                ShotClock(self.path)

    def test_waiters_wake_on_a_change_and_not_on_a_no_op(self):
        clock = ShotClock(self.path)
        woke = []
        waiter = threading.Thread(target=lambda: woke.append(clock.wait(0, timeout=5)))
        waiter.start()
        time.sleep(0.05)
        clock.apply('start')
        waiter.join(2)
        # The waiter times itself out at 5 s and this join gives it 2 s, so a recorded
        # True can only come from apply() releasing the waiter; a wake that did not work
        # leaves woke empty.  That outcome is the mechanism, and the thread being gone
        # says it left the wait rather than merely being recorded by it.  A clock bound
        # on the same wake would grade the machine and adds nothing to either.
        self.assertEqual(woke, [True])
        self.assertFalse(waiter.is_alive())
        clock.apply('start')  # no-op: nobody is told anything changed
        self.assertFalse(clock.wait(clock.seq, timeout=0.2))
        waiter = threading.Thread(target=lambda: woke.append(clock.wait(clock.seq, timeout=5)))
        waiter.start()
        time.sleep(0.05)
        clock.close()
        waiter.join(2)
        self.assertEqual(woke, [True, True], 'close() releases a waiting stream')
        self.assertFalse(waiter.is_alive())

    def test_the_stream_preamble_carries_the_retry_constant(self):
        clock = ShotClock(self.path)
        self.assertEqual(preamble_from_stream(clock),
                         b'retry: ' + str(shot_clock.RETRY_MS).encode(),
                         'the SSE preamble carries the constant, not a second literal')

    def test_the_snapshot_publishes_the_retry_constant(self):
        # The value follows the constant, so a second literal cannot hide here. The
        # snapshot method is the one the clock route calls.
        clock = ShotClock(self.path)
        self.assertEqual(clock.snapshot(now_ms=1_000)['retry_ms'], shot_clock.RETRY_MS)
        with patch.object(shot_clock, 'RETRY_MS', 4321):
            self.assertEqual(clock.snapshot(now_ms=1_000)['retry_ms'], 4321)
            self.assertEqual(preamble_from_stream(ShotClock(self.path), 0.01), b'retry: 4321',
                             'the same patched constant reaches the preamble')

    def test_a_command_answers_the_same_shape_a_read_does(self):
        # The clock route answers POST /api/clock from `apply` and GET /api/clock
        # from `snapshot`, and tests/test_clock_api.py compares the two answers
        # key by key. So both methods report the published delay, and the file on
        # disk holds clock state alone.
        clock = ShotClock(self.path, default_duration=30)
        changed = clock.apply('start', now_ms=1_000)
        noop = clock.apply('start', now_ms=2_000)
        read = clock.snapshot(now_ms=3_000)
        self.assertIn(shot_clock.RETRY_KEY, changed, 'a changed command reports the delay')
        self.assertIn(shot_clock.RETRY_KEY, noop, 'a no-op command reports it too')
        self.assertEqual(changed[shot_clock.RETRY_KEY], read[shot_clock.RETRY_KEY])
        self.assertNotIn(shot_clock.RETRY_KEY, self.persisted(),
                         'the published delay never reaches the clock file')
        self.assertEqual(set(changed) - {shot_clock.RETRY_KEY}, set(read) - {shot_clock.RETRY_KEY},
                         'a command and a read describe the same clock, key for key')

    def test_the_client_default_still_equals_the_server_constant(self):
        # The two files cannot drift in silence: the client's named default is read as
        # text and compared with the constant that governs the server.
        source = CLIENT.read_text()
        found = re.findall(r'const\s+RECONNECT_MS\s*=\s*(\d+)\s*;', source)
        self.assertEqual(len(found), 1, 'the client holds one named RECONNECT_MS default')
        self.assertEqual(int(found[0]), shot_clock.RETRY_MS,
                         'the client default and shot_clock.RETRY_MS are the same number')
        self.assertIn('payload.retry_ms', source,
                      'the client reads the key the snapshot publishes')

    def test_the_client_timeout_still_counts_two_server_heartbeats(self):
        # The live/offline judgement of the client is not a free number. The comment
        # beside the constant states the rule, and shot_clock.HEARTBEAT_S governs the
        # cadence of the stream. Two missed heartbeats is the rule, so a change of the
        # cadence must move the client timeout with it.
        source = CLIENT.read_text()
        found = re.findall(r'const\s+HEARTBEAT_TIMEOUT_MS\s*=\s*(\d+)\s*;', source)
        self.assertEqual(len(found), 1, 'the client holds one named HEARTBEAT_TIMEOUT_MS')
        self.assertEqual(2 * shot_clock.HEARTBEAT_S * 1000, int(found[0]),
                         'the client calls the stream dead after two missed heartbeats of '
                         'shot_clock.HEARTBEAT_S')
        self.assertIn('HEARTBEAT_S', source,
                      'the constant names the owner of the cadence it counts')


class ShotClockRuleOwnerTests(unittest.TestCase):
    """The duration rule - an integer from 5 to 300 seconds - has one owner.

    The round-48 walk found the numbers typed twice: the settings guard of
    annotator/operations.py wrote `5, 300, 'shotClock'` and its document default wrote
    `shotClock=30`. An equal copy is correct today and silent tomorrow: the owner can
    move a bound and the copy stays old. These cases hold the reader at the owner's
    names, and they prove that the guard accepts the owner's minimum and refuses one
    second below it.
    """

    def test_no_shipped_module_types_the_clock_rule_again(self):
        owner = {shot_clock.MIN_DURATION, shot_clock.MAX_DURATION, shot_clock.DEFAULT_DURATION}
        offenders = [f'{path.relative_to(ROOT).as_posix()}:{line} types {sorted(set(numbers) & owner)}'
                     for path in shipped_modules() if path != OWNER
                     for line, numbers in typed_clock_numbers(path)
                     if set(numbers) & owner]
        self.assertEqual(offenders, [],
                         'the duration rule has one owner, annotator/shot_clock.py: import '
                         'MIN_DURATION, MAX_DURATION and DEFAULT_DURATION from it; offenders: '
                         + '; '.join(offenders))

    def test_the_scan_reads_a_typed_copy(self):
        """The scan must catch the two lines this change removed."""
        with tempfile.TemporaryDirectory() as folder:
            typed = Path(folder) / 'typed.py'
            typed.write_text('def load():\n'
                             '    return dict(shotClock=30, autoFrame=False)\n'
                             '\n'
                             'def settings_update(s, p):\n'
                             "    s['settings']['shotClock'] = integer(p['shotClock'], 5, 300, 'shotClock')\n",
                             encoding='utf-8')
            self.assertEqual(typed_clock_numbers(typed), [(2, [30]), (5, [5, 300])],
                             'the scan must read a typed copy of the bounds and of the default')

    def test_the_settings_module_imports_the_rule_from_the_owner(self):
        imported = {alias.name for node in ast.walk(ast.parse(READER.read_text(encoding='utf-8')))
                    if isinstance(node, ast.ImportFrom) and node.module == 'annotator.shot_clock'
                    for alias in node.names}
        for name in ('MIN_DURATION', 'MAX_DURATION', 'DEFAULT_DURATION'):
            self.assertIn(name, imported,
                          f"{READER.relative_to(ROOT).as_posix()} must import {name} from the owner")

    def test_the_settings_guard_takes_its_bounds_from_the_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            ops = Operations(folder)
            self.assertEqual(ops.get()['settings']['shotClock'], shot_clock.DEFAULT_DURATION,
                             "the document default is the owner's default")
            posted = ops.post(dict(action='settings_update', revision=ops.get()['revision'],
                                   shotClock=shot_clock.MIN_DURATION))
            self.assertEqual(posted['settings']['shotClock'], shot_clock.MIN_DURATION,
                             "the guard accepts the owner's minimum")
            ops.post(dict(action='settings_update', revision=ops.get()['revision'],
                          shotClock=shot_clock.MAX_DURATION))
            before = ops.path.read_bytes()
            with self.assertRaisesRegex(
                    ValueError, f"shotClock must be an integer from {shot_clock.MIN_DURATION} "
                                f"to {shot_clock.MAX_DURATION}"):
                ops.post(dict(action='settings_update', revision=ops.get()['revision'],
                              shotClock=shot_clock.MIN_DURATION - 1))
            self.assertEqual(ops.path.read_bytes(), before, 'a refused update writes nothing')

    def test_the_owner_docstring_states_the_bounds_it_holds(self):
        """The owner states its rule in a sentence. A sentence can drift from the code.

        The scan above reads the code of the shipped modules. This case reads the
        sentence of the owner, so a bound that moves in the constants and stays old in
        the docstring fails here.
        """
        typed = [int(text) for text in re.findall(r'\d+', shot_clock.valid_duration.__doc__ or '')]
        self.assertEqual(typed, [shot_clock.MIN_DURATION, shot_clock.MAX_DURATION],
                         'the docstring of valid_duration must state the bounds it holds')


if __name__ == '__main__':
    unittest.main()
