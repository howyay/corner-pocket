# Product
<!-- impeccable:product-schema 1 -->

> **Corner Pocket.** Written 2026-09-25 for the `impeccable-polish` worktree from the repository sources and the PM director's brief. Status truth is `docs/handoff.md`. Other sources: `docs/vision-redesign-outline.md`, `docs/corner-pocket-operations.md`, `docs/corner-pocket-functional-inventory.md`, `docs/unified-workbench.md`, `README.md` and `annotator/ops.js`. The owner interview that Impeccable `init` calls for has not happened. Every fact below comes from those sources, the docs and commits they cite, or the director's brief, and anything undecided is marked **OPEN:**.

## Platform

web

## Users

- **Floor staff** at the club on a tournament night, while matches are being played. Their job is to run the night: register regulars and guests, rack the draw, send ready matches to free tables, keep score, run the shot clock, mark a side *Not here* or *Here now*, and sign scorecards.
- **The operator** reviews what the camera pipeline produced and corrects it. They give each machine-produced event candidate (shot or pot) a verdict, a shooter and a note. They fix model overlays (table quad and cloth polygon, balls, person boxes), label ball crops, place the six calibration anchors, and bind a person track to one regular or one guest name. Today the owner does this review: commit `876e0a0` says the candidates "are served because the owner reviews them". Cloudflare Access admits one identity (`docs/unified-workbench.md` §Hosted access).
- **Data subjects, not users:** regulars (roster records, with an optional face-enrolment photo) and guests. Their notes and match history are private operational data.
- **OPEN:** whether floor staff get their own Access identities, and what the operator access and concurrency policy is (functional inventory §10).
- **OPEN:** which devices floor staff use: the club machine only, or phones at the table as well. A 390 px layout exists (the Vision bottom sheet), but no source says who uses it.

## Product Purpose

Corner Pocket is one pool hall's own operations app and video-review workbench. Both ship from one repo and are served by one process on the club machine.

- **Operations** (Floor, Set up, Matches, Regulars, Back room) runs a club night on real, persisted, server-validated state. Scoring is manual, results are signed explicitly, history is archived rather than destroyed, and nothing is simulated.
- **Vision** works from one fixed overhead camera on the club's Rasson Victory III 9 ft table (Twitch channel `examplechannel`). Its goal (`README.md`) is to build a calibrated top-down recreation in physical millimetres, detect shots and pots, and attribute each one to the player who made it. Attribution is not built yet (see *Not built*). A human sees every machine claim before it counts.

Success means:

- A whole night runs on Corner Pocket with nothing fabricated. Staff enter every score and sign every result explicitly, and a result cannot change once it is complete.
- Every shot or pot on screen is either confirmed by a human or visibly marked as machine-produced and unconfirmed. Accuracy is only quoted against independent truth.
- The operator gets from a candidate to a saved verdict without leaving the stage.
- The pipeline keeps real time on the club machine (the bar is 30 fps end to end; see OPEN below).

## Positioning

Corner Pocket reports exactly what it measured, on this club's own camera, footage and machine, and nothing more. A neighbouring product could not truthfully make the same claim, because it rests on a mechanism, not a tone:

- One fixed camera is mapped to a physical table model (1270 × 2540 mm; ball 57.15 mm) through hand-placed anchors, and those anchors are the authoritative mapping.
- A small trained ball detector runs locally on the club's GPU.
- Claims it cannot prove are refused. The owner once emptied the whole event queue because every candidate measured as occlusion (commit `0e61a4b`), and the UI said why in place.
- Every overlay and every candidate carries its provenance. A human verdict is the only thing that confirms an event.

Corner Pocket is not an auto-referee and must never read as one. The Back room states *Live observations / auto-referee: Not connected*.

## Operating Context

- **Serving.** The `pool-workbench.service` systemd user unit runs `annotator/unified_server.py` on `http://127.0.0.1:8130/`, bound to loopback only. Remote access goes through `https://pool.example.com` over a Cloudflare Tunnel. The whole hostname, including API and media routes, sits behind Cloudflare Access (Pocket ID SSO, one allowed address, 168 h sessions, no bypass).
- **Entry points.** `/` is the operations shell (`annotator/ops.html` + `ops.js`, six tabs). `/app.html` is the older review workbench, kept as a compatibility entry while the native Vision tab is being verified.
- **Offline.** The club machine must run the app with no internet: no CDN fonts, scripts or assets. Two features need the network: Twitch playback and chat (the embed's `parent` must be the real hostname), and the Twitch VOD replay source. When they are unreachable they must say so, and nothing else may break.
- **State.** `annotator/operations.py` owns `out/corner-pocket/state.json`.
  - Writes are revisioned. A stale revision returns HTTP 409: reload and review, never replay silently.
  - An invalid action returns HTTP 400 and changes nothing.
  - Replacement is atomic, only one server process may use a state directory, and audit events are kept (newest 500).
  - Vision reads and writes per-dataset JSON under `out/` (`out/scan30/events.json`, `out/scan30/annotations.json`, …).
  - Every `GET` is side-effect free. The one exception is `GET /api/clip`, which caches a regenerable fragment in `out/clip-cache/`.
- **Footage** (in the production checkout's gitignored `data/`):
  - `vod30` is `data/vod_30min_260815.mp4`, a 30-minute slice of the Aug-15 stream (1280×720, 30 fps).
  - The highlight is `data/vod_highlight.mp4` (377 s).
  - By owner decision, the live input is a Twitch VOD of `examplechannel` replayed in real time, because the live broadcast path is blocked externally (`docs/twitch-vod-as-live.md`).
- **Compute.** A ROCm GPU on the club machine runs the tiny ball net. SAM3 is an offline labeller (the detector's teacher) and is not in the runtime path.
- **The night.** Set up → Registration desk → *Rack the night* (single elimination, automatic byes, the draw seeded in sign-up order, entrants and rules locked) → send to table → score and clock → *Sign scorecard* → winners advance → *Archive & new event*.
- **Production vs polish.** `/home/operator/projects/pool/` is the live checkout. Production serves its `annotator/`, and its `out/` and `data/` hold the real state and footage. Polish work never edits it.
  - Work happens in the `impeccable-polish` worktree and is checked against two fixture servers: `tests/serve_workbench_fixture.py` (:8131; the real VOD plus copied review data) and `tests/serve_operations_fixture.py` (:8132; an empty club).
  - The test suites are `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`, `node --test tests/test_ops.js` and `node tests/test_app_timeline.js`.

## Capabilities and Constraints

### The six tabs

The hierarchy is binding (`docs/corner-pocket-operations.md`). Every tab shares a header with the EN / 中 language toggle, the dark / light theme toggle and a connection badge (`LOCAL · SAVED` or `UNAVAILABLE`). Every tab except Floor also carries the shot clock and a current-score button that returns to Floor.

| # | Tab (EN / 中 · id) | What it does today |
|---|---|---|
| 1 | Floor / 球房 · `floor` | Shows the focused match: table, race, score (±, or *Win frame* for single-frame matches). Holds the shot clock (20 / 30 / 45 / 60 s), *Not here* / *Here now*, *Clear score*, release table and *Sign scorecard*, plus the up-next queue, tables open and tonight's counts. |
| 2 | Set up / 开赛设置 · `setup` | *The night*: event name, singles or doubles, race to 1 / 3 / 5 / 7 / 9 / 11, and tables. *Registration desk*: add a regular or a guest, with a partner for doubles. *Rack the night* locks entrants and rules; *Archive & new event* starts over. |
| 3 | Matches / 对阵 · `matches` | *Scorekeeper's card* (side A and side B scores, save, sign), send to table, *House standings*, *Night log* and archived events. |
| 4 | Vision / 视觉 · `vision` | One stage, two rails, zero subtabs: a source chip row; the *Cues* rail (event candidates, ball-label queue, person tracks); a 16:9 stage with layer chips; the *Inspector* (verdict, shooter and note; identity; anchors); and a scrub strip carrying the single facts line. There is no landing screen. |
| 5 | Regulars / 常客 · `players` | A searchable roster (Active / Visitor / Newcomer / Inactive). Profiles show a staff-entered rating (0–1000) and a win/loss record from recorded results. Includes face enrolment from a photo and *Guests tonight* → *Add to regulars*. |
| 6 | Back room / 后台 · `status` | Appearance (language, theme), a readiness table stating what is and is not connected, the roadmap and operator notes. |

### Vision today (`docs/handoff.md` §1, `docs/vision-verification.md`, commits `876e0a0` and `bc86f26`)

- **Overlay provenance** is shown in place:
  - `MODEL` / `模型`: dashed.
  - `YOURS` / `人工`: solid, with grab handles.
  - `CALIB` / `标定`: pockets projected from the saved anchors.

  Saving a correction writes YOURS, never the model's boxes.
- **Candidates** carry `provenance` (`machine_produced`, `human_confirmed`), a gate status (confirmed / rejected / unconfirmed · 已确证 / 已否决 / 未确证), and the evidence they measured, in its own units. An unconfirmed machine candidate says so in words: *machine-produced candidate; no human has confirmed it* / *机器产出，未经人工确认*.
- **Verdicts** are correct / wrong / unsure (正确 / 错误 / 不确定), plus a shooter and a note.
- **Refusals reach the operator, with numbers.** For example: `quad drift vs saved corners 6.4 px (tol 40 px)`. Three refusals are surfaced, never silent: a refused table quad, a correction that belongs to another (dataset, frame, size), and a model quad that fails the sanity check. An empty queue says why it is empty.
- **Identity.** A person track is bound to one regular (*Which regular?*), one guest name, or *Ignore (not a player)*. Guest names are stored but never trained on.
- **Calibration.** Six anchors (TL / TR / BR / BL / left side / right side), on `vod30` only. Saving anchors records an annotation; it does not refit the pipeline calibration.
- **Source panel** (opened from the *Source* chip): datasets, live start/stop, detector toggles, saved channels, the Twitch URL form, and the Twitch VOD replay (*a replay, never a live broadcast* / *回放，绝不是直播*). Latency is stated as local processing latency, not glass-to-glass.
- **Keyboard:** Space plays or freezes and ← / → step ±1 frame. Both were verified in a browser with no double handling by the native `<video>` element. Shift+← / → steps ±10 (in `annotator/app.js`).

### Technical constraints

- **Stack.** Plain HTML/CSS/JS served as static files by a Python stdlib server (`http.server`). No frontend framework, no build step, and no new frontend dependencies. `annotator/app.js` stays the single stage engine, with its dirty / busy / frame-token guards; never write a second one.
- **Navigation.** Moving between tabs must preserve unsaved edits, in-flight saves, frame-request guards and keyboard focus. Visual parity alone does not count as done.
- **Offline assets.** Served pages must not fetch fonts or assets from a CDN. Met on `impeccable-polish` (`82db63f`, `534d4ac`): fonts are self-hosted under `annotator/fonts/` (OFL texts alongside), 0 third-party requests on a cold load; the CJK faces are subset to the app copy plus the 3,500 common hanzi, fetched only when a page shows one.
- **Tournament safety.**
  - Never generate random winners.
  - Reaching the race target does not finalise a match; staff complete it explicitly.
  - A completed result cannot change.
  - Absence releases the table.
  - Starting a new tournament archives the previous one.
- **Sources.** Only Twitch channel and video URLs are accepted, and the server never fetches arbitrary pasted URLs. An embed is not ingestion, not inference, and not proof that a channel is live. Single-frame inference cannot establish shots, pots or accuracy.
- **Privacy.** Audit events copy neither private note bodies nor source URLs, and never invent actor identities. The face model runs on this machine only.

### Terminology

- **Regular (常客):** a registered club member, i.e. a roster record. **Guest (访客):** an entrant without a profile, who can be promoted to a regular. The `Prospect` status displays as *Newcomer / 新会员*.
- **Person track / identity:** a video-track annotation. It is not a regular until the operator binds it, and the two are never silently conflated. Legacy A / B labels are not registered identities.
- **Candidate:** a machine-produced shot or pot awaiting a verdict. It is not an event anyone has confirmed.
- **Gate status** (confirmed / rejected / unconfirmed): the detection gate's machine verdict on a candidate. A gate-`confirmed` candidate is still machine-produced and still needs a human verdict. Only a human verdict makes it `human_confirmed`.
- **Stored inference (已存推理):** a file written by an earlier run, with its timestamp. Nothing else.
- **Replay (回放) vs live:** a Twitch VOD replay is never called live. A Twitch channel is labelled *LIVE STATUS UNVERIFIED* (直播状态未核验); a Twitch video is labelled *RECORDED VIDEO* (录制视频).
- **Facts line:** the one status line under the stage. Every number is printed there, derived from what is drawn.
- **Shot clock:** *local timer, not shared* (本机计时，不联动). It runs in one browser, survives a refresh, imposes no penalty and updates no other device.

### Not built: never present these as done

- Live observations or auto-refereeing (not connected).
- Live broadcast input. It is unreachable from this machine (usher returns `404 Can not find channel`, and Twitch requires a client-integrity token), so live end to end is unproven.
- Automatic shot-to-player attribution. Identity propagation covers sampled tracklets only, and face binding cannot fire while the roster is empty.
- Ball identity (numbers) at ≥90 % accuracy (backlog).
- Online sign-ups: a roadmap item (P1), not built.
- Authentication and authorisation beyond Cloudflare Access, payments and booking: neither implemented nor designed (functional inventory §10).

### Open

- **OPEN:** shot clock scope. The UI clock is device-local (the Floor says "local timer, not shared"). `main` added a server-authoritative shared clock module (`annotator/shot_clock.py`, tested), but no route or UI uses it yet, so for staff the clock is still per device.
- **OPEN:** correcting a signed result. Completed results cannot change, and the correction/undo policy (roadmap: *result undo trail*, P1) is not designed.
- **OPEN:** real time. 28.0 fps end to end has been measured with the trained net, against a 30 fps bar; the re-measurement is not final.
- **OPEN:** live broadcast. Whether and when a real live path returns is undecided; until then, Twitch VOD replay is the live input.
- **OPEN:** retiring `/app.html` after native Vision integration is verified.

## Brand Commitments

- **Name:** Corner Pocket. **Tagline:** POOL HALL OPERATIONS / 球房运营台. **Mark:** the 8-ball in the header; favicons are in `annotator/favicon*`.
- **Tab names and order are binding:** Floor · Set up · Matches · Vision · Regulars · Back room.
- **Voice.** The club side speaks pool-hall vernacular: *The night*, *Rack the night*, *Registration desk*, *Sign scorecard*, *Here now* / *Not here*, *House standings*, *Night log*, *Back room*. The machine side speaks in plain measured statements: units, tolerances, counts and reasons.
  - No marketing, and no reassurance without evidence.
  - A pending write never shows a success word.
  - An empty list says why it is empty.
  - Absent data reads *Not measured* / *尚未采集*.
- **Bilingual.** Every string ships in English and Simplified Chinese.
- **Visual reference.** The owner supplied `Corner Pocket redesign (1).zip` (its *Corner Pocket Ops* standalone HTML), kept at `/home/operator/projects/pool/design/corner-pocket/` (gitignored; not in this worktree). DESIGN.md records the incumbent visual system; this file does not.

## Evidence on Hand

- **Footage:** the two VODs above, and the club's channel `examplechannel` (one archived broadcast).
- **Detector** (`docs/handoff.md` §3.1):
  - F1 0.927 at 960×540 (P 0.940, R 0.914), 1.48 px median localisation, on a frozen 47-frame held-out set.
  - This measures fidelity to its SAM3 teacher, not ground truth, and its 15 false positives are unreviewed.
  - 28.0 fps end to end.
- **Calibration** (`docs/handoff.md` §3.5): the hand anchors are the authoritative mapping, and `vod30` is one calibration segment. The highlight has no hand anchors, and its saved corners put the bottom rail 28.2 px inside the cloth. The only fix is the owner clicking its six anchors (about 10 minutes).
- **Review data:** `out/scan30/annotations.json` holds one verdict (event 16 = unsure). The served queue holds machine-produced dense-track candidates, none of them human-confirmed as of 2026-09-25.
- **Design research:** `docs/vision-audit.md`, `docs/vision-redesign-outline.md`, `docs/vision-verification.md` and `docs/corner-pocket-functional-inventory.md`. The mockup and screenshots are in the production checkout's `out/vision-redesign/`.
- **Absences future work must not fabricate:**
  - human-validated shots or pots;
  - precision or recall against independent truth;
  - player statistics beyond recorded results;
  - regulars (the roster has 0) or face photos;
  - a live broadcast;
  - customers, testimonials, pricing or other clubs.

  The prototype fixtures (Maya Chen … Zoe Kim, sample matches, the synthetic ball canvas) are demo and test data only, never production content.

## Product Principles

1. **Claim only what is proven.** Provenance is always labelled (model vs human), machine candidates say they are unconfirmed, a replay is never called live, an embed is not proof of liveness, unmeasured means *Not measured*, and production never shows simulated data.
2. **Refusals and failures explain themselves where they happen.** The reason, with its numbers, appears in the place that owns the action, never in a distant toast that clears itself. An empty state says why it is empty.
3. **The human decision is the record.** Machine output stays a candidate until the operator decides. Saves write only the operator's corrections. Staff sign results explicitly, and signed results cannot change. Stale writes are rejected, never replayed silently.
4. **One truth per fact.** Each fact comes from one state and is printed in one place: the facts line is derived from what is drawn, one clock state is shown in every view, and one moment never appears as two disagreeing copies.
5. **The night never waits on the camera.** Club operations work fully without the vision pipeline and without the internet: manual, validated scoring on the club machine.

## Accessibility & Inclusion

- **Language.** Full EN / 简体中文 parity: validation, empty states, status chips, accessible names, toasts and external-service notices. The toggle updates the document language. In Vision, 中 mode was verified to leave no Latin state words behind (`docs/vision-verification.md`).
- **Theme.** Dark and light, defaulting to EN and dark. Language, theme and the shot clock persist in `localStorage` (`cp-ops-lang`, `cp-ops-theme`, `cp-ops-clock`).
- **Keyboard and assistive tech** (required by the functional inventory §1): visible focus states, labelled inputs and ± controls, accessible names on canvas and iframe elements, and `role=status` / `aria-live=polite` feedback. Vision review is designed keyboard-first.
- **Motion.** `prefers-reduced-motion` is honoured (`annotator/ops.css`, `annotator/app.css`).
- **Narrow viewports.** Layouts have been exercised down to 390 px. Below 1100 px, Vision's rails become a bottom sheet (Cues / Inspector tabs) under the 16:9 stage.
- **OPEN:** no formal conformance target (for example WCAG 2.2 AA) has been chosen.
