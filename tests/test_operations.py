"""Fixture-only operations invariants; python -m unittest discover -s tests."""
import json
from pathlib import Path
import random
import tempfile
import threading
import unittest
from unittest.mock import patch

from annotator.operations import ConflictError, Operations


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ops = Operations(self.root)

    def call(self, action, **fields):
        return self.ops.post(dict(action=action, revision=self.ops.get()['revision'], **fields))

    def register(self, count, race_to=7):
        self.call('tournament_setup', raceTo=race_to)
        for n in range(count):
            self.call('entrant_add', members=[{'name': f'Guest {n}'}])
        return self.call('tournament_start')

    def test_empty_and_persistent(self):
        self.assertEqual(self.ops.get()['players'], [])
        self.assertEqual(self.ops.get()['tournament']['matches'], [])
        state = self.call('player_save', name='Ada', rating=600)
        self.assertEqual(Operations(self.root).get(), state)
        self.assertEqual(json.loads(self.ops.path.read_text()), state)

    def test_player_notes_persist_without_entering_audit(self):
        state = self.call('player_save', name='Ada', notes='Private coaching note <b>literal</b>')
        player = state['players'][0]
        self.assertEqual(Operations(self.root).get()['players'][0]['notes'], player['notes'])
        self.assertNotIn('Private coaching note', json.dumps(state['events']))
        state = self.call('player_save', id=player['id'], name='Ada', notes='')
        self.assertEqual(state['players'][0]['notes'], '')
        before = self.ops.path.read_bytes()
        with self.assertRaises(ValueError):
            self.call('player_save', id=player['id'], name='Ada', notes='x' * 4001)
        self.assertEqual(self.ops.path.read_bytes(), before)

    def test_player_rating_is_optional_but_validated_when_present(self):
        for n, extra in enumerate(({}, {'rating': None}, {'rating': ''})):
            state = self.call('player_save', name=f'New {n}', **extra)
            self.assertEqual(state['players'][-1]['rating'], 0)
        state = self.call('player_save', name='Rated', rating=640, status=None)
        ada = state['players'][-1]
        self.assertEqual((ada['rating'], ada['status']), (640, 'Active'))
        before = self.ops.path.read_bytes()
        for bad in ('abc', -5, 1001, 12.5, True, ' '):
            with self.assertRaisesRegex(ValueError, 'rating must be an integer from 0 to 1000'):
                self.call('player_save', name='Bad', rating=bad)
            with self.assertRaisesRegex(ValueError, 'rating must be an integer from 0 to 1000'):
                self.call('player_save', id=ada['id'], name='Rated', rating=bad)
        self.assertEqual(self.ops.path.read_bytes(), before)
        for extra in ({}, {'rating': None}, {'rating': ''}):
            state = self.call('player_save', id=ada['id'], name='Rated', notes=None, **extra)
            self.assertEqual(state['players'][-1]['rating'], 640)

    def test_concurrency_and_validation_do_not_write(self):
        self.call('note_add', text='First')
        before = self.ops.path.read_bytes()
        with self.assertRaises(ConflictError):
            self.ops.post({'action': 'note_add', 'revision': 0, 'text': 'Stale'})
        for payload in ([], {'revision': True}, {'revision': 1, 'action': 'wat'},
                        {'revision': 1, 'action': 'settings_update', 'shotClock': True},
                        {'revision': 1, 'action': 'settings_update', 'publicBoard': 'off'}):
            with self.assertRaises(ValueError):
                self.ops.post(payload)
        self.assertEqual(self.ops.path.read_bytes(), before)

    def test_same_path_instances_serialize(self):
        self.call('note_add', text='Start')
        revision = self.ops.get()['revision']
        outcomes = []
        def save():
            try:
                Operations(self.root).post(dict(action='note_add', text='Race', revision=revision))
                outcomes.append('ok')
            except ConflictError:
                outcomes.append('conflict')
        threads = [threading.Thread(target=save) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(outcomes, ['ok', 'conflict'])

    def test_doubles_and_player_history(self):
        state = self.call('player_save', name='Ada')
        pid = state['players'][0]['id']
        self.call('tournament_setup', format='doubles')
        with self.assertRaises(ValueError):
            self.call('entrant_add', members=[{'pid': pid}])
        state = self.call('entrant_add', members=[{'pid': pid}, {'name': 'Guest'}])
        for members in ([{'pid': pid}, {'name': 'Other'}], [{'name': 'guest'}, {'name': 'Other'}]):
            with self.assertRaises(ValueError):
                self.call('entrant_add', members=members)
        with self.assertRaises(ValueError):
            self.call('player_delete', id=pid)
        with self.assertRaises(ValueError):
            self.call('tournament_setup', format='singles')
        self.call('player_save', id=pid, name='Ada', status='Inactive')
        self.call('entrant_remove', id=state['tournament']['entrants'][0]['id'])
        self.call('player_delete', id=pid)

    def test_doubles_parallel_tables_release_and_archive(self):
        self.call('tournament_setup', name='Doubles night', format='doubles', tables=2, raceTo=1)
        for n in range(4):
            self.call('entrant_add', members=[{'name': f'Team {n} A'}, {'name': f'Team {n} B'}])
        state = self.call('tournament_start')
        opening = [m for m in state['tournament']['matches'] if m['round'] == 1]
        for match in opening:
            state = self.call('match_schedule', id=match['id'])
        self.assertEqual({m['table'] for m in state['tournament']['matches'] if m['status'] == 'live'}, {1, 2})
        self.call('match_score', id=opening[0]['id'], score=[1, 0])
        state = self.call('match_unschedule', id=opening[0]['id'])
        released = next(m for m in state['tournament']['matches'] if m['id'] == opening[0]['id'])
        self.assertEqual(released['score'], [1, 0])
        self.call('match_schedule', id=opening[0]['id'])
        self.call('match_complete', id=opening[0]['id'])
        self.call('match_score', id=opening[1]['id'], score=[0, 1])
        state = self.call('match_complete', id=opening[1]['id'])
        final = next(m for m in state['tournament']['matches'] if m['round'] == 2)
        self.assertTrue(all(final['sides']))
        self.call('match_schedule', id=final['id'])
        self.call('match_score', id=final['id'], score=[1, 0])
        completed = self.call('match_complete', id=final['id'])['tournament']
        self.assertEqual(completed['status'], 'complete')
        state = self.call('tournament_new', confirm=True)
        self.assertEqual(state['history'][-1]['matches'], completed['matches'])
        self.assertEqual(state['history'][-1]['entrants'], completed['entrants'])
        self.assertEqual(Operations(self.root).get(), state)

    def test_all_bracket_sizes_finish_once(self):
        for count in (2, 3, 4, 5, 6, 7, 8, 9, 17):
            with self.subTest(count=count):
                self.call('tournament_new', confirm=True)
                state = self.register(count)
                played = 0
                while state['tournament']['status'] != 'complete':
                    match = next(m for m in state['tournament']['matches'] if m['status'] == 'scheduled')
                    self.call('match_schedule', id=match['id'])
                    self.call('match_score', id=match['id'], score=[7, 2])
                    state = self.call('match_complete', id=match['id'])
                    played += 1
                self.assertEqual(played, count - 1)
                self.assertTrue(state['tournament']['matches'][-1]['winnerId'])
                with self.assertRaises(ValueError):
                    self.call('match_score', id=match['id'], score=[0, 0])

    def test_tables_absence_and_forfeit(self):
        state = self.register(4)
        first, second = state['tournament']['matches'][:2]
        self.call('match_schedule', id=first['id'])
        with self.assertRaisesRegex(ValueError, '^All tables are in use$'):
            self.call('match_schedule', id=second['id'])
        with self.assertRaisesRegex(ValueError, 'table must be an integer from 1 to 1'):
            self.call('match_schedule', id=second['id'], table=2)
        self.call('match_absence', id=first['id'], side=0, absent=True)
        with self.assertRaises(ValueError):
            self.call('match_schedule', id=first['id'])
        self.call('match_schedule', id=second['id'])
        state = self.call('match_forfeit', id=first['id'], side=0)
        self.assertEqual(state['tournament']['matches'][0]['winnerId'], first['sides'][1])
        self.assertEqual(state['tournament']['matches'][0]['result'], 'forfeit')

    def test_score_and_started_registration_guards(self):
        state = self.register(2)
        ident = state['tournament']['matches'][0]['id']
        for action, kwargs in [('tournament_start', {}), ('tournament_setup', {'tables': 2}),
                               ('entrant_add', {'members': [{'name': 'Late'}]}),
                               ('match_score', {'id': ident, 'score': [7, 0]})]:
            with self.assertRaises(ValueError):
                self.call(action, **kwargs)
        self.call('match_schedule', id=ident)
        for score in ([7, 7], [-1, 0], [True, 0], [8, 1], [0], '7,0'):
            with self.assertRaises(ValueError):
                self.call('match_score', id=ident, score=score)
        with self.assertRaises(ValueError):
            self.call('match_complete', id=ident)

    def test_reset_archive_notes_settings(self):
        old = self.register(3)['tournament']
        with self.assertRaises(ValueError):
            self.call('tournament_new')
        state = self.call('tournament_new', confirm=True)
        self.assertEqual(state['history'][0]['matches'], old['matches'])
        self.assertEqual(state['tournament']['matches'], [])
        state = self.call('settings_update', shotClock=45, autoFrame=True)
        self.assertEqual(state['settings']['shotClock'], 45)
        self.assertTrue(state['settings']['autoFrame'])
        state = self.call('note_add', text='<script>literal text</script>')
        state = self.call('note_delete', id=state['notes'][0]['id'])
        self.assertEqual(state['notes'], [])

    def test_sources_and_presentation_settings(self):
        # examplechannel is seeded in fresh state; adding it again is rejected.
        seeded = [s for s in self.ops.get()['sources'] if s.get('channel') == 'examplechannel']
        self.assertEqual(len(seeded), 1)
        with self.assertRaises(ValueError):
            self.call('source_add', url='https://twitch.tv/examplechannel')
        state = self.call('source_add', url='https://www.twitch.tv/videos/12345')
        self.assertEqual(state['sources'][-1]['video'], '12345')
        for url in ('http://twitch.tv/a', 'https://twitch.tv.evil/a', 'https://twitch.tv@evil/a',
                    'https://twitch.tv:443/a', 'https://twitch.tv/a?x=y', 'https://twitch.tv/directory',
                    'https://twitch.tv/videos/no', 'https://twitch.tv/examplechannel'):
            with self.assertRaises(ValueError):
                self.call('source_add', url=url)
        state = self.call('source_delete', id=state['sources'][0]['id'])
        self.assertEqual(len(state['sources']), 1)
        state = self.call('settings_update', clothColor='#1f4a70', lampGlow=0.5, showDiamonds=False)
        self.assertEqual(state['settings']['lampGlow'], 0.5)
        for settings in ({'lampGlow': float('nan')}, {'lampGlow': True}, {'lampGlow': 1},
                         {'showDiamonds': 1}, {'publicBoard': 'on'}, {'clothColor': 'red'}):
            with self.assertRaises(ValueError):
                self.call('settings_update', **settings)

    def test_public_board_switch_defaults_on_rejects_non_booleans_and_round_trips(self):
        # The public board's only control (docs/public-board.md, "Board off" and 6): a boolean
        # setting whose false makes GET /api/board answer {"board":"off"}.
        self.assertIs(self.ops.get()['settings']['publicBoard'], True)
        state = self.call('settings_update', shotClock=45)  # writes the document for the first time
        self.assertIs(state['settings']['publicBoard'], True)
        state = self.call('settings_update', publicBoard=False)
        self.assertIs(state['settings']['publicBoard'], False)
        self.assertIs(json.loads(self.ops.path.read_text())['settings']['publicBoard'], False)
        self.assertIs(Operations(self.root).get()['settings']['publicBoard'], False)
        before = self.ops.path.read_bytes()
        for bad in ('off', 'false', 'on', 1, 0, None, [], {}):
            with self.assertRaisesRegex(ValueError, 'publicBoard must be boolean'):
                self.call('settings_update', publicBoard=bad)
        self.assertEqual(self.ops.path.read_bytes(), before)
        # A document written before the switch existed has no key, and the read side asks
        # `is False` (annotator/public_board.py), so a missing key is on, not off.
        old = json.loads(self.ops.path.read_text())
        del old['settings']['publicBoard']
        self.ops.path.write_text(json.dumps(old))
        self.assertNotIn('publicBoard', Operations(self.root).get()['settings'])
        state = self.call('settings_update', publicBoard=True)
        self.assertIs(state['settings']['publicBoard'], True)
        self.assertIs(Operations(self.root).get()['settings']['publicBoard'], True)

    def test_guest_promotion_after_start_preserves_history_and_competition(self):
        self.register(2)
        self.call('tournament_new', confirm=True)
        before = self.register(2)
        state = self.call('guest_promote', name='  GUEST 0 ')
        player = state['players'][0]
        self.assertEqual(player['name'], 'Guest 0')
        self.assertEqual(player['rating'], 0)
        self.assertEqual(player['status'], 'Active')
        self.assertEqual(state['tournament']['entrants'][0]['members'][0]['pid'], player['id'])
        self.assertEqual(state['tournament']['matches'], before['tournament']['matches'])
        self.assertEqual(state['history'], before['history'])
        saved = self.ops.path.read_bytes()
        for name in ('Guest 0', 'Missing'):
            with self.assertRaises(ValueError):
                self.call('guest_promote', name=name)
        self.assertEqual(self.ops.path.read_bytes(), saved)
        self.assertEqual(len(Operations(self.root).get()['players']), 1)

    def test_guest_promotion_rejects_existing_roster_name(self):
        self.call('entrant_add', members=[{'name': 'Ada'}])
        with self.assertRaisesRegex(ValueError, 'guest in this event'):
            self.call('player_save', name='ADA')
        # A store written before that guard can still hold the collision: build it by hand.
        legacy = json.loads(self.ops.path.read_text())
        legacy['players'].append(dict(id='legacy', name='ADA', joinedAt='2026-01-01T00:00:00+00:00', rating=0, status='Active'))
        self.ops.path.write_text(json.dumps(legacy))
        before = self.ops.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'cannot infer guest identity'):
            self.call('guest_promote', name='ada')
        self.assertEqual(self.ops.path.read_bytes(), before)
        self.assertIsNone(self.ops.get()['tournament']['entrants'][0]['members'][0]['pid'])

    def test_event_audit_persists_order_without_private_content(self):
        self.assertEqual(self.ops.get()['events'], [])
        first = self.call('player_save', name='Ada', notes='private player note')
        second = self.call('note_add', text='private desk note')
        third = self.call('settings_update', shotClock=40)
        events = third['events']
        self.assertEqual([e['action'] for e in events], ['player_save', 'note_add', 'settings_update'])
        self.assertEqual([e['revision'] for e in events], [1, 2, 3])
        self.assertEqual([e['createdAt'] for e in events], sorted(e['createdAt'] for e in events))
        self.assertEqual(events[0]['context'], {'id': first['players'][0]['id'], 'name': 'Ada'})
        self.assertEqual(events[1]['context'], {'id': second['notes'][0]['id']})
        self.assertNotIn('private', json.dumps(events))
        self.assertEqual(Operations(self.root).get()['events'], events)
        before = self.ops.path.read_bytes()
        with self.assertRaises(ValueError):
            self.call('note_add', text='')
        self.assertEqual(self.ops.path.read_bytes(), before)
        self.assertEqual(self.ops.get()['events'], events)

    def test_event_legacy_default_and_bounded_history(self):
        state = self.call('settings_update', shotClock=40)
        del state['events']
        self.ops.path.write_text(json.dumps(state))
        self.assertEqual(self.ops.get()['events'], [])
        state['revision'] = 500
        state['events'] = [dict(id=str(n), action='settings_update', revision=n,
                                createdAt='2026-01-01T00:00:00+00:00', context={}) for n in range(1, 501)]
        self.ops.path.write_text(json.dumps(state))
        events = self.call('settings_update', shotClock=45)['events']
        self.assertEqual(len(events), 500)
        self.assertEqual(events[0]['revision'], 2)
        self.assertEqual(events[-1]['revision'], 501)

    def test_atomic_failure_keeps_previous_state(self):
        self.call('note_add', text='Saved')
        before = self.ops.path.read_bytes()
        with patch('annotator.operations.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                self.call('note_add', text='Not saved')
        self.assertEqual(self.ops.path.read_bytes(), before)
        self.assertEqual(list(self.ops.path.parent.glob('.state-*')), [])


    def test_release_table_preserves_score_and_other_match(self):
        self.call('tournament_setup', tables=2)
        state = self.register(4)
        first, second = state['tournament']['matches'][:2]
        self.call('match_schedule', id=first['id'], table=1)
        self.call('match_schedule', id=second['id'], table=2)
        self.call('match_score', id=first['id'], score=[2, 1])
        state = self.call('match_unschedule', id=first['id'])
        released, untouched = state['tournament']['matches'][:2]
        self.assertEqual((released['status'], released['table'], released['score']),
                         ('scheduled', None, [2, 1]))
        self.assertEqual((untouched['status'], untouched['table']), ('live', 2))
        state = self.call('match_schedule', id=first['id'], table=1)
        self.assertEqual(state['tournament']['matches'][0]['score'], [2, 1])

    def test_registration_absence_propagates_through_bye_and_returns(self):
        for name in ('Ada', 'Bo', 'Cy'):
            self.call('entrant_add', members=[{'name': name}])
        entrant = self.ops.get()['tournament']['entrants'][0]
        self.call('entrant_absence', id=entrant['id'], absent=True)
        state = self.call('tournament_start')
        opening = next(m for m in state['tournament']['matches'] if m['status'] == 'scheduled')
        self.call('match_forfeit', id=opening['id'], side=0)
        final = self.ops.get()['tournament']['matches'][-1]
        self.assertEqual(final['absent'], [entrant['id']])
        self.assertEqual(final['status'], 'delayed')
        before = self.ops.path.read_bytes()
        with self.assertRaises(ValueError):
            self.call('match_schedule', id=final['id'])
        self.assertEqual(before, self.ops.path.read_bytes())
        state = self.call('match_absence', id=final['id'], side=0, absent=False)
        self.assertFalse(state['tournament']['entrants'][0]['absent'])
        self.call('match_schedule', id=final['id'])

    def test_absence_validation_and_closed_registration_are_atomic(self):
        state = self.call('entrant_add', members=[{'name': 'Ada'}])
        ident = state['tournament']['entrants'][0]['id']
        before = self.ops.path.read_bytes()
        with self.assertRaises(ValueError):
            self.call('entrant_absence', id=ident, absent=1)
        self.assertEqual(before, self.ops.path.read_bytes())
        self.call('entrant_add', members=[{'name': 'Bo'}])
        self.call('tournament_start')
        with self.assertRaises(ValueError):
            self.call('entrant_absence', id=ident, absent=True)

    def test_placeholder_guest_names_are_refused(self):
        """R5: a bye is recorded by the draw, never typed in as a player."""
        before = self.ops.path.read_bytes() if self.ops.path.exists() else None
        for name in ('NA', ' n/a ', 'N/A', 'Bye', 'BYE', 'tbd', 'TBD ', '轮空', '輪空', ' 轮空 '):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, '^A bye is added by the draw; type the guest\'s real name$'):
                    self.call('entrant_add', members=[{'name': name}])
        self.assertEqual(before, self.ops.path.read_bytes() if self.ops.path.exists() else None)
        self.call('tournament_setup', format='doubles')
        with self.assertRaisesRegex(ValueError, 'A bye is added by the draw'):
            self.call('entrant_add', members=[{'name': 'Ada'}, {'name': 'tbd'}])
        self.assertEqual(self.ops.get()['tournament']['entrants'], [])
        # names that merely contain the letters stay valid
        for name in ('Nadia', 'Byers', 'Na Li'):
            self.call('entrant_add', members=[{'name': name}, {'name': name + ' 2'}])
        self.assertEqual(len(self.ops.get()['tournament']['entrants']), 3)

    def test_bye_matches_are_never_signed_results(self):
        """R5: a bye completes with result 'bye' and one side; it is not a played match."""
        state = self.register(5)
        byes = [m for m in state['tournament']['matches'] if m.get('result') == 'bye']
        self.assertEqual(len(byes), 3)
        for match in byes:
            self.assertEqual(sum(1 for side in match['sides'] if side), 1)
            self.assertNotIn('completedAt', match)
            with self.assertRaises(ValueError):
                self.call('match_forfeit', id=match['id'], side=0)

    def test_guest_name_cannot_alias_regular(self):
        self.call('player_save', name='Ada', rating=500)
        before = self.ops.path.read_bytes()
        with self.assertRaises(ValueError):
            self.call('entrant_add', members=[{'name': ' ADA '}])
        self.assertEqual(before, self.ops.path.read_bytes())

    def test_renamed_regular_cannot_enter_twice(self):
        state = self.call('player_save', name='Ada')
        pid = state['players'][0]['id']
        self.call('entrant_add', members=[{'pid': pid}])
        self.call('player_save', id=pid, name='Ada renamed')
        before = self.ops.path.read_bytes()
        with self.assertRaises(ValueError):
            self.call('entrant_add', members=[{'pid': pid}])
        self.assertEqual(before, self.ops.path.read_bytes())

    def test_regular_cannot_take_a_current_guest_name(self):
        """R12: two different people must never read the same in tonight's draw."""
        state = self.call('player_save', name='Ada')
        pid = state['players'][0]['id']
        self.call('entrant_add', members=[{'name': 'Walk-in Wu'}])
        before = self.ops.path.read_bytes()
        for name in ('Walk-in Wu', ' walk-in wu '):
            with self.assertRaisesRegex(ValueError, '^Name held by a guest in this event; add the guest to the regulars instead$'):
                self.call('player_save', id=pid, name=name)
            with self.assertRaisesRegex(ValueError, 'guest in this event'):
                self.call('player_save', name=name)
        self.assertEqual(before, self.ops.path.read_bytes())
        # an archived guest no longer blocks the name, and the regular keeps their own name
        self.call('player_save', id=pid, name='Ada')
        self.call('entrant_add', members=[{'name': 'Bo'}])
        self.call('tournament_start')
        self.call('tournament_new', confirm=True)
        self.assertEqual(self.call('player_save', id=pid, name='Walk-in Wu')['players'][0]['name'], 'Walk-in Wu')

    def test_rename_between_rounds_keeps_champion_stats_and_every_match(self):
        """R12 property: renaming never detaches a player from their matches or stats.

        Same seeds, same scores; the only difference is a rename of every regular after
        round 1. The champion, the per-player W-L and every match's sides are identical,
        and the stored entrant snapshot is never rewritten (ids stay authoritative)."""
        def run(rename):
            self.call('tournament_new', confirm=True)
            state = self.call('tournament_setup', raceTo=7)
            ids = {p['name'].split(' ')[0]: p['id'] for p in state['players']}
            for name in ('Ada', 'Bo', 'Cy', 'Di', 'Eve'):
                self.call('entrant_add', members=[{'pid': ids[name]}])
            self.call('entrant_add', members=[{'name': 'Walk-in Wu'}])
            state = self.call('tournament_start')
            renamed = False
            while state['tournament']['status'] != 'complete':
                match = next(m for m in state['tournament']['matches'] if m['status'] == 'scheduled')
                if rename and match['round'] == 2 and not renamed:
                    for player in list(state['players']):
                        state = self.call('player_save', id=player['id'], name=player['name'] + f' #{rename}')
                    renamed = True
                self.call('match_schedule', id=match['id'])
                self.call('match_score', id=match['id'], score=[7, 3])
                state = self.call('match_complete', id=match['id'])
            self.assertEqual(renamed, bool(rename))
            t = state['tournament']
            by_pid = {m['pid']: e['id'] for e in t['entrants'] for m in e['members'] if m['pid']}
            names = {e['id']: e['members'][0]['name'] for e in t['entrants']}
            final = t['matches'][-1]
            stats = {}
            for pid, eid in by_pid.items():
                won = sum(1 for m in t['matches'] if m.get('result') == 'played' and m['winnerId'] == eid)
                lost = sum(1 for m in t['matches'] if m.get('result') == 'played' and eid in m['sides'] and m['winnerId'] != eid)
                stats[pid] = (won, lost)
            return dict(champion=names[final['winnerId']], stats=stats,
                        sides=[[names.get(s) for s in m['sides']] for m in t['matches']],
                        results=[(m['result'], m['score']) for m in t['matches']])

        for name in ('Ada', 'Bo', 'Cy', 'Di', 'Eve'):
            self.call('player_save', name=name)
        plain = run(rename=None)
        for player in self.ops.get()['players']:
            self.call('player_save', id=player['id'], name=player['name'].split(' ')[0])
        renamed = run(rename=1)
        self.assertEqual(plain, renamed)
        state = self.call('tournament_new', confirm=True)
        self.assertEqual(len(state['history']), 2)
        # the archived snapshot keeps the draw-time name; the id links it to the live roster
        roster = {p['id']: p['name'] for p in state['players']}
        archived = state['history'][-1]
        linked = [m for e in archived['entrants'] for m in e['members'] if m['pid']]
        self.assertEqual(len(linked), 5)
        self.assertTrue(all(roster[m['pid']] == m['name'] + ' #1' for m in linked))

    def test_registration_absence_holds_first_round(self):
        self.call('entrant_add', members=[{'name': 'Ada'}])
        state = self.call('entrant_add', members=[{'name': 'Bo'}])
        ident = state['tournament']['entrants'][1]['id']
        self.call('entrant_absence', id=ident, absent=True)
        state = self.call('tournament_start')
        match = state['tournament']['matches'][0]
        self.assertEqual((match['status'], match['absent']), ('delayed', [ident]))
        state = self.call('match_forfeit', id=match['id'], side=1)
        self.assertEqual(state['tournament']['status'], 'complete')
        self.assertNotEqual(state['tournament']['matches'][0]['winnerId'], ident)

    def test_archive_audit_identifies_archived_tournament(self):
        self.register(2)
        old = self.ops.get()['tournament']['id']
        state = self.call('tournament_new', confirm=True)
        self.assertEqual(state['history'][0]['id'], old)
        self.assertEqual(state['events'][-1]['context']['id'], old)
        self.assertNotEqual(state['tournament']['id'], old)

    def test_an_archived_event_always_has_a_name(self):
        """R2: no path through the API archives a nameless event, and the audit line names it."""
        # racked without ever saving the form, then archived
        state = self.register(3)
        self.assertTrue(state['tournament']['name'].strip(), 'the draw fills a name the operator never saved')
        state = self.call('tournament_new', confirm=True)
        self.assertTrue(state['history'][-1]['name'].strip())
        self.assertEqual(state['events'][-1]['context']['name'], state['history'][-1]['name'])
        # archived during registration, never racked
        self.call('entrant_add', members=[{'name': 'Ada'}])
        state = self.call('tournament_new', confirm=True)
        self.assertTrue(state['history'][-1]['name'].strip())
        self.assertNotEqual(state['events'][-1]['context']['name'], '')
        # a saved name is kept exactly
        self.call('tournament_setup', name='Friday 8-Ball')
        self.register(2)
        state = self.call('tournament_new', confirm=True)
        self.assertEqual(state['history'][-1]['name'], 'Friday 8-Ball')
        self.assertTrue(all(night['name'].strip() for night in state['history']))

    def test_delete_only_an_event_with_no_signed_result(self):
        """R1: a mistaken event can be removed while nothing was signed; never after."""
        # current event in registration: delete resets it, nothing archived
        self.call('tournament_setup', name='Oops')
        self.call('entrant_add', members=[{'name': 'Ada'}])
        old = self.ops.get()['tournament']['id']
        with self.assertRaisesRegex(ValueError, '^Explicit confirmation required$'):
            self.call('tournament_delete', id=old)
        state = self.call('tournament_delete', id=old, confirm=True)
        self.assertEqual((state['tournament']['entrants'], state['tournament']['name'], state['history']), ([], '', []))
        self.assertNotEqual(state['tournament']['id'], old)
        self.assertEqual(state['events'][-1]['action'], 'tournament_delete')
        self.assertEqual(state['events'][-1]['context'], {'id': old, 'name': 'Oops'})
        # an unplayed draw (byes only) is still deletable; it was archived by mistake
        self.call('tournament_setup', name='Empty draw')
        self.register(3)
        state = self.call('tournament_new', confirm=True)
        archived = state['history'][-1]['id']
        self.assertTrue(any(m.get('result') == 'bye' for m in state['history'][-1]['matches']))
        state = self.call('tournament_delete', id=archived, confirm=True)
        self.assertEqual(state['history'], [])
        self.assertEqual(state['events'][-1]['context'], {'id': archived, 'name': 'Empty draw'})
        # one signed result (played or forfeit) makes it permanent: current and archived
        for finish in ('match_complete', 'match_forfeit'):
            with self.subTest(finish=finish):
                state = self.register(2)
                match = state['tournament']['matches'][0]
                if finish == 'match_complete':
                    self.call('match_schedule', id=match['id'])
                    self.call('match_score', id=match['id'], score=[7, 1])
                    self.call('match_complete', id=match['id'])
                else:
                    self.call('match_forfeit', id=match['id'], side=1)
                current = self.ops.get()['tournament']['id']
                saved = self.ops.path.read_bytes()
                with self.assertRaisesRegex(ValueError, '^An event with a signed result cannot be deleted; hide it from history instead$'):
                    self.call('tournament_delete', id=current, confirm=True)
                self.assertEqual(self.ops.path.read_bytes(), saved)
                archived = self.call('tournament_new', confirm=True)['history'][-1]['id']
                with self.assertRaisesRegex(ValueError, 'cannot be deleted'):
                    self.call('tournament_delete', id=archived, confirm=True)
        with self.assertRaisesRegex(ValueError, '^Unknown id$'):
            self.call('tournament_delete', id='missing', confirm=True)

    def play_round_one(self, count):
        """Register `count` guests, rack, and sign every played round-1 match 7-2 (side A wins)."""
        state = self.register(count)
        for match in [m for m in state['tournament']['matches'] if m['round'] == 1 and m.get('result') != 'bye']:
            self.call('match_schedule', id=match['id'])
            self.call('match_score', id=match['id'], score=[7, 2])
            state = self.call('match_complete', id=match['id'])
        return state

    def test_revival_draw_fills_a_bye_and_is_audited(self):
        """R6: a seeded draw picks WHO re-enters (into a round-1 bye whose winner has not
        played round 2); it never writes a result and never changes a signed one."""
        state = self.play_round_one(6)  # 6 entrants: 2 byes, 2 played round-1 matches
        t = state['tournament']
        signed_before = {m['id']: json.dumps(m, sort_keys=True) for m in t['matches'] if m.get('result') in ('played', 'forfeit')}
        losers = sorted(next(side for side in m['sides'] if side != m['winnerId'])
                        for m in t['matches'] if m['round'] == 1 and m.get('result') == 'played')
        with self.assertRaisesRegex(ValueError, '^Explicit confirmation required$'):
            self.call('revival_draw')
        before_draw = json.loads(json.dumps(t['matches']))
        state = self.call('revival_draw', confirm=True)
        t = state['tournament']
        event = state['events'][-1]
        self.assertEqual(event['action'], 'revival_draw')
        context = event['context']
        self.assertEqual(context['pool'], losers)
        self.assertIsInstance(context['seed'], int)
        # the audit alone reproduces the draw: same seed, same sorted pool, same pick
        self.assertEqual(context['entrant'], random.Random(context['seed']).choice(context['pool']))
        entrant = next(e for e in t['entrants'] if e['id'] == context['entrant'])
        self.assertEqual(context['name'], entrant['members'][0]['name'])
        # the bye becomes a real round-1 match; its winner takes the round-2 place
        target = self.ops._find(t['matches'], context['match'])
        self.assertEqual(target['round'], 1)
        self.assertIn(context['entrant'], target['sides'])
        self.assertTrue(all(target['sides']))
        self.assertEqual(target['status'], 'scheduled')
        self.assertNotIn('result', target)
        downstream = self.ops._find(t['matches'], context['next'])
        self.assertIn(context['match'], downstream['sources'])
        self.assertEqual((downstream['round'], downstream['status']), (2, 'pending'))
        self.assertIn(None, downstream['sides'])
        self.assertEqual(t['revival']['entrant'], context['entrant'])
        # every signed result is byte-identical, and the revived loss still stands
        self.assertEqual({m['id']: json.dumps(m, sort_keys=True) for m in t['matches'] if m['id'] in signed_before}, signed_before)
        lost = next(m for m in t['matches'] if m.get('result') == 'played' and context['entrant'] in m['sides'])
        self.assertNotEqual(lost['winnerId'], context['entrant'])
        with self.assertRaisesRegex(ValueError, 'already drawn'):
            self.call('revival_draw', confirm=True)
        # undo restores the bracket exactly, until the next signed result
        state = self.call('revival_undo', confirm=True)
        self.assertEqual(state['tournament']['matches'], before_draw)
        self.assertNotIn('revival', state['tournament'])

    def test_a_late_entrant_joins_as_their_own_team(self):
        """R21 item 3: somebody arriving after the draw gets a round-1 bye slot of their own."""
        state = self.play_round_one(6)
        t = state['tournament']
        before = json.loads(json.dumps(t['matches']))
        state = self.call('entrant_add_late', name='Late Lou')
        t = state['tournament']
        added = [m for m in t['matches'] if m.get('late')]
        self.assertEqual(len(added), 1, 'exactly one late slot')
        self.assertEqual((added[0]['round'], added[0]['sources']), (1, []), 'a round-1 bye slot of its own')
        self.assertEqual(added[0]['sides'][1], None, 'with the other side still open')
        self.assertEqual(t['entrants'][-1]['members'][0]['name'], 'Late Lou', 'and the person is on the list')
        self.assertEqual(added[0]['sides'][0], t['entrants'][-1]['id'], 'the slot is theirs')
        rest = [m for m in t['matches'] if not m.get('late')]
        self.assertEqual(rest, before, 'the rest of the tree is byte-identical')
        # A second late sign-up is refused. The gate that answers first is the state of the tournament
        # after the draw (measured: the duplicate never reaches the name check), so the rule asserted
        # here is that it is refused, not which sentence refuses it.
        with self.assertRaises(ValueError):
            self.call('entrant_add_late', name='late lou')
        with self.assertRaises(ValueError):
            self.call('entrant_add_late', name='   ')

    def test_a_late_entrant_can_bring_a_partner(self):
        """R22 item 1: the arrival may be a team of two, and a partner already in the event is refused."""
        state = self.play_round_one(6)
        state = self.call('entrant_add_late', name='Late Lou', partner='Late Sue')
        entry = state['tournament']['entrants'][-1]
        self.assertEqual([m['name'] for m in entry['members']], ['Late Lou', 'Late Sue'],
                         'the two names are one team')
        self.assertEqual(len(entry['members']), 2, 'a team of two, not a second entrant')
        late = [m for m in state['tournament']['matches'] if m.get('late')]
        self.assertEqual(len(late), 1, 'and still one slot of their own')

    def test_revival_draw_can_be_told_who(self):
        """R21 item 3: the operator may name a round-1 loser, and anyone else is refused."""
        state = self.play_round_one(6)
        t = state['tournament']
        losers = sorted(next(side for side in m['sides'] if side != m['winnerId'])
                        for m in t['matches'] if m['round'] == 1 and m.get('result') == 'played')
        # A name the draw would never choose is refused, and the bracket is untouched.
        before = json.loads(json.dumps(t['matches']))
        with self.assertRaisesRegex(ValueError, 'not eligible for the second chance'):
            self.call('revival_draw', confirm=True, entrant='nobody')
        self.assertEqual(state['tournament']['matches'], before, 'a refused name changes nothing')
        self.assertNotIn('revival', state['tournament'])
        # A named loser is the one who returns, and the audit says so.
        chosen = losers[-1]
        state = self.call('revival_draw', confirm=True, entrant=chosen)
        t = state['tournament']
        self.assertEqual(t['revival']['entrant'], chosen, 'the named person is the one who returns')
        self.assertEqual(state['events'][-1]['context']['entrant'], chosen, 'and the audit records it')
        self.assertEqual(t['revival']['pool'], losers, 'the pool the draw would have used is unchanged')

    def test_revival_draw_refuses_with_a_reason(self):
        """R6: unfinished round 1, no played loser, no bye slot, or a signed round-2 result."""
        self.register(5)
        saved = self.ops.path.read_bytes()
        with self.assertRaisesRegex(ValueError, '^Finish round 1 first; every round-1 loser must be in the draw$'):
            self.call('revival_draw', confirm=True)
        self.assertEqual(self.ops.path.read_bytes(), saved)
        self.call('tournament_new', confirm=True)
        state = self.register(3)  # the only played round-1 match ends in a forfeit
        real = next(m for m in state['tournament']['matches'] if m['round'] == 1 and all(m['sides']))
        self.call('match_forfeit', id=real['id'], side=1)
        with self.assertRaisesRegex(ValueError, '^No round-1 loser to draw from$'):
            self.call('revival_draw', confirm=True)
        self.call('tournament_new', confirm=True)
        self.play_round_one(4)  # a power of two has no bye to fill
        with self.assertRaisesRegex(ValueError, '^No round-2 bye slot to fill$'):
            self.call('revival_draw', confirm=True)
        self.call('tournament_new', confirm=True)
        state = self.play_round_one(6)
        second = next(m for m in state['tournament']['matches'] if m['round'] == 2 and all(m['sides']))
        self.call('match_schedule', id=second['id'])
        self.call('match_score', id=second['id'], score=[7, 1])
        self.call('match_complete', id=second['id'])
        with self.assertRaisesRegex(ValueError, '^Round 2 has a signed result; the draw is closed$'):
            self.call('revival_draw', confirm=True)
        with self.assertRaisesRegex(ValueError, '^No revival draw to undo$'):
            self.call('revival_undo', confirm=True)

    def test_a_redraw_after_undo_is_counted_and_never_forgotten(self):
        """R6 follow-up: draw -> undo -> draw is attempt 2; undo never lowers the count,
        and every seed stays in the audit, so a re-roll for a wanted loser is visible."""
        self.play_round_one(6)
        first = self.call('revival_draw', confirm=True)
        self.assertEqual(first['tournament']['revival_draws'], 1)
        self.assertEqual(first['events'][-1]['context']['attempt'], 1)
        undone = self.call('revival_undo', confirm=True)
        self.assertEqual(undone['tournament']['revival_draws'], 1, 'undo never decrements the counter')
        self.assertEqual(undone['events'][-1]['context']['attempt'], 1)
        second = self.call('revival_draw', confirm=True)
        self.assertEqual(second['tournament']['revival_draws'], 2)
        self.assertEqual(second['tournament']['revival']['attempt'], 2)
        self.assertEqual(second['events'][-1]['context']['attempt'], 2)
        draws = [e['context'] for e in second['events'] if e['action'] == 'revival_draw']
        self.assertEqual([d['attempt'] for d in draws], [1, 2])
        self.assertEqual([d['seed'] for d in draws],
                         [first['tournament']['revival']['seed'], second['tournament']['revival']['seed']],
                         'both seeds are in the audit log')
        # a refused draw is not an attempt
        saved = self.ops.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already drawn'):
            self.call('revival_draw', confirm=True)
        self.assertEqual(self.ops.path.read_bytes(), saved)
        self.assertEqual(self.ops.get()['tournament']['revival_draws'], 2)
        # the counter belongs to the event: a new event starts at none
        self.assertNotIn('revival_draws', self.call('tournament_new', confirm=True)['tournament'])

    def test_random_doubles_pairing_is_seeded_shown_and_rerollable(self):
        """R3: solo sign-ups are paired by a seeded draw shown before it becomes the teams."""
        ada = self.call('player_save', name='Ada')['players'][0]['id']
        with self.assertRaisesRegex(ValueError, '^Random pairing is for doubles$'):
            self.call('solo_add', member={'name': 'Bo'})
        self.call('tournament_setup', format='doubles', raceTo=3)
        self.call('solo_add', member={'pid': ada})
        for name in ('Bo', 'Cy', 'Di'):
            self.call('solo_add', member={'name': name})
        # the pool follows the entrant rules: no duplicates, no placeholders, no alias of a regular
        saved = self.ops.path.read_bytes()
        for bad, reason in (({'name': ' bo '}, 'Person already registered'), ({'pid': ada}, 'Person already registered'),
                            ({'name': 'TBD'}, 'A bye is added by the draw'), ({'name': 'ADA'}, 'select the regular by id')):
            with self.assertRaisesRegex(ValueError, reason):
                self.call('solo_add', member=bad)
        self.assertEqual(self.ops.path.read_bytes(), saved)
        self.call('solo_add', member={'name': 'Eve'})
        with self.assertRaisesRegex(ValueError, '^An even number of solo players is needed to pair$'):
            self.call('pair_draw')
        state = self.call('solo_add', member={'name': 'Fay'})
        pool = state['tournament']['pool']
        self.assertEqual([m['name'] for m in pool], ['Ada', 'Bo', 'Cy', 'Di', 'Eve', 'Fay'])
        state = self.call('pair_draw')
        preview = state['tournament']['pairing']
        self.assertEqual(state['events'][-1]['action'], 'pair_draw')
        self.assertEqual(state['events'][-1]['context']['seed'], preview['seed'])
        self.assertEqual(len(preview['teams']), 3)
        # reproducible from the seed: shuffle the pool in sign-up order, pair neighbours
        order = list(range(len(pool)))
        random.Random(preview['seed']).shuffle(order)
        self.assertEqual(preview['teams'], [[pool[order[i]], pool[order[i + 1]]] for i in range(0, 6, 2)])
        self.assertEqual(state['tournament']['entrants'], [], 'a preview is not a registration')
        with self.assertRaisesRegex(ValueError, 'Registration is locked while a pairing is shown'):
            self.call('solo_add', member={'name': 'Gus'})
        # a re-roll draws a new seed and is audited too
        state = self.call('pair_draw')
        self.assertEqual(state['events'][-1]['action'], 'pair_draw')
        self.assertEqual(state['events'][-1]['context']['seed'], state['tournament']['pairing']['seed'])
        teams = state['tournament']['pairing']['teams']
        state = self.call('pair_accept', seed=state['tournament']['pairing']['seed'])
        t = state['tournament']
        self.assertEqual([e['members'] for e in t['entrants']], teams)
        self.assertEqual((t.get('pool'), t.get('pairing')), ([], None))
        self.assertEqual(state['events'][-1]['context']['seed'], state['events'][-2]['context']['seed'])
        # the draw of the bracket stays as it was: registration order seeds it
        state = self.call('tournament_start')
        self.assertEqual(state['tournament']['status'], 'active')

    def test_pairing_accept_must_match_the_shown_seed(self):
        """R3: an operator accepts exactly the pairing they saw; a stale screen is refused."""
        self.call('tournament_setup', format='doubles')
        for name in ('Ann', 'Bea'):
            self.call('solo_add', member={'name': name})
        with self.assertRaisesRegex(ValueError, '^No pairing to accept$'):
            self.call('pair_accept', seed=1)
        seed = self.call('pair_draw')['tournament']['pairing']['seed']
        saved = self.ops.path.read_bytes()
        with self.assertRaisesRegex(ValueError, '^The pairing changed; review the teams again$'):
            self.call('pair_accept', seed=seed + 1)
        self.assertEqual(self.ops.path.read_bytes(), saved)
        # clearing the preview returns to the pool; a solo can then be removed
        state = self.call('pair_clear')
        self.assertIsNone(state['tournament']['pairing'])
        solo = state['tournament']['pool'][0]
        state = self.call('pool_remove', name=solo['name'])
        self.assertEqual([m['name'] for m in state['tournament']['pool']], ['Bea'])
        with self.assertRaisesRegex(ValueError, 'Remove solo players before changing format'):
            self.call('tournament_setup', format='singles')

    def test_hide_from_history_is_a_flag_that_erases_nothing(self):
        """R1: hiding keeps every match and every stat; it can be undone; it is audited."""
        state = self.register(2)
        match = state['tournament']['matches'][0]
        self.call('match_forfeit', id=match['id'], side=0)
        archived = self.call('tournament_new', confirm=True)['history'][-1]
        with self.assertRaisesRegex(ValueError, '^Explicit confirmation required$'):
            self.call('tournament_hide', id=archived['id'], hidden=True)
        with self.assertRaisesRegex(ValueError, 'Only an archived event can be hidden'):
            self.call('tournament_hide', id=self.ops.get()['tournament']['id'], hidden=True, confirm=True)
        with self.assertRaisesRegex(ValueError, 'hidden must be boolean'):
            self.call('tournament_hide', id=archived['id'], hidden='yes', confirm=True)
        state = self.call('tournament_hide', id=archived['id'], hidden=True, confirm=True)
        hidden = state['history'][-1]
        self.assertIs(hidden['hidden'], True)
        self.assertEqual({k: v for k, v in hidden.items() if k != 'hidden'}, archived)
        self.assertEqual(state['events'][-1]['action'], 'tournament_hide')
        self.assertEqual(state['events'][-1]['context'], {'id': archived['id'], 'name': archived['name'], 'hidden': True})
        state = self.call('tournament_hide', id=archived['id'], hidden=False, confirm=True)
        self.assertIs(state['history'][-1]['hidden'], False)
        self.assertEqual(state['events'][-1]['context']['hidden'], False)

    def test_rename_changes_only_the_name_and_is_audited(self):
        """R2: a name-only rename after the draw and for archived events; rules stay locked."""
        self.call('tournament_setup', name='Old name', raceTo=5, tables=2)
        state = self.register(4, race_to=5)
        current = state['tournament']
        match = next(m for m in current['matches'] if m['status'] == 'scheduled')
        self.call('match_schedule', id=match['id'])
        self.call('match_score', id=match['id'], score=[5, 1])
        state = self.call('match_complete', id=match['id'])
        before = {k: v for k, v in state['tournament'].items() if k != 'name'}
        with self.assertRaisesRegex(ValueError, '^Tournament already started$'):
            self.call('tournament_setup', name='Blocked')
        state = self.call('tournament_rename', id=current['id'], name='  New name ', raceTo=1, format='doubles', tables=9)
        self.assertEqual(state['tournament']['name'], 'New name')
        self.assertEqual({k: v for k, v in state['tournament'].items() if k != 'name'}, before)
        self.assertEqual(state['events'][-1]['action'], 'tournament_rename')
        self.assertEqual(state['events'][-1]['context'], {'id': current['id'], 'name': 'New name'})
        # archived events, including a legacy one stored with an empty name
        state = self.call('tournament_new', confirm=True)
        legacy = json.loads(self.ops.path.read_text())
        legacy['history'].insert(0, dict(id='legacy', name='', format='singles', tables=1, raceTo=1,
                                         entrants=[], matches=[], status='complete', archivedAt='2026-01-01'))
        self.ops.path.write_text(json.dumps(legacy))
        archived = json.loads(json.dumps(self.ops.get()['history']))
        state = self.call('tournament_rename', id='legacy', name='January night')
        self.assertEqual(state['history'][0]['name'], 'January night')
        self.assertEqual(state['history'][1:], archived[1:])
        self.assertEqual({k: v for k, v in state['history'][0].items() if k != 'name'},
                         {k: v for k, v in archived[0].items() if k != 'name'})
        self.assertEqual(state['events'][-1]['context'], {'id': 'legacy', 'name': 'January night'})
        saved = self.ops.path.read_bytes()
        for bad in (dict(id='missing', name='x'), dict(id='legacy', name='   '), dict(id='legacy')):
            with self.assertRaises(ValueError):
                self.call('tournament_rename', **bad)
        self.assertEqual(self.ops.path.read_bytes(), saved)


class EventBackfillTests(unittest.TestCase):
    """docs/console-redesign.md 7.4: one past night, typed and confirmed by a person.

    The server reads no video and computes no result: it refuses anything a person did not
    confirm, refuses a broadcast this console does not know, and writes nothing at all on
    every refusal (7.0/7.5).
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ops = Operations(self.root)

    def call(self, action, **fields):
        return self.ops.post(dict(action=action, revision=self.ops.get()['revision'], **fields))

    def payload(self, event=None, source=None):
        body = dict(
            event=dict(name='8-Ball Open · 周一 9/1', format='singles', raceTo=7, tables=4,
                       entrants=[dict(name='Wanwan'), dict(name='Su')],
                       matches=[dict(round=1, sides=['Wanwan', 'Su'], score=[3, 1],
                                     winner='Wanwan', result='played', clip=[452, 1690])]),
            source=dict(kind='vod-backfill', vodId='1234567890', datasetId='tw-1234567890-452-1690',
                        startS=452, endS=1690, channel='examplechannel', title='Monday night',
                        humanReviewed=True))
        body['event'].update(event or {})
        body['source'].update(source or {})
        return body

    def backfill(self, **changes):
        return self.call('event_backfill', **self.payload(**changes))

    def saved(self):
        return self.ops.path.read_bytes() if self.ops.path.exists() else None

    def refuse(self, message, **changes):
        """A refused backfill leaves the store byte-for-byte as it was (and no file at all)."""
        before = self.saved()
        with self.assertRaisesRegex(ValueError, message):
            self.backfill(**changes)
        self.assertEqual(self.saved(), before)

    def refuse_payload(self, message, **fields):
        """The same, for a request whose event/source is not even an object."""
        before = self.saved()
        with self.assertRaisesRegex(ValueError, message):
            self.call('event_backfill', **fields)
        self.assertEqual(self.saved(), before)

    def imported(self, entries):
        """The registry the single-flight import job writes under out/vods/index.json."""
        path = self.root / 'out' / 'vods' / 'index.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(vods=entries)))

    def test_backfill_writes_one_signed_night_and_leaves_tonight_alone(self):
        # an event is being played right now: the backfilled night must not disturb it
        self.call('tournament_setup', raceTo=5)
        self.call('entrant_add', members=[{'name': 'Ada'}])
        self.call('entrant_add', members=[{'name': 'Bo'}])
        tonight = json.loads(json.dumps(self.call('tournament_start')['tournament']))
        before = self.ops.get()

        state = self.backfill()
        self.assertEqual(state['revision'], before['revision'] + 1)
        self.assertEqual(state['tournament'], tonight)
        self.assertEqual(len(state['history']), 1)
        night = state['history'][0]
        self.assertEqual(night['name'], '8-Ball Open · 周一 9/1')
        self.assertEqual((night['format'], night['tables'], night['raceTo'], night['status']),
                         ('singles', 4, 7, 'complete'))
        # the shape the console already renders a night with
        self.assertEqual(night['entrants'],
                         [dict(id=night['entrants'][0]['id'], members=[dict(pid=None, name='Wanwan')]),
                          dict(id=night['entrants'][1]['id'], members=[dict(pid=None, name='Su')])])
        match = night['matches'][0]
        self.assertEqual(match['sides'], [night['entrants'][0]['id'], night['entrants'][1]['id']])
        self.assertEqual((match['round'], match['score'], match['result'], match['clip']),
                         (1, [3, 1], 'played', [452, 1690]))
        self.assertEqual((match['status'], match['winnerId']), ('complete', night['entrants'][0]['id']))
        # nobody knows when a past match ended: no timestamp is invented for it
        self.assertNotIn('completedAt', match)
        self.assertEqual(night['source'], dict(kind='vod-backfill', vodId='1234567890',
                                               datasetId='tw-1234567890-452-1690', startS=452, endS=1690,
                                               channel='examplechannel', title='Monday night',
                                               humanReviewed=True))
        self.assertEqual(night['signOff']['at'], night['archivedAt'])
        # the audit line is the only record that a person wrote these results
        self.assertEqual(state['events'][-1]['action'], 'event_backfill')
        self.assertEqual(state['events'][-1]['context'],
                         dict(id=night['id'], name=night['name'], vodId='1234567890',
                              datasetId='tw-1234567890-452-1690'))
        self.assertNotIn('Wanwan', json.dumps(state['events']))
        self.assertEqual(Operations(self.root).get(), state)
        self.assertEqual(json.loads(self.ops.path.read_text()), state)
        # the night is a first-class timeline entry: hideable, but never deletable
        with self.assertRaisesRegex(ValueError, 'cannot be deleted'):
            self.call('tournament_delete', id=night['id'], confirm=True)
        hidden = self.call('tournament_hide', id=night['id'], confirm=True, hidden=True)
        self.assertEqual((hidden['history'][0]['hidden'], hidden['tournament']), (True, tonight))
        self.assertEqual(hidden['events'][-1]['context'], dict(id=night['id'], name=night['name'], hidden=True))

    def test_backfill_accepts_an_imported_range_and_keeps_its_channel_honest(self):
        self.imported({'tw-1234567890-452-1690': dict(vod_id='1234567890', channel='examplechannel',
                                                      title='Resolved title'),
                       'tw-1234567890': dict(vod_id='1234567890', channel='examplechannel',
                                             title='Full broadcast'),
                       'tw-1234567890-2501-3000': dict(vod_id='1234567890', channel='otherchannel',
                                                       title='Third night'),
                       'tw-1234567890-4000-5000': dict(vod_id='1234567890', channel='otherchannel',
                                                       title='Fourth night')})
        state = self.backfill()
        self.assertEqual(state['history'][0]['source']['channel'], 'examplechannel')
        # with the channel source gone, an imported range is proof enough on its own
        self.call('source_delete', id=self.ops.get()['sources'][0]['id'])
        self.assertEqual(self.ops.get()['sources'], [])
        state = self.backfill(source=dict(datasetId='tw-1234567890-2501-3000', startS=2501, endS=3000,
                                          channel='otherchannel', title=''))
        # a title the operator did not type is filled in from the broadcast's own metadata
        self.assertEqual(state['history'][1]['source']['title'], 'Third night')
        # the whole-broadcast spelling of a range inside that broadcast is accepted too
        state = self.backfill(source=dict(datasetId='tw-1234567890', startS=1691, endS=2000,
                                          channel='examplechannel', title=''))
        self.assertEqual(state['history'][2]['source']['title'], 'Full broadcast')
        # a claim that contradicts what the import resolved is refused, not stored beside it
        self.refuse('channel does not match the channel this range was imported from',
                    source=dict(datasetId='tw-1234567890-4000-5000', startS=4000, endS=5000,
                                channel='examplechannel'))
        self.refuse('for this broadcast and range', source=dict(datasetId='tw-1234567890-1-2'))
        self.refuse('datasetId must be an imported dataset id', source=dict(datasetId='vod30'))
        self.refuse('datasetId must be an imported dataset id', source=dict(datasetId=None))
        self.assertEqual(len(self.ops.get()['history']), 3)

    def test_backfill_accepts_a_saved_video_source_without_a_channel_claim(self):
        self.call('source_add', url='https://www.twitch.tv/videos/1234567890')
        state = self.backfill(source=dict(channel=''))
        self.assertEqual(state['history'][0]['source']['channel'], None)

    def test_backfill_needs_a_person_and_a_known_broadcast(self):
        # 7.4/7.6: the confirmation mark is enforced by the server, the disabled button is not enough
        self.refuse('humanReviewed must be true', source=dict(humanReviewed=False))
        self.refuse('humanReviewed must be true', source=dict(humanReviewed='true'))
        self.refuse('humanReviewed must be true', source=dict(humanReviewed=None))
        self.refuse_payload('source object required', event=self.payload()['event'], source=None)
        self.refuse_payload('event object required', event=None, source=self.payload()['source'])
        self.refuse("source.kind must be 'vod-backfill'", source=dict(kind='clip'))
        # a broadcast this console does not know: no saved source, no imported range
        self.refuse('is not a saved source and was not imported', source=dict(channel='someoneelse'))
        self.refuse('is not a saved source and was not imported',
                    source=dict(channel='', vodId='7654321', datasetId='tw-7654321-452-1690'))
        # the id is parsed by annotator/twitch_vod_source.py, and it is the only spelling allowed
        for bad in ('not-a-vod', '', None, -1, 'https://www.twitch.tv/examplechannel'):
            self.refuse('Twitch VOD id', source=dict(vodId=bad))
        self.refuse('startS must be a whole number of seconds, 0 or more', source=dict(startS=-1))
        self.refuse('startS must be a whole number of seconds, 0 or more', source=dict(startS=True))
        self.refuse('endS must be after startS', source=dict(startS=1690, endS=452))
        self.refuse('endS must be after startS', source=dict(startS=1690, endS=1690))
        self.assertEqual(self.ops.get()['history'], [])
        self.assertEqual(self.ops.get()['revision'], 0)
        self.assertFalse(self.ops.path.exists())

    def test_backfill_refuses_every_unconfirmed_result_without_writing(self):
        def one(score, sides=('Wanwan', 'Su'), winner='Wanwan', clip=(452, 1690), **extra):
            return dict(sides=list(sides), score=score, winner=winner, clip=list(clip), **extra)
        self.refuse('matches must be a non-empty list', event=dict(matches=[]))
        self.refuse('matches must be a non-empty list', event=dict(matches=None))
        self.refuse('Two sides required', event=dict(matches=[one([3, 1], sides=['Wanwan'])]))
        self.refuse('A match needs two different entrants',
                    event=dict(matches=[one([3, 1], sides=['Wanwan', 'Wanwan'])]))
        self.refuse('Every side and winner must name one of the entrants',
                    event=dict(matches=[one([3, 1], sides=['Wanwan', 'Nobody'])]))
        self.refuse('winner must be one of the two sides',
                    event=dict(entrants=[dict(name='Wanwan'), dict(name='Su'), dict(name='Kai')],
                               matches=[one([3, 1], winner='Kai')]))
        self.refuse('score must be an integer from 0 to 99', event=dict(matches=[one([-1, 1])]))
        self.refuse('score must be an integer from 0 to 99', event=dict(matches=[one([3, 1.5])]))
        self.refuse('Two scores required', event=dict(matches=[one([3])]))
        self.refuse('Two scores required', event=dict(matches=[one('3-1')]))
        self.refuse('clip must be \\[start, end\\] in whole seconds',
                    event=dict(matches=[one([3, 1], clip=[452])]))
        self.refuse('clip start must be a whole number of seconds, 0 or more',
                    event=dict(matches=[one([3, 1], clip=[-452, 1690])]))
        self.refuse('clip end must be after clip start',
                    event=dict(matches=[one([3, 1], clip=[1690, 1690])]))
        self.refuse('round must be an integer from 1 to 99', event=dict(matches=[one([3, 1], round=0)]))
        self.refuse("result must be 'played' or 'forfeit'", event=dict(matches=[one([3, 1], result='bye')]))
        self.refuse('entrants must be a non-empty list', event=dict(entrants=[]))
        self.refuse('Two entrants share a name', event=dict(entrants=[dict(name='Su'), dict(name='su')]))
        self.refuse('Two entrants share an id',
                    event=dict(entrants=[dict(id='e1', name='Su'), dict(id='e1', name='Kai')]))
        self.refuse("type the guest's real name", event=dict(entrants=[dict(name='Su'), dict(name='bye')]))
        self.refuse('name must contain', event=dict(name='   '))
        self.refuse('Invalid format', event=dict(format='triples'))
        self.refuse('tables must be an integer from 1 to 32', event=dict(tables=0))
        self.refuse('raceTo must be an integer from 1 to 99', event=dict(raceTo='7'))
        self.assertEqual(self.ops.get()['history'], [])
        self.assertEqual(self.ops.get()['revision'], 0)
        self.assertFalse(self.ops.path.exists())

    def test_backfill_links_a_written_name_to_the_regular_it_names(self):
        """6.1 / the additive `pid` row of 7.6: a night typed from a VOD counts towards a house standing."""
        for name, rating, status in (('Wanwan', 900, 'Active'), ('Su', 900, 'Active'), ('Retired', 800, 'Inactive')):
            self.call('player_save', name=name, rating=rating, status=status)
        roster = {item['name']: item['id'] for item in self.ops.get()['players']}
        state = self.backfill(event=dict(entrants=[dict(pid=roster['Wanwan']), dict(pid=roster['Su'])],
                                         matches=[dict(round=1, sides=['Wanwan', 'Su'], score=[3, 1],
                                                       winner='Wanwan', result='played', clip=[452, 1690])]))
        night = state['history'][0]
        # the entrant carries the regular it was typed from: this is what makes the standing count
        self.assertEqual([entrant['members'] for entrant in night['entrants']],
                         [[dict(pid=roster['Wanwan'], name='Wanwan')], [dict(pid=roster['Su'], name='Su')]])
        self.assertEqual([match['sides'] for match in night['matches']],
                         [[night['entrants'][0]['id'], night['entrants'][1]['id']]])
        self.assertEqual(night['matches'][0]['winnerId'], night['entrants'][0]['id'])
        # the name is the roster's, never the one the request spelled: a night and a standing cannot disagree
        state = self.backfill(event=dict(name='8-Ball Open · 周二 9/2',
                                         entrants=[dict(pid=roster['Wanwan']), dict(pid=roster['Su'])],
                                         matches=[dict(round=1, sides=['Wanwan', 'Su'], score=[1, 3],
                                                       winner='Su', result='played', clip=[1691, 2000])]),
                              source=dict(datasetId='tw-1234567890-1691-2000', startS=1691, endS=2000))
        self.assertEqual([entrant['members'][0]['pid'] for entrant in state['history'][1]['entrants']],
                         [roster['Wanwan'], roster['Su']])
        # a rename does not rewrite the night: the id link stays, and the screens read the live name (R12)
        self.call('player_save', id=roster['Wanwan'], name='Wan Wan')
        self.assertEqual(self.ops.get()['history'][0]['entrants'][0]['members'],
                         [dict(pid=roster['Wanwan'], name='Wanwan')])
        self.assertEqual(next(item['name'] for item in self.ops.get()['players']
                              if item['id'] == roster['Wanwan']), 'Wan Wan')
        # a name the roster does not hold is still a guest, and counts towards nobody
        state = self.backfill(event=dict(name='8-Ball Open · 周三 9/3',
                                         entrants=[dict(pid=roster['Su']), dict(name='Rico')],
                                         matches=[dict(round=1, sides=['Su', 'Rico'], score=[3, 2],
                                                       winner='Su', result='played', clip=[2001, 2400])]),
                              source=dict(datasetId='tw-1234567890-2001-2400', startS=2001, endS=2400))
        self.assertEqual([entrant['members'] for entrant in state['history'][2]['entrants']],
                         [[dict(pid=roster['Su'], name='Su')], [dict(pid=None, name='Rico')]])

    def test_backfill_refuses_a_regular_pointer_it_cannot_honour(self):
        """An unlinked night would silently count towards nobody, so every bad pointer is refused."""
        self.call('player_save', name='Wanwan', rating=900, status='Active')
        self.call('player_save', name='Retired', rating=800, status='Inactive')
        roster = {item['name']: item['id'] for item in self.ops.get()['players']}
        self.refuse('Unknown id', event=dict(entrants=[dict(pid='nope'), dict(name='Kai')]))
        self.refuse('Inactive player', event=dict(entrants=[dict(pid=roster['Retired']), dict(name='Kai')]))
        self.refuse('Two entrants name the same regular',
                    event=dict(entrants=[dict(pid=roster['Wanwan']), dict(pid=roster['Wanwan'])]))
        # a name the roster holds is refused as a name (the fix is to send the pid), on either side
        self.refuse('Player name already exists; send the regular as their player id',
                    event=dict(entrants=[dict(name='Wanwan'), dict(pid=roster['Wanwan'])]))
        self.refuse('Player name already exists; send the regular as their player id',
                    event=dict(entrants=[dict(pid=roster['Wanwan']), dict(name='Wanwan')]))
        self.refuse('Player name already exists; send the regular as their player id',
                    event=dict(entrants=[dict(name='wanwan'), dict(name='Kai')]))
        # the entrants that were never written: the night still holds exactly what a person confirmed
        before = self.ops.get()['revision']
        state = self.backfill(event=dict(entrants=[dict(pid=roster['Wanwan']), dict(name='Kai')],
                                         matches=[dict(round=1, sides=['Wanwan', 'Kai'], score=[3, 0],
                                                       winner='Wanwan', result='played', clip=[452, 1690])]))
        self.assertEqual(state['history'][0]['entrants'][1]['members'], [dict(pid=None, name='Kai')])
        self.assertEqual(state['revision'], before + 1)

    def test_backfill_of_one_range_twice_is_a_conflict_that_names_the_night(self):
        first = self.backfill()
        night = first['history'][0]
        saved = self.saved()
        with self.assertRaises(ConflictError) as caught:
            self.backfill()
        self.assertIn(night['id'], str(caught.exception))
        self.assertIn(night['name'], str(caught.exception))
        self.assertIn('tw-1234567890-452-1690', str(caught.exception))
        # a conflict is not a write: no second night, no revision, not a byte
        self.assertEqual(self.saved(), saved)
        self.assertEqual(self.ops.get()['history'], [night])
        self.assertEqual(self.ops.get()['revision'], first['revision'])
        # the whole-broadcast spelling of the very same range is the same night, too
        with self.assertRaises(ConflictError) as caught:
            self.backfill(source=dict(datasetId='tw-1234567890'))
        self.assertIn(night['id'], str(caught.exception))
        # a different range of the same broadcast is a different night
        state = self.backfill(event=dict(name='8-Ball Open · 周二 9/2'),
                              source=dict(vodId=1234567890, datasetId='tw-1234567890-1691-2000',
                                          startS=1691, endS=2000))
        self.assertEqual([item['name'] for item in state['history']],
                         ['8-Ball Open · 周一 9/1', '8-Ball Open · 周二 9/2'])

    def test_two_consoles_backfilling_at_once_write_one_night(self):
        """One job at a time, no queue (12.5): the loser is refused, it does not wait."""
        written, refused = [], []

        def run():
            try:
                written.append(self.backfill())
            except ConflictError as error:
                refused.append(error)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(written), 1)
        self.assertEqual(len(refused), 1)
        state = self.ops.get()
        self.assertEqual((state['revision'], len(state['history'])), (1, 1))
        self.assertEqual(state['events'][-1]['action'], 'event_backfill')
        self.assertEqual(Operations(self.root).get(), state)


class VodLinkTests(unittest.TestCase):
    """docs/console-redesign.md 23: a broadcast covers events, an event is covered by
    broadcasts.

    The relation is one row per pair - never a list on either side - because it is
    many-to-many in both directions; a link outlives the broadcast's own metadata
    because Twitch forgets broadcasts; and the import's audit line stays exactly what
    the import wrote, because that line is the record of a write.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ops = Operations(self.root)

    def call(self, action, **fields):
        return self.ops.post(dict(action=action, revision=self.ops.get()['revision'], **fields))

    def imported(self, entries):
        """The registry the single-flight import job writes under out/vods/index.json."""
        path = self.root / 'out' / 'vods' / 'index.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(vods=entries)))

    def backfill(self, name='8-Ball Open · 周一 9/1'):
        """One signed night in the timeline, through 7.4's own path."""
        self.imported(['tw-1234567890-452-1690'])
        return self.call('event_backfill',
                         event=dict(name=name, format='singles', raceTo=7, tables=4,
                                    entrants=[dict(name='Wanwan'), dict(name='Su')],
                                    matches=[dict(round=1, sides=['Wanwan', 'Su'], score=[3, 1],
                                                  winner='Wanwan', result='played', clip=[452, 1690])]),
                         source=dict(kind='vod-backfill', vodId='1234567890',
                                     datasetId='tw-1234567890-452-1690', startS=452, endS=1690,
                                     channel='examplechannel', title='Monday night', humanReviewed=True))

    def link(self, vod, event, **fields):
        return self.call('vod_link', vodId=vod, eventId=event, **fields)

    def test_a_backfilled_night_is_a_link_to_its_broadcast(self):
        state = self.backfill()
        night = state['history'][0]
        self.assertEqual(state['links'], [dict(vodId='1234567890', eventId=night['id'],
                                               startS=452, endS=1690, at=night['signOff']['at'])])
        self.assertEqual(state['vods'], [dict(id='1234567890', title='Monday night', channel='',
                                              length_s=0, created_at='')])
        # the import's line is the audit of a write, and a read never rewrites it
        self.assertEqual(night['source']['datasetId'], 'tw-1234567890-452-1690')
        self.assertEqual(night['source']['humanReviewed'], True)
        # read it again: adopting a line is idempotent and needs no clock
        self.assertEqual(Operations(self.root).get(), state)

    def test_a_broadcast_covers_many_events_and_an_event_many_broadcasts(self):
        state = self.backfill()
        night, tonight = state['history'][0]['id'], state['tournament']['id']
        state = self.link('1234567890', tonight, title='Monday night', channel='ExampleChannel',
                          length_s=16455, created_at='2026-10-02T23:07:00Z')
        state = self.link('9999999999', tonight, title='Camera B')
        state = self.link('9999999999', night)
        self.assertEqual({(row['vodId'], row['eventId']) for row in state['links']},
                         {('1234567890', night), ('1234567890', tonight),
                          ('9999999999', night), ('9999999999', tonight)})
        self.assertEqual([row['id'] for row in state['vods']], ['1234567890', '9999999999'])
        # a channel is stored the way a source is stored, and the import's range is kept
        self.assertEqual(next(v for v in state['vods'] if v['id'] == '1234567890')['channel'], 'examplechannel')
        self.assertEqual(next(l for l in state['links']
                              if l['vodId'] == '1234567890' and l['eventId'] == tonight)['startS'], None)
        # the same pair twice is one row, and a range may be filled in later
        state = self.link('9999999999', night, startS=10, endS=20)
        self.assertEqual(len(state['links']), 4)
        self.assertEqual(next(l for l in state['links']
                              if l['vodId'] == '9999999999' and l['eventId'] == night)['endS'], 20)
        # the audit names the pair a person made
        self.assertEqual(state['events'][-1]['context'], dict(vodId='9999999999', id=night,
                                                             name='8-Ball Open · 周一 9/1'))
        self.assertEqual(Operations(self.root).get(), state)

    def test_metadata_is_refreshed_field_by_field(self):
        state = self.call('tournament_setup', raceTo=7)
        tonight = state['tournament']['id']
        state = self.link('1234567890', tonight, title='Monday night', channel='ttpoolfriday',
                          length_s=16455, created_at='2026-10-02T23:07:00Z')
        self.assertEqual(state['vods'][0], dict(id='1234567890', title='Monday night',
                                                channel='ttpoolfriday', length_s=16455,
                                                created_at='2026-10-02T23:07:00Z'))
        state = self.link('1234567890', tonight, length_s=16000)
        self.assertEqual(state['vods'][0]['title'], 'Monday night')
        self.assertEqual((state['vods'][0]['length_s'], state['vods'][0]['created_at']),
                         (16000, '2026-10-02T23:07:00Z'))

    def test_a_refused_link_writes_nothing(self):
        state = self.backfill()
        night = state['history'][0]['id']
        saved = self.ops.path.read_bytes()
        for fields, message in (
                (dict(vodId='1234567890', eventId='nope'), 'Unknown event'),
                (dict(vodId='1234567890', eventId=night, startS=10), 'A range needs both'),
                (dict(vodId='1234567890', eventId=night, startS=20, endS=20), 'endS must be after startS'),
                (dict(vodId='not-a-vod', eventId=night), 'Expected a Twitch VOD id'),
                (dict(vodId='1234567890', eventId=night, created_at='yesterday'), 'ISO-8601'),
                (dict(vodId='1234567890', eventId=night, channel='Not A Channel'), 'Twitch channel login')):
            with self.assertRaisesRegex(ValueError, message):
                self.call('vod_link', **fields)
            self.assertEqual(self.ops.path.read_bytes(), saved)
        with self.assertRaisesRegex(ValueError, 'Unknown link'):
            self.call('vod_unlink', vodId='9999999999', eventId=night)
        self.assertEqual(self.ops.path.read_bytes(), saved)
        # the import's own line is evidence, not a choice: it would come straight back
        with self.assertRaisesRegex(ValueError, 'own import record'):
            self.call('vod_unlink', vodId='1234567890', eventId=night)
        self.assertEqual(self.ops.path.read_bytes(), saved)

    def test_unlinking_leaves_the_broadcast_known(self):
        """A link a person made is theirs to drop; the broadcast stays known (23.2)."""
        state = self.backfill()
        night = state['history'][0]['id']
        state = self.link('9999999999', night, title='Camera B')
        self.assertEqual(len(state['links']), 2)
        state = self.call('vod_unlink', vodId='9999999999', eventId=night)
        self.assertEqual([row['vodId'] for row in state['links']], ['1234567890'])
        self.assertEqual([row['id'] for row in state['vods']], ['1234567890', '9999999999'])
        self.assertEqual(Operations(self.root).get(), state)

    def test_an_event_that_stops_existing_takes_its_links_away(self):
        """The relation has no dangling end: a replaced live event leaves no link behind."""
        state = self.call('tournament_setup', raceTo=7)
        tonight = state['tournament']['id']
        state = self.link('1234567890', tonight, title='Monday night')
        self.assertEqual(len(state['links']), 1)
        state = self.call('tournament_delete', id=tonight, confirm=True)
        self.assertNotEqual(state['tournament']['id'], tonight)
        self.assertEqual(state['links'], [])
        self.assertEqual([row['id'] for row in state['vods']], ['1234567890'])

    def test_an_archived_event_keeps_its_links(self):
        """An event that is archived keeps its id, so tonight's links become its history."""
        state = self.call('tournament_setup', raceTo=7)
        tonight = state['tournament']['id']
        state = self.call('entrant_add', members=[dict(name='Wanwan')])   # singles: one member each
        state = self.link('1234567890', tonight, title='Monday night')
        state = self.call('tournament_new', confirm=True)
        self.assertEqual(state['history'][0]['id'], tonight)
        self.assertEqual([row['eventId'] for row in state['links']], [tonight])


if __name__ == '__main__':
    unittest.main()
