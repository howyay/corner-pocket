"""The vod30 rebuild document has one owner of its name: ``src/events_document.py``.

Round 89 found the name ``events_v2.json`` spelled four times: the owner states
it as ``V2``, and three import-time readers built the path by hand.

    ``src/pid_shooter.py:39``, ``src/pid_shooter2.py:35`` and
    ``src/pid_associate.py:123`` held the same statement:
    ``json.load(open(os.path.join(REPO, "out", "scan30", "events_v2.json")))``.

The four spellings agreed, so a rename of the document moved the writer
(``src/rebuild_events_v2.py``) alone and left three readers pointed at a file
that no longer exists.

The owner answers a path helper, so the three readers call
``events_document.document_path(events_document.V2, root=REPO)``. Each reader
keeps its own base rule, and it takes the name from the owner alone. The bytes
on disk do not move, so this round changes no document and no measurement.

The cases below hold five things:

1. the owner states the name once, and it binds it to ``V2`` at module level;
2. no shipped module spells the name outside the owner and
   ``ALLOWED_TEST_MODULES``;
3. a planted copy is reported with its file and its line;
4. a module that imports the owner and holds no claim of its own is quiet;
5. each of the three readers imports the owner and reads ``V2`` through
   ``document_path``.

The scan reads the used strings of the shipped packages (``src``, ``annotator``,
``tools``, ``scripts``), as ``tests/test_anchor_name_owner.py`` does for the
anchor name and ``tests/test_pid_identity_owner.py`` does for the identity file.
A docstring is not a used string (``tests/_shipped.py`` drops it), so the prose
that explains the name does not fail the rule. That is why the list above may
hold the name inside its own text.

What this case does not see
---------------------------
* it reads the text of a string literal, not the value a name holds at run
  time. A reader that builds the name at run time from a stored fragment passes
  the scan. Case 5 closes that gap for the three readers of this round;
* a module that reaches the document through another module passes, because
  that module is the reader and this scan reads the reader alone;
* it does not run a reader. ``src/pid_shooter.py``, ``src/pid_shooter2.py`` and
  ``src/pid_associate.py`` are scripts: they open the video and the weights at
  import time, so no case here imports one of them.

Do not weaken a check to make a change pass.
"""
import ast
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shipped import SHIPPED, code_strings, shipped_modules  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'src/events_document.py'

#: The one spelling of the name, as the owner holds it in ``V2``.
NAME = 'events_v2.json'

#: The name the owner binds the spelling to.  A later module reads this name.
BINDING = 'V2'

#: The helper the three readers call.  It answers the path, so a reader needs no
#: second spelling of a folder and no copy of the file name.
HELPER = 'document_path'

#: The test modules that may spell the name.  This case must know what the owner
#: states, and it states the answer once, here.  A shipped module has no entry.
ALLOWED_TEST_MODULES = ('tests/test_events_document_owner.py',)

#: The three import-time readers of this round, as paths from the repository
#: root.  Each one reads the name through the owner.
READERS = (
    'src/pid_shooter.py',
    'src/pid_shooter2.py',
    'src/pid_associate.py',
)


def spellings(paths=None):
    """``(path, line, text)`` for every used string of the tree that holds the name.

    A docstring is not a used string (``tests/_shipped.py`` drops it), so the
    prose that explains the name does not appear in the answer.  ``path`` is the
    path the walk read, which is a temporary file when a case plants one.

    The walk answers the paths first and reads them after, so a file that another
    writer of this checkout removed between the two steps has no text to report.
    Such a path is skipped: it is not a module the tree ships.
    """
    found = []
    for path in (shipped_modules() if paths is None else paths):
        try:
            source = path.read_text(encoding='utf-8')
        except FileNotFoundError:
            continue
        tree = ast.parse(source, filename=str(path))
        for line, text in code_strings(tree):
            if NAME in text:
                found.append((Path(path), line, text))
    return found


def shown(path: Path) -> str:
    """The path of a site, relative to the repository root when it sits inside it."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def problems(sites) -> list:
    """A line per site that spells the name and may not."""
    out = []
    for path, line, text in sites:
        relative = shown(path)
        if relative == OWNER or relative in ALLOWED_TEST_MODULES:
            continue
        out.append(f'{relative}:{line} spells {text!r}; the owner of that name is '
                   f'{OWNER}, and it binds it to {BINDING}')
    return out


def dotted(node) -> str:
    """The dotted name of an expression, or "" for any other expression."""
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f'{base}.{node.attr}' if base else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ''


def reads_the_name(tree, helper=HELPER, binding=BINDING) -> bool:
    """True when one tree reads the name of the document through the owner.

    A read is a call of ``events_document.<helper>(events_document.<binding>)``,
    with or without a ``root`` keyword: the first argument must be the name the
    owner binds, and the call must be attributed to ``events_document``.  The
    reader binds the answer to its own constant and keeps its own root, so the
    case reads this shape alone and not the name of the target.
    """
    wanted = f'events_document.{helper}'
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or dotted(node.func) != wanted or not node.args:
            continue
        if dotted(node.args[0]) == f'events_document.{binding}':
            return True
    return False


def owner_binding(tree, name=BINDING):
    """The value node of one module-level binding of the owner, or None."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets):
            return node.value
    return None


class EventsDocumentOwnerTests(unittest.TestCase):
    def test_the_owner_states_the_name_once_and_binds_it(self):
        tree = ast.parse((ROOT / OWNER).read_text(encoding='utf-8'), filename=OWNER)
        sites = [(line, text) for line, text in code_strings(tree) if NAME in text]
        self.assertEqual(
            1, len(sites),
            f'{OWNER} holds the name on {len(sites)} line(s) that are not a docstring: '
            f'{sites}. The owner states it once, as {BINDING}.')
        value = owner_binding(tree)
        self.assertIsNotNone(
            value, f'{OWNER} has no module-level binding of {BINDING}, so no reader can '
                   f'name the document through it')
        stated = value.value if isinstance(value, ast.Constant) else None
        self.assertEqual(
            NAME, stated,
            f'{OWNER} binds {BINDING} to {stated!r}, not to the name {NAME!r}')

    def test_no_shipped_module_spells_the_name_outside_the_owner(self):
        self.assertEqual(
            ('src', 'annotator', 'tools', 'scripts'), SHIPPED,
            'the shipped packages of tests/_shipped.py moved, so this scan reads another tree')
        found = problems(spellings())
        self.assertEqual(
            [], found,
            'sites outside the owner spell the name:\n' + '\n'.join(found))

    def test_the_scan_reports_a_planted_copy_with_its_file_and_its_line(self):
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text(
                'import json\n'
                f'EVENTS = json.load(open("out/scan30/{NAME}"))\n',
                encoding='utf-8')
            sites = spellings([planted])
        self.assertEqual(
            1, len(sites),
            f'the scan answered {sites} for one planted copy on line 2 of {planted}')
        path, line, _ = sites[0]
        self.assertEqual(2, line, f'the scan named line {line}, not line 2')
        self.assertEqual(planted, path, f'the scan named {path}, not {planted}')
        found = problems(sites)
        self.assertEqual(1, len(found), f'the scan did not report the planted copy: {sites}')
        self.assertTrue(
            found[0].startswith(f'{planted}:2 spells '),
            f'the report does not name the file and the line: {found[0]}')

    def test_a_module_that_reads_the_owner_is_quiet(self):
        with tempfile.TemporaryDirectory() as folder:
            reader = Path(folder) / 'reader.py'
            reader.write_text(
                'from src import events_document\n'
                f'EVENTS = events_document.{HELPER}(events_document.{BINDING}, root=ROOT)\n',
                encoding='utf-8')
            found = problems(spellings([reader]))
        self.assertEqual([], found, f'a reader of the owner was reported: {found}')
        shipped = [shown(path) for path, _, _ in spellings()]
        self.assertEqual(
            [OWNER], shipped,
            f'the shipped tree spells the name at {shipped}; the owner is its one home')

    def test_each_reader_reads_the_name_from_the_owner(self):
        for relative in READERS:
            with self.subTest(module=relative):
                tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'),
                                 filename=relative)
                self.assertTrue(
                    reads_the_name(tree),
                    f'{relative} does not read the name through the owner. A reader calls '
                    f'events_document.{HELPER}(events_document.{BINDING}), so the owner '
                    f'alone names the document of a rename.')


if __name__ == '__main__':
    unittest.main()
