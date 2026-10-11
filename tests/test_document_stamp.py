"""One module owns the document stamp protocol, and both readers answer it.

`src/sam3_artifact.py` stamps the ball rows of `sam3_results.json`.
`src/events_document.py` stamps the rows of `events.json`.  The two documents
hold different rows.  Before this change each reader held its own copy of the
stamp protocol, and the two copies drifted: one row stamped
`{"document": {"version": 1, "producer": "src/gone.py"}}` read `mixed` with no
producer in the first reader, and `stamped` with the producer `src/gone.py` in
the second.

This suite holds three things:

  * `OwnerTest` reads the source of `src/` with `ast`.  Only
    `src/document_stamp.py` defines a protocol name, and only it holds a
    producer name.
  * `AgreementTest` forges one document in both shapes and compares the status,
    the version and the producer of the two readers.
  * `ForeignStampTest` holds the exact row that the two readers disagreed on.

The forged files go under /tmp through `tempfile.mkdtemp`.  No test writes
inside the repository.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest

import src.document_stamp as document_stamp
import src.events_document as events_document
import src.sam3_artifact as sam3_artifact
from src.document_stamp import (BALL_ROW_PRODUCERS, DENSE_QUEUE, EVAL_EVENTS, FOREIGN, MIXED,
                                NAMED, PRODUCERS, REBUILD_CALIBRATED, REBUILD_V2, SCAN_EVENTS,
                                STAMP, STAMPED, UNSTAMPED, VERSION)

ROOT = Path(__file__).resolve().parents[1]
OWNER = "src/document_stamp.py"

#: The names of the protocol.  A module of `src/` other than the owner may hold
#: one of them only when it reads the value from `document_stamp`.
PROTOCOL_NAMES = ("VERSION", "STAMP", "STAMPED", "MIXED", "UNSTAMPED",
                  "SCAN_EVENTS", "REBUILD_CALIBRATED", "REBUILD_V2", "DENSE_QUEUE",
                  "EVAL_EVENTS", "PRODUCERS")

#: The producer names, the five module paths.  Each one is a string literal, so a
#: scan for a string constant finds a second copy of one.
PRODUCER_NAMES = (SCAN_EVENTS, REBUILD_CALIBRATED, REBUILD_V2, DENSE_QUEUE, EVAL_EVENTS)

#: A module that wrote rows once and that no longer exists.  This exact name made
#: the two readers disagree.
GONE = "src/gone.py"

#: (label, the value of the stamp key of a row, the answer of both readers).
#: Every case here holds a stamp that both documents read in the same way.
AGREEING_STAMPS = (
    ("a producer of both documents",
     {"version": VERSION, "producer": SCAN_EVENTS}, (STAMPED, VERSION, SCAN_EVENTS)),
    ("a name that no module holds",
     {"version": VERSION, "producer": GONE}, (MIXED, None, None)),
    ("a stamp with no producer name",
     {"version": VERSION}, (MIXED, None, None)),
    ("a stamp with no version",
     {"producer": SCAN_EVENTS}, (MIXED, None, None)),
    ("a version that is not an integer",
     {"version": "1", "producer": SCAN_EVENTS}, (MIXED, None, None)),
    ("a stamp that is a number", 7, (UNSTAMPED, None, None)),
    ("a stamp that is a list", [], (UNSTAMPED, None, None)),
    ("no stamp at all", None, (UNSTAMPED, None, None)),
)


def _source_paths() -> list:
    """(path from the root, source) for every Python module of `src/`."""
    return [(f"src/{path.name}", path.read_text())
            for path in sorted((ROOT / "src").glob("*.py"))]


def _module_level_bindings(source: str) -> dict:
    """name -> the source text of the value, for each protocol name at top level."""
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in PROTOCOL_NAMES:
                    found[target.id] = ast.unparse(node.value)
    return found


def _definitions_outside_the_owner(module: str, source: str) -> list:
    """(name, value) for each protocol name that `module` defines itself.

    The owner defines the protocol.  A reader may hold one name only when its
    value is a read from the owner, so the text of the value names
    `document_stamp`.
    """
    if module == OWNER:
        return []
    return [(name, value) for name, value in _module_level_bindings(source).items()
            if "document_stamp" not in value]


def _producer_literals(source: str) -> list:
    """Every producer name that appears as a string constant in `source`."""
    return sorted({node.value for node in ast.walk(ast.parse(source))
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)
                   and node.value in PRODUCER_NAMES})


def _write_json(path: Path, payload) -> Path:
    """Write one forged document and return its path."""
    path.write_text(json.dumps(payload, indent=1))
    return path


def _ball_row(entry) -> dict:
    """One ball row of the artifact, with `entry` as its stamp."""
    row = {"img": [640.0, 360.0], "table_mm": [1234.5, 321.0]}
    if entry is not None:
        row[STAMP] = entry
    return row


def _event_row(entry) -> dict:
    """One row of the events document, with `entry` as its stamp."""
    row = {"t": 1352.0, "type": "shot"}
    if entry is not None:
        row[STAMP] = entry
    return row


def _forge(directory: Path, balls: list, events: list) -> tuple:
    """Write one document of each shape under `directory`, and return both paths."""
    return (_write_json(directory / sam3_artifact.ARTIFACT, {"1.0": balls}),
            _write_json(directory / events_document.SERVED, events))


def _triple(document) -> tuple:
    """The answer of a reader: its status, its version and its producer."""
    return (document.status, document.version, document.producer)


class OwnerTest(unittest.TestCase):
    """The protocol has one definition site, and both readers read it there."""

    def test_only_the_owner_defines_a_protocol_name(self):
        for module, source in _source_paths():
            with self.subTest(module=module):
                self.assertEqual(
                    _definitions_outside_the_owner(module, source), [],
                    f"{module} defines a protocol name; read it from {OWNER}")

    def test_the_guard_refuses_a_second_definition(self):
        """A forged module shows that the guard above is not vacuous."""
        forged = "VERSION = 1\nSTAMP = 'document'\nPRODUCERS = {}\nROW_KEYS = ('t',)\n"
        self.assertEqual([name for name, _ in _definitions_outside_the_owner("src/other.py",
                                                                            forged)],
                         ["VERSION", "STAMP", "PRODUCERS"])
        self.assertEqual(_definitions_outside_the_owner(OWNER, forged), [],
                         "the owner is the one module that defines the protocol")

    def test_only_the_owner_holds_a_producer_name(self):
        for module, source in _source_paths():
            with self.subTest(module=module):
                if module == OWNER:
                    self.assertEqual(_producer_literals(source), sorted(PRODUCER_NAMES),
                                     "the owner states every producer name once")
                else:
                    self.assertEqual(_producer_literals(source), [],
                                     f"{module} holds a producer name; read it from {OWNER}")

    def test_the_owner_reads_nothing_from_the_package(self):
        """A leaf module cannot take part in an import cycle."""
        tree = ast.parse((ROOT / OWNER).read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        self.assertEqual([name for name in imported if name.startswith("src")], [],
                         "the owner imports nothing from src/, so both readers can import it")

    def test_the_owner_states_the_rule_and_the_row_that_broke_it(self):
        text = (ROOT / OWNER).read_text()
        self.assertIn("The rule, in one sentence", text,
                      "the owner states the honest rule in one sentence")
        self.assertIn(GONE, text, "the owner records the row that the two readers disagreed on")

    def test_both_readers_hold_the_protocol_of_the_owner(self):
        self.assertEqual((sam3_artifact.VERSION, sam3_artifact.STAMP),
                         (document_stamp.VERSION, document_stamp.STAMP))
        self.assertEqual((events_document.VERSION, events_document.STAMP),
                         (document_stamp.VERSION, document_stamp.STAMP))
        self.assertEqual(
            (sam3_artifact.STAMPED, sam3_artifact.MIXED, sam3_artifact.UNSTAMPED),
            (document_stamp.STAMPED, document_stamp.MIXED, document_stamp.UNSTAMPED))
        self.assertEqual(
            (events_document.STAMPED, events_document.MIXED, events_document.UNSTAMPED),
            (document_stamp.STAMPED, document_stamp.MIXED, document_stamp.UNSTAMPED))

    def test_the_two_documents_keep_their_own_producer_sets(self):
        """The event document takes every producer; the artifact takes the ball rows."""
        self.assertEqual(set(sam3_artifact.PRODUCERS), set(BALL_ROW_PRODUCERS))
        self.assertEqual(set(events_document.PRODUCERS), set(PRODUCERS))
        self.assertLess(set(sam3_artifact.PRODUCERS), set(events_document.PRODUCERS),
                        "the two sets differ on purpose, and one holds the other")
        self.assertEqual(sam3_artifact.CAMERA_MODEL, SCAN_EVENTS)
        self.assertEqual(sam3_artifact.REBUILD_CALIBRATED, REBUILD_CALIBRATED)
        self.assertEqual(sam3_artifact.PRODUCERS[SCAN_EVENTS], PRODUCERS[SCAN_EVENTS],
                         "one producer name carries one rule set")


class AgreementTest(unittest.TestCase):
    """Both readers answer one forged document in one way."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _both(self, entry) -> tuple:
        """The two readers over one row of each shape, with the same stamp."""
        balls, events = _forge(self.tmp, [_ball_row(entry)], [_event_row(entry)])
        return sam3_artifact.read(balls), events_document.read(events)

    def test_the_two_readers_agree_on_every_stamp_of_both_documents(self):
        for label, entry, answer in AGREEING_STAMPS:
            with self.subTest(case=label):
                artifact, document = self._both(entry)
                self.assertEqual(_triple(artifact), answer)
                self.assertEqual(_triple(document), answer)

    def test_a_producer_of_the_event_document_is_foreign_to_the_artifact(self):
        """The artifact holds ball rows only, so three producers are not its own."""
        for name in (REBUILD_V2, DENSE_QUEUE, EVAL_EVENTS):
            with self.subTest(producer=name):
                artifact, document = self._both({"version": VERSION, "producer": name})
                self.assertEqual(_triple(artifact), (MIXED, None, None))
                self.assertEqual((artifact.producers, artifact.foreign), ((), 1))
                self.assertEqual(_triple(document), (STAMPED, VERSION, name))

    def test_the_two_readers_count_one_mixed_document_in_one_way(self):
        """Four rows: one named, two with a stamp that names nothing, one bare."""
        entries = [{"version": VERSION, "producer": SCAN_EVENTS},
                   {"version": VERSION, "producer": GONE},
                   {"version": VERSION},
                   None]
        balls, events = _forge(self.tmp, [_ball_row(entry) for entry in entries],
                               [_event_row(entry) for entry in entries])
        artifact, document = sam3_artifact.read(balls), events_document.read(events)
        self.assertEqual(_triple(artifact), (MIXED, None, None))
        self.assertEqual(_triple(document), (MIXED, None, None))
        self.assertEqual(artifact.producers, (SCAN_EVENTS,))
        self.assertEqual(document.producers, (SCAN_EVENTS,))
        self.assertEqual((artifact.unstamped, document.unstamped), (1, 1))
        self.assertEqual((artifact.foreign, document.foreign), (2, 2))
        self.assertIn(SCAN_EVENTS, artifact.describe())
        self.assertIn("foreign", document.describe(),
                      "a mixed document says what it is mixed of")

    def test_the_two_readers_agree_on_an_empty_document(self):
        balls, events = _forge(self.tmp, [], [])
        self.assertEqual(_triple(sam3_artifact.read(balls)), (UNSTAMPED, None, None))
        self.assertEqual(_triple(events_document.read(events)), (UNSTAMPED, None, None))

    def test_both_readers_refuse_a_newer_version(self):
        """A reader keeps its own exception type for a version it cannot read."""
        balls, events = _forge(self.tmp, [_ball_row({"version": VERSION + 1,
                                                     "producer": SCAN_EVENTS})],
                               [_event_row({"version": VERSION + 1,
                                            "producer": SCAN_EVENTS})])
        with self.assertRaises(sam3_artifact.ArtifactVersionError):
            sam3_artifact.read(balls)
        with self.assertRaises(events_document.DocumentVersionError):
            events_document.read(events)
        self.assertFalse(issubclass(sam3_artifact.ArtifactVersionError, ValueError))
        self.assertFalse(issubclass(events_document.DocumentVersionError, ValueError))


class ForeignStampTest(unittest.TestCase):
    """The row that the two readers disagreed on, and its neighbours.

    Before `src/document_stamp.py`, this row read `mixed` with no producer in
    `src/sam3_artifact.py` and `stamped` with the producer `src/gone.py` in
    `src/events_document.py`, though no table of that module held the name.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _both(self, entry) -> tuple:
        balls, events = _forge(self.tmp, [_ball_row(entry)], [_event_row(entry)])
        return sam3_artifact.read(balls), events_document.read(events)

    def test_the_row_that_the_two_readers_disagreed_on(self):
        artifact, document = self._both({"version": VERSION, "producer": GONE})
        self.assertEqual(_triple(artifact), (MIXED, None, None))
        self.assertEqual(_triple(document), (MIXED, None, None))
        self.assertNotEqual(document.status, STAMPED,
                            "a name outside the producer set is not a producer")
        self.assertEqual((artifact.producers, document.producers), ((), ()),
                         "a foreign name never enters the producer list")
        self.assertEqual((artifact.foreign, document.foreign), (1, 1))

    def test_a_stamp_with_no_producer_name_is_not_stamped(self):
        artifact, document = self._both({"version": VERSION})
        self.assertEqual(_triple(artifact), (MIXED, None, None))
        self.assertEqual(_triple(document), (MIXED, None, None))
        self.assertEqual((artifact.foreign, document.foreign), (1, 1))

    def test_the_gone_module_is_not_a_producer_of_either_document(self):
        self.assertFalse(document_stamp.is_producer(GONE))
        self.assertNotIn(GONE, PRODUCERS)
        self.assertNotIn(GONE, BALL_ROW_PRODUCERS)
        self.assertNotIn(GONE, sam3_artifact.PRODUCERS)
        self.assertNotIn(GONE, events_document.PRODUCERS)

    def test_the_owner_rule_reads_one_stamp_and_one_document(self):
        """One sentence holds the rule: the version, and a name of the set."""
        for entry in ({"version": VERSION, "producer": GONE}, {"version": VERSION},
                      {"version": "1", "producer": SCAN_EVENTS}, {}):
            with self.subTest(entry=entry):
                self.assertEqual(document_stamp.classify(entry), FOREIGN)
        self.assertEqual(document_stamp.classify(None), UNSTAMPED)
        self.assertEqual(document_stamp.classify({"version": VERSION,
                                                  "producer": SCAN_EVENTS}), NAMED)
        self.assertEqual(document_stamp.status([], unstamped=0, foreign=0), (UNSTAMPED, None))
        self.assertEqual(document_stamp.status([], unstamped=1, foreign=0), (UNSTAMPED, None))
        self.assertEqual(document_stamp.status([SCAN_EVENTS], unstamped=0, foreign=0),
                         (STAMPED, SCAN_EVENTS))
        self.assertEqual(document_stamp.status([SCAN_EVENTS], unstamped=1, foreign=0),
                         (MIXED, None))
        self.assertEqual(document_stamp.status([SCAN_EVENTS], unstamped=0, foreign=1),
                         (MIXED, None))
        self.assertEqual(document_stamp.status([SCAN_EVENTS, REBUILD_CALIBRATED],
                                               unstamped=0, foreign=0), (MIXED, None))
