"""Each reader of a measured bound names the owner of that bound.

Two measured bounds stood twice in this tree, and no case held either pair.

* The pocket mouth radius, 100 mm.  ``src/event_gates.GateConfig.pot_pocket_r_mm``
  owns the number.  ``src/shot_pot_gate.py`` held a second literal.  A case held
  the derived pixel radius of that copy, but no case held the copy itself
  against the owner, so the two could part and only a pixel number spoke.
* The shot-speed window, 500 mm/s to 11000 mm/s.
  ``src/info_complete_scan`` owns both ends.  ``src/candidate_scan.ScanConfig``
  held a second pair.  No case named ``MAX_SPEED_MM_S``, so the 11000 mm/s
  ceiling could move in silence.

Round 71 gave each bound one home.  ``src/shot_pot_gate.POCKET_R_MM`` reads the
owner's ``pot_pocket_r_mm``.  ``ScanConfig.shot_speed_mm_s`` and
``ScanConfig.max_speed_mm_s`` read the two names of ``src/info_complete_scan``.

This module holds that state in four ways:

1. one ``ast`` walk over the reader files reports a read site that spells a
   number in place of the owner's name;
2. one case proves that the walk finds each declared site, so a renamed site
   cannot make the walk pass with no site at all;
3. one case plants a copy in a source text and reads the report, so a walk that
   stopped matching the inline form fails here;
4. one case proves that each owner name has no second home under ``src/``.

The two ends of each bound are measured by ``tests/test_shot_pot_gate.py``,
``tests/test_event_gates.py``, ``tests/test_candidate_scan.py`` and
``tests/test_info_complete_scan.py``.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: One read site: the reader file, the name the reader binds, and the name the
#: owner of that bound spells.  The right side of the binding must hold the
#: owner's name.  A number is not a name, and the walk reports it.
READ_SITES = (
    ("src/shot_pot_gate.py", "POCKET_R_MM", "pot_pocket_r_mm"),
    ("src/candidate_scan.py", "shot_speed_mm_s", "SHOT_SPEED_MM_S"),
    ("src/candidate_scan.py", "max_speed_mm_s", "MAX_SPEED_MM_S"),
)

#: The owner of each bound, for the failure text.
OWNERS = {
    "pot_pocket_r_mm": "src.event_gates.GateConfig",
    "SHOT_SPEED_MM_S": "src.info_complete_scan",
    "MAX_SPEED_MM_S": "src.info_complete_scan",
}

#: The owner name of each bound and the one file that may spell it.  A second
#: binding of an owner name under ``src/`` is a second home, whatever it holds.
OWNER_FILES = {
    "pot_pocket_r_mm": "src/event_gates.py",
    "SHOT_SPEED_MM_S": "src/info_complete_scan.py",
    "MAX_SPEED_MM_S": "src/info_complete_scan.py",
}

#: The copies the walk must report, each with the bound it belongs to.  The case
#: appends one of these to the real text of the reader file.
PLANTED = (
    ("src/shot_pot_gate.py", "POCKET_R_MM = 110.0\n", "POCKET_R_MM", "pot_pocket_r_mm"),
    ("src/candidate_scan.py", "shot_speed_mm_s: float = 9000.0\n",
     "shot_speed_mm_s", "SHOT_SPEED_MM_S"),
    ("src/candidate_scan.py", "max_speed_mm_s: float = 9000.0\n",
     "max_speed_mm_s", "MAX_SPEED_MM_S"),
)


def bindings(tree):
    """The (line, name, value node) of every module-level and class-level binding.

    A reader states its bound in one of those two places: a module constant, as
    ``POCKET_R_MM`` is, or a dataclass field, as the two ``ScanConfig`` fields
    are.  A binding inside a function is a local name and not a bound.
    """
    out = []
    holders = [tree] + [node for node in tree.body if isinstance(node, ast.ClassDef)]
    for holder in holders:
        for node in holder.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        out.append((node.lineno, target.id, node.value))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                out.append((node.lineno, node.target.id, node.value))
    return out


def names_of(node):
    """Every name the right side of a binding reads."""
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            names.add(sub.attr)
    return names


def read_reports(sources):
    """The read sites that spell a number or another name in place of the owner.

    ``sources`` holds (label, text) pairs, so a case can give the walk a planted
    copy as well as the real files.  The label must equal the declared path, and
    a label no site names is ignored.
    """
    reports = []
    for label, text in sources:
        tree = ast.parse(text, filename=str(label))
        found = bindings(tree)
        for path, name, owner in READ_SITES:
            if label != path:
                continue
            for lineno, bound, value in found:
                if bound != name:
                    continue
                where = "%s:%d: %s" % (label, lineno, name)
                if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)):
                    reports.append(
                        "%s spells %r in place of %s.%s; read the owner's name"
                        % (where, value.value, OWNERS[owner], owner))
                elif owner not in names_of(value):
                    reports.append(
                        "%s does not name %s.%s; the reader must read the owner"
                        % (where, OWNERS[owner], owner))
    return reports


def real_sources():
    """The reader files, read once each, as (declared path, text) pairs."""
    seen, out = set(), []
    for path, _name, _owner in READ_SITES:
        if path in seen:
            continue
        seen.add(path)
        out.append((path, (ROOT / path).read_text(encoding="utf-8")))
    return out


class ReaderSites(unittest.TestCase):
    """Way 1 and way 2: each declared site reads the owner, and the walk sees it."""

    def test_every_declared_site_is_bound_in_its_file(self):
        sources = dict(real_sources())
        missing = []
        for path, name, _owner in READ_SITES:
            bound = {bound for _lineno, bound, _value in bindings(ast.parse(sources[path],
                                                                            filename=path))}
            if name not in bound:
                missing.append("%s: no binding of %s is left, so this walk reads "
                               "nothing for it; restore the binding or move the site "
                               "out of READ_SITES" % (path, name))
        self.assertEqual([], missing, "\n".join(missing))

    def test_no_reader_spells_its_bound_as_a_number(self):
        reports = read_reports(real_sources())
        self.assertEqual([], reports, "\n".join(reports))

    def test_the_owner_names_have_no_second_home_under_src(self):
        offenders = []
        for path in sorted((ROOT / "src").glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for lineno, name, _value in bindings(tree):
                home = OWNER_FILES.get(name)
                if home is not None and home != relative:
                    offenders.append("%s:%d: %s is bound again outside %s"
                                     % (relative, lineno, name, home))
        self.assertEqual([], offenders, "\n".join(offenders))


class PlantedCopies(unittest.TestCase):
    """Way 3: the walk reports a copy, so it cannot pass with no match."""

    def test_a_planted_copy_is_reported(self):
        for path, copy, name, owner in PLANTED:
            text = (ROOT / path).read_text(encoding="utf-8") + copy
            line = text.count("\n")               # the planted binding is the last line
            reports = read_reports([(path, text)])
            hit = [report for report in reports if report.startswith("%s:%d:" % (path, line))]
            self.assertEqual(1, len(hit), "%s: the walk lost the inline form %r: %s"
                                          % (path, copy, reports))
            self.assertIn(name, hit[0])
            self.assertIn(owner, hit[0])
            self.assertIn("spells", hit[0])


if __name__ == "__main__":
    unittest.main()
