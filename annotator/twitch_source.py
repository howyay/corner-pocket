"""Anonymous Twitch web playback, without login, ad filtering, or integrity bypass.

Endpoint/query reference: Streamlink's src/streamlink/plugins/twitch.py.
Returns a direct media playlist, not decoded frames or a latency guarantee.
FFmpeg/OpenCV need not implement Twitch's EXT-X-TWITCH-PREFETCH extension.
Signed URLs are private, short-lived decoder inputs: never log or persist them.
"""
import json
import re
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


class TwitchSourceError(RuntimeError):
    """Safe public error: contains no upstream body, token, or signed URL."""


_TIMEOUT = 5
_MAX_BYTES = 1024 * 1024
_CLIENT_ID = 'kimne78kx3ncx6brgo4mv6wki5h1ko'  # Public web player ID, not a credential.
_TOKEN_HASH = '77777777777777777777777777777777'


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validate_url(url, *, media=False):
    try:
        parts = urlsplit(url)
        host = parts.hostname or ''
        allowed = (host.endswith('.ttvnw.net') or host.endswith('.twitchcdn.net')) if media else host in {
            'gql.twitch.tv', 'usher.ttvnw.net',
        }
        valid = (allowed and parts.scheme == 'https' and not parts.username
                 and not parts.password and parts.port in (None, 443)
                 and not parts.fragment and not re.search(r'[\s\\]', url))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise TwitchSourceError('Twitch returned an unsafe playback URL')
    return url


def _request(url, payload=None):
    _validate_url(url, media=payload is None)
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'}
    data = None
    if payload is not None:
        headers.update({'Client-ID': _CLIENT_ID, 'Content-Type': 'application/json'})
        data = json.dumps(payload).encode('utf-8')
    try:
        context = ssl.create_default_context()
        # Bundled Python installations may not locate the host CA bundle.
        if Path('/etc/ssl/certs/ca-certificates.crt').is_file():
            context.load_verify_locations('/etc/ssl/certs/ca-certificates.crt')
        with build_opener(_NoRedirect(), HTTPSHandler(context=context)).open(Request(url, data=data, headers=headers), timeout=_TIMEOUT) as response:
            body = response.read(_MAX_BYTES + 1)
        if len(body) > _MAX_BYTES:
            raise TwitchSourceError('Twitch playback response exceeds the size limit')
        return body.decode('utf-8-sig')
    except HTTPError as exc:
        if exc.code == 404:
            message = 'Twitch channel is offline or has no public playable stream'
        elif exc.code in (401, 403):
            message = 'Twitch playback is restricted or requires browser authorization'
        else:
            message = 'Twitch playback request failed (HTTP %d)' % exc.code
        raise TwitchSourceError(message) from None
    except (URLError, OSError, UnicodeError, ValueError):
        raise TwitchSourceError('Twitch playback request failed; check network and TLS connectivity') from None


def _playlist(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != '#EXTM3U':
        raise TwitchSourceError('Twitch returned an invalid playback playlist')
    return lines


def resolve_twitch(canonical_url):
    """Resolve https://www.twitch.tv/<channel> to authorized public HTTPS HLS.

    Reject caller credentials, arbitrary URLs, redirects and non-Twitch media
    hosts. Decoder fetches after resolution still need their own protocol policy.
    Network operations have a five-second socket timeout and 1 MiB body limit.
    No authentication or client-integrity fallback is attempted.
    """
    match = re.fullmatch(r'https://www\.twitch\.tv/([a-z0-9_]{1,25})', canonical_url) if isinstance(canonical_url, str) else None
    if not match:
        raise TwitchSourceError('Expected a canonical public Twitch channel URL')
    channel = match[1]
    payload = {
        'operationName': 'PlaybackAccessToken',
        'extensions': {'persistedQuery': {'version': 1, 'sha256Hash': _TOKEN_HASH}},
        'variables': {'isLive': True, 'login': channel, 'isVod': False,
                      'vodID': '', 'playerType': 'embed', 'platform': 'site'},
    }
    try:
        result = json.loads(_request('https://gql.twitch.tv/gql', payload))
        if result.get('errors'):
            raise TwitchSourceError('Twitch playback is unavailable or requires browser authorization')
        token = result['data']['streamPlaybackAccessToken']
        if token is None:
            raise TwitchSourceError('Twitch channel is offline or has no public playable stream')
        signature, value = token['signature'], token['value']
        if not all(isinstance(item, str) and item for item in (signature, value)):
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError):
        raise TwitchSourceError('Twitch returned an invalid playback token response') from None
    master = 'https://usher.ttvnw.net/api/channel/hls/%s.m3u8?%s' % (channel, urlencode({
        'sig': signature, 'token': value, 'platform': 'web',
        'allow_source': 'true', 'allow_audio_only': 'false',
        'playlist_include_framerate': 'true', 'supported_codecs': 'avc1',
    }))
    lines = _playlist(_request(master))
    variants = []
    for index, line in enumerate(lines[:-1]):
        if line.startswith('#EXT-X-STREAM-INF:'):
            bandwidth = re.search(r'(?:[:,])BANDWIDTH=(\d+)(?:,|$)', line)
            if bandwidth and not lines[index + 1].startswith('#'):
                resolution = re.search(r'(?:[:,])RESOLUTION=\d+x(\d+)(?:,|$)', line)
                if resolution:
                    variants.append((int(resolution[1]), int(bandwidth[1]),
                                     _validate_url(urljoin(master, lines[index + 1]), media=True)))
    if not variants:
        raise TwitchSourceError('Twitch channel is offline or has no public video variants')
    # Prefer the best <=720p video; fall back to the smallest available video.
    modest = [variant for variant in variants if variant[0] <= 720]
    media_url = (max(modest) if modest else min(variants))[2]
    media = _playlist(_request(media_url))
    if '#EXT-X-ENDLIST' in media:
        raise TwitchSourceError('Twitch channel is offline; playback has ended')
    if not any(line.startswith('#EXTINF:') for line in media) or any(line.startswith('#EXT-X-STREAM-INF:') for line in media):
        raise TwitchSourceError('Twitch returned no playable live media playlist')
    # Validate current segment, key, map and prefetch references before decoding.
    # Subsequent playlist reloads are performed by the decoder, not this resolver.
    for line in media:
        references = re.findall(r'URI="([^"]*)"', line) if line.startswith('#') else [line]
        if line.startswith('#EXT-X-TWITCH-PREFETCH:'):
            references.append(line.split(':', 1)[1])
        for reference in references:
            _validate_url(urljoin(media_url, reference), media=True)
    return media_url
