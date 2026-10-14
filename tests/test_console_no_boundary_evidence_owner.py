"""The console sentence of no_boundary_evidence reads the python home.

The machine code ``no_boundary_evidence`` stood in five places, and no case read
any two of them:

  * ``src/event_gates.py`` counted it through ``CALIBRATION_NO_EVIDENCE_REASON``,
    the constant ``calibration_warning`` reads at ``src/event_gates.py:530``;
  * ``src/table_refine.py`` spelled it three times: in the refusal dict of
    ``refine_quad``, in the per-side code of ``_refine_once`` and in the fallback
    of the reason ternary;
  * ``annotator/app.js`` holds the row of ``QUAD_REFUSAL_COPY`` that an operator
    reads when the refiner refuses a quad - the walk of round 105 read that row
    at ``annotator/app.js:1138``.

Round 105 gave the python side one home: the string stands once under ``src/``,
on ``REASON_NO_BOUNDARY_EVIDENCE`` in ``src/table_refine.py``, and the gate reads
that name.  The console copy stays, because it is the operator-visible sentence,
not a machine code, so this module holds the pair equal and reddens when either
side drifts.

The reader locates every site by its symbol, not by a line number: another worker
edits ``annotator/app.js``.  A failure names the site to open as
``path:line: <line text>``.

Run: ``./scripts/pool-test.sh python test_console_no_boundary_evidence_owner``
"""
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

#: The one home of the code under ``src/``.
HOME_SITE = 'src/table_refine.py'
HOME_NAME = 'REASON_NO_BOUNDARY_EVIDENCE'

#: The gate that counts the code through its own name.
GATE_SITE = 'src/event_gates.py'
GATE_NAME = 'CALIBRATION_NO_EVIDENCE_REASON'

#: The console file, the head of its reason map, and the machine code itself.
CONSOLE_SITE = 'annotator/app.js'
CONSOLE_HEAD = 'const QUAD_REFUSAL_COPY = {'
TOKEN = 'no_boundary_evidence'

#: The two sentences an operator reads for the code.  They are the console copy
#: this row holds in place: the sentence of ``annotator/app.js:1138`` must not
#: change under the repair that moved the machine code.
OPERATOR_COPY = ('no rail edge is visible inside the search band',
                 '搜索带内看不到库边边缘')

#: The measured size of every scan, read in the shipped tree on 2026-10-13.  A
#: second spelling, a renamed key or a shortened walk changes one of these
#: numbers, and the last case of this module reddens in the same run.
HOME_LITERAL_SITE_COUNT = 1
GATE_ALIAS_COUNT = 1
CONSOLE_ROW_COUNT = 10
CONSOLE_ROW_STRING_COUNT = 2

#: One row of the console map with a bare key, and one with a computed key.
ROW_BARE = re.compile(r"^\s*([A-Za-z_][\w]*)\s*:\s*\[(.*)$")
ROW_COMPUTED = re.compile(r"^\s*\[([A-Za-z_][\w]*)\]\s*:\s*\[(.*)$")

#: One single-quoted sentence of a row.
STRING = re.compile(r"'([^']*)'")


def lines_of(path):
    """`(number, line)` for every line of one file, read as UTF-8."""
    return list(enumerate(path.read_text(encoding='utf-8').splitlines(), start=1))


def display(path):
    """One path as a repository-relative name, or as itself when it is outside."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def site(path, number):
    """One site of one file, as ``path:line``."""
    return f'{display(path)}:{number}'


def report(path, number, why):
    """One offender, as ``path:line: <line text>``, with the reason below it."""
    text = lines_of(path)[number - 1][1]
    return f'{site(path, number)}: {text.strip()}\n  {why}'


def python_files():
    """Every ``src/*.py`` file of this checkout, sorted by path."""
    return sorted((ROOT / 'src').glob('*.py'))


def python_literal_sites(path):
    """`(number, line)` for every line of one python file that quotes the code."""
    quoted = (f"'{TOKEN}'", f'"{TOKEN}"')
    return [(number, line) for number, line in lines_of(path)
            if any(spelling in line for spelling in quoted)]


def definition_line(path, name):
    """`(number, line)` of the statement that binds ``name``, or None."""
    hits = [(number, line) for number, line in lines_of(path)
            if line.strip().startswith(f'{name} =')]
    return hits[0] if len(hits) == 1 else None


def head_line(path, head):
    """`(number, line)` of the one line that holds the head of the map, or None."""
    hits = [(number, line) for number, line in lines_of(path)
            if line.strip().startswith(head)]
    return hits[0] if len(hits) == 1 else None


def console_rows(path, head):
    """`(key, number, line, strings)` for every row of the console map.

    A row starts at the line that holds ``key: [`` and keeps the lines until the
    array closes, so a row whose two sentences wrap answers whole.  A computed
    key (``[QUAD_INVALID_GEOMETRY]: [...]``) answers the name of the symbol.
    """
    lines = lines_of(path)
    start = head_line(path, head)
    if start is None:
        return []
    rows = []
    index = start[0]
    while index < len(lines):
        number, line = lines[index]
        if line.strip() == '};':
            break
        match = ROW_COMPUTED.match(line) or ROW_BARE.match(line)
        if match is None:
            index += 1
            continue
        key, rest = match.group(1), match.group(2)
        depth = 1 + rest.count('[') - rest.count(']')
        text = rest
        while depth > 0 and index + 1 < len(lines):
            index += 1
            more = lines[index][1]
            text += ' ' + more
            depth += more.count('[') - more.count(']')
        rows.append((key, number, line, STRING.findall(text)))
        index += 1
    return rows


def console_drift(path, home_value):
    """An offender report for the console row of ``home_value``, or None.

    The row must carry the key the python home answers, and it must answer the
    two sentences an operator reads.  The report names the site to open, so a
    failure points at the copy that drifted.
    """
    head = head_line(path, CONSOLE_HEAD)
    if head is None:
        return f'{display(path)}: no line holds "{CONSOLE_HEAD}", so this reader finds no map'
    rows = console_rows(path, CONSOLE_HEAD)
    matching = [row for row in rows if row[0] == home_value]
    if len(matching) != 1:
        why = (f'the map holds {len(matching)} rows keyed "{home_value}", so the code the '
               f'python home answers reaches no sentence.')
        # A renamed key is the drift this reader exists for: name the row that
        # answers a near spelling, so the failure points at the line to open.
        near = [row for row in rows if row[0] != home_value
                and (row[0].startswith(home_value) or home_value.startswith(row[0]))]
        if near:
            why += '\n' + '\n'.join(
                '    ' + report(path, number, f'the row here is keyed "{key}", and the python '
                                             f'home answers "{home_value}"')
                for key, number, _, _ in near)
        else:
            why += '  Its keys are: ' + ', '.join(sorted(repr(row[0]) for row in rows))
        return report(path, head[0], why)
    key, number, line, strings = matching[0]
    if tuple(strings) != OPERATOR_COPY:
        return report(path, number,
                      f'the console row "{key}" answers {tuple(strings)!r}, not the recorded '
                      f'operator sentence {OPERATOR_COPY!r}')
    return None


class ConsoleNoBoundaryEvidenceOwnerTest(unittest.TestCase):
    def test_the_code_stands_once_under_src(self):
        """One file under ``src/`` quotes the code, and it quotes it once.

        The reader holds no list of the files it expects to pass.  It walks
        ``src/*.py`` and counts the quoted sites, so a second spelling reddens
        here with the site to open.
        """
        holders = {path: sites for path, sites in
                   ((path, python_literal_sites(path)) for path in python_files()) if sites}
        offenders = [report(path, number,
                            f'the code "{TOKEN}" has one home in {HOME_SITE}, and '
                            f'{site(path, number)} spells it a second time')
                     for path, sites in holders.items() if display(path) != HOME_SITE
                     for number, _ in sites]
        self.assertEqual(
            [], offenders,
            'a second file under src/ quotes the machine code, so one edit of the home '
            'would leave one reader behind:\n' + '\n'.join(offenders))
        sites = holders.get(ROOT / HOME_SITE, [])
        self.assertEqual(
            HOME_LITERAL_SITE_COUNT, len(sites),
            f'{HOME_SITE} quotes "{TOKEN}" {len(sites)} times, not {HOME_LITERAL_SITE_COUNT}:\n'
            + '\n'.join(f'{site(ROOT / HOME_SITE, number)}: {line.strip()}'
                        for number, line in sites))
        home = definition_line(ROOT / HOME_SITE, HOME_NAME)
        self.assertIsNotNone(
            home, f'{HOME_SITE} binds {HOME_NAME} on no single line, so this reader '
                  f'cannot name the home of "{TOKEN}"')
        number, line = home
        self.assertIn(
            TOKEN, line,
            report(ROOT / HOME_SITE, number,
                   f'{HOME_NAME} answers a value that is not "{TOKEN}"'))

    def test_the_gate_reads_the_home_and_quotes_no_second_string(self):
        """``CALIBRATION_NO_EVIDENCE_REASON`` is the home's value, not a copy.

        The gate counted its own literal until round 105.  The constant must
        answer the home object itself: two equal strings agree today, and one of
        them drifts tomorrow.
        """
        from src import event_gates, table_refine
        self.assertIs(
            table_refine.REASON_NO_BOUNDARY_EVIDENCE, event_gates.CALIBRATION_NO_EVIDENCE_REASON,
            f'{GATE_SITE} answers its own string for the code, so the code the gate counts and '
            f'the code the producer reports can part')
        self.assertEqual(TOKEN, event_gates.CALIBRATION_NO_EVIDENCE_REASON,
                         f'{GATE_NAME} answers {event_gates.CALIBRATION_NO_EVIDENCE_REASON!r}, '
                         f'not "{TOKEN}"')
        offenders = [report(ROOT / GATE_SITE, number,
                            f'the code has one home in {HOME_SITE}; {GATE_SITE} quotes it')
                     for number, _ in python_literal_sites(ROOT / GATE_SITE)]
        self.assertEqual(
            [], offenders,
            'the gate quotes the machine code a second time:\n' + '\n'.join(offenders))

    def test_the_console_key_equals_the_python_home(self):
        """The console row the operator reads is keyed by the python home's value.

        The walk of round 105 read the row at ``annotator/app.js:1138``: the key
        is the machine code the refiner puts in a verdict, and the two sentences
        are the operator-visible copy of this row.  A renamed key leaves the
        reader on the ``default`` sentence, so this case holds the key to the
        python home and holds the copy still.
        """
        from src import table_refine
        console = ROOT / CONSOLE_SITE
        drift = console_drift(console, table_refine.REASON_NO_BOUNDARY_EVIDENCE)
        self.assertIsNone(drift, drift or '')
        rows = console_rows(console, CONSOLE_HEAD)
        self.assertEqual(
            CONSOLE_ROW_COUNT, len(rows),
            f'the map of {CONSOLE_SITE} no longer holds {CONSOLE_ROW_COUNT} rows, so this '
            'reader holds less of the pair than the code needs')
        matching = [row for row in rows if row[0] == table_refine.REASON_NO_BOUNDARY_EVIDENCE]
        key, number, line, strings = matching[0]
        self.assertEqual(table_refine.REASON_NO_BOUNDARY_EVIDENCE, key)
        self.assertEqual(list(OPERATOR_COPY), strings,
                         report(console, number,
                                f'the console row "{key}" no longer answers the recorded '
                                f'operator sentence {OPERATOR_COPY!r}'))
        self.assertIn(CONSOLE_SITE, site(console, number))

    def test_a_planted_console_drift_is_reported_with_its_file_and_line(self):
        """The reporter of this module names the file, the line and the text.

        This case writes two small console files to temporary files, each holding
        only the map.  One renames the key of the row, and one edits the sentence
        an operator reads.  The reporter must name the drifted site as
        ``path:line: <line text>``.
        """
        planted = ('const QUAD_REFUSAL_COPY = {\n'
                   f"  {TOKEN}: ['{OPERATOR_COPY[0]}',\n"
                   f"                 '{OPERATOR_COPY[1]}'],\n"
                   "  low_cloth_area: ['the cloth is hidden', '台面被遮挡'],\n"
                   '};\n')
        holder = tempfile.TemporaryDirectory(prefix='console-no-boundary-evidence-owner-')
        self.addCleanup(holder.cleanup)

        renamed = Path(holder.name) / 'app-renamed.js'
        renamed.write_text(planted.replace(f'  {TOKEN}: [', f'  {TOKEN}_v2: ['), encoding='utf-8')
        drift = console_drift(renamed, TOKEN)
        self.assertIsNotNone(drift, 'the reporter passed a map whose key no longer carries the code')
        self.assertIn(f'{renamed}:1:', drift)
        self.assertIn(f'{renamed}:2:', drift)
        self.assertIn(f'rows keyed "{TOKEN}"', drift)
        self.assertIn(f'{TOKEN}_v2', drift)

        reworded = Path(holder.name) / 'app-reworded.js'
        reworded.write_text(planted.replace(OPERATOR_COPY[0], 'no rail edge in the band'),
                            encoding='utf-8')
        drift = console_drift(reworded, TOKEN)
        self.assertIsNotNone(drift, 'the reporter passed a map whose sentence changed')
        self.assertIn(f'{reworded}:2:', drift)
        self.assertIn('not the recorded operator sentence', drift)

    def test_the_scan_of_each_place_keeps_its_measured_size(self):
        """The scans keep the size this module measured, so none passes empty.

        A reader that finds no site answers an empty list, and an empty list
        passes the cases above.  The numbers are the counts of the shipped tree
        on 2026-10-13.
        """
        console = ROOT / CONSOLE_SITE
        measured = {
            'quoted sites of the home': (
                len(python_literal_sites(ROOT / HOME_SITE)), HOME_LITERAL_SITE_COUNT),
            'alias of the gate': (
                1 if definition_line(ROOT / GATE_SITE, GATE_NAME) else 0, GATE_ALIAS_COUNT),
            'rows of the console map': (len(console_rows(console, CONSOLE_HEAD)), CONSOLE_ROW_COUNT),
            'sentences per console row': (
                CONSOLE_ROW_STRING_COUNT,
                sorted({len(strings) for _, _, _, strings in console_rows(console, CONSOLE_HEAD)})[0]),
        }
        for scan, (found, wanted) in measured.items():
            with self.subTest(scan=scan):
                self.assertEqual(
                    wanted, found,
                    f'the scan "{scan}" found {found} sites, not {wanted}.  The number is the '
                    'count this module measured in the shipped tree.  A second spelling, a '
                    'renamed key or a shortened walk changes it, and every other case of this '
                    'module then reads less than the pair it holds.')


if __name__ == '__main__':
    unittest.main()
