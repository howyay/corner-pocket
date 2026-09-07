# E2E-1 — corrected 30-min pipeline run (vod30_260815)

Status: first corrected end-to-end run assembled 2026-09-07. Attribution v0
included; formal validation waits on the :8124 review (event + shooter GT).

## Chain (each step = a committed src/ tool)

| Step | Tool | Artifact | Result |
|---|---|---|---|
| 1. Segment corners | `quad_refine.py` + median | `out/corners_30min_v2.json` | 163/300 frames, jitter 3.95 px median (was ~205 px) |
| 2. Calibration (rect-PnP, auto anchors) | `calib_vod30.py` | `out/calib_vod30.json` (f=1685, H mm->px, biases) | bias-corrected holdout mean 30 mm (bar 15 mm; needs manual anchors) |
| 3. Ball segmentation (existing SAM3 pass) | `sam3_confirm` | `out/scan30/sam3_results.json` | 56 confirmed frames, counts 10..0 chain |
| 4. Events | `rebuild_events_v2.py` | `out/scan30/events_v2.json` | 57 shots + 10 pot rows, chain 10→8→6→5→4→3→1→0, causality 0 |
| 5. Player sensing | SAM3 persons (12 instants) + YOLO | `out/pid1_persons*/`, tracklets | YOLO matches SAM3 13/14; 2 persistent tracks/window |
| 6. Identity prototypes | `pid_identity.py` | `out/pid_identity_v0.json` | A light / B dark, sep ratio 4.3 |
| 7. Per-shot actor | `pid_shooter2.py` | `out/events_actors.json` | 45/57 geometry (white-ball), 7 colour, 5 no-person; 20 A/B switches |

## Run it

```bash
# steps 1-2
.venv/bin/python src/audit_calib.py
.venv/bin/python src/quad_refine.py            # per-frame check
# step 4
.venv/bin/python src/rebuild_events_v2.py      # needs out/scan30/sam3_results.json + records.json
# steps 5-7
.venv/bin/python src/pid_identity.py
.venv/bin/python src/yolo_track.py
.venv/bin/python src/pid_shooter2.py
# review GT: http://127.0.0.1:8124/  (event verdicts + shooter A/B/?)
```

## Visuals
`out/e2e_frame_81.png`, `out/e2e_frame_343.png` — persons (green) in shot
windows; `out/proj_audit_vod30.png` — calibrated projection overlay.

## Known gaps (open issues)
- formal vod30 calibration bar (manual 6-click anchors; HOM-1)
- event P/R + shooter accuracy vs human GT (EVT-1 / PID-5)
- OSNet x0.25 embeddings to replace colour prototypes (PID-4 upgrade)
- ball-ID cert (BALL-1, backlog)
