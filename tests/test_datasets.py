"""The dataset registry (src/datasets.py): built-in ids, imported ids, safe paths, pure reads."""
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import dataset_id_cases
from annotator import live_processing
from src import datasets, enroll_from_tracklet
from src.datasets import imported_id, listing, lookup, parse_imported_id, read_index

ENTRY = {"vod_id": "1000000001", "channel": "examplechannel", "title": "Friday 8-ball",
         "created_at": "2026-09-19T01:02:03Z", "length_s": 13400, "fps": 30.0, "frames": 9000,
         "width": 1280, "height": 720, "bytes": 123456789, "imported_at": "2026-09-28T00:00:00+00:00"}


def tree_stamp(root):
    """Every path under root with its bytes and mtime: what a read must never change."""
    stamp = {}
    for folder, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(folder) / name
            if path.is_file():
                stamp[str(path)] = (hashlib.md5(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            else:
                stamp[str(path)] = "dir"
    return stamp


class DatasetRegistryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def write_index(self, vods):
        path = self.root / "out" / "vods" / "index.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"vods": vods}))
        return path

    def test_built_in_recordings_keep_their_folders_and_media(self):
        self.assertEqual(datasets.STATIC_OUT, {"vod30": "scan30", "highlight": "scan_highlight"})
        vod30, highlight = lookup(self.root, "vod30"), lookup(self.root, "highlight")
        self.assertEqual((vod30.kind, vod30.out_dir, vod30.media_dir, vod30.media_name),
                         ("recording", self.root / "out" / "scan30", self.root / "data", "vod_30min_260815.mp4"))
        self.assertEqual((highlight.out_dir, highlight.media_name),
                         (self.root / "out" / "scan_highlight", "vod_highlight.mp4"))
        self.assertIsNone(vod30.media_file())
        (self.root / "data").mkdir()
        (self.root / "data" / "vod_30min_260815.mp4").write_bytes(b"mp4")
        self.assertEqual(vod30.media_file(), (self.root / "data" / "vod_30min_260815.mp4").resolve())

    def test_built_in_ids_never_read_the_index(self):
        self.write_index("damaged")
        with patch.object(datasets, "read_index", side_effect=AssertionError("index read")):
            self.assertEqual(lookup(self.root, "vod30").kind, "recording")
            self.assertEqual(lookup(self.root, "highlight").kind, "recording")

    def test_imported_ids_are_built_from_numbers_only(self):
        self.assertEqual(imported_id(1000000001), "tw-1000000001")
        self.assertEqual(imported_id("1000000001", 3600, 3900), "tw-1000000001-3600-3900")
        self.assertEqual(imported_id("1000000001", 3600.0, 3900.0), "tw-1000000001-3600-3900")
        for bad in (0, -1, True, 1.5, "abc", "12a", "1" * 13, "../1", "１２", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                imported_id(bad)
        for start, end in ((10, 10), (10, 5), (-1, 5), (1.5, 9), (None, 9), (1, None), (True, 9)):
            with self.assertRaises(ValueError, msg=repr((start, end))):
                imported_id("1", start, end)

    def test_only_canonical_ids_parse(self):
        self.assertEqual(parse_imported_id("tw-1000000001"), ("1000000001", None, None))
        self.assertEqual(parse_imported_id("tw-1000000001-3600-3900"), ("1000000001", 3600, 3900))
        for bad in ("tw-0123", "tw-1-9-5", "tw-1-01-5", "tw-1\n", "tw-1-1", "TW-1", "tw-", "vod30",
                    "../tw-1", "tw-1/..", "tw-" + "1" * 13, "tw-1-1-" + "9" * 60, "", None, 7):
            self.assertIsNone(parse_imported_id(bad), repr(bad))

    def test_an_imported_vod_resolves_only_while_the_index_lists_it(self):
        key = "tw-1000000001-3600-3900"
        self.assertIsNone(lookup(self.root, key))
        self.write_index({key: ENTRY})
        found = lookup(self.root, key)
        self.assertEqual((found.kind, found.out_dir, found.media_dir, found.media_name),
                         ("vod", self.root / "out" / "vods" / key, self.root / "data" / "vods", key + ".mp4"))
        self.assertIsNone(found.media_file())
        media = self.root / "data" / "vods" / (key + ".mp4")
        media.parent.mkdir(parents=True)
        media.write_bytes(b"mp4")
        self.assertEqual(found.media_file(), media.resolve())
        self.assertIsNone(lookup(self.root, "tw-1000000001"))       # the whole VOD is another id
        self.write_index({})
        self.assertIsNone(lookup(self.root, key))                  # deleted from the index: unknown
        with self.assertRaises(TypeError):
            lookup(self.root, ["vod30"])                            # as `in DATASETS` always did

    def test_media_that_escapes_its_folder_is_refused(self):
        key = "tw-5"
        self.write_index({key: dict(ENTRY, vod_id="5")})
        outside = self.root / "secret.mp4"
        outside.write_bytes(b"x")
        (self.root / "data" / "vods").mkdir(parents=True)
        (self.root / "data" / "vods" / "tw-5.mp4").symlink_to(outside)
        self.assertIsNone(lookup(self.root, key).media_file())
        (self.root / "data" / "vods" / "tw-5.mp4").unlink()
        (self.root / "data" / "vods" / "tw-5.mp4").mkdir()            # a folder is not media
        self.assertIsNone(lookup(self.root, key).media_file())

    def test_the_index_is_read_honestly(self):
        self.assertEqual(read_index(self.root), ({}, None))
        path = self.write_index({})
        path.write_text("{not json")
        entries, error = read_index(self.root)
        self.assertEqual(entries, {})
        self.assertIn("not valid JSON", error)
        path.write_text(json.dumps(["tw-1"]))
        self.assertIn("no 'vods' object", read_index(self.root)[1])
        self.write_index({"tw-1": dict(ENTRY, vod_id="1"), "tw-01": dict(ENTRY, vod_id="1"),
                          "tw-2": dict(ENTRY, vod_id="3"), "../x": {}, "tw-4": "text"})
        entries, error = read_index(self.root)
        self.assertEqual(list(entries), ["tw-1"])
        self.assertEqual(error, "4 entries in out/vods/index.json are not valid and not listed")

    def test_media_path_names_the_file_before_it_exists(self):
        self.assertEqual(datasets.media_path(self.root, "vod30"),
                         self.root / "data" / "vod_30min_260815.mp4")
        self.assertEqual(datasets.media_relpath(self.root, "vod30"), "data/vod_30min_260815.mp4")
        self.assertEqual(datasets.media_path(self.root, "highlight"),
                         self.root / "data" / "vod_highlight.mp4")
        for unknown in ("tw-9", "nope", "../scan30", None):
            self.assertIsNone(datasets.media_path(self.root, unknown), repr(unknown))
            self.assertIsNone(datasets.media_relpath(self.root, unknown), repr(unknown))

    def test_media_path_resolves_an_imported_vod_while_it_is_listed(self):
        key = "tw-1000000001-3600-3900"
        self.assertIsNone(datasets.media_path(self.root, key))
        self.write_index({key: ENTRY})
        self.assertEqual(datasets.media_path(self.root, key),
                         self.root / "data" / "vods" / (key + ".mp4"))
        self.assertEqual(datasets.media_relpath(self.root, key), "data/vods/" + key + ".mp4")

    def test_listing_keeps_the_built_in_rows_and_describes_imports(self):
        rows, error = listing(self.root)
        self.assertEqual((rows, error), ([{"id": "vod30", "label": "vod30"},
                                          {"id": "highlight", "label": "highlight"}], None))
        self.write_index({"tw-1000000001-3600-3900": ENTRY, "tw-7": dict(ENTRY, vod_id="7", length_s=60)})
        rows, error = listing(self.root)
        self.assertIsNone(error)
        self.assertEqual([row["id"] for row in rows], ["vod30", "highlight", "tw-1000000001-3600-3900", "tw-7"])
        row = rows[2]
        self.assertEqual(row["label"], "examplechannel · 2026-09-19 · 1:00:00–1:05:00")
        self.assertEqual((row["kind"], row["vod_id"], row["channel"], row["title"]),
                         ("vod", "1000000001", "examplechannel", "Friday 8-ball"))
        self.assertEqual(row["range"], {"start_s": 3600, "end_s": 3900, "whole": False})
        self.assertEqual((row["fps"], row["frames"], row["width"], row["height"], row["media"]),
                         (30.0, 9000, 1280, 720, False))
        self.assertEqual(rows[3]["range"], {"start_s": 0, "end_s": 60, "whole": True})
        self.assertTrue(rows[3]["label"].endswith("whole broadcast"))

    def test_reading_never_writes(self):
        key = "tw-1000000001-3600-3900"
        before = tree_stamp(self.root)
        for dataset_id in ("vod30", "highlight", key, "tw-9", "nope", "../x"):
            lookup(self.root, dataset_id)
        listing(self.root)
        read_index(self.root)
        self.assertEqual(tree_stamp(self.root), before)
        self.assertFalse((self.root / "out").exists())              # not even a folder
        self.write_index({key: ENTRY})
        before = tree_stamp(self.root)
        for dataset_id in ("vod30", key, "tw-9"):
            found = lookup(self.root, dataset_id)
            if found is not None:
                found.media_file()
        listing(self.root)
        self.assertEqual(tree_stamp(self.root), before)
        self.assertFalse((self.root / "out" / "vods" / key).exists())
        self.assertFalse((self.root / "data").exists())


class DatasetIdGrammarTests(unittest.TestCase):
    """The rule a dataset column applies, run over the corpus of ``tests/dataset_id_cases``.

    This side of the boundary is Python. The other side is the SQL of
    ``db/migrations/0004_imported_datasets.sql``; ``tests/test_db.py`` runs the same corpus
    through ``dataset_id_ok`` when a database is configured.
    """

    @staticmethod
    def verdict(text):
        """What a dataset column accepts: a published name, or one canonical imported id."""
        return text in dataset_id_cases.BUILT_IN or parse_imported_id(text) is not None

    def test_every_spelling_gets_the_verdict_the_rule_gives(self):
        for text, expected in dataset_id_cases.CASES:
            with self.subTest(text=repr(text)):
                self.assertEqual(self.verdict(text), expected,
                                 f"the rule gives {expected} for {text!r}")

    def test_the_published_names_are_the_registrys_own(self):
        self.assertEqual(sorted(dataset_id_cases.BUILT_IN), sorted(datasets.STATIC_OUT))

    def test_the_published_names_are_the_only_spelling_the_two_readings_differ_on(self):
        """``dataset_id_ok`` guards every dataset column, so it also covers the two names.

        ``parse_imported_id`` parses imported ids only. Every other spelling must get the
        same verdict from both readings, and this states where they may differ.
        """
        for text, _ in dataset_id_cases.CASES:
            with self.subTest(text=repr(text)):
                if parse_imported_id(text) is not None:
                    self.assertFalse(text in dataset_id_cases.BUILT_IN,
                                     f"{text!r} is both an imported id and a published name")


class BuiltInMediaNameTests(unittest.TestCase):
    """A built-in media file name is spelled once: in ``src.datasets.STATIC``.

    The live source (``annotator/live_processing.py``) and the enrollment tool
    (``src/enroll_from_tracklet.py``) both replay those two files, and both read their
    file names from that one registry.  A name typed again in either module could drift
    from the file the registry resolves.  The offline scan and calibration tools that
    also name these files are outside this refactor and are not asserted here.
    """

    #: module -> the one constant there that maps a built-in id to its media file.
    consumers = (("annotator/live_processing.py", "_DATASETS"),
                 ("src/enroll_from_tracklet.py", "DATASETS"))

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def source(self, relative):
        return (Path(__file__).resolve().parents[1] / relative).read_text()

    def test_the_registry_is_where_the_two_file_names_are_spelled(self):
        self.assertEqual({key: value[1] for key, value in datasets.STATIC.items()},
                         {"vod30": "vod_30min_260815.mp4", "highlight": "vod_highlight.mp4"})

    def test_the_registry_spells_each_name_once(self):
        source = self.source("src/datasets.py")
        for dataset_id, (scan, media) in datasets.STATIC.items():
            self.assertEqual(source.count(media), 1,
                             "src/datasets.py spells %s %d times" % (media, source.count(media)))

    def test_no_consumer_spells_a_media_file_name(self):
        for dataset_id, (scan, media) in datasets.STATIC.items():
            for relative, constant in self.consumers:
                self.assertTrue(media not in self.source(relative),
                                "%s names %s instead of reading it from STATIC"
                                % (relative, media))

    def test_each_consumer_computes_its_mapping_from_the_registry(self):
        for relative, constant in self.consumers:
            values = [node.value for node in ast.walk(ast.parse(self.source(relative)))
                      if isinstance(node, ast.Assign) and len(node.targets) == 1
                      and isinstance(node.targets[0], ast.Name)
                      and node.targets[0].id == constant]
            self.assertEqual(len(values), 1, "%s must define %s exactly once" % (relative, constant))
            names = {node.id for node in ast.walk(values[0]) if isinstance(node, ast.Name)}
            self.assertIn("STATIC", names,
                          "%s must take %s from src.datasets.STATIC" % (relative, constant))

    def test_both_consumers_resolve_the_same_two_media_paths(self):
        (self.root / "data").mkdir()
        for dataset_id, (scan, media) in datasets.STATIC.items():
            from_registry = datasets.media_path(self.root, dataset_id).resolve()
            self.assertEqual(from_registry, self.root / "data" / media)
            self.assertEqual((self.root / "data" / media).resolve(), from_registry)
            self.assertEqual(datasets.media_relpath(self.root, dataset_id), "data/" + media)
            # The live source keeps the bare file name and joins it under data/ ...
            self.assertEqual(live_processing._DATASETS[dataset_id], media)
            self.assertEqual((self.root / "data" / live_processing._DATASETS[dataset_id]).resolve(),
                             from_registry)
            # ... and enrollment keeps the data/-prefixed path it joins onto a root.
            self.assertEqual(enroll_from_tracklet.DATASETS[dataset_id], "data/" + media)
            self.assertEqual((self.root / enroll_from_tracklet.DATASETS[dataset_id]).resolve(),
                             from_registry)
            (self.root / "data" / media).touch()
        # Both modules describe exactly the registry's built-in ids, no more and no fewer.
        self.assertEqual(sorted(live_processing._DATASETS), sorted(datasets.STATIC))
        self.assertEqual(sorted(enroll_from_tracklet.DATASETS), sorted(datasets.STATIC))
        # The live source itself hands out the registry's path for a built-in id.
        processor = live_processing.LiveProcessor(self.root)
        for dataset_id in datasets.STATIC:
            source, path = processor._source_media({"kind": "dataset", "dataset": dataset_id})
            self.assertEqual(source, {"kind": "dataset", "dataset": dataset_id})
            self.assertEqual(path, str(datasets.media_path(self.root, dataset_id).resolve()))


class RegistryConsumerTests(unittest.TestCase):
    """The server and the JSON store resolve every dataset through the registry."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.key = "tw-1000000001-3600-3900"
        path = self.root / "out" / "vods" / "index.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"vods": {self.key: ENTRY}}))

    def test_server_resolves_built_in_and_imported_datasets(self):
        from annotator.unified_server import APIError, Backend, ReadQuery
        backend = Backend(self.root)
        self.assertEqual(backend.dataset("vod30"), self.root / "out" / "scan30")
        self.assertEqual(backend.dataset(self.key), self.root / "out" / "vods" / self.key)
        for unknown in ("tw-9", "nope", "../scan30", None):
            with self.assertRaises(APIError) as caught:
                backend.dataset(unknown)
            self.assertEqual(caught.exception.status, 404)
        with self.assertRaises(APIError) as caught:
            backend.video(self.key)                                  # listed, media not there yet
        self.assertEqual((caught.exception.status, str(caught.exception)), (404, "media not found"))
        listed = backend.get(["api", "datasets"], ReadQuery())
        self.assertEqual([row["id"] for row in listed["datasets"]], ["vod30", "highlight", self.key])
        self.assertNotIn("datasets_error", listed)
        (self.root / "out" / "vods" / "index.json").write_text("{")
        listed = backend.get(["api", "datasets"], ReadQuery())
        self.assertEqual([row["id"] for row in listed["datasets"]], ["vod30", "highlight"])
        self.assertIn("not valid JSON", listed["datasets_error"])

    def test_json_store_keeps_an_imported_vods_corrections_in_its_own_folder(self):
        from src.store import JsonStore
        store = JsonStore(self.root)
        store.correction_put(self.key, 12, {"balls": [], "saved_at": "now"})
        self.assertEqual(store.correction_get(self.key, 12), {"balls": [], "saved_at": "now"})
        saved = self.root.resolve() / "out" / "vods" / self.key / "frame_results" / "12" / "correction.json"
        self.assertTrue(saved.is_file())
        self.assertEqual(store.verdicts_get(self.key), {})
        with self.assertRaises(ValueError):
            store.correction_put("tw-9", 1, {})                      # not in the index
        with self.assertRaises(ValueError):
            store.seeds_get(self.key)                               # seeds stay vod30-only


if __name__ == "__main__":
    unittest.main()
