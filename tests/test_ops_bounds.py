"""Two bounds and one default of the operations layer, each held to one home.

``annotator/operations.py`` owns all three rules.

* **The entrant cap.**  ``ENTRANT_MAX`` is the named fact: one tournament signs up at
  most 128 entrants.  Two checks read that name - ``entrant_add``, the entrant a
  signed-up team adds, and ``pair_accept``, the teams a drawn pairing adds.  Until
  round 63 each check held its own literal 128, free to disagree with the other, and no
  case read either.
* **The appearance bounds.**  ``CLOTH_COLORS`` lists the cloth colours a
  ``settings_update`` accepts, and the lamp glow is a number from ``LAMP_GLOW_MIN`` to
  ``LAMP_GLOW_MAX``.  ``LAMP_GLOW_DEFAULT`` is the glow of a fresh document, and the
  console paints it before any request returns.  The console states all three facts again
  in ``annotator/ops.js``: the cloth option list, the glow range input and its fallback.

The shape of the console rule.  The console is one static file.  It reads no schema of
the server, and it draws the appearance panel before any request returns.  A bound the
server must send costs a route and a fetch for a decorative preview.  This module keeps
the two realms equal instead.  It reads the source text of ``annotator/ops.js`` and
compares that markup with the python names, the way ``tests/test_enroll_bound.py`` reads
the photo guard of the same file for the enroll bound.  This module never edits that
file.

Six rules, one pass over two files:

1. **owner rule** - ``ENTRANT_MAX`` is 128, ``CLOTH_COLORS`` is the four colours of
   today, the glow runs from 0 to 0.5, and its default is 0.22.  The cases freeze the four
   values.
2. **entrant rule** - 128 teams sign up and the 129th meets the cap, with no write.
3. **pairing rule** - a drawn pairing of two teams fills the cap when 126 entrants
   stand, and 127 entrants plus two teams is refused at 129, with no write.
4. **home rule** - the number stands on one line, both checks read the name, and no
   line compares the entrant count with a bare number.
5. **console rule** - the option list holds the owner's colours in the owner's order,
   and the range input holds the owner's two bounds.  The writer accepts every colour
   of the list and both ends of the range, and refuses one step past each edge.
6. **default rule** - the console fallback holds the owner's default, and the settings
   block of the owner reads the name.  The case reports a second statement of the default
   in the owner module.

What this case does not see
---------------------------
* It reads the console by one regex per bound.  A third statement of a bound - a fifth
  colour option outside the list, a second range input - is invisible to it.
* It reads text and not meaning.  A label the operator cannot understand passes, and a
  colour the preview paints outside the select is outside the rule.
* It reads the glow default by one regex in each realm.  A third statement of the default
  - a second fallback, a second literal in the settings block - is invisible to it.
* It reads the cloth default by one regex per realm.  The cloth literal of the console
  fallback and the cloth literal of the settings block are the two statements it holds.
* It pins the numbers of today and not the reason for them.  A later round that raises
  the cap must raise the frozen sizes here in the same change.
* The module holds other checks of the entrant count, such as the minimum of two
  entrants a start needs.  The rule of this round is the cap number.
* The cap cases count entrants.  The identity of an entrant is another rule.
"""
import re
import tempfile
import unittest
from pathlib import Path

from annotator.operations import (CLOTH_COLORS, CLOTH_DEFAULT, ENTRANT_MAX, LAMP_GLOW_DEFAULT,
                                  LAMP_GLOW_MAX, LAMP_GLOW_MIN, Operations)

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / 'annotator' / 'operations.py'
CONSOLE = ROOT / 'annotator' / 'ops.js'
OWNER_TEXT = OWNER.read_text(encoding='utf-8')
CONSOLE_TEXT = CONSOLE.read_text(encoding='utf-8')

#: The values the facts hold today: the cap, the cloth colours, the glow range and the
#: glow default.  The cases freeze them, so a reader can follow the ground of round 63.
CAP_TODAY = 128
COLORS_TODAY = ('#1d5c44', '#1f4a70', '#6a2130', '#2f3a3f')
GLOW_TODAY = (0.0, 0.5)
#: The glow default of the two realms today (round 85).
GLOW_DEFAULT_TODAY = 0.22

#: The cloth default of the two realms today (round 86).
CLOTH_DEFAULT_TODAY = '#1d5c44'

#: The one line that states the cap number.
CAP_HOME = re.compile(r'^ENTRANT_MAX = (\d+)$', re.MULTILINE)

#: One check of the entrant count against the cap number: the shape the cap must not take.
CAP_COPY = re.compile(r"len\(t\['entrants'\]\)[^#\n]*?[<>]=?\s*128\b")

#: One check of the entrant count that reads the owner name.
CAP_NAME = re.compile(r"len\(t\['entrants'\]\)[^#\n]*?[<>]=?\s*ENTRANT_MAX\b")

#: The cloth option list of the console: one colour and one label key for each row.
CONSOLE_COLORS = re.compile(r"\[(\['#[0-9a-f]{6}','[A-Za-z]+'\]"
                            r"(?:,\['#[0-9a-f]{6}','[A-Za-z]+'\])*)\]")

#: The lamp glow field of the console: the default and the four range attributes.
CONSOLE_GLOW = re.compile(r"input\('lampGlow',\s*([^,]+),\s*'range',\s*'([^']*)'\)")

#: One attribute of the range input, in the order the console writes it.
RANGE_ATTR = re.compile(r'(min|max|step)="([^"]*)"')

#: The console fallback of the lamp glow: the value the panel paints before a request
#: returns.
CONSOLE_GLOW_DEFAULT = re.compile(r'\?\?\s*([0-9.]+)')

#: One statement of the glow default as a bare number.  The scan reads the whole line,
#: because the settings line holds a '#' in the cloth colour.
GLOW_COPY = re.compile(r"lampGlow\s*=\s*[0-9]")

#: The console fallback of the cloth colour: the colour the panel paints before a request
#: returns.  The panel holds two copies, and both name the owner default.
CONSOLE_CLOTH_DEFAULT = re.compile(r"clothColor\|\|'(#[0-9a-f]{6})'")

#: The comment of one line of Python source.  A mark that follows a space starts the
#: comment, so the '#' of a colour literal stays in the code.
CLOTH_COMMENT = re.compile(r'\s#.*$')

#: One statement of the cloth default as a bare colour literal.  The scan reads the code
#: of the line and drops the comment, because a comment quotes the literal as a probe.  A
#: mark that follows a space starts the comment, so the '#' of the colour itself stays.
CLOTH_COLOR_COPY = re.compile(r"clothColor\s*=\s*'#[0-9a-f]{6}'")


def cap_copies(text):
    """The lines of ``text`` that compare the entrant count with the cap number."""
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if CAP_COPY.search(line.split('#', 1)[0])]


def glow_copies(text):
    """The lines of ``text`` that state the glow default as a bare number."""
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if GLOW_COPY.search(line)]


def cloth_copies(text):
    """The lines of ``text`` that state the cloth default as a bare colour literal."""
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if CLOTH_COLOR_COPY.search(CLOTH_COMMENT.sub('', line))]


class OpsBounds(unittest.TestCase):
    """The entrant cap and the appearance bounds of the operations layer."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ops = None

    def layer(self, name):
        """Open one operations layer over its own directory and keep it for the case."""
        self.ops = Operations(self.root / name)
        return self.ops

    def call(self, action, **fields):
        return self.ops.post(dict(action=action, revision=self.ops.get()['revision'], **fields))

    def teams(self, count):
        """Sign up ``count`` teams of two guests and return the state."""
        for n in range(count):
            self.call('entrant_add', members=[{'name': f'Guest {n} A'}, {'name': f'Guest {n} B'}])
        return self.ops.get()

    def test_the_entrant_rule_takes_the_cap_and_no_more(self):
        """128 teams sign up, and the 129th meets the cap without a write."""
        self.layer('entrant')
        self.call('tournament_setup', format='doubles')
        self.assertEqual(len(self.teams(CAP_TODAY)['tournament']['entrants']), CAP_TODAY)
        before = self.ops.path.read_bytes()
        with self.assertRaisesRegex(ValueError, '^Maximum 128 entrants$'):
            self.call('entrant_add', members=[{'name': 'Late A'}, {'name': 'Late B'}])
        self.assertEqual(self.ops.path.read_bytes(), before, 'a refused entrant must write nothing')
        self.assertEqual(len(self.ops.get()['tournament']['entrants']), CAP_TODAY)

    def test_the_pairing_rule_takes_the_cap_and_no_more(self):
        """129 entrants and teams is refused; 128 is accepted, on the same tournament."""
        self.layer('pairing')
        self.call('tournament_setup', format='doubles')
        self.assertEqual(len(self.teams(CAP_TODAY - 1)['tournament']['entrants']), CAP_TODAY - 1)
        for n in range(4):
            self.call('solo_add', member={'name': f'Solo {n}'})
        seed = self.call('pair_draw')['tournament']['pairing']['seed']
        before = self.ops.path.read_bytes()
        with self.assertRaisesRegex(ValueError, '^Maximum 128 entrants$'):
            self.call('pair_accept', seed=seed)
        self.assertEqual(self.ops.path.read_bytes(), before, 'a refused pairing must write nothing')
        state = self.ops.get()
        self.assertEqual(len(state['tournament']['entrants']), CAP_TODAY - 1)
        self.assertIsNotNone(state['tournament']['pairing'], 'the refused pairing must stand')
        # One entrant leaves, the pool stands, and the same pairing now fills the cap.
        self.call('pair_clear')
        removed = state['tournament']['entrants'][-1]['id']
        self.call('entrant_remove', id=removed)
        seed = self.call('pair_draw')['tournament']['pairing']['seed']
        state = self.call('pair_accept', seed=seed)
        self.assertEqual(len(state['tournament']['entrants']), CAP_TODAY)
        self.assertIsNone(state['tournament']['pairing'], 'an accepted pairing must clear')

    def test_the_cap_number_stands_on_one_line_and_both_checks_read_it(self):
        """One home for the number, and both checks of the count read the name."""
        self.assertEqual(ENTRANT_MAX, CAP_TODAY)
        self.assertEqual(CAP_HOME.findall(OWNER_TEXT), [str(CAP_TODAY)],
                         f'{OWNER.name} must state the cap number on one line')
        copies = cap_copies(OWNER_TEXT)
        self.assertEqual(copies, [], f'{OWNER.name} must hold no copy of the cap: {copies}')
        self.assertEqual(len(CAP_NAME.findall(OWNER_TEXT)), 2,
                         f'both checks of {OWNER.name} must read the name')

    def test_a_planted_copy_of_the_cap_is_reported(self):
        """The detector reports a second statement of the number, with its line."""
        planted = ("        elif action == 'entrant_add':\n"
                   "            if len(t['entrants']) >= 128:\n"
                   "                raise ValueError('Maximum 128 entrants')\n")
        self.assertEqual(cap_copies(planted), [(2, "if len(t['entrants']) >= 128:")])
        named = "            if len(t['entrants']) >= ENTRANT_MAX:\n"
        self.assertEqual(cap_copies(named), [], 'a check that reads the name is no copy')
        self.assertEqual(cap_copies(OWNER_TEXT), [], 'the live module states no copy')

    def test_the_console_cloth_list_is_the_writer_list(self):
        """The console offers the colours the writer accepts, in the writer's order."""
        hit = CONSOLE_COLORS.search(CONSOLE_TEXT)
        self.assertIsNotNone(hit, f'the cloth option list of {CONSOLE.name} changed shape')
        colours = re.findall(r"'(#[0-9a-f]{6})'", hit.group(1))
        self.assertEqual(colours, list(CLOTH_COLORS), 'the console list and the owner list differ')
        self.assertEqual(CLOTH_COLORS, COLORS_TODAY, 'the frozen cloth list of today')
        self.layer('cloth')
        for colour in colours:
            state = self.call('settings_update', clothColor=colour)
            self.assertEqual(state['settings']['clothColor'], colour)
        before = self.ops.path.read_bytes()
        with self.assertRaisesRegex(ValueError, '^Invalid cloth color$'):
            self.call('settings_update', clothColor='#123456')
        self.assertEqual(self.ops.path.read_bytes(), before)

    def test_the_console_range_is_the_writer_range(self):
        """The range input of the console holds the two bounds the writer applies."""
        hit = CONSOLE_GLOW.search(CONSOLE_TEXT)
        self.assertIsNotNone(hit, f'the lamp glow field of {CONSOLE.name} changed shape')
        attrs = dict(RANGE_ATTR.findall(hit.group(2)))
        self.assertEqual((float(attrs['min']), float(attrs['max'])), (LAMP_GLOW_MIN, LAMP_GLOW_MAX),
                         'the console range and the owner bound differ')
        self.assertEqual((LAMP_GLOW_MIN, LAMP_GLOW_MAX), GLOW_TODAY, 'the frozen range of today')
        step = float(attrs['step'])
        self.assertGreater(step, 0, 'the console needs a step above zero')
        span = (LAMP_GLOW_MAX - LAMP_GLOW_MIN) / step
        self.assertAlmostEqual(span, round(span), msg='the step must divide the range')
        self.layer('glow')
        for glow in GLOW_TODAY:
            state = self.call('settings_update', lampGlow=glow)
            self.assertEqual(state['settings']['lampGlow'], glow, 'both ends of the range must pass')
        before = self.ops.path.read_bytes()
        for bad in (LAMP_GLOW_MAX + 0.01, LAMP_GLOW_MIN - 0.01, float('nan'), float('inf'),
                    True, '0.2'):
            with self.assertRaisesRegex(ValueError, '^lampGlow must be between 0 and 0.5$'):
                self.call('settings_update', lampGlow=bad)
        self.assertEqual(self.ops.path.read_bytes(), before)

    def test_the_console_glow_default_is_the_owner_default(self):
        """The console paints the owner default, and the owner spells the number once."""
        hit = CONSOLE_GLOW.search(CONSOLE_TEXT)
        self.assertIsNotNone(hit, f'the lamp glow field of {CONSOLE.name} changed shape')
        fallback = CONSOLE_GLOW_DEFAULT.search(hit.group(1))
        self.assertIsNotNone(fallback, f'the lamp glow field of {CONSOLE.name} holds no fallback')
        self.assertEqual(float(fallback.group(1)), LAMP_GLOW_DEFAULT,
                         'the console fallback and the owner default differ')
        self.assertEqual(LAMP_GLOW_DEFAULT, GLOW_DEFAULT_TODAY, 'the frozen glow default of today')
        planted = "settings=dict(clothColor='#1d5c44', lampGlow=0.22,"
        self.assertEqual(glow_copies(planted), [(1, planted)],
                         'the detector must read a literal after a cloth colour')
        copies = glow_copies(OWNER_TEXT)
        self.assertEqual(copies, [], f'{OWNER.name} must hold no copy of the default: {copies}')
        self.assertIn('lampGlow=LAMP_GLOW_DEFAULT', OWNER_TEXT,
                      f'the settings block of {OWNER.name} must read the name')

    def test_the_console_cloth_default_is_the_owner_default(self):
        """The console paints the owner default, and the owner spells the colour once."""
        found = CONSOLE_CLOTH_DEFAULT.findall(CONSOLE_TEXT)
        self.assertEqual(len(found), 2, f'{CONSOLE.name} must hold two cloth fallbacks: {found}')
        self.assertEqual(found, [CLOTH_DEFAULT, CLOTH_DEFAULT],
                         'the console fallbacks and the owner default differ')
        self.assertEqual(CLOTH_DEFAULT, CLOTH_DEFAULT_TODAY, 'the frozen cloth default of today')
        planted = "settings=dict(clothColor='#1f4a70',"
        self.assertEqual(cloth_copies(planted), [(1, planted)],
                         'the detector must read a bare colour literal')
        named = "settings=dict(clothColor=CLOTH_DEFAULT,"
        self.assertEqual(cloth_copies(named), [], 'a line that reads the name is no copy')
        copies = cloth_copies(OWNER_TEXT)
        self.assertEqual(copies, [], f'{OWNER.name} must hold no copy of the default: {copies}')
        self.assertIn('clothColor=CLOTH_DEFAULT', OWNER_TEXT,
                      f'the settings block of {OWNER.name} must read the name')
