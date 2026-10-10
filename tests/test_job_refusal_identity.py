"""The job refusal identity: python owns a code and its sentence, and the console reads them.

Every claim here is measured from the sources, so this module starts no server and touches no
network.  Two kinds of measurement are used:

* the sources are parsed.  Each refusal row in ``annotator/refusals.py`` must have a raise site
  in ``annotator/vod_import.py`` that carries its code, and each code the console branches on
  must name one of those rows.  A row without a raise site is dead.  A console code without a
  row is a guess.
* four refusals are raised through the real raise sites on a temporary root, so their sentences
  are pinned byte for byte.  The download itself is not started.
"""
import ast
from inspect import signature
import json
from pathlib import Path
import re
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from annotator import refusals
from annotator.vod_import import REFUSED_CHANNEL, VodImporter, VodImportError

ROOT = Path(__file__).resolve().parents[1]
REFUSALS = ROOT / "annotator" / "refusals.py"
VOD_IMPORT = ROOT / "annotator" / "vod_import.py"
CONSOLE = ROOT / "annotator" / "ops.js"
STAGE = ROOT / "annotator" / "vision-stage.js"

VOD_ID = "1000000001"
DATASET_ID = "tw-1000000001"
# The five codes this round added, and the frozen sentences they are raised with.
CHANNEL_SENTENCE = ("This VOD belongs to someoneelse. Only saved channels can be analysed; "
                    "add the channel under Source first.")
CHANNEL_ZH = "此回放属于 someoneelse。只能分析已保存的频道；请先在“来源”中添加该频道。"
DISK_SENTENCE = ("Not enough free disk space: this import needs 3.2 GB (about 1.0 GB estimated "
                 "x 1.2 + 2 GB reserve) and 0.0 GB is free. Import a shorter range or free some "
                 "space first.")
DISK_ZH = ("磁盘空间不足：本次导入需要 3.2 GB（按 1.0 GB 估算 × 1.2，另留 2 GB 余量），"
           "当前可用 0.0 GB。请缩短导入范围，或先释放一些空间。")
STARTING_SENTENCE = "An import is already starting; wait for it or cancel it first."
STARTING_ZH = "已有一个导入正在启动，请等待它，或先取消。"
RUNNING_SENTENCE = f"An import is already running ({DATASET_ID}); wait for it or cancel it first."
RUNNING_ZH = "已有一个导入在运行，请等待它结束，或先取消。"
IMPORTED_SENTENCE = f"{DATASET_ID} is already imported; delete it first to import it again."
IMPORTED_ZH = "这一段已经导入；要再次导入，请先删除它。"
EXPECTED_CODES = frozenset({"vod_channel_not_saved", "vod_disk_space", "vod_already_starting",
                            "vod_already_running", "vod_already_imported"})
# The only refusal text a javascript file may hold: the console's own hint for an empty name.
# That hint is a REFUSALS row, not a job refusal.  tests/test_refusal_identity.py prints the
# same map, so a new hint must be a decision in both modules.
ALLOWED_CONSOLE_HINTS = {"annotator/ops.js": {"轮空由抽签自动安排，请输入访客的真实姓名。"}}
# The tokens this round removed: a sentence regex or a console copy of a service sentence.
REMOVED_MATCHERS = ("Only saved channels", "Not enough free disk space", "serverText",
                    "bcOtherChannel", "bfChannel", "bfDiskNo")
# Each reader below states that the console takes the identity the service sends, and not a
# sentence of its own.  The message names the surface that would go dark if the pattern left.
CONSOLE_READERS = {
    "annotator/ops.js": (
        (r"served:body", "the estimate and the import refusals attach the served body"),
        (r"served:job", "the poll and the cancel attach the served job record"),
        (r"bfCode\(job\)", "the polled record's code is read, not its sentence"),
        (r"bf\.code===bfRefusalCodes\.", "the console branches on a code, not on a sentence"),
    ),
    "annotator/vision-stage.js": (
        (r"bcIdentity\(", "the panel reads the identity it was served"),
        (r"error\?\.served", "every thrown panel error carries the served body"),
        (r"bcText\(facts,\s*job\)", "the job line reads the record's identity"),
        (r"bcText\(e\.disk\.refusal,\s*e\.disk\.identity\)", "the estimate reads the disk identity"),
    ),
}


def _tree(path):
    return ast.parse(Path(path).read_text(encoding="utf-8"))


def _placeholders(text):
    """The fact names a template names, in the order the sentence states them."""
    return tuple(re.findall(r"\{(\w+)\}", text))


def _declared_rows():
    """({symbol: code} of the single rows, {key: symbol} of JOB_REFUSALS).

    A row is one ``FactRefusal`` or ``Refusal`` call assigned to a name.  The 48 rows inside
    the ``REFUSALS`` dict are not collected: the sentence is their key, and their test is
    tests/test_refusal_identity.py.
    """
    rows, jobs = {}, {}
    for node in _tree(REFUSALS).body:
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        if isinstance(node.value, ast.Call) and getattr(node.value.func, "id", "") in ("FactRefusal",
                                                                                      "Refusal"):
            rows[target.id] = node.value.args[0].value
        elif getattr(target, "id", "") == "JOB_REFUSALS":
            jobs = {key.value: value.id for key, value in zip(node.value.keys, node.value.values)}
    return rows, jobs


def _builder_functions():
    """{function name in refusals.py: the row symbol it fills} for the fact builders."""
    rows, _ = _declared_rows()
    table = {}
    for node in _tree(REFUSALS).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
        symbols = sorted(names & set(rows))
        if symbols:
            table[node.name] = symbols[0]
    return table


def _builder_code(name):
    """The code a builder returns, measured by calling it with one dummy fact per parameter."""
    builder = getattr(refusals, name)
    facts = [1 if parameter.endswith("_bytes") else "probe" for parameter in signature(builder).parameters]
    return builder(*facts)[1][refusals.CODE_KEY]


def _identity_assignments():
    """{unparsed target: builder} for each assignment that unpacks a builder's pair."""
    builders = _builder_functions()
    table = {}
    for node in ast.walk(_tree(VOD_IMPORT)):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        name = getattr(node.value.func, "id", "")
        if name not in builders:
            continue
        for target in node.targets:
            for part in (target.elts if isinstance(target, ast.Tuple) else [target]):
                table[ast.unparse(part)] = name
    return table


def _identity_raise_sites():
    """[(line, kind, token)] for every raise of VodImportError that carries an identity.

    ``kind`` is ``job`` for an inline ``job_identity("<key>")`` call, else ``builder`` with the
    name of the builder whose ``(sentence, identity)`` pair the raise passes on.
    """
    source = VOD_IMPORT.read_text(encoding="utf-8")
    assignments = _identity_assignments()
    sites = []
    for node in ast.walk(_tree(VOD_IMPORT)):
        if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                and getattr(node.exc.func, "id", "") == "VodImportError"):
            continue
        text = " ".join(ast.get_source_segment(source, node).split())
        inline = re.search(r'job_identity\("([a-z_]+)"', text)
        if inline:
            sites.append((node.lineno, "job", inline.group(1)))
            continue
        passed = list(node.exc.args[1:]) + [keyword.value for keyword in node.exc.keywords]
        for argument in passed:
            builder = assignments.get(ast.unparse(argument))
            if builder:
                sites.append((node.lineno, "builder", builder))
                break
    return sites


def _produced():
    """{code: [line, ...]} and {code: [symbol, ...]} from the raise sites, measured."""
    rows, jobs = _declared_rows()
    builders = _builder_functions()
    lines, symbols = {}, {}
    for line, kind, token in _identity_raise_sites():
        if kind == "job":
            if token not in jobs:
                raise AssertionError(f"line {line} carries an unknown job refusal {token!r}")
            symbol = jobs[token]
            code = refusals.job_identity(token)[refusals.CODE_KEY]
        else:
            if token not in builders:
                raise AssertionError(f"line {line} carries an unknown builder {token!r}")
            symbol = builders[token]
            code = _builder_code(token)
        if code != rows[symbol]:
            raise AssertionError(f"line {line} raises {code}, but {symbol} declares {rows[symbol]}")
        lines.setdefault(code, []).append(line)
        symbols.setdefault(code, []).append(symbol)
    return lines, symbols


def _console_codes():
    """{key: code} of the console's own table of the codes it branches on."""
    source = CONSOLE.read_text(encoding="utf-8")
    table = re.search(r"const bfRefusalCodes=\{([^}]*)\}", source)
    if table is None:
        raise AssertionError("annotator/ops.js holds no bfRefusalCodes table")
    return dict(re.findall(r"([A-Za-z_]\w*):'([a-z0-9_]+)'", table.group(1)))


class RaisedIdentityTests(unittest.TestCase):
    """The sentences and the named facts of the refusals, raised on a temporary root."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def importer(self, **options):
        return VodImporter(self.root, lambda: {"sources": []}, **options)

    def refusal(self, importer, method, *args):
        """Call one raise site and return the refusal it raised."""
        with self.assertRaises(VodImportError) as caught:
            getattr(importer, method)(*args)
        return caught.exception

    def plan(self):
        return {"id": DATASET_ID, "vod_id": VOD_ID,
                "range": {"start_s": 0, "end_s": 60, "whole": False}}

    def test_the_channel_refusal_carries_its_code_and_its_channel(self):
        caught = self.refusal(self.importer(), "thumbnail", "someoneelse", VOD_ID)
        self.assertEqual((str(caught), caught.status), (CHANNEL_SENTENCE, 403))
        self.assertEqual(caught.identity, {"code": "vod_channel_not_saved", "zh": CHANNEL_ZH,
                                           "channel": "someoneelse"})
        # The name the raise sites used before this round still means the same sentence.
        self.assertEqual(REFUSED_CHANNEL.format(channel="someoneelse"), CHANNEL_SENTENCE)

    def test_the_disk_refusal_carries_its_code_and_its_three_numbers(self):
        plan = self.plan()
        importer = self.importer(disk_usage=lambda path: SimpleNamespace(free=1))
        with mock.patch.object(VodImporter, "_plan", lambda self, vod, start_s, duration_s: plan), \
                mock.patch.object(VodImporter, "_resolve",
                                  lambda self, plan: ("https://example.invalid/media.m3u8", {}, 10 ** 9)):
            caught = self.refusal(importer, "start", {"vod": VOD_ID})
        self.assertEqual((str(caught), caught.status), (DISK_SENTENCE, 507))
        self.assertEqual(caught.identity, {"code": "vod_disk_space", "zh": DISK_ZH,
                                           "needed_bytes": 3_200_000_000,
                                           "estimate_bytes": 10 ** 9, "free_bytes": 1})

    def test_the_already_starting_refusal_carries_its_code(self):
        importer = self.importer()
        importer._start_lock.acquire()
        try:
            caught = self.refusal(importer, "start", {"vod": VOD_ID})
        finally:
            importer._start_lock.release()
        self.assertEqual((str(caught), caught.status), (STARTING_SENTENCE, 409))
        self.assertEqual(caught.identity, {"code": "vod_already_starting", "zh": STARTING_ZH})

    def test_the_already_running_refusal_carries_its_code_and_its_id(self):
        importer = self.importer()
        importer._job["state"], importer._job["id"] = "running", DATASET_ID
        caught = self.refusal(importer, "start", {"vod": VOD_ID})
        self.assertEqual((str(caught), caught.status), (RUNNING_SENTENCE, 409))
        self.assertEqual(caught.identity, {"code": "vod_already_running", "zh": RUNNING_ZH,
                                           "id": DATASET_ID})

    def test_the_already_imported_refusal_carries_its_code_and_its_id(self):
        index = self.root / "out" / "vods" / "index.json"
        index.parent.mkdir(parents=True)
        index.write_text(json.dumps({"vods": {DATASET_ID: {"vod_id": VOD_ID}}}), encoding="utf-8")
        media = self.root / "data" / "vods" / f"{DATASET_ID}.mp4"
        media.parent.mkdir(parents=True)
        media.write_bytes(b"")
        plan = self.plan()
        with mock.patch.object(VodImporter, "_plan", lambda self, vod, start_s, duration_s: plan):
            caught = self.refusal(self.importer(), "start", {"vod": VOD_ID})
        self.assertEqual((str(caught), caught.status), (IMPORTED_SENTENCE, 409))
        self.assertEqual(caught.identity, {"code": "vod_already_imported", "zh": IMPORTED_ZH,
                                           "id": DATASET_ID})

    def test_the_job_record_publishes_the_identity_beside_the_sentence(self):
        importer = self.importer()
        importer._job["_t0"] = 0.0
        importer._finish(identity={"code": "vod_disk_space", "zh": DISK_ZH, "free_bytes": 1},
                         state="error", error=DISK_SENTENCE)
        record = importer.job()
        self.assertEqual(record["error"], DISK_SENTENCE)
        self.assertEqual(record["code"], "vod_disk_space")
        self.assertEqual((record["zh"], record["free_bytes"]), (DISK_ZH, 1))
        # A finish with no refusal clears the identity, so a stale code cannot outlive it.
        importer._finish(state="done", error=None)
        self.assertNotIn("code", importer.job())

    def test_a_skipped_item_copies_the_identity_beside_the_sentence(self):
        importer = self.importer()
        row = {"id": DATASET_ID, "state": "queued"}
        importer._auto_finish(row, "skipped", DISK_SENTENCE,
                              identity={"code": "vod_disk_space", "zh": DISK_ZH})
        self.assertEqual((row["error"], row["code"], row["zh"]),
                         (DISK_SENTENCE, "vod_disk_space", DISK_ZH))
        self.assertEqual(importer._auto["skipped"], [row])
        self.assertIsNone(importer._auto["current"])

    def test_the_disk_dict_publishes_an_identity_only_when_it_refuses(self):
        room = self.importer(disk_usage=lambda path: SimpleNamespace(free=10 ** 10))._disk(10 ** 6)
        self.assertTrue(room["ok"])
        self.assertIsNone(room["refusal"])
        self.assertEqual(room["identity"], {})
        tight = self.importer(disk_usage=lambda path: SimpleNamespace(free=1))._disk(10 ** 9)
        self.assertFalse(tight["ok"])
        self.assertEqual(tight["refusal"], DISK_SENTENCE)
        self.assertEqual(tight["identity"]["code"], "vod_disk_space")


class DeclaredCodeTests(unittest.TestCase):
    """The rows, the raise sites and the console: one code, one producer, one reader."""

    def test_every_declared_code_has_a_producing_raise_site(self):
        rows, jobs = _declared_rows()
        self.assertTrue(rows, "refusals.py declares no single row")
        lines, symbols = _produced()
        self.assertEqual(set(lines), set(rows.values()))
        self.assertEqual(set(lines), set(EXPECTED_CODES))
        # Both channel raise sites are kept, so the thumbnail route and the plan agree.
        self.assertEqual(lines["vod_channel_not_saved"], sorted(lines["vod_channel_not_saved"]))
        self.assertEqual(len(lines["vod_channel_not_saved"]), 2)
        for code, names in symbols.items():
            self.assertEqual(set(names), {symbol for symbol, own in rows.items() if own == code})
        self.assertEqual(sorted(jobs), ["already_imported", "already_running", "already_starting"])

    def test_the_console_reads_only_codes_python_can_produce(self):
        lines, _ = _produced()
        codes = _console_codes()
        self.assertEqual(set(codes.values()), {"vod_channel_not_saved", "vod_already_imported"})
        source = CONSOLE.read_text(encoding="utf-8")
        for key, code in codes.items():
            self.assertIn(code, lines, f"the console reads {code}, but no raise site sends it")
            self.assertIn(f"bf.code===bfRefusalCodes.{key}", source,
                          f"{key} is declared, but no branch reads it")

    def test_no_javascript_file_holds_a_refusal_sentence(self):
        texts = set(refusals.REFUSALS) | {row.zh for row in refusals.REFUSALS.values()}
        texts |= {refusals.CHANNEL_REFUSAL.en, refusals.CHANNEL_REFUSAL.zh,
                  refusals.DISK_REFUSAL.en, refusals.DISK_REFUSAL.zh}
        texts |= {row.zh for row in refusals.JOB_REFUSALS.values()}
        held, removed = {}, {}
        for path in sorted((ROOT / "annotator").glob("*.js")):
            name, source = f"annotator/{path.name}", path.read_text(encoding="utf-8")
            for text in texts:
                if text and text in source:
                    held.setdefault(name, set()).add(text)
            for token in REMOVED_MATCHERS:
                if token in source:
                    removed.setdefault(name, set()).add(token)
        self.assertEqual(held, ALLOWED_CONSOLE_HINTS)
        self.assertEqual(removed, {})

    def test_the_console_reads_the_identity_it_was_served(self):
        for name, readers in CONSOLE_READERS.items():
            source = (ROOT / name).read_text(encoding="utf-8")
            for pattern, why in readers:
                self.assertRegex(source, pattern, f"{name}: {why}")

    def test_each_template_fills_its_facts_and_leaves_no_placeholder(self):
        self.assertEqual(refusals.CHANNEL_REFUSAL.fields, ("channel",))
        # The disk facts carry the unit in their name; the sentence names the slot without it.
        self.assertEqual(refusals.DISK_REFUSAL.fields,
                         ("needed_bytes", "estimate_bytes", "free_bytes"))
        for row in (refusals.CHANNEL_REFUSAL, refusals.DISK_REFUSAL):
            slots = _placeholders(row.en)
            self.assertEqual(slots, _placeholders(row.zh), f"{row.code}: both languages")
            self.assertEqual(len(slots), len(row.fields), f"{row.code}: one slot per fact")
            for slot, fact in zip(slots, row.fields):
                self.assertTrue(fact.startswith(slot), f"{row.code}: {slot} names {fact}")
        self.assertEqual(_placeholders(refusals.DISK_REFUSAL.zh), ("needed", "estimate", "free"))

    def test_a_builder_fills_both_languages_from_one_set_of_facts(self):
        sentence, identity = refusals.channel_refusal("someoneelse")
        self.assertEqual((sentence, identity["zh"]), (CHANNEL_SENTENCE, CHANNEL_ZH))
        self.assertEqual((identity["code"], identity["channel"]),
                         ("vod_channel_not_saved", "someoneelse"))
        self.assertNotIn("{", sentence + identity["zh"])
        unnamed_sentence, unnamed = refusals.channel_refusal("")
        self.assertEqual(unnamed_sentence, REFUSED_CHANNEL.format(channel="a channel Twitch did not name"))
        self.assertIn("a channel Twitch did not name", unnamed["zh"])
        disk_sentence, disk = refusals.disk_refusal(3_200_000_000, 10 ** 9, 1)
        self.assertEqual((disk_sentence, disk["zh"]), (DISK_SENTENCE, DISK_ZH))
        self.assertEqual((disk["code"], disk["needed_bytes"], disk["estimate_bytes"], disk["free_bytes"]),
                         ("vod_disk_space", 3_200_000_000, 10 ** 9, 1))
        self.assertNotIn("{", disk_sentence + disk["zh"])
        # One home for the byte text, so the sentence and the named facts cannot drift apart.
        self.assertEqual(refusals.gb(8_606_363_471), "8.6 GB")
        self.assertEqual(refusals.gb(52_196_323_328), "52.2 GB")


if __name__ == "__main__":
    unittest.main()
