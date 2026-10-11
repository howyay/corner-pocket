"""Hold the note length to the one number that two layers use.

A note is the longest text this program accepts.  ``annotator/operations.py`` owns the
number, and it bounds two sites with it: the notes of a saved regular, and the text of one
note.  The console cannot import a Python module, so ``annotator/ops.js`` states the number
in the markup of the note field and of the note textarea.

Round 55 measured the cost of the drift.  The number stood in four places with no name and
no guard, so one edit could move one layer away from the other.  A save would then keep a
note that the form refuses, or the form would refuse a note that the save keeps.

This module reads the owner and the console source, and it compares them.  The rendered
markup is a case of ``tests/test_ops.js``, which holds the renderer.

Two numbers of the note path are deliberately not the owner.  The first number is the
sentence ``Player notes must be text up to 4000 characters``: ``annotator/refusals.py`` keys
that sentence on the code ``player_notes_too_long``, the console shows the line, and the
first case below holds the number of the sentence and the number of the owner together.  The
second number is the sentence of the ``note_add`` declaration, ``note must contain 1-4000
characters``; ``tests/test_operations.py`` pins that sentence because a client reads it.
That declaration earns no number of its own, so the bound of that path is the owner alone.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from annotator import operations, refusals
# The bound walk and its four supports have one home, tests/_shipped.py.
from _shipped import bare_bounds, is_number, parse, stated_maximum

ROOT = Path(__file__).resolve().parents[1]
# The one home of the number, and the name both Python sites read.
OWNER = 'annotator/operations.py'
OPERATIONS = ROOT / 'annotator' / 'operations.py'
CONSOLE = ROOT / 'annotator' / 'ops.js'
# The value in force.  The console and the service both refuse a longer note today, so a
# different number changes the accepted set and needs a decision.
LIMIT = 4000
# The console fields that hold the number.  A field names itself in markup, and a field
# without that name is not a note field of this walk.
NOTE_FIELDS = ('notes', 'text')
NOTE_FIELD = re.compile(r'name=(?:"|\')?(notes|text)(?:"|\')?(?=[^\n]*maxlength)')
MAXLENGTH = re.compile(r'maxlength=(?:"|\')?(\d+)')
# The refusal row of the notes guard.  Its sentence states the number too, because it is
# the sentence of the refusal table and the console shows that line.
NOTES_SENTENCE = 'Player notes must be text up to 4000 characters'
NOTES_CODE = 'player_notes_too_long'
SENTENCE_NUMBER = re.compile(r'up to (\d+) characters')


def named_bindings(path, name):
    """Every site of one module that binds one name, with its line and its value."""
    found = []
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            found.append((node.lineno, node.value))
    return found


def note_text_calls(path):
    """Every ``text(...)`` call of one module whose label names a note, with its line."""
    found = []
    for node in ast.walk(parse(path)):
        if not isinstance(node, ast.Call) or getattr(node.func, 'id', None) != 'text':
            continue
        if len(node.args) < 2:
            continue
        label = node.args[1]
        if isinstance(label, ast.Constant) and label.value == 'note':
            found.append((node.lineno, node))
    return found


def console_fields(path):
    """Every note field of the console source, with its name and its maximum."""
    found = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        field = NOTE_FIELD.search(line)
        if field:
            found.append((number, field.group(1), MAXLENGTH.search(line)))
    return found


class NoteLimitTest(unittest.TestCase):
    def test_one_module_owns_the_number(self):
        """One module binds the owner's name, and it binds the value in force."""
        found = named_bindings(OPERATIONS, 'NOTE_MAX')
        self.assertEqual(1, len(found),
                         '%s binds NOTE_MAX at one site, and this walk found %d'
                         % (OWNER, len(found)))
        line, value = found[0]
        self.assertTrue(is_number(value, LIMIT),
                        '%s:%d must bind the number %d' % (OWNER, line, LIMIT))
        self.assertEqual(LIMIT, operations.NOTE_MAX,
                         'every reader imports NOTE_MAX from %s, so the module in force must '
                         'hold the number %d' % (OWNER, LIMIT))
        row = refusals.REFUSALS.get(NOTES_SENTENCE)
        self.assertIsNotNone(row,
                             'the notes guard raises a sentence the refusal table keys, and '
                             'this walk found no row for %r' % NOTES_SENTENCE)
        self.assertEqual(NOTES_CODE, row.code,
                         'the row of %r no longer carries its code' % NOTES_SENTENCE)
        stated = SENTENCE_NUMBER.search(NOTES_SENTENCE)
        self.assertIsNotNone(stated, 'the notes sentence must state the number in words')
        self.assertEqual(operations.NOTE_MAX, int(stated.group(1)),
                         'the refusal sentence states a number that differs from NOTE_MAX, so '
                         'one edit moves the sentence away from the guard')

    def test_the_console_fields_state_the_owner(self):
        """Every note field of the console states the owner's number."""
        value = operations.NOTE_MAX
        expected = re.compile(r'maxlength=(?:"|\')%d(?:"|\')' % value)
        sites, wrong = {}, []
        for line, name, found in console_fields(CONSOLE):
            sites.setdefault(name, []).append('annotator/ops.js:%d' % line)
            if found is None:
                wrong.append('annotator/ops.js:%d: the field %s states no maxlength'
                             % (line, name))
            elif not expected.search(found.string):
                wrong.append('annotator/ops.js:%d: the field %s states maxlength="%s"'
                             % (line, name, found.group(1)))
        self.assertEqual(sorted(NOTE_FIELDS), sorted(sites),
                         '%s owns NOTE_MAX, and the console holds one field per note input.  '
                         'Each of these fields states the number.  Found: %r' % (OWNER, sites))
        self.assertEqual([], wrong,
                         '%s owns NOTE_MAX, and the value in force is %d.  A note field of the '
                         'console holds that number:\n%s' % (OWNER, value, '\n'.join(wrong)))

    def test_the_python_sites_state_the_owner(self):
        """Both Python bounds read the owner, and neither one states the bare number."""
        calls = note_text_calls(OPERATIONS)
        self.assertEqual(1, len(calls),
                         'the operations layer reads the note text at one site, _do_note_add, '
                         'and this walk found %d' % len(calls))
        for line, call in calls:
            stated = stated_maximum(call)
            self.assertIsNotNone(stated,
                                 '%s:%d calls text() for a note without a maximum, so the note '
                                 'falls back to the 200-character default of text()'
                                 % (OWNER, line))
            self.assertEqual('NOTE_MAX', ast.unparse(stated),
                             '%s:%d must pass NOTE_MAX as the maximum of text()' % (OWNER, line))
        sites = ['%s:%d: %s' % (OWNER, line, code) for line, code in bare_bounds(OPERATIONS, LIMIT)]
        self.assertEqual([], sites,
                         'a site of %s bounds a value with the bare number %d.  Pass NOTE_MAX '
                         'instead, so the two layers cannot disagree:\n%s'
                         % (OWNER, LIMIT, '\n'.join(sites)))


if __name__ == '__main__':
    unittest.main()
