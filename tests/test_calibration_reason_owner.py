"""The calibration reason ``no_boundary_evidence`` has one home in python.

Round 105 counted nine live copies of this wire token, and no case read two of
them together:

  * ``src/event_gates.py:495`` held the constant
    ``CALIBRATION_NO_EVIDENCE_REASON = "no_boundary_evidence"``, read at
    ``src/event_gates.py:532``;
  * ``src/table_refine.py`` spelled the token in four places: the refusal dict of
    the last try, the value of the unverified sides, the fallback of the reason
    ternary and the reason of the refusal result - the last one was not in the
    walk of round 105;
  * ``annotator/app.js:1145`` holds the row of ``QUAD_REFUSAL_COPY`` that an
    operator reads, keyed by the token.

The repair gave the string one home: the name ``REASON_NO_BOUNDARY_EVIDENCE`` in
``src/table_refine.py``, bound to the token once.  The four producer sites read
that name, and ``src/event_gates.py`` reads it too, so the gate counts the token
the producer writes.  The console copy stays, because JavaScript cannot import
python.

This module holds the producer side of the row: the home and its type, the four
sites, the gate reader and the console row the reply reaches.  Its neighbour
``tests/test_console_no_boundary_evidence_owner.py`` holds the console pair and
the planted console drift from the other side.  A case that held the same fact
twice would be a second copy, so the two modules split the row.

A case reads a site by its symbol, never by a line number: another worker edits
these files.  A failure names the site to open as ``path:line: <line text>``.

Run: ``./scripts/pool-test.sh python test_calibration_reason_owner``
"""
from pathlib import Path
import ast
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

#: The one home of the token, and the name that carries it.
HOME_SITE = 'src/table_refine.py'
HOME_NAME = 'REASON_NO_BOUNDARY_EVIDENCE'

#: The gate that counts the token through the home, and its own name.
GATE_SITE = 'src/event_gates.py'
GATE_NAME = 'CALIBRATION_NO_EVIDENCE_REASON'

#: The console file, the head of its reason map and the token itself.
CONSOLE_SITE = 'annotator/app.js'
CONSOLE_HEAD = 'const QUAD_REFUSAL_COPY = {'
TOKEN = 'no_boundary_evidence'

#: The two sentences an operator reads for the token.  They are the console copy
#: of this row: the repair moved the machine code, not the operator sentence.
OPERATOR_COPY = ('no rail edge is visible inside the search band',
                 '搜索带内看不到库边边缘')

#: Measured counts of the shipped tree on 2026-10-13.  A second spelling, a
#: renamed key or a shortened walk changes one of these numbers, and the case
#: that reads that scan reddens.
HOME_LITERAL_SITE_COUNT = 1
HOME_READ_SITE_COUNT = 4
GATE_READ_SITE_COUNT = 1
CONSOLE_KEY_ROW_COUNT = 1
CONSOLE_ROW_STRING_COUNT = 2

#: One row of the console map: a bare key, or a computed one.
ROW_BARE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:\s*\[")
ROW_COMPUTED = re.compile(r"^\s*\[([A-Za-z_]\w*)\]\s*:\s*\[")

#: One single-quoted sentence of a row.
STRING = re.compile(r"'([^']*)'")


def lines_of(path):
    """`(number, line)` for every line of one file, read as UTF-8."""
    return list(enumerate(path.read_text(encoding='utf-8').splitlines(), start=1))


def display(path):
    """One path as a repository-relative name, or as itself when it is outside."""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def site(path, number):
    """One site of one file, as ``path:line``."""
    return f'{display(path)}:{number}'


def report(path, number, line, why):
    """One offender, as ``path:line: <line text>``, with the reason below it."""
    return f'{site(path, number)}: {line.strip()}\n  {why}'


def literal_sites(text):
    """`(number, line)` for every line of one source text that quotes the token."""
    quoted = (f"'{TOKEN}'", f'"{TOKEN}"')
    return [(number, line) for number, line in enumerate(text.splitlines(), start=1)
            if any(spelling in line for spelling in quoted)]


def stray_literal_offenders(path, text, home_number):
    """One report per line of ``text`` that quotes the token away from the home."""
    return [report(path, number, line,
                   f'the token "{TOKEN}" has one home on {site(path, home_number)}, and this '
                   f'line quotes it a second time')
            for number, line in literal_sites(text) if number != home_number]


def name_loads(text, name):
    """`(number, line)` for every line that reads ``name``."""
    tree = ast.parse(text)
    numbers = sorted({node.lineno for node in ast.walk(tree)
                      if isinstance(node, ast.Name) and node.id == name
                      and isinstance(node.ctx, ast.Load)})
    lines = text.splitlines()
    return [(number, lines[number - 1]) for number in numbers]


def name_definitions(text, name):
    """`(number, line)` for every module-level line that binds ``name``."""
    tree = ast.parse(text)
    lines = text.splitlines()
    numbers = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            numbers.add(node.lineno)
    return [(number, lines[number - 1]) for number in sorted(numbers)]


def site_nodes(text, wanted):
    """Every syntax node that answers ``wanted``, in source order.

    ``wanted`` is one of the four shapes a site of this row has: ``'dict'``, the
    refusal dict whose ``reason`` value is the home name; ``'assign'``, the value
    of the per-side assignment; ``'ternary'``, the fallback of the reason
    ternary; ``'fallback'``, the right side of the ``or`` of the refusal result.
    """
    tree = ast.parse(text)
    found = []
    for node in ast.walk(tree):
        if wanted == 'dict' and isinstance(node, ast.Dict):
            if any(getattr(key, 'value', None) == 'reason'
                   and isinstance(value, ast.Name) and value.id == HOME_NAME
                   for key, value in zip(node.keys, node.values)):
                found.append(node)
        elif wanted == 'assign' and isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Name) and node.value.id == HOME_NAME:
                found.append(node)
        elif wanted == 'ternary' and isinstance(node, ast.IfExp):
            if isinstance(node.orelse, ast.Name) and node.orelse.id == HOME_NAME:
                found.append(node)
        elif wanted == 'fallback' and isinstance(node, ast.BoolOp):
            if isinstance(node.values[-1], ast.Name) and node.values[-1].id == HOME_NAME:
                found.append(node)
    return sorted(found, key=lambda node: node.lineno)


class NoReason:
    """A calibration result that answers no reason, for the refusal fallback."""

    def get(self, key, default=None):
        """Answer the default, the way a result without a reason does."""
        return default


def console_row(path, token):
    """`(number, line, sentences)` for the console row keyed ``token``, or None.

    The row starts at its key line and keeps the lines until its array closes, so
    a row whose sentences wrap answers whole.
    """
    lines = lines_of(path)
    heads = [number for number, line in lines if line.strip().startswith(CONSOLE_HEAD)]
    if len(heads) != 1:
        return None
    index = heads[0]
    while index < len(lines):
        number, line = lines[index]
        if line.strip() == '};':
            break
        match = ROW_COMPUTED.match(line) or ROW_BARE.match(line)
        if match and match.group(1) == token:
            depth = line.count('[') - line.count(']')
            text = line
            while depth > 0 and index + 1 < len(lines):
                index += 1
                more = lines[index][1]
                text += ' ' + more
                depth += more.count('[') - more.count(']')
            return number, line, STRING.findall(text)
        index += 1
    return None


def console_drift(path, token):
    """An offender report for the console row of ``token``, or None.

    The row must carry the key the python home answers, and it must answer the
    two sentences an operator reads.  The report names the site to open, so a
    renamed key points at the row that travelled with it.
    """
    lines = lines_of(path)
    heads = [number for number, line in lines if line.strip().startswith(CONSOLE_HEAD)]
    if len(heads) != 1:
        return (f'{display(path)}: {len(heads)} lines hold "{CONSOLE_HEAD}", so this reader '
                f'finds no one reason map')
    head_number = heads[0]
    row = console_row(path, token)
    if row is None:
        why = (f'the map holds no row keyed "{token}", so the machine code the refiner writes '
               f'reaches the default sentence.')
        near = [report(path, number, line,
                       f'the row here is keyed "{match.group(1)}", and the python home answers '
                       f'"{token}"')
                for number, line in lines[head_number - 1:]
                for match in (ROW_COMPUTED.match(line) or ROW_BARE.match(line),)
                if match and (match.group(1).startswith(token) or token.startswith(match.group(1)))]
        if near:
            why += '\n' + '\n'.join(near)
        return report(path, head_number, lines[head_number - 1][1], why)
    number, line, sentences = row
    if tuple(sentences) != OPERATOR_COPY:
        return report(path, number, line,
                      f'the console row "{token}" answers {tuple(sentences)!r}, not the recorded '
                      f'operator sentence {OPERATOR_COPY!r}')
    return None


class CalibrationReasonOwnerTest(unittest.TestCase):
    def test_the_home_binds_one_string_of_one_type(self):
        """The token stands once under ``src/``, on the name the sites read.

        The home is a module-level binding of ``src/table_refine.py``, and its
        right side must be the token itself: the wire contract and the console
        guard of this row both read this one string.
        """
        from src import table_refine
        text = (ROOT / HOME_SITE).read_text(encoding='utf-8')
        definitions = name_definitions(text, HOME_NAME)
        self.assertEqual(
            1, len(definitions),
            f'{HOME_SITE} binds {HOME_NAME} on {len(definitions)} module-level lines, not 1:\n'
            + '\n'.join(report(ROOT / HOME_SITE, number, line, 'the binding stands here')
                        for number, line in definitions))
        home_number, home_line = definitions[0]
        self.assertIn(TOKEN, home_line,
                      report(ROOT / HOME_SITE, home_number, home_line,
                             f'{HOME_NAME} answers a value that is not "{TOKEN}"'))
        self.assertEqual(TOKEN, getattr(table_refine, HOME_NAME),
                         f'{HOME_NAME} answers {getattr(table_refine, HOME_NAME)!r}, not '
                         f'"{TOKEN}"')
        self.assertIsInstance(getattr(table_refine, HOME_NAME), str,
                              f'{HOME_NAME} must stay the string of the wire contract')
        stray = stray_literal_offenders(ROOT / HOME_SITE, text, home_number)
        self.assertEqual([], stray,
                         'the producer quotes the token a second time:\n' + '\n'.join(stray))
        self.assertEqual(
            HOME_LITERAL_SITE_COUNT, len(literal_sites(text)),
            f'{HOME_SITE} quotes "{TOKEN}" {len(literal_sites(text))} times, not '
            f'{HOME_LITERAL_SITE_COUNT}')

    def test_the_four_reason_sites_read_the_home_name(self):
        """Every reason site names the home instead of quoting the token.

        The walk of round 105 read three sites of the producer, and it missed the
        fourth, the reason of the refusal result.  This case reads the file as a
        syntax tree and counts the name reads, so a repaired site and a missed
        site both answer here.
        """
        text = (ROOT / HOME_SITE).read_text(encoding='utf-8')
        reads = name_loads(text, HOME_NAME)
        self.assertEqual(
            HOME_READ_SITE_COUNT, len(reads),
            f'{HOME_SITE} reads {HOME_NAME} on {len(reads)} lines, not '
            f'{HOME_READ_SITE_COUNT}:\n'
            + '\n'.join(report(ROOT / HOME_SITE, number, line, f'this line reads {HOME_NAME}')
                        for number, line in reads))
        for number, line in reads:
            self.assertNotIn(
                f"'{TOKEN}'", line,
                report(ROOT / HOME_SITE, number, line,
                       f'this site quotes the token, and the token has one home on '
                       f'{HOME_NAME}'))

    def test_the_gate_reads_the_home_in_its_own_reader(self):
        """The gate counts the token through the home, and its reader stands.

        ``CALIBRATION_NO_EVIDENCE_REASON`` held its own copy of the string until
        round 105.  Now it answers the home object itself, and the reader that
        compares a calibration value with it is unchanged.
        """
        from src import event_gates, table_refine
        self.assertIs(
            table_refine.REASON_NO_BOUNDARY_EVIDENCE, event_gates.CALIBRATION_NO_EVIDENCE_REASON,
            f'{GATE_SITE} answers its own string for the token, so the code the gate counts '
            f'and the code the producer writes can part')
        self.assertEqual(TOKEN, event_gates.CALIBRATION_NO_EVIDENCE_REASON)
        text = (ROOT / GATE_SITE).read_text(encoding='utf-8')
        stray = [report(ROOT / GATE_SITE, number, line,
                        f'the token has one home in {HOME_SITE}, and {GATE_SITE} quotes it')
                 for number, line in literal_sites(text)]
        self.assertEqual([], stray, 'the gate quotes the token a second time:\n' + '\n'.join(stray))
        reads = name_loads(text, GATE_NAME)
        self.assertEqual(
            GATE_READ_SITE_COUNT, len(reads),
            f'{GATE_SITE} reads {GATE_NAME} on {len(reads)} lines, not {GATE_READ_SITE_COUNT}:\n'
            + '\n'.join(report(ROOT / GATE_SITE, number, line, f'this line reads {GATE_NAME}')
                        for number, line in reads))
        number, line = reads[0]
        self.assertIn('==', line,
                      report(ROOT / GATE_SITE, number, line,
                             f'this line no longer compares a calibration value with {GATE_NAME}'))

    def test_the_four_structures_carry_the_token(self):
        """The sites hand the token to the wire, one structure each.

        This case builds the structures from the source of the producer and reads
        the token back: the refusal dict of the last try, the value of the
        per-side assignment, the fallback of the reason ternary and the reason of
        the refusal result.  A site that drifts to another string answers here,
        before any detector runs.
        """
        from src import table_refine
        text = (ROOT / HOME_SITE).read_text(encoding='utf-8')
        home_value = getattr(table_refine, HOME_NAME)
        namespace = {HOME_NAME: home_value}
        built = {}
        for shape, description in (('dict', 'the refusal dict of the last try'),
                                   ('assign', 'the value of the per-side assignment'),
                                   ('ternary', 'the fallback of the reason ternary'),
                                   ('fallback', 'the reason of the refusal result')):
            nodes = site_nodes(text, shape)
            with self.subTest(shape=shape):
                self.assertEqual(
                    1, len(nodes),
                    f'{HOME_SITE} holds {len(nodes)} nodes for {description}, not 1, so this '
                    f'reader reads less of the row than the row needs:\n'
                    + '\n'.join(report(ROOT / HOME_SITE, node.lineno,
                                       text.splitlines()[node.lineno - 1],
                                       f'this node is a candidate for {description}')
                                for node in nodes))
            built[shape] = nodes[0]
        refusal = eval(compile(ast.Expression(built['dict']), '<refusal>', 'eval'), dict(namespace))
        self.assertEqual(
            {'confidence': 0.0, 'reason': TOKEN}, refusal,
            f'the refusal dict of the last try answers {refusal!r}, and the wire contract '
            f'needs the token "{TOKEN}" in it')
        namespace['info'] = NoReason()
        reason = eval(compile(ast.Expression(built['fallback']), '<refusal-reason>', 'eval'),
                      dict(namespace))
        self.assertEqual(
            TOKEN, reason,
            f'the reason of the refusal result answers {reason!r} when the calibration reports '
            f'no reason, and the wire contract needs the token "{TOKEN}"')
        for shape, node in (('assign', built['assign']), ('ternary', built['ternary'])):
            with self.subTest(shape=shape):
                self.assertEqual(home_value,
                                 getattr(table_refine, HOME_NAME),
                                 f'the {shape} site reads the home name, and the home name '
                                 f'answers {home_value!r}')

    def test_the_console_row_answers_the_wire_token(self):
        """The row an operator reads is keyed by the token of the wire.

        JavaScript cannot import python, so the console keeps its own key.  This
        case reads the map of ``annotator/app.js`` as text and holds its row to
        the value the python home answers, so a renamed key reddens here with the
        line to open.
        """
        from src import table_refine
        console = ROOT / CONSOLE_SITE
        token = table_refine.REASON_NO_BOUNDARY_EVIDENCE
        drift = console_drift(console, token)
        self.assertIsNone(drift, drift or '')
        row = console_row(console, token)
        self.assertIsNotNone(row, f'{CONSOLE_SITE} holds no row keyed "{token}"')
        number, line, sentences = row
        self.assertEqual(
            CONSOLE_ROW_STRING_COUNT, len(sentences),
            report(console, number, line,
                   f'the console row "{token}" answers {len(sentences)} sentences, not '
                   f'{CONSOLE_ROW_STRING_COUNT}'))
        self.assertEqual(list(OPERATOR_COPY), sentences,
                         report(console, number, line,
                                f'the console row "{token}" no longer answers the recorded '
                                f'operator sentence {OPERATOR_COPY!r}'))
        rows = [key for key, _, _ in
                ((key, number, line)
                 for key, number, line in ((m.group(1), number, line) for number, line in lines_of(console)
                                           for m in (ROW_COMPUTED.match(line) or ROW_BARE.match(line),)
                                           if m))]
        self.assertEqual(
            CONSOLE_KEY_ROW_COUNT, rows.count(token),
            f'the map of {CONSOLE_SITE} holds {rows.count(token)} rows keyed "{token}", not '
            f'{CONSOLE_KEY_ROW_COUNT}')

    def test_a_planted_second_spelling_is_reported_with_its_file_and_line(self):
        """The reporter of this module names the file, the line and the text.

        This case writes a small source file to a temporary file.  Its home binds
        the token, and a second line of the same file quotes the token again, the
        drift this row exists for.  The reporter must name that line as
        ``path:line: <line text>``, so a repaired reader points at the copy that
        drifted.
        """
        planted = ('ROOT = 1\n'
                   f'{HOME_NAME} = "{TOKEN}"\n'
                   'def refuse():\n'
                   f'    return {{"confidence": 0.0, "reason": "{TOKEN}"}}\n')
        holder = tempfile.TemporaryDirectory(prefix='calibration-reason-owner-')
        self.addCleanup(holder.cleanup)
        copy = Path(holder.name) / 'table_refine.py'
        copy.write_text(planted, encoding='utf-8')
        offenders = stray_literal_offenders(copy, planted, 2)
        self.assertEqual(1, len(offenders), offenders)
        self.assertIn(f'{copy}:4:', offenders[0])
        self.assertIn(f'"reason": "{TOKEN}"', offenders[0])
        self.assertIn('quotes it a second time', offenders[0])
        moved = stray_literal_offenders(copy, planted, 4)
        self.assertEqual(1, len(moved), moved)
        self.assertIn(f'{copy}:2:', moved[0])


if __name__ == '__main__':
    unittest.main()
