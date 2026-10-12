"""The whole-seconds rule has one owner, and the three realms read it.

Two implementations disagreed before round 81.  ``src/datasets.py`` accepted the whole-valued
float ``12.0`` (JSON states a whole number as a number) and spelled the English sentence by hand;
``annotator/operations.seconds`` accepted an ``int`` only, so it refused ``12.0`` with the
skeleton ``WHOLE_SECONDS``; ``annotator/vod_import._whole`` held two copies of the sentence by
hand.  Measured before the change:

* ``datasets._seconds(12.0) -> 12``
* ``operations.seconds(12.0) -> TemplateError: startS must be a whole number of seconds, 0 or more``
* ``vod_import._whole(12.0, 'start_s', 0) -> 12``

One number was judged two ways, and the refusal told the operator that ``12.0`` is not a whole
number.  Round 81 gave the rule one implementation (``src/datasets.whole_seconds``, the private
``_seconds`` renamed) and the sentence one home (``annotator.refusals.WHOLE_SECONDS``, one row of
``TEMPLATES``).

The realms still answer in different voices, and that difference is named and held below:
``src/datasets.py`` raises ``ValueError``, ``annotator/operations.py`` raises ``TemplateError``
(the skeleton, its code and its Chinese row), and ``annotator/vod_import.py`` raises
``VodImportError`` (the route's status and identity).  The import route alone parses a
query-string spelling (``'12'``, ``'12.0'``) and alone reads ``None`` and ``''`` as "not
collected" instead of refusing.

This module holds that state in four ways:

1. one corpus of numbers drives all three readers: every value answers the same whole number in
   every realm, or is refused in every realm;
2. one case names each difference the realms keep, so a named difference cannot become a
   disagreement;
3. one case proves every realm states the owner's sentence, with the same name filled in;
4. one walk proves the rule's body (``int(value) != value``) and the sentence's text have one
   home under ``src/`` and ``annotator/``, and a case plants a copy of each to prove the walk
   reports it.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from annotator import operations, refusals
from annotator.refusals import TemplateError
from annotator.vod_import import VodImportError, _whole
from src.datasets import imported_id, whole_seconds

ROOT = Path(__file__).resolve().parents[1]

#: The rule's one implementation, and the one file that may spell its body.
OWNER_FILE = 'src/datasets.py'
RULE_BODY = 'int(value) != value'

#: The sentence's one home, and the one file that may spell its text.  The fragment below is the
#: row's sentence without its placeholder: a by-hand copy fills the name in, and still matches it.
#: This module therefore holds no copy of the sentence itself.
SENTENCE_FILE = 'annotator/refusals.py'
SENTENCE_FRAGMENT = refusals.WHOLE_SECONDS.split('{name} ', 1)[1]

#: The sentinel the import route answers for a field that was not collected.  It must never be
#: the answer of a value the corpus below states.
DEFAULT = object()


def datasets_answer(value, name='startS'):
    """What ``src/datasets.py`` answers for one value."""
    return whole_seconds(value, name)


def operations_answer(value, name='startS'):
    """What the action layer answers for one value."""
    return operations.seconds(value, name)


def import_answer(value, name='start_s'):
    """What the import route answers for one value, with the not-collected sentinel."""
    return _whole(value, name, DEFAULT)


#: One realm: the file, the name it binds, how to call it, and the voice it refuses in.  The
#: three voices are the difference the realms keep, and the file a report names.
READERS = (
    (OWNER_FILE, 'whole_seconds', datasets_answer, ValueError),
    ('annotator/operations.py', 'seconds', operations_answer, TemplateError),
    ('annotator/vod_import.py', '_whole', import_answer, VodImportError),
)

#: Every spelling every realm must answer the same way: a whole number of seconds.  Measured on
#: 2026-10-12: all three answer ``int(value)`` for each one, 10 ** 20 included (an ``int`` needs
#: no float rounding).
WHOLE = (0, 1, 12, 12.0, 0.0, -0.0, 452, 1690.0, 3600.0, 10 ** 20)

#: Every spelling every realm must refuse.  ``True`` and ``False`` are instances of ``int``; the
#: two infinities and ``nan`` survive an ``int()`` call; ``2 ** 52 - 0.5`` is the largest
#: half-second a float still states exactly.
REFUSED = (0.5, 12.5, -0.5, -1, True, False, float('nan'), float('inf'), float('-inf'),
           2 ** 52 - 0.5, [], {})

#: The spellings only the import route reads: that form posts a query string, so a whole number
#: arrives as text.  The other two realms refuse every string.
QUERY_STRINGS = ('12', '12.0', '0', '3600.0')

#: The spellings the import route alone reads as "not collected" instead of refusing.
NOT_COLLECTED = (None, '')


def answers(value):
    """What each realm answers for one value: the number, or the voice and sentence it raised."""
    out = []
    for path, _bound, reader, _voice in READERS:
        try:
            out.append((path, reader(value)))
        except Exception as error:            # any voice: the case reads what it names
            out.append((path, f'{type(error).__name__}: {error}'))
    return out


def rule_copies(sources):
    """The lines that spell the rule's body or the sentence's text outside their home.

    ``sources`` holds (label, text) pairs, so a case can give the walk a planted copy as well as
    the real files.  The label must equal the declared path.
    """
    reports = []
    for label, text in sources:
        for lineno, line in enumerate(text.splitlines(), 1):
            for marker, home in ((RULE_BODY, OWNER_FILE),
                                 (SENTENCE_FRAGMENT, SENTENCE_FILE)):
                if marker in line and label != home:
                    reports.append('%s:%d: spells the rule of %s; read the owner'
                                   % (label, lineno, home))
    return reports


def real_sources():
    """Every module that may hold a rule of a broadcast, as (path, text) pairs."""
    return [(path.relative_to(ROOT).as_posix(), path.read_text(encoding='utf-8'))
            for folder in ('src', 'annotator')
            for path in sorted((ROOT / folder).glob('*.py'))]


class OneRuleTest(unittest.TestCase):
    """Way 1: one corpus, three readers, one answer for each value."""

    def test_every_whole_number_answers_the_same_number_in_every_realm(self):
        self.assertGreater(len(WHOLE), 8, 'the corpus must state more than the two cases measured')
        for value in WHOLE:
            with self.subTest(value=value):
                got = answers(value)
                self.assertEqual([int(value)] * len(READERS), [answer for _path, answer in got],
                                 f'{value!r} is a whole number of seconds, and every realm must '
                                 f'answer it: {got}')

    def test_every_value_that_is_not_a_whole_second_is_refused_in_every_realm(self):
        for value in REFUSED:
            with self.subTest(value=value):
                for path, answer in answers(value):
                    self.assertIsInstance(answer, str,
                                          f'{path} answered {answer!r} for {value!r}, which is '
                                          f'not a whole number of seconds')

    def test_the_whole_valued_float_12_0_is_a_whole_number_in_every_realm(self):
        """The measured disagreement of round 81, held as a case.

        Before the change ``operations.seconds(12.0)`` raised TemplateError while the other two
        realms answered 12.  A rule narrowed back to ``type(value) is not int`` fails here.
        """
        self.assertEqual(whole_seconds(12.0, 'startS'), 12)
        self.assertEqual(operations.seconds(12.0, 'startS'), 12)
        self.assertEqual(_whole(12.0, 'start_s', DEFAULT), 12)
        # The datasets realm's acceptance is load-bearing: an id that a client states as 12.0
        self.assertEqual(imported_id('123', 12.0, 30.0), 'tw-123-12-30')
        self.assertEqual(imported_id('123', 12, 30), 'tw-123-12-30')

    def test_the_imported_id_refuses_the_same_values_the_rule_refuses(self):
        for value in REFUSED[:6]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    imported_id('123', value, 30)


class NamedDifferenceTest(unittest.TestCase):
    """Way 2: the realms answer in different voices, and the differences are names, not numbers."""

    def test_the_three_voices_are_the_named_difference(self):
        self.assertEqual([voice for _path, _bound, _reader, voice in READERS],
                         [ValueError, TemplateError, VodImportError])
        self.assertTrue(issubclass(TemplateError, ValueError),
                        'the action layer answers the route as a ValueError')
        self.assertFalse(issubclass(VodImportError, ValueError),
                         'the import route carries a status of its own')

    def test_only_the_import_route_parses_a_query_string(self):
        for text in QUERY_STRINGS:
            with self.subTest(text=text):
                self.assertEqual(_whole(text, 'start_s', DEFAULT), int(float(text)))
                for path, reader, voice in ((OWNER_FILE, datasets_answer, ValueError),
                                            ('annotator/operations.py', operations_answer,
                                             TemplateError)):
                    with self.assertRaises(voice, msg=f'{path} read the string {text!r}'):
                        reader(text)

    def test_only_the_import_route_reads_a_missing_field_as_not_collected(self):
        for value in NOT_COLLECTED:
            with self.subTest(value=value):
                self.assertIs(_whole(value, 'start_s', DEFAULT), DEFAULT)
                with self.assertRaises(ValueError):
                    whole_seconds(value, 'startS')
                with self.assertRaises(TemplateError):
                    operations.seconds(value, 'startS')


class OneSentenceTest(unittest.TestCase):
    """Way 3: every realm states the owner's sentence, and the row's identity travels with it."""

    def test_every_realm_states_the_owners_sentence(self):
        """Each realm fills its own name into the row's one sentence."""
        with self.assertRaises(ValueError) as caught:
            whole_seconds(12.5, 'startS')
        self.assertEqual(str(caught.exception), refusals.WHOLE_SECONDS.format(name='startS'))
        with self.assertRaises(TemplateError) as caught:
            operations.seconds(12.5, 'startS')
        self.assertEqual(str(caught.exception), refusals.WHOLE_SECONDS.format(name='startS'))
        self.assertEqual(caught.exception.fields['name'], 'startS',
                         'the identity names the fact the sentence states')
        with self.assertRaises(VodImportError) as caught:
            _whole(12.5, 'start_s', DEFAULT)          # the name the import route states
        self.assertEqual(str(caught.exception), refusals.WHOLE_SECONDS.format(name='start_s'))

    def test_the_import_route_states_the_sentence_for_a_string_it_cannot_parse(self):
        """The second by-hand copy: a query string that is not a number reads the owner too."""
        sentence = refusals.WHOLE_SECONDS.format(name='start_s')
        with self.assertRaises(VodImportError) as caught:
            _whole('half', 'start_s', DEFAULT)
        self.assertEqual(str(caught.exception), sentence)

    def test_the_sentence_is_the_rows_sentence_and_carries_the_rows_code(self):
        with self.assertRaises(TemplateError) as caught:
            operations.seconds(-1, 'clip start')
        row = refusals.TEMPLATES[refusals.WHOLE_SECONDS]
        self.assertEqual(str(caught.exception), refusals.WHOLE_SECONDS.format(name='clip start'))
        self.assertEqual(caught.exception.fields[refusals.CODE_KEY], row.code)
        self.assertEqual(caught.exception.fields[refusals.ZH_KEY],
                         row.zh.format(name='clip start'))


class OneHomeTest(unittest.TestCase):
    """Way 4: the body and the sentence have one home, and a copy is reported."""

    def test_the_owner_holds_the_rule_body_and_the_row_holds_the_sentence(self):
        """The walk below must have something to find, or it passes for the wrong reason."""
        owner = (ROOT / OWNER_FILE).read_text(encoding='utf-8')
        self.assertIn(RULE_BODY, owner, f'{OWNER_FILE} no longer states the rule')
        home = (ROOT / SENTENCE_FILE).read_text(encoding='utf-8')
        self.assertIn(refusals.WHOLE_SECONDS, home, f'{SENTENCE_FILE} no longer states the row')
        self.assertIn(SENTENCE_FRAGMENT, home)

    def test_no_other_module_spells_the_rule_body_or_the_sentence(self):
        reports = rule_copies(real_sources())
        self.assertEqual([], reports, '\n'.join(reports))

    def test_every_reader_names_the_owner(self):
        for path, bound, _reader, _voice in READERS:
            with self.subTest(reader=f'{path}:{bound}'):
                self.assertIn('whole_seconds', (ROOT / path).read_text(encoding='utf-8'),
                              f'{path} binds {bound} without naming the rule\'s owner')

    def test_a_planted_copy_of_each_is_reported(self):
        module = 'annotator/operations.py'
        real = (ROOT / module).read_text(encoding='utf-8')
        # The planted sentence is built from the row, so this module holds no copy of its text.
        planted = (
            ('    if int(value) != value:\n', 'spells the rule of src/datasets.py'),
            ('    raise ValueError(%r)\n' % refusals.WHOLE_SECONDS.format(name='startS'),
             'spells the rule of annotator/refusals.py'),
        )
        for copy, wanted in planted:
            with self.subTest(copy=copy.strip()):
                text = real + copy
                line = text.count('\n')       # the planted line is the last one
                reports = rule_copies([(module, text)])
                hit = [report for report in reports
                       if report.startswith('%s:%d:' % (module, line))]
                self.assertEqual(1, len(hit), 'the walk lost the inline form %r: %s'
                                              % (copy, reports))
                self.assertIn(wanted, hit[0])


if __name__ == '__main__':
    unittest.main()
