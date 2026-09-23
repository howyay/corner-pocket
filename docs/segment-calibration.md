# vod30 per-segment calibration — measured, and the answer is one segment

*2026-09-23 · worker `segment-calib` · artifact `out/calib_vod30_segments.json`*

## The claim under test

A gate report on the served event queue measured the reference cloth quad's
coverage at `0.85–1.00` early and `0.38–0.82` at `t=450 / 483 / 1120`. Coverage
here is `calibration_frac`, the share of the reference quad that is cloth-hued at
that time. `docs/state.md` has warned since the start that **calibration is per
segment** and a single `H` must not be reused, so the working hypothesis was a
camera move that invalidated table-millimetre geometry in the late VOD.

## What the measurement found

`src/calib_segment_measure.py` samples the VOD (`t=0..1800`, every 60 s, plus the
candidate windows) and measures four independent things per frame: the coverage
proxy, the whole-frame phase correlation against the `t=0` anchor, the cloth
region's own HSV, and the per-side refinement evidence from `src/table_refine`
(mask crossing + inner occupancy + edge drop + dark-rail/bright-cloth signature).

| probe | early (t≤360) | late (t≥420) | verdict |
|---|---|---|---|
| whole-frame phase shift vs `t=0` | ≤ 0.13 px | **≤ 0.74 px** (max, t=1800) | the camera never moves |
| refined cloth side lengths | 277/317/622/285 px | 278/317/623/284 px at t=1800 | no pan, no tilt, no zoom |
| verified per-side rail offsets vs the hand anchors | −2.9 / −1.8 / +4.3 / 0.0 px | same values at t=1740 and t=1800 | constant bias, not drift |
| coverage (`calibration_frac`) | 0.986–0.989 | 0.19–0.99, dips at 450/483/1080/1200/1800 | the **only** thing that moves |

At `t=483.4` (coverage 0.777) and `t=1120.2` (coverage 0.800) **all four sides
verify** against the hand-anchor quad, with offsets inside 4 px and the full rail
signature present. The extract in `out/segcalib/probe_t04834.jpg` and
`probe_t11202.jpg` shows why: a player is standing over the cloth, and the loose
cloth mask collapses onto the wall panels and the shirts.

**There is no camera move. The coverage drop is occlusion and shading**, which the
proxy cannot distinguish from a moved camera. `desaturated_frac` inside the quad
rises from 0.02 to 0.07–0.21 at exactly the low-coverage samples.

## The artifact

`out/calib_vod30_segments.json` (additive; no existing calibration file rewritten)
carries one segment `vod30-s1`, `t=0..1800`, `source: human_anchors` — the first
four of the six hand anchors at `t=70`, unchanged — with the per-frame evidence,
the per-side offset distribution, and the `boundary_candidates` list where every
entry is `cause: occlusion_and_shading`, `framing_change: false`.

`late_window_alternative` records what a split *would* look like: the componentwise
temporal median of the 23 late-window refined quads, `source: derived`,
`used: false`. Its per-side evidence gate **does not pass** — at `t=483.4` and
`t=1120.2` it verifies fewer sides than the human quad does. And its corner deltas
(9.3 / 2.5 / 1.5 / 7.4 px) translate to up to **141.7 mm** of canonical-table
disagreement at the far head rail, because the head rail runs at ~4.7 mm/px. That
is the quantified reason not to replace trusted human geometry with a derived quad
on evidence that does not support it.

## Answer to the explicit questions

* **Is the shift a genuine camera move?** No. Whole-frame phase correlation never
  exceeds 0.74 px in 30 minutes, and the cloth's projected side lengths are stable
  to 6.6 px.
* **Can the segment be solved from the source?** There is no segment to solve.
* **Should vod30 be split into two datasets?** Not for calibration. If a split is
  wanted for review, split it on *occupancy* grounds (how often players stand over
  the cloth), not on framing.

## Before / after

`src/segment_calib_report.py` re-measures all 36 candidates four times through the
existing `eval_events` probe + `event_gates` judge, with the SAM3 census store
frozen so a concurrent writer cannot be mistaken for a calibration effect. Columns:
`anchors` (today's single `H`), `segment` (the new per-time lookup), `derived_late`
(counterfactual split at the first below-gate sample), `anchors_repeat` (the same
reference again — the noise floor).

`calibration_frac` per sampled frame:

| t | anchors | segment | derived_late |
|---|---|---|---|
| 0 | 0.999 | 0.999 | 0.999 |
| 420 | 0.787 | 0.787 | 0.791 |
| 450 | 0.382 | 0.382 | 0.376 |
| 483.4 | 0.812 | 0.812 | 0.817 |
| 941.5 | 1.000 | 1.000 | 0.999 |
| 1080 | 0.393 | 0.393 | 0.390 |
| 1120.2 | 0.802 | 0.802 | 0.808 |
| 1200 | 0.543 | 0.543 | 0.554 |
| 1800 | 0.635 | 0.635 | 0.639 |

Verdicts over the 36 candidates:

| reference | confirmed | rejected | unconfirmed | candidates whose class changes |
|---|---|---|---|---|
| `anchors` | 2 | 27 | 7 | — |
| `segment` | 2 | 27 | 7 | **0** |
| `anchors_repeat` | 2 | 27 | 7 | **0** (deterministic with the census store frozen) |
| `derived_late` | 2 | 28 | 6 | 1: `t=1120.16` shot unconfirmed → rejected |

So wiring the per-segment lookup changes **no** verdict, and no
`calibration_frac`, because the evidence puts the whole VOD in one segment. The
only candidate whose geometry class moves at all is `t=1120.16`, and it moves under
the *derived* reference that the per-side gate rejects — which is the argument
against adopting it. `t=483.36` (the late shot the queue keeps) is
`confirmed / tier: geometry` with `calibration_frac = 0.812` under both references.

## Where it is wired

* `src/calib_segments.py` — the time → reference lookup (see below).
* `src/table_refine.prior_for` / `prior_provenance` — the table-detection prior is
  per segment; a tree without the artifact answers exactly as before.
* `annotator/unified_server.py` — every projected event carries the additive
  `px_segment` naming the segment that owns its time. The **pixels move only when
  the artifact reports a split** (`segmentation_verdict: split_supported`), because
  on a single-segment artifact the dataset-level projection already describes the
  one framing that exists; re-projecting through the cloth quad instead is a
  different question, and a visible one — on vod30 the scan's own homography puts
  the cloth head-left corner at table mm (267, 640) while the hand anchors put it
  at (0, 0), so the two mappings disagree by up to **93 px** at the head rail,
  which is a property of the scan's homography and not of any camera move.
  `tests/test_calib_segments.py::EventProjectionWiringTest` pins both branches.

## What this does not fix

* `calibration_frac` remains a confounded proxy. The gate's
  `calibration_warn_fraction = 0.80` fires on correctly calibrated late samples.
  The occlusion-robust reading is the per-side rail evidence
  (`evidence.per_side_offset_px`, `framing_test.samples[].verified_sides`), and the
  camera-move reading is `phase_shift_px`.
* `src/eval_events.py` builds one `Probe` with one homography and cannot consult a
  per-time reference without an edit; that file belongs to another worker this
  round. The seam is one line there: build the probe's `forward`/`inverse`/`quad`
  from `src.calib_segments.Segments.homographies(t)` for the event's own `t`, the
  way `src/segment_calib_report.py`'s `PerTimeProbe` does. Until then
  `out/segcalib/segment_calib_report.json` carries the per-candidate numbers, and
  the served `px_segment` field says which segment each event belongs to.
* The scan's own homography and the hand-anchor geometry disagree by up to 93 px /
  ~440 mm at the head-left corner. That is a **pre-existing** geometry problem,
  larger than the segmentation question and independent of it: it is why the
  event pixel projection and the gate's millimetre measurements do not share one
  reference. It needs its own round.
* The hand anchors sit ~3 px inside the left rail and ~4 px outside the foot rail.
  That bias is present at `t=0` and is not a segmentation effect, but at ~4.7 mm/px
  on the far rail it is worth a fresh anchor pass (HOM-1).

## Commands

```bash
.venv/bin/python src/calib_segment_measure.py        # GPU-free, ~35 s
.venv/bin/python src/calib_segment_fit.py            # writes the artifact
.venv/bin/python src/segment_calib_report.py         # before/after, ~8 min
.venv/bin/python -m unittest discover -s tests -p "test_calib_segments.py"
```
