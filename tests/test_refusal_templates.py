"""The template table: the refusals whose facts are only known at run time.

``annotator/refusals.py`` holds two tables.  ``REFUSALS`` maps a fixed sentence to its code and
its Chinese sentence.  ``TEMPLATES`` does the same for a sentence whose facts arrive with the
call: a field name, a range, an exit code.  The operator then receives a code and a Chinese
sentence there as well, and the console reads the values as data instead of parsing the text.

Every English render below is compared with the sentence the tree printed before the table
existed.  Two sites build such a sentence, and this module drives both of them: the validators of
``annotator/operations.py``, and the import job of ``annotator/vod_import.py``.
"""
import string
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from annotator import refusals
from annotator.operations import instant, integer, seconds, text
from annotator.refusals import (FFMPEG_FAILED, INSTANT, INTEGER_RANGE, SCAN_CHANNEL, TEMPLATES,
                                TEXT_LENGTH, TemplateError, WHOLE_SECONDS, filled_refusal)
from annotator.unified_server import APIError, Backend, refusal_body
from annotator.vod_import import VodImporter

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / 'annotator/operations.py'
VOD_IMPORT = ROOT / 'annotator/vod_import.py'

VOD_ID = '1000000001'
CHANNEL = 'brokenchannel'
CHANNEL_ERROR = 'Twitch API request failed (HTTP 500)'
FFMPEG_DETAIL = 'Server returned 403 Forbidden'

# One routed sentence per case: the skeleton, the facts of the call, and the English the tree
# printed before the table.  The values are the ones the rest of the suite pins
# (tests/test_operations.py and tests/test_vod_import.py name the same sentences).
CASES = (
    (INTEGER_RANGE, {'name': 'rating', 'low': 0, 'high': 1000},
     'rating must be an integer from 0 to 1000'),
    (INTEGER_RANGE, {'name': 'side', 'low': 0, 'high': 1},
     'side must be an integer from 0 to 1'),
    (INTEGER_RANGE, {'name': 'tables', 'low': 1, 'high': 32},
     'tables must be an integer from 1 to 32'),
    (TEXT_LENGTH, {'name': 'note', 'maximum': 4000}, 'note must contain 1\u20134000 characters'),
    (TEXT_LENGTH, {'name': 'name', 'maximum': 200}, 'name must contain 1\u2013200 characters'),
    (WHOLE_SECONDS, {'name': 'startS'}, 'startS must be a whole number of seconds, 0 or more'),
    (WHOLE_SECONDS, {'name': 'clip start'},
     'clip start must be a whole number of seconds, 0 or more'),
    (INSTANT, {'name': 'startedAt'}, 'startedAt must be an ISO-8601 instant'),
    (FFMPEG_FAILED, {'exit_code': 1, 'detail': FFMPEG_DETAIL},
     'ffmpeg stopped (exit 1): Server returned 403 Forbidden. The partial file was removed.'),
    (SCAN_CHANNEL, {'channel': CHANNEL, 'message': CHANNEL_ERROR},
     'brokenchannel: Twitch API request failed (HTTP 500)'),
)

# The five raise sites of the four validators, one call each, with the sentence the suite pins.
VALIDATOR_REFUSALS = (
    (INTEGER_RANGE, lambda: integer('7', 0, 10, 'rating'),
     'rating must be an integer from 0 to 10', {'name': 'rating', 'low': 0, 'high': 10}),
    (TEXT_LENGTH, lambda: text('', 'name'), 'name must contain 1\u2013200 characters',
     {'name': 'name', 'maximum': 200}),
    (WHOLE_SECONDS, lambda: seconds(True, 'startS'),
     'startS must be a whole number of seconds, 0 or more', {'name': 'startS'}),
    (INSTANT, lambda: instant('', 'startedAt'), 'startedAt must be an ISO-8601 instant',
     {'name': 'startedAt'}),
    (INSTANT, lambda: instant('yesterday', 'startedAt'), 'startedAt must be an ISO-8601 instant',
     {'name': 'startedAt'}),
)

CJK = r'[\u4e00-\u9fff]'


def slots(text_value):
    """The placeholder names of one skeleton, in the order the sentence states them."""
    return [name for _, name, _, _ in string.Formatter().parse(text_value) if name]


class TemplateTableTests(unittest.TestCase):
    """The table itself: one row per rule, both languages, no collision with REFUSALS."""

    def test_every_template_row_names_a_code_and_fills_from_its_facts(self):
        for skeleton, row in TEMPLATES.items():
            with self.subTest(code=row.code):
                self.assertRegex(row.code, r'^[a-z][a-z0-9_]*$')
                self.assertEqual(row.en, skeleton)
                self.assertNotEqual(row.en, row.zh)
                self.assertRegex(row.zh, CJK)
                self.assertEqual(slots(row.en), slots(row.zh),
                                 'both languages must state the facts in the same order')
                self.assertEqual(list(row.fields), slots(row.en),
                                 'the fact names must be the placeholders of the skeleton')
                facts = {name: (index + 1 if name.endswith('_bytes') else f'{name}_value')
                         for index, name in enumerate(row.fields)}
                sentence, identity = filled_refusal(skeleton, **facts)
                self.assertEqual(sentence, row.en.format(**facts))
                self.assertNotIn('{', sentence)          # a placeholder must never reach the text
                self.assertNotIn('{', identity['zh'])
                self.assertEqual(identity['code'], row.code)
                self.assertEqual(identity['zh'], row.zh.format(**facts))
                for name, value in facts.items():
                    self.assertEqual(identity[name], value, 'the identity must name every fact')

    def test_every_routed_sentence_keeps_the_english_the_tree_printed(self):
        for skeleton, facts, expected in CASES:
            with self.subTest(skeleton=skeleton, expected=expected):
                sentence, identity = filled_refusal(skeleton, **facts)
                self.assertEqual(sentence, expected)
                self.assertEqual(sentence.encode('utf-8'), expected.encode('utf-8'),
                                 'the English must equal the old literal byte for byte')
                self.assertEqual(identity['code'], TEMPLATES[skeleton].code)
                self.assertEqual(identity['zh'], TEMPLATES[skeleton].zh.format(**facts))
                self.assertRegex(identity['zh'], CJK)

    def test_the_text_length_sentence_keeps_the_dash_of_the_old_literal(self):
        sentence, _ = filled_refusal(TEXT_LENGTH, name='note', maximum=4000)
        self.assertEqual(sentence, 'note must contain 1\u20134000 characters')
        self.assertEqual(sentence.encode('utf-8'), b'note must contain 1\xe2\x80\x934000 characters',
                         'U+2013 is three bytes; a hyphen would read as one')

    def test_no_template_row_collides_with_the_static_table(self):
        static_codes = {row.code for row in refusals.REFUSALS.values()}
        self.assertEqual(set(), {row.code for row in TEMPLATES.values()} & static_codes)
        self.assertEqual(set(), set(TEMPLATES) & set(refusals.REFUSALS),
                         'a skeleton must never be a key of the static table')

    def test_no_template_row_names_a_key_the_body_already_owns(self):
        for row in TEMPLATES.values():
            with self.subTest(code=row.code):
                for owned in ('error', refusals.CODE_KEY, refusals.ZH_KEY):
                    self.assertNotIn(owned, row.fields,
                                     'a fact must not overwrite the key the body owns')


class ValidatorRefusalTests(unittest.TestCase):
    """The validators of annotator/operations.py: the sentence, the code, the Chinese."""

    def test_each_validator_refuses_with_the_sentence_the_code_and_the_facts(self):
        for skeleton, call, expected, facts in VALIDATOR_REFUSALS:
            with self.subTest(expected=expected):
                with self.assertRaises(TemplateError) as caught:
                    call()
                refusal = caught.exception
                self.assertIsInstance(refusal, ValueError)
                self.assertEqual(str(refusal), expected)
                self.assertEqual(refusal.fields['code'], TEMPLATES[skeleton].code)
                self.assertEqual(refusal.fields['zh'], TEMPLATES[skeleton].zh.format(**facts))
                self.assertRegex(refusal.fields['zh'], CJK)
                for name, value in facts.items():
                    self.assertEqual(refusal.fields[name], value)

    def test_the_instant_refusal_keeps_the_parse_error_as_its_cause(self):
        with self.assertRaises(TemplateError) as caught:
            instant('yesterday', 'startedAt')
        self.assertIsInstance(caught.exception.__cause__, ValueError)

    def test_the_route_body_publishes_the_identity_of_a_template_refusal(self):
        with self.assertRaises(TemplateError) as caught:
            integer('7', 0, 10, 'rating')
        refusal = caught.exception
        body = refusal_body(refusal, getattr(refusal, 'fields', {}))
        self.assertEqual(body['error'], 'rating must be an integer from 0 to 10')
        self.assertEqual((body['code'], body['name'], body['low'], body['high']),
                         ('operation_integer_range', 'rating', 0, 10))
        self.assertEqual(body['zh'],
                         TEMPLATES[INTEGER_RANGE].zh.format(name='rating', low=0, high=10))

    def test_a_plain_value_error_still_carries_its_sentence_only(self):
        sentence = 'rating must be an integer from 0 to 1000'
        self.assertEqual(refusal_body(ValueError(sentence), {}), {'error': sentence})


class OperationsRouteTests(unittest.TestCase):
    """The operations route: the fields of a validator refusal survive the wrap.

    ``Backend._route_operations`` turns the ValueError of a writer into an APIError.  The
    identity must travel with it, or the console receives the English sentence alone.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / 'annotator').mkdir()
        (root / 'annotator' / 'ops.html').write_text('<!doctype html><title>fixture</title>')
        (root / 'annotator' / 'ops.js').write_text('void 0;')
        (root / 'data').mkdir()
        self.backend = Backend(root)

    def test_a_validator_refusal_keeps_its_identity_through_the_operations_route(self):
        payload = {'action': 'player_save', 'revision': self.backend.operations().get()['revision'],
                   'name': 'probe', 'rating': 'high'}
        with self.assertRaises(APIError) as caught:
            self.backend._route_operations(payload)
        refusal = caught.exception
        self.assertEqual(str(refusal), 'rating must be an integer from 0 to 1000')
        self.assertEqual(refusal.status, 400)
        self.assertEqual((refusal.fields['code'], refusal.fields['name']),
                         ('operation_integer_range', 'rating'))
        body = refusal_body(refusal, getattr(refusal, 'fields', {}))
        self.assertEqual((body['error'], body['code'], body['low'], body['high']),
                         ('rating must be an integer from 0 to 1000', 'operation_integer_range',
                          0, 1000))
        self.assertEqual(body['zh'],
                         TEMPLATES[INTEGER_RANGE].zh.format(name='rating', low=0, high=1000))


class RoutedSiteTests(unittest.TestCase):
    """No routed site builds its sentence with an f-string any more."""

    def test_the_validators_build_every_sentence_from_the_table(self):
        source = OPERATIONS.read_text(encoding='utf-8')
        for skeleton_name in ('INTEGER_RANGE', 'TEXT_LENGTH', 'WHOLE_SECONDS', 'INSTANT'):
            with self.subTest(skeleton=skeleton_name):
                self.assertIn(f'raise TemplateError({skeleton_name}', source)
        for gone in ("f'{name} must be an integer from", "f'{name} must contain 1",
                     "f'{name} must be a whole number of seconds",
                     "f'{name} must be an ISO-8601 instant'"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, source)

    def test_the_import_job_builds_both_sentences_from_the_table(self):
        source = VOD_IMPORT.read_text(encoding='utf-8')
        self.assertIn('filled_refusal(FFMPEG_FAILED, exit_code=code, detail=detail)', source)
        self.assertIn('filled_refusal(SCAN_CHANNEL, channel=channel, message=error)', source)
        self.assertNotIn('f"ffmpeg stopped (exit {code})', source)
        self.assertNotIn('f"{channel}: {error}"', source)


FFMPEG_FAIL = ("import sys\n"
               "sys.stderr.write('Server returned 403 Forbidden\\n')\n"
               "sys.stderr.flush()\n"
               "sys.exit(1)\n")


class FakeTwitch:
    """The three Twitch calls of one import, with no network and no signature."""

    TwitchVodError = RuntimeError

    def vod_id_of(self, value):
        return str(value).strip().rstrip('/').split('/')[-1].lstrip('v')

    def vod_info(self, vod_id):
        return {'id': vod_id, 'channel': 'examplechannel', 'title': '260918', 'length_s': 13397,
                'created_at': '2026-09-26T06:46:33Z'}

    def resolve_vod(self, vod_id):
        return {'vod_id': vod_id, 'media_url': 'https://example.invalid/stream.m3u8',
                'signature': 'SIG', 'value': 'TOKEN',
                'variant': {'height': 720, 'bandwidth': 3_000_000, 'fps': 30.0, 'url': None}}


class JobRecordTests(unittest.TestCase):
    """The import job: the identity of a refusal reaches the record beside the sentence."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.script = self.root / 'ffmpeg_fails.py'
        self.script.write_text(FFMPEG_FAIL, encoding='utf-8')
        self.sources = [{'id': 's1', 'kind': 'channel', 'channel': 'examplechannel',
                         'url': 'https://www.twitch.tv/examplechannel'}]

    def importer(self, sources=None):
        """An importer whose ffmpeg is a script that prints one line and stops with exit 1."""
        chosen = self.sources if sources is None else sources
        return VodImporter(
            self.root, lambda: {'sources': chosen}, twitch=FakeTwitch(),
            ffmpeg=lambda: [sys.executable, str(self.script)],
            probe=lambda path: {'fps': 30.0, 'frames': 9000, 'width': 1280, 'height': 720},
            disk_usage=lambda path: SimpleNamespace(free=10 ** 12))

    def wait(self, importer, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = importer.job()
            if job.get('state') != 'running':
                return job
            time.sleep(0.02)
        self.fail(f'the job did not finish: {importer.job()}')

    def test_the_ffmpeg_failure_names_its_code_and_its_exit_code_beside_the_sentence(self):
        importer = self.importer()
        importer.start({'vod': VOD_ID, 'start_s': 0, 'duration_s': 60})
        job = self.wait(importer)
        self.assertEqual(job['state'], 'error')
        self.assertEqual(job['error'], 'ffmpeg stopped (exit 1): Server returned 403 Forbidden. '
                                       'The partial file was removed.')
        self.assertEqual(job['code'], 'vod_ffmpeg_failed')
        self.assertEqual(job['zh'],
                         TEMPLATES[FFMPEG_FAILED].zh.format(exit_code=1, detail=FFMPEG_DETAIL))
        self.assertEqual((job['exit_code'], job['detail']), (1, FFMPEG_DETAIL))
        self.assertFalse(importer._media(job['id'], part=True).exists(),
                         'the partial file must not stay behind')

    def test_a_channel_the_scan_cannot_read_keeps_its_sentence(self):
        importer = self.importer(sources=[{'id': 's1', 'kind': 'channel', 'channel': CHANNEL}])
        with mock.patch.object(VodImporter, '_channel_vods',
                               lambda self, channel, force=False: (None, CHANNEL_ERROR)):
            view = importer.scan()
        self.assertEqual(view['error'], 'brokenchannel: Twitch API request failed (HTTP 500)')
        self.assertEqual(view['error'].encode('utf-8'),
                         b'brokenchannel: Twitch API request failed (HTTP 500)')
        # The table holds the identity of that joined text, but the body of /api/vods/queue
        # carries the ten keys the console reads and no key for an identity, so the sentence
        # travels alone (see the limits of round 45 in the evidence file).
        sentence, identity = filled_refusal(SCAN_CHANNEL, channel=CHANNEL, message=CHANNEL_ERROR)
        self.assertEqual(view['error'], sentence)
        self.assertEqual((identity['code'], identity['channel']),
                         ('vod_scan_channel_failed', CHANNEL))
        self.assertRegex(identity['zh'], CJK)


if __name__ == '__main__':
    unittest.main()
