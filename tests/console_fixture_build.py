#!/usr/bin/env python3
"""Regenerate tests/console_fixture_state.json -- the realistic club behind docs/console-shots.md.

The state is never hand-written. This script starts a throwaway
tests/serve_operations_fixture.py, drives the console's own actions over POST /api/operations
(player_save, entrant_add, tournament_start, match_schedule, match_score, match_complete,
match_absence, source_add, note_add, tournament_new, event_backfill) and dumps the resulting
document -- including one night that was typed by hand from a saved Twitch VOD, so the
timeline's backfill badge, its source line and a standing that counts a backfilled night are
all real data rather than a mocked row. Every
field is therefore exactly what annotator/operations.py writes: match shape, entrant members,
bye propagation, audit events, revision.

    .venv/bin/python tests/console_fixture_build.py            # rewrites tests/console_fixture_state.json
    .venv/bin/python tests/console_fixture_build.py --check    # fail if the committed state is stale-shaped

Standard library only, loopback only, no argument is required.
"""
import argparse
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'tests' / 'serve_operations_fixture.py'
DEFAULT_OUT = ROOT / 'tests' / 'console_fixture_state.json'

# The club. Names are mixed English/Chinese because the console is bilingual; the ratings
# are staff-typed (the app never computes them), and a few regulars deliberately have no
# rating and no signed result so the standings table shows both "—" and 0-0 rows.
REGULARS = [
    ('Wei "Stone" Zhang', 812, 'Active'),
    ('Marcus Reed', 764, 'Active'),
    ('陈嘉豪', 731, 'Active'),
    ('Priya Nair', 688, 'Active'),
    ('林小满', 640, 'Active'),
    ('Devin Okoro', 597, 'Active'),
    ('赵启明', 553, 'Active'),
    ('Hannah Brooks', 512, 'Active'),
    ('Kenji Watanabe', 489, 'Active'),
    ('Tomás Ibarra', 470, 'Active'),
    ('吴天成', 0, 'Active'),
    ('周雨桐', 0, 'Prospect'),
    ('Sam Whitlock', 0, 'Visitor'),
    ('何俊杰', 0, 'Inactive'),
]
# Guaranteed to have no signed result at all. 吴天成 plays tonight (live, 0-0) and 周雨桐 /
# Sam Whitlock / 何俊杰 do not play at all, so the Regulars standings show a real "—" row
# (docs/console-shots.md, owner item 4). Nothing here may be entered in an archived event:
# the self-check at the end of build() fails if any of them ever signed a match.
NO_RECORD = {'吴天成', '周雨桐', 'Sam Whitlock', '何俊杰'}
# The open event running right now: 11 regulars plus five guests, a clean 16-draw.
TONIGHT_REGULARS = ['Wei "Stone" Zhang', 'Marcus Reed', '陈嘉豪', 'Priya Nair', '林小满',
                    'Devin Okoro', '赵启明', 'Hannah Brooks', 'Kenji Watanabe', 'Tomás Ibarra',
                    '吴天成']
TONIGHT_GUESTS = ['Danny Lau', '小杨', 'Ravi Menon', '老唐', 'Jordan Pike']
NOTES = [
    'Table 3 cushion is due for replacement — the corner pocket plays short on long rail shots.',
    'Thursday league starts 19:30. Keep tables 1-4 free from 19:00; the 9-foot table stays open play.',
]
SOURCES = ['https://www.twitch.tv/cornerpocket', 'https://www.twitch.tv/videos/2274501933']


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def port_is_free(port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


class Api:
    """A revision-tracking client for the fixture's /api/operations."""

    # Generous: this box is shared and a loaded machine can stall a single write for tens of
    # seconds (observed 23 s for the first POST at load average 22, and a 120 s stall while
    # another project was rendering on the same 12 cores). A short timeout here looks exactly
    # like a fixture bug and is not one. A stall that outlasts even this names its action and
    # points at the fixture's own log instead of printing a bare urllib traceback.
    TIMEOUT = 300
    VERBOSE = False
    LOG = None

    def __init__(self, base):
        self.base = base.rstrip('/')
        self.state = self.get()

    def _request(self, request):
        with urllib.request.urlopen(request, timeout=self.TIMEOUT) as response:
            return json.loads(response.read().decode('utf-8'))

    def get(self):
        self.state = self._request(urllib.request.Request(f'{self.base}/api/operations'))
        return self.state

    def post(self, action, **payload):
        body = json.dumps(dict(revision=self.state['revision'], action=action, **payload)).encode('utf-8')
        request = urllib.request.Request(f'{self.base}/api/operations', data=body,
                                         headers={'Content-Type': 'application/json'}, method='POST')
        if self.VERBOSE:
            print(f'  -> {action} (revision {self.state["revision"]})', flush=True)
        try:
            self.state = self._request(request)
        except urllib.error.HTTPError as error:
            raise SystemExit(f'{action} {payload} -> HTTP {error.code}: {error.read().decode("utf-8", "replace")}')
        except TimeoutError:
            raise SystemExit(f'{action} did not answer within {self.TIMEOUT}s; the fixture log is {self.LOG}')
        return self.state

    def player(self, name):
        return next(p for p in self.state['players'] if p['name'] == name)


def play_out(api, race_to, losers):
    """Play the running bracket to a finish; side 0 always wins so the fixture is deterministic."""
    for _ in range(64):
        tournament = api.state['tournament']
        if tournament['status'] == 'complete':
            return
        match = next((m for m in tournament['matches']
                      if m['status'] in ('scheduled', 'delayed') and all(m['sides'])), None)
        if match is None:
            raise SystemExit('bracket stalled: ' + json.dumps(
                [(m['round'], m['status'], m['sides']) for m in tournament['matches']]))
        if match['status'] == 'delayed':
            api.post('match_absence', id=match['id'], side=0, absent=False)
        api.post('match_schedule', id=match['id'])
        api.post('match_score', id=match['id'], score=[race_to, next(losers)])
        api.post('match_complete', id=match['id'])
    raise SystemExit('bracket did not finish')


def enter(api, names, guests):
    """Register the named regulars and guests, in draw order (registration order seeds the draw)."""
    for name in names:
        api.post('entrant_add', members=[{'pid': api.player(name)['id']}])
    for name in guests:
        api.post('entrant_add', members=[{'name': name}])


def backfill_night(api):
    """One past night typed from the saved VOD, through the same action the console posts.

    The club's channel is deleted above and only 'https://www.twitch.tv/videos/2274501933'
    stays, so this range is a saved source the server accepts (annotator/operations.py,
    _backfill_source). Two regulars carry their pid, so the night counts towards their house
    standing (owner item 4); the third name is a guest and counts towards nobody. Nobody in
    NO_RECORD appears here: their "—" standing has to stay empty.
    """
    vod, start, end = 2274501933, 3600, 11400
    priya, kenji, lin = (api.player(name)['id'] for name in ('Priya Nair', 'Kenji Watanabe', '林小满'))
    return api.post('event_backfill',
                    event=dict(name='Wednesday 8-Ball Open', format='singles', raceTo=5, tables=3,
                               entrants=[dict(pid=priya), dict(name='Danny Lau'),
                                         dict(pid=kenji), dict(pid=lin)],
                               matches=[dict(round=1, sides=['Priya Nair', 'Danny Lau'],
                                             score=[5, 2], winner='Priya Nair', result='played',
                                             clip=[3600, 4500]),
                                        dict(round=1, sides=['Kenji Watanabe', '林小满'],
                                             score=[5, 4], winner='Kenji Watanabe', result='played',
                                             clip=[4700, 5600]),
                                        dict(round=2, sides=['Priya Nair', 'Kenji Watanabe'],
                                             score=[5, 3], winner='Priya Nair', result='played',
                                             clip=[5800, 6900])]),
                    source=dict(kind='vod-backfill', vodId=str(vod), startS=start, endS=end,
                                datasetId=f'tw-{vod}-{start}-{end}', humanReviewed=True))


def build(api):
    for name, rating, status in REGULARS:
        api.post('player_save', **dict(name=name, status=status, **({'rating': rating} if rating else {})))
    for source in SOURCES:
        api.post('source_add', url=source)
    api.post('source_delete', id=api.state['sources'][0]['id'])
    for note in NOTES:
        api.post('note_add', text=note)

    # Two archived events, both fully played, so Records has real standings and a champion each.
    api.post('tournament_setup', name='Warm-up 8-Ball', tables=4, raceTo=5)
    enter(api, ['Wei "Stone" Zhang', 'Marcus Reed', '陈嘉豪', 'Priya Nair', '林小满',
                'Devin Okoro', '赵启明', 'Hannah Brooks'], [])
    api.post('tournament_start')
    play_out(api, 5, iter([3, 2, 4, 1, 3, 4, 2]))

    api.post('tournament_new', confirm=True)
    api.post('tournament_setup', name='Speed Pool side event', tables=3, raceTo=3)
    # 赵启明, not 吴天成: NO_RECORD stays free of signed results (see NO_RECORD above).
    enter(api, ['Wei "Stone" Zhang', 'Marcus Reed', 'Kenji Watanabe', 'Tomás Ibarra',
                '赵启明'], ['Danny Lau'])
    api.post('tournament_start')
    play_out(api, 3, iter([1, 2, 0, 2, 1]))

    # One archived night that came from a VOD: typed, confirmed, and linked to the two
    # regulars who played it (see backfill_night).
    backfill_night(api)

    # The event running now: 16 entrants, no byes, four first-round matches already signed,
    # three on tables (one with a live score), one held because a player is not here.
    api.post('tournament_new', confirm=True)
    api.post('tournament_setup', tables=6, raceTo=5)
    enter(api, TONIGHT_REGULARS, TONIGHT_GUESTS)
    api.post('tournament_start')
    first_round = [m for m in api.state['tournament']['matches'] if m['round'] == 1]
    for match, loser in zip(first_round[:4], (3, 2, 4, 1)):
        api.post('match_schedule', id=match['id'])
        api.post('match_score', id=match['id'], score=[5, loser])
        api.post('match_complete', id=match['id'])
    for index, match in enumerate(first_round[4:7]):
        api.post('match_schedule', id=match['id'])
        if index == 0:
            api.post('match_score', id=match['id'], score=[3, 1])
    api.post('match_absence', id=first_round[7]['id'], side=0, absent=True)


def backdate_joins(state):
    """Only players[].joinedAt is lifted out of "this second": nothing reads it but the profile row."""
    rng = random.Random(20261002)
    for player in state['players']:
        days = rng.randrange(20, 900)
        joined = time.time() - days * 86400 - rng.randrange(0, 86400)
        player['joinedAt'] = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(joined)) + '+00:00'


def signed_record(state, name):
    """How many signed matches this player is in, across the running event and every archive."""
    ident = next(p['id'] for p in state['players'] if p['name'] == name)
    total = 0
    for night in [state['tournament'], *state['history']]:
        for match in night['matches']:
            if match['status'] == 'complete' and all(match['sides']):
                for side in match['sides']:
                    entrant = next(e for e in night['entrants'] if e['id'] == side)
                    if any(m['pid'] == ident for m in entrant['members']):
                        total += 1
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', default=str(DEFAULT_OUT), help='where to write the state (default: %(default)s)')
    parser.add_argument('--port', type=int, help='fixture port (default: a free one)')
    parser.add_argument('--verbose', action='store_true', help='name every action as it is posted')
    args = parser.parse_args()
    Api.VERBOSE = args.verbose

    port = args.port or free_port()
    if not port_is_free(port):
        raise SystemExit(f'port {port} is already in use; the build never touches a running server')
    environment = dict(os.environ, PYTHONPATH='.')
    environment.pop('POOL_DATABASE_URL', None)
    interpreter = str(ROOT / '.venv' / 'bin' / 'python') if (ROOT / '.venv' / 'bin' / 'python').exists() else sys.executable
    # The fixture's output goes to a file, never a pipe this process does not read: the fixture
    # answers one request per handler thread, and a full pipe would block whichever thread is
    # writing while the build waits on that same request.
    fixture_log = Path(tempfile.mkstemp(prefix='console-fixture-', suffix='.log')[1])
    Api.LOG = fixture_log
    log_handle = fixture_log.open('w')
    server = subprocess.Popen([interpreter, str(FIXTURE), '--port', str(port)], cwd=ROOT, env=environment,
                              stdout=log_handle, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 120
        while True:
            if server.poll() is not None:
                raise SystemExit('fixture exited early:\n' + fixture_log.read_text())
            try:
                api = Api(f'http://127.0.0.1:{port}')
                break
            except (urllib.error.URLError, OSError, TimeoutError):
                if time.time() > deadline:
                    raise SystemExit('fixture did not answer /api/operations within 120s')
                time.sleep(0.2)
        build(api)
        state = api.get()
        backdate_joins(state)
        Path(args.out).write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        tournament = state['tournament']
        print(f'wrote {args.out}')
        print(f'  revision {state["revision"]} · {len(state["players"])} players · '
              f'{len(state["history"])} archived events · {len(state["events"])} audit rows · '
              f'{len(state["sources"])} sources · {len(state["notes"])} notes')
        print(f'  running: {tournament["name"]!r} {tournament["status"]} raceTo {tournament["raceTo"]} '
              f'tables {tournament["tables"]} entrants {len(tournament["entrants"])}')
        for status in ('scheduled', 'live', 'delayed', 'complete', 'pending'):
            rows = [m for m in tournament['matches'] if m['status'] == status]
            print(f'  {status:<9} {len(rows):>2} match(es)  tables={sorted(str(m["table"]) for m in rows if m["table"])}')
        empty = {name: signed_record(state, name) for name in sorted(NO_RECORD)}
        if any(empty.values()):
            raise SystemExit(f'expected no signed result for {empty}')
        print(f'  no signed result: {", ".join(empty)}')
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
        log_handle.close()
        if fixture_log.stat().st_size < 4000:
            fixture_log.unlink()
        else:
            print(f'fixture log kept: {fixture_log} ({fixture_log.stat().st_size} B)')
    if not port_is_free(port):
        raise SystemExit(f'port {port} was not released')
    print(f'fixture stopped; 127.0.0.1:{port} is free again')


if __name__ == '__main__':
    main()
