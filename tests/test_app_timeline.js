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
  const api = Object.keys(sandbox.window.CornerPocketReview);
  for (const name of ['mount','activate','deactivate','canLeave','setAppearance','subscribe','snapshot','seek','seekTime','stepFrame','setPlaying','setOverlay','toggleOverlay','selectEvent','selectCrop','selectTrack','selectAnchor','selectBox','clearSelection','saveVerdict','labelBall','setSeed','saveAnchors','saveCorrections','runInference','setDataset','applyLiveStatus','ingestLiveFrame','liveStateText','freeze','counts']) assert.ok(api.includes(name), `missing engine API: ${name}`);
  assert.strictEqual(api.length, 61, 'the engine exposes exactly its lifecycle + one-stage API');
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

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
