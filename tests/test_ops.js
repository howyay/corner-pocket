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
    const bracket = h.evaluate("density='compact';matchesScreen()");
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
  const present = 'a51461c2c94649988a2995e9b27c69a8', removed = 'b0000000c94649988a2995e9b27c69ff', source = '77777777777777777777777777777777';
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
    const html = h.evaluate('matchesScreen()');
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
  const compact = h.evaluate("density='compact';matchesScreen()");
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
  const full = h.evaluate("density='full';matchesScreen()");
  assert.ok(full.includes('data-density="full"') && full.includes('Table 1 · m1'), 'full cards render as before');
  const css = fs.readFileSync(path.join(__dirname, '../annotator/ops.css'), 'utf8');
  assert.ok(css.includes('.rounds[data-density=full] .round .entry{min-height:98px}'), 'the 98 px card height applies to full cards only');
  assert.ok(css.includes('.entry:is(:hover,:focus-within,.selected) :is(.card-head,.card-actions){display:flex}'), 'hover or focus opens the full card');
  assert.ok(/grid-auto-columns:minmax\(180px,1fr\)/.test(css), 'rounds share the viewport width');
  for (const key of ['density', 'densityCompact', 'densityFull']) assert.match(source, new RegExp(`\\b${key}:\\['[^']+','[^']+'\\]`), `${key} has EN and 中`);
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
test('onboard: an empty club gets three real steps on the Floor, and they leave once the draw exists', () => {
  const h = harness();
  const guide = () => { const html = h.evaluate('floorScreen()'); const m = html.match(/<article class="first-run"[\s\S]*?<\/article>/); return m ? m[0] : ''; };
  const first = guide();
  assert.ok(first, 'an empty club sees the guide');
  assert.deepEqual([...first.matchAll(/data-tab="([a-z]+)"/g)].map(m => m[1]), ['players', 'setup', 'setup'], 'each step is the tab button that does it');
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
  const views = {floor: h.evaluate('floorScreen()'), setup: h.evaluate('setupScreen()'), matches: h.evaluate('matchesScreen()')};
  for (const [name, html] of Object.entries(views)) assert.ok(!/>Ada</.test(html) && !/\bAda \//.test(html), `${name}: the stale snapshot name never shows`);
  assert.ok(views.matches.includes('Ada Lovelace'), 'bracket shows the current name');
  const archive = views.matches.slice(views.matches.indexOf('<details'));
  assert.ok(archive.includes('Ada Lovelace'), 'the archived event reads the live roster name for a regular');
  assert.ok(!/Ada —|— Ada\b|>Ada</.test(archive), 'the archive never falls back to the draw-time copy while the regular exists');
  assert.ok(archive.includes('Walk-in Wu'), 'a guest keeps the name typed at the desk');
  // a deleted regular (no roster row) still reads by the snapshot, never "Unknown"
  h.evaluate("data.players=data.players.filter(p=>p.id!=='p2')");
  assert.ok(h.evaluate('matchesScreen()').includes('>Bo'), 'the snapshot is the fallback when the regular is gone');
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
    const html = h.evaluate('matchesScreen()');
    const card = html.slice(html.indexOf('class="rounds"'));
    const first = card.slice(0, card.indexOf('<h3>', card.indexOf('<h3>') + 1));
    assert.ok(first.includes(`>${bye}<`), `${lang}: the bye card is labelled ${bye}`);
    assert.equal((first.match(new RegExp(`>${signed}<`, 'g')) || []).length, 1, `${lang}: only the played card says ${signed}`);
    assert.ok(!first.includes(`>${waiting}<`), `${lang}: the empty side of a bye never reads ${waiting}`);
    const tile = html.match(new RegExp(`<small>${cards}</small><strong>([^<]*)</strong>`))[1];
    assert.equal(tile, '1/2', `${lang}: byes are left out of the signed count and its total`);
    const archive = html.slice(html.indexOf('<details'));
    assert.ok(archive.includes(`>${bye}<`) && !archive.includes(`${esc_(waiting)}`), `${lang}: the archive labels the bye too`);
    const floor = h.evaluate('floorScreen()');
    assert.equal(floor.match(new RegExp(`<small>${cards}</small><strong>([^<]*)</strong>`))[1], '1/2', `${lang}: the Floor tile agrees`);
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
    const matches = h.evaluate('matchesScreen()');
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
  const html = h.evaluate('matchesScreen()');
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
  for (const [lang, rating, table, wins, played, rate] of [['en', 'House rating (manual)', 'Event table', 'Wins', 'Played', 'Win %'], ['zh', '球房评分（手动）', '本场战绩表', '胜场', '场次', '胜率']]) {
    h.evaluate(`lang='${lang}'`);
    const html = h.evaluate('matchesScreen()');
    const standings = html.slice(html.indexOf(`<table class="standings"`), html.indexOf('</table>', html.indexOf(`<table class="standings"`)));
    for (const head of [rating, wins, played, rate]) assert.ok(standings.includes(`>${head}<`), `${lang}: standings column ${head}`);
    // all-time rows: Ann 1-1 (bye excluded), Bea 2-1, Cai 0-1, Dee 1-0 (forfeit win)
    const row = name => standings.match(new RegExp(`>${name}<[^]*?</tr>`))[0].replace(/<[^>]+>/g, '|').split('|').filter(Boolean);
    assert.deepEqual(row('Bea').slice(-4), ['900', '2', '3', '67%']);
    assert.deepEqual(row('Ann').slice(-4), ['100', '1', '2', '50%']);
    assert.deepEqual(row('Dee').slice(-4), ['400', '1', '1', '100%']);
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
  assert.ok(h.evaluate('matchesScreen()').includes('data-action="results-sheet" data-id="h1"'), 'each archived event offers its sheet');
  h.evaluate("data.tournament.matches=[{id:'q1',round:1,sides:['x','y'],score:[0,0],status:'scheduled',absent:[]}]");
  assert.ok(h.evaluate('matchesScreen()').includes('data-action="results-sheet" data-id="t0"'), 'tonight has a sheet once drawn');
  h.evaluate('data.tournament.matches=[]');
  assert.ok(!h.evaluate('matchesScreen()').includes('data-id="t0"'), 'no sheet before the draw');
  await click({action: 'results-sheet', id: 'h1'});
  assert.equal(h.evaluate('sheetId'), 'h1', 'the click opens the sheet');
  const sheet = h.evaluate('matchesScreen()');
  assert.ok(sheet.includes('class="stack results-sheet"'), 'the sheet replaces the Matches view');
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
  assert.ok(!h.evaluate('matchesScreen()').includes('class="stack results-sheet"'), 'back returns to the bracket');
  await click({action: 'results-sheet', id: 'h1'});
  h.evaluate('canNavigate=()=>true');
  await h.handlers.click({target: {closest: s => s === '#review-root' ? null : {dataset: {tab: 'floor'}}}});
  assert.equal(h.evaluate('sheetId'), null, 'leaving Matches closes the sheet');
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
    const html = h.evaluate('matchesScreen()');
    const block = id => { const i = html.indexOf(`data-id="${id}"`); return i < 0 ? '' : html.slice(html.lastIndexOf('<details', i), html.indexOf('</details>', i)); };
    assert.ok(block('h1').includes(`>${hide}<`) && !block('h1').includes(`>${del}<`), `${lang}: a signed event can only be hidden`);
    assert.ok(block('h2').includes(`>${del}<`), `${lang}: an unsigned event can be deleted`);
    assert.ok(!html.includes('Hidden night'), `${lang}: a hidden event is out of the list`);
    assert.ok(html.includes(`>${showHidden}<`), `${lang}: the hidden count is offered`);
    h.evaluate('showHidden=true');
    const all = h.evaluate('matchesScreen()');
    assert.ok(all.includes('Hidden night') && all.includes(`>${unhide}<`), `${lang}: hidden events can be shown and restored`);
    assert.ok(h.evaluate('setupScreen()').includes('data-action="event-delete" data-id="t0"'), `${lang}: tonight, unsigned, can be deleted from Set up`);
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
    const html = h.evaluate('matchesScreen()');
    assert.ok(html.includes(`>${title}<`) && html.includes(`>${drawBtn}<`), `${lang}: the draw is offered while round 2 is unsigned`);
    assert.ok(html.includes(label), `${lang}: it is labelled as a random draw`);
  }
  h.evaluate("data.tournament.matches[3]={...data.tournament.matches[3],status:'scheduled',result:undefined,winnerId:null}");
  assert.ok(!h.evaluate('matchesScreen()').includes('data-action="revival-draw"'), 'no draw until every round-1 loser is known');
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
  const drawn = h.evaluate('matchesScreen()');
  assert.ok(drawn.includes('抽中：Fay') && drawn.includes('种子 12345') && drawn.includes('候选：Dee、Fay'), '中: who, the seed and the pool are shown');
  assert.ok(drawn.includes('data-action="revival-undo"'), 'undo is offered until the next result');
  assert.ok(!drawn.includes('data-action="revival-draw"'), 'one draw per event');
  await click({action: 'revival-undo'});
  assert.equal(asked.at(-1), '撤销这次复活抽签？该空位将恢复为轮空，签过的赛果不受影响。');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls)')), [{name: 'revival_draw', payload: {confirm: true}}, {name: 'revival_undo', payload: {confirm: true}}]);
  // after a newer signed result, undo is gone and the drawn line stays as history
  h.evaluate("data.tournament.matches[5]={...data.tournament.matches[5],status:'complete',result:'played',winnerId:'c',score:[3,2]}");
  const closed = h.evaluate('matchesScreen()');
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
  const screens = {matches: h.evaluate('matchesScreen()'), record: h.evaluate('playersScreen()')};
  assert.ok(/class="standings"/.test(screens.matches) && /class="event-table"/.test(screens.matches), 'the Matches tables render');
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
