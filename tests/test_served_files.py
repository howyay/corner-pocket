"""The file a route may serve, measured at the rule and at the three routes that use it.

src/served_files.py owns the rule. annotator/unified_server.py and annotator/server.py
call it. The legacy review server had three copies of the rule and its /ctx/ route had
none, so `GET /ctx/../../../<a file above the root>` answered 200 with that file. The
cases below send raw request lines, because urllib removes ".." before a request leaves
the process and the hole is only visible without that removal.
"""
import importlib
import socket
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.served_files import bare_name, file_under, relative_under  # noqa: E402

# annotator/server.py reads sys.argv while it loads, and the test runner puts its own
# arguments there. Load it with one argument, as a person who starts the file does.
_argv = sys.argv
sys.argv = [str(ROOT / 'annotator' / 'server.py')]
try:
    legacy = importlib.import_module('annotator.server')
finally:
    sys.argv = _argv


class ServedFileRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'root'
        self.root.mkdir()
        (self.root / 'a.jpg').write_bytes(b'inside')
        (self.root / 'folder').mkdir()
        self.outside = Path(self.tmp.name) / 'outside.txt'
        self.outside.write_bytes(b'outside')

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_bare_name_is_one_path_component(self):
        for name in ('a.jpg', 't00005_b01.jpg', 'with space.jpg'):
            self.assertTrue(bare_name(name), name)
        for name in ('', '.', '..', 'a/b', '../a', '/etc/hostname', 'folder/a.jpg'):
            self.assertFalse(bare_name(name), name)

    def test_the_rule_takes_a_file_inside_the_root_and_refuses_the_rest(self):
        self.assertEqual(file_under(self.root, 'a.jpg'), self.root / 'a.jpg')
        for name in ('missing.jpg', 'folder', '..', '../outside.txt', '/etc/hostname', ''):
            self.assertIsNone(file_under(self.root, name), name)
        self.assertEqual(relative_under(self.root, 'folder/../a.jpg'), self.root / 'a.jpg')
        for rel in ('../outside.txt', str(self.outside), '', 'missing/a.jpg'):
            self.assertIsNone(relative_under(self.root, rel), rel)

    def test_the_rule_does_not_follow_a_link_out_of_the_root(self):
        """A link inside the root that points outside it is not a file the rule takes.

        The link is made for real. A file system without symbolic links makes this case
        fail, which is the loud answer: a skip here would hide the rule on the day it
        matters.
        """
        link = self.root / 'link.txt'
        link.symlink_to(self.outside)
        self.assertTrue(link.exists())
        self.assertIsNone(file_under(self.root, 'link.txt'))
        self.assertIsNone(relative_under(self.root, 'link.txt'))


class ReviewApiRefusalTests(unittest.TestCase):
    """The two sentences the review API already sent to a client stay the same."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'media.jpg').write_bytes(b'inside')
        from annotator import unified_server
        self.unified = unified_server

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_name_with_a_separator_and_a_missing_name_keep_their_own_sentence(self):
        caught = {}
        for name, sentence in (('a/b.jpg', 'invalid media path'), ('media.jpg', None), ('missing.jpg', 'media not found')):
            if sentence is None:
                self.assertEqual(self.unified.safe_file(self.root, name), self.root / name)
                continue
            with self.assertRaises(self.unified.APIError) as caught_error:
                self.unified.safe_file(self.root, name)
            self.assertEqual((caught_error.exception.status, str(caught_error.exception)), (404, sentence))
            caught[name] = sentence
        self.assertEqual(len(caught), 2)


class LegacyRouteTests(unittest.TestCase):
    """The legacy review server answers a file inside its root and nothing above it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.served = base / 'served'
        (cls.served / 'crops' / 'ctx').mkdir(parents=True)
        (cls.served / 'img').mkdir()
        (cls.served / 'events.json').write_text('[]')
        (cls.served / 'crops' / 'meta.json').write_text('[]')
        (cls.served / 'crops' / 'labels.json').write_text('{}')
        (cls.served / 'crops' / 'one.jpg').write_bytes(b'crop-bytes')
        (cls.served / 'crops' / 'ctx' / 'real.png').write_bytes(b'ctx-bytes')
        (cls.served / 'img' / 'nested.png').write_bytes(b'nested-bytes')
        cls.outside = base / 'outside.txt'
        cls.outside.write_text('outside-bytes')
        cls.saved = {name: getattr(legacy, name) for name in
                     ('STATIC_ROOT', 'EVENTS_FILE', 'ANNOT_FILE', 'CROP_DIR', 'LABELS_FILE', 'LABEL_META')}
        legacy.STATIC_ROOT = cls.served
        legacy.EVENTS_FILE = cls.served / 'events.json'
        legacy.ANNOT_FILE = cls.served / 'annotations.json'
        legacy.CROP_DIR = cls.served / 'crops'
        legacy.LABELS_FILE = cls.served / 'crops' / 'labels.json'
        legacy.LABEL_META = cls.served / 'crops' / 'meta.json'
        cls.server = HTTPServer(('127.0.0.1', 0), legacy.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        for name, value in cls.saved.items():
            setattr(legacy, name, value)
        cls.tmp.cleanup()

    def answer(self, path):
        """Send the path as it is written: urllib would remove ".." first."""
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as sock:
            sock.sendall(f'GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nConnection: close\r\n\r\n'.encode())
            chunks = []
            while True:
                block = sock.recv(65536)
                if not block:
                    break
                chunks.append(block)
        head, _, body = b''.join(chunks).partition(b'\r\n\r\n')
        return int(head.split(b' ')[1]), body

    def test_each_route_answers_a_file_inside_its_own_root(self):
        for path, body in (('/ctx/real.png', b'ctx-bytes'), ('/crops/one.jpg', b'crop-bytes'),
                           ('/img/nested.png', b'nested-bytes'), ('/events.json', b'[]')):
            status, answered = self.answer(path)
            self.assertEqual((status, answered), (200, body), path)

    def test_no_route_answers_a_file_above_its_own_root(self):
        for path in ('/ctx/../../../outside.txt', '/crops/../outside.txt', '/ctx/../one.jpg',
                     '/../outside.txt', '/img/../../outside.txt'):
            status, body = self.answer(path)
            self.assertEqual(status, 404, (path, body))

    def test_the_ctx_route_keeps_its_file_and_refuses_the_names_that_leave_its_root(self):
        """A crop request names one file. The old copy of the rule also took a path
        that landed inside the root after ".." was resolved, and it took any path at
        all when the result stayed above the root."""
        status, body = self.answer('/ctx/real.png')
        self.assertEqual((status, body), (200, b'ctx-bytes'))
        status, body = self.answer('/ctx/../ctx/real.png')
        self.assertEqual(status, 404, body)
        status, body = self.answer('/ctx/../../../outside.txt')
        self.assertEqual(status, 404, body)


if __name__ == '__main__':
    unittest.main()
