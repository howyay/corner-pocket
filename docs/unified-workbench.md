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
- Shared shot clock (`annotator/shot_clock.py`, 2026-09-27): `POST /api/clock`
  `{"action": "start"|"pause"|"reset"|"set", "duration": 5-300 with set only}`
  is the only write, to `out/corner-pocket/clock.json` (atomic replace), and only
  on a real change - a Start while running or a Pause while paused returns the
  state unchanged and writes nothing. It is not part of the revisioned
  operations state, so it never makes an operator's `/api/operations` write
  stale. `GET /api/clock` (state + `server_now_ms`) and the Server-Sent Events
  stream `GET /api/clock/stream` (one `clock` event per change, a heartbeat
  every 15 s) never write: an expired clock is reported as `running: false,
  remaining_ms: 0, expired: true` and nothing is persisted. Tested with md5 +
  size + mtime across 40 expired reads (`tests/test_clock_api.py`). The stream
  is the one response that outlives its request on purpose, so it is served from
  its own budget — see **Connection budget** below.
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

## Connection budget (2026-10-02)

One listener serves the console, and the console must not be what spends that
listener's ceiling. `BoundedHTTPServer` (`annotator/unified_server.py`) counts
two budgets apart, each read once at construction:

- `max_handlers = 64` — connections being served as requests. Over the ceiling,
  the connection is answered `HTTP/1.0 503` + `Retry-After: 5` and closed
  immediately: there is no queue, and `request_queue_size` stays 64.
- `max_streams = 256` — responses that outlive their request on purpose. One
  path is admitted today, `GET /api/clock/stream`: the handler calls
  `begin_stream()` before its first event, which gives the request slot back and
  takes a stream slot instead. A full stream budget is refused the same way —
  `503 {"error":"unavailable"}` + `Retry-After: 5`, no queueing — and the
  console's `EventSource` falls back to polling (`annotator/clock-sync.js`).
  Closing the tab, or any failed heartbeat write, returns the stream slot.

Why split at all: a clock stream is held for as long as its tab is open, and its
15 s heartbeat is exactly what keeps `Handler.timeout = 60` from ever firing, so
it never frees a slot by itself. Before the split, a night of open consoles
spent the slots an ordinary `GET /api/operations` needs and the console answered
itself with 503. A stream costs a thread and a socket, not an API call, which is
why its own ceiling is the larger one. `server.pool_state()` reports the two
counters (`{"requests": n, "streams": m}`) and nothing else.

Measured on an ephemeral loopback port (`tests/test_connection_budget.py`, plus a
throwaway probe): 80 streams open at once — above the 64-connection ceiling — all
answered `200`, all carried a `clock` first event, `ss -ltn` reported
`LISTEN 0 64`, `ss -tn` 160 established sockets (both ends of 80 connections),
the counters read `{"requests": 0, "streams": 80}`, and `GET /api/operations`
returned `200` in 0.9 ms / 0.6 ms / 0.6 ms. After every tab closed: counters
`{"requests": 0, "streams": 0}`, no sockets left. Run against the previous code,
the same suite reports `[503 × 16] != []` for the 80 streams and `503 != 200` for
an ordinary call placed behind four streams under a four-slot ceiling.

Not claimed: a long media response (`/media/*`, VOD playback, byte ranges) is
still served as a request. A client that stops reading it is dropped by the 60 s
socket timeout, and playback is bounded by whoever is watching, so it was not
moved into the stream budget. The kernel's accept backlog is untouched: the fix
is in which budget a connection is counted against, not in how many are queued.

## Imported broadcasts (VOD selector)

Any past broadcast of a **saved channel** can be imported and browsed like
`vod30`: scrub, step, freeze, see the per-frame detections, run the frozen-frame
inference job and save corrections. A VOD of any other channel is refused before
a playback token is requested: "This VOD belongs to <channel>. Only saved
channels can be analysed; add the channel under Source first." Imported VODs
are not scanned for events (`/api/<id>/events` answers `{"events": [],
"annotations": {}, "analysed": false}`), and the vod30-only features (saved
anchors, seeds, tracklets) keep answering `404 feature only available for
vod30`. The table prior has no saved anchors, so the naive `no_seed` fallback
and its facts-line wording apply.

Where things live (all gitignored; `git check-ignore -v data/vods/x.mp4` →
`.gitignore:9:data/`):

- `src/datasets.py` is the one registry: `vod30` and `highlight` unchanged, plus
  the entries of `out/vods/index.json`. Ids are `tw-<vod>` (whole) or
  `tw-<vod>-<start_s>-<end_s>`, built from numbers only.
- `data/vods/<id>.mp4` is the media (written as `<id>.mp4.part`, renamed when
  complete). `out/vods/<id>/` holds operator data, e.g.
  `frame_results/<n>/correction.json`.
- `out/vods/index.json` holds channel, title, dates, range, fps, decodable frame
  count, size and import time. It never holds the playback token, its signature
  or the media URL.

Endpoints (reads never write; writes go through the same same-origin check,
64 KB body limit and error bodies as every other POST):

- `GET /api/vods/recent`: up to 10 recent broadcasts per saved channel, cached
  in memory for 3 minutes; a Twitch failure is that channel's `error` with
  `vods: null`, never an empty list.
- `GET /api/vods/estimate?vod=<id|url>&start_s=&duration_s=`: size from the
  variant's BANDWIDTH × duration, the free-disk check, and an ETA from the last
  import's measured rate.
- `GET /api/vods/job`: `state` (`idle|running|done|error|cancelled`), `percent`,
  `done_s`/`total_s` (from ffmpeg's `out_time`), `mb`, `rate_mb_s`, `eta_s`,
  and the honest `error` text.
- `POST /api/vods/import {vod, start_s?, duration_s?}`: one import at a time
  (a second one is `409`). Refused with the numbers (`507`) unless free space ≥
  estimate × 1.2 + 2 GB. ffmpeg runs without a shell, with
  `-protocol_whitelist file,http,https,tcp,tls,crypto` (security audit B-6),
  `-c copy -bsf:a aac_adtstoasc -movflags +faststart`. A stale `.part` of the
  same id is removed when the import starts.
- `POST /api/vods/cancel {confirm: true}`: stops ffmpeg and removes the `.part`;
  the index is untouched. Stopping the server does the same.
- `POST /api/vods/delete {id, confirm: true}`: removes the media and the index
  entry. **Operator corrections under `out/vods/<id>/` are kept**, and the
  response says how many files were kept. To remove those too, delete the folder
  by hand.

A range is cut by stream copy, which keeps the pre-roll from the keyframe before
`start_s`; the MP4 edit list hides it, so frame 0 is exactly `start_s` (pixel
match against Twitch at 3600 s and 3610 s: mse 0.0). The container still counts
the hidden samples (9193 listed, 9002 decodable on a 5-minute range), so the
import records the decodable count and the server uses it for imported VODs.

Measured 2026-09-28 on the scratch fixture (`tests/serve_vod_fixture.py`,
:8217), VOD 1000000001 (examplechannel, 3.7 h, 720p30), 1:00:00–1:05:00: 9.9 s
wall, 121.7 MB (estimated 123.3 MB), 12.4 MB/s, 9002 frames. The whole VOD
would be about 5.5 GB and about 7.4 minutes at that rate.

**Postgres:** migration `0004_imported_datasets.sql` replaced the `dataset IN
('vod30','highlight')` checks with the registry's id format (`dataset_id_ok`,
the rule of `src.datasets.parse_imported_id`) on every dataset column, and
`PostgresStore` validates a dataset with `src.datasets.lookup`, as the JSON
store does: a correction or verdict on an imported VOD is kept under either
store, and one on an id the index does not list is refused by both. Its
records are `json_documents` rows named after the files the JSON store writes
(`out/vods/<id>/frame_results/<n>/correction.json`,
`out/vods/<id>/annotations.json`), so the export writes them back byte for
byte. `out/vods/index.json` itself is catalogue data and stays a file.

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
