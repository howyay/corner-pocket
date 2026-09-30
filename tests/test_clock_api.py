"""The shared shot clock over HTTP: GET /api/clock, POST /api/clock and the
GET /api/clock/stream Server-Sent Events. Every backend lives in a temporary
root; the stream tests bind an ephemeral loopback port (127.0.0.1:0), never a
fixed one, and nothing under the repository's out/ is touched."""
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from annotator.unified_server import Backend, BoundedHTTPServer, make_handler


def file_stamp(path):
    """Bytes + size + mtime: the three things a read must never change."""
    path = Path(path)
    return (hashlib.md5(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns)


class ClockApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.backend = Backend(self.root)
        self.addCleanup(self.backend.close)
        self.file = self.root / 'out' / 'corner-pocket' / 'clock.json'

    def request(self, path, payload=None, origin=None, raw=None):
        handler = make_handler(self.backend).__new__(make_handler(self.backend))
        body = raw if raw is not None else (b'' if payload is None else json.dumps(payload).encode())
        headers = {'Host': '127.0.0.1:8130', 'Content-Type': 'application/json', 'Content-Length': str(len(body))}
        if origin:
            headers['Origin'] = origin
        handler.path, handler.headers = path, headers
        handler.rfile, handler.wfile = io.BytesIO(body), io.BytesIO()
        handler.send_response = lambda status: setattr(handler, 'status', status)
        handler.response_headers = {}
        handler.send_header = lambda key, value: handler.response_headers.update({key: value})
        handler.end_headers = lambda: None
        handler.dispatch(post=payload is not None or raw is not None)
        return handler.status, json.loads(handler.wfile.getvalue())

    def test_get_reports_the_settings_duration_and_the_server_time_and_writes_nothing(self):
        state = self.backend.post(['api', 'operations'], {'revision': 0, 'action': 'settings_update', 'shotClock': 45})
        self.assertEqual(state['settings']['shotClock'], 45)
        ops_stamp = file_stamp(self.root / 'out' / 'corner-pocket' / 'state.json')
        before = int(time.time() * 1000)
        status, clock = self.request('/api/clock')
        after = int(time.time() * 1000)
        self.assertEqual(status, 200)
        self.assertEqual({k: clock[k] for k in ('duration', 'running', 'deadline_ms', 'remaining_ms', 'seq', 'expired')},
                         dict(duration=45, running=False, deadline_ms=None, remaining_ms=45_000, seq=0, expired=False))
        self.assertTrue(before <= clock['server_now_ms'] <= after, 'server_now_ms is the server epoch in ms')
        self.assertFalse(self.file.exists(), 'a read never creates clock.json')
        self.assertEqual(file_stamp(self.root / 'out' / 'corner-pocket' / 'state.json'), ops_stamp)

    def test_post_intents_are_explicit_idempotent_and_persisted(self):
        origin = 'http://127.0.0.1:8130'
        status, started = self.request('/api/clock', {'action': 'start'}, origin)
        self.assertEqual((status, started['running'], started['seq']), (200, True, 1))
        self.assertEqual(started['deadline_ms'] - started['server_now_ms'], 30_000, 'the default duration is 30 s')
        self.assertEqual(json.loads(self.file.read_text())['deadline_ms'], started['deadline_ms'])
        stamp = file_stamp(self.file)
        # A second Start - someone else pressing at the same moment - changes nothing.
        status, again = self.request('/api/clock', {'action': 'start'}, origin)
        self.assertEqual((status, again['deadline_ms'], again['seq']), (200, started['deadline_ms'], 1))
        self.assertEqual(file_stamp(self.file), stamp)
        seqs = [started['seq']]
        for payload in ({'action': 'pause'}, {'action': 'pause'}, {'action': 'reset'}, {'action': 'set', 'duration': 60},
                        {'action': 'start'}, {'action': 'set', 'duration': 20}):
            status, state = self.request('/api/clock', payload, origin)
            self.assertEqual(status, 200, payload)
            seqs.append(state['seq'])
        self.assertEqual(seqs, [1, 2, 2, 3, 4, 5, 6])
        self.assertEqual((state['duration'], state['running'], state['remaining_ms']), (20, False, 20_000))
        # Another backend on the same root - a restarted service - reads the same clock.
        self.assertEqual({k: v for k, v in Backend(self.root).clock_state().items() if k != 'server_now_ms'},
                         {k: v for k, v in state.items() if k != 'server_now_ms'})

    def test_invalid_requests_are_refused_and_write_nothing(self):
        origin = 'http://127.0.0.1:8130'
        cases = [({'action': 'toggle'}, 400), ({'action': 'set', 'duration': 4}, 400),
                 ({'action': 'set', 'duration': 301}, 400), ({'action': 'set', 'duration': '45'}, 400),
                 ({'action': 'set', 'duration': 45.0}, 400), ({'action': 'set', 'duration': True}, 400),
                 ({'action': 'set'}, 400), ({'action': 'start', 'duration': 30}, 400), ({}, 400),
                 ({'action': 'start', 'revision': 1}, 400)]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                status, body = self.request('/api/clock', payload, origin)
                self.assertEqual(status, expected)
                self.assertIn('error', body)
        status, body = self.request('/api/clock', raw=b'[]')
        self.assertEqual(status, 400)
        status, body = self.request('/api/clock', {'action': 'start'}, 'https://evil.example')
        self.assertEqual(status, 403, 'a cross-origin write is refused like every other write')
        self.assertFalse(self.file.exists(), 'no refused request created the file')
        self.assertEqual(self.request('/api/clock', {'action': 'set', 'duration': 45}, origin)[0], 200)
        stamp = file_stamp(self.file)
        for payload, _ in cases:
            self.request('/api/clock', payload, origin)
        self.assertEqual(file_stamp(self.file), stamp)

    def test_expiry_is_computed_by_get_and_never_persisted(self):
        now = [1_000_000]
        with patch('annotator.shot_clock.epoch_ms', lambda: now[0]):
            origin = 'http://127.0.0.1:8130'
            self.request('/api/clock', {'action': 'set', 'duration': 5}, origin)
            status, started = self.request('/api/clock', {'action': 'start'}, origin)
            self.assertEqual(started['deadline_ms'], 1_005_000)
            stamp = file_stamp(self.file)
            now[0] = 1_004_999
            self.assertEqual(self.request('/api/clock')[1]['running'], True)
            for step in range(40):
                now[0] = 1_005_000 + step * 1_500
                status, state = self.request('/api/clock')
                self.assertEqual((status, state['running'], state['remaining_ms'], state['expired'], state['seq']),
                                 (200, False, 0, True, 2))
                self.assertEqual(state['server_now_ms'], now[0])
            self.assertEqual(file_stamp(self.file), stamp, 'md5, size and mtime unchanged across 40 expired reads')

    def test_a_damaged_clock_file_is_reported_not_reset(self):
        self.file.parent.mkdir(parents=True)
        self.file.write_text('{"duration": 3}')
        stamp = file_stamp(self.file)
        with patch('sys.stderr', io.StringIO()) as log:
            status, body = self.request('/api/clock')
        self.assertEqual(status, 500)
        self.assertRegex(body['error'], r'^the shared shot clock file is damaged \(ref [0-9a-f]{8}\)$')
        self.assertNotIn(str(self.root), body['error'], 'no path or parser text reaches the client')
        self.assertIn('invalid shot clock file', log.getvalue(), 'the detail is in the server log')
        self.assertEqual(file_stamp(self.file), stamp)


class ClockStreamTests(unittest.TestCase):
    """A real loopback server on an ephemeral port: the stream is a long-lived
    response that the in-memory handler above cannot exercise."""

    def setUp(self, timeout=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.backend = Backend(self.root)
        handler = make_handler(self.backend)
        handler.log_message = lambda *args: None
        if timeout is not None:
            handler.timeout = timeout
        # The production server class: a per-read socket timeout and a slot cap.
        self.server = BoundedHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.backend.close)
        self.port = self.server.server_address[1]

    def open_stream(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        self.addCleanup(connection.close)
        connection.request('GET', '/api/clock/stream')
        return connection.getresponse()

    @staticmethod
    def next_event(response):
        """One SSE block: (event name, parsed data, comment lines)."""
        name, data, comments = None, None, []
        while True:
            line = response.readline().decode()
            if line == '':
                return None
            line = line.rstrip('\n')
            if line == '':
                if name or data is not None:
                    return name, data, comments
                continue
            if line.startswith(':'):
                comments.append(line)
            elif line.startswith('event: '):
                name = line[7:]
            elif line.startswith('data: '):
                data = json.loads(line[6:])

    def post(self, payload):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        body = json.dumps(payload).encode()
        connection.request('POST', '/api/clock', body, {'Content-Type': 'application/json'})
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_the_stream_headers_first_event_and_a_change(self):
        response = self.open_stream()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('Content-Type'), 'text/event-stream')
        self.assertEqual(response.getheader('Cache-Control'), 'no-cache, no-transform')
        self.assertEqual(response.getheader('X-Accel-Buffering'), 'no')
        self.assertIsNone(response.getheader('Content-Length'))
        self.assertEqual(response.msg.get_all('X-Content-Type-Options'), ['nosniff'], 'nosniff exactly once')
        self.assertIn("connect-src 'self'", response.getheader('Content-Security-Policy'))
        name, first, _ = self.next_event(response)
        self.assertEqual((name, first['seq'], first['running']), ('clock', 0, False))
        self.assertIn('server_now_ms', first)
        began = time.monotonic()
        status, posted = self.post({'action': 'start'})
        name, event, _ = self.next_event(response)
        latency = time.monotonic() - began
        self.assertEqual(status, 200)
        self.assertEqual((name, event['seq'], event['running'], event['deadline_ms']),
                         ('clock', 1, True, posted['deadline_ms']))
        # The heartbeat is 15 s, so anything well under it proves the change woke the
        # stream; 5 s leaves room for a loaded machine (typically ~10 ms here).
        self.assertLess(latency, 5.0, 'a change reaches an open stream at once, not at the next heartbeat')
        self.assertTrue((self.root / 'out' / 'corner-pocket' / 'clock.json').exists(), 'the POST, not the stream, wrote it')

    def test_heartbeats_keep_an_idle_stream_talking(self):
        with patch('annotator.shot_clock.HEARTBEAT_S', 0.2):
            response = self.open_stream()
            self.assertEqual(self.next_event(response)[0], 'clock')
            beats = [self.next_event(response) for _ in range(3)]
        for name, data, comments in beats:
            self.assertEqual(name, 'heartbeat')
            self.assertIn(': heartbeat', comments, 'a comment line too, for proxies')
            self.assertEqual(data['seq'], 0)
            self.assertIn('server_now_ms', data)
        self.assertFalse((self.root / 'out' / 'corner-pocket' / 'clock.json').exists(), 'streaming writes nothing')

    def test_a_waiting_stream_holds_no_lock_and_closes_with_the_server(self):
        response = self.open_stream()
        self.assertEqual(self.next_event(response)[0], 'clock')
        time.sleep(0.1)  # the stream is now waiting for a change
        self.assertTrue(self.backend.lock.acquire(timeout=1), 'the backend lock is free')
        self.backend.lock.release()
        began = time.monotonic()
        state = self.backend.post(['api', 'operations'], {'revision': 0, 'action': 'settings_update', 'shotClock': 20})
        self.assertLess(time.monotonic() - began, 1.0, 'an operations write is not held up by an open stream')
        self.assertEqual(state['revision'], 1)
        status, started = self.post({'action': 'start'})
        self.assertEqual((status, started['duration'], started['deadline_ms'] - started['server_now_ms']), (200, 20, 20_000),
                         'a clock that was never written takes settings.shotClock')
        self.assertEqual(self.next_event(response)[1]['seq'], 1)
        self.backend.close()
        self.assertIsNone(self.next_event(response), 'closing the backend ends every stream')

    def test_a_client_that_leaves_frees_its_stream(self):
        def streams():
            return [t for t in threading.enumerate() if 'process_request_thread' in t.name and t.is_alive()]
        with patch('annotator.shot_clock.HEARTBEAT_S', 0.1):
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
            connection.request('GET', '/api/clock/stream')
            response = connection.getresponse()
            self.assertEqual(self.next_event(response)[0], 'clock')
            self.assertEqual(len(streams()), 1)
            response.close()
            connection.close()
            deadline = time.monotonic() + 3
            while streams() and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertEqual(streams(), [], 'the next heartbeat write fails and the thread ends')

    def outlives_the_socket_timeout(self, timeout, heartbeat, seconds):
        """Restart the server with a per-read socket timeout, open a stream and
        read it for `seconds`: it must still be open, must have carried a
        heartbeat at least every `heartbeat` seconds, and must deliver a change."""
        self.doCleanups()
        self.setUp(timeout=timeout)
        with patch('annotator.shot_clock.HEARTBEAT_S', heartbeat):
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=heartbeat * 3)
            self.addCleanup(connection.close)
            connection.request('GET', '/api/clock/stream')
            response = connection.getresponse()
            self.assertEqual(self.next_event(response)[0], 'clock')
            began = last = time.monotonic()
            beats, gaps = 0, []
            while time.monotonic() - began < seconds:
                name, data, _ = self.next_event(response)
                now = time.monotonic()
                gaps.append(now - last)
                last = now
                beats += name == 'heartbeat'
            self.assertEqual(self.post({'action': 'start'})[0], 200)
            name, data, _ = self.next_event(response)
        self.assertGreater(time.monotonic() - began, timeout, 'open past the handler timeout')
        self.assertEqual((name, data['seq'], data['running']), ('clock', 1, True), 'and still delivering changes')
        self.assertGreaterEqual(beats, int(seconds / heartbeat) - 1)
        self.assertLess(max(gaps), heartbeat + 1.5, 'never silent for longer than the heartbeat')
        return beats, max(gaps)

    def test_a_stream_outlives_the_socket_timeout(self):
        # The handler drops a read that stalls for `timeout` s (B-7). A stream reads
        # nothing after its request line - it only writes - so it is never cut.
        self.outlives_the_socket_timeout(timeout=1, heartbeat=0.3, seconds=3.5)

    @unittest.skipUnless(os.environ.get('CLOCK_LONG_STREAM'), 'CLOCK_LONG_STREAM=1 runs the 75 s production-timeout check')
    def test_a_stream_outlives_the_production_timeout(self):
        from annotator.shot_clock import HEARTBEAT_S
        timeout = make_handler(self.backend).timeout
        self.assertLess(HEARTBEAT_S, timeout)
        beats, gap = self.outlives_the_socket_timeout(timeout=timeout, heartbeat=HEARTBEAT_S, seconds=timeout + 15)
        print(f'\nproduction timeout {timeout} s, heartbeat {HEARTBEAT_S} s: {beats} heartbeats, '
              f'longest silence {gap:.2f} s, stream open {timeout + 15}+ s')


if __name__ == '__main__':
    unittest.main()
