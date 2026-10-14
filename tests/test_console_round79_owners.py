"""Round 79: one sentence, one home to spell it in, and one word per label.

Three rows landed in this round, and this module holds the guard for each one.

Strong 1, the stage-empty sentence.  The sentence stood twice in the tree: annotator/app.js:854 held
the page's copy and annotator/vision-stage.js:138 held a second copy in the adapter's own table, whose
English had drifted ('on the scrub strip' against 'on the strip').  The decision is that
annotator/app.js owns the sentence, in the 'stageEmpty' row of SHARED_WORDS (annotator/app.js:2192);
the constant reads that row, both paint sites (annotator/app.js:861 and annotator/app.js:900) call the
constant, and no other file spells the sentence.  The drifted spelling is the case the sentence rule
makes red, so a second copy cannot come back quietly.

Strong 2, the words table of annotator/ops.js.  One table answered 'Event name' twice, once as
赛事名称 (annotator/ops.js:14) and once as 赛事名 (annotator/ops.js:51), and answered 'Remove' twice,
once as 移除 (annotator/ops.js:14) and once as 删除 (annotator/ops.js:67).  The wording is not the
label's to invent: docs/console-redesign.md:247 renders the start-night form with 赛事名 and its table
records the bfNightName row as 赛事名, while 删除 is this console's Delete word (deletePlayer,
deleteEvent, faceForget) and its Remove word is 移除.  The decision is therefore that both 'Event name'
rows read 赛事名, both 'Remove' rows read 移除, and no row whose English is 'Remove' reads 删除.

Worth 4, the review-workspace sentence.  'Loading the review workspace…' stood in three files: the ops
words table (annotator/ops.js, row 'visionLoading') and both of the adapter's tables
(annotator/vision-stage.js).  The decision is Strong 1's decision again: the row lives in SHARED_WORDS
(annotator/app.js:2193), and the two screens read it.  The ops console reads it through sharedWord()
and say() at annotator/ops.js:893 and annotator/ops.js:1249; the adapter reads it through say() at
annotator/vision-stage.js:1783.  The ops console keeps t() on its own table, because several slot
names stand in both tables with different words: this console's 'live' row reads 'On table' while
SHARED_WORDS answers 'live', so an owner-first t() would repaint the match status badge.

What this module reads, and what it does not:

* It reads the text of annotator/app.js, annotator/ops.js and annotator/vision-stage.js.  It never
  writes a source file: a planted copy lives in a dict in this process and dies with it.
* It runs node to read the owner table and the two rendered screens.  The one-owner rule is a rule
  about what the shipped code does, so the strong case plants a sentinel row into
  window.ConsoleRules.words and asks the adapter's shell and the console's vision surface for it.  A
  reader that stopped asking the owner fails there, even while its own text still reads well.
* It does not read docs/console-redesign.md.  The mockup owns the wording, and this module checks the
  copy where the two screens paint it.
* It does not check every word of the two tables, and it does not judge wording.  A third English word
  with two Chinese spellings stands in the ops table today ('Tables' reads both 球台 and 球台数量); the
  row is not one of this round's labels, so it stays, and the label case records it as the known
  residue rather than hiding it.
* ``node`` is required.  A case that cannot reach the owner table fails; it never skips.
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

ANNOTATOR = ROOT / 'annotator'
APP_JS = ANNOTATOR / 'app.js'
OPS_JS = ANNOTATOR / 'ops.js'
VISION_JS = ANNOTATOR / 'vision-stage.js'

APP = 'annotator/app.js'
OPS = 'annotator/ops.js'
VISION = 'annotator/vision-stage.js'
SOURCES = (APP, OPS, VISION)
PATHS = {APP: APP_JS, OPS: OPS_JS, VISION: VISION_JS}

# The two sentences this round gives one owner, in both languages, and the drifted English word the
# adapter carried before the round.
STAGE_SENTENCE = 'Pick a moment on the scrub strip, or select a cue, then freeze it here.'
STAGE_SENTENCE_ZH = '在拖动条上选择时刻，或选择一条线索，然后在此冻结。'
STAGE_SENTENCE_DRIFT = 'Pick a moment on the strip, or select a cue, then freeze it here.'
LOADING_SENTENCE = 'Loading the review workspace…'
LOADING_SENTENCE_ZH = '正在加载复核工作区…'

# The stage sentence, either language and either spelling: one home, the SHARED_WORDS row below.
STAGE_SENTENCE_RULE = re.compile(
    r"Pick a moment on the (?:scrub )?strip, or select a cue, then freeze it here\."
    r"|在拖动条上选择时刻，或选择一条线索，然后在此冻结。"
)
LOADING_SENTENCE_RULE = re.compile(r"Loading the review workspace…|正在加载复核工作区…")
# A table row that answers a slot.  The colon is what makes a row: a reader that asks the row by name
# writes sharedWord('visionLoading') or SHARED_WORDS.stageEmpty[0] and holds no colon.
SLOT_ROW_RULE = re.compile(r"\b(?:stageEmpty|visionLoading)\s*:")

# The page reads its own owner row through this constant, and both paint sites call the constant.
STAGE_READER_RULE = re.compile(r"STAGE_EMPTY_COPY\s*=\s*\(\)\s*=>\s*SHARED_WORDS\.stageEmpty\[0\]")
STAGE_PAINT_RULE = re.compile(r"text\(STAGE_EMPTY_COPY\(\)\)")
# The adapter's late read of the owner table, and the reader its paint sites go through.
ADAPTER_BRIDGE_RULE = re.compile(
    r"const sharedWord = \(key, lang\) => \{\s*const row = window\.ConsoleRules\.words\[key\];"
)
ADAPTER_SAY_RULE = re.compile(r"const say = key => sharedWord\(key, options\.lang\) \|\|")
# The ops console's late read and its reader, plus the local reader of its vision surface.
OPS_BRIDGE_RULE = re.compile(r"sharedWord=k=>window\.ConsoleRules\.words\[k\]")
OPS_SAY_RULE = re.compile(r"say=k=>sharedWord\(k\)\|\|t\(k\)")
OPS_LOCAL_RULE = re.compile(r"const L=k=>esc\(say\(k\)\)")
# Every site that paints the loading sentence asks the owner for it: say() in both files, and the
# console's vision surface through its local L().
LOADING_READER_RULE = re.compile(r"(?:say|L)\('visionLoading'\)")

# One row of an ops words table: slot, English, Chinese.  The rows stand several to a line.
OPS_LABEL_ROW_RULE = re.compile(r"\b(remove|bfUnmark|event|bfNightName):\['([^']*)','([^']*)'\]")
#: The English words whose rows must agree, and the Chinese word each row of them answers with.
LABEL_AGREEMENT = {'Remove': '移除', 'Event name': '赛事名'}
#: The words a row of the Remove label must not answer with: 删除 is this console's Delete word.
LABEL_REFUSAL = {'Remove': '删除'}
#: The known residue of the agreement rule.  'Tables' reads both 球台 and 球台数量 in the live table,
#: and the row is not one of this round's labels.  The label case fails on any other split word.
KNOWN_SPLIT_WORDS = {'Tables': ['球台', '球台数量']}

#: The lines that spell each sentence, per file.  A second copy moves one of these counts.
STAGE_SENTENCE_HOMES = {APP: 1}
LOADING_SENTENCE_HOMES = {APP: 1}
#: The rows that answer the two slots.  Both stand in the owner table of annotator/app.js, one line
#: each, and no other file holds a row for either slot.
SLOT_ROW_HOMES = {APP: 2}
#: The bridges that reach the owner table, one site per rule per file.
OWNER_BRIDGES = (
    (STAGE_READER_RULE, {APP: 1}),
    (ADAPTER_BRIDGE_RULE, {VISION: 1}),
    (ADAPTER_SAY_RULE, {VISION: 1}),
    (OPS_BRIDGE_RULE, {OPS: 1}),
    (OPS_SAY_RULE, {OPS: 1}),
    (OPS_LOCAL_RULE, {OPS: 1}),
)
#: The sites that paint the loading sentence.  Every one of them reads the owner row.
LOADING_READERS = {OPS: 2, VISION: 1}

# The in-memory anchors a plant replaces.  Each one stands once in its file, and every plant case
# asserts that the plant landed, so a plant that misses its anchor fails instead of passing quietly.
NO_CROP_EN = "noCropHere:'no crop at this frame',"
APP_STAGE_READER = 'const STAGE_EMPTY_COPY = () => SHARED_WORDS.stageEmpty[0];'
ADAPTER_SAY = 'const say = key => sharedWord(key, options.lang) || '
OPS_SAY_CHAIN = (
    "sharedWord=k=>window.ConsoleRules.words[k]?.[lang==='zh'?1:0]??null, say=k=>sharedWord(k)||t(k)"
)
OPS_VISION_CUES = "visionCues:['Vision cues','视觉线索']"
OPS_EVENT_ROW = "event:['Event name','赛事名']"
OPS_UNMARK_ROW = "bfUnmark:['Remove','移除']"

# A planted row is the shape a second copy takes in the adapter's table.
PLANTED_ADAPTER_ROW = (
    "    stageEmpty:'Pick a moment on the strip, or select a cue, then freeze it here.',\n"
)
PLANTED_OPS_ROW = "visionLoading:['Loading the review workspace…','正在加载复核工作区…'],"


def texts_of(paths=SOURCES):
    """The source text of each path, keyed by its repository-relative name."""
    return {name: PATHS[name].read_text(encoding='utf-8') for name in paths}


def rule_sites(pattern, texts=None):
    """Every line a rule matches, as (file, 1-based line number, stripped line)."""
    texts = texts_of() if texts is None else texts
    sites = []
    for name in SOURCES:
        if name not in texts:
            continue
        for number, line in enumerate(texts[name].splitlines(), 1):
            if pattern.search(line):
                sites.append((name, number, line.strip()))
    return sites


def site_counts(sites):
    """The site count per file, so a rule's homes read as one small dict."""
    counts = {}
    for name, _number, _line in sites:
        counts[name] = counts.get(name, 0) + 1
    return counts


def describe(sites):
    """The sites as report lines, so a failure says which line moved."""
    if not sites:
        return '  (none)'
    return '\n'.join(
        '  {0}:{1}  {2}'.format(name, number, line[:110]) for name, number, line in sites
    )


def label_rows(texts=None):
    """Every ops label row this module names, as {slot: [(file, English, Chinese), ...]}."""
    rows = {}
    for name in SOURCES:
        text = (texts_of() if texts is None else texts).get(name, '')
        for match in OPS_LABEL_ROW_RULE.finditer(text):
            rows.setdefault(match.group(1), []).append((name, match.group(2), match.group(3)))
    return rows


def chinese_words_for(english, texts=None):
    """{slot: [Chinese word, ...]} for every ops row whose English label is exactly this word."""
    answer = {}
    for slot, rows in label_rows(texts).items():
        words = [chinese for _name, word, chinese in rows if word == english]
        if words:
            answer[slot] = words
    return answer


# The driver loads the real annotator/app.js for the owner table, then the two readers, and it reads
# back what each screen paints.  A request plants a sentinel pair over the published owner rows, so a
# reader that stopped asking the owner answers the sentinel-free text instead.
NODE_DRIVER = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const ROOT = request.root;
const SENTINEL = {
  stageEmpty: ['SENTINEL-STAGE-EN', 'SENTINEL-STAGE-ZH'],
  visionLoading: ['SENTINEL-LOADING-EN', 'SENTINEL-LOADING-ZH']
};
const noop = () => {};
function node(selector = '') {
  const n = {
    selector, innerHTML: '', textContent: '', hidden: false, value: '', title: '', children: [],
    dataset: {}, style: {setProperty: noop, getPropertyValue: () => ''},
    classList: {add: noop, remove: noop, toggle: noop}, attributes: {},
    setAttribute(k, v) { n.attributes[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(n.attributes, k) ? n.attributes[k] : null; },
    removeAttribute: noop, appendChild(c) { n.children.push(c); return c; },
    insertAdjacentHTML(_w, html) { n.innerHTML += html; },
    addEventListener: noop, removeEventListener: noop,
    querySelector: () => null, querySelectorAll: () => [], closest: () => null, contains: () => false,
    focus: noop, remove: noop, offsetHeight: 1, checked: false, disabled: false, files: [],
    load: noop, play: noop, pause: noop, blur: noop, click: noop,
    getBoundingClientRect: () => ({top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0}),
    setSelectionRange: noop, getContext: () => null, toDataURL: () => ''
  };
  return n;
}
// The console shell queries more selectors than any one test names, so the document double answers
// every name with a live node.  Nothing in these three modules reads a value back from it.
function universal() {
  const target = function () { return universal(); };
  return new Proxy(target, {
    get(t, k) {
      if (k === 'then' || k === 'toJSON') return undefined;
      if (k === Symbol.toPrimitive) return () => '';
      if (k === 'toString' || k === 'valueOf') return () => '';
      if (k === Symbol.iterator) return function* () {};
      if (k === 'length') return 0;
      if (k === 'nodeType') return 1;
      return universal();
    },
    set() { return true; }, apply() { return universal(); }, has() { return true; }, ownKeys() { return []; },
    getOwnPropertyDescriptor() { return {configurable: true, enumerable: true, value: universal()}; }
  });
}
const documentStub = new Proxy({}, {
  get(t, k) {
    if (k === 'querySelector' || k === 'createElement' || k === 'getElementById' || k === 'createDocumentFragment') return () => universal();
    if (k === 'querySelectorAll') return () => [];
    if (k === 'addEventListener' || k === 'removeEventListener') return noop;
    if (k === 'readyState') return 'complete';
    if (k === 'cookie') return '';
    return universal();
  }
});
const store = {};
const storage = {
  getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; }, clear: noop, key: () => null, length: 0
};
const sandbox = {
  console, JSON, Math, Date, Object, Array, String, Number, Boolean, RegExp, Error, TypeError,
  Promise, Set, Map, Symbol, Proxy, Reflect,
  performance: {now: () => 0},
  navigator: {userAgent: 'node', language: 'en', languages: ['en'], clipboard: {writeText: async () => {}}},
  location: {href: 'http://localhost/annotator/ops.html', search: '', hash: '', pathname: '/annotator/ops.html', origin: 'http://localhost', assign: noop, reload: noop},
  history: {replaceState: noop, pushState: noop}, localStorage: storage, sessionStorage: storage,
  document: documentStub, requestAnimationFrame: () => 0, cancelAnimationFrame: noop,
  setTimeout: () => 0, clearTimeout: noop, setInterval: () => 0, clearInterval: noop,
  fetch: async () => ({ok: true, status: 200, json: async () => ({}), text: async () => '', arrayBuffer: async () => new ArrayBuffer(0)}),
  matchMedia: () => ({matches: false, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop}),
  alert: noop, confirm: () => false, prompt: () => null, URL,
  Blob: function () {}, FileReader: function () {}, Image: function () {}, Event: function () {}, CustomEvent: function () {},
  getComputedStyle: () => ({getPropertyValue: () => ''}),
  addEventListener: noop, removeEventListener: noop, dispatchEvent: noop,
  innerWidth: 1280, innerHeight: 800, devicePixelRatio: 1
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;
sandbox.top = sandbox;
sandbox.parent = sandbox;
vm.createContext(sandbox);
function run(name) {
  const file = path.join(ROOT, 'annotator', name);
  vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox, {filename: name});
}
function excerpt(text) {
  const at = text.indexOf('vs-loading');
  return at < 0 ? text.slice(0, 120) : text.slice(at, at + 120);
}
run('app.js');
const rules = sandbox.window.ConsoleRules;
if (!rules || !rules.words) throw new Error('annotator/app.js published no ConsoleRules.words');
const owner = {count: Object.keys(rules.words).length, stageEmpty: rules.words.stageEmpty, visionLoading: rules.words.visionLoading};
if (request.plant) {
  rules.words = Object.assign({}, rules.words, SENTINEL);
}
let shell = '';
const mount = {
  region: () => node(),
  querySelector(sel) { return sel === '.vs-grid' && shell ? this.region(sel) : null; },
  querySelectorAll: () => [], contains: () => true,
  style: {getPropertyValue: () => '', setProperty: noop},
  addEventListener: noop, removeEventListener: noop,
  insertAdjacentHTML(_w, html) { shell += html; }, shellHTML: () => shell
};
sandbox.window.CornerPocketReview = {snapshot: () => null, subscribe: () => () => {}, reloadDatasets: async () => true};
run('vision-stage.js');
sandbox.window.VisionStage.attach({
  mount, lang: 'en', clock: () => 0, fixedClip: () => false, channels: () => [], vods: () => [],
  regulars: () => [], chat: () => false, notice: noop, review: null
});
run('ops.js');
const handle = sandbox.window.OpsConsole.attach({document: documentStub});
const surface = handle.visionSurface();
const table = handle.words;
const rows = Object.entries(table).map(([key, pair]) => [key, pair[0], pair[1]]);
const byEnglish = word => rows.filter(row => row[1] === word).map(row => [row[0], row[2]]);
const spelling = {};
for (const row of rows) {
  const set = spelling[row[1]] = spelling[row[1]] || [];
  if (!set.includes(row[2])) set.push(row[2]);
}
const split = {};
for (const word of Object.keys(spelling)) if (spelling[word].length > 1) split[word] = spelling[word].sort();
const sentences = rows.filter(row => request.sentences.includes(row[1]) || request.sentences.includes(row[2])).map(row => row[0]);
process.stdout.write(JSON.stringify({
  planted: Boolean(request.plant),
  owner,
  vision: {
    sentinel: shell.includes('SENTINEL-LOADING-EN'),
    real: shell.includes('Loading the review workspace'),
    excerpt: excerpt(shell)
  },
  ops: {
    sentinel: surface.includes('SENTINEL-LOADING-EN'),
    real: surface.includes('Loading the review workspace'),
    excerpt: excerpt(surface)
  },
  table: {
    rows: rows.length,
    remove: byEnglish('Remove'),
    event: byEnglish('Event name'),
    split,
    hasVisionLoading: Object.prototype.hasOwnProperty.call(table, 'visionLoading'),
    fallThrough: handle.t('visionLoading'),
    sentences
  }
}) + '\n');
"""


def console_answers(plant=False):
    """The owner table and the two rendered screens, read by node from the shipped files."""
    node = shutil.which('node')
    if not node:
        raise AssertionError('node is required to read window.ConsoleRules.words of annotator/app.js')
    done = subprocess.run(
        [node, '-e', NODE_DRIVER],
        input=json.dumps({
            'root': str(ROOT),
            'plant': plant,
            'sentences': [STAGE_SENTENCE, STAGE_SENTENCE_ZH, LOADING_SENTENCE, LOADING_SENTENCE_ZH],
        }),
        capture_output=True, text=True, timeout=120,
    )
    if done.returncode != 0:
        raise AssertionError('node could not read the console surfaces:\n' + done.stderr.strip())
    return json.loads(done.stdout)


class StageSentenceTest(unittest.TestCase):
    """Strong 1: the stage-empty sentence has one home, and the page reads it."""

    def test_the_sentence_has_one_home_and_the_page_reads_it(self):
        texts = texts_of()
        sentences = rule_sites(STAGE_SENTENCE_RULE, texts)
        self.assertEqual(
            STAGE_SENTENCE_HOMES, site_counts(sentences),
            'the stage sentence must stand in one home\n' + describe(sentences))
        self.assertFalse(
            STAGE_SENTENCE_DRIFT in texts[VISION],
            'the adapter must not carry the drifted English of the sentence')
        self.assertFalse(
            STAGE_SENTENCE_DRIFT in texts[APP],
            'the owner must spell the sentence once, in its settled words\n' + describe(sentences))
        rows = rule_sites(SLOT_ROW_RULE, texts)
        self.assertEqual(
            SLOT_ROW_HOMES, site_counts(rows),
            'the two slots must own one row each, in annotator/app.js\n' + describe(rows))
        readers = rule_sites(STAGE_READER_RULE, texts)
        self.assertEqual(
            {APP: 1}, site_counts(readers),
            'the page must read the owner row, not spell its own copy\n' + describe(readers))
        paints = rule_sites(STAGE_PAINT_RULE, texts)
        self.assertEqual(
            {APP: 2}, site_counts(paints),
            'both paint sites must call the constant that reads the home\n' + describe(paints))

    def test_a_second_stage_sentence_copy_is_reported(self):
        texts = texts_of()
        planted = dict(texts)
        planted[VISION] = planted[VISION].replace(NO_CROP_EN, PLANTED_ADAPTER_ROW + NO_CROP_EN)
        self.assertNotEqual(texts[VISION], planted[VISION], 'the plant missed its anchor')
        sentences = rule_sites(STAGE_SENTENCE_RULE, planted)
        self.assertEqual(
            {APP: 1, VISION: 1}, site_counts(sentences),
            'a second copy of the sentence must be reported, not hidden\n' + describe(sentences))
        rows = rule_sites(SLOT_ROW_RULE, planted)
        self.assertEqual(
            {APP: 2, VISION: 1}, site_counts(rows),
            'a second row for the slot must be reported, not hidden\n' + describe(rows))

    def test_a_page_reader_that_spells_its_own_copy_is_reported(self):
        texts = texts_of()
        planted = dict(texts)
        planted[APP] = planted[APP].replace(APP_STAGE_READER, "const STAGE_EMPTY_COPY = " + repr(STAGE_SENTENCE) + ';')
        self.assertNotEqual(texts[APP], planted[APP], 'the plant missed its anchor')
        readers = rule_sites(STAGE_READER_RULE, planted)
        self.assertEqual(
            {}, site_counts(readers),
            'a reader that spells its own copy must lose the read of the home\n' + describe(readers))
        self.assertEqual(
            {APP: 2}, site_counts(rule_sites(STAGE_PAINT_RULE, planted)),
            'the paint sites still call the constant, so the plant changed one thing only')


class LoadingSentenceTest(unittest.TestCase):
    """Worth 4: the review-workspace sentence has one home, and both screens read it."""

    def test_the_sentence_has_one_home_and_both_screens_read_it(self):
        texts = texts_of()
        sentences = rule_sites(LOADING_SENTENCE_RULE, texts)
        self.assertEqual(
            LOADING_SENTENCE_HOMES, site_counts(sentences),
            'the loading sentence must stand in one home\n' + describe(sentences))
        rows = rule_sites(SLOT_ROW_RULE, texts)
        self.assertEqual(
            SLOT_ROW_HOMES, site_counts(rows),
            'no reader may keep a row of its own for the slot\n' + describe(rows))
        for pattern, homes in OWNER_BRIDGES:
            sites = rule_sites(pattern, texts)
            self.assertEqual(homes, site_counts(sites), 'a bridge to the owner moved\n' + describe(sites))
        readers = rule_sites(LOADING_READER_RULE, texts)
        self.assertEqual(
            LOADING_READERS, site_counts(readers),
            'every paint site of the sentence must ask the owner row\n' + describe(readers))

    def test_the_owner_table_holds_both_sentence_rows(self):
        answer = console_answers()
        owner = answer['owner']
        self.assertEqual([STAGE_SENTENCE, STAGE_SENTENCE_ZH], owner['stageEmpty'],
                         'the owner row of the stage sentence moved: ' + json.dumps(owner['stageEmpty'], ensure_ascii=False))
        self.assertEqual([LOADING_SENTENCE, LOADING_SENTENCE_ZH], owner['visionLoading'],
                         'the owner row of the loading sentence moved: ' + json.dumps(owner['visionLoading'], ensure_ascii=False))
        self.assertGreater(owner['count'], 20, 'the owner table lost rows: ' + str(owner['count']))

    def test_both_screens_render_the_owner_row_and_not_a_copy(self):
        planted = console_answers(plant=True)
        self.assertTrue(planted['planted'], 'the driver did not plant the sentinel')
        for screen in ('vision', 'ops'):
            self.assertTrue(
                planted[screen]['sentinel'],
                'the ' + screen + ' screen did not read the planted owner row: ' + planted[screen]['excerpt'])
            self.assertFalse(
                planted[screen]['real'],
                'the ' + screen + ' screen painted a copy of its own: ' + planted[screen]['excerpt'])
        unplanted = console_answers()
        self.assertTrue(unplanted['vision']['real'], 'the adapter shell lost the loading line')
        self.assertTrue(unplanted['ops']['real'], 'the console surface lost the loading line')

    def test_a_re_added_reader_row_is_reported(self):
        texts = texts_of()
        planted = dict(texts)
        planted[OPS] = planted[OPS].replace(OPS_VISION_CUES, PLANTED_OPS_ROW + OPS_VISION_CUES)
        self.assertNotEqual(texts[OPS], planted[OPS], 'the plant missed its anchor')
        sentences = rule_sites(LOADING_SENTENCE_RULE, planted)
        self.assertEqual(
            {APP: 1, OPS: 1}, site_counts(sentences),
            'a second copy of the loading sentence must be reported, not hidden\n' + describe(sentences))
        rows = rule_sites(SLOT_ROW_RULE, planted)
        self.assertEqual(
            {APP: 2, OPS: 1}, site_counts(rows),
            'a re-added row for the slot must be reported, not hidden\n' + describe(rows))

    def test_a_reader_that_stopped_reading_the_owner_is_reported(self):
        texts = texts_of()
        console = dict(texts)
        console[OPS] = console[OPS].replace(OPS_SAY_CHAIN, "say=k=>t(k)")
        self.assertNotEqual(texts[OPS], console[OPS], 'the plant missed its anchor')
        for pattern, homes in ((OPS_BRIDGE_RULE, {OPS: 1}), (OPS_SAY_RULE, {OPS: 1})):
            sites = rule_sites(pattern, console)
            self.assertEqual(
                {}, site_counts(sites),
                'the console reader stopped asking the owner, and the guard must say so\n' + describe(sites))
        adapter = dict(texts)
        adapter[VISION] = adapter[VISION].replace(ADAPTER_SAY, 'const say = key => ')
        self.assertNotEqual(texts[VISION], adapter[VISION], 'the plant missed its anchor')
        sites = rule_sites(ADAPTER_SAY_RULE, adapter)
        self.assertEqual(
            {}, site_counts(sites),
            'the adapter reader stopped asking the owner, and the guard must say so\n' + describe(sites))


class LabelAgreementTest(unittest.TestCase):
    """Strong 2: one label answers one word, and the Delete word stays with Delete."""

    def test_both_rows_of_each_label_read_one_word(self):
        texts = texts_of()
        for english, chinese in LABEL_AGREEMENT.items():
            rows = chinese_words_for(english, texts)
            self.assertGreaterEqual(len(rows), 2, 'the label lost its rows: ' + repr(rows))
            for slot, words in rows.items():
                self.assertEqual(
                    [chinese], words,
                    'slot ' + slot + ' reads ' + repr(words) + ', and the label answers only ' + repr(chinese))
            for refused in LABEL_REFUSAL.get(english, ()):
                for slot, words in rows.items():
                    self.assertNotIn(refused, words, refused + ' belongs to another label, and slot ' + slot + ' took it')
        self.assertIn('删除', texts[OPS], 'the console still paints Delete, and its word must stay in the table')

    def test_the_live_table_agrees_on_both_labels(self):
        answer = console_answers()['table']
        self.assertEqual(2, len(answer['remove']), 'the Remove label lost a row: ' + json.dumps(answer['remove'], ensure_ascii=False))
        self.assertEqual(2, len(answer['event']), 'the Event name label lost a row: ' + json.dumps(answer['event'], ensure_ascii=False))
        for slot, chinese in answer['remove']:
            self.assertEqual('移除', chinese, 'the live Remove row of ' + slot + ' reads ' + chinese)
        for slot, chinese in answer['event']:
            self.assertEqual('赛事名', chinese, 'the live Event name row of ' + slot + ' reads ' + chinese)
        self.assertGreater(answer['rows'], 400, 'the live table lost rows: ' + str(answer['rows']))

    def test_no_other_english_word_splits_into_two_chinese_words(self):
        table = console_answers()['table']
        self.assertEqual(
            KNOWN_SPLIT_WORDS, table['split'],
            'a new English word answers with two Chinese words: ' + json.dumps(table['split'], ensure_ascii=False))
        self.assertFalse(
            table['hasVisionLoading'],
            'the console took the review-workspace row back, and the sentence would stand twice')
        self.assertEqual(
            'visionLoading', table['fallThrough'],
            'the console reader no longer stops at its own table: ' + repr(table['fallThrough']))
        self.assertEqual([], table['sentences'],
                         'the console table spells an owner sentence: ' + json.dumps(table['sentences'], ensure_ascii=False))

    def test_a_drifted_label_is_reported(self):
        texts = texts_of()
        drifted_event = dict(texts)
        drifted_event[OPS] = drifted_event[OPS].replace(OPS_EVENT_ROW, "event:['Event name','赛事名称']")
        self.assertNotEqual(texts[OPS], drifted_event[OPS], 'the plant missed its anchor')
        rows = chinese_words_for('Event name', drifted_event)
        self.assertEqual(['赛事名称'], rows['event'],
                         'the drifted spelling must be reported in its own slot: ' + repr(rows))
        self.assertEqual(['赛事名'], rows['bfNightName'],
                         'the other row of the label keeps the settled word: ' + repr(rows))
        self.assertNotEqual(rows['event'], rows['bfNightName'],
                            'two rows of one label that disagree must be reported, not hidden')
        drifted_remove = dict(texts)
        drifted_remove[OPS] = drifted_remove[OPS].replace(OPS_UNMARK_ROW, "bfUnmark:['Remove','删除']")
        self.assertNotEqual(texts[OPS], drifted_remove[OPS], 'the plant missed its anchor')
        rows = chinese_words_for('Remove', drifted_remove)
        self.assertIn('删除', rows['bfUnmark'],
                      'a Remove row that took the Delete word must be reported: ' + repr(rows))


if __name__ == '__main__':
    unittest.main()
