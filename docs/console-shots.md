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
