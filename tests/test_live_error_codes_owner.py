"""Hold the sentences of the Twitch layer to the code table of the live layer.

``annotator/live_processing.py`` holds ``_ERROR_CODES``: thirteen English sentences, each
bound to a stable code that the console renders in the operator's language.  Some of those
sentences are raised in ``annotator/twitch_source.py`` and the rest in the live module
itself, so the table and the raise sites are two halves of one contract:

* a sentence a raise site writes must be a key of the table, or a case of
  ``_ERROR_PATTERNS``, or stand in ``UNMAPPED`` below with a reason;
* a key of the table must be a sentence the live layer still writes, or it phrases a
  failure that nobody can reach.

The live module catches ``TwitchSourceError`` alone (``annotator/live_processing.py:337``
through ``_resolve_twitch``) and gives the sentence to ``_fail``, which maps it with
``_error_code``.  A sentence outside both maps reports ``error_code = None``, and the
console then shows the English sentence to an operator who reads Chinese.  A row without a
site is the other half of the same defect: a code no session can ever report.

This module reads the raise sites with ``ast``, reads the table and the patterns out of
their owner, and compares the two directions.  The written set holds every sentence of both
modules and every sentence a call of ``_fail`` hands to the sink.  This module adds no row
to ``_ERROR_CODES``: a new row changes what the console can phrase, so the console table
needs that row too.  The unmapped sentences are recorded in ``UNMAPPED`` instead.

A sentence is the unit of comparison, not a line number: an edit that moves a raise site
keeps its sentence, so the guard stays green, and the report names the line it reads now.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
#: The layer that publishes the error sentences of a live Twitch session.
TWITCH = ROOT / 'annotator' / 'twitch_source.py'
#: The layer that holds the code table and the live module's own raise sites.
LIVE = ROOT / 'annotator' / 'live_processing.py'
#: The stable path prefixes the report prints, so no message carries an absolute path.
TWITCH_NAME = 'annotator/twitch_source.py'
LIVE_NAME = 'annotator/live_processing.py'
#: The error class of the Twitch layer: every raise of this class reaches ``_fail``.
ERROR_CLASS = 'TwitchSourceError'
#: The sink of the live module: the sentence there goes through ``_error_code``.
SINK = '_fail'

#: Sentences a raise site writes that no row of ``_ERROR_CODES`` holds, with the reason.
#: One entry per sentence.  A row for one of them needs the console phrase too
#: (``annotator/app.js`` holds ``liveErrorCodes``), so this guard records the sentence
#: instead of adding a row, and the console falls back to English until that row exists.
UNMAPPED = (
    ('Twitch playback response exceeds the size limit',
     'no client phrase yet: the console would show this English sentence'),
    ('Twitch returned an invalid playback playlist',
     'no client phrase yet: the console would show this English sentence'),
    ('Expected a canonical public Twitch channel URL',
     'no client phrase yet: the console would show this English sentence'),
    ('Twitch playback is restricted or requires browser authorization',
     'the row "Twitch playback is unavailable or requires browser authorization" is its '
     'twin, and this sentence must not take that key'),
    ('Twitch returned an invalid playback token response',
     'no client phrase yet: the console would show this English sentence'),
    ('Twitch returned no playable live media playlist',
     'no client phrase yet: the console would show this English sentence'),
)

#: One filled case per pattern of ``_ERROR_PATTERNS``, with the code and the params it must
#: report.  A row of the table holds a sentence with no value; a pattern holds a sentence
#: with values, so a pattern is checked with a filled sentence instead of with a table key.
PATTERN_CASES = (
    ('Twitch playback request failed (HTTP 403)', 'twitch_http', {'status': 403}),
    ('Replay stalled: no data from Twitch for 20 s at 0:03:12 of 1:02:03; '
     'restart with start_s=192 to continue', 'replay_stalled',
     {'waited_s': 20, 'at_s': 192, 'length_s': 3723, 'start_s': 192}),
    ('Replay stalled: no data from Twitch for 20 s at 0:03:12 of an unknown length; '
     'restart with start_s=192 to continue', 'replay_stalled',
     {'waited_s': 20, 'at_s': 192, 'length_s': None, 'start_s': 192}),
)

#: The value names a pattern captures and the params it must report for them: a position
#: and a length become seconds, and an unknown length becomes None.
PATTERN_PARAMS = {'at': 'at_s', 'length': 'length_s'}

#: The file that writes the sentence of each pattern of ``_ERROR_PATTERNS``, with a text
#: that file must still carry.  The Twitch layer raises the HTTP sentence and the server
#: writes the stall sentence, so a pattern with no site is a code nobody can reach.
PATTERN_ORIGINS = {
    'twitch_http': ('annotator/twitch_source.py', 'playback request failed (HTTP'),
    'replay_stalled': ('annotator/unified_server.py', 'Replay stalled: no data from Twitch'),
}


def _parsed(path, source=None):
    """The parsed module: ``source`` if given, else the file on disk."""
    return ast.parse(source if source is not None else path.read_text(encoding='utf-8'))


def _own_nodes(function):
    """The nodes of ``function`` itself, without the body of a function inside it.

    A test case, or any nested ``def``, is a function of its own.  Reading the outer
    function must not read a raise site of the inner one twice, and a name bound in the
    inner one must not look bound in the outer one.
    """
    found, pending = [], list(function.body)
    while pending:
        node = pending.pop()
        found.append(node)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            pending.extend(ast.iter_child_nodes(node))
    return found


def _bound_error_names(function, module_names):
    """The names in ``function`` that are bound to the Twitch error class.

    The class itself is one of them.  A parameter whose default is a module level name
    (``error=TwitchSourceError`` in ``hls_lines``) joins them, because that parameter is
    the same class unless a caller passes another one.
    """
    bound = {ERROR_CLASS}
    args, defaults = function.args.args, function.args.defaults
    for argument, default in zip(args[len(args) - len(defaults):], defaults):
        if isinstance(default, ast.Name) and default.id in module_names:
            bound.add(argument.arg)
    return bound


def _called_name(node):
    """The name a ``Call`` node calls, or None: ``_fail(x)`` gives ``'_fail'``."""
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    return node.func.attr if isinstance(node.func, ast.Attribute) else None


def _raised_name(node):
    """The name a ``raise`` statement names, or None."""
    error = node.exc
    if isinstance(error, ast.Call):
        return _called_name(error)
    return error.id if isinstance(error, ast.Name) else None


def _static_strings(node):
    """The string constants inside ``node``, without the ``%`` format strings.

    ``'Twitch playback request failed (HTTP %d)'`` is a shape, not a sentence: the values
    go in at the raise site, so a pattern owns it.  This helper skips every literal with a
    ``%``, and the two pattern cases above own those.
    """
    return [part.value for part in ast.walk(node)
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
            and '%' not in part.value]


def _raise_sentences(text, bound_names):
    """``(line, sentence)`` for every sentence a raise site of this class writes."""
    found = []
    for function in [node for node in ast.walk(ast.parse(text))
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        bound = bound_names(function)
        for node in _own_nodes(function):
            if isinstance(node, ast.Raise) and _raised_name(node) in bound:
                found.extend((node.lineno, sentence) for sentence in _static_strings(node))
    return sorted(found)


def _strings_inside(node):
    """The string constants of one expression, in source order."""
    return [part.value for part in ast.walk(node)
            if isinstance(part, ast.Constant) and isinstance(part.value, str)]


def _sink_sentences(text, sink):
    """``(line, sentence)`` for every sentence the live module hands to ``sink``.

    ``_fail`` takes a sentence, and at some sites a code beside it.  The code is a value of
    the table, not a sentence, so only the sentence of the call joins the written set.
    """
    found = []
    for function in [node for node in ast.walk(ast.parse(text))
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        for node in _own_nodes(function):
            if _called_name(node) != sink:
                continue
            for argument in node.args:
                found.extend((node.lineno, sentence) for sentence in _strings_inside(argument))
    return sorted(set(found))


def _format_sentences(path):
    """The ``%`` format literals a file writes: the shapes a pattern of the table captures."""
    return [part.value for part in ast.walk(_parsed(path))
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
            and '%' in part.value]


def _sentences_of(path):
    """Every sentence a file writes, with the pieces of an implicit join put together.

    A writer splits a long sentence over two lines, as in::

        raise TwitchSourceError('Twitch channel is offline or has no '
                                'public video variants')

    The parser sees two constants there, so the two are joined again, and the joined
    sentence joins the set beside each piece.
    """
    source = path.read_text(encoding='utf-8')
    lines = source.splitlines()
    parts = sorted((node for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value in lines[node.lineno - 1]),
                   key=lambda node: (node.lineno, node.col_offset))
    found = set()
    for part in parts:
        run = part.value
        for other in parts:
            if other.lineno == part.end_lineno + 1 and other.col_offset == part.col_offset:
                run += other.value
                part = other
        found.update({run, part.value})
    return found


def _table(path):
    """``_ERROR_CODES`` of ``path``: sentence -> code, read from the assignment."""
    for node in _parsed(path).body:
        if isinstance(node, ast.Assign) \
                and any(isinstance(target, ast.Name) and target.id == '_ERROR_CODES'
                        for target in node.targets):
            return {key.value: value.value for key, value in zip(node.value.keys, node.value.values)}
    raise AssertionError(LIVE_NAME + ' holds no _ERROR_CODES assignment')


def _patterns(path):
    """``_ERROR_PATTERNS`` of ``path``: name -> compiled regular expression."""
    for node in _parsed(path).body:
        if isinstance(node, ast.Assign) \
                and any(isinstance(target, ast.Name) and target.id == '_ERROR_PATTERNS'
                        for target in node.targets):
            return {row.elts[0].value: re.compile(row.elts[1].args[0].value) for row in node.value.elts}
    raise AssertionError(LIVE_NAME + ' holds no _ERROR_PATTERNS tuple')


def _placeholders(text):
    """The placeholder spellings of one sentence: ``%d`` and ``%(name)s``."""
    return re.findall(r'%\((\w+)\)s|%[a-zA-Z]', text)


def _is_pattern_case(sentence, patterns):
    """Whether ``sentence`` is one case of a pattern of the live module.

    The rule is two sided.  Some pattern must match the sentence whole, and every
    placeholder the sentence holds must be a capture group of that pattern.  So
    ``'Twitch playback request failed (HTTP %d)'`` is a case of ``twitch_http``, and a
    sentence that no pattern matches whole is a case of nothing.
    """
    for pattern in patterns.values():
        match = pattern.fullmatch(sentence)
        if match and set(_placeholders(sentence)) <= set(match.groupdict()):
            return True
    return False


def _unmapped_report(raised, table, patterns, reasons):
    """Every raise sentence that no row, no pattern and no list entry claims."""
    return [f'{TWITCH_NAME}:{line} {sentence}'
            for line, sentence in raised
            if sentence not in table and not _is_pattern_case(sentence, patterns)
            and sentence not in reasons]


def _params_of(sentence, pattern):
    """The params the live module reports for a sentence, as ``_error_code`` builds them.

    A position and a length become seconds (``at_s``, ``length_s``), an unknown length
    becomes None, and every other value becomes a number.  The params are numbers and
    None, never English, so the console can phrase each one in either language.
    """
    match = pattern.fullmatch(sentence)
    params = {}
    for key, value in match.groupdict().items():
        if key in PATTERN_PARAMS:
            parts = value.split(':') if value[0].isdigit() else None
            params[PATTERN_PARAMS[key]] = (
                int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) if parts else None)
        else:
            params[key] = int(value)
    return params


def _unclaimed_report(claimed, sentences):
    """Every table key that no sentence of the live layer writes."""
    return [name for name in claimed if name not in sentences]


class LiveErrorCodeOwnerTests(unittest.TestCase):
    """The code table and the raise sites of the live Twitch layer name one vocabulary."""

    def setUp(self):
        self.table = _table(LIVE)
        self.patterns = _patterns(LIVE)
        self.twitch_text = TWITCH.read_text(encoding='utf-8')
        self.live_text = LIVE.read_text(encoding='utf-8')
        self.raised = _raise_sentences(self.twitch_text, self._bound)
        self.sentences = _sentences_of(TWITCH) | _sentences_of(LIVE) \
            | {sentence for _, sentence in _sink_sentences(self.live_text, SINK)}

    def _bound(self, function):
        """The error names in ``function``: the class itself and every bound parameter."""
        module_names = {node.name for node in _parsed(TWITCH).body
                        if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
        return _bound_error_names(function, module_names)

    def test_every_sentence_of_a_raise_site_is_mapped_or_recorded(self):
        """A sentence from the Twitch layer must reach a code, or stand in UNMAPPED."""
        reasons = dict(UNMAPPED)
        report = _unmapped_report(self.raised, self.table, self.patterns, reasons)
        self.assertEqual(
            [], report,
            'these sentences of ' + TWITCH_NAME + ' reach no code, so the console falls back '
            'to English for each one. Give each sentence a row of _ERROR_CODES, or record it in '
            'UNMAPPED of this module when the console has no phrase yet:\n'
            + '\n'.join(f'  {entry}' for entry in report))
        checked = {sentence for _, sentence in self.raised}
        self.assertEqual(
            sorted(checked & set(reasons)), sorted({s for s, _ in UNMAPPED if s in checked}),
            'UNMAPPED holds a sentence that no raise site of ' + TWITCH_NAME + ' writes, so the '
            'list carries a stale entry')
        self.assertTrue(all(reason.strip() for reason in reasons.values()),
                        'every entry of UNMAPPED needs a reason of one line')

    def test_every_table_row_is_a_sentence_of_the_live_layer(self):
        """A code the console renders must have a sentence that some live module writes."""
        unclaimed = _unclaimed_report(list(self.table), self.sentences)
        self.assertEqual(
            [], unclaimed,
            'these rows of _ERROR_CODES name a code that no sentence of ' + LIVE_NAME + ' or '
            + TWITCH_NAME + ' writes, so the console holds a phrase for a failure nobody can '
            'reach:\n' + '\n'.join(f'  {name}' for name in unclaimed))
        for sentence, code, params in PATTERN_CASES:
            with self.subTest(sentence=sentence):
                matched = [name for name, pattern in self.patterns.items()
                           if pattern.fullmatch(sentence)]
                self.assertEqual([code], matched,
                                 f'{sentence!r} is not one case of the pattern {code} of '
                                 '_ERROR_PATTERNS any more')
                self.assertEqual(params, _params_of(sentence, self.patterns[code]),
                                 f'the pattern {code} reports the wrong params for {sentence!r}, '
                                 'so the console cannot phrase this failure in either language')
        for code, (origin, needle) in PATTERN_ORIGINS.items():
            with self.subTest(origin=origin):
                self.assertIn(needle, (ROOT / origin).read_text(encoding='utf-8'),
                              f'the pattern {code} captures a sentence that {origin} does not '
                              'write any more, so the console holds a phrase for a failure '
                              'nobody can reach')
        self.assertEqual(13, len(self.table),
                         'the code table changed size; state the new number and its reason here')

    def test_a_planted_sentence_with_no_row_is_reported(self):
        """The guard reads a sentence that no row holds, and names its file and its line."""
        offender = "raise TwitchSourceError('Twitch returned a sentence no row holds')"
        planted = '\n\ndef _planted_probe(flag):\n    if flag:\n        ' + offender + '\n    return flag\n'
        text = self.twitch_text.rstrip('\n') + '\n' + planted
        self.assertNotEqual(self.twitch_text, text, 'the plant changed no byte of the twin source')
        line = text.splitlines().index('        ' + offender) + 1
        report = _unmapped_report(_raise_sentences(text, self._bound), self.table, self.patterns,
                                  dict(UNMAPPED))
        self.assertIn(
            f'{TWITCH_NAME}:{line} Twitch returned a sentence no row holds', report,
            'the guard did not report the planted sentence with its file and its line, so it '
            'reads no raise site of ' + TWITCH_NAME)
        self.assertEqual(1, len(report),
                         'the plant changed the report by more than one entry:\n'
                         + '\n'.join(f'  {entry}' for entry in report))


if __name__ == '__main__':
    unittest.main()
