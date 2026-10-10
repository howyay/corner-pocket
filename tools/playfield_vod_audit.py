"""Does the playfield check hold on the historical VODs, end to end?

Run it with the project's interpreter:

    .venv/bin/python tools/playfield_vod_audit.py

For every VOD in ``data/vods`` it takes frames at 10%, 50% and 90%, runs the real
``TableStage`` on them - no saved calibration artifact exists for any ``tw-*`` dataset,
so this is the measured path the console falls back to - and records the playfield
verdict with its reasons and metrics.

Two corrections shaped this tool.  A stage carries its measurement, so one stage per
event is required: a reused stage reported the same quad for ten picks and an earlier
run claimed 42 passes where the measured number is 24.  And the events that refuse
everywhere are not refusing a real table: their cloth mask is a band across a rail (the
probe on tw-2860883221 fitted a quad with an aspect of 8.345 against the 2.0 that a
100x50 inch playfield has), so the detector is what those events need - not a looser
tolerance.  They are named as exceptions instead of being averaged away.

The run reads VODs, so it costs minutes.  It always writes the run log
``out/playfield_vod_audit.json``.  How a recording is opened, which cadence the stage
measures on, and the frame's context come from ``tools/playfield_harness.py``, which reads
them from the served pipeline - this tool restates none of them, so it cannot measure an
older configuration than the console serves.  The golden record ``tests/fixtures/playfield_quads.json``
is a tracked file, so this tool rewrites it only when the caller asks for that write AND
every gate passes:

    .venv/bin/python tools/playfield_vod_audit.py --write-fixture

A run that fails a gate writes no fixture, and it prints the gate that failed.  A
regression therefore cannot enter the golden record.  The record names its
producer, its revision, its rule set, its counts, its gates and the hash of its
picks, and ``tests/test_playfield_quads.py`` reads them back.  The test computes
that hash again with its own code, so a hand edit of one pick fails the test.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.atomic_write import write_atomic
from src.playfield import PARALLEL_TOL_DEG, PLAYFIELD_IN, TILT_TOL_DEG
from tools.playfield_harness import Recording, frame_context, new_stage

ROOT = Path(__file__).resolve().parents[1]
PRODUCER = 'tools/playfield_vod_audit.py'
MEASURED = '2026-10-05, one stage per VOD'
# One stage per VOD: a reused stage carries its measurement across events, which made every
# event after the first report the same quad.  The audit measures each event on its own.
STAGE_NOTE = 'one stage per VOD, no saved calibration: measure, like live'
FRAME_FRACTIONS = (0.10, 0.50, 0.90)
RUN_LOG = ROOT / 'out/playfield_vod_audit.json'
FIXTURE = ROOT / 'tests/fixtures/playfield_quads.json'
USAGE = 'usage: .venv/bin/python tools/playfield_vod_audit.py [--write-fixture]'
# The record names the revision that produced it.  A missing git or a missing repository gives
# this value, and the run continues: a record with no revision is weaker evidence, not wrong
# evidence.  GIT_TIMEOUT_S stops a git call that hangs.
REVISION_UNKNOWN = 'unknown'
GIT_TIMEOUT_S = 10
# Two gates, both measured.  The floor is how many events pass at every sampled frame; the
# exceptions are the events that do not, each named with what its measurement actually was.  An
# event that refuses everywhere and is not named is a regression, so the run fails.
FLOOR = 8
KNOWN_REFUSED = {
    # The cloth mask is a band across a rail, so the fit collapses and no table is reported.
    'tw-2860883221.mp4': 'cloth mask is a band: the ordered fit collapses (aspect 8.345)',
    'tw-2871819680.mp4': 'cloth mask is a band: the ordered fit collapses',
    'tw-2885294870.mp4': 'cloth mask is a band: the ordered fit collapses',
    'tw-2890340436.mp4': 'cloth mask is a band: the ordered fit collapses',
    'tw-2890514774.mp4': 'cloth mask is a band: the ordered fit collapses',
    # A quad is measured and the check refuses it.
    'tw-2252489073.mp4': 'measured quad refused: no-parallel-pair',
    'tw-2467528195.mp4': 'measured quad refused: no-parallel-pair',
    'tw-2784932919.mp4': 'measured quad refused: no-parallel-pair',
    'tw-2796131568.mp4': 'measured quad refused: no-parallel-pair',
    # No table comes out at all.
    'tw-2251161439.mp4': 'no quad measured',
    'tw-2638346864.mp4': 'no quad measured',
}


def label(path):
    """The path as a checkout-relative name when it is inside the repository."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def sha1(path):
    """The SHA-1 of the bytes of a file, for a message that names the record it wrote."""
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def picks_sha1(picks):
    """The hash of the picks, over one stated sequence of bytes.

    The bytes are the picks as JSON text.  The keys are sorted, the separators carry no
    space, and the encoding is UTF-8.  ``tests/test_playfield_quads.py`` builds the same
    bytes with its own code and compares the two hashes, so one hand edit of one pick
    fails the test.
    """
    body = json.dumps(picks, sort_keys=True, separators=(',', ':'))
    return hashlib.sha1(body.encode('utf-8')).hexdigest()


def git_revision():
    """The revision of this checkout, or REVISION_UNKNOWN when git cannot name one.

    The record must name the revision that produced it, so a reader can compare the record
    with the code of that revision.  A missing git, a missing repository, a slow call and a
    rejected call all give REVISION_UNKNOWN, and none of them stops the run.
    """
    try:
        done = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return REVISION_UNKNOWN
    revision = done.stdout.strip()
    if done.returncode != 0 or len(revision) != 40:
        return REVISION_UNKNOWN
    if any(char not in '0123456789abcdef' for char in revision):
        return REVISION_UNKNOWN
    return revision


def passes_at_every_frame(report):
    """The events whose every sampled pick passed the playfield check."""
    return sorted(row['vod'] for row in report if row['verdict'] == 'pass')


def gate_failures(report, *, floor=FLOOR, known_refused=KNOWN_REFUSED):
    """Every gate that this measured run does not pass, as (gate name, message) pairs.

    The caller must name the gate that failed, because a refusal without a name cannot be
    acted on.  ``readable``: every recording was read - a file that cannot be opened is not a
    detector refusal, and a known-refused name must not become a silent pass.  ``exceptions``:
    an event that refuses at every sampled frame must be named in KNOWN_REFUSED.  ``floor``:
    at least `floor` events must pass at every sampled frame.
    """
    failures = []
    unreadable = sorted(row['vod'] for row in report if row['verdict'] == 'unreadable')
    if unreadable:
        failures.append(('readable', 'recordings that could not be read: %s' % (unreadable,)))
    unexpected = sorted(row['vod'] for row in report
                        if row['verdict'] != 'pass' and row['vod'] not in known_refused)
    if unexpected:
        failures.append(('exceptions', 'events that refuse everywhere and are not named: %s'
                         % (unexpected,)))
    passing = passes_at_every_frame(report)
    if len(passing) < floor:
        failures.append(('floor', '%d events pass at every frame, floor is %d'
                         % (len(passing), floor)))
    return failures


def fixture_payload(report, counts, passing):
    """The golden record of one run: the provenance, the gates, the verdicts, the picks.

    A reader must see which revision and which rule set built the record, so the record
    carries them with the picks.  A record without them cannot be judged against the code
    that made it.  The record carries the hash of its picks, and the verdict of every
    sampled event, so a reader can verify the picks and name a refusal that no lock covers.
    """
    picks = [{'vod': row['vod'], 'at': pick['at'], 'quad': pick.get('quad'),
              'ok': pick.get('ok'), 'reasons': pick.get('reasons'),
              'aspect': pick.get('aspect'),
              'best_parallel_deg': pick.get('best_parallel_deg')}
             for row in report for pick in row['picks'] if pick.get('quad')]
    return {
        'provenance': {
            'producer': PRODUCER,
            'measured': MEASURED,
            'revision': git_revision(),
            'picks_sha1': picks_sha1(picks),
            'sampling': {'frame_fractions': list(FRAME_FRACTIONS),
                         'picks_per_vod': len(FRAME_FRACTIONS),
                         'vods': len(report),
                         'stage': STAGE_NOTE},
            'rules': {'parallel_tol_deg': PARALLEL_TOL_DEG,
                      'tilt_tol_deg': TILT_TOL_DEG,
                      'playfield_in': list(PLAYFIELD_IN)},
            'gates': {'floor': FLOOR, 'known_refused': sorted(KNOWN_REFUSED)},
        },
        'counts': counts,
        'passing': passing,
        'verdicts': {row['vod']: row['verdict'] for row in report},
        'picks': picks,
    }


def measure_vods():
    """Measure every VOD on the real detector path and return (report, counts)."""
    vods = sorted((ROOT / 'data/vods').glob('*.mp4'))
    report, counts = [], {'ok': 0, 'refused': 0, 'no_quad': 0, 'unreadable': 0}
    for vp in vods:
        # One stage per VOD: this stage carries its measurement, so a stage reused across
        # events reports the first event's quad for all of them.
        stage = new_stage(ROOT)
        try:
            recording = Recording(vp)
        except OSError as exc:
            # A recording that cannot be read is not a refusal by the detector, and it must not
            # pass as one: it gets its own verdict, and the gate below names it.
            print('%s: %s' % (vp.name, exc), flush=True)
            counts['unreadable'] += 1
            report.append({'vod': vp.name, 'frames': None, 'fps': None, 'picks': [],
                           'verdict': 'unreadable'})
            continue
        with recording:
            n, fps = recording.frame_count, recording.fps
            row = {'vod': vp.name, 'frames': n, 'fps': round(fps, 3), 'picks': []}
            for frac in FRAME_FRACTIONS:
                idx, frame = recording.frame_at(frac)
                if frame is None:
                    row['picks'].append({'at': idx, 'read': False}); counts['unreadable'] += 1; continue
                ctx = frame_context(idx, fps)
                try:
                    res = stage.process(frame, ctx) or {}
                except Exception as exc:
                    row['picks'].append({'at': idx, 'error': str(exc)[:120]}); counts['unreadable'] += 1; continue
                pf = res.get('table_playfield')
                entry = {'at': idx, 't_s': round(idx / fps, 1),
                         'aspect': None if not pf else pf.get('aspect'),
                         'best_parallel_deg': None if not pf else pf.get('best_parallel_deg'),
                         'quad': [[round(float(q[0]), 1), round(float(q[1]), 1)]
                                  for q in (res.get('table_polygon') or [])],
                         'polygon': bool(res.get('table_polygon')),
                         'ok': None if not pf else bool(pf.get('ok')),
                         'reasons': (pf or {}).get('reasons')}
                if pf is None:
                    counts['no_quad'] += 1
                elif pf.get('ok'):
                    counts['ok'] += 1
                else:
                    counts['refused'] += 1
                row['picks'].append(entry)
            ok_flags = [p.get('ok') for p in row['picks']]
            row['verdict'] = ('pass' if all(f is True for f in ok_flags)
                              else 'refuse' if all(f is False for f in ok_flags)
                              # Every pick read but no table came out of any of them: that is not "mixed",
                              # and calling it that hid seven events behind one word.
                              else 'no_quad' if all(f is None for f in ok_flags) else 'mixed')
        report.append(row)
        print('%-24s %-7s %s' % (vp.name, row['verdict'], ' '.join(
            'ok' if p.get('ok') else ('refused' if p.get('ok') is False else 'no-quad')
            for p in row['picks'])), flush=True)
    return report, counts


def main(argv=None):
    """Measure every VOD, run the gates, and write the golden record only when asked."""
    args = list(sys.argv[1:]) if argv is None else list(argv)
    unknown = [arg for arg in args if arg != '--write-fixture']
    if unknown:
        print('unknown argument: %s' % (unknown,), flush=True)
        print(USAGE, flush=True)
        return 2
    write_fixture = '--write-fixture' in args
    report, counts = measure_vods()
    if not report:
        print('NO VODS: %s holds no .mp4 file' % (label(ROOT / 'data/vods'),), flush=True)
        return 1
    passing = passes_at_every_frame(report)
    print('SUMMARY', json.dumps(counts), flush=True)
    print('PASS-AT-EVERY-FRAME', json.dumps(passing), flush=True)
    # The run log is the record of the last run, and a failing run must stay inspectable, so
    # this file is written before the gates and written even when a gate fails.
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(RUN_LOG, lambda stream: stream.write(json.dumps(
        {'counts': counts, 'passing': passing, 'measured': MEASURED, 'report': report}, indent=1)))
    failures = gate_failures(report)
    for name, message in failures:
        print('GATE FAIL %s: %s' % (name, message), flush=True)
    if failures:
        if write_fixture:
            print('FIXTURE WRITE REFUSED: %s not written: gate %s failed'
                  % (label(FIXTURE), ', gate '.join(name for name, _ in failures)), flush=True)
        return 1
    print('EXCEPTIONS OK: %d named, %d not passing'
          % (len(KNOWN_REFUSED), sum(1 for row in report if row['verdict'] != 'pass')), flush=True)
    print('THRESHOLD OK: %d events pass at every frame (floor %d)' % (len(passing), FLOOR), flush=True)
    if not write_fixture:
        print('FIXTURE NOT WRITTEN: %s: pass --write-fixture to record this run'
              % label(FIXTURE), flush=True)
        return 0
    payload = fixture_payload(report, counts, passing)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(FIXTURE, lambda stream: stream.write(json.dumps(payload, indent=1)))
    print('FIXTURE WRITTEN: %s: %d picks over %d events, counts %s, revision %s, file sha1 %s'
          % (label(FIXTURE), len(payload['picks']), payload['provenance']['sampling']['vods'],
             json.dumps(counts), payload['provenance']['revision'], sha1(FIXTURE)), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
