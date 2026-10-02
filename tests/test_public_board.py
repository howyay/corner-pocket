"""The read-only public board (docs/public-board.md): its own listener, at the root or
under --public-prefix.

The public listener (--public-port) answers GET/HEAD of a fixed set of paths and
nothing else; --public-prefix mounts that same surface under one path, e.g. /board, so
the board can live on the console's own hostname behind a path-scoped Access bypass.
The one spelling that is not the mounted page is the bare prefix itself: /board answers
308 to /board/, because a document whose URL is /board resolves its relative assets
outside the mount (/board.js). Each test runs the real handlers behind loopback sockets
over a temporary root; no repository data is read or written.
"""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from annotator.unified_server import (BOARD_CSP, BOARD_FILES, BOARD_FONTS, Backend, BoundedHTTPServer,
                                      PublicBoardServer, board_prefix, make_handler, make_public_handler)

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


#: With --public-prefix /board: everything the prefix does not admit, spelled exactly as
#: a client would send it. The prefix is a mount, not a rewrite: nothing outside it is
#: served, and the boundary is a real "/", so "/boardx" is not the prefix.
PREFIXED_NOT_PUBLIC = (
    # The operator API and media under the prefix: the whitelist is still the whole surface.
    "/board/api/operations", "/board/api/unified", "/board/api/live/frame", "/board/media/vod30/video",
    # The same surface without the prefix: the root mount is closed when a prefix is set.
    "/", "/board.js", "/board.css", "/api/board", "/favicon.svg", "/fonts/barlow-500.woff2", "/display",
    "//board/board.js", "/boardx/board.js", "/boardx", "/%62oard/board.js", "/BOARD/board.js", "/board.",
    # Traversal and near-misses inside the prefix, as sent: no decoding, no normalisation.
    "/board/../api/operations", "/board/api/board/../operations", "/board//api/board", "/board/api//board",
    "/board/./board.js", "/board/%2e/board.js", "/board/%2e%2e/annotator/ops.js", "/board/api/board/",
    "/board/ops.js", "/board/board.html", "/board/index.html", "/board/BOARD.js", "/board/board.js/",
    "/board/fonts/", "/board/fonts", "/board/fonts/OFL-Barlow.txt", "/board/fonts/zilla-slab-400.woff2",
    "/board/fonts/../board.js", "/board/fonts/..%2fops.js", "/board/api/board%00", "/board/api/board#/api/board",
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


class NoSecrets:
    """Shared by both listener suites: no answer may carry a file the public must not see."""

    def assertNoSecrets(self, body, path):
        for secret in SECRETS:
            self.assertNotIn(secret, body, path)


class PublicListenerTest(NoSecrets, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.backend = Backend(self.root)
        self.public = Loopback(PublicBoardServer, make_public_handler(self.backend))
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.public.close)

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

    def test_a_bare_prefix_is_not_a_redirect_without_a_prefix(self):
        # Without --public-prefix there is no mount to complete: /board is one more
        # unknown path, exactly as it was before the prefix existed.
        for path in ("/board", "/board/", "/board?lang=zh", "/board/api/board"):
            with self.subTest(path=path):
                response, body = self.public.request("GET", path)
                self.assertEqual(response.status, 404)
                self.assertIsNone(response.getheader("Location"))
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


def get(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def get_headers(port, path):
    """(status, Location, body), for the one answer that is a 308."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.getheader("Location"), response.read()
    finally:
        connection.close()


def wait_for_port(port, process):
    deadline = time.monotonic() + 20
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return
        except OSError:
            if time.monotonic() > deadline or process.poll() is not None:
                raise AssertionError("the public listener never came up")
            time.sleep(0.1)


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
                wait_for_port(public_port, process)
                self.assertEqual(get(public_port, "/"),
                                 (200, b"<!doctype html><title>board fixture</title>"))
                self.assertEqual(get(public_port, "/api/operations")[0], 404)
                self.assertEqual(get(port, "/display")[0], 200)
            finally:
                process.terminate()
                output = process.communicate(timeout=10)[0]
            self.assertIn(f"Public board: http://127.0.0.1:{public_port}".encode(), output)


class PublicPrefixWiringTest(unittest.TestCase):
    """`unified_server.py --public-prefix /board` mounts the surface there and closes the
    root, in the same process as the console."""

    def test_the_prefix_is_mounted_and_the_root_is_not(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fixture_root(temp)
            port, public_port = free_port(), free_port()
            env = {key: value for key, value in os.environ.items() if key != "POOL_DATABASE_URL"}
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "annotator" / "unified_server.py"), "--root", str(root),
                 "--port", str(port), "--public-port", str(public_port), "--public-prefix", "/board"],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                wait_for_port(public_port, process)
                self.assertEqual(get_headers(public_port, "/board"), (308, "/board/", b""))
                self.assertEqual(get(public_port, "/board/"),
                                 (200, b"<!doctype html><title>board fixture</title>"))
                status, body = get(public_port, "/board/api/board")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["board"], "on")
                for path in ("/", "/board.js", "/api/board", "/boardx/board.js", "/board/api/operations",
                             "/board/../api/operations"):
                    with self.subTest(path=path):
                        self.assertEqual(get(public_port, path)[0], 404)
                self.assertEqual(get(port, "/display")[0], 200)
            finally:
                process.terminate()
                output = process.communicate(timeout=10)[0]
            self.assertIn(f"Public board: http://127.0.0.1:{public_port}/board/".encode(), output)


class PublicPrefixTest(NoSecrets, unittest.TestCase):
    """`--public-prefix /board`: the same surface, mounted under one path."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture_root(self.temp.name)
        self.backend = Backend(self.root)
        self.public = Loopback(PublicBoardServer, make_public_handler(self.backend, "/board"))
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.public.close)

    def test_the_prefix_serves_the_whole_surface(self):
        expected = {"/board/": ("board.html", "text/html; charset=utf-8"),
                    "/board/?lang=zh": ("board.html", "text/html; charset=utf-8"),
                    "/board/board.js": ("board.js", "text/javascript; charset=utf-8"),
                    "/board/board.css": ("board.css", "text/css; charset=utf-8"),
                    "/board/favicon.svg": ("favicon.svg", "image/svg+xml")}
        expected.update({f"/board/fonts/{name}": (f"fonts/{name}", "font/woff2") for name in BOARD_FONTS})
        for path, (name, content_type) in expected.items():
            with self.subTest(path=path):
                response, body = self.public.request("GET", path)
                self.assertEqual(response.status, 200)
                self.assertEqual(body, (self.root / "annotator" / name).read_bytes())
                self.assertEqual(response.getheader("Content-Type"), content_type)
                head, head_body = self.public.request("HEAD", path)
                self.assertEqual((head.status, head_body), (200, b""))
                self.assertEqual(head.getheader("Content-Length"), str(len(body)))

    def test_the_bare_prefix_redirects_to_the_mounted_page(self):
        # /board is not the page: an asset URL relative to it lands outside the mount.
        # The one answer that moves a client to the canonical URL is a 308, with no body
        # a browser would render.
        for method in ("GET", "HEAD"):
            with self.subTest(method=method):
                response, body = self.public.request(method, "/board")
                self.assertEqual(response.status, 308)
                self.assertEqual(response.getheader("Location"), "/board/")
                self.assertEqual((response.getheader("Content-Length"), body), ("0", b""))
                self.assertNotIn("text/html", response.getheader("Content-Type") or "")

    def test_the_redirect_carries_the_query_through_verbatim(self):
        # The query is never read, only carried: the bytes that arrived after the "?" are
        # the bytes in Location, so a shared ?lang=zh link survives the bare form.
        for path, location in (("/board?lang=zh", "/board/?lang=zh"),
                               ("/board?x=1&y=%2e%2e", "/board/?x=1&y=%2e%2e"),
                               ("/board?/../ops.js", "/board/?/../ops.js"),
                               ("/board?", "/board/?")):
            with self.subTest(path=path):
                response, body = self.public.request("GET", path)
                self.assertEqual((response.status, response.getheader("Location")), (308, location))
                self.assertEqual(body, b"")

    def test_only_the_exact_bare_prefix_redirects(self):
        # The mount is still matched as a string, as sent: a near-miss of the bare prefix
        # is an unknown path, never a redirect to somewhere it did not ask for.
        for path in ("/boardx", "/board.", "/board/.", "/BOARD", "/%62oard", "//board",
                     "/board/", "/board/board.js", "/board/../board"):
            with self.subTest(path=path):
                status = self.public.request("GET", path)[0]
                self.assertNotIn(status, (301, 302, 303, 307, 308))

    def test_the_cache_rule_follows_the_file_not_the_prefix(self):
        for path, cache in (("/board/fonts/barlow-500.woff2", "public, max-age=86400"),
                            ("/board/favicon.svg", "public, max-age=86400"),
                            ("/board/", "no-cache"), ("/board/board.js", "no-cache"),
                            ("/board/api/board", "no-cache")):
            with self.subTest(path=path):
                response, _ = self.public.request("GET", path)
                self.assertEqual(response.getheader("Cache-Control"), cache)

    def test_the_api_is_mounted_with_its_etag(self):
        response, body = self.public.request("GET", "/board/api/board")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(json.loads(body)["board"], "on")
        etag = response.getheader("ETag")
        self.assertTrue(etag.startswith('W/"'), etag)
        again, nothing = self.public.request("GET", "/board/api/board", {"If-None-Match": etag})
        self.assertEqual((again.status, nothing), (304, b""))
        head, head_body = self.public.request("HEAD", "/board/api/board")
        self.assertEqual((head.status, head_body), (200, b""))

    def test_everything_outside_the_prefix_is_404(self):
        for path in PREFIXED_NOT_PUBLIC:
            for method in ("GET", "HEAD"):
                with self.subTest(path=path, method=method):
                    response, body = self.public.request(method, path)
                    self.assertEqual(response.status, 404)
                    self.assertNoSecrets(body, path)

    def test_raw_targets_under_the_prefix_are_404(self):
        for target in (b"/board/board.js\x00", b"/board/ops.js\t", b"/board/api/board\x7f",
                       b"/board/fonts/\xff..\xff/ops.js"):
            with self.subTest(target=target):
                answer = self.public.raw(b"GET " + target + b" HTTP/1.1\r\nHost: board\r\n\r\n")
                self.assertRegex(answer, rb"^HTTP/1\.[01] (400|404) ")
                self.assertNoSecrets(answer, target)

    def test_any_other_method_is_405_under_the_prefix(self):
        for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "PROPFIND"):
            for path in ("/board", "/board/", "/board/api/board", "/board/board.js", "/board/api/operations"):
                with self.subTest(method=method, path=path):
                    response, body = self.public.request(method, path, {"Content-Type": "application/json"},
                                                         b'{"settings":{"public_board":false}}')
                    self.assertEqual(response.status, 405)
                    self.assertEqual(response.getheader("Allow"), "GET, HEAD")
                    self.assertNoSecrets(body, path)

    def test_the_security_headers_are_the_same_under_the_prefix(self):
        for method, path in (("GET", "/board/"), ("GET", "/board"), ("GET", "/board/board.js"),
                             ("HEAD", "/board/api/board"), ("GET", "/board/api/operations"), ("POST", "/board/")):
            with self.subTest(method=method, path=path):
                response, _ = self.public.request(method, path)
                self.assertEqual(response.getheader("Content-Security-Policy"), BOARD_CSP)
                self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
                self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
                self.assertEqual(response.getheader("Referrer-Policy"), "no-referrer")
                self.assertEqual(response.getheader("X-Robots-Tag"), "noindex, nofollow")
                self.assertNotIn("Python", response.getheader("Server") or "")


class BoardPrefixTest(unittest.TestCase):
    """--public-prefix is validated where it enters the process: a typo must not mount the
    board nowhere, or somewhere wider than it looks."""

    def test_a_plain_path_is_taken_as_written(self):
        self.assertEqual(board_prefix("/board"), "/board")
        self.assertEqual(board_prefix("/board/"), "/board")
        self.assertEqual(board_prefix("/a/b"), "/a/b")

    def test_nothing_and_the_root_mean_the_root_mount(self):
        for value in ("", "/", "//", None):
            with self.subTest(value=value):
                self.assertEqual(board_prefix(value), "")

    def test_a_prefix_that_would_need_guessing_is_refused(self):
        for value in ("board", " board", "/board ", "/board\t", "/bo ard", "//board", "/board//x",
                      "/board/../x", "/board/.", "/board%2Fx", "/board?x=1", "/board#x", "/board\\x", 7):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    board_prefix(value)

    def test_the_handler_refuses_a_prefix_it_cannot_match(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend(fixture_root(temp))
            for value in ("board", "/board/../x"):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        make_public_handler(backend, value)


class TheBoardOffersItsSource(unittest.TestCase):
    """AGPL-3.0 section 13, for the one listener that has no account in front of it.

    The board is a network service anyone can reach, and the program serving it embeds an
    AGPL-3.0 component (ultralytics; see NOTICE), so the page it answers with has to offer
    that program's source. The offer is the footer link; these tests pin it to the file the
    public listener actually serves (`BOARD_FILES["/"]` -> `annotator/board.html`), in both
    languages, so a future edit cannot quietly drop it.
    """

    def test_the_page_the_public_listener_serves_offers_the_source(self):
        page = (ROOT / "annotator" / BOARD_FILES["/"]).read_text(encoding="utf-8")
        self.assertIn('id="source-link"', page)
        self.assertIn('href="https://github.com/howyay/corner-pocket"', page)

    def test_the_offer_is_translated_and_styled(self):
        script = (ROOT / "annotator" / "board.js").read_text(encoding="utf-8")
        self.assertIn("['source-link', 'source']", script)
        self.assertEqual(script.count("source: '"), 2, "English and 中文 both name the source")
        self.assertIn(".source a", (ROOT / "annotator" / "board.css").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
