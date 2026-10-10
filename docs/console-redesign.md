# Corner Pocket 控制台重设计规格（店主 8 条）

**状态**：设计关卡产物，只写这一个文件；未改任何产品代码，未新增依赖、未加构建步骤。
**工作树**：`/home/haoye/projects/pool-w-design`，分支 `b10-design`，base = `main` = `db58594`。
**适用代码**：`annotator/ops.html`（2590 B 外壳）、`annotator/ops.css`（71582 B）、`annotator/ops.js`（109510 B / 229 行，无构建步骤，源文件即产物）、`annotator/clock-sync.js`（共享计时）、`annotator/operations.py`（动作层）、`annotator/unified_server.py`（`/api/operations`、`/api/vods/*`）、`tests/test_ops.js`（105 个测试）。
**行号约定**：`ops.js:24` 指该文件第 24 行（该文件一行一个分区，多数行是整段函数）。**每个行号在改动前必须用锚点串再核一次**（本文件给的是 `main@db58594` 的读数）。

本规格只回答一件事：**照着改，改成什么样**。每条决定后面括号里是"为什么不选另一种"。

---

## 0. 一句话结论

**五个一级目的地，靠数据状态决定看到什么，不靠第二层菜单。**

| 一级目的地 | 它是什么对象 | 什么时候出现 |
|---|---|---|
| `tonight`（今晚） | 球台（Tables）—— 常驻主体，永远可见 | 永远 |
| `records`（战绩档案） | 历史赛事档案 —— 时间线 | 永远 |
| `vision`（视觉） | 摄像机 / 回放 —— 单舞台双轨，本来就没有子 tab | 永远 |
| `players`（常客） | 人 —— 名册 + 球房战绩 | 永远 |
| `status`（后台） | 系统自己 —— 只有出问题时才占导航位 | 有需要维护的事实时 |

今晚页内部有四个**由数据推断**的状态（未开赛 / 报名中 / 比赛中 / 收尾），它们不是 tab：没有可点的分层菜单，状态由 `data` 推导，按钮按"服务端现在允许什么动作"出现或禁用。
Play 的三段（Queue / Tables / Bracket）**合并成一页**：`playScreen()` 本来就同时渲染三段（`ops.js:49`），只是加 `hidden`——本次把三段内容的排版权重改掉，并把那一排 `nav.playtabs`（`ops.js:46`、`ops.css:669`）整排删除。

---

## 1. 最终一级导航

### 1.1 集合、文案、去向

| 最终 id | EN | 中 | 旧 id | 说明 |
|---|---|---|---|---|
| `tonight` | Tonight | 今晚 | `tonight` + `floor` + `matches` + `setup` | 球台页吸收 Floor（记分板）、Matches（对阵表）、Set up（开赛设置）三个已退休屏幕 |
| `records` | Records | 战绩档案 | `records` | 语义收窄：**唯一**职责是"历史赛事入口" |
| `vision` | Vision | 视觉 | `vision` | 不动（它已经是"无分层"的范例） |
| `players` | Regulars | 常客 | `players` | 加一列 house standing（第 6 节） |
| `status` | Back room | 后台 | `status` | **条件项**：没有需要维护的事实时不占导航位（1.4） |
| —（无） | — | — | 已删除：Tonight 的 phase 条、Play 的 playtabs、`More` 展开面板 | 见第 2 节 |

`navTabs` 的**数组值不变**（`ops.js:24` 仍为 `['tonight','records','vision','players','status']`），这样 `screens` 映射（`ops.js:102`）和"每个 tab id 都能解析到一个屏幕"这条不变量（`test_ops.js:2081`）继续成立；**变的是渲染时用哪份列表**（`primaryNav()`，1.4）。

### 1.2 为什么是这五个：按"对象"切，不按"时间流"切

现有 5 个 tab 是按**时间流**切的：Tonight（现在）→ Records（过去）→ Vision（证据）→ Regulars（人）→ Back room（系统）。问题在于：球桌上的比赛、历史赛事、摄像机画面、名册、后台**是四五个同时存在的对象**，不是五个先后阶段。操作员在一条比赛流里被迫多次换 tab，正是店主第 7、8 条的来源。

新切法按对象切：**一张球台、一段历史、一台摄像机、一个名字、一个系统**。判据（能拿代码验证，不是感受）：一次真实操作任务（"把 T2 的分签掉"）需要经过的 tab 数从 2（Tonight→Play 那层 + 记分板）降到 1。

**为什么不选"把 Play 提升为一级 tab"**：那会把 `tonight`（报名/编排）和 `tables`（打球）劈成两个一级项，操作员在"报名→开打"之间要跳 tab，而这两件事在同一张球台上发生。店主第 8 条要的是"Tables 永远可见"——把球台留在 Tonight 里、把报名/编排做成**球台页上按状态出现的卡片**才对。

**为什么要改名 `Play`/`Floor` 的痕迹**：`words.floor`、`words.playQueue`、`words.playTables`、`words.playBracket`、`words.playViews` 全部退休（第 8 节），因为新页面里没有"视图"这个概念可指。

### 1.3 顶栏（店主第 1 条）

`annotator/ops.html` 现在是一条 `<header>` 里塞了三层：`.bar`（`.brand` + `.tools`）→ `#nav` → `#strip`，再往下才是 `#tabbar`。目标：**一层 bar**。

```html
<header><div class="bar">
  <a class="hall" href="/ops.html" aria-label="Corner Pocket"><span class="ball black"><i>8</i></span><span class="hallname">Corner Pocket</span></a>
  <nav id="nav" aria-label="Primary / 主导航"></nav>      <!-- tab 移进顶栏，就在这个 .bar 里 -->
  <div class="tools">
    <span id="connection" class="badge" hidden></span>      <!-- 只在离线/失败时出现（1.5） -->
    <nav class="clockbar" aria-label="Shot timer / 击球计时" data-clock-host></nav>
    <div class="chip-group" role="group" aria-label="Language / 语言">…EN / 中…</div>
    <div class="chip-group" role="group" aria-label="Color theme / 配色" data-theme-group>…暗 / 亮…</div>
    <button data-action="backfill-open">…</button>          <!-- 次要入口，第 7 节 -->
  </div>
</div>
<div id="strip"></div></header>
```

改动要点：
1. `.brand` → `.hall`：**去掉 `<small id="tagline">`**（`render()` 里 `#tagline` 的赋值 `ops.js:103` 随之删除，`words.tagline` 退休）。保留 8 球 + 店名：店主说去掉的是**品牌区**（那块占了一整块、带副标题的盒子），不是把球房名字抹掉——顶栏左侧留一个静态文字标识，是操作员确认"我在哪台机器上"的最后一点线索。**砍掉的**：副标题 `POOL HALL OPERATIONS · 球房运营台`（它只说了一遍店名已经说过的事）。
2. `#nav` 从 `<header>` 的子元素变成 `.bar` 的子元素（就是把它从第 2 行挪进第 1 行）。CSS 从 `.bar,nav,main{max-width:...}`（`ops.css:72`）里把 `nav` 拆出来，改为 `.bar > nav{flex:1 1 auto;min-width:0}`。
3. `header` 的高度因此从"三行 + 一行 tabbar"降到一行。**这就是第 8 条要的那点垂直空间**：Tables 主体整体上移约 96–120 px（按现在 `.bar` + `nav` + `#strip` 的实测高度，实现时用截图量一次并写进 `docs/console-shots.md`）。
4. `#strip`（时钟）留在 header 内、bar 之下：它是**本机计时器**，不是导航，塞进 bar 会让 bar 在比赛时抖动。

### 1.4 条件项：Back room 什么时候出现

`status` 是唯一一个"不出现问题就不该占位"的目的地。谓词（全部来自已有 state，不需要新字段）：

```
needsBackRoom() =
     (data.sources || []).length === 0                      // 一个来源都没配
  || !(data.settings && data.settings.publicBoard !== false && ...)  // 公开记分板被关掉
  || lastError()                                            // 最近一次动作失败且未恢复
  || jobFacts().state !== 'idle'                            // 有导入作业在跑（第 7 节）
  || (data.players || []).some(p => p.status === 'Inactive') // 名册里有需要处理的人
  || budgetWarning()                                        // /api/vods/estimate 报过磁盘不足
```

成立时 `status` 出现在顶栏（5 项），不成立时不出现在顶栏（4 项）。

**关键约束**：`primaryNav()` 只影响**渲染**。`screens.status`、`routeOf('status')`、`#/backroom` 永远照常工作——直接贴 URL 进来照样开页面，而且此时 `primaryNav()` 必须把 `status` 也画出来（否则用户会掉进一个没有导航高亮的页面）。**为什么不干脆删掉 Back room**：`roadmapPanel()`（`ops.js:191`）里 9 条诚实延期项、外观设置（`appearancePanel()`）、来源管理、导入作业进度都在那儿；删掉它们等于把"我们没做完的事"藏起来，违反诚实铁律。

### 1.5 顶栏 badge（店主第 2 条）

`render()`（`ops.js:103`）现在写 `$('#connection').textContent = \`${t('connected')} · ${data.revision}\``。**删掉整条赋值**；`words.connected`（`LOCAL · SAVED / 本地 · 已保存`）与 `words.offline` 一并退休。

替代：
- `#connection` 元素的 `hidden` 属性由**连接健康**驱动：`reload()` 成功 → `hidden`；`reload()` 失败 → 显示 `t('connectionLost') = ['OFFLINE · edits will not save','离线 · 改动不会保存']`。
- 语言的切换（`lang`）、主题（`theme`）本来就是纯本地状态，从不依赖这个 badge，删掉不丢信息。
- `data.revision` 仍然是**乐观写入与并发冲突的根据**（`action()` 里的 409 回滚，`ops.js:83-91`），只是不再当口号显示。**它去哪里了**：Back room 的系统状态行里以"上次写入 revision N · 时间"出现（一行，等宽字体，不抢占顶栏）。这样店主看不到的"数字"没有丢，只是从"标语"变成"维护页的一行事实"。

### 1.6 移动端（≤750 px）与顶栏的关系

`ops.css:697-705` 的现有规则保持不变并**推广**：`#nav` 在 ≤750 px 隐藏，`#tabbar` 变为固定底栏。第 1 条改的是顶栏，底栏不是"第二层菜单"，而是**同一个 `primaryNav()` 的第二个渲染位置**——`tabbarHTML()`（`ops.js:43`）改为读 `primaryNav()`，`barTabs`/`barMore`/`moreOpen`（`ops.js:40-41`）三个变量与 `#tabbar-more` 展开面板**整体删除**（第 2 节）。

底栏在手机上有 4 个等宽槽（条件成立时 5 个）。`ops.css:697` 的 `.tabbar-slot{flex:1 1 0}` 直接支持 4 或 5 个槽，无需新样式。

---

## 2. 状态机

### 2.1 状态集合与转移

两级状态，都从数据推导，都不需要新字段：

**场地级（永远只有一个值）**

| 状态 | 谓词 | 屏幕上多出什么 |
|---|---|---|
| `idle` | `data && !matches().length` | 球台网格 + "开始今晚"卡（开赛设置表单折叠在卡里） |
| `registration` | `matches().length === 0 && entrants().length > 0` | 报名台（`desk-search` ×2、常客、guest、Rack 按钮） |
| `active` | `matches().length > 0 && matches().some(m => m.status !== 'complete')` | 记分板 + 队列 + 对阵表 + 在场名单 |
| `complete` | `matches().length > 0 && matches().every(m => m.status === 'complete')` | 收尾卡（赛果单、第二次机会、归档并新开、删除） |

与现有 `nightPhase()`（`ops.js:30`）逐字等价：`!ms.length → register`；全 complete → `close`；否则 `play`。**这是有意的**：`nightPhase()` 已经在 5 个测试里被固定成事实，新状态机只是给它换一层更好的呈现，不动它的判定。

**服务端闸门（权威）**：`data.tournament.status` 的 `'registration' → 'active' → 'complete'`（由 `operations.py` 的 `tournament_start` 与最后一场签字推进，`operations.py:379`、`operations.py:248`）。客户端不推断这两个值，只用它们决定**按钮的可用性**（2.4）。**为什么两级都要**：客户端状态决定"画什么"，服务端状态决定"能做什么"。前者失效只会画错，后者失效会写出非法数据。

### 2.2 无第二层 tab：为什么不再需要

现有的两层都有具体病灶，删掉之后**没有信息无家可归**：

| 被删的层 | 位置 | 为什么它本来就不该在 | 内容去哪 |
|---|---|---|---|
| `nav.phases`（register/rack/play/close） | `ops.js:33` `phaseStrip()`、`ops.css:654` | 四个"阶段"不是四个目的地，是**一晚的四个时刻**；而且 `curPhase()`（`ops.js:31`）已经能在没有它的情况下算出当前阶段——条子只是把算出来的东西又画了一遍 | 变成顶部一条**只读进度条** `.scene`（无 `button`、无 `data-phase`、无 `aria-current`），以及四张**按状态出现的卡** |
| `nav.playtabs`（queue/tables/bracket） | `ops.js:46` `playStrip()`、`ops.css:669` | 三段内容 `playScreen()`（`ops.js:49`）**同时渲染**，只是加 `hidden`；一排 tab 存在的唯一作用是让操作员把自己已经看得到的东西藏起来 | 三段按 2.3 的权重排成一页 |
| `#tabbar-more`（More 展开） | `ops.js:43`、`ops.css:704` | 一个"更多"按钮把两个目的地藏在一层后面，而它们和其它三项是同级对象 | 常驻 4 槽（1.4/1.6）；Back room 条件出现时不进 More，直接占一个槽 |

### 2.3 今晚页的四个状态：无 tab 怎么"有状态"

规则一句话：**状态决定画面上哪些卡存在，按钮决定状态怎么走。**

```
#/tonight  ·  状态 active
┌───────────────────────────────────────────────────────────────────────────────┐
│ 8  Corner Pocket   [今晚 Tonight] 战绩档案 视觉 常客 后台   EN|中 ☾|☀  ⏱ 0:27 ▶ ↺ │ ← 一层顶栏
├───────────────────────────────────────────────────────────────────────────────┤
│ 今晚 · 8-Ball Open · 单败 · 抢 7 · 报名中 ✓ ──●── 比赛中 ── 收尾        [归档并新开]│ ← .scene 只读进度（无按钮）
├───────────────────────────────────────────────────────────────────────────────┤
│ 球台                                                    TONIGHT'S TABLE       │
│ ┌ T1 Lulu 3–1 Alan   已签 ✓ ┐ ┌ T2 TJJ 2–0 Haoye   进行中●┐ │ 1 Wanwan 1/1      │
│ └ 45 分钟前签字             ┘ └ [A TJJ ●●○ 2  + −]         ┘ │ 2 Su     0/1      │
│ ┌ T3 free   [派下一场 →]   ┐ ┌ T4 free                      ┐ │ 3 Rico   0/0      │
│ └──────────────────────────┘ └─────────────────────────────┘ └───────────────────┘
├───────────────────────────────────────────────────────────────────────────────┤
│ 当前球台 T2 · TJJ vs Haoye                                                  │
│ ┌ TJJ        2   [+][−]   ▸ 更多（让分/弃权/缺赛）────────────────────────────┐
│ └ Haoye      0   [+][−]   [清空] [释放球台] [签字确认]                        ┘
├──────────────────┬────────────────────────────────────────────────────────────┤
│ 排队 QUEUE       │ 对阵表 BRACKET（只读）                                     │
│ Rico–Keiko [派→T3]│ 第 1 轮  Wanwan 3–1 Su ✓   Lulu–Alan T1   TJJ–Haoye T2     │
│ Yuefu–Nadia 已延 │ 第 2 轮  …                                                 │
│ 第 2 轮 … 等待中 │                                                            │
└──────────────────┴────────────────────────────────────────────────────────────┘
```

状态对画面的影响（实现时就是 `tonightScreen()`（`ops.js:35`）里的条件渲染）：

| 状态 | 出现的卡 | 消失的卡 |
|---|---|---|
| `idle` | `.card--start`（赛事名 / 赛制 / 抢几 / 球台数 + `开始今晚`）、球台网格空态、`firstRun()` 三步引导 | 记分板、队列、对阵表、报名台、收尾卡 |
| `registration` | 报名台（常客搜索 → 报名）、guest 添加、在场（Rack）、`随机配对`（有 2+ 单人报名者时）、`开赛` | 记分板、对阵表、收尾卡 |
| `active` | 记分板（**绑在"当前球台"`curTable` 上**）、队列、对阵表、在场、收尾入口（只在全部签完时出现） | 开赛设置表单、报名台（折叠进"补报名"次要按钮） |
| `complete` | 收尾卡（赛果单 / 复制文字 / 第二次机会 / 归档并新开 / 删除）、对阵表（只读） | 记分板、队列、报名台 |

**跨刷新保持"有状态"的三条本地记忆**（都用 `localStorage`，键前缀 `cp-ops-`，与现有 `cp-ops-clock` 同一套）：
- `cp-ops-curtable`：当前球台 id。刷新后记分板还在这张台上。
- `cp-ops-anchor`：`tonight` 页的滚动锚点（球台 id 或卡片 id）。刷新/后退后回到同一处。
- `cp-ops-clip-<matchId>`：**签了一半的分只在最后签字时写服务端**（`ops.js:83-91` 的即时写入是"每一步即一次写入"，把草稿留在本地才不会半路污染服务端）。半个比分是操作员的草稿，不是服务器的事实。

**键盘可达性（铁律）**：状态切换不改变焦点位置。`render()` 后焦点必须落在**同一语义位置的元素**上（`document.activeElement` 的 `data-anchor` 值不变）；原来 `phaseStrip()` 上的 `aria-current="step"` 全部删除，改为 `.scene` 上的 `aria-current` 仅在当前节点，且 `.scene` 是一个 `role="status"` 而非 `nav`——它是报告，不是控件。

### 2.4 状态怎么走：按钮就是唯一的"下一步"

没有 tab 之后，"新赛事 → 报名 → 编排 → 开打"靠**服务端已经强制的动作前置条件**逐步解锁。下表左边是服务端已有的检查（`operations.py`），右边是客户端画什么：

| 服务端已经拒绝的情况 | 出处 | 客户端画法 |
|---|---|---|
| `pair_draw`：`status !== 'registration'` | `operations.py:289` | `随机配对` 按钮只在 `status === 'registration'` 出现 |
| `pair_draw`：`len(entrants) < 2`，或单人报名者奇数 | `operations.py:357`、`operations.py:335` | 按钮 `disabled` + 一行说明（`words.pairNeedEven` 已有） |
| `tournament_start`：`status !== 'registration'` | `operations.py:379` 前 | `开赛` 只在 `registration` 出现 |
| `match_schedule`：`match.status in ('complete','pending')` / 有边未定 / 球台被占 | `operations.py:383-395` | `派→T3` 只在候选球台上出现；被占的台画成 `占用` 不可点 |
| `match_score`：非 live、比分不是抢 N、平局 | `operations.py:426` | `签字确认` 只在 `max(score) === raceTo` 且不平时可用 |
| `tournament_delete`：有已签赛果 | `operations.py:1`（"An event with a signed result cannot be deleted"） | 收尾卡里 `删除` 按钮对这种情况**不出现**，只出现 `隐藏` |

**为什么这样做而不是自己写一套客户端闸门**：客户端闸门与服务端闸门一旦有偏差，就会出现"按钮亮着但服务端拒"的死路（现有 `validationZh`（`ops.js:79`）就是为这类回退准备的）。这里让服务端当唯一权威，客户端只做**显隐**；被拒时仍走 `message(text, error, detail)`（`ops.js:81`）双语解释。

### 2.5 URL hash：可分享、可刷新、可后退

一级路由不变（`routePaths`，`ops.js:25`），只把 `tonight` 的**阶段后缀删除**：

| 目的地 | hash | 备注 |
|---|---|---|
| 今晚（任意状态） | `#/tonight` | 状态由数据推断，不由 URL 决定 |
| 战绩档案 | `#/records` | 展开某一项：`#/records/<eventId>`（新增，用于"把手上的链接发给别人"） |
| 视觉 | `#/vision` | 不变 |
| 常客 | `#/regulars` | 不变；选中某人：`#/regulars/<playerId>`（新增） |
| 后台 | `#/backroom` | 不变 |
| 赛果单（打印） | `#/records/<eventId>/sheet` | 复用现有 `sheetId` 状态（`ops.js:139`） |

旧 hash 的落点（`legacyRoutes`、`legacyPlay`、`phaseFromHash`，`ops.js:27-29` 改为**全部折向 `#/tonight`**）：

| 旧 hash | 新落点 | 理由 |
|---|---|---|
| `#/tonight/register` `#/tonight/rack` `#/tonight/play` `#/tonight/close` | `#/tonight`（原地 `replace`） | 阶段不再是路由；直接贴 `.../close` 的人看到的是当晚真实状态 |
| `#/setup` `#/floor` `#/matches` | `#/tonight` | 三个已退休屏幕 |
| `#/nowhere`、``、`#` | `#/tonight` | 与现状一致 |

**后退/前进语义**：`syncRoute(push)`（`ops.js:71`）只在**用户动作**时 `push`；状态从 `idle→active` 这类**数据驱动**的迁移只 `replace`（否则操作员每签一局就多一条历史记录，按三次后退还没退出今晚）。`canNavigate()`（`ops.js:21`）的 dirty/busy 否决**保留不动**：草稿（2.3 的 `cp-ops-clip-*`）存在时，导航先问一次。

**为什么不用 History API 的 pathname 路由**：`ops.html` 由 `unified_server.py` 的静态表提供（`unified_server.py:2270` 一带），pathname 路由需要在服务端加一条 catch-all；hash 路由零服务端改动、零刷新成本，且当前 5 条测试已经把它固定成契约。

---

## 3. 线框图

两个宽度都要看：**1440 桌面**（操作台）与 **390 手机**（手上）。两栏之下的细节在第 4–7 节。

### 3.1 `idle`（无赛事）— 1440

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ 8 Corner Pocket  [今晚 Tonight] 战绩档案 视觉 常客 后台      EN|中 ☾|☀      ⏱ shot timer 0:30 ▶ ↺ │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 今晚 · 还没有赛事                                                          [用 VOD 补录历史 →]│
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 球台                                                                     TONIGHT'S TABLE     │
│ ┌ T1 free ────────────────┐ ┌ T2 free ────────────────┐ ┌ T3 free ───────────┐ ┌ T4 free ─┐ │
│ │ 4 张台都可以用           │ │                          │ │                     │ │          │ │
│ └─────────────────────────┘ └──────────────────────────┘ └─────────────────────┘ └──────────┘ │
│                                                                                               │
│ ┌ 开始今晚 ────────────────────────────────────────────────────────────────────────────────┐  │
│ │ 赛事名 [8-Ball Open · 周一 9/1   ] 赛制 [单败▾] 抢几 [7] 球台数 [4]                       │  │
│ │                                    [开始今晚 →]                                          │  │
│ └──────────────────────────────────────────────────────────────────────────────────────────┘  │
│ ┌ 第一次用？三步 ──────────────────────────────────────────┐                                  │
│ │ 1 加常客（名册） → 2 报名 → 3 开台                          │                                  │
│ └──────────────────────────────────────────────────────────┘                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 `registration`（报名中）— 1440

```
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 今晚 · 8-Ball Open · 单败 · 抢 7 · 报名中 ✓ ──●── 比赛中 ── 收尾                            │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 报名台                                                                   4 人 · 2 张台空闲 │
│ 常客  [搜姓名…            ]  →  [报名]      临时客人 [姓名       ] [添加并报名]              │
│ 已报名： Wanwan ✓   Su ✓   Rico ✓   Keiko ✓        [随机配对] [开赛 →]（2+ 人可用）         │
│ 在场 tonight： ✗ Wanwan   ✗ Su   ✗ Rico   ✗ Keiko   （点一下 = 到了）                        │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 球台                                                      TONIGHT'S TABLE                    │
│ ┌ T1 free ┐ ┌ T2 free ┐ ┌ T3 free ┐ ┌ T4 free ┐            还没有开局                       │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 `active`（比赛中）— 1440

```
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 今晚 · 8-Ball Open · 单败 · 抢 7 · 报名中 ✓ ── 比赛中●── 收尾                               │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 球台                                                                   TONIGHT'S TABLE       │
│ ┌ T1 Lulu 3–1 Alan   已签 ✓ ┐ ┌ T2 TJJ 2–0 Haoye  进行中 ●┐ │ 1 Wanwan  1/1  · 100%      │
│ │ 45 分钟前                  │ │ 00:45                       │ │ 2 Su      0/1  ·   0%      │
│ └────────────────────────────┘ └─────────────────────────────┘ │ 3 Rico    0/0  ·   —       │
│ ┌ T3 free   [派下一场 →]     ┐ ┌ T4 free                     ┐ └───────────────────────────┘
│ └────────────────────────────┘ └─────────────────────────────┘   ↑ 本场战绩表（点数/比分）
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 当前球台 T2 · TJJ  vs  Haoye                                      00:45 · 本机计时         │
│ ┌ TJJ       2  [+][−]  ┐   [清空]  [释放球台]  [更多 ▾ 让分 / 弃权 / 缺赛]  [签字确认]      │
│ └ Haoye     0  [+][−]  ┘                                                                     │
├───────────────────────────────────┬──────────────────────────────────────────────────────────┤
│ 排队 QUEUE                        │ 对阵表 BRACKET（只读，随签字实时更新）                   │
│ 第 2 轮 Rico–Keiko   [派 → T3]    │ 第 1 轮  Wanwan 3–1 Su ✓   Lulu–Alan T1   TJJ–Haoye T2   │
│ 第 2 轮 Yuefu–Nadia  已延（缺赛） │ 第 2 轮  Rico–Keiko 等待中   …                           │
│ 第 3 轮 … 等待中                  │                                                          │
└───────────────────────────────────┴──────────────────────────────────────────────────────────┘
```

### 3.4 `complete`（收尾）— 1440

```
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 今晚 · 8-Ball Open · 单败 · 抢 7 · 报名中 ✓ 比赛中 ✓ ──●── 收尾                             │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌ 收尾 · 全部签完 ───────────────────────────────────────────────────────────────────────┐   │
│ │ 冠军 Wanwan（决赛 3–1 Su）                                                             │   │
│ │ [赛果单（打印）]  [复制赛果文字]  [第二次机会（随机抽签）]  [重命名]  [归档并新开]  [删除]│   │
│ └────────────────────────────────────────────────────────────────────────────────────────┘   │
│ ┌ 对阵表 BRACKET（只读）────────────────────────────────────────────────────────────────┐   │
│ │ 第 1 轮 Wanwan 3–1 Su ✓ · Lulu 3–2 Alan ✓ · TJJ 3–0 Haoye ✓                            │   │
│ │ 第 2 轮 Wanwan 3–2 Lulu ✓ · TJJ 3–1 …       决赛 Wanwan 3–1 Su ✓                       │   │
│ └────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.5 `records`：Windows 时间线 — 1440

```
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 战绩档案                                          [用 VOD 补录历史赛事…]   [显示已隐藏 (2)] │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 2026                                                                                          │
│   九月 September                                                                              │
│   ●  9/1 周一   8-Ball Open · 周一 9/1        11 人 · 冠军 Wanwan         [展开 ▾]           │
│   │             └ 10 场签完 · 1 场缺赛 · 赛果单 · 来源：Twitch VOD 1234567890 ←（VOD 补录）│
│   ●  8/25 周一  周五 8-Ball Open（已重命名）    8 人 · 冠军 Su            [展开 ▾]           │
│   八月 August                                                                                 │
│   ●  8/18 周一  8-Ball Open · 周一 8/18         9 人 · 冠军 Rico          [展开 ▾]           │
│                                                                                               │
│ 展开后的样子（原地展开，不跳页）                                                              │
│   ●  9/1 周一   8-Ball Open · 周一 9/1        11 人 · 冠军 Wanwan         [收起 ▴]           │
│   │  ┌ 赛果单 ─────────────────────────────────────────────────────────────────┐            │
│   │  │ 第 1 轮 …  决赛 Wanwan 3–1 Su       [打开可打印赛果单] [复制文字]        │            │
│   │  └──────────────────────────────────────────────────────────────────────────┘            │
│   │  来源：Twitch VOD 1234567890 · 09:12–21:40 · 人工逐场确认 · [打开 VOD]                    │
│   │  [重命名]  [从历史隐藏]  [删除]（有已签赛果时"删除"不出现）                                │
│   │  ▸ 这一晚的流水（12 条：改名 / 配对 / 签字 / 存档）                                        │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.6 `vision` — 1440（不改结构，只改顶栏）

```
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 8 Corner Pocket  [今晚] 战绩档案 [视觉 Vision] 常客 后台        EN|中 ☾|☀   ⏱ shot timer 0:30 │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 来源 chips：VOD ×2 · 直播频道 · 新鲜度 · 快捷键   ──（这一行与今天的 Vision 完全一致）        │
├──────────────────┬───────────────────────────────────┬───────────────────────────────────────┤
│ 事件队列 280px   │ 舞台（唯一 16:9 画面）             │ 检视器 320px                          │
└──────────────────┴───────────────────────────────────┴───────────────────────────────────────┘
   ↓ 顶栏少了一层，舞台整体上移；Vision 自己的 DOM 一行未改
```

### 3.7 `players`（常客 + house standing）— 1440

```
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 常客                                          [搜姓名…        ]              [+ 添加常客]    │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 名字          状态     入会       球房战绩    场次   胜率                                    │
│ Wanwan        Active   2026-03-02  1080       24    75%   ▸ 点名字打开个人战绩（只读）        │
│ Su            Active   2026-04-11  1042       19    53%                                      │
│ Keiko         Visitor  2026-05-20     0        0     —     ← 无战绩：破折号，不是 0%          │
│ Rico          Inactive 2026-01-08  1155        8    62%                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.8 `status`（后台）— 1440

```
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 后台                                                                                          │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ 外观 / 球台（球色、灯光、菱形点）        公开记分板 [开] （/board/ 与 /display 同时受影响）   │
│ 来源（Twitch）：examplechannel  [删除]   [+ 添加来源]                                         │
│ 导入作业：idle（或 percent / eta / 取消）                                                     │
│ 上次写入 revision 41 · 2026-10-02 15:04   ← 从顶栏搬来的那条事实                              │
│ ▸ 维护者（9 条诚实延期项，默认折叠）                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.9 手机 390 — 今晚 `active`

```
┌──────────────────────────────┐
│ 8  Corner Pocket    EN ☾|[补录]│ ← 顶栏在手机上只剩身份 + 全局工具
├──────────────────────────────┤
│ 今晚 · 抢 7 · 比赛中 ●        │ ← .scene 只读一行
├──────────────────────────────┤
│ ⏱ shot timer 0:27 ▶ ↺   20 30│
├──────────────────────────────┤
│ T2 · TJJ  vs  Haoye      00:45│ ← 当前球台置顶（上次摸过的台）
│  TJJ     2   [+][−]           │
│  Haoye   0   [+][−]           │
│ [清空] [释放] [更多▾] [签字]  │
├──────────────────────────────┤
│ 球台                          │
│ T1 Lulu 3–1 Alan ✓            │
│ T2 ← 当前                     │
│ T3 free  [派下一场 →]         │
├──────────────────────────────┤
│ 排队 · 2 场等待        ▸ 展开 │
│ 对阵表（只读）         ▸ 展开 │
│ TONIGHT'S TABLE               │
│  1 Wanwan 1/1 · 2 Su 0/1 …    │
├──────────────────────────────┤
│ 今晚 │战绩档案│ 视觉 │ 常客   │ ← 固定底栏 = 同一份 primaryNav()
└──────────────────────────────┘
```

手机 390 — Records 时间线：

```
┌──────────────────────────────┐
│ 8  Corner Pocket    EN ☾      │
├──────────────────────────────┤
│ 战绩档案        [补录…]       │
├──────────────────────────────┤
│ 2026                          │
│  九月 September               │
│  ● 9/1 周一                   │
│  │ 8-Ball Open · 周一 9/1     │
│  │ 11 人 · 冠军 Wanwan        │
│  │ [展开 ▾]                   │
│  ● 8/25 周一                  │
│  │ 周五 8-Ball Open            │
│  │ 8 人 · 冠军 Su   [展开 ▾]  │
├──────────────────────────────┤
│ 今晚 │战绩档案│ 视觉 │ 常客   │
└──────────────────────────────┘
```

### 3.10 手机 390 — VOD 补录（全屏步骤页）

```
┌──────────────────────────────┐
│ ← 退出补录         步骤 2/5  │
│ 选哪一段                      │
├──────────────────────────────┤
│ 来源频道 examplechannel       │
│ ▸ 8-Ball Open · 9/1  3:12:40  │
│   9/1 20:00 · [选这段]        │
│ ▸ 周五夜赛  2:58:10            │
│   8/25 19:30 · [选这段]       │
│ 或者直接贴链接                │
│ [https://www.twitch.tv/videos/│
│  1234567890            ]      │
│ 起点 [0:00:00] 时长 [整场]    │
│ [估算大小]                    │
│ ── 估算：约 1.2 GB · 磁盘剩   │
│    84 GB · 已有同段导入（复用）│
│ [开始导入]                    │
└──────────────────────────────┘
```

---

## 4. Competition 闸门（店主第 8 条）

### 4.1 谓词

"有赛事进行中" = **服务端赛事状态不是 `registration` 且还没有收尾**：

```js
const tournament = () => data.tournament;                       // ops.js:78 已有
const comp = () => tournament().status || 'registration';       // 'registration' | 'active' | 'complete'
const liveComp = () => comp() === 'active';                     // 比赛进行中：显示 dashboard
const dirtyComp = () => matches().some(m => m.status === 'live'); // 台上有球：dashboard 置顶
```

出处（`annotator/operations.py`，全部**已存在**，不需要新字段）：
- 默认 `status='registration'`（`operations.py:61`）；
- `tournament_start` 置 `'active'`（`operations.py:379`）；
- 最后一场签字且已完赛的场次收尾时置 `'complete'`（`operations.py:247-248`：`if t['matches'] and t['matches'][-1]['status'] == 'complete': t['status'] = 'complete'`）；
- 归档并新开：`tournament_new` 把当前赛事推进 `history` 再换成全新 `tournament()`（`status` 回到 `'registration'`）。

因此闸门在数据层是**三值的**，客户端只关心两点：
1. `comp() !== 'active'` → dashboard（记分板 / 队列 / 对阵表）**不出现**；球台网格与"开始今晚"卡占满主体。
2. `comp() === 'active'` → dashboard 出现；若 `dirtyComp()` 为真，记分板**吸附在球台网格上方**（手机上直接置顶，见 3.9）。

**需要服务端补的字段**：无。`status` 的三个值都已写入并被测试固定。**唯一需要加强的一处**（可选，不算阻塞）：`tournament_start` 要求 `status === 'registration'`，所以"报名中但一场没开"和"刚点开赛"在 UI 上只差 `status` 一个值——这足够，不需要 `startedAt`。

### 4.2 Tables 页上的按钮（文案 + 动作序列）

`idle` 时球台网格下方那张卡，标题与按钮：

| 位置 | key | EN | 中 | 动作 |
|---|---|---|---|---|
| 卡片标题 | `startNight` | Start tonight | 开始今晚 | — |
| 主按钮 | `startNightGo` | Start tonight → | 开始今晚 → | `tournament_setup`（名/赛制/抢几/台数）→ 客户端状态进 `registration` |
| 报名台主按钮 | `drawPairs` | Random pairing（已有） | 随机配对（已有） | `pair_draw` |
| 报名台主按钮 | `startEvent` | Start the event → | 开赛 → | `tournament_start` |
| 球台卡按钮 | `sendNext` | Send next → T{n} | 派下一场 → T{n} | `match_schedule`（`table`, `matchId`） |
| 记分板主按钮 | `signScore`（已有） | Sign scorecard | 签字确认 | `match_score` + `score` |

逐步走（**全程不离开 `#/tonight`**）：

```
① 无赛事 → 卡片“开始今晚”填名字/赛制/抢几/台数 → [开始今晚]  → tournament_setup
② 报名中 → 报名台：常客搜索→报名（player_save/guest_promote）、点在场（entrant_absence）
③ 报名中 → [随机配对]（2+ 单人报名者）→ pair_draw；[开赛] → tournament_start（status='active'）
④ 比赛中 → dashboard 出现：队列里 [派 → T3] → match_schedule；T3 上记分 [签字确认] → match_score
⑤ 全部签完 → 收尾卡：[赛果单] [复制赛果文字] [第二次机会] [归档并新开] [删除]
⑥ [归档并新开] → tournament_new：当前赛事进 history（时间线立刻多一条新条目），status 回 registration
```

**为什么按钮是这样放的**：店主第 8 条要"赛事由 Tables 页上的按钮发起"。按钮落在**主体（球台网格）内**而不是顶栏：顶栏是全局的、与"今晚"无关的控件才该在那儿；"开始今晚"是这一页、这一晚的动作。**砍掉的**：一个常驻的 `+ 新赛事` 顶栏按钮（它会让人以为能同时开两个赛事，而 `data.tournament` 只有一个）。

---

## 5. Records = Windows 时间线（店主第 5 条）

### 5.1 Records 的唯一职责

`recordsScreen()`（`ops.js:139`）现在是三段并列 article：`standings`（House standings 全时段位表）、`timeline`（Night log 审计流水）、`history`（Archived events）。店主第 5 条把它收窄成**一件事：历史赛事的入口**，样式是 Windows 时间线（月份分节、每项一行、可展开）。

**三段的去向**（逐条给理由）：

| 旧段 | 去向 | 理由 |
|---|---|---|
| `standings`（House standings，全时段位表） | **移出 Records**：数据变成 Regulars 页每一行的列（第 6 节），记录明细仍在个人战绩弹窗 `recordView(p)`（`ops.js:145`）里 | 店主要的是"每个球员的 house standing 加到常客列表"（第 4 条）。同一张表留在两个地方就是两份会漂移的真相；`resultStats(pid)`（`ops.js:146`）本来就按人算，按人放才对 |
| `timeline`（Night log，`data.events` 审计流水） | **收进每一项的详情**：展开某一场 → `▸ 这一晚的流水（N 条）`（默认折叠） | 审计流水**不是历史赛事的入口**，它是某一晚的注脚。整个删掉会丢事实（谁改了名、谁配对、谁签的字），这也是"签名不可变、改名要留痕"（R2/R12）的实现基础。折进详情后，它从"第三段并列内容"变成"一条目的脚注"，Records 因此只剩一件事 |
| `history`（Archived events） | **就是新的时间线本身** | 第 5 条直说：Night log 与 Archived events 都被时间线取代 |

**这是本次两处主动减法之一**：Records 从三段降为一段（外加一个可选的审计脚注）。

### 5.2 时间线每一项的 schema

现在 `data.history` 里一个归档赛事（`operations.py` 的 `tournament_new` 用 `deepcopy(t)` 加 `archivedAt` 写入）能给的是：`id, name, format, tables, raceTo, entrants[], matches[], status, archivedAt`，外加可选的 `hidden: bool`（`tournament_hide` 写的）。够画：名称、日期、人数（`entrants.length`）、冠军（`champion(night)`，`ops.js:131`，取最后一场的 `winnerId`）、对阵（`eventTable(night)`，`ops.js:142`）。

**不够的与补法**（`schema` 只列**新增**字段；其余照旧）：

| 字段 | 谁能给 | 用途 | 缺失时 |
|---|---|---|---|
| `archivedAt` | ✅ 已有（`tournament_new` 写） | 排序、月份分组 | 理论上不会缺；缺了按 `id` 排序并归到"日期不详"分组 |
| `source: {vodId, datasetId, startS, endS, channel, title}` | ❌ 需新写（第 7.6 节的 `event_backfill`） | 时间线里"来源：Twitch VOD …"那一行 + 打开原片 | 不显示该行（**不显示"未知"，什么都不显示**；无来源的赛事本来就没有可打开的东西） |
| `signOff: {at, by?}` | ❌ 需新写 | 详情里"逐场人工确认于 …" | 同上一行处理 |
| `entrantNames[]` | ⚠️ 可由 `entrants[].name` 复算 | 搜索（R13 逐词 AND）与"搜人名找那一晚" | 直接用 `entrants` |
| `resultCount / byeCount / forfeitCount` | ⚠️ 可复算 | 行摘要"10 场签完 · 1 场缺赛" | 复算即可，不存 |
| `hidden` | ✅ 已有 | `[显示已隐藏]` 开关 | 视为 `false` |

**不需要服务端补的**：冠军、人数、对阵、赛果单全部可从现有字段复算（`champion()`/`eventTable()`/`resultsSheet()` 已经这么做）。**不要**为了"快"把复算结果存进 history：那会制造第二份真相，签字后改名就会对不上（R12 的教训）。

### 5.3 排序、分组、空态

- **排序**：`archivedAt` 降序（新在上）。同日按 `id` 降序（id 是单调 uid）。**为什么不用名称排**：店主看的是"最近哪几晚"，不是字母表。
- **分组**：年（`2026`）→ 月（`九月 September` 双语，见 8.2 的 `months` 表）。月份标题是**分组头，不是可点的筛子**。**砍掉的**一个筛选器行（年/月/来源三个下拉）：时间线本来就要向下滚，筛子把"最近"这件事藏起来，而且与搜索重复——搜索框一条就够（5.5）。
- **空态**：`emptyHistory`（已有）改为两行：`还没有历史赛事` + `[用 VOD 补录历史赛事…]`（同一个入口，空态是它的第二次出现）；如果 `history` 非空但**全部被隐藏**，显示 `全部 N 场都被隐藏 [显示已隐藏]`，而不是假装空。
- **隐藏项**：默认不画；`[显示已隐藏 (N)]` 开关打开后照常出现在时间线里，带 `已隐藏` 徽章（复用 `showHidden`，`ops.js:139`）。

### 5.4 展开的每一项

```
●  9/1 周一   8-Ball Open · 周一 9/1        11 人 · 冠军 Wanwan            [展开 ▾]
│  ├ 赛果单摘要：第 1 轮 … 决赛 Wanwan 3–1 Su      [打开可打印赛果单] [复制赛果文字]
│  ├ 来源：Twitch VOD 1234567890 · 09:12–21:40 · 人工逐场确认 · [打开 VOD]
│  ├ [重命名]  [从历史隐藏]  [删除]（有已签赛果 → 不出现"删除"）
│  └ ▸ 这一晚的流水（12 条）
```

- `打开可打印赛果单`：复用 `sheetId` + `resultsSheet(night)`（`ops.js:135`），hash 变成 `#/records/<id>/sheet`。**打印单是铁律，不动。**
- `复制赛果文字`：`resultsText()`（`ops.js:134`）原样复用。
- `重命名`：`tournament_rename`（只改名，已有）。
- `从历史隐藏`：`tournament_hide`（需要 `confirmed: true`，已有）。
- `删除`：`tournament_delete`。**有 `result in ('played','forfeit')` 的赛事服务端会拒**（"An event with a signed result cannot be deleted; hide it from history instead"）——所以按钮**干脆不画**，而不是画出来再被拒。这与现有测试 `delete only an unsigned event; otherwise hide it from history, which erases nothing (R1)`（`test_ops.js:1526`）一致。
- 审计脚注：`auditNights()`/`auditLine()`（`ops.js:111,117`）的输出按 `nightId` 过滤成 `<ol class="audit">`，默认折叠。

### 5.5 搜索与键盘

- 搜索框一条（`words.search` 已有= `Search names`）：匹配**赛事名 + 参赛人名**，用现有 `nameMatches(name, query)`（`ops.js:180`，NFKC + 去音标 + case fold + 逐词 AND + CJK 子串）。R13 的语义**逐字保留**：每个词都必须命中某个名字。
- 键盘：`Tab` 走 行 → 展开按钮 → 详情里的控件；`Enter`/`Space` 展开收起；展开用 `aria-expanded` + `aria-controls`，不改变焦点。**行本身不是链接**（否则 `Enter` 意义歧义）。

---

## 6. Regulars 加 house standing（店主第 4 条）

### 6.1 列

`playersScreen()`（`ops.js:187`）的行现在只有：名字、`badge(p.status)`、`fmtDate(p.joinedAt)`、`strong(p.rating)`。改为（桌面 ≥751 px）：

| 列 | 数据 | 来源（已存在） | 备注 |
|---|---|---|---|
| 名字 | `p.name` | `roster()` | 点名字打开这名常客自己的档案（管理视图），其中的 `[个人战绩]`（`recordView(p)`，`ops.js:145`）是只读页 —— **实现偏差，见 §12.7** |
| 状态 | `p.status` | `badge(p.status)` | Active / Visitor / Prospect / Inactive |
| 入会 | `p.joinedAt` | `fmtDate()` | |
| 球房战绩 | `p.rating` | 员工手填（`allTime` 文案已声明"并非计算得出"） | **保留"手填"的语义**，不能让它看起来像算出来的 |
| 场次 | `stats.played` | `resultStats(p.id)`（`ops.js:146`） | 只数**已签**赛果 |
| 胜负 | `stats.wins`–`stats.losses` | `signedResult`（`ops.js:140`） | |
| 胜率 | `stats.winPct` | 同上 | |

手机（≤750 px）：表变成两行卡 —— 第一行名字 + 球房战绩，第二行 `12 场 · 9 胜 3 负 · 75%`。**为什么不做横向滚动**：名册是竖着扫的清单，横向滚动会把"胜率"这一列推出屏幕外，等于没有。

### 6.2 无战绩的球员

`played === 0` → 场次显示 `0`，胜负显示 `—`，胜率显示 `—`。**绝不显示 `0%`**：0% 是"打了全输"，`—` 是"没打过"，两者对店主是不同的判断。文案已有 `signedOnly`（"只数已签赛果"）用来在表头下注一行。

### 6.3 排序与搜索

- **默认排序不变**：`roster()` 已按 `rating` 降序（`ops.js:78`）。**不新增排序控件**（店主要的是"看到 standing"，不是"排列 standing"）。
- **搜索不变**：`#roster-search` + `nameMatches`（R13 逐词 AND）继续原样工作；新列**不参与**匹配——加了会把"搜 Wanwan"变成"搜所有胜率含 7 的人"。`test_ops.js:633`（每个 shell 词都有双语）与 `test_ops.js:536`（R13 逐词）必须继续通过。

---

## 7. VOD 回填历史赛事（店主第 6 条）

### 7.0 诚实性红线（先立规矩）

这条流程**唯一**允许写进事实的两个来源：操作员**手输**的赛果，和 **VOD 自己的元数据**（时长、标题、时间）。流水线里**没有任何**"从视频猜比赛"的环节（本仓库不存在比赛边界/赛果检测器——已核对 `src/`、`annotator/`、`tests/` 无 match-detect 实现）。因此 UI **不许**出现 "detected matches / 已检测到 N 场比赛" 这类说法；正确说法是 **"你标记的场次"**。

落库时必须带 `source: {kind:'vod-backfill', vodId, datasetId, startS, endS, humanReviewed: true}`，并且赛果单上永久标一行 `来源：Twitch VOD <id> · 人工逐场确认`，与 `notSimulation`（"不显示模拟观测或虚构统计"）同一套诚实语法。

### 7.1 状态机

```
                    ┌──────────────── 任意时刻可 ← 退出（草稿留 localStorage，作业继续跑）
                    ▼
idle ──入口──▶ pick ──选/贴──▶ verify ──估算 ok──▶ importing ──job done──▶ dataset
                                 │ 失败/磁盘不足                    │ 失败/取消
                                 ▼                                  ▼
                              rejected（就地说明，回到 pick）      failed（可重试）
                                                                     │
dataset ──开始标记──▶ marking ⇄ match-draft（逐场：边界 / 胜者 / 比分）──▶ review ──[结算这一晚]──▶ done
                                                                          │ 校验失败
                                                                          ▼
                                                                       review（就地高亮缺项）
```

| 状态 | 进入触发 | 屏幕 | 关键 UI | 可后退到 |
|---|---|---|---|---|
| `idle` | 退出/未开始 | Records 时间线头部按钮、空态按钮、顶栏次要按钮 | `[用 VOD 补录历史赛事…]` | — |
| `pick` | 点入口 | 全屏步骤页 1/5「选哪一段」 | 已存频道的最近 VOD 列表（`/api/vods/recent`）+ 贴链接框 | 退出 |
| `verify` | 选了 VOD 或点了「检查」 | 2/5「估算」 | 起点/时长 + `[估算大小]`；显示大小、磁盘余量、`已有同段导入（复用）` | pick |
| `importing` | `[开始导入]` | 3/5「下载中」 | 进度条 `percent` / `eta_s` / `rate_mb_s` / `[取消导入]` | verify（仅取消后） |
| `dataset` | job `state==='done'` | 4/5「开始标记」 | 导入完成的视频 + 时长 + `[开始标记]`；同时给出「这场其实是哪一晚」的日期/名字表单 | pick |
| `marking` | `[开始标记]` | 4/5 工作区 | 播放器 + 本机时钟读数；`[开始这一场 @ 12:34]` / `[结束这一场 @ 28:10]`；已标 n 场（可删） | dataset |
| `review` | 最后一场标完 | 5/5「逐场确认」 | 每场一行：边界、胜者、比分、`[确认这场]`；全部确认后 `[结算这一晚]` 才可用 | marking |
| `done` | `event_backfill` 成功 | 5/5 成功页 | `这一晚已写进战绩档案` + `[看时间线]` | — |
| `failed` / `rejected` | 作业失败 / 估算被拒 | 就地错误页 | 原因 + `[重试]` / `[换一段]` | pick |

**刷新/中断**：`importing` 是服务端作业，刷新后靠 `/api/vods/job` 恢复；`marking` 的草稿（边界、胜者、比分、确认标记）在 `localStorage` 的 `cp-ops-backfill` 里，键含 `datasetId`；重新进入同一 `datasetId` 时提示 `继续上次的标记（n 场）？`——**不自动恢复**（半截的比分自动进流程会变成事实）。

### 7.2 每一步的文案（EN / 中）

| key | EN | 中 |
|---|---|---|
| `backfill` | Backfill from a VOD | 用 VOD 补录 |
| `backfillOpen` | Backfill a past event from a Twitch VOD… | 用 Twitch VOD 补录一场历史赛事… |
| `bfStep` | Step {n} of 5 | 步骤 {n}/5 |
| `bfPickTitle` | Which broadcast? | 选哪一段 |
| `bfPaste` | VOD link or id | 回放链接或 id |
| `bfCheck` | Check | 检查 |
| `bfStartAt` | Start at (h:mm:ss) | 起点（时:分:秒） |
| `bfLength` | Length (min, empty = to the end) | 时长（分钟，留空＝到结尾） |
| `bfEstimate` | Estimate | 估算大小 |
| `bfEstimateLine` | About {size} · {free} free on disk · {reuse} | 约 {size} · 磁盘剩余 {free} · {reuse} |
| `bfReuse` | this range is already downloaded | 这一段已经下载过 |
| `bfStartImport` | Start the download | 开始导入 |
| `bfImporting` | Downloading the broadcast | 正在下载这场回放 |
| `bfCancel` | Cancel the download | 取消下载 |
| `bfUploaded` | Recorded broadcast, downloaded once | 已下载的回放 |
| `bfWhichNight` | Which night was this? | 这是哪一晚？ |
| `bfNightName` | Event name | 赛事名 |
| `bfStartMarking` | Start marking | 开始标记 |
| `bfMarkStart` | This match starts here | 这一场从这里开始 |
| `bfMarkEnd` | This match ends here | 这一场到这里结束 |
| `bfMarked` | {n} matches marked by you | 你已标记 {n} 场 |
| `bfReviewTitle` | Confirm each match | 逐场确认 |
| `bfWinner` | Winner | 胜者 |
| `bfScore` | Final score | 最终比分 |
| `bfConfirmMatch` | I watched this — confirm | 我看过了 —— 确认这场 |
| `bfUnconfirmed` | {n} matches still unconfirmed | 还有 {n} 场未确认 |
| `bfCommit` | Write this night to Records | 把这一晚写进战绩档案 |
| `bfDone` | This night is in Records | 这一晚已写进战绩档案 |
| `bfOpenTimeline` | Open the timeline | 看时间线 |
| `bfHonest` | Every result below was typed and confirmed by a person. Nothing here was detected automatically. | 下面每一条赛果都由人工输入并逐场确认。没有任何一条是自动识别出来的。 |
| `bfSameVod` | This range is already in the console. Open it, or pick another range. | 这一段已经在控制台里了。打开它，或换一段。 |
| `bfLeft` | The draft is on this device. The download keeps running without this page. | 草稿保存在本机。离开这个页面下载会继续。 |
| `backfillSource` | Source: Twitch VOD {id} · {range} · confirmed match by match | 来源：Twitch VOD {id} · {range} · 逐场人工确认 |
| `backfillOpenVod` | Open the broadcast | 打开回放 |

### 7.3 失败与中断

| 情况 | 服务端现状 | UI 处理 |
|---|---|---|
| VOD 不存在 / 私有 / 已过期 | `vod_info(strict=True)` → `TwitchVodError` → 502（`vod_import.py:195`） | `verify` 就地显示 Twitch 的原句（可能英文）+ 本地一句中文解释；不写入任何东西 |
| 频道不是已存来源 | `_plan()` → `REFUSED_CHANNEL`（`vod_import.py:196`） | 提示 `先在后台添加这个频道，或换一个已保存的频道` + `[去后台]` 链接（`#/backroom`） |
| 磁盘不足 | `_disk()` → `VodImportError(..., 507)`（`vod_import.py:297`） | 显示 `需要约 X GB，剩 Y GB` + `[换更短的一段]`；不允许开始 |
| 已经在导入（单作业） | `start()` → 409 `An import is already running (…)`（`vod_import.py:284`） | 显示 `正有一个导入在跑（<id>，<percent>%）` + 进度 + `[等它跑完]` / `[取消它]`。**不做队列**：`VodImporter`（`vod_import.py:168` 的 docstring：*"The single-flight import job of one workspace root"*）本来就是单作业，排队需要服务端支持（7.5 明确不做） |
| 同一 VOD/段重复回填 | `start()` → 409 `… is already imported; delete it first…`（`vod_import.py:290`） | `bfSameVod` + `[打开它]`（直接跳到该 dataset 的标记步骤，复用已下载文件） |
| 下载失败 / ffmpeg 非零退出 | `_finish(error=…)`，job `state='failed'` | 错误页显示 job 的 `error` + `[重试]`；`.part` 文件由服务端删（`close()`，`unified_server.py:378`） |
| 用户离开页面 / 关标签 | 线程在服务端继续 | `bfLeft` 一句说明；回到补录入口时靠 `/api/vods/job` 恢复进度；草稿在 `localStorage` |
| 结算时数据非法（缺比分/胜者） | 新的 `event_backfill` 校验 | `review` 就地高亮缺项，逐条列出"第 3 场没有比分"，**不写任何东西** |
| 网络中断 | fetch 抛错 | 与现有 `action()` 一致：`message(text, error, detail)`；作业状态以服务端为准（轮询 `/api/vods/job`） |
| 事后想撤销这一晚 | — | 用时间线的 `[删除]`（未被签字保护时）或 `[从历史隐藏]`；**不提供"回填专用撤销"**——它会造成第二套删除语义 |

### 7.4 需要服务端做什么：复用 vs 新增

**直接复用（零改动）**：`/api/vods/recent`（已存频道最近 VOD）、`/api/vods/estimate`（大小/磁盘/是否已导入）、`/api/vods/import`（下载成 dataset）、`/api/vods/job`（进度）、`/api/vods/cancel`、`/api/vods/delete`；dataset 注册（`src/datasets.py`）保证导入后 Vision 立即可打开它。

**必须新增（一处）**：`/api/operations` 的一个动作 `event_backfill`，payload：

```json
{"revision": 41, "action": "event_backfill",
 "event": {"name": "8-Ball Open · 周一 9/1", "format": "singles", "raceTo": 7, "tables": 4,
           "entrants": [{"name": "Wanwan"}, {"name": "Su"}],
           "matches": [{"round": 1, "sides": ["<eid1>", "<eid2>"], "score": [3, 1],
                        "winner": "<eid1>", "result": "played", "clip": [452, 1690]}]},
 "source": {"kind": "vod-backfill", "vodId": "1234567890",
            "datasetId": "tw-1234567890-452-1690", "startS": 452, "endS": 1690,
            "channel": "examplechannel", "title": "…", "humanReviewed": true}}
```

服务端行为（写进 `operations.py` 的 `_apply`）：
1. 校验：`matches` 非空、每场两边都在 `entrants` 里、`score` 非负整数、`winner` 属于该场、`clip` 是 `[int,int]` 且 `start < end`、`source.humanReviewed === true`。任一不满足 → `ValueError`（400），**什么都不写**。
2. 生成与 `tournament_new` 同形的归档对象（同一套字段 + `archivedAt`），**追加**到 `history`（不替换当前 `tournament`——回填的是过去，不该打断今晚）。
3. 给该条加 `source` 与 `signOff: {at: timestamp()}`；追加一条 `events` 审计（`action: 'event_backfill'`，含 `vodId`）——**审计流水是"谁写的"的唯一证据，回填也必须留痕**。
4. 幂等：同一 `datasetId` 已经写过 → 409，并返回已有 `history` 条目的 id（UI 直接打开它）。

**明确不新增**：不新增"从视频检测比赛"的服务端能力（7.0）；不做导入队列（7.3）；不新增 dataset 之外的存储。

### 7.5 为什么这套设计不会把猜测写成事实

1. **没有猜测环节可写**：客户端只有两个写入口——`/api/vods/import`（下载字节）与 `event_backfill`（人写的赛果）。中间不存在模型输出。
2. **确认是逐场的、带时间戳的**：`signOff.at` + 每场的 `humanReviewed` 由 `[我看过了 —— 确认这场]` 触发，未确认的场次无法进入 payload（`[结算这一晚]` 在 `unconfirmed > 0` 时禁用，服务端再校验一次）。
3. **来源永久随赛事走**：时间线与赛果单永远打印 `backfillSource`。别人（包括三个月后的店主）看到这条记录时，能立刻分辨"这一晚是人工从回放里补的"和"这一晚是当场签的"。
4. **草稿不算事实**：半截的比分只在本机 `localStorage`，不进服务端；`importing` 的进度只读不写业务数据。
5. **失败不产生值**：所有 4xx/5xx 路径只显示原因，不写 history、不改 `revision`（与 `action()` 现有的回滚语义一致，`ops.js:83-91`）。

### 7.6 服务端字段小结

| 字段 | 复用还是新增 | 出处 |
|---|---|---|
| `history[i].archivedAt` `entrants` `matches` `hidden` | 复用 | 现有 `tournament_new` / `tournament_hide` |
| `history[i].entrants[j].members[0].pid` | **新增（加法）** | `event_backfill`：入参 `entrants[]` 写 `{pid}` 的行按**名册**落库（`pid` + 名册当前名字），只写 `{name}` 的行仍是访客（`pid: null`）。这是第 4 条（house standing）与第 6 条（回填）唯一的连接点：`resultStats(pid)` / `record` / `headToHead` 全按 pid 计数 |
| `history[i].source.{kind,vodId,datasetId,startS,endS,channel,title}` | **新增** | `event_backfill` |
| `history[i].source.humanReviewed` | **新增** | 同上（恒为 `true`，服务端强制校验） |
| `history[i].signOff.at` | **新增** | 同上 |
| `events[].action='event_backfill'` + `vodId` | **新增**（沿用现有审计结构） | 同上 |
| 客户端 `cp-ops-backfill`（草稿） | 新增（本机） | 第 7.1 节 |

入参的两种写法与拒绝规则（服务端强制，拒绝即不落盘、不涨 revision、文件一个字节都不动）：

| 写法 | 结果 |
|---|---|
| `entrants: [{pid: '<player id>'}]` | 落库为该常客；名字取**名册当前值**（请求里另拼的名字不生效）；回合/对手/胜者照常按 entrant id 解析 |
| `entrants: [{name: '<新建的访客名>'}]` | 落库为访客（`pid: null`），不计入任何人的 standing |
| `entrants: [{id, name}]` | 仍是自定义 entrant id（第 7.6 节原有行为，不变） |

| 拒绝 | 何时 |
|---|---|
| `Unknown id` | pid 不在名册里（拼错、已删） |
| `Inactive player` | pid 指向停用的常客：停用的人不能挂到历史夜上（要补录先把状态改回 Active，补完再改回去） |
| `Two entrants name the same regular` | 同一常客被写了两遍（两个 pid 行） |
| `Player name already exists; send the regular as their player id` | 只写名字、而名册里已有同名的人 —— **必须改指 pid**。若放行，这一晚会悄悄变成访客、对谁都不计数，正是第 4 条要防的"账对不上" |

**为什么不自动按名字猜 pid**：猜错会把一晚的成绩记到**别人**头上，比不计数更糟。名字命中名册时服务端拒绝并告诉操作员用 pid；控制台侧（`bfPlayerFor` / `bfEntrants`，用与 R13 搜索同一个 `searchFold`）会先把名字折成 pid 再发出，并在每一行显示 `常客 / 访客` 徽标，让人在**发出之前**就看到这一场算谁的。

---

## 8. 文案改动清单（`words`，`ops.js:4`）

### 8.1 删除（**没有替代**，因为它描述的东西被删了）

| key | 现在 | 为什么删 |
|---|---|---|
| `connected` | `['LOCAL · SAVED','本地 · 已保存']` | 店主第 2 条：顶栏不再显示这个数字；`data.revision` 移到后台系统状态行 |
| `offline` | `['UNAVAILABLE','不可用']` | 被 `connectionLost` 取代（语义更准：不是"不可用"，是"改动保存不了"） |
| `tagline` | `['POOL HALL OPERATIONS','球房运营台']` | 副标题只说了一遍店名已经说过的事 |
| `clock` | `['Shot clock · local timer, not shared','击球计时 · 本机计时，不联动']` | 店主第 3 条 |
| `more` / `moreNav` | `['More','更多']` / `['More screens','更多界面']` | More 面板删除 |
| `phaseRegister` `phaseRack` `phasePlay` `phaseClose` | 四个阶段名 | phase 条删除；阶段名若还需要，用 `.scene` 里的短标签 `sceneRegister` 等（8.2） |
| `playViews` / `playQueue` / `playTables` / `playBracket` | Play 三段名 | playtabs 删除；三段内容不再需要"视图名" |
| `floor` | `['Floor','球房']` | 屏幕退休（`floorScreen()` 并入 `tonightScreen()`） |
| `setup` / `matches` | `['Set up','开赛设置']` / `['Matches','对阵']` | 屏幕退休（内容分别并入"开始今晚"卡与对阵表面板） |
| `standings` | `['House standings','球房排名']` | Records 不再有这一段；表头改用 `houseRecord`（8.2） |
| `timeline` | `['Night log','赛事日志']` | 被 `auditTrail`（8.2）取代 |
| `history` | `['Archived events','已归档赛事']` | 被 `events`（8.2）取代 |

### 8.2 改写

| key | 旧 | 新 EN | 新 中 |
|---|---|---|---|
| `clock` → **`shotTimer`** | `Shot clock · local timer, not shared` | `Shot timer` | `击球计时` |
| `records` | `['Records','战绩档案']` | `Records` | `战绩档案`（**不改**：店主认这个名） |
| `players` | `['Regulars','常客']` | `Regulars` | `常客`（不改） |
| `status` | `['Back room','后台']` | `Back room` | `后台`（不改） |
| `relation` | — | `Tables`（**已存在**：`tables:['Tables','球台数量']` 仍用于"球台数"字段） | 球台数量 |
| `tonightTab` | 现文案 | `Tonight` | `今晚`（用作新 `tonight` 一级项的标签，理由见 1.1） |

`shotTimer` 的**唯一**文案规则：顶栏/球台/手机上只出现 `Shot timer` / `击球计时` 两个词。原来那句解释搬进 `clockNotice`（**已存在**，`ops.js:4`：`The shot clock runs only on this browser and survives refresh…`），它在后台页与钟的 `title` 里，不再占标签位置。

**连带的代码改动（必须一起改，否则共享钟替换不掉旧标签）**：`annotator/clock-sync.js:75-77` 的 `LOCAL_TIMER_LIE = ['Shot clock · local timer, not shared','击球计时 · 本机计时，不联动']` 是"要替换掉的旧标签"白名单，`decorate()`（`clock-sync.js:410-411`）靠它把假标签换成 `Shot clock · shared across devices` / `击球计时 · 多设备同步`。`words.clock` 改名后这里必须同步改成 `['Shot timer','击球计时']`，否则 ops.js 画的标签将**永不**被共享钟替换——这是本次最容易漏的一处。同时登录 `clock-sync.js:390-391` 的语言嗅探（它也按这两个字符串判断页面语言）。

### 8.3 新增

| key | EN | 中 |
|---|---|---|
| `connectionLost` | OFFLINE · edits will not save | 离线 · 改动不会保存 |
| `sceneRegister` / `sceneRack` / `scenePlay` / `sceneClose` | Registered / Racked / Playing / Wrapping up | 报名 / 开台 / 比赛中 / 收尾 |
| `sceneIdle` | Nothing on the tables yet | 还没有赛事 |
| `startNight` / `startNightGo` | Start tonight / Start tonight → | 开始今晚 / 开始今晚 → |
| `startEvent` | Start the event → | 开赛 → |
| `sendNext` | Send next → T{table} | 派下一场 → T{table} |
| `events` | Events | 历史赛事 |
| `auditTrail` | This night's log | 这一晚的流水 |
| `houseRecord` | House record | 球房战绩 |
| `nightSummary` | {players} players · champion {name} | {players} 人 · 冠军 {name} |
| `sourceLine` | Source: Twitch VOD {id} · {range} | 来源：Twitch VOD {id} · {range} |
| `backfill*`（全部） | 见 7.2 表 | 见 7.2 表 |
| `months`（12 条） | January … December | 一月 … 十二月 |
| `noRecord` | — | —（无战绩的破折号，不翻译） |

---

## 9. 逐条映射表（店主 8 条 → 改哪里 / 怎么验收）

| # | 店主原话 | 改哪些函数/区域 | 验收方式 |
|---|---|---|---|
| 1 | 去掉顶栏品牌区，tab 移进顶栏 | `annotator/ops.html` 的 `<header><div class="bar">`（`.brand`→`.hall`，删 `<small id="tagline">`，`<nav id="nav">` 移入 `.bar`）；`ops.js:103` `render()` 删 `#tagline` 赋值、`#nav` 重绘改读 `primaryNav()`；`ops.css:72` 拆 `.bar > nav` 规则、删 `.brand` 样式（`ops.css:80-82`）、删 `[data-tab=vision] .bar` 特例（`ops.css:487-488`） | 截图 1440 顶栏只有一行；断言 `ops.html` 里 `id="tagline"` 不存在、`#nav` 是 `.bar` 的后代；新增测试「顶栏只有一行：`.bar` 的子元素是 `.hall`/`#nav`/`.tools`」 |
| 2 | 去掉 "Local Saved 数字" | `ops.js:103` 删 `$('#connection').textContent = …`；`#connection` 改为 `hidden` 驱动（`reload()` 成功/失败）；`words.connected`/`offline` 删除，新增 `connectionLost`；`data.revision` 移到 `statusScreen()`（`ops.js:192`）的一行 | 断言 `render()` 源码里不含 `data.revision` 的拼接；断离线时 `#connection` 显示 `connectionLost` 双语、在线时 `hidden`；断后台页出现 `revision` |
| 3 | 计时标签就叫 "shot timer" | `ops.js:4` `words.clock` → `words.shotTimer = ['Shot timer','击球计时']`；`clockHTML()`（`ops.js:101`）与 `#strip` 改用新 key；**同步** `annotator/clock-sync.js:75-77` 的 `LOCAL_TIMER_LIE` 与 `clock-sync.js:390-391` 的语言嗅探；`clockNotice` 保留 | 断言 EN/中两语言下页面只出现 `Shot timer`/`击球计时`；断言 `clockSync.LOCAL_TIMER_LIE` 等于新标签；**保留** `test_ops.js:1065` 的"没有任何标签声称是本机计时"；浏览器验证：共享钟接上后标签变 `Shot clock · shared across devices` |
| 4 | 每个球员的 house standing 加到常客 | `ops.js:187` `playersScreen()`（加 `resultStats(p.id)` 的场次/胜负/胜率列、无战绩 `—`）；`ops.js:139` `recordsScreen()` 删 `standings` 段；`ops.js:146` `resultStats()` 保持为唯一算法 | 截图 1440/390 常客表；断言 Records 不再出现 `House standings` 标题且 `class="standings"` 表格不在 Records；断言无战绩行出现 `—` 且**不含** `0%`；断言 `#roster-search` 仍走 `nameMatches`（R13） |
| 5 | Records 只作历史赛事入口，Windows 时间线；Night log 与 Archived events 被取代 | `ops.js:139` `recordsScreen()` 重写为时间线（年/月分组、`<ol class="events">`、展开详情）；`ops.js:111-128` `auditNights()` 改为按 night 过滤的折叠脚注；`ops.js:147` `fmtDate()` 复用；`ops.css` 新增 `.tl-*`（时间线）与月份头样式 | 断言时间线按 `archivedAt` 降序、月份头双语、空态两行且含补录入口；断言展开后含 `results-sheet`/`rename-archived`/`event-hide`/`toggle-hidden` 与审计脚注；断言有签字赛果的项**不出现** `event-delete`；截图 1440 与 390 |
| 6 | 用 Twitch VOD 回填历史赛事 | 新增 `ops.js` 分段「Backfill」（状态机第 7.1 节、渲染函数、`localStorage` 草稿）；复用 `/api/vods/*`；新增服务端动作 `event_backfill`（`operations.py` 的 `_apply` + 审计 `auditActions`（`ops.js:110`）加词条） | 新增测试：「补录五步的状态机与文案双语」「同一 VOD 第二次回填走 `bfSameVod` 而不是新导入」「未确认的场次不能结算（客户端禁用 + 服务端 400）」「`event_backfill` payload 形状与幂等 409」；Python 侧新增一条 `operations` 单测 |
| 7 | 没有分层菜单，要有状态 | 删 `phaseStrip()`（`ops.js:33`）、`playStrip()`（`ops.js:46`）、`playTabs`/`playTab`（`ops.js:39`）、`barTabs`/`barMore`/`moreOpen`（`ops.js:40-41`）、`#tabbar-more`（`ops.css:704`）；新增 `comp()/liveComp()/dirtyComp()` 与 `primaryNav()`；`tonightScreen()`（`ops.js:35`）按 2.3 表条件渲染；`syncRoute()`（`ops.js:71`）删阶段后缀 | 断言页面上不存在 `data-phase`、`data-play`、`data-more` 三种按钮；断言 `#/tonight/play` 等旧 hash 原地 `replace` 成 `#/tonight`；断言状态迁移不产生 `push` 历史条目；断言四个状态的卡集合与 2.3 表一致 |
| 8 | Tables 永远可见；competition dashboard 只在赛事进行中；赛事由 Tables 页按钮发起 | `ops.js:35` `tonightScreen()` 主体改为球台网格常驻；`ops.js:107` `floorScreen()` 的内容并入；`ops.js:102` `screens` 表删 `floor`/`matches` 两个键；新增 `.card--start`（`tournament_setup`）与 `.card--wrap`（`wrapScreen()`，源自 `ops.js:70` `closeScreen()`）；`ops.js:193-199` 的事件委托删 `data-phase`/`data-play`/`data-more` 三条分支 | 断言 `comp()==='registration'` 时 `tonightScreen()` 不含记分板/对阵表；`comp()==='active'` 时含；断言 `[开始今晚]` 走 `tournament_setup`；断言球台卡上的 `[派下一场]` 走 `match_schedule`；截图四状态 × 两宽度 |

---

## 10. 测试改动计划（`tests/test_ops.js`）

现状：2172 行、105 个测试。**预计改写 14–18 条、删除 2 条、新增 9–12 条**，总量大致持平（105 → 112 左右）。以下按"必须改/应改/绝不放宽"三档写。

### 10.1 必须改写（不断言就测不出新设计）

| 行 | 测试 | 为什么必须改 | 改成什么 |
|---|---|---|---|
| `test_ops.js:1824` | routes: every tab has a hash route… | 断言 `#/setup → #/tonight/register`、`#/floor → playTab='tables'`、`#/matches → 'bracket'`，这三个概念全删 | 保留"每个一级 tab 有自己的 hash、一次点击一条 `push`、后退/前进走屏幕"；把三条退休 hash 改为断言"落到 `#/tonight` 且 URL 被 `replace` 成 `#/tonight`"；删掉 `playTab` 相关断言；`[记分]` 按钮不再改路由（记分板常驻） |
| `test_ops.js:1857` | routes: a URL opens its screen… | 同上（`cases` 表里有 4 条退休 hash 与 `#/tonight/play` 断言） | `cases` 缩为一级路由；退休 hash 的期望值全改为 `['tonight','#/tonight']` 且**不带** view 参数 |
| `test_ops.js:1909` | Records is a top-level tab… | 断言 `navTabs.slice(0,5)` 的**精确顺序**（`tonight,records,vision,players,status`）—— 顺序不变，但"Records 在 live night 与 Vision 之间"的说法要改；文案断言保留 | 顺序断言保留（数组没变）；把标题改为「Records 是历史档案的目的地」；新增：`primaryNav()` 在 `needsBackRoom()` 为假时**不含** `status` |
| `test_ops.js:1921` | Records holds house standings, the night log and the archive… | 三段结构被第 5/6 条取代 | 全量重写为「时间线契约」：月份分组、降序、`>${t('events')}</h2>`、`<ol class="events"`、展开后含赛果单/改名/隐藏/审计脚注、有签字赛果无 `event-delete`；另加「Play/Tonight 不再含 `House standings`」 |
| `test_ops.js:1957` | Records empty states… | `emptyStandings`/`emptyNightLog`/`emptyHistory` 三个 key 的去向变了 | 只保留 `emptyHistory`（两行 + 补录入口）；新增"全部隐藏"的空态断言 |
| `test_ops.js:1982` | Tonight is one tab whose phase follows the night… | `nightPhase()` 的三种推断保留，但"一个 tab 一个 phase"的表述与 `navLabel('tonight')` 的 key 变了 | 改为断言 `comp()` 四值与 `tonightScreen()` 的卡集合一致；`navLabel('tonight')` 仍为 `Tonight`/`今晚`（key 换成 `tonightTab`） |
| `test_ops.js:1998` | the phase strip: four phases… | `phaseStrip()` 删除 | **删除**，替换为「`.scene` 是只读进度：没有 `button`、没有 `data-phase`、恰一个 `aria-current`、`role="status"`」 |
| `test_ops.js:2027` | Register holds the night, random pairing… | 报名内容改为"报名中的卡"，`data-phase` 选择器失效 | 保留全部内容断言（报名/配对/前台/在场/guest/开台），选择器从 `[data-phase=register]` 改为 `.card--registration` |
| `test_ops.js:2046` | Rack shows who is here and racks… | Rack 不再是阶段屏幕 | 改为断言"在场事实出现在报名卡里，点一下走 `entrant_absence`"；删"rack 后进 Play"的断言 |
| `test_ops.js:2071` | phase routes: each phase is addressable… | 阶段不再是路由 | **删除**，替换为「旧阶段 hash 全部原地折向 `#/tonight`」 |
| `test_ops.js:2081` | every tab id resolves to a screen | 不变量本身要留，但 `screens` 表删了两个键 | 保留（`navTabs` 没变）；补一句断言：`screens` 不再有 `floor`/`matches` |
| `test_ops.js:2087` | Close is the night's end… | `closeScreen()` 改名/并入 | 保留全部动作断言，函数名换成 `wrapScreen()` |
| `test_ops.js:2112` | ≤750px: the fixed bottom bar carries Tonight, Records, Vision and More | More 删除 | 改为「底栏 = `primaryNav()` 的第二个渲染位置」：4 槽（有需要时 5 槽）、无 `data-more`、仍恰一个 `aria-current="page"` |
| `test_ops.js:2130` | More in the bottom bar opens and closes the panel | More 删除 | **删除** |
| `test_ops.js:2139` | the bottom bar survives Vision… | 保留（这是 Vision 的出口），但 `[data-tab=vision] #tabbar` 一类的选择器要跟着顶栏改动核一次 | 基本保留；若顶栏选择器变了就同步 |
| `test_ops.js:2152` | stage 8: Floor and Matches are not tabs any more… | 断言 `playTab='tables'`、`legacyPlay('#/matches')='bracket'`、`data-action="floor"` 改路由 | 改为「已退休的 floor/matches/setup 都不是屏幕，旧 hash 一律折向 `#/tonight`」；删 `legacyPlay` 断言 |
| `test_ops.js:633` | every shell word has EN and 中 copy | `words` 大改（删 11 个 key、加 ~20 个） | 断言方式不变（逐 key 检查双语），但**必须**把新 key 全列进去；另加「`clock-sync.js` 的 `LOCAL_TIMER_LIE` 与 `words.shotTimer` 一致」 |
| `test_ops.js:1065` / `1120` | clock labels / 共享钟替换本机标签 | 标签字符串变了 | `LOCAL_TIMER_LIE` 的期望值改为 `['Shot timer','击球计时']`；"没有标签声称本机计时"这条**保留并加强**（还要断言 `decorate()` 确实替换成功） |

**Screens 快照类**：`test_ops.js:2084-2085`（`screens.matches()`/`screens.floor()` 仍渲染）随 `screens` 表删除一并删除。

### 10.2 新增（预计 9–12 条）

1. 「顶栏只有一行，tab 是它的子节点」（第 1 条）
2. 「`#connection` 不再是 revision 标语：在线隐藏、离线双语」（第 2 条）
3. 「`shot timer` 一个词：EN/中、`clock-sync.js` 同步、替换成功」（第 3 条）
4. 「常客表有 house standing 列；无战绩是 `—` 不是 `0%`」（第 4 条）
5. 「Records 是 Windows 时间线：分组、排序、展开、空态」（第 5 条）
6. 「补录五步状态机：入口 → 选 → 估算 → 导入 → 标记 → 逐场确认 → 落库」（第 6 条）
7. 「补录的诚实性：未确认不能结算；来源行必须出现；`humanReviewed` 必须为真」（第 6 条 + 7.0）
8. 「同一 VOD 重复回填走复用/409，不重新下载」（第 6 条）
9. 「无第二层菜单：页面上不存在 `data-phase`/`data-play`/`data-more` 三种按钮」（第 7 条）
10. 「状态驱动：`comp()` 四值 → 卡集合，且状态迁移不写历史条目」（第 7 条）
11. 「Tables 常驻；dashboard 只随 `status==='active'` 出现；`[开始今晚]`/`[派下一场]` 的动作」（第 8 条）
12. 「后退/前进仍然走屏幕，且草稿（dirty）仍然否决导航」（第 7 条 + 铁律）

### 10.3 绝对不放宽的不变量（改完必须仍然通过）

| 不变量 | 现有断言 |
|---|---|
| 每个 shell 词都有 EN/中，渲染不出原始 key | `test_ops.js:633` |
| GET 永不写（载入只 `replace`，不 `push`） | `test_ops.js:1824`（`h.visits` 全为 `replace`） |
| dirty/busy 否决导航，含后退/前进，且 URL 被放回 | `test_ops.js:159`、`1882` |
| 键盘可达与焦点不被重绘吞掉 | `test_ops.js:604`、`506` |
| 打印赛果单与复制文字 | `test_ops.js:1463` |
| 无子 tab 导航（Vision 那条现在是通则） | `test_ops.js:142` |
| 宽表只在 `.table-wrap` 里滚，页面永不被撑宽 | `test_ops.js:1711` |
| 签名不可变：只有未签字赛事可删，否则只能隐藏 | `test_ops.js:1526` |
| 改名按当前名读，处处一致（R12） | `test_ops.js:1236` |
| R13 逐词 AND 搜索 | `test_ops.js:536`、`562` |

### 10.4 实现后实际落下来的（2026-10-02，wave B，替代第 11 节那条"估算"）

预算 vs 实际：预计"改写 14–18、删 2、加 9–12"；**实际**改写 8、删 0、加 5（`tests/test_ops.js` 109 → **114 条全绿**），外加 `tests/test_operations.py` 45 → **47 条**（新增两条 pid 链路测试）。10.1 的表里其余行由 console lane 自己的提交改完（路由/阶段/面板那批），本节只记 wave B 的部分：

| 10.2 的条目 | 落在哪里 |
|---|---|
| 1、2、3、9、10、11、12 | console lane 的 `d9e82cc`（stage 8/9 那批测试：顶栏一行、`#connection` 离线双语、`shot timer` 一个名字、无第二层菜单、`comp()` 四态、Tables 常驻 + dashboard 跟随、底栏 5 槽） |
| 4 | 新增「没打过的人读 `0` / `—` / `—`，绝不 `0%`」（`6.2`） |
| 5 | 新增「时间线按月分组、最新在前、展开在原地」（`5.3/5.4`） |
| 6 | 新增「补录是五个由人走的步骤，页面从不假装识别」（`7.1`） |
| 7 | 新增「未逐场确认就写不进去，payload 自己声明 `humanReviewed`」（`7.0/7.5`）+ 409 那条尾巴 |
| 8 | 新增「已下载的区间走复用；写下的常客计入 standing」（`7.3/6.1`） |
| 4+6 的连接点 | `tests/test_operations.py`：`test_backfill_links_a_written_name_to_the_regular_it_names`、`test_backfill_refuses_a_regular_pointer_it_cannot_honour` |

改写的 8 条（都是锚点问题，不是行为回归）：R12 改名、R5 轮空标注、R4 表头 `House rating (manual)`、R1 未签字可删、`.table-wrap` 宽表、Records 面板清单、standing 行跳转、空态文案 —— 全部改成按 `data-event` / `playersScreen()` / `standing-cell` 取锚点。

---

## 11. 没覆盖 / 存疑 / 需要店主拍板（权重最高，按重要度排）

1. **`shot timer` 到底指哪只钟？** 现在页面上有**两只**：`#strip` 的本机计时器（`ops.js:92-101`，`localStorage` `cp-ops-clock`，不联动）和 `clock-sync.js` 的**共享钟**（服务端 `settings.shotClock`，多设备同步，接上后会把前者的标签替换成 `Shot clock · shared across devices`）。第 3 条要求标签只叫 "shot timer"——那共享时钟的 **kicker 文案**要不要也一起砍成 `Shot timer`（于是"本机/共享"的区别只剩状态行 `live · synced` 一行）？我按"只砍 ops.js 那个标签、共享钟的标签保留其诚实措辞"写了规格；**如果店主的意思是两只钟在界面上也只叫一个名字**，`clock-sync.js:390-411` 与 `test_ops.js:1065` 要一起改。
2. **Back room 变成条件项可能过头。** 我把它设计成"没有需要维护的事实时不占导航位"（1.4）。风险：店主可能**习惯**它一直在（现有 5 条测试把它当作常驻）。要不要保留常驻？（保留 = 回到 5 项固定导航；条件项 = 4 项更清爽，但发现问题的入口变隐蔽。）
3. **一级项 `tonight` 的中文名**：我定为 `今晚`（EN `Tonight`），并把店主第 8 条里说的 "Tables" 当作**页面内的球台主体**（`words.tables` 已存在且含义是"球台数量"，不能复用为导航名）。如果店主想把导航写成 `Tables / 球台`，需要一个新的字典 key（`navTables`），我按不加 key 处理。
4. **VOD 回填的"比赛边界"靠人手标。** 本仓库**没有**从视频里找比赛边界的检测器，所以我把第 6 条实现为"人看回放、逐场标起止与赛果"（7.0）。这比自动化慢得多。**要问店主**：这是他能接受的操作方式吗？如果他要"自动找比赛"，那是另一个项目（需要新的 CV 工作），不在本规格范围内。
5. **回填作业是单作业的。** `VodImporter` 明确写着"one workspace root 的单飞作业"（`vod_import.py:168`），所以第二个补录请求会 409 而不是排队（7.3）。如果店主想"一次排三场回放",需要服务端加队列——我按"不做队列"写。
6. **Vision 的入口名字没提。** 店主 8 条没提 Vision。我保留它作为一级项（它已是"无分层"范例），但如果店主的心理模型里它是"后台工具"，它应该挪进 Back room——这会改变导航语义，需要他拍板。
7. **没做的部分（诚实列）**：
   - 没有写任何产品代码（本 lane 只是设计关卡）。
   - 没有真机截图（截图 lane 是另一个 worktree `pool-w-console`，产出 `docs/console-shots.md` + `out/console-before/`）；本文件里的线框图是**手绘 ASCII**，不是实测像素。
   - 没有验证 `/api/vods/*` 的端到端行为（只读了 `vod_import.py` 与 `unified_server.py` 的契约 + 现有 `tests/test_vod_import.py` 的端点名）。
   - 没有测过 `event_backfill`（它还不存在）；payload 形状是设计约定，实现时必须同时写 Python 单测。
   - `.scene` 的具体断点（几个像素开始折叠）、手机底栏 4 槽 vs 5 槽的字号是否还够，需要实现后用截图核定。
   - 没有改 `tests/test_ops.js`；第 10 节的"预计新增/删除"是估算（改写 14–18、删 2、加 9–12），实现时以真实 diff 为准。
   - 没动 `/board/` 与 `/display`（铁律：公开面不动）；`settings.publicBoard` 开关的影响范围只在后台页说明里加一句。

---

## 12. 业主裁决（实现前冻结，2026-10-02）

第 11 节那 6 个问题在开工前定死。实现 lane 按本节执行，**不再自行解释**：

1. **`shot timer` 是唯一的名字**（问题 1）：`ops.js` 本机钟的 kicker 与 `clock-sync.js` 的 `LABELS.en/zh.kicker` **都**改成 `Shot timer` / `击球计时`，`LOCAL_TIMER_LIE` 与之一致；`clock-sync.js:390-411` 的语言嗅探、`test_ops.js:1065/1120` 一起改，并**保留并加强**"没有任何标签声称本机计时"这条不变量。**保留同步状态行**（`live · synced` / `reconnecting…` / `offline…`）——它是状态，不是标签。
2. **Back room 常驻**（问题 2）：`primaryNav()` 保留为函数，但**永远返回全部五项**，不做条件隐藏；`needsBackRoom()` 不实现。理由：店主没有要求条件项，出现/消失的入口是额外的一层意外，不是本次目标。
3. **一级项仍叫 `Tonight` / `今晚`**（问题 3）：不加 `navTables`；Tables 是页面内的主体，不是导航名。
4. **回填的比赛边界靠人手标**（问题 4）：仓库里没有边界检测器，按 7.0 实现"人看回放、逐场标起止与赛果"；界面文案必须诚实（`bfManual`），最终报告里也要写明。**不新建 CV 项目。**
5. **单作业、409 不排队**（问题 5）：`VodImporter` 的单飞语义保留，第二个补录请求 409 + 诚实文案；**不加队列**。
6. **Vision 保持一级项**（问题 6）：不挪进 Back room。

### 12.1 实现期追加的两条裁决（2026-10-02，wave B）

7. **Regulars 行的"点名字"进的是管理视图，不是只读战绩**（§6.1 的实现偏差）：standing 行沿用既有的 `data-action="select-player"`（店主平时改资料的那条路），只读的 `recordView` 由行内 `[个人战绩]` 打开。理由：Regulars 本来就是**管理**名单，把主点击改成只读页会让"改名 / 改评分"多一跳，而只读入口仍在（行内一跳）。`test_ops.js` 里"两跳"的断言（`select-player` → `player-record`）就是这条裁决的固化。
8. **回填入参的 `pid` 是加法，不是替换**（§7.6）：只写 `{name}` 的一律按访客落库（`pid: null`）；这与第 4 条自洽的前提是**控制台先把名字折成 pid**（`bfPlayerFor`，与 R13 搜索同一个 `fold`），服务端只做校验与拒绝，不做猜测。


## 13. Owner round 2 — the bar, the timer, the balls (2026-10-03)

Eight items. The owner's words are the intent; the decision under each is frozen and may not be
reinterpreted by an implementation lane. This section is the contract for the round-2 work.

| # | The owner's words | The frozen decision |
|---|---|---|
| 1 | "when i said table i guess i just meant the shot timer, because that needs to be usable without a match going on too" | The always-available element is the **shot timer**, not the Tables page. It renders and works in every venue state (`idle`, `registration`, `active`, `closed`); no part of it may be gated on `comp()`. The round-1 resident Tables body stays as it is. |
| 2 | "entirely remove the corner pocket and 8 ball branding in the top. only leave the tabs." | `a.hall` — the 8-ball glyph and the `Corner Pocket` wordmark — is deleted from `annotator/ops.html`. Nothing replaces it. |
| 3 | "make 1 ball yellow, 2 ball blue, 3 ball red, 4 ball pink, 5 ball orange, 6 ball green, and 7 ball brown." | Colours come from a **palette by ball number**, not the per-tab hex map `navColors`. 8 is black; 9–15 are the same seven hues drawn as stripes. §13.4. |
| 4 | "make the top bar ball icons more realistic and material." | Each ball is a lit sphere: tinted body, specular highlight, rim and contact shadow, and a printed number plate. §13.4. |
| 5 | "make the first tab the shot timer in large." | The first slot of the bar row **is** the timer, set at clock size with its own controls. §13.2. |
| 6 | "there still is redundant live · synced text in the shot time bar.plz rm" | The `[data-clock-sync]` status line is deleted. Failures still speak. §13.3. |
| 7 | "and in the same bar the shot timer text seems to be strangely vertically aligned.. please fix." | The timer slot is one flex row with centre alignment; the stacked `.kicker` that caused the misalignment is gone. §13.2. |
| 8 | "please use impeccable and improve the UI every where." | The 24-command protocol runs again over the current console and lands a second ledger section. §13.5. |

### 13.1 One bar, one row

`header > .bar` holds three children, in this order:

1. `.timer-slot` — the shot timer (first, large). §13.2.
2. `nav#nav` — the five destinations. Their ball numbers are now **2–6**, because slot 1 is the
   timer: Tonight 2, Records 3, Vision 4, Regulars 5, Back room 6. This is exactly the owner's
   colour list applied to a six-slot row.
3. `.tools` — `#connection` (hidden unless the console is offline), the EN/中 chip group and the
   theme chip group. Unchanged.

The old `nav.clockbar` inside `.tools` and the `#strip` row below the bar are both **deleted**.
`#strip` existed only to hold `clockHTML()` and a second copy of the timer; the timer now has one
home and the header stops growing a second row. `.bar` stays `flex: 1 1 auto` for `#nav`, and the
whole bar keeps `max-width: var(--page-max)` and its `clamp()` side padding.

At `max-width: 750px` the header keeps `.timer-slot` (large, always visible) and `.tools`; `#nav`
is still replaced by the fixed bottom `#tabbar`, whose slots stay text-only and hold destinations
only — the timer is never moved off screen behind a tab.

### 13.2 The timer slot

One flex row, `align-items: center`, no wrap, holding in order:

- `span.ball` — ball 1 (yellow), the row's icon; it carries the running state as a class.
- `strong.clock[data-clock]` — the time, `clamp(30px, 3.4vw, 48px)`, `line-height: 1`,
  `font-variant-numeric: tabular-nums`, in the mono face. This is the "in large".
- `button[data-action="clock-toggle"]` — Start (`▶`) / Pause (`⏸`), text label kept for the
  house style.
- `button[data-action="clock-reset"]` — Reset.
- `.presets` — the four duration chips `20 / 30 / 45 / 60` (`data-action="clock-set"`,
  `data-value`), hidden below 750px so the slot stays one row on a phone.
- `.progress` — the 2px elapsed bar, the full width of the slot, at its bottom edge.

The `.kicker` label is **dropped**: the ball and the digits say what the slot is, and the group's
`aria-label` ("Shot timer / 击球计时") names it for a reader. `.kicker { margin-bottom }` inside a
centre-aligned flex row with a 30–48px `line-height: 1` sibling is what produced the odd vertical
alignment the owner saw; removing the second line removes the cause rather than nudging it.

Behaviour (item 1): the slot renders and its controls work in all four venue states. `clock-toggle`
flips between start and pause, `clock-set` changes the duration and re-renders, `clock-reset`
clears the deadline. Nothing in the slot reads `comp()`.

### 13.3 The status line is gone (item 6)

`clock-sync.js` stops painting a status sentence. The element it wrote into — `[data-clock-sync]` —
is deleted from `clockHTML()`, and `decorate()` writes nothing for the `connecting`, `live`,
`polling` or `offline` states.

What stays: a **failed command** still says so. The slot keeps one `<span class="sync-error" hidden>`
element; `decorate()` shows it (and unhides it) only when there is an error text to show — a failed
`clock-set`/`clock-toggle` is a fact the operator must see, and it is not the redundancy the owner
removed. The reason: the owner removed a *state readout*, not the console's honesty about commands
that did not take effect.

The language sniffer in `clock-sync.js` must stop reading the `.kicker`'s text, because the kicker
no longer exists. `render()` sets `#ops-shell.dataset.lang`; `decorate()` reads that (falling back
to `document.documentElement.lang`, then to the old text sniff) to pick the label set.

### 13.4 The balls (items 3 and 4)

One palette, keyed by ball number, used **wherever a ball is drawn** — the bar's timer slot, the
five nav buttons, entrants and any other numbered chip:

| n | colour | n | colour |
|---|---|---|---|
| 1 | `#f2c14e` yellow | 9 | yellow stripe |
| 2 | `#2f6fd0` blue | 10 | blue stripe |
| 3 | `#c8382f` red | 11 | red stripe |
| 4 | `#e885ad` pink | 12 | pink stripe |
| 5 | `#e07a29` orange | 13 | orange stripe |
| 6 | `#2f8f4e` green | 14 | green stripe |
| 7 | `#8a5a2b` brown | 15 | brown stripe |
| 8 | `#1b1b1b` black | — | — |

Above 15 the number is taken modulo 15 (`(n - 1) % 15 + 1`), which is what the entrant chips do
past a full rack. Numbers are drawn inside a white number plate with dark digits, the way a real
ball prints them.

Material: a lit sphere, not a flat disc. Solid 1–8 are a radial gradient whose light comes from
34% / 30% (upper left) with a darker terminator at the lower right, a small specular dot, an inset
rim line, and a contact shadow under the ball. The 9–15 stripe is the same sphere in white with a
colour band across its middle; the number plate sits on the band, so the band and the plate read
apart at 26px. The existing `--ball*` tokens carry the geometry; the per-number colours come from
the palette above rather than from `navColors`.

### 13.5 Impeccable, round 2 (item 8)

The 24-command protocol from `docs/impeccable-commands.md` runs again over the **current** console,
because the console was rebuilt in wave 10 after the polish campaign and the new surfaces
(one-row bar, timer slot, Records timeline, backfill five-step flow, standing columns) have never
been through it.

- Playbooks: `/tmp/impeccable/.dsh/skills/impeccable/reference/<command>.md` (the clone was emptied
  by tmp cleanup and is re-cloned; the pinned commit is `9d715cc`, so a lane that reads it records
  the commit it actually read).
- The campaign's own instruments are reused instead of new ones: `out/impeccable/{numerals,empties,
  overlay_sweep,contrast,focus,narrow,overlap}.sh` and `serve_fixture.py` from
  `~/projects/pool-impeccable` and `~/projects/pool-impeccable-r1`.
- Deliverable: a second section in `docs/impeccable-ledger.md`, one row per command — what it
  inspected, what it decided, the commit(s) it produced, or the honest reason it was a no-op on
  today's code (a command discharged before the redesign is re-checked, not re-run for show).
- Findings are measured, not vibed: viewport, language, theme, the command that raised it, the
  evidence path, and `file:line`. Accepted findings land as commits; rejected ones are recorded with
  the reason.

## §14 — Round 3: what a blind operator measured (visual 4/5, clarity 3/5, 20 findings)

An independent reviewer ran the shipped round-2 console (`f5c680c`) on a seeded club (live event, 16
entrants, 3 tables in play, 14 regulars, revision 111) across five tabs × 1280×900 and 390×844 ×
EN/中文 × dark/light, plus the public board, with no access to source, docs or git. Verdict:
`visual 4, clarity 3, pass false, issues 20` (`out/impeccable/ratings/round-2/verdict.md`). The
acceptance is 5/5 on both, so round 3 fixes the findings below. **Finding ids are the rater's (F1–F20).**

### 14.1 The header at 1280 (F17, major) — one row, 1024 up
Round 2 fixed the 1440 wrap and never measured 1280, which is where the reviewer sat: at 1280 the
persistent header breaks into **two ragged rows** (121 px tall) — "Back room" wraps inside `#nav`, and
EN/中, the theme chips and the `#backfill-open` word wrap inside `.tools`, while ~500 px of the first
row sits empty. Acceptance, measured at 1024/1152/1280/1440/1920 in EN and 中文, dark and light:
- the header is **one row**, height ≤ 64 px, no element inside it wraps to a second line;
- `#nav button { white-space: nowrap }`; `.tools { flex-wrap: nowrap }`;
- the `20/30/45/60` preset group stays hidden below 1440; `#backfill-open` loses its word below 1440
  (icon + `title` + `aria-label` keep it reachable) or moves into the Back room tab — pick one and
  say which in the ledger;
- nothing is clipped: every control keeps a ≥32 px target and stays keyboard-reachable.

### 14.2 The stage box (F2, major)
At 390 in light theme the Vision stage's empty-state sentence wraps to two lines while the box behind
it is one line tall, so "then freeze it here." lands on the black stage: measured `rgb(102,90,77)` on
`rgb(11,9,7)` = **2.97:1**, with `figure.stage` bounding height 0 px against `.stage-empty` 48 px (a
`<figure>` with no decoded frame has no intrinsic height, and `.stage-empty` is `position:absolute;
inset:0` of that 0-height box). Acceptance at 390 and 1280, EN and 中文, light and dark: the sentence
is entirely inside its own background, **no glyph is drawn on `--stage-bg`**, measured contrast ≥ 4.5:1,
and a stage that holds no frame still has a real height.

### 14.3 The operator's words (F1, blocker as measured)
The Vision workspace never loaded footage on the rating fixture, and the product answered an operator
with a developer instruction: `media not found. The review API is unavailable. Use the project review
server, not a file:// URL.` (and its 中文 twin). Two separate repairs:
- the copy is operator-facing: it says what is true and what to do next, and never names `file://`,
  a "review API" or another machine (`annotator/app.js` notice + the 中文 map + the message regex);
- the **rating fixture serves the review workspace** (§14.9), so the next review judges Vision with
  footage instead of a dead stage.

### 14.4 One concept, one 中文 word (F6 major, F4, F11)
- **F6**: a waiting match shows the chip 「已排台」 ("already placed on a table") beside an enabled
  「安排上台」 ("send to table"), and the same English source "RACKED" is rendered 「开台」 by the stage
  stepper on the same screen. One concept, one word: `scheduled`/`sceneRack`/board text all read
  **「已排定」**; the send button stays 「安排上台」.
- **F4**: the race chip reads 「抢几 5」 while the strip says 「抢5」 — `race` renders 「抢{n}」 everywhere;
  「抢几」 survives only where it is a field label.
- **F11**: a 中文 month heading prints 「十月 OCTOBER」 (both languages at once) — one language per label.

### 14.5 Dead promises (F14 major, F15, F16, F5)
- **F14**: the Rename-event card says "archive this event to start a new one" while "archive" appears
  nowhere else in the DOM. The control exists (`closeCard()`, `annotator/ops.js:404`, reached only via
  the close scene) but an operator standing mid-night cannot find it. The **Back room carries the "End
  of the night" card in every state** — its two buttons disabled with the reason shown when the state
  forbids them (`hasSigned`/entrants rules stay exactly as they are) — and the locked note points there.
  Never name a control the operator cannot reach.
- **F15**: the nav balls 2–6 are unexplained and are not shortcuts (`location.hash` never changes,
  `ops.js` has no key handler). They become real: **`Digit1`–`Digit6`** switch to the six destinations
  (ball 1 = the shot timer's slot 1: start/pause it) **unless focus is in a text field or a modifier is
  held**, with `aria-keyshortcuts` and a `title` naming the key. The counts beside the labels stay.
- **F16**: the timer's leading circled "1" is an unlabelled shot counter — it carries the ball's number
  and a `title`, and never reads as a count.
- **F5**: "BACKFILL FROM A VOD" on the Records row is styled exactly like the neighbouring Expand button
  but is plain text. It is either a real button or it stops looking like one.

### 14.6 Labels with scope, and errors next to their field (F9, F12, F18)
- **F9**: the two "Search names" boxes get a real accessible name stating their scope (roster vs
  records), not just a placeholder.
- **F12**: the system disclaimer ("No simulated observations or fabricated statistics are shown.") leaves
  a single player's panel; it belongs where the system as a whole is described.
- **F18**: "Paste a VOD link or id first" appears above the wizard's own heading, ~300 px from the field
  it is about — the message sits with the field.

### 14.7 Density (F7, F8, F10, F13, F19)
- **F7**: at 390 the bottom bar's five labels get ~44 px each and "Back room" wraps — one line each.
- **F8**: "Manual, validated scoring" is squeezed into ~60 px and wraps mid-word (`Man / al, /
  validated / scoring`) — wrap at word boundaries, or drop the phrase below 480 and keep it in `title`.
- **F10**: "HOUSE RATING (MANUAL)" wraps over three lines while every peer header is one.
- **F13**: an expanded Records event is a ragged left-aligned chip cloud — round, pairing and score
  become columns that line up.
- **F19**: the Backfill wizard uses only the left ~600 px of 1280, keeps "Records" marked current, and
  repeats the entry button's label verbatim as its subtitle.

### 14.8 The board's clock (F20)
Table cards show an unbounded elapsed duration ("11 h 08 min") with no stale signal and no statement of
what it measures: the number is labelled and tells the truth about its age.

### 14.9 The rating fixture (F1's environment half)
One command serves the console, the public board **and the review workspace** against a seeded club, so
the next review can judge Vision with footage. `tests/serve_operations_fixture.py` deliberately
populates no review tools; the workbench fixture is the one that does. Deliver: the exact command, a
seeded club, and a check that proves the workspace loaded (no "unavailable" callout, a real stage).

### 14.10 The evidence rule for this round
Every finding gets, at the viewport where it was measured (1280×900 is now a first-class size):
a before/after pair under `out/console-after/`, a row in `docs/impeccable-ledger.md`, and — where a
number decided it — the measured number. Suites stay green: `node --test tests/test_ops.js`,
`node tests/test_app_timeline.js`, `node tests/test_board.js`, and the python suite. Nothing ships with
a restart: static assets are `no-store` and read from disk per request (`annotator/unified_server.py:2162`).

## 15 Round 4 — the rater's thirty-nine findings, and what this round takes

Round 3's rater (`out/impeccable/ratings/round-3/verdict.md`) returned **visual 4 / clarity 4, 39
issues**, over 56 shots: five console tabs at 1280×900 in dark EN / dark 中文 / light EN / light 中文,
two at 390×844, the public board at both widths, and a real session on the review stage. Coverage
passed — no horizontal overflow at either width (`scrollWidth` 390/390, 1280/1280) and AA contrast in
both themes (6.22:1–16.07:1). Finding 1 (a quoted name reaching the bracket as `&quot;`) is **fixed in
`28fbf96`** with a regression test at the end of `tests/test_ops.js`. This section freezes the decisions
for the other 38 and names the file each one belongs to. Every finding is answered: taken, or rejected
with the reason.

### 15.1 One primary action per row (F2, F4, F5, F12, F26)
- **F2** `Send next →` is one line at the same height as a card whose match is already on a table; the
  action never stretches to 133 px. Acceptance: the two card heights are equal at 1280.
- **F4** the entrant's availability is a **control, not a label**: `<button class="attendance"
  data-action="entrant-presence" aria-pressed>` carrying `t('here')`/`t('away')`, with
  `rackAbsentNote` as its `aria-describedby`. Acceptance: the row is keyboard-operable and calls the
  existing `entrant_absence` action.
- **F5** the Waiting-to-play row keeps **one** action per match (`Send to table`); `Not here` and
  `Forfeit` move onto the match's own side rows instead of a five-button wall. Acceptance: ≤ 2 visible
  buttons per match row at 1280.
- **F12** the same table state appears once: `On a table now` keeps table, sides and `Open its
  scoreboard`, and drops the score line the Scoreboard card already owns.
- **F26** the night-ending action is the primary on its own screen: `Archive & new event` is gold on
  the Back room, while the cosmetic `Save` and the `Backfill` entry are secondary.

### 15.2 One vocabulary (F6, F8, F11, F35, F36, F38)
- **F6** one word per language for "the draw exists": `Racked` / 「已排定」, in the stage strip, the
  chips and the queue.
- **F8** the four stage words are separated and the current one is marked by more than a 6 px dot:
  `Registered · Racked · Playing · Wrapping up`, current stage in `--brass-hi`, with a `title` on the
  jargon.
- **F11** one language per month label.
- **F35/F36** the review workspace's short vocabulary gets its expansion at first use (`title` or
  legend), and `BOX LABEL` / `NEW BOX LABEL` become one label that prints the box's current name.
- **F38** the console and the public board name a round identically — one function decides, so
  `ROUND 2` and `Quarter-finals` never disagree about the same match.

### 15.3 Numbers that mean what they say (F16, F17, F20, F21, F22, F34, F37)
- **F21** the average excludes unrated rows and says so: `Average house rating (manual) · 10 rated`
  = 626, not 447; a 0 rating reads `not rated`.
- **F22** the rating shows its scale (`0–1000, typed by staff`) and `ACTIVE · 2026-04-01` shows a
  legend.
- **F17** a search that filters shows what it left (`2 of 3`) and offers `Clear`.
- **F37/F20** the board separates `Board updated <t>` from `Time on table <d>`; a table past
  `ATTENTION_MS` says `check the table` (round 3's rule stands).
- **F34** the review rail shows where it is (`12 of 54`) or scrolls visibly.
- **F16** the timer ball keeps a `title` that says what it is.

### 15.4 The audit log is for people (F16/#16)
`Other saved changes` renders at body size, one row per change: humanised action, local time, the player
or table it touched, with `v111` behind a `title`; the box has a real `max-height` + visible scrollbar
and states how many rows it holds.

### 15.5 Forms, labels and dead ends (F10, F18, F23, F24, F25, F27, F39)
- **F23** every label is bound (`<label for>` or `aria-label`); the icon-only `+` keeps its aria-label
  and gains a `title`; `Save` is disabled while a required field is empty or blank.
- **F24** `Player record` is a drill-down, so it is styled as one; `STATUS` shows `Newcomer` when the
  data says so.
- **F25** the player modal fits a 900 px viewport (internal scroll), `Enroll face` is reachable at rest,
  and the photo input is a styled `<label>` over a visually hidden file input that names the file.
- **F27** `Lamp glow` shows a numeric readout, `Note` has a placeholder, and `Remove` asks once — an
  in-page confirmation, never `window.confirm`.
- **F10/F18/F39** a sentence that names a card links to it (the End-of-the-night card sentence opens
  `#/backroom`); the Backfill takeover marks itself in the header and shows a step overview; "no recent
  broadcasts for the saved channels" names the channels or moves to the screen that has them.

### 15.6 The review stage is a tool (F28, F29, F30, F31, F32, F33, F34, F36)
- **F28** at 1280 the stage fills its column (≥ 70 % of the source width) and offers `Fit`, `100 %` and
  full screen; today a 1280×720 source is shown at 592×333.
- **F29** label density defaults to `table only`; `all` is a choice and the number drawn is visible.
  Acceptance: no chip overlap at the default density.
- **F30** at 390 the stage bar wraps or scrolls with a visible affordance instead of holding 808 px in
  a 374 px box.
- **F33** no native dialog for unsaved corrections: an in-page notice with `Discard` / `Keep editing`
  that names what is unsaved.
- **F31/F32** the Chinese layer: a cue is 「母球」/「击球」, not 「线索」; model labels are wholly one
  language; the half-width colon goes.
- **F34/F36** as §15.2/§15.3.

### 15.7 Availability and the small screen (F14, F20)
- **F14** the 390 tab bar keeps the counts (`Tonight 11`) that the desktop nav shows.
- **F20** at 390 the round list does not break `ROUND` from its number.

### 15.8 Rejected this round, with the reason
- **F6's visible "Backfill" word at 1024**: round 3 measured 9.6 px of slack in the EN nav at 1024, so
  the word returns at ≥ 1440 only and both icon controls keep `title` + `aria-label`.
- **F13/F19**: taken, but as one-line CSS in lane B rather than markup.
- **F18's fixture name** (`Wednesday 8-Ball Open` dated Friday) is fixture data, not product copy: the
  name is corrected in `tests/console_fixture_state.json` so a reviewer cannot be misled again.
- **B-14** (the board's light theme) stays the owner's product decision from round 2.

### 15.9 Lanes
| Lane | Files | Findings |
| --- | --- | --- |
| A | `annotator/ops.js`, `annotator/ops.html`, `tests/test_ops.js` | §15.1–15.5, §15.7 (markup, strings, tests) |
| B | `annotator/ops.css` | the visual half of A's findings: F2 heights, F7 timer gap, F13 underline, F19 caution colour, F20 mobile wrap, F25 modal box |
| C | `annotator/vision-stage.js`, `annotator/app.css`, `annotator/app.js` | §15.6 — the review stage and its Chinese |
| D | `annotator/board.js`, `annotator/board.css`, `tests/test_board.js`, `tests/console_fixture_state.json` | F37, F38, §15.2's board vocabulary, the fixture rename |

### 15.10 The evidence rule
§14.10 stands, with 1280×900 first-class: a before/after pair under `out/console-after/`, a row in
`docs/impeccable-ledger.md` §"Round 4", the measured number where a number decided it, and green
suites (`node --test tests/test_ops.js`, `node tests/test_app_timeline.js`, `node tests/test_board.js`,
the python suite). Nothing ships with a restart — static assets are `no-store` and read from disk per
request (`annotator/unified_server.py:2162`). The live served-byte check is **blocked** while the console
cannot start: at 14:12 PDT on 2026-10-03 `pool-workbench.service` stopped and `/mnt/ext4dat` (the
Postgres volume's disk) was no longer mounted, so `pool-postgres.service` fails with podman exit 125
(`mkdir /mnt/ext4dat/podman: permission denied`). See `.pm/PROJECT.md`, "Outage".

## §16 — Round 5: the owner's eight items (2026-10-03, after round 3 shipped)

The owner sent eight items (m03423) while round 4 was still in flight. Six were UI changes, one was
already satisfied in the code, and one is a feature that needs its own pass. This section is the
record — including the two items where the honest answer was "already true, and here is the proof".

### 16.1 Item 1 — the Backfill control leaves the shared header

`#backfill-open` lived in `.tools`, which is shared by every tab, so a per-archive action appeared on
the Tonight, Vision, Regulars and Back room screens. It is deleted from `annotator/ops.html`, its
painter is deleted from `render()`, and the three entries that live where the work is stay:

| Entry | Where | Markup |
| --- | --- | --- |
| the button on the archive list | Records, above the list | `btn(t('backfillOpen'),'backfill-open','','primary')` |
| the empty-archive invitation | Records, empty history | `emptyNote('emptyHistory','backfill-open','backfillOpen')` |
| the per-night source badge | Records, on a backfilled night | `data-action="backfill-open"` linking to its VOD |

All three still open the wizard through the one route in the click handler
(`if(a==='backfill-open'){bfOpen();return}`). Round 3's F17 test asserted the *header* control had a
name when its word was hidden below 1440 px; that test is now inverted so it asserts the opposite —
what it protected no longer exists, and the thing that does is asserted in its place.

### 16.2 Item 2 — the browser chrome, which is where the brand actually was

The console's top bar lost its wordmark and 8-ball in round 2 (§13.1), so the branding the owner
still saw was the **tab**: the icon and the page title. Both are fixed.

| Page | Title before | Title after |
| --- | --- | --- |
| `annotator/ops.html` | `Corner Pocket · Operations` | `Operations` |
| `annotator/app.html` | `Corner Pocket · Review workbench` | `Review workbench` |
| `annotator/board.html` | `Corner Pocket · Tonight` | `Tonight` |

`annotator/favicon.svg` was an 8-ball (a black sphere with a white plate and a `8`). It is now the
rail diamond — the same dark rounded square, `#c8a04a` diamond outline and centre dot, no digit. The
three rasters (`favicon-32.png`, `favicon-16.png`, `favicon.ico`) were regenerated from the same
geometry with the repo's PIL, so their sizes and every `<link rel="icon">` reference are unchanged.
The console's own favicon was the only 8-ball left in the product: the board and the workbench link
the same files, and the ball badges in the UI are pool balls, which is the domain, not the brand.

**Open, and asked of the owner:** `annotator/board.html`'s masthead still prints
`<p class="house">Corner Pocket</p>` above the event name. That is the last visible instance of the
club's name — on the public display. It stays until the owner rules, because deleting it removes the
venue's name from the scoreboard it puts on the wall.

### 16.3 Item 3 — the ball map, written down

The mapping the owner asked for was already implemented (`annotator/ops.js`, `ballPalette`) and
already tested; what was missing was the record. It is now a law of the product, and the test asserts
both the palette and this table.

| # | Colour | Hex | Used by |
| --- | --- | --- | --- |
| 1 | yellow | `#f2c14e` | the shot timer tab (and the timer ball on the bar) |
| 2 | blue | `#2f6fd0` | Tournament |
| 3 | red | `#c8382f` | Records |
| 4 | pink | `#e885ad` | Vision |
| 5 | orange | `#e07a29` | Regulars |
| 6 | green | `#2f8f4e` | Back room |
| 7 | brown | `#8a5a2b` | the seventh ball, when a surface needs one |
| 8 | black | `#1b1b1b` | the eighth |
| 9–15 | the same seven hues, striped | — | a second rack |
| 16+ | wraps: `(n-1) mod 15 + 1` | — | a third rack and beyond |

`ballNumber()`, `ballColor()`, `ballStripe()` and `ballHTML()` are the only way any surface draws a
ball, so the map is consistent by construction: the entrant badges in `entrantsCard()` use
`ballHTML(i+1)`, the nav destinations use `ballHTML(i+2)` (the timer took ball 1), and nothing else in
the product draws one (`annotator/board.js` has no ball markup).

### 16.4 Items 4 and 7 — the shot timer is the first tab, and Tonight is Tournament

The timer was always available but it was a *strip* inside the nav's row, and it was not a
destination. Both are now true of it:

- **The host moved inside `<nav id="nav">`** as its first child:
  `<div class="timer-slot" role="group" aria-label="Shot timer / 击球计时" data-clock-host></div>`. The
  class and the `data-clock-host` attribute are unchanged, so the pre-fetch paint, `paintClockSlot()`
  and every existing selector keep working. One definition (`timerSlotHost()`) is used by the shell,
  by `render()` and by the tests.
- **`timerHTML()` now renders a destination button first** — `class="timer-tab"`, `data-tab="clock"`,
  `aria-current` when current — holding ball 1 (decorative, `aria-hidden`) and
  `<span class="timer-tab-label">Shot timer</span>`. The tab's accessible name is therefore "Shot
  timer" / "击球计时", **never a shot count** (round 3's F16, kept and improved).
- **It has a screen of its own** (`clockScreen()`, route `#/clock`): the clock at
  `clamp(64px, 13vw, 176px)`, Start/Pause, Reset, the same four durations, a progress rail, and the
  honest note that the clock runs on this browser only. It reads no match state at all — the comment
  in the code says so, and the test strips the comments and proves it.
- **Shortcut keys keep their meaning**: the timer's toggle is still `Digit1`; the five destinations
  are `Digit2`–`Digit6`, and they are balls **2–6** for exactly that reason.
- **The phone bar** puts the timer slot first as well (six slots, same order).
- **Tonight is now "Tournament"** / 「赛事」. Only the word changed: the route key stays `tonight`, so
  every deep link, the scene strings and the state machine are untouched. One key (`tonightTab`) is
  the single source of the name.

### 16.5 Item 5 — the scorecard's Save

The Scorekeeper's card carried a plain `Save` beside `Sign scorecard`. Save recorded the typed score
without signing; the live +/− scoreboard already records in-play scores, so the pair was two weights
for one job and the wrong one looked primary. Save is deleted; **Sign is the card's only button** (it
keeps its confirm), and the fields keep `required` so the browser still refuses an empty score. The
night-settings Save in the Back room is a different form with a different job and stays.

### 16.6 Item 6 — the redundant sentence was already gone

`live · synced`, `connecting…`, `reconnecting — showing last known` and `offline — showing last known`
were removed in round 2 (§13.3): `statusText()` returns the error text or the empty string, and the
only sentence the clock can still say is a *failure*, in a `span.sync-error` that is hidden when
empty and clears itself after `ERROR_MS = 6000`. The owner was looking at a tab loaded before that
change. Round 5 adds the regression test that makes it stay true: four states assert `''`, the label
map is asserted to hold exactly `kicker`, `failed` and `busy`, and the deleted copy is asserted absent
from the client half.

### 16.7 Item 8 — every Twitch VOD (the pictures shipped; the timeline measured, still open)

**What the live API actually answers** (2026-10-03, `gql.twitch.tv/gql`, two probe queries).

- `videos(first: 20, type: ARCHIVE) { edges { cursor node { … previewThumbnailURL(width: 320,
  height: 180) } } pageInfo { hasNextPage endCursor } }` answers `pageInfo {hasNextPage: false,
  endCursor: null}`, and passing `after: <the edge's own cursor>` — with and without `sort: TIME` —
  returns **the same page**. There is no second page to walk.
- `ttpoolfriday` exposes **three** archived broadcasts: `2890514774` (2026-10-03, 4.57 h),
  `2890340436` (2026-10-03, 4.53 h), `2884327358` (2026-09-26, 3.72 h). `cornerpocket` exposes none.
  So "all Twitch VODs" is three nights — ≈12.8 h of video — and the picker was already listing all
  three, without a single picture.
- A bound still belongs in the code before a busier channel arrives: the day an archive has hundreds
  of nights, the listing needs a page count and a visible progress state rather than a silent
  truncation. That change travels with the timeline half below, where walking further has a purpose.

**What shipped (the pictures)**.

| where | what |
| --- | --- |
| `annotator/twitch_vod_source.py:63` | `_CHANNEL_QUERY` asks for `previewThumbnailURL(width: 320, height: 180)` on every edge |
| `:70` `:180` `:211` | `_THUMB_QUERY`, `_raw_bytes()` (the binary twin of `_raw`: the same no-redirect TLS discipline, capped at 400 kB) and the 64-entry, one-hour `_THUMB_CACHE` |
| `:113` `:116` | `_VOD_THUMB_HOSTS = frozenset({'static-cdn.jtvnw.net'})` and `_validate_thumb()` — https, exact host, no credentials, no port, no fragment, no whitespace |
| `:214` | `vod_thumbnail(id)` → `('image/jpeg', bytes)`, or a sentence a person can read (`Twitch has no such video`) |
| `:253` | the listing validates each node's picture and returns `thumbnail`, or `None` when Twitch sent nothing usable |
| `annotator/vod_import.py:50` `:268` `:273` | `thumb_path()` → `/api/vods/thumb?channel=…&id=…`; `recent()` rows carry `thumb`; `thumbnail()` checks the channel against `saved_channels()` **first** and refuses with 403 otherwise |
| `annotator/unified_server.py:1214` `:2277` | `Backend.vod_thumb()` and the `GET /api/vods/thumb` route, ahead of the generic API fallback |
| `annotator/ops.js` `annotator/ops.css` | the picker's row begins with `img.bf-thumb` (160×90, `object-fit: cover`, the asset's own 16:9; 112×63 under 750 px) |

The proxy is the point rather than a detour: the browser fetches the picture from **this** server, so
Twitch learns nothing about who is looking, and the one pinned host is the only address the fetch may
reach. An id alone is not a licence either — the channel has to be one this club saved.

**Evidence**: `out/r5/shot_picker.py` drives the real console (a private server on `:8170`) from
Records into the Backfill picker and reads each row's `<img>` — its `src`, its `naturalWidth` and its
box. The shot and its numbers are in `docs/console-shots.md` §10. The suites are
`tests/test_twitch_vod_source.py` (31 tests: the pinned host, bytes rather than text, the cache
answering the second call, the refusal that never reaches a fetch) and `tests/test_vod_import.py`
(19 tests: the path shape, the saved-channel check, and the binary route over real HTTP).

**Still open — the timeline half.** "Backfill the **timeline** … based on all Twitch VODs" means a
night per broadcast, and a night is not free: each VOD needs its media fetched and a CV pass over it.
The three broadcasts above are ≈12.8 h of video; a hundred nights is a hundred times that, on a box
whose data disk failed this afternoon. Two shapes are worth the owner's decision, and neither is built:

1. **a night per broadcast, on demand** — the picker's existing per-VOD flow, run once per archive row
   (three nights today, minutes each, bounded, reversible);
2. **the archive as the timeline's backbone** — every broadcast becomes a night automatically, with a
   job queue, a progress state and a stop rule. Its cost is unbounded by construction, so it needs a
   budget before it needs an acceptance rule.

The one thing that must not happen is a timeline row for a night whose numbers nobody computed.

**The ship step, done.** The static half (`ops.js`, `ops.css`) was live the moment the merge landed,
which is why the restart could not be skipped: until it happened the picker asked for a picture the
running server did not serve — an empty framed box, not an error, and not a lie. It happened at
16:48:50 PDT (`systemctl --user restart pool-workbench.service`, `MainPID 396105`, `NRestarts=0`,
`:8130` and `:8132` listening again) and was verified against the production port, not the private
one: `/api/vods/recent` 200 with the three local `thumb` paths, `/api/vods/thumb` 200 `image/jpeg`
`no-store` 19 742 bytes (`ff d8 ff` … `ff d9`), an unsaved channel 403, `/api/board` 200 and the
public board 200. The production console was then read with a browser
(`out/r5-picker/prod-pick-1280-en.png`): **3 pictures, 3 loaded, natural 320×180, drawn 160×90, every
`src` a path on this server, `scrollWidth == innerWidth == 1280`**.

### 16.8 Rejected, deferred and already true

| Item | Decision |
| --- | --- |
| a visible "Backfill" word under 1440 px | rejected: at 1024 px the English nav has ~9.6 px of slack (§15.8), and the button it belonged to is gone |
| the board's masthead `Corner Pocket` | deferred to the owner: it is the venue's name on its public display, not chrome |
| the ball map itself | already implemented and tested; round 5 adds the record above and the per-tab assertion |
| the clock's status sentence | already removed in §13.3; round 5 adds the regression test |

### 16.9 Evidence

`tests/test_ops.js` gained one test per item (items 1, 2, 3, 4, 5, 6) and six existing assertions were
rewritten to the new contract without weakening any of them — the bar test now asserts the timer is
inside the nav rather than beside it, the screens map asserts six screens instead of five, the phone
bar asserts six slots, and the F17 test asserts the header control is gone. Scores on the `r5` tree:
`node --test tests/test_ops.js` 140 pass / 0 fail (was 134), `node tests/test_app_timeline.js` 80 / 0,
`node tests/test_board.js` 16 / 0, `python -m unittest discover -s tests` green.

**The sixth item cost width, and the measurement found it.** `tests/console_shots.py --measure-only`
gained the three widths §14.1's claim needs (`small` 1024×900, `mid` 1152×900, `wide` 1920×1080) and
was run over all six:

| Width | Before (six items) | After the trade | nav | contentTop == header |
| --- | --- | --- | --- | --- |
| 1024 EN | **bar 104 · nav 92 — two rows** | 56 | 44 | 57 ✓ |
| 1024 中 | 56 | 56 | 44 | 57 ✓ |
| 1152 both | 57.2 | 57.2 | 45.2 | 58.2 ✓ |
| 1280 both | 58 | 58 | 46 | 59 ✓ |
| 1440 both | 58 | 58 | 46 | 59 ✓ |
| 1920 both | 58 | 58 | 46 | 59 ✓ |
| 390 both | 48 (+ tabbar 53) | 48 (+ tabbar 53) | 0 (hidden) | 49 ✓ |

The wrap was English-only: `out/r5/probe_bar.py` measured the slot at 311.5 px of a 962.8 px content
box (word 60.5, clock 83.5, start, reset) against a nav needing ~1103 px, so `Back room` (111.4 px)
fell to a second row, while 中文 fitted at 780.9 px of nav. The fix is the media query in
`annotator/ops.css`: below 1152 px the slot gives back the visible word and Reset — both of which the
clock's own screen still offers — and the destinations tighten their gaps and padding. The tab keeps
its name through `aria-label`, asserted in the test, so hiding the word cannot leave it unnamed. The
numbers above are from `out/r5-measure/manifest.json`; the instrument is kept in `out/r5/`.


### 16.10 What the phone found that the width matrix could not

The matrix reads the bar's height, not what is inside it. Two defects survived it and only the
390×844 screenshot plus `out/r5/probe_tabbar.py` exposed them:

1. **the clock left the phone header.** The slot moved inside `#nav`, and the phone query hides
   `#nav` to make room for the fixed bottom bar — measured `nav=none` and a 0×0 slot at 390 in both
   languages. §13.1 calls the clock "the one always-available element", so on the phone the nav now
   stays and only its destinations go: the slot measures 176 px (ball, `0:30`, Start — the word and
   Reset are already gone below 1152), the chips 110, the bar's own padding and gap 36, so 311 px of
   390.
2. **four of six labels were truncated.** Six slots divide 390 px into 62 px cells, and the mono
   uppercase label the bar used needed 80 px for `Tournament` — the shots read "SHOT TIM",
   "TOURNAME", "BACK ROO". The phone bar is the one place the words may not be dropped, so each slot
   now stacks its destination's own ball over its label and the label is set in the body face at
   11 px sentence case, where `Tournament` measures 57.8 px. The bar's 4 px gap and the slot's 4 px
   padding were what pushed it out of its box, so the phone cells take the whole width: 65 px each.

| 390×844 | Before | After |
| --- | --- | --- |
| the header's clock | hidden (`#nav` display none, slot 0×0) | **ball 1 + `0:30` + Start**, slot 176 px |
| the bar's slots | 62 px cells, 4 of 6 labels cut | 65 px cells, **6 of 6 fit** (`Tournament` 57.8 px) |
| the bar's content | the word alone | **the destination's ball + the word**, ball decorative |

The ball on the bar is the same map as §16.3 — 1 yellow for the timer, then 2 blue, 3 red, 4 pink, 5
orange, 6 green — which is what makes the phone bar readable at a glance. Both facts are asserted in
`tests/test_ops.js` ("round 5 / owner item 4 on the phone"), and the pictures are
`out/r5-shots2/390x844/` against the earlier `out/r5-shots/390x844/`.

## §17 — Round 6: Records is the timeline of the archive (2026-10-03 evening)

The order, verbatim: **"make the records the timeline view of all twitch vods. make sure its showing."**
§16.7 had measured the timeline half and left it unbuilt because a night per broadcast costs a media
download and a CV pass. The order settles that: Records itself becomes the archive's timeline. What
followed was not a drawing exercise — the first two measurements changed what "all" means, and the
second one changed the server.

### 17.1 `first:` is the window; there is nothing to paginate

Probed live against `gql.twitch.tv/gql` on 2026-10-03:

| probe | answer |
| --- | --- |
| `videos(first: 5, type: ARCHIVE)` on `eslcs` | 5 edges, `pageInfo {hasNextPage: true, endCursor: null}` |
| the same with `after: "<edge cursor>"` | **0 edges** — the cursor Twitch hands out does not move the page |
| `videos(first: 60)` | 60 edges, same `hasNextPage: true, endCursor: null` |
| `videos(first: 60)` on `ttpoolfriday` | 31 edges, `totalCount 31`, `hasNextPage: false` |

So there is no usable cursor and no page to walk. The only lever is `first:`, whose ceiling Twitch
enforces at 100 (ask for 999 and the query goes out as `first: 100`). `RECENT_LIMIT` therefore went
10 → 60 — a club that streams weekly gets about a year in one read — and the clamp went 10 → 100. When
a window *does* fill, the console says so instead of implying completeness: `recent()` reports
`more: len(vods) >= RECENT_LIMIT`, and the card's note adds "There are more than {n}; this box lists
the newest {n}." Today `more` is `false` for this channel, so the sentence is absent.

### 17.2 The finding that made "all" true: `type: ARCHIVE` was 2 of 31

The first live look at the new card showed **two** rows, not the three §16.7 had listed. The cause was
in the query: it filtered `videos(..., type: ARCHIVE)`, and this channel does not keep its history
there.

| query for `ttpoolfriday` | rows |
| --- | --- |
| `videos(first: 60, type: ARCHIVE)` | **2** — the two most recent broadcasts |
| `videos(first: 60)` (every type) | **31** — the whole published history, newest first |
| `videos(first: 60, type: HIGHLIGHT)` | 29 — including "(Record) 260925" (3 h 43 m), "(Record) 260904" (8 h 33 m), "(Record) 260828", "(Record) 260821", "(record) 260815" and the older full-night records |
| `videos(first: 60, type: UPLOAD)` | 0 |

The club's own night archive — the files literally named `(Record) YYYYMMDD` — is typed **HIGHLIGHT**
by Twitch, and `type: ARCHIVE` hides all of it. The filter is gone; the listing is every video the
channel exposes. `broadcastType` is the field that names a video's kind (`type`, `videoType` and
`isHighlight` all answer `null`), so it travels with every row as `broadcast_type` and the console
prints Twitch's own word for it — `Broadcast` / `Highlight` / `Upload`, `直播回放` / `精选` / `上传` —
falling back to `Recording` / `录像` when the field is absent. That is what makes a 4 h 34 m broadcast
and a 0:00:43 clip distinguishable at a glance beyond their duration, in both languages, without the
console inventing a taxonomy.

### 17.3 What Records is now

`recordsScreen()` opens with one card — `<article class="archive-card" id="archive-card">` — above the
event log it has always shown: **Recorded nights**, the count (`31 videos · 0 built`), a Refresh
button, the note ("Every video this channel exposes, newest first. One becomes a night in the log
below only when you build it. Nothing is inferred from the picture or the title."), and then one
timeline row per video.

A row (`annotator/ops.js` `archiveRow`) is the timeline's own shape — the rail and dot of `§14.2`'s
`.tl-item` — carrying:

- its own picture, `160×90` on a laptop and `112×63` on a phone, fetched from **this server** at
  `/api/vods/thumb?channel=…&id=…` and never from the image CDN (the allowlist is
  `static-cdn.jtvnw.net`, and the channel must be saved before a picture is served at all);
- the title, and under it `dayLabel · duration · kind · channel`;
- exactly one of two actions, and no third state: a night already built links into the log below
  (`Open the night`), anything else hands the row to the same backfill flow the picker uses
  (`Build this night`). The link is the recorded `source.vodId`, never a name or date match.

The five states are written out rather than left blank: reading (`Reading the video list…`), nothing
saved (`No Twitch channel is saved yet…add one on the Back room tab`), a channel with no videos, a
refusal (`The archive could not be read` + the reason + `Try again`), and the list itself.

Two implementation rules came out of the tests:

1. **The card paints itself.** `loadArchiveList()` calls `paintArchive()` — `#archive-card`'s
   `innerHTML` — and never `render()`. The first shape called `render()` and broke ten tests with
   `generated asynchronous activity after the test ended … TypeError: Cannot set properties of
   undefined (setting 'tab')`. It was the right failure: a promise that settles late must not rebuild
   Records under an operator who is reading it (the search box, an open sheet, the scroll).
   `showReview()` is the same shape for the same reason. The trigger lives in `render()`'s tail
   (`if(tab==='records'&&!bf)loadArchiveList();`), so a screen function stays pure.
2. **`bf-pick` had to grow an entrance.** `bfPickVod()` writes through `bf`, and on Records `bf` is
   `null` — a row's "Build this night" would have thrown `TypeError: Cannot set properties of null`.
   The route now seeds the flow from the trunk's own draft (`if(!bf)bf=Object.assign(bfFresh(),
   {saved:readBfDraft()})`) before handing over the broadcast, and `bfPrompt()` cannot misfire from
   there because it requires `saved.datasetId===bf.datasetId`.

Both the archive and the picker now name the kind (`annotator/ops.js` `archiveKind(vod)`), so the
picker's rows read `date · 0:01:06 · Highlight` too: the same list is offered in both places.

### 17.4 Verified

| check | result |
| --- | --- |
| `node --test tests/test_ops.js` | **146 / 0** (five new tests: the archive on Records, the kind word per row, a full window's caveat, the five states, the paint rule, and the build hand-off) |
| `tests/test_twitch_vod_source.py` | 32 / OK (the query no longer filters by type; the window is clamped at 100) |
| `tests/test_vod_import.py` | 21 / OK (`broadcast_type` reaches the row, `more` is true exactly when the window filled) |
| live, private `:8171`, `#/records` at 1280×900 | `31 videos · 0 built`, **31 rows**, 31 pictures (18 decoded at rest; the rest are `loading="lazy"`), natural `320×180`, drawn `160×90`, `scrollWidth 1280 == innerWidth 1280` |
| the same at 390×844 | 31 rows, pictures `112×63`, `scrollWidth 390 == innerWidth 390` |
| **production `:8130`** after `systemctl --user restart pool-workbench.service` (22:43:35 PDT, `MainPID 724298`) | `/api/vods/recent` 200 · `ttpoolfriday` · `more false` · **31 videos** · 31 with pictures · kinds `ARCHIVE`+`HIGHLIGHT`; `/api/vods/thumb` 200 `image/jpeg` 19 742 B (SOI `255 216 255`); served `/ops.js` 150 389 B carrying `kindHighlight` and `archiveMore` |
| the production screen, read out of the live page | `31 videos · 0 built`, 31 rows, `Broadcast`/`Highlight` present, 31 pictures, first three `10/2 Fri · 4:34:15 · Broadcast`, `10/2 Fri · 4:31:33 · Broadcast`, `9/27 Sun · 3:43:17 · Highlight`, no overflow |

### 17.5 Evidence

- Pictures: `out/r6-archive/records-archive-1280-en.png`, `records-archive-1280-mid-en.png` (the
  older nights and the clips, after scrolling), `records-archive-390-en.png`, and the production
  frame `out/r6-archive/prod-records-archive-1280-en.png`.
- The listing itself, with the kinds and the proxy paths, was read twice: in process
  (`channel_recent_vods('ttpoolfriday', 60)` → 31 rows) and over HTTP on both ports.
- Reproduce the screen:
  `AGENT_BROWSER_SESSION=r6b <agent-browser> open 'http://127.0.0.1:8171/#/records'` then
  `set viewport 1280 900`, `eval`, `screenshot`.
- Reproduce the data: `PYTHONPATH=. .venv/bin/python -c "from annotator import twitch_vod_source as t;
  print(len(t.channel_recent_vods('ttpoolfriday', 60)))"` → 31 (needs the network).

## §18 — Round 7: the five things the owner asked for after living with round 5

His message, 2026-10-03 23:29 PDT, in his words: *"1. right now for every human i still see two
tracking boxes why?  2. please keep the shot timer as a separate top bar. dont combine it with shot
timer tab.  3. please remove the text 'The shot timer runs only on this browser and survives refresh.
It does not impose a penalty or update other devices.'  4. please greatly simplify the tournament.
when there is no on going tournament, it should be the darkened registration page with the floating
model for starting a tournament.  5. rm 'Signed results only: a bye is not a match, a forfeit
counts.' from regulars"*

Each item below: what he saw, what the code was doing, what changed, and what the evidence is.

### 18.1 "for every human i still see two tracking boxes why?"

Because the stage painted **two independent layers that both cover people**, and only manual boxes
had ever been deduped against them:

- the tracking layer's rectangles — `annotator/app.js:859`:
  `ov.persons && !playing ? (u?.persons || liveBoxes.filter(b => b.label === 'person'))`, drawn as
  `<g class="u-person">` with a green `stroke="#8fd6a8"`;
- the frame's editable boxes — `annotator/app.js:929`, `const editable = playing || liveFrame ? [] :
  state.boxes`, where `state.boxes` is `displayBoxes()`'s `[...manual, ...model]` and `model` is
  `result.inference.boxes` — i.e. the PersonStage's own `person` boxes.

`isPairedModel()` (`annotator/app.js:135`) only fades a **model** box that matches a **manual** box;
nothing compared the model to the tracking layer, so every tracked person also carried its model
rectangle. The counting had the same split: `auto.persons = persons.length` in the persons layer
(`annotator/app.js:868`) and `auto.persons++` again per model person box (`annotator/app.js:918`), so
the facts line under the stage reported roughly two humans per human.

Measured, production `:8130`, one frozen frame with four people in it:

| | persons | rectangles | model person boxes | pairing |
|---|---|---|---|---|
| before | 4 | 14 | 4 | every tracked rect paired with a model rect at IoU 0.98–0.99 |
| after | 4 | 10 | 0 | the ten left are the balls (`ball · confidence 0.86 · MODEL` ×10) |

The fix is three lines and their comments: `personRects` is computed once and the persons layer uses
it; `coveredByPerson(box)` is `boxTagKind(box) === 'auto' && box.label === 'person' &&
personRects.some(per => boxesMatch({bbox: box.bbox}, {bbox: per.bbox}))`; a covered box is skipped in
the drawing map (`return ''`, so `data-box` — the index the handles, the selection and delete all
address — keeps its meaning) and in the counting loop (`continue`). A model person the tracking layer
**missed** still draws, which is the file's existing rule for disagreements: *"agreement reads as one
clean box, a disagreement as a visible gap"*.

Test: `tests/test_app_timeline.js`, `round 7 / owner item 1: one human on the stage carries one
rectangle, not two` — one `u-person` and one `t-box` (the ball), `drawn.persons === 1`, `data-box="1"`
present and `data-box="0"` gone, index 1 still selectable; a model person the track layer missed still
draws; `overlay.persons = false` returns the two plain boxes. Suite: 81 passed, 0 failed.

### 18.2 The shot timer is its own bar, and ball 1 is its own door

The bar held the timer inside the same `<nav>` as the five destinations, which is what round 5 had
built (ball 1 + the word + the clock + Start/Reset + the presets, then balls 2–6). The owner asked for
the timer *above* the destinations as its own bar, and — his ruling of 2026-10-04, after living with
the first cut — for that bar **not** to double as the timer's tab: *"keep the shot timer as a separate
top bar. dont combine it with shot timer tab."* The two are separate things now:

- **the bar is the instrument**: the clock, Start/Pause, Reset, the four presets and the progress
  rail. It carries no ball, no word and no `data-tab` at all.
- **ball 1 is the door**: `clockNavButton()` renders it as the nav's first item (and the phone bottom
  bar's first slot), named by the word, with `aria-keyshortcuts="Digit1"`, exactly like the five
  destinations beside it.

The shell is two rows:

```html
<div class="bar">
  <div class="clockbar" role="group" aria-label="Shot timer / 击球计时" data-clock-host></div>
  <div class="barrow"><nav id="nav" aria-label="Primary / 主导航"></nav><div class="tools">…</div></div>
</div>
```

`annotator/ops.js` paints it: `render()` no longer prepends `timerSlotHost()` to `#nav` (the host is
markup now), `paintClockSlot()` paints `#ops-shell .clockbar` with `clockHTML()`, and the bottom bar is
six slots again — `tabbarSlot('clock', 1) + primaryNav().map((id, i) => tabbarSlot(id, i + 2))`, so
**the owner's ball map survives whole: 1 is the timer, Tournament 2, Records 3, Vision 4, Regulars 5,
Back room 6, and `Digit1` still reaches the timer.**

Measured, production `:8130` at 1280×900, read out of the live page:

| element | top | height | width | left |
|---|---|---|---|---|
| `.bar` | 0 | 110 | 1280 | 0 |
| `.clockbar` | 6 | 46 | 1219 | 31 |
| `.barrow` | 60 | 44 | 1219 | 31 |
| `#nav` (six items) | 60 | 44 | 807 | 31 |
| `.tools` | 64 | 36 | 169 | 1080 |

`document.scrollWidth` 1280 = the viewport, and the four presets are back at every width from 751 up —
round 5 had hidden them below 1440 as the price of one row, and that trade is now retired (it is still
recorded in §16.9 as the measurement that produced it). The nav is also one row at 1024 (measured 665
px inside a 1000 px row), which round 5 could not do while the clock sat inside it.

At 390×844 the header keeps the clock, Start and Reset and drops only the presets; `#nav` is
`display: none` and the bottom bar carries all six, ball 1 included. Cells are 390/6 = 65 px, and the
labels measure 50.1 px ("Shot timer") / 57.8 / 39.5 / 29.3 / 41.8 / 50.9, so nothing is clipped and the
bar's own `scrollWidth` equals its 390 px box.

### 18.3 The sentence is gone

*"The shot timer runs only on this browser and survives refresh. It does not impose a penalty or
update other devices."* lived in two places: the clock screen's `<p class="muted">` and the Back
room's maintainers table row `[t('shotTimer'), t('clockNotice')]`. Both are removed and the key
`clockNotice` is deleted from `words` — the test asserts `t('clockNotice') === 'clockNotice'` and 0
occurrences in the source, so the sentence cannot creep back in.

### 18.4 The tournament's first run is a dialog over the registration page

Before, a club with no event saw a dashed "First night? Three steps to the first break" tutorial, a
four-field "Start tonight" form, a `Save` button and a second "Start tonight →" button — and the
registration desk was hidden until that button was pressed.

Now `tonightState()`'s `idle` venue renders `idleStart()`:

- **no event and no name** → the registration page (`setupScreen('desk')`, which keeps the tables
  resident) inside `<div class="idle-registration" aria-hidden="true" inert>` — `opacity: .3`,
  `filter: saturate(.45)`, `pointer-events: none` — with `startModal(false)` floating over it: a
  `role="dialog" aria-modal="true"` card titled "Start tonight", the honest note *"Name the night and
  start. The draw sends matches to free tables; nothing is inferred."*, the four fields and **one**
  brass primary. There is no Close button on the first run: the honest choice is to name it.
- **named, or drawn** → the registration page itself, with a quiet "Event settings" door
  (`data-action="open-setup"`) that opens the same dialog closeable; its primary says `Save` because
  that is what it does.
- The four-field block left the page; the "The night" card is now a summary — the night's own name
  once it has one, then `Singles · Race to 1 · 2 Tables` — and the draw (`Start the event →`,
  `data-action="tournament-start"`) is the page's only primary.

Deleted with it: `firstRun()` (five `words` keys retired), `renameCard()` (the rename lives in the
dialog, still audited as `tournament_rename`), the `start-night` and `open-desk` routes and the
`deskOpen` flag (replaced by `setupOpen`, which only records "the operator opened the editor"), the
dead `rename-form` submit branch, and the three buttons that had pointed at `open-desk` (they now go
to the tab itself).

The dialog's predicate is deliberately *not* `!T.id`: **the server mints no id on `tournament_setup`
— only the draw (`tournament_start`) does.** Keying the dialog on the id alone put it back over an
inert page the moment the operator named the night, which locked them out of the desk; the browser
pass caught it, and `idleStart()` now asks `!T.id && !String(T.name || '').trim()`, with the test
*"naming the night is enough to get past the dialog, even though the draw is what mints the event
id"* pinning it.

### 18.5 The "Signed results only" sentence is gone

It appeared three times — the event table's panel (`tonightPanel()`), the top of the standing
(`playersScreen()`) and the queue's side panel (`queueScreen()`) — and now appears none: the three
renderings and the `words` key are removed, and the standing test asserts the key is retired
(`t('signedOnly') === 'signedOnly'`).

### 18.6 What the verification found that the suites could not

- The dead end above (the dialog returning after a successful save) — found by driving the real flow
  in a browser.
- The door-opened editor promised "Start tonight →" although its submit only saves; the label now
  follows the same predicate as the dialog itself.
- **The review fixture does not persist writes.** `tests/serve_workbench_fixture.py` accepted
  `POST /api/operations` with 200 and advanced its in-memory revision, while its `--state` file stayed
  at the old revision — so a write path can only be proven against the real server
  (`annotator/unified_server.py`), which needs the console HTML reachable, i.e. `<root>/annotator/`
  (a bare `--root /tmp/…` answers `GET /` with 404 `media not found`).

### 18.7 Evidence

- Pictures: `out/r7/after-vision-one-box-1280.png` (item 1), `out/r7/after-tonight-idle-dialog-1280.png`
  (item 4, the first run), `out/r7/after-tonight-registration-1280.png` (after naming: the page, the
  desk, the draw), `out/r7/after-tonight-settings-dialog-1280.png` (the door: `Save` + `Close`),
  `out/r7/after-phone-bar-390.png`, `out/r7/after-phone-tonight-390.png`,
  `out/r7/after-phone-start-dialog-390.png`, and the "before" frame
  `out/r7/before-tonight-idle-1280.png`.
- Suites: `node --test tests/test_ops.js` 147 / 0, `node tests/test_app_timeline.js` 81 / 0,
  `node tests/test_board.js` 16 / 0.
- Reproduce: `AGENT_BROWSER_SESSION=r7 <agent-browser> open
  'http://127.0.0.1:8130/?r7=2#/tonight'`, `set viewport 1280 900`, `eval`, `screenshot` — the
  console is served from disk, so round 7 needed no service restart.

## §19 — Round 8: the bar under the destinations, ivory balls in both schemes, and a Vision tab that is only the stream (2026-10-04)

The owner worked a night on the round-7 build and sent four items. Three are here; the second
(automatic VOD download) is engine work and lands separately.

### 19.1 Item 1 — the shot timer bar sits under the tab bar, and hides itself on the timer's own tab

Round 7 gave the timer its own row and left it as the header's **first** row, above the
destinations. The owner asked for the other order, and for the bar to disappear while the big
timer screen is open — it would otherwise be a second, smaller copy of the screen underneath it.

- `annotator/ops.html`: the two rows of the header swap. `.barrow` (the five destinations plus the
  language and scheme chips) comes first, `<div class="clockbar" role="group" aria-label="Shot
  timer / 击球计时" data-clock-host>` second. The host element stays in the document on every tab.
- `annotator/ops.css`: `#ops-shell[data-tab=clock] .clockbar{display:none}`. Hiding is CSS, not a
  DOM removal, for one reason: `annotator/clock-sync.js` holds a handle on that host and every
  other tab has to keep repainting it. The shell sets `data-tab` in `render()` already.
- The phone stack follows the same order from the bottom: `--tabbar-h:52px` and
  `--clockbar-h:calc(48px + env(safe-area-inset-bottom))` sit on `#ops-shell`, the tab bar is
  `position:fixed; bottom:var(--clockbar-h)`, the bar is `bottom:0`, and every offset that used to
  add `--tabbar-h` alone now adds both (`main`, `#message`, `.vs-sheettabs`, `.vs-strip`,
  `.vs-rail`, `.vs-inspector`). `[data-tab=clock]` sets `--clockbar-h:0px`, so the stack closes up
  on the timer's own tab instead of leaving a hole where the bar was.

Measured on `127.0.0.1:8130` after a hard load (1280×900, dark): `#nav` top 6, bottom 50, height
44; `.clockbar` top 58, bottom 104, height 46; the header row 0–111. Bar contents
`0:45 Start Reset 20 30 45 60`; destinations `1 Shot timer · 2 Tournament 0 · 3 Records · 4 Vision
· 5 Regulars 8 · 6 Back room`. At 390×844: `.bar` top 0 height 48, `#tabbar` top 735 height 61,
`.clockbar` top 796 height 48 — the bar's bottom edge is the viewport's, and `scrollWidth` is 390
of 390 in both schemes.

### 19.2 Item 4 — the ball faces keep an ivory base in both colour schemes

The console's light scheme redefines no `--ball*` token at all, so before this round the six
destination balls were literally the same pixels in dark and light: ball 1 `rgb(242,193,78)`, ball
2 `rgb(47,111,208)`, sitting on a plate of `rgb(247,243,235)`. The striped sphere
(`.ball[data-stripe="1"]`) already painted an ivory base with the hue riding the band; the
selector list now includes the tab-bar balls:

```css
#ops-shell .ball[data-stripe="1"],#ops-shell #nav .ball,#ops-shell #tabbar .ball{background-color:var(--ball-face);…}
```

Everywhere else in the console a ball keeps its solid face. Verified live: all six `#nav .ball`
bases read `rgb(247,243,235)`, with the 3-stop gradient present on balls 2–6.

**The bug this exposed.** Ball 1 in the destination row rendered with **no band**. `clockNavButton()`
composed its face with `ballHTML(1).replace('<span class="ball"','<span aria-hidden="true"
class="ball')` — the replacement dropped the class attribute's closing quote, so the browser parsed
`<span aria-hidden="true" class="ball style="--ball-c:#f2c14e"="">`: the `style` attribute was
swallowed into the class list, `--ball-c` never landed, and `var(--ball-c)` with no fallback
invalidated the whole `background-image`. The old gold default (`--ball` `#cfa72b`) had been hiding
it since round 7b — the base only became visible when it turned white. The replacement now ends
with the quote, the function carries a comment naming the trap, and `tests/test_ops.js` asserts the
exact composed attribute pair (`aria-hidden="true" class="ball"` **and**
`class="ball" style="--ball-c:#f2c14e"`).

### 19.3 Item 3 — the Vision tab is the live stream; a recorded night is opened from its Records row

Two surfaces used to share one tab: the live panel and the recorded workbench, with the source
chips choosing between them. They are now separated by intent.

- **The Vision tab** (`#/vision`) is the live stream. With nothing running it paints a panel
  (`livePanelScreen()`): `Live stream`, the status line (`idle · Frame age: — ms · Dropped: 0`),
  one chip per saved channel, Start/Stop, the table/person/ball detectors, and the sentence that
  says where recorded nights live. The moment frames arrive it becomes the live workbench.
- **A recorded night** is opened from its row on Records: `Vision` beside `Open the night` on a
  built night's row, `openReview(id)`, and the deep link `#/records/review/<night id>`. That screen
  heads itself with the night's own name, says `footage · the configured datasets · broadcast
  <vod id>`, offers the way back, and hosts the workbench inside `#vs-frame`.
- **The adapter obeys the tab.** `attachSurface()` passes `liveOnly:()=>!reviewId&&tab==='vision'`.
  With that flag `chipsHTML()` withholds the dataset chips, and `sourcePanelHTML()` drops the
  broadcast list, the VOD-replay block and the saved-VOD rows (their block carries
  `vs-live-hidden`). On the live tab the strip keeps Freeze, Play and the facts line — they act on
  the live frame, and the inspector's "run inference on this frozen frame" is a live action — and
  loses the frame index, the two step buttons and the scrubber, which have nothing to step through.
  The recorded review keeps the whole strip.
- **Who hosts the workbench** is one predicate: `reviewHosted()` = a night is open, or the live tab
  is running. Both `showReview()`'s mount/activate decision and `#main`'s `short` class read it, so
  an idle live tab can never show a leftover recorded picture underneath the panel.

**The honest limit.** The recorded review steps through the datasets the server is configured with
(`vod30`, `highlight`); frames extracted per broadcast are not built yet. The screen says so, and
names the broadcast id so the operator knows which night they came from. A dataset per broadcast is
the still-open "a night per broadcast" work.

### 19.4 What the browser pass caught that no suite would have

Two defects, both found by driving the fixture and fixed before the round closed:

1. The review head printed **TBD**. `nightName(night,eid)` names an *entrant* — called with only a
   night it returns `t('tbd')`. The head now uses the app's convention for a night's own name,
   `night.name||t('unnamed')`.
2. The live panel leaked the previously mounted recorded workbench below it: the host's visibility
   was `tab==='vision'||!!reviewId`, which is true on an idle live tab. Fixed by `reviewHosted()`.

A third, quieter one came out of a dictionary check: the console's `words` literal had **two**
`reviewNote` entries, so the earlier definition was silently overridden (the key had no consumer —
that was the only reason nobody saw it). The stale entry is gone, and a test now parses the literal
and fails on any duplicate key.

### 19.5 Evidence

- Suites: `tests/test_ops.js` **151 pass / 0 fail** (four new blocks: the live panel in EN and 中,
  the route and the review screen, the adapter's live-only flag, and the dictionary guard),
  `tests/test_app_timeline.js` 81 / 0, `tests/test_board.js` 16 / 0.
- End to end on `tests/serve_workbench_fixture.py` (`:8180`, state built from the round-7 fixture
  with a saved channel and one built night linked to vod `2890514774`): 31 VOD rows with 1 built,
  `Vision` opens `#/records/review/ea2d2b2abf5446db96dbdade32783adf`, the review mounts inside
  `#vs-frame`, the deep link survives a reload, the live tab shows the panel with zero dataset
  chips and a hidden host, `POST /api/live {action:'start',source:{kind:'dataset',dataset:'vod30'}}`
  turns the same tab into the live workbench (0 dataset chips, the dataset block `display:none`,
  `#vs-live-status` `running · frame age 28 ms · receive-to-result 6 ms`), and stopping the stream
  brings the panel back.
- Screenshots and the reproduce recipe: `docs/console-shots.md` §13.

## §20 — Round 8, owner item 2: the console fetches the broadcasts it is missing (2026-10-04)

The owner's words (m05209): *"please make it automatically download all vods."* Round 8 ships the engine
(§20.1), the one line on Records that reports it (§20.2), and one decision that is still the owner's
(§20.3). Items 1, 3 and 4 of the same work order are §19.

### 20.1 The engine: a beat, a queue, and the same import path

`annotator/vod_import.py` (+324/-13) and `annotator/unified_server.py` (+22/-3) gain no new dependency and
no new download code: the worker calls the existing `start()`, so range, provenance and the library entry
are the ones the manual Import button already produced.

- `AUTO_INTERVAL_S = 900`, `AUTO_KEEP = 10`, `AUTO_MAX_SECONDS = 3600` (`annotator/vod_import.py:54-56`).
- `_channel_vods(self, channel, force=False)` (`annotator/vod_import.py:274`) is the listing extracted out of
  `recent()`, whose 180 s TTL is untouched. `scan()` (`annotator/vod_import.py:781`) forces a fresh listing and
  diffs it against the library: every missing broadcast is queued, newest first, at most `RECENT_LIMIT = 60`
  per channel.
- One drain thread (`_auto_run` `annotator/vod_import.py:663`, `_auto_drain` `:727`) takes one item at a time and
  checks `_disk(0)` — the 2 GB reserve — before each; a refusal is written into that item's `skipped` and the
  queue continues. The sentence is the existing one:
  `Not enough free disk space: this import needs 2.0 GB (about 0.0 GB estimated x 1.2 + 2 GB reserve) and 1.0 GB is free. Import a shorter range or free some space first.`
- **Nothing in the new code deletes anything.** `unlink|rmtree|os.remove|delete(` occurs 0 times in the added
  lines; `close()` (`annotator/vod_import.py:561`) only pushes waiting items back to the queue head.
- Triggers: `main()` spawns `threading.Thread(target=arm_auto, name="vod-auto-arm", daemon=True)`
  (`annotator/unified_server.py`), which calls `auto({"action": "on"})` inside a try/except that only prints
  `VOD auto download not armed: {exc}` — the queue can never stop the server. A 900 s rescan thread keeps the
  beat, and `GET /api/vods/queue` arms it too — but **never turns auto back on**: an operator's `off` stands.
- One switch: `POST /api/vods/auto {"action": "on"|"off"|"scan", "seconds": 1..3600}`. `auto()` rejects
  anything else (`unsupported auto option: …`, `action must be "on", "off" or "scan"`, a bool is not a
  `seconds`). While a drain runs, a manual Import answers 409, so the two paths cannot race for ffmpeg.
- Nothing durable: `seconds`, `off` and the queue itself live in memory; the next scan rebuilds the queue
  from the library.

### 20.2 The one line on Records

The archive card's head carries `#auto-line` under its note (`annotator/ops.js`, `annotator/ops.css`):

```
Automatic download · running · 29 queued · 0 done · now 2890340436 · 1 skipped   [Pause]
Automatic download · paused  · 29 queued · 0 done · now 2890340436 · 1 skipped   [Resume]
自动下载 · 运行中 · 队列 29 · 已完成 0 · 正在 2890340436 · 跳过 1                     [暂停]
```

One button (`data-action="auto-toggle"`) POSTs the opposite of the state it was drawn from. The line reads
`/api/vods/queue` when Records becomes the screen and when Refresh is pressed — never on a timer: polling the
console must not become Twitch traffic. An unreadable queue degrades to one sentence with `Try again`
(`The download queue could not be read: …`); the key shape of the answer is
`{enabled, seconds, last_scan, queued[], current{id,channel,title,length_s,state,error}|null, done[], skipped[], error}`.

### 20.3 What a restart does — the owner's decision

This is the honest catch. Arming happens at startup, so **restarting the service starts backfilling every
missing broadcast by itself** — up to 60 per channel, stopped only by the 2 GB disk reserve. Measured on the
rating fixture seconds after a restart with this code: `enabled: true`, `queued: 30`,
`current: {id: "2890514774", channel: "ttpoolfriday", state: "importing"}`. On a 4.5 h broadcast that is
gigabytes before anybody looks. `pool-workbench.service` has **not** been restarted: production still runs the
previous python, and the line there reads `The download queue could not be read: unknown dataset` with its
`Try again` (measured) until the restart. Turning it `off` first, or lowering `seconds`, is the owner's call —
this is the one item of the four that changes what the machine does on its own.

### 20.4 Evidence

- **Suites**: `discover -p 'test_vod_import.py'` → Ran 32 / OK; `-p 'test_twitch_vod_source.py'` → Ran 32 / OK;
  the full `discover -s tests -p 'test_*.py'` → OK (skipped=48); `node --test tests/test_ops.js` → 152 pass /
  0 fail; `node tests/test_app_timeline.js` → 81 passed; `node --test tests/test_board.js` → 16 pass.
- **The engine, offline** (`/tmp/auto_queue_harness.py`, re-run by me): three ids enqueued and drained in
  order, index and media agreeing, one Twitch call; the disk-refused case lands both items in `skipped` with
  the sentence above and creates no index or media directory; a Twitch 500 fills the item's `error` and leaves
  the job `idle`.
- **The console, in a browser** on the fixture: the line and the button above, the round trip
  `Resume → running · 29 queued · now 2890340436 → Pause → paused`, no horizontal overflow at 1280
  (`out/r8/item2-auto-line-running-1280.png`, `out/r8/item2-auto-line-paused-1280.png`).
- **Audit of the delegate's diff** (I re-checked, not took on report): `+324/-13`, `+22/-3`, `+223/-0`; the 13
  removals are exactly the `recent()` extraction and three route-tuple/docstring lines; no new imports; 0
  destructive calls; the guards above present.

## §21 — Round 9: the owner's ten items (2026-10-04)

The owner's words (m05946) are the work order, and §21.1 answers each one. Nine of the ten are changes to
`annotator/ops.js` and `annotator/ops.css`; the tenth — *"use impeccable skills all throughout"* — is the
process, whose record is `docs/impeccable-ledger.md`. **No python changed in this round.**

### 21.1 The ten items

| # | the owner's words | what shipped |
|---|---|---|
| 1 | "rearrange and set the spacing for shot timer tab." | `clockScreen()` now renders heading → `.timer-face` → `.timer-progress` (directly under the face, `role="progressbar"` with `aria-valuenow`) → `.timer-controls` last; `.timer-card` is an explicit grid (`display:grid; gap:var(--sp-3); padding:var(--sp-5)`), Start is a fixed 132 px and every control a 44 px target, with a 750 px variant. |
| 2 | "rm the text 'RegisteredRackedPlayingWrapping up' from tournament page." | The `.scene-track` is gone from `scene()`, and with it `sceneStep()`, `SCENE_STEPS`, `SCENE_KEYS`, the four roots (`sceneRegister/sceneRack/scenePlay/sceneClose`) and the five `.scene-track`/`.scene-node` CSS rules. |
| 3 | "rm Guests tonight, Tables, Event table, Scorekeeper from the tournament page." | `guestsTonight`, `tablesGrid`, `tablesArea` (the "Event table" and "Scorekeeper" cards), `tableCard`, `nextReady`, `registerScreen` and the tile-based `floorScreen`/`tonightPanel` are deleted. `tonightScreen()` is the scoreboard + `playScreen()` + `nightCard()` (+ `wrapScreen()`/`bracketScreen()` when the night is complete), and the idle path uses `setupScreen()`. |
| 4 | "combine the dropdown for selecting regular. only show name box when selecting guest. use custom dropdown." | §21.2. |
| 5 | "please make the tab bar icons not striped balls. 1-7 are not striped." | The destination balls are solid: `ballStripe = n => ballNumber(n) > 8 ? 1 : 0`, so only 9–15 band, and the ivory `#ops-shell .ball i` number plate is theme-independent — which DESIGN.md's token table already fixes (`ball-face: "#f7f3eb"` in both schemes). The round-8 rule `#ops-shell .ball[data-stripe="1"],#ops-shell #nav .ball,#ops-shell #tabbar .ball{…}` painted a band over every destination; the selector is now `#ops-shell .ball[data-stripe="1"]` alone. |
| 6 | "rm Not built yet and 'Build this night' from the records page. each VOD should be its own card and each day needs to be horizontally stacked." | §21.3. Reading of "horizontally stacked": one day = one section whose VOD cards run horizontally inside it (`.tl-vods{overflow-x:auto}`), the days themselves stacking down the page. The other reading — day *columns* side by side — is one CSS change away; it is written here so the choice is visible rather than implied. |
| 7 | "make the date more visible in the timeline." | The day head is `h3.tl-date` in the display face at `--fs-xl` with `.tl-day-count` beside it (`1 video` / `2 videos`, 中文 `1 个视频` / `2 个视频`); the old 11 px muted head and the "unbuilt" section above it are gone. |
| 8 | "make every VOD card clickable by default. it shouldnt require 'building' it outside the unified scrubber." | §21.3: the card *is* the button, and the review screen for a bare VOD carries the import action itself. |
| 9 | "improve the design of the regulars tab." | `rosterSummary()` (four `.roster-stat` cells: regulars, active, average **over rated regulars only** with `rosterRatingBase`'s note, recorded results) replaces the tile hero; the `+` is `btn(t('newPlayer'),'open-add-player')`; the filters are Everyone/Active/Visitor/Inactive with counts; each row is a two-line card (`.badge` rank, `.standing-name` + `.standing-record`, `.standing-rating` with the value — a dash when nothing is rated — and its own label), and `.standing-head`/`.standing-cell` are deleted from both files. |
| 10 | "use impeccable skills all throughout." | `impeccable context` at SetUp, the refine passes during the work, `impeccable detect --json annotator/ops.js annotator/ops.css` at the end, and the findings row in `docs/impeccable-ledger.md`. |

### 21.2 Item 4: one custom picker per desk slot

`setupScreen()` renders one `deskSlot(i)` per slot — `i` is 0 for singles, 0 and 1 for doubles. The picker
replaces the old `<select>` + always-visible name field: a `.pick-btn` reporting the choice, a `.pick-panel`
holding `.pick-search`, a `.pick-count` and one `.pick-row[data-id][data-name]` per **free** regular, with the
Guest row always first and never hidden.

- `deskFree()` drops regulars already seated or already picked in the other slot (doubles); `deskFilter(field)`
  filters the rows in the DOM by `nameMatches` and updates the count from the panel's `data-total`.
- The `guestName` field is rendered **only** when nothing is picked — the box exists for a guest and for nobody
  else, which is the owner's second sentence.
- Clicks: a row writes `deskPick[slot] = id || ''`, clears the guest draft when a regular was picked, and
  closes the panel; a click anywhere outside `#entrant-form` closes it, and so does `Escape`. The three state
  objects (`deskPick`, `deskOpen`, `deskDraft`) are reset after `entrant_add` succeeds. The chosen pid travels
  in a hidden `input[name=pid{i}]`.

**The round trip, on an isolated root** (`/tmp/r9-root`: `<root>/annotator` symlinked to the repo's, its own
byte-identical copy of the production state; `annotator/unified_server.py --port 8142 --root /tmp/r9-root`):
clicking Wanwan's row makes the button read `Wanwan · 0 ▾`, puts
`a3c749f3e6b744cbab1a6010bf8cc1c1` in `input[name=pid0]`, removes the guest field and closes the panel;
submitting then makes the nav read `Regulars 7` (Wanwan left the free pool) and `Tournament 1` with the toast
`Saved.`. `/tmp/r9-root/out/corner-pocket/state.json` moved md5 `d68b65095cb4e5deb90f260c04d8ba83` →
`c5a3a6484474d09bd7a1c7fd087b1c7f`, revision 12 → 13, and the new entrant `88fa0762d0544de987318aae2f8b38a6`
names that member. Production's own `out/corner-pocket/state.json` is still `d68b65095cb4e5deb90f260c04d8ba83`.

### 21.3 Items 6, 7 and 8: Records is a timeline of days, and the card is the button

`archiveTimeline()` sorts the VODs and emits one `.tl-day` section per local calendar day — the sort makes
equal days neighbours, so a single pass groups them. A section is `.tl-day-head` (`h3.tl-date` in the display
face at `--fs-xl`, the full date via `dayFull()`, `.tl-day-count` beside it) followed by `.tl-vods` and its
cards. The page's old "unbuilt" section and its **Build this night** button are deleted, along with the words
`archiveUnbuilt`, `archiveBuild`, `archiveVision` and `archiveOpen`.

`archiveRow(vod, night)` renders the whole card as one
`<button class="tl-vod" data-action="tl-review" data-id="<vod id>">`: a 16:9 thumb, a two-line clamped title,
`clockLabel · hms · archiveKind` in the meta line (`23:07 · 4:34:15 · Broadcast`), and the small
`archiveBuilt` mark on a card whose night already exists. Clicking routes to `reviewScreen()` with a bare VOD
and no night: that screen prints `dayFull · clockLabel · hms`, one `reviewVodNote` sentence and a primary
**Import this broadcast** button carrying `bf-pick` plus `data-id`/`data-length`/`data-title`. Round 9 drew no
workbench on that page; **round 10 put it back** (§22.3) — the scrubber and the sidebars belong there whether or
not a night exists yet. Nothing has to be built first — that is item 8.
`recordsScreen()` resolves `#/records/review/<id>` against `data.history` first and the archive second, so a
night and a bare VOD share one route.

### 21.4 The phone at 390: a regression the measurement caught

At 390 the Records screen measured `documentElement.scrollWidth` **670** while every other tab measured 390.
Cause, measured rather than guessed: `article.archive-card` is a grid item of the screen's `.stack` and had no
rule of its own, so `min-width:auto` let the 658 px min-content of the day scroller freeze the column. One
line at the end of the Records block in `annotator/ops.css`, with the measurement in the comment above it:
`#ops-shell .stack.records>*{min-width:0}`. After it: `docSW` 390, the card 366 wide, `.tl-vods` 332 wide with
`scrollWidth` 412 — the scroller finally doing the work it was built for — and at 1280 `.tl-vods` is 1185,
equal to its own `scrollWidth`, since a day holds at most three cards.

### 21.5 Evidence

- **Suites**: `node --test tests/test_ops.js` → **152 pass / 0 fail**; `node tests/test_app_timeline.js` →
  **81 passed, 0 failed**; `node --test tests/test_board.js` → **16 pass / 0 fail**;
  `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` → OK (skipped=48). The 25 stale assertions in
  `tests/test_ops.js` were moved to the new contracts (the deleted words, the picker's markup, the archive
  card, the two-line standing row); none was deleted without a replacement.
- **The console, in a browser**, at 1280×900 and 390×844, in English and 中文: the timer screen of item 1
  (face 399×153, rail 332×6 at 1280; 206×79 at 390), six solid destination balls and **no** `data-stripe`
  anywhere, Regulars (4 stat cells, 4 counted filters, 8 two-line rows and no `.tile`), Records (26 day
  sections, 31 cards, each a button carrying a `data-id`), and the card → `#/records/review/2890514774`
  round trip.
- **The picker's write path** on the isolated root, with the state file's md5 and revision as the proof
  (§21.2) — production untouched.
- **The detector** (`impeccable detect --json annotator/ops.js annotator/ops.css`): 25 findings, 17 advisory
  and 8 warning, 24 of them in `annotator/ops.css`. Three sit on lines this round touched; all three are
  advisory and accepted with their reason in `docs/impeccable-ledger.md`.
- Shots for every screen above are in `out/r9/` (`docs/console-shots.md` §15).

## §22 — Round 10: Manage regulars off the desk, not-here back at the match, and an import that takes the broadcast (2026-10-04)

The work order (m06741) is three sentences, and the second one is also a ruling:

> 1. rm the 'manage regulars' button  2. rm the 'not here' button and 'here now' label from the registration
> page. not here is a feature for when its a particular matchup's turn and one of them is not present.  3. import
> broadcast should import the whole thing without time bounds. the recorded scrubber seems to be missing the
> scrubber and the sidebar elements. please fix.

**No python changed in this round.** Items 1–3 are `annotator/ops.js`, `annotator/ops.css` and
`annotator/vision-stage.js`.

### 22.1 Items 1 and 2: the registration page stops carrying club-wide opinions

| # | the owner's words | what shipped |
|---|---|---|
| 1 | "rm the 'manage regulars' button" | `entrantsCard()`'s heading loses the `data-tab="players"` button. Regulars is nav ball 5; a roster is managed there, not from a desk that is holding a tournament. The word `manageRegulars` is deleted in both languages. |
| 2 | "rm the 'not here' button and 'here now' label from the registration page" | The same card loses its `<small class="attendance">` label (`Here now` / `Not here`), its `data-action="entrant-absence"` button and the `rackAbsentNote` paragraph under the heading; the delegated click handler loses the `entrant-absence` branch. The words `attendance` and `rackAbsentNote` and the rule `#ops-shell .attendance{color:var(--ink-dim)}` are deleted. |

What stays, and why it is not a leftover:

- **The feature itself.** `matchControls(m)` draws the per-side `Not here` / `Here now` button on a match — the
  owner's own reading of it, "when its a particular matchup's turn and one of them is not present" — and
  `scoreboardScreen()` keeps the row that says a match is waiting on someone. Neither was touched.
- **The server action** `entrant_absence`, which those controls call (`tests/test_operations.py` and
  `tests/test_board_api.py` call it directly, so it is not dead server-side either).
- **The audit label** `entrant_absence` (`Registration attendance changed`), so a row written by an earlier
  console still renders.

### 22.2 Item 3a: the import is the broadcast, nothing narrower

The backfill's import posted `{vod, start_s, duration_s}` from the two fields of its verify step, so the download
was whatever the operator typed. It now posts `{vod: bf.vod.id}`, and the fields that could bound it are gone:
`bfEstimate()` asks `/api/vods/estimate?vod=<id>`, `bfPickStep()`/`bfVerifyStep()` no longer render `#bf-start` or
`#bf-length`, `bfInput`'s `start`/`length` branches and `bfLength()` are deleted, and the disk-refusal branch
offers **Pick another broadcast** (`bfOther`) instead of "shorten the range" (`bfShorten`), because there is no
range left to shorten.

**The server needed no change, which is the point**: `annotator/vod_import.py`'s
`_plan(vod, start_s, duration_s)` already defaults to the whole broadcast — `start = _whole(start_s,"start_s",0)`,
`duration = _whole(duration_s,"duration_s",length-start)` — and `src/datasets.py`'s `imported_id(vod_id)` names the
dataset from the VOD id alone when the range is the whole thing, so an import with both bounds absent lands on
exactly the dataset the whole-range import would have produced. Two bound fields were the only thing between the
console and that default.

The same treatment went into `annotator/vision-stage.js`'s Source panel (`bcEstimate()`, `bcImport()`, the
`bc-start`/`bc-minutes` fields and the `bcStart`/`bcDuration` words), because after item 3b that panel is one
click from the recorded page — a second ranged import there would recreate this complaint in a new place.

### 22.3 Item 3b: the recorded page keeps its workbench

`reviewScreen()` ended `${isVod?'':visionSurface()}`, so a broadcast with no night yet — the page every card on
Records leads to — drew the note and the import button and nothing else: no scrubber, no cues rail, no inspector.
It now always renders the surface (`</article>${visionSurface()}`).

Two things make that honest rather than decorative:

- **The right video.** `broadcastVodId()` (the night's `source.vodId`, or the bare VOD's id) and
  `datasetForVod(vodId)` (the dataset `tw-<vod id>` — the name `src/datasets.py`'s `imported_id()` gives a
  whole-broadcast import — else any dataset id carrying those digits, i.e. a ranged import of the same
  broadcast) let `showReview()`
  select this broadcast's own dataset after it mounts, once per id (`vodDatasetAsked`). Before this, the engine's
  `loadDatasets()` in `annotator/app.js` picks `vod30` whenever that dataset exists — so even a night whose
  broadcast *had* been imported would have opened `vod30`'s frames, which is the second half of the same bug.
- **The right words.** `reviewVodNote`/`reviewNote` now say that the chips name the datasets this console is
  configured with when this broadcast has none of its own; nothing on the page claims frames that are not there.

### 22.4 Evidence

- **Suites**: `node --test tests/test_ops.js` → **154 pass / 0 fail**; `node tests/test_app_timeline.js` →
  **81 passed, 0 failed**; `node --test tests/test_board.js` → **16 pass / 0 fail**. Two tests are new: one reads
  the source for the import body and the estimate URL, one asserts the broadcast page carries `#vs-grid`,
  `.vs-rail`, `.vs-inspector`, `#vs-scrub`, `.vs-track` and the import button, and that `datasetForVod` answers
  for three different dataset lists.
- **The console, live on `127.0.0.1:8130`** (serving the edited files without a restart), 1280×900: the desk shows
  1 entry, **0** `.attendance`, **0** `entrant-absence`, the picker and the remove button intact, and no `Manage
  regulars` / `Here now` / `Not here` text; the first Records card leads to `#/records/review/2890514774` with
  `#vision-surface` 1, `#vs-grid` 1, `.vs-rail` 1, `.vs-inspector` 1, `#vs-scrub` 1, `.vs-track` 1
  (`display:block`), `.vs-frame-input` 1 (`display:flex`), two step buttons and the play button;
  `Import this broadcast` opens `[data-step=verify]` with **0** `#bf-start`/`#bf-length`, and Estimate issues
  exactly one request — `/api/vods/estimate?vod=2890514774`, no `start_s`, no `duration_s` — while the line reads
  `About 6.8 GB · 173.1 GB free on disk · ` for the whole 4:34:15 broadcast.
- **390×844 and 中文**: `documentElement.scrollWidth` 390 in both languages; the surface is still there
  (`#vs-grid` 1, `#vs-scrub` 366×22, `.vs-track` `display:block`), the grid collapses to one column, and the
  inspector becomes the sheet tab the stylesheet has always made it below 1100 px.
- **The live tab is untouched**: `#/vision` reads `data-vision="live"`, `#vision-surface` 0, `#vision-host` hidden,
  and the panel still reads `Live stream idle · Frame age: — ms · Dropped: 0 · twitch ttpoolfriday` with Start/Stop
  and the three detectors — round 8's "only the stream" ruling holds.
- **The detector** (`impeccable detect --json annotator/ops.js annotator/ops.css annotator/vision-stage.js`):
  25 findings, 17 advisory and 8 warning, 24 of them in `annotator/ops.css` — the same set round 9 tabled, every
  entry shifted to its new line by this round's own edits. **None sits on a line this round touched**; the
  comparison and the disposition are in `docs/impeccable-ledger.md`.
- Shots are in `out/r10/` (`docs/console-shots.md` §16).
- Limits: a **cold deep link** to `#/records/review/<id>` still lands on the Records list, because the route is
  resolved at boot before `/api/vods/recent` answers — the operator's path (open Records, click the card) is what
  this round measured and what works. And `About 6.8 GB` is an estimate of the whole broadcast, not a promise:
  whole-broadcast imports are multi-hour files by definition, which is what was asked for.

## §23 — Round 11: one history (the nights and the broadcasts), a link an operator makes from either end, and the club's own database (2026-10-04)

The round's work order is m07044. One sentence of it is quoted verbatim here because the console's own
comment carries it, and it is the whole of item 2:

> every vod should be able to be associated to one or more competition. and every competition can be
> associated to one or more vod.

The rest of the same message, in short (paraphrased; the message itself is m07044): the shot timer is one
thing and its name is **出杆计时**, not 击球计时, in both clocks; 录制场次 and 历史赛事 are **one list**, not
two screens; and the association has to be makeable from either end.

**What the round is, in one line**: the relation is a store fact — the join table `links`, keyed by the
pair `(vodId, eventId)` — and the console renders it and never derives or invents it.

### 23.1 The model: `vods` and `links` (`annotator/operations.py`)

- `state['vods']` is the broadcasts this console has seen — `{id, title, channel, length_s, created_at}`.
  It exists because the workbench must render a broadcast it can no longer ask Twitch about, and because
  the archive window (`/api/vods/recent`, `RECENT_TTL_S`) is a window, not a record.
- `state['links']` is the relation: one row per pair — `{vodId, eventId, startS, endS, at}`. `_link_vod`
  (`annotator/operations.py:174-196`, reached from the `vod_link` action at `:880`) is idempotent for the
  pair and refreshes the *range* only when the caller knows one ("a link's range belongs to whoever knows it:
  an import writes it, the picker leaves it alone, and a wrong one is cleared by unlink then link again").
  `_unlink_vod` (`:205-217`, reached at `:882`) refuses the
  night's own import — `"This broadcast is this event's own import record; delete or hide the event
  instead"` — because that line is still in the event and the next read would materialise the row again.
  `_drop_links` (`:219-222`) drops a night's rows when the night stops existing, so the table never has a
  dangling end.
- **The import already wrote the relation, in the same write as the night.** Every write ends in `_commit`
  (`annotator/operations.py:290-293`), whose first act is `self._adopt_sources(state)` — "a write persists
  the relation it can derive, so the next reader does not have to" — so the row an import creates is in the
  document before the revision advances. Round 11 is where that relation became visible in the console and
  where an operator can add more to it.
- The two actions are `vod_link` / `vod_unlink` on the existing endpoint: `POST /api/operations` with
  `{revision, action:'vod_link', vodId, eventId, title?, channel?, length_s?, created_at?}` — the metadata
  the picker is holding, so the server never has to ask Twitch — and `{revision, action:'vod_unlink',
  vodId, eventId}` for dropping a pair. The usual revision fence applies (`ConflictError("State changed;
  reload before retrying")`).
- `annotator/operations.py` is **51872 bytes** after the round (161 added lines); `tests/test_operations.py`
  **79905 bytes**, +146 lines in a new `class VodLinkTests` (1132): a backfilled night *is* a link;
  one broadcast covers many events and one event many broadcasts; metadata is refreshed field by field; a
  refused link writes nothing; unlinking leaves the broadcast known; an event that stops existing takes its
  links away; an archived event keeps its links.

### 23.2 The document that predates the table: `normalise()`

A stored document is not a schema. The club's own `out/corner-pocket/state.json` — and its Postgres copy —
was written by builds that had no `vods` and no `links`, so a read that assumed both keys would raise on
exactly the file the club depends on. The fix is a module-level `normalise(state)` (`annotator/operations.py:103`)
that does three `setdefault`s and then materialises the imports' own rows once
(`Operations._adopt_sources`, `:225-243`): for every `source` an import wrote, one `vods` row (the line's
title) and one `links` row (the line's range, or `None` for "the whole broadcast"). It is read-time,
idempotent, clock-free and writes nothing back — a read never rewrites the file — and `Operations._load`
now returns `normalise(json.loads(...))`, so a JSON document, a Postgres document and a fresh one all reach
the rules in the same shape.

The Postgres half needed the same call for the same reason: `PostgresStore._document`
(`src/store_pg.py:106`) reads one raw text document out of `json_documents` and is *not* `Operations._load`,
so it now calls the same `normalise`. Eight added lines in `src/store_pg.py` (20205 bytes) and the two
stores agree again. `docs/postgres.md` records it.

Two tests hold this down, one per store, both built by `tests/test_store_contract.py`'s `before_round_11()`
— a revision-7 document with one archived night that has a `source` line and neither new key
(`tests/test_store_contract.py`, +49 lines): the JSON test writes that file and reads it back through
`Operations`, the Postgres test puts that text into `json_documents` and reads it back through
`PostgresStore`; both require the two keys, the exact link row
(`{"vodId":"2274501933","eventId":"night1","startS":3600,"endS":11400,"at":""}`), the broadcast it names,
the document byte-identical after the read, and a second read equal to the first. `tests/test_store_roundtrip.py`
(+7 lines) adds two links over the archived night, so the relation is proven to survive a real Postgres
round-trip with its numbers, not just its keys.

### 23.3 One list

`recordsScreen()` renders **one card** (`#archive-card`) headed `历史赛事` / `Events`: the search input, the
hidden-nights toggle, the count, Refresh, Backfill a past event, the archive note, the automatic-download
line, `<div id="records-list">`, and the rest-audit fold. The archive's own card, its own heading and
`archiveTimeline()` are gone; `timelineHtml()` is gone with it, and `mergedTimeline()` is the one renderer.
It walks the nights and the broadcasts once, groups them by the day they share (`dayKeyOf`), sorts the days
newest first, then emits year → month → day: `<h3 class="tl-year">`, `<section class="tl-month">` with
`<h3 class="tl-month-head">`, and `<section class="tl-day" data-day="YYYY-M-D">` whose head is
`<h3 class="tl-day-date">` plus a `.tl-day-count` that counts **both** kinds (`2 events · 1 broadcast` /
`2 场赛事 · 1 段直播`). A day carries `ol.tl-nights` and/or `ol.tl-vods` — the same day head for both, which
is what "what happened on the 2nd" should answer.

- **The list is a union, and the union was a browser find.** `/api/vods/recent` is a window with a TTL and
  it is the *server's* view of the channel; the store's own `vods` rows are what a link points at. The first
  browser pass on an isolated root showed **0 broadcasts** with three links on screen, because the list read
  only the archive. `knownVods()` (the record's rows, `fromRecord:true`) is appended to `archiveVods()` by
  id — the archive wins when it has the row, because it carries the thumbnail and the fresh metadata — and a
  card that came from the record alone says so (`Known to this console` / `本机记录的直播`). The node test
  that pins it lists 3 cards for 2 archive rows + 1 record row, with exactly one `.tl-vod-note` and no
  duplicate.
- **A card's mark is the nights that claim it**: `archiveRow(vod, links)` renders `已关联赛事 · <names>`
  when any link row names a night, and `is-made` follows the same rule. The round-6 word `archiveBuilt`
  ("Night built") is gone — with many-to-many, "built" is not one thing.
- **The count line is the head's number, always**: `{n} broadcasts · {built} linked to an event`
  (`31 broadcasts · 0 linked to an event` on the club's page). See 23.5 for why this needed a second pass.
- **One class collision from round 9 is gone**: the day head used `.tl-date`, the same class as a night
  row's date, and a later rule restyled the rows' dates too. The head is `.tl-day-date` now (CSS 1075/1090
  renamed), and the test asserts both that the class exists and that no `.tl-date` rule carries the head's
  `var(--fs-xl)` again.

### 23.4 The link, from either end

- **On a night, inside its drawer** (`eventLinks(night)`, rendered by `eventItem()` after the source line):
  `Broadcasts` / `直播回放`, one chip per link — the broadcast's title, its own import marked
  `本晚自己的导入` / `This night's own import` and unlinkable, the others carrying a `×` — plus the picker
  `Link a broadcast` / `关联直播`.
- **On a broadcast's own page** (`vodEventSection(vodId)`, rendered by `reviewScreen()` when the screen is a
  VOD): the same row labelled `历史赛事` / `Events`, the nights that cover it as chips, and the picker
  `Link an event` / `关联赛事`.
- **The picker is the desk's own listbox**, reused rather than reinvented: `.pick-btn` + `.pick-panel` in
  flow, `data-total`, one `.pick-search` (`data-vod-search`), a `.pick-count` that reads `{n} of {m}` and is
  filtered *in place* by `vodFilter()` (no re-render, so the caret keeps its place), and rows that are
  `data-action="vod-link"` — or `vod-unlink` when the pair already exists, or `disabled` with the badge when
  the pair is the night's own import (`is-locked`). It offers **only what is free**: a broadcast the night
  already claims is not offered again, and the night's own import is not offered at all. Opened from the desk
  side it lists the live tournament first, marked `今晚` / `Tonight`.
- **The writes carry the metadata the console already holds** — `{vodId, eventId, title, channel, length_s,
  created_at}` — so making a link costs one POST and no Twitch call. The console never derives the relation:
  it posts the pair, re-reads, and renders what came back (`.pm/PROJECT.md`'s standing rule about the store
  being the only writer).

### 23.5 Two live defects the shots caught

Both were found by measuring the real page, not by a test, and both are recorded because the tests were
green while they were live.

1. **The count line never appeared.** `paintArchive()` repainted only `#records-list`, while the count span
   and the archive note were rendered inside the *first* paint's conditional — and `archiveList.rows` is
   `null` at the first paint and filled when `/api/vods/recent` answers. So the number the round exists to
   show (`{n} broadcasts · {built} linked to an event`) and the `archiveMore` sentence were **absent from a
   live page**; the node tests passed because they pre-populate `archiveList`. Round 9/10 had the head inside
   the repainted region; round 11 introduced this by narrowing the repaint target. The fix keeps round 6's
   rule that a late answer must not rebuild the screen under an operator: `archiveCountText()` and
   `archiveNoteText()` are now the single source of both sentences, `recordsScreen()` always renders them,
   and `paintArchive()` writes them **in place** (`count.textContent=…`, `note.textContent=…`) next to the
   list it repaints. Measured on production afterwards: `31 broadcasts · 0 linked to an event` in English,
   `31 段直播 · 0 段已关联赛事` in 中文.
2. **The phone scrolled sideways again: 653 px inside a 390 px window.** Every element from `h3.tl-year`
   down to `ol.tl-vods` measured **624** wide in a 332-wide list, in both languages. The mechanism: round 11
   moved the day rows into the `.events` grid (`#ops-shell .events{display:grid;gap:var(--sp-1)}`,
   `annotator/ops.css:750`), so `.tl-month` became a grid item whose computed `min-width:auto` let the
   grid's `auto` track take its min-content — the `.tl-vods` scroller's contents, exactly
   `3×200 + 2×12 = 624`. Round 10 had fixed the same class of bug one level up
   (`#ops-shell .stack.records>*{min-width:0}`, §21.4 "The phone at 390: a regression the measurement
   caught", 670 → 390 then); round 11 re-broke it by changing the chain. The fix is one declaration, with the
   measurement in the comment above it: `#ops-shell .events{display:grid;gap:var(--sp-1);
   grid-template-columns:minmax(0,1fr)}`. Re-measured: 390 → `documentElement.scrollWidth` **390**, card 366,
   `.tl-vods` 332 with `scrollWidth` 412, `.tl-vod-item` 200 — the same numbers §21.4 recorded; 1280 →
   **1280**, `.tl-vods` 1185 == its own `scrollWidth` 1185.

### 23.6 The incident: a suite that wrote into the club, and the guard

The full python suite was launched **with `POOL_DATABASE_URL` exported** (the variable production needs).
It ended `Ran 1265 tests in 224.015s · FAILED (failures=13, errors=11, skipped=4)` — and the failures were
the smaller half of the problem. `open_store()` (`src/store.py:100`) is "Postgres when `POOL_DATABASE_URL`
is set, else the JSON files", so **every in-process `Backend(root)` in the fixture tests was reading and
writing the live club's document** (the database keys it by path, not by root: `out/corner-pocket/state.json`).
`tests/test_unified_server.py:565` failing with `AssertionError: 11 != 1` for `len(state['players'])` was how
it surfaced.

The damage, from the event log that is never truncated (`ops_events`): revisions 22–32
(`player_enroll_from_tracklet` for `Ana` ×5 and `Bo` ×5, `player_save` `Club Regular`) and revisions 33–40
(seven `entrant_add` and a `tournament_start`, which is what created 7 matches and made the tournament
`active` with `raceTo=1`). The club's own last real write was revision 21. It was repaired through the
store's own writer in one transaction (`_locked` → `_document` → drop the three test players, keep the one
real entrant, `matches: []`, `status: 'registration'`, delete the 15 faces those players had, delete
`ops_events` rows above 21 → `_save(…,'repair_test_leak')`), leaving **revision 41 with the eight real
regulars, one entrant and no matches**; the backup of everything touched is `/tmp/r11-repair-backup.json`.

**The prevention is a refusal, not a warning.** `open_store()` now checks `scratch_root(root)` — a root
under the system temp directory — and raises before it can hand a temporary fixture root the club database:

```
open_store: POOL_DATABASE_URL is set, so the club's data lives in Postgres and the root does not isolate
anything: every rooted store with this database reads the same document (out/corner-pocket/state.json).
/tmp/tmpXXXX is a scratch directory, so it would be handed the live club. Refusing. Run without
POOL_DATABASE_URL, or open a throwaway schema on purpose: PostgresStore(root, search_path='...')
(docs/postgres.md).
```

`src/store.py` (15299 bytes, +27 lines) carries `scratch_root` and the refusal; `tests/test_store.py`
(13607 bytes) replaces the selection test's dangerous shape (it used to assert that a *temp* root became a
`PostgresStore`) with one that uses the repository root for that branch, and adds
`test_a_scratch_root_is_never_handed_the_club_database`, which asserts the message names the root, the
variable, `scratch`, the document path, `search_path` and `docs/postgres.md`, and that without the variable
the same fixture root is a `JsonStore`. `docs/postgres.md` (+23 lines) gains the two-pass rule — the fixture
pass runs without the variable, the database passes run per file against their own migrated-and-dropped
schema, and a caller that wants a database from a temporary root constructs `PostgresStore(root,
search_path=…)` on purpose, never `open_store`. Deliberate env-var tests (`tests/test_store.py`,
`tests/test_db.py`, the contract/import/roundtrip classes with their own schemas) are untouched, and
`Backend.store` is lazy (`annotator/unified_server.py:425-431`) so `tests/test_board_api.py`'s
fixture-then-assign pattern still works.

**Proof the guard bites**: `POOL_DATABASE_URL='postgresql://u@127.0.0.1:1/x' … -m unittest test_unified_server`
now stops in the first second with the refusal above, per fixture root, instead of writing to the club.

### 23.7 Verification

| what | result |
|---|---|
| `node --test tests/test_ops.js` (311506 B, +3 tests) | **159 tests · 159 pass · 0 fail** |
| `node tests/test_app_timeline.js` | **81 passed, 0 failed** |
| `node --test tests/test_board.js` | **16 tests · 16 pass · 0 fail** |
| `env -u POOL_DATABASE_URL .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | **`Ran 1266 tests in 245.968s` / `OK (skipped=49)`** |
| `… -m unittest test_store_contract` (with the database) | **`Ran 50 tests in 19.149s` / `OK`** |
| `env -u POOL_DATABASE_URL … -m unittest test_store` | **`Ran 15 tests in 10.705s` / `OK`** |
| detector (`impeccable detect --json annotator/ops.js annotator/ops.css`) | **25 findings — the same 25 as round 9, 0 on a round-11 line** (`docs/impeccable-ledger.md`) |

Production (`127.0.0.1:8130`, served off disk, one restart for the python half): Records reads one card,
26 days, 31 broadcast cards, 0 nights, 0 chips, the count line present, `#auto-line` live; 中文 reads
`31 段直播 · 0 段已关联赛事` under `历史赛事`, the day heads are 中文 dates and `#tabbar` is
`1出杆计时2赛事3战绩档案4视觉5常客6后台` — **the rename is live in the nav** — and `#/clock` reads
`h2 出杆计时`. The isolated root (`--root /tmp/r11-root`, the shipped code) is where the relation is proven
in a browser: one day holding 3 nights and 3 broadcasts (all three cards `Known to this console`, because
that root has no archive window at all), the count `3 broadcasts · 2 linked to an event`, the night's chips
at 482×42 for its own import (badge, no `×`) and 119×42 for the two links an operator made, and both
pickers offering exactly what is free (night side `1 of 1`, broadcast side `4 of 4` with one `is-locked`).
Shots are in `out/r11/` (`docs/console-shots.md` §17).

Limits, stated rather than hidden: the chips and the picker live **inside the night's drawer** (`.tl-body`)
— the list stays one line per night and the operator expands to link, which is the console's existing shape,
but it means a collapsed list shows no chips at all; a **cold deep link** to `#/records/review/<id>` still
lands on the Records list (pre-existing, §22); the day head is the **broadcast's** date (its `created_at`
in this machine's zone) and a night's date is its archived date, so a night played after midnight and its
broadcast can fall on different days — the operator's list shows both, and the join is the link, not the
date; and `{built}` counts links, so a broadcast covering two nights counts once.

## §24 — Round 12: one list, the match on the timer page, and a finish card that stops talking (2026-10-04)

The owner sent three items with a screenshot of a night in play. The screenshot showed the Tonight screen
during a competition, and the quoted page text was the whole of item 3.

### 24.1 Item 1: `等待上场` and `对阵表` are one list

The two cards were the same list read twice. The queue held the ready matches, the live tables and the
signed results. The bracket held the draw, and it repeated the live tables and the signed results inside
its rounds. Measured on the isolated root at 1280: `details.panel` **2**, `.queue-card` **2**, and the same
ring of live matches in three places (the board, `On a table now`, Round 1).

`queuePanel()`, `queueScreen()`, `queueRank()`, `sendCard()`, `queueCard()` and the dead `roundsPanel()` are
deleted. `bracketScreen()` returns **one** `article.bracket-view`:

- `<div class="heading"><h3>对阵表</h3><span class="muted">{facts}</span></div>`, where the facts are
  `bracketLine()` — `{n}/{m} signed` always, and `{n} on table` / `{n} delayed` only when they are not zero —
  plus `{n} to send` when a match is ready;
- the density row (unchanged), then `.rounds` with every match of the night;
- the event table fold moved to `playScreen()` as `eventFold()`.

The list is **not** a `<details>`: `render()` rebuilds `#main.innerHTML`, so a drawer closes itself after
every write, and the operator had to reopen it to send the next match. Send now sits on the match's own card,
where its table and its two names already are.

Measured after, isolated root at 1280: `details.panel` **0**, `.queue-card` **0**, `.bracket-view` **1**,
`.round` **4**, `.bracket-card` **15** (every match of the night once), `details.side-panel` **1**,
`documentElement.scrollWidth` **1280** == `innerWidth`.

Fourteen word keys that only the deleted cards rendered went with them: `queueTitle`, `queueNote`,
`emptyQueueReady`, `emptyQueueDraw`, `onTable`, `signedTitle`, `openTable`, `goQueue`, `sheetTitle`,
`closeSheetNote`, `closeSheetEmpty`, `closeNote`, `endNightTitle`, `endNightNote`. The shell still holds 37
keys no screen renders; those are older, and they are not this round's business.

### 24.2 Item 2: the match follows the night onto the timer's own page

`clockScreen()` now ends with `${liveComp()?scoreboardScreen():''}`. The block is the element from the
screenshot: the badge, the table and the match id, the race badge, the table select, both names, both
scores with `+`/`−`, `Clear score`, `Release table` and `Sign scorecard`.

It is guarded by `liveComp()` — a night is being played — not by a live match, because the empty board
(`No match is on a table. The next match is ready…`) is what a tablet at the table needs between frames.
Measured: isolated root, clock page, 1280 → `.timer-card` **1**, `.scoreboard` **1**, 321 characters;
production (a finished night) → `.scoreboard` **0**, 27 characters, the timer alone.

A tablet at the table must also follow the desk's sends without a reload, so the page re-reads
`/api/operations` every **4 s**:

```
let opsTimer=null;
function stopOpsPolling(){clearTimeout(opsTimer);opsTimer=null}
function syncOpsPolling(){stopOpsPolling();if(tab==='clock'&&liveComp()&&!document.hidden)opsTimer=setTimeout(pollOps,4000)}
async function pollOps(){…}
```

`pollOps()` writes nothing. It stands down on every other tab, on a hidden page, while `busy`, while a match
write is in flight (`pendingMatches.size`), and while a form, dialog or picker is open (`deskOpen`, `selected`,
`setupOpen`, `bf`). It re-renders only when the revision changed. `render()` calls `stopOpsPolling()` and
`syncOpsPolling()` beside the live polling, and `pageshow` + `visibilitychange` do the same.

The block lives **below** `function render()`, not with the clock, and the round-7 rule is why: the clock bar
paints before the first fetch answers and in every venue state, so it reads no match state. That rule now has
three named windows in `tests/test_ops.js` — the bar and its host (`clockHTML()` → `clockScreen()`), the
repaint loop (`tick()` → `const screens=`), and the timer card (the part of `clockScreen()` before the match
block). The old instrument sliced `clockHTML()` → `render()`, which swallowed both the timer page and the poll.

### 24.3 Item 3: the finish is one card, one row, one reason

The owner's screenshot listed four headings for one thing (`收尾`, `结果单`, `结束今晚`, and the night card),
five prose sentences, six tiles, the event name three times and `单打 · 抢1` three times.

`closeSheetCard()` is gone. `wrapScreen()` is now `${closeCard()}${revivalCard()}` and `closeCard()` is one
`article.end-night`:

- `<h3>收尾</h3>`;
- one row: **结果单** (primary, and only once the night is drawn) · **归档并新建赛事** · **删除赛事** (disabled
  per the existing reason) · **赛事设置**;
- one line, only when the delete is off: the same `closeNoEvent` / `closeNoEntrants` / `closeSigned` sentence.

The six tiles became the `bracketLine()` sentence in the draw's heading. The night card is **dropped from the
finish branch** (`tonightScreen()`'s complete branch is `${wrapScreen()}${bracketScreen()}`), so the name,
the format and the race appear once, in the scene line. The default-name note moved into `scene()` with them,
where the name is shown.

Measured on production, the owner's own night, 1280:

| | before | after (EN) | after (中文) |
|---|---|---|---|
| `#main` text | **697** chars | **275** chars | **121** chars |
| `<h3>` on the screen | **5** | **3** | **3** |
| paragraphs | 5 (four prose + one meta) | **1** (the one reason) | 1 |
| `.tile` | **6** | **0** | **0** |
| the event name | 3× | **1×** | 1× |

The three headings left are `Close the night`, `Bracket` and `Round 1` — one card, one list, the draw.

### 24.4 The defect the phone shot caught

The merged card was measured at 390 px on the way out, and the Tonight page had **412 px of horizontal
overflow** (`scrollWidth` **802** on a 390 px phone). Two causes, both min-content:

- `article.bracket-view` is a flex item of the night's stack. Its automatic minimum size was the `.rounds`
  scroller's content (**756 px**), because a block-level `overflow:auto` child still hands its min-content to
  its parent.
- the board's `select#focus-match` is `width:100%` with an automatic minimum of its widest option
  (`球台 1 · Kenji Watanabe / Tomás Ibarra`, **756 px**), which pushed the board to **790 px**.

The old page did not show it: the same board sat in a stack whose width the closed bracket panel did not
inflate. The fix is three declarations — `#ops-shell .bracket-view{min-width:0}`,
`#ops-shell .scoreboard{min-width:0}`, `#ops-shell .score-top select{min-width:0;max-width:100%}` — and the
re-measure is `scrollWidth` **390** == `innerWidth` at 390 in both languages, and **1280** at 1280. The clock
page measured **390** == 390 before and after.

### 24.5 Verification

Suites, on the shipped tree: `node --test tests/test_ops.js` **162/162** (159 + the three round-12
instruments), `node tests/test_app_timeline.js` **81/0**, `node --test tests/test_board.js` **16/16**. No
Python file changed, so no Python suite was run.

| what | where | measured |
|---|---|---|
| the finish, before and after | production 8130, 1280 | 697 → 275 chars; 5 → 3 headings; 6 → 0 tiles (§24.3) |
| one list | isolated root 8144, `#/tonight`, 1280 | `details.panel` 2 → **0**; `.bracket-card` **15**; `scrollWidth` 1280 |
| the match on the timer | isolated root, `#/clock`, 1280 | `.timer-card` **1** + `.scoreboard` **1**; production finish → `.scoreboard` **0** |
| the phone | isolated root, 390, EN + 中文 | `scrollWidth` 802 → **390** == `innerWidth` |
| the languages | both pages, EN + 中文 | the words that name the draw read `Bracket` / `对阵表` |

Shots: `out/r12/before-finish-1280.png`, `after-finish-1280-en.png`, `after-finish-1280-zh.png`,
`after-active-1280-en.png`, `after-active-1280-zh.png`, `after-clock-1280-en.png`, `after-clock-1280-zh.png`,
`after-tonight-390-en.png`, `after-tonight-390-zh.png`, `after-clock-390-en.png`, `after-clock-390-zh.png`.

Limits: the finish screen is the club's own night (revision 46, one signed match), so the before/after table
is one night, not a survey. The merged list and the timer page are the isolated root, which is the only
mid-competition data on this host. The 4 s poll is asserted at the level of its guard and its fetch, not on a
wall clock; nobody has yet watched a tablet follow a send. And the exported `resultsSheet()` is unchanged —
the owner asked for the finish *screen* to be quiet, and the sheet is still the sheet.

## §25 — Round 13a: the competition tab is three elements, one tree view, and no attendance (2026-10-04)

The owner sent nine items. This section covers the six that share one page: ① the settings dialog's buttons,
③ 收尾 on the Back room, ④ the two bracket densities, ⑤ 未到场, ⑥ the board on the competition tab, ⑨ the tab's
three elements. Items ②, ⑦ and ⑧ are the Records tab, the Vision page and the Twitch source configurator.

### 25.1 Item ⑨ + ③: three elements, one of which carries the night's end

`tonightScreen()` had four bodies (`idleStart()`, `setupScreen()`, the active branch with the board, and
`wrapScreen()` for the finish) and the tab rearranged itself as the night moved. It now returns one body for
every state:

```
scene()
section.stack.tonight
  article.card.card--event    赛事设置   the door + Results sheet / Archive & new event / Delete event
  section.stack               bracketScreen()
  article.card.card--entrants 参赛名单   the desk (add entrant, pairing) + the rows
  (revivalCard(), eventFold())
```

`nightCard()`, `setupScreen()`, `wrapScreen()`, `playScreen()`'s old shape and `closeCard()`'s own heading are
gone; `closeCard()` is the row and the one reason line, inside the event card. `statusScreen()` (the Back room)
lost `${closeCard()}` — item ③ is answered by deletion, not by a second copy. The desk moved into the entrants
card because it is about entrants, and the pairing card sits above the form.

The first-run dialog is only for a night with no name at all: `state==='idle' && !id && !name`. A named night
sees its three cards, and the `open-setup` door renders `startModal(true)` over them.

Measured, production 8130, `#/tonight`, 1280: `article.card` **2**, `.card--event` **1**, `.bracket-view`
**1**, `.card--entrants` **1**, headings `Event settings / Bracket / Round 1 / Entrants`, `.scoreboard` **0**,
`[data-action="absence"]` **0**, `[data-action="density"]` **0**, text 255 characters. Isolated root, active
night: the same three cards, 4 rounds, 15 cards, **3** `.table-chip`.

### 25.2 Item ①: Save and Close on one row

`setupForm(first, closeable)` renders both buttons in the `.actions` row, and `startModal()` no longer appends
its own `.row`. Measured in the dialog: buttons `["Save","Close"]`, one distinct `top`, trailing `.row`
count **0**. A first-run dialog (no name yet) has no Close at all, because the fields are the way in.

### 25.3 Item ④: one view

`let density`, the `density` click branch, the `.bracket-density` row, `data-density`, the three words and every
`[data-density=…]` selector are deleted. The tree is a grid that fills the width it has and wraps when it does
not: `grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr))`. The card is the compact one line per
side, and the header row and the controls open on hover, on keyboard focus, on selection, or from the card's own
expand control. Measured at 1280: 4 round columns side by side, 15 cards, `scrollWidth` 1280. At 390: 4 rounds
stacked, `scrollWidth` 390 == `innerWidth`, no overflow in either language.

### 25.4 Items ⑤ and ⑥: no attendance, and the board is the timer page's

Removed: the Here / Not here buttons (`matchControls()`), the board's waiting row, `clockToggle()`'s held-match
guard, the `absence` click branch, `action()`'s `match_absence` clock reset, the five words (`away`, `here`,
`waiting`, `confirmAway`, `confirmHere`), and the `absent` gate on Send and on the ready count. The field stays
in old documents and the console ignores it — a match with `absent:['a']` is now sent like any other.

`tonightScreen()` no longer renders `scoreboardScreen()`: the tree answers "which group is on which table" with
a `.table-chip` on the first line of every card that has a table, the live card gets a brass left edge, and
`card-open` hands the match to the timer page (`focusId`, `tab='clock'`, `syncRoute`, render). The board itself
is `clockScreen()`'s, where round 12 put it.

### 25.5 Verification

`node --test tests/test_ops.js` **162/162**, `node tests/test_app_timeline.js` **81/0**,
`node --test tests/test_board.js` **16/16**. No Python file changed. Shots in `out/r13/`:
`prod-finish-1280.png`, `iso-active-1280.png`, `iso-active-390-zh.png`, `iso-clock-1280.png`,
`settings-dialog-1280.png`.

Limits: the event card's door still carries the word 赛事设置, so the heading and the button read the same
two-word label (no shorter word exists in the shell's dictionary, and inventing one for a button is not a
trade this round needed); the 15-card draw is the isolated root, which is the only mid-competition data on this
host; and `entrant_absence` / `match_absence` stay in the audit labels, because old entries are still labelled.

## §26 — Round 13b: 历史赛事, one toolbar, and one Twitch source configurator (2026-10-04)

### 26.1 Item ②: the tab's name, and its controls rearranged

`records:['Records','战绩档案']` became `records:['History','历史赛事']`, and the page heading now uses the same
word (`t('events')` survives only in the audit labels and the notes). Measured on production: the third tab
reads `3History`, the heading `History`, and the zh tab reads `历史赛事`.

The top of the archive was a `.heading` whose right-hand row held the search box, the hidden toggle, the count,
Refresh and the primary Backfill between them, with the note under it. It is now a heading that carries the
name **and** the count (information, not a control) over one `.toolbar`:

```
[ search … ] [ show N hidden ]      (gap)      [ Sources ] [ Refresh ] [ Backfill ]
```

The search leads and grows (`flex:1 1 240px`); the actions sit at the end, behind `.toolbar-gap{flex:1 1 auto}`,
with the one primary action last; on a phone the search takes the row (`flex:1 1 100%`) and the buttons wrap
under it. Measured at 1280: children in that order, `.primary` count **1**, `scrollWidth` 1280. At 390:
`scrollWidth` **390** == `innerWidth`.

### 26.2 Item ⑧: one configurator, on both tabs

The only place a Twitch source could be added was the form inside the vision rail
(`vision-stage.js`'s `#source-form`), and its own copy said "Add the club channel under Source on Tonight".
`sourceModal()` is one dialog: the saved sources with their kind (live channel or recorded video) and a Remove
per row, one URL field with the existing hint, Save and Close on one row. `render()` mounts it over whichever
tab is open (`(bf?bfScreen():screens[tab]())+(sourceOpen?sourceModal():'')`), so the button works from History,
the Vision live panel and the review surface; it posts the same `source_add` / `source_delete` the console
always posted, and a link Twitch cannot be is stopped at the field.

Measured: on production's History the dialog lists the club's one saved channel as `Live channel` with its row
Remove; the isolated root's Vision panel and review surface each carry the button.

### 26.3 Verification

`node --test tests/test_ops.js` **164/164** (two new instruments: the toolbar's order and the configurator's two
writes), `node tests/test_app_timeline.js` **81/0**, `node --test tests/test_board.js` **16/16**. Shots:
`out/r13/history-1280.png`, `history-390.png`, `sources-dialog-1280.png`, `vision-sources-1280.png`.

Limits: the vision rail's own form is still there in this commit — round 13c's Vision redesign replaces it with
the shared dialog; the club has exactly one saved source, so the dialog's two-row case is the isolated root's.

## §27 — Round 13c: the Vision frame (2026-10-04, owner item ⑦, and ⑧ finished)

### 27.1 What the detector said, and what the page measured

`impeccable detect --json annotator/vision-stage.js` → **0 findings**. The workbench inside passes the rules
the detector knows; the owner's "redesign it" is not a rule violation, so the redesign here is measured
instead. The recorded review at 1280, before: `.vs-stage` 595×392, `.vs-rail` 280×429, `.vs-inspector`
320×446, `.vs-chips` 1219×92, `.vs-strip` 1219×130, 26 buttons, headings **h3 ×4 and h4 ×1 with no h2**, and
`#main` **1038** px tall. The review header alone was a card of four stacked blocks.

### 27.2 The frame, redesigned

- **The header is one line of work, not four blocks.** The title and its date stay in the heading; the one
  action (`Import this broadcast`), the one link control (which event this broadcast belongs to) and `Back to
  Records` stand beside them; the sentence that explains the chips became `<details class="review-why">`
  (`About this broadcast`), because it is read once and the workbench is read every time.
- **One chrome row.** The chips and the Sources door are one row (`.vs-head`), instead of the chips with the
  door under them.
- **The surface has a heading.** `<h2 class="sr-only">Review a recorded night…</h2>` opens the region: it
  started at h3, so a screen reader met the workbench as a set of subsections with no parent.

Measured after, same page, 1280: `#review-card` **252** px, `.vs-stage` 595×392 at y **501**, `#main`
**986** (was 1038), `h2` **2**, `forms` on the page **0**, `scrollWidth` 1280. At 390: `scrollWidth` **390**
== `innerWidth`, stage 366×240, `#main` 693.

### 27.3 Item ⑧ finished: one source form

The vision rail's own `#source-form` — the second place a Twitch source could be added, the one whose copy
said "Add the club channel under Source on Tonight" — is replaced by a button that opens the shared
configurator (`data-vs-action="open-sources"` → `opts.openSources()` → `sourceOpen=true; render()`). Measured
from the review surface: the dialog opens with the isolated root's **2** rows and its one form; the page itself
now holds **0** forms.

### 27.4 Verification

`node --test tests/test_ops.js` **164/164**, `node tests/test_app_timeline.js` **81/0** (two cases there
followed the removed rail form to the shared dialog), `node --test tests/test_board.js` **16/16**. Shots:
`out/r13/vision-review-before-1280.png`, `vision-review-after-1280.png`, `vision-review-after-390.png`,
`vision-sources-from-review-1280.png`.

Limits: the workbench *inside* the frame — the event cards, the ball queue, the person tracks, the layer
sheet, the frame tools — is not redesigned in this round; it is the part the detector found nothing in, and
the frame is where the operator loses the fold. The review page's own numbers are the isolated root's
un-imported broadcast, so the workspace shows its "media not found" state in the shots; that state is data,
not layout.

## §28 — Round 14: the table moves in, a review loses its choosers, and the Vision page stops toggling (2026-10-04)

### 28.1 Item ①: 本场战绩表 joins 参赛名单

`eventFold()` was a fourth element on the competition tab. It is now the last child of the entrants card
(`${eventFold()}` before that card's `</article>`), so the tab is exactly the three elements round 13 asked
for. Measured on production at 1280: `article.card` **2** (the event card and the entrants card) plus the one
draw; the entrants card's children are `heading`, `grid`, `side-panel`, and the fold holds the event table;
`scrollWidth` 1280, and 390 == 390 at 390.

### 28.2 Item ③: a recorded review has no clip and no source chooser

The clip is chosen in the timeline view, so on a review of one broadcast the workbench must not offer another
choice. `attachSurface()` passes `fixedClip:()=>!!reviewId`, and the chips row of `vision-stage.js` reads it:
no source chip, no clip chips, no live-channel chip, and `visionSurface()` draws neither the source door nor
the stop control on a recorded review. Measured on the isolated root's review: `.vs-chip` **0** remaining
(it carried the source chip, `vod30`, `highlight`, the broadcast chips and a live-channel chip),
`[data-vs-action="pick-dataset"]` **0**, `[data-vs-action="source-panel"]` **0**,
`[data-action="sources-open"]` **0**.

### 28.3 Item ④: the Vision page is the stream

The live panel offered a Start/Stop pair. It is now one card with one primary action: the status line, the
saved-channel chips, the detectors, then `Start` with the source door and the History door on the same row,
and one line about where recorded nights live (the second card is folded into it). `Stop` moved to the running
surface, where the stream is: `visionSurface()` carries it, and that surface only renders while the processor
runs. Measured on the isolated root's Vision tab with nothing running: `.live-card` **1**, `.primary` **1**,
`[data-action="live-start"]` **1**, `[data-action="live-stop"]` **0**, the source door **1**.

The honest note, since the question was "why is it a toggle": the console cannot see Twitch liveness. The
server reports the processor's state and the archive, and the shell's own label says the live status is
unverified (`liveLabel`), so an auto-start would start a processor on a channel that may be off the air. What
the page can do without guessing is what it does now: one action, one state.

### 28.4 Item ② answered: what the tracking is

The question was whether the pipeline tracks faces to people, what overlap does, and what happens when a
player is not facing the camera. From the code, not from the marketing:

| stage | implementation | what it means |
|---|---|---|
| detection | `annotator/pipeline_stages.py` `PersonStage`: "GPU YOLOv8n person boxes on the scaled frame" | a *body* detector: it does not need a face, so a player facing away is still detected |
| per-frame tracking | `src/person_pipeline.py`: greedy IoU assignment, `_IOU_MATCH = 0.3`, `_MAX_AGE = 30` | a track survives up to 30 frames without a matching box, then a new id starts |
| identity | `src/person_pipeline.py`'s docstring: "detector → OSNet re-ID → cross-exit identity → face binding"; **body (OSNet) cross-exit clustering is disabled by default** because "measured same/cross-person OSNet cosine distributions overlap on this footage" | identity comes from a **face** (`buffalo_l`), bound at ≥ 0.47 with the runner-up trailing by 0.12 |
| the field the UI shows | `annotator/unified_server.py`: `_PERSON_FIELDS = ("track_id", "bbox", "cluster_id", "player_id", "face_sim", "bound_evidence")` | a track can be a track without a name: `player_id` empty, `face_sim` low, and `bound_evidence` says why |

So: **not face-to-human tracking** — bodies are tracked and faces are what name them. Overlap: IoU matching
at 0.3 with a 30-frame grace; two players who cross can swap ids when their boxes overlap heavily, and there is
no body-appearance gate to repair it (that gate is measured off, not missing). Not facing the camera: detected
and tracked, but unnamed until a quality face appears; the docs record the reason the faces are small —
`det_size` stays 640 and "median eye ~10 px would not survive a smaller detector input".

### 28.5 Verification

`node --test tests/test_ops.js` **167/167** (three new instruments), `node tests/test_app_timeline.js` **81/0**,
`node --test tests/test_board.js` **16/16**. Shots: `out/r14/competition-three-1280.png`,
`review-no-chooser-1280.png`, `vision-one-action-1280.png`.

## §29 — The OpenDesign loop: the design board, and how a redesign comes back (2026-10-04)

The owner asked to sync the design into OpenDesign so the console can be annotated and redesigned there.
OpenDesign runs on this host as a user service (`open-design-daemon` + `open-design-web`, daemon
`http://127.0.0.1:7457`, UI on port 5174 and at `https://design.yay.how`), and the sync bridge is
`~/projects/opendesign-sync` (`odsync`).

### 29.1 What was created

| | |
|---|---|
| OpenDesign project | `corner-pocket-ops-console` — named `Sync Current Design Opendesign Workspace`, `linkedDirs: ["/home/haoye/projects/pool"]`, the same shape the owner's projects for `mergecrew` and `yaydesk` have |
| the artifact | `corner-pocket-ops-console.html` — **the whole UI**: **26 states over 7 screens**, EN + 中文, 190 kB (110 kB of the shipped stylesheet inlined + 76 kB of captured markup), digest `b8573950…`. Created with `od artifacts create --name … --input … --project corner-pocket-ops-console --daemon-url http://127.0.0.1:7457`, then kept current with `node docs/opendesign/capture.mjs --push` (the daemon updates the same file in place through `POST /api/projects/<id>/files`) |
| the repo side | `docs/opendesign/make_board.py` generates `docs/opendesign/corner-pocket-ops-console.html` (the repo's `.gitignore` reserves any `design/` directory for third-party references, so the board lives beside the docs); the tokens are **read from `annotator/ops.css`**, so the board shows the shipped values rather than a copy |
| the link | `odsync link corner-pocket-ops-console --repo /home/haoye/projects/pool --name corner-pocket` → `odsync doctor` all green after the first pull; `odsync status` reports `od=3f2ba384 mirror=3f2ba384` |
| the mirror | `.od-sync/design/` (`corner-pocket-ops-console.html`, `DESIGN-HANDOFF.md`, `DESIGN-MANIFEST.json`) and `.od-sync/implemented/` for write-back; `.od-sync/` is gitignored, as it is in the owner's `sona` repo |

### 29.2 What the board contains: the entire UI, captured

The board is not a redrawing and not a screenshot sheet: **every frame is the markup the shipped console
renders**, captured by booting the app inside the test suite's own sandbox (`tests/test_ops.js`'s `harness()`)
and calling the same functions the browser calls. `docs/opendesign/capture.mjs` writes one frame per state:

| screen | states captured |
|---|---|
| Tournament | idle (no night), registration, active with a match on table 2, complete, the results sheet, event settings (locked dialog), the first-run dialog, the second chance, the pending score, active in 中文 |
| History | the list (nights and broadcasts under one head), the empty state, a night's review, the list in 中文 |
| Regulars | the roster with each row's standing, one player's record modal |
| Back room | notes, appearance and the maintainers fold; in 中文 |
| Shot timer | the timer page with the match it follows |
| Shell | the destinations + phone bar + clock (`tabbarHTML()` + `clockHTML()`), and the printed header of `ops.html` |
| Vision | the live panel (EN + 中文), the live workbench, the recorded review workbench, the Twitch sources dialog |

The stylesheet is inlined byte-for-byte from `annotator/ops.css` with **one mechanical rename**,
`#ops-shell` → `.od-shell` (**772** occurrences), so each frame is scoped and no id repeats; because the
phone media queries come along, a frame shows its 390 px layout when the board is narrowed. Regenerate and
push with `node docs/opendesign/capture.mjs --push`, then `odsync pull corner-pocket`. Verified in a browser:
26 `.od-state` frames, the real tokens applied (`--line` `rgb(41,35,31)`, `--panel2` `rgb(17,14,11)`, the
brass `rgb(204,166,50)`), no horizontal overflow at 1440.

### 29.3 The loop

```
annotate / redesign in OpenDesign (https://design.yay.how · project "Sync Current Design …")
        │
        ▼   ~/projects/opendesign-sync/bin/odsync pull corner-pocket
.od-sync/design/…            (read-only mirror + DESIGN-HANDOFF.md, the visual contract)
        │
        ▼   implement in annotator/ops.{js,css} · annotator/vision-stage.js · tests
        │
        ▼   odsync push corner-pocket        (files staged in .od-sync/implemented/)
```

Limits: the frames carry the **test fixtures**, not the club's data (a frame is a state, not a night); the
live Vision stage is a runtime surface, so its frame is the skeleton the adapter fills; the server-side states
(offline, 409, 503) are behaviour and are not captured; the stylesheet's fonts are not inlined, so the board
falls back to the declared system faces; and the mirror is read-only for me until the owner annotates, while
`odsync push` replaces OpenDesign files, so the habit is to pull first and report before pushing.

## §30 — Round 15, item ①: the opened broadcast drives the workbench (2026-10-04)

**What was wrong.** The review engine (`annotator/app.js`) picks its dataset on load: `vod30` if the workbench
has one, else the first dataset (line 396). Nothing told it which broadcast the operator had just opened, and
round 14 had removed the clip chips from a recorded review, so a historical broadcast opened on whatever
dataset happened to be first.

**What now happens.** `syncReviewDataset()` (in `annotator/ops.js`, called from the 200 ms tick while a review
is open) waits for the workbench to list its datasets, maps the opened broadcast through the existing
`broadcastVodId()` → `datasetForVod()`, and hands that id to `window.CornerPocketReview.setDataset()` **once**
per review. An operator who switches afterwards is not fought, and the engine's own default still governs the
live tab, where no broadcast was opened.

**When no frames exist, the console says so.** After three passes without a dataset for the broadcast — or with
none listed at all — it prints one line: *No frames for this broadcast yet — import it from Broadcasts, then
its scrubber appears here.* A blank strip and a stage asking for "a moment on it" was a dead end.

**Verified.** `node --test tests/test_ops.js` **169/169** (two new instruments: the happy path hands over
`tw-2890514774` exactly once, and the no-frames path explains itself exactly once, not on every tick),
`node tests/test_app_timeline.js` **81/0**, `node --test tests/test_board.js` **16/16**. Measured live on both
servers: production's workbench lists **no** datasets and the isolated root's lists `['vod30','highlight']`, so
neither has an imported broadcast and the notice is what an operator sees there. The switch itself needs a
broadcast whose frames were imported (the Broadcasts block), which is why the acceptance for this item is the
synthetic `tw-` dataset in the test rather than a live screenshot — stated here rather than dressed up.

**Items ②③④ of the same order are not in this commit.** The recon is done and the seams are known, so the
next round starts from facts rather than from reading:
② auto-inference on pause: the engine already exports `freeze` and `runInference`, and carries
`inferRunning` / `inferStatus` / `inferTimer` in its state, so the work is a pause hook plus a progress read in
the stage chrome (`vision-stage.js`), not new machinery.
③ a label box on every track: the engine exports `selectTrack`, `setSeed`, `seedIdentity`, `clearIdentity` and
the enrollment pair, and `vision-stage.js` already renders each track as a `.vs-item` button (line 616), so
this is a control per row wired to callbacks that exist.
④ the playfield constraint: detection runs through `annotator/pipeline_stages.py`'s `TableStage`, which prefers
the saved `src/calib_segments.py` artifact and otherwise measures (the quad search lives in
`src/candidate_scan.py`, with an occlusion gate via a person-box share), and `src/eval_table_detect.py` is the
eval to score against. The 9 ft dimensions (100″ × 50″ playfield, 4.5″ corner and 5″ side pockets) and the
parallel-pair invariant belong in that candidate ranking as a physical score term — a detector change measured
by its own eval, not a front-end edit.

## §31 — Round 17, item ③: the face box reaches the stage, and one human keeps one box (2026-10-04)

**What the operator asked for.** Assign an identity whenever a face is visible; draw the face box if it is
a separate box; keep exactly one box per human; and keep the labelling sidebar consistent per track type.

**What the pipeline already had.** The person pipeline matches a quality face to each tracked person on its
stride frames. It now carries that face's box and quality in the person record (`face_bbox`,
`face_quality`), and the API's `_PERSON_FIELDS` publishes both.

**What the stage does.** Each loaded frame asks `/api/identity/frame` for the frame it is showing. The
request runs **after** the paint and is never awaited with the frame: the first call after a server restart
takes **50 s** while the identity models build (measured), and a frame must not wait for that. The persons
layer prefers the unified detection when it has people, and otherwise draws the identity record, so no
person is drawn twice. The face box is one dashed box tied to that person's own track (`data-face-for`),
with `pointer-events:none` and no `data-person`: it cannot be selected, edited or counted as a second
human. **One human, one box, with the face shown inside it.**

**Measured, live, on production** (`tw-2890514774`, frame 0, after the restart): the overlay holds
**3 `u-person` groups and 2 `u-face` groups**; the identity endpoint answers 200 with 3 persons, 2 of them
with a face box (track 3 `bbox [280,60,385,280]` with `face_bbox [303,67,330,104]`); `vod30` frame 8100
gives 3 persons and 2 face boxes. Screenshot: `out/r17/face-boxes-1280.png`.

**Two defects found by measuring, both fixed.** ① The restart exposed `KeyError: 'face_bbox'` at
`unified_server.py:521` — the server projects every person through a fixed field list, and the pipeline only
set the new keys when a face matched, so **every** identity frame answered 400. The pipeline now always
emits both keys and the projection reads with `get()`. ② The identity fetch was awaited beside the frame
result, which would have held the picture for those 50 s. Both fixes are committed with the measurement in
the message.

**Known limit, stated rather than hidden.** The track rows show the binding when the row's track id exists in
the frame's identity record. On a recorded broadcast the sidebar's rows come from the analysed tracklet file
and the identity record's ids come from the live pipeline, so the two id spaces do not meet there and the
rows render no binding chip (measured: `rows: 3`, `chips: []`). The face boxes still draw, the inspector
still labels the selected track, and on a source where both spaces are the pipeline's own the chip appears.
Matching across two id spaces by box overlap would guess, so it is not done.

**The labelling row.** Every human track carries the same control set the inspector shows — the roster
select, the guest field and Clear — because a form control cannot live inside a `<button>`, each row is a
`div` whose select action is its own button, and a control inside a row selects that row's track first.
Verified live: 3 tracks → 3 rows × (select, input, Clear).

## §32 — Round 17, items ① and ④: the constraint reaches the live stage, the wizard loses five screens (2026-10-04)

**The constraint now speaks from the live pipeline.** `annotator/pipeline_stages.py`'s `TableStage` — the
stage the running processor uses, which prefers the saved segment reference and otherwise measures every
`measure_every_n` frames — checks the polygon it is about to publish with `src/playfield.py` and adds
`table_playfield` to the result and to `evidence()`: `{ok, reasons, best_parallel_deg, aspect}`. A detection
is never thrown away and a constraint can never stop a frame (the check is wrapped, and a polygon that is not
a quad answers `None`). Four cases in `tests/test_live_processing_stages.py` hold it: a venue-shaped polygon
passes, a square claim is refused with `aspect-too-square`, an empty or non-quad polygon answers without an
exception, and the verdict travels in the stage evidence (`22 tests OK`).

**Scored with the eval.** `PYTHONPATH=. .venv/bin/python src/eval_table_detect.py --detector naive
--frames-vod30 6 --frames-highlight 3` ran in 2.4 s and wrote `out/table-detect-eval/naive.{json,txt}`:
`vod30` vs `app-anchors@70.0s` → median **86.86 px**, p90 **92.62 px**, `accept@40` 0.0%; `highlight` vs
`fixed-corners` → median **43.52 px**, p90 **68.55 px**, `accept@40` 50.0%. Read this as the no-regression
baseline it is: the constraint labels and penalises a quad, it does not move the naive detector's corners, so
these numbers are the same before and after. Making the verdict *steer* the candidate choice is a detector
change with its own measurement, and it is the next step rather than a claim here.

**The backfill is three screens.** The wizard kept eight states and showed eight pages; it still keeps every
state, and now shows three screens: **① 选片** (choosing a broadcast and verifying it — the verification panel
appears as soon as one is chosen), **② 导入并标注** (the import's progress is a header over the marking
canvas, with the night's own fields above it), **③ 确认** (done, failed and rejected are banners on the screen
they land on, with the reason and the resolving action beside them). Every panel is guarded by the state it
needs, because one screen now carries up to three of them. Measured in the browser: opening the wizard from
History renders **"Step 1/3"**, `data-screen="1"`, `data-step="pick"`, and **no raw word key** appears on the
page.

**One line for the ingestion.** `bfProgressLine()` renders the running job's percent, rate, remaining time
and the broadcast's name, and History carries it in `#ingest-line` beside the download line, so nobody opens
the wizard to find out; the line is empty when nothing runs, and its button uses the action that already opens
the wizard. Measured: `#ingest-line` is present on History with no text while idle.

## Round 30 · the scrubber owns the layer row (2026-10-06)

The layer chips and the source label were a bar of their own above the picture. They are now the
first cell of the scrubber component at the bottom, together with the shot clock and the identity
span, so the chips, the source label, the frame transport, the track and the facts line are one
bordered component. No separate row was left behind (`vs-stagebar` is gone from the markup and the
stylesheet).

Measured on the review screen at http://127.0.0.1:8130/ops.html#/records/review/2853972244:

- `.vs-stagebar` 0, `.vs-strip` 1.
- `#vs-layers` sits inside `#vs-strip` and is the first child of `.vs-transport`.
- The transport row reads `vs-layers`, frame input, step back, step forward, freeze, play, clock,
  identity (height 54 px; the strip is 138 px).
- The four layer chips read `cloth 0 (+1 manual)`, `balls 10`, `persons 4`, `pockets 6`, all inside
  the strip box.
- The source label inside the strip reads `recorded broadcast of ttpoolfriday · from 2026-08-23 ·
  whole broadcast`; the facts line reads `broadcast time 0:00:00 · 0:00.0 · overlays ON`.

## Round 31 · the review player owns the gesture (2026-10-06)

The owner asked for a player whose scrubbing and jumping work. While the pointer is down the stage
previews the chosen point in place, and the engine queues a point that arrives while a frame decodes.

| What the operator does | What the console does | Measured |
| --- | --- | --- |
| Drag the scrubber | The thumb holds the point, a bubble states the time, the layer chips stay inside the scrubber | 10 of 10 drag steps tracked, `held` 1, `trackHeld` 1, bubble hidden on release |
| Release the scrubber | One seek for the last point, queued when a decode runs | 974 s to frame 29214, 23372 s to frame 701166 (30 fps) |
| `l` `j` `Home` `ArrowRight` on a focused scrubber | +5 s, -5 s, start, +0.1 s | `Home` then `ArrowRight` settles at frame 1, `t` 0 |
| `k` | Play, then pause | play to frame 589 (`t` 20 s), one pause |
| Click a step button | One frame | 595 to 596 |
| Hold a step button | Repeats after 350 ms, then each 90 ms, at most 120 steps | 596 to 603 in 1.4 s, 7 frames |

Two defects were measured and fixed in `annotator/app.js`:

- `seek()` read `canLeave()`, which refuses while a decode runs. The queued-seek branch under it was
  therefore unreachable, and a point chosen during a decode was dropped. Measured before the fix: a
  5:11:38 thumb over a 4:03:28 picture. The unsaved-changes half of the guard still refuses.
- `stepFrame()` read `canLeave()` too, so every tick of a held step button was a no-op. Measured
  before the fix: 0 frames walked. After: 7 frames in 1.4 s.

Environment: the review record `2853972244` resolves to a 10.8-hour Twitch VOD. Frame extraction takes
seconds per frame and the first load can take minutes, so the picture lags the input; the queue keeps
the last choice.

## Round 32 · the architecture review (2026-10-07)

An architecture review of the console and the service named twelve candidates. Ten shipped in five
commits. The owner skipped the two speculative ones. Each row states what the seam was, what it is
now, and the number that proves it.

| # | Candidate | Before | After | Measured |
| --- | --- | --- | --- | --- |
| c1 | The review workbench is one module, not a string protocol | `annotator/ops.js` authored 18 `id="vs-…"` elements and read the stage's own `vs-frame` id | The stage builds the whole shell from its markup; the console hands over a host, a heading, one loading line, and the picture host as the `frameHost` option | Element ids across the seam: 18 out and 1 in before, 0 and 0 after. `#vs-cues` 2058 characters, scrub maximum 38953.943, the picture host parent is the frame region |
| c2 | Close the engine's interface | 73 keys in the literal, 72 live, and a test that demanded 72 | A `net` seam replaces three direct fetches; `attach({mount, fetch})` returns a handle | Published surface 68 keys, five dead keys removed (`selectStageBall`, `cycleVerdict`, `loadCrops`, `loadSeeds`, `loadEvents`) |
| c3 | Each screen is a module that owns its own paint | `render()` at `annotator/ops.js:887` repainted all six screens; `pollOps()` guarded by seven terms | `screenModule(id, build, spec)` returns `{id, root, mount, update, detach, mayRepaint}`; `screenModules` holds the six tab ids; the poll guard is `!busy && !pendingMatches.size && registry.mayRepaint()` | Per tab `{buttons, main text, main children, main sections}` stayed the same across the change: clock 32/158/1/1, tonight 28/260/1/1, records 63/7822/1/1, vision 26/90/1/1, players 36/678/1/1, status 26/1414/1/1 |
| c4 | The tests drive seams instead of reading source text | `tests/test_app_timeline.js` held 89 assertion lines with 105 `includes` calls, and 526 over the whole file | 103 `assertSourceContract(file, snippet, why)` call sites, each printing its claim on every run | Inline source-text assertion lines 0; 157 claims at first, 155 after two of them moved to the suite that builds the shell; tests 88 → 90 |
| c5 | One named tournament interface, not `post(action)` | `post()` dispatched 30 action names and 25 private helpers by name, and the audit was read by name prefixes | `Operation(name, apply, audit, requires, refuse_missing_first)`, `operations_registry()`, 34 rows in `OPERATIONS`, `run(state, payload)` as the only caller of `_apply` | `tests/test_operations.py` 65 OK; a mis-declared row cannot half register (7 bad rows refused) |
| c8 | The Vision adapter has one seam | `window.VisionStage` published 28 names; production called one of them | `window.VisionStage = {attach}`; every renderer is private | Browser: `window.VisionStage` reads `["attach"]` |
| c9 | Stop rewriting `annotator/app.js` to reach inside it | The suite rewrote the source with `source.replace(/\}\)\(\);\s*$/, …)` and injected 69 internal names | The suite runs the source in a sandbox and takes the handle that `attach()` returns | `grep -c "source.replace"` = 0 |
| c10 | One registry for an operator action | The client, `annotator/operations.py` and `annotator/unified_server.py` each held their own list of write actions | `OPERATOR_ACTIONS` holds 21 rows, one per write URL, and `GET /api/actions` serves the same table to the client | All 7 client POST paths have exactly one row; no orphan rows; 30 of 34 operation names are called by the client or the tests |
| c11 | Hand the clock over instead of forging a `StorageEvent` | `annotator/clock-sync.js:442` forged a `StorageEvent`, because `annotator/ops.js` is one IIFE that exports nothing | `annotator/ops.js` publishes `window.OpsClock.receive(value)` and keeps its real `storage` listener | Forged events 1 → 0. A perturbation that puts the forged event back fails 2 tests |
| c12 | Fold the store pass-through and the path it leaks | `_StoreOperations` forwarded calls from `annotator/unified_server.py:319` to `annotator/operations.py:124` | `Store.place(kind, key=None)` is in the protocol and in both backings; `Backend.operations()` returns the store | Every `type(...).__name__ ==` test is gone from the server. `tests/test_unified_server.py` 76 OK, `tests/test_board_api.py` 21 OK (2 skipped), `tests/test_vod_import.py` 32 OK |

### The five commits

| Commit | Candidates | Subject |
| --- | --- | --- |
| `07973dd` | c12, c5, c10 | store: the store owns the operations interface, and one registry names each action |
| `2452d94` | c8, c9, c2 | console: one seam for the stage adapter, one mounted seam for the engine |
| `c763069` | c3 | console: each screen is a module that owns its own paint |
| `a17f259` | c4 | tests: the review suite drives seams instead of reading source text |
| `a113933` | c11, c1 | console: one named seam for the clock, one host for the workbench |

A commit carries more than one candidate when the candidates share a file. The message of each
commit names its candidates and holds the measurements for each of them.

### A defect this round found in its own test work

The helper at `tests/test_app_timeline.js:120` asserted `assert.ok(opts.absent !== found, …)`. For a
claim about a needle that must be present, `opts.absent` is `undefined`, so the comparison was true
whatever the source said. 138 of the 157 claims proved nothing while the suite stayed green. The
repair is `assert.ok(opts.absent ? !found : found, …)`. Two claims then failed, and both named the
wrong file: the inspector's scroll region is authored by the stage, and the 中文 footer copy lives in
the `zhCopy` table in `annotator/app.js:1951`.

The proof that a claim bites needs a replacement that does not contain the needle. Replacing all 53
`#t-overlay` rules in `annotator/app.css` with `.zzz-overlay` prints 2 failures; restoring the file
prints 90 passed and 0 failed. Changing `#t-overlay` to `#t-overlayX` proves nothing, because the
needle still matches inside the longer string.

### What still stands open

- c6 (group the 93 handlers of the service) and c7 (give the backfill wizard its own module) were
  speculative. The owner skipped both.
- c2: the engine handle still exposes 55 readings that the tests call directly (`T.paintOverlay` 42
  references, `T.applyFrameResult` 12).
- c3: `render()` still repaints the nav, the tabbar, the clock slot and the shell. The backfill
  wizard and `paintArchive()` / `paintAuto()` paint outside the registry.
- c4: 155 source contracts remain: `annotator/vision-stage.js` 95, `annotator/app.js` 19,
  `annotator/ops.css` 18, `annotator/app.css` 15, `annotator/ops.js` 4, `annotator/app.html` 4. The
  timeline harness has no `insertAdjacentHTML`, so the shell's markup can be claimed only in the ops
  suite.
- c10: `entrant_absence` and `match_absence` are posted by tests only. The console stopped sending
  them when round 13a removed the attendance UI. They stay, because a server contract can have
  callers outside this repository.
- c1: a controlled run of the build before the change put the picture host in the frame region too,
  because a later `render()` pass repeated the placement. The old code was therefore not a visible
  defect. The change closes the seam; it does not repair a picture.

### The numbers for the round

- Python: `Ran 1321 tests in 213.9 s`, `OK (skipped=51)`.
- JavaScript: `tests/test_ops.js` 195 pass and 0 fail (191 before), `tests/test_app_timeline.js` 90
  passed and 0 failed (88 before; one test sat after `process.exit` and never ran),
  `tests/test_board.js` 16 pass and 0 fail.
- Browser at http://127.0.0.1:8130/ops.html with `ops.js?v=vision-stage-61`, buttons | main text
  characters: clock 32|158, tonight 28|260, records 63|7826, vision 26|102, players 36|678, status
  26|1414. The console log and the error log are empty after a walk of all six tabs and a review
  session.
- File sizes: `annotator/ops.js` 1268 → 1280, `annotator/vision-stage.js` 1682 → 1741,
  `annotator/app.js` 2134 → 2168, `tests/test_ops.js` 4384 → 4629, `tests/test_app_timeline.js` 2879
  → 3166, `annotator/operations.py` 1035 → 1259, `annotator/unified_server.py` 2416 → 2559.
- The Postgres half of `tests/test_store_contract.py` ran against a real server: 59 OK, and it left
  no schema behind.

### Environment

The console under test is http://127.0.0.1:8130/ops.html, served by the systemd user unit
`pool-workbench.service`. The browser walk used one browser, one viewport 1280 px wide with 599 px
inner height, and one recorded match (`2853972244`, a 10.8-hour VOD). Frame extraction takes seconds
per frame, so the picture lags the input. `curl` is refused by a host hook, so the live checks used
`.venv/bin/python` with `urllib.request`.

## Round 33 · the architecture review, the second pass (2026-10-09)

A second architecture review, `/tmp/architecture-review-20261007-123400.html`, named eight
candidates. All eight shipped in six commits. Each row states what the seam was, what it is now,
and the number that proves it.

| # | Candidate | Before | After | Measured |
| --- | --- | --- | --- | --- |
| 01 | One canonical frame | `src/table_geometry.py`, `src/event_gates.py`, `src/scan_events.py` and `src/rebuild_events_v2.py` each held `CANON_W`, `CANON_H` and `POCKETS_MM`, and three of them wrote their own `nearest_pocket`. The rebuild held a fifth copy, and that copy was transposed | `src/table_geometry.py` is the only definition site: `CANON_W` :20, `CANON_H` :21, `POCKETS_MM` :25, `nearest_pocket` :35, `homography_to_canonical` :45. The other modules import the names | Definition sites 4 → 1, `nearest_pocket` 3 → 1. The rebuild edge TL → TR measures 2540.0 mm before and 1269.0 mm after. The pocket name changes for 0 of the 10 committed pot rows: row t=81.0 moves from [2126.6, 1206.4], foot-right 418 mm, to [1062.5, 2411.9], foot-right 244 mm |
| 02 | One time-resolved calibration seam | Fifteen functions in eight modules rebuilt the same chain and picked an entry themselves. `src/motion_scan.py:294` read the artifact itself, `:297` took `segments[0]`, and the note at `:300-301` said that the per-time lookup belongs to the calibration | `src/calib_segments.py` is that seam: `read()` at :317 is the only parser of the artifact layout, and `resolve()` at :493 returns a `Reference` with the quad, the file, the entry inside it and a per-time flag, through the chain `KINDS = ("supplied", "segment", "static", "prior")` at :79. `REFUSED = "corners_30min_v2.json"` at :59 guards the recorded decision | Loader functions that parsed a calibration artifact 15 → 0, and three of them are deleted outright; raw `json.load` / `read_text` / `open` sites over the ten reader files 99 → 69; seam call sites 19; lines that name `calib_segments` 18 → 61; `src/motion_scan.py` 2525 → 2467 lines with its `load_quad` chain 87 → 21; tests 16 → 34; python `Ran 1353 tests`, OK (skipped=51) |
| 03 | One dataset registry | Thirteen modules built a media path by hand from the repository root and the dataset id, so each one knew the artifact layout | `src/datasets.py:175` `media_path(root, dataset_id)` and `:186` `media_relpath` answer that question | Hand-built media path literals 41 lines in 38 files → 26 lines in 24 files. `src/motion_scan.py` names the sample `vod_30min_260815` 0 times |
| 04 | The mounted seam the engine got | `annotator/ops.js` published one global, and the suite rewrote the source text in four places to reach the console's own names | `attach(options)` at `annotator/ops.js:1341` returns one handle, and `:1356` publishes `window.OpsConsole = {attach, setShell, publishShell, shellState}` | Source-text rewrites before boot 4 → 0. The suite runs the file as the page loads it and mounts the console with `window.OpsConsole.attach({document})`. The browser reads 4 keys |
| 05 | One paint owner for the console's own DOM | `paintArchive()` and `paintAuto()` both painted the records region of `#main`, with 7 call sites | `paintRecords()` at `annotator/ops.js:197` owns that screen, and `screenModule()` gained `paint()` at `:900` | Definitions 2 → 0, call sites 7 → 0, and `node tests/test_ops.js` 195 → 197 pass with 0 fail |
| 06 | The engine handle publishes a scenario | The handle carried the engine's private `state` object, named by 60 keys | `frame(result, edits)` at `annotator/app.js:2120`, `scene(patch)` at `:2129`, the named readings at `:2139`, and the handle tail `frame, scene, ...readings` at `:2200` | `attach()` names 91 keys, 61 named plus the 30 readings. Lines that name `T.state` 302 → 0. `window.CornerPocketReview` holds 68 keys, and `'state' in window.CornerPocketReview` is false |
| 07 | One vocabulary for the shell state | The stage named the console's element by id, `annotator/vision-stage.js:1128` `document.querySelector('#ops-shell')`, and `render()` at `annotator/ops.js:916` wrote the attributes itself | `shellState` at `annotator/ops.js:926`, one writer `publishShell` at `:927` for all five attributes, and `setShell` at `:928` as the only patch path. The stage calls `OpsConsole.setShell` | Mentions of the shell id in the stage 1 → 0. Attribute write statements 2 → 5, all in one function. `setShell({vsPanel:true})` changes the review grid from 280px 1204px to 280px 872px 320px, and back |
| 08 | Enrolment uses six names, not fifty-two | `src/enroll_from_tracklet.py` imported `src/person_pipeline` at load time, so an import pulled torch, cv2, argparse and ultralytics | The module names the six objects it uses and keeps `PersonPipeline` inside the two functions that need it, `scan_frames` :518 and `_infer` :1385 | File 1483 → 1520 lines, tests 1068 → 1105, with a fresh interpreter that finds no torch, cv2, argparse or ultralytics |

### The six commits

| Commit | Candidates | Subject |
| --- | --- | --- |
| `987f68c` | 01 | geometry: one canonical frame for the table, the quad and the pockets |
| `14b4352` | 03 | datasets: one registry says where a dataset's media lives |
| `f2cd950` | 06 | console: the engine handle publishes a scenario, not its state |
| `3ba5683` | 04, 05, 07 | console: one vocabulary for the shell, one paint owner per screen |
| `dfc19d6` | 08 | enrol: the enrolment module imports only the six names it uses |
| `f5010c7` | 02 | calibration: one seam answers which reference belongs to a time |

One commit carries three candidates because they share `annotator/ops.js` and `tests/test_ops.js`.
The message of each commit names its candidates and holds the measurements for each of them.

### Two defects the measured check found

The browser check of the review route found two defects, and both are older than this round.

The 200 ms tick called `syncReviewDataset()` before the night list arrived, so `broadcastVodId()` at
`annotator/ops.js:420` read `history` of a null `data` and threw
`TypeError: Cannot read properties of null (reading 'history')`. The tick now waits for `data`. The
old code sits at `HEAD` too, so the defect was not a product of this round.

The `hashchange` handler cleared `reviewId` before it asked `canNavigate()`. A refused navigation
therefore lost the review and its address: the handler wrote `#/records` and dropped the review id.
The handler now compares the next route with the current one first. The browser shows the repair:
after a move to `#/records` the shell review flag reads `0` and `#main` holds 29898 characters.

### What still stands open

- Candidate 02 shipped in `f5010c7` after this record was first written, so the numbers it names moved:
  `calib_segments` now appears on 61 lines, 19 call sites go through the seam, and three former
  loaders no longer exist. Five `load` call sites stay outside the card's scope: `src/table_refine.py`
  twice, `annotator/` twice, and `annotator/pipeline_stages.py:331`.
- Candidate 02 left `src/table_refine.py`'s own prior table and unknown-dataset gate alone, because its
  chain differs from the seam's chain and the card does not name the file.
- Candidate 01 covered the four modules that held the frame, and it left three other frame copies in
  place because they are outside its scope: `src/audit_calib.py:21-22` holds a landscape
  `TABLE_W, TABLE_H = 2540.0, 1270.0` with its own destination, `src/calib_vod30.py:30` holds an
  inline portrait destination, and `src/pipeline.py:28` re-exports the names through a flat import.
- Candidate 01 changed the artifact that `src/rebuild_events_v2.py` writes, so the round ran it.
  `out/scan30/events_v2.json` now holds the same 67 events, 57 shots and 10 pot rows with the same
  ids, and its pocket distances read 244, 246, 336, 336, 338, 386, 431, 493, 498, 696 mm, where the
  artifact of the landscape frame read 345, 349, 389, 418, 419, 439, 440, 440, 634, 1133 mm. 7 of the
  10 rows now sit within 440 mm, and the round-4 line in `docs/state.md` claimed 440 mm for all of
  them. Three rows still sit above 440 mm, and a correction section at the end of `docs/state.md`
  records both sets of numbers.
- Candidate 08 closed the import side of the enrolment module. The exported surface of that module
  still holds names that no caller uses.

### The numbers for the round

- Python: `Ran 1335 tests in 134.951 s`, `OK (skipped=51)`, and `Ran 1353 tests in 108.990 s`, `OK
  (skipped=51)` after candidate 02 added 18 tests.
- JavaScript: `tests/test_ops.js` 197 pass and 0 fail (195 before), `tests/test_app_timeline.js` 90
  passed and 0 failed, `tests/test_board.js` 16 pass and 0 fail.
- The events rebuild prints `57 shots, 10 pot rows, 67 events`, `linked: 10/10  causality violations:
  0  unlinked: 0`, `window drops: [2, 2, 2, 2, 1, 1, 1, 2, 2, 1]` and
  `pocket dists mm: [244, 246, 336, 336, 338, 386, 431, 493] ...`.
- The browser at http://127.0.0.1:8130/ops.html#/records/review/2853972244, viewport 1596 by 1045,
  loads `app.js?v=vision-stage-64`, `vision-stage.js?v=vision-stage-62`,
  `ops.js?v=vision-stage-65` and `clock-sync.js?v=clock-sync-2`. `window.OpsConsole` reads
  `[attach, setShell, publishShell, shellState]` and `window.VisionStage` reads `[attach]`. The
  shell element carries its attributes. `#vs-cues` holds 18570 characters in 86 buttons, `#vs-scrub`
  reports 38953.943, and the error log and the console log stay empty.

### Environment

The console under test is http://127.0.0.1:8130/ops.html, served by pid 1192095. That process
started on 2026-10-07 at 02:50, so it serves the JavaScript of the working tree but the Python of
that morning: every Python change of this round is proved by unit tests, not by the live service.

The browser walk used a raw DevTools-protocol driver. The `agent-browser` daemon cannot write its
socket under `/run/user/1000`, and Chromium hangs on the D-Bus keyring before its first network
request until it starts with `--password-store=basic`. `/dev/shm` is also closed to it, so the driver
adds `--disable-dev-shm-usage` and `--no-zygote`. One browser, one viewport, one recorded match.

## Round 34 · the architecture review, the third pass (2026-10-09)

A third architecture review, `/tmp/architecture-review-20261009-1713.html`, named seventeen
candidates. Two read-only walks supplied them: nine for the console
(`/tmp/dshsess/walk_console_round34.md`) and eight for the service
(`/tmp/dshsess/walk_service_round34.md`). A third walk covers the service routes
(`annotator/unified_server.py` and `annotator/pipeline_stages.py`), which the second walk left out
while the calibration seam was still moving. Each row states what the seam was, what it is now, and
the number that proves it.

| # | Candidate | Before | After | Measured |
| --- | --- | --- | --- | --- |
| C3 | The stage takes the shell writer as an option | `annotator/vision-stage.js` read `window.OpsConsole.setShell` and patched the console's element from outside | The console passes `setShell` in the option bag it already hands `attach()` (`annotator/ops.js:1315`, the last line of the bag), and the stage calls `opts.setShell({labelOverlay, vsPanel})` at `annotator/vision-stage.js:1132` | Reads of the console global in the stage 1 → 0. `tests/test_app_timeline.js` 90 → 91 passed, `tests/test_ops.js` 197 → 198 pass. In the browser at 1596 by 1045 the shell reads `{labelOverlay 0, vsPanel 0}`; one real click on `[data-vs-action="select-track"]` moves it to `{labelOverlay 1, vsPanel 0}`; the error log and the console log stay empty |
| C1 | The composition path runs once, on a page-shaped stub | The suite never called `render()`: 42 calls were replaced and 0 were real, so no test proved that a screen reaches the page | `tests/test_ops.js` gained `domNode(selector)`, `richDocument(handlers)` and a `richDom` option that builds a stub page with one region per selector and records every `appendChild`, `classList`, `setAttribute` and `insertAdjacentHTML`. One test runs the real `render()` | The test observes `#nav` with `aria-current="page"`, `#tabbar` with the same destinations, the active screen in `#main`, `#vision-host` appended to the body, 0 timers on Tonight, the clock bar after a screen switch, and the shell state. `tests/test_ops.js` 198 → 199 pass, 0 fail |
| C2 | The stage publishes the interface the console drives | The console drove 48 engine verbs and read 27 snapshot fields through ad-hoc reads, and `window.VisionStage` published `{attach}` only, so the contract lived in the console's own prose and in its tests' source-text assertions (45 of them named `annotator/vision-stage.js`) | The stage defines its surface once, near the end of `annotator/vision-stage.js`: `OPTIONS` (20 names), `WIRING` (2: `mount`, `review`), `VERBS` (48), `READINGS` (27). `function publish(detach)` returns a handle of 7 + 48 + 27 = 82 keys (`render`, `detach`, `options()`, `verbs()`, `readings()`, `accepts(key)`, `option(key)`), with 48 forwarders `handle[name] = (...args) => engine()[name](...args)` and 27 readings `() => snap()[name]`. `window.VisionStage` stays `{attach}` on purpose | Source-text assertions about the stage 45 → 7; all source-text assertions in `tests/test_app_timeline.js` 100 → 65; the suite 92 → 93 passed, 0 failed. Measured corrections to the card: engine members are 48, not 52 (52 was `42 ∪ 10` with three overlaps, and `target.closest` at `:1597-1610` was a false positive of a local destructured event target); the 27 snapshot fields hold; no named `render*` function exists, so the card's "42 renderers" is not reproduced. A perturbation that renames `'enrollPreview'` inside `VERBS` fails exactly the interface test and restores byte for byte. The same commit repaired a latent defect this work exposed: the row guard at `annotator/vision-stage.js:1369` called `String(snapshot()…)`, but the module defines only `const snap = () => engine()?.snapshot ? engine().snapshot() : null;` at `:262`, so a node carrying `data-vs-track` with an attributing action raised `ReferenceError`. It now reads `String(s?.persons?.track ?? '')`, and a new test drives a track row and asserts one `selectTrackAndSeek` call; a perturbation that puts the undefined name back fails exactly that test |
| C10 | `screenModule` is shallow, and `render()` is one line | `render()` was one 2077-character line with 33 semicolons at `annotator/ops.js:943`, every paint step inline, and `screenModule(id, build, spec={})` took a spec object with three escape hatches (`paint`, `holds`, `release`) that a screen could use or ignore | `render()` is 18 lines at `annotator/ops.js:980-997` with 15 named calls, and 14 further steps are named at `:960-979` (`haltPolling`, `paintDocument`, `paintNav`, `paintTabbar`, `paintShellState`, `paintClockBar`, `mountVisionHost`, `paintActiveScreen`, `paintOverlays`, `paintReviewHost`, `armPolling`, `loadRecordsScreen`, `paintLanguageChips`, `paintThemeChips`). `screenModule(id, screen)` takes one screen object and applies `screenBase` defaults (`build` `''`, `paint` false, `holds` false, `release()`); the six screens declare their own: `clock` paints `paintClockSlot`, `tonight` holds, `records` paints `paintRecords`, `vision` releases through `releaseVisionAdapter`, `players` holds, `status` builds only. A dead `const m=live()` was removed | `render()` 1 line / 2077 characters / 33 semicolons → 18 lines / longest line 23 characters / 15 semicolons; spec escape hatches 3 → 0; rendered fragments 50 → 63 with 45 of 49 compared fragments in place. `tests/test_ops.js` 198 → 201 pass, 0 fail, with a new test at `:4747` that runs the real `render()`. Three perturbations bite: deleting the `paintThemeChips();` call → 200 pass, 1 fail; emptying its body → 199 pass, 2 fail; renaming `paintNav` → 196 pass, 5 fail with `ReferenceError`. The browser check re-ran the whole shell: 6 nav buttons with one `aria-current`, tabbar 1156 characters, `#main` 30515 characters, a theme chip flip to `light`, the 中文 chip to `zh-CN`, the clock screen 2089 characters, and the review route painting 3055 characters of label overlay from one track click, with the error log and the console log empty |
| S2 | A writer refuses a name it does not implement | `_do_match` and `_do_pairing` each ended in an unguarded `else` that WAS an action, so a row could borrow a writer it does not implement | The branches are named (`elif action in ('match_complete','match_forfeit')`, `elif action == 'pair_draw'`) and each writer ends with `raise ValueError(f'Unknown match action: {action}')` | Registry rows 34 → 22 writers, with `_do_match` 6, `_do_pairing` 5, `_do_entrants` 3, `_do_revival` 2. A live experiment registered `Operation('zzz_not_a_real_action', Operations._do_match, …)` and posted it: before the repair the match completed with a winner, after it the answer is `Unknown match action: zzz_not_a_real_action` and the match stays live with no result and no signature. `tests/test_operations.py` 65 → 68 tests; full suite `Ran 1356 tests in 110.994 s`, OK (skipped=51) |
| S3 | A source failure carries its code from the raise site | Thirteen English sentences mapped to nine codes in `_ERROR_CODES` and `_ERROR_PATTERNS`, far from the raises. `'Media decoder cleanup failed'` was reachable and asserted nowhere | `class _SourceError` carries `code` and params. In-process failures name their code where they raise (unsupported_kind, open_failed, frame_invalid, decode_failed, inference_failed), and `_fail` uses a carried code or falls back to the two tables for a sentence from the Twitch layer | `tests/test_live_processing.py` 31 → 34 tests; full suite `Ran 1359 tests in 247.403 s`, OK (skipped=51). Two perturbations bite: a raise without its code fails `test_every_in_process_raise_names_its_code`, and a wrong code on the open failure fails `test_a_failed_session_reports_the_code_its_cause_maps_to` |
| C5 | The clock seam carries the words and the language | The synchronisation half patched the console's markup from outside: it held a second copy of the label pair, read the language by matching rendered text, watched the whole body with a MutationObserver and polled localStorage for a written key | `window.OpsClock` carries four members (`words()`, `lang()` out, `sync()` in, `receive()` unchanged). The console paints the `.sync-error` line it already emits, and reports an accepted key through `clockTook()` | Label pair definitions 2 files → 1 (`annotator/ops.js:9`); `nodeLang` fallbacks 3 → 2; MutationObserver constructions in `annotator/clock-sync.js` 1 → 0; files that name `.sync-error` 3 → 2; every DOM write in the synchronisation half (textContent, createElement, className, appendChild, setAttribute, querySelectorAll, click listener) → 0. `tests/test_ops.js` 199 → 200 pass, 0 fail |
| C8 | The engine's snapshot is composed from named groups | `snapshot()` was one 72-line object literal with 29 top-level keys, and it declared `inferRunning` and `inferStatus` twice | Eighteen named builders compose it, and the duplicate keys are gone | `snapshot()` 72 → 8 lines; builders 0 → 18; duplicate keys 2 → 0; a sandbox loads the previous file and the current file and gets the same `JSON.stringify(snapshot())`, the same 29 top-level keys, the same 147 nested names, the same 68 window keys and the same 91 handle keys. `tests/test_app_timeline.js` 91 → 92 passed, 0 failed |
| C9 | The suite drives the seams instead of reading source text | 155 source-text assertions, 118 of them about `.js` files | 55 assertions now run the real path and read the result: the Chinese copy loops, the anchor layer, the queued seek of round 31, the scrub range | Source-text assertions left 155 → 100; `.js` assertions 118 → 63; call sites 101 → 79; the suite prints the count |
| S4 | One owner resets the session state | `__init__` named 54 fields and `start()` named 38, overlapping but not equal, so a field could be reset in one place and forgotten in the other | `_reset_session(stages=(), *, source=None, detectors=(), state='idle')` at `annotator/live_processing.py:268` owns every session field (37 fields in 46 lines); `__init__` keeps the configuration a caller gave it and calls the reset, and `start()` keeps four names | `__init__` 55 lines and 54 names → 29 lines and 18 names; `start()` 57 lines and 38 names → 37 lines and 4 names; `tests/test_live_processing.py` 34 → 38 tests OK. A perturbation that puts `self._last_drop = None` back into `start()` fails exactly the new ownership guard and leaves the other 37 green. One deliberate change: after a start a stage refuses, `status()['detectors']` is empty instead of the refused list, which is the rule the module already states at `tests/test_live_processing.py:96-109` |
| S5 | A row declares the record it audits | `_audit_group` keyed the audit identity by action-name prefix and fell back to the last row of the collection when the payload named nothing; four rows used the fallback | `Operation.record = Record(collection, field)` names the one row, and each writer hands back the row it made, changed or removed; a write that names no row either way is refused | Rows that declare a record 17 of 34; `_audit_group` occurrences 1 → 0; the audit document stays byte-identical for seven cases (sha1 `26fb7428…`); `tests/test_operations.py` 68 → 73 tests OK. One deliberate change: `entrant_add_late` is audited as the late entrant, not as the rival it brought |
| S6 | One write resolves the registry once | `run()` looked the row up, the audit read it again, and two actions were excluded by a two-name tuple written at the call site | `_apply` holds the one lookup, the refusal, the audit and the write; `audit_before_write` is a row field | `run()` 21 → 10 lines, `_apply` 7 → 20; `OPERATIONS.get` call sites in the write path 3 → 1; registry lookups per write 4 → 1; audit reads per write 2 → 1; rows with `audit_before_write` true = 3 (pair_accept, revival_undo, tournament_delete); `default_name()` call sites 1 → 2 |
| R1 | One vocabulary says what a detector is called | Three lists named the detectors: an inline tuple in the per-frame route, `LIVE_DETECTORS` in the live pipeline, and three string tests in the stage factory. The factory dropped a name it did not know, so `['table','person','balls']` built two stages | `DETECTORS` at `annotator/pipeline_stages.py:690` holds one row per detector with every spelling a caller may use; `resolve_detector`, `resolve_detectors`, `frame_detectors` and `default_stages` read that table, and the route validates through it | Five inputs: `['balls']` `[]` → one causal ball stage; `['bal']` `[]` → `unknown detector 'bal'; accepted names: table, person, ball, balls`; `['table','person','balls']` two stages → three; two inputs unchanged. The per-frame route accepts one more spelling: `['ball']` answered 400 and now answers 202, translated to `'balls'`. `tests/test_live_processing_stages.py` 22 → 28 OK; `tests/test_unified_server.py` 76 → 80 OK |
| S7 | One registry says where a built-in recording lives | The live pipeline held its own detector tuple, `LIVE_DETECTORS = ('table', 'person', 'ball')` at `annotator/live_processing.py:33`, and the live pipeline and the enrolment module each spelled a built-in recording file name | `LIVE_DETECTORS = detector_names()` at `annotator/live_processing.py:38` reads the one detector vocabulary at `annotator/pipeline_stages.py:697`, and `_DATASETS` reads `src/datasets.py:STATIC`, the one registry of the built-in recordings | Detector tuples 2 → 1; `.mp4` literals in the two consumers 1 and 1 → 0 and 0, so no module under `annotator/` spells a built-in recording name; `tests/test_live_processing.py` 38 → 42 tests OK; `tests/test_datasets.py` 13 → 18 tests OK; `tests/test_enroll_from_tracklet.py` 114 tests OK; `tests/test_live_processing_stages.py` 28 OK; `tests/test_pipeline_stages.py` 29 OK. One deliberate change: `'balls'` is an accepted detector spelling for a start. Perturbations: the tuple back at `annotator/live_processing.py:38` fails exactly `test_the_detector_names_come_from_the_vocabulary`; a literal path back at `src/enroll_from_tracklet.py:119` fails 3 tests |
| R33-01 residue | The canonical frame is restated in four more modules (a residue of round 33 card 01; neither walk of round 34 named it) | `src/calibrate.py:32` `WM, HM = 1270.0, 2540.0`; `src/calib_vod30.py:30` `dst`; `src/audit_calib.py:21` `TABLE_W, TABLE_H = 2540.0, 1270.0`; `src/pocket_homography.py:22` `W_MM, H_MM` | `LANDSCAPE_W` :38, `LANDSCAPE_H` :39, `canonical_destination(landscape=False)` :42 and `canonical_pockets()` :58 in `src/table_geometry.py`; each reader calls one of them | Literal 1270/2540 in an AST scan: five files → one, the owner (before, the 77 tracked `.py` files of the parent repository; after, all 249 `.py` files under `src/`, the vendored `src/sam3` included); `np.array_equal` true with equal dtype and shape for every moved value; both import modes print the same values; `tests/test_table_geometry.py` 10 → 13 OK; `py_compile` 6 of 6. `src/audit_calib.py` keeps its landscape reading on purpose: its two error measures compare inside the same transposed frame, so its JSON mm errors equal the portrait reading |
| R4 | The read half of the domain is handed the transport's query mapping | Twelve `query.get(name)[0]` subscripts and one `values[0]` subscript read the parsed query, so a route that named its value honestly depended on the shape of `parse_qs` | `class ReadQuery` at `annotator/unified_server.py:438` with `from_pairs` :464, `text` :488, `integer` :492, `window` :507 and `scalars` :511; the route builds one at :2509 | `query.get(` call sites 12 → 0, `values[0]` 1 → 0, 12 accessor calls; `tests/test_unified_server.py` 80 → 82 tests OK; `?win=68-94&t=70` answers `win='68-94' t=70.0 tracks=3`, where the old code read the character `6` and refused an unknown window; a flat mapping raises `AttributeError` at the first accessor; `from_pairs` refuses a flat string in its own words. Perturbation: an old flat mapping in the route fails exactly four route tests. A stub-socket probe reports the arguments of the four media routes unchanged |
| C7 | The registry test drives every row instead of pinning four names | The test that was meant to hold the operation registry pinned four writer names by hand and asserted `isinstance(OPERATIONS[name].apply.__doc__ or '', str)`, which is true for every function, so a row could be wired to a writer that does not implement it and the test stayed green | `tests/test_operations.py` holds a `DRIVES` table with one row per registry row (world, payload, path, documented effect), pinned to the registry by `assertEqual(sorted(DRIVES), sorted(OPERATIONS))`; each row is driven through its own writer. `refuses_by_name(writer)` parses the writer with `ast` and finds the `raise` whose arguments are not all constants; each writer is then probed with the name `f'{name}_not_a_row'` under `patch.dict(OPERATIONS, {...})`, in a world from `PROBE_WORLDS` where that probe is reachable | Registry rows 34 of 34 driven, 22 writers; the reachable residue is bounded by `assertLessEqual(len(reached), 1)` and printed. `tests/test_operations.py` 1714 → 1955 lines (253 insertions, 12 deletions), `Ran 73 tests OK`; `annotator/operations.py` unchanged at sha1 `631c97b7…`. Three bite proofs: the defect that `96248f7` repaired, put back, fails `AssertionError: 5 not less than or equal to 1` for `_do_pairing`; a row wired to its neighbour fails two subtests while the older pins stay green; my own perturbation, the residue bound 1 → 0, fails exactly the `_do_entrants` bound (sha1 `d56544f3…` → `c4d50ca7…` → restored). The test surfaced a live defect: `_do_entrants` and `_do_revival` hold no final refusal by name, so the name `entrant_add_not_a_row` is accepted and adds a person (entrants 2 → 3) |
| C17 | A start takes the probe it reports, and the suite asks by name | Nine reads of a private name in `tests/test_live_processing.py` drove the session: the session object, its probe and `_reset_session` | `start(source, detectors=None, *, source_kind=None, probe=None)` at `annotator/live_processing.py:356`, `_reset_session(..., probe=None)` at `:277`, and `status()['probe_alive']` at `:741` | Private reads of `processor._` 11 → 5; `tests/test_live_processing.py` 42 → 43 OK; `tests/test_unified_server.py` 82 OK. The five that remain are deliberate: the capture factory of `4a9654b`, an exact three-wake assertion, and the reset ownership test. Perturbation: `probe=probe)` → `probe=None)` at `:399` fails exactly `test_a_given_probe_is_the_live_edge_the_session_reports` (sha1 `ec820582…` → `cc3bf1b3…` → restored). The card's ground was stale: its nine reads and line numbers belong to the `da765d9` era, and `7297712` had added two, so the two points it proposed cannot reach a count of one |
| S2 residue | Every writer refuses a name it does not implement | `_do_entrants` and `_do_revival` ended in a fall-through that WAS an action, the class `96248f7` repaired in `_do_match` and `_do_pairing`; the name `entrant_add_not_a_row` was accepted and added a person (entrants 2 → 3) | `elif action == 'entrant_add':` at `annotator/operations.py:833` and `elif action == 'revival_draw':` at `:1003`, each with a final `raise ValueError(f'Unknown … action: {action}')` at `:845` and `:1053` | Legal names unchanged (`git diff -w --numstat` reads `11 1`); `tests/test_operations.py` 73 → 75 OK and `tests/test_store_contract.py` 54 OK (skipped=29). The residue bound tightens with the repair: `tests/test_operations.py:1855` reads `limit = 0 if writer in guards else 1`, so the four multi-row writers that refuse by name must reach no row. Perturbation: the revival refusal replaced by `pass` fails two tests, the new refusal test and the `_do_revival` residue check (sha1 `aada8601…` → `21eabc81…` → restored) |

| C4 | The two dispatch tables become one action registry with two namespaces | `annotator/ops.js:1146-1183` held 95 `if (a === …)` branches with 24 `await action(...)` calls and 84 literal action names, and `annotator/vision-stage.js:1359-1490` held a second table of 63 `case` labels. A name could exist in one table and not the other, and no test could see it | `function newActionRegistry()` at `annotator/vision-stage.js:11` owns `define`, `defineFields`, `module`, `modules`, `names`, `fieldNames`, `has`, `isField`, `row`, `find` and `run`. The stage table is `const stageAct = (() => {` at `:1392` with 63 rows, `function act(action, value, node)` at `:1524` is a three-line forwarder, and `FIELD_ACTIONS` at `:1535` gained `link-target`. The console table is `const opsAct = (() => {` at `annotator/ops.js:1234` with 95 rows, registered by `const registerOps` at `:1221`; `dispatch(name, ctx = {})` at `:1339` and `run(node, event)` at `:1351` are the two ports, `registerOps();` at `:1355` runs at load, and the click handler calls `await opsAct.run(b,e);` at `:1364`. The handle publishes `dispatch`, `actions` and `registry` at `:1544` | `if(a===` 95 → 0; `case '` 63 → 0; `tests/test_ops.js` 201 → 205 pass, 0 fail; `tests/test_board.js` 16 pass, 0 fail; `tests/test_app_timeline.js` 94 passed, 0 failed, with `source-text assertions left: 65` unchanged. Four new tests hold the one registry: every rendered action resolves, every entry has an emitter or is on the named dead list (`UNREACHABLE_ROWS` at `tests/test_ops.js:4909`, eight ops names and no stage name), one registry serves both modules (`registry.find('live-start').length == 2`), and no branch chain is left. In the browser at 1596 by 1045 (raw CDP at `http://127.0.0.1:8130/#/records`): `globalThis.ActionRegistry` holds `modules() = ["vision-stage","ops"]`, 95 ops names, 63 stage names and the legal cross-namespace overlap `["live-start","live-stop","live-detector","chat"]`; the handle from `attach()` holds 174 keys = 6 ports + 168 `SEAM` rows, where HEAD held 171. An in-place row swap is honoured, proved live (`table['archive-reload'] = () => …` then `h.dispatch('archive-reload')` answers `ran the swapped row`) — but a NEW table object is silently undone, because `registerOps()` re-registers `opsAct.table` whenever `shared.module('ops') !== opsAct.table`. `window.OpsConsole.dispatch` stays undefined on purpose: the ports live on the handle. Perturbation: `shared.run('ops', name)` → `shared.run('ops-typo', name)` fails exactly two tests, the new registry test at `tests/test_ops.js:4937` and the round-13 Twitch configurator test at `tests/test_ops.js:4178` (failing at `:4199` with `TypeError: Cannot read properties of undefined (reading 'name')`); sha1 `bd9e72d6…` → `d006e141…` → restored. The eight dead rows are named and not deleted, and the coverage reader reads source literals, so a name built at run time escapes it |
| C6 | One atomic write with ten implementations | Ten modules each built a temporary file beside the target and called `os.replace`: `src/face_id.py:313-315`, `src/store_export.py:38-44`, `src/person_identity.py:487-490`, `src/store.py:165-172` and `:242-244`, `src/enroll_from_tracklet.py:630-634`, `annotator/shot_clock.py:226-233`, `annotator/vod_import.py:180-187`, `annotator/unified_server.py:213-220`. The docstring at `src/store.py:18` claimed all of them are "the same atomic temp-file + fsync + os.replace", and that claim was false: only some call `fsync`, and the temp names, the cleanup and the encodings differ | `src/atomic_write.py` (120 lines, only `os`, `tempfile`, `pathlib` and `typing`) with `write_atomic(path, write, *, fsync=False, temp_prefix=None, temp_name=None, encoding=None, remove_on_failure=True)` at `:57`, `DEFAULT_PREFIX = "."` at `:40`, and one documented rule per option. Nine call sites moved and each one keeps its own serialization, so `indent`, `sort_keys`, the newline and the encoding are unchanged. The docstring at `src/store.py:18` now names the owner. `annotator/operations.py` was left alone: its own `mkstemp` at `:396` and `replace` at `:403` belong to another worker's file | Five sites are durable (`fsync=True`): `src/store.py:171`, `src/store_export.py:38`, `annotator/shot_clock.py:231`, `annotator/vod_import.py:185`, `annotator/unified_server.py:217`. Four are best-effort on purpose: `src/face_id.py:318`, `src/person_identity.py:491`, `src/store.py:240` (which keeps `temp_name="{stem}.json.tmp"` and `remove_on_failure=False`), `src/enroll_from_tracklet.py:637`. `tests/test_atomic_write.py` 0 → 28 tests OK, and the whole suite then ran `Ran 1468 tests OK (skipped=51)`. My own perturbation found the gap this row closes: with `fsync=True` dropped at `src/store.py:171` the file still ran 26 tests OK, because the owner's fsync behaviour and each site's bytes were tested but nothing said which sites are durable. `class TestCallerDurability` now holds the two role lists, `_drives()` maps nine real write paths by `module.function`, and one test spies on `src.atomic_write.os.fsync` for every site. One run with fsync dropped at `src/store.py:171` and added at `src/person_identity.py:491` failed two subtests by name, and both files were restored from `cp` to sha1 `cd89333e…` and `36b0974c…`. A real-filesystem probe shows the default temp name `.state.json`, and a failing `os.replace` refuses with `disk full`, keeps `{"old": 1}` and removes the temp file |

### The commits so far

| Commit | Candidate | Subject |
| --- | --- | --- |
| `e5a9238` | C3 | console: the stage takes the shell writer as an option, not from a global |
| `8c74b23` | C1 | tests: the console's composition path runs once, on a page-shaped stub |
| `96248f7` | S2 | operations: a writer refuses a name it does not implement |
| `da765d9` | S3 | live: a source failure carries its code from the raise site |
| `704a8cd` | C5 | console: the clock seam carries the words and the language, and the console paints them |
| `39e57dc` | C8, C9 | engine: the snapshot is composed from named groups, and the suite drives the seams |
| `7297712` | S4 | live: one owner resets the session state |
| `af138c8` | R1 | pipeline: one vocabulary says what a detector is called |
| `b651cf5` | S5, S6 | operations: a row declares the record it audits, and one write resolves the registry once |
| `6710957` | S7 | live: the detector names and the recording names come from the one registry |
| `0692f2f` | C1 remainder, C10 | console: one `render()` is a list of named paint steps, and every screen declares its own paint |
| `4fc8b95` | C2 | console: the stage publishes the interface the console drives, and the row guard reads its own state |
| `7ac04a4` | round 33 card 01 residue | geometry: the four leftover frame copies read the one owner |
| `b609cf4` | R4 | server: a read route takes a typed query, and no route subscripts a mapping |
| `f535403` | C7 | operations: the registry test drives every row instead of pinning four names |
| `f2ec2fc` | C17 | live: a start takes the probe it reports, and the tests ask by name |
| `73d98f0` | S2 residue | operations: every writer refuses a name it does not implement |
| `e5a7110` | C4 | console: the two dispatch tables become one action registry with two namespaces |
| `0b7ecd2` | C6 | write: one atomic write module, and the nine call sites keep their bytes |
| `cbadfaf` | R4 repair | server: a read route names the type of its query at its own seam |

All seventeen cards of this review are landed but one. Card 11 stays open: a structured fact travels
as English prose and the console reads it back with a regular expression. The conflict sentence at
`annotator/operations.py:551-552` carries a night id inside the text
(`… "an unnamed event" ({night["id"]}); open it instead`), the server hands that sentence to the
browser at `annotator/unified_server.py:1882`, and `function bfConflictId(text)` at
`annotator/ops.js:482` extracts the id again as the last parenthesised run of
`/\(([^()]+)\)/g`. One number in the messages is wrong: the message of `96248f7`
says the full suite ran 1353 tests, and that tree ran 1356. One sentence is too wide: the message of
`6710957` says that `src/datasets.py:25 STATIC` is the only place in the repository that spells a
media file name. Measured after that change, 33 files under `src/` still spell a `.mp4` name of
their own, and the two built-in names appear in 43 and 14 files of `src`, `annotator` and `tests`.
What that commit measured is narrower and true: before it, exactly one file under `annotator/`
spelled a built-in recording name, and after it none does, because `annotator/live_processing.py`
and `src/enroll_from_tracklet.py` read `src/datasets.py:STATIC` instead. The same commit message
counts the enrolment suite as 112 tests before and 114 after; a detached worktree at `6710957^`
runs `Ran 112 tests in 2.332s OK (skipped=56)`, so that pair of numbers holds.

## Round 35 · the src walk (2026-10-09)

A read-only walk of the `src/` half delivered `/tmp/dshsess/walk_src_round35.md`: 13 candidates, 7
Strong, 4 Worth exploring, 2 Speculative, against the tree of `f535403`. The walk read 76 top-level
`src/*.py` modules and ran nothing, so each number below is a reading of the source. One candidate is
repaired and pushed; the others run in parallel under disjoint write scopes.

| Candidate | The defect | The decision | The measured result |
| --- | --- | --- | --- |
| The judging window | The control rows of the report were read over a hard-coded window of 2.5 s and 2.5 s at `src/motion_scan.py:2128-2129`, while the events those controls judge were read over `args.before, args.after` (1.5 s and 2.5 s) at `:2105-2109`. A control therefore had 1.0 s more data on the left, its peak read higher, and the floor built from the controls understated the false-positive rate of the rule. `peak_in_window` at `:945` and `occlusion_reading` at `:1245` carried the same pair as default values, so a caller could judge with a window it never stated. `--control-half-s` is a different fact and is read at one site only, `:2065`, for the calibration | The window is a value. `judge_window(args)` reads the pair one time in `cmd_report`; `control_row(t, arrays, signal, name, t0, before, after)` requires the window and cannot supply its own; `peak_in_window` and `occlusion_reading` have no defaults, so each caller states the window it judges with. The help text of `--before`, `--after` and `--control-half-s` says which window each option controls | `tests/test_motion_scan.py` 71 tests and 75 `def test_` names → 75 tests OK. A bump 2.0 s before a control reads 0.0 under the event window and 3.0 under the old pair, so the two readings differ by the whole bump. The new guard reads `src/motion_scan.py` and fails when a judging call does not state the pair `before, after` or carries its own literal. Perturbation: the control row supplied `2.5, 2.5` again, exactly one test failed (`test_every_judging_call_in_the_report_states_the_same_pair`) and its message named `src/motion_scan.py:2154`; sha1 `4813d7675f52c1d36532c3ec0a94381465976a89` → `2379293fa801c7e8b6a6b5a2203ccc79938f2f0f` → `4813d7675f52c1d36532c3ec0a94381465976a89` (restored with `cp`). A full `report` run cannot be measured: `cmd_report` reads a saved scan, and `out/scan30` holds no `.npz` file, so the live checks are the new help text of the report command and the readings of the fixture |

| The SAM3 admission gate | The bar that admits a ball instance was written in nine modules. The score cut 0.62 had nine code homes (`src/ball_census.py:107`, `src/ball_fp_audit.py:77`, `src/collect2.py:47`, `src/fast_ball_labels.py:51`, `src/pipeline.py:32`, `src/recut_crops.py:92`, `src/sam3_ball_cache.py:42`, `src/scan_events.py:126`, `src/tiny_ball_net.py:60`), the area band was 60 to 9000 in eight sites, and `src/pipeline.py:162` alone used 6000. Nothing could say which bar admitted an instance | One module holds the five numbers: `SAM3_BALL_MIN_SCORE = 0.62` at `src/ball_gate.py:84`, `SAM3_BALL_MIN_AREA_PX = 60` at `:87`, `SAM3_BALL_MAX_AREA_PX = 9000` at `:93`, `POC_PIPELINE_BALL_MAX_AREA_PX = 6000` at `:99`, `CLASSICAL_BALL_MAX_AREA_960X540_PX = 4200.0` at `:103`. Each site reads the owner and keeps its own local name, so every existing import still works. The 6000 px and the 9000 px bounds serve the same stage - both measure the sum of a SAM3 mask on the same unscaled 1280x720 source frame, in adjacent lines of one function - so the owner docstring states the disagreement and the behaviour does not change | `tests/test_ball_gate.py` 0 -> 7 tests OK; the guard reads every `.py` file under `src/` and fails when a gate-shaped number appears outside the owner; its exemption map is keyed by module and value, each entry names the different decision it belongs to, a stale exemption fails, and an exemption cannot become a wildcard. `tests/test_scan_events.py` 4 OK, `tests/test_sam3_ball_cache.py` 9 OK, `tests/test_ball_fp_audit.py` 54 OK, `tests/test_pipeline_stages.py` 29 OK, `tests/test_ball_census.py` 48 OK, `tests/test_tiny_ball_net.py` 37 OK. An AST scan of the nine modules removed {0.62 x 10, 60 x 6, 9000 x 5, 6000 x 1, 4200.0 x 1} and added only three `0` and one `1` from three new `sys.path` lines. Perturbations: the owner held 0.61 and exactly `test_the_owner_holds_the_documented_numbers` failed (sha1 `ea32c657…` → `4daf52d2…` → restored); `src/scan_events.py` stated 0.62 again and the guard named `src/scan_events.py:128` (sha1 `c89c4a2d…` → `f045f560…` → restored) |

| The events document | Five modules wrote `out/scan30/events.json` (`src/scan_events.py:333`, `src/rebuild_events_calibrated.py:144`, `src/dense_queue.py:640`, `src/eval_events.py:1134`, `src/candidate_scan.py:606`) and the file carried no producer and no version. Four of its sixteen keys are spelled by one writer only (`dup_count`, `last_px`, `pocket_name` and `provenance` at `src/dense_queue.py:302-312` and `src/eval_events.py:822-823`), so no reader could tell which rule set built the rows it read | `src/events_document.py` owns the two document names, the row shape, the version and one sentence per producer. `write` stamps every row with `{STAMP: {"version": VERSION, "producer": producer}}`; `read` returns the rows with the status STAMPED, MIXED or UNSTAMPED and never guesses a producer. The stamp is a row key, so the file stays a JSON list and its list readers keep working. `DocumentVersionError` is not a `ValueError`, so the permissive `except ValueError` at `src/eval_events.py:790` and `src/candidate_scan.py:606` cannot swallow a newer document | The served file is untouched: `out/scan30/events.json`, 12696 bytes, sha1 `3ffb1fe6…`, reads `4 rows, no stamp; the producer is unknown`. `tests/test_events_document.py` 0 → 24 tests OK, with four source guards holding the six callers to the owner. A rogue `Path(queue_path).write_text(json.dumps(entries, indent=1))` at `src/dense_queue.py:748` fails exactly the JSON guard with a message that names the file, the line and the function; sha1 `dce4d4ba…` → `f7c925bb…` → restored. The write is one atomic step through `src/atomic_write.py` since `1ab737e`: a row that JSON cannot serialize leaves the old document in place and removes its temporary file, and a perturbation back to one `open` fails exactly the new test. One measured difference: a new document has mode 0600 where `open` gave the umask default (0644 in this repository). Not proved: the path is not unique across the repository (`src/info_complete_scan.py:419`, `src/motion_scan.py:2313`, `:2316` and `src/store.py:352` still name the file), and no builder ran end to end, because those builders rewrite products under `out/` |

| The sam3 artifact | `out/scan30/sam3_results.json` is declared read-only by two modules that read it (`src/sam3_ball_cache.py:40`, `src/eval_events.py:150`) and rewritten in place by two others: `src/rebuild_events_calibrated.py:36` writes it with `json.dump(sam3, open(SAM3, "w"), indent=1)` after it recomputes every row's `table_mm` from `out/calib_final.json`, and `src/scan_events.py:157` writes it too. The file is 37909 bytes with 8 readers and 2 writers, so a reader cannot tell whether the numbers it trusts came from the detector or from a later calibration | In flight, with one owner for the artifact, its row shape and its producer stamp, on the pattern of `src/events_document.py` | In flight. The worker is `4153ba7f`, and its scope is the four modules plus one new test file |

### The commits so far

| Commit | Candidate | Subject |
| --- | --- | --- |
| `b87e47e` | the judging window | motion_scan: a control is judged with the same window as the event |
| `6963cfa` | the SAM3 admission gate | ball: the admission gate numbers live in one module |
| `dba24ab` | the events document | events: one owner names the producer of every row of a document |
| `1ab737e` | the events document, the atomic step | events: the owner writes a document in one atomic step |

### Where the four works in flight landed

These four works were in flight while this section was written, and all four are landed: the ball
gate (`6963cfa`), the atomic write (`0b7ecd2`), the one action registry (`e5a7110`) and the published
board vocabulary (`590f830`, recorded under round 36 below). Each row keeps the write scope its
worker was given, because none of the workers committed.

| Work | Scope |
| --- | --- |
| The SAM3 admission gate written in nine modules, with a disagreeing area band (60/9000 in eight sites, `src/pipeline.py:162` alone uses 6000, `src/scan_events.py:38` `MAX_BALL_AREA_720 = 4200.0` is a third value in the classical path) | `src/ball_census.py`, `src/ball_fp_audit.py`, `src/collect2.py`, `src/fast_ball_labels.py`, `src/pipeline.py`, `src/recut_crops.py`, `src/sam3_ball_cache.py`, `src/scan_events.py`, `src/tiny_ball_net.py`, the new `src/ball_gate.py` and `tests/test_ball_gate.py` |
| One atomic write with nine implementations, in `src/face_id.py:313-315`, `src/store_export.py:38-44`, `src/person_identity.py:487-490`, `src/store.py:165-172` and `:242-244`, `src/enroll_from_tracklet.py:630-634`, `annotator/shot_clock.py:226-233`, `annotator/vod_import.py:180-187`, `annotator/unified_server.py:213-220`; the docstring at `src/store.py:18` claims all of them are "the same atomic temp-file + fsync + os.replace", which is false | `src/atomic_write.py` and that call list, plus `tests/test_atomic_write.py` |
| One action registry for the two string-keyed dispatch tables: `annotator/ops.js:1146-1183` holds 95 `if (a === …)` branches, 24 `await action(...)` calls and 84 literal action names, and `annotator/vision-stage.js:1359-1490` holds a second table with 63 `case` labels | `annotator/ops.js`, `annotator/vision-stage.js`, `tests/test_ops.js`, `tests/test_app_timeline.js`, `tests/test_board.js`, the cache tags of `annotator/ops.html` |
| One published status and result vocabulary: `annotator/public_board.py:17-18` holds its own `STATUSES` and `RESULTS`, and `:48` maps an unknown status to `"pending"` without a word, while the registry writes `registration`, `scheduled`, `delayed`, `complete`, `pending`, `active`, `bye` and `forfeit` | `annotator/operations.py`, `annotator/public_board.py`, `tests/test_public_board.py`, `tests/test_operations.py` |

## Round 36 · the annotator Python half (2026-10-10)

A read-only walk of the Python modules under `annotator/` delivered
`/tmp/dshsess/walk_annotator_py_round36.md`: 8 candidates, 5 Strong, 2 Worth exploring, 1
Speculative, against the tree of `f535403`. The walk counted 11 modules and 7813 lines, and it ran
nothing. Four of its candidates are landed and pushed in this round, and three more are in flight. Its own limits: it read no file
under `out/`, it did not start the server, it did not diff the atomic writers mechanically, and it
could not prove that the console reads the `actions` array the contract publishes.

| Candidate | The defect | The decision | The measured result |
| --- | --- | --- | --- |
| C6, the provenance hook | A stage hook that returned something other than a dictionary lost its provenance in silence: `if isinstance(extra, dict): entry.update(extra)` at `annotator/pipeline_stages.py:222-227` had no other branch. A hook that raised took the whole frame down. Every other malformed property is refused at `:161-176`, and the registry always contributes `ran` and `age_frames` at `:218`, so the entry still looked complete | `REGISTRY_KEYS = ('ran', 'age_frames')` names the two answers the registry owns and a hook cannot replace. A hook that returns a non-dictionary, or that raises, records `evidence_error` in the entry and never stops the frame, in the shape of the precedent at `annotator/pipeline_stages.py:368` | `tests/test_pipeline_stages.py` 29 → 33 tests OK. The merge site set back to `entry.update(extra)` runs `Ran 33 tests FAILED (failures=1, errors=2)` and fails exactly the three new rule tests, while the test of a stage with no hook stays green (sha1 `42116a6b…` → `4057d3ca…` → restored). A live `LiveProcessor` with a stub capture and a diagnostics hook that raises showed `state error`, 0 runs and `evidence null` before the fix, and `state eos`, 6 runs per stage and `evidence_error` naming the raise after it (probe `/tmp/c6-live/probe.py`) |
| C3, the board vocabulary | `annotator/public_board.py` re-implemented the console's rules in Python, with a third local vocabulary at `:17-18` and a silent fallback at `:48`, while the registry writes eight status and result words. No test compared the two answers | One published vocabulary: `MATCH_STATUSES` and `MATCH_RESULTS` at `annotator/operations.py:95-96`, imported at `annotator/public_board.py:18` and read at `:50` and `:52`. The remaining literals at `:59`, `:61`, `:78` and `:81` stay, because they are semantic choices and not membership tests | `tests/test_public_board.py` 30 → 34 tests OK, `tests/test_operations.py` 75 OK, `tests/test_board_api.py` 21 OK (skipped=2), and the payload of seven fixtures stayed byte for byte (the console fixture payload sha1 is `52597915…`). A dead branch writing `status = 'abandoned'` at `annotator/operations.py:1384` fails exactly `test_every_word_a_match_is_given_is_published` with the file, the line and the word in the message (sha1 `6e454ba5…` → `6fa494a8…` → restored). The scan reads the source of `annotator/operations.py` only, so a non-literal write is invisible, and the `annotator/ops.js` vocabulary is still a second copy with no cross-language test. That remaining half - the standings, the tie-break and the silent status fallback against the console rules - is open, and worker `5e83894e` holds it in round 39 |
| C1, the route contract | `Actions.contract()` publishes `actions = list(row.actions)` at `annotator/unified_server.py:139-142` and serves it from GET `/api/actions` at `:1773`, but 1 of 21 rows sets `actions=`: `annotator/unified_server.py:2049` `actions=TOURNAMENT_ACTIONS`. The other 20 rows publish an empty list while their handlers accept verbs the registry cannot see: 8 in `vod_request` (`annotator/unified_server.py:1402`), 2 in `live_action` (`:562`), 4 in `annotator/shot_clock.py:31` and 3 in `annotator/vod_import.py:848` | Landed, commit `a67903c`: every row declares the verbs its handler accepts. The handler's own tuple is the one owner - `LIVE_ACTIONS` in this module (2), `annotator/shot_clock.py` `ACTIONS` (4) and `annotator/vod_import.py` `AUTO_ACTIONS` (3) - and `OperatorAction.verbs` answers the declared tuple, or the last part of the route URL for a row that reads no action out of the payload, so no row publishes an empty set | `tests/test_unified_server.py` 85 → 90 cases, in the new `WriteActionContractTests` class. The python suite `Ran 1554 tests, OK (skipped=53)` |
| C2, the unstamped caches | Five caches live on one `Backend`: `annotator/unified_server.py:524`, `:536`, `:537`, `:1013` (filled lazily at `:1015`) and `:1176` (lazily at `:1178`). Three carry a stamp and two do not, and `grep -c "\.clear()" annotator/unified_server.py` is 0, so no write invalidates anything. The unstamped pair is `_prior_cache` at `:1013-1024` and `_unified_cache` at `:1046-1049` and `:1087-1092`, bounded by `_UNIFIED_CACHE_MAX = 24` at `:976`. The write that invalidates nothing is `self.store().anchors_put("vod30", str(info["t"]), clean)` at `:1939`, behind the route declared at `:2081`, and the stale value is consumed by `saved = self._prior_for(dataset)` at `:1063` | Open. The provenance rule that three caches state by hand belongs in one place, and a write that changes what a cache holds must invalidate it. Worker `16e50f45` holds this candidate in round 39 | Open |
| C4, the durable-write decision | The walk listed the durable-write decision as five places: four atomic writers and two unsafe plain `Path.write_text` calls at `annotator/server.py:123` and `:144`, in a 154-line module with 0 importers | Resolved by round 34 candidate C6, landed as `0b7ecd2`: one owner in `src/atomic_write.py`, nine call sites, five durable and four best effort, with `class TestCallerDurability` holding the two role lists. `annotator/server.py` was not part of that work because nothing imports it | `tests/test_atomic_write.py` 28 tests OK, and the module still has 0 importers |
| C5, the retention constant | One retention fact lives in two halves: the literal `])[-500:]` at `annotator/operations.py:387` and `MAX_EVENTS = 500` at `src/store_import.py:46`, used at `:173` and `:283`. A comment is the whole contract between them | Landed, commit `58a7d4e`: `src/ops_event_log.py` holds `MAX_EVENTS = 500` and `trim(events)`. Three writers trim through it (`src/store_pg.py:140`, `src/enroll_from_tracklet.py:484`, `annotator/operations.py:397`) and the importer reads the bound from it (`src/store_import.py:177`, `:287`). `src/store_check.py:66` keeps its own SQL `LIMIT 500` and is the one recorded exception | Literal write points 5 → 1, name reads 3 → 2. The new `tests/test_event_retention.py` holds 9 cases. The python suite `Ran 1554 tests, OK (skipped=53)` |
| C7, the Twitch seam | Three host validators (`annotator/twitch_source.py:34`, `annotator/twitch_vod_source.py:99`, `:122`), two allowlists (`:96`, `:119`), seven network sites, and a fourth time-stamped cache at `annotator/twitch_vod_source.py:215` with `_THUMB_CACHE_TTL_S` at `:216` and `_THUMB_CACHE_MAX` at `:217` | Open, Worth exploring. Worker `5e659542` holds this candidate in round 39 | Open |
| C8, `_playlist` twice | `def _playlist(text)` is defined twice, at `annotator/twitch_source.py:80` and `:143`, with byte-identical bodies, and the second definition rebinds the name | Open, Speculative | Open |

### The commits so far

| Commit | Candidate | Subject |
| --- | --- | --- |
| `7309bb8` | C6, the provenance hook | stages: a provenance hook cannot replace the registry answer, and it never stops a frame |
| `590f830` | C3, the board vocabulary | board: the words a match may carry belong to the registry |
| `a67903c` | C1, the route contract | server: every write row declares the verbs its handler accepts |
| `58a7d4e` | C5, the retention constant | events: one owner holds the retention bound of the operations event log |

## Round 37 · the operator half (2026-10-10)

A read-only walk of the half no earlier round had read - `tools/`, `scripts/`, `db/`, `deploy/`,
`viz/` and `research/` - delivered `/tmp/dshsess/walk_tools_round37.md`: 7 candidates, 3 Strong, 3
Worth exploring and 1 Speculative, against the tree of `e5a7110`. The walk ran nothing, opened no
database connection and did not read the deployed systemd user state, so every count below is a
reading of the source, and its grep counts include comments.

| Candidate | The defect | Where it stands |
| --- | --- | --- |
| Strong 1, the golden fixture | `tools/playfield_vod_audit.py:86-95` writes the tracked fixture `tests/fixtures/playfield_quads.json` before its own gates: `FLOOR = 8` at `:100` and `KNOWN_REFUSED` with the floor at `:117-127`. `tests/test_playfield_quads.py:34-53` then replays that fixture through the same `check_quad` that produced it, so a tolerance regression can be baked into the golden. The fixture holds 36 picks over 12 VODs with counts {ok 24, refused 12, no_quad 21}, it passes exactly 8 = `FLOOR`, `FLOOR` is spelled twice, the producer is named only by a free-text date, the test never asserts `KNOWN_REFUSED` membership, and the tool has no main guard and writes the repository at import | Landed, commit `e0557df`: the fixture opens with a `provenance` block (producer, plan, the live rule values, floor `8` and the 11 refused names), and the tool writes the fixture only with `--write-fixture` when both gates pass, else `FIXTURE WRITE REFUSED: <path> not written: gate <name> failed`. `tests/test_playfield_quads.py` 4 to 14 tests; `FLOOR = 8` to `7` fails exactly one test that names both the fixture and `tools/playfield_vod_audit.py:54`; `picks`, `counts` and `passing` are byte-identical to the old file |
| Strong 2, the crop-set vocabulary | One vocabulary is written five times: identical `BALL_SETS` tuples at `src/store.py:55`, `src/store_files.py:21`, `src/store_import.py:45`, `annotator/unified_server.py:40`, plus the `CHECK` at `db/migrations/0002_user_data.sql:174`. Only `src/store_pg.py:33` imports the owner, and no test compares the copies | Landed, commit `0c30e5d`: `src/store_files.py:26 BALL_SETS` is the one Python owner, and `src/store.py`, `src/store_import.py`, `src/store_pg.py` and `annotator/unified_server.py` import it. `tests/test_store_files.py` proves the Python list and the SQL `CHECK` hold the same names in the same order; renaming one name in the owner failed exactly one test in each new test file |
| Strong 3, the dataset-id grammar | The grammar is implemented twice: `dataset_id_ok` at `db/migrations/0004_imported_datasets.sql:24-31` against `parse_imported_id` at `src/datasets.py:84`. The SQL function has 0 hits under `tests/`, and its "25 edge cases equal" claim lives only in a note (`.pm/PROJECT.md:2179`). `:33-34` drops constraints by auto-generated names that `0002` never declares | Landed, commit `2186f91`: `tests/dataset_id_cases.py` is a corpus of 51 spellings with hand-written verdicts, and both sides were proved to bite: `src/datasets.py:36 _ID_MAX` `64` to `63` fails exactly the 64-character case, and `db/migrations/0004_imported_datasets.sql:27` `length(d) <= 64` to `63` fails the same case through the database test |
| Worth, the fingerprint script | `scripts/pool-write-fingerprint.sql` holds 18 hand-copied `SELECT` branches against 19 tables under `db/migrations`, with 0 code callers | Open |
| Worth, the deployment conventions | Deployment has two conventions and no installer: 3 placeholders over 6 occurrences in 2 template services against 2 checked-in drop-ins. `40-public-board.conf:10` hard-codes `%h/projects/pool` and re-spells `--port 8130` although `annotator/unified_server.py:2601` already defaults it, and the `sed` render is copy-pasted at `docs/postgres.md:225` and `:391` | Open |
| Worth, the audit harness | The two audit tools are a copy-paste harness that re-spells the live configuration: `TableStage(..., dataset=None, measure_every_n=30)` at `:35` and `:77`, identical `StageContext` triples at `:46` and `:87`, `30` spelled at 5 sites, while the live path passes the session dataset at `annotator/live_processing.py:388-390` | Open |
| Speculative, the unreferenced folders | `viz/` holds 9 unreferenced HTML fragments (928 lines, untracked, ignored by `.gitignore:14`), and `research/player-attribution-research.md` (38 lines) has 0 references | Open |

### The commits so far

| Commit | What it says |
| --- | --- |
| `2186f91` | datasets: the id grammar is one corpus that both sides answer |
| `0c30e5d` | store: one owner names the crop sets, and the database list is proved equal |
| `e0557df` | tests: the playfield record carries how it was made, and the tool refuses a bad run |

Four workers held disjoint scopes and none of them committed. The sam3 artifact (round 35, Strong 2)
landed as `eeca97d`, the playfield fixture as `e0557df`, the crop-set vocabulary as `0c30e5d`, and
the read-only walk of the test suite as `/tmp/dshsess/walk_tests_round38.md`, which round 38 reads.

## Round 38 · the test suite as a system (2026-10-10)

A read-only walk of the test suite as a system, against the tree of `c2e1b951`. It ran the suites,
read the four harnesses and counted call sites. `docs/console-redesign.md` itself is one of the
inputs it read: the source-text ledger of `tests/test_app_timeline.js` was built by round 34, so the
walk checks it with the same suspicion as the product code.

Delivered `/tmp/dshsess/walk_tests_round38.md`: 9 candidates, 4 Strong, 4 Worth exploring and 1
Speculative. Every count below is a reading of the source, and its grep counts include comments.

| Candidate | The defect | Where it stands |
| --- | --- | --- |
| Strong 1, the frozen evidence | `tests/test_ball_fp_audit.py:412` `class FrozenEvidenceTest` holds 5 test methods that read `out/ball-fp-audit/cases.json` (14603 bytes), `out/ball-fp-audit/verdicts.json` (35249 bytes) and `out/tiny_ball_probe/report_960x540.json` (9821 bytes). `:416-417` skips the class when `CASES_OUT` is absent, and `:439`, `:456`, `:467` skip inside methods with `verdicts have not been computed`. `out/` is ignored by `.gitignore:14` and `git ls-files out/ball-fp-audit out/tiny_ball_probe` returns 0 files, so the same commit runs 5 assertions here and reports 5 skips in a fresh clone | Landed, commit `28ef11d`: the three files are byte-identical copies under `tests/fixtures/ball_fp_audit/`, and the new `PROVENANCE.txt` records the source path, the sha1 and the byte size of each file. The class reads the copies and fails loudly when one is missing, and a new test compares each copy with that record. A new `ProductionPathsTest` pins the four production paths, so this change cannot move the audit output. The measured run: a fresh tree from `git archive HEAD` with the old test file: `Ran 54 tests, OK (skipped=5)`; the same tree with the new test file and the fixtures: `Ran 56 tests, OK`, and no skip line. This checkout: `Ran 56 tests, OK`. One digit of the recorded `cases.json` sha1 changed fails exactly one test, which names the fixture and its source path (restored with `cp -p`) |
| Strong 2, the absence claim | The ledger `tests/test_app_timeline.js:119-132` computes a `between` window with `text.indexOf`, and `:130` tests the snippet against `scope`. If either anchor is renamed, `scope` is `''`, and the one call site that passes `absent: true` with a window (`:1379`) passes on the empty string. 45 call sites use the helper, and 11 pass the `true` shorthand | Landed, commit `cd69d75`: the helper asserts that both anchors were found before the window is built. Proved by restoring the old helper with a renamed anchor (94 passed, 0 failed) and then the new helper (93 passed, 1 failed) |
| Strong 3, the fixture listener | `tests/serve_operations_fixture.py:33` holds `class FixtureServer` with `:44 request_queue_size = 64`, a copy of `annotator/unified_server.py:2122` inside `class BoundedHTTPServer`, which `:29` already imports five names from. `tests/serve_vod_fixture.py:131` serves the product class instead. A change of the ceiling leaves the fixture green | Landed, commit `bd90a09`: the fixture serves `annotator.unified_server.BoundedHTTPServer`, and new tests in `tests/test_unified_server.py` (class `BrowserFixtureListenerTests`) scan `tests/*.py` for the backlog and assert the fixture listener is the product class. `tests/test_unified_server.py` 83 to 85 tests |
| Strong 4, no single runner | No `Makefile`, no `package.json` and no root script exists, so no one command runs the python suite and the three javascript suites. The documented node forms disagree over 47 occurrences, and a bare `node --test` collects 0 tests and exits 0 (node v24.21.0), because no file name matches the node default patterns `*.test.js` and `test-*.js` | Landed, commit `65b4308`: `scripts/pool-test.sh` runs the python suite and the three javascript suites, `pool-test.sh python` and `pool-test.sh js` run one half, and a different argument exits 2. The README names the script and the reason why a bare `node --test` proves nothing. `make` is not installed here, so the runner is a shell script |
| Worth, two harness families | Three javascript harnesses use two assert modules and two DOM stub families | Landed in part, commit `5b4ad2b`: `tests/test_app_timeline.js` now loads `node:assert/strict`, and the six scrub-bubble calls that used the loose form name `strictEqual`. At `28ef11d` the file held 6 `assert.equal(` calls and 352 `assert.strictEqual(` calls; it now holds 0 loose calls and 359 strict ones, and the suite still prints `94 passed, 0 failed` with `source-text assertions left: 65`. The two DOM stub families and the two remaining assert modules are open |
| Worth, one class-level skip | One class-level skip turns off 26 of 94 test methods, and the module writes the same fixture document three times | Open |
| Worth, wall-clock and threads | The suite measures wall-clock time and thread count, which makes a result depend on the machine that ran it | Open |
| Worth, skip calls | Skip calls outnumber the checks that could describe what ran | Landed, commit `e303818`: the new `tests/test_suite_inventory.py` states how many suite checks this checkout does not run, and holds four committed limits at `tests/test_suite_inventory.py:67-70` (`MIN_DISCOVERED_CASES 1550`, `MAX_VISIBLE_SKIP_CASES 52`, `MAX_SKIP_TEST_SITES 26`, `MAX_REQUIRE_SITES 13`). Measured: 1550 cases in 63 modules, discovery 1.17-1.2 s, 52 cases carry `__unittest_skip__` in 7 modules, 26 `self.skipTest()` sites in 11 modules, 13 `data_guard.require` sites in 8 modules; the file runs `Ran 4 tests, OK`. The three Worth items above stay open |
| Speculative, the palette list | The palette check holds a hand-written list of 40 values and scans one directory level | Landed, commit `15e8715`: the scan walks with `rglob` over `.css .js .html .svg` and skips `__pycache__`, states its file count, and holds `SCANNED_FLOOR = 10`. Measured: the walk reaches 14 files, and the top level holds the same 14, so no new file is read today; the failure message names the file and the count, and the value list is checked for emptiness and repeats instead of a hand-written 40. The file holds 5 cases before and after |

### The commits so far

| Commit | What it says |
| --- | --- |
| `bd90a09` | tests: the browser fixtures serve the production listener |
| `cd69d75` | tests: a source window with a missing anchor fails instead of passing empty |
| `65b4308` | tests: one entry point runs the four suites, and the README names it |
| `28ef11d` | tests: the frozen ball-fp evidence is tracked, so the audit test runs in a fresh clone |
| `5b4ad2b` | tests: the timeline suite compares with the strict assert module |
| `e303818` | tests: one case states how many suite checks this checkout does not run |
| `15e8715` | tests: the palette scan states its file count and holds a floor |

## Round 39 · the remaining Strong candidates (2026-10-10)

Five candidates closed as five commits, each with tests and a measured check, and every number in a
message was re-measured before the message was written:

| Commit | What it says |
| --- | --- |
| `a67903c` | server: every write row declares the verbs its handler accepts |
| `58a7d4e` | events: one owner holds the retention bound of the operations event log |
| `5b4ad2b` | tests: the timeline suite compares with the strict assert module |
| `e303818` | tests: one case states how many suite checks this checkout does not run |
| `15e8715` | tests: the palette scan states its file count and holds a floor |

`git push origin main` moved `28ef11d..15e8715`.

Four workers then held disjoint scopes, and none of them commits:

| Worker | Candidate | Write scope |
| --- | --- | --- |
| `16e50f45` | round 36 C2, the five `Backend` caches | `annotator/unified_server.py`, `tests/test_unified_server.py` |
| `5e83894e` | round 36 C3, the remainder: the standings, the tie-break and the silent status fallback | `annotator/public_board.py`, `tests/test_board_api.py` |
| `5e659542` | round 36 C7, the Twitch fetch seam | `annotator/twitch_source.py`, `annotator/twitch_vod_source.py`, `annotator/vod_import.py`, `tests/test_vod_import.py` |
| `36c9a695` | round 35 Strong 3, the SAM3 admission gate | `src/` and one new test file under `tests/` |

`annotator/unified_server.py` is the file the server on 127.0.0.1:8130 runs, so every worker starts its
own instance on a free port and none of them touches that process. Two Strong candidates still wait:
round 34 card 11, the conflict sentence parsed back from the operations text (ground
`annotator/operations.py:551-552`, `annotator/unified_server.py:1882` and
`function bfConflictId(text)` at `annotator/ops.js:482`), waits for `16e50f45` because it needs the
same file; and round 36 C8, `def _playlist(text)` defined twice at `annotator/twitch_source.py:80` and
`:143`, waits for `5e659542`.

