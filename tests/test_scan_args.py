"""The four options of the move-scan command line have one home.

``--video``, ``--dataset``, ``--out-dir`` and ``--quad`` stood twice.  Each of the
two move-scan tools declared them in a nested helper of ``main``, once in
``src/motion_scan.py`` and once in ``src/track_before_detect.py``.  The two
helpers had the name ``common``, the same four calls and the same four defaults
(the walk of round 58 measured one body fingerprint, ``0742717844dd``).  The walk
of ``tests/test_duplicate_bodies.py`` reads module-level ``def`` s only, so it did
not read that pair.  One edit in one tool then changed one tool only.

Round 58 gave the four options one home, ``src/scan_args.py add_scan_options``,
and both tools call it.  This module holds that home two ways:

* ``option_sites`` reads the source of the three modules.  It visits every
  function at every depth, so a nested helper counts, and it reads the
  ``add_argument`` calls of one function only.  A missing option, a changed
  default, a fifth option and a second home each fail with the site and the
  option name.
* ``AnswerTest`` imports the two tools and calls ``build_parser``.  The command
  line a user answers is the parser, so that case reads the four names and the
  four defaults from the parser itself.

The measured command of round 58:

    git grep -n "common(\\|add_parser" -- src/motion_scan.py src/track_before_detect.py
    git grep -n '"video"\\|"dataset"\\|"out-dir"\\|"quad"' -- src/motion_scan.py src/track_before_detect.py

Run: ``./scripts/pool-test.sh python test_scan_args``
"""
from __future__ import annotations

import argparse
import ast
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The one module that adds the four options.
HOME = 'src/scan_args.py'

#: The function of that module that adds them.
OWNER = 'add_scan_options'

#: The two tools that read them.
TOOLS = ('src/motion_scan.py', 'src/track_before_detect.py')

#: Every module this walk reads.
WALKED = (HOME,) + TOOLS

#: The four options and the text of their defaults, as ``ast.unparse`` writes the
#: default with every space removed.  A changed default fails this walk.
PINNED = (('--video', 'None'),
          ('--dataset', "'vod30'"),
          ('--out-dir', "str(ROOT/'out'/'motion_scan')"),
          ('--quad', 'None'))

#: The names of the four options.
WANTED = tuple(name for name, _ in PINNED)

#: The one call that adds one option.
ADD = 'add_argument'


@dataclass(frozen=True)
class OptionSite:
    """One function that adds command-line options, and the options it adds.

    ``options`` holds the name of an option with the text of its default, in
    source order.  ``unreadable`` holds the lines of the calls whose option name
    is not a literal, so a call this walk cannot read is not silent.
    """
    module: str                # the path of the file from the root
    qualname: str              # the function name; a nested helper joins with a dot
    line: int                  # the line of the ``def``
    depth: int                 # 0 for a module-level function, 1 for a nested helper
    options: tuple             # ((option name, default text), ...)
    unreadable: tuple          # the lines of the calls with no literal name

    @property
    def site(self):
        """The site, as ``module:line function``."""
        return '%s:%d %s' % (self.module, self.line, self.qualname)

    @property
    def is_home(self):
        """True when this site is the one home of the four options."""
        return self.module == HOME and self.qualname == OWNER

    @property
    def wanted(self):
        """The names of the four options that this site adds."""
        return tuple(name for name, _ in self.options if name in WANTED)

    def named(self):
        """The options of this site, as ``--name=default``."""
        return ', '.join('%s=%s' % pair for pair in self.options) or 'no option'


def called_name(call):
    """The name of the function one call reads, or None."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


def default_text(node):
    """The text of the ``default`` keyword of one call, or None when it has none.

    The text is the ``ast.unparse`` form with every space removed, so two
    spellings of one default read the same.
    """
    for keyword in node.keywords:
        if keyword.arg == 'default':
            return ast.unparse(keyword.value).replace(' ', '')
    return None


def own_nodes(node):
    """Every node of one function's own body: the body of a nested ``def`` is not here.

    A nested helper is read as a site of its own, so its calls must not count
    twice.  This generator stops at a nested function and at a class.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield child
        yield from own_nodes(child)


def walk_functions(tree):
    """Every function of one module, with its nesting depth and its qualified name.

    A module-level function is depth 0.  A helper written inside another function
    is depth 1, and its name joins the names of its parents with a dot.  The
    round-58 pair sat at depth 1, inside ``main``, so a walk of the top level of a
    module cannot see that pair.  A method of a class is depth 0 here, because the
    depth counts functions and not classes.
    """
    found = []

    def visit(node, depth, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = '%s.%s' % (prefix, child.name) if prefix else child.name
                found.append((child, depth, qualname))
                visit(child, depth + 1, qualname)
            else:
                visit(child, depth, prefix)

    visit(tree, 0, '')
    return found


def option_sites_in(module, source):
    """Every site of one module that adds a command-line option, in source order."""
    tree = ast.parse(source, filename=module)
    sites = []
    for func, depth, qualname in walk_functions(tree):
        options, unreadable = [], []
        for node in own_nodes(func):
            if not (isinstance(node, ast.Call) and called_name(node) == ADD):
                continue
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                options.append((first.value, default_text(node)))
            else:
                unreadable.append(node.lineno)
        if options or unreadable:
            sites.append(OptionSite(module, qualname, func.lineno, depth,
                                    tuple(options), tuple(unreadable)))
    return sites


def option_sites():
    """Every option site of the three modules of this walk."""
    found = []
    for module in WALKED:
        path = ROOT / module
        found.extend(option_sites_in(module, path.read_text(encoding='utf-8')))
    return found


def scan_sites(sites):
    """The sites that add one of the four options, so the sites of this contract.

    A tool adds command-line options of its own (``--stride``, ``--channel``).  An
    option of that kind is not the business of this walk, so a site with none of
    the four options is out of the contract and this walk says nothing about it.
    """
    return [site for site in sites if site.wanted]


def problems(sites):
    """Every defect of one list of sites, as text that names the site and the option.

    Four defects are reported: a site of the contract that is not the one home, an
    option of the four that the home does not add, a default that is not the pinned
    default, and an option that the home adds beside the four.  A call whose option
    name is not a literal is reported too, because this walk cannot read it.
    """
    found = []
    for site in scan_sites(sites):
        names = dict(site.options)
        if not site.is_home:
            found.append('%s adds %s, and the one home of the four options is %s %s'
                         % (site.site, site.named(), HOME, OWNER))
        for name, text in PINNED:
            if name not in names:
                found.append('%s adds no %s' % (site.site, name))
            elif names[name] != text:
                found.append('%s adds %s with the default %s, and the pinned default is %s'
                             % (site.site, name, names[name], text))
        for name, _ in site.options:
            if name not in WANTED:
                found.append('%s adds %s, and the four shared options are %s'
                             % (site.site, name, ', '.join(WANTED)))
        for line in site.unreadable:
            found.append('%s:%d adds an option that this walk cannot read'
                         % (site.module, line))
    return found


def site_listing(sites):
    """The sites of one list, as ``module:line function``."""
    return ', '.join(site.site for site in sites) or 'nowhere'


def module_name(path):
    """The import name of one module, from its path: ``src/x.py`` answers ``src.x``."""
    return path[:-3].replace('/', '.')


class OneHomeTest(unittest.TestCase):
    """The four options of the two move-scan tools live in one module, once."""

    def test_the_walk_reads_both_tools_and_the_home(self):
        """A walk that reached no tool proves nothing about the two tools."""
        sites = option_sites()
        self.assertEqual(sorted(WALKED), sorted({site.module for site in sites}),
                         'the walk reached %s, and it must reach %s'
                         % (sorted({site.module for site in sites}), sorted(WALKED)))
        for tool in TOOLS:
            with self.subTest(tool=tool):
                held = [site for site in sites if site.module == tool]
                self.assertTrue(held, '%s holds no option site, so this walk read no command '
                                      'line of it' % tool)
                self.assertTrue(all(site.options for site in held),
                                '%s holds a site with no option' % tool)

    def test_the_four_options_have_one_home(self):
        """One site adds them, and that site is ``src/scan_args.py add_scan_options``."""
        sites = option_sites()
        scan = scan_sites(sites)
        self.assertEqual(1, len(scan),
                         'the four options stand at %d sites (%s), and their one home is %s %s'
                         % (len(scan), site_listing(scan), HOME, OWNER))
        self.assertTrue(scan[0].is_home,
                        'the four options live at %s, and their one home is %s %s'
                        % (scan[0].site, HOME, OWNER))
        self.assertEqual(WANTED, scan[0].wanted,
                         '%s adds %s, and the four options are %s'
                         % (scan[0].site, scan[0].named(), ', '.join(WANTED)))
        self.assertEqual(0, scan[0].depth,
                         '%s sits at depth %d, so the four options are not at the top of %s'
                         % (scan[0].site, scan[0].depth, HOME))
        self.assertEqual([], problems(sites),
                         'the walk of the three modules reports: %s' % problems(sites))

    def test_the_tools_add_none_of_the_four_options_themselves(self):
        """A tool that adds one of the four holds a second body of the four.

        The duplicate-body walk of ``tests/test_duplicate_bodies.py`` cannot see
        that second body, because it reads module-level ``def`` s only.
        """
        for site in option_sites():
            if site.module in TOOLS:
                with self.subTest(site=site.site):
                    self.assertEqual((), site.wanted,
                                     '%s of %s adds %s, and the one home is %s %s'
                                     % (site.site, site.module, site.wanted, HOME, OWNER))


class ForgedSourceTest(unittest.TestCase):
    """The walk reports a defect of a source written for the case."""

    def test_a_nested_helper_that_misses_one_option_is_reported(self):
        """The round-58 blind spot: a helper inside ``main``, and one option is gone."""
        forged = ('def main(argv=None):\n'
                  '    def common(p):\n'
                  '        p.add_argument("--video", default=None)\n'
                  '        p.add_argument("--dataset", default="vod30")\n'
                  '        p.add_argument("--out-dir", default=str(ROOT / "out" / "motion_scan"))\n'
                  '    return None\n')
        sites = option_sites_in(TOOLS[0], forged)
        self.assertEqual(1, len(sites),
                         'the walk of a nested helper found %d sites (%s), and one must appear'
                         % (len(sites), site_listing(sites)))
        self.assertEqual(1, sites[0].depth,
                         '%s reads as depth %d, and a helper inside main sits at depth 1'
                         % (sites[0].site, sites[0].depth))
        self.assertEqual('main.common', sites[0].qualname,
                         'the walk names the site %s, and a helper inside main is main.common'
                         % sites[0].qualname)
        found = problems(sites)
        self.assertTrue(any('--quad' in text for text in found),
                        'the walk must name the missing option, and it answers: %s' % found)
        self.assertTrue(any(sites[0].site in text for text in found),
                        'the walk must name the site %s, and it answers: %s'
                        % (sites[0].site, found))

    def test_a_second_home_and_a_fifth_option_are_reported(self):
        """A tool that adds the four again is a second home, and a fifth option is not silent."""
        forged = ('def build_parser():\n'
                  '    p = ap.add_parser("scan")\n'
                  '    p.add_argument("--video", default=None)\n'
                  '    p.add_argument("--dataset", default="vod30")\n'
                  '    p.add_argument("--out-dir", default=str(ROOT / "out" / "motion_scan"))\n'
                  '    p.add_argument("--quad", default=None)\n'
                  '    p.add_argument("--scale", default=1)\n'
                  '    return p\n')
        sites = option_sites_in(TOOLS[1], forged)
        found = problems(sites)
        self.assertEqual(1, len(sites), 'the walk found %d sites' % len(sites))
        self.assertTrue(any(sites[0].site in text for text in found),
                        'the walk must name the site %s, and it answers: %s'
                        % (sites[0].site, found))
        self.assertTrue(any('--scale' in text for text in found),
                        'the walk must report the fifth option --scale, and it answers: %s' % found)
        self.assertEqual(('--video', '--dataset', '--out-dir', '--quad'), sites[0].wanted,
                         '%s adds %s, and the four options are %s'
                         % (sites[0].site, sites[0].named(), ', '.join(WANTED)))

    def test_a_changed_default_is_reported(self):
        """The one home with another default fails, and the message holds the option name."""
        forged = ('def add_scan_options(p):\n'
                  '    p.add_argument("--video", default=None)\n'
                  '    p.add_argument("--dataset", default="vod31")\n'
                  '    p.add_argument("--out-dir", default=str(ROOT / "out" / "motion_scan"))\n'
                  '    p.add_argument("--quad", default=None)\n'
                  '    return p\n')
        sites = option_sites_in(HOME, forged)
        found = problems(sites)
        self.assertEqual(1, len(sites), 'the walk found %d sites' % len(sites))
        self.assertEqual([], [text for text in found if '--video' in text or '--quad' in text],
                         'the three other options are unchanged, so only --dataset must fail: %s'
                         % found)
        self.assertTrue(any('--dataset' in text and 'vod31' in text for text in found),
                        'the walk must name --dataset and the new default, and it answers: %s'
                        % found)


class AnswerTest(unittest.TestCase):
    """Both tools answer the same four options, read from the parser they build.

    This class imports the two tools and calls ``build_parser``.  The write of the
    four options is one fact, and the command line a user answers is the parser,
    so this class reads the names and the defaults from the parser itself and not
    from the source text.  The import is cheap in this checkout, and the two tool
    suites import the same modules already.
    """

    #: The four options and the value the parser must answer for each one.
    EXPECTED = (('--video', None),
                ('--dataset', 'vod30'),
                ('--out-dir', str(ROOT / 'out' / 'motion_scan')),
                ('--quad', None))

    #: The subcommands of the two tools.  The repair keeps every one of them.
    SUBCOMMANDS = (('src/motion_scan.py', ('scan', 'report', 'strips', 'channels', 'person')),
                   ('src/track_before_detect.py', ('null', 'eval')))

    def built(self):
        """{module name: {subcommand: (the subparser, a namespace of no argument)}}."""
        from src import motion_scan, track_before_detect
        found = {}
        for mod in (motion_scan, track_before_detect):
            subs = next(action for action in mod.build_parser()._actions
                        if isinstance(action, argparse._SubParsersAction))
            found[mod.__name__] = {name: (parser, parser.parse_args([]))
                                   for name, parser in subs.choices.items()}
        return found

    def answered(self, parser, namespace):
        """{option name: the value the parser answers} for the four options."""
        return {name: getattr(namespace, parser._option_string_actions[name].dest)
                for name, _ in self.EXPECTED if name in parser._option_string_actions}

    def test_every_subcommand_answers_the_four_options(self):
        """A subcommand that stopped calling the home loses an option here."""
        for module, subcommands in self.built().items():
            for name, (parser, namespace) in subcommands.items():
                with self.subTest(module=module, subcommand=name):
                    self.assertEqual(dict(self.EXPECTED), self.answered(parser, namespace),
                                     '%s %s answers %s, and the four options are %s'
                                     % (module, name, self.answered(parser, namespace),
                                        dict(self.EXPECTED)))

    def test_the_two_tools_keep_their_subcommands_and_answer_one_set(self):
        """The repair keeps the five and the two subcommands, and one set of four values."""
        built = self.built()
        for module, names in self.SUBCOMMANDS:
            with self.subTest(module=module):
                name = module_name(module)
                self.assertIn(name, built, 'the walk did not read %s' % module)
                self.assertEqual(names, tuple(built[name]),
                                 '%s answers the subcommands %s, and they are %s'
                                 % (module, tuple(built[name]), names))
        first, second = (built[module_name(module)] for module, _ in self.SUBCOMMANDS)
        one = self.answered(*first['scan'])
        two = self.answered(*second['null'])
        self.assertEqual(one, two,
                         'the two tools answer %s and %s, and the four options have one home'
                         % (one, two))
        self.assertEqual(str(ROOT / 'out' / 'motion_scan'), one['--out-dir'],
                         'the --out-dir default is %s, and the bytes of today are %s'
                         % (one['--out-dir'], str(ROOT / 'out' / 'motion_scan')))

    def test_the_home_answers_the_same_out_dir_bytes_as_the_tools(self):
        """``src/scan_args.py`` sits in ``src/``, so its ``ROOT`` is the same root."""
        from src import scan_args
        self.assertEqual(ROOT, scan_args.ROOT,
                         'the home reads its root as %s, and the repository root is %s'
                         % (scan_args.ROOT, ROOT))
        self.assertTrue(callable(scan_args.add_scan_options),
                        '%s does not hold %s' % (HOME, OWNER))
        self.assertEqual(OWNER, scan_args.add_scan_options.__name__,
                         '%s holds %s, and the one home of the four options is %s'
                         % (HOME, scan_args.add_scan_options.__name__, OWNER))


if __name__ == '__main__':
    unittest.main()
