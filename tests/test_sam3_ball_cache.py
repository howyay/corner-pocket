"""Tests for the SAM3 cache's cloth filter and its re-measure bookkeeping.

The filter is the fix for a measured failure: `detect_table`'s per-frame mask
zeroed a frame that held ten balls (t=487.3 of vod30).  These tests pin that the
verified reference geometry decides, that the choice is recorded, and that a
frame measured through a filter later shown to be wrong goes back on the list.
"""
import ast
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np

import data_guard

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.sam3_ball_cache import (cloth_mask, load_cache, load_filters,  # noqa: E402
                                 pending_times, reference_quad, save_cache)


class ClothMaskTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((720, 1280, 3), 90, np.uint8)
        self.quad = np.array([[400, 300], [900, 300], [950, 600], [350, 600]], np.float32)

    def test_the_reference_quad_decides_and_says_so(self):
        mask, source = cloth_mask(self.frame, reference=self.quad)
        self.assertEqual(source, "reference_quad")
        self.assertGreater(int(mask.sum()), 0)
        # a point inside the quad is cloth, a point far outside is not
        self.assertTrue(mask[450, 600])
        self.assertFalse(mask[50, 50])

    def test_without_a_reference_it_falls_back_and_says_so(self):
        # The workspace has calibration, so the fallback is exercised by taking
        # the reference away rather than by pointing at a missing file.
        from src import sam3_ball_cache as module
        original = module.reference_quad
        module.reference_quad = lambda *args, **kwargs: None
        try:
            mask, source = cloth_mask(self.frame, reference=None)
        finally:
            module.reference_quad = original
        self.assertEqual(source, "frame_mask")
        self.assertEqual(mask.shape, self.frame.shape[:2])

    def test_the_reference_quad_wins_over_a_broken_frame_mask(self):
        # A frame whose per-frame estimate would collapse: the reference still
        # accepts the ball positions inside it.
        mask, source = cloth_mask(self.frame, reference=self.quad)
        self.assertTrue(mask[450, 600])
        self.assertEqual(source, "reference_quad")

    def test_reference_quad_prefers_the_calibration_segment(self):
        # Any one of the three sources reference_quad() falls back through will do.
        data_guard.require_any(data_guard.ROOT / "out" / "calib_vod30_segments.json",
                               data_guard.ROOT / "out" / "pid_anchors_vod30.json",
                               data_guard.ROOT / "out" / "scan30" / "corners.json")
        quad = reference_quad()
        self.assertIsNotNone(quad)
        self.assertEqual(np.asarray(quad).shape, (4, 2))


class PendingTests(unittest.TestCase):
    def test_uncached_times_are_pending(self):
        self.assertEqual(pending_times([1.0, 2.0], cached=[1.0]), [2.0])

    def test_refetch_puts_a_cached_frame_back_on_the_list(self):
        self.assertEqual(pending_times([1.0, 2.0], cached=[1.0, 2.0], refetch=[2.0]), [2.0])

    def test_rounding_matches_the_cache_keys(self):
        # The cache is keyed by the rounded time, so 1.25 and 1.24 both resolve
        # to the key "1.2" and neither is measured twice.
        self.assertEqual(pending_times([1.25], cached=[1.2]), [])
        self.assertEqual(pending_times([1.24], cached=[1.2]), [])
        self.assertEqual(pending_times([1.26], cached=[1.2]), [1.3])


class CacheFilterMapTests(unittest.TestCase):
    def test_the_filter_that_produced_a_frame_is_stored_with_it(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            save_cache(path, {1.0: [{"score": 0.9}], 2.0: []}, {"1.0": 12.0}, "video.mp4",
                       {"1.0": "reference_quad", "2.0": "frame_mask"})
            self.assertEqual(load_filters(path), {"1.0": "reference_quad", "2.0": "frame_mask"})
            self.assertEqual(sorted(load_cache(path)), [1.0, 2.0])

    def test_a_cache_without_the_map_reports_none(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            path.write_text(json.dumps({"frames": {"1.0": []}}))
            self.assertEqual(load_filters(path), {})


# The two readers of the cache map, and the JSON key each one reads.  Round 77 measured
# that both functions held the same five statements twice, and only the key differed, so a
# repair of one reader left the other one as it was.  The duplicate-body walk
# tests/test_duplicate_bodies.py groups a body by its fingerprint and reports a pair that
# stands in two modules, so a pair inside one module is invisible to that walk.  Both
# readers call one body now, and this class holds them to it.
CACHE_MODULE = 'src/sam3_ball_cache.py'
CACHE_BODY = '_json_object'
CACHE_READERS = (('load_costs', 'cost'), ('load_filters', 'filter'))
#: The four statements of the one body, as ``ast.unparse`` spells them, without the
#: docstring.  They answer for a missing file, a damaged file, a file of another shape and
#: a good file.
CACHE_BODY_STATEMENTS = ('path = Path(path)',
                         'if not path.exists():\n    return {}',
                         'try:\n    data = json.loads(path.read_text())\n'
                         'except ValueError:\n    return {}',
                         'return data if isinstance(data, dict) else {}')


def module_text(relative):
    """The text of one repository file, relative to the repository root."""
    return (Path(__file__).resolve().parents[1] / relative).read_text(encoding='utf-8')


def statement_texts(node):
    """The statements of one function, unparsed, without its leading docstring."""
    statements = list(node.body)
    if (statements and isinstance(statements[0], ast.Expr)
            and isinstance(statements[0].value, ast.Constant)
            and isinstance(statements[0].value.value, str)):
        statements = statements[1:]
    return [ast.unparse(statement) for statement in statements]


def reader_problems(text, module=CACHE_MODULE):
    """The readers of one module text that do not call the one body, as one line each.

    The answer is empty when each reader holds one ``return`` statement that calls the
    body, and when the body holds the four statements of the cache map.  A second copy of
    those statements in a reader fails here, and a key that moves fails here.
    """
    problems = []
    bodies = {node.name: node for node in ast.parse(text).body
              if isinstance(node, ast.FunctionDef)}
    if CACHE_BODY not in bodies:
        problems.append(f'{module}: no {CACHE_BODY} function')
    elif tuple(statement_texts(bodies[CACHE_BODY])) != CACHE_BODY_STATEMENTS:
        problems.append(f'{module}: {CACHE_BODY} holds '
                        f'{statement_texts(bodies[CACHE_BODY])}; the one body holds '
                        f'{list(CACHE_BODY_STATEMENTS)}')
    for name, key in CACHE_READERS:
        if name not in bodies:
            problems.append(f'{module}: no {name} function')
            continue
        held = statement_texts(bodies[name])
        wanted = f'return {CACHE_BODY}(path).get({key!r}, {{}})'
        if held != [wanted]:
            problems.append(f'{module}: {name} holds {held}; a reader holds one statement: '
                            f'{wanted!r}')
    return problems


class CacheReaderBodyTests(unittest.TestCase):
    """The two readers of the cache map hold one body, in one home.

    Round 77 measured the defect: ``load_costs`` and ``load_filters`` held the same five
    statements twice, and only the JSON key differed.  Both readers call ``_json_object``
    now, and the two cases below hold them to it.
    """

    def test_the_two_readers_of_the_cache_map_call_the_one_body(self):
        """Each reader must hold one statement, and that statement calls the one body."""
        problems = reader_problems(module_text(CACHE_MODULE))
        self.assertEqual([], problems,
                         'the two readers of the cache map are not one body:\n'
                         + '\n'.join(problems))

    def test_the_two_readers_answer_from_the_one_body(self):
        """Both readers must call the one body; a private copy would miss the patch.

        The body is replaced by a counting function, so a reader that held its own copy of
        the statements would answer from the file and not from the patch.
        """
        from src import sam3_ball_cache as module
        calls = []
        original = module._json_object

        def counting(path):
            calls.append(path)
            return {'cost': {'1.0': 12.0}, 'filter': {'1.0': 'reference_quad'}}

        module._json_object = counting
        try:
            costs = module.load_costs('cache.json')
            filters = module.load_filters('cache.json')
        finally:
            module._json_object = original
        self.assertEqual(['cache.json', 'cache.json'], calls,
                         'each reader must call the one body once')
        self.assertEqual({'1.0': 12.0}, costs)
        self.assertEqual({'1.0': 'reference_quad'}, filters)

    def test_the_guard_reports_a_planted_second_body(self):
        """The old body of the round-77 defect, planted in one reader, must be reported."""
        text = module_text(CACHE_MODULE)
        planted = text.replace(
            '    return _json_object(path).get("filter", {})',
            '    path = Path(path)\n'
            '    if not path.exists():\n'
            '        return {}\n'
            '    try:\n'
            '        data = json.loads(path.read_text())\n'
            '    except ValueError:\n'
            '        return {}\n'
            '    return data.get("filter", {}) if isinstance(data, dict) else {}')
        self.assertNotEqual(text, planted, 'the case plants a second body in load_filters')
        problems = reader_problems(planted)
        self.assertTrue(any('load_filters' in problem for problem in problems),
                        'the planted second body is reported; the guard answered '
                        + repr(problems))


if __name__ == "__main__":
    unittest.main()
