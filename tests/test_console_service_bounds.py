"""One rate bound and one race set, each held to one home in the console and one in the service.

Round 64, two rows of the walk of this round.

* **The replay rate bound.**  ``annotator/unified_server.py`` owns what the service
  accepts: ``_REPLAY_RATE_MAX = 8.0``, and ``replay_request`` refuses a rate above it.
  ``annotator/ops.js`` owns what the console offers: ``REPLAY_RATE_MIN``,
  ``REPLAY_RATE_MAX`` and ``REPLAY_RATE_STEP``, and ``pickReplay`` refuses a larger
  rate with the sentence that names the bound.  Until round 64 the field in
  ``annotator/vision-stage.js`` stated a third answer - ``min="0.25" max="4"
  step="0.25"`` - so the spinner of a number input stopped at 4 while the picker took
  8.  The field now prints the three numbers the console hands it in the option bag
  (``opts.replayRate``) and states no number of its own.
* **The race-to set.**  ``annotator/operations.py`` owns the range the service accepts,
  and ``tournament_setup`` reads the two names of that range.  ``annotator/ops.js``
  holds ``RACE_TO_OPTIONS``, the six races both forms offer.  The console offers fewer
  values than the service accepts, on purpose: an operator calls a race to an odd number
  of frames.

The shape of the console rule.  The console is one static file.  It reads no schema of the
server, and it draws its panel before any request returns.  A bound the server must send
costs a route and a fetch for a form field.  This module keeps the two realms equal
instead.  It reads the source text of ``annotator/ops.js`` and ``annotator/vision-stage.js``
and compares that text with the python names, the way ``tests/test_enroll_bound.py`` reads
the photo guard of the same file for the enroll bound.  This module never edits those files.

Why a new module, and not ``tests/test_ops_bounds.py``: that module holds the entrant cap
and the appearance bounds of round 63.  This module holds the two bounds of round 64, and
the two write scopes stay apart.

Five rules, one pass over four files:

1. **home rule** - the three console numbers stand on three lines of ``annotator/ops.js``,
   the six race values stand on one line of the same file, and no other line of the
   console states either bound.
2. **rate rule** - the console offers a rate from 0.25 to 8, the service accepts a rate up
   to ``_REPLAY_RATE_MAX``, and the two largest values are equal.
3. **hand rule** - the console hands the three numbers to the stage in the option bag,
   the stage prints them in the rate field, and the stage states no number of its own.
4. **race rule** - both forms read the one race list, every value of that list is a race
   the service accepts, and the list is narrower than the service range.
5. **copy rule** - a planted second statement of either bound is reported, with its line.

What this case does not see
---------------------------
* It reads the console by one regex per statement.  A third statement of the rate bound
  in a form this module does not match - a second rate field, a bound built at run time -
  is invisible to it.
* It reads text and not meaning.  The stage could print the bag in a field the operator
  never sees and pass; the browser check of the row is another thing.
* The rate the console offers and the rate the service accepts are held equal.  The
  pacing of a replay at that rate, and the drift the operator reads, are other rules.
* It pins the numbers of today and not the reason for them.  A later round that raises
  ``_REPLAY_RATE_MAX`` must raise the frozen pair here in the same change.
* The race list is narrower than the service range.  Which six races the console should
  offer is a product decision, and this module holds only that the six it offers are
  legal and that both forms offer the same six.
"""
import ast
import re
import tempfile
import unittest
from pathlib import Path

from annotator.operations import Operations
from annotator.unified_server import _REPLAY_RATE_MAX, replay_request

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / 'annotator' / 'ops.js'
STAGE = ROOT / 'annotator' / 'vision-stage.js'
OPERATIONS = ROOT / 'annotator' / 'operations.py'
CONSOLE_TEXT = CONSOLE.read_text(encoding='utf-8')
STAGE_TEXT = STAGE.read_text(encoding='utf-8')
OPERATIONS_TEXT = OPERATIONS.read_text(encoding='utf-8')
OPERATIONS_TREE = ast.parse(OPERATIONS_TEXT)

#: The values the two bounds hold today.  The cases freeze them, so a reader can follow
#: the ground of round 64.
RATE_TODAY = {'REPLAY_RATE_MIN': 0.25, 'REPLAY_RATE_MAX': 8.0, 'REPLAY_RATE_STEP': 0.25}
RACE_TODAY = (1, 99)
RACE_VALUES_TODAY = (1, 3, 5, 7, 9, 11)

#: The one line of the console that states each rate number.
RATE_HOME = re.compile(r'^const (REPLAY_RATE_(?:MIN|MAX|STEP))=([0-9.]+);$', re.MULTILINE)

#: The option bag entry the console hands the stage: the three numbers, by name.
RATE_BAG = re.compile(r'replayRate:\{min:REPLAY_RATE_MIN,max:REPLAY_RATE_MAX,step:REPLAY_RATE_STEP\}')

#: The rate field of the stage: it prints the helper and writes no attribute of its own.
RATE_FIELD = re.compile(r'data-vs-field="vod-rate"\$\{rateBoundAttrs\(\)\}')

#: The helper that prints the bag.  It reads the console's rule and no other source.
RATE_HAND = re.compile(r'const rule = opts && opts\.replayRate;')

#: One attribute of the rate field: the shape that states a number the stage owns.
RATE_ATTR = re.compile(r'data-vs-field="vod-rate"[^>]*?(?:min|max|step)="')

#: One refusal of a rate above a bare number: the shape the console must not take.
RATE_LITERAL = re.compile(r'rate\s*>\s*[0-9]')

#: The one line of the console that states the race values.
RACE_HOME = re.compile(r'^const RACE_TO_OPTIONS=\[([0-9,]+)\];$', re.MULTILINE)

#: One select that reads the race list by name.  Both forms must hold this shape.
RACE_READ = re.compile(r'RACE_TO_OPTIONS\.map\(n=>option\(n,n,')

#: The six values as a bare list.  One statement of them is the home, and no more.
RACE_LITERAL = '[1,3,5,7,9,11]'


def rate_copies(text):
    """The lines of ``text`` where a rate field states a bound of its own."""
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if RATE_ATTR.search(line)]


def rate_literal_copies(text):
    """The lines of ``text`` that refuse a rate by comparing it with a bare number."""
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if RATE_LITERAL.search(line)]


def race_copies(text):
    """The lines of ``text`` that state the six race values outside the one home."""
    return [(number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if RACE_LITERAL in line and not RACE_HOME.match(line)]


def module_numbers(tree):
    """The module-level integer names of one file, by name."""
    named = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if type(node.value.value) is not int:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                named[target.id] = node.value.value
    return named


def integer_bounds(tree, field):
    """Every ``integer(...)`` bound one field receives, as (line, low, high).

    ``annotator/operations.py`` states a bound as a literal or as a module name.  A later
    round may move one to the other, so this reader accepts both shapes and reports a
    bound it cannot resolve instead of guessing a number.
    """
    named = module_numbers(tree)
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != 'integer' or len(node.args) < 4:
            continue
        if field not in ast.unparse(node.args[0]):
            continue
        rows.append((node.lineno, resolve(node.args[1], named), resolve(node.args[2], named)))
    return rows


def resolve(node, named):
    """One bound of an ``integer(...)`` call: a literal, or a module name of that file."""
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.Name) and node.id in named:
        return named[node.id]
    raise AssertionError(f'a race bound is neither a literal nor a module name: {ast.unparse(node)}')


class ConsoleServiceBounds(unittest.TestCase):
    """The replay rate bound and the race-to set, across the console and the service."""

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

    def test_the_rate_bound_stands_once_in_the_console(self):
        """Three console numbers, three lines, and no other statement of the bound."""
        home = RATE_HOME.findall(CONSOLE_TEXT)
        self.assertEqual(dict((key, float(value)) for key, value in home), RATE_TODAY,
                         f'{CONSOLE.name} must state the three rate numbers once each')
        self.assertIsNotNone(RATE_BAG.search(CONSOLE_TEXT),
                             f'{CONSOLE.name} must hand the three numbers to the stage, by name')
        copies = rate_literal_copies(CONSOLE_TEXT)
        self.assertEqual(copies, [], f'{CONSOLE.name} must refuse a rate through the name: {copies}')

    def test_the_stage_prints_the_rate_the_console_offers(self):
        """The field reads the bag, and the stage holds no rate number of its own."""
        self.assertIsNotNone(RATE_FIELD.search(STAGE_TEXT),
                             f'the rate field of {STAGE.name} changed shape')
        self.assertIsNotNone(RATE_HAND.search(STAGE_TEXT),
                             f'the rate field of {STAGE.name} must read opts.replayRate')
        copies = rate_copies(STAGE_TEXT)
        self.assertEqual(copies, [], f'{STAGE.name} must hold no rate bound of its own: {copies}')

    def test_the_console_rate_bound_is_the_service_bound(self):
        """The console offers 0.25 to 8; the service accepts to ``_REPLAY_RATE_MAX``."""
        low = RATE_TODAY['REPLAY_RATE_MIN']
        high = RATE_TODAY['REPLAY_RATE_MAX']
        self.assertEqual(high, _REPLAY_RATE_MAX, 'the console bound and the service bound must agree')
        step = RATE_TODAY['REPLAY_RATE_STEP']
        span = (high - low) / step
        self.assertAlmostEqual(span, round(span), msg='the step must divide the range')
        for rate in (low, low + step, 1.0, high):
            self.assertEqual(replay_request({'kind': 'vod-replay', 'vod_id': '1', 'rate': rate})['rate'],
                             float(rate), f'the service must take the rate {rate} the console offers')

    def test_the_race_set_is_narrower_than_the_service_range(self):
        """Both checks read the owner range, the console set sits inside it, and no write follows a refusal."""
        rows = integer_bounds(OPERATIONS_TREE, 'raceTo')
        self.assertEqual(len(rows), 2, f'two checks of {OPERATIONS.name} must bound raceTo')
        bounds = set((low, high) for _, low, high in rows)
        self.assertEqual(bounds, {RACE_TODAY}, f'both checks must hold {RACE_TODAY}')
        hit = RACE_HOME.search(CONSOLE_TEXT)
        self.assertIsNotNone(hit, f'the race list of {CONSOLE.name} changed shape')
        values = tuple(int(value) for value in hit.group(1).split(','))
        self.assertEqual(values, RACE_VALUES_TODAY, f'the six races of {CONSOLE.name} today')
        low, high = RACE_TODAY
        self.assertTrue(all(low <= value <= high for value in values),
                        'the console must offer no race the service refuses')
        self.assertLess(len(values), high - low + 1,
                        'the console offers fewer races than the service accepts, on purpose')
        self.layer('race')
        for value in (low, high):
            state = self.call('tournament_setup', raceTo=value)
            self.assertEqual(state['tournament']['raceTo'], value, 'the service must take each edge')
        before = self.ops.path.read_bytes()
        for bad in (low - 1, high + 1):
            with self.assertRaisesRegex(ValueError, '^raceTo must be an integer from 1 to 99$'):
                self.call('tournament_setup', raceTo=bad)
        self.assertEqual(self.ops.path.read_bytes(), before, 'a refused race must write nothing')

    def test_both_race_forms_read_the_one_list(self):
        """One statement of the six values, and the two selects read it by name."""
        self.assertEqual(CONSOLE_TEXT.count(RACE_LITERAL), 1,
                         f'{CONSOLE.name} must state the six races in one place')
        reads = RACE_READ.findall(CONSOLE_TEXT)
        self.assertEqual(len(reads), 2, f'both race selects of {CONSOLE.name} must read the list')
        copies = race_copies(CONSOLE_TEXT)
        self.assertEqual(copies, [], f'{CONSOLE.name} holds a second copy of the race set: {copies}')

    def test_a_planted_copy_of_either_bound_is_reported(self):
        """The detectors report a second statement of the bound, with its line."""
        planted_field = ('    <input name="rate" type="number" data-vs-field="vod-rate"'
                         ' min="0.25" max="4" step="0.25" value="2">\n')
        self.assertEqual(rate_copies(planted_field),
                         [(1, planted_field.strip())],
                         'a field that states its own bound is a copy')
        self.assertEqual(rate_copies(STAGE_TEXT), [], 'the live stage states no number')
        planted_literal = 'if(rate>8){message(liveText(1))}\n'
        self.assertEqual(rate_literal_copies(planted_literal), [(1, planted_literal.strip())])
        self.assertEqual(rate_literal_copies(CONSOLE_TEXT), [], 'the live console reads the name')
        planted_list = "  ${[1,3,5,7,9,11].map(n=>option(n,n,1)).join('')}\n"
        self.assertEqual(race_copies(planted_list), [(1, planted_list.strip())])
        self.assertEqual(race_copies(CONSOLE_TEXT), [], 'the live console states the set once')
