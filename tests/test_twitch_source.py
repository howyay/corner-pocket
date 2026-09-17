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


if __name__ == '__main__':
    unittest.main()
