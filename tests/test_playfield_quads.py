"""The recorded playfield quads still get the verdicts they were measured with.

``tools/playfield_vod_audit.py`` runs the table detector over the historical VODs and records
every sampled quad together with the verdict the check gave it.  This test replays those quads
through the check.  Move a tolerance, or change what counts as a table, and the recorded
verdicts stop matching - without paying for the detector a second time.  It also reads the
record's own provenance back: the producer, the revision, the rule set, the floor and the named
exceptions must still be the ones the tool holds, so the golden record stays equal to the code
that built it.  The record carries the hash of its picks, and this test builds the hashed bytes
again with its own code, so a hand edit of one pick fails it.

The audit is also the one owner of the refused event ids and of their reasons.  The evidence
tool reads that owner, and the last cases here scan the other tools for a second copy of an id
list or of a reason.  The two tools held the same five ids in two spellings with no shared
source before, so a move of one copy could not move the other.

    PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_playfield_quads.py'
"""
import ast
import hashlib
import importlib.util
import io
import json
import re
import sys
import tokenize
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
#: The one owner of the refused event ids and of their reasons.
OWNER = TOOL_NAME
EVIDENCE_NAME = 'tools/playfield_quad_evidence.py'
#: The tools that must not hold a copy of the id list.
OTHER_TOOLS = (EVIDENCE_NAME, 'tools/playfield_harness.py')
#: A refused event id, as the tools spell it: a recording name without its suffix.
VOD_ID = re.compile(r"tw-\d{6,}")


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


def load_module(path, name):
    """A tool loaded by path, with the video decoder blocked for the duration of the import.

    ``tools`` is not a package, so a tool loads by path.  The block makes a guard that goes
    missing fail in a moment instead of decoding a recording, and the saved module goes back
    before any other test can see the block.
    """
    saved = sys.modules.get('cv2')
    blocked = types.ModuleType('cv2')

    def no_vod(*args, **kwargs):
        raise RuntimeError('the import of %s must not open a VOD' % path)

    blocked.VideoCapture = no_vod
    sys.modules['cv2'] = blocked
    try:
        spec = importlib.util.spec_from_file_location(name, ROOT / path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop('cv2', None)
        else:
            sys.modules['cv2'] = saved
    return module


def load_evidence():
    """The evidence tool as a module, imported with the video decoder blocked.

    The evidence tool reads the audit tool, which is the one owner of the refused ids and of
    their reasons.  The guard below compares the two, so it loads its own copy of the owner
    and holds the facts of that copy.  An import must open no recording.
    """
    return load_module(EVIDENCE_NAME, 'playfield_quad_evidence')


def source(path):
    """The text of a checkout-relative file."""
    return (ROOT / path).read_text(encoding='utf-8')


def string_literals(path):
    """Every string of one file that is not a docstring, as a list of its text.

    A reason belongs in the map of the owner.  A sentence of a docstring may name a reason,
    and that is not a copy of it.  Python names the docstrings with its own reads of the
    file, so this test guesses no rule about quoting.
    """
    text = (ROOT / path).read_text(encoding='utf-8')
    docstrings = set()
    for node in ast.walk(ast.parse(text)):
        body = getattr(node, 'body', None)
        first = body[0] if isinstance(body, list) and body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            docstrings.add((first.value.lineno, first.value.col_offset))
    found = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.STRING or (token.start[0], token.start[1]) in docstrings:
            continue
        # The token keeps its quotes.  Python reads it back, so the quotes and the escapes
        # cannot hide a copy of a reason.
        try:
            found.append(ast.literal_eval(token.string))
        except (SyntaxError, ValueError):
            found.append(token.string)
    return found


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


class TheRefusedIdsHaveOneOwnerTests(unittest.TestCase):
    """The refused event ids and their reasons live in one tool.  The other tool reads them."""

    def test_no_other_tool_holds_a_list_of_vod_ids(self):
        """A second list of ids is the defect this guard exists for.

        The audit tool holds the ids, each one with the reason of its refusal.  The evidence
        tool held the same five ids as a bare tuple in another spelling, so a move of one list
        did not move the other.  Every tool of this pair must read the one owner.
        """
        copied = {}
        for path in OTHER_TOOLS:
            found = sorted(set(VOD_ID.findall(source(path))))
            if found:
                copied[path] = found
        self.assertEqual(copied, {},
                         'these tools hold a VOD id: %s.  Read %s instead of copying it'
                         % (copied, OWNER))

    def test_the_evidence_tool_reads_the_owner_and_holds_no_id_of_its_own(self):
        """The provider must take its ids from the owner, and every id must match."""
        provider = load_evidence()
        self.assertIn('KNOWN_REFUSED', source(EVIDENCE_NAME),
                      '%s must read the exceptions from %s' % (EVIDENCE_NAME, OWNER))
        self.assertEqual(list(provider.KNOWN_REFUSED), list(AUDIT.KNOWN_REFUSED),
                         '%s and %s read different exceptions' % (EVIDENCE_NAME, OWNER))
        owner_ids = sorted(name[:-4] for name, reason in AUDIT.KNOWN_REFUSED.items()
                           if reason.startswith(provider.CLOTH_REASON))
        self.assertEqual(list(provider.REFUSED), owner_ids,
                         'the provided ids must be the owner ids with that one reason')
        self.assertEqual(len(owner_ids), 5,
                         '%s must provide one id for each of the five events' % EVIDENCE_NAME)

    def test_no_other_tool_holds_a_copy_of_a_reason(self):
        """One reason string has one home: the owner's map.

        A copy is the reason as a string of its own.  The scan reads the strings of the code
        and skips the docstrings, so a sentence that names the same words is not a copy.
        """
        reasons = sorted({reason for reason in AUDIT.KNOWN_REFUSED.values() if reason})
        copied = {path: [reason for reason in reasons if reason in string_literals(path)]
                  for path in OTHER_TOOLS}
        self.assertEqual({path: found for path, found in copied.items() if found}, {},
                         'a tool copies a reason that %s owns' % OWNER)


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

    def test_the_record_names_the_revision_that_produced_it(self):
        """A record that names no revision cannot be compared with the code that made it.

        The tool owns the two forms: a git revision of 40 hexadecimal digits, or the marker it
        writes when git does not answer.  A record with neither form is hand edited.
        """
        revision = self.provenance('revision')
        self.assertIsInstance(revision, str,
                              '%s records revision %r, but a revision is text' % (RECORD, revision))
        is_revision = len(revision) == 40 and all(c in '0123456789abcdef' for c in revision)
        self.assertTrue(is_revision or revision == AUDIT.REVISION_UNKNOWN,
                        stale('%s records revision %r, but the tool writes 40 hexadecimal digits or %r'
                              % (RECORD, revision, AUDIT.REVISION_UNKNOWN)))

    def test_the_record_carries_the_hash_of_the_picks_it_holds(self):
        """A hand edit of one pick changes this hash, so the record cannot claim that pick.

        This test builds the hashed bytes with its own code.  The rule is in the tool: the
        picks as JSON text, with sorted keys, without spaces, in UTF-8.  The test then calls
        the tool's own function, because two rules that disagree cannot both be right.
        """
        recorded = self.provenance('picks_sha1')
        body = json.dumps(self.data['picks'], sort_keys=True, separators=(',', ':'))
        expected = hashlib.sha1(body.encode('utf-8')).hexdigest()
        self.assertEqual(recorded, expected,
                         stale('%s records picks_sha1 %s, but its picks hash to %s'
                               % (RECORD, recorded, expected)))
        self.assertEqual(recorded, AUDIT.picks_sha1(self.data['picks']),
                         '%s and %s give different hashes for the same picks'
                         % (RECORD, defined_at(TOOL_NAME, 'picks_sha1')))

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
        """The tool fails a run over an unnamed refusal, so the record must not hold one.

        The record names the verdict of every sampled event, so this test sees an event that
        produced no quad at all.  A reading of the picks alone cannot see that event, and it
        would let a refusal through that no lock covers.
        """
        self.assertIn('verdicts', self.data,
                      stale('%s holds no verdicts, so this test cannot name a refusal' % RECORD))
        verdicts = self.data['verdicts']
        sampled = self.provenance('sampling')['vods']
        self.assertEqual(len(verdicts), sampled,
                         stale('%s names %d verdicts, but the run sampled %d events'
                               % (RECORD, len(verdicts), sampled)))
        unknown = sorted({vod for vod, _ in self.picks} - set(verdicts))
        self.assertEqual(unknown, [],
                         stale('%s holds picks of events outside its verdicts: %s'
                               % (RECORD, unknown)))
        named = set(AUDIT.KNOWN_REFUSED)
        refused = sorted(vod for vod, verdict in verdicts.items() if verdict != 'pass')
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
