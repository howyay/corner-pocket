# pool — single-camera pool video → calibrated 2D recreation + events + attribution

Track shots, pots and players from a fixed single-camera Twitch pool stream
(`examplechannel`, Rasson Victory III 9 ft), project everything into a calibrated
2D top-down recreation, and attribute each shot/pot to the player who made it.

| | |
|---|---|
| Forgejo | https://git.example.com/operator/pool |
| Kaneo | https://proj.example.com (project `pool`) |
| Worktree | `~/projects/pool` (NOT a git repo before this repo; data/ and out/ are gitignored) |

## Areas and priority (2026-09)

See `docs/roadmap.md` for the decomposition into issues/tasks, acceptance bars
and current measured state. Summary:

| Area | Status | Priority |
|---|---|---|
| Homography / calibration | PnP rectangle-constrained, 13.1 mm mean / 4.9 mm median holdout on 6 anchors (highlight) | P0 — verify per-segment across 30-min footage, cushion-nose alignment |
| Projection | portrait top-down, physical mm (1270×2540), ball diameter 57.15 mm | P0 — audit vs pocket geometry |
| Shot & pot detection | scan_events artifacts exist but **never human-validated** (all `verified:false`); causality 0 violations | P0 — GT review + P/R + fixes |
| Player identification & shot association | research done (`research/player-attribution-research.md`); **no implementation** | P1 — person/cue sensing → tracklets → geometry actor → OSNet x0.25 prototypes → association |
| Ball-ID ≥90 % (smallest model) | pipeline + labelers live; needs finished labels + diverse frames | Backlog |

## Layout

- `src/` — pipeline scripts (calibration, table detect, SAM3 CPU wrapper, scan/events,
  ball-ID training, crop collection, player-attribution to come)
- `annotator/` — tiny review/label servers (`server.py`; set-1 labels :8124, set-2 :8125)
- `research/` — literature reviews (player attribution)
- `docs/` — roadmap, state, handoff notes
- `data/`, `out/` — gitignored (videos live here; artifacts regenerable)

## Environment

- CPU python env: `.venv` (torch cpu + SAM3 patched for CPU)
- ROCm env: `.venv-rocm` (GPU experiments)
- Videos: `data/vod_30min_260815.mp4` (30-min slice, Aug-15 stream),
  `data/vod_highlight.mp4` (377 s game used for the label sets)
- SAM3 weights: `data/sam3.safetensors` (from `1038lab/sam3` HF mirror, ungated)
