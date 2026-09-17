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
