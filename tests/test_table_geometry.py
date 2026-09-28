"""src/table_geometry.py: the canonical table homography, without torch.

The server turns scan millimetres into frame pixels on the first
/api/<dataset>/events. That takes one numpy/cv2 function, which used to live in
src/pipeline.py beside `import torch`, so the first request after a start paid
for torch + SAM3 (~1 s, several seconds under load).
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
SCAN_QUAD = [[100, 100], [1100, 120], [1120, 620], [90, 600]]  # tests/test_unified_server.py's scan30 corners.json
HEAVY = "sorted(m for m in sys.modules if m == 'torch' or m.startswith('sam3'))"


def pipeline_homography(corners):
    """The pre-split src/pipeline.py maths, inline so this file never imports torch."""
    dst = np.array([[0, 0], [1270 - 1, 0], [1270 - 1, 2540 - 1], [0, 2540 - 1]], dtype=np.float32)
    return cv2.getPerspectiveTransform(corners.astype(np.float32), dst)


def production_quad():
    """The saved vod30 hand anchors, ordered as the server orders them; the same
    points as a literal when out/ is absent."""
    from src.frame_inference import anchor_quad
    try:
        quad = anchor_quad(json.loads((REPO / 'out' / 'pid_anchors_vod30.json').read_text()))
    except (OSError, ValueError):
        quad = None
    return quad if quad is not None else np.array([[532, 323], [800, 324], [997, 569], [384, 563]], np.float32)


def run_fresh(test, code):
    """Run ``code`` in a fresh interpreter at the repo root: its ``result`` plus
    the torch/SAM3 modules it left loaded."""
    env = dict(os.environ, PYTHONPATH='.')
    code = textwrap.dedent(code) + f"\nimport json, sys\nprint(json.dumps({{'result': result, 'heavy': {HEAVY}}}))\n"
    done = subprocess.run([sys.executable, '-c', code], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=600)
    test.assertEqual(done.returncode, 0, done.stderr[-3000:])
    return json.loads(done.stdout.splitlines()[-1])


class TableGeometryTests(unittest.TestCase):
    def test_homography_is_byte_identical_to_the_pipeline_maths(self):
        from src.table_geometry import CANON_H, CANON_W, homography_to_canonical
        self.assertEqual((CANON_W, CANON_H), (1270, 2540))
        quads = {'saved vod30 anchors': production_quad(),
                 'scan quad (int)': np.array(SCAN_QUAD),
                 'skewed (float64)': np.array([[37.25, 12.5], [1203.0, 88.75], [1150.5, 701.0], [-20.0, 640.25]])}
        for name, quad in quads.items():
            with self.subTest(quad=name):
                new, old = homography_to_canonical(quad), pipeline_homography(quad)
                self.assertEqual((new.dtype, new.shape), (old.dtype, old.shape))
                self.assertTrue(np.array_equal(new, old))

    def test_light_geometry_imports_never_load_torch(self):
        report = run_fresh(self, """
            import src.table_geometry
            import src.scan_events
            result = sorted(src.scan_events.POCKETS_MM)
        """)
        self.assertEqual(len(report['result']), 6)
        self.assertEqual(report['heavy'], [])

    def test_server_event_geometry_never_loads_torch(self):
        # The narrowest callables behind GET /api/<dataset>/events and /api/unified:
        # each must really project, so a swallowed import error cannot pass as light.
        report = run_fresh(self, f"""
            import tempfile
            from pathlib import Path
            from annotator.unified_server import Backend, atomic_save
            quad = {SCAN_QUAD!r}
            with tempfile.TemporaryDirectory() as tmp:
                atomic_save(Path(tmp) / 'out' / 'scan30' / 'corners.json', {{'corners': quad}})
                backend = Backend(Path(tmp))
                projection = backend._event_projection('vod30')
                result = {{'source': projection and projection[1],
                          'pocket': Backend._pocket_name({{'nearest_pocket': 'left-side (5mm)'}}),
                          'pockets': len(backend._unified_pockets(quad))}}
        """)
        self.assertEqual(report['result'], {'source': 'scan cloth quad', 'pocket': 'left-side', 'pockets': 6})
        self.assertEqual(report['heavy'], [])

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'src.pipeline imports torch')
    def test_pipeline_still_exports_the_geometry(self):
        from src.pipeline import CANON_H, CANON_W, homography_to_canonical
        self.assertEqual((CANON_W, CANON_H), (1270, 2540))
        quad = production_quad()
        self.assertTrue(np.array_equal(homography_to_canonical(quad), pipeline_homography(quad)))


if __name__ == '__main__':
    unittest.main()
