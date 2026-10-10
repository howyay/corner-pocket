"""A Twitch VOD replayed at 1x wall clock, in the shape the live pipeline consumes.

**This is not a live broadcast.**  The live path is externally blocked: `usher.ttvnw.net`
answers `404 {"error":"Can not find channel"}` for every channel without a
client-integrity token, and this repository refuses to acquire one by driving a browser
(no login, no integrity bypass - see ``annotator/twitch_source.py``).  A *recorded* VOD
is reachable anonymously from this machine (verified 2026-09-24, evidence in
``docs/twitch-vod-as-live.md``), and it is a faithful stand-in for demonstrating and
operating near-real-time analysis today: same codec family, same 1280x720, same 30 fps,
delivered at the same wall-clock rate.  Every surface of this module says so - ``kind``
is ``'vod-replay'``, ``live`` is ``False``, and the VOD id, rate, pacing mode and network
state are reported together.

Fetch path (all three steps verified; the endpoints and query shapes mirror Streamlink's
twitch plugin, which is the reference for anonymous web playback):

1. ``https://gql.twitch.tv/gql`` - ``{video(id:"<id>"){playbackAccessToken(params:{platform:
   "web",playerBackend:"mediaplayer",playerType:"site"}){signature value}}}``.  The plain
   query form needs that explicit ``params`` argument; the persisted-query form used by
   the live resolver returns the token under ``data.videoPlaybackAccessToken`` instead.
2. ``https://usher.ttvnw.net/vod/<id>.m3u8?nauth=<value>&nauthsig=<signature>&...`` -
   a master playlist of variants.
3. the best variant at or below ``max_height`` (720p), which is the media playlist the
   decoder opens.

Signed URLs and playback tokens are private, short-lived decoder inputs: they are never
logged, never returned by ``evidence()``, and never persisted.

Capture contract (matches what ``annotator/live_processing.py`` expects from an injected
``capture_factory``, without that file being touched)::

    capture = VodRealtimeCapture(media_url, vod_id=..., rate=1.0, start_s=0.0)
    capture.isOpened() -> True
    ok, frame = capture.read()          # blocks until this frame's wall-clock slot
    capture.get(cv2.CAP_PROP_FPS) / CAP_PROP_POS_FRAMES / CAP_PROP_POS_MSEC
    capture.state()  -> {'kind': 'vod-replay', 'live': False, 'drift_s': ...}
    capture.release()

Pacing is authoritative: ``read()`` holds one frame per ``1/fps`` seconds of wall clock at
``rate=1.0`` and *drops* source frames (counting them) when the consumer has fallen
behind, so the video position tracks wall clock instead of drifting.  A consumer that is
slow loses frames; it never falls behind in time.
"""
import json
import math
from pathlib import Path
import re
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler

from annotator import twitch_source as live

#: The live resolver's host allowlists and anonymous web client id are the single source
#: of truth for which hosts this machine will talk to; the VOD path adds no new host.
_VOD_TOKEN_QUERY = (
    '{ video(id: "%s") { id title lengthSeconds createdAt owner { login } '
    'playbackAccessToken(params: {platform: "web", playerBackend: "mediaplayer", '
    'playerType: "site"}) { signature value } } }')
_VIDEO_QUERY = ('{ video(id: "%s") { id title lengthSeconds createdAt owner { login } } }')
# Every kind of video the channel publishes, not just the two-week broadcast archive. Measured
# 2026-10-03 on the club's own channel: `type: ARCHIVE` returns 2 VODs, while the channel holds 31
# - the seven multi-hour "(Record) YYYYMMDD" files it keeps each night are HIGHLIGHTs, and the
# 43-second to 6-minute clips are HIGHLIGHTs too. `broadcastType` carries that distinction,
# `pageInfo.hasNextPage` says whether the window cut the list short, and one page of 60 held the
# whole history (hasNextPage: false), so nothing is paginated.
_CHANNEL_QUERY = (
    '{ user(login: "%s") { login videos(first: %d) '
    '{ edges { node { id title lengthSeconds createdAt broadcastType '
    'previewThumbnailURL(width: %d, height: %d) } } pageInfo { hasNextPage } } } }')
#: One VOD's preview picture. The listing carries the same field, but a thumbnail request
#: arrives as (channel, id) and must be resolved again; the host is validated before the
#: bytes are fetched, so a tampered index can never point this server at another host.
_THUMB_QUERY = '{ video(id: "%s") { id previewThumbnailURL(width: %d, height: %d) } }'
#: 320x180 previews are ~10-25 kB; the limit is a ceiling, not an expectation.
_THUMB_BYTES = 400000
_THUMB_WIDTH = 320
_THUMB_HEIGHT = 180

#: Media-playlist fetch limits: a long VOD playlist is large, and only its head is needed.
_PLAYLIST_BYTES = 200000
_HEAD_BYTES = 4000


class TwitchVodError(RuntimeError):
    """Safe public error: contains no upstream body, playback token, or signed URL."""


#: This module declares no host and keeps no second allowlist.  The VOD media row and the
#: preview-picture row of the one fetch table are declared in ``annotator/twitch_source.py``
#: (:func:`live.declare`), each with its own pinned hosts, its own transport rule, and its
#: own refusal sentence, so a host added for one purpose there cannot widen another.


def _validate_media(url):
    """HTTPS media URL on Twitch's own CDN (or the pinned VOD distribution) only."""
    return live.allow('vod-media', url, error=TwitchVodError)


def _validate_thumb(url):
    """HTTPS preview picture on Twitch's own static image CDN only."""
    return live.allow('thumb', url, error=TwitchVodError)


def vod_id_of(argument):
    """``1000000001`` / ``v1000000001`` / ``https://www.twitch.tv/videos/1000000001`` -> id."""
    if isinstance(argument, int) and not isinstance(argument, bool) and argument > 0:
        return str(argument)
    if not isinstance(argument, str):
        raise TwitchVodError('Expected a Twitch VOD id or https://www.twitch.tv/videos/<id> URL')
    text = argument.strip().rstrip('/')
    if text.startswith('https://www.twitch.tv/videos/'):
        text = text[len('https://www.twitch.tv/videos/'):]
    text = text.lstrip('vV')
    if not text.isdigit() or int(text) <= 0:
        raise TwitchVodError('Expected a Twitch VOD id or https://www.twitch.tv/videos/<id> URL')
    return text


def _raw(url, payload=None, *, timeout=12, limit=_PLAYLIST_BYTES):
    """One request with its **raw** status and body, so a probe can report both.

    Redirects are refused and the host is validated against the row of the fetch table that
    names this call's purpose - ``api`` for a payload call (``gql.twitch.tv`` /
    ``usher.ttvnw.net``), ``vod-media`` for a media call (``*.ttvnw.net`` /
    ``*.twitchcdn.net``, plus the pinned VOD distribution) - so a signed URL can never be
    redirected off-Twitch.  A transport failure is returned, not raised, with the exception
    *type* only - never the message, which can contain a signed URL.
    """
    live._validate_url(url) if payload is not None else _validate_media(url)
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'}
    data = None
    if payload is not None:
        headers.update({'Client-ID': live._CLIENT_ID, 'Content-Type': 'application/json'})
        data = json.dumps(payload).encode('utf-8')
    context = ssl.create_default_context()
    if Path('/etc/ssl/certs/ca-certificates.crt').is_file():
        context.load_verify_locations('/etc/ssl/certs/ca-certificates.crt')
    opener = build_opener(live._NoRedirect(), HTTPSHandler(context=context))
    try:
        with opener.open(Request(url, data=data, headers=headers), timeout=timeout) as response:
            body = response.read(limit + 1)
            return {'status': response.status, 'body': body.decode('utf-8-sig', 'replace')[:limit],
                    'transport': None}
    except HTTPError as exc:
        try:
            body = exc.read(limit).decode('utf-8-sig', 'replace')
        except Exception:
            body = ''
        return {'status': exc.code, 'body': body, 'transport': None}
    except (URLError, OSError) as exc:
        return {'status': None, 'body': '', 'transport': type(exc).__name__}


def _raw_bytes(url, *, timeout=10, limit=_THUMB_BYTES):
    """One **binary** request, for pictures rather than documents.

    The same discipline as :func:`_raw` - redirects refused, the host validated against the
    ``thumb`` row of the fetch table before anything is fetched, a transport failure reported
    as its exception type only - except that the body is returned as bytes: ``_raw`` decodes
    to text, which a JPEG cannot survive.
    """
    _validate_thumb(url)
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'image/*'}
    context = ssl.create_default_context()
    if Path('/etc/ssl/certs/ca-certificates.crt').is_file():
        context.load_verify_locations('/etc/ssl/certs/ca-certificates.crt')
    opener = build_opener(live._NoRedirect(), HTTPSHandler(context=context))
    try:
        with opener.open(Request(url, headers=headers), timeout=timeout) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                return {'status': None, 'body': b'', 'transport': 'TooLarge'}
            return {'status': response.status, 'body': body, 'transport': None}
    except HTTPError as exc:
        return {'status': exc.code, 'body': b'', 'transport': None}
    except (URLError, OSError) as exc:
        return {'status': None, 'body': b'', 'transport': type(exc).__name__}


#: Resolved preview pictures, so a screen of rows costs one API call per broadcast and a
#: reloaded page costs none.  The ``thumb`` row of the fetch table owns the TTL and the
#: ceiling, and clears wholesale: a preview is a small image and a stale entry is worth less
#: than the bookkeeping of evicting one precisely.  This name is that row's own store.
_THUMB_CACHE = live.cache_store('thumb')


def _fetch_thumbnail(vod, *, timeout):
    """One gql call and one binary fetch for one broadcast; the cache is the caller's."""
    document = gql(_THUMB_QUERY % (vod, _THUMB_WIDTH, _THUMB_HEIGHT), timeout=timeout)
    video = (document.get('data') or {}).get('video')
    if not isinstance(video, dict):
        raise TwitchVodError('Twitch has no such video')
    url = _validate_thumb(video.get('previewThumbnailURL') or '')
    result = _raw_bytes(url, timeout=timeout)
    if result['transport'] is not None:
        raise TwitchVodError('Twitch thumbnail request failed; check network and TLS connectivity')
    if result['status'] != 200:
        raise TwitchVodError('Twitch thumbnail request failed (HTTP %s)' % result['status'])
    body = result['body']
    if not isinstance(body, (bytes, bytearray)) or len(body) < 128:
        raise TwitchVodError('Twitch returned an empty preview picture')
    return 'image/jpeg', bytes(body)


def vod_thumbnail(vod_id, *, timeout=10):
    """One broadcast's preview picture as ``(content_type, bytes)``, or a safe error."""
    vod = vod_id_of(vod_id)
    return live.remember('thumb', vod, lambda: _fetch_thumbnail(vod, timeout=timeout))


def gql(query, *, timeout=12):
    """POST one GraphQL query and return the parsed document, or a safe error."""
    result = _raw('https://gql.twitch.tv/gql', {'query': query}, timeout=timeout)
    if result['transport'] is not None:
        raise TwitchVodError('Twitch API request failed; check network and TLS connectivity')
    if result['status'] != 200:
        raise TwitchVodError('Twitch API request failed (HTTP %s)' % result['status'])
    try:
        return json.loads(result['body'])
    except ValueError:
        raise TwitchVodError('Twitch returned an invalid API response') from None


def channel_recent_vods(channel, limit=3):
    """The most recent archived broadcasts of ``channel``, newest first.

    Each row carries ``thumbnail``: the preview URL *validated* against the static image
    CDN's allowlist, or ``None`` when Twitch sent nothing usable, plus ``broadcast_type``
    (Twitch's own ARCHIVE / HIGHLIGHT / UPLOAD) so the console can name what it lists. Twitch
    serves this channel as a single window - an ``after:`` cursor returns the same page - so
    the window is ``first:`` alone and nothing here paginates.
    """
    if not isinstance(channel, str) or not re.fullmatch(r'[a-z0-9_]{1,25}', channel):
        raise TwitchVodError('Expected a canonical Twitch channel login')
    # 100 is Twitch's own ceiling for one videos page; vod_import.RECENT_LIMIT is the window
    # this box asks for. There is no second page to walk (see that constant's note).
    document = gql(_CHANNEL_QUERY % (channel, max(1, min(int(limit), 100)), _THUMB_WIDTH, _THUMB_HEIGHT))
    user = (document.get('data') or {}).get('user')
    if user is None:
        raise TwitchVodError('Twitch has no such channel')
    edges = ((user.get('videos') or {}).get('edges')) or []
    rows = []
    for node in (edge.get('node') or {} for edge in edges):
        if not node.get('id'):
            continue
        try:
            thumbnail = _validate_thumb(node.get('previewThumbnailURL'))
        except TwitchVodError:
            thumbnail = None
        rows.append(dict(id=node.get('id'), title=node.get('title'), length_s=node.get('lengthSeconds'),
                         created_at=node.get('createdAt'), channel=user.get('login'), thumbnail=thumbnail,
                         broadcast_type=node.get('broadcastType')))
    return rows


def vod_info(vod_id, *, strict=True):
    """Title, length and channel of a VOD. No token, no signature, no media URL."""
    vod = vod_id_of(vod_id)
    result = _raw('https://gql.twitch.tv/gql', {'query': _VIDEO_QUERY % vod})
    if result['transport'] is not None:
        raise TwitchVodError('Twitch API request failed; check network and TLS connectivity')
    video = {}
    errors = None
    if result['status'] == 200:
        try:
            document = json.loads(result['body'])
            video = (document.get('data') or {}).get('video') or {}
            errors = document.get('errors')
        except ValueError:
            errors = 'invalid JSON'
    info = {'vod_id': vod, 'status': result['status'], 'errors': errors, 'id': video.get('id'),
            'title': video.get('title'), 'length_s': video.get('lengthSeconds'),
            'created_at': video.get('createdAt'), 'channel': (video.get('owner') or {}).get('login')}
    if strict and not info['id']:
        raise TwitchVodError('Twitch returned no such VOD (HTTP %s)' % result['status'])
    return info


def vod_token(vod_id, *, strict=True, timeout=12):
    """The VOD's anonymous ``playbackAccessToken``, with its raw request status.

    Returns ``signature``/``value`` for the usher call; ``evidence()`` strips them.
    ``strict=False`` returns the failure instead of raising, which is what the probe
    needs in order to record what Twitch actually said.
    """
    vod = vod_id_of(vod_id)
    result = _raw('https://gql.twitch.tv/gql', {'query': _VOD_TOKEN_QUERY % vod}, timeout=timeout)
    document = {}
    error = None
    if result['transport'] is not None:
        error = 'transport:' + result['transport']
    elif result['status'] != 200:
        error = 'HTTP %s' % result['status']
    else:
        try:
            document = json.loads(result['body'])
        except ValueError:
            error = 'invalid JSON'
    data = document.get('data') or {}
    video = data.get('video') or {}
    token = video.get('playbackAccessToken') or {}
    output = {'vod_id': vod, 'status': result['status'], 'transport': result['transport'],
              'errors': document.get('errors') or (None if error is None else error),
              'data_keys': sorted(data), 'video_keys': sorted(video),
              'signature': token.get('signature') if isinstance(token.get('signature'), str) else None,
              'value': token.get('value') if isinstance(token.get('value'), str) else None,
              'title': video.get('title'), 'length_s': video.get('lengthSeconds'),
              'channel': (video.get('owner') or {}).get('login')}
    output['ok'] = bool(output['signature'] and output['value'])
    if strict and not output['ok']:
        raise TwitchVodError('Twitch returned no playback token for VOD %s (HTTP %s)'
                             % (vod, result['status']))
    return output


def playlist_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def vod_variants(master_url, master_text):
    """``[{height, bandwidth, fps, url}]`` from a VOD master playlist, in file order."""
    lines = playlist_lines(master_text)
    if not lines or lines[0] != '#EXTM3U':
        raise TwitchVodError('Twitch returned an invalid VOD playlist')
    variants = []
    for index, line in enumerate(lines[:-1]):
        if not line.startswith('#EXT-X-STREAM-INF:'):
            continue
        bandwidth = re.search(r'(?:[:,])BANDWIDTH=(\d+)(?:,|$)', line)
        resolution = re.search(r'(?:[:,])RESOLUTION=\d+x(\d+)(?:,|$)', line)
        framerate = re.search(r'(?:[:,])FRAME-RATE=([\d.]+)(?:,|$)', line)
        if bandwidth and resolution and not lines[index + 1].startswith('#'):
            variants.append({'height': int(resolution[1]), 'bandwidth': int(bandwidth[1]),
                             'fps': float(framerate[1]) if framerate else None,
                             'url': _validate_media(urljoin(master_url, lines[index + 1]))})
    return variants


def resolve_vod(vod_id, *, max_height=720, timeout=15):
    """Resolve a VOD id to its playable media playlist, anonymously.

    Returns the master's status, every variant (heights/bandwidths only - the variant
    URLs stay inside the returned dict and are stripped by ``evidence()``), the chosen
    media URL, and the media playlist's own head facts.  Nothing here claims the stream
    is live: a VOD playlist is ``EVENT`` or ``VOD`` typed, not ``None``.
    """
    token = vod_token(vod_id, timeout=timeout)
    master_url = 'https://usher.ttvnw.net/vod/%s.m3u8?%s' % (token['vod_id'], urlencode({
        'nauth': token['value'], 'nauthsig': token['signature'], 'allow_source': 'true',
        'playlist_include_framerate': 'true', 'supported_codecs': 'avc1'}))
    master = _raw(master_url, timeout=timeout)
    if master['transport'] is not None:
        raise TwitchVodError('Twitch VOD playlist request failed; check network and TLS connectivity')
    if master['status'] != 200:
        raise TwitchVodError('Twitch VOD playlist request failed (HTTP %s)' % master['status'])
    variants = vod_variants(master_url, master['body'])
    if not variants:
        raise TwitchVodError('Twitch returned no playable VOD variant')
    modest = [variant for variant in variants if variant['height'] <= max_height]
    chosen = max(modest or variants, key=lambda variant: (variant['height'], variant['bandwidth']))
    head = _raw(chosen['url'], timeout=timeout, limit=_HEAD_BYTES)
    if head['transport'] is not None:
        raise TwitchVodError('Twitch VOD media playlist request failed; check network and TLS connectivity')
    if head['status'] != 200:
        raise TwitchVodError('Twitch VOD media playlist request failed (HTTP %s)' % head['status'])
    lines = playlist_lines(head['body'])
    if not lines or lines[0] != '#EXTM3U':
        raise TwitchVodError('Twitch returned an invalid VOD media playlist')
    playlist_type = next((line.split(':', 1)[1] for line in lines
                          if line.startswith('#EXT-X-PLAYLIST-TYPE:')), None)
    target_duration = next((float(line.split(':', 1)[1]) for line in lines
                            if line.startswith('#EXT-X-TARGETDURATION:')), None)
    if playlist_type not in ('EVENT', 'VOD'):
        raise TwitchVodError('Twitch returned a playlist that is not a finished VOD')
    return {'vod_id': token['vod_id'], 'title': token['title'], 'length_s': token['length_s'],
            'channel': token['channel'], 'master_status': master['status'],
            'media_url': chosen['url'], 'variant': dict(chosen, url=None),
            'variants': [dict(variant, url=None) for variant in variants],
            'playlist': {'type': playlist_type, 'target_duration_s': target_duration,
                         'segments_in_head': sum(1 for line in lines if line.startswith('#EXTINF:')),
                         'has_endlist': any(line == '#EXT-X-ENDLIST' for line in lines)}}


def _cv2():
    """OpenCV is needed by the capture, not by the fetch/probe half of this module."""
    import cv2
    return cv2


def _open(media, *, open_timeout_ms=15000, read_timeout_ms=8000):
    cv2 = _cv2()
    return cv2.VideoCapture(media, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, open_timeout_ms,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, read_timeout_ms,
    ])


class VodRealtimeCapture:
    """A VOD as a capture: real time in, frames out, drift corrected by dropping.

    The wall clock is the authority.  ``read()`` returns the frame whose video time is
    ``start_s + rate x (wall clock since open)``: it *sleeps* while the video is ahead of
    that line and *drops* source frames (counting them) while it is behind, so a slow
    consumer loses frames instead of falling further behind.  At ``rate=1.0`` that is one
    frame per source frame period, which is what makes a recorded VOD indistinguishable
    from a live feed for a consumer - while ``state()`` keeps saying exactly what it is:

        {'kind': 'vod-replay', 'live': False, 'vod_id': ..., 'pacing': 'wall-clock',
         'network': 'hls'|'file', 'rate': 1.0, 'wall_s': ..., 'video_s': ...,
         'expected_video_s': ..., 'drift_s': ..., 'frames_served': ...,
         'frames_dropped': ..., 'read_failures': ...}

    The OpenCV-compatible surface (``isOpened``/``read``/``get``/``release``) is what
    ``annotator/live_processing.py`` consumes from an injected ``capture_factory``; this
    class exists so that file needs no change to gain a real-time VOD input.

    ``max_catchup_s`` bounds how much source material one ``read`` may discard (default
    1 s): a consumer that stalls for a minute recovers over the following reads instead of
    blocking inside one call, and ``state()['drift_s']`` shows the debt while it does.
    """

    def __init__(self, media, *, vod_id=None, rate=1.0, start_s=0.0, fps=None,
                 clock=time.monotonic, sleep=time.sleep, capture=None, network=None,
                 max_catchup_s=1.0, open_timeout_ms=15000, read_timeout_ms=8000):
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
            raise TwitchVodError('rate must be a positive number')
        if isinstance(start_s, bool) or not isinstance(start_s, (int, float)) or start_s < 0:
            raise TwitchVodError('start_s must be a non-negative number')
        if isinstance(max_catchup_s, bool) or not isinstance(max_catchup_s, (int, float)) or max_catchup_s <= 0:
            raise TwitchVodError('max_catchup_s must be a positive number')
        self.media = media
        self.vod_id = vod_id
        self.rate = float(rate)
        self.start_s = float(start_s)
        self._clock, self._sleep = clock, sleep
        self._capture = capture if capture is not None else _open(
            media, open_timeout_ms=open_timeout_ms, read_timeout_ms=read_timeout_ms)
        self._network = network or ('hls' if isinstance(media, str) and media.startswith('https://') else 'file')
        self._fps = float(fps) if fps else self._read_fps()
        self._frame_period = 1.0 / self._fps / self.rate
        self._max_catchup_frames = max(1, int(round(self._fps * self.rate * max_catchup_s)))
        self._start_frame = 0
        if self.start_s:
            self._capture.set(_cv2().CAP_PROP_POS_MSEC, self.start_s * 1000.0)
            self._start_frame = int(round(self.start_s * self._fps))
        self._wall_start = self._clock()
        self._source_frames = 0
        self._served = 0
        self._dropped = 0
        self._read_failures = 0

    def _read_fps(self):
        cv2 = _cv2()
        try:
            fps = float(self._capture.get(cv2.CAP_PROP_FPS))
        except Exception:
            fps = 0.0
        return fps if math.isfinite(fps) and 0 < fps <= 240 else 30.0

    # --- the capture contract annotator/live_processing.py consumes ---------------

    def isOpened(self):
        try:
            return bool(self._capture.isOpened())
        except Exception:
            return False

    def read(self):
        """Wait for this frame's wall-clock slot, or skip ahead if the consumer is late."""
        target = self.start_s + (self._clock() - self._wall_start) * self.rate
        position = self.start_s + self._source_frames / self._fps
        if position < target - self._frame_period:
            budget = self._max_catchup_frames
            while position < target - self._frame_period and budget > 0:
                ok, _ = self._capture.read()
                if not ok:
                    self._read_failures += 1
                    return False, None
                self._source_frames += 1
                self._dropped += 1
                budget -= 1
                position = self.start_s + self._source_frames / self._fps
        elif position > target:
            self._sleep(position - target)
        ok, frame = self._capture.read()
        if ok:
            self._source_frames += 1
            self._served += 1
        else:
            self._read_failures += 1
        return ok, frame

    def get(self, prop):
        cv2 = _cv2()
        if prop == cv2.CAP_PROP_FPS:
            return self._fps
        if prop == cv2.CAP_PROP_POS_FRAMES:
            return float(self._start_frame + self._source_frames)
        if prop == cv2.CAP_PROP_POS_MSEC:
            return (self.start_s + self._source_frames / self._fps) * 1000.0
        return self._capture.get(prop)

    def set(self, prop, value):
        return self._capture.set(prop, value)

    def release(self):
        try:
            self._capture.release()
        finally:
            self._released_at = self._clock()

    # --- honest self-description --------------------------------------------------

    def state(self):
        now = self._clock()
        wall = max(0.0, now - self._wall_start)
        expected = self.start_s + wall * self.rate
        position = self.start_s + self._source_frames / self._fps
        return {'kind': 'vod-replay', 'live': False, 'vod_id': self.vod_id,
                'network': self._network, 'rate': self.rate, 'pacing': 'wall-clock',
                'start_s': self.start_s, 'fps': self._fps,
                'wall_s': round(wall, 3), 'video_s': round(position, 3),
                'expected_video_s': round(expected, 3), 'drift_s': round(position - expected, 3),
                'frames_served': self._served, 'frames_dropped': self._dropped,
                'read_failures': self._read_failures, 'opened': self.isOpened()}



def evidence(result):
    """The printable, redacted view of any result above: no token, no signature, no URL.

    Signed media URLs are reduced to their host and length, and tokens to their lengths,
    because both are private decoder inputs (the usher body even echoes the requesting IP).
    """
    if not isinstance(result, dict):
        return result
    redacted = {}
    for key, value in result.items():
        if key in ('signature', 'value', 'nauth', 'nauthsig'):
            redacted[key + '_len'] = len(value) if isinstance(value, str) else None
        elif key in ('media_url', 'url') and isinstance(value, str) and value:
            redacted[key + '_host'] = urlsplit(value).hostname
            redacted[key + '_len'] = len(value)
        elif isinstance(value, dict):
            redacted[key] = evidence(value)
        elif isinstance(value, list):
            redacted[key] = [evidence(item) for item in value]
        else:
            redacted[key] = value
    return redacted
