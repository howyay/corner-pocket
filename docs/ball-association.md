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
