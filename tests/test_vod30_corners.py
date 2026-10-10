"""One owner for the vod30 reference quad, and five readers that go through it.

``annotator/corners_30min.json`` is a hand-made input, not a pipeline output.
Five calibration tools read it.  Before this test each one opened a different
path, ``out/corners_30min.json``, which is git-ignored and written by nobody: a
fresh clone failed all five loaders.

``src/vod30_corners.py`` owns the path and the parser.  These tests hold that
ownership: the owner resolves from the top of the repository, the five readers
name no corner path of their own, and a copy of the repository without ``out/``
still loads the same quad.

Two tests state the boundary they defend.  ``test_no_reader_spells_a_corner_path``
reads the code of each reader and skips prose, so a comment or a docstring may
name the old file; ``test_only_the_owner_moves_corners_30min_under_a_root`` scans
every python file of the repository and allows the filename in the owner, in
this test, and inside the name ``corners_30min_v2.json``, which is a different
artifact with its own owner.
"""
import ast
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tokenize
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import vod30_corners  # noqa: E402
from vod30_corners import load, reference_path  # noqa: E402

# Imported once, at module level: src/eval_calib.py reaches torch through
# src/pipeline.py, and torch refuses a second import inside one interpreter.
import eval_calib  # noqa: E402

TRACKED_JSON = REPO / "annotator" / "corners_30min.json"
OUT_JSON = REPO / "out" / "corners_30min.json"
EVAL_CALIB = REPO / "src" / "eval_calib.py"
OWNER_MODULE = "src/vod30_corners.py"
TEST_MODULE = "tests/test_vod30_corners.py"
FIXTURE_QUAD = "corners_30min_v2.json"  # a different artifact, not this quad

# The five calibration tools that read the quad, each with the name of the
# owner function it calls (or a citation of the owner in its prose).
READERS = {
    "src/audit_calib.py": ("load_vod30_corners()", "src/vod30_corners.py"),
    "src/eval_calib.py": ("vod30_corners.load", "import vod30_corners"),
    "src/quad_fit.py": ("load_vod30_corners()", "src/vod30_corners.py"),
    "src/quad_fit_lines.py": ("load_vod30_corners()", "src/vod30_corners.py"),
    "src/quad_refine.py": ("load_vod30_corners()", "src/vod30_corners.py"),
}

# The owner filename, and the same name inside the other artifact's filename.
# A bare ``corners_30min`` is not a path: ``estimate_corners_30min`` is a name.
CORNER_PATH = re.compile(r"[\"']corners_30min\.json[\"']|corners_30min(?!_v2)\b\.json")
FIXTURE_PATH = re.compile(r"corners_30min_v2")


def prose_spans(body):
    """Every ``(line, column)`` of *body* that is a comment or a docstring.

    A comment and a docstring may name a file; a call and a variable name may
    not.  The tokenizer and the parse tree give both spans exactly, so the test
    does not need to guess from indentation.
    """
    spans = set()
    for token in tokenize.generate_tokens(io.StringIO(body).readline):
        if token.type == tokenize.COMMENT:
            for column in range(token.start[1], token.end[1]):
                spans.add((token.start[0], column))
    tree = ast.parse(body)
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        doc = ast.get_docstring(node, clean=False)
        if doc is None:
            continue
        for token in tokenize.generate_tokens(io.StringIO(body).readline):
            if token.type != tokenize.STRING or doc not in token.string:
                continue
            for line in range(token.start[0], token.end[0] + 1):
                last = token.end[1] if line == token.end[0] else None
                first = token.start[1] if line == token.start[0] else 0
                for column in range(
                    first, last if last is not None else len(body.splitlines()[line - 1])
                ):
                    spans.add((line, column))
    return spans


def corner_paths_in(body):
    """The pieces of code in *body* that name this quad's file."""
    lines = body.splitlines()
    prose = prose_spans(body)
    found = set()
    for number, line in enumerate(lines, 1):
        for column in range(len(line)):
            if (number, column) in prose:
                continue
            match = CORNER_PATH.search(line, column)
            if match is not None and match.start() == column:
                found.add((line.strip(), match.group(0)))
    return sorted(found)


def python_files():
    """Every python file of the repository that is source, not a build."""
    for path in sorted(REPO.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel.split("/")[0] in {".git", ".venv", "node_modules", "out", "data"}:
            continue
        yield rel, path


def expected_corners():
    """The quad as the tracked file holds it, read without the owner."""
    data = json.loads(TRACKED_JSON.read_text())
    return [[float(x), float(y)] for x, y in data["corners"]]


class OwnerTests(unittest.TestCase):
    """The one module that holds the path and the parser."""

    def test_the_owner_resolves_the_tracked_file_from_the_repository_top(self):
        self.assertEqual(reference_path(), TRACKED_JSON)
        self.assertEqual(TRACKED_JSON.parent.name, "annotator")
        self.assertTrue(TRACKED_JSON.is_file(), f"missing {TRACKED_JSON}")

    def test_load_returns_the_shape_and_the_dtype_the_readers_use(self):
        quad = load()
        self.assertEqual(quad.shape, (4, 2))
        self.assertEqual(quad.dtype, vod30_corners.REF_DTYPE)
        self.assertTrue(bool((quad == quad).all()))

    def test_load_returns_the_four_corners_of_the_tracked_file(self):
        for got, want in zip(load().tolist(), expected_corners()):
            self.assertAlmostEqual(got[0], want[0], places=3)
            self.assertAlmostEqual(got[1], want[1], places=3)

    def test_the_quad_is_a_rectangle_in_the_order_the_readers_assume(self):
        tl, tr, br, bl = load().tolist()
        self.assertLess(tl[0], tr[0])  # top-left is left of top-right
        self.assertLess(bl[0], br[0])  # bottom-left is left of bottom-right
        self.assertLess(tl[1], bl[1])  # the top edge is above the bottom edge
        self.assertLess(tr[1], br[1])
        for corner in (tl, tr, br, bl):
            self.assertTrue(all(0.0 <= v <= 4096.0 for v in corner), corner)


class ReaderRoutingTests(unittest.TestCase):
    """Every reader reaches the quad through the owner, and none by a path."""

    def test_the_five_readers_are_the_files_this_test_routes(self):
        for rel in READERS:
            self.assertTrue((REPO / rel).is_file(), f"missing reader {rel}")

    def test_every_reader_reaches_the_owner_by_call_or_by_citation(self):
        for rel, (call, citation) in READERS.items():
            body = (REPO / rel).read_text()
            with self.subTest(reader=rel):
                self.assertTrue(
                    call in body or citation in body,
                    f"{rel} no longer reaches the quad through the owner: "
                    f"neither {call!r} nor {citation!r} appears in it",
                )

    def test_no_reader_spells_a_corner_path(self):
        for rel in READERS:
            with self.subTest(reader=rel):
                found = corner_paths_in((REPO / rel).read_text())
                self.assertEqual(
                    found,
                    [],
                    f"{rel} hard-codes a path to the quad: {found}.  The one "
                    f"owner is {OWNER_MODULE}; call its load().",
                )

    def test_only_the_owner_moves_corners_30min_under_a_root(self):
        owners = set()
        for rel, path in python_files():
            for line, name in corner_paths_in(path.read_text(errors="replace")):
                if FIXTURE_PATH.search(name):
                    continue  # the _v2 artifact has its own readers
                owners.add(rel)
                self.assertIn(
                    rel,
                    {OWNER_MODULE, TEST_MODULE},
                    f"{rel} holds a path to {name}: {line!r}.  The one owner "
                    f"is {OWNER_MODULE}.",
                )
        self.assertEqual(
            sorted(owners),
            sorted([OWNER_MODULE, TEST_MODULE]),
            "the owner or this test no longer names the tracked quad",
        )

    def test_every_reader_module_imports_and_reaches_the_same_quad(self):
        """Each reader imports, and the owner it binds hands back one quad.

        The three script modules bind the owner inside their ``__main__``
        block, because an import of them must not reach for media.  Their own
        import statements are run here, in a namespace of their own, which is
        what the script sees when it runs.
        """
        want = expected_corners()
        for rel in READERS:
            with self.subTest(reader=rel):
                module = self._import(rel)
                self.assertTrue(module, f"{rel} imported as nothing")
                quad = self._quad_of(module, rel)
                self.assertEqual(quad.shape, (4, 2))
                for corner_got, corner_want in zip(quad.tolist(), want):
                    self.assertAlmostEqual(corner_got[0], corner_want[0], places=3)
                    self.assertAlmostEqual(corner_got[1], corner_want[1], places=3)

    def _quad_of(self, module, rel):
        """The quad the reader reaches, through whichever name it binds."""
        if hasattr(module, "load_vod30_corners"):
            return module.load_vod30_corners()
        if hasattr(module, "vod30_corners"):
            return module.vod30_corners.load()
        body = (REPO / rel).read_text()
        main = [
            node
            for node in ast.parse(body).body
            if isinstance(node, ast.If) and "__main__" in ast.dump(node.test)
        ]
        self_imports = [
            node
            for block in main
            for node in block.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        self.assertTrue(
            self_imports,
            f"{rel} has no __main__ import that reaches the owner",
        )
        namespace = {}
        for node in self_imports:
            exec(compile(ast.Module([node], []), rel, "exec"), namespace)
        return namespace["load_vod30_corners"]()

    @staticmethod
    def _import(rel):
        """Import a reader by file path, in a namespace of its own.

        The three quad modules import each other by bare name, so an import
        that stays in this interpreter would replace the module the next
        subtest sees.  The namespace is put back either way.  A module this
        test already imported -- src/eval_calib.py, which reaches torch -- is
        returned as it is: a second import of torch in one interpreter fails.
        """
        name = Path(rel).stem
        if name in sys.modules:
            return sys.modules[name]
        spec = importlib.util.spec_from_file_location(name, REPO / rel)
        module = importlib.util.module_from_spec(spec)
        saved = dict(sys.modules)
        try:
            spec.loader.exec_module(module)
        finally:
            for key in [k for k in sys.modules if k not in saved]:
                del sys.modules[key]
            sys.modules.update(saved)
        return module


class NoOutTreeTests(unittest.TestCase):
    """The quad resolves for a copy of the repository that has no ``out/``."""

    def test_the_checkout_has_an_out_copy_so_the_proof_bites(self):
        self.assertTrue(
            OUT_JSON.is_file(),
            f"{OUT_JSON} is absent, so this test cannot show that the readers "
            f"stopped using it",
        )

    def test_a_repository_top_without_out_still_holds_the_quad(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "annotator").mkdir()
            (root / "annotator" / "corners_30min.json").write_text(
                TRACKED_JSON.read_text()
            )
            self.assertFalse((root / "out").exists())
            self.assertEqual(
                reference_path(root), root / "annotator" / "corners_30min.json"
            )
            quad = load(root)
            self.assertEqual(quad.shape, (4, 2))
            for corner_got, corner_want in zip(quad.tolist(), expected_corners()):
                self.assertAlmostEqual(corner_got[0], corner_want[0], places=3)
                self.assertAlmostEqual(corner_got[1], corner_want[1], places=3)

    def test_the_loader_resolves_from_another_working_directory(self):
        program = (
            "import json\n"
            "import vod30_corners as c\n"
            "print(c.reference_path())\n"
            "print(c.load().shape)\n"
            "print(json.dumps([float(v) for v in c.load()[0]]))\n"
        )
        done = subprocess.run(
            [sys.executable, "-c", program],
            cwd="/",
            env={
                "PYTHONPATH": f"{REPO / 'src'}:{REPO}",
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            },
            capture_output=True,
            text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[0], str(TRACKED_JSON))
        self.assertEqual(lines[1], "(4, 2)")
        first = json.loads(lines[2])
        want = expected_corners()[0]
        self.assertAlmostEqual(first[0], want[0], places=3)
        self.assertAlmostEqual(first[1], want[1], places=3)
        self.assertTrue(OUT_JSON.is_file(), "the probe changed the real tree")


class LocalScaleTests(unittest.TestCase):
    """The local scale has one unit: pixels per millimetre.

    ``src/eval_calib.py`` used to call it ``local_mm_per_px`` and to document
    mm per pixel, while the body and both call sites divided by its answer.
    The answer is the distance an image point moves when the canonical x
    advances by one millimetre, so the name and the number now agree.
    """

    CANON_CENTRE = (635.0, 1270.0)  # CANON_W / 2, CANON_H / 2
    CANON_OTHER = (127.0, 254.0)

    def setUp(self):
        self.scale = eval_calib.local_px_per_mm

    def image_homography(self):
        """The image-from-canonical homography the scale is measured with."""
        import pipeline

        corners = np.array(expected_corners(), dtype=np.float64)
        return np.linalg.inv(pipeline.homography_to_canonical(corners))

    def test_one_canonical_millimetre_moves_the_image_point_0_344822_px(self):
        got = self.scale(self.image_homography(), np.array(self.CANON_CENTRE))
        self.assertAlmostEqual(got, 0.3448222629535022, places=9)
        # the promised unit, mm per px, is the reciprocal
        self.assertAlmostEqual(1.0 / got, 2.900044769252169, places=9)

    def test_a_second_canonical_point_has_its_own_scale(self):
        got = self.scale(self.image_homography(), np.array(self.CANON_OTHER))
        self.assertAlmostEqual(got, 0.31587778546912104, places=9)
        self.assertAlmostEqual(1.0 / got, 3.165781343296634, places=9)

    def test_the_measured_distance_is_what_the_function_returns(self):
        """The number is the step in image pixels, measured, not inferred."""
        import calibrate

        H = self.image_homography()
        x, y = self.CANON_CENTRE
        before = calibrate.project(H, np.array([[x, y]]))[0]
        after = calibrate.project(H, np.array([[x + 1.0, y]]))[0]
        step = float(np.hypot(after[0] - before[0], after[1] - before[1]))
        self.assertAlmostEqual(step, self.scale(H, np.array(self.CANON_CENTRE)), places=12)
        self.assertAlmostEqual(step, 0.3448222629535022, places=9)

    def test_the_name_the_docstring_and_both_call_sites_hold_one_unit(self):
        body = EVAL_CALIB.read_text()
        tree = ast.parse(body)
        self.assertNotIn(
            "local_mm_per_px",
            body,
            "the name of the function disagrees with its unit again",
        )
        definitions = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        self.assertIn("local_px_per_mm", definitions)
        calls = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertEqual(
            calls.count("local_px_per_mm"),
            2,
            "a call site no longer divides the pixel error by the local scale",
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != "local_px_per_mm":
                continue
            doc = ast.get_docstring(node) or ""
            self.assertIn("Pixels per millimetre", doc)

    def test_the_docstring_bar_of_the_module_is_compared_in_its_code(self):
        body = EVAL_CALIB.read_text()
        for line in body.splitlines():
            if line.startswith("Bar:"):
                self.assertIn("15 mm", line)
                break
        else:
            self.fail("the module docstring no longer states a bar")
        self.assertIn("bar_mm = 15.0", body)
        self.assertIn("bar_ok = len(hold_frames) >= 5 and mean_mm <= bar_mm", body)


if __name__ == "__main__":
    unittest.main()
