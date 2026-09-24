# Corner Pocket — handoff

## Where things stand (2026-09-24)

The club-operations app and the vision pipeline both ship from this repo, served on
`http://127.0.0.1:8130/` behind Cloudflare Access (`systemctl --user restart pool-workbench.service`).
The headline since the last handoff: **the ball detector the pipeline was blocked on now exists and
clears its accuracy bars, while the served event queue is empty on purpose** — 0 events, because
every one of the 15 previously served candidates was measured to be an occlusion artefact, not a
shot.

---

## 1. Current status

### 1.1 The Vision tab — one stage, two rails, zero subtabs
Source of truth: `docs/vision-redesign-outline.md`; independent re-verification: `docs/vision-verification.md`.

- Layout is a source chip row, then `[Cues rail ~280 px | Stage 16:9 | Inspector ~320 px]`, then a scrub strip carrying the **single facts line**. There is no sub-tab navigation and no landing screen.
- **One picture surface**: the stage draws the live edge **or** a VOD frame, never two copies of one moment.
- **Overlay provenance** is tagged in place: `MODEL` / `模型` (dashed), `YOURS` / `人工` (solid, with grab handles), `CALIB` / `标定` (pockets projected from the saved anchors) — `annotator/app.js:220`, `annotator/app.css:65-107`. The facts line names the pocket source, e.g. `pockets 6 (saved anchors)`.
- **Refusal reasons reach the operator** on the stage and in the facts line, e.g. `quad drift vs saved corners 6.4 px (tol 40 px)` (`docs/app-path-refusal.md`; commit `d5873a0`). Three refusals are surfaced rather than silent: a refused table quad, a correction that belongs to another (dataset, frame, size), and a model quad that fails the sanity check.
- Re-verified in a real browser: 0 console errors/warnings across a full drive; Space / ← / → verified (±1 frame, no double consumption); 中 mode has no Latin state-word residue; the facts-line provenance numbers match the SVG node counts exactly, twice, in both languages (`docs/vision-verification.md`).

### 1.2 What the queue serves: nothing, on purpose
`out/scan30/events.json` is `[]` — **0 events**. This is an owner decision (commit `0e61a4b`), not a
failure: the 15 candidates the queue used to carry were each measured as occlusion (a person crossing
the cloth), so the queue was emptied rather than asking for reviews of events that are provably not
shots (`docs/tiered-queue-verification.md` §Round 4).

- The UI says why, in place: `shots-measured-none` (and a separate `pots-measured-none` sentence). Tier filter buttons that could only return nothing are hidden; ALL / SHOTS / POTS / UNREVIEWED stay because each is a way to read a reason.
- The history is kept in artifacts, not deleted: `out/scan30/events.tiered.json` (the 15), `gate_report.json` (33 not-confirmed rows), `eval_regen.json` (all 48 measured).
- `out/scan30/annotations.json` holds exactly **one** verdict: event `16` = `unsure`, `updated_at` 2026-09-23T21:27:12Z (read from the file).

### 1.3 Identity labelling, and where the source settings went
Source: `docs/identity-labelling-and-source-rail.md`.

- A selected person track is labelled as **one regular** (`Which regular?` dropdown) **or one guest name** (text box), or quietly `Ignore (not a player)` under the two options. Write paths: `POST /api/identity/seed`, `POST /api/vod30/seeds`, plus clear/unbind.
- Legacy `A` / `B` / `ignore` are gone from the primary UI but still writable and still trainable; a guest name is stored and displayed but **never** trained on.
- The **`Source` chip** is the first chip of the stage chip row; one click opens `#vs-source-panel` with everything that used to live in the rail (datasets, live state, start/stop, detector toggles, saved channels, Twitch URL form, latency caveat). The rail keeps the frame tools.

### 1.4 API contract — reads are side-effect free
Source: `docs/unified-workbench.md` §"API write contract".

Every `GET` reads and renders and never rewrites a persisted file (checked as bytes + size + mtime).
The single deliberate exception is `GET /api/clip`, which writes a regenerable fragment under
`out/clip-cache/` on a cache miss only — derived media, not state. Writes live in the POST handlers.

---

## 2. What changed since the last handoff

One bullet per landed workstream; the doc carries the detail.

- **Table-cloth refinement, and honest refusal** — `9acf299 vision: refine the table cloth boundary from a static-camera prior`, `d5873a0 vision: carry the refusal reason to the operator, and count the polygon by source`, `a362aa6 eval: score the app detector against the hand anchors, not its own seed` → `docs/app-path-refusal.md`, `docs/table-detect-verification.md`.
- **Candidates from raw motion, then gates, then an empty queue** — `793ea60 detect: generate candidates from raw motion, then buy the evidence`, `13a430c detect: gate the served queue, dedupe at the source, show the numbers`, `1817c7c queue: carry the confirmation tier and the geometry check on every event`, `cc7ca24 vision: badge the confirmation tier, filter on it, and explain an empty pot list`, `0e61a4b vision: say why the event rail is empty, and hide what can no longer act` → `docs/tiered-queue-verification.md`.
- **Ball-scale motion, measured and independently attacked** — `7ab1f33 vision: measure ball-scale motion densely over the whole VOD`, `3f49c0b docs: verify the ball-scale saturation measurement independently` → `docs/motion-saturation-verification.md`.
- **The tiny ball detector: probe, then training pass** — `f86e8c6 vision: probe whether a tiny appearance net can find these balls`, `442c092 vision: pin the tiny-ball probe's measurement rules`, `dfbe0c6 vision: train the tiny ball net at 960x540, and measure the scaling curve` → `docs/tiny-ball-probe.md`, `docs/near-real-time-ball-detector.md`.
- **SAM3 made 4.3× cheaper for labels** — hybrid CPU-head/GPU-encoder labeller in `src/fast_ball_labels.py`; `1b64c2b sam3: filter balls by the verified reference geometry, not the frame mask` → `docs/near-real-time-ball-detector.md` Part A.
- **Shot/pot gate rules, written before the track exists** — `1abeb6a events: gate shots and pots over a ball track`, `4cad7f2 events: test the shot and pot gate on synthetic and census tracks`, `94d67f4 docs: record the shot and pot gate rules and their test outcome` → `docs/state.md` (2026-09-24 entry).
- **Live pipeline: per-frame stages and cadence** — `573bf86 live: pluggable per-frame stages with latency accounting`, `84e72b9 live: serve the static cloth quad from the saved segment reference`, `4ca2d4c live: per-stage cadence so a stage can run on 1 frame in N` → `docs/live-processing-verification.md`.
- **Calibration truth: which mapping is real** — `55b13ad calib: decide the px<->mm mapping and project claims in their own frame`, `f43cf24 events: warn on rail evidence, not coverage, and project claims in their frame`, `5847549 calib: measure the highlight reference` → `docs/calibration-truth.md`, `docs/segment-calibration.md`.
- **Face identification, measured and its bar stated honestly** — `700f506 faces: assess face identification on this footage`, `b90fdf9 faces: make bind_face enforce the same runner-up margin as best_match`, `bc69602 docs: state the effective bind bar (0.47), not the threshold` → `docs/face-identification-assessment.md`.
- **Rail labelling + source panel** — `d0d238f vision: label a person track as one regular or one guest name`, `dcb0d8e server: a track label may be a guest name, and a binding can be undone` → `docs/identity-labelling-and-source-rail.md`.
- **A read no longer rewrites the index; the timeline is exact** — `899c997 identity: a read must not rewrite the index file`, `74f7d7f docs: record that the VOD timeline is exact and the motion is not a ball` → `docs/unified-workbench.md`.
- **Research: no world model will give us ball positions** — `docs/research-video-world-models.md`.

---

## 3. Measured numbers that matter

Every number below is quoted from the file named with it.

### 3.1 Tiny ball detector (`docs/near-real-time-ball-detector.md`; artifact `out/tiny_ball_probe/report_960x540.json`)

| round | input | P | R | **F1** | loc. median | loc. p90 | ms/frame | end-to-end fps |
|---|---|---|---|---|---|---|---|---|
| probe | 640×360 | 0.881 | 0.751 | 0.811 | 2.5 px | 4.48 px | 15.5 | 64 |
| **r1 (operating point)** | **960×540** | 0.940 | 0.914 | **0.927** | **1.48 px** | **3.62 px** | **35.7** | **28.0** |
| r2 | 1280×720 | 0.961 | 0.868 | 0.912 | 1.19 px | 3.20 px | 85.3 | 11.7 |

- Operating point at threshold 0.425: TP 235 / FP 15 / FN 22 (`out/tiny_ball_probe/report_960x540.json`).
- The **frozen held-out set is 47 frames** (`out/tiny_ball_probe/held_frozen.json`, `held: 47`; frozen so that added labels cannot move the validation set). Labels behind the rounds: 468 frames / 2,722 instances.
- Model alone is 23.5 ms/frame (42.6 fps) — it clears 30 fps; **the end-to-end call does not** (35.7 ms). Native 1280×720 costs 2.4× and is not the operating point.

### 3.2 SAM3 as a labeller, 4.3× cheaper (`docs/near-real-time-ball-detector.md` Part A)

| | CPU SAM3 | hybrid | |
|---|---|---|---|
| seconds/frame | 27.1 | **6.27** | same process, same weights |
| frames/minute | 2.21 | **9.57** | **4.32×** |

- **Instance-count agreement vs the verified CPU path: 6/6 frames identical counts, 6/6 fully matched, 0.00 px maximum position error.**
- `prelabel` with the 960×540 student: 600 frames in 52.4 s = **686.8 frames/min**, **6,415 labels kept**, 17 of 6,432 sent to review — a noise filter, not a precision filter.

### 3.3 Live envelope, per stage and per cadence (`docs/live-processing-verification.md` §"Static table, stage cadence")

Quiet host (`loadavg` 4.0–5.8), 90 frames/case, budget 33.33 ms; `ball` is a 15 ms stand-in, not the real detector:

| case | envelope p50 | published/90 | fps |
|---|---|---|---|
| `decode` (no stages) | 2.94 ms | 90 | 30.6 |
| `person` | 17.03 ms | 90 | 30.5 |
| `table+person` | 15.35 ms | 90 | 30.4 |
| `table+person+ball@1` | 30.49 ms | 82 | 27.6 |
| `table+person+ball@2` | 30.86 ms (23.33 amortised) | 71 | 23.9 |
| `table+person+ball@3` | 30.73 ms (20.69 amortised) | 86 | 29.2 |

- Serving the static cloth quad from the saved segment reference cut the table stage from **11.27 ms p50 → 0.05 ms p50** (29.3 → 0.09 ms p95).
- **Under load the envelope collapses**: same host at `loadavg` 6.6 → 17.1 gives `decode` 9.38 ms, `person` 20.84 ms, `table+person` 27.13 ms, and the ball configurations stop publishing usefully.
- Cadence costs latency: onset→call ≈147 ms (ball@1), ≈263 ms (ball@2), ≈380 ms (ball@3) mean. Honest target: 30 fps on a **quiet** host at cadence 2–3, else 15 fps with ≤0.4 s onset.

### 3.4 Why the queue emptied — motion at 720p (`docs/motion-saturation-verification.md`; `docs/tiered-queue-verification.md` §Round 4)

- Ball luma contrast, 1,052 instances: median **39.0**, p95 **70.0**, p99 87.0, max **101.5** — against an assumed 135. The true ceiling of the 17×17 channel is **93–101 (geometry) / 85–98 (injection)**, i.e. 18–25 % below the assumed 124.
- The quiet floor is lower than the original control: p99.9 **72.16** on 13 person-free windows (threshold ×1.25 → **90.20**), **65.51** on the 7 windows checked frame-by-frame, **36.03** on frames where no cloth pixel changed — versus the original **100.51** (threshold **125.6**).
- **15/15 served events were occlusion-explained** (`occ_dense` 0.45–0.97; each event's largest changed component 9.2–58.4× one ball's area) and **0 of 55 ball-scale onsets could be a single ball** — measured in `out/motion_scan/vod30.summary.md` (commit `7ab1f33`) and cited by `docs/tiered-queue-verification.md`. That event-by-event verdict was **not independently re-derived** by `docs/motion-saturation-verification.md`, which marks it out of scope.
- A ball at pool speed moves 12–48 px between frames (`docs/research-video-world-models.md` §1) — single-frame or 0.5 s sampling is far below the event rate.

### 3.5 Calibration truth (`docs/calibration-truth.md`; `docs/segment-calibration.md`)

- **The hand anchors are the authoritative physical mapping**; the scan quad is the frame the queued claims were *written in*, so a claim is projected back through it (`src/eval_events.py:137 claim_calibration`). Held-out provenance test: residuals to the stored pixel 12.88 px (scan frame) vs 38.19 px (anchors).
- The two mappings disagree by up to **90.7 px at the head-left corner**; the frames' own rail evidence supports the anchors on every sampled frame and the scan quad on none.
- The gate's calibration warning fired on correctly calibrated frames and now comes from per-side rail evidence: same 48 candidates → **11 warnings → 0**.
- `vod30` is **one segment**: whole-frame phase shift ≤ 0.74 px over 30 min, verdicts unchanged (2 confirmed / 27 rejected / 7 unconfirmed) under every reference.
- **Highlight:** `out/fixed_corners.json`'s bottom rail sits **28.2 px inside the visible cloth** (≈ 85.3 mm ≈ 0.92 ball diameters); the other three sides agree within 0.5 px. The highlight has no hand anchors, so its app path has no seed and falls back to the naive detector (13.28 px median vs 1.90 px full-res).

### 3.6 Face identification (`docs/face-identification-assessment.md`)

- A production-usable face is found on **74 %** of person instances (vod30 73.93 %; production selection — quality face inside the box — 69.01 %); median inter-eye distance **12.44 px** (gate 8), median detection score **0.807** (gate 0.4).
- Separation: same-person p05 **0.405** vs different-person max **0.226** — **the distributions do not overlap**, so a threshold works. Body/colour re-ID remains disabled because its distributions *do* overlap (0.755 vs 0.882).
- The bar that binds is **0.47** (0.35 threshold + 0.12 runner-up margin); **0.35 alone never binds**. A candidate 0.65 is measured but **not applied**. In the demo window 2 of 35 impostor faces cleared 0.47 (5.7 %), from a single enrolled photo.
- **The roster is empty** — `out/corner-pocket/state.json` has `"players": []` and there is no `out/corner-pocket/face_embeddings.json`, so nothing can bind today.

---

## 4. Open items / not yet true

- **The queue stays empty until dense tracks exist.** The gate produces *nothing* from a sparse census: over the real SAM3 census it emitted 0 shots, 0 pots, 0 unknown disappearances and 435 rejections (`docs/state.md`, 2026-09-24).
- **Detector accuracy is against a teacher, not ground truth.** SAM3 is the label source, so F1 0.927 measures distillation fidelity; the **15 false positives are unreviewed** and only a human looking at `out/tiny_ball_probe/overlays2/*.png` can settle them (`docs/near-real-time-ball-detector.md`).
- **The 30 fps claim is not yet the real detector's.** 28.0 fps end-to-end is measured with the trained net, but the pipeline's own 30 fps envelope was measured with a 15 ms stand-in; the real-detector end-to-end number is being re-measured now and is not final.
- **No live source is reachable**, so live end-to-end is unproven: usher answers `404 Can not find channel` and Streamlink's remaining step is a client-integrity token the module refuses by design (`docs/live-processing-verification.md` §"Twitch live path: NOT reachable"). `upstream_delay_ms` is `None`.
- **The roster has 0 regulars** (`out/corner-pocket/state.json`), so face binding cannot fire even though the matching is measured to work.
- **`annotations.json` holds one verdict** — event 16 = `unsure`, which is most likely the operator's own click, not a reviewed candidate (`out/scan30/annotations.json`).
- **One deliberate write on a read path:** `GET /api/clip` writes a regenerable fragment under `out/clip-cache/` on a cache miss (`docs/unified-workbench.md`).
- **First-load overlay latency is still slow.** Overlays take **~25 s** to reach `overlays ON` on a fresh load at 1440 px — `overlays LOADING (23.1 s)` observed — and **~40 s** at 390 px (`overlays LOADING (34.1 s)`); the earlier frames of that window are loading, not failures (`docs/vision-verification.md`). The stage keeps the last good frame and prints the counter meanwhile. The cold-process bound was not re-measured in this pass.
- **~35 local commits are unpushed** (35 measured by `git log @{u}..HEAD`).
- **Test counts are not re-run in this pass.** Docs record python 621 passed / 2 skipped (`docs/state.md`) and timeline 50 / ops 21 (`docs/identity-labelling-and-source-rail.md`); the count after the calibration-truth round is **UNVERIFIED — no post-round suite number is recorded in a doc read here** (the suite is not runnable at the moment, being fixed by another worker).

---

## 5. Next steps

1. **Owner, ~10 minutes: click the six highlight anchors.** It is the only fix that removes the 28.2 px foot-rail bias *and* gives the highlight a seed; it cannot be automated and no anchor data may be invented (`docs/calibration-truth.md` §3, option 2).
2. **Re-measure the real detector's end-to-end fps** on the same box (a worker is doing this) — that closes the last gap between the 28.0 fps measurement and the 30 fps requirement.
3. **Add the regulars and one photo each.** Face matching is measured to work; the only blocker is the empty roster (`docs/face-identification-assessment.md` §5).
4. **Get dense ball tracks, then let the gate judge them.** The gate is written and tested against synthetic ground truth; it needs a real track (`docs/state.md` 2026-09-24).
5. **Look at the overlays and settle the 15 FPs**, and consider the 2.0 min-per-VOD dense motion pass recommended in `docs/research-video-world-models.md`.
6. **Push the ~35 local commits.**

---

## Key commands

```bash
# app lifecycle
systemctl --user restart pool-workbench.service      # port 8130, loopback only

# suites
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
node --test tests/test_ops.js && node tests/test_app_timeline.js

# browser fixtures (copied data, never production labels)
PYTHONPATH=. .venv/bin/python tests/serve_workbench_fixture.py     # :8131, real VOD + review data
PYTHONPATH=. .venv/bin/python tests/serve_operations_fixture.py    # :8132, empty club

# the detector
PYTHONPATH=. .venv/bin/python -m src.tiny_ball_net report --size 960x540 --overlay-count 20
PYTHONPATH=. .venv/bin/python -m src.fast_ball_labels label --count 300 --stride-s 6
```

## Key docs

| Doc | Contents |
|---|---|
| `docs/vision-redesign-outline.md` | The one-stage Vision design: chips, cues rail, stage, inspector, scrub strip |
| `docs/vision-audit.md` | The audit the redesign answers: six subtabs, duplicate frame surfaces, false `OVERLAYS: none` |
| `docs/vision-verification.md` | Independent browser re-verification of the rebuild and the mobile sheet |
| `docs/tiered-queue-verification.md` | The tiered queue, the emptied queue, and the UI empty states |
| `docs/app-path-refusal.md` | Why the app refused the quad, the fix, and the honest caveat |
| `docs/table-detect-verification.md` | Table-cloth detection baseline and the withdrawn circular result |
| `docs/segment-calibration.md` | One segment on vod30; the coverage drop is occlusion |
| `docs/calibration-truth.md` | Which px↔mm mapping is authoritative, the gate warning fix, the highlight rail |
| `docs/motion-saturation-verification.md` | Independent attack on the ball-scale motion measurement |
| `docs/tiny-ball-probe.md` | The 640×360 feasibility probe (MARGINAL) |
| `docs/near-real-time-ball-detector.md` | The trained 960×540 detector, the hybrid SAM3 labeller, the scaling curve |
| `docs/face-identification-assessment.md` | Face detection, separation, the 0.47 bind bar, the empty roster |
| `docs/identity-labelling-and-source-rail.md` | Regular/guest/Ignore labelling and the `Source` panel |
| `docs/live-processing-verification.md` | Per-stage envelope, cadence, Twitch reachability, SAM3 GPU verdict |
| `docs/research-video-world-models.md` | Why no open world model measures a ball position |
| `docs/unified-workbench.md` | Hosting (Access/tunnel), service, the API write contract |
| `docs/state.md` | Append-only measured-numbers log |
