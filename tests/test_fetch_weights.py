"""scripts/fetch_weights.py accepts only the pinned bytes and leaves nothing behind.

`src/weight_pins.py` owns the pin table, so the script and this module read one
object.  `NOTICE` is the human-readable licence statement, and it states the same
URL, the same SHA-256 and the same size for every weight.  The `NoticeTests` cases
parse both files and compare them in both directions, so a change on either side
fails here.

No network: every download is a fake ``urlopen`` serving bytes from memory.
"""
import copy
import hashlib
import io
import os
import re
import ssl
import tempfile
import unittest
from pathlib import Path

from scripts import fetch_weights as fw
from src import weight_pins
from src.tls_trust import trusted_context

GOOD = b"pinned weights " * 1000
GOOD_SHA = hashlib.sha256(GOOD).hexdigest()
URL = "https://example.invalid/weights.pt"
NOTICE = fw.ROOT / "NOTICE"

# The field names of the two NOTICE shapes: a `Download:` URL on one line, or a
# `repository` name, a `revision` and a `file` name on three lines.
_FIELD = re.compile(r"\s*(SHA-256|Size|Download|repository|revision|file|size)[:\s]\s*(\S.*?)\s*$")
_REVISION = re.compile(r"[0-9a-f]{40}$")


def _blank_entry():
    """One NOTICE entry before any of its fields is read."""
    return {"repository": None, "url": None, "sha256": None, "size": None,
            "revision": None, "file": None}


def _fields_in_notice(text):
    """Every (field, value) pair of NOTICE, in the order of the file."""
    found = []
    for line in text.splitlines():
        match = _FIELD.match(line)
        if match is not None:
            found.append((match.group(1), match.group(2)))
    return found


def _entries_in_notice(text):
    """The pinned-file statements of NOTICE, in the order of the file.

    A `Download:` line starts an entry and states its URL.  The OSNet statement
    gives the URL in parts instead: a `repository` line opens a group, a
    `revision` line names the commit, and the `file` line after them closes the
    entry, whose URL this module rebuilds.  A group with no file, or a `file`
    line outside a group, is prose, and this function drops it.
    """
    entries = []
    current, revision, repository = None, None, None
    for _, (field, value) in enumerate(_fields_in_notice(text)):
        if field == "Download":
            current = _blank_entry()
            current["url"] = value
            entries.append(current)
            revision = None
        elif field == "SHA-256" and current is not None:
            current["sha256"] = value
        elif field in ("Size", "size") and current is not None:
            current["size"] = value
        elif field == "repository":
            current, revision, repository = None, None, value
        elif field == "revision":
            revision = value if _REVISION.match(value) else None
        elif field == "file" and revision is not None:
            current = _blank_entry()
            current.update(repository=repository, revision=revision, file=value)
            entries.append(current)
    return entries


def _byte_count(text):
    """`6,549,796 bytes` -> 6549796.  None when the entry states no count."""
    words = (text or "").split()
    digits = re.sub(r"[^0-9]", "", words[0]) if words else ""
    return int(digits) if digits else None


def _notice_url(entry):
    """The one URL an entry states, from either of the two shapes."""
    if entry["url"] is not None:
        return entry["url"]
    if entry["repository"] and entry["revision"] and entry["file"]:
        return (f"https://huggingface.co/{entry['repository']}/resolve/"
                f"{entry['revision']}/{entry['file']}")
    return None


def _drift_notes(pin, entry):
    """The ways in which one pin and one NOTICE entry disagree: empty when they agree."""
    rel, url, sha256, size = pin
    notes = []
    if _notice_url(entry) != url:
        notes.append(f"{rel}: URL {url} != NOTICE {_notice_url(entry)}")
    if entry["sha256"] != sha256:
        notes.append(f"{rel}: SHA-256 {sha256} != NOTICE {entry['sha256']}")
    if _byte_count(entry["size"]) != size:
        notes.append(f"{rel}: size {size} != NOTICE {entry['size']}")
    return notes


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

    def test_the_script_reads_the_one_owner_table(self):
        self.assertIs(fw.WEIGHTS, weight_pins.WEIGHT_PINS,
                      "scripts/fetch_weights.py must not keep a second copy of the pin table")

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
        context = trusted_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_local_copies_match_the_pins(self):
        for rel, _, sha256, size in fw.WEIGHTS:
            path = fw.ROOT / rel
            if not path.is_file():
                continue  # a fresh clone before scripts/fetch_weights.py
            with self.subTest(rel):
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(fw.sha256_of(path), sha256)


class NoticeTests(unittest.TestCase):
    """NOTICE and src/weight_pins.py must state the same pin.  This is the guard."""

    @classmethod
    def setUpClass(cls):
        cls.entries = _entries_in_notice(NOTICE.read_text(encoding="utf-8"))
        cls.by_url = {_notice_url(entry): entry for entry in cls.entries}

    def entry_for(self, pin):
        """The NOTICE entry that states the URL of `pin`, or a failure that names it."""
        entry = self.by_url.get(pin[1])
        self.assertIsNotNone(
            entry, f"{pin[0]}: NOTICE states no pinned file at {pin[1]}; NOTICE states "
                   f"{sorted(str(url) for url in self.by_url)}")
        return entry

    def test_notice_states_one_entry_per_pin(self):
        self.assertEqual(
            len(self.entries), len(weight_pins.WEIGHT_PINS),
            f"NOTICE states {len(self.entries)} pinned files and src/weight_pins.py holds "
            f"{len(weight_pins.WEIGHT_PINS)}: {sorted(str(url) for url in self.by_url)}")

    def test_notice_states_no_unpinned_entry(self):
        pinned = {pin[1] for pin in weight_pins.WEIGHT_PINS}
        extras = [str(_notice_url(entry)) for entry in self.entries
                  if _notice_url(entry) not in pinned]
        self.assertEqual(extras, [], "NOTICE states a pinned file that src/weight_pins.py does not hold")

    def test_the_yolov8n_pin_matches_notice(self):
        pin = weight_pins.WEIGHTS_BY_PATH["yolov8n.pt"]
        entry = self.entry_for(pin)
        self.assertEqual(entry["url"], pin[1], "the yolov8n entry must state the URL, not a repository")
        self.assertEqual(_drift_notes(pin, entry), [],
                         "the yolov8n pin in src/weight_pins.py and NOTICE disagree")

    def test_the_osnet_pin_matches_notice(self):
        pin = weight_pins.WEIGHTS_BY_PATH[weight_pins.OSNET]
        entry = self.entry_for(pin)
        self.assertEqual(weight_pins.OSNET_REVISION, entry["revision"],
                         "NOTICE must name the pinned commit")
        self.assertEqual(weight_pins.OSNET_FILENAME, entry["file"],
                         "NOTICE must name the pinned file")
        self.assertEqual(weight_pins.OSNET_REPO, f"https://huggingface.co/{entry['repository']}",
                         "NOTICE must name the pinned repository")
        self.assertEqual(_drift_notes(pin, entry), [],
                         "the OSNet pin in src/weight_pins.py and NOTICE disagree")

    def test_an_unknown_url_is_not_silently_accepted(self):
        unknown = ("src/reid/weights/not_pinned.pth", "https://example.invalid/not_pinned.pth",
                   "0" * 64, 1)
        with self.assertRaises(AssertionError):
            self.entry_for(unknown)

    def test_a_planted_url_drift_is_seen(self):
        pin = weight_pins.WEIGHTS_BY_PATH[weight_pins.OSNET]
        self.assertEqual(_drift_notes(pin, self.entry_for(pin)), [],
                         "NOTICE must agree before this plant, or the plant proves nothing")
        entry = copy.deepcopy(self.entry_for(pin))
        entry["revision"] = "b" * 40
        notes = _drift_notes(pin, entry)
        self.assertEqual(len(notes), 1, f"one changed revision must give one note: {notes}")
        self.assertIn("URL", notes[0])
        self.assertIn("b" * 40, notes[0], "the note names the NOTICE revision")
        self.assertIn(weight_pins.OSNET_REVISION, notes[0], "the note names the pinned revision")

    def test_a_planted_sha256_drift_is_seen(self):
        pin = weight_pins.WEIGHTS_BY_PATH["yolov8n.pt"]
        self.assertEqual(_drift_notes(pin, self.entry_for(pin)), [],
                         "NOTICE must agree before this plant, or the plant proves nothing")
        entry = copy.deepcopy(self.entry_for(pin))
        entry["sha256"] = "0" * 64
        notes = _drift_notes(pin, entry)
        self.assertEqual(len(notes), 1, f"one changed digest must give one note: {notes}")
        self.assertIn("SHA-256", notes[0])
        self.assertIn("0" * 64, notes[0], "the note names the NOTICE digest")

    def test_a_planted_size_drift_is_seen(self):
        pin = weight_pins.WEIGHTS_BY_PATH["yolov8n.pt"]
        self.assertEqual(_drift_notes(pin, self.entry_for(pin)), [],
                         "NOTICE must agree before this plant, or the plant proves nothing")
        entry = copy.deepcopy(self.entry_for(pin))
        entry["size"] = f"{pin[3] + 1:,} bytes"
        notes = _drift_notes(pin, entry)
        self.assertEqual(len(notes), 1, f"one changed size must give one note: {notes}")
        self.assertIn("size", notes[0])
        self.assertIn(f"{pin[3] + 1:,}", notes[0], "the note names the NOTICE byte count")

    def test_a_perturbed_pin_table_is_seen_for_every_entry(self):
        """The check reads the owner table, so a perturbation there fails in the same way."""
        pins = copy.deepcopy(weight_pins.WEIGHT_PINS)
        pins = (pins[0], ("src/weights/elsewhere.pth", pins[1][1], "f" * 64, pins[1][3] + 1))
        notes = []
        for pin in pins:
            entry = self.by_url.get(pin[1])
            self.assertIsNotNone(entry, f"{pin[0]}: NOTICE states no pinned file at {pin[1]}")
            notes.extend(_drift_notes(pin, entry))
        self.assertEqual(len(notes), 2,
                         f"a moved path and a changed size, digests equal here: {notes}")


def serving(body):
    calls = []

    def urlopen(request, timeout=None):
        calls.append(request.full_url)
        return io.BytesIO(body)
    return urlopen, calls


def refusing(request, timeout=None):
    raise OSError("network down")


if __name__ == "__main__":
    unittest.main()
