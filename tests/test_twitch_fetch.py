"""Unit tests for the one Twitch fetch seam: the purpose table, its rows, its cache policy.

The seam is ``annotator/twitch_source.py``: ``kind`` names one row, the row owns the hosts
this server may open a socket to for that purpose (and the cache policy of its answers), and
the two validators the VOD module publishes are thin reads of it.  Every case here is offline
except the two that use a loopback listener started by this file; no Twitch host is contacted.
Run: PYTHONPATH=. .venv/bin/python -B tests/test_twitch_fetch.py
"""
import dataclasses
import http.server
import threading
import time
import unittest
from unittest.mock import patch

from annotator import twitch_source as live
from annotator import twitch_vod_source as vod
from annotator.twitch_source import TwitchSourceError
from annotator.twitch_vod_source import TwitchVodError

API_URL = 'https://gql.twitch.tv/gql'
LIVE_MEDIA_URL = 'https://video-weaver.fra02.hls.ttvnw.net/a.ts'
VOD_MEDIA_URL = 'https://d2nvs31859zcd8.cloudfront.net/a/b.m3u8'
THUMB_URL = ('https://static-cdn.jtvnw.net/cf_vods/d2nvs31859zcd8/abc_examplechannel/'
             'thumb/thumb0-320x180.jpg')
PURPOSES = ('api', 'live-media', 'thumb', 'vod-media')
ACCEPTED = {'api': API_URL, 'live-media': LIVE_MEDIA_URL, 'thumb': THUMB_URL,
            'vod-media': VOD_MEDIA_URL}
REFUSED = 'https://evil.example/a'


class PurposeTableTests(unittest.TestCase):
    """The table, not a call site, decides which host one purpose may reach."""

    def test_the_purposes_are_exactly_the_four_the_seam_serves(self):
        self.assertEqual(sorted(live._PURPOSES), list(PURPOSES))

    def test_every_row_pins_its_transport_and_carries_its_refusal_sentence(self):
        for kind in PURPOSES:
            with self.subTest(kind=kind):
                row = live.purpose(kind)
                self.assertTrue(row.hosts or row.suffixes)
                self.assertEqual(row.scheme, 'https')
                self.assertEqual(row.ports, (None, 443))
                self.assertTrue(row.message)

    def test_a_host_added_for_one_purpose_is_refused_by_every_other(self):
        for kind in PURPOSES:
            for other in PURPOSES:
                if other == kind or {kind, other} == {'live-media', 'vod-media'}:
                    continue  # both media rows serve *.ttvnw.net, by design
                with self.subTest(kind=kind, other=other):
                    with self.assertRaises((TwitchSourceError, TwitchVodError)):
                        live.allow(other, ACCEPTED[kind])

    def test_the_vod_distribution_is_not_a_live_media_or_a_picture_host(self):
        for other in ('api', 'live-media', 'thumb'):
            with self.subTest(other=other):
                with self.assertRaises(TwitchSourceError):
                    live.allow(other, VOD_MEDIA_URL)

    def test_the_picture_row_pins_its_host_exactly(self):
        self.assertEqual(live.purpose('thumb').hosts, frozenset({'static-cdn.jtvnw.net'}))
        for url in ('https://static-cdn.jtvnw.net.evil.example/x.jpg',
                    'https://jtvnw.net/x.jpg', 'https://cdn.jtvnw.net/x.jpg'):
            with self.subTest(url=url):
                with self.assertRaises(TwitchSourceError) as caught:
                    live.allow('thumb', url)
                self.assertEqual(str(caught.exception),
                                 'Twitch returned an unsafe thumbnail URL')

    def test_an_unknown_purpose_is_a_programming_error_that_lists_the_others(self):
        with self.assertRaises(ValueError) as caught:
            live.allow('thumbnails', THUMB_URL)
        message = str(caught.exception)
        self.assertIn("'thumbnails'", message)
        for kind in PURPOSES:
            self.assertIn(kind, message)

    def test_a_second_row_for_one_purpose_or_a_hostless_row_is_refused(self):
        with self.assertRaises(ValueError):
            live.declare('thumb', hosts={'static-cdn.jtvnw.net'}, message='duplicate')
        with self.assertRaises(ValueError):
            live.declare('hostless-check', message='refused')
        self.assertNotIn('hostless-check', live._PURPOSES)

    def test_a_declared_row_is_read_back_by_the_same_rules(self):
        live.declare('temp-check', hosts={'example.invalid'}, suffixes=('.example.invalid',),
                     message='refused')
        self.addCleanup(live._PURPOSES.pop, 'temp-check', None)
        for url in ('https://example.invalid/x', 'https://cdn.example.invalid/x'):
            with self.subTest(url=url):
                self.assertEqual(live.allow('temp-check', url), url)
        for url in ('http://example.invalid/x', 'https://example.invalid:8443/x',
                    'https://example.invalid/x#f', 'https://example.invalid\\x'):
            with self.subTest(url=url):
                with self.assertRaises(TwitchSourceError):
                    live.allow('temp-check', url)

    def test_both_modules_answer_with_the_one_table(self):
        self.assertEqual(vod._validate_media(VOD_MEDIA_URL), live.allow('vod-media', VOD_MEDIA_URL))
        self.assertEqual(vod._validate_thumb(THUMB_URL), live.allow('thumb', THUMB_URL))

    def test_the_vod_module_keeps_no_allowlist_or_cache_limit_of_its_own(self):
        for name in ('_VOD_MEDIA_HOSTS', '_VOD_THUMB_HOSTS', '_THUMB_CACHE_TTL_S',
                     '_THUMB_CACHE_MAX'):
            with self.subTest(name=name):
                self.assertFalse(hasattr(vod, name))


class RefusalTests(unittest.TestCase):
    """Every purpose keeps the sentence it always printed, in its own module's error type."""

    def test_the_seam_keeps_the_three_refusal_sentences(self):
        cases = (('api', 'Twitch returned an unsafe playback URL'),
                 ('live-media', 'Twitch returned an unsafe playback URL'),
                 ('vod-media', 'Twitch returned an unsafe VOD playback URL'),
                 ('thumb', 'Twitch returned an unsafe thumbnail URL'))
        for kind, message in cases:
            with self.subTest(kind=kind):
                with self.assertRaises(TwitchSourceError) as caught:
                    live.allow(kind, REFUSED)
                self.assertEqual(str(caught.exception), message)

    def test_the_vod_module_publishes_its_own_two_sentences(self):
        cases = ((vod._validate_media, 'Twitch returned an unsafe VOD playback URL'),
                 (vod._validate_thumb, 'Twitch returned an unsafe thumbnail URL'))
        for function, message in cases:
            with self.subTest(function=function.__name__):
                with self.assertRaises(TwitchVodError) as caught:
                    function(REFUSED)
                self.assertEqual(str(caught.exception), message)

    def test_the_two_modules_do_not_share_an_error_type(self):
        self.assertFalse(issubclass(TwitchVodError, TwitchSourceError))
        self.assertFalse(issubclass(TwitchSourceError, TwitchVodError))

    def test_the_hostile_cases_are_refused_for_every_row(self):
        hostile = ('', None, 'http://static-cdn.jtvnw.net/x.jpg',
                   'https://user:pw@static-cdn.jtvnw.net/x.jpg',
                   'https://static-cdn.jtvnw.net:8443/x.jpg',
                   'https://static-cdn.jtvnw.net/x.jpg#f', 'https://static-cdn.jtvnw.net\\x.jpg',
                   'file:///etc/passwd', 'https://static-cdn.jtvnw.net.evil.example/x.jpg')
        for url in hostile:
            with self.subTest(url=url):
                with self.assertRaises(TwitchVodError):
                    vod._validate_thumb(url)
                with self.assertRaises(TwitchVodError):
                    vod._validate_media(url)

    def test_the_media_and_picture_rows_take_their_own_hosts(self):
        for url in (VOD_MEDIA_URL, LIVE_MEDIA_URL, 'https://some.twitchcdn.net/a.ts'):
            with self.subTest(url=url):
                self.assertEqual(vod._validate_media(url), url)
        self.assertEqual(vod._validate_thumb(THUMB_URL), THUMB_URL)
        with self.assertRaises(TwitchVodError):
            vod._validate_thumb(VOD_MEDIA_URL)
        with self.assertRaises(TwitchVodError):
            vod._validate_media(THUMB_URL)


class CachePolicyTests(unittest.TestCase):
    """The cache policy is a row of the same table, so no caller invents its own."""

    def setUp(self):
        self.store = live.cache_store('thumb')
        self.addCleanup(self.store.clear)

    def test_only_the_picture_row_declares_a_cache(self):
        cached = [kind for kind in PURPOSES if live.cache_policy(kind) is not None]
        self.assertEqual(cached, ['thumb'])
        for kind in ('api', 'live-media', 'vod-media'):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    live.cache_store(kind)

    def test_the_picture_module_uses_the_row_store_not_one_of_its_own(self):
        self.assertIs(vod._THUMB_CACHE, self.store)

    def test_remember_keeps_one_answer_per_key_until_the_row_ttl_passes(self):
        calls = []
        first = live.remember('thumb', 'k', lambda: calls.append('first') or 'A')
        second = live.remember('thumb', 'k', lambda: calls.append('second') or 'B')
        self.assertEqual((first, second, calls), ('A', 'A', ['first']))
        stale = time.monotonic() - live.cache_policy('thumb').ttl_s - 1
        self.store['k'] = (stale, 'A')
        self.assertEqual(live.remember('thumb', 'k', lambda: 'C'), 'C')
        self.assertEqual(self.store['k'][1], 'C')

    def test_remember_never_keeps_an_exception(self):
        def broken():
            raise TwitchVodError('Twitch has no such video')

        for _ in range(2):
            with self.assertRaises(TwitchVodError):
                live.remember('thumb', 'k2', broken)
        self.assertNotIn('k2', self.store)

    def test_remember_clears_the_store_wholesale_when_the_row_is_full(self):
        limit = live.cache_policy('thumb').max_entries
        for index in range(limit):
            self.store['old%d' % index] = (time.monotonic(), 'x')
        self.assertEqual(live.remember('thumb', 'new', lambda: 'y'), 'y')
        self.assertEqual(sorted(self.store), ['new'])

    def test_an_uncached_purpose_produces_on_every_call(self):
        calls = []
        for _ in range(2):
            live.remember('api', 'k', lambda: calls.append('call') or 'A')
        self.assertEqual(len(calls), 2)

    def test_a_picture_is_fetched_once_and_then_answered_by_the_row(self):
        document = {'data': {'video': {'previewThumbnailURL': THUMB_URL}}}
        with patch.object(vod, 'gql', return_value=document) as gql:
            with patch.object(vod, '_raw_bytes',
                              return_value={'status': 200, 'body': b'\xff' * 512,
                                            'transport': None}) as raw_bytes:
                first = vod.vod_thumbnail(1000000001)
                second = vod.vod_thumbnail('v1000000001')
        self.assertEqual(first, ('image/jpeg', b'\xff' * 512))
        self.assertEqual(second, first)
        self.assertEqual((gql.call_count, raw_bytes.call_count), (1, 1))
        self.assertIn('1000000001', self.store)


class LoopbackListener:
    """A loopback HTTP listener that counts requests; no Twitch host is involved."""

    def __init__(self):
        counter = self
        self.requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                counter.requests.append(self.path)
                body = b'\xff\xd8\xff' + b'\x00' * 509
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def url(self):
        return 'http://127.0.0.1:%d/thumb0-320x180.jpg' % self.port


class LoopbackRowTests(unittest.TestCase):
    """The row, and nothing else, decides whether a real socket may open."""

    def setUp(self):
        self.listener = LoopbackListener()
        self.addCleanup(self.listener.close)

    def test_the_product_row_refuses_a_loopback_picture_before_any_socket(self):
        with self.assertRaises(TwitchVodError) as caught:
            vod._raw_bytes(self.listener.url)
        self.assertEqual(str(caught.exception), 'Twitch returned an unsafe thumbnail URL')
        self.assertEqual(self.listener.requests, [])

    def test_the_same_call_is_served_once_the_row_names_the_listener(self):
        row = live.purpose('thumb')
        live._PURPOSES['thumb'] = dataclasses.replace(row, hosts=frozenset({'127.0.0.1'}),
                                                      scheme='http', ports=(self.listener.port,))
        self.addCleanup(live._PURPOSES.__setitem__, 'thumb', row)
        result = vod._raw_bytes(self.listener.url)
        self.assertEqual(result['transport'], None)
        self.assertEqual(result['status'], 200)
        self.assertEqual(result['body'][:3], b'\xff\xd8\xff')
        self.assertEqual(self.listener.requests, ['/thumb0-320x180.jpg'])
