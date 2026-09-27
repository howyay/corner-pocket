"""Server-authoritative shared shot clock; standard library only.

One clock for every device (club PC, phone, tablet, any browser, any tab). It is
deliberately NOT part of the revisioned operations state in
annotator/operations.py: a Start or Pause would bump that revision and turn every
other operator's next write into a stale-revision conflict.

State, with every instant in server epoch milliseconds:
  duration      shot time in whole seconds, 5-300 (the settings.shotClock rule)
  running       True while counting down
  deadline_ms   the absolute instant the shot time runs out (running only)
  remaining_ms  time left while paused (paused only)
  seq           bumped by every real change, never by a read or a no-op
  updated_at    ISO-8601 time of the last real change (None before the first)

snapshot() never writes: once the deadline has passed it reports
running False / remaining_ms 0 / expired True in the answer and persists
nothing. apply() takes an explicit intent - start, pause, reset or set, never a
"toggle", so two people pressing at once cannot cancel each other out - and
persists only a real change, atomically (temp file + os.replace). A running
clock survives a restart because its deadline is absolute.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import time

ACTIONS = ('start', 'pause', 'reset', 'set')
MIN_DURATION = 5
MAX_DURATION = 300
DEFAULT_DURATION = 30
# The change stream (GET /api/clock/stream) is never silent for longer than this:
# Cloudflare drops an idle proxied connection at ~100 s, and a page that hears
# nothing for 30 s falls back to polling.
HEARTBEAT_S = 15
# nosniff and the other policy headers come from the server's end_headers(), once.
SSE_HEADERS = {'Content-Type': 'text/event-stream',
               'Cache-Control': 'no-cache, no-transform',
               'X-Accel-Buffering': 'no'}


def epoch_ms():
    """The server's wall clock in epoch milliseconds - the one clock every device
    is compared against."""
    return time.time_ns() // 1_000_000


def valid_duration(value):
    """The same rule as settings.shotClock: an integer from 5 to 300 seconds."""
    if type(value) is not int or not MIN_DURATION <= value <= MAX_DURATION:
        raise ValueError(f'duration must be an integer from {MIN_DURATION} to {MAX_DURATION}')
    return value


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def _checked(state, path):
    """A persisted clock is used as written or refused; never silently reset."""
    def bad(reason):
        return ValueError(f'invalid shot clock file {path}: {reason}')
    if not isinstance(state, dict):
        raise bad('object required')
    try:
        duration = valid_duration(state.get('duration'))
    except ValueError as error:
        raise bad(str(error)) from None
    running, deadline, remaining = state.get('running'), state.get('deadline_ms'), state.get('remaining_ms')
    if type(running) is not bool:
        raise bad('running must be true or false')
    if running and type(deadline) is not int:
        raise bad('a running clock needs an integer deadline_ms')
    if not running and (type(remaining) is not int or not 0 <= remaining <= duration * 1000):
        raise bad('a paused clock needs remaining_ms from 0 to duration')
    seq, updated = state.get('seq'), state.get('updated_at')
    if type(seq) is not int or seq < 0:
        raise bad('seq must be a non-negative integer')
    if updated is not None and not isinstance(updated, str):
        raise bad('updated_at must be text')
    return dict(duration=duration, running=running,
                deadline_ms=deadline if running else None,
                remaining_ms=None if running else remaining, seq=seq, updated_at=updated)


class ShotClock:
    """The one shared clock, persisted at `path`.

    default_duration (an int, or a callable such as "read settings.shotClock")
    is used only while nothing has been persisted yet; an invalid default falls
    back to 30 s rather than inventing a clock the settings do not allow."""

    def __init__(self, path, default_duration=DEFAULT_DURATION):
        self.path = Path(path)
        self.condition = threading.Condition(threading.RLock())
        self._default = default_duration
        self._closed = False
        self._state = _checked(json.loads(self.path.read_text()), self.path) if self.path.exists() else None

    @property
    def seq(self):
        with self.condition:
            return self._state['seq'] if self._state else 0

    @property
    def closed(self):
        return self._closed

    def _default_duration(self):
        value = self._default() if callable(self._default) else self._default
        try:
            return valid_duration(value)
        except ValueError:
            return DEFAULT_DURATION

    def _current(self, default):
        # Caller holds the lock. The default is resolved before the lock is taken,
        # so a callable that reads other state never runs under this lock.
        if self._state is not None:
            return dict(self._state)
        duration = default if default is not None else DEFAULT_DURATION
        return dict(duration=duration, running=False, deadline_ms=None,
                    remaining_ms=duration * 1000, seq=0, updated_at=None)

    @staticmethod
    def _effective(state, now_ms):
        view = dict(state, expired=False)
        if state['running'] and state['deadline_ms'] <= now_ms:
            # Expiry is an answer, not a write: nothing is persisted here.
            view.update(running=False, remaining_ms=0, expired=True)
        return view

    def snapshot(self, now_ms=None):
        """The clock as of `now_ms` (server epoch ms). Never writes."""
        now_ms = epoch_ms() if now_ms is None else int(now_ms)
        default = self._default_duration() if self._state is None else None
        with self.condition:
            return self._effective(self._current(default), now_ms)

    def apply(self, action, duration=None, now_ms=None):
        """Apply one explicit intent; persist and notify only on a real change.

        start  runs from what is left (from the full duration once expired or at 0);
               a no-op while already running
        pause  keeps what is left; a no-op while already paused or expired
        reset  paused at the full duration
        set    a new duration (5-300 s), paused at it
        """
        if action not in ACTIONS:
            raise ValueError('action must be one of start, pause, reset, set')
        if action == 'set':
            duration = valid_duration(duration)
        elif duration is not None:
            raise ValueError('duration is accepted only with set')
        now_ms = epoch_ms() if now_ms is None else int(now_ms)
        default = self._default_duration() if self._state is None else None
        with self.condition:
            current = self._current(default)
            view = self._effective(current, now_ms)
            full = current['duration'] * 1000
            if action == 'start':
                if view['running']:
                    return view
                left = view['remaining_ms'] if view['remaining_ms'] > 0 else full
                changed = dict(duration=current['duration'], running=True,
                               deadline_ms=now_ms + left, remaining_ms=None)
            elif action == 'pause':
                if not view['running']:
                    return view
                # Clamped: a server clock stepped backwards must not bank extra time.
                changed = dict(duration=current['duration'], running=False, deadline_ms=None,
                               remaining_ms=min(full, current['deadline_ms'] - now_ms))
            else:
                target = duration if action == 'set' else current['duration']
                if (not view['running'] and not view['expired'] and current['duration'] == target
                        and view['remaining_ms'] == target * 1000):
                    return view
                changed = dict(duration=target, running=False, deadline_ms=None,
                               remaining_ms=target * 1000)
            changed.update(seq=current['seq'] + 1, updated_at=_iso(now_ms))
            self._save(changed)
            self._state = changed
            self.condition.notify_all()
            return self._effective(changed, now_ms)

    def wait(self, seq, timeout):
        """Block until the seq differs from `seq`, the clock is closed, or
        `timeout` seconds pass. Returns True when something changed."""
        with self.condition:
            return bool(self.condition.wait_for(
                lambda: self._closed or (self._state['seq'] if self._state else 0) != seq, timeout))

    def close(self):
        """Release every waiter (server shutdown)."""
        with self.condition:
            self._closed = True
            self.condition.notify_all()

    def serve_events(self, state, stream, heartbeat_s=None):
        """Write Server-Sent Events to `stream` until the clock is closed or the
        client goes away (the write then raises OSError): one `clock` event with
        state() now and one after every change, and a heartbeat whenever nothing
        changed for heartbeat_s. The heartbeat is a comment line for proxies plus
        a `heartbeat` event, because EventSource hides comments from the page and
        the page must see that the stream is alive. Waiting is on this clock's
        own Condition only; no other lock is held while it waits."""
        heartbeat_s = HEARTBEAT_S if heartbeat_s is None else heartbeat_s
        stream.write(b'retry: 2000\n\n')
        seq = None
        while not self._closed:
            if self.seq != seq:
                event = state()
                seq = event['seq']
                stream.write(b'event: clock\ndata: ' + json.dumps(event, allow_nan=False).encode() + b'\n\n')
            else:
                beat = json.dumps({'seq': seq, 'server_now_ms': epoch_ms()}).encode()
                stream.write(b': heartbeat\nevent: heartbeat\ndata: ' + beat + b'\n\n')
            stream.flush()
            self.wait(seq, heartbeat_s)

    def _save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.clock-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream, indent=2, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
