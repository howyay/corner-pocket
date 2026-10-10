"""The identity of a refusal: python owns it, and the console reads it.

The service writes each refusal sentence in English.  The console (annotator/ops.js) held its
own Chinese copy of 48 of those sentences, keyed by the English text.  A rewording in python
then dropped the Chinese, and no test caught it.

``annotator/refusals.py`` owns that identity now: one stable code and one Chinese sentence for
each refusal the console must know.  This module walks the modules that raise.  A new refusal
cannot arrive without a row, and a row cannot name a sentence that no raise site produces.
"""
import ast
import hashlib
from pathlib import Path
import unittest

from annotator import refusals
from annotator.unified_server import APIError, operator_message, refusal_body

ROOT = Path(__file__).resolve().parents[1]
# The modules that raise a refusal sentence the operator reads.  The route that answers
# (annotator/unified_server.py) builds one body for both of them.
RAISING_MODULES = ('annotator/operations.py', 'annotator/unified_server.py')
CONSOLE = 'annotator/ops.js'

# How many raised sentences carry no row in annotator/refusals.py.  The console shows its
# generic Chinese line for each one, and the English sentence stays.  This number is a
# decision, not a measurement: change it only when you decide about a sentence.
RAISED_SENTENCES_WITHOUT_A_ROW = 121

# The console owns its own English/Chinese word pairs (annotator/ops.js ``words``).  One pair
# repeats a refusal sentence by coincidence: the enroll form shows it for a name that is a bye
# placeholder.  The pair has its own English text and its own purpose, so it stays.  A new copy
# of a refusal sentence in javascript fails this test.
CONSOLE_WORDS_THAT_REPEAT_A_REFUSAL = {
    'annotator/ops.js': {'placeholderName': '轮空由抽签自动安排，请输入访客的真实姓名。'},
}

# The 48 Chinese sentences as the console held them before round 41.  This digest is the record
# of the move: the table left javascript byte for byte, and no translation happened.
CHINESE_SENTENCES_DIGEST = '194fce1ca9d59243f67f9994dc1054ea14dbec8e'
SENTENCES_DIGEST = '4c1f5c7e255f55dbcd69b0051b58f9374e47a2c4'

_SENTENCES = {}


def raised_sentences(relative_path):
    """Every distinct sentence that an ``ast.Raise`` in this module passes first.

    Only a plain string constant counts.  A sentence that an f-string builds is not a string
    this table can name: its pieces are fragments, not sentences.
    """
    if relative_path not in _SENTENCES:
        found = set()
        for node in ast.walk(ast.parse((ROOT / relative_path).read_text())):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
                continue
            first = node.exc.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.add(first.value)
        _SENTENCES[relative_path] = found
    return set(_SENTENCES[relative_path])


def all_raised_sentences():
    """Every distinct refusal sentence the service can raise, from both modules."""
    found = set()
    for relative_path in RAISING_MODULES:
        found |= raised_sentences(relative_path)
    return found


def digest(values):
    """One sha1 over sorted lines: a stable record of a set of sentences."""
    return hashlib.sha1('\n'.join(sorted(values)).encode()).hexdigest()


class RefusalIdentityTest(unittest.TestCase):
    def test_every_code_the_console_reads_has_a_raising_site(self):
        """A code in the table is a promise: some raise site sends that sentence."""
        produced = all_raised_sentences()
        for sentence, refusal in refusals.REFUSALS.items():
            with self.subTest(code=refusal.code):
                self.assertIn(sentence, produced,
                              f'{refusal.code} names a sentence that no raise site produces: {sentence}')

    def test_no_code_is_dead(self):
        """Every row reaches a refusal body, so no code waits for a route that never sends it."""
        for sentence, refusal in refusals.REFUSALS.items():
            with self.subTest(code=refusal.code):
                body = refusal_body(ValueError(sentence))
                self.assertEqual(body[refusals.CODE_KEY], refusal.code)
                self.assertEqual(body[refusals.ZH_KEY], refusal.zh)
                self.assertEqual(body['error'], sentence)

    def test_the_codes_are_unique_tokens(self):
        codes = [refusal.code for refusal in refusals.REFUSALS.values()]
        self.assertEqual(len(codes), len(set(codes)), 'two rows share a code')
        for code in codes:
            with self.subTest(code=code):
                self.assertRegex(code, r'^[a-z][a-z0-9_]*$',
                                 'a code is a token the console reads, never a sentence')

    def test_a_body_keeps_the_english_sentence_and_adds_the_identity(self):
        refusal = refusals.REFUSALS['Source already added']
        body = refusal_body(ValueError('Source already added'))
        self.assertEqual(body, {'error': 'Source already added',
                                refusals.CODE_KEY: refusal.code,
                                refusals.ZH_KEY: refusal.zh})

    def test_a_body_for_an_unknown_sentence_carries_the_sentence_only(self):
        for sentence in sorted(all_raised_sentences() - set(refusals.REFUSALS))[:3]:
            with self.subTest(sentence=sentence):
                self.assertEqual(refusal_body(ValueError(sentence)), {'error': sentence})

    def test_extra_fields_survive_and_the_table_owns_the_identity(self):
        exc = APIError('Source already added', 409, nightId='n1')
        body = refusal_body(exc, getattr(exc, 'fields', {}))
        self.assertEqual((body['error'], body['nightId']), ('Source already added', 'n1'))
        # A raise site cannot send a wrong identity: the table owns those two keys.
        body = refusal_body(ValueError('Source already added'), {'code': 'fake', 'zh': '假的。'})
        self.assertEqual(body['code'], refusals.REFUSALS['Source already added'].code)

    def test_one_rule_builds_every_refusal_body(self):
        """Both refusal sites call one builder, so a new site cannot forget the identity."""
        source = (ROOT / 'annotator/unified_server.py').read_text()
        calls = [node for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'refusal_body']
        self.assertEqual(len(calls), 2, 'the two refusal sites no longer build their body here')
        self.assertNotIn('{"error": operator_message(exc)', source,
                         'a refusal body is built by hand, without the identity')

    def test_every_row_survives_the_operator_message(self):
        """The body sends the sentence with absolute paths cut, so a row must keep its text."""
        for sentence in refusals.REFUSALS:
            with self.subTest(sentence=sentence):
                self.assertEqual(operator_message(ValueError(sentence)), sentence)

    def test_the_number_of_raised_sentences_without_a_row_is_pinned(self):
        """The sentences with no Chinese line are a known set.  A new one must be a decision."""
        without = all_raised_sentences() - set(refusals.REFUSALS)
        self.assertEqual(
            RAISED_SENTENCES_WITHOUT_A_ROW, len(without),
            f'the raised sentences with no row in annotator/refusals.py changed from '
            f'{RAISED_SENTENCES_WITHOUT_A_ROW} to {len(without)}.  They are now:\n'
            + '\n'.join(sorted(without))
            + '\nEach sentence above reaches the operator as English only.  Add a row with a code '
              'and the Chinese sentence, then set the number in this test.')

    def test_no_javascript_file_holds_a_refusal_sentence(self):
        """No javascript file may hold a refusal sentence: python sends it in the body."""
        files = sorted((ROOT / 'annotator').glob('*.js'))
        self.assertTrue(files, 'the scan found no javascript file to read')
        for path in files:
            text = path.read_text()
            for sentence in refusals.REFUSALS:
                with self.subTest(file=path.name, sentence=sentence):
                    self.assertNotIn(sentence, text, f'{path.name} holds the English refusal sentence')
        held = {}
        chinese = {refusal.zh for refusal in refusals.REFUSALS.values()}
        for path in files:
            text = path.read_text()
            for line in chinese:
                if line in text:
                    held.setdefault(path.relative_to(ROOT).as_posix(), set()).add(line)
        allowed = {name: set(words.values())
                   for name, words in CONSOLE_WORDS_THAT_REPEAT_A_REFUSAL.items()}
        self.assertEqual(allowed, held,
                         'a javascript file holds a refusal sentence, or the console word pair moved')
        # Each exception above is the console's own word pair: the console shows it for its own
        # form check, so it is not a copy of a refusal.
        console = (ROOT / CONSOLE).read_text()
        for words in CONSOLE_WORDS_THAT_REPEAT_A_REFUSAL.values():
            for key in words:
                with self.subTest(word=key):
                    self.assertIn(f"t('{key}')", console, 'the console no longer shows this word pair')

    def test_the_console_reads_the_served_identity(self):
        """The console reads the two keys the table declares beside the English sentence."""
        console = (ROOT / CONSOLE).read_text()
        for key in (refusals.CODE_KEY, refusals.ZH_KEY):
            with self.subTest(key=key):
                self.assertIn(f'served.{key}', console,
                              f'the console no longer reads the served {key} field')

    def test_the_moved_sentences_are_the_ones_the_console_held(self):
        """The English keys and the Chinese sentences are the table the console held."""
        self.assertEqual(SENTENCES_DIGEST, digest(refusals.REFUSALS),
                         'the English sentences of the table changed')
        self.assertEqual(CHINESE_SENTENCES_DIGEST,
                         digest(refusal.zh for refusal in refusals.REFUSALS.values()),
                         'a Chinese sentence changed, so the move was not byte for byte')


if __name__ == '__main__':
    unittest.main()
