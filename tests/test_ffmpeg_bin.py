"""The ffmpeg/ffprobe resolver (annotator/ffmpeg_bin.py) and its two call sites.

POOL_FFMPEG/POOL_FFPROBE win; a pin that points nowhere is a loud 503 that names the
variable, never a silent fallback to the unrooted Nix store glob.
"""
import contextlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from annotator import ffmpeg_bin
from annotator.ffmpeg_bin import (FFPROBE_VAR, FFMPEG_VAR, MediaBinaryMissing,
                                  resolve_ffmpeg, resolve_ffprobe)
from annotator.unified_server import APIError, Backend as ServerBackend
from annotator.vod_import import (VodImportError, VodImporter, default_ffmpeg_command,
                                  ffprobe_beside)


class ResolverCase(unittest.TestCase):
    """A fake PATH, a fake pinned build and a fake Nix store, all under one temp dir."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.on_path = self.bin_dir("path-bin")
        self.pinned = self.bin_dir("pinned")
        self.store = self.root / "store"
        self.store_bin = self.store / "aaa-ffmpeg-headless-9.0-bin" / "bin"
        self.store_bin.mkdir(parents=True)
        for name in ("ffmpeg", "ffprobe"):
            self.executable(self.store_bin / name)
        patcher = mock.patch.object(ffmpeg_bin, "STORE", self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def bin_dir(self, name, names=("ffmpeg", "ffprobe")):
        folder = self.root / name
        folder.mkdir()
        for binary in names:
            self.executable(folder / binary)
        return folder

    @staticmethod
    def executable(path):
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
        return path

    @contextlib.contextmanager
    def environment(self, **values):
        """No pins by default, PATH on the fake bin dir unless the test says otherwise."""
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in (FFMPEG_VAR, FFPROBE_VAR, "PATH"):
                os.environ.pop(key, None)
            os.environ["PATH"] = str(self.on_path)
            os.environ.update({key: str(value) for key, value in values.items()})
            yield

    def empty_store(self):
        empty = self.root / "empty-store"
        empty.mkdir(exist_ok=True)
        return mock.patch.object(ffmpeg_bin, "STORE", empty)


class ResolverTests(ResolverCase):
    def test_the_variable_wins_when_the_file_is_there(self):
        with self.environment(**{FFMPEG_VAR: self.pinned / "ffmpeg", FFPROBE_VAR: self.pinned / "ffprobe"}):
            self.assertEqual(resolve_ffmpeg(), str(self.pinned / "ffmpeg"))
            self.assertEqual(resolve_ffprobe(), str(self.pinned / "ffprobe"))

    def test_a_missing_pinned_ffmpeg_names_the_variable_and_does_not_fall_back(self):
        missing = self.pinned / "gone"
        with self.environment(**{FFMPEG_VAR: missing}):
            with self.assertRaises(MediaBinaryMissing) as raised:
                resolve_ffmpeg()
        self.assertIn(FFMPEG_VAR, str(raised.exception))
        self.assertIn(str(missing), str(raised.exception))

    def test_a_missing_pinned_ffprobe_names_the_variable(self):
        with self.environment(**{FFPROBE_VAR: self.pinned / "gone"}):
            with self.assertRaises(MediaBinaryMissing) as raised:
                resolve_ffprobe()
        self.assertIn(FFPROBE_VAR, str(raised.exception))

    def test_the_store_glob_is_the_fallback_when_the_variable_is_unset(self):
        with self.environment(PATH=""):
            self.assertEqual(resolve_ffmpeg(), str(self.store_bin / "ffmpeg"))
            self.assertEqual(resolve_ffprobe(), str(self.store_bin / "ffprobe"))

    def test_the_existing_default_path_still_wins_over_the_glob(self):
        with self.environment(), self.empty_store():
            self.assertEqual(resolve_ffmpeg(), str(self.on_path / "ffmpeg"))
            self.assertEqual(resolve_ffprobe(), str(self.on_path / "ffprobe"))

    def test_nothing_anywhere_is_a_loud_missing_binary(self):
        with self.environment(PATH=""), self.empty_store():
            with self.assertRaises(MediaBinaryMissing):
                resolve_ffmpeg()
            with self.assertRaises(MediaBinaryMissing):
                resolve_ffprobe()

    def test_ffprobe_is_the_sibling_of_the_resolved_ffmpeg(self):
        with self.environment(PATH=""), self.empty_store():
            self.assertEqual(resolve_ffprobe(beside=str(self.pinned / "ffmpeg")), str(self.pinned / "ffprobe"))

    def test_ffprobe_of_a_pinned_ffmpeg_is_its_own_sibling(self):
        with self.environment(**{FFMPEG_VAR: self.pinned / "ffmpeg"}):
            self.assertEqual(resolve_ffprobe(beside=resolve_ffmpeg()), str(self.pinned / "ffprobe"))


class CallSiteTests(ResolverCase):
    def test_the_clip_path_answers_503_naming_the_variable(self):
        with self.environment(**{FFMPEG_VAR: self.pinned / "gone"}):
            with self.assertRaises(APIError) as raised:
                ServerBackend._ffmpeg()
        self.assertEqual(raised.exception.status, 503)
        self.assertIn(FFMPEG_VAR, str(raised.exception))

    def test_the_clip_path_answers_503_when_no_ffmpeg_is_left(self):
        with self.environment(PATH=""), self.empty_store():
            with self.assertRaises(APIError) as raised:
                ServerBackend._ffmpeg()
        self.assertEqual(raised.exception.status, 503)

    def test_the_importer_default_ffmpeg_is_the_resolved_one(self):
        with self.environment(**{FFMPEG_VAR: self.pinned / "ffmpeg"}):
            importer = VodImporter(self.root, lambda: {})
            self.assertEqual(importer._ffmpeg(), [str(self.pinned / "ffmpeg")])
            self.assertEqual(ffprobe_beside(importer._ffmpeg()), str(self.pinned / "ffprobe"))

    def test_the_importer_default_ffmpeg_is_a_503_when_the_pin_is_broken(self):
        with self.environment(**{FFMPEG_VAR: self.pinned / "gone"}):
            importer = VodImporter(self.root, lambda: {})
            with self.assertRaises(VodImportError) as raised:
                importer._ffmpeg()
            with self.assertRaises(VodImportError):
                default_ffmpeg_command()
        self.assertEqual(raised.exception.status, 503)
        self.assertIn(FFMPEG_VAR, str(raised.exception))

    def test_the_importer_ffprobe_honours_its_own_variable(self):
        with self.environment(PATH="", **{FFPROBE_VAR: self.pinned / "ffprobe"}), self.empty_store():
            self.assertEqual(ffprobe_beside(["ffmpeg"]), str(self.pinned / "ffprobe"))

    def test_the_importer_ffprobe_is_a_503_when_its_pin_is_broken(self):
        with self.environment(**{FFPROBE_VAR: self.pinned / "gone"}):
            with self.assertRaises(VodImportError) as raised:
                ffprobe_beside(["ffmpeg"])
        self.assertEqual(raised.exception.status, 503)
        self.assertIn(FFPROBE_VAR, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
