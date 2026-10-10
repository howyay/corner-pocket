"""Anonymous Twitch web playback, without login, ad filtering, or integrity bypass.

Endpoint/query reference: Streamlink's src/streamlink/plugins/twitch.py.
Returns a direct media playlist, not decoded frames or a latency guarantee.
FFmpeg/OpenCV need not implement Twitch's EXT-X-TWITCH-PREFETCH extension.
Signed URLs are private, short-lived decoder inputs: never log or persist them.
"""
import datetime
import json
import re
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


class TwitchSourceError(RuntimeError):
    """Safe public error: contains no upstream body, token, or signed URL."""


_TIMEOUT = 5
_MAX_BYTES = 1024 * 1024
_CLIENT_ID = 'kimne78kx3ncx6brgo4mv6wki5h1ko'  # Public web player ID, not a credential.
_TOKEN_HASH = 'ed230aa1e33e07eebb8928504583da78a5173989fadfb1ac94be06a04f3cdbe9'  # Public persisted-query hash, not a credential.


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class _CachePolicy:
    """How long one purpose's answers are kept, and how many are kept before a clear."""

    ttl_s: int
    max_entries: int


@dataclass(frozen=True)
class _Purpose:
    """One row of the fetch table: the whole rule for one reason to open a socket.

    ``hosts`` are exact names.  ``suffixes`` are domain tails and keep the leading dot, so
    the bare domain is not a tail of itself.  ``ports`` holds ``None`` for the scheme's
    default port.  Each row carries its own ``message``, so every purpose keeps the refusal
    sentence it always printed.
    """

    hosts: frozenset
    message: str
    suffixes: tuple = ()
    scheme: str = 'https'
    ports: tuple = (None, 443)
    cache: object = None


#: kind -> _Purpose.  The one owner of "which host may we talk to for which purpose".
_PURPOSES = {}


def declare(kind, *, hosts=(), message, suffixes=(), scheme='https', ports=(None, 443),
            cache=None):
    """Write one row of :data:`_PURPOSES`; the only way a purpose becomes reachable.

    A duplicate ``kind`` is refused, because two rows for one purpose is the drift this
    table exists to stop, and so is a row that names no host.
    """
    if kind in _PURPOSES:
        raise ValueError('fetch purpose %r is already declared' % (kind,))
    if not hosts and not suffixes:
        raise ValueError('fetch purpose %r names no host' % (kind,))
    _PURPOSES[kind] = _Purpose(frozenset(hosts), message, tuple(suffixes), scheme,
                               tuple(ports), cache)


#: The web-player API: the persisted-query endpoint and the live resolver.
declare('api', hosts={'gql.twitch.tv', 'usher.ttvnw.net'},
        message='Twitch returned an unsafe playback URL')
#: Live media: the CDN Twitch hands back for a live stream, and nothing else.
declare('live-media', suffixes=('.ttvnw.net', '.twitchcdn.net'),
        message='Twitch returned an unsafe playback URL')
#: VOD media is *not* served from the live hosts: usher hands out a signed playlist on
#: Twitch's CloudFront distribution (observed: d2nvs31859zcd8.cloudfront.net, 2026-09-24).
#: That host is pinned exactly rather than wildcarded - `*.cloudfront.net` would allow
#: every CloudFront distribution on the internet as a decoder input.  If Twitch rotates
#: it, playback fails loudly with 'unsafe VOD playback URL' and the new host is added here.
declare('vod-media', hosts={'d2nvs31859zcd8.cloudfront.net'},
        suffixes=('.ttvnw.net', '.twitchcdn.net'),
        message='Twitch returned an unsafe VOD playback URL')
#: Preview pictures are served from Twitch's static image CDN, not from the media hosts.
#: Pinned exactly, for the same reason the media distribution is: `*.jtvnw.net` would let
#: any host under that domain become an image this server fetches and hands to a browser.
#: A resolved picture is small and cheap to keep, so this row is also the one with a cache.
declare('thumb', hosts={'static-cdn.jtvnw.net'}, cache=_CachePolicy(ttl_s=3600, max_entries=64),
        message='Twitch returned an unsafe thumbnail URL')


def purpose(kind):
    """The row ``kind`` names, or a ``ValueError`` that lists the kinds that exist."""
    try:
        return _PURPOSES[kind]
    except KeyError:
        raise ValueError('unknown fetch purpose %r; declared: %s'
                         % (kind, ', '.join(sorted(_PURPOSES)))) from None


def cache_policy(kind):
    """The cache policy of one purpose, or ``None`` when its answers are never kept."""
    return purpose(kind).cache


_CACHE_STORES = {}


def cache_store(kind):
    """The dict one cached purpose keeps its answers in; an uncached kind has none."""
    if cache_policy(kind) is None:
        raise ValueError('fetch purpose %r declares no cache' % (kind,))
    return _CACHE_STORES.setdefault(kind, {})


def allow(kind, url, *, error=TwitchSourceError):
    """``url``, if this machine may open a socket to it *for this purpose*; else a refusal.

    ``kind`` is the whole caller-side vocabulary, and the row it names is the only place a
    host may be added, so a host added for one purpose cannot widen another.  The refusal is
    ``error(row.message)``: the sentence belongs to the row, the exception type to the module
    that publishes it.
    """
    row = purpose(kind)
    try:
        parts = urlsplit(url)
        host = parts.hostname or ''
        allowed = host in row.hosts or any(host.endswith(suffix) for suffix in row.suffixes)
        valid = (allowed and parts.scheme == row.scheme and not parts.username
                 and not parts.password and parts.port in row.ports
                 and not parts.fragment and not re.search(r'[\s\\]', url))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise error(row.message)
    return url


def remember(kind, key, produce):
    """``produce()``'s answer for ``key``, kept as long as this purpose's policy says.

    A purpose whose row declares no cache calls ``produce()`` on every call.  Only a returned
    value is stored: an exception is never remembered, so the next call tries again.
    """
    row = purpose(kind)
    if row.cache is None:
        return produce()
    store = cache_store(kind)
    now = time.monotonic()
    kept = store.get(key)
    if kept is not None and now - kept[0] < row.cache.ttl_s:
        return kept[1]
    value = produce()
    if len(store) >= row.cache.max_entries:
        store.clear()
    store[key] = (now, value)
    return value


def _validate_url(url, *, media=False):
    """Refuse any playback URL outside the live-media (or the api) row of the table."""
    return allow('live-media' if media else 'api', url)


def _request(url, payload=None, *, timeout=_TIMEOUT):
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
        with build_opener(_NoRedirect(), HTTPSHandler(context=context)).open(Request(url, data=data, headers=headers), timeout=timeout) as response:
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


def playlist_text(media_url, *, timeout=3):
    """The media playlist behind a resolved URL, for reading its timing tags.

    Same host allowlist and no-redirect policy as every other fetch here; a short
    timeout because this is metadata, never frame data.
    """
    return _request(media_url, timeout=timeout)


def _pdt(text):
    try:
        stamp = text.strip().replace('Z', '+00:00')
        return datetime.datetime.fromisoformat(stamp)
    except (ValueError, AttributeError):
        return None


def playlist_lag(text, *, now=None):
    """How long ago the newest segment of a **live** playlist ended, in seconds.

    ``{'lag_s', 'newest_segment_start', 'newest_segment_end', 'segments', 'live'}``, or
    ``None`` when the playlist cannot say: it is not an HLS media playlist, it is a
    recording (``#EXT-X-PLAYLIST-TYPE`` or ``#EXT-X-ENDLIST`` present), or it carries no
    ``#EXT-X-PROGRAM-DATE-TIME``.  Nothing is inferred from ``#EXT-X-TWITCH-ELAPSED-SECS``,
    which is a stream-relative counter, not a wall clock.

    ``#EXT-X-PROGRAM-DATE-TIME`` is stamped by the broadcaster's encoder, so this measures
    *playlist age* on the encoder's clock: if that clock is wrong, this number moves with
    it.  It is the live edge's age, i.e. the freshest a received frame can be.
    """
    try:
        lines = _playlist(text)
    except TwitchSourceError:
        return None
    if any(line.startswith('#EXT-X-PLAYLIST-TYPE:') or line == '#EXT-X-ENDLIST' for line in lines):
        return None
    started, latest, segments = None, None, 0
    for line in lines:
        if line.startswith('#EXT-X-PROGRAM-DATE-TIME:'):
            started = _pdt(line.split(':', 1)[1])
        elif line.startswith('#EXTINF:') and started is not None:
            try:
                duration = float(line.split(':', 1)[1].split(',')[0])
            except (ValueError, IndexError):
                continue
            segments += 1
            latest = (started, started + datetime.timedelta(seconds=duration))
            started = None
    if latest is None:
        return None
    moment = now if now is not None else time.time()
    end = latest[1].timestamp()
    return {'lag_s': moment - end, 'newest_segment_start': latest[0].isoformat(),
            'newest_segment_end': latest[1].isoformat(), 'segments': segments, 'live': True}


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
