"""Guard and behavior tests: one atomic step, and one owner of the document bytes.

Five modules write a JSON document with their own nested `def dump(stream)`:
src/store.py `_write`, src/enroll_from_tracklet.py `_write_json`,
annotator/shot_clock.py `ShotClock._save`, annotator/unified_server.py
`atomic_save`, and annotator/vod_import.py `_atomic_json`. Every one of them builds
the text with `json.dump(..., indent=2, allow_nan=False)` and one trailing newline.

The step that never leaves a half file has one owner, src/atomic_write.py
`write_atomic`. The text of a document has one owner too, src/store_files.py `dump`.
This module holds the five writers to both owners, and it keeps the small
differences they always had:

  * src/store.py `_write`                     fsync, hidden temp name, no temp file
  * src/enroll_from_tracklet.py `_write_json` no fsync, `<name>.tmp<pid>`, and the
                                              temp file stays after a failure
  * annotator/shot_clock.py `ShotClock._save` fsync, temp prefix `.clock-`
  * annotator/unified_server.py `atomic_save` fsync, hidden temp name
  * annotator/vod_import.py `_atomic_json`    fsync, sorted keys in the index

A body cannot call `store_files.dump` with a named format: that function needs the
name of a format, and tests/test_store_files.py refuses every format name in every
file outside the owner. This module asks the owner for the format of a document
path instead (see DOCUMENT), so it can compare the bytes of a writer with the bytes
of the owner. A round that adds a value-only renderer to the owner can delete the
five bodies, and these byte cases stay as they are.

Two rules read the module source of src/*.py and annotator/*.py:
  * Rule 1: a function that names a temp file with a string that contains ".tmp"
    and then renames it builds its own atomic write. No function may do that.
  * Rule 2: a function that calls tempfile.mkstemp or NamedTemporaryFile and then
    renames the result holds its own atomic write. Only the owner and the two
    entries of EXEMPT may do that, and a stale entry fails a case below.

annotator/unified_server.py `event_clip` renames a `.part.mp4` file too. It is not
a writer of this kind: an external encoder writes those bytes, so the function
cannot call `write_atomic`. Rule 1 and Rule 2 do not see it.
"""
from __future__ import annotations

import ast
import json
import tempfile
import textwrap
import unittest
from collections import namedtuple
from pathlib import Path

from src import store_files
from src.atomic_write import write_atomic

ROOT = Path(__file__).resolve().parents[1]

#: One row for every former copy: the key of its generated cases, the file and the
#: function a reader can find, the call that writes a value, and whether the writer
#: leaves its temp file after a failed write.
Site = namedtuple("Site", "key name module qualname drive temp_after_failure")

#: The files that keep their own temp-file-and-rename code, and the reason. The case
#: `test_every_exemption_is_still_needed` fails when a line here outlives its code.
EXEMPT = {
    "src/atomic_write.py": "the owner itself: it makes the temp file and calls os.replace",
    "annotator/operations.py": "Operations._commit keeps the .state- temp file, the fsync and "
                               "the cleanup it had; tests/test_atomic_write.py defers it",
}

#: The one writer whose value reaches the owner with sorted keys.
SORTS_KEYS = {"annotator.vod_import"}

#: The byte format of one document, asked from its owner by a path that the owner
#: itself declares. This module must not spell the name of a format: the case
#: `FileFormats.test_no_other_source_file_spells_a_format_name` of
#: tests/test_store_files.py keeps every such name in src/store_files.py.
DOCUMENT = store_files.fmt_of(store_files.document_paths("operations")[0])

#: A document with mappings in an order that is not the sorted order, a non-ASCII
#: string, a float, a boolean, and empty containers. JSON writes it as ASCII bytes.
VALUE = {
    "zulu": 1,
    "alpha": {"y": [3, {"b": 2, "a": 1}], "x": None},
    "text": "caf\u00e9",
    "ratio": 0.1,
    "flag": False,
    "none": None,
    "empty_list": [],
    "empty_map": {},
}


def _drive_store(path, value):
    import src.store_files as module
    module.save_document(Path(path), value)


def _drive_enroll(path, value):
    import src.enroll_from_tracklet as module
    module._write_json(Path(path), value)


def _drive_shot_clock(path, value):
    import annotator.shot_clock as module
    module.ShotClock(Path(path))._save(value)


def _drive_unified_server(path, value):
    import annotator.unified_server as module
    module.atomic_save(Path(path), value)


def _drive_vod_import(path, value):
    import annotator.vod_import as module
    module._atomic_json(Path(path), value)


SITES = (
    Site("store", "src/store_files.py save_document", "src.store_files", "save_document",
         _drive_store, False),
    Site("enroll", "src/enroll_from_tracklet.py _write_json", "src.enroll_from_tracklet",
         "_write_json", _drive_enroll, True),
    Site("shot_clock", "annotator/shot_clock.py ShotClock._save", "annotator.shot_clock",
         "ShotClock._save", _drive_shot_clock, False),
    Site("unified_server", "annotator/unified_server.py atomic_save", "annotator.unified_server",
         "atomic_save", _drive_unified_server, False),
    Site("vod_import", "annotator/vod_import.py _atomic_json", "annotator.vod_import",
         "_atomic_json", _drive_vod_import, False),
)


def _site(key):
    return next(site for site in SITES if site.key == key)


def _source_files():
    """The top-level modules of src/ and annotator/, in a stable order.

    Top level only, on purpose: src/sam3/ is a vendored checkout with its own
    writers, and it is not a part of this repository's code."""
    for base in ("src", "annotator"):
        for path in sorted((ROOT / base).glob("*.py")):
            yield path


def _module_path(site):
    return ROOT / (site.module.replace(".", "/") + ".py")


def _tree(site):
    return ast.parse(_module_path(site).read_text())


def _resolve(tree, qualname):
    """The node of `qualname`: a function name, or Class.method."""
    node = tree
    for part in qualname.split("."):
        node = next((child for child in getattr(node, "body", [])
                     if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and child.name == part), None)
        if node is None:
            return None
    return node


def _dotted(node):
    """The dotted name of an expression, or "" for any other expression."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    parts.append(node.id)
    return ".".join(reversed(parts))


def _calls(node, names):
    return [call for call in ast.walk(node)
            if isinstance(call, ast.Call) and _dotted(call.func) in names]


def _functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _tmp_string_lines(node):
    """The line of every string in this function that contains ".tmp"."""
    return [item.lineno for item in ast.walk(node)
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
            and ".tmp" in item.value]


def _temp_call_lines(node):
    """The line of every call in this function that makes a temp file."""
    return [item.lineno for item in ast.walk(node) if isinstance(item, ast.Call)
            and _dotted(item.func) in ("tempfile.mkstemp", "tempfile.NamedTemporaryFile",
                                       "tempfile.TemporaryFile", "tempfile.mkdtemp")]


def _rename_lines(node):
    """The line of every call in this function that renames a file."""
    lines = []
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        if _dotted(item.func) in ("os.replace", "os.rename", "shutil.move"):
            lines.append(item.lineno)
        elif isinstance(item.func, ast.Attribute) and item.func.attr in ("replace", "rename"):
            lines.append(item.lineno)
    return lines


def _sites(tree, temp_lines):
    """Every function of this tree that makes a temp name and then renames it."""
    found = []
    for node in _functions(tree):
        temps = temp_lines(node)
        renames = _rename_lines(node)
        if temps and renames:
            found.append((node.lineno, node.name, temps[0], renames[0]))
    return found


def _report(path, site):
    line, name, temp, rename = site
    return (f"{path.relative_to(ROOT).as_posix()}:{line} {name} "
            f"(temp line {temp}, rename line {rename})")


def _newline_writes(node):
    """The number of calls in this function that write one newline to a stream."""
    return len([item for item in ast.walk(node) if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Attribute) and item.func.attr == "write"
                and len(item.args) == 1 and isinstance(item.args[0], ast.Constant)
                and item.args[0].value == "\n"])


def _stray_tmp_lines(node, calls):
    """The line of every ".tmp" string of this function that is not a temp_name option.

    A body may hand the pattern of a temp name to `write_atomic` (the enroll writer
    does). Rule 1 looks for a string and a rename, so such a string is not a second
    writer by itself."""
    allowed = {id(keyword.value) for call in calls for keyword in call.keywords
               if keyword.arg == "temp_name"}
    return [item.lineno for item in ast.walk(node)
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
            and ".tmp" in item.value and id(item) not in allowed]


def _former_text(site, value):
    """The text that the nested `def dump(stream)` of this writer produced."""
    if site.module in SORTS_KEYS:
        return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    return json.dumps(value, indent=2, allow_nan=False) + "\n"


def _owner_text(site, value):
    """The text that src.store_files.dump builds for the value that reaches it."""
    if site.module in SORTS_KEYS:
        value = json.loads(json.dumps(value, sort_keys=True))
    return store_files.dump(value, DOCUMENT)


class TestTheWalk(unittest.TestCase):
    """No module in src/ or annotator/ builds its own atomic write."""

    def test_no_function_names_a_temp_file_and_renames_it(self):
        found = [_report(path, site) for path in _source_files()
                 for site in _sites(ast.parse(path.read_text()), _tmp_string_lines)]
        self.assertEqual([], found, f"a function builds its own atomic write: {found}")

    def test_only_the_owner_and_the_named_exemptions_make_a_temp_file(self):
        found = sorted(path.relative_to(ROOT).as_posix() for path in _source_files()
                       if _sites(ast.parse(path.read_text()), _temp_call_lines))
        self.assertEqual(sorted(EXEMPT), found,
                         "a module outside EXEMPT makes a temp file and renames it")

    def test_every_exemption_is_still_needed(self):
        for relative in sorted(EXEMPT):
            with self.subTest(path=relative):
                sites = _sites(ast.parse((ROOT / relative).read_text()), _temp_call_lines)
                self.assertNotEqual([], sites, f"{relative} no longer holds a temp file "
                                               f"and a rename: remove its line from EXEMPT")

    def test_the_walk_sees_a_planted_copy(self):
        """The two rules catch a hand-written copy, and the walk reads top level only."""
        planted = textwrap.dedent('''
            import json
            import os
            import tempfile
            from pathlib import Path


            def save(path, value):
                path = Path(path)
                fd, name = tempfile.mkstemp(prefix=".doc-", dir=path.parent)
                with os.fdopen(fd, "w") as stream:
                    stream.write(json.dumps(value, indent=2))
                os.replace(name, path)


            def save_two(path, value):
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(value, indent=2))
                tmp.replace(path)
        ''')
        tree = ast.parse(planted)
        self.assertEqual(["save_two"], [site[1] for site in _sites(tree, _tmp_string_lines)],
                         "Rule 1 does not see a copy that names its temp file .tmp")
        self.assertEqual(["save"], [site[1] for site in _sites(tree, _temp_call_lines)],
                         "Rule 2 does not see a copy that calls tempfile.mkstemp")
        paths = [path.relative_to(ROOT).as_posix() for path in _source_files()]
        self.assertTrue(all(path.count("/") == 1 for path in paths),
                        f"the walk must read the top level only: {paths}")
        for site in SITES:
            self.assertIn(_module_path(site).relative_to(ROOT).as_posix(), paths)


class TestFormerCopies(unittest.TestCase):
    """Every former copy calls the two owners, and it keeps the bytes it had."""

    def test_the_table_holds_the_five_former_copies(self):
        self.assertEqual(
            ["annotator/shot_clock.py ShotClock._save",
             "annotator/unified_server.py atomic_save",
             "annotator/vod_import.py _atomic_json",
             "src/enroll_from_tracklet.py _write_json",
             "src/store_files.py save_document"],
            sorted(site.name for site in SITES))

    def test_the_byte_owner_builds_the_text_the_five_bodies_build(self):
        """The owner of the format and the five bodies agree, for every option."""
        for site in SITES:
            with self.subTest(site=site.name):
                self.assertEqual(_former_text(site, VALUE).encode(),
                                 _owner_text(site, VALUE).encode(),
                                 f"{site.name}: the body is not the format of the owner")

    def test_only_the_vod_index_sorts_the_keys_of_its_value(self):
        for site in SITES:
            with self.subTest(site=site.name), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "document.json"
                site.drive(target, {"b": 1, "a": 2})
                if site.module in SORTS_KEYS:
                    self.assertEqual('{\n  "a": 2,\n  "b": 1\n}\n', target.read_text(),
                                     f"{site.name}: the keys of the index must be sorted")
                else:
                    self.assertEqual('{\n  "b": 1,\n  "a": 2\n}\n', target.read_text(),
                                     f"{site.name}: the keys must stay in the order of the value")

    def test_only_the_enroll_writer_does_not_fsync(self):
        for site in SITES:
            with self.subTest(site=site.name):
                call = _calls(_resolve(_tree(site), site.qualname),
                              ("write_atomic", "atomic_write.write_atomic"))[0]
                kwargs = {keyword.arg: keyword.value for keyword in call.keywords}
                got = ast.literal_eval(kwargs["fsync"]) if "fsync" in kwargs else None
                self.assertEqual(site.module != "src.enroll_from_tracklet", bool(got),
                                 f"{site.name}: the fsync option changed")

    def test_the_enroll_writer_keeps_the_options_it_had(self):
        site = _site("enroll")
        call = _calls(_resolve(_tree(site), site.qualname),
                      ("write_atomic", "atomic_write.write_atomic"))[0]
        kwargs = {keyword.arg: keyword.value for keyword in call.keywords}
        self.assertEqual("{name}.tmp{pid}", ast.literal_eval(kwargs["temp_name"]),
                         "the temp name of this writer changed")
        self.assertEqual("utf-8", ast.literal_eval(kwargs["encoding"]),
                         "the encoding of this writer changed")
        self.assertEqual(False, ast.literal_eval(kwargs["remove_on_failure"]),
                         "this writer must leave its temp file after a failure")

    def test_the_owner_keeps_the_whole_or_none_contract(self):
        """The two promises that the five writers need from the owner."""
        for kwargs in ({}, {"temp_name": "{name}.tmp{pid}", "encoding": "utf-8",
                            "remove_on_failure": False}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "document.json"
                target.write_bytes(b'{"old": 1}\n')

                def broken(stream):
                    stream.write('{"half"')
                    raise ZeroDivisionError("the disk is full")

                with self.assertRaises(ZeroDivisionError):
                    write_atomic(target, broken, **kwargs)
                self.assertEqual(b'{"old": 1}\n', target.read_bytes(),
                                 "a reader can see a half file")
                write_atomic(target, lambda stream: stream.write('{"new": 1}\n'), **kwargs)
                self.assertEqual(b'{"new": 1}\n', target.read_bytes())


def _ast_case(site, body):
    def test(self):
        tree = _tree(site)
        node = _resolve(tree, site.qualname)
        self.assertIsNotNone(node, f"{site.name}: the function is not in the module source")
        return body(self, site, tree, node)

    test.__doc__ = f"{site.name}: {body.__doc__}"
    test.__name__ = f"test_{site.key}_{body.__name__}"
    return test


def _calls_the_owner_once(self, site, tree, node):
    """it calls write_atomic one time, and the byte owner builds the text."""
    calls = _calls(node, ("write_atomic", "atomic_write.write_atomic"))
    self.assertEqual(1, len(calls), "the function must call write_atomic one time")
    self.assertEqual([], _stray_tmp_lines(node, calls), "the body names its own temp file")
    self.assertEqual([], _temp_call_lines(node), "the body makes its own temp file")
    self.assertEqual([], _rename_lines(node), "the body renames the file by itself")
    # Round 58: the body writes the text of the owner's renderer, and it holds no
    # text builder of its own.  The bytes are still the bytes of the former body,
    # and the case that drives the site proves them.
    self.assertEqual([], _calls(node, ("json.dump",)),
                     "the body must not build the text with json.dump of its own")
    owners = _calls(node, ("dump_document", "store_files.dump_document"))
    self.assertEqual(1, len(owners),
                     "the body must build the text one time with dump_document")
    nested = [child.name for child in ast.walk(node)
              if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child is not node]
    self.assertEqual([], nested, "the body must hold no text function of its own")


def _writes_owner_bytes(self, site, tree, node):
    """the bytes of the file equal the bytes of the owner and the bytes it had."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "a" / "b" / "document.json"
        site.drive(target, VALUE)
        got = target.read_bytes()
        self.assertEqual(_former_text(site, VALUE).encode(), got, "the bytes changed")
        text = _owner_text(site, VALUE)
        owner = Path(tmp) / "owner" / "document.json"
        owner.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(owner, lambda stream: stream.write(text))
        self.assertEqual(owner.read_bytes(), got, "the bytes are not the bytes of the owner")


def _keeps_old_bytes(self, site, tree, node):
    """a value that JSON refuses keeps the old bytes, and the temp file keeps its rule."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "document.json"
        target.write_bytes(b'{"keep": 1}\n')
        with self.assertRaises(ValueError):
            site.drive(target, {"bad": float("nan")})
        self.assertEqual(b'{"keep": 1}\n', target.read_bytes(),
                         "the target changed after a failed render")
        others = sorted(path.name for path in Path(tmp).iterdir() if path.name != "document.json")
        if site.temp_after_failure:
            self.assertEqual(1, len(others), f"the temp file must stay: {others}")
            self.assertRegex(others[0], r"^document\.json\.tmp\d+$")
        else:
            self.assertEqual([], others, f"a temp file stayed: {others}")


def _install_cases(cls):
    """One named case for every former copy: the name of the case shows the site."""
    for site in SITES:
        for body in (_calls_the_owner_once, _writes_owner_bytes, _keeps_old_bytes):
            case = _ast_case(site, body)
            setattr(cls, case.__name__, case)


_install_cases(TestFormerCopies)


if __name__ == "__main__":
    unittest.main()
