# Live processing: real local verification

## Person identification performance (2026-09-11 measured)

Warm per-frame cost on real VOD 1280x720, CPU only: YOLOv8n person detection ~25–32 ms, OSNet x0.25 (vendored MSMT17 weights) re-ID ~38–47 ms per frame for up to 3 persons — combined worst frame 78 ms, comfortably inside a 10 fps processing budget. Face embeddings (buffalo_l ArcFace) verified usable at this camera distance: 268/268 sampled faces produced 512-dim normalized embeddings; same-person 1s-apart cosine median 0.958 (p05 0.644) vs cross-person same-frame 0.077 (p05 −0.04), supporting thresholds 0.35/0.12 margin. Face sizes: eye distance median ~10.4 px, max 15.9, min 2.3.

Ground-truth caution: `out/events_actors.json` contains 57 entries but 45 were labeled by the previous `osnet-geo` model output, not independent humans (48 B / 4 A / 5 None). Shooter-association P/R must be measured only against human-confirmed labels from the explicit A/B/ignore seeding workflow; model-labeled actors are never truth.

## Identity pipeline on real footage (2026-09-15, full-segment run in progress)

Found and fixed a real integration bug the unit tests could not see: `process_frame` fed the 512-dim ArcFace embedding into the 128-dim body identity index, so any frame containing a visible quality face crashed the pipeline. Fixed in `src/person_pipeline.py`; all 19 identity + 21 face engine tests still pass.

Smoke run (frames 8000–8060, warm): 3 persons/frame, one cluster, no player binding before enrollment (no fabricated identities); enrolling a quality face (eye distance 13.9 px, detection score 0.837) bound the cluster at similarity 1.0 and the binding persisted across view exits. All state writes stayed in a temporary root; production annotation files unchanged.

Warm per-frame cost is dominated by full-frame face analysis (~300–390 ms) over detection (~25 ms) and OSNet re-ID (~55–85 ms): roughly 390–460 ms total, above the 150 ms budget. Face analysis is the known next optimization (ROI-restricted detection), recorded honestly rather than tuned prematurely. Full-segment numbers to follow.

## Application support and boundaries

Vision → Stream/source controls now contains continuous processing controls for local replay and saved canonical Twitch channels. This processing is separate from the optional watch-only Twitch embed. The pipeline continuously decodes into one pending-frame slot and publishes an atomic JPEG/detection pair; under load it drops superseded frames instead of accumulating a queue.

Metrics distinguish queue wait (`receive_to_process_ms`), inference time (`inference_ms`), and complete local receive-to-result age (`receive_to_result_ms`). These exclude Twitch camera/encoder/CDN delay; `upstream_delay_ms` remains null. Cold model startup takes several seconds. CPU SAM3 balls are intentionally excluded from the live detector list; frame-level table/person detection is not temporal shot/pot or shooter identification.

The standard-library resolver obtains anonymous public playback authorization, validates initial Twitch HTTPS playlists and returns safe errors. A real check of `examplechannel` obtained authorization but returned playlist HTTP 404 (offline/no public playable stream). No actual Twitch frames or Twitch upstream latency were verified. Future remote playlist retrieval is performed by OpenCV/FFmpeg; initial URL validation is not a general-purpose arbitrary-HLS security boundary. Source input remains restricted to saved canonical Twitch channels.

Deployment completed after owner authorization and verification: restarted the existing `pool-workbench.service`, confirmed active, and verified origin `/`, `/api/operations`, `/api/live`, and VOD metadata return HTTP 200. Deployed browser shows all six tabs and the native live-processing panel with no JavaScript errors. Public root and `/api/live` both return HTTP 302 to the existing Cloudflare Access login using curl; an initial Python client received HTTP 403, so authenticated external end-to-end remains owner-login dependent. No Access/tunnel configuration or production annotations were changed.

The actual Vision browser lifecycle passed against an isolated real-video fixture: start, canvas frame with paired detections, stop through stopping to stopped, and navigation cleanup. At full 1080p, receive-to-result latency reached about four seconds under shared-host load. Live inference now proportionally caps frames to 960×540; `source_width`/`source_height` retain original dimensions, while JPEG and detection coordinates use `width`/`height`. Selected-frame annotation still uses original frames. This cap is a performance safeguard, not a promised frame rate. Rebenchmark after changes.

Latest predeployment regression: 79 Python tests, 16 review frontend tests, and 21 operations frontend tests passed.

## Reproduce

From `/home/operator/projects/pool`:

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

All fixture, library-config/cache, and temporary files live under `/home/operator/projects/pool/.live-e2e-*` and are removed on exit. The temporary model is a symlink to existing weights. The helper shuts down its HTTP server and joins its thread, stops every processor in `finally`, and verifies the saved Operations fixture is unchanged. It does not edit server/UI/module files or persistent Operations data.

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


