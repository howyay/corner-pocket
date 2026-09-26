# Requirements traceability: the owner's feedback document

This file traces every item in **the owner's feedback document (not in this repository)** against Corner Pocket as
it stands. It changes no code.

The document is feedback on a **different product**, a tournament-bracket web tool (called "the reference product"
below). The owner wants its features and fixes carried into our operations side: Floor · Set up · Matches · Regulars
· Back room. Each item therefore gets a verdict on whether *our* model has the concept, not whether the reference
product does.

## Source, verification, method

- **Source.** The document is 4 pages: body text, embedded screenshots and four comment threads. Page 4 is only a
  screenshot, with no text.
- **Identifying quotes.** Only a short identifying quote per item is committed. The full transcript and page images
  stay outside the repository.
- **Evidence.** Verified at `main` **`8fe1af1`**, with polish-branch docs read at `impeccable-polish` **`90438ac`**.
  - **`annotator/operations.py` lines are read from that HEAD.** It now has `_commit` at `:88` and `enroll_player`
    at `:108`, so every line below was re-anchored.
  - **`annotator/ops.js` renders each screen as one very long line.** A citation such as `ops.js:46` therefore
    names the line the screen lives on. Every cited `ops.js` fragment was checked with a literal grep at `8fe1af1`
    (25 of 25 matched).
- **Behaviour.** Two scratch probes drove `annotator.operations.Operations` in a `tempfile.TemporaryDirectory()`
  and exercised rename, bracket, byes, names and archive. They are kept outside the repository and never touched
  production state.
- **Inventory references.** `inv #N` means item N of the 167-item feature inventory,
  `impeccable-polish:docs/impeccable-feature-inventory.md`.
- **Status values:**
  - **covered**: we already do it.
  - **partial**: the concept exists, but it does not meet the ask.
  - **missing**: no such concept.
  - **conflicts**: it breaks a standing rule, and the closest honest version is proposed.
  - **not applicable**: it only concerns the reference product.
- **Tracks:**
  - **(a)** bug fix on `main`.
  - **(b)** the `impeccable-polish` design branch.
  - **(c)** Postgres backend work (`docs/postgres-design.md`).
  - **(d)** new feature.
- **Priority:** P0 must, P1 should, P2 nice.

## Summary

**15 items (R1–R15).** 8 are feature requests, 3 bugs and 4 UX feedback. 4 comment threads clarify R5, R6, R7
and R12.

| Status | Count | Items |
|---|---|---|
| covered | 3 | R3 (with a caveat), R7, R11 |
| partial | 6 | R2, R4, R8, R9, R13, R15 |
| missing | 3 | R1, R10, R12 |
| conflicts | 2 | R5, R6 |
| not applicable | 1 | R14 |

| Track (primary) | Count | Items |
|---|---|---|
| (a) bug fix on `main` | 5 | R2, R5, R7, R11, R12 |
| (b) `impeccable-polish` | 3 | R9, R13, R14 |
| (c) Postgres backend | 0 primary | R1, R8, R12 and R15 also touch it (see rows) |
| (d) new feature | 7 | R1, R3, R4, R6, R8, R10, R15 |

**Every standing product rule this matrix reconciles:**
- **R5, byes.** The rule is "never claim what the system cannot prove". A bye is recorded natively. It is not a
  placeholder player.
- **R6, loser revival.** The rule is "never generate random winners" (`docs/corner-pocket-operations.md:23`) and
  "completed results are immutable" (`:21`). A random draw may only choose *who re-enters*, it must be audited, and
  it must not rewrite a signed result.
- **R1, delete.** The rule is "production data is never silently destroyed". The proposal is delete-while-empty
  plus archive and hide, with an audit line.
- **R3, random pairing.** The same no-random-results rule applies. Only the pairing is random, and it is shown
  before the draw.
- **R10 and R15, no fabricated statistics.** Stats are computed only from signed results and labelled with their
  scope.
- **Every new string** has EN / 中 parity (`inv #161`).
- **Every new GET** stays read-only.

### Top 10 gaps by user impact

| # | Gap | Plan (one line) | Row | Track |
|---|---|---|---|---|
| 1 | A renamed regular keeps the **old name** in the draw, scorecard and archive. Ours does not vanish, but it goes stale. The document calls this 强需求, a strong requirement. | `ename` already prefers the live roster name. Apply the same rule to the archived-events reader (`ops.js:46`), add a property test "rename never detaches a player from their matches", and let (c) keep `player_id` authoritative. | R12 | (a) |
| 2 | No all-time player view: no history page, no per-player record beyond four tiles. | A read-only *Player record* page reachable from Regulars without opening an event, built on `resultStats` across `[current, ...history]`. | R15 | (d) |
| 3 | No shareable results sheet or champion card; you cannot post "the whole bracket" to the group chat. | A print-ready results page (`@media print` plus one full-bracket view) with the champion taken from the final's `winnerId`. No image rendering server-side. | R10 | (d) |
| 4 | No head-to-head record. | A per-opponent table in the player record: W–L and win % against each opponent, signed matches only, byes and forfeits excluded, sample size shown. | R8 | (d) |
| 5 | The standings are a **rating** list, not results. There is no wins column and no per-event table. | Add Wins / Played / Win % columns, and an event table sorted wins → win % → name. Label rating "house rating (manual)" so it is never read as a result. | R4 | (d) |
| 6 | Byes read as "Signed", and a hand-typed "NA" guest is accepted as a real player. | Show *Bye* (轮空) on bye matches, exclude byes from the "Cards signed" count, and refuse or confirm placeholder guest names (`na`/`bye`/`TBD`/`轮空`). | R5 | (a) |
| 7 | An event racked without saving the form has an **empty name**. The archive then shows a hex id, and the audit log says `name: ''`. | The rack action saves the displayed default name first, or the server fills the default. Add a test that an archived event always has a name. | R2 | (a) |
| 8 | No way to remove a mistaken event. Archive is the only path, and the empty event it leaves still shows up. | `tournament_delete` only while the event has no signed results; otherwise *Archive* plus *Hide from history*. Both confirmed and audited. | R1 | (d) + (c) |
| 9 | The bracket is a sideways-scrolling stack of tall cards: too few matches per screen. | A compact bracket density (one line per side), fitted to the width. `.round .entry{min-height:98px}` at `ops.css:80` is the main cost. | R9 | (b) |
| 10 | Forfeit and in-match absence are unreachable from the UI (finding F1): the fallback for a no-show is missing. | Call `queueCard()` from the Matches bracket, or move its three controls into the bracket card (`ops.js:46`). | R7 (related) | (a) |

## The matrix

The evidence column cites `main@8fe1af1` unless marked otherwise.

| ID | Page | Item (identifying quote → English) | Category | Status | Evidence (UI path · `file:line`) | Gap → proposed change | Pri | Track |
|---|---|---|---|---|---|---|---|---|
| **R1** | 1 | 「無法刪除已有賽事」 → cannot delete an existing event | feature request | **missing** | *Set up → Archive & new event* is the only lifecycle action (`inv #40`). It is confirmed with `newConfirm` (`ops.js:85`) and archives into `history` when entrants or matches exist (`operations.py:350-357`). No action removes an event or a history entry; `tournament_new` only appends. There is no delete for events, while `player_delete` refuses players with history (`operations.py:219-222`). | Add `tournament_delete`, allowed only while no match has `result` `played`/`forfeit`, i.e. registration or an unplayed draw. For events with signed results, add *Hide from history* (a flag, never an erase). Both confirmed, audited, in EN/中. Track (c) must carry the flag and the delete rule. | P1 | (d) + (c) |
| **R2** | 1 | 「無法改已經創的賽事名稱」 → cannot rename an event after creating it | feature request | **covered** on `main` `309ebfe` (rack saves the shown name, server fills a default, `tournament_rename` name-only for current + archived, audited) · was: partial | *Set up → The night → Event name* renames the event while it is in registration (`operations.py:235`). After the draw the form is disabled (`ops.js:43`, `inv #36`) and the server refuses (`operations.py:226` "Tournament already started"). Archived events cannot be renamed. The probe racked without saving the form and got `name=''`; the archive summary then falls back to the id (`h.name||h.id`, `ops.js:46`). | Allow a **name-only** edit after the draw and for archived events: a new `tournament_rename`, audited, leaving the rules untouched. Rules stay locked. Fix the empty-name path: rack saves the displayed default (`autoEventName`, `ops.js:49`) or the server fills it in. Add a test that an archived event always has a name. | P1 | (a) |
| **R3** | 1 | 「雙打沒法隨機配對隊友 輸入順序即隊友」 → doubles: no random teammate pairing; entry order makes teams | feature request | **covered** (explicit pairing; random pairing not built) | *Set up → Registration desk* has explicit *Regular* and *Partner* selects per entrant in doubles (`ops.js:43`). The server requires exactly 2 members (`operations.py:248`). Teams are chosen, not implied by order. | Our flow already avoids the reported problem. For the random ask: an optional *Pair solo sign-ups randomly* step before the draw. It shows the resulting teams for confirmation and records the pairing in the audit log. Pairing only, never results, which is the operations rule at `docs/corner-pocket-operations.md:23`. | P2 | (d) |
| **R4** | 1 | 「本届榜单有勝率, 也新增個勝場」 → the leaderboard shows win rate; add a wins count | feature request | **covered** on `main` `43b24df` (standings Wins/Played/Win %, event table wins → win % → name, rating labelled manual) · was: partial | Win rate and wins exist **only per player** in *Regulars → profile modal* tiles (`ops.js:77`, `inv #51`), computed by `resultStats` (`ops.js:47`) over the current and archived events. *Matches → House standings* is sorted by **rating**, a manual 0–1000 number (`roster()` sort at `ops.js:25`; list at `ops.js:46`; `inv #45`), with no wins or win rate. There is no per-event table. | Add columns **W · Played · Win %** to the standings, plus an **event table** for the current or archived event, sorted wins → win % → name. Rating stays, labelled manual. Only signed `played`/`forfeit` matches count (see R5). EN/中 labels. | P1 | (d) |
| **R5** | 1 (+ thread) | 「vs NA 不算勝率/勝場」 → matches against a bye (輪空) must not count; stop typing na/bye by hand | UX feedback / data | **covered** on `main` `cc82864` (bye badge, signed count, placeholder names) · was: conflicts (the rule is met, the UI mislabels) | The model handles byes natively. The draw pads to a power of two and gives byes to the first seeds (`operations.py:277-282`). `_propagate` completes a match with fewer than two sides as `result='bye'` (`operations.py:179`). Probe: 5 entrants → 7 matches, 3 byes. **Stats already exclude byes:** `resultStats` counts only `m.sides.every(Boolean)` (`ops.js:47`). **The UI still mislabels them:** a bye shows the badge `Signed / 已签` (`badge(m.status)`, `ops.js:46`; `complete:['Signed','已签']`, `ops.js:4`), its empty side reads `Waiting / 待定` (`ename`, `ops.js:25`), and the "Cards signed" tiles count byes (`ops.js:41`, `ops.js:46`). The server also accepts a guest literally named `NA` (probe). | **Conflict:** the UI must not claim a card was signed when no one played. Show **Bye / 轮空** (the badge from `m.result`), render the empty side as "—" with *Bye*, and exclude byes from the signed count. Refuse or confirm placeholder guest names (`na`, `n/a`, `bye`, `tbd`, `轮空`, `輪空`) with a hint that byes are automatic. The stats rule is already correct; add a test that pins it. | P0 | (a) |
| **R6** | 1 (+ thread) | 「敗部復活機制 (僅限復活到一/二輪)」 → loser revival: one click draws one round-1 loser back in | feature request | **conflicts** | Not in the model. The draw is built once at `tournament_start` (`operations.py:274-297`). Completed results are immutable (`operations.py:302`, `docs/corner-pocket-operations.md:21`). Byes auto-complete at the draw (`operations.py:179`), so round-2 slots are fixed. Random winners are forbidden (`docs/corner-pocket-operations.md:23`). | **Closest honest version:** a *Second chance* action, allowed only before any round-2 match has started. It draws **one** round-1 loser uniformly at random, shows the drawn name for confirmation, and places them into a round-2 slot that is still a **bye**. That makes the bye a real match; it never overwrites a signed result. The draw is audited (who, from which pool). Label it "random draw" so it is never read as a result. If no bye slot exists, refuse with a reason. Needs a design note before code. | P2 | (d) |
| **R7** | 1 (+ thread) | 「[bug] 無限輪迴 無法產生冠軍」 → winner keeps advancing; no champion | bug | **covered** (as a property; F1 fixed on `main` `4947c45`: forfeit + *Not here* in the Matches bracket card, each confirmed) | Ours cannot loop. The draw stops at a single final (`if len(current) == 1`, `operations.py:292`). The event completes when the last match completes (`operations.py:187`). There are no ad-hoc "advance" layers. Test `test_all_bracket_sizes_finish_once` (`tests/test_operations.py:139`) plays sizes 2–9 and 17 and asserts exactly `count − 1` played matches plus a final winner. Probe: 5 entrants finished in 3 rounds with a winner. | Keep it as a pinned property: "a finished bracket yields exactly one champion, and renames never change it". Extend the test with a rename between rounds (see R12). **Related gap:** there is no champion display (see R10), and the forfeit fallback is unreachable (finding F1: `queueCard` at `ops.js:42` is never called). Wire the forfeit and match-level *Not here* controls into the bracket (`ops.js:46`). | P1 | (a) |
| **R8** | 1 | 「個人對戰紀錄 … 跟所有人單獨對戰的勝率/紀錄」 → head-to-head record against every opponent | feature request | **covered** on `main` (`6c8ec0c`: head-to-head W–L, win %, sample size, forfeits apart, byes out, guests labelled by name; doubles counted by team) · was: partial | We have per-player totals only: W, L and win rate in the *Regulars* profile modal (`ops.js:77`, from `resultStats`, `ops.js:47`). There is no per-opponent breakdown anywhere; `grep` finds no head-to-head code. | In the player record (R15), add a **vs each opponent** table: opponent, W–L, win %, last met. Signed `played`/`forfeit` matches only; show byes and forfeits separately; always show the sample size. Doubles: count by team, or by partner pair, with the choice labelled. Guests are matched by name only, and the label says so. | P1 | (d) |
| **R9** | 1 | 「頁面顯示的對戰組合太少了(直列), 無法一目了然」 → too few matchups per screen | UX feedback | **partial** | *Matches → bracket by round* (`inv #44`) is a horizontal flex of round columns (`ops.css:78-79`). Each match card has `min-height:98px` (`ops.css:80`) and an 8 px gap (`ops.css:69`), with its own table/id row and status badge (`ops.js:46`). A 16-entrant first round needs about 8 × 106 px of vertical scroll. | A **compact density**: one line per side, name plus score, status as a dot; the bracket fitted to the viewport width. Keep the full card on hover or focus. A design-polish task; the polish branch's no-removal feature contract applies (the inventory file's title). | P1 | (b) |
| **R10** | 2 | 「沒辦法截圖整個賽程表 … 也沒有輸出功能 … 完整結果表發在群裡恭喜冠軍」 → no export; wants one complete results sheet to post, with the champion | feature request | **covered** on `main` (R10 commit: *Results sheet* for current + archived events, `@media print`, *Copy results as text*; champion from the final's `winnerId`) · was: missing | No export, print, share or champion surface. At `ops.js`: `export`, `print(`, `toBlob`, `clipboard` and `champion` all return 0 hits, and `ops.css` has no `@media print`. The completed event only shows its final match with the winner in brass (`ops.js:46`). | A **Results sheet** view for the current and archived events: event name, date, format, champion (the final's `winnerId`), every round, scores, byes labelled. Laid out for `@media print` / save-as-PDF, plus *Copy as text* for chat. Everything is drawn from signed data; a bye is never called a win. No server-side image rendering, and no new GET that writes. | P1 | (d) |
| **R11** | 2 | 「Why 1v1 (左上藍色標籤) 需要組隊?」 → a 1v1 event still shows team forming | UX feedback | **covered** | The format controls the seat count. Singles shows one *Regular/Guest* seat per entrant, doubles shows *Regular* plus *Partner* (`ops.js:43`). The server enforces 1 or 2 members (`operations.py:248`); the probe confirmed 2 members in singles are refused. The format is locked once entrants exist (`operations.py:231`). | Nothing to fix in our flow. Guard it with a UI test that singles registration renders exactly one seat and no *Partner* field, in both languages. | P2 | (a) |
| **R12** | 2–3 (+ thread) | 「我嘗試直接改名字 結果那個人就不見了」 (強需求) → renaming a player mid-event makes them vanish | bug | **covered** on `main` `a30a846` (steps 1–3; step 4 is track (c)) · was: missing (as a guarantee) | Ours never drops a player on rename. Matches reference entrant ids, and the probe showed `sides` unchanged after renaming. But entrants store a **name copy**, `dict(pid=…, name=…)` (`operations.py:262`), which `player_save` does not update (`operations.py:192-200`). The live views prefer the roster name, `player(m.pid)?.name||m.name` (`ename`, `ops.js:25`). The **archived-events** reader prefers the copy, `p.name||player(p.pid)?.name` (`ops.js:46`), so archives show the old name. Renaming a regular to a current guest's name is accepted (probe), because uniqueness is checked only against the roster (`operations.py:194`); two different people then read the same. `guest_promote` links only the current event (`operations.py:207-218`); probe: 0 archived entries linked. `test_renamed_regular_cannot_enter_twice` (`tests/test_operations.py:347`) pins only re-entry. | **Property:** "renaming never detaches a player from their matches or stats, and the displayed name is the current one everywhere." Four steps: (1) the archive reader prefers the roster name, as `ename` does. (2) `player_save` refuses a name that collides with a current guest, or asks to link them. (3) A test renames between rounds, finishes the event, and asserts the same champion, the same `resultStats` and the new name in current and archived views. (4) Postgres: `entrant_members.player_id` stays authoritative and `name` is a snapshot (`docs/postgres-design.md:143`). | P0 | (a) + (c) |
| **R13** | 3 | 「去掉@後可以 at人了 但是像我的名字找不到」 → some names cannot be found by search | UX feedback | **partial** | *Regulars → Roster* search is a single case-insensitive **substring** over `name + status` (`ops.js:77`, input handler `ops.js:86`). A multi-word query whose words are split by punctuation fails. Example: `ann-marie lee` does not match `Ann-Marie (Annie) Lee`, but matches when split into words. There is no width or accent folding. The *Registration desk* has no search at all: it is a plain `<select>` of unregistered regulars (`ops.js:43`). The reference product's employee-directory lookup is not applicable (R14). | Match **each word** independently (AND), after `normalize('NFKC')` plus case folding (full-width, accents). Search on name only; status has its own filter. Give the registration desk a type-to-filter field over the same matcher. EN/中 placeholder parity. | P1 | (b) |
| **R14** | 3 | 「要搜尋超過十秒」 → searching a name takes over 10 s | UX feedback | **not applicable** | The delay comes from the reference product's remote directory lookup. Ours filters in memory on each keystroke, with no network call (`ops.js:77`, `ops.js:86`: no `fetch`). | Nothing to fix for us. Keep the property: local, instant search with no remote directory. If the roster grows past about 1,000 rows, debounce the re-render. (Polish only.) | P2 | (b) |
| **R15** | 3–4 (+ sidebar image) | 「個人分析只能分析統計某一場賽事 … 從古至今的個人分析」 → player analytics should be all-time, not per event | feature request | **covered** on `main` (`6c8ec0c`: read-only *Player record* from Regulars — totals, by event, head-to-head, scope line) · was: partial | Our numbers are already all-time: `resultStats` iterates `[tournament(), ...history]` (`ops.js:47`). They sit only in a *Regulars* modal as four tiles (`ops.js:77`). *Matches → Archived events* is a flat `<details>` list with no per-player view (`ops.js:46`, `inv #47`). The tabs are reachable without opening an event (`ops.js:40`). | A **Player record** page, all-time, reachable from Regulars: totals; per-event results; the head-to-head of R8; a chronological list of results. Label it "all events since <first archived date>". A cumulative chart only if every point is a signed result, and never with a fabricated trend line. Read-only. Track (c) will need an index on `entrant_members.player_id` for this query. | P1 | (d) |

## Items the screenshots show that the document does not request

Parity checks only. None is a requirement.

| Reference feature | Ours | Note |
|---|---|---|
| Undo a decided result (撤销结果) | **Deliberately absent.** Completed results are immutable (`operations.py:302`; `docs/corner-pocket-operations.md:21`). | Keep the rule. A correction flow, if ever needed, is an audited *amend* with a reason, never a silent undo. |
| Reshuffle undecided players (洗牌未决选手) | **Absent.** The draw order is the registration order (`rackHint`, `ops.js:4`). | Seeding choice (registration order / random / rating) could join R3's pre-draw step, shown before the draw. |
| Champion card (本届冠军) | **Missing.** | Covered by R10. |
| Cumulative win-rate chart (累计胜率) | **Missing.** | Covered by R15, under the signed-results-only rule. |
| History with a count badge (比赛历史) | **Partial.** Archived events exist (`inv #47`) but have no count badge or page. | Covered by R15. |
| `LIVE` tag on an event | **Not adopted.** A manual event is never called "live" unless a table has a live match (`live` status). | The standing rule: the UI never claims what it cannot prove. |

## What the product already does (for orientation)

Per the polish inventory and the operations doc:
- One current event plus archived `history`, singles or doubles, single elimination with **native byes**.
- Table assignment, manual race scoring with an explicit *sign*, absences, and a server-side forfeit. The forfeit is
  unreachable in the UI (finding F1).
- Guest entry with promotion to regular, per-player W/L/win-rate tiles over all events, and a bounded, bilingual
  audit log. See `inv #27–60`, `docs/corner-pocket-operations.md`, `docs/handoff.md`.

The Postgres design (`docs/postgres-design.md:125-160`) already has `tournaments.archived_at`,
`entrant_members.player_id` with a name snapshot, and `matches.result IN ('played','forfeit','bye')`. The R1 hide
flag and the R15 query index are its only additions from this matrix.
