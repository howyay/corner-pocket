# Corner Pocket: information-architecture (tab structure) assessment

The owner's question: *"The UX/UI is still questionable. For example, the first 3 tabs can be combined? Idk research and assess."*

This is research and a proposal. **No app code was changed.**

| Pass | Content | State |
|---|---|---|
| 1. Desk | Tab/feature map from code, content-overlap audit, external patterns, multi-device reality | **done** (`c571d67`) |
| 2. Measure | Task costs at 1280 and 390 on a seeded scratch fixture, screenshots `out/ia/current-*.png` (§8) | **done** |
| 3. Propose | 2–3 structures, mapping of all 167 + 14 items, estimated costs, recommendation, wireframes `out/ia/` | pending |

Evidence base: `main` at **`b3f542d`**, which includes the Impeccable design merge `ae1c185`. Line references such as `ops.js:140` are to that commit. `annotator/ops.js` renders each screen as one very long line, so a line number names the screen, not the exact spot.

## 0. Which inventory is "the 167"

- `docs/corner-pocket-functional-inventory.md` is the **design-prototype spec**: 78 checklist items describing the DC/React prototype, not this app.
- The 167-item no-removal contract is **`docs/impeccable-feature-inventory.md`** (merged in `ae1c185`; byte-identical to `impeccable-polish:docs/impeccable-feature-inventory.md`). This assessment maps against it.
- **The 167 list is stale against `main`.** Fourteen user-visible features that exist in `ops.js` today have no item there. So that no feature is lost, they get supplementary ids **S1–S14**. Each one was checked with a literal grep of `ops.js`, and a case-insensitive grep of the inventory found no item for it.

| id | Feature (today's tab) | Code evidence |
|---|---|---|
| S1 | First-night guide: three steps, each a tab button (Floor) | `firstRun()` `ops.js:52` |
| S2 | Rename the event after the draw (Set up) | `#rename-form`, `tournament_rename` |
| S3 | Delete an event that has nothing signed (Set up, end of night) | `event-delete`, `tournament_delete` |
| S4 | Registration-desk search box and its "no match" note (Set up) | `.desk-search`, `deskFilter()` |
| S5 | Random doubles pairing: solo pool, draw/re-roll, accept, clear (Set up) | `pairingCard()` `ops.js:83` |
| S6 | Results sheet: open, print, copy, back (Matches) | `resultsSheet()` `ops.js:81` |
| S7 | Second chance (revival): draw, undo (Matches) | `revivalCard()` `ops.js:82` |
| S8 | Bracket density: compact/full (Matches) | `density`, `cp-ops-density` |
| S9 | Event table: tonight, signed results only (Matches) | `eventTable()` |
| S10 | Per-match Away/Here and Forfeit buttons on live bracket cards (Matches) | `matchControls()` `ops.js:54` |
| S11 | Archived events: rename, hide, show hidden, delete (Matches) | `rename-archived`, `event-hide`, `toggle-hidden`, `event-delete` |
| S12 | Player record: by event, head-to-head (Regulars) | `recordView()` `ops.js:90` |
| S13 | Forget a face (Regulars profile) | `face-forget` |
| S14 | Back room "For maintainers" collapsible, holding the status table and roadmap | `statusScreen()` `ops.js:137` |

**Proposals in pass 3 must house 167 + 14 = 181 items.**

## 1. Current state: the tab → feature map (from code)

The nav is `['floor','setup','matches','vision','players','status']` in `render()` (`ops.js:49`). The active tab is an in-memory variable, `tab='floor'` (`ops.js:6`). There is no URL routing: `location.hash`, `hashchange`, `pushState`, `URLSearchParams` and `location.search` have 0 hits across `ops.js`, `app.js`, `vision-stage.js` and `ops.html`.

| # | Tab | Sections, in render order | 167 items | Supplements |
|---|---|---|---|---|
| – | Shell, every tab | Brand, connection badge, 6 tabs with counters, EN/中, theme, header strip (clock and focused score, tabs 2–6), message line, 409 conflict, busy lock, navigation veto, leave guard, sticky header, offline screen, reduced motion | 1–15 | – |
| – | Shot clock, 3 views of one local state | Floor scoreboard; header strip on tabs 2–6; Vision stagebar at ≤750 px | 16–26 | – |
| 1 | **Floor** | First-night guide (before the draw) → scoreboard for the focused match (focus picker, A/B, +/−, Win frame, Waiting on…/Here now, Clear, Release table, Sign) → tiles (Cards signed, Up next, Entrants, Guests tonight) | 27–34 | S1 |
| 2 | **Set up** | The night (name, format, race, tables; locked after the draw, with rename) → Random pairing (doubles) → Registration desk (search, member/partner, guest name, Add, **Rack the night**) → Entrants (Here/Not here, Remove) → End of the night (Archive & new, Delete event) | 35–40 | S2–S5 |
| 3 | **Matches** | Tiles (event, format, race, signed, live, delayed) → Results sheet button → Second chance → Scorekeeper's card (match select, A/B score, Save, Sign) → density toggle → Bracket by round (**Send to table**, Here now, Away/Here, Forfeit) → Event table → House standings → Night log → Archived events (rename, hide, delete) | 41–47 | S6–S11 |
| 4 | **Vision** | One stage, cues rail, inspector, chip row and `SOURCE ▾`, scrub strip, identity, enrol from footage, keyboard | 61–160 | – |
| 5 | **Regulars** | Tiles → Roster (search, filter, `+` new) → Profile modal (edit, delete, enrol face, forget face, Player record) → Guests tonight (Add to regulars) | 48–56 | S12, S13 |
| 6 | **Back room** | Table appearance → Operator notes → For maintainers ▸ (status table, roadmap) | 57–60 | S14 |
| – | Cross-cutting | 中/EN parity, 390 px, ≤1100 px, touch targets, read-only GETs, shell does not intercept the review, no fake data | 161–167 | – |

Check: 15 + 11 + 8 + 6 + 7 + 100 + 9 + 4 + 7 = **167**. Vision alone is 100 of the 167 (60 %). The "first 3 tabs" hold 21 items plus S1–S11.

### Cross-tab jumps built into the code

| Trigger | Where | Jump | Evidence |
|---|---|---|---|
| *Send to table* | Matches bracket card | **→ Floor**, focused on that match | `ops.js:140`: `focusId=id;tab='floor';render()` |
| Header score button | Tabs 2–6 | → Floor | item 7 |
| Empty board: *Go to Matches* / *Go to Set up* | Floor | → Matches / Set up | `floorScreen()` `ops.js:53` |
| First-night steps | Floor | → Regulars, Set up, Set up | `firstRun()` `ops.js:52` |
| Empty bracket / empty standings | Matches | → Set up / Regulars | `emptyNote(…,'tab:setup')`, `'tab:players'` |
| *Rack the night* | Set up | **none**: the operator stays on Set up, and the bracket that was just drawn is on Matches | `tournament-start` handler `ops.js:140` |

## 2. One night's flow, read from the code

The measurements in pass 2 will replace these predictions with counts.

1. **Register** (Set up): settings → search or pick each entrant → *Add* × N → *Rack the night*. The screen does not move to the bracket.
2. **Send** (Matches): scroll past 6 tiles, the results-sheet button, second chance and the scorekeeper's card to reach the bracket, then *Send to table*. This **jumps to Floor**.
3. **Send the next match**: Floor has an *Up next* tile, but it shows only side A's name and has **no Send button**. So the operator goes back to Matches and scrolls to the bracket again. **Two tables cost 2 round trips: Matches → Floor → Matches → Floor.**
4. **Score** on Floor. With 2 or more live tables, use the focus picker, then +/− or *Win frame*, then *Sign*. The same match can also be scored on the Matches scorekeeper's card, which works differently (number inputs plus Save/Sign).
5. **Look at the bracket and standings**: Matches again.
6. **Late arrival or absence**: before the draw, the Set up entrants list. After the draw, the Floor "Waiting on…" strip (focused match only) or the Matches card (Away/Here).
7. **Close**: Set up → End of the night → *Archive & new event*. Archived nights are then managed on Matches.

In one night the operator therefore works across **Floor, Set up and Matches**, and the Floor ↔ Matches alternation repeats once per match sent to a table.

## 3. Content-overlap audit

| Information or control | Where it appears | Assessment |
|---|---|---|
| **Live match score** | Floor scoreboard (focused match); header strip on tabs 2–6 (read-only, button → Floor); Matches scorekeeper's card (editable); bracket card (read-only) | **Two editors with different models** (per-frame +/− versus a form with number inputs). Duplicated control, not just duplicated information. |
| **Sign scorecard** | Floor footer; Matches scorekeeper's card | Duplicated. Both go through the same confirm. |
| **Shot clock** | Floor, header strip, Vision stagebar at ≤750 px | Deliberate. It is one state (items 16–18), so this is fine. |
| **Send to table** | Matches bracket only | **Hard to find**: it is the most repeated live-night action, and it sits below 4 blocks on a different tab from the one it opens. |
| **Release table** | Floor only (live match) | Asymmetric with Send, which is on Matches only. |
| **Forfeit** | Matches bracket card only | Hard to find from the table view where the forfeit happens. |
| **Attendance (here/away)** | Set up entrants (before the draw); Floor "Waiting on" (focused match); Matches card Away/Here and Here now | **Three places**, split by phase and by focus. |
| **Entrants / guests** | Set up list; Floor tiles (counts); nav counter; Regulars "Guests tonight" (Add to regulars) | Guests appear under Regulars, a tab about members, for the one action that promotes them. |
| **Up next** | Floor tile (side A's name only) | Shows the queue but cannot act on it. |
| **Bracket** | Matches only | Not beside the scoreboard anywhere, so no single view suits a TV. |
| **Standings / "who is good"** | Matches: Event table (tonight, signed) and House standings (all-time, by rating); Regulars: roster rank and rating, profile tiles, Player record | Three shapes of the same question on two tabs. |
| **Event identity and settings** | Set up (form, rename after the draw); Matches tiles (event, format, race); Matches archived-event rename | Rename lives in two places for two kinds of event. |
| **End of night / archive** | Set up (Archive & new, Delete); Matches (archived: rename, hide, delete) | Archive is created on one tab and managed on another. |
| **Face enrolment** | Regulars profile (photo); Vision (enrol from footage); Forget on Regulars | Two entry points. Reasonable (photo versus footage), but not cross-linked. |
| **Set up after the draw** | Mostly a locked form (item 36), plus rename and end-of-night | The tab is live for about the first and last few minutes of a night. |

## 4. External patterns (evidence first, opinion marked)

### Pool and tournament tools: **evidence** (vendor documentation, read)

- **DigitalPool Tournament Builder.** In the **Tables** section each table has **Mobile scoring, Tablet scoring and TV display** buttons. "Any new match that is assigned to that table will automatically appear in the tablet scoring UI." Players *Submit scores*, the match shows as pending, and the director clicks *Approve Scores* "to advance the players in the bracket and release the table." Setup and overlays are separate menus. Source: [DigitalPool Quick Start](https://docs.digitalpool.com/tournament-builder-quick-start-guide).
- **CueScore Jumbotron.** It "Displays all planned & ongoing matches in real time", is "Optimized for big screens", has a customizable grid of tables, and is "Available as a link/URL – just like our scoreboards and score overlay." It is reachable from the dashboard and from the public venue page. Source: [CueScore Jumbotron](https://cuescore.com/cuescore/posts/Jumbotron/50000000).
- **CueScore Pro.** "Assign a tablet to the table and let players keep track of scores in real-time, frame by frame." Source: [CueScore Pro](https://cuescore.com/pro/).
- **Challonge.** A **Stations** tab creates stations (tables, courts…) and assigns matches to them manually or automatically. A **Queues** tab gives "a single view for showcasing current station assignments and upcoming matches", with a **Full Screen** option per station. Sources: [Challonge stations](https://kb.challonge.com/en/article/how-to-create-and-assign-stations-j1xavx/), [Challonge station queue](https://kb.challonge.com/en/article/station-queue-1qqvk9x/).
- **APA Scorekeeper.** The official APA/CPA league scoring app, a separate app designed for iPad, used at the table. Source: [App Store listing](https://apps.apple.com/us/app/apa-scorekeeper/id1480884510). *Unverified:* I read only the store description, not the app's navigation.

**Pattern (opinion, drawn from the evidence above).** All three tournament tools put *queue plus table assignment* in one view: DigitalPool Tables, Challonge Queues. They give the **TV and the table their own URL-addressable, controls-free views**, and keep setup elsewhere. None of the documents shows a single tab bar serving the director, table scorers and spectators alike.

### General IA guidance: **evidence** (NN/g, read)

- **Tabs are for content users do not need at the same time.** Use tabs "When users don't need to simultaneously see information presented under different tabs. Otherwise, users must repeatedly switch between tabs to compare or reference information." Also: "The fewer tabs, the better", and default tabs get more attention than the others. Source: [NN/g, Tabs, Used Right (Sunwall, 2024)](https://www.nngroup.com/articles/tabs-used-right/). Applied here: the queue (Matches) and the table (Floor) are used *together* for every send, which is the case NN/g warns about.
- **Modes cost awareness.** Mode slips happen "when the user is not aware of the currently active mode", and modes lower the "discoverability of mode-specific features." Source: [NN/g, Modes in User Interfaces (Laubheimer, 2019)](https://www.nngroup.com/articles/modes/). This is the main risk for any phase-driven "Tonight" page that hides controls by phase.
- **Top tasks.** Peak moments make the top task dominate. Source: [NN/g, top tasks](https://www.nngroup.com/articles/top-tasks/). *Opinion:* on a match night the top tasks are the four the owner named, and the IA should be judged on those, not on the 181-item total.
- **Local navigation.** Local navigation is "contextual to the user's current location — showing sibling pages within the current category". Source: [NN/g, Local Navigation (Laubheimer)](https://www.nngroup.com/articles/local-navigation/). *Opinion:* this is the pattern for keeping Tonight's phases, or Records' sub-views, visible as siblings instead of hiding them.
- **League scoring on the player's phone.** In CompuSport's league app the player's own match comes first ("Your matches will be the first on top"), then *Enter Score*, then *Send for Approval*, and "The opposing team will need to approve the match." Source: [CompuSport, How to scorekeep on the app](https://compusport.freshdesk.com/support/solutions/articles/44002057637-how-to-scorekeep-on-the-new-app-). This is the same *submit → approve* split as DigitalPool's *Submit scores → Approve Scores*.
- **Task-based versus object-based IA:** no primary source was found that I could read and cite. **Opinion only.** Today's tabs mix the two models. Floor, Set up and Matches are *tasks and phases* of one object, tonight's event. Regulars is an *object* (people), and Back room is a *place*. The evidence above points the same way: operators organise by the night's phases, and everyone else by their own object (my table, the bracket).
- **Setup → Run → Review.** *Evidence:* DigitalPool separates *Setup*, the *Tables* runtime and *Overlays*; Challonge adds a *Queues* runtime view once stations exist. **I found no primary source that names a "Setup → Run → Review" pattern.** It is used here as a label, not as a citation.

## 5. Multi-device reality: what exists today

| Device role (the owner's) | Needs | What exists today | Evidence |
|---|---|---|---|
| Front-desk computer, 1 operator | Everything; a fast send/score loop | 6 tabs; Floor ↔ Matches alternation | §2 |
| Staff phones | Their table's score, check-in, send/sign | The same 6-tab UI at 390 px. Nav counters are hidden (`ops.css:184`). Every destructive control (archive or delete event, delete regular) is on the same surface as scoring. | `ops.css:175–184` |
| TV / big screen | Scoreboard plus bracket, full-screen, no controls, updating by itself | **Nothing.** No display route or mode (0 hits for `requestFullscreen`, `kiosk`, "display mode" in the 4 front-end files). Scoreboard and bracket are on different tabs. **No auto-refresh:** `ops.js` reads `/api/operations` only on load, after its own write, on a 409, on Back room *Refresh* and on Vision's roster reload. Its only timer is the 200 ms clock paint (`ops.js:144`). A TV would stay stale until someone reloads it. | greps above |
| Players' phones | Read-only bracket | **Nothing public.** No read-only view or share link. The hosted site is behind Cloudflare Access with the allow policy limited to the owner's address. *Unverified:* taken from `docs/unified-workbench.md:13–16`; the live Access policy was not inspected. Any device that does get in has full write power; there are no roles. | `docs/unified-workbench.md` |
| Any second device | The same shot clock | The clock is **per browser**: "runs only on this browser … does not … update other devices" (`clockNotice`, item 26). The server-authoritative clock (`GET/POST /api/clock` plus SSE) is on the unmerged `clock-sync` branch. | `git merge-base` check |

**Desk conclusion (opinion, to be tested in pass 2).** One tab bar does not serve the four roles. Two of them, the TV and players' phones, have no surface at all, and the blocker is not the tab structure: it is the missing auto-refresh, the missing routes and the access policy. Merging the first 3 tabs addresses only the front-desk role.

## 6. Problems, preliminary ranking by evidence

Pass 2 will attach measured costs and may re-rank.

1. **The live-night loop is split across two tabs.** *Send to table* exists only on Matches and jumps to Floor, so every match sent is a Floor ↔ Matches round trip. Scoring and signing exist twice, with two interaction models. *Evidence: code (`ops.js:140`, `ops.js:53`, `ops.js:84`); NN/g on tabs used together.*
2. **Two of the four device roles have no surface.** The TV and players' phones have no route, no read-only view, no auto-refresh and a per-browser clock, and access is owner-only per the docs. *Evidence: greps, `clockNotice`, docs.*
3. **Attendance and people data are scattered.** Absence is handled in 3 places, guests on 2 tabs, standings in 3 forms. *Evidence: code, §3.*
4. **Run-time and history are mixed on Matches.** Send, forfeit and the scorekeeper's card sit on the same long page as the night log, archived events, standings and the results sheet. *Evidence: code order in `matchesScreen()`; scroll cost to be measured.*
5. **Set up is dead weight after the draw,** and admin controls are reachable from every device. *Evidence: item 36, S2/S3; §5.*
6. **Phone navigation into and out of Vision.** At ≤750 px the tab bar and strip are hidden on Vision (`ops.css:448`), and no exit control was found in `vision-stage.js`. **Measured (§8):** at 390 px the only way out of Vision is the brand link, which reloads the page at `/`.

*§9 re-ranks these problems with the measured costs.*

## 8. Measured task costs (current structure)

### Harness

- **Isolation:** one ephemeral smolvm guest (Alpine 3.22, 2 vCPU, 3 GB). Inside it run one fixture on guest loopback **`:8210`** and **one** headless Chromium 142 driven over CDP. The fixture is `out/ia/serve_ia.py`, a copy of `tests/serve_workbench_fixture.py` with the port as an argument and a guest-local root `/fx`. The driver is `out/ia/measure.js` and the runner `out/ia/run.sh`.
- **Origin assertion:** `location.origin === 'http://127.0.0.1:8210'` was asserted **165 times**, before and after every action. The driver refuses any origin that is not `127.0.0.1:82xx`. The guest has no `--allow-host-loopback`, so it **cannot reach production `:8130`** even by mistake.
- **Mounts:** the repo **read-only** (a write was refused: `touch: /repo/x: Read-only file system`), plus one scratch `io/` directory under `~/.cache/pool-ia/`, outside the repo.
- **Seed:** only through the fixture's own API (`POST /api/operations`, 129 writes, all 200). There were 10 regulars. The night was **8 entrants** (6 regulars and 2 guests), singles, race to 3, 4 tables, bracket drawn, **2 matches live on tables, 1 signed** (`{"entrants":8,"matches":7,"live":2,"signed":1}`).
- **Run:** 01:44:07–01:45:27 UTC. 0 page errors, 0 fatal. 4 confirm dialogs, all *Sign this result?*, all accepted.
- **Counting rules:**
  - *Tab switch* = a click on a `#nav` tab.
  - *App jump* = the app changed tab by itself.
  - *Click* = any click or tap, including choosing a select option or focusing a field before typing.
  - *Scroll* = the next target was outside the viewport, so the page had to move. *px* = how far.
  - Viewports: 1280×800 desktop, and 390×844 mobile with touch emulation.
  - Every task starts from a **cold load**, which lands on Floor.

### Results

| Task (the owner's four) | Width | Tab switches | App jumps | Clicks | Keystrokes | Scrolls (px) |
|---|---|---|---|---|---|---|
| **T1 Registration + check-in → rack → see the draw.** Settings; 6 regulars through desk search + 2 guests; one *Not here* → *Here now*; *Rack the night*; open the bracket | 1280 | **2** | 0 | 25 | 64 | 2 (380)¹ |
| | 390 | **2** | 0 | 25 | 64 | 4 (2,111) |
| **T2 Send → score → sign → send the next** (match A to a table, play it 3–1 on Floor, sign; then send match B) | 1280 | **2** | **2** | 9 | 0 | 0 |
| | 390 | **2** | **2** | 9 | 0 | 2 (500) |
| **T2b Score + sign the second live table** (2 live; focus picker, +1, sign) | 1280 | 0 | 0 | 3 | 0 | 0 |
| | 390 | 0 | 0 | 3 | 0 | 1 (333) |
| **T3 See the bracket, tonight's table and the house standings** | 1280 | 1 | 0 | 1 | 0 | 3 (886) |
| | 390 | 1 | 0 | 1 | 0 | **3 (1,978)** |
| **T4 Open Vision, then get back to Floor** | 1280 | 2 | 0 | 2 | 0 | 0 |
| | 390 | 1 + **no way back** | 0 | 1 | 0 | 0 |

¹ Corrected by hand. The raw log (`out/ia/measure-results.json`) says 3 scrolls, 633 px. One of those was a 253 px "scroll to the tab bar", which is an artefact of the driver: at 1280 the header, including the nav, is `position:sticky` (`ops.css:59`), so the tab bar never leaves the screen. At 390 the header is `position:static` (`ops.css:176`), so the nav scrolls in the 390 rows are real: 549 px in T1, 217 px in T2.

### What the numbers show

1. **Send is the loop's weak point: 4 tab changes per 2 matches sent.** Every *Send to table* is on Matches and throws the operator to Floor (`matches→floor`, twice in T2). Floor has no Send button, so each next match costs another trip back to Matches (measured `Floor offers a Send button: false`). The cost grows with the table count: one round trip per match, about 7 per 8-entrant night and about 15 per 16-entrant night. **This is exactly the Floor ↔ Matches alternation.**
2. **Scoring itself is cheap once you are on Floor.** T2b, with 2 live tables, costs 3 clicks and 0 tab switches at 1280. The focus picker works. **Merging tabs will not make scoring cheaper. It will make *getting to the right thing to score* cheaper.**
3. **Racking the night leaves the operator on Set up.** The drawn bracket is on Matches (measured: `after Rack the night the app shows: setup`). Then, at 390, the operator must scroll 549 px to reach the tab bar (the header is `position:static` at ≤750 px, `ops.css:176`) and 598 px more to reach the bracket.
4. **At 390 the tab bar costs a scroll almost every time.** The header plus nav is **344 px tall on Set up and Matches**, 41 % of an 844 px screen: the nav wraps to two rows of 3 (104 px), with the strip below. After any scroll, the tabs are off-screen.
5. **Matches is a very long page on a phone.** It is 3,733 px tall at 390 on the seeded night (4.4 screens) and 1,940 px at 1280. Measured positions at 390: the first *Send to table* is at **y = 1,978**, the bracket at 1,136, the event table at 1,583, the standings at 2,078. The scorekeeper's card (743) sits above the bracket. So the most frequent live action is 2.3 screens down.
6. **The compact bracket hides its own Send button.** In the default *Compact* density, `.card-actions` is `display:none` until the card is hovered, focused or selected (`ops.css:144–145`). On a touch screen the operator must tap the card first to reveal *Send to table*. The driver clicked the button through the DOM, so **T2 and T3 undercount by 1 tap per send at 390**, and at 1280 whenever the mouse is not already over the card.
7. **Vision on a phone is a dead end.** At 390 the nav and strip are hidden (`ops.css:448`). The only visible exit is the brand link (`href="/ops.html"`, which 308-redirects to `/`), a **full reload** that also resets unsaved state. At 1280 the nav stays visible.
8. **Registration is dominated by typing and form work, not by navigation.** T1 is 25 clicks and 64 keys, with only 2 tab switches. A structural change cannot remove much of that. The registration desk itself (search to select, then Add) is the lever.

### Known gaps in the measurement

- **T4's "select a cue" step was not measured.** In the guest, `/api/video?dataset=vod30` answered 404 twice. The fixture links the videos through `/repo/data`, and `safe_file()` refuses a path that resolves outside `/fx/data`. The review workspace therefore stayed on *Loading the review workspace…* (see `current-vision-390.png`). T4 measures only getting into Vision and out of it. Cue-level costs are unchanged by any option below, because Vision stays one surface in every option.
- The driver's clicks do not include the **reveal tap** of note 6.
- **Only one operator was simulated.** Multi-device behaviour (TV, phones) was assessed from code (§5), not measured, because no such surface exists to measure.

### Screenshots (`out/ia/`)

| File | What it shows |
|---|---|
| `current-floor-empty-1280.png` | Cold load with no draw yet: first-night guide, empty board |
| `current-setup-registered-1280.png`, `current-setup-registered-390.png` | Set up with 8 entrants, before the rack |
| `current-matches-drawn-1280.png`, `current-matches-drawn-390.png` | Matches right after the rack: nothing on a table |
| `current-floor-night-1280.png`, `current-floor-night-390.png` | Floor on the seeded night: 2 live tables, focus picker, *Up next* tile with no button |
| `current-matches-night-1280.png`, `current-matches-night-390.png` | Matches on the seeded night: tiles, scorekeeper's card, bracket, event table, standings, night log, archived events. Full page, 1,940 px and 3,733 px tall. |
| `current-vision-1280.png`, `current-vision-390.png` | Vision: at 390 the nav and strip are hidden |
| `current-setup-1280.png`, `current-setup-390.png`, `current-players-1280.png`, `current-players-390.png`, `current-status-1280.png`, `current-floor-390-top.png` | The other tabs, for reference |

*Note:* the full-page captures show the sticky header painted at the viewport position where the capture ended (for example, mid-page in `current-matches-night-1280.png`). That is a capture artefact, not a layout bug.

### No-write proof (production and the repo)

| Check | Before (18:37:56 PDT) | After the run | Result |
|---|---|---|---|
| `out/corner-pocket/state.json` md5 | `77777777777777777777777777777777` | `77777777777777777777777777777777` | same |
| same file size and mtime | `5083 1790633155` | `5083 1790633155` | same |
| **Production journal** (`journalctl --user -u pool-workbench --after-cursor=<baseline cursor>`) | cursor saved | **0 requests, 0 POSTs** | production was not contacted at all |
| Manifest of every file under `out data annotator src docs tests` (mtime, size, path; 4,346 files) | saved | **0 diff lines** | nothing written from the scratch roots |
| Where the 129 POSTs went | – | the guest fixture's own log: `129 "POST /api/operations` | guest-local `/fx`, destroyed with the VM |

The md5 alone would not prove this, because the owner legitimately changes `state.json`. The journal and the manifest together show that the run made no request to `:8130` and wrote no file under the repo.

## 9. Problems, ranked by evidence (after measurement)

| Rank | Problem | Evidence strength | Cost it causes (measured or counted) |
|---|---|---|---|
| **1** | **The live-night loop is split between two tabs.** Send is only on Matches and jumps to Floor. Floor's *Up next* cannot send. Scoring and signing exist on both tabs with different models. | Measured, plus code | **2 tab switches + 2 app jumps per 2 matches sent** (T2). About 7 round trips per 8-entrant night and about 15 per 16. On a phone, plus 1 reveal tap per send in compact density. |
| **2** | **The TV and players' phones have no surface.** No display route, no URL state, no auto-refresh, a per-browser shot clock, and owner-only access per the docs. | Code and greps (§5) | 2 of the 4 device roles are unserved. A TV showing Floor would go stale after the first score. |
| **3** | **Phone ergonomics of a six-tab bar.** The 2-row nav plus header is 344 px on Set up and Matches and is not sticky. Matches is 4.4 screens long, with Send at y = 1,978. There is no exit from Vision. | Measured | T1 at 390 is 4 scrolls and 2,111 px, versus 2 scrolls and 380 px at 1280. T3 at 390 is 1,978 px of scrolling. T4 at 390 needs a full reload to leave Vision. |
| **4** | **Racking the night does not show the result.** The operator stays on Set up, and the draw is on Matches. | Measured | +1 tab switch and a scroll on every night (T1). |
| **5** | **Attendance and people are scattered.** Absence is handled in 3 places, guests on 2 tabs, standings in 3 forms. | Code (§3) | Not measured. It is a findability cost, not a per-night click cost. |
| **6** | **Set up is dead after the draw, and admin controls sit next to scoring on every device.** | Code (§3, §5) | Risk rather than clicks: *Archive & new* and *Delete event* are reachable from any staff phone. |

**The owner's question, answered on the evidence: yes, combine the first three tabs, but for the loop, not for tidiness.** The measured cost is concentrated in one place, Send (Matches) ↔ Score (Floor). Registration (T1) and scoring (T2b) are cheap or form-bound. Pass 3 tests how much each structure removes.

## 7. Method and rules followed

- Pass 2 (measurement) is described in §8 and did not contact production either. Pass 1 was desk-only: `annotator/ops.js` (the `render()` nav and every `*Screen`/card renderer), `ops.css`, `docs/impeccable-feature-inventory.md`, `docs/corner-pocket-functional-inventory.md`, `docs/unified-workbench.md`, and git history (`clock-sync` not merged).
- **Production (`:8130`) was not touched in this pass:** no browser, no fixture, no requests.
- Web sources were fetched read-only and are cited inline. Anything I did not read is marked *unverified* or *pending*.
