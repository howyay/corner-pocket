import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from annotator import twitch_source as source


CHANNEL = 'https://www.twitch.tv/examplechannel'
MEDIA = 'https://video-weaver.example.hls.ttvnw.net/live/720.m3u8?private=secret'
TOKEN = json.dumps({'data': {'streamPlaybackAccessToken': {'signature': 'private-signature', 'value': 'private-token'}}})
MASTER = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080\nhttps://cdn.ttvnw.net/1080.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720\n' + MEDIA
PLAYLIST = '#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\nsegment.ts\n#EXT-X-TWITCH-PREFETCH:next.ts\n'


class TwitchSourceTests(unittest.TestCase):
    def test_selects_direct_720p_media_without_credentials_or_ad_overrides(self):
        with patch.object(source, '_request', side_effect=[TOKEN, MASTER, PLAYLIST]) as request:
            self.assertEqual(source.resolve_twitch(CHANNEL), MEDIA)
        self.assertEqual(request.call_count, 3)
        payload = request.call_args_list[0].args[1]
        self.assertEqual(payload['variables']['login'], 'examplechannel')
        self.assertEqual(payload['variables']['playerType'], 'embed')
        self.assertNotIn('Authorization', str(request.call_args_list))
        self.assertNotIn('hide_ads', str(request.call_args_list))

    def test_canonical_channels_only_before_network(self):
        for value in [None, {}, 'http://www.twitch.tv/examplechannel', 'https://twitch.tv/examplechannel',
                      CHANNEL + '?token=secret', 'https://x@www.twitch.tv/examplechannel', CHANNEL + '/videos',
                      'https://www.twitch.tv:443/examplechannel', 'https://evil.test/examplechannel']:
            with self.subTest(value=value), patch.object(source, '_request') as request:
                with self.assertRaises(source.TwitchSourceError):
                    source.resolve_twitch(value)
                request.assert_not_called()

    def test_offline_restricted_and_malformed_tokens_are_safe(self):
        for response, expected in [('{"data":{"streamPlaybackAccessToken":null}}', 'offline'),
                                   ('{"errors":[{"message":"private-token"}]}', 'authorization'),
                                   ('private-token', 'invalid'), ('[]', 'invalid'),
                                   ('{"data":{"streamPlaybackAccessToken":{}}}', 'invalid')]:
            with self.subTest(response=response), patch.object(source, '_request', return_value=response):
                with self.assertRaisesRegex(source.TwitchSourceError, expected) as error:
                    source.resolve_twitch(CHANNEL)
                self.assertNotIn('private-token', str(error.exception))

    def test_rejects_unsafe_master_variants_and_segment_references(self):
        for url in ['http://cdn.ttvnw.net/a', 'file:///etc/passwd', 'https://evil.test/a',
                    'https://cdn.ttvnw.net.evil.test/a', 'https://user:secret@cdn.ttvnw.net/a',
                    'https://cdn.ttvnw.net:444/a']:
            with self.subTest(url=url):
                for responses in [[TOKEN, MASTER.replace(MEDIA, url)],
                                  [TOKEN, MASTER, PLAYLIST.replace('segment.ts', url)],
                                  [TOKEN, MASTER, PLAYLIST + '#EXT-X-KEY:METHOD=AES-128,URI="' + url + '"']]:
                    with patch.object(source, '_request', side_effect=responses):
                        with self.assertRaisesRegex(source.TwitchSourceError, 'unsafe'):
                            source.resolve_twitch(CHANNEL)

    def test_rejects_invalid_empty_ended_or_nested_playlists(self):
        for playlist in ['<html>private-token</html>', '#EXTM3U', PLAYLIST + '#EXT-X-ENDLIST', MASTER]:
            with self.subTest(playlist=playlist), patch.object(source, '_request', side_effect=[TOKEN, MASTER, playlist]):
                with self.assertRaises(source.TwitchSourceError):
                    source.resolve_twitch(CHANNEL)

    def test_transport_limits_and_no_redirect(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'#EXTM3U'
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(source, 'build_opener', return_value=opener) as build:
            self.assertEqual(source._request(MEDIA), '#EXTM3U')
        self.assertIsInstance(build.call_args.args[0], source._NoRedirect)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 5)
        response.__enter__.return_value.read.assert_called_once_with(source._MAX_BYTES + 1)
        self.assertIsNone(source._NoRedirect().redirect_request(None, None, 302, '', {}, 'file:///tmp/a'))

    def test_transport_errors_do_not_expose_signed_url_or_body(self):
        for failure, expected in [(HTTPError(MEDIA, 404, 'private-token', {}, io.BytesIO()), 'offline'),
                                  (HTTPError(MEDIA, 403, 'private-token', {}, io.BytesIO()), 'restricted'),
                                  (HTTPError(MEDIA, 302, 'private-token', {}, io.BytesIO()), 'HTTP 302'),
                                  (URLError(MEDIA), 'network'), (TimeoutError(MEDIA), 'network')]:
            opener = MagicMock()
            opener.open.side_effect = failure
            with patch.object(source, 'build_opener', return_value=opener):
                with self.assertRaisesRegex(source.TwitchSourceError, expected) as error:
                    source._request(MEDIA)
            self.assertNotIn('secret', str(error.exception))
            self.assertNotIn('private-token', str(error.exception))
            self.assertTrue(error.exception.__suppress_context__)

    def test_oversized_response(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'x' * (source._MAX_BYTES + 1)
        with patch.object(source, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(source.TwitchSourceError, 'size limit'):
                source._request(MEDIA)


class PlaylistLagTests(unittest.TestCase):
    """Live-edge age from #EXT-X-PROGRAM-DATE-TIME, and every case where it must say None."""

    NOW = 1_790_410_000.0            # fixed: no wall clock in these assertions

    def live_playlist(self, *, lag_s=1.5, duration=2.0, segments=3, now=None):
        import datetime
        now = self.NOW if now is None else now
        lines = ['#EXTM3U', '#EXT-X-VERSION:3', '#EXT-X-TARGETDURATION:2',
                 '#EXT-X-MEDIA-SEQUENCE:2498', '#EXT-X-TWITCH-LIVE-SEQUENCE:2498',
                 '#EXT-X-TWITCH-ELAPSED-SECS:4778.352']
        # The newest segment ended `lag_s` ago, so its start is lag+duration before now.
        start = now - lag_s - duration - (segments - 1) * duration
        for index in range(segments):
            moment = start + index * duration
            stamp = datetime.datetime.fromtimestamp(moment, datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
            lines += ['#EXT-X-PROGRAM-DATE-TIME:' + stamp, '#EXTINF:%.3f,' % duration,
                      'https://cdn.ttvnw.net/seg%d.ts' % index]
        return '\n'.join(lines) + '\n'

    def test_lag_is_the_age_of_the_newest_segment_end(self):
        lag = source.playlist_lag(self.live_playlist(lag_s=1.5), now=self.NOW)
        self.assertAlmostEqual(lag['lag_s'], 1.5, places=3)
        self.assertEqual(lag['segments'], 3)
        self.assertTrue(lag['live'])
        self.assertIn('+00:00', lag['newest_segment_end'])

    def test_a_different_lag_is_read_back(self):
        self.assertAlmostEqual(source.playlist_lag(self.live_playlist(lag_s=4.25), now=self.NOW)['lag_s'],
                               4.25, places=3)

    def test_playlist_without_program_date_time_says_nothing(self):
        for body in (PLAYLIST,                                    # segments, no PDT
                     '#EXTM3U\n#EXT-X-TWITCH-ELAPSED-SECS:4778.352\n#EXTINF:2,\na.ts\n',
                     '#EXTM3U\n#EXT-X-PROGRAM-DATE-TIME:not-a-time\n#EXTINF:2,\na.ts\n'):
            with self.subTest(body=body[:40]):
                self.assertIsNone(source.playlist_lag(body, now=self.NOW))

    def test_a_recording_is_not_an_upstream(self):
        for kind in ('#EXT-X-PLAYLIST-TYPE:EVENT', '#EXT-X-PLAYLIST-TYPE:VOD'):
            body = self.live_playlist().replace('#EXT-X-VERSION:3', '#EXT-X-VERSION:3\n' + kind)
            with self.subTest(kind=kind):
                self.assertIsNone(source.playlist_lag(body, now=self.NOW))
        ended = self.live_playlist() + '#EXT-X-ENDLIST\n'
        self.assertIsNone(source.playlist_lag(ended, now=self.NOW))

    def test_garbage_is_not_a_playlist(self):
        for body in ('', 'not a playlist', '<html>403</html>', '#EXTM3U\n'):
            with self.subTest(body=body[:20]):
                self.assertIsNone(source.playlist_lag(body, now=self.NOW))

    def test_playlist_text_uses_the_validated_request_path(self):
        with patch.object(source, '_request', return_value=PLAYLIST) as request:
            self.assertEqual(source.playlist_text(MEDIA, timeout=2), PLAYLIST)
        self.assertEqual(request.call_args.kwargs, {'timeout': 2})
        # Unpatched: the host allowlist refuses before any socket is opened.
        with self.assertRaisesRegex(source.TwitchSourceError, 'unsafe'):
            source.playlist_text('https://evil.example/playlist.m3u8')


class PublicTwitchIdentifiersTests(unittest.TestCase):
    """The two constants a secret scanner flags are public Twitch values, not credentials.

    `_TOKEN_HASH` is Twitch's persisted-query SHA-256 for `PlaybackAccessToken` and
    `_CLIENT_ID` is the public web-player client id; both say so where they are defined and
    both are allowlisted in `.gitleaks.toml`. They still have to be the *real* values: a hash
    of the wrong length makes every `PlaybackAccessToken` call fail, so the shape is pinned
    here (one redaction pass truncated the hash to 32 placeholder characters).
    """

    def test_the_persisted_query_hash_is_the_real_64_hex_digest(self):
        self.assertEqual(source._TOKEN_HASH, 'ed230aa1e33e07eebb8928504583da78a5173989fadfb1ac94be06a04f3cdbe9')
        self.assertRegex(source._TOKEN_HASH, r'^[0-9a-f]{64}$')

    def test_the_client_id_is_the_public_web_player_id(self):
        self.assertEqual(source._CLIENT_ID, 'kimne78kx3ncx6brgo4mv6wki5h1ko')
        self.assertRegex(source._CLIENT_ID, r'^[a-z0-9]{30}$')

    def test_the_gql_request_sends_that_hash(self):
        with patch.object(source, '_request', side_effect=[TOKEN, MASTER, PLAYLIST]) as request:
            source.resolve_twitch(CHANNEL)
        self.assertEqual(request.call_args_list[0].args[1]['extensions']['persistedQuery']['sha256Hash'],
                         source._TOKEN_HASH)


if __name__ == '__main__':
    unittest.main()
