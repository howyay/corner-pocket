"""The shell's width system and body face keep one answer in the page copies.

`annotator/ops.css` owns the width and space tokens (`--page-max`, `--measure`,
`--sp-*`) and the body face (`--body`).  `annotator/app.html` links `/app.css`
alone, and `annotator/board.html` links `./board.css` alone, so a standalone page
inherits nothing and its stylesheet holds a value a second time:

  annotator/app.css:18   max-width: var(--page-max, 1560px)
                         padding: var(--sp-3, 12px) clamp(var(--sp-3, 12px), 2.4vw, var(--sp-6, 32px))
  annotator/app.css:22   max-width: var(--measure, 70ch)
  annotator/board.css:19 --body:'Barlow','Noto Sans SC',...,Arial,sans-serif
  annotator/board.css:23 html{... font-family:var(--body); ...}

The copies must stay.  This module holds the two sides equal, and it names the
file and the line of a value that disagrees.

The palette guard reads the same held pair.  Its token pattern
(`tests/test_palette_contrast.py:17`) matches colour values only, so no case
there reads the frame literals or `--body`.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ANNOTATOR = ROOT / 'annotator'

OWNER_SITE = 'annotator/ops.css'
APP_SITE = 'annotator/app.css'
BOARD_SITE = 'annotator/board.css'

#: The base token block of a stylesheet: `:root{...}` without a theme attribute.
#: The theme block of ops.css re-decides colours only, so it stays out of the map.
ROOT_BLOCK = re.compile(r'^:root\{([^}]*)\}', re.M)

#: One custom property of a block.  The lookahead keeps the value free of `;` and
#: `}`, and `$` reaches the last declaration of a block: the block pattern stops
#: at the `}`, so that declaration has no `}` of its own to end it.
DECLARATION = re.compile(r'--([a-z0-9-]+)\s*:\s*([^;}]+?)\s*(?=[;}]|$)')

#: `var(--name, literal)` with a literal fallback.  A fallback that names another
#: `var()` is a remap of a token, not a copy of an owner value, so one level of
#: brackets is allowed and a nested `var(` is not read as a value.
FALLBACK = re.compile(r'var\(\s*--([a-z0-9-]+)\s*,\s*((?:[^()]|\([^()]*\))+?)\s*\)')


def line_of(text, index):
    """The 1-based line of one character offset in `text`."""
    return text.count('\n', 0, index) + 1


def owner_tokens(text):
    """`name -> (value, line)` for each token the base `:root` blocks declare.

    The line is the one the declaration starts on in `text`, not in the block, so
    a report can name the site a reader must open.
    """
    answer = {}
    for block in ROOT_BLOCK.finditer(text):
        first = line_of(text, block.start())
        for item in DECLARATION.finditer(block.group(1)):
            answer.setdefault(item.group(1),
                              (item.group(2), first + block.group(1).count('\n', 0, item.start())))
    return answer


def app_fallbacks(text):
    """`(name, fallback, line)` for each `var(--name, literal)` site in app.css."""
    return [(item.group(1), item.group(2), line_of(text, item.start()))
            for item in FALLBACK.finditer(text)]


def copied_sites(app_text, board_text):
    """`(name, value, site)` for each distinct site that copies an owner token.

    The app page holds the fallback literals.  Two rules can name one token on
    one line, and that line is one site.  The board page holds a second
    declaration of `--body`, which its `html` rule reads.
    """
    found = dict.fromkeys(
        (name, value, '%s:%d' % (APP_SITE, line)) for name, value, line in app_fallbacks(app_text))
    board = owner_tokens(board_text)
    if 'body' in board:
        found[('body', board['body'][0], '%s:%d' % (BOARD_SITE, board['body'][1]))] = None
    return list(found)


def drift(app_text, board_text, owner_text):
    """Every copy site whose value does not answer the owner.

    One item per site: `(name, copy value, owner value or None, copy site, owner
    site)`.  The owner value is None when the owner holds no such name, and the
    owner site is then the file alone: there is no line to open.
    """
    answer = owner_tokens(owner_text)
    found = []
    for name, value, site in copied_sites(app_text, board_text):
        owner_value, owner_line = answer.get(name, (None, None))
        if owner_value == value:
            continue
        found.append((name, value, owner_value, site,
                      '%s:%d' % (OWNER_SITE, owner_line) if owner_line else OWNER_SITE))
    return found


def drift_message(drift):
    """One clause per item: the name, the two values and the two sites."""
    return '; '.join(
        '%s: the copy holds %s at %s, the owner holds %s at %s'
        % (name, value, copy_site, owner_value if owner_value else 'no such name', owner_site)
        for name, value, owner_value, copy_site, owner_site in drift)


def drift_at(items, site):
    """The items whose copy site is in one file."""
    return [item for item in items if item[3].startswith(site + ':')]


def owner_without(owner_text, name):
    """The owner text with the declaration of `name` deleted, as a plant.

    The plant removes the declaration from the line the owner token map names, so
    it takes the token away and it leaves the block in place.
    """
    value, line = owner_tokens(owner_text)[name]
    lines = owner_text.splitlines(keepends=True)
    lines[line - 1] = re.sub(r'--%s\s*:\s*%s' % (re.escape(name), re.escape(value)),
                             '', lines[line - 1], count=1)
    return ''.join(lines)


class StylesheetOwner(unittest.TestCase):
    def setUp(self):
        self.ops = (ANNOTATOR / 'ops.css').read_text()
        self.app = (ANNOTATOR / 'app.css').read_text()
        self.board = (ANNOTATOR / 'board.css').read_text()

    def test_every_app_fallback_answers_the_owner(self):
        """Fact one: the width and space literals of the app copy."""
        found = drift_at(drift(self.app, self.board, self.ops), APP_SITE)
        self.assertEqual([], found,
                         'the app copy disagrees with %s: %s' % (OWNER_SITE, drift_message(found)))

    def test_the_app_copy_names_the_frame_tokens(self):
        """The standalone app page links app.css alone, so the frame must stay here."""
        named = sorted({name for name, value, line in app_fallbacks(self.app)})
        for name in ('page-max', 'measure'):
            with self.subTest(token=name):
                self.assertIn(name, named,
                              'the app copy names --%s, so the standalone page keeps its frame '
                              'and its measure; it names %s' % (name, named))
        self.assertTrue([name for name in named if name.startswith('sp-')],
                        'the app copy names a --sp-* token; it names %s' % named)

    def test_the_board_body_face_answers_the_owner(self):
        """Fact two: the board's second declaration of the body face."""
        copy_item = owner_tokens(self.board).get('body')
        self.assertIsNotNone(copy_item, 'board.css declares --body in its :root block')
        owner_item = owner_tokens(self.ops).get('body')
        self.assertIsNotNone(owner_item, '%s declares --body' % OWNER_SITE)
        self.assertEqual(owner_item[0], copy_item[0],
                         '%s:%d holds --body %s; the owner holds %s at %s:%d'
                         % (BOARD_SITE, copy_item[1], copy_item[0],
                            owner_item[0], OWNER_SITE, owner_item[1]))

    def test_the_board_face_is_the_live_face(self):
        """The board reads the copied token, so the copy is not dead text."""
        uses = [line_of(self.board, item.start()) for item in re.finditer(r'var\(--body\)', self.board)]
        self.assertTrue(uses, 'board.css reads var(--body) at line(s) %s' % uses)
        declared = [found for found in re.finditer(r'--body\s*:', self.board)]
        self.assertEqual(1, len(declared),
                         'board.css declares --body once: %s' % [line_of(self.board, item.start())
                                                                 for item in declared])

    def test_a_planted_frame_value_is_reported_with_its_site(self):
        """Fact one, forged: one changed literal must be named with its file and line."""
        site = 'var(--page-max, 1560px)'
        self.assertEqual(1, self.app.count(site), 'app.css holds one %s site' % site)
        planted = self.app.replace(site, 'var(--page-max, 1561px)')
        found = drift_at(drift(planted, self.board, self.ops), APP_SITE)
        self.assertEqual(['page-max'], [name for name, value, owner, copy_site, owner_site in found],
                         drift_message(found))
        name, value, owner_value, copy_site, owner_site = found[0]
        self.assertEqual(('1561px', '1560px'), (value, owner_value),
                         'the report holds the two values: %s' % drift_message(found))
        line = line_of(self.app, self.app.index(site))
        self.assertEqual('%s:%d' % (APP_SITE, line), copy_site, drift_message(found))
        self.assertIn(site, self.app.splitlines()[line - 1],
                      'the reported line holds the copy site')
        owner_line = owner_tokens(self.ops)['page-max'][1]
        self.assertEqual('%s:%d' % (OWNER_SITE, owner_line), owner_site, drift_message(found))
        self.assertIn('--page-max:1560px', self.ops.splitlines()[owner_line - 1],
                      'the reported line holds the owner declaration')
        for part in (APP_SITE, copy_site, OWNER_SITE, owner_site):
            self.assertIn(part, drift_message(found))

    def test_a_planted_body_value_is_reported_with_its_site(self):
        """Fact two, forged: one changed family must be named with its file and line."""
        site = "--body:'Barlow'"
        self.assertEqual(1, self.board.count(site), 'board.css holds one %s site' % site)
        planted = self.board.replace(site, "--body:'BarlowX'", 1)
        found = drift_at(drift(self.app, planted, self.ops), BOARD_SITE)
        self.assertEqual(['body'], [name for name, value, owner, copy_site, owner_site in found],
                         drift_message(found))
        name, value, owner_value, copy_site, owner_site = found[0]
        self.assertIn('BarlowX', value, drift_message(found))
        self.assertNotIn('BarlowX', owner_value, drift_message(found))
        line = owner_tokens(self.board)['body'][1]
        self.assertEqual('%s:%d' % (BOARD_SITE, line), copy_site, drift_message(found))
        self.assertIn(site, self.board.splitlines()[line - 1],
                      'the reported line holds the copy site')
        owner_line = owner_tokens(self.ops)['body'][1]
        self.assertEqual('%s:%d' % (OWNER_SITE, owner_line), owner_site, drift_message(found))
        for part in (BOARD_SITE, copy_site, OWNER_SITE, owner_site):
            self.assertIn(part, drift_message(found))

    def test_an_owner_removal_is_reported_for_every_copied_name(self):
        """An owner that stops declaring a copied token must not pass in silence."""
        names = sorted({name for name, value, site in copied_sites(self.app, self.board)})
        self.assertTrue(names, 'the two copies name at least one owner token')
        for name in names:
            with self.subTest(token=name):
                planted = owner_without(self.ops, name)
                self.assertNotIn('--%s:' % name, planted,
                                 'the plant removed the declaration of --%s' % name)
                found = [item for item in drift(self.app, self.board, planted)
                         if item[0] == name and item[2] is None]
                self.assertTrue(found,
                                'the report names --%s as lost from %s: %s'
                                % (name, OWNER_SITE, drift_message(drift(self.app, self.board, planted))))


if __name__ == '__main__':
    unittest.main()
