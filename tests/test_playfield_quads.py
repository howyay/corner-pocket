"""The recorded playfield quads still get the verdicts they were measured with.

``tools/playfield_vod_audit.py`` runs the table detector over the historical VODs and records
every sampled quad together with the verdict the check gave it.  This test replays those quads
through the check.  Move a tolerance, or change what counts as a table, and the recorded
verdicts stop matching - without paying for the detector a second time.  It also holds the
floor: at least five of the nineteen events must pass at every sampled frame.

    .venv/bin/python -m unittest tests.test_playfield_quads
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.playfield import check_quad

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'tests/fixtures/playfield_quads.json'
FLOOR = 5


def best_verdict(quad):
    """The stage tries two rotations of the polygon and keeps the better verdict."""
    rotated = quad[1:] + quad[:1]
    return min((check_quad(quad), check_quad(rotated)),
               key=lambda v: (not v['ok'], len(v['reasons'])))


class PlayfieldQuadReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RUN.exists():
            raise unittest.SkipTest('no recorded run: .venv/bin/python tools/playfield_vod_audit.py')
        cls.data = json.loads(RUN.read_text())
        cls.picks = [(p['vod'], p) for p in cls.data['picks']]

    def test_the_recorded_quads_replay_to_the_verdicts_they_were_measured_with(self):
        replayed = 0
        for vod, pick in self.picks:
            quad = pick.get('quad') or []
            if len(quad) != 4:
                continue
            got = best_verdict(quad)
            replayed += 1
            where = '%s@%s' % (vod, pick.get('at'))
            self.assertEqual(bool(got['ok']), bool(pick['ok']), where)
            self.assertEqual(sorted(got['reasons']), sorted(pick.get('reasons') or []), where)
        self.assertGreater(replayed, 40, 'the run should carry a quad for nearly every pick')

    def test_a_quad_that_repeats_a_corner_is_not_a_table(self):
        """A detection that returns the same point twice is not a table, whatever the tolerance."""
        seen = 0
        for vod, pick in self.picks:
            quad = [tuple(q) for q in (pick.get('quad') or [])]
            if len(quad) == 4 and len(set(quad)) < 4:
                seen += 1
                self.assertFalse(pick['ok'], '%s@%s repeats a corner but was accepted' % (vod, pick.get('at')))
        self.assertGreater(seen, 0, 'the recorded run has degenerate quads: keep this guard')

    def test_the_passing_floor_holds(self):
        self.assertGreaterEqual(len(self.data['passing']), FLOOR,
                                'fewer events pass at every sampled frame than the measured floor')


if __name__ == '__main__':
    unittest.main()
