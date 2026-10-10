"""Guard and behavior tests for src/atomic_write.py, the only atomic writer.

The AST guard fails when a module in src/ or annotator/ builds a temp file and
calls os.replace itself. The behavior tests hold the bytes and the options that
the nine call sites had before the change.
"""
from __future__ import annotations

import ast
import importlib
import json
import locale
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import annotator.shot_clock as shot_clock_module
import annotator.unified_server as unified_server
import annotator.vod_import as vod_import
import src.atomic_write as atomic_write
import src.enroll_from_tracklet as enroll_from_tracklet
import src.face_id as face_id
import src.person_identity as person_identity
import src.store as store_module
import src.store_export as store_export

ROOT = Path(__file__).resolve().parents[1]
write_atomic = atomic_write.write_atomic

# The owner of the decision. annotator/operations.py is the tenth writer: a
# different change moves it. Remove that line when the change lands.
EXEMPT = {ROOT / "src" / "atomic_write.py", ROOT / "annotator" / "operations.py"}

SITE_MODULES = [
    "src.face_id",
    "src.store_export",
    "src.person_identity",
    "src.store",
    "src.enroll_from_tracklet",
    "annotator.shot_clock",
    "annotator.vod_import",
    "annotator.unified_server",
]

# (module, qualified function name) for each of the nine call sites.
CALL_SITES = [
    ("src.face_id", "store_faces"),
    ("src.store_export", "_atomic_write"),
    ("src.person_identity", "IdentityIndex.save"),
    ("src.store", "_write"),
    ("src.store", "JsonStore.identity_save"),
    ("src.enroll_from_tracklet", "_write_json"),
    ("annotator.shot_clock", "ShotClock._save"),
    ("annotator.vod_import", "_atomic_json"),
    ("annotator.unified_server", "atomic_save"),
]

DIRECT_TEMP_CALLS = {
    "tempfile.mkstemp",
    "tempfile.NamedTemporaryFile",
    "tempfile.mkdtemp",
    "mkstemp",
    "NamedTemporaryFile",
    "mkdtemp",
}
PATH_BUILDERS = {"open", "Path", "pathlib.Path"}


def _dotted(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _tmp_strings(node) -> list:
    """Every string piece that holds ".tmp" inside one expression."""
    return [sub.value for sub in ast.walk(node)
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and ".tmp" in sub.value]


def _os_replace_lines(tree) -> list:
    """Line numbers of os.replace: an attribute, or a name imported from os."""
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            imported |= {alias.asname or alias.name for alias in node.names if alias.name == "replace"}
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "replace" and _dotted(node.value) == "os":
            lines.append(node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in imported:
            lines.append(node.lineno)
    return lines


class _TempFinder(ast.NodeVisitor):
    """Finds a temp file that this module builds itself."""

    def __init__(self):
        self.evidence = []

    def visit_Call(self, node):
        name = _dotted(node.func)
        if name in DIRECT_TEMP_CALLS:
            self.evidence.append((node.lineno, f"{name}(...)"))
        elif name.endswith((".with_name", ".with_suffix")) or name in PATH_BUILDERS:
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                for text in _tmp_strings(arg):
                    self.evidence.append((node.lineno, f"{name}(... {text!r} ...)"))
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.Add):
            for text in _tmp_strings(node):
                self.evidence.append((node.lineno, f"a name built with {text!r}"))
        self.generic_visit(node)


def _temp_lines(tree) -> list:
    finder = _TempFinder()
    finder.visit(tree)
    return sorted(finder.evidence)


def _source_files():
    for base in ("src", "annotator"):
        yield from sorted((ROOT / base).rglob("*.py"))


def _resolve_node(tree, qualname):
    scopes = [tree]
    for part in qualname.split("."):
        found = []
        for holder in scopes:
            for node in holder.body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == part:
                    found.append(node)
        if not found:
            return None
        scopes = found
    return scopes[0]


def _calls_write_atomic(node) -> bool:
    return any(isinstance(sub, ast.Call) and _dotted(sub.func).endswith("write_atomic")
               for sub in ast.walk(node))


class TestNoSecondWriter(unittest.TestCase):
    """The guard: one module owns the temp-file + os.replace decision."""

    def test_no_other_module_builds_a_temp_file_for_os_replace(self):
        offenders = []
        for path in _source_files():
            if path in EXEMPT:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            replaces = _os_replace_lines(tree)
            temps = _temp_lines(tree)
            if replaces and temps:
                where = ", ".join(f"{path.relative_to(ROOT)}:{line} {what}"
                                  for line, what in temps + [(line, "os.replace") for line in replaces])
                offenders.append(where)
        self.assertEqual([], offenders,
                         "these modules write a file atomically without src.atomic_write:\n  "
                         + "\n  ".join(offenders))

    def test_every_call_site_uses_the_owner_function_by_identity(self):
        for name in SITE_MODULES:
            with self.subTest(module=name):
                module = importlib.import_module(name)
                self.assertIs(atomic_write.write_atomic, getattr(module, "write_atomic", None),
                              f"{name} must import the owner function, not a copy")

    def test_every_call_site_calls_the_owner_inside_its_own_function(self):
        for name, qualname in CALL_SITES:
            with self.subTest(module=name, function=qualname):
                path = ROOT / (name.replace(".", "/") + ".py")
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                node = _resolve_node(tree, qualname)
                self.assertIsNotNone(node, f"{qualname} is missing from {name}")
                self.assertTrue(_calls_write_atomic(node),
                                f"{name}.{qualname} does not call write_atomic")


class TestOwnerBehavior(unittest.TestCase):
    """The owner module: bytes, failure, fsync, temp names, encoding."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="atomic-write-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.path = self.dir / "state.json"

    def _siblings(self):
        return sorted(p.name for p in self.dir.iterdir())

    def test_a_successful_call_writes_the_bytes_and_returns_the_path(self):
        def write(stream):
            stream.write("hello\n")

        result = write_atomic(self.path, write)
        self.assertEqual(self.path, result)
        self.assertEqual("hello\n", self.path.read_text())
        self.assertEqual(["state.json"], self._siblings(), "no temp file stays")

    def test_a_reader_inside_the_write_sees_the_old_bytes(self):
        self.path.write_text("old")
        seen = []

        def write(stream):
            stream.write("new")
            stream.flush()
            seen.append(self.path.read_text())
            seen.append(self._siblings())

        write_atomic(self.path, write)
        self.assertEqual("old", seen[0], "a half file must not appear at the target")
        self.assertEqual(2, len(seen[1]), "the new bytes go to a temp file beside the target")
        self.assertIn("state.json", seen[1])
        self.assertTrue([n for n in seen[1] if n != "state.json"][0].startswith(".state.json"))
        self.assertEqual("new", self.path.read_text())

    def test_a_failure_keeps_the_old_file_and_removes_the_temp(self):
        self.path.write_text("old")

        def write(stream):
            stream.write("new")
            raise ValueError("serialization failed")

        with self.assertRaises(ValueError):
            write_atomic(self.path, write)
        self.assertEqual("old", self.path.read_text())
        self.assertEqual(["state.json"], self._siblings())

    def test_remove_on_failure_false_keeps_the_temp_file(self):
        self.path.write_text("old")

        def write(stream):
            stream.write("new")
            raise ValueError("serialization failed")

        with self.assertRaises(ValueError):
            write_atomic(self.path, write, temp_name="{name}.tmp{pid}", remove_on_failure=False)
        self.assertEqual("old", self.path.read_text())
        self.assertEqual(sorted(["state.json", f"state.json.tmp{os.getpid()}"]), self._siblings())

    def test_a_failure_in_the_replace_keeps_the_old_file_and_removes_the_temp(self):
        self.path.write_text("old")
        with mock.patch("src.atomic_write.os.replace", side_effect=OSError("cross-device")):
            with self.assertRaises(OSError):
                write_atomic(self.path, lambda stream: stream.write("new"))
        self.assertEqual("old", self.path.read_text())
        self.assertEqual(["state.json"], self._siblings())

    def test_fsync_true_calls_os_fsync_and_false_does_not(self):
        for flag, expected in ((True, 1), (False, 0)):
            with self.subTest(fsync=flag):
                with mock.patch("src.atomic_write.os.fsync", wraps=os.fsync) as spy:
                    write_atomic(self.path, lambda stream: stream.write("x"), fsync=flag)
                self.assertEqual(expected, spy.call_count)
                self.assertEqual("x", self.path.read_text())

    def test_fsync_is_called_before_the_replace(self):
        order = []
        real_fsync, real_replace = os.fsync, os.replace
        with mock.patch("src.atomic_write.os.fsync", side_effect=lambda fd: order.append("fsync") or real_fsync(fd)):
            with mock.patch("src.atomic_write.os.replace",
                            side_effect=lambda a, b: order.append("replace") or real_replace(a, b)):
                write_atomic(self.path, lambda stream: stream.write("x"), fsync=True)
        self.assertEqual(["fsync", "replace"], order)

    def test_temp_prefix_goes_to_mkstemp(self):
        with mock.patch("src.atomic_write.tempfile.mkstemp", wraps=tempfile.mkstemp) as spy:
            write_atomic(self.path, lambda stream: stream.write("x"), temp_prefix=".state-")
        self.assertEqual(".state-", spy.call_args.kwargs["prefix"])
        self.assertEqual(self.dir, Path(spy.call_args.kwargs["dir"]))

    def test_temp_name_holds_name_stem_and_pid(self):
        self.assertEqual(self.dir / "state.json.tmp7",
                         atomic_write._sibling_path(self.path, "{name}.tmp7"))
        self.assertEqual(self.dir / "state.json.tmp", 
                         atomic_write._sibling_path(self.path, "{stem}.json.tmp"))
        self.assertEqual(self.dir / f"state.json.tmp{os.getpid()}",
                         atomic_write._sibling_path(self.path, "{name}.tmp{pid}"))

    def test_two_temp_names_at_once_are_an_error(self):
        with self.assertRaises(ValueError):
            write_atomic(self.path, lambda stream: stream.write("x"),
                         temp_prefix=".a-", temp_name="{name}.tmp")

    def test_a_missing_parent_directory_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            write_atomic(self.dir / "missing" / "state.json", lambda stream: stream.write("x"))

    def test_the_default_encoding_is_the_platform_default(self):
        write_atomic(self.path, lambda stream: stream.write("héllo"))
        self.assertEqual("héllo".encode(locale.getencoding()), self.path.read_bytes())

    def test_an_explicit_encoding_is_used(self):
        write_atomic(self.path, lambda stream: stream.write("héllo"), encoding="utf-8")
        self.assertEqual("héllo".encode(), self.path.read_bytes())


class TestCallerFormats(unittest.TestCase):
    """The bytes each call site wrote before the change stay the same."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="atomic-callers-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def test_store_export_writes_the_text_verbatim(self):
        path = self.dir / "export.json"
        store_export._atomic_write(path, '{"a": 1}')
        self.assertEqual(b'{"a": 1}', path.read_bytes())
        self.assertEqual(["export.json"], sorted(p.name for p in self.dir.iterdir()))

    def test_unified_server_atomic_save_uses_indent_2_and_a_newline(self):
        path = self.dir / "state.json"
        unified_server.atomic_save(path, {"a": 1})
        self.assertEqual((json.dumps({"a": 1}, indent=2, allow_nan=False) + "\n").encode(), path.read_bytes())

    def test_store_write_uses_indent_2_and_a_newline(self):
        path = self.dir / "state.json"
        store_module._write(path, {"a": 1})
        self.assertEqual((json.dumps({"a": 1}, indent=2, allow_nan=False) + "\n").encode(), path.read_bytes())

    def test_vod_import_uses_indent_2_sort_keys_and_a_newline(self):
        path = self.dir / "index.json"
        vod_import._atomic_json(path, {"b": 1, "a": 2})
        self.assertEqual((json.dumps({"b": 1, "a": 2}, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(),
                         path.read_bytes())

    def test_shot_clock_uses_indent_2_and_a_newline(self):
        path = self.dir / "clock.json"
        shot_clock_module.ShotClock(path)._save({"seq": 3})
        self.assertEqual((json.dumps({"seq": 3}, indent=2, allow_nan=False) + "\n").encode(), path.read_bytes())
        self.assertEqual(["clock.json"], sorted(p.name for p in self.dir.iterdir()))

    def test_enroll_from_tracklet_uses_indent_2_and_a_newline(self):
        path = self.dir / "store.json"
        enroll_from_tracklet._write_json(path, {"a": 1})
        self.assertEqual((json.dumps({"a": 1}, indent=2, allow_nan=False) + "\n").encode(), path.read_bytes())

    def test_face_id_uses_indent_1_and_no_newline(self):
        import src.face_id as module
        path = self.dir / "faces.json"
        gallery = {"p1": [{"embedding": np.zeros(module.EMBEDDING_DIM, np.float32), "eye_px": 12.0,
                           "det_score": 0.9, "created_at": "2026-01-01T00:00:00+00:00", "source": "t"}]}
        stored = module.store_faces(path, gallery)
        self.assertEqual(json.dumps(stored, indent=1).encode(), path.read_bytes())
        self.assertFalse(path.read_bytes().endswith(b"\n"))
        self.assertEqual(["faces.json"], sorted(p.name for p in self.dir.iterdir()))

    def test_store_identity_save_uses_indent_1_and_no_newline(self):
        store = store_module.JsonStore(self.dir)
        store.identity_save({"c1": {"player_id": "p1"}})
        path = store.identity_path()
        self.assertEqual(json.dumps({"c1": {"player_id": "p1"}}, indent=1).encode(), path.read_bytes())
        self.assertFalse(path.read_bytes().endswith(b"\n"))

    def test_person_identity_save_uses_json_dump_indent_1(self):
        path = self.dir / "identity.json"
        index = person_identity.IdentityIndex(path)
        calls = []
        real_dump = json.dump

        def recorder(obj, stream, **kwargs):
            calls.append((obj, kwargs))
            return real_dump(obj, stream, **kwargs)

        with mock.patch("src.person_identity.json.dump", recorder):
            index.save()
        self.assertEqual(1, len(calls))
        self.assertEqual({"indent": 1}, calls[0][1])
        self.assertEqual(json.dumps(calls[0][0], indent=1).encode(), path.read_bytes())

    def test_no_call_site_leaves_a_temp_file_after_a_successful_write(self):
        store = store_module.JsonStore(self.dir)
        store.identity_save({})
        paths = [self.dir / "export.json", self.dir / "server.json", self.dir / "vod.json",
                 self.dir / "clock.json", self.dir / "enroll.json"]
        store_export._atomic_write(paths[0], "x")
        unified_server.atomic_save(paths[1], {})
        vod_import._atomic_json(paths[2], {})
        shot_clock_module.ShotClock(paths[3])._save({})
        enroll_from_tracklet._write_json(paths[4], {})
        left = [p.name for p in self.dir.rglob("*") if p.is_file() and ".tmp" in p.name]
        self.assertEqual([], left)


class TestCallerDurability(unittest.TestCase):
    """A durable site waits for the disk. A best effort site does not.

    The owner holds both behaviours, so only the call site decides which one a
    write gets. A dropped `fsync=True` leaves the bytes correct, and a bytes
    test cannot see it. Each drive below runs the real write path of one site,
    and the two role lists cover the nine sites in CALL_SITES.
    """

    DURABLE = (
        "src.store_export._atomic_write",
        "src.store._write",
        "annotator.shot_clock.ShotClock._save",
        "annotator.vod_import._atomic_json",
        "annotator.unified_server.atomic_save",
    )
    BEST_EFFORT = (
        "src.face_id.store_faces",
        "src.person_identity.IdentityIndex.save",
        "src.store.JsonStore.identity_save",
        "src.enroll_from_tracklet._write_json",
    )

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="atomic-durable-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def _drives(self):
        gallery = {"p1": [{"embedding": np.zeros(face_id.EMBEDDING_DIM, np.float32), "eye_px": 12.0,
                           "det_score": 0.9, "created_at": "2026-01-01T00:00:00+00:00", "source": "t"}]}
        return {
            "src.face_id.store_faces": lambda: face_id.store_faces(self.dir / "faces.json", gallery),
            "src.store_export._atomic_write": lambda: store_export._atomic_write(self.dir / "export.json", "{}"),
            "src.person_identity.IdentityIndex.save":
                lambda: person_identity.IdentityIndex(self.dir / "identity.json").save(),
            "src.store._write": lambda: store_module._write(self.dir / "state.json", {}),
            "src.store.JsonStore.identity_save":
                lambda: store_module.JsonStore(self.dir).identity_save({}),
            "src.enroll_from_tracklet._write_json":
                lambda: enroll_from_tracklet._write_json(self.dir / "enroll.json", {}),
            "annotator.shot_clock.ShotClock._save":
                lambda: shot_clock_module.ShotClock(self.dir / "clock.json")._save({}),
            "annotator.vod_import._atomic_json": lambda: vod_import._atomic_json(self.dir / "vod.json", {}),
            "annotator.unified_server.atomic_save": lambda: unified_server.atomic_save(self.dir / "server.json", {}),
        }

    def test_the_two_role_lists_cover_every_call_site(self):
        drives = self._drives()
        self.assertEqual(sorted(f"{module}.{name}" for module, name in CALL_SITES), sorted(drives))
        self.assertEqual(sorted(drives), sorted(self.DURABLE + self.BEST_EFFORT))

    def test_each_site_keeps_the_durability_it_had_before_the_change(self):
        real = os.fsync
        for name, drive in self._drives().items():
            with self.subTest(site=name):
                calls = []
                with mock.patch("src.atomic_write.os.fsync", side_effect=lambda fd: calls.append(fd) or real(fd)):
                    drive()
                self.assertEqual(name in self.DURABLE, bool(calls),
                                 f"{name}: fsync called {len(calls)} times, and this site is "
                                 f"{'durable' if name in self.DURABLE else 'best effort'}")


if __name__ == "__main__":
    unittest.main()
