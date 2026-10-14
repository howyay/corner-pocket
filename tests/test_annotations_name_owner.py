"""One home of the three document names of the store layer, and no second spelling.

The store layer gives three documents a file name: the verdicts file of a dataset
(``annotations.json``), the labels file of a crop set (``labels.json``) and the
correction file of one frame (``correction.json``).  Round 109 measured the spellings
of those names in live code: eleven sites in five files of the store layer, and none
of them read a home.

The home already existed.  ``src/store_files.py`` holds the map that answers which
files a document-backed set consists of, and its three branches build the three file
names::

    src/store_files.py:201  return f"{folder}/frame_results/{'*' if frame == '*' else int(frame)}/correction.json"
    src/store_files.py:213  return [f"{folder}/annotations.json" for folder in dirs]
    src/store_files.py:205  return [f"out/{crop_set}/labels.json" for crop_set in BALL_SETS]

Round 109 put no second constant beside those lines.  It added two readers of the map
to the same module.  ``document_name(set_name)`` answers the file name of every set,
and ``correction_path(folder, frame)`` answers the path of one correction document
(``frame`` is the index, or ``"*"`` for the discovery above), so the discovery and
both stores share one spelling of the frame folder as well as of the file name.

Every reader keeps its value byte-identical: a document on disk already carries those
three names, and a reader must still find it.  The case below pins each answer, so a
rename that moves one file and not the others reddens this module.

The walk reads 285 python files under ``src/`` and ``annotator/``.  The eleven reader
sites hold no name any more, so the walk finds three code sites, all in the home
module.  Seven further files spell a name as part of another fact - a fixed path of
one dataset, or the name of an argument of a labeller tool - and the table below
records each one with its reason.  The walk reads every one of those files, so a new
spelling of any of the three names in any live module reddens this module, and the
report names ``path:line`` with the text of that line.

Run: ``./scripts/pool-test.sh python test_annotations_name_owner``

Measured 2026-10-14, Python 3.14.6: the walk reads 285 python files in about 1 s.
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.store_files import correction_path, document_name, document_paths  # noqa: E402

#: The home module of the three names.
HOME = "src/store_files.py"
#: The dotted name of the home, as an import names it.
MODULE = "src.store_files"
#: The three set names and the file name each one must answer.  The anchors document
#: carries the dataset id in its name, so it has no one name and it is not here.
NAMES = {"verdicts": "annotations.json", "labels": "labels.json",
         "corrections": "correction.json"}
#: The form of one read of the home, per set.  A reader names the set; it never
#: spells the file name.
READ_FORMS = {
    "verdicts": ('document_name("verdicts")', "document_name('verdicts')"),
    "labels": ('document_name("labels")', "document_name('labels')"),
    "corrections": ('document_name("corrections")', "document_name('corrections')",
                    "correction_path("),
}
#: Every live site of the fact, as ``(line, kind)`` per module.  The kind is
#: ``home:<set>`` for the branch of the map that holds that name, and the name of the
#: set for a site that reads the home.  A moved, a new or a lost site must restate
#: itself here.
SITES = {
    HOME: ((191, "home:corrections"), (203, "home:verdicts"), (205, "home:labels")),
    "src/store.py": ((327, "verdicts"), (330, "verdicts"), (343, "labels"),
                     (364, "corrections")),
    "src/store_pg.py": ((70, "verdicts"), (72, "labels"), (389, "corrections")),
    "src/store_check.py": ((61, "verdicts"), (65, "corrections"), (69, "labels")),
    "src/store_import.py": ((540, "verdicts"), (541, "verdicts"), (572, "labels"),
                            (600, "corrections"), (719, "verdicts")),
    "annotator/server.py": ((44, "verdicts"), (49, "labels")),
}
#: The names each reader takes from the home, and the line of that import.
IMPORTS = {
    "src/store.py": (66, ("correction_path", "document_name")),
    "src/store_pg.py": (41, ("correction_path", "document_name")),
    "src/store_check.py": (29, ("document_name",)),
    "src/store_import.py": (49, ("correction_path", "document_name")),
    "annotator/server.py": (40, ("document_name",)),
}
#: The files that spell one of the three names as part of another fact, with the
#: measurement behind each entry.  An entry that stops matching a live site fails the
#: walk: the table may not outlive the fact it records.
OTHER_FACTS = {
    "src/confusion.py": "a labeller tool with a labels_dir argument: the name belongs to the argument",
    "src/dense_queue.py": "the eval queue names one dataset's verdicts file by its full path",
    "src/eval_events.py": "the eval tool names one dataset's verdicts file by its full path",
    "src/eval_faces.py": "the eval tool names one dataset's verdicts file by its full path",
    "src/merge_sets.py": "a labeller tool with a crop directory argument: the name belongs to the argument",
    "src/sam3/sam3/eval/saco_veval_evaluators.py": "the vendored SAM3 evaluator reads a COCO ground-truth annotations.json",
    "src/train_ball_id.py": "a labeller tool with a labels_dir argument: the name belongs to the argument",
}
#: The directories the anti-copy walk reads, and the floor that keeps a vacuous walk
#: from passing.
PY_WALKED = ("src/**/*.py", "annotator/**/*.py")
PY_FILE_FLOOR = 100
#: The number of code sites the home module holds.
HOME_SITE_COUNT = 3


def source_text(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list[str]:
    """The lines of one file of this repository."""
    return source_text(relative).splitlines()


def report(relative: str, number: int, line: str, why: str) -> str:
    """The message of one site: the path, the line, the text, and the reason."""
    return f"{relative}:{number}: {line.strip()}\n  {why}"


def docstring_lines(text: str) -> set[int]:
    """The lines of every docstring of one module.  Prose is not a code site."""
    found: set[int] = set()
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found.update(range(value.lineno, (value.end_lineno or value.lineno) + 1))
    return found


def name_sites(relative: str, text: str | None = None) -> list[str]:
    """The code sites of one file that spell one of the three document file names.

    A site is a string fragment whose last path segment is one of the names: the bare
    name, the tail of a joined path, or the name inside a full path of one dataset.
    A docstring may name a file: prose keeps the history of a patch, and it does not
    read the name.
    """
    body = text if text is not None else source_text(relative)
    prose = docstring_lines(body)
    lines = body.splitlines()
    found = []
    for node in ast.walk(ast.parse(body)):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value.rsplit("/", 1)[-1] not in NAMES.values() or node.lineno in prose:
            continue
        why = (f'the file name stands as "{node.value}" in place of the home of the set '
               f"names in {HOME}; read {MODULE}.document_name")
        found.append(report(relative, node.lineno, lines[node.lineno - 1], why))
    return found


def home_sites() -> list[str]:
    """Every code site of the home module, with the reason of the walk."""
    return name_sites(HOME)


def imported_names(relative: str) -> tuple[set[str], int]:
    """The names one reader takes from the home module, and the line of that import."""
    names: set[str] = set()
    number = 0
    for node in ast.walk(ast.parse(source_text(relative))):
        if isinstance(node, ast.ImportFrom) and node.module == MODULE:
            number = node.lineno
            names.update(alias.name for alias in node.names)
    return names, number


def walked() -> list[Path]:
    """Every live python file the anti-copy walk reads."""
    return [path for pattern in PY_WALKED for path in sorted(ROOT.glob(pattern))
            if "__pycache__" not in path.parts]


class AnnotationsNameOwner(unittest.TestCase):
    """One home of the three document names, and no second spelling."""

    def test_the_home_lines_hold_the_three_file_names(self):
        lines = source_lines(HOME)
        for number, kind in SITES[HOME]:
            set_name = kind.split(":", 1)[1]
            with self.subTest(set_name=set_name):
                line = lines[number - 1]
                self.assertIn(NAMES[set_name], line,
                              f"{HOME}:{number} must hold the home of the {set_name} "
                              f"document: {line.strip()!r}")

    def test_the_home_answers_the_three_file_names(self):
        for set_name, file_name in NAMES.items():
            with self.subTest(set_name=set_name):
                self.assertEqual(file_name, document_name(set_name),
                                 f"{MODULE}.document_name must answer the {set_name} file name")
        for set_name in ("operations", "seeds", "verdicts", "labels"):
            with self.subTest(set_name=set_name):
                paths = document_paths(set_name)
                self.assertTrue(paths, f"the map must answer a path for {set_name}")
                for path in paths:
                    self.assertTrue(path.endswith(document_name(set_name)),
                                    f"{path} must end with {document_name(set_name)}")
        with self.assertRaises(ValueError):
            document_name("anchors")   # the anchors name carries the dataset id
        for path in document_paths("corrections", ROOT):
            self.assertTrue(path.endswith(document_name("corrections")),
                            f"{path} must end with {document_name('corrections')}")
        self.assertEqual("out/scan30/frame_results/7/correction.json",
                         correction_path("out/scan30", 7),
                         "the frame index must spell the path the two stores spelled")
        self.assertEqual("out/scan30/frame_results/*/correction.json",
                         correction_path("out/scan30", "*"),
                         "the wildcard must spell the path the discovery globs")

    def test_every_reader_site_reads_the_home(self):
        for relative, sites in SITES.items():
            lines = source_lines(relative)
            for number, kind in sites:
                if kind.startswith("home:"):
                    continue           # the home lines have their own case
                with self.subTest(reader=relative, line=number):
                    line = lines[number - 1].strip()
                    self.assertTrue(any(form in line for form in READ_FORMS[kind]),
                                    f"{relative}:{number} must read the home of the "
                                    f"{kind} document: {line!r}")

    def test_every_reader_takes_the_binding_from_the_home(self):
        for relative, (number, names) in IMPORTS.items():
            with self.subTest(reader=relative):
                taken, line = imported_names(relative)
                text = source_lines(relative)[line - 1].strip()
                self.assertEqual(number, line,
                                 f"{relative}:{number} must hold the import of the home: {text!r}")
                for name in names:
                    self.assertIn(name, taken,
                                  f"{relative}:{line} must take {name} from {MODULE}: {text!r}")

    def test_the_walk_finds_one_home_and_no_second_spelling(self):
        files = walked()
        self.assertGreaterEqual(len(files), PY_FILE_FLOOR,
                                f"the walk must read the live tree: {len(files)} files")
        found: dict[str, list[str]] = {}
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            sites = name_sites(relative)
            if sites:
                found[relative] = sites
        inside = sorted(found.get(HOME, []))
        self.assertEqual(HOME_SITE_COUNT, len(inside),
                         "the home module must hold three code sites:\n" + "\n".join(inside))
        offenders = {relative: sites for relative, sites in found.items()
                     if relative != HOME and relative not in OTHER_FACTS}
        self.assertEqual({}, offenders,
                         "one module may spell these file names: " + HOME
                         + "; every other site is a second home:\n"
                         + "\n".join(site for sites in offenders.values() for site in sites))
        for relative in OTHER_FACTS:
            with self.subTest(other_fact=relative):
                self.assertTrue(found.get(relative),
                                f"{relative} no longer spells a name as its recorded "
                                f"other fact; drop the entry ({OTHER_FACTS[relative]})")

    def test_a_planted_name_is_reported_with_its_file_and_line(self):
        relative = "src/store.py"
        original = source_text(relative)
        current = 'document_name("verdicts")'
        self.assertTrue(current in original, f"the live reader must hold {current}")
        planted_text = original.replace(current, '"%s"' % NAMES["verdicts"])
        self.assertTrue(planted_text != original, "the plant must change the text")
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_store.py"
            planted.write_text(planted_text, encoding="utf-8")
            found = name_sites(str(planted), planted_text)
        self.assertEqual(2, len(found), found)
        for site in found:
            self.assertTrue(site.startswith(f"{planted}:"), site)
            self.assertIn(NAMES["verdicts"], site)
            self.assertIn(document_name("verdicts"), site)
            self.assertIn("read src.store_files.document_name", site)


if __name__ == "__main__":
    unittest.main()
