"""Two bounds of the operations layer, each held to one home.

``annotator/operations.py`` owns both rules.

* **The entrant cap.**  ``ENTRANT_MAX`` is the named fact: one tournament signs up at
  most 128 entrants.  Two checks read that name - ``entrant_add``, the entrant a
  signed-up team adds, and ``pair_accept``, the teams a drawn pairing adds.  Until
  round 63 each check held its own literal 128, free to disagree with the other, and no
  case read either.
* **The appearance bounds.**  ``CLOTH_COLORS`` lists the cloth colours a
  ``settings_update`` accepts, and the lamp glow is a number from ``LAMP_GLOW_MIN`` to
  ``LAMP_GLOW_MAX``.  The console states both bounds again in ``annotator/ops.js``: the
  option list of the cloth select and the range input of the lamp glow.

The shape of the console rule.  The console is one static file.  It reads no schema of
the server, and it draws the appearance panel before any request returns.  A bound the
server must send costs a route and a fetch for a decorative preview.  This module keeps
the two realms equal instead.  It reads the source text of ``annotator/ops.js`` and
compares that markup with the python names, the way ``tests/test_enroll_bound.py`` reads
the photo guard of the same file for the enroll bound.  This module never edits that
file.

Five rules, one pass over two files:

1. **owner rule** - ``ENTRANT_MAX`` is 128, ``CLOTH_COLORS`` is the four colours of
   today, and the glow runs from 0 to 0.5.  The cases freeze the three values.
2. **entrant rule** - 128 teams sign up and the 129th meets the cap, with no write.
3. **pairing rule** - a drawn pairing of two teams fills the cap when 126 entrants
   stand, and 127 entrants plus two teams is refused at 129, with no write.
4. **home rule** - the number stands on one line, both checks read the name, and no
   line compares the entrant count with a bare number.
5. **console rule** - the option list holds the owner's colours in the owner's order,
   and the range input holds the owner's two bounds.  The writer accepts every colour
   of the list and both ends of the range, and refuses one step past each edge.

What this case does not see
---------------------------
* It reads the console by one regex per bound.  A third statement of a bound - a fifth
  colour option outside the list, a second range input - is invisible to it.
* It reads text and not meaning.  A label the operator cannot understand passes, and a
  colour the preview paints outside the select is outside the rule.
* The glow default (0.22) also stands in both realms, and no case here holds it equal.
  The rule of this round is the bound and the option list.
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

from annotator.operations import (CLOTH_COLORS, ENTRANT_MAX, LAMP_GLOW_MAX, LAMP_GLOW_MIN,
                                  Operations)

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / 'annotator' / 'operations.py'
CONSOLE = ROOT / 'annotator' / 'ops.js'
OWNER_TEXT = OWNER.read_text(encoding='utf-8')
CONSOLE_TEXT = CONSOLE.read_text(encoding='utf-8')

#: The three values the bounds hold today.  The cases freeze them, so a reader can
#: follow the ground of round 63.
CAP_TODAY = 128
COLORS_TODAY = ('#1d5c44', '#1f4a70', '#6a2130', '#2f3a3f')
GLOW_TODAY = (0.0, 0.5)

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


def cap_copies(text):
    """The lines of ``text`` that compare the entrant count with the cap number."""
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if CAP_COPY.search(line.split('#', 1)[0])]


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
