# Corner Pocket: the no-removal feature contract (front-end polish)

This file lists every user-visible feature of the web app. The redesign may change how things
look. It may not remove or change the behaviour of anything listed here. Every item stays
**reachable**, and it behaves the same way: the same writes, the same refusals, the same words
(EN and 中), and the same honesty rules. An item may move to another place only if the check on
its line still passes.

Source of truth: the code on branch `impeccable-polish` at `db607ec`/`73a7b65`: `annotator/ops.html`,
`ops.js`, `ops.css`, `app.html`, `app.js`, `app.css` and `vision-stage.js`. The pinned tests are
`tests/test_ops.js` (23) and `tests/test_app_timeline.js` (60). Each feature was checked against
the code, not against the docs. **Known defects** (§19) are recorded as they are. The polish does
not have to keep a defect, but a fix must not remove the feature around it.

## How to check an item

- Serve the isolated fixture from `docs/impeccable-baseline.md`: `http://127.0.0.1:8137/`
  (reset with `out/impeccable/reset_fixture.sh`). `/` serves `ops.html`. `/ops.html` and
  `/app.html` redirect to `/` with a 308.
- Widths: 1280×599 (desktop) and 390×844 (mobile). The language and theme toggles are in the header.
- A check line has the form *click path → observable result*. `[test: …]` names the pinned test
  that already asserts the item. The test suites must stay green:
  `node --test tests/test_ops.js` and `node tests/test_app_timeline.js`.
- Unless an item says otherwise, "the rail" means the left cues rail (`#vs-cues`), "the
  inspector" means the right column (`#vs-inspector`) and "the strip" means the scrub strip
  (`#vs-strip`).

---

## 1. Shell (header, nav, strip, messages)

1. **Brand link**: the 8-ball mark, **Corner Pocket** and the tagline (`POOL HALL OPERATIONS` / `球房运营台`). Check: click the brand → the page reloads at `/` on the Floor tab.
2. **Connection badge**. Check: load the page → it reads `Connecting…`, then `LOCAL · SAVED · <revision>` (中 `本地 · 已保存 · <revision>`). Stop the server and click *Refresh* in the Back room → `UNAVAILABLE` / `不可用`.
3. **Six tabs**, in this order and with these ball numbers: 1 Floor/球房, 2 Set up/开赛设置, 3 Matches/对阵, 4 Vision/视觉, 5 Regulars/常客, 6 Back room/后台. Check: click each → it gets `.active` and `aria-current="page"`, and `#main` swaps to that screen.
4. **Nav counters**: Set up shows the entrant count, Matches the count of matches that are not complete, and Regulars the player count. Check: add an entrant → the Set up counter goes up by 1.
5. **Language toggle `EN` / `中`** (`data-lang`). Check: click 中 → every shell and Vision string is Chinese and `<html lang="zh-CN">`. Reload → still 中 (`localStorage cp-ops-lang`). The toggle is ignored while an action is in flight.
6. **Theme toggle, dark and light** (moon and sun icons, aria `Dark / 暗色` and `Light / 亮色`). Check: click the sun → `<html data-theme="light">`. Reload → it stays light (`cp-ops-theme`). The review DOM is kept and no discard prompt appears. [test: appearance changes retain review DOM without asking to discard]
7. **Header strip** (every tab except Floor): the shot clock plus one button with the focused match score (`<A> 2 – 1 <B>`), or `Tables open`. Check: on Matches, click the score button → Floor opens.
8. **Message line** (`#message`, `role=status`). Check: a successful write shows `Saved.` / `已保存。` for 4.5 s. A failure shows `Action failed: …` for 12 s. A server validation error shows the localized sentence plus a `Technical details` / `技术详情` expander with the raw detail. [test: failed API response localizes primary copy and preserves exact optional detail]
9. **Conflict handling** (HTTP 409). Check: in two tabs, change a score in tab A and then in tab B → tab B reloads the state and shows `Another operator changed the data. Latest state loaded; inspect it before submitting again.`
10. **Busy lock**: during a write every `#main` button is disabled and the tab, language and theme clicks are ignored. Check: throttle the network and press *Save* → the buttons grey out until the reply arrives.
11. **Navigation veto**: when the review engine is dirty or busy, a tab switch asks `Discard unsaved changes?`, and *Cancel* keeps you on Vision. Check: on Vision, draw a box without saving, click Floor → the prompt appears. [test: dirty or busy review vetoes top-level and subtab navigation]
12. **Leave-page guard**: `beforeunload` warns while the review is dirty or busy. Check: draw a box, then close the tab → the browser asks for confirmation.
13. **Sticky header** on desktop. It becomes `position:static` at ≤750 px, with `scroll-padding-top:16px`. Check: scroll the Matches screen at 1280 → the header stays at the top. [test: sticky header scroll inset belongs to the document scrolling root]
14. **Offline screen**: if the first `/api/operations` read fails, `#main` shows `UNAVAILABLE`, the error text and a *Refresh* button. Check: start the page with the server stopped → that card appears, and *Refresh* retries.
15. **Reduced motion**: `prefers-reduced-motion` turns off animations and transitions. Check: turn on reduced motion in the OS → no transitions play.

## 2. Shot clock (one state, every view)

16. **One clock, many views**: the Floor scoreboard, the header strip (on tabs 2 to 6) and the Vision stagebar (`.vs-clock`, shown only at ≤750 px) all paint the same `data-clock` element from one `timer`. Check: start the clock on Floor, open Matches → the strip shows the same second. On a 390 px Vision tab the stagebar shows it too. [test: the clock paints the true remaining time on the first render, in every view]
17. **Correct value on first render**: the first paint is the real remaining time, never a hard-coded `0:30`. The progress bar is painted too. Check: set 20 s, start, wait 7 s, reload → the first frame shows `0:13` (±1 s), not `0:30`.
18. **Persists across reload and tabs** (`localStorage cp-ops-clock`, `{duration, remaining, deadline}`). Check: start the clock and reload → it keeps counting. Open a second browser tab → a start or pause in one tab updates the other within 200 ms (`storage` event).
19. **Start / Pause** (`clock-toggle`). Check: *Start* → it counts down and the label becomes *Pause*. *Pause* → it freezes at the current second.
20. **Reset** (`clock-reset`). Check: *Reset* → it returns to the full duration and stops.
21. **Duration presets 20 / 30 / 45 / 60** (`clock-set`). They are saved to the server as `settings_update {shotClock}`, and the active preset is highlighted. Check: click 45 → the clock reads `0:45` and the 45 chip is active.
22. **Low-time state**: at ≤5 s the clock turns red (`.low`). Check: start a 20 s clock and wait → it turns red at 0:05.
23. **Expiry**: at 0 the clock stops and shows `Shot time expired. No penalty applied.` / `击球时间到。未自动判罚。` Check: let it run out → that message appears and no score changes.
24. **Held for absence**: *Start* is refused with `Delayed` while the focused match has an absent side. Check: in Set up mark an entrant *Not here*, then rack the night → Floor focuses the delayed match, and *Start* shows `Delayed` and does not start. (A live match cannot be marked absent from the UI: finding F1.)
25. **Automatic reset** after `match_complete`, `match_forfeit`, `tournament_new`, `tournament_start` or an absence mark. Check: sign a result → the clock returns to the full duration and stops.
26. **Label**: `Shot clock · local timer, not shared` / `击球计时 · 本机计时，不联动`. The Back room also explains it (item 70). Check: read the kicker above the Floor clock.

## 3. Floor (球房)

27. **Scoreboard** with the focused match: status badge, `Table <n> · <id8>` (or `No match on table`) and a race badge (`Single frame` or `Race to <n>`). Check: send a match to a table → its names and table appear on Floor.
28. **Focus picker** (`#focus-match`), shown only when more than one match is live or delayed. It lists live and delayed tables. Check: with two tables running, change the select → the scoreboard switches match. [test: Floor focus picker includes live and delayed tables]
29. **Side A and side B**: the name and a *leading* highlight for whoever is ahead. With race >1 there are pips (one per frame) and a large score. Check: score 2–1 → A's panel is highlighted and 2 pips are lit.
30. **+ / − score buttons** (race >1), clamped to 0 and the race length, with aria `<name> +1` and `<name> -1`. Check: press + at the race limit → the score stays at the limit.
31. **Win frame** (race = 1): it asks `Sign this result?…`, then writes score 1–0 and completes the match. Check: on a single-frame event, click *Win frame* for A and confirm → the match is signed and the winner advances.
32. **Waiting on … / Here now** strip for absent players on the focused match. Check: use the delayed match from item 24 → `Waiting on: <name>` appears with *Here now*. Click it → the match becomes schedulable (`match_absence {absent:false}`).
33. **Footer actions**: `Manual, validated scoring`, *Clear score* (to 0–0), *Release table* (only while live; `match_unschedule`) and *Sign scorecard* (confirm, then `match_complete`). Check: *Release table* → the match leaves the table and its status becomes scheduled/waiting. [test: table release and registration attendance use existing action API]
34. **Tiles**: `Cards signed` (n/total), `Up next` (the first scheduled match), `Entrants`, `Guests tonight`. Check: sign one match → Cards signed becomes `1/<n>`.

## 4. Set up (开赛设置)

35. **The night** form: *Event name* (defaults to `8-Ball Open · <Day> <m>/<d>`, 中 `<m>月<d>日 <周x> 8球公开赛`), *Format* (Singles/Doubles), *Race to* (1/3/5/7/9/11), *Tables* (1–32) and *Save* (`tournament_setup`). Check: change Tables to 4 and save → `Saved.`, and the value survives a reload.
36. **Locked notice**: after the draw the form is disabled and shows `The draw has started. Entrants and rules are locked; archive this event to start a new one.` Check: rack the night → the fieldset is disabled and the note is shown.
37. **Registration desk**: one member select per seat (two for Doubles: *Regular* and *Partner*). It lists regulars who are not registered yet as `name · rating`, with a *Guest* option and a *Guest name* box. Guests can enter without a profile (`guestNote`). Check: pick "Guest", type a name and click *Add entrant* → the entrant is listed and tagged *Guest*.
38. **Rack the night** (`tournament_start`) with the hint `Single elimination. Byes advance automatically. Registration order seeds the draw.` Check: with ≥2 entrants click it → matches appear on Matches and the form locks.
39. **Entrants list**: numbered balls, name, and a Guest/Regular tag. Before the draw each has *Not here/Here now* (`entrant_absence`) and *Remove* (`entrant_remove`). The heading counts `n · k Guests tonight`. Check: *Not here* on an entrant → the button flips to *Here now*.
40. **Archive & new event** (`tournament_new {confirm:true}`) after the confirm `Archive this event and create a fresh registration? Existing results remain in history.` Check: confirm → Set up resets, and the old event appears under Matches → Archived events.

## 5. Matches (对阵)

41. **Tiles**: event name, format, race, cards signed, live count and delayed count. Check: put a match on a table → the *On table* tile becomes 1.
42. **Scorekeeper's card** (`#score-form`), only for live matches with two sides: a *Match* select, *Side A score* and *Side B score* (0..race), *Save* (score only) and *Sign scorecard* (confirm, then score, then complete). A cancelled confirm or a failed score write never signs. Check: *Save* → the score changes and the match stays live. *Sign* and cancel → nothing is signed. [tests: named id control…; failed score write never signs a result; save-only and cancelled confirmation do not complete a match]
43. **Score select sync**: changing the *Match* select refills the A and B inputs with that match's score. Check: switch the select → the inputs show the other match's score.
44. **Bracket by round**: each match shows its table and id, a status badge, both names (the winner in brass) and the scores. Delayed matches offer *Here now* per absent side, never *Send to table*. Scheduled matches offer *Send to table* (disabled while someone is absent or a side is empty). *Send to table* opens Floor focused on that match. Check: click *Send to table* → Floor opens with that match. [test: delayed matches restore attendance rather than offering invalid scheduling]
45. **House standings**: every player by rating, with a rank badge, name, status word and rating. Check: edit a rating in Regulars → the order here updates.
46. **Night log**: the audit trail, newest first. Each line is `<date> · <action label> · <context> · v<rev>`, with bilingual action labels (for example `Result signed` / `签署赛果`). Check: sign a match → a new top line reads `… · Result signed · … · v<n>`.
47. **Archived events**: a `<details>` per archived night, with each round's matches, names, scores and status. Check: after item 40, expand the archived entry → the old bracket is shown.

## 6. Regulars (常客)

48. **Tiles**: `Active members`, `Average rating`, `Recorded results`. Check: add an Active regular → Active members goes up by 1.
49. **Roster** list (heading: finding D4) with search (`#roster-search`, which matches the name or status and keeps the caret while typing) and filters *Everyone* / *Active*. Rows show a rank, name, status, joined date and rating. Check: type part of a name → the list filters as you type and the cursor does not jump.
50. **Add a regular**: the `+` button (aria `New regular`) opens a modal with *Name* and *Save* (status Active). Check: add "Test" → the row appears and `Saved.` is shown.
51. **Profile modal** (click a row): name, status and joined date. Tiles for Rating, Wins, Losses and Win rate are computed from the current and archived events (`—` when there are none), plus `No simulated observations or fabricated statistics are shown.` Check: open a player with one win → Wins is 1 and Win rate is 100%.
52. **Edit a regular** in the modal: *Name*, *Rating* (0–1000), *Status* (Active/Visitor/Inactive), *Player notes* (≤4000, escaped) and *Save* (`player_save`). Check: set a status to Visitor → the roster row shows *Visitor*. [test: player notes are editable and safely escaped]
53. **Delete regular**, with the confirm `Delete this player? Players in event records cannot be deleted.` The server refuses a player with history (`Player has tournament history; mark Inactive instead`). Check: delete a player with results → the refusal message appears.
54. **Enroll face** (photo upload, `/api/identity/enroll`) with the hint `Choose a clear frontal photo… runs on this machine only.` The result is `<n> face(s) enrolled` or `Enrollment failed: <reason>`. Check: upload a frontal photo → `1 face(s) enrolled`.
55. **Modal close**: the × button and a click on the backdrop close it, and a click inside the modal does not. Check: click outside the dialog → it closes.
56. **Guests tonight**: a list of guest names with *Add to regulars* (`guest_promote`). Check: promote a guest → they appear in the roster.

## 7. Back room (后台)

57. **Table appearance** form: *Cloth color* (Green/Blue/Burgundy/Slate), *Lamp glow* (0–0.5), *Rail diamonds* and *Save* (`settings_update`, with numbers and an unchecked box serialized correctly). The live cloth preview is labelled `Decorative table preview only — not a camera observation.` Check: pick Burgundy and save → the preview turns burgundy. [test: appearance form serializes numbers and unchecked diamonds correctly]
58. **Roadmap · not live monitoring**: exactly nine rows (area, current capability or gap, priority) in both languages. Check: count the rows → 9, with the P1/P2 labels. [test: Back room retains nine truthful deferred roadmap areas]
59. **Status table**: State revision, the persisted operations API (`/api/operations`), Matches `Manual, validated scoring`, Live observations `Not connected`, Review `Vision · VOD`, and Shot clock (`clockNotice`). Below it is `No simulated observations…` and a *Refresh* button (re-reads `/api/operations`). Check: click *Refresh* → the revision matches the header badge.
60. **Operator notes**: a textarea (≤4000), *Add note* (`note_add`), and each note with *Remove* (`note_delete`). Whitespace is preserved. Check: add a two-line note → it shows both lines. *Remove* deletes it.

## 8. Vision: layout and the stage (one surface)

61. **One stage, two rails, no sub-tabs**: the chip row, then [cues rail | stage | inspector], then the sheet tabs (mobile) and the strip. There is no second navigation. Check: open Vision → there is no sub-tab bar, and the stage sits between the two rails. [tests: Vision is one stage with two rails and no sub-tab navigation left; app.html is one stage host with no sub-tab navigation]
62. **Review host lifecycle**: `#vision-host` sits outside the disposable `#main`, is fetched once from `/api/review-template`, and is mounted once. It is hidden (not destroyed) on other tabs: leaving Vision pauses the video and the keys stop, and coming back re-activates the same engine. Check: freeze frame 1000 on Vision, go to Floor, come back → still frame 1000 with the same selection, and the Network panel shows no second `/api/review-template`. [tests: review host is outside the disposable shell main; persistent lifecycle preserves edits…]
63. **Exactly one picture surface**: `#stage` holds one `<video id="t-video">` (the dataset video) and one `<img id="t-img">` (the frozen or live frame). Only one of them is visible at a time, and the SVG overlay `#t-overlay` sits on top. The inspector has no frame picture (ball and face crops are thumbnails, not a second surface). If the video fails, the stage says `The stage video failed to load; freeze a frame to inspect it as a still.` or `The browser refused to play the stage video; freeze a frame instead.` Check: in DevTools count the visible `#stage > video, #stage > img` → exactly 1 once a frame has loaded. Select a cue → the video is shown and the img is hidden. Freeze → the reverse. [tests: the stage is one video with the overlay on top of it; the Vision tab renders one picture surface for the selected cue]
64. **Stage empty state**: `Pick a moment on the scrub strip, or select a cue, then freeze it here.` / `在拖动条上选择时刻，或选择一条线索，然后在此冻结。` Check: open a dataset before any frame has loaded → that text is shown on the stage.
65. **Play chip** (`#stage-play`): `playing|paused · window m:ss.d → m:ss.d · per-frame detections update on freeze|return on freeze`. Check: select a cue → the chip names its loop window.
66. **Live chip** (`#stage-live`): `● live`, or `STALE <n.n> s` after more than 2000 ms without a frame. Check: start live, then stop the server feed → after 2 s the chip turns into `STALE …`.
67. **Stage note** (`#stage-note`): says why a layer is held back (a foreign correction, a rejected or unverified quad, or a refused quad with its reason), in both languages. Check: open a frame whose quad is off → the note reads `The model table quad is <n> px off this dataset's saved corners (… tolerance 40 px) — not drawn.` [tests: a foreign correction and a rejected quad are both stated on the stage; a refused quad states its reason on the stage, in both languages]
68. **Stagebar**: the layer chips, the clock (mobile only) and the identity line `#vs-identity`. It names the current selection (`Ball · crop at this frame <file>`, `Track <id> · <binding>`, `Anchor <n> · x, y`, `#<id> · shot|pot · m:ss.d`, `Box <n> · <label>`, or `Source · <label>`). Check: click a ball on the stage → the line reads `Ball · crop at this frame …`.

## 9. Vision: overlays and provenance

69. **Six layer chips**: Cloth, Balls, Persons, Pockets, Anchors, Events (中 台呢/球/人物/袋口/锚点/事件). Each toggles its layer and is `.on` while shown. Check: click *Balls* → the ball markers disappear and the chip loses `.on`.
70. **Anchors chip gate**: disabled outside `vod30`, with the title `Anchors are available for the vod30 dataset only.` Check: switch to another dataset → the Anchors chip is disabled.
71. **Provenance tags** on every drawn group: `MODEL` / `YOURS` / `CALIB` / `EVENT` (中 `模型` / `人工` / `标定` / `事件`). Check: freeze a frame with detections → ball, person and box groups show `MODEL`. After an edit the box shows `YOURS`. Pockets from saved calibration and a cloth quad from saved corners show `CALIB`. The anchors layer shows `YOURS`, and the polygon shows `YOURS` or `MODEL` by where it came from. The selected cue's geometry shows `EVENT`. Switch to 中 → the tags translate. [tests: every drawn group is tagged by source, in both languages; a model box stays the model…]
72. **Dashed = model, solid = yours**: model boxes are dashed reference, and the operator's boxes are solid with full opacity and grab handles. Both layers are drawn on the same frame at their own coordinates, so a disagreement shows as a gap. Check: open a frame that has both a stored correction and a stored inference → the YOURS box is solid, the MODEL box is dashed and offset. **See defect D1: the dashed style currently never applies.** [test: two layers on one frame: model dashed, yours solid, and only yours are saved]
73. **Faint matched counterpart**: a model box that matches a YOURS box (IoU ≥0.5, or centres ≤8 px apart) is drawn faint (`faint`), with its tag moved under the box. Check: in item 72, the MODEL box overlapping the YOURS box is fainter than an unmatched MODEL box, and its tag sits below it. (Also affected by D1.)
74. **Drag ghost**: when a model box is dragged, resized or nudged it becomes YOURS, and a frozen faint copy of the model's original (`data-ghost="1"`) stays until the frame reloads. The ghost cannot be selected, dragged or saved. Check: drag a MODEL box → a faint box remains at the old spot and clicking it does nothing.
75. **Person chip**: `person · track <id>`, `unbound · track <id>` (has a cluster but no name) or the bound player id. Check: freeze a frame with people → each box carries its chip.
76. **Held-back layers are stated**: pocket markers and pot pulses are drawn only from a checked quad or from saved calibration, never from a refused quad. A partial anchor set is not pocket geometry. Check: on a frame with a refused quad, pockets are tagged `CALIB` (from calibration), or nothing is drawn and the facts line says why. [test: a refused model quad falls back to the saved calibration for the pockets]
77. **Pocket names are position words** (top-left, bottom-right, left-middle… / 左上, 右下, 左中…). Raw rail keys (`foot-right`, `head-left`) never appear. Check: hover a pocket label or read a pot card → no `foot-`/`head-` words. [tests: pocket labels are position words…; rail-corner keys are display-only…]
78. **Video honesty**: while the video plays, per-frame layers (balls, persons, boxes, detected quad) are dropped and never drawn stale. Static layers (cloth, pockets, anchors) and the selected cue's geometry stay. Check: select a cue → no ball or person markers while it plays. Freeze → they come back. [test: playing drops per-frame detections and never paints a stale mark]
79. **Selected-cue geometry**: a pot draws the ball's last position, a line to its pocket, and a colour and distance label. A shot draws a from→to arrow with a head and both numbers. Both are tagged `EVENT`. An event that cannot be projected draws nothing and says so. Check: select a shot cue → an arrow labelled with mm and speed appears. [test: the selected cue draws its own projected geometry, or says it cannot]
80. **Saved correction scoped to its frame**: a stored correction is drawn only on the frame (dataset, index, size) it belongs to. Otherwise the stage says `Saved correction belongs to <owner>, not this frame (…) — not drawn.` Check: move one frame away from a corrected frame → the correction is not drawn and the note says why. [test: a saved correction is drawn only for the frame it belongs to]
81. **Automatic cloth quad validation**: the model quad is drawn only if it is plausible and within tolerance of the dataset's saved corners (`CLOTH_TOLERANCE_PX = 40`, scaled by frame width ÷ reference width, so it reads `tol 40 px` when the widths match). Otherwise it is off (not drawn) or unverified (drawn, with pockets hidden). Check: a frame whose quad drifts more than 40 px → the cloth layer is empty and the facts line says `model quad off saved corners <n> px (tol 40 px)`. [test: the automatic cloth quad is validated against the dataset reference]

## 10. Vision: the chip row and the `SOURCE ▾` panel

82. **Chip row**: the `SOURCE ▾` chip comes first, then one chip per dataset (the active one highlighted), then one `live · twitch <channel>` chip per saved channel (`● ` while it is the live source). Choosing `highlight` also shows the red notice `Highlight candidates were generated with the wrong-resolution calibration. They are not valid accuracy evidence; inspect the source before judging.` Check: click another dataset chip → the stage, rail and strip switch to it (asking to discard if dirty).
83. **Chip meta**: freshness (`<label>` for a VOD, or `live|STALE · frame age <n>`) and the key map `SPACE play · ←/→ step · 0–9/U/C label · A/B identity · V verdict · ⏎ save` (hidden at ≤750 px). Check: read the line under the chips at 1280.
84. **`SOURCE ▾` panel toggle**: the chip is uppercase with `▾` when closed and `▴` when open, `aria-expanded` and `aria-controls="vs-source-panel"`. The panel is closed by default, rendered only on demand, and closed again by the chip or by `×` (aria `Close`). It floats under the chip row (`max-height min(72vh,560px)`, scrolls inside, never widens the page). Check: click `SOURCE` → the panel opens and the caret flips. Click `×` → it closes. [test: the source settings open from the Source chip…]
85. **Panel order**: the start-failure block (if any), then *Twitch VOD replay*, then *Dataset*, then *Live state*, then *Frame detectors*, then *Saved channels* with the URL form. Check: open the panel → the replay fields come before the dataset chips and the channel form. [test: the VOD fields are reachable and keep what the operator typed]
86. **Start-failure block**: `Start attempt`, `Attempted source: <value>`, the server's refusal **verbatim** (escaped, not rewritten), `Remedy: Check that the source is a saved canonical Twitch channel, or that the allowlisted dataset media exists.` and *Retry* (starts again). Check: start an unknown channel → the block shows the server's exact error text. [test: the live ball detector is selectable… (refusal sentence reaches the panel verbatim)]
87. **Dataset block**: dataset chips (the same effect as item 82), then `<label> · frames <count>`. Check: the frame count matches the strip's scrub range plus 1.
88. **Live state row** (`#vs-live-status`): `<state> [· error] · frame age <t> · receive-to-result <t> · dropped <n>`. The state words are localized (item 100). A failed start reads `error`, never `idle`. Check: start live → the row reads `running · frame age … · receive-to-result … · dropped 0`. [test: the facts line uses one word for one live state]
89. **Live Start / Stop**: `POST /api/live {action:'start', source, detectors}` / `{action:'stop'}`. Only the processor's contract fields are sent. Check: *Start* with the vod30 chip picked → the stage shows the live edge. *Stop* → state `stopped`. [test: live start and stop send only processor contract fields]
90. **Live source picker**: saved channels (`twitch:<id>`) and dataset chips (`dataset:<id>`) inside the Live block. Only allow-listed datasets and canonical channels are used. Check: pick a dataset chip in the Live block, then Start → the running source is that dataset. [test: live controls keep the dataset/channel allowlist and the latency caveat]
91. **Live detector toggles**: *Table*, *Person*, *Ball (trained net)*. The ball row explains that it is the trained tiny net, and that the SAM3 *Balls* frame detector is a separate CPU-heavy frame tool. Check: tick *Ball (trained net)*, then Start → `stages` lists `ball`. **See defect D6: toggling does not accumulate.** [test: the live ball detector is selectable and named as the trained net]
92. **Live stages line**: `<stage> · every <n> frames · not run on the skipped frames · <runs> runs`, one line per stage the processor reports. Check: run live with ball → the ball line shows its cadence and run count.
93. **Latency caveat** (always shown): `Twitch upstream delay: UNKNOWN. Receive-to-result is local processing latency, not glass-to-glass latency.` Check: open the panel → the caveat is present in both languages.
94. **Frame detectors** (for inference on a frozen frame): *Table*, *Person*, *Balls* (SAM3, off by default), with `The balls detector (SAM3) is CPU-heavy and stays an explicit opt-in.` Check: untick all and *Run inference* → `Choose at least one detector (table, person, balls).` [test: timeline state defaults are safe]
95. **Saved channels**: each channel URL with *Select* (picks it as the live source) and *Remove* (`source_delete`), or `—` when there are none. Check: *Remove* a channel → it disappears from the panel and from the chip row.
96. **Save Twitch channel** form: *Twitch source URL* plus *Save Twitch channel* (`source_add`). Only `https://www.twitch.tv/<channel>` or `/videos/<digits>` is accepted, with no query. Otherwise the shell shows `Use https://www.twitch.tv/channel or https://www.twitch.tv/videos/123…` or the server's refusal. Check: save `https://www.twitch.tv/somechan?x=1` → it is refused with the hint.
97. **Twitch VOD replay**: *VOD id or URL* (placeholder `https://www.twitch.tv/videos/1234567890`), *Start at (s)*, *Rate (VOD s per wall s)* (0.25–4, step 0.25) and *Use this VOD*. An empty id is never sent (see finding F6 for the missing message). Typed values and the caret survive the 500 ms poll re-render. Check: type an id, wait 2 s → the text and caret are still there. Click *Use this VOD* → `Chosen: vod <id> · Start at (s) <s> · Rate ×<r> · a replay, never a live broadcast`. [tests: the VOD panel prints the replay…; the VOD fields are reachable…]
98. **Replay self-description** (from the server, never from a UI label): `kind vod-replay · live false · vod <id> · Rate ×<r> · drift <d.dd> s · <network> · pacing <p>`. A failure reads `the VOD could not be resolved: <server error>`. The panel never says `live true`. Check: Start a VOD replay → the panel line contains `live false` and `drift`. **See defect D3 for the stage chip.** [test: a Twitch VOD picker sends the replay source the server accepts, never a live label]
99. **Twitch chat** (live Twitch source only): a docked iframe at the top of the inspector, with a *Show chat* / *Hide chat* toggle (shown by default). Check: go live on a channel → chat appears. *Hide chat* removes it.

## 11. Vision: live-state vocabulary and freshness

100. **One vocabulary** for processor states, localized and never raw: idle/空闲, starting/启动中, running/运行中, stopping/停止中, stopped/已停止, eos/已结束, error/错误, failed/失败, completed/已完成, unknown/未知. Unknown values stay verbatim. Check: in 中 start and stop live → only Chinese state words appear. [test: every processor state translates and never leaks raw English]
101. **Frame age and receive-to-result**: shown in the panel row, in the chip meta (age) and in the facts line (`frame age <t> · receive-to-result <t>`). Values under 1 s print as `<n> ms`, others as `<n.n> s`. **STALE** starts above 2000 ms. Check: while live, the facts line shows both numbers and they update every 500 ms.
102. **Live polling**: every 500 ms, only on the Vision tab, and only while the page is visible. It stops on tab switch, `pagehide` and `visibilitychange`. The JPEG and its metadata stay paired, and a sequence mismatch is refused. Check: open Floor → the network panel shows no `/api/live` polls. [tests: live polling cancels on navigation…; live JPEG bytes and their metadata stay atomically paired]
103. **A failed start stays stated**: status polls of an idle processor do not erase the failed attempt. The inspector shows `Live start failed: <error>` until a start succeeds. Check: fail a start and wait 5 s → the failure block is still shown.

## 12. Vision: the cues rail

104. **Events group**: the heading `Events` plus `<n> reviewed`, then the filter buttons *All*, *[geometry-verified]*, *[motion window only]*, *Shots*, *Pots*, *Unreviewed*. The tier filters appear only while some event carries a tier. Check: on a dataset with tiered events → both tier filters are present. Without tiers → they are absent. [test: the confirmation tier is badged on the card and in the inspector, in both languages]
105. **Cue card**: a type badge (Shots/Pots), a **tier badge** (`geometry-verified` / `motion window only`, 中 `几何已核` / `仅运动窗口`, with the hint as its title; no badge when there is no tier), `m:ss.d`, `#id` and the pocket position word. Check: a window-tier card shows `MOTION WINDOW ONLY` and an untiered card shows no badge.
106. **Gate numbers on the card**: for a pot, `pre→post` census and `<mm> mm <pocket>`; for a shot, `<mm> mm <colour>`; plus `motion <n>` and `×<dup>`. Check: a pot card reads like `14→13 · 148 mm left-side`. [test: the cue card and the inspector show the numbers behind a detection gate]
107. **Per-card provenance line**: `<detector> · machine-produced candidate; no human has confirmed it` (中 `机器产出，未经人工确认`), or `confirmed by a person` / `已由人工确认`. It is omitted when the event has no provenance, and it never prints `undefined`. Check: a machine event shows the line in the dim mono style. Switch to 中 → the Chinese sentence. [test: a machine-produced candidate says so on its card…]
108. **Quick verdict buttons** on each card: ✓ / ✗ / ? (Correct/Wrong/Unsure). One click selects the cue and saves the verdict at once. The label shows the saved verdict or `Not reviewed`. Check: click ✓ → the card reads *Correct* and the reviewed count goes up by 1.
109. **Selecting a cue plays and loops its window**: t − 1.5 s to t + 2.5 s, clamped to the video. The picture is the stage video, which loops inside the window. Check: click a card → the stage plays, and after the window end it jumps back to the start. The strip shows the window band. [tests: an event window is t - 1.5s to t + 2.5s…; the stage video loops inside the event window it was given]
110. **Honest empty states**: an empty shot or queue filter reads the measured reason (`No shot candidate survived measurement: every served event is explained by occlusion — … The events stay in the report artifacts, not in the queue.`, `data-vs-empty="shots-measured-none"`). The Pots filter has its own reason (`No pot candidate in this VOD survived measurement: the ball census refuted every claim … and 2 stayed unconfirmed, so this list is empty on purpose.`, `pots-measured-none`). No card is invented. Check: open *Pots* on a VOD with no surviving pot → that sentence, in both languages. [tests: an emptied queue explains itself…; the pots tab explains its empty state…]
111. **POTS = unconfirmed candidates**: the Pots filter lists only pot candidates the gate did not refute. A surviving pot is shown as a candidate with its gate status (`Detection gate unconfirmed · <gate>`), never as a confirmed pot. No shot appears under Pots. Check: select the pot → the inspector reads `Detection gate unconfirmed · …` and has no "confirmed" wording.
112. **Ball queue**: `Ball queue · <n> crops`. Rows show the file, `m:ss.d` and a tag (`Unlabeled` or the label). Clicking selects the crop and seeks to it. Check: click a row → the stage seeks and the inspector shows *Label ball*.
113. **Person tracks**: a window select (`<win> · <count>`) and rows `Track <id>` with the binding tag (`?`, `Player A`, a guest name in its own case, or `Ignore`). Clicking selects the track and seeks into its window. Check: pick a window, click a track → the stage seeks into the window and the inspector shows *Identity*.
114. **Focus highlight**: the group that holds the current selection is `.focused`. Check: select a crop → the Ball queue group is highlighted.

## 13. Vision: the inspector

115. **Nothing selected**: `Nothing selected`, `Select a cue, a ball, a person or an anchor to label it.`, the cue hint `Selecting a cue plays its window on the stage and loops in it; freeze to inspect one frame.`, then **This frame** tools (item 125). No source settings are shown here. Check: press Esc → the inspector shows this state. [tests: the source settings open from the Source chip…; the rail empty state and the labelling copy render in 中 as well]
116. **Close ×** (`deselect`), shown whenever something is selected. Check: click × → the state returns to Nothing selected.
117. **Notice line** in the inspector (localized at render, red for errors). Check: press V with no cue → `Select a cue first.`
118. **Cue block**: `Shots|Pots #id`, `m:ss.d · <pocket>`, *▶ Play in stage*, the note `The clip plays in the stage with its overlay; per-frame detections come back when you freeze.`, **Detected geometry**, **Verdict** (saved or `Not reviewed`), *Shooter* (—/Player A/Player B/Unknown), *Notes*, and a receipt. Check: select a cue and change Shooter → it is kept for the save.
119. **Detected geometry rows** (only rows that have values): Colour, then for a pot *Ball last seen*, *Pocket* and *Pocket at*; for a shot *From*, *To*, *Displacement* (mm) and *Speed* (mm/s). Then Scan window, Projected from, *Detection gate* (`confirmed|rejected|unconfirmed · <gate>`), *Confirmation tier*, Ball census, Claimed colour census, Vanished ball, Re-measured move, Claim vs measured ball, **Net move / path** (`<net> / <path> px`, one decimal, `—` for a missing side), **Peak speed** (`<n> px/s · <d> s`), motion, Duplicate detections merged, Gate notes. Then `Projected from the dataset calibration, in frame pixels.` or `Not projectable: …`. Check: a jittery candidate reads `Net move / path 0.2 / 80.6 px`. [test: a machine-produced candidate says so on its card… (net/path rows)]
120. **Cue footer**: *Correct / Wrong / Unsure* (draft), *Save review* (primary; refused with `Choose a verdict before saving.` without a verdict) and *Next candidate →*. It stays visible at any height. Check: pick *Wrong*, *Save review* → the receipt `✓ shot #<id> … · wrong · 0.0 s Saved`. [test: the adapter localizes engine state, keeps one scrub range and one action footer]
121. **Ball block**: *Label ball*, the crop image (and context), `file · m:ss.d · score`, a 0–9 grid (the active label highlighted), *← Previous crop* / *Next crop →* and a receipt. The footer has *Unknown* (−1), *Cue 0* and *Clear label*. Check: click 7 → the queue tag reads `#7` and the receipt reads `✓ crop <file> = Ball 7`. *Clear label* → the tag reads `Unlabeled`.
122. **Stage ball popover**: click a ball on the stage → a popover with the crop name, 0–9, U, C and *Close*, attached to the ball. It writes to the crop at that time, or says `Select a crop cue in the rail to label it` when there is none. Check: click a stage ball and press 3 in the popover → the crop is labelled 3.
123. **Anchors / Calibration block** (vod30 only; otherwise `Anchors are available for the vod30 dataset only.`): the note `Anchors belong to the raw source frame; saving stores anchor annotations only, it never fits a calibration.`, six anchor rows (`n · x, y`), a nudge pad ↑ ← → ↓, *Load anchors at 70 s / 200 s / 350 s*, `t <s> s`, a receipt, and the footer *Save six anchors*. Check: nudge an anchor, then *Save six anchors* → the receipt `✓ 6 anchors @ t 70.0 · … Saved`.
124. **Box block**: `Box <n>`, *Box label* (person/ball/cue/solid/stripe/eight), *Delete selected*, *Tool* (Select / move, Draw box), *New box label*, *Add table polygon* / *Clear polygon*, the layer note (item 128), *Run inference on frozen frame* with its status, and the footer *Run inference* plus *Save corrections for this frame*. Check: select a box, set the label to stripe, save → the receipt appears.
125. **This frame (cold-frame tools)**: *Select / move*, *Draw box*, *Add table polygon*, *Clear polygon*, *Run inference on frozen frame* (disabled while running), the inference line, the layer note, *Save corrections for this frame* (only when dirty) and `Nothing selected: draw a box on the frame, add the table polygon, or run inference on this frozen frame.` Check: with nothing selected, *Draw box* and drag on the stage → a YOURS box, and Save appears. [test: a cold frame can start a correction without a devtools call]
126. **Box editing on the stage**: drag to move, drag the corner handles to resize, drag the polygon corners, and draw a box in Draw mode (dashed preview). ↑/↓ nudge the selected box or anchor by 1 px. Check: select a box, press ↓ twice → it moves down 2 px and becomes YOURS.
127. **Save corrections payload = only your boxes**: `POST /api/frame-correction {dataset, frame_index, boxes:[{label,bbox}…], table_polygon}`. It holds only boxes whose origin is not `auto` (your boxes, including model boxes you edited). Model boxes, the counterpart and the ghost are never sent, and the payload carries no origin bookkeeping. Invalid coordinates are refused (`A box has invalid coordinates; fix or delete it before saving.`). Check: in DevTools → Network, the request body lists only the YOURS boxes. [test: two layers on one frame: model dashed, yours solid, and only yours are saved]
128. **Layer counts and note**: `your boxes <n> · model boxes <m>` plus `MODEL boxes are this session’s reference only: saving a correction writes your boxes (YOURS), never the model’s.` / `模型框（MODEL）仅为本次会话的参照：保存修正只写入你的框（人工），不会写入模型框。` Check: select a box → the counts match the tags on the stage.
129. **Inference source line**: `inference source: stored inference · <timestamp>` (a file from an earlier run) or `inference source: run on this frame, not stored · <timestamp>` (中 `已存推理` / `本次运行，未存储`). Check: run inference → the line says *not stored*. [test: an inference run says it was not stored, and a stored file is labelled as an earlier run]
130. **Save receipts**: every write is acknowledged next to its artifact, as `✓ <what> · <n.n> s Saved`, `· <what> · saving…`, or `! <what> · save failed: <msg>`. The age updates every second, and on failure the edits stay on screen. Check: save a verdict and watch → the age counts up. [test: engine copy localizes notices, statuses and save receipts]

## 14. Vision: identity (person track)

131. **Binding line**: `Track <id> · [prediction <p>] · <label> · legacy A/B seed|guest name` or `no label yet`, plus `<name> · manual bind|automatic face match|identity binding`. An automatic match is never called a manual bind. Check: select a face-matched track → it reads `… · automatic face match`. [test: a person track is labelled as one regular or one guest name…]
132. **Which regular?** dropdown: `— not a regular (guest) —`, then the roster (not Inactive; Active first; `name · rating`, plus the status word when not Active). It is disabled when the roster is empty and preselects the bound regular. Check: open the dropdown → Visitors show `· Visitor`.
133. **Guest name** box (placeholder `Type the guest’s name`, ≤60). Picking a regular turns it off (`vs-guest-off`, disabled), it does not disappear. The draft survives re-renders. Check: type a name, pick a regular → the box greys out. Pick the guest option → the box comes back with the typed text.
134. **Bind hint** (what *Save* will do): `Saves through the identity pipeline, so face and body matching keep working.` or `Saves the typed name as this track’s label.` or, for a regular on a track without a cluster, `No identity cluster on this track yet — pick a person box on the stage that has one.` Check: pick a regular on a track without a cluster → the noCluster sentence.
135. **Save / Clear** (footer): Save with a regular calls `POST /api/identity/seed {cluster_id, player_id}`. Save with a guest calls `POST /api/vod30/seeds {win,t,track_id,label:<name>}`. Save with neither is refused before any write: `Type a guest name or choose a regular before saving.` Clear removes the seed label and/or `POST /api/identity/unbind {cluster_id}`. Check: Save with an empty form → the refusal and no network write.
136. **Quiet Ignore**: a dashed secondary block, *Ignore (not a player)* (writes the legacy `ignore` seed) with `Marks this track as a spectator…`. Check: click it → the track tag reads `Ignore`.
137. **Legacy A/B rendering**: a stored `A`/`B` renders as `Player A`/`Player B` (中 `选手 A`/`选手 B`) on the rail tag, in the stagebar and in the binding line, named `legacy A/B seed`. A guest name is shown in its own case. Check: a track seeded `A` shows `Player A · legacy A/B seed`. [test: a legacy A/B seed still renders on the rail and in the identity block]
138. **Rebuild assignments / Refresh status** (`POST`/`GET /api/vod30/rebuild`), with the note `Seeds save immediately. Saving a seed alone does not rebuild predictions.` and the status line. Check: *Rebuild* → the status goes from `Rebuilding…` to `Status: <state>`.

## 15. Vision: enrol from footage

139. **Enrol as regular** (inside the Identity block): the preview is a read. `POST /api/identity/enroll-preview {dataset, frame_index, bbox[, cluster_id]}` writes nothing. The hint reads `Reads this person from the footage first; nothing is written until you confirm a name. A window scan can take about a minute.` It needs a stage person box: `Select the person on the stage first: enrolment starts from their box in this frame.` Check: select a track from the rail (no box) and click → that refusal appears.
140. **Pending state**: `collecting faces · <n> s` plus `the scan reads the recording around this frame; it stops by itself and reports what it saw`. The start button is hidden, so the scan cannot start twice. Check: click it → the seconds count up and there is no second button.
141. **Preview crops**: a grid of face crops (data URLs) with `#i · frame <n> · t <s> s` and `det <0.00> · eye <0.0> px`. Check: after the preview, each crop shows its det and eye numbers.
142. **Evidence-level line**: `frames seen <n> · usable faces <kept>/<usable> · purity <p>% (<probes>)|no other face to cross-check · selection IoU <x>`, then `evidence: stored cluster face|window scan · <n> crops · cross-checked|not cross-checked`. Check: a fast-path preview reads `evidence: stored cluster face · 1 crops · not cross-checked`. [test: the enrol block shows the evidence level, the crops and one confirm]
143. **Confirm writes only on click**: *Regular’s name* (≤60), then *Confirm enrolment* (the one write, `POST /api/identity/enroll-confirm {token, player_name}`), then *Cancel*. On success it shows `✓ enrolled; the roster was re-read`, and the shell re-reads `/api/operations`. Check: confirm with a name → the new regular appears in the Regulars roster without a reload.
144. **Refusals in operator words**: `Enrolment refused: <sentence>`, with the module code and its own message beside it, the faces it did see, or `no usable crop was kept: nothing to enrol from`. There are 11 codes: selection_not_matched, track_not_found, no_face_in_track, face_too_small, face_low_detection, single_face_only, inconsistent_faces, mixed_track, no_stored_evidence, preview_expired, **token_mismatch** (`these crops are not the ones you were shown; preview again`), and player_name_required. Check: preview a track with one usable face → `Enrolment refused: only one usable face: no second face to cross-check it` plus `single_face_only · …`. **See defect D2 for refusals that arrive on confirm, including `token_mismatch`.**

## 16. Vision: the scrub strip and the facts line

145. **Transport**: *Frame* number input (0..count−1; Enter seeks), ◀ / ▶ (±1 frame), *Freeze* (primary; pauses and reloads the exact frame) and *▶ Play* / *❚❚ Pause*. All of them are disabled on a live source. Check: type 1000 into Frame → the stage freezes at frame 1000.
146. **Scrub range and event ticks**: one range `0..frame_count−1`, a tick per event (click selects that cue, or seeks to that time), the loop-window band with the cue mark, and `↻ <loops> · playing|paused`. Check: click a tick → that cue plays and the band appears around it.
147. **Live edge marker** (`#vs-edge`): at 100 % while live, otherwise at the current time. Check: go live → the marker jumps to the right end.
148. **Facts line** (`#vs-facts`, `role=status`, one line; the title attribute holds the per-side quad detail). In order:
     - VOD: `frame <n> · t <s> s`. Live: `live|stale [· seq <n>] · frame age <t> · receive-to-result <t>`.
     - Layer counts: `cloth <n>`, plus ` (inference · this session)` or ` (stored inference <timestamp>)` when the polygon comes from inference. Then `balls <n>` and `persons <n>`. A layer with manual additions reads `<model> (+<k> manual)`, and the two numbers add up to what was drawn. With no provenance report only the totals are printed.
     - `pockets <n>` with ` (quad rejected)`, ` (unverified)` or the calibration source when held or projected. Then `anchors <n> · events <n>`.
     - The quad verdict: `quad drift vs saved corners <x.x> px (tol 40 px)` when accepted, `model quad off saved corners <n> px (tol 40 px)`, `model quad unverified`, `quad refused (<reason in words>[ · k/4 sides unverified: i, j])` or `quad from the naive fallback (<reason>)`.
     - `saved correction refused (<owner>)` when a foreign correction is held back.
     - `stored inference <timestamp>` for stored model boxes that do not come from the polygon.
     - `overlays ON|none|LOADING (<s> s)|loading…`.
     - No snake_case code is ever printed. 中 has the same parts (`四边形相对已保存角点漂移 … 容差 40 px`, `推理 · 本次会话`, `已存推理`).
     Check: freeze a vod30 frame with an accepted quad → the line contains `quad drift vs saved corners 5.7 px (tol 40 px)`. [tests: adapter facts line separates model result from manual correction; an accepted quad prints its measured drift…; adapter facts line names the layers it held back; the facts line states a refused quad reason in both languages; the cloth count follows where the polygon came from]
149. **Refusal reasons in words** (the facts line and the stage note): `the cloth is hidden - a player or an object is over the bed`, `no rail edge is visible inside the search band`, `the rail edge sits outside the search band`, `the four sides disagree with the saved centre`, `the four corners are not a valid table quad`, `no saved geometry exists for this dataset`, `no cloth was found in this frame`. An unknown code reads `the detector reported "<words>"`. Check: a frame with an occluded cloth → `quad refused (the cloth is hidden - …)`.

## 17. Keyboard shortcuts (every one in the code)

All shortcuts work only while Vision is active. They are ignored while a text field, select, button, video or contenteditable has focus, and when Ctrl, Meta or Alt is held (`app.js onKeydown`). There is one document-level handler, so a key is never handled twice. [tests: form and video targets never double-consume the stage keys; the verdict keys act on the selected cue only]

150. `Space`: play or pause the stage. Check: press it on a frozen frame → the video plays.
151. `←` / `→`: step one frame. With `Shift`, 10 frames. Check: Shift+→ → the frame index goes up by 10.
152. `,` / `.`: step one frame back or forward. Check: `.` → the frame index goes up by 1.
153. `↑` / `↓`: nudge the selected anchor or box by 1 px vertically. Check: select an anchor, press ↑ → its y goes down by 1.
154. `Esc`: clear the selection. Check: with a cue selected → the inspector shows Nothing selected.
155. `Enter` (⏎): save the verdict of the selected cue, or `Select a cue first.` when no cue is selected. Check: select a cue, press V, then ⏎ → a receipt appears.
156. `0`–`9`: label the selected ball or crop. Check: select a crop, press 5 → the queue tag reads `#5`.
157. `U`: label as unknown. `C`: label as cue (0). Check: select a crop, press U → the tag reads `Unknown`. Press C → `Cue · 0`.
158. `A` / `B`: write the legacy role seed on the selected track. This is the only path left to write `A`/`B` (item 137). Check: select a track, press A → the tag reads `Player A`.
159. `V`: cycle the verdict draft Correct → Wrong → Unsure on the selected cue, or `Select a cue first.` Check: press V three times → the footer highlight cycles.
160. `F`: re-freeze the current frame (seek to itself). Check: press F while the video plays → the stage freezes on the current frame.

The keys chip (item 83) lists only Space, ←/→, 0–9/U/C, A/B, V and ⏎. `,` `.` `↑` `↓` `Esc` `F` and `Shift` are reachable but not listed on screen (finding F4).

## 18. Cross-cutting contracts

161. **中/EN parity**: every shell word (`words`, 131+12 keys), every adapter string (`COPY.en`/`COPY.zh`, 251 keys each), the engine strings (`zhCopy`), the audit labels, the 27 validation messages and the roadmap rows exist in both languages. A switch relabels what is already on screen (drafts, focus and selection are kept). Check: switch language on every tab → no English left in 中 except proper nouns and machine tokens (detector names, ids, `px`, `mm`). [tests: every adapter string ships in both languages; editor translation preserves dirty values, focus, selection…; browser regression: translated options keep submitted values…]
162. **Mobile (390 px)**: in Vision the nav and header strip are hidden, and the rail and inspector become **bottom sheets** (`position:fixed; bottom:44px; max-height:44vh`) switched by the `CUES` / `INSPECTOR` sheet tabs (a fixed 44 px bar). Only the sheet's scroll region scrolls, and the footer never covers rows. The chip row and stagebar scroll sideways inside themselves, the `SOURCE` chip stays first, the clock shows in the stagebar, and the strip is sticky above the sheet tabs. Check: at 390×844, `document.documentElement.scrollWidth === 390` on every tab. Tap *Inspector* → the rail hides and the inspector sheet shows. [tests: app.css styles the one stage surface, ops.css styles the rails and strip (mobile scroll/footer asserts)]
163. **Tablet (≤1100 px)**: the Vision grid becomes one column, with rails at full height. Check: at 1000 px the stage is full width and the rails stack.
164. **Touch targets**: shell buttons are at least 40 px tall, inputs, selects and textareas at least 42 px, nav buttons and the clock *Start*/*Reset* at least 44 px, and the Floor score buttons 46 px. The Vision chips shrink to 28 px at ≤750 px by design (one chip line). Check: at 390, measure the Floor + button → 46 px or more, and a nav tab → 44 px or more.
165. **Read-only API contract**: every `GET` is side-effect free. No persisted file changes after a read-only session. Writes happen only in POST handlers (operations actions, annotate, balls label, seeds, anchors, frame-correction, identity seed/unbind/enroll/enroll-preview/enroll-confirm, inference, rebuild, live). The one exception is `GET /api/clip`, which is a regenerable cache under `out/clip-cache/`. Check: md5 the five production files (`out/corner-pocket/state.json`, `out/pid_seed.json`, `out/scan30/annotations.json`, `out/identity/clusters.json`, `out/scan30/events.json`), browse every tab and select cues, tracks and frames without saving → all md5s, sizes and mtimes are unchanged. (See `docs/unified-workbench.md` "API write contract".)
166. **The shell does not intercept the review**: clicks and submits inside `#review-root` go to the engine and adapter, not to the shell's handlers. Check: submit a form inside Vision → there is no shell `Saved.` toast. [test: shell does not intercept review clicks or form submissions]
167. **No fake data**: no simulated observations or fabricated statistics anywhere (stats come from signed results only, and the empty states are honest). Check: with an empty club every tile shows 0 or `—`, never sample numbers.

---

## 19. Findings (hard to reach or broken today; record, do not fix in the polish)

Each finding was confirmed by running the code in a node `vm` harness (the same pattern as the
pinned tests) or by an exact grep. The paths are in the worktree.

- **D1: model boxes are never dashed or faint.** `paintOverlay` gives model boxes the class
  `t-box auto` (and `auto faint`), and their tags `o-src auto` (`boxTagKind()` returns
  `'auto'`), but `app.css:102-104` styles only `.t-box.model` and `.o-src.model`. Rendered
  classes `t-box auto faint` and `o-src auto` match only the base `.t-box` and `.o-src` rules. So
  the MODEL box is drawn solid like YOURS, the matched counterpart is not faint, the ghost looks
  like a normal box, and the MODEL box tag has no brass stroke. Test 58 asserts the classes but
  not the CSS, so the gap is invisible to the suite. Item 72/73/74 is therefore visible only
  through the tags today. Suggested fix: rename the CSS selector or the class, one line.
- **D2: a refusal on *confirm* reads "Unknown" and shows a success receipt.**
  `enrollConfirm()` stores the server's refusal under `payload.result`, but `enrolBlock()`
  reads `payload.reason`. So a `token_mismatch` (or `preview_expired` or
  `player_name_required`) refusal renders `Enrolment refused: Unknown`, and the receipt still
  reads `✓ <name> → regular · Saved` (probe: `result.reason=token_mismatch`, receipt
  `error:false`). The server answers 200 with `ok:false`. The `enrolMismatch` copy key is never
  used.
- **D3: a VOD replay's live frames are labelled live on the stage.** `pollLive()` sets the
  frame label to `● live · <liveSourceLabel>` for every source, so a replay reads
  `● live · VOD replay 1000000001 · rate ×2 · from 30s`, and the chip row freshness and
  `#stage-live` say `live`. The panel (item 98) is honest, but the stage chrome is not.
- **D4: `rosterTitle` has no dictionary entry.** The Regulars roster heading renders the raw key
  `rosterTitle` in both languages (the only one of 100 shell keys that is missing).
- **D5: live-poll errors crash in the handler.** `pollLive()` writes `$('#live-status')`, but
  that element no longer exists (the panel uses `#vs-live-status`). A successful poll skips it
  with a null check. The `catch` branch does not, so a network error throws `Cannot set
  properties of null` from inside the catch, and the error is never shown in the shell.
- **D6: live detector toggles do not accumulate.** The panel checkboxes are computed from
  the engine's `live.detectors`, which nothing ever writes (it stays `['table','person']`). The
  shell's `liveDetectors` holds the real list. Unticking *Person* sends `['table']`. Then ticking
  *Ball* sends `table+person+ball` (Person is back), and the boxes always show the initial
  ticks. The start payload uses whatever the last click produced.
- **D7: the profile modal state is cleared on every shell click.** In `ops.js`, the click
  handler runs `selected=null;` unconditionally right after the `player-delete` line, so every
  shell button click that reaches the action chain clears it (probe: after `select-player`,
  `selected` is `null`). The modal still opens, because `select-player` renders before the
  reset. But the next render closes it (for example a language or theme switch, or a failed
  write), and a *cancelled* delete also closes it. The editing forms inside the modal submit
  through the `submit` handler, so saving still works.
- **F1: forfeit and match-level "Not here" are unreachable.** `queueCard()` (the
  *Not here/Here now*, *Send to table* and `Forfeit: <name>` controls) has been defined but never
  called since `b484912`. There is no button anywhere that sends `match_forfeit`, and a live or
  scheduled match cannot be marked absent from the UI (only entrants before the draw, item 39).
  So items 24 and 32 can only be reached through data that was already delayed.
- **F2: the anchors layer chip is on, but no anchors are drawn.** `overlay.anchors` defaults
  to `true`, but the anchors load only when the chip is toggled *on* (or *Load anchors at…*
  is used). On first open the chip reads ON and the layer is empty. Turning it on needs two
  clicks (off, then on).
- **F3: the arrow-key box nudge advertises Shift = 10 px, but only ↑/↓ nudge.** ←/→ always
  step frames (and Shift steps 10 frames), so there is no horizontal nudge from the keyboard.
  The hint `arrow keys nudge the selected box (Shift = 10 px)` sits in the engine copy but is
  not rendered anywhere.
- **F4: hidden shortcuts.** `,` `.` `↑` `↓` `Esc` `F` and `Shift+←/→` work but are not in the
  keys chip, and the keys chip itself is hidden at ≤750 px. The `keyMap` copy key is unused.
- **F5: saved Twitch VOD URLs are invisible.** The URL form accepts `…/videos/<digits>`, but
  `channels()` keeps only channels, so a saved VOD URL is stored and then never listed or
  removable in the UI.
- **F6: *Use this VOD* with an empty id does nothing visible.** The adapter's empty-id branch
  calls `opts.notice?.(…)`, but the shell's `attachSurface()` never passes `notice`, so the
  click is silently dropped. The shell's own `Enter a Twitch VOD id or URL` refusal in
  `pickReplay()` is unreachable from the panel.

Counts: **167 numbered features** in 18 surfaces, plus 13 findings (D1–D7, F1–F6), plus the
**14 supplements S1–S14** in §20. **181 items in all.**

---

## 20. Supplements S1–S14 (features on `main` that the 167 missed)

`docs/ia-assessment.md` §0 found fourteen user-visible features in `ops.js` with no item above.
Each was confirmed with a literal grep of `ops.js`; a case-insensitive grep of this file found no
item for it. They are bound by the same rule as items 1–167: they may move, but the check on the
line must still pass. The *Today* tab is where each one lives on `main` at `4f289b2`.

- **S1. First-night guide** (`firstRun()`, Floor, before the draw only). Title `First night? Three steps to the first break` / `第一次开场？三步到开球`; three steps, each a button that opens the place that does it: `Add your regulars (optional)` / `添加常客（可选）`, `Sign in at least two players for tonight` / `为今晚登记至少两位球员`, `Rack the night: the draw sends matches to free tables` / `排出赛程：对阵会分到空闲球台`. A done step shows `✓`. Note: `Guests can play without a profile. This guide leaves once the draw exists.` Check: on an empty club click step 2 → the registration desk opens; rack the night → the guide is gone. [test: onboard: an empty club gets three real steps on the Floor, and they leave once the draw exists]
- **S2. Rename the event after the draw** (`#rename-form`, `tournament_rename`, Set up). Once the night is racked the locked form keeps one editable field, *Event name*, with *Rename event* / *重命名赛事*. The rename is audited (`Event renamed` / `赛事已重命名` in the Night log). Check: rack, rename → `Saved.`, the new name shows, and a new Night log line reads `Event renamed`. [test: after the draw and in the archive only the name can be edited, and it is audited (R2)]
- **S3. Delete an event that has nothing signed** (`event-delete`, `tournament_delete {confirm:true}`, Set up › End of the night). *Delete event* / *删除赛事* is offered for tonight's event only while it has entrants and no signed result. Confirm: `Delete “<name>”? No result was signed in it. This cannot be undone.` Check: register two entrants, *Delete event*, confirm → the Night log reads `Event deleted (nothing was signed)`. Sign one result → the button is gone. [test: delete only an unsigned event; otherwise hide it from history, which erases nothing (R1)]
- **S4. Registration-desk search** (`.desk-search`, `deskFilter()`, Set up). One box per seat, placeholder `Type to find a regular` / `输入以查找常客`. It filters the seat's regular select in place with the roster's matcher (every word, NFKC, accent and case folding). A single match is selected; no match shows `No regular matches` / `没有匹配的常客`. Check: type `wan` → only Wanwan is left and selected; type `zzz` → the no-match note shows. [test: R13: the registration desk filters its regulars in place with the same matcher]
- **S5. Random doubles pairing** (`pairingCard()`, Set up, doubles and before the draw only). *Add solo player* / *添加单人报名* (a regular or a guest name) builds the solo pool, shown as chips with `×` (`pool_remove`), or `No solo sign-ups yet.` *Pair at random* / *随机配对搭档* needs an even pool of 2 or more (otherwise the reason is shown) and draws teams with `seed <n>`. Then *Use these teams* / *采用这些组合* (`pair_accept`), *Re-roll* / *重新抽签* (`pair_draw`) or *Back to the list* / *返回名单* (`pair_clear`). Check: Doubles, add 4 solos, *Pair at random* → 2 teams and a seed; *Use these teams* → 2 entrants. [test: doubles can pair solo sign-ups at random: seed shown, re-roll, accept (R3)]
- **S6. Results sheet** (`resultsSheet()`, Matches). *Results sheet* / *赛果单* opens a printable sheet of one night (tonight once drawn, or any archived night): the name, a date · format · race line, the champion from the final (or `Not decided yet` / `尚未决出`), every round's result lines and the second-chance line. *Print / save as PDF* / *打印 / 存为 PDF*, *Copy results as text* / *复制赛果文字* (then `Results copied. Paste them into the group chat.`) and a back button. Check: open it, *Copy results as text* → the message appears and the clipboard holds the bracket as text. [test: a results sheet prints the whole bracket and copies as text, champion from the final (R10)]
- **S7. Second chance (revival)** (`revivalCard()`, Matches). The card appears once every two-sided round-1 match is signed, while a round-1 bye exists and no round-2 result is signed. *Draw a round-1 loser* / *抽取一名首轮负者* asks `Draw one round-1 loser at random to re-enter the bracket in a bye slot? …` and records the draw with its seed. The card names who was drawn, the attempt, the pool, the seed and the time, and says so when it was redrawn. *Undo the draw* / *撤销抽签* (confirm) is offered only while nothing more has been signed. Check: on a 5-entrant night sign round 1, *Draw* → a named loser takes the bye slot; *Undo* → the bye is back. [tests: a second chance is a labelled random draw, confirmed, undoable, never a result (R6); a redrawn second chance says so on the card, the sheet and the copied text (R6 follow-up)]
- **S8. Bracket density** (`density`, `localStorage cp-ops-density`, Matches). *Compact* / *紧凑* (the default: one line per side with a status dot; the head row and the controls open on hover, focus or selection) or *Full cards* / *完整卡片*, per device. Check: pick *Full cards*, reload → still full cards. [test: R9: the compact bracket is one line per side with a status dot; the full card is still there]
- **S9. Event table** (`eventTable()`, Matches). *Event table* / *本场战绩表*, tonight only, `Signed results only: a bye is not a match, a forfeit counts.` Rank, name, wins, played, win %, sorted by wins, then win %, then name. Check: sign one match → its winner shows 1 win of 1 played. [test: standings count results, not ratings; the event table sorts wins, win %, name (R4)]
- **S10. Per-match Away/Here and Forfeit** (`matchControls()`, Matches bracket card). On every scheduled, live or delayed match with two sides: `Not here: <name>` / `Here now: <name>` per side (`match_absence`, confirm `Mark this player as not here? The match is held until they return; the table is released.`) and `Forfeit: <name>` per side (`match_forfeit`, confirm `Record a forfeit for this side and advance the opponent?`). Check: *Forfeit: A*, confirm → the match is complete and B advances. [test: forfeit and in-match absence are reachable from the Matches bracket, each behind a confirm (F1, R7)]
- **S11. Archived events: rename, hide, show hidden, delete** (Matches › Archived events). Each archived night has *Results sheet*, *Rename event* (prompt `New name for this archived event (the results do not change):`, `tournament_rename`) and either *Hide from history* / *从历史中隐藏* (a night with a signed result; confirm, `tournament_hide`) or *Delete event* (nothing signed; confirm, `tournament_delete`). Hidden nights leave the list; *Show <n> hidden* / *显示 <n> 场已隐藏* and *Hide hidden events* toggle them, and a shown hidden night carries a hidden tag. Check: hide an archived night → it disappears and `Show 1 hidden` appears; click it → the night is back, tagged. [tests: delete only an unsigned event; otherwise hide it from history, which erases nothing (R1); after the draw and in the archive only the name can be edited, and it is audited (R2)]
- **S12. Player record** (`recordView()`, Regulars profile). *Player record* / *球员战绩* opens an all-time, read-only record: `Signed results in <n> events since <date>. Read-only.`, tiles for played, wins, losses and win %, *By event* / *分场战绩* and *Head-to-head* / *交手记录* from signed matches only, and *Back to profile* / *返回档案*. Check: open a regular with one signed win → By event lists that night with one win. [test: a player record is all-time and read-only, with head-to-head from signed matches only (R15, R8)]
- **S13. Forget a face** (`face-forget`, `POST /api/identity/forget`, Regulars profile). *Delete face data* / *删除人脸数据*, behind a confirm that says what goes and what stays. The result names the counts: `Face data deleted: <n> stored faces, <n> matched person unbound, <n> face samples`. Cancel sends nothing. Check: *Delete face data*, cancel → no request; confirm → the counts are shown. [test: the regular profile deletes face data only after a confirm that says what goes, and shows the counts]
- **S14. For maintainers** (Back room). A collapsed `<details>`, *For maintainers* / *维护人员*, `System status and the product roadmap. Not needed to run a night.`, holding the status table (item 59) and the roadmap (item 58). The operator panels (table appearance, notes) come first. Check: open the Back room → the section is closed; expand it → both tables. [test: round 1 · Back room: operator panels first; system status and roadmap under a collapsed, labelled maintainers section]

---

## 21. New homes: the Tonight console (IA option C′, operator half)

The owner chose option C′ of `docs/ia-assessment.md` (§10, §14): the operator console of option A
plus a separate read-only Display. This section gives **every one of the 181 items its home in the
console**; it follows the assessment's §11 mapping (column A), and every deviation is named in the
last column with its reason. The Display (`/display`, built separately) only *copies* some items
read-only; it is never an item's home, and every write path stays in the console.

Legend: **T›Register**, **T›Rack**, **T›Play**, **T›Close** = Tonight and its phase;
**R** = Records; **V** = Vision; **Rg** = Regulars; **BR** = Back room; **Sh** = shell (every
screen); **More** = the ≤750 px bottom bar's *More* sheet. *Reworded* means the item's behaviour is
kept and only the tab its check line names changes; the stage that moves the item rewords it.

Structure: top-level tabs **Tonight · Records · Vision · Regulars · Back room**. Tonight has a phase
strip **Register · Rack · Play · Close**; all four are always clickable, and the default is the
night's phase (no draw → Register; a draw with unsigned matches → Play; everything signed → Close).
At ≤750 px the nav is a fixed bottom bar: **Tonight · Records · Vision · More** (More: Regulars,
Back room). Routes are hash routes: `#/tonight` (the night's phase), `#/tonight/register`,
`#/tonight/rack`, `#/tonight/play`, `#/tonight/close`, `#/records`, `#/vision`, `#/regulars`,
`#/backroom`. The old tab ids redirect: `floor` → `#/tonight/play`, `setup` →
`#/tonight/register`, `matches` → `#/tonight/play`, `players` → `#/regulars`, `status` →
`#/backroom`, `vision` → `#/vision`.

| Items | Today | New home | Check line / deviation |
|---|---|---|---|
| 1 brand link | Sh | Sh | Reworded: the reload lands on Tonight at the night's phase, not on Floor. |
| 2 connection badge, 5 EN/中, 6 theme, 8 message line, 9 conflict, 10 busy lock, 11 navigation veto, 12 leave guard, 14 offline screen, 15 reduced motion | Sh | Sh | Unchanged. 11 also guards a route change (hash, back/forward). |
| 3 six tabs | Sh | Sh: five tabs, plus the ≤750 px bottom bar and hash routes | Reworded: each tab gets `.active` and `aria-current="page"`, `#main` swaps, and the URL hash follows; back/forward walk the routes. |
| 4 nav counters | Sh | Sh: Tonight = entrants before the draw, matches not complete after it; Regulars = players | Reworded (Set up and Matches counters merge into Tonight's). |
| 7 header strip | Sh (tabs 2–6) | Sh: every screen except T›Play; the score button opens T›Play on that match | Reworded. |
| 13 sticky header | Sh | Sh; at ≤750 px the fixed bottom bar is the always-reachable nav | Reworded: at 390 the bottom bar stays on screen while the page scrolls. |
| 16–26 shot clock (one state, many views) | Floor, strip, Vision stagebar | T›Play (the existing `clockHTML()`, unchanged), the strip, the Vision stagebar | Reworded: "Floor" → "Tonight › Play". The clock logic is not touched (the shot-clock worker owns it). |
| 27 scoreboard, 28 focus picker, 29 sides A/B, 30 +/−, 31 Win frame, 33 footer actions | Floor | T›Play › Tables: one scoreboard per table; the table tiles pick the focused table and `#focus-match` stays for the keyboard | Reworded: "on Floor" → "in Tonight › Play". |
| 32 Waiting on … / Here now | Floor | T›Play (focused table and the Queue's held rows) + T›Register attendance | Reworded. |
| 34 Floor tiles | Floor | T›Play summary line (*Cards signed*, *Entrants*, *Guests tonight*); *Up next* becomes the Queue, **with Send** | Reworded: "sign one match → Cards signed becomes `1/<n>`" is read on Play. |
| S1 first-night guide | Floor | T›Register (before the draw) | Steps open Regulars, the registration desk and the Rack card. |
| 35 the night, 36 locked notice, S2 rename after the draw | Set up | T›Register | Reworded: "Set up" → "Tonight › Register". |
| 37 registration desk, S4 desk search | Set up | T›Register | Reworded. |
| S5 random doubles pairing | Set up | T›Register | – |
| 38 Rack the night | Set up | T›Register (last card) and T›Rack; racking **shows T›Play** (the draw) | Reworded: "matches appear on Matches" → "Tonight › Play opens with the draw". |
| 39 entrants list | Set up | T›Register (Entrants and attendance) | Reworded. |
| 56 guests tonight (Add to regulars) | Regulars | T›Register (attendance), with a link to Regulars | Reworded: it moves out of Regulars (per §11). |
| 40 archive & new event, S3 delete event | Set up | T›Close | Reworded: the old event then appears in Records › Archived events. |
| 41 Matches tiles | Matches | T›Play summary line (event, format, race, signed, on table, delayed) | Reworded. |
| 42 scorekeeper's card, 43 score select sync | Matches | T›Play: the number-entry mode of the focused table (`#score-form`, *Save*, *Sign*), kept, not removed | 43 reworded: switching the focused table refills the A and B inputs (one scoring model: the table picker is the match select). |
| 44 bracket by round (Send, Here now) | Matches | T›Play: the Queue (*Send to table*, *Here now*) + the bracket panel | Reworded: *Send to table* keeps you on T›Play with that table's scoreboard focused (it opened Floor). |
| S8 bracket density | Matches | T›Play bracket panel | §11 also lists R; R shows no live bracket (archived nights read as round lists), so density has one home. |
| S10 per-match Away/Here and Forfeit | Matches (card) | T›Play: the focused table's *More*, and each Queue row's *More* | Reworded: "from the Matches bracket" → "from Tonight › Play". |
| S7 second chance | Matches | T›Close (it opens after round 1) | Per §11. |
| S6 results sheet | Matches | T›Close (tonight) + R (each archived night) | – |
| S9 event table | Matches | T›Play (beside the bracket) | Deviation from §11's "+ R": Records holds history and all-time standings; a second copy of tonight's table there would be the duplication §3 of the assessment counts against us. |
| 45 house standings | Matches | R | Reworded. Each name also opens the player record (S12). |
| 46 night log | Matches | R | Reworded. |
| 47 archived events, S11 rename/hide/show/delete | Matches | R | Reworded. |
| 48 Regulars tiles, 49 roster, 50 add, 51 profile, 52 edit, 53 delete, 54 enrol face, 55 modal close, S12 player record, S13 forget face | Regulars | Rg (≤750 px: under More); S12 is also opened from R's standings | – |
| 57 table appearance, 58 roadmap, 59 status table, 60 operator notes, S14 maintainers | Back room | BR (≤750 px: under More) | – |
| 61–160 Vision | Vision | V, unchanged: one surface | At ≤750 px the bottom bar stays visible on Vision, which gives it an exit; the sheet tabs and sheets sit above the bar. 102's check ("open Floor") reads "open any other tab". |
| 161 中/EN parity, 164 touch targets, 165 read-only API, 166 shell does not intercept the review, 167 no fake data | Cross-cutting | unchanged; they bind the new surfaces too | 164 reworded: "the Floor + button" → "the Play + button". |
| 162 mobile 390 px, 163 tablet ≤1100 px | Cross-cutting | re-checked on every new screen; Vision's bottom sheets keep their behaviour above the bottom bar | 162 reworded for the bottom bar. |

Count: 1 + 10 + 1 + 1 + 1 + 1 = 15 shell items; 16–26 = 11; 27–34 = 8; 35–39 = 5, 40 = 1; 41–47 =
7; 48–55 = 8, 56 = 1; 57–60 = 4; 61–160 = 100; 161–167 = 7. **167**, plus S1–S14 = 14, each placed
once. **181 homes, 0 items removed.**
