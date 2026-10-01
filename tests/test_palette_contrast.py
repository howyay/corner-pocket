"""The palette is one token source, meets WCAG 2.2 AA in both themes, and carries
none of the colour values copied from the redesign zip (security audit P-6)."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ANNOTATOR = ROOT / 'annotator'


def tokens(block):
    return dict(re.findall(r'--([a-z0-9-]+):(#[0-9a-f]{6}(?:[0-9a-f]{2})?)\b', block))


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

    #: The 40 hex values that arrived with the third-party redesign zip (security audit P-6).
    #: They used to be read out of `docs/private-audit.md`; that document is deliberately not
    #: published (its copy is kept outside the repository at `.pm/pre-rewrite/private-audit.md`)
    #: and a fresh clone has to stay green, so the list lives here beside the check that needs it.
    ZIP_VALUES = (
        '#14110f #1a1613 #100e0c #241e19 #f6f1e6 #f2e9dd #b6a693 #8a7a68 #6d5f51 #c9a227 '
        '#e3c877 #dcbb46 #17120c #2b241d #7fc39a #16241c #3d5f4c #dfa93a #2a2013 #5c4a1e '
        '#eee6d8 #faf6ee #fffdf8 #e9e0d0 #171208 #241c12 #5b4f41 #7c6d5b #9b8b77 #8a6a12 '
        '#6d5210 #a07d18 #fdf8ee #d9cdb8 #256a45 #dfeade #a6c2ac #8a5307 #f6e9cf #d6bd8a'
    ).split()

    def test_no_zip_derived_colour_remains(self):
        values = self.ZIP_VALUES
        self.assertEqual(len(values), 40)
        for path in sorted(ANNOTATOR.glob('*.*')):
            if path.suffix not in ('.css', '.js', '.html', '.svg'):
                continue
            text = path.read_text().lower()
            for value in values:
                with self.subTest(file=path.name, value=value):
                    self.assertIsNone(re.search(re.escape(value) + r'(?![0-9a-f])', text))


if __name__ == '__main__':
    unittest.main()
