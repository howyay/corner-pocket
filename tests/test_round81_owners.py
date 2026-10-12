"""Round 81 owners: three facts stood twice, and each reader reads its owner now.

Round 81 measured three duplications, each one a fact with two homes:

1. The ``json_documents`` probe stood twice: as ``has_documents_table`` in
   ``src/store_files.py`` and inline in the ``main`` of ``src/store_check.py``.  A
   change to the owner's question left the check tool asking the old one, in
   silence.  The five ``to_regclass`` sites of ``src/`` ask three different
   questions: the migrations journal (``src/db.py``), the operations log
   (``src/store_import.py``) and the export probe (``src/store_export.py``) are
   other facts and they stay.
2. The measurement artifact path ``out/calib_vod30_segments.measure.json`` stood
   twice, as the write default of ``src/calib_segment_measure.py`` and as the read
   default of ``src/calib_segment_fit.py``.  ``MEASURE_ARTIFACT`` of the writer is
   the one home now; the fit tool imports it.
3. The three pretrained weight names stood in the model loop of
   ``src/train_ball_id.py``, and ``ResNet18_Weights.IMAGENET1K_V1`` stood a second
   time at ``src/confusion.py:38``, where no test pinned it.  The ``WEIGHTS``
   mapping of ``src/train_ball_id.py`` is the one home now; the confusion script
   reads it.

The cases read four different things on purpose:

1. the code strings of the shipped packages (``tests/_shipped.py``), so a module
   that spells one of the three facts again fails this module;
2. the import every reader writes, so a reader that stops reading the owner fails
   this module;
3. the owner's own behavior - the probe asks its one question, the mapping names
   real torchvision weights - so a wrong owner is visible;
4. a planted copy in a temporary tree, so the walk of point 1 cannot pass in
   silence.

The three facts stay literals below.  A case that states a fact by importing its
owner would agree with a wrong owner, so each literal is an independent statement.

This module reads source text and imports the owner modules.  It does not read a
database, does not train a model, and does not run the two calibration tools.

Run: ``./scripts/pool-test.sh python test_round81_owners``
"""
from __future__ import annotations

import ast
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from _shipped import bindings, code_strings, shipped_modules  # noqa: E402

#: Row 1: the owner of the probe, the name it binds, its reader, and the question.
PROBE_OWNER = "src/store_files.py"
PROBE_NAME = "has_documents_table"
PROBE_READER = "src/store_check.py"
PROBE = "SELECT to_regclass('json_documents')"

#: Row 2: the owner of the artifact path, its name, its reader, and the file name.
ARTIFACT_OWNER = "src/calib_segment_measure.py"
ARTIFACT_NAME = "MEASURE_ARTIFACT"
ARTIFACT_READER = "src/calib_segment_fit.py"
ARTIFACT_FILE = "calib_vod30_segments.measure.json"

#: Row 3: the owner of the weight names, its mapping, its reader, and the names.
WEIGHT_OWNER = "src/train_ball_id.py"
WEIGHT_MAP = "WEIGHTS"
WEIGHT_READER = "src/confusion.py"
WEIGHT_NAMES = ("MobileNet_V3_Small_Weights.IMAGENET1K_V1",
                "SqueezeNet1_0_Weights.IMAGENET1K_V1",
                "ResNet18_Weights.IMAGENET1K_V1")


def relative(path) -> str:
    """One path, as the repository reports it: under the root, without the root."""
    return str(path).replace(str(ROOT) + "/", "")


def code_sites(value: str, paths=None) -> list[str]:
    """``src/x.py:line`` for every shipped code string equal to ``value``.

    ``code_strings`` of tests/_shipped.py drops the docstrings, so a module may
    name one of the three facts in words without failing this walk.  ``paths``
    overrides the shipped tree, which is how the planted copy below is read.
    """
    sites = []
    for path in (shipped_modules() if paths is None else paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for number, text in code_strings(tree):
            if text == value:
                sites.append(f"{relative(path)}:{number}")
    return sorted(sites)


def files_of(sites) -> list[str]:
    """The file of every site, one entry per site, in the order of the sites."""
    return [site.split(":")[0] for site in sites]


def names_of(path) -> set:
    """Every name one module declares at its top level, functions and bindings.

    ``bindings`` of tests/_shipped.py reads the assignments; the owner of row 1
    binds a function, so the walk here adds the definitions of the module body.
    """
    names = {name for _, name, _ in bindings(path)}
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    names.update(node.name for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    return names


def imports_from(path, module: str, name: str) -> bool:
    """True when one module takes ``name`` from ``module`` by a ``from`` import."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    return any(isinstance(node, ast.ImportFrom) and node.module == module
               and any(alias.name == name for alias in node.names)
               for node in ast.walk(tree))


def names_read(path, name: str) -> int:
    """How many times one module reads ``name`` as a plain name."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    return sum(1 for node in ast.walk(tree)
               if isinstance(node, ast.Name) and node.id == name)


class _ProbeConn:
    """A connection whose one answer to any statement is a row of ``None``.

    ``to_regclass`` of a missing table answers ``NULL``, so this fake is the
    missing-table case of the probe and nothing else.  It records the statements
    it was asked, so a case can read the question.
    """

    def __init__(self, row=(None,)):
        self.asked = []
        self.row = row

    def execute(self, sql, params=None):
        self.asked.append(sql)
        return self

    def fetchone(self):
        return self.row


class Round81OwnersTest(unittest.TestCase):
    """One case family per row, plus the walk that shows each row can fail."""

    def test_the_probe_stands_once_in_the_store_files_owner(self):
        sites = code_sites(PROBE)
        self.assertEqual(files_of(sites), [PROBE_OWNER],
                         "the json_documents probe must stand once, in %s; found %s"
                         % (PROBE_OWNER, sites))
        self.assertIn(PROBE_NAME, names_of(ROOT / PROBE_OWNER),
                      "%s must bind %s" % (PROBE_OWNER, PROBE_NAME))

    def test_the_check_tool_reads_the_probe_owner(self):
        reader = ROOT / PROBE_READER
        self.assertTrue(imports_from(reader, "src.store_files", PROBE_NAME),
                        "%s must import %s from src.store_files" % (PROBE_READER, PROBE_NAME))
        self.assertGreater(names_read(reader, PROBE_NAME), 0,
                           "%s must read %s, not import it alone" % (PROBE_READER, PROBE_NAME))

    def test_the_probe_asks_the_question_the_owner_holds(self):
        from src.store_files import has_documents_table

        conn = _ProbeConn()
        self.assertFalse(has_documents_table(conn))
        self.assertEqual(conn.asked, [PROBE],
                         "the probe must ask the one question this row names")

    def test_the_check_tool_stops_on_a_missing_documents_table(self):
        from src import store_check

        conn = _ProbeConn()

        @contextlib.contextmanager
        def connect():
            yield conn

        stderr = io.StringIO()
        with mock.patch.object(store_check.db, "connect", connect):
            with mock.patch.object(store_check, "check") as projection:
                with contextlib.redirect_stderr(stderr):
                    code = store_check.main([])
        self.assertEqual(code, 2, "a missing json_documents table must stop the tool")
        self.assertEqual(conn.asked, [PROBE],
                         "the tool must ask the probe of %s" % PROBE_OWNER)
        projection.assert_not_called()
        self.assertIn("json_documents does not exist", stderr.getvalue())

    def test_the_artifact_file_name_stands_once_in_the_measure_tool(self):
        sites = code_sites(ARTIFACT_FILE)
        self.assertEqual(files_of(sites), [ARTIFACT_OWNER],
                         "the measurement artifact path must stand once, in %s; found %s"
                         % (ARTIFACT_OWNER, sites))
        self.assertIn(ARTIFACT_NAME, names_of(ROOT / ARTIFACT_OWNER),
                      "%s must bind %s" % (ARTIFACT_OWNER, ARTIFACT_NAME))

    def test_the_fit_tool_reads_the_artifact_owner(self):
        reader = ROOT / ARTIFACT_READER
        self.assertTrue(imports_from(reader, "src.calib_segment_measure", ARTIFACT_NAME),
                        "%s must import %s from src.calib_segment_measure"
                        % (ARTIFACT_READER, ARTIFACT_NAME))
        self.assertGreater(names_read(reader, ARTIFACT_NAME), 0,
                           "%s must read %s, not import it alone"
                           % (ARTIFACT_READER, ARTIFACT_NAME))

    def test_the_fit_tool_reads_the_owner_value(self):
        from src import calib_segment_fit, calib_segment_measure

        self.assertIs(calib_segment_fit.MEASURE_ARTIFACT,
                      calib_segment_measure.MEASURE_ARTIFACT,
                      "one value, read by both tools, and not a second path")

    def test_the_weight_names_stand_once_in_train_ball_id(self):
        for name in WEIGHT_NAMES:
            sites = code_sites(name)
            self.assertEqual(files_of(sites), [WEIGHT_OWNER],
                             "%s must stand once, in %s; found %s"
                             % (name, WEIGHT_OWNER, sites))
        self.assertIn(WEIGHT_MAP, names_of(ROOT / WEIGHT_OWNER),
                      "%s must bind %s" % (WEIGHT_OWNER, WEIGHT_MAP))

    def test_the_confusion_script_reads_the_weight_mapping(self):
        reader = ROOT / WEIGHT_READER
        self.assertTrue(imports_from(reader, "train_ball_id", WEIGHT_MAP),
                        "%s must import %s from train_ball_id" % (WEIGHT_READER, WEIGHT_MAP))
        self.assertGreater(names_read(reader, WEIGHT_MAP), 0,
                           "%s must read %s, not import it alone" % (WEIGHT_READER, WEIGHT_MAP))

    def test_the_weight_mapping_names_real_torchvision_weights(self):
        import torchvision

        from src.train_ball_id import WEIGHTS

        self.assertEqual(sorted(WEIGHTS.values()), sorted(WEIGHT_NAMES),
                         "the mapping must hold exactly the three names of this row")
        for backbone, name in sorted(WEIGHTS.items()):
            weight = torchvision.models.get_weight(name)
            self.assertEqual(str(weight), name,
                             "%s must name a real torchvision weight: %s" % (backbone, name))

    def test_the_walk_reports_planted_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "planted.py"
            path.write_text("A = %r\nB = %r\nC = %r\n"
                            % (PROBE, ARTIFACT_FILE, WEIGHT_NAMES[-1]), encoding="utf-8")
            self.assertEqual(code_sites(PROBE, [path]), [f"{relative(path)}:1"])
            self.assertEqual(code_sites(ARTIFACT_FILE, [path]), [f"{relative(path)}:2"])
            self.assertEqual(code_sites(WEIGHT_NAMES[-1], [path]), [f"{relative(path)}:3"])


if __name__ == "__main__":
    unittest.main()
