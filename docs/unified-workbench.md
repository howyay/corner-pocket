# Corner Pocket unified workbench

Run `.venv/bin/python annotator/unified_server.py --port 8130`, then open
http://127.0.0.1:8130. The origin binds only to loopback; external access must
remain behind Cloudflare Access.

## Hosted access

https://<site> uses the existing `<tunnel>` Cloudflare Tunnel:
`<site>` → `http://127.0.0.1:8130`. Proxied CNAME points to
`<tunnel-id>.cfargotunnel.com`.

Cloudflare Access application `Corner Pocket` protects the entire hostname,
including API/media routes. Pocket ID SSO is the only enabled identity provider;
allow policy is restricted to the owner's address, matching the existing Kaneo SSO
setup. Session duration: 168 hours. There is no public bypass policy.

Origin runs as the workbench service, an enabled user service, with restart on
failure and user lingering enabled. Unit:
`~/.config/systemd/user/<workbench-service>`.
Manage with `systemctl --user {status,restart,stop} <workbench-service>`.

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

### The nominal timeline, measured (2026-09-23)

`src/timing_verify.py` measures the timestamp axis directly, because the owner
reported that no served event lined up with ball movement. On `vod30` the
nominal contract above is not merely nominal: **`frame_index / fps` equals the
container PTS within 1.6 ms at every one of 31 samples across 1806 s**, and the
app's frame path (`frame_index = round(t * fps)`) and the stage's seek path
(`video.currentTime = t`) decode the *identical* picture (SSIM 1.000, 0 frames
apart) at 60 s, 300 s, 900 s, 1700 s and at every event window start. The clip
we show is the moment the detector measured; no seek mapping needs to change.

What the served timestamps *do* contain is motion that is not a ball. For all 15
served events the cloth changes by 10.6-55.8 gray levels (mean) over 15-77 % of
its pixels inside `[t-1.5, t+2.5]` - and 10-76 % of the cloth sits in single
change blobs of 3000 px or more. A ball on this table is 2.5-4.5 px in radius at
the 960x540 working size, so a struck ball changes 0.05-0.2 % of the 73 227-px
cloth: the measured footprints are 100-1000x too large to be one. Contact sheets
at 82.5 s, 483.4 s and 1081.6 s show why - a person crosses or stands in front
of the camera at the served instant, occluding the cloth.

Two consequences worth remembering. First, the cloth-mean absolute difference
prescribed for this check cannot answer "did the ball move": a ball contributes
~0.05-0.2 % of the cloth mean, which is below this stream's still-cloth noise.
Second, the scan's own per-second trigger signal (`out/scan30/records.json`
`motion`) is elevated at the served times (up to 73.9 against a p50 of 4.8), so
the detector fired on a real change at the right moment - the trigger's *content*
is occlusion, not the timestamp. Rejecting occlusion at the candidate stage is
the open fix; it needs a re-scan and has not been made.

Reproduce with
`.venv/bin/python -m src.timing_verify --control-count 12 --drift-step 60`
(~16 s; writes `out/scan30/timing_verify.json`). Tests:
`tests/test_timing_verify.py` pins the two-timebase equality, the app/tool
window-constant parity, the nominal convention in both producers, and that a
noisy control floor yields "not separable" rather than a false negative.

Twitch embedding/ingestion, live DVR buffering, and temporal shot/pot inference
are not implemented. The timeline operates on the two existing local VODs.

## API write contract

Every `GET` is side-effect free: it reads state and renders it, but it never
rewrites a persisted file. The check is bytes + size + mtime, e.g. `md5sum
out/identity/clusters.json` before and after a read.

- Fixed 2026-09-23: `GET /api/identity/frame` and `GET /api/unified` rewrote
  `out/identity/clusters.json` on every observed frame, because
  `IdentityIndex.register()` saved the whole index after each tracker update
  (`src/person_identity.py`, the `process_frame -> update -> register` seam). A
  tracker update is observation, not a decision: reads now change memory only,
  and the file is written by `bind_face()` / `explicit_assign()` — where the
  durable binding is actually made, and which persist everything accumulated
  since the last write — or by an explicit `save()`.
- `GET /api/clip` still writes one thing: a regenerable fragment under
  `out/clip-cache/`, only on a cache miss, keyed by dataset + window, never
  rewriting an existing file (it prunes its own directory). That is derived
  media, not state, so it stays a cache on purpose.
- Reads audited as write-free: `/api/operations`, `/api/vod30/{seeds,tracklets,
  tracks,anchors,rebuild}`, `/api/events`, `/api/frame`, `/api/frame-result`,
  `/api/inference` (status), `/api/datasets`, `/api/balls/<set>/meta`,
  `/api/identity/status`, `/api/live` and `/api/live/frame`,
  `/api/review-template`, `/media/*`, static assets. Writes live in the POST
  handlers (`annotate`, `seeds`, `anchors`, `frame-correction`,
  `identity/{seed,unbind,enroll,enroll-confirm,forget}`, and the inference job
  the POST starts).
- Fixed 2026-09-25: a face match inside `GET /api/unified` /
  `GET /api/identity/frame` called `bind_face()`, which saved the index. The
  pipeline now binds with `persist=False`: the bind is in the payload and in
  memory, and the next genuine mutation (seed, unbind, forget, an enrolment)
  writes it (`1255cc1`).
- `POST /api/identity/forget {"player_id": "…"}` — per-person delete of face
  data, on the operator's explicit request (no auto-expiry). Under the identity
  lock it removes every row of that player from
  `out/corner-pocket/face_embeddings.json` (and from the enrolment scratch copy
  under `out/enroll-eval/scratch/`), unbinds the player's clusters in
  `out/identity/clusters.json` and drops their stored `face` and `face_samples`
  (the 128-d body bank is not a face and stays), and makes the running pipeline
  re-read the gallery, so the player is not auto-bound again. The operations
  record (name, results, events) is not touched. Returns
  `{"forgotten": true, "player_id", "removed": {"store_faces", "scratch_faces",
  "clusters_unbound", "face_samples", "faces"}}`; `400` without a `player_id`,
  `404` (nothing written) when the player has no face data anywhere.
- Fixture measurement (`tests/serve_workbench_fixture.py`, :8131). Before: one
  `GET /api/identity/frame?dataset=vod30&frame=2040` moved the index from md5
  `77777777777777777777777777777777…` / 1,855,684 B / 20:43:21 to `77777777777777777777777777777777…` / 1,865,607 B / 20:58:05.
  After: the same read, `GET /api/vod30/tracklets` and a full read-only page load
  (Vision tab, track selection, `GET /api/unified?dataset=vod30&frame=0`) left
  `77777777777777777777777777777777…` / 1,865,607 B / 20:58:05 untouched. `GET /api/vod30/tracks` was
  byte-identical before and after (`77777777777777777777777777777777…`, 205 B).

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
