# Roadmap & decomposition

State as of 2026-09-07. Every row below maps to a Forgejo issue (= Kaneo task via
repo↔kaneo sync). Measured numbers are updated in `docs/state.md` as work lands.

## Assessment: which area needs what

1. **Homography/calibration — P0, immediate.** Last measured on the highlight:
   13.1 mm mean / 4.9 mm median holdout reprojection (6 pocket anchors, PnP with
   the 1270×2540 rectangle constraint, `out/calib_final.json`). NOT yet proven on
   the 30-min footage or the later crop frames (t=560..1700 s). Corner stability
   was historically the weak point (54–128 px at 720p in an older candidate clip).
   → verify per-segment; if drift/outliers appear, move to cushion-nose anchors.
2. **Projection — P0, immediate (small).** Orientation (portrait, head rail top),
   physical mm, ball-size rendering are in place; audit projection against known
   pocket geometry and report residuals on ≥10 frames.
3. **Shot & pot detection — P0, immediate.** `out/scan30/events.json` (57 shots,
   11 pots, causality-consistent) was **never reviewed**: every event is
   `verified:false`. Detector precision/recall is unmeasured; the annotator UI
   (`annotator/index.html` on :8124) exists for review but no verdicts exist.
   → build the GT review pass, measure P/R per event class, fix failure modes
   (missed quiet shots, phantom pots, pocket assignment), keep causality = 0.
4. **Player identification + player-shot association — P1, todo (biggest).**
   Research report exists with architecture and expected numbers; **zero
   implementation**. Sequence:
   person/cue sensing → player tracklets (occlusion = unknown, not potted) →
   geometric shooter selection at each cue-ball launch → OSNet x0.25 identity
   prototypes (A/B) → shot↔player association + pot attribution (Viterbi) →
   evaluation against reviewed events.
5. **Ball-ID ≥90 % smallest model — BACKLOG.** Labelers live
   (set 1 :8124 — 75/79 labeled; set 2 :8125 — 56 crops from 8 diverse layouts,
   0 labeled). Needs: user labels → merge → final leave-one-frame-out sweep.
   Current ceiling on set 1: ResNet18 79.5 % (label-corrected), small models far
   lower — insufficient class support (≤2 layouts, ball #2 n=1). Certification
   only meaningful after set-2 labels land.

## Issue decomposition (one Forgejo issue = one Kaneo task)

### P0 — immediate attention
- **HOM-1 Calibration across segments** — per-segment anchor holdout RMSE
  (highlight, vod30 t<450, t=560..1700); corner-stability scan; drift verdict;
  cushion-nose alignment if >15 mm. Deliver `docs/state.md` numbers + JSON.
- **PROJ-1 Projection audit** — portrait orientation + mm scale + ball-size
  sanity on ≥10 frames; pocket-center reprojection table; any flip/scale bug out.
- **EVT-1 Shot/pot ground truth & metrics** — review pass over scan30 events
  (annotator verdicts), per-class P/R/F1, causality recheck, top failure-mode
  fixes in `scan_events`/event pipeline; occlusion rule: hidden ball ⇒ unknown.

### P1 — todo (sequenced)
- **PID-1 Person & cue sensing** — SAM3 person/cue/hand instances on shot
  windows; crop+mask store; feasibility + quality report.
- **PID-2 Player tracklets** — fixed-camera association (mask IoU/centroid +
  ReID cost), one identity at a time, occlusion ⇒ unknown state.
- **PID-3 Geometric shooter selection** — cue segment near hand/torso & cue-tip
  distance to cue ball pre-impact; actor-per-shot scores.
- **PID-4 Identity prototypes** — OSNet x0.25 (MSMT17) embeddings over tracklet
  crops, A/B prototype bootstrap (scoreboard/manual anchor), name binding.
- **PID-5 Association & attribution** — per-shot actor fusion (geometry + ReID +
  continuity, ~0.60/0.25/0.10 weights), pot inheritance, Viterbi per rack;
  evaluation vs EVT-1 review (shooter accuracy, switches, coverage).
- **E2E-1 30-min pipeline run** — full re-run with final calibration + events +
  attribution; artifacts + metrics committed to `docs/state.md`.

### Backlog
- **BALL-1 Ball-ID certification** — finish labels (set1 leftovers + set2), merge
  sets, smallest-model sweep ≥90 % (leave-one-frame-out over all layouts).
- **BALL-2** (later) GPU/multiplex tracking, wider footage coverage.

## Working agreement

- Bars are measured; no self-report-only claims (per repo standard practice).
- Each P0/P1 issue closes with numbers in `docs/state.md` and a commit.
- Ball-ID cert stays on the two labeler URLs until labels exist.
