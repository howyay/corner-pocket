# Near-real-time ball detector — fast labels, and the production training pass

The owner needs near-real-time: at 30 fps the budget is **33 ms/frame**. The runtime
side is already proven — the 204,529-param TrackNet-style net runs at **15.5 ms/frame**
on the ROCm GPU (≈64 fps) and trains in minutes. SAM3 cannot be in the runtime path: on
this box its GPU build returns **zero instances** (ROCm 6.4, gfx1201) and its verified
CPU path costs ~27–45 s/frame, so **5,000 labels is ~62 CPU hours**. Part A is the lever
on that number; Part B is the production-shaped detector that consumes the labels.

Everything here is measured on this machine, with the commands at the bottom.
**SAM3 is the teacher, not ground truth** — "2.5 px against SAM3" measures distillation
fidelity, and the overlays are the only accuracy evidence a human can check.

## Part A — the label bottleneck

### The diagnosis, before the fix

The CPU path's ~45 s/frame is not one cost. Instrumented per stage
(`out/fast_ball_labels/agreement.json`):

| stage | CPU | hybrid |
|---|---|---|
| vision encoder (`backbone.vision_backbone`) | ~31–37 s | **≈0.3 s** (ROCm device) |
| text encoder + grounding head | ~8–11 s | ~6 s (CPU) |

The encoder is the part that wants a GPU; the head is the part that is *broken* on this
GPU. They are separable, so `src/fast_ball_labels.py` separates them.

### What was built: `hybrid` SAM3

`Sam3Labeller(mode="hybrid")` keeps one model instance, moves
`model.backbone.vision_backbone` to the ROCm device, and leaves the text encoder and
grounding head on the CPU. The head's arithmetic is therefore byte-for-byte the verified
CPU path — same weights, same dtype, same device, same kernels — which is what makes the
instances checkable rather than asserted.

One non-obvious fix is load-bearing. `SAM3Image.device` is a property that reads the
model's **first parameter**, so moving the encoder to the GPU silently moved the
model's idea of its own device with it and the CPU head began building GPU prompts
(`RuntimeError: Expected all tensors to be on the same device … mat1 is on cuda:0`).
`set_mode` pins it back with `model._device = torch.device("cpu")`.

The GPU's own head was left alone: it is the thing that returns nothing, and a mode
that "runs" without instances is not a labeller.

### Measured

| | CPU SAM3 | hybrid | |
|---|---|---|---|
| seconds/frame | 27.1 | **6.27** | same process, same weights |
| frames/minute | 2.21 | **9.57** | **4.32×** |
| 5,000 frames | 37.6 h | **8.7 h** | |

**Instance-count agreement against the known-good CPU path** (`agreement`, 6 frames):

| t | count CPU | count hybrid | counts agree | matched | max position error |
|---|---|---|---|---|---|
| 4.1 | 11 | 11 | ✔ | 11 | 0.00 px |
| 4.6 | 10 | 10 | ✔ | 10 | 0.00 px |
| 5.1 | 10 | 10 | ✔ | 10 | 0.00 px |
| 6.3 | 10 | 10 | ✔ | 10 | 0.00 px |
| 10.1 | 10 | 10 | ✔ | 10 | 0.00 px |
| 20.2 | 2 | 2 | ✔ | 2 | 0.00 px |

**6/6 frames with identical counts, 6/6 fully matched, 0.00 px maximum error.** The four
full-rack frames read 8–10 balls, which is what the CPU baseline says they hold.

### The labels it produced

`label` walks frames at a stride, skips anything inside the frozen held-out blocks, and
writes incrementally (a 7 s/frame job killed at 90 % must not lose the 90 %).

| | |
|---|---|
| new teacher frames | **275** |
| new ball instances | **1,660** (raw score ≥ 0.62) |
| wall clock | 34.5 min |
| rate | **8.44 frames/min** under a loaded box |

### The honest gap, and the second lever

9.57 frames/min is 4.3×, not "thousands of frames in minutes". The route that does meet
that number is not SAM3 at all: `prelabel` runs the trained student over a strided series
and keeps only detections that survive a **persistence filter** — a ball is in the next
frame. That temporal rule is *new* information (it is not the teacher voting again),
which is what makes a pseudo-label worth more than a re-run of the teacher. Everything
the filter rejects goes to a **review queue** for human eyes rather than into the dataset
silently. Measured with the 960×540 student:

| | |
|---|---|
| frames scanned | 600 (a 60 s window at a 0.1 s stride) |
| wall clock | **52.4 s** |
| rate | **686.8 frames/min** (11.45 fps, 87.4 ms/frame) |
| ball labels kept | **6,415** |
| sent to the review queue | 17 |

**That is the "thousands of labels in minutes" number: 6,415 labels in 52 s.** What it is
*not* is a precision filter — at this stride it rejected 17 of 6,432 detections, because
a ball and a static cloth artefact both persist. See the limitations at the end.

```
PYTHONPATH=. .venv/bin/python -m src.fast_ball_labels prelabel \
    --bitmap out/tiny_ball_probe/960x540-scratch.pt --size 960x540 \
    --start-s 600 --end-s 660 --stride-s 0.1 --radius-px 40 --min-support 0.5
```

## Part B — the production training pass

### The scaling curve

The two axes the probe's section 6 named are resolution (640×360 halves the ball to
9.4 px, and 64 held-out misses sat at a 6.9 px median radius) and data volume. Both were
moved. The held-out set is **frozen** (`out/tiny_ball_probe/held_frozen.json`): adding
labels must not move the validation set, and `split_blocks` re-indexes blocks when gaps
are filled, so round 2 would otherwise be scored on a different 40 frames than round 1.

| round | input | train frames | epochs | P | R | **F1** | loc. median | loc. p90 | ms/frame | fps |
|---|---|---|---|---|---|---|---|---|---|---|
| probe | 640×360 | 116 | 25 | 0.881 | 0.751 | 0.811 | 2.5 px | 4.48 px | 15.5 | 64 |
| **r1** | **960×540** | 300 | 20 | 0.940 | 0.914 | **0.927** | **1.48 px** | **3.62 px** | 35.7 | 28.0 |
| r2 | 1280×720 | 300 | 12 | 0.961 | 0.868 | 0.912 | 1.19 px | 3.20 px | 85.3 | 11.7 |

Labels behind these rounds: **468 frames / 2,722 instances** — the original 1,062 plus
**1,660 new teacher labels from Part A**, at the same ≥0.62 score cut. Training frames
were capped at 300 evenly spaced frames (`--max-train`): the frame cache holds three
uint8 frames per training frame, so 421 frames at 960×540 is ~2 GB of host RAM and the
uncapped round was OOM-killed twice on this 32 GB box, which is shared with three other
workers.

### Cost/benefit of native 1280×720

Native is **not** the operating point. It buys localisation — p90 3.20 px and median
1.19 px, both better than 960×540 — but it costs **2.4× the time** (85.3 ms vs 35.7 ms
end-to-end, 11.7 fps) and its F1 is *lower* (0.912 vs 0.927). The last part is confounded:
r2 ran 12 epochs against r1's 20, so this is not a clean read on accuracy. The cost side
is not confounded — 2.4× is measured — and on its own it settles the choice: at native
resolution the detector cannot clear the fps bar under any training schedule.

### Against the three bars

| bar | 960×540 | met |
|---|---|---|
| held-out F1 ≥ 0.90 | **0.927** (P 0.940 / R 0.914 @ 0.425) | ✔ |
| p90 localisation ≤ 4 px | **3.62 px** (median 1.48 px) | ✔ |
| ≥ 30 fps on the GPU, end-to-end | **28.0 fps** (35.7 ms) | ✘ |

The third bar is the one that is short, and the two numbers behind it say where. The
**model alone is 23.5 ms/frame (42.6 fps) and clears 30 fps**; the end-to-end call —
decode, resize, the 3-frame stack, then the forward — is 35.7 ms. A second, later
measurement on the same checkpoint under a load average of 16–31 gave 27.2 ms
inference-only (36.7 fps) and 39.6 ms end-to-end (25.2 fps), so the frame pipeline, not
the network, is what needs the next 3 ms. The measured numbers on this box carry the
box's load: three other workers were running throughout, and the probe's own 15.5 ms was
taken when it was quieter.

### Disagreements, and which side is wrong

At the operating point (`out/tiny_ball_probe/report_960x540.json`), against the probe's
640×360 run in brackets:

| | 960×540 | probe |
|---|---|---|
| teacher balls the student missed (**FN**) | **22** [64] | teacher score median **0.79**, min 0.627 — confident labels, so these are **student** recall errors; radius median **7.45 px** against 9.2 px overall, so still the small balls; **11 of 22 within 25 px of the cloth edge** |
| student detections with no teacher ball (**FP**) | **15** [26] | all 15 inside the cloth, peak score median 0.53; whether they are student errors or balls the teacher missed **needs eyes, not another metric** |

Raising the resolution cut the recall failure by two-thirds and shrank the median error
from 2.5 px to 1.48 px. The residual FN are the same population as before — small and
rail-adjacent — just far fewer of them.

### Overlays for the owner's eyes

`out/tiny_ball_probe/overlays2/01_t00043.7s.png` … `20_t00570.0s.png` — **20 held-out
frames**, green = teacher label, red = student, with the student's peak score printed.
The teacher is not ground truth, so nothing in this report substitutes for looking at
them.


## Reproduce

```
PYTHONPATH=. .venv/bin/python -m src.fast_ball_labels agreement --frames 6
PYTHONPATH=. .venv/bin/python -m src.fast_ball_labels label --count 300 --stride-s 6
PYTHONPATH=. .venv/bin/python -m src.fast_ball_labels prelabel --size 960x540 \
    --bitmap out/tiny_ball_probe/960x540-scratch.pt --start-s 600 --end-s 660 \
    --stride-s 0.1 --radius-px 40 --min-support 0.5
PYTHONPATH=. .venv/bin/python -m src.tiny_ball_net rounds --plan "960x540:20" --max-train 300
PYTHONPATH=. .venv/bin/python -m src.tiny_ball_net report --size 960x540 \
    --bitmap out/tiny_ball_probe/960x540-scratch.pt --overlay-count 20
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
```

Artifacts: `out/fast_ball_labels/agreement.json`, `out/fast_ball_labels/prelabel.json`,
`out/tiny_ball_probe/new_labels.json`, `out/tiny_ball_probe/held_frozen.json`,
`out/tiny_ball_probe/rounds_960.json`, `rounds_1280.json`, `report_960x540.json`,
`overlays2/*.png`. Nothing is written to the queue, the gates, or
`out/scan30/annotations.json`.

## What this pass could not do

1. **The end-to-end fps bar.** 28.0 fps against 30. The network is 42.6 fps; the frame
   pipeline (decode + resize + stack) is the 12 ms that is missing, and it is a plain
   engineering fix, not a modelling one.
2. **The native-resolution accuracy read is confounded.** r2 ran 12 epochs against r1's
   20. Nothing here says native is *less* accurate; it says native costs 2.4× and its F1
   at an equal-epoch comparison has not been measured.
3. **No human verification.** Every number above is against the teacher. The 15 FP are
   unresolved by construction.
4. **The persistence filter is a noise filter, not a precision filter.** At a 0.1 s
   stride it rejected 17 of 6,432 detections (kept fraction 0.997): a ball and a static
   cloth artefact both "persist", so re-detection cannot separate them. Sending the
   review queue to a human at that rate would cost more than labelling by hand. The
   filter needs a per-track motion fit before the queue is worth a human's time; the
   scan's throughput (686.8 frames/min, 6,415 labels in 52 s) is real, the queue's
   precision is not yet.
5. **The self-training round was not run.** Part A's teacher labels carried the 640×360
   → 960×540 gain; the student pseudo-labels were produced and measured for throughput
   but never added to a training round, so their effect on held-out F1 is unknown.

