"""The sentence of a failed open has one home: ``src/video_errors.py``.

Round 113 measured the sentence at fifteen code sites of seven ``src`` modules.  It
stood in a dict at ``src/calib_mapping_audit.py:258``, ``:447`` and ``:451``; in a
``SystemExit`` at ``src/calib_segment_measure.py:296`` and at
``src/segment_calib_report.py:142`` and ``:184``; in a ``RuntimeError`` at
``src/enroll_from_tracklet.py:518``, ``:786`` and ``:1390``, at
``src/eval_faces.py:602`` and at ``src/eval_table_detect.py:345``; and in an
``OSError`` at ``src/motion_scan.py:367``, ``:535``, ``:700`` and ``:1726``.  Every
site now builds its message with ``cannot_open``, keeps its own exception class and
its own payload, and stands on its own line still.

Four lines spell a different sentence.  They are pinned here with their reason:

* ``annotator/refusals.py:215`` is the refusal subject ``cannot open VOD``: a key of
  the refusal table of the served API, and not a message built from a path.
* ``annotator/unified_server.py:1892`` raises that subject as an ``APIError``.
* ``src/timing_verify.py:161`` is the second wording, ``cannot open video: <path>``.
* ``tools/playfield_harness.py:47`` is the wording of the harness, which
  ``tests/test_playfield_harness.py:246`` reads.

The rule below reads every python file of the four shipped packages, drops the
docstrings, and answers a code string that spells ``cannot open `` beside a format
placeholder: a ``%s`` in the value itself, or an f-string that holds the placeholder
in its own node.  ``src/sam3`` is out of scope: it is a third-party tree.

Run the module with ``./scripts/pool-test.sh python test_cannot_open_owner``.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from _shipped import code_strings  # noqa: E402

#: The one module that owns the sentence.
HOME = "src/video_errors.py"

#: The one spelling of the sentence in the home.
HOME_FORM = 'return f"cannot open {path}"'

#: The four shipped packages of the walk, and the third-party tree it leaves out.
WALKED = ("src/**/*.py", "annotator/*.py", "tools/*.py", "scripts/*.py")
SKIP = ("src/sam3",)

#: The walk reads 118 files today, and every one of them parses: 100 files stand in
#: ``src``, 12 in ``annotator``, 5 in ``tools`` and 1 in ``scripts``.
FILE_FLOOR = 100
SCANNED_FLOOR = 100

#: The sentence, and the marks of a placeholder that stands in a value itself.
SENTENCE = "cannot open "
PLACEHOLDER = re.compile(r"%[sdfr]|\{")

#: The lines that spell a different sentence.  The reason of each line stands in the
#: module docstring above.
PINNED = {
    "annotator/refusals.py": (215,),
    "annotator/unified_server.py": (1892,),
    "src/timing_verify.py": (161,),
    "tools/playfield_harness.py": (47,),
}

#: Every rewritten site, as ``relative: ((line, the stripped text of the line), ...)``.
#: A site that moves, or that changes its class or its payload, must restate itself
#: here.
SITES = {
    "src/calib_mapping_audit.py": (
        (258, 'return {"error": cannot_open(video)}'),
        (447, 'return {"error": cannot_open(video), "quad_px": np.round(quad, 1).tolist()}'),
        (451, 'return {"error": cannot_open(video)}'),
    ),
    "src/calib_segment_measure.py": (
        (296, "raise SystemExit(cannot_open(args.video))"),
    ),
    "src/enroll_from_tracklet.py": (
        (518, "raise RuntimeError(cannot_open(video))"),
        (786, "raise RuntimeError(cannot_open(video))"),
        (1390, "raise RuntimeError(cannot_open(Path(root) / DATASETS[dataset]))"),
    ),
    "src/eval_faces.py": (
        (602, "raise RuntimeError(cannot_open(video))"),
    ),
    "src/eval_table_detect.py": (
        (345, "raise RuntimeError(cannot_open(video))"),
    ),
    "src/motion_scan.py": (
        (367, "raise OSError(cannot_open(video))"),
        (535, "raise OSError(cannot_open(video))"),
        (700, "raise OSError(cannot_open(video))"),
        (1726, "raise OSError(cannot_open(video))"),
    ),
    "src/segment_calib_report.py": (
        (142, "raise SystemExit(cannot_open(video))"),
        (184, "raise SystemExit(cannot_open(video))"),
    ),
}

#: The seven readers of the home, and the one edge each of them adds.
READERS = tuple(sorted(SITES))
EDGE = "from src.video_errors import cannot_open"

#: A planted copy of the sentence, and a planted file that names it in prose alone.
PLANTED = "src/planted_cannot_open.py"
PLANTED_COPY_LINE = 7
PLANTED_TEXT = (
    '"""A planted reader, written and removed by the guard."""\n'
    "\n"
    "import cv2\n"
    "\n"
    "\n"
    "def open_video(video):\n"
    '    raise OSError(f"cannot open {video}")\n'
)
QUIET = "src/quiet_cannot_open.py"
QUIET_TEXT = (
    '"""A planted file that names the sentence in prose alone.\n'
    "\n"
    "The sentence of a failed open reads cannot open <a path>, and this file\n"
    'says so without one code string that spells it.\n'
    '"""\n'
    "\n"
    "\n"
    "def open_video(video):\n"
    '    """Answer the video itself, as a comment does: no message here."""\n'
    "    # The sentence the guard looks for reads cannot open {video}.\n"
    "    return video\n"
)

#: The home, read in a fresh interpreter.
PROBE = (
    "from src.video_errors import cannot_open\n"
    "print(repr(cannot_open('out/vod30.mp4')))\n"
    "print(repr(cannot_open(3)))\n"
)
PROBE_ANSWERS = ["'cannot open out/vod30.mp4'", "'cannot open 3'"]


def source_lines(relative: str) -> list:
    """The lines of one file of the tree, without the newline character."""
    return (ROOT / relative).read_text(encoding="utf-8").splitlines()


def walked_files() -> list:
    """Every python file of the shipped packages, the third-party tree left out."""
    found = []
    for pattern in WALKED:
        for path in sorted(ROOT.glob(pattern)):
            relative = path.relative_to(ROOT).as_posix()
            if "__pycache__" in path.parts or relative.startswith(SKIP):
                continue
            found.append(path)
    return found


def spells_the_sentence(value: str) -> bool:
    """True for a code string whose own value carries the sentence and a mark."""
    return value.startswith(SENTENCE) and PLACEHOLDER.search(value) is not None


def spelled_sites(tree: ast.AST) -> list:
    """Every pair that spells the sentence beside a format placeholder, by line.

    A plain string carries its placeholder in the value itself, as ``cannot open %s``
    does.  An f-string keeps its placeholder in the node, and its value part reads
    ``cannot open `` alone, so the walk of the f-strings below answers those too.
    """
    pairs = {(line, value) for line, value in code_strings(tree)
             if spells_the_sentence(value)}
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        if not any(isinstance(part, ast.FormattedValue) for part in node.values):
            continue
        head = node.values[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            if head.value.startswith(SENTENCE):
                pairs.add((head.lineno, head.value))
    return sorted(pairs)


def analyze() -> list:
    """Every walked code string that spells the sentence outside the pins."""
    offenders = []
    for path in walked_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative == HOME:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, value in spelled_sites(tree):
            if line in PINNED.get(relative, ()):
                continue
            offenders.append("%s:%d: %r spells the sentence; read %s"
                             % (relative, line, value, HOME))
    return offenders


def planted_copy(relative: str, text: str) -> list:
    """Write one planted file, answer the offenders, and remove the file again."""
    path = ROOT / relative
    path.write_text(text, encoding="utf-8")
    try:
        return analyze()
    finally:
        path.unlink()


def probe_home() -> list:
    """The answers of the home, read in a fresh interpreter."""
    handled = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT,
                             capture_output=True, text=True)
    if handled.returncode != 0:
        raise AssertionError(handled.stderr)
    return handled.stdout.splitlines()


class HomeTests(unittest.TestCase):
    """The home answers the sentence, and every site builds from it."""

    def test_the_home_answers_the_sentence(self):
        self.assertEqual(PROBE_ANSWERS, probe_home())

    def test_the_home_holds_one_spelling_of_the_sentence(self):
        self.assertIn(HOME_FORM, [line.strip() for line in source_lines(HOME)])
        tree = ast.parse((ROOT / HOME).read_text(encoding="utf-8"))
        spelled = [value for _, value in code_strings(tree)
                   if value.startswith("cannot open")]
        self.assertEqual([SENTENCE], spelled)

    def test_the_home_imports_nothing_of_the_tree(self):
        tree = ast.parse((ROOT / HOME).read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertEqual([], [name for name in imported if name.startswith("src")],
                         "%s starts an import cycle" % HOME)

    def test_every_site_builds_from_the_home(self):
        for relative in READERS:
            self.assertIn(EDGE, (ROOT / relative).read_text(encoding="utf-8"),
                          "%s must read %s" % (relative, HOME))
        for relative, sites in sorted(SITES.items()):
            lines = source_lines(relative)
            for line, form in sites:
                self.assertEqual(form, lines[line - 1].strip(),
                                 "%s:%d must keep its own class and payload"
                                 % (relative, line))


class WalkTests(unittest.TestCase):
    """No file of the walk spells the sentence itself."""

    def test_no_file_spells_the_sentence(self):
        self.assertEqual([], analyze())

    def test_the_walk_reads_the_shipped_tree(self):
        walked = walked_files()
        self.assertGreaterEqual(len(walked), FILE_FLOOR)
        parsed = 0
        for path in walked:
            ast.parse(path.read_text(encoding="utf-8"))
            parsed += 1
        self.assertGreaterEqual(parsed, SCANNED_FLOOR)
        self.assertEqual(parsed, len(walked))

    def test_the_walk_finds_a_planted_copy(self):
        offenders = planted_copy(PLANTED, PLANTED_TEXT)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("%s:%d" % (PLANTED, PLANTED_COPY_LINE)),
                        offenders[0])

    def test_the_walk_ignores_prose(self):
        self.assertEqual([], planted_copy(QUIET, QUIET_TEXT))

    def test_every_pin_names_a_live_line(self):
        for relative, lines in sorted(PINNED.items()):
            text = source_lines(relative)
            for line in lines:
                self.assertIn(SENTENCE, text[line - 1],
                              "%s:%d must still spell its wording" % (relative, line))


if __name__ == "__main__":
    unittest.main()
