"""Round 70: the shooter values and the seed role words, each held to one console line.

Two vocabularies of the annotation console stood as bare literals at more sites than they
had owners, and no case named the extra sites.

* **The shooter four.**  The four values of the shooter select - ``''`` (not recorded),
  ``'A'``, ``'B'`` and ``'?'`` (unknown) - stood inline at four sites: the select of the
  annotation form in ``annotator/vision-stage.js``, the option list of
  ``annotator/index.html``, the gate of the annotate route in ``annotator/unified_server.py``
  and the ``CHECK (shooter IN ('A','B','?',''))`` of ``db/migrations/0002_user_data.sql``.
  The console copy had no case: the four values were a literal inside a template string, so
  a value the service accepted could miss the panel, and the panel drew a word the gate
  refused.  The service realm states the tuple once, ``SHOOTER_WORDS``, and the route reads
  it.  The console realm states the four rows once, ``SHOOTER_CHOICES``, and the select
  reads it by name.
* **The seed role words.**  The three legacy role words ``'A'``, ``'B'`` and ``'ignore'``
  stood at six sites: the service constant, ``predictions()`` of the same module, the seed
  form of ``src/pid_seed_rebuild.py``, the ``SEED_ROLE_KEYS`` map of
  ``annotator/vision-stage.js``, the seed button of the same file, and the
  ``CHECK (label IN ('A','B','ignore') OR ...)`` of ``db/migrations/0002_user_data.sql``.
  The parity table of ``tests/test_sql_domain_parity.py`` bound two python sites of the six,
  so a fourth role word added to one copy reached the store of another copy and no case
  reported the disagreement.  Each python site reads ``SEED_ROLES`` now, and the console
  builds its map from its own ``SEED_ROLES`` array.

What this module reads, and what it does not
--------------------------------------------
* It reads the source text of three files of this checkout, with one regex per console line.
  A copy of a rule in a form this module does not match - a value built at run time, a second
  panel - is invisible to it.
* It reads no meaning on the console side.  The rendered option list and the rendered seed
  button are driven in ``tests/test_app_timeline.js``, the case that holds the panel.
* ``tests/test_sql_domain_parity.py`` holds the migration texts to the two service constants,
  and ``tests/test_console_vocabulary.py`` holds the box labels and the verdict words.  This
  module holds the two vocabularies of round 70, and the three write scopes stay apart.
* ``annotator/index.html`` states the four shooter values a third time, for the review form
  of the list page.  That page is not the console of this module, and the round-70 write
  scope does not hold it.  This module reads the annotate route of the service instead, and
  the guard of the list page belongs to a later round.
* The service realm owns the words.  The console is a static file that reads no schema of
  the server, so it holds its own copy on purpose, and this module holds the two copies
  equal in value and in order.

The site anchors of this round, as they stand now:

* ``annotator/vision-stage.js:42`` - ``SHOOTER_CHOICES``, the one console home of the four
* ``annotator/vision-stage.js:1095`` - the select that reads it
* ``annotator/vision-stage.js:344`` - ``SEED_ROLES`` and the map that is built from it
* ``annotator/vision-stage.js:1272`` - the seed button that reads the map
* ``annotator/unified_server.py:102`` - ``SHOOTER_WORDS``, the one service home of the four
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = 'annotator/vision-stage.js'
SERVICE = 'annotator/unified_server.py'
MIGRATION = 'db/migrations/0002_user_data.sql'

CONSOLE_TEXT = (ROOT / CONSOLE).read_text(encoding='utf-8')
SERVICE_TEXT = (ROOT / SERVICE).read_text(encoding='utf-8')
MIGRATION_TEXT = (ROOT / MIGRATION).read_text(encoding='utf-8')

#: The one line of the console that states the four shooter rows.
SHOOTER_HOME = re.compile(r"^const SHOOTER_CHOICES = (\[.*\]);$", re.MULTILINE)
#: The one line of the console that states the three seed role words.
SEED_ROLES_HOME = re.compile(r"^const SEED_ROLES = (\[[^\]]*\]);$", re.MULTILINE)
#: The console map line, the two lines of the service, and the two lines that read a name.
SEED_KEYS_HOME = re.compile(r"^const SEED_ROLE_KEYS = (.*);$", re.MULTILINE)
SERVICE_SEED_HOME = re.compile(r"^SEED_ROLES = \(([^)]*)\)$", re.MULTILINE)
SERVICE_SHOOTER_HOME = re.compile(r"^SHOOTER_WORDS = \(([^)]*)\)$", re.MULTILINE)
SEED_BUTTON_READ = re.compile(
    r'data-vs-action="seed" data-vs-value="\$\{SEED_ROLE_KEYS\.ignore\}"')
#: One option of one select, with the three shapes of an option value in this console: the
#: quoted literal, the empty literal, and the template hole that holds the row value.
OPTION_VALUE = re.compile(r'<option value="([^"]*)"')
#: One data attribute value of one console line.  The pattern stops at the closing quote and
#: at the template hole, so it reads ``ignore`` and reads no template text.
DATA_VALUE = re.compile(r'data-vs-value="([^"$]*)"')
#: The select of the annotation form.
SELECT_HOME = re.compile(
    r'<select data-vs-action="shooter">\$\{SHOOTER_CHOICES\.map\(\(\[v, l\]\) =>')


def line_of(text, index):
    """The 1-based line number of one character index of a text."""
    return text[:index].count('\n') + 1


def line(pattern, text, name):
    """The one line of one file that states a rule, or a failure that names the file."""
    hit = pattern.search(text)
    assert hit is not None, f'{name} must state this rule on one line'
    return hit


def words_of(pattern, text, name):
    """The string values of one parenthesised or bracketed javascript array, in order."""
    body = line(pattern, text, name).group(1)
    found = tuple(re.findall(r"'([^']*)'", body))
    if not found:
        raise AssertionError(f'{name}: no word in {body!r}')
    return found


def rows_of_shooter_home(text=CONSOLE_TEXT):
    """The four rows of the console home: one (value, word key) pair per row."""
    body = line(SHOOTER_HOME, text, CONSOLE).group(1)
    found = tuple(re.findall(r"\['([^']*)',\s*'([^']*)'\]", body))
    if not found:
        raise AssertionError(f'{CONSOLE}: no [value, word] row in {body!r}')
    return found


def console_shooter_value_sites(text=CONSOLE_TEXT):
    """Every console line, outside the home, that states a shooter value as an option value.

    The home line holds the four values on purpose.  The select line writes the value of a
    home row, so its hole holds the name ``v`` and not a literal.  The guest select of the
    panel carries an empty option value too, and the empty string alone is not a finding: the
    four words ``'A'``, ``'B'`` and ``'?'`` and the non-empty spelling of the empty value are
    the findings, with their lines.
    """
    sites = []
    for number, source in enumerate(text.splitlines(), 1):
        if SHOOTER_HOME.match(source):
            continue
        for found in OPTION_VALUE.finditer(source):
            if found.group(1) in ('A', 'B', '?'):
                sites.append((number, found.group(1)))
    return sites


def console_seed_value_sites(text=CONSOLE_TEXT):
    """Every console line, outside the map, that states a seed role word in a data value.

    The map line holds the words as keys of an object, so the pattern below reads no key of
    it.  The seed button and the other readers pass the name ``SEED_ROLE_KEYS``, so their
    value holds no word.  A word in a data value is a finding, with its line.
    """
    sites = []
    for number, source in enumerate(text.splitlines(), 1):
        if SEED_KEYS_HOME.match(source):
            continue
        for found in DATA_VALUE.finditer(source):
            if found.group(1) in ('A', 'B', 'ignore'):
                sites.append((number, found.group(1)))
    return sites


class Round70Vocabulary(unittest.TestCase):
    """The two console vocabularies of round 70, and the service copies they must match."""

    # ---- the shooter four, console side ----------------------------------------------------

    def test_the_shooter_values_stand_once_in_the_console(self):
        """The four values stand on the one home line, and no second console site states one.

        A second site reports its line and its value, so the reader knows what to change.
        """
        self.assertEqual(('', 'A', 'B', '?'),
                         tuple(value for value, _ in rows_of_shooter_home()),
                         f'{CONSOLE}: the home rows must hold the four values, in order')
        self.assertEqual([], console_shooter_value_sites(),
                         f'{CONSOLE}: a line outside the home states a shooter value inline; '
                         'read SHOOTER_CHOICES by name instead')

    def test_the_select_reads_the_shooter_home_by_name(self):
        """The annotation form writes the value of the home row, and keeps the empty value."""
        hit = line(SELECT_HOME, CONSOLE_TEXT, CONSOLE)
        select = hit.group(0)[:hit.group(0).index('${SHOOTER_CHOICES')]
        self.assertIn('data-vs-action="shooter"', select,
                      f'{CONSOLE}: the select of the annotation form must carry the shooter '
                      'action')
        self.assertIn("value=\"${v}\"", CONSOLE_TEXT[hit.start():hit.start() + 250],
                      f'{CONSOLE}: the select must write the value of the home row, not a '
                      'literal')
        self.assertIn("annotation.shooter || ''", CONSOLE_TEXT[hit.start():hit.start() + 250],
                      f'{CONSOLE}: the select must keep the empty string as its not-recorded '
                      'value')

    def test_the_four_values_are_one_set_at_every_site(self):
        """The console home, the service constant and the migration CHECK hold one set.

        The service constant is the owner, and the console home spells the four values in its
        own order: the first option of the panel is the not-recorded value, because that is
        the value of a fresh annotation.  The three sites must hold the same four values.
        """
        values = tuple(value for value, _ in rows_of_shooter_home())
        service = words_of(SERVICE_SHOOTER_HOME, SERVICE_TEXT, SERVICE)
        self.assertEqual(set(service), set(values),
                         f'{SERVICE}: SHOOTER_WORDS and the console home disagree')
        check = re.search(r"CHECK \(shooter IN \(([^)]*)\)\)", MIGRATION_TEXT)
        assert check is not None, f'{MIGRATION} must state a shooter CHECK'
        self.assertEqual(set(service), set(re.findall(r"'([^']*)'", check.group(1))),
                         f'{MIGRATION}: the CHECK and SHOOTER_WORDS disagree')

    def test_the_annotate_route_reads_the_service_constant(self):
        """The gate of the annotate route names the constant, and spells no value inline."""
        hit = SERVICE_TEXT.index('    def _route_annotate')
        route = SERVICE_TEXT[hit:]
        end = route.find('\n    def ', 1)
        route = route if end < 0 else route[:end]
        gate = 'if "shooter" in p and p["shooter"] not in SHOOTER_WORDS:'
        self.assertIn(gate, route,
                      f'{SERVICE}: the annotate route must read SHOOTER_WORDS at its gate')
        self.assertNotIn('not in ("A", "B", "?", "")', route,
                         f'{SERVICE}: the annotate route holds a second literal list of the '
                         'four values')

    # ---- the seed role words, console side -------------------------------------------------

    def test_the_seed_role_words_stand_once_in_the_console(self):
        """The three role words stand on the one home line, and no console site states one.

        The seed button of the panel stated ``'ignore'`` inline until round 70.  It reads the
        map by name now, and this case reports any line that states a word inline again.
        """
        self.assertEqual(('A', 'B', 'ignore'),
                         words_of(SEED_ROLES_HOME, CONSOLE_TEXT, CONSOLE),
                         f'{CONSOLE}: the home array must hold the three role words, in order')
        self.assertEqual([], console_seed_value_sites(),
                         f'{CONSOLE}: a line outside the home states a seed role word inline; '
                         'read SEED_ROLE_KEYS by name instead')

    def test_the_map_is_built_from_the_home_array(self):
        """The seed map reads the home array, one row per word, and the two key forms hold.

        The map states no word of its own: it maps the home array.  The two readers of the
        map, ``isSeedRole`` and ``seedText``, must keep the key of every word, so a fourth
        word added to the home array lands in the map as well.
        """
        home = words_of(SEED_ROLES_HOME, CONSOLE_TEXT, CONSOLE)
        map_line = line(SEED_KEYS_HOME, CONSOLE_TEXT, CONSOLE).group(0)
        self.assertIn('Object.fromEntries(SEED_ROLES.map(', map_line,
                      f'{CONSOLE}: the map must be built from the home array, not spelled by '
                      'hand')
        self.assertIn("role === 'ignore' ? 'ignore' : `seed${role}`", map_line,
                      f'{CONSOLE}: the map must state the two key forms of the console')
        for word in ('A', 'B'):
            self.assertIn(word, home, f'{CONSOLE}: the home array must hold the word {word}')
        for key in ('seedA', 'seedB', 'ignore'):
            self.assertIn(f"'{key}'", CONSOLE_TEXT,
                          f'{CONSOLE}: the copy table must hold the word of the key {key}')
        self.assertIn("t(SEED_ROLE_KEYS[String(value)])", CONSOLE_TEXT,
                      f'{CONSOLE}: the reader must name the map, not a word')

    def test_the_seed_button_reads_the_map_by_name(self):
        """The seed button of the panel holds no role word of its own."""
        self.assertTrue(SEED_BUTTON_READ.search(CONSOLE_TEXT),
                        f'{CONSOLE}: the seed button must read SEED_ROLE_KEYS.ignore')
        self.assertEqual([], console_seed_value_sites(),
                         f'{CONSOLE}: a seed site states a role word inline')

    def test_the_three_words_are_one_set_in_both_realms(self):
        """The console home, the service constant and the migration CHECK hold one set.

        This is the pair that the parity table of ``tests/test_sql_domain_parity.py`` bound
        too loosely: it read two python sites of six, and a fourth word could leave two of
        them behind.  This case reads the console copy and the service owner together.
        """
        console = words_of(SEED_ROLES_HOME, CONSOLE_TEXT, CONSOLE)
        service = words_of(SERVICE_SEED_HOME, SERVICE_TEXT, SERVICE)
        self.assertEqual(service, console,
                         f'{SERVICE}: SEED_ROLES and the console home disagree')
        check = re.search(
            r"CHECK \(label IN \(([^)]*)\) OR length\(label\) BETWEEN 1 AND 60\)", MIGRATION_TEXT)
        assert check is not None, f'{MIGRATION} must state the track_seeds label CHECK'
        self.assertEqual(service, tuple(re.findall(r"'([^']*)'", check.group(1))),
                         f'{MIGRATION}: the label CHECK and SEED_ROLES disagree')

    # ---- the plants ------------------------------------------------------------------------

    def test_a_planted_shooter_list_is_reported(self):
        """A second list of the four values is reported, with the line outside the home.

        The plant writes the list the select held before round 70 into a second option tag of
        the console.  The plant works on the text in memory.  It never touches a file of the
        checkout.
        """
        planted = CONSOLE_TEXT.replace(
            'data-vs-action="shooter">',
            'data-vs-action="shooter"><option value="A">x</option>', 1)
        self.assertNotEqual(CONSOLE_TEXT, planted, 'the plant found the select to change')
        self.assertIn('<option value="A"', planted,
                      'the plant must leave an option value the scan can read')
        sites = console_shooter_value_sites(planted)
        self.assertEqual(['A'], [value for _, value in sites],
                         'the plant must appear as one finding, for the word A')
        self.assertEqual([], console_shooter_value_sites(),
                         'the checkout itself holds no second list of the four values')

    def test_a_planted_seed_word_is_reported(self):
        """A second seed site is reported, with the line and its word.

        The plant restores the inline word the seed button held before round 70.  The plant
        works on the text in memory, and it never touches a file of the checkout.
        """
        planted = CONSOLE_TEXT.replace(
            'data-vs-action="seed" data-vs-value="${SEED_ROLE_KEYS.ignore}"',
            'data-vs-action="seed" data-vs-value="ignore"', 1)
        self.assertNotEqual(CONSOLE_TEXT, planted, 'the plant found the seed button to change')
        sites = console_seed_value_sites(planted)
        self.assertEqual(['ignore'], [value for _, value in sites],
                         'the planted word must appear once, so the scan can report it')
        self.assertEqual([], console_seed_value_sites(),
                         'the checkout itself holds no second seed site')


if __name__ == '__main__':
    unittest.main()
