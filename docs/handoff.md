# Corner Pocket — handoff

## Where things stand (2026-09-22)

The repository now contains a complete Corner Pocket club-operations application plus a rebuilt computer-vision pipeline. Everything runs locally at `http://127.0.0.1:8130/` behind Cloudflare Access (deployed), with the app code serving from disk. **The service is RUNNING** on port 8130 and verified: app root, favicon, operations API, live API, and VOD metadata all return 200; public URLs still redirect to Cloudflare Access (302). Restart any time with `systemctl --user restart pool-workbench.service`.

## What exists

### 1. Club operations app (`annotator/ops.html`, `ops.js`, `ops.css`, `operations.py`)
Single-page app, six top-level tabs — **Floor · Set up · Matches · Vision · Regulars · Back room** — all with persistent state in `out/corner-pocket/state.json`. The flow runs through the single page at `/` — `unified_server.py:957-958` serves `ops.html` there, and the shell mounts the review template (`/api/review-template` → `annotator/app.html`) into `#review-root` when Vision is opened. `/app.html` and `/ops.html` are **308 redirects to `/`** (`unified_server.py:928-929`), kept only as compatibility entries.

- **Tournament engine** (`annotator/operations.py`): singles/doubles, byes, scheduling, table assignment/release, scoring, signed results, forfeits, absences propagated through rounds, guest→regular promotion, archive/history. Optimistic concurrency (`revision`, HTTP 409 on stale writes). Bounded audit `events[]` (500 newest).
- **Player identity** (`src/face_id.py`, `src/person_identity.py`, `src/person_pipeline.py`): ArcFace (insightface `buffalo_l`) enrollment per regular, YOLOv8n person detection → vendored OSNet x0.25 re-ID → persistent clusters. Face binding fires once (threshold 0.35 cosine, margin 0.12 over runner-up, quality gate: eye distance ≥ 8 px, det score ≥ 0.4). Explicit A/B/ignore seeds override everything. Body re-ID clustering is **disabled by default** (measured: same-person p05 0.755 vs cross-person p95 0.882 — not separable; see calibration constants in `src/person_identity.py`).
- **UI/UX decisions applied**: event name auto-generated from date + weekday, race default 1, Visitor/Inactive removed from creation flow, Regulars edit is a modal opened by a + icon, tab kicker/title blocks removed, footer removed, date formatting, brass control accents.

### 2. Vision = one stage, two rails, zero subtabs
Vision is a single surface, not a set of modes: a **source chip row**, then `[Cues rail ~280 px | Stage 16:9 | Inspector ~320 px]`, then a **scrub strip** that carries the single facts line. The rails hold the queues, the stage holds the evidence, the inspector holds the decision. `.vs-grid` is `280px minmax(0,1fr) 320px` and `.vs-frame` is `aspect-ratio:16/9` (`annotator/ops.css:212,221`). There is no sub-tab navigation and no landing screen. Design and rationale: `docs/vision-redesign-outline.md`; the audit it answers: `docs/vision-audit.md`.

The stage renders exactly **one frame surface** — the live edge OR a VOD frame, never two copies of the same moment. Overlays are layer chips (Cloth · Balls · Persons · Pockets · Anchors · Events) drawn in the frame's own coordinate system and dragged directly on the imagery. Old sub-tab → new home:

| Old sub-tab | New home |
|---|---|
| Stream / sources | source chip row + Source inspector (chat docks in the inspector) |
| Event review | cues rail + inspector verdict block |
| Ball labels | click / label on the stage, `0–9` / `U` / `C` keys |
| Table calibration | Anchors layer — the six anchors dragged on the stage (gated to `vod30`) |
| Player identities | person boxes on the stage |
| Video timeline | the scrub strip (frame index, ±1, freeze, event ticks, live-edge marker) |
| Twitch embed | the stage itself when the source is live |

**Engine.** `annotator/app.js` remains the single stage engine and still owns the verified write guards (`state.dirty`, `state.busy`, frame-token). `annotator/vision-stage.js` is a thin adapter — no fetch and no frame state of its own: it renders the chip row, rails, chips, inspector and facts line from the engine snapshot and calls the engine's entry points. `annotator/app.html` is now only `#review-root` + `#content`. Deleted with the subtabs: `visionScreen()`, `twitchEmbed()`, `visionNavigation()`, the empty `#vision-host-host`, the duplicate `playersScreen`/`playerForm`/`parseSource` definitions, and the `[data-embedded] nav` hiding rule.

**What the stage says about itself.** Freshness is honest: `frame age` for the live edge, an amber `STALE` state when frames stop (the last good frame stays up, marked), and a standing note that receive-to-result is local processing latency, **not** glass-to-glass. Model results render as a dashed, dimmed reference layer; operator corrections stay solid with grab handles; the facts line separates them as `<model> (+<n> manual)` (`annotator/app.css:53-73`, `annotator/vision-stage.js:160-164`). A failed live start is reported inside the Vision surface — stage line, inspector `Start attempt` block with cause/remedy/Retry, strip chip — never a distant auto-clearing toast.

### 3. Event detection rebuilt (`src/info_complete_scan.py`, `src/twitch_source.py`)
Replaced the old motion-energy detector (which produced 57 mostly-false shot candidates) with an **info-complete gated design**: transient inference only on frames where no person intersects the cloth, cloth area in band, exposure stable, ball census not dropping. Shots = matched same-color ball displacement ≥ 150 mm at 0.5–11 m/s across temporally adjacent gated frames; pots = established balls vanishing through a persistence window. Full-scan result on the 30-min VOD: **22 shots + 19 pots** (`out/scan-ic/events.json`), 17/22 shots cross-validated within 5 s of the old scan. The review queue (`out/scan30/events.json`) now serves these candidates as looping H.264 clips (`GET /api/clip`), legacy events backed up as `events-legacy.json`.

**These 30 candidates are unvalidated — human review is the next step.** They appear as cue cards in the Vision cues rail: selecting one seeks + freezes the stage, and the verdict block in the inspector records the verdict; that produces the shooter-association ground truth needed for P/R.

### 4. Live/VOD processing (`annotator/live_processing.py`, `annotator/twitch_source.py`)
Bounded, latest-frame-only pipeline: continuous decode into one pending slot, atomic JPEG/detection publication, drops stale frames instead of queueing. Twitch resolution via standard-library anonymous playback authorization (no login, no ad filtering), VOD support, safe errors. GPU YOLO person detection on live streams works (ROCm, ~26 ms warm).

### 5. SAM3 balls: CPU only (documented limitation)
The machine has an AMD RX 9070 XT; ROCm PyTorch 2.9.1 works (YOLO on GPU verified). **SAM3's detection head returns zero instances on GPU in every dtype/attention configuration tested** (bf16, fp32, MATH attention, precision env flags) — traced to ROCm 6.4 "high-efficiency" fp32 GEMMs on gfx1201 corrupting SAM3's presence head. SAM3 is pinned to CPU with an explicit error on GPU requests. **A real bug was found and fixed along the way**: `vitdet.py` imported the unfixed fused kernel before the CPU patch ran; `_apply_patches` now rebinds both — this made **CPU SAM3 3× faster** (143.9 s → 47.5 s/frame) with identical output. Full evidence trail in `docs/live-processing-verification.md`; revisit with ROCm 7.x RDNA4 kernel fixes.

## Verification status

- `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` — **168 tests pass, 2 skipped** (operations, identity, live processing, server routing, twitch resolver, info-complete scan, calibration). Re-run 2026-09-22: `Ran 168 tests in 65.385s · OK (skipped=2)`.
- `node tests/test_app_timeline.js` — **21 pass, 0 failed**; `node --test tests/test_ops.js` — **21 pass, 0 fail**. Both re-run 2026-09-22 on the one-stage Vision tab; the timeline suite now pins the new structure (no subtab machinery, one facts line, stage-only surface, EN/中 parity for every adapter string).
- Browser (agent-browser) verified: full tournament lifecycle with doubles, modal forms, bilingual EN/中, favicon files, VOD/clip playback, overlay rendering at 1280/390 px.
- SAM3 CPU parity: 10 balls on vod30 frame 300 after all changes.

## What is NOT done / known gaps

- **Event-candidate human review** — the 30 info-complete candidates still need verdicts before any P/R claim. The one-stage Vision tab is now the place to do it: a candidate is a cue card in the cues rail that seeks + freezes the stage, and the verdict block lives in the inspector. Old model-generated actor labels in `out/events_actors.json` are not ground truth.
- **Shooter association P/R** — blocked on the above; the harness (`tests/live_identity_validation.py`) emits per-cluster face signatures to make labeling fast.
- **SAM3 on GPU** — blocked by ROCm 6.4 gfx1201 numerics (see above), not by our code.
- **Twitch live processing end-to-end** — resolver + pipeline verified; examplechannel was offline during testing, so no real live-stream latency was measured. Upstream Twitch delay is unknown; the interface states that rather than guessing.
- **Overlay latency — OPEN, options undecided, and the two costs must not be conflated.**
  - **Default `/api/unified` path — the only thing the UI's `overlays LOADING (n s)` counter measures.** Each uncached frame decodes the video, detects table + ball candidates and runs person identity (`annotator/unified_server.py:250-270`). Measured on the running service 2026-09-22: frame 1234 (uncached) **1.36 s** — balls 5 · persons 4 · pockets 6, no `persons_error` — plus frames 777 / 778 / 779 / 3000 / 5000 at **0.22–2.28 s**. So the default overlay path is **~0.2–2.3 s per frame with identity included**; `docs/vision-audit.md` measured up to **7.55 s** at frame 3000 on a cold run. The UI shows the counter and keeps the last good frame rather than pretending to be current.
  - **SAM3 balls — opt-in, and a different endpoint from the default path.** `POST /api/inference` with `balls` in `detectors` runs as an async job and does not go through `/api/unified`. SAM3 is pinned to CPU (§5 above: ~47.5 s/frame after the vitdet fix). Measured 2026-09-22 on the same frame 1234: **45.06 s wall** (≈21 s model load, then ≈21 s detection, 9 boxes returned) — consistent with the documented ~47.5 s/frame CPU cost. A deliberate opt-in, not a regression in the overlay path.
  - **Fresh-load cold path: `overlays LOADING (23.1 s)` was measured on a first load** (independent re-verification, `docs/vision-verification.md`, fixture on loopback, 2026-02-14; the fixture's identity models are cold in a fresh process). That is a real cold-path datapoint for the previous bullet's `~0.2-2.3 s` warm figure — the counter measures `/api/unified` on an uncached frame with cold identity models, and the stage keeps the last good frame while it runs. It is one observation, not a distribution: a second cold load was not timed.
  - **A `60.4 s` `overlays LOADING` counter was observed once and is NOT reproduced.** It cannot be attributed to the SAM3 path: `state.loading.overlay` is written only by `loadUnified` (`annotator/app.js:178`, cleared at `:189`), so that counter tracks `/api/unified` alone, and the inference job holds no lock that would block a concurrent `/api/unified` call (`decode_frame` is lock-free; the job takes `self.lock` only for brief job-dict updates). Best explanation: a `/api/unified` call that was genuinely slow on that occasion — most likely cold identity models in a fresh process, or CPU contention — but **that is a hypothesis, not a measurement, and the upper bound stays unquantified.** Options (detector caching, skipping identity while scrubbing, explicit model warm-up) are not yet decided. This is a gap, not a promise.
- **Deployment** — service is running and smoke-tested (root, favicon, APIs 200; Access redirect intact). All recent code changes are live on pool.example.com. A hard refresh (Cmd/Ctrl+Shift+R) may be needed once to pick up the new favicon and the one-stage Vision layout.
- **Commits** — the work is committed, not pending. Vision rebuild: `a4738ba vision: one stage, two rails, zero subtabs`, `6ef2e2c vision: one frame surface, live edge, per-artifact receipts`, `50e3ae7 vision: pin the one-stage contract in tests and docs`, `f101d67 vision: translate live states, separate model from manual marks`, `d77d4df vision: pin the state vocabulary and overlay provenance in tests`.

## Key commands

```bash
# start/stop the app
systemctl --user start pool-workbench.service   # port 8130, loopback only

# run all backend tests (SA3 CPU is slow: ~60s total)
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py'

# frontend tests
node --test tests/test_ops.js && node tests/test_app_timeline.js

# browser fixtures (temporary state, no production writes)
PYTHONPATH=. .venv/bin/python tests/serve_workbench_fixture.py    # port 8131, real VOD + review data
PYTHONPATH=. .venv/bin/python tests/serve_operations_fixture.py   # port 8132, empty club

# real-detector live pipeline evidence
.venv/bin/python -B tests/live_processing_e2e.py --ffmpeg /nix/store/cjsxh3v95ki1mwcccya9zhfdc837703c-ffmpeg-headless-9.0-bin/bin/ffmpeg

# re-scan the VOD for event candidates
PYTHONPATH=. .venv/bin/python src/info_complete_scan.py --stride 2
```

## Key docs

| Doc | Contents |
|---|---|
| `docs/vision-redesign-outline.md` | The one-stage Vision design: source chips, cues rail, stage, inspector, scrub strip; honest-liveness rules; engine decision |
| `docs/vision-audit.md` | The factual audit the redesign answers: six subtabs, four unreachable by mouse, duplicate frame surfaces, false `OVERLAYS: none` |
| `docs/vision-verification.md` | Independent re-verification of the Vision rebuild (round 2) |
| `docs/corner-pocket-functional-inventory.md` | Authoritative acceptance checklist from the mockup |
| `docs/live-processing-verification.md` | Real measured numbers: live pipeline, identity, SAM3 GPU verdict |
| `docs/corner-pocket-verification.md` | Deployed-fix ledger (caching, dead space, fidelity) |
| `docs/corner-pocket-operations.md` | Operations API contract and tournament rules |
| `docs/unified-workbench.md` | Hosting (Access/tunnel), service, hierarchy |
