'use strict';
// Run: node --test tests/test_ops.js. No DOM or network dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {domNode} = require('./dom_stubs.js');
const source = fs.readFileSync(path.join(__dirname, '../annotator/ops.js'), 'utf8');
const clockSync = require('../annotator/clock-sync.js');
const clockSyncSource = fs.readFileSync(path.join(__dirname, '../annotator/clock-sync.js'), 'utf8');
const stageSource = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
// Round 41: python owns the identity of a refusal (annotator/refusals.py). The console holds no
// sentence table at all, so a test that checks the Chinese sentence reads the row from that file
// and passes it the way the service sends it. One owner means one place to change a sentence: a
// rewording in python changes what these tests read, and no copy in javascript can go stale.
function refusalRow(sentence) {
  const rows = fs.readFileSync(path.join(__dirname, '../annotator/refusals.py'), 'utf8').split('\n');
  const line = rows.find(row => row.includes('Refusal(') && (row.includes(`'${sentence}'`) || row.includes(`"${sentence}"`)));
  assert.ok(line, `annotator/refusals.py holds no refusal row for: ${sentence}`);
  const parsed = line.match(/Refusal\(\s*(['"])([a-z_]+)\1\s*,\s*(['"])(.*)\3\s*\)/);
  assert.ok(parsed, `the refusal row does not parse: ${line.trim()}`);
  return {code: parsed[2], zh: parsed[4]};
}
// The workbench markup is the stage's own, built into the host the console hands attach(). These
// tests take the shell the way the console does - attach() on a host stub - so what they read is
// the markup the browser gets, not a string this file asked for. The clock is the console's part of
// it: it travels as a callback, so the shell carries the console's own instant.
const consoleClock = h => () => ({title: h.t('shotTimer'), text: h.clockText(h.clockLeft()), low: !!h.clockLow(h.clockLeft())});
function stageMarkup(h, {lang = 'en', fixed = false} = {}) {
  if (!h.context.window.VisionStage) vm.runInContext(stageSource, h.context);
  const mount = stageMountStub();
  const review = {snapshot: () => null, subscribe: () => () => {}, reloadDatasets: async () => true};
  h.context.window.CornerPocketReview = review;
  h.context.window.VisionStage.attach({mount, lang, clock: consoleClock(h), fixedClip: () => fixed,
    channels: () => [], vods: () => [], regulars: () => [], chat: () => false, notice() {}, review});
  return mount.shellHTML();
}
// One stub document with a region per selector, so render() runs as it does in the browser.
function richDocument(handlers) {
  const regions = new Map(), lists = new Map();
  const body = domNode('body');
  const documentElement = {dataset: {}, lang: '', classList: {toggle() {}, add() {}, remove() {}}};
  // The two chip rows and the clock's two live nodes: render() runs a loop over each of them, so the
  // stub answers with nodes that record what the loop wrote.
  const seeds = {
    '[data-lang]': [{lang: 'en'}, {lang: 'zh'}],
    '#ops-shell button[data-theme]': [{theme: 'dark'}, {theme: 'light'}],
    '[data-clock]': [{}],
    '[data-progress]': [{}]
  };
  const list = selector => {
    if (!lists.has(selector)) lists.set(selector, (seeds[selector] || []).map(seed => {
      const node = domNode(selector);
      Object.assign(node.dataset, seed);
      return node;
    }));
    return lists.get(selector);
  };
  return {
    addEventListener(event, fn) { handlers[event] = fn; },
    querySelector(selector) {
      if (selector === '#ops-shell') return null;      // the shell state stays observable instead
      if (!regions.has(selector)) regions.set(selector, domNode(selector));
      return regions.get(selector);
    },
    querySelectorAll: selector => list(selector),
    createElement: () => domNode(),
    body, documentElement,
    region: selector => regions.get(selector),
    nodes: selector => list(selector)
  };
}
function harness(opts = {}) {
  const handlers = {}, storage = {...opts.storage}, windowHandlers = {}, visits = [], timers = [];
  const document = opts.richDom
    ? richDocument(handlers)
    : {addEventListener(event, fn) { handlers[event] = fn; }, querySelector(selector) { return selector === '#ops-shell' ? null : {}; }, querySelectorAll() { return []; }, documentElement: {dataset: {}, lang: ''}};
  // The URL is a hash route: pushState/replaceState update location.hash, and a test drives back/forward by
  // setting location.hash and calling the captured hashchange listener, as the browser does.
  const location = {hash: opts.hash || ''};
  const history = {pushState(state, title, url) { location.hash = url; visits.push(['push', url]); }, replaceState(state, title, url) { location.hash = url; visits.push(['replace', url]); }};
  const context = {document, location, history, localStorage: {getItem: key => storage[key] || null, setItem: (key, value) => storage[key] = value}, window: {addEventListener(event, fn) { windowHandlers[event] = fn; handlers['window:' + event] = fn; }}, setInterval() {}, setTimeout(fn, ms) { timers.push({fn, ms}); return timers.length }, clearTimeout() {}, URL, console, confirm: () => true, FormData: function(form) { return Object.entries(form.values); }};
  vm.createContext(context);
  // The console runs as the page loads it. The suite does not rewrite its text. The stub page
  // carries no shell, so the console does not boot itself; the test drives it through the handle.
  vm.runInContext(opts.source || source, context, {filename: 'ops.js'});
  const h = context.window.OpsConsole.attach({document});
  // The state the page fetches, and the action channel the tests read instead of the network.
  h.data = {revision: 1, settings: {}, tournament: {raceTo: 7, entrants: [], matches: []}, players: [], history: []};
  h.calls = [];
  h.realAction = h.action;
  h.VmTypeError = vm.runInContext('TypeError', context);
  h.action = async (name, payload) => { h.calls.push({name, payload}); return true };
  return Object.assign(h, {context, handlers, windowHandlers, visits, storage, timers});
}
const tabClick = (h, name) => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {tab: name}}}});
const browserBack = (h, hash) => { h.context.location.hash = hash; h.windowHandlers.hashchange(); };
test('live controls keep the dataset/channel allowlist and the latency caveat', () => {
  const h = harness();
  assert.deepEqual(JSON.parse(JSON.stringify(h.liveSource('dataset:highlight'))), {kind:'dataset', dataset:'highlight'});
  assert.deepEqual(JSON.parse(JSON.stringify(h.liveSource('twitch:saved-id'))), {kind:'twitch', source_id:'saved-id'});
  h.data.sources=[{id:'channel',url:'https://www.twitch.tv/examplechannel'},{id:'vod',url:'https://www.twitch.tv/videos/123'}, {id:'bad',url:'https://example.com/x'}];
  const channels = JSON.stringify(h.channels());
  assert.equal(channels, '[{"id":"channel","url":"https://www.twitch.tv/examplechannel","channel":"examplechannel"}]');
  assert.equal(h.channelOf("channel"), 'examplechannel');
  assert.equal(h.regulars().length, 0);
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  assert.ok(adapter.includes('data-vs-action="live-start"') && adapter.includes('data-vs-action="live-stop"'));
  assert.ok(adapter.includes('data-vs-value="${d}"') && adapter.includes("['table','person','ball']"),
    'the live row offers table, person and the trained ball stage');
  assert.ok(adapter.includes('not glass-to-glass'));
  assert.ok(adapter.includes('data-vs-action="pick-live"'));
});
test('live polling cancels on navigation and only runs inside Vision', () => {
  const h = harness();
  (()=>{h.polls=[]; h.pollLive=g=>h.polls.push(g); h.context.document.querySelector=h.context.document.querySelector||(()=>null); h.tab='vision';return h.syncLivePolling()})();
  assert.equal(h.polls.length, 1);
  (()=>{h.tab='floor';return h.syncLivePolling()})();
  assert.equal(h.polls.length, 1);
  assert.equal(h.liveGeneration, 2);
  (()=>{h.tab='vision';h.context.document.hidden=true;return h.syncLivePolling()})();
  assert.equal(h.polls.length, 1);
  (()=>{h.context.document.hidden=false;return h.syncLivePolling()})();
  assert.equal(h.polls.length, 2);
});
test('live start and stop send only processor contract fields', async () => {
  const h = harness();
  h.context.fetch=async (url,options)=>{h.context.sent={url,payload:JSON.parse(options.body)};return {ok:true,json:async()=>({status:'running'})}};
  await (()=>{h.liveChoice='twitch:channel';h.liveDetectors=['person'];return h.liveAction('start')})();
  assert.deepEqual(h.context.sent,{url:'/api/live',payload:{action:'start',source:{kind:'twitch',source_id:'channel'},detectors:['person']}});
  await h.liveAction('stop');
  assert.deepEqual(h.context.sent.payload,{action:'stop'});
});
// ---- The adapter seam: a test drives the console, not its renderers --------------------------
// A stub mount records the regions the adapter paints, so a test reads the markup the operator
// sees or sends that mount a real click, change or input event.
function stageNodeStub() {
  return {innerHTML: '', textContent: '', value: '', title: '', hidden: false, disabled: false, dataset: {}, attributes: {}, offsetHeight: 1,
    style: {left: '', getPropertyValue: () => '', setProperty() {}},
    classList: {toggle() {}, add() {}, remove() {}},
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getBoundingClientRect: () => ({top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0}),
    focus() {}, setSelectionRange() {}, remove() {}, contains: () => false,
    querySelector: () => null, querySelectorAll: () => [], closest: () => null,
    appendChild(node) {
      const previous = node.parentElement;
      if (previous && Array.isArray(previous.children)) previous.children = previous.children.filter(child => child !== node);
      node.parentElement = this; (this.children = this.children || []).push(node); return node;
    },
    addEventListener() {}, removeEventListener() {}};
}
function stageMountStub() {
  const nodes = new Map(), handlers = {};
  let shell = '';
  return {
    region(selector) { if (!nodes.has(selector)) nodes.set(selector, stageNodeStub()); return nodes.get(selector); },
    // The stage builds its own workbench on the first attach and reuses the one it finds after
    // that, exactly as it does in the browser: an empty host has no .vs-grid yet.
    querySelector(selector) { return selector === '.vs-grid' && !shell ? null : this.region(selector); },
    querySelectorAll: () => [],
    contains: () => true,
    style: {getPropertyValue: () => '', setProperty() {}},
    addEventListener(type, fn) { (handlers[type] = handlers[type] || []).push(fn); },
    removeEventListener(type, fn) { handlers[type] = (handlers[type] || []).filter(f => f !== fn); },
    insertAdjacentHTML(position, markup) { shell += markup; },
    shellHTML: () => shell,
    html(selector) { return this.region(selector).innerHTML; },
    text(selector) { return this.region(selector).textContent; },
    fire(type, target) { for (const fn of handlers[type] || []) fn({type, target, preventDefault() {}, stopPropagation() {}}); },
  };
}
// The clicked node: closest() answers the selectors the adapter asks for.
function stageControlStub(action, value, extra = {}) {
  const dataset = {vsAction: action};
  if (value !== undefined && value !== null && value !== '') dataset.vsValue = String(value);
  return {dataset, value: extra.value === undefined ? '' : extra.value, checked: extra.checked === undefined ? false : extra.checked,
    closest(selector) {
      if (selector === '[data-sheet-tab]') return null;
      if (selector === '[data-vs-action]' || selector === `[data-vs-action="${action}"]`) return this;
      if (selector === '.vs-linkblock') return extra.holder || null;
      return null;
    }};
}
// The Source panel hangs off its chip: open it when it is closed, then read the panel alone.
function openSourcePanel(mount) {
  if (!mount.html('#vs-chips').includes('id="vs-source-panel"')) mount.fire('click', stageControlStub('source-panel'));
}
function sourcePanelHTML(mount) {
  const html = mount.html('#vs-chips'), at = html.indexOf('id="vs-source-panel"');
  return at < 0 ? '' : html.slice(html.lastIndexOf('<', at));
}
// The engine state render() reads. A test overrides only the fields it cares about.
function stageStateStub(over = {}) {
  const base = {
    selection:{kind:'none', box:-1}, source:{kind:'vod', label:'vod30 · 1800 s', channel:null},
    datasets:[{id:'vod30', label:'vod30'}], set:'unlabeled_crops', frame:{index:500, t:20, duration:1800, count:54206, playing:false},
    live:{state:'idle', error:null, attempt:null, frame_age_ms:null, receive_to_result_ms:null, skipped:0, detectors:['table','person'], stale:false, seq:null},
    detectors:{table:true, person:true, balls:false},
    corrections:{tool:'select', newBoxLabel:'ball', box:-1, boxLabel:null, polygon:false, result:'none', dirty:false, inferRunning:false, inferStatus:''},
    dirty:false, notice:{text:''}, receipts:[], busy:false, loading:{overlay:false, since:0}, overlay:{}, drawn:{cloth:0, balls:0, persons:0, pockets:0, anchors:0, events:0},
    cloth:{verdict:{state:'none'}, quad:null, pockets:{}, refusal:null},
    eventFilter:'all', focus:'events',
    events:{items:[], index:0, reviewed:0}, balls:{items:[], index:0},
    anchors:{items:[], points:[], index:0, t:0, loaded:false},
    playback:{on:false, playing:false, event:null, from:0, to:0, loops:1},
    enroll:{status:'idle'},
    persons:{tracks:[], track:null, windows:[{win:'68-94', count:3}], win:'68-94', status:'', predictions:null}};
  const plain = value => value && typeof value === 'object' && !Array.isArray(value);
  for (const [key, value] of Object.entries(over)) base[key] = plain(value) && plain(base[key]) ? {...base[key], ...value} : value;
  return base;
}
// One seam: attach, then set the state, render, read a region or click a control.
function stageSeamStub(h, mount, options = {}) {
  const state = {value: null};
  const review = {snapshot: () => state.value, subscribe: () => () => {}, reloadDatasets: async () => true, ...(options.review || {})};
  h.context.window.CornerPocketReview = review;
  const handle = h.context.window.VisionStage.attach({mount, lang: options.lang || 'en', channels: () => [], vods: () => [], regulars: () => [], chat: () => false, notice() {},
    ...(options.attach || {}), review});
  return {mount, handle, state, review,
    show(snapshot) { state.value = stageStateStub(snapshot); handle.render(); return this; },
    render() { handle.render(); return this; },
    click(action, value, extra) { mount.fire('click', stageControlStub(action, value, extra)); return this; },
    html(selector) { handle.render(); return mount.html(selector); },
    text(selector) { handle.render(); return mount.text(selector); },
    panel(snapshot) { if (snapshot !== undefined) this.show(snapshot); openSourcePanel(mount); return sourcePanelHTML(mount); }};
}
test('live detector ticks accumulate: the boxes show and Start sends exactly what the operator ticked', async () => {
  // The panel derived the boxes from the engine's live.detectors, which nothing
  // writes, so every click started again from ['table','person'] (untick Person,
  // tick Ball -> table+person+ball) and the boxes never moved.
  const h = harness();
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  vm.runInContext(adapter, h.context, {filename:'vision-stage.js'});
  const engineSnap = {live:{state:'idle', error:null, attempt:null, frame_age_ms:null, receive_to_result_ms:null, skipped:0, detectors:['table','person'], stale:false, seq:null, stages:[]},
    source:{kind:'vod', label:'vod30', channel:null}, datasets:[{id:'vod30', label:'vod30'}], dataset:'vod30', frame:{count:54206}, detectors:{table:true, person:true, balls:false}};
  // The snapshot is handed over after attach, so attach's own first render is a no-op.
  let attached = false;
  h.context.window.CornerPocketReview = {snapshot: () => attached ? stageStateStub(engineSnap) : null, setLiveAttempt() {}, clearLiveError() {}, applyLiveStatus() {}};
  h.context.fetch = async (url, options) => { h.context.sent = JSON.parse(options.body); return {ok:true, json: async () => ({state:'starting'})}; };
  // The shell's own attachSurface() wires the adapter, exactly as on the Vision tab.
  const mount = stageMountStub();
  const shellQuery = h.context.document.querySelector;
  h.context.document.querySelector = selector => selector === '#vision-surface' ? mount : shellQuery(selector);
  h.attachSurface();
  h.renderSurface=()=>{};
  const handle = h.visionAdapter;
  attached = true;
  // Only the live row: the Frame detectors row below it has its own table/person boxes.
  const ticked = () => { handle.render(); openSourcePanel(mount);
    return ['table','person','ball'].filter(d => new RegExp(`data-vs-action="live-detector" data-vs-value="${d}" checked`).test(sourcePanelHTML(mount))); };
  const click = (value, checked) => mount.fire('click', stageControlStub('live-detector', value, {checked}));
  assert.deepEqual(ticked(), ['table','person'], 'the defaults are shown');
  click('person', false);
  assert.deepEqual(JSON.parse(JSON.stringify(h.liveDetectors)), ['table']);
  assert.deepEqual(ticked(), ['table'], 'an untick is shown');
  click('ball', true);
  assert.deepEqual(JSON.parse(JSON.stringify(h.liveDetectors)), ['table','ball'], 'Person stays off when Ball goes on');
  assert.deepEqual(ticked(), ['table','ball'], 'and the boxes say so');
  await h.liveAction("start");
  assert.deepEqual(h.context.sent.detectors, ['table','ball'], 'Start sends exactly the ticks');
});
test('live poll reports real status and hands the paired JPEG metadata to the stage', async () => {
  const h = harness(), statusNode = {}, seen = [];
  h.context.document.querySelector = selector => selector === '#live-status' ? statusNode : null;
  h.context.URL = {createObjectURL: () => 'blob:live', revokeObjectURL() {}};
  h.context.window.CornerPocketReview = {applyLiveStatus: status => seen.push({status}), ingestLiveFrame: (url, meta) => seen.push({url, meta})};
  h.context.fetch = async url => url === '/api/live'
    ? {ok:true, json:async()=>({state:'running',frame_age_ms:2500,frames_skipped:9,latest:{receive_to_result_ms:25,seq:12}})}
    : {ok:true, headers:{get:key=>key==='X-Live-Sequence'?'12':JSON.stringify({seq:12,detections:{boxes:[{label:'person',bbox:[1,2,11,22]}]}})}, blob:async()=>({size:3})};
  await h.pollLive(h.liveGeneration);
  assert.ok(statusNode.textContent.startsWith('running'));
  assert.ok(statusNode.textContent.includes('25 ms')&&statusNode.textContent.includes('2500 ms')&&statusNode.textContent.includes('STALE')&&statusNode.textContent.includes('Dropped: 9'));
  assert.equal(seen[0].status.state, 'running');
  assert.equal(seen[1].url, 'blob:live');
  assert.equal(seen[1].meta.seq, 12);
  assert.equal(seen[1].meta.detections.boxes[0].label, 'person');
});
test('a failed live poll is reported on the shell message line, not thrown from the catch', async () => {
  // The catch wrote to #live-status, which the Vision tab no longer has, so a
  // network error became "Cannot set properties of null" inside the catch itself.
  for (const [lang, prefix] of [['en', 'Live poll failed: '], ['zh', '直播轮询失败: ']]) {
    const h = harness(), messageNode = {textContent:'', className:''}, timers = [];
    h.context.document.querySelector = selector => selector === '#message' ? messageNode : null;
    h.context.setTimeout = (fn, ms) => { timers.push(ms); return 1; };
    h.context.window.CornerPocketReview = {applyLiveStatus() { assert.fail('a failed poll has no status to apply'); }};
    h.context.fetch = async () => { throw new h.VmTypeError('Failed to fetch'); };
    (()=>{h.lang=(lang); h.tab='vision';return h.context.document.hidden=false})();
    await h.pollLive(h.liveGeneration);   // must resolve: nothing is thrown out of the catch
    assert.equal(messageNode.textContent, `${prefix}Failed to fetch`, `${lang}: the error reaches the operator`);
    assert.equal(messageNode.className, 'error', `${lang}: styled as an error`);
    assert.deepEqual(timers.filter(ms => ms === 500), [500], `${lang}: and polling carries on`);
  }
  // A poll from a superseded generation says nothing: navigation already cancelled it.
  const h = harness(), messageNode = {textContent:'', className:''};
  h.context.document.querySelector = selector => selector === '#message' ? messageNode : null;
  h.context.fetch = async () => { throw new h.VmTypeError('Failed to fetch'); };
  await h.pollLive(h.liveGeneration - 1);
  assert.equal(messageNode.textContent, '', 'a stale generation stays silent');
});
test('live JPEG bytes and their metadata stay atomically paired', () => {
  assert.ok(source.includes("frame.headers.get('X-Live-Metadata')"));
  assert.ok(source.includes("frame.headers.get('X-Live-Sequence')"));
  assert.ok(source.includes("String(meta.seq)!==frame.headers.get('X-Live-Sequence')"));
  assert.ok(source.includes("ingestLiveFrame(URL.createObjectURL(blob),meta"));
  assert.ok(source.includes('receive_to_result_ms'));
  assert.ok(source.includes('applyLiveStatus(status)'));
});
test('Vision is one stage with two rails and no sub-tab navigation left', () => {
  const h = harness();
  assert.equal(h.t('vision'), 'Livestream');
  assert.deepEqual(JSON.parse(JSON.stringify(h.navTabs)), ['tonight','records','vision','players','status']);
  assert.ok(!source.includes('review-frame'));
  assert.ok(!source.includes('src="/app.html"'));
  // The sub-tab machinery is gone: no mode table, no data-vision buttons, no dead host.
  assert.ok(!source.includes('reviewModes'));
  assert.ok(!source.includes('visionNavigation'));
  assert.ok(!source.includes('data-vision'));
  assert.ok(!source.includes('visionTab'));
  assert.ok(!source.includes('vision-host-host'));
  assert.ok(!source.includes('twitchEmbed'));
  // The console hands over a host, its heading and one loading line; the workbench regions are the
  // stage's own markup, so a host that named them would be the old id protocol again.
  const host = h.visionSurface();
  assert.ok(host.includes('id="vision-surface"') && host.includes('class="vs-loading"'),
    'the console hands the stage a host with its heading and one loading line');
  assert.ok(!/id="vs-(grid|cues|stage|frame|inspector|strip|scrub|chips|marks)"/.test(host),
    'and authors no workbench region of its own');
  const surface = stageMarkup(h);
  for (const id of ['id="vs-chips"','id="vs-cues"','id="vs-stage"','id="vs-inspector"','id="vs-strip"','data-sheet-tab="cues"','data-sheet-tab="inspector"','id="vs-frame"','id="vs-marks"','data-vs-action="freeze"']) assert.ok(surface.includes(id), `vision surface missing ${id}`);
  // These two claims came here from tests/test_app_timeline.js with the markup they are about: that
  // suite mounts the stage on a root with no shell, so only this one can see the inspector's regions.
  assert.ok(surface.includes('id="vs-inspector-scroll"'), 'the inspector scrolls in its own region');
  assert.ok(surface.includes('id="vs-inspector-actions"'), 'the inspector keeps one action footer');
  assert.ok(surface.indexOf('id="vs-frame"') < surface.indexOf('id="vs-inspector"'));
});
test('the console hands the picture host in as data, so no shell id crosses the seam', () => {
  // The console used to look the stage's own id up (document.getElementById('vs-frame')) to move
  // #vision-host inside the workbench. That id is the stage's business, so the element is handed
  // over as an option instead and the stage puts it where its own shell says the picture goes.
  const h = harness();
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  vm.runInContext(adapter, h.context, {filename:'vision-stage.js'});
  h.context.window.CornerPocketReview = {snapshot: () => null, subscribe: () => () => {}, reloadDatasets: async () => true};
  const mount = stageMountStub();
  const adopt = {parentElement: null};
  const shellQuery = h.context.document.querySelector;
  h.context.document.querySelector = selector => selector === '#vision-surface' ? mount : (selector === '#vision-host' ? adopt : shellQuery(selector));
  h.attachSurface();
  const slot = mount.region('.vs-frame');
  assert.deepEqual(slot.children, [adopt], 'the stage adopts the host it is handed into the frame region');
  assert.equal(adopt.parentElement, slot, 'and that region becomes the host parent');
  // The console hoists the host out of the shell before every repaint, so a later attach puts it back.
  stageNodeStub().appendChild(adopt);
  h.attachSurface();
  assert.deepEqual(slot.children, [adopt], 'an attach after the console moved the host puts it back');
  assert.ok(!source.includes("getElementById('vs-frame')"), 'the console never looks up an id the stage authored');
});
test('dirty or busy review vetoes top-level and subtab navigation', async () => {
  for (const dataset of [{tab:'vision'}, {tab:'setup'}, {action:'floor'}]) {
    const h = harness();
    h.context.window.CornerPocketReview = {canLeave: () => false, activate: () => false};
    h.tab='vision';
    await h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
    assert.deepEqual(JSON.parse(JSON.stringify([h.tab,h.lang,h.theme])), ['vision','en','dark']);
  }
});
test('the player modal stays open until an action actually dismisses it', async () => {
  // Every shell click ran `selected=null` after the player-delete line, so the
  // modal closed on the next render (a language switch, a failed write) and a
  // cancelled delete closed it too.
  const click = (h, dataset) => h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
  const h = harness();
  (()=>{h.render=()=>{};return h.data.players=[{id:'p1',name:'Ana',status:'Active',rating:80,createdAt:'2026-09-01T00:00:00Z'}]})();
  await click(h, {action:'select-player', id:'p1'});
  assert.equal(h.selected, 'p1', 'selecting a player opens the modal');
  await click(h, {lang:'zh'});
  assert.equal(h.selected, 'p1', 'a language switch keeps it open');
  await click(h, {action:'filter', value:'Active'});
  assert.equal(h.selected, 'p1', 'so does any other shell button');
  h.context.confirm = () => false;
  await click(h, {action:'player-delete', id:'p1'});
  assert.equal(h.selected, 'p1', 'a cancelled delete keeps it open');
  assert.equal(h.calls.length, 0, 'and deletes nothing');
  h.context.confirm = () => true;
  h.action=async(name,payload)=>{h.calls.push({name,payload});return false};
  await click(h, {action:'player-delete', id:'p1'});
  assert.equal(h.selected, 'p1', 'a refused delete keeps it open, beside its error');
  h.action=async(name,payload)=>{h.calls.push({name,payload});return true};
  await click(h, {action:'player-delete', id:'p1'});
  assert.equal(h.selected, null, 'a delete that happened closes it');
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls.map(c=>c.name))), ['player_delete','player_delete']);
  await click(h, {action:'select-player', id:'p1'});
  await click(h, {action:'close-modal'});
  assert.equal(h.selected, null, 'and so does the close button');
});
test('shell does not intercept review clicks or form submissions', async () => {
  const h = harness();
  const target = {closest: () => ({})};
  await h.handlers.submit({target,preventDefault(){assert.fail('review submit intercepted')}});
  await h.handlers.click({target});
  assert.equal(h.calls.length, 0);
});
test('review host is outside the disposable shell main', () => {
  const html = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
  assert.ok(html.indexOf('</main>') < html.indexOf('id="vision-host"'));
  assert.ok(html.indexOf('/app.js') < html.indexOf('/ops.js'));
});
test('appearance changes retain review DOM without asking to discard', async () => {
  const h = harness();
  h.context.window.CornerPocketReview = {canLeave: () => assert.fail('appearance must preserve edits')};
  h.render=()=>{};
  for (const dataset of [{theme:'light'}, {lang:'zh'}]) await h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
  assert.equal(h.theme, 'light');
  assert.equal(h.lang, 'zh');
});
test('table release and the entry list use existing action API', async () => {
  const h = harness();
  for (const dataset of [{action:'unschedule',id:'m1'}, {action:'entrant-remove',id:'e1'}]) await h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name:'match_unschedule',payload:{id:'m1'}},{name:'entrant_remove',payload:{id:'e1'}}]);
  h.calls.length=0;
  await h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset:{action:'entrant-absence',id:'e1',absent:'true'}}}});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [], 'round 10, item 2: the desk has no not-here action left to write');
});
test('round 13, owner item 5: a delayed match is not offered a table, and nothing marks a side absent', () => {
  const h = harness();
  h.data.tournament.matches=[{id:'m1',round:1,status:'delayed',sides:['e1','e2'],absent:['e1'],score:[0,0]}];
  const html = h.bracketScreen();
  assert.ok(!html.includes('data-action="absence"') && !/未到场|Not here/.test(html), 'nothing on any card marks a side absent');
  assert.ok(!html.includes('data-action="card-open"'), 'no card carries the retired open-board control (round 20, owner item 7)');
  assert.ok(!html.includes('data-action="schedule"'), 'and it is not offered a table while it is held');
});
test('the scoreboard focus picker includes live and delayed tables', () => {
  const h = harness();
  (()=>{h.data.tournament.matches=['live','delayed'].map((status,i)=>({id:'m'+i,table:i+1,round:1,status,sides:['e1','e2'],absent:status==='delayed'?['e1']:[],score:[0,0]}));return h.data.notes=[]})();
  const html = h.scoreboardScreen();
  const match = html.match(/<select id="focus-match" aria-label="([^"]+)">(.*?)<\/select>/);
  assert.ok(match, 'the picker that switches tables carries an accessible name (round 2, B-05)');
  assert.ok(match[1].length > 0, 'and the name is not empty');
  const picker = match[2];
  assert.ok(picker.includes('value="m0"'));
  assert.ok(picker.includes('value="m1"'));
});
test('sticky header scroll inset belongs to the document scrolling root', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('html{scroll-padding-top:270px}'));
  assert.ok(!css.includes(':is(#ops-shell, #ops-footer){scroll-padding-top'));
});
// ---- Overdrive A: instant bracket -------------------------------------------------------
// A harness with the real action(), a scripted server, and a capture of every render.
function instantHarness(lang = 'en') {
  const h = harness();
  (()=>{h.lang=(lang);h.action=h.realAction;h.errors=[];h.message=(text,error,detail)=>h.errors.push({text,error,detail});
    h.renders=[];h.render=()=>h.renders.push({score:JSON.stringify(h.data.tournament.matches[0].score),status:h.data.tournament.matches[0].status,pending:h.isPending('m1'),revision:h.data.revision});
    h.data={revision:3,settings:{},players:[],history:[],events:[],notes:[],
      tournament:{id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
        entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bo'}]}],
        matches:[{id:'m1',round:1,sides:['e1','e2'],score:[0,0],status:'live',table:1,absent:[]}]}};
    h.context.confirm=()=>true;return h.reloads=0})();
  // queue of scripted answers: {status, body} | 'network' ; resolved manually via release()
  (()=>{h.pendingAnswers=[];h.posted=[];
    h.context.fetch=(url,opts)=>{if(!opts||opts.method!=='POST'){h.reloads++;return Promise.resolve({ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(h.serverState))})}
      const body=JSON.parse(opts.body);h.posted.push(body);return new Promise((resolve,reject)=>h.pendingAnswers.push({body,resolve,reject}))};
    h.serverState=JSON.parse(JSON.stringify(h.data));return h.answer=(kind,extra)=>{const p=h.pendingAnswers.shift();if(kind==='network')return p.reject(new h.VmTypeError('Failed to fetch'));
      if(kind==='ok'){const s=JSON.parse(JSON.stringify(h.serverState));s.revision++;const m=s.tournament.matches[0];if(p.body.action==='match_score')m.score=p.body.score;if(p.body.action==='match_complete'){m.status='complete';m.winnerId=m.score[0]>m.score[1]?'e1':'e2'}h.serverState=s;return p.resolve({ok:true,status:200,json:async()=>s})}
      return p.resolve({ok:false,status:kind,json:async()=>extra||{}})}})();
  h.context.window.document = h.context.document;
  return h;
}
const flush = () => new Promise(r => setImmediate(r));
const click = (h, dataset) => h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset, classList:{contains:()=>false}}}});

test('round 1 · Vision loading: the first paint is labelled and says what is loading, in EN and 中', () => {
  for (const [lang, loading, play, freeze, cues] of [['en', 'Loading the review workspace…', 'Play', 'Freeze', 'Cues'], ['zh', '正在加载复核工作区…', '播放', '冻结', '线索']]) {
    const h = harness();
    (()=>{h.lang=(lang);return h.visionAdapter=null})();
    const host = h.visionSurface();
    assert.ok(host.includes('aria-busy="true" data-loading="true"'), `${lang}: the surface is marked busy until the adapter attaches`);
    assert.equal((host.match(/<p class="vs-loading" role="status">/g) || []).length, 1, `${lang}: the console's loading line stands until the stage takes the host`);
    const html = stageMarkup(h, {lang});
    assert.equal((html.match(new RegExp(`<p class="vs-loading" role="status">${loading}</p>`, 'g')) || []).length, 2, `${lang}: both rails say what is loading`);
    // no control is unlabelled on the first paint
    for (const button of html.match(/<button[^>]*>[^<]*<\/button>/g) || []) {
      const named = /aria-label="[^"]+"/.test(button) || />[^<\s][^<]*<\/button>$/.test(button);
      assert.ok(named, `${lang}: unlabelled control ${button.slice(0, 80)}`);
    }
    assert.ok(html.includes(`>▶ ${play}</button>`) && html.includes(`>${freeze}</button>`) && html.includes(`>${cues}</button>`), `${lang}: Play, Freeze and the sheet tab read from the start`);
    h.visionAdapter={render(){}};
    assert.ok(!h.visionSurface().includes('data-loading'), `${lang}: once attached, no loading state`);
  }
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(/\.vision-surface\[data-loading\] \.vs-rail,#ops-shell \.vision-surface\[data-loading\] \.vs-inspector\{min-height:/.test(css), 'the rails hold their loaded size while loading');
  assert.ok(css.includes('.vision-surface[data-loading] .vs-strip{min-height:150px}'), 'the scrubber row is reserved');
  assert.ok(!css.includes('.vs-stagebar'), 'the layer row is not a separate bar');
});
test('round 1 · Back room: operator panels first; system status and roadmap under a collapsed, labelled maintainers section', () => {
  for (const [lang, maint, status] of [['en', 'For maintainers', 'System status'], ['zh', '维护人员', '系统状态']]) {
    const h = harness();
    (()=>{h.lang=(lang);return h.data.notes=[]})();
    const html = h.statusScreen();
    const at = s => html.indexOf(s);
    assert.ok(at('id="appearance-form"') < at('id="note-form"') && at('id="note-form"') < at('<details class="maintainers">'), `${lang}: operator panels come first`);
    assert.ok(!/<details class="maintainers" open/.test(html), `${lang}: the maintainer section starts collapsed`);
    assert.ok(html.includes(`<summary><h2>${maint}</h2>`), `${lang}: it is labelled ${maint}`);
    const inside = html.slice(at('<details class="maintainers">'));
    assert.ok(inside.includes(`<h3>${status}</h3>`) && inside.includes('/api/operations'), `${lang}: the status table is inside, headed, and keeps its facts`);
    assert.ok(inside.includes('data-action="reload"'), `${lang}: Refresh is still there`);
    assert.equal((inside.match(/<tr><td>[^<]*<\/td><td>[^<]*<\/td><td>P[12]<\/td><\/tr>/g) || []).length, 9, `${lang}: the roadmap keeps its nine rows`);
    for (const table of html.match(/<table[\s\S]*?<\/table>/g) || []) assert.ok(/<caption|<thead/.test(table), `${lang}: every table has headers`);
  }
});
test('round 1 · empty states: no fake names, no blank tiles, no list-item empties, every panel headed', () => {
  for (const [lang, noMatch, wait, dflt] of [['en', 'No match is on a table', 'Register the entrants and rack the night first', 'default name · saved when you rack'],
                                             ['zh', '球台上还没有比赛', '先登记参赛者，再生成对阵', '默认名称 · 生成对阵时保存']]) {
    const h = harness();
    (()=>{h.lang=(lang);h.data.players=[];h.data.history=[];h.data.events=[];return h.data.tournament={id:'t1',name:'',format:'singles',raceTo:1,status:'registration',entrants:[],matches:[]}})();
    const floor = h.scoreboardScreen();
    const names = [...floor.matchAll(/<strong class="name"[^>]*>([^<]*)<\/strong>/g)].map(m => m[1]);
    assert.ok(names.every(n => n === '\u2014'), `${lang}: an empty board shows a dash, never a placeholder name`);
    assert.ok(floor.includes('class="empty-note board-empty"') && floor.includes(noMatch) && floor.includes(wait), `${lang}: it says there is no match and what to do`);
    const scene = h.scene();
    assert.ok(!/data-phase=/.test(h.tonightScreen()), `${lang}: no phase button survives anywhere in Tonight`);
    assert.ok(!/<button/.test(scene) && scene.includes(h.esc(h.t('sceneIdle'))), `${lang}: the step is read-only, and an empty venue says so`);
    assert.ok(/<h2 class="sr-only">/.test(floor), `${lang}: the scoreboard has a heading`);
    assert.ok(!/Tables open|球台空闲/.test(floor), `${lang}: never a placeholder name on the board`);
    const matches = h.bracketScreen();
    assert.ok(!/<li>[^<]*(Nothing|暂无|尚无)[^<]*<\/li>/.test(matches), `${lang}: no empty state inside a list`);
    assert.ok(!/Nothing here yet|暂无记录/.test(matches + floor + h.entrantsCard() + h.playersScreen()), `${lang}: the generic empty line is gone`);
    assert.ok(/<h3>[^<]+<\/h3>[\s\S]*?<article class="empty">/.test(matches), `${lang}: the empty draw sits under its own heading`);
    // with a racked night and nothing on a table, the step is Matches
    (()=>{h.data.tournament.name='Friday';h.data.tournament.entrants=[{id:'e1',members:[{name:'A'}]},{id:'e2',members:[{name:'B'}]}];h.data.tournament.matches=[{id:'m1',round:1,sides:['e1','e2'],score:[0,0],status:'scheduled',absent:[]}];return h.data.tournament.status='active'})();
    const play2 = h.playScreen();
    assert.ok(play2.includes('data-action="schedule"'), `${lang}: a racked match can be sent from its own card in the draw`);
    const named = h.scene();
    assert.ok(named.includes('Friday') && !named.includes(dflt), `${lang}: a saved name is not called a default`);
    h.data.tournament.name='';
    const unnamed = h.scene();
    assert.ok(unnamed.includes(h.autoEventName()) && unnamed.includes(dflt),
      `${lang}: an unsaved event name is shown, and said to be the default`);
  }
});
test('round 1 · numbers: every figure in the shell is lining and tabular, past any font: shorthand', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  // Zilla Slab's default figures are old-style ("0" reads as "o"); a font: shorthand resets
  // font-variant-numeric, so the rule must reach every element, not just be inherited.
  assert.ok(css.includes('#ops-shell,#ops-shell *{font-variant-numeric:lining-nums tabular-nums!important}'));
  const displayFaces = (css.match(/url\(\/fonts\/zilla-slab-[^)]+\.woff2\)/g) || []).length;
  assert.ok(displayFaces >= 3, 'the self-hosted Zilla Slab faces are the ones whose subset keeps lnum/tnum');
});
test('instant: a score step shows at once as pending, then the server\u2019s answer confirms it', async () => {
  const h = instantHarness();
  const done = click(h, {action:'score', id:'m1', side:'0', delta:'1'});
  await flush();
  const shown = JSON.parse(JSON.stringify(h.renders.at(-1)));
  assert.deepEqual([shown.score, shown.pending, shown.status], ['[1,0]', true, 'live'], 'the new score is on screen before the server answered, marked pending');
  assert.equal(h.posted[0].revision, 3);
  h.answer('ok'); await done; await flush();
  const final = JSON.parse(JSON.stringify(h.renders.at(-1)));
  assert.deepEqual([final.score, final.pending, final.revision], ['[1,0]', false, 4], 'confirmed: same score, not pending, the server\u2019s revision');
});
test('instant: a signature is never shown before the server signs it', async () => {
  const h = instantHarness();
  (()=>{h.data.tournament.matches[0].score=[3,1];return h.serverState=JSON.parse(JSON.stringify(h.data))})();
  // Round 19, owner item 5: the sign-off is two steps on the same surface. The first click asks, in
  // place, and writes nothing.
  const asked = click(h, {action:'sign', id:'m1'});
  await flush();
  // Asking paints the foot alone - the board is not rebuilt - so the proof is the draft, not a render.
  assert.equal(!!h.signDraft, true, 'asking to sign holds a pending confirmation');
  assert.equal(JSON.stringify(h.signDraft), '{"id":"m1","winner":0}', 'for the winner the score already shows');
  const done = click(h, {action:'sign-confirm', id:'m1'});
  await flush();
  assert.equal(h.renders.at(-1).status, 'live', 'while the signature is unconfirmed the match is still live');
  assert.equal(h.renders.at(-1).pending, true, 'and says it is saving');
  h.answer('ok'); await done; await flush();
  assert.equal(h.renders.at(-1).status, 'complete', 'signed only once the server said so');
});
test('instant: 409 rolls back to the exact previous render, reloads, and says why', async () => {
  const h = instantHarness();
  const before = JSON.stringify(h.data);
  const done = click(h, {action:'score', id:'m1', side:'1', delta:'1'});
  await flush();
  assert.equal(h.renders.at(-1).score, '[0,1]');
  h.answer(409,{error:'State changed; reload before retrying'}); await done; await flush();
  assert.equal(h.reloads, 1, 'the document is reloaded from the server');
  assert.equal(JSON.stringify(h.data), before, 'the state is exactly the pre-tap state (the server had not moved)');
  assert.deepEqual([h.renders.at(-1).score, h.renders.at(-1).pending], ['[0,0]', false]);
  assert.match(h.errors.at(-1).text, /Another operator changed the data/);
});
test('instant: 400 rolls back and shows the server\u2019s reason in both languages', async () => {
  // Round 41: the service sends the code and the Chinese sentence in the refusal body together.
  const row = refusalRow('Schedule match before scoring');
  for (const [lang, reason] of [['en', 'Schedule match before scoring'], ['zh', row.zh]]) {
    const h = instantHarness(lang);
    const before = JSON.stringify(h.data);
    const done = click(h, {action:'score', id:'m1', side:'0', delta:'1'});
    await flush();
    h.answer(400,Object.assign({error:'Schedule match before scoring'}, row)); await done; await flush();
    assert.equal(JSON.stringify(h.data), before, `${lang}: exact rollback`);
    assert.equal(h.renders.at(-1).score, '[0,0]', `${lang}: the screen shows the pre-tap score`);
    assert.ok(h.errors.at(-1).text.includes(reason), `${lang}: ${h.errors.at(-1).text}`);
    assert.equal(h.reloads, 0, `${lang}: a validation refusal does not reload`);
  }
});
test('instant: a network failure rolls back and says so, with no retry', async () => {
  for (const [lang, said] of [['en', 'network did not answer'], ['zh', '网络无响应']]) {
    const h = instantHarness(lang);
    const before = JSON.stringify(h.data);
    const done = click(h, {action:'score', id:'m1', side:'0', delta:'1'});
    await flush();
    h.answer('network'); await done; await flush();
    assert.equal(JSON.stringify(h.data), before, `${lang}: exact rollback`);
    assert.ok(h.errors.at(-1).text.includes(said), `${lang}: ${h.errors.at(-1).text}`);
    assert.equal(h.posted.length, 1, `${lang}: posted once, never retried`);
  }
});
test('instant: two rapid taps are serialised; the final state is the server\u2019s', async () => {
  const h = instantHarness();
  const first = click(h, {action:'score', id:'m1', side:'0', delta:'1'});
  const second = click(h, {action:'score', id:'m1', side:'0', delta:'1'});
  await flush();
  assert.equal(h.posted.length, 1, 'the second write waits for the first');
  h.answer('ok'); await first; await flush(); await flush();
  assert.equal(h.posted.length, 2, 'then it goes');
  assert.equal(h.posted[1].revision, 4, 'carrying the revision the first answer returned (no race)');
  assert.equal(JSON.stringify(h.posted[1].score), '[2,0]', 'and built on the confirmed score');
  h.answer('ok'); await second; await flush();
  assert.equal(JSON.stringify(h.data.tournament.matches[0].score), JSON.stringify(h.serverState.tournament.matches[0].score), 'final state = server state');
  assert.equal(h.renders.at(-1).pending, false);
  // a refused second write rolls back only itself
  const h2 = instantHarness();
  const a = click(h2, {action:'score', id:'m1', side:'0', delta:'1'}), b = click(h2, {action:'score', id:'m1', side:'0', delta:'1'});
  await flush(); h2.answer('ok'); await a; await flush(); await flush();
  h2.answer(400,{error:'Score out of range'}); await b; await flush();
  assert.equal(JSON.stringify(h2.data.tournament.matches[0].score), '[1,0]', 'the confirmed first step stays; only the refused one is undone');
});
test('instant: the pending state is readable by a screen reader, in EN and 中', () => {
  for (const [lang, saving] of [['en', 'saving…'], ['zh', '保存中…']]) {
    const h = harness();
    (()=>{h.lang=(lang);h.data.tournament={id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
      entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bo'}]}],
      matches:[{id:'m1',round:1,sides:['e1','e2'],score:[1,0],status:'live',table:1,absent:[]}]};h.focusId='m1';return h.pendingMatches.set('m1',1)})();
    const floor = h.scoreboardScreen();
    assert.ok(floor.includes('class="scoreboard pending" aria-busy="true"'), `${lang}: the scoreboard is busy`);
    assert.ok(floor.includes(`<p class="pending-note" role="status">${saving}</p>`), `${lang}: and says ${saving}`);
    const bracket = h.bracketScreen();
    assert.ok(bracket.includes('bracket-card pending') && bracket.includes('aria-busy="true"'), `${lang}: the bracket card is busy`);
    assert.ok(bracket.includes(` · ${saving}"`) && bracket.includes(`role="status">${saving}</span>`), `${lang}: its name and live region say ${saving}`);
    assert.ok(!/class="badge complete"/.test(floor), `${lang}: pending never looks signed`);
    h.pendingMatches.clear();
    assert.ok(!h.scoreboardScreen().includes('aria-busy'), `${lang}: gone once confirmed`);
  }
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const pendingRules = css.match(/#ops-shell [^{]*pending[^{]*\{[^}]*\}/g) || [];
  assert.ok(pendingRules.length && pendingRules.every(r => !/animation|transition/.test(r)), 'the pending cue is static (same under reduced motion)');
});
test('narrow: record totals are 2x2 in a narrow modal, one row when wide; wide tables scroll inside', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('#ops-shell .record .tiles{grid-template-columns:repeat(2,minmax(0,1fr))}'), 'the four totals are 2x2 by default');
  assert.ok(css.includes('#ops-shell .record{container-type:inline-size}') && css.includes('@container (min-width:460px){#ops-shell .record .tiles{grid-template-columns:repeat(4,minmax(0,1fr))}}'),
    'and one row of four when the record itself is wide (the modal caps at 540 px, so the container decides, not the viewport)');
  assert.ok(css.includes('#ops-shell .table-wrap{overflow:auto;contain:inline-size}'), 'main\u2019s wrapper still keeps a wide table inside');
  assert.ok(css.includes('#ops-shell .table-wrap{-webkit-mask-image:') && css.includes('animation-timeline:scroll(self inline)'), 'a clipped table says it scrolls');
  const h = harness();
  (()=>{h.data.players=[{id:'p1',name:'Maximiliana Alexandrovna Konstantinopolskaya-Wrightington',rating:50,status:'Active',joinedAt:'2026-09-26'}];return h.data.history=[]})();
  const record = h.recordView(h.data.players[0]);
  assert.ok(record.includes('<div class="record">') && /<div class="tiles">(<div class="tile">[\s\S]*?){4}/.test(record), 'the record has its four totals tiles');
  for (const table of ['per-event', 'h2h']) {
    if (record.includes(`class="${table}"`)) assert.ok(record.includes(`<div class="table-wrap"><table class="${table}"`), `${table} is wrapped`);
  }
});
test('clarify: the night log names entrants and sources instead of printing hex ids', () => {
  const h = harness();
  const present = 'a1111111c94649988a2995e9b27c69ff', removed = 'b0000000c94649988a2995e9b27c69ff', source = '77777777777777777777777777777777';
  (()=>{h.data.players=[{id:'p1',name:'王磊',rating:60,status:'Active'}];
    h.data.tournament={id:'t1',name:'Friday',format:'singles',raceTo:3,status:'registration',
      entrants:[{id:(present),members:[{pid:'p1',name:'王磊'}]}],matches:[]};
    h.data.history=[];h.data.sources=[];return h.data.events=[
      {action:'entrant_add',createdAt:'2026-09-26T01:00:00Z',revision:4,context:{id:(present)}},
      {action:'entrant_remove',createdAt:'2026-09-26T01:01:00Z',revision:5,context:{id:(removed)}},
      {action:'source_add',createdAt:'2026-09-26T01:02:00Z',revision:2,context:{id:(source)}}]})();
  for (const [lang, gone, aSource, added, removedLabel] of [
    ['en', 'an entrant who was removed', 'a source', 'Entrant registered', 'Entrant removed'],
    ['zh', '已移除的参赛者', '一个来源', '参赛报名', '移除参赛者']]) {
    h.lang=(lang);
    const line = i => h.auditLine(h.data.events[(i)]);
    assert.ok(line(0).includes(`${added} · 王磊 · v4`), `${lang}: a present entrant reads by name: ${line(0)}`);
    assert.ok(line(1).includes(`${removedLabel} · ${gone} · v5`), `${lang}: a removed entrant reads as a plain phrase: ${line(1)}`);
    assert.ok(line(2).includes(aSource), `${lang}: a removed source reads as a plain phrase: ${line(2)}`);
    for (const i of [0, 1, 2]) assert.ok(!/[0-9a-f]{8}/.test(line(i)), `${lang}: no hex id in the visible line: ${line(i)}`);
    // never dropped: the id stays inspectable in the list item's title
    const html = h.recordsScreen();
    for (const id of [present, removed, source]) assert.ok(html.includes(`title="${id}"`), `${lang}: ${id.slice(0, 8)} is kept in the title`);
  }
  // a name the server recorded wins; a source still present reads by its URL; an archived entrant resolves from history
  (()=>{h.lang='en';return h.data.sources=[{id:(source),url:'https://www.twitch.tv/examplechannel'}]})();
  assert.ok(h.auditLine(h.data.events[2]).includes('https://www.twitch.tv/examplechannel'));
  h.data.history=[{id:'h1',name:'Thursday',entrants:[{id:(removed),members:[{pid:null,name:'Bo'}]}],matches:[]}];
  assert.ok(h.auditLine(h.data.events[1]).includes('Entrant removed · Bo · v5'), 'an archived night still knows the name');
  assert.ok(h.auditLine({action:'player_save',createdAt:'2026-09-26T01:00:00Z',revision:6,context:{id:'x',name:'Ann'}}).includes('Player saved · Ann · v6'));
});
test('R9: the compact bracket is one line per side with a status dot; the full card is still there', () => {
  const h = harness();
  (()=>{h.data.players=[];return h.data.tournament={id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
    entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bo'}]},{id:'e3',members:[{pid:null,name:'Cai'}]},{id:'e4',members:[{pid:null,name:'Dee'}]}],
    matches:[{id:'m1',round:1,sides:['e1','e2'],score:[1,0],status:'live',table:1,absent:[]},
             {id:'m2',round:1,sides:['e3','e4'],score:[0,0],status:'scheduled',table:null,absent:[]},
             {id:'m3',round:2,sides:[null,null],score:[0,0],status:'pending',table:null,absent:[]}]}})();
  const view = h.bracketScreen();
  assert.ok(!view.includes('data-density') && !view.includes('data-action="density"'), 'one view: no second density and no switch');
  assert.ok(view.includes('<div class="rounds">'), 'one rounds container, with no density attribute');
  const card = view.slice(view.indexOf('data-status="live"'), view.indexOf('data-status="scheduled"'));
  assert.ok(card.includes('class="row card-side first"') && card.includes('class="status-dot"'), 'a side line carries the status dot');
  assert.ok(card.includes('aria-label="Ann – Bo · On table"'), 'the whole match, with its status word, is the card\u2019s name');
  assert.ok(card.includes('class="row card-head"') && /Table 1/.test(card), 'the header row stays, with the table');
  assert.ok(!/m1/.test(card.replace(/data-(?:id|action|side)="[^"]*"/g, '')), 'and not the machine id: an operator never reads it');
  // Round 21, owner item 1: the table stays on the card's first line (its head) and is not repeated
  // beside a player's name.
  assert.ok(card.replace(/<[^>]*>/g, ' ').includes('Table 1') && !card.includes('table-chip'),
    'the table is on the first line, and not beside a player');
  assert.ok(/data-action="forfeit"/.test(card) && !/data-action="absence"/.test(card), 'forfeit stays reachable, attendance does not');
  // Round 20, owner item 7: the card no longer carries an 'open its scoreboard' control.
  assert.ok(!card.includes('card-open') && !card.includes('openTable'), 'the card does not open the board for you');
  assert.ok(view.includes('data-action="schedule" data-id="m2"'), 'Send to table stays reachable');
  assert.ok(view.includes('tabindex="0"'), 'a keyboard user can open a card');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(/\.rounds\{display:grid[^}]*grid-template-columns:repeat\(auto-fit,minmax\(min\(100%,230px\),1fr\)\)/.test(css), 'the rounds fill the width they have and wrap when they do not');
  assert.ok(!/data-density/.test(css), 'the stylesheet carries no second view either');
  assert.ok(css.includes('.bracket-card:is(:hover,:focus-within,.selected,.open) :is(.card-head,.card-actions){display:flex}'), 'hover, focus or the card\u2019s own control opens the details');
  for (const key of ['density', 'densityCompact', 'densityFull']) assert.equal(h.t((key)), key, `${key} is retired from the words file, not just unrendered`);
});
test('round 19 / owner item 4: a bracket card carries no collapse control, only the actions it has', () => {
  const h = harness();
  (()=>{h.data.players=[];return h.data.tournament={id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
    entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bo'}]}],
    matches:[{id:'m1',round:1,sides:['e1','e2'],score:[1,0],status:'live',table:1,absent:[]},
             {id:'m2',round:1,sides:['e1','e2'],score:[0,0],status:'scheduled',table:null,absent:[]}]}})();
  const html = h.bracketScreen();
  assert.ok(!html.includes('card-toggle'), 'no triangle in the corner: the card is never collapsed');
  assert.ok(!html.includes('cardExpand') && !html.includes('cardCollapse'), 'and its copy is retired with it');
  assert.ok(!html.includes('card-open'), 'and no card carries the retired control (round 20, owner item 7)');
  assert.ok(/data-action="schedule" data-id="m2"/.test(html), 'and a scheduled one still takes a table');
  assert.ok(html.includes('tabindex="0"'), 'a keyboard user can still open a card');
});
test('R13: every query word must match the name, after NFKC, accent and case folding', () => {
  const h = harness();
  const m = (name, q) => h.nameMatches(JSON.parse(JSON.stringify(name)), JSON.parse(JSON.stringify(q)));
  // the reported case: words in any order, punctuation is only a separator
  assert.equal(m('Ann-Marie (Annie) Lee', 'ann-marie lee'), true);
  assert.equal(m('Ann-Marie (Annie) Lee', 'lee annie'), true, 'order does not matter');
  assert.equal(m('Ann-Marie (Annie) Lee', 'ann lee bo'), false, 'every word must match (AND)');
  // full-width forms and accents fold to their plain letters
  assert.equal(m('Ann-Marie (Annie) Lee', 'ＡＮＮ－ＭＡＲＩＥ'), true, 'full-width input');
  assert.equal(m('José Núñez', 'jose nunez'), true, 'accents fold');
  assert.equal(m('Jose Nunez', 'JOSÉ'), true, 'and fold in the query too');
  // Chinese names: substring, with or without spaces between the characters
  assert.equal(m('王磊', '磊'), true);
  assert.equal(m('王磊', '王 磊'), true);
  assert.equal(m('欧阳娜娜', '欧阳'), true);
  assert.equal(m('王磊', '李'), false);
  assert.equal(m('Anyone', '   '), true, 'an empty query matches everyone');
  // the roster searches the name only: status has its own filter
  (()=>{h.data.players=[{id:'p1',name:'Bo Active',rating:50,status:'Visitor'},{id:'p2',name:'Cai',rating:40,status:'Active'}];h.query='active';return h.filter=''})();
  const html = h.playersScreen();
  assert.ok(html.includes('Bo Active') && !html.includes('>Cai<'), 'a status word no longer matches a name');
  // R14: the matcher is local; neither it nor the desk filter makes a request
  assert.ok(!/fetch\(/.test(h.nameMatches.toString()+h.deskFilter.toString()), 'no network call on a keystroke');
  // EN/中 placeholder parity for both fields
  for (const key of ['search', 'deskSearch', 'searchCount']) assert.match(source, new RegExp(`\\b${key}:\\['[^']+','[^']+'\\]`), `${key} has EN and 中`);
});
test('R13: the registration desk filters its regulars in place with the same matcher', () => {
  const h = harness();
  (()=>{h.data.players=[{id:'p1',name:'Ann-Marie (Annie) Lee',rating:70,status:'Active'},{id:'p2',name:'王磊',rating:60,status:'Active'},{id:'p3',name:'Bo',rating:50,status:'Active'}];return h.data.tournament={id:'t1',status:'registration',format:'singles',raceTo:3,entrants:[],matches:[]}})();
  const shut = h.entrantsCard();
  assert.ok(shut.includes('class="pick-btn') && shut.includes('aria-controls="desk-list0"'), 'the desk is a combobox, tied to its listbox');
  assert.ok(!shut.includes('class="pick-search"'), 'and shut, it holds no list at all: the panel is what opens (owner item 4)');
  h.deskOpen=0;
  const html = h.entrantsCard();
  assert.ok(html.includes('class="pick-search" data-desk="0"'), 'opened, it has a type-to-filter field');
  assert.ok(html.includes('aria-controls="desk-list0"') && html.includes('id="desk-list0"'), 'the field is tied to its listbox');
  assert.ok(html.includes('type="hidden" name="pid0"'), 'and the pick travels to the server in a hidden input');
  assert.ok(html.includes('data-name="Ann-Marie (Annie) Lee"'), 'options carry the bare name, so the rating is never matched');
  // drive deskFilter against a stub select
  // Round 9 (owner item 4): the desk is a custom listbox, so the filter walks its
  // own rows instead of a native <select>. The Guest row carries no id and is
  // never filtered away; the count line is the test that something was searched.
  (()=>{const rows=[['','Guest'],['p1','Ann-Marie (Annie) Lee'],['p2','王磊'],['p3','Bo']]
    .map(([id,name])=>({dataset:{id,name},hidden:false}));
    const count={hidden:true,textContent:''};
    const deskPanel={dataset:{total:'3'},querySelectorAll:s=>s==='.pick-row'?rows:[],querySelector:s=>s==='.pick-count'?count:null};
    const deskField=v=>({value:v,dataset:{desk:'0'},closest:()=>deskPanel});return h.context.window.__desk={rows,count,field:deskField}})();
  h.deskFilter(h.context.window.__desk.field('ann-marie lee'));
  assert.equal(h.context.window.__desk.rows.filter(r=>!r.hidden).map(r=>r.dataset.id).join(','), ',p1', 'only the match (and the always-present Guest row) stay visible');
  assert.equal(h.context.window.__desk.count.textContent, h.t('searchCount').replace('{n}',1).replace('{m}',3), 'and the line says how many of how many');
  h.deskFilter(h.context.window.__desk.field('７０'));
  assert.equal(h.context.window.__desk.rows.filter(r=>!r.hidden&&r.dataset.id).length, 0, 'the rating is not part of the name: nothing matches');
  h.deskFilter(h.context.window.__desk.field(''));
  assert.equal(h.context.window.__desk.rows.every(r=>!r.hidden), true, 'clearing the field shows everyone again');
});
test('onboard: an empty club gets three real steps in Register, and they leave once the draw exists', () => {
  const h = harness();
  // Round 7, owner item 4: the three-step guide and its page are gone. An empty club gets the
  // registration page with the one dialog that starts the night floating over it.
  (()=>{h.data.players=[];return h.data.tournament={id:'',name:'',format:'singles',raceTo:7,tables:4,status:'registration',entrants:[],matches:[]}})();
  const idle = () => h.tonightScreen();
  const first = idle();
  assert.equal(h.tonightState(), 'idle', 'an empty club is the idle venue');
  assert.ok(first.includes('class="modal modal--start"'), 'and it sees one dialog: name the night and start it');
  assert.ok(first.includes('id="start-title"') && first.includes('aria-modal="true"'), 'announced as a dialog, under one heading');
  assert.ok(first.includes('id="settings-form"'), 'the four fields live in the dialog, not on the page');
  assert.ok(!first.includes('id="entrant-form"'), 'and nothing behind it asks for anything yet: the dialog is the screen');
  assert.ok(first.includes('name="name"') && first.includes('name="format"') && first.includes('name="tables"'),
    'the four fields are in the dialog, where the night is named');
  assert.ok(!first.includes('data-action="dismiss-setup"'),
    'round 13, owner item 1: a night with no name has no Close - Save is the way in');
  assert.ok(/data-action="dismiss-setup"/.test(h.startModal(true)),
    'and a named night\u2019s dialog carries it, on the same row as Save');
  for (const key of ['firstRunTitle', 'firstRunRegulars', 'firstRunEntrants', 'firstRunRack', 'firstRunNote']) {
    assert.equal(h.t((key)), key, `${key} is retired from the words file, not just unrendered`);
  }
  // A named night is not asked to name itself again: the page is the registration page and the
  // dialog is behind one door, which closes.
  h.data.tournament.id='t1';
  const registering = idle();
  assert.ok(!registering.includes('modal--start'), 'a named night is not asked again');
  assert.ok(registering.includes('id="entrant-form"') && registering.includes('class="card card--event"'), 'the desk and the night card are the page');
  assert.ok(registering.includes('data-action="event-rename"'), 'and the one field that edits - the name - is the card’s own door');
  h.setupOpen=true;
  assert.ok(idle().includes('modal--start') && idle().includes('data-action="dismiss-setup"'), 'the door opens the same dialog, and this one closes');
});
test('harden: fields show focus that a border shorthand cannot erase; names and states are announced', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const focus = css.match(/input:focus,[^{]*textarea:focus\{([^}]*)\}/);
  assert.ok(focus, 'one field focus rule');
  assert.match(focus[1], /box-shadow:[^;]*var\(--brass\)/, 'the focus ring is a box-shadow, so .vs-field border:1px cannot remove it');
  assert.ok(!/animation:none!important;transition:none!important/.test(css), 'reduced motion keeps state changes instead of a global kill');
  const html = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
  assert.ok(!html.includes('aria-label="Color theme"'), 'the theme group name is bilingual');
  const surface = stageMarkup(harness());
  assert.ok(surface.includes('role="tab" aria-selected="true" aria-controls="vs-cues"'), 'the sheet bar holds real tabs');
  for (const key of ['cuesRegion', 'stageRegion', 'inspectorRegion', 'sheetTabs', 'stepBack', 'stepForward']) {
    assert.ok(surface.includes(`data-vs-aria="${key}"`), `${key} follows the language toggle`);
  }
  assert.ok(!surface.includes('aria-label="-1"') && !surface.includes('aria-label="+1"'), 'step buttons say what they do');
  assert.ok(source.includes("b.setAttribute('aria-pressed',String(b.dataset.lang===lang))"), 'EN|中 announce the pressed one');
  assert.ok(source.includes("b.setAttribute('aria-pressed',String(b.dataset.theme===theme))"), 'dark|light announce the pressed one');
  const stage = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  for (const key of ['cuesRegion', 'stageRegion', 'inspectorRegion', 'sheetTabs', 'twitchChat', 'stepBack', 'stepForward']) {
    assert.equal((stage.match(new RegExp(`\\b${key}:'`, 'g')) || []).length, 2, `${key} has an EN and a 中 string`);
  }
  assert.ok(!stage.includes('title="Twitch chat"') && !stage.includes('aria-label="×"'), 'no English-only frame title or glyph-only close name');
});
test('player notes are editable and safely escaped', () => {
  const h = harness();
  const html = h.playerForm({id:'p1',name:'A',notes:'</textarea><script>x</script>'});
  assert.ok(html.includes('name="notes" maxlength="4000"'));
  assert.ok(html.includes('&lt;/textarea&gt;'));
  assert.ok(!html.includes('<script>'));
});
test('every shell word has EN and 中 copy, so no raw key renders (Regulars roster heading)', () => {
  const h = harness();
  // Every literal t('key') in the shell must resolve in both languages: t() falls
  // back to the key itself, which is how "rosterTitle" reached the screen.
  const words = JSON.parse(JSON.stringify(h.words));
  const used = [...new Set([...source.matchAll(/\bt\('([A-Za-z0-9_]+)'\)/g)].map(m => m[1]))];
  assert.ok(used.length > 90, `the scan found the shell's keys: ${used.length}`);
  const missing = used.filter(key => !Array.isArray(words[key]) || !words[key][0] || !words[key][1]);
  assert.deepEqual(missing, [], 'every t() key has an EN and a 中 entry');
  h.data.players=[{id:'p1',name:'Ana',status:'Active',rating:80,createdAt:'2026-09-01T00:00:00Z'}];
  for (const [lang, heading] of [['en', words.rosterTitle[0]], ['zh', words.rosterTitle[1]]]) {
    h.lang=(lang);
    const html = h.playersScreen();
    const headings = [...html.matchAll(/<h3[^>]*>([^<]*)<\/h3>/g)].map(m => m[1]);
    assert.ok(headings.includes(heading), `${lang}: the roster heading is its copy: ${JSON.stringify(headings)}`);
    const raw = used.filter(key => new RegExp(`>${key}<`).test(html));
    assert.deepEqual(raw, [], `${lang}: no raw key renders as text on Regulars`);
  }
  assert.ok(/[\u4e00-\u9fff]/.test(words.rosterTitle[1]), 'the 中 heading is Chinese');
});
test('Back room retains nine truthful deferred roadmap areas', () => {
  const h = harness();
  const html = h.roadmapPanel();
  assert.equal((html.match(/<tr>/g)||[]).length, 10);
  assert.ok(html.includes('not live monitoring'));
  assert.ok(html.includes('accuracy unverified'));
  h.lang='zh';
  assert.ok(h.roadmapPanel().includes('尚无自动化'));
});
function submission(formId, values, submitter = {}) {
  // A real form whose `id` control shadows its own id property: the handler reads the form off the
  // event target, and a DOM form exposes its controls through .elements, so the fake must too.
  const form = {preventDefault() {}, id: formId, elements: {id: {value: values.id}}, values, getAttribute: () => formId, classList: {contains: () => false}, querySelectorAll: () => [], querySelector: () => null};
  return {...form, target: form, submitter};
}
// Round 9 (owner item 3): the board is the only scorer, so the score and the signature
// are two separate acts, and the tests follow the two buttons instead of a form id.
const boardClick = (h, dataset) => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset, classList: {contains: () => false}, getAttribute: () => null}}});
const scoreBtn = (h, id, side, delta) => boardClick(h, {action: 'score', id, side: String(side), delta: String(delta)});
const callsSigned = h => JSON.parse(JSON.stringify(h.calls)).some(c => c.name === 'match_complete');
// the board scores the match that is live, so a live one has to exist before a click
const liveMatch = h => h.data.tournament={id:'t0',format:'singles',raceTo:3,status:'active',entrants:[{id:'a',members:[{pid:'pa',name:'Ann'}]},{id:'b',members:[{pid:'pb',name:'Bea'}]}],matches:[{id:'match-1',round:1,sides:['a','b'],score:[0,0],status:'live',table:1,absent:[]}]};
test('the board scores in its own write, and Sign completes in a second one', async () => {
  const h = harness();
  liveMatch(h);
  await scoreBtn(h, 'match-1', 0, 1);
  await scoreBtn(h, 'match-1', 1, -1);
  // Round 19, owner item 5: the sign-off asks in place first, then writes. Two clicks, three writes.
  await boardClick(h, {action: 'sign', id: 'match-1'});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls.map(c=>c.name))), ['match_score', 'match_score'],
    'asking to sign writes nothing');
  await boardClick(h, {action: 'sign-confirm', id: 'match-1'});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls.map(c=>c.name))), ['match_score', 'match_score', 'match_complete'],
    'each +/- is its own write, and the confirmed signature is a third one');
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].payload)), {id: 'match-1', score: [1, 0]},
    'and the first tap moves the side it names by one, clamped to the race');
});
test('failed score write never signs a result', async () => {
  const h = harness();
  liveMatch(h);
  h.action=async(name,payload)=>{h.calls.push({name,payload});return false};
  await scoreBtn(h, 'match-1', 0, 1);
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].name, 'match_score');
  assert.ok(!callsSigned(h), 'and nothing signed a match nobody scored');
});
test('a cancelled confirmation does not complete a match', async () => {
  const h = harness();
  liveMatch(h);
  await scoreBtn(h, 'match-1', 0, 1);
  assert.equal(h.calls.length, 1);
  h.context.confirm = () => false;
  await boardClick(h, {action: 'sign', id: 'match-1'});
  assert.equal(h.calls.length, 1, 'and the cancelled Sign writes nothing');
});
test('registration without a guest name or a regular is stopped at the guest field, in both languages', async () => {
  const h = harness();
  const guest = {validity: '', reported: 0, setCustomValidity(text) { this.validity = text; }, reportValidity() { this.reported++; return false; }};
  const form = values => ({preventDefault() {}, target: {getAttribute: () => 'entrant-form', classList: {contains: () => false}, querySelector: sel => sel === '[name=guest0]' ? guest : null, querySelectorAll: () => [], values}});
  for (const blank of [{pid0: '', guest0: ''}, {pid0: '', guest0: '   '}, {pid0: ''}]) await h.handlers.submit(form(blank));
  assert.equal(h.calls.length, 0, 'a blank guest never reaches the server');
  assert.equal(guest.reported, 3);
  assert.equal(guest.validity, 'Type a guest name or choose a regular.');
  h.lang='zh';
  await h.handlers.submit(form({pid0: '', guest0: ''}));
  assert.equal(guest.validity, '请输入访客姓名，或选择一位常客。');
  await h.handlers.submit(form({pid0: '', guest0: '  Ann  '}));
  await h.handlers.submit(form({pid0: 'p1', guest0: ''}));
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls.map(c => c.payload))), [{members: [{name: 'Ann'}]}, {members: [{pid: 'p1'}]}]);
});
test('a required text field holding only spaces is stopped at the field, in both languages', async () => {
  const h = harness();
  const field = {value: '   ', validity: '', setCustomValidity(text) { this.validity = text; }, reportValidity() { return false; }};
  const form = (id, cls, values) => ({preventDefault() {}, target: {getAttribute: () => id, classList: {contains: c => c === cls}, querySelectorAll: sel => sel.includes('[required]') ? [field] : [], values}});
  for (const [id, cls, values] of [[null, 'player-form', {name: '   ', status: 'Active'}], ['settings-form', '', {name: '   ', format: 'singles', tables: '1', raceTo: '1'}], ['note-form', '', {text: '   '}]]) {
    field.validity = '';
    await h.handlers.submit(form(id, cls, values));
    assert.equal(field.validity, "Fill this in — spaces alone don't count.", id || cls);
  }
  assert.equal(h.calls.length, 0, 'nothing blank reaches the server');
  h.lang='zh';
  await h.handlers.submit(form('note-form', '', {text: '   '}));
  assert.equal(field.validity, '请填写此项，仅有空格不算。');
  field.value = 'Ada';
  await h.handlers.submit(form(null, 'player-form', {name: 'Ada', status: 'Active'}));
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name: 'player_save', payload: {name: 'Ada', status: 'Active'}}]);
});
test('a refusal shows the Chinese sentence the service sends with the code, round 41', () => {
  // Round 41: the console held its own English/Chinese table, so a rewording in python dropped the
  // Chinese with no test to catch it. The service sends {code, zh} in the refusal body now, and the
  // console reads it. An absent or unknown code keeps the generic Chinese answer.
  const h = harness();
  const generic = '请求未被接受，请检查输入或展开技术详情。';
  const row = refusalRow('Source already added');
  assert.equal(h.validationMessage('Source already added'), 'Source already added');
  h.lang='zh';
  assert.equal(h.validationMessage('Source already added', {code: row.code, zh: row.zh}), row.zh,
    'the served Chinese sentence is what the operator reads');
  assert.equal(h.validationMessage('Source already added', {code: row.code}), generic,
    'a code with no sentence keeps the generic answer');
  assert.equal(h.validationMessage('Source already added', {error: 'Source already added'}), generic,
    'a body with no code keeps the generic answer');
  assert.equal(h.validationMessage('Source already added', null), generic, 'a plain string keeps the generic answer');
  assert.equal(h.validationMessage('A source that was added before', [1, 2]), generic, 'a body of another shape keeps the generic answer');
  // The bite: python rewords the sentence. The console cannot answer with the old Chinese text,
  // because it no longer holds one, and it must never guess a sentence for an unknown code.
  assert.equal(h.validationMessage('A source that was added before', {code: 'source_exists'}), generic,
    'an unknown sentence is never mapped onto a sentence the console remembers');
});
test('a stream link the server refuses is explained before or after the request, in both languages', async () => {
  const h = harness();
  for (const path of ['subscriptions', 'inventory', 'wallet', 'jobs', 'turbo', 'Wallet']) {
    assert.equal(h.parseSource('https://www.twitch.tv/'+(path)+''), null, `${path} is a Twitch page, not a channel`);
  }
  assert.equal(h.parseSource('https://www.twitch.tv/examplechannel').channel, 'examplechannel');
  await h.handlers.submit(submission('sources-form', {url: 'https://www.twitch.tv/wallet'}));
  assert.equal(h.calls.length, 0, 'a reserved Twitch page never reaches the server');
  assert.equal(h.validationMessage('Source already added'), 'Source already added');
  h.lang='zh';
  // Round 41: the service sends the code and the Chinese sentence in the refusal body. The console
  // reads that sentence; it holds no table of its own (see refusalRow above).
  const sourceRow = refusalRow('Source already added');
  assert.equal(h.validationMessage('Source already added', sourceRow), sourceRow.zh);
  const urlRow = refusalRow('Use a Twitch channel or videos/<digits> URL');
  assert.equal(h.validationMessage('Use a Twitch channel or videos/<digits> URL', urlRow), urlRow.zh);
});
test('the console and the service agree on every Twitch source URL of the shared corpus', () => {
  // Both rules read tests/source_url_cases.json, so the console never offers a source that the
  // service refuses, and never hides a source that the service accepts. The python test
  // tests/test_source_url_parity.py drives the same rows through the service rule.
  const h = harness();
  const corpus = JSON.parse(fs.readFileSync(path.join(__dirname, 'source_url_cases.json'), 'utf8'));
  assert.ok(corpus.rows.length >= 30, `the corpus holds at least 30 rows, and it holds ${corpus.rows.length}`);
  for (const row of corpus.rows) {
    const parsed = h.parseSource(row.url);
    assert.equal(parsed ? 'accept' : 'refuse', row.verdict, `${row.url}: the console verdict must equal the corpus verdict. ${row.reason}`);
    assert.equal(parsed ? parsed.url : null, row.canonical, `${row.url}: the console canonical URL must equal the corpus canonical URL. ${row.reason}`);
    assert.equal(parsed ? (parsed.channel || parsed.video) : null, row.subject, `${row.url}: the console source name must equal the corpus source name.`);
  }
});
test('choosing a regular after the guest prompt clears it, so the browser lets the form submit', () => {
  const h = harness();
  const guest = {validity: 'Type a guest name or choose a regular.', setCustomValidity(text) { this.validity = text; }};
  const form = {querySelectorAll: sel => sel === 'input' ? [guest] : []};
  h.handlers.change({target: {id: '', name: 'pid0', form}});
  assert.equal(guest.validity, '');
});
test('a full floor is explained in plain words in both languages', () => {
  const h = harness();
  assert.equal(h.validationMessage('All tables are in use'), 'All tables are in use');
  h.lang='zh';
  // Round 41: the service sends the Chinese sentence with the code.
  const tableRow = refusalRow('All tables are in use');
  assert.equal(h.validationMessage('All tables are in use', tableRow), tableRow.zh);
});
test('appearance form serializes numbers and unchecked diamonds correctly', async () => {
  const h = harness();
  await h.handlers.submit(submission('appearance-form', {clothColor: '#1f4a70', lampGlow: '0.4'}));
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0])), {name: 'settings_update', payload: {clothColor: '#1f4a70', lampGlow: 0.4, showDiamonds: false, publicBoard: false}});
});
test('the appearance panel carries the public board switch, on by default, in EN and 中', () => {
  const h = harness();
  const html = h.appearancePanel();
  // A hidden input posts "off" when the box is not ticked, so an unticked box is a real false,
  // never an absent key; a missing setting reads as on, exactly as the board page reads it.
  assert.ok(html.includes('<input type="hidden" name="publicBoard" value="off">'), 'the hidden off input');
  assert.ok(html.includes('<input type="checkbox" name="publicBoard" value="on" checked>'), 'on by default');
  assert.ok(html.includes('Public board: on/off'), 'the EN label, as docs/public-board.md 6 spells it');
  h.lang='zh';
  assert.ok(h.appearancePanel().includes('公网记分板：开/关'), 'the 中 label');
});
test('the public board switch shows a board that is already off and posts a real boolean', async () => {
  const already = harness();
  already.data.settings={publicBoard:false};
  assert.ok(already.appearancePanel().includes('<input type="checkbox" name="publicBoard" value="on" >'),
    'an off board leaves the box unticked');
  const h = harness();
  await h.handlers.submit(submission('appearance-form', {clothColor: '#1d5c44', lampGlow: '0.3', showDiamonds: 'on', publicBoard: 'on'}));
  await h.handlers.submit(submission('appearance-form', {clothColor: '#1d5c44', lampGlow: '0.3', showDiamonds: 'on', publicBoard: 'off'}));
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls.map(c => [c.payload.publicBoard, typeof c.payload.publicBoard]))),
    [[true, 'boolean'], [false, 'boolean']]);
});
test('adding a regular never sends a rating the form did not collect; editing keeps it', async () => {
  const h = harness();
  const playerForm = values => ({preventDefault() {}, target: {getAttribute: () => null, classList: {contains: c => c === 'player-form'}, querySelectorAll: () => [], values}});
  assert.ok(!h.playerForm().includes('name="rating"'), 'create form has no rating field');
  await h.handlers.submit(playerForm({name: 'Ada', status: 'Active'}));
  h.realCall=h.calls[0];
  assert.equal('rating' in h.realCall.payload, false, 'no rating key, so JSON never carries NaN as null');
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0])), {name: 'player_save', payload: {name: 'Ada', status: 'Active'}});
  await h.handlers.submit(playerForm({id: 'p1', name: 'Ada', rating: '640', status: 'Active', notes: ''}));
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls[1])), {name: 'player_save', payload: {id: 'p1', name: 'Ada', rating: 640, status: 'Active', notes: ''}});
});
test('failed API response localizes primary copy and preserves exact optional detail', async () => {
  // Round 41: the console shows the Chinese sentence the service sends, so the stub body carries it.
  const row = refusalRow('Schedule match before scoring');
  const h = harness();
  (()=>{h.lang='zh'; h.render=()=>{}; h.errors=[]; h.message=(text,error,detail)=>h.errors.push({text,error,detail});return h.action=h.realAction})();
  h.context.fetch = async () => ({ok: false, status: 400, json: async () => ({error: 'Schedule match before scoring', code: row.code, zh: row.zh})});
  assert.equal(await h.action('match_score',{id:'match-1',score:[7,4]}), false);
  assert.ok(h.errors[0].text.includes(row.zh), h.errors[0].text);
  assert.equal(h.errors[0].detail, 'Schedule match before scoring');
  assert.ok(!h.errors[0].text.includes('Schedule match'));
  assert.equal(h.busy, false);
});

test('the clock paints the true remaining time on the first render, in every view', () => {
  const h = harness();
  // The defect: clockHTML() hardcoded 0:30, so any re-render (switching to
  // Vision, a stream repainting the strip) flashed a value the clock was not at.
  h.timer={duration:60,remaining:12.4,deadline:null};
  const painted = h.clockHTML();
  assert.ok(painted.includes('>0:13<'), 'the first paint is the real remaining time: ' + painted);
  assert.ok(!painted.includes('>0:30<'), 'never the hardcoded 0:30');
  // The bar scales (transform) rather than resizing (width) since the polish step: 12.4 / 60 = 0.2067.
  assert.ok(painted.includes('transform:scaleX(0.2067)'), 'the progress bar paints the live value too: ' + painted);
  // A running clock paints from the same source, and the interval writes with the
  // same formatter, so a paint and a tick can never disagree.
  h.timer={duration:60,remaining:12.4,deadline:Date.now()+7400};
  assert.ok(/>(0:0[7-8])</.test(h.clockHTML()), 'a deadline render is the live value too');
  (()=>{h.timer={duration:60,remaining:12.4,deadline:null}; h.seen=[];return h.context.document.querySelectorAll = sel => sel === '[data-clock]' ? [{textContent:'', classList:{toggle(){}}}].map(e => { h.seen.push(e); return e; }) : []})();
  h.tick();
  assert.equal(h.seen[0].textContent, '0:13', 'the interval writes exactly what the paint shows');
  assert.equal(h.clockText(h.clockLeft()), '0:13', 'and both go through clockText()');
  // Every view: the Vision surface carries its own [data-clock] (mobile hides the
  // strip that carries the desktop one), and it is painted by the same helpers.
  const surface = stageMarkup(h);
  assert.ok(surface.includes('data-clock'), 'the Vision stagebar carries the same clock element');
  assert.ok(surface.includes('>0:13<'), 'and its first paint is the same instant');
  // A cross-tab tick repaints; only a duration change re-renders the view.
  assert.ok(source.includes('durationChanged?render():tick()'), 'a cross-tab update paints the clock in place');
  // The clock is the server's now, and ops.js adopts it through that same
  // storage event: annotator/clock-sync.js dispatches it with a deadline in this
  // device's clock base, so the one 200 ms interval keeps painting every view
  // from the shared instant with no second painter.
  const serverNow = Date.now() - 5000;             // this device is 5 s fast
  const snapshot = {duration: 60, running: true, deadline_ms: serverNow + 30000, remaining_ms: 30000, seq: 9};
  h.timer={duration:60,remaining:12.4,deadline:null};
  // The naive push — the server's raw deadline — is 5 s out on this device.
  h.handlers['window:storage']({key: 'cp-ops-clock', newValue: JSON.stringify({duration: 60, remaining: 30, deadline: snapshot.deadline_ms})});
  assert.equal(h.clockText(h.clockLeft()), '0:25', 'a raw server deadline on a fast device is 5 s out');
  // What the sync layer actually sends: the same instant in the device's base.
  const adopted = clockSync.toLocalClock(snapshot, Date.now(), -5000);
  h.handlers['window:storage']({key: 'cp-ops-clock', newValue: JSON.stringify(adopted)});
  const shared = h.clockText(h.clockLeft());
  assert.ok(shared === '0:30' || shared === '0:29', 'the shared instant survives the skew: ' + shared);
  assert.equal(h.timer.duration, 60, 'and ops.js kept the server duration');
  assert.ok(h.clockHTML().includes('>' + shared + '<'), 'the strip paints it');
  assert.ok(stageMarkup(h).includes('>' + shared + '<'), 'and the Vision view paints the same instant');
  assert.ok(!clockSyncSource.includes('setInterval(tick'), 'the sync layer adds no second painter');
  assert.equal((source.match(/setInterval\(tick,200\)/g) || []).length, 1, 'ops.js keeps its one 200 ms interval');
});

// The console publishes one named seam for the shared clock, so the sync
// layer calls it instead of forging a StorageEvent that only happens to look like a tab event. The
// payload is the same one the event carried — the JSON string in newValue — and one parser serves
// both ways in, so a real cross-tab event and the hand-over cannot drift apart.
test('the console hands the clock over one named seam, not a forged StorageEvent', () => {
  const h = harness();
  assert.equal(typeof h.context.window.OpsClock, 'object', 'ops.js publishes window.OpsClock');
  assert.equal(typeof h.context.window.OpsClock.receive, 'function', 'with one receive() entry point');
  assert.ok(!/dispatchEvent\s*\(/.test(source), 'the console dispatches no synthetic event for the clock');
  assert.ok(!/new\s+(win\.)?StorageEvent/.test(clockSyncSource), 'the sync layer builds no StorageEvent');
  assert.ok(!/dispatchEvent\s*\(/.test(clockSyncSource), 'and dispatches nothing at the console');
  // What the sync layer sends: the same instant in this device's base, as JSON.
  const serverNow = Date.now() - 5000;                       // this device is 5 s fast
  const snapshot = {duration: 45, running: true, deadline_ms: serverNow + 20000, remaining_ms: 20000, seq: 11};
  const payload = JSON.stringify(clockSync.toLocalClock(snapshot, Date.now(), -5000));
  h.timer={duration:60,remaining:12.4,deadline:null};
  h.context.window.OpsClock.receive(JSON.parse(JSON.stringify(payload)));
  const shown = h.clockText(h.clockLeft());
  assert.ok(shown === '0:20' || shown === '0:19', 'the handed-over instant is what the console shows: ' + shown);
  assert.equal(h.timer.duration, 45, 'and the server duration came with it');
  assert.ok(h.clockHTML().includes('>' + shown + '<'), 'the strip paints it');
  // One parser serves both ways in: a real storage event from another tab still lands in receive().
  assert.equal(typeof h.handlers['window:storage'], 'function', 'a real cross-tab event still lands');
  h.handlers['window:storage']({key: 'cp-ops-clock', newValue: JSON.stringify({duration: 30, remaining: 9, deadline: null})});
  assert.equal(h.clockText(h.clockLeft()), '0:09', 'and adopts through the same parser');
  // A hand-over that cannot be read leaves the clock alone instead of throwing into the sync layer.
  h.context.window.OpsClock.receive('not json');
  assert.equal(h.clockText(h.clockLeft()), '0:09', 'a malformed payload is not adopted');
  h.context.window.OpsClock.receive({duration: 20, remaining: 5, deadline: null});
  assert.equal(h.clockText(h.clockLeft()), '0:05', 'an already-parsed payload is accepted too');
});

test('the sync layer hands the console the clock over that seam, and dispatches no event', async () => {
  const handed = [], dispatched = [];
  const doc = {
    hidden: false,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    documentElement: {dataset: {}, lang: 'en', getAttribute: () => null}
  };
  const win = {
    document: doc,
    location: {href: 'http://127.0.0.1:8130/ops.html'},
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: id => clearTimeout(id),
    setInterval: () => 0,                       // the retry/poll cadence is not under test here
    clearInterval() {},
    addEventListener() {},
    dispatchEvent(event) { dispatched.push(event); return true; },
    localStorage: {getItem: () => null, setItem() {}},
    OpsClock: {receive(value) { handed.push(value); }},
    EventSource: function () { this.addEventListener = () => {}; this.close = () => {}; },
    fetch: async () => ({ok: true, status: 200, json: async () => clockSnapshot({running: true, deadline_ms: Date.now() + 30000, remaining_ms: 30000, server_now_ms: Date.now()})})
  };
  const sync = clockSync.install(win);
  assert.ok(sync, 'install() wired the page up');
  await settle();
  assert.equal(handed.length, 1, 'the first snapshot went to the console over the seam');
  assert.ok(handed[0].includes('"deadline"'), 'with the same JSON the event used to carry: ' + handed[0]);
  assert.deepEqual(Object.keys(JSON.parse(handed[0])).sort(), ['deadline', 'duration', 'remaining'], 'and nothing else');
  assert.deepEqual(dispatched, [], 'no synthetic event was dispatched at the console');
  assert.equal(win.__clockSync, sync, 'the page keeps one sync object, as before');
});

// ---- the shared shot clock: annotator/clock-sync.js ------------------------
// The clock used to be a local timer per device. It is one clock on the server
// now, and ops.js stays the only painter: the sync layer hands it a deadline in
// this device's clock base through the storage event ops.js already listens for.

function clockSnapshot(overrides) {
  return Object.assign({duration: 30, running: false, remaining_ms: 30000, deadline_ms: null, seq: 4, updated_at: '2026-01-01T00:00:00+00:00'}, overrides || {});
}

function clockEnv(options) {
  const opts = options || {};
  const env = {now: 1000, timers: [], nextId: 1, calls: [], errors: [], statuses: [], applied: [], streams: []};
  env.advance = async function (ms) {
    const target = env.now + ms;
    for (;;) {
      let due = null;
      for (const timer of env.timers) if (timer.at <= target && (!due || timer.at < due.at)) due = timer;
      if (!due) break;
      env.now = due.at;
      if (due.repeat) due.at = due.at + due.ms;
      else env.timers.splice(env.timers.indexOf(due), 1);
      due.fn();
      await settle();
    }
    env.now = target;
    await settle();
  };
  env.answer = function (method) {
    return opts.responses ? opts.responses(method, env) : null;
  };
  env.sync = clockSync.createClockSync({
    now: () => env.now,
    timers: {
      setTimeout: (fn, ms) => { const timer = {id: env.nextId++, fn, at: env.now + ms, ms}; env.timers.push(timer); return timer.id; },
      setInterval: (fn, ms) => { const timer = {id: env.nextId++, fn, at: env.now + ms, ms, repeat: true}; env.timers.push(timer); return timer.id; },
      clearTimeout: id => { const i = env.timers.findIndex(timer => timer.id === id); if (i >= 0) env.timers.splice(i, 1); },
      clearInterval: id => { const i = env.timers.findIndex(timer => timer.id === id); if (i >= 0) env.timers.splice(i, 1); }
    },
    fetch: async (url, init) => {
      const method = (init && init.method) || 'GET';
      env.calls.push({method, url, body: init && init.body ? JSON.parse(init.body) : null});
      const answer = env.answer(method);
      if (answer) return answer;
      const snapshot = typeof opts.snapshot === 'function' ? opts.snapshot() : opts.snapshot;
      return {ok: true, status: 200, json: async () => clockSnapshot(Object.assign({server_now_ms: env.now}, snapshot))};
    },
    openStream: (url, handlers) => {
      const stream = {url, closed: false, close() { this.closed = true; }, emit: payload => handlers.event(payload), beat: payload => handlers.heartbeat(payload), fail: () => handlers.error()};
      env.streams.push(stream);
      return stream;
    },
    apply: (local, state) => env.applied.push({local, state}),
    onStatus: status => env.statuses.push(status),
    onError: (text, result) => env.errors.push({text, result}),
    lang: () => opts.lang || 'en'
  });
  return env;
}

test('the shared clock measures this device offset from one round trip, NTP style', () => {
  // A device 5 s fast answers a symmetric 40 ms round trip: it sends while its
  // own clock reads 5 000 000 and the server clock reads 4 995 020.
  const sent = 5000000, received = 5000040, serverNow = 4995020;
  const offset = clockSync.offsetEstimate(serverNow, sent, received);
  assert.equal(offset, -5000, 'offset = server_now − (t_send + rtt/2)');
  const snapshot = {duration: 30, running: true, deadline_ms: serverNow + 30000, remaining_ms: 30000};
  const left = clockSync.displayMs(snapshot, received, offset);
  assert.ok(Math.abs(left - 29960) <= 20, 'the true remaining time is recovered, not the device clock: ' + left);
  const naive = clockSync.displayMs(snapshot, received, 0);
  assert.ok(Math.abs(naive - (left - 5000)) < 50, 'without the offset the same device is exactly 5 s out: ' + naive);
  assert.equal(clockSync.displayMs({running: false, remaining_ms: 12000}, sent, offset), null, 'a paused clock has no deadline to display');
});

test('the shared clock hands ops.js a deadline in this device base, and never re-arms a past one', () => {
  assert.deepEqual(clockSync.toLocalClock({duration: 30, running: true, deadline_ms: 20000, remaining_ms: 5000}, 15000, 0),
    {duration: 30, remaining: 5, deadline: 20000});
  // 5 s fast: the same instant is 35 000 ms on this device's clock.
  assert.deepEqual(clockSync.toLocalClock({duration: 30, running: true, deadline_ms: 30000, remaining_ms: 10000}, 25000, -5000),
    {duration: 30, remaining: 10, deadline: 35000});
  // Already expired on the server: 0:00 with no deadline, so no device replays
  // the expiry message (ops.js shows it once, when a deadline it holds reaches 0).
  assert.deepEqual(clockSync.toLocalClock({duration: 30, running: true, deadline_ms: 14000, remaining_ms: 1000}, 15000, 0),
    {duration: 30, remaining: 0, deadline: null});
  assert.deepEqual(clockSync.toLocalClock({duration: 45, running: false, deadline_ms: null, remaining_ms: 12500}, 15000, 0),
    {duration: 45, remaining: 12.5, deadline: null});
});

test('a clock press reaches the server only once ops.js accepted it, as an explicit intent', () => {
  // The watch reads the clock ops.js WROTE: it accepted the press, so a fresh
  // deadline means this device just started, and a cleared one means it paused.
  const started = {duration: 30, remaining: 30, deadline: 1700000000000};
  const paused = {duration: 30, remaining: 12, deadline: null};
  assert.deepEqual(clockSync.intentFor('clock-toggle', undefined, started), {action: 'start'});
  assert.deepEqual(clockSync.intentFor('clock-toggle', undefined, paused), {action: 'pause'});
  assert.deepEqual(clockSync.intentFor('clock-reset', undefined, paused), {action: 'reset'});
  assert.deepEqual(clockSync.intentFor('clock-set', 45, {duration: 45, remaining: 45, deadline: null}), {action: 'set', duration: 45});
  // A press ops.js refused (the "delayed" guard while a match is absent) writes
  // no clock at all, so nothing is sent to the server.
  assert.equal(clockSync.intentFor('clock-toggle', undefined, null), null);
  // A duration that never landed (settings_update failed) is not sent either.
  assert.equal(clockSync.intentFor('clock-set', 45, {duration: 30, remaining: 30, deadline: null}), null);
});

test('the shared clock sends the intent the server accepts and adopts what comes back', async () => {
  const env = clockEnv({snapshot: {duration: 30, running: true, deadline_ms: 40000, remaining_ms: 20000}});
  env.sync.start();
  await settle();
  env.streams[0].emit(clockSnapshot({server_now_ms: env.now, duration: 30, running: true, deadline_ms: 40000, remaining_ms: 20000}));
  await settle();
  assert.equal(env.sync.status(), 'live');
  await env.sync.intent('start');
  assert.deepEqual(env.calls.at(-1).body, {action: 'start'}, 'duration is only legal with set');
  await env.sync.intent('reset');
  assert.deepEqual(env.calls.at(-1).body, {action: 'reset'});
  await env.sync.intent('set', 45);
  assert.deepEqual(env.calls.at(-1).body, {action: 'set', duration: 45});
  assert.equal(env.errors.length, 0);
  assert.equal(env.applied.length, 5, 'every accepted command paints the state the server returned');
  assert.equal(env.applied.at(-1).state.duration, 30);
  assert.equal(env.sync.status(), 'live', 'a command does not knock a live device out of live');
});

test('a failed clock command shows the error and leaves the displayed clock alone', async () => {
  const failed = clockEnv({responses: method => (method === 'POST' ? {ok: false, status: 500, json: async () => ({error: 'nope'})} : null)});
  const result = await failed.sync.intent('start');
  assert.equal(result.ok, false);
  assert.deepEqual(failed.applied, [], 'a command that did not land never becomes the displayed state');
  assert.equal(failed.sync.status(), 'connecting', 'and it never claims a sync it does not have');
  assert.equal(failed.errors[0].text, 'clock command failed — nothing changed');
  // The display still says what the server last said: the truth is pulled back.
  await failed.advance(2000);
  assert.equal(failed.calls.at(-1).method, 'GET');
  const busy = clockEnv({lang: 'zh', responses: method => (method === 'POST' ? {ok: false, status: 503, headers: {get: () => '5'}, json: async () => ({})} : null)});
  const busyResult = await busy.sync.intent('pause');
  assert.equal(busyResult.reason, 'busy');
  assert.equal(busy.errors[0].text, '服务器繁忙 — 正在重试');
  assert.deepEqual(busy.applied, []);
});

test('a 503 is not an exception: Retry-After is honoured and the last known clock stays', async () => {
  const env = clockEnv({snapshot: {duration: 30, running: false, remaining_ms: 30000}, responses: () => (env.busy ? {ok: false, status: 503, headers: {get: () => '5'}, json: async () => ({})} : null)});
  env.sync.start();
  await settle();
  assert.equal(env.calls.length, 1, 'the first answer arrives');
  assert.equal(env.applied.length, 1, 'and it is on screen');
  env.busy = true;
  env.streams[0].fail();
  await settle();
  const afterFail = env.calls.length;
  assert.equal(env.sync.status(), 'polling');
  await env.advance(4000);
  assert.equal(env.calls.length, afterFail, 'Retry-After: 5 holds the polls back');
  assert.deepEqual(env.errors, [], 'a busy server is not a command error');
  assert.equal(env.applied.length, 1, 'the last known clock stays on screen, unlabelled as anything better');
  await env.advance(1200);
  assert.ok(env.calls.length > afterFail, 'and the poll resumes after it');
  assert.ok(env.streams.length > 1, 'the reconnect waited for it too');
  assert.equal(clockSync.retryAfterMsFrom({headers: {get: () => '5'}}), 5000);
  assert.equal(clockSync.retryAfterMsFrom({headers: {get: () => null}}), clockSync.POLL_MS * 2);
});

test('the shared clock polls when the stream dies and stops once it is back', async () => {
  const env = clockEnv({snapshot: {duration: 30, running: false, remaining_ms: 30000}});
  env.sync.start();
  await settle();
  assert.equal(env.calls[0].method, 'GET', 'the first paint is the server clock, not localStorage');
  assert.equal(env.streams.length, 1, 'and the stream is opened');
  assert.equal(env.sync.status(), 'connecting', 'nothing is claimed before the server has spoken');
  env.streams[0].emit(clockSnapshot({server_now_ms: env.now}));
  await settle();
  assert.equal(env.sync.status(), 'live');
  env.streams[0].fail();
  await settle();
  assert.ok(env.streams[0].closed, 'a failed stream is closed, not left half-open');
  assert.equal(env.sync.status(), 'polling', 'a dead stream is not live');
  const before = env.calls.length;
  await env.advance(1000);
  assert.ok(env.calls.length > before, 'it falls back to GET /api/clock every second');
  await env.advance(1500);
  assert.equal(env.streams.length, 2, 'and keeps trying to reconnect');
  const during = env.calls.length;
  env.streams[1].beat({seq: 4, server_now_ms: env.now});
  await settle();
  assert.equal(env.sync.status(), 'live');
  await env.advance(3000);
  assert.equal(env.calls.length, during, 'polling stops as soon as the stream is back');
});

test('the shared clock treats 30 s of silence as a dead stream and says when it is offline', async () => {
  const env = clockEnv({snapshot: {duration: 30, running: false, remaining_ms: 30000}, responses: () => (env.down ? Promise.reject(new Error('down')) : null)});
  env.sync.start();
  await settle();
  env.streams[0].emit(clockSnapshot({server_now_ms: env.now}));
  await settle();
  assert.equal(env.sync.status(), 'live');
  await env.advance(31000);
  assert.ok(env.streams[0].closed, 'a stream that sends nothing for two heartbeats is dead');
  assert.equal(env.sync.status(), 'polling');
  const applied = env.applied.length;
  env.down = true;
  await env.advance(11000);
  assert.equal(env.sync.status(), 'offline', 'no answer for 10 s is offline, not "synced"');
  assert.equal(env.applied.length, applied, 'and the last known clock is still the one on screen');
  assert.ok(env.statuses.includes('offline'));
  env.down = false;
  await env.advance(1000);
  assert.equal(env.sync.status(), 'polling', 'the first answer back ends the offline state');
  assert.ok(env.applied.length > applied, 'and the truth lands on the clock again');
});

test('the shared clock re-syncs when the tab is shown again, focused, or back online', async () => {
  const env = clockEnv({snapshot: {duration: 30, running: false, remaining_ms: 30000}});
  const before = env.calls.length;
  await env.sync.resync('visibilitychange');
  await env.sync.resync('focus');
  await env.sync.resync('online');
  assert.equal(env.calls.length, before + 3);
  // Every resync carries the server's own clock reading, so the offset tracks a
  // device clock that drifts while the tab sleeps.
  const first = env.applied.at(-1);
  assert.ok(first.state.server_now_ms >= 1000);
});

test('the clock labels stay honest in English and 中文, and only a failure is printed', () => {
  // §12.1: the shot timer has one name, and this half no longer holds a copy of it. ops.js owns
  // words.shotTimer and publishes it on the seam, so the console's label and the clock's idea of
  // the console's language cannot drift apart - there is only one of each.
  assert.equal(clockSync.LABELS.en.kicker, undefined, 'the name is not copied into the sync half');
  assert.equal(clockSync.LABELS.zh.kicker, undefined, 'in either language');
  assert.equal(clockSync.LOCAL_TIMER_LIE, undefined, 'nor is the rendered text it used to match');
  assert.equal(clockSync.decorate, undefined, 'so the pass that rewrote labels on screen is gone');
  assert.equal(typeof clockSync.announce, 'function', 'and the one sentence is handed over the seam instead');
  assert.ok(/shotTimer:\['Shot timer','出杆计时'\]/.test(source), 'ops.js still defines the name exactly once, in both languages');
  // §13.3: the bar stopped narrating sync state. statusText() is now the failure path
  // only, in the language the shell publishes.
  assert.equal(clockSync.statusText('live', 'en', null), '', 'a synced clock says nothing at all');
  assert.equal(clockSync.statusText('polling', 'en', null), '', 'and reconnecting is not a sentence in the bar');
  assert.equal(clockSync.statusText('offline', 'en', null), '', 'nor is offline');
  assert.equal(clockSync.statusText('connecting', 'zh', null), '', 'nor is connecting');
  assert.equal(clockSync.statusText('live', 'en', 'clock command failed — nothing changed'),
    'clock command failed — nothing changed', 'a failed command still speaks');
  assert.equal(clockSync.statusText('busy', 'zh', '服务器繁忙 — 正在重试'), '服务器繁忙 — 正在重试', 'and so does a busy server');
  for (const words of [clockSync.LABELS.en, clockSync.LABELS.zh]) {
    assert.deepEqual(Object.keys(words).sort(), ['busy', 'failed'], 'the table holds two sentences and no name at all');
  }
  // The retired sentences are gone from the copy table itself, both languages, so a state
  // cannot leak back into the bar through the dictionary.
  for (const gone of ['live', 'polling', 'offline', 'connecting']) {
    assert.equal(clockSync.LABELS.en[gone], undefined, `en.${gone} is retired with the status line`);
    assert.equal(clockSync.LABELS.zh[gone], undefined, `zh.${gone} is retired with the status line`);
  }
  // What the clock still has to say is a fact about a command, and it says it in both languages.
  assert.equal(clockSync.LABELS.en.failed, 'clock command failed — nothing changed');
  assert.equal(clockSync.LABELS.zh.failed, '计时指令失败 — 未改变');
  assert.equal(clockSync.LABELS.en.busy, 'server busy — retrying');
  assert.equal(clockSync.LABELS.zh.busy, '服务器繁忙 — 正在重试');
});

test('round 34 / console candidate 5: the console publishes the shot timer name and its language on the seam, and paints the one sentence itself', () => {
  // The console's own facts leave through window.OpsClock, and the sync line is painted by the
  // file that emits it. No pass over the console's renders, and no language recovered by matching
  // text that happens to be on screen.
  const h = harness({richDom: true});
  const seam = h.context.window.OpsClock;
  assert.equal(typeof seam.words, 'function', 'the label leaves the console as a call, not as screen text');
  assert.deepEqual({...seam.words()}, {lang: 'en', kicker: 'Shot timer'}, 'the name and the language it is painted in, in one answer');
  assert.equal(seam.lang(), 'en', 'and the language on its own, for the sentence');
  h.lang = 'zh';
  assert.deepEqual({...seam.words()}, {lang: 'zh', kicker: '出杆计时'}, "the same call in the shell's other language");
  assert.equal(seam.lang(), 'zh');
  // The bar paints that same one name, from that same table.
  tabClick(h, 'clock');
  h.render();
  const slot = h.context.document.region('#ops-shell .clockbar');
  assert.ok(slot.innerHTML.includes('出杆计时'), 'the bar paints the one name the seam published');
  assert.ok(!/kicker/.test(slot.innerHTML), 'with no second line for a label: there is nothing left to rewrite');
  assert.ok(/<span class="sync-error" hidden><\/span>/.test(slot.innerHTML), 'a healthy clock leaves the sync line hidden and empty');
  // A failed command is the one sentence, and it is written into the markup this file emits.
  seam.sync('计时指令失败 — 未改变');
  assert.ok(slot.innerHTML.includes('>计时指令失败 — 未改变<'), 'the sentence is painted by the console, not by the sync half');
  assert.ok(!/class="sync-error" hidden/.test(slot.innerHTML), 'and it is not hidden while it says something');
  seam.sync('');
  assert.ok(/<span class="sync-error" hidden><\/span>/.test(slot.innerHTML), 'an empty sentence leaves it hidden and empty again');
});

test('round 34 / console candidate 5: the sync half hands its one sentence over the seam and reads an accepted press back, with no observer and no store poll', async () => {
  // The other half: ops.js is the only writer of the clock, so it is the only thing that can say
  // a press was taken. The page this runs on offers no observer, no createElement and no readable
  // store - install() still wires the clock up, and the console's DOM is never touched.
  let reads = 0, created = 0;
  const sentences = [], requests = [], handed = [];
  const doc = {
    hidden: false,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    createElement() { created += 1; return {classList: {add() {}, remove() {}}, setAttribute() {}, removeAttribute() {}}; },
    documentElement: {dataset: {}, lang: 'en', getAttribute: () => null}
  };
  const win = {
    document: doc,
    location: {href: 'http://127.0.0.1:8130/ops.html'},
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: id => clearTimeout(id),
    setInterval: () => 0,
    clearInterval() {},
    addEventListener() {},
    localStorage: {getItem() { reads += 1; return null; }, setItem() {}},
    OpsClock: {
      receive(value) { handed.push(value); },
      words: () => ({lang: 'zh', kicker: '出杆计时'}),
      sync(text) { sentences.push(text); }
    },
    EventSource: function () { this.addEventListener = () => {}; this.close = () => {}; },
    fetch: async (url, options) => {
      const method = (options && options.method) || 'GET';
      requests.push({url, method});
      if (method === 'POST') return {ok: true, status: 200, json: async () => clockSnapshot({running: true, deadline_ms: Date.now() + 20000, remaining_ms: 20000, server_now_ms: Date.now()})};
      return {ok: true, status: 200, json: async () => clockSnapshot({running: true, deadline_ms: Date.now() + 30000, remaining_ms: 30000, server_now_ms: Date.now()})};
    }
  };
  assert.equal(typeof win.MutationObserver, 'undefined', 'the page has no observer to install one on');
  const sync = clockSync.install(win);
  assert.ok(sync, 'install() still wires the clock up without one');
  await settle();
  assert.equal(created, 0, "and creates no node in it: the sync line belongs to ops.js's markup");
  assert.equal(reads, 0, 'the store is never opened');
  assert.equal(typeof win.OpsClock.onAccepted, 'function', 'the console reports an accepted press on the seam');
  assert.equal(sentences[sentences.length - 1], '', 'a healthy clock hands over an empty sentence, not a state line');
  assert.equal(handed.length, 1, 'and the first snapshot still reaches the console over receive()');
  // ops.js calls onAccepted in the very branches that write the clock: an accepted press is news.
  win.OpsClock.onAccepted('clock-toggle', undefined, {duration: 30, remaining: 20, deadline: Date.now() + 20000});
  await settle();
  assert.equal(requests.filter(r => r.method === 'POST').length, 1, 'the accepted press is mirrored to the server');
  assert.equal(reads, 0, 'still without opening the store');
  assert.equal(created, 0, "and still without touching the console's DOM");
  // A press ops.js refused is never reported, so a stale clock is never mirrored.
  win.OpsClock.onAccepted('clock-set', 45, {duration: 30, remaining: 20, deadline: null});
  await settle();
  assert.equal(requests.filter(r => r.method === 'POST').length, 1, 'a press the console did not take is not mirrored');
  // The language of the one sentence comes from the console as well, not from a rendered label.
  win.fetch = async (url, options) => {
    const method = (options && options.method) || 'GET';
    requests.push({url, method});
    if (method === 'POST') return {ok: false, status: 503, json: async () => ({error: 'busy'})};
    return {ok: true, status: 200, json: async () => clockSnapshot({})};
  };
  win.OpsClock.onAccepted('clock-reset', undefined, {duration: 30, remaining: 20, deadline: null});
  await settle();
  assert.equal(sentences[sentences.length - 1], '服务器繁忙 — 正在重试',
    'a failed command speaks the language the seam published: ' + sentences[sentences.length - 1]);
  assert.equal(created, 0, 'and even a failure paints nothing here: the sentence travelled, the node stayed');
});

test('a Twitch VOD picker sends the replay source the server accepts, never a live label', () => {
  const h = harness();
  h.pickReplay({vod_id:'https://www.twitch.tv/videos/1000000011',start_s:30,rate:2});
  assert.deepEqual(JSON.parse(JSON.stringify(h.liveSource())),
    {kind: 'vod-replay', vod_id: 'https://www.twitch.tv/videos/1000000011', start_s: 30, rate: 2});
  assert.equal(h.liveSourceLabel('vod-replay').includes('live'), false, 'a replay is never labelled live');
  assert.ok(h.liveSourceLabel('vod-replay').includes('1000000011'), 'the label names the VOD');
  assert.deepEqual(JSON.parse(JSON.stringify(h.replayChoice())),
    {vod_id: 'https://www.twitch.tv/videos/1000000011', start_s: 30, rate: 2}, 'the panel can show what was chosen');
  // An empty box is refused in the shell, before any request is made.
  (()=>{h.errors=[];return h.message=(text,error)=>h.errors.push({text,error})})();
  (()=>{h.vodChoice=null;return h.pickReplay({vod_id:'  '})})();
  assert.equal(h.errors.length, 1);
  assert.equal(h.replayChoice(), null);
});
test('a face photo that is too large or not an image is explained at the file field, in both languages', async () => {
  const h = harness();
  let read = 0;
  h.context.FileReader = function() { this.readAsDataURL = () => { read++; }; };
  const photo = {validity: '', files: [], setCustomValidity(text) { this.validity = text; }, reportValidity() { return false; }};
  const form = {preventDefault() {}, target: {id: 'enroll-form', dataset: {player: 'p1'}, querySelector: () => photo, querySelectorAll: () => [], values: {}}};
  photo.files = [{size: 8 * 1024 * 1024 + 1, type: 'image/jpeg'}];
  await h.handlers.submit(form);
  assert.equal(photo.validity, 'Choose a photo of 8 MB or less.');
  photo.files = [{size: 1000, type: 'application/pdf'}];
  await h.handlers.submit(form);
  assert.equal(photo.validity, 'Choose an image file (JPEG or PNG).');
  h.lang='zh';
  await h.handlers.submit(form);
  assert.equal(photo.validity, '请选择图片文件（JPEG 或 PNG）。');
  photo.files = [{size: 8 * 1024 * 1024 + 1, type: 'image/png'}];
  await h.handlers.submit(form);
  assert.equal(photo.validity, '请选择不超过 8 MB 的照片。');
  assert.equal(read, 0, 'nothing is read or uploaded');
  photo.files = [{size: 1000, type: 'image/jpeg'}];
  await h.handlers.submit(form);
  assert.equal(read, 1, 'a normal photo is read and sent');
  // Round 41: the service sends the Chinese sentence with the code.
  const imageRow = refusalRow('image_base64 is not a decodable image');
  assert.equal(h.validationMessage('image_base64 is not a decodable image', imageRow), imageRow.zh);
});
test('a VOD replay the server would refuse is explained before Start, in both languages', () => {
  const h = harness();
  (()=>{h.errors=[];return h.message=(text,error)=>h.errors.push({text,error})})();
  for (const bad of ["{vod_id:'https://www.twitch.tv/examplechannel'}", "{vod_id:'abc'}", "{vod_id:'0'}", "{vod_id:'1000000011',rate:9}"]) {
    (()=>{h.vodChoice=null;return h.pickReplay(vm.runInContext('(' + bad + ')', h.context))})();
    assert.equal(h.replayChoice(), null, `${bad} is not kept as the replay`);
  }
  assert.deepEqual(JSON.parse(JSON.stringify(h.errors.map(e=>[e.text,e.error]))), [
    ['Use a Twitch VOD id or https://www.twitch.tv/videos/<id>', true],
    ['Use a Twitch VOD id or https://www.twitch.tv/videos/<id>', true],
    ['Use a Twitch VOD id or https://www.twitch.tv/videos/<id>', true],
    ['Rate must be more than 0 and at most 8', true]]);
  (()=>{h.lang='zh'; h.errors=[]; h.pickReplay({vod_id:'abc'});return h.pickReplay({vod_id:'1000000011',rate:9})})();
  assert.deepEqual(JSON.parse(JSON.stringify(h.errors.map(e=>e.text))), ['请输入 Twitch 回放 id 或 https://www.twitch.tv/videos/<id> 网址', '倍速须大于 0 且不超过 8']);
  for (const good of ["{vod_id:'v1000000011',rate:8}", "{vod_id:'https://www.twitch.tv/videos/1000000011/'}", "{vod_id:'1000000011',rate:0.25}"]) {
    (()=>{h.vodChoice=null;return h.pickReplay(vm.runInContext('(' + good + ')', h.context))})();
    assert.notEqual(h.replayChoice(), null, `${good} is accepted`);
  }
});

test('the regular profile deletes face data only after a confirm that says what goes, and shows the counts', async () => {
  const click = (h, dataset) => h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
  for (const [lang, button, receipt, kept] of [
    ['en', 'Delete face data', 'Face data deleted: 3 stored faces, 1 matched person unbound, 2 face samples', 'name and results stay'],
    ['zh', '删除人脸数据', '人脸数据已删除：3 张人脸，解除 1 个匹配人物，2 个人脸样本', '姓名和成绩保留']]) {
    const h = harness(), messageNode = {textContent:'', className:''}, asked = [], sent = [];
    h.context.document.querySelector = selector => selector === '#message' ? messageNode : null;
    (()=>{h.lang=(lang); h.data.players=[{id:'p1',name:'Ana',status:'Active',rating:0}];return h.selected='p1'})();
    assert.ok(h.playersScreen().includes(`data-action="face-forget" data-id="p1"`), `${lang}: the profile offers it`);
    assert.ok(h.playersScreen().includes(`>${button}</button>`), `${lang}: labelled ${button}`);
    // cancelled: nothing is sent
    h.context.confirm = text => { asked.push(text); return false; };
    h.context.fetch = async (url, options) => { sent.push([url, JSON.parse(options.body)]); return {ok:true, json: async () => ({})}; };
    await click(h, {action:'face-forget', id:'p1'});
    assert.equal(sent.length, 0, `${lang}: a cancelled confirm sends nothing`);
    assert.ok(asked[0].includes(kept), `${lang}: the confirm says the operations record stays`);
    // confirmed: one POST with the player id, and a receipt with the counts
    h.context.confirm = () => true;
    h.context.fetch = async (url, options) => { sent.push([url, JSON.parse(options.body)]);
      return {ok:true, json: async () => ({forgotten:true, player_id:'p1', removed:{store_faces:3, scratch_faces:0, clusters_unbound:1, face_samples:2, faces:1}})}; };
    await click(h, {action:'face-forget', id:'p1'});
    assert.deepEqual(sent, [['/api/identity/forget', {player_id:'p1'}]]);
    assert.equal(messageNode.textContent, receipt);
    assert.equal(messageNode.className, '');
    // refused: the reason reaches the operator as an error
    h.context.fetch = async () => ({ok:false, status:404, json: async () => ({error:'no face data for this player'})});
    await click(h, {action:'face-forget', id:'p1'});
    assert.ok(messageNode.textContent.includes('no face data for this player') || lang === 'zh', `${lang}: the reason is shown`);
    assert.equal(messageNode.className, 'error');
  }
});
test('a renamed regular reads by their current name on every screen, archive included (R12)', () => {
  const h = harness();
  // Draw-time snapshot says "Ada"; the roster now says "Ada Lovelace". The guest keeps their typed name.
  (()=>{h.data.players=[{id:'p1',name:'Ada Lovelace',status:'Active',rating:700},{id:'p2',name:'Bo',status:'Active',rating:600}];
    const night=()=>({id:'t1',name:'Friday',format:'singles',raceTo:3,status:'complete',
      entrants:[{id:'e1',members:[{pid:'p1',name:'Ada'}]},{id:'e2',members:[{pid:'p2',name:'Bo'}]},{id:'e3',members:[{pid:null,name:'Walk-in Wu'}]}],
      matches:[{id:'m1',round:1,sides:['e1',null],score:[0,0],status:'complete',result:'bye',winnerId:'e1',absent:[]},
               {id:'m2',round:1,sides:['e2','e3'],score:[3,1],status:'complete',result:'played',winnerId:'e2',absent:[]},
               {id:'m3',round:2,sides:['e1','e2'],score:[3,2],status:'complete',result:'played',winnerId:'e1',absent:[]}]});
    h.data.tournament=night();h.data.history=[Object.assign(night(),{id:'h1',archivedAt:'2026-09-01T00:00:00Z'})];h.data.events=[];return h.data.notes=[]})();
  const views = {tonight: h.tonightScreen(), setup: h.entrantsCard(), matches: h.bracketScreen(), records: h.recordsScreen()};
  for (const [name, html] of Object.entries(views)) assert.ok(!/>Ada</.test(html) && !/\bAda \//.test(html), `${name}: the stale snapshot name never shows`);
  assert.ok(views.matches.includes('Ada Lovelace'), 'bracket shows the current name');
  // The night's own log lives inside its timeline body (5.4), so the night is the anchor, not <details>.
  const archive = views.records.slice(views.records.indexOf('data-event="h1"'));
  assert.ok(archive.includes('Ada Lovelace'), 'the archived event reads the live roster name for a regular');
  assert.ok(!/Ada —|— Ada\b|>Ada</.test(archive), 'the archive never falls back to the draw-time copy while the regular exists');
  assert.ok(archive.includes('Walk-in Wu'), 'a guest keeps the name typed at the desk');
  // a deleted regular (no roster row) still reads by the snapshot, never "Unknown"
  h.data.players=h.data.players.filter(p=>p.id!=='p2');
  assert.ok(h.bracketScreen().includes('>Bo'), 'the snapshot is the fallback when the regular is gone');
  assert.ok(/class="tl-pair">Bo — Walk-in Wu</.test(h.recordsScreen()), 'the archive in Records falls back to the snapshot too');
  assert.equal(JSON.stringify(h.resultStats("p1")), '{"wins":2,"losses":0}', 'the rename leaves the record whole; the bye is not a win');
  h.lang='zh';
  // Round 41: the service sends the Chinese sentence with the code.
  const guestRow = refusalRow('Name held by a guest in this event; add the guest to the regulars instead');
  assert.equal(h.validationMessage('Name held by a guest in this event; add the guest to the regulars instead', guestRow), guestRow.zh);
});
test('a refusal is readable over an open modal: the message sits above the backdrop', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const z = selector => Number(css.match(new RegExp(`${selector.replace(/[.#()]/g, '\\$&')}\\{[^}]*z-index:(\\d+)`))[1]);
  // The polish's distill step wrote `:is(#ops-shell, #ops-footer)` as `#ops-shell` (same specificity).
  assert.ok(z('#ops-shell #message') > z('.modal-backdrop'), 'the player modal must not cover the reason it was refused');
});
test('a bye reads Bye, never Signed or Waiting, and is not a signed card (R5)', () => {
  const h = harness();
  (()=>{h.data.players=[];h.data.events=[];h.data.notes=[];
    const night=()=>({id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
      entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bea'}]},{id:'e3',members:[{pid:null,name:'Cai'}]}],
      matches:[{id:'m1',round:1,sides:['e1',null],score:[0,0],status:'complete',result:'bye',winnerId:'e1',table:null,absent:[]},
               {id:'m2',round:1,sides:['e2','e3'],score:[3,1],status:'complete',result:'played',winnerId:'e2',table:null,absent:[]},
               {id:'m3',round:2,sides:['e1','e2'],score:[0,0],status:'scheduled',table:null,absent:[],sources:['m1','m2']}]});
    h.data.tournament=night();return h.data.history=[Object.assign(night(),{id:'h1',status:'complete',archivedAt:'2026-09-01T00:00:00Z'})]})();
  for (const [lang, bye, signed, waiting, cards] of [['en', 'Bye', 'Signed', 'Waiting', '1/2 signed'], ['zh', '轮空', '已签', '待定', '已签 1/2']]) {
    h.lang=(lang);
    const html = h.bracketScreen();
    const card = html.slice(html.indexOf('class="rounds"'));
    const first = card.slice(0, card.indexOf('<h3>', card.indexOf('<h3>') + 1));
    assert.ok(first.includes(`>${bye}<`), `${lang}: the bye card is labelled ${bye}`);
    assert.equal((first.match(new RegExp(`>${signed}<`, 'g')) || []).length, 1, `${lang}: only the played card says ${signed}`);
    assert.ok(!first.includes(`>${waiting}<`), `${lang}: the empty side of a bye never reads ${waiting}`);
    const line = html.match(/<span class="muted">([^<]*)<\/span>/)[1];
    assert.ok(line.includes(cards), `${lang}: the heading carries ${cards} - byes are left out of the count and its total`);
    const rec = h.recordsScreen(), archive = rec.slice(rec.indexOf('data-event="h1"'));
    assert.ok(archive.includes(`>${bye}<`) && !archive.includes(`${esc_(waiting)}`), `${lang}: the archive labels the bye too`);
    const play = h.playScreen();
    const draw = play.slice(play.indexOf('class="bracket-view"'));
    assert.ok(draw.match(/<span class="muted">([^<]*)<\/span>/)[1].includes(cards), `${lang}: the draw\u2019s heading line agrees`);
  }
  assert.equal(JSON.stringify(h.resultStats("x")), '{"wins":0,"losses":0}');
});
function esc_(s) { return `>${s}<`; }
test('a placeholder guest name is stopped at the field, in both languages (R5)', async () => {
  const h = harness();
  const guest = {validity: '', reported: 0, setCustomValidity(text) { this.validity = text; }, reportValidity() { this.reported++; return false; }};
  const form = values => ({preventDefault() {}, target: {getAttribute: () => 'entrant-form', classList: {contains: () => false}, querySelector: sel => sel === '[name=guest0]' ? guest : null, querySelectorAll: () => [], values}});
  for (const name of ['na', ' N/A ', 'Bye', 'TBD', '轮空', '輪空']) await h.handlers.submit(form({pid0: '', guest0: name}));
  assert.equal(h.calls.length, 0, 'a placeholder never reaches the server');
  assert.equal(guest.reported, 6);
  assert.equal(guest.validity, 'Byes are added by the draw automatically. Type the guest’s real name.');
  h.lang='zh';
  await h.handlers.submit(form({pid0: '', guest0: 'bye'}));
  assert.equal(guest.validity, '轮空由抽签自动安排，请输入访客的真实姓名。');
  // Round 41: the service sends the Chinese sentence with the code.
  const byeRow = refusalRow("A bye is added by the draw; type the guest's real name");
  assert.equal(h.validationMessage("A bye is added by the draw; type the guest's real name", byeRow), byeRow.zh);
  await h.handlers.submit(form({pid0: '', guest0: 'Nadia'}));
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls.map(c => c.payload))), [{members: [{name: 'Nadia'}]}]);
});
test('racking an unsaved event saves the name the form shows first (R2)', async () => {
  const h = harness();
  const nameField = {value: '8-Ball Open · Fri 9/26'};
  h.context.document.querySelector = sel => sel === '#settings-form [name=name]' ? nameField : null;
  h.data.tournament={id:'t1',name:'',format:'singles',tables:1,raceTo:1,status:'registration',entrants:[{id:'e1',members:[]},{id:'e2',members:[]}],matches:[]};
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'tournament-start'}}}});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name: 'tournament_setup', payload: {name: '8-Ball Open · Fri 9/26'}}, {name: 'tournament_start'}]);
  // an event that already has a name is racked as is
  (()=>{h.calls=[];return h.data.tournament.name='Friday 8-Ball'})();
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'tournament-start'}}}});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name: 'tournament_start'}]);
});
test('after the draw and in the archive only the name can be edited, and it is audited (R2)', async () => {
  const h = harness();
  (()=>{h.data.events=[{action:'tournament_rename',createdAt:'2026-09-26T10:00:00Z',revision:9,context:{id:'t1',name:'New'}}];h.data.notes=[];h.data.players=[];
    h.data.tournament={id:'t1',name:'Friday',format:'singles',tables:1,raceTo:3,status:'active',entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bea'}]}],matches:[{id:'m1',round:1,sides:['e1','e2'],score:[0,0],status:'scheduled',table:null,absent:[]}]};return h.data.history=[{id:'h1',name:'',format:'singles',raceTo:1,status:'complete',archivedAt:'2026-09-01T00:00:00Z',entrants:[],matches:[]}]})();
  for (const [lang, rename, label] of [['en', 'Rename event', 'Event renamed'], ['zh', '重命名赛事', '赛事已重命名']]) {
    h.lang=(lang);
    const dialog = h.setupForm(false);
    assert.ok(dialog.includes('id="settings-form"'), `${lang}: the settings dialog is where a drawn night is edited`);
    assert.ok(/name="name"/.test(dialog) && !/name="(format|raceTo|tables)"/.test(dialog), `${lang}: once the rules are locked it carries the name only`);
    assert.ok(dialog.includes(`>${h.esc(h.t('save'))}<`), `${lang}: and its one primary is Save`);
    assert.ok(h.startModal(true).includes(h.esc(h.t('locked'))),
      `${lang}: the rules stay locked, and the dialog that offers to edit the name says why`);
    assert.equal((dialog.match(/name="name"/g) || []).length, 1, `${lang}: the name is edited in one place only`);
    assert.ok(h.entrantsCard().includes(`>${rename}<`) || h.recordsScreen().includes(`>${rename}<`),
      `${lang}: ${rename} is the archived row's control now, not a form on Tonight`);
    const matches = h.recordsScreen();
    assert.ok(matches.includes('data-action="rename-archived"') && matches.includes('data-id="h1"'), `${lang}: an archived event can be renamed`);
    assert.ok(!/<summary>h1 /.test(matches), `${lang}: an unnamed archive never shows its raw id`);
    assert.ok(h.auditLine(h.data.events[0]).includes(label), `${lang}: the audit line reads ${label}`);
  }
  const submit = values => h.handlers.submit({preventDefault() {}, target: {getAttribute: () => 'settings-form', classList: {contains: () => false}, querySelector: () => null, querySelectorAll: () => [], values}});
  await submit({id: 't1', name: '  Friday Final '});
  h.context.prompt = () => ' July night ';
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'rename-archived', id: 'h1'}}}});
  h.context.prompt = () => null;
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'rename-archived', id: 'h1'}}}});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name: 'tournament_rename', payload: {id: 't1', name: 'Friday Final'}}, {name: 'tournament_rename', payload: {id: 'h1', name: 'July night'}}]);
});
test('forfeit and in-match absence are reachable from the Matches bracket, each behind a confirm (F1, R7)', async () => {
  const h = harness();
  (()=>{h.data.players=[];h.data.events=[];h.data.notes=[];h.data.history=[];return h.data.tournament={id:'t1',name:'Friday',format:'singles',tables:2,raceTo:3,status:'active',
      entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bea'}]},{id:'e3',members:[{pid:null,name:'Cai'}]},{id:'e4',members:[{pid:null,name:'Dee'}]}],
      matches:[{id:'m1',round:1,sides:['e1','e2'],score:[0,0],status:'scheduled',table:null,absent:[]},
               {id:'m2',round:1,sides:['e3','e4'],score:[1,0],status:'live',table:1,absent:[]},
               {id:'m3',round:2,sides:[null,null],score:[0,0],status:'pending',table:null,absent:[],sources:['m1','m2']}]}})();
  const html = h.bracketScreen();
  // The card is found by the action it carries: the header no longer prints the machine id (round 19).
  const card = id => {
    const at = html.indexOf(`data-id="${id}"`);
    if (at < 0) return '';
    const start = html.lastIndexOf('class="entry', at);
    const end = html.indexOf('class="entry', at);
    return html.slice(start < 0 ? 0 : start, end < 0 ? html.length : end);
  };
  for (const id of ['m1', 'm2']) {
    const c = card(id);
    assert.ok(/data-action="forfeit"[^>]*data-side="0"/.test(c) && /data-action="forfeit"[^>]*data-side="1"/.test(c), `${id}: forfeit for either side`);
    assert.ok(!/data-action="absence"/.test(c), `${id}: nothing on the card marks a side absent (round 13, owner item 5)`);
  }
  assert.ok(!/m3[^]*data-action="forfeit"/.test(html.slice(html.indexOf('m3'.slice(0, 8)))), 'a pending match (no sides yet) offers no forfeit');
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  const asked = [];
  h.context.confirm = msg => { asked.push(msg); return false; };
  await click({action: 'forfeit', id: 'm1', side: '0'});
  assert.equal(h.calls.length, 0, 'a cancelled confirm sends nothing');
  assert.deepEqual(asked, ['Record a forfeit for this side and advance the opponent?'], 'one confirm, for the forfeit');
  h.context.confirm = msg => { asked.push(msg); return true; };
  h.lang='zh';
  await click({action: 'forfeit', id: 'm2', side: '1'});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name: 'match_forfeit', payload: {id: 'm2', side: 1}}],
    'the write is the forfeit contract, and attendance is not part of it (round 13, owner item 5)');
});
test('standings count results, not ratings; the event table sorts wins, win %, name (R4)', () => {
  const h = harness();
  // Ann beats Bea (played) and Cai (forfeit: Cai no-show); Dee has a bye then loses to Ann... (sizes kept small)
  (()=>{h.data.events=[];h.data.notes=[];
    h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:100},{id:'pb',name:'Bea',status:'Active',rating:900},{id:'pc',name:'Cai',status:'Active',rating:500},{id:'pd',name:'Dee',status:'Active',rating:400}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    h.data.tournament={id:'t2',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',
      entrants:[E('a','pa','Ann'),E('b','pb','Bea'),E('c','pc','Cai'),E('d','pd','Dee'),E('g',null,'Gus')],
      matches:[{id:'x1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[]},
               {id:'x2',round:1,sides:['b','c'],score:[3,1],status:'complete',result:'played',winnerId:'b',absent:[]},
               {id:'x3',round:1,sides:['d','g'],score:[0,0],status:'complete',result:'forfeit',winnerId:'d',absent:[]},
               {id:'x4',round:2,sides:['a','b'],score:[3,2],status:'complete',result:'played',winnerId:'a',absent:[]},
               {id:'x5',round:2,sides:['d',null],score:[0,0],status:'pending',absent:[]}]};return h.data.history=[{id:'t1',name:'Last week',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T00:00:00Z',
      entrants:[E('a1','pa','Ann'),E('b1','pb','Bea')],
      matches:[{id:'y1',round:1,sides:['a1','b1'],score:[1,3],status:'complete',result:'played',winnerId:'b1',absent:[]}]}]})();
  assert.equal(JSON.stringify(h.record(h.tournament(),"a")), '{"wins":1,"losses":0,"played":1}', 'a bye is neither a win nor a played match');
  assert.equal(JSON.stringify(h.record(h.tournament(),"d")), '{"wins":1,"losses":0,"played":1}', 'a forfeit win counts as a signed result');
  assert.equal(JSON.stringify(h.record(h.tournament(),"g")), '{"wins":0,"losses":1,"played":1}');
  const cell = (standing, name, col) => {
    const at = standing.indexOf(`>${name}<`);
    assert.ok(at > 0, `the standing lists ${name}`);
    return standing.slice(at, standing.indexOf('</button>', at));
  };
  for (const [lang, rating, legend] of [['en', 'House rating (manual)', 'Tonight: wins-losses'], ['zh', '球房评分（手动）', '本场战绩：胜-负']]) {
    h.lang=(lang);
    const html = h.playScreen(), standing = h.playersScreen();
    assert.ok(standing.includes(`>${rating}<`), `${lang}: the rating still names itself on the row`);
    // All-time, signed results only: Ann 1-1 (bye excluded), Bea 2-1 (3 played), Dee 1-0 (forfeit win).
    assert.ok(cell(standing, 'Bea').includes('>900<'), `${lang}: the house rating is on Bea's row`);
    assert.ok(cell(standing, 'Bea').includes('2\u20131 \u00b7 67%'), `${lang}: Bea reads 2\u20131 of 3, 67%`);
    assert.ok(cell(standing, 'Ann').includes('1\u20131 \u00b7 50%'), `${lang}: Ann reads 1\u20131 of 2, 50%`);
    assert.ok(cell(standing, 'Dee').includes('1\u20130 \u00b7 100%'), `${lang}: Dee reads 1\u20130, 100%`);
    assert.ok(!standing.includes('>Gus<'), `${lang}: a guest holds no house standing (6.1)`);
    const cardHtml = html.slice(html.indexOf('class="card card--entrants"'));
    // Round 19, owner item 3: the record lives on each entrant's row, so the wording is a chip's
    // title rather than a fold's heading.
    assert.ok(html.includes('data-vs-role="record-legend"') && html.includes(`>${legend}<`),
      `${lang}: the heading names what the numbers are: ${legend}`);
    const order = [...cardHtml.matchAll(/<span class="grow">([^<]+)<small>/g)].map(m => m[1]);
    // Round 19, owner item 3: the entrants list is the entry order. The standings a table used to sort
    // into live in the draw, where the winner of each match is already visible.
    const entryOrder = JSON.parse(JSON.stringify(h.entrants().map(e => h.ename(e.id))));
    assert.deepEqual(order, entryOrder, `${lang}: the list keeps the order the entrants signed up in`);
    assert.equal((cardHtml.match(/data-vs-role="entrant-record"/g) || []).length, entryOrder.length,
      `${lang}: every entrant carries their own record, and no table sorts them a second time`);
  }
});
test('a player record is all-time and read-only, with head-to-head from signed matches only (R15, R8)', async () => {
  const h = harness();
  (()=>{h.data.events=[];h.data.notes=[];
    h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:100,joinedAt:'2026-01-01T00:00:00Z'},{id:'pb',name:'Bea',status:'Active',rating:900},{id:'pc',name:'Cai',status:'Active',rating:500}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    h.data.tournament={id:'t3',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',
      entrants:[E('a','pa','Ann'),E('b','pb','Bea'),E('g',null,'Gus')],
      matches:[{id:'x1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[]},
               {id:'x2',round:1,sides:['b','g'],score:[0,0],status:'complete',result:'forfeit',winnerId:'b',absent:[],completedAt:'2026-09-26T20:00:00Z'},
               {id:'x3',round:2,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',absent:[],completedAt:'2026-09-26T21:00:00Z'}]};return h.data.history=[
      {id:'t1',name:'First',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T12:00:00Z',entrants:[E('a1','pa','Ann'),E('b1','pb','Bea')],
       matches:[{id:'y1',round:1,sides:['a1','b1'],score:[1,3],status:'complete',result:'played',winnerId:'b1',absent:[],completedAt:'2026-09-01T20:00:00Z'}]},
      {id:'t2',name:'Second',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-10T00:00:00Z',entrants:[E('a2','pa','Ann'),E('c2','pc','Cai'),E('g2',null,'Gus')],
       matches:[{id:'z1',round:1,sides:['a2','c2'],score:[3,0],status:'complete',result:'played',winnerId:'a2',absent:[],completedAt:'2026-09-10T20:00:00Z'},
                {id:'z2',round:1,sides:['g2',null],score:[0,0],status:'complete',result:'bye',winnerId:'g2',absent:[]},
                {id:'z3',round:2,sides:['a2','g2'],score:[0,0],status:'complete',result:'forfeit',winnerId:'g2',absent:[],completedAt:'2026-09-10T21:00:00Z'}]}]})();
  // Ann: vs Bea 1-1 (played), vs Cai 1-0 (played); forfeit loss to Gus and the bye stay out of head-to-head.
  assert.equal(JSON.stringify(h.headToHead("pa")), JSON.stringify([
    {opponent: 'Bea', guest: false, wins: 1, losses: 1, played: 2, forfeits: 0, last: '2026-09-26T21:00:00Z'},
    {opponent: 'Cai', guest: false, wins: 1, losses: 0, played: 1, forfeits: 0, last: '2026-09-10T20:00:00Z'},
    {opponent: 'Gus', guest: true, wins: 0, losses: 0, played: 0, forfeits: 1, last: '2026-09-10T21:00:00Z'}]));
  h.render=()=>{};
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  await click({action: 'select-player', id: 'pa'});
  const modal = h.playersScreen();
  assert.ok(modal.includes('data-action="player-record"') && modal.includes('data-id="pa"'), 'the regular profile links to the record');
  await click({action: 'player-record', id: 'pa'});
  for (const [lang, title, h2h, scope, sample, guest] of [
    ['en', 'Player record', 'Head-to-head', 'Signed results in 3 events since 2026-09-01. Read-only.', 'Sample', 'guest, matched by name'],
    ['zh', '球员战绩', '交手记录', '自 2026-09-01 起 3 场赛事的已签赛果', '样本', '访客，按姓名匹配']]) {
    h.lang=(lang);
    const html = h.playersScreen();
    assert.ok(html.includes(`>${title}<`) || html.includes(`${title} ·`), `${lang}: record title`);
    assert.ok(html.includes(scope), `${lang}: the scope is stated: ${scope}`);
    assert.ok(html.includes(`>${h2h}<`), `${lang}: head-to-head section`);
    assert.ok(html.includes(sample), `${lang}: sample size is labelled`);
    assert.ok(html.includes(guest), `${lang}: a guest opponent is labelled as matched by name`);
    const table = html.slice(html.indexOf('<table class="h2h"'), html.indexOf('</table>', html.indexOf('<table class="h2h"')));
    assert.ok(/>Bea<\/td><td>1–1<\/td><td>50%<\/td><td>2<\/td>/.test(table), `${lang}: Bea row W–L, %, n`);
    assert.ok(/Gus[^]*?<td>0–0<\/td><td>—<\/td><td>0<\/td><td>1<\/td>/.test(table), `${lang}: a forfeit-only opponent has no win % and the forfeit is shown apart`);
    assert.ok(!/<form|<input|data-action="player-(save|delete)"/.test(html.slice(html.indexOf('class="record"'))), `${lang}: the record is read-only`);
    const totals = html.slice(html.indexOf('class="record"')).match(/<small>[^<]*<\/small><strong>([^<]*)<\/strong>/g).slice(0, 4).map(s => s.replace(/<[^>]+>/g, '|').split('|').filter(Boolean)[1]);
    assert.deepEqual(totals, ['4', '2', '2', '50%'], `${lang}: totals are resultStats: signed results, a forfeit counts, a bye does not`);
  }
  assert.equal(h.calls.length, 0, 'reading a record never writes');
  await click({action: 'record-back'});
  assert.ok(h.playersScreen().includes('data-action="player-record"'), 'back returns to the profile');
});
test('a results sheet prints the whole bracket and copies as text, champion from the final (R10)', async () => {
  const h = harness();
  (()=>{h.data.events=[];h.data.notes=[];h.data.players=[{id:'pa',name:'Ada',status:'Active',rating:1}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    h.data.tournament={id:'t0',name:'',format:'singles',tables:1,raceTo:3,status:'registration',entrants:[],matches:[]};return h.data.history=[{id:'h1',name:'Friday 8-Ball',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-26T12:00:00Z',
      entrants:[E('a','pa','Ada (old)'),E('b',null,'Bo'),E('c',null,'Cy')],
      matches:[{id:'m1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[]},
               {id:'m2',round:1,sides:['b','c'],score:[0,0],status:'complete',result:'forfeit',winnerId:'b',absent:[]},
               {id:'m3',round:2,sides:['a','b'],score:[3,2],status:'complete',result:'played',winnerId:'a',absent:[],sources:['m1','m2']}]}]})();
  assert.equal(h.resultsText(h.data.history[0]), [
    'Friday 8-Ball · 2026-09-26', 'Singles · Race to 3', 'Champion: Ada', '',
    'Round 1', 'Ada: bye (advances, not a win)', 'Bo wins by forfeit vs Cy', '',
    'Final', 'Ada 3–2 Bo', '', 'Signed results only. A bye advances a player but is not a win.'].join('\n'));
  h.lang='zh';
  assert.equal(h.resultsText(h.data.history[0]), [
    'Friday 8-Ball · 2026-09-26', '单打 · 抢3', '冠军：Ada', '',
    '轮次 1', 'Ada：轮空晋级（不计胜场）', 'Cy 弃权，Bo 晋级', '',
    '决赛', 'Ada 3–2 Bo', '', '仅含已签赛果。轮空晋级不计为胜场。'].join('\n'));
  // an unfinished bracket never names a champion
  (()=>{h.lang='en';return h.data.history[0].matches[2]={...h.data.history[0].matches[2],status:'scheduled',result:undefined,winnerId:null,score:[0,0]}})();
  assert.ok(h.resultsText(h.data.history[0]).includes('Champion: not decided yet'));
  assert.ok(h.resultsText(h.data.history[0]).includes('Ada vs Bo: not played yet'));
  h.data.history[0].matches[2].sides=['a',null];
  assert.ok(h.resultsText(h.data.history[0]).includes('Ada vs TBD: not played yet'), 'an undecided side is TBD, never Waiting');
  h.data.history[0].matches[2].sides=['a','b'];
  h.data.history[0].matches[2]={...h.data.history[0].matches[2],status:'complete',result:'played',winnerId:'a',score:[3,2]};
  // the sheet view: reached from the archive, read-only, full bracket, print + copy controls
  h.render=()=>{};
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  assert.ok(h.recordsScreen().includes('data-action="results-sheet" data-id="h1"'), 'each archived event offers its sheet');
  h.data.tournament.matches=[{id:'q1',round:1,sides:['x','y'],score:[0,0],status:'scheduled',absent:[]}];
  assert.ok(!h.playScreen().includes('data-action="results-sheet"'), 'a drawn night does not offer the sheet yet (round 19, owner item 1)');
  h.data.tournament.matches=[];
  assert.ok(!h.playScreen().includes('data-action="results-sheet"'), 'no sheet before the draw');
  await click({action: 'results-sheet', id: 'h1'});
  assert.equal(h.sheetId, 'h1', 'the click opens the sheet');
  const sheet = h.tonightScreen();
  assert.ok(sheet.includes('class="stack results-sheet"'), 'the sheet replaces the Close view');
  assert.ok(/class="champion"[^]*?Ada/.test(sheet), 'the champion is the final winner, by the live roster name');
  assert.equal((sheet.match(/class="sheet-round"/g) || []).length, 2, 'every round is on the sheet');
  assert.ok(sheet.includes('data-action="print-sheet"') && sheet.includes('data-action="copy-results"'));
  assert.ok(!/<form|<input/.test(sheet), 'the sheet is read-only');
  let copied = null;
  h.context.navigator = {clipboard: {writeText: async text => { copied = text; }}};
  await click({action: 'copy-results', id: 'h1'});
  assert.equal(copied, h.resultsText(h.data.history[0]));
  let printed = 0;
  h.context.print = () => { printed++; };
  await click({action: 'print-sheet'});
  assert.equal(printed, 1);
  assert.equal(h.calls.length, 0, 'a sheet never writes');
  await click({action: 'sheet-back'});
  assert.ok(!h.playScreen().includes('class="stack results-sheet"'), 'back returns to Close');
  await click({action: 'results-sheet', id: 'h1'});
  h.canNavigate=()=>true;
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {tab: 'floor'}}}});
  assert.equal(h.sheetId, null, 'leaving the screen closes the sheet');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const print = css.slice(css.indexOf('@media print'));
  assert.ok(print.length > 20 && /header[^{]*\{[^}]*display:none/.test(print) && /\.no-print[^{]*\{[^}]*display:none/.test(print), 'print hides the shell chrome and the sheet buttons');
  assert.ok(/\.results-sheet[^{]*\.note[^{]*\{[^}]*background:#fff/.test(print), 'the scope note prints on white, not on the dark panel');
});
test('delete only an unsigned event; otherwise hide it from history, which erases nothing (R1)', async () => {
  const h = harness();
  (()=>{h.data.events=[];h.data.notes=[];h.data.players=[{id:'pa',name:'Ada',status:'Active',rating:1}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    h.data.tournament={id:'t0',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'registration',entrants:[E('x',null,'Xu')],matches:[]};return h.data.history=[
      {id:'h1',name:'Signed night',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T12:00:00Z',entrants:[E('a','pa','Ada'),E('b',null,'Bo')],
       matches:[{id:'m1',round:1,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',absent:[]}]},
      {id:'h2',name:'Mistake',format:'singles',raceTo:1,status:'active',archivedAt:'2026-09-02T12:00:00Z',entrants:[E('c',null,'Cy')],matches:[]},
      {id:'h3',name:'Hidden night',hidden:true,format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-03T12:00:00Z',entrants:[E('a3','pa','Ada'),E('d',null,'Di')],
       matches:[{id:'m3',round:1,sides:['a3','d'],score:[0,0],status:'complete',result:'forfeit',winnerId:'a3',absent:[]}]}]})();
  h.render=()=>{};
  for (const [lang, del, hide, unhide, showHidden] of [['en', 'Delete event', 'Hide from history', 'Show in history', 'Show 1 hidden'], ['zh', '删除赛事', '从历史中隐藏', '恢复显示', '显示 1 场已隐藏']]) {
    (()=>{h.lang=(lang);return h.showHidden=false})();
    const html = h.recordsScreen();
    // One night is one timeline item: from its own data-event to the next night's.
    const block = id => { const i = html.indexOf(`data-event="${id}"`); if (i < 0) return '';
      const next = html.indexOf('data-event="', i + 12); return html.slice(i, next < 0 ? html.length : next); };
    assert.ok(block('h1').includes(`>${hide}<`) && !block('h1').includes(`>${del}<`), `${lang}: a signed event can only be hidden`);
    assert.ok(block('h2').includes(`>${del}<`), `${lang}: an unsigned event can be deleted`);
    assert.ok(!html.includes('Hidden night'), `${lang}: a hidden event is out of the list`);
    assert.ok(html.includes(`>${showHidden}<`), `${lang}: the hidden count is offered`);
    h.showHidden=true;
    const all = h.recordsScreen();
    assert.ok(all.includes('Hidden night') && all.includes(`>${unhide}<`), `${lang}: hidden events can be shown and restored`);
    assert.ok(h.playScreen().includes('data-action="event-delete" data-id="t0"'), `${lang}: tonight, unsigned, can be deleted from Close`);
  }
  assert.equal(JSON.stringify(h.resultStats("pa")), '{"wins":2,"losses":0}', 'a hidden event still counts: hiding erases nothing');
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  const asked = [];
  h.context.confirm = msg => { asked.push(msg); return false; };
  h.lang='en';
  await click({action: 'event-delete', id: 'h2'});
  await click({action: 'event-hide', id: 'h1', hidden: 'true'});
  assert.equal(h.calls.length, 0, 'a cancelled confirm sends nothing');
  assert.deepEqual(asked, ['Delete “Mistake”? No result was signed in it. This cannot be undone.', 'Hide “Signed night” from history? Its results and every player’s stats stay; you can show it again.']);
  h.context.confirm = msg => { asked.push(msg); return true; };
  h.lang='zh';
  await click({action: 'event-delete', id: 'h2'});
  await click({action: 'event-hide', id: 'h1', hidden: 'true'});
  await click({action: 'event-hide', id: 'h3', hidden: 'false'});
  assert.equal(asked[2], '删除“Mistake”？该赛事没有已签赛果。此操作无法撤销。');
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [
    {name: 'tournament_delete', payload: {id: 'h2', confirm: true}},
    {name: 'tournament_hide', payload: {id: 'h1', hidden: true, confirm: true}},
    {name: 'tournament_hide', payload: {id: 'h3', hidden: false, confirm: true}}]);
  for (const [action, en, zh] of [['tournament_delete', 'Event deleted (nothing was signed)', '删除赛事（无已签赛果）'], ['tournament_hide', 'Event hidden / shown in history', '赛事在历史中隐藏 / 恢复']]) {
    h.lang='en'; assert.ok(h.auditLine({action:(action),createdAt:'2026-09-26T00:00:00Z',revision:1,context:{name:'X'}}).includes(en));
    h.lang='zh'; assert.ok(h.auditLine({action:(action),createdAt:'2026-09-26T00:00:00Z',revision:1,context:{name:'X'}}).includes(zh));
  }
  // Round 41: the service sends the Chinese sentence with the code.
  const deleteRow = refusalRow('An event with a signed result cannot be deleted; hide it from history instead');
  assert.equal(h.validationMessage('An event with a signed result cannot be deleted; hide it from history instead', deleteRow), deleteRow.zh);
});
test('a second chance is a labelled random draw, confirmed, undoable, never a result (R6)', async () => {
  const h = harness();
  (()=>{h.data.events=[];h.data.notes=[];h.data.history=[];h.data.players=[];
    const E=(id,name)=>({id,members:[{pid:null,name}]});return h.data.tournament={id:'t1',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',
      entrants:[E('a','Ann'),E('b','Bea'),E('c','Cai'),E('d','Dee'),E('e','Eve'),E('f','Fay')],
      matches:[{id:'m1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[],sources:[]},
               {id:'m2',round:1,sides:['b',null],score:[0,0],status:'complete',result:'bye',winnerId:'b',absent:[],sources:[]},
               {id:'m3',round:1,sides:['c','d'],score:[3,1],status:'complete',result:'played',winnerId:'c',absent:[],sources:[]},
               {id:'m4',round:1,sides:['e','f'],score:[3,0],status:'complete',result:'played',winnerId:'e',absent:[],sources:[]},
               {id:'m5',round:2,sides:['a','b'],score:[0,0],status:'scheduled',absent:[],sources:['m1','m2']},
               {id:'m6',round:2,sides:['c','e'],score:[0,0],status:'scheduled',absent:[],sources:['m3','m4']}]}})();
  h.render=()=>{};
  for (const [lang, title, drawBtn, label] of [['en', 'Second chance', 'Draw a round-1 loser', 'Random draw, not a result'], ['zh', '复活赛', '抽取一名首轮负者', '随机抽签，不是赛果']]) {
    h.lang=(lang);
    const html = h.playScreen();
    assert.ok(html.includes(`>${title}<`) && html.includes(`>${drawBtn}<`), `${lang}: the draw is offered while round 2 is unsigned`);
    assert.ok(html.includes(label), `${lang}: it is labelled as a random draw`);
  }
  h.data.tournament.matches[3]={...h.data.tournament.matches[3],status:'scheduled',result:undefined,winnerId:null};
  assert.ok(!h.playScreen().includes('data-action="revival-draw"'), 'no draw until every round-1 loser is known');
  h.data.tournament.matches[3]={...h.data.tournament.matches[3],status:'complete',result:'played',winnerId:'e'};
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  const asked = [];
  h.context.confirm = msg => { asked.push(msg); return false; };
  h.lang='en';
  await click({action: 'revival-draw'});
  assert.equal(h.calls.length, 0, 'a cancelled confirm draws nothing');
  assert.equal(asked[0], 'Draw one round-1 loser at random to re-enter the bracket in a bye slot? The draw is recorded with its seed; no result changes.');
  h.context.confirm = msg => { asked.push(msg); return true; };
  await click({action: 'revival-draw'});
  // after the draw the card shows who, the pool and the seed, and offers undo
  (()=>{h.data.tournament.revival={seed:12345,pool:['d','f'],entrant:'f',name:'Fay',match:'m2',next:'m5',side:1,holder:'b',signed:2,drawnAt:'2026-09-26T20:00:00Z'};
    Object.assign(h.data.tournament.matches[1],{sides:['b','f'],status:'scheduled',winnerId:null});delete h.data.tournament.matches[1].result;return Object.assign(h.data.tournament.matches[4],{sides:['a',null],status:'pending'})})();
  h.lang='zh';
  const drawn = h.playScreen();
  assert.ok(drawn.includes('抽中：Fay') && drawn.includes('种子 12345') && drawn.includes('候选：Dee、Fay'), '中: who, the seed and the pool are shown');
  assert.ok(drawn.includes('data-action="revival-undo"'), 'undo is offered until the next result');
  assert.ok(!drawn.includes('data-action="revival-draw"'), 'one draw per event');
  await click({action: 'revival-undo'});
  assert.equal(asked.at(-1), '撤销这次复活抽签？该空位将恢复为轮空，签过的赛果不受影响。');
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name: 'revival_draw', payload: {confirm: true}}, {name: 'revival_undo', payload: {confirm: true}}]);
  // after a newer signed result, undo is gone and the drawn line stays as history
  h.data.tournament.matches[5]={...h.data.tournament.matches[5],status:'complete',result:'played',winnerId:'c',score:[3,2]};
  const closed = h.playScreen();
  assert.ok(!closed.includes('data-action="revival-undo"') && closed.includes('抽中：Fay'));
  for (const [action, en, zh] of [['revival_draw', 'Second chance drawn (random, audited)', '复活赛抽签（随机，已记录）'], ['revival_undo', 'Second chance undone', '撤销复活赛抽签']]) {
    h.lang='en'; assert.ok(h.auditLine({action:(action),createdAt:'2026-09-26T00:00:00Z',revision:1,context:{name:'Fay'}}).includes(en));
    h.lang='zh'; assert.ok(h.auditLine({action:(action),createdAt:'2026-09-26T00:00:00Z',revision:1,context:{name:'Fay'}}).includes(zh));
  }
  // Round 41: the service sends the Chinese sentence with the code.
  const byeSlotRow = refusalRow('No round-2 bye slot to fill');
  assert.equal(h.validationMessage('No round-2 bye slot to fill', byeSlotRow), byeSlotRow.zh);
});
test('doubles can pair solo sign-ups at random: seed shown, re-roll, accept (R3)', async () => {
  const h = harness();
  (()=>{h.data.events=[];h.data.notes=[];h.data.history=[];h.data.players=[{id:'pa',name:'Ada',status:'Active',rating:5}];return h.data.tournament={id:'t1',name:'Doubles night',format:'doubles',tables:1,raceTo:3,status:'registration',entrants:[],matches:[],
      pool:[{pid:'pa',name:'Ada'},{pid:null,name:'Bo'},{pid:null,name:'Cy'}],pairing:null}})();
  for (const [lang, title, add, draw, odd] of [['en', 'Random pairing', 'Add solo player', 'Pair at random', 'An even number of solo players is needed'], ['zh', '随机配对', '添加单人报名', '随机配对搭档', '需要偶数名单人报名者']]) {
    h.lang=(lang);
    const html = h.entrantsCard();
    assert.ok(html.includes(`>${title}<`) && html.includes(`>${add}<`), `${lang}: a doubles event offers a solo pool`);
    assert.ok(/<button[^>]*data-action="pair-draw"[^>]*disabled/.test(html) && html.includes(odd), `${lang}: an odd pool cannot be paired, and says why`);
    assert.ok(html.includes('Ada') && html.includes('Bo') && html.includes('Cy'));
    assert.ok(html.includes(`>${draw}<`));
  }
  h.data.tournament.format='singles';
  assert.ok(!h.entrantsCard().includes('id="solo-form"'), 'singles has no pairing step');
  (()=>{h.data.tournament.format='doubles';h.data.tournament.pool.push({pid:null,name:'Di'});return h.data.tournament.pairing={seed:424242,teams:[[{pid:null,name:'Cy'},{pid:'pa',name:'Ada'}],[{pid:null,name:'Di'},{pid:null,name:'Bo'}]]}})();
  for (const [lang, seed, accept, reroll, label] of [['en', 'seed 424242', 'Use these teams', 'Re-roll', 'Random draw of partners only; results are never drawn.'], ['zh', '种子 424242', '采用这些组合', '重新抽签', '只随机决定搭档，比赛结果从不抽签。']]) {
    h.lang=(lang);
    const html = h.entrantsCard();
    assert.ok(html.includes(seed) && html.includes(`>${accept}<`) && html.includes(`>${reroll}<`) && html.includes(label), `${lang}: the preview shows the seed, accept and re-roll`);
    assert.ok(html.includes('Cy / Ada') && html.includes('Di / Bo'), `${lang}: the teams are shown before they count`);
    assert.ok(!html.includes('id="entrant-form"'), `${lang}: registration is locked while a pairing is shown`);
  }
  h.render=()=>{};
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  await click({action: 'pair-draw'});
  await click({action: 'pair-accept', seed: '424242'});
  await click({action: 'pair-clear'});
  await click({action: 'pool-remove', name: 'Bo'});
  const submit = values => h.handlers.submit({preventDefault() {}, target: {getAttribute: () => 'solo-form', classList: {contains: () => false}, querySelector: () => ({setCustomValidity() {}, reportValidity() {}}), querySelectorAll: () => [], values}});
  await submit({solo_pid: '', solo_name: '  Eve '});
  await submit({solo_pid: 'pa', solo_name: ''});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [
    {name: 'pair_draw'}, {name: 'pair_accept', payload: {seed: 424242}}, {name: 'pair_clear'},
    {name: 'pool_remove', payload: {name: 'Bo'}}, {name: 'solo_add', payload: {member: {name: 'Eve'}}}, {name: 'solo_add', payload: {member: {pid: 'pa'}}}]);
  for (const [action, en, zh] of [['pair_draw', 'Partners drawn at random', '随机抽取搭档'], ['pair_accept', 'Random pairs registered', '随机组合已报名']]) {
    h.lang='en'; assert.ok(h.auditLine({action:(action),createdAt:'2026-09-26T00:00:00Z',revision:1,context:{seed:1}}).includes(en));
    h.lang='zh'; assert.ok(h.auditLine({action:(action),createdAt:'2026-09-26T00:00:00Z',revision:1,context:{seed:1}}).includes(zh));
  }
  // Round 41: the service sends the Chinese sentence with the code.
  const pairingRow = refusalRow('The pairing changed; review the teams again');
  assert.equal(h.validationMessage('The pairing changed; review the teams again', pairingRow), pairingRow.zh);
});
test('a redrawn second chance says so on the card, the sheet and the copied text (R6 follow-up)', async () => {
  const h = harness();
  (()=>{h.data.events=[];h.data.notes=[];h.data.history=[];h.data.players=[];
    const E=(id,name)=>({id,members:[{pid:null,name}]});return h.data.tournament={id:'t1',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',
      entrants:[E('a','Ann'),E('b','Bea'),E('c','Cai'),E('d','Dee'),E('e','Eve'),E('f','Fay')],
      matches:[{id:'m1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[],sources:[]},
               {id:'m2',round:1,sides:['b','f'],score:[0,0],status:'scheduled',absent:[],sources:[]},
               {id:'m3',round:1,sides:['c','d'],score:[3,1],status:'complete',result:'played',winnerId:'c',absent:[],sources:[]},
               {id:'m4',round:1,sides:['e','f'],score:[3,0],status:'complete',result:'played',winnerId:'e',absent:[],sources:[]},
               {id:'m5',round:2,sides:['a',null],score:[0,0],status:'pending',absent:[],sources:['m1','m2']},
               {id:'m6',round:2,sides:['c','e'],score:[0,0],status:'scheduled',absent:[],sources:['m3','m4']}],
      revival:{seed:777,pool:['d','f'],entrant:'f',name:'Fay',match:'m2',next:'m5',side:1,holder:'b',signed:2,drawnAt:'2026-09-26T20:00:00Z',attempt:1},revival_draws:1}})();
  h.lang='en';
  let card = h.revivalCard();
  assert.ok(card.includes('Draw 1') && !card.includes('Redrawn'), 'a first draw says draw 1 and nothing more');
  (()=>{h.data.tournament.revival.attempt=2;h.data.tournament.revival_draws=2;return h.data.tournament.revival.seed=888})();
  for (const [lang, n, note] of [['en', 'Draw 2', 'Redrawn after an undo — earlier draws are in the audit log'], ['zh', '第 2 次抽签', '撤销后重抽——之前的抽签记录在日志里']]) {
    h.lang=(lang);
    card = h.revivalCard();
    assert.ok(card.includes(n) && card.includes(note), `${lang}: the card shows ${n} and the redraw note`);
  }
  // an undone draw with no current pick still says the count, so the history is not lost
  h.lang='en';const r=h.data.tournament.revival;delete h.data.tournament.revival;
  assert.ok(h.revivalCard().includes('Draws so far: 2 — each one is in the audit log'), 'after an undo the card keeps the count');
  h.data.tournament.revival_draws=1;
  assert.ok(h.revivalCard().includes('Draws so far: 1 — each one is in the audit log'), 'one undone draw still shows');
  h.lang='zh';
  assert.ok(h.revivalCard().includes('已抽签 1 次——每次都记录在日志里'));
  (()=>{h.lang='en';return h.data.tournament.revival_draws=2})();
  h.data.tournament.revival=r;
  for (const [lang, line] of [['en', 'Second chance (random draw, not a result): Fay · seed 888 · draw 2'], ['zh', '复活赛（随机抽签，不是赛果）：Fay · 种子 888 · 第 2 次抽签']]) {
    h.lang=(lang);
    const text = h.resultsText(h.tournament());
    assert.ok(text.split('\n').includes(line), `${lang}: the copied text carries the second-chance line: ${line}`);
    const sheet = h.resultsSheet(h.tournament());
    assert.ok(sheet.includes(line), `${lang}: the sheet carries it too`);
  }
  (()=>{delete h.data.tournament.revival;return h.data.tournament.revival_draws=0})();
  assert.ok(!h.resultsText(h.tournament()).includes('Second chance'), 'no second chance, no line');
});
test('every table the operations screens add sits in a .table-wrap, so a wide table never widens the page', async () => {
  const h = harness();
  (()=>{h.data.events=[];h.data.notes=[];
    h.data.players=[{id:'pa',name:'Alexandria Montgomery-Smythe',status:'Active',rating:720},{id:'pb',name:'Bo',status:'Active',rating:650},{id:'pc',name:'Cy',status:'Active',rating:600}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    h.data.tournament={id:'t2',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',entrants:[E('a','pa','Alexandria Montgomery-Smythe'),E('b','pb','Bo')],
      matches:[{id:'x1',round:1,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',absent:[]}]};
    h.data.history=[{id:'t1',name:'Last week',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T12:00:00Z',entrants:[E('a1','pa','Alexandria Montgomery-Smythe'),E('c1','pc','Cy')],
      matches:[{id:'y1',round:1,sides:['a1','c1'],score:[1,3],status:'complete',result:'played',winnerId:'c1',absent:[]}]}];return h.render=()=>{}})();
  const bare = html => [...html.matchAll(/(.{0,40})<table\b[^>]*>/g)].filter(m => !m[1].endsWith('<div class="table-wrap">')).map(m => m[0].slice(-60));
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'player-record', id: 'pa'}}}});
  const screens = {play: h.playScreen(), records: h.recordsScreen(), record: h.playersScreen()};
  assert.ok(/data-vs-role="entrant-record"/.test(screens.play), 'the Play list carries each entrant\u2019s record on its row');
  assert.ok(/class="roster-summary"/.test(screens.record) && /class="standing-rating"/.test(screens.record), 'the Regulars standing renders');
  assert.ok(/class="h2h"/.test(screens.record) && /class="per-event"/.test(screens.record), 'the Player record tables render');
  for (const [name, html] of Object.entries(screens)) assert.deepEqual(bare(html), [], `${name}: no table outside a .table-wrap`);
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(/\.table-wrap\{[^}]*overflow:auto/.test(css), 'the wrapper scrolls, the page does not');
  // overflow alone is not enough in a grid: an auto track still sizes to the table's min-content
  assert.ok(/\.table-wrap\{[^}]*contain:inline-size/.test(css), 'the wrapper does not lend its table\'s width to the grid track');
  const rules = (css.match(/[^{}]+\{[^}]*\}/g) || []).map(r => ({selectors: r.slice(0, r.indexOf('{')).split(',').map(x => x.trim()), body: r.slice(r.indexOf('{'))}));
  // selectors contain commas inside :is(...), so match the rule's full selector text
  const nowrap = part => rules.some(r => r.body.includes('white-space:nowrap') && r.selectors.join(',').includes(part));
  for (const part of [':is(.standings,.event-table) td:nth-child(n+3)', ':is(.h2h,.per-event) td:nth-child(n+2)']) assert.ok(nowrap(part), `numbers such as 1–0 never break inside a cell: ${part}`);
  for (const part of [':is(.standings,.event-table) th:nth-child(n+3)', ':is(.h2h,.per-event) th:nth-child(n+2)']) assert.ok(!nowrap(part), `a long header such as House rating (manual) may wrap: ${part}`);
});
// ---- VOD selector: the Broadcasts block of the Source panel -------------------------------
function broadcastsHarness(lang = 'en') {
  const h = harness();
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  vm.runInContext(adapter, h.context, {filename:'vision-stage.js'});
  const vodRow = {id:'tw-1000000001-3600-3900', label:'examplechannel · 2026-09-26 · 1:00:00–1:05:00', kind:'vod', vod_id:'1000000001', channel:'examplechannel',
    title:'260918', created_at:'2026-09-26T06:46:33Z', range:{start_s:3600, end_s:3900, whole:false}, fps:30, frames:9002, width:1280, height:720, media:true};
  const snap = {live:{state:'idle', error:null, attempt:null, detectors:['table','person'], stages:[], skipped:0}, source:{kind:'vod', label:'x', channel:null},
    datasets:[{id:'vod30', label:'vod30'}, {id:'highlight', label:'highlight'}, vodRow], dataset:'vod30', frame:{count:9002, t:0, index:0}, detectors:{table:true, person:true, balls:false}};
  const calls = [];
  const replies = {
    '/api/vods/recent': {channels:[{channel:'examplechannel', error:null, vods:[{id:'1000000001', title:'260918', created_at:'2026-09-26T06:46:33Z', length_s:13397, imported:['tw-1000000001-3600-3900']}]}]},
    '/api/vods/job': {state:'running', id:'tw-1000000001-0-600', percent:42.5, mb:51.2, rate_mb_s:12.3, eta_s:95}};
  h.context.fetch = async (url, options) => { calls.push({url, body: options?.body ? JSON.parse(options.body) : null});
    const key = String(url).split('?')[0];
    if (key === '/api/vods/import' && calls.at(-1).body.vod === '1111111111') return {ok:false, status:400, json: async () => ({error:'This VOD belongs to someoneelse. Only saved channels can be analysed; add the channel under Source first.'})};
    // The estimate answers for the VOD it was asked about, as the server does.
    if (key === '/api/vods/estimate') { const vod = decodeURIComponent(String(url).split('vod=')[1] || ''); return {ok:true, status:200, json: async () => ({...replies[key], vod_id: vod})}; }
    return {ok:true, status:200, json: async () => replies[key] || {}}; };
  h.context.setInterval = () => 1; h.context.clearInterval = () => {};
  h.context.setTimeout = fn => { fn(); return 0; }; h.context.URLSearchParams = URLSearchParams;
  // The seam: the tests set the engine snapshot, render, and read the region the operator sees.
  const mount = stageMountStub();
  const seam = stageSeamStub(h, mount, {lang, attach: {channels: () => [{id:'c1', channel:'examplechannel', url:'https://www.twitch.tv/examplechannel'}], vods: () => []}});
  return {h, mount, seam, snap, calls, replies, vodRow};
}
const settle = () => new Promise(resolve => setImmediate(resolve));
test('Broadcasts lists each saved channel\'s recent VODs, the job progress and every existing Source control', async () => {
  const {seam, snap, calls} = broadcastsHarness();
  seam.panel(snap);                              // the first render asks the server
  await settle(); await settle();
  const html = seam.panel(snap);
  assert.ok(calls.some(c => c.url === '/api/vods/recent'), 'recent broadcasts are fetched');
  assert.match(html, /<h4>Broadcasts<\/h4>/);
  assert.match(html, /examplechannel · 2026-09-26 · 3:43:17 · 260918 · imported 1/, 'title, date, duration and imported state');
  assert.match(html, /data-vs-action="bc-open" data-vs-value="1000000001" aria-label="Import… examplechannel 260918"/);
  assert.match(html, /data-vs-field="bc-paste"/, 'a paste box for a link or id');
  assert.match(html, /42\.5% · 51\.2 MB · 12\.3 MB\/s · 1 min 35 s left/, 'real progress: percent, MB, rate, ETA');
  assert.match(html, /<progress max="100" value="42.5"/);
  assert.match(html, /data-vs-action="bc-cancel"/);
  assert.match(html, /data-vs-bc-dataset="tw-1000000001-3600-3900"[\s\S]*data-vs-action="bc-delete"/, 'an imported VOD can be deleted');
  // nothing that was there before is gone
  for (const kept of ['data-vs-action="pick-replay"', 'data-vs-action="live-start"', 'data-vs-action="live-stop"', 'data-vs-action="open-sources"', 'data-vs-action="pick-dataset" data-vs-value="vod30"', 'data-vs-action="pick-dataset" data-vs-value="highlight"'])
    assert.ok(html.includes(kept), `kept: ${kept}`);
  assert.ok(html.includes('data-vs-action="pick-dataset" data-vs-value="tw-1000000001-3600-3900"'), 'the imported VOD is a dataset chip');
});
test('Import takes the whole broadcast, shows the estimated size before confirming, and maps the other-channel refusal to 中文', async () => {
  const {seam, snap, calls, replies} = broadcastsHarness('zh');
  replies['/api/vods/estimate'] = {id:'tw-1000000001', vod_id:'1000000001', channel:'examplechannel', range:{start_s:0, end_s:13397, whole:true},
    estimate_bytes:5505302893, disk:{ok:true, free_bytes:52196323328, needed_bytes:8606363471, refusal:null}, already_imported:false, eta_s:442};
  seam.panel(snap);                              // the block reads the saved list before an open
  await settle(); await settle();
  seam.click('bc-open', '1000000001');
  await settle(); await settle();
  assert.ok(calls.some(c => c.url === '/api/vods/estimate?vod=1000000001'), 'round 10, item 3: the estimate is for the whole broadcast, with no bounds to send');
  const html = seam.panel(snap);
  assert.match(html, /examplechannel · 整场回放 · 约 5\.5 GB, 约 7 min 22 s · 52\.2 GB 可用/, 'size and time before committing');
  assert.match(html, /data-vs-action="bc-import"[^>]*>导入 · 5\.5 GB</);
  assert.ok(!/data-vs-field="bc-start"|data-vs-field="bc-minutes"/.test(html), 'round 10, item 3: no start and no length to type');
  // Another channel's broadcast is refused, and the console states the refusal in 中文.
  seam.click('bc-open', '1111111111');
  await settle(); await settle();
  seam.click('bc-import', '');
  await settle(); await settle();
  assert.deepEqual(calls.filter(c => c.url === '/api/vods/import').map(c => c.body), [{vod:'1111111111'}], 'the whole broadcast, and nothing that bounds it');
  assert.match(seam.panel(snap), /role="alert">此回放属于 someoneelse。只能分析已保存的频道；请先在“来源”中添加该频道。/);
});
test('an imported VOD reads as a recorded broadcast in broadcast time, and its empty rail says why', async () => {
  const {h, seam, snap, vodRow} = broadcastsHarness();
  const on = {...snap, dataset: vodRow.id, frame: {count:9002, t:144.03, index:4321}, eventsAnalysed: false};
  // The chip row states the source in words: that is where the recorded label lands.
  const freshness = state => { seam.show(state); return (/<span class="vs-fresh[^"]*">([^<]*)<\/span>/.exec(seam.html('#vs-chips')) || [])[1]; };
  assert.equal(freshness(on), 'recorded broadcast of examplechannel · from 2026-09-26 · 1:00:00–1:05:00');
  assert.ok(!/live/i.test(freshness(on)), 'never "live"');
  const facts = seam.show({...on, loading: {overlay: false, since: 0}, busy: false, live: {stale: false},
    drawn: {cloth: 1, balls: 1, persons: 2, pockets: 6, anchors: 0, events: 0, auto: {cloth: 1, balls: 1, persons: 2, pockets: 6, anchors: 0, events: 0}}}).text('#vs-facts');
  assert.ok(facts.includes('broadcast time 1:02:24'), `broadcast time = range start + t: ${facts}`);
  const rail = seam.show({...on, events: {items: [], index: 0, reviewed: 0}, eventFilter: 'all', selection: {}, balls: {items: [], index: 0}, persons: {tracks: [], windows: [], win: ''}, focus: 'events'}).html('#vs-cues');
  assert.match(rail, /data-vs-empty="not-scanned">Not scanned for events — browse frames and run inference on a frozen frame\./);
  assert.equal(freshness(snap), 'x', 'vod30 keeps its own label');
  // A server sentence the console cannot translate reaches the operator unchanged.
  h.context.fetch = async url => String(url).includes('/api/vods/estimate')
    ? {ok:false, status:400, json: async () => ({error:'some other sentence'})}
    : {ok:true, status:200, json: async () => ({})};
  seam.click('bc-open', '1000000001');
  await settle(); await settle();
  assert.match(seam.panel(snap), /role="alert">some other sentence</, 'an unmapped server sentence is shown as it arrives');
});test('Refresh list also re-reads the import job, so an import started in another tab shows its progress', async () => {
  const {seam, snap, calls} = broadcastsHarness();
  seam.panel(snap);
  await settle(); await settle();
  calls.length = 0;
  seam.click('bc-refresh', '');
  await settle(); await settle();
  assert.ok(calls.some(c => c.url === '/api/vods/recent') && calls.some(c => c.url === '/api/vods/job'));
  assert.match(seam.panel(snap), /data-vs-bc-job="running"/, 'the job row states the state the server reported');
});
// ---- IA C′ stage 2: hash routes. The URL names the screen; back/forward walk it; old ids map onto it.
test('routes: every tab has a hash route, a tab click pushes it, and back/forward walk the screens', async () => {
  const h = harness();
  h.render=()=>{};
  assert.equal(h.context.location.hash, '#/tonight', 'a cold load names its screen without adding a history entry');
  assert.deepEqual(h.visits, [['replace', '#/tonight']]);
  const expected = {records: '#/records', vision: '#/vision', players: '#/regulars', status: '#/backroom'};
  for (const [id, hash] of Object.entries(expected)) {
    await tabClick(h, id);
    assert.equal(h.tab, id);
    assert.equal(h.context.location.hash, hash, `${id} is ${hash}`);
  }
  assert.equal(h.visits.filter(v => v[0] === 'push').length, 4, 'each tab change is one history entry');
  await tabClick(h, 'status');
  assert.equal(h.visits.filter(v => v[0] === 'push').length, 4, 'the same tab again adds no entry');
  browserBack(h, '#/regulars');
  assert.equal(h.tab, 'players', 'Back returns to Regulars');
  browserBack(h, '#/setup');
  assert.equal(h.tab, 'tonight', 'the old Set up hash opens Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'and folds in place onto the one Tonight route');
  browserBack(h, '#/backroom');
  assert.equal(h.tab, 'status', 'Forward works the same way');
  browserBack(h, '#/floor');
  assert.equal(h.tab, 'tonight', 'the retired Floor hash opens Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'and folds into the one Tonight route');
  browserBack(h, '#/matches');
  assert.equal(h.tab, 'tonight', 'so does the retired Matches hash');
  assert.equal(h.context.location.hash, '#/tonight');
  assert.equal(h.visits.filter(v => v[0] === 'push').length, 4, 'no retired hash ever pushes: every fold is a replace');
});
test('routes: a URL opens its screen; old tab ids and old hashes map onto the routes; unknown ones fall back', () => {
  const cases = [['#/regulars', 'players', '#/regulars'], ['#/backroom', 'status', '#/backroom'], ['#/vision', 'vision', '#/vision'],
    ['#players', 'players', '#/regulars'], ['#/status', 'status', '#/backroom'], ['#setup', 'tonight', '#/tonight'],
    ['#/floor', 'tonight', '#/tonight'], ['#/matches', 'tonight', '#/tonight'],
    ['#/tonight/register', 'tonight', '#/tonight'], ['#/tonight/rack', 'tonight', '#/tonight'],
    ['#/tonight/play', 'tonight', '#/tonight'], ['#/tonight/close', 'tonight', '#/tonight'],
    ['#/nowhere', 'tonight', '#/tonight'], ['', 'tonight', '#/tonight'], ['#', 'tonight', '#/tonight']];
  for (const [hash, tab, canonical] of cases) {
    const h = harness({hash});
    assert.equal(h.tab, tab, `${hash || '(none)'} opens ${tab}`);
    assert.equal(h.context.location.hash, canonical, `${hash || '(none)'} is rewritten in place to ${canonical}`);
    assert.ok(h.visits.every(v => v[0] === 'replace'), 'loading never adds a history entry');
  }
  // a typed or old-style hash while running is the same as a click
  const h = harness();
  h.render=()=>{};
  browserBack(h, '#players');
  assert.equal(h.tab, 'players');
  assert.equal(h.context.location.hash, '#/regulars');
  // in-app links that still carry an old id (empty states, the first-night guide) resolve the same way
  assert.equal(h.routeOf('setup'), 'tonight', 'the retired Set up id is a legacy route, not a screen');
  assert.equal(h.routeOf('floor'), 'tonight', 'so is Floor');
  assert.equal(h.routeOf('matches'), 'tonight', 'and Matches');
  assert.equal(h.routeOf('regulars'), 'players');
  assert.equal(h.routeOf('nope'), null);
});
test('routes: a dirty or busy review vetoes back/forward too, and the URL is put back', () => {
  const h = harness({hash: '#/vision'});
  h.render=()=>{};
  h.context.window.CornerPocketReview = {canLeave: () => false, activate: () => false};
  browserBack(h, '#/records');
  assert.equal(h.tab, 'vision', 'the review keeps its screen');
  assert.equal(h.context.location.hash, '#/vision', 'the address bar says so');
  h.context.window.CornerPocketReview = {canLeave: () => true, activate: () => false};
  h.busy=true;
  browserBack(h, '#/records');
  assert.equal(h.tab, 'vision', 'a write in flight also holds the screen');
  h.busy=false;
  browserBack(h, '#/records');
  assert.equal(h.tab, 'records');
});
test('routes: a veto on the way out of a review keeps the review and its address', () => {
  const h = harness({hash: '#/records/review/n1'});
  h.render=()=>{};
  h.context.window.CornerPocketReview = {canLeave: () => false, activate: () => false};
  browserBack(h, '#/records');
  assert.equal(h.reviewId, 'n1', 'the workbench keeps its broadcast');
  assert.equal(h.context.location.hash, '#/records/review/n1', 'the address bar says so');
  h.context.window.CornerPocketReview = {canLeave: () => true, activate: () => false};
  browserBack(h, '#/records');
  assert.equal(h.reviewId, null, 'with no veto the review closes');
  assert.equal(h.context.location.hash, '#/records');
});
// ---- IA C′ stage 3: Records holds the history half of Matches (house standings, night log, archived events).
function recordsNight(h) {
  (()=>{h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:100},{id:'pb',name:'Bea',status:'Active',rating:900}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    h.data.tournament={id:'t0',name:'Tonight',format:'singles',raceTo:3,tables:2,status:'active',entrants:[E('a','pa','Ann'),E('b','pb','Bea')],
      matches:[{id:'m1',round:1,sides:['a','b'],score:[1,0],status:'live',table:1,absent:[]}]};
    h.data.history=[{id:'h1',name:'Last week',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T00:00:00Z',entrants:[E('a1','pa','Ann'),E('b1','pb','Bea')],
      matches:[{id:'y1',round:1,sides:['a1','b1'],score:[1,3],status:'complete',result:'played',winnerId:'b1',absent:[]}]},
      {id:'h2',name:'Hidden night',hidden:true,format:'singles',raceTo:3,status:'complete',archivedAt:'2026-08-25T00:00:00Z',entrants:[E('a2','pa','Ann'),E('b2','pb','Bea')],
      matches:[{id:'y2',round:1,sides:['a2','b2'],score:[3,0],status:'complete',result:'played',winnerId:'a2',absent:[]}]}];
    h.data.events=[{id:'e1',action:'match_complete',revision:7,at:'2026-09-01T21:00:00Z',context:{id:'y1'}}];return h.data.notes=[]})();
}
test('Records is a top-level tab with its own route, between the live night and Vision', async () => {
  const h = harness({hash: '#/records'});
  assert.equal(h.tab, 'records', 'the URL opens Records');
  assert.equal(h.context.location.hash, '#/records');
  assert.deepEqual(JSON.parse(JSON.stringify(h.navTabs)).slice(0, 5), ['tonight', 'records', 'vision', 'players', 'status'], 'Records sits after the live night, before Vision');
  for (const [lang, label] of [['en', 'History'], ['zh', '历史赛事']]) { h.lang=(lang); assert.equal(h.t('records'), label); }
  h.render=()=>{};
  await tabClick(h, 'tonight');
  await tabClick(h, 'records');
  assert.equal(h.context.location.hash, '#/records', 'a click pushes the route');
  assert.equal(h.routeOf('records'), 'records');
});
test('Records is the event timeline; the house standing lives on every Regulars row', () => {
  const h = harness();
  recordsNight(h);
  for (const lang of ['en', 'zh']) {
    (()=>{h.lang=(lang);return h.showHidden=false})();
    const rec = h.recordsScreen(), play = h.playScreen(), regs = h.playersScreen();
    const heading = h.t('records');
    assert.ok(rec.includes(`>${heading}</h2>`), `${lang}: History is the events timeline (round 13, owner item 2)`);
    for (const key of ['standings', 'timeline', 'history']) {
      const gone = h.t((key));
      assert.ok(!rec.includes(`>${gone}</h2>`) && !rec.includes(`>${gone}</h3>`), `${lang}: Records no longer carries ${gone}`);
    }
    assert.ok(!play.includes(`>${heading}</h2>`), `${lang}: Play keeps tonight only`);
    assert.ok(rec.includes('<div class="events"') && rec.includes('class="tl-item"'), `${lang}: the timeline is a list of nights`);
    assert.ok(rec.includes('data-action="results-sheet" data-id="h1"') && rec.includes('data-action="rename-archived" data-id="h1"') && rec.includes('data-action="event-hide" data-id="h1"'), `${lang}: every archive control stays`);
    assert.ok(!rec.includes('Hidden night') && rec.includes('data-action="toggle-hidden"'), `${lang}: hidden nights stay hidden behind the toggle`);
    assert.ok(regs.includes('class="roster-summary"') && regs.includes('class="standing-rating"'), `${lang}: the house standing is on Regulars`);
    assert.ok(play.includes('data-vs-role="entrant-record"'), `${lang}: tonight's record stays with the entrant it belongs to`);
    assert.ok(play.includes('class="rounds"'), `${lang}: the bracket stays`);
  }
  h.showHidden=true;
  assert.ok(h.recordsScreen().includes('Hidden night'), 'the toggle shows hidden nights in Records');
});
test('a Regulars standing row opens that regular, and the record behind it is read-only', async () => {
  const h = harness();
  recordsNight(h);
  h.render=()=>{};
  const regs = h.playersScreen();
  assert.ok(regs.includes('data-action="select-player" data-id="pb"'), 'each standing row lists that regular');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'select-player', id: 'pb'}}}});
  const own = h.playersScreen();
  assert.ok(own.includes('data-action="player-record" data-id="pb"'), 'that regular\'s own view offers the read-only record');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'player-record', id: 'pb'}}}});
  const open = h.playersScreen();
  assert.ok(/class="modal"[^]*Player record · Bea/.test(open), 'the record opens over Regulars');
  assert.ok(!open.includes('data-action="player-delete"') && !open.includes('player-form'), 'read-only: no edit or delete controls');
  assert.ok(open.includes('data-action="close-modal"'), 'it closes');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'close-modal'}}}});
  assert.ok(!h.playersScreen().includes('class="modal"'), 'closed');
  assert.equal(h.calls.length, 0, 'reading a record never writes');
});
test('Records empty states say what fills the timeline, in EN and 中, with no fake rows', () => {
  const h = harness();
  (()=>{h.data.players=[];h.data.history=[];h.data.events=[];return h.data.tournament={id:'t1',name:'',format:'singles',raceTo:1,status:'registration',entrants:[],matches:[]}})();
  for (const lang of ['en', 'zh']) {
    h.lang=(lang);
    const rec = h.recordsScreen();
    assert.ok(rec.includes(h.esc(h.t('emptyHistory'))), `${lang}: emptyHistory`);
    assert.ok(!/<tr><td>\d/.test(rec) && !/<li[ >]/.test(rec), `${lang}: no rows on an empty club`);
    assert.ok(rec.includes('data-action="backfill-open"'), `${lang}: the empty timeline offers the backfill`);
    const regs = h.playersScreen();
    assert.ok(regs.includes(h.esc(h.t('emptyRoster'))), `${lang}: the standing says what fills it`);
    assert.ok(regs.includes('data-action="open-add-player"'), `${lang}: and it opens the new-regular form`);
    assert.ok(!regs.includes('standing-cell'), `${lang}: no fake standing rows`);
  }
  (()=>{h.lang='en';return h.data.history=[{id:'h1',name:'Night',hidden:true,status:'complete',archivedAt:'2026-09-01T00:00:00Z',entrants:[],matches:[]}]})();
  const hidden = h.recordsScreen();
  assert.ok(hidden.includes(h.esc(h.t('allHidden')).replace('{n}', 1)), 'an all-hidden club says so instead of "nothing here yet"');
  assert.ok(hidden.includes('data-action="toggle-hidden"'), 'and offers the toggle');
  assert.ok(!hidden.includes(h.esc(h.t('emptyHistory'))), 'the empty note is gone once a night exists');
});
const standingRow = (standing, name) => {
  const at = standing.indexOf(`>${name}<`);
  assert.ok(at > 0, `the standing lists ${name}`);
  return standing.slice(at, standing.indexOf('</button>', at));
};
// Round 9 (owner item 9): a row is two lines - the name with its record, and the
// rating with its own label. There are no per-column cells to read any more, so
// the helper derives played / W-L / win % from the record line, and '—' from the
// no-record line, which is what the row actually says.
const standingCell = (h, standing, name, col) => {
  const row = standingRow(standing, name);
  const rec = (row.match(/class="standing-record">([^<]*)</) || [])[1] || '';
  const rating = (row.match(/class="standing-rating"><strong>([^<]*)</) || [])[1] || '';
  const playedLabel = h.t('played');
  const none = rec.startsWith(playedLabel + ' ');
  const wl = (rec.match(/([0-9]+\u2013[0-9]+)/) || [])[1];
  const pct = (rec.match(/([0-9]+%)/) || [])[1];
  const base = {[playedLabel]: none ? rec.slice(playedLabel.length + 1).split(' ')[0] : String(Number((wl || '0\u20130').split('\u2013')[0]) + Number((wl || '0\u20130').split('\u2013')[1])),
                [h.t('wl')]: none ? '\u2014' : wl,
                [h.t('winPct')]: none ? '\u2014' : pct,
                [h.t('rating')]: rating};
  assert.ok(col in base, `${name}: ${col} is a column on the row`);
  return base[col];
};
const commitDisabled = html => {
  const at = html.indexOf('data-action="bf-commit"');
  assert.ok(at > 0, 'the commit control is on the page');
  const tag = html.slice(html.lastIndexOf('<button', at), html.indexOf('>', at));
  return /\bdisabled\b/.test(tag);
};
test('a regular who has never played reads 0 played and —, never 0%, and the row says so (6.2)', () => {
  const h = harness();
  recordsNight(h);
  h.data.players.push({id:'pz',name:'Zed',status:'Active',rating:300,joinedAt:'2026-01-05T00:00:00Z'});
  const standing = h.playersScreen();
  assert.ok(/class="standing[^"]*no-record"/.test(standing), 'the row admits it holds no record');
  assert.equal(standingCell(h, standing, 'Zed', h.t('played')), '0');
  assert.equal(standingCell(h, standing, 'Zed', h.t('wl')), '\u2014');
  assert.equal(standingCell(h, standing, 'Zed', h.t('winPct')), '\u2014');
  assert.ok(!standing.includes('>0%<'), 'nobody reads 0% for a match they never played');
  assert.ok(standing.includes(h.esc(h.t('noRecord'))), 'and the empty cell is the — the words file holds');
  assert.ok(!standing.includes('signedOnly') && h.t('signedOnly') === 'signedOnly',
    'owner item 5: the standing no longer explains a rule nobody asked about, and the key is retired');
});
test('the timeline groups nights by month, newest first, and a night opens in place (5.3/5.4)', () => {
  const h = harness();
  (()=>{h.render=()=>{};h.lang='en';h.showHidden=false;h.openEvents.clear();
    h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:900,joinedAt:'2026-01-01T00:00:00Z'},{id:'pb',name:'Bea',status:'Active',rating:800,joinedAt:'2026-01-01T00:00:00Z'}];
    const mk=(id,name,archivedAt,hidden)=>({id,name,format:'singles',raceTo:7,tables:4,status:'complete',archivedAt,hidden:!!hidden,
      source:{kind:'vod-backfill',vodId:'1234567890',datasetId:'tw-1234567890-452-1690',startS:452,endS:1690,channel:'examplechannel',title:'Monday night',humanReviewed:true},
      signOff:{at:'2026-09-21T03:15:00Z'},
      entrants:[{id:id+'a',members:[{pid:'pa',name:'Ann'}]},{id:id+'b',members:[{pid:null,name:'Guest'}]}],
      matches:[{id:id+'m',round:1,sides:[id+'a',id+'b'],score:[3,1],status:'complete',result:'played',winnerId:id+'a',absent:[]}]});
    h.data.history=[mk('n1','September night','2026-09-20T12:00:00Z'),mk('n2','August night','2026-08-20T12:00:00Z'),mk('n3','July night','2026-07-20T12:00:00Z'),mk('n4','Last year','2025-12-30T12:00:00Z'),mk('h9','Hidden night','2026-06-20T12:00:00Z',true)];return h.data.events=[{action:'event_backfill',createdAt:'2026-09-21T00:00:00Z',revision:9,context:{id:'n1',name:'September night',vodId:'1234567890',datasetId:'tw-1234567890-452-1690'}}]})();
  const html = h.recordsScreen();
  assert.deepEqual([...html.matchAll(/data-event="([^"]+)"/g)].map(m => m[1]), ['n1', 'n2', 'n3', 'n4'], 'newest first, and a hidden night stays out until asked for');
  assert.deepEqual([...html.matchAll(/class="tl-year">([^<]*)</g)].map(m => m[1]), ['2026', '2025'], 'one year head per year, not per night');
  const months = [...html.matchAll(/class="tl-month-head">([^<]*)</g)].map(m => m[1]);
  assert.equal(months.length, 4, 'one month head per month');
  assert.deepEqual(months, ['2026-09-20', '2026-08-20', '2026-07-20', '2025-12-30'].map(day => h.monthLabel(new Date(''+(day)+'T12:00:00Z'))), 'and the months read in order');
  assert.deepEqual(months, ['September', 'August', 'July', 'December'], 'in EN the month head is the English month alone (round 2, B-03)');
  assert.ok(/<h3 class="tl-year">2026<\/h3>/.test(html) && /<h3 class="tl-month-head">September<\/h3>/.test(html),
    'the year and the month are heading levels, so Records can be navigated by heading (round 2, B-13)');
  const zhMonth = (()=>{h.lang='zh';return h.monthLabel(new Date('2026-09-20T12:00:00Z'))})();
  assert.equal(zhMonth, '九月', 'in 中 the month head is 中文 alone, never 中文 plus English (round 3, F11)');
  assert.ok(!/[A-Za-z]/.test(zhMonth), 'round 3 / F11: one language per label, so no Latin month rides along');
  h.lang='en';
  assert.ok(html.includes('id="tl-body-n1" hidden') && !html.includes('aria-expanded="true"'), 'a night starts folded');
  assert.ok(html.includes(h.esc(h.t('signedLine').replace('{n}',1))), 'the row counts signed results');
  assert.ok(html.includes(h.esc(h.t('backfill'))), 'and it is marked as a backfilled night');
  h.openEvents.add('n1');
  const open = h.recordsScreen();
  assert.ok(open.includes('id="tl-body-n1">') && !open.includes('id="tl-body-n1" hidden'), 'opening one night does not leave it');
  assert.ok(open.includes('aria-expanded="true"') && open.includes(h.esc(h.t('tlCollapse'))), 'the toggle flips');
  const body = open.slice(open.indexOf('id="tl-body-n1"'), open.indexOf('data-event="n2"'));
  assert.ok(body.includes(h.esc(h.t('resultsSheet'))) && body.includes(h.esc(h.t('renameEvent'))) && body.includes(h.esc(h.t('hideEvent'))), 'the sheet, the rename and the hide are in the body');
  assert.ok(!body.includes(h.esc(h.t('deleteEvent'))), 'a night with a signed result is never deletable');
  assert.ok(body.includes('<span class="tl-round">Round 1</span><span class="tl-pair">Ann — Guest</span><span class="tl-score">3–1</span>'),
    'round 3 / F13: a match row is a round column, a pair column and a score column, in that order');
  assert.ok(/<span class="tl-score">3–1<\/span><span class="badge /.test(body), 'round 3 / F13: the status badge is the row\'s last cell, so the columns can line up');
  assert.ok(body.includes('href="https://www.twitch.tv/videos/1234567890"'), 'the source row links to the broadcast the night was typed from');
  assert.ok(body.includes(`<summary>${h.esc(h.t('auditTrail'))} (1)</summary>`), 'and the night carries its own audit fold');
  h.showHidden=true;
  const all = h.recordsScreen();
  assert.ok(all.includes('data-event="h9"') && all.includes('tl-item is-hidden'), 'the hidden night shows up as hidden, and is still there');
});
test('round 10 / owner item 3: the backfill import posts the broadcast, never a range', () => {
  assert.ok(/fetch\('\/api\/vods\/import'[^;]*body:JSON\.stringify\(\{vod:bf\.vod\.id\}\)/.test(source), 'the download request carries the broadcast id alone');
  assert.ok(!/import'[^;]*start_s/.test(source), 'with no start and no duration left in it');
  assert.ok(/fetch\(`\/api\/vods\/estimate\?vod=\$\{encodeURIComponent\(id\)\}`/.test(source), 'and the estimate asks the same question the download will');
  assert.ok(!/bf\.startText|bf\.lengthText|id="bf-start"|id="bf-length"/.test(source), 'the fields that asked for the bounds are gone, not hidden');
});
test('the backfill is three human screens, and the page never pretends to detect anything (7.1)', () => {
  const h = harness();
  h.BF_SCREENS===3||(()=>{throw new Error("three screens")})();
  const groups = JSON.parse(JSON.stringify(h.BF_STEPS));
  assert.equal(groups.pick, 1, 'choosing a broadcast is screen 1');
  assert.equal(groups.verify, 1, 'and verifying it is the same screen');
  assert.equal(groups.importing, 2, 'importing is screen 2');
  assert.deepEqual([groups.dataset, groups.marking], [2, 2], 'with the night fields and the marking canvas on it');
  assert.equal(groups.review, 3, 'confirming is screen 3');
  assert.equal(groups.done, 3, 'and a finished night is a banner on it');
  assert.deepEqual([groups.failed, groups.rejected], [1, 1], 'a failure sends the operator back to the choice, as a banner');
  for (const step of ['pick', 'verify', 'importing', 'dataset', 'marking', 'review', 'done', 'failed', 'rejected']) {
    h.bf={step:(step)};
    const html = h.bfScreen();
    assert.ok(/data-vs-role="bf-step">[^<]*\d\/3</.test(html), `${step}: the header counts three screens, not eight`);
    assert.ok(!/>bf[A-Z]/.test(html), `${step}: no raw word key renders`);
  }
  h.bf={step:'done'};
  assert.ok(/class="bf-banner done"/.test(h.bfScreen()), 'done is a banner, not a page of its own');
  h.bf={step:'failed',detail:'the disk is full'};
  const failed = h.bfScreen();
  assert.ok(/class="bf-banner err"/.test(failed) && failed.includes('the disk is full'), 'and a failure says why, on the screen it happened on');
  h.bf={step:'importing',job:{percent:42,rate_mb_s:3.1,eta_s:95},vod:{title:'261001'}};
  const line = h.bfProgressLine();
  assert.ok(line.includes('42%') && line.includes('3.1 MB/s') && line.includes('261001'), 'the one progress line carries the numbers and the name');
  assert.ok(h.bfProgressLine().includes('data-ingest="backfill"'), 'under a stable hook, so History can render it too');
});
test('a backfilled night cannot be committed without a person confirming every row, and the payload says so (7.0/7.5)', async () => {
  const h = harness();
  (()=>{h.render=()=>{};h.lang='en';h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:900,joinedAt:'2026-01-01T00:00:00Z'}];
    h.bf=h.bfFresh();h.bf.vod={id:'1234567890',channel:'examplechannel',title:'Monday night',length_s:7200};h.bf.datasetId='tw-1234567890-452-1690';h.bf.datasetTitle='Monday night';h.bf.startS=452;h.bf.endS=1690;
    h.bfStartMarking();h.bf.clock=452;h.bfMarkStart();h.bf.clock=780;h.bfMarkEnd();h.bf.clock=1690;h.bfMarkStart();h.bf.clock=2000;h.bfMarkEnd();h.bfToReview();
    h.bf.draft[0].sides=['Ann','Guest'];h.bf.draft[0].winner='Ann';h.bf.draft[0].score=[3,1];
    h.bf.draft[1].sides=['Ann','Guest'];h.bf.draft[1].winner='Guest';return h.bf.draft[1].score=[2,3]})();
  h.context.sent = [];
  h.context.fetch = async (url, options) => { h.context.sent.push({url, payload: JSON.parse(options.body)}); return {status: 200, ok: true, json: async () => Object.assign({},h.data,{revision:h.data.revision+1,history:[{id:'h9',name:'Monday night',source:{datasetId:'tw-1234567890-452-1690'}}]})}; };
  await h.bfCommit();
  assert.equal(h.context.sent.length, 0, 'nothing is written while a row is unconfirmed');
  assert.equal(h.bf.notice, h.t('bfUnconfirmed').replace('{n}',2));
  assert.ok(commitDisabled(h.bfScreen()), 'and the commit control is disabled, not just discouraged');
  (()=>{h.bfConfirm(0);return h.bfConfirm(1)})();
  assert.equal(h.bf.draft.filter(m=>!m.confirmed).length, 0);
  assert.ok(!commitDisabled(h.bfScreen()), 'confirmed rows enable the commit');
  const revision = h.data.revision;
  await h.bfCommit();
  assert.equal(h.context.sent.length, 1, 'one confirmed night, one write');
  const sent = h.context.sent[0];
  assert.equal(sent.url, '/api/operations');
  assert.equal(sent.payload.action, 'event_backfill');
  assert.equal(sent.payload.revision, revision, 'the write carries the revision it was read at');
  assert.equal(h.data.revision, revision + 1, 'and the console adopts the state the server answered with');
  assert.equal(sent.payload.source.kind, 'vod-backfill');
  assert.equal(sent.payload.source.humanReviewed, true, 'the server enforces this mark; the disabled button is not enough');
  assert.equal(sent.payload.source.datasetId, 'tw-1234567890-452-1690');
  assert.deepEqual(sent.payload.event.entrants, [{pid: 'pa', name: 'Ann'}, {name: 'Guest'}], 'a typed regular is written as their roster row, a guest as a name');
  assert.deepEqual(sent.payload.event.matches, [
    {round: 1, sides: ['Ann', 'Guest'], score: [3, 1], winner: 'Ann', result: 'played', clip: [452, 780]},
    {round: 1, sides: ['Ann', 'Guest'], score: [2, 3], winner: 'Guest', result: 'played', clip: [1690, 2000]}
  ], 'the clip boundaries the operator marked, and no invented result');
  assert.equal(h.bf.step, 'done', 'the night is written and the flow ends');
  assert.ok(h.bfScreen().includes('data-action="bf-open-timeline"'));
  // the same range cannot be written twice: the server refuses and the console offers the night instead
  (()=>{h.bf=h.bfFresh();h.bf.vod={id:'1234567890',channel:'examplechannel',title:'Monday night',length_s:7200};h.bf.datasetId='tw-1234567890-452-1690';h.bf.datasetTitle='Monday night';h.bf.startS=452;h.bf.endS=1690;
    h.bfStartMarking();h.bf.clock=452;h.bfMarkStart();h.bf.clock=780;h.bfMarkEnd();h.bfToReview();h.bf.draft[0].sides=['Ann','Guest'];h.bf.draft[0].winner='Ann';h.bf.draft[0].score=[3,1];return h.bfConfirm(0)})();
  // An older server names the night in the sentence only: the body carries no nightId key.
  h.context.fetch = async () => ({status: 409, ok: false, json: async () => ({error: 'tw-1234567890-452-1690 is already in the timeline as "Monday night" (h9); open it instead'})});
  await h.bfCommit();
  assert.equal(h.bf.notice, h.t('bfSameVod'));
  assert.equal(h.bf.nightId, 'h9', 'a server that names the night in words only is still read');
  assert.ok(h.bfScreen().includes('data-action="bf-open-night"'), 'a 409 offers the night that already exists instead of overwriting it');
  assert.equal(h.bf.draft.length, 1, 'and it keeps the marks');
});
// Round 34 card 11: the 409 carries the night identity as data. The console reads that key and
// never reads an id out of the sentence, so a reworded sentence cannot misdirect it.
function bfReview(overrides = {}) {
  const h = harness();
  h.render = () => {};
  h.lang = 'en';
  h.openEvents.clear();
  h.bf = h.bfFresh();
  Object.assign(h.bf, {step: 'review', datasetId: 'tw-1234567890-452-1690', startS: 452, endS: 1690,
    datasetTitle: 'Monday night', vod: {id: '1234567890', channel: 'examplechannel', title: 'Monday night', length_s: 7200},
    night: {name: 'Night (2)', format: 'singles', raceTo: 7, tables: 4},
    draft: [{start: 452, end: 780, sides: ['Ann', 'Rico'], winner: 'Ann', score: [3, 1], confirmed: true}]},
    overrides);
  return h;
}
function bfRefuse(h, body) {
  h.context.fetch = async (url, options) => (options && options.method === 'POST')
    ? {status: 409, ok: false, json: async () => body}
    : {status: 200, ok: true, json: async () => h.data};
}
const bfClick = (h, action) => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action}}}});
// The action table starts bfOpenNight and returns at once. The click therefore resolves before the
// night opens. Give the console one macrotask to finish the reload and the open.
const bfOpened = async (h, id) => {
  for (let i = 0; i < 50 && !h.openEvents.has(id); i += 1) await new Promise(resolve => setTimeout(resolve, 0));
  return h.openEvents.has(id);
};
test('a 409 names the night as data, and a night called Night (2) opens by that name (round 34 card 11)', async () => {
  const h = bfReview();
  h.data.history = [{id: 'h1', name: 'Night (2)', source: {datasetId: 'tw-1234567890-452-1690'}}];
  bfRefuse(h, {error: 'tw-1234567890-452-1690 is already in the timeline as "Night (2)" (h1); open it instead', nightId: 'h1'});
  await h.bfCommit();
  assert.equal(h.bf.nightId, 'h1', 'the identity travels beside the sentence');
  assert.equal(h.bf.notice, h.t('bfSameVod'));
  assert.ok(h.bfScreen().includes('data-action="bf-open-night"'));
  await bfClick(h, 'bf-open-night');
  assert.ok(await bfOpened(h, 'h1'), 'the notice opens the night the server named');
});
test('a reworded sentence cannot misdirect the night the console opens (round 34 card 11)', async () => {
  const h = bfReview();
  // The night holds the whole broadcast, so matching on the dataset id cannot find it either:
  // the id in the body is the only way there.
  h.data.history = [{id: 'h1', name: 'Night (2)', source: {datasetId: 'tw-1234567890'}}];
  // A sentence whose last bracket run is the range, not the night: reading words gives 452-1690.
  bfRefuse(h, {error: '"Night (2)" (h1) already holds tw-1234567890-452-1690 (452-1690); open it instead', nightId: 'h1'});
  await h.bfCommit();
  await bfClick(h, 'bf-open-night');
  assert.ok(await bfOpened(h, 'h1'), 'the console opens the night the body names, whatever the sentence says');
});
test('a refusal that names no night offers no button to open one (round 34 card 11)', async () => {
  const h = bfReview();
  h.data.history = [{id: 'h1', name: 'Night (2)', source: {datasetId: 'tw-1234567890-452-1690'}}];
  bfRefuse(h, {error: 'State changed; reload before retrying', nightId: null});
  await h.bfCommit();
  assert.equal(h.bf.nightId, '', 'the body says there is no night to open');
  assert.notEqual(h.bf.notice, h.t('bfSameVod'), 'a stale revision is not the claimed range sitting in the console');
  const screen = h.bfScreen();
  assert.ok(!screen.includes('data-action="bf-open-night"'), 'so no button promises to open one');
  assert.ok(screen.includes(h.esc('State changed; reload before retrying')), 'and the operator reads the server sentence');
});
test('a range that is already downloaded is reused, and a typed regular counts towards their standing (7.3/6.1)', async () => {
  const h = harness();
  (()=>{h.render=()=>{};h.lang='en';
    h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:900,joinedAt:'2026-01-01T00:00:00Z'},{id:'pb',name:'Bea',status:'Active',rating:800,joinedAt:'2026-01-01T00:00:00Z'}];
    h.data.history=[{id:'h1',name:'Monday night',format:'singles',raceTo:7,tables:4,status:'complete',archivedAt:'2026-09-01T12:00:00Z',
      source:{kind:'vod-backfill',vodId:'1234567890',datasetId:'tw-1234567890-452-1690',startS:452,endS:1690,channel:'examplechannel',title:'Monday night',humanReviewed:true},
      signOff:{at:'2026-09-02T03:15:00Z'},
      entrants:[{id:'e1',members:[{pid:'pa',name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Rico'}]}],
      matches:[{id:'m1',round:1,sides:['e1','e2'],score:[3,1],status:'complete',result:'played',winnerId:'e1',absent:[]}]}];
    h.bf=h.bfFresh();return h.bf.recent=[{channel:'examplechannel',error:null,vods:[{id:'1234567890',title:'Monday night',created_at:'2026-09-02T04:00:00Z',length_s:7200,imported:['tw-1234567890-452-1690']}]}]})();
  const pick = h.bfScreen();
  assert.ok(pick.includes(h.esc(h.t('bfReuse'))), 'the picker says this range is already downloaded');
  (()=>{h.bfPickVod('1234567890',7200,'Monday night');return h.bf.estimate={estimate_bytes:1200000000,disk:{free_bytes:84000000000,needed_bytes:1500000000,ok:true},already_imported:true}})();
  const verify = h.bfScreen();
  assert.ok(verify.includes('data-action="bf-use-imported"') && verify.includes(h.esc(h.t('bfReuse'))), 'and offers the range it holds instead of downloading it again');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'bf-use-imported'}}}});
  assert.equal(h.bf.step, 'dataset', 'reusing it goes straight to naming the night');
  assert.equal(h.bfUseImported() || h.bf.notice, h.t('bfReuse'), 'and the reuse is said out loud, in the operator’s words');
  assert.equal(JSON.stringify(h.bfEntrants(['Ann','Bea','Rico'])),
    JSON.stringify([{pid: 'pa', name: 'Ann'}, {pid: 'pb', name: 'Bea'}, {name: 'Rico'}]), 'a name the roster holds is sent as that regular');
  assert.ok(h.bfPersonBadge('Ann').includes(h.esc(h.t('member'))), 'a regular is marked as one at the point of typing');
  assert.ok(h.bfPersonBadge('Rico').includes(h.esc(h.t('guest'))), 'a guest is marked as counting towards nobody');
  assert.equal(h.bfPlayerFor('Ａｎｎ')?.id, 'pa', 'the name is folded the way the search folds it, so full-width typing still finds the regular');
  (()=>{h.bf.step='review';return h.bf.draft=[{start:452,end:780,sides:['Ann','Rico'],winner:'Ann',score:[3,1],confirmed:true}]})();
  const review = h.bfScreen();
  assert.ok(review.includes(h.esc(h.t('bfLinkedCount').replace('{n}',1).replace('{m}',2))), 'the review says exactly how many of the names are regulars');
  assert.ok(review.includes('badge bf-linked'), 'and every name carries its badge');
  const standing = h.playersScreen();
  assert.equal(standingCell(h, standing, 'Ann', h.t('played')), '1', 'the backfilled night counts towards the regular it names');
  assert.equal(standingCell(h, standing, 'Ann', h.t('wl')), `1\u20130`);
  assert.equal(standingCell(h, standing, 'Ann', h.t('winPct')), '100%');
  assert.ok(!/>Rico</.test(standing), 'and the guest counts towards nobody');
});
// ---- IA C′ stage 4: the Tonight tab. A phase strip (Register · Rack · Play · Close), every phase always
// reachable, the default is the night's own phase, and Register holds everything the night needs before the draw.
function tonightNight(h, state) {
  (()=>{h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:100},{id:'pb',name:'Bea',status:'Active',rating:900}];
    var E=(id,pid,name,absent=false)=>({id,absent,members:[{pid,name}]}); // var: test 4 applies this fixture twice in one vm context
    h.data.tournament={id:'t0',name:'Friday',format:'singles',raceTo:3,tables:2,status:'registration',entrants:[E('a','pa','Ann'),E('b','pb','Bea'),E('g',null,'Walk-in Wu',true)],matches:[]};
    h.data.history=[];h.data.events=[];return h.data.notes=[]})();
  if (state === 'drawn') (()=>{h.data.tournament.status='active';h.data.tournament.entrants[2].absent=false;return h.data.tournament.matches=[
      {id:'m1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[]},
      {id:'m2',round:1,sides:['b','g'],score:[0,0],status:'scheduled',table:null,absent:[]},
      {id:'m3',round:2,sides:['a',null],score:[0,0],status:'pending',table:null,absent:[],sources:['m1','m2']}]})();
  if (state === 'done') (()=>{h.data.tournament.status='complete';return h.data.tournament.matches=[
      {id:'m1',round:1,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',absent:[]}]})();
}
test('Tonight is one tab whose state follows the night: an empty venue, entrants, a live event, all signed', () => {
  for (const [state, gate, venue] of [[null, 'registration', 'registration'], ['drawn', 'active', 'active'], ['done', 'complete', 'complete']]) {
    const h = harness();
    tonightNight(h, state);
    assert.equal(h.comp(), gate, `${state || 'registration'} → the server gate is ${gate}`);
    assert.equal(h.tonightState(), venue, `${state || 'registration'} → the venue is ${venue}`);
  }
  // no entrants and no draw is the idle venue: the server is still open for registration
  const idle = harness();
  (()=>{idle.data.players=[];return idle.data.tournament={id:'t0',name:'',format:'singles',raceTo:3,tables:2,status:'registration',entrants:[],matches:[]}})();
  assert.equal(idle.comp(), 'registration', 'the server gate still says registration');
  assert.equal(idle.tonightState(), 'idle', 'but with nobody signed up the venue is idle');
  assert.equal(idle.liveComp(), false, 'and no event is live');
  const h = harness({hash: '#/tonight'});
  assert.equal(h.tab, 'tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'the Tonight route carries no phase');
  tonightNight(h, 'drawn');
  h.syncRoute(false);
  assert.equal(h.context.location.hash, '#/tonight', 'a night in progress never rewrites the URL');
  assert.ok(h.visits.every(v => v[0] === 'replace'), 'a data-driven change never pushes history');
  assert.equal(JSON.parse(JSON.stringify(h.navTabs))[0], 'tonight', 'Tonight is the first tab');
  // Owner item 7 (round 5): the destination keeps its route key and is called Tournament.
  for (const [lang, label] of [['en', 'Tournament'], ['zh', '赛事']]) { h.lang=(lang); assert.equal(h.navLabel('tonight'), label, 'one destination, named once per language'); }
});
test('the step is a read-only scene, and no second-level menu exists anywhere in the shell', async () => {
  const h = harness({hash: '#/tonight/play'});
  tonightNight(h, 'drawn');
  h.render=()=>{};
  assert.equal(h.routeOf('#/tonight/play'), 'tonight', 'the old phase route resolves to Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'and the URL folds in place');
  for (const lang of ['en', 'zh']) {
    h.lang=(lang);
    const scene = h.scene();
    assert.ok(!/<button/.test(scene), `${lang}: nothing in the scene is clickable`);
    assert.ok(!/data-phase|data-play|data-more/.test(scene), `${lang}: no phase, play or more hooks in the scene`);
    assert.ok(!/scene-node|scene-track|aria-current/.test(scene), `${lang}: the four-word state track is gone (owner item 2)`);
    assert.ok(/role="status"/.test(scene) && !/<nav/.test(scene), `${lang}: the scene is a status report, not a navigation landmark`);
    assert.ok(scene.includes(h.esc(h.t('raceN').replace('{n}',h.race()))), `${lang}: a drawn night reads as itself — its format and race, no step words`);
    for (const key of ['sceneRegister', 'sceneRack', 'scenePlay', 'sceneClose']) assert.ok(!source.includes(`${key}:`), `${lang}: ${key} went with the track`);
  }
  // The second level is gone at the source, not just on this screen: nothing can render one again.
  assert.equal((source.match(/data-phase=/g) || []).length, 0, 'no phase button is left in the shell');
  assert.equal((source.match(/data-play=/g) || []).length, 0, 'no play button is left in the shell');
  assert.equal((source.match(/data-more=/g) || []).length, 0, 'no more button is left in the shell');
  for (const gone of ['phaseStrip', 'playStrip', 'playTabs', 'barTabs', 'barMore', 'moreOpen', 'tabbar-more']) {
    assert.ok(!source.includes(gone), `${gone} is deleted, not hidden`);
  }
  assert.ok(!fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8').includes('tabbar-more'), 'and its stylesheet rule went with it');
});
test('Register holds the night, random pairing, the desk, the entry list and Rack', () => {
  const h = harness();
  tonightNight(h, null);
  assert.equal(h.tonightState(), 'registration', 'three entrants and no draw is the registration venue');
  for (const lang of ['en', 'zh']) {
    h.lang=(lang);
    const html = h.tonightScreen();
    assert.ok(html.includes('id="entrant-form"') && html.includes('class="pick-btn'), `${lang}: desk and its combobox`);
    assert.ok(html.includes('data-action="event-rename"') && html.includes('class="card card--event"'), `${lang}: the name is a title with a pencil, not a form on the page`);
    assert.ok(!html.includes('id="settings-form"'), `${lang}: the four fields exist once, in the dialog`);
    assert.ok(html.includes('data-action="entrant-remove"') && !html.includes('data-action="entrant-absence"'), `${lang}: Remove per entrant, and no not-here button (round 10, item 2)`);
    assert.ok(!html.includes('class="attendance"') && !/Here now|\u5df2\u5230\u573a/.test(html), `${lang}: the entry list does not label who is here (round 10, item 2)`);
    assert.ok(!html.includes('data-tab="players"') && !/Manage regulars|\u7ba1\u7406\u5e38\u5ba2/.test(html), `${lang}: no Manage regulars button - the nav already gives Regulars a ball (round 10, item 1)`);
    assert.ok(html.includes('data-action="tournament-start"'), `${lang}: Rack the night is on Register`);
    assert.ok(html.includes('data-action="promote" data-name="Walk-in Wu"'), `${lang}: every guest entrant carries Add to regulars, the one action the word bank and the handler already had`);
    assert.ok(html.includes('class="end-night"') && html.includes('data-action="event-delete"'),
      `${lang}: the event card carries the night\u2019s end (round 13, owner item 3)`);
    assert.ok(!h.statusScreen().includes('class="end-night"'),
      `${lang}: and the Back room does not carry it twice`);
    assert.ok(!html.includes('class="first-run"'), `${lang}: the three-step guide is retired, not unrendered`);
  }
  h.data.tournament.format='doubles';
  assert.ok(h.tonightScreen().includes('class="pairing"'), 'doubles adds random pairing');
  assert.ok(!h.playersScreen().includes('data-action="promote"'), 'Regulars no longer carries guests tonight');
});
test('the night is drawn and started from the same place, and being away is a matchup fact', async () => {
  const h = harness();
  tonightNight(h, null);
  for (const [lang, notHere] of [['en', 'Not here'], ['zh', '未到场']]) {
    h.lang=(lang);
    const html = h.tonightScreen();
    assert.ok(html.includes('data-action="tournament-start"'), `${lang}: the start-the-event button`);
    assert.ok(html.includes(h.esc(h.t('rackHint'))), `${lang}: how the draw is made`);
    assert.ok(!/data-action="entrant-absence"/.test(html) && !html.includes(notHere), `${lang}: being away is not a fact this page records (round 10, item 2)`);
  }
  h.render=()=>{};
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  await click({action: 'entrant-absence', id: 'g', absent: 'false'});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls.map(c=>c.name))), [], 'a not-here click on the desk writes nothing any more (round 10, item 2)');
  h.calls.length=0;
  await click({action: 'tournament-start'});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls.map(c=>c.name))), ['tournament_start'], 'starting the event is one write');
  assert.equal(h.tab, 'tonight', 'and the night never leaves Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'the URL does not move to a phase');
  // after the draw the start button is gone, the whole night form retires, and the tables carry it
  tonightNight(h, 'drawn');
  const drawn = h.tonightScreen();
  assert.ok(!drawn.includes('data-action="tournament-start"'), 'a drawn night cannot be drawn twice');
  assert.ok(!drawn.includes('id="settings-form"'), 'the start-the-night form retires once the event is live');
  assert.ok(!drawn.includes('id="rename-form"'), 'the rename form folded into the settings dialog');
  assert.ok(drawn.includes('data-action="event-rename"') && drawn.includes('class="event-title"'),
    'which the night card opens, so the night can still be renamed');
  assert.ok(!drawn.includes('table-grid') && drawn.includes('class="bracket-view"'), 'no table cards: the draw is where a match is put on a table (round 12, owner item 1)');
});
test('old phase routes fold into the one Tonight route, in place', () => {
  for (const hash of ['#/tonight/rack', '#/tonight/close', '#/tonight/bogus', '#/tonight/register', '#/tonight/play']) {
    const h = harness({hash});
    h.syncRoute(false);
    assert.equal(h.tab, 'tonight', hash);
    assert.equal(h.context.location.hash, '#/tonight', `${hash} folds to #/tonight`);
    assert.ok(h.visits.every(v => v[0] === 'replace'), `${hash} never pushes history`);
  }
});

test('every tab id resolves to a screen module, so no tab can blank the console (stage 6)', () => {
  const h = harness();
  // The registry holds modules. A module mounts into a host and paints
  // markup there, so this asserts the behaviour, not a name in a list.
  const painted = JSON.parse(JSON.stringify(Object.keys(h.screenModules).map(id=>{const module=h.screenModules[id],host={innerHTML:''};module.mount(host);const size=host.innerHTML.length;module.detach();return {id,size}})));
  assert.deepEqual(painted.filter(row => row.size === 0), [], 'every registered screen mounts and paints markup, so no tab can blank the console');
  assert.deepEqual(JSON.parse(JSON.stringify(h.navTabs.filter(id=>!h.screenModules[id]))), [], 'and every tab id resolves to one of them');
  assert.deepEqual(JSON.parse(JSON.stringify(Object.keys(h.screenModules))), ['clock', 'tonight', 'records', 'vision', 'players', 'status'], 'the five destinations and the shot timer, and nothing else: the retired ones are gone, not hidden');
  // Owner item 4 (round 5): the shot timer is a destination like any other - a route, a
  // screen and a name - so no tab can blank it and a deep link reaches it.
  assert.equal(h.routeOf('#/clock'), 'clock', 'the clock has its own route');
  assert.equal(typeof h.screenModules.clock.update, 'function', 'and a screen behind it');
  assert.equal(typeof h.screenModules.floor, 'undefined', 'the Floor screen is retired');
  assert.equal(typeof h.screenModules.matches, 'undefined', 'and so is Matches');
});
test('Close is the night\u2019s end: the results sheet, second chance, archive and delete (stage 6)', async () => {
  const h = harness();
  (()=>{h.data.notes=[];h.data.players=[{id:'pa',name:'Ada',status:'Active',rating:1},{id:'pb',name:'Bo',status:'Active',rating:2}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    h.data.tournament={id:'t0',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'registration',entrants:[E('a','pa','Ada'),E('b','pb','Bo')],matches:[]};
    h.data.history=[];return h.tab='tonight'})();
  h.render=()=>{};
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  const close = () => h.tonightScreen();
  assert.ok(!close().includes('data-action="results-sheet"'), 'no sheet before the draw');
  assert.ok(close().includes('class="card card--event"') && close().includes('event-params'), 'the event card is there from the start, with its name and parameters');
  assert.ok(!/data-phase=/.test(close()), 'and it has no phase button left to point anywhere');
  h.data.tournament.matches=[{id:'q1',round:1,sides:['a','b'],score:[0,0],status:'scheduled',absent:[]}];
  const drawn = close();
  assert.ok(!drawn.includes('data-action="results-sheet"'), 'a drawn night does not offer the sheet yet (round 19, owner item 1)');
  assert.ok(drawn.includes('data-action="new-event"') && drawn.includes('data-action="event-delete" data-id="t0"'), 'Archive & new / Delete event stay in Close');
  assert.ok(drawn.indexOf('data-action="results-sheet"') < drawn.indexOf('data-action="new-event"'), 'the sheet comes first: Results sheet, second chance, archive / delete');
  h.data.tournament.revival=null;
  await click({action: 'results-sheet', id: 't0'});
  assert.equal(h.sheetId, 't0', 'the click opens the sheet');
  assert.ok(close().includes('class="stack results-sheet"'), 'the sheet replaces the Close view');
  assert.ok(h.tonightScreen().includes('class="stack results-sheet"'), 'the sheet survives the tonight render, not only a direct call');
  await click({action: 'sheet-back'});
  assert.ok(!close().includes('class="stack results-sheet"'), 'back returns to Close');
});

test('\u2264750px: the fixed bottom bar carries all six destinations, with no More behind it (stage 7)', () => {
  const h = harness();
  const shell = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
  assert.ok(shell.includes('<nav id="tabbar"'), 'the bottom bar is part of the shell');
  const bar = () => h.tabbarHTML();
  for (const id of ['clock', 'tonight', 'records', 'vision', 'players', 'status']) assert.ok(bar().includes(`data-tab="${id}"`), `${id} is a bar slot`);
  assert.equal((bar().match(/class="tabbar-slot"/g) || []).length, 6, 'the ball map is whole on the phone: 1 is the timer, 2-6 the destinations');
  assert.ok(bar().indexOf('data-tab="clock"') < bar().indexOf('data-tab="tonight"'), 'and ball 1 leads it (round 7 / owner item 2, his ruling)');
  assert.equal((bar().match(/aria-current="page"/g) || []).length, 1, 'the bar marks exactly the tab you are on');
  assert.ok(!/data-more|tabbar-more/.test(bar()), 'no More button and no panel behind it');
  assert.deepEqual(JSON.parse(JSON.stringify(h.primaryNav())), JSON.parse(JSON.stringify(h.navTabs)), 'the bar and the top nav render the same list');
  h.tab='players';
  assert.equal((bar().match(/aria-current="page"/g) || []).length, 1, 'Regulars is the current slot on the bar itself');
  assert.ok(bar().includes('data-tab="players"'), 'the Regulars slot is the current one');
  h.tab='tonight';
  assert.ok(!/data-tab="(floor|matches)"/.test(bar()), 'the bar never grows the retired tabs');
});
test('the bottom bar survives Vision, which is how Vision gets an exit, and every vision surface clears it (stage 7)', () => {
  const h = harness();
  assert.ok(h.tabbarHTML().includes('data-tab="vision"'), 'Vision is a bar slot');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('[data-tab=vision] #tabbar{display:flex}'), 'the vision rule that hides the top nav row does not hide the bar');
  assert.ok(css.includes('env(safe-area-inset-bottom)'), 'the bar and its padding respect the safe area');
  assert.ok(css.includes('--tabbar-h'), 'the bar height is one token the vision surfaces are offset by');
  for (const sel of ['.vs-sheettabs{bottom:calc(var(--tabbar-h) + var(--clockbar-h))', '.vs-strip{bottom:calc(var(--tabbar-h) + var(--clockbar-h) + 44px)']) {
    assert.ok(css.includes(sel), `${sel} sits above both fixed rows`);
  }
  assert.ok(css.includes('@media print{#ops-shell #tabbar{display:none!important}}'), 'the bar never prints');
});

test('stage 8: Floor and Matches are not screens any more, and every old way in folds into Tonight (stage 8)', async () => {
  const h = harness({hash: '#/floor'});
  assert.deepEqual(JSON.parse(JSON.stringify(h.navTabs)), ['tonight', 'records', 'vision', 'players', 'status'], 'the row is Tonight, Records, Vision, Regulars, Back room');
  assert.equal(h.tab, 'tonight', 'the retired Floor hash opens Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'and folds there in place');
  assert.ok(h.visits.every(v => v[0] === 'replace'), 'opening an old hash never adds a history entry');
  for (const id of ['floor', 'matches', 'setup']) {
    assert.equal(h.routeOf((id)), 'tonight', `the retired ${id} id is a legacy route, not a screen`);
  }
  assert.equal(h.routeOf("records"), 'records', 'a live route is not a legacy one');
  h.render=()=>{};
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'floor'}}}});
  assert.equal(h.tab, 'tonight', 'the retired floor action leaves the screen where it is');
  for (const screen of ['tonightScreen', 'recordsScreen', 'playersScreen', 'statusScreen']) {
    assert.ok(!/data-tab="(floor|matches|setup)"/.test((h[screen])()), `${screen} offers no retired tab`);
  }
});

// ---- IA C′ stage 9: one bar, five destinations, a data-driven Tonight, and the shot timer's one name.
test('the bar is two rows: the shot timer, then the five destinations and the tools; no hall and no strip (stage 9 / owner §13.1 + round 7 item 2)', () => {
  const html = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const start = html.indexOf('<div class="bar">'), end = html.indexOf('</header>');
  assert.ok(start > 0 && end > start, 'one bar inside one header');
  const bar = html.slice(start, end);
  // Owner item 1: the Corner Pocket box and its 8 ball are gone, and nothing replaces them.
  assert.ok(!/class="hall"|class="hallname"/.test(html), 'the hall block is deleted, not hidden');
  assert.ok(!html.includes('Corner Pocket') || !bar.includes('Corner Pocket'), 'no wordmark is left in the bar');
  assert.ok(!/class="hall"|hallname/.test(css), 'and its styles went with it');
  // Owner items 2 and 5: the strip is gone, so the timer has exactly one home in the bar.
  assert.equal(html.indexOf('id="strip"'), -1, 'the strip row is deleted');
  assert.equal(css.indexOf('#strip'), -1, 'and so are its rules');
  assert.ok(!/navColors/.test(source) && !/navColors/.test(css), 'the old per-destination colour map is gone with the balls it painted');
  assert.equal((html.match(/data-clock-host/g) || []).length, 1, 'one timer host in the whole shell, in its own row');
  assert.equal((html.match(/<header>/g) || []).length, 1, 'one header');
  // Owner item 2 (round 7) gave the timer a row of its own; owner item 1 (round 8) put that row
  // under the destinations, so the bar is two rows - the five destinations and the tools, then the
  // clock - and nothing in .tools holds a second timer.
  assert.ok(bar.includes('<div class="clockbar" role="group" aria-label="Shot timer / 出杆计时" data-clock-host></div>'),
    'the clock row is a named group with one host, empty until ops.js paints it');
  assert.ok(bar.indexOf('<nav id="nav"') < bar.indexOf('class="clockbar"'), 'the destinations come first, the clock row under them');
  assert.ok(bar.indexOf('<nav id="nav"') < bar.indexOf('class="tools"'), 'the destinations, then the tools');
  assert.ok(bar.indexOf('class="barrow"') < bar.indexOf('class="tools"'), 'the tools share the destinations\' row, not the clock\'s');
  assert.ok(source.includes("$('#nav').innerHTML=clockNavButton()+primaryNav()"), 'render() paints six items into the nav: the timer, then the destinations');
  assert.ok(!source.includes('timerSlotHost'), 'the second definition of the host is gone, not just unused');
  assert.equal((bar.match(/<div class="tools">/g) || []).length, 1, 'and one tools row, unchanged');
  assert.ok(bar.includes('<span id="connection" class="badge" hidden>'), 'the connection badge still starts hidden and empty');
  assert.ok(bar.includes('data-lang="en"') && bar.includes('data-lang="zh"') && bar.includes('data-theme-group'), 'the language and theme chips are untouched');
  assert.ok(css.includes('#ops-shell .barrow > nav{flex:0 1 auto;min-width:0;padding:0}'),
    'the nav keeps its own size inside its row: a row that shrinks it wraps the destinations (measured 96 px against 44)');
  assert.ok(/#ops-shell \.bar\{flex-wrap:nowrap;flex-direction:column/.test(css), 'the bar itself is a column of two rows');
  assert.ok(/#ops-shell \.barrow > \.tools\{flex:0 1 auto;min-width:0;flex-wrap:wrap\}/.test(css), 'the tools are the part that folds');
  assert.ok(!/\.brand/.test(css), 'the brand styles went with the brand block');
  const h = harness();
  assert.equal(h.primaryNav().length, 5, 'the one bar renders five destinations');
  assert.deepEqual(JSON.parse(JSON.stringify(h.primaryNav())), JSON.parse(JSON.stringify(h.navTabs)), 'and Back room is one of them (always, not conditionally)');
  const destinations = JSON.parse(JSON.stringify(h.primaryNav().map((k,i)=>h.ballColor(i+2))));
  assert.deepEqual(destinations, ['#2f6fd0', '#c8382f', '#e885ad', '#e07a29', '#2f8f4e'],
    'the five destinations draw balls 2 (blue) through 6 (green): the timer is ball 1');
  assert.equal(h.ballHTML(1).includes('data-stripe'), false, 'ball 1 is a solid');
  for (const [lang, back] of [['en', 'Back room'], ['zh', '后台']]) {
    h.lang=(lang);
    assert.ok(h.render.toString().includes('paintNav()') && source.includes("$('#nav').innerHTML=clockNavButton()+primaryNav()"),
      `${lang}: render paints the bar from the one list`);
    assert.ok(h.render.toString().includes('paintDocument()') && source.includes('document.documentElement.lang'),
      `${lang}: render publishes the language it painted in`);
    assert.equal(h.navLabel('status'), back, `${lang}: the fifth destination keeps its name`);
  }
});
// ---- owner round 2, items 3-7: the palette, the material balls and the always-on timer slot.
test('one palette keyed by ball number colours every ball: 1-8 the owner list, 9-15 the same hues striped, 16+ wrapping', () => {
  const h = harness();
  const palette = JSON.stringify(h.ballPalette);
  assert.equal(palette, JSON.stringify(['#f2c14e','#2f6fd0','#c8382f','#e885ad','#e07a29','#2f8f4e','#8a5a2b','#1b1b1b',
    '#f2c14e','#2f6fd0','#c8382f','#e885ad','#e07a29','#2f8f4e','#8a5a2b']),
    '1 yellow, 2 blue, 3 red, 4 pink, 5 orange, 6 green, 7 brown, 8 black; 9-15 the same seven hues');
  for (let n = 1; n <= 8; n++) {
    assert.equal(h.ballNumber((n)), n, `ball ${n} keeps its number`);
    assert.equal(h.ballStripe((n)), 0, `ball ${n} is a solid`);
    assert.ok(h.ballHTML((n)).includes('--ball-c:' + h.ballColor((n))), `ball ${n} carries its own hue`);
  }
  for (let n = 9; n <= 15; n++) {
    assert.equal(h.ballStripe((n)), 1, `ball ${n} is a stripe`);
    assert.equal(h.ballColor((n)), h.ballColor(((n - 8))), `ball ${n} is the same hue as ball ${n - 8}`);
    assert.ok(h.ballHTML((n)).includes('data-stripe="1"'), `ball ${n} is drawn as a stripe`);
  }
  // Past a full rack the number wraps, the way entrant chips keep counting.
  assert.equal(h.ballNumber(16), 1, '16 wraps to 1');
  assert.equal(h.ballNumber(23), 8, '23 wraps to 8');
  assert.equal(h.ballNumber(30), 15, '30 wraps to 15');
  assert.equal(h.ballColor(16), '#f2c14e', 'and 16 is yellow again');
  assert.ok(h.ballHTML(16).includes('>1<'), 'the plate shows the wrapped number, not 16');
  // The plate is the number, inside the sphere; the hue is the only inline style.
  assert.equal(h.ballHTML(3), '<span class="ball" style="--ball-c:#c8382f"><i>3</i></span>', 'one helper, one shape');
  // Every place a ball is drawn uses that helper.
  const entrants = (()=>{h.data.tournament={id:'t',name:'',format:'singles',raceTo:7,tables:1,status:'registration',entrants:[{id:'e1',members:[{name:'A'}]},{id:'e2',members:[{name:'B'}]}],matches:[]};h.data.players=[];return h.entrantsCard()})();
  assert.ok(entrants.includes('--ball-c:#f2c14e') && entrants.includes('--ball-c:#2f6fd0'), 'entrant chips draw balls 1 and 2 from the palette');
  assert.ok(!entrants.includes('<span class="ball"><i>'), 'and no longer a flat uncoloured disc');
  assert.ok(h.ballHTML(6).includes('--ball-c:#2f8f4e'), 'ball 6 is the green one the owner asked for');
});
test('the timer slot renders and works in all four venue states, and nothing in it reads comp() (owner items 1 and 5)', async () => {
  // comp() is the tournament status; the live vocabulary is idle through complete. The
  // brief and §13.1 name the last one "closed" — the same state, the repo's spelling.
  const states = [['registration', 'idle'], ['registration', 'registration'], ['active', 'active'], ['complete', 'closed']];
  for (const [status, label] of states) {
    const h = harness();
    (()=>{h.data.tournament={id:'t',name:'',format:'singles',raceTo:7,tables:4,status:(status),entrants:[{id:'e1',members:[{name:'A'}]}],matches:[]};return h.data.players=[]})();
    assert.equal(h.comp(), status, `${label}: the venue is in that state`);
    assert.equal(h.tonightState() !== undefined, true, `${label}: and Tonight has a state of its own`);
    const markup = h.clockHTML();
    assert.ok(h.clockHTML().includes('data-clock'), `${label}: the clock is in the slot`);
    assert.ok(h.clockHTML().includes('data-action="clock-toggle"'), `${label}: the start/pause control is there`);
    assert.ok(h.clockHTML().includes('data-action="clock-reset"'), `${label}: so is reset`);
    assert.ok(h.clockHTML().includes('data-action="clock-set" data-value="20"'), `${label}: and the four presets`);
    assert.ok(markup.includes('data-progress'), `${label}: with the elapsed bar`);
    assert.ok(!/kicker/.test(markup), `${label}: no .kicker second line in the slot`);
    assert.ok(!/class="ball/.test(markup) && !/data-tab=/.test(markup),
      `${label}: and no ball and no tab: the bar is the instrument, ball 1 is the timer's door`);
    // The controls work: toggle starts and pauses, reset clears the deadline, a preset
    // changes the duration through the server before the shell adopts it.
    // A DOM just real enough to render: the shell the language is published on, the
    // elements render paints, and the timer slot, which is the mount this work is about.
    const slot = {innerHTML: ''};
    const node = () => ({innerHTML: '', className: '', textContent: '', dataset: {}, style: {}, hidden: false,
      classList: {toggle() {}, add() {}, remove() {}}, setAttribute() {}, getAttribute: () => null,
      querySelector: () => null, querySelectorAll: () => [], appendChild() {}, addEventListener() {}});
    const shell = node(), nav = node(), tabbar = node(), main = node();
    shell.querySelector = selector => (selector === '.clockbar' ? slot : null);
    h.context.document.querySelector = selector => ({'#ops-shell': shell, '#ops-shell .clockbar': slot, '#nav': nav, '#tabbar': tabbar, '#main': main}[selector] || null);
    h.context.document.body = node();
    h.render=()=>{};
    // The shell's click listener finds its button with closest('button,.modal-backdrop').
    const act = action => h.handlers.click({target: {closest: selector => (selector === 'button,.modal-backdrop' ? {dataset: {action}, classList: {contains: () => false}} : null)}});
    h.timer={duration:30,remaining:30,deadline:null};
    act('clock-toggle');
    assert.ok(h.timer.deadline > 0, `${label}: Start sets a deadline`);
    const running = h.clockHTML();
    assert.ok(running.includes('Pause') || running.includes('暂停'),
      `${label}: the control says Pause while the clock runs - the bar has no ball to light up`);
    act('clock-toggle');
    assert.equal(h.timer.deadline, null, `${label}: Pause clears it`);
    h.timer={duration:30,remaining:4,deadline:null};
    act('clock-reset');
    assert.equal(h.timer.remaining, 30, `${label}: Reset goes back to the duration`);
    await act('clock-set');
    assert.ok(h.timer.duration === 30, `${label}: a preset with no data-value keeps the duration it had`);
  }
  const h = harness();
  h.context.document.querySelector = () => ({innerHTML: '', classList: {toggle() {}}, dataset: {}, style: {}, setAttribute() {}, textContent: ''});
  h.render=()=>{};
  await h.handlers.click({target: {closest: selector => (selector === 'button,.modal-backdrop' ? {dataset: {action: 'clock-set', value: '45'}, classList: {contains: () => false}} : null)}});
  assert.equal(h.timer.duration, 45, 'a preset sets the duration the server accepted');
  assert.equal(h.timer.remaining, 45, 'and the clock starts the new duration');
  // Nothing in the slot can be gated on the venue state, and the slot is painted from the
  // one helper: once at boot and once on every render.
  assert.ok(!/function clockHTML\([^)]*comp/.test(source), 'clockHTML() reads no venue state');
  assert.ok(!/function clockHTML\(\)\{[^}]*comp\(/.test(source), 'nothing inside clockHTML() asks the venue state either');
  assert.equal((source.match(/paintClockSlot\(\)/g) || []).length, 3, 'one definition, one boot paint, and the one repaint the sync sentence asks for; every other paint goes through the clock module');
  assert.ok(/function showSyncError\(text\)\{[^}]*paintClockSlot\(\)/.test(source), 'and that third call is inside showSyncError(): the slot is still painted from the one helper');
});

test('#connection is not a revision slogan: silent while the API answers, one bilingual line when it does not (stage 9)', async () => {
  const h = harness();
  const nodes = new Map();
  const stub = () => ({textContent: '', hidden: false, innerHTML: '', className: '', dataset: {}, style: {},
    classList: {toggle() {}, add() {}, remove() {}}, setAttribute() {}, getAttribute: () => null,
    querySelector: () => null, querySelectorAll: () => [], appendChild() {}, addEventListener() {}});
  h.context.document.querySelector = selector => { if (!nodes.has(selector)) nodes.set(selector, stub()); return nodes.get(selector); };
  h.context.document.querySelectorAll = () => [];
  h.context.document.documentElement = {dataset: {}, lang: ''};
  h.context.document.getElementById = () => null;
  nodes.set('#connection', stub());
  const badge = () => nodes.get('#connection');
  assert.equal(badge().hidden, false, 'the stub starts visible, so hiding it is something the shell does');
  h.context.fetch = async () => ({ok: true, status: 200, json: async () => ({revision: 41, settings: {},
    tournament: {id: 't0', name: 'Friday', format: 'singles', raceTo: 7, tables: 2, status: 'registration', entrants: [], matches: []},
    players: [], history: [], notes: []})});
  await h.reload();
  assert.equal(badge().hidden, true, 'a healthy connection says nothing at all');
  assert.equal(badge().textContent, '', 'and the badge is empty, not a revision');
  assert.ok(!source.includes("$('#connection').textContent=`"), 'no render path paints a slogan into the badge');
  assert.ok(!source.includes("t('connected')") && !source.includes('LOCAL · SAVED'), 'the LOCAL · SAVED copy is gone from the shell');
  h.context.fetch = async () => ({ok: false, status: 503, json: async () => ({})});
  await h.reload();
  assert.equal(badge().hidden, false, 'a failed load brings the badge back');
  for (const [lang, text] of [['en', 'OFFLINE · edits will not save'], ['zh', '离线 · 改动不会保存']]) {
    h.lang=(lang);
    assert.equal(h.t('connectionLost'), text, `${lang}: the badge has honest copy`);
  }
  h.lang='en';
  assert.equal(badge().textContent, 'OFFLINE · edits will not save', 'and the failure writes exactly that');
  // The revision still exists where a maintainer can find it: one line on the Back room page.
  assert.ok(source.includes("<p class=\"muted last-write\">"), 'the Back room carries the last write');
  assert.ok(h.statusScreen().includes(h.esc(h.t('lastWrite').replace('{n}',String(h.data.revision)))), 'and prints the revision without inventing a timestamp');
});
test('the four venue states decide which cards exist on Tonight, and a state change never writes history (stage 9)', () => {
  const idle = harness();
  (()=>{idle.data.players=[];return idle.data.tournament={id:'t0',name:'',format:'singles',raceTo:7,tables:4,status:'registration',entrants:[],matches:[]}})();
  assert.equal(idle.tonightState(), 'idle');
  const idleHtml = idle.tonightScreen();
  assert.ok(idleHtml.includes('id="entrant-form"') && idleHtml.includes('class="card card--event"'),
    'idle: a named night sees its three cards, with the desk in the entrants card');
  assert.ok(!idleHtml.includes('modal--start'), 'idle: a named event has nothing to ask for');
  idle.data.tournament.id='';
  const fresh = idle.tonightScreen();
  assert.ok(fresh.includes('class="modal modal--start"') && fresh.includes('id="settings-form"'),
    'idle and unnamed: one dialog, holding the fields that name the night');
  assert.ok(!fresh.includes('class="idle-registration"') && !fresh.includes('id="entrant-form"'),
    'and nothing else is on the screen: the dialog is the way in');
  idle.data.tournament.id='t0';
  assert.ok(!idleHtml.includes('table-grid'), 'idle: no card grid of tables (owner item 3)');
  for (const gone of ['class="scoreboard"', 'card--wrap', 'side-panel', 'table-grid']) {
    assert.ok(!idleHtml.includes(gone), `idle: no ${gone}`);
  }
  assert.ok(idleHtml.includes('class="rounds"') && idleHtml.includes('<article class="empty">'),
    'idle: round 13, owner item 9: the draw is the tab\u2019s second element, empty, under its heading');
  const reg = harness();
  tonightNight(reg, null);
  assert.equal(reg.tonightState(), 'registration');
  const regHtml = reg.tonightScreen();
  for (const there of ['id="entrant-form"', 'class="pick-btn', 'data-action="tournament-start"', 'class="card card--event"']) {
    assert.ok(regHtml.includes(there), `registration: ${there}`);
  }
  for (const gone of ['class="scoreboard"', 'card--wrap']) {
    assert.ok(!regHtml.includes(gone), `registration: no ${gone}`);
  }
  assert.ok(regHtml.includes('class="rounds"') && regHtml.includes('<article class="empty">'),
    'registration: the draw is on the tab, empty, under its own heading');
  const active = harness();
  tonightNight(active, 'drawn');
  assert.equal(active.tonightState(), 'active');
  assert.equal(active.comp(), 'active');
  const activeHtml = active.tonightScreen();
  for (const there of ['class="rounds"', 'class="entry row"', 'data-action="event-rename"', 'class="bracket-view"']) {
    assert.ok(activeHtml.includes(there), `active: ${there}`);
  }
  for (const gone of ['id="settings-form"', 'class="scoreboard"', 'card--wrap']) {
    assert.ok(!activeHtml.includes(gone), `active: no ${gone}`);
  }
  assert.ok(active.clockScreen().includes('class="scoreboard"'),
    'round 13, owner item 6: the board is on the timer page, and this tab shows the draw');
  (()=>{active.data.tournament.matches[1].status='live';return active.data.tournament.matches[1].table=1})();
  assert.equal(active.dirtyComp(), true, 'a ball on a table is what dirty means');
    // Round 21, owner item 1: the table belongs to the card's own head, where it already is; beside
    // player A's name it read like part of their name.
    const drawn = active.tonightScreen();
    assert.ok(drawn.replace(/<[^>]*>/g, ' ').includes('Table 1') && !drawn.includes('table-chip'),
      'the card says which table the group is on, in its own head');
  const done = harness();
  tonightNight(done, 'done');
  assert.equal(done.tonightState(), 'complete');
  assert.equal(done.comp(), 'complete');
  const doneHtml = done.tonightScreen();
  for (const there of ['class="card card--event"', 'data-action="results-sheet"', 'data-action="new-event"', 'class="rounds"']) {
    assert.ok(doneHtml.includes(there), `complete: ${there}`);
  }
  for (const gone of ['class="scoreboard"', 'id="settings-form"']) {
    assert.ok(!doneHtml.includes(gone), `complete: no ${gone}`);
  }
  assert.ok(doneHtml.includes('data-vs-role="entrant-record"') && !doneHtml.includes('side-panel'),
    'complete: every entrant row carries the night\u2019s record, and there is no second table (round 19, owner item 3)');
  assert.ok(doneHtml.includes('class="entry row"'), 'complete: the entrants stay, so the night can be read back');
  // The state machine is data, not history: a night that moves on repaints the same URL.
  const h = harness();
  tonightNight(h, null);
  h.render=()=>{};
  (()=>{h.data.tournament.status='active';return h.data.tournament.matches=[{id:'m1',round:1,sides:['a','b'],score:[0,0],status:'live',table:1,absent:[]}]})();
  h.syncRoute(false);
  assert.equal(h.context.location.hash, '#/tonight', 'a data-driven move keeps the one Tonight URL');
  assert.ok(h.visits.every(v => v[0] === 'replace'), 'and never adds a history entry');
});
test('the tables are resident, the dashboard follows the live event, and the night\'s buttons write the right actions (stage 9)', async () => {
  const h = harness();
  (()=>{h.data.players=[{id:'p1',name:'Ana',status:'Active',rating:50}];return h.data.tournament={id:'t0',name:'',format:'singles',raceTo:7,tables:3,status:'registration',entrants:[],matches:[]}})();
  const startView = h.tonightScreen();
  assert.ok(startView.includes('id="entrant-form"') && startView.includes('card card--event'), 'the desk is the resident body (owner item 3: no table grid)');
  assert.equal((startView.match(/data-table="/g) || []).length, 0, 'and no table card is drawn anywhere');
  assert.ok(!startView.includes('class="scoreboard"') && !startView.includes('side-panel'), 'no dashboard while the event is not live');
  h.data.tournament.id='';
  assert.ok(h.tonightScreen().includes('id="settings-form"') && h.tonightScreen().includes('class="modal modal--start"'),
    'and an unnamed night opens the dialog as the way in');
  h.data.tournament.id='t0';
  h.render=()=>{};
  const dialog = {getAttribute: () => 'settings-form', classList: {contains: () => false}, querySelectorAll: () => [],
    values: {name: 'Friday', format: 'singles', tables: '3', raceTo: '7'}};
  await h.handlers.submit({preventDefault() {}, target: dialog});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name: 'tournament_setup', payload: {name: 'Friday', format: 'singles', tables: 3, raceTo: 7}}], 'the dialog reads its own form and sets the event up');
  assert.equal(h.setupOpen, false, 'and closes itself, so what it leaves is the page');
  assert.ok(!h.tonightScreen().includes('modal--start'),
    'naming the night is enough to get past the dialog, even though the draw is what mints the event id');
  assert.ok(h.tonightScreen().includes('id="entrant-form"'), 'where the first entrant can be signed in without leaving Tonight');
  assert.ok(h.tonightScreen().includes('data-action="tournament-start"'), 'and the draw is on that page, one click away');
  const door = h.startModal(true);
  assert.ok(door.includes(h.esc(h.t('save'))) && !door.includes(h.esc(h.t('startNightGo'))),
    'and that dialog saves, it does not promise to start anything');
  // The server gate, not the data alone, decides whether the scoring dashboard exists.
  (()=>{h.data.tournament.entrants=[{id:'a',members:[{pid:'p1',name:'Ana'}]},{id:'b',members:[{name:'Bo'}]}];return h.data.tournament.matches=[{id:'m1',round:1,sides:['a','b'],score:[0,0],status:'scheduled',table:null,absent:[]}]})();
  assert.equal(h.liveComp(), false, 'the event is still only registered');
  const gated = h.tonightScreen();
  assert.ok(!gated.includes('class="scoreboard"') && !gated.includes('data-action="score"'), 'so no dashboard, and no way to score, is drawn yet');
  h.data.tournament.status='active';
  assert.equal(h.liveComp(), true, 'starting the event opens the gate');
  const live = h.tonightScreen();
  assert.ok(!live.includes('class="scoreboard"') && live.includes('class="bracket-view"'),
    'round 13, owner item 6: the tab arrives with the draw, and the board stays on the timer page');
  assert.ok(h.clockScreen().includes('class="scoreboard"'), 'where the match is scored, in its own tab');
  // A free table offers the next match by number, and the send carries that number.
  h.calls.length=0;
  assert.ok(/data-action="schedule" data-id="m1"/.test(live), 'the draw offers the waiting match to a free table');
  assert.ok(live.includes(h.esc(h.t('send'))), 'and the button is the card\u2019s own Send');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'schedule', id: 'm1'}}}});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name: 'match_schedule', payload: {id: 'm1'}}], 'sending names the match - the box places it on a free table');
});
test('the draw is where a match is put on a table, and the board carries the live score (owner item 3, round 12 item 1)', () => {
  const h = harness();
  (()=>{h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:1},{id:'pb',name:'Bea',status:'Active',rating:2}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});return h.data.tournament={id:'t0',name:'Friday',format:'singles',raceTo:3,tables:3,status:'active',
      entrants:[E('a','pa','Ann'),E('b','pb','Bea'),E('c',null,'Cy'),E('d',null,'Di')],
      matches:[{id:'m1',round:1,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',table:1,absent:[]},
               {id:'m2',round:1,sides:['c','d'],score:[2,0],status:'live',table:2,absent:[]},
               {id:'m3',round:2,sides:['a','c'],score:[0,0],status:'scheduled',table:null,absent:[]}]}})();
  const grid = h.playScreen() + h.scoreboardScreen();
  assert.ok(grid.includes('class="rounds"') && grid.includes('class="bracket-view"'), 'the draw is the night\u2019s one body (round 12, owner item 1)');
  const cards = grid.split('<div class="entry bracket-card').slice(1);
  assert.equal(cards.length, 3, 'and it holds every match of the night (m1 signed, m2 on a table, m3 waiting)');
  const readyCard = cards.find(c => /data-action="schedule" data-id="m3"/.test(c));
  assert.ok(readyCard && readyCard.includes('Ann') && readyCard.includes('Cy'), 'the one match waiting for a table is sent from its own card, naming both sides');
  assert.equal(cards.filter(c => /data-action="schedule"/.test(c)).length, 1, 'one Send, on the one card that can use it');
  assert.ok(!/data-action="schedule" data-id="m1"/.test(grid) && !/data-action="schedule" data-id="m2"/.test(grid),
    'a signed or a live match is never offered a table again');
  assert.ok(/<strong class="digits">2<\/strong>/.test(grid) && grid.includes(h.esc(h.t('live'))), 'the board is the live table: its score and its word');
  assert.ok(grid.includes('Di') && grid.includes('data-action="score"') && grid.includes('data-action="sign"'), 'and it is scored and signed there');
  assert.ok(!/class="table-card/.test(grid), 'and no card anywhere is a card of a table (owner item 3)');
  // Round 13, owner item 5: the field is still in old documents, and the console ignores it.
  h.data.tournament.matches[2].absent=['a'];
  assert.ok(/data-action="schedule" data-id="m3"/.test(h.playScreen()),
    'attendance no longer holds a match back: anyone can be sent to a table');
});

// --- Round 2 (impeccable audit, 2026-10-03) ---------------------------------
// Every defect the audit measured and this round fixed gets an assertion here, so the
// state that was wrong cannot come back silently.
const opsCss = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
const opsHtml = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
const boardCss = fs.readFileSync(path.join(__dirname, '../annotator/board.css'), 'utf8');

test('round 2: the audit log says what happened in words, in both languages (B-01)', () => {
  const h = harness();
  const actions = ['event_backfill', 'match_complete', 'match_unschedule', 'note_delete'];
  for (const action of actions) {
    for (const lang of ['en', 'zh']) {
      const label = (()=>{h.lang=(lang);return h.auditActions[JSON.parse(JSON.stringify(action))]?.[h.lang==='zh'?1:0]})();
      assert.ok(label && label !== action, `${action} is a sentence in ${lang}, not the backend enum`);
    }
  }
  const line = (()=>{h.lang='en';return h.auditLine({action:'event_backfill',createdAt:'2026-10-03T05:23:40.400503+00:00',revision:75})})();
  assert.ok(line.includes('Backfilled from a VOD'), 'a backfilled night reads as that, not as event_backfill');
  assert.ok(!/event_backfill/.test(line), 'and the raw enum never reaches the operator');
  assert.ok(line.includes('v75'), 'the revision still rides along');
});

test('round 2: every instant on Records is formatted the one way (B-02)', () => {
  const h = harness();
  recordsNight(h);
  (()=>{h.data.history[0].signOff={at:'2026-09-21T03:15:00Z'};return h.data.events.push({id:'e2',action:'event_backfill',createdAt:'2026-10-03T05:23:40.400503+00:00',revision:75,context:{id:'h1'}})})();
  const rec = (()=>{h.lang='en';return h.recordsScreen()})();
  const said = h.dateLine('2026-09-21T03:15:00Z');
  assert.ok(rec.includes(said), `the sign-off instant is printed the way the audit log prints it (${said})`);
  assert.ok(!rec.includes('2026-09-21T03:15:00Z'), 'and never as a raw ISO stamp');
  assert.ok(!rec.includes('.400503'), 'no microseconds anywhere on the screen');
});

test('round 2: Records is navigable by heading (B-03, B-13)', () => {
  const h = harness();
  recordsNight(h);
  const rec = (()=>{h.lang='en';return h.recordsScreen()})();
  assert.ok(/<h2[^>]*>/.test(rec) && /<h3 class="tl-year">/.test(rec) && /<h3 class="tl-month-head">/.test(rec),
    'the page, the year and the month are all heading levels (h2, h3, h3)');
  assert.ok(!/十月/.test(rec) && !/九月/.test(rec), 'in EN no Chinese month rides along');
  const monthHead = h.monthLabel(h.eventDate(h.data.history[0]));
  assert.ok(rec.includes(`class="tl-month-head">${monthHead}<`), `the month heads as ${monthHead} alone, with no second script`);
  assert.ok(/<h3 class="tl-year">2026<\/h3>/.test(rec), 'and the year is a heading, not a styled list item');
  assert.ok(opsCss.includes('.tl-month-head{') && !/[^-]\btl-month\{/.test(opsCss), 'the old non-heading month class is gone from the stylesheet');
});

test('round 2: Regulars has a heading, and the night\u2019s one list is named for its content (B-13, B-12)', () => {
  const h = harness();
  recordsNight(h);
  const players = (()=>{h.lang='en';return h.playersScreen()})();
  assert.ok(/<h2[^>]*>\s*/.test(players) && players.includes(h.esc(h.t('players'))), 'Regulars has an h2 of its own');
  h.lang='zh';
  assert.ok(h.esc(h.t('bracketTitle')) === '对阵表', 'round 12: the queue panel is gone, and the night\u2019s one list is headed by the draw\u2019s own word');
  assert.ok(!source.includes("t('queueTitle')"), 'and the word the old panel used went with it');
});

test('round 2: the disclosure marker is authored, and the list reset covers every fold (B-04, B-07)', () => {
  assert.ok(/#ops-shell details\.panel>summary\{[^}]*list-style:none/.test(opsCss), 'a flex summary suppresses ::marker, so it is switched off on purpose');
  assert.ok(/#ops-shell details\.panel>summary::before\{content:'▸'/.test(opsCss), 'and an authored marker replaces it');
  assert.ok(/#ops-shell details\.panel\[open\]>summary::before\{content:'▾'/.test(opsCss), 'which turns over when the panel opens');
  assert.ok(/#ops-shell \.tl-audit>summary\{[^}]*list-style:none/.test(opsCss), 'the night’s log switches ::marker off on the summary, which is where the marker lives');
  assert.ok(/#ops-shell \.tl-audit>summary::-webkit-details-marker\{display:none\}/.test(opsCss), 'and Chrome’s own triangle goes with it');
  assert.ok(/#ops-shell \.tl-audit>summary::before\{content:'▸'/.test(opsCss), 'so the log folds carry the same authored chevron as the panels');
  assert.ok(/#ops-shell \.tl-audit\[open\]>summary::before\{content:'▾'\}/.test(opsCss), 'which turns over when a night opens');
  assert.ok(!/\.audit,#ops-shell \.tl-audit\{list-style:none/.test(opsCss), 'and the details is out of the list reset: naming it there never touched a summary');
  assert.ok(/#ops-shell details\.panel>summary::-webkit-details-marker\{display:none\}/.test(opsCss), 'and the browser’s own triangle is switched off for that summary');
});

test('round 2: the small toggles are still tappable at phone width (B-08)', () => {
  const phone = opsCss.slice(opsCss.indexOf('@media(max-width:750px)'));
  // Round 19, owner item 4: the collapse triangle is gone, so the phone target rules went with it.
  // What a phone must still reach is the card's own actions.
  assert.ok(!phone.includes('.card-toggle'), 'no dead triangle rule is left in the phone block');
  assert.ok(/#ops-shell \.bracket-card[^{]*\{[^}]*min-height:44px/.test(phone) || phone.includes('.match-controls'), 'the card and its actions keep a thumb-sized target');
});

test('round 2: the board’s bracket text keeps the console’s 11 px floor (B-06)', () => {
  assert.ok(/--tv-xs:11px/.test(boardCss), 'the floor is one token');
  assert.ok(/\.rounds\[data-rows="some"\]\{font-size:max\(\.8rem,var\(--tv-xs\)\)\}/.test(boardCss), 'the some-rows step clamps to the absolute floor');
  assert.ok(/\.rounds\[data-rows="many"\]\{font-size:max\(\.62rem,var\(--tv-xs\)\)\}/.test(boardCss), 'and so does the many-rows step');
  assert.ok(/\.round h3\{font-size:max\(\.8em,var\(--tv-xs\)\)\}/.test(boardCss), 'the round headings no longer resolve to 10.24 px');
  assert.ok(/\.bm-note\{font-size:max\(\.75em,var\(--tv-xs\)\)\}/.test(boardCss), 'nor the match notes to 9.6 px');
  assert.ok(!/--tv-min/.test(boardCss), 'and the floor stays absolute: a share of the parent size measured above the design at a 24 px root');
});

test('round 2: the shot timer has exactly one home, in the bar (B-§13.1)', () => {
  const h = harness();
  (()=>{h.data.tournament={id:'t0',name:'Tonight',format:'singles',raceTo:3,tables:2,status:'active',entrants:[{id:'a',members:[{pid:'pa',name:'Ann'}]},{id:'b',members:[{pid:'pb',name:'Bea'}]}],matches:[{id:'m1',round:1,sides:['a','b'],score:[0,0],status:'live',table:1,absent:[]}]};h.data.players=[];return h.render=()=>{}})();
  const board = h.scoreboardScreen();
  assert.ok(!/data-clock/.test(board), 'neither the floor nor the scoreboard draws a clock of its own — the bar’s slot is the one home');
  assert.equal((h.clockHTML().match(/data-clock/g) || []).length, 1, 'the bar’s slot renders exactly one clock, with its own controls');
  assert.ok(/data-action="clock-toggle"/.test(h.clockHTML()) && /data-action="clock-reset"/.test(h.clockHTML()), 'and the controls live in the slot, not on the scoreboard');
  assert.equal((opsHtml.match(/data-clock-host/g) || []).length, 1, 'ops.html declares one timer host');
  assert.ok(!/#strip/.test(opsHtml) && !/#strip/.test(opsCss), 'and the row that held the second copy is gone from the markup and the stylesheet');
  assert.ok(!/score-top \[data-action=clock/.test(opsCss) && !/clock-toggle\]\{margin-left:auto/.test(opsCss), 'the scoreboard clock controls that only the second copy used are gone too');
});

test('round 2: the night’s name carries a step over its own metadata (B-15)', () => {
  assert.ok(/#ops-shell \.tl-title\{[^}]*font:600 var\(--fs-lg\)\/1\.25 var\(--display\)/.test(opsCss), 'the title takes the display face at a real step up');
  assert.ok(/#ops-shell \.tl-title\{[^}]*text-transform:none/.test(opsCss), 'and stops shouting in uppercase, which is what left it identical to its metadata');
  assert.ok(/#ops-shell \.tl-title small\{[^}]*font:var\(--fs-xs\) var\(--mono\)/.test(opsCss), 'while the metadata keeps the mono face');
  assert.ok(/#ops-shell \.tl-title small\{[^}]*text-transform:uppercase/.test(opsCss), 'and the uppercase treatment that marks it as meta');
});

// ---- Round 3, lane r3a: the blind rater's F4, F5, F6, F9, F12, F14–F19 (docs/console-redesign.md §14).
test('round 3 / F4 + F6: the race reads the same everywhere, and one 中文 word means Racked', () => {
  const h = harness();
  tonightNight(h, 'drawn');
  h.lang='zh';
  assert.equal(h.t('scheduled'), '已排定', 'F6: a match waiting for a table says 已排定');
  assert.ok(!/sceneRack/.test(source), 'F6: the stage stepper went with the four-word track (owner item 2), so the one word cannot drift');
  assert.equal(h.t('send'), '安排上台', 'F6: 安排上台 stays the only word for putting a match on a table');
  const tonight = h.tonightScreen();
  assert.ok(tonight.includes('已排定'), 'F6: the waiting match and the stepper render it');
  assert.ok(!/已排台|开台/.test(tonight), 'F6: no second word for the same stage survives anywhere on the page');
  assert.equal(h.t('race'), '抢几', 'F4: 抢几 survives as the field label');
  h.data.tournament.raceTo=5;
  const board = h.scoreboardScreen();
  assert.ok(board.includes('<span class="badge race">抢5</span>'), 'F4: the chip renders 抢{n}, exactly as the header strip does');
  assert.ok(!/抢几/.test(board), 'F4: the field label never leaks into the chip');
  h.lang='en';
  assert.equal(h.t('scheduled'), 'Racked', 'F6: English keeps Racked for the one word that is left');
  assert.ok(h.scoreboardScreen().includes('<span class="badge race">Race to 5</span>'), 'F4: and English reads Race to 5');
});

test('round 3 / F5: the backfilled-night marker is a control, not text dressed as one', () => {
  const h = harness();
  (()=>{h.lang='en';h.openEvents.clear();
    h.data.history=[{id:'n1',name:'Wednesday 8-Ball Open',archivedAt:'2026-09-17T00:00:00Z',entrants:[{id:'a',members:[{pid:'pa',name:'Ann'}]}],matches:[],source:{kind:'vod-backfill',vodId:'1',startS:0,endS:60}}];return h.data.events=[]})();
  const rec = h.recordsScreen();
  assert.ok(rec.includes('<button type="button" class="badge tl-source-badge" data-action="backfill-open">Backfill from a VOD</button>'),
    'F5: it is a real button wearing the same badge class, so it can carry the row style without reading as a primary button');
  assert.ok(rec.includes('data-action="tl-toggle"'), 'F5: and the row still has its own Expand control beside it');
  assert.ok(h.actions().includes('backfill-open'), 'F5: the one click handler already routes that action');
});

test('round 3 / F9: both search boxes carry a real accessible name that states its scope', () => {
  const h = harness();
  (()=>{h.lang='en';h.data.history=[{id:'n1',name:'Wednesday 8-Ball Open',archivedAt:'2026-09-17T00:00:00Z',entrants:[],matches:[]}];h.data.events=[];
    h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:700}];return h.render=()=>{}})();
  assert.ok(h.recordsScreen().includes('id="events-search" placeholder="Search" aria-label="Search the records"'),
    'F9: the records box names the archive it searches');
  assert.ok(h.playersScreen().includes('id="roster-search" placeholder="Search" aria-label="Search the regulars roster"'),
    'F9: the roster box names the roster');
  h.lang='zh';
  assert.ok(h.recordsScreen().includes('aria-label="搜索赛事记录"'), 'F9: 中文 names the scope too');
  assert.ok(h.playersScreen().includes('aria-label="搜索常客名单"'), 'F9: both boxes, both languages');
  assert.equal(h.t('search'), '搜索', 'F9: the placeholder stays a hint; the aria-label is the name');
});

test('round 3 / F12: the honesty note leaves the individual panels and stays where the system is described', () => {
  const h = harness();
  (()=>{h.lang='en';h.data.history=[];return h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:700,played:1,wins:1,losses:0}]})();
  const note = h.esc(h.t('noSimulation'));
  assert.equal((source.match(/noSimulation/g) || []).length, 2, 'F12: the sentence survives once, in the words and in one screen');
  assert.ok(!h.recordView(h.data.players[0]).includes(note), 'F12: an individual record no longer carries a system-wide claim');
  assert.ok(!h.playersScreen().includes(note), 'F12: nor the Regulars panel behind it');
  assert.ok(h.statusScreen().includes(note), 'F12: the Back room still says it, where the whole system is described');
});

test('round 3 / F14: End of the night is on the Back room in every state, with the forbidden button disabled and explained', () => {
  const h = harness();
  (()=>{h.lang='en';return h.render=()=>{}})();
  (()=>{h.data.tournament={raceTo:7,entrants:[],matches:[]};return h.data.history=[]})();
  assert.ok(!h.tonightScreen().includes('data-action="event-delete"'),
    'F14: with no event at all the screen is the dialog, and nothing offers to delete what does not exist');
  const states = [
    ['an empty registration', h => { h.data.tournament={id:'t0',status:'registration',raceTo:7,entrants:[],matches:[]};h.data.history=[] }, h.t('closeNoEntrants'), false],
    ['a registration with entrants', h => { h.data.tournament={id:'t0',status:'registration',raceTo:7,entrants:[{id:'a',members:[{pid:'pa',name:'Ann'}]}],matches:[]};h.data.history=[] }, null, true],
    ['a night with a signed result', h => { h.data.tournament={id:'t0',status:'active',raceTo:7,entrants:[{id:'a',members:[{pid:'pa',name:'Ann'}]}],matches:[{id:'m1',round:1,sides:['a',null],score:[3,0],status:'complete',result:'played',winnerId:'a',absent:[]}]};h.data.history=[] }, h.t('closeSigned'), false],
  ];
  for (const [name, setup, why, deletable] of states) {
    setup(h);
    const html = h.tonightScreen();
    const end = html.slice(html.indexOf('class="end-night"'));
    assert.ok(html.includes('class="end-night"') && end.includes('data-action="new-event"'),
      `F14: the event card carries the night\u2019s end with ${name} (round 13, owner item 3: the Back room no longer does)`);
    assert.ok(end.includes('data-action="event-delete"'), `F14: and it always carries the delete control (${name})`);
    assert.equal(!/data-action="event-delete"[^>]*disabled/.test(end), deletable, `F14: delete is ${deletable ? 'live' : 'off'} with ${name}`);
    if (why) assert.ok(end.includes(h.esc((why))), `F14: the disabled button says why (${name})`);
    else assert.ok(!/class="note close-why"/.test(end), `F14: nothing is explained away when the state allows it (${name})`);
  }
  h.data.tournament={id:'t0',status:'active',raceTo:7,entrants:[],matches:[]};
  const card = h.eventCard();
  assert.ok(!/archive this event to start/.test(card), 'F14: the night card is a summary and a door, with no stale instruction');
  assert.ok(h.startModal(true).includes(h.esc(h.t('locked'))),
    'F14: and the locked note travels with the settings dialog, where the name is edited');
  for (const lang of ['en', 'zh']) {
    h.lang=(lang);
    assert.ok(h.t('locked').length > 10, `F14: the ${lang} note still says where the night is finished`);
  }
  (()=>{h.lang='en';return h.data.tournament={id:'',name:'Friday 8-ball',format:'singles',raceTo:5,tables:2,status:'registration',entrants:[],matches:[]}})();
  h.data.tournament.entrants=[{id:'x',members:[{name:'A'}]}];
  // Round 19, owner item 1: the competition's name is the card's own heading too, so it reads on both.
  assert.ok(h.scene().includes('Friday 8-ball') && h.eventCard().includes('Friday 8-ball'),
    'F14: the name reads on the scene line and, since round 19, on its own card');
});

test('round 3 / F15 + F16: the balls are shortcuts, and the timer ball names itself', async () => {
  const h = harness();
  tonightNight(h, 'drawn');
  h.render=()=>{};
  assert.equal(h.navKey(1), 'clock', 'F15: ball 1 is the shot timer');
  assert.equal(h.primaryNav().map((k,i)=>h.navKey(i+2)).join(), 'tonight,records,vision,players,status', 'F15: balls 2–6 are the five destinations, in order');
  assert.equal(h.navKey(7), null, 'F15: and there is no seventh ball');
  // A real keyboard sends key:'3' with code:'Digit3' — the rater's own probe printed exactly that — so the
  // handler reads the code first and falls back to the bare digit.
  const key = (n, extra = {}) => ({key: String(n), code: `Digit${n}`, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, preventDefault() {}, ...extra});
  await h.handlers.keydown(key(3));
  assert.equal(h.tab, 'records', 'F15: Digit3 switches to Records');
  assert.equal(h.context.location.hash, '#/records', 'F15: and the URL follows');
  await h.handlers.keydown(key(4, {ctrlKey: true}));
  assert.equal(h.tab, 'records', 'F15: a modifier makes it a browser shortcut, not ours');
  h.context.document.activeElement = {tagName: 'TEXTAREA'};
  await h.handlers.keydown(key(5));
  assert.equal(h.tab, 'records', 'F15: typing in a field is never a shortcut');
  h.context.document.activeElement = {tagName: 'DIV'};
  await h.handlers.keydown(key(5));
  assert.equal(h.tab, 'players', 'F15: outside a field the same key works');
  delete h.context.document.activeElement;
  (()=>{h.timer.duration=30;h.timer.remaining=30;return h.timer.deadline=null})();
  await h.handlers.keydown(key(1));
  assert.ok(!!h.timer.deadline, 'F15: Digit1 starts the shot timer, which is not a tab at all');
  await h.handlers.keydown(key(1));
  assert.ok(!h.timer.deadline, 'F15: pressing it again pauses');
  // The shot clock is shared: clock-sync.js turns a click on that button into POST /api/clock, so the key has
  // to reach the control. Calling clockToggle() behind its back started the clock on this screen only and the
  // next server push silently undid it — measured in the browser, the deadline was rewritten 0.72 s later.
  const wasQuery = h.context.document.querySelector, clicks = [];
  h.context.document.querySelector = selector => selector === '#ops-shell [data-action="clock-toggle"]'
    ? {click() { clicks.push(selector); }} : wasQuery(selector);
  (()=>{h.timer.remaining=30;return h.timer.deadline=null})();
  await h.handlers.keydown(key(1));
  assert.deepEqual(clicks, ['#ops-shell [data-action="clock-toggle"]'],
    'F15: the timer key presses the control, so every listener a mouse reaches runs too');
  assert.ok(!h.timer.deadline, 'F15: and the clock is not toggled a second time behind it');
  h.context.document.querySelector = wasQuery;
  await h.handlers.keydown({key: '2', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, preventDefault() {}});
  assert.equal(h.tab, 'tonight', 'F15: a bare digit with no code still works, as plenty of tooling sends it');
  await h.handlers.keydown({code: 'Digit3', preventDefault() {}});
  assert.equal(h.tab, 'records', 'F15: and so does a code with no key');
  assert.ok(source.includes('aria-keyshortcuts="Digit${key}"') && source.includes("t('keyHint')"), 'F15: every ball names its key in the markup');
  assert.ok(/aria-keyshortcuts="Digit1"[^>]*title=/.test(h.clockNavButton()), 'F15: and the timer names its own key');
  const slot = h.clockNavButton();
  assert.ok(slot.includes('data-tab="clock"') && slot.includes('aria-keyshortcuts="Digit1"'),
    'round 7 / owner item 2 (his ruling): ball 1 is the timer own destination, in the nav like every other');
  assert.ok(slot.includes('<i>1</i>') && slot.includes('aria-hidden="true" class="ball"') && slot.includes('Shot timer'),
    'F16 + owner item 4: inside the item the ball is decorative and the word names it - the number is never read as a count of shots');
  assert.ok(slot.includes('class="ball" style="--ball-c:#f2c14e"'),
    'round 8: the face keeps ballHTML\'s sphere intact - a rewrite that drops the class attribute\'s closing quote '
    + 'swallows the style attribute, --ball-c goes undefined and an unfallback var() paints the base with no band');
  h.tab='clock';
  assert.ok(h.clockNavButton().includes('class="active"') && h.clockNavButton().includes('aria-current="page"'),
    'and it marks itself as the current tab when you are on it');
  h.tab='tonight';
});

test('round 3 / F17 + round 5 owner item 1: backfill is an entry point where the archive is, not in every page\'s header', () => {
  assert.ok(!opsHtml.includes('id="backfill-open"'), 'owner item 1: no backfill control in the shared header - it was on every tab');
  assert.ok(!source.includes('backfillButton'), 'and render() no longer paints one');
  assert.ok(!source.includes("$('#backfill-open')"), 'nothing looks for one either');
  // The three Records-scoped entries stay: the button on the archive list, the empty-history
  // invitation, and the per-night badge a backfilled night carries.
  assert.ok(source.includes("btn(t('backfillOpen'),'backfill-open','','primary')"), 'the archive list keeps its own backfill button');
  assert.ok(source.includes("emptyNote('emptyHistory','backfill-open','backfillOpen')"), 'the empty archive still invites one');
  assert.ok(source.includes("data-action=\"backfill-open\">${esc(t('backfill'))}"), 'and a backfilled night still links back to its VOD');
  assert.ok(harness().actions().includes('backfill-open'), 'all three still open the wizard');
});

test('round 3 / F18: the “paste a VOD link first” note sits with the field it is about', () => {
  const h = harness();
  (()=>{h.lang='en';return h.bf={step:'pick',paste:'',recent:[],notice:h.t('bfNeedVod'),error:'',detail:''}})();
  const screen = h.bfScreen();
  const head = screen.indexOf('bf-head'), field = screen.indexOf('id="bf-vod"'), note = screen.indexOf('id="bf-vod-note"');
  assert.ok(head > 0 && field > head && note > field, 'F18: the note comes after the field it is about, not above the wizard heading');
  assert.ok(!screen.slice(0, field).includes('bf-notice'), 'F18: nothing warns before the field is even on screen');
  assert.ok(screen.includes('aria-describedby="bf-vod-note"'), 'F18: the field points at its own note');
  assert.equal((screen.match(/bf-notice/g) || []).length, 1, 'F18: the note is printed once, beside the field');
  assert.equal(h.bfNoticeHtml(true), '', 'F18: the copy above the steps is suppressed while the field carries it');
  assert.ok(h.bfNoticeHtml(false).includes('bf-notice'), 'F18: while a later step still announces it at the top');
});

test('round 3 / F19: the wizard is its own place in the nav, and its subtitle is not the entry label again', () => {
  const h = harness();
  (()=>{h.lang='en';h.bf={step:'pick',paste:'',recent:[],notice:''};return h.tab='records'})();
  const screen = h.bfScreen();
  assert.ok(!screen.includes(h.esc(h.t('backfillOpen'))), 'F19: the step subtitle never repeats the entry button label, ellipsis and all');
  assert.ok(screen.includes(h.esc(h.t('bfPickNote'))), 'F19: it says what the step does instead');
  assert.ok(source.includes('const cur=!bf&&tab===k'), 'F19: while the wizard is open no destination is marked current in the bar');
  assert.ok(/\(!bf&&tab===id\?' aria-current="page"':''\)/.test(source), 'F19: nor in the 390 tab bar');
  assert.ok(/dataset\.tab=bf\?'backfill':tab;/.test(source), 'F19: and the shell publishes the wizard as its own state, so the layout can drop the tab bar');
  const fresh = harness();
  assert.equal((fresh.tabbarHTML().match(/aria-current="page"/g) || []).length, 1, 'with no wizard open exactly one destination stays current');
});

test('round 4 / rater 1: a name with a quote reaches every surface escaped exactly once', () => {
  const h = harness();
  (()=>{h.data.players=[{id:'p1',name:'Wei "Stone" Zhang',rating:500}];return h.data.tournament={id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
    entrants:[{id:'e1',members:[{pid:'p1',name:null}]},{id:'e2',members:[{pid:null,name:'Jordan Pike'}]}],
    matches:[{id:'m1',round:1,sides:['e1','e2'],score:[1,0],status:'live',table:1,absent:[]}]}})();
  const bracket = h.bracketScreen();
  assert.ok(bracket.includes('Wei &quot;Stone&quot; Zhang'), 'the bracket shows the name as text, not as an entity');
  assert.ok(!bracket.includes('&amp;quot;'), 'the bracket never escapes a name twice');
  assert.ok(bracket.includes('aria-label="Wei &quot;Stone&quot; Zhang – Jordan Pike · On table"'), 'nor does the card\u2019s accessible name');
  const queue = h.playScreen();
  assert.ok(queue.includes('Wei &quot;Stone&quot; Zhang') && !queue.includes('&amp;quot;'), 'the queue is escaped exactly once');
  const board = h.scoreboardScreen();
  assert.ok(board.includes('Wei &quot;Stone&quot; Zhang') && !board.includes('&amp;quot;'), 'so is the board\u2019s line');
  const records = h.recordsScreen();
  assert.ok(!records.includes('&amp;quot;'), 'and no other screen doubles an entity');
  assert.ok(!/esc\(sideName\(/.test(source.replace(/esc\(sideName\(m,m\.sides\[0\]\)\)/g, '').replace(/esc\(sideName\(m,m\.sides\[1\]\)\)/g, '').replace(/esc\(sideName\(m,m\.winnerId\|\|m\.sides\[0\]\)\)/g, '').replace(/esc\(sideName\(m,id\)\)/g, '')),
    'sideName returns text: every remaining insertion point escapes it itself');
});

// ---- Owner round 5 (2026-10-03): the eight items sent after round 3 shipped. The assertions are
// written in the terms the shipped file is written in - the nav's first child, the palette by ball
// number, the one action a card keeps - so a later refactor cannot quietly put the brand, the extra
// Save, the header Backfill button or the sync sentence back.

test('round 5 / owner item 2: the browser chrome carries the work, not the brand', () => {
  const svg = fs.readFileSync(path.join(__dirname, '../annotator/favicon.svg'), 'utf8');
  assert.ok(!/>8</.test(svg) && !/<text/.test(svg), 'the 8-ball mark is gone from the icon, not recoloured');
  assert.ok(svg.includes('stroke="#c8a04a"') && svg.includes('<path d="M32 11 53 32 32 53 11 32Z"'), 'the rail diamond replaces it');
  assert.equal((svg.match(/<circle/g) || []).length, 1, "the only circle left is the diamond's centre dot");
  for (const [file, title] of [['ops.html', 'Operations'], ['app.html', 'Review workbench'], ['board.html', 'Tonight']]) {
    const page = fs.readFileSync(path.join(__dirname, '../annotator/' + file), 'utf8');
    assert.ok(page.includes(`<title>${title}</title>`), `${file}: the tab is named for the work`);
    assert.ok(!/<title>[^<]*Corner Pocket/.test(page), `${file}: no wordmark in the browser chrome`);
  }
  // The rasters were regenerated from the same geometry, so their sizes still match every icon link.
  for (const [file, w, h] of [['favicon-32.png', 32, 32], ['favicon-16.png', 16, 16]]) {
    const png = fs.readFileSync(path.join(__dirname, '../annotator/' + file));
    assert.equal(png.readUInt32BE(16), w, `${file} is ${w}px wide`);
    assert.equal(png.readUInt32BE(20), h, `${file} is ${h}px tall`);
  }
  const ico = fs.readFileSync(path.join(__dirname, '../annotator/favicon.ico'));
  assert.equal(ico.readUInt16LE(0), 0, 'the .ico is a real icon file');
  assert.equal(ico.readUInt16LE(2), 1, 'of the icon type');
  assert.equal(ico.readUInt16LE(4), 3, 'with the three sizes a browser picks from');
  const board = fs.readFileSync(path.join(__dirname, '../annotator/board.html'), 'utf8');
  assert.equal((board.match(/Corner Pocket/g) || []).length, 1,
    "the public board keeps the club's name once, in its masthead - the owner has not ruled on that line");
});

test('round 5 / owner item 3: the ball map is recorded, and every ball the nav draws follows it', () => {
  const h = harness();
  assert.deepEqual(JSON.parse(JSON.stringify(h.primaryNav().map((k,i)=>[h.ballNumber(i+2),h.ballColor(i+2),h.ballStripe(i+2)]))),
    [[2, '#2f6fd0', 0], [3, '#c8382f', 0], [4, '#e885ad', 0], [5, '#e07a29', 0], [6, '#2f8f4e', 0]],
    'the five destinations are balls 2-6, solids: the timer is ball 1');
  assert.equal(h.ballColor(1), '#f2c14e', 'owner item 3: ball 1 is yellow');
  assert.equal(h.ballColor(7), '#8a5a2b', 'ball 7 is brown');
  const doc = fs.readFileSync(path.join(__dirname, '../docs/console-redesign.md'), 'utf8');
  for (const [n, word, hex] of [[1, 'yellow', '#f2c14e'], [2, 'blue', '#2f6fd0'], [3, 'red', '#c8382f'], [4, 'pink', '#e885ad'],
    [5, 'orange', '#e07a29'], [6, 'green', '#2f8f4e'], [7, 'brown', '#8a5a2b'], [8, 'black', '#1b1b1b']]) {
    assert.ok(new RegExp(`\\|\\s*${n}\\s*\\|[^|]*${word}[^|]*\\|[^|]*${hex}`, 'i').test(doc),
      `the contract records ball ${n} as ${word} (${hex}), so the code is not the only record`);
  }
  assert.ok(/9[^|]*15[^|]*stripe/i.test(doc), 'and says what 9-15 are: the same hues, striped');
});

test('round 7 / owner item 2: the timer is a bar of its own and ball 1 is its own door', () => {
  const h = harness();   // an idle venue: no tournament, no draw, nothing running
  const bar = h.clockHTML();
  assert.ok(bar.includes('data-clock') && bar.includes('data-action="clock-toggle"') && bar.includes('data-action="clock-reset"'),
    'the bar holds the live clock and its controls, so it keeps working on every other tab');
  assert.ok(!bar.includes('data-tab=') && !bar.includes('timer-tab') && !/class="ball/.test(bar),
    'and it is not a tab: no ball, no word, no data-tab - the owner ruled the bar and the tab apart');
  const door = h.clockNavButton();
  assert.ok(door.includes('data-tab="clock"') && door.includes('--ball-c:#f2c14e') && door.includes('Shot timer'),
    "ball 1 in the nav opens the timer's own screen, and the word names it");
  assert.equal((h.tabbarHTML().match(/class="tabbar-ball"/g) || []).length, 6,
    "and the phone's bottom bar carries all six, ball 1 included");
  // Round 5 hid the word and Reset below 1152 px so six items would fit one row at 1024 (measured:
  // 104 px in two rows). Round 7 gives the timer a row of its own, so that trade is over for good.
  const narrow = opsCss.slice(opsCss.indexOf('@media (max-width:1151.98px)'), opsCss.indexOf('@media(max-width:750px)'));
  assert.ok(!narrow.includes('timer-tab-label{display:none}') && !narrow.includes('clock-reset"]{display:none}'),
    'below 1152 the word and Reset stay: the timer has its own row now');
  const phoneBlock = opsCss.slice(opsCss.indexOf('@media (max-width:750px)'));
  assert.ok(phoneBlock.includes('#ops-shell .clockbar .presets{display:none}') && !phoneBlock.includes('timer-tab-label'),
    'and on the phone the bar drops the presets, keeping the clock, Start and Reset');
  assert.ok(opsHtml.indexOf('class="barrow"') < opsHtml.indexOf('class="clockbar"') && opsHtml.indexOf('</nav>') < opsHtml.indexOf('class="tools"'),
    'the shell is two rows: the destinations and the tools, then the clock - round 8 (owner item 1) turned round 7\'s order around');
  assert.ok(source.includes("$('#ops-shell .clockbar')"), 'and render() paints that one host');
  // Round 12 (owner item 2) put the match on the timer's own page. The bar and the repaint loop
  // keep round 7's rule - they read no match state, so they paint in every venue state and before
  // the first fetch answers - and the page's one match read is asserted to be exactly one block.
  const noState = (region, name) => {
    const stripped = region.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
    assert.ok(!/comp\(\)|liveComp\(\)|tournament\(\)/.test(stripped),
      `${name} reads no match state, so the clock is usable with no competition running`);
  };
  noState(source.slice(source.indexOf('function clockHTML()'), source.indexOf('function clockScreen()')), 'the clock bar and its host');
  noState(source.slice(source.indexOf('function tick()'), source.indexOf('const screenModules=')), 'the repaint loop');
  const page = source.slice(source.indexOf('function clockScreen()'), source.indexOf('function tick()'));
  assert.ok(page.includes("${liveComp()?scoreboardScreen():''}"), 'the timer page carries the match block (round 12, owner item 2)');
  assert.equal((page.match(/liveComp\(\)/g) || []).length, 1, 'and reads match state exactly once, for that block');
  noState(page.slice(0, page.indexOf('${liveComp()?')), 'the timer card');
  const screen = h.clockScreen();
  assert.ok(screen.includes('data-clock') && screen.includes('data-action="clock-toggle"') && screen.includes('data-action="clock-reset"'),
    'its own screen starts, pauses and resets');
  assert.deepEqual(JSON.parse(JSON.stringify([...h.clockScreen().matchAll(/data-value="(\d+)"/g)].map(m=>m[1]))),
    ['20', '30', '45', '60'], 'with the same four durations as the bar');
  assert.ok(screen.includes('class="timer-face"') && screen.includes('class="timer-progress"') && screen.includes('data-progress'),
    'a large face and a progress rail, and nothing else competing with the time');
  assert.ok(!screen.includes('clockNotice') && h.t('clockNotice') === 'clockNotice',
    'owner item 3: the note is gone from the screen and from the words file');
  assert.equal((source.match(/clockNotice/g) || []).length, 0, 'and nothing else prints it either');
  assert.equal(h.routeOf('#/clock'), 'clock', 'a deep link reaches it');
  assert.equal(h.navLabel('clock'), 'Shot timer', 'and it is named in the nav');
  h.lang='zh';
  assert.equal(h.navLabel('clock'), '出杆计时', 'in either language');
  h.lang='en';
  assert.ok(opsHtml.includes('class="clockbar" role="group" aria-label="Shot timer / 出杆计时" data-clock-host'),
    'the shell ships one host, named, empty until ops.js paints it');
});

test("round 5 / owner item 5: the Scorekeeper's card has one action, and it is Sign", () => {
  const h = harness();
  tonightNight(h, 'drawn');
  // The card shows the match that is on a table; 'drawn' has none live yet.
  assert.ok(!h.tonightScreen().includes('id="score-form"'), 'the manual scorecard is gone (owner item 3): the board is the scorer');
  (()=>{h.data.tournament.matches[1].status='live';return h.data.tournament.matches[1].table=2})();
  const board = h.scoreboardScreen();
  // Round 19, owner item 5: the board carries the score controls always, and offers the sign-off only
  // once a winner exists - a tied score shows the wait instead.
  assert.ok(board.includes('data-action="score"') && (board.includes('data-action="sign"') || board.includes('sign-wait')),
    'a live match is scored and signed on the board, and nowhere else');
  assert.ok(/class="digits"/.test(board), 'and the board carries the score itself');
  assert.ok(!/score-form/.test(source), 'no code path anywhere still looks for a manual score line');
  const settings = h.setupForm(false);
  assert.ok(settings.includes(`<button class="primary">${h.esc(h.t('save'))}</button>`),
    "the settings dialog keeps its Save: that form belongs to the night, not to the scorecard");
  const firstNight = h.setupForm(true);
  assert.ok(firstNight.includes(h.esc(h.t('startNightGo'))) && !firstNight.includes(h.esc(h.t('save'))),
    'while a night that does not exist yet is asked to start, not to save');
});

test('round 5 / owner item 6: the timer bar never narrates its own sync state', () => {
  const {statusText, LABELS} = clockSync;
  assert.equal(statusText('live', 'en', ''), '', 'live says nothing');
  assert.equal(statusText('connecting', 'en', ''), '', 'and neither does connecting');
  assert.equal(statusText('offline', 'zh', ''), '', 'nor offline: the time on screen is the message');
  assert.equal(statusText('polling', 'en', ''), '', 'and nor a reconnect');
  assert.equal(statusText('live', 'en', 'clock command failed — nothing changed'), 'clock command failed — nothing changed',
    'only a failure speaks, and it is the sentence ops.js handed in');
  assert.deepEqual(Object.keys(LABELS.en).sort(), ['busy', 'failed'],
    'the label map holds two failures and no name: the shot timer has one name, defined in ops.js');
  for (const dead of ['showing last known', 'live · synced', '实时 · 已同步', 'connecting…', 'connecting...', 'reconnecting —']) {
    assert.ok(!clockSyncSource.includes(dead), `no "${dead}" copy is left in the clock's client half`);
  }
  // Round 34 / candidate 5: the failure line is the console's own node, emitted hidden while the
  // sentence is empty, and the sync half only hands the sentence over.
  assert.ok(source.includes('<span class="sync-error"' + "${clockSyncError?'':' hidden'}>" + '${esc(clockSyncError)}</span>'),
    'the console emits the line it paints, hidden while the sentence is empty');
  assert.ok(!clockSyncSource.includes("className = 'sync-error'"), 'the sync half no longer writes that node');
  assert.ok(/ERROR_MS = \d+/.test(clockSyncSource), 'and the sentence still clears itself on a timer');
});

test('round 7 / owner item 2 on the phone: the header keeps the clock, the bottom bar all six', () => {
  const h = harness();
  // Round 5 measured six labelled cells in 390 px (out/r5/probe_tabbar.py: mono uppercase needed
  // 80 px in 62 px cells). Round 7 re-measured with the body face at 11 px, and ball 1 came back:
  // 390/6 = 65 px cells hold labels of 50.1 / 57.8 / 39.5 / 29.3 / 41.8 / 50.9 px.
  const bar = h.tabbarHTML();
  assert.equal((bar.match(/class="tabbar-ball" aria-hidden="true"/g) || []).length, 6,
    'every slot stacks its destination\'s ball, and it is decorative - the word names the tab');
  const map = [[1, '#f2c14e'], [2, '#2f6fd0'], [3, '#c8382f'], [4, '#e885ad'], [5, '#e07a29'], [6, '#2f8f4e']];
  for (const [n, hex] of map) {
    assert.ok(bar.includes(`--ball-c:${hex}`), `ball ${n} draws ${hex} on the phone bar too`);
  }
  assert.ok(bar.indexOf('--ball-c:#f2c14e') < bar.indexOf('--ball-c:#2f8f4e'), 'so the bar reads left to right as 1..6');
  // The phone header keeps the clock whole - time, Start and Reset - and drops only the presets.
  const phone = opsCss.slice(opsCss.indexOf('@media (max-width:750px){'));
  assert.ok(phone.includes('#ops-shell #nav{display:none}'),
    'the phone header drops the destinations to the bar, which already lists all six');
  assert.ok(phone.includes('#ops-shell .clockbar .presets{display:none}'),
    'and the clock keeps everything but the four presets');
  // Six cells of 390/6 px: the bar's gap and the slot's padding were what pushed "Tournament"
  // (64 px at 11 px in the body face) out of its box.
  assert.ok(phone.includes('#ops-shell #tabbar{gap:0}'), 'the phone cells get the whole width');
  assert.ok(phone.includes('font:11px/1.1 var(--body)') && phone.includes('text-transform:none'),
    'and the label is the body face at 11 px, sentence case - mono uppercase needed 80 px');
});

// ---- Round 6 (owner, m04262): "make the records the timeline view of all twitch vods."
// The archive is the timeline's backbone: Records opens with every broadcast the box can see,
// each row is either a night already built (which links into the log below) or one to build
// (which opens the same backfill flow the picker uses), and nothing is inferred.
const archiveVods = [
  {id: '2890514774', title: '261001', created_at: '2026-10-03T01:30:00Z', length_s: 16455, imported: true, broadcast_type: 'ARCHIVE', thumb: '/api/vods/thumb?channel=ttpoolfriday&id=2890514774'},
  {id: '2884327358', title: '260918', created_at: '2026-09-26T01:00:00Z', length_s: 13397, imported: false, broadcast_type: 'HIGHLIGHT', thumb: ''}];
const archiveHistory = h => {
  h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:100}];
  h.data.history=[{id:'h9',name:'Friday 8-Ball',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-10-03T05:00:00Z',
    source:{kind:'twitch',vodId:'2890514774',startS:0,endS:3600},
    entrants:[{id:'a9',members:[{pid:'pa',name:'Ann'}]}],matches:[]}];
  h.data.events=[];h.data.notes=[];
  h.data.vods=[{id:'2890514774',title:'261001',channel:'ttpoolfriday',length_s:16455,created_at:'2026-10-03T01:30:00Z'}];
  h.data.links=[{vodId:'2890514774',eventId:'h9',startS:0,endS:3600,at:'2026-10-03T05:00:00Z'}]
};
test('round 6: Records opens with the Twitch archive, and every row is a built night or a night to build', async () => {
  const h = harness({hash: '#/records'});
  const asked = [], answer = {channels: [{channel: 'ttpoolfriday', error: null, saved_channels: ['ttpoolfriday'], vods: archiveVods}]};
  h.context.fetch = async url => { asked.push(url); return {ok: true, json: async () => answer}; };
  archiveHistory(h);
  await h.loadArchiveList(true);
  const screen = h.recordsScreen();
  assert.ok(screen.includes('id="archive-card"') && screen.includes('data-id="2890514774"'), 'the archive is on the Records screen itself, not a state it might reach');
  assert.ok(screen.includes(`>${h.t('records')}</h2>`), 'and the event log it feeds is still below it');
  for (const lang of ['en', 'zh']) {
    h.lang=(lang);
    const card = h.mergedTimeline(), label = key => h.esc(h.t((key)));
    assert.ok(h.recordsScreen().includes(h.esc(h.t('archiveNote'))), `${lang}: the one list says where a night comes from`);
    assert.ok(card.includes('data-action="tl-review" data-id="2890514774"'), `${lang}: a broadcast with a night is the card that opens it`);
    assert.ok(card.includes(label('vodMark')), `${lang}: and names the night that covers it`);
    assert.ok(card.includes('data-action="tl-review" data-id="2884327358"'), `${lang}: a broadcast without a night is the same card - nothing to build first (owner item 8)`);
    assert.ok(!/archiveBuild|archiveUnbuilt|bf-pick/.test(card), `${lang}: no card asks to be built outside the scrubber`);
    // The club's older nights are typed HIGHLIGHT by Twitch, their newest are ARCHIVE: the row
    // says which, in Twitch's own word for it, so a four-hour record and a one-minute clip are
    // told apart by more than the duration.
    assert.ok(card.includes(label('kindArchive')) && card.includes(label('kindHighlight')), `${lang}: each row says what Twitch calls it`);
    assert.equal((card.match(/class="tl-vod-thumb/g) || []).length, 2, `${lang}: every card carries its own picture`);
    assert.equal((card.match(/is-blank/g) || []).length, 1, `${lang}: and the one Twitch has no picture for says so`);
    assert.ok(card.includes('src="/api/vods/thumb?channel=ttpoolfriday&amp;id=2890514774"'), `${lang}: the picture is this box's route, never Twitch's`);
    assert.ok(card.indexOf('2890514774') < card.indexOf('2884327358'), `${lang}: newest first`);
    assert.ok(card.includes('class="tl-day"') && card.includes('class="tl-vods"') && /class="tl-vod[ "]/.test(card), `${lang}: one stacked row of cards per day (owner items 6 and 7)`);
  }
  h.lang='en';
  assert.deepEqual(asked, ['/api/vods/recent'], 'one read, from this box, which holds the credentials');
  assert.ok(h.recordsScreen().includes(h.t('archiveCount').replace('{n}',2).replace('{built}',1)), 'the count names the window and how much of it is linked');
  await h.loadArchiveList();
  assert.equal(asked.length, 1, 'a cached list is not read twice');
  await h.loadArchiveList(true);
  assert.equal(asked.length, 2, 'Refresh reads it again on purpose');
  assert.equal(h.calls.length, 0, 'reading the archive never writes');
});
test('round 6: a full window says there may be older ones -- the archive never claims to be complete', async () => {
  const h = harness({hash: '#/records'});
  archiveHistory(h);
  const answer = more => ({channels: [{channel: 'ttpoolfriday', error: null, more, vods: archiveVods}]});
  h.context.fetch = async () => ({ok: true, json: async () => answer(true)});
  await h.loadArchiveList(true);
  const card = h.recordsScreen();
  assert.ok(card.includes(h.esc(h.t('archiveMore').replace('{n}',2))), 'a window that filled says so, in the count of what is shown');
  assert.ok(card.includes(h.esc(h.t('archiveNote'))), 'and the note still says where a night comes from');
  h.context.fetch = async () => ({ok: true, json: async () => answer(false)});
  await h.loadArchiveList(true);
  assert.ok(!h.recordsScreen().includes(h.esc(h.t('archiveMore').replace('{n}',2))), 'a list Twitch finished sending makes no such claim');
});

test('round 6: a refused, empty or unsaved archive is a state on the page -- never a silent gap', async () => {
  const h = harness({hash: '#/records'});
  (()=>{h.data.players=[];h.data.history=[];h.data.events=[];return h.data.notes=[]})();
  h.context.fetch = async () => ({ok: false, status: 502, json: async () => ({error: 'Twitch is unreachable'})});
  await h.loadArchiveList(true);
  const broken = h.mergedTimeline();
  assert.ok(broken.includes(h.esc(h.t('archiveFailed'))) && broken.includes('Twitch is unreachable'), 'the reason is on the page');
  assert.ok(broken.includes('data-action="archive-reload"'), 'with a way to try again');
  assert.ok(!broken.includes('<li'), 'and no invented row');
  h.context.fetch = async () => ({ok: true, json: async () => ({channels: [{channel: 'ttpoolfriday', error: null, vods: []}]})});
  await h.loadArchiveList(true);
  assert.ok(h.mergedTimeline().includes(h.esc(h.t('archiveNone'))), 'a saved channel with no broadcasts says exactly that');
  assert.ok(!h.mergedTimeline().includes('<li'), 'still no rows');
  h.context.fetch = async () => ({ok: true, json: async () => ({channels: []})});
  await h.loadArchiveList(true);
  assert.ok(h.mergedTimeline().includes(h.esc(h.t('archiveNoSource'))), 'no saved channel points at the Back room');
  assert.ok(!h.mergedTimeline().includes(h.t('archiveNone')), 'and does not borrow the other sentence');
  h.lang='zh';
  assert.ok(h.mergedTimeline().includes('还没有保存 Twitch 频道'), 'the states are written in the console language, not translated on the way out');
});
test('round 6: the archive paints its own card, so a late answer never rebuilds the page under an operator', async () => {
  const painter = source.slice(source.indexOf('function paintRecords(){'), source.indexOf('function loadArchiveList('));
  assert.ok(painter.includes("const list=$('#records-list')") && painter.includes('list.innerHTML=mergedTimeline()'),
    'the loader paints the one list and returns');
  assert.ok(painter.includes("const count=$('#archive-card .archive-count')") && painter.includes('count.textContent=archiveCountText()'),
    'and the count line is written in place, so it is current after the late answer (round 11: a number that lives only in the first paint never appears)');
  assert.ok(painter.includes("const note=$('#archive-card .archive-note')") && painter.includes('note.textContent=archiveNoteText()'),
    'the sentence about what the window holds is written in place too');
  assert.ok(!painter.includes('render()'), 'still nothing rebuilds the screen under an operator');
  assert.ok(!/loadArchiveList[\s\S]{0,400}?archiveList\.loading=false;render\(\)/.test(source),
    'and never re-renders the whole screen after the network answers (the search box and the scroll survive)');
  assert.ok(source.includes("if(tab==='records'&&!bf){loadArchiveList();loadAuto()}"),
    'Records asks for the archive - and the download queue beside it - when it becomes the screen');
  // Read above, run here: Refresh is the one deliberate re-read, and the click asks for both lists.
  const refreshed = harness({richDom: true});
  const read = [];
  refreshed.context.fetch = async url => { read.push(String(url).split('?')[0]); return {ok: true, json: async () => ({channels: [], queue: []})}; };
  await refreshed.dispatch('archive-reload');
  assert.deepEqual(read, ['/api/vods/recent', '/api/vods/queue'],
    'Refresh is the one deliberate re-read, for both');
  // Read above, run here: that step is the only caller of the two, so the render that makes Records the
  // screen asks for both, and a render on any other screen asks for neither.
  const askedOn = tab => {
    const probe = harness({richDom: true});
    const asked = [];
    probe.context.fetch = async url => { asked.push(String(url).split('?')[0]); return {ok: true, json: async () => ({channels: [], queue: []})}; };
    probe.tab = tab;
    probe.render();
    return asked.sort();
  };
  assert.deepEqual(askedOn('records'), ['/api/vods/queue', '/api/vods/recent'], 'and only then');
  assert.deepEqual(askedOn('tonight'), [], 'while a render on another screen asks for neither');
});
test('round 6: Build this night opens the backfill at the broadcast the operator chose', async () => {
  const h = harness({hash: '#/records'});
  const asked = [];
  h.context.fetch = async url => { asked.push(url); return {ok: true, json: async () => ({channels: [{channel: 'ttpoolfriday', error: null, vods: archiveVods}]})}; };
  archiveHistory(h); h.render = () => {};
  await h.loadArchiveList(true);
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  assert.equal(h.bf, null, 'Records is not the backfill: nothing is open yet');
  await click({action: 'archive-reload'});
  assert.equal(asked.filter(u => String(u).includes('/api/vods/recent')).length, 2, 'Refresh reads the archive again');
  assert.equal(asked.filter(u => String(u).includes('/api/vods/queue')).length, 1, 'and reads the download queue once, beside it');
  await click({action: 'bf-pick', id: '2884327358', length: '13397', title: '260918'});
  assert.equal(h.bf.vod.id, '2884327358', 'the broadcast reaches the backfill state');
  assert.equal(h.bf.step, 'verify', 'at the step the picker itself sets, so both entrances meet');
  assert.equal(h.bf.vod.length_s, 13397, 'with the length the row carried');
  assert.equal(h.calls.length, 0, 'opening the flow writes nothing');
  await click({action: 'tl-open-night', id: 'h9'});
  assert.ok(h.openEvents.has('h9'), 'and the other control opens the built night, rather than a copy of it');
});

test('round 6: the picker lists the same archive, with the same picture, duration and kind', () => {
  // One source of truth: the archive card on Records and the backfill picker read the same
  // /api/vods/recent answer, so the operator meets the same rows in both places -- the picture
  // proxied by this box, the duration that tells a night from a clip, and Twitch's own word for
  // what the video is.
  const h = harness();
  (()=>{h.lang='en';return h.bf={step:'pick',paste:'',recent:[{channel:'ttpoolfriday',error:null,more:false,vods:JSON.parse(JSON.stringify(archiveVods))}],notice:'',error:'',detail:''}})();
  const screen = h.bfScreen();
  assert.ok(screen.includes('class="bf-thumb"') && screen.includes('src="/api/vods/thumb?channel=ttpoolfriday&amp;id=2890514774"'), 'the picker draws the same proxy picture the archive does');
  assert.ok(screen.includes('261001') && screen.includes('4:34:15') && screen.includes('3:43:17'), 'with the title and the duration the operator needs to tell a night from a clip');
  assert.ok(screen.includes(h.esc(h.t('kindArchive'))) && screen.includes(h.esc(h.t('kindHighlight'))), "and Twitch's own word for what each one is");
  assert.ok(/data-action="bf-pick" data-id="2884327358" data-length="13397"/.test(screen), 'Use this one carries the broadcast it will build');
  assert.equal((screen.match(/class="bf-thumb"/g) || []).length, 1, 'and only the row that has a picture draws one');
});

test('round 8 / owner item 1: the timer bar sits under the tab bar and leaves the timer its own screen', () => {
  const html = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const bar = html.slice(html.indexOf('<div class="bar">'), html.indexOf('</header>'));
  assert.ok(bar.indexOf('class="barrow"') < bar.indexOf('class="clockbar"'),
    'the destinations come first and the clock row sits under them: a row of doors, then the instrument');
  assert.ok(bar.indexOf('id="nav"') < bar.indexOf('class="clockbar"'), 'with the tab bar itself above it rather than beside it');
  assert.ok(html.includes('data-clock-host'), 'the host stays in the document - the bar is hidden, never removed, so clock-sync.js keeps its handle');
  assert.ok(/\[data-tab=clock\] \.clockbar\{display:none\}/.test(css),
    'on the timer own tab the bar leaves the screen: the big face is the instrument there and the strip must not repeat it');
  const phone = css;
  assert.ok(/#ops-shell\{--tabbar-h:52px;--clockbar-h:calc\(48px \+ env\(safe-area-inset-bottom\)\)\}/.test(phone)
    && /#ops-shell #tabbar\{[^}]*bottom:var\(--clockbar-h\)/.test(phone)
    && /#ops-shell \.clockbar\{[^}]*position:fixed[^}]*bottom:0/.test(phone),
    'on a phone the destinations are the bottom bar, so the strip at the screen edge is the timer and the safe-area inset moves with it');
  assert.ok(/#ops-shell\[data-tab=clock\]\{--clockbar-h:0px\}/.test(phone),
    'and with the timer open the token collapses, so the tab bar returns to the edge instead of leaving a strip of nothing');
  assert.ok(phone.includes('padding-bottom:calc(var(--tabbar-h) + var(--clockbar-h) + var(--sp-4))')
    && phone.includes('bottom:calc(var(--tabbar-h) + var(--clockbar-h) + var(--sp-3))'),
    'the page and the toast clear both fixed rows');
});

test('round 9 / owner items 4 + 5: the destination balls are solid, on the ivory face, in both schemes', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const base = css.match(/#ops-shell \.ball\{([^}]*)\}/);
  assert.ok(base && /background-color:var\(--ball-c,var\(--ball\)\)/.test(base[1]),
    'a ball takes the number\u2019s own colour: a solid ball, as DESIGN.md line 246 has the six destinations');
  const stripe = css.match(/#ops-shell \.ball\[data-stripe="1"\]\{([^}]*)\}/);
  assert.ok(stripe && /background-color:var\(--ball-face\)/.test(stripe[1]) && /var\(--ball-c\)/.test(stripe[1]),
    'only 9-15 are the white sphere with the hue laid across it');
  assert.ok(!/#nav \.ball,#tabbar \.ball/.test(css),
    'and nothing points a nav or tab-bar ball at that band - 1-7 are the solids (owner item 5)');
  const plate = css.match(/#ops-shell \.ball i\{([^}]*)\}/);
  assert.ok(plate && /background:var\(--ball-face\)/.test(plate[1]),
    'the number rides an ivory plate: that is the white the owner asked to keep, and it is on every ball');
  const js = fs.readFileSync(path.join(__dirname, '../annotator/ops.js'), 'utf8');
  assert.ok(/ballStripe=n=>ballNumber\(n\)>8\?1:0/.test(js), 'the stripe flag is 9-15 only, so a destination can never be drawn striped');
  const light = css.match(/:root\[data-theme=light\]\{([^}]*)\}/);
  assert.ok(light && !/--ball/.test(light[1]),
    'the light scheme redefines no ball token at all, so the base cannot follow the theme by accident');
});

test('round 20 / owner item 5 + round 31 / owner item 1: the Livestream tab is the state, the source and a refresh', async () => {
  const h = harness();
  (()=>{h.data.players=[];h.data.events=[];h.data.history=[];h.liveSnapshot={state:'idle',frames_skipped:0};h.liveRunning=()=>false;return h.render=()=>{}})();
  const html = h.livePanelScreen();
  assert.ok(html.includes('id="live-screen"') && html.includes('id="live-panel-status"'), 'the panel keeps its root and status line');
  assert.equal((html.match(/data-action="live-detector"/g) || []).length, 0, 'no detector row while nothing runs');
  assert.equal((html.match(/class="primary"/g) || []).length, 0, 'and no Start until a channel is saved');
  assert.equal((html.match(/<h2>/g) || []).length, 0, 'round 31: the tab is not a card with a heading any more');
  assert.ok(html.includes('data-action="sources-open"'), 'the source configurator is one of the two controls');
  assert.ok(html.includes('data-action="live-refresh"'), 'round 31: a refresh stands in while the stream is off');
  assert.equal((html.match(/data-action="live-debug"/g) || []).length, 0, 'round 31: the workbench toggle left this tab');
  assert.ok(!/data-tab="records"/.test(html) && !html.includes('live-note'), 'no History shortcut and no note while idle');
  // Round 31: the state is the headline of the tab, so the stylesheet sets it well above body size.
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(/\.live-status\{[^}]*font-size:clamp\(22px,3vw,32px\)/.test(css), 'the state is set in large type');
  const src = fs.readFileSync(path.join(__dirname, '../annotator/ops.js'), 'utf8');
  // Run the refresh instead of reading it: the click reads the live endpoint again.
  const refreshed = harness();
  const read = [];
  refreshed.context.fetch = async url => { read.push(String(url).split('?')[0]); return {ok: true, json: async () => ({state: 'idle', frames_skipped: 0})}; };
  await refreshed.dispatch('live-refresh');
  assert.equal(read[0], '/api/live', 'the refresh reads /api/live again');
  // The toggle keeps its capability, in the back room's maintainers block.
  assert.ok(src.includes("${btn(t('refresh'),'reload')}<button data-action=\"live-debug\""), 'the debug door lives in the back room now');
  // The door opens the workbench the stream would otherwise be needed to see, and a stream closes it.
  assert.ok(h.liveVisionScreen().includes('id="live-screen"'), 'idle: the panel is the tab');
  h.debugWorkbench=true;
  assert.ok(h.liveVisionScreen().includes('class="vision-surface"'), 'the debug door reaches the workbench');
  h.debugWorkbench=false;
});
test('round 10 / owner item 3: a broadcast with no night yet still gets the scrubber and the sidebars', () => {
  const h = harness();
  (()=>{h.lang='en';return h.data.history=[]})();
  const html = h.reviewScreen(null,{id:'2890514774',title:'261001',length_s:16455,created_at:'2026-10-02T23:07:00Z'});
  assert.ok(html.includes('class="vision-surface"'), 'the recorded page carries the workbench, not only an import button');
  // The stage grows the regions inside the host the screen paints: the page the
  // operator gets is the screen's host plus the stage's shell, and neither half is optional.
  const page = html + stageMarkup(h);
  for (const part of ['id="vs-grid"', 'class="vs-rail"', 'class="vs-inspector"', 'id="vs-scrub"', 'class="vs-track"', 'id="vs-frame-index"'])
    assert.ok(page.includes(part), `and the ${part} the owner was missing`);
  assert.ok(html.includes('data-action="bf-pick"') && html.includes('data-id="2890514774"'), 'the import is still offered for this broadcast');
  assert.ok(html.includes('data-length="16455"'), 'with the length it will download');
  assert.ok(!html.includes('TBD'), 'and no invented night name');
  // the shell opens the broadcast's own dataset when the machine has one. src/datasets.py's
  // imported_id() is what names it: 'tw-<vod>' for the whole broadcast, 'tw-<vod>-<start>-<end>' for a range.
  h.context.window.CornerPocketReview={canLeave:()=>true,snapshot:()=>({dataset:'vod30',datasets:[{id:'vod30'},{id:'highlight'}]})};
  assert.equal(h.datasetForVod('2890514774'), '', 'with no dataset for this broadcast the engine keeps the configured one');
  h.context.window.CornerPocketReview={canLeave:()=>true,snapshot:()=>({dataset:'vod30',datasets:[{id:'vod30'},{id:'tw-2890514774'}]})};
  assert.equal(h.datasetForVod('2890514774'), 'tw-2890514774', 'and opens it as soon as the import has made it');
  h.context.window.CornerPocketReview={canLeave:()=>true,snapshot:()=>({dataset:'vod30',datasets:[{id:'tw-2890514774-452-1690'}]})};
  assert.equal(h.datasetForVod('2890514774'), 'tw-2890514774-452-1690', 'a ranged import is recognised by the number it carries');
  h.context.window.CornerPocketReview={canLeave:()=>true,snapshot:()=>({dataset:'vod30',datasets:[{id:'tw-2890514774-452-1690'},{id:'tw-2890514774'}]})};
  assert.equal(h.datasetForVod('2890514774'), 'tw-2890514774', 'the whole-broadcast dataset is preferred to a range of it');
  assert.ok(/if\(want&&reviewState\(\)\.dataset!==want&&want!==vodDatasetAsked\)/.test(source), 'and the shell asks for it once the surface is mounted');
});
test('round 11: the count line is painted with the card and stays current when the late answer lands', async () => {
  const h = harness({hash: '#/records'});
  linkHistory(h);
  const first = h.recordsScreen();
  assert.ok(first.includes('class="muted archive-count"'),
    'the head carries the count from the first paint, before /api/vods/recent answers');
  assert.equal(h.esc(h.archiveCountText()),
    h.esc(h.t('archiveCount').replace('{n}','1').replace('{built}','1')),
    'and it counts what the console already knows: the record\u2019s one broadcast, already linked');
  // The live page's bug (found in the browser pass): the head was painted once, so the numbers
  // it could not know yet never arrived - the list repainted and the head stayed as it was.
  (()=>{h.context.window.__paint={list:{innerHTML:''},count:{textContent:''},note:{textContent:''}};return h.context.document.querySelector=s=>s==='#records-list'?h.context.window.__paint.list:s==='#archive-card .archive-count'?h.context.window.__paint.count:s==='#archive-card .archive-note'?h.context.window.__paint.note:null})();
  h.context.fetch = async () => ({ok: true, json: async () => ({channels: [...linkAnswer.channels, {channel: 'other', more: true, vods: []}]})});
  await h.loadArchiveList(true);
  assert.equal(h.context.window.__paint.count.textContent, h.archiveCountText(),
    'the late answer writes the count in place');
  assert.ok(h.context.window.__paint.count.textContent.includes('2'), 'two broadcasts are known now');
  assert.ok(h.context.window.__paint.note.textContent.includes(h.t('archiveMore').replace('{n}','2')),
    'and the sentence gains the clause it could not know before');
  assert.ok(h.context.window.__paint.list.innerHTML.includes('tl-vod-item'), 'the list is repainted beside it');
  assert.ok(!source.includes('loading=false;render()'), 'and the screen is never rebuilt under an operator');
});

test('round 8 · the console words dictionary defines every key exactly once', () => {
  const from = source.indexOf('const words={');
  const body = source.slice(from, source.indexOf('\n', from));
  const keys = [...body.matchAll(/(?:^|,)([A-Za-z_][A-Za-z0-9_]*):\[/g)].map(m => m[1]);
  const seen = new Set(), dups = [];
  for (const key of keys) { if (seen.has(key)) dups.push(key); else seen.add(key); }
  assert.deepEqual(dups, [], `a duplicate key silently overrides its first definition: ${dups.join(', ')}`);
  assert.ok(keys.length > 240, `the dictionary still holds every key (${keys.length})`);
  for (const [lang, miss] of [['en', 'en'], ['zh', 'zh']]) {
    const h = harness();
    h.lang=(lang);
    const missing = ['liveStream','liveNow','livePanelNote','liveNoChannel','reviewTitle','reviewFromRecords','reviewBack','reviewFootage','reviewBroadcast','reviewNote','person','ball','detectors','sources','stop','autoDownload','autoOn','autoPaused','autoPause','autoResume','autoQueued','autoDone','autoNow','autoSkipped','autoFailed','autoReading','searchCount','dayEvents','dayEventsOne','dayVods','dayVodsOne','reviewImport','reviewVodNote','rosterRatingBase','vodMark','vodLinks','vodLinkOpen','vodEventOpen','vodLinkSearch','vodEventSearch','vodLinkNone','vodEventNone','vodLinkEmpty','vodEventEmpty','vodUnlink','vodLinkedBadge','vodTonight','vodWord'].filter(k=>h.t(k)===k);
    assert.equal(JSON.stringify(missing), '[]', `${miss}: every round 8 word key has a translation`);
  }
});

// ---- Round 11 (owner, m07044): "every vod should be able to be associated to one or more
// competition. and every competition can be associated to one or more vod." One history list, and
// a link an operator can make from either end. The relation lives in the store (annotator/
// operations.py `vod_link`/`vod_unlink`); the console renders it and never derives it itself.
const linkAnswer = {channels: [{channel: 'ttpoolfriday', error: null, vods: [
  {id: '2890514774', title: '261001', created_at: '2026-10-03T01:30:00Z', length_s: 16455, broadcast_type: 'ARCHIVE', thumb: '/api/vods/thumb?channel=ttpoolfriday&id=2890514774'},
  {id: '2884327358', title: '260918', created_at: '2026-10-03T02:00:00Z', length_s: 13397, broadcast_type: 'HIGHLIGHT', thumb: ''}]}]};
const linkHistory = h => {
  h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:100}];
  h.data.tournament={id:'t1',name:'',format:'singles',raceTo:7,status:'registration',entrants:[],matches:[]};
  h.data.history=[
    {id:'n1',name:'Friday 8-Ball',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-10-03T05:00:00Z',
     source:{kind:'twitch',vodId:'2890514774',startS:0,endS:3600,title:'261001'},
     entrants:[{id:'a1',members:[{pid:'pa',name:'Ann'}]}],matches:[]},
    {id:'n2',name:'Wednesday 9-Ball',format:'singles',raceTo:5,status:'complete',archivedAt:'2026-10-03T06:30:00Z',
     entrants:[{id:'a2',members:[{pid:'pa',name:'Ann'}]}],matches:[]}];
  h.data.events=[];h.data.notes=[];
  h.data.vods=[{id:'2884327358',title:'260918',channel:'ttpoolfriday',length_s:13397,created_at:'2026-10-03T02:00:00Z'}];
  h.data.links=[{vodId:'2890514774',eventId:'n1',startS:0,endS:3600,at:'2026-10-03T05:00:00Z'},
              {vodId:'2890514774',eventId:'n2',at:'2026-10-03T10:00:00Z'},
              {vodId:'2884327358',eventId:'n2',at:'2026-10-03T10:00:00Z'}];
};
async function linkedScreen(h) {
  h.context.fetch = async () => ({ok: true, json: async () => linkAnswer});
  linkHistory(h);
  await h.loadArchiveList(true);
  h.lang='en';
  return h.recordsScreen();
}
test('round 11: one list - a day carries its nights and its broadcasts, and the links are many-to-many', async () => {
  const h = harness({hash: '#/records'});
  const screen = await linkedScreen(h);
  assert.ok(!screen.includes(`>${h.esc(h.t('archive'))}</h2>`), 'the archive is no longer a screen of its own (owner item 2)');
  assert.ok(!source.includes('archiveTimeline') && !source.includes('timelineHtml') && source.includes('function mergedTimeline(){'),
    'one renderer paints the history, and the two old ones are gone');
  const days = [...screen.matchAll(/class="tl-day" data-day="([^"]+)"/g)].map(m => m[1]);
  assert.equal(new Set(days).size, 1, 'the two nights and the two broadcasts share one day head');
  assert.equal((screen.match(/class="tl-day-head"/g) || []).length, 1, 'one day head, not one per kind');
  assert.ok(screen.includes(h.esc(h.t('dayEvents').replace('{n}','2'))) &&
    screen.includes(h.esc(h.t('dayVods').replace('{n}','2'))), 'the head counts both kinds');
  const day = screen.slice(screen.indexOf('class="tl-day"'));
  assert.ok(day.indexOf('data-event="n1"') > 0 && day.indexOf('data-event="n2"') > 0, 'both nights are rows in that day');
  assert.ok(day.indexOf('data-id="2890514774"') > 0 && day.indexOf('data-id="2884327358"') > 0, 'and both broadcasts are cards in it');
  const cards = [...screen.matchAll(/<li class="tl-vod-item">[^]*?<\/li>/g)].map(m => m[0]);
  const firstCard = cards.find(c => c.includes('data-id="2890514774"'));
  assert.ok(firstCard, 'the broadcast has a card of its own in the merged list');
  assert.ok(firstCard.includes('is-made') && firstCard.includes(h.esc(h.t('vodMark'))) &&
    firstCard.includes('Friday 8-Ball') && firstCard.includes('Wednesday 9-Ball'),
    'a broadcast two nights claim names both of them');
  assert.ok(h.recordsScreen().includes(h.t('archiveCount').replace('{n}','2').replace('{built}','2')),
    'and the count says how many of the window are linked');
  assert.equal(h.calls.length, 0, 'reading the merged list never writes');
});
test('round 11: the link is made from either end, and both directions post the pair', async () => {
  const h = harness({hash: '#/records'});
  await linkedScreen(h);
  h.render=()=>{};
  const row = h.eventItem(h.data.history[1]);
  assert.ok(row.includes('data-action="tl-review" data-id="2890514774"') && row.includes('261001'),
    'the night names its broadcasts, each one a way into the footage');
  assert.ok(row.includes(`data-action="vod-unlink" data-vod="2890514774" data-id="n2"`),
    'a link an operator made can be dropped from the row');
  const imported = h.eventItem(h.data.history[0]);
  assert.ok(imported.includes(h.esc(h.t('vodLinkedBadge'))) && !imported.includes('data-action="vod-unlink" data-vod="2890514774"'),
    "the night's own import record is marked and cannot be unlinked from here");
  assert.ok(row.includes(`data-action="vod-open" data-kind="event" data-id="n2"`), 'and the row carries the one control that adds a link');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'vod-open', kind: 'event', id: 'n2'}}}});
  const panel = h.vodPicker('event','n2',h.t('vodLinkOpen'));
  assert.ok(panel.includes(`aria-expanded="true"`) && panel.includes('class="pick-panel"') && panel.includes('data-vod-search="1"'),
    'the panel opens in place, with one search box');
  assert.ok(!/data-action="vod-link" data-vod="2890514774"/.test(panel) && !/data-action="vod-link" data-vod="2884327358"/.test(panel),
    'the two broadcasts this night already claims are not offered again');
  h.vodPick={kind:'event',id:'n2',q:''};
  assert.equal(h.vodPickRows('event','n2').length, 0, 'both known broadcasts are already linked to it');
  h.vodPick={kind:'event',id:'n1',q:''};
  assert.equal(JSON.stringify(h.vodPickRows('event','n1').map(r=>r.vodId)), '["2884327358"]',
    'the night with one link is offered the other broadcast');
  assert.equal(JSON.stringify(h.vodPickRows('event','n1')[0].attrs),
    '{"title":"260918","channel":"ttpoolfriday","length":"13397","created":"2026-10-03T02:00:00Z"}',
    'every field the store keeps rides the row, so the server never has to ask Twitch');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'vod-link', vod: '2884327358', id: 'n1',
    title: '260918', channel: 'ttpoolfriday', length: '13397', created: '2026-10-03T02:00:00Z'}}}});
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls.at(-1))), {name: 'vod_link', payload: {
    vodId: '2884327358', eventId: 'n1', title: '260918', channel: 'ttpoolfriday', length_s: 13397, created_at: '2026-10-03T02:00:00Z'}},
    'the write carries the pair and the broadcast metadata the store keeps');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'vod-unlink', vod: '2884327358', id: 'n1'}}}});
  assert.equal(JSON.stringify(h.calls.at(-1)),
    '{"name":"vod_unlink","payload":{"vodId":"2884327358","eventId":"n1"}}', 'and dropping it is the pair alone');
  const page = h.reviewScreen(null,h.vodById('2884327358'));
  assert.ok(page.includes('Wednesday 9-Ball'), 'the broadcast page lists the night that covers it');
  assert.ok(page.includes(`data-action="vod-open" data-kind="vod" data-id="2884327358"`), 'and carries the control that links another');
  h.vodPick={kind:'vod',id:'2884327358',q:''};
  assert.deepEqual(JSON.parse(JSON.stringify(h.vodPickRows('vod','2884327358').map(r=>[r.eventId,r.linked,r.locked]))),
    [['t1', false, false], ['n1', false, false], ['n2', true, false]], 'every night is offered, the linked one as its unlink');
  assert.ok(h.vodPicker('vod','2884327358',h.t('vodEventOpen')).includes('data-action="vod-unlink" data-vod="2884327358" data-id="n2"'),
    'and the row for a linked night is the way to drop it');
  h.vodPick={kind:'vod',id:'2890514774',q:''};
  assert.equal(JSON.stringify(h.vodPickRows('vod','2890514774').map(r=>[r.eventId,r.locked])),
    '[["t1",false],["n1",true],["n2",false]]', "the night whose own import is this broadcast is locked, the other is not");
});
test('round 11: the day head is not the row date, and every search still reaches both kinds', async () => {
  const h = harness({hash: '#/records'});
  await linkedScreen(h);
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('#ops-shell .tl-day-date{'), 'the day head has its own class');
  assert.ok(!/#ops-shell \.tl-date\{[^}]*--fs-xl/.test(css), 'and no longer restyles the row date it collided with (round 9)');
  assert.ok(source.includes('<span class="tl-date">') && source.includes('<h3 class="tl-day-date">'), 'the row keeps the small date, the head keeps the loud one');
  (()=>{h.vodPick=null;return h.eventsQuery='261001'})();
  const narrowed = h.mergedTimeline();
  assert.ok(narrowed.includes('data-id="2890514774"') && !narrowed.includes('data-id="2884327358"'), 'the box filters broadcasts by their own title');
  h.eventsQuery='Wednesday';
  const night = h.mergedTimeline();
  assert.ok(night.includes('data-event="n2"') && !night.includes('data-event="n1"'), 'and still filters nights by name');
  h.eventsQuery='';
});

test('round 8 / owner item 2: Records says what the automatic download is doing, and carries its one switch', async () => {
  for (const [lang, title, on, off, queued, done, now, pause, failed] of [
    ['en', 'Automatic download', 'running', 'paused', '3 queued', '12 done', 'now 2890514774', 'Pause', 'The download queue could not be read'],
    ['zh', '自动下载', '运行中', '已暂停', '排队 3 场', '已完成 12 场', '正在 2890514774', '暂停', '无法读取下载队列']]) {
    const h = harness();
    (()=>{h.lang=(lang);h.autoList.rows={enabled:true,queued:[1,2,3],done:Array.from({length:12}),current:{vod_id:'2890514774'},skipped:[],error:null};return h.autoList.error=''})();
    const html = h.autoInner();
    assert.ok(html.includes(title) && html.includes(on) && html.includes(queued) && html.includes(done) && html.includes(now), `${lang}: the line states the queue`);
    assert.ok(/data-action="auto-toggle"/.test(html) && html.includes(`>${pause}</button>`), `${lang}: the switch rides on the line`);
    (()=>{h.autoList.rows={enabled:false,queued:[],done:[],current:null,skipped:['1'],error:'ttpoolfriday: Twitch API request failed (HTTP 500)'};return h.paused=h.autoInner()})();
    const paused = h.paused;
    assert.ok(paused.includes(off) && paused.includes('Twitch API request failed'), `${lang}: a paused queue still says why`);
    assert.ok(/data-action="auto-toggle"/.test(paused), `${lang}: and can be resumed from the same place`);
    (()=>{h.autoList.rows=null;h.autoList.error='HTTP 500';return h.unread=h.autoInner()})();
    const unread = h.unread;
    assert.ok(unread.includes(failed) && unread.includes('data-action="auto-reload"'), `${lang}: an unread queue degrades to one sentence and a retry`);
  }
  // Run the switch instead of reading it: the click posts the opposite of the state on screen.
  const toggle = harness();
  toggle.autoList.rows = {enabled: true, queued: [], done: [], current: null, skipped: [], error: null};
  const posted = [];
  toggle.context.fetch = async (url, options) => { posted.push({url: String(url), body: JSON.parse(options.body)}); return {ok: true, json: async () => ({enabled: false, queued: [], done: []})}; };
  await toggle.dispatch('auto-toggle');
  assert.deepEqual(posted, [{url: '/api/vods/auto', body: {action: 'off'}}], 'the switch is wired to the click handler');
  assert.ok(/loadArchiveList\(\);loadAuto\(\)/.test(source), 'Records reads the queue with the archive list');
  assert.ok(/next=autoList\.rows\?\.enabled\?'off':'on'/.test(source), 'and posts the opposite of the current state');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('#ops-shell .auto-line{'), 'the line has its own layout');
});

test('round 11: a broadcast the channel has forgotten is still listed, from the console\'s own record', async () => {
  const h = harness({hash: '#/records'});
  const screen = await linkedScreen(h);
  assert.equal((screen.match(/class="tl-vod-note"/g) || []).length, 0,
    'a broadcast the archive lists is not marked as coming from the record');
  // Twitch exposes a window, not a history: the store keeps the broadcasts a link points at, and
  // the list must show them even after the channel stops exposing them - otherwise the row the
  // relation was made with disappears from under the night that names it.
  h.data.vods.push({id:'2274501933',title:'260828',channel:'ttpoolfriday',length_s:13800,created_at:'2026-10-03T03:00:00Z'});
  const after = h.recordsScreen();
  const cards = [...after.matchAll(/<li class="tl-vod-item">[^]*?<\/li>/g)].map(m => m[0]);
  const own = cards.find(c => c.includes('data-id="2274501933"'));
  assert.ok(own, 'a broadcast only the record knows is still a card in the merged list');
  assert.ok(own.includes(h.esc(h.t('vodOwn'))), 'and the card says where it came from');
  assert.ok(own.includes('260828'), 'with the title the store kept');
  assert.equal(cards.length, 3, 'no duplicate for the broadcast the archive already listed');
  assert.equal(cards.filter(c => c.includes('class="tl-vod-note"')).length, 1, 'only the unlisted one is marked');
  assert.ok(after.includes(h.t('archiveCount').replace('{n}','3').replace('{built}','2')),
    'the count is the union, not just the window');
  assert.ok(h.calls.length === 0, 'and still no write: the list only reads');
});

// ---------------------------------------------------------------- round 12 (owner, m08064)
// The owner sent three items with a screenshot of a night in play: one list, the match on the
// timer's own page, and a finish card that stops talking. Each item gets its own instrument.
test('round 12 / owner item 1: the queue and the draw are one list, and the ready match sends itself', () => {
  const h = harness();
  tonightNight(h, 'drawn');
  h.render=()=>{};
  for (const lang of ['en', 'zh']) {
    h.lang=(lang);
    const view = h.tonightScreen();
    assert.equal((view.match(/class="bracket-view"/g) || []).length, 1, `${lang}: one list, not a queue beside a draw`);
    assert.ok(!view.includes('queue-card') && !/Waiting to play|等待上场/.test(view), `${lang}: the queue card is gone, word and all`);
    assert.ok(view.includes(`<h3>${h.esc(h.t('bracketTitle'))}</h3>`), `${lang}: the list is headed by the draw's own word`);
    const draw = view.slice(view.indexOf('class="bracket-view"'));
    const line = draw.match(/<span class="muted">([^<]*)<\/span>/)[1];
    assert.ok(line.includes(h.esc(h.t('bracketSend')).replace('{n}','1')), `${lang}: the heading counts the match that waits for a table`);
    assert.ok(/data-action="schedule" data-id="m2"/.test(view), `${lang}: and that match sends itself from its own card`);
    assert.ok(!/<details class="panel"/.test(view), `${lang}: the list is not a drawer that closes itself after every write`);
    assert.ok(/#ops-shell \.bracket-view\{min-width:0\}/.test(opsCss) && /#ops-shell \.score-top select\{min-width:0[^}]*\}/.test(opsCss),
      `${lang}: the list and the board can shrink into a phone (measured: 802 px of scroll width at 390 before the clamp)`);
  }
  const before = (()=>{h.lang='en';return h.tonightScreen()})();
  (()=>{h.data.tournament.matches[1].status='live';return h.data.tournament.matches[1].table=1})();
  const after = h.tonightScreen();
  assert.ok(before.includes('data-action="schedule" data-id="m2"') && !after.includes('data-action="schedule" data-id="m2"'),
    'the match that went to a table is no longer offered one');
  assert.ok(!after.match(/<span class="muted">([^<]*)<\/span>/)[1].includes(h.esc(h.t('bracketSend')).replace('{n}','1')),
    'and the count drops with it, with nothing to reopen');
});
test('round 12 / owner item 2: the match follows the night onto the timer page, and only while a night is played', async () => {
  const h = harness();
  tonightNight(h, null);                        // the desk, before the draw
  const timer = () => h.clockScreen();
  assert.ok(!timer().includes('class="scoreboard"'), 'a desk before the draw leaves the timer page to the timer');
  tonightNight(h, 'drawn');                     // the night is being played
  h.data.tournament.matches.push({id:'m4',round:2,sides:['b','g'],score:[2,1],status:'live',table:1,absent:[]});
  const live = timer();
  assert.ok(live.includes('class="timer-card"') && live.includes('class="scoreboard"'), 'a night in play puts the match under the timer');
  assert.ok(live.includes(h.esc(h.ename('b'))) && live.includes(h.esc(h.ename('g'))), 'with both names on it');
  assert.ok(/data-action="(score|frame)"/.test(live)
    && (live.includes(h.esc(h.t('signNow'))) || live.includes(h.esc(h.t('signNoWinner')))),
    'and the controls that decide the frame, with the sign-off offered only once a winner exists (round 19, owner item 5)');
  tonightNight(h, 'done');
  assert.ok(!timer().includes('class="scoreboard"'), 'a finished night takes it away again');
  // The read that keeps a tablet at the table in step: this page, a night in play, never hidden.
  (()=>{h.reads=0;return h.context.fetch=async()=>{h.reads++;return {ok:true,json:async()=>({revision:h.data.revision})}}})();
  (()=>{h.tab='tonight';h.data.tournament.status='active';return h.data.tournament.matches=[{id:'m5',round:1,sides:['a','b'],score:[0,0],status:'live',table:1,absent:[]}]})();
  await h.pollOps();
  assert.equal(h.reads, 0, 'the read does not run on any other page');
  (()=>{h.tab='clock';return h.stopOpsPolling()})();
  await h.pollOps();
  assert.equal(h.reads, 1, 'a tap on the timer page reads the desk once');
  (()=>{h.context.document.hidden=true;return h.stopOpsPolling()})();
  await h.pollOps();
  assert.equal(h.reads, 1, 'a hidden tab reads nothing');
  (()=>{h.context.document.hidden=false;h.busy=true;return h.stopOpsPolling()})();
  await h.pollOps();
  assert.equal(h.reads, 1, 'and a page that is mid-write leaves the state alone');
  (()=>{h.busy=false;return h.stopOpsPolling()})();
  assert.equal(h.opsTimer, null, 'with the timer stopped, so no read outlives the test');
});
test('a cold load of the timer route waits for the snapshot instead of reading a null one', () => {
  const h = harness();
  (()=>{h.data=null;h.tab='clock';h.context.document.hidden=false;h.timers=[];return h.context.setTimeout=(fn,ms)=>{h.timers.push(ms);return h.timers.length}})();
  assert.doesNotThrow(() => h.syncOpsPolling(),
    'pageshow fires before the first snapshot lands, and the poll must not read that snapshot from the listener');
  assert.equal(h.timers.length, 0, 'so a load with no state yet schedules no read');
  (()=>{h.data={revision:1,tournament:{status:'active',matches:[]}};return h.syncOpsPolling()})();
  assert.equal(h.timers.join(), '4000', 'and a live night on the timer page still schedules its four-second read');
});
test('round 12 / owner item 3: the end of the night is one card, one row, one reason', () => {
  const h = harness();
  tonightNight(h, 'done');
  h.render=()=>{};
  for (const lang of ['en', 'zh']) {
    h.lang=(lang);
    const view = h.tonightScreen();
    assert.equal((view.match(/class="end-night"/g) || []).length, 1, `${lang}: the night\u2019s end is one row`);
    assert.ok(!view.includes('close-sheet') && !view.includes('card--night'), `${lang}: with no second card for the sheet and no summary card of its own`);
    assert.ok(view.includes('class="event-title"') && view.includes('event-params'), `${lang}: it lives in the event card, under the competition’s own name`);
    const start = view.indexOf('class="end-night"');
    const end = view.slice(start, view.indexOf('</div>', view.indexOf('</div>', start) + 1));
    assert.equal((end.match(/<h3>/g) || []).length, 0, `${lang}: and the row carries no heading of its own`);
    assert.equal((view.match(/class="tiles"/g) || []).length, 0, `${lang}: the six tiles are gone`);
    for (const gone of ['closeNote', 'closeSheetNote', 'endNightNote']) {
      assert.ok(!view.includes(h.esc(h.t((gone)))), `${lang}: and the prose of ${gone} is gone with them`);
    }
    for (const action of ['results-sheet', 'new-event', 'event-delete']) {
      assert.ok(end.includes(`data-action="${action}"`), `${lang}: the one row carries ${action}`);
    }
    const name = h.esc(h.tournament().name);
    const shown = (view.match(new RegExp(name, 'g')) || []).length;
    assert.ok(shown === 1 || shown === 2, `${lang}: the name reads on the scene line and, since round 19, on its card: ${shown}`);
    assert.ok(view.includes('class="event-title"'), `${lang}: the card carries it as its title`);
    assert.ok(/data-action="event-delete"[^>]*disabled/.test(end) && end.includes(h.esc(h.t('closeSigned'))),
      `${lang}: the signed result turns the delete off and says so in one line`);
  }
});

// ---------------------------------------------------------------- round 13 (owner, m08064)
test('round 13 / owner item 2: the archive is a heading, then one toolbar', () => {
  const h = harness();
  recordsNight(h);
  h.render=()=>{};
  for (const lang of ['en', 'zh']) {
    h.lang=(lang);
    const rec = h.recordsScreen();
    const heading = rec.slice(rec.indexOf('<div class="heading">'), rec.indexOf('class="toolbar"'));
    assert.ok(heading.includes(`>${h.esc(h.t('records'))}</h2>`) && heading.includes('archive-count'),
      `${lang}: the heading carries the name and the count - information belongs in the heading, not among the buttons`);
    // Round 20, owner item 6: the note explains the box, so it sits in the heading. The toolbar slice ends
  // at the line below it instead of at the note.
  const bar = rec.slice(rec.indexOf('class="toolbar"'), rec.indexOf('id="auto-line"'));
    assert.ok(bar.indexOf('events-search') < bar.indexOf('sources-open'), `${lang}: the search leads the row`);
    assert.ok(bar.indexOf('sources-open') < bar.indexOf('archive-reload') && bar.indexOf('archive-reload') < bar.indexOf('backfill-open'),
      `${lang}: then Sources, Refresh, and the backfill as the one primary action`);
    assert.equal((bar.match(/class="primary"/g) || []).length, 1, `${lang}: exactly one primary action`);
    assert.ok(bar.includes('toolbar-gap'), `${lang}: the actions sit at the end of the row, behind a flexible gap`);
  }
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(/#ops-shell \.toolbar-search\{flex:1 1 240px/.test(css), 'the search grows');
  assert.ok(/@media\(max-width:750px\)\{[\s\S]*?\.toolbar-search\{flex:1 1 100%\}/.test(css), 'and on a phone it takes the row it needs');
  assert.ok(/#ops-shell \.toolbar\{display:flex;flex-wrap:wrap/.test(css), 'the toolbar wraps instead of overflowing');
});
test('round 13 / owner item 8: one Twitch source configurator, on History and on Vision', async () => {
  const h = harness();
  (()=>{h.lang='en';h.render=()=>{};return h.data.sources=[{id:'s1',url:'https://www.twitch.tv/ttpoolfriday'},{id:'s2',url:'https://www.twitch.tv/videos/2890514774'}]})();
  assert.ok(h.recordsScreen().includes('data-action="sources-open"'), 'History carries the one button');
  assert.ok(h.livePanelScreen().includes('data-action="sources-open"'), 'so does the Vision panel');
  assert.ok(stageMarkup(h).includes('data-action="sources-open"'), 'and the review surface');
  assert.ok(source.includes("const overlays=(sourceOpen?sourceModal():'')+(lateOpen?lateModal():'');if(overlays)$('#main').insertAdjacentHTML('beforeend',overlays);"),
    'and render() mounts it over whichever tab the operator is on');
  const dialog = h.sourceModal();
  assert.ok(dialog.includes('id="sources-form"') && dialog.includes('name="url"') && dialog.includes('type="url"'),
    'the dialog is one field and two buttons');
  assert.ok(dialog.includes('Live channel') && dialog.includes('https://www.twitch.tv/ttpoolfriday'), 'it lists the saved channel with its kind');
  assert.ok(dialog.includes('Recorded video') && dialog.includes('https://www.twitch.tv/videos/2890514774'), 'and the saved VOD');
  assert.equal((dialog.match(/data-action="source-remove"/g) || []).length, 2, 'every row can be removed from here');
  await h.handlers.submit(submission('sources-form', {url: 'https://www.twitch.tv/wallet'}));
  assert.equal(h.calls.length, 0, 'a link Twitch cannot be is stopped at the field, before any request');
  await h.handlers.submit(submission('sources-form', {url: 'https://www.twitch.tv/newchannel'}));
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [{name: 'source_add', payload: {url: 'https://www.twitch.tv/newchannel'}}],
    'a channel posts the one action the console always posted');
  assert.equal(h.sourceOpen, false, 'and the dialog closes on the answer');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'source-remove', id: 's2'}}}});
  assert.equal(JSON.parse(JSON.stringify(h.calls))[1].name, 'source_delete', 'a row removes its own source');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'sources-open'}}}});
  assert.equal(h.sourceOpen, true, 'and the button opens it again');
  h.sourceOpen=false;
});

// ---------------------------------------------------------------- round 14 (owner, m08064)
test('round 14 / owner item 1: the event table lives in the entrants card, so the tab is three elements', () => {
  const h = harness();
  tonightNight(h, 'drawn');
  h.render=()=>{};
  const html = h.playScreen();
  // Round 21, owner item 3 added the late-join card. Round 31, owner item 2 moved its control into the
  // event settings card, so the tab is the event card and the entrants card again, the draw between them.
  assert.equal((html.match(/class="card card--/g) || []).length, 2, 'the event card and the entrants card');
  const eventBlock = html.slice(0, html.indexOf('class="bracket-view"'));
  assert.ok(eventBlock.includes('data-action="late-open"'), 'the late-join control is a row of the event settings card');
  assert.equal((html.match(/data-action="late-open"/g) || []).length, 1, 'one late-join door on the tab, not two');
  assert.ok(!html.includes('card--late'), 'and no card of its own any more');
  assert.equal((html.match(/class="bracket-view"/g) || []).length, 1, 'and the draw between them');
  assert.ok(html.indexOf('class="card card--event"') < html.indexOf('class="bracket-view"') && html.indexOf('class="bracket-view"') < html.indexOf('class="card card--entrants"'),
    'in the owner\u2019s order: the event, the draw, the entrants');
  const card = html.slice(html.indexOf('class="card card--entrants"'));
  assert.ok(card.includes('data-vs-role="entrant-record"') && !card.includes('event-table'),
    'round 19, owner item 3: the record is on the entrant rows, and there is no second table anywhere');
  assert.ok(!html.includes('event-table'), 'and no table is on the tab at all');
});
test('round 14 / owner item 3: a recorded review offers no clip and no source chooser', () => {
  const h = harness();
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  assert.ok(source.includes('fixedClip:()=>!!reviewId'), 'the shell tells the workbench the clip is already decided');
  assert.ok(adapter.includes("const datasets = (liveOnly || fixed) ? '' :"), 'so the clip chips are not drawn');
  assert.ok(adapter.includes("const chip = fixed ? '' : `<button"), 'nor the source chip');
  assert.ok(adapter.includes('const channels = (fixed ? [] : (opts.channels() || []))'),
    'and no live-channel chip: a recorded broadcast is not a live source');
  const clip = stageMarkup(h, {fixed: true}), undecided = stageMarkup(h);
  assert.ok(!clip.includes('data-action="sources-open"') && !clip.includes('data-action="live-stop"'),
    'and the recorded review surface carries neither the source door nor the stop control');
  assert.ok(undecided.includes('data-action="sources-open"') && undecided.includes('data-action="live-stop"'),
    'while a surface whose clip is not yet decided offers both');
  h.render=()=>{};
  assert.ok(h.livePanelScreen().includes('data-action="sources-open"'),
    'while the live Vision page keeps the source door, where the stream comes from');
});

// ---------------------------------------------------------------- round 15 (owner, m08064)
test('round 15 / owner item 1: opening a historical broadcast puts that broadcast on the scrubber', () => {
  const h = harness();
  const seen = [];
  (()=>{h.set=[];h.context.window.CornerPocketReview=Object.assign(h.context.window.CornerPocketReview||{},{snapshot:()=>({datasets:[{id:'vod30'},{id:'tw-2890514774'}]}),setDataset:id=>{h.set.push(id);return Promise.resolve(true)}});
    h.reviewDatasetAt=0;h.reviewDatasetSynced=null;
    h.data.history=[{id:'n1',name:'Friday',source:{vodId:'2890514774'},matches:[]}];h.reviewId='n1';return h.syncReviewDataset()})();
  assert.deepEqual(JSON.parse(JSON.stringify(h.set)), ['tw-2890514774'],
    'the engine is handed the opened broadcast\u2019s own dataset, not the engine\u2019s default');
  assert.equal(h.reviewDatasetSynced, 'n1', 'and the sync remembers which review it served');
  h.syncReviewDataset();
  assert.equal(h.set.length, 1, 'it asks once: an operator who switches later is not fought');
  (()=>{h.reviewId=null;h.reviewDatasetAt=0;h.syncReviewDataset();h.reviewId='n2';h.data.history=[{id:'n2',name:'Other',source:{vodId:'424242'},matches:[]}];h.reviewDatasetAt=0;return h.syncReviewDataset()})();
  assert.equal(h.set.length, 1, 'a broadcast this workbench has no dataset for changes nothing');
  assert.ok(source.includes('if(reviewId&&data&&!document.hidden){syncReviewDataset();syncReviewFrames()}'), 'the 200 ms tick is what waits for the datasets and their frames');
});
test('review route: the tick waits for the night list before it looks for the broadcast', () => {
  // Measured in the browser: a review address opened cold threw
  // "Cannot read properties of null (reading 'history')" from the first tick.
  const h = harness({hash: '#/records/review/n1'});
  h.data = null;
  h.reviewDatasetAt = 0;
  h.reviewDatasetSynced = null;
  assert.doesNotThrow(() => h.tick(), 'the tick runs before /api/operations answers');
  assert.equal(h.reviewDatasetSynced, null, 'and it marks no review as synced before the list is known');
});
test('round 15 / owner item 1: a broadcast with no frames says so, once', () => {
  const h = harness();
  (()=>{h.messages=[];h.message=(text,error)=>h.messages.push([text,!!error]);
    h.context.window.CornerPocketReview=Object.assign(h.context.window.CornerPocketReview||{},{snapshot:()=>({datasets:[]}),setDataset:()=>Promise.resolve(true)});
    h.reviewDatasetAt=0;h.reviewDatasetTries=0;h.data.history=[{id:'n1',name:'Friday',source:{vodId:'2890514774'},matches:[]}];
    h.reviewId='n1';for(let i=0;i<3;i++){h.reviewDatasetAt=0;h.syncReviewDataset()}})();
  assert.equal(JSON.parse(JSON.stringify(h.messages)).length, 1,
    'a blank scrubber is explained: no frames for this broadcast yet, import it from Broadcasts');
  assert.ok(JSON.parse(JSON.stringify(h.messages))[0][0].includes('import it from Broadcasts'), 'in the operator\u2019s words');
  (()=>{h.reviewDatasetAt=0;return h.syncReviewDataset()})();
  assert.equal(JSON.parse(JSON.stringify(h.messages)).length, 1, 'once per review, not on every tick');
});

test('round 16 / owner item 1: a dataset switch blanks the stage before the new frame paints', () => {
  const engine = fs.readFileSync(path.join(__dirname, '../annotator/app.js'), 'utf8');
  assert.ok(engine.includes('function clearStageSurfaces() {'), 'the stage has one place that blanks both surfaces');
  assert.ok(engine.includes('state.frame = 0;\n  clearStageSurfaces();'),
    'setDataset calls it before loadVideo, so no other stream\u2019s pixels survive the switch');
  assert.ok(engine.includes("img.removeAttribute('src'); img.hidden = true;"), 'the still image loses its src');
  assert.ok(engine.includes("video.removeAttribute('src'); video.hidden = true;"), 'and so does the video element');
  assert.ok(engine.includes('loadFrame(0)'), 'frame 0 of the chosen dataset is what loads');
});
test('round 16 / owner item 1: a listed broadcast with no decoded frames says so', () => {
  const h = harness();
  (()=>{h.messages=[];h.message=(text,error)=>h.messages.push(text);
    h.context.window.CornerPocketReview=Object.assign(h.context.window.CornerPocketReview||{},{snapshot:()=>({dataset:'tw-2890514774',datasets:[{id:'tw-2890514774'}],frame:{has:false}}),setDataset:()=>Promise.resolve(true)});
    h.data.history=[{id:'n1',name:'Friday',source:{vodId:'2890514774'},matches:[]}];
    h.reviewId='n1';h.reviewDatasetSynced='n1';h.reviewFramesAt=0;h.reviewFramesTold=null;return h.syncReviewFrames()})();
  const said = JSON.parse(JSON.stringify(h.messages));
  assert.equal(said.length, 1, 'the console explains the blank stage instead of leaving it blank');
  assert.ok(said[0].includes('import it from Broadcasts'), 'and names the import that fills it');
  (()=>{h.reviewFramesAt=0;return h.syncReviewFrames()})();
  assert.equal(JSON.parse(JSON.stringify(h.messages)).length, 1, 'once per broadcast');
  (()=>{h.context.window.CornerPocketReview.snapshot=()=>({dataset:'tw-2890514774',datasets:[{id:'tw-2890514774'}],frame:{has:true}});
    h.reviewFramesTold=null;h.reviewFramesAt=0;return h.syncReviewFrames()})();
  assert.equal(JSON.parse(JSON.stringify(h.messages)).length, 1, 'and nothing at all once frames are decoded');
});
test('round 28 / owner item: one player in two appearances - the label panel links a body track to a face track', () => {
  const stage = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  const engine = fs.readFileSync(path.join(__dirname, '../annotator/app.js'), 'utf8');
  const server = fs.readFileSync(path.join(__dirname, '../annotator/unified_server.py'), 'utf8');
  const index = fs.readFileSync(path.join(__dirname, '../src/person_identity.py'), 'utf8');
  assert.ok(server.includes("['api', 'identity', 'link']"), 'the route exists, so the panel has something to call');
  assert.ok(server.includes('def identity_link(self, payload)') && server.includes('identity.link_track(track_id, cluster_id)'),
    'and it reaches the index under the identity lock');
  assert.ok(server.includes('KeyError') && server.includes('ValueError'),
    'an unknown cluster and a bound source are answered, not turned into a 500');
  assert.ok(server.includes('tracks_of(cluster)'),
    'the status route reports which tracks each identity owns, so a merge is visible to the operator');
  assert.ok(index.includes('def link_track(self, track_id: int, cluster_id: int)'),
    'the index owns the merge, so every caller shares one rule');
  assert.ok(index.includes('unbind it before linking'),
    'and it refuses to discard an operator binding, instead of silently rebinding');
  assert.ok(stage.includes('data-vs-action="link-target"') && stage.includes('data-vs-action="link-track"'),
    'the panel offers the identities of this frame and one button');
  assert.ok(stage.includes('target.linkTrack(node, select ? select.value : null)'),
    'the click sends the picker value read at click time, never a draft from an earlier render');
  assert.ok(engine.includes("save(button, '/api/identity/link', {track_id: trackId(track), cluster_id: other}"),
    'the engine posts the track and the cluster it was picked for');
});
test('round 17 / owner item 1: the face a person was identified by is drawn, and never as a second human', () => {
  const engine = fs.readFileSync(path.join(__dirname, '../annotator/app.js'), 'utf8');
  const pipeline = fs.readFileSync(path.join(__dirname, '../src/person_pipeline.py'), 'utf8');
  const server = fs.readFileSync(path.join(__dirname, '../annotator/unified_server.py'), 'utf8');
  assert.ok(server.includes('"face_bbox", "face_quality"'), 'the API carries the face box it already measures');
  assert.ok(pipeline.includes("person['face_bbox'] = [int(v) for v in face['bbox']]"),
    'and the pipeline fills it from the face it matched to that person');
  assert.ok(engine.includes('class="u-face" data-face-for='), 'the overlay draws that box');
  assert.ok(engine.includes('data-face-quality='), 'with the evidence that put it there');
  assert.ok(/class="u-face"[^>]*pointer-events="none"/.test(engine),
    'it takes no pointer events, so it can never be selected or edited as a subject');
  assert.ok(!/class="u-face"[^>]*data-person=/.test(engine),
    'and it is not a person box: one human keeps one box (the face rides inside it)');
});
test('round 27 / owner item 1: the freeze control owns inference, and a plain stop starts nothing', () => {
  const engine = fs.readFileSync(path.join(__dirname, '../annotator/app.js'), 'utf8');
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  assert.ok(engine.includes('function freeze() { setPlaying(false); const ok = seek(state.frame); scheduleAutoInference(); return ok; }'),
    'freezing a frame is the request that starts a run');
  assert.ok(!engine.includes('if (!state.playing) scheduleAutoInference();'),
    'a stop on its own (a scrub, a step, the end of a clip) starts nothing');
  assert.ok(engine.includes('function scheduleAutoInference() {'), 'and it is one named place');
  assert.ok(/if \(tries > 0\) \{ attempt\(tries - 1\); return; \}/.test(engine),
    'a pause the stage cannot serve yet is retried, not dropped');
  assert.ok(engine.includes("state.inferStatus = 'Inference is waiting for this frame to decode.';"),
    'and when it still cannot run, the stage says why instead of staying silent');
  assert.ok(/state\.lastInferredFrame = frame;/.test(engine),
    'the frame is remembered only after a run starts');
  for (const guard of ['state.autoInferOff', 'state.inferRunning', 'state.lastInferredFrame === state.frame', 'state.playing || state.inferRunning']) {
    assert.ok(engine.includes(guard), `the run is guarded: ${guard}`);
  }
  assert.ok(/const attempt = \(tries\) => \{\s*\n\s*autoInferTimer = setTimeout\(async \(\) => \{[\s\S]{0,1600}?\}, 500\);\s*\n\s*\};\s*\n\s*attempt\(4\);/.test(engine),
    'and debounced, so a scrub that lands somewhere does not start work the operator is about to leave');
  assert.ok(engine.includes('function setAutoInference(on) {') && engine.includes('runInference, setAutoInference,'),
    'the operator can turn it off');
  assert.ok(engine.includes('inferRunning: state.inferRunning, inferStatus: state.inferStatus, autoInfer: !state.autoInferOff,'),
    'the snapshot carries the report the stage renders');
  assert.ok(!adapter.includes('data-vs-role="infer-status"') && !adapter.includes("case 'auto-infer'"),
    'the stage carries no second control for the same gesture');
  assert.ok(adapter.includes("const key = corr.inferRunning ? 'freezeRunning' : 'freeze';"),
    'the freeze button reports a run in flight, under its own label key');
  assert.ok(source.includes('setAutoInference:on=>review()?.setAutoInference?.(on)'),
    'and the engine still exposes the switch for a settings surface to call');
});
test('round 17: a superseded frame request does not lock the stage', () => {
  const engine = fs.readFileSync(path.join(__dirname, '../annotator/app.js'), 'utf8');
  assert.ok(engine.includes('} else if (epoch === state.epoch) {'),
    'the stale request releases the stage when the newer one could not start');
  assert.ok(/else loadFrame\(state\.frame\);/.test(engine),
    'and it loads the frame that is actually on screen, so the picture is never left blank');
  assert.ok(engine.includes('state.busy = false; state.decoding = false;\n      const queued = state.pendingSeek; state.pendingSeek = null; notify();\n      if (queued !== null && queued !== undefined) loadFrame(queued);\n      else loadFrame(state.frame);'),
    'the queued seek wins when there is one - that is the request that was refused');
});
test('round 17 / owner item 3: the identity frame reaches the overlay and the track rows', () => {
  const engine = fs.readFileSync(path.join(__dirname, '../annotator/app.js'), 'utf8');
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  assert.ok(engine.includes('fetchIdentity(state.dataset, shot.frame, epoch, request);'),
    'the frame asks for the identity record that belongs to it');
  assert.ok(/async function fetchIdentity\(dataset, n, epoch, request\) \{/.test(engine),
    'in one named place');
  assert.ok(engine.includes('if (epoch !== state.epoch || request !== state.frameReq) return;'),
    'and a record for a frame that has left the stage is dropped');
  assert.ok(engine.includes('catch (_) { state.identity = null; state.identityFor = key; }'),
    'a missing identity pipeline cannot break the picture (the endpoint answers 503 without models)');
  assert.ok(engine.includes('state.identity = identity; state.identityFor = key; notify();'),
    'the record is kept with the frame it describes, and the stage is told');
  assert.ok(!/const \[shot, result\] = await Promise\.all\(\[[^\]]*identity/.test(engine),
    'the identity fetch is never awaited with the frame: its models build on first use');
  assert.ok(/identityPersons\.map\(p => \(\{bbox: p\.bbox, track_id: p\.track_id/.test(engine),
    'the persons layer falls back to the identity record when the unified detection has no people');
  assert.ok(engine.includes('face_bbox: p.face_bbox, face_quality: p.face_quality}'),
    'so the face box the pipeline drew is carried into the overlay');
  assert.ok(engine.includes('persons: {identity: (state.identity?.persons || []).map('),
    'and the rows can see the binding');
  assert.ok(adapter.includes('data-vs-role="track-identity"') && adapter.includes('faceOnly:'),
    'each track row shows who the pipeline says it is, in both languages');
  assert.ok(engine.includes('const face = per.face_bbox && per.face_bbox.length === 4'),
    'the face box still rides inside the one person box');
});
test('round 17 / owner item 4: History shows the ingestion progress in one place', () => {
  const h = harness();
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  (()=>{h.bf=null;h.data.history=[];return h.data.events=[]})();
  assert.ok(h.recordsScreen().includes('id="ingest-line"'),
    'History carries one line for the ingestion, beside the download line');
  assert.equal(h.bfProgressLine(), '', 'and it is empty when nothing is running: no permanent chrome');
  h.bf={step:'importing',job:{percent:42,rate_mb_s:3.1,eta_s:95},vod:{title:'261001'}};
  const line = h.bfProgressLine();
  assert.ok(line.includes('42%') && line.includes('3.1 MB/s') && line.includes('261001'),
    'while a job runs it carries the numbers and the name the wizard shows');
  assert.ok(line.includes('data-action="backfill-open"'),
    'and its button uses the action that already opens the wizard, not a second one');
  assert.ok(h.recordsScreen().includes('42%'), 'so History shows it without opening the wizard');
  assert.ok(css.includes('.ingest-line') && css.includes('.bf-banner.err'), 'both have their own styles');
  assert.ok(css.includes('prefers-reduced-motion:reduce') , 'and the pulse is off for reduced motion');
});
test('round 18 / owner items 1-6, read exactly: the red boxes go, the rest stays', () => {
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  const shell = fs.readFileSync(path.join(__dirname, '../annotator/ops.js'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(!adapter.includes('class="vs-keys"'), 'red box 1: the keyboard-hint line is gone');
  assert.ok(!adapter.includes('data-vs-action="run-inference"') && !adapter.includes("case 'run-inference'"),
    'red box 2: no surface offers a manual inference run - a pause is the signal');
  assert.ok(adapter.includes("const gated = key === 'anchors' && s.dataset !== 'vod30';") && !adapter.includes("if (gated) return '';"),
    'everything boxed green stays: the anchors chip is a control, drawn disabled where it cannot act');
  assert.ok(adapter.includes("t('coldStartHint')"), 'and the empty-state guidance is still there');
  assert.ok(/const pickedPerson = s\.selection\?\.kind === 'person' \|\| \(s\.persons\.track !== null && s\.persons\.track !== undefined\);\n  if \(!pickedPerson\) return '';/.test(adapter),
    'order 2 read exactly: the label box opens for a picked person, by row or on the stage, and is closed otherwise');
  assert.ok(adapter.includes('enrolBlock(s)'), 'while the identity block and its evidence stay');
  assert.ok(!/vs-item vs-track[\s\S]{0,400}<select/.test(adapter), 'order 4: no roster select in a sidebar row');
  assert.ok(adapter.includes('data-vs-role="track-identity"'), 'and the row still names who the pipeline thinks it is');
  assert.ok(css.includes('#ops-shell[data-review="1"]{height:100dvh;overflow:hidden}'), 'order 3: the page fits the viewport');
  assert.ok(/#ops-shell\[data-review="1"\] \.vs-strip\{flex:0 0 auto;/.test(css),
    'and the scrub strip is pinned inside it, never below the fold');
  assert.ok(shell.includes("shell.dataset.review=shellState.review") && shell.includes("setShell({review:!!(reviewId&&!bf)"), 'the shell marks the layout');
  const h = harness();
  (()=>{h.messages=[];h.message=(text,error)=>h.messages.push([text,!!error]);return h.busy=true})();
  assert.equal(h.go('players'), false, 'order 5: a navigation that cannot proceed is refused');
  const said = JSON.parse(JSON.stringify(h.messages));
  assert.equal(said.length, 1, 'and it is not silent');
  assert.equal(said[0][1], true, 'the operator is told, as a warning');
});
test('round 19 / owner item 9: the bar is one row, so the picture starts higher', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator', 'ops.css'), 'utf8');
  const html = fs.readFileSync(path.join(__dirname, '../annotator', 'ops.html'), 'utf8');
  // Round 20, owner item 8: the shot timer is its own bar again, so the rule that pinned it to the
  // bar's edge is gone. What remains is the compact padding.
  assert.ok(!/\.bar \.clockbar\{position:absolute/.test(css), 'the clock is not pinned into the nav row');
  assert.ok(/#ops-shell \.bar\{padding-top:var\(--sp-1\);padding-bottom:var\(--sp-1\)\}/.test(css),
    'the bar keeps the compact padding round 19 gave it');
  assert.ok(/#ops-shell\[data-review="1"\] \.vs-stage\{height:100%;align-self:stretch\}/.test(css),
    'and the stage fills the room the bar gave back');
  assert.ok(/\.vs-stage img,[^}]*\.vs-stage video\{max-height:100%;max-width:100%/.test(css),
    'with the picture filling the stage');
  assert.ok(/ops\.css\?v=vision-stage-\d+/.test(html) && /app\.css\?v=vision-stage-\d+/.test(html),
    'both stylesheets are version-tagged, so a CSS change is never read from the browser cache');
});
test('round 19 / owner item 8: the label box floats over the video while a track is picked', () => {
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(adapter.includes('function paintLabelOverlay(s)') && adapter.includes("host.id = 'vs-label-overlay'"),
    'one function owns the overlay, and it creates the element when the surface has none');
  assert.ok(adapter.includes("inspector.classList.toggle('label-moved', !!html)"),
    'the inspector stops showing its own copy while the overlay is up');
  assert.ok(adapter.includes('${labelBoxHTML(s)}'), 'and both homes render the same markup, not two versions');
  assert.ok(/\.vs-label-overlay\{position:absolute;left:calc\(280px \+ var\(--sp-3\)\)/.test(css),
    'the box is anchored over the stage, clear of the rail');
  assert.ok(css.includes('.vs-inspector.label-moved .vs-labelblock{display:none}'), 'so no second copy is visible');
  assert.ok(/#ops-shell\[data-label-overlay="1"\] \.vs-grid\{grid-template-columns:280px minmax\(0,1fr\) 320px\}/.test(css),
    'and the stage keeps the width it had: narrowing the label column cost more than it gave');
});
test('round 19 / owner item 6: the Tonight screen reads like a person wrote it', () => {
  const h = harness();
  const words = JSON.parse(JSON.stringify(h.words));
  // Batch 1 of the Chinese copy pass. Each pair is checked for the three things that made the old
  // copy read mechanical: a Latin word left in the Chinese, a sentence that is the English one with
  // Chinese characters, and a reference to a control that no longer exists.
  const batch = ['locked', 'closeNoEntrants', 'closeSigned', 'closeNoEvent', 'boardEmptyWait',
                 'boardEmptySend', 'boardEmptyNoDraw', 'signNoWinner', 'noMatch',
                 // batch 2: the Back room, where the jargon lived ('持久化运营接口').
                 'persist', 'forMaintainersNote', 'systemStatusNote', 'noSimulation', 'observation',
                 'review', 'notConnected',
                 // batch 3: History, where the long sentences live.
                 'reviewNote', 'autoQueued', 'autoSkipped', 'autoDone',
                 // batch 4: the backfill wizard, which is where the longest notes live.
                 'bfHonest', 'bfManual', 'bfPickNote', 'bfLeft', 'bfLinkedCount', 'bfChannel'];
  const allow = ['T{table}', 'VOD', 'Twitch', 'MB/s', '{n}', '{name}', '{score}', '{table}', '{id}', '{at}'];
  for (const key of batch) {
    const [en, zh] = words[key];
    assert.ok(en && zh, `${key} has both languages`);
    assert.notEqual(en, zh, `${key} is translated, not copied`);
    // Every placeholder is allowed, whatever it is called: the rule is about words a reader would
    // see, and a token like {m} is a number at render time.
    const stripped = allow.reduce((text, token) => text.split(token).join(''), zh).replace(/\{[a-zA-Z]+\}/g, '');
    assert.ok(!/[A-Za-z]/.test(stripped), `${key} leaves no English word in the Chinese: ${zh}`);
    assert.ok(/[\u3400-\u9fff]/.test(zh), `${key} is Chinese: ${zh}`);
  }
  assert.ok(!words.locked[1].includes('赛事设置'), 'the locked note no longer names a heading that is gone');
  assert.equal(h.t('bfStep'), 'bfStep', 'the retired step counter is out of the table');
  assert.ok(words.locked[1].includes('卡片'), 'it names the card the operator can see');
  assert.ok(words.noMatch[1].includes('球台'), 'and the empty board names the table, not an abstraction');
});
test('round 19 / owner item 6, batch 5: the workbench says it in Chinese too', () => {
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  // The three sentences this batch rewrote, and the phrases it removed. A character census cannot tell
  // a product name from a translation, so the check is on the wording itself.
  assert.ok(adapter.includes('把这条轨迹标为观众：不参与身份分配，也不会和上面两个标注选项混在一起。'),
    'the ignore note says what the operator is doing, not a literal translation');
  assert.ok(adapter.includes('先选一条线索、球、人物或锚点，再开始标注。'), 'the rail empty state stopped padding with 请');
  assert.ok(adapter.includes('选中线索会在舞台上循环播放它的片段；冻结后可逐帧检查。'), 'and the cue note reads as one sentence');
  for (const gone of ['争夺注意力', '请先选择线索', '再进行标注']) {
    assert.ok(!adapter.includes(gone), `${gone} is gone from the workbench's Chinese`);
  }
  for (const key of ['keys', 'keyMap']) {
    assert.ok(!new RegExp(`\\n\\s*${key}:'`).test(adapter), `${key} is out of the table: the hint line it fed went in round 18`);
  }
  for (const [key, zh] of [['ignoreHint', '把这条轨迹标为观众'], ['railEmpty', '先选一条线索'], ['selectCueHint', '选中线索会']]) {
    assert.ok(adapter.includes(zh), `${key} keeps its Chinese: ${zh}`);
  }
});
test('round 20 / owner item 9: the stage is not re-written on every paint', () => {
  const engine = fs.readFileSync(path.join(__dirname, '../annotator/app.js'), 'utf8');
  // A VOD's first frame flashed because the same values were re-applied on every paint, and every
  // assignment to an <img> is a reload. Each write is now guarded by a comparison.
  assert.ok(engine.includes("String(picture) !== 'null' && img.getAttribute('src') !== picture"),
    'the frame source is written only when it changes, and never as a null-ish string');
  assert.ok(engine.includes('if (video && video.hidden !== !videoShown) video.hidden = !videoShown;'),
    'the video element is shown or hidden only when that changes');
  assert.ok(engine.includes('if (empty.hidden !== hideEmpty) empty.hidden = hideEmpty;'),
    'and so is the empty-state note');
  assert.ok(engine.includes('if (note.hidden !== !lines.length) note.hidden = !lines.length;'),
    'and the facts note');
  assert.ok(!/^\s*(img|video|empty|note)\.hidden = /m.test(engine), 'no unguarded hidden write is left in the stage');
});
test('round 20 / owner item 10: the backfill does not ask the operator twice', () => {
  // The three chains are statements inside the click dispatcher and the job adoption, so they are read
  // from the source: each one replaces a decision the operator used to have to make.
  const bfActions = harness().actions();
  assert.ok(bfActions.includes('bf-check'),
    'the estimate follows the check');
  assert.ok(source.includes("if(bf?.estimate?.already_imported)bfUseImported();else bfStartImport();"),
    'and the estimate decides: reuse what is on disk, or download once the disk says there is room');
  assert.ok(/if\(state==='done'\)\{[\s\S]{0,700}?bfStartMarking\(\)/.test(source),
    'a finished import opens the marking canvas instead of stopping on a button');
  // The two decisions that stay with the operator.
  assert.ok(bfActions.includes('bf-confirm'), 'every match is still confirmed by a person');
  assert.ok(bfActions.includes('bf-commit'), 'and the night is still written by one');
  // Nothing in the chain removed a neighbouring action. The table routes each one, and a table
  // cannot hold the same name twice, so the old "exactly one branch" count is now structural.
  for (const name of ['bf-start-import', 'bf-use-imported', 'bf-poll', 'bf-start-marking']) {
    assert.ok(bfActions.includes(name), `${name} is still a routed action`);
  }
  assert.equal(new Set(bfActions).size, bfActions.length, 'the table cannot hold one name twice');
});
test('round 21 / owner item 3: the second chance can be told who to resurrect', () => {
  const h = harness();
  // The card offers the draw and a name; the payload carries the name only when one is chosen.
  assert.ok(source.includes("id=\"revival-pick\""), 'the second-chance card offers a picker');
  assert.ok(source.includes("t('revivalRandom')") && source.includes('function revivalPool(T)'),
    'whose first option is the random draw, over the round-1 losers');
  assert.ok(source.includes("pick?{confirm:true,entrant:pick}:{confirm:true}"),
    'a chosen name travels in the payload, and the draw stays untouched when none is chosen');
  // The pool is the round-1 losers, computed from the tournament the client holds.
  h.data.tournament={id:'t1',format:'singles',raceTo:3,status:'active',
    entrants:[{id:'a',members:[{pid:null,name:'A'}]},{id:'b',members:[{pid:null,name:'B'}]},
              {id:'c',members:[{pid:null,name:'C'}]},{id:'d',members:[{pid:null,name:'D'}]}],
    matches:[{id:'m1',round:1,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',absent:[]},
             {id:'m2',round:1,sides:['c','d'],score:[0,0],status:'scheduled',absent:[]}]};
  assert.deepEqual(JSON.parse(JSON.stringify(h.revivalPool(h.tournament()))), [{id:'b'}],
    'only the loser of a played round-1 match is offered');
});
test('round 21 / owner item 3 + round 29 / owner item 1: the late arrival card opens a dialog', () => {
  const h = harness();
  const SRC = fs.readFileSync(path.join(__dirname, '../annotator/ops.js'), 'utf8');
  // Run both clicks instead of reading them: each one repaints, and both names are routed.
  const paints = [];
  const held = h.render;
  h.render = () => paints.push(1);
  h.dispatch('late-open');
  h.dispatch('late-cancel');
  h.render = held;
  assert.equal(paints.length, 2, 'each click repaints the shell');
  assert.ok(h.actions().includes('late-open') && h.actions().includes('late-cancel'),
    'the card opens the dialog, and the dialog closes it');
  assert.ok(SRC.includes("(sourceOpen?sourceModal():'')+(lateOpen?lateModal():'')"), 'the shell mounts it');
  assert.ok(SRC.includes('&&!pendingMatches.size&&registry.mayRepaint()'), 'and the poll asks the registry, not a screen variable (c3)');
  assert.ok(SRC.includes('holds:()=>deskOpen!==null||setupOpen||lateOpen}'), 'so the Tonight module owns the three cards that stand the repaint down');
  assert.ok(SRC.includes("${esc(eventParams(T))}</p></div>${lateCard()}${closeCard(drawn)}"), 'round 31: the control is a row of the event settings card');
  assert.ok(!SRC.includes('${entrantsCard()}${lateCard()}'), 'and the tab no longer carries a card of its own');
  // It renders only while the event is running: a finished event takes no late arrivals.
  (()=>{h.data.tournament={id:'t1',name:'Open',format:'singles',raceTo:3,status:'complete',entrants:[],matches:[]};h.data.players=[];return h.render=()=>{}})();
  assert.equal(h.lateCard(), '', 'a finished event offers nothing');
  (()=>{h.data.tournament.status='active';return h.data.players=[{id:'pa',name:'Ann',status:'Active',rating:700},{id:'pb',name:'Bo',status:'Inactive',rating:600}]})();
  const html = h.lateCard();
  assert.ok(html.includes('data-action="late-open"') && !html.includes('<form'), 'the card is one button, not a form');
  assert.ok(!html.includes('name="late_pid"') && !html.includes('data-action="late-add"'),
    'the fields and the submit moved into the dialog');
});

test('round 29 / owner item 1: the dialog compels the match-up and the teammate, in both languages', () => {
  const h = harness();
  const SRC = fs.readFileSync(path.join(__dirname, '../annotator/ops.js'), 'utf8');
  const PY = fs.readFileSync(path.join(__dirname, '../annotator/operations.py'), 'utf8');
  (()=>{h.data.tournament={id:'t1',name:'Open',format:'singles',raceTo:3,status:'active',entrants:[{id:'e1',members:[{name:'Ann'}]},{id:'e2',members:[{name:'Bo'}]}],matches:[{id:'m1',round:1,sides:['e1','e2'],score:[7,3],status:'complete',winnerId:'e1',result:'played',absent:[],sources:[]}]};h.data.players=[];return h.render=()=>{}})();
  const singles = h.lateModal();
  for (const value of ['none', 'revive', 'new']) {
    assert.ok(singles.includes(`name="late_opponent" value="${value}" required`),
      `the ${value} answer is offered for the match-up, and required`);
  }
  assert.ok(singles.includes('name="late_opponent_entrant"') && singles.includes('>Bo<'),
    'the second chance offers the round-1 losers, named');
  assert.ok(singles.includes('name="late_opponent_name"'), 'and the new person is named in the dialog');
  assert.ok(!singles.includes('name="late_partner"'), 'a singles event asks for no teammate');
  h.data.tournament.format='doubles';
  const doubles = h.lateModal();
  for (const value of ['none', 'revive', 'new']) {
    assert.ok(doubles.includes(`name="late_partner" value="${value}" required`),
      `a doubles event requires the teammate answer (${value})`);
  }
  assert.ok(doubles.includes('name="late_partner_entrant"') && doubles.includes('name="late_partner_name"'),
    'and offers the same two ways to name the teammate');
  assert.ok(SRC.includes("if(!opponent||(doubles&&!partner)){message(t('lateNeedChoice'),true);return}"),
    'the handler refuses a submit with a decision missing');
  assert.ok(SRC.includes("if(await action('entrant_add_late',body)){lateOpen=false;render()}"),
    'and a successful add closes the dialog and repaints, so the operator is not left looking at it');
  assert.ok(SRC.includes("if(f.getAttribute('id')==='late-form')") && SRC.includes("if(opponent==='revive')body.opponent_entrant") &&
    SRC.includes("if(doubles&&partner==='new')body.partner_name"),
    'the dialog submits through the form path, and the answers travel in the payload');
  assert.ok(PY.includes("if opponent not in ('none', 'revive', 'new'):") &&
    PY.includes("raise ValueError('Choose the teammate for a doubles event')"),
    'the server refuses a payload without the choices, whatever the client');
  assert.ok(PY.includes("final_round = max(match['round'] for match in t['matches'])"),
    'and a late bye slot no longer reads as the night being over');
});

test('round 22 / owner item 3: a chosen point on the scrubber survives the repaint', () => {
  const vs = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  // The console builds the input fresh on every render, so a refused seek used to reset the thumb to 0.
  assert.ok(/const seek = engine\(\)\.seekTime \|\| engine\(\)\.seek;/.test(vs),
    'the scrubber asks for a time seek, which is the call the engine honours');
  assert.ok(vs.includes('let pendingScrub = null;') && vs.includes('if (pendingScrub !== null) scrub.value = String(pendingScrub);'),
    'and the render shows that point instead of the engine frame (round 23)');
  assert.ok(vs.includes("const scrub = $('#vs-scrub');"), 'and the adapter still owns the input');
  assert.ok(!/if \(!engine\(\)\.seek\([^)]*\)\) render\(\);/.test(vs), 'the bare render-on-refusal is gone');
});
test('round 22 / owner item 3: play resumes from the point the operator chose', () => {
  const vs = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  // Measured before: a seek to 172740 followed by play put the scrubber back to 30.
  assert.ok(/const resume = Number\(\$\('#vs-scrub'\)\?\.value \|\| 0\);/.test(vs),
    'the chosen point is read from the scrubber');
  assert.ok(/if \(on && resume > 0 && target\.seek\) target\.seek\(resume\);/.test(vs),
    'and re-applied once playback starts');
  assert.ok(vs.includes("target.setPlaying(on);"), 'the play toggle still goes through the engine');
});
test('round 23 / owner item 1: the layer chips and the source line live with the scrubber', () => {
  // The strip is the stage's markup. The console hands over a host and no region of
  // its own, so the row can only be read here.
  const src = stageSource;
  const console_ = fs.readFileSync(path.join(__dirname, '../annotator/ops.js'), 'utf8');
  const strip = src.indexOf('<div class="vs-strip" id="vs-strip">');
  const track = src.indexOf('<div class="vs-track">');
  assert.ok(strip >= 0 && track > strip, 'the scrubber holds its track');
  assert.ok(src.slice(strip, track).includes('id="vs-layers"'), 'the scrubber carries the layer chips');
  assert.ok(!src.includes('vs-stagebar'), 'the layer chips are not a row of their own');
  assert.ok(!console_.includes('id="vs-strip"') && !console_.includes('vs-stagebar'), 'and the console authors neither');
});

// Owner round 25, workstream A: a refresh or a shared link lands on the viewer route and renders
// before the archive list has arrived, so the review id cannot be resolved yet. Dropping it there
// was why a direct load showed an empty console while an in-app click showed the viewer.
test('a direct load of a review route keeps its id until the archive list arrives', () => {
  const h = harness({hash: '#/records/review/261001'});
  h.data={revision:1,settings:{},tournament:{raceTo:7,entrants:[],matches:[]},players:[],history:[]};
  assert.equal(String(h.reviewId), '261001', 'the boot keeps the route id');
  assert.equal(h.archiveList.rows, null, 'the archive list has not been read yet');
  assert.ok(h.recordsScreen().includes('review-card'), 'the review shell is what renders');
  assert.equal(String(h.reviewId), '261001', 'the id survives the first render');
  // Once the list is known and does not hold the id, the id is dropped as before.
  h.archiveList.rows=[];
  assert.ok(!h.recordsScreen().includes('review-card'), 'an unknown id falls back to the archive');
  assert.equal(String(h.reviewId), 'null', 'a known-missing id is cleared');
  // A review that is not yet a night must not offer the import action for an empty broadcast.
  h.reviewId='261001';
  assert.ok(!h.recordsScreen().includes('data-action="bf-pick"'), 'no import action without a broadcast');
});

test('round 31 / owner item 3: the scrubber follows the pointer, a held step repeats, and the keys the app skips work', () => {
  const stage = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  // The drag: the press holds the point, the preview is throttled, and the last position always lands.
  assert.ok(stage.includes('let scrubHold = null;') && stage.includes('previewScrub(scrubHold);'),
    'the press holds the point');
  assert.ok(stage.includes('if (now - scrubAt >= 250) { scrubAt = now; seekScrub(want); }'),
    'the drag sends one preview seek each 250 ms, not one for each pixel');
  assert.ok(stage.includes('scrubTimer = setTimeout(() => { scrubTimer = 0; if (scrubHold !== null) { scrubAt = 0; seekScrub(scrubHold); } }, 250);'),
    'and a trailing seek carries the last position of a fast drag');
  assert.ok(stage.includes('if (scrubHold !== null) scrub.value = String(scrubHold);'),
    'the render keeps the held point under the thumb');
  assert.ok(stage.includes('if (pendingScrub !== null && Math.abs((Number(s.frame.t) || 0) - pendingScrub) <= 0.25) pendingScrub = null;'),
    'and drops the pin as soon as the engine lands on it');
  // The bubble states the target time, and the preview writes in place.
  assert.ok(stage.includes('id="vs-scrub-bubble"') && css.includes('.vs-scrub-bubble{'), 'the track carries the bubble');
  assert.ok(stage.includes('mark.textContent = scrubT(seconds);') && stage.includes('function scrubT(seconds)'),
    'the bubble states the time');
  const preview = stage.slice(stage.indexOf('function previewScrub'), stage.indexOf('function endScrub'));
  assert.ok(preview.length > 100 && !preview.includes('render()'),
    'and the preview writes in place: a shell render during a gesture would drop the pointer');
  // The keys: only the ones the app does not already own.
  assert.ok(stage.includes("const SCRUB_KEYS = ['j', 'J', 'l', 'L', 'k', 'K', 'Home', 'End'];"),
    'the transport words and the two ends');
  assert.ok(stage.includes("const SCRUB_RANGE_KEYS = [' ', 'Spacebar', ',', '.', 'ArrowLeft', 'ArrowRight'];"),
    'and the transport keys while the range itself has focus, where the app skips them');
  assert.ok(stage.includes("root.addEventListener('keydown', onKey, true);"), 'read before the app sees them');
  // A held step button repeats, which is what makes a long jump practical.
  assert.ok(stage.includes('stepTimer = setTimeout(tick, 350);') && stage.includes('stepTimer = setTimeout(tick, 90);'),
    'a held step button repeats after 350 ms, then each 90 ms');
  assert.ok(stage.includes("root.addEventListener('pointerdown', onPointerDown);") &&
    stage.includes("root.addEventListener('pointerup', onPointerUp);"), 'the pointer starts and ends it');
  assert.ok(stage.includes("root.removeEventListener('pointerdown', onPointerDown);"), 'and detach removes it');
});

test('the console hands the shell-state writer to the stage it mounts, as an option', () => {
  // Round 34, console candidate 3: the stage wrote the shell attributes through
  // window.OpsConsole, a second and undeclared seam. It now receives the writer in the
  // option bag the console already hands in, so one seam carries both directions.
  const h = harness();
  let bag = null;
  const mount = {removeAttribute() {}, querySelectorAll: () => [], classList: {toggle() {}, add() {}, remove() {}}};
  h.context.document.querySelector = selector => (selector === '#ops-shell' ? null : mount);
  h.context.window.VisionStage = {attach: options => { bag = options; return {render() {}, detach() {}}; }};
  h.renderSurface();
  assert.ok(bag, 'the console attaches the stage when the surface repaints');
  assert.strictEqual(typeof bag.setShell, 'function', 'and the writer for the shell state travels in the bag');
  bag.setShell({vsPanel: true});
  assert.strictEqual(h.shellState.vsPanel, '1', 'so a patch from the stage reaches the one shell writer');
  bag.setShell({vsPanel: false});
  assert.strictEqual(h.shellState.vsPanel, '0', 'and a patch that clears the column reaches it too');
});

test('one render() composes the console: the nav, the screen, the vision host and the poll', () => {
  // Round 34, console candidate 1: render() was one line of 2077 characters with 33 statements and
  // it rebuilt the whole page. The suite replaced it 42 times and never ran it, so every
  // composition bug the source comments record was invisible to the tests.
  const h = harness({richDom: true});
  h.render();
  const doc = h.context.document;
  const nav = doc.region('#nav');
  assert.ok(nav && nav.innerHTML.includes('data-tab="tonight"'), 'the nav is rebuilt with its destinations');
  assert.ok(nav.innerHTML.includes('aria-current="page"'), 'and it marks the destination the operator is on');
  const tabbar = doc.region('#tabbar');
  assert.ok(tabbar && tabbar.innerHTML.includes('data-tab="records"'), 'the phone bar follows the same destinations');
  const main = doc.region('#main');
  assert.ok(main && main.innerHTML.length > 0, 'the active screen paints into #main');
  assert.ok(doc.body.appended.some(node => node.selector === '#vision-host'), 'and the vision host is moved to the body');
  assert.strictEqual(h.timers.length, 0, 'the Tonight screen arms no poller: it has no live source to poll');
  tabClick(h, 'clock');
  h.render();
  const slot = doc.region('#ops-shell .clockbar');
  assert.ok(slot && slot.innerHTML.length > 0, 'the clock bar is painted on every render, whatever the venue state');
  assert.deepStrictEqual({...h.shellState}, {review: '0', vision: '', labelOverlay: '0', vsPanel: '0'},
    'and the one shell writer was told what the page shows');
});
test('one render() is a list of named steps, and deleting one call is a visible loss', () => {
  // Round 34, console candidate 1: render() was one line of 2077 characters holding 33 statements, so
  // a mutation experiment on it was indistinguishable from a syntax error. It is now a call list of
  // named steps, and this test is that list: it checks the names and their order, then runs the whole
  // render once per step and again with that one call deleted. The step's effect has to disappear, and
  // no other step may stand in for it.
  const h = harness({richDom: true});
  const names = ['haltPolling', 'paintDocument', 'paintNav', 'paintTabbar', 'paintShellState', 'paintClockBar',
    'mountVisionHost', 'paintActiveScreen', 'paintOverlays', 'paintReviewHost', 'armPolling', 'loadRecordsScreen',
    'paintLanguageChips', 'paintThemeChips', 'tick'];
  const called = (h.render.toString().match(/^ {2}([A-Za-z_$][\w$]*)\(\);?$/gm) || []).map(line => line.trim().replace(/\(\);?$/, ''));
  assert.deepStrictEqual(JSON.parse(JSON.stringify(called)), names,
    'render() calls the fifteen named steps, in the order they own the page');
  for (const name of names) {
    assert.equal(source.split(`\n  ${name}()`).length - 1, 1, `render() calls ${name}() once, on a line of its own`);
    assert.equal((source.match(new RegExp(`\\bfunction ${name}\\(`, 'g')) || []).length, 1, `${name}() is defined once`);
  }
  // Deleting the call, not the definition: the step stays in the file and nothing calls it.
  const without = name => {
    const line = `\n  ${name}()`;
    const at = source.indexOf(line);
    assert.ok(at > -1, `${name}() is called on a line of its own`);
    const end = source[at + line.length] === ';' ? at + line.length + 1 : at + line.length;
    return source.slice(0, at) + source.slice(end);
  };
  const page = (text, tab) => {
    const probe = harness({richDom: true, source: text});
    if (tab) probe.tab = tab;
    return probe;
  };
  const painted = (doc, selector, needle) => ((doc.region(selector)?.innerHTML || '').includes(needle) ? 'painted' : 'absent');
  const stamp = value => JSON.parse(JSON.stringify(value));
  const steps = [
    {name: 'haltPolling', want: 8,
     claim: 'the two pollers are stood down before the guard, so a render with no data still stops them',
     see: text => { const p = page(text); p.data = null; p.liveGeneration = 7; p.render(); return p.liveGeneration; }},
    {name: 'paintDocument', want: 'zh-CN/dark',
     claim: 'the document carries the language and the scheme the console painted in',
     see: text => { const p = page(text); p.lang = 'zh'; p.render(); const el = p.context.document.documentElement; return `${el.lang}/${el.dataset.theme}`; }},
    {name: 'paintNav', want: 'painted',
     claim: 'the nav is rebuilt, and it marks the destination the operator is on',
     see: text => { const p = page(text); p.render(); return painted(p.context.document, '#nav', 'aria-current="page"'); }},
    {name: 'paintTabbar', want: 'painted',
     claim: 'the phone bar follows the same destinations',
     see: text => { const p = page(text); p.render(); return painted(p.context.document, '#tabbar', 'data-tab="records"'); }},
    {name: 'paintShellState', want: 'live',
     claim: 'the one shell writer is told what the page shows',
     see: text => { const p = page(text, 'vision'); p.render(); return p.shellState.vision; }},
    {name: 'paintClockBar', want: 'painted',
     claim: 'the clock bar is painted on every render, whatever the venue state',
     see: text => { const p = page(text), doc = p.context.document; doc.region('#ops-shell .clockbar').innerHTML = ''; p.render(); return painted(doc, '#ops-shell .clockbar', 'data-action="clock-toggle"'); }},
    {name: 'mountVisionHost', want: 'painted',
     claim: 'the vision host is moved to the body, where the stage lives',
     see: text => { const p = page(text); p.render(); return p.context.document.body.appended.some(node => node.selector === '#vision-host') ? 'painted' : 'absent'; }},
    {name: 'paintActiveScreen', want: 'painted',
     claim: 'the screen the registry names is mounted into #main',
     see: text => { const p = page(text); p.render(); return (p.context.document.region('#main')?.innerHTML || '').length ? 'painted' : 'absent'; }},
    {name: 'paintOverlays', want: 'painted',
     claim: 'an open source rail lands over whichever screen is showing',
     see: text => { const p = page(text); p.data.sources = [{id: 's1', url: 'https://www.twitch.tv/ttpoolfriday'}]; p.sourceOpen = true; p.render(); return (p.context.document.region('#main')?.inserted || []).length ? 'painted' : 'absent'; }},
    {name: 'paintReviewHost', want: 'painted',
     claim: 'the review host takes the height of #main before it mounts',
     see: text => { const p = page(text); p.render(); return (p.context.document.region('#main')?.toggles || []).length ? 'painted' : 'absent'; }},
    {name: 'armPolling', want: 'armed',
     claim: 'the clock screen arms the ops beat, after the live poll has its baseline',
     see: text => { const p = page(text, 'clock'); p.data.tournament.status = 'active'; p.render(); return p.timers.some(timer => timer.ms === 4000) ? 'armed' : 'silent'; }},
    {name: 'loadRecordsScreen', want: '/api/vods/queue+/api/vods/recent',
     claim: 'the render that makes Records the screen asks for the archive and the queue',
     see: text => { const p = page(text, 'records'), asked = []; p.context.fetch = async url => { asked.push(String(url).split('?')[0]); return {ok: true, json: async () => ({channels: [], queue: []})}; }; p.render(); return asked.sort().join('+') || 'none'; }},
    {name: 'paintLanguageChips', want: 'false/true',
     claim: 'the chip row says which language is in force, not only which ones exist',
     see: text => { const p = page(text); p.lang = 'zh'; p.render(); return p.context.document.nodes('[data-lang]').map(node => node.attributes['aria-pressed']).join('/'); }},
    {name: 'paintThemeChips', want: 'true/false',
     claim: 'the scheme row says which scheme is in force',
     see: text => { const p = page(text); p.render(); return p.context.document.nodes('#ops-shell button[data-theme]').map(node => node.attributes['aria-pressed']).join('/'); }},
    {name: 'tick', want: 'painted',
     claim: 'the clock the operator reads is written from the one timer state',
     see: text => { const p = page(text); p.render(); return p.context.document.nodes('[data-clock]').map(node => node.textContent).join('') ? 'painted' : 'absent'; }}
  ];
  for (const {name, claim, want, see} of steps) {
    assert.deepStrictEqual(stamp(see(source)), want, `a render() runs ${name}(): ${claim}`);
    assert.notDeepStrictEqual(stamp(see(without(name))), want, `and ${name}() is what does it: ${claim}`);
  }
  assert.deepStrictEqual(steps.map(step => step.name), names, 'every step of the composition is walked, so a new one has to answer too');
});
// ---- One action registry, two modules: coverage is a checkable property ------------------------
// The console and the stage route a click through one table each, and one registry holds both. These
// tests read the live table out of the running modules and the emitters out of the page scripts, so
// a control that renders a name no module handles, or a row no control can reach, is a failing test.
const PAGE_SCRIPTS = ['ops.js', 'vision-stage.js', 'app.js', 'clock-sync.js'];
const pageText = Object.fromEntries(PAGE_SCRIPTS.map(f => [f, fs.readFileSync(path.join(__dirname, '../annotator/', f), 'utf8')]));
// A helper call carries a nested call in its first argument, so the reader splits the arguments by
// depth instead of by a comma. A literal first argument that is not a string yields nothing.
function callArguments(text, name) {
  const found = [], re = new RegExp(`\\b${name}\\(`, 'g');
  let m;
  while ((m = re.exec(text))) {
    let depth = 1, i = re.lastIndex, arg = '', args = [], quote = null;
    for (; i < text.length && depth > 0; i++) {
      const c = text[i];
      if (quote) { if (c === '\\') { arg += c + text[++i]; continue; } if (c === quote) quote = null; arg += c; continue; }
      if (c === "'" || c === '"' || c === '`') { quote = c; arg += c; continue; }
      if (c === '(') depth++;
      if (c === ')') { depth--; if (!depth) break; }
      if (c === ',' && depth === 1) { args.push(arg); arg = ''; continue; }
      arg += c;
    }
    args.push(arg);
    found.push(args);
    re.lastIndex = i;
  }
  return found;
}
const stringLiteral = value => {
  const text = String(value || '').trim();
  const m = text.match(/^'([^']*)'$/) || text.match(/^"([^"]*)"$/);
  return m ? m[1] : null;
};
// Five ways a page script names an action: a literal attribute, a ternary inside an attribute, the
// console's btn() helper, the stage's btnHTML() helper, and the emptyNote() invitation. The two
// helpers write the console attribute, so the stage reader must not count them.
function emittedInto(text, attribute, helpers = false) {
  const out = new Set();
  for (const m of text.matchAll(new RegExp(`${attribute}="([^"$]*)"`, 'g'))) if (m[1]) out.add(m[1]);
  for (const m of text.matchAll(new RegExp(`${attribute}='([^'$]*)'`, 'g'))) if (m[1]) out.add(m[1]);
  for (const m of text.matchAll(new RegExp(`${attribute}="\\$\\{([^}]*)\\}"`, 'g'))) for (const q of m[1].matchAll(/'([^']+)'/g)) out.add(q[1]);
  if (helpers) {
    for (const name of ['btn', 'btnHTML']) for (const args of callArguments(text, name)) { const v = stringLiteral(args[1]); if (v) out.add(v); }
    for (const args of callArguments(text, 'emptyNote')) { const v = stringLiteral(args[1]); if (v) out.add(v); }
  }
  for (const n of [...out]) if (!n || n.startsWith('tab:')) out.delete(n);   // a tab name is a route, not an action
  return out;
}
const CONSOLE_EMITTED = new Set([...emittedInto(pageText['ops.js'], 'data-action', true), ...emittedInto(pageText['vision-stage.js'], 'data-action', true)]);
const STAGE_EMITTED = new Set([...emittedInto(pageText['vision-stage.js'], 'data-vs-action'), ...emittedInto(pageText['app.js'], 'data-vs-action')]);
// The rows no control reaches today. Naming them here is the point: a new one fails this test until
// somebody decides whether it is a row to delete or a control that was never written.
const UNREACHABLE_ROWS = {ops: ['card-open', 'chat', 'focus', 'live-detector', 'open-setup', 'source-delete', 'source-select', 'tl-open-night'], 'vision-stage': []};
// The page builds the registry in the stage, which loads first, and the console reads it. A second
// module is a second namespace in the same object, so a name both tables hold stays two rows.
function sharedRegistry(h) {
  if (!h.context.window.VisionStage) vm.runInContext(stageSource, h.context);
  const registry = h.registry();
  assert.ok(registry, 'the two modules share one registry');
  return registry;
}
test('every action a control renders resolves to an entry in the shared table', () => {
  const registry = sharedRegistry(harness());
  assert.deepStrictEqual([...CONSOLE_EMITTED].filter(name => !registry.has('ops', name)), [],
    'every rendered console action has a row in the console table');
  assert.deepStrictEqual([...STAGE_EMITTED].filter(name => !registry.has('vision-stage', name) && !registry.isField('vision-stage', name)), [],
    'every rendered stage action has a row in the stage table, or is a declared form field');
  assert.ok(STAGE_EMITTED.has('link-target') && registry.isField('vision-stage', 'link-target') && !registry.has('vision-stage', 'link-target'),
    'link-target is read as a field, never dispatched, and the table says so');
  assert.ok(CONSOLE_EMITTED.size > 80 && STAGE_EMITTED.size > 60, 'and both readers found the controls, so an empty scan cannot pass');
});
test('every entry has an emitter, or is named on the list of rows no control reaches', () => {
  const registry = sharedRegistry(harness());
  assert.deepStrictEqual([...registry.names('ops').filter(name => !CONSOLE_EMITTED.has(name))].sort(), UNREACHABLE_ROWS.ops,
    'the console table says which rows no control renders, and names nothing else');
  assert.deepStrictEqual([...registry.names('vision-stage').filter(name => !STAGE_EMITTED.has(name))].sort(), UNREACHABLE_ROWS['vision-stage'],
    'every stage row is a control the operator can press');
  assert.deepStrictEqual([...registry.modules()].sort(), Object.keys(UNREACHABLE_ROWS).sort(),
    'and every module has to answer the question, so a third module cannot pass by being absent');
});
test('both modules route through one table, and the click runs the row the table holds', () => {
  const h = harness();
  assert.strictEqual(h.registry(), null, 'the console alone has no shared registry: it dispatches through its own table');
  const registry = sharedRegistry(h);
  assert.deepStrictEqual([...registry.modules()].sort(), ['ops', 'vision-stage'], 'one registry holds both modules');
  assert.deepStrictEqual([...h.actions()].sort(), [...registry.names('ops')].sort(),
    'the handle reads the same console table the click reads, not a copy of it');
  assert.deepStrictEqual([...registry.names('ops').filter(name => registry.names('vision-stage').includes(name))].sort(),
    ['chat', 'live-detector', 'live-start', 'live-stop'], 'a name both tables hold stays two rows in two namespaces');
  assert.strictEqual(registry.run('ops', 'no-such-action-exists'), undefined, 'a name no table holds is a no-op, not a throw');
  assert.strictEqual(registry.find('live-start').length, 2, 'and a name can be found in more than one module');
  // The dispatcher reads the table when the click arrives: swap a row and the swapped one runs.
  const table = registry.module('ops'), held = table['archive-reload'], seen = [];
  assert.strictEqual(registry.row('ops', 'archive-reload'), held, 'the table holds the row the click runs');
  table['archive-reload'] = () => { seen.push('swapped'); };
  h.dispatch('archive-reload');
  table['archive-reload'] = held;
  assert.deepStrictEqual(seen, ['swapped'], 'so the click runs the row the table holds now, not a branch chain');
});
test('no branch chain is left in either module: the table is the only route', () => {
  assert.strictEqual((source.match(/if\(a===/g) || []).length, 0, 'the console click handler has no if-chain left');
  const at = stageSource.indexOf('const stageAct = (() => {');
  const table = stageSource.slice(at, stageSource.indexOf('\nfunction act(', at));
  assert.ok(at > 0 && table.length > 1000, 'the stage table is where the dispatcher reads');
  assert.strictEqual((table.match(/\bcase '/g) || []).length, 0, 'the stage act() has no case chain left');
  assert.strictEqual((source.match(/opsAct\.run\(/g) || []).length, 1, 'one call site reaches the console table');
  assert.strictEqual((table.match(/registry\.run\('vision-stage'/g) || []).length, 1, 'one call site reaches the stage table');
});
