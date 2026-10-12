"""The document names of a scan have one owner: ``src/events_document.py``.

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

Round 94 found the served name ``events.json`` spelled by hand six times: the owner
states it as ``SERVED``, and five readers plus one command line default built the
path by hand.  The list below holds those lines as round 94 found them, before this
round moved them.

    ``src/info_complete_scan.py:431``, ``src/motion_scan.py:2333`` and ``:2336``,
    ``src/segment_calib_report.py:43``, ``src/store.py:399`` and
    ``src/timing_verify.py:790`` held the file name in their own text.

Five of the six sites read the name through the owner now, so a rename moves the
owner alone.  One site keeps its literal: ``src/eval_events.py`` states the default
of ``--candidates``, and argparse prints that string in ``--help`` while a recorded
command line holds it.  The case below holds that literal equal to the answer of the
owner, so the two cannot drift apart.

The annotator console spells the name at six sites of its own.  That console is
another round's work, so this case counts those sites instead of moving them, and a
seventh site fails the count.

The cases below hold eight things:

1. the owner states each of the two names once, and it binds it at module level;
2. no shipped module spells a name outside the owner, ``ALLOWED_TEST_MODULES``
   and the declared sites below;
3. a planted copy is reported with its file and its line;
4. a module that imports the owner and holds no claim of its own is quiet;
5. each of the three ``V2`` readers imports the owner and reads ``V2`` through
   ``document_path``;
6. each of the five served-name readers calls ``document_path`` or ``document_in``
   with ``SERVED``, so the owner alone names the served document;
7. the frozen literal of ``src/eval_events.py`` equals the answer of the owner and
   is still the default of ``--candidates``;
8. the six sites of ``annotator/`` keep their declared count.

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
  import time, so no case here imports one of them;
* it reads a literal, so it cannot see whether the annotator console reads the same
  file at run time.  The count of case 8 is the whole claim about that console;
* the frozen literal of ``src/eval_events.py`` holds the name in its own text by
  design, and case 7 holds it equal to the owner.  The other file names of that
  module are not this name: the last component of the string decides.

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
from src import events_document  # noqa: E402

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

#: The served document name of every scan, as the owner holds it in ``SERVED``.
#: Round 94 moved five readers and one command line default to the owner.
SERVED_NAME = 'events.json'

#: The name the owner binds the served spelling to.  A reader passes this name.
SERVED_BINDING = 'SERVED'

#: The two helpers of the owner that answer a path.  A served-name reader calls one.
HELPERS = ('document_path', 'document_in')

#: The five readers of round 94 that read the served name through the owner.
#: ``src/eval_events.py`` is not here: it keeps one frozen literal, and case 7 holds
#: that literal equal to the owner.
SERVED_READERS = (
    'src/info_complete_scan.py',
    'src/motion_scan.py',
    'src/segment_calib_report.py',
    'src/store.py',
    'src/timing_verify.py',
)

#: ``(file, text, folder, option)`` of a site that keeps the served name as a
#: literal.  argparse prints a default string in ``--help``, and a recorded command
#: line holds it, so the literal stays at its site.  Case 7 asks the owner for the
#: document in ``folder`` and compares that answer with ``text``.
FROZEN = (
    ('src/eval_events.py', 'out/scan-ic/events.json', 'out/scan-ic', '--candidates'),
)

#: ``(file, text, count)`` of the sites that spell the served name and belong to
#: another round.  The console of ``annotator/`` moves in its own round, so this case
#: counts its sites and fails when a new one appears.  A writer that moves one of
#: these sites lowers the number here in the same change.
OUTSIDE_THIS_ROUND = (
    ('annotator/server.py', 'events.json', 1),
    ('annotator/unified_server.py', 'events.json', 5),
)


def spellings(paths=None, name=NAME):
    """``(path, line, text)`` for every used string of the tree that holds the name.

    The name is the last component of the string, so a report such as
    ``out/scan30/eval_events.json`` is not a spelling of ``events.json``.  A
    docstring is not a used string (``tests/_shipped.py`` drops it), so the
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
            if Path(text).name == name:
                found.append((Path(path), line, text))
    return found


def shown(path: Path) -> str:
    """The path of a site, relative to the repository root when it sits inside it."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def problems(sites, binding=BINDING, frozen=(), outside=()) -> list:
    """A line per site that spells the name and may not.

    The owner states the name, so a site of the owner is quiet.  A site of
    ``frozen`` keeps the text as a literal, and a case of the served name holds that
    literal equal to the owner.  A site of ``outside`` belongs to another round.
    Each allowed site is named by its file and its text, so a second literal in the
    same file is a problem.
    """
    allowed = {(site[0], site[1]) for site in frozen}
    allowed |= {(site[0], site[1]) for site in outside}
    out = []
    for path, line, text in sites:
        relative = shown(path)
        if relative == OWNER or relative in ALLOWED_TEST_MODULES:
            continue
        if (relative, text) in allowed:
            continue
        out.append(f'{relative}:{line} spells {text!r}; the owner of that name is '
                   f'{OWNER}, and it binds it to {binding}')
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

    A read is a call of ``events_document.<helper>`` that passes
    ``events_document.<binding>`` as one of its arguments.  ``document_path`` takes
    the name first, and ``document_in`` takes the folder first and the name second,
    so the case reads every argument position and not a fixed one.  The reader binds
    the answer to its own constant and keeps its own root, so the case reads this
    shape alone and not the name of the target.
    """
    wanted = f'events_document.{helper}'
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or dotted(node.func) != wanted:
            continue
        if any(dotted(argument) == f'events_document.{binding}' for argument in node.args):
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


def owner_document(folder: str) -> str:
    """The path the owner answers for the served document in one folder.

    A case compares a frozen literal with this answer, so the literal and the owner
    cannot drift apart.
    """
    return str(events_document.document_in(folder, events_document.SERVED))


def argument_default(tree, option: str):
    """The literal that one tree states as the default of a command line option.

    ``option`` is the flag text, for example ``--candidates``.  The answer is the text
    of the first ``add_argument(option, default=...)`` call of the tree, or None when
    no call states a literal.  argparse prints a default string in ``--help``, and a
    recorded command line holds it.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if dotted(node.func).rsplit('.', 1)[-1] != 'add_argument':
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and first.value == option):
            continue
        for keyword in node.keywords:
            if keyword.arg == 'default' and isinstance(keyword.value, ast.Constant):
                return keyword.value.value
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


class ServedDocumentNameTests(unittest.TestCase):
    """The served name ``events.json`` reads from the same owner."""

    def test_the_owner_states_the_served_name_once_and_binds_it(self):
        tree = ast.parse((ROOT / OWNER).read_text(encoding='utf-8'), filename=OWNER)
        sites = [(line, text) for line, text in code_strings(tree) if text == SERVED_NAME]
        self.assertEqual(
            1, len(sites),
            f'{OWNER} holds the served name on {len(sites)} line(s) that are not a '
            f'docstring: {sites}. The owner states it once, as {SERVED_BINDING}.')
        value = owner_binding(tree, SERVED_BINDING)
        self.assertIsNotNone(
            value, f'{OWNER} has no module-level binding of {SERVED_BINDING}, so no reader '
                   f'can name the served document through it')
        stated = value.value if isinstance(value, ast.Constant) else None
        self.assertEqual(
            SERVED_NAME, stated,
            f'{OWNER} binds {SERVED_BINDING} to {stated!r}, not to the name {SERVED_NAME!r}')

    def test_no_shipped_module_spells_the_served_name_outside_the_owner(self):
        found = problems(spellings(name=SERVED_NAME), SERVED_BINDING, FROZEN,
                         OUTSIDE_THIS_ROUND)
        self.assertEqual(
            [], found,
            'sites outside the owner spell the served name:\n' + '\n'.join(found))

    def test_the_scan_reports_a_planted_served_copy_with_its_file_and_its_line(self):
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / 'reader.py'
            planted.write_text(
                'import json\n'
                'QUEUE = json.load(open("out/scan30/events.json"))\n',
                encoding='utf-8')
            sites = spellings([planted], SERVED_NAME)
        self.assertEqual(
            1, len(sites),
            f'the scan answered {sites} for one planted copy on line 2 of {planted}')
        found = problems(sites, SERVED_BINDING)
        self.assertEqual(1, len(found), f'the scan did not report the planted copy: {sites}')
        self.assertTrue(
            found[0].startswith(f'{planted}:2 spells '),
            f'the report does not name the file and the line: {found[0]}')

    def test_a_module_that_reads_the_served_name_from_the_owner_is_quiet(self):
        with tempfile.TemporaryDirectory() as folder:
            reader = Path(folder) / 'reader.py'
            reader.write_text(
                'from src import events_document\n'
                'QUEUE = events_document.document_in("out/scan30", events_document.SERVED)\n',
                encoding='utf-8')
            found = problems(spellings([reader], SERVED_NAME), SERVED_BINDING)
        self.assertEqual([], found, f'a reader of the owner was reported: {found}')

    def test_each_served_reader_reads_the_name_from_the_owner(self):
        for relative in SERVED_READERS:
            with self.subTest(module=relative):
                tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'),
                                 filename=relative)
                self.assertTrue(
                    any(reads_the_name(tree, helper, SERVED_BINDING) for helper in HELPERS),
                    f'{relative} does not read the served name through the owner. A reader '
                    f'calls events_document.document_path(events_document.{SERVED_BINDING}) '
                    f'or events_document.document_in(<folder>, '
                    f'events_document.{SERVED_BINDING}), so the owner alone names the '
                    f'served document of a rename.')

    def test_the_frozen_literal_equals_the_owner_and_is_still_an_option_default(self):
        for relative, text, folder, option in FROZEN:
            with self.subTest(module=relative):
                tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'),
                                 filename=relative)
                self.assertEqual(
                    text, owner_document(folder),
                    f'{relative} holds {text!r} for {folder!r}, and the owner answers '
                    f'{owner_document(folder)!r}')
                self.assertEqual(
                    text, argument_default(tree, option),
                    f'{relative} does not state {text!r} as the default of {option}, so the '
                    f'literal is not the text argparse prints')

    def test_the_served_name_sites_outside_this_round_keep_their_count(self):
        counts = {}
        for path, _, text in spellings(name=SERVED_NAME):
            counts.setdefault(shown(path), []).append(text)
        for relative, text, count in OUTSIDE_THIS_ROUND:
            with self.subTest(module=relative):
                sites = counts.get(relative, [])
                self.assertEqual(
                    count, len(sites),
                    f'{relative} spells the served name on {len(sites)} line(s) {sites}, and '
                    f'this round declares {count} site(s) of {text!r}. A round that moves one '
                    f'of these sites lowers the number here in the same change.')

    def test_the_scan_does_not_read_a_report_name_as_the_served_name(self):
        texts = [text for _, _, text in spellings(name=SERVED_NAME)]
        for report in ('out/scan30/eval_events.json', 'out/scan30/probe_events.json'):
            with self.subTest(text=report):
                self.assertNotIn(
                    report, texts,
                    f'the scan reads the report name {report!r} as a spelling of '
                    f'{SERVED_NAME!r}. The name is the last component of the string, so a '
                    f'report is not the document.')


if __name__ == '__main__':
    unittest.main()
