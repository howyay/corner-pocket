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
- **`bind_face` does not check the runner-up margin itself** (`src/person_identity.py:199-221`
  only compares the single similarity). The margin is enforced upstream by `best_match`; a
  direct `bind_face` call with a raw similarity can bind without the ambiguity check.

Roster state today: `out/corner-pocket/state.json` → `"players": []`; no
`out/corner-pocket/face_embeddings.json` at all. Zero enrolled faces, so `best_match` always
returns `None` (`src/face_id.py:187`) and no cluster can bind.

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
