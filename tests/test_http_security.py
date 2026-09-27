"""HTTP-level security tests (docs/private-audit.md area B).

Each test starts its own loopback server on an ephemeral port over a temporary
root: no repository data is read or written.
"""
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
import unittest.mock

from annotator.unified_server import Backend, make_handler


def fixture_root(temp):
    root = Path(temp)
    (root / 'annotator').mkdir()
    (root / 'annotator' / 'ops.html').write_text('<!doctype html><title>fixture</title>')
    (root / 'annotator' / 'ops.js').write_text('void 0;')
    (root / 'data').mkdir()
    (root / 'data' / 'vod_30min_260815.mp4').write_bytes(b'0123456789')
    return root


class LoopbackServer:
    """The real handler behind a real socket, with request logging silenced."""

    def __init__(self, root, server_class=ThreadingHTTPServer, **handler_attributes):
        base = make_handler(Backend(root))
        handler_attributes.setdefault('log_message', lambda self, *args: None)
        self.handler = type('LoopbackHandler', (base,), handler_attributes)
        self.httpd = server_class(('127.0.0.1', 0), self.handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def request(self, method, path, headers=None, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response, response.read()
        finally:
            connection.close()


def csp_directives(response):
    value = response.getheader('Content-Security-Policy') or ''
    return {part.split()[0]: part.split()[1:] for part in (p.strip() for p in value.split(';')) if part}


class SecurityHeaderTests(unittest.TestCase):
    """B-4: every response, including error paths, carries the same policy headers."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.server = LoopbackServer(fixture_root(temp.name))
        self.addCleanup(self.server.close)

    def test_every_response_carries_the_policy_headers(self):
        cases = [('GET', '/', None, None, 200),
                 ('GET', '/ops.js', None, None, 200),
                 ('GET', '/api/operations', None, None, 200),
                 ('GET', '/api/nope', None, None, 404),
                 ('GET', '/media/vod30/video', {'Range': 'bytes=2-5'}, None, 206),
                 ('GET', '/media/vod30/video', {'Range': 'bytes=20-'}, None, 416),
                 ('POST', '/api/operations', {'Content-Type': 'application/json'}, b'{}', 400),
                 ('OPTIONS', '/api/operations', None, None, 501)]
        for method, path, headers, body, status in cases:
            with self.subTest(method=method, path=path, status=status):
                response, _ = self.server.request(method, path, headers, body)
                self.assertEqual(response.status, status)
                csp = csp_directives(response)
                self.assertEqual(csp.get('default-src'), ["'self'"])
                self.assertEqual(csp.get('script-src'), ["'self'"])
                self.assertEqual(csp.get('connect-src'), ["'self'"])
                self.assertEqual(csp.get('frame-src'), ['https://www.twitch.tv'])
                self.assertEqual(csp.get('frame-ancestors'), ["'none'"])
                self.assertEqual(csp.get('base-uri'), ["'none'"])
                self.assertEqual(csp.get('form-action'), ["'self'"])
                self.assertEqual(csp.get('object-src'), ["'none'"])
                self.assertIn('blob:', csp.get('img-src', []))
                self.assertIn('blob:', csp.get('media-src', []))
                self.assertIn("'self'", csp.get('font-src', []))
                self.assertEqual(response.getheader('X-Frame-Options'), 'DENY')
                self.assertEqual(response.getheader('Referrer-Policy'), 'no-referrer')
                permissions = response.getheader('Permissions-Policy') or ''
                for feature in ('camera', 'microphone', 'geolocation', 'payment', 'usb'):
                    self.assertIn(feature + '=()', permissions)
                self.assertEqual(response.getheader('Cross-Origin-Opener-Policy'), 'same-origin')
                self.assertEqual(response.msg.get_all('X-Content-Type-Options'), ['nosniff'])

    def test_scripts_have_no_escape_hatch(self):
        response, _ = self.server.request('GET', '/')
        csp = csp_directives(response)
        for source in ("'unsafe-inline'", "'unsafe-eval'", "'unsafe-hashes'", 'data:', 'blob:', '*', 'https:'):
            self.assertNotIn(source, csp.get('script-src', []))
            self.assertNotIn(source, csp.get('default-src', []))
        self.assertNotIn('*', ' '.join(' '.join(values) for values in csp.values()))


class ConnectionBoundTests(unittest.TestCase):
    """B-7: idle or slow clients cannot pin threads forever, nor grow them without bound."""

    def serve(self, **handler_attributes):
        from annotator import unified_server
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        server = LoopbackServer(fixture_root(temp.name), server_class=unified_server.BoundedHTTPServer,
                                **handler_attributes)
        self.addCleanup(server.close)
        return server

    def test_the_production_defaults_outlast_a_15_second_heartbeat(self):
        from annotator import unified_server
        handler = make_handler(Backend(Path(tempfile.gettempdir())))
        self.assertGreaterEqual(handler.timeout, 60)
        self.assertLessEqual(handler.timeout, 120)
        self.assertGreaterEqual(unified_server.BoundedHTTPServer.max_handlers, 16)
        self.assertLessEqual(unified_server.BoundedHTTPServer.max_handlers, 256)

    def test_a_half_open_request_is_dropped_after_the_timeout(self):
        import socket
        import time
        server = self.serve(timeout=1)
        client = socket.create_connection(('127.0.0.1', server.port), timeout=5)
        self.addCleanup(client.close)
        client.sendall(b'GET / HTTP/1.1\r\nHost: x\r\n')          # headers never finish
        started = time.monotonic()
        self.assertEqual(client.recv(1024), b'')                   # server closed the socket
        self.assertLess(time.monotonic() - started, 4)

    def test_a_slow_body_is_dropped_after_the_timeout(self):
        import socket
        import time
        server = self.serve(timeout=1)
        client = socket.create_connection(('127.0.0.1', server.port), timeout=5)
        self.addCleanup(client.close)
        client.sendall(b'POST /api/operations HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n'
                       b'Content-Length: 100\r\n\r\n{')
        started = time.monotonic()
        data = b''
        while True:
            chunk = client.recv(1024)
            if not chunk:
                break
            data += chunk
        self.assertLess(time.monotonic() - started, 4)
        self.assertNotIn(b'200 OK', data)

    def test_a_stream_that_keeps_writing_is_not_cut(self):
        # A long response that writes a heartbeat more often than the timeout
        # (the shape of an SSE stream) outlives the timeout several times over.
        import time

        def do_GET(self):
            if self.path != '/stream':
                return self.dispatch()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for _ in range(8):
                self.wfile.write(b': heartbeat\n\n')
                self.wfile.flush()
                time.sleep(0.5)
            self.wfile.write(b'data: done\n\n')

        server = self.serve(timeout=1, do_GET=do_GET)
        started = time.monotonic()
        response, body = server.request('GET', '/stream')
        self.assertEqual(response.status, 200)
        self.assertGreater(time.monotonic() - started, 3.5)
        self.assertEqual(body.count(b': heartbeat'), 8)
        self.assertTrue(body.endswith(b'data: done\n\n'))

    def test_handler_threads_are_capped_and_the_excess_is_refused(self):
        import socket
        import threading
        import time
        from annotator import unified_server
        with unittest.mock.patch.object(unified_server.BoundedHTTPServer, 'max_handlers', 4):
            server = self.serve(timeout=30)
        before = threading.active_count()
        idle = []
        for _ in range(12):
            sock = socket.create_connection(('127.0.0.1', server.port), timeout=5)
            sock.sendall(b'GET / HTTP/1.1\r\nHost: x\r\n')           # hold a handler
            idle.append(sock)
            self.addCleanup(sock.close)
        time.sleep(0.5)
        self.assertLessEqual(threading.active_count() - before, 4 + 1)
        refused = 0
        for sock in idle:
            sock.settimeout(0.2)
            try:
                if sock.recv(64).startswith(b'HTTP/1.0 503'):
                    refused += 1
            except socket.timeout:
                pass
        self.assertGreaterEqual(refused, 8)
        for sock in idle:
            sock.close()
        time.sleep(0.5)
        response, _ = server.request('GET', '/')                     # capacity is released
        self.assertEqual(response.status, 200)


class ContentLengthTests(unittest.TestCase):
    """B-8: a malformed Content-Length is a plain 400, never Python's exception text."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.server = LoopbackServer(fixture_root(temp.name))
        self.addCleanup(self.server.close)

    def post(self, length, body=b'{}'):
        import socket
        client = socket.create_connection(('127.0.0.1', self.server.port), timeout=10)
        try:
            head = b'POST /api/operations HTTP/1.0\r\nHost: x\r\nContent-Type: application/json\r\n'
            if length is not None:
                head += b'Content-Length: ' + length + b'\r\n'
            client.sendall(head + b'\r\n' + body)
            data = b''
            while chunk := client.recv(4096):
                data += chunk
        finally:
            client.close()
        status = int(data.split(b' ', 2)[1])
        return status, data.split(b'\r\n\r\n', 1)[1]

    def test_malformed_lengths_are_a_plain_400(self):
        # RFC 9110: Content-Length = 1*DIGIT. '²' (latin-1 0xb2) passes str.isdigit()
        # but not int(); '-5' and '+2' are not digits at all.
        for length in (b'abc', b'1.5', b'+2', b'-5', b' 2 x', b'0x10', b'2, 2', b'\xb2', b'\xd9\xa2'):
            with self.subTest(length=length):
                status, body = self.post(length)
                self.assertEqual(status, 400)
                self.assertEqual(body, b'{"error": "invalid Content-Length"}')

    def test_well_formed_lengths_keep_their_meaning(self):
        self.assertEqual(self.post(b'2')[0], 400)                    # {} reaches validation: revision required
        self.assertIn(b'revision', self.post(b'2')[1])
        for length in (None, b'0', b'65537', b'99999999999999999999'):
            with self.subTest(length=length):
                status, body = self.post(length)
                self.assertEqual(status, 413)
                self.assertEqual(body, b'{"error": "invalid request size"}')


class ErrorBodyTests(unittest.TestCase):
    """B-11: error bodies carry operator sentences, never internals.

    Unexpected exceptions become a generic body with a reference; the detail,
    traceback included, goes to stderr (the service journal). Sentences written
    for the operator keep their words but lose absolute paths.
    """

    SECRET = '/home/someone/private/models/weights.pth'

    def setUp(self):
        import contextlib
        import io
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.server = LoopbackServer(fixture_root(temp.name))
        self.addCleanup(self.server.close)
        self.log = io.StringIO()                         # the service's stderr is the journal
        quiet = contextlib.redirect_stderr(self.log)
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def get_json(self, path):
        import json
        response, body = self.server.request('GET', path)
        return response.status, json.loads(body)

    def fail_with(self, error):
        from annotator import unified_server
        patcher = unittest.mock.patch.object(unified_server.Backend, 'operations', side_effect=error)
        patcher.start()
        self.addCleanup(patcher.stop)
        return self.get_json('/api/operations')

    def test_an_unexpected_exception_is_a_generic_500_and_is_logged(self):
        status, body = self.fail_with(OSError(2, 'No such file or directory', self.SECRET))
        self.assertEqual(status, 500)
        self.assertEqual(body['error'], 'internal error')
        self.assertRegex(body.get('ref', ''), r'^[0-9a-f]{8}$')
        self.assertNotIn(self.SECRET, str(body))
        self.assertIn(f"error {body['ref']}: FileNotFoundError", self.log.getvalue())
        self.assertIn(self.SECRET, self.log.getvalue())
        self.assertIn('Traceback', self.log.getvalue())

    def test_type_and_key_errors_do_not_echo_their_text(self):
        for error in (TypeError("'NoneType' object is not subscriptable: " + self.SECRET),
                      KeyError(self.SECRET)):
            with self.subTest(error=type(error).__name__):
                status, body = self.fail_with(error)
                self.assertEqual(status, 400)
                self.assertEqual(body['error'], 'invalid request')
                self.assertNotIn(self.SECRET, str(body))
                self.assertIn(body['ref'], self.log.getvalue())
                unittest.mock.patch.stopall()

    def test_validation_messages_are_kept_without_paths(self):
        self.assertEqual(self.fail_with(ValueError('rating must be an integer from 0 to 1000')),
                         (400, {'error': 'rating must be an integer from 0 to 1000'}))
        unittest.mock.patch.stopall()
        status, body = self.fail_with(ValueError('cannot read ' + self.SECRET))
        self.assertEqual((status, body), (400, {'error': 'cannot read weights.pth'}))

    def test_urls_survive_path_stripping(self):
        from annotator.unified_server import operator_message
        text = 'Use https://www.twitch.tv/videos/123 or https://www.twitch.tv/channel, not ' + self.SECRET
        self.assertEqual(operator_message(ValueError(text)),
                         'Use https://www.twitch.tv/videos/123 or https://www.twitch.tv/channel, not weights.pth')
        self.assertEqual(operator_message(ValueError('ratio 3/4 and a/b stay')), 'ratio 3/4 and a/b stay')

    def test_a_failed_job_keeps_its_sentence_but_not_internals(self):
        from annotator.unified_server import APIError, Backend, public_error
        self.assertEqual(public_error(APIError('rebuild already running', 409)), 'rebuild already running')
        self.assertEqual(public_error(RuntimeError('OSNet weights not found: ' + self.SECRET)),
                         'OSNet weights not found: weights.pth')
        text = public_error(OSError(13, 'Permission denied', self.SECRET))
        self.assertRegex(text, r'^internal error \(ref [0-9a-f]{8}\)$')
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            stderr = f'Traceback (most recent call last):\n  File "{self.SECRET}", line 1\nRuntimeError: boom\n'
            with unittest.mock.patch('annotator.unified_server.subprocess.run',
                                     return_value=unittest.mock.Mock(returncode=1, stderr=stderr, stdout='')):
                backend._rebuild()
            self.assertEqual(backend.job['status'], 'failed')
            self.assertRegex(backend.job['error'], r'^rebuild failed \(exit 1; ref [0-9a-f]{8}\)$')
            self.assertIn(self.SECRET, self.log.getvalue())


class EnrollPreviewSingleFlightTests(unittest.TestCase):
    """B-9: one enrolment preview at a time (each is ~6.5 CPU-s); the next gets 409."""

    PAYLOAD = {'dataset': 'vod30', 'frame_index': 30, 'bbox': [10, 10, 50, 90]}

    def test_a_second_preview_while_one_runs_is_refused_then_allowed(self):
        from annotator.unified_server import APIError
        started, release = threading.Event(), threading.Event()

        def slow_plan(*args, **kwargs):
            started.set()
            release.wait(10)
            return None

        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            with unittest.mock.patch('src.enroll_from_tracklet.plan_for_selection', side_effect=slow_plan), \
                    unittest.mock.patch('src.enroll_from_tracklet.preview_payload', return_value={'ok': False}):
                first = threading.Thread(target=backend.enroll_preview, args=(dict(self.PAYLOAD),))
                first.start()
                self.assertTrue(started.wait(5))
                with self.assertRaises(APIError) as refused:
                    backend.enroll_preview(dict(self.PAYLOAD))
                self.assertEqual(refused.exception.status, 409)
                self.assertIn('preview', str(refused.exception))
                release.set()
                first.join(5)
                self.assertEqual(backend.enroll_preview(dict(self.PAYLOAD)), {'ok': False})

    def test_a_failed_preview_frees_the_slot(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            with unittest.mock.patch('src.enroll_from_tracklet.plan_for_selection',
                                     side_effect=[RuntimeError('decode failed'), None]), \
                    unittest.mock.patch('src.enroll_from_tracklet.preview_payload', return_value={'ok': False}):
                with self.assertRaises(RuntimeError):
                    backend.enroll_preview(dict(self.PAYLOAD))
                self.assertEqual(backend.enroll_preview(dict(self.PAYLOAD)), {'ok': False})

    def test_invalid_input_is_rejected_without_taking_the_slot(self):
        from annotator.unified_server import APIError
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(Path(temp))
            with self.assertRaises(APIError) as bad:
                backend.enroll_preview({'dataset': 'vod30', 'frame_index': -1, 'bbox': [0, 0, 1, 1]})
            self.assertEqual(bad.exception.status, 400)
            with unittest.mock.patch('src.enroll_from_tracklet.plan_for_selection', return_value=None), \
                    unittest.mock.patch('src.enroll_from_tracklet.preview_payload', return_value={'ok': False}):
                self.assertEqual(backend.enroll_preview(dict(self.PAYLOAD)), {'ok': False})


if __name__ == '__main__':
    unittest.main()
