# Live processing: real local verification

## Person identification performance (2026-09-11 measured)

Warm per-frame cost on real VOD 1280x720, CPU only: YOLOv8n person detection ~25–32 ms, OSNet x0.25 (vendored MSMT17 weights) re-ID ~38–47 ms per frame for up to 3 persons — combined worst frame 78 ms, comfortably inside a 10 fps processing budget. Face embeddings (buffalo_l ArcFace) verified usable at this camera distance: 268/268 sampled faces produced 512-dim normalized embeddings; same-person 1s-apart cosine median 0.958 (p05 0.644) vs cross-person same-frame 0.077 (p05 −0.04), supporting a 0.35 match threshold with a 0.12 margin over the runner-up (the effective bind bar is 0.47 = 0.35 + 0.12; 0.35 alone never binds). Face sizes: eye distance median ~10.4 px, max 15.9, min 2.3.

Ground-truth caution: `out/events_actors.json` contains 57 entries but 45 were labeled by the previous `osnet-geo` model output, not independent humans (48 B / 4 A / 5 None). Shooter-association P/R must be measured only against human-confirmed labels from the explicit A/B/ignore seeding workflow; model-labeled actors are never truth.

## Identity pipeline on real footage (2026-09-15, full-segment run in progress)

Found and fixed a real integration bug the unit tests could not see: `process_frame` fed the 512-dim ArcFace embedding into the 128-dim body identity index, so any frame containing a visible quality face crashed the pipeline. Fixed in `src/person_pipeline.py`; all 19 identity + 21 face engine tests still pass.

Smoke run (frames 8000–8060, warm): 3 persons/frame, one cluster, no player binding before enrollment (no fabricated identities); enrolling a quality face (eye distance 13.9 px, detection score 0.837) bound the cluster at similarity 1.0 and the binding persisted across view exits. All state writes stayed in a temporary root; production annotation files unchanged.

Warm per-frame cost is dominated by full-frame face analysis (~300–390 ms) over detection (~25 ms) and OSNet re-ID (~55–85 ms): roughly 390–460 ms total, above the 150 ms budget. Face analysis is the known next optimization (ROI-restricted detection), recorded honestly rather than tuned prematurely. Full-segment numbers to follow.

## Application support and boundaries

Vision → Stream/source controls now contains continuous processing controls for local replay and saved canonical Twitch channels. This processing is separate from the optional watch-only Twitch embed. The pipeline continuously decodes into one pending-frame slot and publishes an atomic JPEG/detection pair; under load it drops superseded frames instead of accumulating a queue.

Metrics distinguish queue wait (`receive_to_process_ms`), inference time (`inference_ms`), and complete local receive-to-result age (`receive_to_result_ms`). These exclude Twitch camera/encoder/CDN delay; `upstream_delay_ms` remains null. Cold model startup takes several seconds. CPU SAM3 balls are intentionally excluded from the live detector list; frame-level table/person detection is not temporal shot/pot or shooter identification.

The standard-library resolver obtains anonymous public playback authorization, validates initial Twitch HTTPS playlists and returns safe errors. A real check of `examplechannel` obtained authorization but returned playlist HTTP 404 (offline/no public playable stream). No actual Twitch frames or Twitch upstream latency were verified. Future remote playlist retrieval is performed by OpenCV/FFmpeg; initial URL validation is not a general-purpose arbitrary-HLS security boundary. Source input remains restricted to saved canonical Twitch channels.

Deployment completed after owner authorization and verification: restarted the existing workbench service, confirmed active, and verified origin `/`, `/api/operations`, `/api/live`, and VOD metadata return HTTP 200. Deployed browser shows all six tabs and the native live-processing panel with no JavaScript errors. Public root and `/api/live` both return HTTP 302 to the existing Cloudflare Access login using curl; an initial Python client received HTTP 403, so authenticated external end-to-end remains owner-login dependent. No Access/tunnel configuration or production annotations were changed.

The actual Vision browser lifecycle passed against an isolated real-video fixture: start, canvas frame with paired detections, stop through stopping to stopped, and navigation cleanup. At full 1080p, receive-to-result latency reached about four seconds under shared-host load. Live inference now proportionally caps frames to 960×540; `source_width`/`source_height` retain original dimensions, while JPEG and detection coordinates use `width`/`height`. Selected-frame annotation still uses original frames. This cap is a performance safeguard, not a promised frame rate. Rebenchmark after changes.

Latest predeployment regression: 79 Python tests, 16 review frontend tests, and 21 operations frontend tests passed.

## Reproduce

From `<repo>`:

```sh
.venv/bin/python -B tests/live_processing_e2e.py \
  --ffmpeg /nix/store/cjsxh3v95ki1mwcccya9zhfdc837703c-ffmpeg-headless-9.0-bin/bin/ffmpeg
```

Requires the existing `.venv` OpenCV/Ultralytics/Torch installation, `yolov8n.pt`, and `data/vod_30min_260815.mp4`. Installs/downloads nothing. Emits JSON evidence to stdout; assertions or FFmpeg failures return nonzero. `--outputs` defaults to four. Runtime varies with CPU load; each observation has a 45-second deadline.

The agreed public seams are `LiveProcessor.start`, `status`, `latest_jpeg`, and `stop`. Both detectors are the real `src.frame_inference.infer_frame` table/person implementation; capture is the default OpenCV FFmpeg backend. No fake capture or inference is injected.

1. Replay the actual 1280×720 VOD using production ROOT in dataset mode, with no Operations-state writes. Observe several paired JPEG/detection results, then stop.
2. FFmpeg creates a 12-second, 640×360, 15 FPS real-content clip and a six-segment VOD HLS playlist under a temporary project-root directory. Replay the clip through dataset mode until `eos`.
3. Save a temporary Operations source with canonical `https://www.twitch.tv/examplechannel`. Inject only the resolver, returning a localhost HTTP HLS URL. A managed stdlib HTTP server delays each segment by one second so a finite fixture produces several observable outputs. Run to the expected live-disconnect error.
4. Repeat HTTP HLS and stop while running after four outputs.
5. Resolve the saved source to an HTTP 404 playlist and verify open failure, zero frames, and no JPEG.

All fixture, library-config/cache, and temporary files live under `<repo>/.live-e2e-*` and are removed on exit. The temporary model is a symlink to existing weights. The helper shuts down its HTTP server and joins its thread, stops every processor in `finally`, and verifies the saved Operations fixture is unchanged. It does not edit server/UI/module files or persistent Operations data.

## Capped-frame re-verification (current module)

After the live resize cap was added, the full helper ran again with `--outputs 8` and returned **exit code 0**. Assertions verify original `source_width/source_height` of 1280×720 and paired JPEG/metadata of 960×540, preserving aspect ratio; the 640×360 fixtures remain unchanged. Real detector and OpenCV capture defaults were retained.

| VOD sequence | Inference ms | Receive-to-result ms | Frame age at poll ms |
|---:|---:|---:|---:|
| 1 | 10364.24 | 10369.55 | 10369.75 |
| 280 | 252.95 | 294.07 | 315.95 |
| 289 | 328.82 | 336.38 | 340.41 |
| 299 | 329.16 | 338.11 | 357.43 |
| 309 | 64.83 | 73.28 | 85.46 |
| 311 | 101.66 | 116.81 | 124.81 |
| 314 | 374.86 | 399.66 | 419.68 |
| 325 | 395.02 | 437.11 | 457.83 |

VOD sample: received **338**, processed **8**, skipped **329**. Stop took **474.82 ms**, both threads dead. All eight sampled outputs reported four persons and no table polygon. This is a real detector limitation at the sampled resized frames, not a successful table-localization claim.

Warm samples excluding cold startup: inference **64.83–395.02 ms**, total local receive-to-result **73.28–437.11 ms**. Cold startup was **10.37 seconds**. The cap is verified functionally; host load was uncontrolled, so these results neither establish a speedup over the historical run nor guarantee subsecond processing on other VODs or 1080p content.

| Current capped run case | Received / processed / skipped | State before stop | Stop ms |
|---|---|---|---:|
| 12-second clip | 180 / 97 / 83 | `eos` | 0.08 |
| Finite HTTP HLS | 180 / 10 / 169 | expected `error` | 32.83 |
| Active HTTP HLS after eight outputs | 107 / 8 / 99 | `running` | 891.45 |
| HTTP 404 | 0 / 0 / 0 | expected `error` | 0.015 |

All stop results were `stopped` with decoder/worker dead; the HTTP server was shut down, the background job collected, and temporary fixtures removed. Canonical-source resolution, real playlist/segment HTTP retrieval, paired JPEG checks, EOS/error semantics, and no-state-write assertions passed again. This remains local HTTP HLS, not actual Twitch.

## Historical successful run (before resize cap)

The earlier execution returned **exit code 0**. Every case used real table/person inference. No new dependencies were installed. Background verification jobs were collected, and the HTTP server was shut down.

### Actual local VOD: first four observed outputs

| Sequence | Received | Processed | Skipped | Inference ms | Receive-to-result ms | Frame age at poll ms |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 185 | 1 | 183 | 6860.48 | 6863.63 | 6872.18 |
| 185 | 188 | 2 | 185 | 90.19 | 110.89 | 127.75 |
| 188 | 192 | 3 | 188 | 131.33 | 146.27 | 155.95 |
| 192 | 194 | 4 | 189 | 58.30 | 69.73 | 83.70 |

All four decoded JPEGs were 1280×720, 266–270 KB, with four detected persons each. The table polygon was present on sequence 1 and absent on the next three: real detector output is not guaranteed to find a table on every frame. Cold model initialization dominates the first result; skipped sequence numbers show latest-frame replacement rather than accumulating a FIFO backlog.

Active VOD stop took **37.26 ms**; state became `stopped`, both decoder and worker were dead.

### Finite VOD and HTTP HLS

| Case | Received | Processed | Skipped | Terminal/sample state | Stop ms |
|---|---:|---:|---:|---|---:|
| 12-second local clip | 180 | 172 | 8 | `eos`, no error | 0.07 |
| HTTP HLS through injected Twitch resolver | 180 | 10 | 169 | `error` | 45.37 |
| Active HTTP HLS stop | 47 | 4 | 43 | `running` before stop | 95.83 |
| HTTP missing playlist | 0 | 0 | 0 | `error`, no latest JPEG | 0.015 |

Finite HLS observed sequences were `1, 17, 18, 47, 48, 77, 78, 107, 108, 137`. HTTP evidence recorded requests for `/fixture.m3u8` and `/fixture0.ts` through `/fixture5.ts`, and the resolver received exactly the saved canonical Twitch URL. Active HLS stop observed `1, 17, 18, 47`; frame age at sample was 906.87 ms. Both worker threads were dead after every successful stop.

Expected terminal errors:

- Finite media treated as live: `Live stream ended or read timed out; restart to reconnect`.
- Missing playlist: `Could not open the selected media source`.

`error` may appear while an already-running inference is still finishing. The HLS error snapshot had `worker_alive=true`; `stop()` joined it and returned `stopped`. Stop preserves the error for diagnostics. Do not interpret an error snapshot alone as proof that threads have exited. Counts at stop/error can include a discarded in-flight frame, so received need not equal processed plus skipped.

The helper decodes each returned JPEG, verifies dimensions against its paired metadata, checks strictly increasing result sequence numbers, detector labels, and nonnegative timing with total receive-to-result at least inference duration. This tests the atomic result-pair API, not independent semantic proof that every box exactly belongs to those pixels.

## Limitations

- **Not actual Twitch.** No working Twitch resolver was available for the target `examplechannel`. This verifies saved-source validation, resolver invocation, real HTTP HLS decoding, and real inference only. It does not prove the channel is live, authenticate Twitch, or test Twitch CDN/playlist behavior.
- The HLS playlist is finite (`ENDLIST`) with paced local segment responses, not a continuously refreshed production live playlist.
- `receive_to_process_ms` is queue wait; `receive_to_result_ms` includes inference/encoding; `frame_age_ms` is latest result age since local decode receipt. `upstream_delay_ms` remains `null`. None measures broadcast-to-viewer latency or FFmpeg/network buffering before decode receipt.
- Startup latency is substantial (6.86 seconds in the final run; 9.03 seconds in a prior successful run). Throughput and skip counts vary with CPU contention and warm caches; these are observations, not performance guarantees.
- These runs establish bounded stop for local VOD and responsive/paced localhost HTTP, not arbitrary hung native I/O or pathological remote servers. Existing unit tests cover injected stuck-worker behavior separately.
- No ball/SAM3, browser, MJPEG route, UI controls, or detector-accuracy benchmark is covered here. No processor bug requiring a module edit was established.

## Person pipeline end-to-end run on full VOD segment (2026-09-15 measured)

Real (no-mock) run of `src/person_pipeline.py` (default YOLOv8n detector + vendored OSNet x0_25 re-ID + insightface buffalo_l face engine) over `data/vod_30min_260815.mp4` frames 8000-12000 (t=266.7-400.0s, 2001 frames processed at every 2nd frame = 15 fps), driver `tests/live_pipeline_run.py` (`E2E_F0/E2E_F1/E2E_STEP` overridable). All identity state went to a TempDir root (`/tmp/e2e-identity-sbhiiq9f`): `out/identity/clusters.json` + `out/corner-pocket/face_embeddings.json` under the temp root; production `out/` verified unchanged (2178 files mtime+size checked before/after); the video was opened read-only. Warm-up (detector 0.83-1.94s cold, OSNet 0.08s, buffalo_l 1.6s) ran before all timing. Note the YOLO "first call ~9s" figure includes ultralytics/torch import; the isolated first `predict()` here was 0.8-1.9s.

Segment run, no enrollment (phase 1):
- Persons tracked per frame: mean 2.95, max 5, zero-person frames 0 (no detector misses).
- Clusters: 41 tracker track_ids all merged into **1 cluster** (see finding B below); 38 cross-exit re-associations (new track joins the existing cluster), 0 true cluster merges (only one cluster ever existed).
- All `player_id` None — no fabricated identities without enrollment. 2933 `best_match` calls returned None against the empty gallery.
- Face quality seen (eye_px, center-inside-person faces): 3538 observations, p50 12.0 px, max 25.5 px.

Enrollment + binding (phase 2, fresh identity index, same real detector/encoder/face engine, temp face store):
- Clearest quality face of the dominant cluster: frame 11460 (t=382.00s), eye_px 25.5, det_score 0.833 → enrolled as `e2e-player-A` (1 face).
- First attempt re-ran only frames after 11460 and never bound — the enrolled person exits the right frame edge at ~frame 11462 and never returns with a detectable face (cosine vs enrolled: 0.723 @11458, 0.653 @11461, 0.315 @11462 turning away, undetected from 11463). Phase 2 therefore re-runs the whole segment.
- Bind: frame 8002 (t=266.73s), similarity **0.4922** ≥ 0.47 bar (threshold 0.35 + margin 0.12); the 8000 probe at 0.4499 was correctly rejected. Gallery margin is `inf` with a single enrolled player; measured cross-person face cosines on this footage are 0.005-0.078, so the effective margin at bind was ≈0.42.
- `player_id` persisted for the rest of the segment (0 violations), but only trivially: all persons share the single over-merged cluster, so binding one face labels everyone.
- Visual check of the bound vs enrolled face crops (48x49 vs 63x79 px, different pose, glasses): not convincingly the same person — 0.4922 sits in the ambiguous zone between cross-person p05 (-0.04) and same-person p05 (0.644). Probable false-positive bind; the margin guard is only meaningful with ≥2 enrolled players.

Timing (warm, per processed frame, ms): phase 1 total mean 326.6 / p50 323.1 / p95 489.8 / max 1354.3 (first processed frames still shed residual cold cost); phase 2 total mean 318.1 / p95 468.4 / max 703.2. Breakdown (phase 2): detector 22.3, OSNet encoder 51.9, buffalo_l face analyze 240.6 (p95 387.6). **The 150 ms warm target is NOT met: mean ≈ 320 ms ≈ 2.1x budget.** Detector + re-ID alone are ≈74 ms; full-frame face analysis on every frame is 75% of the cost (ROI gating or running face detection only when needed would fit the budget).

Findings:
- A. Bug fixed in `src/person_pipeline.py` (process_frame): the 512-d buffalo_l face embedding was passed to `IdentityIndex.update()` as `face_embedding`, but the index enforces one embedding dim (128-d OSNet) — the default pipeline crashed with `ValueError: embedding dim mismatch: got 512, expected 128` on the first real frame with a visible face (unit tests never caught it because fakes use same-dim vectors). Fix: stop feeding the raw face embedding into the body index; binding already flows through `best_match` + `bind_face`. All 19 person_* + 21 face_id unit tests pass after the fix.
- B. Body re-ID over-merges on this footage: same-frame OSNet cosines between clearly different persons are 0.79-0.87 (P1-P2 0.872, P1-P3 0.789, P2-P3 0.866 @11461) — far above MATCH=0.35. The 0.958/0.077 same/cross-person calibration quoted in `person_identity.py` is the face-embedding calibration, not body. Consequence: one cluster per session, "cross-exit re-association" fires trivially. Needs recalibration (body threshold ≳0.9) or a dedicated body-embedding calibration before cluster counts are meaningful.
- C. Weak-bind risk: with one enrolled player the margin check degenerates (`inf`), and a 0.49 similarity can bind a different person (observed). Enrollment flows should require ≥2 reference faces/players or a higher single-entry bar.
- D. `out/scan30/events.json` has no events at t=278/300/322; actual events inside the segment window: shots at t=273, 281, 343, 359, 372, 387 and pots at t=281, 343 (x2), 387.

## Body re-ID threshold calibration + over-merge fix (2026-09-15 measured)

Finding B follow-up. Driver: `tests/test_body_calibration.py` — real YOLOv8n person boxes + vendored OSNet x0.25 128-d embeddings on `data/vod_30min_260815.mp4`, production read-only, all state in temp dirs; heavy real-model passes are env-gated (`POOL_BODY_CALIBRATION=1`), the fast contract tests run in normal `unittest` discovery.

Pseudo-ground-truth (no human labels): a cross-person pair = two person boxes detected in the SAME sampled frame (never the same person); a same-person pair = the same box chained across consecutive sampled frames with IoU >= 0.6, compared across gaps <= 1 s (30 frames). Frames 8000-12000, every 10th frame embedded: 401 sampled frames, 1183 person embeddings, 8192 same-person pairs, 1330 cross-person pairs.

OSNet cosine distributions:
- same-person (<= 1 s gaps): p05 **0.7549**, median **0.8300**, p95 0.9972, max 0.9998; stable across gap buckets 0-10 / 10-20 / 20-30 frames (p05 0.755 in all three, so not a tracking artifact).
- cross-person (same frame): p05 0.7473, median **0.8107**, p95 **0.8824**, max 0.9830.

Verdict: **distributions OVERLAP — body-only clustering cannot separate these players at 1280x720 with these embeddings; no threshold exists.** Same-person p05 (0.755) sits below cross-person p95 (0.882) and the medians nearly coincide (0.830 vs 0.811): different people in one frame scored up to 0.983 cosine, one person vs themselves ~1 s apart scored down to 0.678. Any threshold low enough to keep true same-person pairs also merges different people (which is exactly how the borrowed 0.35 FACE bar produced the 41-tracks-into-1 mega-cluster); any threshold high enough to reject cross-person pairs rejects most true pairs (a "≳0.9" bar from finding B would miss ~95% of same-person pairs, p95 notwithstanding). Likely cause: small player crops, similar clothing, generic MSMT17 x0.25 weights. Honest negative finding accepted; identity binding runs on faces only.

Applied to `src/person_identity.py`:
- FACE binding keeps the measured face bar unchanged: `match_threshold=0.35`, `margin=0.12`.
- BODY merging is disabled by default: `BODY_MATCH_THRESHOLD = BODY_MATCH_DISABLED = inf`, `BODY_MARGIN = 0.0`, with the rationale above as code comments. `IdentityIndex` gained `body_match_threshold`/`body_margin` params; `_match_or_new` uses the body bar. Every unknown tracker track now opens its own cluster; cross-exit re-association happens through faces (a returning track is a fresh cluster that binds to the same player_id via `bind_face()`). Explicit body constants re-enable the merge mechanism (covered by unit tests). `PersonPipeline` needed no code change — it inherits the defaults.

Cluster spot check (real YOLO + OSNet, frames 8000-8300 every 2nd frame = 150 processed, face engine stubbed because clustering is face-independent; temp state only): 7 tracker tracks — with the borrowed 0.35 bar they collapse into **1 cluster** (the reported mega-cluster); with the calibrated defaults they form **7 clusters** (no body merge), and no `player_id` is set without enrollment. Unit suites after the change: `test_person_identity.py` 12 pass, `test_person_pipeline.py` 15 pass, `test_body_calibration.py` fast tests pass (2 real-footage tests skipped unless `POOL_BODY_CALIBRATION=1`).

## Info-complete gated event scan (2026-09-15)

`src/info_complete_scan.py` replaces motion-energy guessing with a design the owner specified: transient inference only on **info-complete (IC) frames** — no person intersecting the cloth (YOLO every 5th frame + hold), cloth area in band, exposure stable, ball census not falling below the recent mode. Shots/pots derive from diffs of temporally adjacent IC frames only; any occlusion break resets the pair.

Matching: stage 1 greedy same-color nearest within radius (slow balls); stage 2 same-color leftovers match at range **only when the color is genuinely unique in both frames** (the white class includes the cue ball and stripe whites, so counts > 1 are ambiguous). Shot = matched displacement ≥ 150 mm **and speed 0.5–11 m/s**, both endpoints on-table; pot = established ball (seen ≥ 3 consecutive IC frames, ≤ 2 simultaneous vanish, on-table position) absent through a persistence window, with position/color refractory suppression. All coordinates live in one 960×540 space with a self-estimated median-corner homography (the stored `scan30/corners.json` predates the per-axis scaling fix and is unsafe for full-res mapping).

**Full-scan result (27,001 frames at 15 fps, 9.8 min wall):** 806 IC frames (gate is deliberately strict: cloth band 15,797 / census 7,660 / person 2,672 rejections), 444 pairs → **22 shot candidates (2.4–8.9 m/s; 17 of 22 within 5 s of an old-scan shot time) and 19 pot candidates**, written to `out/scan-ic/events.json` + `stats.json` for human review. Cross-validation against the old motion scan is strong; recall is limited by the strict gate, and precision still needs the SAM3 confirmation stage before these become the review queue. 15 unit tests cover the gate, two-stage matching, and candidate contracts; full suite 159 tests green.

## Identity validation harness (2026-09-15)

`tests/live_identity_validation.py` runs the production `PersonPipeline` (face-binding-only mode: body clustering disabled; face bar match 0.35 / margin 0.12, quality eye >= 8px) over three ~60s windows of real footage (`data/vod_30min_260815.mp4`, 1280x720@30), every 2nd frame (901 sampled frames per window), with all mutable state in per-window temp dirs. The production `out/` tree is snapshotted before/after and verified byte-identical after the run (`production_out_untouched: true`); `out/pid_seed.json` is empty, the production face gallery is absent, so no `player_id` was ever set — this is the pre-labeling baseline.

Run: `.venv/bin/python tests/live_identity_validation.py --seconds 60 --centers 278,364,486 --out /tmp/identity-validation-20260915`

Windows were verified against real events in `out/scan30/events.json` (events strictly inside each window):

- W1 t=248-308s: shots at 255, **273 (verified)**, 281; pots linked at 255, 281.
- W2 t=334-394s: **343 (verified)**, 359, 372, 387 shots; pots at 343, 387.
- W3 t=456-516s: shots at 457, 474, 486.

Per window the harness emits a machine-readable report (`window-N-report.json`), a per-frame printed table (`window-N-frames.txt`), and a face-embedding sidecar (`window-N-face-embeddings.npz`): per sampled frame every tracked person with `track_id`, `cluster_id`, bbox and the face observation the pipeline used (`eye_px`, `det_score`, face bbox); per cluster a face-appearance signature (unique face instances, frames where faces were seen, eye_px/det_score ranges — e.g. W1 cluster 9: 64 faces across 250 frames, eye 9.7-14.7px); and the co-occurrence graph (which clusters were simultaneously present and how many frames they shared). The signatures are the evidence a human needs to label "cluster N = Player A" quickly.

Measured consistency numbers (bind bar 0.47 = threshold 0.35 + margin 0.12; metrics use unique face instances, deduped across stride-reused embeddings):

| Window | Same-cluster pairs | min | median | pairs below bar | Cross-cluster max | cross p95 | median | dup-attach pairs | Frames with persons / no quality face |
|---|---|---|---|---|---|---|---|---|---|
| W1 | 15318 | -0.07 | 0.78 | 1610 (10.5%) | 0.959 | 0.815 | 0.086 | 603 | 901 / 16 (1.8%) |
| W2 | 14438 | -0.12 | 0.663 | 2245 (15.6%) | 0.900 | 0.512 | 0.051 | 134 | 901 / 189 (21.0%) |
| W3 | 21118 | -0.11 | 0.699 | 3880 (18.4%) | 0.949 | 0.733 | 0.066 | 1047 | 901 / 11 (1.2%) |

Reading of these numbers, honestly stated:

- Cross-person separation matches the calibration (cross-cluster median 0.05-0.09), but per window a handful of cross-cluster pairs exceed the bar (max 0.90-0.96); each is stored in the JSON (`cross_pairs_above_bind_bar`) and printed as a `REVIEW` line by the summary — either a short duplicate tracker track (its single face instance near-identical to its parent cluster) or a candidate same-human re-entry. Separating these is human work, not automatic.
- A fraction of same-cluster pairs falls below the bind bar in every window (10-18%), concentrated in a few long-lived tracks (e.g. W1 clusters 3, 10, 11): evidence of identity switches by IoU association inside a single tracker track. Cluster-level min/median are in the per-window report; humans should label those clusters per face-instance, not per track.
- Face availability is high (no-face-with-persons ratio 1.2-1.8% in W1/W3) except W2 (21.0%) — that window's faces sit near the 8px quality floor, so fewer observations pass the quality gate. This ratio measures quality-gated binding evidence, not instantaneous detector recall (observations are reused between analyze strides).
- Latency: median 72.6 / 75.9 / 111.0 ms per processed frame (window medians), 226 face analyze calls per window on CPU.

**Shooter-association precision/recall remains UNMEASURED.** No human labels exist (`out/pid_seed.json` is empty). Precision/recall of associating identity clusters to shooters at shot events can only be computed after a human labels the clusters in at least one window using the per-cluster face-appearance signatures and co-occurrence data this harness produces; the harness exists to make that labeling fast. No src code was changed by this validation.
## SAM3 GPU deep investigation (2026-09-16, final verdict: CPU-only, binding fix improved CPU 3×)

Hardware: AMD Radeon RX 9070 XT (Navi 48/gfx1201). ROCm PyTorch 2.9.1+rocm6.4 verified working (HIP, matmul). YOLOv8n person detection on GPU verified (4 persons, ~26 ms warm).

**Root cause found and fixed (application level):** `vitdet.py` binds `from sam3.perflib.fused import addmm_act` at import time. In the server's import order, vitdet is imported BEFORE `sam3_cpu._apply_patches()` rebinds the module attribute, so vitdet kept the ORIGINAL bf16 fused kernel — which corrupts the fp32 CPU path on ROCm torch 2.9.1 (bf16 activations into fp32 weights) and degrades GPU runs. Fix: `_apply_patches` now rebinds BOTH `fused.addmm_act` AND `vitdet.addmm_act`. CPU SAM3 after the fix: **10 balls in 47.5 s** (previously 143.9 s — the plain fp32 replacement is also 3× faster than the bf16 fused kernel on this CPU).

**Remaining GPU failure (environment level, unfixable at application level):** with the binding fixed, every GPU configuration still returns 0 instances (bf16+autocast, fp32+MATH attention, fp32 with precision env flags). Traced to the first conv: fp32 patch_embed output on GPU diverges from CPU by 0.0218 max-abs, and the direct conv kernel test shows GPU fp32 conv error is 6e-6 (same as CPU) — so the divergence enters through the surrounding ops (rocBLAS/hipBLASLt "high-efficiency" fp32 GEMMs on gfx1201 run reduced-precision emulation by default; documented ROCm behavior, cf. PyTorch PR #188168). The amplified difference flips SAM3's presence head negative, dropping all instances. Precision env flags (TORCH_BLAS_PREFER_HIGH_PRECISION, HIPBLASLT_HIGH_EFFICIENCY_MODE=0, ROCBLAS_USE_HIGH_EFFICIENCY_MODE=0, cudnn.allow_tf32=False) did not change the outcome on ROCm 6.4 — revisit with ROCm 7.x when gfx1201 fp32 GEMM correctness ships.

Current wiring: `inference_device()` returns cuda for YOLO/table ops; SAM3 is pinned to CPU with a loader that refuses GPU (explicit error). The GPU SAM3 refusal message and this document supersede the earlier 'not supported' verdict; the blocker is ROCm 6.4 numerics on RDNA4, not PyTorch wiring.: AMD Radeon RX 9070 XT (Navi 48/gfx1201, PCI 1002:7550). Installed ROCm PyTorch 2.9.1+rocm6.4 + torchvision 0.24.1 (replacing the CPU builds); `torch.cuda.is_available()` is True and GPU matmul verifies. YOLOv8n person detection on GPU: verified 4 persons on vod30 frame 300, warm ~26–31 ms.

SAM3 zero-shot detection on the GPU returns **zero instances in every configuration tested** (CPU finds 10 balls on the same frame):

| Configuration | Result |
|---|---|
| bf16 weights + autocast, default attention | 0 instances |
| bf16 weights + autocast, MATH/EFFICIENT SDPA | 0 instances |
| fp32 weights, vendored autocast disabled | runs, 0 instances |
| fp32 weights, native eager position precompute | runs, 0 instances |
| fp32 + MATH attention | dtype crash (mixed) |
| CPU (verified baseline) | 10 balls, 144 s |

Vendored-code patches applied during the investigation (geometry-encoder prompt dtype alignment, decoder-FFN dtype guard) remain in the tree as no-ops on CPU. The loader now **refuses GPU for SAM3** with an explicit error rather than silently returning zero balls; `src/frame_inference.inference_device()` selects `cuda` for YOLO/table and `cpu` for SAM3. Root cause is most plausibly an immature ROCm 6.4 attention kernel for gfx1201 inside SAM3's detection head — an environment/compiler issue, not an application-level fix. Revisit when ROCm ships RDNA4 kernel fixes.

## Per-frame stage seam and the 30 fps envelope (2026-09-24 measured)

Requirement under test: near-real-time at **30 fps = 33.3 ms/frame end to end, decode included**. GPU present and used (`torch 2.9.1+rocm6.4`, `torch.cuda.is_available()` True, AMD Radeon RX 9070 XT).

### The seam

`annotator/pipeline_stages.py` is the whole framework: one method, one registry, one rolling window.

- **Contract** — a stage is any object with a non-empty `name`, an optional numeric `budget_ms`, and `process(frame, context) -> result`. `context.result(name)` returns an *earlier* stage's result for the same frame (a ball detector needs the cloth polygon the table stage already found; a stage that needs nothing ignores the argument). `context.seq`/`context.source` carry the frame identity.
- **Registry** — `StageRegistry(stages, clock)` runs stages in registration order, refuses duplicate names, measures each with the pipeline's own clock, and returns a `StageRun` (`results`, `timings_ms`, `total_ms`, `overrun_stage`, `overrun_ms`, `budget_ms`). Every stage of a frame still runs after an overrun: a half-measured profile of a late frame is worthless for deciding what to cut.
- **Default registry** — `table` then `person`, each calling `infer_frame` with its own detector list, merged by `merge_detections`. An injected `infer(frame, detectors, root)` is wrapped as a single `detect` stage, so the pre-existing metadata contract (`detections`, `inference_ms`) is unchanged.
- **Budget** — `frame_budget_ms` defaults to `1000/source fps` (33.33 ms at 30 fps). A frame is dropped, not published late, when a stage exceeds its own `budget_ms` or when the accumulated time (decode + scale + encode + stages) exceeds the frame budget. Nothing queues: the pending slot holds one frame, and a newer frame supersedes it.
- **Drop accounting** — `frames_skipped` stays the total, now partitioned into exactly three reasons on `status()['drop_reasons']`: `no_frame_ready` (the decoder superseded the frame before the worker took it), `stage_overrun` (budget blown), `stale` (already older than a frame period at pickup, or abandoned by stop/error). `frames_processed + sum(drop_reasons) == frames_received` holds at every point, and `status()['last_drop']` names the reason, the sequence and the offending stage.
- **Latency** — `LatencyWindow(120)` records `decode`, `resize`, `encode`, each stage, `receive_to_process`, `receive_to_result` and `inter_frame`, exposed as `count/p50/p95/max/last` on `status()['stages']` (registry order, with each stage's budget) and `status()['latency_ms']`. Percentiles are nearest-rank over the retained samples, not interpolated. All of it is additive on the existing `/api/live` payload; `frames_skipped`, `frame_age_ms` and `latest.*` are unchanged.
- **Ball detector seam** — register one stage; the decode loop is not touched:

```python
class BallStage(Stage):
    name = 'ball'
    budget_ms = 15.0                       # its own ceiling, or None for the frame budget
    def __init__(self, root): self.root = Path(root)
    def process(self, frame, context):
        cloth = context.result('table')    # the polygon the table stage already found
        return {'boxes': [...]}            # merged into detections.boxes in stage order

registry = StageRegistry(default_stages(['table', 'person'], root) + [BallStage(root)])
processor = LiveProcessor(root, stages=registry)   # or stages=[...] on the app path
```

### What was measured

Real VOD replay (no network): `data/vod_30min_260815.mp4`, 1280x720 at 30.0003 fps, seek to frame 8000, 90 frames per case, model warm (each case is run twice; the first run pays and discards the one-time YOLO load), real 30 fps pacing, budget enforced. `tests/live_envelope_run.py`, artifact `out/live-envelope/envelope.json`. The host was **shared** at the time (another worker's `src.tiny_ball_net` probe at ~108% CPU plus an Android emulator at ~218%); `loadavg` 30-33 on 12 cores during the reported run, recorded per case in the JSON. `person` and `table` run on the scaled 960x540 frame the pipeline has always used, so these are not the 720p ~26 ms figure.

| case (stage list) | decode p50 | resize p50 | encode p50 | table p50 | person p50 | ball p50 | envelope p50 | envelope p95 | published/90 | achieved fps | drops (nfr/overrun/stale) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `decode` (no stages) | 0.84 | 1.82 | 1.72 | — | — | — | **4.38** | 11.34 | 90 | 30.6 | 0/0/0 |
| `person` | 0.97 | 5.62 | 1.64 | — | 14.78 | — | **23.01** | 56.55 | 63 | 21.0 | 3/25/1 |
| `table+person` | 1.96 | 6.44 | 1.81 | 11.27 | 15.46 | — | **36.94** | 87.97 | 7 | 2.3 | 20/63/2 |
| `person+ball` (15 ms stand-in) | 1.58 | 6.05 | 1.72 | — | 15.26 | 15.07 | **39.68** | 82.18 | 1 | 0.3 | 20/68/2 |
| `tablecached+person+ball` | 1.99 | 6.72 | 1.77 | 0.00 (max 39.4) | 17.19 | 15.07 | **42.74** | 88.12 | 0 | 0.0 | 26/63/2 |
| `table+person+ball` (default + ball) | 1.72 | 6.70 | 1.80 | 11.82 | 15.66 | 15.08 | **52.78** | 110.50 | 0 | 0.0 | 37/53/1 |

`envelope = decode + resize + encode + sum(stages)`, p50 unless stated. The `ball` numbers are exact: `BallStandIn` sleeps 15 ms and never varies (`p50 15.07, p95 16.54, max 16.71`), so the pipeline's own accounting is verified against a known quantity.

### Verdict: 30 fps is NOT met with a 15 ms ball stage

- **No headroom for the ball detector at the current stage mix.** The cheapest observed non-ball envelope for `table+person` was 36.94 ms p50 in this run (22.92 ms in an earlier, quieter window at load 34-38) against a 33.33 ms budget; adding the 15 ms stand-in measures 52.78 ms p50 and drops **every** frame (37 `no_frame_ready` + 53 `stage_overrun`). Even the best case is 22.92 + 15.07 = 38.0 ms, i.e. ~4.7 ms over. The answer to "is there headroom" is **no**, and it is not close.
- **The pipeline only meets 30 fps when it has almost nothing to do.** With zero stages it publishes 90/90 at 30.6 fps (envelope 4.38 ms p50). The person stage alone leaves 10.3 ms of slack in this run and overshot on 25 of 90 frames (published 21.0 fps); the drop counters show the overshoot instead of hiding it as latency.
- **The table stage is the cheapest thing to remove.** It costs 11.27 ms p50 on every frame for a polygon that changes only when the table is re-covered; the cached variant (`recompute every 30 frames`, harness-local `TableEveryN`, public contract only) measures **0.00 ms p50, 39.4 ms once per 30 frames** — that is ~11 ms/frame returned to the budget. `person` alone measured 14.0 ms p50 in the earlier quieter window, so `person+ball` would be ~29 ms there — still only ~4 ms of slack, and the ball detector fits *only* if the static cloth comes off the per-frame path.
- **Recommendation:** take the cloth polygon off the per-frame path (cache or a slow lane), target the ball detector at ≤10 ms, and keep the budget enforced so an overshoot surfaces as a counted drop rather than as a lagging picture.
- **Drop behaviour proven, not just asserted:** with the synthetic 15 ms stage registered, all 90 frames were dropped and reported (see the table), no frame was queued, and `frames_processed + sum(drop_reasons) == frames_received`. `tests/test_live_processing_stages.py` pins this and the reason breakdown; `tests/test_pipeline_stages.py` pins ordering, context, percentile and budget semantics.

### Twitch live path: NOT reachable (no live-channel numbers)

The Twitch proof could not be produced; the VOD-replay table above is the evidence.

- The saved channel (`https://www.twitch.tv/examplechannel`, `out/corner-pocket/state.json`) and three further public channels all fail at resolution with the module's safe public error *"Twitch channel is offline or has no public playable stream"*.
- The failure is not a stale query hash: `twitch_source._TOKEN_HASH` is byte-identical to the persisted-query hash in current Streamlink `master` (`77777777777777777777777777777777…cdbe9`), and the `PlaybackAccessToken` GQL call returns a **non-null** token.
- The failing step is usher: `https://usher.ttvnw.net/api/channel/hls/<channel>.m3u8` answers `404 {"error":"Can not find channel"}` for that token, with and without a browser user-agent. Streamlink's only additional step is a client-integrity token (`Device-Id`/`Client-Integrity` headers, acquired by driving a headless browser), which this module refuses by design (no login, no ad filtering, no integrity bypass). Whether the channels are genuinely offline or Twitch now requires integrity for anonymous playback could not be distinguished from here without a live channel.
- Consequence: **`resolve_twitch` behaves correctly and safely** (no credential fallback, no token leakage, actionable message), but no live decode, receive-rate or drop number exists. Live latency therefore remains `upstream_delay_ms = None`, i.e. unmeasured, exactly as `docs/handoff.md` §4 states.

### What was not measured

- Glass-to-glass latency. `upstream_delay_ms` is still `None`; receive-to-result is local processing only.
- The real ball detector (it does not exist yet): its ~15 ms is an assumption, supplied as a stand-in stage.
- Anything on a quiet host: every number above carries a `loadavg` of 30-33 with two other tenants consuming ~3.5 cores of 12, and the CPU-side steps (resize, encode, pickup latency) are the ones that move with host load. GPU stage times were the stable ones.
- Multi-process/threaded partitioning, 60 fps sources, and a second camera. The budget machinery is per-frame and single-worker, so a 60 fps source would need `frame_budget_ms` 16.7 and would drop proportionally more.

## Static table, stage cadence, and the re-measured envelope (2026-09-24 measured)

Follow-up to the section above, which measured `table+person` at 36.94 ms on a host loaded to `loadavg` 30-33. Two changes came out of it, and both are now the pipeline's default behaviour rather than a harness case.

### 1. The static cloth quad is no longer measured per frame

`TableStage(root, dataset=…)` answers from `src.calib_segments.load(dataset, root)` — for vod30 the operator's `human_anchors` quad in `out/calib_vod30_segments.json` (one segment, t 0-1800 s, `frame_size` 1280x720) — resolved for the frame's time and scaled to the working frame. No detector runs on the normal path. `LiveProcessor` now carries the decoder's `CAP_PROP_POS_FRAMES` (replay only) and the source `fps` into the stage context so a per-segment reference can be resolved at all, and passes the source's `dataset` into `default_stages`. Without a saved reference (live streams have none) the quad is measured at most once every `table_measure_every_n` (default 30) frames and served from that measurement in between.

Measured effect: the table stage's cost fell from **11.27 ms p50 / 29.3 ms p95 per frame to 0.05 ms p50 / 0.09 ms p95** (saved reference, same VOD, same 960x540 working frame). `table+person` went from 36.94 ms to **14.95 ms p50** in the quiet window below. That is the largest single win available in this pipeline, and it was the first finding.

**Honest status contract.** Every published frame carries `metadata['stage_evidence']` — one entry per registered stage — and `metadata['source_frame_index']`; `status()['stages'][i]` carries `evidence`, `runs` and `skips`. The table stage reports `table_source` ∈ `saved:<segment id>` / `saved-clamped:<segment id>` / `measured`, `table_age_frames` (how old the geometry it served is) and `table_reference_size`. A consumer can therefore always tell a reference quad from a measurement, and how old it is. Serving last-known geometry is correct for a static camera precisely because the frame says so; a frame whose evidence is old is identifiable, not silent.

### 2. Per-stage cadence (`Stage.every_n_frames`)

A stage registered with `every_n_frames=N` runs on 1 frame in N. On the others it is **absent**: no `process` call, no result, no timing sample — so "did not run" can never be read as "found nothing" or as the previous frame's answer. Every frame still gets an evidence entry for every stage (`{'ran': False, 'age_frames': k}`, or `age_frames: None` if it has never run). The cadence is on `status()['stages'][i]['every_n_frames']` with `runs`/`skips` counters. The honest rule is unchanged and now enforced by construction: **missing evidence is unknown, never last-known-value.**

### The re-measured matrix (VOD replay, 90 frames/case, warm, budget enforced)

`tests/live_envelope_run.py --frames 90 --warmup 12`, artifacts `out/live-envelope/matrix-quiet-load4.json` and `matrix-loaded-load17.json`. `ball` is the **stand-in for a detector that does not exist yet** (`sleep(15 ms)`, exact in every run: p50 15.06, p95 15.1), so every conclusion below is provisional on that cost. `table` is the shipped saved-reference path. `result` is the measured `receive_to_result`; `env` is decode+scale+encode+Σ stage p50 (the worst-frame estimate, what the budget sees); `amort` divides each stage's p50 by its cadence (the sustained estimate).

**Run 1 — quiet host (another worker's probe and an Android emulator had just exited), `loadavg` 4.0-5.8:**

| case | load | decode | resize | encode | table | person | ball | env p50 | amort p50 | result p50 | result p95 | published/90 | fps | drops nfr/overrun/stale |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `decode` | 4.3 | 0.45 | 1.04 | 1.45 | – | – | – | 2.94 | 2.94 | 2.53 | 3.24 | 90 | 30.6 | 0/0/0 |
| `person` | 4.1 | 0.56 | 4.20 | 1.38 | – | 10.89 | – | 17.03 | 17.03 | 16.58 | 22.23 | 90 | 30.5 | 0/0/0 |
| `table+person` | 4.1 | 0.50 | 3.86 | 1.29 | 0.05 | 9.65 | – | 15.35 | 15.35 | 14.95 | 17.41 | 90 | 30.4 | 0/0/0 |
| `table+person+ball@1` | 4.0 | 0.51 | 3.89 | 1.30 | 0.05 | 9.68 | 15.06 | 30.49 | 30.49 | 30.23 | 37.10 | 82 | 27.6 | 0/8/1 |
| `table+person+ball@2` | 5.8 | 0.58 | 3.92 | 1.32 | 0.05 | 9.93 | 15.06 | 30.86 | 23.33 | 29.75 | 66.82 | 71 | 23.9 | 5/14/0 |
| `table+person+ball@3` | 5.3 | 0.55 | 3.82 | 1.31 | 0.06 | 9.93 | 15.06 | 30.73 | 20.69 | 15.97 | 33.35 | 86 | 29.2 | 0/4/0 |
| `person+ball@1` | 5.3 | 0.57 | 3.92 | 1.30 | – | 9.90 | 15.06 | 30.75 | 30.75 | 30.48 | 41.43 | 75 | 25.2 | 0/15/0 |
| `person+ball@2` | 5.0 | 0.56 | 3.88 | 1.30 | – | 9.89 | 15.06 | 30.69 | 23.16 | 29.37 | 36.35 | 85 | 28.6 | 0/5/0 |
| `person+ball@3` | 5.4 | 0.86 | 5.31 | 1.56 | – | 12.15 | 15.07 | 34.95 | 24.90 | 20.58 | 35.66 | 68 | 23.0 | 1/21/0 |

**Run 2 — 40 seconds later, same host, `loadavg` rising 6.6 → 17.1 (another tenant returned):** `decode` 9.38 ms p50, `person` 20.84, `table+person` 27.13 — the fixed cost alone approaches the 33.33 ms budget — and every ball configuration collapses (`table+person+ball@1` 0/90 published, `person+ball@1` 4/90, `person+ball@3` 59/90). `decode`/`person`/`table+person` still published 90/83/59 frames of 90.

### Which configuration meets which target

- **30 fps (33.33 ms), quiet host:** `decode` ✓ (2.5 ms), `person` ✓ (16.6 ms), `table+person` ✓ (15.0 ms), and every ball configuration **at the stand-in's 15 ms** — `ball@1` result p50 30.2 ms, `ball@2` 29.8 ms, `ball@3` median frame 16.0 ms with the ball-bearing frames at ~30 ms. All are inside the budget, but the ball-bearing frames leave only **~3 ms of margin**, which is exactly why the drop counts are 4-19 of 90 rather than zero: the p95 of those frames (33-41 ms) crosses the line under any scheduling jitter. `ball@3` shows the lowest drop count of the ball configurations (4/90) because two of three frames are ball-free.
- **15 fps (66.7 ms):** every configuration, in both runs (worst measured p50 65.8 ms: `table+person+ball@1` at `loadavg` 17).
- **Not met at all:** a loaded host. At `loadavg` ≈ 17 the CPU-side steps (decode/scale/encode and thread wake-up) grow 3-9×, and no configuration with the ball stage publishes usefully. The pipeline does what it promises — it drops and counts rather than lagging — but "near real time" on this box requires an unloaded host, or partitioning the CPU-side work away from the decoder.
- **Effective onset latency** (shot onset at t → the gate can call it). The gate (`src/shot_pot_gate.py`) needs `onset_intervals = 3` consecutive above-bar intervals, each interval's `dt ≤ max_gap_s = 0.25 s`, with the motion bar at 40 px/s. At cadence N the ball samples are N × 33.33 ms apart, so 3 intervals span 3·N·33.33 ms of *motion*; add the sampling phase (the first sample after onset lands on average N/2 frames later) and the last frame's processing (~30 ms at the 30 fps budget):

| cadence | interval dt | motion spanned by the 3 intervals | mean onset→call | worst-case onset→call | sustained (amortised) envelope |
|---|---|---|---|---|---|
| `ball@1` | 33.3 ms | 100 ms | ~147 ms | ~180 ms | 30.5 ms |
| `ball@2` | 66.7 ms | 200 ms | ~263 ms | ~300 ms | 23.3 ms |
| `ball@3` | 100 ms | 300 ms | ~380 ms | ~430 ms | 20.7 ms |

  The interval chain also bounds the cadence: `max_gap_s` 0.25 s allows at most **cadence 7** at 30 fps (7 × 33.33 = 233 ms; cadence 8 = 267 ms would break every run before it forms). And because a skipped frame carries `{'ran': False}`, the gate must treat those frames as *unknown samples*, compute `dt` from the samples' own timestamps, and never assume `dt = 1/fps`.

**Honest target for the owner's requirement:** with the stand-in's 15 ms, **30 fps is reachable on a quiet host with the ball stage at cadence 2-3**, at the cost of 0.26-0.38 s onset latency; `ball@2` (≈23 ms amortised, ~0.26 s onset) is the balanced choice. If the ball detector costs more than ~15 ms, or the host is shared (which is the normal state of this machine), the honest target is **15 fps with ≤0.4 s onset latency**, which every configuration measured here meets with room. Neither statement survives a detector that is slower than the stand-in: this is a measurement of the *envelope*, not of a detector that does not exist yet.

### What this section did not measure

- The real ball detector: 15 ms is an assumption. Its cost on GPU, its own warm-up, and its accuracy are all unknown, so the 30 fps conclusion is provisional.
- A quiet host for long: run 2 shows the same configuration collapsing when `loadavg` tripled, and the host is shared with other agents and (at the time of writing) an Android emulator.
- Twitch live: still unreachable for the reasons in the section above.
- Whether the shot/pot gate accepts cadence-partitioned samples: the arithmetic above is derived from the gate's constants, and the gate has not been run against a cadenced ball stream (its `_intervals` already derives `dt` from sample times, but that path is unexercised with gaps).

## The trained ball detector in the pipeline, and the first events it produces (2026-09-24 measured)

The stand-in is gone: `annotator/pipeline_stages.py` now carries the trained detector as a stage, the envelope has been re-measured with the real net in it, and the shot/pot gate has been run against five minutes of dense per-frame tracks.

### 1. `BallStage`: the detector behind the existing stage contract

`BallStage` loads the 960x540 round (`out/tiny_ball_probe/960x540-scratch.pt`, 300 train frames / 20 epochs, 204,529 params) at its measured operating point (threshold 0.425), lazily on the first frame, and answers through the same stage contract every other stage uses.

- **Result**: `{'balls': [{'x', 'y', 'score'}], 'boxes': []}` — positions in the *working frame's* pixels, so a consumer never has to guess which coordinate space a sample is in. Ball rows are deliberately **not** appended to `boxes`: the published box list is what the app draws, and injecting a detection class the app never asked for is a contract change nobody requested. `merge_detections` carries them as `detections['balls']` instead.
- **Absent, never stale**: on a frame the cadence skipped, the payload has **no `balls` key at all** and `stage_evidence['ball']` is `{'ran': False, 'age_frames': k}`. "Did not run" can never be read as "found nothing".
- **Evidence per frame** names what the result was made of: `ball_count`, `ball_threshold`, `ball_size`, `ball_stack`, `ball_stack_planes`, `ball_warm`, `ball_stack_span_frames`.
- **A missing checkpoint raises** `FileNotFoundError` naming the full path — never an empty result.
- **The stack is causal and says so.** The net trains on `(t-1, t, t+1)`; a live stream has only the past, so the stage feeds `(t-2, t-1, t)` (`ball_stack: 'causal'`). At `every_n_frames=N` the three planes span 2N source frames, reported as `ball_stack_span_frames` — a property of partitioning a temporal detector, not something to hide.
- **`ball` is requestable at runtime** (`live: let the ball stage be requested at runtime`): `LiveProcessor.start(source, ['table','person','ball'])`, with `ball_every_n` the caller's cadence (default 1 = every frame, mirroring `table_measure_every_n`). The start is **refused**, before any state is touched and before any thread exists, when the weights are missing or empty (naming `'ball'` and the expected path), when no ball stage would exist at all (the legacy `infer=` path), or for an unknown detector name. A pipeline that runs and quietly omits a requested stage is the failure this prevents. The GUI's live-detector row still lists table/person only; the API is ahead of the checkbox on purpose.

### 2. What the detector does on the held-out set — and what that set cannot say

`tests/ball_stack_ab.py`, artifact `out/tiny_ball_probe/stack_ab.json`. Same 47 held-out frames, same preprocessing code path as the stage, two stack layouts:

| stack layout | F1 | P | R | tp/fp/fn | median px | p90 px |
|---|---|---|---|---|---|---|
| centred `(t-1,t,t+1)` — what it trained on | 0.927 | 0.940 | 0.914 | 235/15/22 | 1.48 | 3.62 |
| causal `(t-2,t-1,t)` — what a live stream can feed | 0.923 | 0.933 | 0.914 | 235/17/22 | 1.45 | 3.73 |

The centred column reproduces the published operating point **exactly**, which is the check that the stage's own decode/resize/stack is the same function the probe measured — otherwise the causal column would be a comparison of two different pipelines. The cost of running the live layout is **−0.004 F1, identical recall, two more false positives**. The stack layout was never the problem.

Frame cost, split (median of repeated measurements, same host moment):

| piece | measured |
|---|---|
| forward pass, synced (`.cpu()` inside the timed region) | **24.6 ms** (min 14.0) |
| the stage **without** the forward: resize, 3-plane RGB stack, `/255`, peak search | **19.7 ms** (min 14.7) |
| the whole stage inside the live pipeline | **56.0-72.3 ms** p50 at `loadavg` 27-34 |

So ~20 ms of the stage is work that is not the CNN, and the envelope's 56-72 ms is that plus the forward plus load. The forward is 24.6 ms only when it is *synced*: timing `model(x)` alone measures ROCm kernel queueing (~1.5 ms) and is not a measurement of the forward. The earlier "23.5 ms inference-only" figure survives this check.

**The held-out set is a still-ball set.** Binning every labelled held-out ball by its own speed (1:1 nearest-first assignment to the neighbouring labelled frame, so a moving ball is not pinned to the stationary neighbour it passed):

| labelled speed | n | found | recall |
|---|---|---|---|
| < 40 px/s (the gate's motion bar) | 210 | 194 | 0.924 |
| 40-200 px/s | 4 | 4 | 1.0 |
| 200-600 px/s | 1 | 1 | 1.0 |
| > 600 px/s | 0 | — | — |

**5 of 215 labelled balls move faster than the gate's own motion bar; none exceeds 600 px/s.** The F1 0.927 is therefore a statement about finding *stationary* balls. It is not evidence that the detector holds a ball through a shot, and nothing in the held-out set can make it so. The five moving balls were all found — that is five samples, not a result. This is the largest caveat on every accuracy claim in this document.

### 3. The envelope with the real detector in it

`tests/live_envelope_run.py --frames 90 --warmup 10 --ball real`, artifact `out/live-envelope/matrix-real.json`. Host `loadavg` 27.0-28.0 (1-minute) throughout — the host was carrying other workers (SAM3 on CPU, a face scan of this same VOD, an HLS pull) and the stand-in matrix earlier in this document was measured at 4.0-5.8. **The absolute numbers below are load-inflated and are not comparable with that one**; `person`, which nobody changed, went from 9.65 to 19.59 ms p50 on load alone. What is comparable is the ball stage's own price and the shape of the collapse.

| case | load | decode | resize | encode | table | person | ball p50/p95 | env p50 | amort p50 | result p50/p95 | published/90 | fps | drops nfr/overrun/stale |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `decode` | 27.5 | 1.86 | 4.46 | 1.90 | – | – | – | 8.22 | 8.22 | 6.94/12.36 | 90 | 30.4 | 0/0/0 |
| `table+person` | 27.1 | 2.26 | 6.75 | 1.90 | 0.10 | 19.59 | – | 30.60 | 30.60 | 35.01/62.42 | 34 | 11.4 | 6/51/0 |
| `table+person+ball@1` | 27.0 | 2.13 | 6.27 | 1.71 | 0.09 | 13.97 | **56.0/91.4** | 80.20 | 80.20 | 100.98/128.66 | 0 | 0.0 | 64/25/2 |
| `table+person+ball@2` | 26.9 | 2.46 | 6.56 | 1.86 | 0.10 | 18.13 | **61.4/76.5** | 90.48 | 59.80 | 71.81/118.54 | 5 | 1.7 | 41/44/2 |
| `table+person+ball@3` | 28.0 | 3.05 | 8.38 | 2.48 | 0.12 | 28.08 | **72.3/122.3** | 114.42 | 66.21 | 77.00/166.81 | 1 | 0.3 | 49/40/1 |

Every ball configuration collapses where the stand-in's fit. For reference, the stand-in's own matrix (15.06 ms, `loadavg` 4-5.8, earlier in this document) published 82/71/86 frames of 90 at `ball@1/@2/@3` with envelopes of 30.5/30.9/30.7 ms. The real stage is 56-72 ms where the stand-in was 15.06, and discounting the ~2x load inflation gives ~28-36 ms — still 2x the stand-in. The stage cost breakdown in section 2 says where that goes.

**Onset latency, with the real per-frame cost** (the gate needs `onset_intervals = 3` consecutive above-bar intervals; `dt` = cadence x frame period; the sampling phase is how long after the onset the first sample lands; the last frame still has to be processed):

| cadence | interval | motion spanned | + phase | + ball processing (p50/p95) | mean onset->call | worst onset->call |
|---|---|---|---|---|---|---|
| `ball@1` | 33.3 ms | 100 ms | 16.7 ms | 56.0 / 91.4 ms | **173 ms** | 225 ms |
| `ball@2` | 66.7 ms | 200 ms | 33.3 ms | 61.4 / 76.5 ms | **295 ms** | 343 ms |
| `ball@3` | 100 ms | 300 ms | 50.0 ms | 72.3 / 122.3 ms | **422 ms** | 522 ms |

**The finding that matters more than the collapse: cadence cannot rescue a stage that costs more than the frame budget.** A partitioned stage runs on 1 frame in N, but the frame it runs on pays the whole cost, and the pipeline drops any frame whose stages push it past the budget. With a 33.33 ms budget and a 45-60 ms ball stage, *every ball-bearing frame overruns*: cadence N reduces the amortised rate (the `amort p50` column) without touching the peak. `ball@1` is the clean demonstration — its 25 frames that ran the ball stage were all counted as `stage_overrun`, and the case published **0 of 90** frames; the 5 frames `ball@2` did publish were frames its cadence skipped. To publish a ball result at 30 fps the stage must cost roughly <=25 ms wall including its own preprocessing; at 15 fps (66.7 ms) the budget reaches ~55 ms and this stage, at 45-60 ms, is still marginal. The honest summary: **the detector does not fit this pipeline's real-time envelope at either target on this host, and the binding constraint is peak per-frame cost, not the average.**

The definitive re-measurement in a genuinely quiet window is still deferred: the host sat at `loadavg` 24-43 for the whole of this session, and a 45-minute wait for `loadavg < 8` expired without one. What did happen at the end of that wait is the next best thing, and it changes how the table above should be read.

**The same-load pair.** With the wait expired, both matrices were run back to back in the same window — real then stand-in, no wait between them (`out/live-envelope/matrix-real-quiet.json`, `matrix-standin-quiet.json`) — so the two are measured under one load instead of against a load-4 row from the previous session:

| case | real: ball p50/p95 | stand-in: ball p50/p95 | real published/90 | stand-in published/90 | real load | stand-in load |
|---|---|---|---|---|---|---|
| `table+person` | – | – | 35 | 8 | 40.8 | 36.9 |
| `ball@1` | 60.3/117.5 | **15.2/16.9** | 0 | 0 | 40.8 | 37.6 |
| `ball@2` | 52.2/73.5 | **15.1/16.0** | 4 | 3 | 39.3 | 37.2 |
| `ball@3` | 59.9/98.4 | **15.1/17.2** | 9 | 5 | 39.5 | 37.2 |

Three things follow, and the second one corrects the impression the load-27 table gives on its own:

1. **The detector's price is 3.5-4.0x the stand-in's, and that is a property of the detector, not of the load**: 52.2-60.3 ms p50 against an exact `sleep(15 ms)` at 15.1-15.2 ms, on the same host, minutes apart. The p95 gap is wider still (73.5-117.5 ms vs 16.0-17.2 ms).
2. **The published counts in this pair carry no information about the detector.** `table+person` — no ball stage at all, nobody's change — scattered from 35/90 to 8/90 between the two passes. At `loadavg` ~38 even the *stand-in's* envelope (47.9-55.3 ms) is past the 33.33 ms budget, so the ball-bearing frame is dropped whichever detector is in it. Reading the load-27 table as "the real detector caused the collapse" would be wrong: at this load the pipeline is in a regime where the detector's cost barely moves the outcome.
3. **Onset latency at one load, both detectors**: real 177/286/410 ms (`ball@1/@2/@3`) against stand-in 132/248/365 ms. The difference is exactly the ball stage's measured processing time (+45/+37/+45 ms), which is the sanity check that the arithmetic in the table above is measuring what it claims.

So the detector-specific claims rest on the stage cost breakdown in section 2 (24.6 ms forward + 19.7 ms of the stage's own work) and on this pair, not on the drop counts; the 30 fps question cannot be settled until the host is quiet and the whole matrix can be re-run at 4-6.

### 4. Five minutes of dense tracks, and the first shot/pot events this project has measured

`tests/ball_dense_events.py --start 1350 --seconds 300 --cadence 2`, artifact `out/dense-events/segment-1350-1650.json`. The segment is **t 1350.0-1650.0 s of `data/vod_30min_260815.mp4`** (frames 40500-49499), chosen as the busiest 300 s of the VOD by the sum of the scan's motion signal; it contains held-out frames (1363-1366, 1530, 1650) as well as training ones. The chain is the production one end to end: the same stage registry `LiveProcessor.start(source, ['table','person','ball'])` builds (`table` @1, `person` @1, `ball` @2), then `src/ball_census.associate` on the per-frame detections, then `src/motion_scan.probe_pair` for the occlusion channel, then `src/shot_pot_gate.classify` with the verified human-anchor cloth quad (`out/calib_vod30_segments.json`; identical to the gate's own `VOD30_REFERENCE_QUAD`, checked) scaled to the working frame.

**Track shape — the thing that has to be readable before any event claim is.**

| quantity | measured |
|---|---|
| frames decoded / expected | 9000 / 9000 |
| ball stage runs (cadence 2) | 4500 of an expected 4500 — cadence decay, exactly as designed |
| ball detections | 19,534 (4.34 per sampled frame) |
| identities | 248 (211 with >=2 samples, 37 singletons) |
| median identity length | 8.5 samples / **0.93 s** (max 1381 samples / 104.7 s) |
| sample spacing | 66.7 ms (= 2 x 33.33 ms), no gaps from load |
| interval speed | median **0.3 px/s**, p90 11.5 px/s, max 809.1 px/s |
| intervals above the 40 px/s motion bar | 974 of 19,286 |
| frames with a person inside the cloth quad | 7,427 / 9,000 (**82.5%**; 7,529 had any person box; the largest single box covered 79.8% of the quad) |
| `occ_dense` >= 0.30 (the occlusion channel's own bar) | **15.1%** of frames (p50 0.016, p90 0.423, max 0.985) |

Two things to read off that table. The tracks are **dense in time** (66.7 ms spacing, no load-induced gaps — the offline pass discards no frame) but **fragmented in identity** (median 0.93 s per identity, 248 of them for roughly ten balls). And the occlusion channel is far more conservative than "a person is present": a person covers part of the cloth in 82.5% of frames, but the 61x61 px densest-change window only clears its 0.30 bar in 15.1%.

**The gate's verdict** (721 rejections, every one with its code, samples and thresholds):

| verdict | count |
|---|---|
| **shots** | **3** |
| pots | 0 |
| unknown disappearances | 0 |
| rejections | 721 |
| onset groups | 3 (each 1 identity; **0 breaks** — a break needs >=3 simultaneous identities) |

**The three shots.** A ball at rest for seconds, then a sustained run above the motion bar — the first measurement-backed shot detection in this project:

| onset t | identity | rest before | peak speed | duration | path | direction | ends |
|---|---|---|---|---|---|---|---|
| 1482.25 s | `t129-white` | 1.67 s / 25 intervals (max 3.99 px/s) | 303.6 px/s | 0.267 s | 80.6 px | 249.8 deg | 136.6 px from a pocket, open cloth |
| 1580.12 s | `t193-blue` | 9.73 s / 146 intervals (max 2.99 px/s) | 491.6 px/s | 0.733 s | 159.9 px (net 159.1) | 197.9 deg | 29.4 px from a pocket, then the track ends (`endless_roll`) |
| 1621.52 s | `t265-blue` | 1.80 s / 27 intervals (max 3.80 px/s) | 301.7 px/s | 0.200 s | 59.9 px | 347.9 deg | 156.6 px from a pocket, open cloth |

**These three events are machine-produced and unconfirmed by a human.** They are the output of `src/shot_pot_gate.py` on tracks from a detector whose own accuracy is measured against a teacher (section 5), on a segment inside that detector's training time range. They satisfy the rules and carry their evidence; nobody has watched the footage at those three timestamps and said "that is a shot". Treat them as the first measurement-backed candidates, not as verified events.

**Why no pots, in the gate's own codes.** The pot rule's precondition is a disappearance near a pocket that does not come back; the tracks never deliver one:

| rejection code | n | what it means here |
|---|---|---|
| `disappeared_outside_pocket` | 170 | identities ended on open cloth: median 89.9 px from the nearest pocket (11 within 20 px, 37 within 40 px, 76 within 80 px) |
| `reappeared_after_gap` | 162 | identities came back after 0.5-2.0 s (median 0.9 s) — a gap, not a pot |
| `motion_too_short` | 157 | 114 bursts lasted **one** interval, 43 lasted two (median burst 63.8 px/s): above the bar, but not the 3 consecutive intervals `onset_intervals` demands |
| `no_motion_onset` | 79 | genuinely still: median peak interval speed 5.0 px/s |
| `track_too_short` | 74 | fewer than 3 samples: no interval pair at all |
| `no_still_stretch` | 73 | tracks that start already moving (median peak 125.6 px/s) yield no rest window |
| `left_cloth` / `roll_without_pocket` / `track_ends_at_window_end` | 2 / 2 / 2 | off the cloth; rolled to the end still on it; ends where the data ends |

**The occlusion channel was not the blocker.** Not one pot event was produced — not even an `unknown` one — so no verdict in this run depended on the occlusion channel at all: every disappearance was rejected on geometry first (outside the pocket radius, reappeared after a gap, or the window ended). That is the opposite of the expected failure mode, and worth stating plainly: with 162 identities reappearing after a median 0.9 s gap and 170 ending more than 40 px from any pocket, the dominant defect is **identity fragmentation**, not occlusion. `TRACK_MATCH_PX = 30` in the associator plus the detector's own dropouts on a fast or partly covered ball split one ball's path into several identities, so a potted ball is not seen to disappear near a pocket: it is seen to stop being detected mid-cloth and then reappear, or to be replaced by a new identity.

**Load diagnosis, so a sparse result cannot be misread.** Host `loadavg` was **35.5/33.0/23.5 at the start and 34.1/33.4/29.8 at the end** of this run, which makes two different sparsities worth separating:

- *Cadence decay*: the ball stage ran 4500 of 4500 expected samples (1 frame in 2). Predicted by `--cadence`, independent of load.
- *Budget drops*: **4,779 of 9,000 frames exceeded the 33.33 ms budget** (4,239 attributed to the ball stage, 539 to `person`, 1 to `table`). At this load a *live* run of this very configuration would have published almost nothing. This offline pass counts the overrun and keeps the frame, so **the tracks above contain every frame a live run would have thrown away** — their sparsity is cadence and detector behaviour, not a busy box. Wall clock: 846 s (10.63 fps offline); per-step p50/p95: decode 2.1/7.0, resize 8.1/17.1, occlusion 18.9/36.9, `person` 17.2/35.5, `ball` 63.1/94.7, table 0.09/0.15 ms; accounted 842.4 s of 846.4 s.

The live pipeline's own partition invariant (`frames_received` = published + dropped, one reason each, reasons `no_frame_ready` / `stage_overrun` / `stale`) is not exercised by this offline pass, which has no receive/process/drop split: it decoded 9000 frames and processed 9000. That invariant is unchanged by any of this work and is pinned by `tests/live_processing_stages.py`.

### 5. What this does not establish

- **The detector's F1 is measured against SAM3, which is a teacher, not ground truth.** 15 of its held-out detections have no label at all, and the disagreement report's own reading is that they are either student false positives or teacher misses. Nothing here resolves them; only eyes can.
- **The held-out set is 96% stationary balls** (section 2), so the F1 does not cover the case the gate cares about — a ball in flight. The dense run is the only evidence about that case, and it is indirect: 4.34 balls per sampled frame, 974 intervals above the motion bar, and at least one 159 px burst sustained for 0.73 s.
- **No human has verified the three detected shots.** They satisfy the gate's rules and carry their rest stretch, peak speed and sample list; that is all that can be said. The 5-minute segment is also inside the detector's *training* time range, so these tracks are the detector at its best, not at its generalisation limit.
- **No pot was detected, and the reason is structural rather than a threshold away.** Getting pots out of this footage needs identity persistence through a fast mover and through a player crossing the cloth — an association or detector problem, not a `pocket_r_mm` problem. `src/shot_pot_gate.py` was not changed at all for this measurement.
- **The real-time envelope is not met.** Both the collapse at `loadavg` 27-41 and the peak-frame-cost arithmetic point the same way: ~45 ms of stage cost against a 33.33 ms budget. The 20 ms of that which is not the CNN (resize + RGB stack + `/255` + peak search) is the cheap half to attack next; the identity fragmentation is the other. What is *not* established is the exact quiet-host number: the same-load pair above says the detector is 3.5-4x the stand-in, and the stage breakdown says what the 45 ms is, but nobody has yet run the matrix at `loadavg` 4-6 with the real detector in it.
- **Twitch live remains unverified** for the reasons in the section above; nothing here was measured on a live stream.

### 6. The declared quiet window, and the plain statement that it never arrived

The owner declared the window after the heavy lines (SAM3 false-positive audit, HLS replay, face scan, training, dense run) finished. The protocol was: sample `loadavg` once a minute for up to 20 minutes, start when it drops below 8, otherwise run anyway and say so. **Samples 1-20 ran at 23.21, 25.82, 22.37, 25.30, 29.84, 27.42, 25.69, 25.46, 25.27, 34.11, 35.61, 35.61, 35.28, 35.63, 32.89, 41.82, 39.43, 40.42, 45.25, 57.81 — the load rose monotonically and the window never arrived.** The runs themselves then ran at **`loadavg` 61.2-73.5**, the highest of the session, because the still-active UI-round worker started its browser fixtures (`serve_workbench_fixture.py`, four `chromium` processes, node coverage runs) during the wait. This is not a quiet-host measurement and must not be quoted as one; it is a third, more loaded replicate of the same-load comparison.

Both passes were still run back to back, so the pair is at least internally consistent. Artifacts: `out/live-envelope/matrix-real-quiet.json` and `matrix-standin-quiet.json` (**these hold the load 61-73 pass**); the earlier pair at `loadavg` 37-41 is preserved as `matrix-real-load39.json` / `matrix-standin-load39.json` and is the better same-load comparison of the two.

| case | real published/90 | real ball p50/p95 | stand-in published/90 | stand-in ball p50/p95 | real env p50 | stand-in env p50 | real r2r p50 | stand-in r2r p50 | real onset | stand-in onset | load real / stand-in |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `decode` | 90 | – | 90 | – | 14.06 | 13.84 | 12.55 | 11.78 | – | – | 62.2 / 73.5 |
| `table+person` | **0** | – | **18** | – | 46.77 | 33.73 | 63.28 | 40.50 | – | – | 63.4 / 61.2 |
| `ball@1` | 0 | 65.1/133.1 | 0 | **15.1/16.1** | 102.57 | 63.96 | 114.90 | 79.62 | 182 ms | 132 ms | 63.3 / 64.6 |
| `ball@2` | 0 | 109.5/198.7 | 3 | **15.2/17.1** | 197.22 | 60.92 | 150.53 | 66.24 | 343 ms | 249 ms | 64.0 / 65.9 |
| `ball@3` | 2 | 84.0/185.5 | 0 | **15.1/17.4** | 165.54 | 70.72 | 126.61 | 79.67 | 434 ms | 365 ms | 64.0 / 65.6 |

What this pass adds, stated so it cannot be over-read:

- **The ball stage's price ordering is stable across loads: 4.3x, 7.2x, 5.6x the stand-in at `loadavg` 63-66, against 3.5-4.0x at 37-41.** The stand-in is a `sleep(15 ms)` and stays at 15.1-15.2 ms in every pass; the real stage tracks the host, which is what a stage that is ~20 ms of CPU memory traffic plus a GPU forward does under CPU contention.
- **Nothing publishes at this load even with no ball stage in the frame**: real `table+person` 0/90 with `person` p50 30.7 ms, stand-in `table+person` 18/90 with `person` p50 21.0 ms. That is the same finding as the load-39 pair, one load band further out: at this contention the pipeline's drops are dominated by the frame's *fixed* cost, and the detector's share of the budget is not what decides whether a frame goes.
- **`decode` is unaffected** (90/90, 30.3-30.5 fps, envelope 13.8-14.1 ms) — the decoder paces the source and the drops come from the worker side, which is the correct behaviour.
- **Onset latency at this load**: real 182/343/434 ms against stand-in 132/249/365 ms, the difference again being exactly the ball stage's processing time (+50/+94/+69 ms).

The quiet-host number remains **unmeasured**. Everything the detector-specific claims rest on — the 3.5-4.0x price, the ~45 ms composition, the peak-cost argument — comes from the load-39 pair and the stage-cost breakdown in section 2, both of which are internally consistent and neither of which is a quiet-host figure.

### 7. Plan: getting the `ball` stage under the frame budget (written, not built)

**The budget is ~18 ms, not 25 ms.** On the quietest measurement in this document (the stand-in matrix at `loadavg` 4.0-5.8) a `table+person` frame costs **15.35 ms p50** — decode 0.50 + resize 3.86 + encode 1.29 + table 0.05 + person 9.65. The ball stage therefore has **33.33 - 15.35 = 17.98 ms** to fit a 30 fps frame at all, and less than that to fit with margin for jitter. A 25 ms stage still overruns the frame; the target is `<=15 ms` to be safe at cadence 1.

**What the ~45 ms is made of, and one gap in the measurement.** Two pieces are timed: the stage without the forward **19.7 ms** (per-call resize, 3x `cvtColor` BGR->RGB, `np.concatenate`, `astype(np.float32)` and `/255`, then `pick_peaks`), and the synced forward **24.6 ms**. Two pieces are in *neither* number, because both are built outside the timed regions: `np.ascontiguousarray(stack.transpose(2, 0, 1))` (an 18.7 MB HWC->CHW copy inside `heatmap`) and the`.to(device)` host-to-device copy of that same 18.7 MB. The live loop measures the whole thing at 52-60 ms at `loadavg` 38, which is consistent with the unmeasured pair being real work. **Any optimisation must be verified with a harness that times the whole `process()` call**, or it will move cost from a measured column into an unmeasured one.

Candidates, ranked by saving-per-risk:

1. **Build the network input directly in CHW float, once, into a preallocated buffer.** One `cvtColor` per frame instead of three (consecutive calls currently re-convert the same two frames), fill a persistent `(9, H, W)` float32 buffer in place, no `concatenate`, no `astype`, no separate `/255` pass, no `transpose`+`ascontiguousarray`. Removes three full passes over ~19 MB, leaves one write pass. **Expected saving 15-20 ms** (19.7 -> ~5, plus the untimed transpose copy -> ~0). **Numerically identical, and it has to be bit-identical by construction**: cast each uint8 plane to float32 (exact), then `np.divide(plane, 255.0, out=buffer[k], ...)` so the division stays float32; a reciprocal multiply or a uint8/double promotion would shift the last bit and make "identical" a hope rather than a check. **Risk: low** — pure data movement.
2. **Keep a persistent device tensor and send uint8 planes instead of the 18.7 MB float tensor.** H2D traffic drops 18.7 -> 1.6 MB per frame and the float expansion happens on device. **Expected saving 4-8 ms. Risk: low-medium** (device buffer lifetimes inside a stage that currently has none; assumes the copy is the cost, which this ROCm box has not been shown to be).
3. **Replace the peak search** (`cv2.dilate` 5x5 over the whole 960x540 heatmap, `np.argwhere`, then a Python NMS loop) with a GPU `max_pool2d` + threshold mask, or a threshold-first ROI dilate. **Expected saving 3-6 ms** (estimated, not split out inside the 19.7 ms). **Risk: medium — it changes which peaks survive NMS, so it needs the held-out sweep, not just a timing run.**
4. **fp16/bf16 forward.** The input is 18.7 MB of float32 per frame for a 204k-parameter net, so the forward is activation-bandwidth-bound. **Expected saving 5-10 ms. Risk: high for accuracy** — the heatmap values move, peaks near the 0.425 threshold can flip, so it requires the full 38-point held-out sweep, a re-chosen operating threshold and a fresh p90 localisation, not a wall-clock comparison.
5. **Drop the ball stage's working resolution to 640x360** (the box pipeline keeps 960x540). Everything scales by 0.44: ~45 ms -> **~20 ms**, which fits with margin. **Risk: high, and it is a different detector round.** The only 640x360 measurement that exists is old and weak (193 labelled frames / 1062 instances, 116 train frames, best F1 **0.811** at threshold 0.1, p90 4.48 px, in `out/tiny_ball_probe/probe.json`), so it must be retrained on the current 300-frame label set and re-measured (`src/tiny_ball_net.py rounds --plan 640x360:20`) before anyone quotes a number for it. It is the only single change that reaches the budget outright.

**Order and the honest end state.** (1) alone takes the stage from 52-60 ms to roughly 33-40 ms — still over. (1)+(2) to roughly 28-32. (1)+(2)+(3) to roughly 25-28. Only (1)+(2)+(3)+(4), or (5), lands at or under **18 ms** with margin. Two of the five change what the detector outputs (3 the peak set, 4 the heatmap) and one changes the model itself (5); all three need the held-out columns re-run, and (1) and (2) must reproduce the current numbers **exactly** or they are wrong rather than merely slow or fast.

**Verification, with what already exists.** `tests/ball_stack_ab.py` gives the held-out truth in about 90 s: the centred column must still read F1 0.927 / P 0.940 / R 0.914, tp/fp/fn 235/15/22 at threshold 0.425 for (1) and (2), and a full re-sweep is the tool for (4). The same file's `stage_cost_ms` times the stage with the forward stubbed and needs one addition — timing the transpose and H2D pieces too — so the 19.7/24.6 split stops hiding them. `tests/live_envelope_run.py --ball real` gives the live frame's p50/p95, published/90 and drop reasons at the chosen cadence. And `tests/ball_dense_events.py` re-runs the 5-minute segment through the gate, which is the only end-to-end guard that an "numerically identical" optimisation really is one: the same 3 shots at t=1482.25 / 1580.12 / 1621.52 with the same 721 rejection codes is the pass condition, not a faster clock.

## Live broadcast on the owner's channel (2026-09-26 measured, while it lasted)

The owner's channel was live, so for the first time the live path was tested against a real broadcast rather than a VOD replay. Everything below is a real measurement on `https://www.twitch.tv/examplechannel` (the only saved source in `out/corner-pocket/state.json`), taken from a Python shell, the production API on `127.0.0.1:8130`, and a read-only browser session. Two bugs were found and fixed; one design limit was found and is **not** fixed (see the last part).

### Reachability (the live path works; it was the channel that was offline before)

`annotator.twitch_source.resolve_twitch('https://www.twitch.tv/examplechannel')` → media playlist on `usw23.playlist.ttvnw.net` (a later call resolved `usw22`), **1280x720 @ 30.0 fps**, first frame in 0.02 s. The playlist is unambiguously live: `#EXT-X-TWITCH-ELAPSED-SECS:4778.4` (stream up ~79.6 min), `#EXT-X-MEDIA-SEQUENCE:2498`, `#EXT-X-TARGETDURATION:6`, **no `#EXT-X-ENDLIST`**. So the earlier `404 {"error":"Can not find channel"}` was an offline channel, not a broken resolver: today the same call succeeds.

### The production session, driven exactly as the Vision UI does

`POST /api/live {"action":"start","source":{"kind":"twitch","source_id":"77777777777777777777777777777777…"},"detectors":["table","person"]}` with `Origin: http://127.0.0.1:8130` (matching `liveAction()` in `annotator/ops.js`), then `GET /api/live` every 2 s for 200 s (`out/live-test/live-session.json`).

| what | measured |
|---|---|
| frames received / processed | 5495 / 380 (**1.9 published fps**), `no_frame_ready` 5102, `stage_overrun` 13, `stale` 0 |
| partition invariant | **holds** (380 + 5115 = 5495) |
| `receive_to_result` p50 / p95 / max | **19.87 / 29.77 / 44.61 ms** — inside the 33.33 ms budget at p50 **and** p95 |
| `decode` p50 / p95 / max | 0.40 / 2.04 / **1942.6 ms** — bursts through buffered segments, then blocks for the next one |
| `inter_frame` p50 / p95 | 0.41 / 2.05 ms — frames arrive in bursts, not at 30 fps |
| `resize` / `encode` p50 | 4.24 / 1.56 ms |
| `table` p50 / p95 / max | **0.01 / 0.02 / 12.14 ms** (`table_source: measured`, `table_age_frames` ≤ 21) |
| `person` p50 / p95 / max | 10.64 / 14.93 / 16.92 ms |
| `frame_age_ms` during the run | 280 ms → 1933 ms, swinging with each burst |
| detections on the published frames | 4 person boxes (scores 0.72-0.89), a table polygon, no ball stage in the detector list |

The session then **died twice, reproducibly**, at ~200 s and at ~4 min, with `state: error` and the exact message `Live stream ended or read timed out; restart to reconnect` (received 5495/633, processed 380/45). That is a decoder read timeout, not the stream ending: the stream was still live afterwards (resolved again successfully, `#EXT-X-TWITCH-ELAPSED-SECS` still advancing).

### The UI, read-only (screenshots in `out/live-test/`)

`agent-browser` (0.38.1, run from the local bun cache — the `~/.local/bin/agent-browser` symlink is broken on this host) against `http://127.0.0.1:8130`, `location.origin === 'http://127.0.0.1:8130'` asserted before anything else. No production state was written; only the Vision tab was opened.

| check | result |
|---|---|
| live frame on the stage | ✅ `img[src^="blob:"]`, natural 1280x720, parent `.stage` |
| MODEL boxes dashed | ✅ 3 person rects in group `o-src model` with computed `stroke-dasharray: 10px, 7px`, green stroke. (Attribute-based checks see nothing here — the dash comes from CSS, which is why `getComputedStyle` is the right test.) |
| live state text, EN | `live · seq 390 · frame age 359 ms · receive-to-result 24 ms · cloth 0 · balls 0 · persons 3 · pockets 0 (quad rejected)` |
| live state text, 中 | `直播 · seq 633 · 帧龄 1.8 s · 接收到结果 27 ms · 台呢 0 · 球 0 · 人物 3 · 袋口 0 (四边形被拒绝) · 锚点 0 · 事件 0 · 模型四边形偏离已保存角点 · 叠加层 开` |
| facts line | present, bilingual, carries frame age and receive-to-result — the honest numbers the earlier section asked for |
| no dataset layers over the live frame | ⚠️ the *pocket* markers (`u-pocket` + `o-src model` groups, `MODELtop-left…right-middle`) are drawn over the live frame and **do not move** (identical coordinates 6 s apart) — they are the saved-anchor projection, i.e. dataset/calibration geometry over live video. The 50-rect SVG present before the live frames arrived is that layer, not a person layer |
| chat panel / Twitch embed | there is **no `<iframe>` in the DOM** at all while the live session runs (0 iframes), so nothing loaded and no `parent=` frame error could occur; no console error either way |
| console errors | none (`agent-browser errors` empty) |
| screenshots | `live-vision-en-1280.png`, `live-vision-en-1280-live.png`, `live-vision-zh-1280.png`, `live-vision-zh-390.png`, `live-vision-en-390.png`; live frames `live-frame-01..03.jpg`; session data `live-session.json`; fix verification `verification.json` |

### Detection sanity and upstream delay on real live frames

- **People**: on `live-frame-02.jpg` the detector reports **4 person boxes** while **5 people are clearly visible** in the wide shot (left with cue, left-centre, leaning at the back, right-centre at the table, far right) — one person missed. The boxes it does return are tight and plausible (scores 0.72-0.89).
- **Table quad**: on live frames there is no saved reference (live has no dataset), so the stage measures it on its 30-frame cadence (`table_source: measured`, `table_age_frames` ≤ 21, p50 0.01 ms, 12 ms at each refresh) and the app then **refuses** the measured quad against the saved anchors — the facts line says `pockets 0 (quad rejected)` / `袋口 0 (四边形被拒绝)` and `模型四边形偏离已保存角点`. The label is honest: the quad exists in the API metadata (`table_polygon: true`) but is not drawn or used, and the UI says why.
- **Ball stage**: not offered on the live detectors list (`['table','person']`), so no live ball fps comparison was possible — no detector, nothing to time.
- **Upstream delay** (broadcast → our receive), from two probes of the HLS media playlist comparing the newest segment's `#EXT-X-PROGRAM-DATE-TIME + #EXTINF` against our wall clock: **0.308 s and 1.367 s**. Caveat: `PROGRAM-DATE-TIME` comes from the broadcaster's/encoder's clock, so this measures *playlist age*, not verifiably the true broadcast lag; a wrong encoder clock moves this number with it. Combined with the measured `receive_to_result` p50 19.9-20.9 ms, approximate **glass-to-result ≈ 0.33-1.4 s**. `upstream_delay_ms` in the status payload is still `None`; the number above is measured externally, as instructed.

### Sample kept for offline re-testing

`data/live-samples/examplechannel-20260926T081051Z.ts` — `ffmpeg -c copy` of the live stream, **665.2 s (11 min 5 s)**, 1280x720 h264 30 fps + aac, **274.7 MB** (ffprobe-verified; `data/` is gitignored and was not committed). It exists so the live path can be re-tested through the VOD-as-live source (`annotator/twitch_vod_source.py`) after the stream ends, with the same pacing semantics.

### Two bugs found and fixed (`4a9654b`)

1. **A live segment gap was fatal.** `_capture()` used a 2 s `CAP_PROP_READ_TIMEOUT_MSEC` for every source. A live HLS stream delivers a segment every 2-6 s, so a normal gap between segments surfaced as `read` returning false and `_fail('Live stream ended or read timed out')` — the session died twice in production, reproducibly, while the stream stayed up. Fix: the default capture now takes a read timeout that follows the source kind — 2000 ms for a local replay (unchanged, its test still pins those exact values) and `live_read_timeout_ms` (default 20000 ms) for a live stream. Verified against the live stream in-process for **240 s: `state=running` throughout, `error=None`, crossing the ~200 s point where production died twice** (`out/live-test/verification.json`).
2. **One notify per decoded frame.** A live decoder outruns the source when ffmpeg has segments buffered (measured `decode` p50 0.4 ms, i.e. thousands of frames per second during a burst) and the decode loop woke the worker for every frame. The loop now still publishes every frame into the single pending slot but wakes the worker at most once per source frame period. Test: a 200-frame instant burst produces **≤4 notifies** (previously one per frame).

### The design limit that is NOT fixed: published rate on a bursty live source

The published rate stayed at **1.8-1.9 fps** after both fixes, while each published frame cost only 20.9 ms p50 (`receive_to_result`) and the source delivered 30.4 fps. The cause is the interaction, not the fixes: HLS delivers ~30 frames per 1-2 s segment as a burst; the single latest-frame-only slot means the worker — which needs 20.9 ms per frame — is superseded for all but the newest frame of each burst, so it publishes roughly **one frame per segment** and each published frame carries a `frame_age` of 0.5-1.8 s. This is the design working as specified (never queue, never fall behind) meeting a source that arrives in bursts. Three options, each with a cost, for the owner/director to choose:

- **Pace the live decode loop** to the source frame period (the replay path already does this): publishes ~30 fps at ~20 ms each, but permanently sits one buffer depth (~2-6 s) behind the live edge.
- **A bounded queue of 2-4 frames** for live sources: the worker drains a burst at ~45 fps (its own limit) with ~0.2-0.5 s added latency, at the cost of the "one pending frame" invariant that the whole backpressure design rests on.
- **Leave it**: 1.8 fps with ≤1.8 s frame age is honest and bounded, and it is what the operator sees today.

### What this round did not prove

- **Real glass-to-glass latency.** The 0.33-1.4 s figure depends on the encoder's `PROGRAM-DATE-TIME`; nothing here measures the camera-to-encoder leg.
- **Live ball detection.** No ball stage was in the detectors list, so no fps with/without it was measured on live video.
- **The fix in production.** Production still runs the pre-fix code (a restart is the director's call); the fix is verified in-process against the live stream instead.
- **Chat embed behaviour.** With no `<iframe>` in the DOM there was nothing to load or refuse; whether the Twitch embed works on `127.0.0.1` with `parent=` remains untested.

Cleanup and integrity: the session I started is `stopped` (`decoder_alive`/`worker_alive` false). All five protected files are byte-identical to their pre-test values — `out/corner-pocket/state.json` `77777777777777777777777777777777`, `out/pid_seed.json` `77777777777777777777777777777777`, `out/scan30/annotations.json` `77777777777777777777777777777777`, `out/scan30/events.json` `77777777777777777777777777777777`, `out/identity/clusters.json` `77777777777777777777777777777777` (682485 bytes, mtime 2026-09-23). The service journal since the test started contains only GETs plus **four** `POST /api/live` — the stops and starts of this test, and nothing else.

### Follow-up (2026-09-26, same day): `upstream_delay_ms` is now measured in-process

The number in the table above was measured from a shell. It is now what `/api/live` reports for a live Twitch source: while a session runs, a small probe thread (`annotator/live_processing._UpstreamDelayProbe`) fetches the media playlist on a cadence (`upstream_refresh_s`, default 5 s) and reads the newest segment's `#EXT-X-PROGRAM-DATE-TIME` plus its `#EXTINF`; the delay is `now - (segment start + duration)` — how long ago the newest segment finished being produced. The worker re-reads the probe at receive time, so `latest.upstream_delay_ms` is the value that applied when that frame arrived, and `status()['upstream_delay_ms']` follows it. The probe runs on its own thread and only a number crosses back, so a slow playlist fetch cannot stall frames.

**Labels and limits, stated on the payload:** whenever a value exists the status also carries `upstream_clock: 'broadcaster'`, because `#EXT-X-PROGRAM-DATE-TIME` is stamped by the broadcaster's **encoder clock** — if that clock is wrong, this number moves with it, and nothing here measures the camera-to-encoder leg. It is the age of the *live edge*, i.e. the freshest a received frame can be; a frame served from a buffered backlog is older than this. It stays `None` (with `upstream_clock` also `None`) for dataset/replay sources, for a playlist that is a recording (`#EXT-X-PLAYLIST-TYPE` or `#EXT-X-ENDLIST`), for a playlist without `PROGRAM-DATE-TIME`, and whenever the playlist cannot be fetched — a stale number is never repeated or invented. Computing it is a plain GET of the playlist; nothing is written. `tests/test_twitch_source.py::PlaylistLagTests` pins the arithmetic and every `None` case against a fixture playlist, and `tests/test_live_processing.py::UpstreamDelayTests` pins the in-process path (labelled value on a live playlist, `None` for a playlist without PDT, `None` when the fetch fails, and no probe at all for a dataset source).



