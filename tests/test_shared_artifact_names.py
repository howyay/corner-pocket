"""The four artifact file names of the out/ root have one owner.

Round 84 found the names in two kinds of place.  The map `SHARED_ARTIFACTS` of
``src/store.py`` held three of them, and `JsonStore.artifact()` read that map.  The
other readers spelled a name again, one method away from the store: the two store
layers and the served readers of ``annotator/unified_server.py``.  The fourth name,
``pid2_tracklets.json``, stood in ``src/store.py`` and in the server and in no map.
Neither store layer refused the kind, so a rename split a reader from the writer.

Four names have one home now: `SHARED_ARTIFACTS`, `TRACKLETS_NAME` and the tuple
`SHARED_ARTIFACT_NAMES` of ``src/store.py``.

The walk below reads the two store layers, the served readers of
``annotator/unified_server.py``, and the five modules that take a name of the
out/ root: ``src/pid_associate.py``, ``src/yolo_track.py``,
``src/pid_seed_rebuild.py``, ``src/pid_osnet_tight.py`` and
``src/pid_osnet_tracks.py``.  Each of the five held one name or more as a string
literal.

The cases below hold four facts:

1. the owner answers exactly four names, and each name is a plain JSON file name;
2. no reader of ``READERS`` spells one of the four names as a string literal again.
   The walk reads source with ``ast``, so it sees a literal and not a sentence, and
   it names the site ``file:line``;
3. a planted copy answers its own site, so case 2 cannot pass in silence;
4. every reader of ``READERS`` reads the owner, so the walk cannot hold a module
   that cannot read it.

One limit holds: a reader that cannot import the owner stays out of ``READERS``.  A
producer of the files, for example ``src/pid_shooter.py``, is not a reader.

Run: ``./scripts/pool-test.sh python test_shared_artifact_names``
"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.store import SHARED_ARTIFACT_NAMES  # noqa: E402

#: The owner module of the four names, as a path under the repository root.
OWNER = "src/store.py"

#: The two store layers and the served readers.  A name stands in the owner alone.
READERS = (
    # the two store layers and the served readers
    "src/store_pg.py",
    "annotator/unified_server.py",
    # the modules that took a name of the out/ root.  Each one reads src/store.py,
    # so the walk below may hold it (see the case ``test_every_reader_reads_the_owner``).
    "src/pid_associate.py",
    "src/yolo_track.py",
    "src/pid_seed_rebuild.py",
    "src/pid_osnet_tight.py",
    "src/pid_osnet_tracks.py",
)

#: The number of sibling files at the out/ root.  A test states this fact on
#: purpose, so the case cannot agree with a short map by reading the map alone.
NAME_COUNT = 4


def spelled_strings(path: Path) -> list[tuple[int, str]]:
    """The (line, text) of every string literal of one module, docstrings dropped.

    A docstring describes a file.  It is not a name a reader reads, so the walk
    below leaves it out.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            docstrings.add(id(body[0].value))
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def spelling_sites(paths, names=SHARED_ARTIFACT_NAMES) -> list[str]:
    """One `path:line quotes name` entry for every literal that spells one name."""
    entries = []
    for path in paths:
        for number, value in spelled_strings(path):
            if value in names:
                entries.append(f"{path}:{number} quotes {value}")
    return sorted(entries)


def reader_sites() -> list[str]:
    """The same entries over the two store layers and the served readers."""
    return spelling_sites([ROOT / relative for relative in READERS])


def owner_imports(path: Path, owner=OWNER) -> list[str]:
    """One `path:line imports name` entry for every name `path` reads from the owner.

    A reader that cannot read the owner cannot hold a name of the out/ root.  The walk
    reads the syntax tree, so an import inside a function counts as one site.
    """
    module = owner[: -len(".py")].replace("/", ".")
    entries = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                entries.append(f"{path}:{node.lineno} imports {alias.name}")
    return entries


class SharedArtifactNames(unittest.TestCase):
    """One home for the four names, and no second spelling in a reader."""

    def test_the_owner_answers_four_plain_json_names(self):
        names = tuple(SHARED_ARTIFACT_NAMES)
        self.assertEqual(len(names), NAME_COUNT,
                         f"{OWNER}: the map must hold the {NAME_COUNT} names of the out/ root")
        self.assertEqual(len(set(names)), NAME_COUNT,
                         f"{OWNER}: two rows of the map must not name one file: {names}")
        for name in names:
            self.assertTrue(name.endswith(".json"), f"{OWNER}: {name} must name a JSON file")
            self.assertNotIn("/", name, f"{OWNER}: {name} must be a bare name at the out/ root")

    def test_no_reader_spells_one_of_the_four_names(self):
        sites = reader_sites()
        self.assertEqual(sites, [],
                         f"a name of the out/ root has one owner, {OWNER}; "
                         "read SHARED_ARTIFACT_NAMES or TRACKLETS_NAME from it: "
                         + "; ".join(sites))

    def test_every_reader_reads_the_owner(self):
        """A reader list holds no module that cannot read the owner, so no case is idle."""
        for relative in READERS:
            with self.subTest(reader=relative):
                self.assertTrue(owner_imports(ROOT / relative),
                                f"{relative} names a file of the out/ root and does not "
                                f"read {OWNER}; it could hold its own copy of the name")

    def test_the_walk_reports_a_planted_copy(self):
        """A copy must answer its own site, so the case above cannot pass in silence."""
        name = SHARED_ARTIFACT_NAMES[-1]
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_reader.py"
            planted.write_text(f'NAME = "{name}"\n', encoding="utf-8")
            self.assertEqual(spelling_sites([planted]), [f"{planted}:1 quotes {name}"],
                             "the walk must name the line of a planted copy")

    def test_a_short_map_fails_the_count(self):
        """A map of three names must fail the count, so the case above reads a fact."""
        three = tuple(SHARED_ARTIFACT_NAMES[:3])
        self.assertNotEqual(len(three), NAME_COUNT,
                            "a map of three names must not answer the four names")
        self.assertEqual(len(SHARED_ARTIFACT_NAMES), NAME_COUNT,
                         f"{OWNER}: the owner must hold the fourth name too")


if __name__ == "__main__":
    unittest.main()
