"""The retention bound of the operations event log: one owner, and every trim reads it.

The operations log lives in two places, and they keep different history on purpose:

  * the document `out/corner-pocket/state.json` shows the newest rows only, so the
    file a browser downloads and the document the database stores stay small;
  * the `ops_events` table keeps every row ever written.

Before this change the number was written at four code sites in four modules:

  * `annotator/operations.py:394` - the slice `[-500:]` of `_commit`;
  * `src/enroll_from_tracklet.py:483` - the slice `[-500:]` of `_roster_payload`;
  * `src/store_import.py:47` - `MAX_EVENTS = 500`;
  * `src/store_pg.py:38` - `MAX_EVENTS = 500`.

Two modules that must agree each held their own constant, so changing one of them
alone changed the bound of one writer and left the others at the old value.  Nothing
failed.  A fifth literal, `LIMIT 500`, sits in `src/store_check.py:66`.

`src/ops_event_log.py` is now the only owner of the number.  It is a new module and
not `src/events_document.py`, because that module owns a different document: its rows
carry `t` and `type`, and its own scope says "it does not decide which rows are
events, and it does not delete a row" (`src/events_document.py:37`).  An operations
event carries `revision`, `action` and `context` and no `type`, so that module
refuses it (`test_the_operations_log_is_not_an_events_document` measures this).

This file holds the census and the guards:

  * `census_report()` answers every place the bound is written, with file and line; no
    line of this file is a print statement, so the proof command is one line:
    `PYTHONPATH=. .venv/bin/python -c "import sys; sys.path.insert(0, 'tests'); import
    test_event_retention as t; sys.stdout.write(t.census_report())"`;
  * `test_no_module_outside_the_owner_writes_the_bound` reads `src/`, `annotator/`,
    `tools/` and `scripts/` with `ast` and fails, naming file and line, when a
    literal spelling of the number appears next to a slice, a `LIMIT` or a
    retention-named constant outside the owner;
  * `test_a_trim_keeps_exactly_the_owners_bound` writes the bound plus one row
    through the two real writers and asserts the newest rows survive.

The guard compares against the owner's live value, so it keeps working when the
value changes.  It is exact for the value this repository froze (500): measured on
2026-10-05, `[-500:]`, `[:500]` and `LIMIT 500` occur nowhere else in the four
directories (`[-2:]` and `[-1:]` appear in `src/sam3/`, and 2 is not the bound).
"""
from __future__ import annotations

import ast
import json
import re
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER = "src/ops_event_log.py"
OWNER_MODULE = "src.ops_event_log"
SCOPE = ("src", "annotator", "tools", "scripts")

#: The names a module would use if it kept its own copy of the bound.
RETENTION_NAMES = frozenset({
    "MAX_EVENTS", "MAX_EVENT_LOG", "MAX_EVENTS_KEPT",
    "EVENT_LIMIT", "EVENT_LOG_LIMIT", "EVENTS_LIMIT",
})

#: `LIMIT 500` in a string, but not `LIMIT %s` (a parameter) and not `LIMIT 50`.
LIMIT_LITERAL = re.compile(r"LIMIT\s+(\d+)\b", re.IGNORECASE)

#: A literal spelling the owner does not write, which this change may not remove.
#: The key is (path, kind, matched text), so an entry that stops matching fails.
OUTSIDE_THE_OWNERS_WRITE_SCOPE = {
    ("src/store_check.py", "LIMIT", "LIMIT 500"):
        "src/store_check.py:65-66 reads the newest rows of the live ops_events table for its "
        "projection check.  That file is outside the files this change may write, so the "
        "literal stays.  It agrees with the owner today (500).  Recorded, not changed.",
}


@dataclass(frozen=True)
class Site:
    """One place a source file writes the bound, or reads the owner's name."""
    path: str
    line: int
    kind: str          # CONSTANT | SLICE | LIMIT | NAME
    match: str         # the matched text
    text: str          # the source line

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}"

    @property
    def key(self) -> tuple:
        return (self.path, self.kind, self.match)

    def describe(self) -> str:
        return f"{self.where:<40} {self.kind:<9} {self.match:<14} {self.text}"


# -- reading the source ---------------------------------------------------------
def _number(node):
    """The integer a node holds, signed, or None.  `-500` is a UnaryOp."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _number(node.operand)
        return None if inner is None else -inner
    return None


def _retention_name(node):
    """The retention name a node carries, or None."""
    if isinstance(node, ast.Name) and node.id in RETENTION_NAMES:
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in RETENTION_NAMES:
        return node.attr
    return None


def scan(path: Path, number) -> list:
    """Every bound site of one Python file, sorted by line.

    A site is a retention-named constant bound to `number`, a slice bound equal to
    `number`, a string that spells `LIMIT <number>`, or a read of a retention name.
    """
    rel = path.relative_to(ROOT).as_posix()
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    sites = []

    def add(node, kind, match):
        line = getattr(node, "lineno", 0)
        text = lines[line - 1].strip() if 0 < line <= len(lines) else ""
        sites.append(Site(rel, line, kind, match, text))

    for node in ast.walk(ast.parse(source, filename=str(path))):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if number is not None and _number(node.value) == number:
                for target in targets:
                    if _retention_name(target):
                        add(node, "CONSTANT", _retention_name(target))
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            for bound in (node.slice.lower, node.slice.upper):
                if bound is None:
                    continue
                if _retention_name(bound):
                    add(bound, "NAME", _retention_name(bound))
                elif number is not None and _number(bound) is not None and abs(_number(bound)) == number:
                    add(bound, "SLICE", ast.unparse(bound))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found = LIMIT_LITERAL.search(node.value)
            if found and number is not None and int(found.group(1)) == number:
                add(node, "LIMIT", f"LIMIT {found.group(1)}")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if _retention_name(node):
                add(node, "NAME", _retention_name(node))
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            if _retention_name(node):
                add(node, "NAME", _retention_name(node))
    return sorted(sites, key=lambda site: (site.path, site.line, site.kind))


def scope_files():
    """Every Python file of the four directories, in a stable order."""
    for directory in SCOPE:
        base = ROOT / directory
        if base.is_dir():
            yield from sorted(base.rglob("*.py"))


def scope_sites(number) -> list:
    """Every bound site outside the owner."""
    owner = (ROOT / OWNER).resolve()
    sites = []
    for path in scope_files():
        if path.resolve() == owner:
            continue
        sites.extend(scan(path, number))
    return sites


def prose_sites(number, known) -> list:
    """Lines that name the number and an event, and are not code sites."""
    lines = set()
    for path in scope_files():
        rel = path.relative_to(ROOT).as_posix()
        for line, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if (rel, line) in known or str(number) not in text or "event" not in text.lower():
                continue
            lines.add(Site(rel, line, "PROSE", str(number), text.strip()))
    return sorted(lines, key=lambda site: (site.path, site.line))


def owner_module():
    """The owner module, imported.  Fails loudly when the owner is missing."""
    from importlib import import_module
    return import_module(OWNER_MODULE)


def owner_number():
    return owner_module().MAX_EVENTS


def owner_site() -> str:
    """`src/ops_event_log.py:NN` - the line that defines the bound."""
    sites = [site for site in scan(ROOT / OWNER, owner_number()) if site.kind == "CONSTANT"]
    return sites[0].where if sites else OWNER


def census_report(number=None) -> str:
    """The bound's sites, as text.  The proof for the report."""
    named = "the owner" if number is None else "given"
    number = owner_number() if number is None else number
    owner_sites = scan(ROOT / OWNER, number) if (ROOT / OWNER).exists() else []
    outside = scope_sites(number)
    written = [site for site in outside if site.kind != "NAME"]
    read = [site for site in outside if site.kind == "NAME"]
    known = {(site.path, site.line) for site in owner_sites + outside}
    prose = prose_sites(number, known)
    out = [f"retention bound {number} ({named}); owner {OWNER}",
           f"literal spellings outside the owner: {len(written)}"]
    out += [f"  {site.describe()}" for site in written]
    out.append(f"reads of the owner's name outside the owner: {len(read)}")
    out += [f"  {site.describe()}" for site in read]
    out.append(f"the owner writes the number {len([s for s in owner_sites if s.kind != 'NAME'])} time(s):")
    out += [f"  {site.describe()}" for site in owner_sites]
    out.append(f"prose lines that name the number and an event: {len(prose)}")
    out += [f"  {site.describe()}" for site in prose]
    return "\n".join(out)


# -- the fakes the database tests read ------------------------------------------
class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _Recorder:
    """A connection that records its SQL and answers the counts it is asked for."""

    def __init__(self, events: int = 0):
        self.events = events
        self.queries = []

    def execute(self, sql, params=()):
        self.queries.append((" ".join(sql.split()), params))
        if "count(*)" in sql:
            return _Result([(self.events if "ops_events" in sql else 0,)])
        if "FROM ops_meta" in sql:
            return _Result([(7, {}, {})])
        return _Result([])


# -- the guards -----------------------------------------------------------------
class OneOwnerTest(unittest.TestCase):
    """The number is written once, in src/ops_event_log.py."""

    def test_the_owner_writes_the_number_once(self):
        number = owner_number()
        sites = scan(ROOT / OWNER, number)
        spellings = [(site.kind, site.match, site.line) for site in sites if site.kind != "NAME"]
        self.assertEqual(
            [kind for kind, _, _ in spellings], ["CONSTANT"],
            f"the owner must write the bound exactly once, as a constant: {spellings}")
        self.assertEqual(spellings[0][1], "MAX_EVENTS",
                         f"the owner's constant is named MAX_EVENTS: {spellings[0]}")
        self.assertTrue([site for site in sites if site.kind == "NAME"],
                        f"{OWNER} must read its own name where it trims, not the literal")

    def test_no_module_outside_the_owner_writes_the_bound(self):
        number = owner_number()
        written = [site for site in scope_sites(number) if site.kind != "NAME"]
        unexplained = [site for site in written if site.key not in OUTSIDE_THE_OWNERS_WRITE_SCOPE]
        message = (f"a second spelling of the retention bound {number} exists outside {OWNER}; "
                   f"every trim must read {owner_site()}: "
                   + "; ".join(f"{site.where} {site.kind} {site.match!r}" for site in unexplained))
        self.assertEqual([site.where for site in unexplained], [], message)
        self.assertEqual(
            sorted(site.key for site in written), sorted(OUTSIDE_THE_OWNERS_WRITE_SCOPE),
            f"the recorded exceptions must be exactly the spellings that exist; found "
            f"{[site.where for site in written]}, recorded "
            f"{[key[0] + ' ' + key[2] for key in OUTSIDE_THE_OWNERS_WRITE_SCOPE]}")

    def test_every_recorded_exception_is_still_a_site(self):
        found = {site.key for site in scope_sites(owner_number())}
        stale = [key for key in OUTSIDE_THE_OWNERS_WRITE_SCOPE if key not in found]
        self.assertEqual(stale, [],
                         f"a recorded exception no longer matches any site, so it must go: "
                         f"{[key[0] + ' ' + key[2] for key in stale]}")


class TheTrimTest(unittest.TestCase):
    """A trim keeps exactly the owner's newest rows, in order."""

    def test_the_owner_trim_keeps_the_newest_rows_in_order(self):
        from src.ops_event_log import trim
        bound = owner_number()
        rows = [{"revision": revision} for revision in range(1, bound + 3)]
        self.assertEqual(trim([]), [], "an empty log stays empty")
        self.assertEqual(trim(rows[:3]), rows[:3], "a short log is not changed")
        self.assertEqual(trim(rows[:bound]), rows[:bound], "a log at the bound is not changed")
        kept = trim(rows[:bound + 1])
        self.assertEqual(len(kept), bound, f"a trim keeps {bound} rows ({owner_site()})")
        self.assertEqual(kept, rows[1:bound + 1], "a trim drops the oldest row and keeps the order")
        self.assertIsNot(kept, rows, "a trim answers a new list, as the slices did")

    def test_a_trim_keeps_exactly_the_owners_bound(self):
        """Write the bound plus one row through the two real writers.

        Writer 1 is `Operations.post`, the commit path of `annotator/operations.py`.
        Writer 2 is `_roster_payload`, the roster path of `src/enroll_from_tracklet.py`.
        Each must leave the newest `MAX_EVENTS` rows, oldest first.
        """
        from annotator.operations import Operations
        from src.enroll_from_tracklet import _roster_payload
        bound = owner_number()
        writer = f"a trim keeps the newest {bound} rows ({owner_site()}: MAX_EVENTS = {bound})"

        with tempfile.TemporaryDirectory() as tmp:
            ops = Operations(Path(tmp))
            for revision in range(bound + 1):
                ops.post({"action": "settings_update", "revision": revision, "shotClock": 30})
            state = ops.get()
            kept = state["events"]
            self.assertEqual(kept[-1]["revision"], bound + 1,
                             f"{writer}; the last kept row is the row the writer just added")
            self.assertEqual(len(kept), bound, f"{writer}, not {len(kept)}")
            self.assertEqual([row["revision"] for row in kept], list(range(2, bound + 2)),
                             f"{writer}; the first kept row is the 2nd oldest of the {bound + 1} "
                             f"written, and no row inside the window is lost")
            self.assertEqual(json.loads(ops.path.read_text())["events"], kept,
                             "the file on disk holds the rows the writer kept")

        seeded = [{"id": f"e{revision}", "createdAt": "2026-01-01T00:00:00+00:00",
                   "revision": revision, "action": "note_add", "context": {}}
                  for revision in range(1, bound + 1)]
        payload = _roster_payload(
            {"revision": bound, "players": [], "events": seeded},
            {"id": "p1", "name": "Ada"},
            {"track_id": 7, "kept": 3, "kept_frame_indices": [1, 2, 3]})
        self.assertEqual(len(payload["events"]), bound, f"{writer}, not {len(payload['events'])}")
        self.assertEqual(payload["events"][-1]["revision"], bound + 1,
                         "the roster writer keeps the row it just added")
        self.assertEqual(payload["events"][0], seeded[1],
                         f"{writer}; the roster writer drops the oldest row only, so the first "
                         f"kept row is the 2nd oldest of the {bound + 1} written")

    def test_the_file_reader_answers_every_row_the_file_holds(self):
        """The bound is a write rule.  The reader returns the file, so one owner is enough."""
        from annotator.operations import Operations
        bound = owner_number()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops = Operations(root)
            state = ops.get()
            state["revision"] = bound + 1
            state["events"] = [{"id": f"e{revision}", "createdAt": "2026-01-01T00:00:00+00:00",
                                "revision": revision, "action": "note_add", "context": {}}
                               for revision in range(1, bound + 2)]
            ops.path.parent.mkdir(parents=True, exist_ok=True)
            ops.path.write_text(json.dumps(state))
            read = Operations(root).get()["events"]
            self.assertEqual(len(read), bound + 1,
                             "a file a writer never trimmed is read as it is; the reader does not "
                             "enforce the bound, so no second copy of the number is needed here")
            self.assertEqual(read, json.loads(ops.path.read_text())["events"])


class TheDatabaseTest(unittest.TestCase):
    """The document keeps the bound; the table keeps every row.  Both are recorded."""

    def test_the_database_renderer_asks_for_the_owners_bound(self):
        """`OperationsSet.render` builds the document from the table: it asks the database
        for the newest rows, with the owner's number as its parameter."""
        from src.store_import import OperationsSet
        conn = _Recorder(events=0)
        document = OperationsSet().render(conn)
        asked = [(sql, params) for sql, params in conn.queries if "ops_events" in sql]
        self.assertEqual(len(asked), 1, f"one query reads the log: {[sql for sql, _ in asked]}")
        sql, params = asked[0]
        self.assertEqual(params, (owner_number(),),
                         f"the renderer must pass the owner's number ({owner_site()})")
        self.assertIn("ORDER BY revision DESC LIMIT %s", sql,
                      "the newest rows are read first, and the bound is a parameter")
        self.assertTrue(sql.rstrip().endswith("last ORDER BY revision"),
                        "the rows are then returned oldest first, as the file holds them")
        self.assertEqual(document["events"], [], "the fake table holds no row")

    def test_the_table_keeps_every_row_while_the_count_reports_the_bound(self):
        """Recorded disagreement: `OperationsSet.write` inserts every row of the document,
        so the table is unbounded, and `OperationsSet.actual` reports at most the bound
        (src/store_import.py:177) while `OperationsSet.expected` counts the document with
        no cap (src/store_import.py:331).  The value 500 is not asserted here; it is pinned
        by tests/test_operations.py:308."""
        from src.store_import import OperationsSet
        bound = owner_number()
        document = {"revision": 1, "players": [], "settings": {}, "notes": [], "sources": [],
                    "tournament": {"id": "t1", "name": "T", "entrants": []},
                    "events": [{"id": f"e{n}", "revision": n, "action": "note_add", "context": {}}
                               for n in range(1, bound + 101)]}
        writer = _Recorder()
        OperationsSet().write(writer, document)
        inserted = [sql for sql, _ in writer.queries if sql.startswith("INSERT INTO ops_events")]
        self.assertEqual(len(inserted), bound + 100,
                         "src/store_import.py:221 inserts every row of the document, so the "
                         "table keeps every event and is not the bounded side")
        counts = OperationsSet().actual(_Recorder(events=bound + 100))
        self.assertEqual(counts["ops_events"], bound,
                         f"a table of {bound + 100} rows reports the bound ({owner_site()})")
        expected = OperationsSet().expected(document)
        self.assertEqual(expected["ops_events"], bound + 100,
                         "the document side counts every row it was given, with no cap")
        self.assertNotEqual(expected["ops_events"], counts["ops_events"],
                            "so a document with more rows than the bound cannot be verified "
                            "against the table: src/store_import.py:656 refuses it.  Recorded, "
                            "not changed.")


class WhyNotTheEventsDocumentTest(unittest.TestCase):
    """The bound cannot live in src/events_document.py, and this measures why."""

    def test_the_operations_log_is_not_an_events_document(self):
        from src import events_document
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / events_document.SERVED
            row = {"id": "e1", "createdAt": "2026-01-01T00:00:00+00:00",
                   "revision": 1, "action": "note_add", "context": {}}
            with self.assertRaises(ValueError) as caught:
                events_document.write(path, [row], producer=events_document.SCAN_EVENTS)
            self.assertIn("no t", str(caught.exception),
                          "an operations event has no `t`: the events document refuses it")
            self.assertFalse(path.exists(), "a refused write writes nothing")
        self.assertEqual(events_document.VERSION, 1,
                         "that module owns the version of another document; this change "
                         "does not touch it")


if __name__ == "__main__":
    unittest.main()
