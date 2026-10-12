"""One home for the seek window of one frame at one time, and one refusal text.

Round 76 measured six sites in five files that spelled the same four statements
by hand: open the container, set ``CAP_PROP_POS_MSEC``, read one frame, release
the container.  The six sites also disagreed on the answer of a gap: four raised
with three different texts, and two answered ``None``.

The seek window and the time and the frame number of the container now stand
once, in ``read_frame`` of ``src/pipeline.py``.  Two answers to a gap are real
rules, so the owner gives each flock its own name:

* ``extract_frame`` (and ``frame_gap_refusal`` below it) — this caller cannot
  work without a frame.  The site refuses with the one text.
* ``extract_frame_or_none`` — a gap is an answer for this caller.  The site
  answers ``None``.

Every site reads one of the owner names through a local import.  No site opens a
``cv2.VideoCapture`` of its own.

The planted-copy case holds the rule the scan reads: a hand-written window with
other names is reported, because the scan masks the names and keeps the shape.

Run: ``./scripts/pool-test.sh python test_frame_reader_owner``
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
TREES = (ROOT / "src", ROOT / "annotator", ROOT / "tools", ROOT / "scripts", ROOT / "tests")
VENDORED = ROOT / "src" / "sam3"

# The clip the probe measured: 40 frames of 64x48, MJPG at 30.0 fps, frame i is
# grey 5*i.  A lossy codec answers a grey near 5*i, so the cases allow +-4.
CLIP_FRAMES = 40
CLIP_SIZE = (64, 48)
CLIP_FPS = 30.0
CLIP_T = 0.5
CLIP_FRAME = 15          # the frame the container delivers at CLIP_T
CLIP_NUMBER = 16         # CAP_PROP_POS_FRAMES after that read: one more
CLIP_GREY = 75
GAP_T = 1e12             # beyond every clip of the tree
GAP_TEXT = "could not read frame at t=1000000000000.0"

# (module, function, the owner name it reads, the refusing name it must hold)
SITES = (
    ("src/pipeline.py", "extract_frame", "read_frame", "frame_gap_refusal"),
    ("src/pipeline.py", "extract_frame_or_none", "read_frame", None),
    ("src/tiny_ball_net.py", "load_frame", "read_frame", "frame_gap_refusal"),
    ("src/sam3_ball_cache.py", "detect_frame", "extract_frame", None),
    ("src/sam3_ball_cache.py", "diagnose_frame", "read_frame", None),
    ("src/ball_fp_audit.py", "measure_frame", "extract_frame", None),
    ("src/ball_fp_audit.py", "native_frame", "extract_frame_or_none", None),
    ("src/fast_ball_labels.py", "frame_at", "extract_frame_or_none", None),
)


def module_paths():
    """Every python file of the five trees, without the vendored package."""
    for tree in TREES:
        for path in sorted(tree.rglob("*.py")):
            if VENDORED in path.parents or ".venv" in path.parts:
                continue
            yield path


def function_body(tree, name):
    """The statements of one function, without its docstring."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = list(node.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            return node, body
    return None, None


def calls_in(path, function):
    """Every name called inside one function: a bare name or an attribute."""
    _, body = function_body(ast.parse(Path(path).read_text()), function)
    names = set()
    for node in body or ():
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                if isinstance(sub.func, ast.Name):
                    names.add(sub.func.id)
                elif isinstance(sub.func, ast.Attribute):
                    names.add(sub.func.attr)
    return names


def reader_offenders(path, function, owner, refusal=None):
    """The reasons one site does not read the owner, as text lines."""
    names = calls_in(path, function)
    found = []
    if "VideoCapture" in names:
        found.append(f"{Path(path).name}: {function} opens a VideoCapture of its own")
    if owner not in names:
        found.append(f"{Path(path).name}: {function} does not read {owner}")
    if refusal is not None and refusal not in names:
        found.append(f"{Path(path).name}: {function} does not name {refusal}")
    return found


def refusal_texts(path):
    """Every f-string of one file that names a frame gap, with its line."""
    found = []
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.JoinedStr):
            text = "".join(part.value for part in node.values
                           if isinstance(part, ast.Constant) and isinstance(part.value, str))
            if "frame at t=" in text:
                found.append((node.lineno, ast.unparse(node)))
    return found


class FrameReaderOwnerTests(unittest.TestCase):
    """The owner answers both container numbers, and every site reads it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.clip = Path(cls.tmp.name) / "clip.avi"
        writer = __import__("cv2").VideoWriter(str(cls.clip),
                                               __import__("cv2").VideoWriter_fourcc(*"MJPG"),
                                               CLIP_FPS, CLIP_SIZE)
        for index in range(CLIP_FRAMES):
            writer.write(np.full((CLIP_SIZE[1], CLIP_SIZE[0], 3), index * 5, np.uint8))
        writer.release()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_owner_answers_the_frame_the_time_and_the_number(self):
        from src.pipeline import read_frame

        frame, decoded_t, number = read_frame(self.clip, CLIP_T)
        self.assertEqual(frame.shape, (CLIP_SIZE[1], CLIP_SIZE[0], 3))
        self.assertLessEqual(abs(int(frame.mean()) - CLIP_GREY), 4)
        self.assertEqual(decoded_t, CLIP_T)
        self.assertEqual(number, CLIP_NUMBER)
        # the container counts the frames it delivered, so the number of the
        # first frame is one and the number after the read is one more
        _first, _t0, number0 = read_frame(self.clip, 0.0)
        self.assertEqual(number0, 1)

    def test_a_gap_gives_no_frame_and_no_promise_about_the_numbers(self):
        from src.pipeline import read_frame

        frame, _decoded_t, _number = read_frame(self.clip, GAP_T)
        self.assertIsNone(frame)

    def test_the_refusing_flock_refuses_with_the_one_text(self):
        from src import ball_fp_audit, tiny_ball_net
        from src.pipeline import extract_frame

        for name, call in (
            ("pipeline.extract_frame", lambda: extract_frame(self.clip, GAP_T)),
            ("tiny_ball_net.load_frame", lambda: tiny_ball_net.load_frame(self.clip, GAP_T)),
        ):
            with self.subTest(site=name):
                with self.assertRaises(RuntimeError) as caught:
                    call()
                self.assertEqual(str(caught.exception), GAP_TEXT)

    def test_the_none_flock_answers_none(self):
        from src.fast_ball_labels import frame_at
        from src.pipeline import extract_frame_or_none

        self.assertIsNone(extract_frame_or_none(self.clip, GAP_T))
        self.assertIsNone(frame_at(GAP_T, video=self.clip))

    def test_the_two_sam3_readers_hold_their_two_answers(self):
        from src.sam3_ball_cache import detect_frame, diagnose_frame

        reference = np.zeros((4, 2), np.float32)
        with self.assertRaises(RuntimeError) as caught:
            detect_frame(self.clip, GAP_T, None, None)
        self.assertEqual(str(caught.exception), GAP_TEXT)
        report = diagnose_frame(self.clip, GAP_T, None, None, reference=reference)
        self.assertEqual(report, {"t": GAP_T, "ok": False})

    def test_the_two_ball_fp_audit_readers_hold_their_two_answers(self):
        from src import ball_fp_audit

        # both sites name the vod30 clip through ROOT, so the case moves ROOT to
        # a tree that holds the measured clip
        original = ball_fp_audit.ROOT
        tree = Path(self.tmp.name) / "staged"
        (tree / "data").mkdir(parents=True, exist_ok=True)
        (tree / "data" / "vod_30min_260815.mp4").write_bytes(self.clip.read_bytes())
        ball_fp_audit.ROOT = tree
        try:
            self.assertIsNone(ball_fp_audit.native_frame(GAP_T))
            with self.assertRaises(RuntimeError) as caught:
                ball_fp_audit.measure_frame(GAP_T)
        finally:
            ball_fp_audit.ROOT = original
        self.assertEqual(str(caught.exception), GAP_TEXT)

    def test_every_site_reads_one_owner_name(self):
        offenders = []
        for path, function, owner, refusal in SITES:
            offenders += reader_offenders(ROOT / path, function, owner, refusal)
        self.assertEqual(offenders, [], "sites that do not read the owner: " + ", ".join(offenders))

    def test_the_one_refusal_text_stands_in_one_function(self):
        offenders = []
        for path in module_paths():
            if path == ROOT / "src" / "pipeline.py":
                continue
            for line, text in refusal_texts(path):
                offenders.append(f"{path.relative_to(ROOT)}:{line}: {text}")
        self.assertEqual(offenders, [], "a second refusal text stands at: " + ", ".join(offenders))
        found = refusal_texts(ROOT / "src" / "pipeline.py")
        self.assertEqual(len(found), 1, f"pipeline.py holds {len(found)} refusal texts")
        _node, body = function_body(ast.parse((ROOT / "src" / "pipeline.py").read_text()),
                                    "frame_gap_refusal")
        self.assertIn(found[0][0], [s.lineno for s in body],
                      "the refusal text left frame_gap_refusal")

    def test_the_scan_sees_a_planted_copy(self):
        planted = Path(self.tmp.name) / "planted_reader.py"
        planted.write_text(
            "import cv2\n"
            "\n"
            "\n"
            "def planted_seek(video, t):\n"
            "    cap = cv2.VideoCapture(str(video))\n"
            "    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)\n"
            "    ok, bgr = cap.read()\n"
            "    cap.release()\n"
            "    if not ok:\n"
            "        raise RuntimeError(f'no frame at t={t}')\n"
            "    return bgr\n"
        )
        found = reader_offenders(planted, "planted_seek", "read_frame")
        self.assertTrue(any("VideoCapture" in line for line in found),
                        "the scan did not see the planted window: " + str(found))
        self.assertEqual(len(refusal_texts(planted)), 1, "the scan did not see the planted text")


if __name__ == "__main__":
    unittest.main()
