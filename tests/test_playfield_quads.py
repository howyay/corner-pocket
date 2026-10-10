"""The recorded playfield quads still get the verdicts they were measured with.

``tools/playfield_vod_audit.py`` runs the table detector over the historical VODs and records
every sampled quad together with the verdict the check gave it.  This test replays those quads
through the check.  Move a tolerance, or change what counts as a table, and the recorded
verdicts stop matching - without paying for the detector a second time.  It also reads the
record's own provenance back: the producer, the rule set, the floor and the named exceptions
must still be the ones the tool holds, so the golden record stays equal to the code
that built it.

    PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_playfield_quads.py'
"""
import hashlib
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.playfield import PARALLEL_TOL_DEG, PLAYFIELD_IN, TILT_TOL_DEG, check_quad

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'tests/fixtures/playfield_quads.json'
RECORD = 'tests/fixtures/playfield_quads.json'
TOOL = ROOT / 'tools/playfield_vod_audit.py'
TOOL_NAME = 'tools/playfield_vod_audit.py'
RUN_LOG = ROOT / 'out/playfield_vod_audit.json'


def load_audit():
    """The audit tool as a module, imported by path with the video decoder blocked.

    ``tools`` is not a package, so the file is loaded by path.  An import runs the module body,
    and the tool is guarded: that body only defines names and opens no VOD.  The decoder is
    blocked here, so a guard that goes missing fails this test in a moment instead of decoding
    a VOD.  The block is removed again before any other test can see it.
    """
    saved = sys.modules.get('cv2')
    blocked = types.ModuleType('cv2')

    def no_vod(*args, **kwargs):
        raise RuntimeError('the import of %s must not open a VOD' % TOOL_NAME)

    blocked.VideoCapture = no_vod
    sys.modules['cv2'] = blocked
    try:
        spec = importlib.util.spec_from_file_location('playfield_vod_audit', TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop('cv2', None)
        else:
            sys.modules['cv2'] = saved
    return module


def recorded_state():
    """The bytes and the modification time of every file this test calls a record."""
    state = {}
    for path in (RUN, RUN_LOG):
        if path.exists():
            state[str(path)] = (hashlib.sha1(path.read_bytes()).hexdigest(),
                                path.stat().st_mtime_ns)
    return state


STATE_BEFORE_IMPORT = recorded_state()
AUDIT = load_audit()
STATE_AFTER_IMPORT = recorded_state()


def defined_at(path, name):
    """The path and the 1-based line that defines a top-level name, for a failure message."""
    for number, line in enumerate((ROOT / path).read_text(encoding='utf-8').splitlines(), 1):
        if line.startswith(name):
            return '%s:%d' % (path, number)
    return path


def stale(hint):
    """The message for a record that no longer matches the code that built it."""
    return '%s: rebuild the record with .venv/bin/python %s --write-fixture' % (hint, TOOL_NAME)


def best_verdict(quad):
    """The stage tries two rotations of the polygon and keeps the better verdict."""
    rotated = quad[1:] + quad[:1]
    return min((check_quad(quad), check_quad(rotated)),
               key=lambda v: (not v['ok'], len(v['reasons'])))


class TheAuditToolImportsWithoutWritingTests(unittest.TestCase):
    """An import of the audit tool must define names only: no media, no write."""

    def test_the_import_wrote_no_record(self):
        changed = sorted(path for path, state in STATE_AFTER_IMPORT.items()
                         if STATE_BEFORE_IMPORT.get(path) != state)
        self.assertEqual(changed, [],
                         'the import of %s rewrote %s' % (TOOL_NAME, changed))

    def test_the_import_defines_the_rule_set_that_the_record_names(self):
        self.assertEqual(AUDIT.PRODUCER, TOOL_NAME, 'the tool must name itself as the producer')
        self.assertGreater(AUDIT.FLOOR, 0, 'the floor must be a positive count')
        self.assertTrue(AUDIT.KNOWN_REFUSED, 'the tool must name the events that do not pass')


class PlayfieldQuadReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RUN.exists():
            raise unittest.SkipTest('no recorded run: .venv/bin/python tools/playfield_vod_audit.py')
        cls.data = json.loads(RUN.read_text())
        cls.picks = [(p['vod'], p) for p in cls.data['picks']]

    def provenance(self, key):
        """The named part of the record's provenance, with a message when it is missing."""
        block = self.data.get('provenance') or {}
        self.assertIn(key, block, '%s holds no %r, so the record cannot name what built it: %s'
                      % (RECORD, key, sorted(block)))
        return block[key]

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
        """A refusal the operator cannot diagnose stops the work, so the run records its numbers."""
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

    def test_the_record_names_the_producer_that_built_it(self):
        """A record that cannot name its producer cannot be rebuilt or judged."""
        producer = self.provenance('producer')
        self.assertEqual(producer, TOOL_NAME,
                         '%s names the producer %r, but the producer is %s'
                         % (RECORD, producer, TOOL_NAME))
        self.assertTrue((ROOT / producer).exists(), 'the named producer does not exist: %s' % producer)
        self.assertTrue(self.provenance('measured'),
                        '%s does not say when the run was measured' % RECORD)

    def test_the_record_names_the_rules_the_tolerance_was_built_with(self):
        """The tolerance is the measured threshold, so the record must carry the one it used."""
        rules = self.provenance('rules')
        self.assertEqual(rules['parallel_tol_deg'], PARALLEL_TOL_DEG,
                         stale('%s records parallel_tol_deg %r, but %s defines %r'
                               % (RECORD, rules['parallel_tol_deg'],
                                  defined_at('src/playfield.py', 'PARALLEL_TOL_DEG'), PARALLEL_TOL_DEG)))
        self.assertEqual(rules['tilt_tol_deg'], TILT_TOL_DEG,
                         stale('%s records tilt_tol_deg %r, but %s defines %r'
                               % (RECORD, rules['tilt_tol_deg'],
                                  defined_at('src/playfield.py', 'TILT_TOL_DEG'), TILT_TOL_DEG)))
        self.assertEqual(tuple(rules['playfield_in']), tuple(PLAYFIELD_IN),
                         stale('%s records playfield_in %r, but %s defines %r'
                               % (RECORD, rules['playfield_in'],
                                  defined_at('src/playfield.py', 'PLAYFIELD_IN'), PLAYFIELD_IN)))

    def test_the_record_names_the_floor_the_tool_gates_with(self):
        """The floor is the second lock, so a record with another floor is another rule set."""
        gate = self.provenance('gates')['floor']
        self.assertEqual(gate, AUDIT.FLOOR,
                         stale('%s records floor %r, but %s defines %r'
                               % (RECORD, gate, defined_at(TOOL_NAME, 'FLOOR'), AUDIT.FLOOR)))

    def test_the_record_names_the_exceptions_the_tool_gates_with(self):
        """A recorded name that is not the tool's name would hide a swapped exception."""
        named = sorted(AUDIT.KNOWN_REFUSED)
        recorded = sorted(self.provenance('gates')['known_refused'])
        self.assertEqual(recorded, named,
                         stale('%s records %d exceptions, but %s names %d'
                               % (RECORD, len(recorded), defined_at(TOOL_NAME, 'KNOWN_REFUSED'),
                                  len(named))))

    def test_every_event_that_does_not_pass_is_a_named_exception(self):
        """The tool fails a run over an unnamed refusal, so the record must not hold one."""
        named = set(AUDIT.KNOWN_REFUSED)
        refused = sorted({vod for vod, pick in self.picks if pick['ok'] is not True})
        unnamed = [vod for vod in refused if vod not in named]
        self.assertEqual(unnamed, [],
                         '%s holds an event that does not pass and is not named in %s: %s'
                         % (RECORD, defined_at(TOOL_NAME, 'KNOWN_REFUSED'), unnamed))

    def test_every_named_exception_is_an_event_that_does_not_pass(self):
        """An exception that passes hides a difference, and the counts must agree."""
        named = set(AUDIT.KNOWN_REFUSED)
        passing = list(self.data['passing'])
        self.assertEqual(sorted(set(passing) & named), [],
                         '%s passes at every frame and is also named in %s: %s'
                         % (RECORD, defined_at(TOOL_NAME, 'KNOWN_REFUSED'), sorted(set(passing) & named)))
        sampled = self.provenance('sampling')['vods']
        self.assertEqual(len(passing) + len(named), sampled,
                         stale('%s holds %d passing events and %d exceptions, but the run sampled %d events'
                               % (RECORD, len(passing), len(named), sampled)))

    def test_the_recorded_counts_cover_every_sampled_pick(self):
        """The counts are the run's own tally, so the record cannot claim a run it did not have."""
        self.assertIn('counts', self.data, '%s holds no counts' % RECORD)
        counts = self.data['counts']
        sampling = self.provenance('sampling')
        self.assertEqual(sorted(counts), ['no_quad', 'ok', 'refused', 'unreadable'])
        self.assertEqual(counts['ok'], sum(1 for _, pick in self.picks if pick['ok'] is True))
        self.assertEqual(counts['refused'], sum(1 for _, pick in self.picks if pick['ok'] is False))
        self.assertEqual(counts['ok'] + counts['refused'], len(self.picks),
                         stale('%s records %d picks with a table and counts %d'
                               % (RECORD, len(self.picks), counts['ok'] + counts['refused'])))
        self.assertEqual(sampling['picks_per_vod'], len(sampling['frame_fractions']))
        self.assertEqual(sum(counts.values()), sampling['vods'] * sampling['picks_per_vod'],
                         stale('%s counts %d picks, but the run sampled %d events of %d frames'
                               % (RECORD, sum(counts.values()), sampling['vods'],
                                  sampling['picks_per_vod'])))

    def test_the_record_names_the_sampling_the_run_used(self):
        """The record says how it sampled, so a reader can repeat the measurement."""
        sampling = self.provenance('sampling')
        self.assertEqual(sampling['stage'], AUDIT.STAGE_NOTE,
                         stale('%s records the stage %r, but %s defines %r'
                               % (RECORD, sampling['stage'], defined_at(TOOL_NAME, 'STAGE_NOTE'),
                                  AUDIT.STAGE_NOTE)))
        self.assertEqual(sorted(sampling['frame_fractions']), [0.1, 0.5, 0.9])

    def test_the_passing_floor_holds(self):
        self.assertGreaterEqual(len(self.data['passing']), AUDIT.FLOOR,
                                'fewer events pass at every sampled frame than the measured floor')


if __name__ == '__main__':
    unittest.main()
