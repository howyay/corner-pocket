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
  vm.runInContext(source.replace("(() => {", '').replace(/reload\(\);\s*\}\)\(\);\s*$/, ''), context);
  vm.runInContext("data={revision:1,settings:{},tournament:{raceTo:7,entrants:[],matches:[]},players:[],history:[]}; calls=[]; realAction=action; action=async(name,payload)=>{calls.push({name,payload});return true}", context);
  return {context, handlers, evaluate: expression => vm.runInContext(expression, context)};
}
test('live processing allows datasets and saved channels, never arbitrary media URLs', () => {
  const h = harness();
  assert.deepEqual(JSON.parse(h.evaluate("JSON.stringify(liveSource('dataset:highlight'))")), {kind:'dataset', dataset:'highlight'});
  assert.deepEqual(JSON.parse(h.evaluate("JSON.stringify(liveSource('twitch:saved-id'))")), {kind:'twitch', source_id:'saved-id'});
  h.evaluate("data.sources=[{id:'channel',url:'https://www.twitch.tv/examplechannel'},{id:'vod',url:'https://www.twitch.tv/videos/123'}]");
  const html = h.evaluate('livePanel()');
  assert.ok(html.includes('twitch:channel'));
  assert.ok(!html.includes('twitch:vod'));
  assert.ok(html.includes('dataset:vod30') && html.includes('dataset:highlight'));
  assert.ok(html.includes('data-live-detector="table"') && html.includes('data-live-detector="person"'));
  assert.ok(html.includes('UNKNOWN') && html.includes('not glass-to-glass'));
  h.evaluate("lang='zh'");
  assert.ok(h.evaluate('livePanel()').includes('原生实时处理'));
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
test('live poll uses actual processor status and atomically paired JPEG metadata', async () => {
  const h=harness(), statusNode={}, drawn=[], canvas={getContext:()=>({drawImage:()=>drawn.push('image'),strokeRect:(...box)=>drawn.push(box)})};
  h.context.document.querySelector=selector=>selector==='#live-frame'?canvas:statusNode;
  h.context.createImageBitmap=async()=>({width:640,height:360,close(){}});
  h.context.fetch=async url=>url==='/api/live'?{ok:true,json:async()=>({state:'running',frame_age_ms:2500,frames_skipped:9,latest:{receive_to_result_ms:25,detections:{boxes:[{bbox:[9,9,9,9]}]}}})}:{ok:true,headers:{get:key=>key==='X-Live-Sequence'?'12':JSON.stringify({seq:12,detections:{boxes:[{bbox:[1,2,11,22]}]}})},blob:async()=>({})};
  await h.evaluate('pollLive(liveGeneration)');
  assert.ok(statusNode.textContent.startsWith('running'));
  assert.ok(statusNode.textContent.includes('25 ms')&&statusNode.textContent.includes('2500 ms')&&statusNode.textContent.includes('STALE')&&statusNode.textContent.includes('Dropped: 9'));
  assert.deepEqual(drawn,['image',[1,2,10,20]]);
  assert.equal(canvas.hidden,false);
});
test('live image overlays use metadata paired with the JPEG, not status polling', () => {
  assert.ok(source.includes("frame.headers.get('X-Live-Metadata')"));
  assert.ok(source.includes("frame.headers.get('X-Live-Sequence')"));
  assert.ok(source.includes('const detections=meta.detections||{}'));
  assert.ok(source.includes('if(generation!==liveGeneration)return;const canvas'));
  assert.ok(source.includes('receive_to_result_ms'));
});
test('Vision is fourth and every review mode is a native subtab', () => {
  const h = harness();
  assert.equal(h.evaluate("t('vision')"), 'Vision');
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(Object.keys(reviewModes))')), ['stream','events','balls','calibration','players','timeline']);
  assert.ok(source.includes("['floor','setup','matches','vision','players','status']"));
  assert.ok(!source.includes('review-frame'));
  assert.ok(!source.includes('src="/app.html"'));
});
test('dirty or busy review vetoes top-level and subtab navigation', async () => {
  for (const dataset of [{tab:'vision'}, {vision:'balls'}, {action:'floor'}]) {
    const h = harness();
    h.context.window.CornerPocketReview = {canLeave: () => false, activate: () => false};
    h.evaluate("tab='vision';visionTab='events'");
    await h.handlers.click({target:{closest: selector => selector === '#review-root' ? null : {dataset}}});
    assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify([tab,visionTab,lang,theme])')), ['vision','events','en','dark']);
  }
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
test('player notes are editable and safely escaped', () => {
  const h = harness();
  const html = h.evaluate("playerForm({id:'p1',name:'A',notes:'</textarea><script>x</script>'})");
  assert.ok(html.includes('name="notes" maxlength="4000"'));
  assert.ok(html.includes('&lt;/textarea&gt;'));
  assert.ok(!html.includes('<script>'));
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
  return {preventDefault() {}, target: {id: {shadowedByNamedControl: true}, getAttribute: () => formId, classList: {contains: () => false}, values}, submitter};
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
test('appearance form serializes numbers and unchecked diamonds correctly', async () => {
  const h = harness();
  await h.handlers.submit(submission('appearance-form', {clothColor: '#1f4a70', lampGlow: '0.4'}));
  assert.deepEqual(JSON.parse(h.evaluate('JSON.stringify(calls[0])')), {name: 'settings_update', payload: {clothColor: '#1f4a70', lampGlow: 0.4, showDiamonds: false}});
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
