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

- Forgejo `<owner>/pool` (private) ⇄ Kaneo project `pool` (sync via Gitea
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

## 2026-09-22 (correction) — that 4.38 px / 100 % table-cloth result was a self-score

- The section above claims "vod30 vs corners30-v2 median 78.4 -> 4.38 px, accept
  0 -> 100 %" as a detector improvement. It is **circular and must not stand as an
  improvement claim**: `prior_for('vod30')` read `out/corners_30min_v2.json`, the
  same file `src/eval_table_detect.py` scores against. Seeding a refinement from a
  reference and then scoring it against that reference measures the seed, not the
  detector. The 4.38 px / 100 % figures and the "44 px inside the cloth" claim in
  that section are withdrawn.
- What the cloth edge actually is (vod30, t=70, horizontal scanlines on the
  outermost bright-cloth boundary, cross-checked against the HSV cloth mask): the
  left edge **slants** x=520 (y=330) -> x=381 (y=560). `corners_30min_v2.json` puts
  a **vertical** left rail at x~450: 67 px outside the cloth at the top and 70 px
  inside at the bottom. The six hand anchors track that same edge within **6-13 px**
  (perpendicular deviation <= 10 px), i.e. the anchors are the correct reference and
  the app's 40 px tolerance is sound. Reproduced here: mask edge
  x=520/502/482/462/444/424/406/386 vs anchor line x=528/509/491/472/454/435/417/398
  at y=330..540.
- Corrected numbers, same 45 + 21 frame sample, seeded from the hand anchors
  (`out/pid_anchors_vod30.json`) since commit `b33b966`:
  - vod30 vs app-anchors: median **5.09 px**, p90 5.83, max 6.28, accept@40 px
    **86.4 %** (38/44 readable frames), confidence median 1.0; refusals 6
    (`low_cloth_area` 2, `no_boundary_evidence` 4 = players over the bed).
  - vod30 vs `corners_30min_v2.json`: median **43.08 px**, accept 0 % — recorded
    only to show that the old reference disagrees with the cloth, not as a target.
  - highlight vs `fixed_corners.json`: median **11.73 px**, p90 11.83, accept
    **95 %** (19/20; the saved highlight reference's bottom rail sits 26-29 px
    inside the visible cloth - see the note above).
  - App path (`app_prior_for('vod30')` -> `detect_table_for_frame`, anchors seed):
    11/15 frames drawn, median **4.99 px**, p90 5.36 vs anchors, all four sides
    verified on every accepted frame; cost 10.0 -> 29.9 ms median on a 640x360
    input.
- Two defects found by an independent verifier and fixed in the same commit:
  1. the step was converted to frame pixels and then divided by the mask scale
     again, so an iteration advanced ~half the measured offset and the 8 px cap
     bound at an effective 32 px; the side profile now measures on the
     full-resolution mask (the 2x downsample moved the mask edge ~1.5 px). A 10 px
     prior perturbation now converges to 0.68 px in two iterations (was 3.02 px).
  2. a side whose band held no boundary evidence was still reported as a
     high-confidence quad: a +-120 px rail perturbation returned a 61-65 px-wrong
     quad at confidence 0.70-0.75 with `reason=None`. Every side must now show an
     occupancy crossing with cloth inside it (>= 0.55 coverage), a real drop
     (>= 0.20) and the rail signature outside it (dark band then bright outside,
     >= 25 gray levels); otherwise the frame is refused with a per-side reason
     code, or the side is explicitly marked `inherited` (weak but agreeing
     evidence within 3 px, never counted as verified, confidence reduced). The
     120 px case now returns no corners with `no_boundary_evidence`.
- Evidence: `out/table-detect-eval/after-anchor-seed.{json,txt}`,
  `baseline-naive.{json,txt}`, `app-verdict.json`; tests
  `tests/test_table_refine.py` (per-side verification, step size, refusal cases).

## 2026-09-24 — shot/pot gating over a real ball track: the rules exist before the detector

Every event verdict this repo has produced so far was decided from a sparse ball
census (1-3 detections per sampled frame): 24 of 30 served events were false and
all 16 pots were refuted. The GPU ball detector in training (204k params,
15.5 ms/frame) will supply **dense per-frame tracks**, so the rules are written
and tested now, against synthetic ground truth, so the first real track can be
judged the moment it exists.

- New, pure (stdlib only, no video, no OpenCV, no torch, no I/O):
  `src/shot_pot_gate.py`; tests `tests/test_shot_pot_gate.py` (57 tests + 6
  subtests, green).
- **Pocket model = the verified reference geometry, not a new calibration.**
  Six pocket centres in source pixels are the canonical `POCKETS_MM` (the same
  names as `src/event_gates.py`) projected through the cloth quad of
  `out/calib_vod30_segments.json` (`segments[0].quad_px`, source
  `human_anchors`, i.e. `out/pid_anchors_vod30.json` `anchors["70.0"][:4]`).
  Independent cross-check: the file's two *hand side-pocket* anchors sit 6.8 px
  and 4.9 px from the projected side pockets, and the four corner anchors 0.0-0.7
  px, so two independent human measurements agree on all six places. The pot
  radius is the repo's measured `pot_pocket_r_mm = 100 mm` (`src/event_gates.py`:
  vanished balls cluster at 39-86 mm and then jump to >= 110 mm) converted at
  each pocket's **local** scale, 12.9 px head / 38.8 px foot: the far end is
  foreshortened ~3x, so one global pixel radius would be wrong at both ends.

### The rules and every bar

- **Shot = motion onset.** A ball still for `rest_window_s = 0.5 s` (0.5 s = 15
  dense frames, and a ball at the motion bar covers 20 px - 2-5 ball diameters -
  in that time, so "still" cannot be met in motion) with at least
  `rest_min_intervals = 2` intervals, each at or below `rest_speed_px_s = 6 px/s`
  (0.2 px per 30 fps frame: below the detector's positional noise and below 6 % of
  the smallest ball radius, which is 3.7 px here), then `onset_intervals = 3`
  consecutive intervals above `motion_speed_px_s = 40 px/s` (1.3 px/frame, 6.7x
  the rest bar; 3 frames = 0.1 s of commitment, the regime a single-frame identity
  jump and label swap cannot hold). An interval longer than `max_gap_s = 0.25 s`
  breaks a run: "sustained" cannot be claimed across frames the ball was not seen
  in. The event carries the onset time (the last measured still position), the
  direction (image space: 0 deg = +x, 90 deg = +y down), the peak speed, the
  duration, and the still stretch plus the run as evidence.
- **Pot = the track terminates inside a pocket radius** and does not reappear for
  `persistence_s = 1.0 s` (30 dense frames of absence, ~100x the frame period,
  far longer than a one-frame dropout, while the last ~40 px into a pocket take
  <= 0.2 s at a modest 200 px/s), with the occlusion channel **clear** for that
  stretch. A disappearance must also exceed `vanish_min_s = 0.4 s` *and*
  `vanish_cadence_multiple = 4x` the track's own median interval, so a 0.5 s
  census is not read as vanishing between two normal samples.
- **The occlusion channel is an input** (per-sample flags, or `occ_share` /
  `occ_dense` from `src/motion_scan.py`, whose person bar `OCC_DENSE_MIN = 0.30`
  is reused and pinned equal by a test). A ball that vanishes while a person
  covers the cloth is **unknown, never potted**; a silent channel (no reading) is
  also unknown, never clear; and a pot with no stated observation window after the
  disappearance is unknown, never a free pot.
- **Break = N shot events in one group.** 4 movers starting within
  `simultaneous_window_s = 0.15 s` give 4 shot events that share a `group_id`,
  plus one group record flagged `is_break` at `break_min_balls = 3` (2 movers is a
  cue plus the ball it contacted - a normal shot; one contact cannot start 3
  identities at once). Merging them into one event would throw away the per-ball
  directions and speeds; not grouping them would hide that it was one act.
- **Nothing is silent.** Every disappearance, motion burst, rest-only track and
  frame-edge exit is emitted with a reason code, the samples used and the
  thresholds that decided it: `no_motion_onset`, `motion_too_short`,
  `no_still_stretch`, `roll_without_pocket`, `reappeared_after_gap`,
  `disappeared_outside_pocket`, `left_frame_edge`, `left_cloth`,
  `track_ends_at_window_end`, `track_too_short`, `below_confidence_floor`,
  `empty_track`, and `PotEvent(verdict="unknown")` for the occluded cases.
- **No threshold is tuned against the 25 known movers or the emptied queue**
  (neither belongs to this work). Every bar above is geometry (a ball is
  3.7-11.1 px here), the detector's frame period, or a repo-measured value.

### Test outcome

- `tests/test_shot_pot_gate.py`: 57 tests + 6 subtests, all green. Synthetic
  ground truth: a stationary ball, a single shot (onset/direction/peak/duration),
  a pot into each of the six pockets, a break (4 movers), jitter below the bar,
  a single-frame jump, a rolling ball that never reaches a pocket, a ball leaving
  the frame edge, a ball leaving the cloth, a corner pot that must not be called
  "left the cloth", a ball vanishing under the occlusion flag (asserted
  **unknown**, not a pot), an occlusion series over the persistence window, a
  silent channel, a disappearance and reappearance (gap, not a pot), an identity
  swap inside a pocket radius, a ball parked in the jaws, a gap shorter than the
  vanish bar, and a sparse track whose vanish gap scales with its own cadence.
- **One test is built from real data**: the SAM3 census frame-times
  (`out/scan30/sam3_census.json`, 138 sampled times, t = 4.1-1799.7 s) chained by
  colour plus nearest-neighbour continuity into 364 short tracks (70 with >= 3
  samples, longest 9). The gate produces **nothing: 0 shots, 0 pots, 0 unknown
  disappearances, 435 rejections** (294 `track_too_short`, 66 `no_motion_onset`,
  4 `motion_too_short`, 69 `disappeared_outside_pocket`, 1 `reappeared_after_gap`,
  1 `track_ends_at_window_end`). The reason is measured and pinned: the census is
  sampled 0.9 s apart at the median, well beyond the 0.25 s gap bar, and every
  above-bar burst in the whole file is 2 intervals against the 3-interval onset
  bar. The honest result of gating a sparse census is nothing, and the test says
  so in numbers rather than in prose.
- Full suite after this work: **621 passed, 2 skipped** (baseline was 461 + 2
  skipped; the rest arrived with concurrent workers' test files in this tree).

### What the gate cannot do without the detector (stated, not hidden)

- It cannot attribute a shot to a player: a track has no actor.
- It cannot tell a pot from a ball **parked in the jaws**: both end inside the
  pocket radius. The case is flagged (`parked_in_jaws_possible`, and the verdict
  is `unknown / at_rest_inside_pocket_radius` when the last sighting is at rest)
  and never decided.
- Its pot rule is only as good as the detector's **identity persistence**: a ball
  that reappears after a full persistence window inside a pocket radius is an
  identity swap, and once that happens none of that identity's later
  disappearances is called a pot either (`prior_identity_swap_inside_pocket`).
- It cannot see the cloth or the frame: a pocket is geometry, so a vanish near the
  rail with no pocket there is `disappeared_outside_pocket`; the frame and cloth
  tests only run when the caller supplies `frame_size` / `cloth_quad`.
- A track that starts already moving cannot produce a shot (there is no still
  stretch to prove the onset), so the associator must deliver the rest before the
  shot. Nothing here measures the ball, the identity or the occlusion channel;
  those come from the detector, the associator and `src/motion_scan.py`.
- Not touched by this work (byte-identical): `src/event_gates.py`,
  `src/eval_events.py`, `src/tiny_ball_net.py`, `src/face_id.py`,
  `src/person_identity.py`, `annotator/live_processing.py`, `out/pid_seed.json`,
  `out/scan30/annotations.json`, the queue.

## Archived correction on frame 0 (2026-09-25)

`out/scan30/frame_results/0/correction.json` was a saved manual correction
(`source: manual`, 2026-09-23T06:51:44Z, 4 person + 10 ball boxes, uniform ball
sizes) that had been written from the model's own output, so frame 0 drew `人工`
over balls that looked like model results. The owner chose to archive rather than
delete it: it is now `out/scan30/frame_results/0/correction.superseded.json`
(byte-identical, md5 `77777777777777777777777777777777`), which the app no longer
reads as this frame's correction. Frame 0 now draws only the model's boxes
(`data-boxes="auto"`, 14 boxes, no manual split in the facts line) with its stored
inference labelled as an earlier run (`9/16/2026, 4:07:48 AM`). No other
correction file was touched and nothing was deleted.

## 2026-09-25 — the shot/pot gate met its first real track: oscillation, millimetres, and the error bar

The dense-track run over t 1350-1650 s (245 tracks, 19534 samples, 960x540) served
3 "shots" and 1 "pot candidate" as queue ids 9001-9004. Two of the three shots were
**detector oscillation** - id 9001 (white) peaked at 303.6 px/s with a net
displacement of 0.20 px over an 80.6 px path, id 9003 (blue) had 19.7 px of net over
59.9 px of path - and the pot candidate's two radius tests **disagreed with each
other**: 9.62 px from the left-side pocket centre inside a 14.46 px pixel radius, but
**148 mm** from the same centre against the project's 100 mm gate. `src/shot_pot_gate.py`
was fixed for both, and the fixes are three rules, each with its basis stated.

### Rule 1 - a shot must also go somewhere

`min_net_displacement_diameters = 2.0` ball diameters, with the ball resolved **in
the frame pixels of the track being judged**: `ball_diameter_px = 18.4 px x
frame_size[0]/1280` (median ball diameter measured on vod30 at native 1280x720), so
the dense run's 960x540 gives **13.8 px and a 27.6 px bar** with no change to the
consumer's call site. Basis: a ball is the only honest ruler a track carries;
detector localisation/identity noise is of order one ball (the rest bar's 0.2 px per
frame sits under it); and the bar is deliberately *looser* than the repo's own
mm-based shot gate (`src/event_gates.GateConfig.shot_min_disp_mm = 300`, i.e. 5.3
ball diameters, measured 471 mm and 1345 mm for the two human-confirmed shots
against <= 112 mm for every dead window) because this gate produces candidates for
that gate to judge. A sustained run below the bar is now
`oscillation_no_net_travel` - a rejection carrying net, path, net/path, diameters,
peak speed and thresholds - and never a shot and never a roll rejection.

### Rule 2 - the pocket test is decided in millimetres, and per pocket

`PocketModel.measure()` un-projects the last sighting through the reference
homography and compares the true table distance against the canonical `pocket_r_mm
= 100 mm` gate (the repo's measured bar: vanished balls cluster at 39-86 mm and jump
to >= 110 mm). The per-pocket pixel radius stays as a **reported diagnostic**, and
so does the ellipse the projection actually makes of the 100 mm disc: at 960x540,
`left-side 22.2 x 5.9 px`, `foot-right 39.7 x 15.3 px`, `head-left 15.9 x 3.1 px`.
When the two tests disagree and the millimetre test is decisively outside, the
record is a rejection `pocket_test_disagrees_px_vs_mm` with both numbers - never a
pot-shaped candidate produced by the pixel radius alone.

### Rule 3 - the detector's own error bar is propagated

`localisation_error_px = 3.62` - the ball detector's **p90** localisation error at
its r1 operating point 960x540 (median 1.48 px), measured in
`out/tiny_ball_probe/report_960x540.json` (`operating.localisation_px_p90`,
docs/near-real-time-ball-detector.md). That is the frame the dense run gates in.

- **Shots**: net travel is the difference of two sightings, so its error is
  `sqrt(2) x 3.62 = 5.12 px`. net <= 22.5 px -> `oscillation_no_net_travel`;
  22.5-32.7 px -> **`GateReport.unresolved`** with `code="oscillation_unresolved"`
  (a new record type in a new report channel: it is in neither `shots` nor
  `rejections`, so a consumer cannot mistake it for a shot); >= 32.7 px -> shot.
- **Pots**: the millimetre distance's uncertainty is `|J^T u| . 3.62` - the
  pixel->millimetre Jacobian at the ball, projected along the pocket-to-ball
  direction (the worst case over all directions would swamp the gate from every
  direction at the head pockets, where 100 mm is 3.1 px). At the left-side pocket it
  is 54 mm; at the foot pockets ~23 mm; at the head pockets 20-74 mm depending on the
  approach. Verdicts are three-way: `d + u <= 100` -> inside, `d - u > 100` ->
  outside, otherwise **`unknown / pocket_distance_within_uncertainty`**. The iron
  rule keeps its own reason when it applies: a ball that vanishes while a person
  covers the cloth is `unknown / cloth_occluded_at_disappearance` (its occlusion
  status is in the record either way).

### The four served events, before -> after (re-run of the same segment, `--output /tmp`)

| id | before | after |
|----|--------|-------|
| 9001 t125-white | shot, net 0.20 px | **not a shot**: `oscillation_no_net_travel` (0.01 diameters) |
| 9002 t193-blue | shot, net 159.10 px | **still a shot** (11.5 diameters, 491.6 px/s peak, 9.7 s of rest) |
| 9003 t256-blue | shot, net 19.70 px | **not a shot**: `oscillation_no_net_travel` (1.43 diameters) |
| 9004 t265-blue | unknown (occluded) | **unknown**, and now also 148.48 mm against 100 mm with a 54.11 mm error bar = `verdict_mm: ambiguous`: the pot candidate does **not** survive the millimetre test |

Segment totals, before -> after: **shots 3 -> 1, pots 0 -> 0, unknown disappearances
1 -> 8, unresolved 0 -> 6, rejections 713 -> 701, breaks 3 -> 1.**
Rejection codes after: `disappeared_outside_pocket` 165, `motion_too_short` 161,
`no_motion_onset` 78, `track_too_short` 68, `no_still_stretch` 47,
`reappeared_after_gap` 154, **`oscillation_no_net_travel` 23**, `left_cloth` 2,
`track_ends_at_window_end` 2, `roll_without_pocket` 1 (445 of these are on tracks
other than the four above). The 6 unresolved runs sit at 23.6-31.6 px of net travel
against the 27.6 px bar; the 8 unknowns are all occluded disappearances whose
millimetre distance is also inside the error bar (31-54 mm).

### Evidence and state

- `tests/test_shot_pot_gate.py`: **63 tests + 9 subtests**, green. New coverage: a
  jittering identity that exceeds the speed rule is not a shot (both served shapes);
  an oscillation is refused by name; a run inside the bar's error bar is
  `unresolved`, in neither `shots` nor `rejections`; the served candidate's 9.62 px /
  148.5 mm / 54.1 mm ambiguity; a further sighting (12 px, 190 mm) is a named
  disagreement rejection; a ball at the hole (2 px, 32 mm) is a confident pot; the
  foot-rail ellipse; and the SAM3 census, whose 3 sparse chains near the left-side
  pocket moved from `disappeared_outside_pocket` to ambiguous unknown.
- Full suite after this work: **921 passed, 3 skipped** (the gate's 63 are part of
  it; the rest of the growth is concurrent workers' test files in the same tree).
- The wave: `tests/ball_dense_events.py` was **run read-only** (another worker owns
  it; no line needed changing) with `--output /tmp/dense-after-fix2.json`, so
  `out/dense-events/` and `out/scan30/events.json` are untouched by this work.
- **What the error bar now forbids**: at the head pockets 100 mm is 3.1 px at
  960x540, so with a 3.62 px p90 localisation error no head-pocket pot claim can be
  confirmed from the compressed direction at all - it is `unknown`, and the honest
  reading is that the far end cannot resolve this gate. The same 3.62 px also makes
  a net travel within 5.12 px of the shot bar unresolved rather than a shot. The
  gate cannot attribute a shot to a player, cannot separate a pot from a ball parked
  in the jaws (`parked_in_jaws_possible` + `unknown`), and its pot rule is only as
  good as the detector's identity persistence.

