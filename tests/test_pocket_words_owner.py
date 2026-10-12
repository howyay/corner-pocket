"""One pocket display map has two owners, and this guard holds them equal.

The rule is one map: a stored pocket key -> the English word and the Chinese
word.  Two realms keep it, because a browser cannot read a python name and this
repository has no build step.

``src/dense_queue.py`` holds the python copy in two maps keyed by the stored key:

    POCKET_WORDS      stored key -> the English word (top-left, bottom-right, ...)
    POCKET_WORDS_ZH   stored key -> the Chinese word

``annotator/app.js`` holds the console copy in two steps:

    POCKET_LABELS     stored key -> the displayed word
    POCKET_WORDS      the displayed word -> [english word, chinese word]

A word changed in one realm, or a key added to one realm, moves one half only.
No other case reads the two realms together: the ledger
``docs/console-redesign.md`` spells ``POCKET_WORDS`` 0 times, and
``git grep -c "distance_sentence" -- tests/`` answers 0.

The cases below hold the two copies equal, report the file name and the line of
every difference, and hold the sentence builder to the displayed word of the
owner in both languages.  Do not delete a copy: hold it equal.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
QUEUE = 'src/dense_queue.py'
CONSOLE = 'annotator/app.js'
STAGE = 'annotator/vision-stage.js'

#: Python text: POCKET_WORDS = {"head-left": "top-left", ...}
PY_PAIR = re.compile(r'"([^"]+)"\s*:\s*"([^"]+)"')
#: Javascript text: 'head-left':'top-left'  and  'top-left':['top-left','左上']
JS_ROW = re.compile(r"'([^']+)'\s*:\s*(\[[^\]]*\]|'[^']*')")
#: A string inside one javascript row.
JS_TEXT = re.compile(r"'([^']*)'")


def read(relative):
    """The bytes of a repository file, as text."""
    return (ROOT / relative).read_text(encoding='utf-8')


def py_owner(relative, source):
    """The python half: {stored key: (english word, chinese word, line number)}.

    The two dict literals are read from the text.  This walk is small on
    purpose: another rule owns the shape of the module, and a walk that followed
    an import would fail on a tree without the data of this checkout.
    """
    rows = {}
    for name in ('POCKET_WORDS', 'POCKET_WORDS_ZH'):
        pattern = re.compile(r'\b' + name + r'\s*=\s*\{')
        head = pattern.search(source)
        if head is None:
            raise AssertionError('%s: the owner %s is gone, so no case here can read a word'
                                 % (relative, name))
        body = source[head.end():source.index('}', head.end())]
        rows[name] = [(key, word, source.count('\n', 0, head.end()) + 1 + offset)
                      for offset, (key, word) in enumerate(PY_PAIR.findall(body))]
    keys = [key for key, _, _ in rows['POCKET_WORDS']]
    zh_keys = [key for key, _, _ in rows['POCKET_WORDS_ZH']]
    if keys != zh_keys:
        raise AssertionError('%s: POCKET_WORDS names %r and POCKET_WORDS_ZH names %r, so one '
                             'stored key has one word only' % (relative, keys, zh_keys))
    return {key: (word, zh, line) for (key, word, line), (_, zh, _)
            in zip(rows['POCKET_WORDS'], rows['POCKET_WORDS_ZH'])}


def js_tables(relative, source):
    """The two console tables: {stored key: (shown word, line)} and {shown word: (english, zh, line)}.

    The console builds the same map in two steps.  Each row of the second table
    holds the displayed word twice, so a pair is visible on one line here.
    """
    head = re.search(r'\bPOCKET_LABELS\s*=\s*\{', source)
    if head is None:
        raise AssertionError('%s: the console owner POCKET_LABELS is gone, so no case here can '
                             'read a word' % relative)
    labels = {}
    body = source[head.end():source.index('};', head.end())]
    for number, line in enumerate(body.splitlines(), source.count('\n', 0, head.end()) + 1):
        for key, shown in JS_ROW.findall(line):
            labels[key] = (shown.strip("'"), number)
    table = {}
    words = re.search(r'\bPOCKET_WORDS\s*=\s*\{', source)
    if words is None:
        raise AssertionError('%s: the console owner POCKET_WORDS is gone, so no case here can '
                             'read a word' % relative)
    body = source[words.end():source.index('};', words.end())]
    for number, line in enumerate(body.splitlines(), source.count('\n', 0, words.end()) + 1):
        for shown, row in JS_ROW.findall(line):
            texts = JS_TEXT.findall(row)
            if len(texts) != 2:
                raise AssertionError('%s:%d: the row %r carries %d words, not the pair of one '
                                     'pocket' % (relative, number, line.strip(), len(texts)))
            table[shown] = (texts[0], texts[1], number)
    if not labels or not table:
        raise AssertionError('%s: a console table is empty, so a walk over it reads no word'
                             % relative)
    return labels, table


def js_owner(relative, source):
    """The javascript half: {stored key: (english word, chinese word, line number)}."""
    labels, table = js_tables(relative, source)
    rows = {}
    for key, (shown, label_line) in labels.items():
        if shown not in table:
            raise AssertionError('%s:%d: the stored key %r shows the word %r, and POCKET_WORDS '
                                 'has no row for it' % (relative, label_line, key, shown))
        english, zh, word_line = table[shown]
        rows[key] = (english, zh, word_line)
    return rows


def compare(left, right, left_name, right_name):
    """Every key or word that differs, with the file name and the line.

    ``left`` and ``right`` are {stored key: (english word, chinese word, line)}.
    One report carries the same words in the same order, so two runs answer the
    same text.
    """
    reports = []
    for key in sorted(set(left) | set(right)):
        if key not in left:
            reports.append(('%s:%d' % (right_name, right[key][2]),
                            'the stored key %r is in %s only' % (key, right_name)))
            continue
        if key not in right:
            reports.append(('%s:%d' % (left_name, left[key][2]),
                            'the stored key %r is in %s only' % (key, left_name)))
            continue
        for place, index in (('English', 0), ('Chinese', 1)):
            mine, theirs = left[key][index], right[key][index]
            if mine != theirs:
                reports.append(('%s:%d and %s:%d'
                                % (left_name, left[key][2], right_name, right[key][2]),
                                'the stored key %r has the %s word %r in %s at line %d and '
                                '%r in %s at line %d'
                                % (key, place, mine, left_name, left[key][2],
                                   theirs, right_name, right[key][2])))
    return reports


def both_realms():
    """The two owners of this checkout, and the python source of the module."""
    source = read(QUEUE)
    return py_owner(QUEUE, source), js_owner(CONSOLE, read(CONSOLE)), source


class TheTwoRealmsHoldOneMap(unittest.TestCase):
    """The python copy and the console copy answer the same six pairs."""

    def test_the_effective_maps_are_equal(self):
        python_rows, console_rows, _ = both_realms()
        reports = compare(python_rows, console_rows, QUEUE, CONSOLE)
        self.assertEqual(
            [], reports,
            'the two owners of the pocket words differ, key for key and word for word:\n'
            + '\n'.join('%s: %s' % item for item in reports))

    def test_the_walk_reads_the_words_it_claims(self):
        """A walk that lost a realm passes the case above by reading nothing."""
        python_rows, console_rows, _ = both_realms()
        self.assertGreaterEqual(len(python_rows), 6,
                                'the python copy holds %d pairs: %r'
                                % (len(python_rows), sorted(python_rows)))
        self.assertGreaterEqual(len(console_rows), 6,
                                'the console copy holds %d pairs: %r'
                                % (len(console_rows), sorted(console_rows)))
        for key, (english, zh, _) in sorted(python_rows.items()):
            self.assertTrue(re.fullmatch(r'[a-z]+-[a-z]+', english),
                            '%s: the stored key %r holds the english word %r, and a displayed '
                            'word is not the stored rail term' % (QUEUE, key, english))
            self.assertTrue(zh, '%s: the stored key %r holds no chinese word' % (QUEUE, key))


class TheThirdFileHoldsNoCopy(unittest.TestCase):
    """``annotator/vision-stage.js`` reads the engine; it spells no pair of its own."""

    def test_the_stage_defines_no_pocket_table(self):
        source = read(STAGE)
        for name in ('POCKET_WORDS', 'POCKET_LABELS'):
            self.assertIsNone(
                re.search(r'\b%s\s*=' % name, source),
                '%s declares %s, so this file holds a third copy of the displayed words'
                % (STAGE, name))
        self.assertIn('pocketText', source,
                      '%s names no engine call for a pocket word, so no case can say where its '
                      'words come from' % STAGE)


class TheSentenceCarriesTheShownWord(unittest.TestCase):
    """``distance_sentence`` prints the displayed word, not the stored key."""

    KEY = 'left-side'
    DISTANCE = '124.0'
    UNCERTAINTY = '6.0'
    RADIUS = '42.0'
    VERDICT = 'inside'

    def sentence(self, pocket, verdict, distance=DISTANCE):
        from src.dense_queue import distance_sentence
        return distance_sentence(distance, self.UNCERTAINTY, self.RADIUS, pocket, verdict)

    def test_the_shown_word_of_the_owner_appears_in_both_languages(self):
        python_rows, _, _ = both_realms()
        key = self.KEY
        self.assertIn(key, python_rows, 'the owner must hold the stored key %r' % key)
        english, zh = python_rows[key][:2]
        pair = self.sentence(key, self.VERDICT)
        self.assertIsInstance(pair, tuple,
                              'the builder answers %r, and the operator reads a pair of '
                              'sentences' % type(pair).__name__)
        self.assertEqual(2, len(pair), 'the builder answers %d sentences, not the two '
                                       'languages: %r' % (len(pair), pair))
        sentence, sentence_zh = pair
        self.assertIsInstance(sentence, str,
                              'the english sentence is %r, not text' % type(sentence).__name__)
        self.assertIsInstance(sentence_zh, str,
                              'the chinese sentence is %r, not text' % type(sentence_zh).__name__)
        self.assertIn('from the %s pocket' % english, sentence,
                      'the english sentence %r does not carry the displayed word %r of %s'
                      % (sentence, english, QUEUE))
        self.assertIn(zh, sentence_zh,
                      'the chinese sentence %r does not carry the displayed word %r of %s'
                      % (sentence_zh, zh, QUEUE))
        for text, name in ((sentence, 'english'), (sentence_zh, 'chinese')):
            self.assertNotIn(key, text,
                             'the %s sentence %r prints the stored rail key %r, and the rail '
                             'shows the position word instead' % (name, text, key))

    def test_each_verdict_answers_a_pair_of_sentences(self):
        for verdict in ('inside', 'outside'):
            pair = self.sentence(self.KEY, verdict)
            self.assertEqual(2, len(pair), 'the builder answers %r for the verdict %r'
                             % (pair, verdict))
            self.assertTrue(all(isinstance(part, str) for part in pair),
                            'the builder answers %r for the verdict %r' % (pair, verdict))
        third = self.sentence(self.KEY, 'neither')
        self.assertTrue(all(isinstance(part, str) for part in third),
                        'a verdict outside the two words must answer one honest sentence, and '
                        'it answered %r' % (third,))
        self.assertNotIn('neither', ' '.join(third),
                         'the builder prints the raw verdict %r, and the operator reads a '
                         'sentence: %r' % ('neither', third))

    def test_the_three_arguments_reach_the_sentence(self):
        """The sentence must carry the distance, the error bar and the radius it was given."""
        sentence, sentence_zh = self.sentence(self.KEY, self.VERDICT)
        for part in ('124', '6', '42'):
            self.assertIn(part, sentence,
                          'the english sentence %r does not carry the number %r of its own '
                          'arguments' % (sentence, part))
        self.assertIn('在42', sentence_zh,
                      'the chinese sentence %r does not carry the radius it was given'
                      % (sentence_zh,))

    def test_a_key_the_owner_does_not_hold_stays_verbatim(self):
        pair = self.sentence('pocket-not-in-the-map', self.VERDICT)
        self.assertIn('pocket-not-in-the-map', pair[0],
                      'an unknown key must stay verbatim in the english sentence: %r' % (pair[0],))
        self.assertIn('pocket-not-in-the-map', pair[1],
                      'an unknown key must stay verbatim in the chinese sentence: %r' % (pair[1],))

    def test_no_distance_answers_no_sentence(self):
        self.assertEqual((None, None), self.sentence(self.KEY, self.VERDICT, distance=None),
                         'a distance of None must answer two Nones, so no reader prints a '
                         'sentence about a ball nothing measured')


class AChangedWordIsReported(unittest.TestCase):
    """A planted difference is reported with the stored key, the file and the line."""

    def planted(self, old, new):
        source = read(CONSOLE)
        self.assertEqual(1, source.count(old),
                         'the planted text %r occurs %d times in %s, and the planting needs one '
                         'site' % (old, source.count(old), CONSOLE))
        text = source.replace(old, new)
        self.assertNotEqual(source, text, 'the planting changed nothing')
        return text

    def test_a_changed_english_word_is_reported(self):
        python_rows, _, _ = both_realms()
        key = 'foot-right'
        english = python_rows[key][0]
        planted = self.planted("'%s':['%s'," % (english, english),
                               "'%s':['%s-x'," % (english, english))
        reports = compare(python_rows, js_owner(CONSOLE, planted),
                          QUEUE, CONSOLE)
        self.assertEqual(1, len(reports),
                         'a planted english word gave %d reports: %r' % (len(reports), reports))
        place, why = reports[0]
        self.assertIn(key, why, 'the report does not name the stored key: %r' % (why,))
        self.assertIn(CONSOLE, place, 'the report does not name the file: %r' % (place,))
        self.assertIn('English', why, 'the report does not name the language: %r' % (why,))

    def test_a_changed_chinese_word_is_reported(self):
        python_rows, _, _ = both_realms()
        key = 'head-left'
        zh = python_rows[key][1]
        planted = self.planted("'%s']" % zh, "'%s-x']" % zh)
        reports = compare(python_rows, js_owner(CONSOLE, planted),
                          QUEUE, CONSOLE)
        self.assertEqual(1, len(reports),
                         'a planted chinese word gave %d reports: %r' % (len(reports), reports))
        place, why = reports[0]
        self.assertIn(key, why, 'the report does not name the stored key: %r' % (why,))
        self.assertIn(CONSOLE, place, 'the report does not name the file: %r' % (place,))
        self.assertIn('Chinese', why, 'the report does not name the language: %r' % (why,))

    def test_a_python_word_of_another_spelling_is_reported(self):
        """The walk reads the python owner too, not only the console copy."""
        python_rows, console_rows, source = both_realms()
        key = 'right-side'
        english = python_rows[key][0]
        head = source.index('POCKET_WORDS = {')
        tail = source.index('}', head)
        planted = (source[:head]
                   + source[head:tail].replace('"%s"' % english, '"%s-x"' % english, 1)
                   + source[tail:])
        reports = compare(py_owner(QUEUE, planted), console_rows, QUEUE, CONSOLE)
        self.assertEqual(1, len(reports),
                         'a planted python word gave %d reports: %r' % (len(reports), reports))
        place, why = reports[0]
        self.assertIn(key, why, 'the report does not name the stored key: %r' % (why,))
        self.assertIn(CONSOLE, place, 'the report does not name the file: %r' % (place,))


if __name__ == '__main__':
    unittest.main()
