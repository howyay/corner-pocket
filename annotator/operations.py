"""Persistent, server-authoritative pool operations; standard library only."""
import copy
import json
import os
import math
import random
import re
from dataclasses import dataclass
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


#: the state collections an action can name as the one row it acts on (see Record).
RECORD_COLLECTIONS = ('players', 'entrants', 'matches', 'sources', 'notes', 'history')


@dataclass(frozen=True)
class Record:
    """The one row of the store an action acts on, declared by the action itself.

    `collection` is the state list that holds the row and `field` the payload field that
    names it. A payload that names nothing is not guessed at: the write hands the row over
    (the row it created, changed or removed), and a write that names nothing either is
    refused. The prefix table and the last-row fallback this replaces are gone."""

    collection: str
    field: str = 'id'


@dataclass(frozen=True)
class Operation:
    """One named write on the operations document, declared in one place.

    The name, the code that writes the change, the audit line the change produces and
    the fields the payload must carry all live in this record. The dispatcher and the
    declaration check read the same record, so an action cannot register half of itself."""

    name: str
    apply: object            # (Operations, state, payload) -> the row it acted on, or None
    audit: object            # (state, payload) -> dict
    requires: tuple = ()     # ((field, refusal message), ...)
    # True when a missing declared field is refused before the action runs. Some actions
    # refuse a state precondition first (a closed registration, a stopped tournament), so
    # their own code keeps the field check and the order of the two refusals stays.
    refuse_missing_first: bool = True
    # True when the audit is read before the write, because the write clears what the
    # audit reads: a deleted event, an accepted pairing, an undone draw. Every other
    # action is audited after the write, on the document the caller gets back.
    audit_before_write: bool = False
    # The one row this action acts on, when it has one; it then needs no audit projection
    # of its own (the dispatcher reads the row the payload or the write names).
    record: object = None

    def refuse_missing(self, payload):
        """Refuse a payload that does not carry a field this action needs."""
        for field, refusal in self.requires:
            if field not in payload:
                raise ValueError(refusal)


def operations_registry(rows):
    """Check each declaration, then key them by name. A half-declared action fails here."""
    registry = {}
    for row in rows:
        if not isinstance(row, Operation):
            raise ValueError(f'operation must be an Operation, not {type(row).__name__}')
        if not isinstance(row.name, str) or not row.name:
            raise ValueError('operation needs a name')
        if row.name in registry:
            raise ValueError(f'operation {row.name} is declared twice')
        if not callable(row.apply):
            raise ValueError(f'operation {row.name} has no writer')
        if not callable(row.audit):
            raise ValueError(f'operation {row.name} has no audit projection')
        if not isinstance(row.requires, tuple):
            raise ValueError(f'operation {row.name} needs a tuple of required fields')
        for entry in row.requires:
            if (not isinstance(entry, tuple) or len(entry) != 2
                    or not all(isinstance(part, str) and part for part in entry)):
                raise ValueError(f'operation {row.name} declares a bad required field: {entry!r}')
        if not isinstance(row.audit_before_write, bool):
            raise ValueError(f'operation {row.name} needs audit_before_write to be a boolean')
        if row.record is not None:
            if not isinstance(row.record, Record):
                raise ValueError(f'operation {row.name} needs a Record, not {type(row.record).__name__}')
            if row.record.collection not in RECORD_COLLECTIONS:
                raise ValueError(f'operation {row.name} names an unknown collection: {row.record.collection}')
            if not isinstance(row.record.field, str) or not row.record.field:
                raise ValueError(f'operation {row.name} needs a payload field that names its row')
        registry[row.name] = row
    return registry


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
        """Run the operation the payload names. The registry holds its declaration."""
        if not isinstance(payload, dict):
            raise ValueError('JSON object required')
        with self.lock:
            state = self._load()
            if type(payload.get('revision')) is not int:
                raise ValueError('integer revision required')
            if payload['revision'] != state['revision']:
                raise ConflictError('State changed; reload before retrying')
            action, context = self.run(state, payload)
            return self._commit(state, action, context)

    def run(self, state, payload):
        """Apply one payload to one document. Answer (action, audit context).

        The file backing and the database backing both call this method. Thus one
        registry holds the writer, the audit line and the required fields, and the two
        backings cannot drift apart. The one write step is `_apply`, and the row is
        resolved there once: neither the audit nor the writer looks it up again."""
        applied = self._apply(state, payload)
        # A caller that replaced the write step with its own write leaves nothing to log.
        return applied if applied is not None else (payload.get('action'), {})

    def roster_add(self, state, player):
        """Add the enrolled regular to the roster once. One roster rule, two backings.

        `player` is the roster record the enrolment planned; it is added only when its
        id is not on the roster yet (an existing regular gains faces, not a row), and
        a name that another player already holds (casefold) is refused, the rule
        `player_save` enforces."""
        if not any(existing.get('id') == player['id'] for existing in state['players']):
            name = text(player.get('name'), 'name')
            if any(existing['name'].casefold() == name.casefold() for existing in state['players']):
                raise ValueError('Player name already exists')
            # the defaults player_save gives a new regular: the plan carries only
            # {id, name} when it matched a regular who has since been deleted
            state['players'].append({'joinedAt': timestamp(), 'rating': 0, 'status': 'Active',
                                     **player, 'name': name})

    def enroll_player(self, player, context):
        """Add a player confirmed from the footage: one read-modify-write under the
        store lock, at the CURRENT revision, never a stale document written over it.

        The event is appended to the same log."""
        with self.lock:
            state = self._load()
            self.roster_add(state, player)
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
    def _event_context(state, payload, operation, written=None):
        """The audit line of one action, read from that action's own declaration.

        Whitelist domain identity only: never copy request or note contents. An action
        that declares the one row it acts on adds that row's identity: the row the
        payload names, or - when the payload cannot name it - the row its write named."""
        context = operation.audit(state, payload)
        if operation.record is not None:
            context.update(_row_context(operation.record, state, payload, written))
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
    def _late_pool(t):
        """The round-1 losers who may come back. A forfeit loser did not play, so they are not here."""
        return sorted(next(side for side in m['sides'] if side != m['winnerId'])
                      for m in t['matches'] if m['round'] == 1 and m.get('result') == 'played')

    @staticmethod
    def _late_refuse_member(t, name, pid, sentence):
        """One person, one place in the event: the arrival, the opponent and the partner all pass here."""
        for existing in t['entrants']:
            for member in existing.get('members', []):
                same_pid = bool(pid) and member.get('pid') == pid
                same_name = (member.get('name') or '').casefold() == name.casefold()
                if same_pid or same_name:
                    raise ValueError(sentence)

    def _late_entrant(self, t, mode, entrant, name, pool):
        """The person on the other side of the late slot, as an entrant id."""
        if mode == 'revive':
            if entrant not in pool:
                raise ValueError('That person is not eligible for the second chance')
            return entrant
        if not name:
            raise ValueError('A new opponent needs a name')
        name = text(name, 'name', 120)
        Operations._late_refuse_member(t, name, None, 'That person is already in this tournament')
        rival = dict(id=uid(), members=[dict(pid=None, name=name)])
        t['entrants'].append(rival)
        return rival['id']

    def _late_partner(self, t, mode, entrant, name, pool):
        """The partner is a member of the team, so the person is copied, not the entrant."""
        if mode == 'revive':
            if entrant not in pool:
                raise ValueError('That person is not eligible for the second chance')
            # They are an entrant already, so the duplicate check does not apply to them.
            member = self._find(t['entrants'], entrant)['members'][0]
            return dict(pid=member.get('pid'), name=member['name'])
        if not name:
            raise ValueError('A new teammate needs a name')
        name = text(name, 'name', 120)
        Operations._late_refuse_member(t, name, None, 'That person is already in this tournament')
        return dict(pid=None, name=name)

    @staticmethod
    def _late_refuse_both_sides(members, rival):
        """One person cannot play on both sides of the same match."""
        def keys(rows):
            return {(row.get('pid') or str(row.get('name') or '').casefold()) for row in rows}
        if keys(members) & keys(rival):
            raise ValueError('That person cannot play on both sides of the match')

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
        if t['matches']:
            # Round 29: the last match in the list is not always the last round. A late entrant's round-1
            # bye slot is appended after the final, and this test used to read it as the night being over.
            final_round = max(match['round'] for match in t['matches'])
            final = [match for match in t['matches'] if match['round'] == final_round]
            if all(match['status'] == 'complete' for match in final):
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
        """The one write step: resolve the row once, then declare, audit and write.

        One registry lookup per write, and the row it answers is the one the refusal,
        the audit and the writer all read (candidate 6). The audit is read on the side
        the row declares: before the write when the write clears what the audit reads,
        after it otherwise, on the document the caller gets back. Answer (action, audit
        context), or None when a caller replaced this method with its own write."""
        action = p.get('action')
        operation = OPERATIONS.get(action) if isinstance(action, str) else None
        if operation is None:
            raise ValueError('Unknown operations action')
        if operation.refuse_missing_first:
            operation.refuse_missing(p)
        if operation.audit_before_write:
            context = self._event_context(s, p, operation)
            operation.apply(self, s, p)
            return action, context
        written = operation.apply(self, s, p)
        return action, self._event_context(s, p, operation, written)

    def _do_player_save(self, s, p):
        t = s['tournament']
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
        return player

    def _do_guest_promote(self, s, p):
        t = s['tournament']
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

    def _do_player_delete(self, s, p):
        t = s['tournament']
        player = self._find(s['players'], p.get('id'))
        if any(m.get('pid') == player['id'] for night in [t] + s['history'] for e in night['entrants'] for m in e['members']):
            raise ValueError('Player has tournament history; mark Inactive instead')
        s['players'].remove(player)
        return player

    def _do_tournament_setup(self, s, p):
        t = s['tournament']
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

    def _do_pairing(self, s, p):
        """R3: an optional random pairing of solo sign-ups; pairing only, never a result."""
        action = p.get('action')
        t = s['tournament']
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
        elif action == 'pair_draw':
            if len(pool) < 2 or len(pool) % 2:
                raise ValueError('An even number of solo players is needed to pair')
            seed = random.SystemRandom().randrange(2 ** 31)
            order = list(range(len(pool)))
            random.Random(seed).shuffle(order)
            t['pairing'] = dict(seed=seed, teams=[[pool[order[i]], pool[order[i + 1]]] for i in range(0, len(order), 2)])
        else:
            # A name this writer does not implement is refused here. The old fall-through drew a
            # pairing for any unknown name, so a bad registry row paired a tournament.
            raise ValueError(f'Unknown pairing action: {action}')

    def _do_entrants(self, s, p):
        action = p.get('action')
        t = s['tournament']
        if t['status'] != 'registration':
            raise ValueError('Registration is closed')
        if t.get('pairing'):
            raise ValueError('Registration is locked while a pairing is shown; accept or clear it first')
        if action == 'entrant_absence':
            if type(p.get('absent')) is not bool:
                raise ValueError('absent must be boolean')
            entrant = self._find(t['entrants'], p.get('id'))
            entrant['absent'] = p['absent']
            return entrant
        if action == 'entrant_remove':
            entrant = self._find(t['entrants'], p.get('id'))
            t['entrants'].remove(entrant)
            return entrant
        members = p.get('members')
        if not isinstance(members, list) or len(members) != (2 if t['format'] == 'doubles' else 1):
            raise ValueError('Wrong number of team members')
        if len(t['entrants']) >= 128:
            raise ValueError('Maximum 128 entrants')
        result = []
        for member in members:
            result.append(self._person(s, t, member, result))
        entrant = dict(id=uid(), members=result)
        t['entrants'].append(entrant)
        return entrant

    def _do_tournament_start(self, s, p):
        t = s['tournament']
        if t['status'] != 'registration' or len(t['entrants']) < 2:
            raise ValueError('Need an unstarted tournament with at least two entrants')
        if not t['name'].strip():
            # R2: an event that is drawn is never nameless. The server fills the default
            # the form displays here, where the draw the name belongs to is made; the
            # audit of this write and every later read then name it (candidate 6).
            t['name'] = default_name()
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

    def _do_entrant_add_late(self, s, p):
        # Round 21, owner item 3: somebody who arrives after the draw joins as their own team, in a
        # round-1 bye slot of their own with no sources, so the rest of the tree is untouched and
        # _propagate has nothing to rewrite.
        # Round 29, owner item 1: the operator decides that slot in a dialog. The match-up and, for
        # doubles, the teammate are each one of three choices: nobody (the arrival advances), a
        # second chance (a round-1 loser who played comes back into the slot), or a new person
        # (registered here by name as the opponent or the partner). A payload without those choices
        # is refused, so no client can skip the decision.
        t = s['tournament']
        if t['status'] != 'active':
            raise ValueError('The tournament is not running')
        doubles = t.get('format') == 'doubles'
        late_name = text(p.get('name'), 'name', 120)
        late_pid = p.get('pid') or None
        self._late_refuse_member(t, late_name, late_pid, 'That person is already in this tournament')
        opponent = p.get('opponent')
        if opponent not in ('none', 'revive', 'new'):
            raise ValueError('Choose the match-up: nobody, a second chance, or a new player')
        partner = p.get('partner')
        if doubles:
            if partner not in ('none', 'revive', 'new'):
                raise ValueError('Choose the teammate for a doubles event')
        elif partner not in (None, 'none'):
            raise ValueError('A teammate needs a doubles event')
        pool = Operations._late_pool(t)
        members = [dict(pid=late_pid, name=late_name)]
        if doubles and partner != 'none':
            members.append(self._late_partner(t, partner, p.get('partner_entrant'), p.get('partner_name'), pool))
        late = dict(id=uid(), members=members)
        t['entrants'].append(late)
        rival = None if opponent == 'none' else self._late_entrant(
            t, opponent, p.get('opponent_entrant'), p.get('opponent_name'), pool)
        if rival is not None:
            Operations._late_refuse_both_sides(members, self._find(t['entrants'], rival)['members'])
        t['matches'].append(dict(id=uid(), round=1, sides=[late['id'], rival], score=[0, 0], table=None,
                                 status='pending', winnerId=None, absent=[], sources=[], late=True,
                                 lateOpponent=opponent, latePartner=partner or 'none'))
        self._propagate(t)
        # The arrival is the row this write made, whatever it then drew: the rival it may
        # have added is a second row of the same collection (candidate 5, measured).
        return late

    def _do_match(self, s, p):
        action = p.get('action')
        t = s['tournament']
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
        elif action in ('match_complete', 'match_forfeit'):
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
        else:
            # A name this writer does not implement is refused here. The old fall-through ran
            # match_complete for any unknown name, so a bad registry row played a match.
            raise ValueError(f'Unknown match action: {action}')
        return match

    def _do_revival(self, s, p):
        action = p.get('action')
        t = s['tournament']
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

    def _do_tournament_rename(self, s, p):
        # Name only, current or archived: format, race, tables and results stay locked.
        self._find([s['tournament']] + s['history'], p.get('id'))['name'] = text(p.get('name'), 'name', 120)

    def _do_tournament_delete(self, s, p):
        # R1: only a mistake with nothing signed may go; a signed result is permanent.
        t = s['tournament']
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

    def _do_tournament_hide(self, s, p):
        # R1: a flag on an archived event; every match and stat stays.
        t = s['tournament']
        night = self._find(s['history'] + [t], p.get('id'))
        if p.get('confirm') is not True:
            raise ValueError('Explicit confirmation required')
        if night is t:
            raise ValueError('Only an archived event can be hidden')
        if type(p.get('hidden')) is not bool:
            raise ValueError('hidden must be boolean')
        night['hidden'] = p['hidden']

    def _do_tournament_new(self, s, p):
        t = s['tournament']
        if p.get('confirm') is not True:
            raise ValueError('Explicit confirmation required')
        if t['entrants'] or t['matches']:
            if not t['name'].strip():
                # R2: an event that is archived is never nameless either. Filling the
                # name here, in the writer, keeps the archived night and the audit line
                # that names it in step (candidate 6).
                t['name'] = default_name()
            archived = copy.deepcopy(t)
            archived['archivedAt'] = timestamp()
            s['history'].append(archived)
        else:
            self._drop_links(s, t['id'])
        s['tournament'] = tournament()
        # The night this write retired, archived or dropped: the audit names it (candidate 5).
        return t

    def _do_event_backfill(self, s, p):
        self._backfill(s, p)

    def _do_vod_link(self, s, p):
        self._link_vod(s, p)

    def _do_vod_unlink(self, s, p):
        self._unlink_vod(s, p)

    def _do_source_add(self, s, p):
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
        return source

    def _do_source_delete(self, s, p):
        sources = s.setdefault('sources', [])
        source = self._find(sources, p.get('id'))
        sources.remove(source)
        return source

    def _do_settings_update(self, s, p):
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

    def _do_note_add(self, s, p):
        note = dict(id=uid(), text=text(p.get('text'), 'note', 4000), createdAt=timestamp())
        s['notes'].append(note)
        return note

    def _do_note_delete(self, s, p):
        note = self._find(s['notes'], p.get('id'))
        s['notes'].remove(note)
        return note


def _audit_none(state, payload):
    """No audit document of its own: the store logs the row the action declares."""
    return {}


def _audit_current_event(state, payload):
    """The current event: every tournament action that names no night of its own."""
    t = state['tournament']
    return dict(id=t['id'], name=t['name'])


def _audit_night(state, payload):
    """The event the action names, current or archived."""
    t = state['tournament']
    night = next((n for n in [t] + state['history'] if n['id'] == payload.get('id')), None)
    if night and payload.get('action') == 'tournament_hide' and 'hidden' in night:
        return dict(id=night['id'], name=night['name'], hidden=night['hidden'])
    return dict(id=night['id'], name=night['name']) if night else {}


def _audit_revival(state, payload):
    """The whole draw, so anyone can re-run it: seed, sorted pool, pick, slot."""
    drawn = state['tournament'].get('revival')
    return dict(drawn) if drawn else {}


def _audit_pairing(state, payload):
    """R3: the seed and the teams it made (names only; pool order is sign-up order)."""
    pairing = state['tournament'].get('pairing')
    if not pairing:
        return {}
    return dict(seed=pairing['seed'],
                teams=[' / '.join(m['name'] for m in team) for team in pairing['teams']])


def _audit_guest_promote(state, payload):
    """The roster row the guest became, read back by the name the payload claims."""
    name = payload.get('name')
    if isinstance(name, str):
        matches = [p for p in state['players'] if p['name'].casefold() == name.strip().casefold()]
        if matches:
            return dict(id=matches[0]['id'], name=matches[0]['name'])
    return {}


def _audit_vod(state, payload):
    """The pair a person made: the event, and the broadcast."""
    t = state['tournament']
    vod, event = payload.get('vodId'), payload.get('eventId')
    night = next((n for n in [t] + state['history'] if n['id'] == event), None)
    context = dict(vodId=str(vod)) if isinstance(vod, str) else {}
    if night is not None:
        context.update(id=night['id'], name=night['name'])
    return context


def _audit_backfill(state, payload):
    """7.6: the night the backfill wrote and the broadcast it came from, read back from
    the store rather than copied from the request."""
    source = payload.get('source') if isinstance(payload.get('source'), dict) else {}
    night = next((n for n in reversed(state['history'])
                  if (n.get('source') or {}).get('datasetId') == source.get('datasetId')), None)
    if night is None:
        return dict(vodId=source['vodId']) if isinstance(source.get('vodId'), str) else {}
    return dict(id=night['id'], name=night['name'], vodId=night['source'].get('vodId'),
                datasetId=night['source'].get('datasetId'))


def _rows(state, collection):
    """The state rows one declared collection holds: a Record names one of these.

    Only the collection the action declared is read, so an action never depends on a
    part of the document it does not touch."""
    t = state['tournament']
    if collection == 'players':
        return state['players']
    if collection == 'entrants':
        return t['entrants']
    if collection == 'matches':
        return t['matches']
    if collection == 'sources':
        return state.get('sources', [])
    if collection == 'notes':
        return state['notes']
    return state['history']


def _named_row(record, state, payload):
    """The row the payload names, or None. The last row of a collection is never a guess."""
    named = payload.get(record.field) if isinstance(payload, dict) else None
    if not named:
        return None
    return next((row for row in _rows(state, record.collection)
                 if row.get(record.field) == named), None)


def _row_context(record, state, payload, written):
    """The audit identity of the one row an action acts on.

    The payload names it when it can; otherwise the write named it, by handing over the
    row it created, changed or removed. A payload that names nothing and a write that
    named nothing is refused rather than resolved to a neighbour (candidate 5)."""
    item = _named_row(record, state, payload) or written
    if item is None:
        raise ValueError(f'This action must name the {record.collection} row it acts on')
    context = dict(id=item['id'])
    if 'name' in item:
        context['name'] = item['name']
    return context


# The one registry: every action names its writer, its audit projection and the fields
# its payload must carry. `refuse_missing_first` is False where the action refuses a state
# precondition before it reads those fields, so the two refusals keep today's order.
# `audit_before_write` is True where the write clears what the audit reads. `record` names
# the one row the action acts on: the payload names it when it can, the write names it
# otherwise, and a row that neither names is refused (candidate 5).
OPERATIONS = operations_registry([
    Operation('player_save', Operations._do_player_save, _audit_none,
              (('name', 'name must contain 1–200 characters'),), record=Record('players')),
    Operation('guest_promote', Operations._do_guest_promote, _audit_guest_promote,
              (('name', 'guest name must contain 1–200 characters'),)),
    Operation('player_delete', Operations._do_player_delete, _audit_none,
              (('id', 'Unknown id'),), record=Record('players')),
    Operation('tournament_setup', Operations._do_tournament_setup, _audit_current_event),
    Operation('solo_add', Operations._do_pairing, _audit_none,
              (('member', 'Invalid member'),), refuse_missing_first=False),
    Operation('pool_remove', Operations._do_pairing, _audit_none,
              (('name', 'name must contain 1–200 characters'),), refuse_missing_first=False),
    Operation('pair_draw', Operations._do_pairing, _audit_pairing, refuse_missing_first=False),
    Operation('pair_clear', Operations._do_pairing, _audit_none, refuse_missing_first=False),
    Operation('pair_accept', Operations._do_pairing, _audit_pairing,
              (('seed', 'The pairing changed; review the teams again'),), refuse_missing_first=False,
              audit_before_write=True),
    Operation('entrant_add', Operations._do_entrants, _audit_none,
              (('members', 'Wrong number of team members'),), refuse_missing_first=False,
              record=Record('entrants')),
    Operation('entrant_remove', Operations._do_entrants, _audit_none,
              (('id', 'Unknown id'),), refuse_missing_first=False, record=Record('entrants')),
    Operation('entrant_absence', Operations._do_entrants, _audit_none,
              (('absent', 'absent must be boolean'), ('id', 'Unknown id')), refuse_missing_first=False,
              record=Record('entrants')),
    Operation('tournament_start', Operations._do_tournament_start, _audit_current_event),
    Operation('entrant_add_late', Operations._do_entrant_add_late, _audit_none,
              (('name', 'name must contain 1–120 characters'),
               ('opponent', 'Choose the match-up: nobody, a second chance, or a new player')),
              refuse_missing_first=False, record=Record('entrants')),
    Operation('match_schedule', Operations._do_match, _audit_none, (('id', 'Unknown id'),),
              record=Record('matches')),
    Operation('match_unschedule', Operations._do_match, _audit_none, (('id', 'Unknown id'),),
              record=Record('matches')),
    Operation('match_score', Operations._do_match, _audit_none,
              (('id', 'Unknown id'), ('score', 'Two scores required')), record=Record('matches')),
    Operation('match_complete', Operations._do_match, _audit_none, (('id', 'Unknown id'),),
              record=Record('matches')),
    Operation('match_absence', Operations._do_match, _audit_none,
              (('id', 'Unknown id'), ('side', 'side must be an integer from 0 to 1'),
               ('absent', 'absent must be boolean')), record=Record('matches')),
    Operation('match_forfeit', Operations._do_match, _audit_none,
              (('id', 'Unknown id'), ('side', 'side must be an integer from 0 to 1')),
              record=Record('matches')),
    Operation('revival_draw', Operations._do_revival, _audit_revival,
              (('confirm', 'Explicit confirmation required'),)),
    Operation('revival_undo', Operations._do_revival, _audit_revival,
              (('confirm', 'Explicit confirmation required'),), audit_before_write=True),
    Operation('tournament_rename', Operations._do_tournament_rename, _audit_night,
              (('name', 'name must contain 1–120 characters'), ('id', 'Unknown id'))),
    Operation('tournament_delete', Operations._do_tournament_delete, _audit_night,
              (('id', 'Unknown id'), ('confirm', 'Explicit confirmation required')),
              audit_before_write=True),
    Operation('tournament_hide', Operations._do_tournament_hide, _audit_night,
              (('id', 'Unknown id'), ('confirm', 'Explicit confirmation required'),
               ('hidden', 'hidden must be boolean'))),
    Operation('tournament_new', Operations._do_tournament_new, _audit_none,
              (('confirm', 'Explicit confirmation required'),), record=Record('history')),
    Operation('event_backfill', Operations._do_event_backfill, _audit_backfill,
              (('source', 'event object required'),)),
    Operation('vod_link', Operations._do_vod_link, _audit_vod,
              (('vodId', 'Expected a Twitch VOD id or https://www.twitch.tv/videos/<id> URL'),
               ('eventId', 'eventId must contain 1–120 characters'))),
    Operation('vod_unlink', Operations._do_vod_unlink, _audit_vod,
              (('vodId', 'Expected a Twitch VOD id or https://www.twitch.tv/videos/<id> URL'),
               ('eventId', 'eventId must contain 1–120 characters'))),
    Operation('source_add', Operations._do_source_add, _audit_none,
              (('url', 'Twitch URL must contain 1–500 characters'),), record=Record('sources')),
    Operation('source_delete', Operations._do_source_delete, _audit_none, (('id', 'Unknown id'),),
              record=Record('sources')),
    Operation('settings_update', Operations._do_settings_update, _audit_none),
    Operation('note_add', Operations._do_note_add, _audit_none,
              (('text', 'note must contain 1–4000 characters'),), record=Record('notes')),
    Operation('note_delete', Operations._do_note_delete, _audit_none, (('id', 'Unknown id'),),
              record=Record('notes')),
])

#: every action name the dispatcher accepts, in declaration order.
ACTION_NAMES = tuple(OPERATIONS)
