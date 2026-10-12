"""One home for the ball stage's peak-search cut, and a report for every copy.

``annotator/pipeline_stages.py`` holds ``BALL_THRESHOLD``, the cut ``BallStage``
searches peaks with.  Eight harness sites used to spell the number out: a harness
that decides a ball label must read the owner's name instead, because a copy can
drift from the owner with nothing to report it.

This guard walks every ``*.py`` file of the project, finds each numeric literal
that equals the owner's value, and names the file and the line.  The virtual
environment and the generated ``out/`` tree are not the project's source and are
not read.  The owner itself is the one allowed holder: it is exempt by rule, and
one case below still reads its text and pins the single binding that the exemption
covers.

A comment or a docstring that mentions the number is not a copy: only a value the
interpreter can read reports.  The measurement harnesses under ``tests/`` are
guarded like every other module.
"""
import ast
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The one module that may hold the number, relative to the repository root.
OWNER = "annotator/pipeline_stages.py"
#: The one name that holds it.
OWNER_NAME = "BALL_THRESHOLD"
#: The name a deciding site reads.
OWNER_REF = "annotator.pipeline_stages.%s" % OWNER_NAME
#: First path parts that hold no project source: the virtual environment, the
#: generated artifacts, the object store and installed packages.
SKIPPED_TOP_LEVEL = (".git", ".venv", "node_modules", "out", "__pycache__")


def _owner_value():
    from annotator.pipeline_stages import BALL_THRESHOLD
    return BALL_THRESHOLD


OWNER_VALUE = _owner_value()

#: Modules that may hold the number, and why.  The owner is the one entry: a
#: harness that decides a ball label has no reason to be here.
EXEMPT = {OWNER: "the owner: the one module allowed to hold the value"}


def is_the_cut(node):
    """True when this AST node is a plain number equal to the owner's value.

    Compared without a float conversion: the tree holds integers too large for
    ``float`` (a digest table, a bit mask), and ``int`` 0 is not ``0.425`` while
    ``int`` 0.425 cannot exist.
    """
    if not isinstance(node, ast.Constant):
        return False
    value = node.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, int) and not isinstance(OWNER_VALUE, int):
        return False
    return value == OWNER_VALUE


def literal_findings(label, text):
    """Every numeric literal equal to the cut: ``"<label>:<line>: <report>"``.

    A number inside a string is not a literal, so a comment or a docstring that
    mentions the cut does not report.
    """
    tree = ast.parse(text, filename=label)
    out = []
    for node in ast.walk(tree):
        if is_the_cut(node):
            out.append("%s:%d: spells %r as a number; read %s"
                       % (label, node.lineno, node.value, OWNER_REF))
    return out


#: A scanned file does not change while the cases of one run read it, so the walk
#: happens once: three cases read the same tree.
@lru_cache(maxsize=None)
def repository_sources():
    """Every ``*.py`` file of the project, sorted: ``((relative path, text), ...)``.

    The virtual environment, the git object store and the generated ``out/`` tree
    are not the project's source and are not scanned.
    """
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in SKIPPED_TOP_LEVEL:
            continue
        found.append((rel.as_posix(), path.read_text(encoding="utf-8", errors="replace")))
    return tuple(found)


def copy_findings(sources):
    """Only the reported copies, in path order."""
    return [line for rel, text in sources if rel not in EXEMPT
            for line in literal_findings(rel, text)]


class TheCutHasOneHome(unittest.TestCase):
    """The owner holds one number; no other module holds it as a literal."""

    def test_the_walk_reads_the_project(self):
        """A walk that found no file would pass the scan cases for no reason."""
        sources = repository_sources()
        self.assertGreater(len(sources), 100, "the walk must read the project's modules")
        self.assertIn(OWNER, [rel for rel, _ in sources], "the walk must read the owner")

    def test_the_owner_holds_it_once(self):
        sources = dict(repository_sources())
        self.assertIn(OWNER, sources, "the owner file must exist")
        found = literal_findings(OWNER, sources[OWNER])
        self.assertEqual(
            1, len(found),
            "the owner %s must hold the cut exactly once:\n%s" % (OWNER, "\n".join(found)))

    def test_no_module_outside_the_owner_states_the_cut_as_a_number(self):
        found = copy_findings(repository_sources())
        self.assertEqual(
            [], found,
            "the cut's one home is %s; these sites spell it out instead of reading %s:\n%s"
            % (OWNER, OWNER_REF, "\n".join(found)))


class APlantedCopyIsReported(unittest.TestCase):
    """The walk reports a copy at its own line, and only a real number."""

    #: The planted copy, built so that this file holds no copy of its own.
    PLANTED = "OTHER_CUT = %r\n" % OWNER_VALUE

    def setUp(self):
        self.text = "import os\n\n\n%s" % self.PLANTED
        self.line = len(self.text.splitlines())

    def test_a_planted_copy_reports_its_file_and_its_line(self):
        found = literal_findings("tests/planted_probe.py", self.text)
        self.assertEqual(1, len(found), "one copy must report once:\n%s" % "\n".join(found))
        self.assertTrue(
            found[0].startswith("tests/planted_probe.py:%d:" % self.line),
            "the report must name the copy's line, not the file's:\n%s" % found[0])
        self.assertIn(OWNER_REF, found[0],
                      "the report must send the reader to the owner:\n%s" % found[0])

    def test_a_near_value_is_not_the_cut(self):
        text = "import os\n\nNEAR = 0.4251\n"
        self.assertEqual([], literal_findings("tests/near_probe.py", text))

    def test_a_sentence_about_the_cut_is_not_a_copy(self):
        text = ('"""The probe runs at 0.425, the owner\'s value."""\n'
                "# the cut is 0.425 and this comment holds no value\n"
                "NAME = '0.425'\n")
        self.assertEqual([], literal_findings("tests/prose_probe.py", text))

    def test_a_site_that_reads_the_owner_name_is_clean(self):
        text = ("from annotator.pipeline_stages import BALL_THRESHOLD\n\n\n"
                "def stage(frames, threshold=BALL_THRESHOLD):\n"
                "    return frames, threshold\n")
        self.assertEqual([], literal_findings("tests/reader_probe.py", text))


if __name__ == "__main__":
    unittest.main()
