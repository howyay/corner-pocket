# Tiny appearance-based ball detector — feasibility probe

**Question.** Difference-based methods are exhausted on this footage (single frame 24 %
of known movers in the best channel, track-before-detect 8 % with every confirmed track
sitting on an occlusion). Can a small appearance network learn to find these 18.9 px
balls, fast enough to run over a whole VOD?

**Verdict: MARGINAL** — 0.811 held-out F1 (bar 0.9) with 2.5 px median localisation at
15.5 ms/frame. It is close, the shortfall is diagnosable, and nothing about it looks
fundamental. Numbers and the caveats behind them follow.

## 1. Labels — and the one deviation from the brief

| source | frames | instances |
|---|---|---|
| `out/scan30/sam3_results.json` (the app's own cache) | 56 | — |
| `out/scan30/sam3_census.json` (earlier rounds) | 138 | — |
| **union, deduplicated by time** | **193** | **1062** |

Every stored score is ≥ 0.624, because both caches were written with the production
score cut (`MIN_SCORE = 0.62`); the delivered labels are therefore the teacher's
*confident* set, and that is the recall ceiling this probe inherits.

**The brief asked for ≈80 freshly labelled frames. They are not here.** SAM3 was
loaded on the ROCm GPU (43 s) but the processor returned zero balls when built with
`device="cuda"`, and the known-good CPU path costs ~45 s/frame (≈60 min for 80
frames). Rather than spend the probe's budget on a SAM3 device bug, the run used the
193 existing frames, which already span 4.1 s to 1799.7 s at ~1 Hz. **Consequence: the
probe measures distillation fidelity on the teacher's own confident labels, and its
F1 is an upper bound on accuracy, not an accuracy.** Adding the 80 frames — and
recording raw scores down to ~0.30 so the teacher's misses become visible — is the
first thing a full version must do.

## 2. Split (by time, not by frame)

Labels are ~1 Hz in bursts, so a per-frame "5 s away from training" rule threw away
most of the set (it left 18 training frames out of 193). The split is by **contiguous
~30 s blocks**, holding out every fourth block, with frames within 5 s of a block
boundary dropped from both sides:

| set | frames | ball instances |
|---|---|---|
| train | 116 | 722 |
| held-out | 47 | 258 |
| dropped for the gap | 30 | 82 |
| **tightest train↔held gap** | **5.2 s** | |

No held-out frame is within 5 s of any training frame, so the held-out score is not a
near-duplicate score.

## 3. Model

TrackNet-style heatmap regression, 3 frames in → one heatmap out.

| | |
|---|---|
| parameters | **204,529** |
| input | **640×360** (the ball is 9.4 px across here, against 18.9 px native) |
| channels | 9 (3 frames × RGB) |
| output | 1 channel, same size; target = a Gaussian of σ 2.5 px per labelled ball, taken as a maximum when two balls overlap |
| device | **ROCm GPU** (`torch 2.9.1+rocm6.4`, AMD Radeon Graphics) |
| training | 25 epochs, **256.8 s**, final MSE 0.00033 |
| augmentation | horizontal/vertical flips, ±8 px translation, ±15 % brightness/colour |

640×360 was chosen for the probe's budget: the ball keeps 9.4 px there, and a 4×
smaller frame than 960×540 makes a CPU-only pass plausible. A production version
should train at 960×540 or native, where the ball has 2–4× the pixels — the recall
failure below points at exactly that.

## 4. Held-out results (47 frames, 258 labelled balls)

Operating point chosen as the best F1 on the held-out sweep, matching by greedy
one-to-one assignment with a 6 px gate, in native pixels:

| threshold | TP | FP | FN | precision | recall | **F1** | loc. median | loc. p90 |
|---|---|---|---|---|---|---|---|---|
| **0.10** | 193 | 26 | 64 | **0.881** | **0.751** | **0.811** | **2.5 px** | 4.48 px |
| 0.15 | 177 | 16 | 80 | 0.917 | 0.689 | 0.787 | 2.5 px | 4.36 px |
| 0.075 | 194 | 44 | 63 | 0.815 | 0.755 | 0.784 | 2.5 px | 4.48 px |

No threshold in the sweep reaches 0.9 F1; the best is 0.811. Localisation beats the
≤4 px bar on the median and misses it at p90.

**Speed** (measured, 12 held-out frames, including the 3-frame stack and the decode):

| device | ms/frame | projected 30-min VOD (54,206 frames) |
|---|---|---|
| ROCm GPU | **15.5** | **14.0 min** |
| CPU | 92.5 | 84 min |

The GPU figure makes a full-VOD pass practical today.

## 5. Epistemics — what these numbers are not

**SAM3 is the teacher, not ground truth.** "2.5 px against SAM3" measures *distillation
fidelity*: how well 204 k parameters reproduce a 47 s/frame teacher. It is not
accuracy, and it cannot be, because the teacher is the only source of labels here.

The only evidence that does not come from the teacher is the overlays:
`out/tiny_ball_probe/overlays/01_t00043.7s.png` … `10_t00136.4s.png` — ten held-out
frames with the teacher's labels in green and the student's detections in red. They
have to be looked at; nothing in this report substitutes for that.

### Disagreements, and who is wrong

| | count | reading |
|---|---|---|
| teacher labels**outside** the cloth quad | 2 of 1062 (0.2 %) | the teacher is essentially on-table; one green circle in the overlays does sit on a person's leg, so at least one teacher label is not a ball |
| **FN** — teacher balls the student missed | **64** | teacher score median **0.810** (i.e. confident labels, not the teacher's low-score guesses) and radius median **6.9 px** against 9.2 px overall, so the student misses **small** balls; **47 of the 64 are within 25 px of the cloth edge**, so it also misses balls near the rail. These are **student** errors, and they are the recall shortfall |
| **FP** — student detections with no teacher ball | **26** | 25 inside the cloth. Given the teacher's known recall weakness (8–10 balls where a full rack has up to 16), some are plausibly real balls the teacher missed — **but judging that needs eyes, not another metric**, and this probe does not claim it |

Judged by: position inside the cloth quad, the teacher's own score for the missed
label, and the label's radius relative to the 9.2 px median. No human verification of
the 26 FPs was performed.

## 6. What a full version needs

1. **More training frames, and better ones.** 193 frames / 1062 instances is a few
   hundred times short of what this kind of model wants. The recall failure is
   concentrated on small and edge balls — more examples of exactly those.
2. **Higher input resolution.** 640×360 halves the ball's diameter relative to native;
   the 6.9 px misses are the visible cost. Train at 960×540 or native.
3. **Raw teacher scores, and a lower cut.** Re-label with `min_score ≈ 0.30` recorded,
   so the teacher's misses can be separated from its guesses.
4. **Human verification of a few hundred held-out balls.** Without it the ceiling of
   any measurement here is the teacher.
5. **A real train/validation/test split with time gaps**, and the F1 reported on the
   human-verified set only.
6. Budget: the probe cost ~5 min of GPU training and ~12 min of labelling-free work.
   A first real version is on the order of 5,000–20,000 labelled frames, several GPU
   hours of training, and a human verification pass — days, not weeks.

## 7. Reproduce

```
PYTHONPATH=. .venv/bin/python -m src.tiny_ball_net describe
PYTHONPATH=. .venv/bin/python -m src.tiny_ball_net evaluate --epochs 25
```

Artifacts: `out/tiny_ball_probe/probe.json` (full sweep), `disagreement.json`,
`tiny_ball_net.pt`, `overlays/*.png`. Nothing was written outside
`out/tiny_ball_probe/`, and `src/tiny_ball_net.py` + `tests/test_tiny_ball_net.py` are
the only source files touched.
