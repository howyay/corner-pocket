"""Persistent, server-authoritative pool operations; standard library only."""
import copy
import json
import os
import math
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


def text(value, name, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f'{name} must contain 1–{maximum} characters')
    return value.strip()


def tournament():
    return dict(id=uid(), name='', format='singles', tables=1, raceTo=1,
                entrants=[], matches=[], status='registration')


class Operations:
    # Share a lock across backend instances for the same store in this process.
    _locks = {}
    _locks_guard = threading.Lock()

    def __init__(self, root):
        self.path = Path(root).resolve() / 'out' / 'corner-pocket' / 'state.json'
        with self._locks_guard:
            self.lock = self._locks.setdefault(self.path, threading.RLock())

    def _load(self):
        if self.path.exists():
            state = json.loads(self.path.read_text())
            state.setdefault('events', [])
            return state
        return dict(revision=0, players=[], tournament=tournament(), history=[],
                    settings=dict(shotClock=30, autoFrame=False, clothColor='#1d5c44', lampGlow=0.22,
                                  showDiamonds=True), notes=[], sources=[dict(id=uid(), url='https://www.twitch.tv/examplechannel', kind='channel', channel='examplechannel')], events=[])

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
            context = self._event_context(state, payload)
            self._apply(state, payload)
            if payload.get('action') != 'tournament_new':
                context.update(self._event_context(state, payload))
            state['revision'] += 1
            state['events'] = (state['events'] + [dict(id=uid(), createdAt=timestamp(),
                revision=state['revision'], action=payload['action'], context=context)])[-500:]
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

    def _apply(self, s, p):
        action = p.get('action')
        t = s['tournament']
        if action == 'player_save':
            name = text(p.get('name'), 'name')
            if any(x['name'].casefold() == name.casefold() and x['id'] != p.get('id') for x in s['players']):
                raise ValueError('Player name already exists')
            player = self._find(s['players'], p['id']) if p.get('id') else dict(id=uid(), joinedAt=timestamp(), rating=0, status='Active')
            status = p.get('status', player['status'])
            if status not in ('Active', 'Visitor', 'Prospect', 'Inactive'):
                raise ValueError('Invalid player status')
            player.update(name=name, rating=integer(p.get('rating', player['rating']), 0, 1000, 'rating'), status=status)
            if 'notes' in p:
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
            t.update(format=fmt, tables=integer(p.get('tables', t['tables']), 1, 32, 'tables'),
                     raceTo=integer(p.get('raceTo', t['raceTo']), 1, 99, 'raceTo'))
            if 'name' in p:
                t['name'] = text(p['name'], 'name')
        elif action in ('entrant_add', 'entrant_remove', 'entrant_absence'):
            if t['status'] != 'registration':
                raise ValueError('Registration is closed')
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
            occupied = {m['name'].casefold() for e in t['entrants'] for m in e['members']}
            occupied_ids = {m['pid'] for e in t['entrants'] for m in e['members'] if m['pid']}
            result = []
            for member in members:
                if not isinstance(member, dict):
                    raise ValueError('Invalid member')
                if member.get('pid'):
                    player = self._find(s['players'], member['pid'])
                    if player['status'] == 'Inactive':
                        raise ValueError('Inactive player')
                    person = dict(pid=player['id'], name=player['name'])
                else:
                    person = dict(pid=None, name=text(member.get('name'), 'guest name'))
                    if any(player['name'].casefold() == person['name'].casefold() for player in s['players']):
                        raise ValueError('Player name already exists; select the regular by id')
                if person['name'].casefold() in occupied or person['pid'] and person['pid'] in occupied_ids:
                    raise ValueError('Person already registered')
                occupied.add(person['name'].casefold())
                if person['pid']:
                    occupied_ids.add(person['pid'])
                result.append(person)
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
        elif action == 'tournament_new':
            if p.get('confirm') is not True:
                raise ValueError('Explicit confirmation required')
            if t['entrants'] or t['matches']:
                archived = copy.deepcopy(t)
                archived['archivedAt'] = timestamp()
                s['history'].append(archived)
            s['tournament'] = tournament()
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
        elif action == 'note_add':
            s['notes'].append(dict(id=uid(), text=text(p.get('text'), 'note', 4000), createdAt=timestamp()))
        elif action == 'note_delete':
            s['notes'].remove(self._find(s['notes'], p.get('id')))
        else:
            raise ValueError('Unknown operations action')
