"""Isolated operations browser fixture; no production annotation writes.

Run with PYTHONPATH=. .venv/bin/python tests/serve_operations_fixture.py.
Operations state is temporary and removed on exit. Review tools are intentionally
not populated here; use serve_workbench_fixture.py for media/review integration.
--public-port adds the read-only public board on its own listener, in this process,
exactly as annotator/unified_server.py serves it (docs/public-board.md), so a load
test drives both surfaces of one fixture without touching the console's routes.
--state seeds the operations document from a JSON file written in the server's own
schema (tests/console_fixture_state.json; docs/console-shots.md), so a screenshot or
a UI check starts from a realistic club instead of an empty one.

seed_state, FixtureServer and attach_public_board are the parts the review fixture
(tests/serve_workbench_fixture.py) shares: one process, one root, both surfaces, and
one place that knows where the store reads its document from.
"""
import argparse
import faulthandler
import json
from http.server import ThreadingHTTPServer
import signal
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from annotator.unified_server import (Backend, PublicBoardServer, board_prefix, make_handler,
                                      make_public_handler)


class FixtureServer(ThreadingHTTPServer):
    """The console listener with production's accept backlog (BoundedHTTPServer: no ceiling here).

    A bare ThreadingHTTPServer keeps the stdlib's listen(5). A browser opens six connections per
    host, so a page with ten webfonts overflows that queue: measured against this fixture, the
    slowest request of a 24-way burst took 2.06 s while every smaller burst stayed at 0.01 s, and
    in a screenshot run the stalled request is the one holding up the render. Production serves
    console traffic through BoundedHTTPServer, whose request_queue_size is 64; the fixture matches
    it so a browser sees the same listener it would see in the hall.
    """
    daemon_threads = True
    request_queue_size = 64


def seed_state(root, source):
    """Write a console fixture document where the store reads it, and say what was seeded.

    The JsonStore reads <root>/out/corner-pocket/state.json (src/store.py, JsonStore ->
    annotator/operations.py Operations.path). Written before the store is opened so the
    first GET already answers with the seeded club. Not validated here: Operations._load
    reads it, and a malformed document fails loudly on the first request.
    """
    document = json.loads(Path(source).read_text())
    destination = root / 'out' / 'corner-pocket' / 'state.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2, allow_nan=False) + '\n')
    print(f'Seeded operations state: {Path(source).resolve()} ({len(document.get("players", []))} players, '
          f'revision {document.get("revision")})', flush=True)
    return document


def attach_public_board(backend, port, prefix=''):
    """The read-only public board on its own listener, in this process (docs/public-board.md)."""
    server = PublicBoardServer(('127.0.0.1', port), make_public_handler(backend, prefix))
    threading.Thread(target=server.serve_forever, name='public-board', daemon=True).start()
    return server


def main():
    # kill -USR1 <pid> dumps every thread's stack: a fixture that stops answering under a burst
    # of long-lived /api/clock/stream connections is otherwise a black box.
    faulthandler.register(signal.SIGUSR1, all_threads=True, chain=False)
    parser = argparse.ArgumentParser(description=__doc__)
    # Not 8132: that is the public board's port in production
    # (deploy/systemd/pool-workbench.service.d/40-public-board.conf). A fixture left
    # running on it would stop the service from restarting (port already in use).
    parser.add_argument('--port', type=int, default=8150)
    parser.add_argument('--public-port', type=int,
                        help='also serve the read-only public board on this loopback port (docs/public-board.md)')
    parser.add_argument('--public-prefix', type=board_prefix, default='', metavar='PATH',
                        help='mount the public board under this path, e.g. /board (default: the root)')
    parser.add_argument('--state', metavar='FILE',
                        help='seed the operations document from this JSON file before serving')
    args = parser.parse_args()
    with TemporaryDirectory(prefix='corner-pocket-browser-') as folder:
        root = Path(folder)
        (root / 'annotator').symlink_to(ROOT / 'annotator', target_is_directory=True)
        if args.state:
            seed_state(root, args.state)
        backend = Backend(root)
        server = FixtureServer(('127.0.0.1', args.port), make_handler(backend))
        public = attach_public_board(backend, args.public_port, args.public_prefix) if args.public_port else None
        print(f'Isolated operations fixture: http://127.0.0.1:{args.port}/ops.html', flush=True)
        if public:
            print(f'Public board: http://127.0.0.1:{args.public_port}{args.public_prefix}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if public:
                public.shutdown()
                public.server_close()
            server.server_close()


if __name__ == '__main__':
    main()
