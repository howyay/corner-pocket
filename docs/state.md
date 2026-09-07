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
