"""Pins that the detection harness cannot score a detector against its own seed.

vod30's "median 4.38 px, accept 100 %" headline came from a harness whose detector
mode was seeded with ``prior_for(dataset)`` - i.e. with ``out/corners_30min_v2.json``,
the very file it was then scored against.  A detector scored against its own seed
reports how far it moved, not how good it is (docs/app-path-refusal.md).  These
tests keep that combination impossible: the seed comes from the hand anchors, both
references are always reported, and the circular one is labelled as such.
"""
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src import eval_table_detect as ev
from src.frame_inference import app_prior_for, app_prior_source

SOURCE = Path(ev.__file__).read_text()


class ReferenceTests(unittest.TestCase):
    def test_both_vod30_references_are_reported_with_their_quality(self):
        refs = ev.load_references()['vod30']
        names = [ref['name'] for ref in refs]
        self.assertIn('app-anchors@70.0s', names)
        self.assertIn('corners30-v2', names)
        by_name = {ref['name']: ref for ref in refs}
        self.assertEqual(by_name['app-anchors@70.0s']['quality'], 'authoritative')
        self.assertEqual(by_name['app-anchors@70.0s']['source_file'], str(ev.ANCHORS))
        self.assertEqual(by_name['corners30-v2']['quality'], 'circular')
        self.assertEqual(by_name['corners30-v2']['source_file'], str(ev.CORNERS_V2))
        self.assertIn('CIRCULAR', by_name['corners30-v2']['note'])
        self.assertEqual(ev.authoritative_reference(refs), 'app-anchors@70.0s')

    def test_the_highlight_reference_is_authoritative(self):
        refs = ev.load_references()['highlight']
        self.assertEqual([ref['name'] for ref in refs], ['fixed-corners'])
        self.assertEqual(ev.authoritative_reference(refs), 'fixed-corners')


class SeedGuardTests(unittest.TestCase):
    def setUp(self):
        self.refs = ev.load_references()['vod30']

    def test_a_seed_from_a_scored_reference_fails_loudly(self):
        with self.assertRaises(AssertionError) as ctx:
            ev.assert_seed_is_measurable('vod30', str(ev.CORNERS_V2), self.refs)
        self.assertIn('not an authoritative reference', str(ctx.exception))
        # the authoritative seed and "no seed at all" both stay legal
        ev.assert_seed_is_measurable('vod30', str(ev.ANCHORS), self.refs)
        ev.assert_seed_is_measurable('vod30', None, self.refs)

    def test_every_detector_mode_refuses_the_circular_seed(self):
        frame = np.zeros((360, 640, 3), np.uint8)
        for name in ('refined', 'app'):
            with self.subTest(detector=name), \
                    patch('src.frame_inference.app_prior_source', return_value=ev.CORNERS_V2), \
                    patch('src.frame_inference.app_prior_for',
                          return_value=np.asarray(ev.load_references()['vod30'][1]['corners'])):
                with self.assertRaises(AssertionError):
                    ev.DETECTORS[name](frame, 'vod30', 0, self.refs)

    def test_no_detector_mode_seeds_from_prior_for(self):
        bare = re.findall(r'(?<!app_)prior_for[(]', SOURCE)
        self.assertEqual(bare, [], 'a detector seeded from prior_for(dataset) is scored against '
                                   'its own seed')
        self.assertNotIn('import prior_for', SOURCE)
        self.assertIn('app_prior_source', SOURCE)
        self.assertEqual(sorted(ev.DETECTORS), ['app', 'naive', 'refined'])

    def test_the_naive_mode_has_no_seed_and_the_refined_mode_uses_the_anchors(self):
        refs = ev.load_references()['vod30']
        _, info = ev.DETECTORS['naive'](np.zeros((48, 64, 3), np.uint8), 'vod30', 0, refs)
        self.assertIsNone(info['seed_file'])
        self.assertIsNone(app_prior_for('nope-not-a-dataset'))
        self.assertEqual(str(app_prior_source('vod30')), str(ev.ANCHORS))
        # highlight has no hand anchors, so the refined mode has no seed there either
        self.assertIsNone(app_prior_source('highlight'))


class OutputTests(unittest.TestCase):
    def summary(self):
        refs = ev.load_references()['vod30']
        rows = [{'t': 61.0, 'read': True, 'width': 1280, 'height': 720, 'source': 'refined_saved_prior',
                 'ms': 40.0, 'seed_file': str(ev.ANCHORS), 'references': {
                     refs[0]['name']: {'state': 'ok', 'mean': 6.4},
                     refs[1]['name']: {'state': 'off', 'mean': 43.0}}}]
        return ev.summarise(rows, refs, 'refined', 'vod30', 1.0)

    def test_the_text_output_names_the_authoritative_reference_and_headlines_it(self):
        text = ev._table(self.summary())
        self.assertIn('vs app-anchors@70.0s [authoritative]', text)
        self.assertIn('[circular', text)
        self.assertLess(text.index('[authoritative]'), text.index('[circular'),
                        'the honest number is printed first')
        self.assertIn('HEADLINE vs app-anchors@70.0s: median 6.4 px', text)
        self.assertIn(f'seed={ev.ANCHORS}', text)

    def test_the_json_summary_keeps_both_references_and_names_the_authoritative_one(self):
        summary = self.summary()
        self.assertEqual(summary['authoritative_reference'], 'app-anchors@70.0s')
        self.assertEqual(summary['seeded_from'], str(ev.ANCHORS))
        self.assertEqual(summary['references']['corners30-v2']['quality'], 'circular')
        self.assertEqual(summary['references']['corners30-v2']['error_px']['median'], 43.0)
        self.assertEqual(summary['references']['app-anchors@70.0s']['error_px']['median'], 6.4)


if __name__ == '__main__':
    unittest.main()
