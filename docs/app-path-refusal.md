# Why the app path refuses quads the offline harness scores at 4.58 px

Measured at `HEAD` = `4bfe889` (`src/table_refine.py` blob `4bfe889b62a07`, see the sha1 the
harness stamps), 15 vod30 frames (the four `low_cloth_area` frames t=849.5/970.9/1618.2/1658.6
plus eleven fresh ones), with `out/app_path_probe.py` and `out/cloth_edge_probe.py`.

## 1. The app path does not shift the quad — a 2x scale error is not what happens

The app path (`annotator/unified_server.Backend._unified_detection`: 640x360 copy, cached
`_prior_for` scaled by 1/2, corners scaled back by 2) and the full-resolution path the offline
harness scores produce **the same quad to 1.0-2.95 px mean per corner** (median 2.51 px over the
frames where both return one; per-corner max 5.5 px). Both score the same against both
references:

| path | vs `corners_30min_v2` median | vs the hand anchors median | app verdict vs anchors |
|---|---|---|---|
| app (640x360) | 5.30 px | **43.22 px** | 0/15 drawn (10 off, 5 no detection) |
| full-res (1280x720) | 4.65 px | **43.03 px** | 0/15 |

So the app's refusal is not a downscale/scale artefact: the full-resolution quad fails the app's
rule by exactly the same margin. `out/app-path-probe-auto.json` has the per-frame table.

## 2. The refusal is the app's clearance reference, and it is *correct*

`annotator/app.js` validates the quad against the first four of the six hand anchors
(`out/pid_anchors_vod30.json`) with a 40 px mean-corner bar. The refined quad sits 43.0-43.2 px
from them on every frame — 3 px over the bar — and the residual is dominated by the left side:
per-corner 79 / 5 / 23 / 64 px at t=61.

The visible cloth says the app is right. Scanline runs of the cloth hue
(`out/cloth_edge_probe.py`, t=61, `|H-106|<=16, S>=105, V>=55`):

| row y | visible cloth left edge x | anchors' left rail x | refined/v2 left rail x |
|---|---|---|---|
| 330 | 521 | 528 (-7 px inside) | 454 (**67 px outside the cloth**) |
| 400 | 475 | 485 | 453 |
| 470 | 430 | 441 | 452 |
| 520 | 398 | 411 | 451 |
| 560 | 380 | 386 | 450 (**70 px inside the cloth**) |

The cloth's left edge slants (slope ~-0.6 px/px); the anchors track it within 6-13 px; the refined
quad's left rail is nearly vertical and *crosses* the cloth edge around y=430. A quad whose left
side is 67 px outside the table at the top and 70 px inside at the bottom is not drawable.

## 3. The 4.58 px is a self-score, not accuracy

`src/table_refine.prior_for('vod30')` reads `out/corners_30min_v2.json` — byte-identical to the
`corners30-v2` reference `src/eval_table_detect.py` scores against. The refinement moves 4.6-8.4 px
from that prior, so "4.58 px median / 97.2 % accept" measures *how far the refinement moved from
its own seed*. Seed the same refinement from the anchors instead and the numbers swap exactly:
6.4 px from the anchors, 43 px from `corners_30min_v2`.

That is also why the app never draws: the detector's search centre is 67-90 px off the visible
cloth on the left, and both the band (+-34 px before the widen-in-flight change) and the
mean-occupancy crossing (which pins a side where *half* the scan lines are covered, i.e. where the
wrong rail happens to cross the cloth edge) keep it there.

## 4. Two real defects on the way

* `src/table_refine.py` (another worker's file this round, **not touched here**): each side
  advances only **half** the frame-pixel correction it measures — `chosen[s]` is already converted
  to frame pixels at `cross * mask_scale`, then divided by `mask_scale` again before `_shift_side`,
  so the +-8 px clip also binds at 32 px. Measured `applied/reported = 1.011` (n=37, correct = 2.0).
* `annotator/unified_server.start_inference` calls `infer_frame(frame, detectors, root, progress)`
  with no `dataset=`, so the saved frozen-frame inference polygon is the **naive** quad (measured
  131 px from the anchors at t=427.8) while every other surface shows the refined one; `app.js`
  paints that polygon. Reported, not changed here.

## 5. What the fix does

`src/frame_inference.app_prior_for` is the app path's only seed: the dataset's saved hand
anchors (its earliest saved time, first four of six) or **None** — never
`out/corners_30min_v2.json`, which is a measured-bad seed (67-90 px off the visible cloth on its
left rail). The refinement, its evidence gates and its honest refusal are unchanged; only the
search centre moves. `annotator/unified_server.Backend._prior_for`,
`src.frame_inference.detect_table_for_frame`, `src.frame_inference.infer_frame` and
`src/check_app_quad` all resolve it through that one function, so the browser, the cold-path
inference job and the offline app-visible harness cannot disagree about the seed. A dataset with
no anchors gets no refinement prior and keeps its documented naive fallback
(`reason='no_prior'`), rather than a reference of unknown quality.

Verified on the same 15 frames, `--refine-rev HEAD --prior auto` (the real server path, seed now
resolved to the anchors), `out/app-path-probe-fixed.json`:

| app path (640x360) | before | after |
|---|---|---|
| vs the hand anchors, median | 43.22 px | **6.43 px** (p90 8.07, max 27.82) |
| vs `corners_30min_v2`, median | 5.30 px | 42.95 px (the old self-score, now the honest gap) |
| app verdict vs anchors | 0 ok / 10 off / 5 no detection | **11 ok** / 0 off / **4 no detection** |
| frames drawn | 0/15 | **11/15** |

The four refusals are the four `low_cloth_area` frames (t=849.5/970.9/1618.2/1658.6) plus t=20.3,
a player standing over the bed - they are refusals, not failures, and they stay refusals.

Also fixed here: `annotator/unified_server.start_inference` called
`infer_frame(frame, detectors, root, progress)` with no `dataset=`, so the saved frozen-frame
inference polygon that `app.js` paints was the **naive** quad (131 px from the anchors at
t=427.8). It now names its dataset, and `infer_frame` resolves the prior under its own `root`.

**Caveat, stated plainly**: seeding from the reference weakens the app's check as an *independent*
test of the table's position - it now bounds the refinement's drift from the operator's hand
geometry ("the quad did not wander more than 40 px from the saved corners") instead of asking "is
this quad the table". The independent evidence for a drawn quad is the frame's own cloth evidence
(the refinement's per-side gates) plus the scanline measurement in §2. The Vision facts line now
prints the measured drift (`quad drift vs saved corners 6.4 px (tol 40 px)`) rather than only the
pass/fail, so the number is visible to the operator.

Still open, not in this worker's files: `src/eval_table_detect.py --detector app` seeds
`detect_table_refined` with `prior_for(dataset)` and scores it against the same file, so the
full-resolution "4.58 px / 97.2 %" headline remains a self-score - it is now the only place that
still does this.
