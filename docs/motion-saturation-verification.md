# Ball-scale saturation on vod30: independent verification

Verifier: a separate worker, given one target -- **break the measurement, not the artifact**.
`out/motion_scan/vod30.summary.md` (commit `7ab1f33`) concluded that ball motion is not
measurable at 720p on this VOD and that the measurement is *saturated* (no ball can clear the
operator threshold). That conclusion drives a product decision, so it was attacked with a
different sample and different instruments wherever possible.

**No product file was touched.** Nothing under `src/`, no queue, gate or annotation. Every
number below comes from scratch code under `out/motion_verify/` (gitignored) reading the video
with the product's own channel functions imported read-only. Verify what is claimed by
re-running the scripts listed in *Reproduction*.

## What was measured, and with what

| # | instrument | evidence used | what it is independent of |
|---|---|---|---|
| 1 | contrast of the SAM3 balls against the cloth, in luma and in 7 other channels | both SAM3 caches (193 frame-times), 153 frames decoded, **1052 ball instances** | the original's assumed constant 135 |
| 2 | the ceiling: exact geometry of the channel + injection of a synthetic ball through `clip_motion` | 2 consecutive native frames of a verified-quiet stretch | the original's dilution arithmetic |
| 3 | the floor: ball17 on 14 stretches of 10 s ranked by occlusion density, YOLOv8n person boxes, 7 montages looked at frame by frame | video, `yolov8n.pt`, own channel runs | the original's control windows |
| 4 | the cross-check: ball17 at **the 78 frames where SAM3 reports >= 8 balls** | both SAM3 caches | the original's onset lists |
| 5 | optional: the same on the 1080p highlight cache (existing cache only, no scan) | `out/scan_highlight/sam3_results.json` (20 frames, snapshotted) | -- |

Two sanity checks that the instruments agree with the original where they should:

* Re-running the original's own floor definition on its own series (`out/motion_scan/vod30.series.npz`,
  `occ_dense < 0.3 & occ_share < 0.02`) gives **p99.9 = 101.53** (`n = 47434`) against the reported
  **100.51** on the control subset -- the code path is reproduced.
* On the 14 quiet windows the archived series and the fresh run agree to **0.2 %** (p99.9 72.00 vs
  72.16), so differences below are the *sample*, not the code.

## 1. The real ball-vs-cloth contrast (n = 1052 instances)

Ball core = inner 50 % of the min-enclosing-circle radius SAM3 reported; cloth ring = 1.3r..2.0r
restricted to the (2 px eroded) verified cloth quad. `contrast = |median(core) - median(ring)|`.

| statistic | luma (the channel `ball17` uses) | best single channel (B / R, whichever is larger) |
|---|---|---|
| median | **39.0** | 89.5 |
| p10 | 14.5 | 57.0 |
| p90 | 62.5 | 140.0 |
| **p95 ("best case")** | **70.0** | 145.0 |
| p99 | 87.0 | 157.5 |
| max | **101.5** | 174.0 |

By colour (luma median / max): blue 38 / 77, red 28 / 79, black 59 / 71, maroon 41 / 44,
**white cue ball 27.5 / 84**, "unknown" 49 / 101.5. **Best case = p95 (70), with the single
maximum at 101.5** -- that maximum is a white cue ball sitting in the cushion shadow at t=1363.7
(core 163 vs ring 61, seen in `out/motion_verify/probe_white.png`); the ordinary white ball on
lit cloth is 25-50.

The consequence is immediate: **the assumed 135 gray levels is 1.33x the single measured maximum,
1.55x the measured 99th percentile and 1.9x the best case used here (p95 = 70)**. On this VOD the cloth is blue and most balls are dark; in luma
they are far dimmer steps than the assumption implies. In the blue channel the same balls are
1.5-2x more distinct (median 89.5, max 174) -- the information is there at this resolution, the
luma channel is what discards it.

## 2. The recomputed ceiling

Both the exact geometry of the channel (max over window position and displacement of
`mean |f(t) - f(t-1)|` for a translating disc, x contrast) and a **direct injection**: a disc of
the measured contrast is painted on two consecutive native frames of a quiet stretch and the
product's own `clip_motion` reads it back. "Fill ceiling" = geometry; "injection" = end-to-end.

| inputs | k=9 | k=13 | **k=17** | k=25 |
|---|---|---|---|---|
| geometry, C=101.5 (measured max), median ball R=9.45 | 101.5 | 101.5 | **93.1** | 65.9 |
| geometry, C=101.5, p90 ball R=12.4 | 101.5 | 101.5 | **101.5** | 83.5 |
| geometry, C=70 (measured p95), median ball | 70.0 | 70.0 | **64.2** | 45.5 |
| geometry, C=39 (measured median), median ball | 38.8 | 38.8 | **35.6** | 25.2 |
| geometry, **C=135 (the original's assumption)** | 135.0 | 135.0 | **123.8** | 87.7 |
| injection, C=101.5, median ball, no blur | 98.8 | 98.3 | **84.7** | 60.7 |
| injection, C=101.5, p90 ball, no blur | 99.1 | 98.6 | **98.3** | 77.2 |
| injection, C=135, p90 ball, no blur | 133.1 | 132.6 | **132.3** | 104.0 |

* The original's arithmetic is **internally correct**: with C=135 it reproduces 123.8 ~ 124.
  Its input is what the footage does not support. With the measured contrast the true ceiling of
  the 17x17 luma channel is **93-101 (best case)** and **~85-98 measured end-to-end**, i.e.
  **18-25 % below the 124 the report states**.
* Window size does not rescue the measurement. k=9 raises the crude ceiling (a 9x9 window can sit
  entirely inside a changed region) but the noise rises faster than the signal -- see section 3:
  `ball9`'s quiet floor is 108.9 versus `ball17`'s 72.2, so head-room gets *worse*
  (best-case injection reading over its own quiet threshold: 0.73x at k=9, 1.09x at k=17,
  1.04x at k=25).
* What is *not* what the original says: a ball that moves does produce a reading far above the
  still-frame noise (section 3), and a **median-contrast ball cannot** (ceiling 31-36 against a
  noise floor of 36).

## 3. The independently measured floor

14 non-overlapping 10 s blocks were chosen from the whole VOD by **`occ_dense` p90 alone** (the
original's occlusion proxy; `ball17` was not used to choose anything), then each was checked with
YOLOv8n person boxes and 7 of them were looked at frame by frame in 1 s montages
(`out/motion_verify/montage/`). One of the 14 (t=1600-1610, `occ_dense` max 0.66, `ball17` max
120.7) is visibly occluded and is excluded from the "person-free" rows.

| floor sample | n frames | p99 (ball17) | **p99.9** | max | threshold x1.25 |
|---|---|---|---|---|---|
| the original: unoccluded control frames of the whole VOD | 41353 | 67.2 | **100.51** | 160.9 | 125.64 |
| 14 candidate windows (this run) | 4186 | 50.2 | 93.94 | 120.7 | 117.42 |
| **13 person-free windows** | 3887 | 44.7 | **72.16** | 80.5 | **90.20** |
| 7 windows checked frame by frame | 2093 | 36.7 | **65.51** | 79.3 | 81.89 |
| frames where **not one cloth pixel changed** (`occ_share == 0`) | 2795 | 24.0 | **36.03** | 40.8 | **45.04** |

**The floor is lower than 100.5 -- by 28 % on person-free stretches and by 64 % on frames where
the cloth does not change at all.** That is the loud version of the finding this check was asked
for: there *is* head-room below the operator's 125.6, but only in the sense that the bar is
re-calibratable; the ball's ceiling (section 2, ~98-101 at best) does not rise with it.

Per-footprint floors on the same 13 quiet windows (p99.9 -> threshold): `ball9` 108.9 -> 136.1,
`ball13w` 75.0 -> 93.7, **`ball17` 72.2 -> 90.2**, `ball25` 59.4 -> 74.2.

## 4. The decisive cross-check: the frames SAM3 sees 8-10 balls

At **all 78 frames** where the union of the two SAM3 caches reports >= 8 balls (67 of them with
`occ_dense < 0.3`, i.e. nobody at the cloth), the channel was recomputed with the product's own
code, plus the local 17x17 reading **at each SAM3 ball centre**.

| | ball17 (max over the cloth) | local reading at the balls |
|---|---|---|
| median | 22.4 | **0.29** |
| p90 | 86.8 | 3.01 |
| max | 151.3 | 78.8 |
| frames above 100.51 (original floor) | **4 / 78 = 5.1 %** | **0 / 78 = 0 %** |
| frames above 125.64 (original threshold) | 2 / 78 = 2.6 % | 0 / 78 = 0 % |
| frames above 72.16 (quiet floor) | 12 / 78 = 15.4 % | 5 / 78 = 6.4 % |

Strongest frames (all of them at the rack around the served events of t=483-486):

| t | n balls | ball17 | occ_dense | max reading at a ball |
|---|---|---|---|---|
| 484.6 | 9 | 151.3 | 0.362 | 1.5 |
| 484.4 | 9 | 137.7 | 0.570 | 50.4 |
| 486.2 | 9 | 125.0 | 0.540 | 78.8 |
| 1663.0 | 8 | 101.3 | 0.298 | 1.3 |
| 486.5 | 9 | 98.7 | 0.587 | 0.2 |
| 1619.1 | 9 | 97.9 | 0.204 | 22.9 |
| 27.5 | 10 | 97.2 | 0.159 | 9.4 |

**Read this carefully, because the obvious reading is wrong.** The SAM3 balls are real -- SAM3
detects 8-10 of them per frame *on the native 720p frames*, which by itself shows the balls are
present in the pixels at this resolution. But at those same frames the balls' own footprints are
**silent** (median local reading 0.29, and no frame at all has a ball above 100.5). A ball at rest
changes nothing between two frames, so this cross-check measures **"these balls are not moving"**,
not "the channel is blind to balls". It is a confirmation that the census balls are static at the
cached moments; the blindness question is answered by section 2, where a *moving* ball of measured
contrast is pushed through the same code and reads 58-99.

Where the reading does come from is visible too: the three largest ball17 values sit exactly on
frames with `occ_dense` 0.36-0.59 (a person at the rack), and the change is not at the balls
(local 1.5-50). The one genuinely interesting number is **78.8** -- the largest reading ever
measured at a SAM3 ball's own position, at t=486.2, immediately after the served event at 484.1,
with 9 balls visible. If that is a broken ball rather than the occluder, then a real ball on this
footage produces ~79, which clears the still-frame bar (45.0) and the quiet bar (72.2 -> 90.2 is
just above it) but is missed by the operator threshold 125.6. It cannot be separated from the
occluder with the evidence available, so it is reported as a number, not as a claim.

## 5. Optional: the 1080p highlight (existing cache only)

`out/scan_highlight/sam3_results.json` (snapshotted, 20 frames, 157 ball instances) plus
`config_for(..., "highlight")`: ball radius **15.4 px -> 31 px across, 2.7x the area** of the
vod30 median ball. Measured luma contrast: median **52**, p95 **109**, max **121**; best single
channel median 179, max 222. The channel (k=27) at those frames: median 11.7, p90 74.2, max 83.8,
**0/20 above the vod30 floor**; the largest local reading at a ball is 39.1. Same pattern as
section 4 -- cached frames are moments when the balls are at rest. The highlight is a friendlier
case in every dimension (bigger ball, higher contrast); its own floor is being measured by the
worker who owns that scan and is not duplicated here.

## Verdicts

| claim (from `out/motion_scan/vod30.summary.md`) | verdict | the numbers that decide it |
|---|---|---|
| one ball covers 266 px² and can change at most 532 px² | **CONFIRMED** | median radius 9.45 px -> area 266 px², disjoint old+new = 532 px²; pure geometry |
| a ball's best possible 17x17 footprint mean is **~124**, from an assumed contrast of **~135** | **REFUTED** | the assumption is not in the footage: luma contrast median **39.0**, p95 **70.0**, p99 87.0, max **101.5** (n=1052). Geometry with C=135 does give 123.8, so the arithmetic is right and the input is wrong; at the measured contrast the ceiling is **93-101 (geometry) / 85-98 (injection)** |
| the unoccluded-control floor is p99.9 = **100.5**, so the threshold became **125.6** | **PARTIAL** | 100.5 is reproduced exactly (101.53 from the raw series). But that sample spans 86 % of the VOD and is not a still table: on 13 person-free 10 s stretches p99.9 = **72.16**, on the 7 verified frame by frame **65.51**, on frames where no cloth pixel changed **36.03** |
| therefore **no ball can clear the bar** (the threshold sits at a single ball's best case) | **CONFIRMED as stated, PARTIAL as a general claim** | against the bar as it stands the best possible ball reads **98-101 < 125.6** -- a ~20 % margin, not the 1 % of the original arithmetic. Against a bar re-calibrated to quiet frames (**90.20**) a top-contrast ball (>= 90, the top ~1 % of instances) clears it; a **median** ball (ceiling 31-36 vs still floor 36) still does not |
| this is "not measurable at 720p", a sensor problem and not a modelling one | **REFUTED in that strong form** | SAM3 detects 8-10 balls per frame **on the native 720p frames**, so the balls are measurable at this resolution by appearance; in the blue/R channels they carry median **89.5** / max **174** contrast where luma carries 39 / 101.5; and a moving ball of measured contrast reads **58-99** through the real channel against a still-frame floor of **36**. What *is* true at 720p: in luma, and after the 17x17 dilution, the **median** ball sits at the noise floor, so a luma-only difference detector has no margin for a typical ball |
| the measurement is saturated *at the operator threshold 125.6* | **CONFIRMED** | the largest reading a single ball can produce **98-101 < 125.6**; no SAM3-visible ball over 78 frames reaches it (0/78 have a ball-local reading above 100.5) |
| 15/15 served events were occlusion, not shots | **NOT VERIFIED here** | out of scope of this check; the events sit at `occ_dense` 0.45-0.97 and nothing measured here contradicts the occluder explanation, but the event-by-event verdict was not re-derived |

## Limitations

* 153 of the 193 cached frame-times decoded (1052 instances, 0 skipped). Those frames are
  candidate/onset brackets, so the sample is biased towards moments when something happens; if
  anything, the highest-contrast ball is under-represented, which would raise the ceiling, not
  lower it.
* The injection assumes a uniformly coloured disc -- the best case for a footprint *mean* -- and
  motion along x with a box blur of 0.5x or 1.0x the displacement. Real shading can only lower
  the mean.
* The floor windows were *chosen* with `occ_dense` p90 (a candidate generator, no `ball17` used),
  then verified by YOLOv8n and by eye on 7 of the 14. A person could in principle disturb the
  cloth without YOLO noticing; the 7 montages show the table quiet, and the results are reported
  both with and without the one window that is visibly occluded.
* p99.9 over ~3000 frames is the 2nd-4th largest value: it is a legitimate reading but it carries
  sampling noise of roughly +/-10 grays; the p99 rows are given for that reason.
* CPU only, no new dependencies, no service restart, no push.
* `src/motion_scan.py` in the working tree was being edited concurrently by another worker
  (the footprint is being parameterised); nothing here writes to it. The channel functions were
  imported from that working copy at the time of the runs, and the values they produce were
  checked against the *committed* artifact: on the same 10 s windows the archived
  `out/motion_scan/vod30.series.npz` gives ball17 p99.9 = 72.00 where the fresh run gives 72.16,
  and the original floor definition on the archived series gives 101.53 against the reported
  100.51 -- so the version used is measuring the same channel.

## Reproduction

```
.venv/bin/python out/motion_verify/contrast2.py                       # contrast, 1052 instances
.venv/bin/python out/motion_verify/pick_windows.py                    # rank the quiet windows
.venv/bin/python out/motion_verify/verify_windows.py --hz 1           # YOLOv8n on them
.venv/bin/python out/motion_verify/montage.py --windows 680,1500,1680,1320,0,530,750
.venv/bin/python out/motion_verify/measure.py --windows out/motion_verify/windows.json --out out/motion_verify/floor.json
.venv/bin/python out/motion_verify/measure.py --frames out/motion_verify/sam3_ge8_frames.json --out out/motion_verify/crosscheck.json
.venv/bin/python out/motion_verify/ceiling.py                         # geometry + injection
.venv/bin/python out/motion_verify/highlight_crosscheck.py            # optional 1080p
```
