"""The shared shot clock module on its own: intents, idempotence, seq, expiry
without writes, persistence across instances and duration validation. Every
clock lives in a temporary directory; nothing under the repository's out/ is
touched."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from annotator.shot_clock import ShotClock, epoch_ms


def file_stamp(path):
    """Bytes + size + mtime: the three things a read must never change."""
    path = Path(path)
    return (hashlib.md5(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns)


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
                                     seq=0, updated_at=None, expired=False))
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
        with patch('annotator.shot_clock.os.replace', side_effect=OSError('disk full')):
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
        began = time.monotonic()
        clock.apply('start')
        waiter.join(2)
        self.assertEqual(woke, [True])
        self.assertLess(time.monotonic() - began, 1)
        clock.apply('start')  # no-op: nobody is told anything changed
        self.assertFalse(clock.wait(clock.seq, timeout=0.2))
        waiter = threading.Thread(target=lambda: woke.append(clock.wait(clock.seq, timeout=5)))
        waiter.start()
        time.sleep(0.05)
        clock.close()
        waiter.join(2)
        self.assertEqual(woke, [True, True], 'close() releases a waiting stream')
        self.assertFalse(waiter.is_alive())


if __name__ == '__main__':
    unittest.main()
