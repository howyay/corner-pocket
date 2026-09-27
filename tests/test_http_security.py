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


if __name__ == '__main__':
    unittest.main()
