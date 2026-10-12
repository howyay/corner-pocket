"""One home for one operator-visible sentence, and one reader of each home.

Round 80 measured two sentences, each with two owners.

* The single-frame note.  The payload of ``src/frame_inference.py`` minted the words,
  and the merge fallback of ``annotator/pipeline_stages.py`` spelled the same words
  again.  The case in ``tests/test_pipeline_stages.py`` asked for one substring of the
  note only, so the two spellings could drift apart and no case failed.
* The expiry sentence.  The clock tick of ``annotator/ops.js`` shows the words, and
  ``docs/corner-pocket-operations.md`` restated them.  No case read that document for
  the sentence at all.

The decision of the round:

* the producer, ``src/frame_inference.py``, owns the note, because it mints the note.
  The name is ``EVENT_NOTE_SINGLE_FRAME``.  The stage keeps its ``or`` fallback and
  reads that name, and the producer answers its own payload with the same name.
* the console, ``annotator/ops.js``, owns the expiry sentence.  The document names the
  owner and holds no copy of the words.  The document cites a line of the owner, and
  this case reads the line the citation names.

The scan reads every file of the shipped trees (``src``, ``annotator``, ``tools``,
``scripts``) and the one document.  The vendored ``src/sam3`` tree and every file
above ``SIZE_LIMIT`` stay out, as the other tree walks of this suite leave them out.
Every rule below has a planted-copy case, so a scan that reads nothing fails instead
of passing for free.

Limits: the scan reads text and not meaning, so a sentence that a build step writes
into a shipped file, or one that is built at run time, is invisible to it.  The
console reader anchors on the expiry branch of the clock tick and stops at a quote,
so a moved branch or a sentence with a quote in it fails the case loudly.

Run: ``./scripts/pool-test.sh python test_pipeline_note_owner``
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _shipped import SHIPPED, bindings, code_strings, parse  # noqa: E402
from src.frame_inference import EVENT_NOTE_SINGLE_FRAME  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRAME_INFERENCE = 'src/frame_inference.py'
STAGE = 'annotator/pipeline_stages.py'
CONSOLE = 'annotator/ops.js'
DOCUMENT = 'docs/corner-pocket-operations.md'

#: The owner name of the note, in the module that mints the note.
NOTE_NAME = 'EVENT_NOTE_SINGLE_FRAME'

#: The words themselves, read from the owner and never spelled here.
NOTE = EVENT_NOTE_SINGLE_FRAME

#: The branch of the console clock tick that sends the expiry sentence at zero.
EXPIRY_BRANCH = 'timer.deadline&&left===0){'
LANGUAGE_PAIR = re.compile(r"message\(lang==='zh'\?('[^']*'):('[^']*')\)")

#: A file above this size is not a source file this case reads.  The vendored
#: ``src/sam3`` tree holds the large assets, and it stays out by name below.
SIZE_LIMIT = 1_000_000
VENDORED = ROOT / 'src' / 'sam3'

#: The spelling of the fallback this case plants over, to prove the reader rule.
FALLBACK = 'note or EVENT_NOTE_SINGLE_FRAME'


def shipped_files():
    """Every file of the shipped trees this case reads, in a stable order."""
    for name in SHIPPED:
        for path in sorted((ROOT / name).rglob('*')):
            if not path.is_file() or VENDORED in path.parents:
                continue
            if '__pycache__' in path.parts or path.stat().st_size > SIZE_LIMIT:
                continue
            yield path


def shipped_texts():
    """{path inside the repository: text} for every file the scan reads."""
    return {path.relative_to(ROOT).as_posix(): path.read_text(encoding='utf-8', errors='replace')
            for path in shipped_files()}


def sites(text, sentence):
    """Every 1-based line number of one text that holds one sentence."""
    return [number for number, line in enumerate(text.splitlines(), start=1)
            if sentence in line]


def copy_sites(sentence, texts):
    """Every site of one sentence: (path, line), for a text table and not for disk."""
    found = []
    for name, text in sorted(texts.items()):
        for number in sites(text, sentence):
            found.append((name, number))
    return found


def counts(found):
    """{path: number of sites} of a site list."""
    tally = {}
    for name, _number in found:
        tally[name] = tally.get(name, 0) + 1
    return tally


def describe(found):
    """A site list as report lines."""
    return ['  %s:%d' % (name, number) for name, number in found]


def document_text():
    """The text of the one document this case reads."""
    return (ROOT / DOCUMENT).read_text(encoding='utf-8')


def expiry_pair(text):
    """The two languages of the expiry sentence, read from the one console site.

    The console sends this message as the clock reaches zero.  The reader anchors on
    the expiry branch and takes the first language pair of a ``message`` call after
    it, so this case holds no copy of the words.
    """
    anchor = text.find(EXPIRY_BRANCH)
    if anchor < 0:
        return None
    match = LANGUAGE_PAIR.search(text, anchor)
    if match is None:
        return None
    return ast.literal_eval(match.group(1)), ast.literal_eval(match.group(2))


def dict_value(tree, function, key):
    """The value node one function gives one key of a dict, or None."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != function:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Dict):
                continue
            for slot, value in zip(sub.keys, sub.values):
                if isinstance(slot, ast.Constant) and slot.value == key:
                    return value
    return None


def reads_name(value, name):
    """True when one value node names the owner somewhere inside it."""
    return any(isinstance(node, ast.Name) and node.id == name for node in ast.walk(value))


def binding_value(path, name):
    """The value node one module binds to one name, or None."""
    for _line, bound, value in bindings(path):
        if bound == name:
            return value
    return None


def owner_findings(path, name, sentence):
    """Every way one module fails to be the one home of one sentence."""
    value = binding_value(path, name)
    if value is None:
        return ['%s: binds no %s' % (Path(path).name, name)]
    if not (isinstance(value, ast.Constant) and value.value == sentence):
        return ['%s: %s is not the one sentence of the shipped tree' % (Path(path).name, name)]
    return []


def fallback_findings(path, function, key, name):
    """Every way one function fails to read the owner name for one dict key."""
    value = dict_value(parse(path), function, key)
    module = Path(path).name
    if value is None:
        return ['%s: %s gives no value for %r' % (module, function, key)]
    found = []
    if not (isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or)):
        found.append('%s: %s gives %r a value that is no `or` fallback' % (module, function, key))
    if not reads_name(value, name):
        found.append('%s: %s does not read %s for %r' % (module, function, name, key))
    spelled = code_strings(value)
    if spelled:
        found.append('%s: %s spells %d string literal(s) in the fallback of %r'
                     % (module, function, len(spelled), key))
    return found


def imports_from(path, module, name):
    """True when one module reads one name from one other module."""
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            if any(alias.name == name for alias in node.names):
                return True
    return False


class NoteOwnerTests(unittest.TestCase):
    """The producer owns the note, and the stage reads the owner name."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_note_stands_once_in_the_shipped_tree(self):
        found = copy_sites(NOTE, shipped_texts())
        self.assertEqual({FRAME_INFERENCE: 1}, counts(found),
                         'the note must stand once, in its owner:\n' + '\n'.join(describe(found)))

    def test_the_owner_name_answers_the_one_sentence(self):
        self.assertEqual([], owner_findings(ROOT / FRAME_INFERENCE, NOTE_NAME, NOTE),
                         'the owner name must hold the one sentence')

    def test_the_producer_answers_its_payload_with_the_owner_name(self):
        value = dict_value(parse(ROOT / FRAME_INFERENCE), 'infer_frame', 'event_note')
        self.assertIsNotNone(value, 'infer_frame gives the payload no event_note')
        self.assertTrue(reads_name(value, NOTE_NAME),
                        'infer_frame must answer event_note with %s' % NOTE_NAME)

    def test_the_stage_reads_the_owner_name(self):
        self.assertTrue(imports_from(ROOT / STAGE, 'src.frame_inference', NOTE_NAME),
                        '%s must read %s from src.frame_inference' % (STAGE, NOTE_NAME))

    def test_the_stage_fallback_answers_the_owner(self):
        self.assertEqual([], fallback_findings(ROOT / STAGE, 'merge_detections', 'event_note',
                                               NOTE_NAME),
                         'the merge fallback must read the owner name and spell no literal')

    def test_the_stage_answers_the_owner_note(self):
        from annotator.pipeline_stages import merge_detections

        self.assertEqual(NOTE, merge_detections({}, ['table'])['event_note'])

    def test_the_scan_sees_a_planted_copy_in_the_shipped_tree(self):
        texts = shipped_texts()
        self.assertNotIn(STAGE, counts(copy_sites(NOTE, texts)),
                         'the stage must hold no copy of the note before this plant')
        planted = dict(texts)
        planted[STAGE] = texts[STAGE] + '\n# a planted second home\n# ' + NOTE + '\n'
        self.assertNotEqual(texts[STAGE], planted[STAGE], 'the plant missed its anchor')
        self.assertEqual(1, counts(copy_sites(NOTE, planted))[STAGE],
                         'the scan must report a planted copy')

    def test_a_fallback_that_spells_the_note_is_refused(self):
        text = (ROOT / STAGE).read_text(encoding='utf-8')
        self.assertIn(FALLBACK, text, 'the stage no longer holds %r, so this plant has no anchor'
                      % FALLBACK)
        planted = Path(self.tmp.name) / 'planted_stage.py'
        planted.write_text(text.replace(FALLBACK, 'note or %r' % NOTE), encoding='utf-8')
        found = fallback_findings(planted, 'merge_detections', 'event_note', NOTE_NAME)
        self.assertTrue(any('does not read' in line for line in found),
                        'the rule must refuse a fallback that spells the words: %s' % found)
        self.assertTrue(any('spells' in line for line in found),
                        'the rule must report the literal of the planted fallback: %s' % found)


class ExpiryOwnerTests(unittest.TestCase):
    """The console owns the expiry sentence, and the document names the owner."""

    @staticmethod
    def pair():
        """The two languages of the expiry sentence, read from the console."""
        pair = expiry_pair((ROOT / CONSOLE).read_text(encoding='utf-8'))
        if pair is None:
            raise AssertionError('%s holds no expiry pair at the clock tick' % CONSOLE)
        return pair

    def test_the_console_holds_the_pair_once(self):
        english, chinese = self.pair()
        self.assertNotEqual(english, chinese, 'the two languages must differ')
        texts = shipped_texts()
        for sentence in (english, chinese):
            found = copy_sites(sentence, texts)
            self.assertEqual({CONSOLE: 1}, counts(found),
                             'the console owns one site of %r:\n%s'
                             % (sentence, '\n'.join(describe(found))))

    def test_the_document_names_the_owner_and_holds_no_copy(self):
        text = document_text()
        for sentence in self.pair():
            self.assertEqual([], sites(text, sentence),
                             'the document must not repeat the console sentence')
        self.assertIn(CONSOLE, text, 'the document must name the console owner')

    def test_the_citation_of_the_document_lands_on_the_sentence(self):
        text = document_text()
        cited = re.findall(r'annotator/ops\.js:(\d+)', text)
        self.assertTrue(cited, 'the document must cite a line of its owner')
        lines = (ROOT / CONSOLE).read_text(encoding='utf-8').splitlines()
        for number in cited:
            self.assertLessEqual(int(number), len(lines),
                                 'the citation %s:%s is past the file' % (CONSOLE, number))
            line = lines[int(number) - 1]
            for sentence in self.pair():
                self.assertIn(sentence, line,
                              'the cited line %s:%s must hold the sentence' % (CONSOLE, number))

    def test_the_scan_sees_a_planted_copy_in_the_document(self):
        text = document_text()
        for sentence in self.pair():
            self.assertEqual([], sites(text, sentence),
                             'the document must hold no copy before this plant')
            planted = text + '\n' + sentence + '\n'
            self.assertNotEqual(text, planted, 'the plant missed its anchor')
            self.assertEqual(1, len(sites(planted, sentence)),
                             'the scan must report a planted copy')


if __name__ == '__main__':
    unittest.main()
