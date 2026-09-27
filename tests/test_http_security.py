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


if __name__ == '__main__':
    unittest.main()
