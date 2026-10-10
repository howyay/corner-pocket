"""Unit tests for the Twitch VOD source: id parsing, redaction, allowlists, fetch shapes.

No network: every request goes through ``annotator.twitch_vod_source._raw``, which the
tests replace with a scripted fake.  The real endpoints were verified once by hand and the
raw evidence is recorded in ``docs/twitch-vod-as-live.md``.
Run: PYTHONPATH=. .venv/bin/python -B tests/test_twitch_vod_source.py
"""
import json
import re
import unittest
from unittest.mock import patch

from annotator import twitch_vod_source as vod
from annotator.twitch_vod_source import TwitchVodError

MASTER = '\n'.join([
    '#EXTM3U',
    '#EXT-X-TWITCH-INFO:ORIGIN="s3",B="false"',
    '#EXT-X-MEDIA:TYPE=VIDEO,GROUP-ID="chunked",NAME="1080p60",AUTOSELECT=YES',
    '#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080,FRAME-RATE=60.000',
    'https://d2nvs31859zcd8.cloudfront.net/1080.m3u8',
    '#EXT-X-STREAM-INF:BANDWIDTH=3161420,RESOLUTION=1280x720,FRAME-RATE=30.000',
    'https://d2nvs31859zcd8.cloudfront.net/720.m3u8',
    '#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=854x480,FRAME-RATE=30.000',
    'https://d2nvs31859zcd8.cloudfront.net/480.m3u8',
]) + '\n'
MEDIA_HEAD = '\n'.join([
    '#EXTM3U', '#EXT-X-VERSION:3', '#EXT-X-TARGETDURATION:12',
    '#EXT-X-PLAYLIST-TYPE:EVENT', '#EXT-X-MEDIA-SEQUENCE:0',
    '#EXTINF:10.000,', 'https://d2nvs31859zcd8.cloudfront.net/000.ts',
]) + '\n'
GQL_VOD = {'data': {'video': {'id': '1000000001', 'title': '260918', 'lengthSeconds': 31137,
                              'createdAt': '2026-09-19T01:29:07Z', 'owner': {'login': 'examplechannel'},
                              'playbackAccessToken': {'signature': 'S' * 40, 'value': 'V' * 444}}}}
THUMB_URL = ('https://static-cdn.jtvnw.net/cf_vods/d2nvs31859zcd8/abc_examplechannel/'
             'thumb/thumb0-320x180.jpg')
GQL_CHANNEL = {'data': {'user': {'login': 'examplechannel', 'videos': {'edges': [
    {'node': {'id': '1000000001', 'title': '260918', 'lengthSeconds': 31137,
              'createdAt': '2026-09-19T01:29:07Z', 'broadcastType': 'HIGHLIGHT',
              'previewThumbnailURL': THUMB_URL}}]}}}}


def reply(status, body):
    return {'status': status, 'body': body, 'transport': None}


class Network:
    """Scripted ``_raw``: records every call, answers by URL substring."""

    def __init__(self, gql_body=None, master=MASTER, media=MEDIA_HEAD, status=None):
        self.calls = []
        self.gql_body = gql_body if gql_body is not None else GQL_VOD
        self.master = master
        self.media = media
        self.statuses = dict(status or {})

    def __call__(self, url, payload=None, **kwargs):
        self.calls.append((url, payload))
        if payload is not None:
            status = self.statuses.get('gql', 200)
            return reply(status, json.dumps(self.gql_body))
        if 'usher.ttvnw.net/vod/' in url:
            status = self.statuses.get('usher', 200)
            return reply(status, self.master if status == 200 else '[{"error":"Can not find channel"}]')
        status = self.statuses.get('media', 200)
        return reply(status, self.media)


class VodIdTests(unittest.TestCase):
    def test_accepted_forms(self):
        for argument in ('1000000001', 'v1000000001', 'V1000000001',
                         'https://www.twitch.tv/videos/1000000001',
                         'https://www.twitch.tv/videos/1000000001/', 1000000001):
            with self.subTest(argument=argument):
                self.assertEqual(vod.vod_id_of(argument), '1000000001')

    def test_rejected_forms(self):
        for argument in ('', 'abc', 'v', None, [], {}, 0, -1, True,
                         'https://www.twitch.tv/examplechannel',
                         'https://evil.example/videos/123'):
            with self.subTest(argument=argument):
                with self.assertRaises(TwitchVodError):
                    vod.vod_id_of(argument)


class MediaAllowlistTests(unittest.TestCase):
    def test_accepts_twitch_cdn_and_the_pinned_vod_host(self):
        for url in ('https://d2nvs31859zcd8.cloudfront.net/a/b.m3u8',
                    'https://vod-secure.ttvnw.net/a.m3u8',
                    'https://video-weaver.fra02.hls.ttvnw.net/a.ts',
                    'https://d123.cloudfront.net/x.ts'.replace('d123.cloudfront.net', 'some.twitchcdn.net')):
            with self.subTest(url=url):
                self.assertEqual(vod._validate_media(url), url)

    def test_refuses_everything_else(self):
        for url in ('http://d2nvs31859zcd8.cloudfront.net/a.m3u8',
                    'https://evil.cloudfront.net/a.m3u8',
                    'https://d2nvs31859zcd8.cloudfront.net.evil.example/a.m3u8',
                    'https://user:pass@d2nvs31859zcd8.cloudfront.net/a.m3u8',
                    'https://d2nvs31859zcd8.cloudfront.net:8443/a.m3u8',
                    'https://d2nvs31859zcd8.cloudfront.net/a.m3u8#frag',
                    'https://d2nvs31859zcd8.cloudfront.net/a\\b.m3u8',
                    'file:///etc/passwd', ''):
            with self.subTest(url=url):
                with self.assertRaises(TwitchVodError):
                    vod._validate_media(url)


class EvidenceTests(unittest.TestCase):
    def test_never_prints_a_token_or_a_signed_url(self):
        result = {'vod_id': '1000000001', 'signature': 'S' * 40, 'value': 'V' * 444,
                  'media_url': 'https://d2nvs31859zcd8.cloudfront.net/secret/path.m3u8?nauth=SECRET',
                  'variant': {'height': 720, 'url': 'https://d2nvs31859zcd8.cloudfront.net/x.m3u8?t=1'},
                  'variants': [{'height': 480, 'url': 'https://d2nvs31859zcd8.cloudfront.net/y.m3u8'}]}
        printed = json.dumps(vod.evidence(result), sort_keys=True)
        for secret in ('S' * 40, 'V' * 444, 'SECRET', 'secret/path', 'x.m3u8', 'y.m3u8'):
            self.assertNotIn(secret, printed)
        redacted = vod.evidence(result)
        self.assertEqual(redacted['signature_len'], 40)
        self.assertEqual(redacted['value_len'], 444)
        self.assertEqual(redacted['media_url_host'], 'd2nvs31859zcd8.cloudfront.net')
        self.assertNotIn('url', redacted['variants'][0])

    def test_passes_plain_values_through(self):
        self.assertEqual(vod.evidence({'status': 200, 'errors': None}), {'status': 200, 'errors': None})
        self.assertEqual(vod.evidence('x'), 'x')


class PlaylistTests(unittest.TestCase):
    def test_variants_are_parsed_with_resolution_bandwidth_and_rate(self):
        variants = vod.vod_variants('https://usher.ttvnw.net/vod/1.m3u8?nauthsig=x', MASTER)
        self.assertEqual([v['height'] for v in variants], [1080, 720, 480])
        self.assertEqual(variants[1]['bandwidth'], 3161420)
        self.assertEqual(variants[1]['fps'], 30.0)

    def test_invalid_playlists_are_refused(self):
        for body in ('', 'not a playlist'):
            with self.subTest(body=body):
                with self.assertRaises(TwitchVodError):
                    vod.vod_variants('https://usher.ttvnw.net/vod/1.m3u8', body)

    def test_stream_in_without_resolution_is_not_a_variant(self):
        body = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nhttps://d2nvs31859zcd8.cloudfront.net/a.m3u8\n'
        self.assertEqual(vod.vod_variants('https://usher.ttvnw.net/vod/1.m3u8', body), [])
        with self.assertRaises(TwitchVodError):
            vod.vod_variants('https://usher.ttvnw.net/vod/1.m3u8',
                             '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=1x1\nhttps://evil.example/a.m3u8\n')


class TokenTests(unittest.TestCase):
    def test_token_is_extracted_and_evidence_is_redacted(self):
        network = Network()
        with patch('annotator.twitch_vod_source._raw', network):
            token = vod.vod_token('1000000001')
        self.assertTrue(token['ok'])
        self.assertEqual(token['signature'], 'S' * 40)
        self.assertEqual(token['channel'], 'examplechannel')
        self.assertEqual(token['length_s'], 31137)
        printed = json.dumps(vod.evidence(token), sort_keys=True)
        self.assertNotIn('S' * 40, printed)
        self.assertNotIn('V' * 444, printed)
        query = network.calls[0][1]['query']
        self.assertIn('playbackAccessToken(params: {platform: "web"', query)
        self.assertIn('playerBackend: "mediaplayer"', query)
        self.assertIn('video(id: "1000000001")', query)

    def test_missing_token_is_a_safe_error_or_a_recorded_failure(self):
        network = Network(gql_body={'data': {'video': {'id': '1'}},
                                    'errors': [{'message': 'argument: params is required'}]})
        with patch('annotator.twitch_vod_source._raw', network):
            with self.assertRaises(TwitchVodError):
                vod.vod_token('1')
            loose = vod.vod_token('1', strict=False)
        self.assertFalse(loose['ok'])
        self.assertIsNone(loose['signature'])
        self.assertEqual(loose['errors'], [{'message': 'argument: params is required'}])
        self.assertIn('params is required', json.dumps(vod.evidence(loose)))

    def test_transport_failure_is_reported_by_type_only(self):
        def broken(url, payload=None, **kwargs):
            return {'status': None, 'body': '', 'transport': 'URLError'}
        with patch('annotator.twitch_vod_source._raw', broken):
            with self.assertRaises(TwitchVodError):
                vod.vod_token('1')
            loose = vod.vod_token('1', strict=False)
        self.assertEqual(loose['transport'], 'URLError')
        self.assertFalse(loose['ok'])


class ChannelTests(unittest.TestCase):
    def test_recent_vods_are_listed(self):
        network = Network(gql_body=GQL_CHANNEL)
        with patch('annotator.twitch_vod_source._raw', network):
            vods = vod.channel_recent_vods('examplechannel', 1)
        self.assertEqual(vods, [{'id': '1000000001', 'title': '260918', 'length_s': 31137,
                                 'created_at': '2026-09-19T01:29:07Z', 'channel': 'examplechannel',
                                 'broadcast_type': 'HIGHLIGHT', 'thumbnail': THUMB_URL}])
        query = network.calls[0][1]['query']
        self.assertIn('videos(first: 1)', query)
        # Measured 2026-10-03 on the club's own channel: `type: ARCHIVE` answered with 2 videos
        # while the channel exposes 31 -- the older nights are typed HIGHLIGHT, which is where
        # the club's own "(Record) YYYYMMDD" archive lives. The listing must not filter them out.
        self.assertNotIn('type: ARCHIVE', query)
        self.assertIn('broadcastType', query)
        self.assertIn('previewThumbnailURL(width: 320, height: 180)', query)

    def test_the_window_is_one_page_and_clamped_to_twitchs_own_ceiling(self):
        """Measured 2026-10-03: `videos` exposes no working cursor (pageInfo.endCursor is null on
        every page and an edge cursor passed as `after:` returns nothing), so `first:` IS the
        window. Twitch's ceiling for one page is 100; ask for more and 100 is what happens. The
        same measurement found the other half of the window: one page of 60 held the channel's
        whole history (31 videos, newest first, `hasNextPage: False`)."""
        big = Network(gql_body=GQL_CHANNEL)
        with patch('annotator.twitch_vod_source._raw', big):
            vod.channel_recent_vods('examplechannel', 999)
        self.assertIn('videos(first: 100)', big.calls[0][1]['query'])
        small = Network(gql_body=GQL_CHANNEL)
        with patch('annotator.twitch_vod_source._raw', small):
            vod.channel_recent_vods('examplechannel', 0)
        self.assertIn('videos(first: 1)', small.calls[0][1]['query'])

    def test_unknown_channel_and_bad_login(self):
        with patch('annotator.twitch_vod_source._raw', Network(gql_body={'data': {'user': None}})):
            with self.assertRaises(TwitchVodError):
                vod.channel_recent_vods('examplechannel')
        for channel in ('', 'Not A Channel', 'https://www.twitch.tv/x', None):
            with self.assertRaises(TwitchVodError):
                vod.channel_recent_vods(channel)


class ResolveTests(unittest.TestCase):
    def test_resolves_the_best_variant_at_or_below_720p(self):
        network = Network()
        with patch('annotator.twitch_vod_source._raw', network):
            resolved = vod.resolve_vod('1000000001')
        self.assertEqual(resolved['master_status'], 200)
        self.assertEqual(resolved['variant']['height'], 720)
        self.assertTrue(resolved['media_url'].startswith('https://d2nvs31859zcd8.cloudfront.net/'))
        self.assertEqual([v['height'] for v in resolved['variants']], [1080, 720, 480])
        self.assertEqual([v['url'] for v in resolved['variants']], [None, None, None])
        self.assertEqual(resolved['playlist']['type'], 'EVENT')
        self.assertEqual(resolved['playlist']['target_duration_s'], 12.0)
        self.assertFalse(resolved['playlist']['has_endlist'])
        self.assertEqual(vod.evidence(resolved)['media_url_host'], 'd2nvs31859zcd8.cloudfront.net')
        usher = [url for url, payload in network.calls if payload is None][0]
        self.assertIn('https://usher.ttvnw.net/vod/1000000001.m3u8?', usher)
        self.assertIn('nauthsig=', usher)

    def test_usher_failure_is_a_safe_error(self):
        network = Network(status={'usher': 404})
        with patch('annotator.twitch_vod_source._raw', network):
            with self.assertRaises(TwitchVodError) as caught:
                vod.resolve_vod('1000000001')
        self.assertIn('404', str(caught.exception))
        self.assertNotIn('nauth', str(caught.exception))

    def test_live_typed_playlist_is_refused_as_not_a_vod(self):
        live_head = '#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2.0,\nhttps://d2nvs31859zcd8.cloudfront.net/a.ts\n'
        network = Network(media=live_head)
        with patch('annotator.twitch_vod_source._raw', network):
            with self.assertRaises(TwitchVodError) as caught:
                vod.resolve_vod('1000000001')
        self.assertIn('not a finished VOD', str(caught.exception))

    def test_no_variants_is_a_safe_error(self):
        network = Network(master='#EXTM3U\n')
        with patch('annotator.twitch_vod_source._raw', network):
            with self.assertRaises(TwitchVodError):
                vod.resolve_vod('1000000001')


class FakeCapture:
    """A decoder standing in for OpenCV: counts reads, records seeks."""

    def __init__(self, frames=100000, fps=30.0, opened=True):
        self.frames, self.fps, self.opened = frames, fps, opened
        self.index = 0
        self.seeks = []
        self.released = False

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return self.fps if prop == 5 else float(self.index)          # 5 == CAP_PROP_FPS

    def set(self, prop, value):
        self.seeks.append((prop, value))
        return True

    def read(self):
        if self.index >= self.frames:
            return False, None
        self.index += 1
        return True, ('frame', self.index)

    def release(self):
        self.released = True
        self.opened = False


class FakeClock:
    """A clock that only advances when something sleeps."""

    def __init__(self, now=0.0):
        self.now = now
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class PacingTests(unittest.TestCase):
    def capture(self, *, inner=None, **kwargs):
        inner = inner or FakeCapture(**{key: value for key, value in kwargs.items()
                                       if key in ('frames', 'fps', 'opened')})
        clock = FakeClock()
        capture = vod.VodRealtimeCapture('https://d2nvs31859zcd8.cloudfront.net/vod.m3u8',
                                         vod_id='1000000001', capture=inner, clock=clock,
                                         sleep=clock.sleep, **{key: value for key, value in kwargs.items()
                                                               if key not in ('frames', 'fps', 'opened')})
        return capture, inner, clock

    def test_serves_one_frame_per_source_frame_period(self):
        capture, inner, clock = self.capture()
        for _ in range(5):
            ok, frame = capture.read()
            self.assertTrue(ok)
        self.assertEqual(capture.state()['frames_served'], 5)
        self.assertEqual(capture.state()['frames_dropped'], 0)
        self.assertAlmostEqual(clock.now, 4 / 30.0, places=6)        # first frame is immediate
        self.assertEqual(len(clock.slept), 4)
        # Steady state holds the video at most one frame period ahead of the wall clock.
        self.assertLessEqual(0.0, capture.state()['drift_s'])
        self.assertLessEqual(capture.state()['drift_s'], 1 / 30.0 + 1e-9)

    def test_rate_scales_the_wall_clock_slot(self):
        capture, inner, clock = self.capture(rate=2.0)
        for _ in range(5):
            capture.read()
        self.assertAlmostEqual(clock.now, 4 / 60.0, places=6)        # 60 fps of video in real time
        self.assertEqual(capture.state()['rate'], 2.0)
        self.assertEqual(capture.state()['frames_dropped'], 0)

    def test_a_late_consumer_loses_frames_instead_of_drifting(self):
        capture, inner, clock = self.capture()
        capture.read()
        clock.now += 5.0                                             # consumer stalled 5 s
        ok, frame = capture.read()
        self.assertTrue(ok)
        state = capture.state()
        self.assertEqual(state['frames_dropped'], 30)                # bounded catch-up: 1 s worth
        self.assertLessEqual(abs(state['drift_s']), 4.1)             # still behind, bounded
        for _ in range(6):                                           # keeps catching up, never blocks
            capture.read()
        state = capture.state()
        self.assertLessEqual(abs(state['drift_s']), 0.05)            # back on the wall clock
        self.assertGreater(state['frames_dropped'], 30)
        self.assertEqual(state['frames_served'], 8)

    def test_start_offset_seeks_and_shifts_the_timeline(self):
        capture, inner, clock = self.capture()
        capture2 = vod.VodRealtimeCapture('file.mp4', start_s=600.0, capture=FakeCapture(),
                                          clock=FakeClock(), sleep=lambda seconds: None, fps=30.0)
        self.assertEqual(inner.seeks, [])
        self.assertEqual(capture2._capture.seeks[0][1], 600000.0)    # CAP_PROP_POS_MSEC
        self.assertEqual(capture2.state()['video_s'], 600.0)
        self.assertEqual(capture2.get(5), 30.0)                      # FPS
        self.assertEqual(capture2.get(1), 18000.0)                   # POS_FRAMES = 600 s * 30 fps
        self.assertEqual(capture2.get(0), 600000.0)                  # POS_MSEC

    def test_state_never_claims_to_be_live(self):
        capture, inner, clock = self.capture()
        capture.read()
        state = capture.state()
        self.assertEqual(state['kind'], 'vod-replay')
        self.assertFalse(state['live'])
        self.assertEqual(state['vod_id'], '1000000001')
        self.assertEqual(state['pacing'], 'wall-clock')
        self.assertEqual(state['network'], 'hls')
        self.assertEqual(state['fps'], 30.0)
        self.assertIn('drift_s', state)
        self.assertTrue(state['opened'])
        self.assertEqual(vod.VodRealtimeCapture('data/vod_30min_260815.mp4', capture=FakeCapture()).state()['network'],
                         'file')

    def test_end_of_media_and_release_are_reported(self):
        capture, inner, clock = self.capture(frames=2)
        self.assertTrue(capture.read()[0])
        self.assertTrue(capture.read()[0])
        ok, frame = capture.read()
        self.assertFalse(ok)
        self.assertIsNone(frame)
        self.assertEqual(capture.state()['read_failures'], 1)
        capture.release()
        self.assertTrue(inner.released)
        self.assertFalse(capture.isOpened())

    def test_capture_without_an_inner_decoder_uses_opencv_timeouts(self):
        with patch('annotator.twitch_vod_source._open', return_value=FakeCapture()) as opener:
            capture = vod.VodRealtimeCapture('https://d2nvs31859zcd8.cloudfront.net/v.m3u8', fps=30.0)
        self.assertEqual(opener.call_args[0][0], 'https://d2nvs31859zcd8.cloudfront.net/v.m3u8')
        self.assertTrue(capture.isOpened())

    def test_bad_arguments_are_refused(self):
        for kwargs in ({'rate': 0}, {'rate': -1}, {'rate': True}, {'rate': 'x'},
                       {'start_s': -1}, {'start_s': None}, {'start_s': True}, {'max_catchup_s': 0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(TwitchVodError):
                    vod.VodRealtimeCapture('file.mp4', capture=FakeCapture(), **kwargs)


class StateKeySetTests(unittest.TestCase):
    """The class docstring example is the whole ``state()`` answer, key for key."""

    def example_keys(self):
        document = vod.VodRealtimeCapture.__doc__
        start = document.index("{'kind'")
        block = document[start:document.index('}', start) + 1]
        return set(re.findall(r"'([a-z_]+)':", block))

    def test_the_docstring_example_is_exactly_the_state_key_set(self):
        capture = vod.VodRealtimeCapture('file.mp4', capture=FakeCapture(), clock=FakeClock(),
                                         sleep=lambda seconds: None, fps=30.0)
        self.assertEqual(self.example_keys(), set(capture.state()))

    def test_the_parse_reads_the_example_and_not_the_whole_docstring(self):
        listed = self.example_keys()
        self.assertIn('drift_s', listed)                  # the block is found and read
        self.assertNotIn('max_catchup_s', listed)


class ThumbnailTests(unittest.TestCase):
    """The preview picture: a pinned host, bytes rather than text, and one fetch per VOD."""

    def setUp(self):
        vod._THUMB_CACHE.clear()
        self.addCleanup(vod._THUMB_CACHE.clear)

    def gql_reply(self, url):
        return {'data': {'video': {'id': '1000000001', 'previewThumbnailURL': url}}}

    def test_the_listing_validates_each_picture_without_failing_the_row(self):
        body = {'data': {'user': {'login': 'examplechannel', 'videos': {'edges': [
            {'node': {'id': '1000000001', 'title': '260918', 'lengthSeconds': 31137,
                      'createdAt': '2026-09-19T01:29:07Z',
                      'previewThumbnailURL': 'https://evil.example/x.jpg'}}]}}}}
        with patch('annotator.twitch_vod_source._raw', Network(gql_body=body)):
            rows = vod.channel_recent_vods('examplechannel', 1)
        self.assertIsNone(rows[0]['thumbnail'])      # offered, refused, listed without it
        self.assertEqual(rows[0]['id'], '1000000001')

    def test_only_the_pinned_image_cdn_is_accepted(self):
        for url in ('https://evil.example/x.jpg', 'http://static-cdn.jtvnw.net/x.jpg',
                    'https://static-cdn.jtvnw.net.evil.example/x.jpg',
                    'https://user:pw@static-cdn.jtvnw.net/x.jpg', '', None):
            with self.assertRaises(TwitchVodError):
                vod._validate_thumb(url)
        self.assertEqual(vod._validate_thumb(THUMB_URL), THUMB_URL)

    def test_a_picture_is_bytes_and_twice_is_cached(self):
        picture = b'\xff\xd8\xff\xe0' + b'0' * 400
        fetched = []

        def raw_bytes(url, **kwargs):
            fetched.append(url)
            return {'status': 200, 'body': picture, 'transport': None}

        network = Network(gql_body=self.gql_reply(THUMB_URL))
        with patch('annotator.twitch_vod_source._raw', network), \
                patch('annotator.twitch_vod_source._raw_bytes', raw_bytes):
            first = vod.vod_thumbnail('1000000001')
            second = vod.vod_thumbnail('v1000000001')          # the same broadcast, another spelling
        self.assertEqual(first, ('image/jpeg', picture))
        self.assertEqual(second, first)
        self.assertEqual(fetched, [THUMB_URL])                 # one fetch
        self.assertEqual(len(network.calls), 1)                # one API call
        self.assertIn('previewThumbnailURL(width: 320, height: 180)',
                      network.calls[0][1]['query'])

    def test_a_refused_picture_never_reaches_the_fetch(self):
        fetched = []
        with patch('annotator.twitch_vod_source._raw',
                   Network(gql_body=self.gql_reply('https://evil.example/x.jpg'))), \
                patch('annotator.twitch_vod_source._raw_bytes',
                      lambda url, **kw: fetched.append(url)):
            with self.assertRaises(TwitchVodError):
                vod.vod_thumbnail('1000000001')
        self.assertEqual(fetched, [])

    def test_a_missing_or_broken_picture_is_a_safe_error(self):
        for body in ({'data': {'video': None}}, {'data': {}}, {}):
            with patch('annotator.twitch_vod_source._raw', Network(gql_body=body)):
                with self.assertRaises(TwitchVodError):
                    vod.vod_thumbnail('999')
        cases = ({'status': None, 'body': b'', 'transport': 'URLError'},
                 {'status': 404, 'body': b'', 'transport': None},
                 {'status': 200, 'body': b'\xff\xd8', 'transport': None})
        for case in cases:
            vod._THUMB_CACHE.clear()
            with patch('annotator.twitch_vod_source._raw',
                       Network(gql_body=self.gql_reply(THUMB_URL))), \
                    patch('annotator.twitch_vod_source._raw_bytes', lambda url, **kw: case):
                with self.assertRaises(TwitchVodError):
                    vod.vod_thumbnail('1000000001')


if __name__ == '__main__':
    unittest.main()
