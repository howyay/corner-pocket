"""The SAM3 checkpoint has one pin, and every reader takes its path from it.

`src/weight_pins.py` is the one owner of this repository's weight pins.  It pinned
the detector file and the OSNet file.  It did not pin the SAM3 checkpoint, and
eleven sites in nine shipped files spelled that path by hand, with three base
rules: a bare string against the callers's working directory, a join with the
repository root, and one join with `ROOT.parent` in `src/scan_events.py`, whose
`ROOT` is `src/`.  The same command line meant two different files in two
directories, and the pin table could see neither a rename nor a move of the
weight.

The pin now stands in `src/weight_pins.py`, and each site reads it and keeps its
own base rule.  Four rules, one class each:

* the file name of the pin stands in one string literal of the shipped tree, and
  that literal is the pin.  A path built from parts is reported the same way,
  because the last part of such a path is the file name.
* the pin states the path under the repository root, and the pin table states the
  same path, so a table lookup answers with the pin.
* each of the eleven sites reads `SAM3` from `src.weight_pins` and builds its path
  from that name.  The set below is the measured ground of round 88; a site that
  stops reading the pin fails here, and so does a file that starts reading it.
* a planted copy in a scratch file is reported, and a scratch file that reads the
  owner is not.

The scan reads the four shipped packages through `SHIPPED`, and it reads the four
string literals of a tree through `code_strings`.  The vendored SAM3 source under
`src/sam3/` is not shipped code of this repository, so it keeps the exclusion that
`tests/test_weight_pins.py` uses.

Run: ``./scripts/pool-test.sh python test_weight_pins_owner``
"""
import ast
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _shipped import SHIPPED, code_strings, shipped_modules  # noqa: E402
from src import weight_pins  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
#: The file that owns the pin table, and the only file that may spell the path.
OWNER = ROOT / "src" / "weight_pins.py"
#: Vendored upstream code, not ours to change.  One exclusion, one tree.
VENDORED = ROOT / "src" / "sam3"

#: The file name of the SAM3 checkpoint, read from the pin itself.
CHECKPOINT_NAME = Path(weight_pins.SAM3).name

#: The eleven sites of round 88, by the file name under the repository root.  A
#: file with two sites stands once: the rule is "reads the pin", not "counts lines".
SITES = (
    "src/ball_fp_audit.py",
    "src/collect2.py",
    "src/fast_ball_labels.py",
    "src/frame_inference.py",
    "src/pipeline.py",
    "src/recut_crops.py",
    "src/sam3_ball_cache.py",
    "src/sam3_cpu.py",
    "src/scan_events.py",
)

#: A planted copy, and a clean file that reads the owner.  The scan reads both.
PLANTED = 'CHECKPOINT = ROOT / "data" / "sam3.safetensors"\n'
CLEAN = 'from src.weight_pins import SAM3\nCHECKPOINT = ROOT / SAM3\n'


def _names_the_checkpoint(text):
    """True when `text` is a code string that names the SAM3 checkpoint file.

    The pin holds the path under the repository root, and the bare file name is a
    path of one part, so one test reads both.  A path built from parts reaches the
    same answer through its last part."""
    return isinstance(text, str) and Path(text).name == CHECKPOINT_NAME


def _sites(path):
    """The (line, text) of every code string of `path` that names the checkpoint."""
    return [(line, text) for line, text in code_strings(ast.parse(path.read_text(encoding="utf-8")))
            if _names_the_checkpoint(text)]


def _reads_the_pin(tree):
    """True when the tree takes the path of the checkpoint from the owner.

    Two spellings reach the owner, and both are one read: the name `SAM3` of the
    `from src.weight_pins import SAM3` form, and the attribute `weight_pins.SAM3` of
    the module form.  `src/frame_inference.py` holds the second form, because it
    reads three names of that table."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.weight_pins":
            if any(alias.name == "SAM3" for alias in node.names):
                return True
        if (isinstance(node, ast.Attribute) and node.attr == "SAM3"
                and isinstance(node.value, ast.Name) and node.value.id == "weight_pins"):
            return True
    return False


def _uses_the_pin(tree):
    """True when the tree uses the name `SAM3` after it read the pin.

    An import alone reads nothing.  `src/pipeline.py` passes the pin to the model
    loader, `src/recut_crops.py` joins it with the repository root, and the default
    argument of `src/sam3_ball_cache.py` holds it.  Three uses, one name."""
    return any((isinstance(node, ast.Name) and node.id == "SAM3")
               or (isinstance(node, ast.Attribute) and node.attr == "SAM3")
               for node in ast.walk(tree))


def _text(node):
    """The text of a string literal, cut for a failure message."""
    return node[:60] if isinstance(node, str) else str(node)


class OneHomeTest(unittest.TestCase):
    def test_one_string_literal_names_the_checkpoint_and_it_is_the_pin(self):
        """Eleven sites spelled the path.  One home is the answer, and it is the pin."""
        sites = [(path.relative_to(ROOT), line, text)
                 for path in shipped_modules() if VENDORED not in path.parents
                 for line, text in _sites(path)]
        found = ", ".join(f"{path}:{line} ({_text(text)})" for path, line, text in sites) or "none"
        self.assertEqual(
            len(sites), 1,
            f"the file name {CHECKPOINT_NAME} stands in {len(sites)} code strings of the shipped "
            f"tree: {found}. It must stand in the pin alone, in {OWNER.relative_to(ROOT)}.")
        self.assertEqual(
            sites[0][0], OWNER.relative_to(ROOT),
            f"the one code string that names {CHECKPOINT_NAME} is in {sites[0][0]}, and "
            f"{OWNER.relative_to(ROOT)} must own it.")
        self.assertEqual(
            sites[0][2], weight_pins.SAM3,
            f"the pin holds {sites[0][2]!r}, and the owner name states "
            f"{weight_pins.SAM3!r}.")

    def test_the_scan_reports_a_path_built_from_parts(self):
        """The three base rules build the path from parts, so the parts are the case."""
        with TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch.py"
            scratch.write_text('CHECKPOINT = ROOT / "data" / "sam3.safetensors"\n')
            self.assertEqual([text for _line, text in _sites(scratch)], ["sam3.safetensors"],
                             "the last part of a path built from parts is the file name.")

    def test_a_planted_copy_is_reported_and_a_clean_reader_is_not(self):
        """The rule the scan states is the rule the scan holds."""
        with TemporaryDirectory() as tmp:
            planted = Path(tmp) / "planted.py"
            planted.write_text(PLANTED)
            clean = Path(tmp) / "clean.py"
            clean.write_text(CLEAN)
            self.assertEqual([text for _line, text in _sites(planted)],
                             ["sam3.safetensors"],
                             "a planted copy of the path is a second home of the fact.")
            self.assertEqual(_sites(clean), [], "a reader of the owner holds no copy.")


class PinTest(unittest.TestCase):
    def test_the_pin_states_the_path_under_the_repository_root(self):
        """The two pins that stand beside it state a relative path, so this one does too."""
        self.assertEqual(weight_pins.SAM3, "data/sam3.safetensors")
        self.assertFalse(Path(weight_pins.SAM3).is_absolute(),
                         "a pin states the path under the repository root, not an absolute path.")
        self.assertEqual(Path(weight_pins.SAM3).name, CHECKPOINT_NAME)
        self.assertEqual(len(Path(weight_pins.SAM3).parts), 2,
                         "the checkpoint sits in data/, so the pin has two parts.")

    def test_the_pin_table_does_not_claim_the_checkpoint(self):
        """The checkpoint has no URL, no SHA-256 and no size: fetch_weights.py does not
        download it.  A table row without those three facts would be a false pin."""
        self.assertNotIn(weight_pins.SAM3, weight_pins.WEIGHTS_BY_PATH)
        self.assertEqual([row[0] for row in weight_pins.WEIGHT_PINS],
                         [weight_pins.YOLO, weight_pins.OSNET])


class SitesTest(unittest.TestCase):
    def test_every_site_reads_the_pin(self):
        """Each of the eleven sites takes the path from the owner, and holds no copy.

        Three base rules use the name of an import, and the join with
        `ROOT.parent` of `src/scan_events.py` uses the name of the module, because
        that file reads three names of the pin table."""
        bad = []
        for name in SITES:
            path = ROOT / name
            self.assertTrue(path.is_file(), f"{name} is not a file of this tree.")
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if not _reads_the_pin(tree):
                bad.append(f"{name} does not read SAM3 from src.weight_pins")
                continue
            if not _uses_the_pin(tree):
                bad.append(f"{name} reads the pin and never uses the name SAM3")
                continue
            if _sites(path):
                bad.append(f"{name} holds a copy of the file name at line "
                           f"{_sites(path)[0][0]}")
        self.assertEqual(bad, [], "; ".join(bad))

    def test_an_import_without_a_use_does_not_read_the_pin(self):
        """A reader of the pin names it.  An import that nothing reads fails here."""
        with TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch.py"
            scratch.write_text("from src.weight_pins import SAM3\n")
            tree = ast.parse(scratch.read_text(encoding="utf-8"))
            self.assertTrue(_reads_the_pin(tree))
            self.assertFalse(_uses_the_pin(tree),
                             "the name of the import is not a use of the pin.")

    def test_no_other_shipped_file_reads_the_pin(self):
        """A new reader is a new base rule.  The list above is the measured ground."""
        readers = set()
        for path in shipped_modules():
            if VENDORED in path.parents or path == OWNER:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if _reads_the_pin(tree):
                readers.add(path.relative_to(ROOT).as_posix())
        self.assertEqual(sorted(readers), sorted(SITES),
                         "the set of files that read the SAM3 pin changed.")

    def test_the_scan_scope_is_the_four_shipped_packages(self):
        """The guard reads the tree that ships, and it does not read the suite."""
        self.assertEqual(SHIPPED, ('src', 'annotator', 'tools', 'scripts'))
        self.assertTrue(shipped_modules(), "the walk of the shipped tree answered nothing.")


if __name__ == "__main__":
    unittest.main()
