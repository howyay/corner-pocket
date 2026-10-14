"""One home for the SAM3 byte-pair asset name: `src/weight_pins.py` holds it.

The fact is the name of the byte-pair table that SAM3 loads next to its weights.
The table is vendored under `src/sam3/sam3/assets/`.  A loader holds its own
root and joins the name.

The two live copies at the round-107 walk were:

* `src/multiplex_demo.py:23: BPE = ROOT / "sam3" / "sam3" / "assets" / SAM3_BPE`
* `src/sam3_cpu.py:67:             Path(__file__).resolve().parent / "sam3" / "sam3" / "assets" / SAM3_BPE`

Round 107 W7 gave the name one home, `SAM3_BPE` in `src/weight_pins.py:94`, and
both loaders read it.  `src/multiplex_demo.py:18` holds the root of the first
loader and `src/sam3_cpu.py:67` starts from `Path(__file__)`.  Both files live
in `src/`, so both joins resolve to the same vendored file.

This module holds the name once, as `NAME`.  The reason: a case that reads both
sides from the same home stays green when the home value moves.  The value pin
must hold the shipped value itself.  The walk allows two spellings of the name:
the home line of the owner and the pin line of this module.  Every other
spelling is an offender.  The walk reports every offender as
`path:line: <the line text>`.

The cases:

* the owner holds one definition of the name, on the line this module reads;
* the home line spells the name, and the home value is the shipped name, and
  that name is a file on disk;
* each loader imports the home, joins the asset directory, ends the join in the
  home name, holds no literal, and starts from the directory of the file;
* the two loaders name the same parts, so one home moves both paths;
* the walk over the two loaders answers no copy;
* the walk over the tracked trees answers one spelling per allowed site;
* the walk leaves the vendored tree `src/sam3/` out, because `.gitignore:18`
  marks that tree ignored;
* the walk is honest: a planted copy in a loader is an offender with its path
  and line, and a moved value in the owner moves the pinned value.

Run: ``./scripts/pool-test.sh python test_sam3_asset_name_owner``
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
ANNOTATOR = ROOT / "annotator"
SCRIPTS = ROOT / "scripts"
TOOLS = ROOT / "tools"

#: The fact this module guards: the shipped name of the SAM3 byte-pair table.
NAME = "bpe_simple_vocab_16e6.txt.gz"
OWNER = "src/weight_pins.py"
OWNER_NAME = "SAM3_BPE"
OWNER_MODULE = "weight_pins"
GUARD = "tests/test_sam3_asset_name_owner.py"

#: The directory the two loaders join the name onto, under `src/`.
ASSET_DIR = ("sam3", "sam3", "assets")

#: Each loader: the file, the assignment that holds the path, and its root.
#: Both roots are the directory of the file, so both are `src/`.
READERS = (
    ("src/multiplex_demo.py", "BPE", "ROOT"),
    ("src/sam3_cpu.py", "kwargs['bpe_path']", "Path(__file__).resolve().parent"),
)

#: The trees the walk reads, and one pattern per tree.
SWEEP = ((SRC, "**/*.py"), (TESTS, "*.py"), (ANNOTATOR, "*.js"),
         (SCRIPTS, "*.sh"), (TOOLS, "*.py"))

#: The directory names the walk leaves out: build output, data, and caches.
EXCLUDED = (".venv", "out", "data", "deploy", "__pycache__", ".pm", ".git")

#: A second spelling of the name, planted in memory at the end of one text.
PLANTED = f'\nBPE_FALLBACK = "{NAME}"\n'
PLANTED_OFFSET = 2

HOME_RE = re.compile(r"^SAM3_BPE\s*=\s*[\"']")
PIN_RE = re.compile(r"^NAME\s*=\s*[\"']")


def source_text(where: str) -> str:
    """The text of one file of the repository."""
    return (ROOT / where).read_text(encoding="utf-8")


def source_lines(where: str) -> list:
    """The lines of one file of the repository."""
    return source_text(where).splitlines()


def report(where: str, number: int, body: str, why: str) -> str:
    """One failure line: `path:line: <the line text>`, and the reason."""
    return f"{where}:{number}: {body.strip()}  <- {why}"


def blame(sites, why: str) -> str:
    """Every site as `path:line: <the line text>`, with the reason."""
    return "; ".join(report(where, number, body, why)
                     for where, number, body in sites)


def home_line(text: str, where: str = OWNER) -> int:
    """The number of the one line of the owner that defines the name."""
    sites = [number for number, body in enumerate(text.splitlines(), start=1)
             if HOME_RE.match(body)]
    if len(sites) != 1:
        raise AssertionError(
            f"{where} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
    return sites[0]


def owner_value(text: str, where: str = OWNER) -> str:
    """The string the home line binds to the name."""
    number = home_line(text, where)
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Assign) and node.lineno == number:
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
    raise AssertionError(f"{where}:{number} binds no string to {OWNER_NAME}")


def name_lines(text: str, where: str) -> list:
    """Every line that spells the name: `(path, line, the line text)`."""
    return [(where, number, body)
            for number, body in enumerate(text.splitlines(), start=1)
            if NAME in body]


def allowed_lines(text: str, where: str) -> set:
    """The lines that may spell the name: the home line, and the pin line.

    The owner holds one spelling, on the line that defines the name.  This
    module holds one spelling, on the line that pins the value.  A reader holds
    no allowed line, so every spelling inside a reader counts.
    """
    allowed = set()
    if where == OWNER:
        allowed.add((OWNER, home_line(text, OWNER)))
    if where == GUARD:
        allowed.update((GUARD, number)
                       for number, body in enumerate(text.splitlines(), start=1)
                       if PIN_RE.match(body))
        if not allowed:
            raise AssertionError(f"{GUARD} holds no pin line for {OWNER_NAME}")
    return allowed


def copies_beyond_the_home(text: str, where: str) -> list:
    """Every spelling of the name away from the allowed lines."""
    allowed = allowed_lines(text, where)
    return [site for site in name_lines(text, where)
            if (site[0], site[1]) not in allowed]


def literal_sites(text: str, where: str) -> list:
    """Every string literal of the name: `(path, line, the literal written)`."""
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Constant) and node.value == NAME:
            found.append((where, node.lineno, ast.unparse(node)))
    return sorted(found, key=lambda site: site[1])


def asset_joins(text: str, where: str) -> list:
    """Every assignment that joins the asset directory.

    The answer is `(line, target, parts, leaf, base)`.  `parts` holds the string
    parts of the join in written order, `leaf` the last element, and `base` the
    first element.  The walk reads the written parts, so a loader that builds
    the path by hand shows up.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        rights = []
        expr = node.value
        while isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
            rights.append(expr.right)
            expr = expr.left
        if not rights:
            continue
        rights.reverse()
        written = node.targets[0] if isinstance(node, ast.Assign) else node.target
        parts = tuple(part.value for part in rights[:-1]
                      if isinstance(part, ast.Constant) and isinstance(part.value, str))
        found.append((node.lineno, ast.unparse(written), parts,
                      ast.unparse(rights[-1]), ast.unparse(expr)))
    return sorted(found, key=lambda site: site[0])


def imported_names(text: str, where: str) -> set:
    """Every name one module imports from the owner module."""
    found = set()
    for node in ast.walk(ast.parse(text, filename=where)):
        if (isinstance(node, ast.ImportFrom)
                and node.module in (OWNER_MODULE, f"src.{OWNER_MODULE}")):
            found.update(alias.asname or alias.name for alias in node.names)
    return found


def owner_module_aliases(text: str, where: str) -> set:
    """Every local name of the owner module itself."""
    found = set()
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in (OWNER_MODULE, f"src.{OWNER_MODULE}"):
                    found.add(alias.asname or alias.name.split(".")[-1])
    return found


def reads_the_home(text: str, where: str) -> bool:
    """True when one text names the home, directly or under a module alias."""
    if OWNER_NAME in imported_names(text, where):
        return True
    return any(f"{alias}.{OWNER_NAME}" in text
               for alias in owner_module_aliases(text, where))


def skip_tree(where: str) -> bool:
    """True when the walk leaves one path out.

    `src/sam3/` is the vendored SAM3 tree.  `.gitignore:18` marks that tree
    ignored, so a spelling inside it is not a live copy.
    """
    parts = Path(where).parts
    if parts[:2] == ("src", "sam3"):
        return True
    return any(part in EXCLUDED for part in parts)


class OwnerTests(unittest.TestCase):
    """The home of the name, and the value it holds."""

    def test_the_owner_holds_one_definition_of_the_name(self):
        """`src/weight_pins.py` holds one line that defines the name."""
        number = home_line(source_text(OWNER))
        self.assertIsInstance(number, int,
                              f"{OWNER} names no single line for {OWNER_NAME}")

    def test_the_home_line_spells_the_name(self):
        """The home line spells the name of the shipped asset."""
        lines = source_lines(OWNER)
        number = home_line(source_text(OWNER))
        body = lines[number - 1]
        self.assertIn(NAME, body,
                      report(OWNER, number, body,
                             f"the home of {OWNER_NAME} must spell the name"))

    def test_the_owner_value_is_the_shipped_name(self):
        """The value pin holds the shipped name, so a move reddens the case."""
        text = source_text(OWNER)
        number = home_line(text)
        value = owner_value(text)
        self.assertEqual(NAME, value,
                         report(OWNER, number, source_lines(OWNER)[number - 1],
                                f"{OWNER_NAME} holds {value!r} and not the "
                                f"shipped name {NAME!r}"))

    def test_the_shipped_asset_file_is_under_the_owner_name(self):
        """The name of the home is the name of a file on disk."""
        value = owner_value(source_text(OWNER))
        asset = SRC.joinpath(*ASSET_DIR) / value
        self.assertTrue(asset.is_file(),
                        f"{OWNER_NAME} names {value!r}, and {asset} is not a file")


class ReaderTests(unittest.TestCase):
    """Each loader reads the home, and holds no second home."""

    def check_reader(self, where: str, target: str, base: str) -> None:
        """One loader: the import, the join, the parts, the leaf, and the root."""
        text = source_text(where)
        lines = source_lines(where)
        self.assertTrue(reads_the_home(text, where),
                        f"{where} imports no {OWNER_NAME} from {OWNER_MODULE}, "
                        f"so the join cannot read the home")
        joins = [site for site in asset_joins(text, where) if site[1] == target]
        self.assertEqual(1, len(joins),
                         f"{where} holds {len(joins)} joins under {target}: "
                         f"{[(site[0], site[2], site[3]) for site in joins]}")
        number, _target, parts, leaf, seen_base = joins[0]
        body = lines[number - 1]
        self.assertEqual(ASSET_DIR, parts,
                         report(where, number, body,
                                f"the join writes {parts} and not {ASSET_DIR}"))
        self.assertEqual(OWNER_NAME, leaf,
                         report(where, number, body,
                                f"the join ends in {leaf} and not the home name "
                                f"{OWNER_NAME}"))
        self.assertEqual(base, seen_base,
                         report(where, number, body,
                                f"the join starts from {seen_base} and not {base}, "
                                f"the directory of the file"))
        literals = literal_sites(text, where)
        self.assertEqual([], literals,
                         blame(literals, "the loader must read the home and "
                                         "hold no literal of the name"))

    def test_multiplex_demo_reads_the_home(self):
        """`src/multiplex_demo.py` joins `SAM3_BPE` onto its own root."""
        self.check_reader("src/multiplex_demo.py", "BPE", "ROOT")

    def test_sam3_cpu_reads_the_home(self):
        """`src/sam3_cpu.py` joins `SAM3_BPE` onto the directory of the file."""
        self.check_reader("src/sam3_cpu.py", "kwargs['bpe_path']",
                          "Path(__file__).resolve().parent")

    def test_the_two_loaders_name_the_same_asset_parts(self):
        """One home moves both paths, because both joins name the same parts."""
        value = owner_value(source_text(OWNER))
        parts = set()
        resolved = set()
        for where, target, _base in READERS:
            joins = [site for site in asset_joins(source_text(where), where)
                     if site[1] == target]
            self.assertEqual(1, len(joins), f"{where} holds {len(joins)} joins")
            parts.add(joins[0][2])
            resolved.add(str(SRC.joinpath(*joins[0][2]) / value))
        self.assertEqual(1, len(parts),
                         f"the two loaders join {sorted(parts)}, so one home "
                         f"cannot move both paths")
        self.assertEqual(1, len(resolved),
                         f"the two loaders resolve {sorted(resolved)}, so the "
                         f"paths differ")
        path = Path(sorted(resolved)[0])
        self.assertTrue(path.is_file(), f"{path} is not a file")


class WalkTests(unittest.TestCase):
    """The honest count of the walk, over the trees the walk reads."""

    def test_the_two_loaders_answer_no_copy(self):
        """Neither loader holds a second home of the name."""
        offenders = []
        for where, _target, _base in READERS:
            offenders.extend(copies_beyond_the_home(source_text(where), where))
        self.assertEqual([], offenders,
                         blame(offenders, "the name has one home, in the owner"))

    def test_the_walk_of_the_tracked_trees_answers_one_spelling_per_site(self):
        """The walked trees hold the home spelling and the pin spelling only."""
        offenders = []
        seen = 0
        for directory, pattern in SWEEP:
            for path in sorted(directory.rglob(pattern)):
                where = path.relative_to(ROOT).as_posix()
                if skip_tree(where):
                    continue
                seen += 1
                offenders.extend(
                    copies_beyond_the_home(path.read_text(encoding="utf-8"), where))
        self.assertGreater(seen, 250, f"the walk read {seen} files, too few to trust")
        self.assertEqual([], offenders,
                         blame(offenders, "the name has one home, in the owner"))

    def test_the_walk_leaves_the_vendored_tree_out(self):
        """The ignored SAM3 tree stays out, and the worked tree stays in."""
        self.assertTrue(skip_tree("src/sam3/sam3/model_builder.py"),
                        "the vendored SAM3 tree must stay out of the walk")
        self.assertFalse(skip_tree("src/sam3_cpu.py"),
                         "a source file whose name starts with sam3 must stay in")
        self.assertFalse(skip_tree(GUARD), "this module must stay in the walk")


class PlantedTests(unittest.TestCase):
    """The walk is honest: a planted copy reddens the case and names the line."""

    def test_a_planted_copy_in_a_loader_names_the_line(self):
        """A second spelling in a loader is an offender with its path and line."""
        for where, _target, _base in READERS:
            text = source_text(where) + PLANTED
            offenders = copies_beyond_the_home(text, where)
            self.assertEqual(1, len(offenders),
                             f"the walk found {len(offenders)} offenders in the "
                             f"planted {where}: {offenders}")
            _place, number, _body = offenders[0]
            message = blame(offenders, "a second spelling is a second home")
            self.assertEqual(len(source_lines(where)) + PLANTED_OFFSET, number,
                             f"the walk names line {number}: {message}")
            self.assertIn(f"{where}:{number}: ", message,
                          f"the failure text names no path and line: {message}")
            self.assertIn(NAME, message,
                          f"the failure text quotes no name: {message}")

    def test_a_planted_copy_moves_the_count_of_a_loader(self):
        """A live loader answers no spelling, and the planted loader one."""
        for where, _target, _base in READERS:
            live = name_lines(source_text(where), where)
            planted = name_lines(source_text(where) + PLANTED, where)
            self.assertEqual([], live,
                             blame(live, "a loader must not spell the name"))
            self.assertEqual(1, len(planted),
                             f"the planted {where} answers {len(planted)} spellings")

    def test_a_moved_value_in_the_owner_moves_the_pinned_value(self):
        """A move of the home value reddens the value case of the owner."""
        text = source_text(OWNER)
        moved = text.replace(f'"{NAME}"', '"other_bpe_table.txt.gz"')
        self.assertNotEqual(text, moved, "the fixture did not move the value")
        self.assertNotEqual(NAME, owner_value(moved),
                            "the pinned value did not move with the home")


if __name__ == "__main__":
    unittest.main()
