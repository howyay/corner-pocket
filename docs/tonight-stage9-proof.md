# Tonight console — stage 9 proof

Owner lane: internal-audience C′ stages 5–9. Branch `tonight`, worktree `~/projects/pool-tonight`.
Proof run 2026-10-01 (UTC) against **this worktree only**; the production checkout `~/projects/pool`
was never written to, never restarted and never POSTed to.

Code under proof (all four on branch `tonight`):

| stage | commit | subject |
| --- | --- | --- |
| 4 | `7fc7a7e` (merged into `main` as `e9c4899`) | Tonight shell, phase strip, Register |
| 5 | `919ce35` | Tonight stage 5: Play is Queue \| Tables \| Bracket with one scoring model |
| 6 | `c9f4ec2` | Tonight stage 6: Close owns the results sheet, second chance and the end of the night |
| 7 | `2c06570` | Tonight stage 7: the fixed bottom bar at 750px, with More for Regulars and Back room |
| 8 | `e805b10` | Tonight stage 8: Floor and Matches retire into Play, and their old routes still land there |
| 9 | this document | Tonight stage 9: the proof — measures, inventory and screenshots |

`main` was `91f0ff6` throughout (ancestor of `HEAD`); every stage boundary rebased cleanly.

## 1. The acceptance criteria, before and after

The criterion is the directive's: T2 zero tab switches and zero jumps at both widths, T1 zero tab switches,
T3 at 390 px has the Send control within one screen.

BEFORE = `out/ia/measure-results.json` from the live checkout (`~/projects/pool`), origin
`http://127.0.0.1:8210`, started `2026-09-29T01:44:07.175Z`, 10 tasks, 175 checks, 0 errors.
AFTER = `out/tonight/after/results.json` from this worktree, origin `http://127.0.0.1:8251`, started
`2026-10-01T05:41:37.727Z`, 10 tasks, 193 checks, 0 errors, 4 dialogs, 17 screenshots.

Numbers are `tabSwitches / autoJumps / clicks / scrolls / scrolledPixels`.

| task | width | before | after | verdict |
| --- | --- | --- | --- | --- |
| T1 register the night | 1280 | 2 / 0 / 25 / 3 / 633 | **0** / 0 / 25 / 5 / 1142 | zero tab switches |
| T1 register the night | 390 | 2 / 0 / 25 / 4 / 2111 | **0** / 0 / 25 / 4 / 2297 | zero tab switches |
| T2 send to table | 1280 | 2 / **2** / 9 / 0 / 0 | **0** / **0** / 9 / 3 / 602 | zero switches, zero jumps |
| T2 send to table | 390 | 2 / **2** / 9 / 2 / 500 | **0** / **0** / 9 / 2 / 828 | zero switches, zero jumps |
| T2b score and sign | 1280 | 0 / 0 / 3 / 0 / 0 | 0 / 0 / 3 / 0 / 0 | unchanged |
| T2b score and sign | 390 | 0 / 0 / 3 / 1 / 333 | 0 / 0 / 3 / 0 / 0 | one scroll removed |
| T3 the night's three faces + Records | 1280 | 1 / 0 / 1 / 3 / 886 | 1 / 0 / 4 / 2 / 270 | the one switch is the Records visit |
| T3 the night's three faces + Records | 390 | 1 / 0 / 1 / 3 / 1978 | 1 / 0 / 4 / 2 / 888 | the one switch is the Records visit |
| T4 Vision | 1280 | 2 / 0 / 2 / 0 / 0 | 2 / 0 / 3 / 0 / 0 | Vision is a top-level surface by design |
| T4 Vision | 390 | 1 / 0 / 1 / 0 / 0 | 1 / 0 / 1 / 0 / 0 | unchanged |

**Send within one screen at 390 px.** Measured on the surface that owns the control:

| measurement | before | after |
| --- | --- | --- |
| first `[data-action="schedule"]`, T3 at 390 | `matches-night-390.firstSend = 1978` px (page 3733 px, viewport 844 px) | `queue-night-390.firstSend = 840` px (page 1327 px, viewport 844 px) |
| first `[data-action="schedule"]`, T2 at 390 | — | `floor-live-390.firstSend = 414` px |
| per-table scoreboard, T2 at 390 | `floor-live-390.scoreboard = 241` px | `floor-live-390.scoreboard = 386` px (page 884 → 1489 px: the clock and the card grew with the table) |

So Send went from 2.3 screens down to inside the first screen (840 ≤ 844, and 414 when a match is already on a
table). Between stages 4 and 8 the page never leaves Play: the old flow's `autoJumps` are gone.

### How the AFTER run drove the new console

`out/ia/measure.js` in `main` drives the old IA through `#nav button[data-tab="setup"|"floor"|"matches"]`, which
stages 4 and 8 retired. That file was **not** modified. A copy was made and only the navigation step was
rewritten, so the task bodies, the measurements and the pass criteria are unchanged:

| old IA target | new control |
| --- | --- |
| `setup` | Play phase, `[data-phase="register"]` (Register is phases, not a tab) |
| `floor` | Play → `[data-play="tables"]` |
| `matches` | Play → `[data-play="bracket"]` |
| (new) queue | Play → `[data-play="queue"]`, where Send lives now |

T3 was re-pointed at the three Play faces plus Records in the same visit, because those faces are no longer
separate tabs. Everything else — every click, key, scroll and page fact — is the original script.

## 2. The inventory is intact — 181 in, 181 homed, 0 removed

`docs/impeccable-feature-inventory.md` holds 167 numbered items, no duplicates, no gaps.
`docs/ia-assessment.md` §11 (lines 301–341; the count line is 340) places all of 1..167 across the surfaces and
also names all fourteen S1–S14 findings; its count line still reads "…Total 167. S1–S14 = 14, each placed once
above. 181 in all, with no item removed…". Checked mechanically against the shipped console:

* `navTabs` = tonight, records, vision, players, status — no retired tab left in the row;
* `phases` = register, rack, play, close, all four always clickable;
* `playTabs` = queue, tables, bracket;
* every home code used by §11 (T, R, V, Rg, BR) still exists as a surface.

Result: `167 + 14 = 181, none homeless, none removed`.

## 3. Screenshots — enemy and Chinese, 1280 and 390, dark and light

52 PNGs in `out/tonight/` (6.3 MB): every combination of `{en, zh} × {dark, light} × {1280×800, 390×844}`
covering Register, Play→Queue, Play→Tables, Play→Bracket, Close and Records, plus the bottom bar with More open
at 390 px.

Per-shot facts recorded in `out/tonight/shots-results.json` (68 checks):

* console errors 0, uncaught exceptions 0, log entries 0, dialogs 0;
* CSP violations 0 (`securitypolicyviolation` listener installed before the first navigation);
* horizontal overflow 0: `scrollWidth == documentElement.clientWidth` in all 52 shots (1280 = 1280, 390 = 390);
* bottom bar height: 0 px at 1280 (hidden), 53 px at 390, 114 px with More open;
* visible Send on Queue at 390: 840 px (en) / 832 px (zh), inside the 844 px viewport;
* visible scoreboard on Tables at 390: 627 px (en) / 634 px (zh) — one screen again;
* the shot clock renders in the top strip on every surface except Play, where it renders inside the focused
  table's scoreboard, so the operator sees exactly one clock.

## 4. Test suites

* `node --test tests/test_ops.js` — **102/102 pass** (stage 8; stage 9 adds this document only).
* `node tests/test_app_timeline.js` — **80 passed, 0 failed**.
* Full Python suite on this exact tree —
  `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q` →
  `Ran 1213 tests in 346.365s`, `OK (skipped=52)`, exit 0. The one flaky test in this suite is
  `test_clock_api.ClockStreamTests.test_a_stream_outlives_the_socket_timeout` (a 1 s socket timeout against a
  0.3 s heartbeat under host load); it passed in this run, and this lane touched no clock file.

## 5. What this proof does **not** cover

* The Cloudflare path (`pool.example.com`, the `/board/` public board) and the production console at
  `127.0.0.1:8130` — never touched. Every number here comes from a loopback fixture on `127.0.0.1:8251` serving
  this worktree's files.
* No physical phone or tablet. `env(safe-area-inset-bottom)` evaluates to 0 in headless Chromium, so the 53 px
  bar is 52 px of bar plus its border, not a device with a home indicator.
* The shot clock's cross-device sync over a real network; the fixture keeps it in one process.
* Light/dark rendering on a real display panel (colour tokens are asserted by `tests/test_palette_contrast.py`,
  not by eye here).

## 6. Commands

```
# fixture (copy of tests/serve_workbench_fixture.py on its own port; untracked, git-excluded)
.venv/bin/python tests/_b7_tonight_fixture.py            # 127.0.0.1:8251

# measures (browser work serialised host-wide)
flock "$TMPDIR"/pool-browser.lock systemd-run --user --collect --wait --pipe --quiet \
  --working-directory=$PWD -p MemoryMax=8G -- \
  node /tmp/b9/measure.js http://127.0.0.1:8251 $PWD/out/tonight/after

# screenshots
flock "$TMPDIR"/pool-browser.lock systemd-run --user --collect --wait --pipe --quiet \
  --working-directory=$PWD -p MemoryMax=8G -- \
  node /tmp/b9/shots.js http://127.0.0.1:8251 $PWD/out/tonight

# inventory check
node /tmp/b9/inventory.js

# suites
node --test tests/test_ops.js
node tests/test_app_timeline.js
flock "$TMPDIR"/pool-suite.lock systemd-run --user --collect --wait --pipe --quiet \
  --working-directory=$PWD -p MemoryMax=8G -- env PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
```
