"""The rule of the verified cloth quad has one owner, and this module holds it there.

The rule answers one question: which quad is the cloth of this dataset?

    the human calibration segment of the dataset
    then the hand anchors of that dataset
    then the scan corners

Two modules answered that question before this guard existed, and they disagreed.
``src/sam3_frame_audit.py`` read its anchor file from a signature default that
froze ``vod30``, so a foreign dataset received the vod30 anchors.
``src/sam3_ball_cache.py`` derived ``out/pid_anchors_<dataset>.json`` from its
parameter.  For ``dataset="tw-1234567"`` the audit answered from the vod30
anchors while the cache answered from the scan corners.

The owner is ``src.calib_segments.verified_cloth_quad``.  Both callers ask the
owner, and no module under ``src/`` answers the rule for itself.

The checks here read three different things on purpose:

1. the answer of both entry points on one real dataset, which is the behavior;
2. the source text, so a second home of the rule cannot appear in silence;
3. the abstract syntax tree, so a default argument cannot freeze one dataset.

Do not weaken a check to make a change pass.  Move the rule, or delete the second
answer, and keep this module green.
"""
import ast
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import numpy as np  # noqa: E402

import data_guard  # noqa: E402
from src import calib_segments as cs  # noqa: E402
from src.sam3_ball_cache import reference_quad as cache_reference_quad  # noqa: E402
from src.sam3_frame_audit import reference_quad as audit_reference_quad  # noqa: E402

OWNER = ROOT / "src" / "calib_segments.py"
FAMILY = ROOT / "src" / "sam3_"
FOREIGN_DATASET = "tw-1234567"
VOD30_ANCHORS = ROOT / "out" / "pid_anchors_vod30.json"
ATOL = 1e-3

# A parser reads a docstring as an expression statement, not as a constant with a
# value, so a comment about the rule is not a second home of the rule.  Only code
# is a home.
RULE_TEXT = "verified_cloth_quad"
ANCHOR_TEXT = "pid_anchors"
CALLER_FILES = (ROOT / "src" / "sam3_frame_audit.py", ROOT / "src" / "sam3_ball_cache.py")


def callers():
    """The two entry points, with the module name for a report."""
    return (("sam3_frame_audit", audit_reference_quad),
            ("sam3_ball_cache", cache_reference_quad))


def answer(quad):
    """The quad of an entry point, also when the answer carries a label."""
    return quad[0] if isinstance(quad, tuple) else quad


def freeze_offenders(paths):
    """Every line that names the vod30 anchors.  The old shape of the defect."""
    offenders = []
    for path in paths:
        for number, line in enumerate(Path(path).read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if f"{ANCHOR_TEXT}_vod30" in line:
                offenders.append(f"{Path(path).name}:{number}: {line.strip()}")
    return offenders


def rule_offenders(paths):
    """Every line that names the rule outside a call of the owner."""
    offenders = []
    for path in paths:
        for number, line in enumerate(Path(path).read_text().splitlines(), 1):
            if line.lstrip().startswith("#") or RULE_TEXT not in line:
                continue
            if "calib_segments." in line:
                continue
            offenders.append(f"{Path(path).name}:{number}: {line.strip()}")
    return offenders


class ClothQuadOwnerTests(unittest.TestCase):
    def test_the_owner_module_answers_the_rule(self):
        reference = cs.verified_cloth_quad("vod30")
        self.assertTrue(reference.found)
        self.assertEqual(reference.kind, "human_segment")
        self.assertIsNotNone(reference.quad)
        self.assertEqual(np.asarray(reference.quad).shape, (4, 2))

    def test_both_callers_give_one_answer_on_a_foreign_dataset(self):
        """The regression: the two owners disagreed for dataset=tw-1234567."""
        audit = answer(audit_reference_quad(dataset=FOREIGN_DATASET))
        cache = answer(cache_reference_quad(dataset=FOREIGN_DATASET))
        if cache is None or audit is None:
            self.assertIsNone(cache)
            self.assertIsNone(audit)
            return
        self.assertTrue(np.allclose(audit, cache, atol=ATOL),
                        "the frame audit and the ball cache disagree on the cloth quad")

    def test_a_foreign_dataset_does_not_receive_the_vod30_anchors(self):
        data_guard.require(VOD30_ANCHORS)
        store = json.loads(VOD30_ANCHORS.read_text())
        vod30_quad = np.asarray(next(iter(store["anchors"].values()))[:4], np.float32)
        for name, value in callers():
            with self.subTest(caller=name):
                quad = answer(value(dataset=FOREIGN_DATASET))
                if quad is None:
                    continue
                self.assertFalse(np.allclose(np.asarray(quad, np.float32), vod30_quad, atol=ATOL),
                                 f"{name} answered with the vod30 hand anchors")

    def test_the_anchor_file_name_comes_from_the_dataset(self):
        with self.subTest(step="the owner derives the name of the file"):
            derived = cs.verified_cloth_quad("vod30")
            self.assertIn("vod30", str(derived.origin))
        with self.subTest(step="a foreign dataset never reads the vod30 file"):
            foreign = cs.verified_cloth_quad(FOREIGN_DATASET)
            if foreign.found:
                self.assertNotIn("vod30", str(foreign.origin))

    def test_no_caller_freezes_the_vod30_anchors(self):
        """The old shape: a default argument that reads the anchors of one dataset."""
        self.assertEqual(
            freeze_offenders(CALLER_FILES), [],
            "a default freezes the vod30 anchors for every dataset: "
            + ", ".join(freeze_offenders(CALLER_FILES)))

    def test_no_caller_names_the_rule_alone(self):
        """A caller may say the name of the rule only as a call of the owner."""
        self.assertEqual(
            rule_offenders(CALLER_FILES), [],
            "a second home for the cloth-quad rule: " + ", ".join(rule_offenders(CALLER_FILES)))

    def test_the_scan_sees_a_planted_copy(self):
        """Both scans must catch the shape they exist for, so their silence means something.

        The copy is a temp file, so the working tree stays as it is.
        """
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "planted.py"
            with self.subTest(planted="a default that reads the vod30 anchors"):
                path.write_text('def reference_quad(dataset="vod30",\n'
                                '                  anchors_path="out/pid_anchors_vod30.json"):\n'
                                '    return dataset\n')
                found = freeze_offenders([path])
                self.assertEqual(len(found), 1, f"the scan did not see {path}: {found}")
                self.assertIn("pid_anchors_vod30", found[0])
            with self.subTest(planted="a second statement of the rule"):
                path.write_text('def answer(dataset):\n'
                                '    return verified_cloth_quad(dataset)\n')
                found = rule_offenders([path])
                self.assertEqual(len(found), 1, f"the scan did not see {path}: {found}")
                self.assertIn("verified_cloth_quad", found[0])
            with self.subTest(planted="the owner is not a caller"):
                path.write_text('quad = calib_segments.verified_cloth_quad(dataset)\n')
                self.assertEqual(rule_offenders([path]), [],
                                 "a call of the owner is not a second home")

    def test_no_module_takes_a_scan_corners_default(self):
        """A default of one scan directory freezes the geometry of one dataset."""
        offenders = []
        for path in sorted(FAMILY.glob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef) or not node.args.defaults:
                    continue
                names = [argument.arg for argument in node.args.args[-len(node.args.defaults):]]
                for argument, default in zip(names, node.args.defaults):
                    if argument != "corners_path":
                        continue
                    text = ast.unparse(default)
                    if "scan" in text:
                        offenders.append(f"{path.name}:{node.lineno}: "
                                         f"{node.name}({argument}={text})")
        self.assertEqual(
            offenders, [],
            "a signature default freezes the scan corners of one dataset: " + ", ".join(offenders))

    def test_no_module_takes_an_anchor_name_with_a_dataset(self):
        """An anchor name that a dataset parameter selects is a second home."""
        offenders = []
        for path in sorted(FAMILY.glob("*.py")):
            if path == OWNER:
                continue
            tree = ast.parse(path.read_text())
            with_dataset = any(node.arg == "dataset"
                               for node in ast.walk(tree) if isinstance(node, ast.arg))
            names = {node.value for node in ast.walk(tree)
                     if isinstance(node, ast.Constant) and isinstance(node.value, str)
                     and ANCHOR_TEXT in node.value}
            if with_dataset and names:
                offenders.append(f"{path.name}: {', '.join(sorted(names))}")
        self.assertEqual(
            offenders, [],
            "a caller derives an anchor file name from a dataset: " + ", ".join(offenders))

    def test_the_owner_is_the_only_place_that_answers_the_rule(self):
        text = OWNER.read_text()
        for word in (RULE_TEXT, ANCHOR_TEXT, "CLOTH_STEPS"):
            with self.subTest(word=word):
                self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
