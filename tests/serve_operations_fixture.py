"""Isolated operations browser fixture; no production annotation writes.

Run with PYTHONPATH=. .venv/bin/python tests/serve_operations_fixture.py.
Operations state is temporary and removed on exit. Review tools are intentionally
not populated here; use serve_workbench_fixture.py for media/review integration.
"""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from annotator.unified_server import Backend, make_handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8132)
    args = parser.parse_args()
    with TemporaryDirectory(prefix='corner-pocket-browser-') as folder:
        root = Path(folder)
        (root / 'annotator').symlink_to(ROOT / 'annotator', target_is_directory=True)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(Backend(root)))
        print(f'Isolated operations fixture: http://127.0.0.1:{args.port}/ops.html', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
