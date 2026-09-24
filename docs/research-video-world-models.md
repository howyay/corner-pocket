# Open-source video physics / world models — what exists, what they measure, and whether any of it helps this pipeline

**Date:** 2026-09-23 · **Author:** research pass for the Corner Pocket owner review
**Trigger:** the owner watched the detected events and reported that *none of the event timestamps have any ball movement detected*.

**Method:** every model/benchmark claim below is cited to a URL that was actually fetched in this pass (arXiv abstract/HTML,
project site, repository README, or vendor docs). Claims that could not be fetched are marked **UNVERIFIED**. Local
numbers were measured on this box on 2026-09-23; the command is stated with each one.

---

## 0. Bottom line

**Every open video world model in this survey generates; none of them measures.** The best entry on the only benchmark
that scores *physical outcome* rather than looks — Physics-IQ Verified, TOP-1 **58.2 ± 1.8 / 100** (Magi-1 24B + GeoPhys,
2026-06-19); best NVIDIA open-weight entry **Cosmos3-Super, 50.8 ± 2.2** (2026-09-22) — is still ~42–49 points from the
ceiling, and no published system demonstrates that it can be conditioned on a
20-pixel ball and asked for its next position in millimetres
([leaderboard](https://github.com/google-deepmind/physics-IQ-benchmark), [paper](https://arxiv.org/abs/2501.09038)).

The gap the owner is seeing is **not a physics-modelling gap; it is a missing measurement**. Our own gate report says the
same thing from the inside: of 48 event candidates, the dominant rejection reasons are `displacement_corroborated` (15),
`geometry_mismatch` (13), `census_did_not_drop` (12) — i.e. the pipeline is deciding events from a sparse ball *census*
(1–3 classical detections per sampled frame), never from a dense ball *track*
(`out/scan30/eval_regen.json`, measured 2026-09-23).

**Recommended:** a dense, cheap motion-measurement pass (frame differencing inside the verified cloth quad) plus a
rolling/impulse physics prior, and a falsifiable shot-time criterion. Measured cost of the measurement primitive on this
machine: **2.0 min of single-core CPU for the entire 30-minute VOD** (decode + abs-diff, 2.2 ms/frame, 54,206 frames).

---

## 1. Our constraints, restated with numbers measured on this box

| Constraint | Measured value | How measured |
|---|---|---|
| VOD 1 | 1280×720, 30.0 fps, 54,206 frames, 30.11 min (`data/vod_30min_260815.mp4`) | OpenCV `CAP_PROP_*` probe, 2026-09-23 |
| VOD 2 | 1920×1080, 29.997 fps, 11,309 frames, 6.28 min (`data/vod_highlight.mp4`) | same |
| Ball apparent size | median **18.4 px** diameter; p10 13.8 px, p90 24.8 px (1,062 ball instances) | SAM3 radius `r` in `out/scan30/sam3_results.json` + `out/scan30/sam3_census.json` |
| SAM3 cache size | **194 frame-times**, not 43 (56 app frames + 138 project frames) | frame keys in the two cache files |
| Cloth scale | ~2.8 mm/px at the pipeline's 960×540 working frame; a 57 mm ball is ~20 px | comment in `src/ball_census.py:41` |
| Ball motion between frames | **11.9 px/frame at 1 m/s, 35.7 px/frame at 3 m/s** (960×540); **15.9 / 47.6 px/frame** on the 1280×720 frames | 2.8 mm/px and 2.8/1.333 mm/px, ×30 fps |
| SAM3 cost | 47.5 s/frame CPU (documented); **715 h ≈ 29.8 days** for one 30-min VOD | `docs/handoff.md`; arithmetic |
| CPU frame loop | 591 fps decode; 2,045 fps gray+absdiff; **2.2 ms/frame** → 2.0 min for the full VOD | 400-frame timing run, 2026-09-23 |
| GPU | AMD RX 9070 XT; ROCm PyTorch 2.9.1 works for YOLO persons (~26 ms warm); **SAM3's presence head returns zero instances on GPU** (ROCm 6.4 gfx1201) | `docs/handoff.md` §5 |
| Event queue state | 48 candidates → 32 shots + 16 pots (6 duplicates collapsed); 15 confirmed, 26 rejected, 7 unconfirmed; "gate precision estimate 0.13", explicitly **not human-verified** | `out/scan30/eval_regen.json` `aggregates` |
| Assets to build on | `src/ball_census.py` (fused classical+SAM3 census, temporal identity), `src/table_refine.py` (verified cloth quad, 5.09 px median vs hand anchors on vod30), `src/event_gates.py` (pure gate functions), `src/eval_events.py`, 194-frame SAM3 cache | `docs/state.md` 2026-09-22 entries; source tree |

The decisive local fact: **a ball at pool speed moves 12–48 px between frames — up to 2.6× its own diameter.** Any
method that decides ball state from a single frame, or from frames ~0.5 s apart, is sampling far below the event rate.

---

## 2. Open video world models / physics-aware video models (last ~24 months)

| Name | Open? | Weights? | Size / compute | What it predicts | Measured physical accuracy (source) | Runnable on our box? | Applicable to our task? |
|---|---|---|---|---|---|---|---|
| **V-JEPA 2 / 2-AC** (Meta) | Yes (majority MIT) | Yes — ViT-L 300M, ViT-H 600M, ViT-g 1B | 1B-class encoder; CPU-feasible inference; 1M+ h pretraining | **Latent** future representations; 2-AC is action-conditioned on *robot* actions (<62 h Droid) | SSv2 top-1 77.3; EK100 recall@5 39.7 — motion/anticipation metrics, not position accuracy ([repo](https://github.com/facebookresearch/vjepa2), [paper](https://arxiv.org/abs/2506.09985)) | Yes (weights are 1B-class, not multi-hundred-GB) | **No — generates latents, not measurements.** No mechanism to emit "ball at (x,y) in mm". V-JEPA 2.1 exists (2026-03-16) but is still an encoder family |
| **NVIDIA Cosmos-Predict2.5** | Yes | Yes (HF) | 2B / 14B; NIM path requires Hopper-or-later and **≥80 GB VRAM** | Video futures from text/image/video; robot action-conditioned variant | Not listed on the Physics-IQ Verified board under this name ([support matrix](https://docs.nvidia.com/nim/cosmos/2.0.0/support-matrix.html), [repo](https://github.com/nvidia-cosmos/cosmos-predict2.5), [LICENSE = Apache-2.0](https://raw.githubusercontent.com/nvidia-cosmos/cosmos-predict2.5/main/LICENSE)) | Not as deployed: CUDA/TensorRT stack, 80 GB VRAM. Raw weights on an AMD card: **unverified** | **No — generation.** Nothing in the API returns a measured ball state |
| **NVIDIA Cosmos 3** (2026) | Yes (HF checkpoints) | Yes | Super **64B**, Nano **16B**, Edge **4B**; Super targets H200/B200/GB200 | "Sees, reasons, simulates, acts" — world/action models for Physical AI | **Physics-IQ Verified #2: Cosmos3-Super 50.8 ± 2.2; Cosmos3-Edge 32.7** ([leaderboard](https://github.com/google-deepmind/physics-IQ-benchmark), [repo](https://github.com/NVIDIA/Cosmos)) | No: 64B/16B on CUDA-class hardware; 4B Edge targets RTX Pro 6000 / Jetson | **No.** Even the #2 system scores 50.8/100 on *coarse* physical metrics; that is not a measurement instrument |
| **Genie 3** (Google DeepMind) | **No** | **No** | Not published; research preview | Interactive navigable worlds from text; 24 fps, 720p, minutes of consistency | No public benchmark score; blog states a "few minutes" consistency limit ([blog](https://deepmind.google/discover/blog/genie-3-a-new-frontier-for-world-models/)) | N/A | **No** — closed, and a generator besides |
| **LingBot-World** (Robbyant/Ant, 2026) | Yes | Yes (HF `robbyant/lingbot-world-base-cam`) | image-to-video world simulator; 16 fps at <1 s latency | Long-horizon interactive video | None published on Physics-IQ Verified; claims "minute-level horizon" ([model card](https://huggingface.co/robbyant/lingbot-world-base-cam)) | Unknown — size not verified in this pass | **No** — same generator category |
| **ABot-PhysWorld** (AMAP CV Lab, 2026) | Yes (code + weights + training code) | Yes | 14B DiT | Robot-manipulation video with physics-aware training + DPO | 1st on WorldArena leaderboard (2026-04), 2nd at CVPR 2026 GigaBrain World-Model track — **qualitative/manipulation benchmarks, no position error reported** ([repo](https://github.com/flyingGH/ABot-PhysWorld), paper arXiv:2603.23376) | No: 14B diffusion on a CUDA-class target | **No** — predicts robot interaction video |
| **Wan 2.2** | Yes | Yes | MoE A14B: 27B total / 14B active; the documented i2v command asks for **≥80 GB VRAM** (the 5B dense TI2V variant is documented at ≥24 GB, e.g. RTX 4090) | Text/image → video | **Physics-IQ Verified: Wan 2.2 14B = 32.2 ± 0.6; 5B = 27.7 ± 0.9** ([repo](https://github.com/Wan-Video/Wan2.2), [leaderboard](https://github.com/google-deepmind/physics-IQ-benchmark)) | No | **No** |
| **HunyuanVideo 1.5** | Yes | Yes | Not verified in this pass | Text/image → video | **Physics-IQ Verified 33.4 ± 0.8** ([paper](https://arxiv.org/abs/2511.18870), leaderboard) | No | **No** |
| **CogVideoX** | Yes | Yes | 2B / 5B; vendor says 2B on a GTX 1080 Ti, 5B on an RTX 3060 | Text/image → video | **Physics-IQ Verified: CogVideoX-5B 31.8 ± 1.5** ([repo](https://github.com/THUDM/CogVideo), leaderboard) | The only generator here with a plausible consumer-GPU path, but AMD ROCm support is **unverified** | **No** — the benchmark score is the point: 31.8/100 |
| **Mochi 1** (Genmo) | Yes | Yes | Not verified in this pass | Text → video | None on the Physics-IQ Verified board | Unverified | **No** |
| **LTX-Video** (Lightricks) | Yes | Yes (HF) | Not verified in this pass | Text/image → video | None on the board | Unverified | **No** |
| **iVideoGPT** (NeurIPS 2024) | Yes | Yes (HF collection) | Tokenizer 114M/310M + transformer 138M/436M; **64×64 and 256×256** | Action/goal-conditioned future frames, robot data | Reported on manipulation suites at 64×64 — three orders of magnitude coarser than 720p ([repo](https://github.com/thuml/iVideoGPT), [paper](https://arxiv.org/abs/2405.15223)) | Yes in principle | **No** — 64×64/256×256 cannot represent an 18 px ball, let alone localise it |
| **PhysGaussian / PhysDreamer / PhysGen / PhysFlow** | Yes (research code) | Varies | Mesh/Gaussian + MPM or rigid-body solvers | Physically-plausible *appearance and deformation* of 3D assets | No ball/position benchmark; evaluated by rendering and user preference ([PhysGaussian](https://arxiv.org/abs/2311.12198), [PhysDreamer](https://arxiv.org/abs/2404.13026), [PhysGen](https://arxiv.org/abs/2409.18964), [PhysFlow](https://arxiv.org/abs/2411.14423)) | Not applicable | **No** — these need a 3D asset and material parameters; we need a detector |

**Pattern across the table:** the open world-model category is now large, well-licensed, and genuinely open-weight — and
uniformly aimed at *synthesis*. The only quantitative evidence of physical competence that exists is coarse
(scene-level IoU/MSE on Physics-IQ, manipulation success on WorldArena), not positional.

---

## 3. Benchmarks that measure physical understanding in video

| Benchmark | What it scores | Headline finding | Source |
|---|---|---|---|
| **Physics-IQ** (ICCV'25 challenge; WACV 2026 paper) | 396 real videos, 66 scenarios, 8 s, 30 fps, 3 views × 2 takes; Spatial-IoU, Spatiotemporal-IoU, Weighted-spatial-IoU, MSE, normalised so a second real take = 100 ("physical variance") | **Best model 24.1 / 100** (VideoPoet multiframe); all models "show a massive gap" to real physics. Realism ≠ physics: Sora fooled an MLLM 55.6% of the time (chance 50%) while scoring worst-in-class on physics | [paper](https://arxiv.org/abs/2501.09038), [site](https://physics-iq.github.io/) |
| **Physics-IQ Verified** (2026, recommended variant) | Same, with hardened prompts/metrics; leaderboard with ± std over 4 runs | Top entry **58.2 ± 1.8** (Magi-1 24B + GeoPhys, 2026-06-19); **Cosmos3-Super 50.8 ± 2.2** (2026-09-22); **Sora 2 26.5 ± 0.8**. Ideal = 100.0 | [repo README leaderboard](https://github.com/google-deepmind/physics-IQ-benchmark) |
| **WorldModelBench** (2025) | Instruction-following + physics-adherence violations in generated video, judged by a model | Motivated by "current benchmarks … ignoring important factors to world models such as physics adherence" — abstract-level claim only in this pass (results table not extracted) | [arXiv:2502.20694](https://arxiv.org/abs/2502.20694) |
| **CrashTwin / physics-grounded multi-agent benchmark** (2026) | Metric-scale kinematics recovered from generated video; SE(3)/Sim(3) errors; 38K crash events, mini-eval 100 synthetic + 16 real | **"No publicly accessible model can recover metric-scale dynamics from uncalibrated severe-collision videos"**; the authors' own tracking baseline needs relinking + Kalman + metric depth correction to reach **sub-metre** instance error | [arXiv:2606.28757](https://arxiv.org/abs/2606.28757) |
| **Physion** (+ Physion++ 2023) | 8 simulated scenarios; humans vs models on object-contact prediction | Algorithms need "more physically explicit scene representations" to reach human ability | [site](https://physion-benchmark.github.io/), [Physion++ (NeurIPS 2023)](https://papers.nips.cc/paper_files/paper/2023/file/77777777777777777777777777777777-Paper-Datasets_and_Benchmarks.pdf) |
| **CLEVRER** | Synthetic collision videos; 4 question families (descriptive / explanatory / predictive / counterfactual) | Models "thrive on the perception-based task (descriptive)" and "perform poorly on the causal tasks" | [site](http://clevrer.csail.mit.edu/) |
| **IntPhys** (2018) | Violation-of-expectation framework for intuitive physics | Pre-window and synthetic; included only because the brief named it | [arXiv:1803.07616](https://arxiv.org/abs/1803.07616) |

### The single most useful benchmark finding

**Physics-IQ scores *outcomes*, and it normalises the ceiling to a second real recording of the same event — not to a
perfect prediction.** Even so, the entire open field sits at 27–58 out of 100, and the metric is scene-level IoU/MSE,
never "the ball is 3 px from where it should be". Meanwhile the 2026 multi-agent benchmark states outright that
recovering **metric-scale** dynamics from generated video is an unsolved problem, and its own best pipeline reaches only
sub-metre error — roughly **two orders of magnitude coarser** than what a 2.8 mm/px cloth requires.

**Conclusion: no benchmark in this space publishes a positional/velocity error for ball-like objects, because no model
produces one.** "Effective" in this literature means "physically plausible to a judge", not "numerically correct".

---

## 4. Object-centric tracking and dynamics for tiny, fast sports objects — the actually relevant literature

| Work | What it does | Reported numbers | Relevance to us |
|---|---|---|---|
| **TrackNetV2 → V4** | 3-frame heatmap regressor for tiny fast balls (tennis, shuttlecock); V4 adds motion-attention maps from frame differencing | Detection correct if within **4 px**. Tennis test split (3,279 frames): TrackNetV2 **Acc 93.4 / F1 96.5 @ 186.4 FPS**; TrackNetV4 v2 **Acc 94.7 / F1 97.2 @ 169.1 FPS**; fine-tuning adds +0.8–1.4 pp ([arXiv:2409.14543](https://arxiv.org/abs/2409.14543)) | **Closest published match to our problem, and it is a *detector*, not a world model.** Note the honest picture: the CNN family gets ~95% at 4 px, and the *entire* V4 contribution is ≤1.4 pp |
| **TrackNetV3** (ACM TOMM 2024) | Adds background as auxiliary input + trajectory rectification via inpainting masks to repair occluded frames | Accuracy not extracted in this pass ([repo](https://raw.githubusercontent.com/qaz812345/TrackNetV3/master/README.md), paper [10.1145/3595916.3626370](https://dl.acm.org/doi/10.1145/3595916.3626370)) | The rectification idea is directly stealable: occluded ball → repair the *trajectory*, not the frame |
| **Kalman-filter trackers on fast tiny objects** (2025) | Benchmarks DeepOCSORT / OCSORT / ByteTrack / BoTSORT / StrongSORT on a racquetball dataset | All "exhibit poor performance … due to erratic and non-linear motion"; ByteTrack 26.6 ms/frame but **ADE 114 px vs OCSORT 79.9 px** (≈260% worse); conclusion: current KF trackers "inadequate … for reliable tiny object tracking" ([arXiv:2509.18451](https://arxiv.org/abs/2509.18451)) | **Direct warning:** adding a Kalman/MOT tracker on top of a weak detector will not fix our timestamps. Failures cascade from detector misses |
| **Rule-constrained cue-ball identification, broadcast snooker** (2026) | Formulates ball identity as assignment under the snooker inventory (1 cue + 15 reds + 6 colours) rather than a per-candidate appearance test | **419 hand-annotated shots: 88.1% → 95.5% identity accuracy; held-out venues 80.5% → 95.2%**; on 150 newly covered shots 38.0% → 76.7%; metric-state coverage (CueLift) **36.2% → 55.4%**; ceiling 92.0% because the cue ball is missing from the candidate pool in 12 shots ([arXiv:2609.23450](https://arxiv.org/abs/2609.23450)) | **The most transferable idea in this survey:** a *bounded inventory* + rules turns identity into an assignment problem. Our `src/ball_census.py` already gestures at this (one physical ball per colour; presence refutes a vanish). Also note the sobering part: even with 95% identity accuracy, metric state exists for only ~55% of shots |
| **Billiards Sports Analytics** (ACM TOMM 2024) | Dataset of pro 9-ball from YouTube (227 players, 94 tournaments): break layouts, ball traces, statistics; tasks = layout prediction/generation/retrieval | Data extracted **manually with Kinovea**, not by automated tracking; results reported for layout tasks (BLCNN/BLGAN), not ball dynamics ([arXiv:2407.19686](https://arxiv.org/abs/2407.19686)) | Evidence that public billiards trajectory data is still hand-annotated — i.e. the automated measurement problem we have is not solved off the shelf |
| **pix2pockets** (2025) | 8-ball shot suggestion from a *single* image in the wild; YOLOv5 ball detection + projection | Self-collected annotation: 195 images / 5,748 boxes (+52/1,624); **AP50 91%**, >95% when the table occupies enough pixels, dropping to ~50% for distant views; projection error 0.22–0.76 cm; shot precision needed 0.25° (one ball) / 0.01° (ball-ball) ([arXiv:2504.12045](https://arxiv.org/abs/2504.12045)) | Two useful facts: (a) a tiny labelled pool dataset *is* enough for a small YOLO to hit 91% AP50; (b) the precision that shot prediction requires from a ball position is brutal (0.01°) — a further argument against generative short-cuts |
| **Attention-Pool** (Computers 14(9):352, 2025) | 9-ball game video analytics (object attention + temporal gated attention) for event/outcome classification | **UNVERIFIED in this pass** — both `https://doi.org/10.3390/computers14090352` and `https://www.mdpi.com/2073-431X/14/9/352` returned HTTP 403; an internal note cites "87.4% clear-shot accuracy" but that number could not be re-checked at the source | Treat as exists-but-unread; do not build on the number |

---

## 5. Physics engines as priors/constraints (not detectors)

| Engine | License / stack | What it gives us | What it cannot give us | Source |
|---|---|---|---|---|
| **Newton** | Apache-2.0; Linux Foundation project; built on **NVIDIA Warp**, with **MuJoCo Warp as its primary backend** | Rigid/soft/multiphysics, differentiability, GPU batch | Needs an initial state and parameters we are trying to measure; CUDA/Warp-bound | [repo](https://github.com/newton-physics/newton) |
| **MuJoCo Warp (MJWarp)** | Apache-2.0; "targeting NVIDIA GPUs"; scales better than MJX "on nearly every workload" | Fast batched contact simulation if we ever needed it | Same state problem, plus NVIDIA-only execution | [docs](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html), [repo](https://github.com/google-deepmind/mujoco_warp) |
| **Genesis World 1.0** | Open (Genesis AI); unified multi-physics + Nyx renderer + Quadrants compiler | A Pythonic simulator for physical AI | Same; the historical "43M FPS" marketing claim is **UNVERIFIED** in this pass (the current README no longer carries it) | [repo](https://github.com/Genesis-Embodied-AI/Genesis) |

**Honest framing:** for a single ball rolling on a plane, we do not need any of these. Constant-deceleration rolling
(`v(t) = v0 − μ g t` on cloth) plus a specular cushion reflection with a restitution coefficient is a handful of
equations and fits in the existing `src/event_gates.py` pure-function style. A physics engine earns its keep when you
have many interacting rigid bodies and *known* initial conditions; we have neither, and these engines are CUDA-first on a
ROCm box.

---

## 6. Verdict, ranked on the four axes that matter here

Ranking criteria: **(a) can it run on this machine, (b) does it measure or generate, (c) is there quantitative evidence,
(d) integration cost into `ball_census` / `event_gates`.**

1. **Classical dense motion measurement + rolling/cushion physics prior — GO.**
   (a) Runs: 2.2 ms/frame single-core on CPU. (b) Measures: it returns px positions and velocities. (c) Evidence:
   TrackNet's own numbers show a *learned* version of this reaches 94.7% at ≤4 px — the classical version is the cheap
   first cut. (d) Low: a new observation source into `ball_census.py`, one new gate in `event_gates.py`.
2. **A TrackNet-style tiny-ball heatmap network trained on our own footage — CONDITIONAL GO (only if #1's recall is
   insufficient).** (a) Small conv nets like YOLO already run on this GPU under ROCm (~26 ms warm, `docs/handoff.md`);
   a TrackNet-class net is **unverified** but plausible. (b) Measures. (c) The only method class with published
   sub-4-px numbers on this exact problem. (d) High: labelling is the real cost.
3. **Rule/inventory-constrained identity assignment (snooker 2026 pattern) — ADOPT AS A DESIGN PATTERN, cheap.**
   Our census already encodes a coarse version; the snooker result (95.5% identity, but 55.4% metric coverage) argues
   that identity is tractable and **coverage is the bottleneck** — exactly the owner's complaint.
4. **Video world models (Cosmos 3, V-JEPA 2, Wan 2.2, LingBot-World, Genie 3) — WRONG TOOL.**
   (a) Mostly cannot run: 16–64B, 80 GB VRAM, CUDA/TensorRT paths. (b) They **generate**; whether a generated *plausible*
   future matches the *true* one is exactly what Physics-IQ measures, and the answer is 26.5–58.2/100. (c) No published
   positional accuracy for ball-like objects exists. (d) Extremely high: new stack, new failure modes.
5. **Physics engines (Newton, MuJoCo Warp, Genesis) — NOT NEEDED.**
   (a) CUDA-first on an AMD box. (b) Would be a *constraint*, not a measurement. (c) No evidence they help when the state
   is unknown. (d) Medium-high integration for ~zero expected gain over three lines of analytic rolling physics.
6. **Object-centric interactive world models (iVideoGPT, 64×64/256×256) — WRONG TOOL, wrong resolution.** A ball is
   ~18 px at 720p; these models run at 64–256 px *for the whole scene*.
7. **Physics-based generation (PhysGaussian/PhysDreamer/PhysGen/PhysFlow) — WRONG TOOL.** They need a scene asset and
   material parameters and produce plausible deformation video; none of them localises a ball in an existing VOD.

### Plain statement of what is the wrong tool, and why

- **Generation is not measurement.** A diffusion/world model's output distribution can be sharp and still wrong; the
  Physics-IQ authors had to invent IoU-style metrics because PSNR/SSIM/FVD "are not equipped to judge whether a model
  understands real-world physics" ([paper](https://arxiv.org/abs/2501.09038)). "Plausible" is the failure mode we are
  trying to detect, not the product we want.
- **The state we need is the input these models require.** Every engine and physics-based generator in §5 needs initial
  positions/velocities; those are precisely our unknowns.
- **The measurement literature is 100× cheaper and 1000× better documented for our case.** A 4-px-accuracy heatmap net on
  a 3-frame stack, trained on a few hundred labelled frames, beats a 14B video diffusion model on this task by
  construction — and the 2026 multi-agent benchmark's own conclusion ("no publicly accessible model can recover
  metric-scale dynamics", [arXiv:2606.28757](https://arxiv.org/abs/2606.28757)) is the field admitting it.

---

## 7. Recommendation — 1 primary approach, 2 follow-ons, with costs and falsifiable criteria

### R1 (do first, 1–2 days): dense motion measurement inside the cloth quad, then "motion-before-timestamp"

**What:** for every frame of the VOD, compute a background-subtracted motion energy restricted to the verified cloth quad
from `src/table_refine.py`; extract moving blobs whose size/brightness match a ball (14–25 px); attach each blob to the
existing census as an extra `Observation` source with a `source='motion'` tag. Then add one gate: **a shot candidate is
`unconfirmed` unless at least one moving-blob track exists within ±0.5 s of its timestamp.**

**Cost:** measured primitive = 2.2 ms/frame CPU (decode+gray+absdiff) = **2.0 min per 30-min VOD**; with blob extraction
and filtering, budget **5–15 min per VOD, single-core, no GPU**. Development 1–2 days. Ground truth: 10 hand-checked shot
times ≈ 1–2 h of human time.

**Falsifiable success criteria:**
- On 10 hand-checked shot events, ≥9 have a measured motion onset within **±0.2 s** of the hand-labelled time.
- **Zero** queue events are emitted with no measured ball motion in ±0.5 s (this directly answers the owner's complaint).
- Distinguishing cue-ball motion from player motion: the false-motion rate inside the cloth quad is <1 blob/second of
  footage outside shot windows.

### R2 (only if R1's recall is insufficient, 1–2 weeks): tracking-by-rectification with a physics smoother

Add a constant-deceleration rolling model + cushion reflection as the motion model of a small RTS/particle smoother over
the R1 blobs (the TrackNetV3 "repair the trajectory, not the frame" idea, [repo](https://raw.githubusercontent.com/qaz812345/TrackNetV3/master/README.md)),
giving explicit uncertainty and an occlusion flag rather than a guessed position.
**Cost:** CPU-only; 2–4 days of implementation; evaluation reuses the same 10–20 hand-checked events.
**Falsifiable:** after an occlusion of ≤5 frames, predicted ball position is within **≤2 px (≈5.6 mm)** at the first
frame after reappearance on ≥80% of 20 hand-checked occlusions; and predicted cushion-impact times match hand-labelled
contacts within ±0.1 s.

### R3 (only if R1+R2 still miss shots, 2–4 weeks): a TrackNet-class heatmap detector trained on our footage

**What:** 3-frame-stack heatmap CNN (TrackNetV2/V4 architecture), trained on our two VODs.
**Cost:** the dominant cost is labels — 500–2,000 hand-labelled frames; bootstrap them semi-automatically from the
194 cached SAM3 frames plus R1 motion peaks, then correct by hand (≈4–10 h human). Training: 2–6 GPU-hours for a
15–20M-param net — **but ROCm compatibility for this specific net is unverified**; YOLO person detection on this GPU is
verified at ~26 ms warm (`docs/handoff.md`), which is encouraging but not proof.
**Falsifiable:** median error **≤4 px** and ≥90% frame-level presence accuracy on 50 held-out hand-labelled frames with
the ball visible; end-to-end shot-time error ≤0.2 s on the same 10 events; inference ≥30 fps on our GPU or ≥10 fps on CPU.

---

## 8. What we should NOT do

1. **Do not use SAM3 as the ball sensor at scale.** 47.5 s/frame CPU → **715 h (29.8 days)** for one 30-min VOD
   (`docs/handoff.md`). Keep it as a sparse verifier of the 194 cached frames.
2. **Do not download or fine-tune a video world model** (Cosmos 3, Wan 2.2, V-JEPA 2-AC, LingBot-World). They generate,
   they are 4–64B, their documented deployment is 80 GB CUDA-class hardware, and their best measured physical score is
   58.2/100 on coarse metrics. No training budget exists and none of this would produce a ball position.
3. **Do not add another Kalman/MOT tracker and expect the timestamps to improve.** Published evidence on fast tiny
   objects shows five standard KF trackers all fail, with errors cascading from detector misses
   ([arXiv:2509.18451](https://arxiv.org/abs/2509.18451)).
4. **Do not build on Physics-IQ / WorldModelBench scores as if they predicted our accuracy.** Those metrics are
   scene-level IoU/MSE over 8-second clips; they have never been reported for a 20 px ball.
5. **Do not substitute a physics engine for a detector.** Newton/MuJoCo Warp/Genesis need the state we are trying to
   measure, and their fast paths are CUDA-bound on an AMD box.
6. **Do not hand-annotate the whole dataset Kinovea-style as the end state.** That is what the published billiards
   dataset did ([arXiv:2407.19686](https://arxiv.org/abs/2407.19686)); use hand labels only as evaluation ground truth.

---

## 9. Unverified / could-not-source list (do not quote these as fact)

- **Attention-Pool (Computers 14(9):352, 2025)** — publisher blocks automated fetch (HTTP 403 from both `doi.org` and
  `mdpi.com`). Its existence is confirmed via [DOAJ](https://doaj.org/article/77777777777777777777777777777777) search
  metadata, but no accuracy figure was re-verified. The "87.4% clear-shot accuracy" number circulating in-repo is
  **UNVERIFIED**.
- **LTX-Video, Mochi 1, HunyuanVideo 1.5, Cosmos 3 Nano's exact Physics-IQ Verified score, LingBot-World parameter
  count** — open weights confirmed, sizes/VRAM/licence terms not confirmed in this pass.
- **Genesis "43M FPS" claim** — not present in the current README; treated as UNVERIFIED.
- **TrackNetV3 accuracy numbers** — the repo README describes the method (background auxiliary input, inpainting-based
  trajectory rectification) but the README carries no numbers; the paper is paywalled at the publisher.
- **WorldModelBench results table** — only the abstract was extracted; the per-model physics-violation rates were not.
- **ROCm behaviour of any diffusion or TrackNet-class network on the RX 9070 XT** — untested. The only verified GPU
  workload in this repo is YOLO person detection.

---

## 10. One-line answer to the owner's question

No open video world model on the market will add ball movement to our event timestamps, because none of them measures —
Physics-IQ's own authors had to invent IoU metrics precisely because generative realism says nothing about physical
correctness, and the best entry on the 2026 open leaderboard is 58/100 on that coarse scale. What will add it is a
2-minute-per-VOD CPU difference pass plus a rolling-ball physics prior, evaluated against 10 hand-checked shot times.
