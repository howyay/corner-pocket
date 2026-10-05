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
    freshness:'Freshness', saved:'Saved channels', savedVods:'Saved VODs', useInForm:'Use', savedOk:'Saved', addChannel:'Save Twitch channel', channelUrl:'Twitch source URL',
    select:'Select', remove:'Remove', chat:'Chat', showChat:'Show chat', hideChat:'Hide chat',
    startFailed:'Start attempt', cause:'Cause', remedy:'Remedy', retry:'Retry',
    lastLiveError:'Last live session ended with an error at {at}',
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
    vodReplay:'Twitch VOD replay', vodId:'VOD id or URL', vodIdNeeded:'Enter a Twitch VOD id or URL first.', vodStart:'Start at (s)', vodRate:'Rate (VOD s per wall s)',
    vodUse:'Use this VOD', vodChosen:'Chosen', vodNotLive:'a replay, never a live broadcast',
    // Imported broadcasts: a past VOD of a saved channel, downloaded once and browsed frame by frame.
    bcTitle:'Broadcasts', bcNote:'Recent broadcasts of your saved channels. Import one (or a range of it) to browse it frame by frame and run inference on any frozen frame.',
    bcNone:'No recent broadcasts listed.', bcError:'Twitch did not answer for this channel', bcRefresh:'Refresh list', bcLoading:'Asking Twitch…',
    bcImported:'imported', bcImport:'Import…', bcPaste:'VOD link or id', bcPasteGo:'Check',
    bcEstimate:'Estimate', bcConfirm:'Import', bcCancelForm:'Close', bcWhole:'whole broadcast', bcSize:'about', bcTime:'about', bcTimeUnknown:'time unknown until one import has run',
    bcFree:'free', bcAlready:'already imported', bcJob:'Import', bcCancel:'Cancel import', bcCancelAsk:'Cancel this import? The partial file is deleted and nothing is listed.',
    bcMb:'MB', bcEta:'left', bcDelete:'Delete…', bcDeleteAsk:'Delete this imported broadcast? Its video file and its list entry are removed. Your saved corrections are kept.',
    bcRecorded:'recorded broadcast', bcOf:'of', bcFrom:'from', bcAt:'broadcast time',
    bcAria:'Import progress',
    bcEventsNone:'Not scanned for events — browse frames and run inference on a frozen frame.',
    bcOtherChannel:'This VOD belongs to {channel}. Only saved channels can be analysed; add the channel under Source first.',
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
    inferenceSession:'inference \u00b7 this session',
    // Live detectors: the trained tiny ball net is a live stage, unlike the
    // CPU-heavy SAM3 frame detector, and the panel names the difference.
    boundManual:'manual bind', boundAuto:'automatic face match', boundIdentity:'identity binding',
    bindIdentityHint:'Saves through the identity pipeline, so face and body matching keep working.',
    bindGuestHint:'Saves the typed name as this track’s label.',
    closePanel:'Close',
    noCluster:'No identity cluster on this track yet — pick a person box on the stage that has one.',
    loading2:'loading…', reviewedCount:'reviewed', inQueue:'in queue', crops:'crops', reviewedWord:'reviewed',
    prediction:'prediction', seed:'saved seed', liveState:'Live state', manual:'manual', detectorReason:'The balls detector (SAM3) is CPU-heavy and stays an explicit opt-in.',
    attemptSource:'Attempted source', frameCount:'frames', keyMap:'Key map', showCues:'Cues', showInspector:'Inspector', cuesRegion:'Vision cues', stageRegion:'Vision stage', inspectorRegion:'Vision inspector', sheetTabs:'Vision panels', twitchChat:'Twitch chat', stepBack:'Previous frame', stepForward:'Next frame',
    notGlass:'receive-to-result is local processing latency, not glass-to-glass',
    stageEmpty:'Pick a moment on the strip, or select a cue, then freeze it here.', noCropHere:'no crop at this frame',
    liveNow:'live', staleNow:'STALE', replayNow:'VOD replay',
    coldStartHint:'Nothing selected: draw a box on the frame, add the table polygon, or run inference on this frozen frame.',
    quadOff:'model quad off saved corners', quadUnverified:'model quad unverified',
    quadRefused:'quad refused', quadFallback:'quad from the naive fallback', storedInference:'stored inference',
    quadDrift:'quad drift vs saved corners', tableFits:'table outline matches the saved corners',
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
    gateNetPath:'Net move / path', gatePeakSpeed:'Peak speed', gateDenseWindow:'Track window',
    provenanceMachine:'suggested by the computer · not yet confirmed by a person', provenanceMachineLegacy:'machine-produced candidate; no human has confirmed it', detectedBy:'detected by', technicalDetails:'Technical details',
    provenanceHuman:'confirmed by a person',
    tierLabel:'Confirmation tier', tierGeometry:'geometry-verified', tierWindow:'motion window only',
    tierGeometryHint:'The re-measured motion matches the claim: this ball, this start, this end.',
    tierWindowHint:'A ball really moved in this window, but not the one or where the claim said. Review it as a moment, not as the claimed shot.',
    noPotsMeasured:'No pot candidate in this VOD survived measurement: the ball census refuted every claim (a ball said to be potted was still on the cloth) and 2 stayed unconfirmed, so this list is empty on purpose.',
    noShotsMeasured:'No shot candidate survived measurement: every served event is explained by occlusion — a person crossing the cloth at that moment — and at 720p one ball\'s best possible signal sits on the detection floor (motion measured over the whole VOD: 0 of 55 ball-scale onsets could be a single ball). The events stay in the report artifacts, not in the queue.',
    loopWord:'loop', playingWord:'playing', pausedWord:'paused',
    inferAutoOn:'Inference runs when playback stops', inferAutoOff:'Auto inference off', inferAutoRunning:'Inferring',
    faceOnly:'face seen'
  },
  zh: {
    cues:'线索', inspector:'检查器', sources:'视频源', events:'事件', balls:'球', persons:'人物',
    anchors:'锚点', cloth:'台呢', pockets:'袋口', verdict:'判定', shooter:'击球者', notes:'备注',
    all:'全部', shots:'击球', pots:'入袋', pending:'未复核', labels:'球号标注', queue:'裁剪图队列',
    tracks:'人物轨迹', identity:'身份', calibration:'标定', frameIndex:'帧', step:'步进',
    freeze:'冻结', play:'播放', pause:'暂停', ticks:'事件刻度', dataset:'数据集',
    start:'开始', stop:'停止', detectors:'帧检测器', table:'球桌', person:'人物', ball:'球',
    latency:'Twitch 上游延迟：未知。接收到结果仅为本地处理耗时，不是端到端延迟。',
    freshness:'新鲜度', saved:'已保存频道', savedVods:'已保存回放', useInForm:'填入', savedOk:'已保存', addChannel:'保存 Twitch 频道', channelUrl:'Twitch 来源地址',
    select:'选择', remove:'移除', chat:'聊天', showChat:'显示聊天', hideChat:'隐藏聊天',
    startFailed:'启动尝试', cause:'原因', remedy:'处理', retry:'重试',
    lastLiveError:'上一次直播会话于 {at} 因错误结束',
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
    selectCueHint:'选中线索会在舞台上循环播放它的片段；冻结后可逐帧检查。',
    noCrops:'此队列没有裁剪图。', noTracks:'此录像没有可用的轨迹窗口。',
    noEvents:'此筛选下没有事件候选。', vodOnlyAnchors:'锚点仅适用于 vod30 数据集。',
    cropAtFrame:'此帧的裁剪图', selectedBall:'球', trackWord:'轨迹', box:'标注框', anchorWord:'锚点',
    seedA:'选手 A', seedB:'选手 B',
    whichRegular:'选择常客', guestOption:'— 不是常客（访客）—', guestName:'访客姓名',
    guestPlaceholder:'输入访客姓名', saveBinding:'保存', clearBinding:'清除',
    notAPlayer:'忽略（不是球员）',
    ignoreHint:'把这条轨迹标为观众：不参与身份分配，也不会和上面两个标注选项混在一起。',
    railEmpty:'先选一条线索、球、人物或锚点，再开始标注。', thisFrame:'此帧', noSelection:'未选择',
    bindNone:'尚未标注', bindLegacy:'旧版 A/B 种子', bindGuest:'访客姓名',
    liveBall:'球（训练网络）',
    liveBallNote:'实时球检测使用训练好的小型网络（流水线的 ball 阶段，启动前校验权重）。帧检测器里的「球」是 CPU 密集的 SAM3 扫描：它属于帧工具，从不作为实时阶段运行。',
    stageEvery:'每', stageAbsent:'跳过的帧上不运行', stageRuns:'次运行',
    vodReplay:'Twitch 回放', vodId:'回放 id 或网址', vodIdNeeded:'请先输入 Twitch 回放 id 或网址。', vodStart:'起始秒', vodRate:'倍速（回放秒/墙钟秒）',
    vodUse:'使用该回放', vodChosen:'已选择', vodNotLive:'回放，绝不是直播',
    bcTitle:'回放', bcNote:'已保存频道的近期直播回放。导入整场（或其中一段）后，可逐帧浏览，并对任意冻结帧运行推理。',
    bcNone:'没有列出近期回放。', bcError:'Twitch 未回应此频道', bcRefresh:'刷新列表', bcLoading:'正在询问 Twitch…',
    bcImported:'已导入', bcImport:'导入…', bcPaste:'回放链接或 id', bcPasteGo:'检查',
    bcEstimate:'估算', bcConfirm:'导入', bcCancelForm:'关闭', bcWhole:'整场回放', bcSize:'约', bcTime:'约', bcTimeUnknown:'完成一次导入前无法估计用时',
    bcFree:'可用', bcAlready:'已导入', bcJob:'导入', bcCancel:'取消导入', bcCancelAsk:'取消此次导入？未完成的文件会被删除，不会列出。',
    bcMb:'MB', bcEta:'剩余', bcDelete:'删除…', bcDeleteAsk:'删除这场已导入的回放？视频文件和列表条目会被移除，已保存的修正会保留。',
    bcRecorded:'录制回放', bcOf:'·', bcFrom:'日期', bcAt:'直播时间',
    bcAria:'导入进度',
    bcEventsNone:'未做事件扫描——可逐帧浏览，并对冻结帧运行推理。',
    bcOtherChannel:'此回放属于 {channel}。只能分析已保存的频道；请先在“来源”中添加该频道。',
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
    inferenceSession:'推理 \u00b7 本次会话',
    boundManual:'人工绑定', boundAuto:'自动人脸匹配', boundIdentity:'身份绑定',
    bindIdentityHint:'通过身份流程保存，人脸与体型匹配继续生效。',
    bindGuestHint:'把输入的姓名保存为该轨迹的标注。',
    closePanel:'关闭',
    noCluster:'此轨迹尚无身份聚类——请在舞台上选择带有聚类的球员框。',
    loading2:'读取中…', reviewedCount:'已复核', inQueue:'队列中', crops:'张裁剪图', reviewedWord:'已复核',
    prediction:'预测', seed:'已保存种子', liveState:'直播状态', manual:'人工', detectorReason:'球检测器（SAM3）为 CPU 密集，需显式开启。',
    attemptSource:'尝试的来源', frameCount:'帧数', keyMap:'按键', showCues:'线索', showInspector:'检查器', cuesRegion:'视觉线索', stageRegion:'视觉舞台', inspectorRegion:'视觉检查器', sheetTabs:'视觉面板', twitchChat:'Twitch 聊天', stepBack:'上一帧', stepForward:'下一帧',
    notGlass:'接收到结果为本地处理耗时，并非端到端延迟',
    stageEmpty:'在拖动条上选择时刻，或选择一条线索，然后在此冻结。', noCropHere:'此帧没有裁剪图',
    liveNow:'直播', staleNow:'已过期', replayNow:'回放',
    coldStartHint:'未选择对象：可直接在帧上绘制标注框、添加球桌多边形，或对本冻结帧运行推理。',
    quadOff:'模型四边形偏离已保存角点', quadUnverified:'模型四边形未校验',
    quadRefused:'四边形已拒绝', quadFallback:'四边形来自朴素回退', storedInference:'已存推理',
    quadDrift:'四边形相对已保存角点漂移', tableFits:'球台轮廓与已保存角点一致',
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
    gateNetPath:'净位移 / 路径', gatePeakSpeed:'峰值速度', gateDenseWindow:'轨迹窗口',
    provenanceMachine:'电脑识别的候选 · 尚未经人工确认', provenanceMachineLegacy:'机器产出，未经人工确认', detectedBy:'识别来源', technicalDetails:'技术细节',
    provenanceHuman:'已由人工确认',
    tierLabel:'确认层级', tierGeometry:'几何已核', tierWindow:'仅运动窗口',
    tierGeometryHint:'复测位移与声称一致：同这颗球、同起点、同终点。',
    tierWindowHint:'该窗口确有球在动，但不是声称的那颗，或不在声称的位置。请按「时刻」复核，而不是按声称的那次击球。',
    noPotsMeasured:'本场没有经测量存活的入袋候选：球数普查推翻了每一条断言（声称入袋的球仍在台面上），另有 2 条未确认，因此列表为空是刻意的。',
    noShotsMeasured:'没有击球候选通过测量：已服务的每条事件都被遮挡解释——那一刻有人穿过台面——且 720p 下单球的最强信号正好卡在检测底噪上（全片实测：55 个球尺度突变中 0 个可能来自单颗球）。这些事件保留在报告产物里，不在队列中。',
    loopWord:'循环', playingWord:'播放中', pausedWord:'已暂停',
    inferAutoOn:'暂停即自动推理', inferAutoOff:'自动推理已关闭', inferAutoRunning:'推理中',
    faceOnly:'已见人脸'
  }
};
let opts = null, root = null, sig = {}, sheet = 'cues', ageTimer = null, footerObserver = null;
// The source panel's open state and the half-typed guest name are adapter state,
// not engine state: the engine owns no frame or source selection ambiguity.
let sourceOpen = false, guestDraft = null;
// The VOD fields keep what the operator typed: the panel is rebuilt whenever the
// live status changes (every poll), so an input whose value only lives in the DOM
// loses a half-typed id. Same idea as guestDraft.
let replayDraft = null;
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
// A selected event can be the engine's raw object (no nearest_pocket_text), so a raw
// value still goes through the engine's words (pocketLabel, defined below, runs at call time).
function pocketName(event) { return event?.nearest_pocket_text || (event?.nearest_pocket ? pocketLabel(event.nearest_pocket) : ''); }
// One name per pocket on every surface: a stored rail key (right-side, foot-left...) is
// shown as the engine's position word (right-middle, bottom-left...; 中 右中, 左下...).
const pocketLabel = token => token ? (engine()?.pocketText ? engine().pocketText(String(token)) : String(token)) : '';
// Ball colours in the operator's language (the engine's table); unknown ones stay as data.
const colourLabel = value => value ? (engine()?.colourWord?.(value) || String(value)) : '';
// A vanish distance with its uncertainty and the pocket, e.g. '148 ± 54 mm · left-middle'.
function vanishText(n) {
  if (!Number.isFinite(n?.vanish_dist_mm)) return '';
  const unc = Number.isFinite(n.vanish_dist_mm_uncertainty) ? ` ± ${Math.round(n.vanish_dist_mm_uncertainty)}` : '';
  const pocket = pocketLabel(n.vanish_pocket);
  return `${Math.round(n.vanish_dist_mm)}${unc} mm${pocket ? ` · ${pocket}` : ''}`;
}
function pocketTag(event) {
  const n = event?.gate?.numbers;
  // With a vanish reading the gate line below already names the pocket with its mm;
  // the tag then names only the pocket, never a second spelling of the same one.
  const name = n && Number.isFinite(n.vanish_dist_mm) && n.vanish_pocket ? pocketLabel(n.vanish_pocket) : pocketName(event);
  return name ? `<span class="vs-mono vs-dim">${esc(name)}</span>` : '';
}
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
    if (Number.isFinite(n.vanish_dist_mm)) out.push(vanishText(n));
  } else if (Number.isFinite(n.disp_mm)) {
    out.push(`${Math.round(n.disp_mm)} mm${n.disp_color ? ` ${colourLabel(n.disp_color)}` : ''}`);
  }
  if (Number.isFinite(n.window_motion)) out.push(`${t('gateMotion')} ${n.window_motion}`);
  if ((event.dup_count || 1) > 1) out.push(`×${event.dup_count}`);
  return out;
}
// Gate reason codes in words. A code the table does not know stays verbatim (it is
// evidence), and a reason that is already a sentence from the scan is kept, in 中
// replaced by the scan's own Chinese sentence when it wrote one.
const REASONS = {
  cloth_occluded_at_disappearance: ['a person covered the cloth when the ball vanished', '球消失时有人挡住了台呢'],
  pocket_distance_ambiguous_mm: ['the pocket distance is within its error of the pocket edge', '袋口距离落在误差范围内，无法判定'],
  pocket_distance_outside_mm: ['the ball vanished outside the pocket radius', '球在袋口半径之外消失'],
  pocket_distance_within_uncertainty: ['the pocket distance is within its uncertainty', '袋口距离在不确定度之内'],
  pocket_test_agrees: ['pixel and millimetre pocket tests agree', '像素与毫米袋口判定一致'],
  pocket_test_disagrees_px_vs_mm: ['pixel and millimetre pocket tests disagree', '像素与毫米袋口判定不一致'],
  dense_motion_onset: ['motion onset found in the dense track', '密集跟踪中找到了起动'],
  window_grade_no_claim_to_check: ['motion-window grade: no separate claim to check the move against', '仅运动窗口：没有可对照的独立声明'],
  census_recovered: ['the ball count recovered afterwards', '之后球数恢复了'],
  displacement_corroborated: ['the move was re-measured and agrees', '位移已重新测量并一致'],
  geometry_mismatch: ['the claimed geometry and the measured move differ', '声称的几何与实测位移不一致'],
  identity_swap_suspected: ['two balls may have swapped identity', '可能有两颗球身份互换'],
  parked_in_jaws_possible: ['the ball may be parked in the pocket jaws', '球可能停在袋口颚部'],
  disappeared_outside_pocket: ['the ball disappeared away from any pocket', '球在远离袋口处消失'],
  no_motion_onset: ['no motion onset was found', '未找到起动'],
  motion_too_short: ['the motion was too short to count', '运动太短，不计入'],
  mm_projection_mismatch: ['the millimetre projection disagrees with the pixels', '毫米投影与像素不一致'],
};
// The gate that decided, in words (the code stays when it is new).
const GATES = {census:['census','球数'], occlusion:['occlusion','遮挡'], displacement:['displacement','位移'], motion:['motion','运动'], geometry:['geometry','几何']};
const gateName = code => { const row = GATES[String(code)]; return row ? (opts?.lang === 'zh' ? row[1] : row[0]) : String(code ?? ''); };
function reasonText(code) {
  const raw = String(code ?? '');
  const row = REASONS[raw];
  if (row) return opts?.lang === 'zh' ? row[1] : row[0];
  if (opts?.lang === 'zh') {
    const m = raw.match(/^([\d.]+) ± ([\d.]+) mm from the ([\w-]+) pocket -- too uncertain to call/);
    if (m) return `距${pocketLabel(m[3])}袋 ${m[1]} ± ${m[2]} mm，误差跨过袋口半径，无法判定`;
  }
  return raw;
}
function gateStatusWord(status) {
  return t(status === 'confirmed' ? 'gateConfirmed' : status === 'rejected' ? 'gateRejected' : 'gateUnconfirmed');
}
function eventGeometry(item) {
  const rows = [];
  const row = (key, value) => { if (value) rows.push({key, html: `<li class="vs-mono"><span class="vs-dim">${esc(t(key))}</span> ${esc(value)}</li>`}); };
  row('colour', colourLabel(item.color));
  if (item.type === 'pot') {
    row('ballLast', `${pxText(item.last_px)} px`);
    row('pocket', item.pocket_name ? pocketLabel(item.pocket_name) : pocketName(item));
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
    row('gateCheck', `${gateStatusWord(gate.status)}${gate.gate ? ` · ${gateName(gate.gate)}` : ''}`);
    if (item.tier === 'geometry' || item.tier === 'window') row('tierLabel', t(item.tier === 'geometry' ? 'tierGeometry' : 'tierWindow'));
    if (item.type === 'pot') {
      row('gateCensus', Number.isFinite(n.census_pre) && Number.isFinite(n.census_post) ? `${n.census_pre} → ${n.census_post}` : '');
      row('gateColourCensus', Number.isFinite(n.color_census_pre) && Number.isFinite(n.color_census_post) ? `${n.color_census_pre} → ${n.color_census_post}` : '');
      row('gateVanish', Number.isFinite(n.vanish_dist_mm)
        ? `${vanishText(n)}${Number.isFinite(n.approach_mm) ? ` · ${Math.round(n.approach_mm)} mm` : ''}` : '');
    } else {
      row('gateMove', Number.isFinite(n.disp_mm) ? `${Math.round(n.disp_mm)} mm${n.disp_color ? ` · ${colourLabel(n.disp_color)}` : ''}` : '');
      row('gateGap', Number.isFinite(n.geometry_gap_px) ? `${Math.round(n.geometry_gap_px)} px` : '');
    }
    // Net displacement vs path length is what separates a real shot from detector
    // jitter: a ball that ends where it started travelled a path without moving.
    row('gateNetPath', Number.isFinite(n.dense_net_displacement_px) || Number.isFinite(n.dense_path_length_px)
      ? `${Number.isFinite(n.dense_net_displacement_px) ? Number(n.dense_net_displacement_px).toFixed(1) : '—'} / ${Number.isFinite(n.dense_path_length_px) ? Number(n.dense_path_length_px).toFixed(1) : '—'} px` : '');
    row('gatePeakSpeed', Number.isFinite(n.dense_peak_speed_px_s)
      ? `${Math.round(n.dense_peak_speed_px_s)} px/s${Number.isFinite(n.dense_duration_s) ? ` · ${Number(n.dense_duration_s).toFixed(2)} s` : ''}` : '');
    row('gateMotion', Number.isFinite(n.window_motion) ? String(n.window_motion) : '');
    row('gateDup', (item.dup_count || 1) > 1 ? String(item.dup_count) : '');
    // Words first; the gate's own code stays in brackets, because it is the evidence
    // a report or a bug refers to.
    row('gateNotes', (gate.reasons || []).map(code => { const words = reasonText(code); return words === String(code) || !REASONS[code] ? words : `${words} (${code})`; }).join(' · '));
  }
  // Round 1: plain rows first; rows that are measurement plumbing (pixel positions, projection
  // source, the gate's raw notes and numbers) go under one "Technical details" disclosure.
  const technical = new Set(['ballLast', 'pocketAt', 'shotFrom', 'shotTo', 'projectedFrom', 'gateNotes', 'gateCensus', 'gateColourCensus', 'gateMove', 'gateGap', 'gateNetPath', 'gatePeakSpeed', 'gateMotion', 'gateDup']);
  const plain = rows.filter(r => !technical.has(r.key)).map(r => r.html), tech = rows.filter(r => technical.has(r.key)).map(r => r.html);
  const body = (plain.length ? `<ul class="vs-facts">${plain.join('')}</ul>` : '') +
    (tech.length ? `<details class="vs-tech"><summary>${esc(t('technicalDetails'))}</summary><ul class="vs-facts">${tech.join('')}</ul></details>` : '');
  return `${body}<p class="vs-note">${esc(item.projectable ? t('projectedNote') : t('notProjectable'))}</p>`;
}
function receiptLine(kind) {
  const row = (snap()?.receipts || []).find(r => r.key === kind);
  if (!row) return '';
  if (!row.at) return `<p class="vs-receipt pending">· ${esc(engineText(row.text))}</p>`;
  // A failed write is a red "!" line that never claims "Saved".
  if (row.error) return `<p class="vs-receipt error">! ${esc(engineText(row.text))}</p>`;
  const age = Math.max(0, (Date.now() - row.at) / 1000);
  return `<p class="vs-receipt" data-receipt-at="${row.at}">✓ ${esc(engineText(row.text))} · ${age.toFixed(1)} s ${esc(t('savedOk'))}</p>`;
}
// The footer's height is measured, never assumed: the scroll region reserves
// exactly that much (CSS var --vs-footer-h) so no row hides under it. The strip is
// measured the same way (--vs-strip-h): on a phone the sheet sits above it, never on it.
function syncFooterHeight() {
  const inspector = $('#vs-inspector'), footer = $('#vs-inspector-actions');
  const strip = $('#vs-strip');
  if (root && strip) {   // root is the mount, #vision-surface
    const stripHeight = `${strip.offsetHeight}px`;
    if (root.style.getPropertyValue('--vs-strip-h') !== stripHeight) root.style.setProperty('--vs-strip-h', stripHeight);
    // Where the 16:9 stage ends on screen: on a phone the bottom sheet must stop here,
    // not at a fixed 240 px, so it never covers the picture it is about.
    const frame = $('.vs-frame');
    if (frame) { const stageBottom = `${Math.round(frame.getBoundingClientRect().bottom + (typeof scrollY === 'number' ? scrollY : 0))}px`; if (root.style.getPropertyValue('--vs-stage-bottom') !== stageBottom) root.style.setProperty('--vs-stage-bottom', stageBottom); }
  }
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
// A Twitch VOD replay reaches the stage through the live path but is never called
// live: the server's own status (kind 'vod-replay') decides the word.
function liveWordKey(s) { return s.live?.source?.kind === 'vod-replay' || s.live?.replay?.kind === 'vod-replay' ? 'replayNow' : 'live'; }
function chipsHTML(s) {
  // Owner item 3: the Vision tab is the live stream. When the console says so, the chip row
  // offers live sources and nothing recorded - the datasets and the replay form belong to a
  // night's recorded review, whose only entrance is that night's row on Records.
  const liveOnly = !!opts.liveOnly?.(), fixed = !!opts.fixedClip?.();
  const channels = (fixed ? [] : (opts.channels() || [])).map(c => `<button class="vs-chip${s.source.kind === 'live' && s.source.channel === c.channel ? ' active' : ''}" data-vs-action="pick-live" data-vs-value="twitch:${esc(c.id)}">${s.source.kind === 'live' && s.source.channel === c.channel ? '● ' : ''}${esc(t('live'))} · twitch ${esc(c.channel || '')}</button>`).join('');
  const datasets = (liveOnly || fixed) ? '' : (s.datasets || []).map(d => `<button class="vs-chip${s.source.kind === 'vod' && d.id === s.dataset ? ' active' : ''}" data-vs-action="pick-dataset" data-vs-value="${esc(d.id)}">${esc(d.label || d.id)}</button>`).join('');
  const freshness = s.source.kind === 'live'
    ? `<span class="vs-fresh${s.live.stale ? ' stale' : ''}">${s.live.stale ? esc(t('stale')) : esc(t(liveWordKey(s)))} · ${esc(t('age'))} ${fmtAge(s.live.frame_age_ms)}</span>`
    : liveOnly ? `<span class="vs-fresh">${esc(t('live'))}</span>` : `<span class="vs-fresh">${esc(recordedLabel(s) || s.source.label)}</span>`;
  // The source settings hang off the chip row itself: one chip opens the panel
  // that used to be the rail's nothing-selected state, so the rail stays about
  // the selection and the settings are still one click away at any width.
  const chip = fixed ? '' : `<button class="vs-chip vs-source-chip${sourceOpen ? ' active' : ''}" data-vs-action="source-panel" aria-expanded="${sourceOpen ? 'true' : 'false'}" aria-controls="vs-source-panel" aria-label="${esc(t('sources'))}">${esc(t('sources'))}</button>`;
  const panel = sourceOpen ? `<div class="vs-source-panel" id="vs-source-panel" role="group" aria-label="${esc(t('sources'))}">
    <div class="vs-source-head"><strong>${esc(t('sources'))}</strong><button class="vs-source-close" data-vs-action="source-panel" aria-label="${esc(t('closePanel'))}">×</button></div>
    ${sourcePanelHTML(s)}</div>` : '';
  // Round 17, owner item 2: inference runs itself when the picture stops, so the stage reports what it
  // is doing and offers the one switch. The engine owns the run; this is its report.
  const corr = s.corrections || {};
  const infer = corr.inferRunning
    ? `<button class="vs-infer running" data-vs-action="auto-infer" data-vs-value="on" data-vs-role="infer-status">${esc(t('inferAutoRunning'))} · ${esc(String(corr.inferStatus || '').slice(0, 90))}</button>`
    : `<button class="vs-infer${corr.autoInfer === false ? ' off' : ''}" data-vs-action="auto-infer" data-vs-value="${corr.autoInfer === false ? 'on' : 'off'}" data-vs-role="infer-status">${esc(corr.autoInfer === false ? t('inferAutoOff') : t('inferAutoOn'))}</button>`;
  return `<div class="vs-chiprow" role="group" aria-label="${esc(t('dataset'))}">${chip}${datasets}${channels}</div>
  <div class="vs-chipmeta">${infer}${freshness}</div>${panel}`;
}
// Who made this candidate: one quiet line under the card's facts, never a badge.
// A machine-produced candidate says so in its own words (translated in 中); an
// event with no provenance block renders nothing at all - not "undefined".
function provenanceLine(event) {
  const p = event?.provenance;
  if (!p || typeof p !== 'object') return '';
  const parts = [];
  // Round 1: operators read the plain statement; the detector string (machine vocabulary) is kept one
  // step away - in the line's title and a visually hidden span - never removed.
  const detector = p.detector ? String(p.detector) : '';
  const statement = p.statement ? String(p.statement) : (p.machine_produced && !p.human_confirmed ? t('provenanceMachine') : '');
  if (statement) {
    const known = [COPY.en.provenanceMachine, COPY.zh.provenanceMachine, COPY.en.provenanceMachineLegacy, COPY.zh.provenanceMachineLegacy].includes(statement);
    parts.push(esc(known ? t('provenanceMachine') : statement));
  }
  if (p.human_confirmed) parts.push(esc(t('provenanceHuman')));
  if (!parts.length && !detector) return '';
  // the hidden detector span joins with a space, so the visible line ends on the statement, not on " · "
  const hidden = detector ? ` <span class="vs-sr-only">${esc(t('detectedBy'))}: ${esc(detector)}</span>` : '';
  return `<div class="vs-prov${p.human_confirmed ? ' confirmed' : ''}" data-vs-provenance="${p.human_confirmed ? 'human' : 'machine'}" title="${esc([detector ? `${t('detectedBy')}: ${detector}` : '', p.statement || ''].filter(Boolean).join(' · '))}">${parts.join(' · ')}${hidden}</div>`;
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
      ${provenanceLine(e)}
      <div class="vs-verbs">${['correct','wrong','unsure'].map(v => `<button class="${e.verdict === v ? 'active' : ''}" data-vs-action="verdict" data-vs-id="${esc(e.id)}" data-vs-value="${v}" title="${esc(t(v))}" aria-label="${esc(t(v))}">${{correct:'✓',wrong:'✗',unsure:'?'}[v]}</button>`).join('')}<span class="vs-verb-label">${esc(e.verdict ? t(e.verdict) : t('notReviewed'))}</span></div>
    </article>`).join('') : s.eventsAnalysed === false ? `<p class="vs-empty" data-vs-empty="not-scanned">${esc(t('bcEventsNone'))}</p>`
    : `<p class="vs-empty" data-vs-empty="${esc(emptyMarker(s.eventFilter))}">${esc(t(emptyReasonKey(s.eventFilter)))}</p>`;
  const crops = s.balls.items;
  const cropRows = crops.length ? crops.map(c => `<button class="vs-item${s.selection.crop && c.file === s.selection.crop.file ? ' selected' : ''}" data-vs-action="select-crop" data-vs-value="${esc(c.file)}"><span class="vs-mono">${esc(c.file)}</span><span class="vs-mono vs-dim">${esc(timecode(c.t))}</span><span class="vs-tag${c.label == null ? '' : ' done'}">${esc(c.label == null ? t('unlabeled') : labelText(c.label))}</span></button>`).join('') : `<p class="vs-empty">${esc(t('noCrops'))}</p>`;
  // Round 17, owner item 2: every human track carries the same labelling controls, in the list,
  // where the operator is looking - the same roster select and guest field the inspector shows for
  // the selected track, so one track type has one control set wherever it appears. A form control
  // cannot live inside a <button>, so the row is a div with the select action on its own button.
  // Round 17, owner item 3: the row shows who the pipeline says this track is, from the per-frame
  // identity record, so an operator sees the binding without opening the inspector - and sees when
  // a face box is the evidence for it.
  const roster = (opts?.regulars?.() || []);
  const identityFor = id => (s.persons.identity || []).find(p => String(p.track_id) === String(id)) || null;
  const tracks = s.persons.tracks.length ? s.persons.tracks.map(x => {
    const label = x.seed || x.label; const selected = String(s.persons.track) === String(x.id);
    const ident = identityFor(x.id);
    const who = ident && ident.player_id ? ((roster.find(r => String(r.id) === String(ident.player_id)) || {}).name || ident.player_id) : null;
    const sim = ident && ident.face_sim != null ? ` ${Number(ident.face_sim).toFixed(2)}` : '';
    const chip = who ? `<span class="vs-tag bound" data-vs-role="track-identity">${esc(who)}${esc(sim)}</span>`
      : ident && ident.face_bbox ? `<span class="vs-tag${' '}face" data-vs-role="track-identity">${esc(t('faceOnly'))}</span>`
      : '';
    return `<button class="vs-item vs-track${selected ? ' selected' : ''}" data-vs-action="select-track" data-vs-value="${esc(x.id)}"><span class="vs-mono">${esc(t('trackWord'))} ${esc(x.id)}</span>${chip}<span class="vs-tag${label ? ' done' : ''}${label && !isSeedRole(label) ? ' guest' : ''}">${esc(seedText(label) || '?')}</span></button>`;
  }).join('') : `<p class="vs-empty">${esc(t('noTracks'))}</p>`;
  return `<section class="vs-group${s.focus === 'events' ? ' focused' : ''}"><header><h3>${esc(t('events'))}</h3><span class="vs-mono">${esc(s.events.reviewed)} ${esc(t('reviewedWord'))}</span></header>
    <div class="vs-filters">${filters.map(([v, l]) => `<button class="vs-filter${s.eventFilter === v ? ' active' : ''}" data-vs-action="event-filter" data-vs-value="${v}">${esc(t(l))}</button>`).join('')}</div>${cards}</section>
  <section class="vs-group${s.focus === 'balls' ? ' focused' : ''}"><header><h3>${esc(t('queue'))}</h3><span class="vs-mono">${crops.length} ${esc(t('crops'))}</span></header>${cropRows}</section>
  <section class="vs-group${s.focus === 'persons' ? ' focused' : ''}"><header><h3>${esc(t('tracks'))}</h3>${s.persons.windows.length ? `<select id="vs-window">${s.persons.windows.map(w => `<option value="${esc(w.win)}" ${w.win === s.persons.win ? 'selected' : ''}>${esc(w.win)} · ${w.count}</option>`).join('')}</select>` : ''}</header>${tracks}</section>`;
}
function layersHTML(s) {
  // Round 21, owner item 6: the row is the four layers an operator switches while watching. The anchors
  // and events layers were toggles with nothing to toggle on a live or a recorded picture.
  const layers = [['cloth','cloth'],['balls','balls'],['persons','persons'],['pockets','pockets']];
  return layers.map(([key, label]) => {
    const gated = key === 'anchors' && s.dataset !== 'vod30';
    // F2: the anchors layer is on by default but empty until loaded; the chip says what is drawn.
    const shown = s.overlay[key] && !gated && (key !== 'anchors' || s.anchors.loaded);
    return `<button class="vs-layer${shown ? ' on' : ''}" aria-pressed="${shown ? 'true' : 'false'}" data-vs-action="layer" data-vs-value="${key}" ${gated ? 'disabled' : ''} title="${gated ? esc(t('vodOnlyAnchors')) : esc(t(label))}">${esc(t(label))}</button>`;
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
// An imported VOD is a recorded broadcast, never live: say whose and from when,
// and give times as broadcast time (range start + t).
function importedRow(s) { return s.source.kind === 'vod' ? (s.datasets || []).find(d => d.id === s.dataset && d.kind === 'vod') || null : null; }
function recordedLabel(s) {
  const d = importedRow(s); if (!d) return '';
  const span = d.range?.whole ? t('bcWhole') : `${hms(d.range?.start_s)}–${hms(d.range?.end_s)}`;
  return `${t('bcRecorded')} ${t('bcOf')} ${d.channel || '?'} · ${t('bcFrom')} ${String(d.created_at || '').slice(0, 10)} · ${span}`.replace(/\s+/g, ' ');
}
function factsLine(s) {
  const parts = [];
  const imported = importedRow(s);
  if (imported) parts.push(recordedLabel(s), `${t('bcAt')} ${hms((imported.range?.start_s || 0) + Number(s.frame.t || 0))}`);
  // One word per state: the strip says the same thing the chip says.
  if (s.source.kind === 'live') parts.push(`${(s.live.stale ? t('stale') : t(liveWordKey(s))).toLowerCase()}${s.live.seq != null ? ` · seq ${s.live.seq}` : ''}`, `${t('age')} ${fmtAge(s.live.frame_age_ms)}`, `${t('receive')} ${fmtAge(s.live.receive_to_result_ms)}`);
  // The frame's time in the same m:ss.d the cue cards use (25:53.5), not a bare second count.
  else parts.push(`${t('frameReadout')} ${s.frame.index}`, timecode(s.frame.t));
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
  // "stored inference" means a file an earlier run wrote, with its timestamp; a
  // polygon produced by inference run on this frame now is this session's and is
  // never called stored - that wording appears in exactly one place, here.
  const storedInference = s.corrections?.inferenceAt && s.corrections?.storedInference
    ? `${t('storedInference')} ${stampText(s.corrections.inferenceAt)}`
    : null;
  const clothLabel = layer('cloth', t('cloth').toLowerCase())
    + (cloth.polygon === 'inference' ? ` (${storedInference || t('inferenceSession')})` : '');
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
  else if (verdict.state === 'ok' && verdict.mean != null) parts.push(`${t('tableFits')} (${verdict.mean.toFixed(1)} px · ${t('tolerance')} ${Math.round(verdict.tolerance)} px)`);
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
  // A stored inference file is an earlier run's evidence; the cloth token above
  // already names it with its timestamp, and the box layer says the same thing in
  // the inspector. Nothing else on this line repeats it.
  if (storedInference && cloth.polygon !== 'inference' && (s.corrections?.modelBoxes ?? 0) > 0) parts.push(storedInference);
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
    <div class="vs-row"></div>
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
  const draft = replayDraft || {};
  const vodValue = draft.vod != null ? draft.vod : (chosen?.vod_id || '');
  const startValue = draft.start != null ? draft.start : String(chosen?.start_s ?? 0);
  const rateValue = draft.rate != null ? draft.rate : String(chosen?.rate ?? 1);
  const running = live.replay || (live.source && live.source.kind === 'vod-replay' ? live.source : null);
  const failed = live.attempt?.error && String(live.attempt.source || '').startsWith('vod-replay');
  const state = running ? `<p class="vs-mono" data-vs-replay="running">${esc(replaySelfDescription(running))}</p>`
    : failed ? `<p class="vs-mono" data-vs-replay="failed">${esc(t('vodFailed'))}: ${esc(live.attempt.error)}</p>`
    : chosen ? `<p class="vs-mono" data-vs-replay="chosen">${esc(t('vodChosen'))}: vod ${esc(chosen.vod_id)} · ${esc(t('vodStart'))} ${esc(chosen.start_s)} · ${esc(t('vodRate').split(' ')[0])} ×${esc(chosen.rate)} · ${esc(t('vodNotLive'))}</p>`
    : '';
  return `<div class="vs-block vs-replay"><h4>${esc(t('vodReplay'))}</h4>
    <label class="vs-field">${esc(t('vodId'))}<input name="vod" type="text" data-vs-field="vod" value="${esc(vodValue)}" placeholder="https://www.twitch.tv/videos/1234567890"></label>
    <div class="vs-row"><label class="vs-field">${esc(t('vodStart'))}<input name="start" type="number" data-vs-field="vod-start" min="0" step="1" value="${esc(startValue)}"></label><label class="vs-field">${esc(t('vodRate'))}<input name="rate" type="number" data-vs-field="vod-rate" min="0.25" max="4" step="0.25" value="${esc(rateValue)}"></label></div>
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
// The live detector ticks are the shell's: it holds what the operator ticked and
// sends exactly that on Start (the engine's live.detectors is never written).
function liveDetectorList(s) { return opts?.liveDetectors ? opts.liveDetectors() : (s.live.detectors || []); }
// ---- Broadcasts: import a past VOD of a saved channel (annotator/vod_import.py) ----
// The panel owns this small state; every number shown is the server's.
let bc = {recent: null, loading: false, error: '', form: null, estimate: null, job: null, poll: null, busy: false};
const hms = s => { const v = Math.max(0, Math.round(Number(s) || 0)); return `${Math.floor(v / 3600)}:${String(Math.floor(v % 3600 / 60)).padStart(2, '0')}:${String(v % 60).padStart(2, '0')}`; };
const sizeText = bytes => bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${(bytes / 1e6).toFixed(0)} MB`;
const minutesText = s => { const v = Math.max(0, Math.round(Number(s) || 0)); return v >= 600 ? `${Math.round(v / 60)} min` : v >= 60 ? `${Math.floor(v / 60)} min ${v % 60} s` : `${v} s`; };
// The one refusal the owner asked to have in both languages; any other server sentence is shown as sent.
function serverText(message) {
  const other = /^This VOD belongs to (\S+)\. Only saved channels can be analysed; add the channel under Source first\.$/.exec(String(message || ''));
  return other ? t('bcOtherChannel').replace('{channel}', other[1]) : String(message || '');
}
async function bcApi(path, body) {
  const response = await fetch(path, body === undefined ? {cache: 'no-store'} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  let data = null; try { data = await response.json(); } catch (_) { /* a non-JSON body is reported below */ }
  if (!response.ok || !data || data.error) throw new Error(serverText(data?.error) || `HTTP ${response.status}`);
  return data;
}
function bcRender() { sig.chips = null; render(); }
async function bcLoadRecent() {
  bc.loading = true; bc.error = ''; bcRender();
  try { bc.recent = await bcApi('/api/vods/recent'); } catch (error) { bc.error = error.message; }
  bc.loading = false; bcRender();
}
// The server's job, polled every second while it runs (an import started in another tab too).
async function bcPollJob() {
  const was = bc.job?.state;
  try { bc.job = await bcApi('/api/vods/job'); } catch (error) { bc.error = error.message; }
  const running = bc.job?.state === 'running';
  if (running && !bc.poll) bc.poll = setInterval(bcPollJob, 1000);
  if (!running && bc.poll) { clearInterval(bc.poll); bc.poll = null; }
  if (was === 'running' && bc.job?.state === 'done') { await engine()?.reloadDatasets?.(); bcLoadRecent(); }
  bcRender();
}
function bcWatch() { bcPollJob(); }
// Round 10, owner item 3: importing a broadcast imports all of it. The estimate asks the same
// question the download will, so the size on this screen is the size of the file that arrives;
// the start and the length that used to sit between those two facts are gone.
async function bcEstimate() {
  const form = bc.form || {};
  bc.busy = true; bc.error = ''; bc.estimate = null; bcRender();
  try { bc.estimate = await bcApi(`/api/vods/estimate?vod=${encodeURIComponent(form.vod)}`); } catch (error) { bc.error = error.message; }
  bc.busy = false; bcRender();
}
async function bcImport() {
  const e = bc.estimate; if (!e) return bcEstimate();   // nothing estimated yet: show the size first
  bc.busy = true; bc.error = ''; bcRender();
  try {
    bc.job = await bcApi('/api/vods/import', {vod: e.vod_id});
    bc.form = null; bc.estimate = null; bcWatch();
  } catch (error) { bc.error = error.message; }
  bc.busy = false; bcRender();
}
async function bcCancel() {
  if (!confirm(t('bcCancelAsk'))) return;
  try { bc.job = await bcApi('/api/vods/cancel', {confirm: true}); } catch (error) { bc.error = error.message; }
  bcPollJob();
}
async function bcDelete(id) {
  if (!confirm(t('bcDeleteAsk'))) return;
  try { const done = await bcApi('/api/vods/delete', {id, confirm: true}); opts.notice?.(done.message); await engine()?.reloadDatasets?.(); bcLoadRecent(); }
  catch (error) { bc.error = error.message; bcRender(); }
}
function bcJobHTML() {
  const job = bc.job;
  if (!job || job.state === 'idle') return '';
  const running = job.state === 'running';
  const facts = running
    ? [`${Number(job.percent || 0).toFixed(1)}%`, `${job.mb ?? 0} ${t('bcMb')}`, job.rate_mb_s ? `${job.rate_mb_s} MB/s` : '', job.eta_s != null ? `${minutesText(job.eta_s)} ${t('bcEta')}` : ''].filter(Boolean).join(' · ')
    : (job.error || job.message || job.state);
  const bar = running ? `<progress max="100" value="${esc(Number(job.percent || 0))}" aria-label="${esc(`${t('bcAria')} ${job.id}`)}"></progress>` : '';
  return `<div class="vs-channel vs-bc-job" data-vs-bc-job="${esc(job.state)}" role="status" aria-live="polite"><span class="vs-mono">${esc(t('bcJob'))} ${esc(job.id || '')}: ${esc(serverText(facts))}</span>${bar}${running ? `<button data-vs-action="bc-cancel" aria-label="${esc(t('bcCancel'))}">${esc(t('bcCancel'))}</button>` : ''}</div>`;
}
function bcFormHTML() {
  const form = bc.form; if (!form) return '';
  const e = bc.estimate;
  const span = e ? (e.range.whole ? t('bcWhole') : `${hms(e.range.start_s)}–${hms(e.range.end_s)}`) : '';
  const eta = e ? (e.eta_s != null ? `${t('bcTime')} ${minutesText(e.eta_s)}` : t('bcTimeUnknown')) : '';
  const summary = e ? `<p class="vs-mono" data-vs-bc-estimate="${esc(e.id)}">${esc(e.channel)} · ${esc(span)} · ${esc(t('bcSize'))} ${esc(sizeText(e.estimate_bytes))}, ${esc(eta)} · ${esc(sizeText(e.disk.free_bytes))} ${esc(t('bcFree'))}${e.already_imported ? ` · ${esc(t('bcAlready'))}` : ''}</p>${e.disk.ok ? '' : `<p class="vs-mono vs-bc-refusal">${esc(e.disk.refusal)}</p>`}` : '';
  return `<div class="vs-bc-form" data-vs-bc-form="${esc(form.vod)}">
    <p class="vs-mono">vod ${esc(form.vod)}${form.title ? ` · ${esc(form.title)}` : ''}</p>
    ${summary}
    <div class="vs-row"><button data-vs-action="bc-estimate"${bc.busy ? ' disabled' : ''}>${esc(t('bcEstimate'))}</button>${e && e.disk.ok && !e.already_imported ? `<button class="primary" data-vs-action="bc-import"${bc.busy ? ' disabled' : ''}>${esc(t('bcConfirm'))} · ${esc(sizeText(e.estimate_bytes))}</button>` : ''}<button data-vs-action="bc-close">${esc(t('bcCancelForm'))}</button></div></div>`;
}
function broadcastsBlock(s) {
  if (bc.recent == null && !bc.loading && !bc.error) setTimeout(bcLoadRecent, 0);
  if (bc.job == null) { bc.job = {state: 'idle'}; setTimeout(bcPollJob, 0); }
  const rows = (bc.recent?.channels || []).map(channel => {
    if (!channel.vods) return `<p class="vs-mono vs-bc-refusal" data-vs-bc-channel="${esc(channel.channel)}">${esc(channel.channel)}: ${esc(t('bcError'))} — ${esc(channel.error)}</p>`;
    if (!channel.vods.length) return `<p class="vs-empty">${esc(channel.channel)}: ${esc(t('bcNone'))}</p>`;
    return channel.vods.map(v => `<div class="vs-channel" data-vs-bc-vod="${esc(v.id)}"><span class="vs-mono">${esc(channel.channel)} · ${esc(String(v.created_at || '').slice(0, 10))} · ${esc(hms(v.length_s))} · ${esc(v.title || '')}${v.imported.length ? ` · ${esc(t('bcImported'))} ${esc(v.imported.length)}` : ''}</span><button data-vs-action="bc-open" data-vs-value="${esc(v.id)}" aria-label="${esc(`${t('bcImport')} ${channel.channel} ${v.title || v.id}`)}">${esc(t('bcImport'))}</button></div>`).join('');
  }).join('');
  const imported = (s.datasets || []).filter(d => d.kind === 'vod').map(d => `<div class="vs-channel" data-vs-bc-dataset="${esc(d.id)}"><span class="vs-mono">${esc(d.label)}${d.title ? ` · ${esc(d.title)}` : ''}</span><button data-vs-action="bc-delete" data-vs-value="${esc(d.id)}" aria-label="${esc(`${t('bcDelete')} ${d.label}`)}">${esc(t('bcDelete'))}</button></div>`).join('');
  return `<div class="vs-block vs-broadcasts" role="group" aria-label="${esc(t('bcTitle'))}"><h4>${esc(t('bcTitle'))}</h4>
    <p class="vs-note">${esc(t('bcNote'))}</p>
    ${bc.loading ? `<p class="vs-note">${esc(t('bcLoading'))}</p>` : rows}
    ${bcFormHTML()}
    <div class="vs-row"><label class="vs-field">${esc(t('bcPaste'))}<input type="text" data-vs-field="bc-paste" value="${esc(bc.paste || '')}" placeholder="https://www.twitch.tv/videos/1234567890"></label><button data-vs-action="bc-paste">${esc(t('bcPasteGo'))}</button><button data-vs-action="bc-refresh">${esc(t('bcRefresh'))}</button></div>
    ${bcJobHTML()}
    ${bc.error ? `<p class="vs-mono vs-bc-refusal" role="alert">${esc(bc.error)}</p>` : ''}
    ${imported}</div>`;
}
function sourcePanelHTML(s) {
  // Owner item 3 again, this time inside the panel: on the live tab there is no broadcast list,
  // no replay form and no dataset block - a recorded surface here would be the thing the owner
  // asked to remove. The live state block, the channels and the detectors stay.
  const liveOnly = !!opts.liveOnly?.();
  const attempt = s.live.attempt && s.live.attempt.error ? `<div class="vs-error-block"><h4>${esc(t('startFailed'))}</h4><p class="vs-mono">${esc(t('attemptSource'))}: ${esc(s.live.attempt.source || '—')}</p><p class="vs-mono">${esc(s.live.attempt.error)}</p><p>${esc(t('remedy'))}: ${esc(t('remedyText'))}</p><button data-vs-action="live-start">${esc(t('retry'))}</button></div>`
    // A stopped session's failure is history: a muted line saying so, never the red box.
    : s.live.last_error?.error ? `<p class="vs-note" data-vs-last-live-error>${esc(t('lastLiveError').replace('{at}', s.live.last_error.at ? new Date(s.live.last_error.at * 1000).toTimeString().slice(0, 5) : '—'))}: ${esc(s.live.last_error.error)}</p>` : '';
  const vodRows = liveOnly ? '' : (opts.vods?.() || []).map(v => `<div class="vs-channel"><span class="vs-mono">${esc(v.url)}</span><button data-vs-action="use-saved-vod" data-vs-value="${esc(v.video)}">${esc(t('useInForm'))}</button><button data-vs-action="forget-channel" data-vs-id="${esc(v.id)}">${esc(t('remove'))}</button></div>`).join('');
  const channels = (opts.channels() || []).map(c => `<div class="vs-channel"><span class="vs-mono">${esc(c.url)}</span><button data-vs-action="pick-live" data-vs-value="twitch:${esc(c.id)}">${esc(t('select'))}</button><button data-vs-action="forget-channel" data-vs-id="${esc(c.id)}">${esc(t('remove'))}</button></div>`).join('');
  const live = s.live;
  // A start that failed must not leave the row reading "idle": the row states
  // the failure with the same vocabulary the running/stopped states use.
  const liveFailed = !!(live.error || live.attempt?.error);
  const liveRowState = liveFailed && live.state !== 'running' && live.state !== 'starting' ? 'error' : live.state;
  return `${attempt}
  ${liveOnly ? '' : broadcastsBlock(s)}
  ${liveOnly ? '' : replayBlock(s)}
  <div class="vs-block${liveOnly ? ' vs-live-hidden' : ''} vs-dataset-block"><h4>${esc(t('dataset'))}</h4><div class="vs-chiprow">${(s.datasets || []).map(d => `<button class="vs-chip${s.source.kind === 'vod' && d.id === s.dataset ? ' active' : ''}" data-vs-action="pick-dataset" data-vs-value="${esc(d.id)}">${esc(d.label || d.id)}</button>`).join('')}</div>
    <p class="vs-mono">${esc(s.source.kind === 'vod' ? s.source.label : '—')} · ${esc(t('frameCount'))} ${esc(s.frame.count)}</p></div>
  <div class="vs-block"><h4>${esc(t('liveState'))}</h4>
    <p class="vs-mono" id="vs-live-status">${esc(stateText(liveRowState))}${(live.error || live.attempt?.error) ? ` · ${esc(live.error || live.attempt.error)}` : ''} · ${esc(t('age'))} ${fmtAge(live.frame_age_ms)} · ${esc(t('receive'))} ${fmtAge(live.receive_to_result_ms)} · ${esc(t('dropped'))} ${esc(live.skipped ?? 0)}</p>
    <div class="vs-row"><button class="primary" data-vs-action="live-start">${esc(t('start'))}</button><button data-vs-action="live-stop">${esc(t('stop'))}</button></div>
    <div class="vs-chiprow">${channels}${liveOnly ? '' : (s.datasets || []).map(d => `<button class="vs-chip" data-vs-action="pick-live" data-vs-value="dataset:${esc(d.id)}">${esc(d.label || d.id)}</button>`).join('')}</div>
    <div class="vs-row">${['table','person','ball'].map(d => `<label class="vs-check" title="${d === 'ball' ? esc(t('liveBallNote')) : esc(t(d))}"><input type="checkbox" data-vs-action="live-detector" data-vs-value="${d}" ${liveDetectorList(s).includes(d) ? 'checked' : ''}> ${esc(d === 'ball' ? t('liveBall') : t(d))}</label>`).join('')}</div>
    <p class="vs-note" data-vs-live-ball="note">${esc(t('liveBallNote'))}</p>
    ${liveStageLine(s)}
    <p class="vs-note">${esc(t('latency'))}</p></div>
  <div class="vs-block"><h4>${esc(t('detectors'))}</h4><div class="vs-row">${[['table','table'],['person','person'],['balls','ball']].map(([k, l]) => `<label class="vs-check"><input type="checkbox" data-vs-action="detector" data-vs-value="${k}" ${s.detectors[k] ? 'checked' : ''}> ${esc(t(l))}</label>`).join('')}</div><p class="vs-note">${esc(t('detectorReason'))}</p></div>
  <div class="vs-block"><h4>${esc(t('saved'))}</h4>${channels || `<p class="vs-empty">—</p>`}${vodRows ? `<h4>${esc(t('savedVods'))}</h4>${vodRows}` : ''}
    <div class="row vs-source-actions"><button data-vs-action="open-sources">${esc(t('sourcesTitle'))}</button></div></div>`;
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
// Round 19, owner item 8: the label box is one piece of markup with two homes. It sits in the
// inspector when the label column has room, and as an overlay on the video when a track is picked -
// which is the moment the operator wants the picture at its largest and the field at hand.
// Round 19, owner item 8: while a track is picked, the label box floats over the video, so the picture
// keeps the whole stage and the field sits where the operator is looking. The overlay element is created
// here if the surface does not provide one, which keeps the stage markup the engine's business.
function paintLabelOverlay(s) {
  if (typeof document === 'undefined') return;
  let host = document.querySelector('#vs-label-overlay');
  if (!host) {
    const grid = document.querySelector('.vs-grid');
    if (!grid) return;
    host = document.createElement('div');
    host.id = 'vs-label-overlay';
    host.className = 'vs-label-overlay';
    host.setAttribute('role', 'group');
    grid.appendChild(host);
  }
  const html = labelBoxHTML(s);
  if (host.innerHTML !== html) host.innerHTML = html;
  host.hidden = !html;
  const inspector = document.querySelector('#vs-inspector');
  if (inspector && inspector.classList) inspector.classList.toggle('label-moved', !!html);
  // The shell narrows the label column while the overlay is up, so the stage keeps the width.
  const shell = document.querySelector('#ops-shell');
  if (shell && shell.setAttribute) shell.setAttribute('data-label-overlay', html ? '1' : '0');
}
function labelBoxHTML(s) {
  // Round 19, owner item 8: one piece of markup with two homes - the inspector when the label column
  // has room, and an overlay on the video the moment a track is picked, when the picture matters most.
  const pickedPerson = s.selection?.kind === 'person' || (s.persons.track !== null && s.persons.track !== undefined);
  if (!pickedPerson) return '';
  const facts = bindingFacts(s);
  const roster = (opts?.regulars?.() || []);
  const picked = facts.identity ? facts.identity.id : '';
  const guestValue = facts.guest ? facts.label.raw : (guestDraft && String(guestDraft.track) === String(s.persons.track) ? guestDraft.value : '');
  const options = [`<option value=""${picked ? '' : ' selected'}>${esc(t('guestOption'))}</option>`]
    .concat(roster.map(row => `<option value="${esc(row.id)}"${String(row.id) === picked ? ' selected' : ''}>${esc(row.name)}${row.rating != null ? ` · ${esc(row.rating)}` : ''}${row.statusText && row.status && row.status !== 'Active' ? ` · ${esc(row.statusText)}` : ''}</option>`));
  const guestOff = !!picked;
  return `  <div class="vs-block vs-labelblock">
    <label class="vs-field">${esc(t('whichRegular'))}<select data-vs-action="regular" ${roster.length ? '' : 'disabled'}>${options.join('')}</select></label>
    <label class="vs-field${guestOff ? ' vs-guest-off' : ''}" data-vs-role="guest-field">${esc(t('guestName'))}<input type="text" data-vs-action="guest-name" maxlength="60" value="${esc(guestValue)}" placeholder="${esc(t('guestPlaceholder'))}" ${guestOff ? 'disabled' : ''}></label>
    <p class="vs-note" data-vs-role="bind-hint">${esc(bindHint(facts, picked))}</p>
  </div>`;
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
  ${labelBoxHTML(s)}
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
// A stored result's time in the operator's language: 2026-09-16 04:07 (the same in 中),
// not the browser's default locale, which printed '9/16/2026, 4:07:48 AM' inside Chinese copy.
const stampText = value => { if (!value) return ''; const at = new Date(value); if (Number.isNaN(at.getTime())) return String(value); const p = n => String(n).padStart(2, '0'); return `${at.getFullYear()}-${p(at.getMonth() + 1)}-${p(at.getDate())} ${p(at.getHours())}:${p(at.getMinutes())}`; };
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
  if (kind === 'box') return `<button class="primary" data-vs-action="save-corrections">${esc(t('saveCorrections'))}</button>`;
  // Nothing selected: the live start/stop pair moved into the Source panel with
  // the rest of the source settings, so this footer only carries the frame's own
  // pending write.
  return s.dirty ? `<button class="primary" data-vs-action="save-corrections">${esc(t('saveCorrections'))}</button>` : '';
}
function inspectorHTML(s) {
  const kind = s.selection.kind;
  const body = kind === 'event' ? eventBlock(s) : kind === 'ball' ? ballBlock(s) : kind === 'person' ? personBlock(s) : kind === 'anchor' ? anchorBlock(s) : kind === 'box' ? boxBlock(s) : emptyRailBlock(s);
  // The channel on the stage: the processor's own status names it (the shell's frame
  // label only knows the Source picker, which can still read the dataset).
  const channel = s.source.kind === 'live' ? (s.live.source?.kind === 'twitch' && s.live.source.channel) || s.source.channel : null;
  const liveChat = channel && opts.chat();
  const chat = liveChat ? `<div class="vs-chat"><iframe title="${esc(t('twitchChat'))}" src="https://www.twitch.tv/embed/${esc(channel)}/chat?parent=${esc(location.hostname)}&darkpopout"></iframe></div>` : '';
  const chatToggle = channel ? `<button class="vs-chat-toggle" data-vs-action="chat">${esc(opts.chat() ? t('hideChat') : t('showChat'))}</button>` : '';
  const close = kind === 'none' ? '' : `<button class="vs-close" data-vs-action="deselect" aria-label="${esc(t('closePanel'))}">×</button>`;
  const notice = s.notice.text ? `<div class="vs-notice${s.notice.error ? ' error' : ''}" role="status">${esc(engineText(s.notice.text))}</div>` : '';
  return `${chat}${chatToggle}${close}${notice}${body}`;
}
// ---- rendering -----------------------------------------------------------
function render() {
  const s = snap();
  if (!root || !s) return;
  const chips = chipsHTML(s);
  if (chips !== sig.chips) {
    const node = $('#vs-chips');
    if (node) {
      // The panel is rebuilt whenever the live status changes (every poll). A field
      // the operator is typing in keeps its focus and its caret on top of keeping
      // its value in replayDraft, so typing an id is never interrupted.
      const active = typeof document !== 'undefined' ? document.activeElement : null;
      const keep = active && node.contains && node.contains(active) && active.dataset
        ? (active.dataset.vsField || active.dataset.vsAction || active.id || null) : null;
      const caret = keep && typeof active.selectionStart === 'number' ? active.selectionStart : null;
      node.innerHTML = chips; sig.chips = chips;
      if (keep) {
        const again = node.querySelector(`[data-vs-field="${keep}"], [data-vs-action="${keep}"], #${keep}`);
        if (again) { if (again.focus) again.focus(); if (caret != null && again.setSelectionRange) again.setSelectionRange(caret, caret); }
      }
    } else { sig.chips = chips; }
  }
  const railSig = `${s.focus}|${s.eventFilter}|${s.events.index}|${s.events.items.map(e => `${e.id}:${e.verdict}`).join(',')}|${s.balls.items.length}|${s.balls.index}|${s.selection.crop?.file || ''}|${s.persons.win}|${s.persons.tracks.map(x => `${x.id}:${x.seed || ''}`).join(',')}|${s.persons.track || ''}|${s.events.reviewed}|${opts.lang}`;
  if (railSig !== sig.rail) { const node = $('#vs-cues'); if (node) node.innerHTML = railHTML(s); sig.rail = railSig; }
  const layersSig = `${s.dataset}|${s.anchors?.loaded ? 1 : 0}|${Object.entries(s.overlay).map(([k, v]) => `${k}${v ? 1 : 0}`).join('')}`;
  if (layersSig !== sig.layers) { const node = $('#vs-layers'); if (node) node.innerHTML = layersHTML(s); sig.layers = layersSig; }
  const identity = identityHTML(s);
  if (identity !== sig.identity) { const node = $('#vs-identity'); if (node) node.innerHTML = identity; sig.identity = identity; }
  // The identity block reads the saved seed and the track's binding, so both
  // belong in the signature: a save must repaint the block that saved it.
  const insSig = `${s.selection.kind}|${s.selection.event?.id || ''}|${s.selection.crop?.file || ''}|${s.selection.crop?.label ?? ''}|${s.selection.track ?? ''}|${s.selection.person?.cluster_id ?? ''}|${s.selection.person?.player_id ?? ''}|${s.selection.person?.bound_evidence?.source ?? ''}|${(s.persons.tracks || []).find(x => String(x.id) === String(s.persons.track))?.seed ?? ''}|${s.enroll?.status || ''}|${s.enroll?.payload?.token || ''}|${s.enroll?.payload?.reason || ''}|${s.enroll?.elapsed_ms == null ? '' : Math.round(s.enroll.elapsed_ms / 1000)}|${s.selection.anchor ?? ''}|${s.selection.box ?? ''}|${s.corrections.tool}|${s.corrections.boxLabel || ''}|${s.corrections.newBoxLabel || ''}|${s.corrections.inferStatus}|${s.corrections.result}|${s.corrections.manualBoxes ?? ''}/${s.corrections.modelBoxes ?? ''}|${s.persons.status}|${s.live.state}|${s.live.error || ''}|${s.live.attempt?.at || ''}|${s.live.detectors.join(',')}|${s.notice.text}|${s.busy}|${s.dataset}|${s.source.kind}|${s.source.channel || ''}|${s.live.source?.channel || ''}|${(s.receipts || []).map(r => `${r.key}:${r.at}`).join(',')}|${opts.lang}`;
  if (insSig !== sig.inspector) {
    paintLabelOverlay(s);
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
  // Accessible names follow the language toggle too (data-vs-aria names the COPY key).
  root.querySelectorAll('[data-vs-aria]').forEach(node => { const copy = t(node.dataset.vsAria); if (node.getAttribute('aria-label') !== copy) node.setAttribute('aria-label', copy); });
  const frameField = $('#vs-frame-index');
  if (frameField) { const max = String(Math.max(0, s.frame.count - 1)); if (frameField.getAttribute('max') !== max) frameField.setAttribute('max', max); frameField.disabled = s.source.kind === 'live'; }
  // The strip is the VOD timeline; a live edge has no frame index to step.
  const liveStrip = s.source.kind === 'live';
  const strip = $('#vs-strip'); if (strip) strip.dataset.live = liveStrip ? '1' : '0';
  root.querySelectorAll('[data-vs-action="step"],[data-vs-action="freeze"],[data-vs-action="play"],#vs-scrub').forEach(node => { node.disabled = liveStrip; });
  syncFooterHeight();
  const grid = $('.vs-grid'); if (grid) grid.dataset.sheet = sheet;
  root.querySelectorAll('[data-sheet-tab]').forEach(b => { const on = b.dataset.sheetTab === sheet; b.classList.toggle('active', on); b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', String(on)); });
  if (!ageTimer) ageTimer = setInterval(receiptAge, 1000);
}
// ---- actions -------------------------------------------------------------
function act(action, value, node) {
  const target = engine();
  const s = snap();
  const num = Number(value);
  // A control inside a track row belongs to that row's track, not to whichever track happened to
  // be selected, so the row selects its own track before the action is interpreted.
  const rowTrack = node?.dataset?.vsTrack;
  if (rowTrack && ['regular','guest-name','seed'].includes(action) && String(snapshot().persons?.track ?? '') !== String(rowTrack)) {
    // selectTrack() inside this call sets the selection synchronously; the loads it starts are
    // awaited by the engine, and the action below reads the selection, so nothing needs to wait here.
    const switching = target.selectTrackAndSeek(rowTrack);
    if (switching && switching.catch) switching.catch(() => {});
  }
  switch (action) {
    case 'pick-dataset': target.setDataset(value); break;
    case 'bc-refresh': bcLoadRecent(); bcPollJob(); break;   // an import started elsewhere shows up too
    case 'bc-open': { const vod = (bc.recent?.channels || []).flatMap(c => c.vods || []).find(v => v.id === value); bc.form = {vod: value, title: vod?.title || ''}; bc.estimate = null; bc.error = ''; bcEstimate(); break; }
    case 'bc-paste': { const vod = String(bc.paste || '').trim(); if (!vod) { root.querySelector('[data-vs-field="bc-paste"]')?.focus(); break; } bc.form = {vod, title: ''}; bc.estimate = null; bc.error = ''; bcEstimate(); break; }
    case 'bc-estimate': bcEstimate(); break;
    case 'bc-import': bcImport(); break;
    case 'bc-close': bc.form = null; bc.estimate = null; bc.error = ''; bcRender(); break;
    case 'bc-cancel': bcCancel(); break;
    case 'bc-delete': bcDelete(value); break;
    case 'pick-live': opts.pickLive(value); break;
    case 'live-start': opts.startLive(); break;
    case 'live-stop': opts.stopLive(); break;
    case 'forget-channel': opts.forgetChannel(node.dataset.vsId); break;
    case 'open-sources': opts.openSources?.(); break;
    case 'auto-infer': opts.setAutoInference?.(String(node?.dataset?.vsValue || 'on') === 'on'); break;
    case 'use-saved-vod': { replayDraft = {...(replayDraft || {}), vod: `https://www.twitch.tv/videos/${value}`}; render(); root.querySelector('[data-vs-field="vod"]')?.focus(); break; }
    case 'live-detector': { const list = new Set(liveDetectorList(s)); if (node.checked) list.add(value); else list.delete(value); opts.setLiveDetectors([...list]); break; }
    case 'pick-replay': {
      // A VOD id or URL, where in it to start, and how fast: the server resolves it
      // and the panel reports the capture's own kind/live/rate/drift afterwards.
      const field = name => (root.querySelector(`[data-vs-field="${name}"]`) || {}).value || '';
      const vod = String(field('vod')).trim();
      if (!vod) { opts.notice?.(t('vodIdNeeded')); root.querySelector('[data-vs-field="vod"]')?.focus(); break; }
      replayDraft = {vod, start: field('vod-start'), rate: field('vod-rate')};
      opts.pickReplay({vod_id: vod, start_s: Number(field('vod-start')) || 0, rate: Number(field('vod-rate')) || 1});
      break;
    }
    case 'detector': target.setDetector(value, node.checked); break;
    case 'layer': {
      // F2: the Anchors chip reads off until anchors are loaded, so its first click loads them.
      const on = value === 'anchors' && s.overlay.anchors && !s.anchors.loaded ? true : target.toggleOverlay(value);
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
  if (!root || (root.contains && !root.contains(event.target))) return;
  const target = event.target;
  const guest = target.closest ? target.closest('[data-vs-action="guest-name"]') : null;
  if (guest) { guestDraft = {track: String(snap()?.persons?.track ?? ''), value: guest.value}; return; }
  const field = target.dataset?.vsField;
  if (field === 'bc-paste') { bc.paste = target.value; return; }
  if (field) { replayDraft = {...(replayDraft || {}), [field === 'vod' ? 'vod' : field === 'vod-start' ? 'start' : 'rate']: target.value}; }
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
  if (event.target.id === 'vs-scrub') {
    // R22 item 3: a seek that the engine refuses used to end in render(), and the render rebuilds the
    // input from the console's markup - measured: the thumb snapped back to 0, so a chosen point could
    // not be kept. The chosen value is put back after the repaint.
    const want = Number(event.target.value);
    if (!engine().seek(want)) { render(); const scrub = $('#vs-scrub'); if (scrub) scrub.value = String(want); }
    return;
  }
}
function attach(options) {
  opts = options; root = options.mount;
  sig = {}; // the shell rebuilds #main on every render: never trust cached regions
  const footer = root.querySelector('#vs-inspector-actions');
  if (footerObserver) { footerObserver.disconnect(); footerObserver = null; }
  if (footer && typeof ResizeObserver !== 'undefined') {
    footerObserver = new ResizeObserver(syncFooterHeight); footerObserver.observe(footer);
    const strip = root.querySelector('#vs-strip'); if (strip) footerObserver.observe(strip);
    const frame = root.querySelector('.vs-frame'); if (frame) footerObserver.observe(frame);
  }
  root.addEventListener('click', onClick);
  root.addEventListener('change', onChange);
  root.addEventListener('input', onInput);
  const unsubscribe = engine()?.subscribe ? engine().subscribe(render) : null;
  render();
  return {render, detach() { if (unsubscribe) unsubscribe(); root.removeEventListener('click', onClick); root.removeEventListener('change', onChange); root.removeEventListener('input', onInput); }};
}
window.VisionStage = {attach, render, act, onInput, actionsHTML, factsLine, identityHTML, chipsHTML, inspectorHTML, quadReason, quadDetail, gateEvidence, eventGeometry, tierBadge, railHTML, bindingFacts, sourcePanelHTML, emptyRailBlock, seedText, syncGuestField};
// The Broadcasts block, for tests: its state, the renderers and the refusal mapping.
Object.assign(window.VisionStage, {broadcastsBlock, recordedLabel, serverText, bcState: () => bc, bcReset: () => { if (bc.poll) clearInterval(bc.poll); bc = {recent: null, loading: false, error: '', form: null, estimate: null, job: null, poll: null, busy: false}; }});
})();
