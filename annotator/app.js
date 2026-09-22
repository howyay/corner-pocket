(() => {
'use strict';
// Corner Pocket review engine: ONE stage surface (live edge or VOD frame, the
// same <img> fed by different sources), no sub-tab navigation. This module owns
// every frame request, every guard (dirty / busy / frame token) and every write
// path. annotator/vision-stage.js renders the source chips, cues rail, layer
// chips, inspector and scrub strip from snapshot() and drives this engine
// through the public API below; it owns no frame state and performs no fetch.
let root = null, active = false, mounting = null, initialized = false;
const $ = (s, scope = root) => scope ? scope.querySelector(s) : null;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const enc = encodeURIComponent;
// Historical review-mode names stay valid activation targets so nothing that
// used to be reachable disappears; they all activate the one stage and only
// move the adapter's focus to the rail group that owns the capability.
const modes = {events:'events', balls:'balls', calibration:'calibration', players:'players', timeline:'timeline', stream:'timeline'};
const raise = frame => frame === null || frame === undefined ? null : Math.round(frame);
const state = {
  mode:'timeline', dataset:'vod30', datasets:[], sets:[], set:'unlabeled_crops',
  events:[], annotations:{}, eventIndex:0, eventFilter:'all', verdictDraft:null, shooterDraft:null, noteDraft:null,
  balls:{items:[], labels:{}, index:0, file:null},
  anchors:{pts:[], index:0, w:1920, h:1080, saved:false, loaded:false, t:70},
  persons:{windows:[], win:'', tracks:[], seeds:{}, track:null, predictions:null, predictionsStale:false, status:'', rebuild:null},
  vmeta:null, frame:0, fresult:null, unified:null, frameDirty:false,
  boxes:[], polygon:null, sel:-1, tool:'select', drag:null,
  frameWidth:0, frameHeight:0, frameReq:0, shotUrl:null,
  overlay:{cloth:true,balls:true,persons:true,pockets:true,anchors:true,events:true},
  drawn:{cloth:0,balls:0,persons:0,pockets:0,anchors:0,events:0,on:false,source:'none'},
  loading:{overlay:false,since:0},
  live:{state:'idle',error:null,frame_age_ms:null,receive_to_result_ms:null,skipped:0,seq:null,receivedAt:null,stale:false,detections:null,attempt:null,detectors:['table','person']},
  source:{kind:'vod',label:'',channel:null},
  sel:{kind:'none',crop:null,ball:null,person:null,track:null,anchor:0,event:null,box:-1},
  focus:'events',
  receipts:[], notice:{text:'',error:false},
  dirty:false, busy:false, epoch:0, decoding:false, playing:false, playTimer:null, unifiedTimer:null, pendingSeek:null,
  detectors:{table:true,person:true,balls:false}, inferTimer:null, inferRunning:false, inferStatus:'',
  subs:[]
};
const subscribers = [];
function subscribe(fn) { if (typeof fn === 'function') subscribers.push(fn); return () => { const i = subscribers.indexOf(fn); if (i >= 0) subscribers.splice(i, 1); }; }
function notify() { for (const fn of subscribers.slice()) { try { fn(); } catch (error) { if (typeof console !== 'undefined' && console.warn) console.warn('vision adapter render failed', error); } } }
function notice(text, error = false) { state.notice = {text: text || '', error: !!error}; notify(); }
function canLeave() { return !state.busy && (!state.dirty || confirm(text('Discard unsaved changes?'))); }
function markDirty() { state.dirty = true; notify(); }
function counts() { return {cloth: state.drawn.cloth, balls: state.drawn.balls, persons: state.drawn.persons, pockets: state.drawn.pockets, anchors: state.drawn.anchors, events: state.drawn.events}; }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let data; try { data = await response.json(); } catch { throw new Error(`Server returned non-JSON (${response.status}). Open this workbench through the review server.`); }
  if (!response.ok || data.error) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
// Per-artifact save receipts: every write is acknowledged next to the artifact
// it changed, with the artifact id and the age of the write.
function receipt(key, textValue, at = Date.now(), error = false) { state.receipts = [{key, text: textValue, at, error}, ...state.receipts.filter(r => r.key !== key)].slice(0, 8); notify(); }
async function save(button, path, body, after, key, label) {
  if (state.busy) return false;
  state.busy = true; notify();
  if (button) button.disabled = true;
  const saved = button ? button.textContent : '';
  if (button) button.textContent = text('Saving…');
  state.receipts = [{key, text: `${label} · ${text('saving…')}`, at: 0, error: false}, ...state.receipts.filter(r => r.key !== key)];
  notify();
  try {
    const data = await api(path, body);
    if (after) after(data);
    state.dirty = false;
    receipt(key, label);
    state.notice = {text:'', error:false};
    return true;
  } catch (error) {
    receipt(key, `${label} · ${text('save failed')}: ${error.message}`, Date.now(), true);
    notice(`${text('save failed')}: ${error.message}. ${text('Your changes remain on screen; retry when ready.')}`, true);
    return false;
  } finally { state.busy = false; if (button) { button.disabled = false; button.textContent = text(saved); } notify(); }
}
function time(t) { t = Number(t) || 0; return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2,'0')}`; }
function image(src, alt, cls = '') { return `<img class="${cls}" src="${esc(src)}" alt="${esc(alt)}">`; }
// ---- free functions pinned by tests and reused by the adapter -------------
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
function ballLabelText(value) { return value === undefined || value === null ? 'Unlabeled' : value === -1 || value === 'u' ? 'Unknown' : value === 0 ? 'Cue · 0' : `Ball ${value}`; }
// ---- data loading (the only fetches in the Vision tab) --------------------
async function loadDatasets() {
  const data = await api('/api/datasets');
  if (!data.datasets?.length) throw new Error('No VOD datasets are configured.');
  state.sets = data.ball_sets || []; state.set = state.sets[0]?.id || 'unlabeled_crops';
  state.datasets = data.datasets;
  state.dataset = data.datasets.some(d => d.id === 'vod30') ? 'vod30' : data.datasets[0].id;
  notify();
}
async function loadVideo() {
  const meta = await api(`/api/video?dataset=${enc(state.dataset)}`);
  state.vmeta = meta; state.frameWidth = meta.width; state.frameHeight = meta.height;
  notify();
}
async function loadEvents() {
  const data = await api(`/api/${enc(state.dataset)}/events`);
  state.events = data.events || []; state.annotations = data.annotations || {}; notify();
  if (state.dataset === 'highlight') notice('Highlight candidates were generated with the wrong-resolution calibration. They are not valid accuracy evidence; inspect the source before judging.', true);
}
async function loadCrops(setId = state.set) {
  const data = await api(`/api/balls/${enc(setId)}/meta`);
  state.set = setId; state.balls = {items: data.items || [], labels: data.labels || {}, index: 0, file: null}; notify();
}
async function loadAnchors(t = state.anchors.t) {
  const data = await api(`/api/vod30/anchors?t=${enc(t)}`);
  const w = data.width || 1920, h = data.height || 1080;
  let pts = (data.pts || data.suggested_pts || []).map(p => Array.isArray(p) ? [...p] : [p.x, p.y]);
  if (pts.length !== 6) pts = [[.3,.2],[.7,.2],[.7,.8],[.3,.8],[.3,.5],[.7,.5]].map(([x,y]) => [Math.round(x*w),Math.round(y*h)]);
  state.anchors = {pts, index:0, w, h, saved: !!data.pts, loaded: true, t: data.t ?? t};
  notify();
}
async function loadPersons() {
  const data = await api('/api/vod30/tracklets');
  const windows = data.windows || [];
  state.persons.windows = windows.map(w => ({win: w.win, count: (w.tracks || []).length}));
  state.persons.seeds = data.seeds || {};
  state.persons.predictions = data.predictions || null;
  if (!state.persons.windows.some(w => w.win === state.persons.win)) state.persons.win = state.persons.windows[0]?.win || '';
  notify();
}
let trackRequest = 0;
async function loadTracks(at = null) {
  const epoch = state.epoch, request = ++trackRequest;
  const win = state.persons.win;
  if (!win) { state.persons.tracks = []; notify(); return; }
  const [start, end] = String(win).split('-').map(Number);
  const t = Number.isFinite(at) ? at : (Number.isFinite(start) && state.t >= start && state.t <= end ? state.t : start);
  try {
    const data = await api(`/api/vod30/tracks?win=${enc(win)}&t=${enc(t)}`);
    if (epoch !== state.epoch || request !== trackRequest) return;
    state.persons.tracks = data.tracks || [];
    state.persons.t = data.t ?? t;
    notify();
  } catch (error) { if (epoch === state.epoch && request === trackRequest) notice(`${text('Tracks unavailable.')} ${error.message}`, true); }
}
async function loadSeeds() {
  try { const data = await api('/api/vod30/seeds'); state.persons.seeds = data.seeds || {}; notify(); } catch (_) {}
}
// ---- stage: exactly one frame surface ------------------------------------
async function fetchFrame(dataset, n) {
  // Bounded: a stalled request would otherwise leave the stage "decoding" forever
  // and swallow every queued seek behind it.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  let response;
  try { response = await fetch(`/api/frame?dataset=${enc(dataset)}&frame=${n}`, {signal: controller.signal}); }
  catch (error) { throw new Error(error.name === 'AbortError' ? `Frame ${n} request timed out after 25 s` : error.message); }
  finally { clearTimeout(timeout); }
  if (!response.ok) { let message = `Frame request failed (${response.status})`; try { message = (await response.json()).error || message; } catch {} throw new Error(message); }
  return {url: URL.createObjectURL(await response.blob()), frame: Number(response.headers.get('X-Frame-Index')), t: Number(response.headers.get('X-Timestamp-Seconds')), kind: response.headers.get('X-Timestamp-Kind') || '', w: Number(response.headers.get('X-Frame-Width')), h: Number(response.headers.get('X-Frame-Height'))};
}
// One overlay fetch per settled frame: a burst of seeks must not queue a
// dozen 10-second identity runs on the review server (the frame token still
// drops any response that arrives after a newer frame).
function scheduleUnified(frame, epoch, request) {
  clearTimeout(state.unifiedTimer);
  state.unifiedTimer = setTimeout(() => loadUnified(state.dataset, frame, epoch, request), 300);
}
async function loadUnified(dataset, frame, epoch, request) {
  state.loading = {overlay: true, since: Date.now()}; notify();
  try {
    const response = await fetch(`/api/unified?dataset=${enc(dataset)}&frame=${frame}`, {cache:'no-store'});
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (epoch !== state.epoch || request !== state.frameReq) return;
    state.unified = data;
    state.drawn.source = state.fresult?.correction ? 'manual corrections' : state.fresult?.inference ? 'inference' : 'unified';
  } catch {
    if (epoch === state.epoch && request === state.frameReq) state.unified = null;
  } finally {
    if (epoch === state.epoch && request === state.frameReq) { state.loading = {overlay: false, since: 0}; paintOverlay(); notify(); }
  }
}
async function loadFrame(n) {
  if (state.busy || !state.vmeta) return;
  const meta = state.vmeta; n = clampFrame(n, meta);
  const epoch = state.epoch, request = ++state.frameReq;
  state.busy = true; state.decoding = true; notify();
  try {
    const [shot, result] = await Promise.all([fetchFrame(state.dataset, n), api(`/api/frame-result?dataset=${enc(state.dataset)}&frame=${n}`)]);
    if (epoch !== state.epoch || request !== state.frameReq) { URL.revokeObjectURL(shot.url); return; }
    if (state.shotUrl) URL.revokeObjectURL(state.shotUrl);
    state.shotUrl = shot.url; state.frame = shot.frame; state.t = shot.t; state.fresult = result;
    state.frameWidth = shot.w || state.frameWidth; state.frameHeight = shot.h || state.frameHeight;
    state.dirty = false; state.unified = null; state.drawn.source = 'none';
    applyFrameResult(); renderStage();
    scheduleUnified(shot.frame, epoch, request);
  } catch (error) {
    if (epoch === state.epoch && request === state.frameReq) notice(`${text('Frame load failed')}: ${error.message}`, true);
  } finally {
    if (epoch === state.epoch && request === state.frameReq) {
      state.busy = false; state.decoding = false;
      const queued = state.pendingSeek; state.pendingSeek = null; notify();
      if (queued !== null && queued !== undefined) loadFrame(queued);
    }
  }
}
function applyFrameResult() {
  const display = displayBoxes(state.fresult);
  state.boxes = display.boxes; state.polygon = display.polygon;
  // A frame load replaces the box list, so only a box selection is dropped.
  // Event / ball / person / anchor selections survive the seek that selected them.
  if (state.sel.kind === 'box') state.sel = {kind:'none',crop:null,ball:null,person:null,track:null,anchor:0,event:null,box:-1};
  state.drawn.source = state.fresult?.correction ? 'manual corrections' : state.fresult?.inference ? 'inference' : 'none';
}
// Seek = freeze the stage on one decoded frame. Used by every cue selection.
// A seek that arrives while a decode is in flight is queued, never dropped:
// clicking a cue must always end on that cue's frame.
function seek(n) {
  const meta = state.vmeta; if (!meta) return false;
  n = clampFrame(n, meta);
  if (!canLeave()) return false;
  if (state.busy) { state.pendingSeek = n; notify(); return true; }
  loadFrame(n); return true;
}
function seekTime(t) { const meta = state.vmeta; if (!meta) return false; return seek(frameFromTime(meta, t)); }
function stepFrame(delta) { if (!state.vmeta || !canLeave()) return false; return seek((state.pendingSeek ?? state.frame) + delta); }
function setPlaying(playing) {
  state.playing = !!playing;
  clearTimeout(state.playTimer); state.playTimer = null;
  if (state.playing) tickPlayback();
  notify();
}
// Frames come from the review server one request at a time: playback is a
// decode-rate pump, and the facts line reports the measured rate honestly.
let playMark = 0, playCount = 0;
function playbackRate() {
  if (!playMark) return 0;
  const seconds = (Date.now() - playMark) / 1000;
  return seconds > 0 ? playCount / seconds : 0;
}
function tickPlayback() {
  if (!state.playing) return;
  if (!playMark) { playMark = Date.now(); playCount = 0; }
  if (!state.busy && state.vmeta) {
    if (state.frame >= state.vmeta.frame_count - 1) { setPlaying(false); return; }
    playCount++;
    loadFrame(state.frame + 1).then(() => {});
  }
  state.playTimer = setTimeout(tickPlayback, 90);
}
function setOverlay(kind, on) {
  if (!(kind in state.overlay)) return false;
  state.overlay[kind] = !!on; paintOverlay(); notify(); return true;
}
function toggleOverlay(kind) { const next = !state.overlay[kind]; setOverlay(kind, next); return next; }
// The facts line is derived from what the painter actually drew, so
// "overlays: none" while nodes are drawn is structurally impossible.
// ---- stage rendering -----------------------------------------------------
function stageHTML() {
  const w = state.frameWidth || 1280, h = state.frameHeight || 720;
  return `<figure class="stage" id="stage">
    <img id="t-img" alt="${esc(text('Raw decoded frame'))}" ${state.shotUrl ? `src="${esc(state.shotUrl)}"` : ''}>
    <svg id="t-overlay" role="group" aria-label="${esc(text('Frame overlays'))}" viewBox="0 0 ${w} ${h}"></svg>
    <div class="stage-empty" id="stage-empty" ${state.shotUrl || state.liveShift ? 'hidden' : ''}>${esc(text('Pick a moment on the scrub strip, or select a cue, then freeze it here.'))}</div>
    <div class="stage-live" id="stage-live" ${state.source.kind === 'live' ? '' : 'hidden'}></div>
    <div class="stage-popover" id="stage-popover" hidden></div>
  </figure>`;
}
function renderStage() {
  const content = $('#content');
  if (!content) return;
  if (content.dataset.stage !== '1' || !$('#t-overlay')) { content.dataset.stage = '1'; content.innerHTML = stageHTML(); }
  const img = $('#t-img');
  if (img && state.shotUrl && img.getAttribute('src') !== state.shotUrl) img.src = state.shotUrl;
  if (img) img.hidden = !state.shotUrl;
  const empty = $('#stage-empty'); if (empty) empty.hidden = !!state.shotUrl;
  const svg = $('#t-overlay'); if (svg) { svg.setAttribute('viewBox', `0 0 ${state.frameWidth || 1280} ${state.frameHeight || 720}`); if (!svg.dataset.bound) { svg.dataset.bound = '1'; svg.onpointerdown = overlayPointerDown; svg.onpointermove = overlayPointerMove; svg.onpointerup = svg.onpointercancel = overlayPointerUp; } }
  paintOverlay(); paintLiveChip(); paintPopover(); notify();
}
function paintLiveChip() {
  const chip = $('#stage-live'); if (!chip) return;
  const live = state.live;
  chip.hidden = false;
  if (state.source.kind === 'live' && live.stale) chip.className = 'stage-live stale';
  else if (state.source.kind === 'live') chip.className = 'stage-live on';
  else chip.hidden = true;
  chip.textContent = state.source.kind !== 'live' ? '' : live.stale ? `${text('STALE')} ${live.frame_age_ms != null ? (live.frame_age_ms / 1000).toFixed(1) + ' s' : ''}`.trim() : `● ${text('live')}`;
}
function paintOverlay() {
  const svg = $('#t-overlay'); if (!svg) return;
  const drawn = {cloth:0,balls:0,persons:0,pockets:0,anchors:0,events:0};
  // Provenance: `auto` holds what the model drew (unified detection or the live
  // metadata stream); the manual polygon and correction boxes are counted into
  // the same totals so the facts line still matches the stage exactly.
  const auto = {cloth:0,balls:0,persons:0,pockets:0,anchors:0,events:0};
  const layers = [];
  const ov = state.overlay, live = state.live, isLive = state.source.kind === 'live';
  const u = state.unified;
  const liveBoxes = (live?.detections?.boxes || []);
  const livePoly = live?.detections?.table_polygon || null;
  if (ov.cloth) {
    const corners = u?.table_corners || livePoly;
    if (corners && corners.length) { layers.push(`<polygon class="u-cloth" points="${corners.map(p => p.join(',')).join(' ')}" fill="none"></polygon>`); auto.cloth = 1; }
  }
  if (ov.pockets && u?.pockets) { layers.push(u.pockets.map(pk => `<g class="u-pocket"><circle cx="${pk.cx}" cy="${pk.cy}" r="12" fill="none" stroke="var(--brass)" stroke-width="2.5"></circle><text x="${pk.cx}" y="${pk.cy + 26}" text-anchor="middle" font-size="13">${esc(pk.name)}</text></g>`).join('')); auto.pockets = u.pockets.length; }
  if (ov.persons) {
    const persons = u?.persons || (isLive ? liveBoxes.filter(b => b.label === 'person') : []);
    layers.push(persons.map(per => {
      const [x1, y1, x2, y2] = per.bbox;
      const track = per.track_id ?? per.track;
      const selected = state.sel.kind === 'person' && track !== undefined && String(state.sel.person?.track_id ?? state.sel.person?.track) === String(track);
      const chip = ov && per.player_id ? `<text x="${x1}" y="${Math.max(14, y1 - 6)}" font-size="15" fill="#8fd6a8">${esc(per.player_id)}</text>` : (per.cluster_id ? `<text x="${x1}" y="${Math.max(14, y1 - 6)}" font-size="13" fill="var(--ink-dim)">track ${esc(track)}</text>` : '');
      return `<g class="u-person${selected ? ' selected' : ''}" data-person="${esc(track)}" data-bbox="${esc((per.bbox || []).join(','))}" data-cluster="${esc(per.cluster_id ?? '')}" data-player="${esc(per.player_id ?? '')}"><rect x="${x1}" y="${y1}" width="${x2 - x1}" height="${y2 - y1}" fill="none" stroke="#8fd6a8" stroke-width="2"></rect>${chip}</g>`;
    }).join(''));
    auto.persons = persons.length;
  }
  if (ov.balls) {
    const balls = u?.balls || (isLive ? liveBoxes.filter(b => b.label === 'ball') : []);
    layers.push(balls.map((b, i) => {
      const cx = b.cx ?? (b.bbox ? (b.bbox[0] + b.bbox[2]) / 2 : 0), cy = b.cy ?? (b.bbox ? (b.bbox[1] + b.bbox[3]) / 2 : 0), r = Math.max(9, b.r ?? 12);
      return `<g class="u-ball" data-ball="${i}" data-cx="${cx}" data-cy="${cy}" data-r="${r}" data-color="${esc(b.color ?? '')}"><circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--brass-hi)" stroke-width="2"></circle><circle cx="${cx}" cy="${cy}" r="2" fill="var(--brass-hi)"></circle></g>`;
    }).join(''));
    auto.balls = balls.length;
  }
  if (ov.events && u?.events && u?.pockets) {
    for (const event of u.events) {
      if (event.type !== 'pot') continue;
      const name = String(event.nearest_pocket || '').split(/[\s(]/)[0];
      const pk = u.pockets.find(p => p.name === name);
      if (pk) { layers.push(`<circle class="u-pot-pulse" cx="${pk.cx}" cy="${pk.cy}" r="18" fill="none" stroke="var(--red)" stroke-width="3"></circle>`); auto.events++; }
    }
  }
  if (ov.anchors && state.anchors.loaded && state.dataset === 'vod30') {
    layers.push(state.anchors.pts.map(([x, y], i) => `<g class="u-anchor${state.sel.kind === 'anchor' && state.anchors.index === i ? ' selected' : ''}" data-anchor="${i}"><circle cx="${x}" cy="${y}" r="12"></circle><text x="${x + 18}" y="${y - 16}">${i + 1}</text></g>`).join(''));
    auto.anchors = state.anchors.pts.length;
  }
  // The editable layer is the operator's only once a correction exists or they
  // have edited this frame; an untouched inference frame stays a model result.
  const boxSource = state.dirty || state.fresult?.correction ? 'manual' : 'auto';
  const boxesAreManual = boxSource === 'manual';
  for (const box of state.boxes) {
    if (box.label === 'person') { boxesAreManual ? drawn.persons++ : auto.persons++; }
    else if (ballLabel(box.label)) { boxesAreManual ? drawn.balls++ : auto.balls++; }
  }
  if (state.polygon) boxesAreManual ? drawn.cloth++ : auto.cloth++;
  svg.dataset.boxes = boxSource;
  const boxes = state.boxes.map((box, i) => {
    const [x1, y1, x2, y2] = box.bbox, center = boxCenter(box);
    const selected = state.sel.kind === 'box' && state.sel.box === i;
    const handles = selected ? [[x1,y1],[x2,y1],[x2,y2],[x1,y2]].map(([hx,hy],c) => `<rect class="handle" data-handle="${c}" x="${hx-7}" y="${hy-7}" width="14" height="14"></rect>`).join('') : '';
    return `<g data-box="${i}" class="t-box${selected ? ' selected' : ''}"><rect x="${x1}" y="${y1}" width="${x2-x1}" height="${y2-y1}"></rect>${ballLabel(box.label) ? `<circle class="center-dot" cx="${center[0]}" cy="${center[1]}" r="4"></circle>` : ''}<text x="${x1+4}" y="${Math.max(16,y1-6)}">${esc(box.label)}${box.score != null ? ` ${Number(box.score).toFixed(2)}` : ''}</text>${handles}</g>`;
  }).join('');
  const poly = state.polygon ? `<polygon class="t-poly" points="${state.polygon.map(p => p.join(',')).join(' ')}"></polygon>${state.polygon.map((p,i) => `<circle class="handle" data-poly="${i}" cx="${p[0]}" cy="${p[1]}" r="9"></circle>`).join('')}` : '';
  const preview = state.drag && state.drag.kind === 'draw' ? `<rect class="draw-preview" x="${Math.min(state.drag.x1,state.drag.x2)}" y="${Math.min(state.drag.y1,state.drag.y2)}" width="${Math.abs(state.drag.x2-state.drag.x1)}" height="${Math.abs(state.drag.y2-state.drag.y1)}"></rect>` : '';
  svg.innerHTML = layers.join('') + poly + boxes + preview;
  svg.querySelectorAll('g[data-box]').forEach(g => g.onclick = () => { if (state.tool === 'select' && state.sel.box !== Number(g.dataset.box)) { selectBox(Number(g.dataset.box)); } });
  svg.querySelectorAll('g.u-ball').forEach(g => g.onclick = event => { event.stopPropagation(); selectStageBall(Number(g.dataset.ball), Number(g.dataset.cx), Number(g.dataset.cy), Number(g.dataset.r)); });
  svg.querySelectorAll('g.u-person').forEach(g => g.onclick = event => { event.stopPropagation(); selectStagePerson(g.dataset); });
  svg.querySelectorAll('g.u-anchor').forEach(g => g.onclick = event => { event.stopPropagation(); selectAnchor(Number(g.dataset.anchor)); });
  Object.assign(drawn, {cloth: drawn.cloth + auto.cloth, balls: drawn.balls + auto.balls, persons: drawn.persons + auto.persons, pockets: auto.pockets, anchors: auto.anchors, events: auto.events});
  state.drawn = {...drawn, auto, on: true, source: state.drawn.source};
}
// ---- selection -----------------------------------------------------------
function selectEvent(index) {
  const event = state.events[index]; if (!event) return false;
  state.eventIndex = index;
  state.verdictDraft = null; state.shooterDraft = null; state.noteDraft = null;
  state.sel = {kind:'event', event, crop:null, ball:null, person:null, track:null, anchor:0, box:-1};
  state.focus = 'events';
  notify();
  seekTime(event.t);
  return true;
}
function selectCrop(file) {
  const item = state.balls.items.find(i => i.file === file) || (file ? {file, t: state.t} : null);
  if (!item) return false;
  state.balls.file = item.file;
  state.balls.index = Math.max(0, state.balls.items.findIndex(i => i.file === item.file));
  state.sel = {kind:'ball', crop: item, ball:null, event:null, person:null, track:null, anchor:0, box:-1};
  state.focus = 'balls';
  notify();
  if (Number.isFinite(Number(item.t))) seekTime(Number(item.t));
  return true;
}
function cropsAt(t, tolerance = 0.6) { return state.balls.items.filter(i => Math.abs(Number(i.t) - Number(t)) <= tolerance); }
// A stage ball is a detection, not a file: it selects the crop cue at this
// frame's time so the 0–9/U/C popover writes the artifact that owns the label.
function selectStageBall(index, cx, cy, r) {
  const near = cropsAt(state.t);
  const fallback = near.find(i => state.balls.labels[i.file] == null) || near[0];
  state.sel = {kind:'ball', crop: fallback || null, ball:{index, cx, cy, r}, event:null, person:null, track:null, anchor:0, box:-1};
  if (fallback) { state.balls.file = fallback.file; state.balls.index = Math.max(0, state.balls.items.findIndex(i => i.file === fallback.file)); }
  state.focus = 'balls';
  notify(); paintOverlay(); paintPopover();
}
function selectStagePerson(dataset) {
  const track = dataset.person === '' ? null : trackId(dataset.person);
  const bbox = String(dataset.bbox || '').split(',').map(Number);
  state.sel = {kind:'person', person:{track_id: track, bbox, cluster_id: dataset.cluster || null, player_id: dataset.player || null}, crop:null, ball:null, event:null, track: track, anchor:0, box:-1};
  state.focus = 'persons';
  if (!state.persons.windows.length) loadPersons().then(() => { if (state.persons.win) loadTracks(); });
  notify();
}
function selectTrack(id) {
  const track = state.persons.tracks.find(t => String(t.id) === String(id)) || {id: trackId(id), box:null, label:null, seed:null};
  state.persons.track = track.id;
  state.sel = {kind:'person', person:{track_id: id, bbox: track.box || null, cluster_id: null, player_id: null}, track: id, crop:null, ball:null, event:null, anchor:0, box:-1};
  state.focus = 'persons';
  notify(); paintOverlay();
  return track;
}
async function selectTrackAndSeek(id) {
  selectTrack(id);
  if (!state.persons.windows.length) await loadPersons();
  await loadTracks();
  const [start, end] = String(state.persons.win).split('-').map(Number);
  const at = state.persons.t ?? start;
  if (Number.isFinite(at)) seekTime(Math.max(start, Math.min(end, at)));
  return true;
}
function selectAnchor(index) {
  if (state.dataset !== 'vod30') return false;
  state.anchors.index = index;
  state.sel = {kind:'anchor', anchor:index, crop:null, ball:null, person:null, track:null, event:null, box:-1};
  state.focus = 'anchors';
  notify(); paintOverlay();
  return true;
}
function selectBox(index) {
  state.sel = {kind:'box', box:index, crop:null, ball:null, person:null, track:null, event:null, anchor:0};
  state.sel_box = index;
  notify(); paintOverlay();
}
function clearSelection() { state.sel = {kind:'none',crop:null,ball:null,person:null,track:null,anchor:0,event:null,box:-1}; state.sel_box = -1; notify(); paintPopover(); }
// ---- writes --------------------------------------------------------------
function eventForSelection() { return state.sel.kind === 'event' ? state.sel.event : state.events[state.eventIndex] || null; }
function verdictValue() { const event = eventForSelection(); return event ? (state.annotations[String(event.id)] || {}) : {}; }
function setVerdictDraft(verdict) { state.verdictDraft = verdict; notify(); }
function cycleVerdict() { const order = ['correct','wrong','unsure']; const current = state.verdictDraft ?? verdictValue().verdict ?? ''; const next = order[(order.indexOf(current) + 1) % order.length]; state.verdictDraft = next; notify(); return next; }
async function saveVerdict(button, verdict) {
  const event = eventForSelection(); if (!event) return false;
  const saved = state.annotations[String(event.id)] || {};
  const body = {event_id: event.id, verdict: verdict || state.verdictDraft || saved.verdict || '', shooter: state.shooterDraft ?? saved.shooter ?? '', note: state.noteDraft ?? saved.note ?? ''};
  if (!body.verdict) { notice(text('Choose a verdict before saving.'), true); return false; }
  const frame = state.frame;
  return save(button, `/api/${enc(state.dataset)}/annotate`, body, () => {
    state.annotations[String(event.id)] = body; state.verdictDraft = body.verdict;
  }, 'event', `${event.type === 'pot' ? 'cue' : 'shot'} #${event.id} ${event.type} @ frame ${frame} · ${body.verdict}`);
}
function labelValueText(value) { return value === null || value === undefined ? 'cleared' : value === -1 ? 'Unknown' : value === 0 ? 'Cue 0' : `Ball ${value}`; }
async function labelBall(button, value) {
  const crop = state.sel.kind === 'ball' ? state.sel.crop : null;
  if (!crop) { notice(text('Select a ball or a crop first.'), true); return false; }
  const file = crop.file.split('/').pop();
  const label = value === 'clear' ? null : Number(value);
  return save(button, `/api/balls/${enc(state.set)}/label`, {file, label}, () => {
    state.balls.labels ||= {};
    if (label === null) delete state.balls.labels[file]; else state.balls.labels[file] = label === -1 ? 'u' : label;
  }, 'ball', `crop ${file} = ${labelValueText(label === -1 ? 'u' : label)}`);
}
// The seeds contract types track_id as an integer; rail dataset attributes are strings.
function trackId(value) { return typeof value === 'string' && /^-?\d+$/.test(value) ? Number(value) : value; }
async function setSeed(button, role, playerId) {
  const track = state.sel.track;
  if (track === null || track === undefined) { notice(text('Select a visible track first.'), true); return false; }
  const t = state.persons.t ?? state.t;
  const body = {win: state.persons.win, t, track_id: trackId(track), label: role === 'clear' ? null : role};
  return save(button, '/api/vod30/seeds', body, async () => { await loadSeeds(); }, 'person', `win ${state.persons.win} · track ${track} = ${role === 'clear' ? 'cleared' : role}`);
}
async function seedIdentity(button, playerId) {
  const person = state.sel.person || {};
  if (!person.cluster_id) { notice(text('This track has no identity cluster yet.'), true); return false; }
  return save(button, '/api/identity/seed', {cluster_id: person.cluster_id, player_id: playerId}, null, 'person', `cluster ${String(person.cluster_id).slice(0, 6)} → ${playerId}`);
}
async function saveAnchors(button) {
  return save(button, '/api/vod30/anchors', {t: state.anchors.t, pts: state.anchors.pts.map(p => [...p])}, () => { state.anchors.saved = true; }, 'anchor', `${state.anchors.pts.length} anchors @ t ${Number(state.anchors.t).toFixed(1)}`);
}
async function saveCorrections(button) {
  if (state.busy || !state.fresult) return false;
  const invalid = state.boxes.find(box => !normalizeBox(box.bbox, state.frameWidth, state.frameHeight));
  if (invalid) { notice(text('A box has invalid coordinates; fix or delete it before saving.'), true); return false; }
  const body = {dataset: state.dataset, frame_index: state.frame, boxes: state.boxes.map(box => ({label: box.label, bbox: box.bbox})), table_polygon: state.polygon ? state.polygon.map(p => [p[0], p[1]]) : null};
  const ok = await save(button, '/api/frame-correction', body, () => { state.fresult.correction = {boxes: state.boxes.map(b => ({label: b.label, bbox: b.bbox.slice()})), table_polygon: body.table_polygon}; state.drawn.source = 'manual corrections'; paintOverlay(); }, 'corrections', `frame ${state.frame} · ${state.boxes.length} boxes${state.polygon ? ' + polygon' : ''}`);
  return ok;
}
function setTool(tool) { state.tool = tool; notify(); }
function setDetector(kind, on) { if (!(kind in state.detectors)) return false; state.detectors[kind] = !!on; notify(); return true; }
function setShooter(value) { state.shooterDraft = value; notify(); }
function setNote(value) { state.noteDraft = value; }
function setEventFilter(filter) { state.eventFilter = ['all','shot','pot','pending'].includes(filter) ? filter : 'all'; notify(); }
function freeze() { setPlaying(false); return seek(state.frame); }
async function setWindow(win) {
  if (state.busy) return false;
  state.persons.win = win;
  const start = Number(String(win).split('-')[0]);
  notify();
  if (Number.isFinite(start)) { await loadTracks(); seekTime(start); }
  return true;
}
function setBoxLabel(label) { if (state.boxes[state.sel.box]) { state.boxes[state.sel.box].label = label; markDirty(); paintOverlay(); } }
function deleteBox() { if (state.sel.box >= 0) { state.boxes.splice(state.sel.box, 1); clearSelection(); state.dirty = true; paintOverlay(); notify(); } }
function addPolygon() { const w = state.frameWidth, h = state.frameHeight; state.polygon = [[Math.round(w*.1),Math.round(h*.1)],[Math.round(w*.9),Math.round(h*.1)],[Math.round(w*.9),Math.round(h*.9)],[Math.round(w*.1),Math.round(h*.9)]]; markDirty(); paintOverlay(); }
function clearPolygon() { if (state.polygon) { state.polygon = null; markDirty(); paintOverlay(); } }
function setNewBoxLabel(label) { state.newBoxLabel = label; notify(); }
function nudgeAnchor(dx, dy) {
  if (state.busy) return;
  const p = state.anchors.pts[state.anchors.index]; if (!p) return;
  p[0] = Math.max(0, Math.min(state.anchors.w - 1, p[0] + dx)); p[1] = Math.max(0, Math.min(state.anchors.h - 1, p[1] + dy));
  markDirty(); paintOverlay();
}
async function runInference(button) {
  if (state.busy || !state.fresult) { if (!state.fresult) notice(text('Freeze a frame before running inference.'), true); return false; }
  const detectors = Object.keys(state.detectors).filter(k => state.detectors[k]);
  if (!detectors.length) { notice(text('Choose at least one detector (table, person, balls).'), true); return false; }
  const frame = state.frame, epoch = state.epoch;
  state.inferRunning = true; state.inferStatus = `${text('Starting inference on frame')} ${frame} (${detectors.join(', ')})…`; notify();
  try {
    const job = await api('/api/inference', {dataset: state.dataset, frame_index: frame, detectors});
    if (epoch !== state.epoch) return false;
    state.inferStatus = `${text('Inference running for frame')} ${job.frame_index}: ${job.stage || 'queued'}…`; notify();
    pollInference(epoch, job.frame_index);
    return true;
  } catch (error) {
    if (epoch === state.epoch) { state.inferRunning = false; state.inferStatus = text('Idle.'); notice(`${text('Inference failed to start')}: ${error.message}`, true); }
    return false;
  }
}
function pollInference(epoch, frame) {
  clearTimeout(state.inferTimer);
  state.inferTimer = setTimeout(async () => {
    try {
      const job = await api(`/api/inference?dataset=${enc(state.dataset)}`);
      if (epoch !== state.epoch) return;
      if (job.status === 'running') { state.inferStatus = `${text('Inference running for frame')} ${job.frame_index}: ${job.stage || ''}…`; notify(); pollInference(epoch, frame); return; }
      state.inferRunning = false;
      if (job.status === 'failed') { state.inferStatus = text('Inference failed.'); notice(`${text('Frame inference failed')}: ${job.error || 'unknown error'}`, true); return; }
      state.inferStatus = `${text('Inference completed for frame')} ${job.frame_index}.`; notify();
      if (job.status === 'completed' && job.result && job.frame_index === frame && state.frame === frame) {
        if (state.fresult) state.fresult.inference = job.result;
        if (!state.dirty && !state.fresult?.correction) { applyFrameResult(); renderStage(); }
        paintOverlay(); notify();
        notice(text('Inference overlays updated for the frozen frame.'));
      } else if (job.status === 'completed') notice(`${text('Inference for frame')} ${job.frame_index} ${text('finished; freeze that frame to see its overlays.')}`);
    } catch (error) { if (epoch === state.epoch) { state.inferRunning = false; state.inferStatus = text('Status check failed.'); notice(`${text('Inference status error')}: ${error.message}`, true); } }
  }, 1500);
}
async function rebuild(button) {
  if (button) button.disabled = true;
  state.persons.status = text('Rebuilding…'); notify();
  try {
    const data = await api('/api/vod30/rebuild', {});
    state.persons.rebuild = data.status || 'unknown';
    state.persons.status = `${text('Status')}: ${data.status || 'unknown'}${data.error ? ` — ${data.error}` : ''}`;
    if (data.status === 'running') setTimeout(() => refreshRebuild(), 2500);
  } catch (error) { state.persons.status = `${text('Rebuild failed')}: ${error.message}`; notice(`${text('Rebuild failed')}: ${error.message}`, true); }
  notify();
}
async function refreshRebuild() {
  try {
    const data = await api('/api/vod30/rebuild');
    state.persons.rebuild = data.status || 'unknown';
    state.persons.status = `${text('Status')}: ${data.status || 'unknown'}${data.error ? ` — ${data.error}` : ''}`;
    if (data.status === 'completed') { const fresh = await api('/api/vod30/tracklets'); state.persons.predictions = fresh.predictions; await loadTracks(); }
  } catch (error) { state.persons.status = `${text('Status unavailable')}: ${error.message}`; }
  notify();
}
// ---- live source: the stage shows the live edge in the same <img> ---------
function applyLiveStatus(status) {
  if (!status || typeof status !== 'object') return;
  const previous = state.live.state;
  state.live.state = status.state || 'idle';
  state.live.error = status.error || null;
  state.live.skipped = status.frames_skipped ?? 0;
  state.live.receive_to_result_ms = status.latest?.receive_to_result_ms ?? null;
  state.live.frame_age_ms = status.frame_age_ms ?? null;
  if (status.latest?.seq != null) state.live.seq = status.latest.seq;
  // Frames that stopped arriving keep the last good image, marked stale.
  const measured = state.live.receivedAt ? Date.now() - state.live.receivedAt : null;
  const age = state.live.state === 'running' ? (state.live.frame_age_ms ?? measured) : measured;
  state.live.frame_age_ms = age;
  state.live.stale = age != null && age > 2000;
  // A failed start stays stated until a start succeeds: status polls of an
  // idle/stopped processor must not erase the attempt that failed.
  const failure = status.error || (state.live.state === 'error' ? state.live.error : null);
  if (failure) {
    state.live.attempt = {at: Date.now(), error: failure, source: state.live.attempt?.source || null};
    notice(`${text('Live start failed')}: ${failure}`, true);
  } else if (state.live.state === 'running' || state.live.state === 'starting') {
    state.live.attempt = null;
  } else if (state.live.attempt?.error) {
    state.live.error = state.live.attempt.error;
  }
  if (previous !== state.live.state || state.live.stale) notify();
  paintLiveChip(); notify();
}
// A live frame is one <img> fed from /api/live/frame, with the overlay
// metadata that arrived in the same response headers.
function ingestLiveFrame(url, meta, source = {}) {
  const epoch = state.epoch;
  state.source = {kind:'live', label: source.label || state.source.label, channel: source.channel ?? state.source.channel};
  state.live.detections = meta?.detections || null;
  state.live.seq = meta?.seq ?? state.live.seq;
  state.live.receivedAt = Date.now();
  const img = $('#t-img'); const svg = $('#t-overlay');
  if (img) { img.src = url; img.hidden = false; }
  if (epoch === state.epoch) { state.unified = null; paintOverlay(); paintLiveChip(); notify(); }
}
function setLiveAttempt(attempt) { state.live.attempt = attempt; notify(); }
// A successful start clears the failed-attempt block and its in-surface notice.
function clearLiveError() {
  state.live.attempt = null; state.live.error = null;
  if (state.notice.error) state.notice = {text:'',error:false};
  notify();
}
// ---- dataset / source switching -----------------------------------------
async function setDataset(dataset) {
  if (!canLeave()) return false;
  state.dataset = dataset; state.unified = null; state.fresult = null; state.shotUrl = null; state.frame = 0;
  state.source = {kind:'vod', label: dataset, channel:null};
  state.anchors.loaded = false;
  notify();
  try { await loadVideo(); await loadEvents(); await loadFrame(0); } catch (error) { notice(error.message, true); }
  return true;
}
// ---- pointer editing on the imagery -------------------------------------
function svgPoint(event) {
  const svg = $('#t-overlay'); if (!svg) return [0, 0];
  const rect = svg.getBoundingClientRect();
  return [Math.round(Math.max(0, Math.min(state.frameWidth, (event.clientX - rect.left) / rect.width * state.frameWidth))), Math.round(Math.max(0, Math.min(state.frameHeight, (event.clientY - rect.top) / rect.height * state.frameHeight)))];
}
function overlayPointerDown(event) {
  if (state.busy) return;
  const svg = $('#t-overlay'), handle = event.target.closest('[data-handle]'), poly = event.target.closest('[data-poly]'), anchor = event.target.closest('[data-anchor]'), box = event.target.closest('[data-box]');
  if (handle && (state.sel.box >= 0 || state.sel === undefined)) { event.preventDefault(); svg.setPointerCapture(event.pointerId); state.drag = {kind:'handle', box: Number(handle.closest('[data-box]')?.dataset.box ?? state.sel.box), corner: Number(handle.dataset.handle)}; return; }
  if (poly) { event.preventDefault(); svg.setPointerCapture(event.pointerId); state.drag = {kind:'poly', index: Number(poly.dataset.poly)}; return; }
  if (anchor) { event.preventDefault(); selectAnchor(Number(anchor.dataset.anchor)); svg.setPointerCapture(event.pointerId); state.drag = {kind:'anchor', index: Number(anchor.dataset.anchor)}; return; }
  if (box) { const index = Number(box.dataset.box); selectBox(index); if (state.tool === 'draw') return; event.preventDefault(); svg.setPointerCapture(event.pointerId); const [x,y] = svgPoint(event); state.drag = {kind:'move', box: index, x, y, orig: state.boxes[index].bbox.slice()}; return; }
  if (state.tool === 'draw') { event.preventDefault(); svg.setPointerCapture(event.pointerId); const [x,y] = svgPoint(event); state.drag = {kind:'draw', x1:x, y1:y, x2:x, y2:y}; paintOverlay(); return; }
  clearSelection();
}
function overlayPointerMove(event) {
  const drag = state.drag; if (!drag || state.busy) return;
  const [x, y] = svgPoint(event);
  if (drag.kind === 'move') {
    const box = state.boxes[drag.box]; if (!box) return;
    const w = drag.orig[2] - drag.orig[0], h = drag.orig[3] - drag.orig[1];
    const nx1 = Math.max(0, Math.min(state.frameWidth - w, drag.orig[0] + x - drag.x)), ny1 = Math.max(0, Math.min(state.frameHeight - h, drag.orig[1] + y - drag.y));
    box.bbox = [nx1, ny1, nx1 + w, ny1 + h]; markDirty(); paintOverlay();
  } else if (drag.kind === 'handle') {
    const box = state.boxes[drag.box]; if (!box) return;
    const next = box.bbox.slice();
    next[[0,2,2,0][drag.corner]] = x; next[[1,1,3,3][drag.corner]] = y;
    box.bbox = normalizeBox(next, state.frameWidth, state.frameHeight) || box.bbox;
    markDirty(); paintOverlay();
  } else if (drag.kind === 'poly') { state.polygon[drag.index] = [x, y]; markDirty(); paintOverlay();
  } else if (drag.kind === 'anchor') {
    const p = state.anchors.pts[drag.index]; if (!p) return;
    p[0] = Math.max(0, Math.min(state.anchors.w - 1, x)); p[1] = Math.max(0, Math.min(state.anchors.h - 1, y));
    markDirty(); paintOverlay();
  } else if (drag.kind === 'draw') { drag.x2 = x; drag.y2 = y; paintOverlay(); }
}
function overlayPointerUp() {
  const drag = state.drag; if (!drag) return;
  state.drag = null;
  if (drag.kind === 'draw') {
    const bbox = normalizeBox([drag.x1, drag.y1, drag.x2, drag.y2], state.frameWidth, state.frameHeight);
    if (bbox) { state.boxes.push({label: state.newBoxLabel || 'ball', bbox}); selectBox(state.boxes.length - 1); setTool('select'); markDirty(); }
  }
  paintOverlay(); notify();
}
function nudgeBox(dx, dy) {
  if (state.busy || state.sel.box < 0 || !state.boxes[state.sel.box]) return;
  const box = state.boxes[state.sel.box], moved = normalizeBox([box.bbox[0]+dx, box.bbox[1]+dy, box.bbox[2]+dx, box.bbox[3]+dy], state.frameWidth, state.frameHeight);
  if (moved) { box.bbox = moved; markDirty(); paintOverlay(); }
}
// ---- the ball label popover, attached to the ball on the imagery ---------
function paintPopover() {
  const pop = $('#stage-popover'); if (!pop || !state.sel.ball) { if (pop) pop.hidden = true; return; }
  const { cx, cy } = state.sel.ball, w = state.frameWidth || 1280, h = state.frameHeight || 720;
  const crop = state.sel.crop;
  pop.hidden = false;
  pop.style.left = `${Math.max(4, Math.min(78, cx / w * 100))}%`;
  pop.style.top = `${Math.max(6, Math.min(74, cy / h * 100))}%`;
  pop.innerHTML = `<div class="pop-head">${esc(crop ? crop.file.split('/').pop() : text('No crop at this frame'))}</div>
    <div class="pop-grid">${Array.from({length:10},(_,i) => `<button data-vs-action="label-ball" data-vs-value="${i}" ${crop ? '' : 'disabled'}>${i}</button>`).join('')}</div>
    <div class="pop-row"><button data-vs-action="label-ball" data-vs-value="-1" ${crop ? '' : 'disabled'}>U</button><button data-vs-action="label-ball" data-vs-value="0" ${crop ? '' : 'disabled'}>C</button><button data-vs-action="close-popover">${esc(text('Close'))}</button></div>
    <div class="pop-note">${esc(crop ? text('The label is written to this crop') : text('Select a crop cue in the rail to label it'))}</div>`;
}
// ---- keyboard ------------------------------------------------------------
function onKeydown(e) {
  if (!active || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target && e.target.closest && e.target.closest('input,textarea,select,button,video,[contenteditable="true"]')) return;
  if (e.__cpHandled) return;
  e.__cpHandled = true;
  const key = e.key;
  if (key === ' ' || key === 'Spacebar') { e.preventDefault(); setPlaying(!state.playing); return; }
  if (key === ',' || key === '.') { e.preventDefault(); stepFrame(key === ',' ? -1 : 1); return; }
  if (key === 'ArrowLeft' || key === 'ArrowRight') { e.preventDefault(); stepFrame((key === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 10 : 1)); return; }
  if (key === 'ArrowUp' || key === 'ArrowDown') {
    if (state.sel.kind === 'anchor') { e.preventDefault(); nudgeAnchor(0, key === 'ArrowUp' ? -1 : 1); return; }
    if (state.sel.box >= 0) { e.preventDefault(); nudgeBox(0, key === 'ArrowUp' ? -1 : 1); }
    return;
  }
  if (key === 'Escape') { clearSelection(); return; }
  if (key === 'Enter') { saveVerdict(null); return; }
  if (/^[0-9]$/.test(key)) { e.preventDefault(); labelBall(null, Number(key)); return; }
  const upper = key.length === 1 ? key.toUpperCase() : key;
  if (upper === 'U') { e.preventDefault(); labelBall(null, -1); return; }
  if (upper === 'C') { e.preventDefault(); labelBall(null, 0); return; }
  if (upper === 'A' || upper === 'B') { e.preventDefault(); setSeed(null, upper); return; }
  if (upper === 'V') { e.preventDefault(); cycleVerdict(); return; }
  if (upper === 'F') { e.preventDefault(); seek(state.frame); }
}
function bindControls() {
  root.tabIndex = -1;
  root.addEventListener('keydown', onKeydown);
  root.addEventListener('pointerdown', e => { if (active && !e.target.closest('input,textarea,select,button,video,[contenteditable="true"]')) root.focus({preventScroll:true}); });
  document.addEventListener('keydown', event => { if (event.__cpHandled) return; onKeydown(event); });
}
window.addEventListener('beforeunload', e => { if (state.dirty || state.busy) { e.preventDefault(); e.returnValue = ''; } });
// ---- lifecycle -----------------------------------------------------------
async function init() {
  try {
    await loadDatasets();
    initialized = true;
    await loadVideo();
    await loadEvents();
    loadCrops(state.set).catch(() => {});
    loadFrame(0);
  } catch (error) {
    notice(`${error.message} ${text('The review API is unavailable. Use the project review server, not a file:// URL.')}`, true);
  }
}
function switchMode(mode) {
  if (!Object.hasOwn(modes, mode)) return false;
  if (modes[mode] === state.mode) { state.mode = modes[mode]; return true; }
  if (!canLeave()) return false;
  state.mode = modes[mode];
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
function activate(mode = 'timeline') {
  if (!root || !switchMode(mode)) return false;
  active = true;
  state.focus = {events:'events', balls:'balls', calibration:'anchors', players:'persons', timeline:'timeline', stream:'sources'}[mode] || state.focus;
  notify();
  return true;
}
function deactivate() {
  active = false;
  setPlaying(false);
  root?.querySelectorAll('video').forEach(video => video.pause());
}
// ---- i18n: engine-owned stage strings, EN/中 parity ----------------------
function snapshot() {
  const meta = state.vmeta;
  const selected = {
    none: state.sel.kind === 'none',
    kind: state.sel.kind,
    event: state.sel.kind === 'event' ? state.sel.event : null,
    crop: state.sel.kind === 'ball' ? state.sel.crop : null,
    ball: state.sel.kind === 'ball' ? state.sel.ball : null,
    person: state.sel.kind === 'person' ? state.sel.person : null,
    track: state.sel.kind === 'person' ? state.sel.track : null,
    anchor: state.sel.kind === 'anchor' ? state.sel.anchor : null,
    box: state.sel.kind === 'box' ? state.sel.box : -1
  };
  return {
    lang: root?.lang || 'en',
    dataset: state.dataset, datasets: state.datasets, set: state.set, sets: state.sets,
    frame: {index: state.frame, t: state.t, fps: meta?.fps ?? 0, count: meta?.frame_count ?? 0, duration: meta?.duration ?? 0, kind: meta?.timestamp_kind || '', has: !!state.shotUrl, decoding: state.decoding, playing: state.playing, rate: playbackRate()},
    source: {kind: state.source.kind, label: state.source.kind === 'vod' ? `${state.dataset} · ${meta ? `${Math.round(meta.duration)} s · ${Number(meta.fps).toFixed(3)} fps` : '—'}` : state.source.label, channel: state.source.channel},
    live: {state: state.live.state, error: state.live.error, frame_age_ms: state.live.frame_age_ms, receive_to_result_ms: state.live.receive_to_result_ms, skipped: state.live.skipped, seq: state.live.seq, stale: state.live.stale, attempt: state.live.attempt, detectors: state.live.detectors},
    overlay: {...state.overlay}, drawn: {...state.drawn}, loading: {...state.loading},
    selection: selected, focus: state.focus, eventFilter: state.eventFilter,
    detectors: {...state.detectors},
    events: {items: state.events.map(e => ({id: e.id, type: e.type, t: e.t, nearest_pocket: e.nearest_pocket ?? null, evidence: e.evidence ?? null, verdict: state.annotations[String(e.id)]?.verdict || '', annotation: state.annotations[String(e.id)] || null})), index: state.eventIndex, reviewed: Object.keys(state.annotations).length},
    verdictDraft: state.verdictDraft ?? null,
    balls: {set: state.set, items: state.balls.items.slice(0, 400).map(i => ({file: i.file, t: i.t, score: i.score ?? null, ctx: i.ctx ?? null, label: state.balls.labels[i.file] ?? null})), index: state.balls.index, labels: state.balls.labels},
    persons: {win: state.persons.win, windows: state.persons.windows, tracks: state.persons.tracks.map(t => ({id: t.id, label: t.label ?? null, box: t.box ?? null, seed: Object.values(state.persons.seeds || {}).find(s => s.win === state.persons.win && String(s.track_id) === String(t.id))?.label ?? null})), track: state.persons.track, predictions: state.persons.predictions, status: state.persons.status},
    anchors: {...state.anchors, points: state.anchors.pts.map(p => [...p])},
    corrections: {tool: state.tool, newBoxLabel: state.newBoxLabel || 'ball', box: state.sel.kind === 'box' ? state.sel.box : -1, boxes: state.boxes.length, boxLabel: state.sel.kind === 'box' ? state.boxes[state.sel.box]?.label : null, polygon: !!state.polygon, result: state.fresult ? (state.fresult.correction ? 'manual corrections' : state.fresult.inference ? 'inference' : 'none') : 'none', dirty: state.dirty, inferRunning: state.inferRunning, inferStatus: state.inferStatus},
    receipts: state.receipts.slice(), notice: {...state.notice}, busy: state.busy, dirty: state.dirty
  };
}
// Every state the live processor (live_processing.py: idle / starting / running /
// stopping / stopped / eos / error) and the identity rebuild job can report.
// One map, used by the engine's own status lines and by the vision adapter, so
// no raw English state can reach the UI in 中 mode.
const stateCopy = {
  idle:['idle','空闲'], starting:['starting','启动中'], running:['running','运行中'],
  stopping:['stopping','停止中'], stopped:['stopped','已停止'], eos:['eos','已结束'],
  error:['error','错误'], failed:['failed','失败'], completed:['completed','已完成'], unknown:['unknown','未知']
};
function liveStateText(value, lang = root?.lang) {
  const row = stateCopy[String(value ?? '').toLowerCase()];
  if (!row) return String(value ?? '');
  return lang === 'zh' ? row[1] : row[0];
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
  'Raw decoded frame':'原始解码帧', 'Frame overlays':'帧叠加层',
  'Pick a moment on the scrub strip, or select a cue, then freeze it here.':'在拖动条上选择时刻，或选择一条线索，然后在此冻结。',
  'STALE':'已过期', 'live':'直播', 'Close':'关闭', 'No crop at this frame':'此帧没有裁剪图',
  'The label is written to this crop':'标注将写入此裁剪图', 'Select a crop cue in the rail to label it':'请在左栏选择裁剪图线索以标注',
  'Select a ball or a crop first.':'请先选择球或裁剪图。', 'Select a visible track first.':'请先选择可见的轨迹。',
  'This track has no identity cluster yet.':'此轨迹尚无身份聚类。', 'saving…':'保存中…', 'save failed':'保存失败',
  'Your changes remain on screen; retry when ready.':'更改仍保留在屏幕上，可稍后重试。',
  'Choose a verdict before saving.':'请先选择判定再保存。', 'Saving…':'保存中…',
  'Discard unsaved changes?':'放弃未保存的更改？', 'Live start failed':'直播启动失败', 'STALE state':'已过期状态',
  'Freeze a frame before running inference.':'运行推理前请先冻结一帧。',
  'Choose at least one detector (table, person, balls).':'请至少选择一个检测器（球桌、人物、球）。',
  'Starting inference on frame':'正在启动帧', 'Inference running for frame':'正在对帧运行推理：',
  'Inference failed to start':'推理启动失败', 'Inference failed.':'推理失败。', 'Frame inference failed':'帧推理失败',
  'Inference completed for frame':'帧推理已完成：', 'Inference for frame':'帧', 'finished; freeze that frame to see its overlays.':'推理已完成；冻结该帧可查看叠加层。',
  'Inference overlays updated for the frozen frame.':'冻结帧的推理叠加层已更新。', 'Inference status error':'推理状态错误',
  'Status check failed.':'状态检查失败。', 'Idle.':'空闲。', 'Rebuilding…':'正在重建…', 'Status':'状态',
  'Rebuild failed':'重建失败', 'Status unavailable':'状态不可用', 'A box has invalid coordinates; fix or delete it before saving.':'有标注框坐标无效；请修复或删除后再保存。',
  'Frame load failed':'帧加载失败', 'Tracks unavailable.':'轨迹不可用。', 'No VOD datasets are configured.':'尚未配置录像数据集。',
  'The review API is unavailable. Use the project review server, not a file:// URL.':'复核 API 不可用。请通过项目复核服务器打开，而非 file:// 地址。',
  'Highlight candidates were generated with the wrong-resolution calibration. They are not valid accuracy evidence; inspect the source before judging.':'集锦候选由分辨率不匹配的标定生成，不能作为有效准确率证据；请先检查原始资料再判定。'
};
Object.assign(editorCopy, {
  'Frame unavailable. Choose another time or retry loading.':'帧不可用。请选择其他时间或重新加载。',
  'CANDIDATE · NOT VALIDATED':'候选 · 未验证',
  'Choose a verdict before saving.':'请先选择判定再保存。', 'Freeze a frame first.':'请先冻结一帧。',
  'Unlabeled':'未标注', 'Unknown':'未知', 'Cue · 0':'母球 · 0',
  'Event review':'事件复核', 'Ball labels':'球号标注', 'Table calibration':'球桌标定', 'Player identities':'选手身份', 'Video timeline':'视频时间轴',
  'Frame inference':'帧推理', 'Correction editor':'修正编辑器', 'Save corrections for this frame':'保存此帧修正',
  'Balls · SAM3 on CPU (slow)':'球 · CPU 上的 SAM3（较慢）', 'LOCAL INGESTED VOD ONLY · NO LIVE SOURCES':'仅限本地导入录像 · 无直播源',
  'The scrubber and jumps address raw decoded frame indexes (nominal CFR time = frame ÷ fps; not VFR-exact). Step buttons fetch exact decoded frames from the review server.':'拖动条和跳转使用原始解码帧索引（名义固定帧率时间 = 帧 ÷ fps，并非精确可变帧率时间）。步进按钮从复核服务器获取精确解码帧。',
  'Frame inference covers this single decoded frame only. It cannot detect shots or pots — event inference needs time windows and is out of scope here.':'帧推理仅覆盖此单张解码帧，无法检测击球或入袋；事件推理需要时间窗口，不在此功能范围内。',
  'Drag boxes or corner handles; arrow keys nudge the selected box (Shift = 10 px). Ball centers follow their box. Drag table polygon corners. Saving writes manual corrections for this exact frame; saved inference is never overwritten.':'拖动标注框或角点控制柄；方向键微调所选框（Shift = 10 像素）。球心随标注框移动。可拖动球桌多边形角点。保存仅写入此精确帧的人工修正，绝不覆盖已保存的推理结果。',
  'Infer results and manual corrections are saved separately. Inference never overwrites your correction file.':'推理结果和人工修正分别保存。推理不会覆盖修正文件。',
  'Saved':'已保存', 'Track':'轨迹', 'Track window':'轨迹窗口', 'Delete selected':'删除所选', 'Draw box':'绘制标注框', 'Select / move':'选择 / 移动',
  'Selected label':'所选标注', 'New box label':'新框标注', 'Add table polygon':'添加球桌多边形', 'Clear polygon':'清除多边形',
  'solid':'实色', 'stripe':'花色', 'eight':'黑八', 'person':'人物', 'cue':'母球', 'ball':'球', 'table':'球桌'
});
// Only UI-owned copy is eligible: never walk notes, source facts, or raw data.
const editorTemplates = [
  [/^(.+) · detector score (.+) \(not accuracy\)$/, (source, score) => `${source} · 检测器分数 ${score}（非准确率）`],
  [/^Ball (\d+)$/, number => `球 ${number}`],
  [/^RAW DECODED FRAME · (.+) · frame (\d+) · nominal (.+)s \((.+)\) · OVERLAYS: (.+)$/, (dataset, frame, time, kind, overlays) => `原始解码帧 · ${dataset} · 帧 ${frame} · 名义时间 ${time}s (${kind}) · 叠加层：${({'manual corrections':'人工修正',inference:'推理',none:'无',unified:'统一检测'})[overlays] || overlays}`],
  [/^([\d.]+) fps · (\d+) frames · (.+) · nominal CFR timestamps$/, (fps, frames, duration) => `${fps} fps · ${frames} 帧 · ${duration} · 名义 CFR 时间戳`],
  [/^Frame load failed: ([\s\S]*)$/, detail => `帧加载失败：${detail}`],
  [/^Save failed: ([\s\S]*)\. Your changes remain on screen; retry when ready\.$/, detail => `保存失败：${detail}。更改仍保留在屏幕上，可稍后重试。`],
  [/^Save failed: ([\s\S]*)\. Your edits remain on screen; retry when ready\.$/, detail => `保存失败：${detail}。编辑仍保留在屏幕上。`],
  [/^Live start failed: ([\s\S]*)$/, detail => `直播启动失败：${detail}`],
  [/^Status: (.+?)( — [\s\S]*)?$/, (status, detail = '') => `状态：${liveStateText(status, 'zh')}${detail}`],
  [/^Status unavailable: ([\s\S]*)$/, detail => `状态不可用：${detail}`],
  [/^Rebuild failed: ([\s\S]*)$/, detail => `重建失败：${detail}`],
  [/^Inference completed for frame (\d+)\.$/, frame => `帧 ${frame} 推理已完成。`],
  [/^Inference running for frame (\d+): (.*)…$/, (frame, stage) => `正在对帧 ${frame} 运行推理：${stage}…`],
  [/^Starting inference on frame (\d+) \((.*)\)…$/, (frame, detectors) => `正在启动帧 ${frame} 的推理（${detectors}）…`],
  [/^Frame inference failed: ([\s\S]*)$/, detail => `帧推理失败：${detail}`],
  [/^Corrections saved for frame (\d+)\.$/, frame => `帧 ${frame} 的修正已保存。`]
];
function text(copy) {
  if (root?.lang !== 'zh') return copy;
  if (Object.hasOwn(editorCopy, copy)) return editorCopy[copy];
  for (const [pattern, format] of editorTemplates) { const match = copy.match(pattern); if (match) return format(...match.slice(1)); }
  return copy;
}
function updateOverlayFacts(source) {
  state.drawn.source = source;
  notify();
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
  root.querySelectorAll('#content label, #content button, #content option, #content .empty, #content .hint, #content .facts, #stage-popover .pop-head, #stage-popover .pop-note').forEach(el => {
    for (const node of el.childNodes) if (node.nodeType === 3) translate(node, 'nodeValue');
  });
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
  const changed = root.lang !== lang;
  root.lang = lang; root.dataset.theme = theme;
  try { localStorage.setItem('corner-pocket-lang', lang); localStorage.setItem('corner-pocket-theme', theme); } catch (_) {}
  for (const [kind, value, values] of [['lang',lang,['en','zh']],['theme',theme,['dark','light']]]) {
    for (const name of values) { const button = $(`#${kind}-${name}`); if (!button) continue; button.classList.toggle('active', name === value); button.setAttribute('aria-pressed', String(name === value)); }
  }
  if (!copyObserver && typeof MutationObserver !== 'undefined') {
    copyObserver = new MutationObserver(translateEditor);
    copyObserver.observe(root, {childList:true, subtree:true, characterData:true});
  }
  translateEditor();
  root.querySelectorAll('[data-i18n], [data-i18n-html]').forEach(el => {
    const html = el.hasAttribute('data-i18n-html'), property = html ? 'innerHTML' : 'textContent';
    const key = el.getAttribute(html ? 'data-i18n-html' : 'data-i18n');
    if (!englishCopy.has(el)) englishCopy.set(el, el[property]);
    el[property] = lang === 'zh' ? zhCopy[key] || englishCopy.get(el) : englishCopy.get(el);
  });
  // Re-paint engine-rendered stage strings through text() in the new language.
  if (changed && state.vmeta) { renderStage(); }
  notify();
}
window.CornerPocketReview = {
  mount, activate, deactivate, setAppearance,
  canLeave: () => !active || canLeave(),
  subscribe, snapshot, notify,
  seek, seekTime, stepFrame, setPlaying, setOverlay, toggleOverlay, freeze, setDetector, setEventFilter,
  selectEvent, selectCrop, selectTrack, selectTrackAndSeek, selectAnchor, selectBox, clearSelection,
  selectStageBall, selectStagePerson,
  saveVerdict, cycleVerdict, setVerdictDraft, setShooter, setNote, labelBall, setSeed, seedIdentity,
  saveAnchors, saveCorrections, runInference, rebuild, refreshRebuild, setWindow,
  setTool, setBoxLabel, deleteBox, addPolygon, clearPolygon, setNewBoxLabel, nudgeAnchor,
  setDataset, loadAnchors, loadPersons, loadTracks, loadCrops, loadSeeds, loadEvents,
  applyLiveStatus, ingestLiveFrame, setLiveAttempt, clearLiveError, liveStateText,
  counts,
  text: copy => text(copy)
};
const standaloneRoot = document.querySelector('#review-root');
if (standaloneRoot) { mount(standaloneRoot); activate(); }
})();
