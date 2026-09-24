"""Person pipeline tests; everything injected, no model loads."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.person_identity import IdentityIndex  # noqa: E402
from src.person_pipeline import PersonPipeline  # noqa: E402

ORTH_A = np.zeros(128, np.float32); ORTH_A[0] = 1.0
ORTH_B = np.zeros(128, np.float32); ORTH_B[1] = 1.0
PLAYER_EMB = np.zeros(128, np.float32); PLAYER_EMB[3] = 1.0


def face(bbox, eye=12.0, det=0.9, emb=PLAYER_EMB):
    return {'bbox': list(bbox), 'eye_px': eye, 'det_score': det, 'embedding': np.asarray(emb, np.float32)}


class FakeDetector:
    def __init__(self, per_call):
        self.per_call = list(per_call)

    def __call__(self, frame):
        return [{'bbox': list(b), 'conf': 0.9} for b in self.per_call.pop(0)]


class FakeEncoder:
    def __init__(self, per_call):
        self.per_call = list(per_call)

    def __call__(self, crops):
        return [np.asarray(v, np.float32) for v in self.per_call.pop(0)]


class FakeEngine:
    def __init__(self, faces_per_call=None, match=None):
        self.per_call = list(faces_per_call) if faces_per_call is not None else None
        self.match = match

    def analyze(self, frame):
        if not self.per_call:
            return []
        return self.per_call.pop(0)

    def quality(self, f):
        return f.get('eye_px', 0) >= 8.0 and f.get('det_score', 0) >= 0.4

    def best_match(self, emb, gallery):
        return self.match


class CountingEngine(FakeEngine):
    """FakeEngine that counts analyze() calls for face-cache/stride tests."""

    def __init__(self, faces_per_call=None, match=None):
        super().__init__(faces_per_call, match)
        self.analyze_calls = 0

    def analyze(self, frame):
        self.analyze_calls += 1
        return super().analyze(frame)


def make(tmp, boxes, vecs, faces=None, match=None):
    return PersonPipeline(Path(tmp),
                          detector=FakeDetector(boxes),
                          body_encoder=FakeEncoder(vecs),
                          face_engine=FakeEngine(faces, match),
                          identity=IdentityIndex(Path(tmp) / 'clusters.json'))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.frame = np.zeros((720, 1280, 3), np.uint8)
        self.box = [10, 10, 210, 610]
        self.other = [600, 10, 900, 610]
        self.p1 = [40, 200, 100, 300]  # inside self.box

    def test_two_persons_two_clusters(self):
        p = make(self.tmp.name, [[self.box, self.other]], [[ORTH_A, ORTH_B]], [[]])
        out = p.process_frame(self.frame, frame_index=0)
        self.assertEqual(len(out['persons']), 2)
        self.assertEqual(len({x['cluster_id'] for x in out['persons']}), 2)
        self.assertEqual(out['events'], [])

    def test_same_track_next_frame(self):
        p = make(self.tmp.name, [[self.box], [self.box]], [[ORTH_A], [ORTH_A]], [[]])
        out1 = p.process_frame(self.frame, frame_index=0)
        out2 = p.process_frame(self.frame, frame_index=1)
        self.assertEqual(out1['persons'][0]['track_id'], out2['persons'][0]['track_id'])

    def test_cross_exit_same_cluster(self):
        boxes = [[self.box]] + [[] for _ in range(3)] + [[self.box]]
        vecs = [[ORTH_A], [ORTH_A]]
        p = make(self.tmp.name, boxes, vecs, [[]])
        c1 = p.process_frame(self.frame, frame_index=0)['persons'][0]['cluster_id']
        for i in range(1, 4):
            p.process_frame(self.frame, frame_index=i)
        c2 = p.process_frame(self.frame, frame_index=40)['persons'][0]['cluster_id']
        self.assertEqual(c1, c2)

    def test_face_binds_once(self):
        faces = [[face(self.p1)], [face([2000, 2000, 2050, 2050])]]
        match = {'player_id': 'p1', 'similarity': 0.9, 'margin': 0.5}
        p = make(self.tmp.name, [[self.box], [self.box]], [[ORTH_A], [ORTH_A]], faces, match)
        out1 = p.process_frame(self.frame, frame_index=0)
        self.assertEqual(out1['events'][0]['kind'], 'bind')
        self.assertEqual(out1['persons'][0]['player_id'], 'p1')
        out2 = p.process_frame(self.frame, frame_index=1)
        self.assertEqual(out2['events'], [])
        self.assertEqual(out2['persons'][0]['player_id'], 'p1')

    def test_face_outside_persons_no_bind(self):
        faces = [[face([2000, 2000, 2050, 2050])]]
        match = {'player_id': 'p1', 'similarity': 0.9, 'margin': 0.5}
        p = make(self.tmp.name, [[self.box]], [[ORTH_A]], faces, match)
        out = p.process_frame(self.frame, frame_index=0)
        self.assertEqual(out['events'], [])
        self.assertIsNone(out['persons'][0]['player_id'])

    def test_unknown_face_stays_unbound(self):
        p = make(self.tmp.name, [[self.box]], [[ORTH_A]], [[face(self.p1)]], None)
        out = p.process_frame(self.frame, frame_index=0)
        self.assertIsNone(out['persons'][0]['player_id'])
        self.assertEqual(out['events'], [])

    def test_enroll_filters_quality(self):
        with mock.patch('torch.load', side_effect=AssertionError('no model')):
            p = make(self.tmp.name, [[self.box]], [[ORTH_A]],
                     [[face(self.p1), face(self.p1, eye=4.0)]], None)
            kept = p.enroll_face('p1', self.frame)
        self.assertEqual(kept, 1)
        self.assertEqual(len(p._gallery_data()['p1']), 1)

    def test_seed_overrides_binding(self):
        p = make(self.tmp.name, [[self.box]], [[ORTH_A]], [[]], None)
        out = p.process_frame(self.frame, frame_index=0)
        cluster = out['persons'][0]['cluster_id']
        self.assertTrue(p.explicit_seed(cluster, 'p2', 'seed'))
        boxes = [[self.box]]
        vecs = [[ORTH_A]]
        faces = [[face(self.p1)]]
        match = {'player_id': 'p1', 'similarity': 0.9, 'margin': 0.5}
        p = PersonPipeline(Path(self.tmp.name), detector=FakeDetector(boxes),
                           body_encoder=FakeEncoder(vecs), face_engine=FakeEngine(faces, match),
                           identity=p.identity)
        out2 = p.process_frame(self.frame, frame_index=5)
        self.assertEqual(out2['persons'][0]['player_id'], 'p2')
        self.assertEqual(out2['events'], [])

    def test_result_contract(self):
        p = make(self.tmp.name, [[self.box]], [[ORTH_A]], [[]])
        out = p.process_frame(self.frame, frame_index=0)
        self.assertEqual(set(out), {'persons', 'events'})
        self.assertEqual(set(out['persons'][0]),
                         {'track_id', 'bbox', 'cluster_id', 'player_id', 'face_sim', 'bound_evidence'})


class FaceCacheStrideTests(unittest.TestCase):
    """Face-stage latency controls: signature cache + face_stride subsampling."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.frame = np.zeros((720, 1280, 3), np.uint8)
        self.box = [10, 10, 210, 610]
        self.other = [600, 10, 900, 610]
        self.p1 = [40, 200, 100, 300]  # inside self.box
        self.p2 = [700, 200, 760, 300]  # inside self.other

    def run_frames(self, boxes, vecs, engine, stride=4):
        p = PersonPipeline(Path(self.tmp.name), detector=FakeDetector(boxes),
                           body_encoder=FakeEncoder(vecs), face_engine=engine,
                           identity=IdentityIndex(Path(self.tmp.name) / 'clusters.json'),
                           face_stride=stride)
        outs = [p.process_frame(self.frame, frame_index=i) for i in range(len(boxes))]
        return p, outs

    def test_signature_cache_skips_repeated_analyze(self):
        eng = CountingEngine([[face(self.p1)]],
                             {'player_id': 'p1', 'similarity': 0.9, 'margin': 0.5})
        p, outs = self.run_frames([[self.box], [self.box], [self.box]], [[ORTH_A]] * 3, eng)
        self.assertEqual(eng.analyze_calls, 1)  # same boxes -> cache hits
        self.assertEqual(outs[0]['events'][0]['kind'], 'bind')
        self.assertEqual(outs[2]['persons'][0]['player_id'], 'p1')
        self.assertEqual(outs[2]['events'], [])

    def test_cached_face_still_binds_on_cache_hit(self):
        eng = CountingEngine([[face(self.p1)]], None)
        p, _ = self.run_frames([[self.box], [self.box], [self.box]],
                               [[ORTH_A]] * 4, eng)
        self.assertEqual(eng.analyze_calls, 1)
        eng.match = {'player_id': 'p1', 'similarity': 0.9, 'margin': 0.5}
        p.detector = FakeDetector([[self.box]])
        out2 = p.process_frame(self.frame, frame_index=3)  # cache hit, face reused
        self.assertEqual(eng.analyze_calls, 1)
        self.assertEqual(out2['events'][0]['kind'], 'bind')
        self.assertEqual(out2['persons'][0]['player_id'], 'p1')

    def test_box_change_reanalyzes(self):
        eng = CountingEngine([[face(self.p1)], [face(self.p2)]], None)
        self.run_frames([[self.box], [self.other]], [[ORTH_A]] * 2, eng, stride=1)
        self.assertEqual(eng.analyze_calls, 2)  # signature changed -> miss

    def test_face_stride_limits_analysis_rate(self):
        eng = CountingEngine([[face(self.p1)], [face(self.p2)]], None)
        boxes = [[self.box], [self.other], [self.box], [self.other],
                 [self.box], [self.other], [self.box], [self.other]]
        p, outs = self.run_frames(boxes, [[ORTH_A]] * 8, eng)
        self.assertEqual(eng.analyze_calls, 2)  # stride frames 0 and 4 only
        self.assertEqual([len(o['persons']) for o in outs], [1] * 8)  # tracking unaffected

    def test_stride_one_analyzes_every_changed_frame(self):
        eng = CountingEngine([[face(self.p1)], [face(self.p2)], [face(self.p1)]], None)
        self.run_frames([[self.box], [self.other], [self.box]], [[ORTH_A]] * 3, eng, stride=1)
        self.assertEqual(eng.analyze_calls, 3)

    def test_no_detections_skip_analysis(self):
        eng = CountingEngine([[]], None)
        p, outs = self.run_frames([[], []], [[]] * 2, eng)
        self.assertEqual(eng.analyze_calls, 0)
        self.assertEqual(outs[1]['persons'], [])


class DetectorWeightsTest(unittest.TestCase):
    """The person detector must never fetch weights: ultralytics answers a
    missing weights path by downloading the release asset from GitHub, which
    would turn any root that forgot the file into a network dependency (the
    unified-view fixture hit exactly that). These tests prove the no-download
    behaviour by construction: every path that could try is patched to fail
    loudly, and the missing-weights case must raise before any loader runs.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _no_network(self):
        """Any ultralytics download raises; YOLO construction is recorded."""
        import ultralytics.utils.downloads as downloads
        loader = mock.Mock()
        patchers = [
            mock.patch.object(downloads, 'download',
                              side_effect=AssertionError('network download attempted')),
            mock.patch.object(downloads, 'safe_download',
                              side_effect=AssertionError('network download attempted')),
            mock.patch('ultralytics.YOLO', loader),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        return loader

    def test_missing_weights_raise_instead_of_downloading(self):
        loader = self._no_network()
        with mock.patch('src.person_pipeline.REPO', self.root):  # no repo fallback either
            with self.assertRaises(RuntimeError) as ctx:
                PersonPipeline(self.root)._get_detector()
        message = str(ctx.exception)
        self.assertIn('yolov8n.pt', message, 'the error names the expected file')
        self.assertIn(str(self.root / 'yolov8n.pt'), message)
        self.assertIn('downloads are disabled', message)
        self.assertFalse(loader.called, 'no loader (and so no download) may run')

    def test_root_local_weights_are_preferred(self):
        loader = self._no_network()
        (self.root / 'yolov8n.pt').write_bytes(b'not really a checkpoint')
        PersonPipeline(self.root)._get_detector()
        self.assertEqual(loader.call_args.args[0], str(self.root / 'yolov8n.pt'))

    def test_repo_weights_are_the_fallback(self):
        loader = self._no_network()
        PersonPipeline(self.root)._get_detector()
        from src.person_pipeline import REPO
        self.assertEqual(loader.call_args.args[0], str(REPO / 'yolov8n.pt'))
        self.assertTrue((REPO / 'yolov8n.pt').is_file(), 'the fallback exists in this repo')

    def test_weights_helper_is_the_only_source(self):
        loader = self._no_network()
        (self.root / 'yolov8n.pt').write_bytes(b'x')
        pipeline = PersonPipeline(self.root)
        self.assertEqual(pipeline.detector_weights(), self.root / 'yolov8n.pt')
        with mock.patch('src.person_pipeline.REPO', self.root / 'nowhere'):
            with self.assertRaises(RuntimeError):
                PersonPipeline(self.root / 'empty').detector_weights()
        self.assertFalse(loader.called)


if __name__ == '__main__':
    unittest.main()
