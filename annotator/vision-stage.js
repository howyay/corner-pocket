/* vision-stage: the thin Vision adapter. It renders the source chip row, the
   cues rail, the layer chips, the inspector and the scrub strip from the review
   engine's snapshot(), and calls the engine's entry points. It owns no frame
   state and performs no fetch of its own. */
(() => {
'use strict';
const COPY = {
  en: {
    cues:'Cues', inspector:'Inspector', sources:'Source', events:'Events', balls:'Balls', persons:'Persons',
    anchors:'Anchors', cloth:'Cloth', pockets:'Pockets', verdict:'Verdict', shooter:'Shooter', notes:'Notes',
    all:'All', shots:'Shots', pots:'Pots', pending:'Unreviewed', labels:'Label ball', queue:'Ball queue',
    tracks:'Person tracks', identity:'Identity', calibration:'Calibration', frameIndex:'Frame', step:'Step',
    freeze:'Freeze', play:'Play', pause:'Pause', ticks:'Event ticks', dataset:'Dataset',
    start:'Start', stop:'Stop', detectors:'Frame detectors', table:'Table', person:'Person', ball:'Balls',
    latency:'Twitch upstream delay: UNKNOWN. Receive-to-result is local processing latency, not glass-to-glass latency.',
    freshness:'Freshness', saved:'Saved channels', addChannel:'Save Twitch channel', channelUrl:'Twitch source URL',
    select:'Select', remove:'Remove', chat:'Chat', showChat:'Show chat', hideChat:'Hide chat',
    startFailed:'Start attempt', cause:'Cause', remedy:'Remedy', retry:'Retry',
    remedyText:'Check that the source is a saved canonical Twitch channel, or that the allowlisted dataset media exists.',
    correct:'Correct', wrong:'Wrong', unsure:'Unsure', saveReview:'Save review', nextCue:'Next candidate →',
    evidence:'Source evidence', notReviewed:'Not reviewed', reviewed:'Reviewed', unlabeled:'Unlabeled',
    unknown:'Unknown', cue:'Cue', clear:'Clear label', prevCrop:'← Previous crop', nextCrop:'Next crop →',
    ignore:'Ignore', clearSeed:'Clear seed', rebuild:'Rebuild assignments', refresh:'Refresh status',
    seedHint:'Seeds save immediately. Saving a seed alone does not rebuild predictions.',
    saveAnchors:'Save six anchors', anchorsAt:'Load anchors at', anchorNote:'Anchors belong to the raw source frame; saving stores anchor annotations only, it never fits a calibration.',
    boxLabel:'Box label', deleteBox:'Delete selected', saveCorrections:'Save corrections for this frame',
    runInference:'Run inference on frozen frame', addPolygon:'Add table polygon', clearPolygon:'Clear polygon',
    newBoxLabel:'New box label', tool:'Tool', selectTool:'Select / move', drawTool:'Draw box',
    frameReadout:'frame', overlays:'overlays', loading:'LOADING', none:'none', on:'ON',
    live:'live', stale:'STALE', age:'frame age', receive:'receive-to-result', dropped:'dropped',
    selectCueHint:'Selecting a cue seeks and freezes the stage. Overlays are layer chips; nothing switches mode.',
    noCrops:'No crops in this queue.', noTracks:'No track windows are available for this VOD.',
    noEvents:'No event candidates in this filter.', vodOnlyAnchors:'Anchors are available for the vod30 dataset only.',
    keys:'SPACE play · ←/→ step · 0–9/U/C label · A/B identity · V verdict · ⏎ save',
    cropAtFrame:'crop at this frame', selectedBall:'Ball', trackWord:'Track', box:'Box', anchorWord:'Anchor',
    seedA:'Player A', seedB:'Player B', regular:'Name (identity pipeline)', bindName:'Bind name',
    noCluster:'No identity cluster on this track yet — pick a person box on the stage that has one.',
    loading2:'loading…', reviewedCount:'reviewed', inQueue:'in queue', crops:'crops', reviewedWord:'reviewed',
    prediction:'prediction', seed:'saved seed', liveState:'Live state', manual:'manual', detectorReason:'The balls detector (SAM3) is CPU-heavy and stays an explicit opt-in.',
    attemptSource:'Attempted source', frameCount:'frames', keyMap:'Key map', showCues:'Cues', showInspector:'Inspector',
    notGlass:'receive-to-result is local processing latency, not glass-to-glass',
    stageEmpty:'Pick a moment on the strip, or select a cue, then freeze it here.', noCropHere:'no crop at this frame',
    liveNow:'live', staleNow:'STALE'
  },
  zh: {
    cues:'线索', inspector:'检查器', sources:'视频源', events:'事件', balls:'球', persons:'人物',
    anchors:'锚点', cloth:'台呢', pockets:'袋口', verdict:'判定', shooter:'击球者', notes:'备注',
    all:'全部', shots:'击球', pots:'入袋', pending:'未复核', labels:'球号标注', queue:'裁剪图队列',
    tracks:'人物轨迹', identity:'身份', calibration:'标定', frameIndex:'帧', step:'步进',
    freeze:'冻结', play:'播放', pause:'暂停', ticks:'事件刻度', dataset:'数据集',
    start:'开始', stop:'停止', detectors:'帧检测器', table:'球桌', person:'人物', ball:'球',
    latency:'Twitch 上游延迟：未知。接收到结果仅为本地处理耗时，不是端到端延迟。',
    freshness:'新鲜度', saved:'已保存频道', addChannel:'保存 Twitch 频道', channelUrl:'Twitch 来源地址',
    select:'选择', remove:'移除', chat:'聊天', showChat:'显示聊天', hideChat:'隐藏聊天',
    startFailed:'启动尝试', cause:'原因', remedy:'处理', retry:'重试',
    remedyText:'请确认来源是已保存的标准 Twitch 频道，或数据集媒体确实存在。',
    correct:'正确', wrong:'错误', unsure:'不确定', saveReview:'保存复核', nextCue:'下一个候选 →',
    evidence:'原始证据', notReviewed:'未复核', reviewed:'已复核', unlabeled:'未标注',
    unknown:'未知', cue:'母球', clear:'清除标注', prevCrop:'← 上一张裁剪图', nextCrop:'下一张裁剪图 →',
    ignore:'忽略', clearSeed:'清除种子', rebuild:'重建分配', refresh:'刷新状态',
    seedHint:'种子立即保存。仅保存种子不会重建预测。',
    saveAnchors:'保存六个锚点', anchorsAt:'加载锚点时刻', anchorNote:'锚点属于原始源帧；保存仅存储锚点标注，不会拟合标定。',
    boxLabel:'标注框标签', deleteBox:'删除所选', saveCorrections:'保存此帧修正',
    runInference:'对冻结帧运行推理', addPolygon:'添加球桌多边形', clearPolygon:'清除多边形',
    newBoxLabel:'新框标注', tool:'工具', selectTool:'选择 / 移动', drawTool:'绘制标注框',
    frameReadout:'帧', overlays:'叠加层', loading:'加载中', none:'无', on:'开',
    live:'直播', stale:'已过期', age:'帧龄', receive:'接收到结果', dropped:'丢帧',
    selectCueHint:'选择线索会定位并冻结舞台。叠加层为图层开关，不再切换模式。',
    noCrops:'此队列没有裁剪图。', noTracks:'此录像没有可用的轨迹窗口。',
    noEvents:'此筛选下没有事件候选。', vodOnlyAnchors:'锚点仅适用于 vod30 数据集。',
    keys:'空格 播放 · ←/→ 步进 · 0–9/U/C 标注 · A/B 身份 · V 判定 · ⏎ 保存',
    cropAtFrame:'此帧的裁剪图', selectedBall:'球', trackWord:'轨迹', box:'标注框', anchorWord:'锚点',
    seedA:'选手 A', seedB:'选手 B', regular:'姓名（身份流程）', bindName:'绑定姓名',
    noCluster:'此轨迹尚无身份聚类——请在舞台上选择带有聚类的球员框。',
    loading2:'读取中…', reviewedCount:'已复核', inQueue:'队列中', crops:'张裁剪图', reviewedWord:'已复核',
    prediction:'预测', seed:'已保存种子', liveState:'直播状态', manual:'人工', detectorReason:'球检测器（SAM3）为 CPU 密集，需显式开启。',
    attemptSource:'尝试的来源', frameCount:'帧数', keyMap:'按键', showCues:'线索', showInspector:'检查器',
    notGlass:'接收到结果为本地处理耗时，并非端到端延迟',
    stageEmpty:'在拖动条上选择时刻，或选择一条线索，然后在此冻结。', noCropHere:'此帧没有裁剪图',
    liveNow:'直播', staleNow:'已过期'
  }
};
let opts = null, root = null, sig = {}, sheet = 'cues', ageTimer = null;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const t = key => (COPY[opts?.lang] || COPY.en)[key] || COPY.en[key] || key;
const $ = id => root ? root.querySelector(id) : null;
const engine = () => opts?.review;
const snap = () => engine()?.snapshot ? engine().snapshot() : null;
const timecode = value => { const tenths = Math.round((Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0) * 10); const m = Math.floor(tenths / 600), seconds = ((tenths % 600) / 10).toFixed(1); return `${m}:${seconds.padStart(4, '0')}`; };
const fmtAge = ms => ms == null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
// One vocabulary for processor states, owned by the engine (idle / starting /
// running / stopping / stopped / eos / error), so 中 mode never shows a raw
// English state word.
const stateText = value => engine()?.liveStateText ? engine().liveStateText(value) : String(value ?? '');
function labelText(label) { if (label === 'u' || label === -1) return t('unknown'); if (label === 0) return `${t('cue')} · 0`; return `#${label}`; }
function receiptLine(kind) {
  const row = (snap()?.receipts || []).find(r => r.key === kind);
  if (!row) return '';
  if (!row.at) return `<p class="vs-receipt pending">· ${esc(row.text)}</p>`;
  const age = Math.max(0, (Date.now() - row.at) / 1000);
  return `<p class="vs-receipt${row.error ? ' error' : ''}" data-receipt-at="${row.at}">${row.error ? '!' : '✓'} ${esc(row.text)} · ${age.toFixed(1)} s ${esc(t('saved'))}</p>`;
}
function receiptAge() {
  if (!root) return;
  const now = Date.now(), saved = opts?.lang === 'zh' ? '已保存' : 'Saved';
  root.querySelectorAll('[data-receipt-at]').forEach(node => {
    node.textContent = node.textContent.replace(/[\d.]+ s (?:已保存|Saved)$/, `${Math.max(0, (now - Number(node.dataset.receiptAt)) / 1000).toFixed(1)} s ${saved}`);
  });
}
// ---- regions -------------------------------------------------------------
function chipsHTML(s) {
  const channels = (opts.channels() || []).map(c => `<button class="vs-chip${s.source.kind === 'live' && s.source.channel === c.channel ? ' active' : ''}" data-vs-action="pick-live" data-vs-value="twitch:${esc(c.id)}">${s.source.kind === 'live' && s.source.channel === c.channel ? '● ' : ''}${esc(t('live'))} · twitch ${esc(c.channel || '')}</button>`).join('');
  const datasets = (s.datasets || []).map(d => `<button class="vs-chip${s.source.kind === 'vod' && d.id === s.dataset ? ' active' : ''}" data-vs-action="pick-dataset" data-vs-value="${esc(d.id)}">${esc(d.label || d.id)}</button>`).join('');
  const freshness = s.source.kind === 'live'
    ? `<span class="vs-fresh${s.live.stale ? ' stale' : ''}">${s.live.stale ? esc(t('stale')) : esc(t('live'))} · ${esc(t('age'))} ${fmtAge(s.live.frame_age_ms)}</span>`
    : `<span class="vs-fresh">${esc(s.source.label)}</span>`;
  return `<div class="vs-chiprow" role="group" aria-label="${esc(t('dataset'))}">${datasets}${channels}</div>
  <div class="vs-chipmeta">${freshness}<span class="vs-keys">${esc(t('keys'))}</span></div>`;
}
function railHTML(s) {
  const events = s.events.items.filter(e => s.eventFilter === 'all' || (s.eventFilter === 'pending' ? !e.verdict : e.type === s.eventFilter));
  const cards = events.length ? events.map((e, i) => `<article class="vs-card${e.id === s.selection.event?.id ? ' selected' : ''}" data-vs-action="select-event" data-vs-id="${esc(e.id)}">
      <div class="vs-card-row"><span class="vs-badge ${esc(e.type)}">${esc(e.type === 'pot' ? t('pots') : t('shots'))}</span><span class="vs-mono">${esc(timecode(e.t))}</span><span class="vs-mono vs-dim">#${esc(e.id)}</span>${e.nearest_pocket ? `<span class="vs-mono vs-dim">${esc(e.nearest_pocket)}</span>` : ''}</div>
      <div class="vs-verbs">${['correct','wrong','unsure'].map(v => `<button class="${e.verdict === v ? 'active' : ''}" data-vs-action="verdict" data-vs-id="${esc(e.id)}" data-vs-value="${v}" title="${esc(t(v))}" aria-label="${esc(t(v))}">${{correct:'✓',wrong:'✗',unsure:'?'}[v]}</button>`).join('')}<span class="vs-verb-label">${esc(e.verdict ? t(e.verdict) : t('notReviewed'))}</span></div>
    </article>`).join('') : `<p class="vs-empty">${esc(t('noEvents'))}</p>`;
  const crops = s.balls.items;
  const cropRows = crops.length ? crops.map(c => `<button class="vs-item${s.selection.crop && c.file === s.selection.crop.file ? ' selected' : ''}" data-vs-action="select-crop" data-vs-value="${esc(c.file)}"><span class="vs-mono">${esc(c.file)}</span><span class="vs-mono vs-dim">${esc(timecode(c.t))}</span><span class="vs-tag${c.label == null ? '' : ' done'}">${esc(c.label == null ? t('unlabeled') : labelText(c.label))}</span></button>`).join('') : `<p class="vs-empty">${esc(t('noCrops'))}</p>`;
  const tracks = s.persons.tracks.length ? s.persons.tracks.map(x => `<button class="vs-item${String(s.persons.track) === String(x.id) ? ' selected' : ''}" data-vs-action="select-track" data-vs-value="${esc(x.id)}"><span class="vs-mono">${esc(t('trackWord'))} ${esc(x.id)}</span><span class="vs-tag${x.seed ? ' done' : ''}">${esc(x.seed || x.label || '?')}</span></button>`).join('') : `<p class="vs-empty">${esc(t('noTracks'))}</p>`;
  return `<section class="vs-group${s.focus === 'events' ? ' focused' : ''}"><header><h3>${esc(t('events'))}</h3><span class="vs-mono">${esc(s.events.reviewed)} ${esc(t('reviewedWord'))}</span></header>
    <div class="vs-filters">${[['all','all'],['shot','shots'],['pot','pots'],['pending','pending']].map(([v, l]) => `<button class="vs-filter${s.eventFilter === v ? ' active' : ''}" data-vs-action="event-filter" data-vs-value="${v}">${esc(t(l))}</button>`).join('')}</div>${cards}</section>
  <section class="vs-group${s.focus === 'balls' ? ' focused' : ''}"><header><h3>${esc(t('queue'))}</h3><span class="vs-mono">${crops.length} ${esc(t('crops'))}</span></header>${cropRows}</section>
  <section class="vs-group${s.focus === 'persons' ? ' focused' : ''}"><header><h3>${esc(t('tracks'))}</h3>${s.persons.windows.length ? `<select id="vs-window">${s.persons.windows.map(w => `<option value="${esc(w.win)}" ${w.win === s.persons.win ? 'selected' : ''}>${esc(w.win)} · ${w.count}</option>`).join('')}</select>` : ''}</header>${tracks}</section>`;
}
function layersHTML(s) {
  const layers = [['cloth','cloth'],['balls','balls'],['persons','persons'],['pockets','pockets'],['anchors','anchors'],['events','events']];
  return layers.map(([key, label]) => {
    const gated = key === 'anchors' && s.dataset !== 'vod30';
    return `<button class="vs-layer${s.overlay[key] && !gated ? ' on' : ''}" data-vs-action="layer" data-vs-value="${key}" ${gated ? 'disabled' : ''} title="${gated ? esc(t('vodOnlyAnchors')) : esc(t(label))}">${esc(t(label))}</button>`;
  }).join('');
}
function identityHTML(s) {
  const sel = s.selection;
  if (sel.kind === 'ball') return sel.crop ? `${esc(t('selectedBall'))} · ${esc(t('cropAtFrame'))} ${esc(sel.crop.file)}${sel.crop.label != null ? ` · ${esc(labelText(sel.crop.label))}` : ''}` : esc(t('noCropHere'));
  if (sel.kind === 'person') return `${esc(t('trackWord'))} ${esc(sel.track)}`;
  if (sel.kind === 'anchor') return `${esc(t('anchorWord'))} ${Number(sel.anchor) + 1} · ${s.anchors.points[sel.anchor] ? `${Math.round(s.anchors.points[sel.anchor][0])}, ${Math.round(s.anchors.points[sel.anchor][1])}` : ''}`;
  if (sel.kind === 'event' && sel.event) return `#${esc(sel.event.id)} · ${esc(sel.event.type)} · ${esc(timecode(sel.event.t))}`;
  if (sel.kind === 'box') return `${esc(t('box'))} ${sel.box + 1} · ${esc(s.corrections.boxLabel || '')}`;
  return `${esc(t('sources'))} · ${esc(s.source.label)}`;
}
function factsLine(s) {
  const parts = [];
  // One word per state: the strip says the same thing the chip says.
  if (s.source.kind === 'live') parts.push(`${(s.live.stale ? t('stale') : t('live')).toLowerCase()}${s.live.seq != null ? ` · seq ${s.live.seq}` : ''}`, `${t('age')} ${fmtAge(s.live.frame_age_ms)}`, `${t('receive')} ${fmtAge(s.live.receive_to_result_ms)}`);
  else parts.push(`${t('frameReadout')} ${s.frame.index}`, `t ${Number(s.frame.t).toFixed(1)} s`);
  const d = s.drawn, auto = d.auto;
  // Model vs operator provenance: `<model> (+<manual> manual)`. The two numbers
  // add up to exactly what the painter drew, so the totals stay honest. Without
  // a provenance report from the painter the totals print alone - the line never
  // guesses who drew what.
  const layer = (key, label) => {
    const total = Number(d[key] || 0);
    if (!auto) return `${label} ${total}`;
    const manual = Math.max(0, total - Number(auto[key] || 0));
    return manual ? `${label} ${Number(auto[key] || 0)} (+${manual} ${t('manual')})` : `${label} ${total}`;
  };
  // Layer names come from the same copy table as the chips, so the facts line
  // is fully bilingual (EN keeps the design's lowercase technical tokens).
  parts.push(layer('cloth', t('cloth').toLowerCase()), layer('balls', t('balls').toLowerCase()), layer('persons', t('persons').toLowerCase()), t('pockets').toLowerCase() + ' ' + Number(d.pockets || 0), t('anchors').toLowerCase() + ' ' + Number(d.anchors || 0), layer('events', t('events').toLowerCase()));
  const total = d.cloth + d.balls + d.persons + d.pockets + d.anchors + d.events;
  if (s.loading.overlay) parts.push(`${t('overlays')} ${t('loading')} (${((Date.now() - s.loading.since) / 1000).toFixed(1)} s)`);
  else if (s.busy) parts.push(`${t('overlays')} ${t('loading2')}`);
  else parts.push(`${t('overlays')} ${total > 0 ? t('on') : t('none')}`);
  return parts.join(' · ');
}
function sourceBlock(s) {
  const attempt = s.live.attempt && s.live.attempt.error ? `<div class="vs-error-block"><h4>${esc(t('startFailed'))}</h4><p class="vs-mono">${esc(t('attemptSource'))}: ${esc(s.live.attempt.source || '—')}</p><p class="vs-mono">${esc(s.live.attempt.error)}</p><p>${esc(t('remedy'))}: ${esc(t('remedyText'))}</p><button data-vs-action="live-start">${esc(t('retry'))}</button></div>` : '';
  const channels = (opts.channels() || []).map(c => `<div class="vs-channel"><span class="vs-mono">${esc(c.url)}</span><button data-vs-action="pick-live" data-vs-value="twitch:${esc(c.id)}">${esc(t('select'))}</button><button data-vs-action="forget-channel" data-vs-id="${esc(c.id)}">${esc(t('remove'))}</button></div>`).join('');
  const live = s.live;
  return `${attempt}
  <h3>${esc(t('sources'))}</h3>
  <p class="vs-note">${esc(t('selectCueHint'))}</p>
  <div class="vs-block"><h4>${esc(t('dataset'))}</h4><div class="vs-chiprow">${(s.datasets || []).map(d => `<button class="vs-chip${s.source.kind === 'vod' && d.id === s.dataset ? ' active' : ''}" data-vs-action="pick-dataset" data-vs-value="${esc(d.id)}">${esc(d.label || d.id)}</button>`).join('')}</div>
    <p class="vs-mono">${esc(s.source.kind === 'vod' ? s.source.label : '—')} · ${esc(t('frameCount'))} ${esc(s.frame.count)}</p></div>
  <div class="vs-block"><h4>${esc(t('liveState'))}</h4>
    <p class="vs-mono" id="vs-live-status">${esc(stateText(live.state))}${live.error ? ` · ${esc(live.error)}` : ''} · ${esc(t('age'))} ${fmtAge(live.frame_age_ms)} · ${esc(t('receive'))} ${fmtAge(live.receive_to_result_ms)} · ${esc(t('dropped'))} ${esc(live.skipped ?? 0)}</p>
    <div class="vs-chiprow">${channels}${(s.datasets || []).map(d => `<button class="vs-chip" data-vs-action="pick-live" data-vs-value="dataset:${esc(d.id)}">${esc(d.label || d.id)}</button>`).join('')}</div>
    <div class="vs-row">${['table','person'].map(d => `<label class="vs-check"><input type="checkbox" data-vs-action="live-detector" data-vs-value="${d}" ${(live.detectors || []).includes(d) ? 'checked' : ''}> ${esc(t(d))}</label>`).join('')}</div>
    <div class="vs-row"><button data-vs-action="live-start" class="primary">${esc(t('start'))}</button><button data-vs-action="live-stop">${esc(t('stop'))}</button></div>
    <p class="vs-note">${esc(t('latency'))}</p></div>
  <div class="vs-block"><h4>${esc(t('detectors'))}</h4><div class="vs-row">${[['table','table'],['person','person'],['balls','ball']].map(([k, l]) => `<label class="vs-check"><input type="checkbox" data-vs-action="detector" data-vs-value="${k}" ${s.detectors[k] ? 'checked' : ''}> ${esc(t(l))}</label>`).join('')}</div><p class="vs-note">${esc(t('detectorReason'))}</p></div>
  <div class="vs-block"><h4>${esc(t('saved'))}</h4>${channels || `<p class="vs-empty">—</p>`}
    <form id="source-form"><label class="vs-field">${esc(t('channelUrl'))}<input name="url" type="url" placeholder="https://www.twitch.tv/channel" required></label><button class="primary">${esc(t('addChannel'))}</button></form></div>`;
}
function eventBlock(s) {
  const item = s.selection.event || s.events.items[s.events.index];
  if (!item) return `<h3>${esc(t('events'))}</h3><p class="vs-empty">${esc(t('noEvents'))}</p>`;
  const annotation = item.annotation || {};
  const verdict = s.verdictDraft ?? annotation.verdict ?? '';
  const dataset = encodeURIComponent(s.dataset);
  const evidence = item.evidence ? `/media/${dataset}/evidence/${encodeURIComponent(String(item.evidence).split('/').pop())}` : `/media/${dataset}/event-frame/${encodeURIComponent(item.id)}`;
  return `<h3>${esc(item.type === 'pot' ? t('pots') : t('shots'))} <span class="vs-mono vs-dim">#${esc(item.id)}</span></h3>
  <p class="vs-mono">${esc(timecode(item.t))}${item.nearest_pocket ? ` · ${esc(item.nearest_pocket)}` : ''}</p>
  <figure class="vs-evidence"><video controls loop muted playsinline preload="metadata" poster="${esc(evidence)}" src="/api/clip?dataset=${dataset}&t=${encodeURIComponent(item.t)}" data-vs-fallback="${esc(evidence)}"></video><figcaption class="vs-mono">${esc(t('evidence'))}</figcaption></figure>
  <div class="vs-block"><h4>${esc(t('verdict'))}</h4><div class="vs-row">${['correct','wrong','unsure'].map(v => `<button class="${verdict === v ? 'active' : ''}" data-vs-action="verdict-draft" data-vs-value="${v}">${esc(t(v))}</button>`).join('')}</div></div>
  <label class="vs-field">${esc(t('shooter'))}<select data-vs-action="shooter">${[['','—'],['A',t('seedA')],['B',t('seedB')],['?',t('unknown')]].map(([v, l]) => `<option value="${v}" ${(annotation.shooter || '') === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
  <label class="vs-field">${esc(t('notes'))}<textarea rows="3" data-vs-action="note">${esc(annotation.note || '')}</textarea></label>
  <div class="vs-row"><button class="primary" data-vs-action="save-verdict">${esc(t('saveReview'))}</button><button data-vs-action="next-event">${esc(t('nextCue'))}</button></div>
  ${receiptLine('event')}`;
}
function ballBlock(s) {
  const crop = s.selection.crop;
  if (!crop) return `<h3>${esc(t('labels'))}</h3><p class="vs-empty">${esc(t('noCrops'))}</p>${receiptLine('ball')}`;
  const file = crop.file.split('/').pop();
  const label = crop.label;
  const ctx = crop.ctx ? `<img class="ctx" src="/media/balls/${encodeURIComponent(s.set)}/ctx/${encodeURIComponent(crop.ctx)}" alt="">` : '';
  return `<h3>${esc(t('labels'))}</h3>
  <div class="vs-crop"><img src="/media/balls/${encodeURIComponent(s.set)}/${encodeURIComponent(file)}" alt="${esc(file)}">${ctx}</div>
  <p class="vs-mono">${esc(file)} · ${esc(timecode(crop.t))}${crop.score != null ? ` · ${Number(crop.score).toFixed(2)}` : ''}</p>
  <div class="vs-ballgrid">${Array.from({length:10},(_,i) => `<button class="${label === i ? 'active' : ''}" data-vs-action="label-ball" data-vs-value="${i}">${i}</button>`).join('')}</div>
  <div class="vs-row"><button class="${label === 'u' ? 'active' : ''}" data-vs-action="label-ball" data-vs-value="-1">${esc(t('unknown'))}</button><button class="${label === 0 ? 'active' : ''}" data-vs-action="label-ball" data-vs-value="0">${esc(t('cue'))} 0</button><button data-vs-action="label-ball" data-vs-value="clear">${esc(t('clear'))}</button></div>
  <div class="vs-row"><button data-vs-action="crop-step" data-vs-value="-1">${esc(t('prevCrop'))}</button><button data-vs-action="crop-step" data-vs-value="1">${esc(t('nextCrop'))}</button></div>
  ${receiptLine('ball')}`;
}
function personBlock(s) {
  const track = s.persons.tracks.find(x => String(x.id) === String(s.persons.track)) || null;
  const seed = track?.seed || null;
  const person = s.selection.person || {};
  const cluster = person.cluster_id || null;
  const names = (opts.regulars() || []);
  return `<h3>${esc(t('identity'))}</h3>
  <p class="vs-mono">${esc(t('trackWord'))} ${esc(s.persons.track ?? '—')} · ${esc(t('prediction'))}: ${esc(track?.label || '—')} · ${esc(t('seed'))}: ${esc(seed || '—')}</p>
  <div class="vs-row"><button class="${seed === 'A' ? 'active' : ''}" data-vs-action="seed" data-vs-value="A">${esc(t('seedA'))}</button><button class="${seed === 'B' ? 'active' : ''}" data-vs-action="seed" data-vs-value="B">${esc(t('seedB'))}</button><button class="${seed === 'ignore' ? 'active' : ''}" data-vs-action="seed" data-vs-value="ignore">${esc(t('ignore'))}</button><button data-vs-action="seed" data-vs-value="clear">${esc(t('clearSeed'))}</button></div>
  <p class="vs-note">${esc(t('seedHint'))}</p>
  <div class="vs-block"><h4>${esc(t('regular'))}</h4>${cluster ? `<div class="vs-row"><select data-vs-action="regular">${names.map(n => `<option value="${esc(n.id)}">${esc(n.name)}</option>`).join('') || '<option value="">—</option>'}</select><button data-vs-action="bind-regular">${esc(t('bindName'))}</button></div>` : `<p class="vs-empty">${esc(t('noCluster'))}</p>`}</div>
  <div class="vs-block"><h4>${esc(t('rebuild'))}</h4><div class="vs-row"><button data-vs-action="rebuild">${esc(t('rebuild'))}</button><button data-vs-action="rebuild-refresh">${esc(t('refresh'))}</button></div><p class="vs-mono">${esc(s.persons.status || '')}</p></div>
  ${receiptLine('person')}`;
}
function anchorBlock(s) {
  if (s.dataset !== 'vod30') return `<h3>${esc(t('calibration'))}</h3><p class="vs-empty">${esc(t('vodOnlyAnchors'))}</p>`;
  const rows = s.anchors.points.map((p, i) => `<button class="vs-item${s.selection.anchor === i ? ' selected' : ''}" data-vs-action="select-anchor" data-vs-value="${i}"><span>${i + 1}</span><span class="vs-mono">${Math.round(p[0])}, ${Math.round(p[1])}</span></button>`).join('');
  return `<h3>${esc(t('calibration'))}</h3>
  <p class="vs-note">${esc(t('anchorNote'))}</p>
  <div class="vs-items">${rows || `<p class="vs-empty">${esc(t('loading2'))}</p>`}</div>
  <div class="vs-nudge"><button data-vs-action="nudge" data-vs-value="0,-1">↑</button><button data-vs-action="nudge" data-vs-value="-1,0">←</button><button data-vs-action="nudge" data-vs-value="1,0">→</button><button data-vs-action="nudge" data-vs-value="0,1">↓</button></div>
  <div class="vs-row">${[70,200,350].map(x => `<button data-vs-action="anchors-at" data-vs-value="${x}">${esc(t('anchorsAt'))} ${x} s</button>`).join('')}</div>
  <div class="vs-row"><button class="primary" data-vs-action="save-anchors">${esc(t('saveAnchors'))}</button></div>
  <p class="vs-mono">${s.anchors.loaded ? `t ${Number(s.anchors.t).toFixed(1)} s` : esc(t('loading2'))}</p>
  ${receiptLine('anchor')}`;
}
function boxBlock(s) {
  const index = s.selection.box;
  const labels = ['person','ball','cue','solid','stripe','eight'];
  return `<h3>${esc(t('box'))} ${index + 1}</h3>
  <label class="vs-field">${esc(t('boxLabel'))}<select data-vs-action="box-label">${labels.map(l => `<option value="${l}" ${s.corrections.boxLabel === l ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
  <div class="vs-row"><button data-vs-action="delete-box">${esc(t('deleteBox'))}</button></div>
  <div class="vs-block"><h4>${esc(t('tool'))}</h4><div class="vs-row"><button class="${s.corrections.tool === 'select' ? 'active' : ''}" data-vs-action="tool" data-vs-value="select">${esc(t('selectTool'))}</button><button class="${s.corrections.tool === 'draw' ? 'active' : ''}" data-vs-action="tool" data-vs-value="draw">${esc(t('drawTool'))}</button></div>
    <label class="vs-field">${esc(t('newBoxLabel'))}<select data-vs-action="new-box-label">${labels.map(l => `<option value="${l}" ${s.corrections.newBoxLabel === l ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
    <div class="vs-row"><button data-vs-action="add-polygon">${esc(t('addPolygon'))}</button><button data-vs-action="clear-polygon">${esc(t('clearPolygon'))}</button></div></div>
  <div class="vs-block"><h4>${esc(t('runInference'))}</h4><p class="vs-mono">${esc(s.corrections.inferStatus || '')}</p><div class="vs-row"><button data-vs-action="run-inference">${esc(t('runInference'))}</button><button class="primary" data-vs-action="save-corrections">${esc(t('saveCorrections'))}</button></div>${receiptLine('corrections')}</div>`;
}
function inspectorHTML(s) {
  const kind = s.selection.kind;
  const body = kind === 'event' ? eventBlock(s) : kind === 'ball' ? ballBlock(s) : kind === 'person' ? personBlock(s) : kind === 'anchor' ? anchorBlock(s) : kind === 'box' ? boxBlock(s) : sourceBlock(s);
  const liveChat = s.source.kind === 'live' && s.source.channel && opts.chat();
  const chat = liveChat ? `<div class="vs-chat"><iframe title="Twitch chat" src="https://www.twitch.tv/embed/${esc(s.source.channel)}/chat?parent=${esc(location.hostname)}&darkpopout"></iframe></div>` : '';
  const chatToggle = s.source.kind === 'live' && s.source.channel ? `<button class="vs-chat-toggle" data-vs-action="chat">${esc(opts.chat() ? t('hideChat') : t('showChat'))}</button>` : '';
  const close = kind === 'none' ? '' : `<button class="vs-close" data-vs-action="deselect" aria-label="×">×</button>`;
  const notice = s.notice.text ? `<div class="vs-notice${s.notice.error ? ' error' : ''}" role="status">${esc(s.notice.text)}</div>` : '';
  return `${chat}${chatToggle}${close}${notice}${body}`;
}
// ---- rendering -----------------------------------------------------------
function render() {
  const s = snap();
  if (!root || !s) return;
  const chips = chipsHTML(s);
  if (chips !== sig.chips) { const node = $('#vs-chips'); if (node) node.innerHTML = chips; sig.chips = chips; }
  const railSig = `${s.focus}|${s.eventFilter}|${s.events.index}|${s.events.items.map(e => `${e.id}:${e.verdict}`).join(',')}|${s.balls.items.length}|${s.balls.index}|${s.selection.crop?.file || ''}|${s.persons.win}|${s.persons.tracks.map(x => `${x.id}:${x.seed || ''}`).join(',')}|${s.persons.track || ''}|${s.events.reviewed}|${opts.lang}`;
  if (railSig !== sig.rail) { const node = $('#vs-cues'); if (node) node.innerHTML = railHTML(s); sig.rail = railSig; }
  const layersSig = `${s.dataset}|${Object.entries(s.overlay).map(([k, v]) => `${k}${v ? 1 : 0}`).join('')}`;
  if (layersSig !== sig.layers) { const node = $('#vs-layers'); if (node) node.innerHTML = layersHTML(s); sig.layers = layersSig; }
  const identity = identityHTML(s);
  if (identity !== sig.identity) { const node = $('#vs-identity'); if (node) node.innerHTML = identity; sig.identity = identity; }
  const insSig = `${s.selection.kind}|${s.selection.event?.id || ''}|${s.selection.crop?.file || ''}|${s.selection.crop?.label ?? ''}|${s.selection.track ?? ''}|${s.selection.anchor ?? ''}|${s.selection.box ?? ''}|${s.corrections.tool}|${s.corrections.boxLabel || ''}|${s.corrections.newBoxLabel || ''}|${s.corrections.inferStatus}|${s.corrections.result}|${s.persons.status}|${s.live.state}|${s.live.error || ''}|${s.live.attempt?.at || ''}|${s.live.detectors.join(',')}|${s.notice.text}|${s.busy}|${s.dataset}|${s.source.kind}|${(s.receipts || []).map(r => `${r.key}:${r.at}`).join(',')}|${opts.lang}`;
  if (insSig !== sig.inspector) { const node = $('#vs-inspector'); if (node) node.innerHTML = inspectorHTML(s); sig.inspector = insSig; }
  const frameInput = $('#vs-frame-index');
  if (frameInput && document.activeElement !== frameInput) frameInput.value = s.frame.index;
  const scrub = $('#vs-scrub');
  if (scrub && document.activeElement !== scrub) scrub.value = s.frame.index;
  const marksSig = `${s.dataset}|${s.frame.duration}|${s.events.items.map(e => `${e.id}:${e.t}:${e.type}`).join(',')}`;
  const marks = $('#vs-marks');
  if (marks && marksSig !== sig.marks) {
    marks.innerHTML = s.events.items.map(e => { const pct = e.t / s.frame.duration * 100; return pct >= 0 && pct <= 100 ? `<button class="scrub-mark ${esc(e.type)}" data-vs-action="select-event-time" data-vs-value="${esc(e.t)}" title="#${esc(e.id)} ${esc(e.type)} · ${esc(timecode(e.t))}" style="left:${pct}%"></button>` : ''; }).join('');
    sig.marks = marksSig;
  }
  const facts = $('#vs-facts'); if (facts) facts.textContent = factsLine(s);
  const edge = $('#vs-edge'); if (edge) { edge.dataset.live = s.source.kind === 'live' ? '1' : '0'; edge.style.left = `${s.source.kind === 'live' ? 100 : (s.frame.duration ? Math.min(100, Math.max(0, s.frame.t / s.frame.duration * 100)) : 0)}%`; }
  const play = $('#vs-play'); if (play) play.textContent = s.frame.playing ? `❚❚ ${t('pause')}` : `▶ ${t('play')}`;
  root.querySelectorAll('[data-vs-label]').forEach(node => { const copy = t(node.dataset.vsLabel); if (node.textContent !== copy) node.textContent = copy; });
  const frameField = $('#vs-frame-index');
  if (frameField) { const max = String(Math.max(0, s.frame.count - 1)); if (frameField.getAttribute('max') !== max) frameField.setAttribute('max', max); frameField.disabled = s.source.kind === 'live'; }
  // The strip is the VOD timeline; a live edge has no frame index to step.
  const liveStrip = s.source.kind === 'live';
  const strip = $('#vs-strip'); if (strip) strip.dataset.live = liveStrip ? '1' : '0';
  root.querySelectorAll('[data-vs-action="step"],[data-vs-action="freeze"],[data-vs-action="play"],#vs-scrub').forEach(node => { node.disabled = liveStrip; });
  const grid = $('.vs-grid'); if (grid) grid.dataset.sheet = sheet;
  root.querySelectorAll('[data-sheet-tab]').forEach(b => b.classList.toggle('active', b.dataset.sheetTab === sheet));
  if (!ageTimer) ageTimer = setInterval(receiptAge, 1000);
}
// ---- actions -------------------------------------------------------------
function act(action, value, node) {
  const target = engine();
  const s = snap();
  const num = Number(value);
  switch (action) {
    case 'pick-dataset': target.setDataset(value); break;
    case 'pick-live': opts.pickLive(value); break;
    case 'live-start': opts.startLive(); break;
    case 'live-stop': opts.stopLive(); break;
    case 'forget-channel': opts.forgetChannel(node.dataset.vsId); break;
    case 'live-detector': { const list = new Set(s.live.detectors || []); if (node.checked) list.add(value); else list.delete(value); opts.setLiveDetectors([...list]); break; }
    case 'detector': target.setDetector(value, node.checked); break;
    case 'layer': {
      const on = target.toggleOverlay(value);
      // Calibration is a layer: turning it on loads the anchors for their saved
      // time and seeks the one stage there, and the inspector echoes the anchor.
      if (value === 'anchors' && on) {
        if (!s.anchors.loaded) target.loadAnchors(70).then(() => { target.selectAnchor(0); target.seekTime(70); });
        else target.selectAnchor(s.anchors.index ?? 0);
      }
      break;
    }
    case 'event-filter': target.setEventFilter(value); break;
    case 'select-event': { const index = s.events.items.findIndex(e => String(e.id) === String(node.dataset.vsId)); if (index >= 0) target.selectEvent(index); break; }
    case 'select-event-time': { const index = s.events.items.findIndex(e => Number(e.t) === num); if (index >= 0) target.selectEvent(index); else target.seekTime(num); break; }
    case 'verdict': { const index = s.events.items.findIndex(e => String(e.id) === String(node.dataset.vsId)); if (index >= 0) { target.selectEvent(index); target.saveVerdict(null, value); } break; }
    case 'verdict-draft': target.setVerdictDraft(value); break;
    case 'shooter': target.setShooter(node.value); break;
    case 'note': target.setNote(node.value); break;
    case 'save-verdict': target.saveVerdict(node, null); break;
    case 'next-event': target.selectEvent(Math.min(s.events.items.length - 1, s.events.index + 1)); break;
    case 'select-crop': target.selectCrop(value); break;
    case 'crop-step': { const items = s.balls.items; const i = Math.max(0, Math.min(items.length - 1, s.balls.index + num)); if (items[i]) target.selectCrop(items[i].file); break; }
    case 'label-ball': target.labelBall(null, value === 'clear' ? 'clear' : Number(value)); break;
    case 'select-track': target.selectTrackAndSeek(value); break;
    case 'seed': target.setSeed(null, value); break;
    case 'bind-regular': { const select = root.querySelector('[data-vs-action="regular"]'); target.seedIdentity(null, select ? select.value : ''); break; }
    case 'rebuild': target.rebuild(node); break;
    case 'rebuild-refresh': target.refreshRebuild(); break;
    case 'select-anchor': target.selectAnchor(Number(value)); break;
    case 'nudge': { const [dx, dy] = String(value).split(',').map(Number); target.nudgeAnchor(dx, dy); break; }
    case 'anchors-at': target.loadAnchors(num).then(() => { target.selectAnchor(target.snapshot().anchors.index); target.seekTime(num); }); break;
    case 'save-anchors': target.saveAnchors(node); break;
    case 'tool': target.setTool(value); break;
    case 'new-box-label': target.setNewBoxLabel(node.value); break;
    case 'box-label': target.setBoxLabel(node.value); break;
    case 'delete-box': target.deleteBox(); break;
    case 'add-polygon': target.addPolygon(); break;
    case 'clear-polygon': target.clearPolygon(); break;
    case 'save-corrections': target.saveCorrections(node); break;
    case 'run-inference': target.runInference(node); break;
    case 'step': target.stepFrame(num); break;
    case 'freeze': target.freeze(); break;
    case 'play': target.setPlaying(!s.frame.playing); break;
    case 'deselect': target.clearSelection(); break;
    case 'chat': opts.toggleChat(); break;
    case 'close-popover': target.clearSelection(); break;
    default: break;
  }
}
const FIELD_ACTIONS = ['shooter','note','regular','box-label','new-box-label'];
function onClick(event) {
  if (!root || !root.contains(event.target)) return;
  const sheetTab = event.target.closest('[data-sheet-tab]');
  if (sheetTab) { sheet = sheetTab.dataset.sheetTab; render(); return; }
  const node = event.target.closest('[data-vs-action]');
  if (!node || FIELD_ACTIONS.includes(node.dataset.vsAction)) return;
  event.preventDefault();
  act(node.dataset.vsAction, node.dataset.vsValue, node);
}
function onChange(event) {
  if (!root || !root.contains(event.target)) return;
  const node = event.target.closest('[data-vs-action]');
  if (node && (FIELD_ACTIONS.includes(node.dataset.vsAction) || node.dataset.vsAction === 'live-detector' || node.dataset.vsAction === 'detector')) { act(node.dataset.vsAction, node.value, node); return; }
  if (event.target.id === 'vs-window') { engine().setWindow(event.target.value); return; }
  if (event.target.id === 'vs-frame-index') { if (!engine().seek(Number(event.target.value))) render(); return; }
  if (event.target.id === 'vs-scrub') { if (!engine().seek(Number(event.target.value))) render(); return; }
}
function attach(options) {
  opts = options; root = options.mount;
  sig = {}; // the shell rebuilds #main on every render: never trust cached regions
  root.addEventListener('click', onClick);
  root.addEventListener('change', onChange);
  const unsubscribe = engine()?.subscribe ? engine().subscribe(render) : null;
  render();
  return {render, detach() { if (unsubscribe) unsubscribe(); root.removeEventListener('click', onClick); root.removeEventListener('change', onChange); }};
}
window.VisionStage = {attach, render, act, factsLine, identityHTML, chipsHTML};
})();
