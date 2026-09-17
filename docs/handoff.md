# Corner Pocket — handoff

## Where things stand (2026-09-16)

The repository now contains a complete Corner Pocket club-operations application plus a rebuilt computer-vision pipeline. Everything runs locally at `http://127.0.0.1:8130/` behind Cloudflare Access (deployed), with the app code serving from disk. **The service is RUNNING** on port 8130 and verified: app root, favicon, operations API, live API, and VOD metadata all return 200; public URLs still redirect to Cloudflare Access (302). Restart any time with `systemctl --user restart pool-workbench.service`.

## What exists

### 1. Club operations app (`annotator/ops.html`, `ops.js`, `ops.css`, `operations.py`)
Single-page app, six top-level tabs — **Floor · Set up · Matches · Vision · Regulars · Back room** — all with persistent state in `out/corner-pocket/state.json`.

- **Tournament engine** (`annotator/operations.py`): singles/doubles, byes, scheduling, table assignment/release, scoring, signed results, forfeits, absences propagated through rounds, guest→regular promotion, archive/history. Optimistic concurrency (`revision`, HTTP 409 on stale writes). Bounded audit `events[]` (500 newest).
- **Player identity** (`src/face_id.py`, `src/person_identity.py`, `src/person_pipeline.py`): ArcFace (insightface `buffalo_l`) enrollment per regular, YOLOv8n person detection → vendored OSNet x0.25 re-ID → persistent clusters. Face binding fires once (threshold 0.35 cosine, margin 0.12 over runner-up, quality gate: eye distance ≥ 8 px, det score ≥ 0.4). Explicit A/B/ignore seeds override everything. Body re-ID clustering is **disabled by default** (measured: same-person p05 0.755 vs cross-person p95 0.882 — not separable; see calibration constants in `src/person_identity.py`).
- **UI/UX decisions applied**: event name auto-generated from date + weekday, race default 1, Visitor/Inactive removed from creation flow, Regulars edit is a modal opened by a + icon, tab kicker/title blocks removed, footer removed, date formatting, brass control accents.

### 2. Vision = one unified viewer
The old six Vision subtabs are gone. Vision contains a collapsible **Stream/sources** panel (Twitch live + VOD embeds, chat, native live processing) above the **Unified viewer**: video player, frozen-frame inspector, and overlay layers (cloth polygon, ball locations — click to create/label a correction box, six pockets with names, person boxes with cluster/identity chips) toggled per layer. Event markers on the scrub bar come from the info-complete scan.

### 3. Event detection rebuilt (`src/info_complete_scan.py`, `src/twitch_source.py`)
Replaced the old motion-energy detector (which produced 57 mostly-false shot candidates) with an **info-complete gated design**: transient inference only on frames where no person intersects the cloth, cloth area in band, exposure stable, ball census not dropping. Shots = matched same-color ball displacement ≥ 150 mm at 0.5–11 m/s across temporally adjacent gated frames; pots = established balls vanishing through a persistence window. Full-scan result on the 30-min VOD: **22 shots + 19 pots** (`out/scan-ic/events.json`), 17/22 shots cross-validated within 5 s of the old scan. The review queue (`out/scan30/events.json`) now serves these candidates as looping H.264 clips (`GET /api/clip`), legacy events backed up as `events-legacy.json`.

**These 30 candidates are unvalidated — human review is the next step.** Open Event review, watch the clips, record verdicts; that produces the shooter-association ground truth needed for P/R.

### 4. Live/VOD processing (`annotator/live_processing.py`, `annotator/twitch_source.py`)
Bounded, latest-frame-only pipeline: continuous decode into one pending slot, atomic JPEG/detection publication, drops stale frames instead of queueing. Twitch resolution via standard-library anonymous playback authorization (no login, no ad filtering), VOD support, safe errors. GPU YOLO person detection on live streams works (ROCm, ~26 ms warm).

### 5. SAM3 balls: CPU only (documented limitation)
The machine has an AMD RX 9070 XT; ROCm PyTorch 2.9.1 works (YOLO on GPU verified). **SAM3's detection head returns zero instances on GPU in every dtype/attention configuration tested** (bf16, fp32, MATH attention, precision env flags) — traced to ROCm 6.4 "high-efficiency" fp32 GEMMs on gfx1201 corrupting SAM3's presence head. SAM3 is pinned to CPU with an explicit error on GPU requests. **A real bug was found and fixed along the way**: `vitdet.py` imported the unfixed fused kernel before the CPU patch ran; `_apply_patches` now rebinds both — this made **CPU SAM3 3× faster** (143.9 s → 47.5 s/frame) with identical output. Full evidence trail in `docs/live-processing-verification.md`; revisit with ROCm 7.x RDNA4 kernel fixes.

## Verification status

- `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` — **168 tests pass** (operations, identity, live processing, server routing, twitch resolver, info-complete scan, calibration).
- `node --test tests/test_ops.js` — 21 pass; `node tests/test_app_timeline.js` — 16 pass.
- Browser (agent-browser) verified: full tournament lifecycle with doubles, modal forms, bilingual EN/中, favicon files, VOD/clip playback, overlay rendering at 1280/390 px.
- SAM3 CPU parity: 10 balls on vod30 frame 300 after all changes.

## What is NOT done / known gaps

- **Event-candidate human review** — the 30 info-complete candidates need verdicts before any P/R claim. Old model-generated actor labels in `out/events_actors.json` are not ground truth.
- **Shooter association P/R** — blocked on the above; the harness (`tests/live_identity_validation.py`) emits per-cluster face signatures to make labeling fast.
- **SAM3 on GPU** — blocked by ROCm 6.4 gfx1201 numerics (see above), not by our code.
- **Twitch live processing end-to-end** — resolver + pipeline verified; examplechannel was offline during testing, so no real live-stream latency was measured. Upstream Twitch delay is unknown; the UI says so.
- **Deployment** — service is running and smoke-tested (root, favicon, APIs 200; Access redirect intact). All recent code changes are live on pool.example.com. A hard refresh (Cmd/Ctrl+Shift+R) may be needed once to pick up the new favicon and merged Vision layout.
- Commits: **everything is uncommitted** (the repo has no commit history for this work — decide what to commit before doing anything destructive).

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
| `docs/corner-pocket-functional-inventory.md` | Authoritative acceptance checklist from the mockup |
| `docs/live-processing-verification.md` | Real measured numbers: live pipeline, identity, SAM3 GPU verdict |
| `docs/corner-pocket-verification.md` | Deployed-fix ledger (caching, dead space, fidelity) |
| `docs/corner-pocket-operations.md` | Operations API contract and tournament rules |
| `docs/unified-workbench.md` | Hosting (Access/tunnel), service, hierarchy |
