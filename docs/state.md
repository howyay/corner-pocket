# Measured state (append-only)

## Correction before unified Corner Pocket UI work

Earlier entries and chat summaries overstate validation. HTTP 200 checks did
not establish browser usability. Manual pocket anchors had no implemented
calibration consumer; seed propagation was experimental and automatically
inferred B, not continuous validated identity recognition. Candidate-only
reviews cannot establish recall without independent missed-event ground truth.

The highlight scan used `annotator/corners_30min.json` despite different video
geometry. Its 6-shot/3-pot output is **invalid for accuracy claims**, not a clean
validated rescan. Count recovery alone does not prove occlusion or a pot, and
whole-VOD player/shot/pot precision and recall remain unmeasured. Treat actor
assignments as suggestions and smoke-test prototypes as non-human labels.

The unified UI work uses the supplied `Corner Pocket redesign (1).zip` design
and replaces the fragmented correction entry points; it does not certify the
underlying predictions. Ball-ID certification remains backlog.

## 2026-09-07 — repo + kaneo wired; calibration cross-segment audit first cut

- Forgejo `operator/pool` (private) ⇄ Kaneo project `pool` (sync via Gitea
  integration webhook; 11 issues = 11 Kaneo tasks, externalIds matched).
- Audit tool: `src/audit_calib.py` → `out/audit_homography.json`.

### HIGHLIGHT 1080p (vod_highlight.mp4, t=5..200) — STABLE
Cloth-quad corners vs `fixed_corners.json`: median **2.0 px**, p90 16.4 px
(single outlier frame t=90, likely corner occlusion). At ~2.6 mm/px this is
median ~5 mm corner jitter. Segment calibration (`calib_final.json`, holdout
13.1 mm mean / 4.9 mm median) stands.

### VOD30 720p (vod_30min_260815.mp4, t=60..1740) — UNRELIABLE, needs re-anchoring
- Quad detection ok on 9/15 sampled frames; deviations vs the provisional
  `corners_30min.json`: median **59.8 px**, p90 135 px (≈114–260 mm at ~1.9 mm/px).
- Failure mode diagnosed: HSV cloth segmentation is healthy (largest component
  120–185 kpx on every sampled frame incl. failing ones) — the **quadrilateral
  fit stage** fails/degrades when a player occludes the cloth boundary
  (concave hull). Morphology/hull variants made it worse (best = current config).
- Next (HOM-1): edge-line RANSAC quad fitting (fit 4 boundary lines on the
  largest cloth component → intersect corners) or temporal-median corner
  tracking with outlier rejection; then fresh 6-anchor holdout on vod30.
- Note: vod30 (1280×720) and highlight (1920×1080) have different camera
  framing → calibration is per-segment; a single H must not be reused.

### Ball-ID label sets (backlog, see BALL-1)
- Set 1 `out/unlabeled_crops` (79 crops, 6 frames of highlight): 75/79 labeled,
  no per-frame duplicates after 2026-09-03 corrections; 4 open (t5_b08, t5_b11
  (rack; likely 14/15), t60_b07, t60_b13 (likely cue)).
- Set 2 `out/unlabeled_crops2` (56 crops, 8 frames t=560..1700 of vod30): 0/56
  labeled. Mask-only crops + context images; labelers :8124 (set 1) and
  :8125 (set 2).
- Ceiling on set 1 only: ResNet18 79.5 % leave-one-frame-out (label-corrected);
  SqueezeNet 14 %, MobileNetV3-S 43 % — insufficient class support; certification
  deferred to BALL-1 after set-2 labels.

## 2026-09-07 (round 2) — vod30 720p corner detection characterized; EVT-1 consistency audit

### HOM-1 — vod30 corner detection characterization (src/quad_fit.py v3, make_segment_corners.py)
- Tight-hue adaptive mask (anchor hue from centre band) is clean per frame (largest comp ~110 kpx,
  bbox ≈ table). Failure is downstream of masking:
  - mask/quad over-segmentation at 720p merges walls/clothing; minAreaRect axes can flip (90°),
  - per-frame quad dispersion is BIMODAL/wide even after area gate: temporal median residual
    median 205 px, p90 371 px over 175 sampled frames (max 510 px) → the simple
    largest-component + approxPolyDP quad path is NOT usable for vod30 corners.
- Robust side-line fitting (RANSAC / iterative assignment, quad_fit v3) converges 15/15 on the
  sampled frames but with ~340 px systematic offset (mask edge loss on one rail biases the box).
- Verdict: vod30 needs a line/corner-based finder (cushion rails via edge RANSAC in a dilated
  cloth region) OR user-anchored pockets on 1–2 frames + rect-constrained PnP (highlight path);
  per-frame quads should be replaced by one fixed segment homography (camera static).
- Highlight 1080p remains stable (median 2.0 px).

### EVT-1 — events.json consistency audit (no GT yet)
- Causality violations: 0 (57 shots, 11 pot rows; every pot linked_shot_t <= pot t).
- Pot count chain internally consistent: 10→8→6→5→4→3→1→0.
- Issues to fix before GT review:
  - pot rows are DUPLICATED pairwise (same t, same counts twice; 11 rows for 6 distinct moments),
  - 6/68 events verified so far (all false),
  - shot gaps up to 33–123 s imply missed quiet shots (false negatives) — candidate windows
    around those gaps,
  - one pot window_s [406,408] lies AFTER its pot t=387 (inconsistent window semantics from
    rebuild_events_calibrated.py).

### PID-1 — person sensing feasibility (SAM3, CPU)
- 4 shot-window frames (vod30 t=39.5/126.5/280.5/386.5, pre-impact −0.5 s): SAM3 text prompt
  "person" detected 5/3/3/2 persons (scores 0.87–0.99); at t=280.5 & 386.5 a dominant large
  person bbox (area frac 0.17–0.19, spanning table centre) = bent shooter pose. 13 crops stored
  under out/pid1_persons/ (+report.json).
- Implication: person masks exist per shot window; spectators also detected → tracklet zone
  exclusion + geometric actor scoring (PID-2/PID-3) required, as the research predicted.

## 2026-09-07 (round 3) — HOM-1: strip-refined corners solved for vod30

- New tool `src/quad_refine.py`: refines a prior quad by scanning cloth->edge
  transitions along side-normal strips (robust vs occlusion; 13/15 sampled
  frames ok, fails only at heavy-occlusion instants).
- `out/corners_30min_v2.json` (method + stats): 163/300 frames accepted (MAD
  gate 6 px); per-frame jitter median **3.95 px**, p90 **5.59 px** (old
  approach: ~205 px median). At ~1.9 mm/px -> ~7.5 mm / 10.6 mm corner jitter.
- Systematic offset vs the provisional corners_30min found on the left side
  (old TL/BL off by ~28-39 px): new reference is temporally consistent.
- Remaining for the formal bar: 6-pocket anchor holdout on vod30 (user clicks,
  same as the highlight path) -> rect-PnP + mm RMSE; then PROJ-1 pocket
  residual table. Automatic rail-finder attempts (quad_fit.py v2/v3,
  quad_fit_lines.py) documented as not viable on this footage.

## 2026-09-07 (round 4) — EVT-1: corrected event rebuild (events_v2.json)

- Root causes found in the old build: (1) sam3 image coords were reprojected
  with the HIGHLIGHT (1080p) calibration on the vod30 (720p) scan -> wrong mm;
  (2) pot counts used raw counts incl. detection spikes; (3) occlusion gate was
  missing in records (cloth_area recomputed per sam3 t from the video instead).
- src/rebuild_events_v2.py -> out/scan30/events_v2.json: real-mm H from
  corners_30min_v2 (2540x1270), real pocket centers, monotone-hull pot logic
  (counts physically non-increasing; rises = detection noise), causality links.
- Result: 57 shots + 10 pot rows (was 11 w/ inconsistent chain); pot chain
  clean 10->8->6->5->4->3->1->0 (double pots at 81/137/343s, singles at
  199/255/281/408s); all pots linked to shots; causality violations 0; pocket
  distances <= 440 mm (bogus 1.1 m rows eliminated).
- Late-game samples at t=347/390/406 were detection spikes (count 4 at 390);
  hull logic renders them harmless. GT review (annotator on events_v2) remains
  the bar; 67 events.

## 2026-09-07 (round 5) — PID-2/PID-3/PID-4 precursors on shot instants

- SAM3 person scan extended to 12 shot instants (out/pid1_persons*): 2-5 persons
  per instant, scores 0.87-0.99; 33 crops stored.
- PID-3 cue feasibility: SAM3 "cue stick" probe returns thin long candidates
  (e.g. 13x226 px at t=342.5) — usable but noisy; geometry fallback = cue-ball
  position from event ball_from.
- PID-2 dense tracklet detector gap: this cv2 5.0 build lacks HOGDescriptor and
  CascadeClassifier; torchvision detection weights not fetchable right now
  (pytorch.org denied, HF mirror unavailable). Dense continuous person tracking
  deferred (ultralytics pip install or ROCm multiplex later).
- PID-4 precursor (src/pid_identity.py): k-means k=2 over torso colors of
  table-zone persons at 12 instants: 16 persons, clusters LIGHT (rgb ~104) vs
  DARK (rgb ~35-80), between/within ratio 4.3; bent-shooter boxes (area frac
  ~0.18) map to the DARK player at t=80.5/280.5/342.5/386.5 (and light player
  elsewhere) -> strong preliminary A/B separation; artifacts
  out/pid_identity_v0.json + out/pid_identity_montage.png (for user review).
- Next: user shooter-GT field in the event review UI would let PID-3/5 scoring
  be validated directly on the same review pass.

## 2026-09-07 (round 6) — vod30 calibration auto pass + shooter field in reviewer

- src/calib_vod30.py: full rect-PnP run on vod30 (f=1685 px, 87/200 frames w/
  usable quad+anchors): per-anchor medians TL 41 / TR 35 / BR 15 / BL 23 /
  left-side 71 / right-side 10 mm (auto dark-blob anchors). Bias-corrected
  half/half holdout: mean 30.0 mm / median 29.3 mm -> bar (<=15 mm) NOT MET.
  Left side pocket blob detection is the weak anchor at 720p. out/calib_vod30.json
  stores f, per-anchor medians, biases, holdout and the median H (usable now,
  to be superseded by a manual 6-click anchor pass: same as the highlight path).
- Review annotator (:8124) now persists a SHOOTER field per event (A light /
  B dark / ? unknown) - one review pass yields event GT + shooter GT for
  PID-3/5 validation. index.html JS syntax checked (node --check).

## 2026-09-07 (round 7) — PID-2 v0 tracklets (YOLO) + PROJ-1 audit on vod30

- ultralytics 8.4.142 installed in .venv (YOLOv8n, 6.2MB); person detections
  match SAM3 anchors on shared frames (bent shooter, players, spectator).
- src/yolo_track.py: 1 fps person tracklets over 4 shot windows (greedy
  nearest-centre association, 6 s stale pruning = occlusion gaps):
  - each window yields 2 long-lived tracks (26 s, ~27 samples) = the two
    players, plus short spectator tracks;
  - SAM3 anchor agreement 13/14 boxes (t=80.5 3/3, 198.5 3/4, 342.5 3/3,
    386.5 4/4); 4 windows ran in ~14 s total (CPU).
  - out/pid2_tracklets.json; occlusion semantics (hidden => gap, not identity
    switch) inherited by association design.
- PROJ-1 projection audit (vod30, out/calib_vod30.json H): portrait orientation
  correct (head rail top y~303-314, foot rail bottom y~570-584, side pockets at
  mid-length); mm rulers consistent with perspective (centre: 2.92 mm/px across
  width, length foreshortening ~0.107 px/mm avg; 1000 mm rulers check out);
  per-anchor biases (px) recorded; overlay artifact out/proj_audit_vod30.png.
- Next: bind tracklets to A/B identity (OSNet or colour) and score shooter per
  event (PID-3/4/5), then E2E-1.

## 2026-09-07 (round 8) — PID-3 v0 per-shot actor assignment

- src/pid_shooter.py: for each of 57 shots: YOLO persons at t-1.2s (table
  zone), torso-colour cluster (A light / B dark per pid_identity prototypes),
  geometry when verified (cue-ball mm -> px through calib_vod30 H):
  - 52/57 assigned (5 no-person); geometry 6 (t=273/343/849/1072/1614/1662,
    all actor B/dark, dist to cue 314-539 px); colour-only 46; A/B switches 15
    (sequence BBBBABAAABBBBAABBBBABABBBBBBBBAB?BBB...); dark heavy (B~3x A).
  - Sparse geometry because only shots with SAM3 displacement verification
    (<=3.5s pairs) carry ball_from; per-shot actor GT from the :8124 reviewer
    (shooter field) is the validation target.
- out/events_actors.json.

## 2026-09-07 (round 9) — PID-3 v1 white-ball geometry + E2E-1 assembly

- pid_shooter2.py: white (cue) ball localized per shot frame (HSV on cloth:
  found in 50/57) -> nearest-person geometry for 45/57 shots (was 6), 7 colour
  fallback, 5 no-person; actors: 20 A/B switches (sequence AAAAABA?B...).
- docs/e2e_run.md: corrected 30-min chain documented with run commands,
  artifacts and metrics (corners -> calib -> sam3 -> events_v2 -> persons ->
  tracklets -> prototypes -> per-shot actors). Visuals: out/e2e_frame_81.png,
  out/e2e_frame_343.png.
- Validation still needs :8124 GT (verdicts + shooter).

## 2026-09-07 (round 10) — PID-4 v1: OSNet x0.25 embeddings

- Vendored official osnet.py (kaiyangzhou/deep-person-reid, src/reid/) +
  MSMT17-pretrained x0.25 weights (HF kaiyangzhou/osnet, 9.3MB, src/reid/weights).
- src/pid_osnet.py embeds the 16 table-zone persons (256x128 crops):
  leave-one-out NN same-colour-cluster 14/16 (0.88); intra cos 0.991 vs inter
  0.987 (small gap: full-body crops incl. background dominate - mask-tight
  crops or OSNet-AIN would improve; colour prototypes remain primary identity
  cue until then). out/pid_osnet_eval.json.

## 2026-09-07 (round 11) — PID-4 v2 tracklet identity binding: inconclusive (cause found)

- Embedded crops along colour-separated tracks (2 windows, full & torso modes,
  both channel orders): intra ~0.99-1.00 AND inter ~0.99 -> pretrained OSNet
  does NOT separate persons here on full-YOLO-box crops.
- Cause: crops are background-dominated in this dark venue (persons are small
  within their boxes; e.g. 70x178px at 720p) -> embeddings approximate the
  venue background direction; synthetic controls (white/black/noise) vary
  correctly, so the model/weights/preprocessing are not degenerate per se.
- Person-level NN on 16 crops still matched colour clusters 14/16 (coarse).
- Next steps (PID-4): SAM3 mask-tight person crops (store masks at scan time),
  and/or OSNet-AIN or a small fine-tune; colour prototypes remain primary.
  Tracklet identity binding should be re-tested with tight crops.

## 2026-09-07 (round 12) — OSNet separation FIXED: weight-loading bug + tight crops

- Root cause of the round-11 "background dominance" conclusion was WRONG: the
  loader filtered keys by 'backbone.'/'fc.' prefixes, but torchreid checkpoints
  store conv layers unprefixed -> only fc was loaded, all convs stayed random.
  Full load (minus classifier): 0 missing.
- With correct weights:
  - tight-crop track pairs: win 68-94 intra 0.90/0.80 vs inter 0.69;
    win 330-356 intra 0.62/0.73 vs inter 0.52.
  - full-crop track pairs: win 68-94 intra 0.958/0.664 vs inter 0.414;
    win 330-356 intra 0.641/0.900 vs inter 0.46-0.48 (torso mode similar).
  - 16-person NN vs colour clusters: 13-14/16.
- Conclusion: OSNet x0.25 MSMT17 separates the two players in this footage;
  earlier negative result superseded (docs + issue comments corrected).
- Mask-tight crops + masks stored under out/pid_masks (13 frames, 42 crops).

## 2026-09-07 (round 13) — PID-5 v0 fused per-shot association

- src/pid_associate.py: A/B prototypes = mean OSNet embeddings of the
  colour-separated track pairs (2 windows); per shot: person boxes at t-0.8s,
  embeddings, cue-ball (white) geometry; actor = person nearest cue, labelled by
  prototype argmax w/ margin.
- Result: 52/57 shots assigned (5 no-person); cue geometry 45; low-margin 9;
  sequence heavily B (dark): "BBBBBBA?BBB...A?..." with 6 A/B switches.
  Caveats: prototype set from 2 windows may not cover the light player's
  appearances; nearest-cue selection may bias toward the near-table player.
  Validation requires the :8124 shooter GT. out/events_actors.json (v2).

## 2026-09-08 — round: person-in-loop tooling + VOD highlight pipeline test

- PID-6 anchor UI live on :8126 (pocket anchors w/ auto prefill; feeds HOM-1).
- PID-6 player seed UI live on :8127 (click player-A track; rebuild rebuilds
  OSNet prototypes & propagates across all tracklets; smoke test passed).
- Review UIs now show predicted actor per event (from events_actors.json via
  /api/actors, id-mapped) on :8124 / :8129.
- vod30 event-time ball crops collected: 294 crops + ctx at 59 event times ->
  served on :8128 (label.html) for ball-ID GT at the exact event frames.
- scan_events patched (mp -> ThreadPoolExecutor; sandbox denies /dev/shm).
- Highlight VOD pipeline test: full scan+SAM3+events ran end-to-end on
  vod_highlight.mp4 -> out/scan_highlight/events.json: 6 shots + 11 pots,
  evidence jpgs, served on :8129.  NOTE: 11 pots vs known ~9 balls -> likely
  double-counted pairs (same pattern as the old vod30 bug: two pocket windows
  firing for one ball); needs the same causal-chain guard as events_v2.

## 2026-09-22 — table-cloth boundary: baseline, refinement, and a reference-geometry defect

- Harness `src/eval_table_detect.py` (45 vod30 frames over t=0..1806, 21 highlight
  frames), app rule reproduced offline (`mean corner distance <= 40 px`, best of
  four cyclic alignments; `src/check_app_quad.py`). Baseline detector
  `src/table_detect.detect_table`:
  - vod30, ms/frame median 17.98 / p90 26.55; vs app-anchors median **72.77** /
    p90 145.28 / max 176.86, accept@40 px **2.3%**, states `{off 15,
    no detection 16, ok 1, invalid geometry 12}`; vs corners30-v2 median 78.36,
    accept 0%.
  - highlight, vs fixed_corners median **1.9** / p90 22.47, accept 85%.
- Refined detector `src/table_refine.py`: static-camera prior (saved reference
  quad, or the previous accepted frame) + strip/edge refinement — per side a
  narrow perpendicular band, occupancy crossing of the cloth mask with an
  intensity-ramp fallback, per-side motion capped at 8 px/iteration, partial
  occlusion holds the unmeasured side instead of failing the frame — returning
  `confidence`/`reason` and keeping `corners`/`mask`/`debug`. Wired into
  `src/frame_inference.py` (`detect_table_for_frame`, optional `dataset=`) and
  `annotator/unified_server.py` `_unified_detection` (cached `_prior_for`).
  `detect_table()` is unchanged for its existing callers (pipeline,
  rebuild_events_v2, info_complete_scan, ball_detect, scan_events).
  - vod30 vs corners30-v2 median **4.38** / p90 7.16 / max 12.9, accept **100%**
    (44/44 readable; t=1806.8 unreadable); no-detection 16 -> **0**, invalid
    geometry 12 -> **0**; vs app-anchors 43.1 px, accept 0%.
  - highlight median **11.7** / p90 11.8, accept **100%**, no refusals.
  - Cost: app path (640x360 input) **9.8 -> 36.1 ms** median (+26 ms/frame);
    full-res 1280x720 192 ms median (p90 366), inside the 0.2-2.3 s budget.
- App-visible: model-quad refusals on vod30 **40/45 -> 4/45**, invalid-geometry
  3 -> 0. The remaining four are refused with reason `low_cloth_area` and never
  guessed: t=849.5, 970.9, 1618.2, 1658.6 — players standing over the bed, mean
  gray inside the table quad 54-68 vs 89 at t=70.
- **Reference-geometry defect (not a detector failure)**: the app validates the
  quad against the first four of the six hand anchors, and those anchors are
  pocket-jaw centres ~44 px inside the cloth boundary (per-corner 78.6 / 4.7 /
  27.1 / 65.6 px vs the recorded cloth quad; anchor cloth-mask coverage 0.27-0.68
  against 0.0 at the cloth corners). The best possible cloth-corner quad scores
  **42.9-58.6 px** against them, i.e. above the 40 px tolerance, so a correct quad
  is structurally un-drawable until the app's reference is fixed. Fix pending an
  owner decision: re-anchor the four cloth corners, or derive the cloth corners
  from the pocket geometry.
- Circularity caveats: corners30-v2 is refinement-derived and is scored here
  against a refinement detector (optimistic); the anchors are pocket geometry
  (pessimistic). Both references are reported, neither is rigged.
- highlight note: 11.7 px against a reference whose bottom rail sits 26-29 px
  inside the visible cloth (measured at t=10/60/180/300/360). `_MAX_MOVE_PX` in
  `src/table_refine.py` is the knob if literal parity with the old reference is
  preferred over tracking the visible cloth.
- Evidence: `out/table-detect-eval/baseline-naive.{json,txt}`,
  `after-refined.{json,txt}`, `app-verdict.json`,
  `overlay-normal.png` / `overlay-occluded.png` / `overlay-fixed.png`.
