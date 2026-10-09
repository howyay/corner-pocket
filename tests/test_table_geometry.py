"""src/table_geometry.py: the canonical table homography, without torch.

The server turns scan millimetres into frame pixels on the first
/api/<dataset>/events. That takes one numpy/cv2 function, which used to live in
src/pipeline.py beside `import torch`, so the first request after a start paid
for torch + SAM3 (~1 s, several seconds under load).

The same module is also the single definition site of the canonical frame
(CANON_W, CANON_H) and of the pocket table (POCKETS_MM). OneCanonicalFrameTests
fails when a second, disagreeing copy of either comes back.
"""
import ast
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
POCKET_NAMES = {'head-left', 'head-right', 'foot-left', 'foot-right', 'left-side', 'right-side'}


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

    def test_split_segment_projection_never_loads_torch(self):
        # A measured camera move sends each event through its own segment's quad
        # (Segments.homographies). Synthetic artifact, only the fields
        # src/calib_segments.py reads: segmentation_verdict, segments[].id/t_start/
        # t_end/quad_px/source.
        quads = {'A': SCAN_QUAD, 'B': [[300, 150], [1000, 160], [1060, 560], [250, 550]]}
        report = run_fresh(self, f"""
            import tempfile
            from pathlib import Path
            from annotator.unified_server import Backend, atomic_save
            quads = {quads!r}
            with tempfile.TemporaryDirectory() as tmp:
                atomic_save(Path(tmp) / 'out' / 'calib_vod30_segments.json', {{
                    'segmentation_verdict': 'split_supported',
                    'segments': [{{'id': 'A', 't_start': 0, 't_end': 100, 'quad_px': quads['A'], 'source': 'human_anchors'}},
                                 {{'id': 'B', 't_start': 101, 't_end': 200, 'quad_px': quads['B'], 'source': 'refined'}}]}})
                events = [{{'id': 1, 't': 50, 'type': 'pot', 'last_mm': [635, 1270]}},
                          {{'id': 2, 't': 150, 'type': 'pot', 'last_mm': [635, 1270]}}]
                items, _ = Backend(Path(tmp))._event_geometry('vod30', events)
                result = [[item.get('px_segment'), item.get('px_source'), item.get('last_px')] for item in items]
        """)
        expected = []
        for name, source in (('A', 'human anchors'), ('B', 'refined')):
            x, y, w = np.linalg.inv(pipeline_homography(np.array(quads[name]))) @ [635.0, 1270.0, 1.0]
            expected.append([name, f'segment {name} · {source}', [round(x / w, 1), round(y / w, 1)]])
        self.assertEqual(report['result'], expected)
        self.assertEqual(report['heavy'], [])

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'src.pipeline imports torch')
    def test_pipeline_still_exports_the_geometry(self):
        from src.pipeline import CANON_H, CANON_W, homography_to_canonical
        self.assertEqual((CANON_W, CANON_H), (1270, 2540))
        quad = production_quad()
        self.assertTrue(np.array_equal(homography_to_canonical(quad), pipeline_homography(quad)))


class OneCanonicalFrameTests(unittest.TestCase):
    """One frame, one pocket table: the importers share it and no module restates it."""

    @staticmethod
    def src_modules():
        return sorted(p for p in (REPO / 'src').glob('*.py') if p.name != 'table_geometry.py')

    def test_no_module_restates_the_canonical_frame(self):
        restated = {}
        for path in self.src_modules():
            names = set()
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                else:
                    continue
                names.update(t.id for t in targets if isinstance(t, ast.Name))
            hits = names & {'CANON_W', 'CANON_H', 'POCKETS_MM'}
            if hits:
                restated[path.name] = sorted(hits)
        self.assertEqual(restated, {})

    def test_no_module_holds_a_second_pocket_table(self):
        # A millimetre table is a dict literal keyed by >= 4 pocket names whose
        # values are 2-element coordinates. The exemptions are real tables of
        # another kind: src/shot_pot_gate.py VOD30_POCKETS_PX holds px /
        # px_per_mm dicts (tests/test_shot_pot_gate.py re-derives them), and
        # src/dense_queue.py POCKET_WORDS holds displayed words.
        found = {}
        for path in self.src_modules():
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Dict) or len(node.keys) < 4:
                    continue
                keys = {k.value for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                if len(keys & POCKET_NAMES) < 4:
                    continue
                pairs = [v for v in node.values
                         if isinstance(v, (ast.Tuple, ast.List)) and len(v.elts) == 2]
                if len(pairs) < 4:
                    continue
                found.setdefault(path.name, []).append(node.lineno)
        self.assertEqual(found, {})

    def test_the_importers_share_the_one_table_object(self):
        from src import event_gates, rebuild_events_v2, scan_events, shot_pot_gate, table_geometry
        for module in (event_gates, scan_events, shot_pot_gate):
            with self.subTest(module=module.__name__):
                self.assertIs(module.POCKETS_MM, table_geometry.POCKETS_MM)
                self.assertEqual((module.CANON_W, module.CANON_H),
                                 (table_geometry.CANON_W, table_geometry.CANON_H))
        # The three modules that resolve a millimetre pair to a pocket share the
        # one rule as well. src/shot_pot_gate.py has its own PocketModel.
        for module in (event_gates, scan_events, rebuild_events_v2):
            with self.subTest(module=module.__name__, name='nearest_pocket'):
                self.assertIs(module.nearest_pocket, table_geometry.nearest_pocket)
        # The rebuild wrote its own transposed destination before this; it now
        # takes the canonical homography and the canonical distances, so it needs
        # no frame constant of its own.
        self.assertIs(rebuild_events_v2.homography_to_canonical,
                      table_geometry.homography_to_canonical)
        self.assertNotIn('getPerspectiveTransform', (REPO / 'src' / 'rebuild_events_v2.py').read_text())

    def test_the_pocket_table_is_portrait_not_landscape(self):
        from src.table_geometry import nearest_pocket
        # (1150, 300) is 120 mm from head-right when x is the 1270 mm width. A
        # landscape table (x = 2540, y = 1270) answers head-left for that pair.
        self.assertEqual(nearest_pocket(1150.0, 300.0)[0], 'head-right')
        self.assertEqual(nearest_pocket(1200.0, 2500.0)[0], 'foot-right')
        self.assertEqual(nearest_pocket(0.0, 1270.0)[0], 'left-side')

    def test_the_head_rail_edge_spans_1270_mm(self):
        # The quad is ordered [TL, TR, BR, BL]; TL->TR is the head rail, which is
        # the 1270 mm side of the playing surface. The old rebuild destination
        # put 2540 mm on exactly this edge.
        from src.table_geometry import CANON_H, CANON_W, homography_to_canonical
        quad = np.array([[532.0, 323.0], [800.0, 324.0], [997.0, 569.0], [384.0, 563.0]])
        H = homography_to_canonical(quad)
        mm = []
        for x, y in quad:
            p = H @ np.array([x, y, 1.0])
            mm.append(p[:2] / p[2])
        self.assertAlmostEqual(float(mm[1][0] - mm[0][0]), CANON_W - 1, places=3)
        self.assertAlmostEqual(float(mm[3][1] - mm[0][1]), CANON_H - 1, places=3)


if __name__ == '__main__':
    unittest.main()
