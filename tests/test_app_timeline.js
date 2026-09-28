'use strict';
// Frontend logic tests for annotator/app.js (video timeline mode). Node syntax only, zero deps: node tests/test_app_timeline.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'app.js'), 'utf8');

function elementStub() {
  return {setAttribute() {}, insertAdjacentHTML() {}, addEventListener() {}, classList: {add() {}, remove() {}, toggle() {}}};
}
const sandbox = {
  document: {querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, createElement: () => elementStub()},
  window: {addEventListener() {}},
  fetch: () => Promise.reject(new Error('no network in tests')),
  confirm: () => true,
  URL: {createObjectURL: () => 'blob:test', revokeObjectURL() {}},
  setTimeout, clearTimeout, console, Math, Number, Object, JSON, Date
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
// Instrument within the closure; production exports only its lifecycle API.
vm.runInContext(source.replace(/\}\)\(\);\s*$/, `
  globalThis.T = {clampFrame, frameTime, frameFromTime, timecode, markerLeft, ballLabel, boxCenter, normalizeBox, displayBoxes, state,
    setRoot: host => { root = host; }, onKeydown, text, translateEditor, updateOverlayFacts,
    pocketText, pocketWord, POCKET_LABELS, CLOTH_TOLERANCE_PX, clothTolerance, quadDistance, quadSanity, validateCloth,
    correctionScope, sourceTag, sourceTagLabel, personChip, applyFrameResult, paintOverlay, clothNotice, loadClothReference,
    calibratedPockets, POCKET_ANCHOR_ORDER, polygonSource, quadRefusalText, quadFallbackText, quadReasonText,
    playEvent, eventWindow, dropPerFrame, exitPlayback, stageHTML, bindVideo, stageVideo, paintPlayChip, paintLiveChip,
    placeTags, tagRow, beginTags: () => { tagQueue = []; }, boxTagKind, markBoxEdited, ghostModelBox, boxIou, boxesMatch, isPairedModel, correctionBody, manualBoxCount, modelBoxCount,
    paintCueGeometry, cueGeometryVisible, drawnPocket, staticQuad, colourWord, CLIP_BEFORE_S, CLIP_AFTER_S};
})();`), sandbox, {filename: 'app.js'});
const T = sandbox.T;

const META = {dataset: 'vod30', fps: 25, frame_count: 45000, duration: 1800, width: 1920, height: 1080, timestamp_kind: 'nominal_cfr'};
let passed = 0, failed = 0;
// Arrays come from the vm realm, so compare structurally via JSON.
const same = (a, b) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b));
function test(name, fn) {
  try { fn(); console.log(`PASS ${name}`); passed++; }
  catch (error) { console.error(`FAIL ${name}: ${error.message}`); failed++; }
}

test('lifecycle is the only public namespace and absent host does not mount', () => {
  const api = Object.keys(sandbox.window.CornerPocketReview);
  for (const name of ['mount','activate','deactivate','canLeave','setAppearance','subscribe','snapshot','seek','seekTime','stepFrame','setPlaying','setOverlay','toggleOverlay','selectEvent','playEvent','selectCrop','selectTrack','selectAnchor','selectBox','clearSelection','saveVerdict','labelBall','setSeed','seedIdentity','clearIdentity','enrollPreview','enrollConfirm','setEnrollName','cancelEnroll','saveAnchors','saveCorrections','runInference','setDataset','applyLiveStatus','ingestLiveFrame','liveStateText','freeze','counts','pocketText','colourWord']) assert.ok(api.includes(name), `missing engine API: ${name}`);
  // +2 for the polish's clarify step: pocketText and colourWord, so the adapter names pockets and colours in one vocabulary.
  assert.strictEqual(api.length, 69, 'the engine exposes exactly its lifecycle + one-stage API');
  assert.strictEqual(sandbox.state, undefined);
  assert.strictEqual(sandbox.window.CornerPocketReview.activate('events'), false);
});

test('mount initializes once and standalone mounts only its own host', () => {
  let requests = 0, bindings = 0, rootPresent = false;
  const host = {id:'review-root', dataset:{}, querySelector: () => elementStub(), querySelectorAll: () => [], addEventListener() { bindings++; }};
  let documentBindings = 0;
  const context = {document:{querySelector: () => rootPresent ? host : null, addEventListener() { documentBindings++; }}, window:{addEventListener() {}}, fetch() { requests++; return new Promise(() => {}); }, console};
  vm.createContext(context);
  vm.runInContext(source, context);
  assert.strictEqual(requests, 0);
  const review = context.window.CornerPocketReview;
  const mounting = review.mount(host);
  assert.strictEqual(review.mount(host), mounting);
  assert.strictEqual(requests, 1);
  assert.strictEqual(bindings, 2);
  assert.strictEqual(documentBindings, 1, 'the vision surface owns one document-level key handler');
  assert.strictEqual(review.mount({...host}), false);
  rootPresent = true;
  vm.runInContext(source, context);
  assert.strictEqual(requests, 2, 'standalone host automatically initializes');
});

test('persistent lifecycle preserves edits and uses mode leave guards', () => {
  const review = sandbox.window.CornerPocketReview;
  const content = {...elementStub(), innerHTML:'unsaved form', value:'draft'};
  const host = {id:'review-root', dataset:{}, querySelector: () => content, querySelectorAll: () => []};
  T.setRoot(host);
  assert.strictEqual(review.activate('events'), true);
  T.state.dirty = true;
  sandbox.confirm = () => false;
  assert.strictEqual(review.canLeave(), false);
  assert.strictEqual(review.activate('balls'), false);
  assert.strictEqual(T.state.mode, 'events');
  sandbox.confirm = () => true;
  assert.strictEqual(review.canLeave(), true);
  assert.strictEqual(T.state.dirty, true);
  review.setAppearance('zh', 'light');
  assert.strictEqual(content.innerHTML, 'unsaved form');
  assert.strictEqual(content.value, 'draft');
  assert.strictEqual(T.state.dirty, true);
  assert.strictEqual(host.lang, 'zh');
  assert.strictEqual(host.dataset.theme, 'light');
  T.state.busy = true;
  assert.strictEqual(review.canLeave(), false);
  assert.strictEqual(review.activate('timeline'), false);
  review.deactivate();
  assert.strictEqual(review.canLeave(), true, 'hidden review must not block other shell pages');
  T.onKeydown({target:{closest() { throw new Error('inactive keyboard handler ran'); }}});
  T.state.busy = false;
  assert.strictEqual(review.activate('events'), true);
  assert.strictEqual(T.state.dirty, true);
  assert.strictEqual(content.value, 'draft');
  assert.strictEqual(review.activate('invalid'), false);
  T.state.dirty = false;
  review.deactivate();
});

test('clampFrame clamps, rounds and defaults', () => {
  assert.strictEqual(T.clampFrame(5, META), 5);
  assert.strictEqual(T.clampFrame(-3, META), 0);
  assert.strictEqual(T.clampFrame(99999, META), META.frame_count - 1);
  assert.strictEqual(T.clampFrame(7.6, META), 8);
  assert.strictEqual(T.clampFrame(NaN, META), 0);
  assert.strictEqual(T.clampFrame(4, null), 0);
});

test('frameTime and frameFromTime round-trip via fps', () => {
  assert.strictEqual(T.frameTime(META, 100), 4);
  assert.strictEqual(T.frameFromTime(META, 4), 100);
  assert.strictEqual(T.frameFromTime(META, 4.05), 101);
  assert.strictEqual(T.frameFromTime(META, 99999), META.frame_count - 1);
  assert.strictEqual(T.frameFromTime(META, -5), 0);
});

test('timecode renders m:ss.d', () => {
  assert.strictEqual(T.timecode(0), '0:00.0');
  assert.strictEqual(T.timecode(5), '0:05.0');
  assert.strictEqual(T.timecode(65.43), '1:05.4');
  assert.strictEqual(T.timecode(-2), '0:00.0');
  assert.strictEqual(T.timecode(69.99928974652252), '1:10.0');
  assert.strictEqual(T.timecode(59.99), '1:00.0');
  assert.strictEqual(T.timecode(Infinity), '0:00.0');
});

test('markerLeft clamps outside events to null', () => {
  assert.strictEqual(T.markerLeft({t: 180}, META), 10);
  assert.strictEqual(T.markerLeft({t: -1}, META), null);
  assert.strictEqual(T.markerLeft({t: 1900}, META), null);
});

test('ballLabel and boxCenter', () => {
  assert.ok(T.ballLabel('ball') && T.ballLabel('cue') && T.ballLabel('eight'));
  assert.ok(!T.ballLabel('person') && !T.ballLabel('table'));
  assert.strictEqual(JSON.stringify(T.boxCenter({bbox: [10, 20, 30, 60]})), '[20,40]');
});

test('normalizeBox clamps, reorders, and rejects degenerate boxes', () => {
  assert.deepStrictEqual([...T.normalizeBox([10, 10, 50, 40], 1920, 1080)], [10, 10, 50, 40]);
  assert.deepStrictEqual([...T.normalizeBox([50, 40, 10, 10], 1920, 1080)], [10, 10, 50, 40]);
  assert.deepStrictEqual([...T.normalizeBox([-5, -5, 5000, 5000], 1920, 1080)], [0, 0, 1920, 1080]);
  assert.strictEqual(T.normalizeBox([1, 1, 1, 40], 1920, 1080), null);
  assert.strictEqual(T.normalizeBox([NaN, 1, 5, 5], 1920, 1080), null);
  assert.strictEqual(T.normalizeBox([1, 1], 1920, 1080), null);
});

test('displayBoxes keeps both layers, each box with its own origin', () => {
  const inference = {boxes: [{label: 'person', bbox: [1, 2, 3, 4], score: 0.9}], table_polygon: [[0, 0], [1, 0], [1, 1], [0, 1]]};
  const correction = {boxes: [{label: 'cue', bbox: [5, 6, 7, 8]}], table_polygon: null};
  const display = T.displayBoxes({inference, correction});
  assert.strictEqual(display.source, 'manual corrections');
  // Both layers are kept (the correction no longer replaces the inference), and
  // provenance travels with each box: the correction is the operator's, the
  // inference is the model's, nothing has been edited in this session.
  same(display.boxes, [{label: 'cue', bbox: [5, 6, 7, 8], origin: 'manual', edited: false},
                       {label: 'person', bbox: [1, 2, 3, 4], score: 0.9, origin: 'auto', edited: false}]);
  const inferred = T.displayBoxes({inference, correction: null});
  assert.strictEqual(inferred.source, 'inference');
  same(inferred.boxes, [{label: 'person', bbox: [1, 2, 3, 4], score: 0.9, origin: 'auto', edited: false}]);
  same(inferred.polygon, [[0, 0], [1, 0], [1, 1], [0, 1]]);
  inferred.polygon[0][0] = 99;
  assert.strictEqual(inference.table_polygon[0][0], 0, 'polygon copy must not alias saved data');
  const none = T.displayBoxes({inference: null, correction: null});
  assert.strictEqual(none.source, 'none');
  assert.strictEqual(none.boxes.length, 0);
  assert.strictEqual(none.polygon, null);
});

test('timeline state defaults are safe', () => {
  assert.strictEqual(T.state.detectors.balls, false, 'CPU-heavy balls detector is explicit opt-in');
  assert.strictEqual(T.state.detectors.table, true);
  assert.strictEqual(T.state.detectors.person, true);
  assert.strictEqual(T.state.tool, 'select');
});

test('app.js pins the backend request contract and required labels', () => {
  for (const needle of [
    '/api/video?dataset=', '/api/frame?dataset=', '/api/frame-result?dataset=', '/api/inference?dataset=',
    "'/api/inference',", "'/api/frame-correction',", '/api/unified?dataset=',
    'X-Frame-Index', 'X-Timestamp-Seconds', 'X-Timestamp-Kind', 'X-Frame-Width', 'X-Frame-Height',
    "'/api/' + 'vod30/anchors'", '/api/vod30/seeds', '/api/identity/seed', '/api/balls/',
    'X-Frame-Index', 'AbortController'
  ]) assert.ok(source.includes(needle) || source.includes(needle.replace("' + '", '')), `missing contract fragment: ${needle}`);
  assert.ok(!source.includes('id="vod"'), 'the second VOD video surface is gone');
  assert.ok(!source.includes('Frozen frame inspector'), 'the duplicate frozen-frame panel is gone');
});

test('every processor state translates and never leaks raw English', () => {
  const review = sandbox.window.CornerPocketReview;
  const host = {lang:'en', querySelector: () => elementStub(), querySelectorAll: () => []};
  T.setRoot(host);
  const states = ['idle','starting','running','stopping','stopped','eos','error','failed','completed','unknown'];
  for (const state of states) {
    assert.strictEqual(review.liveStateText(state), state, `${state} must render as itself in EN`);
    host.lang = 'zh';
    const chinese = review.liveStateText(state);
    assert.ok(/[\u4e00-\u9fff]/.test(chinese), `${state} is untranslated in 中`);
    assert.strictEqual(T.text(`Status: ${state}`), `状态：${chinese}`);
    host.lang = 'en';
  }
  assert.strictEqual(review.liveStateText('stopped'), 'stopped');
  assert.strictEqual(review.liveStateText('brand-new-state'), 'brand-new-state', 'unknown values stay verbatim');
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  assert.ok(adapter.includes('liveStateText') && !/esc\(live\.state\)/.test(adapter), 'the adapter must not print the raw state');
});

test('form and video targets never double-consume the stage keys', () => {
  const review = sandbox.window.CornerPocketReview;
  T.setRoot({id:'review-root', dataset:{}, querySelector: () => elementStub(), querySelectorAll: () => []});
  assert.strictEqual(review.activate('timeline'), true);
  assert.ok(source.includes("closest('input,textarea,select,button,video,[contenteditable=\"true\"]')"), 'video is in the early-return selector list');
  T.state.vmeta = {dataset:'vod30', fps:25, frame_count:45000, duration:1800, width:1920, height:1080};
  const before = T.state.frame;
  T.onKeydown({key:'ArrowRight', target:{closest: selector => selector.includes('video') ? {} : null}});
  assert.strictEqual(T.state.frame, before, 'a focused video keeps its own arrow keys');
  T.onKeydown({key:'ArrowRight', target:{closest: selector => selector.includes('input') ? {} : null}});
  assert.strictEqual(T.state.frame, before, 'a form field keeps its own arrow keys');
  T.state.vmeta = null; T.state.dirty = false;
  review.deactivate();
});

test('overlay tags never overprint: YOURS keeps its spot, the rest move to free space inside the frame', () => {
  T.beginTags();
  const markup = [T.tagRow(100, 100, 'auto', 'ball 0.84'), T.tagRow(100, 100, 'manual', 'ball'), T.tagRow(102, 104, 'model', 'person 0.97'),
                  T.tagRow(1270, 710, 'model', 'ball 0.50')].join('');
  const html = T.placeTags(markup, 1280, 720);
  assert.ok(!html.includes('\u0000'), 'every queued row is drawn');
  const rows = [...html.matchAll(/<g class="o-src (\w+)" data-src="\w+"><rect x="(-?\d+)" y="(-?\d+)" width="(\d+)"/g)]
    .map(([, kind, x, y, w]) => ({kind, x: +x, y: +y, w: +w}));
  assert.strictEqual(rows.length, 4);
  const yours = rows.find(r => r.kind === 'manual');
  assert.deepStrictEqual([yours.x, yours.y], [100, 100], 'the operator\u2019s tag is placed first, where it was asked for');
  // A row is its tag plus the label text after it: measure where each label ends.
  const ends = [...html.matchAll(/<text class="o-label" x="(-?\d+)" y="(-?\d+)">([^<]*)<\/text>/g)].map(([, x, y, s]) => ({x: +x, y: +y, end: +x + s.length * 14 * 0.62}));
  const full = rows.map(r => { const l = ends.find(e => e.y === r.y + 13 && e.x === r.x + r.w + 6); return {...r, w: l ? Math.ceil(l.end - r.x) : r.w}; });
  for (let i = 0; i < full.length; i++) for (let j = i + 1; j < full.length; j++) {
    const a = full[i], b = full[j];
    const overlap = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + 20 && b.y < a.y + 20;
    assert.ok(!overlap, `rows ${a.kind}@${a.x},${a.y} and ${b.kind}@${b.x},${b.y} do not overlap`);
  }
  for (const r of rows) assert.ok(r.x >= 0 && r.y >= 0 && r.y + 20 <= 720, `${r.kind} stays inside the frame`);
  assert.strictEqual(T.tagRow(5, 6, 'model', ''), T.tagRow(5, 6, 'model', ''), 'outside a paint a row is drawn where asked (no queue)');
  assert.ok(T.tagRow(5, 6, 'model', '').includes('x="5" y="6"'));
});

test('round 1 · overlay tags stay legible at the displayed scale and never overprint; nothing they said is lost', () => {
  // A 1280-wide frame shown 372 px wide (the 390 phone): tags scale so the text is >= 11 px on screen.
  const src = fs.readFileSync(path.join(__dirname, '../annotator/app.js'), 'utf8');
  assert.ok(/const MIN_TAG_PX = 11;/.test(src) && /tagScale = measureTagScale\(svg, state\.frameWidth \|\| 1280\);/.test(src), 'the scale is measured every paint');
  // measureTagScale: 14 px frame text shown at 372/1280 would be 4 px; the tag scales so it is 11 px.
  const measure = new Function(`${src.slice(src.indexOf('const SRC_TAG_HEIGHT'), src.indexOf('function glyphWidth'))}; return measureTagScale;`)();
  const k = measure({getBoundingClientRect: () => ({width: 372})}, 1280);
  assert.ok(Math.abs(14 * k * 372 / 1280 - 11) < 0.01, `14 px x ${k.toFixed(2)} x 372/1280 = 11 px on screen`);
  assert.strictEqual(measure({getBoundingClientRect: () => ({width: 1280})}, 1280), 1, 'a full-size frame is not scaled');
  // Crowded frame: 12 model rows asked for the same spot, plus the operator's and a calibration row.
  T.beginTags();
  const asks = [T.tagRow(100, 100, 'manual', 'ball'), T.tagRow(100, 100, 'calib', 'top-left')];
  for (let i = 0; i < 12; i++) asks.push(T.tagRow(100 + i, 100, 'auto', 'person'));
  const html = T.placeTags(asks.join(''), 1280, 720);
  assert.ok(!html.includes('\u0000'), 'every queued row resolves');
  const rows = [...html.matchAll(/<g class="o-src (\w+)" data-src="\w+">(<title>([^<]*)<\/title>)?<rect x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)"/g)]
    .map(([, kind, , title, x, y, w, h]) => ({kind, title, x: +x, y: +y, w: +w, h: +h}));
  const labels = [...html.matchAll(/<text class="o-label" x="(-?\d+)" y="(-?\d+)"[^>]*>([^<]*)<\/text>/g)].map(([, x, y, s]) => ({x: +x, y: +y, s}));
  const full = rows.map(r => { const l = labels.find(e => e.x > r.x && e.x <= r.x + r.w + 12 && e.y > r.y && e.y <= r.y + r.h); return {...r, w: l ? Math.ceil(l.x + l.s.length * 14 * 0.62 - r.x) : r.w}; });
  for (let i = 0; i < full.length; i++) for (let j = i + 1; j < full.length; j++) {
    const a = full[i], b = full[j];
    assert.ok(!(a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + a.h && b.y < a.y + b.h), `rows ${a.kind}@${a.x},${a.y} and ${b.kind}@${b.x},${b.y} never overprint`);
  }
  assert.ok(rows.some(r => r.kind === 'manual') && rows.some(r => r.kind === 'calib'), 'the operator\u2019s and calibration rows always keep a spot');
  // A row with no room for its label keeps its chip, with the label as the chip's title (one hover away).
  for (const r of rows.filter(r => r.title)) assert.strictEqual(r.title, 'person', 'a chip-only row keeps its label in <title>');
  // Confidence is not printed on the frame any more; it is in the box's <title>, with who drew it.
  assert.ok(!/\bperson 0\.\d\d\b/.test(src.slice(src.indexOf('function paintOverlay'))), 'the score left the tag text');
  assert.ok(src.includes("text('confidence')") && src.includes("'confidence':'置信度'"), 'and is in the box title, EN and 中');
});

test('F3: with a box selected the arrows nudge it both ways (Shift = 10 px); with none, ←/→ step frames', () => {
  const review = sandbox.window.CornerPocketReview;
  T.setRoot({id:'review-root', dataset:{}, querySelector: () => elementStub(), querySelectorAll: () => []});
  assert.strictEqual(review.activate('timeline'), true);
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  T.setRoot({lang:'en', dataset:{}, querySelector: s => s === '#t-overlay' ? svg : s === '#stage-note' ? note : null, querySelectorAll: () => []});
  T.state.vmeta = {dataset:'vod30', fps:25, frame_count:45000, duration:1800, width:1920, height:1080};
  T.state.frameWidth = 1920; T.state.frameHeight = 1080;
  T.state.boxes = [{label:'ball', bbox:[100, 100, 140, 140], source:'manual'}];
  T.state.sel.kind = 'box'; T.state.sel.box = 0;
  const frame = T.state.frame;
  const key = (k, shift = false) => T.onKeydown({key:k, shiftKey:shift, preventDefault() {}, target:{closest: () => null}});
  key('ArrowRight');
  assert.deepStrictEqual([...T.state.boxes[0].bbox], [101, 100, 141, 140], '→ moves the box 1 px right');
  key('ArrowLeft', true);
  assert.deepStrictEqual([...T.state.boxes[0].bbox], [91, 100, 131, 140], 'Shift+← moves it 10 px left');
  key('ArrowDown', true);
  assert.deepStrictEqual([...T.state.boxes[0].bbox], [91, 110, 131, 150], 'Shift+↓ moves it 10 px down');
  assert.strictEqual(T.state.frame, frame, 'and the frame never steps while a box is selected');
  T.state.sel.kind = 'none'; T.state.sel.box = -1; T.state.boxes = [];
  T.state.vmeta = null; T.state.dirty = false;
  review.deactivate();
});

test('engine copy localizes notices, statuses and save receipts', () => {
  const host = {lang:'zh', querySelector: () => elementStub(), querySelectorAll: () => []};
  T.setRoot(host);
  for (const [source, chinese] of [
    ['Select a ball or a crop first.', '请先选择球或裁剪图。'],
    ['Select a visible track first.', '请先选择可见的轨迹。'],
    ['Live start failed: Select a saved canonical Twitch channel', '直播启动失败：Select a saved canonical Twitch channel'],
    ['Save failed: HTTP 409. Your changes remain on screen; retry when ready.', '保存失败：HTTP 409。更改仍保留在屏幕上，可稍后重试。'],
    ['crop t00005_b00.jpg = Cue 0', '裁剪图 t00005_b00.jpg = 母球 0'],
    ['crop t00005_b00.jpg = Ball 7', '裁剪图 t00005_b00.jpg = 球 7'],
    ['crop t00005_b00.jpg = Unknown', '裁剪图 t00005_b00.jpg = 未知'],
    ['crop t00005_b00.jpg = cleared', '裁剪图 t00005_b00.jpg = 已清除'],
    ['win 68-94 · track 1 = A', '窗口 68-94 · 轨迹 1 = A'],
    ['6 anchors @ t 70.0', '6 个锚点 @ t 70.0'],
    ['frame 0 · 14 boxes + polygon', '帧 0 · 14 个标注框 + 多边形'],
    ['shot #2 shot @ frame 180 · correct', '击球 #2 @ 帧 180 · 正确'],
    ['Status: stopped', '状态：已停止'],
    ['Status: running', '状态：运行中']
  ]) assert.strictEqual(T.text(source), chinese, source);
  host.lang = 'en';
  assert.strictEqual(T.text('Select a ball or a crop first.'), 'Select a ball or a crop first.', 'source text is language-neutral');
  assert.strictEqual(T.text('win 68-94 · track 1 = A'), 'win 68-94 · track 1 = A');
  host.lang = 'zh';
});

test('app.html is one stage host with no sub-tab navigation', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'app.html'), 'utf8');
  assert.ok(html.includes('id="review-root"') && html.includes('id="content"'));
  assert.ok(!html.includes('data-mode='), 'review mode buttons are gone');
  assert.ok(!html.includes('ops-header'), 'the duplicate review header is gone');
});

test('app.css styles the one stage surface, ops.css styles the rails and strip', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'app.css'), 'utf8');
  for (const needle of ['.stage > img', '#t-overlay', '.draw-preview', '.t-poly', '.center-dot', '.stage-popover', '.pop-grid']) {
    assert.ok(css.includes(needle), `missing stage css: ${needle}`);
  }
  assert.ok(!css.includes('.timeline-grid'), 'the two-panel timeline grid is gone');
  assert.ok(!css.includes('[data-embedded] nav'), 'the hidden review nav rule is gone');
  const ops = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'ops.css'), 'utf8');
  for (const needle of ['.vs-grid', '.vs-rail', '.vs-inspector', '.vs-strip', '.scrub-mark', '.vs-layer', '.vs-sheettabs', 'grid-template-columns:280px minmax(0,1fr) 320px']) {
    assert.ok(ops.includes(needle), `missing surface css: ${needle}`);
  }
  // The inspector scrolls above a fixed action footer: the scroll region reserves
  // the footer's measured height, so no row hides under it at 390 or at short heights.
  assert.ok(ops.includes('padding-bottom:calc(12px + var(--vs-footer-h,0px))'), 'the scroll region must reserve the footer height');
  assert.ok(ops.includes('scroll-padding-bottom:calc(var(--vs-footer-h,0px) + 8px)'));
  assert.ok(ops.includes('.vs-inspector-actions{flex:none'), 'the footer is a flex sibling, not an overlay');
  assert.ok(ops.includes(':is(#ops-shell) .vs-rail{overflow:auto}'), 'only the rail keeps its own mobile scroll');
  assert.ok(!/bottom:44px;max-height:44vh;overflow:auto/.test(ops), 'the mobile aside must not scroll under the footer');
  // On a phone the sheet stops where the 16:9 stage ends (measured), so it never covers the picture.
  assert.ok(ops.includes('var(--vs-strip-h,150px) - var(--vs-stage-bottom,240px))') && !ops.includes('var(--vs-strip-h,150px) - 240px)'),
    'the sheet height gives way to the measured stage bottom, not a fixed 240 px');
  const adapterCode = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  assert.ok(adapterCode.includes("root.style.setProperty('--vs-stage-bottom'") && adapterCode.includes("footerObserver.observe(frame)"),
    'the stage bottom is measured and re-measured when the frame resizes');
});

test('editor translation preserves dirty values, focus, selection and pending save state', () => {
  const caption = {nodeType:3, nodeValue:'Frame load failed'};
  const optionText = {nodeType:3, nodeValue:'solid'};
  const button = {tagName:'BUTTON', childNodes:[caption], disabled:true};
  const option = {tagName:'OPTION', childNodes:[optionText], value:'solid', hasAttribute: () => false, setAttribute(name, value) { this[name] = value; }};
  const note = {value:'Save review — my raw note', placeholder:'What does the source actually show?', selectionStart:4, selectionEnd:9};
  let onMutation, requests = 0;
  sandbox.MutationObserver = class { constructor(callback) { onMutation = callback; } observe() {} };
  sandbox.fetch = () => { requests++; throw new Error('language switch must not fetch'); };
  const host = {lang:'en', dataset:{}, querySelector: () => elementStub(), querySelectorAll: selector => selector.includes('[data-i18n]') ? [] : selector.includes('[placeholder]') ? [note] : selector.includes('[aria-label]') ? [] : [button, option]};
  T.setRoot(host); T.state.dirty = true; T.state.busy = true; T.state.sel = 2;
  sandbox.document.activeElement = note;
  const before = JSON.stringify(T.state);
  sandbox.window.CornerPocketReview.setAppearance('zh', 'light');
  assert.strictEqual(requests, 0);
  assert.strictEqual(caption.nodeValue, '帧加载失败');
  assert.strictEqual(optionText.nodeValue, '实色');
  assert.strictEqual(option.value, 'solid');
  assert.strictEqual(note.value, 'Save review — my raw note');
  assert.strictEqual(note.selectionStart, 4); assert.strictEqual(note.selectionEnd, 9);
  assert.strictEqual(sandbox.document.activeElement, note);
  assert.strictEqual(button.disabled, true); assert.strictEqual(JSON.stringify(T.state), before);
  host.lang = 'en'; T.translateEditor();
  assert.strictEqual(caption.nodeValue, 'Frame load failed');
  assert.strictEqual(note.placeholder, 'What does the source actually show?');
  host.lang = 'zh'; caption.nodeValue = 'Saving…'; T.translateEditor();
  assert.strictEqual(caption.nodeValue, '保存中…');
  caption.nodeValue = 'Frame load failed'; onMutation();
  assert.strictEqual(caption.nodeValue, '帧加载失败');
  assert.strictEqual(T.text('Save failed: HTTP 409: abc_xyz. Your changes remain on screen; retry when ready.'), '保存失败：HTTP 409: abc_xyz。更改仍保留在屏幕上，可稍后重试。');
  assert.strictEqual(T.text('abc_xyz'), 'abc_xyz');
  // The facts line is composed by the vision-stage adapter from state.drawn, so the
  // engine only has to record what the painter drew.
  T.updateOverlayFacts('manual corrections');
  assert.strictEqual(T.state.drawn.source, 'manual corrections');
  assert.strictEqual(T.text('RAW DECODED FRAME · vod30 · frame 100 · nominal 4.000s (nominal_cfr) · OVERLAYS: manual corrections'), '原始解码帧 · vod30 · 帧 100 · 名义时间 4.000s (nominal_cfr) · 叠加层：人工修正');
  host.lang = 'zh';
  // The person-identity copy moved to the adapter when the players sub-tab became
  // an inspector block, so that string is now covered by the adapter parity test.
  assert.strictEqual(T.text('Status: failed — MODEL_PATH=/tmp/a'), '状态：失败 — MODEL_PATH=/tmp/a');
  assert.strictEqual(T.text('RAW DECODED FRAME · vod30 · frame 100 · nominal 4.000s (nominal_cfr) · OVERLAYS: manual corrections'), '原始解码帧 · vod30 · 帧 100 · 名义时间 4.000s (nominal_cfr) · 叠加层：人工修正');
  assert.strictEqual(T.text('Inference running for frame 100: SAM3_CPU…'), '正在对帧 100 运行推理：SAM3_CPU…');
  T.state.dirty = false; T.state.busy = false;
});

test('browser regression: translated options keep submitted values, stage copy keeps parity', () => {
  const options = ['solid','stripe','eight'].map(value => ({tagName:'OPTION', value, childNodes:[{nodeType:3,nodeValue:value}], hasAttribute: () => true}));
  const host = {lang:'zh', querySelectorAll: selector => selector.includes('option') ? options : []};
  T.setRoot(host); T.translateEditor();
  same(options.map(option => option.value), ['solid','stripe','eight']);
  same(options.map(option => option.childNodes[0].nodeValue), ['实色','花色','黑八']);
  const hint = 'Drag boxes or corner handles; arrow keys nudge the selected box (Shift = 10 px). Ball centers follow their box. Drag table polygon corners. Saving writes manual corrections for this exact frame; saved inference is never overwritten.';
  assert.strictEqual(T.text(hint), '拖动标注框或角点控制柄；方向键微调所选框（Shift = 10 像素）。球心随标注框移动。可拖动球桌多边形角点。保存仅写入此精确帧的人工修正，绝不覆盖已保存的推理结果。');
  host.lang = 'en'; T.translateEditor();
  same(options.map(option => option.nodeValue), [undefined, undefined, undefined]);
  same(options.map(option => option.childNodes[0].nodeValue), ['solid','stripe','eight']);
});

test('adapter facts line separates model result from manual correction', () => {
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const context = {window:{}, document:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}}, location:{hostname:'127.0.0.1'}};
  vm.createContext(context);
  vm.runInContext(adapter, context);
  const base = {
    source:{kind:'vod', label:'vod30', channel:null}, frame:{index:8100, t:270, duration:1800, count:45000, playing:false, rate:0},
    loading:{overlay:false, since:0}, busy:false, live:{stale:false, seq:null, frame_age_ms:null, receive_to_result_ms:null},
    drawn:{cloth:2, balls:16, persons:8, pockets:6, anchors:0, events:1, auto:{cloth:1, balls:8, persons:4, pockets:6, anchors:0, events:1}}
  };
  const facts = context.window.VisionStage.factsLine(base);
  assert.ok(facts.includes('cloth 1 (+1 manual)'), facts);
  assert.ok(facts.includes('balls 8 (+8 manual)'), facts);
  assert.ok(facts.includes('persons 4 (+4 manual)'), facts);
  assert.ok(facts.includes('pockets 6') && !facts.includes('pockets 6 (+'), 'pockets are never manual');
  assert.ok(facts.endsWith('overlays ON'), facts);
  const clean = context.window.VisionStage.factsLine({...base, drawn:{cloth:1, balls:8, persons:4, pockets:6, anchors:0, events:1, auto:{cloth:1, balls:8, persons:4, pockets:6, anchors:0, events:1}}});
  assert.ok(!clean.includes('manual'), 'an untouched frame prints no provenance marker');
  const loading = context.window.VisionStage.factsLine({...base, loading:{overlay:true, since: Date.now() - 1600}});
  assert.ok(/overlays LOADING \(1\.[56] s\)$/.test(loading), loading);
  const empty = context.window.VisionStage.factsLine({...base, drawn:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0}}});
  assert.ok(empty.endsWith('overlays none'), empty);
  const older = context.window.VisionStage.factsLine({...base, drawn:{cloth:1, balls:2, persons:0, pockets:0, anchors:0, events:0}});
  assert.ok(older.includes('balls 2') && !older.includes('manual'), 'a snapshot without provenance still prints its totals');
});

test('an accepted quad prints its measured drift, not just a pass', () => {
  // The detector searches around the saved anchors it is validated against
  // (src/frame_inference.app_prior_for), so "ok" alone would hide the number
  // that says how far the refinement moved from the operator's corners.
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const context = {window:{}, document:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}}, location:{hostname:'127.0.0.1'}};
  vm.createContext(context);
  vm.runInContext(adapter, context);
  const base = {
    source:{kind:'vod', label:'vod30', channel:null}, frame:{index:8100, t:270, duration:1800, count:45000, playing:false, rate:0},
    loading:{overlay:false, since:0}, busy:false, live:{stale:false, seq:null, frame_age_ms:null, receive_to_result_ms:null},
    drawn:{cloth:1, balls:8, persons:4, pockets:6, anchors:0, events:1, auto:{cloth:1, balls:8, persons:4, pockets:6, anchors:0, events:1}},
    cloth:{verdict:{state:'ok', reason:'within tolerance', mean:6.43, max:8.07, tolerance:40, source:'saved anchors'},
           pockets:{source:'model', count:6, reference:null}, reference:{source:'saved anchors', width:1280, height:720}}
  };
  const fresh = context.window.VisionStage.factsLine(base);
  // Round 1 (pin changed deliberately): the plain check leads, the measured drift and the
  // tolerance still follow it, so an accepted quad still prints its number, not just a pass.
  assert.ok(fresh.includes('table outline matches the saved corners (6.4 px · tol 40 px)'), fresh);
  const unverified = context.window.VisionStage.factsLine({...base, cloth:{...base.cloth, verdict:{state:'unverified', mean:null, tolerance:null}}});
  assert.ok(unverified.includes('model quad unverified') && !unverified.includes('quad drift'), unverified);
  const off = context.window.VisionStage.factsLine({...base, cloth:{...base.cloth, verdict:{state:'off', reason:'off saved corners', mean:43.2, tolerance:40}}});
  assert.ok(off.includes('model quad off saved corners 43 px (tol 40 px)'), off);
});

test('the facts line uses one word for one live state', () => {
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const context = {window:{}, document:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}}, location:{hostname:'127.0.0.1'}};
  vm.createContext(context);
  vm.runInContext(adapter, context);
  const live = {source:{kind:'live', label:'live', channel:'examplechannel'}, frame:{index:0, t:0, duration:1800, count:45000, playing:false, rate:0},
    loading:{overlay:false, since:0}, busy:false, live:{stale:false, seq:12, frame_age_ms:240, receive_to_result_ms:33},
    drawn:{cloth:1, balls:0, persons:3, pockets:0, anchors:0, events:0, auto:{cloth:1, balls:0, persons:3, pockets:0, anchors:0, events:0}}};
  const fresh = context.window.VisionStage.factsLine(live);
  assert.ok(fresh.startsWith('live · seq 12'), fresh);
  const stale = context.window.VisionStage.factsLine({...live, live:{...live.live, stale:true, frame_age_ms:10200}});
  assert.ok(stale.startsWith('stale · seq 12'), stale);
  assert.ok(!stale.includes('live'), 'the stale state is not described as live');
  assert.ok(stale.includes('frame age 10.2 s') && stale.includes('receive-to-result 33 ms'), stale);
  assert.ok(adapter.includes('not glass-to-glass') || adapter.includes('latency'), 'the latency caveat string is untouched');
});

test('the verdict keys act on the selected cue only', () => {
  const review = sandbox.window.CornerPocketReview;
  T.setRoot({id:'review-root', dataset:{}, querySelector: () => elementStub(), querySelectorAll: () => []});
  assert.strictEqual(review.activate('timeline'), true);
  T.state.events = [{id: 29, type: 'pot', t: 8100}, {id: 30, type: 'shot', t: 9000}];
  T.state.annotations = {};
  T.state.verdictDraft = null;
  T.state.sel = {kind:'none', crop:null, ball:null, person:null, track:null, anchor:0, event:null, box:-1};
  const key = (k, opts = {}) => T.onKeydown({key: k, target:{closest: () => null}, preventDefault() {}, ...opts});
  key('v');
  assert.strictEqual(T.state.verdictDraft, null, 'V must not draft a verdict with no cue selected');
  assert.strictEqual(T.state.notice.text, 'Select a cue first.');
  key('Enter');
  assert.deepStrictEqual(T.state.annotations, {}, '⏎ must not save a verdict with no cue selected');
  T.state.sel = {kind:'event', event: T.state.events[0], crop:null, ball:null, person:null, track:null, anchor:0, box:-1};
  key('v');
  assert.strictEqual(T.state.verdictDraft, 'correct');
  T.state.verdictDraft = null; T.state.dirty = false;
  review.deactivate();
});

test('the adapter localizes engine state, keeps one scrub range and one action footer', () => {
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const shell = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'ops.js'), 'utf8');
  // 1. the scrub range is driven like the frame field, not left at max=0
  assert.ok(/scrub\.getAttribute\('max'\) !== max/.test(adapter), 'the scrub range must publish frame_count - 1');
  assert.ok(adapter.includes("scrub.setAttribute('max', max)"));
  assert.ok(adapter.includes("scrub.setAttribute('step', '1')"));
  // 2. engine-built strings render in the active language
  assert.ok(adapter.includes('engineText(s.notice.text)'), 'notices localize at render');
  // the reserved footer height is measured, never hardcoded
  assert.ok(adapter.includes('footer.offsetHeight') && adapter.includes("setProperty('--vs-footer-h'"), 'the footer height must be derived');
  assert.ok(adapter.includes('new ResizeObserver(syncFooterHeight)'), 'footer height changes must re-derive the padding');
  assert.ok(adapter.includes("data-vs-action=\"verdict-draft\""), 'the verdict verbs live in the always-visible footer');
  assert.ok(adapter.includes('engineText(row.text)'), 'receipts localize at render');
  assert.ok(adapter.includes('engineText(s.corrections.inferStatus'));
  assert.ok(adapter.includes('engineText(s.persons.status'));
  // 3. a failed start is a failed state in the status row
  assert.ok(adapter.includes('liveRowState'), 'the live row must not read idle after a failed start');
  // 4. the primary action of each block lives in an always-visible footer
  assert.ok(adapter.includes('function actionsHTML'));
  assert.ok(shell.includes('id="vs-inspector-scroll"') && shell.includes('id="vs-inspector-actions"'));
  assert.ok(!adapter.includes('vs-sticky'), 'the footer replaced the sticky row');
  // 5. a dataset switch re-loads the stage even while a decode owns it
  assert.ok(source.includes('state.pendingSeek = 0'), 'the dataset switch must queue its frame reload');
  assert.ok(source.includes('state.live.detections = null'), 'live detections must not survive a dataset switch');
});

test('every adapter string ships in both languages', () => {
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const start = adapter.indexOf('const COPY = {');
  const literal = adapter.slice(adapter.indexOf('{', start), adapter.indexOf('\n};', start) + 2);
  const table = vm.runInNewContext(`(${literal})`);
  const enKeys = Object.keys(table.en).sort(), zhKeys = Object.keys(table.zh).sort();
  assert.ok(enKeys.length > 60, `adapter copy table looks truncated: ${enKeys.length}`);
  same(zhKeys, enKeys);
  for (const key of enKeys) assert.ok(String(table.zh[key] || '').length, `missing zh copy for ${key}`);
  for (const key of ['cues','inspector','sources','verdict','freeze','stale','startFailed','saveAnchors','latency']) {
    assert.notStrictEqual(table.zh[key], table.en[key], `${key} is untranslated`);
    assert.ok(/[\u4e00-\u9fff]/.test(table.zh[key]), `${key} has no Chinese copy`);
  }
  const zhBlock = adapter.slice(adapter.indexOf('zh: {'));
  assert.ok(zhBlock.includes('线索') && zhBlock.includes('启动尝试') && zhBlock.includes('已过期'));
});

test('pocket labels are position words in both languages, never rail terms', () => {
  const host = {lang:'en', querySelector: () => elementStub(), querySelectorAll: () => []};
  T.setRoot(host);
  assert.strictEqual(T.pocketText('foot-right (124mm)'), 'bottom-right (124mm)');
  assert.strictEqual(T.pocketText('557mm from foot-right'), '557mm from bottom-right');
  assert.strictEqual(T.pocketText('left-side (77mm)'), 'left-middle (77mm)');
  assert.strictEqual(T.pocketText('head-left'), 'top-left');
  assert.strictEqual(T.pocketText('head-right'), 'top-right');
  assert.strictEqual(T.pocketText('foot-left'), 'bottom-left');
  host.lang = 'zh';
  assert.strictEqual(T.pocketText('foot-right (124mm)'), '右下 (124mm)');
  assert.strictEqual(T.pocketText('557mm from foot-right'), '距右下 557mm');
  assert.strictEqual(T.pocketText('head-right'), '右上');
  host.lang = 'en';
  // Stored keys are untouched: the map is applied at render time only.
  assert.strictEqual(Object.keys(T.POCKET_LABELS).sort().join(','), 'foot-left,foot-right,head-left,head-right,left-side,right-side');
  assert.strictEqual(T.pocketText('brand-new-pocket'), 'brand-new-pocket', 'unknown tokens stay verbatim');
  // The engine publishes the display name beside the stored one.
  T.state.events = [{id: 1, type: 'pot', t: 5.6, nearest_pocket: 'foot-right (124mm)'}];
  T.state.annotations = {};
  const snap = sandbox.window.CornerPocketReview.snapshot();
  assert.strictEqual(snap.events.items[0].nearest_pocket, 'foot-right (124mm)');
  assert.strictEqual(snap.events.items[0].nearest_pocket_text, 'bottom-right (124mm)');
  T.state.events = [];
});

test('the automatic cloth quad is validated against the dataset reference', () => {
  const reference = {points: [[454.9,307.8],[799.5,319.4],[1023.8,573.1],[449.6,563.5]], source:'saved calibration', width:1280, height:720};
  const saved = [[455,308],[800,320],[1024,573],[450,564]];
  const ok = T.validateCloth(saved, reference, 1280, 720);
  assert.strictEqual(ok.state, 'ok');
  assert.ok(ok.mean < 2 && ok.tolerance === T.CLOTH_TOLERANCE_PX);
  // A quad that starts at another vertex is the same quadrilateral.
  assert.strictEqual(T.validateCloth([[800,320],[1024,573],[450,564],[455,308]], reference, 1280, 720).state, 'ok');
  // A mirrored quad is a different projection and never aligns.
  assert.notStrictEqual(T.validateCloth([[307.8,454.9],[319.4,799.5],[573.1,1023.8],[563.5,449.6]], reference, 1280, 720).state, 'ok');
  // The measured per-frame detector quads (59.9-145 px) are refused.
  for (const quad of [[[190,176],[806,324],[1024,596],[384,566]], [[534,258],[768,282],[1036,594],[378,550]], [[208,216],[1000,226],[1008,600],[384,566]]]) {
    const verdict = T.validateCloth(quad, reference, 1280, 720);
    assert.strictEqual(verdict.state, 'off', `quad ${JSON.stringify(quad)} must be refused`);
    assert.ok(verdict.mean > verdict.tolerance);
  }
  // Geometry that is not a table quad is refused before any distance check.
  assert.strictEqual(T.validateCloth([[10,10],[20,10],[20,20],[10,20]], reference, 1280, 720).reason, 'invalid geometry');
  assert.strictEqual(T.validateCloth([[NaN,0],[1,1],[2,2],[3,3]], reference, 1280, 720).reason, 'invalid geometry');
  assert.strictEqual(T.validateCloth([[0,0],[2000,0],[2000,2000],[0,2000]], reference, 1280, 720).detail, 'outside frame');
  assert.strictEqual(T.validateCloth([[100,100],[110,100],[110,105],[100,100]], reference, 1280, 720).reason, 'invalid geometry');
  // No reference for this dataset: drawn, but never silently trusted.
  assert.strictEqual(T.validateCloth(saved, null, 1280, 720).state, 'unverified');
  // The tolerance follows the source size the reference was measured at.
  assert.strictEqual(T.clothTolerance(reference, 1920), 60);
  assert.strictEqual(T.clothTolerance(null, 1280), T.CLOTH_TOLERANCE_PX);
  assert.strictEqual(T.clothTolerance(reference, 0), T.CLOTH_TOLERANCE_PX);
  // The clearance bar must not move without this suite moving with it.
  assert.strictEqual(T.CLOTH_TOLERANCE_PX, 40);
});

test('a saved correction is drawn only for the frame it belongs to', () => {
  const frame = {dataset:'vod30', frame:2101, width:1280, height:720};
  const good = {dataset:'vod30', frame_index:2101, width:1280, height:720, boxes:[{label:'person', bbox:[1,2,30,40]}], table_polygon:[[0,0],[10,0],[10,10],[0,10]]};
  assert.strictEqual(T.correctionScope(good, frame).ok, true);
  assert.strictEqual(T.correctionScope(null, frame).ok, true, 'no correction is not a refusal');
  const wrongFrame = T.correctionScope({...good, frame_index:2100}, frame);
  assert.strictEqual(wrongFrame.ok, false);
  assert.strictEqual(wrongFrame.owner, 'vod30 frame 2100 @ 1280×720');
  assert.strictEqual(wrongFrame.expected, 'vod30 frame 2101 @ 1280×720');
  const wrongSize = T.correctionScope({...good, width:1920, height:1080}, frame);
  assert.strictEqual(wrongSize.ok, false);
  assert.ok(wrongSize.detail.includes('width 1920 ≠ 1280') && wrongSize.detail.includes('height 1080 ≠ 720'), wrongSize.detail);
  assert.strictEqual(T.correctionScope({...good, dataset:'highlight'}, frame).ok, false);
  assert.strictEqual(T.correctionScope({boxes:[], table_polygon:null}, frame).ok, false, 'an unscoped file cannot be tied to this frame');
  // The stage drops a foreign correction from state, so nothing downstream can
  // paint it or count it as this frame's manual geometry.
  T.setRoot({lang:'en', querySelector: () => null, querySelectorAll: () => []});
  T.state.dataset = 'vod30'; T.state.frame = 2101; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.sel = {kind:'none', crop:null, ball:null, person:null, track:null, anchor:0, event:null, box:-1};
  T.state.fresult = {inference:{boxes:[{label:'ball', bbox:[5,5,20,20]}], table_polygon:null}, correction:{...good, frame_index:2100, boxes:[{label:'person', bbox:[9,9,99,99]}]}};
  T.applyFrameResult();
  assert.strictEqual(T.state.fresult.correction, null);
  // The foreign correction was dropped, so what is left is the model's own box:
  // the surviving layer's provenance is the inference's, not the correction's.
  same(T.state.boxes, [{label:'ball', bbox:[5,5,20,20], origin:'auto', edited:false}]);
  assert.strictEqual(T.state.polygon, null);
  assert.strictEqual(T.state.cloth.refusal.ok, false);
  assert.strictEqual(T.state.cloth.refusal.owner, 'vod30 frame 2100 @ 1280×720');
  // The same correction on its own frame is kept and counted as manual.
  T.state.fresult = {inference:null, correction:{...good, boxes:[{label:'person', bbox:[9,9,99,99]}]}};
  T.applyFrameResult();
  assert.strictEqual(T.state.cloth.refusal, null);
  same(T.state.boxes, [{label:'person', bbox:[9,9,99,99], origin:'manual', edited:false}]);
  same(T.state.polygon, [[0,0],[10,0],[10,10],[0,10]]);
  T.state.fresult = null; T.state.boxes = []; T.state.polygon = null;
});

test('a model box stays the model\'s until the operator edits that box', () => {
  // The owner-reported bug: one frame-level flag (`dirty || correction`) painted
  // every box YOURS as soon as anything on the frame was dirty, so boxes the
  // model's own inference had produced read as 人工. Provenance is per box.
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : selector === '#stage-note' ? note : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.overlay = {cloth:false, balls:false, persons:false, pockets:false, anchors:false, events:false};
  T.state.cloth.reference = null; T.state.unified = null; T.state.polygon = null;
  T.state.sel = {kind:'none', crop:null, ball:null, person:null, track:null, anchor:0, event:null, box:-1};
  T.state.fresult = {inference:{boxes:[{label:'ball', bbox:[10,10,30,30]}, {label:'ball', bbox:[40,40,60,60]}], table_polygon:null}, correction:null};
  T.applyFrameResult();
  T.state.dirty = true;                       // an unsaved edit somewhere on this frame
  T.paintOverlay();
  assert.strictEqual(svg.dataset.boxes, 'auto', 'a dirty frame does not make the model\'s boxes the operator\'s');
  assert.strictEqual((svg.innerHTML.match(/data-src="auto"/g) || []).length, 2, 'both boxes keep the model tag');
  assert.ok(svg.innerHTML.includes('>MODEL<') && !svg.innerHTML.includes('>YOURS<'), 'nothing reads YOURS yet');
  assert.strictEqual(T.state.drawn.balls, 2);
  assert.strictEqual(T.state.drawn.auto.balls, 2);
  assert.strictEqual(T.state.drawn.balls - T.state.drawn.auto.balls, 0, 'the facts split agrees: nothing manual');
  // The operator touches one box: that box is theirs, the other is still the model's.
  T.markBoxEdited(T.state.boxes[0]);
  T.paintOverlay();
  assert.strictEqual(svg.dataset.boxes, 'mixed', 'the frame carries both provenances');
  assert.strictEqual((svg.innerHTML.match(/data-src="manual"/g) || []).length, 1, 'one box is tagged YOURS');
  assert.strictEqual((svg.innerHTML.match(/data-src="auto"/g) || []).length, 1, 'the untouched one is still MODEL');
  assert.ok(svg.innerHTML.includes('>MODEL<') && svg.innerHTML.includes('>YOURS<'), 'the histogram shows both');
  assert.strictEqual(T.state.drawn.balls - T.state.drawn.auto.balls, 1, 'the facts split counts exactly one manual box');
  // A stored correction is the operator's; a stored inference is the model's.
  T.state.fresult = {inference:null, correction:{dataset:'vod30', frame_index:0, width:1280, height:720, boxes:[{label:'ball', bbox:[10,10,30,30]}]}};
  T.applyFrameResult(); T.paintOverlay();
  assert.strictEqual(T.boxTagKind(T.state.boxes[0]), 'manual', 'a stored correction is the operator\'s');
  T.state.fresult = {inference:{boxes:[{label:'ball', bbox:[10,10,30,30]}], table_polygon:null}, correction:null};
  T.applyFrameResult(); T.paintOverlay();
  assert.strictEqual(T.boxTagKind(T.state.boxes[0]), 'auto', 'a stored inference is the model\'s');
  assert.strictEqual(T.state.boxes[0].edited, false, 'a reloaded box does not inherit this session\'s edit');
  T.state.dirty = false; T.state.fresult = null; T.state.boxes = [];
});

test('every drawn group is tagged by source, in both languages', () => {
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : selector === '#stage-note' ? note : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.cloth.reference = null;
  T.state.overlay = {cloth:true, balls:true, persons:true, pockets:true, anchors:false, events:true};
  T.state.dirty = false;
  T.state.fresult = {correction:{dataset:'vod30', frame_index:0, width:1280, height:720, boxes:[{label:'person', bbox:[30,140,200,590]}, {label:'ball', bbox:[600,390,620,410]}], table_polygon:[[128,72],[1152,72],[1152,648],[128,648]]}};
  T.applyFrameResult();
  T.state.unified = {
    table_corners:[[190,176],[806,324],[1024,596],[384,566]],
    pockets:[{name:'head-left', cx:200, cy:180}, {name:'foot-right', cx:1000, cy:590}],
    persons:[{bbox:[30,140,200,590], track_id:12, cluster_id:68}],
    balls:[{cx:600, cy:400, r:12}], events:[{type:'pot', nearest_pocket:'foot-right (124mm)'}]
  };
  T.paintOverlay();
  const html = svg.innerHTML;
  assert.ok(html.includes('data-src="model"') && html.includes('data-src="manual"'), 'both sources are tagged');
  assert.ok(html.includes('>MODEL<') && html.includes('>YOURS<'), html.slice(0, 200));
  assert.ok(html.includes('unbound · track 12'), 'a clustered track without a player name says so');
  assert.ok(!/head-left|foot-right/.test(html), 'rail-corner vocabulary never reaches the stage');
  assert.ok(!html.includes('u-pocket'), 'pocket markers are held while the quad is unverified');
  assert.ok(!html.includes('data-anchor'), 'the anchors layer is off');
  assert.ok(note.textContent.includes('No saved corner set exists for this dataset'), note.textContent);
  assert.strictEqual(note.hidden, false);
  // 中: the same tags and the same vocabulary, translated.
  host.lang = 'zh';
  T.paintOverlay();
  assert.ok(svg.innerHTML.includes('>模型<') && svg.innerHTML.includes('>人工<'), 'tags are bilingual');
  assert.ok(svg.innerHTML.includes('未绑定 · 轨迹 12'), 'the chip is bilingual');
  assert.ok(note.textContent.includes('没有已保存的角点集'), note.textContent);
  host.lang = 'en';
  // A person detection with no cluster is still a person label, and a bound
  // player id is shown as the id alone.
  assert.strictEqual(T.personChip({bbox:[0,0,1,1], track_id:12}, 12), 'person · track 12');
  assert.strictEqual(T.personChip({cluster_id: 68, track_id:12}, 12), 'unbound · track 12');
  assert.strictEqual(T.personChip({player_id:'B', cluster_id: 70, track_id:3}, 3), 'B');
  // A checked quad paints the model outline and its pockets, still tagged.
  T.state.cloth.reference = {points:[[454.9,307.8],[799.5,319.4],[1023.8,573.1],[449.6,563.5]], source:'saved calibration', width:1280, height:720};
  T.state.unified.table_corners = [[455,308],[800,320],[1024,573],[450,564]];
  T.paintOverlay();
  assert.ok(svg.innerHTML.includes('u-cloth'), 'a checked quad is drawn');
  assert.ok(svg.innerHTML.includes('u-pocket'), 'pockets follow a checked quad');
  assert.ok(svg.innerHTML.includes('bottom-right'), 'the pocket marker is renamed in place');
  assert.strictEqual(note.hidden, true, 'no reason to show once the quad is checked');
  // A rejected quad paints nothing and says why.
  T.state.unified.table_corners = [[190,176],[806,324],[1024,596],[384,566]];
  T.paintOverlay();
  assert.ok(!svg.innerHTML.includes('u-cloth'), 'a rejected quad is not drawn');
  assert.ok(!svg.innerHTML.includes('u-pocket'), 'its pockets are not drawn');
  assert.ok(note.textContent.includes("off this dataset's saved corners (saved calibration, tolerance 40 px)"), note.textContent);
  T.state.unified = null; T.state.fresult = null; T.state.boxes = []; T.state.polygon = null; T.state.cloth.reference = null;
});

test('rail-corner keys are display-only and zhCopy is keyed by the slot it labels', () => {
  const zhBlock = source.slice(source.indexOf('const zhCopy'), source.indexOf('const editorCopy'));
  assert.ok(!/'(head|foot)-(left|right)'\s*:/.test(zhBlock), 'zhCopy must not key copy by pocket name');
  assert.ok(zhBlock.includes("'footer-left':'本地数据 · 显式保存'") && zhBlock.includes("'footer-right':'复核结论在核验前不是真值。'"));
  assert.ok(source.includes('pocketText(pk.name)'), 'stage pocket labels go through the display map');
  assert.ok(!source.includes('esc(pk.name)'), 'the raw pocket key is never printed');
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  assert.ok(adapter.includes('nearest_pocket_text'), 'the rail card shows the mapped name');
  assert.ok(!adapter.includes('esc(e.nearest_pocket)') && !adapter.includes('esc(item.nearest_pocket)'), 'the rail and inspector never print the raw key');
});

test('a foreign correction and a rejected quad are both stated on the stage', () => {
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : selector === '#stage-note' ? note : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.unified = null; T.state.fresult = null; T.state.boxes = []; T.state.polygon = null;
  T.state.cloth.reference = null;
  T.state.cloth.refusal = {ok:false, owner:'vod30 frame 12 @ 1920×1080', expected:'vod30 frame 0 @ 1280×720', detail:'width 1920 ≠ 1280'};
  T.paintOverlay();
  assert.strictEqual(note.hidden, false);
  assert.strictEqual(note.textContent, 'Saved correction belongs to vod30 frame 12 @ 1920×1080, not this frame (vod30 frame 0 @ 1280×720) — not drawn.');
  host.lang = 'zh';
  T.paintOverlay();
  assert.strictEqual(note.textContent, '已保存的修正属于 vod30 frame 12 @ 1920×1080，与当前帧（vod30 frame 0 @ 1280×720）不符——未绘制。');
  host.lang = 'en';
  T.state.cloth.refusal = null;
  // A quad that is off the dataset's saved corners: refused with the number.
  T.state.cloth.reference = {points:[[454.9,307.8],[799.5,319.4],[1023.8,573.1],[449.6,563.5]], source:'saved anchors', width:1280, height:720};
  T.state.unified = {table_corners:[[190,176],[806,324],[1024,596],[384,566]], pockets:[{name:'head-left', cx:200, cy:180}], persons:[], balls:[], events:[]};
  T.paintOverlay();
  assert.strictEqual(T.state.cloth.verdict.state, 'off');
  assert.match(note.textContent, /^The model table quad is \d+ px off this dataset's saved corners \(saved anchors, tolerance 40 px\) — not drawn\.$/);
  // A quad that is not a table quad at all: refused before any distance check.
  T.state.unified.table_corners = [[0,0],[2000,0],[2000,2000],[0,2000]];
  T.paintOverlay();
  assert.strictEqual(note.textContent, 'The model table quad is not a valid table quad for this frame (outside frame) — not drawn.');
  T.state.unified = null;
  T.paintOverlay();
  assert.strictEqual(note.hidden, true);
});

test('adapter facts line names the layers it held back', () => {
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const context = {window:{}, document:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}}, location:{hostname:'127.0.0.1'}};
  vm.createContext(context);
  vm.runInContext(adapter, context);
  const base = {
    source:{kind:'vod', label:'vod30', channel:null}, frame:{index:0, t:0, duration:1800, count:45000, playing:false, rate:0},
    loading:{overlay:false, since:0}, busy:false, live:{stale:false, seq:null, frame_age_ms:null, receive_to_result_ms:null},
    drawn:{cloth:0, balls:6, persons:4, pockets:0, anchors:0, events:0, auto:{cloth:0, balls:6, persons:4, pockets:0, anchors:0, events:0}},
    cloth:{verdict:{state:'off', mean:98.1, max:171.7, tolerance:40, source:'saved calibration'}, refusal:{ok:false, owner:'vod30 frame 12 @ 1920×1080', expected:'vod30 frame 0 @ 1280×720'}}
  };
  const facts = context.window.VisionStage.factsLine(base);
  assert.ok(facts.includes('pockets 0 (quad rejected)'), facts);
  assert.ok(facts.includes('model quad off saved corners 98 px (tol 40 px)'), facts);
  assert.ok(facts.includes('saved correction refused (vod30 frame 12 @ 1920×1080)'), facts);
  const unverified = context.window.VisionStage.factsLine({...base, drawn:{...base.drawn, cloth:1, auto:{...base.drawn.auto, cloth:1}}, cloth:{verdict:{state:'unverified'}, refusal:null}});
  assert.ok(unverified.includes('pockets 0 (unverified)') && unverified.includes('model quad unverified'), unverified);
  // Pockets drawn from the saved calibration say so, in the engine's own words.
  const offset = context.window.VisionStage.factsLine({...base, drawn:{...base.drawn, pockets:6}, cloth:{verdict:{state:'off', mean:95, tolerance:40}, pockets:{source:'calibration', count:6, reference:'saved anchors'}, refusal:null}});
  assert.ok(offset.includes('pockets 6 (saved anchors)'), offset);
  const clean = context.window.VisionStage.factsLine({...base, drawn:{...base.drawn, cloth:1, pockets:6, auto:{...base.drawn.auto, cloth:1, pockets:6}}, cloth:null});
  assert.ok(clean.includes('cloth 1') && clean.includes('pockets 6') && !clean.includes('quad'), clean);
});

test('a refused model quad falls back to the saved calibration for the pockets', () => {
  const anchors = {points:[[454.9,307.8],[799.5,319.4],[1023.8,573.1],[449.6,563.5],[448.4,402.9],[883.9,413.3]], source:'saved anchors', width:1280, height:720};
  same(T.POCKET_ANCHOR_ORDER, ['head-left','head-right','foot-right','foot-left','left-side','right-side']);
  same(T.calibratedPockets(anchors).map(p => p.name), T.POCKET_ANCHOR_ORDER);
  same(T.calibratedPockets(anchors).map(p => p.cx), [454.9, 799.5, 1023.8, 449.6, 448.4, 883.9]);
  assert.strictEqual(T.calibratedPockets({points:[[1,2],[3,4],[5,6],[7,8]], source:'saved anchors'}), null, 'a partial anchor set is not pocket geometry');
  assert.strictEqual(T.calibratedPockets(null), null);
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : selector === '#stage-note' ? note : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.fresult = null; T.state.boxes = []; T.state.polygon = null; T.state.cloth.refusal = null;
  T.state.overlay = {cloth:true, balls:true, persons:true, pockets:true, anchors:false, events:true};
  T.state.cloth.reference = anchors;
  // The per-frame model quad is 95 px off (measured on vod30 frame 0): refused,
  // but the pockets are drawn from the saved anchors instead of going dark.
  T.state.unified = {table_corners:[[190,176],[806,324],[1024,596],[384,566]], pockets:[{name:'head-left', cx:200, cy:180}, {name:'foot-right', cx:1000, cy:590}], persons:[], balls:[], events:[{type:'pot', nearest_pocket:'foot-right (124mm)'}]};
  T.paintOverlay();
  const html = svg.innerHTML;
  assert.strictEqual(T.state.cloth.verdict.state, 'off');
  assert.strictEqual(T.state.cloth.pockets.source, 'calibration');
  assert.strictEqual(T.state.cloth.pockets.reference, 'saved anchors');
  assert.strictEqual(T.state.drawn.pockets, 6);
  assert.strictEqual(T.state.drawn.events, 1, 'the pot pulse follows the trusted pockets');
  assert.ok(html.includes('data-src="calib"'), 'pocket markers are tagged as calibration-derived');
  assert.ok(!html.includes('data-src="model"'), 'no model tag for a quad that was refused (no cloth/ball/person drawn)');
  assert.ok(!/head-left|foot-right/.test(html), 'storage keys never reach the stage');
  assert.ok(html.includes('bottom-right') && html.includes('top-left'), 'pocket names are the display names');
  assert.ok(!html.includes('u-cloth'), 'the refused quad is still not drawn');
  assert.ok(html.includes('u-pot-pulse'), 'a pot at a trusted pocket still pulses');
  // The pot pulse sits on the CALIBRATION pocket, not on the refused quad's pocket.
  const pulse = Number(html.match(/u-pot-pulse" cx="([\d.]+)"/)[1]);
  assert.strictEqual(Math.round(pulse), 1024);
  assert.ok(html.includes('>CALIB<'));
  host.lang = 'zh';
  T.paintOverlay();
  assert.ok(svg.innerHTML.includes('>标定<') && svg.innerHTML.includes('右下'), 'the calibration tag and pocket names are bilingual');
  host.lang = 'en';
  // Live has no dataset calibration: nothing to borrow, nothing drawn.
  T.state.source = {kind:'live', label:'twitch', channel:'x'};
  T.paintOverlay();
  assert.strictEqual(T.state.cloth.pockets.source, null);
  assert.ok(!svg.innerHTML.includes('u-pocket'));
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  // A dataset without saved anchors keeps the held-back report.
  T.state.cloth.reference = null;
  T.paintOverlay();
  assert.strictEqual(T.state.cloth.pockets.source, null);
  assert.ok(!svg.innerHTML.includes('u-pocket'), 'no trusted pocket geometry: nothing is drawn');
  assert.ok(note.textContent.includes('No saved corner set exists for this dataset'), note.textContent);
  T.state.unified = null; T.state.cloth.reference = null;
});

test('a cold frame can start a correction without a devtools call', () => {
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const context = {window:{}, document:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}}, location:{hostname:'127.0.0.1'}};
  vm.createContext(context);
  vm.runInContext(adapter, context);
  const stage = context.window.VisionStage;
  // attach() only needs a host to bind to: the surface state is module-level.
  stage.attach({mount:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}}, lang:'en', review:{snapshot: () => null}, channels: () => [], regulars: () => [], chat: () => false});
  const base = {
    selection:{kind:'none', box:-1}, source:{kind:'vod', label:'vod30', channel:null}, datasets:[{id:'vod30', label:'vod30'}], set:'unlabeled_crops',
    frame:{count:54206, index:500}, live:{state:'idle', error:null, attempt:null, frame_age_ms:null, receive_to_result_ms:null, skipped:0, detectors:['table','person']},
    detectors:{table:true, person:true, balls:false}, corrections:{tool:'select', newBoxLabel:'ball', box:-1, boxLabel:null, polygon:false, result:'none', dirty:false, inferRunning:false, inferStatus:''},
    dirty:false, notice:{text:''}, receipts:[], persons:{tracks:[], track:null, windows:[], win:'', status:''}
  };
  const html = stage.inspectorHTML(base);
  for (const action of ['data-vs-action="add-polygon"', 'data-vs-action="run-inference"', 'data-vs-value="draw"']) assert.ok(html.includes(action), `a cold frame must offer ${action}`);
  assert.ok(html.includes('data-vs-action="tool"') && html.includes('data-vs-action="clear-polygon"'));
  assert.ok(!html.includes('data-vs-action="save-corrections"'), 'an untouched frame has nothing to save');
  assert.ok(stage.inspectorHTML({...base, dirty:true}).includes('data-vs-action="save-corrections"'), 'unsaved edits expose the existing save action');
  // The box block keeps its own copy of the same controls (inference stays in
  // the action footer for that block), and the person block stays identity-only.
  const box = stage.inspectorHTML({...base, selection:{kind:'box', box:0}});
  assert.ok(box.includes('data-vs-action="add-polygon"') && box.includes('data-vs-action="delete-box"'));
  assert.ok(adapter.includes('data-vs-action="run-inference"'), 'the box footer keeps run-inference');
  const person = stage.inspectorHTML({...base, selection:{kind:'person', track:3, person:{cluster_id:null}}});
  assert.ok(person.includes('Identity') && !person.includes('data-vs-action="add-polygon"'), 'the person block stays the identity block');
  assert.ok(!person.includes('data-vs-value="A"') && !person.includes('data-vs-value="B"'), 'the person block no longer offers the removed A/B seeds');
  assert.ok(adapter.includes('case \'identity-save\'') && adapter.includes('case \'identity-clear\''), 'the surface must act on both identity actions');
  // Every one of these buttons reaches a real engine entry point.
  for (const action of ['tool','add-polygon','clear-polygon','run-inference','save-corrections']) {
    assert.ok(adapter.includes(`case '${action}'`), `the surface must act on ${action}`);
  }
  for (const api of ['setTool','addPolygon','clearPolygon','runInference','saveCorrections']) {
    assert.ok(typeof sandbox.window.CornerPocketReview[api] === 'function', `the engine must expose ${api}`);
  }
});

test('a refused quad states its reason on the stage, in both languages', () => {
  // The detector's codes (low_cloth_area ...) are a machine contract: the operator
  // gets a phrase, the affected-side count, and never a raw snake_case token.
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : selector === '#stage-note' ? note : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.fresult = null; T.state.boxes = []; T.state.polygon = null;
  T.state.cloth.reference = null; T.state.cloth.refusal = null;
  T.state.unified = {table_corners:null, pockets:[], persons:[], balls:[], events:[], table_quad:{
    state:'naive_fallback', reason:'low_cloth_area', confidence:0.0, source:'naive', verified_sides:2,
    sides:[{side:0, state:'unverified', reason:'low_cloth_area'}, {side:1, state:'verified'},
           {side:2, state:'unverified', reason:'low_cloth_area'}, {side:3, state:'verified'}],
    seed_file:'/tmp/out/pid_anchors_vod30.json'}};
  T.paintOverlay();
  assert.strictEqual(T.state.cloth.verdict.state, 'none', 'no quad was returned, so nothing is painted');
  assert.strictEqual(note.hidden, false, 'a silent absence is what this fixes');
  assert.ok(note.textContent.includes('Table quad refused: the cloth is hidden'), note.textContent);
  assert.ok(note.textContent.includes('(2/4 sides unverified: 1, 3)'), note.textContent);
  assert.ok(!/_/.test(note.textContent), 'no raw snake_case code reaches the operator');
  host.lang = 'zh';
  T.paintOverlay();
  assert.ok(note.textContent.includes('球桌四边形已拒绝：台面被遮挡'), note.textContent);
  assert.ok(note.textContent.includes('（未校验边 2/4：1, 3）'), note.textContent);
  host.lang = 'en';
  // An accepted quad keeps the plain stage: no refusal sentence, drift stays in the facts line.
  const anchors = [[532,323],[800,324],[997,569],[384,563]];
  T.state.cloth.reference = {points:anchors, source:'saved anchors', width:1280, height:720};
  T.state.unified.table_quad = {state:'refined', reason:null, confidence:0.8, source:'refined_saved_prior',
                                verified_sides:4, sides:[], seed_file:'/tmp/out/pid_anchors_vod30.json'};
  T.state.unified.table_corners = anchors;
  T.paintOverlay();
  assert.strictEqual(note.hidden, true);
  assert.strictEqual(T.quadReasonText('boundary_outside_band'), 'the rail edge sits outside the search band');
  assert.strictEqual(T.quadReasonText('a_new_code'), 'the detector reported "a new code"');
  T.state.unified = null;
});

test('the cloth count follows where the polygon came from', () => {
  // A stored correction is the operator's (manual); a stored inference polygon is
  // model-derived. Counting both as auto is why "cloth 2" never showed (+1 manual)
  // while the stage tagged one polygon YOURS.
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.unified = null; T.state.cloth.reference = null; T.state.boxes = []; T.state.dirty = false;
  const poly = [[100,100],[600,100],[600,400],[100,400]];
  T.state.polygon = poly;
  T.state.fresult = {correction:{table_polygon:poly, boxes:[]}, inference:null};
  T.paintOverlay();
  assert.strictEqual(T.polygonSource(), 'manual');
  assert.strictEqual(T.state.cloth.polygon, 'manual');
  assert.strictEqual(T.state.drawn.cloth, 1, 'one cloth polygon is on the stage in total');
  assert.strictEqual(T.state.drawn.auto.cloth, 0, 'a stored correction is not counted as auto');
  assert.strictEqual(T.state.drawn.cloth - T.state.drawn.auto.cloth, 1, 'the facts split sees one manual polygon');
  assert.ok(svg.innerHTML.includes('YOURS'), 'a stored correction is tagged as the operator\'s');
  T.state.fresult = {correction:null, inference:{table_polygon:poly, boxes:[]}};
  T.paintOverlay();
  assert.strictEqual(T.polygonSource(), 'inference');
  assert.strictEqual(T.state.drawn.auto.cloth, 1, 'a stored inference polygon is model-derived');
  assert.strictEqual(T.state.drawn.cloth - T.state.drawn.auto.cloth, 0, 'nothing manual to report');
  assert.ok(svg.innerHTML.includes('MODEL') && !svg.innerHTML.includes('YOURS'), 'tag matches the count');
  T.state.dirty = true;
  assert.strictEqual(T.polygonSource(), 'manual', 'an edited inference polygon becomes the operator\'s');
  T.state.dirty = false; T.state.polygon = null; T.state.fresult = null;
  assert.strictEqual(T.polygonSource(), null);
});

test('the facts line states a refused quad reason in both languages', () => {
  // Fix 1 end to end on the render side: table_quad.reason exists, so the facts
  // line says why there is no quad instead of an unexplained `cloth 0`.
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const context = {window:{}, document:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}}, location:{hostname:'127.0.0.1'}};
  vm.createContext(context);
  vm.runInContext(adapter, context);
  const V = context.window.VisionStage;
  // zh copy comes from the adapter's own opts (ops.js passes the shell language in),
  // so the bilingual assertions attach with lang:'zh' first and switch back.
  const mountStub = {querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}};
  V.attach({mount: mountStub, lang:'en'});
  const quad = {state:'naive_fallback', reason:'low_cloth_area', confidence:0.0, source:'naive', verified_sides:2,
                sides:[{side:0, state:'unverified', reason:'low_cloth_area'}, {side:1, state:'verified'},
                       {side:2, state:'unverified', reason:'low_cloth_area'}, {side:3, state:'verified'}],
                seed_file:'/tmp/out/pid_anchors_vod30.json'};
  const base = {
    source:{kind:'vod', label:'vod30', channel:null}, frame:{index:8100, t:270, duration:1800, count:45000, playing:false, rate:0},
    loading:{overlay:false, since:0}, busy:false, live:{stale:false, seq:null, frame_age_ms:null, receive_to_result_ms:null},
    drawn:{cloth:0, balls:8, persons:4, pockets:0, anchors:0, events:1, auto:{cloth:0, balls:8, persons:4, pockets:0, anchors:0, events:1}},
    cloth:{verdict:{state:'none', reason:'no detection'}, quad, pockets:{source:null, count:0, reference:null}, reference:null}
  };
  const refused = V.factsLine(base);
  assert.ok(refused.includes('quad refused (the cloth is hidden'), 'A ' + refused);
  assert.ok(refused.includes('2/4 sides unverified: 1, 3'), 'B ' + refused);
  assert.ok(!/_/.test(refused.split('quad refused')[1].split(' · ')[0]), 'no snake_case code in the facts line');
  assert.ok(V.quadDetail(base).includes('reason: the cloth is hidden'), V.quadDetail(base));
  V.attach({mount: mountStub, lang:'zh'});
  const zh = V.factsLine(base);
  assert.ok(zh.includes('四边形已拒绝 (台面被遮挡'), 'Z1 ' + zh);
  assert.ok(zh.includes('未校验边 2/4：1, 3'), 'Z2 ' + zh);
  V.attach({mount: mountStub, lang:'en'});
  // A refusal with a drawn fallback quad says which quad the operator is looking at.
  const fallback = V.factsLine({...base, drawn:{...base.drawn, cloth:1, auto:{...base.drawn.auto, cloth:1}},
                                cloth:{...base.cloth, verdict:{state:'unverified', mean:null, tolerance:null}}});
  assert.ok(fallback.includes('quad from the naive fallback (the cloth is hidden'), 'F ' + fallback);
  // An accepted, fully verified quad keeps the drift line and grows no refusal.
  const ok = V.factsLine({...base, drawn:{...base.drawn, cloth:1, auto:{...base.drawn.auto, cloth:1}},
                          cloth:{...base.cloth, quad:{...quad, state:'refined', reason:null, verified_sides:4, sides:[]},
                                 verdict:{state:'ok', reason:'within tolerance', mean:5.7, tolerance:40, source:'saved anchors'}}});
  assert.ok(ok.includes('table outline matches the saved corners (5.7 px · tol 40 px)'), 'O ' + ok);
  assert.ok(!ok.includes('refused') && !ok.includes('fallback'), 'O2 ' + ok);
  // The stored-inference polygon names itself instead of hiding inside the total.
  const inference = V.factsLine({...base, cloth:{...base.cloth, polygon:'inference', quad:null, verdict:{state:'none'}},
                                 drawn:{cloth:1, balls:0, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:1, balls:0, persons:0, pockets:0, anchors:0, events:0}}});
  // "stored inference" is reserved for a file an earlier run wrote; a polygon from
  // inference run on this frame now is this session's, and says so.
  assert.ok(inference.includes('cloth 1 (inference · this session)'), 'I ' + inference);
  assert.ok(!inference.includes('stored inference'), 'I2 a session run is never called stored: ' + inference);
  const stored = V.factsLine({...base, cloth:{...base.cloth, polygon:'inference', quad:null, verdict:{state:'none'}},
                              corrections:{tool:'select', result:'inference', storedInference:true, inferenceAt:'2026-09-16T04:07:48+00:00'},
                              drawn:{cloth:1, balls:0, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:1, balls:0, persons:0, pockets:0, anchors:0, events:0}}});
  assert.ok(stored.includes('cloth 1 (stored inference') && /2026|9\/16/.test(stored),
    'I3 a file from an earlier run keeps its own timestamp: ' + stored);
  assert.ok(V.factsLine({...base, cloth:{...base.cloth, polygon:'manual', quad:null, verdict:{state:'none'}},
                         drawn:{cloth:2, balls:0, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:1, balls:0, persons:0, pockets:0, anchors:0, events:0}}}).includes('cloth 1 (+1 manual)'), 'M');
});

test('the stage is one video with the overlay on top of it', () => {
  T.state.shotUrl = null;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  const html = T.stageHTML();
  assert.strictEqual((html.match(/<video/g) || []).length, 1, 'exactly one stage video surface');
  assert.ok(html.includes('id="t-video"') && html.includes('id="t-img"'), 'video and the frozen still share the stage');
  assert.ok(html.indexOf('id="t-video"') < html.indexOf('id="t-overlay"'), 'the overlay SVG is painted over the video');
  assert.ok(html.includes('id="stage-play"'), 'the playback state chip exists');
  const css = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'app.css'), 'utf8');
  for (const needle of ['.stage > video', '.stage > video[hidden]', '.stage > svg', '.u-cue-line', '.u-cue-pocket', '.u-cue-head']) {
    assert.ok(css.includes(needle), `missing stage video css: ${needle}`);
  }
  // The inspector holds no picture at all: the stage is the one surface for a
  // cue, and it already freezes into the still when the window cannot play.
  const adapter = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  assert.ok(!/<video/.test(adapter), 'the inspector video element is gone');
  assert.ok(!adapter.includes('/api/clip'), 'the inspector no longer fetches a raw clip');
  assert.ok(adapter.includes('data-vs-action="play-event"'), 'the cue plays in the stage instead');
  assert.ok(!adapter.includes('vs-evidence'), 'the inspector keeps no second picture surface either');
});

test('the Vision tab renders one picture surface for the selected cue', () => {
  // A cue click used to paint a second still in the inspector next to a moving
  // stage; two pictures of the same moment read as one stale picture. The
  // inspector now carries no picture at all, and the rail cards carry none:
  // every cue-shaped selection has exactly the stage.
  const VS = adapterStage('en');
  const item = {id:1046, type:'shot', t:484.1, color:'blue', from_px:[100, 200], to_px:[300, 400], disp_mm:727,
                speed_mm_s:47.75, window_s:[482.6, 486.6], px_source:'scan cloth quad', projectable:true, tier:'geometry',
                annotation:{verdict:'correct', shooter:'A', note:'checked'}};
  const snapshot = visionSnapshot({
    dataset:'vod30', focus:'events', eventFilter:'all', verdictDraft:null,
    selection:{kind:'event', event:item, box:-1},
    events:{items:[item], index:0, reviewed:1},
    balls:{items:[], index:0, set:'unlabeled_crops', labels:{}},
  });
  const inspector = VS.inspectorHTML(snapshot);
  assert.ok(!/<img|<video/.test(inspector), 'the inspector block for a cue holds no picture at all');
  assert.ok(inspector.includes('data-vs-action="play-event"'), 'the cue still offers the stage playback');
  assert.ok(inspector.includes('The clip plays in the stage with its overlay'), 'the note explaining the one surface stays');
  assert.ok(inspector.includes('#1046') && inspector.includes('Detected geometry') && inspector.includes('Verdict') && inspector.includes('Correct'),
    'the id, geometry and verdict stay in the block that lost its picture');
  const rail = VS.railHTML(snapshot);
  assert.ok(!/<img|<video/.test(rail), 'the cues rail carries no per-cue thumbnail picture');
  assert.ok(rail.includes('data-vs-action="select-event"') && rail.includes('tier-geometry'), 'the rail card keeps its pick action and tier badge');
  // The stage markup holds the playing video and the frozen still; renderStage
  // shows exactly one of them, so the tab never has two live pictures.
  T.state.shotUrl = null;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  const stage = T.stageHTML();
  assert.strictEqual((stage.match(/<video/g) || []).length, 1, 'one stage video');
  assert.strictEqual((stage.match(/<img/g) || []).length, 1, 'one stage still');
  const app = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'app.js'), 'utf8');
  assert.ok(app.includes('videoShown = playing && !!stageVideo() && videoReady(video);'), 'the video needs a playable window');
  assert.ok(app.includes('const showStill = !!state.shotUrl && !videoShown;'), 'the still is the same one surface, shown when the video cannot play');
});

test('an event window is t - 1.5s to t + 2.5s, clamped to the video', () => {
  assert.strictEqual(T.CLIP_BEFORE_S, 1.5, 'the same before the /api/clip endpoint defaults to');
  assert.strictEqual(T.CLIP_AFTER_S, 2.5, 'the same after the /api/clip endpoint defaults to');
  T.state.vmeta = {dataset:'vod30', fps:30, frame_count:54206, duration:1806.8, width:1280, height:720};
  same(T.eventWindow({t: 100}), {from: 98.5, to: 102.5, before: 1.5, after: 2.5});
  same(T.eventWindow({t: 0.5}), {from: 0, to: 3, before: 1.5, after: 2.5}, 'never before the start of the video');
  assert.strictEqual(T.eventWindow({t: 1806}).to, 1806.8, 'never past the end of the video');
});

test('the stage video loops inside the event window it was given', () => {
  const video = {dataset:{}, currentTime:0, readyState:1, paused:true, played:0, attrs:{},
                 getAttribute(name) { return this.attrs[name] ?? null; }, setAttribute(name, value) { this.attrs[name] = value; },
                 load() {}, pause() { this.paused = true; }, play() { this.paused = false; this.played++; return Promise.resolve(); }};
  const host = {lang:'en', querySelector: selector => selector === '#t-video' ? video : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.vmeta = {dataset:'vod30', fps:30, frame_count:54206, duration:1806.8, width:1280, height:720};
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.events = [{id: 4, t: 100, type:'pot', last_mm:[1,2], last_px:[3,4], pocket_name:'foot-right', pocket_px:[5,6], px_source:'scan cloth quad', window_s:[99,103]}];
  T.state.annotations = {};
  T.bindVideo(video);
  assert.strictEqual(T.stageVideo(), video, 'the real video element is the stage video');
  assert.strictEqual(T.playEvent(0), true);
  assert.strictEqual(video.attrs.src, '/media/vod30/video', 'the stage plays the dataset video, not a pre-rendered clip');
  assert.strictEqual(video.currentTime, 98.5, 'it seeks to t - before');
  assert.strictEqual(video.played, 1, 'and plays');
  same([T.state.playback.from, T.state.playback.to], [98.5, 102.5]);
  // Past the end of the window it wraps to the start and counts the loop.
  video.currentTime = 102.6;
  video.ontimeupdate();
  assert.strictEqual(video.currentTime, 98.5, 'the window loops instead of running past it');
  assert.strictEqual(T.state.playback.loops, 1);
  video.currentTime = 100.2;
  video.ontimeupdate();
  assert.strictEqual(video.currentTime, 100.2, 'inside the window nothing is rewound');
  assert.strictEqual(T.state.frame, 3006, 'the strip follows the playing picture');
  // Freezing leaves video mode: the picture pauses and the still path takes over.
  T.exitPlayback();
  assert.strictEqual(T.state.playback.on, false);
  assert.strictEqual(video.paused, true, 'freezing pauses the video');
  T.state.vmeta = null; T.state.events = [];
});

test('playing drops per-frame detections and never paints a stale mark', () => {
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.t = 5; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.overlay = {cloth:true, balls:true, persons:true, pockets:true, anchors:false, events:true};
  T.state.cloth.reference = {points:[[454.9,307.8],[799.5,319.4],[1023.8,573.1],[449.6,563.5],[480,397],[865,398]], source:'saved anchors', width:1280, height:720};
  T.state.unified = {
    table_corners:[[455,308],[800,320],[1024,573],[450,564]],
    pockets:[{name:'head-left', cx:459, cy:269}, {name:'foot-right', cx:1024, cy:573}],
    persons:[{bbox:[30,140,200,590], track_id:12}], balls:[{cx:600, cy:400, r:12}], events:[]
  };
  T.state.fresult = {inference:{boxes:[{label:'ball', bbox:[600,390,620,410]}], table_polygon:null}, correction:null};
  T.state.sel = {kind:'none', crop:null, ball:null, person:null, track:null, anchor:0, event:null, box:-1};
  T.applyFrameResult();
  T.exitPlayback();
  T.paintOverlay();
  assert.ok(svg.innerHTML.includes('u-ball') && svg.innerHTML.includes('u-person'), 'a frozen frame draws its detections');
  assert.ok(svg.innerHTML.includes('t-box'), 'and its editable boxes');
  assert.strictEqual(T.state.drawn.perFrame, 1);
  // The video runs: the painter must clear them rather than leave them behind.
  T.state.playback = {on:true, playing:true, event:null, from:0, to:0, loops:0, seek:NaN};
  T.paintOverlay();
  assert.ok(!svg.innerHTML.includes('u-ball'), 'no stale ball marker while the video plays');
  assert.ok(!svg.innerHTML.includes('u-person'), 'no stale person box while the video plays');
  assert.ok(!svg.innerHTML.includes('t-box'), 'no stale editable box while the video plays');
  assert.ok(svg.innerHTML.includes('u-cloth') && svg.innerHTML.includes('u-pocket'), 'the static layers stay drawn');
  assert.ok(svg.innerHTML.includes('>CALIB<'), 'and say they are calibration, not a detection');
  assert.strictEqual(T.state.drawn.perFrame, 0);
  // Playback drops the state itself, so a later paint cannot resurrect it.
  T.state.unified = {balls:[{cx:1, cy:1, r:9}]}; T.state.boxes = [{label:'ball', bbox:[1,1,9,9]}];
  T.dropPerFrame();
  assert.strictEqual(T.state.unified, null);
  assert.strictEqual(T.state.fresult, null);
  assert.strictEqual(T.state.boxes.length, 0);
  assert.strictEqual(T.state.dirty, false);
  T.exitPlayback();
});

test('the selected cue draws its own projected geometry, or says it cannot', () => {
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.overlay = {cloth:false, balls:false, persons:false, pockets:false, anchors:false, events:true};
  T.state.unified = null; T.state.fresult = null; T.state.boxes = [];
  T.state.cloth.reference = {points:[[532,323],[800,324],[997,569],[384,563],[480,397],[865,398]], source:'saved anchors', width:1280, height:720};
  T.state.playback = {on:true, playing:true, event:null, from:0, to:0, loops:0, seek:NaN};
  const pot = {id: 1, type:'pot', t: 5.6, color:'blue', last_mm:[1146.2,2547.9], last_px:[965.4,605.0],
               pocket_name:'foot-right', pocket_px:[1021.1,608.2], nearest_pocket:'foot-right (124mm)', px_source:'measured ball correspondences'};
  T.state.sel = {kind:'event', event: pot, crop:null, ball:null, person:null, track:null, anchor:0, box:-1};
  T.state.playback = {on:true, playing:true, event: pot, from:4.1, to:8.2, loops:0, seek:NaN};
  T.paintOverlay();
  assert.ok(svg.innerHTML.includes('u-cue-ball') && svg.innerHTML.includes('u-cue-pocket'), 'the ball and its pocket are marked');
  assert.ok(svg.innerHTML.includes('u-cue-line'), 'and a line joins them');
  assert.ok(svg.innerHTML.includes('blue → bottom-right (124mm)'), 'labelled with the colour and the distance');
  assert.ok(svg.innerHTML.includes('>EVENT<'), 'tagged as the event geometry, not a detection');
  // The highlight lands on the pocket the stage actually draws when it has one.
  same(T.drawnPocket('foot-right', pot), [997, 569]);
  // A shot draws the direction, the displacement and the speed.
  const shot = {id: 2, type:'shot', t: 6.0, color:null, disp_mm:172, speed_m_s:2.6, speed_mm_s:2600,
                from_px:[463.2,284.8], to_px:[600,400], px_source:'measured ball correspondences'};
  T.state.sel = {kind:'event', event: shot, crop:null, ball:null, person:null, track:null, anchor:0, box:-1};
  T.state.playback = {on:true, playing:true, event: shot, from:4.5, to:8.5, loops:0, seek:NaN};
  T.paintOverlay();
  assert.ok(svg.innerHTML.includes('u-cue-head'), 'the shot arrow has a head');
  assert.ok(svg.innerHTML.includes('172 mm · 2600 mm/s'), 'shot labels carry both numbers');
  // A cue the scan has no colour for leaves it out instead of printing "unknown".
  T.state.sel = {kind:'event', event: {...shot, color:'blue'}, crop:null, ball:null, person:null, track:null, anchor:0, box:-1};
  assert.ok(T.paintCueGeometry({...shot, color:'blue'}).markup.includes('blue · 172 mm'), 'a known colour is named');
  // An event the dataset cannot project draws no geometry at all.
  const raw = {id: 3, type:'pot', t: 9.4, last_mm:[1287.7,2526.4], nearest_pocket:'foot-right (22mm)'};
  assert.strictEqual(T.cueGeometryVisible(raw), false);
  assert.strictEqual(T.paintCueGeometry(raw), null);
  T.state.sel = {kind:'event', event: raw, crop:null, ball:null, person:null, track:null, anchor:0, box:-1};
  T.state.playback = {on:true, playing:true, event: raw, from:7.9, to:11.9, loops:0, seek:NaN};
  T.paintOverlay();
  assert.ok(!svg.innerHTML.includes('u-cue-ball') && !svg.innerHTML.includes('u-cue-line'), 'nothing is invented for it');
  T.exitPlayback();
});

test('the snapshot carries the event geometry and the playback window', () => {
  const review = sandbox.window.CornerPocketReview;
  T.state.dataset = 'vod30';
  T.state.events = [{id: 1, type:'pot', t: 5.6, nearest_pocket:'foot-right (124mm)', last_mm:[1146.2,2547.9],
                     last_px:[965.4,605.0], pocket_name:'foot-right', pocket_px:[1021.1,608.2], px_source:'measured ball correspondences', color:'blue'}];
  T.state.annotations = {};
  T.exitPlayback();
  const snap = review.snapshot();
  const item = snap.events.items[0];
  assert.strictEqual(item.last_px[0], 965.4, 'the projected pixels reach the shell');
  assert.strictEqual(item.pocket_name, 'foot-right');
  assert.strictEqual(item.px_source, 'measured ball correspondences');
  assert.strictEqual(item.projectable, true);
  assert.strictEqual(item.nearest_pocket_text, 'bottom-right (124mm)', 'and the label stays a position word');
  assert.strictEqual(snap.playback.on, false);
  T.state.playback = {on:true, playing:true, event:{id:1}, from:4.1, to:8.1, loops:2, seek:NaN};
  const playing = review.snapshot();
  assert.strictEqual(playing.playback.on, true);
  assert.strictEqual(playing.playback.loops, 2);
  assert.strictEqual(playing.playback.event, 1);
  assert.strictEqual(playing.frame.video, true);
  T.exitPlayback(); T.state.events = [];
});

test('the cue card and the inspector show the numbers behind a detection gate', () => {
  // The gate block the eval tool writes carries the numbers a human verdict
  // needs: census before -> after, the vanished ball's distance to its pocket,
  // the re-measured move. Loading the adapter standalone proves the formatting
  // without a browser.
  const adapterSource = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const box = {window:{}, document:{querySelector: () => null, querySelectorAll: () => []}, URL:{},
               fetch: () => Promise.reject(new Error('no network in tests')), setTimeout, clearTimeout,
               console, Math, Number, Object, JSON, Date};
  box.globalThis = box;
  vm.createContext(box);
  vm.runInContext(adapterSource, box, {filename:'vision-stage.js'});
  const VS = box.window.VisionStage;
  const pot = {id:1, type:'pot', t:5.6, color:'blue', dup_count:3,
               gate:{status:'rejected', gate:'census', reasons:['census_recovered'],
                     numbers:{census_pre:3, census_post:2, color_census_pre:2, color_census_post:1,
                              vanish_dist_mm:60, vanish_pocket:'foot-right', motion_max:1.82}}};
  const shot = {id:16, type:'shot', t:82.5, color:'white', dup_count:1,
                gate:{status:'confirmed', gate:'displacement',
                      reasons:['displacement_corroborated', 'geometry_mismatch'],
                      numbers:{disp_mm:777, disp_color:'white', window_motion:16.85, geometry_gap_px:386.5}}};
  // Without an engine the adapter prints the stored pocket key; with one (below), the position word.
  same(VS.gateEvidence(pot), ['3→2', '60 mm · foot-right', '×3']);
  same(VS.gateEvidence(shot), ['777 mm white', 'motion 16.85']);
  same(VS.gateEvidence({id:3, type:'pot'}), []);          // no gate block: no invented numbers
  const potFacts = VS.eventGeometry(pot);
  assert.ok(potFacts.includes('Ball census') && potFacts.includes('3 → 2'), 'the census reaches the inspector');
  assert.ok(potFacts.includes('Vanished ball') && potFacts.includes('60 mm · foot-right'), 'so does the pocket distance');
  assert.ok(potFacts.includes('rejected · census') && potFacts.includes('census_recovered'), 'and why the gate failed');
  assert.ok(potFacts.includes('Duplicate detections merged'), 'and how many repeats were merged');
  const shotFacts = VS.eventGeometry(shot);
  assert.ok(shotFacts.includes('Re-measured move') && shotFacts.includes('777 mm · white'), 'the re-measured move reaches the inspector');
  assert.ok(shotFacts.includes('387 px'), 'so does the claim-vs-measured gap');
  const zh = adapterSource.match(/\n  zh: \{[\s\S]*?\n  \}/)[0];
  for (const key of ['gateCheck', 'gateConfirmed', 'gateRejected', 'gateCensus', 'gateVanish', 'gateMove'])
    assert.ok(new RegExp(`${key}:'[^']*[\\u4e00-\\u9fff]`).test(zh), `${key} is translated in 中`);
  assert.ok(adapterSource.includes('gateEvidence(e)'), 'the cue rail renders the gate numbers on the card');
});

test('the confirmation tier is badged on the card and in the inspector, in both languages', () => {
  const adapterSource = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const box = {window:{}, document:{querySelector: () => null, querySelectorAll: () => []}, URL:{},
               fetch: () => Promise.reject(new Error('no network in tests')), setTimeout, clearTimeout,
               console, Math, Number, Object, JSON, Date};
  box.globalThis = box;
  vm.createContext(box);
  vm.runInContext(adapterSource, box, {filename:'vision-stage.js'});
  const VS = box.window.VisionStage;
  const geometry = VS.tierBadge({tier:'geometry'});
  const window_ = VS.tierBadge({tier:'window'});
  assert.ok(geometry.includes('geometry-verified') && geometry.includes('data-vs-tier="geometry"'), 'the solid tier is badged');
  assert.ok(window_.includes('motion window only') && window_.includes('data-vs-tier="window"'), 'the window tier is badged');
  assert.ok(geometry.includes('vs-badge tier-geometry') && window_.includes('vs-badge tier-window'),
    'the two tiers carry different classes, so the rail can tell them apart at a glance');
  assert.strictEqual(VS.tierBadge({id:9, type:'shot'}), '', 'an event with no tier is never badged as verified');
  const shot = {id:1011, type:'shot', t:1799.1, color:'white', tier:'window',
                gate:{status:'confirmed', gate:'displacement', reasons:['displacement_corroborated','geometry_mismatch'],
                      numbers:{disp_mm:318, disp_color:'white', geometry_gap_px:263.2, calibration_frac:0.351}},
                geometry_check:{matches:false, gap_px:263.2, tol_px:60}};
  const facts = VS.eventGeometry(shot);
  assert.ok(facts.includes('Confirmation tier') && facts.includes('motion window only'),
    'the tier survives into the inspector verdict block');
  const served = {id:28, type:'shot', t:483.4, color:'black', tier:'geometry',
                  gate:{status:'confirmed', gate:'displacement', reasons:['displacement_corroborated'],
                        numbers:{disp_mm:1837, disp_color:'black', geometry_gap_px:29}}};
  assert.ok(VS.eventGeometry(served).includes('geometry-verified'), 'and so does the geometry tier');
  const rail = VS.railHTML({eventFilter:'all', selection:{}, focus:'events', events:{items:[shot, served], index:0, reviewed:0},
                            balls:{items:[], index:0}, persons:{tracks:[], windows:[], win:null}, frame:{}, source:{}, live:{}});
  assert.ok(rail.includes('data-vs-tier="geometry"') && rail.includes('data-vs-tier="window"'),
    'the rail shows both tiers side by side');
  assert.ok(rail.includes('data-vs-value="geometry"') && rail.includes('data-vs-value="window"'),
    'and offers a filter for each tier');
  assert.ok(rail.match(/vs-card tier-window/), 'the card itself is marked with its tier');
  const zhTiers = adapterSource.match(/\n  zh: \{[\s\S]*?\n  \}/)[0];
  for (const key of ['tierGeometry', 'tierWindow', 'tierLabel', 'noPotsMeasured'])
    assert.ok(new RegExp(`${key}:'[^']*[\\u4e00-\\u9fff]`).test(zhTiers), `${key} is translated in 中`);
});

test('an emptied queue explains itself instead of showing a bare list', () => {
  const adapterSource = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const box = {window:{}, document:{querySelector: () => null, querySelectorAll: () => []}, URL:{},
               fetch: () => Promise.reject(new Error('no network in tests')), setTimeout, clearTimeout,
               console, Math, Number, Object, JSON, Date};
  box.globalThis = box;
  vm.createContext(box);
  vm.runInContext(adapterSource, box, {filename:'vision-stage.js'});
  const VS = box.window.VisionStage;
  const emptyQueue = {eventFilter:'all', selection:{}, focus:'events', events:{items:[], index:0, reviewed:0},
                      balls:{items:[], index:0}, persons:{tracks:[], windows:[], win:null}, frame:{}, source:{}, live:{}};
  const rail = VS.railHTML(emptyQueue);
  assert.ok(rail.includes('data-vs-empty="shots-measured-none"'), 'the empty queue is marked as measured-empty');
  assert.ok(rail.includes('No shot candidate survived measurement'), 'and says so');
  assert.ok(rail.includes('explained by occlusion'), 'naming the measured reason: occlusion');
  assert.ok(rail.includes('detection floor'), 'and the resolution limit behind it');
  assert.ok(rail.includes('report artifacts'), 'and where the events still live');
  assert.ok(!rail.includes('data-vs-action="select-event"'), 'no card is invented for an empty queue');
  assert.ok(!rail.includes('No event candidates in this filter.'), 'the bare copy is not used while the reason exists');
  const geometryFilter = VS.railHTML({...emptyQueue, eventFilter:'geometry'});
  assert.ok(geometryFilter.includes('data-vs-empty="shots-measured-none"'), 'a tier filter inherits the same reason');
  const pots = VS.railHTML({...emptyQueue, eventFilter:'pot'});
  assert.ok(pots.includes('data-vs-empty="pots-measured-none"') && pots.includes('No pot candidate in this VOD survived measurement'),
    'the pots tab keeps its own reason');
  const shot = {id:28, type:'shot', t:483.4, color:'black', tier:'geometry', gate:{status:'confirmed', gate:'displacement', numbers:{disp_mm:1837}}};
  const withEvent = VS.railHTML({...emptyQueue, events:{items:[shot], index:0, reviewed:0}});
  assert.ok(withEvent.includes('data-vs-value="geometry"') && withEvent.includes('data-vs-value="window"'),
    'with a tiered event the tier controls come back');
  const untiered = VS.railHTML({...emptyQueue, events:{items:[{...shot, tier:null}], index:0, reviewed:0}});
  assert.ok(!untiered.includes('data-vs-value="geometry"'), 'without a tiered event they are not offered');
  assert.ok(!untiered.includes('data-vs-tier='), 'and no badge is invented');
  const inspector = VS.inspectorHTML ? '' : '';
  const zhShots = adapterSource.match(/\n  zh: \{[\s\S]*?\n  \}/)[0];
  for (const key of ['noShotsMeasured', 'noPotsMeasured', 'tierGeometry', 'tierWindow'])
    assert.ok(new RegExp(`${key}:'[^']*[\\u4e00-\\u9fff]`).test(zhShots), `${key} is translated in 中`);
  assert.ok(/noShotsMeasured:'[^']*遮挡/.test(zhShots), 'the 中 reason names the occlusion');
});

test('the pots tab explains its empty state instead of showing a bare list', () => {
  const adapterSource = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  const box = {window:{}, document:{querySelector: () => null, querySelectorAll: () => []}, URL:{},
               fetch: () => Promise.reject(new Error('no network in tests')), setTimeout, clearTimeout,
               console, Math, Number, Object, JSON, Date};
  box.globalThis = box;
  vm.createContext(box);
  vm.runInContext(adapterSource, box, {filename:'vision-stage.js'});
  const VS = box.window.VisionStage;
  const shot = {id:28, type:'shot', t:483.4, color:'black', tier:'geometry', gate:{status:'confirmed', gate:'displacement', numbers:{disp_mm:1837}}};
  const rail = VS.railHTML({eventFilter:'pot', selection:{}, focus:'events', events:{items:[shot], index:0, reviewed:0},
                            balls:{items:[], index:0}, persons:{tracks:[], windows:[], win:null}, frame:{}, source:{}, live:{}});
  assert.ok(rail.includes('data-vs-empty="pots-measured-none"'), 'the empty pots list is marked as measured-empty');
  assert.ok(rail.includes('No pot candidate in this VOD survived measurement'), 'and names why: no candidate survived measurement');
  assert.ok(rail.includes('the ball census refuted every claim'), 'with the refuting gate named');
  assert.ok(!rail.includes('data-vs-action="select-event"'), 'no shot is smuggled into the pots tab');
  const empty = VS.railHTML({eventFilter:'all', selection:{}, focus:'events', events:{items:[], index:0, reviewed:0},
                             balls:{items:[], index:0}, persons:{tracks:[], windows:[], win:null}, frame:{}, source:{}, live:{}});
  assert.ok(empty.includes('data-vs-empty="shots-measured-none"'), 'an empty queue gets the shot reason, not the pot one');
  assert.ok(!empty.includes('No pot candidate'), 'the pot reason never leaks onto the shots filter');
  assert.ok(source.includes('tier: e.tier') && source.includes('geometry_check:'),
    'app.js passes the tier and the geometry check through to the rail');
});

// ---- identity labelling + source panel (owner request, 2026-09-23) --------
// The adapter under test: loaded once per language with a stub host, so the
// blocks can be rendered without a browser or a live engine.
function adapterStage(lang, roster, extra) {
  const adapterSource = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
  // setInterval is a no-op: a full render starts the receipt-age ticker, which would
  // otherwise keep this test process alive.
  const box = {window:{}, document:{querySelector: () => null, querySelectorAll: () => []},
               location:{hostname:'127.0.0.1'}, URL:{}, fetch: () => Promise.reject(new Error('no network in tests')),
               setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {}, console, Math, Number, Object, JSON, Date};
  box.globalThis = box;
  vm.createContext(box);
  vm.runInContext(adapterSource, box, {filename:'vision-stage.js'});
  const VS = box.window.VisionStage;
  VS.attach({mount:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}},
             lang, review:{snapshot: () => null}, channels: () => [], regulars: () => roster || [], chat: () => false, ...(extra || {})});
  return VS;
}
// The smallest snapshot the identity block and the chip row read.
function visionSnapshot(over = {}) {
  return {
    selection:{kind:'none', box:-1}, source:{kind:'vod', label:'vod30 · 1800 s', channel:null},
    datasets:[{id:'vod30', label:'vod30'}], set:'unlabeled_crops', frame:{index:500, t:20, duration:1800, count:54206, playing:false},
    live:{state:'idle', error:null, attempt:null, frame_age_ms:null, receive_to_result_ms:null, skipped:0, detectors:['table','person'], stale:false, seq:null},
    detectors:{table:true, person:true, balls:false},
    corrections:{tool:'select', newBoxLabel:'ball', box:-1, boxLabel:null, polygon:false, result:'none', dirty:false, inferRunning:false, inferStatus:''},
    dirty:false, notice:{text:''}, receipts:[], busy:false, loading:{overlay:false, since:0}, overlay:{}, drawn:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0},
    cloth:{verdict:{state:'none'}, quad:null, pockets:{}, refusal:null},
    persons:{tracks:[], track:null, windows:[{win:'68-94', count:3}], win:'68-94', status:'', predictions:null},
    ...over
  };
}
const ADAPTER_SOURCE = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8');
const ROSTER = [{id:'p1', name:'Ana', rating:78, status:'Active', statusText:'Active'},
                {id:'p2', name:'Bo', rating:52, status:'Visitor', statusText:'Visitor'}];

test('a person track is labelled as one regular or one guest name, and Save hits the matching endpoint', () => {
  const VS = adapterStage('en', ROSTER);
  const person = visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null, player_id:null, bound_evidence:null}}});
  const block = VS.inspectorHTML(person);
  assert.ok(block.includes('Which regular?') && block.includes('data-vs-action="regular"'), 'option 1: the roster dropdown');
  assert.ok(block.includes('Guest name') && block.includes('data-vs-action="guest-name"'), 'option 2: the guest textbox');
  assert.ok(block.includes('— not a regular (guest) —'), 'the guest option is explicit, not an empty label');
  assert.ok(block.includes('Ana · 78') && block.includes('Bo · 52 · Visitor'), 'the roster carries name + rating (+ status when not Active)');
  assert.ok(block.includes('data-vs-binding="none"') && block.includes('no label yet'), 'an unlabelled track says so honestly');
  assert.ok(!block.includes('data-vs-value="A"') && !block.includes('data-vs-action="bind-regular"'), 'the removed A/B buttons are gone');
  const footer = VS.actionsHTML(person);
  assert.ok(footer.includes('data-vs-action="identity-save"') && footer.includes('data-vs-action="identity-clear"'), 'Save and Clear are the only writes');
  assert.ok(!footer.includes('data-vs-value="A"') && !footer.includes('data-vs-value="B"') && !footer.includes('data-vs-value="clear"'), 'the footer keeps no legacy seed buttons');
  // Which path each choice takes, pinned at the call site and in the engine.
  assert.ok(ADAPTER_SOURCE.includes('if (picked) target.seedIdentity(node, picked);'), 'a picked regular calls seedIdentity');
  assert.ok(/find\(x => String\(x\.id\) === String\(s\.persons\.track\)\)\?\.seed/.test(ADAPTER_SOURCE),
    'the inspector signature carries the selected track seed, so a save repaints the block that saved it');
  assert.ok(ADAPTER_SOURCE.includes('else { guestDraft = null; target.setSeed(node, name); }'), 'a typed name calls setSeed');
  assert.ok(source.includes("save(button, '/api/identity/seed', {cluster_id: person.cluster_id, player_id: playerId}"), 'the regular path posts /api/identity/seed with the player id');
  assert.ok(source.includes("return save(button, '/api/vod30/seeds', body"), 'the guest path posts /api/vod30/seeds with the typed name');
  assert.ok(source.includes("save(button, '/api/identity/unbind', {cluster_id: person.cluster_id}"), 'Clear unbinds through /api/identity/unbind');
  // The idle guest box and the disabled guest box are the same control.
  assert.ok(VS.syncGuestField('p1') === undefined && ADAPTER_SOURCE.includes("input.disabled = off"), 'picking a regular turns the guest box off, not away');
  // A regular with a cluster states what Save will do; without one it says why not.
  const bound = visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:7, player_id:'p1', bound_evidence:{source:'explicit_assign'}}},
                                persons:{tracks:[{id:2, seed:null}], track:2, windows:[], win:'68-94', status:'', predictions:null}});
  const boundBlock = VS.inspectorHTML(bound);
  assert.ok(boundBlock.includes('data-vs-binding="regular"') && boundBlock.includes('Ana · manual bind'), 'an explicit pick reads as a manual bind');
  assert.ok(boundBlock.includes('value="p1" selected'), 'the dropdown preselects the bound regular');
  assert.ok(boundBlock.includes('Saves through the identity pipeline'), 'and the hint names the pipeline');
  assert.ok(VS.inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null, player_id:null}}})).includes('Saves the typed name'), 'with no cluster the guest path is the one described');
  // The automatic match is named as such, never as the operator's pick.
  const auto = visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:7, player_id:'p1', bound_evidence:{source:'bind_face'}}},
                               persons:{tracks:[{id:2, seed:null}], track:2, windows:[], win:'68-94', status:'', predictions:{map:{'2:68-94':'B'}, detail:{}, stale:false}}});
  const autoBlock = VS.inspectorHTML(auto);
  assert.ok(autoBlock.includes('automatic face match') && autoBlock.includes('prediction B'), 'an automatic match says it is one, next to the stored prediction');
  assert.ok(!autoBlock.includes('manual bind'), 'an automatic match is never reported as a manual bind');
});

test('a legacy A/B seed still renders on the rail and in the identity block', () => {
  const VS = adapterStage('en', ROSTER);
  for (const [seed, text] of [['A','Player A'], ['B','Player B'], ['ignore','Ignore']]) {
    const s = visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null}},
                              persons:{tracks:[{id:2, seed}], track:2, windows:[], win:'68-94', status:'', predictions:null}});
    const block = VS.inspectorHTML(s);
    assert.ok(block.includes(`data-vs-binding="legacy-${seed}"`), `a stored ${seed} seed keeps its own binding state`);
    assert.ok(block.includes(text) && block.includes('legacy A/B seed'), `a stored ${seed} seed reads as ${text}, named as a legacy value`);
    const rail = VS.railHTML({eventFilter:'all', selection:{}, focus:'persons', events:{items:[], index:0, reviewed:0},
                              balls:{items:[], index:0}, persons:{tracks:[{id:2, seed}], windows:[], win:'68-94', track:null}, frame:{}, source:{}, live:{}});
    assert.ok(rail.includes(text), `the rail tag reads ${text}, not the raw ${seed}`);
  }
  // A guest name is a label too, and it is not shouted in upper case or read as a role.
  const guest = visionSnapshot({selection:{kind:'person', track:3, person:{track_id:3, cluster_id:null}},
                                persons:{tracks:[{id:3, seed:'Minh'}], track:3, windows:[], win:'68-94', status:'', predictions:null}});
  assert.ok(VS.inspectorHTML(guest).includes('data-vs-binding="guest"'), 'a typed name is stored and read as a guest label');
  const guestRail = VS.railHTML({eventFilter:'all', selection:{}, focus:'persons', events:{items:[], index:0, reviewed:0},
                                 balls:{items:[], index:0}, persons:{tracks:[{id:3, seed:'Minh'}], windows:[], win:'68-94', track:null}, frame:{}, source:{}, live:{}});
  assert.ok(guestRail.includes('>Minh<') && guestRail.includes('vs-tag done guest'), 'a guest name is not put in the legacy A/B uppercase style');
  // Nothing was removed from the pipeline's reach: the keyboard seeds still post
  // the three legacy values through the same endpoint the pipeline reads.
  assert.ok(source.includes("if (upper === 'A' || upper === 'B') { e.preventDefault(); setSeed(null, upper); return; }"), 'the legacy A/B keyboard seeds stay reachable');
  assert.ok(source.includes("role === 'clear' ? null : (typeof role === 'string' ? role.trim() : role)"), 'one seeds writer still carries clear, the role values and a guest name');
});

test('the source settings open from the Source chip and are no longer the rail empty state', () => {
  const VS = adapterStage('en', ROSTER);
  const base = visionSnapshot();
  const none = VS.inspectorHTML(base);
  assert.ok(none.includes('data-vs-empty="no-selection"'), 'the rail marks its nothing-selected state');
  assert.ok(none.includes('<h3>Nothing selected</h3>') && !none.includes('<h3>Inspector</h3>'), 'and heads it as such, not as the rail itself');
  assert.ok(none.includes('Select a cue, a ball, a person or an anchor to label it.'), 'and says what to select (EN)');
  assert.ok(none.includes('This frame') && none.includes('data-vs-action="add-polygon"') && none.includes('data-vs-action="run-inference"'), 'the frame tools stay, under their own heading');
  assert.ok(none.indexOf('This frame') > none.indexOf('data-vs-empty="no-selection"'), 'and are separated from the empty-state copy');
  for (const gone of ['data-vs-action="pick-dataset"', 'data-vs-action="live-start"', 'data-vs-action="live-stop"', 'data-vs-action="pick-live"',
                      'data-vs-action="detector"', 'id="vs-live-status"', 'id="source-form"', 'Twitch upstream delay']) {
    assert.ok(!none.includes(gone), `the rail's nothing-selected state no longer carries ${gone}`);
  }
  assert.ok(!VS.actionsHTML(base), 'and its footer carries no source action either');
  const closed = VS.chipsHTML(base);
  assert.ok(closed.includes('data-vs-action="source-panel"') && closed.includes('aria-expanded="false"'), 'the Source chip sits in the chip row, closed');
  assert.ok(!closed.includes('id="vs-source-panel"'), 'nothing is rendered until it is asked for');
  VS.act('source-panel');
  const open = VS.chipsHTML(base);
  assert.ok(open.includes('id="vs-source-panel"') && open.includes('aria-expanded="true"'), 'one click opens the settings panel');
  for (const kept of ['data-vs-action="pick-dataset"', 'data-vs-action="live-start"', 'data-vs-action="live-stop"', 'data-vs-action="pick-live"',
                      'data-vs-action="live-detector"', 'data-vs-action="detector"', 'id="vs-live-status"', 'id="source-form"',
                      'Twitch upstream delay', 'not glass-to-glass']) {
    assert.ok(open.includes(kept), `the panel keeps ${kept}`);
  }
  assert.ok(open.includes('data-vs-action="live-start"') && open.includes('data-vs-action="live-stop"'),
    'start/stop moved with the block instead of disappearing from the rail footer');
  assert.ok(VS.sourcePanelHTML(visionSnapshot({live:{state:'error', error:'no frames', attempt:{source:'twitch:abc', error:'no frames', at:1}, frame_age_ms:null, receive_to_result_ms:null, skipped:3, detectors:[]}}))
    .includes('Start attempt'), 'the refusal reason block still renders inside the panel');
  VS.act('source-panel');
  assert.ok(!VS.chipsHTML(base).includes('id="vs-source-panel"'), 'and the chip closes it again');
});

test('the rail empty state and the labelling copy render in 中 as well', () => {
  const zh = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'vision-stage.js'), 'utf8').match(/\n  zh: \{[\s\S]*?\n  \}/)[0];
  for (const key of ['railEmpty', 'noSelection', 'thisFrame', 'whichRegular', 'guestOption', 'guestName', 'saveBinding', 'clearBinding', 'notAPlayer',
                     'bindNone', 'bindLegacy', 'bindGuest', 'boundManual', 'boundAuto', 'bindIdentityHint', 'bindGuestHint', 'ignoreHint'])
    assert.ok(new RegExp(`${key}:'[^']*[\\u4e00-\\u9fff]`).test(zh), `${key} is translated in 中`);
  const VS = adapterStage('zh', ROSTER);
  const none = VS.inspectorHTML(visionSnapshot());
  assert.ok(none.includes('请先选择线索、球、人物或锚点，再进行标注。'), 'the rail empty state is Chinese');
  assert.ok(none.includes('此帧'), 'the frame-tools heading is Chinese');
  const person = VS.inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null}}}));
  assert.ok(person.includes('选择常客') && person.includes('访客姓名'), 'both labelling options are Chinese');
  assert.ok(person.includes('— 不是常客（访客）—'), 'the guest option is Chinese');
  const legacy = VS.inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null}},
                                                 persons:{tracks:[{id:2, seed:'A'}], track:2, windows:[], win:'68-94', status:'', predictions:null}}));
  assert.ok(legacy.includes('选手 A') && legacy.includes('旧版 A/B 种子'), 'a legacy A seed reads as 选手 A in 中 too');
  const en = adapterStage('en', ROSTER).inspectorHTML(visionSnapshot());
  assert.ok(en.includes('Select a cue, a ball, a person or an anchor to label it.'), 'EN keeps its own copy, not a translation of 中');
});

test('an inference run says it was not stored, and a stored file is labelled as an earlier run', () => {
  // The write is gone from the server (no file, no directory); what the UI owes
  // the operator is the provenance: this frame's own run, or a file an earlier
  // run left behind - never the two blurred together.
  assert.ok(source.includes('Inference completed for frame ${job.frame_index} (not stored).'),
    'the completion line says the result was not stored');
  assert.ok(source.includes('推理已完成（未存储）'), 'and 中 renders the same sentence');
  const boxes = {tool:'select', newBoxLabel:'ball', box:0, boxLabel:'ball', polygon:false, result:'inference',
                 dirty:false, inferRunning:false, inferStatus:'Idle.'};
  const stored = visionSnapshot({selection:{kind:'box', box:0},
                                 corrections:{...boxes, storedInference:true, inferenceAt:'2026-09-23T20:58:05+00:00'}});
  const storedHTML = adapterStage('en', ROSTER).inspectorHTML(stored);
  assert.ok(storedHTML.includes('data-vs-inference="stored"') && storedHTML.includes('stored inference'),
    'a stored file is named as stored');
  assert.ok(/2026|9\/2[0-9]|09\/2[0-9]/.test(storedHTML), 'with its own timestamp');
  const session = visionSnapshot({selection:{kind:'box', box:0},
                                  corrections:{...boxes, storedInference:false, inferenceAt:'2026-09-23T21:10:00+00:00'}});
  const sessionHTML = adapterStage('en', ROSTER).inspectorHTML(session);
  assert.ok(sessionHTML.includes('data-vs-inference="session"') && sessionHTML.includes('run on this frame, not stored'),
    'this session\'s run says it was not stored');
  const zhHTML = adapterStage('zh', ROSTER).inspectorHTML(stored);
  assert.ok(zhHTML.includes('已存推理') && zhHTML.includes('推理来源'), 'and the stored label is Chinese too');
  const facts = adapterStage('en', ROSTER).factsLine(visionSnapshot({
    drawn:{cloth:0, balls:2, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:0, balls:2, persons:0, pockets:0, anchors:0, events:0}},
    cloth:{verdict:{state:'none'}, quad:null, pockets:{}, refusal:null},
    corrections:{...boxes, storedInference:true, inferenceAt:'2026-09-23T20:58:05+00:00', modelBoxes:2}}));
  assert.ok(facts.includes('stored inference'), 'the facts line names the earlier run too: ' + facts);
  assert.ok(!adapterStage('en', ROSTER).factsLine(visionSnapshot({
    drawn:{cloth:0, balls:2, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:0, balls:2, persons:0, pockets:0, anchors:0, events:0}},
    cloth:{verdict:{state:'none'}, quad:null, pockets:{}, refusal:null},
    corrections:{...boxes, storedInference:false, inferenceAt:'2026-09-23T21:10:00+00:00', modelBoxes:2}})).includes('stored inference'),
    'a session run never says stored in the facts line either');
  const zhStored = adapterStage('zh', ROSTER).factsLine(visionSnapshot({
    drawn:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0}},
    cloth:{verdict:{state:'none'}, polygon:'inference', quad:null, pockets:{}, refusal:null},
    corrections:{...boxes, storedInference:true, inferenceAt:'2026-09-23T20:58:05+00:00', modelBoxes:0}}));
  assert.ok(zhStored.includes('已存推理'), '中 says 已存推理 for a stored file: ' + zhStored);
  const zhSession = adapterStage('zh', ROSTER).factsLine(visionSnapshot({
    drawn:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0}},
    cloth:{verdict:{state:'none'}, polygon:'inference', quad:null, pockets:{}, refusal:null},
    corrections:{...boxes, storedInference:false, inferenceAt:'2026-09-23T21:10:00+00:00', modelBoxes:0}}));
  assert.ok(zhSession.includes('推理 · 本次会话'), '中 says 本次会话 for a session run: ' + zhSession);
  assert.ok(!zhSession.includes('已存推理'), 'and never 已存推理 for one: ' + zhSession);
});

test('the live ball detector is selectable and named as the trained net', () => {
  const VS = adapterStage('en', ROSTER);
  const running = visionSnapshot({live:{state:'running', error:null, attempt:null, frame_age_ms:20, receive_to_result_ms:30,
    skipped:0, detectors:['table','person','ball'], stale:false, seq:1,
    stages:[{name:'table', every_n_frames:30, runs:2, skips:28, budget_ms:12},
            {name:'person', every_n_frames:1, runs:30, skips:0, budget_ms:10},
            {name:'ball', every_n_frames:2, runs:15, skips:15, budget_ms:120}]}});
  const panel = VS.sourcePanelHTML(running);
  for (const option of ['data-vs-value="table"', 'data-vs-value="person"', 'data-vs-value="ball"']) {
    assert.ok(panel.includes(option), `the live detector row offers ${option}`);
  }
  assert.ok(panel.includes('Ball (trained net)'), 'the ball row names the trained net, not SAM3');
  assert.ok(panel.includes('The live ball detector is the trained tiny net'), 'and says which path it is');
  assert.ok(panel.includes('SAM3'), 'while naming the CPU-heavy frame detector as the other one');
  assert.ok(panel.includes('data-vs-live-stages="3"'), 'the panel reports the stages the processor really has');
  assert.ok(panel.includes('every 2 frames') && panel.includes('not run on the skipped frames'),
    'a partitioned stage states its cadence and what a skipped frame means: ' + panel.slice(0, 400));
  assert.ok(panel.includes('15 runs'), 'with how often it actually ran');
  const zhPanel = adapterStage('zh', ROSTER).sourcePanelHTML(running);
  assert.ok(zhPanel.includes('球（训练网络）') && zhPanel.includes('每 2 帧'), 'the row and the cadence are Chinese: ' + zhPanel.slice(0, 300));
  // A refusal is the server's sentence, shown as it comes - never a green state.
  const refused = visionSnapshot({live:{state:'error', error:"Requested detector 'ball' cannot run: no weights at /x/960x540-scratch.pt",
    attempt:{source:'dataset:vod30', error:"Requested detector 'ball' cannot run: no weights at /x/960x540-scratch.pt", at: 1},
    frame_age_ms:null, receive_to_result_ms:null, skipped:0, detectors:['table','person'], stale:false, seq:null, stages:[]}});
  const refusalPanel = adapterStage('en', ROSTER).sourcePanelHTML(refused);
  assert.ok(refusalPanel.includes('cannot run: no weights at /x/960x540-scratch.pt'),
    'the refusal sentence reaches the panel verbatim (escaped, not rewritten)');
  assert.ok(refusalPanel.includes('error · Requested detector &#39;ball&#39;'), 'and the live row keeps the state error');
  assert.ok(refusalPanel.includes('Start attempt'), 'and is labelled as the attempt that failed');
});

test('the VOD panel prints the replay\'s own kind, live, rate and drift', () => {
  const base = {state:'idle', error:null, attempt:null, frame_age_ms:null, receive_to_result_ms:null, skipped:0,
                detectors:['table','person'], stale:false, seq:null, stages:[], source:null, replay:null};
  const chosen = adapterStage('en', ROSTER, {replayChoice: () => ({vod_id: '1000000011', start_s: 30, rate: 2})})
    .sourcePanelHTML(visionSnapshot({live:{...base}}));
  assert.ok(chosen.includes('data-vs-replay="chosen"'), 'a chosen VOD is shown before it starts');
  assert.ok(chosen.includes('vod 1000000011') && chosen.includes('a replay, never a live broadcast'),
    'and it is named a replay, never a broadcast: ' + chosen.slice(chosen.indexOf('vs-replay'), chosen.indexOf('vs-replay') + 200));
  const running = adapterStage('en', ROSTER).sourcePanelHTML(visionSnapshot({live:{...base, state:'running',
    source:{kind:'vod-replay', vod_id:'1000000011', rate:2, start_s:30},
    replay:{kind:'vod-replay', live:false, vod_id:'1000000011', rate:2, drift_s:-0.42, network:'hls', pacing:'wall-clock', wall_s:12.5, video_s:12.1}}}));
  assert.ok(running.includes('data-vs-replay="running"'), 'a running replay reports itself');
  assert.ok(running.includes('kind vod-replay') && running.includes('live false'), 'kind and live come from the server: ' + running.slice(running.indexOf('vs-replay'), running.indexOf('vs-replay') + 260));
  assert.ok(running.includes('vod 1000000011') && running.includes('×2') && running.includes('drift -0.42 s'), 'with the id, the rate and the drift');
  assert.ok(!/live true/.test(running), 'nothing here claims it is live');
  const failed = adapterStage('en', ROSTER).sourcePanelHTML(visionSnapshot({live:{...base, state:'error',
    error:'Twitch VOD playlist request failed (HTTP 403)', attempt:{source:'vod-replay', error:'Twitch VOD playlist request failed (HTTP 403)', at:1}}}));
  assert.ok(failed.includes('data-vs-replay="failed"') && failed.includes('Twitch VOD playlist request failed (HTTP 403)'),
    'a refusal shows its cause instead of a spinner that never ends');
  const zhRunning = adapterStage('zh', ROSTER).sourcePanelHTML(visionSnapshot({live:{...base, state:'running',
    source:{kind:'vod-replay', vod_id:'1000000011', rate:2, start_s:30}, replay:{kind:'vod-replay', live:false, vod_id:'1000000011', rate:2, drift_s:-0.42}}}));
  assert.ok(zhRunning.includes('回放') && zhRunning.includes('漂移'), 'and the panel is bilingual');
});

test('a VOD replay is never called live on the stage chip, the freshness line, the facts line or the stagebar', () => {
  // The replay's frames arrive through the live path, so the stage chrome used to
  // read "● live" / "直播" while the panel said "live false". The server's own
  // status (live.source / live.replay: kind 'vod-replay') decides the word.
  const replayLive = {state:'running', error:null, attempt:null, frame_age_ms:240, receive_to_result_ms:33, skipped:0,
    detectors:['table','person'], stale:false, seq:12, stages:[],
    source:{kind:'vod-replay', vod_id:'1000000011', rate:2, start_s:30},
    replay:{kind:'vod-replay', live:false, vod_id:'1000000011', rate:2, drift_s:-0.42}};
  const shellLabel = source => {
    // ops.js builds the frame label it hands to ingestLiveFrame; run its real code.
    const opsSource = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'ops.js'), 'utf8');
    const k = opsSource.indexOf('review()?.ingestLiveFrame(URL.createObjectURL(blob),meta,{label:');
    const expr = opsSource.slice(opsSource.indexOf('label:', k) + 6, opsSource.indexOf(',channel:', k));
    const liveSourceLabel = opsSource.slice(opsSource.indexOf('function liveSourceLabel('), opsSource.indexOf('function replayChoice('));
    return lang => vm.runInNewContext(`const lang=${JSON.stringify(lang)};const liveText=(en,zh)=>lang==='zh'?zh:en;
      const liveChoice='vod-replay', vodChoice={vod_id:'1000000011', start_s:30, rate:2}, channelOf=()=>null;
      const source=${JSON.stringify(source)};
      ${liveSourceLabel.replace(/\/\/[^\n]*\n/g, '\n')}
      ${expr}`);
  };
  for (const [lang, liveWord] of [['en', 'live'], ['zh', '直播']]) {
    // The frame label the shell hands to the stage (the stagebar's "Sources · …").
    const label = shellLabel({kind:'vod-replay', vod_id:'1000000011', start_s:30, rate:2})(lang);
    assert.ok(!label.includes(liveWord) && !label.includes('●'), `${lang}: the shell's frame label for a replay is not live: ${label}`);
    assert.ok(label.includes('1000000011'), `${lang}: it still names the VOD: ${label}`);
    const liveLabel = shellLabel({kind:'twitch', source_id:'x'})(lang);
    assert.ok(liveLabel.startsWith(`● ${liveWord}`), `${lang}: a real channel is still live: ${liveLabel}`);
    // The engine's stage chip.
    const chip = {hidden:true, className:'', textContent:''};
    T.setRoot({lang, querySelector: selector => selector === '#stage-live' ? chip : null, querySelectorAll: () => []});
    T.state.source = {kind:'live', label, channel:null};
    Object.assign(T.state.live, {stale:false, frame_age_ms:240, source:replayLive.source, replay:replayLive.replay});
    T.paintLiveChip();
    assert.ok(!chip.hidden && chip.textContent && !chip.textContent.includes(liveWord), `${lang}: the stage chip of a replay is not live: "${chip.textContent}"`);
    assert.ok(!/\bon\b/.test(chip.className), `${lang}: nor styled as the live-on chip: ${chip.className}`);
    Object.assign(T.state.live, {source:{kind:'twitch', source_id:'x', channel:'examplechannel'}, replay:null});
    T.paintLiveChip();
    assert.strictEqual(chip.textContent, `● ${lang === 'zh' ? '直播' : 'live'}`, `${lang}: a real channel keeps the live chip`);
    Object.assign(T.state.live, {source:null, replay:null, stale:false, frame_age_ms:null});
    T.state.source = {kind:'vod', label:'vod30', channel:null};
    // The adapter's chip-row freshness and the facts line.
    const snapshot = visionSnapshot({source:{kind:'live', label, channel:null}, live:replayLive,
      loading:{overlay:false, since:0}, drawn:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0}}});
    const VSr = adapterStage(lang, ROSTER);
    const fresh = (VSr.chipsHTML(snapshot).match(/<span class="vs-fresh[^"]*">([^<]*)<\/span>/) || [])[1] || '';
    assert.ok(fresh && !fresh.includes(liveWord), `${lang}: the freshness line of a replay is not live: "${fresh}"`);
    assert.ok(/240 ms/.test(fresh), `${lang}: and it still says how old the frame is: "${fresh}"`);
    const facts = VSr.factsLine(snapshot);
    assert.ok(!facts.toLowerCase().includes(liveWord), `${lang}: the facts line of a replay is not live: "${facts.slice(0, 80)}"`);
    // A stale replay says stale, as a stale broadcast does.
    const staleFresh = (VSr.chipsHTML({...snapshot, live:{...replayLive, stale:true}}).match(/<span class="vs-fresh[^"]*">([^<]*)<\/span>/) || [])[1] || '';
    assert.ok(staleFresh.includes(lang === 'zh' ? '已过期' : 'STALE'), `${lang}: a stale replay says stale: "${staleFresh}"`);
    // A real channel keeps its live word on both.
    const channel = {...snapshot, live:{...replayLive, source:{kind:'twitch', source_id:'x', channel:'examplechannel'}, replay:null}};
    assert.ok(((VSr.chipsHTML(channel).match(/<span class="vs-fresh[^"]*">([^<]*)<\/span>/) || [])[1] || '').startsWith(liveWord), `${lang}: a channel is live`);
  }
});

test('the enrol block shows the evidence level, the crops and one confirm', () => {
  // The engine's two calls: a read for the preview, the write only on confirm.
  assert.ok(source.includes("api('/api/identity/enroll-preview', body)"), 'the preview is a read of its own endpoint');
  assert.ok(source.includes("body.cluster_id = person.cluster_id"), 'it carries the cluster id when the track has one, for the fast path');
  assert.ok(source.includes("save(button, '/api/identity/enroll-confirm', {token: payload.token, player_name: name}"),
    'the confirm is the one write, with the token and the typed name');
  const idle = adapterStage('en', ROSTER).inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null}}}));
  assert.ok(idle.includes('data-vs-action="enroll-preview"') && idle.includes('Enrol as regular'), 'the person rail offers the action');
  assert.ok(idle.includes('nothing is written until you confirm'), 'and says the preview writes nothing');
  const pending = adapterStage('en', ROSTER).inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null}},
    enroll:{status:'pending', payload:null, name:'', elapsed_ms:4200, error:null}}));
  assert.ok(pending.includes('data-vs-enrol="pending"') && pending.includes('collecting faces · 4 s'),
    'a slow preview reports itself working, with elapsed seconds: ' + pending.slice(0, 80));
  assert.ok(!pending.includes('data-vs-action="enroll-preview"'), 'and cannot be started twice');
  const ready = {status:'ready', name:'', elapsed_ms:null, error:null,
    payload:{ok:true, token:'tok', track_id:6, selection_iou:0.98, frames_seen:6,
      crops:[{index:0, frame_index:2010, t:67.0, det_score:0.7977, eye_px:12.7, jpeg_data_url:'data:image/jpeg;base64,AAA'},
             {index:1, frame_index:2040, t:68.0, det_score:0.81, eye_px:13.1, jpeg_data_url:'data:image/jpeg;base64,BBB'}],
      purity:{probes:49, agreement:0.98}, quality:{kept:2, usable:2},
      evidence:{source:'window_scan', stored_face:false, cross_checked:true, crops:2, frames_scanned:2}}};
  const readyHTML = adapterStage('en', ROSTER).inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null}}, enroll:ready}));
  assert.ok(readyHTML.includes('data-vs-crop="0"') && readyHTML.includes('data-vs-crop="1"'), 'the crops are shown');
  assert.ok(readyHTML.includes('data:image/jpeg;base64,AAA'), 'as data URLs, so no file route is needed');
  assert.ok(readyHTML.includes('det 0.80') && readyHTML.includes('eye 12.7 px'), 'with the detection and eye numbers');
  assert.ok(readyHTML.includes('frames seen 6') && readyHTML.includes('usable faces 2/2') && readyHTML.includes('purity 98% (49)'),
    'and the plan\u2019s own numbers: ' + readyHTML.slice(readyHTML.indexOf('facts'), readyHTML.indexOf('facts') + 220));
  assert.ok(readyHTML.includes('evidence: window scan · 2 crops · cross-checked'), 'and which evidence level produced them');
  assert.ok(readyHTML.includes('data-vs-action="enroll-name"') && readyHTML.includes('data-vs-action="enroll-confirm"')
    && readyHTML.includes('data-vs-action="enroll-cancel"'), 'with one name box, one confirm and one cancel');
  // One stored face: weaker evidence, said out loud.
  const cluster = {...ready, payload:{...ready.payload, evidence:{source:'cluster_face', stored_face:true, cross_checked:false, crops:1, frames_scanned:0},
    crops:[ready.payload.crops[0]], quality:{kept:1, usable:1}, purity:{probes:0, agreement:null}}};
  const clusterHTML = adapterStage('en', ROSTER).inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:7}}, enroll:cluster}));
  assert.ok(clusterHTML.includes('evidence: stored cluster face · 1 crops · not cross-checked'),
    'the cluster path says it is not cross-checked: ' + clusterHTML.slice(clusterHTML.indexOf('evidence:'), clusterHTML.indexOf('evidence:') + 90));
  assert.ok(clusterHTML.includes('no other face to cross-check'), 'and why purity is absent');
  // A refusal is the reason in the operator's words, with the code still visible.
  const refused = {status:'refused', name:'', elapsed_ms:null, error:null,
    payload:{ok:false, reason:'single_face_only', message:'only one usable face: upload a second photo to prove consistency',
             crops:[{index:0, frame_index:2010, t:67.0, det_score:0.79, eye_px:12.7, jpeg_data_url:'data:image/jpeg;base64,AAA'}]}};
  const refusedHTML = adapterStage('en', ROSTER).inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null}}, enroll:refused}));
  assert.ok(refusedHTML.includes('data-vs-enrol="refused"') && refusedHTML.includes('only one usable face: no second face to cross-check it'),
    'the refusal is a sentence, in operator language');
  assert.ok(refusedHTML.includes('single_face_only') && refusedHTML.includes('upload a second photo'), 'with the module code and its own sentence beside it');
  assert.ok(refusedHTML.includes('data-vs-crop="0"'), 'and it still shows the face it did see');
  // A refusal on confirm (the server answers 200 ok:false: token_mismatch,
  // preview_expired, player_name_required) reaches the operator as its real
  // reason in both languages, and nothing about it looks like a success.
  const confirmSource = source.replace(/\}\)\(\);\s*$/, 'globalThis.E = {state, enrollConfirm, snapshot, setRoot: host => { root = host; }}; })();');
  // Runs the real async confirm against a stubbed server answer and returns the
  // engine snapshot and what confirm resolved to.
  const confirmWith = answer => {
    const box = {document:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, createElement: () => elementStub()},
                 window:{addEventListener() {}}, confirm: () => true, URL:{createObjectURL: () => 'blob:test', revokeObjectURL() {}},
                 setTimeout, clearTimeout, console, Math, Number, Object, JSON, Date};
    box.globalThis = box;
    // microtaskMode drains the confirm's awaits before runInContext returns, so the
    // real async write runs to its end without an async test.
    const context = vm.createContext(box, {microtaskMode:'afterEvaluate'});
    vm.runInContext(confirmSource, context, {filename:'app.js'});
    // The stub lives in the context's realm: an outer-realm promise would settle on
    // the outer microtask queue, after runInContext has already returned.
    vm.runInContext(`fetch = async () => ({ok:true, status:200, json: async () => (${JSON.stringify(answer)})});
      E.setRoot({lang:'en', querySelector: () => null, querySelectorAll: () => []});
      E.state.enroll = {status:'ready', name:'Ana', startedAt:0, error:null, payload:${JSON.stringify(ready.payload)}};
      E.enrollConfirm(null).then(value => { globalThis.confirmed = value; }, error => { globalThis.confirmError = String(error); });`, context);
    return {engineSnap: vm.runInContext('E.snapshot()', context), confirmed: box.confirmed, confirmError: box.confirmError};
  };
  // A confirm the server accepts is still a success: written, and one ✓ receipt.
  const written = confirmWith({ok:true, player_id:'p9', player_name:'Ana', revision:8, embeddings:2});
  assert.strictEqual(written.engineSnap.enroll.status, 'written');
  const writtenReceipt = written.engineSnap.receipts.find(r => r.key === 'person');
  assert.ok(writtenReceipt && writtenReceipt.error === false && writtenReceipt.text === 'Ana → regular', JSON.stringify(writtenReceipt));
  for (const [reason, message, en, zh] of [
    ['token_mismatch', 'these crops are not the ones you were shown; reload the frame', 'these crops are not the ones you were shown; preview again', '这些裁剪图与展示时不一致；请重新预览'],
    ['preview_expired', 'this preview is no longer held; preview the track again before confirming', 'this preview is no longer held; preview again', '此预览已不再保留；请重新预览'],
    ['player_name_required', 'a name is required to enrol a regular', 'a name is required to enrol a regular', '登记常客需要姓名']]) {
    const {engineSnap, confirmed, confirmError} = confirmWith({ok:false, reason, message, detail:{}});
    const box = {confirmed};
    assert.strictEqual(confirmError, undefined, `${reason}: a refusal is an answer, not an exception`);
    assert.strictEqual(engineSnap.enroll.status, 'refused', `${reason}: the block is refused`);
    assert.strictEqual(box.confirmed, false, `${reason}: a refused confirm is not a successful write`);
    const receipt = engineSnap.receipts.find(r => r.key === 'person');
    assert.ok(receipt && receipt.error === true && receipt.text.includes(reason),
      `${reason}: nothing was written, so the receipt is an error naming the refusal: ${JSON.stringify(engineSnap.receipts)}`);
    const selection = {kind:'person', track:2, person:{track_id:2, cluster_id:null}};
    for (const [lang, sentence] of [['en', en], ['zh', zh]]) {
      // The adapter reads the receipts from the engine it is attached to (handed
      // over after attach, so attach's own first render stays a no-op here).
      let attached = false;
      const VSe = adapterStage(lang, ROSTER, {review:{snapshot: () => attached ? engineSnap : null}});
      attached = true;
      const html = VSe.inspectorHTML(visionSnapshot({selection, enroll:engineSnap.enroll}));
      assert.ok(!html.includes('✓'), `${reason} (${lang}): no success mark anywhere in the person block`);
      const line = (html.match(/<p class="vs-receipt[^"]*"[^>]*>[^<]*<\/p>/) || [''])[0];
      assert.ok(line.includes('vs-receipt error') && line.includes('>! ') && !/Saved|已保存/.test(line),
        `${reason} (${lang}): the receipt is the red "!" line and never says Saved: ${line}`);
      assert.ok(html.includes('data-vs-enrol="refused"') && html.includes(sentence),
        `${reason} (${lang}): the refusal is the real reason: ` + html.slice(html.indexOf('data-vs-enrol'), html.indexOf('data-vs-enrol') + 160));
      assert.ok(!html.includes(lang === 'zh' ? '未知' : 'Unknown'), `${reason} (${lang}): never "Unknown"`);
      assert.ok(html.includes(reason), `${reason} (${lang}): with the module code beside it`);
    }
  }
  const none = {status:'refused', name:'', elapsed_ms:null, error:null, payload:{ok:false, reason:'no_face_in_track', message:'x', crops:[]}};
  assert.ok(adapterStage('en', ROSTER).inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null}}, enroll:none}))
    .includes('no usable crop was kept'), 'a refusal with no crops says so instead of showing an empty box');
  const zh = adapterStage('zh', ROSTER).inspectorHTML(visionSnapshot({selection:{kind:'person', track:2, person:{track_id:2, cluster_id:null}}, enroll:cluster}));
  assert.ok(zh.includes('已存聚类人脸') && zh.includes('未交叉核对') && zh.includes('确认登记'), 'the whole block is Chinese too');
});

test('two layers on one frame: model dashed, yours solid, and only yours are saved', () => {
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : selector === '#stage-note' ? note : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.overlay = {cloth:false, balls:false, persons:false, pockets:false, anchors:false, events:false};
  T.state.cloth.reference = null; T.state.unified = null; T.state.polygon = null;
  T.state.sel = {kind:'none', crop:null, ball:null, person:null, track:null, anchor:0, event:null, box:-1};
  // The reported frame: a stored correction (the operator's) and the model's own
  // inference, with one ball in both layers and one only the model saw.
  T.state.fresult = {correction:{dataset:'vod30', frame_index:0, width:1280, height:720,
                                 boxes:[{label:'ball', bbox:[100,100,120,120]}]},
                     inference:{boxes:[{label:'ball', bbox:[101,101,121,121]}, {label:'ball', bbox:[400,300,420,320]}], table_polygon:null}};
  T.state.dirty = false;
  T.applyFrameResult();
  assert.strictEqual(T.state.boxes.length, 3, 'both layers are in state.boxes');
  assert.strictEqual(T.manualBoxCount(), 1);
  assert.strictEqual(T.modelBoxCount(), 2);
  T.paintOverlay();
  const html = svg.innerHTML;
  assert.ok(html.includes('data-origin="manual"') && html.includes('data-origin="auto"'), 'both origins are drawn');
  assert.ok(html.includes('>YOURS<') && html.includes('>MODEL<'), 'with their own tags');
  assert.ok(/class="t-box manual"/.test(html) && /class="t-box auto/.test(html), 'and their own classes for solid vs dashed');
  // The model box the operator already covered by a manual box is that pair's faint
  // counterpart, at the model's own rectangle - not a second bright box.
  assert.ok(/data-origin="auto"[^>]*class="t-box auto faint"/.test(html) || /class="t-box auto faint"/.test(html),
    'a matched model box is drawn faint: ' + html.slice(html.indexOf('data-origin="auto"'), html.indexOf('data-origin="auto"') + 120));
  assert.ok(html.includes('x="101"') && html.includes('y="101"'), 'at the model\u2019s coordinates, so a disagreement shows as a gap');
  assert.ok(!/class="t-box auto faint"[^>]*data-ghost/.test(html), 'nothing is frozen before an edit');
  // The save payload carries the operator's box only.
  const body = T.correctionBody();
  assert.strictEqual(body.boxes.length, 1, 'one manual box is saved');
  same(body.boxes[0], {label:'ball', bbox:[100,100,120,120]});
  assert.ok(body.boxes.every(box => box.origin === undefined), 'and the payload carries no origin bookkeeping of its own');
  // Dragging a model box makes it the operator's, and the model's original stays as
  // a frozen ghost until the frame is reloaded.
  const model = T.state.boxes[2];
  T.ghostModelBox(model);
  model.bbox = [460, 300, 480, 320];
  T.markBoxEdited(model);
  T.paintOverlay();
  assert.strictEqual(model.origin, 'manual', 'the dragged box is the operator\u2019s');
  const ghost = T.state.boxes.find(box => box.frozen);
  same(ghost.bbox, [400, 300, 420, 320]);
  assert.strictEqual(ghost.origin, 'auto');
  assert.ok(/data-ghost="1"/.test(svg.innerHTML), 'and it is drawn as a ghost');
  const after = T.correctionBody();
  assert.strictEqual(after.boxes.length, 2, 'the edited model box is now included in the save payload');
  assert.ok(after.boxes.some(box => JSON.stringify(box.bbox) === JSON.stringify([460, 300, 480, 320])), 'at its new geometry');
  assert.ok(!after.boxes.some(box => JSON.stringify(box.bbox) === JSON.stringify([400, 300, 420, 320])), 'the ghost is never saved');
  assert.strictEqual(T.state.boxes.filter(box => box.origin === 'auto' && !box.frozen).length, 1,
    'the paired model box stays the model\u2019s: a counterpart is never promoted to a decision');
  // The painter says the same thing the payload does.
  assert.ok(svg.innerHTML.includes('data-origin="auto"'), 'the model\u2019s layer is still on the stage after the edit');
  T.state.fresult = null; T.state.boxes = []; T.state.dirty = false;
});

// The painter and app.css must speak one vocabulary. The test above checks the
// class names only, and model boxes shipped solid because app.css styled `.model`
// while the painter emits `auto`. So resolve the emitted classes against app.css
// the way the browser does: every `#t-overlay .<classes> <tag>` rule whose classes
// are all on the element applies, more classes win, and a later rule wins a tie.
function overlayRuleStyle(css, classes, tag) {
  const rules = [];
  for (const [, selectors, body] of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    for (const selector of selectors.split(',')) {
      const match = selector.trim().match(/^#t-overlay\s+((?:\.[\w-]+)+)\s+(\w+)$/);
      if (!match || match[2] !== tag) continue;
      const need = match[1].slice(1).split('.');
      if (need.every(c => classes.includes(c))) rules.push({weight: need.length, order: rules.length, body});
    }
  }
  const style = {};
  for (const rule of rules.sort((a, b) => a.weight - b.weight || a.order - b.order)) {
    for (const decl of rule.body.split(';')) {
      const at = decl.indexOf(':');
      if (at > 0) style[decl.slice(0, at).trim()] = decl.slice(at + 1).trim();
    }
  }
  return style;
}
test('app.css styles the classes the painter emits: model dashed, yours solid, counterpart and ghost faint', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'app.css'), 'utf8');
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : selector === '#stage-note' ? note : null, querySelectorAll: () => []};
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.state.overlay = {cloth:false, balls:false, persons:false, pockets:false, anchors:false, events:false};
  T.state.cloth.reference = null; T.state.unified = null; T.state.polygon = null;
  T.state.sel = {kind:'none', crop:null, ball:null, person:null, track:null, anchor:0, event:null, box:-1};
  // One YOURS box with its model counterpart, one lone model box, and one model box
  // the operator drags away (it becomes YOURS and leaves a frozen ghost behind).
  T.state.fresult = {correction:{dataset:'vod30', frame_index:0, width:1280, height:720, boxes:[{label:'ball', bbox:[100,100,120,120]}]},
                     inference:{boxes:[{label:'ball', bbox:[101,101,121,121]}, {label:'ball', bbox:[400,300,420,320]},
                                       {label:'ball', bbox:[600,300,620,320]}], table_polygon:null}};
  T.state.dirty = false;
  T.applyFrameResult();
  const dragged = T.state.boxes[3];
  T.ghostModelBox(dragged); dragged.bbox = [660, 300, 680, 320]; T.markBoxEdited(dragged);
  T.paintOverlay();
  const html = svg.innerHTML;
  const groups = [...html.matchAll(/<g data-box="(\d+)" data-origin="(\w+)"( data-ghost="1")? class="([^"]+)"/g)]
    .map(([, index, origin, ghost, cls]) => ({index: Number(index), origin, ghost: !!ghost, classes: cls.split(/\s+/)}));
  const group = index => groups.find(g => g.index === index);
  const rect = index => overlayRuleStyle(css, group(index).classes, 'rect');
  const dashed = style => !!style['stroke-dasharray'] && style['stroke-dasharray'] !== 'none';
  const opacity = style => style.opacity === undefined ? 1 : Number(style.opacity);
  const [yours, counterpart, model, edited, ghost] = [0, 1, 2, 3, 4].map(rect);
  assert.ok(dashed(model) && opacity(model) < 1,
    `a MODEL box (class "${group(2).classes.join(' ')}") is dashed and dimmed: ${JSON.stringify(model)}`);
  assert.ok(!dashed(yours) && opacity(yours) === 1, `a YOURS box is solid at full opacity: ${JSON.stringify(yours)}`);
  assert.ok(!dashed(edited) && opacity(edited) === 1, `so is the model box the operator dragged: ${JSON.stringify(edited)}`);
  assert.ok(dashed(counterpart) && opacity(counterpart) < opacity(model),
    `a matched counterpart (class "${group(1).classes.join(' ')}") is fainter than a lone model box: ${JSON.stringify(counterpart)}`);
  assert.ok(group(4).ghost && dashed(ghost) && opacity(ghost) < opacity(model), `the drag ghost is faint too: ${JSON.stringify(ghost)}`);
  // A box's MODEL tag wears the same brass stroke as every other MODEL tag.
  const tags = [...html.matchAll(/<g class="(o-src [^"]+)" data-src="(\w+)">/g)].map(([, cls, src]) => ({src, classes: cls.split(/\s+/)}));
  const modelTag = tags.find(tag => tag.src === 'auto'), yoursTag = tags.find(tag => tag.src === 'manual');
  assert.strictEqual(overlayRuleStyle(css, modelTag.classes, 'rect').stroke, 'var(--brass)',
    `a box's MODEL tag (class "${modelTag.classes.join(' ')}") has the brass stroke`);
  assert.strictEqual(overlayRuleStyle(css, yoursTag.classes, 'rect').stroke, 'var(--green)', 'and a YOURS tag the green one');
  T.state.fresult = null; T.state.boxes = []; T.state.dirty = false;
});

test('a successful enrol confirm resolves true and re-reads the roster through the hook the shell mounted', () => {
  // enrollConfirm read `opts?.reloadRoster`, but the engine has no `opts`: the
  // shell handed reloadRoster to the vision adapter only. So every successful
  // confirm threw "opts is not defined" after the write, and the roster was never
  // re-read. The engine now takes the hook through mount(host, hooks).
  const host = {id:'review-root', lang:'en', dataset:{}, querySelector: () => elementStub(), querySelectorAll: () => [], addEventListener() {}};
  const box = {document:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, createElement: () => elementStub()},
               window:{addEventListener() {}}, confirm: () => true, URL:{createObjectURL: () => 'blob:test', revokeObjectURL() {}},
               localStorage:{getItem: () => null, setItem() {}}, setTimeout, clearTimeout, console, Math, Number, Object, JSON, Date};
  box.globalThis = box;
  const context = vm.createContext(box, {microtaskMode:'afterEvaluate'});
  vm.runInContext(source.replace(/\}\)\(\);\s*$/, 'globalThis.E = {state}; })();'), context, {filename:'app.js'});
  // Only the enrol write answers; every other request mount() makes stays pending.
  vm.runInContext(`fetch = (url, init) => url === '/api/identity/enroll-confirm'
      ? Promise.resolve({ok:true, status:200, json: async () => ({ok:true, player_id:'p9', player_name:'Nina', revision:8, embeddings:3})})
      : new Promise(() => {});
    globalThis.rosterReads = 0;`, context);
  const review = box.window.CornerPocketReview;
  review.mount(host, {reloadRoster: () => { box.rosterReads++; }});
  vm.runInContext(`E.state.enroll = {status:'ready', name:'Nina', startedAt:0, error:null, payload:{ok:true, token:'tok', crops:[]}};
    window.CornerPocketReview.enrollConfirm(null).then(value => { globalThis.confirmed = value; }, error => { globalThis.confirmError = String(error); });`, context);
  assert.strictEqual(box.confirmError, undefined, 'a successful confirm throws nothing');
  assert.strictEqual(box.confirmed, true, 'and resolves true');
  assert.strictEqual(vm.runInContext('E.state.enroll.status', context), 'written');
  assert.strictEqual(box.rosterReads, 1, 'the roster is re-read once, through the mounted hook');
  // A shell that mounts without hooks (the standalone review page) still confirms cleanly.
  const bare = {...box, rosterReads:0, confirmed:undefined, confirmError:undefined};
  bare.globalThis = bare;
  const bareContext = vm.createContext(bare, {microtaskMode:'afterEvaluate'});
  vm.runInContext(source.replace(/\}\)\(\);\s*$/, 'globalThis.E = {state}; })();'), bareContext, {filename:'app.js'});
  vm.runInContext(`fetch = (url) => url === '/api/identity/enroll-confirm'
      ? Promise.resolve({ok:true, status:200, json: async () => ({ok:true})}) : new Promise(() => {});`, bareContext);
  bare.window.CornerPocketReview.mount({...host});
  vm.runInContext(`E.state.enroll = {status:'ready', name:'Nina', startedAt:0, error:null, payload:{ok:true, token:'tok', crops:[]}};
    window.CornerPocketReview.enrollConfirm(null).then(value => { globalThis.confirmed = value; }, error => { globalThis.confirmError = String(error); });`, bareContext);
  assert.strictEqual(bare.confirmError, undefined, 'without a hook there is still no exception');
  assert.strictEqual(bare.confirmed, true);
  // The shell passes its roster re-read to the engine's mount, not only to the adapter.
  const shell = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'ops.js'), 'utf8');
  assert.ok(/review\(\)\.mount\(host\.querySelector\('#review-root'\),\{reloadRoster:/.test(shell), 'ops.js mounts the engine with the reloadRoster hook');
});

test('a stage click on a person sends the enrol preview an integer cluster, or none', () => {
  // The painter writes the cluster into data-cluster, and a DOM dataset is always
  // a string: the click stored cluster_id "148", and the preview refused it with
  // 400 "cluster_id must be an integer" while a rail selection (a number) worked.
  const box = {document:{querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, createElement: () => elementStub()},
               window:{addEventListener() {}}, confirm: () => true, URL:{createObjectURL: () => 'blob:test', revokeObjectURL() {}},
               setTimeout, clearTimeout, console, Math, Number, Object, JSON, Date};
  box.globalThis = box;
  const context = vm.createContext(box, {microtaskMode:'afterEvaluate'});
  vm.runInContext(source.replace(/\}\)\(\);\s*$/, 'globalThis.E = {state, selectStagePerson, enrollPreview, setRoot: host => { root = host; }}; })();'), context, {filename:'app.js'});
  // The preview body is recorded; loadPersons() and the preview answer at once.
  vm.runInContext(`globalThis.bodies = [];
    fetch = (url, init) => {
      if (url === '/api/identity/enroll-preview') { bodies.push(JSON.parse(init.body)); return Promise.resolve({ok:true, status:200, json: async () => ({ok:true, token:'tok', crops:[]})}); }
      return Promise.resolve({ok:true, status:200, json: async () => ({windows:[{win:'68-94', tracks:[1]}], seeds:{}})});
    };
    E.setRoot({lang:'en', querySelector: () => null, querySelectorAll: () => []});
    E.state.dataset = 'vod30'; E.state.frame = 0; E.state.unified = {persons:[]};`, context);
  const click = dataset => vm.runInContext(`E.state.enroll = {status:'idle', payload:null, name:'', startedAt:0, error:null};
    E.selectStagePerson(${JSON.stringify(dataset)}); E.enrollPreview(null); E.state.sel.person.cluster_id`, context);
  // A clustered person, exactly as the painter writes it.
  const clustered = click({person:'4', bbox:'796,197,928,418', cluster:'148', player:''});
  assert.strictEqual(clustered, 148, 'the selection holds the cluster as a number');
  const sent = vm.runInContext('bodies[bodies.length - 1]', context);
  assert.strictEqual(sent.cluster_id, 148, 'and the preview is sent the integer the server requires');
  assert.strictEqual(typeof sent.cluster_id, 'number');
  assert.strictEqual(vm.runInContext('E.state.enroll.status', context), 'ready', 'so the preview is answered, not refused');
  // A person with no cluster keeps the no-cluster path: no cluster_id at all.
  const bare = click({person:'7', bbox:'10,20,110,220', cluster:'', player:''});
  assert.strictEqual(bare, null, 'no cluster stays null');
  const sentBare = vm.runInContext('bodies[bodies.length - 1]', context);
  assert.ok(!('cluster_id' in sentBare), 'and the preview body carries no cluster_id: ' + JSON.stringify(sentBare));
  same(sentBare.bbox, [10, 20, 110, 220]);
  // A cluster the frame's identity row knows still wins when the click carries none.
  vm.runInContext("E.state.unified = {persons:[{track_id:9, cluster_id:31, player_id:null}]}", context);
  assert.strictEqual(click({person:'9', bbox:'1,2,3,4', cluster:'', player:''}), 31, 'the identity row fills an empty data-cluster');
});

test('a live or replay frame is drawn with its own detections only, never the dataset frame\'s layers', () => {
  // The stage showed a VOD replay frame with vod30 frame 0's stored inference
  // boxes, cloth polygon and facts ("stored inference …") painted over it: two
  // sources on one picture. The overlay describes the picture it is drawn on.
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  const host = {lang:'en', querySelector: selector => selector === '#t-overlay' ? svg : selector === '#stage-note' ? note : null, querySelectorAll: () => []};
  const snapshot = () => sandbox.window.CornerPocketReview.snapshot();
  T.setRoot(host);
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.overlay = {cloth:true, balls:true, persons:true, pockets:true, anchors:true, events:true};
  T.state.sel = {kind:'none', crop:null, ball:null, person:null, track:null, anchor:0, event:null, box:-1};
  T.state.playback = {on:false, playing:false, event:null, from:0, to:0, loops:0, seek:NaN};
  // vod30 frame 0 as the stage holds it: a stored inference (boxes + polygon), the
  // frame's unified detections, the dataset's saved anchors (calibration pockets).
  const anchors = {points:[[454.9,307.8],[799.5,319.4],[1023.8,573.1],[449.6,563.5],[448.4,402.9],[883.9,413.3]], source:'saved anchors', width:1280, height:720};
  T.state.fresult = {inference:{stored_inference:true, saved_at:'2026-09-16T11:07:48Z', table_polygon:[[128,72],[1152,72],[1152,648],[128,648]],
                                boxes:[{label:'ball', bbox:[680,484,702,507], score:0.86}, {label:'person', bbox:[33,134,200,591], score:0.89}]}, correction:null};
  T.state.dirty = false;
  T.applyFrameResult();
  T.state.cloth.reference = anchors;
  T.state.anchors.loaded = true; T.state.anchors.pts = [[100,100],[200,100],[200,200],[100,200],[150,100],[150,200]];
  const frame0 = {table_corners:[[454,307],[799,319],[1023,573],[449,563]], pockets:[{name:'head-left', cx:455, cy:308}],
                  persons:[{bbox:[33,134,200,591], track_id:4, cluster_id:148}], balls:[{cx:691, cy:495, r:11}], events:[]};
  T.state.unified = frame0;
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.paintOverlay();
  const vodHtml = svg.innerHTML;
  assert.ok(vodHtml.includes('t-box') && vodHtml.includes('t-poly') && vodHtml.includes('u-person'), 'the dataset frame draws its own layers');
  // The replay frame arrives: its own detections are two persons and no polygon.
  T.state.source = {kind:'live', label:'VOD replay 1000000011', channel:null};
  T.state.live.detections = {boxes:[{label:'person', bbox:[500,200,600,500]}, {label:'person', bbox:[700,210,800,520]}], table_polygon:null};
  T.state.unified = frame0;           // a unified answer for frame 0 that is still in state
  T.paintOverlay();
  const html = svg.innerHTML;
  assert.ok(!html.includes('t-box') && !html.includes('t-poly'), 'no stored-inference box or polygon over a live frame: ' + html.slice(0, 160));
  assert.ok(!html.includes('u-cloth') && !html.includes('u-pocket') && !html.includes('u-anchor') && !html.includes('u-ball'),
    'no dataset cloth, pockets, anchors or balls');
  assert.ok(!html.includes('data-cluster="148"'), 'no dataset-frame person');
  assert.strictEqual((html.match(/class="u-person/g) || []).length, 2, 'only the live frame\'s own two persons');
  assert.ok(html.includes('data-src="model"'), 'drawn with their own MODEL provenance');
  const d = T.state.drawn;
  same([d.cloth, d.balls, d.persons, d.pockets, d.anchors, d.events], [0, 0, 2, 0, 0, 0]);
  const snap = snapshot();
  assert.strictEqual(snap.corrections.storedInference, false, 'the stored inference is not reported for a live frame');
  const facts = adapterStage('en', ROSTER).factsLine({...visionSnapshot(), ...snap, live:{...snap.live, stale:false, seq:5, frame_age_ms:40, receive_to_result_ms:20}});
  assert.ok(!/stored inference/.test(facts), 'the facts line never says stored inference over a live frame: ' + facts);
  assert.ok(/persons 2\b/.test(facts) && /cloth 0\b/.test(facts) && /balls 0\b/.test(facts), 'and counts only what is drawn: ' + facts);
  // No live detector on: nothing at all.
  T.state.live.detections = null;
  T.paintOverlay();
  assert.ok(!/<(g|polygon|rect|circle)\b/.test(svg.innerHTML), 'no detections, nothing drawn: ' + svg.innerHTML.slice(0, 120));
  // The operator stops the source: the stage goes back to the dataset frame it
  // held, and that frame's layers return untouched.
  T.state.live.state = 'running';
  sandbox.window.CornerPocketReview.applyLiveStatus({state:'stopped', frames_skipped:0});
  assert.strictEqual(T.state.source.kind, 'vod', 'a stop returns the stage to the dataset frame');
  T.state.unified = frame0;           // the frame's unified answer, re-read after the stop
  T.paintOverlay();
  assert.strictEqual(svg.innerHTML, vodHtml, 'the dataset frame\'s layers come back exactly');
  assert.strictEqual(snapshot().corrections.storedInference, true);
  // A feed that stalls or ends is not a stop: its last frame stays, still live.
  T.state.source = {kind:'live', label:'VOD replay 1000000011', channel:null};
  T.state.live.state = 'running';
  sandbox.window.CornerPocketReview.applyLiveStatus({state:'eos', frames_skipped:0});
  assert.strictEqual(T.state.source.kind, 'live', 'end of stream keeps the last live frame on the stage');
  T.state.source = {kind:'vod', label:'vod30', channel:null}; T.state.live.state = 'idle';
  T.state.fresult = null; T.state.boxes = []; T.state.polygon = null; T.state.unified = null; T.state.live.detections = null;
  T.state.cloth.reference = null; T.state.anchors.loaded = false; T.state.anchors.pts = [];
});

test('the saved-anchor pockets and anchor marks never land on a live picture, whatever the source flag says', () => {
  // Production, 2026-09-26: the owner's live frame carried six CALIB pocket markers
  // that never moved. The pockets came from the dataset's saved anchors whenever the
  // engine's source still read 'vod' - and a live picture is on the stage under a
  // 'vod' source after a live error and a Stop, after a dataset chip click while the
  // feed runs, and while Vision mounts during a running session. The overlay has to
  // follow the picture that is actually on the stage.
  const svg = {dataset:{}, innerHTML:'', querySelectorAll: () => []};
  const note = {hidden:true, textContent:'', dataset:{}, classList:{toggle() {}}};
  const img = {hidden:false, _src:'', getAttribute() { return this._src; }};
  Object.defineProperty(img, 'src', {get() { return this._src; }, set(value) { this._src = value; }});
  svg.setAttribute = () => {}; svg.dataset.bound = '1';
  const content = {dataset:{stage:'1'}, innerHTML:''};   // a mounted stage: renderStage() runs for real
  T.setRoot({lang:'en', dataset:{}, querySelector: selector => ({'#t-overlay': svg, '#stage-note': note, '#t-img': img, '#content': content})[selector] || null, querySelectorAll: () => []});
  const review = sandbox.window.CornerPocketReview;
  T.state.dataset = 'vod30'; T.state.frame = 0; T.state.frameWidth = 1280; T.state.frameHeight = 720;
  T.state.overlay = {cloth:true, balls:true, persons:true, pockets:true, anchors:true, events:true};
  T.state.sel = {kind:'none', crop:null, ball:null, person:null, track:null, anchor:0, event:null, box:-1};
  T.state.playback = {on:false, playing:false, event:null, from:0, to:0, loops:0, seek:NaN};
  T.state.fresult = null; T.state.boxes = []; T.state.polygon = null; T.state.unified = null;
  // The dataset's saved-anchor document is loaded, and the anchors layer is on.
  T.state.cloth.reference = {points:[[454.9,307.8],[799.5,319.4],[1023.8,573.1],[449.6,563.5],[448.4,402.9],[883.9,413.3]], source:'saved anchors', width:1280, height:720};
  T.state.anchors.loaded = true; T.state.anchors.pts = [[100,100],[200,100],[200,200],[100,200],[150,100],[150,200]];
  const layers = () => ({pockets:(svg.innerHTML.match(/class="u-pocket"/g) || []).length, calib:(svg.innerHTML.match(/data-src="calib"/g) || []).length,
                         anchors:(svg.innerHTML.match(/class="u-anchor/g) || []).length, cloth:(svg.innerHTML.match(/class="u-cloth"/g) || []).length});
  // Frame 0 on the stage: its calibration pockets and anchor marks are its own.
  T.state.source = {kind:'vod', label:'vod30', channel:null}; T.state.shotUrl = 'blob:frame0'; img.src = 'blob:frame0';
  T.paintOverlay();
  const frameHtml = svg.innerHTML;
  same(layers(), {pockets:6, calib:7, anchors:6, cloth:1});
  // Vision mounts while a session runs: the first live frame lands before the stage
  // has its picture element; the stage built after it shows that frame, not frame 0.
  const noStage = {lang:'en', dataset:{}, querySelector: () => null, querySelectorAll: () => []};
  T.setRoot(noStage);
  T.state.live.state = 'running';
  review.ingestLiveFrame('blob:live-0', {seq:0, detections:{boxes:[], table_polygon:null}}, {label:'live', channel:null});
  assert.ok(T.stageHTML().includes('src="blob:live-0"'), 'a stage built after the first live frame shows that frame');
  T.setRoot({lang:'en', dataset:{}, querySelector: selector => ({'#t-overlay': svg, '#stage-note': note, '#t-img': img, '#content': content})[selector] || null, querySelectorAll: () => []});
  T.state.source = {kind:'vod', label:'vod30', channel:null}; T.state.live.state = 'idle'; T.state.live.shown = null;
  // The live feed runs; its detector measured a quad and it was refused (as on 09-26).
  T.state.live.state = 'running';
  review.ingestLiveFrame('blob:live-1', {seq:1, detections:{boxes:[{label:'person', bbox:[500,200,600,500]}], table_polygon:[[0,0],[10,0],[10,10],[0,10]]}}, {label:'● live · twitch examplechannel', channel:'examplechannel'});
  same(layers(), {pockets:0, calib:0, anchors:0, cloth:0}, 'the live frame: no saved-anchor pockets, marks or quad');
  assert.strictEqual(T.state.drawn.pockets, 0); assert.strictEqual(T.state.drawn.anchors, 0);
  // (1) The picture is live but the source flag says 'vod' (mount order; a dataset
  // chip clicked while the feed runs; Stop after a live error): still nothing.
  T.state.source = {kind:'vod', label:'vod30', channel:null};
  T.paintOverlay();
  same(layers(), {pockets:0, calib:0, anchors:0, cloth:0}, 'a live picture under a vod source flag gets no dataset layers');
  assert.strictEqual(T.state.drawn.pockets, 0, 'and the facts line counts none');
  assert.strictEqual(T.state.drawn.anchors, 0);
  T.state.source = {kind:'live', label:'● live · twitch examplechannel', channel:'examplechannel'};
  // A re-render while live (a language switch, a rebuilt stage markup) keeps the live
  // picture: the dataset still never slips under the live overlay.
  T.state.source = {kind:'live', label:'● live · twitch examplechannel', channel:'examplechannel'};
  const vmeta = T.state.vmeta; T.state.vmeta = vmeta || {width:1280, height:720, fps:30, duration:1800, frame_count:54000};
  review.setAppearance('zh', 'dark');           // a language switch re-renders the stage
  assert.strictEqual(img.src, 'blob:live-1', 'a re-render keeps the live picture');
  review.setAppearance('en', 'dark');
  T.state.vmeta = vmeta;
  assert.ok(T.stageHTML().includes('src="blob:live-1"'), 'and so does a rebuilt stage');
  same(layers(), {pockets:0, calib:0, anchors:0, cloth:0});
  // (2) The feed dies (state error, the last live picture stays), then the operator stops.
  review.applyLiveStatus({state:'error', error:'Live stream ended or read timed out; restart to reconnect', frames_skipped:0});
  T.paintOverlay();
  same(layers(), {pockets:0, calib:0, anchors:0, cloth:0}, 'a dead feed keeps its last live picture without dataset layers');
  review.applyLiveStatus({state:'stopped', frames_skipped:0});
  assert.strictEqual(T.state.source.kind, 'vod', 'a stop after an error hands the stage back as well');
  assert.strictEqual(img.src, 'blob:frame0', 'with the dataset picture on it');
  T.paintOverlay();
  assert.strictEqual(svg.innerHTML, frameHtml, 'frame 0\'s layers come back byte-identical');
  // (3) A live measured quad that passes its check: its pockets are the model's own.
  T.state.live.state = 'running';
  review.ingestLiveFrame('blob:live-2', {seq:2, detections:{boxes:[], table_polygon:[[455,308],[799,320],[1023,573],[450,563]], pockets:[{name:'head-left', cx:455, cy:308}]}}, {label:'live', channel:'examplechannel'});
  assert.ok(!svg.innerHTML.includes('data-src="calib"'), 'never a CALIB tag on a live frame');
  assert.strictEqual((svg.innerHTML.match(/class="u-anchor/g) || []).length, 0, 'never a saved anchor mark on a live frame');
  review.applyLiveStatus({state:'stopped', frames_skipped:0});
  T.state.source = {kind:'vod', label:'vod30', channel:null}; T.state.live.state = 'idle'; T.state.live.detections = null; T.state.shotUrl = null;
  T.state.cloth.reference = null; T.state.anchors.loaded = false; T.state.anchors.pts = [];
});

test('a running Twitch channel has its chat toggle and embed, named by the processor', () => {
  // Production, 2026-09-26: the owner's channel ran live and the page had no chat
  // iframe at all. The inspector took the channel only from the shell's label for the
  // frame, and that label is built from the Source picker - which stays on the
  // dataset when the session was started elsewhere or the page was reloaded. The
  // processor's own status names the channel it is reading.
  let chatOn = true;
  const toggles = [];
  const VSc = adapterStage('en', ROSTER, {chat: () => chatOn, toggleChat: () => { toggles.push(1); chatOn = !chatOn; }});
  const running = {...visionSnapshot().live, state:'running', source:{kind:'twitch', source_id:'77777777777777777777777777777777', channel:'examplechannel'}, replay:null};
  // The frame arrived with no channel from the shell (its picker said dataset:vod30).
  const shot = visionSnapshot({source:{kind:'live', label:'● live · dataset vod30', channel:null}, live:running});
  const html = VSc.inspectorHTML(shot);
  const frame = (html.match(/<iframe[^>]*src="([^"]+)"/) || [])[1] || '';
  assert.ok(frame.startsWith('https://www.twitch.tv/embed/examplechannel/chat?parent=127.0.0.1'), 'the chat embed names the running channel and this host: ' + (frame || html.slice(0, 160)));
  assert.ok(/data-vs-action="chat"[^>]*>Hide chat</.test(html), 'with a toggle that says what it does');
  chatOn = false;
  const hidden = VSc.inspectorHTML(shot);
  assert.ok(!hidden.includes('<iframe'), 'hidden: no embed');
  assert.ok(/data-vs-action="chat"[^>]*>Show chat</.test(hidden), 'and the toggle offers it back');
  // A VOD replay and a dataset feed have no chat to show.
  const replay = visionSnapshot({source:{kind:'live', label:'VOD replay 1000000001', channel:null},
                                 live:{...running, source:{kind:'vod-replay', vod_id:'1000000001', start_s:600, rate:1}}});
  chatOn = true;
  assert.ok(!/<iframe|data-vs-action="chat"/.test(VSc.inspectorHTML(replay)), 'a replay has no chat');
  assert.ok(!/<iframe|data-vs-action="chat"/.test(VSc.inspectorHTML(visionSnapshot())), 'a dataset frame has no chat');
});

test('the VOD fields are reachable and keep what the operator typed', () => {
  // (1) The panel used to list the replay controls last, so at 1280x900 the button
  // sat below the panel's own scroll box: elementFromPoint on it returned the
  // frame-index input and a mouse click never reached it. The block is first now.
  const panel = adapterStage('en', ROSTER).sourcePanelHTML(visionSnapshot());
  assert.ok(panel.indexOf('data-vs-replay=') > 0 || panel.indexOf('data-vs-field="vod"') > 0, 'the replay block is in the panel');
  assert.ok(panel.indexOf('data-vs-field="vod"') < panel.indexOf('data-vs-action="pick-dataset"'),
    'and it comes before the dataset block, so its controls are inside the panel\u2019s visible box');
  assert.ok(panel.indexOf('data-vs-action="pick-replay"') < panel.indexOf('id="source-form"'),
    'above the saved-channels form too');
  // (2) The value lives in adapter state, not only in the DOM: the panel is rebuilt
  // on every live-status poll, and a half-typed id used to vanish with it.
  const VS = adapterStage('en', ROSTER);
  VS.onInput({target: {dataset: {vsField: 'vod'}, closest: () => null, value: 'https://www.twitch.tv/videos/1000000011'}});
  VS.onInput({target: {dataset: {vsField: 'vod-start'}, closest: () => null, value: '30'}});
  const again = VS.sourcePanelHTML(visionSnapshot());
  assert.ok(again.includes('value="https://www.twitch.tv/videos/1000000011"'), 'the typed id survives a rebuild');
  assert.ok(/data-vs-field="vod-start"[^>]*value="30"/.test(again), 'and so does the start offset');
  VS.act('source-panel');   // the panel is open while an id is being typed
  assert.ok(VS.chipsHTML(visionSnapshot()).includes('value="https://www.twitch.tv/videos/1000000011"'),
    'including a chips re-render, which is what the poll triggers');
  assert.ok(ADAPTER_SOURCE.includes('document.activeElement') && ADAPTER_SOURCE.includes('setSelectionRange'),
    'and a focused field keeps its focus and caret across that rebuild');
});

test('F2: the Anchors chip reads off until anchors are drawn, and one click loads them', () => {
  const calls = [];
  let s = visionSnapshot({dataset:'vod30', overlay:{cloth:true, balls:true, persons:true, pockets:true, anchors:true, events:true},
                          anchors:{loaded:false, pts:[], index:0}, events:{items:[], index:0, reviewed:0}, balls:{items:[], index:0},
                          playback:{on:false, event:null, from:0, to:0, loops:0, playing:false}});
  const review = {snapshot: () => s,
                  toggleOverlay: kind => { calls.push('toggle ' + kind); s.overlay[kind] = !s.overlay[kind]; return s.overlay[kind]; },
                  loadAnchors: t => { calls.push('load ' + t); return Promise.resolve(); },
                  selectAnchor() {}, seekTime() {}};
  const VSx = adapterStage('en', ROSTER, {review});
  assert.ok(ADAPTER_SOURCE.includes("(key !== 'anchors' || s.anchors.loaded)"), 'the chip is on only when anchors are loaded');
  assert.ok(ADAPTER_SOURCE.includes('aria-pressed="${shown ? \'true\' : \'false\'}"'), 'and says so to a screen reader');
  VSx.act('layer', 'anchors');
  assert.deepStrictEqual(calls, ['load 70'], 'the first click loads the anchors; it does not switch the layer off');
  assert.strictEqual(s.overlay.anchors, true, 'and the layer stays on');
  s.anchors.loaded = true;
  VSx.act('layer', 'anchors');
  assert.deepStrictEqual(calls, ['load 70', 'toggle anchors'], 'once drawn, a click hides them as before');
});

test('clarify: one pocket name per card, the distance with its error, reasons in words beside their codes', () => {
  const pot = {id:9005, type:'pot', t:1553.5, color:'blue', nearest_pocket:'right-side (148 ± 54mm)',
               gate:{status:'unconfirmed', gate:'occlusion', reasons:['cloth_occluded_at_disappearance', 'pocket_test_agrees'],
                     numbers:{vanish_dist_mm:148.49, vanish_dist_mm_uncertainty:54.2, vanish_pocket:'right-side'}}};
  const words = {'right-side':['right-middle','右中']}, colours = {blue:['blue','蓝']};
  for (const [lang, pocket, colour, reason] of [['en', 'right-middle', 'blue', 'a person covered the cloth when the ball vanished'],
                                                ['zh', '右中', '蓝', '球消失时有人挡住了台呢']]) {
    const review = {snapshot: () => null, text: s => s,
                    pocketText: v => (words[String(v).replace(/ \(.*\)$/, '')] || [v, v])[lang === 'zh' ? 1 : 0],
                    colourWord: v => (colours[v] || ['', ''])[lang === 'zh' ? 1 : 0]};
    const VSx = adapterStage(lang, ROSTER, {review});
    same(VSx.gateEvidence(pot), [`148 ± 54 mm · ${pocket}`]);
    const card = VSx.railHTML({eventFilter:'all', selection:{}, focus:'events', events:{items:[pot], index:0, reviewed:0},
      balls:{items:[], index:0}, persons:{tracks:[], windows:[], win:null}, frame:{}, source:{}, live:{}});
    const row = card.match(/<div class="vs-card-row">[\s\S]*?<\/div>/)[0];
    assert.ok(row.includes(`>${pocket}<`), `${lang}: the card names the pocket once, as a position word`);
    assert.ok(!card.includes('right-side') && !/\(148 ± 54mm\)/.test(card), `${lang}: no second spelling of the same pocket`);
    const inspector = VSx.eventGeometry(pot);
    assert.ok(inspector.includes(`148 ± 54 mm · ${pocket}`), `${lang}: the inspector reads the same distance`);
    assert.ok(inspector.includes(`${reason} (cloth_occluded_at_disappearance)`), `${lang}: reasons in words, the code kept as evidence`);
    assert.ok(inspector.includes(colour), `${lang}: the colour is a word, not a raw key`);
  }
});

test('F5: a saved VOD URL is listed, can fill the replay form, and can be removed', () => {
  const vods = () => [{id:'s9', url:'https://www.twitch.tv/videos/1234567890', video:'1234567890'}];
  const VSx = adapterStage('en', ROSTER, {vods, forgetChannel() {}});
  const panel = VSx.sourcePanelHTML(visionSnapshot());
  assert.ok(panel.includes('Saved VODs') && panel.includes('https://www.twitch.tv/videos/1234567890'), 'the saved VOD is listed');
  assert.ok(panel.includes('data-vs-action="use-saved-vod" data-vs-value="1234567890"'), 'with a Use button');
  assert.ok(panel.includes('data-vs-action="forget-channel" data-vs-id="s9"'), 'and a Remove button');
  const none = adapterStage('en', ROSTER).sourcePanelHTML(visionSnapshot());
  assert.ok(!none.includes('Saved VODs'), 'no heading when nothing is saved');
  const shell = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'ops.js'), 'utf8');
  assert.ok(shell.includes("parsed.kind==='vod'?{id:s.id,url:s.url,video:parsed.video}") && shell.includes('channels,vods,regulars'),
    'the shell passes saved VODs to the adapter');
  assert.strictEqual((ADAPTER_SOURCE.match(/savedVods:'/g) || []).length, 2, 'the heading exists in both languages');
});

test('F6: Use this VOD with an empty id says what to do instead of doing nothing', () => {
  for (const [lang, sentence] of [['en', 'Enter a Twitch VOD id or URL first.'], ['zh', '请先输入 Twitch 回放 id 或网址。']]) {
    const notices = [], picked = [];
    const VSx = adapterStage(lang, ROSTER, {notice: text => notices.push(text), pickReplay: choice => picked.push(choice)});
    VSx.act('pick-replay');
    assert.deepStrictEqual(notices, [sentence], `${lang}: one notice, a sentence, not the field label`);
    assert.strictEqual(picked.length, 0, 'and no replay is requested');
  }
  const shell = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'ops.js'), 'utf8');
  assert.ok(shell.includes('notice:text=>message(text,true)'), 'the shell passes notice, so the adapter is heard');
});

function VSrail({events, lang = 'en'}) {
  return adapterStage(lang, ROSTER).railHTML({eventFilter:'all', selection:{}, focus:'events',
    events:{items: events, index: 0, reviewed: 0}, balls:{items:[], index:0},
    persons:{tracks:[], windows:[], win:null}, frame:{}, source:{}, live:{}});
}
const VS = adapterStage('en', ROSTER);   // one handle for the pure formatters

test('a machine-produced candidate says so on its card, and an event without provenance says nothing', () => {
  const shot = {id:9002, type:'shot', t:1580.1, color:'blue', tier:'window',
                provenance:{detector:'dense-track · trained 960×540 net @ ball@2', machine_produced:true, human_confirmed:false,
                            statement:'machine-produced candidate; no human has confirmed it', ball_id:'t193-blue'},
                gate:{status:'confirmed', gate:'motion', reasons:['dense_motion_onset'], tier:'window',
                      numbers:{disp_mm:1308, disp_color:'blue', dense_net_displacement_px:159.1, dense_path_length_px:159.86,
                               dense_peak_speed_px_s:491.63, dense_duration_s:0.733326}}};
  const rail = VSrail({events:[shot]});
  assert.ok(rail.includes('data-vs-provenance="machine"'), 'the provenance line is rendered');
  assert.ok(rail.includes('dense-track · trained 960×540 net @ ball@2'), 'with the detector that produced it');
  // Round 1 (pins changed deliberately): the card leads with plain words that keep the honesty
  // ("not yet confirmed by a person"); the detector and the stored statement stay one step away,
  // in the line's title (hover) and a visually hidden span (screen readers), never removed.
  assert.ok(rail.includes('>suggested by the computer · not yet confirmed by a person'), 'the plain statement is what the operator reads');
  assert.ok(rail.includes('machine-produced candidate; no human has confirmed it'), 'and its own stored statement is kept (title)');
  assert.ok(/title="detected by: dense-track · trained 960×540 net @ ball@2/.test(rail), 'the detector is one hover away');
  assert.ok(!rail.includes('undefined'), 'and never the word undefined');
  // Quieter than the badge: the tier badge is a .vs-badge, provenance is a footnote.
  assert.ok(rail.includes('vs-badge tier-window') && rail.includes('class="vs-prov"'), 'the two are different elements');
  const zh = VSrail({events:[shot], lang:'zh'});
  assert.ok(zh.includes('电脑识别的候选 · 尚未经人工确认'), '中 renders the plain statement in Chinese: ' + zh.slice(zh.indexOf('vs-prov'), zh.indexOf('vs-prov') + 120));
  assert.ok(zh.includes('dense-track · trained 960×540 net @ ball@2'), 'and keeps the detector name, which is machine vocabulary');
  // Absent provenance renders nothing at all - not an empty line, not "undefined".
  const bare = VSrail({events:[{id:7, type:'shot', t:5.0, tier:'geometry'}]});
  assert.ok(!bare.includes('data-vs-provenance'), 'no provenance block, no line');
  assert.ok(!bare.includes('vs-prov'), 'and no empty footnote either');
  assert.ok(!bare.includes('undefined'), 'and never undefined');
  // A candidate a human confirmed says that instead.
  const confirmed = VSrail({events:[{...shot, provenance:{...shot.provenance, human_confirmed:true}}]});
  assert.ok(confirmed.includes('data-vs-provenance="human"') && confirmed.includes('confirmed by a person'),
    'a human-confirmed candidate says so');
  // The inspector's gate block carries the pair that separates a shot from jitter.
  const numbers = VS.eventGeometry(shot);
  assert.ok(numbers.includes('Net move / path') && numbers.includes('159.1 / 159.9 px'), 'net vs path is in the gate block: ' + numbers);
  assert.ok(numbers.includes('Peak speed') && numbers.includes('492 px/s'), 'with the peak speed and window');
  const jitter = VS.eventGeometry({...shot, gate:{...shot.gate, numbers:{...shot.gate.numbers, dense_net_displacement_px:0.2, dense_path_length_px:80.56}}});
  assert.ok(jitter.includes('0.2 / 80.6 px'), 'a jittery candidate reads 0.2 / 80.6 px');
  const legacy = VS.eventGeometry({id:11, type:'shot', t:9.0, gate:{status:'confirmed', gate:'displacement', reasons:[], numbers:{disp_mm:1837}}});
  assert.ok(!legacy.includes('Net move / path'), 'an event without dense numbers grows no row');
  // The engine hands the rail the payload as stored.
  assert.ok(source.includes('provenance: e.provenance && typeof e.provenance === \'object\' ? {...e.provenance} : null'),
    'app.js carries provenance into the event snapshot');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);

