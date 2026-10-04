'use strict';
(() => {
const $=s=>document.querySelector(s), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const words={shotTimer:['Shot timer','出杆计时'],lastWrite:['Last write · revision {n}','上次写入 · 版本 {n}'],connectionLost:['OFFLINE · edits will not save','离线 · 改动不会保存'],sceneIdle:['Nothing on the tables yet','还没有赛事'],startNight:['Start tonight','开始今晚'],startNightGo:['Start tonight →','开始今晚 →'],startEvent:['Start the event →','开赛 →'],sendNext:['Send next → T{table}','派下一场 → T{table}'],tablesBody:['Tables','球台'],tableFree:['free','空闲'],records:['History','历史赛事'],sheetBackRecords:['Back to records','返回战绩档案'],vision:['Vision','视觉'],players:['Regulars','常客'],status:['Back room','后台'],loading:['Loading…','读取中…'],start:['Start','开始'],pause:['Pause','暂停'],reset:['Reset','重置'],signed:['Cards signed','已签赛果'],next:['Up next','下一场'],entrants:['Entrants','参赛名单'],guests:['Guests tonight','今晚访客'],empty:['Nothing here yet.','暂无记录。'],open:['Tables open','球台空闲'],pending:['Waiting','待定'],scheduled:['Racked','已排定'],live:['On table','进行中'],delayed:['Delayed','延迟'],complete:['Signed','已签'],registration:['Registration','报名中'],finished:['Finished','已结束'],table:['Table','球台'],race:['Race to','抢几'],single:['Single frame','单局'],win:['Win frame','赢得本局'],clear:['Clear score','清空比分'],save:['Save','保存'],sign:['Sign scorecard','签署赛果'],send:['Send to table','安排上台'],forfeit:['Forfeit','弃权'],night:['The night','今晚赛事'],event:['Event name','赛事名称'],format:['Format','赛制'],singles:['Singles','单打'],doubles:['Doubles','双打'],tables:['Tables','球台数量'],locked:['The draw has started. Entrants and rules are locked. Archive the event from the Event settings card to start a new one.','赛事已开始，参赛名单和规则已锁定。请在「赛事设置」卡片归档本场并新建赛事。'],reg:['Registration desk','报名台'],member:['Regular','常客'],guest:['Guest','访客'],pick:['Choose a regular','选择常客'],guestName:['Guest name','访客姓名'],partner:['Partner','搭档'],add:['Add entrant','添加参赛者'],remove:['Remove','移除'],rack:['Rack the night','生成对阵并开赛'],rackHint:['Single elimination. Byes advance automatically. Registration order seeds the draw.','单败淘汰，轮空自动晋级，按报名顺序排列。'],guestNote:['Guests can enter without a player profile. Add them to the regulars later.','访客无需球员档案即可报名，之后可转为常客。'],new:['Archive & new event','归档并新建赛事'],newConfirm:['Archive this event and create a fresh registration? Existing results remain in history.','归档本次赛事并创建新报名？已有赛果将保留在历史记录中。'],scorecard:['Scorekeeper’s card','记分员赛果单'],match:['Match','比赛'],scoreA:['Side A score','甲方比分'],scoreB:['Side B score','乙方比分'],winner:['Winner','胜者'],round:['Round','轮次'],standings:['House standings','球房排名'],timeline:['Night log','赛事日志'],refresh:['Refresh','刷新'],search:['Search names','搜索姓名'],deskSearch:['Type to find a regular','输入以查找常客'],searchCount:['{n} of {m}','{n} / {m}'],all:['Everyone','全部'],Active:['Active','活跃'],Visitor:['Visitor','访客'],Prospect:['Newcomer','新会员'],Inactive:['Inactive','停用'],rating:['House rating (manual)','球房评分（手动）'],name:['Name','姓名'],playerStatus:['Status','状态'],newPlayer:['New regular','添加常客'],editPlayer:['Edit regular','编辑常客'],deletePlayer:['Delete regular','删除常客'],enrollFace:['Enroll face','录入人脸'],enrollHint:['Choose a clear frontal photo of the player. The face model runs on this machine only.','请选择该球员清晰的正面照片。人脸模型仅在本机运行。'],enrollSubmit:['Enroll photo','录入照片'],enrollDone:['face(s) enrolled','张人脸已录入'],enrollFail:['Enrollment failed','人脸录入失败'],faceForget:['Delete face data','删除人脸数据'],faceForgetConfirm:['Delete all face data of this regular? This removes every enrolled face photo embedding, the face samples stored for the people matched to them, and those matches. The regular\'s name and results stay. This cannot be undone.','删除该常客的全部人脸数据？将删除所有已录入的人脸特征、与其匹配人物保存的人脸样本以及这些匹配。姓名和成绩保留。此操作无法撤销。'],faceForgetDone:['Face data deleted','人脸数据已删除'],faceForgetFail:['Face data was not deleted','人脸数据未删除'],deleteConfirm:['Delete this player? Players in event records cannot be deleted.','删除此球员？已关联赛事的球员无法删除。'],promote:['Add to regulars','加入常客'],activeMembers:['Active members','活跃会员'],average:['Average house rating (manual)','平均球房评分（手动）'],played:['Played','场次'],winPct:['Win %','胜率'],eventTable:['Event table','本场战绩表'],allTime:['All signed results, every event. The house rating is typed in by staff, not computed.','所有赛事的已签赛果。球房评分由工作人员手动填写，并非计算得出。'],logged:['Recorded results','已记录赛果'],wins:['Wins','胜场'],losses:['Losses','负场'],winRate:['Win rate','胜率'],joined:['Joined','加入时间'],notMeasured:['Not measured','尚未采集'],source:['Twitch source URL','Twitch 来源地址'],sourceHint:['Use https://www.twitch.tv/channel or https://www.twitch.tv/videos/123. Twitch playback is separate from local video analysis.','使用 https://www.twitch.tv/channel 或 https://www.twitch.tv/videos/123。Twitch 播放与本地视频分析相互独立。'],sourceAdd:['Save source','保存来源'],showChat:['Show chat','显示聊天'],hideChat:['Hide chat','隐藏聊天'],external:['Open on Twitch ↗','在 Twitch 打开 ↗'],liveLabel:['TWITCH CHANNEL · LIVE STATUS UNVERIFIED','TWITCH 频道 · 直播状态未核验'],vodLabel:['TWITCH VOD · RECORDED VIDEO','TWITCH 回放 · 录制视频'],noSource:['No Twitch source configured. Add a source below.','尚未配置 Twitch 来源，请在下方添加。'],twitchNote:['Twitch controls playback and availability. No tracking, scoring, or camera health is inferred from this embed.','播放和可用性由 Twitch 控制。此嵌入不提供追踪、自动计分或摄像头健康状态。'],review:['Local VOD review & analysis','本地回放复核与分析'],openReview:['Open review workbench ↗','打开复核工作台 ↗'],loadReview:['Load review workbench','载入复核工作台'],area:['Area','模块'],now:['Now','当前'],notes:['Operator notes','运营备注'],note:['Note','备注'],addNote:['Add note','添加备注'],revision:['State revision','数据版本'],persist:['Persisted operations API','持久化运营接口'],manual:['Manual, validated scoring','人工录入并校验比分'],notConnected:['Not connected','未连接'],observation:['Live observations / auto-referee','实时观测 / 自动裁判'],noSimulation:['No simulated observations or fabricated statistics are shown.','不显示模拟观测或虚构统计。'],saved:['Saved.','已保存。'],conflict:['Another operator changed the data. Latest state loaded; inspect it before submitting again.','其他操作员已更改数据。已载入最新状态，请核对后重新提交。'],confirmSign:['Sign this result? Completed cards are immutable and advance the winner.','签署此赛果？签署后无法修改，胜者将晋级。'],confirmForfeit:['Record a forfeit for this side and advance the opponent?','记录此方弃权并让对手晋级？'],local:['Local operations · manual scoring · real persisted data','本地运营 · 人工计分 · 真实持久化数据'],error:['Action failed','操作失败'],select:['Select…','请选择…'],noMatch:['No match on table','暂无进行中比赛'],unknown:['Unknown','未知'],history:['Archived events','已归档赛事'],randomPair:['Random pairing','随机配对'],pairHint:['Random draw of partners only; results are never drawn. Solo sign-ups are paired, shown with the seed, and count only when you accept.','只随机决定搭档，比赛结果从不抽签。单人报名者会被配对并显示种子，采用后才计入报名。'],soloAdd:['Add solo player','添加单人报名'],pairDraw:['Pair at random','随机配对搭档'],pairNeedEven:['An even number of solo players is needed.','需要偶数名单人报名者。'],pairSeed:['seed {seed}','种子 {seed}'],pairAccept:['Use these teams','采用这些组合'],pairReroll:['Re-roll','重新抽签'],pairClear:['Back to the list','返回名单'],secondChance:['Second chance','复活赛'],revivalHint:['Random draw, not a result: one round-1 loser who played is drawn to fill a bye; the bye’s holder must now play them. Signed results never change.','随机抽签，不是赛果：从实际比赛的首轮负者中抽出一人填补轮空位，轮空者需与其比赛。已签赛果不会改变。'],revivalDraw:['Draw a round-1 loser','抽取一名首轮负者'],revivalDrawn:['Drawn: {name}','抽中：{name}'],revivalPool:['Pool: {names}','候选：{names}'],revivalSeed:['seed {seed}','种子 {seed}'],revivalAttempt:['Draw {n}','第 {n} 次抽签'],revivalRedrawn:['Redrawn after an undo — earlier draws are in the audit log','撤销后重抽——之前的抽签记录在日志里'],revivalSoFar:['Draws so far: {n} — each one is in the audit log','已抽签 {n} 次——每次都记录在日志里'],revivalLine:['Second chance (random draw, not a result): {name} · seed {seed} · draw {n}','复活赛（随机抽签，不是赛果）：{name} · 种子 {seed} · 第 {n} 次抽签'],revivalUndo:['Undo the draw','撤销抽签'],confirmRevival:['Draw one round-1 loser at random to re-enter the bracket in a bye slot? The draw is recorded with its seed; no result changes.','随机抽取一名首轮负者，以轮空位重新进入对阵？抽签连同种子会被记录，任何赛果都不会改变。'],confirmRevivalUndo:['Undo this second-chance draw? The slot goes back to a bye; no signed result is touched.','撤销这次复活抽签？该空位将恢复为轮空，签过的赛果不受影响。'],deleteEvent:['Delete event','删除赛事'],hideEvent:['Hide from history','从历史中隐藏'],unhideEvent:['Show in history','恢复显示'],hiddenTag:['Hidden from history. Results and stats still count.','已从历史中隐藏，赛果与统计仍然计入。'],showHiddenN:['Show {n} hidden','显示 {n} 场已隐藏'],hideHidden:['Hide hidden events','收起已隐藏赛事'],confirmDelete:['Delete “{name}”? No result was signed in it. This cannot be undone.','删除“{name}”？该赛事没有已签赛果。此操作无法撤销。'],confirmHide:['Hide “{name}” from history? Its results and every player’s stats stay; you can show it again.','将“{name}”从历史中隐藏？赛果和所有球员统计都会保留，之后可以恢复显示。'],confirmUnhide:['Show “{name}” in history again?','重新在历史中显示“{name}”？'],resultsSheet:['Results sheet','赛果单'],tbd:['TBD','待定'],raceN:['Race to {n}','抢{n}'],sheetBack:['Back to matches','返回对阵'],printSheet:['Print / save as PDF','打印 / 存为 PDF'],copyResults:['Copy results as text','复制赛果文字'],copied:['Results copied. Paste them into the group chat.','赛果已复制，可粘贴到群聊。'],copyFail:['This browser did not allow copying. Select the text and copy it by hand.','浏览器不允许复制，请手动选中文字复制。'],champion:['Champion','冠军'],championLine:['Champion: {c}','冠军：{c}'],noChampion:['Champion: not decided yet','冠军：尚未决出'],notDecided:['Not decided yet','尚未决出'],final:['Final','决赛'],byeLine:['{a}: bye (advances, not a win)','{a}：轮空晋级（不计胜场）'],forfeitLine:['{w} wins by forfeit vs {l}','{l} 弃权，{w} 晋级'],notPlayedLine:['{a} vs {b}: not played yet','{a} 对 {b}：尚未比赛'],sheetNote:['Signed results only. A bye advances a player but is not a win.','仅含已签赛果。轮空晋级不计为胜场。'],playerRecord:['Player record','球员战绩'],recordScope:['Signed results in {n} events since {date}. Read-only.','自 {date} 起 {n} 场赛事的已签赛果。只读。'],perEvent:['By event','分场战绩'],wl:['W–L','胜–负'],headToHead:['Head-to-head','交手记录'],h2hNote:['Played matches only: byes are left out and forfeits are counted apart, never as a win or a loss.','只统计实际对局：轮空不计，弃权单独列出，不计胜负。'],opponent:['Opponent','对手'],sample:['Sample (matches)','样本（场）'],guestByName:['guest, matched by name','访客，按姓名匹配'],tonight:['tonight','本场'],back:['Back to profile','返回档案'],renameEvent:['Rename event','重命名赛事'],renameArchived:['New name for this archived event (the results do not change):','为这场已归档赛事输入新名称（赛果不会改变）：'],unnamed:['Unnamed event','未命名赛事'],dayEventsOne:['{n} event','{n} 场赛事'],dayEvents:['{n} events','{n} 场赛事'],dayVodsOne:['{n} broadcast','{n} 段直播'],dayVods:['{n} broadcasts','{n} 段直播'],reviewImport:['Import this broadcast','导入这段直播'],reviewVodNote:['No night in the log uses this broadcast yet. If its footage is already on this machine, the chips above open it; otherwise they are the datasets this console is configured with. Import it and its own footage arrives for marking.','日志里还没有哪一晚使用这段直播。如果这台机器上已有它的素材，上面的标签可以直接打开；否则它们是服务器已配置的数据集。导入之后，它自己的素材就会进来供标注。'],archiveNote:['Every video this channel exposes, newest first, one row per day. Open any card to review its footage; a night enters the log below only when an import finishes. Nothing is inferred from the picture or the title.','该频道公开的全部视频，最新的在最前，每天一行。点开任意卡片即可审看画面；只有导入完成后，才会有新的一晚写入下方日志。画面和标题都不会被自动推断。'],archiveReading:['Reading the archive…','正在读取视频列表…'],archiveNone:['No videos for the saved channels yet.','已存频道还没有视频。'],archiveFailed:['The archive could not be read','回放列表读取失败'],archiveRetry:['Try again','重试'],vodMark:['Covers an event','已关联赛事'],vodOwn:['Known to this console','本机记录的直播'],vodLinks:['Broadcasts','直播回放'],vodLinkOpen:['Link a broadcast','关联直播'],vodEventOpen:['Link an event','关联赛事'],vodLinkSearch:['Search broadcasts','搜索直播'],vodEventSearch:['Search events','搜索赛事'],vodLinkNone:['No broadcast is linked to this night yet.','这一晚还没有关联任何直播。'],vodEventNone:['No night is linked to this broadcast yet.','这段直播还没有关联任何赛事。'],vodLinkEmpty:['Every broadcast this box knows is already linked here.','这台机器知道的直播都已关联到这里。'],vodEventEmpty:['Every night is already linked to this broadcast.','每一晚都已关联到这段直播。'],vodUnlink:['Unlink','取消关联'],vodLinkedBadge:["This night's own import",'本晚自己的导入'],vodTonight:['Tonight','今晚'],vodWord:['Broadcast','直播回放'],autoDownload:['Automatic download','自动下载'],autoOn:['running','运行中'],autoPaused:['paused','已暂停'],autoPause:['Pause','暂停'],autoResume:['Resume','继续'],autoQueued:['{n} queued','队列 {n}'],autoDone:['{n} done','已完成 {n}'],autoNow:['now {id}','正在 {id}'],autoSkipped:['{n} skipped','跳过 {n}'],autoFailed:['The download queue could not be read','无法读取下载队列'],autoReading:['Reading the download queue…','正在读取下载队列…'],liveStream:['Live stream','直播'],liveNow:['Live','直播中'],person:['Person','人物'],ball:['Ball','球'],detectors:['Detectors','检测器'],sources:['Sources','来源'],stop:['Stop','停止'],livePanelNote:['Start the stream and this tab becomes the live workbench. Recorded nights are reviewed from their row on Records.','开始直播后，这个标签页就是直播工作台。已结束的夜晚请从战绩档案里对应那一行进入审看。'],liveNoChannel:['Add the club channel under Source on Tonight, then come back and start the stream.','先在“今晚赛事”的来源里加上俱乐部频道，再回来开始直播。'],reviewTitle:['Review a recorded night','审看已录制的夜晚'],reviewFromRecords:['Recorded footage is opened from a night on Records - never from this tab.','录制素材一律从战绩档案里的某一晚进入，不在这个标签页打开。'],reviewBack:['Back to Records','返回战绩档案'],reviewFootage:['footage · the configured datasets','素材 · 已配置的数据集'],reviewBroadcast:['broadcast','直播'],reviewNote:['This screen steps through the broadcast’s own footage when this machine has it; otherwise the datasets the server is configured with, named in the chips above.','这台机器上有该场直播自己的素材时，这里逐帧审看的就是它；否则是服务器已配置的数据集，上面的标签会写明。'],archiveCount:['{n} broadcasts · {built} linked to an event','{n} 段直播 · {built} 段已关联赛事'],archiveKind:['Recording','录像'],kindArchive:['Broadcast','直播回放'],kindHighlight:['Highlight','精选'],kindUpload:['Upload','上传'],archiveMore:['There are more than {n}; this box lists the newest {n}.','回放多于 {n} 条，这里只列出最新的 {n} 条。'],archiveNoSource:['No Twitch channel is saved yet, so there is nothing to list. Add one on the Back room tab.','还没有保存 Twitch 频道，暂时没有可列出的回放。请在「后台」页添加。']}
Object.assign(words,{playerNotes:['Player notes','球员备注'],releaseTable:['Release table','释放球台'],appearance:['Table appearance','球台外观'],cloth:['Cloth color','台呢颜色'],lamp:['Lamp glow','灯光强度'],diamonds:['Rail diamonds','球台菱形标记'],publicBoard:['Public board: on/off','公网记分板：开/关'],appearanceNote:['Decorative table preview only — not a camera observation.','仅为球台装饰预览，并非摄像头观测。'],greenCloth:['Green','绿色'],blueCloth:['Blue','蓝色'],redCloth:['Burgundy','酒红色'],grayCloth:['Slate','灰色'],serviceError:['The service rejected this request. Technical detail:','服务未接受此请求。技术详情：'],rosterRatingBase:['over {n} rated, {m} unrated','按 {n} 位已评级的常客统计，{m} 位未评级'],rosterTitle:['Roster','常客名册'],visionLoading:['Loading the review workspace…','正在加载复核工作区…'],visionCues:['Vision cues','视觉线索'],visionStage:['Vision stage','视觉舞台'],visionInspector:['Vision inspector','视觉检查器'],visionPanels:['Vision panels','视觉面板'],visionCuesTab:['Cues','线索'],visionInspectorTab:['Inspector','检查器'],visionFrame:['Frame','帧'],visionPrev:['Previous frame','上一帧'],visionNext:['Next frame','下一帧'],visionFreeze:['Freeze','冻结'],visionPlay:['Play','播放'],forMaintainers:['For maintainers','维护人员'],forMaintainersNote:['System status and the product roadmap. Not needed to run a night.','系统状态与产品路线图。日常运营无需查看。'],systemStatus:['System status','系统状态'],systemStatusNote:['What this installation does today, and where its data is saved.','本系统当前能做什么，以及数据保存在哪里。'],scoreboardTitle:['Scoreboard','记分板'],focusMatch:['Match being scored (switch tables)','正在计分的比赛（切换球台）'],boardEmptyNoDraw:['No match is on a table. Register the entrants and rack the night first.','暂无比赛上台。请先登记参赛者并生成对阵。'],boardEmptySend:['No match is on a table. The next match is ready and can be sent to a free table.','暂无比赛上台。下一场比赛已排定，可安排到空闲球台。'],boardEmptyWait:['No match is on a table. The next match is waiting for its players (the round before must finish).','暂无比赛上台。下一场比赛在等待选手（上一轮需先结束）。'],goMatches:['Open Matches','打开对阵'],goSetup:['Open Register','打开登记'],goRegulars:['Open Regulars','打开常客'],noneScheduled:['none scheduled','暂无待上台比赛'],defaultNameNote:['default name · saved when you rack','默认名称 · 生成对阵时保存'],bracketTitle:['Bracket','对阵表'],emptyScorecard:['Appears when a match is on a table: its score can then be typed here and signed.','有比赛上台后出现，可在此录入比分并签署。'],emptyBracket:['The bracket appears once the night is racked. Register at least two entrants, then Rack.','生成对阵后显示对阵表。请先登记至少两名参赛者，然后生成对阵。'],emptyTable:['Appears when a match is on a table: send one from the Queue.','有比赛上台后出现：请从“队列”安排上台。'],emptyEventTable:['Fills with each signed result tonight (byes are not counted).','今晚每签署一场结果即更新（轮空不计）。'],emptyStandings:['Lists every regular once they are added in Regulars; results count once they are signed.','在“常客”中添加常客后列出；签署的结果计入战绩。'],emptyNightLog:['Every saved change is logged here, newest first: registrations, scores, signatures.','每次保存的更改都记录在此（最新在上）：报名、比分、签署。'],emptyHistory:['Archived nights appear here after “Archive & new event” in Set up.','在“开赛设置”中“归档并新建赛事”后，已归档的赛事显示在此。'],emptyEntrants:['No one is registered yet. Add a regular or a guest with the form above.','尚无人报名。请用上方表单添加常客或访客。'],emptyPool:['No solo sign-ups yet.','尚无单人报名。'],emptyPerEvent:['No signed results yet. Each night this player plays appears here.','尚无已签署结果。该球员参加的每晚比赛会显示在此。'],emptyH2H:['No played matches yet. Opponents appear once a result is signed.','尚无已完成比赛。签署结果后会列出对手。'],emptyRoster:['No regulars yet. Add the first one; guests can be promoted later.','尚无常客。请添加第一位；访客之后也可转为常客。'],emptyRosterFiltered:['No regular matches this search or filter.','没有符合搜索或筛选条件的常客。'],emptyGuests:['Guests registered tonight can be added to the regulars here.','今晚报名的访客可在此转为常客。'],savingNow:['saving…','保存中…'],netRolledBack:['Not saved: the network did not answer. The score is back to what the server last confirmed.','未保存：网络无响应。比分已恢复为服务器最后确认的值。'],auditGoneEntrant:['an entrant who was removed','已移除的参赛者'],auditSource:['a source','一个来源'],auditMatch:['a match','一场比赛'],auditGonePlayer:['a player who was removed','已删除的球员'],auditNote:['a note','一条备注'],cardExpand:['Show the full card','展开完整卡片'],cardCollapse:['Hide the details','收起详情'],closeLabel:['Close','关闭'],guestNeeded:['Type a guest name or choose a regular.','请输入访客姓名，或选择一位常客。'],notBlank:["Fill this in — spaces alone don't count.",'请填写此项，仅有空格不算。'],photoSize:['Choose a photo of 8 MB or less.','请选择不超过 8 MB 的照片。'],photoType:['Choose an image file (JPEG or PNG).','请选择图片文件（JPEG 或 PNG）。'],bye:['Bye','轮空'],placeholderName:['Byes are added by the draw automatically. Type the guest’s real name.','轮空由抽签自动安排，请输入访客的真实姓名。'],tonightTab:['Tournament','赛事'],eventSettings:['Event settings','赛事设置'],startNote:['Name the night and start. The draw sends matches to free tables; nothing is inferred.','给今晚命名并开始。对阵会分到空闲球台，一切都不做推断。']});
// Owner round 2: one language per label, one word per concept, and the two search boxes name their own scope.
Object.assign(words,{searchRecords:['Search the records','搜索赛事记录'],searchRoster:['Search the regulars roster','搜索常客名单'],backfillShort:['Backfill','补录'],bfPickNote:['Choose the broadcast that covers the night, then mark the games that were actually played. Nothing is inferred.','选择覆盖当晚的直播，然后标注实际进行的比赛。不做任何推断。'],closeNoEvent:['Nothing to end yet: no event has been set up.','还没有可结束的赛事。'],closeSigned:['Delete is off because a result is signed; archiving keeps the results in the history.','已有赛果签署，删除已关闭；归档会把赛果保留在历史中。'],closeNoEntrants:['Delete is off: this event has no entrants and no signed result yet.','删除已关闭：本场赛事还没有参赛者，也没有签署的赛果。'],digitKey:['Digit {n}','数字键 {n}'],keyHint:['Shortcut: {key} switches to this tab','快捷键：{key} 切换到本页'],keyHintTimer:['Shortcut: {key} starts or pauses the shot timer','快捷键：{key} 开始或暂停出杆计时'],timerBall:['Ball {n} · shot timer','{n} 号球 · 出杆计时']});
Object.assign(words,{reviewWhy:['About this broadcast','关于这场直播'],sourcesTitle:['Twitch sources','Twitch 来源'],sourcesNote:['Save the club channel and the VOD links the console reads. Twitch playback is separate from the local analysis.','保存控制台要读取的俱乐部频道与 VOD 链接。Twitch 播放与本地分析相互独立。'],sourcesEmpty:['No Twitch source saved yet.','还没有保存 Twitch 来源。'],kindChannel:['Live channel','直播频道'],kindVod:['Recorded video','录像回放'],openTable:['Open its scoreboard','打开记分板'],bracketSigned:['{n}/{m} signed','已签 {n}/{m}'],bracketLive:['{n} on table','进行中 {n}'],bracketDelayed:['{n} delayed','延迟 {n}'],bracketSend:['{n} to send','待上台 {n}']});
let lang=localStorage.getItem('cp-ops-lang')||'en',theme=localStorage.getItem('cp-ops-theme')||'dark',tab='tonight',data=null,busy=false,selected=null,query='',filter='',focusId=null,chat=true,sourceId=null,reviewPromise=null,visionAdapter=null,visionAttempt=null,recordId=null,sheetId=null,showHidden=false,setupOpen=false;
// ---- Records: one Windows-style timeline of past events (docs/console-redesign.md 5),
// and the VOD backfill that writes one (7). The night log is no longer a panel of its
// own - it is the footnote of the night it belongs to - and the house standings moved
// onto each row of Regulars (6), where resultStats() stays the only algorithm.
Object.assign(words,{
  events:['Events','历史赛事'],auditTrail:['This night’s log','这一晚的流水'],auditRest:['Other saved changes (not archived yet)','尚未归档的其他改动'],houseRecord:['House record','球房战绩'],
  nightSummary:['{players} players · champion {name}','{players} 人 · 冠军 {name}'],sourceLine:['Source: Twitch VOD {id} · {range}','来源：Twitch VOD {id} · {range}'],
  noRecord:['—','—'],unknownDate:['Date unknown','日期不详'],allHidden:['All {n} events are hidden','{n} 场赛事全部被隐藏'],
  signedLine:['{n} signed','{n} 场签完'],byeCount:['{n} byes','{n} 场轮空'],hiddenBadge:['Hidden','已隐藏'],
  tlExpand:['Expand','展开'],tlCollapse:['Collapse','收起'],emptySearch:['Nothing matches this search','没有符合条件的赛事'],
  backfill:['Backfill from a VOD','用 VOD 补录'],backfillOpen:['Backfill a past event from a Twitch VOD…','用 Twitch VOD 补录一场历史赛事…'],
  bfStep:['Step {n} of 5','步骤 {n}/5'],bfExit:['Leave the backfill','退出补录'],bfPickTitle:['Which broadcast?','选哪一段'],
  bfPaste:['VOD link or id','回放链接或 id'],bfCheck:['Check','检查'],bfVerifyTitle:['Estimate the download','估算大小'],
  bfStartAt:['Start at (h:mm:ss)','起点（时:分:秒）'],
  bfEstimate:['Estimate','估算大小'],bfEstimateLine:['About {size} · {free} free on disk · {reuse}','约 {size} · 磁盘剩余 {free} · {reuse}'],
  bfReuse:['this range is already downloaded','这一段已经下载过'],bfUseImported:['Skip the download — use the file already here','跳过下载 —— 直接用已下载的文件'],bfStartImport:['Start the download','开始导入'],
  bfImporting:['Downloading the broadcast','正在下载这场回放'],bfCancel:['Cancel the download','取消下载'],
  bfWait:['Wait for it','等它跑完'],bfBusy:['An import is already running. Wait for it, or cancel it.','正有一个导入在跑。等它跑完，或取消它。'],
  bfUploaded:['Recorded broadcast, downloaded once','已下载的回放'],bfWhichNight:['Which night was this?','这是哪一晚？'],
  bfNightName:['Event name','赛事名'],bfStartMarking:['Start marking','开始标记'],bfMarkStart:['This match starts here','这一场从这里开始'],
  bfMarkEnd:['This match ends here','这一场到这里结束'],bfMarked:['{n} matches marked by you','你已标记 {n} 场'],
  bfReviewTitle:['Confirm each match','逐场确认'],bfWinner:['Winner','胜者'],bfScore:['Final score','最终比分'],
  bfPlayer1:['Player one','球员一'],bfPlayer2:['Player two','球员二'],bfConfirmMatch:['I watched this — confirm','我看过了 —— 确认这场'],
  bfConfirmed:['Confirmed','已确认'],bfUnconfirmed:['{n} matches still unconfirmed','还有 {n} 场未确认'],
  bfCommit:['Write this night to Records','把这一晚写进战绩档案'],bfDone:['This night is in Records','这一晚已写进战绩档案'],
  bfOpenTimeline:['Open the timeline','看时间线'],bfOpen:['Open it','打开它'],bfRetry:['Retry','重试'],
  bfOther:['Pick another broadcast','换一段直播'],
  bfHonest:['Every result below was typed and confirmed by a person. Nothing here was detected automatically.','下面每一条赛果都由人工输入并逐场确认。没有任何一条是自动识别出来的。'],
  bfManual:['You mark every match by hand. Nothing is detected from the video.','每一场都由你手动标记，视频里没有任何自动识别。'],
  bfLinkedCount:['{n} of {m} names are regulars: their results count towards their house standing. The rest are guests and count towards nobody.','{m} 个名字中有 {n} 个是常客：他们的成绩计入球房排名；其余按访客处理，不计入任何人的排名。'],
  bfSameVod:['This range is already in the console. Open it, or pick another range.','这一段已经在控制台里了。打开它，或换一段。'],
  bfLeft:['The draft is on this device. The download keeps running without this page.','草稿保存在本机。离开这个页面下载会继续。'],
  bfChannel:['Add this channel under Back room first, or pick a saved channel.','请先在后台添加这个频道，或换一个已保存的频道。'],
  bfNoVods:['No recent broadcasts for the saved channels','已存频道没有最近的回放'],bfPick:['Use this one','选这段'],
  bfNeedVod:['Paste a VOD link or id first','请先粘贴回放链接或 id'],bfNeedMarks:['Mark at least one match first','请先标记至少一场'],
  bfMarkOrder:['The end must come after the start','结束时间必须晚于开始时间'],bfToReview:['Confirm each match →','逐场确认 →'],
  bfBackMarking:['Back to marking','返回标记'],bfUnmark:['Remove','删除'],bfIncomplete:['Every match needs both players, the winner and the score.','每一场都需要两位球员、胜者和比分。'],
  bfResumePrompt:['Continue the marks from last time ({n} matches)?','继续上次的标记（{n} 场）？'],bfResumeYes:['Continue','继续'],bfResumeNo:['Start over','重新开始'],
  bfFailedTitle:['The download stopped','下载中断'],bfRejectedTitle:['This range cannot be imported','这一段无法导入'],
  bfDiskNo:['Not enough free disk space for this range.','磁盘空间不足，装不下这一段。'],
  backfillSource:['Source: Twitch VOD {id} · {range} · confirmed match by match','来源：Twitch VOD {id} · {range} · 逐场人工确认'],signOffLine:['Confirmed match by match · {at}','逐场人工确认 · {at}'],
  backfillOpenVod:['Open the broadcast','打开回放']});
let bf=null,eventsQuery='',openEvents=new Set();
const BF_DRAFT='cp-ops-backfill',BF_STEPS={pick:1,verify:2,importing:3,dataset:4,marking:4,review:5,done:5,failed:2,rejected:2};
const MONTHS=[['January','一月'],['February','二月'],['March','三月'],['April','四月'],['May','五月'],['June','六月'],['July','七月'],['August','八月'],['September','九月'],['October','十月'],['November','十一月'],['December','十二月']];
const WEEKDAYS=[['Sun','周日'],['Mon','周一'],['Tue','周二'],['Wed','周三'],['Thu','周四'],['Fri','周五'],['Sat','周六']];
const dateLine=at=>{const d=new Date(at);return Number.isNaN(d.getTime())?String(at??''):d.toLocaleString(lang==='zh'?'zh-CN':'en')};
const monthLabel=d=>lang==='zh'?MONTHS[d.getMonth()][1]:MONTHS[d.getMonth()][0];
const dayLabel=d=>`${d.getMonth()+1}/${d.getDate()} ${WEEKDAYS[d.getDay()][lang==='zh'?1:0]}`;
const hms=value=>{const s=Math.max(0,Math.floor(Number(value)||0));return `${Math.floor(s/3600)}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`};
const sizeText=bytes=>Number(bytes)>=1e9?`${(Number(bytes)/1e9).toFixed(1)} GB`:`${Math.round(Number(bytes)/1e6)} MB`;
const eventDate=night=>{const d=new Date(night?.archivedAt);return isNaN(d)?null:d};
const bfValue=(selector,fallback)=>{const value=$(selector)?.value;return value===undefined||value===null?fallback:value};
// ---- Records timeline --------------------------------------------------------------------
function timelineNights(){
  return (data.history||[]).filter(n=>showHidden||!n.hidden).slice().sort((a,b)=>{
    const da=eventDate(a),db=eventDate(b);
    if(da&&db&&da-db)return db-da;
    if(da&&!db)return -1;
    if(!da&&db)return 1;
    return String(b.id).localeCompare(String(a.id))})}
function eventNames(night){return [night.name||'',...(night.entrants||[]).flatMap(e=>(e.members||[]).map(m=>player(m.pid)?.name||m.name||''))]}
// R13, word by word: every word must hit the event name or one of the people in it.
function eventMatchesQuery(night,text){const parts=searchFold(text).split(' ').filter(Boolean);if(!parts.length)return true;const names=eventNames(night);return parts.every(part=>names.some(name=>nameMatches(name,part)))}
function auditOf(night){const ids=new Set([night.id,...(night.matches||[]).map(m=>m.id),...(night.entrants||[]).map(e=>e.id)]);return (data.events||[]).filter(e=>e.context&&ids.has(e.context.id))}
// The night log of a night is a footnote of that night (5.4). Changes that belong to no
// archived night - tonight's own edits, a player rename, a source - keep their one
// collapsed footnote at the end of the timeline: the facts stay, they just stop being a
// third panel on Records.
function auditRest(){const known=new Set();for(const night of (data.history||[])){known.add(night.id);for(const m of night.matches||[])known.add(m.id);for(const e of night.entrants||[])known.add(e.id)}return (data.events||[]).filter(e=>!(e.context&&known.has(e.context.id)))}
function auditList(list){return list.length?`<ol class="audit">${list.slice().reverse().map(e=>`<li${auditTitle(e)?` title="${esc(auditTitle(e))}"`:''}>${esc(auditLine(e))}</li>`).join('')}</ol>`:`<p class="muted">${esc(t('emptyNightLog'))}</p>`}
function auditFold(list,label,extra=''){return `<details class="tl-audit${extra}"><summary>${esc(label)} (${list.length})</summary>${auditList(list)}</details>`}
function eventSide(night,id){const e=(night.entrants||[]).find(x=>x.id===id);if(!e)return null;return (e.members||[]).map(m=>player(m.pid)?.name||m.name||t('unknown')).join(' / ')}
function sheetSummary(night){const list=night.matches||[];if(!list.length)return '';const rounds=[...new Set(list.map(m=>m.round))].sort((a,b)=>a-b),line=r=>list.filter(m=>m.round===r).map(m=>resultLine(night,m)).join(' · ');return rounds.length>1?`${roundTitle(night,rounds[0])}: ${line(rounds[0])} … ${roundTitle(night,rounds.at(-1))}: ${line(rounds.at(-1))}`:`${roundTitle(night,rounds[0])}: ${line(rounds[0])}`}
function eventItem(night){
  const date=eventDate(night),open=openEvents.has(night.id),list=night.matches||[],signed=list.filter(m=>['played','forfeit'].includes(m.result)).length,byes=list.filter(isBye).length,c=champion(night),audit=auditOf(night);
  const tally=[t('signedLine').replace('{n}',signed),byes?t('byeCount').replace('{n}',byes):''].filter(Boolean).join(' · ');
  return `<li class="tl-item${night.hidden?' is-hidden':''}" data-event="${esc(night.id)}">
  <div class="tl-row">
    <span class="tl-date">${date?esc(dayLabel(date)):esc(t('unknownDate'))}</span>
    <span class="tl-title grow">${esc(quoted(night))}<small>${esc(t('nightSummary').replace('{players}',(night.entrants||[]).length).replace('{name}',c||'—'))} · ${esc(tally)}</small></span>
    ${night.source?`<button type="button" class="badge tl-source-badge" data-action="backfill-open">${esc(t('backfill'))}</button>`:''}
    ${night.hidden?`<span class="badge">${esc(t('hiddenBadge'))}</span>`:''}
    <button type="button" class="tl-toggle" data-action="tl-toggle" data-id="${esc(night.id)}" aria-expanded="${open}" aria-controls="tl-body-${esc(night.id)}">${esc(t(open?'tlCollapse':'tlExpand'))}</button>
  </div>
  <div class="tl-body" id="tl-body-${esc(night.id)}"${open?'':' hidden'}>
    ${list.length?`<p class="tl-sheet muted">${esc(sheetSummary(night))}</p>`:''}
    <div class="row">${btn(t('resultsSheet'),'results-sheet',`data-id="${esc(night.id)}"`)}${btn(t('copyResults'),'copy-results',`data-id="${esc(night.id)}"`)}</div>
    ${night.source?`<p class="tl-source">${esc(t('backfillSource').replace('{id}',night.source.vodId).replace('{range}',`${hms(night.source.startS)}–${hms(night.source.endS)}`))} · <a href="https://www.twitch.tv/videos/${encodeURIComponent(String(night.source.vodId))}" target="_blank" rel="noopener">${esc(t('backfillOpenVod'))}</a></p>`:''}
    ${eventLinks(night)}
    ${night.signOff?`<p class="muted">${esc(t('signOffLine').replace('{at}',dateLine(night.signOff.at)))}</p>`:''}
    <div class="row">${btn(t('renameEvent'),'rename-archived',`data-id="${esc(night.id)}"`)}${night.hidden?btn(t('unhideEvent'),'event-hide',`data-id="${esc(night.id)}" data-hidden="false"`):btn(t('hideEvent'),'event-hide',`data-id="${esc(night.id)}" data-hidden="true"`)}${hasSigned(night)?'':btn(t('deleteEvent'),'event-delete',`data-id="${esc(night.id)}"`,'danger')}</div>
    ${list.length?`<ol class="tl-matches">${list.map(m=>`<li><span class="tl-round">${esc(t('round'))} ${m.round}</span><span class="tl-pair">${m.sides.map(id=>esc(eventSide(night,id)||(isBye(m)?'—':t('pending')))).join(' — ')}</span><span class="tl-score">${isBye(m)?'':m.score.join('–')}</span>${mbadge(m)}</li>`).join('')}</ol>`:''}
    ${auditFold(audit,t('auditTrail'))}
  </div>
</li>`}
// The log's own grouping moved into mergedTimeline() (round 11): one pass over nights and
// broadcasts together, grouped by the day they share.
// ---- Records: one history - the nights, and the broadcasts that cover them (16.11, 23.1) ----
// Round 11, owner item 2 (m07044): 录制场次 and 历史赛事 are the same list. The archive's own card
// and its own heading are gone; every day in the log carries that day's nights and that day's
// broadcasts together, under the year and month heads the log always had, with the day as the
// last step. A day is the unit both kinds share - a night is archived with a date and a broadcast
// carries one - so "what happened on the 2nd" answers with the night and the footage at once.
// The list comes from /api/vods/recent (the server holds the Twitch credentials and caches the
// answer for RECENT_TTL_S) and every picture from /api/vods/thumb, so a browser rendering this
// page never talks to Twitch. A broadcast is still not a night: it appears whether or not any
// night claims it, the archive never invents a night, and the only thing that joins the two is a
// link row (annotator/operations.py, `vod_link`).
const archiveList={rows:null,error:'',loading:false};
const vodWhen=vod=>{const d=new Date(vod?.created_at);return isNaN(d)?null:d};
// Round 11: Twitch forgets. The store keeps a row per broadcast it has seen - the copy a link
// points at - so the list is the union of what the channel exposes now and what this console
// recorded. An archive row wins (it carries the thumbnail and the fresh metadata); a broadcast
// only the record knows is marked, so nobody takes it for one the channel still exposes.
function knownVods(){
  return (data.vods||[]).map(vod=>Object.assign({id:String(vod.id||''),title:String(vod.title||''),
    created_at:String(vod.created_at||''),length_s:Number(vod.length_s)||0,thumb:'',
    channel:String(vod.channel||''),fromRecord:true}))}
function archiveVods(){
  const rows=(archiveList.rows||[]).flatMap(c=>(c.vods||[]).map(v=>Object.assign({},v,{channel:c.channel})));
  const seen=new Set(rows.map(v=>String(v.id)));
  for(const vod of knownVods())if(vod.id&&!seen.has(vod.id)){seen.add(vod.id);rows.push(vod)}
  return rows.sort((a,b)=>{
    const da=vodWhen(a),db=vodWhen(b);
    if(da&&db&&da-db)return db-da;
    if(da&&!db)return -1;
    if(!da&&db)return 1;
    return String(b.id).localeCompare(String(a.id))})}
// The list arrives after the page does, so it is painted into its own card rather than through
// render(): a late answer must not rebuild Records under an operator who is reading it (the
// search box, an open sheet, the scroll), and a page that has gone away is not this loader's
// failure. showReview() is the same shape for the same reason.
function archiveCountText(){const vods=archiveVods();return t('archiveCount').replace('{n}',String(vods.length)).replace('{built}',String(vods.filter(v=>linksFor(v.id).length).length))}
function archiveNoteText(){const vods=archiveVods(),fuller=(archiveList.rows||[]).some(c=>c&&c.more);return t('archiveNote')+(fuller?` ${t('archiveMore').replace('{n}',vods.length)}`:'')}
// The head's two numbers only know themselves once /api/vods/recent answers, and that answer
// lands after the first paint.  So the count and the note are painted with the card and then
// written in place - the list is repainted the same way, and nothing calls render() (round 6:
// a late answer must not rebuild the screen under an operator, and round 11 found on the live
// page that a count which exists only in the first paint never appears at all).
function paintArchive(){
  const list=$('#records-list');if(list&&'innerHTML' in list)list.innerHTML=mergedTimeline();
  const count=$('#archive-card .archive-count');if(count)count.textContent=archiveCountText();
  const note=$('#archive-card .archive-note');if(note)note.textContent=archiveNoteText()}
async function loadArchiveList(force=false){
  if(archiveList.loading||(!force&&archiveList.rows))return;
  archiveList.loading=true;paintArchive();
  try{
    const r=await fetch('/api/vods/recent',{cache:'no-store'}),body=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(body.error||`HTTP ${r.status}`);
    archiveList.rows=body.channels||[];archiveList.error=''
  }catch(error){archiveList.rows=[];archiveList.error=String(error?.message||error)}
  archiveList.loading=false;paintArchive()}
// Owner item 2 (round 8): the box downloads every archived broadcast by itself. The console's job
// is to say what that queue is doing and to hand the operator the one switch, so the work is
// visible instead of silent. Reading /api/vods/queue is also what arms the beat on a fresh console.
const autoList={rows:null,error:'',loading:false};
async function loadAuto(force=false){
  if(autoList.loading||(!force&&autoList.rows))return;
  autoList.loading=true;paintAuto();
  try{
    const r=await fetch('/api/vods/queue',{cache:'no-store'}),body=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(body.error||`HTTP ${r.status}`);
    autoList.rows=body;autoList.error=''
  }catch(error){autoList.rows=null;autoList.error=String(error?.message||error)}
  autoList.loading=false;paintAuto()}
function autoCount(key){const list=autoList.rows?.[key];return Array.isArray(list)?list.length:0}
function autoInner(){
  if(autoList.error)return `<p class="empty-note">${esc(t('autoFailed'))}: ${esc(autoList.error)} ${btn(t('archiveRetry'),'auto-reload')}</p>`;
  if(!autoList.rows)return `<p class="muted" role="status">${esc(t('autoReading'))}</p>`;
  const rows=autoList.rows,on=!!rows.enabled,current=rows.current?String(rows.current.vod_id||rows.current.id||''):'';
  const bits=[on?t('autoOn'):t('autoPaused'),t('autoQueued').replace('{n}',autoCount('queued')),t('autoDone').replace('{n}',autoCount('done'))];
  if(current)bits.push(t('autoNow').replace('{id}',current));
  if(autoCount('skipped'))bits.push(t('autoSkipped').replace('{n}',autoCount('skipped')));
  if(rows.error)bits.push(String(rows.error));
  return `<p class="muted">${esc(t('autoDownload'))} · ${bits.map(esc).join(' · ')} ${btn(on?t('autoPause'):t('autoResume'),'auto-toggle')}</p>`}
function paintAuto(){const host=$('#auto-line');if(host)host.innerHTML=autoInner()}
async function autoToggle(){
  const next=autoList.rows?.enabled?'off':'on';
  try{
    const r=await fetch('/api/vods/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:next})});
    const body=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(body.error||`HTTP ${r.status}`);
    autoList.rows=body;autoList.error=''
  }catch(error){message(String(error?.message||error),true)}
  paintAuto()}
function archiveKind(vod){
  const word={ARCHIVE:'kindArchive',HIGHLIGHT:'kindHighlight',UPLOAD:'kindUpload'}[String(vod?.broadcast_type||'').toUpperCase()];
  return t(word||'archiveKind')}
// Round 9, owner items 6-8. The archive is one card per broadcast, grouped into a row for each
// day with the date set as the loudest thing in the group (item 7), and every card is itself the
// door into the review (item 8): opening a broadcast no longer requires building it first,
// because building it is one of the things the review is for. The two words that used to gate
// that door - "Not built yet" and "Build this night" - are gone (item 6); a card whose broadcast
// already has a night in the log carries a quiet mark instead of a state badge.
function clockLabel(d){if(!d)return'';try{return new Intl.DateTimeFormat(lang==='zh'?'zh-CN':'en-GB',{hour:'2-digit',minute:'2-digit'}).format(d)}catch{return''}}
function dayFull(d){if(!d)return t('unknownDate');try{return new Intl.DateTimeFormat(lang==='zh'?'zh-CN':'en-GB',{weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(d)}catch{return dayLabel(d)}}
function archiveRow(vod,links){
  const when=vodWhen(vod),thumb=String(vod?.thumb||''),length=Number(vod?.length_s)||0,title=String(vod.title||'')||t('unnamed');
  const meta=[clockLabel(when),hms(length),archiveKind(vod)].filter(Boolean).join(' · ');
  const named=(links||[]).filter(l=>l.night);
  const mark=named.length?`<small class="tl-vod-made">${esc(t('vodMark'))} · ${esc(named.map(l=>l.night.name||t('unnamed')).join(' · '))}</small>`:'';
  const note=vod.fromRecord?`<small class="tl-vod-note">${esc(t('vodOwn'))}</small>`:'';
  return `<li class="tl-vod-item"><button type="button" class="tl-vod${named.length?' is-made':''}" data-action="tl-review" data-id="${esc(String(vod.id))}">
  ${thumb?`<img class="tl-vod-thumb" src="${esc(thumb)}" alt="" width="160" height="90" loading="lazy" decoding="async">`:`<span class="tl-vod-thumb is-blank" aria-hidden="true"></span>`}
  <span class="tl-vod-body"><span class="tl-vod-title">${esc(title)}</span><small class="tl-vod-meta">${esc(meta)}</small>${note}${mark}</span>
</button></li>`}
// Round 11: the relation the owner asked for, at both ends. `links` is the join table the store
// keeps - one row per (broadcast, event, range) - and these four helpers are the only place the
// console reads it. An event the link names but the log no longer holds is not shown: there is
// nothing to click through to, and the server drops those rows when an event is deleted.
function eventById(id){return [tournament(),...(data.history||[])].find(n=>n&&n.id===id)||null}
function vodById(id){
  const key=String(id),row=archiveVods().find(v=>String(v.id)===key),known=(data.vods||[]).find(v=>String(v.id)===key)||{};
  const merged=Object.assign({title:'',length_s:0,created_at:''},known,row||{});merged.id=key;return merged}
function vodTitle(vod){return String(vod?.title||'')||`${t('vodWord')} ${String(vod?.id||'')}`}
function linkRows(){
  return (data.links||[]).map(l=>{
    const night=eventById(l.eventId);
    return {link:l,night,vod:vodById(l.vodId),
      locked:!!night&&String((night.source||{}).vodId||'')===String(l.vodId)}})
    .filter(l=>l.night)}
function linksFor(vodId){const key=String(vodId);return linkRows().filter(l=>String(l.link.vodId)===key)}
function linksOf(eventId){const key=String(eventId);return linkRows().filter(l=>String(l.link.eventId)===key)}

// The log itself: year, then month, then the day that holds both kinds of row. The grouping is one
// pass because the nights are newest first and the broadcasts arrive sorted the same way.
function dayKeyOf(d){return d?`${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`:'none'}
function archiveMatchesQuery(vod){
  const parts=searchFold(eventsQuery).split(' ').filter(Boolean);if(!parts.length)return true;
  const names=[String(vod?.title||''),String(vod?.id||''),String(vod?.channel||'')].map(searchFold);
  return parts.every(part=>names.some(name=>name.includes(part)))}
function dayCounts(day){
  const bits=[];
  if(day.nights.length)bits.push(t(day.nights.length===1?'dayEventsOne':'dayEvents').replace('{n}',String(day.nights.length)));
  if(day.vods.length)bits.push(t(day.vods.length===1?'dayVodsOne':'dayVods').replace('{n}',String(day.vods.length)));
  return bits.join(' · ')}
function daySection(day){
  const attrs=day.key==='none'?'':` data-day="${esc(day.key)}"`;
  return `<section class="tl-day"${attrs}>
  <div class="tl-day-head"><h3 class="tl-day-date">${esc(day.when?dayFull(day.when):t('unknownDate'))}</h3><span class="muted tl-day-count">${esc(dayCounts(day))}</span></div>
  ${day.nights.length?`<ol class="tl-nights">${day.nights.map(eventItem).join('')}</ol>`:''}
  ${day.vods.length?`<ol class="tl-vods">${day.vods.map(v=>archiveRow(v,linksFor(v.id))).join('')}</ol>`:''}
</section>`}
function emptyTimeline(nights,allVods,loading,error){
  const total=(data.history||[]).length,hiddenN=(data.history||[]).filter(n=>n.hidden).length;
  if(eventsQuery)return emptyNote('emptySearch');
  if(!total){
    const channels=archiveList.rows;
    if(!error&&channels&&!channels.length)return `<p class="empty-note">${esc(t('archiveNoSource'))}</p>`;
    if(!error&&channels&&!allVods.length)return `<p class="empty-note">${esc(t('archiveNone'))}</p>`;
    return emptyNote('emptyHistory','backfill-open','backfillOpen')}
  if(hiddenN&&!nights.length&&!allVods.length)return `<p class="empty-note">${esc(t('allHidden').replace('{n}',hiddenN))} ${btn(t('showHiddenN').replace('{n}',hiddenN),'toggle-hidden')}</p>`;
  return emptyNote('emptySearch')}
function mergedTimeline(){
  const loading=archiveList.rows===null,error=archiveList.error;
  const nights=timelineNights().filter(n=>eventMatchesQuery(n,eventsQuery));
  const allVods=archiveVods(),vods=allVods.filter(archiveMatchesQuery);
  const days=new Map();
  const slot=when=>{const key=dayKeyOf(when);let row=days.get(key);if(!row){row={key,when,nights:[],vods:[]};days.set(key,row)}return row};
  for(const night of nights)slot(eventDate(night)).nights.push(night);
  for(const vod of vods)slot(vodWhen(vod)).vods.push(vod);
  const rows=[...days.values()].sort((a,b)=>(b.when?b.when.getTime():0)-(a.when?a.when.getTime():0));
  const status=error?`<p class="empty-note">${esc(t('archiveFailed'))}: ${esc(error)} ${btn(t('archiveRetry'),'archive-reload')}</p>`
    :(loading?`<p class="muted" role="status">${esc(t('archiveReading'))}</p>`:'');
  if(!rows.length)return `${status}${emptyTimeline(nights,allVods,loading,error)}`;
  const months=[];
  for(const day of rows){const when=day.when,year=when?when.getFullYear():null,stamp=when?`${year}-${when.getMonth()}`:'unknown';
    let month=months.at(-1);
    if(!month||month.stamp!==stamp){month={stamp,year,label:when?monthLabel(when):t('unknownDate'),days:[]};months.push(month)}
    month.days.push(day)}
  let year=null;
  const list=`<div class="events">${months.map(month=>{const head=month.year!==year?`<h3 class="tl-year">${esc(month.year??t('unknownDate'))}</h3>`:'';year=month.year;
    return `${head}<section class="tl-month"><h3 class="tl-month-head">${esc(month.label)}</h3>${month.days.map(daySection).join('')}</section>`}).join('')}</div>`;
  return `${status}${list}`}

// The picker, in both directions, on the desk's own listbox pattern: one panel, filtered in place,
// closed by any click outside it. A row that is already linked is the way to unlink it, except the
// one the event's own import record owns - that link is the night's history, and the server refuses
// to drop it (deleting or hiding the night is how it goes).
let vodPick=null;
function vodPickOpen(kind,id){return !!vodPick&&vodPick.kind===kind&&String(vodPick.id)===String(id)}
function vodPickRows(kind,id){
  const rows=[];
  if(kind==='event'){
    const linked=new Set((data.links||[]).filter(l=>String(l.eventId)===String(id)).map(l=>String(l.vodId)));
    const seen=new Set();
    const push=vod=>{const key=String(vod.id);if(!key||linked.has(key)||seen.has(key))return;seen.add(key);
      rows.push({vodId:key,label:vodTitle(vod),meta:[clockLabel(vodWhen(vod)),hms(Number(vod.length_s)||0)].filter(Boolean).join(' · '),
        attrs:{title:String(vod.title||''),channel:String(vod.channel||''),length:String(Number(vod.length_s)||0),created:String(vod.created_at||'')}})};
    for(const vod of archiveVods())push(vod);
    for(const vod of (data.vods||[]))push(vod);
    return rows}
  const live=tournament();
  for(const night of [live,...(data.history||[])]){if(!night)continue;
    const link=(data.links||[]).find(l=>String(l.vodId)===String(id)&&String(l.eventId)===String(night.id));
    const locked=String((night.source||{}).vodId||'')===String(id);
    rows.push({eventId:night.id,label:night.name||t('unnamed'),
      meta:[eventDate(night)?dayLabel(eventDate(night)):'',live&&night.id===live.id?t('vodTonight'):''].filter(Boolean).join(' · '),
      linked:!!link,locked:!!link&&locked})}
  return rows}
function vodRowButton(kind,id,row,q){
  const label=`${row.label} ${row.meta||''}`;
  if(row.locked)return `<button type="button" class="pick-row on is-locked" disabled data-label="${esc(label)}">${esc(row.label)}<small>${esc(t('vodLinkedBadge'))}</small></button>`;
  const attrs=Object.entries(row.attrs||{}).filter(([,v])=>v).map(([k,v])=>` data-${k}="${esc(v)}"`).join('');
  return `<button type="button" role="option" class="pick-row${row.linked?' on':''}" data-action="${row.linked?'vod-unlink':'vod-link'}" data-vod="${esc(row.vodId||String(id))}" data-id="${esc(kind==='event'?String(id):String(row.eventId))}" data-label="${esc(label)}"${attrs}${nameMatches(label,q)?'':' hidden'}>${esc(row.label)}${row.meta?`<small>${esc(row.meta)}</small>`:''}${row.linked?`<small>${esc(t('vodUnlink'))}</small>`:''}</button>`}
function vodPicker(kind,id,label){
  const open=vodPickOpen(kind,id),q=open?String(vodPick.q||''):'';
  const rows=vodPickRows(kind,id);
  const shown=rows.filter(r=>r.locked||nameMatches(`${r.label} ${r.meta||''}`,q)).length;
  const search=esc(t(kind==='event'?'vodLinkSearch':'vodEventSearch'));
  return `<div class="pick vod-pick-host">
  <button type="button" class="pick-btn vod-pick-btn" data-action="vod-open" data-kind="${esc(kind)}" data-id="${esc(String(id))}" aria-haspopup="listbox" aria-expanded="${open?'true':'false'}"><span class="grow">${esc(label)}</span><span class="pick-caret" aria-hidden="true">▾</span></button>
  ${open?`<div class="pick-panel" data-total="${rows.length}">
    <input class="pick-search" data-vod-search="1" type="search" autocomplete="off" value="${esc(q)}" placeholder="${search}" aria-label="${search}">
    <p class="muted pick-count"${q.trim()?'':' hidden'}>${esc(t('searchCount').replace('{n}',String(shown)).replace('{m}',String(rows.length)))}</p>
    <div class="pick-rows">${rows.length?rows.map(r=>vodRowButton(kind,id,r,q)).join(''):`<p class="muted">${esc(t(kind==='event'?'vodLinkEmpty':'vodEventEmpty'))}</p>`}</div>
  </div>`:''}
</div>`}
function vodFilter(field){
  const panel=field.closest?.('.pick-panel');if(!panel)return;
  const q=field.value,total=Number(panel.dataset.total||0);let shown=0;
  for(const row of panel.querySelectorAll('.pick-row')){if(row.disabled)continue;const hit=nameMatches(row.dataset.label||'',q);row.hidden=!hit;if(hit)shown++}
  const count=panel.querySelector('.pick-count');if(count){count.hidden=!q.trim();count.textContent=t('searchCount').replace('{n}',String(shown)).replace('{m}',String(total))}}
// A night's own row names the broadcasts it covers, each one a way into its footage. The one that
// arrived with the night's own import is marked and cannot be dropped here.
function eventLinks(night){
  const own=String(night?.source?.vodId||'');
  const chips=linksOf(night.id).map(l=>{
    const key=String(l.link.vodId);
    const label=key===own&&String(night.source?.title||'')?String(night.source.title):vodTitle(l.vod);
    return `<span class="vod-chip">${btn(label,'tl-review',`data-id="${esc(key)}"`)}${l.locked?`<span class="badge">${esc(t('vodLinkedBadge'))}</span>`:`<button type="button" class="vod-unlink" data-action="vod-unlink" data-vod="${esc(key)}" data-id="${esc(night.id)}" aria-label="${esc(t('vodUnlink'))}" title="${esc(t('vodUnlink'))}">×</button>`}</span>`}).join('');
  return `<div class="vod-links"><span class="vod-links-label">${esc(t('vodLinks'))}</span>${chips||`<span class="muted">${esc(t('vodLinkNone'))}</span>`}${vodPicker('event',night.id,t('vodLinkOpen'))}</div>`}
// A broadcast's own page names the nights it covers, from the same rows.
function vodEventSection(vodId){
  const chips=linksFor(vodId).map(l=>`<span class="vod-chip"><span class="vod-chip-name">${esc(l.night.name||t('unnamed'))}</span>${l.locked?`<span class="badge">${esc(t('vodLinkedBadge'))}</span>`:`<button type="button" class="vod-unlink" data-action="vod-unlink" data-vod="${esc(String(vodId))}" data-id="${esc(l.night.id)}" aria-label="${esc(t('vodUnlink'))}" title="${esc(t('vodUnlink'))}">×</button>`}</span>`).join('');
  return `<div class="vod-links"><span class="vod-links-label">${esc(t('events'))}</span>${chips||`<span class="muted">${esc(t('vodEventNone'))}</span>`}${vodPicker('vod',vodId,t('vodEventOpen'))}</div>`}

// Records' one job: the entrance to past events. The audit log lives inside the night it
// belongs to; the house standings live on each Regulars row (6.1).
// The recorded review (owner item 3): the same workbench the Vision tab used to carry, opened
// from the broadcast it belongs to on Records. The head names the broadcast the operator came
// from, and the note says which pictures the screen is showing rather than implying a match it
// cannot make.
// Round 9, owner item 8: a card can also be a broadcast with no night in the log yet. That page
// keeps the same head and offers the import.
// Round 10, owner item 3: it keeps the workbench too. Round 9 dropped the surface here on the
// argument that the datasets this console is configured with belong to other nights; the owner's
// answer was that a recorded page with no scrubber and no sidebars is not a review page, and he
// is right. The surface now opens the broadcast's OWN dataset when the machine has one
// (datasetForVod below builds the id the way src/datasets.py does), and the note says plainly
// when what is on screen is somebody else's footage instead of hiding the transport.
// Round 10, owner item 3: which broadcast a recorded page is about, and the dataset it lives
// in. src/datasets.py `imported_id(vod_id)` names a whole-broadcast import `tw-<vod>`, and a
// ranged one `tw-<vod>-<start>-<end>` in absolute seconds, so the exact whole-broadcast id is
// tried first and an id that merely carries the number — a ranged import of the same broadcast —
// is the fallback. The engine's own pick (app.js `loadDatasets`) prefers vod30 whenever it
// exists, which is why this cannot be left to it.
let vodDatasetAsked='';
function broadcastVodId(){
  if(!reviewId)return '';
  const night=(data.history||[]).find(n=>n.id===reviewId);
  if(night)return String(night.source?.vodId||'');
  const vod=archiveVods().find(v=>String(v.id)===String(reviewId));
  return vod?String(vod.id||''):''}
function datasetForVod(vodId){
  const digits=(String(vodId||'').match(/\d{4,12}/)||[''])[0];if(!digits)return '';
  const ids=(reviewState().datasets||[]).map(d=>String(d.id||''));
  return ids.find(id=>id==='tw-'+digits)||ids.find(id=>id.includes(digits))||''}
function reviewScreen(night,vod){
  const isVod=!night,vodId=String(isVod?vod?.id:night?.source?.vodId||''),when=isVod?vodWhen(vod):null;
  const title=isVod?(String(vod?.title||'')||t('unnamed')):(night.name||t('unnamed'));
  const meta=isVod
    ?[dayFull(when),clockLabel(when),hms(Number(vod?.length_s)||0)].filter(Boolean).join(' · ')
    :[t('reviewFootage'),vodId?`${t('reviewBroadcast')} ${vodId}`:''].filter(Boolean).join(' · ');
  const act=isVod?btn(t('reviewImport'),'bf-pick',`data-id="${esc(vodId)}" data-length="${esc(String(Number(vod?.length_s)||0))}" data-title="${esc(String(vod?.title||''))}"`,'primary'):'';
  // Round 13, owner item 7: the review's header was a card of four stacked blocks - 380 px of frame
  // above the work, at 1280. The title and its date stay in the heading; the one action and the one
  // link control stand beside them; and the sentence that explains the chips is a fold, because it is
  // read once and the workbench is read every time.
  return `<article class="review-card" id="review-card">
  <div class="heading"><div class="grow"><h2>${esc(title)}</h2><p class="muted review-meta">${esc(meta)}</p></div>
    <div class="row review-act">${isVod?vodEventSection(vodId):''}${act}${btn(t('reviewBack'),'review-back')}</div></div>
  <details class="review-why"><summary>${esc(t('reviewWhy'))}</summary><p class="muted">${esc(isVod?t('reviewVodNote'):t('reviewNote'))}</p></details>
</article>${visionSurface()}`}
function recordsScreen(){
  if(reviewId){
    const night=(data.history||[]).find(n=>n.id===reviewId);
    if(night)return reviewScreen(night);
    const vod=archiveVods().find(v=>String(v.id)===String(reviewId));
    if(vod)return reviewScreen(null,vod);
    reviewId=null}
  if(sheetId){const night=(data.history||[]).find(n=>n.id===sheetId);if(night)return resultsSheet(night);sheetId=null}
  const hiddenN=(data.history||[]).filter(n=>n.hidden).length;
  return `<section class="stack records"><article class="archive-card" id="archive-card">
  <div class="heading"><h2>${esc(t('records'))}</h2><span class="muted archive-count">${esc(archiveCountText())}</span></div>
  <div class="toolbar" role="group" aria-label="${esc(t('records'))}">
    ${input('events-search',eventsQuery,'search',`id="events-search" placeholder="${esc(t('search'))}" aria-label="${esc(t('searchRecords'))}"`)}
    ${hiddenN?btn(showHidden?t('hideHidden'):t('showHiddenN').replace('{n}',hiddenN),'toggle-hidden'):''}
    <span class="toolbar-gap" aria-hidden="true"></span>
    ${btn(t('sources'),'sources-open')}
    ${btn(t('refresh'),'archive-reload')}
    ${btn(t('backfillOpen'),'backfill-open','','primary')}
  </div>
  <p class="muted archive-note">${esc(archiveNoteText())}</p>
  <div class="auto-line" id="auto-line">${autoInner()}</div>
  <div id="records-list">${mergedTimeline()}</div>
  ${auditRest().length?auditFold(auditRest(),t('auditRest'),' tl-audit-rest'):''}
</article></section>`}
// ---- Backfill one past night from a Twitch VOD (7.1) ------------------------------------
function bfFresh(){return {step:'pick',vod:null,startS:0,endS:0,estimate:null,job:null,datasetId:'',datasetTitle:'',paste:'',night:{name:'',format:'singles',raceTo:7,tables:1},clock:0,marks:[],draft:[],error:'',detail:'',notice:'',conflict:'',nightId:'',busy:false,recent:null,saved:null}}
function readBfDraft(){try{const raw=JSON.parse(localStorage.getItem(BF_DRAFT)||'null');return raw&&typeof raw==='object'&&!Array.isArray(raw)?raw:null}catch(_){return null}}
function saveBfDraft(){if(!bf)return;try{localStorage.setItem(BF_DRAFT,JSON.stringify({datasetId:bf.datasetId,vodId:bf.vod?.id||'',channel:bf.vod?.channel||'',title:bf.vod?.title||'',startS:bf.startS,endS:bf.endS,night:bf.night,marks:bf.marks,draft:bf.draft,savedAt:new Date().toISOString()}))}catch(_){}}
function clearBfDraft(){try{localStorage.removeItem(BF_DRAFT)}catch(_){}}
function bfError(error){const detail=String(error?.message||error||'');if(/Only saved channels/i.test(detail))return t('bfChannel');if(/Not enough free disk space/i.test(detail))return t('bfDiskNo');return validationMessage(detail)}
function bfConflictId(text){const all=[...String(text||'').matchAll(/\(([^()]+)\)/g)];return all.length?all[all.length-1][1]:''}
function bfSeconds(text){const parts=String(text??'').trim().split(':').map(Number);if(!parts.length||parts.some(n=>!Number.isFinite(n)||n<0))return null;return Math.round(parts.reduce((total,part)=>total*60+part,0))}
function bfPasteId(text){const m=String(text??'').trim().match(/(?:videos\/)?([0-9]{4,12})\/?$/);return m?m[1]:''}
async function bfOpen(){bf=Object.assign(bfFresh(),{saved:readBfDraft()});render();await bfRecent();render()}
function bfExit(){bf=null;render()}
async function bfRecent(){try{const r=await fetch('/api/vods/recent',{cache:'no-store'}),body=await r.json().catch(()=>({}));if(!r.ok)throw Error(body.error||`HTTP ${r.status}`);bf.recent=body.channels||[];bf.detail=''}catch(error){bf.recent=[];bf.detail=String(error.message||error)}}
function bfPickVod(id,length,title){bf.vod={id:String(id),length_s:Number(length)||0,title:title||''};bf.datasetId='';bf.estimate=null;bf.notice='';bf.detail='';bf.error='';bf.step='verify';render()}
function bfCheck(){const text=String(bfValue('#bf-vod',bf.paste)??'');bf.paste=text;const id=bfPasteId(text);if(!id){bf.notice=t('bfNeedVod');bf.error='';render();return}bfPickVod(id,0,'')}
async function bfEstimate(){
  const id=bf?.vod?.id;if(!id){bf.notice=t('bfNeedVod');render();return}
  bf.busy=true;render();
  // Round 10, owner item 3: the estimate describes the whole broadcast, because that is what the
  // import takes. An estimate for a range the download will not honour would be the same lie in
  // a second place - and the disk figure is the one number that must be about the real download.
  try{
    const r=await fetch(`/api/vods/estimate?vod=${encodeURIComponent(id)}`,{cache:'no-store'}),body=await r.json().catch(()=>({}));
    if(!r.ok)throw Object.assign(Error(body.error||`HTTP ${r.status}`),{status:r.status});
    bf.estimate=body;bf.datasetId=String(body.id||'');bf.startS=Number(body.range?.start_s)||0;bf.endS=Number(body.range?.end_s)||0;
    bf.vod=Object.assign({},bf.vod,{title:body.title||bf.vod.title,channel:body.channel||'',length_s:body.length_s||bf.vod.length_s});
    bf.error='';bf.detail='';bf.notice=body.already_imported?t('bfReuse'):'';bf.step='verify'}
  catch(error){bf.detail=String(error?.message||error);bf.error=bfError(error);bf.step='rejected'}
  bf.busy=false;render()}
async function bfStartImport(){
  if(!bf.estimate){await bfEstimate();if(!bf.estimate||bf.error)return}
  bf.busy=true;bf.notice='';render();
  try{
    // Round 10, owner item 3: the download is the whole broadcast. Both bounds have server
    // defaults (annotator/vod_import.py `_plan`: start 0, duration = the rest of the VOD), and a
    // whole import is the dataset src/datasets.py `imported_id(vod_id)` names - the same id the
    // estimate below already returned, so a second press without a server restart is still a
    // reuse, not a second download.
    const r=await fetch('/api/vods/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vod:bf.vod.id})});
    const job=await r.json().catch(()=>({}));
    if(r.status===409){
      bf.detail=String(job.error||'');
      if(/already imported/i.test(bf.detail)){bf.notice=t('bfReuse');bf.error='';bf.step='dataset';bf.busy=false;saveBfDraft();render();return}
      bf.notice=t('bfBusy');bf.step='importing';bf.job=Object.assign({state:'running'},job);bf.busy=false;render();return}
    if(!r.ok)throw Object.assign(Error(job.error||`HTTP ${r.status}`),{status:r.status});
    bf.job=job;bf.datasetId=String(job.id||bf.datasetId);bf.error='';bf.detail='';bf.step='importing'}
  catch(error){bf.detail=String(error?.message||error);bf.error=bfError(error);bf.step='failed'}
  bf.busy=false;saveBfDraft();render();if(bf.step==='importing')bfSchedule()}
async function bfPoll(){try{const r=await fetch('/api/vods/job',{cache:'no-store'}),job=await r.json().catch(()=>({}));if(!r.ok)throw Error(job.error||`HTTP ${r.status}`);bfAdoptJob(job)}catch(error){bf.detail=String(error?.message||error);bf.error=bfError(error);render()}}
async function bfCancel(){try{const r=await fetch('/api/vods/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})}),job=await r.json().catch(()=>({}));if(!r.ok)throw Error(job.error||`HTTP ${r.status}`);bfAdoptJob(job)}catch(error){bf.detail=String(error?.message||error);bf.error=bfError(error);render()}}
function bfAdoptJob(job){
  if(!bf)return;bf.job=job;const state=String(job.state||'');
  if(state==='done'){bf.step='dataset';bf.datasetId=String(job.id||bf.datasetId);bf.datasetTitle=job.title||'';bf.vod=Object.assign({},bf.vod,{title:job.title||bf.vod.title,channel:job.channel||bf.vod.channel||''});bf.notice='';saveBfDraft()}
  else if(state==='error'||state==='failed'){bf.step='failed';bf.detail=String(job.error||'');bf.error=bfError(job.error||'')}
  else if(state==='cancelled'){bf.step='verify';bf.notice=String(job.message||'');bf.job=null}
  render();if(bf?.step==='importing')bfSchedule()}
function bfSchedule(){if(bf?.step==='importing')setTimeout(()=>{bfPoll()},2000)}
function bfRetry(){bf.error='';bf.detail='';bf.notice='';bf.step=bf.estimate?'verify':'pick';render()}
// 7.3: the same range, already downloaded, is never fetched twice - the operator goes
// straight to marking the file that is already on disk.
function bfUseImported(){bf.notice=t('bfReuse');bf.error='';bf.detail='';bf.step='dataset';saveBfDraft();render()}
function bfChooseOther(){bf.error='';bf.detail='';bf.notice='';bf.estimate=null;bf.datasetId='';bf.datasetTitle='';bf.step='pick';render()}
function bfStartMarking(){
  const name=String(bfValue('#bf-night-name',bf.night.name)||'').trim()||bf.datasetTitle||bf.vod?.title||autoEventName();
  bf.night=Object.assign({},bf.night,{name});bf.marks=[];bf.draft=[];bf.clock=0;bf.notice='';bf.saved=readBfDraft();bf.step='marking';saveBfDraft();render()}
function bfPrompt(){
  const saved=bf.saved;if(!saved||!saved.datasetId||saved.datasetId!==bf.datasetId)return '';
  const n=(saved.draft||[]).length||(saved.marks||[]).length;if(!n)return '';
  return `<p class="note">${esc(t('bfResumePrompt').replace('{n}',n))} ${btn(t('bfResumeYes'),'bf-resume')} ${btn(t('bfResumeNo'),'bf-drop-draft')}</p>`}
function bfResumeDraft(){
  const saved=bf.saved||readBfDraft();if(!saved)return;
  bf.marks=(saved.marks||[]).map(m=>({start:m.start,end:m.end}));
  bf.draft=(saved.draft||[]).map(m=>Object.assign({},m,{score:[...(m.score||[null,null])]}));
  bf.night=Object.assign({},bf.night,saved.night||{});if(saved.startS)bf.startS=saved.startS;if(saved.endS)bf.endS=saved.endS;
  bf.step=bf.draft.length?'review':'marking';render()}
function bfDropDraft(){clearBfDraft();bf.saved=null;bf.marks=[];bf.draft=[];render()}
function bfClockRead(){const media=$('#bf-media'),at=Number(media?.currentTime);return Number.isFinite(at)&&at>0?at:bf.clock}
function bfMarkStart(){const at=Math.round(bfClockRead());const open=bf.marks.filter(m=>m.end==null).pop();if(open){if(at<=open.start){bf.notice=t('bfMarkOrder');render();return}open.end=at}else bf.marks.push({start:at,end:null});bf.notice='';saveBfDraft();render()}
function bfMarkEnd(){const at=Math.round(bfClockRead()),open=bf.marks.filter(m=>m.end==null).pop();if(!open){bf.notice=t('bfNeedMarks');render();return}if(at<=open.start){bf.notice=t('bfMarkOrder');render();return}open.end=at;bf.notice='';saveBfDraft();render()}
function bfUnmark(index){bf.marks.splice(index,1);saveBfDraft();render()}
function bfToReview(){
  const ready=bf.marks.filter(m=>m.end!=null);if(!ready.length){bf.notice=t('bfNeedMarks');render();return}
  bf.marks=ready;
  bf.draft=ready.map((m,i)=>{const kept=bf.draft[i];return kept&&kept.start===m.start&&kept.end===m.end?kept:{start:m.start,end:m.end,sides:['',''],winner:'',score:[null,null],confirmed:false}});
  bf.notice='';bf.step='review';saveBfDraft();render()}
function bfPeople(){return [...new Set([...roster().map(p=>p.name),...bf.draft.flatMap(m=>m.sides).filter(Boolean)])]}
function bfRowBroken(m){return !m.sides[0]||!m.sides[1]||m.sides[0]===m.sides[1]||!m.winner||!m.sides.includes(m.winner)||!Number.isInteger(m.score[0])||!Number.isInteger(m.score[1])||m.score[0]<0||m.score[1]<0}
function bfConfirm(index){const m=bf.draft[index];if(!m)return;if(bfRowBroken(m)){m.confirmed=false;bf.notice=t('bfIncomplete');render();return}m.confirmed=true;bf.notice='';saveBfDraft();render()}
// A typed name that folds to a roster name exactly is written as that regular (pid), so the
// past night counts towards their house standing (6.1); anything else is a guest and counts
// towards nobody. The server refuses a guest whose name is already a regular's, so a slip here
// is a message, never a silent split of one person's history.
function bfPlayerFor(name){const fold=searchFold(name);if(!fold)return null;return (data.players||[]).find(p=>searchFold(p.name)===fold)||null}
function bfEntrants(names){return names.map(name=>{const p=bfPlayerFor(name);return p?{pid:p.id,name:p.name}:{name:String(name)}})}
function bfPersonBadge(name){return name?`<span class="badge bf-linked">${esc(t(bfPlayerFor(name)?'member':'guest'))}</span>`:''}
function bfPayload(){
  const rows=bf.draft,names=[...new Set(rows.flatMap(m=>m.sides))];
  return {event:{name:String(bf.night.name||bf.datasetTitle||autoEventName()),format:bf.night.format==='doubles'?'doubles':'singles',raceTo:Number(bf.night.raceTo)||1,tables:Number(bf.night.tables)||1,
      entrants:bfEntrants(names),
      matches:rows.map(m=>({round:1,sides:[m.sides[0],m.sides[1]],score:[Number(m.score[0]),Number(m.score[1])],winner:m.winner,result:'played',clip:[Math.round(m.start),Math.round(m.end)]}))},
    source:{kind:'vod-backfill',vodId:String(bf.vod.id),datasetId:String(bf.datasetId),startS:Number(bf.startS),endS:Number(bf.endS),channel:bf.vod.channel||'',title:bf.vod.title||'',humanReviewed:true}}}
async function bfCommit(){
  const rows=bf.draft;if(!rows.length){bf.notice=t('bfNeedMarks');render();return}
  const unconfirmed=rows.filter(m=>!m.confirmed).length;
  if(unconfirmed){bf.notice=t('bfUnconfirmed').replace('{n}',unconfirmed);render();return}
  if(rows.some(bfRowBroken)){bf.notice=t('bfIncomplete');render();return}
  const payload=bfPayload();bf.busy=true;bf.notice='';render();
  try{
    const r=await fetch('/api/operations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({revision:data.revision,action:'event_backfill'},payload))});
    const result=await r.json().catch(()=>({}));
    if(r.status===409){bf.conflict=String(result.error||'');bf.nightId=bfConflictId(bf.conflict);bf.notice=t('bfSameVod');bf.busy=false;render();return}
    if(!r.ok){bf.detail=String(result.error||`HTTP ${r.status}`);bf.notice=validationMessage(bf.detail);bf.busy=false;render();return}
    data=result;bf.nightId=((result.history||[]).find(n=>(n.source||{}).datasetId===bf.datasetId)||{}).id||'';bf.step='done';bf.busy=false;clearBfDraft();render();message(t('bfDone'))}
  catch(error){bf.detail=String(error?.message||error);bf.notice=validationMessage(bf.detail);bf.busy=false;render()}}
function bfOpenTimeline(){const id=bf?.nightId;bf=null;if(id){showHidden=true;openEvents.add(id)}go('records')}
async function bfOpenNight(){
  const wanted=bf?.nightId||bfConflictId(bf?.conflict||''),wantedDataset=bf?.datasetId;
  try{await reload()}catch(_){}
  const night=(data?.history||[]).find(n=>n.id===wanted)||(data?.history||[]).find(n=>(n.source||{}).datasetId===wantedDataset);
  bf=null;if(night){showHidden=true;openEvents.add(night.id)}go('records')}
function bfInput(node){
  const key=String(node?.dataset?.bf||'');if(!bf||!key)return false;const value=node.value;
  if(key==='vod')bf.paste=value;
  else if(key==='clock')bf.clock=bfSeconds(value)??bf.clock;
  else if(key==='night-name')bf.night.name=value;
  else if(key==='night-format')bf.night.format=value;
  else if(key==='night-race')bf.night.raceTo=Number(value)||1;
  else if(key==='night-tables')bf.night.tables=Number(value)||1;
  else if(/^side-\d+-[01]$/.test(key)){const [i,s]=key.split('-').slice(1);bf.draft[Number(i)].sides[Number(s)]=value;bf.draft[Number(i)].confirmed=false}
  else if(/^winner-\d+$/.test(key)){const i=Number(key.split('-')[1]);bf.draft[i].winner=value;bf.draft[i].confirmed=false}
  else if(/^score-\d+-[01]$/.test(key)){const [i,s]=key.split('-').slice(1),n=Number(value);bf.draft[Number(i)].score[Number(s)]=value===''||!Number.isFinite(n)?null:n;bf.draft[Number(i)].confirmed=false}
  else return false;
  saveBfDraft();return true}
// ---- Backfill screens (7.2 copy, 3.10 layout) -------------------------------------------
function bfNoticeHtml(inline){return `${bf.notice&&!inline?`<p class="note bf-notice" role="status">${esc(bf.notice)}</p>`:''}${bf.error||bf.detail?`<p class="note err">${esc(bf.error||'')}${bf.detail?` <span class="muted">${esc(bf.detail)}</span>`:''}</p>`:''}`}
function bfClockLine(){return `<div class="row bf-clockline">${field(t('bfStartAt'),input('clock',hms(bf.clock),'text','id="bf-clock" data-bf="clock" class="bf-clock-input"'))}<span class="bf-at" id="bf-clock-read">@ ${esc(hms(bf.clock))}</span>${btn(t('bfMarkStart'),'bf-mark-start','','primary')}${btn(t('bfMarkEnd'),'bf-mark-end')}</div>`}
function bfDatalist(){return `<datalist id="bf-people">${bfPeople().map(name=>`<option value="${esc(name)}"></option>`).join('')}</datalist>`}
function bfPickStep(){
  const channels=(bf.recent||[]).map(channel=>{
    const rows=(channel.vods||[]).map(v=>`<div class="row bf-vod">${v.thumb?`<img class="bf-thumb" src="${esc(v.thumb)}" alt="" width="160" height="90" loading="lazy" decoding="async">`:''}<span class="grow">${esc(v.title||v.id)}<small>${esc(fmtDate(v.created_at))} · ${esc(hms(v.length_s))} · ${esc(archiveKind(v))}${(v.imported||[]).length?` · ${esc(t('bfReuse'))}`:''}</small></span>${btn(t('bfPick'),'bf-pick',`data-id="${esc(v.id)}" data-length="${Number(v.length_s)||0}" data-title="${esc(v.title||'')}"`)}</div>`).join('');
    const body=channel.error?`<p class="note err">${esc(channel.error)}</p>`:(rows?`<div class="stack">${rows}</div>`:`<p class="muted">${esc(t('bfNoVods'))}</p>`);
    return `<article class="bf-channel"><h3>${esc(channel.channel)}</h3>${body}</article>`}).join('');
  return `<h2>${esc(t('bfPickTitle'))}</h2><p class="muted">${esc(t('bfPickNote'))}</p>${channels}
  <form id="bf-pick-form" class="bf-form">${field(t('bfPaste'),input('vod',bf.paste,'text',`id="bf-vod" data-bf="vod"${bf.notice?' aria-describedby="bf-vod-note"':''} placeholder="https://www.twitch.tv/videos/1234567890"`))}${bf.notice?`<p class="note bf-notice" id="bf-vod-note" role="status">${esc(bf.notice)}</p>`:''}
    <div class="actions">${btn(t('bfCheck'),'bf-check','','primary')}</div></form>`}
function bfVerifyStep(){
  const e=bf.estimate,disk=e?.disk||{},reuse=e?.already_imported?t('bfReuse'):'';
  return `<h2>${esc(t('bfVerifyTitle'))}</h2>
  <p class="muted">${esc(bf.vod?.channel||'')} · ${esc(bf.vod?.title||bf.vod?.id||'')} · ${esc(hms(bf.vod?.length_s||0))}</p>
  <div class="row">${btn(t('bfEstimate'),'bf-estimate','','primary')}</div>
  ${e?`<p class="bf-estimate" role="status">${esc(t('bfEstimateLine').replace('{size}',sizeText(e.estimate_bytes)).replace('{free}',sizeText(disk.free_bytes)).replace('{reuse}',reuse))}</p>`:''}
  ${disk.ok===false?`<p class="note err">${esc(disk.refusal||t('bfDiskNo'))}</p><div class="row">${btn(t('bfOther'),'bf-choose-other')}</div>`:''}
  ${e&&disk.ok!==false&&!e.already_imported?`<div class="row">${btn(t('bfStartImport'),'bf-start-import','','primary')}${btn(t('bfOther'),'bf-choose-other')}</div>`:''}
  ${e?.already_imported?`<p class="note">${esc(t('bfReuse'))}</p><div class="row">${btn(t('bfUseImported'),'bf-use-imported','','primary')}${btn(t('bfStartImport'),'bf-start-import')}${btn(t('bfOther'),'bf-choose-other')}</div>`:''}
  ${bfPrompt()}`}
function bfImportingStep(){
  const job=bf.job||{},percent=Math.max(0,Math.min(100,Number(job.percent)||0)),eta=job.eta_s?` · ${hms(job.eta_s)}`:'',rate=job.rate_mb_s?` · ${job.rate_mb_s} MB/s`:'';
  return `<h2>${esc(t('bfImporting'))}</h2>
  <div class="progress" role="progressbar" aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100"><span style="transform:scaleX(${(percent/100).toFixed(3)})"></span></div>
  <p class="muted">${esc(String(percent))}%${esc(eta)}${esc(rate)}</p>
  <p class="note">${esc(t('bfLeft'))}</p>
  <div class="row">${btn(t('bfWait'),'bf-poll')}${btn(t('bfCancel'),'bf-cancel')}</div>
  ${bfPrompt()}`}
function bfDatasetStep(){
  const N=bf.night;
  return `<h2>${esc(t('bfWhichNight'))}</h2>
  <p class="muted">${esc(t('bfUploaded'))} · ${esc(bf.datasetTitle||bf.vod?.title||bf.datasetId)} · ${esc(hms((bf.endS||0)-(bf.startS||0)))}</p>
  <div class="fields">${field(t('bfNightName'),input('night-name',N.name||bf.datasetTitle||bf.vod?.title||'','text','id="bf-night-name" data-bf="night-name" maxlength="120"'))}
    ${field(t('format'),`<select id="bf-night-format" data-bf="night-format">${['singles','doubles'].map(f=>option(f,t(f),N.format)).join('')}</select>`)}
    ${field(t('race'),`<select id="bf-night-race" data-bf="night-race">${[1,3,5,7,9,11].map(n=>option(n,n,N.raceTo)).join('')}</select>`)}
    ${field(t('tables'),input('night-tables',N.tables,'number','id="bf-night-tables" data-bf="night-tables" min="1" max="32"'))}</div>
  <div class="row">${btn(t('bfStartMarking'),'bf-start-marking','','primary')}</div>
  ${bfPrompt()}`}
function bfMarkingStep(){
  const done=bf.marks.filter(m=>m.end!=null).length;
  return `<h2>${esc(t('bfStartMarking'))}</h2>
  <div class="bf-stage"><video id="bf-media" controls preload="metadata" src="/media/${encodeURIComponent(String(bf.datasetId||''))}/video"></video></div>
  ${bfClockLine()}
  <p class="bf-marked" role="status">${esc(t('bfMarked').replace('{n}',done))}</p>
  <ol class="bf-marks">${bf.marks.map((m,i)=>`<li${m.end==null?' class="open"':''}><span class="tl-date">#${i+1}</span> ${esc(hms(m.start))} – ${m.end==null?esc(t('pending')):esc(hms(m.end))} ${btn(t('bfUnmark'),'bf-unmark',`data-id="${i}"`)}</li>`).join('')}</ol>
  <p class="note">${esc(t('bfManual'))}</p>
  <div class="row">${btn(t('bfToReview'),'bf-to-review','','primary')}</div>
  ${bfDatalist()}`}
function bfReviewStep(){
  const unconfirmed=bf.draft.filter(m=>!m.confirmed).length;
  const rows=bf.draft.map((m,i)=>`<div class="bf-review${m.confirmed?' done':''}">
    <span class="tl-date">#${i+1}</span><span class="muted bf-bounds">${esc(hms(m.start))}–${esc(hms(m.end))}</span>
    ${field(t('bfPlayer1'),input(`p1-${i}`,m.sides[0],'text',`list="bf-people" data-bf="side-${i}-0"`)+bfPersonBadge(m.sides[0]))}
    ${field(t('bfPlayer2'),input(`p2-${i}`,m.sides[1],'text',`list="bf-people" data-bf="side-${i}-1"`)+bfPersonBadge(m.sides[1]))}
    ${field(t('bfWinner'),`<select data-bf="winner-${i}"><option value="">${esc(t('pending'))}</option>${[m.sides[0],m.sides[1]].filter(Boolean).map(name=>option(name,name,m.winner)).join('')}</select>`)}
    ${field(t('bfScore'),`<span class="bf-score"><input type="number" min="0" max="99" data-bf="score-${i}-0" value="${m.score[0]==null?'':m.score[0]}"> – <input type="number" min="0" max="99" data-bf="score-${i}-1" value="${m.score[1]==null?'':m.score[1]}"></span>`)}
    ${m.confirmed?`<span class="badge">${esc(t('bfConfirmed'))}</span>`:btn(t('bfConfirmMatch'),'bf-confirm',`data-id="${i}"`)}
  </div>`).join('');
  const names=[...new Set(bf.draft.flatMap(m=>m.sides).filter(Boolean))],linked=names.filter(name=>bfPlayerFor(name)).length;
  return `<h2>${esc(t('bfReviewTitle'))}</h2><p class="note">${esc(t('bfHonest'))}</p>
  <p class="note bf-linked-count">${esc(t('bfLinkedCount').replace('{n}',linked).replace('{m}',names.length))}</p>
  <form id="bf-review-form">${rows}</form>
  <p class="bf-unconfirmed" role="status">${unconfirmed?esc(t('bfUnconfirmed').replace('{n}',unconfirmed)):''}</p>
  ${bfDatalist()}
  <div class="row">${btn(t('bfBackMarking'),'bf-to-marking')}${btn(t('bfCommit'),'bf-commit',unconfirmed||bf.busy?'disabled':'','primary')}</div>
  ${bf.conflict?`<p class="note err">${esc(t('bfSameVod'))} ${btn(t('bfOpen'),'bf-open-night')}</p>`:''}`}
function bfDoneStep(){return `<h2>${esc(t('bfDone'))}</h2><div class="row">${btn(t('bfOpenTimeline'),'bf-open-timeline','','primary')}</div>`}
function bfFailedStep(){return `<h2>${esc(t(bf.step==='rejected'?'bfRejectedTitle':'bfFailedTitle'))}</h2>
  <div class="row">${btn(t('bfRetry'),'bf-retry','','primary')}${btn(t('bfOther'),'bf-choose-other')}${/Only saved channels/i.test(bf.detail||'')?`<a href="#/backroom">${esc(t('status'))}</a>`:''}</div>`}
function bfScreen(){
  const step=bf?.step||'pick',body=step==='pick'?bfPickStep():step==='verify'?bfVerifyStep():step==='importing'?bfImportingStep():step==='dataset'?bfDatasetStep():step==='marking'?bfMarkingStep():step==='review'?bfReviewStep():step==='done'?bfDoneStep():bfFailedStep();
  return `<section class="stack backfill" data-step="${esc(step)}">
  <div class="bf-head"><button type="button" class="link" data-action="bf-exit">← ${esc(t('bfExit'))}</button><span class="bf-step muted">${esc(t('bfStep').replace('{n}',BF_STEPS[step]||1))}</span></div>
  ${bfNoticeHtml(step==='pick')}
  ${body}
</section>`}
document.addEventListener('timeupdate',e=>{if(e.target?.id==='bf-media'&&bf){bf.clock=Math.round(Number(e.target.currentTime)||0);const read=$('#bf-clock-read');if(read)read.textContent=`@ ${hms(bf.clock)}`}},true);
let liveTimer=null,liveGeneration=0,liveChoice='dataset:vod30',liveDetectors=['table','person'];
const liveText=(en,zh)=>lang==='zh'?zh:en;
let vodChoice=null;
// Owner round 8 (item 3): the recorded review is Records' business, not the Vision tab's.
// reviewId holds the night whose broadcast is open, so the Vision tab can stay the live
// stream alone and every recorded surface has exactly one entrance - a night's row.
let reviewId=null;
// The Vision tab's gate (owner item 3): the last answer from /api/live decides whether the tab
// shows the live controls alone or the workbench fed by live frames. liveWasRunning is what the
// last paint believed, so one state change repaints once and a steady state never loops.
let liveSnapshot=null,liveWasRunning=null;
function liveRunning(){return liveSnapshot?.state==='running'||liveSnapshot?.state==='starting'}
// The workbench is hosted by exactly two screens: a night's recorded review, and the live tab
// once frames are actually arriving. Everywhere else #vision-host stays hidden and the review
// app is deactivated, so a panel never sits above a leftover recorded picture (owner item 3).
function reviewHosted(){return !!reviewId||(tab==='vision'&&liveRunning())}
// A source is one of three shapes, and the replay one is never called live: the
// panel prints what the server and the capture report, not a label we choose.
function liveSource(value=liveChoice){const [kind,...id]=value.split(':');if(kind==='vod-replay')return {kind:'vod-replay',vod_id:vodChoice?.vod_id??'',start_s:vodChoice?.start_s??0,rate:vodChoice?.rate??1};return kind==='dataset'?{kind,dataset:id.join(':')}:{kind:'twitch',source_id:id.join(':')}}
function stopLivePolling(){liveGeneration++;clearTimeout(liveTimer);liveTimer=null}
function syncLivePolling(){stopLivePolling();if(tab==='vision'&&!document.hidden)pollLive(liveGeneration)}
async function pollLive(generation){try{const response=await fetch('/api/live',{cache:'no-store'}),status=await response.json();if(!response.ok)throw Error(status.error||`HTTP ${response.status}`);if(generation!==liveGeneration)return;const latest=status.latest;const liveNode=$('#live-status');if(liveNode)liveNode.textContent=`${review()?.liveStateText?.(status.state)??status.state}${status.error?' · '+status.error:''} · ${liveText('Receive-to-result','接收到结果')}: ${latest?.receive_to_result_ms?.toFixed(0)??'—'} ms · ${liveText('Frame age','帧龄')}: ${status.frame_age_ms?.toFixed(0)??'—'} ms${status.frame_age_ms>2000?' · '+liveText('STALE','已过期'):''} · ${liveText('Dropped','丢帧')}: ${status.frames_skipped??0}`;
// The live tab's own panel carries the same numbers under its own id: the workbench's #live-status
// only exists once frames arrive, and a stale panel beside a live workbench would be a lie.
const panelNode=$('#live-panel-status');if(panelNode)panelNode.textContent=livePanelStatus();review()?.applyLiveStatus(status);liveSnapshot=status;const running=liveRunning();if(running!==liveWasRunning){liveWasRunning=running;if(tab==='vision'&&!reviewId)render()}if(status.state==='running'&&latest){const frame=await fetch('/api/live/frame',{cache:'no-store'});if(frame.ok){const meta=JSON.parse(frame.headers.get('X-Live-Metadata'));if(String(meta.seq)!==frame.headers.get('X-Live-Sequence'))throw Error('Frame sequence mismatch');const blob=await frame.blob();if(generation!==liveGeneration)return;const source=liveSource(liveChoice);review()?.ingestLiveFrame(URL.createObjectURL(blob),meta,{label:source.kind==='vod-replay'?liveSourceLabel(liveChoice):`● ${liveText('live','直播')} · ${liveSourceLabel(liveChoice)}`,channel:source.kind==='twitch'?channelOf(source.source_id):null})}}}catch(error){if(generation===liveGeneration)message(`${liveText('Live poll failed','直播轮询失败')}: ${error.message}`,true)}finally{if(generation===liveGeneration&&tab==='vision'&&!document.hidden)liveTimer=setTimeout(()=>pollLive(generation),500)}}
async function liveAction(action){stopLivePolling();const attempted=liveChoice;try{const payload=action==='start'?{action,source:liveSource(liveChoice),detectors:liveDetectors}:{action};const response=await fetch('/api/live',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),result=await response.json();if(!response.ok)throw Error(result.error||`HTTP ${response.status}`);visionAttempt=null;review()?.clearLiveError();review()?.applyLiveStatus(result)}catch(error){visionAttempt={source:attempted,error:error.message,at:Date.now()};review()?.setLiveAttempt(visionAttempt);review()?.applyLiveStatus({state:'error',error:error.message});message(error.message,true)}finally{syncLivePolling();renderSurface()}}
window.addEventListener('pagehide',stopLivePolling);
window.addEventListener('pageshow',()=>{syncLivePolling();syncOpsPolling()});
document.addEventListener('visibilitychange',()=>{syncLivePolling();syncOpsPolling()});
const review=()=>window.CornerPocketReview;
function canNavigate(){return !busy&&(!review()?.canLeave||review().canLeave())}
// Hash routes (IA C′): the URL names the screen, so a reload, back/forward and a bookmark land where the operator was.
// Old tab ids (and hashes written with them) map onto the same routes; anything unknown falls back to the default screen.
const navTabs=['tonight','records','vision','players','status'];
// One palette keyed by ball number, used wherever a ball is drawn (owner §13.3/§13.4):
// 1 yellow, 2 blue, 3 red, 4 pink, 5 orange, 6 green, 7 brown, 8 black, 9-15 the same
// seven hues as stripes. Past a full rack the number wraps, as it does on a real rack.
const ballPalette=['#f2c14e','#2f6fd0','#c8382f','#e885ad','#e07a29','#2f8f4e','#8a5a2b','#1b1b1b','#f2c14e','#2f6fd0','#c8382f','#e885ad','#e07a29','#2f8f4e','#8a5a2b'];
const ballNumber=n=>((Math.trunc(n)-1)%15+15)%15+1, ballColor=n=>ballPalette[ballNumber(n)-1], ballStripe=n=>ballNumber(n)>8?1:0;
// The geometry lives in ops.css (one lit sphere, an inset rim, a contact shadow, a white
// number plate); the per-number hue arrives as --ball-c, so the CSS keeps the material.
const ballHTML=(n,label)=>`<span class="ball"${ballStripe(n)?' data-stripe="1"':''} style="--ball-c:${ballColor(n)}"${label?` role="img" title="${esc(label)}" aria-label="${esc(label)}"`:''}><i>${ballNumber(n)}</i></span>`;
const routePaths={clock:'clock',tonight:'tonight',records:'records',vision:'vision',players:'regulars',status:'backroom'};
const legacyRoutes={setup:'tonight',floor:'tonight',matches:'tonight'};
function routeOf(value){const key=String(value??'').replace(/^#?\/*/,'').split(/[/?]/)[0].toLowerCase();if(legacyRoutes[key])return legacyRoutes[key];return Object.keys(routePaths).find(id=>id===key||routePaths[id]===key)||null}
// A night's recorded review has its own address under Records (#/records/review/<id>), so a
// reload, a bookmark or the back button lands back on the broadcast instead of the list.
function reviewRoute(){const m=String(location.hash||'').match(/^#\/records\/review\/([^/?]+)/);return m?decodeURIComponent(m[1]):null}
function navLabel(id){return id==='tonight'?t('tonightTab'):id==='clock'?t('shotTimer'):t(id)}
const comp=()=>tournament().status||'registration',liveComp=()=>comp()==='active',dirtyComp=()=>matches().some(m=>m.status==='live');
function tonightState(){const ms=matches();if(!ms.length)return entrants().length?'registration':'idle';return ms.every(m=>m.status==='complete')?'complete':'active'}
const primaryNav=()=>navTabs.slice();
// Round 9, owner item 2: the four-word state track is gone ("Registered Racked Playing Wrapping
// up"). Three of those four words are jargon and the fourth is a phase the operator is living in,
// so reading them in a row told nobody anything - the panels say what state the night is in. The
// line names the night now, and nothing else. sceneStep() and its two key maps went with it.
function scene(){const T=tournament();if(!matches().length&&!entrants().length)return `<section class="scene" role="status"><span class="scene-who">${esc(t('tonightTab'))} · ${esc(t('sceneIdle'))}</span></section>`;const named=(T.name||'').trim(),who=[esc(t('tonightTab')),esc(named||autoEventName())].join(' · '),note=named?'':` · ${esc(t('defaultNameNote'))}`,meta=` · ${esc(t(T.format==='doubles'?'doubles':'singles'))} · ${esc(t('raceN').replace('{n}',race()))}`;return `<section class="scene" role="status"><span class="scene-who">${who}${note}${meta}</span></section>`}
// Round 7, owner item 4: the setup fields exist in exactly one place (setupForm), and it is
// inside a dialog. With no event at all the Tournament tab is the registration page itself,
// dimmed and inert behind the start dialog - there is one thing to do, so nothing competes with
// it. Once an event exists the same dialog is the editor (open-setup), and the night card is
// what opens it.
function setupForm(first,closeable){const T=tournament(),locked=comp()!=='registration';return `<form id="settings-form"><fieldset class="bare"><div class="fields">${field(t('event'),input('name',T.name||autoEventName(),'text','required maxlength="120"'))}${locked?'':field(t('format'),`<select name="format">${['singles','doubles'].map(f=>option(f,t(f),T.format)).join('')}</select>`)+field(t('race'),`<select name="raceTo">${[1,3,5,7,9,11].map(n=>option(n,n,T.name?T.raceTo:1)).join('')}</select>`)+field(t('tables'),input('tables',T.tables,'number','min="1" max="32" required'))}</div><div class="actions mt-3"><button class="primary">${esc(first?t('startNightGo'):t('save'))}</button>${closeable?`<button type="button" data-action="dismiss-setup">${esc(t('closeLabel'))}</button>`:''}</div></fieldset></form>`}
function startModal(closeable){const T=tournament(),first=!T.id&&!String(T.name||'').trim(),note=first?t('startNote'):(comp()!=='registration'?t('locked'):'');return `<div class="modal-backdrop"${closeable?' data-action="dismiss-setup"':''}><div class="modal modal--start" role="dialog" aria-modal="true" aria-labelledby="start-title"><h3 id="start-title">${esc(first?t('startNight'):t('eventSettings'))}</h3>${note?`<p class="note">${esc(note)}</p>`:''}${setupForm(first,closeable)}</div></div>`}
// The page under the dialog is the registration page, and the tables stay resident inside it:
// they are the venue's furniture, not the event's (round 3), and a scrim over them costs nothing.
// Round 13, owner item 9: the competition tab is three elements - the event's card at the top, the
// draw, the entrants at the bottom. The card carries the identity line the tiles used to repeat, the
// door to the settings dialog, and the end-of-night actions that used to sit in a second card on the
// Back room (item 3). Nothing else on this tab talks about the event.
function eventCard(){const T=tournament(),drawn=matches().some(m=>m.sides.every(Boolean));return `<article class="card card--event"><div class="heading"><h3>${esc(t('eventSettings'))}</h3></div>${closeCard(drawn)}</article>`}
function panel(key,count,body){return `<details class="panel"><summary><h3>${esc(t(key))}</h3>${count?`<span class="muted">${count}</span>`:''}</summary>${body}</details>`}
// Round 13, owner items 3, 6 and 9. One body for every state the night can be in: the event card,
// the draw, the entrants. The scoreboard left this tab (item 6) - it is the timer page's board, and
// this tab answers "which group is on which table" inside the tree. The finish is the same three
// cards, so the tab no longer rearranges itself under the operator at the end of a night.
function tonightScreen(){const state=tonightState();if(sheetId){const night=[tournament(),...(data.history||[])].find(n=>n.id===sheetId);if(night)return `${scene()}${resultsSheet(night)}`;sheetId=null}const T=tournament(),body=setupOpen?startModal(true):(state==='idle'&&!T.id&&!String(T.name||'').trim()?startModal(false):playScreen());return `${scene()}<section class="stack tonight">${body}</section>`}
// Round 5: six slots in a 390 px phone bar is 62 px each, and the mono uppercase label the bar
// used before needed 80 px for "Tournament" (measured: four of six labels truncated). The phone
// bar is the one place the words may not be dropped, so each slot now stacks the destination's
// own ball over its label, and the stylesheet sets that label in the body face at 11 px, where
// "Tournament" measures 57. The ball is decorative - the button is named by the word.
function tabbarSlot(id,n){return '<button type="button" class="tabbar-slot" data-tab="'+id+'"'+(!bf&&tab===id?' aria-current="page"':'')+'><span class="tabbar-ball" aria-hidden="true">'+ballHTML(n)+'</span>'+esc(navLabel(id))+'</button>'}
function tabbarHTML(){return tabbarSlot('clock',1)+primaryNav().map((id,i)=>tabbarSlot(id,i+2)).join('')}
// Ball 1 is the timer's own door (owner item 2, ruled 2026-10-04): the bar above the nav runs the
// clock, this item opens the room-sized one. It is the only nav item that carries no count.
/* Ball 1's face in the destinations' bar is decorative - the button's own words name it - so
   it carries aria-hidden while keeping ballHTML's sphere. The rewrite of that opening tag has
   to leave the class attribute closed: without its closing quote the browser swallows the
   style attribute into the class list, --ball-c goes undefined, and a var() with no fallback
   takes the whole background-image down with it (measured live on 8130, 2026-10-04: the face
   painted the base and no band, and the default gold hid it until the base turned white). */
function clockNavButton(){const cur=!bf&&tab==='clock',face=ballHTML(1).replace('<span class="ball"','<span aria-hidden="true" class="ball"');return `<button data-tab="clock" class="${cur?'active':''}" aria-current="${cur?'page':'false'}" aria-keyshortcuts="Digit1" title="${esc(t('keyHintTimer').replace('{key}',t('digitKey').replace('{n}',1)))}">${face}${esc(t('shotTimer'))}</button>`}
// Round 12, owner item 1: the queue and the bracket were the same list read twice - the ready
// matches, the live tables and the signed results each sat in both cards, in two scroll boxes,
// and the drawer around them closed itself again after every write. One list, always open: a
// scheduled match is sent from its own card in the draw, where its table and its two names are.
function playScreen(){return `${eventCard()}${bracketScreen()}${revivalCard()}${entrantsCard()}`}
function eventFold(){const T=tournament();if(!entrants().length)return '';return '<details class="side-panel"><summary>'+esc(t('eventTable'))+'</summary><div class="table-wrap"><table class="event-table"><thead><tr><th>#</th><th>'+esc(t('name'))+'</th><th>'+esc(t('wins'))+'</th><th>'+esc(t('played'))+'</th><th>'+esc(t('winPct'))+'</th></tr></thead><tbody>'+eventTable(T).map((r,i)=>'<tr><td>'+(i+1)+'</td><td>'+esc(r.name)+'</td><td>'+r.wins+'</td><td>'+r.played+'</td><td>'+pct(r.wins,r.played)+'</td></tr>').join('')+'</tbody></table></div></details>'}
function matchId(form){const named=form?.elements?.id?.value||form?.querySelector?.('[name=id]')?.value;const id=(typeof named==='string'?named:'')||(typeof form?.id==='string'?form.id:'');if(!id)return null;return matches().find(m=>m.id===id)||{id}}

function closeCard(drawn){const T=tournament(),entrantN=(T.entrants||[]).length,signed=hasSigned(T),started=!!T.id,canDelete=started&&entrantN>0&&!signed,why=!started?t('closeNoEvent'):signed?t('closeSigned'):entrantN?'':t('closeNoEntrants');return `<div class="end-night"><div class="row">${btn(t('eventSettings'),'open-setup')}${drawn&&started?btn(t('resultsSheet'),'results-sheet',`data-id="${esc(T.id)}"`):''}${btn(t('new'),'new-event',started?'':'disabled')}${btn(t('deleteEvent'),'event-delete',`data-id="${esc(T.id)}"${canDelete?'':' disabled'}`,'danger')}</div>${why?`<p class="note close-why" role="status">${esc(why)}</p>`:''}</div>`}
function syncRoute(push){const hash=reviewId?`#/records/review/${encodeURIComponent(reviewId)}`:(tab==='tonight'?'#/tonight':`#/${routePaths[tab]}`);if(location.hash!==hash)history[push?'pushState':'replaceState'](null,'',hash)}
function go(next){if(!next||!canNavigate())return false;tab=next;bf=null;sheetId=null;recordId=null;reviewId=null;syncRoute(true);render();return true}
// A night's row on Records opens that broadcast's recorded review. The tab does not move: the
// review lives under Records, so the nav keeps telling the operator where its entrance was.
function openReview(id){reviewId=String(id);sheetId=null;bf=null;tab='records';syncRoute(true);render();window.scrollTo?.(0,0)}
window.addEventListener('hashchange',()=>{const next=routeOf(location.hash)||'tonight',wasReview=reviewId;reviewId=reviewRoute();if((next!==tab||reviewId!==wasReview)&&canNavigate()){tab=next;sheetId=null;recordId=null;render()}syncRoute(false)});
tab=routeOf(location.hash)||tab;reviewId=reviewRoute();syncRoute(false);
async function showReview(){const host=$('#vision-host');if(!host)return;const isActive=reviewHosted();const slot=document.getElementById('vs-frame');if(slot&&host.parentElement!==slot)slot.appendChild(host);host.hidden=!isActive;if(!isActive){review()?.deactivate();return}try{if(!reviewPromise)reviewPromise=(async()=>{const response=await fetch('/api/review-template');if(!response.ok)throw Error(`HTTP ${response.status}`);const parsed=new DOMParser().parseFromString((await response.json()).html,'text/html');const root=parsed.querySelector('#review-root');if(!root)throw Error('Review markup is unavailable');root.dataset.embedded='true';root.hidden=false;const placeholder=root.querySelector('#content .empty');if(placeholder){placeholder.textContent=t('visionLoading');placeholder.setAttribute('role','status')}if(!host.querySelector('#review-root'))host.appendChild(document.importNode(root,true));await review().mount(host.querySelector('#review-root'),{reloadRoster:()=>reload()});review().activate('timeline');attachSurface();review().loadPersons().then(()=>review().loadTracks()).catch(()=>{})})();await reviewPromise;if(isActive){review().setAppearance(lang,theme);review().activate(reviewState().focus||'timeline');const want=datasetForVod(broadcastVodId());if(want&&reviewState().dataset!==want&&want!==vodDatasetAsked){vodDatasetAsked=want;review()?.setDataset?.(want)}}renderSurface()}catch(error){reviewPromise=null;message(`${t('error')}: ${error.message}`,true)}}
let timer;try{timer=JSON.parse(localStorage.getItem('cp-ops-clock'))}catch{}if(!timer||!Number.isFinite(timer.remaining))timer={duration:30,remaining:30,deadline:null};
const t=k=>words[k]?.[lang==='zh'?1:0]??k, btn=(label,action,attrs='',kind='')=>`<button type="button" class="${kind}" data-action="${action}" ${attrs}>${esc(label)}</button>`,badge=(status)=>`<span class="badge ${esc(status)}">${esc(t(status))}</span>`,isBye=m=>m.result==='bye',mbadge=m=>badge(isBye(m)?'bye':m.status),sideName=(m,id)=>!id&&isBye(m)?'—':ename(id),field=(label,html)=>`<label><span>${esc(label)}</span>${html}</label>`,input=(name,value='',type='text',extra='')=>`<input name="${name}" type="${type}" value="${esc(value)}" ${extra}>`,option=(v,label,current)=>`<option value="${esc(v)}" ${String(current)===String(v)?'selected':''}>${esc(label)}</option>`,tiles=items=>`<div class="tiles">${items.map(([label,value,note])=>`<div class="tile"><small>${esc(label)}</small><strong>${esc(value)}</strong>${note?`<span class="tile-note">${esc(note)}</span>`:''}</div>`).join('')}</div>`
const tournament=()=>data.tournament, entrants=()=>tournament().entrants||[], matches=()=>data?.tournament?.matches||[], player=id=>data.players.find(p=>p.id===id), entrant=id=>entrants().find(e=>e.id===id),ename=id=>{const e=entrant(id);return e?(e.members||[]).map(m=>player(m.pid)?.name||m.name||t('unknown')).join(' / '):t('pending')},live=()=>matches().find(m=>m.id===focusId&&['live','delayed'].includes(m.status))||matches().find(m=>m.status==='live')||matches().find(m=>m.status==='delayed'),race=()=>tournament().raceTo||7,guestPeople=()=>[...new Set(entrants().flatMap(e=>(e.members||[]).filter(m=>!m.pid).map(m=>m.name)))],roster=()=>data.players.slice().sort((a,b)=>b.rating-a.rating),allowed=()=>!busy&&data;
const validationZh={'Player name already exists':'球员姓名已存在。','The pairing changed; review the teams again':'配对已变化，请重新查看组合。','An even number of solo players is needed to pair':'需要偶数名单人报名者才能配对。','Registration is locked while a pairing is shown; accept or clear it first':'正在显示配对结果，请先采用或清除。','Random pairing is for doubles':'随机配对仅用于双打。','No pairing to accept':'没有可采用的配对。','Remove solo players before changing format':'请先移除单人报名者，再更改赛制。','No round-2 bye slot to fill':'没有可填补的第二轮轮空位。','No round-1 loser to draw from':'首轮没有可抽取的负者。','Finish round 1 first; every round-1 loser must be in the draw':'请先完成首轮，所有首轮负者都要参加抽签。','Round 2 has a signed result; the draw is closed':'第二轮已有签署的赛果，抽签已关闭。','A second chance was already drawn for this event':'本场赛事已经抽过复活名额。','Undo is closed: a result has been signed since the draw':'抽签后已有新的签署赛果，无法撤销。','No revival draw to undo':'没有可撤销的复活抽签。','An event with a signed result cannot be deleted; hide it from history instead':'有已签赛果的赛事不能删除，请改为从历史中隐藏。','Only an archived event can be hidden':'只能隐藏已归档的赛事。',"A bye is added by the draw; type the guest's real name":'轮空由抽签自动安排，请输入访客的真实姓名。','Name held by a guest in this event; add the guest to the regulars instead':'这个名字属于本场赛事的一位访客；请把该访客加入常客，而不是给常客改成同名。','Player name already exists; select the regular by id':'该姓名已属于常客，请从常客名单选择。','Player name already exists; cannot infer guest identity':'该姓名已存在，无法确定访客身份。','Player has tournament history; mark Inactive instead':'球员已有赛事记录，请改为停用而非删除。','Remove entrants before changing format':'请先移除参赛者，再更改赛制。','Tournament already started':'赛事已经开始。','Registration is closed':'报名已关闭。','Person already registered':'此人已经报名。','Inactive player':'该球员已停用。','Need an unstarted tournament with at least two entrants':'请至少登记两名参赛者，并确保赛事尚未开始。','Wrong number of team members':'队伍人数不符合赛制。','Maximum 128 entrants':'最多允许128名参赛者。','Match is not editable':'此比赛当前不可编辑。','Absent player; match held':'有球员缺席，比赛暂缓。','Table is occupied':'球台已被占用。','All tables are in use':'所有球台都在使用中，请先释放一张球台。','Source already added':'这个直播源已经添加过了。','image_base64 is not a decodable image':'无法读取这张图片，请换一张 JPEG 或 PNG 照片。','Use a Twitch channel or videos/<digits> URL':'请输入Twitch频道网址或 videos/<数字> 视频网址。','Match is not on a table':'此比赛尚未上台。','Schedule match before scoring':'请先安排比赛上台，再记录比分。','Two scores required':'请填写双方比分。','Both players cannot win':'双方不能同时达到获胜比分。','A live race-winning score is required':'请先填写进行中比赛的有效获胜比分。','Explicit confirmation required':'需要明确确认此操作。','Unknown id':'找不到此记录，请刷新后重试。','Invalid format':'赛制无效。','Invalid player status':'球员状态无效。','Player notes must be text up to 4000 characters':'球员备注最多4000字。','State changed; reload before retrying':'数据已被修改，请刷新后重试。','Use an HTTPS Twitch channel or video URL without query parameters':'请输入不带查询参数的HTTPS Twitch频道或视频网址。'};
function validationMessage(detail){return lang==='zh'?(validationZh[detail]||'请求未被接受，请检查输入或展开技术详情。'):detail}
function message(text,error=false,detail=''){$('#message').textContent=text;$('#message').className=error?'error':'';if(detail)$('#message').innerHTML=`${esc(text)}<details><summary>${lang==='zh'?'技术详情':'Technical details'}</summary><code>${esc(detail)}</code></details>`;clearTimeout(message.timeout);message.timeout=setTimeout(()=>{$('#message').textContent=''},error?12000:4500)}
async function reload(){try{const r=await fetch('/api/operations',{cache:'no-store'});if(!r.ok)throw Error(`HTTP ${r.status}`);data=await r.json();$('#connection').hidden=true;render()}catch(e){$('#connection').hidden=false;$('#connection').textContent=t('connectionLost');message(`${t('error')}: ${e.message}`,true);if(!data)$('#main').innerHTML=`<article><h2>${esc(t('connectionLost'))}</h2><p>${esc(e.message)}</p>${btn(t('refresh'),'reload')}</article>`}}
// Overdrive A (instant bracket). Match writes go through one queue per match. A score step is
// drawn at once and marked pending; a signature is only marked pending. Any refusal restores the
// exact pre-write snapshot; the server's answer always has the last word.
const matchQueues=new Map(),pendingMatches=new Map();
const isPending=id=>pendingMatches.has(id);
// A repaint is a view: if it throws (a detached tab, a test harness), the write still happens.
const paint=()=>{try{render()}catch(e){console.warn('repaint skipped',e)}};
function matchWrite(id,name,build){const run=async()=>{const m=data?.tournament?.matches?.find(x=>x.id===id);const {payload,apply}=build(m||{score:[0,0]});const snapshot=JSON.parse(JSON.stringify(data));pendingMatches.set(id,(pendingMatches.get(id)||0)+1);if(apply&&m)apply(m);paint();try{return await action(name,{id,...payload},{snapshot})}finally{const n=pendingMatches.get(id)-1;if(n>0)pendingMatches.set(id,n);else pendingMatches.delete(id);paint()}};const next=(matchQueues.get(id)||Promise.resolve()).then(run,run);matchQueues.set(id,next.then(()=>{},()=>{}));return next}
async function action(name,payload={},opts={}){const queued=!!opts.snapshot;if(!queued&&!allowed())return false;if(!queued){busy=true;document.querySelectorAll('#main button').forEach(b=>b.disabled=true)}try{const r=await fetch('/api/operations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:data.revision,action:name,...payload})});const result=await r.json();if(r.status===409){if(queued)data=opts.snapshot;await reload();throw Error(t('conflict'))}if(!r.ok){const detail=result.error||result.message||`HTTP ${r.status}`;throw Object.assign(Error(validationMessage(detail)),{detail})}data=result;if(['match_complete','match_forfeit','tournament_new','tournament_start'].includes(name)){timer.remaining=timer.duration;timer.deadline=null;persistClock()}render();message(t('saved'));return true}catch(e){if(queued&&e.message!==t('conflict'))data=opts.snapshot;if(queued&&e instanceof TypeError){message(t('netRolledBack'),true,e.message);render();return false}message(`${t('error')}: ${e.message}`,true,e.detail);render();return false}finally{if(!queued){busy=false;document.querySelectorAll('#main button').forEach(b=>b.disabled=false)}}}
function persistClock(){localStorage.setItem('cp-ops-clock',JSON.stringify(timer))}function clockLeft(){return timer.deadline?Math.max(0,(timer.deadline-Date.now())/1000):timer.remaining}
// One clock, one formatter. Every view (all six tabs, the Vision stagebar on
// mobile, the floor scoreboard, a second tab) paints from these and the single
// interval writes with them, so a re-render can never show a different instant -
// which is what hardcoding the initial '0:30' did.
function clockText(left){const s=Math.max(0,Math.ceil(left));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`}
function clockLow(left){return left<=5}
// The bar scales instead of resizing: transform is composited, width re-lays out the row every tick.
function clockScale(left){return Math.max(0,Math.min(1,left/timer.duration)).toFixed(4)}
function clockToggle(){const left=clockLeft();timer.remaining=left>0?left:timer.duration;timer.deadline=timer.deadline?null:Date.now()+timer.remaining*1000;persistClock();render()}
function clockHTML(){const left=clockLeft(),running=!!timer.deadline;return `<strong class="clock${clockLow(left)?' low':''}" data-clock>${esc(clockText(left))}</strong>${btn(t(running?'pause':'start'),'clock-toggle',`aria-keyshortcuts="Digit1" title="${esc(t('keyHintTimer').replace('{key}',t('digitKey').replace('{n}',1)))}"`)}${btn(t('reset'),'clock-reset')}<span class="presets" role="group" aria-label="${esc(t('shotTimer'))}">${[20,30,45,60].map(n=>btn(n,'clock-set',`data-value="${n}"`,timer.duration===n?'preset active':'preset')).join('')}</span><span class="sync-error" hidden></span><span class="progress"><span data-progress style="transform:scaleX(${clockScale(left)})"></span></span>`}
// Round 7, owner item 2: the timer's home is markup - <div class="clockbar" data-clock-host> is
// the header's first row in annotator/ops.html - because a bar that is always on screen must
// exist before clock-sync.js looks for it, and render() must not be able to replace it.
// The owner ruled on 2026-10-04: the bar is the instrument, the tab is the door. So the bar holds
// the clock and its controls and nothing else, and ball 1 is the timer's own destination in the
// nav and in the phone's bottom bar again. One badge, one job: the bar never doubles as a tab.
function paintClockSlot(){const slot=$('#ops-shell .clockbar');if(slot)slot.innerHTML=clockHTML()}
// Item 4: the timer's own screen - the night's clock, readable from across the room. Round 7,
// owner item 3: the browser-local disclosure line is gone; the clock is a clock.
function clockScreen(){const left=clockLeft(),running=!!timer.deadline;return `<section class="stack"><article class="timer-card"><h2>${esc(t('shotTimer'))}</h2><p class="timer-face"><strong class="clock${clockLow(left)?' low':''}" data-clock>${esc(clockText(left))}</strong></p><span class="timer-progress" role="progressbar" aria-label="${esc(t('shotTimer'))}" aria-valuemin="0" aria-valuemax="${timer.duration}" aria-valuenow="${Math.round(left)}"><span data-progress style="transform:scaleX(${clockScale(left)})"></span></span><div class="timer-controls"><button type="button" class="primary" data-action="clock-toggle" aria-keyshortcuts="Digit1">${esc(t(running?'pause':'start'))}</button><button type="button" data-action="clock-reset">${esc(t('reset'))}</button><span class="presets" role="group" aria-label="${esc(t('shotTimer'))}">${[20,30,45,60].map(n=>btn(n,'clock-set',`data-value="${n}"`,timer.duration===n?'preset active':'preset')).join('')}</span></div></article>${liveComp()?scoreboardScreen():''}</section>`}
// The clock is the one always-available element (owner §13.1): it paints before the first
// fetch answers and in every venue state, because nothing here reads comp().
paintClockSlot();function tick(){const left=clockLeft();document.querySelectorAll('[data-clock]').forEach(e=>{const text=clockText(left);if(e.textContent!==text)e.textContent=text;e.classList.toggle('low',clockLow(left))});document.querySelectorAll('[data-progress]').forEach(e=>e.style.transform=`scaleX(${clockScale(left)})`);if(timer.deadline&&left===0){timer.remaining=0;timer.deadline=null;persistClock();render();message(lang==='zh'?'击球时间到。未自动判罚。':'Shot time expired. No penalty applied.')}}
const screens={clock:clockScreen,tonight:tonightScreen,records:recordsScreen,vision:liveVisionScreen,players:playersScreen,status:statusScreen};
function render(){stopLivePolling();stopOpsPolling();if(!data)return;document.documentElement.lang=lang==='zh'?'zh-CN':'en';document.documentElement.dataset.theme=theme;$('#nav').innerHTML=clockNavButton()+primaryNav().map((k,i)=>{const cur=!bf&&tab===k,key=String(i+2);return `<button data-tab="${k}" class="${cur?'active':''}" aria-current="${cur?'page':'false'}" aria-keyshortcuts="Digit${key}" title="${esc(t('keyHint').replace('{key}',t('digitKey').replace('{n}',key)))}">${ballHTML(i+2)}${esc(navLabel(k))}<small>${k==='tonight'?(matches().length?matches().filter(m=>m.status!=='complete').length:entrants().length):k==='players'?data.players.length:''}</small></button>`}).join('');const tb=$('#tabbar');if(tb)tb.innerHTML=tabbarHTML();const m=live();$('#ops-shell').dataset.tab=bf?'backfill':tab;$('#ops-shell').dataset.lang=lang==='zh'?'zh':'en';$('#ops-shell').dataset.vision=reviewId?'recorded':(tab==='vision'?'live':'');paintClockSlot();const host=$('#vision-host');if(host&&host.parentElement!==document.body)document.body.appendChild(host);visionAdapter?.detach();visionAdapter=null;$('#main').innerHTML=(bf?bfScreen():screens[tab]())+(sourceOpen?sourceModal():'');liveWasRunning=liveRunning();$('#main').classList.toggle('short',reviewHosted());showReview();syncLivePolling();syncOpsPolling();if(tab==='records'&&!bf){loadArchiveList();loadAuto()}document.querySelectorAll('[data-lang]').forEach(b=>{b.classList.toggle('active',b.dataset.lang===lang);b.setAttribute('aria-pressed',String(b.dataset.lang===lang))});document.querySelectorAll('#ops-shell button[data-theme]').forEach(b=>{b.classList.toggle('active',b.dataset.theme===theme);b.setAttribute('aria-pressed',String(b.dataset.theme===theme))});document.querySelector('[data-theme-group]')?.setAttribute('aria-label',lang==='zh'?'配色 / Color theme':'Color theme / 配色');document.querySelector('#vision-host')?.setAttribute('aria-label',lang==='zh'?'视觉复核':'Vision review');tick()}
// Round 12, owner item 2: the match follows the night onto the timer's own page. The desk sends a
// match and signs a frame; the tablet at the table only ever reads, so this page re-reads the
// document the desk writes, four seconds at a time - and never while a hand is mid-sentence: it
// never writes, it runs only on this tab while a night is played, and it stands down while the
// page is hidden or a form, a dialog or a picker is open on it.
let sourceOpen=false,opsTimer=null;
function stopOpsPolling(){clearTimeout(opsTimer);opsTimer=null}
function syncOpsPolling(){stopOpsPolling();if(tab==='clock'&&liveComp()&&!document.hidden)opsTimer=setTimeout(pollOps,4000)}
async function pollOps(){opsTimer=null;if(tab!=='clock'||!liveComp()||document.hidden)return;if(!busy&&!bf&&!pendingMatches.size&&deskOpen===null&&!selected&&!setupOpen){try{const response=await fetch('/api/operations',{cache:'no-store'});if(response.ok){const next=await response.json();if(next.revision!==data?.revision&&!busy&&!pendingMatches.size){data=next;render();return}}}catch(error){/* the desk owns the truth; a failed read changes nothing here */}}syncOpsPolling()}
// It lives below render() for a reason: the clock bar paints in every venue state and reads no
// match state (round 7's rule), and that rule is only true while the poll is not part of it.
// Onboard: before the first match exists, the Floor says what to do first, from real state:
// regulars (optional), entrants, rack the night. Each step is the tab button that does it.
function scoreboardScreen(){const m=live();return `<article class="scoreboard${m&&isPending(m.id)?' pending':''}"${m&&isPending(m.id)?' aria-busy="true"':''}>${m&&isPending(m.id)?`<p class="pending-note" role="status">${esc(t('savingNow'))}</p>`:''}<h2 class="sr-only">${esc(t('scoreboardTitle'))}</h2><div class="score-top row">${badge(m?.status||'pending')}<span class="muted grow">${esc(m?`${t('table')} ${m.table||'—'} · ${m.id.slice(0,8)}`:t('noMatch'))}</span>${race()===1?badge('single'):`<span class="badge race">${esc(t('raceN').replace('{n}',race()))}</span>`}${matches().filter(x=>['live','delayed'].includes(x.status)).length>1?`<select id="focus-match" aria-label="${esc(t('focusMatch'))}">${matches().filter(x=>['live','delayed'].includes(x.status)).map(x=>option(x.id,`${t('table')} ${x.table||'—'} · ${ename(x.sides[0])} / ${ename(x.sides[1])}`,m?.id)).join('')}</select>`:''}</div>${m?'':`<p class="empty-note board-empty">${esc(t(matches().some(x=>x.status==='scheduled'&&x.sides.every(Boolean))?'boardEmptySend':matches().length?'boardEmptyWait':'boardEmptyNoDraw'))}</p>`}${[0,1].map(i=>`${i?'<div class="vs">vs</div>':''}<div class="side ${m&&m.score[i]>m.score[1-i]?'leading':''}"><div><small>${esc(i===0?'A':'B')}</small><strong class="name"${m?'':' aria-hidden="true"'}>${esc(m?ename(m.sides[i]):'—')}</strong>${race()>1?`<div class="pips">${Array.from({length:race()},(_,n)=>`<i class="pip ${n<(m?.score[i]||0)?'on':''}"></i>`).join('')}</div>`:''}</div><div class="row">${race()>1?`<strong class="digits">${m?.score[i]||0}</strong><div class="score-buttons">${btn('+','score',`data-id="${m?.id||''}" data-side="${i}" data-delta="1" ${!m?'disabled':''} aria-label="${esc(ename(m?.sides[i]))} +1"`,'primary')}${btn('−','score',`data-id="${m?.id||''}" data-side="${i}" data-delta="-1" ${!m?'disabled':''} aria-label="${esc(ename(m?.sides[i]))} -1"`)}</div>`:btn(t('win'),'frame',`data-id="${m?.id||''}" data-side="${i}" ${!m?'disabled':''}`,'primary')}</div></div>`).join('')}${m?`<div class="score-foot row"><span class="grow muted">${esc(t('manual'))}</span>${btn(t('clear'),'clear',`data-id="${m.id}"`)}${m.status==='live'?btn(t('releaseTable'),'unschedule',`data-id="${m.id}"`):''}${btn(t('sign'),'sign',`data-id="${m.id}"`,'primary')}</div>`:''}</article>`}
// Round 9, owner item 3: the Tournament tab lost four blocks. The Tables grid went first - every
// card in it restated a match the Waiting-to-play panel already shows, and "Send next -> T4"
// (which sent a match to a *named* table) was the one thing it could do that nothing else could;
// the queue's own Send button asks the server to place the match on a free table, which is the
// same job without the operator having to pick a number. tableCard(), tablesGrid(), tablesArea()
// and the Event table + Scorekeeper's card pair (tonightPanel()) went with it: the event table
// still lives inside the Waiting-to-play panel as a fold, and the scorekeeper's card duplicated
// the scoreboard's +/- and Sign. guestsTonight() was the fourth - every guest it listed is
// already an entrant above it, with the same Promote button next to them.
// Round 13, owner item 5: being away is gone. Attendance was a second door onto the draw, and the
// operator can always send anyone to a table. The match controls are the forfeit, and nothing else.
function matchControls(m){if(m.status==='complete'||m.status==='pending'||!m.sides.every(Boolean))return '';return `<div class="row match-controls">${[0,1].map(i=>btn(`${t('forfeit')}: ${ename(m.sides[i])}`,'forfeit',`data-id="${m.id}" data-side="${i}"`,'danger')).join('')}</div>`}
// Round 10, owner items 1 and 2: the entry list is a list, not a second Regulars tab and not a
// second place to say who is here. "Manage regulars" pointed at the tab the nav already gives a
// ball to. Being not here is a fact about one matchup, and the operator marks it where that
// matchup is - matchControls() puts a Here / Not here button on each side, and the scoreboard's
// waiting row carries the same button while the match is held. So the card keeps the ball, the
// name, Guest or member, Promote and Remove, and nothing else.
// Round 13, owner item 9: the desk moved in here, because it is about entrants, and the start
// button sits with the list it starts from. The pairing card for doubles sits above the form.
function entrantsCard(){const T=tournament(),locked=comp()!=='registration',desk=locked?'':(T.format==='doubles'?pairingCard(T):'')+(T.pairing?'':`<form id="entrant-form"><div class="fields">${Array.from({length:T.format==='doubles'?2:1},(_,i)=>deskSlot(i)).join('')}</div><div class="row"><button>${esc(t('add'))}</button>${T.format!=='doubles'?`<button type="button" class="primary" data-action="tournament-start">${esc(t('startEvent'))}</button>`:''}</div><p class="grow muted">${esc(t('rackHint'))}</p></form>`)+(T.pairing?`<div class="row"><button type="button" class="primary" data-action="tournament-start">${esc(t('startEvent'))}</button></div>`:'');return `<article class="card card--entrants"><div class="heading"><h3>${esc(t('entrants'))}</h3><span class="muted">${entrants().length} · ${guestPeople().length} ${esc(t('guests'))}</span></div>${desk}<div class="grid">${entrants().map((e,i)=>`<div class="entry row">${ballHTML(i+1)}<span class="grow">${esc(ename(e.id))}<small>${esc(e.members.some(m=>!m.pid)?t('guest'):t('member'))}</small></span>${e.members.some(m=>!m.pid)?btn(t('promote'),'promote',`data-name="${esc(ename(e.id))}"`):''}${locked?'':btn(t('remove'),'entrant-remove',`data-id="${e.id}"`)}</div>`).join('')||emptyNote('emptyEntrants')}</div>${eventFold()}</article>`}
/* Round 9, owner item 4: "combine the dropdown for selecting regular. only show name box when
   selecting guest. use custom dropdown." The old desk put a search box, a native <select> of the
   whole roster and a guest-name field in front of the operator for every entrant, and the search
   box filtered nothing but that select's options. This is one control instead: the button shows
   the pick (a regular's name and rating, or the word for a guest), the panel holds the search and
   the rows, and the guest-name field is rendered exactly when no regular is picked. The state
   lives outside the DOM (deskPick/deskOpen/deskDraft) because every interaction re-renders the
   screen; readDeskDraft() copies what has been typed back into it first, and the panel's own
   rows are filtered in place so the search box keeps its focus and its caret. */
let deskPick={0:'',1:''},deskOpen=null,deskDraft={0:{q:'',guest:''},1:{q:'',guest:''}};
function deskFree(){const taken=new Set(entrants().flatMap(e=>(e.members||[]).map(m=>m.pid)).filter(Boolean));return roster().filter(p=>!taken.has(p.id))}
function deskSlot(i){
  const free=deskFree(),picked=deskPick[i]||'',draft=deskDraft[i]||{q:'',guest:''},q=draft.q||'',open=deskOpen===i;
  const chosen=free.find(p=>p.id===picked),hits=free.filter(p=>nameMatches(p.name,q));
  const rows=`<button type="button" role="option" aria-selected="${picked?'false':'true'}" class="pick-row${picked?'':' on'}" data-action="desk-pick" data-desk="${i}" data-id="">${esc(t('guest'))}<small>${esc(t('guestName'))}</small></button>`
    +free.map(p=>`<button type="button" role="option" aria-selected="${picked===p.id?'true':'false'}" class="pick-row${picked===p.id?' on':''}" data-action="desk-pick" data-desk="${i}" data-id="${esc(p.id)}" data-name="${esc(p.name)}"${nameMatches(p.name,q)?'':' hidden'}>${esc(p.name)}<small>${esc(String(p.rating))}</small></button>`).join('');
  const searchCount=t('searchCount').replace('{n}',String(hits.length)).replace('{m}',String(free.length));
  return `<div class="stack desk">
    <span class="desk-label">${esc(t(i?'partner':'member'))}</span>
    <div class="pick">
      <button type="button" class="pick-btn${open?' open':''}" data-action="desk-open" data-desk="${i}" aria-haspopup="listbox" aria-expanded="${open?'true':'false'}" aria-controls="desk-list${i}"><span class="grow">${esc(chosen?`${chosen.name} · ${chosen.rating}`:t('guest'))}</span><span class="pick-caret" aria-hidden="true">▾</span></button>
      ${open?`<div class="pick-panel" id="desk-list${i}" role="listbox" aria-label="${esc(t('pick'))}" data-total="${free.length}">
        <input class="pick-search" data-desk="${i}" type="search" autocomplete="off" value="${esc(q)}" placeholder="${esc(t('deskSearch'))}" aria-label="${esc(t('deskSearch'))}" aria-controls="desk-list${i}">
        <p class="muted pick-count"${q.trim()?'':' hidden'}>${esc(searchCount)}</p>
        <div class="pick-rows">${rows}</div>
      </div>`:''}
    </div>
    <input type="hidden" name="pid${i}" id="desk-pid${i}" value="${esc(picked)}">
    ${picked?'':field(t('guestName'),input(`guest${i}`,draft.guest,'text','maxlength="120" autocomplete="off"'))}
  </div>`}
function readDeskDraft(){const form=document.getElementById('entrant-form');if(!form)return;form.querySelectorAll('.desk').forEach((slot,i)=>{const box=slot.querySelector('.pick-search'),guest=slot.querySelector(`input[name="guest${i}"]`);deskDraft[i]={q:box?box.value:(deskDraft[i]?.q||''),guest:guest?guest.value:(deskDraft[i]?.guest||'')}})}
const auditActions={match_unschedule:['Table released','释放球台'],entrant_absence:['Registration attendance changed','报名到场状态变更'],player_save:['Player saved','保存球员'],player_delete:['Player deleted','删除球员'],guest_promote:['Guest added to regulars','访客转为常客'],tournament_setup:['Event settings saved','保存赛事设置'],entrant_add:['Entrant registered','参赛报名'],entrant_remove:['Entrant removed','移除参赛者'],tournament_start:['Draw started','生成对阵'],match_schedule:['Match sent to table','比赛上台'],match_score:['Score updated','更新比分'],match_complete:['Result signed','签署赛果'],match_absence:['Attendance changed','到场状态变更'],match_forfeit:['Forfeit recorded','记录弃权'],tournament_new:['Event archived / new event','归档并新建赛事'],tournament_rename:['Event renamed','赛事已重命名'],tournament_delete:['Event deleted (nothing was signed)','删除赛事（无已签赛果）'],tournament_hide:['Event hidden / shown in history','赛事在历史中隐藏 / 恢复'],revival_draw:['Second chance drawn (random, audited)','复活赛抽签（随机，已记录）'],revival_undo:['Second chance undone','撤销复活赛抽签'],solo_add:['Solo player signed up','单人报名'],pool_remove:['Solo player removed','移除单人报名'],pair_draw:['Partners drawn at random','随机抽取搭档'],pair_clear:['Random pairing cleared','清除随机配对'],pair_accept:['Random pairs registered','随机组合已报名'],source_add:['Source saved','保存来源'],source_delete:['Source removed','删除来源'],settings_update:['Settings updated','更新设置'],note_add:['Note added','添加备注'],note_delete:['Note removed','删除备注'],event_backfill:['Backfilled from a VOD','VOD 补录']};;
// Who or what an audit line is about, in words. The server's context carries a name for
// players, events and pairings; for entrants, sources, matches and notes it carries only an id,
// so the name is looked up in tonight's state, then in archived nights. Nothing is guessed: an
// id that no longer resolves reads as a plain phrase, and the id itself stays in the title.
function auditNights(){return [tournament(),...(data.history||[])].filter(Boolean)}
function auditEntrantName(id){for(const n of auditNights()){const e=(n.entrants||[]).find(x=>x.id===id);if(e)return (e.members||[]).map(m=>player(m.pid)?.name||m.name).filter(Boolean).join(' / ')||null}return null}
function auditSubject(e){const c=e.context||{},a=String(e.action||''),id=c.id;
if(c.name)return c.name;
if(Array.isArray(c.teams)&&c.teams.length)return c.teams.join(' · ');
if(a.startsWith('entrant_'))return (id&&auditEntrantName(id))||t('auditGoneEntrant');
if(a.startsWith('source_')){const s=(data?.sources||[]).find(x=>x.id===id);return s?.url||t('auditSource')}
if(a.startsWith('match_')){for(const n of auditNights()){const m=(n.matches||[]).find(x=>x.id===id);if(m){const names=m.sides.map(s=>s&&auditEntrantName(s));if(names.every(Boolean))return names.join(' – ')}}return t('auditMatch')}
if(a.startsWith('player_')){const p=id&&player(id);return p?.name||t('auditGonePlayer')}
if(a.startsWith('note_'))return t('auditNote');
if(a.startsWith('revival_')){const n=c.entrant&&auditEntrantName(c.entrant);return n||''}
return ''}
function auditTitle(e){const c=e.context||{};return [c.id,c.entrant].filter(Boolean).map(String).join(' · ')}
function auditLine(e){const label=auditActions[e.action]?.[lang==='zh'?1:0]||e.action;const who=auditSubject(e);return `${dateLine(e.createdAt)} · ${label}${who?` · ${who}`:''} · v${e.revision}`}
function nightName(night,eid){const e=(night.entrants||[]).find(e=>e.id===eid);return e?(e.members||[]).map(m=>player(m.pid)?.name||m.name||t('unknown')).join(' / '):t('tbd')}
function roundTitle(night,r){const last=Math.max(0,...(night.matches||[]).map(m=>m.round));return r===last&&r>1?t('final'):`${t('round')} ${r}`}
function champion(night){const f=(night.matches||[]).at(-1);return f&&f.status==='complete'&&f.winnerId?nightName(night,f.winnerId):null}
function resultLine(night,m){const n=id=>nightName(night,id),w=m.winnerId,l=m.sides.find(id=>id&&id!==w);if(isBye(m))return t('byeLine').replace('{a}',n(w));if(m.status!=='complete')return t('notPlayedLine').replace('{a}',n(m.sides[0])).replace('{b}',n(m.sides[1]));if(m.result==='forfeit')return t('forfeitLine').replace('{w}',n(w)).replace('{l}',n(l));const i=m.sides.indexOf(w);return `${n(w)} ${m.score[i]}–${m.score[1-i]} ${n(l)}`}
function revivalLine(night){const r=night.revival;return t('revivalLine').replace('{name}',nightName(night,r.entrant)).replace('{seed}',r.seed).replace('{n}',r.attempt||1)}
function resultsText(night){const rounds=[...new Set((night.matches||[]).map(m=>m.round))].sort((a,b)=>a-b),c=champion(night);return [`${night.name||t('unnamed')} · ${fmtDate(night.archivedAt||night.matches?.find(m=>m.completedAt)?.completedAt||new Date().toISOString())}`,`${t(night.format||'singles')} · ${(night.raceTo||1)===1?t('single'):t('raceN').replace('{n}',night.raceTo)}`,c?t('championLine').replace('{c}',c):t('noChampion'),...(night.revival?[revivalLine(night)]:[]),'',...rounds.flatMap(r=>[roundTitle(night,r),...(night.matches||[]).filter(m=>m.round===r).map(m=>resultLine(night,m)),'']),t('sheetNote')].join('\n')}
function resultsSheet(night){const rounds=[...new Set((night.matches||[]).map(m=>m.round))].sort((a,b)=>a-b),c=champion(night);return `<section class="stack results-sheet"><div class="row no-print">${btn(t(tab==='records'?'sheetBackRecords':'sheetBack'),'sheet-back')}${btn(t('printSheet'),'print-sheet','','primary')}${btn(t('copyResults'),'copy-results',`data-id="${esc(night.id)}"`)}</div><article><h2>${esc(night.name||t('unnamed'))}</h2><p class="muted">${esc(resultsText(night).split('\n')[0].split(' · ').slice(1).join(' · '))} · ${esc(resultsText(night).split('\n')[1])}</p><p class="champion"><small>${esc(t('champion'))}</small><strong>${esc(c||t('notDecided'))}</strong></p>${night.revival?`<p class="muted">${esc(revivalLine(night))}</p>`:''}</article><div class="sheet-rounds">${rounds.map(r=>`<article class="sheet-round"><h3>${esc(roundTitle(night,r))}</h3>${(night.matches||[]).filter(m=>m.round===r).map(m=>`<p class="sheet-match${isBye(m)?' bye':''}">${esc(resultLine(night,m))}</p>`).join('')}</article>`).join('')}</div><p class="note">${esc(t('sheetNote'))}</p></section>`}
function revivalCard(){const T=tournament(),r=T.revival,list=matches(),signed=list.filter(m=>['played','forfeit'].includes(m.result)).length,open=list.length&&!r&&!list.some(m=>m.round>=2&&['played','forfeit'].includes(m.result))&&list.some(m=>m.round===1&&m.result==='played')&&list.some(m=>m.round===1&&isBye(m))&&list.filter(m=>m.round===1&&m.sides.every(Boolean)).every(m=>m.status==='complete');const draws=T.revival_draws||0;if(!r&&!open&&!draws)return '';const name=id=>ename(id);return `<article class="revival"><h3>${esc(t('secondChance'))}</h3><p class="note">${esc(t('revivalHint'))}</p>${!r&&draws?`<p class="muted">${esc(t('revivalSoFar').replace('{n}',draws))}</p>`:''}${r?`<p><strong>${esc(t('revivalDrawn').replace('{name}',name(r.entrant)))}</strong> · ${esc(t('revivalAttempt').replace('{n}',r.attempt||1))}</p>${(r.attempt||1)>1?`<p class="note">${esc(t('revivalRedrawn'))}</p>`:''}<p class="muted">${esc(t('revivalPool').replace('{names}',r.pool.map(name).join(lang==='zh'?'、':', ')))} · ${esc(t('revivalSeed').replace('{seed}',r.seed))} · ${esc(fmtDate(r.drawnAt))}</p>${signed===r.signed?btn(t('revivalUndo'),'revival-undo','','danger'):''}`:btn(t('revivalDraw'),'revival-draw','','primary')}</article>`}
function pairingCard(T){const pool=T.pool||[],pr=T.pairing,team=m=>m.map(x=>player(x.pid)?.name||x.name).join(' / ');return `<article class="pairing"><h3>${esc(t('randomPair'))}</h3><p class="note">${esc(t('pairHint'))}</p>${pr?`<p class="muted">${esc(t('pairSeed').replace('{seed}',pr.seed))}</p><ol class="pair-teams">${pr.teams.map(x=>`<li>${esc(team(x))}</li>`).join('')}</ol><div class="row">${btn(t('pairAccept'),'pair-accept',`data-seed="${pr.seed}"`,'primary')}${btn(t('pairReroll'),'pair-draw')}${btn(t('pairClear'),'pair-clear')}</div>`:`<form id="solo-form" class="fields">${field(t('member'),`<select name="solo_pid"><option value="">${esc(t('guest'))}</option>${roster().filter(p=>p.status!=='Inactive'&&!entrants().some(e=>e.members.some(m=>m.pid===p.id))&&!pool.some(m=>m.pid===p.id)).map(p=>option(p.id,p.name,'')).join('')}</select>`)}${field(t('guestName'),input('solo_name','','text','maxlength="120"'))}<div><button>${esc(t('soloAdd'))}</button></div></form><div class="row mt-3">${pool.map(m=>`<span class="badge">${esc(player(m.pid)?.name||m.name)} ${btn('×','pool-remove',`data-name="${esc(m.name)}" aria-label="${esc(t('remove'))} ${esc(m.name)}"`)}</span>`).join('')||`<span class="muted">${esc(t('emptyPool'))}</span>`}</div><div class="row mt-3">${btn(t('pairDraw'),'pair-draw',pool.length<2||pool.length%2?'disabled':'','primary')}${pool.length%2||pool.length<2?`<span class="muted">${esc(t('pairNeedEven'))}</span>`:''}</div>`}</article>`}
function bracketLine(){const list=matches(),all=list.filter(m=>!isBye(m)).length,signed=list.filter(m=>m.status==='complete'&&!isBye(m)).length,live=list.filter(m=>m.status==='live').length,late=list.filter(m=>m.status==='delayed').length;return [t('bracketSigned').replace('{n}',signed).replace('{m}',all),live?t('bracketLive').replace('{n}',live):'',late?t('bracketDelayed').replace('{n}',late):''].filter(Boolean).join(' · ')}
function bracketScreen(){const list=matches(),rounds=[...new Set(list.map(m=>m.round))].sort((a,b)=>a-b),ready=list.filter(m=>m.status==='scheduled'&&m.sides.every(Boolean)).length,line=bracketLine()+(rounds.length&&ready?` · ${t('bracketSend').replace('{n}',ready)}`:'');return `<section class="stack"><article class="bracket-view"><div class="heading"><h3>${esc(t('bracketTitle'))}</h3><span class="muted">${esc(line)}</span></div><div class="rounds">${rounds.map(r=>`<article class="round"><h3>${esc(t('round'))} ${r}</h3>${list.filter(m=>m.round===r).map(m=>`<div class="entry bracket-card${isPending(m.id)?' pending':''}${m.status==='live'?' live':''}${m.status==='delayed'?' held':''}" tabindex="0"${isPending(m.id)?' aria-busy="true"':''} data-status="${esc(isBye(m)?'bye':m.status)}" aria-label="${esc(`${sideName(m,m.sides[0])} – ${sideName(m,m.sides[1])} · ${t(isBye(m)?'bye':m.status)}${isPending(m.id)?` · ${t('savingNow')}`:''}`)}">${isPending(m.id)?`<span class="pending-note" role="status">${esc(t('savingNow'))}</span>`:''}<button type="button" class="card-toggle" data-action="card-toggle" aria-expanded="false" aria-label="${esc(t('cardExpand'))}" title="${esc(t('cardExpand'))}"><span aria-hidden="true">▾</span></button><div class="row card-head"><small class="grow">${m.table?`${esc(t('table'))} ${m.table}`:'—'} · ${m.id.slice(0,8)}</small>${mbadge(m)}</div>${m.sides.map((id,i)=>`<div class="row card-side${i===0?' first':''}${id&&id===m.winnerId?' won':''}"><i class="status-dot" aria-hidden="true"></i>${i===0&&m.table?`<span class="table-chip">${esc(t('table'))} ${m.table}</span>`:''}<strong class="grow" style="color:${id&&id===m.winnerId?'var(--brass-hi)':'var(--ink)'}">${esc(sideName(m,id))}</strong><strong>${isBye(m)?'':m.score[i]}</strong></div>`).join('')}<div class="card-actions">${m.status==='scheduled'?btn(t('send'),'schedule',`data-id="${m.id}" ${!m.sides.every(Boolean)?'disabled':''}`):''}${['live','delayed'].includes(m.status)?btn(t('openTable'),'card-open',`data-id="${m.id}"`):''}${matchControls(m)}</div></div>`).join('')}</article>`).join('')||`<article class="empty">${emptyNote('emptyBracket','tab:tonight','goSetup')}</article>`}</div></article></section>`}
const signedResult=m=>m.status==='complete'&&!isBye(m)&&m.sides.every(Boolean),pct=(w,n)=>n?`${Math.round(w/n*100)}%`:'—',hasSigned=n=>(n.matches||[]).some(m=>['played','forfeit'].includes(m.result)),quoted=n=>n.name||t('unnamed');
function record(night,eid){let wins=0,losses=0;for(const m of night.matches||[])if(signedResult(m)&&m.sides.includes(eid)){if(m.winnerId===eid)wins++;else losses++}return {wins,losses,played:wins+losses}}
function eventTable(night){const name=e=>(e.members||[]).map(m=>player(m.pid)?.name||m.name||t('unknown')).join(' / ');return (night.entrants||[]).map(e=>({name:name(e),...record(night,e.id)})).sort((a,b)=>b.wins-a.wins||(b.played?b.wins/b.played:-1)-(a.played?a.wins/a.played:-1)||a.name.localeCompare(b.name))}
function nightsOf(pid){return [...(data.history||[]),tournament()].filter(n=>(n.entrants||[]).some(e=>e.members.some(m=>m.pid===pid)))}
function headToHead(pid){const rows=new Map();for(const n of nightsOf(pid)){const mine=(n.entrants||[]).filter(e=>e.members.some(m=>m.pid===pid)).map(e=>e.id);for(const m of n.matches||[]){if(!signedResult(m))continue;const side=m.sides.findIndex(id=>mine.includes(id));if(side<0)continue;const opp=(n.entrants||[]).find(e=>e.id===m.sides[1-side]);if(!opp)continue;const pids=opp.members.map(x=>x.pid).filter(Boolean),guest=!pids.length,key=guest?'g:'+opp.members.map(x=>x.name.toLowerCase()).join('/'):'p:'+pids.join('/'),opponent=opp.members.map(x=>player(x.pid)?.name||x.name).join(' / ');const r=rows.get(key)||{opponent,guest,wins:0,losses:0,played:0,forfeits:0,last:''};r.opponent=opponent;if(m.result==='forfeit')r.forfeits++;else{r.played++;if(m.winnerId===m.sides[side])r.wins++;else r.losses++}if((m.completedAt||'')>r.last)r.last=m.completedAt||'';rows.set(key,r)}}return [...rows.values()].sort((a,b)=>b.played-a.played||a.opponent.localeCompare(b.opponent))}
function recordView(p){const s=resultStats(p.id),n=s.wins+s.losses,nights=nightsOf(p.id),since=fmtDate(nights[0]?.archivedAt||nights[0]?.matches?.find(m=>m.completedAt)?.completedAt||p.joinedAt),rows=headToHead(p.id);return `<div class="modal-head"><h3>${esc(t('playerRecord'))} · ${esc(p.name)}</h3>${btn("×","close-modal",`aria-label="${esc(t('closeLabel'))}"`)}</div><div class="record"><p class="muted">${esc(t('recordScope').replace('{n}',nights.length).replace('{date}',since))}</p>${tiles([[t('played'),n],[t('wins'),s.wins],[t('losses'),s.losses],[t('winPct'),pct(s.wins,n)]])}<h3>${esc(t('perEvent'))}</h3>${nights.length?`<div class="table-wrap"><table class="per-event"><thead><tr><th>${esc(t('event'))}</th><th>${esc(t('wl'))}</th></tr></thead><tbody>${nights.slice().reverse().map(night=>{const r=(night.entrants||[]).filter(e=>e.members.some(m=>m.pid===p.id)).reduce((acc,e)=>{const x=record(night,e.id);return {wins:acc.wins+x.wins,losses:acc.losses+x.losses}},{wins:0,losses:0});return `<tr><td>${esc(night.name||t('unnamed'))}<small>${esc(fmtDate(night.archivedAt)||t('tonight'))}</small></td><td>${r.wins}–${r.losses}</td></tr>`}).join('')}</tbody></table></div>`:emptyNote('emptyPerEvent')}<h3>${esc(t('headToHead'))}</h3><p class="muted">${esc(t('h2hNote'))}</p>${rows.length?`<div class="table-wrap"><table class="h2h"><thead><tr><th>${esc(t('opponent'))}</th><th>${esc(t('wl'))}</th><th>${esc(t('winPct'))}</th><th>${esc(t('sample'))}</th><th>${esc(t('forfeit'))}</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.opponent)}${r.guest?`<small>${esc(t('guestByName'))}</small>`:''}</td><td>${r.wins}–${r.losses}</td><td>${pct(r.wins,r.played)}</td><td>${r.played}</td><td>${r.forfeits}</td></tr>`).join('')}</tbody></table></div>`:emptyNote('emptyH2H')}${tab==='records'?'':`<div class="row">${btn(t('back'),'record-back')}</div>`}</div>`}
function resultStats(pid){let wins=0,losses=0;for(const night of [tournament(),...(data.history||[])]){const ids=(night.entrants||[]).filter(e=>e.members.some(m=>m.pid===pid)).map(e=>e.id);for(const m of night.matches||[]){if(m.status==='complete'&&m.sides.every(Boolean)&&m.sides.some(id=>ids.includes(id))){if(ids.includes(m.winnerId))wins++;else losses++}}}return {wins,losses}}
function fmtDate(iso){if(!iso)return'';const d=new Date(iso);if(isNaN(d))return String(iso).slice(0,10);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function autoEventName(){const d=new Date(),days=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],daysZh=['周日','周一','周二','周三','周四','周五','周六'];return lang==='zh'?`${d.getMonth()+1}月${d.getDate()}日 ${daysZh[d.getDay()]} 8球公开赛`:`8-Ball Open · ${days[d.getDay()]} ${d.getMonth()+1}/${d.getDate()}`}
// Owner item 3: the Vision tab is the live stream. Until the server carries one, the tab shows
// the live controls alone - no dataset chip, no recorded frames, no frame transport. When the
// stream runs, the workbench the tab always had mounts and the live frames feed it; the recorded
// workbench is opened from a night's row on Records, which is its only entrance.
function liveVisionScreen(){return liveRunning()?visionSurface():livePanelScreen()}
function livePanelStatus(){
  const s=liveSnapshot||{},word=review()?.liveStateText?.(s.state||'idle')||liveText({idle:'idle',starting:'starting',running:'live',stopped:'stopped',error:'error'}[s.state]||'idle',{idle:'空闲',starting:'启动中',running:'直播中',stopped:'已停止',error:'出错'}[s.state]||'空闲');
  return `${word}${s.error?' · '+s.error:''} · ${liveText('Frame age','帧龄')}: ${s.frame_age_ms?.toFixed?.(0)??'—'} ms · ${liveText('Dropped','丢帧')}: ${s.frames_skipped??0}`}
function livePanelScreen(){
  // The console's own words, not the adapter's: `live` here means "on the table", so the chip
  // says liveNow, and the detector labels reuse table/person/ball exactly as the panel does.
  const list=channels()||[],active=liveSource(liveChoice);
  const chips=list.map(c=>{const value='twitch:'+c.id,on=active.kind==='twitch'&&String(active.source_id)===String(c.id);return `<button class="vs-chip${on?' active':''}" data-action="live-pick" data-value="${esc(value)}" aria-pressed="${on?'true':'false'}">${on?'● ':''}${esc(t('liveNow'))} · twitch ${esc(c.channel||'')}</button>`}).join('');
  const boxes=[['table',t('table')],['person',t('person')],['ball',t('ball')]].map(([k,label])=>`<label class="vs-check"><input type="checkbox" data-action="live-detector" data-value="${k}" ${liveDetectors.includes(k)?'checked':''}> ${esc(label)}</label>`).join('');
  const note=list.length?t('livePanelNote'):t('liveNoChannel');
  return `<section class="stack live-screen" id="live-screen">
  <article class="live-card">
    <div class="heading"><h2>${esc(t('liveStream'))}</h2></div>
    <p class="vs-mono live-status" id="live-panel-status" role="status">${esc(livePanelStatus())}</p>
    ${list.length?`<div class="vs-chiprow" role="group" aria-label="${esc(t('sources'))}">${chips}</div>`:''}
    <div class="vs-row live-actions"><button class="primary" data-action="live-start">${esc(t('start'))}</button>${btn(t('sources'),'sources-open')}<button data-tab="records">${esc(t('records'))} →</button></div>
    <div class="vs-row live-detectors" role="group" aria-label="${esc(t('detectors'))}">${boxes}</div>
    <p class="muted live-note">${esc(note)} ${esc(t('reviewFromRecords'))}</p>
  </article>
</section>`}
function visionSurface(){const L=k=>esc(t(k)),loadingLine=`<p class="vs-loading" role="status">${L('visionLoading')}</p>`;return `<section class="vision-surface" id="vision-surface"${visionAdapter?'':' aria-busy="true" data-loading="true"'}>
<h2 class="sr-only">${L('reviewTitle')}</h2>
<div class="vs-head"><div class="vs-chips" id="vs-chips"></div><div class="row vs-sources">${reviewId?'':`${btn(t('sources'),'sources-open')}${btn(t('stop'),'live-stop')}`}</div></div>
<div class="vs-grid" id="vs-grid" data-sheet="cues">
<aside class="vs-rail" id="vs-cues" aria-label="${L('visionCues')}" data-vs-aria="cuesRegion">${loadingLine}</aside>
<section class="vs-stage" id="vs-stage" aria-label="${L('visionStage')}" data-vs-aria="stageRegion">
<div class="vs-stagebar"><div class="vs-layers" id="vs-layers"></div><span class="vs-clock" title="${esc(t('shotTimer'))}"><strong class="clock${clockLow(clockLeft())?' low':''}" data-clock>${esc(clockText(clockLeft()))}</strong></span><span class="vs-identity" id="vs-identity"></span></div>
<div class="vs-frame" id="vs-frame"></div>
</section>
<aside class="vs-inspector" id="vs-inspector" aria-label="${L('visionInspector')}" data-vs-aria="inspectorRegion"><div class="vs-inspector-scroll" id="vs-inspector-scroll">${loadingLine}</div><div class="vs-inspector-actions" id="vs-inspector-actions"></div></aside>
</div>
<div class="vs-sheettabs" role="tablist" aria-label="${L('visionPanels')}" data-vs-aria="sheetTabs"><button type="button" role="tab" aria-selected="true" aria-controls="vs-cues" data-sheet-tab="cues" class="active" data-vs-label="showCues">${L('visionCuesTab')}</button><button type="button" role="tab" aria-selected="false" aria-controls="vs-inspector" data-sheet-tab="inspector" data-vs-label="showInspector">${L('visionInspectorTab')}</button></div>
<div class="vs-strip" id="vs-strip">
<div class="vs-transport">
<label class="vs-frame-input"><span data-vs-label="frameIndex">${L('visionFrame')}</span><input id="vs-frame-index" type="number" min="0" value="0"></label>
<button type="button" data-vs-action="step" data-vs-value="-1" aria-label="${L('visionPrev')}" data-vs-aria="stepBack">◀</button>
<button type="button" data-vs-action="step" data-vs-value="1" aria-label="${L('visionNext')}" data-vs-aria="stepForward">▶</button>
<button type="button" data-vs-action="freeze" class="primary" data-vs-label="freeze">${L('visionFreeze')}</button>
<button type="button" id="vs-play" data-vs-action="play">▶ ${L('visionPlay')}</button>
</div>
<div class="vs-track">
<div class="scrub-marks" id="vs-marks"></div>
<input id="vs-scrub" type="range" min="0" max="0" step="1" value="0">
<span class="vs-edge" id="vs-edge"></span>
</div>
<p class="vs-facts" id="vs-facts" role="status"></p>
</div>
</section>`}
// R13/R14: search is local and instant (no request per keystroke). Every query word must
// occur in the name (AND), after NFKC (full-width forms), accent folding and case folding.
// Punctuation separates words, so "ann-marie lee" finds "Ann-Marie (Annie) Lee"; CJK names
// match by substring, with or without spaces ("王 磊" and "王磊" both find 王磊).
function searchFold(value){return String(value??'').normalize('NFKC').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim()}
function nameMatches(name,query){const words=searchFold(query).split(' ').filter(Boolean);if(!words.length)return true;const hay=searchFold(name),compact=hay.replace(/ /g,'');return words.every(w=>hay.includes(w)||compact.includes(w))}
/* Round 9, owner item 4: the desk's search now filters the picker's own rows in place. Nothing
   is re-rendered, so the caret stays where it was typed; the Guest row is never hidden (it is
   how an operator goes back to a walk-in), and the count line reports what is left of the free
   regulars rather than silently dropping rows. */
function deskFilter(field){const panel=field.closest?.('.pick-panel');if(!panel)return;const q=field.value,total=Number(panel.dataset.total||0);let shown=0;for(const row of panel.querySelectorAll('.pick-row')){if(!(row.dataset.id||''))continue;const ok=nameMatches(row.dataset.name||'',q);row.hidden=!ok;if(ok)shown++}const count=panel.querySelector('.pick-count');if(count){count.hidden=!q.trim();count.textContent=t('searchCount').replace('{n}',String(shown)).replace('{m}',String(total))}}
// R9: bracket density, per device. Compact shows one line per side; full shows every card as before.
// Round 1: an empty state says what fills the panel and the next step, never just "nothing here".
const emptyNote=(key,action='',label='')=>`<p class="empty-note">${esc(t(key))}${action?` ${btn(t(label),action.startsWith('tab:')?'':action,action.startsWith('tab:')?`data-tab="${action.slice(4)}"`:'')}`:''}</p>`;
/* Round 9, owner item 9: the Regulars tab's own header. The three-tile strip that opened it
   reported an "average house rating" over every row including the regulars who have never been
   rated, which made the number wrong in a way the reader could not see. One line instead: the
   club at a glance, and the average names the base it was taken over. */
function rosterSummary(all){
  const active=all.filter(p=>p.status==='Active').length,rated=all.filter(p=>Number(p.rating)>0);
  const mean=rated.length?Math.round(rated.reduce((s,p)=>s+Number(p.rating||0),0)/rated.length):0;
  const played=[tournament(),...(data.history||[])].reduce((n,event)=>n+(event.matches||[]).filter(m=>m.status==='complete'&&m.sides.every(Boolean)).length,0);
  const cell=(label,value,note)=>`<div class="roster-stat"><small>${esc(label)}</small><strong>${esc(String(value))}</strong>${note?`<small class="roster-stat-note">${esc(note)}</small>`:''}</div>`;
  return `<div class="roster-summary" role="group" aria-label="${esc(t('players'))}">${cell(t('players'),all.length)}${cell(t('activeMembers'),active)}${cell(t('average'),rated.length?mean:'—',t('rosterRatingBase').replace('{n}',String(rated.length)).replace('{m}',String(all.length-rated.length)))}${cell(t('logged'),played)}</div>`}
function playersScreen(){const all=roster(),rows=all.filter(p=>(!filter||p.status===filter)&&nameMatches(p.name,query)),p=data.players.find(p=>p.id===selected)||null,stats=p?resultStats(p.id):{wins:0,losses:0},wins=stats.wins,losses=stats.losses;const modalOpen=selected&&(selected==='new'||p);let modal='';if(modalOpen&&selected==='new')modal=`<div class="modal-backdrop" data-action="close-modal"><div class="modal" role="dialog" aria-modal="true" ><div class="modal-head"><h3>${esc(t('newPlayer'))}</h3>${btn("×","close-modal",`aria-label="${esc(t('closeLabel'))}"`)}</div>${playerForm()}</div></div>`;else if(modalOpen&&p&&recordId===p.id)modal=`<div class="modal-backdrop" data-action="close-modal"><div class="modal" role="dialog" aria-modal="true" >${recordView(p)}</div></div>`;else if(modalOpen&&p)modal=`<div class="modal-backdrop" data-action="close-modal"><div class="modal" role="dialog" aria-modal="true" ><div class="modal-head"><h3>${esc(p.name)}</h3>${btn("×","close-modal",`aria-label="${esc(t('closeLabel'))}"`)}</div><p>${esc(t(p.status))} · ${esc(fmtDate(p.joinedAt||p.createdAt))}</p>${tiles([[t('rating'),p.rating],[t('wins'),wins],[t('losses'),losses],[t('winRate'),wins+losses?`${Math.round(wins/(wins+losses)*100)}%`:'—']])}<div class="row mb-3">${btn(t('playerRecord'),'player-record',`data-id="${p.id}"`,'primary')}</div>${playerForm(p)}<div class="row mt-3">${btn(t('deletePlayer'),'player-delete','data-id="'+p.id+'"','danger')}${btn(t('faceForget'),'face-forget','data-id="'+p.id+'"','danger')}</div><h3>${esc(t('enrollFace'))}</h3><p class="note">${esc(t('enrollHint'))}</p><form id="enroll-form" data-player="${p.id}"><input type="file" id="enroll-photo" accept="image/*" required><div class="actions mt-3"><button class="primary" type="submit">${esc(t('enrollSubmit'))}</button></div></form></div></div>`;return `<section class="stack"><h2 class="sr-only">${esc(t('players'))}</h2>${rosterSummary(all)}<div class="grid"><article><div class="row items-center justify-between mb-3"><h3 class="m-0">${esc(t('rosterTitle'))}</h3>${btn(t('newPlayer'),'open-add-player','','primary add-player')}</div><div class="stack">${input('query',query,'search',`id="roster-search" placeholder="${esc(t('search'))}" aria-label="${esc(t('searchRoster'))}"`)}<div class="row">${['','Active','Visitor','Inactive'].map(f=>{const n=f?all.filter(p=>p.status===f).length:all.length;return btn(`${t(f||'all')} ${n}`,'filter',`data-value="${f}"`,filter===f?'active':'')}).join('')}</div></div><div class="standing-list mt-4">${rows.map(p=>{const st=resultStats(p.id),n=st.wins+st.losses;return `<button type="button" class="standing${n?'':' no-record'}" data-action="select-player" data-id="${p.id}"><span class="badge">${all.indexOf(p)+1}</span><span class="grow standing-name">${esc(p.name)}<small>${esc(t(p.status))} · ${esc(fmtDate(p.joinedAt||p.createdAt))}</small><small class="standing-record">${n?`${st.wins}–${st.losses} · ${pct(st.wins,n)}`:`${esc(t('played'))} 0 · ${esc(t('noRecord'))}`}</small></span><span class="standing-rating"><strong>${Number(p.rating)>0?esc(String(p.rating)):'—'}</strong><small>${esc(t('rating'))}</small></span></button>`}).join('')||emptyNote(query||filter?'emptyRosterFiltered':'emptyRoster','open-add-player','newPlayer')}</div></article></div>${modal}</section>`}
function playerForm(p){const editing=!!p;const statusOptions=editing?['Active','Visitor','Inactive']:['Active'];return `<form class="player-form mb-4">${p?input('id',p.id,'hidden'):''}<div class="fields">${field(t('name'),input('name',p?.name||'','text','required maxlength="120"'))}${editing?field(t('rating'),input('rating',p?.rating??0,'number','required min="0" max="1000"')):''}${editing?field(t('playerStatus'),`<select name="status">${statusOptions.map(s=>option(s,t(s),p?.status||'Active')).join('')}</select>`):input('status','Active','hidden')}</div>${editing?field(t('playerNotes'),`<textarea name="notes" maxlength="4000" rows="3">${esc(p?.notes||'')}</textarea>`):''}<div><button class="primary">${esc(t('save'))}</button></div></form>`}
function parseSource(value){try{const u=new URL(value);if(u.protocol!=='https:'||!['twitch.tv','www.twitch.tv'].includes(u.hostname)||u.port||u.username||u.password||u.search||u.hash)return null;const path=u.pathname.match(/^\/([A-Za-z0-9_]{1,25})\/?$/),vod=u.pathname.match(/^\/videos\/(\d+)\/?$/);if(vod)return {kind:'vod',video:vod[1],url:`https://www.twitch.tv/videos/${vod[1]}`};if(path&&!['videos','directory','downloads','settings','search','login','signup','subscriptions','inventory','wallet','jobs','turbo'].includes(path[1].toLowerCase()))return {kind:'channel',channel:path[1].toLowerCase(),url:`https://www.twitch.tv/${path[1].toLowerCase()}`}}catch{}return null}
function appearancePanel(){const s=data.settings||{};return `<article><h3>${esc(t('appearance'))}</h3><form id="appearance-form"><div class="fields">${field(t('cloth'),`<select name="clothColor">${[['#1d5c44','greenCloth'],['#1f4a70','blueCloth'],['#6a2130','redCloth'],['#2f3a3f','grayCloth']].map(([color,key])=>option(color,t(key),s.clothColor||'#1d5c44')).join('')}</select>`)}${field(t('lamp'),input('lampGlow',s.lampGlow??.22,'range','min="0" max="0.5" step="0.02"'))}${field(t('diamonds'),`<input type="checkbox" name="showDiamonds" ${s.showDiamonds!==false?'checked':''}>`)}${field(t('publicBoard'),`<input type="hidden" name="publicBoard" value="off"><input type="checkbox" name="publicBoard" value="on" ${s.publicBoard!==false?'checked':''}>`)}</div><div><button class="primary">${esc(t('save'))}</button></div></form><div class="cloth-preview" style="background-color:${esc(s.clothColor||'#1d5c44')};background-image:radial-gradient(ellipse at top,rgba(255,230,170,${Number(s.lampGlow)||0}),transparent 75%)" role="img" aria-label="${esc(t('appearanceNote'))}">${s.showDiamonds!==false?'<span class="rail-diamonds">◆　◆　◆　◆　◆　◆</span>':''}<span>${esc(t('appearanceNote'))}</span>${s.showDiamonds!==false?'<span class="rail-diamonds">◆　◆　◆　◆　◆　◆</span>':''}</div></article>`}
function roadmapPanel(){const zh=lang==='zh',rows=[['House ledger server writes','球房账本服务写入','Local operations persistence only; no dedicated ledger service','仅本地运营持久化，尚无专用账本服务','P1'],['Online signups','在线报名','Local registration only; public signup service absent','仅本地报名，尚无公开报名服务','P1'],['Scotch-doubles turn order','苏格兰双打轮次','Doubles entrants supported; turn enforcement absent','支持双打报名，尚无轮次强制检查','P2'],['Result undo trail','赛果撤销轨迹','Audit history exists; result undo absent','已有审计记录，尚无赛果撤销','P1'],['Trained ball detector','训练球检测器','Explicit local inference available; accuracy unverified','可显式运行本地推理，准确度未经验证','P1'],['Safe people detector','可靠人员检测器','Review tools available; safety validation absent','已有复核工具，尚无可靠性验证','P2'],['Calibrated replay beyond 2.5D','超越2.5D的标定回放','Pocket calibration available; advanced replay absent','已有袋口标定，尚无高级回放','P1'],['Per-shot automatic clock start','逐杆自动启动计时','Manual device clock only; shot integration absent','仅设备手动计时，尚无击球联动','P2'],['Automatic reseeding / forfeit timer','自动重排 / 弃权计时','Explicit manual actions only; automation absent','仅显式手动操作，尚无自动化','P1']];return `<article><h3>${zh?'后续计划 · 非实时监控':'Roadmap · not live monitoring'}</h3><div class="table-wrap"><table><thead><tr><th>${zh?'目标领域':'Target area'}</th><th>${zh?'当前能力 / 尚缺功能':'Current capability / gap'}</th><th>${zh?'优先级':'Priority'}</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r[zh?1:0])}</td><td>${esc(r[zh?3:2])}</td><td>${r[4]}</td></tr>`).join('')}</tbody></table></div></article>`}
function statusScreen(){return `<section class="stack">${appearancePanel()}<article><h3>${esc(t('notes'))}</h3><form id="note-form">${field(t('note'),'<textarea name="text" required maxlength="4000" rows="3"></textarea>')}<div><button>${esc(t('addNote'))}</button></div></form><div class="mt-3">${(data.notes||[]).map(n=>`<div class="entry row"><span class="grow pre-wrap">${esc(n.text)}</span>${btn(t('remove'),'note-delete',`data-id="${n.id}"`)}</div>`).join('')}</div></article><details class="maintainers"><summary><h2>${esc(t('forMaintainers'))}</h2><span class="muted">${esc(t('forMaintainersNote'))}</span></summary><div class="stack"><article class="maint-status"><h3>${esc(t('systemStatus'))}</h3><p class="muted">${esc(t('systemStatusNote'))}</p><p class="muted last-write">${esc(t('lastWrite').replace('{n}',String(data.revision)))}</p><div class="table-wrap"><table><caption class="sr-only">${esc(t('systemStatus'))}</caption><thead><tr><th>${esc(t('area'))}</th><th>${esc(t('now'))}</th></tr></thead><tbody>${[[t('revision'),data.revision],[t('persist'),'/api/operations'],[t('scoreboardTitle'),t('manual')],[t('observation'),t('notConnected')],[t('review'),`${t('vision')} · VOD`]].map(row=>`<tr>${row.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="note">${esc(t('noSimulation'))}</p>${btn(t('refresh'),'reload')}</article>${roadmapPanel()}</div></details></section>`}
document.addEventListener('click',async e=>{if(e.target.closest?.('#review-root'))return;
// Round 9, owner item 4: the desk's listbox closes on any click that lands outside the form,
// before the click is interpreted. Clicks inside it - the search box, a row, Add entrant - are
// left alone, so choosing a regular and then submitting are both single clicks.
if(deskOpen!==null&&!e.target.closest?.('#entrant-form')){deskOpen=null;render()}
if(vodPick&&!e.target.closest?.('.vod-pick-host')){vodPick=null;render()}
const b=e.target.closest('button,.modal-backdrop');if(!b)return;if(b.classList?.contains('modal-backdrop')&&e.target.closest('.modal'))return;if(b.dataset.lang){if(busy)return;lang=b.dataset.lang;localStorage.setItem('cp-ops-lang',lang);render();return}if(b.dataset.theme){if(busy)return;theme=b.dataset.theme;localStorage.setItem('cp-ops-theme',theme);render();return}if(b.dataset.action==='card-toggle'){const card=b.closest('.entry');if(card){const open=card.classList.toggle('open');b.setAttribute('aria-expanded',String(open));const label=t(open?'cardCollapse':'cardExpand');b.setAttribute('aria-label',label);b.setAttribute('title',label)}return}
if(b.dataset.tab){go(routeOf(b.dataset.tab));return}const a=b.dataset.action,id=b.dataset.id,side=Number(b.dataset.side),m=matches().find(m=>m.id===id);if(!a)return;
if(a==='vod-open'){const kind=String(b.dataset.kind||'event'),key=String(b.dataset.id||'');
  vodPick=vodPick&&vodPick.kind===kind&&String(vodPick.id)===key?null:{kind,id:key,q:''};render();return}
if(a==='vod-link'){const payload={vodId:String(b.dataset.vod||''),eventId:String(b.dataset.id||'')};
  if(b.dataset.title)payload.title=b.dataset.title;if(b.dataset.channel)payload.channel=b.dataset.channel;
  if(Number(b.dataset.length))payload.length_s=Number(b.dataset.length);if(b.dataset.created)payload.created_at=b.dataset.created;
  if(await action('vod_link',payload)){vodPick=null;render()}return}
if(a==='vod-unlink'){if(await action('vod_unlink',{vodId:String(b.dataset.vod||''),eventId:String(b.dataset.id||'')})){vodPick=null;render()}return}
if(a==='desk-open'){readDeskDraft();deskOpen=deskOpen===Number(b.dataset.desk)?null:Number(b.dataset.desk);render();return}if(a==='desk-pick'){readDeskDraft();const slot=Number(b.dataset.desk);deskPick[slot]=id||'';if(id)deskDraft[slot]={...deskDraft[slot],guest:''};deskOpen=null;render();return}if(a==='backfill-open'){bfOpen();return}if(a==='tl-toggle'){const key=String(id);openEvents.has(key)?openEvents.delete(key):openEvents.add(key);render();return}if(a==='archive-reload'){loadArchiveList(true);loadAuto(true);return}if(a==='auto-toggle'){autoToggle();return}if(a==='auto-reload'){loadAuto(true);return}if(a==='tl-open-night'){const key=String(id);openEvents.add(key);render();const node=$(`[data-event="${key}"]`);if(node&&typeof node.scrollIntoView==='function')node.scrollIntoView({block:'center'});return}if(a==='tl-review'){openReview(id);return}if(a==='review-back'){reviewId=null;syncRoute(true);render();window.scrollTo?.(0,0);return}if(a==='bf-exit'){bfExit();return}// Two entrances meet here: the picker inside the backfill (bf is already set) and a row on
// Records' archive, where the operator has chosen the broadcast before the flow was open.
if(a==='bf-pick'){if(!bf)bf=Object.assign(bfFresh(),{saved:readBfDraft()});bfPickVod(id,b.dataset.length,b.dataset.title);return}if(a==='bf-check'){bfCheck();return}if(a==='bf-estimate'){bfEstimate();return}if(a==='bf-start-import'){bfStartImport();return}if(a==='bf-use-imported'){bfUseImported();return}if(a==='bf-cancel'){bfCancel();return}if(a==='bf-poll'){bfPoll();return}if(a==='bf-retry'){bfRetry();return}if(a==='bf-choose-other'){bfChooseOther();return}if(a==='bf-resume'){bfResumeDraft();return}if(a==='bf-drop-draft'){bfDropDraft();return}if(a==='bf-start-marking'){bfStartMarking();return}if(a==='bf-mark-start'){bfMarkStart();return}if(a==='bf-mark-end'){bfMarkEnd();return}if(a==='bf-unmark'){bfUnmark(Number(id));return}if(a==='bf-to-review'){bfToReview();return}if(a==='bf-to-marking'){if(bf){bf.step='marking';render()}return}if(a==='bf-confirm'){bfConfirm(Number(id));return}if(a==='bf-commit'){bfCommit();return}if(a==='bf-open-timeline'){bfOpenTimeline();return}if(a==='bf-open-night'){bfOpenNight();return}
if(a==='reload')return reload();
 // The Vision tab's own controls while no stream is running (owner item 3): the panel is not the
 // adapter's markup, so its buttons report through these branches and repaint through render().
 if(a==='live-start'){startLive();return}if(a==='live-stop'){stopLive();return}if(a==='live-pick'){pickLive(String(b.dataset.value||''));render();return}if(a==='live-detector'){const d=String(b.dataset.value||'');setLiveDetectors(liveDetectors.includes(d)?liveDetectors.filter(x=>x!==d):[...liveDetectors,d]);render();return}if(a==='clock-toggle'){clockToggle()}if(a==='clock-reset'){timer.remaining=timer.duration;timer.deadline=null;persistClock();render()}if(a==='clock-set'){const duration=Number(b.dataset.value);if(!Number.isFinite(duration)||duration<=0)return;if(await action('settings_update',{shotClock:duration})){timer={duration,remaining:duration,deadline:null};persistClock();render()}}
if(a==='score'&&m){const delta=Number(b.dataset.delta);await matchWrite(id,'match_score',x=>{const score=[...x.score];score[side]=Math.max(0,Math.min(race(),score[side]+delta));return {payload:{score},apply:y=>{y.score=score}}})}if(a==='clear')await matchWrite(id,'match_score',()=>({payload:{score:[0,0]},apply:y=>{y.score=[0,0]}}));if(a==='sign'&&confirm(t('confirmSign')))await matchWrite(id,'match_complete',()=>({payload:{}}));if(a==='frame'&&m&&confirm(t('confirmSign'))){const score=[0,0];score[side]=1;if(await matchWrite(id,'match_score',()=>({payload:{score},apply:y=>{y.score=[...score]}})))await matchWrite(id,'match_complete',()=>({payload:{}}))};if(a==='open-setup'){setupOpen=true;render();return}if(a==='sources-open'){sourceOpen=true;render();return}if(a==='sources-close'){sourceOpen=false;render();return}if(a==='dismiss-setup'){setupOpen=false;render();return}if(a==='focus'){focusId=id;render();return}if(a==='card-open'){focusId=id;tab='clock';syncRoute(true);render();window.scrollTo?.(0,0);return}if(a==='source-remove'){if(await action('source_delete',{id}))render();return}if(a==='schedule'){if(await action('match_schedule',{id,table:b.dataset.table?Number(b.dataset.table):undefined})){focusId=id;render()}}if(a==='forfeit'&&confirm(t('confirmForfeit')))await action('match_forfeit',{id,side});if(a==='unschedule')await action('match_unschedule',{id});if(a==='entrant-remove')await action('entrant_remove',{id});if(a==='tournament-start'){const shown=document.querySelector('#settings-form [name=name]')?.value?.trim();if(!tournament().name&&shown&&!await action('tournament_setup',{name:shown}))return;tab='tonight';if((await action('tournament_start'))===false)returnsyncRoute(true)}if(a==='results-sheet'){sheetId=id;render();window.scrollTo?.(0,0)}if(a==='sheet-back'){sheetId=null;render()}if(a==='print-sheet')print();if(a==='copy-results'){const night=[tournament(),...(data.history||[])].find(n=>n.id===id);if(night){try{await navigator.clipboard.writeText(resultsText(night));message(t('copied'))}catch(e){message(t('copyFail'),true,e.message)}}}if(a==='revival-draw'&&confirm(t('confirmRevival')))await action('revival_draw',{confirm:true});if(a==='revival-undo'&&confirm(t('confirmRevivalUndo')))await action('revival_undo',{confirm:true});if(a==='pair-draw')await action('pair_draw');if(a==='pair-accept')await action('pair_accept',{seed:Number(b.dataset.seed)});if(a==='pair-clear')await action('pair_clear');if(a==='pool-remove')await action('pool_remove',{name:b.dataset.name});if(a==='toggle-hidden'){showHidden=!showHidden;render()}if(a==='event-delete'){const n=[tournament(),...(data.history||[])].find(n=>n.id===id);if(n&&confirm(t('confirmDelete').replace('{name}',quoted(n))))await action('tournament_delete',{id,confirm:true})}if(a==='event-hide'){const n=(data.history||[]).find(n=>n.id===id),hidden=b.dataset.hidden==='true';if(n&&confirm(t(hidden?'confirmHide':'confirmUnhide').replace('{name}',quoted(n))))await action('tournament_hide',{id,hidden,confirm:true})}if(a==='rename-archived'){const h=(data.history||[]).find(h=>h.id===id);const name=prompt(t('renameArchived'),h?.name||'');if(name!==null&&name.trim())await action('tournament_rename',{id,name:name.trim()})}if(a==='new-event'&&confirm(t('newConfirm')))await action('tournament_new',{confirm:true});if(a==='select-player'){selected=id;recordId=null;render()}if(a==='player-record'){if(tab!=='records')selected=id;recordId=id;render()}if(a==='record-back'){recordId=null;render()}if(a==='open-add-player'){selected='new';render()}if(a==='close-modal'){selected=null;recordId=null;render()}if(a==='filter'){filter=b.dataset.value;render()}if(a==='player-delete'&&confirm(t('deleteConfirm'))&&await action('player_delete',{id}))selected=null;if(a==='face-forget'&&confirm(t('faceForgetConfirm'))){try{const r=await fetch('/api/identity/forget',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player_id:id})});const result=await r.json().catch(()=>({}));if(!r.ok)throw Error(result.error||`HTTP ${r.status}`);const n=result.removed||{};message(lang==='zh'?`${t('faceForgetDone')}：${n.store_faces||0} 张人脸，解除 ${n.clusters_unbound||0} 个匹配人物，${n.face_samples||0} 个人脸样本`:`${t('faceForgetDone')}: ${n.store_faces||0} stored faces, ${n.clusters_unbound||0} matched person unbound, ${n.face_samples||0} face samples`)}catch(error){message(`${t('faceForgetFail')}: ${validationMessage(error.message)}`,true,lang==='zh'?error.message:'')}}if(a==='promote')await action('guest_promote',{name:b.dataset.name});if(a==='source-select'){sourceId=id;render()}if(a==='source-delete')await action('source_delete',{id});if(a==='chat'){chat=!chat;render()}if(a==='note-delete')await action('note_delete',{id})});
// Owner round 2 (F15): the numbered ball in front of each destination is a real shortcut.
// Digit1 is the shot timer's slot 1 (start/pause); a text field or a held modifier keeps the key.
// The timer key activates the control instead of calling the toggle behind its back: the shot
// clock is shared (clock-sync.js turns a click on that button into a POST /api/clock), so a key
// that skipped the control would start the clock on this screen only and the next server push
// would silently undo it. Tapping the button runs every listener a mouse reaches.
const navKey=n=>n===1?'clock':(primaryNav()[n-2]||null);
const clockControl=()=>document.querySelector?.('#ops-shell [data-action="clock-toggle"]');
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&deskOpen!==null){deskOpen=null;render();return}if(e.key==='Escape'&&vodPick){vodPick=null;render();return}const hit=/^Digit([1-6])$/.exec(e.code||'')||/^([1-6])$/.exec(e.key||'');if(!hit||e.altKey||e.ctrlKey||e.metaKey||e.shiftKey)return;const el=document.activeElement,tag=String(el?.tagName||'').toUpperCase();if(['INPUT','TEXTAREA','SELECT'].includes(tag)||el?.isContentEditable)return;const target=navKey(Number(hit[1]));if(!target)return;if(target!=='clock'){go(target)}else{const b=clockControl();b&&typeof b.click==='function'?b.click():clockToggle()}e.preventDefault()});
document.addEventListener('input',e=>{e.target.setCustomValidity?.('');if(e.target.dataset?.desk!=null){deskFilter(e.target);return}
if(e.target.dataset?.vodSearch!=null){vodFilter(e.target);return}if(e.target.dataset?.bf){bfInput(e.target);return}if(e.target.id==='events-search'){const cursor=e.target.selectionStart;eventsQuery=e.target.value;render();const el=$('#events-search');el.focus();el.setSelectionRange(cursor,cursor);return}if(e.target.id==='roster-search'){const cursor=e.target.selectionStart;query=e.target.value;render();const el=$('#roster-search');el.focus();el.setSelectionRange(cursor,cursor)}});
document.addEventListener('change',e=>{e.target.form?.querySelectorAll('input').forEach(i=>i.setCustomValidity(''));if(e.target.dataset?.bf){bfInput(e.target);if(/^(night-|side-|winner-|score-)/.test(String(e.target.dataset.bf)))render();return}if(e.target.id==='focus-match'){focusId=e.target.value;render()}});
document.addEventListener('submit',async e=>{if(e.target.closest?.('#review-root'))return;e.preventDefault();const f=e.target,v=Object.fromEntries(new FormData(f));;if(f.id==='enroll-form'){const field=f.querySelector('#enroll-photo'),photo=field.files[0];if(!photo)return;const bad=!/^image\//.test(photo.type)?'photoType':photo.size>8*1024*1024?'photoSize':'';if(bad){field.setCustomValidity(t(bad));field.reportValidity();return}const reader=new FileReader();reader.onload=async()=>{try{const base64=String(reader.result).split(',')[1];const r=await fetch('/api/identity/enroll',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player_id:f.dataset.player,image_base64:base64})});const result=await r.json().catch(()=>({}));if(!r.ok)throw Error(result.error||`HTTP ${r.status}`);message(`${result.enrolled} ${t('enrollDone')}`)}catch(error){message(`${t('enrollFail')}: ${validationMessage(error.message)}`,true,lang==='zh'?error.message:'')}};reader.readAsDataURL(photo);return}const spaces=[...f.querySelectorAll('input[type=text][required],textarea[required]')].find(i=>!i.value.trim());if(spaces){spaces.setCustomValidity(t('notBlank'));spaces.reportValidity();return}if(f.getAttribute('id')==='appearance-form')await action('settings_update',{clothColor:v.clothColor,lampGlow:Number(v.lampGlow),showDiamonds:v.showDiamonds==='on',publicBoard:v.publicBoard==='on'});if(f.getAttribute('id')==='solo-form'){const name=String(v.solo_name??'').trim();if(!v.solo_pid&&!name){const i=f.querySelector('[name=solo_name]');i.setCustomValidity(t('guestNeeded'));i.reportValidity();return}if(!v.solo_pid&&['na','n/a','bye','tbd','轮空','輪空'].includes(name.toLowerCase())){const i=f.querySelector('[name=solo_name]');i.setCustomValidity(t('placeholderName'));i.reportValidity();return}await action('solo_add',{member:v.solo_pid?{pid:v.solo_pid}:{name}})}if(f.getAttribute('id')==='settings-form'){setupOpen=false;const T=tournament();if(comp()!=='registration')await action('tournament_rename',{id:T.id,name:String(v.name||T.name).trim()});else await action('tournament_setup',{name:v.name,format:v.format,tables:Number(v.tables),raceTo:Number(v.raceTo)})}if(f.getAttribute('id')==='entrant-form'){const members=Array.from({length:tournament().format==='doubles'?2:1},(_,i)=>v[`pid${i}`]?{pid:v[`pid${i}`]}:{name:String(v[`guest${i}`]??'').trim()}),blank=members.findIndex(m=>m.name==='');const fake=members.findIndex(m=>['na','n/a','bye','tbd','轮空','輪空'].includes((m.name||'').toLowerCase()));if(blank<0&&fake>=0){const input=f.querySelector(`[name=guest${fake}]`);input.setCustomValidity(t('placeholderName'));input.reportValidity();return}if(blank>=0){const input=f.querySelector(`[name=guest${blank}]`);input.setCustomValidity(t('guestNeeded'));input.reportValidity();return}if(await action('entrant_add',{members})){deskPick={0:'',1:''};deskDraft={0:{q:'',guest:''},1:{q:'',guest:''}};deskOpen=null}}if(f.classList.contains('player-form')){const {rating,...rest}=v;await action('player_save',rating?{...rest,rating:Number(rating)}:rest)}if(f.getAttribute('id')==='sources-form'){const parsed=parseSource(v.url);if(!parsed){const i=f.querySelector('[name=url]');if(i){i.setCustomValidity(t('sourceHint'));i.reportValidity()}return}if(await action('source_add',{url:parsed.url}))sourceOpen=false}if(f.getAttribute('id')==='note-form')await action('note_add',{text:v.text})});
setInterval(tick,200);window.addEventListener('storage',e=>{if(e.key==='cp-ops-clock'){try{const next=JSON.parse(e.newValue)||timer;const durationChanged=next.duration!==timer.duration;timer=next;durationChanged?render():tick()}catch{}}});reload();

// ---- Vision: one stage, two rails, zero subtabs ---------------------------
// The review engine (app.js) owns the single frame surface; this shell owns the
// live source lifecycle and hands the vision-stage adapter its callbacks.
function reviewState(){try{return review()?.snapshot?.()||{}}catch(_){return {}}}
// Round 13, owner item 8: one simple configurator, on History and on Vision. It reads the same
// `data.sources` the console has always kept and writes the two actions it has always posted; the
// only thing that is new is that it is one place, reachable from both tabs, instead of a form that
// lived inside the vision rail.
function sourceRows(){const list=data?.sources||[];if(!list.length)return `<p class="muted">${esc(t('sourcesEmpty'))}</p>`;return list.map(s=>{const parsed=parseSource(s.url),kind=parsed?t(parsed.kind==='channel'?'kindChannel':'kindVod'):t('source');return `<div class="entry row"><span class="grow"><strong>${esc(kind)}</strong> <small class="source-url">${esc(s.url)}</small></span>${btn(t('remove'),'source-remove',`data-id="${esc(s.id)}"`)}</div>`}).join('')}
function sourceModal(){return `<div class="modal-backdrop" data-action="sources-close"><div class="modal modal--sources" role="dialog" aria-modal="true" aria-labelledby="sources-title"><div class="modal-head"><h3 id="sources-title">${esc(t('sourcesTitle'))}</h3><button type="button" class="close-x" data-action="sources-close" aria-label="${esc(t('closeLabel'))}">×</button></div><p class="muted">${esc(t('sourcesNote'))}</p><form id="sources-form"><label class="field"><span>${esc(t('source'))}</span><input name="url" type="url" required placeholder="https://www.twitch.tv/yourchannel" aria-describedby="sources-hint"><small class="muted" id="sources-hint">${esc(t('sourceHint'))}</small></label><div class="actions mt-3"><button class="primary">${esc(t('sourceAdd'))}</button><button type="button" data-action="sources-close">${esc(t('closeLabel'))}</button></div></form><div class="stack source-list">${sourceRows()}</div></div></div>`}
function channels(){return (data?.sources||[]).map(s=>{const parsed=parseSource(s.url);return parsed&&parsed.kind==='channel'?{id:s.id,url:s.url,channel:parsed.channel}:null}).filter(Boolean)}
// F5: saved VOD URLs are listed too (the form accepts them), so they can be used and removed.
function vods(){return (data?.sources||[]).map(s=>{const parsed=parseSource(s.url);return parsed&&parsed.kind==='vod'?{id:s.id,url:s.url,video:parsed.video}:null}).filter(Boolean)}
function channelOf(id){return channels().find(c=>c.id===id)?.channel||null}
// The roster the Vision rail labels person tracks from: every regular who is
// not retired, Active ones first, each with the rating that tells two similar
// names apart and a shell-language status word for the ones that are not Active.
function regulars(){return (data?.players||[]).filter(p=>p.status!=='Inactive').map(p=>({id:p.id,name:p.name,rating:Number.isFinite(Number(p.rating))?Number(p.rating):null,status:p.status||'Active',statusText:t(p.status||'Active')})).sort((a,b)=>(b.status==='Active')-(a.status==='Active')||(b.rating??0)-(a.rating??0))}
function liveSourceLabel(value){const [kind,...rest]=String(value).split(':');const id=rest.join(':');if(kind==='twitch'){const channel=channelOf(id);return channel?`twitch ${channel}`:liveText('Twitch channel','Twitch 频道')}if(kind==='vod-replay')return `${liveText('VOD replay','回放')} ${vodChoice?.vod_id||''} · ${liveText('rate','倍速')} ×${vodChoice?.rate??1} · ${liveText('from','起始')} ${vodChoice?.start_s??0}s`;return `${liveText('dataset','数据集')} ${id}`}
// The chosen VOD, for the panel: it must say what was asked for, and never that
// it is live. The running replay's own description comes from the server status.
function replayChoice(){return liveChoice==='vod-replay'&&vodChoice?{...vodChoice}:null}
function pickReplay(choice){const id=String(choice?.vod_id??'').trim();if(!id){message(liveText('Enter a Twitch VOD id or URL','请输入 Twitch 回放 id 或网址'),true);return}const digits=id.replace(/\/+$/,'').replace(/^https:\/\/www\.twitch\.tv\/videos\//,'').replace(/^[vV]+/,''),rate=Number(choice?.rate)>0?Number(choice.rate):1;if(!/^\d+$/.test(digits)||!(Number(digits)>0)){message(liveText('Use a Twitch VOD id or https://www.twitch.tv/videos/<id>','请输入 Twitch 回放 id 或 https://www.twitch.tv/videos/<id> 网址'),true);return}if(rate>8){message(liveText('Rate must be more than 0 and at most 8','倍速须大于 0 且不超过 8'),true);return}vodChoice={vod_id:id,start_s:Math.max(0,Number(choice?.start_s)||0),rate};liveChoice='vod-replay';visionAttempt=null;review()?.setLiveAttempt({source:liveChoice,at:Date.now(),error:null});renderSurface()}
function pickLive(value){liveChoice=value;visionAttempt=null;review()?.setLiveAttempt({source:value,at:Date.now(),error:null});renderSurface()}
function startLive(){visionAttempt=null;review()?.setLiveAttempt(null);liveAction('start')}
function stopLive(){liveAction('stop')}
function setLiveDetectors(list){liveDetectors=list.length?list:['table'];renderSurface()}
async function forgetChannel(id){await action('source_delete',{id});renderSurface()}
function attachSurface(){const mount=$('#vision-surface');if(!mount||!window.VisionStage)return;mount.removeAttribute?.('aria-busy');mount.removeAttribute?.('data-loading');mount.querySelectorAll?.('.vs-loading').forEach(n=>n.remove());visionAdapter=window.VisionStage.attach({mount,lang,review:review(),channels,vods,regulars,chat:()=>chat,toggleChat:()=>{chat=!chat;render()},pickLive,startLive,stopLive,setLiveDetectors,liveDetectors:()=>[...liveDetectors],forgetChannel,fixedClip:()=>!!reviewId,openSources:()=>{sourceOpen=true;render()},pickReplay,replayChoice,notice:text=>message(text,true),
// Owner item 3: on the Vision tab the workbench is the live stream - no dataset chip, no replay
// form, no frame transport. Those belong to a night's recorded review, which is opened from
// Records and is the only place `liveOnly` answers false while the console is not on Vision.
liveOnly:()=>!reviewId&&tab==='vision',
// After a confirmed enrolment the roster must come from a fresh read, not from the
// shell's copy: reload() re-reads /api/operations and re-renders.
reloadRoster:()=>reload()})}
function renderSurface(){attachSurface();visionAdapter?.render()}
})();
