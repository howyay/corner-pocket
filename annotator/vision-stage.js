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
    freshness:'Freshness', saved:'Saved channels', savedOk:'Saved', addChannel:'Save Twitch channel', channelUrl:'Twitch source URL',
    select:'Select', remove:'Remove', chat:'Chat', showChat:'Show chat', hideChat:'Hide chat',
    startFailed:'Start attempt', cause:'Cause', remedy:'Remedy', retry:'Retry',
    remedyText:'Check that the source is a saved canonical Twitch channel, or that the allowlisted dataset media exists.',
    correct:'Correct', wrong:'Wrong', unsure:'Unsure', saveReview:'Save review', nextCue:'Next candidate →',
    notReviewed:'Not reviewed', reviewed:'Reviewed', unlabeled:'Unlabeled',
    unknown:'Unknown', cue:'Cue', clear:'Clear label', prevCrop:'← Previous crop', nextCrop:'Next crop →',
    ignore:'Ignore', rebuild:'Rebuild assignments', refresh:'Refresh status',
    seedHint:'Seeds save immediately. Saving a seed alone does not rebuild predictions.',
    saveAnchors:'Save six anchors', anchorsAt:'Load anchors at', anchorNote:'Anchors belong to the raw source frame; saving stores anchor annotations only, it never fits a calibration.',
    boxLabel:'Box label', deleteBox:'Delete selected', saveCorrections:'Save corrections for this frame',
    layerNote:'MODEL boxes are this session\u2019s reference only: saving a correction writes your boxes (YOURS), never the model\u2019s.',
    modelBoxes:'model boxes', yourBoxes:'your boxes',
    runInference:'Run inference on frozen frame', addPolygon:'Add table polygon', clearPolygon:'Clear polygon',
    newBoxLabel:'New box label', tool:'Tool', selectTool:'Select / move', drawTool:'Draw box',
    frameReadout:'frame', overlays:'overlays', loading:'LOADING', none:'none', on:'ON',
    live:'live', stale:'STALE', age:'frame age', receive:'receive-to-result', dropped:'dropped',
    selectCueHint:'Selecting a cue plays its window on the stage and loops in it; freeze to inspect one frame.',
    noCrops:'No crops in this queue.', noTracks:'No track windows are available for this VOD.',
    noEvents:'No event candidates in this filter.', vodOnlyAnchors:'Anchors are available for the vod30 dataset only.',
    keys:'SPACE play · ←/→ step · 0–9/U/C label · A/B identity · V verdict · ⏎ save',
    cropAtFrame:'crop at this frame', selectedBall:'Ball', trackWord:'Track', box:'Box', anchorWord:'Anchor',
    seedA:'Player A', seedB:'Player B',
    // Identity labelling: one regular (the identity pipeline), or a guest name
    // (this track's label). The legacy A/B/ignore values stay readable.
    whichRegular:'Which regular?', guestOption:'— not a regular (guest) —', guestName:'Guest name',
    guestPlaceholder:'Type the guest’s name', saveBinding:'Save', clearBinding:'Clear',
    notAPlayer:'Ignore (not a player)',
    ignoreHint:'Marks this track as a spectator: excluded from identity assignment, and never competing with the two labelling options above.',
    railEmpty:'Select a cue, a ball, a person or an anchor to label it.', thisFrame:'This frame', noSelection:'Nothing selected',
    bindNone:'no label yet', bindLegacy:'legacy A/B seed', bindGuest:'guest name',
    // Live detectors: the trained tiny ball net is a live *stage*, unlike the
    // CPU-heavy SAM3 frame detector, and the panel names the difference.
    liveBall:'Ball (trained net)',
    liveBallNote:'The live ball detector is the trained tiny net (the pipeline\u2019s "ball" stage; its weights are checked before the start). The Balls row under Frame detectors is the CPU-heavy SAM3 scan: a frame tool here, never a live stage.',
    stageEvery:'every', stageAbsent:'not run on the skipped frames', stageRuns:'runs',
    // Twitch VOD replay: a source, never a broadcast. The panel prints the
    // server's and the capture's own words (kind, live, rate, drift), not ours.
    vodReplay:'Twitch VOD replay', vodId:'VOD id or URL', vodStart:'Start at (s)', vodRate:'Rate (VOD s per wall s)',
    vodUse:'Use this VOD', vodChosen:'Chosen', vodNotLive:'a replay, never a live broadcast',
    vodNote:'The server resolves the VOD with Twitch and replays it in real time. The panel reports what the server and the capture say it is: kind, live, the VOD id, the rate and the drift it is carrying.',
    vodResolving:'resolving the VOD with Twitch…', vodFailed:'the VOD could not be resolved',
    vodDrift:'drift', vodVideoAt:'video at', vodWall:'wall', liveFlag:'live', pace:'pacing',
    enrolTitle:'Enrol as regular',
    enrolStart:'Enrol as regular', enrolHint:'Reads this person from the footage first; nothing is written until you confirm a name. A window scan can take about a minute.',
    enrolScanning:'collecting faces', enrolWait:'the scan reads the recording around this frame; it stops by itself and reports what it saw',
    enrolNeedsBox:'pick the person on the stage first: enrolment starts from their box in this frame',
    enrolCrops:'crops', enrolFrame:'frame', enrolDet:'det', enrolEye:'eye', enrolFramesSeen:'frames seen',
    enrolFaces:'usable faces', enrolPurity:'purity', enrolNoPurity:'no other face to cross-check',
    enrolIoU:'selection IoU', enrolEvidence:'evidence', enrolClusterFace:'stored cluster face',
    enrolWindowScan:'window scan', enrolCrossChecked:'cross-checked', enrolNotCrossChecked:'not cross-checked',
    enrolName:'Regular\u2019s name', enrolConfirm:'Confirm enrolment', enrolCancel:'Cancel',
    enrolRefused:'Enrolment refused', enrolNoCrops:'no usable crop was kept: nothing to enrol from',
    enrolWrote:'enrolled; the roster was re-read', enrolRetry:'Preview again',
    enrolMismatch:'these crops are not the ones you were shown; preview again',
    inferenceNotStored:'run on this frame, not stored', inferenceFrom:'inference source',
    // Live detectors: the trained tiny ball net is a live stage, unlike the
    // CPU-heavy SAM3 frame detector, and the panel names the difference.
    boundManual:'manual bind', boundAuto:'automatic face match', boundIdentity:'identity binding',
    bindIdentityHint:'Saves through the identity pipeline, so face and body matching keep working.',
    bindGuestHint:'Saves the typed name as this track’s label.',
    closePanel:'Close',
    noCluster:'No identity cluster on this track yet — pick a person box on the stage that has one.',
    loading2:'loading…', reviewedCount:'reviewed', inQueue:'in queue', crops:'crops', reviewedWord:'reviewed',
    prediction:'prediction', seed:'saved seed', liveState:'Live state', manual:'manual', detectorReason:'The balls detector (SAM3) is CPU-heavy and stays an explicit opt-in.',
    attemptSource:'Attempted source', frameCount:'frames', keyMap:'Key map', showCues:'Cues', showInspector:'Inspector',
    notGlass:'receive-to-result is local processing latency, not glass-to-glass',
    stageEmpty:'Pick a moment on the strip, or select a cue, then freeze it here.', noCropHere:'no crop at this frame',
    liveNow:'live', staleNow:'STALE',
    coldStartHint:'Nothing selected: draw a box on the frame, add the table polygon, or run inference on this frozen frame.',
    quadOff:'model quad off saved corners', quadUnverified:'model quad unverified',
    quadRefused:'quad refused', quadFallback:'quad from the naive fallback', storedInference:'stored inference',
    quadDrift:'quad drift vs saved corners',
    pocketsHeldRejected:'quad rejected', pocketsHeldUnverified:'unverified',
    correctionRefused:'saved correction refused', tolerance:'tol',
    playInStage:'▶ Play in stage', geometry:'Detected geometry', colour:'Colour',
    ballLast:'Ball last seen', pocketAt:'Pocket at', shotFrom:'From', shotTo:'To',
    displacement:'Displacement', speed:'Speed', scanWindow:'Scan window',
    projectedFrom:'Projected from', pocket:'Pocket',
    evidenceNote:'The clip plays in the stage with its overlay; per-frame detections come back when you freeze.',
    projectedNote:'Projected from the dataset calibration, in frame pixels.',
    notProjectable:'Not projectable: this dataset has no usable calibration for this event, so only the scan millimetres exist.',
    gateCheck:'Detection gate', gateConfirmed:'confirmed', gateRejected:'rejected', gateUnconfirmed:'unconfirmed',
    gateCensus:'Ball census', gateColourCensus:'Claimed colour census', gateVanish:'Vanished ball',
    gateMove:'Re-measured move', gateMotion:'motion', gateGap:'Claim vs measured ball',
    gateDup:'Duplicate detections merged', gateNotes:'Gate notes',
    tierLabel:'Confirmation tier', tierGeometry:'geometry-verified', tierWindow:'motion window only',
    tierGeometryHint:'The re-measured motion matches the claim: this ball, this start, this end.',
    tierWindowHint:'A ball really moved in this window, but not the one or where the claim said. Review it as a moment, not as the claimed shot.',
    noPotsMeasured:'No pot candidate in this VOD survived measurement: the ball census refuted every claim (a ball said to be potted was still on the cloth) and 2 stayed unconfirmed, so this list is empty on purpose.',
    noShotsMeasured:'No shot candidate survived measurement: every served event is explained by occlusion — a person crossing the cloth at that moment — and at 720p one ball\'s best possible signal sits on the detection floor (motion measured over the whole VOD: 0 of 55 ball-scale onsets could be a single ball). The events stay in the report artifacts, not in the queue.',
    loopWord:'loop', playingWord:'playing', pausedWord:'paused'
  },
  zh: {
    cues:'线索', inspector:'检查器', sources:'视频源', events:'事件', balls:'球', persons:'人物',
    anchors:'锚点', cloth:'台呢', pockets:'袋口', verdict:'判定', shooter:'击球者', notes:'备注',
    all:'全部', shots:'击球', pots:'入袋', pending:'未复核', labels:'球号标注', queue:'裁剪图队列',
    tracks:'人物轨迹', identity:'身份', calibration:'标定', frameIndex:'帧', step:'步进',
    freeze:'冻结', play:'播放', pause:'暂停', ticks:'事件刻度', dataset:'数据集',
    start:'开始', stop:'停止', detectors:'帧检测器', table:'球桌', person:'人物', ball:'球',
    latency:'Twitch 上游延迟：未知。接收到结果仅为本地处理耗时，不是端到端延迟。',
    freshness:'新鲜度', saved:'已保存频道', savedOk:'已保存', addChannel:'保存 Twitch 频道', channelUrl:'Twitch 来源地址',
    select:'选择', remove:'移除', chat:'聊天', showChat:'显示聊天', hideChat:'隐藏聊天',
    startFailed:'启动尝试', cause:'原因', remedy:'处理', retry:'重试',
    remedyText:'请确认来源是已保存的标准 Twitch 频道，或数据集媒体确实存在。',
    correct:'正确', wrong:'错误', unsure:'不确定', saveReview:'保存复核', nextCue:'下一个候选 →',
    notReviewed:'未复核', reviewed:'已复核', unlabeled:'未标注',
    unknown:'未知', cue:'母球', clear:'清除标注', prevCrop:'← 上一张裁剪图', nextCrop:'下一张裁剪图 →',
    ignore:'忽略', rebuild:'重建分配', refresh:'刷新状态',
    seedHint:'种子立即保存。仅保存种子不会重建预测。',
    saveAnchors:'保存六个锚点', anchorsAt:'加载锚点时刻', anchorNote:'锚点属于原始源帧；保存仅存储锚点标注，不会拟合标定。',
    boxLabel:'标注框标签', deleteBox:'删除所选', saveCorrections:'保存此帧修正',
    layerNote:'模型框（MODEL）仅为本次会话的参照：保存修正只写入你的框（人工），不会写入模型框。',
    modelBoxes:'模型框', yourBoxes:'你的框',
    runInference:'对冻结帧运行推理', addPolygon:'添加球桌多边形', clearPolygon:'清除多边形',
    newBoxLabel:'新框标注', tool:'工具', selectTool:'选择 / 移动', drawTool:'绘制标注框',
    frameReadout:'帧', overlays:'叠加层', loading:'加载中', none:'无', on:'开',
    live:'直播', stale:'已过期', age:'帧龄', receive:'接收到结果', dropped:'丢帧',
    selectCueHint:'选择线索会在舞台上播放其片段并循环；冻结后可检查单帧。',
    noCrops:'此队列没有裁剪图。', noTracks:'此录像没有可用的轨迹窗口。',
    noEvents:'此筛选下没有事件候选。', vodOnlyAnchors:'锚点仅适用于 vod30 数据集。',
    keys:'空格 播放 · ←/→ 步进 · 0–9/U/C 标注 · A/B 身份 · V 判定 · ⏎ 保存',
    cropAtFrame:'此帧的裁剪图', selectedBall:'球', trackWord:'轨迹', box:'标注框', anchorWord:'锚点',
    seedA:'选手 A', seedB:'选手 B',
    whichRegular:'选择常客', guestOption:'— 不是常客（访客）—', guestName:'访客姓名',
    guestPlaceholder:'输入访客姓名', saveBinding:'保存', clearBinding:'清除',
    notAPlayer:'忽略（不是球员）',
    ignoreHint:'将该轨迹标记为观众：排除在身份分配之外，也不会与上方两个标注选项争夺注意力。',
    railEmpty:'请先选择线索、球、人物或锚点，再进行标注。', thisFrame:'此帧', noSelection:'未选择',
    bindNone:'尚未标注', bindLegacy:'旧版 A/B 种子', bindGuest:'访客姓名',
    liveBall:'球（训练网络）',
    liveBallNote:'实时球检测使用训练好的小型网络（流水线的 ball 阶段，启动前校验权重）。帧检测器里的「球」是 CPU 密集的 SAM3 扫描：它属于帧工具，从不作为实时阶段运行。',
    stageEvery:'每', stageAbsent:'跳过的帧上不运行', stageRuns:'次运行',
    vodReplay:'Twitch 回放', vodId:'回放 id 或网址', vodStart:'起始秒', vodRate:'倍速（回放秒/墙钟秒）',
    vodUse:'使用该回放', vodChosen:'已选择', vodNotLive:'回放，绝不是直播',
    vodNote:'由服务端向 Twitch 解析该回放并实时播放。面板只报服务端与采集器的原话：类型、是否直播、回放 id、倍速以及当前漂移。',
    vodResolving:'正在向 Twitch 解析该回放…', vodFailed:'该回放无法解析',
    vodDrift:'漂移', vodVideoAt:'视频位置', vodWall:'墙钟', liveFlag:'直播', pace:'节拍',
    enrolTitle:'登记为常客',
    enrolStart:'登记为常客', enrolHint:'先从录像中读取该人物；在你确认姓名之前不会写入任何内容。窗口扫描约需一分钟。',
    enrolScanning:'正在采集人脸', enrolWait:'扫描正在读取此帧附近的录像；它会自行结束并报告所见',
    enrolNeedsBox:'请先在舞台上选择该人物：登记从他/她在此帧的标注框开始',
    enrolCrops:'张裁剪图', enrolFrame:'帧', enrolDet:'检测', enrolEye:'眼距', enrolFramesSeen:'可见帧数',
    enrolFaces:'可用人脸', enrolPurity:'纯度', enrolNoPurity:'没有其他人脸可交叉核对',
    enrolIoU:'选择重叠度', enrolEvidence:'证据', enrolClusterFace:'已存聚类人脸',
    enrolWindowScan:'窗口扫描', enrolCrossChecked:'已交叉核对', enrolNotCrossChecked:'未交叉核对',
    enrolName:'常客姓名', enrolConfirm:'确认登记', enrolCancel:'取消',
    enrolRefused:'登记被拒绝', enrolNoCrops:'没有保留可用裁剪图：无从登记',
    enrolWrote:'已登记；名单已重新读取', enrolRetry:'重新预览',
    enrolMismatch:'这些裁剪图与展示时不一致；请重新预览',
    inferenceNotStored:'本次运行，未存储', inferenceFrom:'推理来源',
    boundManual:'人工绑定', boundAuto:'自动人脸匹配', boundIdentity:'身份绑定',
    bindIdentityHint:'通过身份流程保存，人脸与体型匹配继续生效。',
    bindGuestHint:'把输入的姓名保存为该轨迹的标注。',
    closePanel:'关闭',
    noCluster:'此轨迹尚无身份聚类——请在舞台上选择带有聚类的球员框。',
    loading2:'读取中…', reviewedCount:'已复核', inQueue:'队列中', crops:'张裁剪图', reviewedWord:'已复核',
    prediction:'预测', seed:'已保存种子', liveState:'直播状态', manual:'人工', detectorReason:'球检测器（SAM3）为 CPU 密集，需显式开启。',
    attemptSource:'尝试的来源', frameCount:'帧数', keyMap:'按键', showCues:'线索', showInspector:'检查器',
    notGlass:'接收到结果为本地处理耗时，并非端到端延迟',
    stageEmpty:'在拖动条上选择时刻，或选择一条线索，然后在此冻结。', noCropHere:'此帧没有裁剪图',
    liveNow:'直播', staleNow:'已过期',
    coldStartHint:'未选择对象：可直接在帧上绘制标注框、添加球桌多边形，或对本冻结帧运行推理。',
    quadOff:'模型四边形偏离已保存角点', quadUnverified:'模型四边形未校验',
    quadRefused:'四边形已拒绝', quadFallback:'四边形来自朴素回退', storedInference:'已存推理',
    quadDrift:'四边形相对已保存角点漂移',
    pocketsHeldRejected:'四边形被拒绝', pocketsHeldUnverified:'未校验',
    correctionRefused:'已保存修正被拒绝', tolerance:'容差',
    playInStage:'▶ 在舞台播放', geometry:'检测几何', colour:'颜色',
    ballLast:'球最后位置', pocketAt:'袋口位置', shotFrom:'起点', shotTo:'终点',
    displacement:'位移', speed:'速度', scanWindow:'扫描窗口',
    projectedFrom:'投影来源', pocket:'袋口',
    evidenceNote:'片段在舞台上带叠加层播放；逐帧检测需冻结后恢复。',
    projectedNote:'由数据集标定投影到帧像素。',
    notProjectable:'无法投影：该数据集对此事件没有可用标定，仅有扫描毫米值。',
    gateCheck:'检测门', gateConfirmed:'已确证', gateRejected:'已否决', gateUnconfirmed:'未确证',
    gateCensus:'球数', gateColourCensus:'声称颜色球数', gateVanish:'消失球',
    gateMove:'复测位移', gateMotion:'运动量', gateGap:'声称位置与实测球',
    gateDup:'合并的重复检测', gateNotes:'检测门备注',
    tierLabel:'确认层级', tierGeometry:'几何已核', tierWindow:'仅运动窗口',
    tierGeometryHint:'复测位移与声称一致：同这颗球、同起点、同终点。',
    tierWindowHint:'该窗口确有球在动，但不是声称的那颗，或不在声称的位置。请按「时刻」复核，而不是按声称的那次击球。',
    noPotsMeasured:'本场没有经测量存活的入袋候选：球数普查推翻了每一条断言（声称入袋的球仍在台面上），另有 2 条未确认，因此列表为空是刻意的。',
    noShotsMeasured:'没有击球候选通过测量：已服务的每条事件都被遮挡解释——那一刻有人穿过台面——且 720p 下单球的最强信号正好卡在检测底噪上（全片实测：55 个球尺度突变中 0 个可能来自单颗球）。这些事件保留在报告产物里，不在队列中。',
    loopWord:'循环', playingWord:'播放中', pausedWord:'已暂停'
  }
};
let opts = null, root = null, sig = {}, sheet = 'cues', ageTimer = null, footerObserver = null;
// The source panel's open state and the half-typed guest name are adapter state,
// not engine state: the engine owns no frame or source selection ambiguity.
let sourceOpen = false, guestDraft = null;
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
// The engine stores notices and statuses as English source text; the adapter
// localizes them at render time, so a language switch re-labels what is already
// on screen (the inspector signature includes the language).
const engineText = value => engine()?.text ? engine().text(String(value ?? '')) : String(value ?? '');
// The detector reports machine codes (low_cloth_area, no_boundary_evidence, ...);
// the operator reads a phrase. Same idea as labelText: the code never reaches the
// UI, and the default still translates instead of printing snake_case.
const QUAD_REASON = {
  low_cloth_area: ['the cloth is hidden - a player or an object is over the bed', '台面被遮挡——有人或物体挡在台面上'],
  no_boundary_evidence: ['no rail edge is visible inside the search band', '搜索带内看不到库边边缘'],
  boundary_outside_band: ['the rail edge sits outside the search band', '库边边缘超出搜索带'],
  prior_disagreement: ['the four sides disagree with the saved centre', '四条边与已保存中心不一致'],
  invalid_geometry: ['the four corners are not a valid table quad', '四个角点不构成有效球桌四边形'],
  no_prior: ['no saved geometry exists for this dataset', '该数据集没有已保存几何'],
  no_cloth_area: ['no cloth was found in this frame', '此帧没有找到台呢']
};
function quadReason(code) {
  const raw = String(code || 'unknown');
  const row = QUAD_REASON[raw];
  if (row) return opts?.lang === 'zh' ? row[1] : row[0];
  const words = raw.replace(/_/g, ' ');
  return opts?.lang === 'zh' ? `检测器报告「${words}」` : `the detector reported "${words}"`;
}
function quadSideNote(quad) {
  const verified = Number(quad?.verified_sides);
  if (!Number.isFinite(verified) || verified >= 4) return '';
  const sides = (quad?.sides || []).filter(side => side.state !== 'verified')
    .map(side => Number(side.side) + 1).join(', ');
  const count = 4 - verified;
  return opts?.lang === 'zh' ? ` · 未校验边 ${count}/4${sides ? `：${sides}` : ''}` : ` · ${count}/4 sides unverified${sides ? `: ${sides}` : ''}`;
}
function quadDetail(s) {
  const quad = s?.cloth?.quad;
  if (!quad) return '';
  const head = opts?.lang === 'zh'
    ? `四边形：${quad.state || '?'}（种子 ${quad.seed_file || '无'}）`
    : `quad: ${quad.state || '?'} (seed ${quad.seed_file || 'none'})`;
  const reason = quad.reason ? (opts?.lang === 'zh' ? `，原因 ${quadReason(quad.reason)}` : `, reason: ${quadReason(quad.reason)}`) : '';
  const sides = (quad.sides || []).map(side => `${Number(side.side) + 1}:${side.state}${side.reason ? `(${quadReason(side.reason)})` : ''}`).join(', ');
  return `${head}${reason}${sides ? (opts?.lang === 'zh' ? `，各边 ${sides}` : `, sides ${sides}`) : ''}`;
}
function labelText(label) { if (label === 'u' || label === -1) return t('unknown'); if (label === 0) return `${t('cue')} · 0`; return `#${label}`; }
// A saved seed is either one of the three legacy role values the identity
// pipeline still reads (A / B / ignore) or a guest name the operator typed.
// Both live in the same seeds store under the same key, so the reader must tell
// them apart by the role words alone - never by "looks like a name".
const SEED_ROLE_KEYS = {A:'seedA', B:'seedB', ignore:'ignore'};
function isSeedRole(value) { return value != null && Object.prototype.hasOwnProperty.call(SEED_ROLE_KEYS, String(value)); }
function seedText(value) { return value == null || value === '' ? '' : isSeedRole(value) ? t(SEED_ROLE_KEYS[String(value)]) : String(value); }
// What this person track is labelled with right now, and where the label came
// from. A track can carry two independent things at once: a saved seeds label
// (a legacy A/B/ignore value, or a guest name) and an identity binding on its
// cluster (the operator's explicit pick, or an automatic face/body match).
// Everything reported here exists in the state; nothing is inferred.
function bindingFacts(s) {
  const track = (s?.persons?.tracks || []).find(x => String(x.id) === String(s.persons.track)) || null;
  const person = s?.selection?.person || {};
  const seed = track?.seed ?? null;
  const playerId = person.player_id ?? null;
  const roster = (opts?.regulars ? opts.regulars() : null) || [];
  const bound = playerId ? roster.find(row => String(row.id) === String(playerId)) || null : null;
  const evidence = person.bound_evidence || null;
  return {
    track, seed, playerId, bound, evidence,
    cluster: person.cluster_id ?? null,
    legacy: isSeedRole(seed),
    guest: seed != null && !isSeedRole(seed),
    label: seed == null ? null : {text: seedText(seed), raw: String(seed)},
    identity: playerId ? {
      id: String(playerId),
      name: bound ? bound.name : String(playerId),
      // A face/body match is never the operator's pick: the evidence says which.
      source: evidence?.source === 'bind_face' ? 'boundAuto' : evidence?.source === 'explicit_assign' ? 'boundManual' : 'boundIdentity'
    } : null,
    kind: playerId ? 'regular' : seed == null ? 'none' : isSeedRole(seed) ? `legacy-${seed}` : 'guest'
  };
}
// The honest one-liner: what this track is bound to, and by which path. Both
// halves are shown when both exist, so a stale legacy seed can never hide an
// identity binding (or the other way round).
function bindingLine(s) {
  const facts = bindingFacts(s);
  const parts = [`${t('trackWord')} ${s.persons.track ?? '—'}`];
  const prediction = s.persons.predictions && !s.persons.predictions.stale ? (s.persons.predictions.map || {})[`${s.persons.track}:${s.persons.win}`] : null;
  if (prediction) parts.push(`${t('prediction')} ${prediction}`);
  if (facts.label) parts.push(`${facts.label.text} · ${t(facts.legacy ? 'bindLegacy' : 'bindGuest')}`);
  else parts.push(t('bindNone'));
  if (facts.identity) parts.push(`${facts.identity.name} · ${t(facts.identity.source)}`);
  return `<p class="vs-mono" data-vs-binding="${esc(facts.kind)}">${parts.map(esc).join(' · ')}</p>`;
}
// Pocket names are pool-table rail terms in stored data; every displayed label
// is the position word the engine maps them to, never the raw key.
function pocketName(event) { return event?.nearest_pocket_text || event?.nearest_pocket || ''; }
function pocketTag(event) { const name = pocketName(event); return name ? `<span class="vs-mono vs-dim">${esc(name)}</span>` : ''; }
// What the scan actually measured for this cue, and whether the server could
// project it into frame pixels. An event the dataset cannot project says so:
// there is no second, browser-side guess at where the ball was.
function pxText(point) {
  return Array.isArray(point) && point.length === 2 && point.every(Number.isFinite) ? `${Math.round(point[0])}, ${Math.round(point[1])}` : '';
}
// The two or three numbers that decided this cue, so a human verdict takes
// seconds: the ball census before -> after, the vanished ball's distance to its
// pocket, the re-measured move. Empty when the cue carries no gate block.
function gateEvidence(event) {
  const n = event?.gate?.numbers;
  if (!n) return [];
  const out = [];
  if (event.type === 'pot') {
    if (Number.isFinite(n.census_pre) && Number.isFinite(n.census_post)) out.push(`${n.census_pre}→${n.census_post}`);
    if (Number.isFinite(n.vanish_dist_mm)) out.push(`${Math.round(n.vanish_dist_mm)} mm ${n.vanish_pocket || ''}`.trim());
  } else if (Number.isFinite(n.disp_mm)) {
    out.push(`${Math.round(n.disp_mm)} mm${n.disp_color ? ` ${n.disp_color}` : ''}`);
  }
  if (Number.isFinite(n.window_motion)) out.push(`${t('gateMotion')} ${n.window_motion}`);
  if ((event.dup_count || 1) > 1) out.push(`×${event.dup_count}`);
  return out;
}
function gateStatusWord(status) {
  return t(status === 'confirmed' ? 'gateConfirmed' : status === 'rejected' ? 'gateRejected' : 'gateUnconfirmed');
}
function eventGeometry(item) {
  const rows = [];
  const row = (key, value) => { if (value) rows.push(`<li class="vs-mono"><span class="vs-dim">${esc(t(key))}</span> ${esc(value)}</li>`); };
  row('colour', item.color || '');
  if (item.type === 'pot') {
    row('ballLast', `${pxText(item.last_px)} px`);
    row('pocket', item.pocket_name || pocketName(item));
    row('pocketAt', `${pxText(item.pocket_px)} px`);
  } else {
    row('shotFrom', `${pxText(item.from_px)} px`);
    row('shotTo', `${pxText(item.to_px)} px`);
    row('displacement', item.disp_mm != null ? `${Math.round(item.disp_mm)} mm` : '');
    row('speed', item.speed_mm_s != null ? `${Math.round(item.speed_mm_s)} mm/s` : '');
  }
  row('scanWindow', Array.isArray(item.window_s) ? `${timecode(item.window_s[0])} → ${timecode(item.window_s[1])}` : '');
  if (item.projectable) row('projectedFrom', item.px_source || '');
  const gate = item.gate;
  if (gate) {
    const n = gate.numbers || {};
    row('gateCheck', `${gateStatusWord(gate.status)}${gate.gate ? ` · ${gate.gate}` : ''}`);
    if (item.tier === 'geometry' || item.tier === 'window') row('tierLabel', t(item.tier === 'geometry' ? 'tierGeometry' : 'tierWindow'));
    if (item.type === 'pot') {
      row('gateCensus', Number.isFinite(n.census_pre) && Number.isFinite(n.census_post) ? `${n.census_pre} → ${n.census_post}` : '');
      row('gateColourCensus', Number.isFinite(n.color_census_pre) && Number.isFinite(n.color_census_post) ? `${n.color_census_pre} → ${n.color_census_post}` : '');
      row('gateVanish', Number.isFinite(n.vanish_dist_mm)
        ? `${Math.round(n.vanish_dist_mm)} mm${n.vanish_pocket ? ` · ${n.vanish_pocket}` : ''}${Number.isFinite(n.approach_mm) ? ` · ${Math.round(n.approach_mm)} mm` : ''}` : '');
    } else {
      row('gateMove', Number.isFinite(n.disp_mm) ? `${Math.round(n.disp_mm)} mm${n.disp_color ? ` · ${n.disp_color}` : ''}` : '');
      row('gateGap', Number.isFinite(n.geometry_gap_px) ? `${Math.round(n.geometry_gap_px)} px` : '');
    }
    row('gateMotion', Number.isFinite(n.window_motion) ? String(n.window_motion) : '');
    row('gateDup', (item.dup_count || 1) > 1 ? String(item.dup_count) : '');
    row('gateNotes', (gate.reasons || []).join(' · '));
  }
  const body = rows.length ? `<ul class="vs-facts">${rows.join('')}</ul>` : '';
  return `${body}<p class="vs-note">${esc(item.projectable ? t('projectedNote') : t('notProjectable'))}</p>`;
}
function receiptLine(kind) {
  const row = (snap()?.receipts || []).find(r => r.key === kind);
  if (!row) return '';
  if (!row.at) return `<p class="vs-receipt pending">· ${esc(engineText(row.text))}</p>`;
  const age = Math.max(0, (Date.now() - row.at) / 1000);
  return `<p class="vs-receipt${row.error ? ' error' : ''}" data-receipt-at="${row.at}">${row.error ? '!' : '✓'} ${esc(engineText(row.text))} · ${age.toFixed(1)} s ${esc(t('savedOk'))}</p>`;
}
// The footer's height is measured, never assumed: the scroll region reserves
// exactly that much (CSS var --vs-footer-h) so no row hides under it.
function syncFooterHeight() {
  const inspector = $('#vs-inspector'), footer = $('#vs-inspector-actions');
  if (!inspector || !footer) return;
  const height = `${footer.offsetHeight}px`;
  if (inspector.style.getPropertyValue('--vs-footer-h') !== height) inspector.style.setProperty('--vs-footer-h', height);
}
function receiptAge() {
  if (!root) return;
  const now = Date.now(), saved = t('savedOk');
  root.querySelectorAll('[data-receipt-at]').forEach(node => {
    node.textContent = node.textContent.replace(/[\d.]+ s (?:已保存|Saved)$/, `${Math.max(0, (now - Number(node.dataset.receiptAt)) / 1000).toFixed(1)} s ${saved}`);
  });
}
// ---- regions -------------------------------------------------------------
// The strip shows where the stage's video is playing: the loop window of the
// selected cue, the cue's own time inside it, and how many loops have run. It is
// the same window the stage loops in (the cue's t ± CLIP_BEFORE/CLIP_AFTER), so
// the band and the picture can never describe two different moments.
function windowBandHTML(s) {
  const playback = s.playback || {};
  const duration = Number(s.frame.duration) || 0;
  if (!playback.on || !duration) return '';
  const clamp = value => Math.max(0, Math.min(100, value));
  const left = clamp((Number(playback.from) || 0) / duration * 100);
  const right = clamp((Number(playback.to) || 0) / duration * 100);
  const at = playback.event == null ? null : (s.events.items || []).find(e => String(e.id) === String(playback.event));
  const mark = at ? clamp(Number(at.t) / duration * 100) : null;
  return `<span class="scrub-window" style="left:${left}%;width:${Math.max(0.4, right - left)}%"></span>`
    + (mark == null ? '' : `<span class="scrub-cue" style="left:${mark}%" title="${esc(timecode(at.t))}"></span>`)
    + `<span class="scrub-loop" data-playing="${playback.playing ? '1' : '0'}">↻ ${esc(playback.loops || 0)} · ${esc(playback.playing ? t('playingWord') : t('pausedWord'))}</span>`;
}
function chipsHTML(s) {
  const channels = (opts.channels() || []).map(c => `<button class="vs-chip${s.source.kind === 'live' && s.source.channel === c.channel ? ' active' : ''}" data-vs-action="pick-live" data-vs-value="twitch:${esc(c.id)}">${s.source.kind === 'live' && s.source.channel === c.channel ? '● ' : ''}${esc(t('live'))} · twitch ${esc(c.channel || '')}</button>`).join('');
  const datasets = (s.datasets || []).map(d => `<button class="vs-chip${s.source.kind === 'vod' && d.id === s.dataset ? ' active' : ''}" data-vs-action="pick-dataset" data-vs-value="${esc(d.id)}">${esc(d.label || d.id)}</button>`).join('');
  const freshness = s.source.kind === 'live'
    ? `<span class="vs-fresh${s.live.stale ? ' stale' : ''}">${s.live.stale ? esc(t('stale')) : esc(t('live'))} · ${esc(t('age'))} ${fmtAge(s.live.frame_age_ms)}</span>`
    : `<span class="vs-fresh">${esc(s.source.label)}</span>`;
  // The source settings hang off the chip row itself: one chip opens the panel
  // that used to be the rail's nothing-selected state, so the rail stays about
  // the selection and the settings are still one click away at any width.
  const chip = `<button class="vs-chip vs-source-chip${sourceOpen ? ' active' : ''}" data-vs-action="source-panel" aria-expanded="${sourceOpen ? 'true' : 'false'}" aria-controls="vs-source-panel" aria-label="${esc(t('sources'))}">${esc(t('sources'))}</button>`;
  const panel = sourceOpen ? `<div class="vs-source-panel" id="vs-source-panel" role="group" aria-label="${esc(t('sources'))}">
    <div class="vs-source-head"><strong>${esc(t('sources'))}</strong><button class="vs-source-close" data-vs-action="source-panel" aria-label="${esc(t('closePanel'))}">×</button></div>
    ${sourcePanelHTML(s)}</div>` : '';
  return `<div class="vs-chiprow" role="group" aria-label="${esc(t('dataset'))}">${chip}${datasets}${channels}</div>
  <div class="vs-chipmeta">${freshness}<span class="vs-keys">${esc(t('keys'))}</span></div>${panel}`;
}
function tierBadge(event) {
  // The confirmation tier, on the card and in the inspector: geometry-verified
  // means the re-measured motion matches the claim, motion-window means a ball
  // moved but not the one or where the claim said.  Shown only when the gate
  // recorded a tier, so an unlabelled event never reads as verified.
  const tier = event?.tier === 'geometry' ? 'geometry' : event?.tier === 'window' ? 'window' : null;
  if (!tier) return '';
  const key = tier === 'geometry' ? 'tierGeometry' : 'tierWindow';
  const hint = tier === 'geometry' ? 'tierGeometryHint' : 'tierWindowHint';
  return `<span class="vs-badge tier-${tier}" data-vs-tier="${tier}" title="${esc(t(hint))}">${esc(t(key))}</span>`;
}
function emptyReasonKey(filter) {
  // Every empty filter says why it is empty. An empty queue is a measured
  // result, not a bug: the served events were measured away (a person crossing
  // the cloth at the claimed moment, and at 720p one ball's best possible signal
  // sits on the detection floor), and no pot candidate survived the census.
  return filter === 'pot' ? 'noPotsMeasured' : 'noShotsMeasured';
}
function emptyMarker(filter) {
  return filter === 'pot' ? 'pots-measured-none' : 'shots-measured-none';
}
function railHTML(s) {
  const events = s.events.items.filter(e => {
    if (s.eventFilter === 'all') return true;
    if (s.eventFilter === 'pending') return !e.verdict;
    if (s.eventFilter === 'geometry' || s.eventFilter === 'window') return e.tier === s.eventFilter;
    return e.type === s.eventFilter;
  });
  // Tier controls exist only while an event carries a tier: an empty queue must
  // not offer filters that can only ever return nothing.
  const tiered = s.events.items.some(e => e.tier === 'geometry' || e.tier === 'window');
  const filters = [['all', 'all'], ['shot', 'shots'], ['pot', 'pots'], ['pending', 'pending']];
  if (tiered) filters.splice(1, 0, ['geometry', 'tierGeometry'], ['window', 'tierWindow']);
  const cards = events.length ? events.map((e, i) => `<article class="vs-card tier-${esc(e.tier || 'none')}${e.id === s.selection.event?.id ? ' selected' : ''}" data-vs-action="select-event" data-vs-id="${esc(e.id)}">
      <div class="vs-card-row"><span class="vs-badge ${esc(e.type)}">${esc(e.type === 'pot' ? t('pots') : t('shots'))}</span>${tierBadge(e)}<span class="vs-mono">${esc(timecode(e.t))}</span><span class="vs-mono vs-dim">#${esc(e.id)}</span>${pocketTag(e)}</div>
      ${gateEvidence(e).length ? `<div class="vs-mono vs-dim fv-gate">${esc(gateEvidence(e).join(' · '))}</div>` : ''}
      <div class="vs-verbs">${['correct','wrong','unsure'].map(v => `<button class="${e.verdict === v ? 'active' : ''}" data-vs-action="verdict" data-vs-id="${esc(e.id)}" data-vs-value="${v}" title="${esc(t(v))}" aria-label="${esc(t(v))}">${{correct:'✓',wrong:'✗',unsure:'?'}[v]}</button>`).join('')}<span class="vs-verb-label">${esc(e.verdict ? t(e.verdict) : t('notReviewed'))}</span></div>
    </article>`).join('') : `<p class="vs-empty" data-vs-empty="${esc(emptyMarker(s.eventFilter))}">${esc(t(emptyReasonKey(s.eventFilter)))}</p>`;
  const crops = s.balls.items;
  const cropRows = crops.length ? crops.map(c => `<button class="vs-item${s.selection.crop && c.file === s.selection.crop.file ? ' selected' : ''}" data-vs-action="select-crop" data-vs-value="${esc(c.file)}"><span class="vs-mono">${esc(c.file)}</span><span class="vs-mono vs-dim">${esc(timecode(c.t))}</span><span class="vs-tag${c.label == null ? '' : ' done'}">${esc(c.label == null ? t('unlabeled') : labelText(c.label))}</span></button>`).join('') : `<p class="vs-empty">${esc(t('noCrops'))}</p>`;
  const tracks = s.persons.tracks.length ? s.persons.tracks.map(x => { const label = x.seed || x.label; return `<button class="vs-item${String(s.persons.track) === String(x.id) ? ' selected' : ''}" data-vs-action="select-track" data-vs-value="${esc(x.id)}"><span class="vs-mono">${esc(t('trackWord'))} ${esc(x.id)}</span><span class="vs-tag${label ? ' done' : ''}${label && !isSeedRole(label) ? ' guest' : ''}">${esc(seedText(label) || '?')}</span></button>`; }).join('') : `<p class="vs-empty">${esc(t('noTracks'))}</p>`;
  return `<section class="vs-group${s.focus === 'events' ? ' focused' : ''}"><header><h3>${esc(t('events'))}</h3><span class="vs-mono">${esc(s.events.reviewed)} ${esc(t('reviewedWord'))}</span></header>
    <div class="vs-filters">${filters.map(([v, l]) => `<button class="vs-filter${s.eventFilter === v ? ' active' : ''}" data-vs-action="event-filter" data-vs-value="${v}">${esc(t(l))}</button>`).join('')}</div>${cards}</section>
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
  if (sel.kind === 'person') {
    // The stagebar states the same binding the rail does, in one phrase.
    const facts = bindingFacts(s);
    const bound = facts.identity ? `${facts.identity.name} · ${t(facts.identity.source)}`
      : facts.label ? `${facts.label.text} · ${t(facts.legacy ? 'bindLegacy' : 'bindGuest')}` : t('bindNone');
    return `${esc(t('trackWord'))} ${esc(sel.track)} · ${esc(bound)}`;
  }
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
  // A layer that was held back says so here, in the same words as the stage
  // note: an empty layer is never left unexplained.
  const cloth = s.cloth || {};
  const verdict = cloth.verdict || {};
  const refusal = cloth.refusal || null;
  const quad = cloth.quad || null;
  const clothLabel = layer('cloth', t('cloth').toLowerCase())
    + (cloth.polygon === 'inference' ? ` (${t('storedInference')})` : '');
  parts.push(clothLabel, layer('balls', t('balls').toLowerCase()), layer('persons', t('persons').toLowerCase()));
  const pocketCount = Number(d.pockets || 0);
  const pocketSource = cloth.pockets?.source || null;
  const pocketsHeld = !pocketCount && verdict.state === 'off' ? t('pocketsHeldRejected') : !pocketCount && verdict.state === 'unverified' ? t('pocketsHeldUnverified') : '';
  // A drawn pocket marker names its own source: the checked model quad, or the
  // saved anchors / calibration it was projected from (engine-localized).
  const pocketNote = pocketsHeld || (pocketCount && pocketSource === 'calibration' ? engineText(cloth.pockets?.reference || '') : '');
  parts.push(`${t('pockets').toLowerCase()} ${pocketCount}${pocketNote ? ` (${pocketNote})` : ''}`);
  parts.push(t('anchors').toLowerCase() + ' ' + Number(d.anchors || 0), layer('events', t('events').toLowerCase()));
  if (verdict.state === 'off' && verdict.mean != null) parts.push(`${t('quadOff')} ${Math.round(verdict.mean)} px (${t('tolerance')} ${Math.round(verdict.tolerance)} px)`);
  else if (verdict.state === 'off') parts.push(t('quadOff'));
  else if (verdict.state === 'unverified') parts.push(t('quadUnverified'));
  // The detector searches around the saved hand anchors, so a pass is a drift
  // measurement, not a verdict on the table: report the number, not just "ok".
  else if (verdict.state === 'ok' && verdict.mean != null) parts.push(`${t('quadDrift')} ${verdict.mean.toFixed(1)} px (${t('tolerance')} ${Math.round(verdict.tolerance)} px)`);
  // Why there is no quad at all. The detector's codes stay machine-side; the
  // operator reads the phrase, plus how many sides were left unverified (the
  // per-side list is the tooltip on this line).
  if (quad?.reason && (verdict.state === 'none' || verdict.state === 'off')) {
    const sides = quadSideNote(quad);
    parts.push(`${t('quadRefused')} (${quadReason(quad.reason)}${sides})`);
  } else if (quad?.state === 'naive_fallback') {
    parts.push(`${t('quadFallback')} (${quadReason(quad.reason)})`);
  }
  if (refusal) parts.push(`${t('correctionRefused')} (${refusal.owner})`);
  // A stored inference file is an earlier run's evidence, and the line says so
  // rather than letting it read as this session's detection.
  if (s.corrections?.storedInference && s.corrections?.inferenceAt) parts.push(`${t('storedInference')} ${stampText(s.corrections.inferenceAt)}`);
  const total = d.cloth + d.balls + d.persons + d.pockets + d.anchors + d.events;
  if (s.loading.overlay) parts.push(`${t('overlays')} ${t('loading')} (${((Date.now() - s.loading.since) / 1000).toFixed(1)} s)`);
  else if (s.busy) parts.push(`${t('overlays')} ${t('loading2')}`);
  else parts.push(`${t('overlays')} ${total > 0 ? t('on') : t('none')}`);
  return parts.join(' · ');
}
// Nothing selected is still an annotatable frame. The correction controls used
// to live only inside the box block, which needs an existing box, so a cold
// frame (no saved correction, no saved inference) offered no way to draw a box,
// add the table polygon or run inference at all. Same actions, same write
// guards, reachable with an empty selection - under "This frame", because they
// are frame tools, not source settings.
function coldFrameBlock(s) {
  const tool = s.corrections?.tool === 'draw' ? 'draw' : 'select';
  return `<div class="vs-block vs-frame-tools"><h4>${esc(t('thisFrame'))}</h4>
    <div class="vs-row"><button class="${tool === 'select' ? 'active' : ''}" data-vs-action="tool" data-vs-value="select">${esc(t('selectTool'))}</button><button class="${tool === 'draw' ? 'active' : ''}" data-vs-action="tool" data-vs-value="draw">${esc(t('drawTool'))}</button></div>
    <div class="vs-row"><button data-vs-action="add-polygon">${esc(t('addPolygon'))}</button><button data-vs-action="clear-polygon">${esc(t('clearPolygon'))}</button></div>
    <div class="vs-row"><button data-vs-action="run-inference" ${s.corrections?.inferRunning ? 'disabled' : ''}>${esc(t('runInference'))}</button></div>
    ${inferenceLine(s)}${s.corrections?.inferStatus ? `<p class="vs-mono">${esc(engineText(s.corrections.inferStatus))}</p>` : ''}
    <p class="vs-note" data-vs-layers-note="1">${esc(t('layerNote'))}</p>
    ${s.dirty ? `<div class="vs-row"><button class="primary" data-vs-action="save-corrections">${esc(t('saveCorrections'))}</button></div>` : ''}
    <p class="vs-note">${esc(t('coldStartHint'))}</p></div>`;
}
// The rail with nothing selected: selection-related copy only. The source
// settings are not here any more - they open from the Source chip in the chip
// row, so the rail cannot be mistaken for a settings drawer.
function emptyRailBlock(s) {
  return `<h3>${esc(t('noSelection'))}</h3>
  <p class="vs-empty" data-vs-empty="no-selection">${esc(t('railEmpty'))}</p>
  <p class="vs-note">${esc(t('selectCueHint'))}</p>
  ${coldFrameBlock(s)}`;
}
// The Source block's body, now the body of the panel under the chip row: the
// dataset chips, the live state row, the detector toggles, freshness, the saved
// channels and the latency caveat are unchanged, only the container moved.
// Which live stages the running processor actually has, and at what cadence: a
// partitioned stage is absent on the frames it skips, and the panel says so
// rather than letting "no ball" stand for "no ball detector ran".
// The VOD replay request, and the honest self-description of the replay that is
// actually running: kind 'vod-replay', live false, the VOD id, the rate and the
// drift the capture is carrying. A replay is never labelled a broadcast here,
// and a refusal is the server's sentence rather than a spinner that never ends.
function replaySelfDescription(replay) {
  if (!replay || !replay.kind) return '';
  const parts = [`kind ${replay.kind}`, `${t('liveFlag')} ${replay.live === true}`];
  if (replay.vod_id) parts.push(`vod ${replay.vod_id}`);
  if (replay.rate != null) parts.push(`${t('vodRate').split(' ')[0]} ×${replay.rate}`);
  if (replay.drift_s != null) parts.push(`${t('vodDrift')} ${Number(replay.drift_s).toFixed(2)} s`);
  if (replay.network) parts.push(replay.network);
  if (replay.pacing) parts.push(`${t('pace')} ${replay.pacing}`);
  return parts.join(' · ');
}
function replayBlock(s) {
  const live = s.live || {};
  const chosen = opts.replayChoice ? opts.replayChoice() : null;
  const running = live.replay || (live.source && live.source.kind === 'vod-replay' ? live.source : null);
  const failed = live.attempt?.error && String(live.attempt.source || '').startsWith('vod-replay');
  const state = running ? `<p class="vs-mono" data-vs-replay="running">${esc(replaySelfDescription(running))}</p>`
    : failed ? `<p class="vs-mono" data-vs-replay="failed">${esc(t('vodFailed'))}: ${esc(live.attempt.error)}</p>`
    : chosen ? `<p class="vs-mono" data-vs-replay="chosen">${esc(t('vodChosen'))}: vod ${esc(chosen.vod_id)} · ${esc(t('vodStart'))} ${esc(chosen.start_s)} · ${esc(t('vodRate').split(' ')[0])} ×${esc(chosen.rate)} · ${esc(t('vodNotLive'))}</p>`
    : '';
  return `<div class="vs-block vs-replay"><h4>${esc(t('vodReplay'))}</h4>
    <label class="vs-field">${esc(t('vodId'))}<input name="vod" type="text" data-vs-field="vod" placeholder="https://www.twitch.tv/videos/1234567890"></label>
    <div class="vs-row"><label class="vs-field">${esc(t('vodStart'))}<input name="start" type="number" data-vs-field="vod-start" min="0" step="1" value="0"></label><label class="vs-field">${esc(t('vodRate'))}<input name="rate" type="number" data-vs-field="vod-rate" min="0.25" max="4" step="0.25" value="1"></label></div>
    <div class="vs-row"><button data-vs-action="pick-replay">${esc(t('vodUse'))}</button></div>
    ${state}<p class="vs-note">${esc(t('vodNote'))}</p></div>`;
}
function liveStageLine(s) {
  const stages = (s.live?.stages || []).filter(stage => stage && stage.name);
  if (!stages.length) return '';
  const rows = stages.map(stage => {
    const cadence = Number(stage.every_n_frames) > 1
      ? `${t('stageEvery')} ${Number(stage.every_n_frames)} ${t('frameCount')} · ${t('stageAbsent')}`
      : `${t('stageEvery')} 1 ${t('frameCount')}`;
    const runs = Number(stage.runs || 0);
    return `${esc(stage.name)} · ${esc(cadence)} · ${runs} ${t('stageRuns')}`;
  });
  return `<p class="vs-mono" data-vs-live-stages="${stages.length}">${rows.map(esc).join('<br>')}</p>`;
}
function sourcePanelHTML(s) {
  const attempt = s.live.attempt && s.live.attempt.error ? `<div class="vs-error-block"><h4>${esc(t('startFailed'))}</h4><p class="vs-mono">${esc(t('attemptSource'))}: ${esc(s.live.attempt.source || '—')}</p><p class="vs-mono">${esc(s.live.attempt.error)}</p><p>${esc(t('remedy'))}: ${esc(t('remedyText'))}</p><button data-vs-action="live-start">${esc(t('retry'))}</button></div>` : '';
  const channels = (opts.channels() || []).map(c => `<div class="vs-channel"><span class="vs-mono">${esc(c.url)}</span><button data-vs-action="pick-live" data-vs-value="twitch:${esc(c.id)}">${esc(t('select'))}</button><button data-vs-action="forget-channel" data-vs-id="${esc(c.id)}">${esc(t('remove'))}</button></div>`).join('');
  const live = s.live;
  // A start that failed must not leave the row reading "idle": the row states
  // the failure with the same vocabulary the running/stopped states use.
  const liveFailed = !!(live.error || live.attempt?.error);
  const liveRowState = liveFailed && live.state !== 'running' && live.state !== 'starting' ? 'error' : live.state;
  return `${attempt}
  <div class="vs-block"><h4>${esc(t('dataset'))}</h4><div class="vs-chiprow">${(s.datasets || []).map(d => `<button class="vs-chip${s.source.kind === 'vod' && d.id === s.dataset ? ' active' : ''}" data-vs-action="pick-dataset" data-vs-value="${esc(d.id)}">${esc(d.label || d.id)}</button>`).join('')}</div>
    <p class="vs-mono">${esc(s.source.kind === 'vod' ? s.source.label : '—')} · ${esc(t('frameCount'))} ${esc(s.frame.count)}</p></div>
  <div class="vs-block"><h4>${esc(t('liveState'))}</h4>
    <p class="vs-mono" id="vs-live-status">${esc(stateText(liveRowState))}${(live.error || live.attempt?.error) ? ` · ${esc(live.error || live.attempt.error)}` : ''} · ${esc(t('age'))} ${fmtAge(live.frame_age_ms)} · ${esc(t('receive'))} ${fmtAge(live.receive_to_result_ms)} · ${esc(t('dropped'))} ${esc(live.skipped ?? 0)}</p>
    <div class="vs-row"><button class="primary" data-vs-action="live-start">${esc(t('start'))}</button><button data-vs-action="live-stop">${esc(t('stop'))}</button></div>
    <div class="vs-chiprow">${channels}${(s.datasets || []).map(d => `<button class="vs-chip" data-vs-action="pick-live" data-vs-value="dataset:${esc(d.id)}">${esc(d.label || d.id)}</button>`).join('')}</div>
    <div class="vs-row">${['table','person','ball'].map(d => `<label class="vs-check" title="${d === 'ball' ? esc(t('liveBallNote')) : esc(t(d))}"><input type="checkbox" data-vs-action="live-detector" data-vs-value="${d}" ${(live.detectors || []).includes(d) ? 'checked' : ''}> ${esc(d === 'ball' ? t('liveBall') : t(d))}</label>`).join('')}</div>
    <p class="vs-note" data-vs-live-ball="note">${esc(t('liveBallNote'))}</p>
    ${liveStageLine(s)}
    <p class="vs-note">${esc(t('latency'))}</p></div>
  <div class="vs-block"><h4>${esc(t('detectors'))}</h4><div class="vs-row">${[['table','table'],['person','person'],['balls','ball']].map(([k, l]) => `<label class="vs-check"><input type="checkbox" data-vs-action="detector" data-vs-value="${k}" ${s.detectors[k] ? 'checked' : ''}> ${esc(t(l))}</label>`).join('')}</div><p class="vs-note">${esc(t('detectorReason'))}</p></div>
  ${replayBlock(s)}
  <div class="vs-block"><h4>${esc(t('saved'))}</h4>${channels || `<p class="vs-empty">—</p>`}
    <form id="source-form"><label class="vs-field">${esc(t('channelUrl'))}<input name="url" type="url" placeholder="https://www.twitch.tv/channel" required></label><button class="primary">${esc(t('addChannel'))}</button></form></div>`;
}
function eventBlock(s) {
  const item = s.selection.event || s.events.items[s.events.index];
  if (!item) return `<h3>${esc(t('events'))}</h3><p class="vs-empty" data-vs-empty="shots-measured-none">${esc(t('noShotsMeasured'))}</p>`;
  const annotation = item.annotation || {};
  const verdict = s.verdictDraft ?? annotation.verdict ?? '';
  // The stage is the only picture surface for a cue: it plays the window with
  // the overlay and freezes into a still when the window cannot play. The
  // inspector used to carry a second still (`/media/<dataset>/evidence/<file>`,
  // falling back to an event frame); rendered next to a moving stage it read as
  // a picture that never updated.
  return `<h3>${esc(item.type === 'pot' ? t('pots') : t('shots'))} <span class="vs-mono vs-dim">#${esc(item.id)}</span></h3>
  <p class="vs-mono">${esc(timecode(item.t))}${pocketName(item) ? ` · ${esc(pocketName(item))}` : ''}</p>
  <div class="vs-row"><button class="primary" data-vs-action="play-event" data-vs-value="${esc(s.events.index)}">${esc(t('playInStage'))}</button></div>
  <p class="vs-note">${esc(t('evidenceNote'))}</p>
  <div class="vs-block"><h4>${esc(t('geometry'))}</h4>${eventGeometry(item)}</div>
  <div class="vs-block"><h4>${esc(t('verdict'))}</h4><p class="vs-mono">${esc(verdict ? t(verdict) : t('notReviewed'))}</p></div>
  <label class="vs-field">${esc(t('shooter'))}<select data-vs-action="shooter">${[['','—'],['A',t('seedA')],['B',t('seedB')],['?',t('unknown')]].map(([v, l]) => `<option value="${v}" ${(annotation.shooter || '') === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
  <label class="vs-field">${esc(t('notes'))}<textarea rows="3" data-vs-action="note">${esc(annotation.note || '')}</textarea></label>
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
  <div class="vs-row"><button data-vs-action="crop-step" data-vs-value="-1">${esc(t('prevCrop'))}</button><button data-vs-action="crop-step" data-vs-value="1">${esc(t('nextCrop'))}</button></div>
  ${receiptLine('ball')}`;
}
// Identity labelling for a person track: EXACTLY two ways to name it - a
// regular from the roster (the identity pipeline keeps face/body matching
// working) or a guest name (stored as this track's label in the seeds store).
// "Not a player" is a quiet secondary action because spectators exist in this
// footage and must stay excludable without competing with the two options.
// The module's refusal codes, in the operator's words. The code and its own
// sentence stay on screen next to the translation, so nothing is smoothed over.
const ENROL_REASON_COPY = {
  selection_not_matched:['the click does not overlap a person in this frame', '此点击与此帧中的人物不重叠'],
  track_not_found:['that person was not seen in the sampled frames', '在采样帧中没有看到该人物'],
  no_face_in_track:['the person was seen, but no face inside their box', '看到了该人物，但其标注框内没有人脸'],
  face_too_small:['every face was below the eye-distance gate', '所有人脸都低于眼距门槛'],
  face_low_detection:['every face was below the detection gate', '所有人脸都低于检测门槛'],
  single_face_only:['only one usable face: no second face to cross-check it', '只有一张可用人脸：没有第二张可交叉核对'],
  inconsistent_faces:['the usable faces do not agree: more than one person may be in this track', '可用人脸彼此不一致：该轨迹内可能有不止一人'],
  mixed_track:['the best faces disagree with the rest of this track: the track may have switched people', '最佳人脸与轨迹其余部分不一致：该轨迹可能换过人'],
  no_stored_evidence:['the identity index holds no usable face for this cluster', '身份索引中该聚类没有可用人脸'],
  preview_expired:['this preview is no longer held; preview again', '此预览已不再保留；请重新预览'],
  token_mismatch:['these crops are not the ones you were shown; preview again', '这些裁剪图与展示时不一致；请重新预览'],
  player_name_required:['a name is required to enrol a regular', '登记常客需要姓名']
};
function enrolReasonText(payload) {
  const row = ENROL_REASON_COPY[payload?.reason];
  if (!row) return String(payload?.message || payload?.reason || t('unknown'));
  return opts?.lang === 'zh' ? row[1] : row[0];
}
function enrolCropsHTML(payload) {
  const crops = payload?.crops || [];
  if (!crops.length) return '';
  return `<div class="vs-cropgrid">${crops.map(c => `<figure class="vs-cropcard" data-vs-crop="${esc(c.index)}"><img src="${esc(c.jpeg_data_url || '')}" alt=""><figcaption><span class="vs-mono">#${esc(c.index)}</span> · ${esc(t('enrolFrame'))} ${esc(c.frame_index)}${c.t != null ? ` · t ${Number(c.t).toFixed(1)} s` : ''}<br><span class="vs-mono vs-dim">${esc(t('enrolDet'))} ${c.det_score != null ? Number(c.det_score).toFixed(2) : '—'} · ${esc(t('enrolEye'))} ${c.eye_px != null ? Number(c.eye_px).toFixed(1) : '—'} px</span></figcaption></figure>`).join('')}</div>`;
}
// The enrolment block on the selected person: preview (reads), then the one
// confirm click (writes). The evidence level is stated before the name is typed,
// because one stored face is weaker evidence than a cross-checked gallery.
function enrolBlock(s) {
  const e = s.enroll || {status:'idle'};
  const p = e.payload || {};
  const ev = p.evidence || {};
  const seconds = e.elapsed_ms != null ? (Number(e.elapsed_ms) / 1000).toFixed(0) : '0';
  const start = e.status === 'pending' ? '' : `<div class="vs-row"><button data-vs-action="enroll-preview">${esc(e.status === 'idle' ? t('enrolStart') : t('enrolRetry'))}</button></div>`;
  let body = '';
  if (e.status === 'pending') {
    body = `<p class="vs-mono" data-vs-enrol="pending">${esc(t('enrolScanning'))} · ${esc(seconds)} s</p><p class="vs-note">${esc(t('enrolWait'))}</p>`;
  } else if (e.status === 'ready' || e.status === 'written') {
    const facts = [
      `${t('enrolFramesSeen')} ${p.frames_seen ?? '—'}`,
      `${t('enrolFaces')} ${p.quality?.kept ?? '—'}/${p.quality?.usable ?? '—'}`,
      `${t('enrolPurity')} ${p.purity?.probes ? `${Math.round((p.purity.agreement ?? 0) * 100)}% (${p.purity.probes})` : t('enrolNoPurity')}`,
      `${t('enrolIoU')} ${p.selection_iou ?? '—'}`
    ].join(' · ');
    const evidence = `${t('enrolEvidence')}: ${t(ev.stored_face ? 'enrolClusterFace' : 'enrolWindowScan')} · ${ev.crops ?? (p.crops || []).length} ${t('enrolCrops')} · ${t(ev.cross_checked ? 'enrolCrossChecked' : 'enrolNotCrossChecked')}`;
    body = `${enrolCropsHTML(p)}<p class="vs-mono" data-vs-enrol="facts">${esc(facts)}</p><p class="vs-mono" data-vs-enrol="evidence">${esc(evidence)}</p>
      <label class="vs-field">${esc(t('enrolName'))}<input type="text" data-vs-action="enroll-name" maxlength="60" value="${esc(e.name || '')}"></label>
      <div class="vs-row"><button class="primary" data-vs-action="enroll-confirm">${esc(t('enrolConfirm'))}</button>${e.status === 'written' ? '' : `<button data-vs-action="enroll-cancel">${esc(t('enrolCancel'))}</button>`}</div>
      ${e.status === 'written' ? `<p class="vs-mono" data-vs-enrol="written">✓ ${esc(t('enrolWrote'))}</p>` : ''}`;
  } else if (e.status === 'refused') {
    body = `<p class="vs-mono" data-vs-enrol="refused">${esc(t('enrolRefused'))}: ${esc(enrolReasonText(p))}</p><p class="vs-mono vs-dim">${esc(p.reason || '')}${p.message ? ` · ${esc(p.message)}` : ''}</p>${enrolCropsHTML(p) || `<p class="vs-note">${esc(t('enrolNoCrops'))}</p>`}`;
  }
  return `<div class="vs-block vs-enrol"><h4>${esc(t('enrolTitle'))}</h4>${start}${body}<p class="vs-note">${esc(t('enrolHint'))}</p></div>`;
}
function personBlock(s) {
  const facts = bindingFacts(s);
  const roster = opts.regulars() || [];
  const picked = facts.identity ? facts.identity.id : '';
  const guestValue = facts.guest ? facts.label.raw : (guestDraft && String(guestDraft.track) === String(s.persons.track) ? guestDraft.value : '');
  const options = [`<option value=""${picked ? '' : ' selected'}>${esc(t('guestOption'))}</option>`]
    .concat(roster.map(row => `<option value="${esc(row.id)}"${String(row.id) === picked ? ' selected' : ''}>${esc(row.name)}${row.rating != null ? ` · ${esc(row.rating)}` : ''}${row.statusText && row.status && row.status !== 'Active' ? ` · ${esc(row.statusText)}` : ''}</option>`));
  const guestOff = !!picked;
  return `<h3>${esc(t('identity'))}</h3>
  ${bindingLine(s)}
  <div class="vs-block vs-labelblock">
    <label class="vs-field">${esc(t('whichRegular'))}<select data-vs-action="regular" ${roster.length ? '' : 'disabled'}>${options.join('')}</select></label>
    <label class="vs-field${guestOff ? ' vs-guest-off' : ''}" data-vs-role="guest-field">${esc(t('guestName'))}<input type="text" data-vs-action="guest-name" maxlength="60" value="${esc(guestValue)}" placeholder="${esc(t('guestPlaceholder'))}" ${guestOff ? 'disabled' : ''}></label>
    <p class="vs-note" data-vs-role="bind-hint">${esc(bindHint(facts, picked))}</p>
  </div>
  ${enrolBlock(s)}
  <div class="vs-block vs-quiet"><div class="vs-row"><button data-vs-action="seed" data-vs-value="ignore">${esc(t('notAPlayer'))}</button></div>
    <p class="vs-note">${esc(t('ignoreHint'))}</p></div>
  <div class="vs-block"><h4>${esc(t('rebuild'))}</h4><div class="vs-row"><button data-vs-action="rebuild">${esc(t('rebuild'))}</button><button data-vs-action="rebuild-refresh">${esc(t('refresh'))}</button></div><p class="vs-note">${esc(t('seedHint'))}</p><p class="vs-mono">${esc(engineText(s.persons.status || ''))}</p></div>
  ${receiptLine('person')}`;
}
// What Save will do, said before the click: a regular needs an identity cluster,
// a guest name never does. The note is the honest reason, not a dead button.
function bindHint(facts, picked) {
  if (!picked) return t('bindGuestHint');
  return facts.cluster == null ? t('noCluster') : t('bindIdentityHint');
}
function anchorBlock(s) {
  if (s.dataset !== 'vod30') return `<h3>${esc(t('calibration'))}</h3><p class="vs-empty">${esc(t('vodOnlyAnchors'))}</p>`;
  const rows = s.anchors.points.map((p, i) => `<button class="vs-item${s.selection.anchor === i ? ' selected' : ''}" data-vs-action="select-anchor" data-vs-value="${i}"><span>${i + 1}</span><span class="vs-mono">${Math.round(p[0])}, ${Math.round(p[1])}</span></button>`).join('');
  return `<h3>${esc(t('calibration'))}</h3>
  <p class="vs-note">${esc(t('anchorNote'))}</p>
  <div class="vs-items">${rows || `<p class="vs-empty">${esc(t('loading2'))}</p>`}</div>
  <div class="vs-nudge"><button data-vs-action="nudge" data-vs-value="0,-1">↑</button><button data-vs-action="nudge" data-vs-value="-1,0">←</button><button data-vs-action="nudge" data-vs-value="1,0">→</button><button data-vs-action="nudge" data-vs-value="0,1">↓</button></div>
  <div class="vs-row">${[70,200,350].map(x => `<button data-vs-action="anchors-at" data-vs-value="${x}">${esc(t('anchorsAt'))} ${x} s</button>`).join('')}</div>
  <p class="vs-mono">${s.anchors.loaded ? `t ${Number(s.anchors.t).toFixed(1)} s` : esc(t('loading2'))}</p>
  ${receiptLine('anchor')}`;
}
// Where this frame's detection came from, said out loud: a stored file is
// evidence from an earlier run and keeps its own timestamp; a result run on this
// frame now was never written to disk.
const stampText = value => { if (!value) return ''; const at = new Date(value); return Number.isNaN(at.getTime()) ? String(value) : at.toLocaleString(); };
function inferenceLine(s) {
  const c = s.corrections || {};
  if (!c.inferenceAt || c.result === 'none') return '';
  return `<p class="vs-mono" data-vs-inference="${c.storedInference ? 'stored' : 'session'}">${esc(t('inferenceFrom'))}: ${esc(t(c.storedInference ? 'storedInference' : 'inferenceNotStored'))} · ${esc(stampText(c.inferenceAt))}</p>`;
}
function boxLayers(s) { return `${s.corrections?.manualBoxes ?? 0}/${s.corrections?.modelBoxes ?? 0}`; }
function boxBlock(s) {
  const index = s.selection.box;
  const labels = ['person','ball','cue','solid','stripe','eight'];
  return `<h3>${esc(t('box'))} ${index + 1}</h3>
  <label class="vs-field">${esc(t('boxLabel'))}<select data-vs-action="box-label">${labels.map(l => `<option value="${l}" ${s.corrections.boxLabel === l ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
  <div class="vs-row"><button data-vs-action="delete-box">${esc(t('deleteBox'))}</button></div>
  <div class="vs-block"><h4>${esc(t('tool'))}</h4><div class="vs-row"><button class="${s.corrections.tool === 'select' ? 'active' : ''}" data-vs-action="tool" data-vs-value="select">${esc(t('selectTool'))}</button><button class="${s.corrections.tool === 'draw' ? 'active' : ''}" data-vs-action="tool" data-vs-value="draw">${esc(t('drawTool'))}</button></div>
    <label class="vs-field">${esc(t('newBoxLabel'))}<select data-vs-action="new-box-label">${labels.map(l => `<option value="${l}" ${s.corrections.newBoxLabel === l ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
    <div class="vs-row"><button data-vs-action="add-polygon">${esc(t('addPolygon'))}</button><button data-vs-action="clear-polygon">${esc(t('clearPolygon'))}</button></div></div>
  <div class="vs-block vs-layers-note" data-vs-layers="${esc(boxLayers(s))}"><h4>${esc(t('yourBoxes'))}</h4><p class="vs-mono">${esc(t('yourBoxes'))} ${esc(s.corrections?.manualBoxes ?? 0)} · ${esc(t('modelBoxes'))} ${esc(s.corrections?.modelBoxes ?? 0)}</p><p class="vs-note">${esc(t('layerNote'))}</p></div>
  <div class="vs-block"><h4>${esc(t('runInference'))}</h4>${inferenceLine(s)}<p class="vs-mono">${esc(engineText(s.corrections.inferStatus || ''))}</p>${receiptLine('corrections')}</div>`;
}
// The primary write of the active block lives in the inspector's action footer,
// so it stays clickable at any viewport height (measured at 1280x599).
function actionsHTML(s) {
  const kind = s.selection.kind;
  if (kind === 'event') {
    const item = s.selection.event || s.events.items[s.events.index];
    const verdict = s.verdictDraft ?? item?.annotation?.verdict ?? '';
    return `${['correct','wrong','unsure'].map(v => `<button class="${verdict === v ? 'active' : ''}" data-vs-action="verdict-draft" data-vs-value="${v}">${esc(t(v))}</button>`).join('')}<button class="primary" data-vs-action="save-verdict">${esc(t('saveReview'))}</button><button data-vs-action="next-event">${esc(t('nextCue'))}</button>`;
  }
  if (kind === 'ball') {
    const label = s.selection.crop?.label;
    return `<button class="${label === 'u' ? 'active' : ''}" data-vs-action="label-ball" data-vs-value="-1">${esc(t('unknown'))}</button><button class="${label === 0 ? 'active' : ''}" data-vs-action="label-ball" data-vs-value="0">${esc(t('cue'))} 0</button><button data-vs-action="label-ball" data-vs-value="clear">${esc(t('clear'))}</button>`;
  }
  if (kind === 'person') {
    // The primary write of the identity block lives in the footer, so it stays
    // clickable at any viewport height: Save (regular or guest) and Clear.
    return `<button class="primary" data-vs-action="identity-save">${esc(t('saveBinding'))}</button><button data-vs-action="identity-clear">${esc(t('clearBinding'))}</button>`;
  }
  if (kind === 'anchor') return `<button class="primary" data-vs-action="save-anchors">${esc(t('saveAnchors'))}</button>`;
  if (kind === 'box') return `<button data-vs-action="run-inference">${esc(t('runInference'))}</button><button class="primary" data-vs-action="save-corrections">${esc(t('saveCorrections'))}</button>`;
  // Nothing selected: the live start/stop pair moved into the Source panel with
  // the rest of the source settings, so this footer only carries the frame's own
  // pending write.
  return s.dirty ? `<button class="primary" data-vs-action="save-corrections">${esc(t('saveCorrections'))}</button>` : '';
}
function inspectorHTML(s) {
  const kind = s.selection.kind;
  const body = kind === 'event' ? eventBlock(s) : kind === 'ball' ? ballBlock(s) : kind === 'person' ? personBlock(s) : kind === 'anchor' ? anchorBlock(s) : kind === 'box' ? boxBlock(s) : emptyRailBlock(s);
  const liveChat = s.source.kind === 'live' && s.source.channel && opts.chat();
  const chat = liveChat ? `<div class="vs-chat"><iframe title="Twitch chat" src="https://www.twitch.tv/embed/${esc(s.source.channel)}/chat?parent=${esc(location.hostname)}&darkpopout"></iframe></div>` : '';
  const chatToggle = s.source.kind === 'live' && s.source.channel ? `<button class="vs-chat-toggle" data-vs-action="chat">${esc(opts.chat() ? t('hideChat') : t('showChat'))}</button>` : '';
  const close = kind === 'none' ? '' : `<button class="vs-close" data-vs-action="deselect" aria-label="×">×</button>`;
  const notice = s.notice.text ? `<div class="vs-notice${s.notice.error ? ' error' : ''}" role="status">${esc(engineText(s.notice.text))}</div>` : '';
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
  // The identity block reads the saved seed and the track's binding, so both
  // belong in the signature: a save must repaint the block that saved it.
  const insSig = `${s.selection.kind}|${s.selection.event?.id || ''}|${s.selection.crop?.file || ''}|${s.selection.crop?.label ?? ''}|${s.selection.track ?? ''}|${s.selection.person?.cluster_id ?? ''}|${s.selection.person?.player_id ?? ''}|${s.selection.person?.bound_evidence?.source ?? ''}|${(s.persons.tracks || []).find(x => String(x.id) === String(s.persons.track))?.seed ?? ''}|${s.enroll?.status || ''}|${s.enroll?.payload?.token || ''}|${s.enroll?.payload?.reason || ''}|${s.enroll?.elapsed_ms == null ? '' : Math.round(s.enroll.elapsed_ms / 1000)}|${s.selection.anchor ?? ''}|${s.selection.box ?? ''}|${s.corrections.tool}|${s.corrections.boxLabel || ''}|${s.corrections.newBoxLabel || ''}|${s.corrections.inferStatus}|${s.corrections.result}|${s.persons.status}|${s.live.state}|${s.live.error || ''}|${s.live.attempt?.at || ''}|${s.live.detectors.join(',')}|${s.notice.text}|${s.busy}|${s.dataset}|${s.source.kind}|${(s.receipts || []).map(r => `${r.key}:${r.at}`).join(',')}|${opts.lang}`;
  if (insSig !== sig.inspector) {
    const body = $('#vs-inspector-scroll'), actions = $('#vs-inspector-actions');
    if (body) body.innerHTML = inspectorHTML(s);
    if (actions) actions.innerHTML = `<div class="vs-row">${actionsHTML(s)}</div>`;
    sig.inspector = insSig;
  }
  const frameInput = $('#vs-frame-index');
  if (frameInput && document.activeElement !== frameInput) frameInput.value = s.frame.index;
  const scrub = $('#vs-scrub');
  if (scrub) {
    const max = String(Math.max(0, s.frame.count - 1));
    if (scrub.getAttribute('max') !== max) scrub.setAttribute('max', max);
    if (scrub.getAttribute('step') !== '1') scrub.setAttribute('step', '1');
    if (document.activeElement !== scrub) scrub.value = s.frame.index;
  }
  const marksSig = `${s.dataset}|${s.frame.duration}|${s.events.items.map(e => `${e.id}:${e.t}:${e.type}`).join(',')}|${s.playback.on ? 1 : 0}|${s.playback.event || ''}|${s.playback.from}|${s.playback.to}|${s.playback.loops}|${s.playback.playing ? 1 : 0}`;
  const marks = $('#vs-marks');
  if (marks && marksSig !== sig.marks) {
    marks.innerHTML = windowBandHTML(s) + s.events.items.map(e => { const pct = e.t / s.frame.duration * 100; return pct >= 0 && pct <= 100 ? `<button class="scrub-mark ${esc(e.type)}" data-vs-action="select-event-time" data-vs-value="${esc(e.t)}" title="#${esc(e.id)} ${esc(e.type)} · ${esc(timecode(e.t))}" style="left:${pct}%"></button>` : ''; }).join('');
    sig.marks = marksSig;
  }
  const facts = $('#vs-facts');
  if (facts) { facts.textContent = factsLine(s); facts.title = quadDetail(s); }
  const edge = $('#vs-edge'); if (edge) { edge.dataset.live = s.source.kind === 'live' ? '1' : '0'; edge.style.left = `${s.source.kind === 'live' ? 100 : (s.frame.duration ? Math.min(100, Math.max(0, s.frame.t / s.frame.duration * 100)) : 0)}%`; }
  const play = $('#vs-play'); if (play) play.textContent = s.frame.playing ? `❚❚ ${t('pause')}` : `▶ ${t('play')}`;
  root.querySelectorAll('[data-vs-label]').forEach(node => { const copy = t(node.dataset.vsLabel); if (node.textContent !== copy) node.textContent = copy; });
  const frameField = $('#vs-frame-index');
  if (frameField) { const max = String(Math.max(0, s.frame.count - 1)); if (frameField.getAttribute('max') !== max) frameField.setAttribute('max', max); frameField.disabled = s.source.kind === 'live'; }
  // The strip is the VOD timeline; a live edge has no frame index to step.
  const liveStrip = s.source.kind === 'live';
  const strip = $('#vs-strip'); if (strip) strip.dataset.live = liveStrip ? '1' : '0';
  root.querySelectorAll('[data-vs-action="step"],[data-vs-action="freeze"],[data-vs-action="play"],#vs-scrub').forEach(node => { node.disabled = liveStrip; });
  syncFooterHeight();
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
    case 'pick-replay': {
      // A VOD id or URL, where in it to start, and how fast: the server resolves it
      // and the panel reports the capture's own kind/live/rate/drift afterwards.
      const field = name => (root.querySelector(`[data-vs-field="${name}"]`) || {}).value || '';
      const vod = String(field('vod')).trim();
      if (!vod) { opts.notice?.(t('vodId')); break; }
      opts.pickReplay({vod_id: vod, start_s: Number(field('vod-start')) || 0, rate: Number(field('vod-rate')) || 1});
      break;
    }
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
    case 'play-event': { const index = Number(value); if (Number.isInteger(index) && s.events.items[index]) target.playEvent(index); break; }
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
    case 'source-panel': sourceOpen = !sourceOpen; sig.chips = null; render(); break;
    case 'regular': syncGuestField(value); break;
    case 'guest-name': guestDraft = {track: String(s.persons.track ?? ''), value: node.value}; break;
    // The two labelling paths, never mixed: a regular goes through the identity
    // pipeline (the player's id on this track's cluster), a guest name is this
    // track's label in the seeds store. An empty form is refused by setSeed
    // before any write happens.
    case 'identity-save': {
      const select = root.querySelector('[data-vs-action="regular"]');
      const input = root.querySelector('[data-vs-action="guest-name"]');
      const picked = select ? select.value : '';
      const name = input ? input.value.trim() : '';
      if (picked) target.seedIdentity(node, picked);
      else { guestDraft = null; target.setSeed(node, name); }
      break;
    }
    case 'identity-clear': guestDraft = null; target.clearIdentity(node); break;
    // The preview only reads; the confirm is the write, and it happens here.
    case 'enroll-preview': target.enrollPreview(node); break;
    case 'enroll-confirm': target.enrollConfirm(node); break;
    case 'enroll-cancel': target.cancelEnroll(); break;
    case 'enroll-name': target.setEnrollName(node.value); break;
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
const FIELD_ACTIONS = ['shooter','note','regular','guest-name','enroll-name','box-label','new-box-label'];
// The guest box is the fallback path, so a chosen regular turns it off instead
// of leaving two competing inputs on screen. The hint says what Save will do,
// including the honest reason a regular cannot be saved on this track yet.
function syncGuestField(value) {
  const field = root.querySelector('[data-vs-role="guest-field"]');
  const input = root.querySelector('[data-vs-action="guest-name"]');
  const hint = root.querySelector('[data-vs-role="bind-hint"]');
  const off = !!value;
  if (field) field.classList.toggle('vs-guest-off', off);
  if (input) input.disabled = off;
  if (hint) hint.textContent = off ? (snap()?.selection?.person?.cluster_id == null ? t('noCluster') : t('bindIdentityHint')) : t('bindGuestHint');
}
function onInput(event) {
  if (!root || !root.contains(event.target)) return;
  const node = event.target.closest ? event.target.closest('[data-vs-action="guest-name"]') : null;
  if (node) guestDraft = {track: String(snap()?.persons?.track ?? ''), value: node.value};
}
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
  const footer = root.querySelector('#vs-inspector-actions');
  if (footerObserver) { footerObserver.disconnect(); footerObserver = null; }
  if (footer && typeof ResizeObserver !== 'undefined') { footerObserver = new ResizeObserver(syncFooterHeight); footerObserver.observe(footer); }
  root.addEventListener('click', onClick);
  root.addEventListener('change', onChange);
  root.addEventListener('input', onInput);
  const unsubscribe = engine()?.subscribe ? engine().subscribe(render) : null;
  render();
  return {render, detach() { if (unsubscribe) unsubscribe(); root.removeEventListener('click', onClick); root.removeEventListener('change', onChange); root.removeEventListener('input', onInput); }};
}
window.VisionStage = {attach, render, act, actionsHTML, factsLine, identityHTML, chipsHTML, inspectorHTML, quadReason, quadDetail, gateEvidence, eventGeometry, tierBadge, railHTML, bindingFacts, sourcePanelHTML, emptyRailBlock, seedText, syncGuestField};
})();
