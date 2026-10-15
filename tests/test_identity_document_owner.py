"""The identity index document has one home: ``src/store_files.py``.

Round 113 walked the path ``out/identity/clusters.json`` and found it spelled at eight
code sites in seven modules.  Two of them looked like owners and did not own it together:
the row of the format map at ``src/store_files.py:110`` and ``JsonStore.identity_path``
at ``src/store.py:269``.  The other six:

* ``src/person_identity.py:75``, now :77  ``DEFAULT_PATH = ... / "out" / "identity" / "clusters.json"``
* ``src/person_pipeline.py:71``  ``IdentityIndex(self.root / 'out' / 'identity' / 'clusters.json', ...)``
* ``src/store_export.py:60``     ``texts["out/identity/clusters.json"] = dump(...)``
* ``src/store_export.py:80``     ``ROW_FILES = ("out/identity/clusters.json", FACE_STORE)``
* ``src/enroll_from_tracklet.py:1192`` ``CLUSTER_INDEX = Path("out") / "identity" / "clusters.json"``
* ``src/store_import.py:368``    ``raw = snap.json("out/identity/clusters.json")``

A rename of the document then needed one edit at each site, and a site that missed the
edit opened a second file.  The home is the module that already owns the format map and
the served document names::

    src/store_files.py:104: IDENTITY_DOCUMENT = "out/identity/clusters.json"
    src/store_files.py:110:     IDENTITY_DOCUMENT: INDENT1,     (the format-map row)
    src/store_files.py:259: def identity_document(root) -> Path

``identity_document`` keeps the caller's spelling of the root, the way
``JsonStore._faces_path`` joins ``FACE_STORE``: a repository root joins the whole
relative path, and a root that already ends in ``out`` joins the file name.

One live site spells the same path and is NOT this document's reader.  It stays, and
this guard pins it with its reason:

* ``src/eval_faces.py:96`` lists it in ``PROTECTED``, the one live list of the paths the
  demo must never write (``tests/test_protected_paths_owner.py`` reads that list).  The
  entry is a protected file name, not the path of the identity document.

Round 115 walked the same path again.  The rule above saw only a code constant EQUAL to
the whole path, so a site that joined the two parts of it in one expression was invisible:
``annotator/unified_server.py:1114`` spelled ``self.out / "identity" / "clusters.json"``
while ``identity_document(self.out)`` answered the same path.  That site now reads the
home, and the walk below has a second rule: any ``+`` or ``/`` expression whose string
parts carry both ``identity`` and ``clusters.json`` is a spelling of the document.  A site
that carries one part only -- ``src/eval_faces.py:748`` makes the ``out/identity`` folder
-- is no spelling of the document.  An f-string holds its literal parts as no such
expression, so a split spelling built in one stays outside this walk.

The walk below reads every python file of ``src/`` and ``annotator/``, skips ``src/sam3/``
and the byte-code trees, drops the string node of a module, class or function docstring,
and answers every code constant equal to the path, and every split spelling of it, that is
neither the home nor a pinned line.  Two floors keep a walk that read nothing from passing
in silence.

Run: ``./scripts/pool-test.sh python test_identity_document_owner``
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

from src.store_files import FORMATS, IDENTITY_DOCUMENT, identity_document  # noqa: E402
from _shipped import code_strings  # noqa: E402

#: The home module, the two names it owns, and the path they answer.
HOME = "src/store_files.py"
CONSTANT = "IDENTITY_DOCUMENT"
FUNCTION = "identity_document"
PATH = "out/identity/clusters.json"
#: The line of the format map that keys the path through the constant, pinned by number
#: and text.  The row moved once in this round and the number below moved with it.  The
#: format name is not spelled here: tests/test_store_files.py owns it, so this case builds
#: the text it expects and that guard keeps the one owner.
FORMAT_LINE = 110
FORMAT_FORM = "IDENTITY_DOCUMENT: " + "INDENT" + "1" + ","
#: The extra segments a caller's root carries before the owner's path.
REPO_PREFIX = "out/identity/clusters.json"
#: The sites this guard accepts, as the reason each one holds the path.
PINNED = {
    HOME: (),  # the home itself is the owner, never an offender
    "src/eval_faces.py": (96,),  # the PROTECTED list of the demo: a file name, not a path
}
#: The directories the walk reads, the subtree it skips, and the floors that keep a
#: vacuous walk from passing.
WALKED = ("src/**/*.py", "annotator/*.py")
SKIP = ("src/sam3",)
FILE_FLOOR = 200
SCANNED_FLOOR = 150
#: The modules that read the home instead of spelling the path, the last one the reader
#: round 115 moved off a split spelling.
READERS = ("src/store.py", "src/person_identity.py", "src/person_pipeline.py",
           "src/store_export.py", "src/enroll_from_tracklet.py", "src/store_import.py",
           "annotator/unified_server.py")
#: Planted modules of the honesty cases.
PLANTED = "src/planted_identity.py"
PLANTED_COPY_LINE = 6
PLANTED_TEXT = ('"""A planted module that names out/identity/clusters.json in its docstring."""\n'
                "\n"
                "\n"
                "def row():\n"
                '    """The docstring names the path in words, which is no code constant."""\n'
                '    return "%s"\n' % PATH)
QUIET = "src/quiet_identity.py"
QUIET_TEXT = ('"""A planted module that names out/identity/clusters.json in its docstring."""\n'
              "\n"
              "\n"
              "def row():\n"
              '    """The docstring names the path in words, which is no code constant."""\n'
              "    return 1\n")
#: The two parts a split spelling joins, and the planted modules of the honesty cases of
#: that rule.  The first joins both parts in one expression; the second carries the folder
#: alone, which is no spelling of the document.
PARTS = ("identity", "clusters.json")
SPLIT_PLANTED = "src/planted_split_identity.py"
SPLIT_COPY_LINE = 6
SPLIT_TEXT = ('"""A planted module that joins the two parts of the identity path."""\n'
              "\n"
              "\n"
              "def row(root):\n"
              '    """The docstring names out/identity/clusters.json in words, which is no expression."""\n'
              '    return Path(root) / "identity" / "clusters.json"\n')
QUIET_SPLIT = "src/quiet_split_identity.py"
QUIET_SPLIT_TEXT = ('"""A planted module that names the identity folder alone."""\n'
                    "\n"
                    "\n"
                    "def row(root):\n"
                    '    """The docstring names out/identity in words, which is no expression."""\n'
                    '    return Path(root) / "out" / "identity"\n')
#: The probe that reads the home in a fresh interpreter of this venv.
PROBE = ("from pathlib import Path; import src.store_files as module; "
         "print(module.%s); "
         "print(module.%s(Path('/repo'))); "
         "print(module.%s(Path('/tmp/t') / 'out'))" % (CONSTANT, FUNCTION, FUNCTION))


def source_lines(relative: str) -> list:
    """The lines of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8").splitlines()


def walked_files() -> list:
    """Every walked python file, the generated subtree left out."""
    found = sorted(path for pattern in WALKED for path in ROOT.glob(pattern)
                   if "__pycache__" not in path.parts
                   and not any(part in SKIP for part in path.relative_to(ROOT).parts))
    return found


def planted_copy(relative: str, text: str) -> list:
    """Write one planted module, run the walk, and remove it."""
    path = ROOT / relative
    path.write_text(text, encoding="utf-8")
    try:
        return analyze()
    finally:
        path.unlink()


def split_spellings(tree: ast.AST) -> list:
    """Every ``+`` or ``/`` expression of the tree that joins the two parts of the path."""
    sites = []
    seen = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, (ast.Add, ast.Div)):
            continue
        texts = [child.value for child in ast.walk(node)
                 if isinstance(child, ast.Constant) and isinstance(child.value, str)]
        if any(PARTS[0] in text for text in texts) and any(PARTS[1] in text for text in texts):
            if node.lineno in seen:
                continue
            seen.add(node.lineno)
            sites.append((node.lineno, ast.unparse(node)))
    return sites


def analyze() -> list:
    """Every walked spelling of the path that is neither the home nor a pin."""
    offenders = []
    for path in walked_files():
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, value in code_strings(tree):
            if value != PATH:
                continue
            if relative == HOME or line in PINNED.get(relative, ()):
                continue
            offenders.append("%s:%d: %r spells the identity document path; read %s.%s"
                             % (relative, line, value, HOME, CONSTANT))
        if relative == HOME:
            continue
        for line, text in split_spellings(tree):
            offenders.append("%s:%d: %s joins the two parts of the identity document path; "
                             "read %s.%s" % (relative, line, text, HOME, CONSTANT))
    return offenders


class HomeTests(unittest.TestCase):
    """The home holds the path, and a caller's root joins it."""

    def test_the_home_answers_the_path(self):
        answer = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.splitlines()
        self.assertEqual(answer[0], PATH)
        self.assertEqual(answer[1], "/repo/" + REPO_PREFIX)
        self.assertEqual(answer[2], "/tmp/t/" + REPO_PREFIX)

    def test_the_format_map_row_keys_the_constant(self):
        self.assertEqual(source_lines(HOME)[FORMAT_LINE - 1].strip(), FORMAT_FORM)
        self.assertLessEqual(FORMAT_LINE, 110, "the pinned lines of document_paths moved")

    def test_every_reader_reads_the_home(self):
        for relative in READERS:
            text = "\n".join(source_lines(relative))
            self.assertTrue(CONSTANT in text or FUNCTION in text,
                            "%s no longer reads the identity document of %s" % (relative, HOME))


class WalkTests(unittest.TestCase):
    """The walk names every copy that is no home and no pin."""

    def test_no_file_spells_the_path(self):
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

    def test_the_walk_finds_a_planted_split_copy(self):
        offenders = planted_copy(SPLIT_PLANTED, SPLIT_TEXT)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("%s:%d" % (SPLIT_PLANTED, SPLIT_COPY_LINE)),
                        offenders[0])
        self.assertIn("joins the two parts", offenders[0])

    def test_the_walk_ignores_a_folder_alone(self):
        self.assertEqual([], planted_copy(QUIET_SPLIT, QUIET_SPLIT_TEXT))

    def test_every_pin_names_a_live_line(self):
        for relative, lines in PINNED.items():
            if not lines:
                continue
            text = source_lines(relative)
            for line in lines:
                self.assertIn(PATH, text[line - 1],
                              "%s:%d no longer spells the identity document path" % (relative, line))


if __name__ == "__main__":
    unittest.main()
