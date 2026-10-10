# Face identification on this footage — measured

Owner's question: **"can you do face identification?"** This is the measurement behind the
answer. It runs the *existing* code (`src/face_id.py`, `src/person_pipeline.py`), changes
nothing in the production path, and writes only under `out/face-eval/` (gitignored).

Verdict up front: **yes, on this footage, for enrolled regulars.** Person instances on the
main VOD yield a production-usable face 74% of the time, median inter-eye distance 12.4 px
(gate 8), median detection score 0.81 (gate 0.4), and same-person vs different-person face
similarity does not overlap in either direction. The blocker is not image quality — it is
that **the roster is empty** (0 regulars, no `face_embeddings.json`), so nothing can bind.
The open risk is single-photo enrollment: 2 of 35 same-table-end impostor faces cleared the
production bar in the demo window (0.60, 0.55 cosine).

---

## 1. Inventory: where the capability actually lives

| Stage | Location |
| --- | --- |
| Face detection + embedding (buffalo_l, SCRFD det + ArcFace w600k_r50), CPU provider, `det_size=640` | `src/face_id.py:50-96` (`FaceEngine._create_analyzer` 56-65, `analyze` 67-96) |
| Pad + ×2/×4/×8 upscale retry for tight enrollment crops | `src/face_id.py:98-130` (`analyze_resilient`) |
| Quality gates: `MIN_EYE_PX=8.0`, `MIN_DET_SCORE=0.4` | `src/face_id.py:41-45`, `quality()` 147-152 |
| Match bar `DEFAULT_THRESHOLD=0.35`, `DEFAULT_MARGIN=0.12` | `src/face_id.py:43-44`, `best_match()` 178-202 |
| Enrollment store (biometrics kept out of `state.json`) | `src/face_id.py:39` (`DEFAULT_FACE_STORE`), `store_faces()` 243-267, `load_faces()` 270-279 |
| Face→person association (`center inside person box`), stride + signature caching | `src/person_pipeline.py:135-157`, association at `181-188` |
| Matching + binding per frame: `best_match` → `bind_face` | `src/person_pipeline.py:203-212` |
| Enrollment entry point: `enroll_face()` | `src/person_pipeline.py:226-234` |
| `bind_face()`: unbound only, requires `similarity >= match_threshold + margin`, persists | `src/person_identity.py:199-221` (bar at 211, first-match-wins at 209) |
| Index defaults (face bar) + body matching disabled | `src/person_identity.py:108-129`, `67-69` |
| HTTP `POST /api/identity/enroll` (base64 → `cv2.imdecode` → `enroll_face`) | `annotator/unified_server.py:228-252`, route `1102-1103`, 12 MB body cap `1313` |
| HTTP `GET /api/identity/frame` (decode → `process_frame`) | `annotator/unified_server.py:205-226`, route `1016-1017` |
| `GET /api/unified` runs the same seam, degrades to no persons on failure | `annotator/unified_server.py:441-446`, route `1018-1019` |
| `GET /api/identity/status`, seed / unbind overrides | `annotator/unified_server.py:254-266`, `268-295` |
| Browser upload form (one photo per player) | `annotator/ops.js:77` |

Two gate details worth knowing before trusting a binding:

- The **effective bar is 0.47, not 0.35**: `best_match` accepts at ≥0.35 with a ≥0.12 gap
  (`src/face_id.py:200`), then `bind_face` adds `similarity >= threshold + margin`
  (`src/person_identity.py:211`). Both are composed in `process_frame` (204-207).
- **`bind_face` enforces the same margin as `best_match`** since the fix round (see 7.1). The
  binding path calls the shared `src.face_id.accept_match()` with `bind=True`
  (`src/person_identity.py:293-315`), so a probe must reach the binding bar, 0.47, and, when a
  runner-up is supplied, trail that runner-up by >= 0.12. Before this fix the binding path
  compared the single similarity only. One enrolment photo then produced 2 impostor binds out
  of 35 measured faces, at 0.60 and 0.55.

Roster state at the round-27 re-measurement: `out/corner-pocket/state.json` holds **7
players** (Wanwan, Su, Lulu, Alan, TJJ, Haoye, Yuefu). There is still no
`out/corner-pocket/face_embeddings.json`, so locally `best_match` returns `None`
(`src/face_id.py:187`), the 48 clusters in `out/identity/clusters.json` are all unbound, and
no cluster can bind until a regular is enrolled. The production console keeps its own store.

## 2. Face detectability on the real footage

240 sampled frames (16 anchors × 10 frames every 0.5 s on `data/vod_30min_260815.mp4`,
8 × 10 on `data/vod_highlight.mp4`), production YOLO person boxes + production face engine:
**484 person instances, 962 faces detected.** Anchors spread over the whole session, and
"distance" is read off the person-box height (taller box = closer to the camera).

| Gate (per person instance) | n | rate |
| --- | ---: | ---: |
| any face detected | 450 | 92.98% |
| face centre inside that person box | 389 | 80.37% |
| eye distance ≥ 8 px | 415 | 85.74% |
| detection score ≥ 0.4 | 450 | 92.98% |
| **passes both quality gates** | **415** | **85.74%** |
| **production selection** (quality face *inside the box*, what `process_frame` can match) | **334** | **69.01%** |

| Slice | person instances | with a usable face | yield |
| --- | ---: | ---: | ---: |
| `vod30` (1280×720, 30 min) | 399 | 295 | 73.93% |
| `highlight` (1920×1080, 6 min) | 85 | 39 | 45.88% |
| far — box < 250 px tall | 118 | 81 | 68.64% |
| mid — box 250–400 px | 251 | 203 | 80.88% |
| near — box ≥ 400 px (closest to camera) | 115 | 50 | 43.48% |
| session 0–5 min / 5–10 / 10–15 / 15–20 / 20–25 / 25–30 | 155/114/58/66/77/14 | 110/74/47/51/43/9 | 71.0/64.9/81.0/77.3/55.8/64.3% |

Quality-face geometry: face box median **30.6 × 36.4 px** (p05 25.9 × 28.9, p95 51.6 × 60.3,
max 108 × 129); inter-eye distance median **12.44 px** (p05 9.98, p95 18.75, max 43.56);
detection score median **0.807** (p05 0.661, p95 0.874).

Two honest readings of the table:

- **The dark room does not defeat the detector.** 3–6 m away still lands above the 8 px eye
  gate (only 14% of instances fail it) because `det_size=640` runs on the full 1280×720 frame.
- **Yield is not monotone in distance.** The *closest* instances perform worst (43%): a box
  ≥400 px tall is usually a back-of-head, a body cut by the frame edge, or someone walking
  between the camera and the table. The failure mode is orientation and cropping, not resolution.
- `highlight` is the weaker VOD (46%): it is a 1080p close-up clip where the single player is
  often off-frame or in profile, and 0 frames had quality faces at *both* table ends.

## 3. Identity separation: does 0.35 + 0.12 separate people here?

Same-person class = two faces on one IoU-linked tracklet, ≤4.5 s apart (1016 pairs, 114
tracklets). Different-people class = two faces from different person boxes **in the same
frame** (182 pairs — no tracking assumption possible). Pairs where two overlapping person
boxes claimed the *same* face are dropped (25 such pairs; 30 instances in the census have a
face claimed twice — `center_inside` is per-box, a diagnostic, not a binding hazard).

| Class | n | min | p05 | median | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| within tracklet (same person) | 1016 | −0.059 | **0.405** | 0.791 | 0.913 | 0.954 |
| different person, same frame | 182 | −0.129 | −0.041 | 0.041 | 0.168 | **0.226** |

**The two distributions do not overlap**: the worst different-person pair (0.226) is below
the worst-but-one-tenth same-person pair (p05 0.405). The production 0.35 threshold sits in
that empty band; the stricter 0.47 bind bar sits deeper inside it.

- same-person pairs clearing 0.35: **95.96%**; clearing the 0.47 bind bar: **93.11%**
- different-person same-frame pairs clearing 0.35: **0.00%** (and 0.00% at 0.47)
- per VOD, same-person p05/median: `vod30` 0.391 / 0.799, `highlight` 0.443 / 0.657

Player-to-player (the two table ends, same frame, provably different people, `vod30`):
n=30, median 0.058, p95 0.207, max 0.226 — comfortably rejected by both gates.

**What face ID cannot do here is the roster, not the matching.** The same table end holds the
same person in only **6 of 16** consecutive-anchor pairs (≈112 s apart): the similarity is
bimodal (0.76–0.89 when the same person stays, 0.00–0.11 when someone else has taken the
table). A 30-minute session is a rotating tournament; "the person at the near end" is a
position, not an identity. Long-range re-identification therefore has to *bind to a player
identity* (which is exactly what `bind_face` does), not assume continuity.

This also settles the repo's older question: body/colour re-ID was disabled because its
distributions overlap (OSNet same-person p05 0.755 vs cross-person p95 0.882,
`src/person_identity.py:58-69`). Face similarity on the same frames separates with a 0.18
margin between classes. Face is doing work that body could not.

## 4. End-to-end demo (isolated scratch store, production code path)

Window: `vod30` anchors 6→9 at the near/left end, chosen because the measured medoid
continuity across those anchors is 0.853 / 0.762 / 0.831 (same person throughout).
Scratch root `out/face-eval/scratch/` (symlinked `data/`, `src/`, `annotator/`, `yolov8n.pt`;
own `out/corner-pocket/` and `out/identity/`), i.e. the `tests/serve_workbench_fixture.py`
pattern.

1. **Enrollment** through `PersonPipeline.enroll_face` — the function
   `POST /api/identity/enroll` calls: one padded photo crop of the *medoid* face of anchor 6
   (frame 20589, eye 12.77 px, det 0.841, crop 128×164) → **1 gallery entry for
   `player-left`**, stored at `out/face-eval/scratch/out/corner-pocket/face_embeddings.json`.
   (The other table end had no quality face in that anchor, so only one player is enrolled —
   the impostor class below is what tests rejection.)
2. **Held-out matching** (bursts 7–9, faces never enrolled), via `best_match` on the scratch
   gallery — 28 probes of the recurring person, 35 impostor probes (other people standing at
   the same end, plus the other end):

   | Probe class | n | median | p05 | p95 | max | bound to `player-left` |
   | --- | ---: | ---: | ---: | ---: | ---: | ---: |
   | same person | 28 | 0.786 | 0.718 | 0.864 | 0.871 | **28/28** |
   | impostor | 35 | 0.010 | −0.042 | 0.226 | **0.603** | 2/35 |

   All 28 same-person probes cleared the 0.47 bind bar; **2 impostor faces did too (0.603,
   0.551)** — a 5.7% false-accept rate in this window, from a single enrolled photo. The
   measured gap between the worst false accept (0.603) and the worst true accept (0.697)
   suggests ≈0.65 as the separating bar *for this window*; that is one window, not a
   calibration, and the honest fix is more enrollment photos rather than a moved threshold.
3. **Full pipeline replay** (`process_frame` → tracker → `best_match` → `bind_face` →
   `IdentityIndex.save`, ≥4.5 s of real frames x 3 anchors): 30 frames, 79 person
   observations, **2 bind events — both to `player-left`, at similarity 0.782 (frame 23883,
   cluster 1) and 0.865 (frame 27253, cluster 10)**, both on the left/near end and none on
   the other end. Binds are deliberately rare: a cluster binds once, ever.

Read-only proof: md5 of `out/corner-pocket/state.json`, `out/pid_seed.json`,
`out/scan30/annotations.json`, `out/identity/clusters.json` identical before/after
(`out/corner-pocket/face_embeddings.json` absent before and after — production has no
biometrics at all). `out/face-eval/demo.json` records both md5 maps.

### 4b. The same thing over HTTP (the route the browser uses)

An *empty* second scratch root (`out/face-eval/scratch-http`) was served on port 8133
(`src.eval_faces serve --root out/face-eval/scratch-http --port 8133`) and driven with real
requests, so this is the production route and not a re-implementation:

| Request | Result |
| --- | --- |
| `GET /api/identity/status` (before) | `{"tracks": 0, "clusters": 0, "bound": []}` |
| `POST /api/identity/enroll` (base64 PNG of the anchor-6 medoid face) | `{"enrolled": 1, "player_id": "player-left"}` → `out/face-eval/scratch-http/out/corner-pocket/face_embeddings.json` |
| `GET /api/identity/frame` × 12 held-out frames | 2 bind events: `player-left` at 0.7824411988258362 (frame 23883, cluster 1) and 0.864875316619873 (frame 27253, cluster 10) |
| `GET /api/identity/status` (after) | `{"tracks": 10, "clusters": 10, "bound": [{"cluster_id": 1, "player_id": "player-left"}, {"cluster_id": 10, "player_id": "player-left"}]}` |

The two similarities are bit-identical to the in-process replay above, and the server was
stopped after the run. Nothing under `out/corner-pocket/` or `out/identity/` changed.

## 5. What the owner must do to use this in production

1. **Add the regulars** in the Operations page (`players` is currently `[]` in
   `out/corner-pocket/state.json`).
2. **Upload one photo per regular** through the existing enroll form
   (`annotator/ops.js:77` → `POST /api/identity/enroll`). The photo lands in
   `out/corner-pocket/face_embeddings.json`, separate from `state.json` on purpose
   (biometrics are not match events). 3–5 photos per person is the cheap upgrade: the gallery
   scores a probe against every entry and keeps the best (`src/face_id.py:190-193`), so extra
   photos lift the same-person p05 0.718 without moving the 0.47 bar.
3. **Nothing else.** From then on, every `GET /api/identity/frame` and every `GET /api/unified`
   frame runs the pipeline (`annotator/unified_server.py:205-226`, `441-446`); an unbound
   cluster whose person box holds a quality face that matches an enrolled player at ≥0.47 and
   ≥0.12 clear of any other player gets that `player_id` plus a `bind` event, and the review
   rail shows it. `POST /api/identity/seed` (explicit assign) and `/api/identity/unbind` stay
   available as manual overrides.
4. Expect a **bind to be a one-time event per track**, and expect no bind at all for the
   ~31% of person instances with no usable face (backs turned, cropped at the frame edge) or
   for anyone not enrolled.

### If face ID is rejected anyway, use this instead — and what it costs

The repo's current fallback is body appearance + explicit seeds (`BODY_MATCH_DISABLED`,
`src/person_identity.py:67-69`; seeds in `out/pid_seed.json`, clusters in
`out/identity/clusters.json`). The trade-off is measured, not estimated:

| | Face (this round) | Body/colour (current fallback) |
| --- | --- | --- |
| Separation on these frames | same p05 0.405 vs cross max 0.226 — **no overlap** | same p05 0.755 vs cross p95 0.882 — **overlap, no threshold works** |
| Enrollment cost | 1–5 photos per regular, once | none |
| Coverage | 69% of person instances have a usable face | ~100% (any visible torso) |
| Identity semantics | stable `player_id` from the roster | cluster + explicit seed per session, human-labelled |

Face wins on separation and loses on enrollment friction and coverage. Since the coverage
gap is exactly the "no usable face" 31% above, the practical design is both: faces bind
automatically when visible, explicit seeds cover the rest — which is what
`person_identity.py` already implements.

## 6. Reproduce

```bash
PYTHONPATH=. .venv/bin/python -m src.eval_faces measure --dir out/face-eval   # ~5.5 min CPU
PYTHONPATH=. .venv/bin/python -m src.eval_faces analyse --dir out/face-eval   # no models
PYTHONPATH=. .venv/bin/python -m src.eval_faces demo    --dir out/face-eval   # ~5 min CPU
PYTHONPATH=. .venv/bin/python -m src.eval_faces serve --root out/face-eval/scratch --port 8133
PYTHONPATH=. .venv/bin/python -m src.eval_faces md5                           # protected files
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_eval_faces.py' -q
```

Artifacts: `out/face-eval/detections.json` (484 instances, 240 frames, embeddings),
`out/face-eval/analysis.json` (all tables above), `out/face-eval/demo.json` (enrollment,
held-out matching, replay binds, md5s). All gitignored; regenerable from `src/eval_faces.py`.

## 7. Bar configuration (fix round: the margin, and the number to quote)

### 7.1 `bind_face` now enforces the same margin as `best_match`

`best_match()` rejected an ambiguous probe (best − runner-up < 0.12), but
`IdentityIndex.bind_face()` checked only the similarity — so any caller of `bind_face`
could bind a face whose closest competitor was a hair behind. Both paths now call one rule,
`src.face_id.accept_match(similarity, runner_up, threshold, margin, bind, bind_bar)`:

- matching (`bind=False`): `similarity >= threshold` **and** the runner-up trailing by `>= margin`;
- binding (`bind=True`): `similarity >= bind_bar` **and** the same runner-up margin.

`best_match()` returns `runner_up` next to `similarity`/`margin` (None for a single-player
gallery) and `PersonPipeline.process_frame` passes it through (`runner_up=match.get('runner_up')`
in `src/person_pipeline.py`), so the margin is enforced twice on the production path. Proven by
`tests/test_person_identity.py::test_bind_rejects_a_runner_up_inside_the_margin` (0.80 with a
0.70 runner-up must not bind; the same 0.80 with a 0.68 runner-up binds),
`::test_bind_margin_boundary_is_inclusive` (0.120 passes, 0.11999 does not),
`::test_shared_rule_is_the_same_for_matching_and_binding`, and
`tests/test_eval_faces.py::test_measured_bind_gate_is_the_shared_rule` (the measurement tool
reports the same gate the code applies).

### 7.2 The number an operator must quote is 0.47, not 0.35

`bar = threshold + margin` composes, and only the composed number binds. The configuration now
says so explicitly:

| Value | Where | Meaning |
| --- | --- | --- |
| `DEFAULT_THRESHOLD = 0.35` | `src/face_id.py` | gallery *matching* bar — "is this a known face" |
| `DEFAULT_MARGIN = 0.12` | `src/face_id.py` | runner-up separation, enforced by both paths |
| `DEFAULT_BIND_BAR = 0.47` | `src/face_id.py` | **the bar that binds** = threshold + margin |
| `IdentityIndex(bind_bar=...)` | `src/person_identity.py` | explicit override; `None` keeps 0.47, so tuning `match_threshold`/`margin` moves the binding bar with it |
| `IdentityIndex.effective_bind_bar` | `src/person_identity.py` | property reporting the bar actually applied |
| `CANDIDATE_BIND_BAR = 0.65` | `src/face_id.py` | measured candidate — **not applied** (§7.3) |

Places that stated a number the system does not apply, and what they now say:

| Place | Was | Now |
| --- | --- | --- |
| `src/face_id.py` module docstring | threshold rationale with no binding statement | a "WHERE THE BAR IS APPLIED" block: 0.35 matches, **0.35 never binds**, binding is 0.47 + margin |
| `src/face_id.py` constants | `DEFAULT_THRESHOLD` / `DEFAULT_MARGIN` only | `+ DEFAULT_BIND_BAR = 0.47`, `+ CANDIDATE_BIND_BAR = 0.65` |
| `src/person_identity.py` module docstring | "the 0.35/0.12 defaults below are the FACE bar" | "threshold 0.35 / margin 0.12. The bar bind_face() applies is the composed one, DEFAULT_BIND_BAR = 0.47; 0.35 alone never binds" |
| `src/person_identity.py` `bind_face` docstring | "Requires similarity >= match_threshold + margin" | names the shared rule, the runner-up requirement, and the defect it fixes |
| `src/person_pipeline.py` module docstring | "faces bind at >= 0.35 with 0.12 margin" | "a face binds at >= 0.47 (the effective bar = match_threshold 0.35 + margin 0.12 …), the runner-up must trail by 0.12" |
| `src/eval_faces.py` | bind column computed as `similarity >= threshold + margin` | calls `accept_match(..., bind=True)`, so the reported bind / false-accept numbers match the code |
| `docs/face-identification-assessment.md:39` | already stated 0.47 | unchanged; this section is the canonical statement |

Both remaining places were corrected in follow-up commit `bc69602`: `docs/handoff.md:13` now reads
"effective bind bar 0.47 = 0.35 threshold + 0.12 margin, with the runner-up 0.12 behind — 0.35
alone never binds", and `docs/live-processing-verification.md:5` now reads "supporting a 0.35
match threshold with a 0.12 margin over the runner-up (the effective bind bar is 0.47 = 0.35 +
0.12; 0.35 alone never binds)". (Line 139 of that file already quoted the 0.47 bar correctly.)

### 7.3 Candidate bar 0.65 — evidence, sample size, what would confirm it

**Not applied.** The deployed default stays 0.47; the candidate is
`src/face_id.CANDIDATE_BIND_BAR`, opt-in per index via `IdentityIndex(bind_bar=0.65)`.
`tests/test_person_identity.py::test_explicit_bind_bar_overrides_the_composition` pins that an
explicit bar is used as-is while the default remains 0.47, and
`::test_bind_bar_rule_follows_configured_threshold_and_margin` pins the *rule*
(bar = threshold + margin) rather than the number.

| | cosine | sample |
| --- | ---: | --- |
| worst false accept (face at the enrolled table end, not the enrolled person) | 0.603 | 35 impostor probes |
| second false accept | 0.551 | 2/35 = 5.7% false-accept rate |
| worst correct accept | 0.697 | 28 same-person probes (median 0.786) |

The gap between 0.603 and 0.697 is where a separating bar would sit; 0.65 is mid-gap. **The
sample is one 30-minute window, one enrolled player, one photo, 63 probes** — enough to
nominate a value, not to adopt one. Two reasons to be careful:

1. the same 0.47 bar produced **zero** false accepts in the 240-frame census
   (different-people-same-frame max 0.226, 0.0% clearing the 0.35 threshold), so those two
   faces are not representative impostors: they are same-end faces the 0.6-to-burst-medoid
   labelling rule called "not the enrolled person", and may be that person in a hard pose;
2. raising the bar costs real binds — only 93.1% of within-tracklet same-person pairs clear
   0.47 today, and the same-person p05 is 0.405, so a 0.65 bar would drop a material tail.
   More enrolment photos per regular (the gallery keeps the best entry,
   `src/face_id.py:190-193`) lift that tail without touching the bar.

What would confirm or refute the candidate (do **not** re-tune on this window):

1. **Windows:** ≥ 5 sessions, each with ≥ 2 players enrolled, ≥ 60 s of play per player, spread
   over different lighting and segments.
2. **Labels:** per window, ≥ 100 same-person probes and ≥ 100 impostor probes *verified as
   different people* — not "not the medoid of this burst". A human pass over a probe montage is
   the cheap version.
3. **Decision rule:** choose the lowest bar whose per-window worst impostor accept stays 0.05
   below the per-window 5th-percentile same-person accept, on **every** window, not on the
   pooled distribution. If no bar satisfies that, the honest answer is more enrolment photos,
   not a moved bar.
4. **Report both errors** per window: the false-accept rate at the chosen bar and the
   lost-bind rate it causes, with the enrolment-photo count used.


## 8. Association end to end, on one real window (round 27 re-measurement)

The question was whether the face-to-human-track association is reliable. The chain has three
steps, and they do not have the same reliability.

**Step 1 - a usable face exists.** Over 240 sampled frames of two recordings, 484 person
instances were measured. A face that passes both quality gates, eye distance >= 8 px and
detection score >= 0.4, and whose centre falls inside the person box, exists for 334 of them:
**69.01%**. In the enrolment window below, 23 of 71 tracks held **no usable face at all**.

**Step 2 - the face names the right player.** 182 pairs of different people in one frame were
measured. Their highest cosine is **0.226**. The match bar is 0.35 and the binding bar is 0.47,
so **0.00%** of impostor pairs accept. 95.96% of same-person pairs accept at 0.35, and 93.11%
accept at 0.47. Where a usable face exists, the naming step is reliable on this footage.

**Step 3 - one human is one identity.** This step is weak, and it is weak by design. Body
matching is disabled because the measured distributions overlap: the same person >= 1 s apart
scores p05 0.755 and median 0.830, while different people in one frame score p95 0.882 and
median 0.811. A track therefore joins a cluster through a face only. One window of 180 frames
produced **71 tracks that group into 23 identities**, and the largest group holds **16 tracks**.
The association is per appearance. A player who steps out and returns is a new track until a
face links it.

**What enrolment does with an unsure track.** An enrolment run over that window enrolled
**17 of 71 tracks** and refused 54 with a reason: `no_face_in_track` 23, `single_face_only` 12,
`face_too_small` 8, `mixed_track` 6 (the track holds two people), `inconsistent_faces` 5. The
refusals are the safety property: the system refuses instead of guessing.

**One photo is not enough.** A single enrolment photo put the worst impostor accept at 0.603.
That is below the candidate bar 0.65, but above the 0.47 in use (see 7.3). The production flow
therefore requires at least two agreeing faces before it writes a name (`PURITY_DEFAULT=0.5`,
`PURITY_PROBES_MIN=2`, `src/enroll_from_tracklet.py:87-88`), and the operator confirms the
preview.

**Sources:** `out/face-eval/analysis.json` (steps 1 and 2), `out/enroll-eval/verify.json` and
`out/enroll-eval/report.json` (step 3 and the refusals).

## 9. One body track joins a face track (round 28: the link control)

The panel now associates a body track with a face track, and one name then covers both.

**The control.** Pick a person track on the stage. The identity panel shows "Link to another
appearance", a list of the identities that are visible in this frame, and one button. The
list excludes the picked track. A face mark follows the identity that carries a face. A
note states that the link merges the two identities. A second note appears when the frame
holds one identity only, because there is nothing to link to.

**The rule.** `IdentityIndex.link_track(track_id, cluster_id)` (`src/person_identity.py`)
moves the track's cluster into the picked one. The merge appends the body bank, inherits
the face when the target has none, merges the face samples under the 8-sample cap, keeps
the larger `last_seen_frame`, deletes the source cluster, and re-points every track that
pointed at it. The target keeps its player. A cluster that is already bound to a player is
refused (ValueError, HTTP 409), because a merge cannot decide which name wins. The method
saves the index, so the merge survives a restart.

**The route.** `POST /api/identity/link` takes `{"track_id", "cluster_id"}` and answers
`{"track_id", "cluster_id", "merged", "moved_tracks", "player_id"}`. A value that is not an
integer answers 400, an unknown cluster 404, and a bound source 409. `GET
/api/identity/status` now also returns `rows`: one entry per cluster with `cluster_id`,
`player_id`, `samples`, `last_seen_frame` and `tracks`, so the panel lists real identities.

**Measured** on the local console (`http://127.0.0.1:8130/ops.html#/records/review/2853972244`,
dataset `tw-2853972244`, frame 300, 9 person instances). The rail pickers were 1, 2 and 4.
The link list held 5 other identities, with the face mark on those that carried one. The
status held 60 clusters before the link and 59 after it, and cluster 52 then owned tracks
[2, 4, 5]. The roster select was set to Wanwan and Save was pressed: the status answered
`bound: [{cluster_id: 52, player_id: "a3c749f3..."}]`, and the cluster row held the same
player with 3 tracks. After `systemctl --user restart pool-workbench.service` the status
still held 59 clusters and the same binding, and the cluster row held 8 face samples with
`tracks: []`: the track map is session state, and it refills when frames are read again.

**The one defect the run found.** After a merge the panel's selection still pointed at the
cluster that the merge had deleted. The next Save therefore answered 404 and the name
stayed empty. `linkTrack` now moves the pick to the cluster that survived, which carries no
player yet (`annotator/app.js:1312`).

**Tests.** `tests/test_person_identity.py` holds four link tests: the merge, the idempotent
second link, the bound-source refusal, and a merge that survives a reload.
`tests/test_unified_server.py` holds two route tests. `tests/test_app_timeline.js` renders
the link block and asserts its options, its wording in both languages, and the engine
lines. `tests/test_ops.js` holds the contract that ties the route, the handler, the index
method and the panel together.

## 10. The shooter, when no face is visible

`research/player-attribution-research.md` holds the plan for the next identification step:
name the shooter of one shot from the tracklets, with no face and no name on the table. The
note collects published results and cost estimates. No number in it was measured on this
footage.

The order of the choices is: the face work in this document while a usable face exists
(69% of person instances, Section 2), then the body-appearance fallback in Section 5, then
the plan in that note.
