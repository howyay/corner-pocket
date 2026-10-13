"""One home for the paste label that both console screens show.

The round-106 walk found the pair ``VOD link or id`` / ``回放链接或 id`` in two
live console copies: ``annotator/ops.js:44`` (the ``bfPaste`` row of the ops
table) and the two rows of ``annotator/vision-stage.js`` (``:105`` English and
``:213`` Chinese, the ``bcPaste`` row), each painted by its own panel.  Both
files load into the shipped page ``annotator/ops.html``, and that page loads
``annotator/app.js`` first, so a word that both screens show belongs in the
SHARED_WORDS table of ``annotator/app.js``.  That is the decision the committed
round-79 case (``tests/test_console_round79_owners.py``) already holds for its
own word, and this row follows it: one row per slot name, and the two panels
read that row through ``window.ConsoleRules.words``.

The cases below hold the row from four sides:

* case 1 reads the home: the two slot rows carry the pair, the pair stands
  twice, and no other shipped file of the console quotes a member of the pair;
* case 2 reads the two panels: each one asks the home through the quoted slot
  name and holds no row of the pair;
* case 3 plants a row of the pair back into each panel text and reads the
  report: the failure text names the file, the line number and the line text;
* the last case reads ``annotator/ops.html``: the home is published before the
  two panels load.

A slot name is always written with its quotes here.  The bare prefix also
matches ``bfPasteId`` at ``annotator/ops.js:520``, a different name, and a scan
on the prefix would answer for it.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The table that owns every word both console screens show.
OWNER = 'annotator/app.js'
OWNER_HEAD = 'const SHARED_WORDS = Object.freeze({'
#: The page that ships both panels, and the files of the two panels.
PAGE = 'annotator/ops.html'
OPS = 'annotator/ops.js'
STAGE = 'annotator/vision-stage.js'

#: The pair both screens show, and its two quoted spellings.
PAIR = ('VOD link or id', '回放链接或 id')
LITERALS = ("'VOD link or id'", "'回放链接或 id'")
#: The slot name each panel asks for.
OPS_KEY = 'bfPaste'
STAGE_KEY = 'bcPaste'
#: The ask site of each panel: the quoted slot name, never the bare prefix.
OPS_ASK = "say('bfPaste')"
STAGE_ASK = "t('bcPaste')"
#: Measured sizes: the pair stands in two rows of the home, one per slot name,
#: and each panel quotes its slot name once, on the ask site.
OWNER_ROW_COUNT = 2
ASK_COUNT = 1

ROW = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*\[\s*'([^']*)'\s*,\s*'([^']*)'\s*\]")
SCRIPTS = re.compile(r'src="/([A-Za-z0-9_.-]+\.js)')


def display(relative_path, number, line):
    """The citation shape of a report: the path, the line number, the line text."""
    return f'{relative_path}:{number}: {line.strip()}'


def report(offender, why):
    """One finding: the citation of the offender, then the reason."""
    relative_path, number, line = offender
    return f'{display(relative_path, number, line)}\n  {why}'


def read(relative_path):
    """The text of a file of the repository."""
    return (ROOT / relative_path).read_text(encoding='utf-8')


def owner_rows(text):
    """The slot rows of the SHARED_WORDS table: slot name -> (English, Chinese)."""
    start = text.index(OWNER_HEAD)
    block = text[start:text.index('\n});', start)]
    return {match.group(1): (match.group(2), match.group(3)) for match in ROW.finditer(block)}


def owner_span(text):
    """The first and the last line number of the SHARED_WORDS table."""
    start = text.index(OWNER_HEAD)
    return (text[:start].count('\n') + 1,
            text[:text.index('\n});', start)].count('\n') + 1)


def stray_sites(relative_path, text, owner_lines):
    """The lines that quote a member of the pair outside the home table, one entry per line."""
    first, last = owner_lines
    return [(relative_path, number, line)
            for number, line in enumerate(text.splitlines(), 1)
            if any(literal in line for literal in LITERALS)
            and not (relative_path == OWNER and first <= number <= last)]


def console_paths():
    """Every shipped file of the console, as relative paths, in file order."""
    root = ROOT / 'annotator'
    return sorted(path.relative_to(ROOT).as_posix()
                  for path in root.iterdir() if path.suffix in ('.js', '.html'))


def panel_offenders(relative_path, key, ask):
    """The reasons why a panel does not read the home, in report order."""
    text = read(relative_path)
    found = []
    if ask not in text:
        found.append(f'{relative_path} holds no {ask}: the panel spells its own copy of the label')
    for number, line in enumerate(text.splitlines(), 1):
        if f'{key}:' in line:
            found.append(report((relative_path, number, line),
                                f'the panel states the pair in a row of its own; '
                                f'the home is {OWNER}'))
    count = text.count(f"'{key}'")
    if count != ASK_COUNT:
        found.append(f'{relative_path} quotes the slot name {key!r} {count} times, not {ASK_COUNT}: '
                     'the ask site is the one place that may name it, and the bare prefix bfPasteId '
                     'of annotator/ops.js:520 is another name')
    return found


class ConsolePasteLabelOwnerTest(unittest.TestCase):
    """One home for the paste label, and a report that names every second copy."""

    def test_the_home_is_one_row_per_slot_name_of_the_shared_table(self):
        """Case 1: the home holds the pair twice, and no other file quotes it."""
        text = read(OWNER)
        rows = owner_rows(text)
        offenders = []
        for key in (OPS_KEY, STAGE_KEY):
            value = rows.get(key)
            if value != PAIR:
                lines = text.splitlines()
                number = next((n for n, line in enumerate(lines, 1)
                               if line.strip().startswith(f'{key}:')
                               or any(literal in line for literal in LITERALS)), 0)
                where = (display(OWNER, number, lines[number - 1]) if number
                         else f'{OWNER}: the row "{key}" is absent')
                offenders.append(f'{where}  <- the SHARED_WORDS row "{key}" must carry {PAIR}; '
                                 f'it carried {value}')
        self.assertEqual([], offenders, '\n'.join(offenders))
        owner_lines = owner_span(text)
        offenders = []
        for relative_path in console_paths():
            offenders += stray_sites(relative_path, read(relative_path), owner_lines)
        self.assertEqual(
            [], [report(item, f'the pair stands in the SHARED_WORDS table of {OWNER} '
                              'and this line spells it a second time')
                 for item in offenders],
            'the pair must stand once, in the home table')
        for literal in LITERALS:
            count = text.count(literal)
            self.assertEqual(OWNER_ROW_COUNT, count,
                             f'{OWNER} must quote {literal} {OWNER_ROW_COUNT} times, '
                             f'one per slot row; it quotes it {count} times')

    def test_each_panel_reads_the_home_and_holds_no_row(self):
        """Case 2: each panel asks the home by name, and holds no row of the pair."""
        offenders = (panel_offenders(OPS, OPS_KEY, OPS_ASK)
                     + panel_offenders(STAGE, STAGE_KEY, STAGE_ASK))
        self.assertEqual([], offenders, 'both panels must read the one home')
        # The prefix of another name stands beside the slot name, so the count of
        # the quoted name proves that this guard read the slot name and not it.
        self.assertGreaterEqual(read(OPS).count('bfPasteId'), 1,
                                'annotator/ops.js:520 defines bfPasteId, and this case holds the '
                                'quoted slot name apart from that prefix')

    def test_the_shipped_page_publishes_the_home_before_both_panels(self):
        """The page loads the home first, then the two panels that ask it."""
        scripts = SCRIPTS.findall(read(PAGE))
        self.assertIn('app.js', scripts, f'{PAGE} must load annotator/app.js')
        for panel in ('vision-stage.js', 'ops.js'):
            self.assertIn(panel, scripts, f'{PAGE} must load annotator/{panel}')
            self.assertLess(scripts.index('app.js'), scripts.index(panel),
                            f'{PAGE} must load app.js before {panel}: the panels ask the home at '
                            'the first paint, and a later load answers nothing')

    def test_a_planted_row_of_the_pair_is_reported_with_its_file_and_line(self):
        """Case 3: a row that a panel states again is named by path and line."""
        plant = {
            OPS: ("bfCheck:['Check','检查']",
                  "bfPaste:['VOD link or id','回放链接或 id'],bfCheck:['Check','检查']"),
            STAGE: ("bcPasteGo:'Check',",
                    "bcPaste:'VOD link or id', bcPasteGo:'Check',"),
        }
        owner_lines = owner_span(read(OWNER))
        for relative_path, (anchor, row) in sorted(plant.items()):
            with self.subTest(panel=relative_path):
                text = read(relative_path)
                planted = text.replace(anchor, row, 1)
                self.assertNotEqual(text, planted, f'the plant must land in {relative_path}')
                lines = planted.splitlines()
                number = next(number for number, line in enumerate(lines, 1)
                              if any(literal in line for literal in LITERALS))
                offenders = stray_sites(relative_path, planted, owner_lines)
                self.assertEqual(1, len(offenders), offenders)
                self.assertEqual(display(relative_path, number, lines[number - 1]),
                                 display(*offenders[0]))
                self.assertIn(f'{relative_path}:{number}:',
                              report(offenders[0], 'the pair stands again'))


if __name__ == '__main__':
    unittest.main()
