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
