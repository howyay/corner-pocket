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
    playEvent, eventWindow, dropPerFrame, exitPlayback, stageHTML, bindVideo, stageVideo, paintPlayChip,
    staticQuad, CLIP_BEFORE_S, CLIP_AFTER_S};
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
  for (const name of ['mount','activate','deactivate','canLeave','setAppearance','subscribe','snapshot','seek','seekTime','stepFrame','setPlaying','setOverlay','toggleOverlay','selectEvent','playEvent','selectCrop','selectTrack','selectAnchor','selectBox','clearSelection','saveVerdict','labelBall','setSeed','saveAnchors','saveCorrections','runInference','setDataset','applyLiveStatus','ingestLiveFrame','liveStateText','freeze','counts']) assert.ok(api.includes(name), `missing engine API: ${name}`);
  assert.strictEqual(api.length, 62, 'the engine exposes exactly its lifecycle + one-stage API');
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
  assert.ok(fresh.includes('quad drift vs saved corners 6.4 px (tol 40 px)'), fresh);
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
  assert.ok(adapter.includes("data-vs-action=\"seed\" data-vs-value=\"A\""), 'the person footer keeps the seed actions');
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
  assert.ok(ok.includes('quad drift vs saved corners 5.7 px (tol 40 px)'), 'O ' + ok);
  assert.ok(!ok.includes('refused') && !ok.includes('fallback'), 'O2 ' + ok);
  // The stored-inference polygon names itself instead of hiding inside the total.
  const inference = V.factsLine({...base, cloth:{...base.cloth, polygon:'inference', quad:null, verdict:{state:'none'}},
                                 drawn:{cloth:1, balls:0, persons:0, pockets:0, anchors:0, events:0, auto:{cloth:1, balls:0, persons:0, pockets:0, anchors:0, events:0}}});
  assert.ok(inference.includes('cloth 1 (stored inference)'), 'I ' + inference);
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
  for (const needle of ['.stage > video', '.stage > video[hidden]', '.stage > svg']) {
    assert.ok(css.includes(needle), `missing stage video css: ${needle}`);
  }
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

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
