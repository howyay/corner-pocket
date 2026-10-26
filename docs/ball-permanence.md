# Ball permanence on the table plane

The console loses a ball when the detector does. This document records the world
state that fixes that, the numbers the demo measured, and what the layer does not
do yet.

## What the layer is

`src/ball_world.py` keeps the known set of balls as a world state in table
millimetres. Every ball owns a slot. A slot is retired only by pocket evidence,
or by an explicit rack reset. A missing detection is a visibility question, not
an identity question.

The state machine has five words:

- `active` - matched this frame.
- `coast` - unmatched, the predicted spot is visible, inside the patience.
- `occluded` - unmatched, the predicted spot lies under an occluder.
- `lost` - unmatched beyond the patience, or an occlusion that outlived
  `occluded_patience_s`. The slot stays, and the words say so.
- `potted` - the predicted path entered a pocket. The slot is retired.

Assignment is global over the known set. Every frame builds a cost matrix
(prediction distance, colour compatibility, confidence) and solves it with
`scipy.optimize.linear_sum_assignment`. A settled ball's colour is its identity: a
different colour group cannot claim the slot. Similar colours (red, maroon, pink)
are compatible, because a 13-pixel ball carries no reliable hue.

Physics is closed-form: rolling friction is a constant deceleration, a cushion
reflects the velocity and keeps `cushion_retain`, and a pocket ends the ball.
`Slot.predict` is therefore a physical prediction, not a linear extrapolation of
pixels.

## What the demo measured

Input: `data/vod_30min_260815.mp4`, from t=1105 s for 40 s at 30 frames per
second (1186 frames, a 9-ball rack and the break). Observations come from the
trained YOLO11n-seg ball model at `imgsz=1280`; occluders come from YOLOv8n
person boxes; the table quad comes from the saved static-camera prior
(`detect_table_for_frame(..., dataset="vod30")`). That run mapped the quad to
2540 x 1270 mm with the head rail on x. Round 128 found that this put the side
pockets on the short rails. The demo and the world now use the canonical frame of
`src/table_geometry.py`: 1270 x 2540 mm, head rail at the top, side pockets on the
long rails. The numbers below come from the first run.

| quantity | value |
|---|---|
| slots seeded at t=1105.5 s | 11 |
| frames | 1186 |
| matched slot-observations | 6050 |
| occlusion episodes | 72 |
| re-acquired after occlusion | 62 (86 %) |
| lost episodes (slot kept) | 34 |
| identity switches (colour-group conflict) | 0 |
| frames with every slot unmatched | visible in the demo (a player covers the table) |

The demo renders `out/ball_world_demo/demo.mp4` and
`out/ball_world_demo/metrics.json`. Every slot carries a visible state: green
ring = active, yellow = coast, orange = occluded, red = lost. The trail is the
slot's own history in table millimetres.

Reproduce:

    PYTHONPATH=. .venv/bin/python tools/ball_world_demo.py \
        --start 1105 --seconds 40 --fps 30 \
        --weights <ball segmenter>.pt \
        --gate-mm 70 --gate-slack 1.0 --bootstrap-gate-mm 220 \
        --seed-frames 15 --out out/ball_world_demo

## Limits the demo exposed

1. Seeding is one moment. A ball hidden at seed time never enters the set, so 11
   of the rack's balls were tracked while the rest stayed unmatched. A rack prior
   (9-ball: nine known positions) would seed the full set exactly. That is the
   next step, not a property of the tracker.
2. The occluder channel is a person bounding box. A player bent over the table is
   sometimes missed, so a hidden ball reads `coast` instead of `occluded`. The
   slot is kept either way; the word is what changes.
3. Colour names are coarse at 13-pixel balls (nearest palette on a
   brightness-normalised mean). They are a hint and a display, not the identity
   by themselves. The demo's identity came from position and physics.
4. `friction_mm_s2 = 250` is a default, not a fitted value. A fitted value would
   tighten the fast-ball gates.
5. There is no two-pass replay yet, and no game-state coupling: the pot gate's
   `disappeared_outside_pocket` and `reappeared_after_gap` verdicts are not yet
   wired in as slot transitions.

## Tests

`tests/test_ball_world.py` drives the state machine with synthesis: constant
deceleration, prediction/step agreement, cushion reflection, occlusion with
re-acquisition at the predicted spot, coast then lost, occlusion expiry, pocket
retirement, colour rejection, and crossing balls that keep their identities.
