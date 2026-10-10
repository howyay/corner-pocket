"""Coarse scan geometry and downstream consumers; no model or VOD scan."""
import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import torch

from src import scan_events


class ScanEventsTests(unittest.TestCase):
    corners = np.array([[120, 60], [840, 60], [840, 480], [120, 480]], dtype=np.float32)
    center = np.array([300, 165], dtype=np.float32)

    def scan_fixture(self, width, height):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        cap = MagicMock()
        cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 30.0, cv2.CAP_PROP_FRAME_COUNT: 30.0,
        }[prop]
        cap.read.return_value = (True, frame)
        with patch.object(scan_events.cv2, 'VideoCapture', return_value=cap), \
             patch.object(scan_events, 'detect_table', return_value={
                 'corners': self.corners, 'mask': np.ones((540, 960), dtype=np.uint8),
             }) as table, \
             patch.object(scan_events, 'detect_ball_candidates', return_value=[{
                 'cx': float(self.center[0]), 'cy': float(self.center[1]),
             }]):
            records, corners = scan_events.classical_scan('fixture.mp4', 1.0)
        self.assertEqual(table.call_args.args[0].shape, (540, 960, 3))
        cap.release.assert_called_once()
        return records, corners

    def test_original_pixel_coordinates_and_canonical_projection(self):
        for width, height in ((1280, 720), (1920, 1080), (1280, 800)):
            with self.subTest(resolution=(width, height)):
                records, corners = self.scan_fixture(width, height)
                scale = np.array([width / 960, height / 540])
                np.testing.assert_allclose(corners, self.corners * scale)
                np.testing.assert_allclose(records[0]['cands'][0],
                                           np.round(self.center * scale, 1))
                H = scan_events.homography_to_canonical(corners)
                point = H @ np.r_[self.center * scale, 1.0]
                np.testing.assert_allclose(point[:2] / point[2],
                                           [(scan_events.CANON_W - 1) / 4, (scan_events.CANON_H - 1) / 4],
                                           atol=1e-3)
                self.assertEqual(records[0]['motion'], 0.0)

    def test_main_persists_source_pixel_homography(self):
        for width, height in ((1280, 720), (1920, 1080)):
            with self.subTest(resolution=(width, height)), tempfile.TemporaryDirectory() as tmp:
                records, corners = self.scan_fixture(width, height)
                with patch.object(scan_events, 'classical_scan', return_value=(records, corners)), \
                     patch('sys.argv', ['scan_events.py', '--out', tmp]):
                    scan_events.main()
                saved = json.loads((Path(tmp) / 'corners.json').read_text())
                np.testing.assert_allclose(saved['corners'], corners)
                H = scan_events.homography_to_canonical(np.array(saved['corners']))
                pixels = np.c_[corners, np.ones(4)]
                projected = (H @ pixels.T).T
                np.testing.assert_allclose(projected[:, :2] / projected[:, 2:],
                                           [[0, 0], [scan_events.CANON_W - 1, 0],
                                            [scan_events.CANON_W - 1, scan_events.CANON_H - 1],
                                            [0, scan_events.CANON_H - 1]], atol=1e-3)

    def test_sam_confirmation_projects_full_resolution_centers(self):
        for width, height in ((1280, 720), (1920, 1080)):
            with self.subTest(resolution=(width, height)), tempfile.TemporaryDirectory() as tmp:
                _, corners = self.scan_fixture(width, height)
                out = Path(tmp)
                (out / 'corners.json').write_text(json.dumps({'corners': corners.tolist()}))
                center = self.center * [width / 960, height / 540]
                cap = MagicMock()
                cap.read.return_value = (True, np.zeros((height, width, 3), dtype=np.uint8))
                proc = MagicMock()
                proc.set_text_prompt.return_value = {
                    'masks': torch.ones((1, 1, 10, 10)), 'scores': torch.tensor([0.9]),
                }
                with patch.object(scan_events.cv2, 'VideoCapture', return_value=cap), \
                     patch('sam3_cpu.load_sam3_image_model'), \
                     patch('sam3_cpu.make_processor', return_value=proc), \
                     patch('torch.set_num_threads'), \
                     patch('pipeline.detect_table', return_value={
                         'mask': np.ones((height, width), dtype=np.uint8),
                     }), \
                     patch('pipeline.ball_center', return_value=(*center, 8.0)):
                    results = scan_events.sam3_confirm('fixture.mp4', [0.0], out)
                self.assertEqual(len(results[0.0]), 1)
                np.testing.assert_allclose(results[0.0][0]['img'], np.round(center, 1))
                np.testing.assert_allclose(results[0.0][0]['table_mm'],
                                           [(scan_events.CANON_W - 1) / 4, (scan_events.CANON_H - 1) / 4], atol=0.1)
                cap.release.assert_called_once()

    def test_cli_default_matches_available_vod(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(scan_events, 'classical_scan', return_value=([], None)) as scan, \
             patch('sys.argv', ['scan_events.py', '--out', tmp]):
            scan_events.main()
        scan.assert_called_once_with('data/vod_30min_260815.mp4', 1.0)

    def shot_pair(self, move_mm, gap_s=1.0):
        """Two SAM3 samples, one ball, `move_mm` apart along the table x axis."""
        return {0.0: [{'table_mm': [400.0, 400.0]}],
                gap_s: [{'table_mm': [400.0 + move_mm, 400.0]}]}

    def test_shot_refinement_reads_its_displacement_floor(self):
        sam3 = self.shot_pair(200.0)
        low = scan_events.shot_refinement(sam3, shot_disp=150.0)
        high = scan_events.shot_refinement(sam3, shot_disp=300.0)
        self.assertEqual(len(low), 1, 'a 200 mm move is a shot at a 150 mm floor')
        self.assertEqual(high, [], 'and no shot at a 300 mm floor')
        self.assertEqual(low[0]['disp_mm'], 200)
        self.assertEqual(low[0]['t'], 0.5)
        self.assertAlmostEqual(low[0]['speed_m_s'], 0.2, places=6)

    def test_the_default_floor_is_the_module_constant(self):
        self.assertEqual(scan_events.SHOT_DISP_MM, 300.0)
        self.assertEqual(scan_events.shot_refinement(self.shot_pair(200.0)), [],
                         'the default floor refuses a 200 mm move')
        self.assertEqual(len(scan_events.shot_refinement(self.shot_pair(350.0))), 1,
                         'and accepts a 350 mm move')

    def test_no_function_advertises_a_parameter_it_never_reads(self):
        """A threshold nothing reads is a knob that does nothing."""
        source = Path(scan_events.__file__)
        offenders = []
        for node in ast.walk(ast.parse(source.read_text())):
            if not isinstance(node, ast.FunctionDef):
                continue
            read = {name.id for name in ast.walk(node) if isinstance(name, ast.Name)}
            for arg in node.args.args:
                if arg.arg not in read:
                    offenders.append(f'{source.name}:{arg.lineno} {node.name}({arg.arg})')
        self.assertEqual(offenders, [])

    def test_main_routes_the_shot_floor_through_one_function(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, corners = self.scan_fixture(1280, 720)
            with patch.object(scan_events, 'classical_scan', return_value=(records, corners)), \
                 patch.object(scan_events, 'shot_refinement', return_value=[]) as refine, \
                 patch('sys.argv', ['scan_events.py', '--out', tmp]):
                scan_events.main()
        refine.assert_called_once()
        self.assertEqual(len(refine.call_args.args), 1, 'the floor stays inside the function')
        self.assertEqual(refine.call_args.kwargs, {})


if __name__ == '__main__':
    unittest.main()
