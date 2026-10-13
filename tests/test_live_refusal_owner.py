"""The sentences a live start can refuse with have one owner and one pattern.

annotator/live_processing.py raises the refusal sentences the operator reads.  The console phrases
them in Chinese, and it has two homes for them: the ``liveErrorCodes`` table for a sentence that
carries a code, and the anchored pattern list ``const liveRefusals = [`` for a sentence that carries
none.  The two files drift apart in silence, because nothing reads them together, and a sentence with
no pattern stays English in the Chinese console.

This module is that reader.  It parses every raise of the owner, builds the sentence each one sends,
and asks the shipped patterns of annotator/app.js which sentences they claim.  An uncovered sentence
is reported as ``file:line sentence``.

Some sentences are uncovered on purpose and stay English.  The UNMAPPED table below names each one
with its reason, so the report holds only the sentences nobody has judged yet.  A reason names the
fact that proves it, and a case reads that fact: the scope of the raise, or the refusal row of
annotator/refusals.py.  tests/console_text.py owns the javascript line of the last sentence, so this
module reads the line from that owner and never writes it again.

The detector-list sentence of annotator/live_processing.py:380 is the sentence this round gives a
pattern.
"""

import ast
import json
import os
import re
import subprocess
import unittest
import uuid
from pathlib import Path
from typing import NamedTuple

import console_text

from annotator import refusals

ROOT = Path(__file__).resolve().parent.parent
OWNER = 'annotator/live_processing.py'
CONSOLE = 'annotator/app.js'
ANCHOR = 'const liveRefusals = ['
CODES_ANCHOR = 'const liveErrorCodes = {'


def console_line_sentence():
    """The one refusal sentence the console shows as a javascript line, read from its owner.

    tests/console_text.py owns that line, and annotator/refusals.py owns the sentence itself.  A
    second statement of the sentence in a test module would be the drift this round removes, so
    this module reads the owner view and holds no literal of its own.
    """
    rows = console_text.line_rows()
    if len(rows) != 1:
        raise AssertionError('tests/console_text.py holds {0} line rows, not one: {1}'
                             .format(len(rows), rows))
    return rows[0].refusal


CONSOLE_LINE_SENTENCE = console_line_sentence()

# The one value the console pattern of annotator/live_processing.py:143 names, and the value the
# worker substitutes into its `%s`.  The console owns the reading, so this module reads it here.
DETECTOR_NAME = 'ball'
RUN_VALUE = 'ball.pt'

# The detector-list sentence, its pattern index, its Chinese form, and the retired row before it.
DETECTOR_INDEX = 10
DETECTOR_SENTENCE = 'Live detectors must be a non-empty list of table, person, ball, balls'
DETECTOR_TEXT = 'Live detectors must be a non-empty list of %s'
DETECTOR_SENTENCE_ZH = '直播检测器必须是非空列表，只能用 table、person、ball、balls'
DEAD_DETECTOR_SENTENCE = 'Live detectors must be table, person and/or ball; SAM balls are not supported'
DEAD_PATTERN_SOURCE = r'^Live detectors must be table, person and\/or ball; SAM balls are not supported$'
DETECTOR_PATTERN_SOURCE = (r'^Live detectors must be a non-empty list of '
                           r'(?:table|person|ball|balls)(?:, (?:table|person|ball|balls))*$')
FIRST_PATTERN_SOURCE = r'^Select a saved canonical Twitch channel$'

# Every raise of the owner, as (line, sentence as the source spells it, error code or None).  A raise
# with a code is phrased by the liveErrorCodes table of the console; a raise without one is phrased
# by the liveRefusals patterns.
RAISES = (
    (135, "Requested detector 'ball' has no stage in this pipeline; pass a BallStage with stages= or drop it from detectors", None),
    (143, "Requested detector 'ball' cannot run: %s", None),
    (151, 'a message the caller builds', None),
    (264, 'Pass either infer or stages, not both', None),
    (339, 'source must be a dataset or saved Twitch channel object', None),
    (343, 'dataset must be vod30 or highlight', None),
    (346, 'Allowlisted dataset media is unavailable', None),
    (355, 'Saved Twitch channel is unavailable', None),
    (360, 'Select a saved canonical Twitch channel', None),
    (363, 'Select a saved canonical Twitch channel', None),
    (365, 'Use an allowlisted dataset or saved Twitch source_id, not a URL', None),
    (380, DETECTOR_TEXT, None),
    (393, 'Previous live processing threads have not exited; stop and retry', None),
    (517, 'Unsupported live source kind', 'unsupported_kind'),
    (546, 'Could not open the selected media source', 'open_failed'),
    (573, 'Decoded frame must be a color image no larger than 3840 × 2160', 'frame_invalid'),
    (660, CONSOLE_LINE_SENTENCE, None),
)

# The sentences an operator reads, one row per raise, in line order.  A sentence a pattern claims is
# the sentence the service sends, so the reading is the same on both sides.
ON_SCREEN = {
    135: "Requested detector 'ball' has no stage in this pipeline; pass a BallStage with stages= or drop it from detectors",
    143: "Requested detector 'ball' cannot run: ball.pt",
    264: 'Pass either infer or stages, not both',
    339: 'source must be a dataset or saved Twitch channel object',
    343: 'dataset must be vod30 or highlight',
    346: 'Allowlisted dataset media is unavailable',
    355: 'Saved Twitch channel is unavailable',
    360: 'Select a saved canonical Twitch channel',
    363: 'Select a saved canonical Twitch channel',
    365: 'Use an allowlisted dataset or saved Twitch source_id, not a URL',
    380: DETECTOR_SENTENCE,
    393: 'Previous live processing threads have not exited; stop and retry',
    517: 'Unsupported live source kind',
    546: 'Could not open the selected media source',
    573: 'Decoded frame must be a color image no larger than 3840 × 2160',
    660: CONSOLE_LINE_SENTENCE,
}

# A judged sentence: no pattern phrases it, and one fact in the tree proves why.
class Judged(NamedTuple):
    """One sentence that stays the server's English, with the reason the reader needs.

    reason  one line for the reader
    holder  the fact that proves the reason.  ``constructor`` means the raise sits in
            ``LiveProcessing.__init__``; ``refusal table`` means annotator/refusals.py owns the
            sentence as a refusal row, and the console shows that row.
    """
    reason: str
    holder: str


# Every sentence with no pattern and no code, and the reason it stays the server's English.  The
# holder names the fact that the case below reads, so a reason cannot rot into prose.
UNMAPPED = {
    'Pass either infer or stages, not both': Judged(
        'the caller passed both arguments, and the start form offers no such choice', 'constructor'),
    CONSOLE_LINE_SENTENCE: Judged(
        'annotator/refusals.py owns the sentence as a refusal row, and the console shows that row',
        'refusal table'),
}

# annotator/live_processing.py:151 forwards a message its caller builds, so it sends no sentence of
# its own.  Every other raise of the owner carries one.
UNREADABLE = (151,)

NODE_DRIVER = r"""
// The refusal patterns of annotator/app.js, read as the shipped text and kept as shipped regexes.
const anchor = 'const liveRefusals = [';
const text = require('fs').readFileSync(process.env.CONSOLE, 'utf8');
const start = text.indexOf(anchor);
if (start < 0) { throw new Error('annotator/app.js holds no ' + anchor); }
let depth = 0;
let end = start + anchor.length - 1;
for (; end < text.length; end++) {
  if (text[end] === '[') { depth++; continue; }
  if (text[end] === ']') { depth--; if (depth === 0) { break; } }
}
if (end >= text.length) { throw new Error('the refusal pattern list of annotator/app.js never closes'); }
const patterns = require('vm').runInNewContext('(' + text.slice(start + anchor.length - 1, end + 1) + ')');
console.log(JSON.stringify(patterns.map(([pattern, render]) => ({
  source: pattern.source,
  render: render('ball', 'ball.pt')
}))));
"""


def owner_text(text=None):
    """The source text of the refusing owner, or the given text in its place."""
    if text is not None:
        return text
    return (ROOT / OWNER).read_text(encoding='utf-8')


def console_source(text=None):
    """The source text of the console, or the given text in its place."""
    if text is not None:
        return text
    return (ROOT / CONSOLE).read_text(encoding='utf-8')


def owner_module(text=None):
    """The parsed module of the owner, so a case reads raise statements as data."""
    return ast.parse(owner_text(text), filename=OWNER)


def all_raise_lines(text=None):
    """The line of every raise of the owner, in line order, so a new raise is reported."""
    found = []
    for node in ast.walk(owner_module(text)):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            found.append(node.lineno)
    return sorted(found)


def owner_raises(text=None, concrete=True):
    """Every raise of the owner that carries a sentence, as [(line, sentence, code), ...].

    ``concrete`` builds the sentence an operator reads, with the values a run supplies.  A caller
    that wants the raise text itself passes ``concrete=False`` and reads `%s` where a value stands.
    """
    rows = []
    for node in ast.walk(owner_module(text)):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
            continue
        if node.lineno in UNREADABLE:
            continue
        where = '{0}:{1}'.format(OWNER, node.lineno)
        rows.append((node.lineno, sentence_of(node.exc.args[0], where, concrete),
                     error_code(node.exc)))
    return sorted(rows)


def error_code(call):
    """The error code of one raise, and None when the sentence carries no code."""
    if len(call.args) < 2:
        return None
    return concat_text(call.args[1])


def sentence_of(node, where, concrete=True):
    """The sentence of one raise: the text an operator reads, or the raise text itself."""
    literal = concat_text(node)
    if literal is not None:
        return literal
    template = format_parts(node, concrete)
    if template is None:
        raise AssertionError(where + ' sends a sentence this module cannot read: ' + ast.dump(node))
    built, parts = template
    for code, value in parts:
        built = built.replace(specifier(code), value, 1)
    return built


def specifier(code):
    """The one `%` marker a sentence template holds, so a sentence stays readable."""
    return '%' + code + '\x00'


def format_parts(node, concrete=True):
    """The template of one sentence with its arguments, and None when the shape is unknown.

    The owner builds a sentence with `%`, and it may join two of them with `+`.  Each `%` carries
    its own argument, so the parts are read in source order and each one takes the value of its own
    operand: the detector name for `%r`, and the detector list of a `', '.join(...)` for `%s`.
    """
    if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
            and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)):
        codes = [match[1] for match in re.findall(r'%[rs]', node.left.value)]
        built = node.left.value
        for code in codes:
            built = built.replace('%' + code, specifier(code), 1)
        parts = [(code, value_of(node.right, code, concrete)) for code in codes]
        return built, parts
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = format_parts(node.left, concrete), format_parts(node.right, concrete)
        if left is not None and right is not None:
            return left[0] + right[0], left[1] + right[1]
    return None


def value_of(argument, code, concrete=True):
    """The value one `%` of a sentence takes, as the text an operator reads."""
    if not concrete:
        return '%' + code
    if code == 'r':
        return "'{0}'".format(DETECTOR_NAME)
    if isinstance(argument, ast.Call):
        return ', '.join(join_values(argument))
    literal = concat_text(argument)
    if literal is not None:
        return literal
    if isinstance(argument, ast.Name):
        return RUN_VALUE
    raise AssertionError('a sentence substitutes a value this module cannot read: ' + ast.dump(argument))


def concat_text(node):
    """The text of a string expression, adjacent literals joined, and None for anything else."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = concat_text(node.left), concat_text(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def join_values(node):
    """The detector list of a ``', '.join(LIVE_DETECTORS)`` call, read from the shipped vocabulary."""
    receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
    if (isinstance(node.func, ast.Attribute) and node.func.attr == 'join' and node.args
            and concat_text(receiver) == ', '
            and isinstance(node.args[0], ast.Name) and node.args[0].id == 'LIVE_DETECTORS'):
        return detector_names()
    raise AssertionError('this sentence joins a list this module cannot read: ' + ast.dump(node))


def detector_names():
    """The detector vocabulary of the owner, read from the service that names it."""
    from annotator.live_processing import LIVE_DETECTORS
    names = list(LIVE_DETECTORS)
    if not names:
        raise AssertionError('the owner names no detector: ' + repr(names))
    return names


def console_rows(source=None):
    """The shipped patterns and their renders, read by node from the console text."""
    if source is None:
        return rows_of(str(ROOT / CONSOLE))
    probe = ROOT / ('.live-refusal-probe-{0}.js'.format(uuid.uuid4().hex))
    probe.write_text(source, encoding='utf-8')
    try:
        return rows_of(str(probe))
    finally:
        probe.unlink()


def rows_of(path):
    """The patterns and renders of one console file, read as shipped text by node."""
    node = shutil_which_node()
    if not node:
        raise AssertionError('node is required to run the refusal patterns of ' + CONSOLE)
    done = subprocess.run(
        [node, '-e', NODE_DRIVER], capture_output=True, text=True, timeout=120,
        env=dict(os.environ, CONSOLE=path),
    )
    if done.returncode != 0:
        raise AssertionError('node could not read the refusal patterns of ' + path
                             + ':\n' + done.stderr.strip())
    return json.loads(done.stdout)


def shutil_which_node():
    """The node program on PATH, and None when this host has no node."""
    for directory in os.environ.get('PATH', '').split(os.pathsep):
        candidate = Path(directory or '.') / 'node'
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


def console_patterns(text=None):
    """The refusal patterns of the console, as regexes this module can run."""
    return [re.compile(row['source']) for row in console_rows(text)]


def console_code_keys(text=None):
    """The error codes the console phrases, read from its own liveErrorCodes table."""
    source = console_source(text)
    start = source.index(CODES_ANCHOR) + len(CODES_ANCHOR)
    end = source.index('\n};', start)
    return re.findall(r'^\s{2}([a-z_]+):', source[start:end], re.M)


def sentences(text=None, concrete=True, coded=False):
    """Every refusal sentence of the owner with its location, as [(file:line, sentence), ...].

    ``coded`` selects the sentences that carry an error code; the default selects the sentences that
    carry none, and those are the ones the refusal patterns must phrase.
    """
    return [('{0}:{1}'.format(OWNER, line), sentence)
            for line, sentence, code in owner_raises(text, concrete)
            if (code is not None) == coded]


def enclosing_functions(text=None):
    """{raise line: the name of the function that holds it}, read from the parsed owner."""
    module = owner_module(text)
    parents = {}
    for node in ast.walk(module):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    found = {}
    for node in ast.walk(module):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        holder = parents.get(node)
        while holder is not None and not isinstance(holder, ast.FunctionDef):
            holder = parents.get(holder)
        if holder is not None:
            found[node.lineno] = holder.name
    return found


def scopes_of(sentence, text=None):
    """The functions that hold a raise of one sentence, in name order."""
    functions = enclosing_functions(text)
    sent = [line for line, spelled, _code in owner_raises(text) if spelled == sentence]
    return sorted({functions[line] for line in sent if line in functions})


def uncovered(entries, patterns, unmapped=None):
    """Every sentence no pattern covers, as ``file:line sentence``, in line order.

    A sentence passes when one console pattern holds it from its first character to its last.  An
    entry that ``unmapped`` names is judged already and stays out of the report, so the report
    carries the sentences nobody has judged, each judged one carrying its reason.
    """
    known = UNMAPPED if unmapped is None else unmapped
    reported = []
    for where, sentence in entries:
        if any(pattern.search(sentence) for pattern in patterns):
            continue
        if sentence in known:
            continue
        reported.append('{0} {1}'.format(where, sentence))
    return reported


def detector_pattern(text=None):
    """The detector-list pattern of the console, and the render that phrases it in Chinese."""
    rows = console_rows(text)
    return re.compile(rows[DETECTOR_INDEX]['source']), rows[DETECTOR_INDEX]['render']


class LiveRefusalOwnerTest(unittest.TestCase):
    """The refusal sentences of the owner, read against the patterns of the console."""

    def test_the_owner_raises_are_exactly_the_list_this_module_guards(self):
        self.assertEqual([line for line, _sentence, _code in RAISES], all_raise_lines(),
                         'a raise of the owner moved or arrived: ' + repr(all_raise_lines()))
        self.assertEqual({line: sentence for line, sentence, _code in RAISES if line not in UNREADABLE},
                         dict((line, sentence) for line, sentence, _code in owner_raises(concrete=False)),
                         'a raise of the owner sends another sentence')
        self.assertEqual(ON_SCREEN, dict((line, sentence) for line, sentence, _code in owner_raises()),
                         'an operator reads a sentence of this list')

    def test_each_sentence_without_a_code_is_claimed_by_exactly_one_pattern(self):
        patterns = console_patterns()
        entries = [(where, sentence) for where, sentence in sentences() if sentence not in UNMAPPED]
        self.assertTrue(entries, 'the owner sends sentences with no code: ' + repr(entries))
        for where, sentence in entries:
            holders = [number for number, pattern in enumerate(patterns) if pattern.search(sentence)]
            self.assertEqual(1, len(holders),
                             '{0} is claimed by one pattern and no other: {1}'.format(where, holders))

    def test_every_sentence_without_a_code_reaches_a_pattern_or_a_judged_reason(self):
        patterns = console_patterns()
        offenders = uncovered(sentences(), patterns)
        self.assertEqual([], offenders,
                         'every refusal sentence needs a console pattern, or a reason in UNMAPPED:\n'
                         + '\n'.join(offenders) + '\n(judged: ' + repr(sorted(UNMAPPED)) + ')')
        self.assertTrue(UNMAPPED, 'the judged table names the sentences that stay English')
        for sentence, judged in UNMAPPED.items():
            with self.subTest(sentence=sentence):
                self.assertTrue(judged.reason, 'every judged entry carries a reason: ' + repr(judged))
                self.assertEqual(judged.reason.strip(), judged.reason,
                                 'a reason is one trimmed line: ' + repr(judged.reason))
                self.assertNotIn('\n', judged.reason, 'a reason is one line: ' + repr(judged.reason))
                self.assertFalse(any(pattern.search(sentence) for pattern in patterns),
                                 'a judged sentence stays uncovered: ' + sentence)
                self.assertIn(judged.holder, ('constructor', 'refusal table'),
                              'a judged entry names the fact that proves it: ' + repr(judged.holder))
                if judged.holder == 'constructor':
                    self.assertEqual(['__init__'], scopes_of(sentence),
                                     'the judged raise sits in the constructor: ' + sentence)
                else:
                    self.assertIn(sentence, refusals.REFUSALS,
                                  'annotator/refusals.py owns the judged sentence: ' + sentence)

    def test_each_sentence_with_a_code_has_its_row_in_the_console_table(self):
        keys = console_code_keys()
        self.assertTrue(keys, 'the console holds an error-code table: ' + repr(keys))
        coded = [(line, sentence, code) for line, sentence, code in owner_raises() if code]
        self.assertEqual(3, len(coded), 'the owner sends three coded sentences: ' + repr(coded))
        for line, sentence, code in coded:
            self.assertIn(code, keys, '{0}:{1} carries a code the console phrases: {2}'
                          .format(OWNER, line, code))

    def test_the_detector_list_sentence_has_its_pattern_and_the_console_phrases_it(self):
        pattern, render = detector_pattern()
        self.assertEqual(DETECTOR_PATTERN_SOURCE, pattern.pattern,
                         'the detector-list pattern holds its own sentence and no other: '
                         + repr(pattern.pattern))
        self.assertTrue(pattern.search(DETECTOR_SENTENCE),
                        'the detector-list sentence needs its pattern: ' + DETECTOR_SENTENCE)
        self.assertEqual(DETECTOR_SENTENCE_ZH, render,
                         'the console phrases the sentence in Chinese: ' + repr(render))
        self.assertIn(('{0}:380'.format(OWNER), DETECTOR_SENTENCE), sentences(),
                      'the service sends the sentence this case names: ' + repr(sentences()))
        for wrapped in ('prefix: ' + DETECTOR_SENTENCE, DETECTOR_SENTENCE + ' and more',
                        'Live detectors must be a non-empty list of', DEAD_DETECTOR_SENTENCE):
            self.assertIsNone(pattern.search(wrapped),
                              'an anchored pattern refuses a wrapped or unrelated sentence: ' + wrapped)
        for names in (['table'], ['table', 'person'], detector_names(), ['person', 'ball'],
                      ['balls', 'table']):
            sentence = 'Live detectors must be a non-empty list of ' + ', '.join(names)
            self.assertTrue(pattern.search(sentence), 'a legal list is claimed: ' + sentence)
        for names in (['camera'], ['ball '], ['tables'], ['table and person'],
                      detector_names() + ['bats']):
            sentence = 'Live detectors must be a non-empty list of ' + ', '.join(names)
            self.assertIsNone(pattern.search(sentence), 'an illegal list stays English: ' + sentence)

    def test_the_retired_detector_row_still_claims_its_sentence_and_no_raise_sends_it(self):
        rows = console_rows()
        self.assertIn(DEAD_PATTERN_SOURCE, [row['source'] for row in rows],
                      'the retired row stays in the console: ' + DEAD_DETECTOR_SENTENCE)
        patterns = console_patterns()
        holders = [number for number, pattern in enumerate(patterns)
                   if pattern.search(DEAD_DETECTOR_SENTENCE)]
        self.assertEqual([6], holders,
                         'the retired row claims its own sentence and no other row does: '
                         + repr(holders))
        self.assertNotIn(DEAD_DETECTOR_SENTENCE, [sentence for _where, sentence in sentences()],
                         'no raise of the owner sends the retired sentence, so the row is dead: '
                         + DEAD_DETECTOR_SENTENCE)

    def test_a_sentence_no_pattern_covers_is_reported_as_file_line_sentence(self):
        entry = ('{0}:380'.format(OWNER), DETECTOR_SENTENCE)
        patterns = console_patterns()
        self.assertEqual([], uncovered([entry], patterns),
                         'the detector-list sentence has its pattern now')
        self.assertEqual(['{0}:380 '.format(OWNER) + DETECTOR_SENTENCE],
                         uncovered([entry], patterns[:DETECTOR_INDEX]),
                         'a sentence no pattern covers is reported as file:line sentence')
        self.assertEqual([], uncovered([entry], patterns[:DETECTOR_INDEX], {DETECTOR_SENTENCE: 'why'}),
                         'a judged sentence never reaches the report')

    def test_a_planted_sentence_is_reported_and_nothing_else_is(self):
        planted = 'A planted refusal no console pattern covers'
        text = owner_text().replace(
            "raise ValueError('Select a saved canonical Twitch channel')",
            'raise ValueError({0!r})'.format(planted), 1)
        self.assertNotEqual(owner_text(), text, 'the plant missed its anchor')
        offenders = uncovered(sentences(text), console_patterns())
        self.assertIn('{0}:360 '.format(OWNER) + planted, offenders,
                      'the planted sentence is reported with its line: ' + repr(offenders))
        self.assertEqual(1, len(offenders),
                         'the plant adds one sentence and one report line: ' + repr(offenders))

    def test_a_lost_pattern_names_the_sentence_it_leaves_english(self):
        text = console_source().replace(FIRST_PATTERN_SOURCE, DETECTOR_PATTERN_SOURCE, 1)
        self.assertNotEqual(console_source(), text, 'the plant missed its anchor')
        both = ['{0}:360 Select a saved canonical Twitch channel'.format(OWNER),
                '{0}:363 Select a saved canonical Twitch channel'.format(OWNER)]
        self.assertEqual(both, uncovered(sentences(), console_patterns(text)),
                         'the lost row leaves both raises that send its sentence English')
        self.assertEqual(['{0}:380 '.format(OWNER) + DETECTOR_SENTENCE],
                         uncovered(sentences(), console_patterns()[:DETECTOR_INDEX]),
                         'a lost pattern names the sentence it leaves English')


if __name__ == '__main__':
    unittest.main()
