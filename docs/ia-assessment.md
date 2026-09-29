# Corner Pocket: information-architecture (tab structure) assessment

The owner's question: *"The UX/UI is still questionable. For example, the first 3 tabs can be combined? Idk research and assess."*

This is research and a proposal. **No app code was changed.**

| Pass | Content | State |
|---|---|---|
| 1. Desk | Tab/feature map from code, content-overlap audit, external patterns, multi-device reality | **done** (`c571d67`) |
| 2. Measure | Task costs at 1280 and 390 on a seeded scratch fixture, screenshots `out/ia/current-*.png` (§8) | **done** |
| 3. Propose | Three structures, mapping of all 167 + 14 items, estimated costs, recommendation, wireframes `out/ia/` (§10–§13) | **done** |

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

## 7. Method and rules followed

- **Pass 1 (desk):**
  - Read `annotator/ops.js` (the `render()` nav and every `*Screen`/card renderer) and `ops.css`.
  - Read `docs/impeccable-feature-inventory.md`, `docs/corner-pocket-functional-inventory.md` and `docs/unified-workbench.md`.
  - Checked git history (`clock-sync` not merged).
  - No browser, no fixture, no requests.
- **Pass 2 (measurement):** see §8. One VM, one fixture on `:8210`, one browser. **Production `:8130` received 0 requests in the whole session** (journal checked from a saved cursor).
- **Pass 3 (proposal):**
  - Built from passes 1 and 2.
  - The option costs in §12 are estimates, labelled as such.
  - The wireframes are low-fidelity and are not app code.
- **No app code was changed.** The only committed file is this document. The screenshots, harness and wireframes are in `out/ia/`, which is gitignored like the rest of `out/`.
- **Web sources** were fetched read-only and are cited inline. Anything I did not read is marked *unverified*. Where no primary source was found, the text says so and marks the claim as opinion.

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

1. **Send is the loop's weak point: 4 tab changes per 2 matches sent.** Every *Send to table* is on Matches and throws the operator to Floor (`matches→floor`, twice in T2). Floor has no Send button, so each next match costs another trip back to Matches (measured `Floor offers a Send button: false`). The cost grows with the number of matches: one round trip per match, about 7 per 8-entrant night and about 15 per 16-entrant night. **This is exactly the Floor ↔ Matches alternation.**
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

## 10. Three alternative structures

All three keep every one of the 181 items (§11). They differ in what they merge and in whom they serve.

### Option A: one "Tonight" workspace, phase-driven (a merge of Floor, Set up and Matches)

```
Tonight  ─┬─ phase strip: Register · Rack · Play · Close   (all four always clickable; default = the night's phase)
          ├─ Register : The night · Random pairing · Registration desk · Entrants/attendance · Rack the night
          ├─ Play     : Queue (ready/held, Send → table) │ Tables (scoreboard, focus) │ Bracket + tonight's table
          └─ Close    : Results sheet · Second chance · Archive & new / Delete event
Records   (history half of Matches: House standings · Night log · Archived events · player record link)
Vision    (unchanged, one surface)
Regulars  (roster, profiles, faces; Guests tonight moves to Tonight › attendance)
Back room (appearance, notes, maintainers)
```

5 tabs instead of 6. One device model: the same app for everyone, laid out responsively.

### Option B: separate tabs by role (Desk / Table / Board)

```
Desk   (front-desk operator): The night · Registration · Entrants · Queue + Send · Close/Archive
Table  (staff phone)        : pick my table → scoreboard, +/−, Sign, Release, Forfeit, Away/Here, shot clock
Board  (anyone)             : Bracket · tonight's table · House standings · Night log · Results sheet · Archive
Vision · Regulars · Back room (unchanged)
```

6 tabs. Each tab is one role's whole job. Send lives on Desk, scoring on Table.

### Option C′ (recommended): a Tonight console plus a read-only Display

This is A's operator console, plus a separate read-only surface for the two roles that have none today.

```
/            Operator console (front desk + staff phones)
             Tonight (phase strip; Play = Queue │ Tables │ Bracket) · Records · Vision · Regulars · Back room
             ≤750 px: fixed bottom bar  Tonight · Records · Vision · More(Regulars, Back room)
/display     Read-only Display (TV and players' phones)
             Tables in play (big type) · Next up · Bracket · Tonight's table · auto-refresh · no controls
             Same page, one column at phone width = the players' bracket view
```

C′ is A for the operator plus the missing Display. The Display is also the natural home for a later *per-table* view, like DigitalPool's per-table TV/Tablet links and Challonge's per-station Full Screen.

## 11. Where every inventory item goes (167 + 14 = 181, none homeless)

Legend: **T** = Tonight (sub-area in brackets), **R** = Records, **V** = Vision, **Rg** = Regulars, **BR** = Back room, **Sh** = shell (every screen), **D** = Display (C′ only, read-only *copy*: the item's home and its write path stay in the console). For B: **Desk / Table / Board**.

| Items | Today | A: Tonight | B: by role | C′: console + Display |
|---|---|---|---|---|
| 1 Brand, 2 connection badge, 5 EN/中, 6 theme, 8 message line, 9 conflict, 10 busy lock, 11 navigation veto, 12 leave guard, 14 offline screen, 15 reduced motion | Shell | Sh | Sh | Sh; D shows 2, 5, 6, 15 (read-only) |
| **3** six tabs | Shell | **changes**: 5 tabs (Tonight, Records, Vision, Regulars, Back room). The check becomes "each tab gets `.active` and `aria-current`". | Changes: 6 role tabs | Changes: 5 tabs, bottom bar ≤750 px |
| **4** nav counters | Shell | Tonight = entrants before the draw / matches not complete after; Regulars = players | Desk = entrants, Table = live, Board = not complete | as A |
| **7** header strip (clock + focused score → Floor) | Tabs 2–6 | On every tab except Tonight › Play; the score button opens Tonight › Play | On every tab except Table | as A |
| **13** sticky header | Shell | Sh (at ≤750 px the bottom bar replaces it as the always-reachable nav) | Sh | as A |
| 16–26 shot clock (one state, 3 views; 26 label "local timer, not shared") | Floor, strip, Vision stagebar | T›Play scoreboard, strip, Vision stagebar | Table, strip, Vision | as A. **D shows no clock until `clock-sync` merges**, because a local timer on a TV would lie (item 26, rule 167). |
| 27 scoreboard, 28 focus picker, 29 sides A/B, 30 +/−, 31 Win frame, 33 footer actions | Floor | T›Play (Tables) | Table | T›Play; D mirrors 27 and 29 read-only |
| 32 Waiting on … / Here now | Floor | T›Play (Tables) + T›Register attendance | Table + Desk | as A |
| 34 Floor tiles (signed, up next, entrants, guests) | Floor | T›Play header line; *Up next* becomes the Queue, **with Send** | Desk | as A; D: "Next up" |
| **S1** first-night guide | Floor | T›Register (empty state) | Desk | as A |
| 35 the night, 36 locked notice, **S2** rename after the draw | Set up | T›Register (locked after the draw; rename stays) | Desk | as A |
| 37 registration desk, **S4** desk search | Set up | T›Register | Desk | as A |
| **S5** random doubles pairing | Set up | T›Register | Desk | as A |
| 38 Rack the night | Set up | T›Rack, **then shows T›Play** (the draw) | Desk, then shows Board | as A |
| 39 entrants list (here/not here, remove) | Set up | T›Register + attendance panel | Desk | as A |
| 40 archive & new event, **S3** delete event | Set up | T›Close | Desk | as A (console only; never on D) |
| 41 Matches tiles | Matches | T›Play header line | Board | as A; D header |
| 42 scorekeeper's card, 43 score select sync | Matches | T›Play, as the keyboard/number-entry mode of the focused table (kept, not removed) | Table | as A |
| 44 bracket by round (Send, Here now) | Matches | T›Play: queue actions (Send, Here now) + read-only bracket; full bracket in R too | Board (view) + Desk (Send) | as A; D: bracket, read-only |
| **S8** bracket density | Matches | T›Play bracket + R | Board | as A |
| **S10** per-match Away/Here + Forfeit | Matches (card) | T›Play (focused table, under "More") | Table | as A |
| **S7** second chance | Matches | T›Close (it opens after round 1) | Desk | as A |
| **S6** results sheet (print, copy) | Matches | T›Close + R | Board | as A |
| **S9** event table (tonight) | Matches | T›Play side panel + R | Board | as A; D |
| 45 house standings | Matches | R | Board | R; D optional |
| 46 night log | Matches | R | Board | R |
| 47 archived events, **S11** archived rename/hide/delete | Matches | R | Board | R (console only) |
| 48 Regulars tiles, 49 roster, 50 add, 51 profile, 52 edit, 53 delete, 54 enrol face, 55 modal close, **S12** player record, **S13** forget face | Regulars | Rg (S12 also linked from R standings) | Rg | as A (≤750 px: under More) |
| 56 guests tonight (add to regulars) | Regulars | T›Register attendance, with a link to Rg | Desk | as A |
| 57 table appearance, 58 roadmap, 59 status table, 60 operator notes, **S14** maintainers | Back room | BR | BR | BR (≤750 px: under More) |
| 61–160 Vision (stage, overlays, chip row and SOURCE panel, live vocabulary, cues rail, inspector, identity, enrol from footage, scrub strip, keyboard) | Vision | V, **unchanged**: one surface (item 61) | V | V; at ≤750 px the bottom bar stays visible, which fixes the dead end |
| 161 中/EN parity, 164 touch targets, 165 read-only API, 166 shell does not intercept the review, 167 no fake data | Cross-cutting | unchanged; they now also bind the new surfaces | unchanged | unchanged; D must satisfy 161, 165 and 167 (its GETs are read-only by construction) |
| **162** mobile 390 px, **163** tablet ≤1100 px | Cross-cutting | re-checked for the Tonight layout; Vision's bottom sheets are unchanged | re-checked | as A, plus the 44 px bottom bar sits above Vision's sheet tabs |

Count: 11 shell items + 3 changed (3, 4, 7) + 13 = 15; 16–26 = 11; 27–34 = 8; 35–40 = 6; 41–47 = 7; 48–56 = 9; 57–60 = 4; 61–160 = 100; 161–167 = 7. **Total 167. S1–S14 = 14, each placed once above. 181 in all, with no item removed.** Items whose *check line* names a tab (3, 7, 34, 44, and the "Floor opens" checks) need their check reworded, **not** their behaviour. This is the no-removal contract's own rule: "An item may move to another place only if the check on its line still passes."

## 12. Estimated task costs for each option

These are **estimates**, not measurements. They are derived by walking each wireframe with the same counting rules as §8, from the same starting state: cold load, and the same seeded night. At 390 in A and C′ the nav is a fixed bottom bar, so no scroll is ever spent reaching it.

| Task | Width | Today, **measured** (tabs + jumps / clicks / scrolls) | A: Tonight | B: by role | C′: console + Display |
|---|---|---|---|---|---|
| T1 register 8 + check-in + rack + see the draw | 1280 | 2 + 0 / 25 / 2 | **0** / 23 (the cold load lands on Tonight › Register; rack shows Play) / 1 | 1 / 24 (Desk, then Board to see the draw) / 1 | **0** / 23 / 1 |
| | 390 | 2 + 0 / 25 / 4 (2,111 px) | 0 / 23 / 3 (about 1,000 px: form, entrants, rack) | 1 / 24 / 3 | 0 / 23 / 3 |
| T2 send A → score → sign → send B | 1280 | **2 + 2** / 9 / 0 | **0** / 7 (Send in the queue, 4 score taps, Sign, Send) / 0 | **2** / 9 (Desk Send → Table: score, Sign → Desk Send) / 0 | **0** / 7 / 0 |
| | 390 | **2 + 2** / 9 / 2 (+1 reveal tap per send) | 0 / 7–8 (8 if the table has to be picked) / 1 | 2 / 9–10 / 1 | 0 / 7–8 / 1 |
| T2b score + sign table 2 of 2 | 1280 | 0 / 3 / 0 | 0 / 3 (click the table tile, +1, sign) / 0 | 1 (to Table) / 3 / 0 | 0 / 3 / 0 |
| | 390 | 0 / 3 / 1 | 0 / 3 / 1 | 1 / 3 / 1 | 0 / 3 / 1 |
| T3 bracket + tonight's table + standings | 1280 | 1 / 1 / 3 (886 px) | bracket + tonight's table: **0 / 0 / 0** (on Play); all-time standings: 1 (Records) / 1 / 0–1 | 1 / 1 / 2 (all on Board) | as A on the console; **0 interactions on the TV** (always on screen) |
| | 390 | 1 / 1 / 3 (1,978 px) | bracket + tonight's table: 0 / 1 (expand the bracket) / 1; standings: 1 (Records) / 1 / 1 | 1 / 1 / 3 | players: **0**, the Display on their own phone; staff as A |
| T4 Vision and back | 1280 | 2 / 2 / 0 | 2 / 2 / 0 | 2 / 2 / 0 | 2 / 2 / 0 |
| | 390 | 1 + **no way back** (full reload) | 2 / 2 / 0 (bottom bar) | 2 / 2 / 0 only if the nav stays visible; not in B's scope | 2 / 2 / 0 (bottom bar) |

**Per night** (8 entrants means 7 matches, all on tables, no forfeits): today costs about **14 tab changes on Send alone** (7 × (1 tab + 1 app jump)), versus 0 in A and C′ and about 14 in B, because B only moves the split. That is why B is ruled out as the main structure: it names the problem by role but keeps Send and Score apart.

## 13. Risks and build effort

| | A: Tonight | B: by role | C′: console + Display |
|---|---|---|---|
| **Removes the measured #1 cost** (the Send ↔ Score split) | Yes | **No**: it moves it (Desk ↔ Table) | Yes |
| **Serves the TV and players** (#2) | No | Partly: Board is still a control surface, with no auto-refresh | **Yes** |
| **Phone** (#3) | Yes (bottom bar; Records makes Tonight shorter) | Partly (Table is good; Desk is still long) | Yes |
| **Main risks** | *Mode slips* (NN/g): a phase that hides controls. Mitigation: all four phases are always clickable siblings, and the default phase follows the state. Also: rewording about 10 check lines in the 167 list, and rewriting `tests/test_ops.js` (69 tests, **15 references to tab ids**). | Two tabs for one night, so the split remains. Role labels do not match one operator doing every role at a small hall. | Everything in A, plus: **(1) the Display needs a refresh path.** Polling `GET /api/operations` every 2–5 s is enough at this scale. Server-sent events exist only on the unmerged `clock-sync` branch. **(2) Access:** players' phones cannot get past Cloudflare Access today (owner-only allow policy, per the docs). A read-only public path is a security decision for the owner, *not* an IA one. **(3) Shot clock on the TV:** hidden until `clock-sync` merges (rule 167, no fake data). **(4)** The CSP and security headers must cover `/display`. |
| **Build effort (1 engineer, including tests and a 1280/390 browser check)** | **4–6 days**: 2 for the Tonight shell and phase strip, 1 for Play (queue + tables + side panel), 1 for Records and the bottom bar, 1–2 for tests, rewording the inventory checks, and the EN/中 strings. | **3–4 days**: mostly regrouping existing sections. | **6–9 days**: A (4–6), plus the read-only Display route and polling (1–2), plus the phone layout of the Display and auto-scaling type for the TV (1). Access policy work, if the owner wants the Display public, is separate and not estimated here. |

Estimates are opinions. They assume the current single-file `ops.js` renderer is kept, not rewritten. An owner decision on public access could move C′ by more than any other factor.

## 14. Recommendation

**Build C′: merge Floor, Set up and Matches into one *Tonight* console, whose *Play* view puts the queue, the tables and the bracket on one screen, and add a separate read-only `/display` for the TV and players' phones.** One-sentence justification: the measured cost sits almost entirely in the Send (Matches) ↔ Score (Floor) round trip, which only a merge removes, and two of the four device roles have no surface at all, which only a Display fixes.

**Answer to the owner:** yes, combine the first three tabs, but as **one live-night workspace**, not as one long page. Keep the phases visible, move history to *Records*, and give the TV and players their own screen.

**What to prototype first, to prove it (about 1–1.5 days, throwaway, on a fixture ≥8210):** only **Tonight › Play**, with the queue (Send), the table tiles (focus + scoreboard) and the read-only bracket on one screen, at 1280 and 390, plus a 30-line `/display` page that polls `GET /api/operations`. Re-run this doc's T2 and T3 driver against it. The prototype passes if **T2 goes from 2 tab switches + 2 jumps to 0** at both widths, with no new scroll at 390, and the Display updates within 5 s of a score change. If T2 does not reach 0, do not build the rest.

## 15. Wireframes

- **HTML, low-fidelity, open in a browser:** `out/ia/wireframe-recommended.html`, with 4 frames:
  1. Tonight › Play at 1280;
  2. Tonight › Register at 1280;
  3. staff phone at 390 beside a player's phone (Display) at 390;
  4. the TV Display.
- **ASCII**, the same structure:

```
1280 · Tonight › Play (operator console)
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ ● Corner Pocket   [Tonight] Records  Vision  Regulars  Back room     EN|中 ☾|☀ [Display↗]│
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ ✓Register(8) ✓Rack [Play · 2 on table · 1/7 signed] Close      Clock 0:30 ▶ ↺ 20 30 45 60│
├──────────────────────┬─────────────────────────────────────────┬─────────────────────────┤
│ QUEUE                │ TABLES                                  │ BRACKET (read-only)     │
│ Rico–Keiko [Send→T3] │ [T1 Lulu 1–1 Alan] [T2 TJJ 2–0 Haoye]  │ R1 Wanwan 3–1 Su ✓      │
│ Yuefu–Nadia  held    │ [T3 free]          [T4 free]            │ R1 Lulu–Alan  T1        │
│   Nadia [Here now]   │ ┌ SCOREBOARD · T2 ─────────────────────┐│ R1 TJJ–Haoye  T2        │
│ R2 … waiting         │ │ A TJJ   ●●○  2  [+][−]               ││ R2 …  R3 …              │
│ ATTENDANCE           │ │ B Haoye ○○○  0  [+][−]               ││ TONIGHT'S TABLE         │
│ Nadia  not here      │ │ [Clear] [Release] [More▾] [Sign]     ││ 1 Wanwan 1/1  2 Su 0/1  │
│                      │ └──────────────────────────────────────┘│ → Records for the rest  │
└──────────────────────┴─────────────────────────────────────────┴─────────────────────────┘

390 · staff phone                         390 · player's phone = /display
┌──────────────────────────────┐          ┌──────────────────────────────┐
│ ● Corner Pocket      EN ☾    │          │ ● Friday 8-Ball Open   live  │
│ ✓Reg ✓Rack [Play 2·1/7] Close│          │ ON THE TABLES                │
│ Clock 0:30 [Start][Reset]    │          │  T1 Lulu 1–1 Alan            │
│ Table ▾ T2 · TJJ / Haoye     │          │  T2 TJJ 2–0 Haoye            │
│  A TJJ    2   [+][−]         │          │ BRACKET                      │
│  B Haoye  0   [+][−]         │          │  R1 Wanwan 3–1 Su ✓ …        │
│  [Sign scorecard] [More▾]    │          │ TONIGHT'S TABLE              │
│ NEXT UP                      │          │  1 Wanwan 1/1 …              │
│  Rico–Keiko      [Send→T3]   │          │ (no controls, auto-refresh)  │
│ Bracket ▸                    │          │                              │
├──────────────────────────────┤          └──────────────────────────────┘
│ Tonight │Records│Vision│More │  ← fixed bottom bar, always reachable
└──────────────────────────────┘
```

