"""Selected-frame fixture tests; no servers, models, or production label writes."""
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from annotator.unified_server import APIError, Backend, ReadQuery, atomic_save, make_handler
from src.frame_inference import infer_frame


class FrameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        for name in ('vod_30min_260815.mp4', 'vod_highlight.mp4'):
            writer = cv2.VideoWriter(str(self.root / 'data' / name), cv2.VideoWriter_fourcc(*'mp4v'), 10, (64, 48))
            self.assertTrue(writer.isOpened())
            for i in range(6):
                writer.write(np.full((48, 64, 3), i * 35, dtype=np.uint8))
            writer.release()
        self.backend = Backend(self.root)

    def request(self, path, payload=None):
        handler = make_handler(self.backend)
        request = object.__new__(handler)
        request.path = path
        raw = json.dumps(payload).encode() if payload is not None else b''
        request.headers = {'Content-Length': str(len(raw))}
        request.rfile, request.wfile = io.BytesIO(raw), io.BytesIO()
        headers = {}
        request.send_response = lambda status: headers.update(status=status)
        request.send_header = lambda k, v: headers.update({k: v})
        request.end_headers = lambda: None
        request.dispatch(post=payload is not None)
        return headers, request.wfile.getvalue()

    def test_video_frame_metadata_and_jpeg(self):
        meta = self.backend.get(['api', 'video'], ReadQuery({'dataset': 'vod30'}))
        self.assertEqual((meta['fps'], meta['frame_count'], meta['width'], meta['height']), (10, 6, 64, 48))
        self.assertEqual(meta['duration'], .6)
        image, frame = self.backend.decode_frame('vod30', 4)
        self.assertAlmostEqual(image.mean(), 140, delta=5)
        self.assertEqual(frame['timestamp_seconds'], .4)
        headers, raw = self.request('/api/frame?dataset=vod30&frame=4')
        self.assertEqual(headers['status'], 200)
        self.assertEqual(headers['X-Timestamp-Kind'], 'nominal_cfr')
        self.assertEqual(headers['X-Frame-Index'], '4')
        self.assertTrue(raw.startswith(b'\xff\xd8'))

    def test_allowlist_and_frame_bounds(self):
        for dataset, frame in [('..', 0), ('vod30', -1), ('vod30', 6), ('vod30', 1.5), ('vod30', True), ('vod30', 'NaN'), ('vod30', '../a')]:
            with self.subTest(dataset=dataset, frame=frame), self.assertRaises(APIError):
                self.backend.frame_result(dataset, frame)

    def test_manual_separate_persistence(self):
        inferred = {'boxes': [], 'source': 'inferred'}
        atomic_save(self.backend.frame_path('vod30', 2, 'inference'), inferred)
        payload = dict(dataset='vod30', frame_index=2, boxes=[dict(label='cue', bbox=[1, 2, 10, 20])], table_polygon=[[0, 0], [60, 0], [60, 40], [0, 40]])
        headers, raw = self.request('/api/frame-correction', payload)
        self.assertEqual(headers['status'], 200)
        fresh = Backend(self.root).frame_result('vod30', 2)
        # A file an earlier run wrote is still readable evidence, and the read says
        # so: stored_inference marks it as not this session's result.
        self.assertEqual(fresh['inference'], {**inferred, 'stored_inference': True})
        self.assertEqual(fresh['correction']['boxes'][0]['center'], [5.5, 11])
        self.assertIsNone(self.backend.frame_result('highlight', 2)['correction'])
        self.assertEqual(list(self.root.rglob('.*.json')), [])

    def test_invalid_corrections(self):
        invalid = [dict(boxes=[dict(label='admin', bbox=[0, 0, 1, 1])]),
                   dict(boxes=[dict(label='ball', bbox=[0, 0, 65, 20])]),
                   dict(boxes=[dict(label='ball', bbox=[10, 0, 1, 20])]),
                   dict(boxes=[dict(label='ball', bbox=[0, 0, float('nan'), 20])]),
                   dict(table_polygon=[[0, 0]] * 4), dict(boxes=[{}] * 201)]
        for update in invalid:
            with self.subTest(update=update), self.assertRaises(APIError):
                self.backend.save_frame_correction(dict(dataset='vod30', frame_index=0, **update))
        self.assertFalse((self.root / 'out').exists())

    def test_async_bounded_failure_and_result(self):
        entered, release = threading.Event(), threading.Event()
        original_thread = threading.Thread
        threads = []
        def thread_factory(*args, **kwargs):
            thread = original_thread(*args, **kwargs)
            threads.append(thread)
            return thread
        def inference(frame, detectors, root, progress, dataset=None):
            progress('fixture detecting')
            entered.set()
            release.wait(5)
            return dict(boxes=[], table_polygon=None, events_supported=False)
        with patch('src.frame_inference.infer_frame', side_effect=inference), patch('annotator.unified_server.threading.Thread', side_effect=thread_factory):
            headers, raw = self.request('/api/inference', dict(dataset='vod30', frame_index=2))
            self.assertEqual(headers['status'], 202)
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.backend.inference_status('vod30')['stage'], 'fixture detecting')
            with self.assertRaises(APIError) as error:
                self.backend.start_inference(dict(dataset='highlight', frame_index=0))
            self.assertEqual(error.exception.status, 409)
            release.set()
            threads[-1].join(5)
        self.assertEqual(self.backend.inference_status('vod30')['status'], 'completed')
        # On-the-spot inference stores nothing: the result is in the job and in the
        # page that asked for it, and a fresh read of that frame finds no inference.
        self.assertEqual(self.backend.inference_status('vod30')['result']['source'], 'inferred')
        self.assertIsNone(Backend(self.root).frame_result('vod30', 2)['inference'])
        self.assertFalse(self.backend.frame_path('vod30', 2, 'inference').exists())
        with patch('src.frame_inference.infer_frame', side_effect=RuntimeError('fixture missing model')), patch('annotator.unified_server.threading.Thread', side_effect=thread_factory):
            self.backend.start_inference(dict(dataset='vod30', frame_index=3, detectors=['balls']))
            threads[-1].join(5)
        self.assertEqual(self.backend.inference_status('vod30')['error'], 'fixture missing model')
        self.assertFalse(self.backend.inference_busy)
        self.assertIsNone(self.backend.frame_result('vod30', 3)['inference'])

    def test_balls_reuses_actual_pipeline_contract(self):
        import torch
        from src.table_detect import detect_table
        frame = np.full((120, 160, 3), (200, 110, 20), dtype=np.uint8)
        cv2.circle(frame, (80, 60), 8, (255, 255, 255), -1)
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.circle(mask, (80, 60), 8, 1, -1)
        state = dict(masks=torch.tensor(mask[None, None].astype(bool)),
                     boxes=torch.tensor([[72, 52, 88, 68]]), scores=torch.tensor([.95]))
        self.assertIn('mask', detect_table(frame))
        class Processor:
            def set_image(self, image):
                return state
            def set_text_prompt(self, prompt, state):
                return state
        (self.root / 'data' / 'sam3.safetensors').write_bytes(b'fixture')
        with patch('src.sam3_cpu.load_sam3_image_model', return_value=object()), patch('src.sam3_cpu.make_processor', return_value=Processor()):
            result = infer_frame(frame, ['balls'], self.root)
        self.assertEqual(len(result['boxes']), 1)
        ball = result['boxes'][0]
        self.assertEqual(ball['label'], 'ball')
        self.assertEqual(ball['style'], 'cue')
        self.assertEqual(ball['color'], 'white')
        self.assertEqual(ball['center'], [80, 60])

    def test_person_model_reused_and_invalidated(self):
        from unittest.mock import MagicMock
        weights = self.root / 'yolov8n.pt'
        weights.write_bytes(b'fixture')
        model = MagicMock()
        result = model.predict.return_value[0]
        result.boxes.xyxy.cpu.return_value.tolist.return_value = [[1, 2, 3, 4]]
        result.boxes.conf.cpu.return_value.tolist.return_value = [0.9]
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        with patch('ultralytics.YOLO', return_value=model) as loader, \
                patch('src.frame_inference._person_model', None), \
                patch('src.frame_inference._person_weights', None):
            first = infer_frame(frame, ['person'], self.root)
            self.assertEqual(first, infer_frame(frame, ['person'], self.root))
            self.assertEqual(loader.call_count, 1)
            weights.write_bytes(b'changed checkpoint')
            infer_frame(frame, ['person'], self.root)
            self.assertEqual(loader.call_count, 2)
            weights.unlink()
            with self.assertRaisesRegex(RuntimeError, 'missing'):
                infer_frame(frame, ['person'], self.root)
        self.assertEqual(first['boxes'][0]['center'], [2, 3])

    def test_table_only_without_model_and_detector_validation(self):
        result = infer_frame(np.zeros((48, 64, 3), dtype=np.uint8), ['table'], self.root)
        self.assertIsNone(result['table_polygon'])
        self.assertFalse(result['events_supported'])
        for detectors in [[], ['invalid'], ['table', 'table'], 'balls', [{}]]:
            with self.assertRaises(APIError):
                self.backend.start_inference(dict(dataset='vod30', frame_index=0, detectors=detectors))
        with self.assertRaisesRegex(RuntimeError, 'downloads are disabled'):
            infer_frame(np.zeros((48, 64, 3), dtype=np.uint8), ['person'], self.root)


if __name__ == '__main__':
    unittest.main()
