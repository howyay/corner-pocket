"""scripts/fetch_weights.py accepts only the pinned bytes and leaves nothing behind.

No network: every download is a fake ``urlopen`` serving bytes from memory.
"""
import hashlib
import io
import os
import re
import tempfile
import unittest
from pathlib import Path

from scripts import fetch_weights as fw

GOOD = b"pinned weights " * 1000
GOOD_SHA = hashlib.sha256(GOOD).hexdigest()
URL = "https://example.invalid/weights.pt"


def serving(body):
    calls = []

    def urlopen(request, timeout=None):
        calls.append(request.full_url)
        return io.BytesIO(body)
    return urlopen, calls


def refusing(request, timeout=None):
    raise OSError("network down")


class FetchTests(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name) / "weights"
        self.dest = self.dir / "model.pt"

    def names(self):
        return sorted(p.name for p in self.dir.iterdir()) if self.dir.exists() else []

    def test_the_pinned_bytes_are_accepted(self):
        urlopen, calls = serving(GOOD)
        self.assertEqual(fw.fetch(self.dest, URL, GOOD_SHA, len(GOOD), urlopen), "downloaded")
        self.assertEqual(self.dest.read_bytes(), GOOD)
        self.assertEqual(calls, [URL])
        self.assertEqual(self.names(), ["model.pt"], "no temporary file is left")
        umask = os.umask(0)
        os.umask(umask)
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o666 & ~umask,
                         "the same mode a plain open() would give")

    def test_wrong_bytes_are_refused_and_deleted(self):
        urlopen, _ = serving(GOOD[:-1] + b"X")
        with self.assertRaises(fw.ChecksumError):
            fw.fetch(self.dest, URL, GOOD_SHA, len(GOOD), urlopen)
        self.assertEqual(self.names(), [], "neither the file nor a partial copy exists")

    def test_a_stream_longer_than_the_pin_is_refused(self):
        urlopen, _ = serving(GOOD + b"more")
        with self.assertRaises(fw.ChecksumError):
            fw.fetch(self.dest, URL, GOOD_SHA, len(GOOD), urlopen)
        self.assertEqual(self.names(), [])

    def test_a_network_failure_leaves_nothing(self):
        with self.assertRaises(OSError):
            fw.fetch(self.dest, URL, GOOD_SHA, len(GOOD), refusing)
        self.assertEqual(self.names(), [])

    def test_a_correct_present_file_is_skipped(self):
        self.dir.mkdir()
        self.dest.write_bytes(GOOD)
        urlopen, calls = serving(b"never read")
        self.assertEqual(fw.fetch(self.dest, URL, GOOD_SHA, len(GOOD), urlopen), "present")
        self.assertEqual(calls, [], "nothing is downloaded")
        self.assertEqual(self.dest.read_bytes(), GOOD)

    def test_a_wrong_present_file_is_replaced_only_by_the_pinned_bytes(self):
        self.dir.mkdir()
        self.dest.write_bytes(b"truncated")
        with self.assertRaises(fw.ChecksumError):
            fw.fetch(self.dest, URL, GOOD_SHA, len(GOOD), serving(b"also wrong")[0])
        self.assertEqual(self.dest.read_bytes(), b"truncated", "a failed fetch changes nothing")
        self.assertEqual(self.names(), ["model.pt"])
        self.assertEqual(fw.fetch(self.dest, URL, GOOD_SHA, len(GOOD), serving(GOOD)[0]), "replaced")
        self.assertEqual(self.dest.read_bytes(), GOOD)
        self.assertEqual(self.names(), ["model.pt"])


class PinTests(unittest.TestCase):

    def test_every_weight_is_pinned_in_full(self):
        paths = [rel for rel, *_ in fw.WEIGHTS]
        self.assertEqual(paths, ["yolov8n.pt", "src/reid/weights/osnet_x0_25_msmt17.pth"],
                         "the paths the code loads from")
        for rel, url, sha256, size in fw.WEIGHTS:
            self.assertRegex(sha256, r"^[0-9a-f]{64}$", rel)
            self.assertTrue(url.startswith("https://"), rel)
            self.assertGreater(size, 0, rel)
        hf_url = fw.WEIGHTS[1][1]
        self.assertRegex(hf_url, r"^https://huggingface\.co/kaiyangzhou/osnet/resolve/[0-9a-f]{40}/")
        self.assertIsNone(re.search(r"/resolve/main/", hf_url), "pinned to a commit, not main")

    def test_downloads_verify_certificates(self):
        context = fw.tls_context()
        self.assertEqual(context.verify_mode, fw.ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_local_copies_match_the_pins(self):
        for rel, _, sha256, size in fw.WEIGHTS:
            path = fw.ROOT / rel
            if not path.is_file():
                continue  # a fresh clone before scripts/fetch_weights.py
            with self.subTest(rel):
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(fw.sha256_of(path), sha256)


if __name__ == "__main__":
    unittest.main()
