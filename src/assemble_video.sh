#!/usr/bin/env bash
# Assemble panel PNGs into a demo video with ffmpeg.
set -euo pipefail
RUN="${1:-out/run1}"
FPS="${2:-2}"
OUT="${3:-out/recreation_demo.mp4}"

# rename panels by zero-padded index ordered by timestamp
idx=0
for p in $(ls "$RUN"/panel_*.png | sort -t_ -k2); do
  printf -v n "%04d" "$idx"
  cp "$p" "$RUN/.seq_$n.png"
  idx=$((idx+1))
done

nix shell nixpkgs#ffmpeg-headless -c ffmpeg -y -framerate "$FPS" -i "$RUN/.seq_%04d.png" \
  -c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart "$OUT"

rm -f "$RUN"/.seq_*.png
echo "wrote $OUT ($idx frames)"
