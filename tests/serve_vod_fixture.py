"""Scratch workbench for the VOD selector; production files are never written.

A copy of tests/serve_workbench_fixture.py with its own root and port:

    PYTHONPATH=. .venv/bin/python tests/serve_vod_fixture.py [--port 8217] [--fresh]
    PYTHONPATH=. .venv/bin/python tests/serve_vod_fixture.py --fresh --golden out/vod-selector/golden/before

The scratch root is ``out/vod-fixture/`` under this checkout. Inputs are copied in
(reflinks where the filesystem shares blocks, so the recordings cost no space), never
symlinked, so every write the server makes - frame corrections, imported VODs under
``data/vods/`` and ``out/vods/``, the identity index - lands inside the scratch root.
``annotator/`` and ``src/`` are symlinks the server only reads.  No ``state.json`` is
copied: the operations document is the default one, whose one saved channel is
``examplechannel``, as in production.

``--golden DIR`` serves on the port in this process, sends a fixed handful of GETs
over HTTP, and writes each response (status, headers, body) plus the bytes of every
file under the scratch root afterwards to DIR, then exits.  Two runs are compared
with ``diff -r``; the only normalised field is the ``Date`` header.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from annotator.unified_server import Backend, BoundedHTTPServer, make_handler  # noqa: E402

SCRATCH = ROOT / 'out' / 'vod-fixture'
PRODUCTION_PORT = 8130
COPIED = ('scan30', 'scan_highlight', 'unlabeled_crops', 'unlabeled_crops2', 'vod30_event_crops',
          'pid2_tracklets.json', 'calib_vod30.json', 'events_actors.json', 'pid_anchors_vod30.json')
MEDIA = ('vod_30min_260815.mp4', 'vod_highlight.mp4')
GOLDEN = ('/api/datasets', '/api/vod30/events', '/api/highlight/events',
          '/api/frame?dataset=vod30&frame=0', '/media/vod30/frame?t=0',
          '/api/unified?dataset=vod30&frame=0', '/api/nope/events')


def copy(source, target):
    """cp -a --reflink=auto: shared blocks on btrfs, a plain copy elsewhere."""
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cp', '-a', '--reflink=auto', str(source), str(target)], check=True)


def build(root, fresh=False):
    root = Path(root)
    if not root.resolve().is_relative_to((ROOT / 'out').resolve()) or root.resolve() == (ROOT / 'out').resolve():
        raise SystemExit(f'the scratch root must be a folder under {ROOT / "out"}')
    if fresh and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    for name in ('annotator', 'src'):
        if not (root / name).is_symlink():
            (root / name).symlink_to(ROOT / name, target_is_directory=True)
    for name in COPIED:
        source, target = ROOT / 'out' / name, root / 'out' / name
        if source.exists() and not target.exists():
            copy(source, target)
    for name in MEDIA:
        if (ROOT / 'data' / name).is_file() and not (root / 'data' / name).exists():
            copy(ROOT / 'data' / name, root / 'data' / name)
    if (ROOT / 'yolov8n.pt').is_file() and not (root / 'yolov8n.pt').exists():
        copy(ROOT / 'yolov8n.pt', root / 'yolov8n.pt')
    if not (root / 'out' / 'pid_anchors_vod30.json').exists():
        (root / 'out' / 'pid_anchors_vod30.json').write_text(json.dumps({'anchors': {}}))
    if not (root / 'out' / 'pid_seed.json').exists():
        (root / 'out' / 'pid_seed.json').write_text(json.dumps({'seeds': {}}))
    return root


def files(root):
    """Every regular file under root (symlinked folders are inputs, not followed)."""
    listed = {}
    for path in sorted(Path(root).rglob('*')):
        if path.is_symlink() or not path.is_file() or any(p.is_symlink() for p in path.parents if p != Path(root)):
            continue
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1 << 20), b''):
                digest.update(block)
        listed[str(path.relative_to(root))] = [path.stat().st_size, digest.hexdigest()]
    return listed


def golden(base, root, target):
    assert base.startswith('http://127.0.0.1:') and not base.endswith(f':{PRODUCTION_PORT}'), base
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    before = files(root)
    report = []
    for index, path in enumerate(GOLDEN):
        try:
            response = urlopen(Request(base + path), timeout=600)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            headers = {k: ('(normalised)' if k == 'Date' else v) for k, v in response.headers.items()}
            status = response.status
        name = f'{index:02d}.body'
        (target / name).write_bytes(body)
        report.append({'get': path, 'status': status, 'headers': headers, 'bytes': len(body),
                       'sha256': hashlib.sha256(body).hexdigest(), 'body_file': name})
    after = files(root)
    written = {name: value for name, value in after.items() if before.get(name) != value}
    (target / 'responses.json').write_text(json.dumps(report, indent=1) + '\n')
    (target / 'files_written_by_the_gets.json').write_text(json.dumps(written, indent=1, sort_keys=True) + '\n')
    (target / 'files_after.json').write_text(json.dumps(after, indent=1, sort_keys=True) + '\n')
    return report, written


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--port', type=int, default=8217)
    parser.add_argument('--root', type=Path, default=SCRATCH)
    parser.add_argument('--fresh', action='store_true', help='rebuild the scratch root from nothing')
    parser.add_argument('--golden', type=Path, help='run the golden GETs, write them here, exit')
    args = parser.parse_args()
    if args.port < 8200 or args.port == PRODUCTION_PORT:
        raise SystemExit('the fixture serves on a port of 8200 or more, never the production port')
    root = build(args.root, fresh=args.fresh)
    backend = Backend(root)
    server = BoundedHTTPServer(('127.0.0.1', args.port), make_handler(backend))
    base = f'http://127.0.0.1:{args.port}'
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    print(f'VOD fixture: {base} (root {root})', flush=True)
    try:
        if args.golden is None:
            server.serve_forever()
        else:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            report, written = golden(base, root, args.golden)
            for row in report:
                print(row['status'], row['bytes'], row['sha256'][:16], row['get'], flush=True)
            print('files written by the GETs:', sorted(written) or 'none', flush=True)
            server.shutdown()
    except KeyboardInterrupt:
        pass
    finally:
        backend.close()
        server.server_close()


if __name__ == '__main__':
    main()
