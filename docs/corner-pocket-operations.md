# Corner Pocket operations

Implementation in progress. The required application hierarchy is **Floor · Set up · Matches · Vision · Regulars · Back room**. Vision is the fourth top-level tab and contains native subtabs for **Event review · Ball labels · Table calibration · Player identities · Video timeline · Stream/source controls**. The existing review tools must be integrated into this shell, not presented as a separate application or optional iframe. Club management remains fully available outside Vision. Regulars are registered club members; Vision player identities are video-track annotations and must not be silently conflated.

Native integration must preserve unsaved edits, in-flight saves, frame-request guards, and keyboard focus when navigating. Visual parity alone is not functional completion.

## State and API

`annotator/operations.py` owns `out/corner-pocket/state.json`. The first GET returns an empty club and registration-stage tournament; no prototype people, scores, or observations are imported. Mutations use atomic file replacement and a shared in-process lock. Run only one server process against a given state directory.

- GET `/api/operations`: current state.
- POST `/api/operations`: `{revision, action, ...actionFields}`; returns committed state with incremented revision.
- A stale revision returns HTTP 409. Reload and review the latest state before resubmitting; do not silently replay a stale action.
- Invalid actions return HTTP 400 without changing persistent state.
- Existing same-origin write protection and private Access deployment remain applicable. Player notes and tournament history are private operational data.

Actions cover player records, singles/doubles entrants, tournament setup/start/archive, table assignment, scores, signed results, absences, forfeits, settings, source registration, and notes. See `Operations._apply` for authoritative payload validation.

## Shot clock — one clock, every device

The shot clock is **shared across devices on purpose**. The club PC, a phone, a tablet, any browser and any tab show the same clock: whoever presses Start, Pause, Reset or 20/30/45/60 sets the clock everybody sees. This is the product decision, not a limitation — a shot clock only one device can see is not a shot clock. The old per-device behaviour and its label ("Shot clock · local timer, not shared" / "击球计时 · 本机计时，不联动") are gone.

The clock follows the **server's** clock, not each device's own. A device measures its offset from the server on every answer and displays `deadline − (its own Date.now() + offset)`, so a phone whose system time is several seconds out still shows the same remaining time as the PC.

### What the operator sees

- The clock appears in the strip at the top of every tab, on the Floor scoreboard, and on the Vision stage bar. All of them are painted from one value by ops.js's single 200 ms repaint, so two views on one screen cannot disagree.
- The label reads **"Shot clock · shared across devices"** / **"击球计时 · 多设备同步"**.
- A sync-state line beside the clock says exactly what this device knows:

| State | English | 中文 |
|---|---|---|
| connecting | `connecting…` | `连接中…` |
| the change stream is live | `live · synced` | `实时 · 已同步` |
| stream down, polling every 1 s | `reconnecting — showing last known` | `重新连接中 — 显示最后已知` |
| no answer for 10 s | `offline — showing last known` | `离线 — 显示最后已知` |
| a command POST failed | `clock command failed — nothing changed` | `计时指令失败 — 未改变` |
| the server is out of slots (503) | `server busy — retrying` | `服务器繁忙 — 正在重试` |

- Expiry still reads "Shot time expired. No penalty applied." / "击球时间到。未自动判罚。". Each device may show it once; expiry is never a penalty and never a write.
- A command that did not land never looks like it did: a failed POST shows the error, leaves the displayed time alone, then pulls the truth back from the server.
- Start keeps its existing guard — it refuses while the live match has absent players — and a refused press sends nothing to the server.

### When the network drops

- While the stream is healthy the page listens to `GET /api/clock/stream` (`EventSource`): changes arrive as they happen, plus a heartbeat every 15 s. "live · synced" means the stream spoke **recently** — an open socket that has gone quiet is not treated as synced.
- If the stream errors, or 30 s pass with no heartbeat (two missed heartbeats), the page falls back to polling `GET /api/clock` **every 1 s** until the stream reconnects, and the clock is labelled "reconnecting — showing last known". The last known time stays on screen and keeps counting down; it is never blanked or frozen silently.
- After 10 s with no answer at all the label becomes "offline — showing last known".
- Coming back is immediate: `visibilitychange` (page becomes visible), `focus` and `online` each trigger a fresh `GET`. Phones throttle background tabs, so returning to the tab never waits for the next poll.
- A 503 from the bounded server is not an exception: `Retry-After` is honoured (capped at 60 s), the label reads "server busy — retrying", and polling pauses until then.
- The clock keeps running through all of this. The deadline is absolute on the server, so a dropped connection only changes what a device **knows**, never the time itself.

### The write contract, for operators

- **`GET /api/clock` is side-effect free.** It reads and renders. A clock whose deadline has passed is reported as `running: false, remaining_ms: 0, expired: true` — expiry is an answer, not an event — and nothing is written. This is the same rule as every other read in the app.
- **`POST /api/clock` is the only writer of `out/corner-pocket/clock.json`**, and only on a real change: a Start while already running, or a Pause while already paused, returns the state unchanged and writes nothing. The file is written atomically (temp file + rename).
- The intents are explicit — **`start`, `pause`, `reset`, `set`** — never a "toggle", so two people pressing at once cannot cancel each other out:
  - `start` — runs from what is left; from the full duration once the clock has expired or is at zero. A no-op while already running.
  - `pause` — keeps what is left. A no-op while already paused or expired.
  - `reset` — paused at the full duration.
  - `set` — a new duration, 5–300 s (the same rule as `settings.shotClock`), paused at it.
- The clock is deliberately **not** part of the revisioned operations state, so pressing Start never makes another operator's `/api/operations` write fail with a stale revision.
- It survives a service restart: the deadline is absolute, so a restart does not reset or restart a running clock.
- Until anything has ever been set, the duration comes from `settings.shotClock`. A damaged `clock.json` answers HTTP 500 with a log reference and is **never silently reset**.

The endpoint and its fields are specified once, in `docs/unified-workbench.md` §"API write contract" (the shared-shot-clock bullet). That section is authoritative for the API; this section describes what the operator sees and must not be read as a second contract.

### What was verified, and what was not

Two independent browser sessions against a loopback fixture on this host, at **390 px and 1280 px, in EN and 中**:

- Start on device A reached first paint on device B in **32 ms**; over **20 presses** press-to-update propagation was **p50 282 ms**.
- With a **+5 s skew injected into one session's `Date.now()`** before the page script ran, both sessions matched on second-transitions at **p50 143 ms / p95 143 ms / max 148 ms**, against a 0.3 s bar.
- Screenshots are in `out/shot-clock/` (expiry and language/width pairs).

Limits, stated plainly:

- Every number above was measured **on this host, on loopback, through the fixture** — not through Cloudflare, and not on the phones or tablets the club actually uses. **The real Cloudflare path was never exercised**; it needs an authenticated browser session.
- The evidence covers EN and 中 at two widths. No other device, browser or version was exercised.
- `tests/test_clock_api.ClockStreamTests` is **load-sensitive on this host** (it asserts 1.0 s wall-clock budgets): it failed twice while the box was at load 26, then passed in isolation. Treat a failure there as load first and a real defect second.

## Tournament rules

Setup and entrant changes are locked after starting. Draws are single elimination with automatic byes. Ready matches must be assigned to an available table before scoring. Reaching the race target does not silently finalize a result: explicitly complete the match. Completed results are immutable and winners advance to dependent matches. Marking a side absent releases the table. Registration-stage `entrant_absence` records attendance before the draw; absence propagates when matches become ready, including after byes. Match attendance updates keep entrant attendance synchronized for later rounds. `match_unschedule` releases a live table while preserving its score, so the match can be reassigned through normal scheduling. Starting a new tournament requires confirmation and archives the previous tournament instead of destroying history.

These are intentional safety improvements over the prototype's destructive bracket rebuilds and random-result demonstration button. Never generate random winners in the real application.

## Sources and evidence

Source registration accepts Twitch channel and video URLs only; it does not fetch arbitrary URLs on the server. Twitch embeds must use the actual browser hostname as their `parent` parameter. Embedding a stream is not ingestion or inference. Do not label source registration as proof that a channel is live.

The existing annotation and local-VOD/frame-inference workbench is being integrated natively under Vision. `/app.html` remains a compatibility entry while this integration is verified. Its A/B track labels are not registered player identities. Single-frame inference cannot establish shots, pots, or accuracy metrics. Do not fabricate balls, observations, statistics, or shooter-to-roster associations from the prototype's simulated canvas data.

## Verification

Use temporary state directories for tests; never save fixtures into production annotations or operations state.

```sh
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
node tests/test_app_timeline.js
```

Operations unit tests cover persistence, stale writes, validation, atomic failure, entrants, doubles, table exclusivity, absences, forfeits, history, sources, settings, guest promotion, bounded audit history, and bracket completion for power-of-two and non-power-of-two entrant counts.

Every successful mutation appends a revision-ordered audit event to `events` (newest 500 retained). Events contain UTC timestamps, action names, and limited target IDs/names; they do not copy private note bodies or source URLs, and do not invent authenticated actor identities. Guest promotion atomically links a current entrant to a new registered player; same-name roster collisions are rejected rather than silently merging identities.

The source server now routes `/` to operations and keeps `/app.html` as the review workbench. The running production process has not been restarted to activate that route. Browser acceptance remains necessary for all six tabs, bilingual forms, mobile layout, tournament lifecycle, reload persistence, and existing review integration.

No hosting restart or external deployment is part of the implementation verification phase.

## The late arrival chooses a match-up

The console card "Join after the draw" opens a dialog. The server refuses any arrival that does
not state a match-up, so every client is compelled, not only the browser.

- Match-up: `none` (the arrival takes a slot of their own and advances on a bye), `revive` (a
  first-round loser plays them), or `new` (a person registers as the opponent).
- Teammate, in a doubles event: the same three choices. A doubles arrival that states none is
  refused.

`POST entrant_add_late` takes `opponent` and, for doubles, `partner` in that set; `opponent_entrant`
and `partner_entrant` name a round-one loser and must be in the second-chance pool; `opponent_name`
and `partner_name` name a new person, who is registered as an entrant. One person may not appear on
both sides of the match. The match records `lateOpponent` and `latePartner`.

Measured on a scratch club (4 entrants, round one played, race to 7): no answer is refused by the
browser and the revision does not move; `revive` gives one late match, sides "Late Lou" / "Bo",
status `scheduled`; `new` with the name "Nina New" gives "Late Sam" / "Nina New"; one person in both
slots is refused with "That person cannot play on both sides of the match"; in doubles, `revive` /
`revive` gives "Doubles Late + D1" / "B1 + B2" with both pair members present. A defect the run
found: the dialog stayed open after a save, so the poll could not repaint it and the operator was
stuck. The save now closes the dialog.
