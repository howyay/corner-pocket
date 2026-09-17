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
    setRoot: host => { root = host; }, onKeydown, text, translateEditor, updateOverlayFacts};
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
  same(Object.keys(sandbox.window.CornerPocketReview), ['mount','activate','deactivate','canLeave','setAppearance']);
  assert.strictEqual(sandbox.state, undefined);
  assert.strictEqual(sandbox.window.CornerPocketReview.activate('events'), false);
});

test('mount initializes once and standalone mounts only its own host', () => {
  let requests = 0, bindings = 0, rootPresent = false;
  const host = {id:'review-root', dataset:{}, querySelector: () => elementStub(), querySelectorAll: () => [], addEventListener() { bindings++; }};
  const context = {document:{querySelector: () => rootPresent ? host : null}, window:{addEventListener() {}}, fetch() { requests++; return new Promise(() => {}); }, console};
  vm.createContext(context);
  vm.runInContext(source, context);
  assert.strictEqual(requests, 0);
  const review = context.window.CornerPocketReview;
  const mounting = review.mount(host);
  assert.strictEqual(review.mount(host), mounting);
  assert.strictEqual(requests, 1);
  assert.strictEqual(bindings, 2);
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

test('displayBoxes prefers manual correction over inference and copies data', () => {
  const inference = {boxes: [{label: 'person', bbox: [1, 2, 3, 4], score: 0.9}], table_polygon: [[0, 0], [1, 0], [1, 1], [0, 1]]};
  const correction = {boxes: [{label: 'cue', bbox: [5, 6, 7, 8]}], table_polygon: null};
  const display = T.displayBoxes({inference, correction});
  assert.strictEqual(display.source, 'manual corrections');
  same(display.boxes, [{label: 'cue', bbox: [5, 6, 7, 8]}]);
  const inferred = T.displayBoxes({inference, correction: null});
  assert.strictEqual(inferred.source, 'inference');
  same(inferred.boxes, [{label: 'person', bbox: [1, 2, 3, 4], score: 0.9}]);
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
    "'/api/inference',", "'/api/frame-correction',", '/media/${enc(state.dataset)}/video',
    'X-Frame-Index', 'X-Timestamp-Seconds', 'X-Timestamp-Kind', 'X-Frame-Width', 'X-Frame-Height',
    'LOCAL INGESTED VOD ONLY', 'cannot detect shots or pots', 'Balls · SAM3 on CPU (slow)'
  ]) assert.ok(source.includes(needle), `missing contract fragment: ${needle}`);
});

test('app.html registers the timeline mode button', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'app.html'), 'utf8');
  assert.ok(html.includes('data-mode="timeline"'));
  assert.ok(html.includes('Video timeline'));
});

test('app.css styles the timeline pieces', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'annotator', 'app.css'), 'utf8');
  for (const needle of ['.timeline-grid', '.scrub-mark', '.scrub-marks', '.transport', '.draw-preview', '.t-poly', '.center-dot']) {
    assert.ok(css.includes(needle), `missing css: ${needle}`);
  }
});

test('editor translation preserves dirty values, focus, selection and pending save state', () => {
  const caption = {nodeType:3, nodeValue:'Save review'};
  const optionText = {nodeType:3, nodeValue:'correct'};
  const button = {tagName:'BUTTON', childNodes:[caption], disabled:true};
  const option = {tagName:'OPTION', childNodes:[optionText], value:'correct', hasAttribute: () => false, setAttribute(name, value) { this[name] = value; }};
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
  assert.strictEqual(caption.nodeValue, '保存复核');
  assert.strictEqual(optionText.nodeValue, '正确');
  assert.strictEqual(option.value, 'correct');
  assert.strictEqual(note.value, 'Save review — my raw note');
  assert.strictEqual(note.selectionStart, 4); assert.strictEqual(note.selectionEnd, 9);
  assert.strictEqual(sandbox.document.activeElement, note);
  assert.strictEqual(button.disabled, true); assert.strictEqual(JSON.stringify(T.state), before);
  host.lang = 'en'; T.translateEditor();
  assert.strictEqual(caption.nodeValue, 'Save review');
  assert.strictEqual(note.placeholder, 'What does the source actually show?');
  host.lang = 'zh'; caption.nodeValue = 'Saving…'; T.translateEditor();
  assert.strictEqual(caption.nodeValue, '保存中…');
  caption.nodeValue = 'Save review'; onMutation();
  assert.strictEqual(caption.nodeValue, '保存复核');
  assert.strictEqual(T.text('Save failed: HTTP 409: abc_xyz. Your changes remain on screen; retry when ready.'), '保存失败：HTTP 409: abc_xyz。更改仍保留在屏幕上，可稍后重试。');
  assert.strictEqual(T.text('abc_xyz'), 'abc_xyz');
  const frameNode = {nodeType:3, nodeValue:'RAW DECODED FRAME · vod30 · frame 100 · nominal 4.000s (nominal_cfr) · OVERLAYS: inference'};
  const facts = {tagName:'DIV', childNodes:[frameNode], firstChild:frameNode, get textContent() { return frameNode.nodeValue; }, set textContent(value) { frameNode.nodeValue = value; }};
  const selectors = host.querySelectorAll;
  host.querySelectorAll = selector => selector.includes('[aria-label]') || selector.includes('[placeholder]') ? [] : [facts];
  host.querySelector = () => facts;
  T.translateEditor(); T.updateOverlayFacts('manual corrections'); onMutation();
  assert.strictEqual(frameNode.nodeValue, '原始解码帧 · vod30 · 帧 100 · 名义时间 4.000s (nominal_cfr) · 叠加层：人工修正');
  host.lang = 'en'; T.translateEditor();
  assert.strictEqual(frameNode.nodeValue, 'RAW DECODED FRAME · vod30 · frame 100 · nominal 4.000s (nominal_cfr) · OVERLAYS: manual corrections');
  host.lang = 'zh'; host.querySelectorAll = selectors;
  assert.strictEqual(T.text('Track track_8 · prediction: A · saved seed: B'), '轨迹 track_8 · 预测：A · 已保存种子：B');
  assert.strictEqual(T.text('Status: failed — MODEL_PATH=/tmp/a'), '状态：失败 — MODEL_PATH=/tmp/a');
  assert.strictEqual(T.text('RAW DECODED FRAME · vod30 · frame 100 · nominal 4.000s (nominal_cfr) · OVERLAYS: manual corrections'), '原始解码帧 · vod30 · 帧 100 · 名义时间 4.000s (nominal_cfr) · 叠加层：人工修正');
  assert.strictEqual(T.text('Inference running for frame 100: SAM3_CPU…'), '正在对帧 100 运行推理：SAM3_CPU…');
  T.state.dirty = false; T.state.busy = false;
});

test('browser regression: anchor spans, padded track label and box option values', () => {
  const rows = ['1. Top left','2. Top right','3. Bottom right','4. Bottom left','5. Left side','6. Right side'];
  const nodes = rows.map(nodeValue => ({nodeType:3, nodeValue}));
  const track = {nodeType:3, nodeValue:'Track window '};
  const options = ['solid','stripe','eight'].map(value => ({tagName:'OPTION', value, childNodes:[{nodeType:3,nodeValue:value}], hasAttribute: () => true}));
  const host = {lang:'zh', querySelectorAll(selector) {
    if (!selector.includes('[data-point] span')) return [];
    return [...nodes.map(node => ({childNodes:[node]})), {childNodes:[track]}, ...options];
  }};
  T.setRoot(host); T.translateEditor();
  same(nodes.map(node => node.nodeValue), ['1. 左上','2. 右上','3. 右下','4. 左下','5. 左侧','6. 右侧']);
  assert.strictEqual(track.nodeValue, '轨迹窗口 ');
  same(options.map(option => option.value), ['solid','stripe','eight']);
  same(options.map(option => option.childNodes[0].nodeValue), ['实色','花色','黑八']);
  const hint = 'Drag boxes or corner handles; arrow keys nudge the selected box (Shift = 10 px). Ball centers follow their box. Drag table polygon corners. Saving writes manual corrections for this exact frame; saved inference is never overwritten.';
  assert.strictEqual(T.text(hint), '拖动标注框或角点控制柄；方向键微调所选框（Shift = 10 像素）。球心随标注框移动。可拖动球桌多边形角点。保存仅写入此精确帧的人工修正，绝不覆盖已保存的推理结果。');
  host.lang = 'en'; T.translateEditor();
  same(nodes.map(node => node.nodeValue), rows);
  assert.strictEqual(track.nodeValue, 'Track window ');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
