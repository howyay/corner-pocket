"""Parity test for the Twitch source URL rule; python -m unittest discover -s tests."""
import json
import re
from pathlib import Path
import unittest

from annotator.operations import TWITCH_RESERVED_CHANNELS, parse_twitch_source_url

CORPUS = Path(__file__).with_name('source_url_cases.json')
CONSOLE = Path(__file__).resolve().parents[1] / 'annotator' / 'ops.js'
# The console's copy of the reserved-channel list, as annotator/ops.js writes it.
CONSOLE_TUPLE = re.compile(r'^const TWITCH_RESERVED_CHANNELS=\[([^\]]*)\];$', re.MULTILINE)
CONSOLE_WORD = re.compile(r"'([^']*)'")
# The channel login rule of the console, as annotator/ops.js writes it: one alphabet, one ceiling.
# The console cannot import the python name TWITCH_LOGIN of annotator/twitch_source.py, so it holds
# a copy of the shape. tests/test_console_service_bounds.py holds the ceiling of that copy.
CONSOLE_LOGIN = re.compile(r'const channel=/\^\\/\(\[([A-Za-z0-9_-]+)\]\{1,(\d+)\}\)\$')
# The six URL shapes that the console and the service read in different ways before the repair.
# Four shapes show a console that was too free: the dot segments, the port 443 and the upper case
# host. Two shapes show a console that was too strict: the double trailing slash on a channel and
# on a video. The old console rule used new URL, and that function rewrites all of these shapes.
OLD_DISAGREEMENTS = ('https://www.twitch.tv/./examplechannel',
                     'https://www.twitch.tv/a/../examplechannel',
                     'https://www.twitch.tv:443/examplechannel',
                     'https://WWW.TWITCH.TV/examplechannel',
                     'https://www.twitch.tv/examplechannel//',
                     'https://www.twitch.tv/videos/123//')


class SourceUrlParityTests(unittest.TestCase):
    """Drive the service rule over the corpus in tests/source_url_cases.json.

    The service rule is the reference for the URL shape. The repair changed the console rule
    only, because the console rule used new URL, and that function rewrites the host case, the
    default port 443 and the dot segments. The service reads the URL as the operator typed it.
    No corpus row made the service rule change, so this file keeps the shape rule that
    annotator/operations.py had. The test imports the named rule function, so the test holds no
    second copy of the rule. tests/test_ops.js reads the same corpus for the console rule.
    """

    def rows(self):
        with CORPUS.open(encoding='utf-8') as handle:
            return json.load(handle)['rows']

    def test_the_corpus_is_large_and_holds_the_measured_cases(self):
        rows = self.rows()
        self.assertGreaterEqual(len(rows), 30)
        urls = [row['url'] for row in rows]
        self.assertEqual(len(set(urls)), len(urls), 'the corpus holds one row for each URL')
        for url in OLD_DISAGREEMENTS:
            self.assertIn(url, urls, 'the corpus holds every measured disagreement')
        for word in TWITCH_RESERVED_CHANNELS:
            self.assertIn('https://www.twitch.tv/' + word, urls, 'the corpus holds every reserved word')
        self.assertTrue(any(row['verdict'] == 'accept' for row in rows))
        self.assertTrue(any(row['verdict'] == 'refuse' for row in rows))

    def test_every_row_names_its_verdict_and_its_reason(self):
        for row in self.rows():
            with self.subTest(url=row['url']):
                self.assertIn(row['verdict'], ('accept', 'refuse'))
                self.assertTrue(row['reason'].strip(), 'the row explains the verdict')
                if row['verdict'] == 'accept':
                    self.assertTrue(row['canonical'].startswith('https://www.twitch.tv/'))
                    self.assertTrue(row['subject'])
                else:
                    self.assertIsNone(row['canonical'])
                    self.assertIsNone(row['subject'])

    def test_the_service_rule_matches_every_corpus_row(self):
        for row in self.rows():
            with self.subTest(url=row['url']):
                if row['verdict'] == 'refuse':
                    with self.assertRaises(ValueError):
                        parse_twitch_source_url(row['url'])
                    continue
                source = parse_twitch_source_url(row['url'])
                self.assertEqual(source['url'], row['canonical'])
                if source['kind'] == 'video':
                    self.assertEqual(source['video'], row['subject'])
                    self.assertEqual(source['url'], 'https://www.twitch.tv/videos/' + row['subject'])
                else:
                    self.assertEqual(source['channel'], row['subject'])
                    self.assertEqual(source['url'], 'https://www.twitch.tv/' + row['subject'])


    def test_the_console_holds_the_same_reserved_words(self):
        source = CONSOLE.read_text(encoding='utf-8')
        match = CONSOLE_TUPLE.search(source)
        self.assertIsNotNone(match, 'annotator/ops.js holds no TWITCH_RESERVED_CHANNELS array')
        words = CONSOLE_WORD.findall(match.group(1))
        self.assertEqual(words, list(TWITCH_RESERVED_CHANNELS),
                         'annotator/ops.js holds a different reserved-channel list from '
                         'annotator/operations.py: the service refuses a channel that the '
                         'console accepts when a word is missing, and the console refuses a '
                         'real channel when a word is extra')
        self.assertEqual(len(set(words)), len(words), 'the console list holds a word twice')

    def test_the_console_spells_the_reserved_words_once(self):
        source = CONSOLE.read_text(encoding='utf-8')
        wanted = set(TWITCH_RESERVED_CHANNELS)
        sites = [number for number, line in enumerate(source.splitlines(), 1)
                 if len(wanted & set(CONSOLE_WORD.findall(line))) > 1]
        self.assertEqual(1, len(sites),
                         'annotator/ops.js must spell the reserved words once, in one array; '
                         'found these lines with two or more of them: %s' % (sites,))
        self.assertIn("!TWITCH_RESERVED_CHANNELS.includes(", source,
                      'parseSource must read the one array; a typed list would drift again')

    def test_the_console_reads_the_login_of_a_url(self):
        """The console states the login once, reads both cases, and lowers it for its URL."""
        source = CONSOLE.read_text(encoding='utf-8')
        hits = CONSOLE_LOGIN.findall(source)
        self.assertEqual(1, len(hits),
                         'annotator/ops.js must state the channel login once; found: %s' % (hits,))
        alphabet, ceiling = hits[0]
        self.assertEqual('A-Za-z0-9_', alphabet,
                         'parseSource must read the login as the operator typed it: a URL holds both '
                         'cases, and the service rule reads the same shape with re.IGNORECASE and '
                         're.ASCII')
        self.assertTrue(ceiling.isdigit(), 'parseSource must end the login at a fixed ceiling')
        self.assertIn('channel[1].toLowerCase()', source,
                      'parseSource must lower the login of the channel it returns and of its '
                      'canonical URL, the way annotator/operations.py does')
        # The corpus row for this URL is an accept row: the service lowers the login too.
        served = parse_twitch_source_url('https://www.twitch.tv/ExampleChannel')
        self.assertEqual(served['channel'], 'examplechannel',
                         'the service rule must lower the login of that URL')
        self.assertEqual(served['url'], 'https://www.twitch.tv/examplechannel',
                         'the console and the service must agree on the canonical URL of a login '
                         'that holds an upper case letter')


if __name__ == '__main__':
    unittest.main()
