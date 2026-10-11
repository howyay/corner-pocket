"""Hold the two verified frame times, and the coverage bar, to their owners.

A person verified two frames of ``vod30`` against the reference quad.  The
coverage of each frame is a fact of the calibration, and ``docs/calibration-truth.md``
states the pair.  Four modules held a literal copy of the times: the audit, the
measure tool, the fit and the report.  One edit of a frame had to move four
tuples and two comments, and no test compared them.

``src/calib_segments.py`` owns the pair now.  The four readers build their own
collections from the owner, so a collection keeps the times it needs and holds no
second copy of the fact.

The coverage bar is a second fact of the same family.  ``src/event_gates.py``
owns it as ``GateConfig.calibration_warn_fraction``, and ``src/calib_segment_fit.py``
applies it to a sample.  The fit read a number before, and its own prose called
that number a trigger while the gate called the field "reporting only".

This module reads the owner, the four readers and the gate.  It proves the
numbers, and it proves that each reader names the owner in its source, so a later
edit cannot put a literal back without a failure.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from src import (calib_mapping_audit, calib_segment_fit, calib_segment_measure,
                 calib_segments, segment_calib_report)
from src.event_gates import GateConfig

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
# The one home of the pair, and the name of the file it stands in.
OWNER = 'calib_segments.py'
OWNER_PATH = SRC / OWNER
# The two frames a person verified against the reference quad.
VERIFIED = (483.4, 1120.2)
# The name of the document that states the pair, and the name of the coverage bar.
TRUTH_DOC = 'docs/calibration-truth.md'
GATE_FIELD = 'calibration_warn_fraction'


def source_files():
    """The modules of ``src/``, in one stable order."""
    return tuple(sorted(SRC.glob('*.py')))


def numeric_constants(source):
    """``(line, value)`` for every float constant of one source text."""
    tree = ast.parse(source)
    return tuple((node.lineno, node.value) for node in ast.walk(tree)
                 if isinstance(node, ast.Constant) and isinstance(node.value, float))


def frame_sites(sources):
    """The ``file:line`` sites that state a verified frame, outside the owner.

    ``sources`` maps a file name to its text.  The walk reads the syntax tree, so
    a comment that states the time is not a site: only code is.  One line that
    states both frames is one site.
    """
    sites = set()
    for name, source in sorted(sources.items()):
        if name == OWNER:
            continue
        for line, value in numeric_constants(source):
            if value in VERIFIED:
                sites.add('%s:%d' % (name, line))
    return sorted(sites)


def named_in(source, *names):
    """The names of ``names`` that the source text uses as a name."""
    used = {node.id for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Name)}
    return tuple(name for name in names if name in used)


def assigned_value(source, name):
    """The value node of the module-level assignment to ``name``, or None."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return node.value
    return None


class VerifiedFrameHomeTest(unittest.TestCase):
    """The pair has one home, and the four readers name it."""

    def test_one_module_states_a_verified_frame(self):
        sources = {path.name: path.read_text() for path in source_files()}
        self.assertEqual([], frame_sites(sources),
                         'the frames of %s are one fact, and %s owns it' % (VERIFIED, OWNER))

    def test_the_walk_sees_a_planted_copy(self):
        planted = {'calib_mapping_audit.py': 'FRAME_TIMES = (70.0, 0.0, 483.4, 1120.2)\n'}
        self.assertEqual(['calib_mapping_audit.py:1'], frame_sites(planted),
                         'the walk must see a literal frame in a reader')

    def test_a_comment_may_state_the_time(self):
        prose = {'eval_events.py': '# measured at t=483.4 with all four rails verified\n'}
        self.assertEqual([], frame_sites(prose),
                         'the walk reads code only, so a comment is not a second owner')

    def test_the_owner_holds_the_pair_and_names_the_document(self):
        self.assertEqual(VERIFIED, tuple(calib_segments.VERIFIED_FRAMES))
        self.assertEqual(VERIFIED[0], calib_segments.VERIFIED_FRAME_LOW)
        self.assertEqual(VERIFIED[1], calib_segments.VERIFIED_FRAME_HIGH)
        self.assertIn(TRUTH_DOC, OWNER_PATH.read_text(),
                      'the owner must name the document that states the pair')

    def test_the_four_readers_take_the_times_from_the_owner(self):
        self.assertEqual((70.0, 0.0) + VERIFIED + (1800.0,),
                         tuple(calib_mapping_audit.FRAME_TIMES))
        for time in VERIFIED:
            self.assertIn(time, calib_segment_measure.CANDIDATE_TIMES)
        fit = (SRC / 'calib_segment_fit.py').read_text()
        self.assertEqual(('VERIFIED_FRAMES',), named_in(fit, 'VERIFIED_FRAMES'))
        report = (SRC / 'segment_calib_report.py').read_text()
        self.assertEqual(('VERIFIED_FRAME_LOW', 'VERIFIED_FRAME_HIGH'),
                         named_in(report, 'VERIFIED_FRAME_LOW', 'VERIFIED_FRAME_HIGH'))
        audit = (SRC / 'calib_mapping_audit.py').read_text()
        self.assertEqual(('VERIFIED_FRAMES',), named_in(audit, 'VERIFIED_FRAMES'))
        measure = (SRC / 'calib_segment_measure.py').read_text()
        self.assertEqual(('VERIFIED_FRAME_LOW', 'VERIFIED_FRAME_HIGH'),
                         named_in(measure, 'VERIFIED_FRAME_LOW', 'VERIFIED_FRAME_HIGH'))

    def test_the_two_frames_are_not_one_collection_in_a_reader(self):
        audit = (SRC / 'calib_mapping_audit.py').read_text()
        value = assigned_value(audit, 'FRAME_TIMES')
        self.assertIsNotNone(value, 'src/calib_mapping_audit.py must bind FRAME_TIMES')
        self.assertTrue(any(isinstance(node, ast.Starred) and isinstance(node.value, ast.Name)
                            and node.value.id == 'VERIFIED_FRAMES' for node in ast.walk(value)),
                        'FRAME_TIMES must unpack the owner, not repeat the two times')


class CoverageBarHomeTest(unittest.TestCase):
    """The coverage bar reads the gate field, and no module types it again."""

    def test_the_bar_reads_the_gate_field(self):
        self.assertEqual(GateConfig.calibration_warn_fraction, calib_segment_fit.GATE_FRACTION)
        self.assertIsInstance(calib_segment_fit.GATE_FRACTION, float)

    def test_the_bar_is_not_a_number_in_the_source(self):
        fit = (SRC / 'calib_segment_fit.py').read_text()
        value = assigned_value(fit, 'GATE_FRACTION')
        self.assertIsNotNone(value, 'src/calib_segment_fit.py must bind GATE_FRACTION')
        self.assertIsInstance(value, ast.Attribute,
                              'GATE_FRACTION must read the gate field, not a number')
        self.assertEqual(GATE_FIELD, value.attr)

    def test_no_other_module_binds_the_bar(self):
        offenders = []
        for path in source_files():
            if path.name in ('event_gates.py', 'calib_segment_fit.py'):
                continue
            for node in ast.parse(path.read_text()).body:
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and GATE_FIELD in target.id:
                        offenders.append('%s:%d' % (path.name, node.lineno))
        self.assertEqual([], offenders,
                         'the coverage bar of %s is owned by src/event_gates.py' % GATE_FIELD)


if __name__ == '__main__':
    unittest.main()
