# The console, photographed — the round-2 bar, before and after

*The screenshots the console redesign owed: the harness that measures the bar is the one that
shoots it, so every claim below has a PNG beside it and a JSON number behind that. The "before"
column is the brief's own record of the wave-10 bar; the "after" column was measured at the
round's last type and board commits on 2026-10-03, in the same run that wrote the 22 pictures.
The intermediate wave-10 bar was never photographed — §7 says exactly why.*

| | |
|---|---|
| script | `tests/console_shots.py` — stdlib + a hand-rolled CDP client, re-runnable, exit 0 = every assertion held |
| fixture | `tests/serve_operations_fixture.py --state tests/console_fixture_state.json` — revision 111, 14 players, 3 archived events, a throwaway root on two loopback ports |
| browser | a **private copy** at `/home/haoye/projects/pool-w-shots/out/browser/cp-shots` (Chrome/151.0.7922.137). It is byte-identical to the store build but its `comm` is `cp-shots`, so a `pkill -x chromium` from another session cannot reach it and it cannot be blamed for one |
| shots | 22 PNGs · 1.56 MiB · `chromium restarts: 0` · 0 problems · every shot matched its requested pixel size, rendered, and loaded its stylesheets |
| output | `out/console-after/` (untracked): `1440x900/`, `390x844/`, `manifest.json`, `board-metrics.json`, `fixture.log` |
| measured at | `817d19d` + `ad87278`; merged to main as `6854a46` |

## 1. How to reproduce

From the repository root:

```
.venv/bin/python tests/console_shots.py --build after \
  --chromium /home/haoye/projects/pool-w-shots/out/browser/cp-shots \
  --states tonight-play,records,regulars,backfill --sizes desktop,phone --langs en,zh
```

The pass walks `#/tonight` and `#/records` at both sizes and both languages for the header
measurement, then shoots the six story states. `--skip-metrics` is honoured (see §6); the
fixture's own log lands next to the shots as `fixture.log`.

## 2. The header: 117 / 170 px → 79 px, and the second row is gone

`header_metrics`, all eight rows. "Before" is the brief's record of the wave-10 bar; only the
after column was measured by this pass — lane A measured the redesigned phone header
independently and got the same 116 px.

| viewport | state | before | after | the row as measured |
|---|---|---|---|---|
| 1440x900 | tonight-play en / zh | 117 px | **79 px** | `bar=78 nav=44 navItems=5 strip=- tabbar=0 contentTop=79` |
| 1440x900 | records en / zh | 170 px | **79 px** | same bar, still one row |
| 390x844 | tonight-play en / zh | 113 px | 117 px | `bar=116 nav=0 tabbar=53 contentTop=117` |
| 390x844 | records en / zh | 280 px | **117 px** | the `.strip` row that had grown to 167 px on this screen is gone |

**Round 3 took this bar further, and the table above is round 2's record.** The blind rater sat at
**1280×900** — a width this pass never measured — where the same bar was still two ragged rows,
121 px tall, and its twenty findings took the header to **57–59 px in one row from 1024 to 1920**
(§8). The round-2 shots described here now live in `out/console-after-r2/`; `out/console-after/`
holds round 3's.

`strip=-` is the harness saying the `#strip` element it used to measure no longer exists; `nav=0`
on the phone is the design's own rule — the five destinations move to the fixed bottom bar
(`tabbar=53`), and the timer never leaves the top. The English desktop bar was the only one that
ever wrapped: its three sections needed 1384 px against a 1376 px content box, so `.tools` fell to
a second row (measured `en=127` against `zh=79`) — which is why the bug looked language-specific.

## 3. The public board's bracket had no floor (B-06)

Read with `getComputedStyle` through the same private browser at the four widths the finding named
(`out/console-after/board-metrics.json`). The floor is the console's own 11 px `--fs-xs` token,
written as an absolute `max(…, var(--tv-xs))` — an earlier attempt wrote it in `em`, which
resolves against the *parent* size and inflated the type at every root instead of flooring it.

| viewport | root | `.rounds` | `.round h3` | `.bm-note` |
|---|---|---|---|---|
| 1000x800 | 12.5 px | 11 px | 11 px | 11 px |
| 1280x900 | 16 px | 12.8 px | **11 px** (was 10.24) | **11 px** (was 9.6) |
| 1400x900 | 17.5 px | 14 px | 11.2 px | 11 px |
| 1920x1080 | 24 px | 19.2 px | 15.36 px | 14.4 px |

The floor bites only where the density steps would have taken the text below the token, and never
inflates a size that was already large enough.

## 4. What the shots show

| finding | visible in `out/console-after/` |
|---|---|
| B-03 | `1440x900/records-en.png`: `2026`, then `OCTOBER` alone — no `十月` in the English build; the Chinese shot keeps `十月 OCTOBER` |
| B-15 | the three event titles are set in the display face at a real step above their metadata; the metadata row keeps the mono, uppercase, letterspaced treatment |
| B-01 | `records-night-open-en.png`: the audit log names the action instead of printing `event_backfill` |
| B-02 | the night's sign-off prints `10/2/2026, 10:23:40 PM`-shaped text, not an ISO instant with microseconds |
| B-04 | `tonight-play-*.png`: every collapsible panel header carries the brass `▸`, and `▾` when open |
| B-07 | `records-night-open-en.png`: `▸ This night's log (24)` and `▸ Other saved changes (not archived yet) (54)` in brass — Chrome's grey triangle is gone from both folds; this shot is what proved the first attempt (a `list-style:none` reset on the wrong element) was a no-op |
| B-12 | Tonight's two formerly identical `Queue` headings now read `Waiting to play` and `On a table now` |
| §13.1 | one timer with controls: the header slot renders one `[data-clock]`, and `scoreboardScreen()` / `floorScreen()` render none |

## 5. One timer, and how it is asserted

The round-2 contract deleted the whole `#strip` row, but that left a hole no lane could read out of
the text: `render()` injected a timer into `#strip` **and** `scoreboardScreen()` injected a second
complete copy with its own Start / Reset and its own presets (measured before the fix:
`clockCount = 2`, both reading `SHOT TIMER live · synced 0:30`). The decision is **the header slot
survives**: the timer is in the bar's first slot, the design requires it in every venue state while
a scoreboard exists only in `active`, and the slot's contents are specified exactly once. The
Vision stage bar keeps its single read-only `[data-clock]` (a readout with no controls is not a
second timer). `tests/test_ops.js` fails if a `[data-clock]` with controls ever reappears in the
scoreboard or the floor, so the decision cannot be undone by accident.

## 6. Two harness defects that had to be fixed before the shots existed

The re-shoot above is the **second** attempt. The first two runs died with `Page.navigate did not
answer within 600s` and wrote 0 PNGs — and the harness's own spawned fixture was the cause: it was
started with `subprocess.PIPE, stderr=subprocess.STDOUT` and nothing ever drained that pipe, so a
fixture that logs every request *before* answering blocked itself inside `log_request` once the
64 KiB buffer filled. The process stayed LISTENing at 0 % CPU, answering nothing: `/`,
`/api/operations` and `/annotator/ops.js` all timed out while the socket stayed open. Two
hypotheses were disproven on the way — six simultaneous long-lived `/api/clock/stream` connections
do **not** hold the store lock (`/api/operations` answered in 2 ms with all six open), and twenty
cold navigations leave the fixture at one thread. The pipe is now drained on a thread, mirrored to
`out/console-*/fixture.log`, and a failed pass prints that tail instead of nothing. The smaller
defect: `--skip-metrics` was declared and never read, so the header measurement ran even when it
was not asked for.

## 7. Honest limits

- **The intermediate wave-10 bar was never photographed.** Its pass ran three times on a box at
  `load average` 30–45 (another session's microVM plus several browsers) and every attempt died at
  the stall guard — the last one exited at `02:09:45` with one PNG on disk. The wave-10 bar was
  live for under four hours and was replaced by this round's; its numbers survive only as the
  "before" column above, which comes from the brief, not from a picture.
- **Theme and state coverage.** The 22 shots are dark theme except `records-light-en.png`; the
  light theme across all five screens was covered by the round-2 audit's campaign
  (`out/impeccable-r2/shots/`, 92 PNGs), not by this harness.
- **The phone header is 116 px**, above the 60–90 px band — that band was stated for the desktop
  one-row bar. The phone keeps its two-row stack (timer row + tools row) above the fixed tabbar by
  design, and nobody has yet decided that 116 is the right number for it.
- **Ball legibility at 16 px / 34 px** is judged from the CSS and the PNGs, not measured
  pixel-by-pixel; there is no "smallest readable number disc" measurement.
- **The public board has no light theme at all** (finding B-14, carried open for the owner), so its
  §3 numbers are dark-only and EN-only.
- **`label`-level type came from computed styles**, not from rendered glyphs: sub-pixel differences
  below 0.1 px are not visible in the JSON.
- **The box was loaded throughout** (load 20–33). One earlier measurement pass stalled on
  `records-zh` and one full screenshot pass wrote 0 PNGs in 23 minutes; the evidence above comes
  from the passes that completed (22 PNGs, 8 metrics, 0 problems).

## 8. Round 3: the laptop width, and the twenty findings a blind rater found there

The independent rater's round-2 pass sat at **1280×900** — the width round 2 never measured — and
returned `visual 4 / clarity 3 / pass false / 20 issues`. Round 3 fixed all twenty; the ledger has
one row each (`docs/impeccable-ledger.md`, section "Round 3 — the blind rater's twenty findings"),
including the three this round's own probes found and no lane had claimed. This is the pictorial
half.

| viewport, 900 tall | EN dark | 中 dark | what changed |
|---|---|---|---|
| 1024 | 121 → **57 px** | 121 → **57 px** | `nav` holds one row (96 → 44), `.tools` one row (84 → 40), the preset chips leave the bar |
| 1152 | 121 → **58.2 px** | 121 → **58.2 px** | as 1024 |
| 1280 | 121 → **59 px** | 74.5 → **59 px** | the rater's own width: two ragged rows became one, with `#nav` at 44 px and `contentTop == headerHeight` |
| 1440 | 79 → **59 px** | 79 → **59 px** | the presets come back, every chip ≥ 32 px |
| 1920 | 79 → **59 px** | 79 → **59 px** | `#backfill-open` gets its word back (icon + word below 1440) |

All 20 rows (five widths × EN/中 × dark/light) measured identical in both themes, with
`scrollWidth == viewport`, no clipped control and no header control under 32 px. The rest of the
twenty, from the harness's own instruments:

| finding | before | after |
|---|---|---|
| F2, the Vision stage's empty state | 390: `figure.stage` 0 px tall, the box 48 px, the sentence's 2nd line painted on `--stage-bg` at **2.97:1** | `#stage-empty` == `figure.stage` == **372×96**, both lines on the box's own background, **6.54:1** light / **6.91:1** dark, floor 32 px with the box hidden |
| F19, the Backfill wizard | 593.3 px in a 1218.6 px main | **1218.6 px**, prose still capped at `--measure` |
| F13, an expanded night's matches | badges at x 222.7 / 196.4 / 282.6 / 224.4 / 294.2 / 251.2 / 308.1 | score column and badge column line up in all 7 rows at 1280 (badge right edge 1232.3) and at 390 (361) |
| F7 / F8 / F10 | the phone tab bar's "Back room" on 2 lines; the scoring note over 3 lines; "House rating (manual)" over 3 lines | five slots 74.8×52 one line each; note 332×22.5 with the three buttons on one row; head cell 180×14, row 18 px |
| F14 / F15 | "archive" existed only inside a sentence, and the numbered keys did nothing | the End-of-the-night card on every Back room state (1218.6×231.5, `Archive & new event` enabled, `Delete event` disabled with a `role=status` reason); real CDP presses move Digit3→`#/records`, Digit4→`#/vision`, Digit5→`#/regulars`, Digit6→`#/backroom`, Digit1 flips the timer |
| F20, the board's clock | an unbounded "12 h 25 min" with nothing saying what it measured | labelled `Time on table` / 「台上时长」, amber + "check the table" past `ATTENTION_MS = 2 h`, and the number **freezes** at the last server-confirmed answer while the board is stale |

**How to reproduce it.** The console pass is unchanged apart from the new `laptop` size:

```
.venv/bin/python tests/console_shots.py --build after \
  --chromium /home/haoye/projects/pool-w-shots/out/browser/cp-shots \
  --states tonight-play,records --sizes laptop,desktop,phone --langs en,zh
```

The Vision shots need a fixture that serves the review workspace, which the harness's own fixture
does not. One command serves the seeded club, the console, the review workspace and the public
board:

```
PYTHONPATH=. .venv/bin/python tests/serve_workbench_fixture.py \
  --port 8167 --public-port 8168 --public-prefix /board --state tests/console_fixture_state.json
```

`tests/smoke_rating_fixture.py --label after` is the measuring tool for that fixture (it starts its
own headless Chromium, because the shot harness pins its fixture to 8150/8151).

**Where the round-3 pictures are.** `out/console-after/1280x900/` and `out/console-after/390x844/` —
22 PNGs each (18 harness shots in EN and 中文, three Vision shots the harness has no state for, and
one 中文 public board shot, since the harness pins the board to EN), plus `manifest.json` (every
shot's pixel size, sha256, `mainChars`, and the `ops.css?v=vision-stage-22` sheet with its 547
rules), `vision-manifest.json`, `board-zh-manifest.json` and `fixture.log`. The instruments and
every raw number are in `out/r3m/`. All of `out/` is gitignored: this is untracked evidence, not a
commit.

- **Limits.** The harness has no Vision state and no 1024/1152/1920 sizes — the five-width header
  matrix and the Vision geometry are `out/r3m/`'s instruments. The three Vision shots show the
  empty stage (the shape a fixture without review tools produces), not a populated workspace, so
  the stage's *populated* layout is still unphotographed; the rating fixture above is what a
  reviewer should use. The public board remains dark-only (round 2's B-14, the owner's call), and
  `ATTENTION_MS = 2 h` is a product judgement rather than a measurement.

## 9. Round 5: the nav's sixth item, and the width it cost

The owner's round-5 items made the shot timer a destination of its own, first in the nav, with ball 1
(`docs/console-redesign.md` §16.4). That is a sixth item in a row that had ~9.6 px of slack at 1024 px,
so the claim in §14.1 — one row, 1024 up — had to be re-measured rather than argued.

**The measurement found a real regression.** At 1024 px in English the bar wrapped to two rows
(`bar 104 · nav 92`); Chinese still fitted (56 / 44) because its labels are shorter:

```
  header 1024x900  tonight-play en bar=104 nav=92 strip=- tabbar=0 contentTop=105
  header 1024x900  tonight-play zh bar=56  nav=44 strip=- tabbar=0 contentTop=57
```

`out/r5/probe_bar.py` (kept with the round-5 evidence) measured why: the timer slot is **311.5 px** of a
**962.8 px** content box — the word "Shot timer" 60.5, the clock 83.5, Start, Reset — and the five
destinations need another 546 px plus gaps, so the tools row pushed `Back room` (111.4 px) onto a
second row. The fix trades the slot's two redundant controls for the row: below 1152 px the visible
word and Reset go (`annotator/ops.css`), and the destinations tighten their gap and padding. The tab
keeps its name through `aria-label`, so hiding the word cannot leave it unnamed.

| Width · language | Before | After |
| --- | --- | --- |
| 1024 EN | bar 104 · nav 92 (two rows) | **bar 56 · nav 44** |
| 1024 中 | 56 · 44 | 56 · 44 |
| 1152 EN / 中 | 57.2 · 45.2 | 57.2 · 45.2 |
| 1280 EN / 中 | 58 · 46 | 58 · 46 |
| 1440 EN / 中 | 58 · 46 | 58 · 46 |
| 1920 EN / 中 | 58 · 46 | 58 · 46 |
| 390 EN / 中 | 48 · nav hidden · tabbar 53 | 48 · nav hidden · tabbar 53 |

`contentTop == header height` at every one of those sizes (57 / 58.2 / 59 / 59 / 59 / 49), which is what
"sits in one row" means in this document: nothing below the header overlaps the content.

**How to reproduce.** The harness now knows the three widths §14.1 names, so the whole matrix is one
command (the fixture and the browser are the harness's own, 8150/8151):

```bash
.venv/bin/python tests/console_shots.py --build after --measure-only \
  --sizes small,mid,laptop,desktop,wide,phone --langs en,zh --out out/r5-measure
# and, for the per-item geometry behind the fix:
.venv/bin/python out/r5/probe_bar.py 1024,1152
```

**What is where.** `out/r5-measure/manifest.json` carries all 24 measurements (six widths × two
languages × two routes) with the fixture at revision 111 and `chromium restarts: 0`; `out/r5/` keeps
`probe_bar.py` and the raw geometry it printed. Both are gitignored evidence, not commits.

**The phone found two more, and the matrix could not see either** — because it reads the bar's
height and not what is inside it. `out/r5/probe_tabbar.py` (kept with the round-5 evidence) measures
the header's timer and each bottom-bar slot's own text width:

1. **the clock left the phone header.** The slot now lives inside `#nav`, which the phone query hides
   to make room for the fixed bottom bar: measured `nav=none` and a 0×0 slot at 390 in both
   languages. The nav stays on the phone now and only its destinations go — the slot measures 176 px
   (ball, `0:30`, Start; the word and Reset are already gone below 1152), the chips 110, the bar's
   padding and gap 36, so 311 of 390 px.
2. **four of six labels were truncated.** Six slots divide 390 px into 62 px cells and the mono
   uppercase label needed 80 px for `Tournament` ("SHOT TIM", "TOURNAME", "BACK ROO"). Each slot now
   stacks its destination's ball over its label, the label is the body face at 11 px sentence case
   (`Tournament` 57.8 px), and the bar's 4 px gap plus the slot's 4 px padding — which were what
   pushed it out of its box — are gone on the phone, giving 65 px cells.

| 390×844 | Before | After |
| --- | --- | --- |
| the header's clock | hidden (`#nav` none, slot 0×0) | ball 1 + `0:30` + Start, slot 176 px |
| the bar's slots | 62 px cells, 4 of 6 labels cut | 65 px cells, 6 of 6 fit |
| the bar's content | the word alone | the destination's ball + the word |

The ball is the map of `docs/console-redesign.md` §16.3 (1 yellow for the timer, then 2 blue, 3 red,
4 pink, 5 orange, 6 green), so the phone bar now reads as the same colour law the rest of the
product uses. The pictures are `out/r5-shots2/390x844/` against the first pass in
`out/r5-shots/390x844/`; the harness gained a `clock` state (`AFTER_STATES`) so the new screen is
photographed like any other, and `tests/test_ops.js` asserts both fixes.

- **Limits.** The harness still has no Vision state, and the round-5 shots cover the shell, the new
  clock screen and the phone bar; the round-3 set in `out/console-after/` remains the last picture of
  the console's other screens. The board is unchanged and still dark-only. The 1152 px breakpoint is
  a measurement of 1024's overflow, not a designed boundary: between 1024 and 1152 the slot shows no
  word and no Reset on any width.

## 10. Item 8: the picker's own pictures, from a live server

The Backfill picker used to name three broadcasts and show nothing beside them. It now shows each
broadcast's own preview picture — fetched by **this** server, not by the browser from an image CDN.

This shot cannot live in the fixture run above: its rows come from Twitch, so it needs the network and
a live server. The whole reproduction is four commands and one page.

```sh
.venv/bin/python annotator/unified_server.py --port 8170 --root ~/projects/pool &
B=/home/haoye/.local/share/npm/lib/node_modules/agent-browser/bin/agent-browser-linux-x64
AGENT_BROWSER_SESSION=picker $B open 'http://127.0.0.1:8170/#/records'
AGENT_BROWSER_SESSION=picker $B set viewport 1280 900
AGENT_BROWSER_SESSION=picker $B click '[data-action="backfill-open"]'
AGENT_BROWSER_SESSION=picker $B screenshot out/r5-picker/backfill-pick-1280-en.png
```

What the page itself reported (read back with `$B eval`, so these are the browser's numbers, not the
stylesheet's intent) — at 1280×900 and again at 390×844:

| what | 1280×900 | 390×844 |
| --- | --- | --- |
| rows carrying a picture (`img.bf-thumb`) | 3 | 3 |
| loaded (`complete` and `naturalWidth > 0`) | 3 of 3 | 3 of 3 |
| the decoded asset | 320×180 each | 320×180 each |
| the box it is drawn into | 160×90 | **112×63** |
| document `scrollWidth` vs `innerWidth` | 1280 vs 1280 | 390 vs 390 |

The `src` every row asked for is a path on this server —
`/api/vods/thumb?channel=ttpoolfriday&id=2890514774`, and `…436`, `…358` for the others — never
`static-cdn.jtvnw.net`. The three broadcasts are `261001` (2026-10-02, 4:34:15), `261001`
(2026-10-02, 4:31:33) and `260918` (2026-09-25, 3:43:17): the saved channel's whole archive. On the
phone the row's title moves above its date, and the pictures stay 16:9.

The HTTP layer under the same run, checked directly:

| request | answer |
| --- | --- |
| `GET /api/vods/thumb?channel=ttpoolfriday&id=2890514774` | 200 `image/jpeg`, `Cache-Control: no-store`, 19 742 bytes, `ff d8 ff … ff d9` |
| `GET /api/vods/thumb?channel=<not saved>&id=2890514774` | 403 `This VOD belongs to <that channel>. Only saved channels can be analysed; add the channel under Source first.` |
| `GET /api/vods/thumb?channel=ttpoolfriday&id=<unknown>` | 502 `Twitch has no such video` |

**On production, after the restart.** `pool-workbench.service` was restarted at 16:48:50 PDT
(`systemctl --user restart pool-workbench.service`, `MainPID 396105`, `NRestarts=0`, `:8130` and
`:8132` listening again) because the static half was already live and the python half was not: the
same route, checked against the real port rather than the private one, answered `/api/vods/recent` 200
with the three local `thumb` paths and `/api/vods/thumb` 200 `image/jpeg` `no-store` 19 742 bytes
`ff d8 ff … ff d9`, an unsaved channel 403, `/api/board` 200 and the public board 200. The production
console was then read with the same browser tooling (`AGENT_BROWSER_SESSION=prod8`) and reported **3
pictures, 3 loaded, natural 320×180, drawn 160×90, `scrollWidth == innerWidth == 1280`** —
`out/r5-picker/prod-pick-1280-en.png`, shot against the real club state, not a fixture.

Limits, stated plainly: this shot needs the network, so it is not part of the offline fixture run and
its numbers cannot be reproduced on a box with no route to Twitch; the archive here is three
broadcasts, so the bound a busier channel would need is argued in `docs/console-redesign.md` §16.7
rather than measured; and a **night** per broadcast — the timeline half of item 8 — is still not built.

## 11. Round 6: Records as the archive's timeline, on the real channel

The owner's next order — "make the records the timeline view of all twitch vods. make sure its
showing" — is the first screen in this document whose evidence is entirely live data from the club's
own channel. There is no fixture for it and there cannot be one: the rows are Twitch's answer.

Reproduce (the private server, so production is untouched while measuring):

```
cd /home/haoye/projects/pool
nohup .venv/bin/python annotator/unified_server.py --port 8171 --root /home/haoye/projects/pool > /tmp/priv8171.log 2>&1 &
ss -ltnp | grep ':8171'                      # ~20 s after launch it is listening
AGENT_BROWSER_SESSION=r6b /home/haoye/.local/share/npm/lib/node_modules/agent-browser/bin/agent-browser-linux-x64 \
  open 'http://127.0.0.1:8171/#/records'
# then: set viewport 1280 900 ; eval "<the measurement below>" ; screenshot out/r6-archive/…
```

| measured in the live page | 1280×900 | 390×844 |
| --- | --- | --- |
| the card's heading | `Recorded nights` | same |
| the count | `31 videos · 0 built` | same |
| rows | **31** (`.tl-item.tl-vod`) | 31 |
| each row's meta | `10/2 Fri · 4:34:15 · Broadcast · ttpoolfriday`, `9/27 Sun · 3:43:17 · Highlight · …` | same, wrapped |
| pictures | 31 `<img class="tl-vod-thumb">`, natural `320×180`, drawn `160×90` | drawn **`112×63`** |
| decoded at rest | **18 of 31** — the rest are below the fold and `loading="lazy"` | the visible ones |
| horizontal overflow | `scrollWidth 1280 == innerWidth 1280` | `390 == 390` |
| the two actions a row can offer | `Build this night` (nothing built yet) / `Open the night` | same |

On production, after `systemctl --user restart pool-workbench.service` (22:43:35 PDT, `MainPID 724298`):

| check | answer |
| --- | --- |
| `GET :8130/api/vods/recent` | 200 · `ttpoolfriday` · `more false` · **31 vods** · kinds `ARCHIVE`+`HIGHLIGHT` · 31 with `thumb` |
| `GET :8130/api/vods/thumb?channel=ttpoolfriday&id=2890514774` | 200 · `image/jpeg` · 19 742 B · SOI `255 216 255` |
| served `/ops.js` | 150 389 B, carrying `kindHighlight` and `archiveMore` |
| the live `#/records` page on `:8130` | `31 videos · 0 built`, 31 rows, `Broadcast`/`Highlight`, 31 pictures, no overflow |

The pictures this section leans on are `out/r6-archive/records-archive-1280-en.png` (the top of the
list), `records-archive-1280-mid-en.png` (scrolled: the older full-night records and then the clips —
`(runout) 260612 · 0:03:00`, `260529 run out · 0:01:06`), `records-archive-390-en.png` (the phone) and
`prod-records-archive-1280-en.png` (production, real club state).

Limits, stated plainly: this is the one screen whose content cannot be pinned by a fixture — the
archive is whatever Twitch answers, so the numbers above are dated 2026-10-03 and a channel that
publishes a new VOD changes them; the three long-lived `HIGHLIGHT` recordings are the club's own
`(Record) YYYYMMDD` files, and Twitch's word for them is the one the row prints; nothing here infers a
night from a title or a picture, so a row only becomes a night in the log when an operator builds it,
and today **0 of 31** are built; and the lazy images mean "shown" is smaller than "present" by design
(18 of 31 at rest), which is why both numbers are printed rather than one.

## 12. Round 7: one rectangle per human, a timer with its own bar, and a first run that is a dialog

Round 7 answered five things the owner asked for on 2026-10-03 23:29 PDT; the reasoning and the code
are in `docs/console-redesign.md` §18. The pictures are `out/r7/`.

Reproduce (the console is served from disk, so nothing needs restarting):

```
B=/home/haoye/.local/share/npm/lib/node_modules/agent-browser/bin/agent-browser-linux-x64
AGENT_BROWSER_SESSION=r7 $B open 'http://127.0.0.1:8130/?r7=2#/tonight'
AGENT_BROWSER_SESSION=r7 $B set viewport 1280 900
AGENT_BROWSER_SESSION=r7 $B eval "<the reads below>"
AGENT_BROWSER_SESSION=r7 $B screenshot out/r7/after-tonight-registration-1280.png
```

The bar, measured in the live page at 1280×900 (production):

| element | top | height | width | left |
|---|---|---|---|---|
| `.bar` | 0 | 110 | 1280 | 0 |
| `.clockbar` (the timer's own row) | 6 | 46 | 1219 | 31 |
| `.barrow` (destinations + tools) | 60 | 44 | 1219 | 31 |
| `#nav` (six items) | 60 | 44 | 807 | 31 |
| `.tools` | 64 | 36 | 169 | 1080 |

`document.scrollWidth` 1280 = `window.innerWidth`; the bar reads `0:30 Start Reset 20 30 45 60` with no
ball and no `data-tab` in it, and the nav carries all six balls with `Digit1`–`Digit6`; the presets are
visible again from 751 up. At 1024×900 the nav is also one row (665 px inside a 1000 px row). At
390×844: `.bar` 100 px tall, `.clockbar` `top 6 h 40` reading `0:30 Start Reset`, `#nav` computed
`display: none`, `#tabbar` `top 847 h 53` with `["1Shot timer","2Tournament","3Records","4Vision",
"5Regulars","6Back room"]`, `.presets` computed `none`, and the six cells are 65 px each with labels
measuring 50.1 / 57.8 / 39.5 / 29.3 / 41.8 / 50.9 px, so none is clipped; `scrollWidth` 390 = the
viewport.

The first run, measured on an unnamed-night fixture and on an isolated real server:

| read | value |
|---|---|
| the page behind | `.idle-registration` present, `inert`, `aria-hidden="true"`, `opacity 0.3`, `pointer-events: none` |
| the dialog | `.modal--start`, `role="dialog"`, `aria-modal="true"`, title `Start tonight`, fields `name/format/raceTo/tables`, primary `Start tonight →`, no Close on the first run; 358×492 at 390×844, no overflow |
| after submitting | `{modal: false, dim: false, desk: true, draw: "Start the event →", door: true, message: "Saved."}` and the state file revision 111 → 112 with `tournament_setup` in `events` |
| the door for a named night | the same dialog with `["Save","Close"]` |

The one-rectangle change is photographed on the live stage: `out/r7/before-tonight-idle-1280.png` is
the old Tonight (tutorial + form + two buttons) and `out/r7/after-vision-one-box-1280.png` is the
Vision stage with one green rectangle per human (`persons 4` in the facts line, ten ball boxes, no
model person boxes) where the same frame used to show fourteen rectangles and `personBoxes: 4`.

Limits, stated plainly: the fixture (`tests/serve_workbench_fixture.py`) answers writes with 200 but
**does not persist them** to its `--state` file, so every write-path claim above was taken against
`annotator/unified_server.py` on an isolated root (`/tmp/r7-root`, with `<root>/annotator` symlinked,
because the console HTML is served from there); the Vision frame is a stored inference from
2026-09-16, so "one rectangle per human" is one frame at one moment, judged by eye and by IoU; and the
phone bar's numbers are computed styles plus a screenshot, not a device.

The owner ruled on 2026-10-04 that the bar and the timer's tab must be separate things, so §12's first
cut (the bar holding ball 1 and the word as one clickable tab, five slots in the bottom bar) was
replaced the same day. Shots of the ruling: `out/r7/after-bar-b-six-balls-1280.png` (EN) and
`after-bar-b-six-balls-1280-zh.png` (中), plus `after-phone-bar-390-b.png` for the six-cell bottom bar.
The measurement commands are the ones above with `?r7b=1` as the cache-buster.
