"""The crop set folder and its two documents have one home: ``src/store_files.py``.

Round 111 walked the crop vocabulary and found the same three words spelled again and
again: the folder ``out/unlabeled_crops`` and the two documents ``ctx.json`` and
``meta.json``.  The measuring walk counted the folder chosen by ``BALL_SETS[0]`` at six
code sites (``src/make_ctx.py:23``, ``src/recut_crops.py:39``, ``src/confusion.py:22``,
``annotator/server.py:47``, ``annotator/unified_server.py:1880`` and
``src/store.py:343``), the document ``ctx.json`` at nine code sites in five modules, and
the document ``meta.json`` at sixteen code sites in ten modules.  A rename of a crop set
then needed one edit at each site, and a site that missed the edit opened a second folder.

The home is the module that already owns the crop sets and the served document names::

    src/store_files.py:43: BALL_SETS = ("unlabeled_crops", "unlabeled_crops2", "vod30_event_crops")

Round 112 appended the three names and one function below line 256 of that module, so the
pinned lines 191, 203 and 205 of :func:`document_paths` keep their numbers, and the row at
:205 now reads the folder through the home::

    src/store_files.py, after :256: CTX_DOCUMENT = "ctx.json"
                                    META_DOCUMENT = "meta.json"
                                    def crops_dir(set_name) -> str

An unknown set name has one home too.  Round 116 moved the sentence of the refusal into
``unknown_ball_set`` in ``src/store_rules.py``, and the three writers now read it:
``src/store.py:342``, ``src/store_files.py:286`` and ``src/store_pg.py:344``.
``annotator/unified_server.py:1880`` still refuses the same name on the wire, in four
words and without the name, before the folder is joined.

A few sites spell the same words and are NOT the crop set.  They stay, and this guard
pins each of them with its reason:

* ``src/collect2.py:92`` and ``:93`` write the documents of that tool's own output folder.
* ``src/merge_sets.py:24``, ``:25``, ``:46`` and ``:47`` compose the same documents from
  two crop sets into a third folder; that tool has its own two-folder vocabulary.
* ``src/train_ball_id.py:74``, ``:86``, ``src/pid_osnet_tight.py:30`` and
  ``src/multiplex_demo.py:280`` read the ``meta.json`` of another folder: a different fact.

The walk below reads every python file of ``src/`` and ``annotator/``, skips ``src/sam3/``,
drops the string node of a module, class or function docstring, and answers every code
constant equal to one of the three words that is neither the home nor a pinned site.  Two
floors keep a walk that read nothing from passing in silence.

Run: ``./scripts/pool-test.sh python test_crops_document_owner``
"""
from __future__ import annotations

import ast
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

#: The home module and the three names it owns.
HOME = "src/store_files.py"
SETS_NAME = "BALL_SETS"
FOLDER_FUNCTION = "crops_dir"
CTX_NAME = "CTX_DOCUMENT"
META_NAME = "META_DOCUMENT"
CTX_VALUE = "ctx.json"
META_VALUE = "meta.json"
#: The three crop set names, spelled once here so a case can measure the home against them.
CROP_SETS = ("unlabeled_crops", "unlabeled_crops2", "vod30_event_crops")
#: The row of the home that reads the folder, pinned by number and text.
LABELS_LINE = 205
LABELS_FORM = 'return [f"{crops_dir(crop_set)}/labels.json" for crop_set in BALL_SETS]'
#: The three writers that refuse an unknown set name.  The sentence of the three has
#: one home, ``unknown_ball_set`` in ``src/store_rules.py`` (round 116).
REFUSALS = ("src/store.py", "src/store_files.py", "src/store_pg.py")
REFUSAL_FORM = "raise ValueError(unknown_ball_set(crop_set))"
#: The same refusal, with the variable name of each writer's own parameter:
#: `crops_dir` names its argument `set_name`.  The count of the calls is one per file.
REFUSAL_FORMS = {"src/store.py": REFUSAL_FORM,
                 "src/store_files.py": "raise ValueError(unknown_ball_set(set_name))",
                 "src/store_pg.py": REFUSAL_FORM}
WIRE_REFUSAL = 'raise APIError("unknown ball set", 404)'
#: The modules that read the home for a folder or a document name.
READERS = ("src/make_ctx.py", "src/recut_crops.py", "src/confusion.py", "annotator/server.py",
           "annotator/unified_server.py", "src/store.py")
#: The directories the walk reads, the subtree it skips, and the floors that keep a
#: vacuous walk from passing.
WALKED = ("src/**/*.py", "annotator/*.py")
SKIP = ("src/sam3",)
FILE_FLOOR = 200
SCANNED_FLOOR = 100
#: The words of the crop vocabulary, and the sites that may spell them without a copy.
WORDS = (CTX_VALUE, META_VALUE) + CROP_SETS
PINNED = {
    HOME: (),  # the home itself is the owner, never an offender
    "src/collect2.py": (92, 93),
    "src/merge_sets.py": (24, 25, 46, 47),
    "src/train_ball_id.py": (74, 86),
    "src/pid_osnet_tight.py": (30,),
    "src/multiplex_demo.py": (280,),
}
#: Planted modules of the honesty cases.
PLANTED = "src/planted_crops.py"
PLANTED_COPY_LINE = 6
PLANTED_TEXT = ('"""A planted module that names meta.json in its docstring."""\n'
                "\n"
                "\n"
                "def row():\n"
                '    """The docstring names ctx.json, which is no code constant."""\n'
                '    return "%s"\n' % META_VALUE)
QUIET = "src/quiet_crops.py"
QUIET_TEXT = ('"""A planted module that names meta.json in prose only."""\n'
              "\n"
              "\n"
              "def row():\n"
              '    """The docstring names ctx.json, which is no code constant."""\n'
              "    return 1\n")
#: The probe that reads the home in a fresh interpreter of this venv.
PROBE = ("import src.store_files as module; "
         "print([module.%s(name) for name in module.%s]); "
         "print(repr(module.%s), repr(module.%s))" % (FOLDER_FUNCTION, SETS_NAME, CTX_NAME, META_NAME))


def source_lines(relative: str) -> list:
    """The lines of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8").splitlines()


def walked_files() -> list:
    """Every walked python file, the generated subtree left out."""
    found = sorted(path for pattern in WALKED for path in ROOT.glob(pattern)
                   if "__pycache__" not in path.parts
                   and not any(part in SKIP for part in path.relative_to(ROOT).parts))
    return found


def planted_copy(relative: str, text: str) -> str:
    """Write one planted module, run the caller, and remove it."""
    path = ROOT / relative
    path.write_text(text, encoding="utf-8")
    try:
        return analyze()
    finally:
        path.unlink()


def analyze(extra=()) -> list:
    """Every walked code constant of the crop vocabulary that is no home and no pin."""
    offenders = []
    for path in walked_files():
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, value in code_strings(tree):
            if value not in WORDS:
                continue
            if relative == HOME:
                continue
            if line in PINNED.get(relative, ()):
                continue
            offenders.append("%s:%d: %r spells the crop vocabulary; read %s"
                             % (relative, line, value, HOME))
    return offenders


class HomeTests(unittest.TestCase):
    """The home holds the three names, and the pinned row reads it."""

    def test_the_folder_is_the_set_name(self):
        answer = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.splitlines()
        self.assertEqual(answer[0], "['out/unlabeled_crops', 'out/unlabeled_crops2', "
                                    "'out/vod30_event_crops']")
        self.assertEqual(answer[1], "'ctx.json' 'meta.json'")

    def test_an_unknown_name_is_refused_in_the_store_words(self):
        code = ("import src.store_files as module\n"
                "try:\n"
                "    module.crops_dir('nope')\n"
                "except ValueError as caught:\n"
                "    print(caught)\n")
        answer = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.strip()
        self.assertEqual(answer, "unknown ball set: nope")
        for relative, form in REFUSAL_FORMS.items():
            stripped = [line.strip() for line in source_lines(relative)]
            self.assertIn(form, stripped,
                          "%s no longer refuses an unknown set name" % relative)
        self.assertIn(WIRE_REFUSAL, [line.strip() for line in source_lines("annotator/unified_server.py")],
                      "the wire refusal of an unknown ball set moved")

    def test_the_labels_row_reads_the_home(self):
        self.assertEqual(source_lines(HOME)[LABELS_LINE - 1].strip(), LABELS_FORM)
        self.assertLessEqual(LABELS_LINE, 205, "the pinned lines of document_paths moved")


class WalkTests(unittest.TestCase):
    """The walk names every copy that is no home and no pin."""

    def test_no_file_spells_the_crop_vocabulary(self):
        offenders = analyze()
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_walk_reads_the_shipped_tree(self):
        files = walked_files()
        self.assertGreaterEqual(len(files), FILE_FLOOR)
        parsed = 0
        for path in files:
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            parsed += 1
        self.assertGreaterEqual(parsed, SCANNED_FLOOR)

    def test_the_walk_finds_a_planted_copy(self):
        offenders = planted_copy(PLANTED, PLANTED_TEXT)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("%s:%d" % (PLANTED, PLANTED_COPY_LINE)),
                        offenders[0])

    def test_the_walk_ignores_prose(self):
        self.assertEqual([], planted_copy(QUIET, QUIET_TEXT))

    def test_every_pin_names_a_live_line(self):
        for relative, lines in PINNED.items():
            if not lines:
                continue
            text = source_lines(relative)
            for line in lines:
                self.assertTrue(any(word in text[line - 1] for word in WORDS),
                                "%s:%d no longer spells a crop word" % (relative, line))

    def test_every_reader_reads_a_home_name(self):
        for relative in READERS:
            text = "\n".join(source_lines(relative))
            self.assertTrue(
                any(name in text for name in (FOLDER_FUNCTION, CTX_NAME, META_NAME, SETS_NAME)),
                "%s no longer reads the crop vocabulary of %s" % (relative, HOME))


if __name__ == "__main__":
    unittest.main()
