"""The recorded playfield quads still get the verdicts they were measured with.

``tools/playfield_vod_audit.py`` runs the table detector over the historical VODs and records
every sampled quad together with the verdict the check gave it.  This test replays those quads
through the check.  Move a tolerance, or change what counts as a table, and the recorded
verdicts stop matching - without paying for the detector a second time.  It also holds the
floor: at least eight of the nineteen events must pass at every sampled frame, and no event may
refuse everywhere without being named in the audit's exception list.

    .venv/bin/python -m unittest tests.test_playfield_quads
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.playfield import PARALLEL_TOL_DEG, check_quad

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'tests/fixtures/playfield_quads.json'
# The measured floor: eight events pass at every sampled frame, and the eleven that do not
# are named in tools/playfield_vod_audit.py's KNOWN_REFUSED with what their measurement was.
FLOOR = 8


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
        self.assertGreater(replayed, 30, 'the run should carry a quad for nearly every pick')

    def test_the_recorded_run_has_no_degenerate_quad(self):
        """A quad that repeats a corner is refused by the fit, so the run cannot contain one.

        The synthetic cases live in tests/test_table_detect.py; this checks the measured run, where
        five events used to come back as a thin wedge with one corner listed twice.
        """
        repeated = ['%s@%s' % (vod, pick.get('at')) for vod, pick in self.picks
                    if len(set(tuple(q) for q in (pick.get('quad') or []))) < 4]
        self.assertEqual(repeated, [], 'the fit let a degenerate quad through: %s' % (repeated,))

    def test_a_refused_pick_records_the_metric_that_refused_it(self):
        """A refusal the operator cannot diagnose is a dead end, so the run records its numbers."""
        refused = 0
        for vod, pick in self.picks:
            if pick['ok'] is not False:
                continue
            refused += 1
            where = '%s@%s' % (vod, pick.get('at'))
            self.assertTrue(pick.get('reasons'), 'refused without a reason: ' + where)
            self.assertTrue(pick.get('aspect') is not None and pick.get('best_parallel_deg') is not None,
                            'refused without the metrics that refused it: ' + where)
            if 'no-parallel-pair' in (pick.get('reasons') or []):
                self.assertGreater(pick['best_parallel_deg'], PARALLEL_TOL_DEG,
                                   'refused for parallelism inside the tolerance: ' + where)
        self.assertGreater(refused, 0, 'the recorded run carries refusals: keep the metrics')

    def test_the_passing_floor_holds(self):
        self.assertGreaterEqual(len(self.data['passing']), FLOOR,
                                'fewer events pass at every sampled frame than the measured floor')


if __name__ == '__main__':
    unittest.main()
