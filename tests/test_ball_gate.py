"""src/ball_gate.py: one home for the SAM3 ball admission gate numbers.

Nine modules used to spell the gate themselves, and src/pipeline.py capped an
instance mask at 6000 px while five other sites capped it at 9000 px with no
stated reason.  The gate has three bars -- a score cut, an area window and a
radius band -- and the radius band, 4.0..60.0 px, was still written out at four
sites after the area and score unification.  src/ball_gate.py now owns the seven
values.  This file fails when a second copy of one of those values comes back,
when a gate site stops sharing the owner's object, or when the owner's numbers
stop matching the ones documented here.

Two sweeps guard the second-home rule, because a number has to sit in the right
*position* to be a gate number: ``gate_literal_hits`` reads area and score
positions, ``radius_literal_hits`` reads radius positions.  The second sweep is
also run over the four spellings the sites actually used, so the guard's bite is
a test and not a claim.

Nothing here imports a detector, and nothing here reads out/ or data/.  Two gate
sites are straight-line scripts: src/collect2.py:23-24 makes out/ directories at
import, and src/recut_crops.py:43 reads out/unlabeled_crops/meta.json at import.
Their binding is therefore checked by running the file's own import statement --
the technique tests/test_table_geometry.py:166 uses for src/audit_calib.py.
"""
import ast
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src import ball_gate as owner  # noqa: E402

SRC = REPO / "src"
OWNER = SRC / "ball_gate.py"
#: Every number the gate owns.  A literal of one of these in a gate position
#: under src/ is a second home for the decision, whatever it is named.
GATE_VALUES = (0.62, 60, 6000, 9000, 4200)
#: A literal counts as a gate position only next to one of these words.
GATE_WORDS = ("area", "score")
#: The radius band, the gate's third bar.  Checked apart from GATE_VALUES: the
#: position that makes a 4.0 or a 60.0 a gate number is a radius position, and a
#: radius position is not an area position.  ``60`` above is the lower *area*
#: cap; the ``60.0`` here is a length in pixels.
RADIUS_VALUES = (4.0, 60.0)
#: A name is a radius name when one of its tokens is one of these words ...
RADIUS_WORDS = ("r", "radius")
#: ... and every other token is one of these qualifiers.  The vocabulary is what
#: keeps ``pad_r`` (src/motion_scan.py:1623, the padding of a crop) out: "pad" is
#: not a qualifier, so that 60 stays a padding and never a radius.
RADIUS_QUALIFIERS = ("min", "max", "ball", "sam3")
#: The four spellings the gate sites used before the radius band moved, written
#: here so a test can prove the sweep still catches each one.  If the sweep
#: stops biting, this test fails with the sweep, not with the tree.
RADIUS_SPELLINGS = (
    ("src/pipeline.py", "if r < 4.0 or r > 60.0:\n    continue\n"),
    ("src/scan_events.py", "if r < 4.0 or r > 60.0:\n    continue\n"),
    ("src/sam3_ball_cache.py", "MIN_R, MAX_R = 4.0, 60.0\n"),
    ("src/ball_fp_audit.py", "BALL_MIN_R, BALL_MAX_R = 4.0, 60.0\n"),
)
#: Sources that carry a 4.0 or a 60.0 in a radius-*shaped* spot but are not the
#: gate's radius band.  Each must produce no radius hit at all.
NOT_THE_RADIUS_BAND = (
    ("src/motion_scan.py", "pad_l, pad_r, pad_t, pad_b = (60, 20, 16, 34)\n"),
    ("the area window", "if area < 60 or area > 9000:\n    continue\n"),
)
#: The numbers this file documents, with the type each site used before the
#: move: the gate window was an int pair, the score cut and 4200 were floats,
#: and the radius band was a float pair.
DOCUMENTED = {
    "SAM3_BALL_MIN_SCORE": 0.62,
    "SAM3_BALL_MIN_AREA_PX": 60,
    "SAM3_BALL_MAX_AREA_PX": 9000,
    "POC_PIPELINE_BALL_MAX_AREA_PX": 6000,
    "CLASSICAL_BALL_MAX_AREA_960X540_PX": 4200.0,
    "SAM3_BALL_MIN_RADIUS_PX": 4.0,
    "SAM3_BALL_MAX_RADIUS_PX": 60.0,
}
#: Which owner names each gate site reads.  A site that drops a usage fails.
GATE_SITES = {
    "src/ball_census.py": ("SAM3_BALL_MIN_SCORE",),
    "src/ball_fp_audit.py": ("SAM3_BALL_MIN_SCORE", "SAM3_BALL_MIN_AREA_PX",
                             "SAM3_BALL_MAX_AREA_PX", "SAM3_BALL_MIN_RADIUS_PX",
                             "SAM3_BALL_MAX_RADIUS_PX"),
    "src/collect2.py": ("SAM3_BALL_MIN_SCORE", "SAM3_BALL_MIN_AREA_PX",
                        "SAM3_BALL_MAX_AREA_PX"),
    "src/fast_ball_labels.py": ("SAM3_BALL_MIN_SCORE",),
    "src/pipeline.py": ("SAM3_BALL_MIN_SCORE", "SAM3_BALL_MIN_AREA_PX",
                        "POC_PIPELINE_BALL_MAX_AREA_PX", "SAM3_BALL_MIN_RADIUS_PX",
                        "SAM3_BALL_MAX_RADIUS_PX"),
    "src/recut_crops.py": ("SAM3_BALL_MIN_SCORE", "SAM3_BALL_MIN_AREA_PX",
                           "SAM3_BALL_MAX_AREA_PX"),
    "src/sam3_ball_cache.py": ("SAM3_BALL_MIN_SCORE", "SAM3_BALL_MIN_AREA_PX",
                               "SAM3_BALL_MAX_AREA_PX", "SAM3_BALL_MIN_RADIUS_PX",
                               "SAM3_BALL_MAX_RADIUS_PX"),
    "src/scan_events.py": ("SAM3_BALL_MIN_SCORE", "SAM3_BALL_MIN_AREA_PX",
                           "SAM3_BALL_MAX_AREA_PX", "CLASSICAL_BALL_MAX_AREA_960X540_PX",
                           "SAM3_BALL_MIN_RADIUS_PX", "SAM3_BALL_MAX_RADIUS_PX"),
    "src/tiny_ball_net.py": ("SAM3_BALL_MIN_SCORE",),
}
#: Third-party checkouts that ship under src/, by directory name.  They are not
#: this repository's decisions, so the guard does not read them.  The test
#: asserts both exist, so this skip cannot become a wildcard.  The check is on
#: directory components, never on a string prefix: ``src/sam3_ball_cache.py`` is
#: a gate site and must stay in scope.
VENDORED = ("reid", "sam3")


def assigned_names(*targets) -> set:
    """Every plain name bound by an assignment target, tuple targets included."""
    names = set()
    for node in targets:
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            names |= assigned_names(*node.elts)
        elif isinstance(node, ast.Starred):
            names |= assigned_names(node.value)
    return names


def literals(node) -> list:
    """The constant leaves of one expression, tuple and list elements included."""
    if isinstance(node, ast.Constant):
        return [node]
    if isinstance(node, (ast.Tuple, ast.List)):
        out = []
        for element in node.elts:
            out += literals(element)
        return out
    return []


def bound_pairs(targets, value) -> list:
    """(name, constant) pairs of a plain or tuple assignment, index by index."""
    pairs = []
    for target in targets:
        if isinstance(target, ast.Name) and isinstance(value, ast.Constant):
            pairs.append((target.id, value.value))
        elif isinstance(target, ast.Tuple) and isinstance(value, (ast.Tuple, ast.List)):
            for index, element in enumerate(target.elts):
                if isinstance(element, ast.Name) and index < len(value.elts):
                    leaf = value.elts[index]
                    if isinstance(leaf, ast.Constant):
                        pairs.append((element.id, leaf.value))
    return pairs


def gate_literal_hits(path) -> list:
    """(lineno, value, text) for each gate number that sits in a gate position.

    A gate position is one of three places: an operand of a comparison whose
    other side names an area or a score; the value of a binding whose name names
    an area or a score; the default of a function argument named for an area.
    """
    hits = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Compare):
            operands = [node.left] + list(node.comparators)
            texts = [ast.unparse(operand) for operand in operands]
            for index, operand in enumerate(operands):
                if not (isinstance(operand, ast.Constant) and operand.value in GATE_VALUES):
                    continue
                others = " ".join(t for i, t in enumerate(texts) if i != index).lower()
                if any(word in others for word in GATE_WORDS):
                    hits.append((operand.lineno, operand.value, ast.unparse(node)))
        elif isinstance(node, ast.Assign):
            names = assigned_names(*node.targets)
            if not any(word in name.lower() for name in names for word in GATE_WORDS):
                continue
            for leaf in literals(node.value):
                if leaf.value in GATE_VALUES:
                    hits.append((leaf.lineno, leaf.value, ast.unparse(node)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pairs = list(zip(node.args.args[-len(node.args.defaults):], node.args.defaults)) \
                if node.args.defaults else []
            pairs += [(a, d) for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults) if d]
            for argument, default in pairs:
                if "area" not in argument.arg.lower():
                    continue
                for leaf in literals(default):
                    if leaf.value in GATE_VALUES:
                        hits.append((leaf.lineno, leaf.value, ast.unparse(node).splitlines()[0]))
    return sorted(set(hits))


def radius_name(text: str) -> bool:
    """Is this name a word for the gate's radius?

    True when one of its underscore-separated tokens is ``r`` or ``radius`` and
    every other token is a qualifier (``min``, ``max``, ``ball``, ``sam3``).
    ``r`` and ``radius`` pass; ``MIN_R``, ``MAX_R``, ``BALL_MIN_R`` and
    ``BALL_MAX_R`` pass; ``pad_r`` does not, because ``pad`` is a padding and not
    a qualifier of a radius.
    """
    tokens = [token for token in text.lower().split("_") if token]
    if not tokens:
        return False
    if not any(token in RADIUS_WORDS for token in tokens):
        return False
    return all(token in RADIUS_WORDS or token in RADIUS_QUALIFIERS for token in tokens)


def radius_literal_hits(source: str) -> list:
    """(lineno, value, text) for each radius-band number that sits in a radius position.

    A radius position is one of three places: an operand of a comparison whose
    other side is a radius name; the value of a binding whose name is a radius
    name; the default of an argument whose name is a radius name.
    """
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare):
            operands = [node.left] + list(node.comparators)
            texts = [ast.unparse(operand) for operand in operands]
            for index, operand in enumerate(operands):
                if not (isinstance(operand, ast.Constant)
                        and operand.value in RADIUS_VALUES):
                    continue
                others = [t for i, t in enumerate(texts) if i != index]
                if any(radius_name(other) for other in others):
                    hits.append((operand.lineno, operand.value, ast.unparse(node)))
        elif isinstance(node, ast.Assign):
            names = {name for name in assigned_names(*node.targets) if radius_name(name)}
            if not names:
                continue
            for leaf in literals(node.value):
                if leaf.value in RADIUS_VALUES:
                    hits.append((leaf.lineno, leaf.value, ast.unparse(node)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pairs = list(zip(node.args.args[-len(node.args.defaults):], node.args.defaults)) \
                if node.args.defaults else []
            pairs += [(a, d) for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults) if d]
            for argument, default in pairs:
                if not radius_name(argument.arg):
                    continue
                for leaf in literals(default):
                    if leaf.value in RADIUS_VALUES:
                        hits.append((leaf.lineno, leaf.value, argument.arg))
    return sorted(set(hits))


def src_modules() -> list:
    """Every .py under src/ except the owner and the vendored checkouts."""
    return sorted(p for p in SRC.rglob("*.py")
                  if p != OWNER and p.relative_to(SRC).parts[0] not in VENDORED)


def other_area_decisions() -> dict:
    """The remaining gate-shaped literals, each a different decision.

    Keyed by (module, value) so a *new* gate number in the same module still
    fails.  The lower cap of each of these windows is not the gate's lower cap,
    which is what makes them a different decision; the test checks that.
    """
    return {
        ("src/ball_detect.py", 9000.0):
            "classical colour-blob contour cap, lower cap 40.0 px (src/ball_detect.py:31)",
        ("src/candidate_scan.py", 9000.0):
            "same classical cap on a 960x540 frame, lower cap 14.0 (src/candidate_scan.py:54)",
        ("src/eval_events.py", 9000.0):
            "same classical cap, lower cap 14.0 (src/eval_events.py:58)",
        ("src/info_complete_scan.py", 9000.0):
            "same classical cap, lower cap 14.0 (src/info_complete_scan.py:54)",
        ("src/calibrate.py", 6000):
            "pocket-hole dark window, lower cap 120 px (src/calibrate.py:41)",
    }


def import_statement(path):
    """The file's own ``src.ball_gate`` import node, or None."""
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ImportFrom) and node.module == "src.ball_gate":
            return node
        if isinstance(node, ast.Import) and any(a.name == "src.ball_gate" for a in node.names):
            return node
    return None


class OneBallGateTests(unittest.TestCase):
    """One gate, one home: the sites share the owner and no module restates it."""

    @staticmethod
    def bind_owner_names(path) -> dict:
        """Run only the file's owner import, and return the names it binds.

        Running the whole file is impossible for the two scripts, and importing
        the others here would load cv2 and torch for a name check.
        """
        node = import_statement(path)
        if node is None:
            return {}
        namespace = {}
        exec(compile(ast.Module([node], []), str(path), "exec"), namespace)
        return {k: v for k, v in namespace.items() if not k.startswith("__")}

    def test_no_module_under_src_restates_a_gate_number(self):
        # The owner's own numbers are checked by test_the_owner_holds_the_
        # documented_numbers, so a changed value fails one test and not two.
        paths = src_modules()
        top_level = [p for p in SRC.glob("*.py") if p != OWNER]
        self.assertTrue(set(top_level) <= set(paths))  # the walk covers every module
        self.assertGreater(len(paths), 60)
        exempt = other_area_decisions()
        found = []
        for path in paths:
            relative = str(path.relative_to(REPO))
            for lineno, value, text in gate_literal_hits(path):
                if (relative, value) in exempt:
                    continue
                found.append(f"{relative}:{lineno}: {value!r} in {text}")
        self.assertEqual(found, [], "a module under src/ defines its own "
                                    "gate number:\n" + "\n".join(found))

    def test_no_module_under_src_restates_the_radius_band(self):
        # The third bar needs no exemption map.  That is not luck: the sweep
        # reads a radius position, and the four sites that used to spell the band
        # each spelled it in one.  A module that spells it again fails here.
        paths = src_modules()
        self.assertGreater(len(paths), 60)
        found = []
        for path in paths:
            relative = str(path.relative_to(REPO))
            source = path.read_text(encoding="utf-8")
            for lineno, value, text in radius_literal_hits(source):
                found.append(f"{relative}:{lineno}: {value!r} in {text}")
        self.assertEqual(found, [], "a module under src/ defines its own radius "
                                    "band:\n" + "\n".join(found))

    def test_the_radius_sweep_catches_the_four_spellings_the_sites_used(self):
        # The guard's bite, as a test.  A sweep that stops matching the form the
        # sites used would let the band be written out again and still pass
        # test_no_module_under_src_restates_the_radius_band.
        for _origin, source in RADIUS_SPELLINGS:
            hits = radius_literal_hits(source)
            self.assertEqual([value for _lineno, value, _text in hits],
                             [4.0, 60.0], f"the sweep lost {source!r}")

    def test_the_radius_sweep_leaves_the_other_radius_shaped_numbers_alone(self):
        # A guard that flags a crop padding, or the area window, would be noise.
        for origin, source in NOT_THE_RADIUS_BAND:
            self.assertEqual(radius_literal_hits(source), [],
                             f"{origin}: the sweep is flagging a different quantity")

    def test_the_owner_states_the_radius_band(self):
        document = owner.__doc__
        self.assertIn("SAM3_BALL_MIN_RADIUS_PX", document)
        self.assertIn("SAM3_BALL_MAX_RADIUS_PX", document)
        # The four sites the band moved out of are named in the owner, so the
        # next reader can check the claim instead of taking it.
        for site in ("src/pipeline.py", "src/scan_events.py",
                     "src/sam3_ball_cache.py", "src/ball_fp_audit.py"):
            self.assertIn(site, document)
        self.assertIn("4.0, 60.0", document)
        # The radius 60 and the area 60 are two quantities, so they keep two
        # names and two types.  An int area and a float length cannot be passed
        # one for the other by accident.
        self.assertIn("the area 60", document)
        # Prose is wrapped, so compare it with its whitespace flattened.
        prose = " ".join(document.split())
        self.assertIn("A length in pixels and a count of pixels are different "
                      "quantities", prose)
        self.assertIs(type(owner.SAM3_BALL_MIN_AREA_PX), int)
        self.assertIs(type(owner.SAM3_BALL_MAX_RADIUS_PX), float)
        self.assertIs(type(owner.SAM3_BALL_MIN_RADIUS_PX), float)

    def test_the_other_area_decisions_are_the_documented_ones(self):
        # The exemption map is the honest part of the guard: it must not grow
        # without a reason, and each entry must really be a different window.
        self.assertEqual(
            sorted(other_area_decisions()),
            [("src/ball_detect.py", 9000.0), ("src/calibrate.py", 6000),
             ("src/candidate_scan.py", 9000.0), ("src/eval_events.py", 9000.0),
             ("src/info_complete_scan.py", 9000.0)])
        self.assertTrue(all(reason.strip() for reason in other_area_decisions().values()))
        # An exemption that no longer matches a real hit is a stale exemption,
        # and a stale exemption would hide the next second home.
        for (relative, value) in other_area_decisions():
            hits = [hit for hit in gate_literal_hits(REPO / relative) if hit[1] == value]
            self.assertTrue(hits, f"{relative}: no {value!r} hit is left to exempt")
        lower_caps = {
            "src/ball_detect.py": 40.0,          # min_area default
            "src/calibrate.py": 120,             # min_area default, a pocket hole
            "src/candidate_scan.py": 14.0,
            "src/eval_events.py": 14.0,
            "src/info_complete_scan.py": 14.0,
        }
        for relative, documented in lower_caps.items():
            measured = set()
            for node in ast.walk(ast.parse((REPO / relative).read_text(encoding="utf-8"))):
                if isinstance(node, ast.Assign):
                    measured |= {value for name, value in bound_pairs(node.targets, node.value)
                                 if name == "MIN_BALL_AREA"}
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    pairs = list(zip(node.args.args[-len(node.args.defaults):],
                                     node.args.defaults)) if node.args.defaults else []
                    measured |= {d.value for a, d in pairs
                                 if a.arg.lower() == "min_area" and isinstance(d, ast.Constant)}
            self.assertEqual(measured, {documented},
                             f"{relative}: its lower area cap moved; the exemption "
                             f"now needs new evidence")
            self.assertNotIn(owner.SAM3_BALL_MIN_AREA_PX, measured,
                             f"{relative}: its lower cap IS the gate's lower cap, so "
                             f"it is the same decision and must not be exempt")

    def test_the_vendored_checkouts_this_guard_skips_still_exist(self):
        for name in VENDORED:
            self.assertTrue((SRC / name).is_dir())

    def test_every_gate_site_binds_the_owner_objects(self):
        # ``is``, not ``==``: a site must hold the owner's object, so no copy of
        # a number can drift away from its home.
        for relative, expected in GATE_SITES.items():
            path = REPO / relative
            bound = self.bind_owner_names(path)
            self.assertEqual(sorted(bound), sorted(expected),
                             f"{relative}: it must import exactly {sorted(expected)}")
            for name in expected:
                self.assertIs(bound[name], getattr(owner, name),
                              f"{relative}: {name} is not the owner's object")
            used = {node.id for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                    if isinstance(node, ast.Name)}
            for name in expected:
                self.assertIn(name, used, f"{relative}: {name} is imported and never used")
            # A flat ``from ball_gate import ...`` would build a second module
            # object, and a second object is a second home.
            tree = ast.parse(path.read_text(encoding="utf-8"))
            flat = [node for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module == "ball_gate"]
            self.assertEqual(flat, [],
                             f"{relative}: import the owner as src.ball_gate, never flat")

    def test_the_owner_holds_the_documented_numbers(self):
        self.assertEqual(sorted(owner.__all__), sorted(DOCUMENTED))
        for name, value in DOCUMENTED.items():
            actual = getattr(owner, name)
            self.assertEqual(actual, value, f"src/ball_gate.py: {name} changed")
            self.assertIs(type(actual), type(value),
                          f"src/ball_gate.py: {name} changed type")

    def test_the_owner_states_the_disagreement(self):
        document = owner.__doc__.lower()
        self.assertIn("contradict", document)
        self.assertIn("src/pipeline.py", document)
        self.assertNotEqual(owner.POC_PIPELINE_BALL_MAX_AREA_PX, owner.SAM3_BALL_MAX_AREA_PX)
        self.assertIn("6000", owner.__doc__)
        self.assertIn("9000", owner.__doc__)
        self.assertIn("4200", owner.__doc__)

    def test_the_owner_imports_nothing(self):
        # The home must stay importable without cv2, torch or SAM3: that is why
        # src/ball_fp_audit.py no longer needs a copy of the numbers.
        allowed = set(sys.stdlib_module_names) | {"numpy"}
        for node in ast.walk(ast.parse(OWNER.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [(node.module or "").split(".")[0]]
            else:
                continue
            for module in modules:
                self.assertIn(module, allowed, f"src/ball_gate.py imports {module}")


if __name__ == "__main__":
    unittest.main()
