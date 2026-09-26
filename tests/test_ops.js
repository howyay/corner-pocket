'use strict';
// Run: node --test tests/test_ops.js. No DOM or network dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../annotator/ops.js'), 'utf8');
function harness() {
  const handlers = {}, storage = {};
  const document = {addEventListener(event, fn) { handlers[event] = fn; }, querySelector() { return {}; }, querySelectorAll() { return []; }, documentElement: {}};
  const context = {document, localStorage: {getItem: key => storage[key] || null, setItem: (key, value) => storage[key] = value}, window: {addEventListener() {}}, setInterval() {}, setTimeout() {}, clearTimeout() {}, URL, console, confirm: () => true, FormData: function(form) { return Object.entries(form.values); }};
  vm.createContext(context);
  vm.runInContext(source.replace("(() => {", '').replace('});reload();', '});').replace(/\}\)\(\);\s*$/, ''), context);
  vm.runInContext("data={revision:1,settings:{},tournament:{raceTo:7,entrants:[],matches:[]},players:[],history:[]}; calls=[]; realAction=action; action=async(name,payload)=>{calls.push({name,payload});return true}", context);
  return {context, handlers, evaluate: expression => vm.runInContext(expression, context)};
}
test('live controls keep the dataset/channel allowlist and the latency caveat', () => {
  const h = harness();
  assert.deepEqual(JSON.parse(h.evaluate("JSON.stringify(liveSource('dataset:highlight'))")), {kind:'dataset', dataset:'highlight'});
  assert.deepEqual(JSON.parse(h.evaluate("JSON.stringify(liveSource('twitch:saved-id'))")), {kind:'twitch', source_id:'saved-id'});
  h.evaluate("data.sources=[{id:'channel',url:'https://www.twitch.tv/examplechannel'},{id:'vod',url:'https://www.twitch.tv/videos/123'}, {id:'bad',url:'https://example.com/x'}]");
  const channels = h.evaluate('JSON.stringify(channels())');
  assert.equal(channels, '[{"id":"channel","url":"https://www.twitch.tv/examplechannel","channel":"examplechannel"}]');
  assert.equal(h.evaluate('channelOf("channel")'), 'examplechannel');
  assert.equal(h.evaluate('regulars().length'), 0);
  const adapter = fs.readFileSync(path.join(__dirname, '../annotator/vision-stage.js'), 'utf8');
  assert.ok(adapter.includes('data-vs-action="live-start"') && adapter.includes('data-vs-action="live-stop"'));
  assert.ok(adapter.includes('data-vs-value="${d}"') && adapter.includes("['table','person','ball']"),
    'the live row offers table, person and the trained ball stage');
  assert.ok(adapter.includes('not glass-to-glass'));
  assert.ok(adapter.includes('data-vs-action="pick-live"'));
});
test('live polling cancels on navigation and only runs inside Vision', () => {
  const h = harness();
  h.evaluate("polls=[]; pollLive=g=>polls.push(g); document.querySelector=document.querySelector||(()=>null); tab='vision';syncLivePolling()");
  assert.equal(h.evaluate('polls.length'), 1);
  h.evaluate("tab='floor';syncLivePolling()");
  assert.equal(h.evaluate('polls.length'), 1);
  assert.equal(h.evaluate('liveGeneration'), 2);
  h.evaluate("tab='vision';document.hidden=true;syncLivePolling()");
  assert.equal(h.evaluate('polls.length'), 1);
  h.evaluate('document.hidden=false;syncLivePolling()');
  assert.equal(h.evaluate('polls.length'), 2);
});
test('live start and stop send only processor contract fields', async () => {
  const h = harness();
  h.context.fetch=async (url,options)=>{h.context.sent={url,payload:JSON.parse(options.body)};return {ok:true,json:async()=>({status:'running'})}};
  await h.evaluate("liveChoice='twitch:channel';liveDetectors=['person'];liveAction('start')");
  assert.deepEqual(h.context.sent,{url:'/api/live',payload:{action:'start',source:{kind:'twitch',source_id:'channel'},detectors:['person']}});
  await h.evaluate("liveAction('stop')");
  assert.deepEqual(h.context.sent.payload,{action:'stop'});
});
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
  h.context.window.CornerPocketReview = {snapshot: () => attached ? engineSnap : null, setLiveAttempt() {}, clearLiveError() {}, applyLiveStatus() {}};
  h.context.fetch = async (url, options) => { h.context.sent = JSON.parse(options.body); return {ok:true, json: async () => ({state:'starting'})}; };
  // The shell's own attachSurface() wires the adapter, exactly as on the Vision tab.
  const mount = {querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, contains: () => true};
  const shellQuery = h.context.document.querySelector;
  h.context.document.querySelector = selector => selector === '#vision-surface' ? mount : shellQuery(selector);
  h.evaluate('attachSurface()');
  h.evaluate('renderSurface=()=>{}');
  const VS = h.context.window.VisionStage;
  attached = true;
  // Only the live row: the Frame detectors row below it has its own table/person boxes.
  const ticked = () => ['table','person','ball'].filter(d => new RegExp(`data-vs-action="live-detector" data-vs-value="${d}" checked`).test(VS.sourcePanelHTML(engineSnap)));
  const click = (value, checked) => VS.act('live-detector', value, {checked});
  assert.deepEqual(ticked(), ['table','person'], 'the defaults are shown');
  click('person', false);
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(liveDetectors)')), ['table']);
  assert.deepEqual(ticked(), ['table'], 'an untick is shown');
  click('ball', true);
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(liveDetectors)')), ['table','ball'], 'Person stays off when Ball goes on');
  assert.deepEqual(ticked(), ['table','ball'], 'and the boxes say so');
  await h.evaluate('liveAction("start")');
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
  await h.evaluate('pollLive(liveGeneration)');
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
    h.context.fetch = async () => { throw new TypeError('Failed to fetch'); };
    h.evaluate(`lang='${lang}'; tab='vision'; document.hidden=false`);
    await h.evaluate('pollLive(liveGeneration)');   // must resolve: nothing is thrown out of the catch
    assert.equal(messageNode.textContent, `${prefix}Failed to fetch`, `${lang}: the error reaches the operator`);
    assert.equal(messageNode.className, 'error', `${lang}: styled as an error`);
    assert.deepEqual(timers.filter(ms => ms === 500), [500], `${lang}: and polling carries on`);
  }
  // A poll from a superseded generation says nothing: navigation already cancelled it.
  const h = harness(), messageNode = {textContent:'', className:''};
  h.context.document.querySelector = selector => selector === '#message' ? messageNode : null;
  h.context.fetch = async () => { throw new TypeError('Failed to fetch'); };
  await h.evaluate('pollLive(liveGeneration - 1)');
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
  assert.equal(h.evaluate("t('vision')"), 'Vision');
  assert.ok(source.includes("['floor','setup','matches','vision','players','status']"));
  assert.ok(!source.includes('review-frame'));
  assert.ok(!source.includes('src="/app.html"'));
  // The sub-tab machinery is gone: no mode table, no data-vision buttons, no dead host.
  assert.ok(!source.includes('reviewModes'));
  assert.ok(!source.includes('visionNavigation'));
  assert.ok(!source.includes('data-vision'));
  assert.ok(!source.includes('visionTab'));
  assert.ok(!source.includes('vision-host-host'));
  assert.ok(!source.includes('twitchEmbed'));
  const surface = h.evaluate('visionSurface()');
  for (const id of ['id="vs-chips"','id="vs-cues"','id="vs-stage"','id="vs-inspector"','id="vs-strip"','data-sheet-tab="cues"','data-sheet-tab="inspector"','id="vs-frame"','id="vs-marks"','data-vs-action="freeze"']) assert.ok(surface.includes(id), `vision surface missing ${id}`);
  assert.ok(surface.indexOf('id="vs-frame"') < surface.indexOf('id="vs-inspector"'));
});
test('dirty or busy review vetoes top-level and subtab navigation', async () => {
  for (const dataset of [{tab:'vision'}, {tab:'setup'}, {action:'floor'}]) {
    const h = harness();
    h.context.window.CornerPocketReview = {canLeave: () => false, activate: () => false};
    h.evaluate("tab='vision'");
    await h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
    assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify([tab,lang,theme])')), ['vision','en','dark']);
  }
});
test('the player modal stays open until an action actually dismisses it', async () => {
  // Every shell click ran `selected=null` after the player-delete line, so the
  // modal closed on the next render (a language switch, a failed write) and a
  // cancelled delete closed it too.
  const click = (h, dataset) => h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
  const h = harness();
  h.evaluate("render=()=>{}; data.players=[{id:'p1',name:'Ana',status:'Active',rating:80,createdAt:'2026-09-01T00:00:00Z'}]");
  await click(h, {action:'select-player', id:'p1'});
  assert.equal(h.evaluate('selected'), 'p1', 'selecting a player opens the modal');
  await click(h, {lang:'zh'});
  assert.equal(h.evaluate('selected'), 'p1', 'a language switch keeps it open');
  await click(h, {action:'filter', value:'Active'});
  assert.equal(h.evaluate('selected'), 'p1', 'so does any other shell button');
  h.context.confirm = () => false;
  await click(h, {action:'player-delete', id:'p1'});
  assert.equal(h.evaluate('selected'), 'p1', 'a cancelled delete keeps it open');
  assert.equal(h.evaluate('calls.length'), 0, 'and deletes nothing');
  h.context.confirm = () => true;
  h.evaluate('action=async(name,payload)=>{calls.push({name,payload});return false}');
  await click(h, {action:'player-delete', id:'p1'});
  assert.equal(h.evaluate('selected'), 'p1', 'a refused delete keeps it open, beside its error');
  h.evaluate('action=async(name,payload)=>{calls.push({name,payload});return true}');
  await click(h, {action:'player-delete', id:'p1'});
  assert.equal(h.evaluate('selected'), null, 'a delete that happened closes it');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls.map(c=>c.name))')), ['player_delete','player_delete']);
  await click(h, {action:'select-player', id:'p1'});
  await click(h, {action:'close-modal'});
  assert.equal(h.evaluate('selected'), null, 'and so does the close button');
});
test('shell does not intercept review clicks or form submissions', async () => {
  const h = harness();
  const target = {closest: () => ({})};
  await h.handlers.submit({target,preventDefault(){assert.fail('review submit intercepted')}});
  await h.handlers.click({target});
  assert.equal(h.evaluate('calls.length'), 0);
});
test('review host is outside the disposable shell main', () => {
  const html = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
  assert.ok(html.indexOf('</main>') < html.indexOf('id="vision-host"'));
  assert.ok(html.indexOf('/app.js') < html.indexOf('/ops.js'));
});
test('appearance changes retain review DOM without asking to discard', async () => {
  const h = harness();
  h.context.window.CornerPocketReview = {canLeave: () => assert.fail('appearance must preserve edits')};
  h.evaluate('render=()=>{}');
  for (const dataset of [{theme:'light'}, {lang:'zh'}]) await h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
  assert.equal(h.evaluate('theme'), 'light');
  assert.equal(h.evaluate('lang'), 'zh');
});
test('table release and registration attendance use existing action API', async () => {
  const h = harness();
  for (const dataset of [{action:'unschedule',id:'m1'}, {action:'entrant-absence',id:'e1',absent:'true'}]) await h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name:'match_unschedule',payload:{id:'m1'}},{name:'entrant_absence',payload:{id:'e1',absent:true}}]);
});
test('delayed matches restore attendance rather than offering invalid scheduling', () => {
  const h = harness();
  h.evaluate("data.tournament.matches=[{id:'m1',round:1,status:'delayed',sides:['e1','e2'],absent:['e1'],score:[0,0]}]");
  const html = h.evaluate('matchesScreen()');
  assert.ok(html.includes('data-action="absence"'));
  assert.ok(!html.includes('data-action="schedule"'));
});
test('Floor focus picker includes live and delayed tables', () => {
  const h = harness();
  h.evaluate("data.tournament.matches=['live','delayed'].map((status,i)=>({id:'m'+i,table:i+1,round:1,status,sides:['e1','e2'],absent:status==='delayed'?['e1']:[],score:[0,0]}));data.notes=[]");
  const html = h.evaluate('floorScreen()');
  const picker = html.match(/<select id="focus-match">(.*?)<\/select>/)[1];
  assert.ok(picker.includes('value="m0"'));
  assert.ok(picker.includes('value="m1"'));
});
test('sticky header scroll inset belongs to the document scrolling root', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('html{scroll-padding-top:270px}'));
  assert.ok(!css.includes(':is(#ops-shell, #ops-footer){scroll-padding-top'));
});
test('harden: fields show focus that a border shorthand cannot erase; names and states are announced', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const focus = css.match(/input:focus,[^{]*textarea:focus\{([^}]*)\}/);
  assert.ok(focus, 'one field focus rule');
  assert.match(focus[1], /box-shadow:[^;]*var\(--brass\)/, 'the focus ring is a box-shadow, so .vs-field border:1px cannot remove it');
  assert.ok(!/animation:none!important;transition:none!important/.test(css), 'reduced motion keeps state changes instead of a global kill');
  const html = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
  assert.ok(!html.includes('aria-label="Color theme"'), 'the theme group name is bilingual');
  const surface = harness().evaluate('visionSurface()');
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
  const html = h.evaluate("playerForm({id:'p1',name:'A',notes:'</textarea><script>x</script>'})");
  assert.ok(html.includes('name="notes" maxlength="4000"'));
  assert.ok(html.includes('&lt;/textarea&gt;'));
  assert.ok(!html.includes('<script>'));
});
test('every shell word has EN and 中 copy, so no raw key renders (Regulars roster heading)', () => {
  const h = harness();
  // Every literal t('key') in the shell must resolve in both languages: t() falls
  // back to the key itself, which is how "rosterTitle" reached the screen.
  const words = JSON.parse(h.evaluate('JSON.stringify(words)'));
  const used = [...new Set([...source.matchAll(/\bt\('([A-Za-z0-9_]+)'\)/g)].map(m => m[1]))];
  assert.ok(used.length > 90, `the scan found the shell's keys: ${used.length}`);
  const missing = used.filter(key => !Array.isArray(words[key]) || !words[key][0] || !words[key][1]);
  assert.deepEqual(missing, [], 'every t() key has an EN and a 中 entry');
  h.evaluate("data.players=[{id:'p1',name:'Ana',status:'Active',rating:80,createdAt:'2026-09-01T00:00:00Z'}]");
  for (const [lang, heading] of [['en', words.rosterTitle[0]], ['zh', words.rosterTitle[1]]]) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('playersScreen()');
    const headings = [...html.matchAll(/<h3[^>]*>([^<]*)<\/h3>/g)].map(m => m[1]);
    assert.ok(headings.includes(heading), `${lang}: the roster heading is its copy: ${JSON.stringify(headings)}`);
    const raw = used.filter(key => new RegExp(`>${key}<`).test(html));
    assert.deepEqual(raw, [], `${lang}: no raw key renders as text on Regulars`);
  }
  assert.ok(/[\u4e00-\u9fff]/.test(words.rosterTitle[1]), 'the 中 heading is Chinese');
});
test('Back room retains nine truthful deferred roadmap areas', () => {
  const h = harness();
  const html = h.evaluate('roadmapPanel()');
  assert.equal((html.match(/<tr>/g)||[]).length, 10);
  assert.ok(html.includes('not live monitoring'));
  assert.ok(html.includes('accuracy unverified'));
  h.evaluate("lang='zh'");
  assert.ok(h.evaluate('roadmapPanel()').includes('尚无自动化'));
});
function submission(formId, values, submitter = {}) {
  return {preventDefault() {}, target: {id: {shadowedByNamedControl: true}, getAttribute: () => formId, classList: {contains: () => false}, querySelectorAll: () => [], values}, submitter};
}
test('named id control cannot shadow form identity; sign saves score before completion', async () => {
  const h = harness();
  await h.handlers.submit(submission('score-form', {id: 'match-1', a: '7', b: '4'}, {name: 'sign'}));
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'match_score', payload: {id: 'match-1', score: [7, 4]}}, {name: 'match_complete', payload: {id: 'match-1'}}]);
});
test('failed score write never signs a result', async () => {
  const h = harness();
  h.evaluate('action=async(name,payload)=>{calls.push({name,payload});return false}');
  await h.handlers.submit(submission('score-form', {id: 'match-1', a: '7', b: '4'}, {name: 'sign'}));
  assert.equal(h.evaluate('calls.length'), 1);
  assert.equal(h.evaluate('calls[0].name'), 'match_score');
});
test('save-only and cancelled confirmation do not complete a match', async () => {
  const h = harness();
  await h.handlers.submit(submission('score-form', {id: 'match-1', a: '6', b: '4'}));
  assert.equal(h.evaluate('calls.length'), 1);
  h.context.confirm = () => false;
  await h.handlers.submit(submission('score-form', {id: 'match-1', a: '7', b: '4'}, {name: 'sign'}));
  assert.equal(h.evaluate('calls.length'), 1);
});
test('registration without a guest name or a regular is stopped at the guest field, in both languages', async () => {
  const h = harness();
  const guest = {validity: '', reported: 0, setCustomValidity(text) { this.validity = text; }, reportValidity() { this.reported++; return false; }};
  const form = values => ({preventDefault() {}, target: {getAttribute: () => 'entrant-form', classList: {contains: () => false}, querySelector: sel => sel === '[name=guest0]' ? guest : null, querySelectorAll: () => [], values}});
  for (const blank of [{pid0: '', guest0: ''}, {pid0: '', guest0: '   '}, {pid0: ''}]) await h.handlers.submit(form(blank));
  assert.equal(h.evaluate('calls.length'), 0, 'a blank guest never reaches the server');
  assert.equal(guest.reported, 3);
  assert.equal(guest.validity, 'Type a guest name or choose a regular.');
  h.evaluate("lang='zh'");
  await h.handlers.submit(form({pid0: '', guest0: ''}));
  assert.equal(guest.validity, '请输入访客姓名，或选择一位常客。');
  await h.handlers.submit(form({pid0: '', guest0: '  Ann  '}));
  await h.handlers.submit(form({pid0: 'p1', guest0: ''}));
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls.map(c => c.payload))')), [{members: [{name: 'Ann'}]}, {members: [{pid: 'p1'}]}]);
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
  assert.equal(h.evaluate('calls.length'), 0, 'nothing blank reaches the server');
  h.evaluate("lang='zh'");
  await h.handlers.submit(form('note-form', '', {text: '   '}));
  assert.equal(field.validity, '请填写此项，仅有空格不算。');
  field.value = 'Ada';
  await h.handlers.submit(form(null, 'player-form', {name: 'Ada', status: 'Active'}));
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'player_save', payload: {name: 'Ada', status: 'Active'}}]);
});
test('a stream link the server refuses is explained before or after the request, in both languages', async () => {
  const h = harness();
  for (const path of ['subscriptions', 'inventory', 'wallet', 'jobs', 'turbo', 'Wallet']) {
    assert.equal(h.evaluate(`parseSource('https://www.twitch.tv/${path}')`), null, `${path} is a Twitch page, not a channel`);
  }
  assert.equal(h.evaluate("parseSource('https://www.twitch.tv/examplechannel').channel"), 'examplechannel');
  await h.handlers.submit(submission('source-form', {url: 'https://www.twitch.tv/wallet'}));
  assert.equal(h.evaluate('calls.length'), 0, 'a reserved Twitch page never reaches the server');
  assert.equal(h.evaluate("validationMessage('Source already added')"), 'Source already added');
  h.evaluate("lang='zh'");
  assert.equal(h.evaluate("validationMessage('Source already added')"), '这个直播源已经添加过了。');
  assert.equal(h.evaluate("validationMessage('Use a Twitch channel or videos/<digits> URL')"), '请输入Twitch频道网址或 videos/<数字> 视频网址。');
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
  assert.equal(h.evaluate("validationMessage('All tables are in use')"), 'All tables are in use');
  h.evaluate("lang='zh'");
  assert.equal(h.evaluate("validationMessage('All tables are in use')"), '所有球台都在使用中，请先释放一张球台。');
});
test('appearance form serializes numbers and unchecked diamonds correctly', async () => {
  const h = harness();
  await h.handlers.submit(submission('appearance-form', {clothColor: '#1f4a70', lampGlow: '0.4'}));
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls[0])')), {name: 'settings_update', payload: {clothColor: '#1f4a70', lampGlow: 0.4, showDiamonds: false}});
});
test('adding a regular never sends a rating the form did not collect; editing keeps it', async () => {
  const h = harness();
  const playerForm = values => ({preventDefault() {}, target: {getAttribute: () => null, classList: {contains: c => c === 'player-form'}, querySelectorAll: () => [], values}});
  assert.ok(!h.evaluate('playerForm()').includes('name="rating"'), 'create form has no rating field');
  await h.handlers.submit(playerForm({name: 'Ada', status: 'Active'}));
  h.evaluate('realCall=calls[0]');
  assert.equal(h.evaluate("'rating' in realCall.payload"), false, 'no rating key, so JSON never carries NaN as null');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls[0])')), {name: 'player_save', payload: {name: 'Ada', status: 'Active'}});
  await h.handlers.submit(playerForm({id: 'p1', name: 'Ada', rating: '640', status: 'Active', notes: ''}));
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls[1])')), {name: 'player_save', payload: {id: 'p1', name: 'Ada', rating: 640, status: 'Active', notes: ''}});
});
test('failed API response localizes primary copy and preserves exact optional detail', async () => {
  const h = harness();
  h.evaluate("lang='zh'; render=()=>{}; errors=[]; message=(text,error,detail)=>errors.push({text,error,detail}); action=realAction");
  h.context.fetch = async () => ({ok: false, status: 400, json: async () => ({error: 'Schedule match before scoring'})});
  assert.equal(await h.evaluate("action('match_score',{id:'match-1',score:[7,4]})"), false);
  assert.match(h.evaluate('errors[0].text'), /请先安排比赛上台，再记录比分/);
  assert.equal(h.evaluate('errors[0].detail'), 'Schedule match before scoring');
  assert.ok(!h.evaluate('errors[0].text').includes('Schedule match'));
  assert.equal(h.evaluate('busy'), false);
});

test('the clock paints the true remaining time on the first render, in every view', () => {
  const h = harness();
  // The defect: clockHTML() hardcoded 0:30, so any re-render (switching to
  // Vision, a stream repainting the strip) flashed a value the clock was not at.
  h.evaluate("timer={duration:60,remaining:12.4,deadline:null}");
  const painted = h.evaluate('clockHTML()');
  assert.ok(painted.includes('>0:13<'), 'the first paint is the real remaining time: ' + painted);
  assert.ok(!painted.includes('>0:30<'), 'never the hardcoded 0:30');
  assert.ok(painted.includes('width:20.666'), 'the progress bar paints the live value too: ' + painted);
  // A running clock paints from the same source, and the interval writes with the
  // same formatter, so a paint and a tick can never disagree.
  h.evaluate("timer={duration:60,remaining:12.4,deadline:Date.now()+7400}");
  assert.ok(/>(0:0[7-8])</.test(h.evaluate('clockHTML()')), 'a deadline render is the live value too');
  h.evaluate("timer={duration:60,remaining:12.4,deadline:null}; seen=[]; document.querySelectorAll = sel => sel === '[data-clock]' ? [{textContent:'', classList:{toggle(){}}}].map(e => { seen.push(e); return e; }) : []");
  h.evaluate('tick()');
  assert.equal(h.evaluate('seen[0].textContent'), '0:13', 'the interval writes exactly what the paint shows');
  assert.equal(h.evaluate('clockText(clockLeft())'), '0:13', 'and both go through clockText()');
  // Every view: the Vision surface carries its own [data-clock] (mobile hides the
  // strip that carries the desktop one), and it is painted by the same helpers.
  const surface = h.evaluate('visionSurface()');
  assert.ok(surface.includes('data-clock'), 'the Vision stagebar carries the same clock element');
  assert.ok(surface.includes('>0:13<'), 'and its first paint is the same instant');
  // A cross-tab tick repaints; only a duration change re-renders the view.
  assert.ok(source.includes('durationChanged?render():tick()'), 'a cross-tab update paints the clock in place');
});

test('a Twitch VOD picker sends the replay source the server accepts, never a live label', () => {
  const h = harness();
  h.evaluate("pickReplay({vod_id:'https://www.twitch.tv/videos/1000000011',start_s:30,rate:2})");
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(liveSource())')),
    {kind: 'vod-replay', vod_id: 'https://www.twitch.tv/videos/1000000011', start_s: 30, rate: 2});
  assert.equal(h.evaluate("liveSourceLabel('vod-replay')").includes('live'), false, 'a replay is never labelled live');
  assert.ok(h.evaluate("liveSourceLabel('vod-replay')").includes('1000000011'), 'the label names the VOD');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(replayChoice())')),
    {vod_id: 'https://www.twitch.tv/videos/1000000011', start_s: 30, rate: 2}, 'the panel can show what was chosen');
  // An empty box is refused in the shell, before any request is made.
  h.evaluate("errors=[]; message=(text,error)=>errors.push({text,error})");
  h.evaluate("vodChoice=null; pickReplay({vod_id:'  '})");
  assert.equal(h.evaluate('errors.length'), 1);
  assert.equal(h.evaluate('replayChoice()'), null);
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
  h.evaluate("lang='zh'");
  await h.handlers.submit(form);
  assert.equal(photo.validity, '请选择图片文件（JPEG 或 PNG）。');
  photo.files = [{size: 8 * 1024 * 1024 + 1, type: 'image/png'}];
  await h.handlers.submit(form);
  assert.equal(photo.validity, '请选择不超过 8 MB 的照片。');
  assert.equal(read, 0, 'nothing is read or uploaded');
  photo.files = [{size: 1000, type: 'image/jpeg'}];
  await h.handlers.submit(form);
  assert.equal(read, 1, 'a normal photo is read and sent');
  assert.equal(h.evaluate("validationMessage('image_base64 is not a decodable image')"), '无法读取这张图片，请换一张 JPEG 或 PNG 照片。');
});
test('a VOD replay the server would refuse is explained before Start, in both languages', () => {
  const h = harness();
  h.evaluate("errors=[]; message=(text,error)=>errors.push({text,error})");
  for (const bad of ["{vod_id:'https://www.twitch.tv/examplechannel'}", "{vod_id:'abc'}", "{vod_id:'0'}", "{vod_id:'1000000011',rate:9}"]) {
    h.evaluate(`vodChoice=null; pickReplay(${bad})`);
    assert.equal(h.evaluate('replayChoice()'), null, `${bad} is not kept as the replay`);
  }
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(errors.map(e=>[e.text,e.error]))')), [
    ['Use a Twitch VOD id or https://www.twitch.tv/videos/<id>', true],
    ['Use a Twitch VOD id or https://www.twitch.tv/videos/<id>', true],
    ['Use a Twitch VOD id or https://www.twitch.tv/videos/<id>', true],
    ['Rate must be more than 0 and at most 8', true]]);
  h.evaluate("lang='zh'; errors=[]; pickReplay({vod_id:'abc'}); pickReplay({vod_id:'1000000011',rate:9})");
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(errors.map(e=>e.text))')), ['请输入 Twitch 回放 id 或 https://www.twitch.tv/videos/<id> 网址', '倍速须大于 0 且不超过 8']);
  for (const good of ["{vod_id:'v1000000011',rate:8}", "{vod_id:'https://www.twitch.tv/videos/1000000011/'}", "{vod_id:'1000000011',rate:0.25}"]) {
    h.evaluate(`vodChoice=null; pickReplay(${good})`);
    assert.notEqual(h.evaluate('replayChoice()'), null, `${good} is accepted`);
  }
});
