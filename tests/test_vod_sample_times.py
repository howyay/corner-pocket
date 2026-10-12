"""One home for the six highlight sample instants, and one home for the dense bar.

Two rules of the repair loop stand in this file.

The highlight recording ``data/vod_highlight.mp4`` has six sample instants:
5, 28, 60, 90, 150 and 200 seconds.  ``src/audit_calib.py`` (its highlight pass),
``src/quad_fit.py``, ``src/quad_fit_lines.py`` and ``src/recut_crops.py`` once held
that list four times.  ``src/datasets.py`` owns the instants now, because it owns the
built-in media names, and the four scripts read the owner.

The dense-occupancy bar ``OCC_DENSE_MIN`` is the share of the occlusion window that
changed, above which a person explains the motion.  ``src/motion_scan.py`` owns it,
because that module measures the occlusion channel in the window.  ``src/shot_pot_gate.py``
reads the owner, so every value the gate accepts or refuses stays where it was.

Each walk below also reads a planted copy, so a tree with a second home reports that
home and not ``OK``.
"""
import ast
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

OWNER_MODULE = "src/datasets.py"
OWNER_NAME = "HIGHLIGHT_SAMPLE_TIMES"
SAMPLE_TIMES = (5, 28, 60, 90, 150, 200)

#: the four scripts that measure the highlight recording, and the function that reads
#: the instants in each one.  The empty name means the module level; ``src/quad_fit.py``
#: and ``src/quad_fit_lines.py`` read the owner there under ``if __name__ == "__main__":``.
READERS = (
    ("src/audit_calib.py", "main"),
    ("src/quad_fit.py", ""),
    ("src/quad_fit_lines.py", ""),
    ("src/recut_crops.py", ""),
)

BAR_NAME = "OCC_DENSE_MIN"
BAR_OWNER = "src/motion_scan.py"
BAR_READER = "src/shot_pot_gate.py"


def source_files():
    """Every module of ``src/``, in a stable order."""
    return tuple(sorted(SRC.glob("*.py")))


def parsed(relative):
    """The tree of one repository file, named as the walk reports it."""
    return ast.parse(source(relative), filename=relative)


def source(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def constants(node):
    """The numeric constants under one node, in source order."""
    found = [(child.lineno, child.value) for child in ast.walk(node)
             if isinstance(child, ast.Constant) and isinstance(child.value, (int, float))
             and not isinstance(child.value, bool)]
    found.sort(key=lambda item: item[0])
    return tuple(value for _, value in found)


def six_homes(tree, relative):
    """The ``file:line`` sites that state the six instants as one sequence.

    A site is a list, tuple or set of exactly six numeric constants in the order of
    :data:`SAMPLE_TIMES`.  A comment is not a site, because a comment holds no node.
    """
    homes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            continue
        if len(node.elts) != len(SAMPLE_TIMES):
            continue
        if constants(node) == SAMPLE_TIMES:
            homes.append("%s:%d" % (relative, node.lineno))
    return sorted(homes)


def owner_readers(tree):
    """``function -> the names of the rows where the code reads the owner``.

    ``src/quad_fit.py`` and ``src/quad_fit_lines.py`` read the owner under
    ``if __name__ == "__main__":`` at the module level, and ``src/recut_crops.py``
    binds its list at the module level too, so the empty name is a real row here.
    """
    found = {}
    for name, node in bodies(tree):
        if any(isinstance(child, ast.Name) and child.id == OWNER_NAME
               for child in ast.walk(node)):
            found.setdefault(name, []).append(name or "the module level")
    return found


def bodies(tree):
    """The named functions of a module, plus the module level under the empty name."""
    yield "", tree
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node


def name_bindings(tree, function=None):
    """``name -> value node`` for the bindings of one function, or of the module level."""
    found = {}
    for name, node in bodies(tree):
        if name != (function or ""):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                targets, value = child.targets, child.value
            elif isinstance(child, ast.AnnAssign) and child.value is not None:
                targets, value = [child.target], child.value
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    found[target.id] = value
    return found


def names_of(node):
    """Every name a node reads, bare or as an attribute."""
    found = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Attribute):
            found.add(child.attr)
    return found


def planted(*lines):
    """Write a planted module under a temporary folder and answer the folder and its tree."""
    temp = tempfile.TemporaryDirectory(prefix="sample-time-")
    path = Path(temp.name) / "planted_module.py"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return temp, path.read_text(encoding="utf-8")


class HighlightSampleTimesHomeTests(unittest.TestCase):
    """The six instants of the highlight recording have one home."""

    def test_the_value_states_the_six_instants_in_seconds(self):
        from src.datasets import HIGHLIGHT_SAMPLE_TIMES
        self.assertEqual(tuple(HIGHLIGHT_SAMPLE_TIMES), SAMPLE_TIMES,
                         "the owner must keep every instant and the order")
        self.assertIsInstance(HIGHLIGHT_SAMPLE_TIMES, tuple,
                              "a caller must not be able to change the owner's list")

    def test_no_other_module_states_the_six_instants(self):
        seen = []
        for path in source_files():
            relative = "src/" + path.name
            if relative == OWNER_MODULE:
                continue
            seen.extend(six_homes(ast.parse(path.read_text(encoding="utf-8"),
                                          filename=str(path)), relative))
        self.assertEqual(seen, [],
                         "a second home for the six instants: %r" % (seen,))

    def test_the_walk_sees_a_planted_copy_of_the_six_instants(self):
        temp, text = planted("TIMES = [5, 28, 60, 90, 150, 200]")
        self.addCleanup(temp.cleanup)
        self.assertEqual(six_homes(ast.parse(text), "src/read.py"), ["src/read.py:1"],
                         "the walk must report a second copy of the six instants")

    def test_a_sequence_of_another_length_is_not_a_home(self):
        _, text = planted("TIMES = [5, 28, 60, 90, 150]", "OTHER = [60, 180, 300]")
        self.assertEqual(six_homes(ast.parse(text), "src/read.py"), [])

    def test_a_comment_may_state_the_instants(self):
        _, text = planted("# the six instants are 5, 28, 60, 90, 150, 200 seconds",
                          "TIMES = read_the_owner()")
        self.assertEqual(six_homes(ast.parse(text), "src/read.py"), [])

    def test_the_owner_names_the_recording_and_the_four_scripts(self):
        text = source(OWNER_MODULE)
        self.assertIn("the ``highlight`` row of :data:`STATIC`", text,
                      "the owner must name the recording it belongs to")
        for relative, _ in READERS:
            self.assertIn(relative, text, "the owner must name %s" % relative)

    def test_the_four_scripts_read_the_owner(self):
        for relative, function in READERS:
            with self.subTest(reader=relative):
                tree = parsed(relative)
                self.assertIn("from src.datasets import %s" % OWNER_NAME, source(relative),
                              "%s must import the instants from the owner" % relative)
                self.assertIn(function, owner_readers(tree),
                              "%s must read the owner's instants in %s"
                              % (relative, function or "its own code"))
                for name, value in name_bindings(tree).items():
                    if "TIMES" not in name:
                        continue
                    self.assertIn(OWNER_NAME, names_of(value),
                                  "%s binds %s without asking the owner" % (relative, name))

    def test_a_reader_that_binds_its_own_list_is_reported(self):
        _, text = planted("from src.datasets import HIGHLIGHT_SAMPLE_TIMES",
                          "",
                          "",
                          "def main():",
                          "    TIMES = [5, 28, 60, 90, 150, 200]")
        tree = ast.parse(text)
        bindings = name_bindings(tree, "main")
        self.assertEqual(sorted(bindings), ["TIMES"])
        self.assertNotIn(OWNER_NAME, names_of(bindings["TIMES"]),
                         "a reader that spells the instants must not name the owner")
        self.assertEqual(owner_readers(tree), {})
        self.assertEqual(six_homes(tree, "src/planted.py"), ["src/planted.py:5"])

    def test_a_reader_that_takes_the_owner_is_accepted(self):
        _, text = planted("from src.datasets import HIGHLIGHT_SAMPLE_TIMES",
                          "",
                          "TIMES = list(HIGHLIGHT_SAMPLE_TIMES)")
        tree = ast.parse(text)
        self.assertIn(OWNER_NAME, names_of(name_bindings(tree)["TIMES"]))
        self.assertEqual(six_homes(tree, "src/planted.py"), [])

    def test_only_the_owner_and_the_two_guards_carry_the_searched_literal(self):
        """The tree-wide check, by a second reading: the raw words, not the nodes.

        The owner states the instants.  This file and ``tests/test_datasets.py``
        compare against them.  Anything else that carries the raw words is a new
        home, and the four reader scripts in particular must answer nothing.
        """
        found = subprocess.run(["git", "grep", "-l", "-F", "5, 28, 60, 90, 150, 200", "--",
                                "src", "tests", "tools", "annotator", "scripts"],
                               cwd=str(ROOT), capture_output=True, text=True)
        self.assertIn(found.returncode, (0, 1), "git grep failed: %s" % found.stderr)
        allowed = {OWNER_MODULE, "tests/test_datasets.py", "tests/test_vod_sample_times.py"}
        self.assertEqual(set(found.stdout.split()) - allowed, set(),
                         "a new home for the raw instants")
        self.assertEqual(set(found.stdout.split()) & {relative for relative, _ in READERS}, set())


class OcclusionBarHomeTests(unittest.TestCase):
    """The dense bar has one home, in the module that measures the channel."""

    def test_the_owner_holds_the_bar_and_its_justification(self):
        from src.motion_scan import OCC_DENSE_MIN
        self.assertEqual(OCC_DENSE_MIN, 0.30, "every accepted and refused value stays put")
        text = source(BAR_OWNER)
        self.assertIn("OCC_DENSE_MIN = 0.30", text)
        self.assertIn("can change at most ~0.14 of it", text,
                      "the owner must keep the geometric justification")

    def test_the_reader_names_the_owner(self):
        self.assertIn("from src.motion_scan import %s" % BAR_NAME, source(BAR_READER),
                      "%s must read the bar from its owner" % BAR_READER)

    def test_only_the_owner_binds_the_bar(self):
        seen = []
        for path in source_files():
            relative = "src/" + path.name
            if relative == BAR_OWNER:
                continue
            if BAR_NAME in name_bindings(ast.parse(path.read_text(encoding="utf-8"),
                                                  filename=str(path))):
                seen.append(relative)
        self.assertEqual(seen, [], "a second home for the bar: %r" % (seen,))

    def test_the_walk_sees_a_planted_bar(self):
        temp, text = planted("OCC_DENSE_MIN = 0.30")
        self.addCleanup(temp.cleanup)
        self.assertIn(BAR_NAME, name_bindings(ast.parse(text)))

    def test_the_gate_holds_the_owner_object(self):
        from src.motion_scan import OCC_DENSE_MIN as owner_bar
        from src.shot_pot_gate import OCC_DENSE_MIN as gate_bar
        self.assertIs(gate_bar, owner_bar,
                      "the gate must hold the owner's object, not a copy of its value")


if __name__ == "__main__":
    unittest.main()
