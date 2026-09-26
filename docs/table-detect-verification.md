# Independent verification — table-cloth refinement (`8560109`, `9acf299`)

Verifier: separate agent, no product code edited. Everything below was measured on a
**fresh sample of frames the implementer never measured**, with scripts and overlays
under `out/table-detect-eval/verify-*` (git-ignored; this doc is the only commit).
Commands to reproduce are in §13.

## 0. Verdicts

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| 1 | `src/table_refine.py` exists, is wired into `src/frame_inference.py` and `annotator/unified_server._unified_detection` | **CONFIRMED** | code read: `detect_table_for_frame` (`src/frame_inference.py:17`), `_unified_detection` (`annotator/unified_server.py:321`), cached `_prior_for` (:276) |
| 2 | vod30 vs `corners_30min_v2.json`: median 78.4 → 4.38 px, p90 135.3 → 7.16, accept@40 0 % → 100 %, "no quad" 16 → 0, invalid geometry 12 → 0 | **CONFIRMED** in the letter (fresh: 69.86 → 4.58, p90 88.85 → 5.96, accept 0 → 97.2 %, no-quad 18 → 1, invalid 9 → 0) — **PARTIAL** in substance: the reference *is* the prior file (§3, §9.1) |
| 3 | The refined quad "measures the cloth boundary" (4.4 px is an accuracy figure) | **REFUTED** | the prior file and the scoring reference are byte-identical; the refinement moves ≤ 4.7 px from it; the reference's own TL/BR corners are 66.2 / 51.5 px from the visible cloth (§9.1) |
| 4 | vod30 vs `pid_anchors_vod30.json` (first 4 of 6): median 72.8 → 43.1 px, accept 2.3 % → 0 % | **CONFIRMED** | fresh: 76.45 → 43.06 (p90 90.5 → 43.57, max 112.76 → 45.62), accept 0 % both |
| 5 | …because those anchors are pocket-jaw centres "~44 px inside the cloth", so a correct cloth quad *cannot* pass 40 px | **REFUTED** | anchors are 2.2 / 2.0 / 28.4 / 14.0 px from the colour-cloth boundary; a quad built on cloth-boundary points scores **11.6–28.4 px** against the anchors on 5 sampled frames and passes `quadSanity` (§9.1) |
| 6 | highlight vs `fixed_corners.json`: median 1.9 → 11.7 px, accept 85 % → 100 % | **CONFIRMED** | fresh: 0.94 → 13.68 (p90 15.99 → 13.79), accept 83.3 % → 100 %; refined median is **6.6× worse** than naive |
| 7 | The saved highlight reference's bottom rail lies 26–29 px inside the visible cloth | **CONFIRMED** | visible cloth bottom edge y = 873–875 (median of 9 columns, 3 criteria) vs rail 844/849; but the refined rail (864.3–869.5) is *itself* 6–11 px inside that edge (§9.2) |
| 8 | Cost: app path 9.8 → 36.1 ms median; full-res 192 ms median | **PARTIAL** | ratios reproduced (app 4.5 → 20.2 ms = 4.5×; full 14.1 → 51.4 ms = 3.6×); absolute ms not reproducible on this machine (2–4× faster here), and their refined/naive ratio (10.7×) is not |
| 9 | "App-visible: model-quad refusals on vod30 dropped 40/45 → 4/45" | **REFUTED** | on 36 fresh frames the app paints **0** automatic quads both before and after (naive: 26 no-detection + 8 refused + 2 invalid; refined: 35 refused + 1 no-detection). Only "no quad at all" improved (26/36 → 1/36); the anchor check still rejects 35/36 |
| 10 | Four frames refused as `low_cloth_area`; occlusion never guessed | **CONFIRMED** for the 4 + 1 more; **PARTIAL** generally (partial occlusion returns a quad) | §5 |
| 11 | Tests: python 179 OK (skipped 2), timeline 33, ops 21 | **CONFIRMED** verbatim | §8 |
| 12 | `detect_table()` unchanged for existing callers | **CONFIRMED** | no diff in `src/table_detect.py` across both commits; corners and mask bit-identical to the pre-change module on 4 frames; ball-filter mask unchanged (§8) |
| 13 | "Honest failure": a stale/wrong prior yields `reason`/low confidence, never a confident wrong quad | **REFUTED** | a 120 px one-side prior error returns a quad **61–65 px wrong with confidence 0.70–0.75 and `reason=None`**; a corner-perturbed prior falls through to `refined_naive` and returns a 49–117 px wrong quad with confidence 0.13–0.45 (§3, §4) |

## 1. Sample (new, disjoint)

The implementer's used times are the union of `src/eval_table_detect.sample_times` (45 vod30 /
21 highlight) and `src/check_app_quad.run` (45 / 45). The fresh times were chosen one per equal
bin, maximising the distance to every used time:

* vod30 — 36 frames, t = 20.3 … 1793.4, **min separation 10.3 s** from any implementer frame.
* highlight — 18 frames, t = 12.6 … 365.8, **min separation 4.2 s** (126 frames at 30 fps; the
  highlight span is only 377 s and the implementer's two grids leave no larger gap).

Measurement is `src/eval_table_detect`'s own `evaluate()`/`summarise()` (same `quad_distance`,
same `quad_sanity`, same 40 px rule, full-resolution frames), driven from
`out/table-detect-eval/verify_sample.py` with a patched `sample_times`.

## 2. New-sample result (full resolution, app-style metric)

vod30 — 36 fresh frames (min separation 10.3 s):

| detector | reference | median | p90 | max | accept@40 | states |
|---|---|---|---|---|---|---|
| naive | corners30-v2 | **69.86** | 88.85 | 115.99 | 0 % | no-detection 18, off 9, invalid geometry 9 |
| refined | corners30-v2 | **4.58** | 5.96 | 10.88 | **97.2 %** | ok 35, no-detection 1 |
| naive | app-anchors@70 s | 76.45 | 90.50 | 112.76 | 0 % | (same as above) |
| refined | app-anchors@70 s | 43.06 | 43.57 | 45.62 | 0 % | off 35, no-detection 1 |

highlight — 18 fresh frames (min separation 4.2 s):

| detector | reference | median | p90 | max | accept@40 | states |
|---|---|---|---|---|---|---|
| naive | fixed-corners | **0.94** | 15.99 | 43.52 | 83.3 % | ok 15, no-detection 2, off 1 |
| refined | fixed-corners | **13.68** | 13.79 | 14.07 | 100 % | ok 18 |

So: the vod30 improvement reproduces on unseen frames (with 97.2 % instead of 100 % accept —
one fresh frame, t = 20.3, has a player over the bed and is refused `low_cloth_area`), and the
highlight *regression in median accuracy* also reproduces, larger (6.6× worse than naive).

**App path** (vod30 at 640×360 then ×2, exactly `_unified_detection`; highlight native):

| dataset | naive verdicts vs saved anchors | refined verdicts | painted frames |
|---|---|---|---|
| vod30 | no-detection 26, refused 8, invalid geometry 2 | refused 35, no-detection 1 | **0 before, 0 after** |
| highlight | painted 16 ("unverified"), no-detection 2 | painted 18 | 16 → 18 |

`annotator/app.js loadClothReference()` returns `null` unless the dataset is `vod30`, so on
highlight the automatic quad is painted as *unverified* — the 13.7 px change is app-visible
there, and on vod30 nothing is painted either way.

## 3. Falsification attempt 1 — prior staleness

`out/table-detect-eval/verify_falsify_prior.py`; see §3 — the first 10 fresh vod30 frames + the 4 reported
refusal frames (5 of those 14 have no control quad at all and are excluded — they are genuinely
unmeasurable). Control = same
frame refined from the true prior (4.1–8.4 px from the cloth reference). Residual = mean corner
distance to the control quad.

| perturbed prior | returned | residual vs control (px) | confidence | reason |
|---|---|---|---|---|
| rotation +3° | 9/9 | 12.51 – 14.88 | 0.34 – 0.75 | none |
| rotation +6° | 9/9 | 25.31 – 28.00 | 0.21 – 0.66 | none |
| top side 80 px inward | 3/9 | 49.6 – 116.5 (`refined_naive`) | 0.13 – 0.45 | `degenerate_prior` 5, `low_cloth_area` 1 |
| **corner0 +40 px, corner2 +80 px** | 3/9 | 49.6 – 116.5 (`refined_naive`) | 0.13 – 0.45 | `degenerate_prior` 5, `low_cloth_area` 1 |
| left side 120 px inward | 9/9 | 60.2 – 75.8 | 0.32 – **0.884** | none |
| top side 40 px outward | 9/9 | 18.8 – 27.5 | 0.26 – 0.45 | none |
| all sides +24 px outward | 9/9 | 14.4 – 33.5 | 0.12 – 0.45 | none |

* **It does not recover.** A one-side shift is either *held* (the true boundary is outside the
  ±34 px band, so no evidence exists and the side keeps the prior's position) or moved only
  part-way. `side_moves_px` confirms the held sides: `moves ≈ [0.25, 0.12]` where the shifted
  side should have produced `≈ 8`.
* **It is not honest about it.** The 120 px case returns a quad **61.2–65.2 px** off the control
  with confidence **0.70–0.75** and no reason. The confidence formula only uses band peak /
  edge width / scan spread and a `(4 − held)/4` factor, so an unmeasured side costs 25 % of the
  confidence and is otherwise invisible (`held_sides` is only inside `debug_info`).
* **Iters.** Every accepted frame reports `iterations = 2`, i.e. the budget ran out; the loop's
  own convergence break (`max|move| < 0.75 px`) almost never fires and nothing exposes
  "converged". `iterations = 1` appears only where nothing moved at all.
* The implementer's test `test_refinement_recovers_a_perturbed_prior` perturbs **12 px** and
  asserts `< 6.0 px` residual — see §4: that threshold is exactly the signature of a 50 %
  correction, not of recovery.

## 4. Falsification attempt 2 — the 8 px/iteration cap, and the pixel scale under it

`out/table-detect-eval/verify_falsify_cap.py`, `verify_falsify_scale.py`.

**The correction is applied at half scale.** `_side_evidence`/`_side_occupancy` measure on the
2×-downsampled mask, so a full-res offset `D` appears as `D/2`; the code then multiplies by
`mask_scale` (`table_refine.py:561,564,586`), which *cancels* the conversion. Measured, real
frame, left side, ±10 px perturbation:

```
perturbation +10 px -> reported mask_offset_px -3.50, applied side motion -3.49 px, residual 3.25 px
perturbation -10 px -> reported mask_offset_px +6.50, applied side motion +6.51 px, residual 3.73 px
```

(With the prior already 3 px inside the boundary, the true offset is 13 px; the tool moves 6.5 px of
it.) Consequences:

1. Each iteration halves the residual: **2 iterations leave 25 % of the initial error.** On their
   own synthetic bed a 12 px perturbation ends at 2.3–2.5 px per corner — which is why their
   assertion `< 6.0` passes.
2. The reported diagnostic offsets (`mask_offset_px`, `scan_offset_px`, `side_moves_px`) are in
   **half-pixel (downsampled) units**, labelled as px.
3. `_MAX_MOVE_PX = 8` is therefore a cap of **16 full-resolution px per iteration**, not 8
   (`docs/state.md` "per-side motion capped at 8 px/iteration" is wrong in full-res px). The clip
   only starts to bind for offsets ≥ 32 px; below that the ±34 px band is the limit.

**Cap/band failure — a case where convergence is impossible and the result is returned anyway**
(real frames, 5 usable frames each):

| prior error | side 3 (left) inward | side 3 outward | side 0 (top) inward |
|---|---|---|---|
| 40 px | 21.1–25.0 px residual, conf 0.70 | 15.5–19.2 px, conf 0.41 | refused → `refined_naive`, 66 px, conf 0.26 |
| 80 px | 41.1–45.0 px residual, conf 0.72 | 35.7–39.3 px, conf 0.45 | refused → `refined_naive`, 66 px, conf 0.26 |
| 120 px | **61.2–65.2 px residual, conf 0.70–0.75, no refusal** | 56.0–59.6 px, conf 0.38–0.45 | refused → `refined_naive`, 117 px, conf 0.13 |

Iteration sweep (`side3 +30 px`, real frame): residual 14.95 px at 1 iteration, 14.07 at 2,
14.47 at 3 and at 6 — it does not converge further, because the boundary is at the band edge and
the side is simply held; `reason` is `None`, confidence 0.43.
Overlays: `verify-prior-side3_inward_120px-t61.png`, `verify-prior-corner0_40_corner2_80-t61.png`.

**Answer to the question as asked:** the result is *returned as confident-but-wrong*, not refused.
The 8 px cap is not what stops it (the ±34 px band is), but both limits share the same defect: no
signal distinguishes "the frame was measured and agrees" from "this side was never measured".

## 5. Falsification attempt 3 — occlusion honesty

`out/table-detect-eval/verify_honesty.py`, overlays `verify-occlusion-*.png`.

| t | refined (full-res **and** app path) | corners | server serves | app verdict | stock-mask fill inside cloth quad | mean gray inside cloth quad |
|---|---|---|---|---|---|---|
| 849.5 | `low_cloth_area`, conf 0.0 | none | nothing (naive also empty) | nothing painted | 0.19 | 47.2 |
| 970.9 | `low_cloth_area`, conf 0.0 | none | nothing | nothing painted | 0.23 | 56.5 |
| 1618.2 | `low_cloth_area`, conf 0.0 | none | nothing | nothing painted | 0.01 | 71.1 |
| 1658.6 | `low_cloth_area`, conf 0.0 | none | nothing | nothing painted | 0.22 | 55.8 |
| 20.3 (fresh, picked as the darkest) | `low_cloth_area`, conf 0.0 | none | nothing | nothing painted | 0.35 | 45.6 |
| 1385.8 (fresh, occluded) | accepted, conf 0.252 | kept | refined quad | refused by the app (54.8 px) | 0.60 | 56.8 |
| 1120.7 (fresh, occluded) | accepted, conf 0.323 | kept | refined quad | refused by the app (48.8 px) | 0.79 | 58.4 |
| 70.0 (reference frame) | accepted, conf 0.683 | kept | refined quad | refused by the app (43.0 px) | 0.98 | 89.3 |

The four reported refusals reproduce exactly, at both resolutions, with no quad drawn anywhere —
the frame at t = 849.5 (`verify-occlusion-t849.5.png`) has a player across the whole foot rail.
`low_cloth_area` is an accurate reason (mask fill 0.01–0.23 against 0.98 on a clean frame).
Two fresh occluded frames are **not** refused: partial occlusion is by design returned with a
lower confidence, and there the confidence (0.25/0.32) is at least lower. The risk is that a
*stale prior* produces the same signature (§3) with confidence up to 0.75.

## 6. Falsification attempt 4 — dark/blank/first frames

No crash anywhere; reasons are honest and confidence 0.0 (`verify_honesty.py`, part C):

* black 1280×720 + vod30 prior → `low_cloth_area`, corners none; black 640×360 + prior/2 → same;
  black 1920×1080 + highlight prior → same; white 1280×720 + prior → `low_cloth_area`;
  black with no prior → `no_cloth_area`.
* black frame through `Backend._unified_detection` for both datasets → `corners = None`,
  `balls = []`, no exception.
* t = 0.00 / 0.02 / 0.5 of both VODs decode and produce refined quads (vod30 t = 0: 11.65 px vs the
  cloth reference, naive 74.71; highlight t = 0: 14.01, naive 74.81): no crash, `reason=None`,
  confidence 0.57/1.0. Overlays `verify-first-frame-*.png`.

## 7. Falsification attempt 5 — server / live wiring

`verify_honesty.py` part D, `verify-honesty.json`:

* `_prior_for(dataset)` is keyed per dataset and returns that dataset's own file; an interleaved
  sequence `highlight, vod30, bogus, highlight, vod30` returns each dataset's prior exactly
  (bit-identical to `prior_for()`), `bogus → None`, and a Backend rooted at a foreign directory
  (no `out/` there) → `None` (falls back to naive). No stale-prior path found.
* `_unified_detection('vod30', 7, …)` and `('highlight', 7, …)` return different quads (42.86 px vs
  the vod30 anchors / 13.88 px vs the highlight reference), the (dataset, frame) cache returns the
  same value on repeat, and 4 threads × 3 calls mixing both datasets produced no errors and one
  stable result per dataset.
* Live path: `LiveProcessor` calls `self._infer(frame, self._detectors, self.root)`
  (`annotator/live_processing.py:211`) with **no** `dataset`, so `detect_table_for_frame` gets
  `prior=None` and returns the naive corners — `infer_frame(dataset=…)` has no production caller
  at all. Safe (no prior can be wrong), but the refinement does not reach the live view or the
  cold-frame inference path.

## 8. Falsification attempt 6 — offline tools

* `git diff 8560109^..HEAD -- src/table_detect.py` → empty.
* The pre-change module (from `git show 8560109^:src/table_detect.py`) imported side by side
  returns **bit-identical** corners and masks at t = 20.3, 70, 101.8, 849.5; the dict is still
  exactly `{corners, mask, debug}`.
* Existing call sites (`src/pipeline.py`, `src/scan_events.py`, `src/info_complete_scan.py`,
  `src/rebuild_events_v2.py`, `src/ball_detect.py`) are untouched and still import
  `table_detect.detect_table`.
* The refined path returns `mask = detect_cloth_mask(bgr)`, bit-identical to the naive mask, so
  `detect_ball_candidates(small, table['mask'])` is unaffected.
* Tests: python `Ran 179 tests … OK (skipped=2)`; `node tests/test_app_timeline.js` → 33 passed,
  0 failed; `node --test tests/test_ops.js` → 21 pass, 0 fail.

## 9. The two reference-geometry claims (§5 in the directive)

### 9.1 "The anchors are pocket-jaw centres ~44 px inside the cloth; a correct cloth quad cannot pass 40 px" — REFUTED

Because `detect_cloth_mask` merges the carpet, the rail shadow and the cloth into one component
(the module's own docstring says so), any conclusion drawn from that mask is unsafe. I built an
independent **colour** mask: pixels within BGR distance 60 of the table-bed median colour
(bed BGR (190, 111, 45) at t = 70), morphologically cleaned, largest component containing the table
centre; it covers 10.4 % of the frame (the documented table quad is 9.5 %). Visual check:
`verify-cloth-truth-t70.png`, zooms in `verify-anchor-zoom-{0..3}.png`.

Distance from each point to the nearest visible-cloth pixel / to the cloth boundary, at t = 70:

| point | cloth-colour at the point | nearest cloth px | nearest cloth boundary px |
|---|---|---|---|
| anchor 0 [532, 323] | no | 3.2 | 2.2 |
| anchor 1 [800, 324] | yes | 0.0 | 2.0 |
| anchor 2 [997, 569] | no | 29.2 | 28.4 |
| anchor 3 [384, 563] | no | 15.0 | 14.0 |
| v2/prior TL [454.9, 307.8] | no | **67.0** | **66.2** |
| v2/prior TR [799.5, 319.4] | no | 2.7 | 1.7 |
| v2/prior BR [1023.8, 573.1] | no | **52.3** | **51.5** |
| v2/prior BL [449.6, 563.5] | yes | 0.6 | 1.5 |
| refined TL [452.6, 310.5] | no | **67.5** | **66.7** |
| refined BR [1020.0, 573.3] | no | **49.2** | **48.4** |

The anchors are 2–28 px from the cloth (mean 11.7); the *reference* is the outlier at TL (66 px)
and BR (52 px), and the refined quad inherits it. The claimed contrast ("anchor cloth-mask
coverage 0.27–0.68 against 0.0 at the cloth corners") is also not reproducible with the stock mask:
anchors 0.54 / 0.57 / 0.97 / 0.62, corners30-v2 corners 1.00 / 0.35 / 0.04 / 0.62.

**Counterexample to "structurally un-drawable":** take, for each anchor, the nearest cloth-boundary
pixel → quad `[[531, 325], [800, 322], [979, 547], [385, 549]]`, which `quadSanity` accepts, scores
**11.67 px mean (max 28.4)** against the app's anchors and **passes 40 px**. Repeated on 5 unrelated
frames: 11.6 / 11.8 / 16.2 / 24.2 / 28.4 px — always below tolerance. A correct cloth quad is
drawable today; what is un-drawable is the quad seeded from the stored reference.

### 9.2 "The saved highlight reference's bottom rail lies 26–29 px inside the visible cloth" — CONFIRMED

Vertical scans at 9 columns across the foot rail, 8 frames (the implementer's 5 plus 3 fresh):
the visible cloth bottom edge is y = 873–875 by three independent criteria (colour-cloth mask,
cloth hue band, saturation drop), the saved reference is at y = 844 / 849 → **26–31 px inside**.
But the refined rail (864.3–869.5) is still **6–11 px inside** that edge: the refinement measures
that edge and stops short, exactly as the halving + 2-iteration budget predicts
(28.5 px offset → 14.3 → 7.1 px residual). Overlays `verify-highlight-rail-t*.png`.

## 10. Claims I could NOT reproduce

1. **The 44 px inter-anchor/cloth offset** ("anchors ~44 px inside the cloth boundary"): measured
   2.2 / 2.0 / 28.4 / 14.0 px. The 43 px figure is the anchor-to-*reference* distance, not the
   anchor-to-cloth distance.
2. **"Accept 100 %" on vod30**: 97.2 % (35/36); the fresh sample contains a frame the implementer's
   grid never hit (t = 20.3, refused `low_cloth_area`).
3. **"App-visible refusals 40/45 → 4/45"**: the app paints nothing in either configuration;
   the change is "no quad at all" 26/36 → 1/36.
4. **Absolute cost** (app path 9.8 → 36.1 ms, full-res 192 ms): my machine measures 4.5 → 20.2 ms
   and 14.1 → 51.4 ms. Ratios agree; absolute values and their refined/naive ratio (10.7×) do not.
5. **`_MAX_MOVE_PX = 8` as a per-iteration cap**: the applied motion is capped at 16 full-res px
   and the value the clip sees is a quarter of the full-res offset.
6. **The "perturbed-prior recovery" test as evidence of recovery**: it passes with a 50 % error
   (12 px in, 2.3–2.5 px per corner out) because its threshold is `< 6.0`.
7. **The claimed anchor-vs-cloth-corner mask-coverage contrast** (§9.1).
8. **"Measure" rather than "does not drift from the seed"**: with the reference supplied as the
   prior, the 4.4–4.6 px median cannot distinguish a detector that tracks the cloth from one that
   returns its seed (measured drift at t = 70: 4.66 px mean, 7.36 px max).

## 11. Confidence and caveats

* High confidence (direct measurement, reproducible, numbers in the JSON artefacts): claims 1, 2
  (letter), 4, 6, 10, 11, 12 and every §3–§8 falsification result.
* Medium-high: §9.1/§9.2 — the conclusions rest on my own single-frame colour segmentation. The
  threshold (BGR radius 60, 10.4 % coverage against the documented 9.5 %) and the visual overlays
  are provided so the result can be re-judged; the 5-frame stability check (11.6–28.4 px floor)
  and the 26–31 px highlight result do not depend on any single frame.
* Not established by me: browser-level behaviour (I modelled `validateCloth` and
  `loadClothReference` from `annotator/app.js` rather than running the GUI), and long-run
  temporal behaviour (my sample is 54 frames, not a full-VOD scan).
* The one genuinely valuable part of the change stands: on vod30 the "no quad at all" cases drop
  from 18/36 to 1/36 and the quad lands 4.6 px from the reference it was seeded with. The
  headline number is a no-drift measure, not an accuracy measure, and the app still paints
  nothing on vod30.

## 12. Artefacts

| path (under `out/table-detect-eval/`) | content |
|---|---|
| `verify_sample.py` / `verify-sample.json` / `verify-sample.txt` | fresh sample, full-res naive vs refined, both references |
| `verify_falsify_prior.py`, `verify-prior.json` | §3 perturbation battery |
| `verify_falsify_cap.py`, `verify-cap.json` | §4 cap/band battery (synthetic + real) |
| `verify_falsify_scale.py`, `verify-scale.json` | §4 half-scale proof (reported vs applied) |
| `verify_honesty.py`, `verify-honesty.json` | app path, occlusion, dark/blank, server wiring |
| `verify_cloth_truth.py`, `verify-cloth-truth.json`, `-stability.json` | §9.1 independent cloth boundary |
| `verify_refs.py`, `verify-refs.json` | §9.2 highlight rail + §8 offline checks |
| `verify_zoom_cost.py`, `verify-zoom-cost.json` | anchor zooms + cost |
| `verify-cloth-truth-t70.png`, `verify-anchors-t70.png`, `verify-anchor-zoom-{0..3}.png` | contested anchor geometry |
| `verify-prior-side3_inward_120px-t61.png`, `verify-prior-corner0_40_corner2_80-t61.png` | contested stale-prior results |
| `verify-occlusion-t*.png` (7), `verify-first-frame-*.png` (6) | occlusion and first-frame evidence |
| `verify-highlight-rail-t*.png` (8) | highlight bottom-rail claim |

## 13. Reproduce

```bash
cd <repo>
export PYTHONPATH=.:out/table-detect-eval
.venv/bin/python out/table-detect-eval/verify_sample.py
.venv/bin/python out/table-detect-eval/verify_falsify_prior.py
.venv/bin/python out/table-detect-eval/verify_falsify_cap.py
.venv/bin/python out/table-detect-eval/verify_falsify_scale.py
.venv/bin/python out/table-detect-eval/verify_honesty.py
.venv/bin/python out/table-detect-eval/verify_cloth_truth.py
.venv/bin/python out/table-detect-eval/verify_refs.py
.venv/bin/python out/table-detect-eval/verify_zoom_cost.py
```

## 14. Suggested follow-ups (not part of this verification)

1. Fix the `mask_scale` unit error (`table_refine.py:561,564` vs `:586`) — one iteration should
   land the side on the measured boundary; the `_MAX_MOVE_PX` comment then means what it says.
2. Make a *held* side visible: expose `converged`/`held_sides` and treat "held because no evidence
   in the band" as a refusal (or a much lower confidence), so a stale prior cannot look like a
   partial occlusion.
3. Re-anchor the vod30 reference (or score against the colour-cloth boundary): the stored
   `corners_30min_v2.json` TL/BR corners are 66 / 52 px outside the visible cloth, and the app's
   40 px bar is therefore unsatisfiable by any quad seeded from it — while a cloth-correct quad
   would score ~12 px against the saved anchors.
