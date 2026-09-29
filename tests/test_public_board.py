"""The read-only public board (docs/public-board.md): its own listener.

The public listener (--public-port) answers GET/HEAD of a fixed set of paths and
nothing else. Each test runs the real handlers behind loopback sockets over a
temporary root; no repository data is read or written.
"""
import http.client
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from annotator.unified_server import (BOARD_CSP, BOARD_FONTS, Backend, BoundedHTTPServer, PublicBoardServer,
                                      make_handler, make_public_handler)

ROOT = Path(__file__).resolve().parents[1]
#: Contents of files the public listener must never hand out.
SECRETS = (b"OPS PAGE", b"OPS SCRIPT", b"OPS STYLE", b"APP SCRIPT", b"APP PAGE", b"VISION SCRIPT",
           b"VIDEO BYTES", b"LICENSE TEXT", b"NOT A BOARD FONT")
#: Every one of these is a 404 on the public listener, for GET and HEAD alike.
NOT_PUBLIC = (
    # The operator API and media: every route but /api/board.
    "/api/operations", "/api/unified", "/api/unified?dataset=vod30", "/api/datasets", "/api/live",
    "/api/live/frame", "/api/clip?t=1", "/api/frame?frame=1", "/api/review-template", "/api/identity",
    "/api/board/", "/api//board", "/api/board/../operations", "/API/BOARD", "/api/board%00", "/api", "/api/",
    "/media/vod30/video", "/media/vod30/frame?t=1", "/media/", "/data/vod_30min_260815.mp4",
    # The operator console's own files, and the board page under any other name.
    "/ops.js", "/ops.css", "/ops.html", "/app.js", "/app.html", "/app.css", "/vision-stage.js", "/display",
    "/board.html", "/index.html", "/annotator/board.js",
    # Fonts the board does not use, the licence texts and the build script.
    "/fonts/OFL-Barlow.txt", "/fonts/zilla-slab-400.woff2", "/fonts/build_fonts.py", "/fonts/", "/fonts",
    # Near-misses of whitelisted names.
    "/board.js/", "/./board.js", "/%62oard.js", "/BOARD.JS", "/board.js%00", "/board.js;.css", "/board.js.map",
    # Traversal: plain, encoded, double-encoded, mixed case, backslashes.
    "/../annotator/ops.js", "/%2e%2e/annotator/ops.js", "/%2E%2E/%2E%2E/etc/passwd", "/%252e%252e/annotator/ops.js",
    "/fonts/..%2fops.js", "/fonts/%2e%2e/ops.js", "/fonts/%2e%2e%2fops.js", "/fonts/..%252fops.js",
    "/fonts/..%5c..%5cops.js", "/..\\annotator\\ops.js", "/fonts\\..\\ops.js", "/fonts/..\\..\\ops.js",
    "/%5c..%5cops.js", "//api/operations", "///media/vod30/video",
    # Query and fragment tricks: the query is never read, so it cannot pick another route.
    "/ops.js?x=1", "/api/operations?/api/board", "/api/operations?path=/api/board", "/api/operations#/api/board",
    "/%3F/api/board", "*", "http://127.0.0.1/api/operations",
)


def fixture_root(temp):
    root = Path(temp)
    annotator = root / "annotator"
    (annotator / "fonts").mkdir(parents=True)
    files = {"board.html": "<!doctype html><title>board fixture</title>", "board.js": "void 'board fixture';",
             "board.css": "body{color:#fff}", "ops.html": "OPS PAGE", "ops.js": "OPS SCRIPT", "ops.css": "OPS STYLE",
             "app.js": "APP SCRIPT", "app.html": "APP PAGE", "app.css": "APP STYLE", "vision-stage.js": "VISION SCRIPT",
             "favicon.svg": "<svg xmlns='http://www.w3.org/2000/svg'/>"}
    for name, text in files.items():
        (annotator / name).write_text(text)
    for name in BOARD_FONTS:
        (annotator / "fonts" / name).write_bytes(b"wOF2" + name.encode())
    (annotator / "fonts" / "zilla-slab-400.woff2").write_bytes(b"NOT A BOARD FONT")
    (annotator / "fonts" / "OFL-Barlow.txt").write_text("LICENSE TEXT")
    (annotator / "fonts" / "build_fonts.py").write_text("LICENSE TEXT")
    (root / "data").mkdir()
    (root / "data" / "vod_30min_260815.mp4").write_bytes(b"VIDEO BYTES")
    return root


class Loopback:
    """A real server on an ephemeral loopback port, request logging silenced."""

    def __init__(self, server_class, handler):
        quiet = type("Quiet" + handler.__name__, (handler,), {"log_message": lambda self, *args: None})
        self.httpd = server_class(("127.0.0.1", 0), quiet)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def request(self, method, path, headers=None, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response, response.read()
        finally:
            connection.close()

    def raw(self, data):
        """Send bytes http.client would refuse to, and read until the server closes."""
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as sock:
            sock.sendall(data)
            chunks = []
            try:
                while chunk := sock.recv(65536):
                    chunks.append(chunk)
            except ConnectionResetError:
                pass  # the server closed with our unread bytes still queued: what came before stands
            return b"".join(chunks)


class PublicListenerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.backend = Backend(self.root)
        self.public = Loopback(PublicBoardServer, make_public_handler(self.backend))
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.public.close)

    def assertNoSecrets(self, body, path):
        for secret in SECRETS:
            self.assertNotIn(secret, body, path)

    def test_the_board_files_are_served_with_their_types(self):
        expected = {"/": ("board.html", "text/html; charset=utf-8"),
                    "/?lang=zh": ("board.html", "text/html; charset=utf-8"),
                    "/?/../ops.js": ("board.html", "text/html; charset=utf-8"),
                    "/board.js": ("board.js", "text/javascript; charset=utf-8"),
                    "/board.css": ("board.css", "text/css; charset=utf-8"),
                    "/favicon.svg": ("favicon.svg", "image/svg+xml")}
        expected.update({f"/fonts/{name}": (f"fonts/{name}", "font/woff2") for name in BOARD_FONTS})
        for path, (name, content_type) in expected.items():
            with self.subTest(path=path):
                response, body = self.public.request("GET", path)
                self.assertEqual(response.status, 200)
                self.assertEqual(body, (self.root / "annotator" / name).read_bytes())
                self.assertEqual(response.getheader("Content-Type"), content_type)
                head, head_body = self.public.request("HEAD", path)
                self.assertEqual((head.status, head_body), (200, b""))
                self.assertEqual(head.getheader("Content-Length"), str(len(body)))

    def test_a_whitelisted_file_that_is_missing_is_a_plain_404(self):
        response, body = self.public.request("GET", "/favicon-32.png")
        self.assertEqual(response.status, 404)
        self.assertNotIn(str(self.root).encode(), body)

    def test_every_other_path_is_404(self):
        for path in NOT_PUBLIC:
            for method in ("GET", "HEAD"):
                with self.subTest(path=path, method=method):
                    response, body = self.public.request(method, path)
                    self.assertEqual(response.status, 404)
                    self.assertNoSecrets(body, path)

    def test_raw_request_targets_http_client_would_refuse_are_404(self):
        for target in (b"/board.js\x00", b"/ops.js\t", b"/api/board\x7f", b"/fonts/\xff..\xff/ops.js"):
            with self.subTest(target=target):
                answer = self.public.raw(b"GET " + target + b" HTTP/1.1\r\nHost: board\r\n\r\n")
                self.assertRegex(answer, rb"^HTTP/1\.[01] (400|404) ")
                self.assertNoSecrets(answer, target)

    def test_any_other_method_is_405_on_any_path(self):
        for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "PROPFIND", "BREW"):
            for path in ("/", "/api/board", "/api/operations", "/ops.js"):
                with self.subTest(method=method, path=path):
                    response, body = self.public.request(method, path, {"Content-Type": "application/json"},
                                                         b'{"settings":{"public_board":false}}')
                    self.assertEqual(response.status, 405)
                    self.assertEqual(response.getheader("Allow"), "GET, HEAD")
                    self.assertNoSecrets(body, path)
        answer = self.public.raw(b"CONNECT 127.0.0.1:8130 HTTP/1.1\r\nHost: 127.0.0.1:8130\r\n\r\n")
        self.assertTrue(answer.startswith(b"HTTP/1.0 405 "), answer[:40])

    def test_security_headers_on_every_answer(self):
        for method, path in (("GET", "/"), ("GET", "/board.js"), ("HEAD", "/board.css"), ("GET", "/api/operations"),
                             ("GET", "/%2e%2e/ops.js"), ("POST", "/"), ("DELETE", "/api/board")):
            with self.subTest(method=method, path=path):
                response, _ = self.public.request(method, path)
                self.assertEqual(response.getheader("Content-Security-Policy"), BOARD_CSP)
                self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
                self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
                self.assertEqual(response.getheader("Referrer-Policy"), "no-referrer")
                self.assertEqual(response.getheader("Cross-Origin-Opener-Policy"), "same-origin")
                self.assertIn("camera=()", response.getheader("Permissions-Policy"))
                self.assertEqual(response.getheader("X-Robots-Tag"), "noindex, nofollow")
                self.assertNotIn("Python", response.getheader("Server") or "")

    def test_the_board_csp_is_the_decided_one(self):
        self.assertEqual(BOARD_CSP, "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; "
                                    "font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; "
                                    "object-src 'none'")

    def test_one_request_per_connection(self):
        # A pipelined second request is never read: an idle or smuggled request
        # cannot hold a slot or ride along.
        answer = self.public.raw(b"GET /board.css HTTP/1.1\r\nHost: b\r\n\r\nGET /ops.js HTTP/1.1\r\nHost: b\r\n\r\n")
        self.assertEqual(answer.count(b"HTTP/1."), 1)
        self.assertIn(b"body{color:#fff}", answer)
        self.assertNoSecrets(answer, "pipelined")

    def test_http_0_9_gets_nothing(self):
        # A 0.9 answer has no headers, so it would have no CSP either.
        self.assertEqual(self.public.raw(b"GET /\r\n\r\n"), b"")

    def test_the_public_pool_is_small_and_separate(self):
        self.assertTrue(issubclass(PublicBoardServer, BoundedHTTPServer))
        self.assertEqual(PublicBoardServer.max_handlers, 16)
        self.assertLess(PublicBoardServer.max_handlers, BoundedHTTPServer.max_handlers)
        operator = Loopback(BoundedHTTPServer, make_handler(self.backend))
        self.addCleanup(operator.close)
        # Sixteen clients that connect and say nothing hold all sixteen slots...
        idle = [socket.create_connection(("127.0.0.1", self.public.port), timeout=10) for _ in range(16)]
        try:
            # ...so, once the server has accepted them all, the next is told "busy" at once, not queued.
            deadline = time.monotonic() + 5
            while not self.public.raw(b"GET / HTTP/1.1\r\nHost: b\r\n\r\n").startswith(b"HTTP/1.0 503 "):
                self.assertLess(time.monotonic(), deadline, "a seventeenth client was not told busy")
                time.sleep(0.05)
            # The operator console, on its own pool, does not notice.
            response, body = operator.request("GET", "/display")
            self.assertEqual((response.status, body), (200, b"<!doctype html><title>board fixture</title>"))
        finally:
            for sock in idle:
                sock.close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.public.raw(b"GET / HTTP/1.1\r\nHost: b\r\n\r\n").startswith(b"HTTP/1.0 200 "):
                break
            time.sleep(0.05)
        else:
            self.fail("the public pool did not recover after its clients left")


class OperatorPortTest(unittest.TestCase):
    """The operator console serves the same page at /display, for a logged-in TV."""

    def test_display_and_its_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fixture_root(temp)
            operator = Loopback(BoundedHTTPServer, make_handler(Backend(root)))
            try:
                for path, name in (("/display", "board.html"), ("/board.js", "board.js"), ("/board.css", "board.css")):
                    with self.subTest(path=path):
                        response, body = operator.request("GET", path)
                        self.assertEqual(response.status, 200)
                        self.assertEqual(body, (root / "annotator" / name).read_bytes())
            finally:
                operator.close()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class PublicPortWiringTest(unittest.TestCase):
    """`unified_server.py --public-port` starts the second listener in the same process."""

    def test_public_port_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fixture_root(temp)
            port, public_port = free_port(), free_port()
            env = {key: value for key, value in os.environ.items() if key != "POOL_DATABASE_URL"}
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "annotator" / "unified_server.py"), "--root", str(root),
                 "--port", str(port), "--public-port", str(public_port)],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        socket.create_connection(("127.0.0.1", public_port), timeout=1).close()
                        break
                    except OSError:
                        if time.monotonic() > deadline or process.poll() is not None:
                            self.fail("the public listener never came up")
                        time.sleep(0.1)
                public = http.client.HTTPConnection("127.0.0.1", public_port, timeout=10)
                public.request("GET", "/")
                page = public.getresponse()
                self.assertEqual((page.status, page.read()), (200, b"<!doctype html><title>board fixture</title>"))
                public.close()
                public = http.client.HTTPConnection("127.0.0.1", public_port, timeout=10)
                public.request("GET", "/api/operations")
                refused = public.getresponse()
                self.assertEqual(refused.status, 404)
                public.close()
                operator = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                operator.request("GET", "/display")
                self.assertEqual(operator.getresponse().status, 200)
                operator.close()
            finally:
                process.terminate()
                output = process.communicate(timeout=10)[0]
            self.assertIn(f"Public board: http://127.0.0.1:{public_port}".encode(), output)


if __name__ == "__main__":
    unittest.main()
