#!/usr/bin/env bash
# Run the console e2e suite. Playwright's chromium needs the nix store libraries,
# so this script builds LD_LIBRARY_PATH first, then runs the runner.
set -euo pipefail
cd "$(dirname "$0")/.."

BIN=$(ls -d "$HOME"/.cache/ms-playwright/chromium_headless_shell-* 2>/dev/null | sort -V | tail -1)
BIN="$BIN/chrome-headless-shell-linux64/chrome-headless-shell"
if [ ! -x "$BIN" ]; then
  echo "no playwright chromium at $BIN; run: npx playwright install chromium" >&2
  exit 1
fi

LIBPATH=$(python3 - "$BIN" <<'PY'
import glob, os, subprocess, sys
bin_path = sys.argv[1]

def is64(path):
    with open(path, 'rb') as f:
        head = f.read(5)
    return head[:4] == b'\x7fELF' and head[4] == 2

def find64(lib):
    for hit in sorted(glob.glob(f"/nix/store/*/lib/{lib}")):
        if is64(hit):
            return os.path.dirname(hit)
    return None

paths = []
env = dict(os.environ)
for _ in range(15):
    env['LD_LIBRARY_PATH'] = ':'.join(paths)
    out = subprocess.run(['ldd', bin_path], capture_output=True, text=True, env=env).stdout
    missing = sorted({ln.split()[0] for ln in out.splitlines() if 'not found' in ln})
    added = []
    for lib in missing:
        found = find64(lib)
        if found and found not in paths:
            paths.append(found)
            added.append(found)
    if not missing or not added:
        break
print(':'.join(paths))
PY
)

echo "run with $(echo "$LIBPATH" | tr ':' '\n' | wc -l) library paths from the nix store"
LD_LIBRARY_PATH="$LIBPATH" npx e2e run "$@"
