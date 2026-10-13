"""The speed field of an event has one owner, and the route reads that owner.

The events-document field of the average speed of a shot had three live sites and
no case that named it:

  * the two rebuilders wrote the name as a plain literal
    (``src/rebuild_events_v2.py`` and ``src/rebuild_events_calibrated.py``),
  * the live route of ``annotator/unified_server.py`` read a second copy of that
    name as a plain literal for its fallback,
  * and no case in ``tests/`` named the field at all.

The drift was silent.  A rename in one rebuilder left the rebuilt document with
no name the route reads.  ``item.setdefault('speed_mm_s', ...)`` never ran for
those events, the console showed no speed, and the suite stayed green.

This module holds the three sides to one owner,
``src.events_document.EVENT_SPEED_FIELD``:

  * every write of a speed field in the two rebuilders, read as text,
  * every fallback name the route reads, read from the syntax tree of the route,
  * and one projection in a run: a document whose only speed name is the owner
    value must come back from the route with ``speed_mm_s``.

The value the guard measures, at the time of writing: ``avg_speed_m_s``.  The
same suite holds ``tests/test_unified_server.py`` on the older field
``speed_m_s`` of ``src/scan_events.py``, which is a different name and stays.

Not in this guard: ``src/eval_events.py`` also writes a ``speed_m_s`` field, and
that writer is outside this change.  This module reports every site it reads, so
a later change can move it to the owner.

Run: ``./scripts/pool-test.sh python test_event_speed_field_owner``
"""
from __future__ import annotations

import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from annotator.unified_server import Backend  # noqa: E402
from src import events_document  # noqa: E402

#: The owner module, as a path from the repository root.
OWNER = "src/events_document.py"
#: The owner name, read from the imported module and from no copy of the text.
OWNER_NAME = "EVENT_SPEED_FIELD"
#: The two modules that write the field of a rebuilt document.
WRITERS = ("src/rebuild_events_v2.py", "src/rebuild_events_calibrated.py")
#: The live route that projects each event for the console.
ROUTE = "annotator/unified_server.py"
#: The speed name of the older scan writer, ``src/scan_events.py``.  The route
#: reads it first, and it is a different field.
LEGACY_SPEED = "speed_m_s"
#: The field the route adds to a projected item.
PROJECTED_SPEED = "speed_mm_s"
#: Every name that ends a speed field.  A detector that reads one shape only
#: misses the other writer, so the walk states both.
SPEED_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*_m_s$")
#: Every spelling of the owner name that this module accepts as a write of the
#: owner field: the constant alone, and the constant under its module.
OWNER_SPELLINGS = ("EVENT_SPEED_FIELD", "events_document.EVENT_SPEED_FIELD")


def owner_value() -> str:
    """The value of the owner constant, read from the imported module.

    The dotted read is deliberate.  ``getattr`` on the module answers the value of
    the module that is loaded now, so a guard that plants a new value in
    ``events_document.EVENT_SPEED_FIELD`` is answered by that value.
    """
    value = getattr(events_document, OWNER_NAME, None)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{OWNER}:{OWNER_NAME} is not a non-empty string: {value!r}")
    return value


def source_text(relative: str) -> str:
    """The text of one source file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one source file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(relative: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return f"{relative}:{line}: {text.strip()}  <- {why}"


def literal_speed_sites(text: str, where: str) -> list:
    """Every speed-field name a module writes as a plain string literal.

    A write is a dictionary key of a ``dict`` display, a subscript of a ``dict``,
    or a keyword of a call.  A ``get`` call is a read and not a write, so the
    fallback of the route does not appear here.  The answer is
    ``(line, the literal as written, the value)`` per site.
    """
    found = []
    tree = ast.parse(text, filename=where)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            pairs = [(key, value) for key, value in zip(node.keys, node.values)
                     if key is not None]
        elif isinstance(node, ast.Call):
            pairs = [(word, word.value) for word in node.keywords if word.arg]
        else:
            pairs = []
        for key, value in pairs:
            if isinstance(key, ast.Constant) and isinstance(key.value, str) \
                    and SPEED_FIELD_RE.match(key.value):
                found.append((key.lineno, ast.unparse(key), key.value))
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str) \
                and SPEED_FIELD_RE.match(node.slice.value):
            found.append((node.lineno, ast.unparse(node.slice), node.slice.value))
    return sorted(found)


def speed_reads(text: str, where: str) -> list:
    """Every speed-field name the route reads for a fallback.

    The shape is ``<expression>.get(<name>)`` or ``<expression>.get(<name>,
    <default>)``: the first argument is the name.  The answer is
    ``(line, the first argument as written, the value or None when the argument
    is not a literal)``.

    The walk states both shapes on purpose.  A walk that reads the two-argument
    form only misses the owner read inside the default of the outer call, and
    that read is the one this guard exists to hold.
    """
    found = []
    tree = ast.parse(text, filename=where)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "get":
            continue
        name = node.args[0]
        if isinstance(name, ast.Constant) and isinstance(name.value, str) \
                and SPEED_FIELD_RE.match(name.value):
            found.append((node.lineno, ast.unparse(name), name.value))
            continue
        if isinstance(name, (ast.Name, ast.Attribute, ast.Subscript)):
            written = ast.unparse(name)
            if written in OWNER_SPELLINGS or written.endswith("." + OWNER_NAME):
                found.append((node.lineno, written, None))
    return sorted(found)


class OwnerTests(unittest.TestCase):
    """The owner name, the value the guard measures and the type of that value."""

    def test_the_owner_names_the_shipped_field(self):
        self.assertEqual(owner_value(), "avg_speed_m_s",
                         f"{OWNER}:{OWNER_NAME} moved; the two rebuilders and the "
                         f"route must move with it")

    def test_the_owner_line_of_the_module_carries_the_shipped_field(self):
        """The line of the owner module that holds the value, with its number.

        This case pins the owner at ``path:line``.  The value the module answers
        and the value that the text of the module shows must be one word, so a
        reader of the report can open that line and see the shipped name.
        """
        owner = owner_value()
        lines = source_lines(OWNER)
        sites = [(number, text) for number, text in enumerate(lines, start=1)
                 if re.match(rf"\s*{OWNER_NAME}\s*=", text)]
        self.assertEqual(1, len(sites),
                         f"{OWNER} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
        number, text = sites[0]
        self.assertEqual(owner, "avg_speed_m_s",
                         report(OWNER, number, text,
                                "the shipped field moved; the rebuilt documents and "
                                "the route must stay on the same word"))
        self.assertIn(f'{OWNER_NAME} = "{owner}"', text,
                      report(OWNER, number, text,
                             f"the line does not assign {owner!r} to {OWNER_NAME}"))

    def test_the_owner_field_is_a_metres_per_second_name(self):
        self.assertTrue(SPEED_FIELD_RE.match(owner_value()),
                        f"{OWNER}:{OWNER_NAME} = {owner_value()!r} is not a speed field name")


class WriterTests(unittest.TestCase):
    """Every write of a speed field in the two rebuilders names the owner."""

    def test_every_writer_field_write_agrees_with_the_owner(self):
        owner = owner_value()
        offenders = []
        for relative in WRITERS:
            for line, written, value in literal_speed_sites(source_text(relative), relative):
                if value != owner:
                    offenders.append(report(
                        relative, line, source_lines(relative)[line - 1],
                        f"{written} is not the owner value {owner!r} of {OWNER}"))
        self.assertEqual([], offenders,
                         "a rebuilder writes a speed field outside its owner:\n"
                         + "\n".join(offenders))

    def test_every_rebuilder_defines_the_owner_name_nowhere_of_its_own(self):
        """A rebuilder that defines the name answers its own copy, not the owner."""
        offenders = []
        for relative in WRITERS:
            tree = ast.parse(source_text(relative), filename=relative)
            for node in ast.walk(tree):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == OWNER_NAME:
                        offenders.append(report(
                            relative, node.lineno, source_lines(relative)[node.lineno - 1],
                            f"the second definition of {OWNER_NAME}; the owner is {OWNER}"))
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_no_writer_spells_the_field_name_as_a_literal(self):
        """A string that holds the owner value is a second home of the fact.

        The agreement case above holds the field to the owner *value*.  A plain
        literal earns that test whenever its value equals that value today, and
        the same literal is a second home tomorrow: the owner moves, this string
        stays, and no case reads both.  So this case holds the field name to the
        owner *name*.  The accepted spellings stay ``OWNER_SPELLINGS``: the
        constant alone, and the constant under its module.
        """
        offenders = []
        for relative in WRITERS:
            for line, written, value in literal_speed_sites(source_text(relative), relative):
                if written in OWNER_SPELLINGS or value == OWNER_NAME:
                    continue
                offenders.append(report(
                    relative, line, source_lines(relative)[line - 1],
                    f"{written} is a plain literal; write the owner name "
                    f"{'/'.join(OWNER_SPELLINGS)} of {OWNER} instead"))
        self.assertEqual([], offenders,
                         "a rebuilder spells the speed field name as a literal "
                         "outside its owner:\n" + "\n".join(offenders))

    def test_the_two_rebuilders_write_through_the_owner_name(self):
        """The anti-vacuity case: the scan must find the real field at the real sites.

        A scan that reads nothing passes every agreement case above.  This case
        holds the two rebuilders to one write of the owner name each, and it holds
        the value of that write to the owner value.
        """
        owner = owner_value()
        accepted = list(OWNER_SPELLINGS) if owner in OWNER_SPELLINGS \
            else list(OWNER_SPELLINGS) + [owner]
        for relative in WRITERS:
            lines = source_lines(relative)
            sites = [(number, text) for number, text in enumerate(lines, start=1)
                     if any(spelling + ":" in text for spelling in OWNER_SPELLINGS)]
            self.assertTrue(sites, f"{relative} writes no speed field through "
                                   f"{'/'.join(OWNER_SPELLINGS)}")
            for number, text in sites:
                self.assertTrue(any(spelling in text for spelling in accepted),
                                report(relative, number, text,
                                       "the write does not reach the owner name "
                                       f"{'/'.join(accepted)}"))

    def test_the_scan_reports_a_planted_second_writer_name(self):
        """A writer line with another field name is reported with its file and line.

        The planted line names the owner value in its comment, so the detector
        holds the field name and not the word of the owner.
        """
        owner = owner_value()
        planted = ("shots.append({\n"
                   "    't': 1.0, 'type': 'shot',\n"
                   f"    'disp_mm': 300, 'mean_speed_m_s': 0.15,  # not {owner}\n"
                   "})\n")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rebuild_events_v2.py"
            path.write_text(planted, encoding="utf-8")
            offenders = [report("src/rebuild_events_v2.py", line, planted.splitlines()[line - 1],
                                f"{written} is not the owner value {owner!r} of {OWNER}")
                         for line, written, value in literal_speed_sites(planted, str(path))
                         if value != owner]
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn("src/rebuild_events_v2.py:3:", offenders[0])
        self.assertIn("mean_speed_m_s", offenders[0])
        self.assertIn(owner, offenders[0])
        self.assertIn("avg_speed_m_s", offenders[0])


class RouteTests(unittest.TestCase):
    """The route reads the owner name for its fallback."""

    def test_the_route_fallback_agrees_with_the_owner(self):
        owner = owner_value()
        offenders = []
        for line, written, value in speed_reads(source_text(ROUTE), ROUTE):
            if value is not None and value != owner and written != f"'{LEGACY_SPEED}'":
                offenders.append(report(
                    ROUTE, line, source_lines(ROUTE)[line - 1],
                    f"{written} is not the owner value {owner!r} of {OWNER}"))
        self.assertEqual([], offenders,
                         "the route reads a fallback name that no owner states:\n"
                         + "\n".join(offenders))

    def test_the_route_reads_the_owner_for_the_rebuilt_document(self):
        """The anti-vacuity case of the route: one read names the owner constant."""
        reads = speed_reads(source_text(ROUTE), ROUTE)
        owner_reads = [(line, written) for line, written, value in reads if value is None]
        self.assertTrue(owner_reads,
                        f"{ROUTE} reads no fallback through {OWNER_NAME}; the "
                        f"rebuilt document would carry no speed")
        for line, written in owner_reads:
            self.assertIn(OWNER_NAME, written)
            self.assertIn(OWNER_NAME, source_lines(ROUTE)[line - 1])

    def test_the_scan_reports_a_planted_route_fallback_name(self):
        """A route line with another fallback name is reported with its file and line."""
        owner = owner_value()
        planted = ("def project(event):\n"
                   "    speed = event.get('speed_m_s', event.get('mean_speed_m_s'))\n")
        offenders = [report(ROUTE, line, planted.splitlines()[line - 1],
                            f"{written} is not the owner value {owner!r} of {OWNER}")
                     for line, written, value in speed_reads(planted, ROUTE)
                     if value is not None and value != owner and written != f"'{LEGACY_SPEED}'"]
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f"{ROUTE}:2:", offenders[0])
        self.assertIn("mean_speed_m_s", offenders[0])
        self.assertIn(owner, offenders[0])
        self.assertIn("avg_speed_m_s", offenders[0])

    def test_the_route_projects_the_owner_field_into_speed_mm_s(self):
        """The run: a document whose only speed name is the owner value.

        The fixture carries no ``speed_m_s`` field, so the projection below can
        carry a speed only when the route reads the owner field of the document.
        """
        owner = owner_value()
        row = {"id": 11, "t": 5.6, "type": "shot", "disp_mm": 300,
               owner: 0.15,
               "ball_from": [100.0, 200.0], "ball_to": [300.0, 400.0]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backend = Backend(root)
            scan = root / "out" / "scan30"
            scan.mkdir(parents=True)
            events_document.write(scan / events_document.SERVED, [row],
                                  producer=events_document.REBUILD_V2)
            restored = events_document.read(scan / events_document.SERVED)
            self.assertEqual(1, len(restored.rows))
            self.assertEqual(0.15, restored.rows[0].get(owner),
                             "the document does not carry the owner field")
            items, _report = backend._event_geometry("vod30", restored.rows)
        self.assertEqual(1, len(items))
        self.assertEqual(150, items[0].get(PROJECTED_SPEED),
                         f"the route did not read the owner field {owner!r}")


if __name__ == "__main__":
    unittest.main()
