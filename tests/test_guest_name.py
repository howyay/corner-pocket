"""One guest-name maximum: one owner, two readers, one refusal sentence.

The number lived in two places.  The enroll route of ``annotator/unified_server.py`` refused
a name longer than 60 characters.  ``annotator/operations.py`` read the 200-character default
of ``text()`` and accepted that name.  The two layers answered two different questions.

``annotator/refusals.py`` owns the number now (``GUEST_NAME_MAX``).  That module imports no
module of this repository, and ``annotator/operations.py`` imports it, so this home keeps the
import graph acyclic.  Both layers read the name, and the seed-label refusal sentence states
the same number.

The walk below reads source, so it sees a module the runner has not loaded yet.  It finds
every site by content and never by line number.  One case measures the two paths at the
owner's number and at the next one.

Round 55 added the last two readers of the number: ``_person`` and ``_do_guest_promote`` of
``annotator/operations.py`` took the 200-character default of ``text()``.  The console
fields repeated the number as well, and one of them accepted 120 characters.  Two more cases
hold the guest-name path of the operations layer and the guest fields of the console to the
owner.

Round 58 added the second bound of this shape: ``NAME_TEXT_MAX`` (120 characters) holds the
entrant, solo, tournament and event names, six readers of ``annotator/operations.py`` import it,
and the five name fields of the console state it.  The case that holds both layers lives here,
because the walk is the same walk.
"""
from __future__ import annotations

import ast
import re
import tempfile
import unittest
from pathlib import Path

from annotator import operations, refusals, unified_server
# The bound walk and its four supports have one home, tests/_shipped.py.
from _shipped import (bare_bounds, is_length, is_number, owner_bindings, parse,
                     stated_maximum)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_TREES = (ROOT / 'annotator', ROOT / 'src')

# The one home of the number, and the name every reader imports.
OWNER = 'annotator/refusals.py'
OWNED = 'GUEST_NAME_MAX'
# The two readers that bound a name: the enroll route, the seed label and the guest-name
# path of the operations layer.
READERS = (('annotator/unified_server.py', 'enroll_confirm'),
           ('annotator/unified_server.py', 'seed_label'),
           ('annotator/operations.py', 'roster_add'))
# The value in force.  The enroll route refused a longer name before this round, so a
# different number changes the accepted set and needs a decision.
LIMIT = 60
# The words that find the one raise site whose sentence states the number.
SENTENCE_MARK = 'guest name up to'
# The label the operations layer gives a guest name.  A call with this label must pass the
# owner.
GUEST_LABEL = 'guest name'
# The console files that hold a guest-name field, and the fields themselves.  The console
# cannot import Python, so each field states the number as an attribute value.  A field
# carries its name on the line of its own ``maxlength`` attribute.  A selector such as
# ``[name=late_name]`` states no maximum, so the pattern below skips it.
JS_FILES = (ROOT / 'annotator/ops.js', ROOT / 'annotator/vision-stage.js')
GUEST_FIELDS = ('guest${i}', 'late_name', 'solo_name', 'enroll-name', 'guest-name')
GUEST_FIELD = re.compile(r'(?:"|\')?(guest\$\{i\}|late_name|solo_name|enroll-name|guest-name)'
                         r'(?:"|\')?(?=[^\n]*maxlength)')
MAXLENGTH = re.compile(r'maxlength=(?:"|\')?(\d+)')

# The name bound the console states as well: the entrant, solo, tournament and event names of a
# player.  The console cannot import the Python constant, so each field states the number as the
# value of its ``maxlength`` attribute.  The markers below are content, not line numbers: two
# event-name fields share one spelling, and the late-entrant field carries a template name.
NAME_FIELDS = ("input('night-name'", "input('name'", '`${name}_name`', 'id="event-name"')
# The measured number of console fields that carry a name.  A new field needs a decision, so the
# case below fails and names the count.
NAME_FIELD_COUNT = 5
# The labels the operations layer gives the names NAME_TEXT_MAX bounds.  A call with one of these
# labels and no third argument takes the 200-character default of text(), and that is another rule.
NAME_LABELS = ('name', 'entrant name')
# The measured number of ``text()`` calls that read the name bound.
NAME_SITE_COUNT = 6


def source_files():
    """Every service module that could bound a name."""
    return sorted(path for tree in SOURCE_TREES for path in tree.glob('*.py'))


def relative(path):
    return path.relative_to(ROOT).as_posix()


def guest_text_calls(path):
    """Every ``text(...)`` call of one module whose label names a guest, with its line."""
    found = []
    for node in ast.walk(parse(path)):
        if not isinstance(node, ast.Call) or getattr(node.func, 'id', None) != 'text':
            continue
        if len(node.args) < 2:
            continue
        label = node.args[1]
        if isinstance(label, ast.Constant) and label.value == GUEST_LABEL:
            found.append((node.lineno, node))
    return found


def guest_maxlengths(path):
    """Every guest-name field of one console file, with its name and its maximum.

    A field states a maximum.  A selector such as ``[name=late_name]`` and a read of a
    field value state no maximum, so they are not fields of this walk.
    """
    found = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        field = GUEST_FIELD.search(line)
        if field:
            found.append((number, field.group(1), MAXLENGTH.search(line)))
    return found


def name_maxlengths(path):
    """Every console field of one module that carries a name marker, with its maximum.

    A field states a maximum.  The search starts at the marker, so a field that follows another
    bounded field on the same line cannot answer with that field's number.
    """
    found = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        starts = [line.index(marker) for marker in NAME_FIELDS if marker in line]
        if starts:
            found.append((number, MAXLENGTH.search(line, min(starts))))
    return found


def raised_sentences(path):
    """Every sentence a raise site of one module states, with its line."""
    found = []
    for node in ast.walk(parse(path)):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
            continue
        first = node.exc.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.append((node.lineno, first.value))
    return found


def defined_function(path, name):
    """The function one module defines under this name, or None."""
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def text_calls(node):
    """Every ``text(...)`` call under one node, with its line."""
    return [(child.lineno, child) for child in ast.walk(node)
            if isinstance(child, ast.Call) and getattr(child.func, 'id', None) == 'text']


def length_bounds(node):
    """Every site under one node that compares a length with a bare number."""
    found = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Compare):
            continue
        operands = [child.left] + list(child.comparators)
        if any(is_length(operand) for operand in operands):
            for operand in operands:
                if isinstance(operand, ast.Constant) and type(operand.value) is int:
                    found.append((child.lineno, ast.unparse(child)))
    return found


class GuestNameTest(unittest.TestCase):
    def test_one_module_owns_the_number(self):
        """One module binds the owner's name, and it binds the value in force."""
        found = {relative(path): [site for site in owner_bindings(path) if site[1] == OWNED]
                 for path in source_files()}
        holders = {name: sites for name, sites in found.items() if sites}
        self.assertEqual([OWNER], list(holders),
                         'the guest-name maximum must have one home.  %s imports no module of '
                         'this repository, and annotator/operations.py imports it, so another '
                         'home makes an import cycle or a second value.  Found: %r'
                         % (OWNER, sorted(holders)))
        sites = holders[OWNER]
        self.assertEqual(1, len(sites), '%s binds %s more than once' % (OWNER, OWNED))
        line, _, value = sites[0]
        self.assertTrue(is_number(value, LIMIT),
                        '%s:%d must bind the number %d.  The enroll route refused a longer name '
                        'before this round, so another number changes the accepted set.'
                        % (OWNER, line, LIMIT))

    def test_no_second_name_holds_the_bound(self):
        """No other name holds a maximum of a name: a second name is a second owner."""
        loose = ['%s:%d: %s' % (relative(path), line, target)
                 for path in source_files() for line, target, _ in owner_bindings(path)
                 if target.endswith('NAME_MAX') and (relative(path), target) != (OWNER, OWNED)]
        self.assertEqual([], loose,
                         'a second name holds a bound of a guest name.  %s owns the number, and '
                         'every reader imports it:\n%s' % (OWNER, '\n'.join(loose)))

    def test_no_module_bounds_a_name_with_the_bare_number(self):
        """No module bounds a value with the bare number: every reader imports the owner."""
        sites = ['%s:%d: %s' % (relative(path), line, code)
                 for path in source_files() for line, code in bare_bounds(path, LIMIT)]
        self.assertEqual([], sites,
                         'a module bounds a value with the bare number %d.  Import %s from %s '
                         'instead, so the two layers cannot disagree:\n%s'
                         % (LIMIT, OWNED, OWNER, '\n'.join(sites)))

    def test_the_name_readers_state_the_owner(self):
        """Each reader that bounds a length states the owner, never a bare number."""
        sites = []
        for module, function in READERS:
            node = defined_function(ROOT / module, function)
            self.assertIsNotNone(node, '%s defines no %s' % (module, function))
            sites += ['%s:%d: %s' % (module, line, code) for line, code in length_bounds(node)]
        self.assertEqual([], sites,
                         'a guest-name reader bounds a length with a bare number, so the layers '
                         'can disagree.  Pass %s from %s instead:\n%s'
                         % (OWNED, OWNER, '\n'.join(sites)))

    def test_both_layers_read_the_owner(self):
        """The operations layer and the server hold the owner's value, not a copy."""
        holders = {'refusals': refusals.GUEST_NAME_MAX,
                   'operations': getattr(operations, OWNED, None),
                   'unified_server': getattr(unified_server, OWNED, None)}
        self.assertEqual({refusals.GUEST_NAME_MAX}, set(holders.values()),
                         'every layer reads %s from %s: %r' % (OWNED, OWNER, holders))

    def test_the_enroll_path_states_the_owner(self):
        """The guest-name path of the operations layer passes the owner, never the default."""
        enroll = defined_function(ROOT / 'annotator/operations.py', 'roster_add')
        self.assertIsNotNone(enroll, 'annotator/operations.py defines no roster_add')
        calls = text_calls(enroll)
        self.assertTrue(calls, 'roster_add no longer validates the guest name with text()')
        for line, call in calls:
            stated = list(call.args[2:3]) + [word.value for word in call.keywords
                                             if word.arg == 'maximum']
            self.assertEqual(1, len(stated),
                             'annotator/operations.py:%d calls text() without a maximum, so the '
                             'guest name falls back to the default of text()' % line)
            self.assertEqual(OWNED, ast.unparse(stated[0]),
                             'annotator/operations.py:%d must pass %s as the maximum of text()'
                             % (line, OWNED))

    def test_the_guest_label_states_the_owner(self):
        """Every guest-name reader of the operations layer passes the owner, never the default."""
        module = ROOT / 'annotator/operations.py'
        calls = guest_text_calls(module)
        self.assertEqual(2, len(calls),
                         'the operations layer reads a guest name at two sites, _person and '
                         '_do_guest_promote, and this walk found %d' % len(calls))
        for line, call in calls:
            stated = stated_maximum(call)
            self.assertIsNotNone(stated,
                                 'annotator/operations.py:%d calls text() for a guest name '
                                 'without a maximum, so the name falls back to the 200-character '
                                 'default of text()' % line)
            self.assertEqual(OWNED, ast.unparse(stated),
                             'annotator/operations.py:%d must pass %s as the maximum of text()'
                             % (line, OWNED))

    def test_the_console_guest_fields_state_the_owner(self):
        """Every guest-name field of the console states the owner's number."""
        pattern = re.compile(r'^GUEST_NAME_MAX = (\d+)$', re.MULTILINE)
        match = pattern.search((ROOT / OWNER).read_text(encoding='utf-8'))
        self.assertIsNotNone(match, '%s binds %s on a line of its own' % (OWNER, OWNED))
        value = int(match.group(1))
        expected = re.compile(r'maxlength=(?:"|\')%d(?:"|\')' % value)
        sites, wrong = {}, []
        for path in JS_FILES:
            for line, name, found in guest_maxlengths(path):
                sites.setdefault(name, []).append('%s:%d' % (relative(path), line))
                if found is None:
                    wrong.append('%s:%d: the field %s states no maxlength'
                                 % (relative(path), line, name))
                elif not expected.search(found.string):
                    wrong.append('%s:%d: the field %s states maxlength="%s"'
                                 % (relative(path), line, name, found.group(1)))
        self.assertEqual(sorted(GUEST_FIELDS), sorted(sites),
                         '%s owns %s, and the console holds one field per guest-name input.  '
                         'Each of these fields states the number.  Found: %r'
                         % (OWNER, OWNED, sites))
        self.assertEqual([], wrong,
                         '%s owns %s, and the value in force is %d.  A guest field of the console '
                         'holds that number:\n%s' % (OWNER, OWNED, value, '\n'.join(wrong)))

    def test_the_name_bound_states_one_owner_in_both_layers(self):
        """One owner holds the 120-character name bound, and both layers state it.

        This case lives beside the guest-name bound because the walk is the same walk: one module
        owns a number, the Python readers import the name, and the console fields state the value.
        A second module would copy this file's parsers.
        """
        pattern = re.compile(r'^NAME_TEXT_MAX = (\d+)$', re.MULTILINE)
        match = pattern.search((ROOT / OWNER).read_text(encoding='utf-8'))
        self.assertIsNotNone(match, '%s binds NAME_TEXT_MAX on a line of its own' % OWNER)
        value = int(match.group(1))
        self.assertEqual(value, refusals.NAME_TEXT_MAX, 'the module and its source agree')
        self.assertEqual(value, operations.NAME_TEXT_MAX,
                         'and the operations layer imports that name')
        # The Python side: every name-labelled text() call that states a bound states the name.
        stated, bare = [], []
        for node in ast.walk(parse(ROOT / 'annotator/operations.py')):
            if not isinstance(node, ast.Call) or getattr(node.func, 'id', None) != 'text':
                continue
            label = node.args[1] if len(node.args) > 1 else None
            if not isinstance(label, ast.Constant) or label.value not in NAME_LABELS:
                continue
            maximum = stated_maximum(node)
            if maximum is None:
                continue
            if isinstance(maximum, ast.Name) and maximum.id == 'NAME_TEXT_MAX':
                stated.append(node.lineno)
            elif is_number(maximum, value):
                bare.append((node.lineno, ast.unparse(node)))
        self.assertEqual(NAME_SITE_COUNT, len(stated),
                         'annotator/operations.py reads NAME_TEXT_MAX on every name path it bounds.  '
                         'Found: %r' % (stated,))
        self.assertEqual([], bare,
                         'a name path states the owner NAME_TEXT_MAX, never the bare number %d:\n%s'
                         % (value, '\n'.join('%d: %s' % site for site in bare)))
        # The console side: every name field states the same number, and no other field does.
        expected = re.compile(r'maxlength=(?:"|\')%d(?:"|\')' % value)
        fields, wrong = [], []
        for path in JS_FILES:
            for line, found in name_maxlengths(path):
                fields.append('%s:%d' % (relative(path), line))
                if found is None or not expected.search(found.string):
                    wrong.append('%s:%d: the field states maxlength="%s"'
                                 % (relative(path), line, found.group(1) if found else 'none'))
        self.assertEqual(NAME_FIELD_COUNT, len(fields),
                         'the console holds %d name fields, and each one states the bound:\n%s'
                         % (NAME_FIELD_COUNT, '\n'.join(fields)))
        self.assertEqual([], wrong,
                         '%s owns NAME_TEXT_MAX, and the value in force is %d.  A name field of the '
                         'console holds that number:\n%s' % (OWNER, value, '\n'.join(wrong)))

    def test_the_refusal_sentence_carries_the_owner_number(self):
        """One raise site states the sentence, and the sentence states the owner's number."""
        sentence = refusals.SEED_LABEL_TEXT_INVALID
        self.assertIn(str(refusals.GUEST_NAME_MAX), sentence,
                      'the seed-label refusal sentence must state the number %s owns' % OWNED)
        self.assertEqual('seed_label_text_invalid', refusals.REFUSALS[sentence].code,
                         'the refusal table no longer keys the sentence on its own row')
        found = [(line, text) for line, text in raised_sentences(ROOT / 'annotator/unified_server.py')
                 if SENTENCE_MARK in text]
        self.assertEqual(1, len(found),
                         'one raise site of annotator/unified_server.py states the seed-label '
                         'sentence, and this walk found %d' % len(found))
        self.assertEqual(sentence, found[0][1],
                         'annotator/unified_server.py:%d states a sentence that differs from '
                         'refusals.SEED_LABEL_TEXT_INVALID' % found[0][0])

    def test_the_route_and_the_operations_layer_agree(self):
        """Both layers accept the owner's number and refuse the next one."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backend = unified_server.Backend(root)
            unified_server.atomic_save(root / 'out' / 'pid2_tracklets.json', {
                '68-94': {'tracklets': [{'id': 1, 'n': 2,
                                         'samples': [[68, [1, 2, 3, 4]], [70, [2, 3, 4, 5]]]}]}})
            accepted, refused = 'n' * LIMIT, 'n' * (LIMIT + 1)
            # The enroll route: the owner's number passes its bound, the next one does not.
            result = backend.post(['api', 'identity', 'enroll-confirm'],
                                  {'token': 'gone', 'player_name': accepted})
            self.assertEqual('preview_expired', result.get('reason'),
                             'the enroll route refused a name of %d characters' % LIMIT)
            with self.assertRaises(unified_server.APIError) as enroll_refusal:
                backend.post(['api', 'identity', 'enroll-confirm'],
                             {'token': 'gone', 'player_name': refused})
            self.assertEqual('player_name must be at most %d characters' % refusals.GUEST_NAME_MAX,
                             str(enroll_refusal.exception))
            # The operations layer: the same two answers, and never the 200-character default.
            store = operations.Operations(root / 'state.json')
            store.enroll_player({'id': 'p-%d' % LIMIT, 'name': accepted}, {})
            with self.assertRaises(ValueError) as operations_refusal:
                store.enroll_player({'id': 'p-next', 'name': refused}, {})
            self.assertEqual(refusals.filled_refusal(refusals.TEXT_LENGTH, name='name',
                                                     maximum=refusals.GUEST_NAME_MAX)[0],
                             str(operations_refusal.exception))
            # The seed label: the parse holds the owner's number, and the route refuses the
            # next one with the sentence the refusal table keys the Chinese line on.
            self.assertEqual(accepted, unified_server.Backend.seed_label(accepted))
            self.assertIsNone(unified_server.Backend.seed_label(refused))
            with self.assertRaises(unified_server.APIError) as seed_refusal:
                backend.post(['api', 'vod30', 'seeds'],
                             {'win': '68-94', 'track_id': 1, 't': 68, 'label': refused})
            self.assertEqual(refusals.SEED_LABEL_TEXT_INVALID, str(seed_refusal.exception))
            body = unified_server.refusal_body(seed_refusal.exception)
            self.assertEqual(refusals.REFUSALS[refusals.SEED_LABEL_TEXT_INVALID].code,
                             body[refusals.CODE_KEY])


if __name__ == '__main__':
    unittest.main()
