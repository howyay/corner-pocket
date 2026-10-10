"""Tests for the owner of the SAM3 ball artifact.

The artifact `out/scan30/sam3_results.json` was declared read-only in
`src/sam3_ball_cache.py` and in `src/eval_events.py`, while
`src/scan_events.py` and `src/rebuild_events_calibrated.py` rewrote it in place.
The file named no producer, so no reader could tell a `table_mm` that the camera
model measured from one that `out/calib_final.json` recomputed.  For the file of
2026-09-03 every one of the 270 rows equals the calibrated recompute.

These tests hold the four callers to `src/sam3_artifact.py`.  Two whole-scope
source guards fail by file and line: one when a scope module names the file
itself, and one when a scope module rewrites the path the owner named without
going through `sam3_artifact.write`.  The read tests hold a read to the bytes of
the file it read.
"""
import ast
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import data_guard

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import sam3_artifact  # noqa: E402
from src.sam3_artifact import (ARTIFACT, CAMERA_MODEL, MIXED, PRODUCERS,  # noqa: E402
                               REBUILD_CALIBRATED, ROW_KEYS, STAMP, STAMPED,
                               UNSTAMPED, VERSION, ArtifactShapeError,
                               ArtifactVersionError)

ROOT = Path(__file__).resolve().parents[1]
OWNER = "src/sam3_artifact.py"

#: The four callers of the owner: the two writers and the two declared readers.
SCOPE = (
    "src/scan_events.py",
    "src/rebuild_events_calibrated.py",
    "src/sam3_ball_cache.py",
    "src/eval_events.py",
)

#: A code string that names the artifact but is not this artifact, with the
#: reason it may stay.  The key is (module, the string).  The guard fails when a
#: key stops matching a string in that module.  The table is empty: no call in
#: scope has a reason to name the file, because the owner names it.
OTHER_ARTIFACT_FILES = {}

#: The calls of the owner that return a path.  A module that binds one of these
#: calls to a name holds the artifact path, and a JSON write into that name is a
#: rewrite of the artifact in place.
OWNER_PATH_CALLS = ("sam3_artifact.artifact_path", "sam3_artifact.artifact_in")

#: The two members of the scope that hold the artifact path, and the write that
#: each one is allowed to make through the owner.
PRODUCER_WRITES = {
    CAMERA_MODEL: ("sam3_artifact.write(",),
    REBUILD_CALIBRATED: ("sam3_artifact.write(",),
}

ROW = {"img": [640.0, 360.0], "r": 7.5, "score": 0.87, "table_mm": [1234.5, 321.0]}


def _dotted(node) -> str:
    """`json.dump` for the attribute chain of `node`, and "" for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _code_strings(tree) -> list:
    """(line, text) for every string literal that is not a docstring."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def _names_the_artifact(value: str) -> bool:
    """True when a string literal names the artifact, by its last path component."""
    return Path(value).name == ARTIFACT


def _walk(node, where: str):
    """(where, node) for every node, with `where` the innermost function name."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from _walk(child, child.name)
            continue
        yield where, child
        yield from _walk(child, where)


def _calls(tree) -> list:
    """(function, line, dotted name) for every call in the module."""
    return [(where, node.lineno, _dotted(node.func))
            for where, node in _walk(tree, "<module>") if isinstance(node, ast.Call)]


def _owner_path_names(tree) -> set:
    """The names a module binds to a path that `OWNER_PATH_CALLS` returned."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if any(_dotted(inner.func) in OWNER_PATH_CALLS
               for inner in ast.walk(value) if isinstance(inner, ast.Call)):
            names.update(target.id for target in targets if isinstance(target, ast.Name))
    return names


def _json_write_target(call):
    """The expression a JSON write writes into, or None when it writes no JSON."""
    name = _dotted(call.func)
    tail = name.split(".")[-1]
    if name == "json.dump":
        stream = call.args[1] if len(call.args) > 1 else None
        if isinstance(stream, ast.Call) and _dotted(stream.func) == "open" and stream.args:
            return stream.args[0]
        return None
    if tail in ("write_text", "write"):
        arguments = list(call.args) + [keyword.value for keyword in call.keywords]
        if any(_dotted(inner.func) == "json.dumps"
               for argument in arguments for inner in ast.walk(argument)
               if isinstance(inner, ast.Call)):
            return call.func.value
    return None


class OwnerWriteTest(unittest.TestCase):
    """A writer stamps the producer of every row it built, and names its own."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / ARTIFACT

    def test_write_stamps_every_ball_row_and_keeps_every_value(self):
        sam3_artifact.write(self.path, {"26.2": [ROW], "30.0": []},
                            producer=CAMERA_MODEL, indent=None)
        data = json.loads(self.path.read_text())
        written = data["26.2"][0]
        self.assertEqual(written[STAMP], {"version": VERSION, "producer": CAMERA_MODEL})
        self.assertEqual({key: value for key, value in written.items() if key != STAMP}, ROW,
                         "a write changes no row value")
        self.assertEqual(data["30.0"], [], "an empty frame stays an empty frame")

    def test_the_stamp_is_inside_the_row_and_not_beside_it(self):
        """Six of the eight readers call `float(key)` on every top-level key."""
        sam3_artifact.write(self.path, {"26.2": [ROW]}, producer=CAMERA_MODEL)
        data = json.loads(self.path.read_text())
        self.assertEqual(sorted(data), ["26.2"], "a top-level stamp key would stop six readers")
        self.assertIn(STAMP, data["26.2"][0])

    def test_write_refuses_a_producer_this_module_does_not_know(self):
        with self.assertRaises(ValueError) as caught:
            sam3_artifact.write(self.path, {"1.0": [ROW]}, producer="src/nobody.py")
        self.assertIn("cannot write rows it cannot name", str(caught.exception))
        self.assertFalse(self.path.exists(), "a refused write writes nothing")

    def test_write_refuses_a_frame_key_that_is_not_a_time(self):
        with self.assertRaises(ValueError) as caught:
            sam3_artifact.write(self.path, {"frames": [ROW]}, producer=CAMERA_MODEL)
        self.assertIn("is not a time", str(caught.exception))

    def test_write_refuses_a_row_with_no_table_mm(self):
        with self.assertRaises(ValueError) as caught:
            sam3_artifact.write(self.path, {"1.0": [{"img": [1.0, 2.0]}]},
                                producer=CAMERA_MODEL)
        self.assertIn("no 'table_mm'", str(caught.exception))
        self.assertEqual(list(ROW_KEYS), ["img", "table_mm"])

    def test_write_refuses_a_row_that_is_not_an_object(self):
        with self.assertRaises(ValueError) as caught:
            sam3_artifact.write(self.path, {"1.0": [[1.0, 2.0]]}, producer=CAMERA_MODEL)
        self.assertIn("row 0 of frame '1.0'", str(caught.exception))

    def test_write_replaces_a_stamp_when_the_call_built_every_value(self):
        """`src/rebuild_events_calibrated.py` recomputes every table_mm."""
        sam3_artifact.write(self.path, {"1.0": [ROW]}, producer=CAMERA_MODEL)
        sam3_artifact.write(self.path, sam3_artifact.read(self.path).frames,
                            producer=REBUILD_CALIBRATED)
        self.assertEqual(sam3_artifact.read(self.path).producer, REBUILD_CALIBRATED)

    def test_a_write_that_fails_leaves_the_old_file_in_place(self):
        """The bytes reach the file in one step, so a reader never sees half a file."""
        sam3_artifact.write(self.path, {"1.0": [ROW]}, producer=CAMERA_MODEL)
        before = self.path.read_bytes()
        with self.assertRaises(TypeError):
            sam3_artifact.write(self.path, {"2.0": [{**ROW, "score": object()}]},
                                producer=CAMERA_MODEL)
        self.assertEqual(before, self.path.read_bytes(),
                         "a write that fails must leave the file as it was")
        self.assertEqual([ARTIFACT], sorted(entry.name for entry in Path(self.tmp.name).iterdir()),
                         "a write that fails removes its temporary file")


class CopyTest(unittest.TestCase):
    """A caller that copies a row stamps only the rows it built itself."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / ARTIFACT

    def test_a_copied_row_keeps_the_stamp_of_the_builder_that_made_it(self):
        sam3_artifact.write(self.path, {"1.0": [ROW]}, producer=REBUILD_CALIBRATED)
        data = sam3_artifact.read(self.path).frames       # exactly as a reader returns it
        data["2.0"] = sam3_artifact.stamp([ROW], CAMERA_MODEL)
        sam3_artifact.write(self.path, data, producer=CAMERA_MODEL, keep_stamps=True)
        artifact = sam3_artifact.read(self.path)
        self.assertEqual(artifact.status, MIXED)
        self.assertEqual(set(artifact.producers), {CAMERA_MODEL, REBUILD_CALIBRATED})
        self.assertEqual(artifact.frames["1.0"][0][STAMP]["producer"], REBUILD_CALIBRATED,
                         "the copied row still names the module that recomputed it")
        self.assertEqual(artifact.frames["2.0"][0][STAMP]["producer"], CAMERA_MODEL)

    def test_a_copied_row_with_no_stamp_stays_without_one(self):
        """The file of this repository holds 270 such rows; this module never guesses."""
        legacy = {"img": [1.0, 2.0], "table_mm": [3.0, 4.0]}
        self.path.write_text(json.dumps({"1.0": [legacy]}))
        data = sam3_artifact.read(self.path).frames
        data["2.0"] = sam3_artifact.stamp([legacy], CAMERA_MODEL)
        sam3_artifact.write(self.path, data, producer=CAMERA_MODEL, keep_stamps=True)
        artifact = sam3_artifact.read(self.path)
        self.assertEqual(artifact.status, MIXED)
        self.assertEqual(artifact.unstamped, 1)
        self.assertNotIn(STAMP, artifact.frames["1.0"][0],
                         "a copied row that carries no stamp keeps no stamp")

    def test_write_refuses_a_kept_stamp_this_module_does_not_know(self):
        foreign = {**ROW, STAMP: {"version": VERSION, "producer": "src/gone.py"}}
        with self.assertRaises(ValueError) as caught:
            sam3_artifact.write(self.path, {"1.0": [foreign]}, producer=CAMERA_MODEL,
                                keep_stamps=True)
        self.assertIn("A caller that copies a row it did not build", str(caught.exception))
        self.assertFalse(self.path.exists())

    def test_write_refuses_a_kept_version_this_module_does_not_write(self):
        newer = {**ROW, STAMP: {"version": VERSION + 1, "producer": CAMERA_MODEL}}
        with self.assertRaises(ArtifactVersionError):
            sam3_artifact.write(self.path, {"1.0": [newer]}, producer=CAMERA_MODEL,
                                keep_stamps=True)

    def test_stamp_refuses_a_row_that_another_producer_built(self):
        built = sam3_artifact.stamp([ROW], REBUILD_CALIBRATED)
        with self.assertRaises(ValueError) as caught:
            sam3_artifact.stamp(built, CAMERA_MODEL)
        self.assertIn("cannot stamp a row that another producer built", str(caught.exception))

    def test_stamp_keeps_every_value_of_the_row_it_stamps(self):
        stamped = sam3_artifact.stamp([ROW], CAMERA_MODEL)
        self.assertEqual({key: value for key, value in stamped[0].items() if key != STAMP}, ROW)
        self.assertEqual(ROW, {"img": [640.0, 360.0], "r": 7.5, "score": 0.87,
                               "table_mm": [1234.5, 321.0]},
                         "the call changes no row it was given")


class OwnerReadTest(unittest.TestCase):
    """A read returns the rows of the file, and says who built them or that it cannot."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / ARTIFACT

    def test_a_read_of_a_real_file_returns_its_rows_unchanged(self):
        """Byte level: the frames of `read` are the JSON object of the file."""
        sam3_artifact.write(self.path, {"26.2": [ROW], "30.0": []}, producer=CAMERA_MODEL,
                            indent=None)
        artifact = sam3_artifact.read(self.path)
        self.assertEqual(artifact.frames, json.loads(self.path.read_bytes()),
                         "a read returns the rows of the file unchanged")
        self.assertEqual({key: value for key, value in artifact.frames["26.2"][0].items()
                          if key != STAMP}, ROW, "a read changes no row value")

    def test_a_read_reports_the_camera_model_after_a_camera_write(self):
        sam3_artifact.write(self.path, {"26.2": [ROW]}, producer=CAMERA_MODEL)
        artifact = sam3_artifact.read(self.path)
        self.assertEqual(artifact.status, STAMPED)
        self.assertTrue(artifact.named)
        self.assertEqual(artifact.producer, CAMERA_MODEL)
        self.assertEqual(artifact.version, VERSION)
        self.assertIn(CAMERA_MODEL, artifact.describe())

    def test_a_read_reports_the_rebuild_after_a_rebuild_write(self):
        sam3_artifact.write(self.path, {"26.2": [ROW]}, producer=REBUILD_CALIBRATED)
        self.assertEqual(sam3_artifact.read(self.path).producer, REBUILD_CALIBRATED)

    def test_a_read_reports_a_file_that_names_no_producer(self):
        self.path.write_text(json.dumps({"26.2": [ROW], "30.0": []}))
        artifact = sam3_artifact.read(self.path)
        self.assertEqual(artifact.status, UNSTAMPED)
        self.assertIsNone(artifact.producer, "an unstamped file names no producer")
        self.assertIsNone(artifact.version)
        self.assertEqual(artifact.unstamped, 1)
        self.assertEqual(artifact.empty, 1, "an empty frame holds no table_mm to name")
        self.assertIn("the producer is unknown", artifact.describe())

    def test_read_refuses_a_file_that_is_not_an_object_of_frame_lists(self):
        self.path.write_text(json.dumps([ROW]))
        with self.assertRaises(ArtifactShapeError):
            sam3_artifact.read(self.path)

    def test_read_refuses_a_frame_that_is_not_a_list(self):
        self.path.write_text(json.dumps({"26.2": ROW}))
        with self.assertRaises(ArtifactShapeError):
            sam3_artifact.read(self.path)

    def test_read_refuses_a_version_this_module_does_not_read(self):
        self.path.write_text(json.dumps({"26.2": [
            {**ROW, STAMP: {"version": VERSION + 1, "producer": CAMERA_MODEL}}]}))
        with self.assertRaises(ArtifactVersionError):
            sam3_artifact.read(self.path)

    def test_a_shape_refusal_is_a_value_error_and_a_version_refusal_is_not(self):
        """`src/sam3_ball_cache.py:load_cache` tolerates a damaged file, not a newer one."""
        self.assertTrue(issubclass(ArtifactShapeError, ValueError))
        self.assertFalse(issubclass(ArtifactVersionError, ValueError))


class NameTest(unittest.TestCase):
    """The owner names the file, so a caller names the repository table instead."""

    def test_artifact_path_follows_the_dataset_table(self):
        self.assertEqual(sam3_artifact.artifact_path(), ROOT / "out" / "scan30" / ARTIFACT)

    def test_an_unknown_dataset_keeps_the_scan_name_of_motion_scan(self):
        self.assertEqual(sam3_artifact.artifact_path("nope"),
                         ROOT / "out" / "scan_nope" / ARTIFACT)

    def test_artifact_in_uses_the_directory_it_is_given(self):
        self.assertEqual(sam3_artifact.artifact_in("out/scan30"), Path("out/scan30") / ARTIFACT)

    def test_owns_the_artifact_name_only(self):
        self.assertTrue(sam3_artifact.owns(f"out/scan30/{ARTIFACT}"))
        self.assertTrue(sam3_artifact.owns(Path("/anywhere") / ARTIFACT))
        self.assertFalse(sam3_artifact.owns("out/scan30/sam3_census.json"))
        self.assertFalse(sam3_artifact.owns("out/scan30/events.json"))


class ScopeGuardTest(unittest.TestCase):
    """No module in scope names the artifact or rewrites it outside the owner."""

    def test_every_module_in_scope_calls_the_owner(self):
        for relative in SCOPE:
            calls = _calls(ast.parse((ROOT / relative).read_text()))
            self.assertTrue([name for _, _, name in calls if name.startswith("sam3_artifact.")],
                            f"{relative} does not go through {OWNER}")

    def test_every_producer_names_a_module_that_writes_through_the_owner(self):
        for producer, rule in PRODUCERS.items():
            self.assertIn(producer, SCOPE, f"{producer} is not a module in scope")
            self.assertTrue(rule.strip(), f"{producer} has no rule-set note")
            text = (ROOT / producer).read_text()
            for fragment in PRODUCER_WRITES[producer]:
                self.assertIn(fragment, text,
                              f"{producer} is a producer but does not write through {OWNER}")

    def test_a_producer_that_copies_a_row_keeps_the_stamp_it_read(self):
        """`src/scan_events.py` measures one frame and copies the frames it read."""
        text = (ROOT / CAMERA_MODEL).read_text()
        self.assertIn("sam3_artifact.stamp(", text,
                      f"{CAMERA_MODEL} must stamp the rows of its own call")
        self.assertIn("keep_stamps=True", text,
                      f"{CAMERA_MODEL} must keep the stamps of the rows it copies")

    def test_a_producer_that_recomputes_every_value_restamps_every_row(self):
        text = (ROOT / REBUILD_CALIBRATED).read_text()
        self.assertNotIn("keep_stamps=True", text,
                         f"{REBUILD_CALIBRATED} recomputes every table_mm, so every row is "
                         f"its own work")

    def test_scope_modules_name_the_artifact_only_through_the_owner(self):
        used, found = set(), []
        for relative in SCOPE:
            tree = ast.parse((ROOT / relative).read_text())
            for line, value in _code_strings(tree):
                if _names_the_artifact(value):
                    found.append((relative, line, value))
                    if (relative, value) in OTHER_ARTIFACT_FILES:
                        used.add((relative, value))
        for relative, line, value in found:
            self.assertIn((relative, value), OTHER_ARTIFACT_FILES,
                          f"{relative}:{line} names {value!r}; {ARTIFACT} is named in "
                          f"{OWNER} only (use artifact_path/artifact_in)")
        self.assertEqual(OTHER_ARTIFACT_FILES.keys() - used, set(),
                         "an entry in OTHER_ARTIFACT_FILES outlived its code")

    def test_scope_modules_do_not_rewrite_the_artifact_in_place(self):
        """`json.dump(x, open(SAM3, "w"))` is a rewrite of the owner's file."""
        offenders = []
        for relative in SCOPE:
            tree = ast.parse((ROOT / relative).read_text())
            names = _owner_path_names(tree)
            for where, node in _walk(tree, "<module>"):
                if not isinstance(node, ast.Call):
                    continue
                if _dotted(node.func).startswith("sam3_artifact."):
                    continue                     # the write of the owner itself
                if _json_write_target(node) is None:
                    continue
                target = {name.id for name in ast.walk(_json_write_target(node))
                          if isinstance(name, ast.Name)}
                if target & names:
                    offenders.append(
                        f"{relative}:{node.lineno} {where} writes JSON into the path that "
                        f"{OWNER} named")
        self.assertEqual(offenders, [],
                         "a function rewrites the artifact without going through the owner: "
                         + "; ".join(offenders))


class RealArtifactTest(unittest.TestCase):
    """The artifact of this workspace, when the checkout has it."""

    def setUp(self):
        self.path = data_guard.require(sam3_artifact.artifact_path())

    def test_a_read_of_the_real_file_returns_its_rows_unchanged(self):
        artifact = sam3_artifact.read(self.path)
        self.assertEqual(artifact.frames, json.loads(self.path.read_bytes()),
                         "a read returns the rows of the real file unchanged")
        self.assertEqual(artifact.balls,
                         sum(len(rows) for rows in artifact.frames.values() if isinstance(rows, list)))

    def test_the_real_file_names_one_producer_or_says_that_it_cannot(self):
        artifact = sam3_artifact.read(self.path)
        self.assertIn(artifact.status, (STAMPED, MIXED, UNSTAMPED))
        if artifact.status == STAMPED:
            self.assertIn(artifact.producer, PRODUCERS)
            self.assertEqual(artifact.version, VERSION)
        else:
            self.assertIsNone(artifact.producer, "a reader must not guess a producer")
        self.assertTrue(artifact.describe())


if __name__ == "__main__":
    unittest.main()
