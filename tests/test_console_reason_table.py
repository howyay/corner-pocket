"""Hold the console reason tables to the codes the producer files write.

The console shows two reason tables, and each table has one owner.  ``const REASONS``
holds the gate reasons in ``annotator/vision-stage.js``.  ``const QUAD_REFUSAL_COPY``
holds the geometry refusals in ``annotator/app.js``, because annotator/ops.html loads that
file before the adapter and annotator/app.html loads it alone; the adapter reads the
owner's table through ``window.ConsoleRules.quadReasons``.  The producer writes a code; the
operator screen must answer a sentence for it on both screens.  This module derives the
vocabulary from the producer sources, reads each table out of its owner, and compares the
two directions.  A new producer code therefore fails here until the screen can say it in
words.

The adapter must hold no second copy of an owner row.  A row that both files spell is the
drift this module exists to catch, so one case plants such a copy in the adapter source and
reads the report, and another case plants an owner source that lost one row.

Every rule below is written against the syntax of one producer file comment by comment,
and the rule name and the line that carries the code travel into the failure text.  A
reason that is already a sentence from the scan needs no row: the render keeps such a
value as it is, and the case here says so.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / 'annotator' / 'vision-stage.js'
OWNER = ROOT / 'annotator' / 'app.js'
GATE_PRODUCERS = (
    ROOT / 'src' / 'event_gates.py',
    ROOT / 'src' / 'dense_queue.py',
    ROOT / 'src' / 'shot_pot_gate.py',
)
REFINE_PRODUCER = ROOT / 'src' / 'table_refine.py'

CODE = re.compile(r'^[a-z][a-z0-9_]*$')
SENTENCE = re.compile(r'\s')
ROW = re.compile(r"(?:\[([A-Za-z_][A-Za-z0-9_]*)\]|([A-Za-z_][A-Za-z0-9_]*))\s*:\s*\[([^\]]*)\]")
LABEL = re.compile(r"'(?:\\.|[^'\\])*'")
CONSTANT = re.compile(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'([^']*)'")

# Rows of ``const REASONS`` that no rule below can derive.  The value is the reason the
# row stays.  The comparison case asserts that this set equals the measured set, so a
# new entry needs a comment here and a row that loses its producer must leave the set.
ROWS_WITHOUT_A_PRODUCER = {
    # ``identity_swap_suspected`` and ``parked_in_jaws_possible`` are boolean fields of
    # PotEvent (src/shot_pot_gate.py:976, :968).  The gate copies them into a Rejection's
    # ``numbers`` block (src/shot_pot_gate.py:1490) and into the event (src/shot_pot_gate.py
    # :1490), and the dense queue copies them into its own ``numbers`` block
    # (src/dense_queue.py:295-296).  Neither is ever an element of a ``reasons`` list, so
    # no rule here can reach it.  The rows stay: the screen prints these notes in words.
    'identity_swap_suspected': 'a pot-event flag, never a member of a reasons list',
    'parked_in_jaws_possible': 'a pot-event flag, never a member of a reasons list',
    # The trigger is gone (src/event_gates.py:67 records that; tests/test_event_gates.py:190
    # asserts the code absent), but documents already written to out/ carry it and the
    # screen renders those documents.  A console row never rewrites a producer, and it
    # never drops a row that an old document still needs.
    'calibration_weak_at_time': 'a legacy code that old documents in out/ still carry',
}

# The quad table has one row that no rule below can derive: the composed row that answers a
# code that no rule of src/table_refine.py writes.  Its two strings carry the slot ``${code}``
# and each screen fills that slot with its own reading of the code.  The comparison case
# asserts that this set equals the measured set.
ROWS_WITHOUT_A_PRODUCER_QUAD = {
    'default': 'the composed row that answers a code no rule derives',
}


def console_table(word, source=None, path=CONSOLE):
    """Return the reason table that starts at `word` in the module at `path`."""
    text = path.read_text(encoding='utf-8') if source is None else source
    head = text.find(word)
    if head < 0:
        raise AssertionError(f'{word!r} is not in {path}')
    start = text.find('{', head)
    if start < 0:
        raise AssertionError(f'{word!r} in {path} has no table body')
    depth, end = 1, start + 1
    while end < len(text) and depth > 0:
        depth += {'{': 1, '}': -1}.get(text[end], 0)
        end += 1
    if depth:
        raise AssertionError(f'the table at {word!r} in {path} never closes')
    # A row key may be a computed one ([QUAD_INVALID_GEOMETRY]:, annotator/app.js:1140), so each
    # bracketed name is resolved against the string constants of the same module.
    names = dict(CONSTANT.findall(text))
    rows = {}
    for found in ROW.finditer(text[start + 1:end - 1]):
        key = names.get(found.group(1), found.group(1)) if found.group(1) else found.group(2)
        rows[key] = [ast.literal_eval(label) for label in LABEL.findall(found.group(3))]
    if not rows:
        raise AssertionError(f'the table at {word!r} in {path} holds no row')
    return rows


def console_reasons(source=None):
    """Return the gate reason table of annotator/vision-stage.js."""
    return console_table('const REASONS', source)


def console_quad_reasons(source=None):
    """Return the geometry reason table of its owner, annotator/app.js."""
    return console_table('const QUAD_REFUSAL_COPY', source, OWNER)


def quad_copy_report(text, rows):
    """Return the codes whose row stands again in `text`, so a file holds a second copy.

    A copy shows as the row's own English or Chinese sentence, or as a key spelling for the
    code.  A bare code name is not a copy on its own: a comment may name a code that the
    adapter answers, and the adapter's header comment does.
    """
    found = []
    for code, row in sorted(rows.items()):
        key = re.search(rf"(?:^|[\s,\[])'?{re.escape(code)}'?\s*:", text, re.M)
        if key or row[0] in text or row[1] in text:
            found.append(code)
    return found


def quad_rows_missing(source=None):
    """Return the src/table_refine.py codes that `source` holds no row for."""
    rows = console_quad_reasons(source)
    codes, _ = split_codes(derived_quad_values())
    return sorted(set(codes) - set(rows))


def walk(node, scope=None):
    """Yield (node, name of the enclosing function) for every node under `node`."""
    yield node, scope
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from walk(child, child.name)
        else:
            yield from walk(child, scope)


def call_name(func):
    """Return the plain name of a called function, or None."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def target_names(target):
    """Return the names an assignment target sets.

    A target may be a plain name, an attribute, a subscript with a string key
    (``r["reason"] = ...``) or a tuple or list of those (``ok, why = _plausible(...)``,
    src/table_refine.py:941).
    """
    if isinstance(target, (ast.Tuple, ast.List)):
        names = []
        for element in target.elts:
            names.extend(target_names(element))
        return names
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute):
        return [target.attr]
    if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
        if isinstance(target.slice.value, str):
            return [target.slice.value]
    return []


def names_inside(node):
    """Return every plain name used inside `node`, in source order."""
    return [child.id for child in ast.walk(node) if isinstance(child, ast.Name)]


class Module:
    """One producer file, indexed so that a rule can follow a name to its value."""

    def __init__(self, path):
        self.path = path
        self.tree = ast.parse(path.read_text(encoding='utf-8'))
        self.values = {}
        self.returns = {}
        self._index()

    def _index(self):
        for node, scope in walk(self.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    for name in target_names(target):
                        self.values.setdefault((scope, name), []).append((node.value, scope))
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                for name in target_names(node.target):
                    self.values.setdefault((scope, name), []).append((node.value, scope))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child, child_scope in walk(node, node.name):
                    if child_scope == node.name and isinstance(child, ast.Return):
                        if child.value is not None:
                            self.returns.setdefault(node.name, []).append((child.value, node.name))

    def assignment_values(self, name, scope):
        """Return the values `name` can hold in `scope`, then at module level."""
        found = list(self.values.get((scope, name), []))
        found.extend(self.values.get((None, name), []))
        return found

    def collect(self, node, scope=None, depth=2):
        """Yield (value, line) for every string constant `node` can become.

        A value is followed one step at a time: a name to its assignment, a call to the
        values its own function returns.  A dict, a subscript, an f-string and a composed
        value (``"playfield:" + ...``, src/table_refine.py:1022) hold no code, so they stop
        the walk.
        """
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                yield node.value, node.lineno
            return
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for element in node.elts:
                yield from self.collect(element, scope, depth)
        elif isinstance(node, ast.IfExp):
            yield from self.collect(node.body, scope, depth)
            yield from self.collect(node.orelse, scope, depth)
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                yield from self.collect(value, scope, depth)
        elif isinstance(node, ast.Name) and depth >= 1:
            for value, value_scope in self.assignment_values(node.id, scope):
                yield from self.collect(value, value_scope, depth - 1)
        elif isinstance(node, ast.Call) and depth > 0:
            for value, value_scope in self.returns.get(call_name(node.func), []):
                yield from self.collect(value, value_scope, depth - 1)


def assigned_to(module, names):
    """Yield (value, scope, rule) for every assignment to one of `names`."""
    for (scope, name), entries in module.values.items():
        if name in names:
            for value, value_scope in entries:
                yield value, value_scope, f'assignment to {name!r}'


def appends_to(module, names):
    """Yield (argument, scope, rule) for every append or extend call on one of `names`."""
    for node, scope in walk(module.tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func.value
        if node.func.attr in ('append', 'extend') and isinstance(target, ast.Name):
            if target.id in names and node.args:
                yield node.args[0], scope, f'{target.id}.{node.func.attr}(...)'


def dict_values(module, words):
    """Yield (value, scope, rule) for every value under a `reason` or `reasons` key."""
    for node, scope in walk(module.tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in words:
                    yield value, scope, f'dict value under {key.value!r}'


def gate_result_reasons(call):
    """Return the ``reasons`` argument of a ``GateResult(...)`` call.

    ``GateResult`` is a dataclass and ``reasons`` is its third field (src/event_gates.py
    :122), so the call passes the keyword or the third positional argument
    (src/event_gates.py:411).
    """
    for keyword in call.keywords:
        if keyword.arg == 'reasons':
            return keyword.value
    if len(call.args) > 2:
        return call.args[2]
    return None


def rejection_code(call):
    """Return the code argument of a ``Rejection(...)`` call.

    The code is the keyword ``code`` or the second positional argument, as in every call
    of src/shot_pot_gate.py:1236 to :1568.
    """
    for keyword in call.keywords:
        if keyword.arg == 'code':
            return keyword.value
    if len(call.args) > 1:
        return call.args[1]
    return None


def _collect(found, module, seeds):
    """Add every value of the seed nodes to `found` with its site and its rule."""
    for node, scope, rule in seeds:
        for value, line in module.collect(node, scope):
            found.setdefault(value, []).append((module.path.name, line, rule))


def derived_gate_values():
    """Return {value: [(file, line, rule), ...]} for the three gate producers.

    One rule set per producer, each stated against that file's own syntax:

    * ``src/event_gates.py``: the ``reasons`` argument of every ``GateResult(...)`` call,
      every value assigned to the name ``reasons`` and every argument appended to it.
    * ``src/dense_queue.py``: every value under a ``reasons`` key, and every name inside
      such a value with the assignments and the appends that build it (the ``codes`` list
      of the pot event, src/dense_queue.py:241-250).
    * ``src/shot_pot_gate.py``: the code argument of every ``Rejection(...)`` call, and
      every value assigned to a name or attribute ``reason``/``reasons``, which covers the
      branches of the ternary at src/shot_pot_gate.py:1505-1507.
    """
    found: dict = {}
    for path in GATE_PRODUCERS:
        module = Module(path)
        seeds = []
        if path.name == 'event_gates.py':
            for node, scope in walk(module.tree):
                if isinstance(node, ast.Call) and call_name(node.func) == 'GateResult':
                    argument = gate_result_reasons(node)
                    if argument is not None:
                        seeds.append((argument, scope, 'GateResult reasons argument'))
            seeds.extend(assigned_to(module, ('reasons',)))
            seeds.extend(appends_to(module, ('reasons',)))
        elif path.name == 'dense_queue.py':
            followed = set()
            for value, scope, rule in dict_values(module, ('reasons',)):
                seeds.append((value, scope, rule))
                followed.update(names_inside(value))
            for name in sorted(followed):
                seeds.extend(assigned_to(module, (name,)))
                seeds.extend(appends_to(module, (name,)))
        else:
            for node, scope in walk(module.tree):
                if isinstance(node, ast.Call) and call_name(node.func) == 'Rejection':
                    argument = rejection_code(node)
                    if argument is not None:
                        seeds.append((argument, scope, 'Rejection code argument'))
            seeds.extend(assigned_to(module, ('reason', 'reasons')))
        _collect(found, module, seeds)
    return found


def derived_quad_values():
    """Return {value: [(file, line, rule), ...]} for src/table_refine.py.

    The rules are every value under a ``reason``/``reasons`` key and every value assigned
    to a name, attribute or subscript ``reason``/``reasons``.
    """
    module = Module(REFINE_PRODUCER)
    seeds = list(dict_values(module, ('reason', 'reasons')))
    seeds.extend(assigned_to(module, ('reason', 'reasons')))
    found: dict = {}
    _collect(found, module, seeds)
    return found


def split_codes(values):
    """Split a derived vocabulary into ({code: sites}, [sentence, ...])."""
    codes = {value: sites for value, sites in values.items() if CODE.match(value)}
    sentences = sorted(value for value in values if not CODE.match(value))
    return codes, sentences


def describe(codes, limit=4):
    """Return one line per code, naming the site and the rule that derived it."""
    lines = []
    for code in sorted(codes):
        sites = codes[code]
        shown = ', '.join(f'{name}:{line} ({rule})' for name, line, rule in sites[:limit])
        lines.append(f'  {code}  <- {shown}')
    return '\n'.join(lines) if lines else '  (none)'


NODE_DRIVER = r"""
const fs = require('fs');
const vm = require('vm');
const noop = () => {};
const element = () => ({style: {setProperty: noop}, classList: {add: noop, remove: noop},
  setAttribute: noop, appendChild: noop, addEventListener: noop, textContent: '',
  querySelector: () => null, querySelectorAll: () => []});
globalThis.window = {addEventListener: noop, removeEventListener: noop, localStorage: null,
  matchMedia: () => ({matches: false, addEventListener: noop}), location: {search: '', href: ''}};
globalThis.document = {addEventListener: noop, removeEventListener: noop, readyState: 'complete',
  querySelector: () => null, querySelectorAll: () => [], getElementById: () => null,
  createElement: element, body: element(), head: element(), documentElement: element()};
globalThis.localStorage = {getItem: () => null, setItem: noop, removeItem: noop};
globalThis.location = {href: '', search: '', hash: '', pathname: '/'};
globalThis.history = {replaceState: noop, pushState: noop};
globalThis.navigator = {language: 'en', userAgent: 'node'};
globalThis.requestAnimationFrame = () => 0;
globalThis.cancelAnimationFrame = noop;
globalThis.setInterval = () => 0;
globalThis.clearInterval = noop;
globalThis.setTimeout = () => 0;
globalThis.clearTimeout = noop;
// annotator/ops.html loads the engine first and the adapter second, so this driver loads them in
// that order: the adapter reads the owner's tables from window.ConsoleRules at paint time.
const engineSource = fs.readFileSync(__OWNER_PATH__, 'utf8');
vm.runInThisContext(engineSource, {filename: 'app.js'});
const engine = globalThis.window.CornerPocketReview.attach();
const source = fs.readFileSync(__MODULE_PATH__, 'utf8');
const close = source.lastIndexOf('})();');
if (close < 0) throw new Error('annotator/vision-stage.js has no trailing })(); to open');
const seam = 'globalThis.__reasonSeam = {reasonText: reasonText, quadReason: quadReason,'
  + ' setLang: lang => { opts = Object.assign(opts || {}, {lang}); }};';
vm.runInThisContext(source.slice(0, close) + seam + source.slice(close));
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const answers = {en: {}, zh: {}};
for (const lang of ['en', 'zh']) {
  globalThis.__reasonSeam.setLang(lang);
  engine.setRoot({lang});
  for (const code of request.gate) answers[lang][code] = globalThis.__reasonSeam.reasonText(code);
  for (const code of request.quad) {
    answers[lang]['quad:' + code] = globalThis.__reasonSeam.quadReason(code);
    answers[lang]['owner:' + code] = engine.quadReasonText(code);
  }
}
process.stdout.write(JSON.stringify(answers));
"""


def rendered_reasons(gate, quad):
    """Ask the real console screens how they render each code, in both languages."""
    node = shutil.which('node')
    if not node:
        raise AssertionError('node is required to ask the console screens how they render a reason')
    driver = (NODE_DRIVER.replace('__MODULE_PATH__', json.dumps(str(CONSOLE)))
              .replace('__OWNER_PATH__', json.dumps(str(OWNER))))
    done = subprocess.run([node, '-e', driver], input=json.dumps({'gate': gate, 'quad': quad}),
                          capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise AssertionError(f'node could not load {OWNER} and {CONSOLE}:\n{done.stderr.strip()}')
    return json.loads(done.stdout)


class ConsoleReasonTableTest(unittest.TestCase):
    """Compare the console reason tables with the producer files, both ways."""

    def test_every_derived_gate_value_is_a_code_or_a_sentence(self):
        values = derived_gate_values()
        odd = sorted(value for value in values
                     if not CODE.match(value) and not SENTENCE.search(value))
        self.assertEqual([], odd,
                         'a derived gate reason is neither a code nor a sentence, so a rule '
                         'collected a composed value:\n' + describe({value: values[value] for value in odd}))

    def test_every_derived_gate_code_has_a_row(self):
        rows = console_reasons()
        codes, _ = split_codes(derived_gate_values())
        missing = {code: codes[code] for code in codes if code not in rows}
        self.assertEqual({}, missing,
                         'const REASONS in annotator/vision-stage.js has no row for these gate '
                         'reason codes, so the operator reads the bare code:\n' + describe(missing))

    def test_every_gate_row_has_a_producer_or_a_recorded_reason(self):
        rows = set(console_reasons())
        codes, _ = split_codes(derived_gate_values())
        unexplained = sorted(rows - set(codes) - set(ROWS_WITHOUT_A_PRODUCER))
        self.assertEqual([], unexplained,
                         'this row of const REASONS in annotator/vision-stage.js has no producer in '
                         'src/event_gates.py, src/dense_queue.py or src/shot_pot_gate.py, so either '
                         'the row is stale or a derivation rule stopped collecting its code:\n  '
                         + '\n  '.join(unexplained))
        measured = sorted(rows - set(codes))
        self.assertEqual(sorted(ROWS_WITHOUT_A_PRODUCER), measured,
                         'ROWS_WITHOUT_A_PRODUCER no longer matches the rows without a producer; '
                         'update the set and its comment for each row:\n'
                         f'  rows without a producer: {measured}\n'
                         f'  pinned: {sorted(ROWS_WITHOUT_A_PRODUCER)}')

    def test_every_derived_quad_code_has_a_row_and_every_quad_row_has_a_producer(self):
        rows = set(console_quad_reasons())
        codes, _ = split_codes(derived_quad_values())
        missing = {code: codes[code] for code in codes if code not in rows}
        self.assertEqual({}, missing,
                         'const QUAD_REFUSAL_COPY in annotator/app.js has no row for these codes '
                         'of src/table_refine.py, so both screens read the bare code:\n' + describe(missing))
        unexplained = sorted(rows - set(codes) - set(ROWS_WITHOUT_A_PRODUCER_QUAD))
        self.assertEqual([], unexplained,
                         'this row of const QUAD_REFUSAL_COPY in annotator/app.js has no producer '
                         'in src/table_refine.py:\n  ' + '\n  '.join(unexplained))
        measured = sorted(rows - set(codes))
        self.assertEqual(sorted(ROWS_WITHOUT_A_PRODUCER_QUAD), measured,
                         'ROWS_WITHOUT_A_PRODUCER_QUAD no longer matches the rows without a producer; '
                         'update the set and its comment for each row:\n'
                         f'  rows without a producer: {measured}\n'
                         f'  pinned: {sorted(ROWS_WITHOUT_A_PRODUCER_QUAD)}')

    def test_every_row_of_both_tables_is_two_non_empty_strings(self):
        for name, rows in (('REASONS', console_reasons()),
                           ('QUAD_REFUSAL_COPY', console_quad_reasons())):
            for code, row in sorted(rows.items()):
                with self.subTest(table=name, code=code):
                    self.assertEqual(2, len(row), f'{name}[{code}] is not a pair of strings: {row!r}')
                    self.assertTrue(row[0].strip() and row[1].strip(),
                                    f'{name}[{code}] holds an empty string: {row!r}')
                    self.assertNotEqual(code, row[0], f'{name}[{code}] repeats the code as its English words')
                    self.assertNotEqual(code, row[1], f'{name}[{code}] repeats the code as its Chinese words')

    def test_both_screens_answer_a_sentence_for_every_row_and_code(self):
        rows, quad = console_reasons(), console_quad_reasons()
        codes, sentences = split_codes(derived_gate_values())
        quad_codes, _ = split_codes(derived_quad_values())
        gate_asked = sorted(set(rows) | set(codes) | set(sentences))
        quad_asked = sorted(set(quad) | set(quad_codes))
        answers = rendered_reasons(gate_asked, quad_asked)

        def want(row, code, index):
            """The row the screen must show: a row may carry the ``${code}`` slot."""
            return row[index].replace('${code}', code.replace('_', ' '))

        for lang in ('en', 'zh'):
            index = 0 if lang == 'en' else 1
            for code, row in sorted(rows.items()):
                with self.subTest(lang=lang, code=code):
                    self.assertEqual(want(row, code, index), answers[lang][code],
                                     f'reasonText({code!r}) in {lang} does not answer the row of '
                                     'const REASONS, so the operator reads something else')
            for code in sorted(codes):
                if code in rows:
                    continue
                with self.subTest(lang=lang, code=code):
                    self.assertNotEqual(code, answers[lang][code],
                                        f'reasonText({code!r}) in {lang} returns the bare code, and '
                                        'const REASONS has no row for it')
            # Both screens answer the same sentence for every row of the owner's table and for
            # every code the producer writes: the engine reads its own copy, the adapter reads
            # the same row through window.ConsoleRules.quadReasons.
            for code, row in sorted(quad.items()):
                for screen in ('quad:', 'owner:'):
                    with self.subTest(lang=lang, code=screen + code):
                        self.assertEqual(want(row, code, index), answers[lang][screen + code],
                                         f'{screen}{code!r} in {lang} does not answer the row of '
                                         'const QUAD_REFUSAL_COPY in annotator/app.js, so the two '
                                         'screens show different words')
            for code in sorted(quad_codes):
                if code in quad:
                    continue
                for screen in ('quad:', 'owner:'):
                    with self.subTest(lang=lang, code=screen + code):
                        self.assertNotEqual(code, answers[lang][screen + code],
                                            f'{screen}{code!r} in {lang} returns the bare code, and '
                                            'the owner holds no row for it')
        for sentence in sentences:
            with self.subTest(lang='en', code=sentence):
                self.assertEqual(sentence, answers['en'][sentence],
                                 'a reason that is already a sentence from the scan must render as '
                                 'it is in English; it needs no row')

    def test_the_adapter_holds_no_second_copy_of_an_owner_row(self):
        rows = console_quad_reasons()
        text = CONSOLE.read_text(encoding='utf-8')
        self.assertEqual([], quad_copy_report(text, rows),
                         'annotator/vision-stage.js holds a second copy of a row of '
                         'const QUAD_REFUSAL_COPY, the table that annotator/app.js owns; the '
                         'adapter must read the owner through window.ConsoleRules.quadReasons')
        # The report reads a copy: this row stands in the adapter source and nowhere else.
        row = rows['low_cloth_area']
        planted = text.replace(
            'function quadReason(code) {',
            'const QUAD_REASON = {\n  low_cloth_area: [%r, %r]\n};\nfunction quadReason(code) {'
            % (row[0], row[1]))
        self.assertNotEqual(text, planted, 'the plant changed no byte of the adapter source')
        self.assertEqual(['low_cloth_area'], quad_copy_report(planted, rows),
                         'the report did not name the planted copy, so it reads nothing')

    def test_a_derived_reason_with_no_row_in_the_owner_is_reported(self):
        text = OWNER.read_text(encoding='utf-8')
        self.assertEqual([], quad_rows_missing(text),
                         'annotator/app.js holds no sentence for these codes of src/table_refine.py:\n'
                         + '\n'.join(f'  {code}' for code in quad_rows_missing(text)))
        # The check reads a missing row: 'degenerate_prior' loses its only sentence.
        planted, count = re.subn(r'  degenerate_prior: \[[\s\S]*?\],\n', '', text, count=1)
        self.assertEqual(1, count, 'the plant did not remove the row from the owner source')
        self.assertEqual(['degenerate_prior'], quad_rows_missing(planted),
                         'the check did not name the row that the planted owner source lost')
