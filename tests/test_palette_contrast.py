"""The palette is one token source, meets WCAG 2.2 AA in both themes, and carries
none of the colour values copied from the redesign zip (security audit P-6).

`annotator/ops.css` owns the palette. The public board cannot load that file, so
`annotator/board.css` holds a copy of the dark block. The two files are a held
pair. The cases below fail when one copied value disagrees with the owner.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ANNOTATOR = ROOT / 'annotator'


def tokens(block):
    return dict(re.findall(r'--([a-z0-9-]+):(#[0-9a-f]{6}(?:[0-9a-f]{2})?)\b', block))


def dark_block(text):
    """The dark token block of one stylesheet, as a match of its own line."""
    return re.search(r'^:root\{color-scheme:dark;[^}]*\}', text, re.M)


def declarations(text, match):
    """(name, value, line) for each custom property the matched block declares.

    The line is the one the property starts on in `text`, not in the block, so a
    report can name the site a reader must open.
    """
    block = match.group(0)
    first = text.count('\n', 0, match.start())
    return [
        (item.group(1), item.group(2), first + block.count('\n', 0, item.start()) + 1)
        for item in re.finditer(r'--([a-z0-9-]+)\s*:\s*([^;}]+?)\s*(?=[;}])', block)
    ]


#: A value that names a colour. A board token with such a value must answer the owner.
COLOUR_VALUE = re.compile(r'^(?:#[0-9a-f]{3,8}|rgba?\()', re.I)

BOARD_SITE = 'annotator/board.css'
OWNER_SITE = 'annotator/ops.css'


def palette_drift(board_text, owner_text):
    """Every value the board copies and the owner answers with another value.

    One item per name: (name, board value, owner value, board site, owner site).
    The owner value is None when the owner holds no such name. A name only the
    board holds is not a drift unless its value is a colour: the board keeps its
    own non-colour tokens (--tv-xs).
    """
    board_match, owner_match = dark_block(board_text), dark_block(owner_text)
    if board_match is None:
        return []
    if owner_match is None:
        raise AssertionError('%s holds no dark token block' % OWNER_SITE)
    answer = {name: (value, line) for name, value, line in declarations(owner_text, owner_match)}
    drift = []
    for name, value, line in declarations(board_text, board_match):
        owner_value, owner_line = answer.get(name, (None, None))
        if owner_value == value:
            continue
        if owner_value is None and not COLOUR_VALUE.match(value):
            continue
        drift.append((name, value, owner_value,
                      '%s:%d' % (BOARD_SITE, line),
                      '%s:%d' % (OWNER_SITE, owner_line) if owner_line else OWNER_SITE))
    return drift


def drift_message(drift):
    """Each drift as one clause: the name, the two values and the two sites."""
    return '; '.join(
        '%s: the board holds %s at %s, the owner holds %s at %s'
        % (name, value, board_site, owner_value or 'no such name', owner_site)
        for name, value, owner_value, board_site, owner_site in drift)


def rgb(value):
    return [int(value[i:i + 2], 16) for i in (1, 3, 5)], (int(value[7:9], 16) / 255 if len(value) == 9 else 1)


def over(fg, bg):
    (f, a), (b, _) = rgb(fg), rgb(bg)
    return [round(f[i] * a + b[i] * (1 - a)) for i in range(3)]


def luminance(channels):
    lin = [c / 255 / 12.92 if c / 255 <= 0.03928 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(fg, bg):
    """Contrast of fg (may carry alpha) composited on the opaque bg."""
    x, y = luminance(over(fg, bg)), luminance(rgb(bg)[0])
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


class PaletteContrast(unittest.TestCase):
    def setUp(self):
        css = (ANNOTATOR / 'ops.css').read_text()
        dark = re.search(r'^:root\{color-scheme:dark;[^}]*\}', css, re.M)
        light = re.search(r'^:root\[data-theme=light\]\{[^}]*\}', css, re.M)
        self.assertTrue(dark and light, 'ops.css holds the dark and light token blocks')
        self.dark = tokens(dark.group(0))
        self.light = dict(self.dark, **tokens(light.group(0)))

    def test_every_text_pair_is_aa_in_both_themes(self):
        inks = ('ink-hi', 'ink', 'ink-mid', 'ink-dim', 'ink-faint', 'brass', 'brass-hi', 'green', 'blue', 'amber', 'red')
        surfaces = ('bg', 'panel', 'panel2', 'rail', 'neutral-bg', 'live-bg')
        for name, t in (('dark', self.dark), ('light', self.light)):
            pairs = [(i, s) for i in inks for s in surfaces]
            pairs += [(k, k + '-bg') for k in ('green', 'blue', 'amber', 'red')]
            pairs += [('red-ink', 'red-bg'), ('brass-fg', 'brass'), ('brass-fg', 'brass-hover')]
            for fg, bg in pairs:
                with self.subTest(theme=name, fg=fg, bg=bg):
                    self.assertGreaterEqual(ratio(t[fg], t[bg]), 4.5)

    def test_controls_and_focus_are_three_to_one(self):
        for name, t in (('dark', self.dark), ('light', self.light)):
            with self.subTest(theme=name):
                self.assertGreaterEqual(ratio(t['btn-line'], t['panel']), 3)
                self.assertGreaterEqual(ratio(t['brass'], t['bg']), 3)

    def test_stage_labels_read_on_the_dark_frame_in_both_themes(self):
        plate = over(self.dark['stage-plate'], self.dark['stage-bg'])
        plate = '#%02x%02x%02x' % tuple(plate)
        for ink in ('stage-ink', 'stage-ink-hi', 'stage-event', 'stage-bound',
                    'stage-brass-hi', 'stage-green', 'stage-amber', 'stage-red'):
            with self.subTest(ink=ink):
                self.assertGreaterEqual(ratio(self.dark[ink], plate), 4.5)

    def test_one_token_source(self):
        app = (ANNOTATOR / 'app.css').read_text()
        # Only the overlay's remap of accents onto the stage accents (var(), never a value).
        declared = re.findall(r'--([a-z0-9-]+)\s*:\s*([^;}]+)', app)
        self.assertTrue(all(v.strip().startswith('var(--stage-') for _, v in declared), declared)
        self.assertEqual(re.findall(r'#[0-9a-fA-F]{3,8}\b|rgba?\(', app), [], 'app.css has no colour literals')

    def test_every_board_value_answers_the_owner(self):
        """One source: the board's copy of the palette must answer ops.css."""
        board = (ANNOTATOR / 'board.css').read_text()
        owner = (ANNOTATOR / 'ops.css').read_text()
        drift = palette_drift(board, owner)
        self.assertEqual([], drift,
                         'the board copy disagrees with %s: %s' % (OWNER_SITE, drift_message(drift)))

    def test_a_planted_drift_is_reported_with_two_values_and_two_sites(self):
        """A forged copy with one changed value must be reported, with both sites."""
        board = (ANNOTATOR / 'board.css').read_text()
        owner = (ANNOTATOR / 'ops.css').read_text()
        planted = board.replace('--brass:#cca632', '--brass:#ff0000')
        self.assertNotEqual(planted, board, 'the planted value is not in the board copy')
        self.assertEqual(1, planted.count('--brass:#ff0000'), 'the forged text holds one planted value')
        self.assertEqual(1, owner.count('--brass:#cca632'), 'the owner holds one brass value')
        drift = palette_drift(planted, owner)
        self.assertEqual(['brass'], [item[0] for item in drift], drift_message(drift))
        name, value, owner_value, board_site, owner_site = drift[0]
        self.assertEqual(('#ff0000', '#cca632'), (value, owner_value))
        self.assertEqual('%s:%d' % (BOARD_SITE, planted.count('\n', 0, planted.index('--brass:#ff0000')) + 1),
                         board_site, 'the report names the line of the planted value')
        self.assertEqual('%s:%d' % (OWNER_SITE, owner.count('\n', 0, owner.index('--brass:#cca632')) + 1),
                         owner_site, 'the report names the line of the owner value')
        message = drift_message(drift)
        for part in (name, value, owner_value, board_site, owner_site):
            self.assertIn(part, message, message)

    def test_the_page_and_the_stylesheet_hold_one_source(self):
        """The page loads the owner when the copy is gone; while the copy stays, both must agree."""
        page = (ANNOTATOR / 'board.html').read_text()
        board = (ANNOTATOR / 'board.css').read_text()
        sheets = []
        for tag in re.findall(r'<link\b[^>]*>', page):
            if 'stylesheet' in tag:
                sheets.extend(re.findall(r'href="([^"]+)"', tag))
        loads_owner = any(sheet.split('?')[0].endswith('ops.css') for sheet in sheets)
        block = dark_block(board)
        copied = ([name for name, value, _ in declarations(board, block) if COLOUR_VALUE.match(value)]
                  if block else [])
        if not copied:
            self.assertTrue(loads_owner,
                            'board.css keeps no palette, so the page must load its owner %s; the page '
                            'loads %s' % (OWNER_SITE, sheets))
            return
        self.assertFalse(loads_owner,
                         'board.css copies %d colour(s) and the page also loads %s: one page would '
                         'hold two sources' % (len(copied), OWNER_SITE))
        drift = palette_drift(board, (ANNOTATOR / 'ops.css').read_text())
        self.assertEqual([], drift, 'the held pair disagrees: %s' % drift_message(drift))

    #: The 40 hex values that arrived with the third-party redesign zip (security audit P-6).
    #: They used to be read out of the operator's private audit record, which is deliberately
    #: not published and is kept outside the repository; a fresh clone has to stay green, so
    #: the list lives here beside the check that needs it.
    ZIP_VALUES = (
        '#14110f #1a1613 #100e0c #241e19 #f6f1e6 #f2e9dd #b6a693 #8a7a68 #6d5f51 #c9a227 '
        '#e3c877 #dcbb46 #17120c #2b241d #7fc39a #16241c #3d5f4c #dfa93a #2a2013 #5c4a1e '
        '#eee6d8 #faf6ee #fffdf8 #e9e0d0 #171208 #241c12 #5b4f41 #7c6d5b #9b8b77 #8a6a12 '
        '#6d5210 #a07d18 #fdf8ee #d9cdb8 #256a45 #dfeade #a6c2ac #8a5307 #f6e9cf #d6bd8a'
    ).split()

    #: Suffixes that can carry a colour literal, and the directory the walk steps past.
    SCANNED_SUFFIXES = ('.css', '.js', '.html', '.svg')
    SKIPPED_DIRS = ('__pycache__',)

    #: A floor, never an equality: a scan that stops reaching files must fail, but a
    #: new stylesheet must not. The floor sits below today's count on purpose, so it
    #: is not a second hand-written count in disguise.
    SCANNED_FLOOR = 10

    def scanned_files(self):
        """Every source file under annotator/, at any depth, minus the bytecode caches."""
        return [
            path for path in sorted(ANNOTATOR.rglob('*'))
            if path.is_file()
            and path.suffix in self.SCANNED_SUFFIXES
            and not set(path.relative_to(ANNOTATOR).parts[:-1]) & set(self.SKIPPED_DIRS)
        ]

    def test_no_zip_derived_colour_remains(self):
        values = self.ZIP_VALUES
        self.assertTrue(values, 'the zip value list is not empty')
        self.assertEqual(len(values), len(set(values)), 'the zip value list repeats no value')
        files = self.scanned_files()
        self.assertGreaterEqual(
            len(files), self.SCANNED_FLOOR,
            'the scan reached %d file(s), below the floor of %d: %s'
            % (len(files), self.SCANNED_FLOOR, [str(p.relative_to(ANNOTATOR)) for p in files]))
        for path in files:
            text = path.read_text().lower()
            for value in values:
                with self.subTest(file=path.name, value=value):
                    self.assertIsNone(
                        re.search(re.escape(value) + r'(?![0-9a-f])', text),
                        '%s carries the zip-derived value %s; the scan reached %d file(s)'
                        % (path.relative_to(ANNOTATOR), value, len(files)))


if __name__ == '__main__':
    unittest.main()
