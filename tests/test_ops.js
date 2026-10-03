'use strict';
// Run: node --test tests/test_ops.js. No DOM or network dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../annotator/ops.js'), 'utf8');
const clockSync = require('../annotator/clock-sync.js');
const clockSyncSource = fs.readFileSync(path.join(__dirname, '../annotator/clock-sync.js'), 'utf8');
function harness(opts = {}) {
  const handlers = {}, storage = {...opts.storage}, windowHandlers = {}, visits = [];
  const document = {addEventListener(event, fn) { handlers[event] = fn; }, querySelector() { return {}; }, querySelectorAll() { return []; }, documentElement: {dataset: {}, lang: ''}};
  // The URL is a hash route: pushState/replaceState update location.hash, and a test drives back/forward by
  // setting location.hash and calling the captured hashchange listener, as the browser does.
  const location = {hash: opts.hash || ''};
  const history = {pushState(state, title, url) { location.hash = url; visits.push(['push', url]); }, replaceState(state, title, url) { location.hash = url; visits.push(['replace', url]); }};
  const context = {document, location, history, localStorage: {getItem: key => storage[key] || null, setItem: (key, value) => storage[key] = value}, window: {addEventListener(event, fn) { windowHandlers[event] = fn; handlers['window:' + event] = fn; }}, setInterval() {}, setTimeout() {}, clearTimeout() {}, URL, console, confirm: () => true, FormData: function(form) { return Object.entries(form.values); }};
  vm.createContext(context);
  vm.runInContext(source.replace("(() => {", '').replace('});reload();', '});').replace(/\}\)\(\);\s*$/, ''), context);
  vm.runInContext("data={revision:1,settings:{},tournament:{raceTo:7,entrants:[],matches:[]},players:[],history:[]}; calls=[]; realAction=action; action=async(name,payload)=>{calls.push({name,payload});return true}", context);
  return {context, handlers, windowHandlers, visits, storage, evaluate: expression => vm.runInContext(expression, context)};
}
const tabClick = (h, name) => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {tab: name}}}});
const browserBack = (h, hash) => { h.context.location.hash = hash; h.windowHandlers.hashchange(); };
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
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(navTabs)')), ['tonight','records','vision','players','status']);
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
  const html = h.evaluate('bracketScreen()');
  assert.ok(html.includes('data-action="absence"'));
  assert.ok(!html.includes('data-action="schedule"'));
});
test('Floor focus picker includes live and delayed tables', () => {
  const h = harness();
  h.evaluate("data.tournament.matches=['live','delayed'].map((status,i)=>({id:'m'+i,table:i+1,round:1,status,sides:['e1','e2'],absent:status==='delayed'?['e1']:[],score:[0,0]}));data.notes=[]");
  const html = h.evaluate('floorScreen()');
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
  h.evaluate(`lang='${lang}';action=realAction;errors=[];message=(text,error,detail)=>errors.push({text,error,detail});
    renders=[];render=()=>renders.push({score:JSON.stringify(data.tournament.matches[0].score),status:data.tournament.matches[0].status,pending:isPending('m1'),revision:data.revision});
    data={revision:3,settings:{},players:[],history:[],events:[],notes:[],
      tournament:{id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
        entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bo'}]}],
        matches:[{id:'m1',round:1,sides:['e1','e2'],score:[0,0],status:'live',table:1,absent:[]}]}};
    confirm=()=>true;reloads=0;`);
  // queue of scripted answers: {status, body} | 'network' ; resolved manually via release()
  h.evaluate(`pendingAnswers=[];posted=[];
    fetch=(url,opts)=>{if(!opts||opts.method!=='POST'){reloads++;return Promise.resolve({ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(serverState))})}
      const body=JSON.parse(opts.body);posted.push(body);return new Promise((resolve,reject)=>pendingAnswers.push({body,resolve,reject}))};
    serverState=JSON.parse(JSON.stringify(data));
    answer=(kind,extra)=>{const p=pendingAnswers.shift();if(kind==='network')return p.reject(new TypeError('Failed to fetch'));
      if(kind==='ok'){const s=JSON.parse(JSON.stringify(serverState));s.revision++;const m=s.tournament.matches[0];if(p.body.action==='match_score')m.score=p.body.score;if(p.body.action==='match_complete'){m.status='complete';m.winnerId=m.score[0]>m.score[1]?'e1':'e2'}serverState=s;return p.resolve({ok:true,status:200,json:async()=>s})}
      return p.resolve({ok:false,status:kind,json:async()=>extra||{}})};`);
  h.context.window.document = h.context.document;
  return h;
}
const flush = () => new Promise(r => setImmediate(r));
const click = (h, dataset) => h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset, classList:{contains:()=>false}}}});

test('round 1 · Vision loading: the first paint is labelled and says what is loading, in EN and 中', () => {
  for (const [lang, loading, play, freeze, cues] of [['en', 'Loading the review workspace…', 'Play', 'Freeze', 'Cues'], ['zh', '正在加载复核工作区…', '播放', '冻结', '线索']]) {
    const h = harness();
    h.evaluate(`lang='${lang}';visionAdapter=null`);
    const html = h.evaluate('visionSurface()');
    assert.ok(html.includes('aria-busy="true" data-loading="true"'), `${lang}: the surface is marked busy until the adapter attaches`);
    assert.equal((html.match(new RegExp(`<p class="vs-loading" role="status">${loading}</p>`, 'g')) || []).length, 2, `${lang}: both rails say what is loading`);
    // no control is unlabelled on the first paint
    for (const button of html.match(/<button[^>]*>[^<]*<\/button>/g) || []) {
      const named = /aria-label="[^"]+"/.test(button) || />[^<\s][^<]*<\/button>$/.test(button);
      assert.ok(named, `${lang}: unlabelled control ${button.slice(0, 80)}`);
    }
    assert.ok(html.includes(`>▶ ${play}</button>`) && html.includes(`>${freeze}</button>`) && html.includes(`>${cues}</button>`), `${lang}: Play, Freeze and the sheet tab read from the start`);
    h.evaluate('visionAdapter={render(){}}');
    assert.ok(!h.evaluate('visionSurface()').includes('data-loading'), `${lang}: once attached, no loading state`);
  }
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(/\.vision-surface\[data-loading\] \.vs-rail,#ops-shell \.vision-surface\[data-loading\] \.vs-inspector\{min-height:/.test(css), 'the rails hold their loaded size while loading');
  assert.ok(css.includes('.vision-surface[data-loading] .vs-stagebar{min-height:50px}'), 'the stagebar row is reserved');
});
test('round 1 · Back room: operator panels first; system status and roadmap under a collapsed, labelled maintainers section', () => {
  for (const [lang, maint, status] of [['en', 'For maintainers', 'System status'], ['zh', '维护人员', '系统状态']]) {
    const h = harness();
    h.evaluate(`lang='${lang}';data.notes=[]`);
    const html = h.evaluate('statusScreen()');
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
  for (const [lang, noMatch, wait, dflt] of [['en', 'No match is on a table', 'Register entrants, rack the night, then send a match from the Queue', 'default name · saved when you rack'],
                                             ['zh', '暂无比赛上台', '请先登记参赛者并生成对阵，再从“队列”安排比赛上台', '默认名称 · 生成对阵时保存']]) {
    const h = harness();
    h.evaluate(`lang='${lang}';data.players=[];data.history=[];data.events=[];data.tournament={id:'t1',name:'',format:'singles',raceTo:1,status:'registration',entrants:[],matches:[]}`);
    const floor = h.evaluate('floorScreen()');
    const names = [...floor.matchAll(/<strong class="name"[^>]*>([^<]*)<\/strong>/g)].map(m => m[1]);
    assert.deepEqual(names, ['—', '—'], `${lang}: an empty board shows no name, not "Tables open"`);
    assert.ok(floor.includes('class="empty-note board-empty"') && floor.includes(noMatch) && floor.includes(wait), `${lang}: it says there is no match and what to do`);
    const scene = h.evaluate('scene()');
    assert.ok(!/data-phase=/.test(h.evaluate('tonightScreen()')), `${lang}: no phase button survives anywhere in Tonight`);
    assert.ok(!/<button/.test(scene) && scene.includes(h.evaluate("esc(t('sceneIdle'))")), `${lang}: the step is read-only, and an empty venue says so`);
    assert.ok(/<h2 class="sr-only">/.test(floor), `${lang}: the scoreboard has a heading`);
    assert.ok(!/Tables open|球台空闲/.test(floor), `${lang}: never a placeholder name on the board`);
    const matches = h.evaluate('bracketScreen()');
    assert.ok(matches.includes(dflt), `${lang}: an unsaved event name is shown, and said to be the default`);
    assert.ok(!/<li>[^<]*(Nothing|暂无|尚无)[^<]*<\/li>/.test(matches), `${lang}: no empty state inside a list`);
    assert.ok(!/Nothing here yet|暂无记录/.test(matches + floor + h.evaluate('setupScreen()') + h.evaluate('playersScreen()')), `${lang}: the generic empty line is gone`);
    assert.ok(matches.includes('<article class="empty"><h3>'), `${lang}: the empty bracket panel has a heading`);
    // with a racked night and nothing on a table, the step is Matches
    h.evaluate(`data.tournament.name='Friday';data.tournament.entrants=[{id:'e1',members:[{name:'A'}]},{id:'e2',members:[{name:'B'}]}];data.tournament.matches=[{id:'m1',round:1,sides:['e1','e2'],score:[0,0],status:'scheduled',absent:[]}];data.tournament.status='active'`);
    const play2 = h.evaluate('playScreen()');
    assert.ok(play2.includes('data-action="schedule"'), `${lang}: a racked match can be sent from the Queue`);
    assert.ok(!h.evaluate('bracketScreen()').includes(dflt), `${lang}: a saved name is not called a default`);
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
  const shown = JSON.parse(h.evaluate('JSON.stringify(renders.at(-1))'));
  assert.deepEqual([shown.score, shown.pending, shown.status], ['[1,0]', true, 'live'], 'the new score is on screen before the server answered, marked pending');
  assert.equal(h.evaluate('posted[0].revision'), 3);
  h.evaluate("answer('ok')"); await done; await flush();
  const final = JSON.parse(h.evaluate('JSON.stringify(renders.at(-1))'));
  assert.deepEqual([final.score, final.pending, final.revision], ['[1,0]', false, 4], 'confirmed: same score, not pending, the server\u2019s revision');
});
test('instant: a signature is never shown before the server signs it', async () => {
  const h = instantHarness();
  h.evaluate("data.tournament.matches[0].score=[3,1];serverState=JSON.parse(JSON.stringify(data))");
  const done = click(h, {action:'sign', id:'m1'});
  await flush();
  assert.equal(h.evaluate('renders.at(-1).status'), 'live', 'while the signature is unconfirmed the match is still live');
  assert.equal(h.evaluate('renders.at(-1).pending'), true, 'and says it is saving');
  h.evaluate("answer('ok')"); await done; await flush();
  assert.equal(h.evaluate('renders.at(-1).status'), 'complete', 'signed only once the server said so');
});
test('instant: 409 rolls back to the exact previous render, reloads, and says why', async () => {
  const h = instantHarness();
  const before = h.evaluate('JSON.stringify(data)');
  const done = click(h, {action:'score', id:'m1', side:'1', delta:'1'});
  await flush();
  assert.equal(h.evaluate('renders.at(-1).score'), '[0,1]');
  h.evaluate("answer(409,{error:'State changed; reload before retrying'})"); await done; await flush();
  assert.equal(h.evaluate('reloads'), 1, 'the document is reloaded from the server');
  assert.equal(h.evaluate('JSON.stringify(data)'), before, 'the state is exactly the pre-tap state (the server had not moved)');
  assert.deepEqual([h.evaluate('renders.at(-1).score'), h.evaluate('renders.at(-1).pending')], ['[0,0]', false]);
  assert.match(h.evaluate('errors.at(-1).text'), /Another operator changed the data/);
});
test('instant: 400 rolls back and shows the server\u2019s reason in both languages', async () => {
  for (const [lang, reason] of [['en', 'Schedule match before scoring'], ['zh', '请先安排比赛上台，再记录比分']]) {
    const h = instantHarness(lang);
    const before = h.evaluate('JSON.stringify(data)');
    const done = click(h, {action:'score', id:'m1', side:'0', delta:'1'});
    await flush();
    h.evaluate("answer(400,{error:'Schedule match before scoring'})"); await done; await flush();
    assert.equal(h.evaluate('JSON.stringify(data)'), before, `${lang}: exact rollback`);
    assert.equal(h.evaluate('renders.at(-1).score'), '[0,0]', `${lang}: the screen shows the pre-tap score`);
    assert.ok(h.evaluate('errors.at(-1).text').includes(reason), `${lang}: ${h.evaluate('errors.at(-1).text')}`);
    assert.equal(h.evaluate('reloads'), 0, `${lang}: a validation refusal does not reload`);
  }
});
test('instant: a network failure rolls back and says so, with no retry', async () => {
  for (const [lang, said] of [['en', 'network did not answer'], ['zh', '网络无响应']]) {
    const h = instantHarness(lang);
    const before = h.evaluate('JSON.stringify(data)');
    const done = click(h, {action:'score', id:'m1', side:'0', delta:'1'});
    await flush();
    h.evaluate("answer('network')"); await done; await flush();
    assert.equal(h.evaluate('JSON.stringify(data)'), before, `${lang}: exact rollback`);
    assert.ok(h.evaluate('errors.at(-1).text').includes(said), `${lang}: ${h.evaluate('errors.at(-1).text')}`);
    assert.equal(h.evaluate('posted.length'), 1, `${lang}: posted once, never retried`);
  }
});
test('instant: two rapid taps are serialised; the final state is the server\u2019s', async () => {
  const h = instantHarness();
  const first = click(h, {action:'score', id:'m1', side:'0', delta:'1'});
  const second = click(h, {action:'score', id:'m1', side:'0', delta:'1'});
  await flush();
  assert.equal(h.evaluate('posted.length'), 1, 'the second write waits for the first');
  h.evaluate("answer('ok')"); await first; await flush(); await flush();
  assert.equal(h.evaluate('posted.length'), 2, 'then it goes');
  assert.equal(h.evaluate('posted[1].revision'), 4, 'carrying the revision the first answer returned (no race)');
  assert.equal(h.evaluate('JSON.stringify(posted[1].score)'), '[2,0]', 'and built on the confirmed score');
  h.evaluate("answer('ok')"); await second; await flush();
  assert.equal(h.evaluate('JSON.stringify(data.tournament.matches[0].score)'), h.evaluate('JSON.stringify(serverState.tournament.matches[0].score)'), 'final state = server state');
  assert.equal(h.evaluate('renders.at(-1).pending'), false);
  // a refused second write rolls back only itself
  const h2 = instantHarness();
  const a = click(h2, {action:'score', id:'m1', side:'0', delta:'1'}), b = click(h2, {action:'score', id:'m1', side:'0', delta:'1'});
  await flush(); h2.evaluate("answer('ok')"); await a; await flush(); await flush();
  h2.evaluate("answer(400,{error:'Score out of range'})"); await b; await flush();
  assert.equal(h2.evaluate('JSON.stringify(data.tournament.matches[0].score)'), '[1,0]', 'the confirmed first step stays; only the refused one is undone');
});
test('instant: the pending state is readable by a screen reader, in EN and 中', () => {
  for (const [lang, saving] of [['en', 'saving…'], ['zh', '保存中…']]) {
    const h = harness();
    h.evaluate(`lang='${lang}';data.tournament={id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
      entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bo'}]}],
      matches:[{id:'m1',round:1,sides:['e1','e2'],score:[1,0],status:'live',table:1,absent:[]}]};focusId='m1';pendingMatches.set('m1',1)`);
    const floor = h.evaluate('floorScreen()');
    assert.ok(floor.includes('class="scoreboard pending" aria-busy="true"'), `${lang}: the scoreboard is busy`);
    assert.ok(floor.includes(`<p class="pending-note" role="status">${saving}</p>`), `${lang}: and says ${saving}`);
    const bracket = h.evaluate("density='compact';bracketScreen()");
    assert.ok(bracket.includes('bracket-card pending') && bracket.includes('aria-busy="true"'), `${lang}: the bracket card is busy`);
    assert.ok(bracket.includes(` · ${saving}"`) && bracket.includes(`role="status">${saving}</span>`), `${lang}: its name and live region say ${saving}`);
    assert.ok(!/class="badge complete"/.test(floor), `${lang}: pending never looks signed`);
    h.evaluate("pendingMatches.clear()");
    assert.ok(!h.evaluate('floorScreen()').includes('aria-busy'), `${lang}: gone once confirmed`);
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
  h.evaluate("data.players=[{id:'p1',name:'Maximiliana Alexandrovna Konstantinopolskaya-Wrightington',rating:50,status:'Active',joinedAt:'2026-09-26'}];data.history=[]");
  const record = h.evaluate("recordView(data.players[0])");
  assert.ok(record.includes('<div class="record">') && /<div class="tiles">(<div class="tile">[\s\S]*?){4}/.test(record), 'the record has its four totals tiles');
  for (const table of ['per-event', 'h2h']) {
    if (record.includes(`class="${table}"`)) assert.ok(record.includes(`<div class="table-wrap"><table class="${table}"`), `${table} is wrapped`);
  }
});
test('clarify: the night log names entrants and sources instead of printing hex ids', () => {
  const h = harness();
  const present = 'a1111111c94649988a2995e9b27c69ff', removed = 'b0000000c94649988a2995e9b27c69ff', source = '77777777777777777777777777777777';
  h.evaluate(`data.players=[{id:'p1',name:'王磊',rating:60,status:'Active'}];
    data.tournament={id:'t1',name:'Friday',format:'singles',raceTo:3,status:'registration',
      entrants:[{id:'${present}',members:[{pid:'p1',name:'王磊'}]}],matches:[]};
    data.history=[];data.sources=[];
    data.events=[
      {action:'entrant_add',createdAt:'2026-09-26T01:00:00Z',revision:4,context:{id:'${present}'}},
      {action:'entrant_remove',createdAt:'2026-09-26T01:01:00Z',revision:5,context:{id:'${removed}'}},
      {action:'source_add',createdAt:'2026-09-26T01:02:00Z',revision:2,context:{id:'${source}'}}]`);
  for (const [lang, gone, aSource, added, removedLabel] of [
    ['en', 'an entrant who was removed', 'a source', 'Entrant registered', 'Entrant removed'],
    ['zh', '已移除的参赛者', '一个来源', '参赛报名', '移除参赛者']]) {
    h.evaluate(`lang='${lang}'`);
    const line = i => h.evaluate(`auditLine(data.events[${i}])`);
    assert.ok(line(0).includes(`${added} · 王磊 · v4`), `${lang}: a present entrant reads by name: ${line(0)}`);
    assert.ok(line(1).includes(`${removedLabel} · ${gone} · v5`), `${lang}: a removed entrant reads as a plain phrase: ${line(1)}`);
    assert.ok(line(2).includes(aSource), `${lang}: a removed source reads as a plain phrase: ${line(2)}`);
    for (const i of [0, 1, 2]) assert.ok(!/[0-9a-f]{8}/.test(line(i)), `${lang}: no hex id in the visible line: ${line(i)}`);
    // never dropped: the id stays inspectable in the list item's title
    const html = h.evaluate('recordsScreen()');
    for (const id of [present, removed, source]) assert.ok(html.includes(`title="${id}"`), `${lang}: ${id.slice(0, 8)} is kept in the title`);
  }
  // a name the server recorded wins; a source still present reads by its URL; an archived entrant resolves from history
  h.evaluate(`lang='en';data.sources=[{id:'${source}',url:'https://www.twitch.tv/examplechannel'}]`);
  assert.ok(h.evaluate('auditLine(data.events[2])').includes('https://www.twitch.tv/examplechannel'));
  h.evaluate(`data.history=[{id:'h1',name:'Thursday',entrants:[{id:'${removed}',members:[{pid:null,name:'Bo'}]}],matches:[]}]`);
  assert.ok(h.evaluate('auditLine(data.events[1])').includes('Entrant removed · Bo · v5'), 'an archived night still knows the name');
  assert.ok(h.evaluate(`auditLine({action:'player_save',createdAt:'2026-09-26T01:00:00Z',revision:6,context:{id:'x',name:'Ann'}})`).includes('Player saved · Ann · v6'));
});
test('R9: the compact bracket is one line per side with a status dot; the full card is still there', () => {
  const h = harness();
  h.evaluate(`data.players=[];data.tournament={id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
    entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bo'}]},{id:'e3',members:[{pid:null,name:'Cai'}]},{id:'e4',members:[{pid:null,name:'Dee'}]}],
    matches:[{id:'m1',round:1,sides:['e1','e2'],score:[1,0],status:'live',table:1,absent:[]},
             {id:'m2',round:1,sides:['e3','e4'],score:[0,0],status:'scheduled',table:null,absent:[]},
             {id:'m3',round:2,sides:[null,null],score:[0,0],status:'pending',table:null,absent:[]}]}`);
  const compact = h.evaluate("density='compact';bracketScreen()");
  assert.ok(compact.includes('<div class="rounds" data-density="compact">'), 'compact is the default density');
  const card = compact.slice(compact.indexOf('data-status="live"'), compact.indexOf('data-status="scheduled"'));
  assert.ok(card.includes('class="row card-side first"') && card.includes('class="status-dot"'), 'a side line carries the status dot');
  assert.ok(card.includes('aria-label="Ann – Bo · On table"'), 'the whole match, with its status word, is the card\u2019s name');
  // nothing is removed: the header, the badge and every control are in the card, shown on hover/focus
  assert.ok(card.includes('class="row card-head"') && card.includes('Table 1 · m1') && card.includes('>On table<'), 'header row and badge stay');
  for (const action of ['absence', 'forfeit']) assert.ok(card.includes(`data-action="${action}"`), `${action} stays reachable`);
  assert.ok(compact.includes('data-action="schedule" data-id="m2"'), 'Send to table stays reachable');
  assert.ok(compact.includes('tabindex="0"'), 'a keyboard user can open a card');
  // the toggle, and the full density renders the same cards
  assert.ok(compact.includes('data-action="density" data-value="full" aria-pressed="false"'), 'a pressed-state toggle offers full cards');
  const full = h.evaluate("density='full';bracketScreen()");
  assert.ok(full.includes('data-density="full"') && full.includes('Table 1 · m1'), 'full cards render as before');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('.rounds[data-density=full] .round .entry{min-height:98px}'), 'the 98 px card height applies to full cards only');
  assert.ok(css.includes('.entry:is(:hover,:focus-within,.selected,.open) :is(.card-head,.card-actions){display:flex}'), 'hover, focus or the card\u2019s own control opens the full card');
  assert.ok(/grid-auto-columns:minmax\(180px,1fr\)/.test(css), 'rounds share the viewport width');
  for (const key of ['density', 'densityCompact', 'densityFull']) assert.match(source, new RegExp(`\\b${key}:\\['[^']+','[^']+'\\]`), `${key} has EN and 中`);
});
test('R9 on touch: every compact card carries its own expand control, and pressing it does not re-render', async () => {
  const h = harness();
  h.evaluate(`data.players=[];data.tournament={id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
    entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bo'}]}],
    matches:[{id:'m1',round:1,sides:['e1','e2'],score:[1,0],status:'live',table:1,absent:[]}]}`);
  const compact = h.evaluate("density='compact';bracketScreen()");
  assert.ok(compact.includes('class="card-toggle" data-action="card-toggle" aria-expanded="false"'), 'the card carries a control of its own, so a thumb has something to press');
  assert.ok(compact.includes('aria-label="Show the full card"'), 'the control says what it does');
  // pressing it flips .open in place: no render(), no action(), so focus and scroll stay put
  let open = false, toggled = null;
  const attrs = {};
  const card = {classList: {toggle(cls) { toggled = cls; open = !open; return open; }}};
  const button = {dataset: {action: 'card-toggle'}, setAttribute(k, v) { attrs[k] = v; }, closest: sel => sel === '.entry' ? card : null};
  const press = () => h.handlers.click({target: {closest: sel => sel === 'button,.modal-backdrop' ? button : null}});
  await press();
  assert.equal(toggled, 'open', 'the class that reveals the card is toggled on the card itself');
  assert.equal(attrs['aria-expanded'], 'true', 'the control reports the open state');
  assert.equal(attrs['aria-label'], 'Hide the details', 'and renames itself to the way back');
  await press();
  assert.equal(attrs['aria-expanded'], 'false', 'pressing again puts the card back');
  assert.equal(attrs['aria-label'], 'Show the full card');
  assert.equal(h.evaluate('calls.length'), 0, 'opening a card is not a server action');
  // the same rules serve a pointer, a keyboard and a thumb; the control only exists where hover is missing
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('.rounds[data-density=compact] .card-toggle{display:flex'), 'shown on a compact card');
  assert.ok(/\.card-toggle\{display:none/.test(css), 'never on a full card, which already shows everything');
  assert.ok(css.includes('.rounds[data-density=compact] .card-side.first{padding-right:var(--sp-5)}'), 'the name never runs under the control');
  for (const key of ['cardExpand', 'cardCollapse']) assert.match(source, new RegExp(`\\b${key}:\\['[^']+','[^']+'\\]`), `${key} has EN and 中`);
  assert.equal(h.evaluate("lang='zh';bracketScreen()").includes('aria-label="展开完整卡片"'), true, 'the control is translated');
});
test('R13: every query word must match the name, after NFKC, accent and case folding', () => {
  const h = harness();
  const m = (name, q) => h.evaluate(`nameMatches(${JSON.stringify(name)}, ${JSON.stringify(q)})`);
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
  h.evaluate("data.players=[{id:'p1',name:'Bo Active',rating:50,status:'Visitor'},{id:'p2',name:'Cai',rating:40,status:'Active'}];query='active';filter=''");
  const html = h.evaluate('playersScreen()');
  assert.ok(html.includes('Bo Active') && !html.includes('>Cai<'), 'a status word no longer matches a name');
  // R14: the matcher is local; neither it nor the desk filter makes a request
  assert.ok(!/fetch\(/.test(h.evaluate('nameMatches.toString()+deskFilter.toString()')), 'no network call on a keystroke');
  // EN/中 placeholder parity for both fields
  for (const key of ['search', 'deskSearch', 'deskNone']) assert.match(source, new RegExp(`\\b${key}:\\['[^']+','[^']+'\\]`), `${key} has EN and 中`);
});
test('R13: the registration desk filters its regulars in place with the same matcher', () => {
  const h = harness();
  h.evaluate("data.players=[{id:'p1',name:'Ann-Marie (Annie) Lee',rating:70,status:'Active'},{id:'p2',name:'王磊',rating:60,status:'Active'},{id:'p3',name:'Bo',rating:50,status:'Active'}];data.tournament={id:'t1',status:'registration',format:'singles',raceTo:3,entrants:[],matches:[]}");
  const html = h.evaluate('setupScreen()');
  assert.ok(html.includes('class="desk-search" data-desk="0"'), 'the desk has a type-to-filter field');
  assert.ok(html.includes('aria-controls="desk-pid0"') && html.includes('id="desk-pid0"'), 'tied to its select');
  assert.ok(html.includes('data-name="Ann-Marie (Annie) Lee"'), 'options carry the bare name, so the rating is never matched');
  // drive deskFilter against a stub select
  h.evaluate(`const opts=[{value:'',textContent:'Guest',dataset:{},hidden:false},
    {value:'p1',textContent:'Ann-Marie (Annie) Lee · 70',dataset:{name:'Ann-Marie (Annie) Lee'},hidden:false},
    {value:'p2',textContent:'王磊 · 60',dataset:{name:'王磊'},hidden:false},
    {value:'p3',textContent:'Bo · 50',dataset:{name:'Bo'},hidden:false}];
    const sel={options:opts,value:'',get selectedOptions(){return opts.filter(o=>o.value===this.value)}};
    const none={hidden:true};
    document.getElementById=id=>id==='desk-pid0'?sel:id==='desk-none0'?none:null;
    deskSelect=sel;deskNone=none;`);
  h.evaluate("deskFilter({value:'ann-marie lee',dataset:{desk:'0'}})");
  assert.equal(h.evaluate("opts.filter(o=>!o.hidden).map(o=>o.value).join(',')"), ',p1', 'only the match (and Guest) stay visible');
  assert.equal(h.evaluate('deskSelect.value'), 'p1', 'a single match is selected');
  h.evaluate("deskFilter({value:'７０',dataset:{desk:'0'}})");
  assert.equal(h.evaluate('deskNone.hidden'), false, 'the rating is not part of the name: nothing matches, and it says so');
  h.evaluate("deskFilter({value:'',dataset:{desk:'0'}})");
  assert.equal(h.evaluate("opts.every(o=>!o.hidden)"), true, 'clearing the field shows everyone again');
});
test('onboard: an empty club gets three real steps in Register, and they leave once the draw exists', () => {
  const h = harness();
  const guide = () => { const html = h.evaluate('registerScreen()'); const m = html.match(/<article class="first-run"[\s\S]*?<\/article>/); return m ? m[0] : ''; };
  const first = guide();
  assert.ok(first, 'an empty club sees the guide');
  assert.deepEqual([...first.matchAll(/data-tab="([a-z]+)"/g)].map(m => m[1]), ['players'], 'step 1 is the Regulars tab');
  assert.deepEqual([...first.matchAll(/data-action="([a-z-]+)"/g)].map(m => m[1]), ['open-desk', 'tournament-start'], 'steps 2 and 3 do the work in place: open the desk, then start the event');
  assert.ok(!first.includes('class="done"'), 'nothing is ticked before anything happened');
  h.evaluate("data.players=[{id:'p1',name:'Ana',rating:50,status:'Active'}]");
  assert.equal((guide().match(/class="done"/g) || []).length, 1, 'a saved regular ticks step 1');
  h.evaluate("data.tournament.entrants=[{id:'e1',members:[{pid:'p1',name:'Ana'}]},{id:'e2',members:[{pid:null,name:'Bo'}]}]");
  assert.equal((guide().match(/class="done"/g) || []).length, 2, 'two entrants tick step 2');
  h.evaluate("data.tournament.matches=[{id:'m1',round:1,sides:['e1','e2'],score:[0,0],status:'scheduled',table:null,absent:[]}]");
  assert.equal(guide(), '', 'the guide leaves once the draw exists');
  for (const key of ['firstRunTitle', 'firstRunRegulars', 'firstRunEntrants', 'firstRunRack', 'firstRunNote']) {
    assert.match(source, new RegExp(`${key}:\\['[^']+','[^']+'\\]`), `${key} has an EN and a 中 string`);
  }
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
  // A real form whose `id` control shadows its own id property: the handler reads the form off the
  // event target, and a DOM form exposes its controls through .elements, so the fake must too.
  const form = {preventDefault() {}, id: formId, elements: {id: {value: values.id}}, values, getAttribute: () => formId, classList: {contains: () => false}, querySelectorAll: () => [], querySelector: () => null};
  return {...form, target: form, submitter};
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
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls[0])')), {name: 'settings_update', payload: {clothColor: '#1f4a70', lampGlow: 0.4, showDiamonds: false, publicBoard: false}});
});
test('the appearance panel carries the public board switch, on by default, in EN and 中', () => {
  const h = harness();
  const html = h.evaluate('appearancePanel()');
  // A hidden input posts "off" when the box is not ticked, so an unticked box is a real false,
  // never an absent key; a missing setting reads as on, exactly as the board page reads it.
  assert.ok(html.includes('<input type="hidden" name="publicBoard" value="off">'), 'the hidden off input');
  assert.ok(html.includes('<input type="checkbox" name="publicBoard" value="on" checked>'), 'on by default');
  assert.ok(html.includes('Public board: on/off'), 'the EN label, as docs/public-board.md 6 spells it');
  h.evaluate("lang='zh'");
  assert.ok(h.evaluate('appearancePanel()').includes('公网记分板：开/关'), 'the 中 label');
});
test('the public board switch shows a board that is already off and posts a real boolean', async () => {
  const already = harness();
  already.evaluate('data.settings={publicBoard:false}');
  assert.ok(already.evaluate('appearancePanel()').includes('<input type="checkbox" name="publicBoard" value="on" >'),
    'an off board leaves the box unticked');
  const h = harness();
  await h.handlers.submit(submission('appearance-form', {clothColor: '#1d5c44', lampGlow: '0.3', showDiamonds: 'on', publicBoard: 'on'}));
  await h.handlers.submit(submission('appearance-form', {clothColor: '#1d5c44', lampGlow: '0.3', showDiamonds: 'on', publicBoard: 'off'}));
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls.map(c => [c.payload.publicBoard, typeof c.payload.publicBoard]))')),
    [[true, 'boolean'], [false, 'boolean']]);
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
  // The bar scales (transform) rather than resizing (width) since the polish step: 12.4 / 60 = 0.2067.
  assert.ok(painted.includes('transform:scaleX(0.2067)'), 'the progress bar paints the live value too: ' + painted);
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
  // The clock is the server's now, and ops.js adopts it through that same
  // storage event: annotator/clock-sync.js dispatches it with a deadline in this
  // device's clock base, so the one 200 ms interval keeps painting every view
  // from the shared instant with no second painter.
  const serverNow = Date.now() - 5000;             // this device is 5 s fast
  const snapshot = {duration: 60, running: true, deadline_ms: serverNow + 30000, remaining_ms: 30000, seq: 9};
  h.evaluate("timer={duration:60,remaining:12.4,deadline:null}");
  // The naive push — the server's raw deadline — is 5 s out on this device.
  h.handlers['window:storage']({key: 'cp-ops-clock', newValue: JSON.stringify({duration: 60, remaining: 30, deadline: snapshot.deadline_ms})});
  assert.equal(h.evaluate('clockText(clockLeft())'), '0:25', 'a raw server deadline on a fast device is 5 s out');
  // What the sync layer actually sends: the same instant in the device's base.
  const adopted = clockSync.toLocalClock(snapshot, Date.now(), -5000);
  h.handlers['window:storage']({key: 'cp-ops-clock', newValue: JSON.stringify(adopted)});
  const shared = h.evaluate('clockText(clockLeft())');
  assert.ok(shared === '0:30' || shared === '0:29', 'the shared instant survives the skew: ' + shared);
  assert.equal(h.evaluate('timer.duration'), 60, 'and ops.js kept the server duration');
  assert.ok(h.evaluate('clockHTML()').includes('>' + shared + '<'), 'the strip paints it');
  assert.ok(h.evaluate('visionSurface()').includes('>' + shared + '<'), 'and the Vision view paints the same instant');
  assert.ok(!clockSyncSource.includes('setInterval(tick'), 'the sync layer adds no second painter');
  assert.equal((source.match(/setInterval\(tick,200\)/g) || []).length, 1, 'ops.js keeps its one 200 ms interval');
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
  assert.equal(clockSync.LABELS.en.kicker, 'Shot timer');
  assert.equal(clockSync.LABELS.zh.kicker, '击球计时');
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
    assert.ok(!/local timer|本机计时/.test(words.kicker), 'no label claims the clock is local any more');
    assert.ok(!/Shot clock|shared across devices|多设备同步/.test(words.kicker), 'and no label invents a second name for it');
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
  assert.deepEqual([...clockSync.LOCAL_TIMER_LIE], ['Shot timer', '击球计时'], 'the two words the shell paints are exactly what the shared clock adopts');
});

// The smallest DOM decorate() needs: one clock mount, an optional .kicker (the Vision stage
// bar's label and any page whose shell does not publish a language), an optional shell that
// publishes one, and the slot's own .sync-error span.
function fakeClockNode(attrs) {
  const node = {attrs: {...attrs}, textContent: '', className: '', hidden: false,
    classList: {toggle() {}, add() {}, remove() {}},
    setAttribute(name, value) { node.attrs[name] = value; },
    getAttribute(name) { return name in node.attrs ? node.attrs[name] : null; },
    removeAttribute(name) { delete node.attrs[name]; }};
  return node;
}
function fakeClockMount(options) {
  const opts = options || {};
  const children = [];
  let holder = null;
  const kicker = opts.kicker === null ? null : fakeClockNode({});
  if (kicker) kicker.textContent = opts.kicker || '';
  const error = opts.error === null ? null : fakeClockNode({});
  if (error && opts.error) error.textContent = opts.error;
  const strong = {closest: selector => (selector === '.vs-clock' && opts.vsClock ? holder : null), parentElement: null, nextSibling: null};
  holder = {
    querySelector: selector => {
      if (selector === '.kicker') return kicker;
      if (selector === '.sync-error') return error;
      if (selector === '[data-clock-sync]') return children.find(child => child.attrs && 'data-clock-sync' in child.attrs) || null;
      return null;
    },
    getAttribute: name => (name === 'title' ? (opts.title || null) : null),
    setAttribute: (name, value) => { if (name === 'title') opts.title = value; },
    insertBefore: (node, anchor) => { const at = anchor ? children.indexOf(anchor) : -1; children.splice(at < 0 ? children.length : at, 0, node); },
    appendChild: node => { children.push(node); node.parentNode = holder; },
    removeChild: node => { const at = children.indexOf(node); if (at >= 0) children.splice(at, 1); }
  };
  strong.parentElement = holder;
  if (kicker) {
    children.push(kicker);
    kicker.nextSibling = strong;
  } else {
    children.push(strong);
  }
  if (error) children.push(error);
  const shell = fakeClockNode({});
  if (opts.lang) shell.attrs['data-lang'] = opts.lang;
  const doc = {
    querySelector: selector => (selector === '#ops-shell' ? shell : null),
    createElement: () => fakeClockNode({}),
    querySelectorAll: () => [strong],
    documentElement: {getAttribute: name => (name === 'lang' ? (opts.rootLang || 'en') : null)}
  };
  return {doc, shell, kicker, error, holder, children,
    lines: () => children.filter(child => child.attrs && 'data-clock-sync' in child.attrs)};
}

test('one shot-timer name in both clocks, no sync line, and the slot speaks only when a command failed', () => {
  assert.deepEqual([...clockSync.LOCAL_TIMER_LIE], ['Shot timer', '击球计时']);
  // One name, checked across all three places that can paint it: the shell dictionary,
  // the shared clock's own labels, and the mount point in the top bar.
  const dictionary = JSON.parse(`[${/shotTimer:\[([^\]]*)\]/.exec(source)[1]}]`.replace(/'/g, '"'));
  assert.deepEqual(dictionary, ['Shot timer', '击球计时'], 'the shell paints one name');
  assert.deepEqual([...clockSync.LOCAL_TIMER_LIE], dictionary, 'the shared clock adopts exactly the label ops.js paints');
  assert.equal(clockSync.LABELS.en.kicker, dictionary[0]);
  assert.equal(clockSync.LABELS.zh.kicker, dictionary[1]);
  const html = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
  assert.ok(html.includes('aria-label="Shot timer / 击球计时"'), 'the top-bar mount point is named the same');
  const shell = {attrs: {}};
  const en = fakeClockMount({lang: 'en'});
  clockSync.decorate(en.doc, 'live', null);
  assert.equal(en.lines().length, 0, 'nothing is written beside a healthy clock');
  assert.equal(en.error.hidden, false, 'the stub starts visible, so hiding it is something decorate() does');
  assert.equal(en.error.attrs.hidden, '', 'a healthy clock leaves the error span hidden and empty');
  clockSync.decorate(en.doc, 'polling', null);
  assert.equal(en.lines().length, 0, 'reconnecting is not a line either');
  assert.equal(en.error.attrs.hidden, '', 'and it is still hidden');
  // The Vision stage bar's only label is the title attribute: it still adopts the one name.
  const vs = fakeClockMount({kicker: null, vsClock: true, title: clockSync.LOCAL_TIMER_LIE[1], lang: 'en'});
  clockSync.decorate(vs.doc, 'polling', null);
  assert.equal(vs.error.attrs.hidden, '', 'the stage bar is quiet too');
  assert.equal(vs.lines().length, 0, 'and carries no sync line');
  // The swap is still whitelist-gated: nothing else in the chrome is rewritten behind ops.js's back.
  const other = fakeClockMount({kicker: 'Tables open', lang: 'en'});
  clockSync.decorate(other.doc, 'live', null);
  assert.equal(other.kicker.textContent, 'Tables open', 'a label that is not the shot timer is left alone');
  // A failed command is the one thing that shows, in the language the shell published.
  const err = fakeClockMount({lang: 'en'});
  clockSync.decorate(err.doc, 'live', 'clock command failed — nothing changed');
  assert.equal(err.error.textContent, 'clock command failed — nothing changed');
  assert.equal(err.error.attrs.hidden, undefined, 'an error is not hidden');
  assert.equal(err.lines().length, 0, 'and it comes as itself, not as a sync line');
  const errZh = fakeClockMount({lang: 'zh'});
  clockSync.decorate(errZh.doc, 'busy', '服务器繁忙 — 正在重试');
  assert.equal(errZh.error.textContent, '服务器繁忙 — 正在重试', 'the error follows the published language');
  // The language is published by render() on the shell, with documentElement.lang as the
  // fallback before the old label sniff is ever needed (owner §13.2).
  const published = fakeClockMount({kicker: clockSync.LOCAL_TIMER_LIE[0], lang: 'zh'});
  clockSync.decorate(published.doc, 'live', '计时指令失败 — 未改变');
  assert.equal(published.error.textContent, '计时指令失败 — 未改变', 'the shell dataset outranks the label it paints');
  const byRoot = fakeClockMount({kicker: null, vsClock: true, title: clockSync.LOCAL_TIMER_LIE[1], rootLang: 'zh-CN'});
  clockSync.decorate(byRoot.doc, 'live', '计时指令失败 — 未改变');
  assert.equal(byRoot.error.textContent, '计时指令失败 — 未改变', 'documentElement.lang is the second source');
  const sniffed = fakeClockMount({kicker: clockSync.LOCAL_TIMER_LIE[0], rootLang: ''});
  clockSync.decorate(sniffed.doc, 'live', 'clock command failed — nothing changed');
  assert.equal(sniffed.error.textContent, 'clock command failed — nothing changed', 'the old sniff still answers when nothing is published');
  // Nowhere in the three shipped files does a label claim a local timer, or name it twice.
  for (const [name, text] of [['clock-sync.js', clockSyncSource], ['ops.js', source], ['ops.html', html]]) {
    assert.ok(!/local timer|本机计时/.test(text), `${name}: no label claims the timer is local`);
    assert.ok(!/Shot clock · local|多设备同步|shared across devices/.test(text), `${name}: no second name for the shot timer survives`);
    assert.ok(!/\.muted\[data-clock-sync\]/.test(text.split('querySelector')[0]), `${name}: nothing paints a sync line any more`);
    assert.ok(!/live · synced|实时 · 已同步/.test(text), `${name}: the redundant sync text is gone, both languages`);
  }
  assert.ok(!shell.attrs['data-lang'], 'and the fixture shell starts without a language, so publishing one is something render() does');
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

test('the regular profile deletes face data only after a confirm that says what goes, and shows the counts', async () => {
  const click = (h, dataset) => h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
  for (const [lang, button, receipt, kept] of [
    ['en', 'Delete face data', 'Face data deleted: 3 stored faces, 1 matched person unbound, 2 face samples', 'name and results stay'],
    ['zh', '删除人脸数据', '人脸数据已删除：3 张人脸，解除 1 个匹配人物，2 个人脸样本', '姓名和成绩保留']]) {
    const h = harness(), messageNode = {textContent:'', className:''}, asked = [], sent = [];
    h.context.document.querySelector = selector => selector === '#message' ? messageNode : null;
    h.evaluate(`lang='${lang}'; data.players=[{id:'p1',name:'Ana',status:'Active',rating:0}]; selected='p1'`);
    assert.ok(h.evaluate('playersScreen()').includes(`data-action="face-forget" data-id="p1"`), `${lang}: the profile offers it`);
    assert.ok(h.evaluate('playersScreen()').includes(`>${button}</button>`), `${lang}: labelled ${button}`);
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
  h.evaluate(`data.players=[{id:'p1',name:'Ada Lovelace',status:'Active',rating:700},{id:'p2',name:'Bo',status:'Active',rating:600}];
    const night=()=>({id:'t1',name:'Friday',format:'singles',raceTo:3,status:'complete',
      entrants:[{id:'e1',members:[{pid:'p1',name:'Ada'}]},{id:'e2',members:[{pid:'p2',name:'Bo'}]},{id:'e3',members:[{pid:null,name:'Walk-in Wu'}]}],
      matches:[{id:'m1',round:1,sides:['e1',null],score:[0,0],status:'complete',result:'bye',winnerId:'e1',absent:[]},
               {id:'m2',round:1,sides:['e2','e3'],score:[3,1],status:'complete',result:'played',winnerId:'e2',absent:[]},
               {id:'m3',round:2,sides:['e1','e2'],score:[3,2],status:'complete',result:'played',winnerId:'e1',absent:[]}]});
    data.tournament=night();data.history=[Object.assign(night(),{id:'h1',archivedAt:'2026-09-01T00:00:00Z'})];data.events=[];data.notes=[]`);
  const views = {floor: h.evaluate('floorScreen()'), setup: h.evaluate('setupScreen()'), matches: h.evaluate('bracketScreen()'), records: h.evaluate('recordsScreen()')};
  for (const [name, html] of Object.entries(views)) assert.ok(!/>Ada</.test(html) && !/\bAda \//.test(html), `${name}: the stale snapshot name never shows`);
  assert.ok(views.matches.includes('Ada Lovelace'), 'bracket shows the current name');
  // The night's own log lives inside its timeline body (5.4), so the night is the anchor, not <details>.
  const archive = views.records.slice(views.records.indexOf('data-event="h1"'));
  assert.ok(archive.includes('Ada Lovelace'), 'the archived event reads the live roster name for a regular');
  assert.ok(!/Ada —|— Ada\b|>Ada</.test(archive), 'the archive never falls back to the draw-time copy while the regular exists');
  assert.ok(archive.includes('Walk-in Wu'), 'a guest keeps the name typed at the desk');
  // a deleted regular (no roster row) still reads by the snapshot, never "Unknown"
  h.evaluate("data.players=data.players.filter(p=>p.id!=='p2')");
  assert.ok(h.evaluate('bracketScreen()').includes('>Bo'), 'the snapshot is the fallback when the regular is gone');
  assert.ok(/· Bo — Walk-in Wu ·/.test(h.evaluate('recordsScreen()')), 'the archive in Records falls back to the snapshot too');
  assert.equal(h.evaluate('JSON.stringify(resultStats("p1"))'), '{"wins":2,"losses":0}', 'the rename leaves the record whole; the bye is not a win');
  h.evaluate("lang='zh'");
  assert.equal(h.evaluate("validationMessage('Name held by a guest in this event; add the guest to the regulars instead')"), '这个名字属于本场赛事的一位访客；请把该访客加入常客，而不是给常客改成同名。');
});
test('a refusal is readable over an open modal: the message sits above the backdrop', () => {
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const z = selector => Number(css.match(new RegExp(`${selector.replace(/[.#()]/g, '\\$&')}\\{[^}]*z-index:(\\d+)`))[1]);
  // The polish's distill step wrote `:is(#ops-shell, #ops-footer)` as `#ops-shell` (same specificity).
  assert.ok(z('#ops-shell #message') > z('.modal-backdrop'), 'the player modal must not cover the reason it was refused');
});
test('a bye reads Bye, never Signed or Waiting, and is not a signed card (R5)', () => {
  const h = harness();
  h.evaluate(`data.players=[];data.events=[];data.notes=[];
    const night=()=>({id:'t1',name:'Friday',format:'singles',raceTo:3,status:'active',
      entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bea'}]},{id:'e3',members:[{pid:null,name:'Cai'}]}],
      matches:[{id:'m1',round:1,sides:['e1',null],score:[0,0],status:'complete',result:'bye',winnerId:'e1',table:null,absent:[]},
               {id:'m2',round:1,sides:['e2','e3'],score:[3,1],status:'complete',result:'played',winnerId:'e2',table:null,absent:[]},
               {id:'m3',round:2,sides:['e1','e2'],score:[0,0],status:'scheduled',table:null,absent:[],sources:['m1','m2']}]});
    data.tournament=night();data.history=[Object.assign(night(),{id:'h1',status:'complete',archivedAt:'2026-09-01T00:00:00Z'})]`);
  for (const [lang, bye, signed, waiting, cards] of [['en', 'Bye', 'Signed', 'Waiting', 'Cards signed'], ['zh', '轮空', '已签', '待定', '已签赛果']]) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('bracketScreen()');
    const card = html.slice(html.indexOf('class="rounds"'));
    const first = card.slice(0, card.indexOf('<h3>', card.indexOf('<h3>') + 1));
    assert.ok(first.includes(`>${bye}<`), `${lang}: the bye card is labelled ${bye}`);
    assert.equal((first.match(new RegExp(`>${signed}<`, 'g')) || []).length, 1, `${lang}: only the played card says ${signed}`);
    assert.ok(!first.includes(`>${waiting}<`), `${lang}: the empty side of a bye never reads ${waiting}`);
    const tile = html.match(new RegExp(`<small>${cards}</small><strong>([^<]*)</strong>`))[1];
    assert.equal(tile, '1/2', `${lang}: byes are left out of the signed count and its total`);
    const rec = h.evaluate('recordsScreen()'), archive = rec.slice(rec.indexOf('data-event="h1"'));
    assert.ok(archive.includes(`>${bye}<`) && !archive.includes(`${esc_(waiting)}`), `${lang}: the archive labels the bye too`);
    const play = h.evaluate('playScreen()');
    assert.equal(play.match(new RegExp(`<small>${cards}</small><strong>([^<]*)</strong>`))[1], '1/2', `${lang}: the Play header tile agrees`);
  }
  assert.equal(h.evaluate('JSON.stringify(resultStats("x"))'), '{"wins":0,"losses":0}');
});
function esc_(s) { return `>${s}<`; }
test('a placeholder guest name is stopped at the field, in both languages (R5)', async () => {
  const h = harness();
  const guest = {validity: '', reported: 0, setCustomValidity(text) { this.validity = text; }, reportValidity() { this.reported++; return false; }};
  const form = values => ({preventDefault() {}, target: {getAttribute: () => 'entrant-form', classList: {contains: () => false}, querySelector: sel => sel === '[name=guest0]' ? guest : null, querySelectorAll: () => [], values}});
  for (const name of ['na', ' N/A ', 'Bye', 'TBD', '轮空', '輪空']) await h.handlers.submit(form({pid0: '', guest0: name}));
  assert.equal(h.evaluate('calls.length'), 0, 'a placeholder never reaches the server');
  assert.equal(guest.reported, 6);
  assert.equal(guest.validity, 'Byes are added by the draw automatically. Type the guest’s real name.');
  h.evaluate("lang='zh'");
  await h.handlers.submit(form({pid0: '', guest0: 'bye'}));
  assert.equal(guest.validity, '轮空由抽签自动安排，请输入访客的真实姓名。');
  assert.equal(h.evaluate(`validationMessage("A bye is added by the draw; type the guest's real name")`), '轮空由抽签自动安排，请输入访客的真实姓名。');
  await h.handlers.submit(form({pid0: '', guest0: 'Nadia'}));
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls.map(c => c.payload))')), [{members: [{name: 'Nadia'}]}]);
});
test('racking an unsaved event saves the name the form shows first (R2)', async () => {
  const h = harness();
  const nameField = {value: '8-Ball Open · Fri 9/26'};
  h.context.document.querySelector = sel => sel === '#settings-form [name=name]' ? nameField : null;
  h.evaluate("data.tournament={id:'t1',name:'',format:'singles',tables:1,raceTo:1,status:'registration',entrants:[{id:'e1',members:[]},{id:'e2',members:[]}],matches:[]}");
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'tournament-start'}}}});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'tournament_setup', payload: {name: '8-Ball Open · Fri 9/26'}}, {name: 'tournament_start'}]);
  // an event that already has a name is racked as is
  h.evaluate("calls=[];data.tournament.name='Friday 8-Ball'");
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'tournament-start'}}}});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'tournament_start'}]);
});
test('after the draw and in the archive only the name can be edited, and it is audited (R2)', async () => {
  const h = harness();
  h.evaluate(`data.events=[{action:'tournament_rename',createdAt:'2026-09-26T10:00:00Z',revision:9,context:{id:'t1',name:'New'}}];data.notes=[];data.players=[];
    data.tournament={id:'t1',name:'Friday',format:'singles',tables:1,raceTo:3,status:'active',entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bea'}]}],matches:[{id:'m1',round:1,sides:['e1','e2'],score:[0,0],status:'scheduled',table:null,absent:[]}]};
    data.history=[{id:'h1',name:'',format:'singles',raceTo:1,status:'complete',archivedAt:'2026-09-01T00:00:00Z',entrants:[],matches:[]}]`);
  for (const [lang, rename, label] of [['en', 'Rename event', 'Event renamed'], ['zh', '重命名赛事', '赛事已重命名']]) {
    h.evaluate(`lang='${lang}'`);
    const setup = h.evaluate('setupScreen()');
    const form = setup.match(/<form id="rename-form"[^]*?<\/form>/);
    assert.ok(form, `${lang}: a rename form is offered after the draw`);
    assert.ok(/name="name"/.test(form[0]) && !/name="(format|raceTo|tables)"/.test(form[0]), `${lang}: the rename form carries the name only`);
    assert.ok(form[0].includes(`>${rename}<`), `${lang}: the button says ${rename}`);
    assert.ok(/<fieldset disabled/.test(setup), `${lang}: the rules stay locked`);
    assert.equal((setup.match(/name="name"/g) || []).length, 1, `${lang}: the name is edited in one place only`);
    const matches = h.evaluate('recordsScreen()');
    assert.ok(matches.includes('data-action="rename-archived"') && matches.includes('data-id="h1"'), `${lang}: an archived event can be renamed`);
    assert.ok(!/<summary>h1 /.test(matches), `${lang}: an unnamed archive never shows its raw id`);
    assert.ok(h.evaluate('auditLine(data.events[0])').includes(label), `${lang}: the audit line reads ${label}`);
  }
  const submit = values => h.handlers.submit({preventDefault() {}, target: {getAttribute: () => 'rename-form', classList: {contains: () => false}, querySelector: () => null, querySelectorAll: () => [], values}});
  await submit({id: 't1', name: '  Friday Final '});
  h.context.prompt = () => ' July night ';
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'rename-archived', id: 'h1'}}}});
  h.context.prompt = () => null;
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'rename-archived', id: 'h1'}}}});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'tournament_rename', payload: {id: 't1', name: 'Friday Final'}}, {name: 'tournament_rename', payload: {id: 'h1', name: 'July night'}}]);
});
test('forfeit and in-match absence are reachable from the Matches bracket, each behind a confirm (F1, R7)', async () => {
  const h = harness();
  h.evaluate(`data.players=[];data.events=[];data.notes=[];data.history=[];
    data.tournament={id:'t1',name:'Friday',format:'singles',tables:2,raceTo:3,status:'active',
      entrants:[{id:'e1',members:[{pid:null,name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Bea'}]},{id:'e3',members:[{pid:null,name:'Cai'}]},{id:'e4',members:[{pid:null,name:'Dee'}]}],
      matches:[{id:'m1',round:1,sides:['e1','e2'],score:[0,0],status:'scheduled',table:null,absent:[]},
               {id:'m2',round:1,sides:['e3','e4'],score:[1,0],status:'live',table:1,absent:[]},
               {id:'m3',round:2,sides:[null,null],score:[0,0],status:'pending',table:null,absent:[],sources:['m1','m2']}]}`);
  const html = h.evaluate('bracketScreen()');
  const card = id => html.slice(html.indexOf(`${id.slice(0, 8)}</small>`), html.indexOf('</div></div>', html.indexOf(`${id.slice(0, 8)}</small>`)) + 400);
  for (const id of ['m1', 'm2']) {
    const c = card(id);
    assert.ok(/data-action="forfeit"[^>]*data-side="0"/.test(c) && /data-action="forfeit"[^>]*data-side="1"/.test(c), `${id}: forfeit for either side`);
    assert.ok(/data-action="absence"[^>]*data-absent="true"/.test(c), `${id}: a side can be marked not here`);
  }
  assert.ok(!/m3[^]*data-action="forfeit"/.test(html.slice(html.indexOf('m3'.slice(0, 8)))), 'a pending match (no sides yet) offers no forfeit');
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  const asked = [];
  h.context.confirm = msg => { asked.push(msg); return false; };
  await click({action: 'forfeit', id: 'm1', side: '0'});
  await click({action: 'absence', id: 'm1', side: '1', absent: 'true'});
  await click({action: 'absence', id: 'm1', side: '1', absent: 'false'});
  assert.equal(h.evaluate('calls.length'), 0, 'a cancelled confirm sends nothing');
  assert.deepEqual(asked, ['Record a forfeit for this side and advance the opponent?', 'Mark this player as not here? The match is held until they return; the table is released.', 'Mark this player as here again? The match can then go to a table.']);
  h.context.confirm = msg => { asked.push(msg); return true; };
  h.evaluate("lang='zh'");
  await click({action: 'absence', id: 'm2', side: '0', absent: 'true'});
  await click({action: 'forfeit', id: 'm2', side: '1'});
  assert.equal(asked[3], '将此球员标记为未到场？比赛将暂缓直到其返回，球台会被释放。');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'match_absence', payload: {id: 'm2', side: 0, absent: true}}, {name: 'match_forfeit', payload: {id: 'm2', side: 1}}]);
});
test('standings count results, not ratings; the event table sorts wins, win %, name (R4)', () => {
  const h = harness();
  // Ann beats Bea (played) and Cai (forfeit: Cai no-show); Dee has a bye then loses to Ann... (sizes kept small)
  h.evaluate(`data.events=[];data.notes=[];
    data.players=[{id:'pa',name:'Ann',status:'Active',rating:100},{id:'pb',name:'Bea',status:'Active',rating:900},{id:'pc',name:'Cai',status:'Active',rating:500},{id:'pd',name:'Dee',status:'Active',rating:400}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    data.tournament={id:'t2',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',
      entrants:[E('a','pa','Ann'),E('b','pb','Bea'),E('c','pc','Cai'),E('d','pd','Dee'),E('g',null,'Gus')],
      matches:[{id:'x1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[]},
               {id:'x2',round:1,sides:['b','c'],score:[3,1],status:'complete',result:'played',winnerId:'b',absent:[]},
               {id:'x3',round:1,sides:['d','g'],score:[0,0],status:'complete',result:'forfeit',winnerId:'d',absent:[]},
               {id:'x4',round:2,sides:['a','b'],score:[3,2],status:'complete',result:'played',winnerId:'a',absent:[]},
               {id:'x5',round:2,sides:['d',null],score:[0,0],status:'pending',absent:[]}]};
    data.history=[{id:'t1',name:'Last week',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T00:00:00Z',
      entrants:[E('a1','pa','Ann'),E('b1','pb','Bea')],
      matches:[{id:'y1',round:1,sides:['a1','b1'],score:[1,3],status:'complete',result:'played',winnerId:'b1',absent:[]}]}]`);
  assert.equal(h.evaluate('JSON.stringify(record(tournament(),"a"))'), '{"wins":1,"losses":0,"played":1}', 'a bye is neither a win nor a played match');
  assert.equal(h.evaluate('JSON.stringify(record(tournament(),"d"))'), '{"wins":1,"losses":0,"played":1}', 'a forfeit win counts as a signed result');
  assert.equal(h.evaluate('JSON.stringify(record(tournament(),"g"))'), '{"wins":0,"losses":1,"played":1}');
  const cell = (standing, name, col) => {
    const at = standing.indexOf(`>${name}<`);
    assert.ok(at > 0, `the standing lists ${name}`);
    const m = standing.slice(at).match(new RegExp(`data-col="${col.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"[^>]*>([^<]*)<`));
    assert.ok(m, `${name}: a ${col} cell`);
    return m[1];
  };
  for (const [lang, rating, table, played, wl, rate] of [['en', 'House rating (manual)', 'Event table', 'Played', 'W\u2013L', 'Win %'], ['zh', '球房评分（手动）', '本场战绩表', '场次', '胜\u2013负', '胜率']]) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('playScreen()'), standing = h.evaluate('playersScreen()');
    for (const label of [rating, played, wl, rate]) assert.ok(standing.includes(`>${label}<`), `${lang}: standing column ${label}`);
    // All-time, signed results only: Ann 1-1 (bye excluded), Bea 2-1 (3 played), Dee 1-0 (forfeit win).
    assert.equal(cell(standing, 'Bea', rating), '900');
    assert.equal(cell(standing, 'Bea', played), '3');
    assert.equal(cell(standing, 'Bea', wl), '2\u20131');
    assert.equal(cell(standing, 'Bea', rate), '67%');
    assert.equal(cell(standing, 'Ann', played), '2');
    assert.equal(cell(standing, 'Ann', wl), '1\u20131');
    assert.equal(cell(standing, 'Ann', rate), '50%');
    assert.equal(cell(standing, 'Dee', wl), '1\u20130');
    assert.equal(cell(standing, 'Dee', rate), '100%');
    assert.ok(!standing.includes('>Gus<'), `${lang}: a guest holds no house standing (6.1)`);
    const ev = html.slice(html.indexOf(`<table class="event-table"`), html.indexOf('</table>', html.indexOf(`<table class="event-table"`)));
    assert.ok(html.includes(`>${table}<`), `${lang}: event table heading`);
    const order = [...ev.matchAll(/<tr><td>\d+<\/td><td>([^<]+)</g)].map(m => m[1]);
    assert.deepEqual(order, ['Ann', 'Dee', 'Bea', 'Cai', 'Gus'], `${lang}: wins, then win %, then name`);
  }
});
test('a player record is all-time and read-only, with head-to-head from signed matches only (R15, R8)', async () => {
  const h = harness();
  h.evaluate(`data.events=[];data.notes=[];
    data.players=[{id:'pa',name:'Ann',status:'Active',rating:100,joinedAt:'2026-01-01T00:00:00Z'},{id:'pb',name:'Bea',status:'Active',rating:900},{id:'pc',name:'Cai',status:'Active',rating:500}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    data.tournament={id:'t3',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',
      entrants:[E('a','pa','Ann'),E('b','pb','Bea'),E('g',null,'Gus')],
      matches:[{id:'x1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[]},
               {id:'x2',round:1,sides:['b','g'],score:[0,0],status:'complete',result:'forfeit',winnerId:'b',absent:[],completedAt:'2026-09-26T20:00:00Z'},
               {id:'x3',round:2,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',absent:[],completedAt:'2026-09-26T21:00:00Z'}]};
    data.history=[
      {id:'t1',name:'First',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T12:00:00Z',entrants:[E('a1','pa','Ann'),E('b1','pb','Bea')],
       matches:[{id:'y1',round:1,sides:['a1','b1'],score:[1,3],status:'complete',result:'played',winnerId:'b1',absent:[],completedAt:'2026-09-01T20:00:00Z'}]},
      {id:'t2',name:'Second',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-10T00:00:00Z',entrants:[E('a2','pa','Ann'),E('c2','pc','Cai'),E('g2',null,'Gus')],
       matches:[{id:'z1',round:1,sides:['a2','c2'],score:[3,0],status:'complete',result:'played',winnerId:'a2',absent:[],completedAt:'2026-09-10T20:00:00Z'},
                {id:'z2',round:1,sides:['g2',null],score:[0,0],status:'complete',result:'bye',winnerId:'g2',absent:[]},
                {id:'z3',round:2,sides:['a2','g2'],score:[0,0],status:'complete',result:'forfeit',winnerId:'g2',absent:[],completedAt:'2026-09-10T21:00:00Z'}]}]`);
  // Ann: vs Bea 1-1 (played), vs Cai 1-0 (played); forfeit loss to Gus and the bye stay out of head-to-head.
  assert.equal(h.evaluate('JSON.stringify(headToHead("pa"))'), JSON.stringify([
    {opponent: 'Bea', guest: false, wins: 1, losses: 1, played: 2, forfeits: 0, last: '2026-09-26T21:00:00Z'},
    {opponent: 'Cai', guest: false, wins: 1, losses: 0, played: 1, forfeits: 0, last: '2026-09-10T20:00:00Z'},
    {opponent: 'Gus', guest: true, wins: 0, losses: 0, played: 0, forfeits: 1, last: '2026-09-10T21:00:00Z'}]));
  h.evaluate('render=()=>{}');
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  await click({action: 'select-player', id: 'pa'});
  const modal = h.evaluate('playersScreen()');
  assert.ok(modal.includes('data-action="player-record"') && modal.includes('data-id="pa"'), 'the regular profile links to the record');
  await click({action: 'player-record', id: 'pa'});
  for (const [lang, title, h2h, scope, sample, guest] of [
    ['en', 'Player record', 'Head-to-head', 'Signed results in 3 events since 2026-09-01. Read-only.', 'Sample', 'guest, matched by name'],
    ['zh', '球员战绩', '交手记录', '自 2026-09-01 起 3 场赛事的已签赛果', '样本', '访客，按姓名匹配']]) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('playersScreen()');
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
  assert.equal(h.evaluate('calls.length'), 0, 'reading a record never writes');
  await click({action: 'record-back'});
  assert.ok(h.evaluate('playersScreen()').includes('data-action="player-record"'), 'back returns to the profile');
});
test('a results sheet prints the whole bracket and copies as text, champion from the final (R10)', async () => {
  const h = harness();
  h.evaluate(`data.events=[];data.notes=[];data.players=[{id:'pa',name:'Ada',status:'Active',rating:1}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    data.tournament={id:'t0',name:'',format:'singles',tables:1,raceTo:3,status:'registration',entrants:[],matches:[]};
    data.history=[{id:'h1',name:'Friday 8-Ball',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-26T12:00:00Z',
      entrants:[E('a','pa','Ada (old)'),E('b',null,'Bo'),E('c',null,'Cy')],
      matches:[{id:'m1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[]},
               {id:'m2',round:1,sides:['b','c'],score:[0,0],status:'complete',result:'forfeit',winnerId:'b',absent:[]},
               {id:'m3',round:2,sides:['a','b'],score:[3,2],status:'complete',result:'played',winnerId:'a',absent:[],sources:['m1','m2']}]}]`);
  assert.equal(h.evaluate("resultsText(data.history[0])"), [
    'Friday 8-Ball · 2026-09-26', 'Singles · Race to 3', 'Champion: Ada', '',
    'Round 1', 'Ada: bye (advances, not a win)', 'Bo wins by forfeit vs Cy', '',
    'Final', 'Ada 3–2 Bo', '', 'Signed results only. A bye advances a player but is not a win.'].join('\n'));
  h.evaluate("lang='zh'");
  assert.equal(h.evaluate("resultsText(data.history[0])"), [
    'Friday 8-Ball · 2026-09-26', '单打 · 抢3', '冠军：Ada', '',
    '轮次 1', 'Ada：轮空晋级（不计胜场）', 'Cy 弃权，Bo 晋级', '',
    '决赛', 'Ada 3–2 Bo', '', '仅含已签赛果。轮空晋级不计为胜场。'].join('\n'));
  // an unfinished bracket never names a champion
  h.evaluate("lang='en';data.history[0].matches[2]={...data.history[0].matches[2],status:'scheduled',result:undefined,winnerId:null,score:[0,0]}");
  assert.ok(h.evaluate("resultsText(data.history[0])").includes('Champion: not decided yet'));
  assert.ok(h.evaluate("resultsText(data.history[0])").includes('Ada vs Bo: not played yet'));
  h.evaluate("data.history[0].matches[2].sides=['a',null]");
  assert.ok(h.evaluate("resultsText(data.history[0])").includes('Ada vs TBD: not played yet'), 'an undecided side is TBD, never Waiting');
  h.evaluate("data.history[0].matches[2].sides=['a','b']");
  h.evaluate("data.history[0].matches[2]={...data.history[0].matches[2],status:'complete',result:'played',winnerId:'a',score:[3,2]}");
  // the sheet view: reached from the archive, read-only, full bracket, print + copy controls
  h.evaluate('render=()=>{}');
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  assert.ok(h.evaluate('recordsScreen()').includes('data-action="results-sheet" data-id="h1"'), 'each archived event offers its sheet');
  h.evaluate("data.tournament.matches=[{id:'q1',round:1,sides:['x','y'],score:[0,0],status:'scheduled',absent:[]}]");
  assert.ok(h.evaluate('wrapScreen()').includes('data-action="results-sheet" data-id="t0"'), 'tonight has a sheet once drawn');
  h.evaluate('data.tournament.matches=[]');
  assert.ok(!h.evaluate('wrapScreen()').includes('data-action="results-sheet"'), 'no sheet before the draw');
  await click({action: 'results-sheet', id: 'h1'});
  assert.equal(h.evaluate('sheetId'), 'h1', 'the click opens the sheet');
  const sheet = h.evaluate('wrapScreen()');
  assert.ok(sheet.includes('class="stack results-sheet"'), 'the sheet replaces the Close view');
  assert.ok(/class="champion"[^]*?Ada/.test(sheet), 'the champion is the final winner, by the live roster name');
  assert.equal((sheet.match(/class="sheet-round"/g) || []).length, 2, 'every round is on the sheet');
  assert.ok(sheet.includes('data-action="print-sheet"') && sheet.includes('data-action="copy-results"'));
  assert.ok(!/<form|<input/.test(sheet), 'the sheet is read-only');
  let copied = null;
  h.context.navigator = {clipboard: {writeText: async text => { copied = text; }}};
  await click({action: 'copy-results', id: 'h1'});
  assert.equal(copied, h.evaluate("resultsText(data.history[0])"));
  let printed = 0;
  h.context.print = () => { printed++; };
  await click({action: 'print-sheet'});
  assert.equal(printed, 1);
  assert.equal(h.evaluate('calls.length'), 0, 'a sheet never writes');
  await click({action: 'sheet-back'});
  assert.ok(!h.evaluate('wrapScreen()').includes('class="stack results-sheet"'), 'back returns to Close');
  await click({action: 'results-sheet', id: 'h1'});
  h.evaluate('canNavigate=()=>true');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {tab: 'floor'}}}});
  assert.equal(h.evaluate('sheetId'), null, 'leaving the screen closes the sheet');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  const print = css.slice(css.indexOf('@media print'));
  assert.ok(print.length > 20 && /header[^{]*\{[^}]*display:none/.test(print) && /\.no-print[^{]*\{[^}]*display:none/.test(print), 'print hides the shell chrome and the sheet buttons');
  assert.ok(/\.results-sheet[^{]*\.note[^{]*\{[^}]*background:#fff/.test(print), 'the scope note prints on white, not on the dark panel');
});
test('delete only an unsigned event; otherwise hide it from history, which erases nothing (R1)', async () => {
  const h = harness();
  h.evaluate(`data.events=[];data.notes=[];data.players=[{id:'pa',name:'Ada',status:'Active',rating:1}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    data.tournament={id:'t0',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'registration',entrants:[E('x',null,'Xu')],matches:[]};
    data.history=[
      {id:'h1',name:'Signed night',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T12:00:00Z',entrants:[E('a','pa','Ada'),E('b',null,'Bo')],
       matches:[{id:'m1',round:1,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',absent:[]}]},
      {id:'h2',name:'Mistake',format:'singles',raceTo:1,status:'active',archivedAt:'2026-09-02T12:00:00Z',entrants:[E('c',null,'Cy')],matches:[]},
      {id:'h3',name:'Hidden night',hidden:true,format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-03T12:00:00Z',entrants:[E('a3','pa','Ada'),E('d',null,'Di')],
       matches:[{id:'m3',round:1,sides:['a3','d'],score:[0,0],status:'complete',result:'forfeit',winnerId:'a3',absent:[]}]}]`);
  h.evaluate('render=()=>{}');
  for (const [lang, del, hide, unhide, showHidden] of [['en', 'Delete event', 'Hide from history', 'Show in history', 'Show 1 hidden'], ['zh', '删除赛事', '从历史中隐藏', '恢复显示', '显示 1 场已隐藏']]) {
    h.evaluate(`lang='${lang}';showHidden=false`);
    const html = h.evaluate('recordsScreen()');
    // One night is one timeline item: from its own data-event to the next night's.
    const block = id => { const i = html.indexOf(`data-event="${id}"`); if (i < 0) return '';
      const next = html.indexOf('data-event="', i + 12); return html.slice(i, next < 0 ? html.length : next); };
    assert.ok(block('h1').includes(`>${hide}<`) && !block('h1').includes(`>${del}<`), `${lang}: a signed event can only be hidden`);
    assert.ok(block('h2').includes(`>${del}<`), `${lang}: an unsigned event can be deleted`);
    assert.ok(!html.includes('Hidden night'), `${lang}: a hidden event is out of the list`);
    assert.ok(html.includes(`>${showHidden}<`), `${lang}: the hidden count is offered`);
    h.evaluate('showHidden=true');
    const all = h.evaluate('recordsScreen()');
    assert.ok(all.includes('Hidden night') && all.includes(`>${unhide}<`), `${lang}: hidden events can be shown and restored`);
    assert.ok(h.evaluate('wrapScreen()').includes('data-action="event-delete" data-id="t0"'), `${lang}: tonight, unsigned, can be deleted from Close`);
  }
  assert.equal(h.evaluate('JSON.stringify(resultStats("pa"))'), '{"wins":2,"losses":0}', 'a hidden event still counts: hiding erases nothing');
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  const asked = [];
  h.context.confirm = msg => { asked.push(msg); return false; };
  h.evaluate("lang='en'");
  await click({action: 'event-delete', id: 'h2'});
  await click({action: 'event-hide', id: 'h1', hidden: 'true'});
  assert.equal(h.evaluate('calls.length'), 0, 'a cancelled confirm sends nothing');
  assert.deepEqual(asked, ['Delete “Mistake”? No result was signed in it. This cannot be undone.', 'Hide “Signed night” from history? Its results and every player’s stats stay; you can show it again.']);
  h.context.confirm = msg => { asked.push(msg); return true; };
  h.evaluate("lang='zh'");
  await click({action: 'event-delete', id: 'h2'});
  await click({action: 'event-hide', id: 'h1', hidden: 'true'});
  await click({action: 'event-hide', id: 'h3', hidden: 'false'});
  assert.equal(asked[2], '删除“Mistake”？该赛事没有已签赛果。此操作无法撤销。');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [
    {name: 'tournament_delete', payload: {id: 'h2', confirm: true}},
    {name: 'tournament_hide', payload: {id: 'h1', hidden: true, confirm: true}},
    {name: 'tournament_hide', payload: {id: 'h3', hidden: false, confirm: true}}]);
  for (const [action, en, zh] of [['tournament_delete', 'Event deleted (nothing was signed)', '删除赛事（无已签赛果）'], ['tournament_hide', 'Event hidden / shown in history', '赛事在历史中隐藏 / 恢复']]) {
    h.evaluate(`lang='en'`); assert.ok(h.evaluate(`auditLine({action:'${action}',createdAt:'2026-09-26T00:00:00Z',revision:1,context:{name:'X'}})`).includes(en));
    h.evaluate(`lang='zh'`); assert.ok(h.evaluate(`auditLine({action:'${action}',createdAt:'2026-09-26T00:00:00Z',revision:1,context:{name:'X'}})`).includes(zh));
  }
  assert.equal(h.evaluate(`validationMessage('An event with a signed result cannot be deleted; hide it from history instead')`), '有已签赛果的赛事不能删除，请改为从历史中隐藏。');
});
test('a second chance is a labelled random draw, confirmed, undoable, never a result (R6)', async () => {
  const h = harness();
  h.evaluate(`data.events=[];data.notes=[];data.history=[];data.players=[];
    const E=(id,name)=>({id,members:[{pid:null,name}]});
    data.tournament={id:'t1',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',
      entrants:[E('a','Ann'),E('b','Bea'),E('c','Cai'),E('d','Dee'),E('e','Eve'),E('f','Fay')],
      matches:[{id:'m1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[],sources:[]},
               {id:'m2',round:1,sides:['b',null],score:[0,0],status:'complete',result:'bye',winnerId:'b',absent:[],sources:[]},
               {id:'m3',round:1,sides:['c','d'],score:[3,1],status:'complete',result:'played',winnerId:'c',absent:[],sources:[]},
               {id:'m4',round:1,sides:['e','f'],score:[3,0],status:'complete',result:'played',winnerId:'e',absent:[],sources:[]},
               {id:'m5',round:2,sides:['a','b'],score:[0,0],status:'scheduled',absent:[],sources:['m1','m2']},
               {id:'m6',round:2,sides:['c','e'],score:[0,0],status:'scheduled',absent:[],sources:['m3','m4']}]}`);
  h.evaluate('render=()=>{}');
  for (const [lang, title, drawBtn, label] of [['en', 'Second chance', 'Draw a round-1 loser', 'Random draw, not a result'], ['zh', '复活赛', '抽取一名首轮负者', '随机抽签，不是赛果']]) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('wrapScreen()');
    assert.ok(html.includes(`>${title}<`) && html.includes(`>${drawBtn}<`), `${lang}: the draw is offered while round 2 is unsigned`);
    assert.ok(html.includes(label), `${lang}: it is labelled as a random draw`);
  }
  h.evaluate("data.tournament.matches[3]={...data.tournament.matches[3],status:'scheduled',result:undefined,winnerId:null}");
  assert.ok(!h.evaluate('wrapScreen()').includes('data-action="revival-draw"'), 'no draw until every round-1 loser is known');
  h.evaluate("data.tournament.matches[3]={...data.tournament.matches[3],status:'complete',result:'played',winnerId:'e'}");
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  const asked = [];
  h.context.confirm = msg => { asked.push(msg); return false; };
  h.evaluate("lang='en'");
  await click({action: 'revival-draw'});
  assert.equal(h.evaluate('calls.length'), 0, 'a cancelled confirm draws nothing');
  assert.equal(asked[0], 'Draw one round-1 loser at random to re-enter the bracket in a bye slot? The draw is recorded with its seed; no result changes.');
  h.context.confirm = msg => { asked.push(msg); return true; };
  await click({action: 'revival-draw'});
  // after the draw the card shows who, the pool and the seed, and offers undo
  h.evaluate(`data.tournament.revival={seed:12345,pool:['d','f'],entrant:'f',name:'Fay',match:'m2',next:'m5',side:1,holder:'b',signed:2,drawnAt:'2026-09-26T20:00:00Z'};
    Object.assign(data.tournament.matches[1],{sides:['b','f'],status:'scheduled',winnerId:null});delete data.tournament.matches[1].result;
    Object.assign(data.tournament.matches[4],{sides:['a',null],status:'pending'})`);
  h.evaluate("lang='zh'");
  const drawn = h.evaluate('wrapScreen()');
  assert.ok(drawn.includes('抽中：Fay') && drawn.includes('种子 12345') && drawn.includes('候选：Dee、Fay'), '中: who, the seed and the pool are shown');
  assert.ok(drawn.includes('data-action="revival-undo"'), 'undo is offered until the next result');
  assert.ok(!drawn.includes('data-action="revival-draw"'), 'one draw per event');
  await click({action: 'revival-undo'});
  assert.equal(asked.at(-1), '撤销这次复活抽签？该空位将恢复为轮空，签过的赛果不受影响。');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'revival_draw', payload: {confirm: true}}, {name: 'revival_undo', payload: {confirm: true}}]);
  // after a newer signed result, undo is gone and the drawn line stays as history
  h.evaluate("data.tournament.matches[5]={...data.tournament.matches[5],status:'complete',result:'played',winnerId:'c',score:[3,2]}");
  const closed = h.evaluate('wrapScreen()');
  assert.ok(!closed.includes('data-action="revival-undo"') && closed.includes('抽中：Fay'));
  for (const [action, en, zh] of [['revival_draw', 'Second chance drawn (random, audited)', '复活赛抽签（随机，已记录）'], ['revival_undo', 'Second chance undone', '撤销复活赛抽签']]) {
    h.evaluate("lang='en'"); assert.ok(h.evaluate(`auditLine({action:'${action}',createdAt:'2026-09-26T00:00:00Z',revision:1,context:{name:'Fay'}})`).includes(en));
    h.evaluate("lang='zh'"); assert.ok(h.evaluate(`auditLine({action:'${action}',createdAt:'2026-09-26T00:00:00Z',revision:1,context:{name:'Fay'}})`).includes(zh));
  }
  assert.equal(h.evaluate(`validationMessage('No round-2 bye slot to fill')`), '没有可填补的第二轮轮空位。');
});
test('doubles can pair solo sign-ups at random: seed shown, re-roll, accept (R3)', async () => {
  const h = harness();
  h.evaluate(`data.events=[];data.notes=[];data.history=[];data.players=[{id:'pa',name:'Ada',status:'Active',rating:5}];
    data.tournament={id:'t1',name:'Doubles night',format:'doubles',tables:1,raceTo:3,status:'registration',entrants:[],matches:[],
      pool:[{pid:'pa',name:'Ada'},{pid:null,name:'Bo'},{pid:null,name:'Cy'}],pairing:null}`);
  for (const [lang, title, add, draw, odd] of [['en', 'Random pairing', 'Add solo player', 'Pair at random', 'An even number of solo players is needed'], ['zh', '随机配对', '添加单人报名', '随机配对搭档', '需要偶数名单人报名者']]) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('setupScreen()');
    assert.ok(html.includes(`>${title}<`) && html.includes(`>${add}<`), `${lang}: a doubles event offers a solo pool`);
    assert.ok(/<button[^>]*data-action="pair-draw"[^>]*disabled/.test(html) && html.includes(odd), `${lang}: an odd pool cannot be paired, and says why`);
    assert.ok(html.includes('Ada') && html.includes('Bo') && html.includes('Cy'));
    assert.ok(html.includes(`>${draw}<`));
  }
  h.evaluate("data.tournament.format='singles'");
  assert.ok(!h.evaluate('setupScreen()').includes('id="solo-form"'), 'singles has no pairing step');
  h.evaluate("data.tournament.format='doubles';data.tournament.pool.push({pid:null,name:'Di'});data.tournament.pairing={seed:424242,teams:[[{pid:null,name:'Cy'},{pid:'pa',name:'Ada'}],[{pid:null,name:'Di'},{pid:null,name:'Bo'}]]}");
  for (const [lang, seed, accept, reroll, label] of [['en', 'seed 424242', 'Use these teams', 'Re-roll', 'Random draw of partners only; results are never drawn.'], ['zh', '种子 424242', '采用这些组合', '重新抽签', '只随机决定搭档，比赛结果从不抽签。']]) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('setupScreen()');
    assert.ok(html.includes(seed) && html.includes(`>${accept}<`) && html.includes(`>${reroll}<`) && html.includes(label), `${lang}: the preview shows the seed, accept and re-roll`);
    assert.ok(html.includes('Cy / Ada') && html.includes('Di / Bo'), `${lang}: the teams are shown before they count`);
    assert.ok(!html.includes('id="entrant-form"'), `${lang}: registration is locked while a pairing is shown`);
  }
  h.evaluate('render=()=>{}');
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  await click({action: 'pair-draw'});
  await click({action: 'pair-accept', seed: '424242'});
  await click({action: 'pair-clear'});
  await click({action: 'pool-remove', name: 'Bo'});
  const submit = values => h.handlers.submit({preventDefault() {}, target: {getAttribute: () => 'solo-form', classList: {contains: () => false}, querySelector: () => ({setCustomValidity() {}, reportValidity() {}}), querySelectorAll: () => [], values}});
  await submit({solo_pid: '', solo_name: '  Eve '});
  await submit({solo_pid: 'pa', solo_name: ''});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [
    {name: 'pair_draw'}, {name: 'pair_accept', payload: {seed: 424242}}, {name: 'pair_clear'},
    {name: 'pool_remove', payload: {name: 'Bo'}}, {name: 'solo_add', payload: {member: {name: 'Eve'}}}, {name: 'solo_add', payload: {member: {pid: 'pa'}}}]);
  for (const [action, en, zh] of [['pair_draw', 'Partners drawn at random', '随机抽取搭档'], ['pair_accept', 'Random pairs registered', '随机组合已报名']]) {
    h.evaluate("lang='en'"); assert.ok(h.evaluate(`auditLine({action:'${action}',createdAt:'2026-09-26T00:00:00Z',revision:1,context:{seed:1}})`).includes(en));
    h.evaluate("lang='zh'"); assert.ok(h.evaluate(`auditLine({action:'${action}',createdAt:'2026-09-26T00:00:00Z',revision:1,context:{seed:1}})`).includes(zh));
  }
  assert.equal(h.evaluate(`validationMessage('The pairing changed; review the teams again')`), '配对已变化，请重新查看组合。');
});
test('a redrawn second chance says so on the card, the sheet and the copied text (R6 follow-up)', async () => {
  const h = harness();
  h.evaluate(`data.events=[];data.notes=[];data.history=[];data.players=[];
    const E=(id,name)=>({id,members:[{pid:null,name}]});
    data.tournament={id:'t1',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',
      entrants:[E('a','Ann'),E('b','Bea'),E('c','Cai'),E('d','Dee'),E('e','Eve'),E('f','Fay')],
      matches:[{id:'m1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[],sources:[]},
               {id:'m2',round:1,sides:['b','f'],score:[0,0],status:'scheduled',absent:[],sources:[]},
               {id:'m3',round:1,sides:['c','d'],score:[3,1],status:'complete',result:'played',winnerId:'c',absent:[],sources:[]},
               {id:'m4',round:1,sides:['e','f'],score:[3,0],status:'complete',result:'played',winnerId:'e',absent:[],sources:[]},
               {id:'m5',round:2,sides:['a',null],score:[0,0],status:'pending',absent:[],sources:['m1','m2']},
               {id:'m6',round:2,sides:['c','e'],score:[0,0],status:'scheduled',absent:[],sources:['m3','m4']}],
      revival:{seed:777,pool:['d','f'],entrant:'f',name:'Fay',match:'m2',next:'m5',side:1,holder:'b',signed:2,drawnAt:'2026-09-26T20:00:00Z',attempt:1},revival_draws:1}`);
  h.evaluate("lang='en'");
  let card = h.evaluate('revivalCard()');
  assert.ok(card.includes('Draw 1') && !card.includes('Redrawn'), 'a first draw says draw 1 and nothing more');
  h.evaluate('data.tournament.revival.attempt=2;data.tournament.revival_draws=2;data.tournament.revival.seed=888');
  for (const [lang, n, note] of [['en', 'Draw 2', 'Redrawn after an undo — earlier draws are in the audit log'], ['zh', '第 2 次抽签', '撤销后重抽——之前的抽签记录在日志里']]) {
    h.evaluate(`lang='${lang}'`);
    card = h.evaluate('revivalCard()');
    assert.ok(card.includes(n) && card.includes(note), `${lang}: the card shows ${n} and the redraw note`);
  }
  // an undone draw with no current pick still says the count, so the history is not lost
  h.evaluate("lang='en';const r=data.tournament.revival;delete data.tournament.revival");
  assert.ok(h.evaluate('revivalCard()').includes('Draws so far: 2 — each one is in the audit log'), 'after an undo the card keeps the count');
  h.evaluate('data.tournament.revival_draws=1');
  assert.ok(h.evaluate('revivalCard()').includes('Draws so far: 1 — each one is in the audit log'), 'one undone draw still shows');
  h.evaluate("lang='zh'");
  assert.ok(h.evaluate('revivalCard()').includes('已抽签 1 次——每次都记录在日志里'));
  h.evaluate("lang='en';data.tournament.revival_draws=2");
  h.evaluate('data.tournament.revival=r');
  for (const [lang, line] of [['en', 'Second chance (random draw, not a result): Fay · seed 888 · draw 2'], ['zh', '复活赛（随机抽签，不是赛果）：Fay · 种子 888 · 第 2 次抽签']]) {
    h.evaluate(`lang='${lang}'`);
    const text = h.evaluate('resultsText(tournament())');
    assert.ok(text.split('\n').includes(line), `${lang}: the copied text carries the second-chance line: ${line}`);
    const sheet = h.evaluate('resultsSheet(tournament())');
    assert.ok(sheet.includes(line), `${lang}: the sheet carries it too`);
  }
  h.evaluate("delete data.tournament.revival;data.tournament.revival_draws=0");
  assert.ok(!h.evaluate('resultsText(tournament())').includes('Second chance'), 'no second chance, no line');
});
test('every table the operations screens add sits in a .table-wrap, so a wide table never widens the page', async () => {
  const h = harness();
  h.evaluate(`data.events=[];data.notes=[];
    data.players=[{id:'pa',name:'Alexandria Montgomery-Smythe',status:'Active',rating:720},{id:'pb',name:'Bo',status:'Active',rating:650},{id:'pc',name:'Cy',status:'Active',rating:600}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    data.tournament={id:'t2',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'active',entrants:[E('a','pa','Alexandria Montgomery-Smythe'),E('b','pb','Bo')],
      matches:[{id:'x1',round:1,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',absent:[]}]};
    data.history=[{id:'t1',name:'Last week',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T12:00:00Z',entrants:[E('a1','pa','Alexandria Montgomery-Smythe'),E('c1','pc','Cy')],
      matches:[{id:'y1',round:1,sides:['a1','c1'],score:[1,3],status:'complete',result:'played',winnerId:'c1',absent:[]}]}];render=()=>{}`);
  const bare = html => [...html.matchAll(/(.{0,40})<table\b[^>]*>/g)].filter(m => !m[1].endsWith('<div class="table-wrap">')).map(m => m[0].slice(-60));
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'player-record', id: 'pa'}}}});
  const screens = {play: h.evaluate('playScreen()'), records: h.evaluate('recordsScreen()'), record: h.evaluate('playersScreen()')};
  assert.ok(/class="event-table"/.test(screens.play), 'the Play event table renders');
  assert.ok(/class="standing-head"/.test(screens.record) && /class="standing-cell"/.test(screens.record), 'the Regulars standing renders');
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
  const VS = h.context.window.VisionStage;
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
    return {ok:true, status:200, json: async () => replies[key] || {}}; };
  h.context.setInterval = () => 1; h.context.clearInterval = () => {};
  h.context.setTimeout = fn => { fn(); return 0; }; h.context.URLSearchParams = URLSearchParams;
  // render() reads the engine snapshot; a null one keeps it a no-op, and the tests call the block renderers directly.
  h.context.window.CornerPocketReview = {snapshot: () => null, subscribe: () => () => {}, reloadDatasets: async () => true};
  const mount = {querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, contains: () => true};
  VS.attach({mount, lang, review: h.context.window.CornerPocketReview, channels: () => [{id:'c1', channel:'examplechannel', url:'https://www.twitch.tv/examplechannel'}], vods: () => [], notice() {}});
  VS.bcReset();
  return {h, VS, snap, calls, replies, vodRow};
}
const settle = () => new Promise(resolve => setImmediate(resolve));
test('Broadcasts lists each saved channel\'s recent VODs, the job progress and every existing Source control', async () => {
  const {VS, snap, calls} = broadcastsHarness();
  VS.sourcePanelHTML(snap);                       // first render asks the server
  await settle(); await settle();
  const html = VS.sourcePanelHTML(snap);
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
  for (const kept of ['data-vs-action="pick-replay"', 'data-vs-action="live-start"', 'data-vs-action="live-stop"', 'data-vs-action="pick-dataset" data-vs-value="vod30"', 'data-vs-action="pick-dataset" data-vs-value="highlight"', 'id="source-form"'])
    assert.ok(html.includes(kept), `kept: ${kept}`);
  assert.ok(html.includes('data-vs-action="pick-dataset" data-vs-value="tw-1000000001-3600-3900"'), 'the imported VOD is a dataset chip');
});
test('Import asks for a range, shows the estimated size before confirming, and maps the other-channel refusal to 中文', async () => {
  const {h, VS, snap, calls, replies} = broadcastsHarness('zh');
  replies['/api/vods/estimate'] = {id:'tw-1000000001', vod_id:'1000000001', channel:'examplechannel', range:{start_s:0, end_s:13397, whole:true},
    estimate_bytes:5505302893, disk:{ok:true, free_bytes:52196323328, needed_bytes:8606363471, refusal:null}, already_imported:false, eta_s:442};
  VS.bcState().recent = replies['/api/vods/recent'];
  VS.act('bc-open', '1000000001', {dataset:{}});
  await settle(); await settle();
  assert.ok(calls.some(c => c.url === '/api/vods/estimate?vod=1000000001&start_s=0'), 'the default is the whole VOD');
  const html = VS.sourcePanelHTML(snap);
  assert.match(html, /examplechannel · 整场回放 · 约 5\.5 GB, 约 7 min 22 s · 52\.2 GB 可用/, 'size and time before committing');
  assert.match(html, /data-vs-action="bc-import"[^>]*>导入 · 5\.5 GB</);
  assert.match(html, /data-vs-field="bc-start"/);
  assert.match(html, /data-vs-field="bc-minutes"/);
  VS.bcState().estimate = {...replies['/api/vods/estimate'], vod_id:'1111111111'};
  VS.act('bc-import', '', {dataset:{}});
  await settle(); await settle();
  assert.equal(VS.bcState().error, '此回放属于 someoneelse。只能分析已保存的频道；请先在“来源”中添加该频道。');
  assert.match(VS.sourcePanelHTML(snap), /role="alert">此回放属于 someoneelse/);
  h.context.window.VisionStage.bcReset();
});
test('an imported VOD reads as a recorded broadcast in broadcast time, and its empty rail says why', () => {
  const {VS, snap, vodRow} = broadcastsHarness();
  const on = {...snap, dataset: vodRow.id, frame: {count:9002, t:144.03, index:4321}, eventsAnalysed: false};
  assert.equal(VS.recordedLabel(on), 'recorded broadcast of examplechannel · from 2026-09-26 · 1:00:00–1:05:00');
  assert.ok(!/live/i.test(VS.recordedLabel(on)), 'never "live"');
  const facts = VS.factsLine({...on, loading: {overlay: false, since: 0}, busy: false, live: {stale: false},
    drawn: {cloth: 1, balls: 1, persons: 2, pockets: 6, anchors: 0, events: 0, auto: {cloth: 1, balls: 1, persons: 2, pockets: 6, anchors: 0, events: 0}}});
  assert.ok(facts.includes('broadcast time 1:02:24'), `broadcast time = range start + t: ${facts}`);
  const rail = VS.railHTML({...on, events: {items: [], index: 0, reviewed: 0}, eventFilter: 'all', selection: {}, balls: {items: [], index: 0}, persons: {tracks: [], windows: [], win: ''}, focus: 'events'});
  assert.match(rail, /data-vs-empty="not-scanned">Not scanned for events — browse frames and run inference on a frozen frame\./);
  assert.equal(VS.recordedLabel(snap), '', 'vod30 keeps its own label');
  assert.equal(VS.serverText('some other sentence'), 'some other sentence');
});
test('Refresh list also re-reads the import job, so an import started in another tab shows its progress', async () => {
  const {VS, calls} = broadcastsHarness();
  VS.act('bc-refresh', '', {dataset:{}});
  await settle(); await settle();
  assert.ok(calls.some(c => c.url === '/api/vods/recent') && calls.some(c => c.url === '/api/vods/job'));
  assert.equal(VS.bcState().job.state, 'running');
});
// ---- IA C′ stage 2: hash routes. The URL names the screen; back/forward walk it; old ids map onto it.
test('routes: every tab has a hash route, a tab click pushes it, and back/forward walk the screens', async () => {
  const h = harness();
  h.evaluate('render=()=>{}');
  assert.equal(h.context.location.hash, '#/tonight', 'a cold load names its screen without adding a history entry');
  assert.deepEqual(h.visits, [['replace', '#/tonight']]);
  const expected = {records: '#/records', vision: '#/vision', players: '#/regulars', status: '#/backroom'};
  for (const [id, hash] of Object.entries(expected)) {
    await tabClick(h, id);
    assert.equal(h.evaluate('tab'), id);
    assert.equal(h.context.location.hash, hash, `${id} is ${hash}`);
  }
  assert.equal(h.visits.filter(v => v[0] === 'push').length, 4, 'each tab change is one history entry');
  await tabClick(h, 'status');
  assert.equal(h.visits.filter(v => v[0] === 'push').length, 4, 'the same tab again adds no entry');
  browserBack(h, '#/regulars');
  assert.equal(h.evaluate('tab'), 'players', 'Back returns to Regulars');
  browserBack(h, '#/setup');
  assert.equal(h.evaluate('tab'), 'tonight', 'the old Set up hash opens Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'and folds in place onto the one Tonight route');
  browserBack(h, '#/backroom');
  assert.equal(h.evaluate('tab'), 'status', 'Forward works the same way');
  browserBack(h, '#/floor');
  assert.equal(h.evaluate('tab'), 'tonight', 'the retired Floor hash opens Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'and folds into the one Tonight route');
  browserBack(h, '#/matches');
  assert.equal(h.evaluate('tab'), 'tonight', 'so does the retired Matches hash');
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
    assert.equal(h.evaluate('tab'), tab, `${hash || '(none)'} opens ${tab}`);
    assert.equal(h.context.location.hash, canonical, `${hash || '(none)'} is rewritten in place to ${canonical}`);
    assert.ok(h.visits.every(v => v[0] === 'replace'), 'loading never adds a history entry');
  }
  // a typed or old-style hash while running is the same as a click
  const h = harness();
  h.evaluate('render=()=>{}');
  browserBack(h, '#players');
  assert.equal(h.evaluate('tab'), 'players');
  assert.equal(h.context.location.hash, '#/regulars');
  // in-app links that still carry an old id (empty states, the first-night guide) resolve the same way
  assert.equal(h.evaluate("routeOf('setup')"), 'tonight', 'the retired Set up id is a legacy route, not a screen');
  assert.equal(h.evaluate("routeOf('floor')"), 'tonight', 'so is Floor');
  assert.equal(h.evaluate("routeOf('matches')"), 'tonight', 'and Matches');
  assert.equal(h.evaluate("routeOf('regulars')"), 'players');
  assert.equal(h.evaluate("routeOf('nope')"), null);
});
test('routes: a dirty or busy review vetoes back/forward too, and the URL is put back', () => {
  const h = harness({hash: '#/vision'});
  h.evaluate('render=()=>{}');
  h.context.window.CornerPocketReview = {canLeave: () => false, activate: () => false};
  browserBack(h, '#/records');
  assert.equal(h.evaluate('tab'), 'vision', 'the review keeps its screen');
  assert.equal(h.context.location.hash, '#/vision', 'the address bar says so');
  h.context.window.CornerPocketReview = {canLeave: () => true, activate: () => false};
  h.evaluate('busy=true');
  browserBack(h, '#/records');
  assert.equal(h.evaluate('tab'), 'vision', 'a write in flight also holds the screen');
  h.evaluate('busy=false');
  browserBack(h, '#/records');
  assert.equal(h.evaluate('tab'), 'records');
});
// ---- IA C′ stage 3: Records holds the history half of Matches (house standings, night log, archived events).
function recordsNight(h) {
  h.evaluate(`data.players=[{id:'pa',name:'Ann',status:'Active',rating:100},{id:'pb',name:'Bea',status:'Active',rating:900}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    data.tournament={id:'t0',name:'Tonight',format:'singles',raceTo:3,tables:2,status:'active',entrants:[E('a','pa','Ann'),E('b','pb','Bea')],
      matches:[{id:'m1',round:1,sides:['a','b'],score:[1,0],status:'live',table:1,absent:[]}]};
    data.history=[{id:'h1',name:'Last week',format:'singles',raceTo:3,status:'complete',archivedAt:'2026-09-01T00:00:00Z',entrants:[E('a1','pa','Ann'),E('b1','pb','Bea')],
      matches:[{id:'y1',round:1,sides:['a1','b1'],score:[1,3],status:'complete',result:'played',winnerId:'b1',absent:[]}]},
      {id:'h2',name:'Hidden night',hidden:true,format:'singles',raceTo:3,status:'complete',archivedAt:'2026-08-25T00:00:00Z',entrants:[E('a2','pa','Ann'),E('b2','pb','Bea')],
      matches:[{id:'y2',round:1,sides:['a2','b2'],score:[3,0],status:'complete',result:'played',winnerId:'a2',absent:[]}]}];
    data.events=[{id:'e1',action:'match_complete',revision:7,at:'2026-09-01T21:00:00Z',context:{id:'y1'}}];data.notes=[]`);
}
test('Records is a top-level tab with its own route, between the live night and Vision', async () => {
  const h = harness({hash: '#/records'});
  assert.equal(h.evaluate('tab'), 'records', 'the URL opens Records');
  assert.equal(h.context.location.hash, '#/records');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(navTabs)')).slice(0, 5), ['tonight', 'records', 'vision', 'players', 'status'], 'Records sits after the live night, before Vision');
  for (const [lang, label] of [['en', 'Records'], ['zh', '战绩档案']]) { h.evaluate(`lang='${lang}'`); assert.equal(h.evaluate("t('records')"), label); }
  h.evaluate('render=()=>{}');
  await tabClick(h, 'tonight');
  await tabClick(h, 'records');
  assert.equal(h.context.location.hash, '#/records', 'a click pushes the route');
  assert.equal(h.evaluate("routeOf('records')"), 'records');
});
test('Records is the event timeline; the house standing lives on every Regulars row', () => {
  const h = harness();
  recordsNight(h);
  for (const lang of ['en', 'zh']) {
    h.evaluate(`lang='${lang}';showHidden=false`);
    const rec = h.evaluate('recordsScreen()'), play = h.evaluate('playScreen()'), regs = h.evaluate('playersScreen()');
    const heading = h.evaluate(`t('events')`);
    assert.ok(rec.includes(`>${heading}</h2>`), `${lang}: Records is the events timeline`);
    for (const key of ['standings', 'timeline', 'history']) {
      const gone = h.evaluate(`t('${key}')`);
      assert.ok(!rec.includes(`>${gone}</h2>`) && !rec.includes(`>${gone}</h3>`), `${lang}: Records no longer carries ${gone}`);
    }
    assert.ok(!play.includes(`>${heading}</h2>`), `${lang}: Play keeps tonight only`);
    assert.ok(rec.includes('<div class="events"') && rec.includes('class="tl-item"'), `${lang}: the timeline is a list of nights`);
    assert.ok(rec.includes('data-action="results-sheet" data-id="h1"') && rec.includes('data-action="rename-archived" data-id="h1"') && rec.includes('data-action="event-hide" data-id="h1"'), `${lang}: every archive control stays`);
    assert.ok(!rec.includes('Hidden night') && rec.includes('data-action="toggle-hidden"'), `${lang}: hidden nights stay hidden behind the toggle`);
    assert.ok(regs.includes('class="standing-head"') && regs.includes('class="standing-cell"'), `${lang}: the house standing is on Regulars`);
    assert.ok(play.includes('<table class="event-table"'), `${lang}: tonight's event table stays with the Tables scoreboard`);
    assert.ok(play.includes('class="rounds"'), `${lang}: the bracket stays`);
  }
  h.evaluate('showHidden=true');
  assert.ok(h.evaluate('recordsScreen()').includes('Hidden night'), 'the toggle shows hidden nights in Records');
});
test('a Regulars standing row opens that regular, and the record behind it is read-only', async () => {
  const h = harness();
  recordsNight(h);
  h.evaluate('render=()=>{}');
  const regs = h.evaluate('playersScreen()');
  assert.ok(regs.includes('data-action="select-player" data-id="pb"'), 'each standing row lists that regular');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'select-player', id: 'pb'}}}});
  const own = h.evaluate('playersScreen()');
  assert.ok(own.includes('data-action="player-record" data-id="pb"'), 'that regular\'s own view offers the read-only record');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'player-record', id: 'pb'}}}});
  const open = h.evaluate('playersScreen()');
  assert.ok(/class="modal"[^]*Player record · Bea/.test(open), 'the record opens over Regulars');
  assert.ok(!open.includes('data-action="player-delete"') && !open.includes('player-form'), 'read-only: no edit or delete controls');
  assert.ok(open.includes('data-action="close-modal"'), 'it closes');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'close-modal'}}}});
  assert.ok(!h.evaluate('playersScreen()').includes('class="modal"'), 'closed');
  assert.equal(h.evaluate('calls.length'), 0, 'reading a record never writes');
});
test('Records empty states say what fills the timeline, in EN and 中, with no fake rows', () => {
  const h = harness();
  h.evaluate("data.players=[];data.history=[];data.events=[];data.tournament={id:'t1',name:'',format:'singles',raceTo:1,status:'registration',entrants:[],matches:[]}");
  for (const lang of ['en', 'zh']) {
    h.evaluate(`lang='${lang}'`);
    const rec = h.evaluate('recordsScreen()');
    assert.ok(rec.includes(h.evaluate(`esc(t('emptyHistory'))`)), `${lang}: emptyHistory`);
    assert.ok(!/<tr><td>\d/.test(rec) && !/<li[ >]/.test(rec), `${lang}: no rows on an empty club`);
    assert.ok(rec.includes('data-action="backfill-open"'), `${lang}: the empty timeline offers the backfill`);
    const regs = h.evaluate('playersScreen()');
    assert.ok(regs.includes(h.evaluate(`esc(t('emptyRoster'))`)), `${lang}: the standing says what fills it`);
    assert.ok(regs.includes('data-action="open-add-player"'), `${lang}: and it opens the new-regular form`);
    assert.ok(!regs.includes('standing-cell'), `${lang}: no fake standing rows`);
  }
  h.evaluate("lang='en';data.history=[{id:'h1',name:'Night',hidden:true,status:'complete',archivedAt:'2026-09-01T00:00:00Z',entrants:[],matches:[]}]");
  const hidden = h.evaluate('recordsScreen()');
  assert.ok(hidden.includes(h.evaluate(`esc(t('allHidden')).replace('{n}', 1)`)), 'an all-hidden club says so instead of "nothing here yet"');
  assert.ok(hidden.includes('data-action="toggle-hidden"'), 'and offers the toggle');
  assert.ok(!hidden.includes(h.evaluate(`esc(t('emptyHistory'))`)), 'the empty note is gone once a night exists');
});
const standingCell = (h, standing, name, col) => {
  const at = standing.indexOf(`>${name}<`);
  assert.ok(at > 0, `the standing lists ${name}`);
  const m = standing.slice(at).match(new RegExp(`data-col="${col.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"[^>]*>([^<]*)<`));
  assert.ok(m, `${name}: a ${col} cell`);
  return m[1];
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
  h.evaluate("data.players.push({id:'pz',name:'Zed',status:'Active',rating:300,joinedAt:'2026-01-05T00:00:00Z'})");
  const standing = h.evaluate('playersScreen()');
  assert.ok(standing.includes('class="entry row w-full text-left standing no-record"'), 'the row admits it holds no record');
  assert.equal(standingCell(h, standing, 'Zed', h.evaluate("t('played')")), '0');
  assert.equal(standingCell(h, standing, 'Zed', h.evaluate("t('wl')")), '\u2014');
  assert.equal(standingCell(h, standing, 'Zed', h.evaluate("t('winPct')")), '\u2014');
  assert.ok(!standing.includes('>0%<'), 'nobody reads 0% for a match they never played');
  assert.ok(standing.includes(h.evaluate("esc(t('noRecord'))")), 'and the empty cell is the — the words file holds');
  assert.ok(standing.includes(`<p class="note">${h.evaluate("esc(t('signedOnly'))")}</p>`), 'the standing says what it counts');
});
test('the timeline groups nights by month, newest first, and a night opens in place (5.3/5.4)', () => {
  const h = harness();
  h.evaluate(`render=()=>{};lang='en';showHidden=false;openEvents.clear();
    data.players=[{id:'pa',name:'Ann',status:'Active',rating:900,joinedAt:'2026-01-01T00:00:00Z'},{id:'pb',name:'Bea',status:'Active',rating:800,joinedAt:'2026-01-01T00:00:00Z'}];
    const mk=(id,name,archivedAt,hidden)=>({id,name,format:'singles',raceTo:7,tables:4,status:'complete',archivedAt,hidden:!!hidden,
      source:{kind:'vod-backfill',vodId:'1234567890',datasetId:'tw-1234567890-452-1690',startS:452,endS:1690,channel:'examplechannel',title:'Monday night',humanReviewed:true},
      signOff:{at:'2026-09-21T03:15:00Z'},
      entrants:[{id:id+'a',members:[{pid:'pa',name:'Ann'}]},{id:id+'b',members:[{pid:null,name:'Guest'}]}],
      matches:[{id:id+'m',round:1,sides:[id+'a',id+'b'],score:[3,1],status:'complete',result:'played',winnerId:id+'a',absent:[]}]});
    data.history=[mk('n1','September night','2026-09-20T12:00:00Z'),mk('n2','August night','2026-08-20T12:00:00Z'),mk('n3','July night','2026-07-20T12:00:00Z'),mk('n4','Last year','2025-12-30T12:00:00Z'),mk('h9','Hidden night','2026-06-20T12:00:00Z',true)];
    data.events=[{action:'event_backfill',createdAt:'2026-09-21T00:00:00Z',revision:9,context:{id:'n1',name:'September night',vodId:'1234567890',datasetId:'tw-1234567890-452-1690'}}]`);
  const html = h.evaluate('recordsScreen()');
  assert.deepEqual([...html.matchAll(/data-event="([^"]+)"/g)].map(m => m[1]), ['n1', 'n2', 'n3', 'n4'], 'newest first, and a hidden night stays out until asked for');
  assert.deepEqual([...html.matchAll(/class="tl-year">([^<]*)</g)].map(m => m[1]), ['2026', '2025'], 'one year head per year, not per night');
  const months = [...html.matchAll(/class="tl-month-head">([^<]*)</g)].map(m => m[1]);
  assert.equal(months.length, 4, 'one month head per month');
  assert.deepEqual(months, ['2026-09-20', '2026-08-20', '2026-07-20', '2025-12-30'].map(day => h.evaluate(`monthLabel(new Date('${day}T12:00:00Z'))`)), 'and the months read in order');
  assert.deepEqual(months, ['September', 'August', 'July', 'December'], 'in EN the month head is the English month alone (round 2, B-03)');
  assert.ok(/<h3 class="tl-year">2026<\/h3>/.test(html) && /<h3 class="tl-month-head">September<\/h3>/.test(html),
    'the year and the month are heading levels, so Records can be navigated by heading (round 2, B-13)');
  const zhMonth = h.evaluate("lang='zh';monthLabel(new Date('2026-09-20T12:00:00Z'))");
  assert.equal(zhMonth, '九月 September', 'in 中 the head still names the month in both scripts');
  h.evaluate("lang='en'");
  assert.ok(html.includes('id="tl-body-n1" hidden') && !html.includes('aria-expanded="true"'), 'a night starts folded');
  assert.ok(html.includes(h.evaluate("esc(t('signedLine').replace('{n}',1))")), 'the row counts signed results');
  assert.ok(html.includes(h.evaluate("esc(t('backfill'))")), 'and it is marked as a backfilled night');
  h.evaluate("openEvents.add('n1')");
  const open = h.evaluate('recordsScreen()');
  assert.ok(open.includes('id="tl-body-n1">') && !open.includes('id="tl-body-n1" hidden'), 'opening one night does not leave it');
  assert.ok(open.includes('aria-expanded="true"') && open.includes(h.evaluate("esc(t('tlCollapse'))")), 'the toggle flips');
  const body = open.slice(open.indexOf('id="tl-body-n1"'), open.indexOf('data-event="n2"'));
  assert.ok(body.includes(h.evaluate("esc(t('resultsSheet'))")) && body.includes(h.evaluate("esc(t('renameEvent'))")) && body.includes(h.evaluate("esc(t('hideEvent'))")), 'the sheet, the rename and the hide are in the body');
  assert.ok(!body.includes(h.evaluate("esc(t('deleteEvent'))")), 'a night with a signed result is never deletable');
  assert.ok(body.includes(`Round 1 \u00b7 Ann \u2014 Guest \u00b7 3\u20131`), 'the body lists the results as a person would read them');
  assert.ok(body.includes('href="https://www.twitch.tv/videos/1234567890"'), 'the source row links to the broadcast the night was typed from');
  assert.ok(body.includes(`<summary>${h.evaluate("esc(t('auditTrail'))")} (1)</summary>`), 'and the night carries its own audit fold');
  h.evaluate('showHidden=true');
  const all = h.evaluate('recordsScreen()');
  assert.ok(all.includes('data-event="h9"') && all.includes('tl-item is-hidden'), 'the hidden night shows up as hidden, and is still there');
});
test('the backfill is five human steps, and the page never pretends to detect anything (7.1)', () => {
  const h = harness();
  h.evaluate(`render=()=>{};lang='en';bf=bfFresh();
    bf.recent=[{channel:'examplechannel',error:null,vods:[{id:'1234567890',title:'Monday night',created_at:'2026-09-02T04:00:00Z',length_s:7200}]}]`);
  const step = n => h.evaluate(`t('bfStep').replace('{n}',${n})`);
  const pick = h.evaluate('bfScreen()');
  assert.ok(pick.includes('data-step="pick"') && pick.includes(step(1)), 'step 1: pick a broadcast');
  assert.ok(pick.includes('data-length="7200"') && pick.includes('data-title="Monday night"') && pick.includes(h.evaluate("esc(t('bfPick'))")), 'the picker carries the length, so the estimate is about this broadcast');
  assert.ok(pick.includes('data-action="bf-exit"'), 'leaving is always one click');
  h.evaluate("bfPickVod('1234567890',7200,'Monday night')");
  const verify = h.evaluate('bfScreen()');
  assert.ok(verify.includes('data-step="verify"') && verify.includes(step(2)), 'step 2: choose the range');
  assert.ok(verify.includes('id="bf-start"') && verify.includes('id="bf-length"'), 'by typing where it starts, not by trusting a machine');
  h.evaluate(`bf.startS=452;bf.endS=1690;bf.datasetId='tw-1234567890-452-1690';
    bf.estimate={estimate_bytes:1200000000,disk:{free_bytes:84000000000,needed_bytes:1500000000,ok:true},already_imported:false}`);
  const estimate = h.evaluate('bfScreen()');
  assert.ok(/<p class="bf-estimate" role="status">/.test(estimate), 'the estimate is a stated fact');
  assert.ok(estimate.includes('1.2 GB') && estimate.includes('84.0 GB'), 'the size and the free space, in real units');
  assert.ok(estimate.includes('data-action="bf-start-import"') && estimate.includes('data-action="bf-choose-other"'), 'the import is one explicit click, never automatic');
  h.evaluate("bf.step='importing';bf.job={percent:42,eta_s:300,rate_mb_s:12}");
  const importing = h.evaluate('bfScreen()');
  assert.ok(importing.includes('data-step="importing"') && importing.includes(step(3)), 'step 3: the download is visible');
  assert.ok(importing.includes('role="progressbar"') && importing.includes('aria-valuenow="42"'), 'with a real percentage rather than a spinner');
  assert.ok(importing.includes('data-action="bf-poll"'), 'and it can be left and come back to');
  h.evaluate("bf.step='dataset';bf.datasetTitle='Monday night'");
  const dataset = h.evaluate('bfScreen()');
  assert.ok(dataset.includes('data-step="dataset"') && dataset.includes(step(4)), 'step 4: which night was this?');
  assert.ok(dataset.includes(h.evaluate("esc(t('bfWhichNight'))")), 'the page asks the operator');
  assert.ok(dataset.includes('id="bf-night-name"') && dataset.includes('id="bf-night-format"') && dataset.includes('id="bf-night-race"'), 'the name, the format and the race are typed by a person');
  h.evaluate('bfStartMarking()');
  const marking = h.evaluate('bfScreen()');
  assert.ok(marking.includes('data-step="marking"'), 'step 4 continues: marking');
  assert.ok(marking.includes('id="bf-media"') && marking.includes('/media/tw-1234567890-452-1690/video'), 'the video on the page is the range that was imported');
  assert.ok(marking.includes(h.evaluate("esc(t('bfManual'))")), 'and the page says every boundary is marked by hand');
  h.evaluate('bf.clock=452;bfMarkStart();bf.clock=780;bfMarkEnd();bf.clock=1690;bfMarkStart();bf.clock=2000;bfMarkEnd()');
  const marked = h.evaluate('bfScreen()');
  assert.ok(marked.includes(h.evaluate("esc(t('bfMarked').replace('{n}',2))")), 'two matches marked');
  assert.equal([...marked.matchAll(/<li[ >]/g)].length, 2, 'one row per mark');
  assert.ok(marked.includes('data-action="bf-unmark" data-id="0"'), 'a wrong mark can be dropped');
  assert.ok(marked.includes('data-action="bf-to-review"'), 'and the next step is explicit');
  h.evaluate('bfToReview()');
  const review = h.evaluate('bfScreen()');
  assert.ok(review.includes('data-step="review"') && review.includes(step(5)), 'step 5: confirm every result');
  assert.ok(review.includes(h.evaluate("esc(t('bfHonest'))")), 'the page says nothing here was detected automatically');
  assert.ok(review.includes('id="bf-review-form"') && review.includes('data-action="bf-confirm" data-id="0"'), 'one row per marked match, each waiting for a person');
  assert.ok(review.includes(h.evaluate("esc(t('bfUnconfirmed').replace('{n}',2))")), 'and it says how many are still unconfirmed');
  assert.ok(review.includes('data-action="bf-to-marking"'), 'going back to the marks is one click');
});
test('a backfilled night cannot be committed without a person confirming every row, and the payload says so (7.0/7.5)', async () => {
  const h = harness();
  h.evaluate(`render=()=>{};lang='en';data.players=[{id:'pa',name:'Ann',status:'Active',rating:900,joinedAt:'2026-01-01T00:00:00Z'}];
    bf=bfFresh();bf.vod={id:'1234567890',channel:'examplechannel',title:'Monday night',length_s:7200};bf.datasetId='tw-1234567890-452-1690';bf.datasetTitle='Monday night';bf.startS=452;bf.endS=1690;
    bfStartMarking();bf.clock=452;bfMarkStart();bf.clock=780;bfMarkEnd();bf.clock=1690;bfMarkStart();bf.clock=2000;bfMarkEnd();bfToReview();
    bf.draft[0].sides=['Ann','Guest'];bf.draft[0].winner='Ann';bf.draft[0].score=[3,1];
    bf.draft[1].sides=['Ann','Guest'];bf.draft[1].winner='Guest';bf.draft[1].score=[2,3]`);
  h.context.sent = [];
  h.context.fetch = async (url, options) => { h.context.sent.push({url, payload: JSON.parse(options.body)}); return {status: 200, ok: true, json: async () => h.evaluate("Object.assign({},data,{revision:data.revision+1,history:[{id:'h9',name:'Monday night',source:{datasetId:'tw-1234567890-452-1690'}}]})")}; };
  await h.evaluate('bfCommit()');
  assert.equal(h.context.sent.length, 0, 'nothing is written while a row is unconfirmed');
  assert.equal(h.evaluate('bf.notice'), h.evaluate("t('bfUnconfirmed').replace('{n}',2)"));
  assert.ok(commitDisabled(h.evaluate('bfScreen()')), 'and the commit control is disabled, not just discouraged');
  h.evaluate('bfConfirm(0);bfConfirm(1)');
  assert.equal(h.evaluate('bf.draft.filter(m=>!m.confirmed).length'), 0);
  assert.ok(!commitDisabled(h.evaluate('bfScreen()')), 'confirmed rows enable the commit');
  const revision = h.evaluate('data.revision');
  await h.evaluate('bfCommit()');
  assert.equal(h.context.sent.length, 1, 'one confirmed night, one write');
  const sent = h.context.sent[0];
  assert.equal(sent.url, '/api/operations');
  assert.equal(sent.payload.action, 'event_backfill');
  assert.equal(sent.payload.revision, revision, 'the write carries the revision it was read at');
  assert.equal(h.evaluate('data.revision'), revision + 1, 'and the console adopts the state the server answered with');
  assert.equal(sent.payload.source.kind, 'vod-backfill');
  assert.equal(sent.payload.source.humanReviewed, true, 'the server enforces this mark; the disabled button is not enough');
  assert.equal(sent.payload.source.datasetId, 'tw-1234567890-452-1690');
  assert.deepEqual(sent.payload.event.entrants, [{pid: 'pa', name: 'Ann'}, {name: 'Guest'}], 'a typed regular is written as their roster row, a guest as a name');
  assert.deepEqual(sent.payload.event.matches, [
    {round: 1, sides: ['Ann', 'Guest'], score: [3, 1], winner: 'Ann', result: 'played', clip: [452, 780]},
    {round: 1, sides: ['Ann', 'Guest'], score: [2, 3], winner: 'Guest', result: 'played', clip: [1690, 2000]}
  ], 'the clip boundaries the operator marked, and no invented result');
  assert.equal(h.evaluate('bf.step'), 'done', 'the night is written and the flow ends');
  assert.ok(h.evaluate('bfScreen()').includes('data-action="bf-open-timeline"'));
  // the same range cannot be written twice: the server refuses and the console offers the night instead
  h.evaluate(`bf=bfFresh();bf.vod={id:'1234567890',channel:'examplechannel',title:'Monday night',length_s:7200};bf.datasetId='tw-1234567890-452-1690';bf.datasetTitle='Monday night';bf.startS=452;bf.endS=1690;
    bfStartMarking();bf.clock=452;bfMarkStart();bf.clock=780;bfMarkEnd();bfToReview();bf.draft[0].sides=['Ann','Guest'];bf.draft[0].winner='Ann';bf.draft[0].score=[3,1];bfConfirm(0)`);
  h.context.fetch = async () => ({status: 409, ok: false, json: async () => ({error: 'A night already covers this broadcast and range (tw-1234567890-452-1690)'})});
  await h.evaluate('bfCommit()');
  assert.equal(h.evaluate('bf.notice'), h.evaluate("t('bfSameVod')"));
  assert.ok(h.evaluate('bfScreen()').includes('data-action="bf-open-night"'), 'a 409 offers the night that already exists instead of overwriting it');
  assert.equal(h.evaluate('bf.draft.length'), 1, 'and it keeps the marks');
});
test('a range that is already downloaded is reused, and a typed regular counts towards their standing (7.3/6.1)', async () => {
  const h = harness();
  h.evaluate(`render=()=>{};lang='en';
    data.players=[{id:'pa',name:'Ann',status:'Active',rating:900,joinedAt:'2026-01-01T00:00:00Z'},{id:'pb',name:'Bea',status:'Active',rating:800,joinedAt:'2026-01-01T00:00:00Z'}];
    data.history=[{id:'h1',name:'Monday night',format:'singles',raceTo:7,tables:4,status:'complete',archivedAt:'2026-09-01T12:00:00Z',
      source:{kind:'vod-backfill',vodId:'1234567890',datasetId:'tw-1234567890-452-1690',startS:452,endS:1690,channel:'examplechannel',title:'Monday night',humanReviewed:true},
      signOff:{at:'2026-09-02T03:15:00Z'},
      entrants:[{id:'e1',members:[{pid:'pa',name:'Ann'}]},{id:'e2',members:[{pid:null,name:'Rico'}]}],
      matches:[{id:'m1',round:1,sides:['e1','e2'],score:[3,1],status:'complete',result:'played',winnerId:'e1',absent:[]}]}];
    bf=bfFresh();bf.recent=[{channel:'examplechannel',error:null,vods:[{id:'1234567890',title:'Monday night',created_at:'2026-09-02T04:00:00Z',length_s:7200,imported:['tw-1234567890-452-1690']}]}]`);
  const pick = h.evaluate('bfScreen()');
  assert.ok(pick.includes(h.evaluate("esc(t('bfReuse'))")), 'the picker says this range is already downloaded');
  h.evaluate("bfPickVod('1234567890',7200,'Monday night');bf.estimate={estimate_bytes:1200000000,disk:{free_bytes:84000000000,needed_bytes:1500000000,ok:true},already_imported:true}");
  const verify = h.evaluate('bfScreen()');
  assert.ok(verify.includes('data-action="bf-use-imported"') && verify.includes(h.evaluate("esc(t('bfReuse'))")), 'and offers the range it holds instead of downloading it again');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'bf-use-imported'}}}});
  assert.equal(h.evaluate('bf.step'), 'dataset', 'reusing it goes straight to naming the night');
  assert.equal(h.evaluate('bfUseImported() || bf.notice'), h.evaluate("t('bfReuse')"), 'and the reuse is said out loud, in the operator’s words');
  assert.equal(h.evaluate(`JSON.stringify(bfEntrants(['Ann','Bea','Rico']))`),
    JSON.stringify([{pid: 'pa', name: 'Ann'}, {pid: 'pb', name: 'Bea'}, {name: 'Rico'}]), 'a name the roster holds is sent as that regular');
  assert.ok(h.evaluate("bfPersonBadge('Ann')").includes(h.evaluate("esc(t('member'))")), 'a regular is marked as one at the point of typing');
  assert.ok(h.evaluate("bfPersonBadge('Rico')").includes(h.evaluate("esc(t('guest'))")), 'a guest is marked as counting towards nobody');
  assert.equal(h.evaluate("bfPlayerFor('\uff21\uff4e\uff4e')?.id"), 'pa', 'the name is folded the way the search folds it, so full-width typing still finds the regular');
  h.evaluate("bf.step='review';bf.draft=[{start:452,end:780,sides:['Ann','Rico'],winner:'Ann',score:[3,1],confirmed:true}]");
  const review = h.evaluate('bfScreen()');
  assert.ok(review.includes(h.evaluate("esc(t('bfLinkedCount').replace('{n}',1).replace('{m}',2))")), 'the review says exactly how many of the names are regulars');
  assert.ok(review.includes('badge bf-linked'), 'and every name carries its badge');
  const standing = h.evaluate('playersScreen()');
  assert.equal(standingCell(h, standing, 'Ann', h.evaluate("t('played')")), '1', 'the backfilled night counts towards the regular it names');
  assert.equal(standingCell(h, standing, 'Ann', h.evaluate("t('wl')")), `1\u20130`);
  assert.equal(standingCell(h, standing, 'Ann', h.evaluate("t('winPct')")), '100%');
  assert.ok(!/>Rico</.test(standing), 'and the guest counts towards nobody');
});
// ---- IA C′ stage 4: the Tonight tab. A phase strip (Register · Rack · Play · Close), every phase always
// reachable, the default is the night's own phase, and Register holds everything the night needs before the draw.
function tonightNight(h, state) {
  h.evaluate(`data.players=[{id:'pa',name:'Ann',status:'Active',rating:100},{id:'pb',name:'Bea',status:'Active',rating:900}];
    var E=(id,pid,name,absent=false)=>({id,absent,members:[{pid,name}]}); // var: test 4 applies this fixture twice in one vm context
    data.tournament={id:'t0',name:'Friday',format:'singles',raceTo:3,tables:2,status:'registration',entrants:[E('a','pa','Ann'),E('b','pb','Bea'),E('g',null,'Walk-in Wu',true)],matches:[]};
    data.history=[];data.events=[];data.notes=[]`);
  if (state === 'drawn') h.evaluate(`data.tournament.status='active';data.tournament.entrants[2].absent=false;data.tournament.matches=[
      {id:'m1',round:1,sides:['a',null],score:[0,0],status:'complete',result:'bye',winnerId:'a',absent:[]},
      {id:'m2',round:1,sides:['b','g'],score:[0,0],status:'scheduled',table:null,absent:[]},
      {id:'m3',round:2,sides:['a',null],score:[0,0],status:'pending',table:null,absent:[],sources:['m1','m2']}]`);
  if (state === 'done') h.evaluate(`data.tournament.status='complete';data.tournament.matches=[
      {id:'m1',round:1,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',absent:[]}]`);
}
test('Tonight is one tab whose state follows the night: an empty venue, entrants, a live event, all signed', () => {
  for (const [state, gate, venue] of [[null, 'registration', 'registration'], ['drawn', 'active', 'active'], ['done', 'complete', 'complete']]) {
    const h = harness();
    tonightNight(h, state);
    assert.equal(h.evaluate('comp()'), gate, `${state || 'registration'} → the server gate is ${gate}`);
    assert.equal(h.evaluate('tonightState()'), venue, `${state || 'registration'} → the venue is ${venue}`);
  }
  // no entrants and no draw is the idle venue: the server is still open for registration
  const idle = harness();
  idle.evaluate("data.players=[];data.tournament={id:'t0',name:'',format:'singles',raceTo:3,tables:2,status:'registration',entrants:[],matches:[]}");
  assert.equal(idle.evaluate('comp()'), 'registration', 'the server gate still says registration');
  assert.equal(idle.evaluate('tonightState()'), 'idle', 'but with nobody signed up the venue is idle');
  assert.equal(idle.evaluate('liveComp()'), false, 'and no event is live');
  const h = harness({hash: '#/tonight'});
  assert.equal(h.evaluate('tab'), 'tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'the Tonight route carries no phase');
  tonightNight(h, 'drawn');
  h.evaluate('syncRoute(false)');
  assert.equal(h.context.location.hash, '#/tonight', 'a night in progress never rewrites the URL');
  assert.ok(h.visits.every(v => v[0] === 'replace'), 'a data-driven change never pushes history');
  assert.equal(JSON.parse(h.evaluate('JSON.stringify(navTabs)'))[0], 'tonight', 'Tonight is the first tab');
  for (const [lang, label] of [['en', 'Tonight'], ['zh', '今晚']]) { h.evaluate(`lang='${lang}'`); assert.equal(h.evaluate("navLabel('tonight')"), label); }
});
test('the step is a read-only scene, and no second-level menu exists anywhere in the shell', async () => {
  const h = harness({hash: '#/tonight/play'});
  tonightNight(h, 'drawn');
  h.evaluate('render=()=>{}');
  assert.equal(h.evaluate("routeOf('#/tonight/play')"), 'tonight', 'the old phase route resolves to Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'and the URL folds in place');
  for (const lang of ['en', 'zh']) {
    h.evaluate(`lang='${lang}'`);
    const scene = h.evaluate('scene()');
    assert.ok(!/<button/.test(scene), `${lang}: nothing in the scene is clickable`);
    assert.ok(!/data-phase|data-play|data-more/.test(scene), `${lang}: no phase, play or more hooks in the scene`);
    assert.equal((scene.match(/aria-current/g) || []).length, 1, `${lang}: exactly one current node`);
    assert.ok(/role="status"/.test(scene) && !/<nav/.test(scene), `${lang}: the scene is a status report, not a navigation landmark`);
    assert.ok(scene.includes(h.evaluate("esc(t('scenePlay'))")), `${lang}: a drawn night with a signed match reads Playing`);
    for (const key of ['sceneRegister', 'sceneRack', 'scenePlay', 'sceneClose']) assert.ok(source.includes(`${key}:`), `${lang}: ${key} exists`);
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
test('Register holds the night, random pairing, the desk, entrants with attendance, guests tonight and Rack', () => {
  const h = harness();
  tonightNight(h, null);
  assert.equal(h.evaluate('tonightState()'), 'registration', 'three entrants and no draw is the registration venue');
  for (const lang of ['en', 'zh']) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('tonightScreen()');
    assert.ok(html.includes('id="settings-form"') && html.includes('id="entrant-form"') && html.includes('class="desk-search"'), `${lang}: settings, desk and desk search`);
    assert.ok(html.includes('data-action="entrant-absence"') && html.includes('data-action="entrant-remove"'), `${lang}: attendance and remove per entrant`);
    assert.ok(html.includes('data-action="tournament-start"'), `${lang}: Rack the night is on Register`);
    assert.ok(html.includes('data-action="promote" data-name="Walk-in Wu"'), `${lang}: guests tonight moved here, with Add to regulars`);
    assert.ok(html.includes('data-tab="players"'), `${lang}: guests tonight links to Regulars`);
    assert.ok(!html.includes('class="end-night"'), `${lang}: archive and delete are not on Register (they are Close)`);
    assert.ok(html.includes('class="first-run"'), `${lang}: an undrawn night shows the first-night guide`);
  }
  h.evaluate("data.tournament.format='doubles'");
  assert.ok(h.evaluate('tonightScreen()').includes('class="pairing"'), 'doubles adds random pairing');
  assert.ok(!h.evaluate('playersScreen()').includes('data-action="promote"'), 'Regulars no longer carries guests tonight');
});
test('who is here is a fact on the desk, and the night is drawn and started from the same place', async () => {
  const h = harness();
  tonightNight(h, null);
  for (const [lang, notHere] of [['en', 'Not here'], ['zh', '未到场']]) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('tonightScreen()');
    assert.ok(html.includes('data-action="tournament-start"'), `${lang}: the start-the-event button`);
    assert.ok(html.includes(h.evaluate("esc(t('rackHint'))")), `${lang}: how the draw is made`);
    assert.ok(/Walk-in Wu[^]*?Not here|Walk-in Wu[^]*?未到场/.test(html) && html.includes(notHere), `${lang}: an absent entrant is named before the draw`);
    assert.ok(html.includes(h.evaluate("esc(t('rackAbsentNote'))")), `${lang}: it says an absent entrant's match is held`);
    assert.ok(/data-action="entrant-absence" data-id="g" data-absent="false"/.test(html), `${lang}: attendance is a button on the entrant, not a screen of its own`);
  }
  h.evaluate('render=()=>{}');
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  await click({action: 'entrant-absence', id: 'g', absent: 'false'});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls.map(c=>c.name))')), ['entrant_absence'], 'marking someone present writes that one fact');
  h.evaluate('calls.length=0');
  await click({action: 'tournament-start'});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls.map(c=>c.name))')), ['tournament_start'], 'starting the event is one write');
  assert.equal(h.evaluate('tab'), 'tonight', 'and the night never leaves Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'the URL does not move to a phase');
  // after the draw the start button is gone, the whole night form retires, and the tables carry it
  tonightNight(h, 'drawn');
  const drawn = h.evaluate('tonightScreen()');
  assert.ok(!drawn.includes('data-action="tournament-start"'), 'a drawn night cannot be drawn twice');
  assert.ok(!drawn.includes('id="settings-form"'), 'the start-the-night form retires once the event is live');
  assert.ok(drawn.includes('id="rename-form"'), 'but the night can still be renamed');
  assert.ok(drawn.includes('data-table="'), 'the tables are the screen, live or not');
});
test('old phase routes fold into the one Tonight route, in place', () => {
  for (const hash of ['#/tonight/rack', '#/tonight/close', '#/tonight/bogus', '#/tonight/register', '#/tonight/play']) {
    const h = harness({hash});
    h.evaluate('syncRoute(false)');
    assert.equal(h.evaluate('tab'), 'tonight', hash);
    assert.equal(h.context.location.hash, '#/tonight', `${hash} folds to #/tonight`);
    assert.ok(h.visits.every(v => v[0] === 'replace'), `${hash} never pushes history`);
  }
});

test('every tab id resolves to a screen, so no tab can blank the console (stage 6)', () => {
  const h = harness();
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(navTabs.filter(id=>typeof screens[id]!=="function"))')), [], 'every tab id has a screen');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(Object.keys(screens))')), ['tonight', 'records', 'vision', 'players', 'status'], 'and nothing else is a screen: the retired ones are gone, not hidden');
  assert.equal(h.evaluate('typeof screens.floor'), 'undefined', 'the Floor screen is retired');
  assert.equal(h.evaluate('typeof screens.matches'), 'undefined', 'and so is Matches');
});
test('Close is the night\u2019s end: the results sheet, second chance, archive and delete (stage 6)', async () => {
  const h = harness();
  h.evaluate(`data.notes=[];data.players=[{id:'pa',name:'Ada',status:'Active',rating:1},{id:'pb',name:'Bo',status:'Active',rating:2}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    data.tournament={id:'t0',name:'Tonight',format:'singles',tables:1,raceTo:3,status:'registration',entrants:[E('a','pa','Ada'),E('b','pb','Bo')],matches:[]};
    data.history=[];tab='tonight';`);
  h.evaluate('render=()=>{}');
  const click = dataset => h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset}}});
  const close = () => h.evaluate('wrapScreen()');
  assert.ok(!close().includes('data-action="results-sheet"'), 'no sheet before the draw');
  assert.ok(close().includes(h.evaluate("esc(t('closeTitle'))")), 'the wrap-up card is there from the start');
  assert.ok(!/data-phase=/.test(close()), 'and it has no phase button left to point anywhere');
  h.evaluate("data.tournament.matches=[{id:'q1',round:1,sides:['a','b'],score:[0,0],status:'scheduled',absent:[]}]");
  const drawn = close();
  assert.ok(drawn.includes('data-action="results-sheet" data-id="t0"'), 'tonight has a sheet once drawn');
  assert.ok(drawn.includes('data-action="new-event"') && drawn.includes('data-action="event-delete" data-id="t0"'), 'Archive & new / Delete event stay in Close');
  assert.ok(drawn.indexOf('data-action="results-sheet"') < drawn.indexOf('data-action="new-event"'), 'the sheet comes first: Results sheet, second chance, archive / delete');
  h.evaluate("data.tournament.revival=null");
  await click({action: 'results-sheet', id: 't0'});
  assert.equal(h.evaluate('sheetId'), 't0', 'the click opens the sheet');
  assert.ok(close().includes('class="stack results-sheet"'), 'the sheet replaces the Close view');
  assert.ok(h.evaluate('tonightScreen()').includes('class="stack results-sheet"'), 'the sheet survives the tonight render, not only a direct call');
  await click({action: 'sheet-back'});
  assert.ok(!close().includes('class="stack results-sheet"'), 'back returns to Close');
});

test('\u2264750px: the fixed bottom bar is the same five destinations, with no More behind it (stage 7)', () => {
  const h = harness();
  const shell = fs.readFileSync(path.join(__dirname, '../annotator/ops.html'), 'utf8');
  assert.ok(shell.includes('<nav id="tabbar"'), 'the bottom bar is part of the shell');
  const bar = () => h.evaluate('tabbarHTML()');
  for (const id of ['tonight', 'records', 'vision', 'players', 'status']) assert.ok(bar().includes(`data-tab="${id}"`), `${id} is a bar slot`);
  assert.equal((bar().match(/class="tabbar-slot"/g) || []).length, 5, 'all five destinations are slots — four equal widths, none behind More');
  assert.equal((bar().match(/aria-current="page"/g) || []).length, 1, 'the bar marks exactly the tab you are on');
  assert.ok(!/data-more|tabbar-more/.test(bar()), 'no More button and no panel behind it');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(primaryNav())')), JSON.parse(h.evaluate('JSON.stringify(navTabs)')), 'the bar and the top nav render the same list');
  h.evaluate("tab='players'");
  assert.equal((bar().match(/aria-current="page"/g) || []).length, 1, 'Regulars is the current slot on the bar itself');
  assert.ok(bar().includes('data-tab="players"'), 'the Regulars slot is the current one');
  h.evaluate("tab='tonight'");
  assert.ok(!/data-tab="(floor|matches)"/.test(bar()), 'the bar never grows the retired tabs');
});
test('the bottom bar survives Vision, which is how Vision gets an exit, and every vision surface clears it (stage 7)', () => {
  const h = harness();
  assert.ok(h.evaluate('tabbarHTML()').includes('data-tab="vision"'), 'Vision is a bar slot');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('[data-tab=vision] #tabbar{display:flex}'), 'the vision rule that hides the top nav row does not hide the bar');
  assert.ok(css.includes('env(safe-area-inset-bottom)'), 'the bar and its padding respect the safe area');
  assert.ok(css.includes('--tabbar-h'), 'the bar height is one token the vision surfaces are offset by');
  for (const sel of ['.vs-sheettabs{bottom:var(--tabbar-h)', '.vs-strip{bottom:calc(var(--tabbar-h)']) {
    assert.ok(css.includes(sel), `${sel} sits above the bar`);
  }
  assert.ok(css.includes('@media print{#ops-shell #tabbar{display:none!important}}'), 'the bar never prints');
});

test('stage 8: Floor and Matches are not screens any more, and every old way in folds into Tonight (stage 8)', async () => {
  const h = harness({hash: '#/floor'});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(navTabs)')), ['tonight', 'records', 'vision', 'players', 'status'], 'the row is Tonight, Records, Vision, Regulars, Back room');
  assert.equal(h.evaluate('tab'), 'tonight', 'the retired Floor hash opens Tonight');
  assert.equal(h.context.location.hash, '#/tonight', 'and folds there in place');
  assert.ok(h.visits.every(v => v[0] === 'replace'), 'opening an old hash never adds a history entry');
  for (const id of ['floor', 'matches', 'setup']) {
    assert.equal(h.evaluate(`routeOf('${id}')`), 'tonight', `the retired ${id} id is a legacy route, not a screen`);
  }
  assert.equal(h.evaluate('routeOf("records")'), 'records', 'a live route is not a legacy one');
  h.evaluate('render=()=>{}');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'floor'}}}});
  assert.equal(h.evaluate('tab'), 'tonight', 'the retired floor action leaves the screen where it is');
  for (const screen of ['tonightScreen', 'recordsScreen', 'playersScreen', 'statusScreen']) {
    assert.ok(!/data-tab="(floor|matches|setup)"/.test(h.evaluate(`${screen}()`)), `${screen} offers no retired tab`);
  }
});

// ---- IA C′ stage 9: one bar, five destinations, a data-driven Tonight, and the shot timer's one name.
test('the bar is one row: the shot timer first, the five destinations, the tools; no hall and no strip (stage 9 / owner §13.1)', () => {
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
  assert.equal(html.indexOf('class="clockbar"'), -1, 'the second timer in .tools is deleted too');
  assert.equal((html.match(/data-clock-host/g) || []).length, 1, 'one timer slot in the whole shell');
  assert.equal((html.match(/<header>/g) || []).length, 1, 'one header');
  // The slot is the bar's first child, so the large timer is the first thing in the top bar.
  assert.ok(bar.includes('<div class="timer-slot" role="group" aria-label="Shot timer / 击球计时" data-clock-host></div>'),
    'the slot is a named group with one host, empty until ops.js paints it');
  assert.ok(bar.indexOf('class="timer-slot"') < bar.indexOf('<nav id="nav"'), 'the timer comes first');
  assert.ok(bar.indexOf('<nav id="nav"') < bar.indexOf('<div class="tools"'), 'then the destinations');
  assert.equal((bar.match(/<div class="tools">/g) || []).length, 1, 'and one tools row, unchanged');
  assert.ok(bar.includes('<span id="connection" class="badge" hidden>'), 'the connection badge still starts hidden and empty');
  assert.ok(bar.includes('data-lang="en"') && bar.includes('data-lang="zh"') && bar.includes('data-theme-group'), 'the language and theme chips are untouched');
  assert.ok(css.includes('#ops-shell .bar > nav{flex:0 1 auto;min-width:0;padding:0}'),
    'the nav keeps its own size: a bar that shrinks it wraps the destinations onto a second row (measured 96 px against 44)');
  assert.ok(css.includes('#ops-shell .bar{flex-wrap:nowrap}'), 'the bar itself is one row');
  assert.ok(/#ops-shell \.bar > \.tools\{flex:0 1 auto;min-width:0;flex-wrap:wrap\}/.test(css), 'the tools are the part that folds');
  assert.ok(!/\.brand/.test(css), 'the brand styles went with the brand block');
  const h = harness();
  assert.equal(h.evaluate('primaryNav()').length, 5, 'the one bar renders five destinations');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(primaryNav())')), JSON.parse(h.evaluate('JSON.stringify(navTabs)')), 'and Back room is one of them (always, not conditionally)');
  const destinations = JSON.parse(h.evaluate('JSON.stringify(primaryNav().map((k,i)=>ballColor(i+2)))'));
  assert.deepEqual(destinations, ['#2f6fd0', '#c8382f', '#e885ad', '#e07a29', '#2f8f4e'],
    'the five destinations draw balls 2 (blue) through 6 (green): the timer is ball 1');
  assert.equal(h.evaluate('ballHTML(1)').includes('data-stripe'), false, 'ball 1 is a solid');
  for (const [lang, back] of [['en', 'Back room'], ['zh', '后台']]) {
    h.evaluate(`lang='${lang}'`);
    assert.ok(h.evaluate('render').toString().includes('primaryNav()'), `${lang}: render paints the bar from the one list`);
    assert.ok(h.evaluate('render').toString().includes("dataset.lang"), `${lang}: render publishes the language it painted in`);
    assert.equal(h.evaluate("navLabel('status')"), back, `${lang}: the fifth destination keeps its name`);
  }
});
// ---- owner round 2, items 3-7: the palette, the material balls and the always-on timer slot.
test('one palette keyed by ball number colours every ball: 1-8 the owner list, 9-15 the same hues striped, 16+ wrapping', () => {
  const h = harness();
  const palette = h.evaluate('JSON.stringify(ballPalette)');
  assert.equal(palette, JSON.stringify(['#f2c14e','#2f6fd0','#c8382f','#e885ad','#e07a29','#2f8f4e','#8a5a2b','#1b1b1b',
    '#f2c14e','#2f6fd0','#c8382f','#e885ad','#e07a29','#2f8f4e','#8a5a2b']),
    '1 yellow, 2 blue, 3 red, 4 pink, 5 orange, 6 green, 7 brown, 8 black; 9-15 the same seven hues');
  for (let n = 1; n <= 8; n++) {
    assert.equal(h.evaluate('ballNumber(' + n + ')'), n, `ball ${n} keeps its number`);
    assert.equal(h.evaluate('ballStripe(' + n + ')'), 0, `ball ${n} is a solid`);
    assert.ok(h.evaluate('ballHTML(' + n + ')').includes('--ball-c:' + h.evaluate('ballColor(' + n + ')')), `ball ${n} carries its own hue`);
  }
  for (let n = 9; n <= 15; n++) {
    assert.equal(h.evaluate('ballStripe(' + n + ')'), 1, `ball ${n} is a stripe`);
    assert.equal(h.evaluate('ballColor(' + n + ')'), h.evaluate('ballColor(' + (n - 8) + ')'), `ball ${n} is the same hue as ball ${n - 8}`);
    assert.ok(h.evaluate('ballHTML(' + n + ')').includes('data-stripe="1"'), `ball ${n} is drawn as a stripe`);
  }
  // Past a full rack the number wraps, the way entrant chips keep counting.
  assert.equal(h.evaluate('ballNumber(16)'), 1, '16 wraps to 1');
  assert.equal(h.evaluate('ballNumber(23)'), 8, '23 wraps to 8');
  assert.equal(h.evaluate('ballNumber(30)'), 15, '30 wraps to 15');
  assert.equal(h.evaluate('ballColor(16)'), '#f2c14e', 'and 16 is yellow again');
  assert.ok(h.evaluate('ballHTML(16)').includes('>1<'), 'the plate shows the wrapped number, not 16');
  // The plate is the number, inside the sphere; the hue is the only inline style.
  assert.equal(h.evaluate('ballHTML(3)'), '<span class="ball" style="--ball-c:#c8382f"><i>3</i></span>', 'one helper, one shape');
  // Every place a ball is drawn uses that helper.
  const entrants = h.evaluate("data.tournament={id:'t',name:'',format:'singles',raceTo:7,tables:1,status:'registration',entrants:[{id:'e1',members:[{name:'A'}]},{id:'e2',members:[{name:'B'}]}],matches:[]};data.players=[];entrantsCard()");
  assert.ok(entrants.includes('--ball-c:#f2c14e') && entrants.includes('--ball-c:#2f6fd0'), 'entrant chips draw balls 1 and 2 from the palette');
  assert.ok(!entrants.includes('<span class="ball"><i>'), 'and no longer a flat uncoloured disc');
  assert.ok(h.evaluate('ballHTML(6)').includes('--ball-c:#2f8f4e'), 'ball 6 is the green one the owner asked for');
});
test('the timer slot renders and works in all four venue states, and nothing in it reads comp() (owner items 1 and 5)', async () => {
  // comp() is the tournament status; the live vocabulary is idle through complete. The
  // brief and §13.1 name the last one "closed" — the same state, the repo's spelling.
  const states = [['registration', 'idle'], ['registration', 'registration'], ['active', 'active'], ['complete', 'closed']];
  for (const [status, label] of states) {
    const h = harness();
    h.evaluate(`data.tournament={id:'t',name:'',format:'singles',raceTo:7,tables:4,status:'${status}',entrants:[{id:'e1',members:[{name:'A'}]}],matches:[]};data.players=[]`);
    assert.equal(h.evaluate('comp()'), status, `${label}: the venue is in that state`);
    assert.equal(h.evaluate('tonightState() !== undefined'), true, `${label}: and Tonight has a state of its own`);
    const markup = h.evaluate('timerHTML()');
    assert.ok(h.evaluate('clockHTML()').includes('data-clock'), `${label}: the clock is in the slot`);
    assert.ok(h.evaluate('clockHTML()').includes('data-action="clock-toggle"'), `${label}: the start/pause control is there`);
    assert.ok(h.evaluate('clockHTML()').includes('data-action="clock-reset"'), `${label}: so is reset`);
    assert.ok(h.evaluate('clockHTML()').includes('data-action="clock-set" data-value="20"'), `${label}: and the four presets`);
    assert.ok(markup.includes('data-progress'), `${label}: with the elapsed bar`);
    assert.ok(!/kicker/.test(markup), `${label}: no .kicker second line in the slot`);
    assert.equal((markup.match(/class="ball[^"]*"/g) || []).length, 1, `${label}: one ball, the 1`);
    assert.ok(markup.includes('--ball-c:#f2c14e'), `${label}: and it is the yellow 1`);
    // The controls work: toggle starts and pauses, reset clears the deadline, a preset
    // changes the duration through the server before the shell adopts it.
    // A DOM just real enough to render: the shell the language is published on, the
    // elements render paints, and the timer slot, which is the mount this work is about.
    const slot = {innerHTML: ''};
    const node = () => ({innerHTML: '', className: '', textContent: '', dataset: {}, style: {}, hidden: false,
      classList: {toggle() {}, add() {}, remove() {}}, setAttribute() {}, getAttribute: () => null,
      querySelector: () => null, querySelectorAll: () => [], appendChild() {}, addEventListener() {}});
    const shell = node(), nav = node(), tabbar = node(), main = node();
    shell.querySelector = selector => (selector === '.timer-slot' ? slot : null);
    h.context.document.querySelector = selector => ({'#ops-shell': shell, '#ops-shell .timer-slot': slot, '#nav': nav, '#tabbar': tabbar, '#main': main}[selector] || null);
    h.context.document.body = node();
    h.evaluate('render=()=>{}');
    // The shell's click listener finds its button with closest('button,.modal-backdrop').
    const act = action => h.handlers.click({target: {closest: selector => (selector === 'button,.modal-backdrop' ? {dataset: {action}, classList: {contains: () => false}} : null)}});
    h.evaluate('timer={duration:30,remaining:30,deadline:null}');
    act('clock-toggle');
    assert.ok(h.evaluate('timer.deadline') > 0, `${label}: Start sets a deadline`);
    const running = h.evaluate('timerHTML()');
    assert.ok(/class="ball running"/.test(running), `${label}: the ball says the clock is running`);
    assert.ok(running.includes('Pause') || running.includes('暂停'), `${label}: and the control offers Pause`);
    act('clock-toggle');
    assert.equal(h.evaluate('timer.deadline'), null, `${label}: Pause clears it`);
    h.evaluate('timer={duration:30,remaining:4,deadline:null}');
    act('clock-reset');
    assert.equal(h.evaluate('timer.remaining'), 30, `${label}: Reset goes back to the duration`);
    await act('clock-set');
    assert.ok(h.evaluate('timer.duration') === 30, `${label}: a preset with no data-value keeps the duration it had`);
  }
  const h = harness();
  h.context.document.querySelector = () => ({innerHTML: '', classList: {toggle() {}}, dataset: {}, style: {}, setAttribute() {}, textContent: ''});
  h.evaluate('render=()=>{}');
  await h.handlers.click({target: {closest: selector => (selector === 'button,.modal-backdrop' ? {dataset: {action: 'clock-set', value: '45'}, classList: {contains: () => false}} : null)}});
  assert.equal(h.evaluate('timer.duration'), 45, 'a preset sets the duration the server accepted');
  assert.equal(h.evaluate('timer.remaining'), 45, 'and the clock starts the new duration');
  // Nothing in the slot can be gated on the venue state, and the slot is painted from the
  // one helper: once at boot and once on every render.
  assert.ok(!/function clockHTML\([^)]*comp/.test(source), 'clockHTML() reads no venue state');
  assert.ok(!/function timerHTML\([^)]*comp/.test(source), 'and neither does timerHTML()');
  assert.ok(!/function timerHTML\(\)\{[^}]*comp\(/.test(source), 'nothing inside timerHTML() asks the venue state either');
  assert.equal((source.match(/paintClockSlot\(\)/g) || []).length, 3, 'one definition, one boot paint and one render paint, from one helper');
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
  await h.evaluate('reload()');
  assert.equal(badge().hidden, true, 'a healthy connection says nothing at all');
  assert.equal(badge().textContent, '', 'and the badge is empty, not a revision');
  assert.ok(!source.includes("$('#connection').textContent=`"), 'no render path paints a slogan into the badge');
  assert.ok(!source.includes("t('connected')") && !source.includes('LOCAL · SAVED'), 'the LOCAL · SAVED copy is gone from the shell');
  h.context.fetch = async () => ({ok: false, status: 503, json: async () => ({})});
  await h.evaluate('reload()');
  assert.equal(badge().hidden, false, 'a failed load brings the badge back');
  for (const [lang, text] of [['en', 'OFFLINE · edits will not save'], ['zh', '离线 · 改动不会保存']]) {
    h.evaluate(`lang='${lang}'`);
    assert.equal(h.evaluate("t('connectionLost')"), text, `${lang}: the badge has honest copy`);
  }
  h.evaluate("lang='en'");
  assert.equal(badge().textContent, 'OFFLINE · edits will not save', 'and the failure writes exactly that');
  // The revision still exists where a maintainer can find it: one line on the Back room page.
  assert.ok(source.includes("<p class=\"muted last-write\">"), 'the Back room carries the last write');
  assert.ok(h.evaluate('statusScreen()').includes(h.evaluate("esc(t('lastWrite').replace('{n}',String(data.revision)))")), 'and prints the revision without inventing a timestamp');
});
test('the four venue states decide which cards exist on Tonight, and a state change never writes history (stage 9)', () => {
  const idle = harness();
  idle.evaluate("data.players=[];data.tournament={id:'t0',name:'',format:'singles',raceTo:7,tables:4,status:'registration',entrants:[],matches:[]}");
  assert.equal(idle.evaluate('tonightState()'), 'idle');
  const idleHtml = idle.evaluate('tonightScreen()');
  assert.ok(idleHtml.includes('class="card card--start"'), 'idle: the start-tonight card');
  assert.ok(idleHtml.includes('class="first-run"'), 'idle: the three-step guide');
  assert.ok(idleHtml.includes('table-grid'), 'idle: the tables, resident from the first minute');
  for (const gone of ['id="entrant-form"', 'class="scoreboard"', 'class="rounds"', 'card--wrap', 'details class="panel"']) {
    assert.ok(!idleHtml.includes(gone), `idle: no ${gone}`);
  }
  const reg = harness();
  tonightNight(reg, null);
  assert.equal(reg.evaluate('tonightState()'), 'registration');
  const regHtml = reg.evaluate('tonightScreen()');
  for (const there of ['id="entrant-form"', 'class="desk-search"', 'data-action="tournament-start"', 'class="first-run"', 'table-grid']) {
    assert.ok(regHtml.includes(there), `registration: ${there}`);
  }
  for (const gone of ['class="scoreboard"', 'class="rounds"', 'card--wrap']) {
    assert.ok(!regHtml.includes(gone), `registration: no ${gone}`);
  }
  const active = harness();
  tonightNight(active, 'drawn');
  assert.equal(active.evaluate('tonightState()'), 'active');
  assert.equal(active.evaluate('comp()'), 'active');
  const activeHtml = active.evaluate('tonightScreen()');
  for (const there of ['class="scoreboard"', 'table-grid', 'class="rounds"', 'details class="panel"', 'class="attendance"', 'id="rename-form"']) {
    assert.ok(activeHtml.includes(there), `active: ${there}`);
  }
  for (const gone of ['id="settings-form"', 'id="entrant-form"', 'card--wrap']) {
    assert.ok(!activeHtml.includes(gone), `active: no ${gone}`);
  }
  assert.ok(activeHtml.indexOf('class="scoreboard"') > activeHtml.indexOf('table-grid'), 'nothing is live, so the board sits under the tables');
  active.evaluate("data.tournament.matches[1].status='live';data.tournament.matches[1].table=1");
  assert.equal(active.evaluate('dirtyComp()'), true, 'a ball on a table is what dirty means');
  assert.ok(active.evaluate('tonightScreen()').indexOf('class="scoreboard"') < active.evaluate('tonightScreen()').indexOf('table-grid'), 'and a live table pins the board above the grid');
  const done = harness();
  tonightNight(done, 'done');
  assert.equal(done.evaluate('tonightState()'), 'complete');
  assert.equal(done.evaluate('comp()'), 'complete');
  const doneHtml = done.evaluate('tonightScreen()');
  for (const there of ['card--wrap', 'data-action="results-sheet"', 'data-action="new-event"', 'class="rounds"', 'table-grid']) {
    assert.ok(doneHtml.includes(there), `complete: ${there}`);
  }
  for (const gone of ['class="scoreboard"', 'details class="panel"', 'id="entrant-form"', 'id="settings-form"']) {
    assert.ok(!doneHtml.includes(gone), `complete: no ${gone}`);
  }
  // The state machine is data, not history: a night that moves on repaints the same URL.
  const h = harness();
  tonightNight(h, null);
  h.evaluate('render=()=>{}');
  h.evaluate("data.tournament.status='active';data.tournament.matches=[{id:'m1',round:1,sides:['a','b'],score:[0,0],status:'live',table:1,absent:[]}]");
  h.evaluate('syncRoute(false)');
  assert.equal(h.context.location.hash, '#/tonight', 'a data-driven move keeps the one Tonight URL');
  assert.ok(h.visits.every(v => v[0] === 'replace'), 'and never adds a history entry');
});
test('the tables are resident, the dashboard follows the live event, and the night\'s buttons write the right actions (stage 9)', async () => {
  const h = harness();
  h.evaluate("data.players=[{id:'p1',name:'Ana',status:'Active',rating:50}];data.tournament={id:'t0',name:'',format:'singles',raceTo:7,tables:3,status:'registration',entrants:[],matches:[]}");
  const startView = h.evaluate('tonightScreen()');
  assert.ok(startView.includes('table-grid'), 'the tables are the resident body');
  assert.equal((startView.match(/data-table="/g) || []).length, 3, 'one card per table the event declares');
  assert.ok(!startView.includes('class="scoreboard"') && !startView.includes('details class="panel"'), 'no dashboard while the event is not live');
  assert.ok(startView.includes('data-action="start-night"'), '[Start tonight] is the way in');
  h.evaluate('render=()=>{}');
  h.evaluate("FormData=function(f){return f.values};__form={reportValidity:()=>true,values:[['name','Friday'],['format','singles'],['tables','3'],['raceTo','7']]};document.querySelector=sel=>sel==='#settings-form'?__form:null");
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'start-night'}}}});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'tournament_setup', payload: {name: 'Friday', format: 'singles', tables: 3, raceTo: 7}}], 'the start card reads its own form and sets the event up');
  assert.equal(h.evaluate('deskOpen'), true, 'and opens the registration desk, in place');
  assert.ok(h.evaluate('tonightScreen()').includes('id="entrant-form"'), 'so the first entrant can be signed in without leaving Tonight');
  // The server gate, not the data alone, decides whether the scoring dashboard exists.
  h.evaluate("data.tournament.entrants=[{id:'a',members:[{pid:'p1',name:'Ana'}]},{id:'b',members:[{name:'Bo'}]}];data.tournament.matches=[{id:'m1',round:1,sides:['a','b'],score:[0,0],status:'scheduled',table:null,absent:[]}]");
  assert.equal(h.evaluate('liveComp()'), false, 'the event is still only registered');
  const gated = h.evaluate('tonightScreen()');
  assert.ok(!gated.includes('class="scoreboard"') && !gated.includes('details class="panel"'), 'so no dashboard is drawn yet');
  h.evaluate("data.tournament.status='active'");
  assert.equal(h.evaluate('liveComp()'), true, 'starting the event opens the gate');
  const live = h.evaluate('tonightScreen()');
  assert.ok(live.includes('class="scoreboard"') && live.includes('details class="panel"'), 'and the dashboard arrives');
  // A free table offers the next match by number, and the send carries that number.
  h.evaluate('calls.length=0');
  assert.ok(/data-action="schedule" data-id="m1" data-table="1"/.test(live), 'a free table offers to send the next match to it');
  assert.ok(live.includes(h.evaluate("esc(t('sendNext').replace('{table}','1'))")), 'and the button says which table it is');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {action: 'schedule', id: 'm1', table: '1'}}}});
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'match_schedule', payload: {id: 'm1', table: 1}}], 'sending names the match and the table');
});
test('a table card says what is on that table: a signed result, a live score, or the next match to send (stage 9)', () => {
  const h = harness();
  h.evaluate(`data.players=[{id:'pa',name:'Ann',status:'Active',rating:1},{id:'pb',name:'Bea',status:'Active',rating:2}];
    const E=(id,pid,name)=>({id,members:[{pid,name}]});
    data.tournament={id:'t0',name:'Friday',format:'singles',raceTo:3,tables:3,status:'active',
      entrants:[E('a','pa','Ann'),E('b','pb','Bea'),E('c',null,'Cy'),E('d',null,'Di')],
      matches:[{id:'m1',round:1,sides:['a','b'],score:[3,1],status:'complete',result:'played',winnerId:'a',table:1,absent:[]},
               {id:'m2',round:1,sides:['c','d'],score:[2,0],status:'live',table:2,absent:[]},
               {id:'m3',round:2,sides:['a','c'],score:[0,0],status:'scheduled',table:null,absent:[]}]}`);
  const grid = h.evaluate('tablesGrid()');
  assert.ok(grid.includes(h.evaluate("esc(t('tablesBody'))")), 'the grid is headed');
  const cards = grid.split('<article class="table-card').slice(1);
  assert.equal(cards.length, 3, 'one card per table');
  assert.ok(cards[0].includes('data-table="1"') && cards[0].includes('Ann') && cards[0].includes('Bea'), 'T1 names both sides');
  assert.ok(/<strong class="digits">3<\/strong>/.test(cards[0]) && /<strong class="digits">1<\/strong>/.test(cards[0]), 'and carries the signed score');
  assert.ok(cards[0].includes(h.evaluate("esc(t('complete'))")), 'T1 reads Signed');
  assert.ok(/data-action="schedule" data-id="m3" data-table="1"/.test(cards[0]), 'a table whose match is signed is free again and offers the next one');
  assert.ok(/class="table-card live"/.test(grid) && cards[1].includes(h.evaluate("esc(t('live'))")), 'T2 is the table with a ball on it');
  assert.ok(cards[1].includes('data-action="focus"'), 'and it can be brought to the scoreboard');
  assert.ok(!cards[1].includes('data-action="schedule"'), 'a table in play is never offered a second match');
  assert.ok(cards[2].includes(h.evaluate("esc(t('tableFree'))")), 'T3 says it is free');
  assert.ok(/data-action="schedule" data-id="m3" data-table="3"/.test(cards[2]), 'and offers the waiting match by table number');
  // Absent players are named, not silently sent: an absent side holds the match.
  h.evaluate("data.tournament.matches[2].absent=['a']");
  assert.ok(!/data-action="schedule"/.test(h.evaluate('tablesGrid()')), 'a held match is offered to no table');
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
      const label = h.evaluate(`lang='${lang}';auditActions[${JSON.stringify(action)}]?.[lang==='zh'?1:0]`);
      assert.ok(label && label !== action, `${action} is a sentence in ${lang}, not the backend enum`);
    }
  }
  const line = h.evaluate(`lang='en';auditLine({action:'event_backfill',createdAt:'2026-10-03T05:23:40.400503+00:00',revision:75})`);
  assert.ok(line.includes('Backfilled from a VOD'), 'a backfilled night reads as that, not as event_backfill');
  assert.ok(!/event_backfill/.test(line), 'and the raw enum never reaches the operator');
  assert.ok(line.includes('v75'), 'the revision still rides along');
});

test('round 2: every instant on Records is formatted the one way (B-02)', () => {
  const h = harness();
  recordsNight(h);
  h.evaluate(`data.history[0].signOff={at:'2026-09-21T03:15:00Z'};data.events.push({id:'e2',action:'event_backfill',createdAt:'2026-10-03T05:23:40.400503+00:00',revision:75,context:{id:'h1'}})`);
  const rec = h.evaluate("lang='en';recordsScreen()");
  const said = h.evaluate("dateLine('2026-09-21T03:15:00Z')");
  assert.ok(rec.includes(said), `the sign-off instant is printed the way the audit log prints it (${said})`);
  assert.ok(!rec.includes('2026-09-21T03:15:00Z'), 'and never as a raw ISO stamp');
  assert.ok(!rec.includes('.400503'), 'no microseconds anywhere on the screen');
});

test('round 2: Records is navigable by heading (B-03, B-13)', () => {
  const h = harness();
  recordsNight(h);
  const rec = h.evaluate("lang='en';recordsScreen()");
  assert.ok(/<h2[^>]*>/.test(rec) && /<h3 class="tl-year">/.test(rec) && /<h3 class="tl-month-head">/.test(rec),
    'the page, the year and the month are all heading levels (h2, h3, h3)');
  assert.ok(!/十月/.test(rec) && !/九月/.test(rec), 'in EN no Chinese month rides along');
  const monthHead = h.evaluate("monthLabel(eventDate(data.history[0]))");
  assert.ok(rec.includes(`class="tl-month-head">${monthHead}<`), `the month heads as ${monthHead} alone, with no second script`);
  assert.ok(/<h3 class="tl-year">2026<\/h3>/.test(rec), 'and the year is a heading, not a styled list item');
  assert.ok(opsCss.includes('.tl-month-head{') && !/[^-]\btl-month\{/.test(opsCss), 'the old non-heading month class is gone from the stylesheet');
});

test('round 2: Regulars has a heading, and both Queue panels are named for their content (B-13, B-12)', () => {
  const h = harness();
  recordsNight(h);
  const players = h.evaluate("lang='en';playersScreen()");
  assert.ok(/<h2[^>]*>\s*/.test(players) && players.includes(h.evaluate("esc(t('players'))")), 'Regulars has an h2 of its own');
  h.evaluate("lang='zh'");
  assert.ok(h.evaluate("esc(t('queueTitle'))") === '等待上场', 'the waiting list is no longer headed with the board’s word for Queue');
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
  assert.ok(/#ops-shell \.card-toggle\{[^}]*width:44px;height:44px/.test(phone), 'a 24 px glyph gets a 44 px target on a phone');
  assert.ok(/#ops-shell \.card-toggle\{[^}]*min-height:44px/.test(phone), 'and outranks the base min-height:0');
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
  h.evaluate(`data.tournament={id:'t0',name:'Tonight',format:'singles',raceTo:3,tables:2,status:'active',entrants:[{id:'a',members:[{pid:'pa',name:'Ann'}]},{id:'b',members:[{pid:'pb',name:'Bea'}]}],matches:[{id:'m1',round:1,sides:['a','b'],score:[0,0],status:'live',table:1,absent:[]}]};data.players=[];render=()=>{}`);
  const board = h.evaluate('floorScreen() + scoreboardScreen()');
  assert.ok(!/data-clock/.test(board), 'neither the floor nor the scoreboard draws a clock of its own — the bar’s slot is the one home');
  assert.equal((h.evaluate('timerHTML()').match(/data-clock/g) || []).length, 1, 'the bar’s slot renders exactly one clock, with its own controls');
  assert.ok(/data-action="clock-toggle"/.test(h.evaluate('timerHTML()')) && /data-action="clock-reset"/.test(h.evaluate('timerHTML()')), 'and the controls live in the slot, not on the scoreboard');
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
