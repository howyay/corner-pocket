"""The scan corners path has one owner: ``src/calib_segments.SCAN_CORNERS``.

Round 89 found the path ``out/scan30/corners.json`` spelled seven times.  The
owner states it as :data:`SCAN_CORNERS`, and six sites wrote the same text again:

1. the ``--corners`` default of ``src/info_complete_scan.py``;
2. the ``--scan-quad`` default of ``src/eval_events.py``;
3. the ``--quad`` default of ``src/timing_verify.py``;
4. the ``corners_path`` parameter of ``src.sam3_ball_cache.cloth_mask``;
5. the ``corners_path`` parameter of ``src.sam3_ball_cache.run``;
6. the ``--corners`` default of ``src/sam3_ball_cache.main``.

The seven spellings agreed, so a rename of the file moved the owner alone and
left six readers pointed at a path that does not exist.  The six sites read
:data:`SCAN_CORNERS` now.  Every default keeps its value, because the owner
answers the same text.

The cases below hold eight things:

1. the owner states the name once;
2. no shipped module outside the owner states the path, in one literal or built
   from two or more parts;
3. a planted copy is reported with its file and its line;
4. a path built from parts is reported with its file and its line;
5. a module that imports the owner is quiet;
6. each of the six sites reads the owner;
7. the report of the shipped tree reads every kind, so one kind cannot hide a
   module that builds the path by hand;
8. a copy that a module builds from parts is reported with its file and its line.

Round 93 found two more copies of the path, at ``src/calib_mapping_audit.py:70``
and ``src/tiny_ball_net.py:61``.  Each one joined the parts by hand, and the case
at point 2 asked for ``'spells'`` findings only, so the guard hid both.  The two
modules read the owner now, and the case reads every kind.

The scan reads the used strings of the shipped packages (``src``, ``annotator``,
``tools``, ``scripts``), through ``tests/_shipped.py``.  A comment is not a
finding: ``code_strings`` drops a docstring, and a literal holds no comment.  The
two prose mentions of the path in ``src/calib_mapping_audit.py`` are therefore
outside the scan, and they stay.

Run: ``./scripts/pool-test.sh python test_scan_corners_owner``
"""
import ast
from pathlib import Path
import sys
import tempfile
import unittest
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from _shipped import code_strings, shipped_modules  # noqa: E402
from src import calib_segments  # noqa: E402

#: The relative path of the one module that owns the name.
OWNER = 'src/calib_segments.py'

#: The name the owner states once, and no other shipped module states.
OWNER_NAME = 'SCAN_CORNERS'

#: The value of the owner, read from the owner and never spelled here again.
OWNER_VALUE = calib_segments.SCAN_CORNERS

#: Two words that together tell the reader which file a string names.  A string
#: that holds both is a copy of the name, or the half of one.
TOKENS = ('scan30', 'corners')

#: The module-level name of the owner that a reader imports.
OWNER_MODULE = 'src.calib_segments'


class Site(NamedTuple):
    """One site that must read the owner, and the shape of that site.

    ``line`` is the line the brief of round 89 gives, for the tree of round 88.
    ``now`` is the line of this site after the round 89 edit that added an import
    above it.  The check reports ``now``, and it keeps ``line`` for the reader.
    """

    relative: str
    line: int                # the line the brief gives, in the tree of round 88
    now: int                 # the line of this site in the tree of round 89
    kind: str                # 'signature' or 'argparse'
    name: str                # the function name, or the option name
    parameter: str = ''      # the parameter name; "" for an option


#: The six sites of round 89, and the line each one moved to.
SITES = (
    Site('src/info_complete_scan.py', 415, 417, 'argparse', '--corners'),
    Site('src/eval_events.py', 1090, 1096, 'argparse', '--scan-quad'),
    Site('src/timing_verify.py', 789, 798, 'argparse', '--quad'),
    Site('src/sam3_ball_cache.py', 126, 128, 'signature', 'cloth_mask', 'corners_path'),
    Site('src/sam3_ball_cache.py', 313, 315, 'signature', 'run', 'corners_path'),
    Site('src/sam3_ball_cache.py', 389, 391, 'argparse', '--corners'),
)


def imported_here(tree, path, module=OWNER_MODULE, name=OWNER_NAME):
    """The local names a module gives to ``name`` of ``module``.

    A reader may import the constant, or import its module and read the
    attribute.  The second form binds the module name, so the caller answers the
    module name in that case.
    """
    aliases = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            aliases += [word.asname or word.name for word in node.names
                        if word.name == name]
        elif isinstance(node, ast.Import):
            aliases += [word.asname or word.name.split('.')[0]
                        for word in node.names if word.name == module]
    return aliases


def reads_the_owner(node, aliases, path):
    """True when one expression reads the owner's constant.

    Two spellings count: the imported name (``SCAN_CORNERS``), and the module
    with the attribute (``calib_segments.SCAN_CORNERS``).  A name the reader did
    not import does not count, so a local name that happens to be spelled the
    same is not a read of the owner.
    """
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, ast.Attribute) and node.attr == OWNER_NAME:
        base = node.value
        return (isinstance(base, ast.Name) and base.id in aliases) or ast.unparse(base) in aliases
    if OWNER_NAME in ast.unparse(node) and aliases:
        return True
    return False


def signature_read(relative, name, parameter):
    """The message for one signature site that does not read the owner, or None.

    The message holds the line, the column and the function, so a reader finds
    the default that names the path by hand.
    """
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'), filename=relative)
    aliases = imported_here(tree, relative)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != name:
            continue
        arguments = list(node.args.args)
        defaults = list(node.args.defaults) + [word.value for word in node.args.kw_defaults
                                               if word is not None]
        for argument, default in zip(arguments[-len(node.args.defaults):] if
                                     node.args.defaults else [], node.args.defaults):
            if argument.arg == parameter:
                if reads_the_owner(default, aliases, relative):
                    return None
                return (f'{relative}:{default.lineno}:{default.col_offset} {name}('
                        f'{parameter}={ast.unparse(default)}) does not read '
                        f'{OWNER}:{OWNER_NAME}')
        del defaults
    return f'{relative}: {name} takes no parameter {parameter}'


def option_read(relative, flag):
    """The message for one argparse site that does not read the owner, or None.

    The message holds the line, the column and the option, so a reader finds the
    default that names the path by hand.
    """
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'), filename=relative)
    aliases = imported_here(tree, relative)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        called = node.func
        name = called.attr if isinstance(called, ast.Attribute) else getattr(called, 'id', '')
        first = node.args[0]
        if name != 'add_argument' or not (isinstance(first, ast.Constant) and first.value == flag):
            continue
        stated = [word.value for word in node.keywords if word.arg == 'default']
        if not stated:
            return f'{relative}:{node.lineno} {flag} takes no default'
        if reads_the_owner(stated[0], aliases, relative):
            return None
        return (f'{relative}:{stated[0].lineno}:{stated[0].col_offset} {flag} holds '
                f'{ast.unparse(stated[0])} in place of {OWNER}:{OWNER_NAME}')
    return f'{relative}: no add_argument call states {flag}'


def parts_of_one_path(node):
    """The string texts that a single expression of ``+`` and ``/`` joins."""
    texts = []
    for piece in ast.walk(node):
        if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
            texts.append(piece.value)
    return texts


def statement_line(relative, matches):
    """The line of the first statement of a module that ``matches`` accepts."""
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'), filename=relative)
    lines = [node.lineno for node in ast.walk(tree) if matches(node)]
    return min(lines) if lines else 0


def assembled(tree):
    """Line and texts of every path that a module joins with ``+`` or ``/``.

    A path built from parts carries one part with the first word of the name or
    with both words, and one part with the second word.  A lone ``"out"`` names
    no file and is not a finding; the reader must keep that word free for every
    other directory.  Both words hold the answer, and the answer is sorted, so
    the line of a report and the words in it do not depend on the walk order.
    """
    built = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, (ast.Add, ast.Div)):
            continue
        texts = parts_of_one_path(node)
        if not (any(text and TOKENS[0] in text for text in texts)
                and any(text and TOKENS[1] in text for text in texts)):
            continue
        built.append((node.lineno, tuple(sorted(text for text in texts if text))))
    return built


def named_by_hand(text):
    """True when one string names the scan corners file, in whole or in part."""
    return text == OWNER_VALUE or all(word in text for word in TOKENS)


def copies(paths=None):
    """(relative, line, text, kind) for every string that names the path by hand.

    ``kind`` is ``'spells'`` for the whole path in one literal, ``'names'`` for a
    literal that holds both words, and ``'builds'`` for a part of one expression
    of ``+`` and ``/`` that holds one word, or both.  A module that reads the
    owner holds none of the three.
    """
    found = []
    for path in (shipped_modules() if paths is None else paths):
        label = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=label)
        placed = {}
        for line, texts in assembled(tree):
            if line not in placed or sum(map(len, texts)) < sum(map(len, placed[line])):
                # One line answers one finding.  If two paths start on the one
                # line, the shorter names the file.
                placed[line] = texts
        for line, text in code_strings(tree):
            if line in placed and text in placed[line]:
                # A part of a path is a finding with no word of its own: "out"
                # names nothing, and it joins the words that do.
                found.append((label, line, text, 'builds'))
            elif line not in placed and text == OWNER_VALUE:
                found.append((label, line, text, 'spells'))
            elif line not in placed and named_by_hand(text):
                found.append((label, line, text, 'names'))
    return found


#: Every kind of finding this module reports.
ALL = ('spells', 'names', 'builds')

#: The kind of the finding that a path built from parts gives, and the one kind
#: that one ``'spells'`` site can hide.  A guard that reads one kind only reports
#: nothing for two hand-built copies of the path.
BUILT = 'builds'


def problems(sites, only=ALL):
    """One line per site outside the owner that names the path by hand.

    ``only`` selects the kinds in the answer, and its default is every kind.  One
    kind is not enough: ``'spells'`` sees a whole path in one literal alone, and
    the two hand-built copies of round 93 hold no such literal.  The shipped tree
    must hold no ``'spells'`` finding, because a literal that equals the path is a
    copy and the owner is its one home.
    """
    return [f'{relative}:{line} {kind} {text!r}'
            for relative, line, text, kind in sites if relative != OWNER and kind in only]


class ScanCornersOwnerTests(unittest.TestCase):
    def test_the_owner_states_the_name_once(self):
        owner = [site for site in copies() if site[0] == OWNER]
        self.assertEqual(
            1, len(owner),
            f'{OWNER} must state the name once, and it holds {owner}')
        self.assertEqual('spells', owner[0][3],
                         f'the one spelling of {OWNER} is a whole path, and it holds {owner[0]}')
        self.assertTrue(OWNER_VALUE and TOKENS[0] in OWNER_VALUE and TOKENS[1] in OWNER_VALUE,
                        f'the owner answers {OWNER_VALUE!r}, which does not name the file')

    def test_no_module_outside_the_owner_spells_the_path(self):
        found = problems(copies())
        self.assertEqual([], found,
                         'sites outside the owner name the scan corners path:\n'
                         + '\n'.join(found))

    def test_a_planted_copy_is_reported_with_its_file_and_its_line(self):
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text('import argparse\n'
                               'ap = argparse.ArgumentParser()\n'
                               f'ap.add_argument("--corners", default={OWNER_VALUE!r})\n',
                               encoding='utf-8')
            found = problems(copies([planted]), only=ALL)
        self.assertEqual(1, len(found), f'the scan did not see the planted copy: {found}')
        self.assertTrue(found[0].startswith(f'{planted}:3 '),
                        f'the report names no file and no line: {found[0]}')
        self.assertIn(OWNER_VALUE, found[0], f'the report hides the text: {found[0]}')

    def test_a_path_built_from_parts_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text('from pathlib import Path\n'
                               'ROOT = Path(".")\n'
                               'CORNERS = ROOT / "scan30" / "corners.json"\n'
                               'JOINED = "out/" + "scan30/corners.json"\n',
                               encoding='utf-8')
            found = problems(copies([planted]), only=ALL)
        self.assertNotEqual([], found, 'the scan did not see a path built from parts')
        self.assertTrue(all(text.startswith(f'{planted}:') for text in found),
                        f'a report names a site outside the planted module: {found}')
        self.assertTrue(any('builds' in text for text in found),
                        f'no report names the built path: {found}')
        for line in (3, 4):
            self.assertTrue(any(text.startswith(f'{planted}:{line} ') for text in found),
                            f'no report names the assembled line {line}: {found}')

    def test_a_quiet_word_inside_a_built_path_is_reported(self):
        # "./out" names no file by itself, and the scan must still see a module
        # that assembles the path from quiet parts.  The first part carries the
        # report, and it makes any change of the other parts visible too.
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text('from pathlib import Path\n'
                               'ROOT = Path("./out")\n'
                               'CORNERS = ROOT / "scan30" / "corners.json"\n'
                               'LONGER = "scan30/corners.json" + ".bak"\n',
                               encoding='utf-8')
            found = problems(copies([planted]), only=ALL)
        self.assertTrue(any(text.startswith(f'{planted}:3 builds') for text in found),
                        f'no report names the quiet part of a built path: {found}')
        self.assertTrue(any(text.startswith(f'{planted}:4 builds') for text in found),
                        f'no report names the whole path that a build also holds: {found}')
        self.assertFalse(any(text.startswith(f'{planted}:2 ') for text in found),
                         f'the scan reported a path that does not name the file: {found}')

    def test_a_built_path_without_the_file_name_is_quiet(self):
        # A module may build a path from "out" for any other file.  The two words
        # of the scan corners name must both be in the one expression.
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text('from pathlib import Path\n'
                               'OUT = Path("out")\n'
                               'SAMPLES = OUT / "scan30" / "samples.json"\n'
                               'FLAGS = OUT / "corners" / "flags.json"\n'
                               'BOTH = OUT / "scan30" / "corners.json"\n',
                               encoding='utf-8')
            found = problems(copies([planted]), only=ALL)
        self.assertTrue(found and all(text.startswith(f'{planted}:5 builds') for text in found),
                        f'the scan reported a path that does not name the file: {found}')
        for line in (3, 4):
            self.assertFalse(any(text.startswith(f'{planted}:{line} ') for text in found),
                             f'the scan reported a path with one word only: {found}')

    def test_a_module_that_reads_the_owner_is_quiet(self):
        with tempfile.TemporaryDirectory() as folder:
            reader = Path(folder) / 'reader.py'
            reader.write_text('from src import calib_segments\n'
                              'CORNERS = calib_segments.SCAN_CORNERS\n'
                              'from src.calib_segments import SCAN_CORNERS as PATH\n'
                              'SAME = PATH\n',
                              encoding='utf-8')
            found = problems(copies([reader]), only=ALL)
        self.assertEqual([], found, f'a reader of the owner was reported: {found}')

    def test_each_site_reads_the_owner(self):
        for site in SITES:
            with self.subTest(site=f'{site.relative} {site.name}'):
                if site.kind == 'signature':
                    answer = signature_read(site.relative, site.name, site.parameter)
                else:
                    answer = option_read(site.relative, site.name)
                self.assertIsNone(answer, answer or f'{site.relative} reads the owner: {site.name}')

    def test_each_site_is_on_the_line_this_module_records(self):
        # The brief gives the line of every site in the tree of round 88, and the
        # edit of round 89 moved each one.  A moved site changes no other file,
        # and the report of this module names both lines.
        for site in SITES:
            with self.subTest(site=f'{site.relative}:{site.now}'):
                if site.kind == 'signature':
                    where = statement_line(site.relative, lambda node: (
                        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name == site.name))
                else:
                    where = statement_line(site.relative, lambda node: (
                        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'add_argument' and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value == site.name))
                self.assertEqual(site.now, where,
                                 f'{site.relative} {site.name} is on line {where} now,'
                                 f' and this module records {site.now}')
                self.assertLess(site.line, site.now,
                                f'the brief gives {site.line}, and the site must move down')

    def test_each_site_keeps_a_live_default_equal_to_the_owner(self):
        from src.info_complete_scan import SCAN_CORNERS as ICS_PATH
        from src.eval_events import SCAN_CORNERS as EVENTS_PATH
        from src.timing_verify import SCAN_CORNERS as TIMING_PATH
        from src.sam3_ball_cache import SCAN_CORNERS as CACHE_PATH
        for name, value in (('src/info_complete_scan.py', ICS_PATH),
                            ('src/eval_events.py', EVENTS_PATH),
                            ('src/timing_verify.py', TIMING_PATH),
                            ('src/sam3_ball_cache.py', CACHE_PATH)):
            with self.subTest(module=name):
                self.assertIs(value, OWNER_VALUE,
                              f'{name} answers {value!r}, and the owner answers {OWNER_VALUE!r}')

    def test_a_hand_built_copy_of_the_path_is_reported(self):
        # One module may build the path from parts and hold no literal that equals
        # it.  A guard that reads the whole path in one literal only hides that
        # module, so this case plants one and reads the report of the full walk.
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text('from pathlib import Path\n'
                               'ROOT = Path(".")\n'
                               'CORNERS = ROOT / "out" / "scan30" / "corners.json"\n',
                               encoding='utf-8')
            found = problems(copies([planted]))
        self.assertTrue(found, 'the report hides a path that one module builds by hand')
        self.assertTrue(any(text.startswith(f'{planted}:3 {BUILT} ') for text in found),
                        f'no report names the hand-built site with its line: {found}')

    def test_the_default_report_reads_every_kind(self):
        # A guard that reads one kind alone answers nothing here: the planted
        # module holds two whole paths, so it holds no build.  The filter must
        # still answer the build of the one path that a module joins from parts.
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text('from pathlib import Path\n'
                               'ROOT = Path(".")\n'
                               'CORNERS = ROOT / "scan30" / "corners.json"\n',
                               encoding='utf-8')
            found = [text for text in problems(copies([planted]))
                     if text.startswith(f'{planted}:3 ')]
        self.assertTrue(found, 'the default report reads one kind only')
        self.assertEqual({BUILT}, {text.split()[1] for text in found},
                         f'the default report answers a kind that hides the build: {found}')

    def test_a_planted_local_default_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text('import argparse\n'
                               'def cloth_mask(bgr, corners_path="out/scan30/corners.json"):\n'
                               '    return bgr\n'
                               'ap = argparse.ArgumentParser()\n'
                               'ap.add_argument("--quad", default="out/scan30/corners.json")\n',
                               encoding='utf-8')
            with self.subTest(site='a signature default'):
                answer = signature_read(planted, 'cloth_mask', 'corners_path')
                self.assertIsNotNone(answer, 'the signature walk accepted a local default')
                self.assertIn(f'{planted}:2', answer)
            with self.subTest(site='an argparse default'):
                answer = option_read(planted, '--quad')
                self.assertIsNotNone(answer, 'the option walk accepted a local default')
                self.assertIn(f'{planted}:5', answer)


if __name__ == '__main__':
    unittest.main()
