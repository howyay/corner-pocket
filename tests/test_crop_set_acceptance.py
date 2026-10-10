"""A crop set the owner names is accepted; a set it does not name is refused.

These tests drive the real read and write paths after the vocabulary moved to one
owner: the JSON store under a temporary root, and the console's ball-set route. They
pin the refusal text, the HTTP status and the on-disk bytes, so the move changed no
behaviour. The names come from the owner, so the tests follow the owner tuple.
"""
import tempfile
import unittest
from pathlib import Path

from annotator.unified_server import APIError, Backend, ReadQuery
from src.store import JsonStore
from src.store_files import BALL_SETS

# No owner names this set. It is close to a real name on purpose: a guard that reads
# a prefix, or that accepts any name of the same shape, passes this set by accident.
UNKNOWN = "unlabeled_crops3"


class JsonStoreLabels(unittest.TestCase):
    """The store's write and read path for one crop set's labels.json."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = JsonStore(self.root)

    def test_a_named_set_is_written_and_read_back_byte_for_byte(self):
        path = self.root / "out" / "unlabeled_crops2" / "labels.json"
        self.assertFalse(path.exists(), "the test writes the first copy of this file")
        self.store.label_put("unlabeled_crops2", "crop.png", 7)
        self.assertEqual(path.read_bytes(), b'{\n  "crop.png": 7\n}\n',
                         "the on-disk layout is unchanged: indent=2, one trailing newline")
        self.assertEqual(self.store.labels_get("unlabeled_crops2"), {"crop.png": 7})

    def test_every_name_the_owner_lists_is_accepted_and_written(self):
        for name in BALL_SETS:
            self.store.label_put(name, "crop.png", "u")
            self.assertEqual(self.store.labels_get(name), {"crop.png": "u"})
            self.assertTrue((self.root / "out" / name / "labels.json").is_file(),
                            f"the store must write a file for the named set {name}")

    def test_a_set_the_owner_does_not_name_is_refused_unchanged(self):
        for call in (lambda: self.store.label_put(UNKNOWN, "crop.png", 7),
                     lambda: self.store.labels_get(UNKNOWN)):
            with self.assertRaises(ValueError) as caught:
                call()
            self.assertEqual(str(caught.exception), f"unknown ball set: {UNKNOWN}",
                             "the refusal text of the store is unchanged")
        self.assertFalse((self.root / "out").exists(),
                         "a refused set must not create a directory or a file")


class ConsoleBallSetRoute(unittest.TestCase):
    """The console route that turns a ball-set name into a crop directory."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.backend = Backend(self.root)

    def test_a_named_set_is_accepted_and_an_unnamed_set_is_a_404(self):
        self.assertEqual(self.backend.crops("vod30_event_crops"),
                         self.root / "out" / "vod30_event_crops")
        with self.assertRaises(APIError) as caught:
            self.backend.crops(UNKNOWN)
        self.assertEqual((str(caught.exception), caught.exception.status),
                         ("unknown ball set", 404),
                         "the refusal of the console route is unchanged")

    def test_the_dataset_listing_offers_the_owner_names_in_the_owner_order(self):
        listed = self.backend.get(["api", "datasets"], ReadQuery({}))
        self.assertEqual(listed["ball_sets"],
                         [{"id": name, "label": name} for name in BALL_SETS],
                         "the listing must offer the owner names, in the owner order")


if __name__ == "__main__":
    unittest.main()
