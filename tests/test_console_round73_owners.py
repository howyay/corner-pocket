"""Round 73: one home for the byte count an operator reads, and one for the default detector set.

Two rules of this checkout stood at more sites than they had owners, and no case named the extra
sites.

* **The byte count an operator reads.**  One display rule - ``N.N GB`` at 1 GB and up, ``N MB``
  below - stood at four sites: ``annotator/refusals.py`` (``gb``),
  ``annotator/vod_import.py`` (``size_text``), ``annotator/ops.js`` (``sizeText``) and
  ``annotator/vision-stage.js`` (``sizeText``).  The MB branch answered two ways: the python
  side wrote one decimal (``12.3 MB``) and both console copies wrote none (``12 MB``).  The GB
  branch answered two ways at an exact tie too: 1_250_000_000 bytes read ``1.2 GB`` in python
  and ``1.3 GB`` in the console, because ``:.1f`` rounds a tie to the even digit and
  ``Number.toFixed`` rounds it up.  The console answer wins: the operator reads the estimate
  line beside Start (``annotator/ops.js:664``) and the broadcast panel
  (``annotator/vision-stage.js:1029``, ``:1033``), and the console states the rule at two sites
  against one.
  ``annotator/refusals.py`` owns both branches now: ``rounded`` (:333) rounds a tie up, ``gb``
  (:346) and ``size_text`` (:351) spell the two branches.  The console realm states the same
  rule once, on ``window.ConsoleRules.sizeText`` in ``annotator/app.js:26``, because a static
  file cannot import a python name; the two adapters read that name late
  (``annotator/ops.js:132``, ``annotator/vision-stage.js:955``), and ``annotator/vod_import.py``
  imports ``size_text`` for its import sentence (:572).
* **The default live-detector set.**  The pair ``('table', 'person')`` stood at four sites: the
  two service doors (``annotator/live_processing.py:373``, ``annotator/unified_server.py:2047``)
  and the two console sites (``annotator/ops.js:766``, ``annotator/app.js:64``).  The console
  copy was held by one case (``tests/test_ops.js:264``); the two service copies were held by
  none.  ``annotator/pipeline_stages.py:751`` owns the set now, in ``DEFAULT_DETECTORS``, beside
  the ``DETECTORS`` tuple that owns the names.  The console realm states its own set once, in
  ``DEFAULT_LIVE_DETECTORS`` (``annotator/app.js:30``), published as
  ``window.ConsoleRules.liveDetectors``.  ``annotator/vision-stage.js:1077`` draws a three-name
  vocabulary row, ``['table','person','ball']``.  That row is the vocabulary of the panel, not
  the default set, and this module does not read it as a copy.

What this module reads, and what it does not
--------------------------------------------
* It reads the source text of eight files of this checkout, with one regex per rule line.  A
  rule that a file builds at run time, or a second panel, is invisible to it.
* It reads no rendered console.  The two ``node`` cases load the real ``annotator/app.js`` and
  ask that owner for its answers.  The rendered panel is driven in
  ``tests/test_app_timeline.js``, and the rendered adapters in ``tests/test_ops.js``.
* It does not read the job view of ``annotator/vod_import.py``.  ``view['mb']``
  (``annotator/vod_import.py:432``) is one number with one home, and the console prints the
  number it receives (``annotator/vision-stage.js:1021``).  No second copy of that rule stands.
* It does not re-measure the disk sentence.  ``tests/test_vod_import.py:262`` and ``:443`` hold
  the sentence, and ``tests/test_job_refusal_identity.py:390`` holds ``gb``.  This module holds
  the boundary table of both branches, and every measured value of those modules stays.
* ``node`` is required.  A case that cannot reach the console home fails; it never skips.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from annotator import pipeline_stages, refusals  # noqa: E402

ANNOTATOR = ROOT / 'annotator'
REFUSALS = ANNOTATOR / 'refusals.py'
VOD_IMPORT = ANNOTATOR / 'vod_import.py'
PIPELINE_STAGES = ANNOTATOR / 'pipeline_stages.py'
LIVE_PROCESSING = ANNOTATOR / 'live_processing.py'
UNIFIED_SERVER = ANNOTATOR / 'unified_server.py'
APP_JS = ANNOTATOR / 'app.js'
OPS_JS = ANNOTATOR / 'ops.js'
VISION_STAGE_JS = ANNOTATOR / 'vision-stage.js'
SOURCES = (REFUSALS, VOD_IMPORT, PIPELINE_STAGES, LIVE_PROCESSING, UNIFIED_SERVER,
           APP_JS, OPS_JS, VISION_STAGE_JS)

# One line of the byte rule: a division by 1e6 or 1e9 that writes a MB or a GB label on the
# same line.  Both realms write the rule of a branch on one line, so a line is a site.
BYTE_RULE = re.compile(r"1e[69][^\n]*(?:MB|GB)")
# One line of the default detector set, in the spelling of each realm.
PAIR_JS = re.compile(r"\[\s*'table'\s*,\s*'person'\s*\]")
PAIR_PY = re.compile(r"\(\s*'table'\s*,\s*'person'\s*\)")
# The two adapter reads, and the two service reads, of the two owners.
CONSOLE_BYTE_READ = re.compile(r"window\.ConsoleRules\.sizeText")
CONSOLE_DETECTOR_READ = re.compile(r"window\.ConsoleRules\.liveDetectors")
PY_DETECTOR_READ = re.compile(r"\bDEFAULT_DETECTORS\b")
PY_SIZE_IMPORT = re.compile(r"from annotator\.refusals import \([^)]*\bsize_text\b", re.S)
# The line that the python home must not hold twice.
LOCAL_SIZE_TEXT = re.compile(r"^def size_text\(", re.M)

#: The files that state the byte rule, and the number of rule lines each states.  The python
#: realm states two lines in one home (the GB branch and the MB branch); the console realm
#: states one line that carries both branches.  Any other site is a copy.
BYTE_HOMES = {'annotator/refusals.py': 2, 'annotator/app.js': 1}
#: The files that state the default detector set, and the number of lines each states.
DETECTOR_HOMES = {'annotator/pipeline_stages.py': 1, 'annotator/app.js': 1}
# The two adapter lines that a planted copy replaces.  The cases fail when one of them moves,
# so a plant stays a plant and never rewrites a file.
ADAPTER_BYTE_READ = 'const sizeText=v=>window.ConsoleRules.sizeText(v);'
ADAPTER_DETECTOR_READ = ('if(!liveDetectors)liveDetectors=[...window.ConsoleRules.liveDetectors];'
                         'return liveDetectors;')

#: The boundary table: every boundary of the two branches, both tie families, and the accepted
#: values of the two modules that measured this rule before round 73 (8.6 GB and 52.2 GB of
#: ``tests/test_job_refusal_identity.py:390``, and the disk numbers of
#: ``tests/test_vod_import.py:262``).  2_050_000_000 is the count that caught a first repair
#: attempt: the double of ``2_050_000_000 / 1e9`` sits *below* the tie 2.05, so the console
#: answers ``2.0 GB`` and a float tie test answered ``2.1 GB``.
BOUNDARY_COUNTS = (0, 1, 999, 1_000, 999_999, 1_000_000, 1_500_000, 2_500_000, 12_345_678,
                   999_999_999, 1_000_000_000, 1_000_000_001, 1_250_000_000, 1_500_000_000,
                   2_050_000_000, 8_606_363_471, 52_196_323_328, 999_050_000_000)
#: The measured answer of each count.  The python realm and the console realm must both read
#: this table: the last case compares the python answers with the answers of the real
#: ``annotator/app.js``.
BOUNDARY_ANSWERS = {
    0: '0 MB', 1: '0 MB', 999: '0 MB', 1_000: '0 MB', 999_999: '1 MB', 1_000_000: '1 MB',
    1_500_000: '2 MB', 2_500_000: '3 MB', 12_345_678: '12 MB', 999_999_999: '1000 MB',
    1_000_000_000: '1.0 GB', 1_000_000_001: '1.0 GB', 1_250_000_000: '1.3 GB',
    1_500_000_000: '1.5 GB', 2_050_000_000: '2.0 GB', 8_606_363_471: '8.6 GB',
    52_196_323_328: '52.2 GB', 999_050_000_000: '999.0 GB',
}


def texts_of(paths=SOURCES):
    """Return the source text of each file, keyed by its path under the repository root."""
    return {str(path.relative_to(ROOT)): path.read_text(encoding='utf-8') for path in paths}


def rule_sites(pattern, texts):
    """Return one site per line of each text that carries the pattern: (file, line, text)."""
    sites = []
    for name in sorted(texts):
        for number, line in enumerate(texts[name].splitlines(), start=1):
            if pattern.search(line):
                sites.append((name, number, line.strip()))
    return sites


def site_counts(sites):
    """Return the number of sites per file."""
    counts = {}
    for name, _, _ in sites:
        counts[name] = counts.get(name, 0) + 1
    return counts


def describe(sites):
    """Return one line per site, naming the file, the line number and the rule line."""
    lines = [f'  {name}:{number}  {line}' for name, number, line in sites]
    return '\n'.join(lines) if lines else '  (none)'


def byte_rule_sites(texts=None):
    """Return every line of the eight sources that states a branch of the byte rule."""
    return rule_sites(BYTE_RULE, texts_of() if texts is None else texts)


def detector_set_sites(texts=None):
    """Return every line of the eight sources that states the default detector pair."""
    texts = texts_of() if texts is None else texts
    return rule_sites(PAIR_JS, texts) + rule_sites(PAIR_PY, texts)


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
// annotator/ops.html loads this file before the two adapters, so the driver loads it alone and
// reads the owner's rules from window.ConsoleRules.
vm.runInThisContext(fs.readFileSync(__OWNER_PATH__, 'utf8'), {filename: 'app.js'});
const rules = globalThis.window.ConsoleRules;
if (!rules || typeof rules.sizeText !== 'function')
  throw new Error('annotator/app.js published no ConsoleRules.sizeText');
if (!rules.liveDetectors) throw new Error('annotator/app.js published no ConsoleRules.liveDetectors');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify({
  sizes: request.counts.map(count => rules.sizeText(count)),
  detectors: Array.from(rules.liveDetectors),
  keys: Object.keys(rules),
}));
"""


def console_answers(counts):
    """Ask the owner of the console rules for its size answers and its default detector set."""
    node = shutil.which('node')
    if not node:
        raise AssertionError('node is required to read window.ConsoleRules of annotator/app.js')
    driver = NODE_DRIVER.replace('__OWNER_PATH__', json.dumps(str(APP_JS)))
    done = subprocess.run([node, '-e', driver], input=json.dumps({'counts': list(counts)}),
                          capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise AssertionError(f'node could not load {APP_JS}:\n{done.stderr.strip()}')
    return json.loads(done.stdout)


class ByteCountOwnersTest(unittest.TestCase):
    """Hold the byte rule to one home per realm, and the two homes to one answer."""

    def test_the_byte_rule_has_one_home_in_each_realm(self):
        sites = byte_rule_sites()
        self.assertEqual(BYTE_HOMES, site_counts(sites),
                         'the byte rule must stand at one home per realm and nowhere else.  '
                         'annotator/refusals.py owns the python rule, annotator/app.js owns the '
                         'console rule, and every other site reads one of the two:\n'
                         + describe(sites))

    def test_every_other_byte_site_reads_a_home(self):
        texts = texts_of()
        for path in (OPS_JS, VISION_STAGE_JS):
            name = str(path.relative_to(ROOT))
            self.assertRegex(texts[name], CONSOLE_BYTE_READ,
                             f'{name} must read the console home window.ConsoleRules.sizeText '
                             'instead of stating the rule again')
        self.assertRegex(texts[str(VOD_IMPORT.relative_to(ROOT))], PY_SIZE_IMPORT,
                         'annotator/vod_import.py must import size_text from annotator.refusals, '
                         'because a local copy of the rule is the drift this module catches')
        self.assertNotRegex(texts[str(VOD_IMPORT.relative_to(ROOT))], LOCAL_SIZE_TEXT,
                            'annotator/vod_import.py must hold no second def size_text')

    def test_a_second_byte_rule_is_reported(self):
        planted = dict(texts_of())
        planted['annotator/ops.js'] = planted['annotator/ops.js'].replace(
            ADAPTER_BYTE_READ,
            'const sizeText=bytes=>Number(bytes)>=1e9?`${(Number(bytes)/1e9).toFixed(1)} GB`'
            ':`${Math.round(Number(bytes)/1e6)} MB`;')
        planted['annotator/vod_import.py'] = planted['annotator/vod_import.py'] + (
            '\n\ndef size_text(count):\n'
            '    return gb(count) if count >= 1e9 else f"{count / 1e6:.1f} MB"\n')
        sites = byte_rule_sites(planted)
        self.assertEqual({'annotator/refusals.py': 2, 'annotator/app.js': 1,
                          'annotator/ops.js': 1, 'annotator/vod_import.py': 1},
                         site_counts(sites),
                         'the walk must report a second console rule and a second python rule:\n'
                         + describe(sites))

    def test_a_byte_home_that_lost_its_rule_is_reported(self):
        planted = dict(texts_of())
        for name in ('annotator/refusals.py', 'annotator/app.js'):
            kept = [line for line in planted[name].splitlines() if not BYTE_RULE.search(line)]
            planted[name] = '\n'.join(kept)
        sites = byte_rule_sites(planted)
        self.assertEqual({}, site_counts(sites),
                         'a home that lost its rule must leave the walk empty, so the first case '
                         'cannot pass with a moved home:\n' + describe(sites))

    def test_the_python_rule_answers_the_boundary_table(self):
        measured = {count: refusals.size_text(count) for count in BOUNDARY_COUNTS}
        self.assertEqual(BOUNDARY_ANSWERS, measured,
                         'annotator.refusals.size_text must answer the measured boundary table; '
                         'a moved rounding or a moved branch fails here')

    def test_the_console_rule_answers_the_boundary_table(self):
        answers = console_answers(BOUNDARY_COUNTS)
        expected = [BOUNDARY_ANSWERS[count] for count in BOUNDARY_COUNTS]
        self.assertEqual(expected, answers['sizes'],
                         'window.ConsoleRules.sizeText of annotator/app.js must answer the '
                         'measured boundary table')

    def test_the_two_realms_answer_one_table_of_counts(self):
        answers = console_answers(BOUNDARY_COUNTS)
        rows = [(count, refusals.size_text(count), console)
                for count, console in zip(BOUNDARY_COUNTS, answers['sizes'])]
        disagreements = [row for row in rows if row[1] != row[2]]
        self.assertEqual([], disagreements,
                         'the python home (annotator/refusals.py:351) and the console home '
                         '(annotator/app.js:26) must answer one text for every count.  A row '
                         'here is (count, python, console):\n  '
                         + '\n  '.join(f'{count}: python {python!r} vs console {console!r}'
                                       for count, python, console in disagreements))
        self.assertEqual(['sizeText', 'liveDetectors'],
                         [key for key in ('sizeText', 'liveDetectors') if key in answers['keys']],
                         'annotator/app.js must publish both rules on window.ConsoleRules')


class DefaultDetectorSetTest(unittest.TestCase):
    """Hold the default detector set to one home per realm, and the two homes to one set."""

    def test_the_default_set_has_one_home_in_each_realm(self):
        sites = detector_set_sites()
        self.assertEqual(DETECTOR_HOMES, site_counts(sites),
                         'the default detector set must stand at one home per realm and nowhere '
                         'else.  annotator/pipeline_stages.py owns the service set, '
                         'annotator/app.js owns the console set, and every other site reads one '
                         'of the two:\n' + describe(sites))

    def test_every_other_detector_site_reads_a_home(self):
        texts = texts_of()
        for path in (LIVE_PROCESSING, UNIFIED_SERVER):
            name = str(path.relative_to(ROOT))
            self.assertRegex(texts[name], PY_DETECTOR_READ,
                             f'{name} must read annotator.pipeline_stages.DEFAULT_DETECTORS')
        self.assertRegex(texts[str(OPS_JS.relative_to(ROOT))], CONSOLE_DETECTOR_READ,
                         'annotator/ops.js must read window.ConsoleRules.liveDetectors')
        self.assertIn("['table','person','ball']", texts[str(VISION_STAGE_JS.relative_to(ROOT))],
                      'annotator/vision-stage.js draws the three-name vocabulary row of the live '
                      'panel; this module reads that row as a vocabulary, not as the default set')

    def test_a_second_default_set_is_reported(self):
        planted = dict(texts_of())
        planted['annotator/live_processing.py'] = planted['annotator/live_processing.py'] + (
            "\n        detectors = ['table', 'person'] if detectors is None else detectors\n")
        planted['annotator/ops.js'] = planted['annotator/ops.js'].replace(
            ADAPTER_DETECTOR_READ, "const liveDefaults=['table', 'person'];")
        sites = detector_set_sites(planted)
        self.assertEqual({'annotator/pipeline_stages.py': 1, 'annotator/app.js': 1,
                          'annotator/live_processing.py': 1, 'annotator/ops.js': 1},
                         site_counts(sites),
                         'the walk must report a second service set and a second console set:\n'
                         + describe(sites))

    def test_a_detector_home_that_lost_the_set_is_reported(self):
        planted = dict(texts_of())
        for name in ('annotator/pipeline_stages.py', 'annotator/app.js'):
            kept = [line for line in planted[name].splitlines()
                    if not PAIR_JS.search(line) and not PAIR_PY.search(line)]
            planted[name] = '\n'.join(kept)
        sites = detector_set_sites(planted)
        self.assertEqual({}, site_counts(sites),
                         'a home that lost the set must leave the walk empty, so the first case '
                         'cannot pass with a moved home:\n' + describe(sites))

    def test_the_two_realms_state_one_default_detector_set(self):
        self.assertEqual(('table', 'person'), tuple(pipeline_stages.DEFAULT_DETECTORS),
                         'annotator/pipeline_stages.DEFAULT_DETECTORS owns the service set')
        answers = console_answers([0])
        self.assertEqual(list(pipeline_stages.DEFAULT_DETECTORS), answers['detectors'],
                         'window.ConsoleRules.liveDetectors of annotator/app.js and '
                         'annotator.pipeline_stages.DEFAULT_DETECTORS must state one set')
        self.assertEqual(['table', 'person'], answers['detectors'],
                         'the two realms state the set in this order, and the live status of the '
                         'panel reads it in that order')


if __name__ == '__main__':
    unittest.main()
