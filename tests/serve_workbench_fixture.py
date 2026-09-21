"""Browser-only scratch workspace; production labels are never modified."""
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from annotator.unified_server import Backend, make_handler
from http.server import ThreadingHTTPServer

fixture = ROOT / 'out' / 'ui-browser-fixture'
fixture.mkdir(parents=True, exist_ok=True)
# Media stays read-only through symlinks; annotation JSON is copied separately.
for name in ('annotator', 'data', 'src'):
    link = fixture / name
    if not link.exists():
        link.symlink_to(ROOT / name, target_is_directory=True)
for folder in ('scan30', 'scan_highlight', 'unlabeled_crops', 'unlabeled_crops2', 'vod30_event_crops'):
    source = ROOT / 'out' / folder
    target = fixture / 'out' / folder
    target.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        dest = target / path.name
        if path.suffix == '.json':
            shutil.copy2(path, dest)
        elif path.is_dir():
            if dest.is_symlink():
                dest.unlink()
            shutil.copytree(path, dest, dirs_exist_ok=True)
        else:
            if dest.is_symlink():
                dest.unlink()
            shutil.copy2(path, dest)
for name in ('pid2_tracklets.json', 'calib_vod30.json', 'events_actors.json'):
    shutil.copy2(ROOT / 'out' / name, fixture / 'out' / name)
for name, value in [('pid_seed.json', {'seeds': {}}), ('pid_anchors_vod30.json', {'anchors': {}})]:
    (fixture / 'out' / name).write_text(json.dumps(value))
# Reuse production decoding read-only; correction writes stay in the fixture.
backend = Backend(fixture)
real = Backend(ROOT)
backend.video = real.video
backend.frame = real.frame
backend.frame_jpeg = real.frame_jpeg
# The live source allowlist resolves data/ through realpath, so the fixture's
# symlinked data/ fails it. Point the live processor at the real root: live
# decoding and detection only read media, they never write annotations.
from annotator.live_processing import LiveProcessor
backend._live = LiveProcessor(ROOT)
print('Isolated browser fixture: http://127.0.0.1:8131', flush=True)
ThreadingHTTPServer(('127.0.0.1', 8131), make_handler(backend)).serve_forever()
