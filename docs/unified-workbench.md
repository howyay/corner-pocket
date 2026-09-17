# Corner Pocket unified workbench

Run `.venv/bin/python annotator/unified_server.py --port 8130`, then open
http://127.0.0.1:8130. The origin binds only to loopback; external access must
remain behind Cloudflare Access.

## Hosted access

https://pool.example.com uses the existing `pool-tunnel` Cloudflare Tunnel:
`pool.example.com` → `http://127.0.0.1:8130`. Proxied CNAME points to
`11111111-1111-1111-1111-111111111111.cfargotunnel.com`.

Cloudflare Access application `Corner Pocket` protects the entire hostname,
including API/media routes. Pocket ID SSO is the only enabled identity provider;
allow policy is restricted to `owner@example.com`, matching the existing Kaneo SSO
setup. Session duration: 168 hours. There is no public bypass policy.

Origin runs as enabled user service `pool-workbench.service`, with restart on
failure and user lingering enabled. Unit:
`/home/operator/.config/systemd/user/pool-workbench.service`.
Manage with `systemctl --user {status,restart,stop} pool-workbench.service`.

Verified unauthenticated public root/API requests return HTTP 302 to Access;
local metadata returns HTTP 200 and port 8130 listens only on 127.0.0.1.
An authenticated end-to-end SSO session still requires the owner's login.

Visual source: user-supplied `Corner Pocket redesign (1).zip`, particularly its
Corner Pocket Ops standalone HTML. Warm brown, cream and brass tokens, sticky
top header with 8-ball mark, numbered nav, lang/theme chips, slab headings and
brass-edged lamp panels. No new frontend dependencies.
The archive remains the design reference, not an executable dependency.

## Application hierarchy

The main application has six top-level tabs: **Floor, Set up, Matches, Vision, Regulars, Back room**. Existing review modes listed below belong inside **Vision**, alongside Stream/source controls. Native integration is in progress; refer to `corner-pocket-verification.md` for what has actually been checked. `/app.html` remains a compatibility entry, not the intended primary navigation.

Club Regulars are roster records. Vision Player identities are tracking annotations, not automatically identified club members.

## Vision review modes

- Event review: VOD30/highlight candidates, verdict, shooter and notes. Missing
  evidence falls back to a clearly labeled raw source frame. Source video supports
  byte ranges. Writes preserve existing annotation fields and dataset separation.
- Ball labels: all three crop sets, context imagery, 0–15, unknown and clear.
  Existing full-path label keys are preserved. Sets are explicitly independent
  of the VOD selector.
- Table calibration: VOD30 raw frame, six SVG draggable anchors, keyboard and
  button nudging, bounded atomic saves. Order TL/TR/BR/BL/left-side/right-side.
- Player identities: VOD30 windows and boxes, explicit A/B/ignore/clear seeds,
  background rebuild status/errors. Both A and B are required for learned
  propagation; spectators are never automatically selected as B. Stale prototype
  outputs without matching seed metadata are suppressed.

## Video timeline

Choose **05 Video timeline**, jump to a frame or scrub the player and click
**Freeze player frame**. The inspector shows a server-decoded JPEG; ±1 steps
operate from that frozen frame. Run selected detectors, then move/resize boxes,
change labels, or edit table polygon corners and explicitly save corrections.

Browser checks passed: frame 2100 jump, decoded +1 to 2101, isolated polygon
correction persistence, and a real asynchronous table/person run rendering three
person boxes. Native video loaded with readyState 4. At 390 px viewport width,
document width remained 390 px. No browser JavaScript errors were reported.
Frontend syntax and 11 helper/contract tests passed. The browser correction test
used isolated fixture data; production annotations were not changed. The real
inference test saved only a model result for VOD30 frame 2100.

### Backend and timing

The local VOD timeline uses frame indices as the inspection identity. Timestamps
are nominal `frame_index / fps` values, not a guarantee of exact variable-frame-rate
presentation timestamps. `GET /api/video?dataset=vod30` exposes metadata;
`GET /api/frame?dataset=vod30&frame=2100` returns the selected decoded JPEG.

Inference is one asynchronous job at a time: table/person by default, SAM3 balls
only when explicitly selected because CPU inference can be slow. Results live in
`out/{scan30|scan_highlight}/frame_results/{frame_index}/inference.json`.
Corrections live separately in `correction.json`; they never overwrite model
outputs. These are raw-pixel boxes and table polygons, not validated identities.

Real inference smoke checks on VOD30 frame 2100 (~70 seconds) returned a table
polygon, three person detections and eight ball detections. These counts establish
execution only, not accuracy. The optional Ultralytics settings write outside the
workspace was denied; person inference still completed. No workaround was used.
The full backend suite now has 21 passing tests, including frame bounds/decoding,
async errors/busy behavior, corrections and the reused ball helper contract.

Twitch embedding/ingestion, live DVR buffering, and temporal shot/pot inference
are not implemented. The timeline operates on the two existing local VODs.

## Verification

- 14 isolated backend unit tests pass: dataset isolation, legacy label keys,
  annotation merge, finite/bounded anchors, atomic failure behavior, media/path
  containment, static assets, byte ranges, explicit seeds, stale outputs,
  raw event frames and rebuild failure/unknown behavior.
- `node --check annotator/app.js` and `git diff --check` pass.
- Real browser: all four modes loaded; real crop/context images loaded; missing
  evidence fallback decoded successfully on both VOD datasets.
- Isolated browser fixture: saved verdict/shooter/note survived reload; unknown
  and clear ball writes succeeded; anchor nudge/save succeeded; explicit player
  seed saved; rebuild without B completed with unknown outputs. No production
  human labels were changed by these checks.
- Mobile viewport 390×844: document width 390, no horizontal overflow. Screenshots
  in `out/corner-pocket-desktop.png` and `out/corner-pocket-mobile.png`.

Reproduce isolated write checks with
`.venv/bin/python tests/serve_workbench_fixture.py` at port 8131. It resets a
scratch workspace under `out/ui-browser-fixture/`, never production labels.

## Limits, not implied certifications

Pocket saves record annotations, not a fitted calibration. Full seeded OSNet
rebuild with both identities has not been browser-validated; missing-seed and
failure handling have been tested. Identity propagation covers existing sampled
tracklets, not continuous all-frame recognition or automatic shooter retraining.

Highlight event results used the wrong calibration previously and are not valid
accuracy evidence. Candidate-only reviews cannot measure recall. Independent
missed-event truth and full VOD precision/recall remain future pipeline work.
Ball-ID ≥90% certification remains backlog. This release integrates existing
correction workflows; it does not invent missing labels or certify predictions.
