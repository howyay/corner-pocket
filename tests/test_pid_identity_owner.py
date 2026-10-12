"""The identity reference file has one owner: ``src/pid_identity.py``.

Round 88 found the name of ``out/pid_identity_v0.json`` spelled four times: the
writer in ``src/pid_identity.py``, and three import-time readers,
``src/pid_osnet.py``, ``src/pid_shooter.py`` and ``src/pid_shooter2.py``.  Each
reader held the byte-identical literal ``"out" / "pid_identity_v0.json"``.  The
four spellings agreed, so a rename of the file moved the writer alone and left
three readers pointed at a file that no longer exists.

The owner states the name once, as ``IDENTITY_REFERENCE``, and the three readers
take the path from it.  The bytes on disk do not move, so this round changes no
document and no measurement.

The scan reads the used strings of the shipped packages (``src``, ``annotator``,
``tools``, ``scripts``), as ``tests/test_anchor_name_owner.py`` does for the
anchor name.  A docstring is not a used string (``tests/_shipped.py`` drops it),
so the prose that explains the name does not fail the rule.

What this case does not see
---------------------------
* it reads the text of a string literal, not the value a name holds at run time.
  A reader that builds the name at run time from a stored fragment passes the
  scan.  The four derivation cases below close that gap for the three readers of
  this round;
* a module that reaches the file through another module passes, because that
  module is the reader and this scan reads the reader alone;
* it does not run the writer.  ``src/pid_identity.py`` is a script, so no case
  here opens the video or writes the document.

Do not weaken a check to make a change pass.
"""
import ast
import dataclasses
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shipped import code_strings, shipped_modules

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'src/pid_identity.py'

#: The one spelling of the name: the path from the repository root, and the value
#: ``IDENTITY_REFERENCE`` holds.
NAME = 'out/pid_identity_v0.json'

#: The distinct part of the name.  A report reads this fragment, so it names a
#: later spelling of the file even when the occurrence marker around it moves:
#: ``pid_identity_v1.json`` fails, and a copy of the fragment alone fails.
FRAGMENT = 'pid_identity_v0'

#: The tail of the name the fragment does not cover: the extension.
SUFFIX = '.json'


@dataclasses.dataclass(frozen=True)
class Reader:
    """One module that takes the name from the owner, and the name it binds."""

    relative: str
    name: str


#: The three import-time readers of this round.  Each one binds the owner's path
#: under its own name, so the case below reads a binding and not a docstring.
DERIVED = (
    Reader('src/pid_osnet.py', 'IDENTITY_REFERENCE'),
    Reader('src/pid_shooter.py', 'IDENTITY_REFERENCE'),
    Reader('src/pid_shooter2.py', 'IDENTITY_REFERENCE'),
)


def _is_occurrence(part: str) -> bool:
    """True when ``part`` is one occurrence marker of the name, and nothing else.

    An empty part is a marker, the ``.json`` tail is a marker, and ``v0.json`` is
    a marker.  A bracket, a space or a second path means the text continues
    around the fragment, so the answer is False and the string is not this name.
    """
    return all(character.isalnum() or character in '._' for character in part)


def names_the_reference(text: str) -> bool:
    """True when one string literal says the name of the identity document.

    The parse removes the fragment once, then reads the two parts it left.  The
    part in front must be a folder path, because the writer states the name from
    the repository root: ``out/``.  The part behind must be the extension or
    nothing, so a copy that adds a second extension is not this name.

    The rule reads one folder name and not a chain of them.  The name of this
    round stands in one folder, and a chain needs an earlier separator that this
    parse does not read.  Add the chain when a caller states one.
    """
    if text.count(FRAGMENT) != 1:
        return False
    head, tail = text.split(FRAGMENT)
    return (head.endswith('/') and _is_occurrence(head[:-1])
            and tail in ('', SUFFIX))


def spelled_sites(paths=None) -> list:
    """(relative, line, text) for every used string of the shipped tree that says the name.

    A path outside the repository answers its own path, so a guest file in a
    temporary folder reports an absolute name and the rules below still work.
    """
    found = []
    for path in (shipped_modules() if paths is None else paths):
        relative = (path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT)
                    else path.as_posix())
        for line, text in code_strings(ast.parse(path.read_text(encoding='utf-8'))):
            if names_the_reference(text):
                found.append((relative, line, text))
    return found


def spell_problems(sites) -> list:
    """One line per site that says the name and is not the owner."""
    return [f'{relative}:{line} spells {text!r}; the owner of that name is {OWNER}'
            for relative, line, text in sites if relative != OWNER]


def imported_names(tree) -> dict:
    """The local name of every name one module imports from a module named pid_identity."""
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or '').endswith('pid_identity'):
            for alias in node.names:
                imported[alias.asname or alias.name] = node.lineno
    return imported


def bound_names(tree, names) -> set:
    """(name, line) for every module-level name one module binds to one of its imported names.

    The value may use the imported name at any depth.  ``src/pid_osnet.py`` reads
    the path inside ``json.load(open(...))``, and ``src/pid_shooter.py`` reads it
    in the same way, so a rule that looked at a bare ``Name`` value alone would
    report neither reader.
    """
    bound = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if not any(isinstance(child, ast.Name) and child.id in names
                   for child in ast.walk(value)):
            continue
        bound.update((target.id, node.lineno)
                     for target in targets if isinstance(target, ast.Name))
    return bound


def derives_the_reference(tree) -> bool:
    """True when one module binds a module-level name to the owner's ``IDENTITY_REFERENCE``."""
    return bool(bound_names(tree, imported_names(tree)))


def stated_name(relative: str, name: str) -> str:
    """The string the module binds to ``name`` at module level.

    The scan reads the source text and does not import the module.  The three
    readers and the owner all import ``cv2`` and a video reader, so an import
    here would fail on a machine without them.
    """
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'))
    lines = {line: text for line, text in code_strings(tree)}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if name in targets:
            return lines[node.value.lineno]
    raise AssertionError(f'{relative} does not bind {name} at module level')


class IdentityNameOwnerTest(unittest.TestCase):
    """The owner states the name once, and no other shipped module spells it."""

    def test_the_owner_states_the_name_once(self):
        sites = [site for site in spelled_sites() if site[0] == OWNER]
        self.assertEqual(1, len(sites),
                         f'{OWNER} must state the name once, and it holds ' + repr(sites))
        self.assertEqual(NAME, sites[0][2])

    def test_the_fragment_is_the_name_without_its_occurrence_marker(self):
        self.assertIn(FRAGMENT, NAME,
                      'the fragment must catch a spelling of the name it belongs to')
        self.assertTrue(names_the_reference(NAME),
                        'the fragment must report the name of the owner')
        self.assertEqual(f'{FRAGMENT}{SUFFIX}', Path(NAME).name)

    def test_the_default_name_is_the_name_of_this_case(self):
        self.assertEqual(NAME, stated_name(OWNER, 'IDENTITY_REFERENCE'),
                         'the owner answers ' + repr(stated_name(OWNER, 'IDENTITY_REFERENCE')))

    def test_no_other_module_spells_the_name(self):
        problems = spell_problems(spelled_sites())
        self.assertEqual([], problems,
                         'sites outside the owner spell the name:\n' + '\n'.join(problems))

    def test_the_scan_sees_a_planted_copy(self):
        """A second spelling must answer its line, so the case above cannot pass in silence."""
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text(f'PATH = "{NAME}"\n', encoding='utf-8')
            sites = spelled_sites([planted])
            problems = spell_problems(sites)
        self.assertNotEqual([], problems,
                            'the scan did not see a planted copy; it answered ' + repr(sites))
        self.assertTrue(any(NAME in problem for problem in problems),
                        'the report does not name the planted copy; it answered ' + repr(problems))

    def test_the_scan_refuses_a_text_that_carries_the_fragment_inside_a_sentence(self):
        """A prose string or another path may name the file; it is not this name."""
        self.assertFalse(names_the_reference('see out/pid_identity_v0.json for the prototypes'))
        self.assertFalse(names_the_reference(''))
        self.assertFalse(names_the_reference('pid_identity'))
        self.assertFalse(names_the_reference('out/pid_identity_v0.json.bak'),
                         'the name must stand at the end of the text')
        self.assertTrue(names_the_reference(NAME),
                        'the name of the owner is a spelling of the name')
        self.assertTrue(names_the_reference('out/pid_identity_v0'),
                        'the name without its extension is a spelling of the name')
        self.assertTrue(names_the_reference('runs/pid_identity_v0.json'),
                        'the name from another folder is a spelling of the name')

    def test_an_unknown_module_joins_the_scan_before_it_ships(self):
        """The scan reads the shipped tree, so a new module that spells the name fails."""
        found = sorted(relative for relative, _, _ in spelled_sites())
        self.assertEqual([OWNER], found,
                         'a shipped module outside ' + OWNER + ' spells the name: ' + repr(found))

    def test_a_new_reader_of_the_name_fails_before_it_ships(self):
        """The binding rule must see a module that takes the name, and it holds no string.

        The guest module spells no path.  A guard that read string literals alone
        answers nothing here, so the case fails and names the doubt.
        """
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text('from src.pid_identity import IDENTITY_REFERENCE\n'
                               'PATH = IDENTITY_REFERENCE\n', encoding='utf-8')
            tree = ast.parse(planted.read_text(encoding='utf-8'))
            derived = derives_the_reference(tree)
            spelled = spelled_sites([planted])
        self.assertTrue(derived, 'the binding rule did not see a module that takes the name')
        self.assertEqual([], spelled,
                         'the guest module must hold no path, or the case proves nothing')

    def test_the_three_readers_import_the_name_from_the_owner(self):
        for reader in DERIVED:
            tree = ast.parse((ROOT / reader.relative).read_text(encoding='utf-8'))
            self.assertIn(reader.name, imported_names(tree),
                          f'{reader.relative} does not import {reader.name} from {OWNER}')

    def test_every_module_that_derives_the_name_is_a_declared_reader(self):
        """The three readers of this round are the whole derivation, and no more.

        The check reads the binding of every shipped module, so the list below
        cannot drift from the tree: a module that joins the derivation fails here
        until a reader names it, and a declared reader that stops deriving fails
        too.
        """
        declared = {reader.relative for reader in DERIVED}
        bound = set()
        for path in shipped_modules():
            relative = path.relative_to(ROOT).as_posix()
            if relative == OWNER:
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            if derives_the_reference(tree):
                bound.add(relative)
        self.assertEqual(sorted(declared), sorted(bound),
                         'a module that binds the owner name is not in DERIVED, or the reverse')

    def test_a_reader_holds_no_second_path_to_the_document(self):
        """Each declared reader is a shipped module, and it spells the name nowhere.

        A reader that keeps its own copy of the path passes the import case above
        and fails here, so the two cases hold the two halves of the rule.
        """
        shipped = {path.relative_to(ROOT).as_posix() for path in shipped_modules()}
        spelled = {relative for relative, _, _ in spelled_sites()}
        for reader in DERIVED:
            self.assertIn(reader.relative, shipped,
                          f'{reader.relative} is not a module of the shipped tree')
            self.assertNotIn(reader.relative, spelled,
                             f'{reader.relative} spells the name; it must read {OWNER} instead')


if __name__ == '__main__':
    unittest.main()
