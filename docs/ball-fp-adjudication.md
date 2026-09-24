# Ball detector: adjudicating the 15 false positives

**The one number:** of the 15 held-out detections the teacher called false, **6 are real
balls** and **9 are the student's own errors**. Of the 6, four sat at SAM3 scores the
production cut (0.62) discarded — teacher recall the pipeline threw away — and two are
balls production kept.

**Why this document exists.** `src/tiny_ball_net.py` reports held-out F1 0.927 (median
1.48 px, p90 3.62 px) on `out/tiny_ball_probe/report_960x540.json`. That number is measured
against SAM3, which is a **teacher, not ground truth**. So the report's 15 detections with no
label and 22 labels with no detection were ambiguous by construction: a "false positive" is
either a student hallucination or a teacher miss. Nothing in the report distinguished them,
and the honest fix is a third measurement, not 15 crops on a human's desk.

Tool: `src/ball_fp_audit.py` (new). Tests: `tests/test_ball_fp_audit.py` (new, 54 tests).
Crops: `out/ball-fp-audit/` (37 PNGs, one per case).

## Method

The whole audit rests on one fact about the teacher caches:

> Every label in `out/scan30/sam3_census.json` and `out/scan30/sam3_results.json` was written
> with the production score cut already applied. Across all 194 frames the **minimum stored
> score is 0.6245**. A teacher instance the student found *below* 0.62 is therefore **absent
> from the labels, not refuted by them.**

So the labels cannot answer the question, and the answer needs a fresh SAM3 pass whose
confidence floor is below the cut.

1. **Rebuild the disputed set.** Load `out/tiny_ball_probe/960x540-scratch.pt`, run the student
   on the 47 frozen held-out frames, and reproduce the report's errors at the report's own
   operating threshold (0.425, read from the JSON rather than re-chosen). Result: **exactly
   15 FPs and 22 FNs**, matching `report_960x540.json` field for field. The audit adjudicates
   the published errors, not a fresh set of them.
2. **Buy a third measurement** on the 14 distinct frames carrying a false positive (15 FPs, 2
   of them on one frame). `Sam3Processor.confidence_threshold` is lowered to **0.15** and the
   prompt is the same `"billiard ball"` the caches used; every instance it returns is kept.
   One forward pass yields all four sweep thresholds (0.20 / 0.35 / 0.50 / **0.62**), so the
   sweep is free once a frame is paid for. **0.62 is the production cut: any instance below it
   is teacher recall that production threw away.**
3. **Adjudicate** each FP at the disputed point: every SAM3 instance within **10 px**, with its
   offset, score, area, radius and on-cloth flag, plus the nearest instance's offset so a
   near-miss stays visible. Verdict rules:

   | verdict | condition |
   |---|---|
   | `teacher_recall` | an instance **inside the teacher's own ball gate** (area 60–9000, r 4–60, on the reference cloth) within 10 px, at score ≥ 0.20 |
   | `student_hallucination` | no instance within 10 px at any swept threshold |
   | `unresolved` | an instance is present but fails the gate; the score is below the audit's own 0.20 floor; or the frame was never measured |

   The gate is the teacher's own definition of a ball, mirrored from `src.sam3_ball_cache.py`
   and asserted against it by a test. `unresolved` exists so that **silence is never read as a
   hallucination** — an unmeasured frame cannot become evidence.

4. **The mirror test for the 22 FNs** costs no SAM3: their teacher instance and score are
   already in the labels. The student's heatmaps are re-thresholded on the frozen report's own
   `0.05 + 0.025 i` grid, so the recovery count and the precision/recall cost are the same
   measurement rather than two that have to be reconciled.
5. **One crop per case** under `out/ball-fp-audit/`, 180×180 native px at 3× zoom, with the
   disputed point crosshaired, the student's peaks in red, the teacher's label in green, the
   sweep's instances in cyan (below the cut) or orange (at or above it), the scores printed in
   the image, and a thumbnail locating the crop on the table. The picture is the checkable
   artifact; the verdict is the thing to check, not the thing to trust.

## Per-case verdicts

| case | t (s) | student | nearest inst (offset / score) | justifying inst (offset / score) | verdict | why |
|---|---|---|---|---|---|---|
| fp01 | 43.7 | 0.49 | - | - | **student_hallucination** | no_instance_within_radius_at_any_threshold |
| fp02 | 234.6 | 0.51 | - | - | **student_hallucination** | no_instance_within_radius_at_any_threshold |
| fp03 | 235.4 | 0.50 | - | - | **student_hallucination** | no_instance_within_radius_at_any_threshold |
| fp04 | 236.7 | 0.47 | - | - | **student_hallucination** | no_instance_within_radius_at_any_threshold |
| fp05 | 237.5 | 0.47 | - | - | **student_hallucination** | no_instance_within_radius_at_any_threshold |
| fp06 | 1078.1 | 0.54 | - | - | **student_hallucination** | no_instance_within_radius_at_any_threshold |
| fp07 | 1078.1 | 0.44 | - | - | **student_hallucination** | no_instance_within_radius_at_any_threshold |
| fp08 | 1079.2 | 0.47 | - | - | **student_hallucination** | no_instance_within_radius_at_any_threshold |
| fp09 | 1080.2 | 0.53 | - | - | **student_hallucination** | no_instance_within_radius_at_any_threshold |
| fp10 | 1364.0 | 0.72 | 0.8 px / 0.84 | 0.8 px / 0.84 | **teacher_recall** | instance_at_or_above_production_cut |
| fp11 | 1650.0 | 0.85 | 6.5 px / 0.86 | 6.5 px / 0.86 | **teacher_recall** | instance_at_or_above_production_cut |
| fp12 | 1777.5 | 0.81 | 1.8 px / 0.41 | 1.8 px / 0.41 | **teacher_recall** | instance_below_production_cut |
| fp13 | 1778.0 | 0.82 | 1.8 px / 0.48 | 1.8 px / 0.48 | **teacher_recall** | instance_below_production_cut |
| fp14 | 1779.1 | 0.82 | 1.9 px / 0.51 | 1.9 px / 0.51 | **teacher_recall** | instance_below_production_cut |
| fp15 | 1780.1 | 0.81 | 1.3 px / 0.18 | 1.7 px / 0.49 | **teacher_recall** | instance_below_production_cut |

**`teacher_recall 6 / student_hallucination 9 / unresolved 0.`**

### The six real balls

- **fp12–fp15 are the case the production cut was suspected of** (t = 1777.5–1780.1): the same
  ball at ≈(750, 377), 10.4 px radius, which the student fires on at 0.81–0.82 and SAM3 scores
  **0.41 / 0.48 / 0.51 / 0.49 at 1.8 px** — sustained across four consecutive frames, all below
  a cut that keeps everything at or above 0.6245. Production deleted a ball SAM3 was tracking.
  Raising these back requires the cut to drop to **0.50–0.35**.
- **fp10 (t = 1364.0)** is different and worse: the student fires at 0.72 and SAM3 has a **0.84**
  instance **0.8 px** away that production *would* have kept. See the cache defect below.
- **fp11 (t = 1650.0)** is a **double-count, not a second ball.** The student fires at (562.7,
  443.2) and the teacher's ball is at (561.5, 449.5) — **6.41 px** away, just outside the report's
  6.0 px match tolerance. So one ball, missed by 6.4 px, is booked twice: as false positive fp11
  *and* as false negative **fn17** (teacher score 0.857). SAM3's confirming instance (0.86) sits
  at 6.45 px, on the teacher's position rather than the student's, which is what makes this a
  **localisation** error at the tolerance boundary rather than a detection error. It is also why
  fn17 never "recovers" at any threshold: the peak is there, it is simply 6.4 px out.

### The nine hallucinations are not noise — they are the cue and the hand

The crops make the failure mode legible, and it is systematic rather than random:

| cluster | frames | what is actually at the disputed point |
|---|---|---|
| fp02–fp05 | 234.6 – 237.5, ≈(570, 380) | the player's **hand/glove** on the cue, at the cloth edge |
| fp06–fp09 | 1078.1 – 1080.2, ≈(532, 401) and (438, 505) | the **cue tip / shaft**, white ferrule against blue cloth |
| fp01 | 43.7, ≈(800, 540) | the **cue shaft** crossing the rail, with a real ball 79 px away |

Nine of nine are ball-sized, low-contrast, ball-adjacent objects in the cue/hand/rail region —
exactly what a 204,529-parameter appearance net trained on teacher labels would be expected to
confuse. Two of the three clusters are *sustained over 3–4 consecutive frames*, which means
they survive the single-frame NMS: they would survive a temporal filter too unless it is
explicitly taught that a ball does not sit on a cue tip.

## The mirror test: the 22 false negatives

Zero of the 22 have any student peak within 6.0 px at the operating threshold — so **none of
them is a greedy-matching artifact**; they are genuine misses.

| student threshold | FN recovered | tp | fp | fn | precision | recall | F1 | p90 loc (px) |
|---|---|---|---|---|---|---|---|---|
| 0.425 | 0/22 | 235 | 15 | 22 | 0.940 | 0.914 | 0.927 | 3.62 |
| 0.375 | 2/22 | 237 | 20 | 20 | 0.922 | 0.922 | 0.922 | 3.6 |
| 0.350 | 2/22 | 237 | 21 | 20 | 0.919 | 0.922 | 0.920 | 3.6 |
| 0.325 | 3/22 | 238 | 24 | 19 | 0.908 | 0.926 | 0.917 | 3.59 |
| 0.300 | 5/22 | 240 | 24 | 17 | 0.909 | 0.934 | 0.921 | 3.58 |
| 0.250 | 6/22 | 241 | 28 | 16 | 0.896 | 0.938 | 0.916 | 3.57 |
| 0.225 | 7/22 | 242 | 29 | 15 | 0.893 | 0.942 | 0.917 | 3.64 |
| 0.200 | 7/22 | 242 | 29 | 15 | 0.893 | 0.942 | 0.917 | 3.64 |
| 0.150 | 7/22 | 242 | 34 | 15 | 0.877 | 0.942 | 0.908 | 3.64 |
| 0.100 | 8/22 | 243 | 44 | 14 | 0.847 | 0.946 | 0.893 | 3.63 |
| 0.050 | 9/22 | 244 | 94 | 13 | 0.722 | 0.949 | 0.820 | 3.66 |

**7 of the 22 come back at 0.225 for F1 0.917 (down 0.010); 5 come back at 0.300 for F1 0.921
(down 0.006). The remaining 15 never come back at any threshold — even at 0.05, where the
detector emits 94 false positives, only 9 of 22 are recovered.**

That split is the useful result, and it is not "the student needs a lower threshold":

- the 7 recoverable ones are ordinary recall-at-the-margin cases, and at **1.02 px median
  localisation** they are well-placed, not lucky hits;
- the 15 unrecoverable ones are a **capability gap**. The crops show what it is: at
  t = 1363.2/1363.7 the teacher has six balls with r ≈ 12 px in a tight cluster, and the
  student fires **once** where there are two adjacent balls (fn12, 18.1 px away) — a merge
  failure, which no threshold can split. Others are balls at the cloth edge (fn02–fn05 sit
  4.3 px from it) and one is the 6.4 px localisation miss that is also fp11.

## Secondary finding: the teacher cache has wrong rows, and it changes the F1 label

The audit's own reproducibility check compares each re-measured frame against the teacher
cache. It found `t = 1364.0` disagreeing: **`out/scan30/sam3_results.json["1364.0"]` is an
empty list, while SAM3 returns 7 admitted instances at scores 0.76–0.88 on that frame.**

- This is not the sweep being wrong. On the other 13 FP frames the re-run reproduced the cached
  admitted instances exactly (0 unmatched, 0 extra) — including the frames whose cached row is
  *correctly* empty (1078.1, 1079.2, 1080.2, untouched by the student's detections there).
- Its consequence is already visible in the table: fp10 was booked as a false positive against
  an empty truth row, and it is a ball SAM3 scores 0.84. **So the F1 0.927 is measured against
  at least one wrong truth row.**
- **The defect is one row, not a pattern.** Held frame `t = 1366.0` also has an empty cached row,
  so it was measured too (`--extra-times 1366.0`, one frame, 41.6 s): SAM3 returns **0 instances
  at the 0.15 floor**, so that empty row is *correct*. 14 of the 15 frames measured here agree
  with the cache; exactly one held-out truth row — `t = 1364.0` — is wrong.
- The direction of the F1 error is therefore known for the frames checked: fp10 would have been
  a true positive had that row been right, so the reported F1 is **understated** by that case.
  Whether *unmeasured* held frames carry further wrong rows is not settled.
- 13 of the 56 rows in `sam3_results.json` and 27 of the 138 in `sam3_census.json` are empty.
  Only the held-out ones affect the reported score, and only the ones the student disputed were
  checked. An empty cache row is indistinguishable from a correct "no balls here", which is why
  the audit measures rather than trusts it.

## What this does and does not prove

**Does prove:** the adjudicator is **independent of the student**. The 15 FPs and 22 FNs were
settled by a second forward pass whose instances the student never saw and cannot have been
distilled into. So "6 of the 15 are real balls" is not the student's own opinion of itself, and
the hallucination verdicts are not the teacher's labels recycled.

**Does not prove:** SAM3 is still not ground truth. `teacher_recall` means **"the teacher sees a
ball here too"**, not "a human confirms a ball". Two specific ways this matters:

- a *shared* blind spot is invisible to this method. If both models fire on the same cue tip,
  the instance appears and the FP is booked as recall. The crops are the only defence, which is
  why one is rendered per case rather than a summary sheet;
- SAM3's own instance gate (area/radius/cloth) is inherited as the definition of a ball. An
  instance it rejects is reported `unresolved`, not resolved in either direction.

**Changing the production cut is not what the numbers recommend.** Four of the six real balls
(fp12–fp15) would be recovered by dropping the cut to 0.35–0.50, but the cut is not the
detector's threshold: it is the label filter that decides what gets **stored**. Lowering it
changes the training set, not the held-out score, and this audit measured SAM3's instances —
not what a retrained student would do with them.

## Cost, honestly

| item | value |
|---|---|
| SAM3 model load | **92.9 s**, once per process |
| frames bought | **15** — 14 distinct FP frames + 1 cache-integrity frame (`t = 1366.0`), **0** reused from cache |
| seconds/frame | **50.2 mean**, 30.7–86.7 range over 15 frames (754.0 s total) |
| wall clock, sweep | **816.8 s ≈ 13.6 min** for the 14 FP frames; **123.5 s** for the extra frame in a second process (its own load) |
| student passes (GPU) | 3 × ≈ 38–42 s (cases, verdicts, crops) |
| FN mirror test | **0 SAM3 frames** — the teacher instance and score are already in the labels |
| total SAM3 spend | **15 frames, ~17 min wall clock including two model loads** |

**Nothing was reused from cache and the reason is structural, not an oversight:** both teacher
caches were written with the 0.62 cut applied, so they hold no instance below 0.6245 and cannot
answer a question about sub-cut recall. What the cache *did* supply for free is the
verification: 14 of the 15 frames reproduced their cached admitted instances exactly, which is
what makes the low-threshold numbers below them trustworthy — and the 15th is the defect above.

The frames are cached in `out/ball-fp-audit/sam3_sweep.json` and written after every frame, so
an interrupted run stays usable and a re-run costs nothing. 50.9 s/frame is above the 27–45 s
this box is documented at; the difference is CPU contention from the test suite running
alongside, and it is reported rather than smoothed.

**A 4× lever nobody used here:** `src/fast_ball_labels.py` documents a `hybrid` SAM3 mode that
puts the vision encoder on the ROCm GPU and keeps the (GPU-broken) head on the CPU —
**6.27 s/frame against 27.1**, with instance counts and positions agreeing on every frame it
measured. This audit stayed on the verified CPU path because agreeing with the frozen caches is
the point of an adjudication; **any future audit of more than ~20 frames should use `hybrid`
and spend 4× less.**

## Remaining uncertainty

1. **Which side is right is still a judgement, not a measurement.** 9 hallucination verdicts
   rest on SAM3 having found nothing there; a human looking at the 9 crops could overturn any
   of them, and the crops exist so that this costs seconds.
2. **The `t = 1364.0` cache defect is bounded, not explained.** One wrong held-out row is proven
   and the second candidate row (`1366.0`) was measured and cleared, so the defect looks like a
   single frame rather than a pattern — but *why* the app's cache recorded an empty row where
   SAM3 sees 7 balls is uninvestigated, and the other 39 held-out frames that carry a cache row
   were not re-measured (that is a full 47-frame pass, ≈ 40 min on CPU).
3. **The 6 recall verdicts include 2 that are not the "thrown away by production" story.**
   fp10 is a cache defect and fp11 is a 6.4 px localisation miss at the tolerance boundary.
   Reading "6 real balls" as "production discarded 6 real balls" would be wrong — it discarded
   **4**. And because fp11 is the same ball as fn17, the 15 FP and 22 FN counts double-count that
   one ball: the honest error total is 14 distinct false positives and 21 distinct misses.
4. **fn-unrecoverable is measured on the student's heatmaps at one resolution.** The 15
   unrecoverable misses are a merge/capacity limit at 960x540; whether a larger input or a
   higher-resolution head splits those adjacent balls is untested here.

## Reproducing

```
PYTHONPATH=. .venv/bin/python src/ball_fp_audit.py cases      # rebuild FP/FN, no SAM3
PYTHONPATH=. .venv/bin/python src/ball_fp_audit.py sam3 --budget-s 1500   # ~14 min
PYTHONPATH=. .venv/bin/python src/ball_fp_audit.py sam3 --extra-times 1366.0 --only-extra
PYTHONPATH=. .venv/bin/python src/ball_fp_audit.py verdicts   # adjudicate + mirror test
PYTHONPATH=. .venv/bin/python src/ball_fp_audit.py crops      # 37 PNGs
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_ball_fp_audit.py'
```

Evidence: `out/ball-fp-audit/cases.json`, `sam3_sweep.json`, `verdicts.json`, `verdicts.md`
(the tables above are generated from this JSON so the doc cannot drift from it), and 37 crops.
`out/` is gitignored by this repo's policy — all of it is regenerable from `src/ball_fp_audit.py`.

Read-only with respect to `src/tiny_ball_net.py`, `src/sam3_cpu.py`, `src/fast_ball_labels.py`,
`src/motion_scan.py`, `src/ball_census.py` and `annotator/`. The teacher caches were read, never
written; no production artifact was touched.
