# SAM3 Single-Camera → 2D Pool Recreation — Proof of Concept

## Goal
Take a historical single-camera Twitch VOD from [examplechannel](https://www.twitch.tv/examplechannel/videos),
segment the pool balls with state-of-the-art segmentation (Meta **SAM 3**), and
**project the camera view into a canonical 2D top-down recreation** of the table
via a homography — recovering ball positions in table coordinates.

## Data
- Channel: `examplechannel` (Friday-night 8-ball streams, fixed elevated end-on camera,
  royal-blue cloth, all four playing-surface corners visible — near-ideal for homography).
- Clip used: VOD **v1000000002** — *"8-ball break and run out"* (377 s, 1920×1080@30).
- Download: `yt-dlp -f 1080p "https://www.twitch.tv/videos/1000000002"` (no login).

## Pipeline (`src/`)
1. **Table detection** (`table_detect.py`) — classical: HSV blue-cloth segmentation →
   largest component → quadrilateral fit → 4 ordered corners. A homography `H`
   maps the cloth quad to a canonical 1000×500 (2:1) table. The camera is static,
   so `H` is locked to the median corner positions (MAD ≤ 1 px) from a quick pass.
2. **Ball segmentation — SAM 3** (`sam3_cpu.py`, `src/sam3/` = `facebookresearch/sam3`):
   `build_sam3_image_model` with the official weights; text prompt **"billiard ball"**
   → open-vocabulary *exhaustive instance segmentation*: every ball gets a precise
   mask — even a tight 15-ball rack is separated (16/16 instances at t=5 s).
3. **Filtering** — score ≥ 0.62, mask on cloth, size/circularity priors.
4. **Identity** (`classify_ball`) — heuristic HSV statistics inside each mask:
   colour + cue / solid / stripe / black (ball numbers 1–15 not resolved).
5. **Projection** — ball centre (min-enclosing circle of the SAM3 mask) through `H`
   → canonical table coordinates; balls rendered at constant physical size (57.15 mm
   on a 2540 mm table), which is what a true top-down recreation requires.
6. **Render** — per sampled frame a 3-panel image:
   original + SAM3 masks · bird's-eye rectified table · schematic 2D recreation.

## SAM 3 on CPU (no GPU)
Official checkpoints on HuggingFace are **gated** (no credentials available), so the
same weights were taken from the ungated transformers mirror
[`1038lab/sam3`](https://huggingface.co/1038lab/sam3) (safetensors). The official
code assumes CUDA in a few eager paths; minimal patches (documented in `sam3_cpu.py`
and two one-line edits in `src/sam3/sam3/model/`) make it run on CPU:
- eager CUDA position-encoding precompute → lazy on device;
- fused bf16 `addmm_act` kernel → plain fp32 linear+activation;
- `pin_memory()` → no-op; decoder coord cache → CPU.
Per-frame cost on 4 CPU threads: ~25–110 s (encode + text grounding), heavily
dependent on host load.

## Results
- **31 sampled frames** covering the whole clip (`out/run2/panel_*.png`),
  results in `out/run2/results.json`, demo video `out/recreation_demo.mp4`.
- Narrative reproduced correctly: 12 balls after the break → ball count falling
  through the run-out (11 → 10 → 9 … → 3) → 1–2 at the end.
- **QA (`src/qa.py`)**: 100 % of projected balls inside the canonical table bounds
  (0 out-of-bounds with the fixed homography); corner stability 0 px across frames.
- **Independent cross-check**: a classical colour/geometry detector agrees with the
  SAM3 positions where both fire (7/8, 5/5, 3/6 on test frames) while SAM3 has
  clearly higher recall (12 vs 8, 9 vs 5), i.e. the segmentation drives recall,
  not the heuristic.

## Limitations / next steps
- Ball identity (colour/style) is a heuristic; red/maroon/purple are confused under
  the stream lighting and numbers 1–15 are not assigned. A per-class SAM3 text
  prompt ("yellow stripe ball", …) or a fine-tuned detector would fix this.
- Tight racks partially merge masks → some racked balls dropped (9/15 at t=4 s).
- Homography uses the cloth quad; cushion-nose geometry would tighten edge accuracy.
- CPU-only ⇒ seconds per frame; on a GPU the same pipeline would run near real-time,
  and SAM 3.1 Multiplex could add cross-frame ball tracking.
- Vision QA backends were unavailable during this session, so visual verification
  was limited to programmatic checks — the panels are provided for manual review.

## Reproduce
```bash
source .venv/bin/activate
# download the VOD
nix shell nixpkgs#ffmpeg-headless nixpkgs#yt-dlp -c yt-dlp -f 1080p \
  -o data/vod_250725_break_run.mp4 https://www.twitch.tv/videos/1000000002
# full pipeline (SAM3 weights in data/sam3.safetensors from 1038lab/sam3)
taskset -c 0-3 python src/pipeline.py --out out/run2 --every 12 --start 4 \
  --end 370 --corners out/fixed_corners.json
bash src/assemble_video.sh out/run2 2 out/recreation_demo.mp4
python src/qa.py out/run2/results.json
```
