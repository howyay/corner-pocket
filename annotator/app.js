(() => {
'use strict';
// Vanilla review UI. API writes happen only on explicit user actions.
let root = null, active = false, mounting = null, initialized = false;
const $ = (s, scope = root) => scope.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const enc = encodeURIComponent;
const state = {mode:'events',dataset:'vod30',sets:[],set:'',data:null,index:0,filter:'all',dirty:false,busy:false,epoch:0,anchor:0,pts:[],t:70,win:'',track:null,frame:0,vmeta:null,fresult:null,boxes:[],polygon:null,sel:-1,tool:'select',drag:null,shotUrl:null,frameReq:0,frameWidth:0,frameHeight:0,scrubbing:false,inferTimer:null,inferRunning:false,detectors:{table:true,person:true,balls:false},unified:null,overlay:{balls:true,pockets:true,persons:true,identity:true}};
const modes = {events:['Event review','Inspect shot and pot candidates against their source evidence.'],balls:['Ball labels','Resolve crop identities. Cue is 0; numbered balls are 1–15.'],calibration:['Table calibration','Place six pocket anchors on the original, unwarped video frame.'],players:['Player identities','Review track boxes and explicitly seed player A, player B, or ignore.'],timeline:['Unified viewer','Scrub the local VOD and inspect balls, pockets, cloth, persons, and identity overlays on one canvas.']};
let rebuildTimer;
function notice(text, error = false) { const el = $('#notice'); el.hidden = !text; el.className = error ? 'error' : ''; el.textContent = text; }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let data; try { data = await response.json(); } catch { throw new Error(`Server returned non-JSON (${response.status}). Open this workbench through the review server.`); }
  if (!response.ok || data.error) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
function canLeave() { return !state.busy && (!state.dirty || confirm(text('Discard unsaved changes?'))); }
function markDirty() { state.dirty = true; const el = $('#save-state'); if (el) el.textContent = 'Unsaved changes'; }
async function save(button, path, body, after) {
  if (state.busy) return;
  state.busy = true; button.disabled = true; const label = button.textContent; const savedLabel = Object.keys(editorCopy).find(key => editorCopy[key] === label) || label; button.textContent = text('Saving…');
  const fields = [...root.querySelectorAll('#content input, #content select, #content textarea')].filter(el => !el.disabled); fields.forEach(el => el.disabled = true);
  try { const data = await api(path, body); if (after) after(data); state.dirty = false; notice('Saved to the review dataset.'); const el = $('#save-state'); if (el) el.textContent = 'Saved'; }
  catch (error) { notice(`Save failed: ${error.message}. Your changes remain on screen; retry when ready.`, true); }
  finally { state.busy = false; button.disabled = false; button.textContent = text(savedLabel); fields.forEach(el => el.disabled = false); }
}
function time(t) { t = Number(t) || 0; return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2,'0')}`; }
function image(src, alt, cls = '') { return `<img class="${cls}" src="${esc(src)}" alt="${esc(alt)}">`; }
function imageErrors() { root.querySelectorAll('#content img').forEach(img => img.addEventListener('error', () => { if (img.dataset.fallback) { const fallback = img.dataset.fallback; delete img.dataset.fallback; img.alt = 'Raw source frame fallback (original evidence unavailable)'; const caption = document.createElement('div'); caption.className = 'facts'; caption.textContent = 'RAW SOURCE FRAME FALLBACK · Original evidence image unavailable'; img.insertAdjacentElement('afterend',caption); img.addEventListener('error', () => { const error = document.createElement('div'); error.className = 'image-error'; error.textContent = 'Evidence and raw source frame unavailable. Try the source video below.'; img.replaceWith(error); }, {once:true}); img.src = fallback; return; } if (img.closest('.frame')) { const frame = img.closest('.frame'); frame.classList.add('failed'); if (!frame.querySelector('.frame-error')) frame.insertAdjacentHTML('beforeend','<div class="frame-error">Frame unavailable. Choose another time or retry loading.</div>'); } else { const error = document.createElement('div'); error.className = 'image-error'; error.textContent = `${img.alt} unavailable.`; img.replaceWith(error); } }, {once:true})); }
async function loadMode() {
  clearTimeout(rebuildTimer); clearTimeout(state.inferTimer); const epoch = ++state.epoch; state.frameReq++;
  state.dirty = false; state.index = 0; state.filter = 'all'; state.data = null;
  $('#title').textContent = modes[state.mode][0]; $('#subtitle').textContent = modes[state.mode][1];
  root.querySelectorAll('[data-mode]').forEach(b => { b.classList.toggle('active', b.dataset.mode === state.mode); b.setAttribute('aria-current', b.dataset.mode === state.mode ? 'page' : 'false'); });
  notice(''); $('#content').setAttribute('aria-busy','true'); $('#content').innerHTML = '<div class="empty">Loading review data…</div>';
  try {
    if (['calibration','players'].includes(state.mode) && state.dataset !== 'vod30') { $('#content').innerHTML = '<div class="empty">Calibration and player seed review are available for the 30-minute VOD only.<br>Select the 30-minute dataset above.</div>'; return; }
    let data;
    if (state.mode === 'timeline') { const [events,meta] = await Promise.all([api(`/api/${enc(state.dataset)}/events`), api(`/api/video?dataset=${enc(state.dataset)}`)]); if (epoch !== state.epoch) return; state.data = {events: events.events || []}; state.vmeta = meta; renderTimeline(); return; }
    if (state.mode === 'events') data = await api(`/api/${enc(state.dataset)}/events`);
    if (state.mode === 'balls') data = await api(`/api/balls/${enc(state.set)}/meta`);
    if (state.mode === 'calibration') data = await api(`/api/vod30/anchors?t=${state.t}`);
    if (state.mode === 'players') data = await api('/api/vod30/tracklets');
    if (epoch !== state.epoch) return;
    state.data = data;
    if (state.dataset === 'highlight' && state.mode === 'events') notice('Highlight candidates were generated with the wrong-resolution calibration. They are not valid accuracy evidence; inspect the source before judging.',true);
    ({events:renderEvents,balls:renderBalls,calibration:renderCalibration,players:renderPlayers})[state.mode]();
  } catch (error) { if (epoch === state.epoch) { notice(error.message,true); $('#content').innerHTML = '<div class="empty">Could not load this workspace.<br><button id="retry">Retry loading</button></div>'; $('#retry').onclick = loadMode; } }
  finally { if (epoch === state.epoch) $('#content').setAttribute('aria-busy','false'); }
}
function filteredEvents() { return (state.data.events || []).filter(e => state.filter === 'all' || e.type === state.filter || (state.filter === 'pending' && !state.data.annotations?.[String(e.id)])); }
function renderEvents() {
  const events = filteredEvents(), annotations = state.data.annotations || {};
  const reviewed = (state.data.events || []).filter(e => annotations[String(e.id)]).length;
  $('#content').innerHTML = `<div class="toolbar"><label>Queue <select id="event-filter">${['all','shot','pot','pending'].map(v => `<option value="${v}" ${v === state.filter ? 'selected' : ''}>${{all:'All candidates',shot:'Shots',pot:'Pots',pending:'Unreviewed'}[v]}</option>`).join('')}</select></label><span class="count">${reviewed} / ${(state.data.events || []).length} reviewed · ${events.length} in queue</span></div><div class="review-grid"><section class="panel queue" aria-label="Event queue">${events.map((e,i) => `<button data-event="${i}" class="${i === state.index ? 'selected' : ''}"><span class="row"><span class="badge ${esc(e.type)}">${esc(e.type)}</span><span>${time(e.t)}</span></span><small>#${esc(e.id)} · ${esc(annotations[String(e.id)]?.verdict || 'Needs review')}</small></button>`).join('') || '<div class="empty">No events in this queue.</div>'}</section><section class="panel" id="event-detail"></section></div>`;
  $('#event-filter').onchange = e => { if (!canLeave()) { e.target.value = state.filter; return; } state.filter = e.target.value; state.index = 0; state.dirty = false; renderEvents(); };
  root.querySelectorAll('[data-event]').forEach(b => b.onclick = () => { if (canLeave()) { state.index = Number(b.dataset.event); state.dirty = false; renderEvents(); } });
  const e = events[state.index]; if (!e) { $('#event-detail').innerHTML = '<div class="empty">Select another queue to continue.</div>'; return; }
  const a = annotations[String(e.id)] || {};
  const evidenceImg = e.evidence ? image(`/media/${enc(state.dataset)}/evidence/${enc(e.evidence.split('/').pop())}`,`Evidence for event ${e.id}`,'evidence') : image(`/media/${enc(state.dataset)}/event-frame/${enc(e.id)}`,'Raw source frame (no original evidence image)','evidence');
  const posterMatch = evidenceImg.match(/src="([^"]+)"/);
  const poster = posterMatch ? posterMatch[1] : '';
  const clip = `<figure class="evidence evidence-clip"><video controls loop muted playsinline preload="metadata" poster="${esc(poster)}" src="/api/clip?dataset=${enc(state.dataset)}&t=${encodeURIComponent(e.t)}" onerror="clipFailed(this)" aria-label="Video clip around event ${esc(e.id)}"></video><figcaption class="facts">CLIP ${time(Math.max(0,(e.t||0)-1.5))}–${time((e.t||0)+2.5)} · loops · static frame on failure</figcaption></figure>`;
  $('#event-detail').innerHTML = `<div class="panel-head"><h2>${e.type === 'pot' ? 'Pot' : 'Shot'} candidate <span class="muted">#${esc(e.id)}</span></h2><span class="badge">${time(e.t)}</span></div>${clip}<div class="facts"><span>TIME ${esc(e.t)}s</span>${e.nearest_pocket ? `<span>POCKET ${esc(e.nearest_pocket)}</span>` : ''}${e.window_s ? `<span>WINDOW ${esc(e.window_s.join('–'))}s</span>` : ''}<span>CANDIDATE · NOT VALIDATED</span></div><div class="panel-body"><h3>Review decision</h3><div class="form-grid"><label>Verdict<select id="verdict"><option value="">Choose a verdict</option>${['correct','wrong','unsure'].map(v => `<option ${a.verdict === v ? 'selected' : ''}>${v}</option>`).join('')}</select></label><label>Shooter (human label)<select id="shooter">${[['','Not assigned'],['A','Player A'],['B','Player B'],['?','Unknown']].map(([v,l]) => `<option value="${v}" ${a.shooter === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label></div><label for="note">Evidence / review note</label><textarea id="note" placeholder="What does the source actually show?">${esc(a.note || '')}</textarea><div class="actions"><button id="save-event" class="primary">Save review</button><button id="next-event" ${state.index >= events.length - 1 ? 'disabled' : ''}>Next candidate →</button><span id="save-state" class="save-state">${a.verdict ? 'Saved review' : 'Not reviewed'}</span></div><details class="source-video"><summary>Open source video at ${time(e.t)}</summary><video controls preload="none" src="/media/${enc(state.dataset)}/video#t=${Number(e.t) || 0}"></video></details></div>`;
  if (e.evidence) { const fallbackVideo = $('#event-detail .evidence-clip video'); if (fallbackVideo) fallbackVideo.dataset.rawFallback = `/media/${enc(state.dataset)}/event-frame/${enc(e.id)}`; }
  ['verdict','shooter','note'].forEach(id => $('#'+id).oninput = markDirty);
  $('#save-event').onclick = event => { if (!$('#verdict').value) { notice('Choose a verdict before saving.',true); return; } const body = {event_id:e.id,verdict:$('#verdict').value,shooter:$('#shooter').value,note:$('#note').value}; save(event.target,`/api/${enc(state.dataset)}/annotate`,body,() => { annotations[String(e.id)] = body; state.data.annotations = annotations; renderEvents(); }); };
  $('#next-event').onclick = () => { if (canLeave()) { state.index++; state.dirty = false; renderEvents(); } }; imageErrors();
}
function clipFailed(video) {
  const figure = video.closest('.evidence-clip');
  if (!figure) return;
  const img = document.createElement('img');
  img.className = 'evidence';
  img.src = video.dataset.rawFallback || video.poster;
  img.alt = 'Static evidence frame fallback (clip unavailable)';
  img.addEventListener('error', () => { const message = document.createElement('div'); message.className = 'image-error'; message.textContent = 'Clip and evidence frame unavailable. Use the source video below.'; img.replaceWith(message); }, {once:true});
  video.replaceWith(img);
  const caption = figure.querySelector('figcaption');
  if (caption) caption.textContent = 'STATIC FRAME FALLBACK · Clip encoding unavailable for this moment';
}
async function identityStatus() {
  const body = $('#identity-status-body');
  if (!body) return;
  try {
    const response = await fetch('/api/identity/status', {cache: 'no-store'});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || `HTTP ${response.status}`);
    const bound = (data.bound || []).map(b => `#${b.cluster_id.slice(0, 6)} → ${esc(b.player_id)}`).join(' · ');
    body.innerHTML = `${data.clusters || 0} identity cluster(s) · ${bound ? 'Bound: ' + bound : 'No face bindings yet.'}`;
  } catch (error) {
    body.textContent = `Identity models unavailable (${error.message}).`;
  }
}
function labelText(v) { return v === undefined || v === null ? 'Unlabeled' : v === -1 || v === 'u' ? 'Unknown' : v === 0 ? 'Cue · 0' : `Ball ${v}`; }
function filteredBalls() { return (state.data.items || []).filter(item => state.filter !== 'pending' || state.data.labels?.[item.file] == null); }
function renderBalls() {
  const items = filteredBalls(); state.index = Math.min(state.index,Math.max(0,items.length - 1)); const item = items[state.index];
  $('#content').innerHTML = `<div class="toolbar"><label>Crop set <select id="ball-set">${state.sets.map(s => `<option value="${esc(s.id)}" ${s.id === state.set ? 'selected' : ''}>${esc(s.label || s.id)}</option>`).join('')}</select></label><label>Queue <select id="ball-filter"><option value="all">All crops</option><option value="pending" ${state.filter === 'pending' ? 'selected' : ''}>Unlabeled</option></select></label><span class="count">${items.length ? state.index + 1 : 0} / ${items.length} crops · set independent of VOD selector</span></div><div id="crop-detail"></div>`;
  $('#ball-set').onchange = e => { if (!canLeave()) { e.target.value = state.set; return; } state.set = e.target.value; loadMode(); };
  $('#ball-filter').onchange = e => { if (!canLeave()) { e.target.value = state.filter; return; } state.filter = e.target.value; state.index = 0; renderBalls(); };
  if (!item) { $('#crop-detail').innerHTML = '<div class="empty">No crops in this queue.</div>'; return; }
  const file = item.file.split('/').pop(), label = state.data.labels?.[file];
  $('#crop-detail').innerHTML = `<section class="panel"><div class="panel-head"><h2>Identify the ball</h2><span class="badge">${esc(labelText(label))}</span></div><div class="crop-view panel-body"><div><div class="crop-images">${image(`/media/balls/${enc(state.set)}/${enc(file)}`,'Ball crop')}${item.ctx ? image(`/media/balls/${enc(state.set)}/ctx/${enc(item.ctx)}`,'Ball context','context') : ''}</div><p class="hint">${esc(file)} · ${time(item.t)}${item.score != null ? ` · detector score ${esc(item.score)} (not accuracy)` : ''}</p></div><div><h3>Human label</h3><div class="ball-grid">${Array.from({length:16},(_,i) => `<button data-label="${i}" class="${label === i ? 'selected' : ''}">${i}<small>${i === 0 ? 'CUE' : i <= 7 ? 'SOLID' : i === 8 ? 'EIGHT' : 'STRIPE'}</small></button>`).join('')}</div><div class="actions"><button data-label="-1" class="${label === -1 || label === 'u' ? 'selected' : ''}">Unknown</button><button data-label="clear">Clear label</button></div><p class="hint">Each label button saves immediately. Unknown is a saved decision; clear removes the label.</p><span id="save-state" class="save-state">${label == null ? 'Unlabeled' : 'Saved label'}</span></div></div><div class="panel-head"><button id="prev-crop" ${state.index === 0 ? 'disabled' : ''}>← Previous crop</button><button id="next-crop" ${state.index >= items.length - 1 ? 'disabled' : ''}>Next crop →</button></div></section>`;
  root.querySelectorAll('[data-label]').forEach(b => b.onclick = () => { const value = b.dataset.label === 'clear' ? null : Number(b.dataset.label); save(b,`/api/balls/${enc(state.set)}/label`,{file,label:value},() => { state.data.labels ||= {}; if (value === null) delete state.data.labels[file]; else state.data.labels[file] = value === -1 ? 'u' : value; renderBalls(); }); });
  $('#prev-crop').onclick = () => { if (!state.busy) { state.index--; renderBalls(); } }; $('#next-crop').onclick = () => { if (!state.busy) { state.index++; renderBalls(); } }; imageErrors();
}
const anchorNames = ['Top left','Top right','Bottom right','Bottom left','Left side','Right side'];
function frameHTML() { return `<div class="frame" id="frame">${image(`/media/vod30/frame?t=${state.t}`,'Raw VOD frame')}<svg id="overlay" role="group" aria-label="Frame annotations"></svg></div>`; }
function timeToolbar(extra = '') { return `<div class="toolbar">${extra}<label>Frame time (seconds) <input id="frame-time" type="number" min="0" step="0.1" value="${state.t}"></label><button id="load-frame">Load frame</button><span class="count">RAW FRAME · VOD30</span></div>`; }
function frameTimeAction(callback) { $('#load-frame').onclick = () => { const n = Number($('#frame-time').value); if ($('#frame-time').value === '' || !Number.isFinite(n) || n < 0) { notice('Enter a non-negative time in seconds.',true); return; } if (canLeave()) { state.t = n; callback(); } }; }
function renderCalibration() {
  const data = state.data; state.t = data.t ?? state.t;
  state.pts = (data.pts || data.suggested_pts || []).map(p => Array.isArray(p) ? [...p] : [p.x,p.y]);
  const w = data.width || 1920, h = data.height || 1080;
  if (state.pts.length !== 6) state.pts = [[.3,.2],[.7,.2],[.7,.8],[.3,.8],[.3,.5],[.7,.5]].map(([x,y]) => [Math.round(x*w),Math.round(y*h)]);
  $('#content').innerHTML = timeToolbar()+`<div class="frame-layout"><section class="panel"><div class="panel-head"><h2>Six-pocket anchors</h2><span class="badge">${data.pts ? 'Saved anchors' : 'Unsaved suggestion'}</span></div>${frameHTML()}<div class="panel-body hint">Drag an anchor, or select one and nudge with the controls. Arrow keys move the selected anchor by 1 pixel; Shift moves 10. Coordinates refer to the raw source frame.</div></section><section class="panel panel-body"><h3>Anchor positions</h3><div id="anchor-list" class="anchor-list"></div><div class="nudge"><span></span><button data-nudge="0,-1" aria-label="Nudge up">↑</button><span></span><button data-nudge="-1,0" aria-label="Nudge left">←</button><button data-nudge="0,1" aria-label="Nudge down">↓</button><button data-nudge="1,0" aria-label="Nudge right">→</button></div><button id="save-anchors" class="primary">Save six anchors</button><p id="save-state" class="hint">${data.pts ? 'Saved annotation' : 'Suggestion only — inspect before saving'}</p><p class="hint">Saving stores anchor annotations. It does not fit a calibration or rerun detection.</p><p class="hint">Suggested times: ${esc((data.suggested_times || []).join(', '))} seconds</p></section></div>`;
  state.frameWidth = w; state.frameHeight = h; $('#overlay').setAttribute('viewBox',`0 0 ${w} ${h}`); drawAnchors();
  frameTimeAction(loadMode);
  root.querySelectorAll('[data-nudge]').forEach(b => b.onclick = () => nudge(...b.dataset.nudge.split(',').map(Number)));
  $('#save-anchors').onclick = e => save(e.target,'/api/vod30/anchors',{t:state.t,pts:state.pts.map(p => [...p])});
  const svg = $('#overlay'); let drag = null;
  svg.onpointerdown = e => { const g = e.target.closest('[data-anchor]'); if (!g || state.busy) return; state.anchor = Number(g.dataset.anchor); drag = state.anchor; svg.setPointerCapture(e.pointerId); drawAnchors(); e.preventDefault(); };
  svg.onpointermove = e => { if (drag === null) return; const rect = svg.getBoundingClientRect(); state.pts[drag] = [Math.max(0,Math.min(w-1,Math.round((e.clientX-rect.left)/rect.width*w))),Math.max(0,Math.min(h-1,Math.round((e.clientY-rect.top)/rect.height*h)))]; markDirty(); drawAnchors(); };
  svg.onpointerup = svg.onpointercancel = () => { drag = null; }; imageErrors();
}
function drawAnchors() {
  $('#overlay').innerHTML = state.pts.map(([x,y],i) => `<g data-anchor="${i}" class="${state.anchor === i ? 'selected' : ''}"><circle cx="${x}" cy="${y}" r="12"></circle><text x="${x+18}" y="${y-16}">${i+1}</text></g>`).join('');
  $('#anchor-list').innerHTML = state.pts.map(([x,y],i) => `<button data-point="${i}" class="${state.anchor === i ? 'selected' : ''}"><span>${i+1}. ${anchorNames[i]}</span><span>${Math.round(x)}, ${Math.round(y)}</span></button>`).join('');
  root.querySelectorAll('[data-point]').forEach(b => b.onclick = () => { state.anchor = Number(b.dataset.point); drawAnchors(); });
}
function nudge(dx,dy) { if (state.busy) return; const p = state.pts[state.anchor]; p[0] = Math.max(0,Math.min(state.frameWidth-1,p[0]+dx)); p[1] = Math.max(0,Math.min(state.frameHeight-1,p[1]+dy)); markDirty(); drawAnchors(); }
function renderPlayers() {
  const windows = state.data.windows || [];
  if (!windows.length) { $('#content').innerHTML = '<div class="empty">No tracklet windows are available for this VOD.</div>'; return; }
  if (!windows.some(w => w.win === state.win)) state.win = windows[0].win;
  const [start,end] = state.win.split('-').map(Number); if (state.t < start || state.t > end) state.t = start;
  $('#content').innerHTML = timeToolbar(`<label>Track window <select id="track-window">${windows.map(w => `<option value="${esc(w.win)}" ${state.win === w.win ? 'selected' : ''}>${esc(w.win)} · ${(w.tracks || []).length} tracks</option>`).join('')}</select></label>`)+`<div id="identity-status" class="panel panel-body" role="status"><h3>Identity status</h3><p class="hint">Face bindings from enrolled regulars; manual seeds always override. 身份状态：来自已录入常客的人脸绑定；手动种子始终优先。</p><p id="identity-status-body" class="hint">Checking status…</p></div><div class="frame-layout"><section class="panel"><div class="panel-head"><h2>Player seed review</h2><span class="badge">Experimental</span></div><div id="player-frame"></div><div class="panel-body hint">Click a track box to select it. Predictions are experimental, not identity ground truth. Only the explicit seed buttons save labels.<p id="prediction-status"></p></div></section><section class="panel panel-body"><h3>Selected track</h3><div id="track-detail" class="hint">Loading tracks…</div><div id="track-list" class="anchor-list"></div><div class="actions"><button data-seed="A">Player A</button><button data-seed="B">Player B</button><button data-seed="ignore">Ignore</button><button data-seed="clear">Clear seed</button></div><p id="save-state" class="hint">Select a visible track first.</p><div class="rebuild"><h3>Identity rebuild</h3><p class="hint">Rebuild experimental assignments using saved seeds. Saving a seed alone does not rebuild predictions.</p><button id="rebuild">Rebuild assignments</button><button id="rebuild-refresh">Refresh status</button><p id="rebuild-status" class="hint" role="status">Checking status…</p></div></section></div>`;
  identityStatus();

  $('#track-window').onchange = e => { if (state.busy) { e.target.value = state.win; return; } state.win = e.target.value; const start = Number(state.win.split('-')[0]); if (Number.isFinite(start)) { state.t = start; $('#frame-time').value = start; } loadTracks(); };
  frameTimeAction(loadTracks);
  root.querySelectorAll('[data-seed]').forEach(b => b.onclick = () => { if (state.track === null) { notice('Select a visible track first.',true); return; } const body = {win:state.win,t:state.t,track_id:state.track,label:b.dataset.seed === 'clear' ? null : b.dataset.seed}; save(b,'/api/vod30/seeds',body,() => { loadTracks(); }); });
  $('#rebuild').onclick = async e => { const epoch = state.epoch; e.target.disabled = true; try { const data = await api('/api/vod30/rebuild',{}); if (epoch === state.epoch) showRebuild(data); } catch (error) { if (epoch === state.epoch) notice(`Rebuild failed: ${error.message}`,true); e.target.disabled = false; } };
  $('#rebuild-refresh').onclick = refreshRebuild; loadTracks(); refreshRebuild();
}
let trackRequest = 0;
async function loadTracks() {
  const epoch = state.epoch, request = ++trackRequest; state.track = null; $('#player-frame').innerHTML = '<div class="empty">Loading raw frame and tracks…</div>'; $('#track-list').innerHTML = ''; $('#track-detail').textContent = 'Loading tracks…';
  root.querySelectorAll('[data-seed]').forEach(b => b.disabled = true);
  try {
    const [data, tracklets] = await Promise.all([api(`/api/vod30/tracks?win=${enc(state.win)}&t=${state.t}`), api('/api/vod30/tracklets')]); if (epoch !== state.epoch || request !== trackRequest) return;
    state.data.predictions = tracklets.predictions;
    state.tracks = (data.tracks || []).map(track => ({...track,label:state.data.predictions?.map?.[`${track.id}:${state.win}`] || null})); state.t = data.t ?? state.t; state.seeds = (await api('/api/vod30/seeds')).seeds || {}; if (epoch !== state.epoch || request !== trackRequest) return;
    $('#player-frame').innerHTML = frameHTML();
    const img = $('#frame img'); img.onload = () => { if (!$('#overlay') || epoch !== state.epoch || request !== trackRequest) return; state.frameWidth = img.naturalWidth; state.frameHeight = img.naturalHeight; drawTracks(); };
    if (img.complete && img.naturalWidth) img.onload();
    $('#track-detail').textContent = state.tracks.length ? 'Select a track box or track below.' : 'No tracks at this time. Try a different frame within the window.'; drawTrackList(); imageErrors();
  } catch (error) { if (epoch === state.epoch && request === trackRequest) { notice(error.message,true); $('#player-frame').innerHTML = '<div class="empty">Frame/track request failed. Use Load frame to retry.</div>'; $('#track-detail').textContent = 'Tracks unavailable.'; } }
}
function selectTrack(id) { if (state.busy) return; state.track = id; drawTracks(); drawTrackList(); const track = state.tracks.find(t => t.id === id); const seed = Object.values(state.seeds || {}).find(s => s.win === state.win && String(s.track_id) === String(id)); $('#track-detail').textContent = `Track ${id} · prediction: ${track?.label || 'unassigned'} · saved seed: ${seed?.label || 'none'}`; $('#save-state').textContent = 'Choose an explicit seed label to save.'; root.querySelectorAll('[data-seed]').forEach(b => { b.disabled = false; b.classList.toggle('selected',b.dataset.seed === seed?.label); }); }
function drawTrackList() { if ($('#prediction-status')) $('#prediction-status').textContent = state.data.predictions?.stale ? `Predictions withheld: ${state.data.predictions.reason || 'Saved seeds or rebuild snapshot changed. Rebuild after explicitly labeling A and B.'}` : 'Predictions use the saved seed snapshot; they remain experimental.'; $('#track-list').innerHTML = state.tracks.map(t => `<button data-track-id="${esc(t.id)}" class="${state.track === t.id ? 'selected' : ''}">Track ${esc(t.id)} <span>${esc(t.label || '?')}</span></button>`).join(''); root.querySelectorAll('[data-track-id]').forEach(b => b.onclick = () => selectTrack(state.tracks.find(t => String(t.id) === b.dataset.trackId).id)); }
function drawTracks() { const svg = $('#overlay'); if (!svg) return; svg.setAttribute('viewBox',`0 0 ${state.frameWidth || 1920} ${state.frameHeight || 1080}`); svg.innerHTML = state.tracks.map((t,i) => { const [x1,y1,x2,y2] = t.box; return `<g data-track="${i}" class="${state.track === t.id ? 'selected' : ''}"><rect x="${x1}" y="${y1}" width="${Math.max(0,x2-x1)}" height="${Math.max(0,y2-y1)}"></rect><text x="${x1+4}" y="${Math.max(18,y1-7)}">${esc(t.id)} · ${esc(t.label || '?')}</text></g>`; }).join(''); svg.querySelectorAll('[data-track]').forEach(g => g.onclick = () => selectTrack(state.tracks[Number(g.dataset.track)].id)); }
function showRebuild(data) { if (state.mode !== 'players' || !$('#rebuild-status')) return; const status = data.status || 'unknown'; $('#rebuild-status').textContent = `Status: ${status}${data.error ? ` — ${data.error}` : ''}`; $('#rebuild').disabled = status === 'running'; clearTimeout(rebuildTimer); if (status === 'running') rebuildTimer = setTimeout(refreshRebuild,2500); }
async function refreshRebuild() { const epoch = state.epoch; try { const data = await api('/api/vod30/rebuild'); if (epoch !== state.epoch) return; showRebuild(data); if (data.status === 'completed') { const fresh = await api('/api/vod30/tracklets'); if (epoch !== state.epoch) return; state.data.predictions = fresh.predictions; if (state.tracks) { state.tracks.forEach(track => track.label = fresh.predictions?.map?.[`${track.id}:${state.win}`] || null); drawTracks(); drawTrackList(); if (state.track !== null) selectTrack(state.track); } } } catch (error) { if (epoch === state.epoch && $('#rebuild-status')) $('#rebuild-status').textContent = `Status unavailable: ${error.message}`; } }
// ---- Video timeline mode: local VOD, raw frame indexes, frozen-frame corrections ----
const BOX_LABELS = ['person','ball','cue','solid','stripe','eight'];
function clampFrame(n, meta) { if (!meta || !Number.isFinite(n)) return 0; return Math.max(0, Math.min(meta.frame_count - 1, Math.round(n))); }
function frameTime(meta, n) { return n / meta.fps; }
function frameFromTime(meta, t) { return clampFrame(t * meta.fps, meta); }
function timecode(t) { const value = Number(t); const tenths = Math.round((Number.isFinite(value) ? Math.max(0, value) : 0) * 10); const m = Math.floor(tenths / 600), seconds = ((tenths % 600) / 10).toFixed(1); return `${m}:${seconds.padStart(4, '0')}`; }
function markerLeft(event, meta) { const pct = (Number(event.t) || 0) / meta.duration * 100; return pct >= 0 && pct <= 100 ? pct : null; }
function ballLabel(label) { return ['ball','cue','solid','stripe','eight'].includes(label); }
function boxCenter(box) { return [(box.bbox[0] + box.bbox[2]) / 2, (box.bbox[1] + box.bbox[3]) / 2]; }
function normalizeBox(value, w, h) {
  if (!Array.isArray(value) || value.length !== 4 || value.some(v => !Number.isFinite(v))) return null;
  const x1 = Math.max(0, Math.min(w, Math.min(value[0], value[2]))), x2 = Math.max(0, Math.min(w, Math.max(value[0], value[2])));
  const y1 = Math.max(0, Math.min(h, Math.min(value[1], value[3]))), y2 = Math.max(0, Math.min(h, Math.max(value[1], value[3])));
  return x2 - x1 >= 1 && y2 - y1 >= 1 ? [Math.round(x1), Math.round(y1), Math.round(x2), Math.round(y2)] : null;
}
function displayBoxes(result) {
  const source = result?.correction ? 'manual corrections' : result?.inference ? 'inference' : 'none';
  const payload = result?.correction || result?.inference || {};
  return {source, boxes: (payload.boxes || []).map(b => ({label: b.label, bbox: b.bbox.slice(), score: b.score})), polygon: payload.table_polygon ? payload.table_polygon.map(p => [...p]) : null};
}
function renderTimeline() {
  const meta = state.vmeta;
  if (state.shotUrl) { URL.revokeObjectURL(state.shotUrl); state.shotUrl = null; }
  Object.assign(state, {frame: 0, fresult: null, boxes: [], polygon: null, sel: -1, tool: 'select', drag: null, scrubbing: false, inferRunning: false});
  $('#content').innerHTML = `<div class="toolbar"><span class="chip">LOCAL INGESTED VOD ONLY · NO LIVE SOURCES</span><span class="chip-group" role="group" aria-label="Overlays">${[['balls','Balls'],['pockets','Pockets'],['persons','Persons'],['identity','Identity']].map(([k, l]) => `<label class="overlay-toggle"><input type="checkbox" data-overlay="${k}" ${state.overlay[k] ? 'checked' : ''}> ${l}</label>`).join('')}</span><label>Jump to frame <input id="jump-frame" type="number" min="0" max="${meta.frame_count - 1}" value="0"></label><button id="jump-frame-go">Go</button><label>Jump to time (s) <input id="jump-time" type="number" min="0" step="0.01" value="0"></label><button id="jump-time-go">Go</button><span class="count">${esc(meta.fps.toFixed(3))} fps · ${meta.frame_count} frames · ${timecode(meta.duration)} · nominal CFR timestamps</span></div><div class="timeline-grid"><section class="panel"><div class="panel-head"><h2>Local VOD player</h2><span class="badge">/media/${esc(state.dataset)}/video</span></div><video id="vod" src="/media/${enc(state.dataset)}/video" preload="metadata" controls></video><div class="transport"><button id="play-toggle">▶ Play</button><button id="step-back">◀ −1 frame</button><button id="step-fwd">+1 frame ▶</button><button id="freeze-current" class="primary">Freeze player frame</button><span id="player-clock" class="hint"></span></div><div class="scrub-wrap"><div id="scrub-marks" class="scrub-marks" aria-label="Event markers">${(state.data.events || []).map(e => { const pct = markerLeft(e, meta); return pct === null ? '' : `<button class="scrub-mark ${esc(e.type)}" data-jump="${esc(e.t)}" title="#${esc(e.id)} ${esc(e.type)} at ${timecode(e.t)}" style="left:${pct}%"></button>`; }).join('')}</div><input id="scrub" type="range" min="0" max="${meta.frame_count - 1}" step="1" value="0" aria-label="Scrub decoded frames"></div><div class="panel-body hint">The scrubber and jumps address raw decoded frame indexes (nominal CFR time = frame ÷ fps; not VFR-exact). Ticks are event candidates — click to jump. Step buttons fetch exact decoded frames from the review server.</div></section><section class="panel"><div class="panel-head"><h2>Frozen frame inspector</h2><span class="badge" id="frame-badge">no frame loaded</span></div><div class="frame empty" id="t-frame">Pick a moment with the player or jump controls, then freeze it to inspect and correct.</div><div class="facts" id="frame-facts">FROZEN FRAME · nothing loaded yet</div></section><section class="panel panel-body"><h3>Frame inference</h3><div class="detector-row">${[['table','Table'],['person','Person'],['balls','Balls · SAM3 on CPU (slow)']].map(([k,l]) => `<label class="detector"><input type="checkbox" data-detector="${k}" ${state.detectors[k] ? 'checked' : ''}> ${l}</label>`).join('')}</div><div class="actions"><button id="run-inference" class="primary" disabled>Run inference on frozen frame</button></div><p id="infer-status" class="hint" role="status">Idle. Freeze a frame, choose detectors, then run.</p><p class="hint">Frame inference covers this single decoded frame only. It cannot detect shots or pots — event inference needs time windows and is out of scope here.</p><h3>Correction editor</h3><div class="actions"><button data-tool="select" class="selected">Select / move</button><button data-tool="draw">Draw box</button><label>New box label <select id="new-box-label">${BOX_LABELS.map(l => `<option>${l}</option>`).join('')}</select></label><label>Selected label <select id="box-label" disabled>${BOX_LABELS.map(l => `<option>${l}</option>`).join('')}</select></label><button id="delete-box" disabled>Delete selected</button></div><div class="actions"><button id="add-polygon">Add table polygon</button><button id="clear-polygon" disabled>Clear polygon</button></div><div class="actions"><button id="save-corrections" class="primary" disabled>Save corrections for this frame</button><span id="save-state" class="save-state">No frame loaded</span></div><p class="hint">Drag boxes or corner handles; arrow keys nudge the selected box (Shift = 10 px). Ball centers follow their box. Drag table polygon corners. Saving writes manual corrections for this exact frame; saved inference is never overwritten.</p></section></div>`;
  const video = $('#vod'), metaMax = meta.frame_count - 1;
  video.addEventListener('error', () => notice(`Local VOD ${state.dataset} could not be loaded. Open this workbench through the review server with the dataset ingested.`, true));
  video.addEventListener('timeupdate', () => { if (!state.scrubbing && $('#scrub')) $('#scrub').value = clampFrame(video.currentTime * meta.fps, meta); updatePlayerClock(); });
  video.addEventListener('play', () => { const b = $('#play-toggle'); if (b) b.textContent = '❚❚ Pause'; });
  video.addEventListener('pause', () => { const b = $('#play-toggle'); if (b) b.textContent = '▶ Play'; });
  $('#play-toggle').onclick = () => { video.paused ? video.play() : video.pause(); };
  const scrub = $('#scrub');
  scrub.addEventListener('input', () => { state.scrubbing = true; video.currentTime = frameTime(meta, Number(scrub.value) || 0); updatePlayerClock(); });
  scrub.addEventListener('change', () => { state.scrubbing = false; });
  $('#scrub-marks').onclick = e => { const mark = e.target.closest('[data-jump]'); if (mark && canLeave()) jumpToTime(Number(mark.dataset.jump)); };
  $('#step-back').onclick = () => stepFrame(-1);
  $('#step-fwd').onclick = () => stepFrame(1);
  $('#freeze-current').onclick = () => { if (canLeave()) { const n = clampFrame(video.currentTime * meta.fps, meta); video.currentTime = frameTime(meta, n); loadFrame(n); } };
  $('#content').onchange = e => { const k = e.target.dataset && e.target.dataset.overlay; if (k) { state.overlay[k] = e.target.checked; drawTimelineOverlay(); } };
  $('#jump-frame-go').onclick = () => { const n = clampFrame(Number($('#jump-frame').value), meta); if ($('#jump-frame').value === '' || !Number.isFinite(Number($('#jump-frame').value))) { notice('Enter a frame index.', true); return; } if (canLeave()) { video.currentTime = frameTime(meta, n); loadFrame(n); } };
  $('#jump-time-go').onclick = () => { const t = Number($('#jump-time').value); if ($('#jump-time').value === '' || !Number.isFinite(t) || t < 0) { notice('Enter a non-negative time in seconds.', true); return; } if (canLeave()) jumpToTime(t); };
  root.querySelectorAll('[data-detector]').forEach(c => c.onchange = () => { state.detectors[c.dataset.detector] = c.checked; });
  $('#run-inference').onclick = runInference;
  root.querySelectorAll('[data-tool]').forEach(b => b.onclick = () => setTool(b.dataset.tool));
  $('#new-box-label').onchange = () => setTool('draw');
  $('#box-label').onchange = () => { if (state.sel >= 0 && state.boxes[state.sel]) { state.boxes[state.sel].label = $('#box-label').value; markDirty(); drawTimelineOverlay(); } };
  $('#delete-box').onclick = () => { if (state.sel >= 0) { state.boxes.splice(state.sel, 1); state.sel = -1; markDirty(); syncEditor(); drawTimelineOverlay(); } };
  $('#add-polygon').onclick = () => { const w = state.frameWidth, h = state.frameHeight; state.polygon = [[Math.round(w*.1),Math.round(h*.1)],[Math.round(w*.9),Math.round(h*.1)],[Math.round(w*.9),Math.round(h*.9)],[Math.round(w*.1),Math.round(h*.9)]]; markDirty(); syncEditor(); drawTimelineOverlay(); };
  $('#clear-polygon').onclick = () => { if (state.polygon) { state.polygon = null; markDirty(); syncEditor(); drawTimelineOverlay(); } };
  $('#save-corrections').onclick = e => saveCorrections(e.currentTarget);
  syncEditor(); syncTimelineButtons(); updatePlayerClock();
}
function updatePlayerClock() { const el = $('#player-clock'), video = $('#vod'); if (el && video && state.vmeta) el.textContent = `${timecode(video.currentTime)} · ≈frame ${clampFrame(video.currentTime * state.vmeta.fps, state.vmeta)}`; }
function jumpToTime(t) { const meta = state.vmeta; if (!meta) return; const n = frameFromTime(meta, t); $('#vod').currentTime = frameTime(meta, n); $('#jump-time').value = frameTime(meta, n).toFixed(2); $('#jump-frame').value = n; loadFrame(n); }
function stepFrame(delta) {
  if (state.busy || !state.vmeta || !canLeave()) return;
  const video = $('#vod');
  const base = state.fresult ? state.frame : clampFrame(video.currentTime * state.vmeta.fps, state.vmeta);
  if (state.fresult) video.currentTime = frameTime(state.vmeta, clampFrame(base + delta, state.vmeta));
  loadFrame(base + delta);
}
async function fetchFrame(dataset, n) {
  const response = await fetch(`/api/frame?dataset=${enc(dataset)}&frame=${n}`);
  if (!response.ok) { let message = `Frame request failed (${response.status})`; try { message = (await response.json()).error || message; } catch {} throw new Error(message); }
  return {url: URL.createObjectURL(await response.blob()), frame: Number(response.headers.get('X-Frame-Index')), t: Number(response.headers.get('X-Timestamp-Seconds')), kind: response.headers.get('X-Timestamp-Kind') || '', w: Number(response.headers.get('X-Frame-Width')), h: Number(response.headers.get('X-Frame-Height'))};
}
async function loadFrame(n) {
  if (state.busy || !state.vmeta) return;
  const meta = state.vmeta; n = clampFrame(n, meta);
  const epoch = state.epoch, request = ++state.frameReq;
  state.busy = true; syncTimelineButtons();
  const badge = $('#frame-badge'); if (badge) badge.textContent = `decoding frame ${n}…`;
  try {
    const [shot, result] = await Promise.all([fetchFrame(state.dataset, n), api(`/api/frame-result?dataset=${enc(state.dataset)}&frame=${n}`)]);
    if (epoch !== state.epoch || request !== state.frameReq) { URL.revokeObjectURL(shot.url); return; }
    if (state.shotUrl) URL.revokeObjectURL(state.shotUrl);
    state.shotUrl = shot.url; state.frame = shot.frame; state.fresult = result;
    state.dirty = false; applyFrameResult(); renderFrozen(shot); notice('');
    fetch(`/api/unified?dataset=${enc(state.dataset)}&frame=${shot.frame}`).then(r => r.ok ? r.json() : Promise.reject(Error(`HTTP ${r.status}`))).then(data => { if (epoch === state.epoch && request === state.frameReq) { state.unified = data; drawTimelineOverlay(); } }).catch(() => { if (epoch === state.epoch && request === state.frameReq) { state.unified = null; } });
  } catch (error) { if (epoch === state.epoch && request === state.frameReq) { notice(`Frame load failed: ${error.message}`, true); if (badge) badge.textContent = 'frame load failed'; } }
  finally { if (epoch === state.epoch && request === state.frameReq) { state.busy = false; syncEditor(); syncTimelineButtons(); } }
}
function applyFrameResult() {
  const display = displayBoxes(state.fresult);
  state.boxes = display.boxes; state.polygon = display.polygon; state.sel = -1;
  const saved = $('#save-state');
  if (saved) saved.textContent = state.fresult.correction ? 'Corrections saved for this frame' : state.fresult.inference ? 'Inference loaded — edit and save corrections' : 'No saved results for this frame yet';
  syncEditor(); syncTimelineButtons();
}
function renderFrozen(shot) {
  const holder = $('#t-frame'); if (!holder) return;
  holder.classList.remove('empty');
  holder.innerHTML = `<img id="t-img" src="${shot.url}" alt="Raw decoded frame ${shot.frame}"><svg id="t-overlay" role="group" aria-label="Frame overlays" viewBox="0 0 ${shot.w} ${shot.h}"></svg>`;
  state.frameWidth = shot.w; state.frameHeight = shot.h;
  $('#frame-badge').textContent = `frame ${shot.frame} · ${timecode(shot.t)} · ${state.dataset}`;
  const display = displayBoxes(state.fresult);
  $('#frame-facts').textContent = `RAW DECODED FRAME · ${state.dataset} · frame ${shot.frame} · nominal ${timecode(shot.t)}s (${shot.kind || 'nominal_cfr'}) · OVERLAYS: ${display.source}`;
  const img = $('#t-img');
  img.onload = () => { if ($('#t-overlay')) drawTimelineOverlay(); };
  if (img.complete && img.naturalWidth) img.onload();
  const svg = $('#t-overlay');
  svg.onpointerdown = overlayPointerDown; svg.onpointermove = overlayPointerMove; svg.onpointerup = svg.onpointercancel = overlayPointerUp;
  imageErrors();
}
function drawTimelineOverlay() {
  const svg = $('#t-overlay'); if (!svg) return;
  const boxes = state.boxes.map((box, i) => {
    const [x1, y1, x2, y2] = box.bbox, center = boxCenter(box);
    const handles = i === state.sel ? [[x1,y1],[x2,y1],[x2,y2],[x1,y2]].map(([hx,hy],c) => `<rect class="handle" data-handle="${c}" x="${hx-7}" y="${hy-7}" width="14" height="14"></rect>`).join('') : '';
    return `<g data-box="${i}" class="t-box${i === state.sel ? ' selected' : ''}"><rect x="${x1}" y="${y1}" width="${x2-x1}" height="${y2-y1}"></rect>${ballLabel(box.label) ? `<circle class="center-dot" cx="${center[0]}" cy="${center[1]}" r="4"></circle>` : ''}<text x="${x1+4}" y="${Math.max(16,y1-6)}">${esc(box.label)}${box.score != null ? ` ${Number(box.score).toFixed(2)}` : ''}</text>${handles}</g>`;
  }).join('');
  const poly = state.polygon ? `<polygon class="t-poly" points="${state.polygon.map(p => p.join(',')).join(' ')}"></polygon>${state.polygon.map((p,i) => `<circle class="handle" data-poly="${i}" cx="${p[0]}" cy="${p[1]}" r="9"></circle>`).join('')}` : '';
  const preview = state.drag && state.drag.kind === 'draw' ? `<rect class="draw-preview" x="${Math.min(state.drag.x1,state.drag.x2)}" y="${Math.min(state.drag.y1,state.drag.y2)}" width="${Math.abs(state.drag.x2-state.drag.x1)}" height="${Math.abs(state.drag.y2-state.drag.y1)}"></rect>` : '';
  const u = state.unified, ov = state.overlay || {};
  const layers = [];
  if (u) {
    const H = u.height || 720;
    if (ov.pockets && u.pockets) layers.push(u.pockets.map(pk => `<g class="u-pocket"><circle cx="${pk.cx}" cy="${pk.cy}" r="12" fill="none" stroke="var(--brass)" stroke-width="2.5"></circle><text x="${pk.cx}" y="${pk.cy + 26}" text-anchor="middle" font-size="13">${esc(pk.name)}</text></g>`).join(''));
    if (ov.persons && u.persons) layers.push(u.persons.map(per => { const [x1, y1, x2, y2] = per.bbox; const chip = ov.identity && per.player_id ? `<text x="${x1}" y="${Math.max(14, y1 - 6)}" font-size="15" fill="#8fd6a8">${esc(per.player_id)}</text>` : (ov.identity && per.cluster_id ? `<text x="${x1}" y="${Math.max(14, y1 - 6)}" font-size="13" fill="var(--ink-dim)">track ${per.track_id}</text>` : ''); return `<g class="u-person" data-track="${per.track_id}"><rect x="${x1}" y="${y1}" width="${x2 - x1}" height="${y2 - y1}" fill="none" stroke="#8fd6a8" stroke-width="2"></rect>${chip}</g>`; }).join(''));
    if (ov.balls && u.balls) layers.push(u.balls.map(b => `<g class="u-ball" data-cx="${b.cx}" data-cy="${b.cy}" data-r="${b.r}" data-color="${esc(b.color)}"><circle cx="${b.cx}" cy="${b.cy}" r="${Math.max(9, b.r)}" fill="none" stroke="var(--brass-hi)" stroke-width="2"></circle><circle cx="${b.cx}" cy="${b.cy}" r="2" fill="var(--brass-hi)"></circle></g>`).join(''));
    if (u.table_corners) layers.push(`<polygon class="u-cloth" points="${u.table_corners.map(p => p.join(',')).join(' ')}" fill="none"></polygon>`);
    // Pot pulse: events within ±2s highlight the nearest pocket by name.
    if (ov.pockets && u.events && u.pockets) { for (const e of u.events) { if (e.type !== 'pot') continue; const name = String(e.nearest_pocket || '').split(/[\s(]/)[0]; const pk = u.pockets.find(pk => pk.name === name); if (pk) layers.push(`<circle class="u-pot-pulse" cx="${pk.cx}" cy="${pk.cy}" r="18" fill="none" stroke="var(--red)" stroke-width="3"></circle>`); } }
  }
  svg.innerHTML = layers.join('') + poly + boxes + preview;
  svg.querySelectorAll('g[data-box]').forEach(g => g.onclick = () => { if (state.tool === 'select' && state.sel !== Number(g.dataset.box)) { state.sel = Number(g.dataset.box); syncEditor(); drawTimelineOverlay(); } });
  svg.querySelectorAll('g.u-ball').forEach(g => g.onclick = () => { const cx = Number(g.dataset.cx), cy = Number(g.dataset.cy), r = Number(g.dataset.r); const hit = state.boxes.findIndex(box => { const [x1, y1, x2, y2] = box.bbox; return cx >= x1 - 8 && cx <= x2 + 8 && cy >= y1 - 8 && cy <= y2 + 8 && box.label; }); if (hit >= 0) { state.sel = hit; syncEditor(); drawTimelineOverlay(); return; } state.boxes.push({ label: 'ball', bbox: [Math.round(cx - r), Math.round(cy - r), Math.round(cx + r), Math.round(cy + r)] }); state.sel = state.boxes.length - 1; markDirty(); syncEditor(); drawTimelineOverlay(); });
  svg.querySelectorAll('g.u-person').forEach(g => g.onclick = () => { const track = Number(g.dataset.track); const per = (state.unified?.persons || []).find(pp => pp.track_id === track); if (!per) return; if (per.player_id) { notice(`${per.player_id} · cluster ${String(per.cluster_id).slice(0, 6)}`); } else if (per.cluster_id) { notice(`Track ${track}: no identity bound yet. Use seeds in Player identities.`); } });
}
function svgPoint(event) {
  const rect = $('#t-overlay').getBoundingClientRect();
  return [Math.round(Math.max(0, Math.min(state.frameWidth, (event.clientX - rect.left) / rect.width * state.frameWidth))), Math.round(Math.max(0, Math.min(state.frameHeight, (event.clientY - rect.top) / rect.height * state.frameHeight)))];
}
function overlayPointerDown(event) {
  if (state.busy) return;
  const svg = $('#t-overlay'), handle = event.target.closest('[data-handle]'), poly = event.target.closest('[data-poly]'), box = event.target.closest('[data-box]');
  if (handle && state.sel >= 0) { event.preventDefault(); svg.setPointerCapture(event.pointerId); state.drag = {kind:'handle', box: state.sel, corner: Number(handle.dataset.handle)}; return; }
  if (poly) { event.preventDefault(); svg.setPointerCapture(event.pointerId); state.drag = {kind:'poly', index: Number(poly.dataset.poly)}; return; }
  if (box) { state.sel = Number(box.dataset.box); syncEditor(); drawTimelineOverlay(); if (state.tool === 'draw') return; event.preventDefault(); svg.setPointerCapture(event.pointerId); const [x,y] = svgPoint(event); state.drag = {kind:'move', box: state.sel, x, y, orig: state.boxes[state.sel].bbox.slice()}; return; }
  if (state.tool === 'draw') { event.preventDefault(); svg.setPointerCapture(event.pointerId); const [x,y] = svgPoint(event); state.drag = {kind:'draw', x1:x, y1:y, x2:x, y2:y}; drawTimelineOverlay(); return; }
  if (state.sel !== -1) { state.sel = -1; syncEditor(); drawTimelineOverlay(); }
}
function overlayPointerMove(event) {
  const drag = state.drag; if (!drag || state.busy) return;
  const [x, y] = svgPoint(event);
  if (drag.kind === 'move') {
    const box = state.boxes[drag.box], w = drag.orig[2] - drag.orig[0], h = drag.orig[3] - drag.orig[1];
    const nx1 = Math.max(0, Math.min(state.frameWidth - w, drag.orig[0] + x - drag.x)), ny1 = Math.max(0, Math.min(state.frameHeight - h, drag.orig[1] + y - drag.y));
    box.bbox = [nx1, ny1, nx1 + w, ny1 + h]; markDirty(); drawTimelineOverlay();
  } else if (drag.kind === 'handle') {
    const box = state.boxes[drag.box], next = box.bbox.slice();
    next[[0,2,2,0][drag.corner]] = x; next[[1,1,3,3][drag.corner]] = y;
    box.bbox = normalizeBox(next, state.frameWidth, state.frameHeight) || box.bbox;
    markDirty(); drawTimelineOverlay();
  } else if (drag.kind === 'poly') { state.polygon[drag.index] = [x, y]; markDirty(); drawTimelineOverlay();
  } else if (drag.kind === 'draw') { drag.x2 = x; drag.y2 = y; drawTimelineOverlay(); }
}
function overlayPointerUp() {
  const drag = state.drag; if (!drag) return;
  state.drag = null;
  if (drag.kind === 'draw') {
    const bbox = normalizeBox([drag.x1, drag.y1, drag.x2, drag.y2], state.frameWidth, state.frameHeight);
    if (bbox) { state.boxes.push({label: $('#new-box-label')?.value || 'ball', bbox}); state.sel = state.boxes.length - 1; setTool('select'); markDirty(); }
  }
  syncEditor(); drawTimelineOverlay();
}
function nudgeBox(dx, dy) {
  if (state.busy || state.sel < 0 || !state.boxes[state.sel]) return;
  const box = state.boxes[state.sel], moved = normalizeBox([box.bbox[0]+dx, box.bbox[1]+dy, box.bbox[2]+dx, box.bbox[3]+dy], state.frameWidth, state.frameHeight);
  if (moved) { box.bbox = moved; markDirty(); drawTimelineOverlay(); }
}
function setTool(tool) {
  state.tool = tool;
  root.querySelectorAll('[data-tool]').forEach(b => b.classList.toggle('selected', b.dataset.tool === tool));
}
function syncEditor() {
  const has = state.sel >= 0 && state.boxes[state.sel];
  const label = $('#box-label'), remove = $('#delete-box'), clearPoly = $('#clear-polygon'), save = $('#save-corrections');
  if (label) { label.disabled = !has; if (has) label.value = state.boxes[state.sel].label; }
  if (remove) remove.disabled = !has;
  if (clearPoly) clearPoly.disabled = !state.polygon;
  if (save) save.disabled = state.busy || !state.fresult;
  const addPoly = $('#add-polygon'); if (addPoly) addPoly.disabled = state.busy || !state.fresult;
}
function syncTimelineButtons() {
  ['#step-back','#step-fwd','#freeze-current'].forEach(sel => { const el = $(sel); if (el) el.disabled = state.busy; });
  const run = $('#run-inference'); if (run) run.disabled = state.busy || state.inferRunning || !state.fresult;
}
function setInferRunning(running) { state.inferRunning = running; syncTimelineButtons(); }
function setInferStatus(text) { const el = $('#infer-status'); if (el) el.textContent = text; }
async function runInference() {
  if (state.busy || !state.fresult) { if (!state.fresult) notice('Freeze a frame before running inference.', true); return; }
  const detectors = Object.keys(state.detectors).filter(k => state.detectors[k]);
  if (!detectors.length) { notice('Choose at least one detector (table, person, balls).', true); return; }
  const frame = state.frame, epoch = state.epoch;
  setInferRunning(true); setInferStatus(`Starting inference on frame ${frame} (${detectors.join(', ')})…`);
  try {
    const job = await api('/api/inference', {dataset: state.dataset, frame_index: frame, detectors});
    if (epoch !== state.epoch) return;
    setInferStatus(`Inference running for frame ${job.frame_index}: ${job.stage || 'queued'}…`);
    pollInference(epoch, job.frame_index);
  } catch (error) {
    if (epoch === state.epoch) { setInferRunning(false); setInferStatus('Idle.'); notice(`Inference failed to start: ${error.message}`, true); }
  }
}
function pollInference(epoch, frame) {
  clearTimeout(state.inferTimer);
  state.inferTimer = setTimeout(async () => {
    try {
      const job = await api(`/api/inference?dataset=${enc(state.dataset)}`);
      if (epoch !== state.epoch) return;
      if (job.status === 'running') { setInferStatus(`Inference running for frame ${job.frame_index}: ${job.stage || ''}…`); pollInference(epoch, frame); return; }
      setInferRunning(false);
      if (job.status === 'failed') { setInferStatus('Inference failed.'); notice(`Frame inference failed: ${job.error || 'unknown error'}`, true); return; }
      setInferStatus(`Inference completed for frame ${job.frame_index}.`);
      if (job.status === 'completed' && job.result && job.frame_index === frame && state.frame === frame) {
        if (state.fresult) state.fresult.inference = job.result;
        if (!state.dirty && !state.fresult?.correction) applyFrameResult();
        drawTimelineOverlay();
        updateOverlayFacts(displayBoxes(state.fresult).source);
        notice('Inference overlays updated for the frozen frame.');
      } else if (job.status === 'completed') notice(`Inference for frame ${job.frame_index} finished; freeze that frame to see its overlays.`);
    } catch (error) { if (epoch === state.epoch) { setInferRunning(false); setInferStatus('Status check failed.'); notice(`Inference status error: ${error.message}`, true); } }
  }, 1500);
}
async function saveCorrections(button) {
  if (state.busy || !state.fresult) return;
  const invalid = state.boxes.find(box => !normalizeBox(box.bbox, state.frameWidth, state.frameHeight));
  if (invalid) { notice('A box has invalid coordinates; fix or delete it before saving.', true); return; }
  const body = {dataset: state.dataset, frame_index: state.frame, boxes: state.boxes.map(box => ({label: box.label, bbox: box.bbox})), table_polygon: state.polygon ? state.polygon.map(p => [p[0], p[1]]) : null};
  state.busy = true; syncTimelineButtons(); button.disabled = true; const label = button.textContent; const savedLabel = Object.keys(editorCopy).find(key => editorCopy[key] === label) || label; button.textContent = text('Saving…');
  const fields = [...root.querySelectorAll('.timeline-grid button, .timeline-grid select')].filter(el => !el.disabled); fields.forEach(el => el.disabled = true);
  try {
    const data = await api('/api/frame-correction', body);
    state.fresult.correction = data.correction;
    applyFrameResult(); drawTimelineOverlay();
    state.dirty = false; notice(`Corrections saved for frame ${state.frame}.`);
    updateOverlayFacts('manual corrections');
  } catch (error) { notice(`Save failed: ${error.message}. Your edits remain on screen; retry when ready.`, true); }
  finally { state.busy = false; fields.forEach(el => el.disabled = false); button.disabled = false; button.textContent = text(savedLabel); syncEditor(); syncTimelineButtons(); }
}
function bindControls() {
root.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => switchMode(b.dataset.mode));
$('#dataset').onchange = e => { if (!canLeave()) { e.target.value = state.dataset; return; } state.dataset = e.target.value; loadMode(); };
root.tabIndex = -1;
root.addEventListener('keydown', onKeydown);
root.addEventListener('pointerdown', e => { if (active && !e.target.closest('input,textarea,select,button,a,video,[contenteditable="true"]')) root.focus({preventScroll:true}); });
for (const lang of ['en','zh']) $(`#lang-${lang}`).onclick = () => setAppearance(lang, root.dataset.theme);
for (const theme of ['dark','light']) $(`#theme-${theme}`).onclick = () => setAppearance(root.lang, theme);
}
window.addEventListener('beforeunload',e => { if (state.dirty || state.busy) { e.preventDefault(); e.returnValue = ''; } });
function onKeydown(e) { if (!active || e.ctrlKey || e.metaKey || e.altKey || e.target.closest('input,textarea,select,button,[contenteditable="true"]')) return;
  if (state.mode === 'timeline') { if (state.busy || !$('#t-overlay')) return; if (e.key === ',' || e.key === '.') { e.preventDefault(); stepFrame(e.key === ',' ? -1 : 1); return; } if (state.sel < 0) return; const delta = {ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key]; if (delta) { e.preventDefault(); nudgeBox(...delta.map(v => v * (e.shiftKey ? 10 : 1))); } return; }
  if (state.mode !== 'calibration' || !$('#anchor-list') || state.busy) return; const delta = {ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key]; if (delta) { e.preventDefault(); nudge(...delta.map(v => v*(e.shiftKey ? 10 : 1))); } }
async function init() { try { const data = await api('/api/datasets'); if (!data.datasets?.length) throw new Error('No VOD datasets are configured.'); state.sets = data.ball_sets || []; state.set = state.sets[0]?.id || 'unlabeled_crops'; state.dataset = data.datasets.some(d => d.id === 'vod30') ? 'vod30' : data.datasets[0].id; $('#dataset').innerHTML = data.datasets.map(d => `<option value="${esc(d.id)}" ${d.id === state.dataset ? 'selected' : ''}>${esc(d.label || d.id)}</option>`).join(''); $('#dataset').disabled = false; initialized = true; await loadMode(); } catch (error) { notice(error.message,true); $('#content').innerHTML = '<div class="empty">The review API is unavailable.<br>Use the project review server, not a file:// URL.<br><button id="retry-init">Retry connection</button></div>'; $('#content').setAttribute('aria-busy','false'); $('#retry-init').onclick = init; } }
function switchMode(mode) {
  if (!Object.hasOwn(modes, mode)) return false;
  if (mode === state.mode) return true;
  if (!canLeave()) return false;
  state.mode = mode;
  if (initialized) loadMode();
  return true;
}
function mount(host) {
  if (root) return root === host ? mounting : false;
  if (!host || host.id !== 'review-root') return false;
  root = host;
  bindControls();
  let lang = 'en', theme = 'dark';
  try { lang = localStorage.getItem('corner-pocket-lang') || lang; theme = localStorage.getItem('corner-pocket-theme') || theme; } catch (_) {}
  setAppearance(lang, theme);
  mounting = init();
  return mounting;
}
function activate(mode = state.mode) {
  if (!root || !switchMode(mode)) return false;
  active = true;
  return true;
}
function deactivate() {
  active = false;
  root?.querySelectorAll('video').forEach(video => video.pause());
}
const zhCopy = {
  tagline:'复核工作台 · 本地录像', feed:'本地复核',
  'nav-events':'事件复核', 'meta-events':'击球 · 入袋', 'nav-balls':'球号标注', 'meta-balls':'母球 · 1–15',
  'nav-calibration':'球桌标定', 'meta-calibration':'六个袋口', 'nav-players':'选手身份', 'meta-players':'A · B · 忽略',
  'nav-timeline':'统一视图', 'meta-timeline':'逐帧 · 推理', 'strip-label':'人在回路',
  strip:'模型候选 · 人工判定 · 未经验证不宣称精度', eyebrow:'复核台', stamp:'检查 · 标注<br><strong>核验</strong>',
  'foot-left':'本地数据 · 显式保存', 'foot-right':'复核结论在核验前不是真值。'
};
// Only UI-owned copy is eligible: never walk notes, source facts, or raw data.
const editorCopy = {
  'Event review':'事件复核', 'Inspect shot and pot candidates against their source evidence.':'对照原始证据检查击球和入袋候选。',
  'Ball labels':'球号标注', 'Resolve crop identities. Cue is 0; numbered balls are 1–15.':'确认裁剪图中的球号。母球为 0，目标球为 1–15。',
  'Table calibration':'球桌标定', 'Place six pocket anchors on the original, unwarped video frame.':'在未经变换的原始视频帧上放置六个袋口锚点。',
  'Player identities':'选手身份', 'Review track boxes and explicitly seed player A, player B, or ignore.':'检查轨迹框并明确标注选手 A、选手 B 或忽略。',
  'Video timeline':'视频时间轴', 'Scrub the local VOD, freeze exact decoded frames, run frame detectors, and correct boxes.':'浏览本地录像、冻结精确解码帧、运行检测器并修正标注框。',
  'Queue':'队列', 'All candidates':'全部候选', 'Shots':'击球', 'Pots':'入袋', 'Unreviewed':'未复核',
  'No events in this queue.':'此队列没有事件。', 'Select a candidate.':'选择一个候选。', 'Review decision':'复核判定', 'Verdict':'判定',
  'Choose a verdict':'选择判定', 'correct':'正确', 'wrong':'错误', 'unsure':'不确定', 'Shooter (human label)':'击球者（人工标注）',
  'Not assigned':'未分配', 'Player A':'选手 A', 'Player B':'选手 B', 'Unknown':'未知', 'Evidence / review note':'证据 / 复核备注',
  'What does the source actually show?':'原始资料实际显示了什么？', 'Save review':'保存复核', 'Next candidate →':'下一个候选 →',
  'Saved review':'已保存复核', 'Not reviewed':'未复核', 'Unsaved changes':'未保存的更改', 'Saved':'已保存', 'Saving…':'保存中…',
  'Loading review data…':'正在加载复核数据…', 'Saved to the review dataset.':'已保存到复核数据集。', 'Discard unsaved changes?':'放弃未保存的更改？',
  'Enter a non-negative time in seconds.':'请输入非负的秒数。', 'Frame time (seconds)':'帧时间（秒）', 'Load frame':'加载帧',
  'Six-pocket anchors':'六个袋口锚点', 'Saved anchors':'已保存锚点', 'Unsaved suggestion':'未保存的建议', 'Save anchors':'保存锚点',
  'Top left':'左上', 'Top right':'右上', 'Bottom right':'右下', 'Bottom left':'左下', 'Left side':'左侧', 'Right side':'右侧',
  'Previous':'上一个', 'Next':'下一个', '← Previous':'← 上一个', 'Next →':'下一个 →', 'Ignore':'忽略', 'Save identity':'保存身份',
  'Play':'播放', 'Pause':'暂停', 'Playing':'播放中', 'Paused':'已暂停', 'Loading…':'加载中…', 'Preview paused':'预览已暂停', 'Preview unavailable':'预览不可用',
  'Select':'选择', 'Add person':'添加人物', 'Add ball':'添加球', 'Delete selected':'删除所选', 'No box selected':'未选择标注框',
  'Table':'球桌', 'Person':'人物', 'Balls':'球', 'Freeze frame':'冻结帧', 'Run detectors':'运行检测器', 'Running inference…':'正在推理…',
  'Save corrections':'保存修正', 'Corrections saved for this frame':'此帧修正已保存', 'Inference loaded — edit and save corrections':'推理已加载 — 编辑并保存修正',
  'No saved results for this frame yet':'此帧暂无保存结果', 'Unsaved manual corrections':'未保存的人工修正',
  'Source video unavailable':'原始视频不可用', 'Preview stream unavailable. Frame-by-frame review still works.':'预览流不可用。仍可逐帧复核。'
};
Object.assign(editorCopy, {
  'Frame unavailable. Choose another time or retry loading.':'帧不可用。请选择其他时间或重新加载。',
  'Calibration and player seed review are available for the 30-minute VOD only.':'球桌标定和选手种子复核仅适用于 30 分钟录像。', 'Select the 30-minute dataset above.':'请在上方选择 30 分钟数据集。',
  'Could not load this workspace.':'无法加载此工作区。', 'Retry loading':'重新加载', 'Select another queue to continue.':'请选择其他队列继续。',
  'RAW SOURCE FRAME · No original evidence image supplied':'原始源帧 · 未提供原始证据图像', 'CANDIDATE · NOT VALIDATED':'候选 · 未验证',
  'Crop set':'裁剪图集', 'All crops':'全部裁剪图', 'Unlabeled':'未标注', 'No crops in this queue.':'此队列没有裁剪图。', 'Identify the ball':'识别球号', 'Human label':'人工标注', 'Clear label':'清除标注',
  'Each label button saves immediately. Unknown is a saved decision; clear removes the label.':'点击标注按钮立即保存。“未知”也是保存的判定；“清除”会移除标注。', '← Previous crop':'← 上一张裁剪图', 'Next crop →':'下一张裁剪图 →',
  'RAW FRAME · VOD30':'原始帧 · VOD30', 'Anchor positions':'锚点位置', 'Save six anchors':'保存六个锚点',
  'Drag an anchor, or select one and nudge with the controls. Arrow keys move the selected anchor by 1 pixel; Shift moves 10. Coordinates refer to the raw source frame.':'拖动锚点，或选中后使用控件微调。方向键移动 1 像素，按住 Shift 移动 10 像素。坐标基于原始源帧。',
  'Saving stores anchor annotations. It does not fit a calibration or rerun detection.':'保存仅存储锚点标注，不会拟合标定或重新运行检测。',
  'No tracklet windows are available for this VOD.':'此录像没有可用的轨迹窗口。', 'Track window':'轨迹窗口', 'Player seed review':'选手种子复核', 'Experimental':'实验性',
  'Click a track box to select it. Predictions are experimental, not identity ground truth. Only the explicit seed buttons save labels.':'点击轨迹框进行选择。预测属于实验结果，并非身份真值。只有明确点击种子按钮才会保存标注。',
  'Selected track':'所选轨迹', 'Loading tracks…':'正在加载轨迹…', 'Clear seed':'清除种子', 'Select a visible track first.':'请先选择可见的轨迹。',
  'Identity rebuild':'身份重建', 'Run rebuild':'运行重建', 'Refresh status':'刷新状态', 'Loading raw frame and tracks…':'正在加载原始帧和轨迹…',
  'Frame/track request failed. Use Load frame to retry.':'帧 / 轨迹请求失败。请点击“加载帧”重试。', 'Select a track box or track below.':'选择轨迹框或下方轨迹。', 'No tracks at this time. Try a different frame within the window.':'此时刻没有轨迹。请尝试窗口中的其他帧。', 'Tracks unavailable.':'轨迹不可用。',
  'LOCAL INGESTED VOD ONLY · NO LIVE SOURCES':'仅限本地导入录像 · 无直播源', 'Jump to frame':'跳转到帧', 'Jump to time (s)':'跳转到时间（秒）', 'Go':'跳转', 'Local VOD player':'本地录像播放器', '▶ Play':'▶ 播放', '❚❚ Pause':'❚❚ 暂停', '◀ −1 frame':'◀ 前一帧', '+1 frame ▶':'后一帧 ▶', 'Freeze player frame':'冻结播放器帧',
  'Frozen frame + overlays':'冻结帧与叠加层', 'Loading frame…':'正在加载帧…', 'Overlay layers':'叠加图层', 'Show table':'显示球桌', 'Show persons':'显示人物', 'Show balls':'显示球',
  'Inference':'推理', 'Table model':'球桌模型', 'Person model':'人物模型', 'Ball model (optional)':'球模型（可选）', 'Auto-run after scrub':'拖动后自动运行', 'Run inference on frame':'对此帧运行推理',
  'The scrubber and jumps address raw decoded frame indexes (nominal CFR time = frame ÷ fps; not VFR-exact). Ticks are event candidates — click to jump. Step buttons fetch exact decoded frames from the review server.':'拖动条和跳转使用原始解码帧索引（名义固定帧率时间 = 帧 ÷ fps，并非精确可变帧率时间）。刻度为事件候选，点击可跳转。步进按钮从复核服务器获取精确解码帧。',
  'Infer results and manual corrections are saved separately. Inference never overwrites your correction file.':'推理结果和人工修正分别保存。推理不会覆盖修正文件。', 'Correction tools':'修正工具', 'Add cue':'添加母球', 'Selected box':'所选标注框', 'Label':'标注', 'Ball 1–15':'球 1–15', 'Ball number':'球号', 'Apply box edit':'应用标注框修改', 'Correction note':'修正备注', 'Optional context for this frame correction':'此帧修正的可选说明', 'Clear all boxes':'清除全部标注框',
  'Drag a box to move it. Select a box and drag its square handles to resize. Add tools draw a new box. Table polygon stays the detector result.':'拖动标注框进行移动。选中标注框后拖动方形控制点调整大小。使用添加工具绘制新框。球桌多边形保留检测器结果。',
  'Choose a verdict before saving.':'请先选择判定再保存。', 'Freeze a frame first.':'请先冻结一帧。', 'Select at least one detector.':'请至少选择一个检测器。',
  'Raw source frame fallback (original evidence unavailable)':'原始源帧备用图（原始证据不可用）', 'RAW SOURCE FRAME FALLBACK · Original evidence image unavailable':'原始源帧备用图 · 原始证据图像不可用', 'Evidence and raw source frame unavailable. Try the source video below.':'证据和原始源帧不可用。请尝试下方原始视频。',
  'Cue · 0':'母球 · 0', 'Ball crop':'球裁剪图', 'Ball context':'球的上下文', 'Saved label':'已保存标注', 'Raw VOD frame':'原始录像帧', 'Saved annotation':'已保存标注', 'Suggestion only — inspect before saving':'仅为建议 — 保存前请检查',
  'Choose an explicit seed label to save.':'请选择明确的种子标注并保存。', 'Saved seeds or rebuild snapshot changed. Rebuild after explicitly labeling A and B.':'保存的种子或重建快照已更改。请明确标注 A 和 B 后重建。', 'Balls · SAM3 on CPU (slow)':'球 · CPU 上的 SAM3（较慢）',
  'Freeze a frame before running inference.':'运行推理前请先冻结一帧。', 'Choose at least one detector (table, person, balls).':'请至少选择一个检测器（球桌、人物、球）。', 'Inference failed.':'推理失败。', 'Inference overlays updated for the frozen frame.':'冻结帧的推理叠加层已更新。', 'Status check failed.':'状态检查失败。', 'No VOD datasets are configured.':'尚未配置录像数据集。',
  'Rebuild experimental assignments using saved seeds. Saving a seed alone does not rebuild predictions.':'使用保存的种子重建实验性分配。仅保存种子不会重建预测。', 'Rebuild assignments':'重建分配', 'Checking status…':'正在检查状态…',
  'Pick a moment with the player or jump controls, then freeze it to inspect and correct.':'使用播放器或跳转控件选择时刻，然后冻结以检查和修正。', 'FROZEN FRAME · nothing loaded yet':'冻结帧 · 尚未加载', 'Frame inference':'帧推理', 'Run inference on frozen frame':'对冻结帧运行推理', 'Idle. Freeze a frame, choose detectors, then run.':'空闲。冻结一帧、选择检测器，然后运行。',
  'Frame inference covers this single decoded frame only. It cannot detect shots or pots — event inference needs time windows and is out of scope here.':'帧推理仅覆盖此单张解码帧，无法检测击球或入袋；事件推理需要时间窗口，不在此功能范围内。', 'Correction editor':'修正编辑器', 'Select / move':'选择 / 移动', 'Draw box':'绘制标注框', 'New box label':'新框标注', 'Selected label':'所选标注', 'Add table polygon':'添加球桌多边形', 'Clear polygon':'清除多边形', 'Save corrections for this frame':'保存此帧修正', 'No frame loaded':'未加载帧',
  'solid':'实色', 'stripe':'花色', 'eight':'黑八',
  'Drag boxes or corner handles; arrow keys nudge the selected box (Shift = 10 px). Ball centers follow their box. Drag table polygon corners. Saving writes manual corrections for this exact frame; saved inference is never overwritten.':'拖动标注框或角点控制柄；方向键微调所选框（Shift = 10 像素）。球心随标注框移动。可拖动球桌多边形角点。保存仅写入此精确帧的人工修正，绝不覆盖已保存的推理结果。',
  'SOLID':'实色', 'EIGHT':'黑八', 'STRIPE':'花色', 'CUE':'母球', 'Cue':'母球', 'person':'人物', 'cue':'母球', 'unknown':'未知', 'ball':'球', 'Raw source frame (no original evidence image)':'原始源帧（无原始证据图像）',
  'Highlight candidates were generated with the wrong-resolution calibration. They are not valid accuracy evidence; inspect the source before judging.':'集锦候选由分辨率不匹配的标定生成，不能作为有效准确率证据；请先检查原始资料再判定。',
  'Idle.':'空闲。', 'frame load failed':'帧加载失败', 'no frame loaded':'尚未加载帧', 'Frozen frame inspector':'冻结帧检查器', 'Predictions use the saved seed snapshot; they remain experimental.':'预测使用已保存的种子快照，仍属于实验结果。',
  'Needs review':'待复核', 'shot':'击球', 'pot':'入袋', 'Frame overlays':'帧叠加层', 'Frame annotations':'帧标注', 'Scrub decoded frames':'拖动浏览解码帧', 'Event markers':'事件标记'
});
const editorTemplates = [
  [/^(.+) · detector score (.+) \(not accuracy\)$/, (source, score) => `${source} · 检测器分数 ${score}（非准确率）`],
  [/^(.+) · ≈frame (\d+)$/, (time, frame) => `${time} · 约第 ${frame} 帧`],
  [/^Ball (\d+)$/, number => `球 ${number}`],
  [/^(\d+) \/ (\d+) crops · set independent of VOD selector$/, (index, count) => `${index} / ${count} 张裁剪图 · 图集独立于录像选择`],
  [/^Suggested times: (.*) seconds$/, times => `建议时间：${times} 秒`],
  [/^(\d+)\. (Top left|Top right|Bottom right|Bottom left|Left side|Right side)$/, (index, name) => `${index}. ${text(name)}`],
  [/^(.+) · (\d+) tracks$/, (window, count) => `${window} · ${count} 条轨迹`],
  [/^Track (.+) · prediction: (.+) · saved seed: (.+)$/, (id, prediction, seed) => `轨迹 ${id} · 预测：${prediction} · 已保存种子：${seed}`],
  [/^Track (.+) $/, id => `轨迹 ${id} `],
  [/^Predictions withheld: ([\s\S]*)$/, detail => `预测已暂缓：${text(detail)}`],
  [/^Status: (.+?)( — [\s\S]*)?$/, (status, detail = '') => `状态：${({running:'运行中',completed:'已完成',failed:'失败',idle:'空闲',unknown:'未知'})[status] || status}${detail}`],
  [/^Status unavailable: ([\s\S]*)$/, detail => `状态不可用：${detail}`],
  [/^decoding frame (\d+)…$/, frame => `正在解码帧 ${frame}…`],
  [/^RAW DECODED FRAME · (.+) · frame (\d+) · nominal (.+)s \((.+)\) · OVERLAYS: (.+)$/, (dataset, frame, time, kind, overlays) => `原始解码帧 · ${dataset} · 帧 ${frame} · 名义时间 ${time}s (${kind}) · 叠加层：${({'manual corrections':'人工修正',inference:'推理',none:'无'})[overlays] || overlays}`],
  [/^([\d.]+) fps · (\d+) frames · (.+) · nominal CFR timestamps$/, (fps, frames, duration) => `${fps} fps · ${frames} 帧 · ${duration} · 名义 CFR 时间戳`],
  [/^Inference running for frame (\d+): (.*)…$/, (frame, stage) => `正在对帧 ${frame} 运行推理：${stage}…`],
  [/^Inference completed for frame (\d+)\.$/, frame => `帧 ${frame} 推理已完成。`],
  [/^Inference for frame (\d+) finished; freeze that frame to see its overlays\.$/, frame => `帧 ${frame} 推理已完成；冻结该帧可查看叠加层。`],
  [/^Inference failed to start: ([\s\S]*)$/, detail => `推理启动失败：${detail}`],
  [/^Frame inference failed: ([\s\S]*)$/, detail => `帧推理失败：${detail}`],
  [/^Starting inference on frame (\d+) \((.*)\)…$/, (frame, detectors) => `正在启动帧 ${frame} 的推理（${detectors}）…`],
  [/^Inference status error: ([\s\S]*)$/, detail => `推理状态错误：${detail}`],
  [/^Corrections saved for frame (\d+)\.$/, frame => `帧 ${frame} 的修正已保存。`],
  [/^Save failed: ([\s\S]*)\. Your edits remain on screen; retry when ready\.$/, detail => `保存失败：${detail}。编辑仍保留在屏幕上。`],
  [/^Local VOD (.+) could not be loaded\. Open this workbench through the review server with the dataset ingested\.$/, dataset => `无法加载本地录像 ${dataset}。请导入数据集并通过复核服务器打开此工作台。`],
  [/^(Ball crop|Ball context|Raw VOD frame) unavailable\.$/, kind => `${text(kind)}不可用。`],
  [/^Rebuild failed: ([\s\S]*)$/, detail => `重建失败：${detail}`],
  [/^Inference failed: ([\s\S]*)$/, detail => `推理失败：${detail}`],
  [/^Frame load failed: ([\s\S]*)$/, detail => `帧加载失败：${detail}`],
  [/^frame (\d+) · (.+) · (.+)$/, (frame, time, dataset) => `帧 ${frame} · ${time} · ${dataset}`],
  [/^#(.+) · (Needs review|correct|wrong|unsure)$/, (id, verdict) => `#${id} · ${text(verdict)}`],
  [/^TIME (.+)$/, value => `时间 ${value}`], [/^POCKET (.+)$/, value => `袋口 ${value}`], [/^WINDOW (.+)$/, value => `窗口 ${value}`],
  [/^Save failed: ([\s\S]*)\. Your changes remain on screen; retry when ready\.$/, detail => `保存失败：${detail}。更改仍保留在屏幕上，可稍后重试。`],
  [/^(\d+) \/ (\d+) reviewed · (\d+) in queue$/, (done, total, queued) => `${done} / ${total} 已复核 · 队列中 ${queued}`],
  [/^Open source video at (.+)$/, at => `在 ${at} 打开原始视频`],
  [/^(Pot|Shot) candidate $/, kind => `${kind === 'Pot' ? '入袋' : '击球'}候选 `],
  [/^Raw decoded frame (\d+)$/, frame => `原始解码帧 ${frame}`],
  [/^Evidence for event (.+)$/, id => `事件 ${id} 的证据`]
];
function text(copy) {
  if (root?.lang !== 'zh') return copy;
  if (Object.hasOwn(editorCopy, copy)) return editorCopy[copy];
  for (const [pattern, format] of editorTemplates) { const match = copy.match(pattern); if (match) return format(...match.slice(1)); }
  return copy;
}
function updateOverlayFacts(source) {
  const facts = $('#frame-facts'); if (!facts) return;
  const node = facts.firstChild, previous = node && translatedCopy.get(node)?.nodeValue;
  const english = previous && node.nodeValue === previous.output ? previous.source : facts.textContent;
  facts.textContent = english.replace(/OVERLAYS: .*/, `OVERLAYS: ${source}`);
}
const translatedCopy = new WeakMap();
function translateEditor() {
  if (!root) return;
  const translate = (node, property) => {
    const current = node[property], previous = translatedCopy.get(node)?.[property];
    const source = previous && current === previous.output ? previous.source : current;
    const trimmed = source.trim();
    const output = Object.hasOwn(editorCopy, trimmed) ? source.replace(trimmed, text(trimmed)) : text(source) !== source ? text(source) : source.replace(trimmed, text(trimmed));
    if (output === source && !previous) return;
    translatedCopy.set(node, {...translatedCopy.get(node), [property]: {source, output}});
    if (current !== output) node[property] = output;
  };
  root.querySelectorAll('#title, #subtitle, #notice, #save-state, #content label, #content button, #content option, #content h2, #content h3, #content summary, #content .empty, #content .hint, #content .count, #content .panel-body > p, #content [data-point] span, #content [data-label] small, #content .chip, #content .frame-error, #content .image-error, #content [data-event] .badge, #crop-detail .badge, #content .frame-layout .panel-head .badge, #content .facts, #content .facts > span, #content [data-event] small, #track-detail, #prediction-status, #rebuild-status, #infer-status, #frame-badge, #play-state, #t-save-state').forEach(el => {
    if (el.closest?.('#ball-set')) return;
    // Without an explicit value, translating an option changes submitted data.
    if (el.tagName === 'OPTION' && !el.hasAttribute('value')) el.setAttribute('value', el.value);
    for (const node of el.childNodes) if (node.nodeType === 3) translate(node, 'nodeValue');
  });
  root.querySelectorAll('#content [placeholder]').forEach(el => translate(el, 'placeholder'));
  root.querySelectorAll('#content [aria-label], #content img[alt]').forEach(el => {
    for (const attribute of ['aria-label', 'alt']) {
      if (!el.hasAttribute(attribute)) continue;
      const current = el.getAttribute(attribute), previous = translatedCopy.get(el)?.[attribute];
      const source = previous && current === previous.output ? previous.source : current;
      const output = text(source);
      translatedCopy.set(el, {...translatedCopy.get(el), [attribute]: {source, output}});
      if (current !== output) el.setAttribute(attribute, output);
    }
  });
}
let copyObserver;
const englishCopy = new Map();
function setAppearance(lang, theme) {
  if (!root) return;
  lang = lang === 'zh' ? 'zh' : 'en'; theme = theme === 'light' ? 'light' : 'dark';
  root.lang = lang; root.dataset.theme = theme;
  try { localStorage.setItem('corner-pocket-lang', lang); localStorage.setItem('corner-pocket-theme', theme); } catch (_) {}
  for (const [kind, value, values] of [['lang',lang,['en','zh']],['theme',theme,['dark','light']]]) {
    for (const name of values) { const button = $(`#${kind}-${name}`); button.classList.toggle('active', name === value); button.setAttribute('aria-pressed', String(name === value)); }
  }
  // Observe future async renders, not form properties. Translation never rebuilds editors.
  if (!copyObserver && typeof MutationObserver !== 'undefined') {
    copyObserver = new MutationObserver(translateEditor);
    copyObserver.observe(root, {childList:true, subtree:true, characterData:true});
  }
  translateEditor();
  // Translate chrome in place; never rebuild the editable review content.
  root.querySelectorAll('[data-i18n], [data-i18n-html]').forEach(el => {
    const html = el.hasAttribute('data-i18n-html'), property = html ? 'innerHTML' : 'textContent';
    const key = el.getAttribute(html ? 'data-i18n-html' : 'data-i18n');
    if (!englishCopy.has(el)) englishCopy.set(el, el[property]);
    el[property] = lang === 'zh' ? zhCopy[key] || englishCopy.get(el) : englishCopy.get(el);
  });
}
window.CornerPocketReview = {mount, activate, deactivate, canLeave: () => !active || canLeave(), setAppearance};
const standaloneRoot = document.querySelector('#review-root');
if (standaloneRoot) { mount(standaloneRoot); activate(); }
})();
