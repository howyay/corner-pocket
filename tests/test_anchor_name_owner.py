"""The anchor file name of a dataset has one owner: ``src/calib_segments.py``.

Round 82 found the name spelled in fifteen files: five frozen ``ANCHORS`` constants,
five readers that built the path by hand, the owner's own ``STATIC_REFERENCES`` row,
the two ``--anchors`` defaults, and two prose strings.  A rename of the file then
needed fifteen edits, and a reader that missed one read a file that does not exist.

The owner now answers three names: :func:`anchors_reference_path` (the path from the
out/ root), :func:`anchors_reference_name` (the file name alone), and the two ends
``ANCHORS_HEAD`` and ``ANCHORS_SUFFIX`` for a reader that joins a name to a folder or
that matches a stored name.

Two sites keep the text as a frozen literal: a default of an argparse option appears
in ``--help`` and in a recorded command line, so those two keep the text.  The cases
below hold each frozen site equal to the owner.

The scan reads the used strings of the shipped trees.  A test that states an
expectation is not shipped code (tests/_shipped.py), so the trees under test are the
four packages only.

Do not weaken a check to make a change pass.
"""
import ast
import pathlib
import sys
import tempfile
import unittest
from typing import NamedTuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from _shipped import code_strings, shipped_modules
from src.calib_segments import (ANCHORS_HEAD, ANCHORS_SUFFIX, STATIC_REFERENCES,
                                anchors_reference_name, anchors_reference_path)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OWNER = 'src/calib_segments.py'
SPELLED = 'pid_anchors'
DATASET = 'vod30'
FROZEN_WHY = ('argparse prints this default in --help, and a recorded command line '
              'holds the text')


class FrozenSite(NamedTuple):
    """One site that must keep the name as a literal, and the reason it must."""

    relative: str
    flag: str
    literal: str
    why: str


#: The sites that stay frozen.  Every other site reads the owner.  A site that
#: appears here is held equal to the owner by
#: :meth:`AnchorNameOwnerTests.test_every_frozen_site_holds_the_owner_name`, and a
#: site whose code disappears fails
#: :meth:`AnchorNameOwnerTests.test_every_frozen_entry_is_still_used`.
FROZEN = (
    FrozenSite('src/eval_events.py', '--anchors', 'out/pid_anchors_vod30.json', FROZEN_WHY),
    FrozenSite('src/timing_verify.py', '--anchors', 'out/pid_anchors_vod30.json', FROZEN_WHY),
)


def spelled_sites(paths=None) -> list:
    """(relative, line, text) for every used string of the shipped tree that names it.

    A docstring is not a used string (``tests/_shipped.py`` drops it), so the cases
    below report a reader, and not the prose that explains it.
    """
    found = []
    for path in (shipped_modules() if paths is None else paths):
        relative = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
        for line, text in code_strings(ast.parse(path.read_text(encoding='utf-8'))):
            if SPELLED in text:
                found.append((relative, line, text))
    return found


def spell_problems(sites) -> list:
    """A line per site that spells the name and is neither the owner nor a frozen site."""
    frozen = {(site.relative, site.literal) for site in FROZEN}
    problems = []
    for relative, line, text in sites:
        if relative == OWNER or (relative, text) in frozen:
            continue
        problems.append(f'{relative}:{line} spells {text!r}; the owner of that name is {OWNER}')
    return problems


def arg_default(relative: str, flag: str) -> list:
    """The literal default of every argparse option ``flag`` of one module."""
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'))
    answers = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')
        first = node.args[0]
        if name != 'add_argument' or not (isinstance(first, ast.Constant) and first.value == flag):
            continue
        for keyword in node.keywords:
            if keyword.arg == 'default':
                answers.append(keyword.value.value if isinstance(keyword.value, ast.Constant) else keyword.value)
    return answers


class AnchorNameOwnerTests(unittest.TestCase):
    def test_no_other_module_spells_the_anchor_name(self):
        problems = spell_problems(spelled_sites())
        self.assertEqual([], problems, 'sites outside the owner spell the name:\n' + '\n'.join(problems))

    def test_the_scan_sees_a_planted_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            planted = pathlib.Path(folder) / 'reader.py'
            planted.write_text('PATH = "out/pid_anchors_vod30.json"\n', encoding='utf-8')
            sites = spelled_sites([planted])
            problems = spell_problems(sites)
        self.assertNotEqual([], problems, 'the scan did not see a planted copy; it answered ' + repr(sites))
        self.assertTrue(any('pid_anchors_vod30.json' in problem for problem in problems),
                        'the report does not name the planted copy; it answered ' + repr(problems))

    def test_every_frozen_site_holds_the_owner_name(self):
        problems = []
        for site in FROZEN:
            answers = arg_default(site.relative, site.flag)
            if answers != [site.literal]:
                problems.append(f'{site.relative} {site.flag} answers {answers!r}, '
                                f'and the frozen site holds {site.literal!r}')
            if site.literal != anchors_reference_path(DATASET):
                problems.append(f'{site.relative} freezes {site.literal!r}, and the owner answers '
                                f'{anchors_reference_path(DATASET)!r} ({site.why})')
        self.assertEqual([], problems, 'a frozen site drifted from the owner:\n' + '\n'.join(problems))

    def test_every_frozen_entry_is_still_used(self):
        used = {(relative, text) for relative, _, text in spelled_sites() if relative != OWNER}
        expected = {(site.relative, site.literal) for site in FROZEN}
        self.assertEqual(set(), expected - used,
                         'a frozen entry outlived its code; remove it from FROZEN: ' + repr(sorted(expected - used)))

    def test_the_owner_holds_one_spelling_and_derives_the_rest(self):
        sites = [site for site in spelled_sites() if site[0] == OWNER]
        self.assertEqual(1, len(sites),
                         'the owner must hold one spelling of the name, and it holds ' + repr(sites))
        self.assertEqual('out/pid_anchors_{dataset}.json', sites[0][2],
                         'the one spelling of the owner is the format of the name')
        self.assertEqual(anchors_reference_name(DATASET), STATIC_REFERENCES[DATASET]['file'],
                         'the owner reads its own second site from the derivation')

    def test_the_two_owner_answers_agree(self):
        name = anchors_reference_name(DATASET)
        self.assertEqual(ANCHORS_HEAD + DATASET + ANCHORS_SUFFIX, name)
        self.assertEqual('out/' + name, anchors_reference_path(DATASET))
        self.assertEqual('out/other.json', anchors_reference_path(DATASET, 'out/other.json'),
                         'a caller that names its own path must keep it')
        self.assertNotEqual(anchors_reference_name('highlight'), name,
                            'a second dataset must move the name, not keep the vod30 file')


if __name__ == '__main__':
    unittest.main()
