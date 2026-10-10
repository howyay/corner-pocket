"""Parity test for the Twitch source URL rule; python -m unittest discover -s tests."""
import json
from pathlib import Path
import unittest

from annotator.operations import TWITCH_RESERVED_CHANNELS, parse_twitch_source_url

CORPUS = Path(__file__).with_name('source_url_cases.json')
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


if __name__ == '__main__':
    unittest.main()
