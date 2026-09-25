"""The frozen-frame inference job must name its dataset (and its seed review).

``annotator/unified_server.start_inference`` used to call ``infer_frame`` without
``dataset=``, so the polygon it saved - and ``app.js`` paints it - came from the
naive detector (131 px from the saved anchors at t=427.8 on vod30) while every other
surface showed the refined quad.  See docs/app-path-refusal.md.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from annotator.unified_server import Backend

ANCHORS = [[532.0, 323.0], [800.0, 324.0], [997.0, 569.0], [384.0, 563.0],
           [700.0, 200.0], [560.0, 500.0]]

class InferencePathTests(unittest.TestCase):
    """The frozen-frame polygon app.js paints must come from the same refinement."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'out').mkdir()
        (self.root / 'out' / 'pid_anchors_vod30.json').write_text(
            json.dumps({'anchors': {'70.0': ANCHORS}}))
        self.backend = Backend(self.root)

    def test_start_inference_names_its_dataset_for_the_table_detector(self):
        seen = {}
        polygon = [[100.0, 80.0], [540.0, 76.0], [540.0, 280.0], [100.0, 284.0]]
        meta = {"dataset": "vod30", "frame_index": 2, "timestamp_seconds": 0.1,
                "timestamp_kind": "nominal_cfr", "width": 1280, "height": 720}

        def fake(frame, detectors, root, progress, dataset=None):
            seen['dataset'] = dataset
            return dict(boxes=[], table_polygon=polygon, events_supported=False)

        with patch.object(Backend, 'frame_metadata', lambda self, d, i: dict(meta)), \
                patch.object(Backend, 'decode_frame',
                             lambda self, d, i: (np.zeros((720, 1280, 3), np.uint8), dict(meta))), \
                patch('src.frame_inference.infer_frame', side_effect=fake):
            self.backend.start_inference(dict(dataset='vod30', frame_index=2))
            for _ in range(250):
                if self.backend.inference_status('vod30')['status'] == 'completed':
                    break
                time.sleep(0.02)
            saved = self.backend.inference_status('vod30')['result']
        self.assertEqual(self.backend.inference_status('vod30')['status'], 'completed')
        # The result is in the response, not on disk: no file for this frame.
        self.assertFalse(self.backend.frame_path('vod30', 2, 'inference').exists(),
                         'on-the-spot inference writes nothing')
        self.assertEqual(seen['dataset'], 'vod30',
                         'without dataset= the saved polygon is the naive detector quad')
        self.assertEqual(saved['table_polygon'], polygon)
        self.assertEqual(saved['source'], 'inferred')
