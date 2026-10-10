"""The events document has one owner, and this suite holds the callers to it.

Two guards, both reading the source of the modules in scope with `ast`, so a
module that names the served document or that writes a JSON list of events
outside `src/events_document.py` fails here instead of at the review rail:

  * `test_scope_modules_name_a_document_only_through_the_owner` fails on a code
    string that names a document, unless the name is the exempt candidate file
    in `OTHER_DOCUMENT_FILES`;
  * `test_scope_modules_write_json_only_through_the_owner` fails on a function
    that writes JSON into a file and neither goes through
    `events_document.write` nor appears in `WRITES_OUTSIDE_THE_DOCUMENT`.

Both tables fail when an entry stops matching, so an exemption cannot outlive
the code it was granted to.

The guards cover the modules in `SCOPE`.  `src/motion_scan.py`, `src/store.py`
and `annotator/` also name the served file; they are outside this change.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest

import src.events_document as events_document
from src.events_document import (DENSE_QUEUE, DOCUMENTS, EVAL_EVENTS, MIXED, PRODUCERS,
                                 REBUILD_CALIBRATED, REBUILD_V2, SCAN_EVENTS, SERVED, STAMP,
                                 STAMPED, UNSTAMPED, V2, VERSION, DocumentShapeError,
                                 DocumentVersionError)

ROOT = Path(__file__).resolve().parents[1]
OWNER = "src/events_document.py"

#: The modules this change put behind the owner, as paths from the repository
#: root.  A module leaves this list only with the scope of the change.
SCOPE = (
    "src/scan_events.py",
    "src/rebuild_events_calibrated.py",
    "src/rebuild_events_v2.py",
    "src/dense_queue.py",
    "src/eval_events.py",
    "src/candidate_scan.py",
)
SCOPE_AND_OWNER = SCOPE + (OWNER,)
DOCUMENT_NAMES = (SERVED, V2)

#: A code string that names a document but is not a document of a scan, with the
#: reason it may stay.  The key is (module, the string).  The guard fails when a
#: key stops matching a string in that module.
OTHER_DOCUMENT_FILES = {
    ("src/eval_events.py", "out/scan-ic/events.json"):
        "the info-complete candidate file, which src/info_complete_scan.py writes "
        "(outside this change); it is a candidate list, not a scan document",
}

#: A function that writes JSON into a file without going through
#: `events_document.write`, with the file it writes and why that is not the
#: document.  A function that writes through the owner needs no entry.
WRITES_OUTSIDE_THE_DOCUMENT = {
    ("src/dense_queue.py", "write_ledger"):
        "the retired-id ledger, a map keyed by ball_id",
    ("src/eval_events.py", "measure"):
        "the probe cache ({version, payloads})",
    ("src/candidate_scan.py", "write_plan"):
        "sam3_plan.json and candidates_selected.json",
    ("src/candidate_scan.py", "main"):
        "the raw scan candidates (--out), none of them gated",
}

#: The keys one served row of out/scan30/events.json carried before this change
#: (measured at HEAD 2c59ed9).  Every reader of the document reads some of them,
#: so a write may add a key but may not drop or change one.
SERVED_ROW_KEYS = ("color", "dup_count", "gate", "id", "last_mm", "last_px", "nearest_pocket",
                   "origin", "pocket_name", "provenance", "source", "t", "tier", "type",
                   "verified", "window_s")


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


def _names_a_document(value: str) -> bool:
    """True when a string literal names one of the documents.

    The test is on the last path component of the literal, so a report such as
    "out/scan30/eval_events.json" is not mistaken for the document
    "out/scan30/events.json".
    """
    return Path(value).name in DOCUMENT_NAMES


def _json_write_kind(call) -> str | None:
    """The kind of JSON write this call is, or None when it writes no JSON."""
    name = _dotted(call.func)
    if name == "json.dump":
        return "json.dump"
    if name.split(".")[-1] in ("write_text", "write"):
        arguments = list(call.args) + [keyword.value for keyword in call.keywords]
        if any(_dotted(inner.func) == "json.dumps"
               for argument in arguments for inner in ast.walk(argument)
               if isinstance(inner, ast.Call)):
            return name
    return None


def _walk(node, where: str):
    """(where, node) for every node, with `where` the innermost function name."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from _walk(child, child.name)
            continue
        yield where, child
        yield from _walk(child, where)


def _json_write_sites(tree) -> list:
    """(function, line, kind) for every JSON write in the module."""
    return [(where, node.lineno, _json_write_kind(node))
            for where, node in _walk(tree, "<module>")
            if isinstance(node, ast.Call) and _json_write_kind(node)]


def _calls(tree) -> list:
    """(function, line, dotted name) for every call in the module."""
    return [(where, node.lineno, _dotted(node.func))
            for where, node in _walk(tree, "<module>") if isinstance(node, ast.Call)]


class OwnerWriteTest(unittest.TestCase):
    """A writer cannot write rows it cannot name."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / SERVED

    def test_write_stamps_every_row_and_keeps_every_value(self):
        row = {"t": 1352.0, "type": "pot", "id": 9001, "color": "5",
               "nearest_pocket": "head-left (18 ± 12mm)", "pocket_name": "head-left",
               "last_mm": [120.5, 400.25], "last_px": [812.0, 96.5], "dup_count": 1,
               "tier": None, "origin": "dense-track", "verified": False,
               "window_s": [1350.5, 1353.5],
               "gate": {"status": "unconfirmed", "gate": "occlusion", "reasons": ["a"],
                        "codes": ["cloth_occluded_at_disappearance"], "numbers": {"dense_x": 1},
                        "dup_count": 1, "colors_merged": ["5"]},
               "provenance": {"detector": "dense-track · trained 960×540 net @ ball@2",
                              "machine_produced": True, "human_confirmed": False}}
        events_document.write(self.path, [row], producer=DENSE_QUEUE)
        data = json.loads(self.path.read_text())
        self.assertIsInstance(data, list, "every reader reads a top-level list")
        self.assertEqual(len(data), 1)
        written = data[0]
        self.assertEqual(written[STAMP], {"version": VERSION, "producer": DENSE_QUEUE})
        self.assertEqual({k: v for k, v in written.items() if k != STAMP}, row,
                         "a write changes no row value")

    def test_a_write_that_fails_leaves_the_old_document_in_place(self):
        """The bytes reach the file in one step, so a reader never sees half a document."""
        events_document.write(self.path, [{"t": 1.0, "type": "shot"}], producer=SCAN_EVENTS)
        before = self.path.read_bytes()
        with self.assertRaises(TypeError):
            events_document.write(self.path, [{"t": 2.0, "type": "pot", "bad": object()}],
                                  producer=SCAN_EVENTS)
        self.assertEqual(before, self.path.read_bytes(),
                         "a write that fails must leave the document as it was")
        self.assertEqual([SERVED], sorted(entry.name for entry in self.tmp.iterdir()),
                         "a write that fails removes its temporary file")

    def test_write_refuses_a_producer_this_module_does_not_know(self):
        with self.assertRaises(ValueError) as caught:
            events_document.write(self.path, [{"t": 1.0, "type": "shot"}],
                                  producer="src/nobody.py")
        self.assertIn("cannot write rows it cannot name", str(caught.exception))
        self.assertFalse(self.path.exists(), "a refused write writes nothing")

    def test_write_refuses_a_row_that_is_not_an_object(self):
        with self.assertRaises(ValueError) as caught:
            events_document.write(self.path, [["t", 1.0]], producer=SCAN_EVENTS)
        self.assertIn("row 0", str(caught.exception))

    def test_write_refuses_a_row_with_no_type(self):
        with self.assertRaises(ValueError) as caught:
            events_document.write(self.path, [{"t": 1.0}], producer=SCAN_EVENTS)
        self.assertIn("no type", str(caught.exception))

    def test_write_refuses_a_row_another_producer_stamped(self):
        stamped = {"t": 1.0, "type": "shot",
                   STAMP: {"version": VERSION, "producer": DENSE_QUEUE}}
        with self.assertRaises(ValueError) as caught:
            events_document.write(self.path, [stamped], producer=SCAN_EVENTS)
        self.assertIn("cannot name a row another producer built", str(caught.exception))

    def test_write_stamps_the_same_producer_again_without_complaint(self):
        events_document.write(self.path, [{"t": 1.0, "type": "shot"}], producer=SCAN_EVENTS)
        document = events_document.read(self.path)
        events_document.write(self.path, document.rows, producer=SCAN_EVENTS)
        again = events_document.read(self.path)
        self.assertTrue(again.named)
        self.assertEqual(again.producer, SCAN_EVENTS)

    def test_write_refuses_a_document_name_this_module_does_not_own(self):
        with self.assertRaises(ValueError):
            events_document.document_in("out/scan30", name="results.json")


class OwnerReadTest(unittest.TestCase):
    """A reader always learns which rule set produced the rows, or that it cannot."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _file(self, rows, name=SERVED):
        path = self.tmp / name
        path.write_text(json.dumps(rows, indent=1))
        return path

    def test_a_legacy_document_reads_as_unknown_not_as_a_guess(self):
        path = self._file([{"t": 1.0, "type": "shot", "id": 1},
                           {"t": 2.0, "type": "pot", "id": 2}])
        document = events_document.read(path)
        self.assertEqual(document.status, UNSTAMPED)
        self.assertFalse(document.named)
        self.assertIsNone(document.producer, "the producer of an unstamped file is unknown")
        self.assertIsNone(document.version)
        self.assertEqual([row["id"] for row in document.rows], [1, 2], "the rows are kept")
        self.assertIn("unknown", document.describe())

    def test_an_empty_document_names_no_producer(self):
        document = events_document.read(self._file([]))
        self.assertEqual(document.status, UNSTAMPED)
        self.assertEqual(document.rows, [])

    def test_a_mixed_document_is_unknown(self):
        path = self._file([{"t": 1.0, "type": "shot"},
                           {"t": 2.0, "type": "shot", STAMP: {"version": VERSION,
                                                              "producer": DENSE_QUEUE}}])
        document = events_document.read(path)
        self.assertEqual(document.status, MIXED)
        self.assertIsNone(document.producer)
        self.assertEqual(document.producers, (DENSE_QUEUE,))
        self.assertEqual(document.unstamped, 1)

    def test_a_stamped_document_names_its_producer(self):
        path = self.tmp / SERVED
        events_document.write(path, [{"t": 1.0, "type": "shot"}], producer=EVAL_EVENTS)
        document = events_document.read(path)
        self.assertEqual(document.status, STAMPED)
        self.assertTrue(document.named)
        self.assertEqual((document.version, document.producer), (VERSION, EVAL_EVENTS))

    def test_read_refuses_a_document_newer_than_this_module(self):
        path = self._file([{"t": 1.0, "type": "shot",
                            STAMP: {"version": VERSION + 1, "producer": DENSE_QUEUE}}])
        with self.assertRaises(DocumentVersionError) as caught:
            events_document.read(path)
        self.assertIn("newer than this module knows", str(caught.exception))
        self.assertNotIsInstance(caught.exception, ValueError,
                                 "a caller that tolerates a damaged file still stops here")

    def test_read_refuses_a_document_that_is_not_a_list(self):
        path = self._file({"version": VERSION, "events": [{"t": 1.0, "type": "shot"}]})
        with self.assertRaises(DocumentShapeError) as caught:
            events_document.read(path)
        self.assertIsInstance(caught.exception, ValueError)
        self.assertIn("JSON list of rows", str(caught.exception))

    def test_read_does_not_change_the_file(self):
        path = self._file([{"t": 1.0, "type": "shot", "note": "ü"}])
        before = path.read_bytes()
        events_document.read(path)
        self.assertEqual(path.read_bytes(), before)

    def test_the_served_document_of_this_workspace_reads(self):
        served = events_document.document_path()
        if not served.exists():
            self.skipTest(f"no served document at {served}")
        document = events_document.read(served)
        self.assertEqual(document.path, served)
        self.assertIn(document.status, (STAMPED, MIXED, UNSTAMPED))
        for row in document.rows:
            self.assertIsInstance(row, dict)
            self.assertIn("t", row, "the readers read a time on every row")
            self.assertIn("type", row, "the readers read a type on every row")


class OwnerPathTest(unittest.TestCase):
    """The document path is named once, in the owner."""

    def test_the_served_document_follows_the_dataset_table(self):
        from src.datasets import STATIC_OUT

        self.assertEqual(events_document.document_path(),
                         ROOT / "out" / STATIC_OUT["vod30"] / SERVED)
        self.assertEqual(events_document.document_path(dataset="highlight"),
                         ROOT / "out" / STATIC_OUT["highlight"] / SERVED)

    def test_an_unknown_dataset_keeps_the_scan_name_of_motion_scan(self):
        self.assertEqual(events_document.scan_dir("r34"), ROOT / "out" / "scan_r34")

    def test_the_two_documents_are_named_once(self):
        self.assertEqual(DOCUMENTS, (SERVED, V2))
        self.assertEqual(events_document.document_path(V2),
                         ROOT / "out" / "scan30" / V2)
        self.assertEqual(events_document.document_path(root="out/ui-browser-fixture"),
                         Path("out/ui-browser-fixture") / "out" / "scan30" / SERVED,
                         "a relative root is used as given, as src/eval_events.py passes it")

    def test_document_in_uses_the_directory_it_is_given(self):
        self.assertEqual(events_document.document_in("out/scan30"), Path("out/scan30") / SERVED)


class ScopeGuardTest(unittest.TestCase):
    """No module in scope names a document or writes JSON outside the owner."""

    def test_every_module_in_scope_calls_the_owner(self):
        for relative in SCOPE:
            calls = _calls(ast.parse((ROOT / relative).read_text()))
            self.assertTrue([name for _, _, name in calls
                             if name.startswith("events_document.")],
                            f"{relative} does not go through {OWNER}")

    def test_every_producer_names_a_module_that_writes_through_the_owner(self):
        for producer, rule in PRODUCERS.items():
            self.assertIn(producer, SCOPE, f"{producer} is not a module in scope")
            self.assertTrue(rule.strip(), f"{producer} has no rule-set note")
            text = (ROOT / producer).read_text()
            self.assertIn("events_document.write(", text,
                          f"{producer} is a producer but does not write through {OWNER}")

    def test_scope_modules_name_a_document_only_through_the_owner(self):
        used, found = set(), []
        for relative in SCOPE:
            tree = ast.parse((ROOT / relative).read_text())
            for line, value in _code_strings(tree):
                if _names_a_document(value):
                    found.append((relative, line, value))
                    if (relative, value) in OTHER_DOCUMENT_FILES:
                        used.add((relative, value))
        for relative, line, value in found:
            self.assertIn((relative, value), OTHER_DOCUMENT_FILES,
                          f"{relative}:{line} names {value!r}; the documents are named in "
                          f"{OWNER} only (use document_path/document_in)")
        self.assertEqual(OTHER_DOCUMENT_FILES.keys() - used, set(),
                         "an entry in OTHER_DOCUMENT_FILES outlived its code")

    def test_scope_modules_write_json_only_through_the_owner(self):
        used, offenders = set(), []
        for relative in SCOPE:
            tree = ast.parse((ROOT / relative).read_text())
            through_owner = {where for where, _, name in _calls(tree)
                             if name == "events_document.write"}
            for where, line, kind in _json_write_sites(tree):
                if where in through_owner:
                    continue
                if (relative, where) in WRITES_OUTSIDE_THE_DOCUMENT:
                    used.add((relative, where))
                    continue
                offenders.append(f"{relative}:{line} {where} writes JSON with {kind}")
        self.assertEqual(offenders, [],
                         "a function writes JSON into a file without naming it in the owner: "
                         + "; ".join(offenders))
        self.assertEqual(WRITES_OUTSIDE_THE_DOCUMENT.keys() - used, set(),
                         "an entry in WRITES_OUTSIDE_THE_DOCUMENT outlived its code")


if __name__ == "__main__":
    unittest.main()
