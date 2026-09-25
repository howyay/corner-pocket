(() => {
'use strict';
// Corner Pocket review engine: ONE stage surface (live edge or VOD frame, the
// same <img> fed by different sources), no sub-tab navigation. This module owns
// every frame request, every guard (dirty / busy / frame token) and every write
// path. annotator/vision-stage.js renders the source chips, cues rail, layer
// chips, inspector and scrub strip from snapshot() and drives this engine
// through the public API below; it owns no frame state and performs no fetch.
let root = null, active = false, mounting = null, initialized = false;
// What the embedding shell hands the engine at mount (e.g. reloadRoster); the
// standalone page mounts without any.
let hooks = {};
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
  cloth:{reference:null,verdict:{state:'none',reason:'no detection'},quad:null,polygon:null,pockets:{source:null,count:0,reference:null},refusal:null},
  loading:{overlay:false,since:0},
  live:{state:'idle',error:null,frame_age_ms:null,receive_to_result_ms:null,skipped:0,seq:null,receivedAt:null,stale:false,detections:null,attempt:null,detectors:['table','person']},
  source:{kind:'vod',label:'',channel:null},
  sel:{kind:'none',crop:null,ball:null,person:null,track:null,anchor:0,event:null,box:-1},
  focus:'events',
  receipts:[], notice:{text:'',error:false},
  dirty:false, busy:false, epoch:0, decoding:false, playing:false, playTimer:null, unifiedTimer:null, pendingSeek:null,
  playback:{on:false, playing:false, event:null, from:0, to:0, loops:0, seek:NaN},
  detectors:{table:true,person:true,balls:false}, inferTimer:null, inferRunning:false, inferStatus:'',
  // Enrolling the person on screen: the preview only reads, the confirm is the
  // one write, and both live here so the rail renders one truth.
  enroll:{status:'idle', payload:null, name:'', startedAt:0, error:null},
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
    notice(`Save failed: ${error.message}. Your changes remain on screen; retry when ready.`, true);
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
// Box provenance is per box, not per frame. A stored correction is the
// operator's (`manual`), a stored inference result is the model's (`auto`), and
// an edit made in this session makes that one box the operator's - the frame-level
// flag this used to share painted every model box YOURS as soon as anything on the
// frame was dirty, which is not what the operator did.
function displayBoxes(result) {
  // Both layers, always: the stored correction is the operator's (manual) and the
  // stored inference is the model's (auto). A correction used to replace the
  // inference list, so the model's boxes vanished exactly when the operator most
  // needed to see where the two disagreed.
  const source = result?.correction ? 'manual corrections' : result?.inference ? 'inference' : 'none';
  const manual = (result?.correction?.boxes || []).map(b => ({label: b.label, bbox: b.bbox.slice(), score: b.score, origin: 'manual', edited: false}));
  const model = (result?.inference?.boxes || []).map(b => ({label: b.label, bbox: b.bbox.slice(), score: b.score, origin: 'auto', edited: false}));
  const polygon = result?.correction?.table_polygon || result?.inference?.table_polygon || null;
  return {source, boxes: [...manual, ...model], polygon: polygon ? polygon.map(p => [...p]) : null};
}
// The one place a box's origin changes: an edit by the operator in this session.
function markBoxEdited(box) { if (box) { box.origin = 'manual'; box.edited = true; } }
function boxTagKind(box) { return box?.origin === 'manual' ? 'manual' : 'auto'; }
// An edited model box becomes the operator's, but the model's original stays on
// the stage as a frozen ghost until the frame is reloaded: the operator can see
// what the model said before they moved it, and the ghost is never saveable.
function ghostModelBox(box) {
  if (!box || box.origin !== 'auto' || box.frozen) return;
  state.boxes.push({label: box.label, bbox: box.bbox.slice(), score: box.score, origin: 'auto', edited: true, frozen: true});
}
function boxIou(a, b) {
  const [ax1, ay1, ax2, ay2] = a, [bx1, by1, bx2, by2] = b;
  const width = Math.min(ax2, bx2) - Math.max(ax1, bx1), height = Math.min(ay2, by2) - Math.max(ay1, by1);
  if (width <= 0 || height <= 0) return 0;
  const inter = width * height;
  const union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter;
  return union > 0 ? inter / union : 0;
}
// Two boxes describe the same object when they overlap by half or more, or when
// their centres are within 8 px. The overlap bar is the usual "same object" bar
// between two box sets; the centre fallback exists because the balls are small -
// the same ball with a slightly different radius can drop under the IoU bar while
// sitting on the same centre - and 8 px is below the smallest radius drawn on the
// stage (9 px), so it can never merge two different balls.
function boxesMatch(a, b) {
  if (boxIou(a.bbox, b.bbox) >= 0.5) return true;
  const [ax, ay] = boxCenter(a), [bx, by] = boxCenter(b);
  return Math.hypot(ax - bx, ay - by) <= 8;
}
// A model box that a manual box already describes is drawn as that box's faint
// counterpart: agreement reads as one clean box, a disagreement as a visible gap.
function isPairedModel(box, boxes) {
  if (box?.origin !== 'auto') return false;
  return boxes.some(other => other !== box && other.origin === 'manual' && boxesMatch(box, other));
}
function ballLabelText(value) { return value === undefined || value === null ? 'Unlabeled' : value === -1 || value === 'u' ? 'Unknown' : value === 0 ? 'Cue · 0' : `Ball ${value}`; }
// ---- pocket vocabulary, overlay provenance, geometry clearance ------------
// Stored pocket keys are pool-table rail terms (head rail / foot rail). On the
// imagery they read as body parts - a marker labelled `head-left` beside a
// player is read as that player's head - so every DISPLAYED label goes through
// this map at render time. Stored keys and APIs never change.
const POCKET_LABELS = {
  'head-left':'top-left', 'head-right':'top-right',
  'foot-left':'bottom-left', 'foot-right':'bottom-right',
  'left-side':'left-middle', 'right-side':'right-middle'
};
const POCKET_WORDS = {
  'top-left':['top-left','左上'], 'top-right':['top-right','右上'],
  'bottom-left':['bottom-left','左下'], 'bottom-right':['bottom-right','右下'],
  'left-middle':['left-middle','左中'], 'right-middle':['right-middle','右中']
};
function pocketWord(token, lang) {
  const shown = POCKET_LABELS[String(token)] || String(token ?? '');
  const row = POCKET_WORDS[shown];
  return row ? (lang === 'zh' ? row[1] : row[0]) : shown;
}
// `nearest_pocket` is a composed string ("foot-right (124mm)", "557mm from
// foot-right"): the position word is translated, the measurement is kept.
function pocketText(value, lang = root?.lang) {
  const raw = String(value ?? '').trim();
  const from = raw.match(/^([\d.]+)\s*mm from ([\w-]+)$/);
  if (from) return lang === 'zh' ? `距${pocketWord(from[2], lang)} ${from[1]}mm` : `${from[1]}mm from ${pocketWord(from[2], lang)}`;
  const near = raw.match(/^([\w-]+)\s*\((.*)\)$/);
  if (near) return `${pocketWord(near[1], lang)} (${near[2]})`;
  return pocketWord(raw, lang);
}
// Mean corner distance is the clearance bar for the automatic cloth quad. The
// reference's own temporal jitter is 3.95 px median / 5.59 px p90; the
// documented disagreement between the old and the refined vod30 corner sets is
// 28-39 px; the per-frame detector path measured 59.9-145 px mean on sampled
// vod30 frames. 40 px (~76 mm at the documented 1.9 mm/px) sits above the known
// systematic disagreement and below every measured detector failure.
const CLOTH_TOLERANCE_PX = 40;
function clothTolerance(reference, frameWidth) {
  const base = Number(reference?.width), width = Number(frameWidth);
  return Number.isFinite(base) && base > 0 && Number.isFinite(width) && width > 0 ? CLOTH_TOLERANCE_PX * (width / base) : CLOTH_TOLERANCE_PX;
}
function quadPoints(value) {
  if (!Array.isArray(value) || value.length < 4) return null;
  const points = value.slice(0, 4).map(p => Array.isArray(p) ? [Number(p[0]), Number(p[1])] : null);
  return points.every(p => p && Number.isFinite(p[0]) && Number.isFinite(p[1])) ? points : null;
}
// A quad that starts at another vertex is still the same quadrilateral, so the
// best of the four cyclic alignments is scored; a mirrored quad is a different
// projection and never aligns.
function quadDistance(quad, reference) {
  const points = quadPoints(quad), ref = quadPoints(reference);
  if (!points || !ref) return null;
  let best = null;
  for (let shift = 0; shift < 4; shift++) {
    const distances = ref.map((p, i) => Math.hypot(points[(i + shift) % 4][0] - p[0], points[(i + shift) % 4][1] - p[1]));
    const mean = distances.reduce((sum, d) => sum + d, 0) / 4;
    if (!best || mean < best.mean) best = {mean, max: Math.max(...distances), shift, distances};
  }
  return best;
}
// A painted quad must also be a plausible table: inside the frame, four
// distinct corners, and an area a table can actually occupy (the saved vod30
// quad covers 9.5% of its frame).
function quadSanity(points, width, height) {
  if (!points) return 'malformed';
  const w = Number(width), h = Number(height);
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return 'malformed';
  for (const [x, y] of points) if (x < -2 || y < -2 || x > w + 2 || y > h + 2) return 'outside frame';
  for (let i = 0; i < 4; i++) { const a = points[i], b = points[(i + 1) % 4]; if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 8) return 'degenerate corner'; }
  const area = Math.abs(points.reduce((sum, p, i) => sum + p[0] * points[(i + 1) % 4][1] - points[(i + 1) % 4][0] * p[1], 0)) / 2;
  const fraction = area / (w * h);
  return fraction >= 0.02 && fraction <= 0.9 ? null : `implausible area ${(fraction * 100).toFixed(1)}%`;
}
// Verdict for one frame's automatic quad: ok (checked and within tolerance),
// off (checked and refused), unverified (no saved reference for this dataset),
// none (nothing detected). Only `ok` and `unverified` may be painted.
//
// What this check is now: the detector searches around the same saved anchors it
// is compared against here (src/frame_inference.app_prior_for), because the
// reference it used to search around - out/corners_30min_v2.json - sits 67-90 px
// off the visible cloth on its left rail and made every frame fail. A pass is
// therefore a *drift bound* on the saved hand geometry ("the refinement did not
// wander far from the operator's corners"), not an independent test that the quad
// is the table: the evidence for the boundary is the refinement's own per-side
// measurement of this frame. The facts line prints the measured drift, so the
// number is visible instead of hidden behind a pass/fail. See
// docs/app-path-refusal.md.
function validateCloth(corners, reference, frameWidth, frameHeight) {
  const points = quadPoints(corners);
  const bad = quadSanity(points, frameWidth, frameHeight);
  if (bad) return {state:'off', reason:'invalid geometry', detail:bad, mean:null, max:null, tolerance:null, source:null};
  const ref = quadPoints(reference?.points);
  if (!ref) return {state:'unverified', reason:'no saved reference', detail:'', mean:null, max:null, tolerance:null, source:null};
  const tolerance = clothTolerance(reference, frameWidth);
  const fit = quadDistance(points, ref);
  return fit.mean <= tolerance
    ? {state:'ok', reason:'within tolerance', detail:'', mean:fit.mean, max:fit.max, tolerance, source:reference.source}
    : {state:'off', reason:'off saved corners', detail:'', mean:fit.mean, max:fit.max, tolerance, source:reference.source};
}
// A saved frame correction belongs to exactly one (dataset, frame, source
// size). The server files it under the dataset and frame it was written for,
// but a re-encode or a copied file can leave a correction whose pixels describe
// another image; drawing it over the current frame would present foreign
// geometry as the operator's current correction. Anything that does not match
// is refused, reported, and never painted.
function correctionScope(correction, frame) {
  if (!correction) return {ok:true, owner:null, expected:null, detail:null};
  const expected = `${frame?.dataset ?? '?'} frame ${frame?.frame ?? '?'} @ ${frame?.width ?? '?'}×${frame?.height ?? '?'}`;
  const owner = `${correction.dataset ?? '?'} frame ${correction.frame_index ?? '?'} @ ${correction.width ?? '?'}×${correction.height ?? '?'}`;
  const detail = [];
  if (frame?.dataset !== undefined && correction.dataset !== undefined && String(correction.dataset) !== String(frame.dataset)) detail.push(`dataset ${correction.dataset} ≠ ${frame.dataset}`);
  if (frame?.frame !== undefined && correction.frame_index !== undefined && Number(correction.frame_index) !== Number(frame.frame)) detail.push(`frame ${correction.frame_index} ≠ ${frame.frame}`);
  for (const [label, saved, live] of [['width', correction.width, frame?.width], ['height', correction.height, frame?.height]]) {
    if (saved === undefined || saved === null || live === undefined || live === null) continue;
    if (Number(saved) !== Number(live)) detail.push(`${label} ${saved} ≠ ${live}`);
  }
  // A file that declares no scope at all cannot be tied to this frame either.
  const declared = ['dataset','frame_index','width','height'].filter(key => correction[key] !== undefined && correction[key] !== null);
  if (!declared.length) detail.push('no scope metadata');
  return {ok: !detail.length, owner, expected, detail: detail.join(', ')};
}
// Every drawn geometry group says who drew it: MODEL (detector / inference
// output) or YOURS (the operator's saved correction or live edit). The dashed
// model vs solid editable styling stays; the tag is what makes the difference
// readable without the facts line.
const SRC_TAG_HEIGHT = 18, SRC_TAG_FONT = 14;
function glyphWidth(value, size) {
  let width = 0;
  for (const ch of String(value ?? '')) width += /[\u2e80-\u9fff\uff00-\uffef]/.test(ch) ? size : size * 0.62;
  return width;
}
function sourceTagLabel(kind) { return text(kind === 'manual' ? 'YOURS' : kind === 'calib' ? 'CALIB' : kind === 'event' ? 'EVENT' : 'MODEL'); }
function sourceTagWidth(kind) { return Math.round(glyphWidth(sourceTagLabel(kind), SRC_TAG_FONT) + 14); }
function sourceTag(x, y, kind) {
  const label = sourceTagLabel(kind), width = sourceTagWidth(kind);
  return `<g class="o-src ${kind}" data-src="${kind}"><rect x="${Math.round(x)}" y="${Math.round(y)}" width="${width}" height="${SRC_TAG_HEIGHT}" rx="3"></rect><text x="${Math.round(x + 7)}" y="${Math.round(y + 13)}">${esc(label)}</text></g>`;
}
// The tag and the group's own label share one line, so two sources drawn on the
// same spot stay readable instead of stacking four rows of small text.
function tagRow(x, y, kind, label, cls = 'o-label') {
  const row = sourceTag(x, y, kind);
  if (!label) return row;
  return `${row}<text class="${cls}" x="${Math.round(x + sourceTagWidth(kind) + 6)}" y="${Math.round(y + 13)}">${esc(label)}</text>`;
}
function quadOrigin(points) {
  const xs = points.map(p => Number(p[0])), ys = points.map(p => Number(p[1]));
  return [Math.min(...xs), Math.min(...ys)];
}
// A person chip is a label, not a box: it names the detection and its track,
// and states `unbound` while the track has a cluster but no player name.
function personChip(per, track) {
  if (per?.player_id) return String(per.player_id);
  const id = track === undefined || track === null || track === '' ? '—' : track;
  const prefix = per?.cluster_id === undefined || per?.cluster_id === null ? text('person') : text('unbound');
  return `${prefix} · ${text('track')} ${id}`;
}
// The dataset's saved six anchors are the two side pockets plus the four cloth
// corners, in the canonical order the calibration uses. They are the trusted
// pocket geometry when this frame's model quad cannot be trusted, so the pockets
// layer keeps working instead of going dark behind a refused quad.
const POCKET_ANCHOR_ORDER = ['head-left', 'head-right', 'foot-right', 'foot-left', 'left-side', 'right-side'];
function calibratedPockets(reference) {
  const points = Array.isArray(reference?.points) ? reference.points : null;
  if (!points || points.length < POCKET_ANCHOR_ORDER.length) return null;
  const rows = points.slice(0, POCKET_ANCHOR_ORDER.length).map((p, i) => {
    const cx = Number(p?.[0]), cy = Number(p?.[1]);
    return Number.isFinite(cx) && Number.isFinite(cy) ? {name: POCKET_ANCHOR_ORDER[i], cx, cy} : null;
  });
  return rows.every(Boolean) ? rows : null;
}
// The dataset's own saved cloth quad - the static-camera geometry the operator
// placed, or the saved calibration. While the video runs this is the only cloth
// the stage may draw: a per-frame detected quad describes a frame, not a moving
// picture, and the tag says which of the two is on screen (MODEL vs CALIB).
function staticQuad() {
  const points = state.cloth.reference?.points;
  const quad = Array.isArray(points) && points.length >= 4 ? points.slice(0, 4).map(p => [Number(p[0]), Number(p[1])]) : null;
  return quad && quad.every(p => Number.isFinite(p[0]) && Number.isFinite(p[1])) ? quad : null;
}
// The pockets the stage actually draws, so an event's target pocket highlight is
// the marker the operator can see rather than a second, differently-calibrated
// point a few pixels away. Falls back to the event's own projected pocket.
function drawnPocket(name, event) {
  const pockets = calibratedPockets(state.cloth.reference) || [];
  const drawn = name ? pockets.find(p => p.name === name) : null;
  if (drawn) return [drawn.cx, drawn.cy];
  const px = event?.pocket_px;
  return Array.isArray(px) && px.length === 2 && px.every(Number.isFinite) ? [Number(px[0]), Number(px[1])] : null;
}
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
  } catch (error) { if (epoch === state.epoch && request === trackRequest) notice(`Tracks unavailable. ${error.message}`, true); }
}
async function loadSeeds() {
  try { const data = await api('/api/vod30/seeds'); state.persons.seeds = data.seeds || {}; notify(); } catch (_) {}
}
// The clearance reference for the automatic cloth quad: the dataset's saved six
// anchors when they exist, otherwise the projection of its saved calibration.
// Framing is per segment, so the reference is a per-dataset value, is compared
// only against VOD frames of that dataset, and is never used for a live source.
// All six points are kept: the first four are the cloth quad the quad check
// needs, and the same six are the dataset's trusted pocket geometry.
async function loadClothReference() {
  state.cloth.reference = null;
  if (state.dataset !== 'vod30') { paintOverlay(); notify(); return null; }
  try {
    const data = await api(`/api/${enc('vod30')}/anchors?t=${enc(state.anchors.t)}`);
    const saved = Array.isArray(data.pts) && data.pts.length >= 4;
    const suggested = Array.isArray(data.suggested_pts) && data.suggested_pts.length >= 4;
    if (saved || suggested) state.cloth.reference = {
      points: (saved ? data.pts : data.suggested_pts).slice(0, POCKET_ANCHOR_ORDER.length).map(p => [Number(p[0]), Number(p[1])]),
      source: saved ? 'saved anchors' : 'saved calibration',
      width: Number(data.width) || state.frameWidth,
      height: Number(data.height) || state.frameHeight
    };
  } catch (_) { state.cloth.reference = null; }
  paintOverlay(); notify();
  return state.cloth.reference;
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
    if (epoch === state.epoch && request === state.frameReq) notice(`Frame load failed: ${error.message}`, true);
  } finally {
    if (epoch === state.epoch && request === state.frameReq) {
      state.busy = false; state.decoding = false;
      const queued = state.pendingSeek; state.pendingSeek = null; notify();
      if (queued !== null && queued !== undefined) loadFrame(queued);
    }
  }
}
function applyFrameResult() {
  // Scope first: a correction whose stored scope is not this frame is dropped
  // from state entirely, so no later code path (painter, counters, save body)
  // can present foreign geometry as this frame's manual correction.
  const context = {dataset: state.dataset, frame: state.frame, width: state.frameWidth, height: state.frameHeight};
  const scope = correctionScope(state.fresult?.correction, context);
  state.cloth.refusal = scope.ok ? null : scope;
  if (!scope.ok && state.fresult) state.fresult.correction = null;
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
  // Freezing is the exit from video mode: pause the picture and decode the
  // still through the unchanged guarded path below.
  exitPlayback();
  if (state.busy) { state.pendingSeek = n; notify(); return true; }
  loadFrame(n); return true;
}
function seekTime(t) { const meta = state.vmeta; if (!meta) return false; return seek(frameFromTime(meta, t)); }
function stepFrame(delta) { if (!state.vmeta || !canLeave()) return false; return seek((state.pendingSeek ?? state.frame) + delta); }
function setPlaying(playing) {
  state.playing = !!playing;
  clearTimeout(state.playTimer); state.playTimer = null;
  const video = stageVideo();
  if (state.playing) {
    if (video && videoReady(video)) {
      const at = Number(video.currentTime) || Number(state.t) || 0;
      const keep = state.playback.on && state.sel.kind === 'event' ? state.playback : null;
      // Playing drops the frozen frame's detections: the picture is moving.
      dropPerFrame();
      state.playback = {on:true, playing:false, event:keep ? keep.event : null,
                        from:keep ? keep.from : at, to:keep ? keep.to : 0, loops:keep ? keep.loops : 0, seek:NaN};
      startVideo(video, keep ? keep.from : at);
      renderStage();
    } else tickPlayback();   // no stage video (live edge): the decode pump stays the fallback
  } else {
    if (video && !video.paused) video.pause();
    state.playback.playing = false;
    renderStage();
  }
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
// ---- the stage video: one moving surface, one overlay ---------------------
// The stage used to be a still only: the video now runs inside it, under the
// same SVG overlay and in the same coordinate space (both are 100% width of the
// figure with the frame's aspect, the SVG viewBox stays the frame's pixels).
// Freezing leaves video mode and runs the still path unchanged - the dirty /
// busy / frame-token guards, /api/frame and /api/unified are all still there.
//
// Honesty rule, and the reason this is written down: everything the painter
// draws for a *frame* (balls, persons, boxes, the detected quad) belongs to one
// decoded frame. The moment the picture moves those detections are stale, so
// they are dropped and not drawn until the operator freezes again. Only the
// static-per-dataset layers (cloth quad, pockets, anchors) and the selected
// event's own geometry are drawn over moving video, and the stage says so.
const CLIP_BEFORE_S = 1.5, CLIP_AFTER_S = 2.5;
function videoSrc() { return state.source.kind === 'live' ? null : `/media/${enc(state.dataset)}/video`; }
// Per-frame detections describe one frame. Dropping them is not a cache flush:
// it is the only way a stale ball marker can never survive into playback.
function dropPerFrame() {
  state.unified = null; state.fresult = null; state.boxes = []; state.polygon = null;
  state.dirty = false; state.drawn.perFrame = 0;
  if (state.sel.kind === 'box') state.sel = {...state.sel, kind:'none', box:-1};
}
function eventWindow(event) {
  const t = Number(event?.t), at = Number.isFinite(t) ? t : 0;
  const meta = state.vmeta;
  const from = Math.max(0, at - CLIP_BEFORE_S);
  const to = Math.min(Number(meta?.duration) || at + CLIP_AFTER_S, at + CLIP_AFTER_S);
  return {from, to: Math.max(from + 0.2, to), before: CLIP_BEFORE_S, after: CLIP_AFTER_S};
}
function exitPlayback() {
  const video = stageVideo();
  if (video && video.paused === false) video.pause();
  state.playback = {on:false, playing:false, event:null, from:0, to:0, loops:0, seek:NaN};
  state.playing = false;
}
function bindVideo(video) {
  if (!video.dataset || video.dataset.bound) return video;
  video.dataset.bound = '1';
  video.onplay = () => { state.playback.playing = true; state.playing = true; renderStage(); notify(); };
  video.onpause = () => { state.playback.playing = false; state.playing = false; notify(); };
  video.onloadedmetadata = () => {
    if (state.playback.on && Number.isFinite(state.playback.seek)) { video.currentTime = state.playback.seek; state.playback.seek = NaN; }
    renderStage();
  };
  // Loop the event window, and keep the strip honest about where the picture is.
  video.ontimeupdate = () => {
    const playback = state.playback, meta = state.vmeta;
    const now = Number(video.currentTime) || 0;
    state.t = now;
    if (meta) state.frame = clampFrame(frameFromTime(meta, now), meta);
    if (playback.on && playback.event && playback.to > playback.from && now >= playback.to - 0.03) {
      playback.loops++;
      video.currentTime = playback.from;
    }
    notify();
  };
  video.onerror = () => notice(text('The stage video failed to load; freeze a frame to inspect it as a still.'), true);
  return video;
}
function videoReady(video) {
  const src = videoSrc();
  if (!src) return false;
  if (video.getAttribute('src') !== src) { video.setAttribute('src', src); video.load(); }
  return true;
}
// The mounted <video>, or null when there is none. A real element has a dataset,
// getAttribute and play(); a host without them (the test harness, the live edge)
// simply has no stage video and keeps the old decode-rate pump.
function stageVideo() {
  const video = $('#t-video');
  return video && video.dataset && video.getAttribute && typeof video.play === 'function' ? bindVideo(video) : null;
}
function startVideo(video, at) {
  if (video.readyState >= 1) { try { video.currentTime = at; } catch (_) {} }
  else state.playback.seek = at;
  const started = video.play();
  // The element is the source of truth for "is the picture moving": calling
  // play() on an element that already plays fires no `play` event, so the flag
  // is set here and corrected by the element's own handlers afterwards.
  state.playback.playing = video.paused === false;
  state.playing = state.playback.playing;
  if (started && typeof started.catch === 'function') started.catch(() =>
    notice(text('The browser refused to play the stage video; freeze a frame instead.'), true));
}
// Is the stage video actually moving? Read from the element, never from a flag
// that a missed event can leave stale - the chip must not claim a paused stage.
function videoPlaying() {
  const video = $('#t-video');
  return !!(video && state.playback.on && video.paused === false);
}
// Selecting a cue plays its window on the stage and loops in it: the evidence is
// the video itself, not a second player in the inspector.
function playEvent(index) {
  const event = state.events[index]; if (!event) return false;
  if (!canLeave()) return false;
  state.eventIndex = index;
  state.verdictDraft = null; state.shooterDraft = null; state.noteDraft = null;
  state.sel = {kind:'event', event, crop:null, ball:null, person:null, track:null, anchor:0, box:-1};
  state.focus = 'events';
  dropPerFrame();
  const window_ = eventWindow(event);
  state.playback = {on:true, playing:false, event, from:window_.from, to:window_.to, loops:0, seek:window_.from};
  const video = stageVideo();
  if (!video || !videoReady(video)) { state.playback.on = false; seekTime(event.t); notify(); return true; }
  startVideo(video, window_.from);
  renderStage(); notify();
  return true;
}
// The facts line is derived from what the painter actually drew, so
// "overlays: none" while nodes are drawn is structurally impossible.
// ---- stage rendering -----------------------------------------------------
function stageHTML() {
  const w = state.frameWidth || 1280, h = state.frameHeight || 720;
  return `<figure class="stage" id="stage">
    <video id="t-video" playsinline muted preload="metadata" hidden></video>
    <img id="t-img" alt="${esc(text('Raw decoded frame'))}" ${state.shotUrl ? `src="${esc(state.shotUrl)}"` : ''}>
    <svg id="t-overlay" role="group" aria-label="${esc(text('Frame overlays'))}" viewBox="0 0 ${w} ${h}"></svg>
    <div class="stage-empty" id="stage-empty" ${state.shotUrl || state.liveShift ? 'hidden' : ''}>${esc(text('Pick a moment on the scrub strip, or select a cue, then freeze it here.'))}</div>
    <div class="stage-live" id="stage-live" ${state.source.kind === 'live' ? '' : 'hidden'}></div>
    <div class="stage-play" id="stage-play" role="status" hidden></div>
    <div class="stage-note" id="stage-note" role="status" hidden></div>
    <div class="stage-popover" id="stage-popover" hidden></div>
  </figure>`;
}
function renderStage() {
  const content = $('#content');
  if (!content || !content.dataset) return;   // no real stage host: nothing to render into
  if (content.dataset.stage !== '1' || !$('#t-overlay')) { content.dataset.stage = '1'; content.innerHTML = stageHTML(); }
  const playing = !!state.playback.on;
  const video = $('#t-video');
  let videoShown = false;
  if (video && video.dataset) {
    videoShown = playing && !!stageVideo() && videoReady(video);
    video.hidden = !videoShown;
  }
  const img = $('#t-img');
  if (img && state.shotUrl && img.getAttribute('src') !== state.shotUrl) img.src = state.shotUrl;
  const showStill = !!state.shotUrl && !videoShown;
  if (img) img.hidden = !showStill;
  const empty = $('#stage-empty'); if (empty) empty.hidden = !!state.shotUrl || videoShown;
  const svg = $('#t-overlay'); if (svg) { svg.setAttribute('viewBox', `0 0 ${state.frameWidth || 1280} ${state.frameHeight || 720}`); if (!svg.dataset.bound) { svg.dataset.bound = '1'; svg.onpointerdown = overlayPointerDown; svg.onpointermove = overlayPointerMove; svg.onpointerup = svg.onpointercancel = overlayPointerUp; } }
  paintOverlay(); paintLiveChip(); paintPlayChip(); paintPopover(); notify();
}
// What the stage is doing, next to the picture it is doing it to: whether the
// video runs, which window it loops in, and the rule that per-frame detections
// only come back on a freeze. No fake liveness.
function paintPlayChip() {
  const chip = $('#stage-play'); if (!chip) return;
  const playback = state.playback;
  if (!playback.on) { chip.hidden = true; chip.textContent = ''; return; }
  chip.hidden = false;
  const moving = videoPlaying();
  chip.dataset.playing = moving ? '1' : '0';
  const parts = [moving ? text('playing') : text('paused')];
  if (playback.event) parts.push(`${text('window')} ${timecode(playback.from)} → ${timecode(playback.to)}`);
  parts.push(text(moving ? 'per-frame detections update on freeze' : 'per-frame detections return on freeze'));
  chip.textContent = parts.join(' · ');
}
// A Twitch VOD replay reaches the stage through the live path, but it is never
// called live: the server's own status (kind 'vod-replay') decides the word.
function liveIsReplay(live = state.live) { return live?.source?.kind === 'vod-replay' || live?.replay?.kind === 'vod-replay'; }
function paintLiveChip() {
  const chip = $('#stage-live'); if (!chip) return;
  const live = state.live, replay = liveIsReplay(live);
  chip.hidden = false;
  if (state.source.kind === 'live' && live.stale) chip.className = 'stage-live stale';
  else if (state.source.kind === 'live') chip.className = replay ? 'stage-live replay' : 'stage-live on';
  else chip.hidden = true;
  chip.textContent = state.source.kind !== 'live' ? '' : live.stale ? `${text('STALE')} ${live.frame_age_ms != null ? (live.frame_age_ms / 1000).toFixed(1) + ' s' : ''}`.trim() : replay ? `▶ ${text('VOD replay')}` : `● ${text('live')}`;
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
  // Video mode: only the static-per-dataset layers and the selected event's own
  // geometry are drawn. A per-frame detection is not re-used here - it would be
  // a marker for a frame that is no longer on screen.
  const playing = !!state.playback.on;
  // A live or replay frame is described by what the live pipeline returned for it,
  // and by nothing of the dataset frame the stage held before: its stored inference,
  // correction, unified detections, anchors and the pockets derived from them all
  // describe a different picture. They come back when the stage returns to it.
  const liveFrame = isLive;
  const u = playing || liveFrame ? null : state.unified;
  const liveBoxes = (live?.detections?.boxes || []);
  const livePoly = live?.detections?.table_polygon || null;
  // Clearance first: the automatic quad is painted only when its geometry is
  // plausible and (on a VOD frame of a dataset that has one) within tolerance of
  // the dataset's saved corners. The pocket markers and pot pulses are derived
  // from that same quad, so they are painted only from a checked quad - a wrong
  // quad is exactly what lands a rail-corner marker on top of a player.
  const autoCloth = (Array.isArray(u?.table_corners) && u.table_corners.length ? u.table_corners : null)
    || (isLive && Array.isArray(livePoly) && livePoly.length ? livePoly : null)
    || (liveFrame ? null : staticQuad());
  const reference = state.source.kind === 'vod' ? state.cloth.reference : null;
  const clothVerdict = autoCloth ? validateCloth(autoCloth, reference, state.frameWidth, state.frameHeight) : {state:'none',reason:'no detection',detail:'',mean:null,max:null,tolerance:null,source:null};
  clothVerdict.available = Number(u?.pockets?.length || 0);
  state.cloth.verdict = clothVerdict;
  // What the detector decided about the quad (additive API field `table_quad`):
  // the refusal reason and the per-side evidence the operator needs when the cloth
  // layer stays empty.
  state.cloth.quad = u?.table_quad || null;
  // Pocket markers need pocket geometry that can be trusted: this frame's model
  // quad when it passed its clearance check, otherwise the dataset's saved
  // anchors / calibration - the same geometry the anchors layer draws. A refused
  // quad is never borrowed, and with no trusted source at all nothing is drawn.
  const modelPockets = clothVerdict.state === 'ok' ? (u?.pockets || []) : [];
  const calibPockets = modelPockets.length ? [] : (calibratedPockets(reference) || []);
  const pockets = modelPockets.length ? modelPockets : calibPockets;
  const pocketSource = modelPockets.length ? 'model' : calibPockets.length ? 'calibration' : null;
  state.cloth.pockets = {source: pocketSource, count: pockets.length, reference: pocketSource === 'calibration' ? reference?.source ?? null : null};
  if (ov.cloth && autoCloth && clothVerdict.state !== 'off') {
    const detected = Array.isArray(u?.table_corners) && u.table_corners.length;
    const [qx, qy] = quadOrigin(quadPoints(autoCloth));
    layers.push(`<polygon class="u-cloth" points="${autoCloth.map(p => p.join(',')).join(' ')}" fill="none"></polygon>`);
    layers.push(sourceTag(qx + 8, qy + 8, detected || isLive ? 'model' : 'calib'));
    auto.cloth = 1;
  }
  if (ov.pockets && pockets.length) {
    const kind = pocketSource === 'calibration' ? 'calib' : 'model';
    layers.push(pockets.map(pk => {
      const label = pocketText(pk.name);
      const width = sourceTagWidth(kind) + 6 + glyphWidth(label, 14);
      return `<g class="u-pocket"><circle cx="${pk.cx}" cy="${pk.cy}" r="12" fill="none" stroke="var(--brass)" stroke-width="2.5"></circle></g>${tagRow(pk.cx - width / 2, pk.cy + 16, kind, label)}`;
    }).join(''));
    auto.pockets = pockets.length;
  }
  if (ov.persons && !playing) {
    const persons = u?.persons || (isLive ? liveBoxes.filter(b => b.label === 'person') : []);
    layers.push(persons.map(per => {
      const [x1, y1, x2, y2] = per.bbox;
      const track = per.track_id ?? per.track;
      const selected = state.sel.kind === 'person' && track !== undefined && String(state.sel.person?.track_id ?? state.sel.person?.track) === String(track);
      const chip = ov ? `<text class="u-chip${per.player_id ? ' bound' : ''}" x="${x1 + 2 + sourceTagWidth('model') + 6}" y="${Math.max(16, y1 - 8)}">${esc(personChip(per, track))}</text>` : '';
      return `${sourceTag(x1 + 2, Math.max(2, y1 - 26), 'model')}${chip}<g class="u-person${selected ? ' selected' : ''}" data-person="${esc(track)}" data-bbox="${esc((per.bbox || []).join(','))}" data-cluster="${esc(per.cluster_id ?? '')}" data-player="${esc(per.player_id ?? '')}"><rect x="${x1}" y="${y1}" width="${x2 - x1}" height="${y2 - y1}" fill="none" stroke="#8fd6a8" stroke-width="2"></rect></g>`;
    }).join(''));
    auto.persons = persons.length;
  }
  if (ov.balls && !playing) {
    const balls = u?.balls || (isLive ? liveBoxes.filter(b => b.label === 'ball') : []);
    layers.push(balls.map((b, i) => {
      const cx = b.cx ?? (b.bbox ? (b.bbox[0] + b.bbox[2]) / 2 : 0), cy = b.cy ?? (b.bbox ? (b.bbox[1] + b.bbox[3]) / 2 : 0), r = Math.max(9, b.r ?? 12);
      return `${sourceTag(cx - sourceTagWidth('model') / 2, cy - r - 22, 'model')}<g class="u-ball" data-ball="${i}" data-cx="${cx}" data-cy="${cy}" data-r="${r}" data-color="${esc(b.color ?? '')}"><circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--brass-hi)" stroke-width="2"></circle><circle cx="${cx}" cy="${cy}" r="2" fill="var(--brass-hi)"></circle></g>`;
    }).join(''));
    auto.balls = balls.length;
  }
  // A pot pulse is placed at the pocket the event names: it follows the same
  // trusted-source rule as the markers themselves, so a pulse never points at a
  // pocket position the pockets layer would not draw.
  if (ov.events && u?.events && pockets.length) {
    for (const event of u.events) {
      if (event.type !== 'pot') continue;
      const name = String(event.nearest_pocket || '').split(/[\s(]/)[0];
      const pk = pockets.find(p => p.name === name);
      if (pk) { layers.push(`<circle class="u-pot-pulse" cx="${pk.cx}" cy="${pk.cy}" r="18" fill="none" stroke="var(--red)" stroke-width="3"></circle>`); auto.events++; }
    }
  }
  // The selected cue's own geometry, drawn for the whole playback window and on
  // a frozen frame that sits in that window: a pot is the ball's last known
  // position, the line to the pocket it names and a ring on that pocket; a shot
  // is the from -> to displacement with its speed. Everything here is the
  // server's projection of the scan's millimetres (px_source travels with the
  // event); an event without pixels says "not projectable" instead.
  const cue = ov.events && !liveFrame ? (state.sel.kind === 'event' ? state.sel.event : null) : null;
  if (cue && cueGeometryVisible(cue)) {
    const geometry = paintCueGeometry(cue);
    if (geometry) { layers.push(geometry.markup); auto.events++; }
  }
  if (ov.anchors && state.anchors.loaded && state.dataset === 'vod30' && !liveFrame) {
    const [ax, ay] = state.anchors.pts[0] || [0, 0];
    layers.push(state.anchors.pts.map(([x, y], i) => `<g class="u-anchor${state.sel.kind === 'anchor' && state.anchors.index === i ? ' selected' : ''}" data-anchor="${i}"><circle cx="${x}" cy="${y}" r="12"></circle><text x="${x + 18}" y="${y - 16}">${i + 1}</text></g>`).join(''));
    layers.push(sourceTag(ax + 16, Math.max(2, ay - 32), 'manual'));
    auto.anchors = state.anchors.pts.length;
  }
  // The editable layer is the operator's only once a correction exists or they
  // have edited this frame; an untouched inference frame stays a model result.
  // While the video runs the editable layer is empty by construction: it belongs
  // to one frame, and dropPerFrame() emptied it when playback started.
  // Each box is counted and tagged by its own origin, so the facts-line split and
  // the on-stage tags come from one truth: the model's boxes stay MODEL/模型 and
  // only the boxes the operator actually made or touched read YOURS/人工.
  const editable = playing || liveFrame ? [] : state.boxes;
  const boxKinds = editable.map(boxTagKind);
  const boxSource = boxKinds.length && boxKinds.every(kind => kind === boxKinds[0]) ? boxKinds[0] : boxKinds.length ? 'mixed' : 'auto';
  for (const box of editable) {
    const manual = boxTagKind(box) === 'manual';
    if (box.label === 'person') { manual ? drawn.persons++ : auto.persons++; }
    else if (ballLabel(box.label)) { manual ? drawn.balls++ : auto.balls++; }
  }
  // The editable polygon is counted by where it came from: the operator's own
  // correction is manual (so the facts split can fire), a stored inference polygon
  // is model-derived and counted as auto.
  const editPolygon = liveFrame ? null : state.polygon;
  const polySource = editPolygon ? polygonSource() : null;
  state.cloth.polygon = polySource;
  if (editPolygon) polySource === 'manual' ? drawn.cloth++ : auto.cloth++;
  svg.dataset.boxes = boxSource;
  const boxes = editable.map((box, i) => {
    const [x1, y1, x2, y2] = box.bbox, center = boxCenter(box);
    const kind = boxTagKind(box);
    const selected = state.sel.kind === 'box' && state.sel.box === i && !box.frozen;
    const ghost = box.frozen === true;
    const faint = ghost || isPairedModel(box, state.boxes);
    // A paired model box puts its tag under the box so the two tags never sit on
    // top of each other: agreement keeps one clean pair of rectangles.
    const tagAt = faint && kind === 'auto' ? y2 + 18 : Math.max(2, y1 - 26);
    const handles = selected ? [[x1,y1],[x2,y1],[x2,y2],[x1,y2]].map(([hx,hy],c) => `<rect class="handle" data-handle="${c}" x="${hx-7}" y="${hy-7}" width="14" height="14"></rect>`).join('') : '';
    return `${tagRow(x1, tagAt, kind, `${box.label}${box.score != null ? ` ${Number(box.score).toFixed(2)}` : ''}`)}<g data-box="${i}" data-origin="${kind}"${ghost ? ' data-ghost="1"' : ''} class="t-box ${kind}${faint ? ' faint' : ''}${selected ? ' selected' : ''}"><rect x="${x1}" y="${y1}" width="${x2-x1}" height="${y2-y1}"></rect>${ballLabel(box.label) ? `<circle class="center-dot" cx="${center[0]}" cy="${center[1]}" r="4"></circle>` : ''}${handles}</g>`;
  }).join('');
  const poly = editPolygon ? (() => { const [px, py] = quadOrigin(quadPoints(state.polygon) || [[0,0]]); return `${sourceTag(px + 8, py + 8, polySource === 'manual' ? 'manual' : 'model')}<polygon class="t-poly" points="${state.polygon.map(p => p.join(',')).join(' ')}"></polygon>${state.polygon.map((p,i) => `<circle class="handle" data-poly="${i}" cx="${p[0]}" cy="${p[1]}" r="9"></circle>`).join('')}`; })() : '';
  const preview = state.drag && state.drag.kind === 'draw' ? `<rect class="draw-preview" x="${Math.min(state.drag.x1,state.drag.x2)}" y="${Math.min(state.drag.y1,state.drag.y2)}" width="${Math.abs(state.drag.x2-state.drag.x1)}" height="${Math.abs(state.drag.y2-state.drag.y1)}"></rect>` : '';
  svg.innerHTML = layers.join('') + poly + boxes + preview;
  svg.querySelectorAll('g[data-box]').forEach(g => g.onclick = () => { const index = Number(g.dataset.box); if (state.boxes[index]?.frozen) return; if (state.tool === 'select' && state.sel.box !== index) { selectBox(index); } });
  svg.querySelectorAll('g.u-ball').forEach(g => g.onclick = event => { event.stopPropagation(); selectStageBall(Number(g.dataset.ball), Number(g.dataset.cx), Number(g.dataset.cy), Number(g.dataset.r)); });
  svg.querySelectorAll('g.u-person').forEach(g => g.onclick = event => { event.stopPropagation(); selectStagePerson(g.dataset); });
  svg.querySelectorAll('g.u-anchor').forEach(g => g.onclick = event => { event.stopPropagation(); selectAnchor(Number(g.dataset.anchor)); });
  Object.assign(drawn, {cloth: drawn.cloth + auto.cloth, balls: drawn.balls + auto.balls, persons: drawn.persons + auto.persons, pockets: auto.pockets, anchors: auto.anchors, events: auto.events});
  // Per-frame provenance for the facts line and for the tests that pin the
  // honesty rule: at zero while the video runs, because nothing frame-shaped is
  // painted then.
  state.drawn = {...drawn, auto, on: true, source: state.drawn.source, playing,
                 perFrame: editable.length};
  paintStageNote();
}
// Why the detector produced no quad, in the operator's words. The server sends
// machine codes (low_cloth_area, no_boundary_evidence, ...) and the operator reads
// a sentence: the codes are a detector contract, not UI copy. Same map shape as
// POCKET_WORDS; "${code}" is the only composed slot and it stays translated.
const QUAD_REFUSAL_COPY = {
  low_cloth_area: ['the cloth is hidden - a player or an object is over the bed',
                   '台面被遮挡——有人或物体挡在台面上'],
  no_boundary_evidence: ['no rail edge is visible inside the search band',
                         '搜索带内看不到库边边缘'],
  boundary_outside_band: ['the rail edge sits outside the search band',
                          '库边边缘超出搜索带'],
  prior_disagreement: ['the four sides disagree with the saved centre',
                       '四条边与已保存中心不一致'],
  invalid_geometry: ['the four corners are not a valid table quad',
                     '四个角点不构成有效球桌四边形'],
  no_prior: ['no saved geometry exists for this dataset',
             '该数据集没有已保存几何'],
  no_cloth_area: ['no cloth was found in this frame', '此帧没有找到台呢'],
  default: ['the detector reported "${code}"', '检测器报告「${code}」']
};
function quadReasonText(code) {
  const row = QUAD_REFUSAL_COPY[String(code || '')] || QUAD_REFUSAL_COPY.default;
  return (root?.lang === 'zh' ? row[1] : row[0]).replace('${code}', String(code || 'unknown').replace(/_/g, ' '));
}
function quadSideText(quad) {
  const verified = Number(quad?.verified_sides);
  if (!Number.isFinite(verified) || verified >= 4) return '';
  const unverified = quad?.sides?.filter(side => side.state !== 'verified')
    .map(side => Number(side.side) + 1).join(', ');
  return root?.lang === 'zh'
    ? `（未校验边 ${4 - verified}/4${unverified ? `：${unverified}` : ''}）`
    : ` (${4 - verified}/4 sides unverified${unverified ? `: ${unverified}` : ''})`;
}
function quadRefusalText(quad) {
  const phrase = quadReasonText(quad?.reason);
  return root?.lang === 'zh'
    ? `球桌四边形已拒绝：${phrase}——未绘制。${quadSideText(quad)}`
    : `Table quad refused: ${phrase} — not drawn.${quadSideText(quad)}`;
}
function quadFallbackText(quad) {
  const phrase = quadReasonText(quad?.reason);
  return root?.lang === 'zh'
    ? `当前绘制的是朴素检测回退结果，而非精修四边形：${phrase}。`
    : `The model quad is the naive fallback, not the refined one: ${phrase}.`;
}
// Where the editable polygon came from. The stage tag and the facts split have to
// agree with the count the painter records, or the operator reads "cloth 2" while
// one polygon is tagged YOURS and no (+1 manual) ever appears.
function polygonSource() {
  if (!state.polygon) return null;
  // A stored inference polygon is model-derived; everything else on this layer is
  // the operator's - their saved correction, or a live edit of either.
  if (state.fresult?.correction?.table_polygon) return 'manual';
  if (state.fresult?.inference?.table_polygon) return state.dirty ? 'manual' : 'inference';
  return 'manual';
}
// Why a layer is not on the stage is stated in place, next to the imagery:
// either the model quad failed its clearance check or a saved correction was
// refused because it belongs to another frame. Both are facts about the frame
// the operator is looking at, not transient errors.
function clothNotice(verdict, refusal, quad) {
  const lines = [];
  if (refusal && !refusal.ok) lines.push(text(`Saved correction belongs to ${refusal.owner}, not this frame (${refusal.expected}) — not drawn.`));
  if (verdict?.state === 'off') lines.push(verdict.reason === 'invalid geometry'
    ? text(`The model table quad is not a valid table quad for this frame (${verdict.detail}) — not drawn.`)
    : text(`The model table quad is ${Math.round(verdict.mean)} px off this dataset's saved corners (${text(verdict.source || 'unknown')}, tolerance ${Math.round(verdict.tolerance)} px) — not drawn.`));
  else if (verdict?.state === 'unverified') lines.push(text('No saved corner set exists for this dataset: the model quad is drawn unverified and pocket markers stay hidden.'));
  // Why the detector produced no quad (or a fallback one) travels with the payload
  // as `table_quad`: without it a refused frame reaches the operator as a silent
  // absence. The reason codes are mapped to operator phrases, never printed raw.
  if (quad?.reason && (verdict?.state === 'off' || verdict?.state === 'none')) lines.push(quadRefusalText(quad));
  else if (quad?.state === 'naive_fallback') lines.push(quadFallbackText(quad));
  return lines.filter(Boolean);
}
function paintStageNote() {
  const note = $('#stage-note'); if (!note) return;
  const lines = clothNotice(state.cloth.verdict, state.cloth.refusal, state.cloth.quad);
  note.hidden = !lines.length;
  note.dataset.live = state.source.kind === 'live' ? '1' : '0';
  note.classList.toggle('error', !!(state.cloth.refusal && !state.cloth.refusal.ok));
  const body = lines.join(' ');
  if (note.textContent !== body) note.textContent = body;
}
// ---- the selected cue, drawn ---------------------------------------------
// A cue's geometry comes from the server's projection of the scan's millimetres
// (`px_source` travels with the event), so nothing here is estimated in the
// browser. It is drawn while the stage plays that cue's window and on a frozen
// frame inside it; an event without pixels draws nothing and says why.
const COLOUR_WORDS = {
  blue:['blue','蓝'], red:['red','红'], yellow:['yellow','黄'], green:['green','绿'],
  white:['white','白'], black:['black','黑'], pink:['pink','粉'], brown:['brown','棕'],
  orange:['orange','橙'], purple:['purple','紫'], grey:['grey','灰'], gray:['grey','灰']
};
function colourWord(value) {
  const row = COLOUR_WORDS[String(value ?? '').toLowerCase()];
  return row ? (root?.lang === 'zh' ? row[1] : row[0]) : '';
}
function cueGeometryVisible(event) {
  if (!event?.px_source) return false;
  if (![event.last_px, event.from_px, event.to_px].some(p => Array.isArray(p) && p.length >= 2)) return false;
  const playback = state.playback;
  if (playback.on && playback.event && String(playback.event.id) === String(event.id)) return true;
  const t = Number(state.t);
  return Number.isFinite(t) && Math.abs(t - Number(event.t)) <= 3.0;
}
// The scan carries no colour for vod30 events, so a label simply leaves it out
// instead of printing "unknown" over the imagery; the inspector shows the row
// only when the data has one.
function numberText(value, unit, fallback = '—') {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number)} ${unit}` : fallback;
}
function paintCueGeometry(event) {
  const parts = [];
  if (event.type === 'pot') {
    const last = Array.isArray(event.last_px) ? event.last_px.map(Number) : null;
    const pocket = drawnPocket(event.pocket_name, event);
    if (!last || !pocket) return null;
    parts.push(`<line class="u-cue-line" x1="${last[0]}" y1="${last[1]}" x2="${pocket[0]}" y2="${pocket[1]}" fill="none"></line>`);
    parts.push(`<g class="u-cue-ball"><circle cx="${last[0]}" cy="${last[1]}" r="14" fill="none"></circle><circle cx="${last[0]}" cy="${last[1]}" r="3"></circle></g>`);
    parts.push(`<circle class="u-cue-pocket" cx="${pocket[0]}" cy="${pocket[1]}" r="24" fill="none"></circle>`);
    const label = `${colourWord(event.color) ? `${colourWord(event.color)} → ` : ''}${pocketText(event.nearest_pocket || event.pocket_name)}`;
    parts.push(tagRow(last[0] + 18, Math.max(2, last[1] - 30), 'event', label, 'o-label'));
    return {markup: parts.join('')};
  }
  const from = Array.isArray(event.from_px) ? event.from_px.map(Number) : null;
  const to = Array.isArray(event.to_px) ? event.to_px.map(Number) : null;
  if (!from || !to) return null;
  const angle = Math.atan2(to[1] - from[1], to[0] - from[0]);
  const head = [[to[0], to[1]],
                [to[0] - 18 * Math.cos(angle - 0.42), to[1] - 18 * Math.sin(angle - 0.42)],
                [to[0] - 18 * Math.cos(angle + 0.42), to[1] - 18 * Math.sin(angle + 0.42)]];
  parts.push(`<line class="u-cue-line" x1="${from[0]}" y1="${from[1]}" x2="${to[0]}" y2="${to[1]}" fill="none"></line>`);
  parts.push(`<polygon class="u-cue-head" points="${head.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')}"></polygon>`);
  parts.push(`<circle class="u-cue-takeoff" cx="${from[0]}" cy="${from[1]}" r="12" fill="none"></circle>`);
  const label = `${colourWord(event.color) ? `${colourWord(event.color)} · ` : ''}${numberText(event.disp_mm, 'mm')} · ${numberText(event.speed_mm_s, 'mm/s')}`;
  parts.push(tagRow(Math.min(from[0], to[0]) + 14, Math.max(2, Math.min(from[1], to[1]) - 30), 'event', label, 'o-label'));
  return {markup: parts.join('')};
}
// ---- selection -----------------------------------------------------------
// Selecting a cue plays its evidence on the stage and loops inside its window;
// the freeze button (or any step) is what returns to a single decoded frame.
function selectEvent(index) { return playEvent(index); }
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
  const identity = trackIdentity(track);
  // data-cluster is a DOM string ("148"); the server takes cluster_id as an integer.
  const cluster = /^\d+$/.test(dataset.cluster || '') ? Number(dataset.cluster) : identity.cluster_id;
  state.sel = {kind:'person', person:{track_id: track, bbox, cluster_id: cluster, player_id: dataset.player || identity.player_id, bound_evidence: identity.bound_evidence}, crop:null, ball:null, event:null, track: track, anchor:0, box:-1};
  state.focus = 'persons';
  if (!state.persons.windows.length) loadPersons().then(() => { if (state.persons.win) loadTracks(); });
  notify();
}
// The identity binding a track already carries, when this frame's identity
// overlay resolved it: a stage click carries it in the markup, a rail pick asks
// the same overlay payload instead of running the pipeline a second time.
// Unknown stays unknown - never guessed, so the rail can say so out loud.
function trackIdentity(track) {
  const row = track === null || track === undefined ? null : (state.unified?.persons || []).find(p => String(p.track_id ?? p.track) === String(track));
  if (!row) return {cluster_id: null, player_id: null, bound_evidence: null};
  return {cluster_id: row.cluster_id ?? null, player_id: row.player_id ?? null, bound_evidence: row.bound_evidence ?? null};
}
function selectTrack(id) {
  const track = state.persons.tracks.find(t => String(t.id) === String(id)) || {id: trackId(id), box:null, label:null, seed:null};
  state.persons.track = track.id;
  state.sel = {kind:'person', person:{track_id: id, bbox: track.box || null, ...trackIdentity(track.id)}, track: id, crop:null, ball:null, event:null, anchor:0, box:-1};
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
  if (!body.verdict) { notice('Choose a verdict before saving.', true); return false; }
  const frame = state.frame;
  return save(button, `/api/${enc(state.dataset)}/annotate`, body, () => {
    state.annotations[String(event.id)] = body; state.verdictDraft = body.verdict;
  }, 'event', `${event.type === 'pot' ? 'cue' : 'shot'} #${event.id} ${event.type} @ frame ${frame} · ${body.verdict}`);
}
function labelValueText(value) { return value === null || value === undefined ? 'cleared' : value === -1 || value === 'u' ? 'Unknown' : value === 0 ? 'Cue 0' : `Ball ${value}`; }
async function labelBall(button, value) {
  const crop = state.sel.kind === 'ball' ? state.sel.crop : null;
  if (!crop) { notice('Select a ball or a crop first.', true); return false; }
  const file = crop.file.split('/').pop();
  const label = value === 'clear' ? null : Number(value);
  return save(button, `/api/balls/${enc(state.set)}/label`, {file, label}, () => {
    state.balls.labels ||= {};
    if (label === null) delete state.balls.labels[file]; else state.balls.labels[file] = label === -1 ? 'u' : label;
  }, 'ball', `crop ${file} = ${text(labelValueText(label === -1 ? 'u' : label))}`);
}
// The seeds contract types track_id as an integer; rail dataset attributes are strings.
function trackId(value) { return typeof value === 'string' && /^-?\d+$/.test(value) ? Number(value) : value; }
// One write per track label. Three shapes share this path on purpose, because
// they share one store: 'clear' removes the entry, 'A'/'B'/'ignore' are the
// legacy role values the identity pipeline still reads, and anything else is a
// guest name the operator typed. The server validates both shapes.
async function setSeed(button, role, playerId) {
  const track = state.sel.track;
  if (track === null || track === undefined) { notice('Select a visible track first.', true); return false; }
  const label = role === 'clear' ? null : (typeof role === 'string' ? role.trim() : role);
  if (label !== null && String(label) === '') { notice('Type a guest name or choose a regular before saving.', true); return false; }
  const t = state.persons.t ?? state.t;
  const body = {win: state.persons.win, t, track_id: trackId(track), label};
  return save(button, '/api/vod30/seeds', body, async () => { await loadSeeds(); }, 'person', `win ${state.persons.win} · track ${track} = ${label === null ? 'cleared' : label}`);
}
// The regular path: the player's id is bound to this track's identity cluster,
// so face/body matching keeps working from the same explicit pick.
async function seedIdentity(button, playerId) {
  const person = state.sel.person || {};
  if (!person.cluster_id) { notice('This track has no identity cluster yet.', true); return false; }
  return save(button, '/api/identity/seed', {cluster_id: person.cluster_id, player_id: playerId}, null, 'person', `cluster ${String(person.cluster_id).slice(0, 6)} → ${playerId}`);
}
// Clear is a real undo of either labelling path: the seeds label (guest name or
// a legacy A/B/ignore value) is removed, and an identity binding on this track's
// cluster is unbound. Both writes are explicit; nothing else is touched.
async function clearIdentity(button) {
  const track = state.sel.track;
  const person = state.sel.person || {};
  const seeded = track !== null && track !== undefined
    && Object.values(state.persons.seeds || {}).some(s => s.win === state.persons.win && String(s.track_id) === String(track));
  const bound = person.cluster_id !== null && person.cluster_id !== undefined && person.player_id;
  if (!seeded && !bound) { notice('Nothing is bound to this track yet.', true); return false; }
  let ok = true;
  if (seeded) ok = await setSeed(button, 'clear');
  if (bound) {
    const unbound = await save(button, '/api/identity/unbind', {cluster_id: person.cluster_id}, null, 'person', `cluster ${String(person.cluster_id).slice(0, 6)} unbound`);
    if (unbound) { state.sel.person = {...person, player_id: null, bound_evidence: null}; }
    ok = unbound && ok;
  }
  return ok;
}
// ---- enrolling a regular from the person on screen ------------------------
// Two steps, and only the second one writes. The preview scans the person's
// track (or reads the identity index when the track already carries a cluster)
// and can take a while, so it reports what it is doing and cannot be started
// twice; the plan it returns is held under one token, which the confirm re-checks
// against the recording before anything is written.
async function enrollPreview(button) {
  const person = state.sel.person || {};
  const bbox = Array.isArray(person.bbox) && person.bbox.length === 4 && person.bbox.every(Number.isFinite) ? person.bbox : null;
  if (!bbox) { notice('Select the person on the stage first: enrolment starts from their box in this frame.', true); return false; }
  if (state.enroll.status === 'pending') return false;
  const epoch = state.epoch;
  state.enroll = {status:'pending', payload:null, name: state.enroll.name || '', startedAt: Date.now(), error:null};
  notify();
  try {
    const body = {dataset: state.dataset, frame_index: state.frame, bbox: bbox.slice()};
    if (person.cluster_id !== null && person.cluster_id !== undefined) body.cluster_id = person.cluster_id;
    const payload = await api('/api/identity/enroll-preview', body);
    if (epoch !== state.epoch || state.enroll.status !== 'pending') return false;
    state.enroll = {status: payload?.ok ? 'ready' : 'refused', payload, name: state.enroll.name || '', startedAt: state.enroll.startedAt, error:null};
    notify();
    return !!payload?.ok;
  } catch (error) {
    if (epoch !== state.epoch) return false;
    state.enroll = {status:'idle', payload:null, name: state.enroll.name || '', startedAt:0, error:error.message};
    notice(`Enrolment preview failed: ${error.message}`, true);
    notify();
    return false;
  }
}
async function enrollConfirm(button) {
  const payload = state.enroll.payload;
  if (!payload?.token) { notice('Preview the person before confirming.', true); return false; }
  const name = String(state.enroll.name || '').trim();
  // A refusal (200 ok:false: token_mismatch, preview_expired, player_name_required)
  // wrote nothing: throwing inside the save keeps its ✓ receipt away, and the block
  // shows the refusal's own reason, not the preview's.
  const ok = await save(button, '/api/identity/enroll-confirm', {token: payload.token, player_name: name},
    data => {
      state.enroll = {status: data?.ok ? 'written' : 'refused', payload: data?.ok ? {...payload, result: data} : {...payload, ...data, result: data}, name, startedAt: 0, error: null};
      if (!data?.ok) throw new Error(data?.reason || 'refused');
    },
    'person', `${name || '—'} → regular`);
  if (ok && state.enroll.status === 'written' && hooks.reloadRoster) hooks.reloadRoster();
  return ok;
}
// The typed name is a draft: it must not re-render the block while it is typed in.
function setEnrollName(value) { state.enroll = {...state.enroll, name: String(value ?? '')}; }
function cancelEnroll() { state.enroll = {status:'idle', payload:null, name: state.enroll.name || '', startedAt:0, error:null}; notify(); }
async function saveAnchors(button) {
  return save(button, '/api/vod30/anchors', {t: state.anchors.t, pts: state.anchors.pts.map(p => [...p])}, () => { state.anchors.saved = true; }, 'anchor', `${state.anchors.pts.length} anchors @ t ${Number(state.anchors.t).toFixed(1)}`);
}
// What 'save corrections' writes: the operator's own boxes only. The model's are
// session-only reference (and a frozen ghost of an edited model box is never a
// correction of ours); an edited model box has already flipped its origin, so it is
// included - which is exactly how the operator turns a model box into theirs.
function manualBoxCount() { return state.boxes.filter(box => box.origin !== 'auto').length; }
function modelBoxCount() { return state.boxes.filter(box => box.origin === 'auto').length; }
function correctionBody() {
  return {dataset: state.dataset, frame_index: state.frame,
          boxes: state.boxes.filter(box => box.origin !== 'auto').map(box => ({label: box.label, bbox: box.bbox.slice()})),
          table_polygon: state.polygon ? state.polygon.map(p => [p[0], p[1]]) : null};
}
async function saveCorrections(button) {
  if (state.busy || !state.fresult) return false;
  const invalid = state.boxes.find(box => !normalizeBox(box.bbox, state.frameWidth, state.frameHeight));
  if (invalid) { notice('A box has invalid coordinates; fix or delete it before saving.', true); return false; }
  const body = correctionBody();
  const ok = await save(button, '/api/frame-correction', body, data => {
    // The stored correction carries its own scope (dataset, frame, source
    // size): keep the server's copy so the next paint checks what was saved.
    state.fresult.correction = data?.correction || {dataset: body.dataset, frame_index: body.frame_index, width: state.frameWidth, height: state.frameHeight, boxes: state.boxes.map(b => ({label: b.label, bbox: b.bbox.slice()})), table_polygon: body.table_polygon};
    state.cloth.refusal = null; state.drawn.source = 'manual corrections'; paintOverlay();
  }, 'corrections', `frame ${state.frame} · ${state.boxes.length} boxes${state.polygon ? ' + polygon' : ''}`);
  return ok;
}
function setTool(tool) { state.tool = tool; notify(); }
function setDetector(kind, on) { if (!(kind in state.detectors)) return false; state.detectors[kind] = !!on; notify(); return true; }
function setShooter(value) { state.shooterDraft = value; notify(); }
function setNote(value) { state.noteDraft = value; }
function setEventFilter(filter) { state.eventFilter = ['all','shot','pot','pending','geometry','window'].includes(filter) ? filter : 'all'; notify(); }
function freeze() { setPlaying(false); return seek(state.frame); }
async function setWindow(win) {
  if (state.busy) return false;
  state.persons.win = win;
  const start = Number(String(win).split('-')[0]);
  notify();
  if (Number.isFinite(start)) { await loadTracks(); seekTime(start); }
  return true;
}
function setBoxLabel(label) { const box = state.boxes[state.sel.box]; if (box) { box.label = label; markBoxEdited(box); markDirty(); paintOverlay(); } }
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
  if (state.busy || !state.fresult) { if (!state.fresult) notice('Freeze a frame before running inference.', true); return false; }
  const detectors = Object.keys(state.detectors).filter(k => state.detectors[k]);
  if (!detectors.length) { notice('Choose at least one detector (table, person, balls).', true); return false; }
  const frame = state.frame, epoch = state.epoch;
  state.inferRunning = true; state.inferStatus = `Starting inference on frame ${frame} (${detectors.join(', ')})…`; notify();
  try {
    const job = await api('/api/inference', {dataset: state.dataset, frame_index: frame, detectors});
    if (epoch !== state.epoch) return false;
    state.inferStatus = `Inference running for frame ${job.frame_index}: ${job.stage || 'queued'}…`; notify();
    pollInference(epoch, job.frame_index);
    return true;
  } catch (error) {
    if (epoch === state.epoch) { state.inferRunning = false; state.inferStatus = 'Idle.'; notice(`Inference failed to start: ${error.message}`, true); }
    return false;
  }
}
function pollInference(epoch, frame) {
  clearTimeout(state.inferTimer);
  state.inferTimer = setTimeout(async () => {
    try {
      const job = await api(`/api/inference?dataset=${enc(state.dataset)}`);
      if (epoch !== state.epoch) return;
      if (job.status === 'running') { state.inferStatus = `Inference running for frame ${job.frame_index}: ${job.stage || ''}…`; notify(); pollInference(epoch, frame); return; }
      state.inferRunning = false;
      if (job.status === 'failed') { state.inferStatus = 'Inference failed.'; notice(`Frame inference failed: ${job.error || 'unknown error'}`, true); return; }
      state.inferStatus = `Inference completed for frame ${job.frame_index} (not stored).`; notify();
      if (job.status === 'completed' && job.result && job.frame_index === frame && state.frame === frame) {
        if (state.fresult) state.fresult.inference = job.result;
        if (!state.dirty && !state.fresult?.correction) { applyFrameResult(); renderStage(); }
        paintOverlay(); notify();
        notice('Inference overlays updated for the frozen frame.');
      } else if (job.status === 'completed') notice(`Inference for frame ${job.frame_index} finished; freeze that frame to see its overlays.`);
    } catch (error) { if (epoch === state.epoch) { state.inferRunning = false; state.inferStatus = 'Status check failed.'; notice(`Inference status error: ${error.message}`, true); } }
  }, 1500);
}
async function rebuild(button) {
  if (button) button.disabled = true;
  state.persons.status = 'Rebuilding…'; notify();
  try {
    const data = await api('/api/vod30/rebuild', {});
    state.persons.rebuild = data.status || 'unknown';
    state.persons.status = `Status: ${data.status || 'unknown'}${data.error ? ` — ${data.error}` : ''}`;
    if (data.status === 'running') setTimeout(() => refreshRebuild(), 2500);
  } catch (error) { state.persons.status = `Rebuild failed: ${error.message}`; notice(`Rebuild failed: ${error.message}`, true); }
  notify();
}
async function refreshRebuild() {
  try {
    const data = await api('/api/vod30/rebuild');
    state.persons.rebuild = data.status || 'unknown';
    state.persons.status = `Status: ${data.status || 'unknown'}${data.error ? ` — ${data.error}` : ''}`;
    if (data.status === 'completed') { const fresh = await api('/api/vod30/tracklets'); state.persons.predictions = fresh.predictions; await loadTracks(); }
  } catch (error) { state.persons.status = `Status unavailable: ${error.message}`; }
  notify();
}
// ---- live source: the stage shows the live edge in the same <img> ---------
function applyLiveStatus(status) {
  if (!status || typeof status !== 'object') return;
  const previous = state.live.state;
  state.live.state = status.state || 'idle';
  state.live.error = status.error || null;
  state.live.skipped = status.frames_skipped ?? 0;
  // Per-stage evidence from the processor: the panel names which detectors ran and
  // at what cadence, instead of implying all of them ran on every frame.
  state.live.stages = Array.isArray(status.stages) ? status.stages : [];
  state.live.receive_to_result_ms = status.latest?.receive_to_result_ms ?? null;
  state.live.frame_age_ms = status.frame_age_ms ?? null;
  state.live.source = status.source && typeof status.source === 'object' ? status.source : null;
  state.live.replay = status.replay && typeof status.replay === 'object' ? status.replay : null;
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
    notice(`Live start failed: ${failure}`, true);
  } else if (state.live.state === 'running' || state.live.state === 'starting') {
    state.live.attempt = null;
  } else if (state.live.attempt?.error) {
    state.live.error = state.live.attempt.error;
  }
  // An operator stop hands the stage back to the dataset frame it held, with that
  // frame's own layers; a feed that stalls or ends keeps its last frame (stale).
  if (state.live.state === 'stopped' && previous !== 'stopped' && state.source.kind === 'live') returnToDatasetFrame();
  if (previous !== state.live.state || state.live.stale) notify();
  paintLiveChip(); notify();
}
function returnToDatasetFrame() {
  state.source = {kind:'vod', label: state.dataset, channel:null};
  state.live.detections = null;
  if (state.shotUrl) { renderStage(); scheduleUnified(state.frame, state.epoch, state.frameReq); }
  else if (state.vmeta) loadFrame(state.frame);
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
  if (epoch === state.epoch) { state.unified = null; state.cloth.refusal = null; state.cloth.verdict = {state:'none',reason:'no detection'}; paintOverlay(); paintLiveChip(); notify(); }
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
  state.cloth.refusal = null; state.cloth.reference = null;
  // The live edge's last frame and its detections belong to the live source.
  state.live.detections = null; state.live.stale = false;
  state.anchors.loaded = false;
  // A dataset switch always re-loads the one stage for the new dataset. The
  // request is queued too, so a decode that is already in flight cannot swallow
  // the switch and leave the stage without its model layer.
  notify();
  try {
    await loadVideo();
    await loadEvents();
  } catch (error) { notice(`${error.message}. The review API is unavailable. Use the project review server, not a file:// URL.`, true); return false; }
  loadClothReference().catch(() => {});
  if (state.busy) state.pendingSeek = 0;      // a decode owns the stage: it reloads frame 0 next
  else { state.pendingSeek = null; loadFrame(0); }
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
  if (handle && (state.sel.box >= 0 || state.sel === undefined)) { const target = Number(handle.closest('[data-box]')?.dataset.box ?? state.sel.box); if (state.boxes[target]?.frozen) return; event.preventDefault(); svg.setPointerCapture(event.pointerId); state.drag = {kind:'handle', box: target, corner: Number(handle.dataset.handle)}; return; }
  if (poly) { event.preventDefault(); svg.setPointerCapture(event.pointerId); state.drag = {kind:'poly', index: Number(poly.dataset.poly)}; return; }
  if (anchor) { event.preventDefault(); selectAnchor(Number(anchor.dataset.anchor)); svg.setPointerCapture(event.pointerId); state.drag = {kind:'anchor', index: Number(anchor.dataset.anchor)}; return; }
  if (box) { const index = Number(box.dataset.box); if (state.boxes[index]?.frozen) return; selectBox(index); if (state.tool === 'draw') return; event.preventDefault(); svg.setPointerCapture(event.pointerId); const [x,y] = svgPoint(event); state.drag = {kind:'move', box: index, x, y, orig: state.boxes[index].bbox.slice()}; return; }
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
    ghostModelBox(box);
    box.bbox = [nx1, ny1, nx1 + w, ny1 + h]; markBoxEdited(box); markDirty(); paintOverlay();
  } else if (drag.kind === 'handle') {
    const box = state.boxes[drag.box]; if (!box) return;
    const next = box.bbox.slice();
    next[[0,2,2,0][drag.corner]] = x; next[[1,1,3,3][drag.corner]] = y;
    box.bbox = normalizeBox(next, state.frameWidth, state.frameHeight) || box.bbox;
    ghostModelBox(box); markBoxEdited(box); markDirty(); paintOverlay();
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
    if (bbox) { state.boxes.push({label: state.newBoxLabel || 'ball', bbox, origin:'manual', edited:true}); selectBox(state.boxes.length - 1); setTool('select'); markDirty(); }
  }
  paintOverlay(); notify();
}
function nudgeBox(dx, dy) {
  if (state.busy || state.sel.box < 0 || !state.boxes[state.sel.box]) return;
  const box = state.boxes[state.sel.box], moved = normalizeBox([box.bbox[0]+dx, box.bbox[1]+dy, box.bbox[2]+dx, box.bbox[3]+dy], state.frameWidth, state.frameHeight);
  if (moved) { ghostModelBox(box); box.bbox = moved; markBoxEdited(box); markDirty(); paintOverlay(); }
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
  // V / ⏎ act on the selected cue only: with the Source panel open they must not
  // commit a draft to whichever event happens to be current.
  if (key === 'Enter') { if (state.sel.kind === 'event') saveVerdict(null); else notice('Select a cue first.', true); return; }
  if (/^[0-9]$/.test(key)) { e.preventDefault(); labelBall(null, Number(key)); return; }
  const upper = key.length === 1 ? key.toUpperCase() : key;
  if (upper === 'U') { e.preventDefault(); labelBall(null, -1); return; }
  if (upper === 'C') { e.preventDefault(); labelBall(null, 0); return; }
  if (upper === 'A' || upper === 'B') { e.preventDefault(); setSeed(null, upper); return; }
  if (upper === 'V') { e.preventDefault(); if (state.sel.kind === 'event') cycleVerdict(); else notice('Select a cue first.', true); return; }
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
    loadClothReference().catch(() => {});
    loadFrame(0);
  } catch (error) {
    notice(`${error.message}. The review API is unavailable. Use the project review server, not a file:// URL.`, true);
  }
}
function switchMode(mode) {
  if (!Object.hasOwn(modes, mode)) return false;
  if (modes[mode] === state.mode) { state.mode = modes[mode]; return true; }
  if (!canLeave()) return false;
  state.mode = modes[mode];
  return true;
}
function mount(host, shellHooks = {}) {
  if (root) return root === host ? mounting : false;
  if (!host || host.id !== 'review-root') return false;
  root = host;
  hooks = shellHooks || {};
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
    frame: {index: state.frame, t: state.t, fps: meta?.fps ?? 0, count: meta?.frame_count ?? 0, duration: meta?.duration ?? 0, kind: meta?.timestamp_kind || '', has: !!state.shotUrl, decoding: state.decoding, playing: state.playing, rate: playbackRate(), video: !!state.playback.on},
    playback: {on: !!state.playback.on, playing: videoPlaying(), loops: state.playback.loops || 0, from: state.playback.from || 0, to: state.playback.to || 0, event: state.playback.event ? state.playback.event.id : null, before: CLIP_BEFORE_S, after: CLIP_AFTER_S},
    source: {kind: state.source.kind, label: state.source.kind === 'vod' ? `${state.dataset} · ${meta ? `${Math.round(meta.duration)} s · ${Number(meta.fps).toFixed(3)} fps` : '—'}` : state.source.label, channel: state.source.channel},
    live: {state: state.live.state, error: state.live.error, frame_age_ms: state.live.frame_age_ms, receive_to_result_ms: state.live.receive_to_result_ms, skipped: state.live.skipped, seq: state.live.seq, stale: state.live.stale, attempt: state.live.attempt, detectors: state.live.detectors, stages: state.live.stages || [], source: state.live.source || null, replay: state.live.replay || null},
    overlay: {...state.overlay}, drawn: {...state.drawn}, loading: {...state.loading},
    selection: selected, focus: state.focus, eventFilter: state.eventFilter,
    detectors: {...state.detectors},
    events: {items: state.events.map(e => ({id: e.id, type: e.type, t: e.t, nearest_pocket: e.nearest_pocket ?? null, nearest_pocket_text: e.nearest_pocket ? pocketText(e.nearest_pocket) : null, evidence: e.evidence ?? null, verdict: state.annotations[String(e.id)]?.verdict || '', annotation: state.annotations[String(e.id)] || null,
      // Everything the inspector and the stage need to show what was detected:
      // the scan's own millimetres, and the server's projection of them (absent
      // when the dataset has no usable calibration - then it is not projectable).
      window_s: Array.isArray(e.window_s) ? [...e.window_s] : null,
      last_mm: e.last_mm ?? null, from_mm: e.ball_from ?? null, to_mm: e.ball_to ?? null,
      last_px: e.last_px ?? null, from_px: e.from_px ?? null, to_px: e.to_px ?? null,
      pocket_name: e.pocket_name ?? null, pocket_px: e.pocket_px ?? null, px_source: e.px_source ?? null,
      color: e.color ?? null, disp_mm: e.disp_mm ?? null, speed_mm_s: e.speed_mm_s ?? (Number.isFinite(Number(e.speed_m_s)) ? Math.round(Number(e.speed_m_s) * 1000) : null),
      // The gate block the eval tool measured and wrote onto the event: the
      // numbers behind the automated call (census, pocket distance, re-measured
      // move, calibration coverage). Passed through as stored, never invented.
      gate: e.gate && typeof e.gate === 'object' ? {...e.gate, numbers: {...(e.gate.numbers || {})}} : null,
      // Which tier the event was confirmed at ("geometry" = the re-measured
      // motion matches the claim, "window" = a ball moved, but not the one or
      // where the claim said) and the claim-vs-measurement check behind it.
      // Passed through as stored; the claim geometry itself is never rewritten.
      tier: e.tier === 'geometry' || e.tier === 'window' ? e.tier : null,
      geometry_check: e.geometry_check && typeof e.geometry_check === 'object' ? {...e.geometry_check} : null,
      // Who made this candidate, and whether a human has confirmed it: passed
      // through as stored (detector, statement, machine_produced, human_confirmed),
      // so the rail can say a candidate is machine-produced instead of implying a
      // reviewed result. Absent stays absent.
      provenance: e.provenance && typeof e.provenance === 'object' ? {...e.provenance} : null,
      dup_count: Number.isFinite(Number(e.dup_count)) ? Number(e.dup_count) : null,
      projectable: !!(e.px_source || e.last_px || e.from_px)})), index: state.eventIndex,
    // Verdicts count only while their event is still in the queue: a verdict
    // recorded against a cue the detection gates later dropped must not read as
    // "reviewed" next to a queue that no longer holds it.
    reviewed: state.events.filter(e => state.annotations[String(e.id)]?.verdict).length},
    verdictDraft: state.verdictDraft ?? null,
    balls: {set: state.set, items: state.balls.items.slice(0, 400).map(i => ({file: i.file, t: i.t, score: i.score ?? null, ctx: i.ctx ?? null, label: state.balls.labels[i.file] ?? null})), index: state.balls.index, labels: state.balls.labels},
    persons: {win: state.persons.win, windows: state.persons.windows, tracks: state.persons.tracks.map(t => ({id: t.id, label: t.label ?? null, box: t.box ?? null, seed: Object.values(state.persons.seeds || {}).find(s => s.win === state.persons.win && String(s.track_id) === String(t.id))?.label ?? null})), track: state.persons.track, predictions: state.persons.predictions, status: state.persons.status},
    anchors: {...state.anchors, points: state.anchors.pts.map(p => [...p])},
    corrections: {tool: state.tool, newBoxLabel: state.newBoxLabel || 'ball', box: state.sel.kind === 'box' ? state.sel.box : -1, boxes: state.boxes.length, boxLabel: state.sel.kind === 'box' ? state.boxes[state.sel.box]?.label : null, polygon: !!state.polygon, result: state.fresult ? (state.fresult.correction ? 'manual corrections' : state.fresult.inference ? 'inference' : 'none') : 'none', dirty: state.dirty, inferRunning: state.inferRunning, inferStatus: state.inferStatus, manualBoxes: manualBoxCount(), modelBoxes: modelBoxCount(),
      // Where this frame's inference came from: a stored file from an earlier run
      // (marked by the server, with its own timestamp) or the result of inference
      // run on this frame now, which is never written to disk. A live or replay
      // frame is not the dataset frame, so its stored result is not reported there.
      storedInference: state.source.kind !== 'live' && state.fresult?.inference?.stored_inference === true,
      inferenceAt: state.source.kind !== 'live' && state.fresult?.inference?.saved_at || null},
    cloth: {verdict: {...state.cloth.verdict}, quad: state.cloth.quad ? {...state.cloth.quad} : null, polygon: state.cloth.polygon || null, reference: state.cloth.reference ? {source: state.cloth.reference.source, width: state.cloth.reference.width, height: state.cloth.reference.height} : null, pockets: {...(state.cloth.pockets || {source:null, count:0, reference:null})}, refusal: state.cloth.refusal && !state.cloth.refusal.ok ? {...state.cloth.refusal} : null, notice: clothNotice(state.cloth.verdict, state.cloth.refusal)},
    enroll: {status: state.enroll.status, payload: state.enroll.payload, name: state.enroll.name, error: state.enroll.error,
             // How long the preview has been collecting faces, so the rail can say
             // it is working rather than spinning forever.
             elapsed_ms: state.enroll.status === 'pending' ? Math.max(0, Date.now() - state.enroll.startedAt) : null},
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
  // Every key names the slot it labels: the two pocket keys that used to carry
  // the footer copy are gone (pocket names are data keys and were never shell
  // slots), and the footer slots are named after themselves.
  'footer-left':'本地数据 · 显式保存', 'footer-right':'复核结论在核验前不是真值。'
};
// Only UI-owned copy is eligible: never walk notes, source facts, or raw data.
const editorCopy = {
  'Raw decoded frame':'原始解码帧', 'Frame overlays':'帧叠加层',
  'Pick a moment on the scrub strip, or select a cue, then freeze it here.':'在拖动条上选择时刻，或选择一条线索，然后在此冻结。',
  'STALE':'已过期', 'live':'直播', 'VOD replay':'回放', 'Close':'关闭', 'No crop at this frame':'此帧没有裁剪图',
  'The label is written to this crop':'标注将写入此裁剪图', 'Select a crop cue in the rail to label it':'请在左栏选择裁剪图线索以标注',
  'Select a ball or a crop first.':'请先选择球或裁剪图。', 'Select a visible track first.':'请先选择可见的轨迹。',
  'This track has no identity cluster yet.':'此轨迹尚无身份聚类。', 'saving…':'保存中…', 'save failed':'保存失败',
  'Type a guest name or choose a regular before saving.':'请先输入访客姓名或选择常客，再保存。',
  'Select the person on the stage first: enrolment starts from their box in this frame.':'请先在舞台上选择该人物：登记从他/她在此帧的标注框开始。',
  'Preview the person before confirming.':'请先预览该人物再确认。',
  'Enrolment preview failed':'登记预览失败',
  'Nothing is bound to this track yet.':'该轨迹尚未绑定任何标注。',
  'Your changes remain on screen; retry when ready.':'更改仍保留在屏幕上，可稍后重试。',
  'Choose a verdict before saving.':'请先选择判定再保存。', 'Saving…':'保存中…',
  'Discard unsaved changes?':'放弃未保存的更改？', 'Live start failed':'直播启动失败', 'STALE state':'已过期状态',
  'Freeze a frame before running inference.':'运行推理前请先冻结一帧。',
  'Choose at least one detector (table, person, balls).':'请至少选择一个检测器（球桌、人物、球）。',
  'Starting inference on frame':'正在启动帧', 'Inference running for frame':'正在对帧运行推理：',
  'Inference failed to start':'推理启动失败', 'Inference failed.':'推理失败。', 'Frame inference failed':'帧推理失败',
  'Inference completed for frame':'帧推理已完成：', 'Inference for frame':'帧', 'finished; freeze that frame to see its overlays.':'推理已完成；冻结该帧可查看叠加层。',
  'Inference overlays updated for the frozen frame.':'冻结帧的推理叠加层已更新。', 'Inference status error':'推理状态错误',  'Status check failed.':'状态检查失败。', 'Idle.':'空闲。', 'Rebuilding…':'正在重建…', 'Status':'状态',
  'No saved corner set exists for this dataset: the model quad is drawn unverified and pocket markers stay hidden.':'此数据集没有已保存的角点集：模型四边形按未校验绘制，袋口标记不显示。',
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
  'Saved':'已保存', 'cleared':'已清除', 'Cue 0':'母球 0', 'Select a cue first.':'请先选择线索。', 'cue':'母球', 'shot':'击球', 'pot':'入袋', 'correct':'正确', 'wrong':'错误', 'unsure':'不确定', 'Track':'轨迹', 'Track window':'轨迹窗口', 'Delete selected':'删除所选', 'Draw box':'绘制标注框', 'Select / move':'选择 / 移动',
  'Selected label':'所选标注', 'New box label':'新框标注', 'Add table polygon':'添加球桌多边形', 'Clear polygon':'清除多边形',
  'solid':'实色', 'stripe':'花色', 'eight':'黑八', 'person':'人物', 'cue':'母球', 'ball':'球', 'table':'球桌',
  // Source tags the engine paints on the imagery, and the identity chip.
  'MODEL':'模型', 'YOURS':'人工', 'CALIB':'标定', 'EVENT':'事件', 'track':'轨迹', 'unbound':'未绑定',
  'saved anchors':'已保存锚点', 'saved calibration':'已保存标定',
  // Stage video state and the honesty rule that goes with it: what is drawn over
  // moving video, and what only comes back on a freeze.
  'playing':'播放中', 'paused':'已暂停', 'window':'窗口', 'loop':'循环', 'colour unknown':'颜色未知',
  'per-frame detections update on freeze':'逐帧检测在冻结后更新',
  'per-frame detections return on freeze':'逐帧检测在冻结后恢复',
  'The stage video failed to load; freeze a frame to inspect it as a still.':'舞台视频加载失败；可冻结一帧以静帧方式检查。',
  'The browser refused to play the stage video; freeze a frame instead.':'浏览器拒绝播放舞台视频；请改为冻结一帧。'
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
  [/^Tracks unavailable\. ([\s\S]*)$/, detail => `轨迹不可用。${detail}`],
  // Save receipts are engine-built too: they localize at render time like notices.
  [/^crop (.+) = (.+)$/, (file, value) => `裁剪图 ${file} = ${text(value)}`],
  [/^win (.+) · track (.+) = (.+)$/, (win, track, role) => `窗口 ${win} · 轨迹 ${track} = ${text(role)}`],
  [/^(\d+) anchors @ t (.+)$/, (count, at) => `${count} 个锚点 @ t ${at}`],
  [/^frame (\d+) · (\d+) boxes( \+ polygon)?$/, (frame, boxes, polygon) => `帧 ${frame} · ${boxes} 个标注框${polygon ? ' + 多边形' : ''}`],
  [/^(shot|cue) #(.+?) (shot|pot) @ frame (\d+) · (.+)$/, (kind, id, type, frame, verdict) => `${text(type === 'pot' ? 'pot' : 'shot')} #${id} @ 帧 ${frame} · ${text(verdict)}`],
  [/^(\d+) anchors @ t ([\d.]+)$/, (count, at) => `${count} 个锚点 @ t ${at}`],
  [/^([\s\S]*?)\. The review API is unavailable\. Use the project review server, not a file:\/\/ URL\.$/, detail => `${detail}。复核 API 不可用。请通过项目复核服务器打开，而非 file:// 地址。`],
  [/^Inference completed for frame (\d+)\.$/, frame => `帧 ${frame} 推理已完成。`],
  [/^Inference completed for frame (\d+) \(not stored\)\.$/, frame => `帧 ${frame} 推理已完成（未存储）。`],
  [/^Inference running for frame (\d+): (.*)…$/, (frame, stage) => `正在对帧 ${frame} 运行推理：${stage}…`],
  [/^Starting inference on frame (\d+) \((.*)\)…$/, (frame, detectors) => `正在启动帧 ${frame} 的推理（${detectors}）…`],
  [/^Frame inference failed: ([\s\S]*)$/, detail => `帧推理失败：${detail}`],
  // Why the stage is empty where a table quad or a saved correction would be:
  // these lines are composed from the verdict, so they localize as templates.
  [/^Saved correction belongs to (.+), not this frame \((.+)\) — not drawn\.$/, (owner, expected) => `已保存的修正属于 ${owner}，与当前帧（${expected}）不符——未绘制。`],
  [/^The model table quad is ([\d.]+) px off this dataset's saved corners \((.+), tolerance ([\d.]+) px\) — not drawn\.$/, (off, source, tolerance) => `模型球桌四边形与本数据集已保存角点相差 ${off} px（${source}，容差 ${tolerance} px）——未绘制。`],
  [/^The model table quad is not a valid table quad for this frame \((.+)\) — not drawn\.$/, detail => `模型球桌四边形对本帧不是有效的球桌四边形（${detail}）——未绘制。`],
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
  selectEvent, playEvent, selectCrop, selectTrack, selectTrackAndSeek, selectAnchor, selectBox, clearSelection,
  selectStageBall, selectStagePerson,
  saveVerdict, cycleVerdict, setVerdictDraft, setShooter, setNote, labelBall, setSeed, seedIdentity, clearIdentity,
  enrollPreview, enrollConfirm, setEnrollName, cancelEnroll,
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
