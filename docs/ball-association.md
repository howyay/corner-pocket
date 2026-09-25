# Ball association — why identities fragment, and what bridging costs

Scope: `src/ball_census.py` (`associate`, `Track`) measured through the existing
harness `tests/ball_dense_events.py` on `out/dense-events/segment-1350-1650.json`
(300 s, 8999 decoded frames, ball stage at cadence 2, 19534 ball samples, 248
identities, 66.7 ms sampling, 4.34 detections per sampled frame).  The segment
lies inside the detector's training range: this is a behaviour measurement, not
an accuracy claim.

## Before — the measured fragmentation (commit for `src/ball_association_audit.py`)

`PYTHONPATH=. .venv/bin/python src/ball_association_audit.py out/dense-events/segment-1350-1650.json`
→ `out/dense-events/segment-1350-1650.audit.json`

| measure | value |
|---|---|
| identities | 248 (median 8.5 samples / 0.93 s, longest 1381 samples / 104.7 s) |
| terminations on open cloth | **170** — 120 lost on a **clean frame** (tracking failure), 50 lost under **occlusion** (`occ_dense ≥ 0.30`) |
| nearest pocket at the last sighting | median **89.5 px**, p10 25.9, p90 138.4, only **11 within 20 px** |
| reappearances | **162** — 114 on a clean frame, 48 under occlusion; gap median **0.87 s**, 146 of 162 in 0.5–2.0 s |
| fragment links (same colour, gap ≤ 2.5 s) | 20 px: 12 · 60 px: 39 · **150 px: 135** · 300 px: 225 |
| moving links (> 20 px) | 213, implied speed median **158 px/s**, p90 841, max 3701 |
| gate | 3 shots, 0 pots, 0 unknowns, 721 rejections |

Read: **~70 % of the losses are the detector missing a ball that was there**, not
occlusion (the gate's own iron rule is preserved — a loss under a person stays
`unknown`).  And the split is not "the ball stayed put": only 12 of 225 links are
within 20 px, the rest are a ball that kept moving through the gap at a median
158 px/s.  `TRACK_MATCH_PX = 30` measures distance to the *last position*, so a
ball that rolls 60 px in one 66.7 ms sample — 900 px/s, an ordinary shot — is a
new identity by construction.  That is the defect the predictor has to remove.

Link counts are a lower bound: they are built from the evidence samples each
rejection carries (up to 6 per row), not from the full tracks.

## After — the same segment, the same harness, prediction instead of a fixed gate

`PYTHONPATH=. .venv/bin/python tests/ball_dense_events.py --start 1350 --seconds 300` (two
decodes; the frame-level facts agree exactly — 19534 balls, occlusion share 0.1512 — so the
comparison is controlled on everything the association cannot touch).

| measure | before (fixed 30 px) | after (prediction) |
|---|---|---|
| identities | 248 | 245 |
| single-sample identities | 37 | 30 |
| stable (≥ 2 samples) | 211 | 215 |
| longest identity | 1381 samples / 104.7 s | **1632 samples / 114.4 s** |
| terminations on open cloth | 170 | 172 (120 clean · 52 occluded) |
| reappearances | 162 | 154 (108 clean · 46 occluded) |
| gate | 3 shots, **0 pots, 0 unknown**, 721 rejections | 3 shots, **0 pots, 1 unknown**, 713 rejections |
| purity: shared detections | 0 | **0** |
| purity: kink-like speed changes in the evidence tails | 110 | 121 |

**The honest answer on pots: still zero confirmed — and one pot-shaped event now exists.**
`t265-blue` ends at (368.3, 306.3), **9.6 px from the left-side pocket centre** (radius
14.5 px), having run (325, 381) → (344, 349) → (368, 306) at 734 px/s when the track
stops; it is seen nowhere in the remaining 11.4 s of the segment and no identity swap is
suspected. The gate returns `unknown` / `cloth_occluded_at_disappearance`, which is the
project's iron rule: the cloth was occluded at that moment, and a ball that vanishes under
a person is unknown, not potted. Before the fix this path was fragmented and never reached
the pocket radius.

**Why the gain is modest, measured.** The residual after constant-velocity prediction is
still a median 123 px over all candidate links (p90 276), i.e. the ball's motion *changes
inside* the gap — it is struck, or it bounces — and a straight-line predictor cannot follow
that. Bridging those would be fusing two balls, not tracking one. And only 28 % of the
candidate links are same-colour (216 same / 551 cross), so a misread colour still blocks
most cross-colour fragments. The kink proxy rose 110 → 121: some of those are real cushion
bounces the wider gate now keeps as one identity (correct), and the counter cannot tell
them from a fusion — it is a review signal, not a verdict.

Reproduce: `src/ball_association_audit.py` (per-side diagnosis) and
`src/ball_association_ab.py` (one decode, both associators; its post-harness phase was
killed by the host's OOM killer at load 89, so the comparison above is the two artifacts).
Artifacts: `out/dense-events/segment-1350-1650.{before,after}.json` and the matching
`.audit.json` files.

