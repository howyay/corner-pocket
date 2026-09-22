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
    correctionScope, sourceTag, sourceTagLabel, personChip, applyFrameResult, paintOverlay, clothNotice, loadClothReference};
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
  same(T.state.boxes, [{label:'ball', bbox:[5,5,20,20]}]);
  assert.strictEqual(T.state.polygon, null);
  assert.strictEqual(T.state.cloth.refusal.ok, false);
  assert.strictEqual(T.state.cloth.refusal.owner, 'vod30 frame 2100 @ 1280×720');
  // The same correction on its own frame is kept and counted as manual.
  T.state.fresult = {inference:null, correction:{...good, boxes:[{label:'person', bbox:[9,9,99,99]}]}};
  T.applyFrameResult();
  assert.strictEqual(T.state.cloth.refusal, null);
  same(T.state.boxes, [{label:'person', bbox:[9,9,99,99]}]);
  same(T.state.polygon, [[0,0],[10,0],[10,10],[0,10]]);
  T.state.fresult = null; T.state.boxes = []; T.state.polygon = null;
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
  const clean = context.window.VisionStage.factsLine({...base, drawn:{...base.drawn, cloth:1, pockets:6, auto:{...base.drawn.auto, cloth:1, pockets:6}}, cloth:null});
  assert.ok(clean.includes('cloth 1') && clean.includes('pockets 6') && !clean.includes('quad'), clean);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
