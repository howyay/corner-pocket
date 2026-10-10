"""One harness for the playfield audit tools: one owner of the cadence, one way to read a VOD.

Both playfield tools measure the served table stage on historical recordings, and each carried
its own copy of that measurement path: open the container, take the frame at a fraction, build
one stage per event, build the frame's context, and spell the cadence again.  The copies drifted
from the served pipeline they claimed to measure - the cadence was written as a literal in both
tools, and a recording that could not be opened was reported as "no quad measured", which the
exceptions gate accepts for a known-refused event.

These cases hold the new shape: one definition of the cadence in the pipeline, ``tools`` spells
it once (in the harness), both tools drive the stage and the context through the harness, and a
recording that cannot be read fails the run under its own gate.
"""
import importlib.util
import inspect
import re
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = 'tools/playfield_harness.py'
AUDIT = 'tools/playfield_vod_audit.py'
EVIDENCE = 'tools/playfield_quad_evidence.py'
TOOLS = (AUDIT, EVIDENCE)
#: The roots that hold the served pipeline and the code that measures it.
SOURCES = ('annotator', 'src', 'tools', 'scripts')


def source(path):
    """The text of a checkout-relative file."""
    return (ROOT / path).read_text(encoding='utf-8')


def modules_under(*roots):
    """Every .py file under the given roots, as checkout-relative paths."""
    found = []
    for root in roots:
        found.extend(path.relative_to(ROOT).as_posix()
                     for path in sorted((ROOT / root).rglob('*.py'))
                     if '__pycache__' not in path.parts)
    return found


def load(path, name):
    """A module loaded by path: ``tools`` is not a package, so the tools load this way too."""
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_audit():
    """The audit tool as a module, imported with the video decoder blocked.

    An import runs the module body: it must define names only and open no recording.  The
    decoder is blocked here so a guard that goes missing fails in a moment instead of decoding
    a VOD, and the block is removed again before any other test can see it.
    """
    saved = sys.modules.get('cv2')
    blocked = types.ModuleType('cv2')

    def no_vod(*args, **kwargs):
        raise RuntimeError('the import of %s must not open a recording' % AUDIT)

    blocked.VideoCapture = no_vod
    sys.modules['cv2'] = blocked
    try:
        return load(AUDIT, 'playfield_vod_audit_harness_test')
    finally:
        if saved is None:
            sys.modules.pop('cv2', None)
        else:
            sys.modules['cv2'] = saved


sys.path.insert(0, str(ROOT))
HARNESS_MODULE = load(HARNESS, 'playfield_harness_test')
AUDIT_MODULE = load_audit()


class TheCadenceHasOneOwnerTests(unittest.TestCase):
    """The measurement cadence is stated once, and every default that names it agrees."""

    def test_one_module_assigns_the_cadence(self):
        owners = [path for path in modules_under(*SOURCES)
                  if re.search(r'^TABLE_MEASURE_EVERY_N\s*=', source(path), re.M)]
        self.assertEqual(owners, ['annotator/pipeline_stages.py'],
                         'the cadence must have exactly one definition')

    def test_tools_spell_the_cadence_nowhere(self):
        spelled = [path for path in TOOLS
                   if re.search(r'measure_every_n\s*=\s*\d', source(path))]
        self.assertEqual(spelled, [], 'a tool must read the cadence, not restate it')

    def test_tools_name_the_one_harness(self):
        for path in TOOLS:
            text = source(path)
            for name in ('Recording', 'frame_context', 'new_stage'):
                self.assertIn(name, text, '%s must drive %s through the harness' % (path, name))

    def test_every_default_that_names_the_cadence_agrees_with_the_owner(self):
        from annotator.live_processing import LiveProcessor
        from annotator.pipeline_stages import (TABLE_MEASURE_EVERY_N, TableStage,
                                               default_stages)
        named = {
            'TableStage.__init__': inspect.signature(TableStage.__init__)
            .parameters['measure_every_n'].default,
            'default_stages': inspect.signature(default_stages)
            .parameters['table_measure_every_n'].default,
            'LiveProcessor.__init__': inspect.signature(LiveProcessor.__init__)
            .parameters['table_measure_every_n'].default,
            'playfield_harness.new_stage': HARNESS_MODULE.new_stage(ROOT).measure_every_n,
        }
        self.assertEqual(named, {name: TABLE_MEASURE_EVERY_N for name in named},
                         'every default must be the one named value')

    def test_the_fallback_rate_is_spelled_once_in_tools(self):
        spelled = [path for path in modules_under('tools')
                   if re.search(r'\b30\.0\b', source(path))]
        self.assertEqual(spelled, [HARNESS],
                         'the frame-rate fallback must be spelled once, in the harness')


class AnUnreadableRecordingTests(unittest.TestCase):
    """A recording that cannot be read is a failed run, not a detector refusal."""

    def test_the_harness_refuses_a_file_it_cannot_read(self):
        broken = ROOT / 'out' / 'test_playfield_harness_not_a_video.mp4'
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_bytes(b'this file is not a recording\n')
        try:
            with self.assertRaises(OSError) as caught:
                HARNESS_MODULE.Recording(broken)
        finally:
            broken.unlink()
        self.assertIn('cannot open', str(caught.exception))

    def test_a_known_refused_name_that_was_not_read_fails_the_run(self):
        name = 'tw-2251161439.mp4'
        self.assertIn(name, AUDIT_MODULE.KNOWN_REFUSED,
                      'this case needs a name the exceptions gate accepts')
        report = [{'vod': name, 'frames': None, 'fps': None, 'picks': [],
                   'verdict': 'unreadable'}]
        failures = AUDIT_MODULE.gate_failures(report, floor=0)
        gates = dict(failures)
        self.assertIn('readable', gates, 'an unread recording must fail under its own gate')
        self.assertIn(name, gates['readable'],
                      'the failure must name the recording that was not read')

    def test_a_known_refusal_still_passes_every_gate(self):
        report = [{'vod': name, 'frames': 100, 'fps': 30.0,
                   'picks': [{'at': 1, 'ok': None}], 'verdict': 'no_quad'}
                  for name in sorted(AUDIT_MODULE.KNOWN_REFUSED)]
        self.assertEqual(AUDIT_MODULE.gate_failures(report, floor=0), [],
                         'a named refusal must stay accepted')


if __name__ == '__main__':
    unittest.main()
