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
                        {'revision': 1, 'action': 'settings_update', 'shotClock': True}):
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
                         {'showDiamonds': 1}, {'clothColor': 'red'}):
            with self.assertRaises(ValueError):
                self.call('settings_update', **settings)

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
        self.assertEqual(state['events'][-1]['action'], 'revival_undo')
        self.assertEqual(state['events'][-1]['context']['seed'], context['seed'])
        state = self.call('revival_draw', confirm=True)
        match = self.ops._find(state['tournament']['matches'], state['events'][-1]['context']['match'])
        self.call('match_schedule', id=match['id'])
        self.call('match_score', id=match['id'], score=[7, 0])
        self.call('match_complete', id=match['id'])
        saved = self.ops.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'a result has been signed since the draw'):
            self.call('revival_undo', confirm=True)
        self.assertEqual(self.ops.path.read_bytes(), saved)

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


if __name__ == '__main__':
    unittest.main()
