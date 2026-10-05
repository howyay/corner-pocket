"""Persistent, server-authoritative pool operations; standard library only."""
import copy
import json
import os
import math
import random
import re
from urllib.parse import urlsplit
from pathlib import Path
import tempfile
import threading
from datetime import datetime, timezone
from uuid import uuid4


class ConflictError(ValueError):
    """The caller must reload before retrying a stale mutation."""


def uid():
    return uuid4().hex


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer from {low} to {high}')
    return value


def optional(payload, key, default):
    """A missing, null or blank field was not collected: keep the default."""
    value = payload.get(key)
    return default if value is None or value == '' else value


def text(value, name, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f'{name} must contain 1–{maximum} characters')
    return value.strip()


def seconds(value, name):
    """A position in a broadcast: whole seconds, 0 or more (the rule src/datasets.py uses)."""
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a whole number of seconds, 0 or more')
    return value


def vod_id(value):
    """The numeric id of a Twitch VOD argument, parsed by the source module's own rule
    (annotator/twitch_vod_source.py): the action layer keeps no second spelling of it and
    never touches the network."""
    from annotator.twitch_vod_source import TwitchVodError, vod_id_of
    try:
        return vod_id_of(value)
    except TwitchVodError as error:
        raise ValueError(str(error)) from error


def instant(value, name):
    """An ISO-8601 instant, spelled the way the Twitch API spells it
    (`2026-10-02T23:07:00Z`).  The console passes the field through untouched, so what is
    enforced here is the format, not the value."""
    stamp = value.strip() if isinstance(value, str) else ''
    if not stamp or len(stamp) > 40:
        raise ValueError(f'{name} must be an ISO-8601 instant')
    try:
        datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError(f'{name} must be an ISO-8601 instant') from error
    return stamp


def name_key(name):
    """The key under which two player names are the same name: the rule every name
    check here applies (casefold of the trimmed name). The database stores it in
    players.name_key and enforces uniqueness on it, so both stores accept exactly the
    same names."""
    return name.strip().casefold()


# Typed stand-ins for "no opponent": the draw records a bye itself, so a guest
# with one of these names would be a fake person (R5).
PLACEHOLDER_NAMES = {'na', 'n/a', 'bye', 'tbd', '轮空', '輪空'}


def tournament():
    return dict(id=uid(), name='', format='singles', tables=1, raceTo=1,
                entrants=[], matches=[], status='registration')


def default_name(now=None):
    """The name the Set up form displays before anyone types one (autoEventName, EN)."""
    now = now or datetime.now().astimezone()
    day = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[now.weekday()]
    return f'8-Ball Open · {day} {now.month}/{now.day}'


def normalise(state):
    """Every document enters through here, whichever store hands it over: the three keys a
    build before round 11 does not have, and the links the import lines already in the
    document imply.  Read-time, idempotent and clock-free - a read writes nothing, and the
    next write persists what the read derived (Operations._commit).  The JSON store calls it
    from Operations._load, the Postgres store from PostgresStore._document, so one club
    answers the same question the same way on either store."""
    state.setdefault('events', [])
    state.setdefault('vods', [])
    state.setdefault('links', [])
    Operations._adopt_sources(state)
    return state


class Operations:
    # Share a lock across backend instances for the same store in this process.
    _locks = {}
    _locks_guard = threading.Lock()

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / 'out' / 'corner-pocket' / 'state.json'
        with self._locks_guard:
            self.lock = self._locks.setdefault(self.path, threading.RLock())

    def _load(self):
        if self.path.exists():
            return normalise(json.loads(self.path.read_text()))
        return dict(revision=0, players=[], tournament=tournament(), history=[], vods=[], links=[],
                    settings=dict(shotClock=30, autoFrame=False, clothColor='#1d5c44', lampGlow=0.22,
                                  showDiamonds=True, publicBoard=True), notes=[], sources=[dict(id=uid(), url='https://www.twitch.tv/examplechannel', kind='channel', channel='examplechannel')], events=[])

    # -- Broadcasts and the events they cover (round 11) ----------------------------------
    # The relation is many-to-many, so it is one link row per pair and never a list on
    # either side: one broadcast can cover several events (a night that ran past a restart,
    # two events in one stream) and one event can be covered by several broadcasts (two
    # cameras, a stream and a phone).  `vods` keeps each broadcast's own metadata, because
    # Twitch forgets broadcasts and this club must not: a link outlives the VOD it names.
    # `history[i].source` stays exactly what event_backfill wrote - the audit line of an
    # import - and _adopt_sources materialises a link for it, so both directions of the
    # relation are read from `links` alone.
    def _vod_of(self, s, vod):
        """The `vods` row for this broadcast, created empty when it is new."""
        row = next((v for v in s['vods'] if v['id'] == vod), None)
        if row is None:
            row = dict(id=vod, title='', channel='', length_s=0, created_at='')
            s['vods'].append(row)
        return row

    def _vod_metadata(self, row, p):
        """Refresh only the fields the caller actually sent: the picker knows a
        broadcast's title and length, an import knows its range, and neither may blank
        what the other learned."""
        if 'title' in p:
            row['title'] = text(p.get('title'), 'title', 200) if str(p.get('title') or '').strip() else ''
        if 'channel' in p:
            channel = str(p.get('channel') or '').strip().lower()
            if channel and not re.fullmatch(r'[a-z0-9_]{1,25}', channel):
                raise ValueError('channel must be a Twitch channel login')
            row['channel'] = channel
        if 'length_s' in p:
            row['length_s'] = integer(p.get('length_s'), 0, 604800, 'length_s')
        if 'created_at' in p:
            row['created_at'] = instant(p.get('created_at'), 'created_at')

    def _event_of(self, s, event):
        night = next((n for n in [s['tournament'], *s['history']] if n['id'] == event), None)
        if night is None:
            raise ValueError('Unknown event')
        return night

    def _link_vod(self, s, p):
        """Attach one broadcast to one event.  Idempotent: the pair is the key, so a
        second link of the same pair refreshes the metadata instead of making a row."""
        vod = vod_id(p.get('vodId'))
        event = text(p.get('eventId'), 'eventId', 120)
        self._event_of(s, event)
        start, end = p.get('startS'), p.get('endS')
        if (start is None) != (end is None):
            raise ValueError('A range needs both startS and endS')
        if start is not None:
            start = seconds(start, 'startS')
            end = seconds(end, 'endS')
            if end <= start:
                raise ValueError('endS must be after startS')
        self._vod_metadata(self._vod_of(s, vod), p)
        link = next((l for l in s['links'] if l['vodId'] == vod and l['eventId'] == event), None)
        if link is None:
            s['links'].append(dict(vodId=vod, eventId=event, startS=start, endS=end, at=timestamp()))
        elif start is not None:
            # a link's range belongs to whoever knows it: an import writes it, the picker
            # leaves it alone, and a wrong one is cleared by unlink then link again.
            link.update(startS=start, endS=end)

    @staticmethod
    def _source_vod(night):
        """The broadcast an import's own line names, parsed the way that line is parsed."""
        try:
            return vod_id((night.get('source') or {}).get('vodId'))
        except ValueError:
            return ''

    def _unlink_vod(self, s, p):
        vod = vod_id(p.get('vodId'))
        event = text(p.get('eventId'), 'eventId', 120)
        night = self._event_of(s, event)
        link = next((l for l in s['links'] if l['vodId'] == vod and l['eventId'] == event), None)
        if link is None:
            raise ValueError('Unknown link')
        if self._source_vod(night) == vod:
            # the import's own record of the night is evidence, not a choice: the line is
            # still in the event, so the next read would materialise the link again. The
            # way to drop it is to change the event (delete the mistake, or hide it).
            raise ValueError("This broadcast is this event's own import record; delete or hide the event instead")
        s['links'].remove(link)

    def _drop_links(self, s, event):
        """An event that stops existing takes no links with it: the relation never has a
        dangling end (a deleted event, or a live event replaced before it had a draw)."""
        s['links'] = [l for l in s['links'] if l['eventId'] != event]

    @staticmethod
    def _adopt_sources(state):
        """Read-time, idempotent, clock-free: every `source` an import wrote becomes one
        link row, so a night's broadcasts and a broadcast's nights come from one table.
        Nothing here writes to `source` and nothing here reads the network."""
        for night in [state['tournament'], *state['history']]:
            source = night.get('source') or {}
            vod = Operations._source_vod(night)
            if not vod:
                continue                  # no line, or one an older build wrote in its own spelling
            if not any(v['id'] == vod for v in state['vods']):
                state['vods'].append(dict(id=vod, title=str(source.get('title') or '')[:200],
                                          channel='', length_s=0, created_at=''))
            if any(l['vodId'] == vod and l['eventId'] == night['id'] for l in state['links']):
                continue
            start, end = source.get('startS'), source.get('endS')
            if type(start) is not int or type(end) is not int or start < 0 or end <= start:
                start = end = None
            at = str((night.get('signOff') or {}).get('at') or night.get('archivedAt') or '')
            state['links'].append(dict(vodId=vod, eventId=night['id'], startS=start, endS=end, at=at))

    def get(self):
        with self.lock:
            return self._load()

    def post(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('JSON object required')
        with self.lock:
            state = self._load()
            if type(payload.get('revision')) is not int:
                raise ValueError('integer revision required')
            if payload['revision'] != state['revision']:
                raise ConflictError('State changed; reload before retrying')
            if payload.get('action') in ('tournament_start', 'tournament_new'):
                # R2: an event that is drawn or archived is never nameless; the
                # server fills the default the form displays (the audit reads it).
                t = state['tournament']
                if not t['name'].strip() and (payload['action'] == 'tournament_start' or t['entrants'] or t['matches']):
                    t['name'] = default_name()
            context = self._event_context(state, payload)
            self._apply(state, payload)
            if payload.get('action') not in ('tournament_new', 'tournament_delete'):
                context.update(self._event_context(state, payload))
            return self._commit(state, payload['action'], context)

    def enroll_player(self, player, context):
        """Add a player confirmed from the footage: one read-modify-write under the
        store lock, at the CURRENT revision, never a stale document written over it.

        `player` is the roster record the enrolment planned; it is added only when its
        id is not on the roster yet (an existing regular gains faces, not a row), and
        a name that another player already holds (casefold) is refused, the rule
        `player_save` enforces. The event is appended to the same log."""
        with self.lock:
            state = self._load()
            if not any(existing.get('id') == player['id'] for existing in state['players']):
                name = text(player.get('name'), 'name')
                if any(existing['name'].casefold() == name.casefold() for existing in state['players']):
                    raise ValueError('Player name already exists')
                # the defaults player_save gives a new regular: the plan carries only
                # {id, name} when it matched a regular who has since been deleted
                state['players'].append({'joinedAt': timestamp(), 'rating': 0, 'status': 'Active',
                                         **player, 'name': name})
            return self._commit(state, 'player_enroll_from_tracklet', context)

    def _commit(self, state, action, context):
        """Advance the revision, log the event, write the file atomically."""
        # a write persists the relation it can derive, so the next reader does not have to
        self._adopt_sources(state)
        state['revision'] += 1
        state['events'] = (state['events'] + [dict(id=uid(), createdAt=timestamp(),
            revision=state['revision'], action=action, context=context)])[-500:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.state-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream, indent=2, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return state

    @staticmethod
    def _event_context(state, payload):
        """Whitelist domain identity only: never copy request or note contents."""
        action = payload.get('action')
        t = state['tournament']
        context = {}
        groups = [('player_', state['players']), ('entrant_', t['entrants']),
                  ('match_', t['matches']), ('source_', state.get('sources', [])),
                  ('note_', state['notes'])]
        if not isinstance(action, str):
            return context
        if action in ('revival_draw', 'revival_undo'):
            # the whole draw is audited, so anyone can re-run it: seed, sorted pool, pick, slot
            return dict(t['revival']) if t.get('revival') else context
        if action in ('pair_draw', 'pair_accept') and t.get('pairing'):
            # R3: the seed and the teams it made (names only; pool order is sign-up order)
            return dict(seed=t['pairing']['seed'],
                        teams=[' / '.join(m['name'] for m in team) for team in t['pairing']['teams']])
        if action in ('tournament_rename', 'tournament_delete', 'tournament_hide'):
            night = next((n for n in [t] + state['history'] if n['id'] == payload.get('id')), None)
            if night and action == 'tournament_hide' and 'hidden' in night:
                return dict(id=night['id'], name=night['name'], hidden=night['hidden'])
            return dict(id=night['id'], name=night['name']) if night else context
        if action in ('vod_link', 'vod_unlink'):
            # the audit line names the pair a person made: the event, and the broadcast
            vod, event = payload.get('vodId'), payload.get('eventId')
            night = next((n for n in [t] + state['history'] if n['id'] == event), None)
            context = dict(vodId=str(vod)) if isinstance(vod, str) else {}
            if night is not None:
                context.update(id=night['id'], name=night['name'])
            return context
        if action == 'event_backfill':
            # 7.6: the audit line of a backfill names the night it wrote and the broadcast it
            # came from, read back from the store rather than copied from the request.
            source = payload.get('source') if isinstance(payload.get('source'), dict) else {}
            night = next((n for n in reversed(state['history'])
                          if (n.get('source') or {}).get('datasetId') == source.get('datasetId')), None)
            if night is None:
                return dict(vodId=source['vodId']) if isinstance(source.get('vodId'), str) else context
            return dict(id=night['id'], name=night['name'], vodId=night['source'].get('vodId'),
                        datasetId=night['source'].get('datasetId'))
        if action.startswith('tournament_'):
            return dict(id=t['id'], name=t['name'])
        if action == 'guest_promote':
            name = payload.get('name')
            if isinstance(name, str):
                matches = [p for p in state['players'] if p['name'].casefold() == name.strip().casefold()]
                if matches:
                    return dict(id=matches[0]['id'], name=matches[0]['name'])
            return context
        for prefix, items in groups:
            if not action.startswith(prefix):
                continue
            item = next((item for item in items if item['id'] == payload.get('id')), None)
            if item is None and not payload.get('id') and items:
                item = items[-1]
            if item:
                context['id'] = item['id']
                if prefix == 'player_':
                    context['name'] = item['name']
            break
        return context

    @staticmethod
    def _find(items, ident):
        item = next((item for item in items if item['id'] == ident), None)
        if item is None:
            raise ValueError('Unknown id')
        return item

    @classmethod
    def _person(cls, s, t, member, team=()):
        """One registrant, by the entrant rules: a known active regular by id, or a guest
        with a real name; nobody twice across tonight's entrants, the solo pool and `team`."""
        if not isinstance(member, dict):
            raise ValueError('Invalid member')
        if member.get('pid'):
            player = cls._find(s['players'], member['pid'])
            if player['status'] == 'Inactive':
                raise ValueError('Inactive player')
            person = dict(pid=player['id'], name=player['name'])
        else:
            person = dict(pid=None, name=text(member.get('name'), 'guest name'))
            if person['name'].casefold() in PLACEHOLDER_NAMES:
                raise ValueError("A bye is added by the draw; type the guest's real name")
            if any(player['name'].casefold() == person['name'].casefold() for player in s['players']):
                raise ValueError('Player name already exists; select the regular by id')
        taken = [m for e in t['entrants'] for m in e['members']] + t.get('pool', []) + list(team)
        if any(m['name'].casefold() == person['name'].casefold() or person['pid'] and m['pid'] == person['pid'] for m in taken):
            raise ValueError('Person already registered')
        return person

    @staticmethod
    def _propagate(t):
        for match in t['matches']:
            if match['status'] == 'complete':
                continue
            if match['sources']:
                parents = [Operations._find(t['matches'], ident) for ident in match['sources']]
                match['sides'] = [parent['winnerId'] for parent in parents]
                if not all(parent['status'] == 'complete' for parent in parents):
                    continue
            present = [side for side in match['sides'] if side]
            if len(present) < 2:
                match.update(status='complete', winnerId=present[0] if present else None, result='bye', table=None)
            elif match['status'] == 'pending':
                match['status'] = 'scheduled'
                match['absent'] = [side for side in match['sides']
                                   if Operations._find(t['entrants'], side).get('absent', False)]
                if match['absent']:
                    match['status'] = 'delayed'
        if t['matches'] and t['matches'][-1]['status'] == 'complete':
            t['status'] = 'complete'

    def _backfill_source(self, s, source, vod, start, end):
        """The source line of a backfilled night, or the refusal that stops it.

        A broadcast may be written about only when this console already knows it: either the
        range is an imported dataset of this root (out/vods/index.json, which the
        single-flight import job writes for saved channels only) or the broadcast is a saved
        source. Nothing here reads the video or asks Twitch anything — the id is parsed by
        annotator/twitch_vod_source.py and the rest is read from disk (7.0).
        """
        from src.datasets import imported_id, parse_imported_id, read_index
        claimed = source.get('datasetId')
        if not isinstance(claimed, str) or parse_imported_id(claimed) is None:
            raise ValueError('datasetId must be an imported dataset id such as tw-1234567890-452-1690')
        ranged = imported_id(vod, start, end)
        if claimed not in (ranged, imported_id(vod)):
            raise ValueError(f'datasetId must be {ranged} for this broadcast and range')
        for night in s['history']:
            line = night.get('source') or {}
            # 7.4: the same range, backfilled twice, must not become two nights — matched on
            # the id the operator sends and on the range itself, so the whole-broadcast
            # spelling of the same segment cannot slip past the ranged one.
            if line.get('datasetId') == claimed or (line.get('vodId'), line.get('startS'), line.get('endS')) == (vod, start, end):
                raise ConflictError(f'{line.get("datasetId") or claimed} is already in the timeline as '
                                    f'"{night.get("name") or "an unnamed event"}" ({night["id"]}); open it instead')
        channel = source.get('channel')
        channel = channel.strip() if isinstance(channel, str) else ''
        title = source.get('title')
        title = title.strip() if isinstance(title, str) else ''
        entry = read_index(self.root)[0].get(claimed)
        if entry is not None:
            # the import job recorded the channel and title it resolved; a claim that
            # contradicts them is refused instead of stored beside them
            listed = entry.get('channel')
            if channel and isinstance(listed, str) and listed and listed.casefold() != channel.casefold():
                raise ValueError('channel does not match the channel this range was imported from')
            channel = channel or (listed if isinstance(listed, str) else '')
            title = title or (entry.get('title') if isinstance(entry.get('title'), str) else '')
        else:
            saved = s.get('sources') or []
            videos = {item.get('video') for item in saved if item.get('kind') == 'video'}
            channels = {str(item.get('channel') or '').casefold() for item in saved if item.get('kind') == 'channel'}
            if vod not in videos and channel.casefold() not in channels:
                raise ValueError('This broadcast is not a saved source and was not imported; '
                                 'add its channel or the VOD under Source first')
        return dict(kind='vod-backfill', vodId=vod, datasetId=claimed, startS=start, endS=end,
                    channel=channel or None, title=title or None, humanReviewed=True)

    @staticmethod
    def _backfill_entrants(s, entrants):
        """The entrants of a backfilled night in the shape this store already uses, plus the
        resolver from a written side to the entrant it names.

        A side is written as the entrant's id when the payload carries one and as their name
        when it does not; names are unique inside the night, so a reference is never ambiguous.
        A named regular is written as their roster row (`pid`), so a past night counts towards
        that regular's house standing (6.1); a name nobody on the roster holds stays a guest.
        """
        if not isinstance(entrants, list) or not entrants:
            raise ValueError('entrants must be a non-empty list')
        rows, by_id, by_name, by_pid = [], {}, {}, {}
        for row in entrants:
            if not isinstance(row, dict):
                raise ValueError('Invalid entrant')
            pid = row.get('pid')
            if pid is None:
                name, guest = text(row.get('name'), 'entrant name', 120), None
                if any(item['name'].casefold() == name.casefold() for item in s['players']):
                    raise ValueError('Player name already exists; send the regular as their player id')
            else:
                player = next((item for item in s['players'] if item['id'] == pid), None)
                if player is None:
                    raise ValueError('Unknown id')
                if player['status'] == 'Inactive':
                    raise ValueError('Inactive player')
                if player['id'] in by_pid:
                    raise ValueError('Two entrants name the same regular')
                name, guest = player['name'], player['id']
            if name_key(name) in PLACEHOLDER_NAMES:
                raise ValueError("A bye is added by the draw; type the guest's real name")
            ident = row.get('id')
            ident = uid() if ident is None else text(ident, 'entrant id', 64)
            if ident in by_id:
                raise ValueError('Two entrants share an id')
            if name_key(name) in by_name:
                raise ValueError('Two entrants share a name')
            by_id[ident] = ident
            by_name[name_key(name)] = ident
            if guest:
                by_pid[guest] = ident
            rows.append(dict(id=ident, members=[dict(pid=guest, name=name)]))

        def side(value):
            key = value.strip() if isinstance(value, str) else ''
            if key in by_id:
                return by_id[key]
            if key and name_key(key) in by_name:
                return by_name[name_key(key)]
            raise ValueError('Every side and winner must name one of the entrants')

        return rows, side

    @staticmethod
    def _backfill_matches(matches, side):
        """One archived match per hand-typed result: complete, each holding the boundary the
        operator marked (clip) and nothing this server computed."""
        if not isinstance(matches, list) or not matches:
            raise ValueError('matches must be a non-empty list')
        rows = []
        for match in matches:
            if not isinstance(match, dict):
                raise ValueError('Invalid match')
            sides = match.get('sides')
            if not isinstance(sides, list) or len(sides) != 2:
                raise ValueError('Two sides required')
            sides = [side(value) for value in sides]
            if sides[0] == sides[1]:
                raise ValueError('A match needs two different entrants')
            score = match.get('score')
            if not isinstance(score, list) or len(score) != 2:
                raise ValueError('Two scores required')
            winner = side(match.get('winner'))
            if winner not in sides:
                raise ValueError('winner must be one of the two sides')
            result = match.get('result', 'played')
            if result not in ('played', 'forfeit'):
                raise ValueError("result must be 'played' or 'forfeit'")
            clip = match.get('clip')
            if not isinstance(clip, list) or len(clip) != 2:
                raise ValueError('clip must be [start, end] in whole seconds')
            clip = [seconds(clip[0], 'clip start'), seconds(clip[1], 'clip end')]
            if clip[1] <= clip[0]:
                raise ValueError('clip end must be after clip start')
            rows.append(dict(id=uid(), round=integer(match.get('round', 1), 1, 99, 'round'),
                             sides=sides, score=[integer(value, 0, 99, 'score') for value in score],
                             table=None, status='complete', winnerId=winner, absent=[], sources=[],
                             result=result, clip=clip))
        return rows

    def _backfill(self, s, p):
        """7.4: write one past night, typed and confirmed by a person, onto the timeline.

        The video is never read and no boundary is computed: `source.humanReviewed` is the
        confirmation the server enforces, and every refused request leaves the store exactly
        as it was (7.5). The night is APPENDED to `history`; the event being played tonight is
        not touched (7.4 step 2).
        """
        event, source = p.get('event'), p.get('source')
        if not isinstance(event, dict):
            raise ValueError('event object required')
        if not isinstance(source, dict):
            raise ValueError('source object required')
        if source.get('humanReviewed') is not True:
            raise ValueError('Every result must be confirmed by a person: source.humanReviewed must be true')
        if source.get('kind') != 'vod-backfill':
            raise ValueError("source.kind must be 'vod-backfill'")
        vod = vod_id(source.get('vodId'))
        start = seconds(source.get('startS'), 'startS')
        end = seconds(source.get('endS'), 'endS')
        if end <= start:
            raise ValueError('endS must be after startS')
        name = text(event.get('name'), 'name', 120)
        fmt = event.get('format', 'singles')
        if fmt not in ('singles', 'doubles'):
            raise ValueError('Invalid format')
        tables = integer(event.get('tables', 1), 1, 32, 'tables')
        race_to = integer(event.get('raceTo', 1), 1, 99, 'raceTo')
        # Nothing below writes to the store before every field has been accepted.
        line = self._backfill_source(s, source, vod, start, end)
        entrants, side = self._backfill_entrants(s, event.get('entrants'))
        matches = self._backfill_matches(event.get('matches'), side)
        signed = timestamp()
        s['history'].append(dict(id=uid(), name=name, format=fmt, tables=tables, raceTo=race_to,
                                 entrants=entrants, matches=matches, status='complete',
                                 archivedAt=signed, source=line, signOff=dict(at=signed)))

    def _apply(self, s, p):
        action = p.get('action')
        t = s['tournament']
        if action == 'player_save':
            name = text(p.get('name'), 'name')
            if any(x['name'].casefold() == name.casefold() and x['id'] != p.get('id') for x in s['players']):
                raise ValueError('Player name already exists')
            # A guest's name is a claim too: two different people must never read the same.
            if any(m['name'].casefold() == name.casefold() for e in t['entrants'] for m in e['members'] if not m['pid']):
                raise ValueError('Name held by a guest in this event; add the guest to the regulars instead')
            player = self._find(s['players'], p['id']) if p.get('id') else dict(id=uid(), joinedAt=timestamp(), rating=0, status='Active')
            status = optional(p, 'status', player['status'])
            if status not in ('Active', 'Visitor', 'Prospect', 'Inactive'):
                raise ValueError('Invalid player status')
            player.update(name=name, rating=integer(optional(p, 'rating', player['rating']), 0, 1000, 'rating'), status=status)
            if p.get('notes') is not None:
                if not isinstance(p['notes'], str) or len(p['notes']) > 4000:
                    raise ValueError('Player notes must be text up to 4000 characters')
                player['notes'] = p['notes'].strip()
            if not p.get('id'):
                s['players'].append(player)
        elif action == 'guest_promote':
            name = text(p.get('name'), 'guest name').casefold()
            members = [member for entrant in t['entrants'] for member in entrant['members']
                       if member['name'].casefold() == name]
            if len(members) != 1 or members[0]['pid'] is not None:
                raise ValueError('Exactly one unregistered current tournament guest is required')
            if any(player['name'].casefold() == name for player in s['players']):
                raise ValueError('Player name already exists; cannot infer guest identity')
            member = members[0]
            player = dict(id=uid(), name=member['name'], joinedAt=timestamp(), rating=0, status='Active')
            s['players'].append(player)
            member['pid'] = player['id']
        elif action == 'player_delete':
            player = self._find(s['players'], p.get('id'))
            if any(m.get('pid') == player['id'] for night in [t] + s['history'] for e in night['entrants'] for m in e['members']):
                raise ValueError('Player has tournament history; mark Inactive instead')
            s['players'].remove(player)
        elif action == 'tournament_setup':
            if t['status'] != 'registration':
                raise ValueError('Tournament already started')
            fmt = p.get('format', t['format'])
            if fmt not in ('singles', 'doubles'):
                raise ValueError('Invalid format')
            if fmt != t['format'] and t['entrants']:
                raise ValueError('Remove entrants before changing format')
            if fmt != t['format'] and t.get('pool'):
                raise ValueError('Remove solo players before changing format')
            t.update(format=fmt, tables=integer(p.get('tables', t['tables']), 1, 32, 'tables'),
                     raceTo=integer(p.get('raceTo', t['raceTo']), 1, 99, 'raceTo'))
            if 'name' in p:
                t['name'] = text(p['name'], 'name')
        elif action in ('solo_add', 'pool_remove', 'pair_draw', 'pair_clear', 'pair_accept'):
            # R3: an optional random pairing of solo sign-ups; pairing only, never a result.
            if t['status'] != 'registration':
                raise ValueError('Registration is closed')
            if t['format'] != 'doubles':
                raise ValueError('Random pairing is for doubles')
            pool, pairing = t.setdefault('pool', []), t.get('pairing')
            if action == 'pair_clear':
                t['pairing'] = None
            elif action == 'pair_accept':
                if not pairing:
                    raise ValueError('No pairing to accept')
                if p.get('seed') != pairing['seed']:
                    raise ValueError('The pairing changed; review the teams again')
                if len(t['entrants']) + len(pairing['teams']) > 128:
                    raise ValueError('Maximum 128 entrants')
                t['entrants'].extend(dict(id=uid(), members=team) for team in pairing['teams'])
                t.update(pool=[], pairing=None)
            elif pairing and action != 'pair_draw':
                raise ValueError('Registration is locked while a pairing is shown; accept or clear it first')
            elif action == 'solo_add':
                pool.append(self._person(s, t, p.get('member')))
            elif action == 'pool_remove':
                name = text(p.get('name'), 'name').casefold()
                pool.remove(next((m for m in pool if m['name'].casefold() == name), None) or self._find([], None))
            else:
                if len(pool) < 2 or len(pool) % 2:
                    raise ValueError('An even number of solo players is needed to pair')
                seed = random.SystemRandom().randrange(2 ** 31)
                order = list(range(len(pool)))
                random.Random(seed).shuffle(order)
                t['pairing'] = dict(seed=seed, teams=[[pool[order[i]], pool[order[i + 1]]] for i in range(0, len(order), 2)])
        elif action in ('entrant_add', 'entrant_remove', 'entrant_absence'):
            if t['status'] != 'registration':
                raise ValueError('Registration is closed')
            if t.get('pairing'):
                raise ValueError('Registration is locked while a pairing is shown; accept or clear it first')
            if action == 'entrant_absence':
                if type(p.get('absent')) is not bool:
                    raise ValueError('absent must be boolean')
                self._find(t['entrants'], p.get('id'))['absent'] = p['absent']
                return
            if action == 'entrant_remove':
                t['entrants'].remove(self._find(t['entrants'], p.get('id')))
                return
            members = p.get('members')
            if not isinstance(members, list) or len(members) != (2 if t['format'] == 'doubles' else 1):
                raise ValueError('Wrong number of team members')
            if len(t['entrants']) >= 128:
                raise ValueError('Maximum 128 entrants')
            result = []
            for member in members:
                result.append(self._person(s, t, member, result))
            t['entrants'].append(dict(id=uid(), members=result))
        elif action == 'tournament_start':
            if t['status'] != 'registration' or len(t['entrants']) < 2:
                raise ValueError('Need an unstarted tournament with at least two entrants')
            size = 1 << (len(t['entrants']) - 1).bit_length()
            ids = [e['id'] for e in t['entrants']]
            # Give byes to the first seeds; never create empty/empty first-round matches.
            byes = size - len(ids)
            pairs = [[ids[i], None] for i in range(byes)]
            pairs += [ids[i:i + 2] for i in range(byes, len(ids), 2)]
            previous = []
            round_number = 1
            while pairs:
                current = []
                for index, sides in enumerate(pairs):
                    match = dict(id=uid(), round=round_number, sides=sides, score=[0, 0], table=None,
                                 status='pending', winnerId=None, absent=[], sources=previous[index * 2:index * 2 + 2])
                    t['matches'].append(match)
                    current.append(match['id'])
                if len(current) == 1:
                    break
                previous = current
                pairs = [[None, None] for _ in range(len(current) // 2)]
                round_number += 1
            t['status'] = 'active'
            self._propagate(t)
        elif action in ('match_schedule', 'match_unschedule', 'match_score', 'match_complete', 'match_absence', 'match_forfeit'):
            match = self._find(t['matches'], p.get('id'))
            if match['status'] in ('complete', 'pending') or not all(match['sides']):
                raise ValueError('Match is not editable')
            if action == 'match_schedule':
                if match['absent']:
                    raise ValueError('Absent player; match held')
                occupied = {m['table'] for m in t['matches'] if m['id'] != match['id'] and m['status'] == 'live'}
                table = p.get('table', next((n for n in range(1, t['tables'] + 1) if n not in occupied), None))
                if table is None:
                    raise ValueError('All tables are in use')
                table = integer(table, 1, t['tables'], 'table')
                if table in occupied:
                    raise ValueError('Table is occupied')
                match.update(table=table, status='live')
            elif action == 'match_unschedule':
                if match['status'] != 'live':
                    raise ValueError('Match is not on a table')
                match.update(table=None, status='scheduled')
            elif action == 'match_score':
                if match['status'] != 'live':
                    raise ValueError('Schedule match before scoring')
                score = p.get('score')
                if not isinstance(score, list) or len(score) != 2:
                    raise ValueError('Two scores required')
                score = [integer(v, 0, t['raceTo'], 'score') for v in score]
                if score == [t['raceTo'], t['raceTo']]:
                    raise ValueError('Both players cannot win')
                match['score'] = score
            elif action == 'match_absence':
                side = integer(p.get('side'), 0, 1, 'side')
                if type(p.get('absent')) is not bool:
                    raise ValueError('absent must be boolean')
                self._find(t['entrants'], match['sides'][side])['absent'] = p['absent']
                absent = set(match['absent'])
                if p['absent']:
                    absent.add(match['sides'][side])
                else:
                    absent.discard(match['sides'][side])
                match.update(absent=sorted(absent), status='delayed' if absent else 'scheduled', table=None)
            else:
                if action == 'match_forfeit':
                    side = integer(p.get('side'), 0, 1, 'side')
                    winner = 1 - side
                else:
                    if match['status'] != 'live' or max(match['score']) != t['raceTo'] or match['score'][0] == match['score'][1]:
                        raise ValueError('A live race-winning score is required')
                    winner = 0 if match['score'][0] > match['score'][1] else 1
                match.update(status='complete', winnerId=match['sides'][winner], table=None,
                             result='forfeit' if action == 'match_forfeit' else 'played', completedAt=timestamp())
                self._propagate(t)
        elif action in ('revival_draw', 'revival_undo'):
            if p.get('confirm') is not True:
                raise ValueError('Explicit confirmation required')
            signed = sum(1 for m in t['matches'] if m.get('result') in ('played', 'forfeit'))
            if action == 'revival_undo':
                drawn = t.get('revival')
                if not drawn:
                    raise ValueError('No revival draw to undo')
                if signed != drawn['signed']:
                    raise ValueError('Undo is closed: a result has been signed since the draw')
                match = self._find(t['matches'], drawn['match'])
                match['sides'][drawn['side']] = None
                match.update(status='complete', winnerId=drawn['holder'], result='bye', table=None, absent=[], score=[0, 0])
                self._find(t['matches'], drawn['next']).update(status='pending', table=None, absent=[], score=[0, 0])
                del t['revival']
                self._propagate(t)
                return
            # R6, the honest version: chance picks WHO re-enters, never who wins.
            if t.get('revival'):
                raise ValueError('A second chance was already drawn for this event')
            if not t['matches']:
                raise ValueError('The draw has not started')
            if any(m['round'] >= 2 and m.get('result') in ('played', 'forfeit') for m in t['matches']):
                raise ValueError('Round 2 has a signed result; the draw is closed')
            first = [m for m in t['matches'] if m['round'] == 1]
            if any(all(m['sides']) and m['status'] != 'complete' for m in first):
                raise ValueError('Finish round 1 first; every round-1 loser must be in the draw')
            # a forfeit loser did not play (no-show or withdrawal) and is not revived
            pool = sorted(next(side for side in m['sides'] if side != m['winnerId'])
                          for m in first if m.get('result') == 'played')
            if not pool:
                raise ValueError('No round-1 loser to draw from')
            slots = []
            for m in first:
                following = next((d for d in t['matches'] if m['id'] in d['sources']), None)
                if (m.get('result') == 'bye' and following and following['status'] in ('pending', 'scheduled', 'delayed')
                        and not following['table'] and following['score'] == [0, 0]):
                    slots.append((m, following))
            if not slots:
                raise ValueError('No round-2 bye slot to fill')
            # the last bye in the draw belongs to the lowest seed that has one
            match, following = slots[-1]
            # Round 21, owner item 3: the operator may name the person instead of taking the draw. The
            # pool is what the draw itself chooses from, so a name outside it is refused rather than
            # quietly resurrecting somebody who is still playing.
            chosen = p.get('entrant')
            if chosen is not None and chosen not in pool:
                raise ValueError('That person is not eligible for the second chance')
            seed = random.SystemRandom().randrange(2 ** 31)
            entrant = chosen if chosen is not None else random.Random(seed).choice(pool)
            side = match['sides'].index(None)
            holder = match['winnerId']
            members = self._find(t['entrants'], entrant)['members']
            names = {x['id']: x['name'] for x in s['players']}
            # Every successful draw counts, and undo never lowers it: a re-roll until a
            # wanted loser comes up stays visible on the card, the sheet and in the log.
            t['revival_draws'] = t.get('revival_draws', 0) + 1
            t['revival'] = dict(seed=seed, pool=pool, entrant=entrant, match=match['id'], next=following['id'],
                                side=side, holder=holder, signed=signed, drawnAt=timestamp(),
                                name=' / '.join(names.get(x['pid'], x['name']) for x in members),
                                attempt=t['revival_draws'])
            match['sides'][side] = entrant
            match.pop('result')
            match.update(status='pending', winnerId=None, table=None, absent=[])
            following.update(status='pending', table=None, absent=[])
            self._propagate(t)
        elif action == 'tournament_rename':
            # Name only, current or archived: format, race, tables and results stay locked.
            self._find([t] + s['history'], p.get('id'))['name'] = text(p.get('name'), 'name', 120)
        elif action == 'tournament_delete':
            # R1: only a mistake with nothing signed may go; a signed result is permanent.
            night = self._find([t] + s['history'], p.get('id'))
            if p.get('confirm') is not True:
                raise ValueError('Explicit confirmation required')
            if any(m.get('result') in ('played', 'forfeit') for m in night['matches']):
                raise ValueError('An event with a signed result cannot be deleted; hide it from history instead')
            if night is t:
                s['tournament'] = tournament()
            else:
                s['history'].remove(night)
            self._drop_links(s, night['id'])
        elif action == 'tournament_hide':
            # R1: a flag on an archived event; every match and stat stays.
            night = self._find(s['history'] + [t], p.get('id'))
            if p.get('confirm') is not True:
                raise ValueError('Explicit confirmation required')
            if night is t:
                raise ValueError('Only an archived event can be hidden')
            if type(p.get('hidden')) is not bool:
                raise ValueError('hidden must be boolean')
            night['hidden'] = p['hidden']
        elif action == 'tournament_new':
            if p.get('confirm') is not True:
                raise ValueError('Explicit confirmation required')
            if t['entrants'] or t['matches']:
                archived = copy.deepcopy(t)
                archived['archivedAt'] = timestamp()
                s['history'].append(archived)
            else:
                self._drop_links(s, t['id'])
            s['tournament'] = tournament()
        elif action == 'event_backfill':
            self._backfill(s, p)
        elif action == 'vod_link':
            self._link_vod(s, p)
        elif action == 'vod_unlink':
            self._unlink_vod(s, p)
        elif action == 'source_add':
            url = text(p.get('url'), 'Twitch URL', 500)
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or parsed.netloc not in ('twitch.tv', 'www.twitch.tv') or parsed.query or parsed.fragment:
                raise ValueError('Use an HTTPS Twitch channel or video URL without query parameters')
            path = parsed.path.rstrip('/')
            video = re.fullmatch(r'/videos/([0-9]+)', path)
            channel = re.fullmatch(r'/([A-Za-z0-9_]{1,25})', path)
            if not video and (not channel or channel[1].lower() in ('videos', 'directory', 'downloads', 'settings', 'search', 'login', 'signup', 'subscriptions', 'inventory', 'wallet', 'jobs', 'turbo')):
                raise ValueError('Use a Twitch channel or videos/<digits> URL')
            canonical = 'https://www.twitch.tv' + path.lower()
            sources = s.setdefault('sources', [])
            if any(source['url'] == canonical for source in sources):
                raise ValueError('Source already added')
            source = dict(id=uid(), url=canonical, kind='video' if video else 'channel')
            source['video' if video else 'channel'] = video[1] if video else channel[1].lower()
            sources.append(source)
        elif action == 'source_delete':
            sources = s.setdefault('sources', [])
            sources.remove(self._find(sources, p.get('id')))
        elif action == 'settings_update':
            if 'clothColor' in p:
                if p['clothColor'] not in ('#1d5c44', '#1f4a70', '#6a2130', '#2f3a3f'):
                    raise ValueError('Invalid cloth color')
                s['settings']['clothColor'] = p['clothColor']
            if 'lampGlow' in p:
                glow = p['lampGlow']
                if type(glow) not in (float, int) or not math.isfinite(glow) or not 0 <= glow <= 0.5:
                    raise ValueError('lampGlow must be between 0 and 0.5')
                s['settings']['lampGlow'] = glow
            if 'showDiamonds' in p:
                if type(p['showDiamonds']) is not bool:
                    raise ValueError('showDiamonds must be boolean')
                s['settings']['showDiamonds'] = p['showDiamonds']
            if 'shotClock' in p:
                s['settings']['shotClock'] = integer(p['shotClock'], 5, 300, 'shotClock')
            if 'autoFrame' in p:
                if type(p['autoFrame']) is not bool:
                    raise ValueError('autoFrame must be boolean')
                s['settings']['autoFrame'] = p['autoFrame']
            if 'publicBoard' in p:
                # The public board's only control (docs/public-board.md, "Board off" and 6): false
                # makes GET /api/board answer {"board":"off"}. Read side: public_board.build.
                if type(p['publicBoard']) is not bool:
                    raise ValueError('publicBoard must be boolean')
                s['settings']['publicBoard'] = p['publicBoard']
        elif action == 'note_add':
            s['notes'].append(dict(id=uid(), text=text(p.get('text'), 'note', 4000), createdAt=timestamp()))
        elif action == 'note_delete':
            s['notes'].remove(self._find(s['notes'], p.get('id')))
        else:
            raise ValueError('Unknown operations action')
