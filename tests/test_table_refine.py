"""Cloth-boundary detector contract: confidence/reason, refinement, no crash.

The synthetic frames here build a blue bed inside a dark rail so the detector has
a boundary to find without any VOD on disk; the recorded-reference test is skipped
when ``out/corners_30min_v2.json`` is absent (it is an artifact, not source).
"""
import ast
import importlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src import calib_segments
from src.table_detect import detect_table
from src.table_detect import _order_corners
from src.table_refine import (_DATASET_PRIOR, CHECK_UNAVAILABLE, detect_table_refined, load_priors,
                              prior_for, prior_provenance, prior_spec, refine_quad_edges)

ROOT = Path(__file__).resolve().parent.parent

# The corners v2 file has one home, ``src/calib_segments.py``.  The six modules
# below read its path from that owner.  The note of the ``vod30`` prior speaks
# about the file, so the count of its readers must hold readers and not
# spellings.  A module that writes the path by hand agrees with the owner only
# until the next rename.
CORNERS_V2_OWNER = 'src/calib_segments.py'
CORNERS_V2_NAME = calib_segments.corners_v2_name()
CORNERS_V2_READERS = (
    ('src/eval_table_detect.py', 'CORNERS_V2'),
    ('src/calib_segment_measure.py', 'SCAN_QUAD'),
    ('src/rebuild_events_v2.py', 'CORNERS'),
    ('src/calib_vod30.py', 'CORNERS'),
    ('src/pid_identity.py', 'QUAD'),
    ('src/pid_shooter.py', 'QUAD'),
)

# The readers that bind a path and import without the video reader of the
# repository.  This test compares their live answer with the answer of the home.
CORNERS_V2_LIVE = ('src/eval_table_detect.py', 'src/calib_segment_measure.py',
                   'src/rebuild_events_v2.py', 'src/calib_vod30.py')


def reader_problem(relative, name):
    """The message for one reader whose binding does not read the owner, or None.

    A module that spells the path itself counts as a reader of the file today,
    and its path agrees with the owner only until the next rename.  This answer
    reads the binding of the module, so the count below holds real readers.  The
    two readers that load the quad at import time need the video reader of the
    repository, so this test reads their text and not their import.
    """
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'), filename=relative)
    aliases = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or '').endswith('calib_segments'):
            aliases += [word.asname or word.name for word in node.names
                        if word.name == 'corners_v2_path']
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if any(isinstance(inner, ast.Name) and inner.id in aliases for inner in ast.walk(node.value)):
            return None
        return (f'{relative}:{node.lineno} {name} = {ast.unparse(node.value)} does not read '
                f'{CORNERS_V2_OWNER}')
    return f'{relative} binds no module-level {name}'


def bed_frame(quad=None, occlude=None, cloth_bgr=(150, 100, 50), rail_px=30):
    """Synthetic 640x360 frame shaped like the vod30 geometry.

    The bed covers ~9.5% of the frame, the same fraction the saved vod30 quad
    covers, so the app's quad-sanity rules (2%-90% area, inside the frame) behave
    here exactly as they do on the recording.  Brightness is ordered the way the
    real frames are - cloth (gray ~93) brighter than the rail band (~55), bright
    outside (~160) - because the detector requires that rail signature before it
    will call a crossing a table boundary.
    """
    w, h = 640, 360
    frame = np.full((h, w, 3), 160, dtype=np.uint8)                 # bright outside
    if quad is None:
        quad = np.array([[102, 124], [372, 124], [472, 279], [102, 279]], dtype=np.int32)
    # A rail band of constant width: offset each side line outward by rail_px and
    # intersect neighbours (a centroid-scaled quad would give a band that is thick
    # on the long sides and thin on the short ones).
    q = quad.astype(np.float64)
    centre = q.mean(axis=0)
    lines = []
    for i in range(4):
        a, b = q[i], q[(i + 1) % 4]
        d = b - a
        d = d / max(float(np.linalg.norm(d)), 1e-9)
        nrm = np.array([-d[1], d[0]])
        if np.dot(nrm, (a + b) / 2.0 - centre) < 0:
            nrm = -nrm
        lines.append((a + nrm * rail_px, d))
    rail = []
    for i in range(4):
        p1, d1 = lines[i]
        p2, d2 = lines[(i + 1) % 4]
        m = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]])
        t = np.linalg.solve(m, p2 - p1)
        rail.append(p1 + t[0] * d1)
    cv2.fillConvexPoly(frame, np.asarray(rail, np.int32), (55, 55, 55))      # dark rail
    cv2.fillConvexPoly(frame, quad.astype(np.int32), tuple(int(v) for v in cloth_bgr))
    if occlude is not None:
        # A body is mid-brightness: it must not look like a rail band, and it must
        # not offer the dark-rail + bright-outside signature either.
        for rect in occlude:
            cv2.rectangle(frame, rect[0], rect[1], (112, 112, 112), -1)
    return frame, quad.astype(np.float32)


class DetectorContractTests(unittest.TestCase):
    corners = np.array([[102, 124], [372, 124], [472, 279], [102, 279]], dtype=np.float32)

    def test_dict_contract_is_superset_of_the_naive_one(self):
        frame, quad = bed_frame()
        result = detect_table_refined(frame)
        for key in ('corners', 'mask', 'debug'):
            self.assertIn(key, result)
        for key in ('confidence', 'reason', 'source', 'refined', 'prior', 'debug_info'):
            self.assertIn(key, result)
        self.assertEqual(result['confidence'], 0.4)
        self.assertEqual(result['reason'], 'no_prior')
        self.assertFalse(result['refined'])
        self.assertEqual(result['source'], 'naive')

    def test_dark_frame_is_refused_with_a_reason_not_a_guess(self):
        frame = np.full((360, 640, 3), 12, dtype=np.uint8)
        result = detect_table_refined(frame, prior=self.corners)
        self.assertIsNone(result['corners'])
        self.assertEqual(result['confidence'], 0.0)
        self.assertIn(result['reason'], ('low_cloth_area', 'no_boundary_evidence', 'prior_disagreement'))
        self.assertIsInstance(result['debug_info'], dict)

    def test_blank_frame_without_prior_reports_no_cloth(self):
        frame = np.full((360, 640, 3), 250, dtype=np.uint8)
        result = detect_table_refined(frame)
        self.assertIsNone(result['corners'])
        self.assertEqual(result['reason'], 'no_cloth_area')

    def test_refinement_recovers_a_perturbed_prior(self):
        frame, quad = bed_frame()
        # a prior 12 px out on the two long sides: the refinement pulls both back
        prior = quad + np.array([[0, -12], [0, -12], [0, 12], [0, 12]], dtype=np.float32)
        result = detect_table_refined(frame, prior=prior)
        self.assertIsNotNone(result['corners'], 'a clean synthetic bed must refine')
        self.assertTrue(result['refined'])
        self.assertLess(float(np.linalg.norm(result['corners'] - quad, axis=1).mean()), 6.0)
        self.assertGreater(result['confidence'], 0.0)
        self.assertLessEqual(result['confidence'], 1.0)

    def test_falls_back_to_the_naive_quad_when_the_prior_sees_nothing(self):
        """A prior on the wrong object must not get copied through: the naive
        quad is tried as its own search centre and reported as such."""
        frame, quad = bed_frame()
        far = np.array([[10, 10], [70, 10], [70, 50], [10, 50]], dtype=np.float32)
        result = detect_table_refined(frame, prior=far)
        self.assertIsNotNone(result['corners'])
        self.assertEqual(result['source'], 'refined_naive')
        self.assertLess(float(np.linalg.norm(result['corners'] - quad, axis=1).mean()), 8.0)

    def test_refuses_a_dark_frame_even_with_a_matching_prior(self):
        frame = np.full((360, 640, 3), 15, dtype=np.uint8)
        result = detect_table_refined(frame, prior=self.corners)
        self.assertIsNone(result['corners'])
        self.assertEqual(result['confidence'], 0.0)
        self.assertIn(result['reason'], ('low_cloth_area', 'no_boundary_evidence', 'prior_disagreement'))

    def test_one_iteration_advances_the_measured_offset_in_real_pixels(self):
        """The step size is the measurement, converted once and expressed in real
        pixels (regression: the step was divided by the mask scale, so each
        iteration advanced half of what it had just measured)."""
        from src.table_refine import _MAX_MOVE_PX
        frame, quad = bed_frame()
        offset = 10.0
        prior = quad + np.array([[0, -offset], [0, -offset], [0, offset], [0, offset]], dtype=np.float32)
        one, info = refine_quad_edges(frame, prior, iters=1)
        self.assertIsNotNone(one, f'clean bed refused: {info.get("reason")}')
        moved = abs(float(one[0][1] - prior[0][1]))
        self.assertGreater(moved, min(offset, _MAX_MOVE_PX) - 1.5,
                           f'one iteration moved only {moved:.1f} px of a {offset:.0f} px offset')
        self.assertLessEqual(moved, _MAX_MOVE_PX + 0.01, 'the cap must be the real-pixel cap')
        two, _ = refine_quad_edges(frame, prior, iters=2)
        self.assertLess(float(np.linalg.norm(np.asarray(two) - quad, axis=1).mean()), 1.5,
                        'two iterations must converge on a clean bed')

    def test_a_corner_dragged_off_the_cloth_is_either_refused_or_verified(self):
        """Corner-level damage leaves the side *lines* intact, so a good recovery is
        legitimate - but any accepted quad must account for all four sides, and any
        refusal must carry no corners."""
        frame, quad = bed_frame()
        prior = quad.copy()
        prior[0] += np.array([40, 0], dtype=np.float32)
        prior[2] += np.array([80, 0], dtype=np.float32)
        result = detect_table_refined(frame, prior=prior)
        if result['corners'] is None:
            self.assertEqual(result['confidence'], 0.0)
            self.assertIsNotNone(result['reason'])
            return
        info = result['debug_info']
        info = info if 'verified_sides' in info else (info.get('tried') or [{}])[0].get('info', {})
        self.assertEqual(info.get('verified_sides', 0) + len(info.get('inherited_sides') or []), 4)
        if info.get('inherited_sides'):
            self.assertLess(result['confidence'], 0.8)
        else:
            self.assertLess(float(np.linalg.norm(np.asarray(result['corners']) - quad, axis=1).mean()), 8.0)

    def test_side_verification_is_reported_per_side(self):
        """Every accepted quad names which sides were measured and which inherited
        the prior, and any side that is neither refuses the frame."""
        frame, quad = bed_frame()
        result = detect_table_refined(frame, prior=quad)
        self.assertIsNotNone(result['corners'])
        info = result['debug_info']
        self.assertEqual(info.get('verified_sides'), 4)
        self.assertEqual(info.get('inherited_sides'), [])
        for side in info['sides']:
            self.assertTrue(side.get('verified'))
            self.assertIsNotNone(side.get('mask_band_peak'))

    def test_occlusion_marks_the_covered_side_instead_of_failing(self):
        """A covered side has no evidence of its own and no contradiction, so it
        inherits the prior and is reported - or the frame refuses. What must not
        happen is a silent full-confidence answer."""
        frame, quad = bed_frame(occlude=[((0, 124), (639, 320))])   # bottom rail blocked
        result = detect_table_refined(frame, prior=quad)
        if result['corners'] is None:
            self.assertEqual(result['confidence'], 0.0)
            self.assertIsNotNone(result['reason'])
        else:
            info = result['debug_info']
            self.assertLess(info.get('verified_sides'), 4)
            self.assertTrue(info.get('inherited_sides'))
            self.assertLess(result['confidence'], 0.8)

    def test_prior_is_never_returned_unchecked(self):
        frame, _ = bed_frame()
        prior = np.array([[4, 4], [636, 4], [636, 356], [4, 356]], dtype=np.float32)
        quad, info = refine_quad_edges(frame, prior)
        self.assertIsNone(quad)
        self.assertEqual(info['confidence'], 0.0)
        self.assertIsNotNone(info['reason'])

    def test_priors_load_with_provenance(self):
        priors = load_priors()
        self.assertIn('vod30', priors)
        self.assertIn('highlight', priors)
        for entry in priors.values():
            if entry['quad'] is not None:
                self.assertEqual(np.asarray(entry['quad']).shape, (4, 2))
                self.assertTrue(entry['source'])

    def test_published_note_states_the_scope_of_its_entry(self):
        """The note travels as provenance, so it must name the entry it describes.

        ``prior_provenance`` publishes ``spec["note"]`` as its ``detail``, and
        ``load_priors`` publishes the same string when no segment artifact exists.
        A reader of that copy must not conclude that ``corners_30min_v2.json`` is
        dead: modules of ``src/`` still load the file today.
        """
        with tempfile.TemporaryDirectory() as root:
            published = prior_provenance('vod30', root=root)
        self.assertEqual(published['kind'], 'saved_prior')
        note = published['detail']
        self.assertEqual(note, _DATASET_PRIOR['vod30']['note'], 'the published copy is the note of the entry')
        # The note names the entry it describes.
        self.assertIn('vod30', note)
        # No part of the note names the file without naming the entry in the same part.
        # The split keeps the whole name: its dot has no space after it.
        for part in re.split(r'[.;]\s+', note):
            if CORNERS_V2_NAME in part:
                self.assertIn('vod30', part, f'the note names the file outside the scope of its entry: {part}')
        # The note scopes the exclusion.  It never calls the file unused.
        self.assertNotIn('NOT used', note)
        self.assertIsNone(
            re.search(re.escape(CORNERS_V2_NAME) + r'\s+(?:is\s+)?(?:NOT|not)\s+used', note),
            f'the note calls the file unused: {note}')
        # The scope keeps the measurement that explains it.
        self.assertIn('70 px', note)
        # The claim of the note holds in the tree: each reader resolves the file
        # through its one home.  A module that wrote the path by hand counted as
        # a reader here before, and the count said nothing about the home.
        problems = [problem for relative, name in CORNERS_V2_READERS
                    if (problem := reader_problem(relative, name))]
        self.assertEqual([], problems,
                         'a reader of the file of the note does not read its one home, '
                         + CORNERS_V2_OWNER + ': ' + '; '.join(problems))
        for relative, name in CORNERS_V2_READERS:
            if relative not in CORNERS_V2_LIVE:
                continue
            module = importlib.import_module(relative[:-3].replace('/', '.'))
            self.assertEqual(Path(str(getattr(module, name))), calib_segments.corners_v2_path(),
                             f'{relative} resolves another path than {CORNERS_V2_OWNER}')
        self.assertGreaterEqual(len(CORNERS_V2_READERS), 2,
                                'the note says that the file stays in use, and these modules read it: '
                                + ', '.join(relative for relative, _name in CORNERS_V2_READERS))

    def test_naive_detector_is_unchanged(self):
        """The other callers keep the old dict; detect_table must still work."""
        frame, _ = bed_frame()
        plain = detect_table(frame)
        self.assertEqual(set(plain), {'corners', 'mask', 'debug'})
        self.assertIsNotNone(plain['corners'])


class PriorTableTest(unittest.TestCase):
    """This module's prior table reads the one owner of the (file, key) pairs.

    ``src/calib_segments.py`` ``STATIC_REFERENCES`` owns the pair of a dataset, and
    the prior table of this module reads it.  The pair stood in both modules before
    round 67, and the two readers disagreed about a name in neither table:
    ``src/calib_segments.py`` served the highlight corners file for any unknown name
    while ``prior_for`` answered None.  These cases hold the two tables together and
    hold the answer for an unknown name.
    """

    def test_both_datasets_read_one_owner(self):
        """Each dataset takes its pair from the owner, not from a copy here."""
        from src import calib_segments as cs

        self.assertEqual(set(_DATASET_PRIOR), set(cs.STATIC_REFERENCES),
                         'the two tables hold different datasets')
        for dataset, owned in cs.STATIC_REFERENCES.items():
            with self.subTest(dataset=dataset):
                spec = prior_spec(dataset)
                self.assertEqual((spec['file'], spec['key']), (owned['file'], owned['key']))
                self.assertEqual(spec['points'], 4, 'each saved reference has four quad points')
                self.assertEqual(spec['note'], _DATASET_PRIOR[dataset]['note'],
                                 'the table and the lookup publish one note')

    def test_the_pair_stands_in_no_literal_of_this_module(self):
        """A copy of the pair here is what this round deleted."""
        from src import calib_segments as cs

        source = Path(__file__).resolve().parents[1].joinpath('src', 'table_refine.py').read_text()
        for owned in cs.STATIC_REFERENCES.values():
            with self.subTest(file=owned['file']):
                self.assertNotIn(f'"{owned["file"]}"', source)

    def test_an_unknown_dataset_has_no_prior_and_no_fallback(self):
        """An unknown name answers None here, and the other reader agrees."""
        from src import calib_segments as cs

        unknown = 'a_dataset_neither_table_names'
        self.assertIsNone(prior_spec(unknown))
        self.assertIsNone(prior_for(unknown))
        self.assertEqual(prior_provenance(unknown), {'dataset': unknown, 'kind': 'none',
                                                     'source': None})
        # The other reader answers a not-found reference for the same name, and it
        # never serves the highlight corners file.
        self.assertIsNone(cs.reference_spec(unknown))
        reference = cs.static_reference(unknown)
        self.assertFalse(reference.found)
        self.assertIsNone(reference.quad)
        self.assertNotIn('fixed_corners.json', json.dumps(reference.as_dict()))

    def test_an_unknown_dataset_with_a_root_full_of_references_still_has_none(self):
        """The fixture holds both reference files, and the unknown name takes neither."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'out').mkdir(parents=True)
            (root / 'out' / 'fixed_corners.json').write_text(json.dumps(
                {'corners': [[100, 100], [900, 100], [900, 500], [100, 500]]}))
            (root / 'out' / 'pid_anchors_vod30.json').write_text(json.dumps(
                {'anchors': {'70.0': [[10, 10], [20, 10], [20, 20], [10, 20]]}}))
            self.assertIsNone(prior_for('a_dataset_neither_table_names', root=root))
            # The control: the same root serves the two known datasets.
            self.assertIsNotNone(prior_for('highlight', root=root))
            self.assertIsNotNone(prior_for('vod30', root=root))


class RecordedReferenceTests(unittest.TestCase):
    """The vod30 improvement, pinned on the recorded artifact when present."""

    def setUp(self):
        if not (ROOT / 'out' / 'corners_30min_v2.json').is_file():
            self.skipTest('out/corners_30min_v2.json is not present')
        video = ROOT / 'data' / 'vod_30min_260815.mp4'
        if not video.is_file():
            self.skipTest('vod30 is not present')
        self.video = video

    def frame_at(self, t):
        cap = cv2.VideoCapture(str(self.video))
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            self.skipTest(f'cannot decode vod30 at t={t}')
        return frame

    def test_refinement_agrees_with_the_hand_anchors_on_a_recorded_frame(self):
        """vod30 is seeded from the six hand anchors and scored against them.

        The previous version of this test scored against ``corners_30min_v2.json``
        after seeding from that same file - a self-score.  The anchors track the
        visible cloth edge (left rail x=520 at y=330 -> x=381 at y=560); the v2 left
        rail is a vertical x=450, so agreement with the anchors is the signal.
        """
        with open(ROOT / 'out' / 'pid_anchors_vod30.json') as handle:
            anchors_raw = json.load(handle)['anchors']
        key = sorted(anchors_raw, key=float)[0]
        anchors = _order_corners(np.asarray(anchors_raw[key][:4], np.float32))
        frame = self.frame_at(70)
        naive = np.asarray(detect_table(frame)['corners'], np.float32)
        refined = detect_table_refined(frame, prior=prior_for('vod30'))
        self.assertIsNotNone(refined['corners'])
        naive_err = float(np.linalg.norm(_order_corners(naive) - anchors, axis=1).mean())
        refined_err = float(np.linalg.norm(_order_corners(refined['corners']) - anchors, axis=1).mean())
        self.assertLess(refined_err, naive_err)
        self.assertLess(refined_err, 15.0)
        info = refined['debug_info']
        self.assertEqual(info.get('verified_sides', 0) + len(info.get('inherited_sides') or []), 4)


class PlayfieldVerdictTests(unittest.TestCase):
    """The refine path reports the table's own geometry, and a check that could not run is no pass.

    The rule has one home in this module: ``best_verdict`` tries the two rotations of the polygon
    and ``unavailable_verdict`` answers a check that could not run.  This path held the opposite
    answer before: the same fault read as ``ok`` True with no reason, so a reader could not tell
    it from a measured pass.
    """

    def test_a_quad_that_ran_keeps_its_measured_answer(self):
        frame, quad = bed_frame()
        _, info = refine_quad_edges(frame, quad)
        playfield = info['playfield']
        self.assertTrue(playfield['ok'], playfield['reasons'])
        self.assertEqual(playfield['reasons'], [])
        self.assertIn('best_parallel_deg', playfield['metrics'], 'the field the stage projects')
        self.assertIn('aspect', playfield['metrics'], 'the field the stage projects')
        self.assertIsNone(info['reason'], 'a quad that passes reports no refused rule')

    def test_a_check_that_cannot_run_is_not_a_pass(self):
        """The import of the check fails: nobody measured the table, and the verdict says so."""
        frame, quad = bed_frame()
        with patch.dict(sys.modules, {'src.playfield': None}):
            _, info = refine_quad_edges(frame, quad)
        playfield = info['playfield']
        self.assertIs(playfield['ok'], False, 'ok means the check ran and accepted the quad')
        self.assertEqual(playfield['reasons'], [CHECK_UNAVAILABLE])
        self.assertEqual(playfield['metrics'], {}, 'nobody measured the table')
        self.assertIn('src.playfield', playfield['error'], 'the fault text rides beside it')
        self.assertEqual(info['reason'], 'playfield:' + CHECK_UNAVAILABLE,
                         'the refused rule and its reason reach the record the consumer reads')
