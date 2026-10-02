"""Isolated operations browser fixture; no production annotation writes.

Run with PYTHONPATH=. .venv/bin/python tests/serve_operations_fixture.py.
Operations state is temporary and removed on exit. Review tools are intentionally
not populated here; use serve_workbench_fixture.py for media/review integration.
--public-port adds the read-only public board on its own listener, in this process,
exactly as annotator/unified_server.py serves it (docs/public-board.md), so a load
test drives both surfaces of one fixture without touching the console's routes.
"""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from annotator.unified_server import (Backend, PublicBoardServer, board_prefix, make_handler,
                                      make_public_handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8132)
    parser.add_argument('--public-port', type=int,
                        help='also serve the read-only public board on this loopback port (docs/public-board.md)')
    parser.add_argument('--public-prefix', type=board_prefix, default='', metavar='PATH',
                        help='mount the public board under this path, e.g. /board (default: the root)')
    args = parser.parse_args()
    with TemporaryDirectory(prefix='corner-pocket-browser-') as folder:
        root = Path(folder)
        (root / 'annotator').symlink_to(ROOT / 'annotator', target_is_directory=True)
        backend = Backend(root)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(backend))
        public = None
        if args.public_port:
            public = PublicBoardServer(('127.0.0.1', args.public_port),
                                       make_public_handler(backend, args.public_prefix))
            threading.Thread(target=public.serve_forever, name='public-board', daemon=True).start()
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
