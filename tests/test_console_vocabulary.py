"""One guard for the two console vocabularies that the service also holds.

annotator/app.js owns the words of a box label and the words of a cue verdict. It builds the
object VOCABULARY and publishes it on window.CornerPocketReview.vocabulary. Three other sites
must spell the same words: the service validator in annotator/unified_server.py, the verdict
CHECK of db/migrations/0002_user_data.sql, and the three review buttons of annotator/index.html.
annotator/vision-stage.js owns no list: it reads the owner at its former literal sites.

The earlier defect: a word that one site added and another site did not have reached the
operator as a refusal. A second defect of the same shape: the two lists could leave a word out
silently, because no test compared them.

Every case reads the files of this checkout. A disagreement reports the site and the word, so
the reader knows what to change. The last case plants a fourth word in one site and proves that
this guard reports it.
"""

import re
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The two vocabularies, in the order that the owner spells them. The order is part of the
#: contract: annotator/index.html writes the three verdict buttons in it, and the marker layer
#: and the console paint the box menu in it.
BOX_LABEL_WORDS = ('person', 'ball', 'cue', 'solid', 'stripe', 'eight')
VERDICT_WORDS = ('correct', 'wrong', 'unsure')

OWNER = 'annotator/app.js'
JS_SITE = 'annotator/vision-stage.js'
HTML_SITE = 'annotator/index.html'
PY_SITE = 'annotator/unified_server.py'
SQL_SITE = 'db/migrations/0002_user_data.sql'
PARITY_SITE = 'tests/test_sql_domain_parity.py'

#: The files that this guard reads, and no others. A copy that lives outside this list is a
#: finding, not a silent pass: case 4 walks this list for a literal list of the same words.
GUARDED_FILES = (OWNER, JS_SITE, HTML_SITE, PY_SITE, SQL_SITE, PARITY_SITE)


# ---- the sites: one reader each, so a break names its file -------------------------------------

@dataclass(frozen=True)
class Words:
    """One list of words as one site spells it, with the line that holds it."""

    site: str
    line: int
    words: tuple


def _lines(site):
    return (ROOT / site).read_text(encoding='utf-8').splitlines()


def _line_of(text, index):
    return text[:index].count('\n') + 1


def _owner_words():
    """Read the two lists the owner builds, with the line each list starts on."""
    text = '\n'.join(_lines(OWNER))
    found = {}
    for name in ('boxLabels', 'verdictWords'):
        # The owner freezes each array, so the words sit inside a call: Object.freeze([...]).
        # The pattern reads the inner bracket pair, with or without the freeze call.
        match = re.search(r"%s\s*:\s*(?:[A-Za-z.]+\()?\[([^\]]*)\]" % name, text)
        if not match:
            raise AssertionError(f'{OWNER}: no array literal named {name}')
        found[name] = Words(OWNER, _line_of(text, match.start()),
                            tuple(re.findall(r"'([^']*)'", match.group(1))))
    return found


def python_words_from(text):
    """Read BOX_LABELS and VERDICT_WORDS from the text of the service module."""
    found = []
    for name in ('BOX_LABELS', 'VERDICT_WORDS'):
        match = re.search(r"^%s\s*=\s*\(([^)]*)\)" % name, text, re.M)
        if not match:
            raise AssertionError(f'{PY_SITE}: no module constant named {name}')
        found.append(Words(PY_SITE, _line_of(text, match.start()),
                           tuple(re.findall(r"'([^']*)'", match.group(1)))))
    return tuple(found)


def sql_words_from(text):
    """Read the verdict CHECK from the text of the migration, the way SQLite spells it."""
    match = re.search(r"verdict\s+text\s+CHECK\s*\(\s*verdict\s+IN\s*\(([^)]*)\)", text)
    if not match:
        raise AssertionError(f'{SQL_SITE}: no verdict CHECK constraint')
    return Words(SQL_SITE, _line_of(text, match.start()),
                 tuple(re.findall(r"'([^']*)'", match.group(1))))


def html_verdict_buttons_from(text):
    """Read the three review buttons of the list page, in document order."""
    seen = [(text[:m.start()].count('\n') + 1, m.group(1))
            for m in re.finditer(r'data-v="([^"]+)"', text)]
    if not seen:
        raise AssertionError(f'{HTML_SITE}: no button carries data-v')
    return Words(HTML_SITE, seen[0][0], tuple(value for _, value in seen))


# ---- the checks: one comparison each, so a failure names its site and its word -----------------

def compare(name, expected, words):
    """Every word of the owner is in this site, in the owner's order. Report each difference.

    The return value is a list of plain sentences. The case shows the list on failure, and the
    planted-word case reads the same list as the finding.
    """
    found = []
    if len(words.words) != len(expected):
        found.append(f'{words.site}:{words.line}: {len(words.words)} words, the owner has '
                     f'{len(expected)}')
    for word in expected:
        if word not in words.words:
            found.append(f'{words.site}:{words.line}: the word {word!r} of {name} is missing')
    if not found and words.words != tuple(expected):
        found.append(f'{words.site}:{words.line}: the order is {list(words.words)}, the owner '
                     f'writes {list(expected)}')
    return found


def vocabulary_disagreements(override=None):
    """Check every other site against the owner. Return one sentence per disagreement.

    An override is ``(site, text)``. It replaces the text of that site, so this function is the
    one path that the planted-word case drives against a source that holds a fourth word.
    """
    def text_of(site):
        if override and override[0] == site:
            return override[1]
        return (ROOT / site).read_text(encoding='utf-8')

    owner = _owner_words()
    box_words, verdict_words = python_words_from(text_of(PY_SITE))
    found = []
    found += compare('boxLabels', owner['boxLabels'].words, box_words)
    found += compare('verdictWords', owner['verdictWords'].words, verdict_words)
    found += compare('verdictWords', owner['verdictWords'].words, sql_words_from(text_of(SQL_SITE)))
    found += compare('verdictWords', owner['verdictWords'].words,
                     html_verdict_buttons_from(text_of(HTML_SITE)))
    return found


#: The owner's two reads, by name and line. annotator/vision-stage.js owns no list: it asks the
#: owner at each site that used to hold a literal. The three literals were held by boxBlock (the
#: two label selects) and by the two verdict button rows.
READ_SITES = (
    ('annotator/vision-stage.js', 40, 'const boxLabels = () => window.CornerPocketReview.vocabulary.boxLabels;'),
    ('annotator/vision-stage.js', 41, 'const verdictWords = () => window.CornerPocketReview.vocabulary.verdictWords;'),
)


class ConsoleVocabulary(unittest.TestCase):

    def test_the_owner_holds_both_vocabularies(self):
        owner = _owner_words()
        self.assertEqual(owner['boxLabels'].words, BOX_LABEL_WORDS)
        self.assertEqual(owner['verdictWords'].words, VERDICT_WORDS)

    def test_every_other_site_holds_the_owner_words(self):
        found = vocabulary_disagreements()
        self.assertEqual(found, [], 'the vocabulary left the owner:\n' + '\n'.join(found))

    def test_the_service_names_one_constant_per_vocabulary(self):
        box, verdict = python_words_from((ROOT / PY_SITE).read_text(encoding='utf-8'))
        self.assertEqual(box.words, BOX_LABEL_WORDS)
        self.assertEqual(verdict.words, VERDICT_WORDS)

    def test_the_console_reads_the_owner_at_each_former_literal(self):
        for site, number, expected in READ_SITES:
            line = _lines(site)[number - 1].strip()
            self.assertEqual(line, expected,
                             f'{site}:{number} must read the owner, not a literal of its own')
        source = '\n'.join(_lines(JS_SITE))
        self.assertEqual(len(re.findall(r'window\.CornerPocketReview\.vocabulary\.', source)), 2,
                         'the adapter reads the owner at its two reads and nowhere else')

    def test_the_sql_pair_binds_the_migration_to_the_service_constant(self):
        parity = '\n'.join(_lines(PARITY_SITE))
        self.assertIn('VERDICT_WORDS', parity,
                      f'{PARITY_SITE}: the event_verdicts pair must read the service constant')

    def test_a_planted_fourth_word_is_reported(self):
        # The one path that the guard reads is vocabulary_disagreements(), so each plant drives
        # that function. A plant changes one site and leaves every other site alone.
        python_plant = re.sub(r"^VERDICT_WORDS\s*=\s*\([^)]*\)",
                              "VERDICT_WORDS = ('correct', 'wrong', 'unsure', 'maybe')",
                              (ROOT / PY_SITE).read_text(encoding='utf-8'), count=1, flags=re.M)
        self.assertIn("'maybe'", python_plant,
                      f'{PY_SITE}: the plant found no VERDICT_WORDS line to change')
        found = vocabulary_disagreements(override=(PY_SITE, python_plant))
        # A plant adds a word, so it changes the length of the list. The reader of the site
        # sees the count, and the sentence names the site and the two counts.
        self.assertTrue(any(sentence.startswith(f'{PY_SITE}:') and '4 words' in sentence
                            for sentence in found),
                        f'the guard did not report the planted word at {PY_SITE}: {found}')

        html_plant, count = re.subn(r'(data-v="correct")', r'\1 data-v="maybe"',
                                    (ROOT / HTML_SITE).read_text(encoding='utf-8'), count=1)
        self.assertEqual(count, 1, f'{HTML_SITE}: the plant found no correct button to change')
        found = vocabulary_disagreements(override=(HTML_SITE, html_plant))
        self.assertTrue(any(sentence.startswith(f'{HTML_SITE}:') and '4 words' in sentence
                            for sentence in found),
                        f'the guard did not report the planted button at {HTML_SITE}: {found}')

    def test_no_other_literal_list_of_these_words_lives_in_the_guarded_files(self):
        # One run of the owner's words, quoted and next to each other in one line, is a copy of
        # a vocabulary. The owner holds the two lists, and both are named where the reader sees
        # them, so this case walks the other five files: the adapter, the list page, the service
        # module, the migration and the sql parity module. It reads no other file.
        owner = _owner_words()
        patterns = [(name, re.compile(r'[^\'"\n]{2,}'.join(re.escape(word) for word in words.words)))
                    for name, words in owner.items()]
        for site in GUARDED_FILES:
            if site == OWNER:
                continue
            for number, line in enumerate(_lines(site), 1):
                for name, pattern in patterns:
                    if pattern.search(line):
                        self.fail(f'{site}:{number} holds a second copy of the {name} list: '
                                  f'{line.strip()}')


if __name__ == '__main__':
    unittest.main()
