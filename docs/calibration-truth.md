# Calibration truth — the two mappings, the gate's warning, and the highlight reference

*2026-09-24 · worker `calibration-truth` · artifacts `out/calib_mapping_audit.json`,
`out/scan30/eval_calib_truth.json`, `out/scan30/probe_events_v8.json` · tool
`src/calib_mapping_audit.py`*

Three questions that all touched the same subsystem, answered with measurements.
Every number below was produced by a command in this document; the sample size
and the load are stated with it. Nothing rewrites a calibration data file, and
the three protected files are byte-identical (md5 in §5).

| question | verdict |
|---|---|
| which px↔mm mapping is authoritative? | **the hand anchors** for physical geometry; the **scan quad** is the frame the queued claims were written in, and a claim must be projected back through it |
| does the gate's calibration warning still fire on good frames? | **no** — it now comes from the per-side rail evidence; a 48-candidate re-run went 11 warnings → 0 |
| is `out/fixed_corners.json` wrong, and does it matter at 1080p? | yes, at the bottom rail only: **28.2 px ≈ 85 mm ≈ 0.92 ball diameters** inside the visible cloth; the other three sides agree within 0.5 px |

---

## 1. The 93 px / ~440 mm disagreement

### What the two mappings are

* **A — hand anchors** `out/pid_anchors_vod30.json`, six clicked pocket positions
  at t=70 (`[[532,323],[800,324],[997,569],[384,563]]` are the four cloth
  corners, `[[480,397],[865,398]]` the two side pockets).
* **B — scan quad** `out/scan30/corners.json`
  (`[[459.3,268.9],[803.7,315.8],[1023.4,584.3],[421.8,560.6]]`), written by
  `src/scan_events.py:225` as the median of the scan's own `detect_table`
  detections.

Both are homographies to the same canonical frame
(`src/pipeline.py:64 homography_to_canonical`, 1270 × 2540 mm). They are not the
same mapping, and the difference is **positional**.

### The disagreement, by position

`PYTHONPATH=. .venv/bin/python -m src.calib_mapping_audit` — 25 unique canonical
points (5×5 grid over the cloth; the six pockets coincide with grid points), both
quads, full 1280×720 frame.

| region (canonical y) | n | Δpx median | Δpx max | B's position error, mm (median / max) | mm of a 10 px error |
|---|---|---|---|---|---|
| head rail (y<400) | 5 | 38.0 | **90.7** (head-left corner) | 850.9 / 1950.6 | 143.6 perpendicular, 47.4 along the rail |
| middle | 15 | 22.2 | 72.3 | 143.7 / 994.0 | ~64 |
| foot rail (y>2140) | 5 | 55.5 | 67.6 | 110.2 / 138.9 | 33.3 perpendicular, 20.7 along the rail |

Per corner, in px: head-left **90.7**, head-right 9.0, foot-right 30.3,
foot-left 38.0. The "≈440 mm" in the earlier hand-off is `90.7 px × 4.74 mm/px`
(the head rail's *along-rail* scale); measured in A's own millimetres the same
pixel disagreement is 1950 mm at that corner, and 689 mm read the other way —
because the homography is strongly non-linear past the head rail. That is the
first reason not to convert px to mm with one scale.

### Foreshortening, quantified

| mapping | perpendicular mm/px (head / foot) | ratio | rail width px (head / foot) | along-rail mm/px (head / foot) |
|---|---|---|---|---|
| A hand anchors | 14.36 / 3.33 | **4.31×** | 268 / 613 (2.29× compression) | 4.74 / 2.07 |
| B scan quad | 10.92 / 3.61 | 3.02× | 348 / 602 (1.73×) | 3.65 / 2.11 |

The scan quad *understates* the head-rail foreshortening (3.0× against A's 4.3×)
because it pulls the head rail 348 px wide — high onto the rail and wall panels —
where the visible cloth edge is 268 px wide.

### Which one is right — three independent measurements

1. **The frames' own rail boundaries.** `src.table_refine.refine_quad_edges`
   (inner occupancy + edge drop + the dark-band-then-bright-cloth signature) run
   on real frames with each quad as the prior:

   | t | prior A | prior B |
   |---|---|---|
   | 70.0 | 4/4 verified | 2 supported, sides 0,3 unverified |
   | 0.0 | 4/4 | 2 supported |
   | 483.4 | 4/4 | 3 supported, side 2 unverified |
   | 1120.2 | 4/4 | 1 supported, sides 0,2,3 unverified |
   | 1800.0 | 2 verified + 2 inherited = 4 | 1 supported |

   The frame supports A on every sampled frame and B on none.

2. **Held-out human clicks.** Anchors 5 and 6 (the side pockets) belong to the
   same click set but took no part in fitting the four-corner quad. Under A they
   land **23.6 mm** and **18.3 mm** from the true pocket centres (0,1270) and
   (1270,1270); under B, **236.0 mm** and **166.4 mm**.

3. **Corner containment.** Three of B's four corners lie *outside* A's cloth
   (head-left by 90.7 px, foot-right by 30.5, head-right by 9.0); A's four
   corners lie inside B's larger rectangle. B is not the same physical
   rectangle, it is a bigger, rotated one.

**Verdict: A is the physical mapping. B is not a rival reference — it is the
frame the queued claims were written in.**

### Which frame wrote the queued claims (measured, not assumed)

The scan's own homography is *not* `out/scan30/corners.json` and is not
persisted: `src/info_complete_scan.py:205-212` builds it as the median of the
first 30 `detect_table` quads in **960×540** space (the `--corners` argument at
`:399` is loaded at `:407` but never used inside `scan_info_complete`).

The candidates still let us test it. Every pot carries both `last_mm` and the
pixel it was measured at (`last_cx`, `last_cy`, 960-space). Feeding `last_mm`
back through each candidate mapping and comparing with that pixel is a held-out
provenance test (`out/calib_mapping_audit.json.claim_frame_provenance`):

| candidate frame | n | median residual to the stored pixel | p90 | max |
|---|---|---|---|---|
| hand anchors A | 14 | 38.19 px | 49.71 | 59.83 |
| scan quad B (`corners.json`) | 14 | **12.88 px** | 31.88 | 33.33 |

The scan frame wins by 3×, so the claims really are scan-frame millimetres.
12.88 px is an *upper bound* on the reconstruction (the exact H is unknown);
38.19 px is a *lower bound* on the anchors' misfit.

### Where each mapping is used, and which consumer was wrong

| consumer | mapping used | right? |
|---|---|---|
| `src/eval_events.py:106 reference_calibration` → every measured mm, every pocket distance, the census | A (B only as a fallback for anchorless datasets) | **right** |
| `src/calib_segments.py:40-41` + `out/calib_vod30_segments.json` (`source: human_anchors`, `evidence.trusted_for_mm`) → the per-event reference quad | A | **right** |
| `src/table_refine.py:71 _DATASET_PRIOR["vod30"]` → the refinement's search prior | A | **right** |
| `src/event_gates.py:63 POCKETS_MM` + `nearest_pocket` (pocket radii, `pot_pocket_r_mm=100`) | canonical mm, mapped by A wherever a pixel is involved | **right** |
| `src/eval_events.py` claim projections (`geometry_gap_px`, `from/to_in_cloth_px`, `census_geometry_gap_px`) | **B was needed; A was used** | **wrong — fixed** |
| `src/info_complete_scan.py:207-212` (writes the claims' mm) | its own detector median | self-consistent; see §4 |
| `src/sam3_ball_cache.py:101,176`, `src/scan_events.py:225`, `src/timing_verify.py:778`, `src/tiny_ball_net.py:45`, `annotator/unified_server.py:476` | B, for mask/quads/detector inputs | consistent with the claim frame; none of them claims to report physical mm |

### The consumer fix (additive, no data renamed)

`src/eval_events.py:137 claim_calibration` returns the claim frame's inverse,
`Probe.claim_px` projects a claim through it, and the four claim-derived fields
now use it. `Probe.px` keeps the physical mapping for measured millimetres, and
the report carries both (`geometry_check.gap_px` and
`geometry_check.gap_px_reference_frame`).

Before/after on served candidates (same run, same cache; the projection is the
only difference) — `out/scan30/eval_calib_truth.json`:

| id | t | claim start mm | gap, claim frame | gap, reference frame (old) | Δ |
|---|---|---|---|---|---|
| 1013 | 1561.15 | [971.1, 2417.4] | 260.3 px | 207.6 px | +52.7 |
| 1049 | 1360.09 | [1051.6, 2422.2] | 347.1 | 298.4 | +48.7 |
| 1003 | 1617.52 | [1121.1, 2413.2] | 235.8 | 191.1 | +44.7 |
| 1014 | 1617.55 | [134.5, 2490.9] | 233.9 | 278.5 | −44.6 |
| 1006 | 484.86 | [44.3, 2562.3] | 285.8 | 326.4 | −40.6 |

(Largest five of the 31 shots that carry a measured start; all of them are far
above `shot_geometry_tol_px = 60`, so no verdict in this sample hinges on the
Δ. The distances are what changed.)

**Side effect, stated plainly.** The same switch moves claim points at the rails
across the `off_cloth` gate's threshold (`off_cloth_tol_px = -2`): of the 76
claim points (`from_mm`/`to_mm`) in the served candidate set, 2 were outside the
cloth under the old projection and 22 are under the claim-frame projection — 20
points that used to sit 0–6 px inside now sit 3–11 px outside. That is the true
consequence of correcting the projection (a ball centre 11 px outside the cloth
at the foot really is off the cloth, and B's reconstruction error, 12.88 px
median, is far smaller than the 38.19 px error it replaces), but it is *not*
free: it is a stricter gate on rail-adjacent shots, and it is the one change in
this round that can move verdicts. If the owner wants the old leniency back, the
place to change it is `off_cloth_tol_px`, not the projection — do not revert the
mapping.

---

## 2. The gate's calibration warning fired on correctly calibrated frames

Coverage (`calibration_frac`) is the share of the reference quad that is
cloth-hued. Measured across the calibrated VOD it runs 0.19–0.99 while the
camera never moves (whole-frame phase shift ≤ 0.74 px, `out/calib_vod30_segments.json`),
because a player standing on the cloth makes the HSV mask collapse onto the wall
panels. It fired on **11 of the 48 served candidates** in the previous run
(`out/scan30/eval_regen.json`, `calibration_weak_at_time`).

It is now a reported number only. The warning comes from the per-side rail
evidence already used by `src/calib_segment_fit` — a side counts when the search
finds the cloth boundary inside its band with the inner-occupancy, edge-drop and
dark-band-then-bright-cloth signature — measured per event by
`src/eval_events.py Probe.rail_evidence` (0.03–0.10 s per frame on this machine)
and judged by the pure `src/event_gates.py:519 calibration_warning`:

* `calibration_reference_contradicted_at_time` — a side's boundary is
  demonstrably somewhere else (`boundary_outside_band`, `prior_disagreement`);
* `calibration_rail_unverified_at_time` — **two or more** sides with no boundary
  evidence anywhere in their band: the reference does not fit the frame.

One unmeasurable side does not warn (a body covers a rail); a frame where
nothing could be measured at all (mask collapsed) is *unmeasurable*, never bad;
and `rail_evidence=None` warns about nothing.

### The two pinned cases, measured

| case | measurement | gate |
|---|---|---|
| t=483.4, t=1120.2 (the frames the old warning fired on) | 4/4 rails **verified**, coverage 0.777 / 0.800 | silent |
| t=484.1, t=1617.5, t=1661.0, t=1799.1 (the other low-coverage frames) | 0–1 side without evidence, or nothing measurable at all | silent |
| the 90 px-off scan quad at t=0/70/1120.2/1800 | 2–3 sides with no boundary evidence | **warns** |

Pinned in `tests/test_calib_mapping_audit.py` (real frames, `skipUnless` the VOD)
and `tests/test_event_gates.py` (pure gate, hand-built evidence from the same
measurements). Re-run on the same 48 candidates with the same probe cache:
`calibration_weak_at_time` 11 → **0**, and all 48 events carry `rail_evidence`
and `calibration_frac` in their gate numbers.

Honest limit: the per-side rail evidence cannot separate "the reference is
wrong" from "the player covers that rail" on a *single* side — that is why the
rule needs two sides or an explicit contradiction, and why a half-wrong
reference that still verifies three sides (the scan quad at t=483.4, 3
supported) stays silent.

---

## 3. The highlight reference has no hand anchors and its bottom rail is inside the cloth

`out/fixed_corners.json` = `[[722,452],[1177,449],[1433,844],[467,849]]` on
1920×1080 is the highlight's reference (`src/table_refine.py:76`; also
`src/eval_table_detect.py:56`, `src/motion_scan.py:303`, `src/quad_fit.py:131`,
`src/quad_fit_lines.py:209`, `src/audit_calib.py:71`). There are no hand anchors
for the highlight, so the app path gets no seed and falls back to the naive
detector on the 960×540 copy (13.28 px median against the 1.90 px full-res
result, `docs/app-path-refusal.md:123-133`).

`PYTHONPATH=. .venv/bin/python -m src.calib_mapping_audit` §`highlight_reference`,
25 frames across the 377 s highlight VOD, three definitions:

| definition of the visible cloth edge | bottom rail | other sides |
|---|---|---|
| mask edge — last cloth-hued row at the column, `detect_cloth_mask` (the definition the vod30 anchors were clicked to) | **28.24 px** inset (p10 27.79, p90 28.69, n=75) | −0.10 / 0.40 / 0.50 px |
| rail step — strongest bright→dark gradient in a ±40 px perpendicular profile, median of 21 stations (owes the mask nothing) | **28.0 px** inset (n=25, spread 27.5–28.0) | 12.5 / −1.0 / −0.5 px |
| the refinement's own per-side offset (`refine_quad_edges`) | 20.97 px — a *clipped* per-iteration number (`_MAX_MOVE_PX = 8`), not a boundary measurement | ≤ 0.5 px |

So the earlier "26–29 px" is confirmed and sharpened: **28.2 px**, i.e.
**85.3 mm** at the reference's own 3.02 mm/px at the rail, **0.92 ball
diameters** at the stated 30.8 px ball. One of 25 frames was refused by the
refinement; the other three sides are correct to within half a pixel. The
reference is *not* off by 28 px everywhere — it is one rail.

**Does it matter at 1080p?** For the 30.8 px ball: a ball resting within one ball
diameter of the foot rail has its centre mapped past y = 2540 mm (the reference
is inset, so ~85 mm of real cloth maps outside the table), which is exactly the
region where pots happen. For the app path it is *not* the current failure: the
app has no seed at all for the highlight, and that is a separate defect —
re-deriving this file's bottom rail would not give the highlight a seed.

### Options, with costs

1. **Re-derive the highlight reference from the visible cloth** — new *additive*
   artifact (e.g. `out/highlight_corners_v2.json`) built by the same per-side
   evidence, `fixed_corners.json` untouched. Removes the 28 px / 85 mm foot bias
   for every consumer that measures millimetres; the derivation is CPU-only and
   takes minutes. **But** it is derived from the same boundary evidence a scorer
   would score it with, so it can never be an independent scoring reference for
   the harness — the same circularity `docs/app-path-refusal.md` removed.
2. **Hand anchors for the highlight** — the owner clicks the six pockets on one
   highlight frame, exactly as for vod30 (the click UI already exists,
   `src/pid_anchor_ui.py`). ~10 minutes of owner time, then I wire it as
   `_DATASET_PRIOR["highlight"]` + a segment artifact + tests (~1 h). This is the
   only option that fixes *both* the rail bias and the missing seed, and it is
   the only one that gives the highlight a reference that may be scored against.
   **It cannot be automated, and no anchor data may be invented.**
3. **Accept the naive fallback on the highlight** — costs nothing, keeps the app
   path at 13.28 px median (0.43 ball diameters at 1080p) and keeps every
   highlight millimetre at the foot rail biased by ~85 mm.

**Recommended: (2), with (1) only as a stop-gap.** The measurement above settles
that the file is wrong, so "accept as is" is only honest if highlight mm are
never used; the fix that makes highlight comparable to vod30 needs human
geometry, and it is 10 minutes of the owner's time rather than another derived
loop. That is a decision for the owner, not for this worker — no anchor data was
created here.

---

## 4. What is still not decided, and what would decide it

* **The exact scan homography.** It was never persisted
  (`src/info_complete_scan.py:207-212`). `corners.json` reconstructs the stored
  pixels to 12.88 px median; persisting the estimated `H` (or its median quad)
  with the scan would make the claim-frame reconstruction exact and let the
  20-point `off_cloth` shift be re-measured against the scan's own frame.
  *Measurement:* one scan re-run with `H` written next to `raw_scan.json`.
* **Whether the 2018-line `off_cloth` strictness should move.** The fix makes the
  claim projection faithful; whether rail-adjacent `off_cloth` claims should be
  rejected is a gate-tolerance question (`off_cloth_tol_px`), not a mapping one.
  *Measurement:* the 20 flipped claims overlaid on frames — a human can decide
  whether the ball's centre is on the cloth in a few minutes.
* **The highlight reference's own authority.** Only hand anchors can settle it;
  the visible-cloth measurement (28 px, two definitions) bounds how wrong it is.

## 5. Reproduce

```bash
PYTHONPATH=. .venv/bin/python -m src.calib_mapping_audit            # §1, §3 -> out/calib_mapping_audit.json
PYTHONPATH=. .venv/bin/python -m src.eval_events \
  --candidates out/scan30/candidates_selected.json \
  --cache out/scan30/probe_events_v8.json \
  --report out/scan30/eval_calib_truth.json                        # §1, §2
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_calib_mapping_audit.py'
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_event_gates.py'
```

Protected files, md5 before and after this round: `out/corner-pocket/state.json`
`77777777777777777777777777777777`, `out/pid_seed.json`
`77777777777777777777777777777777`, `out/scan30/annotations.json`
`77777777777777777777777777777777`. No calibration data file was modified; the
two new artifacts are additive.
