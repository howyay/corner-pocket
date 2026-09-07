# Measured state (append-only)

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
