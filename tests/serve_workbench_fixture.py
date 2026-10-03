"""Review fixture: the console, the mounted review workspace and, with --public-port, the board.

Run with PYTHONPATH=. .venv/bin/python tests/serve_workbench_fixture.py --port 8167
--public-port 8168 --public-prefix /board --state tests/console_fixture_state.json: one
command, one process, the console and review workspace on --port (default 8131) and the
public board on --public-port.
Browser-only scratch workspace; production labels are never modified: media is reached
through read-only symlinks and every annotation write lands in out/ui-browser-fixture.

--state seeds the operations document from a JSON file written in the server's own schema
(tests/console_fixture_state.json), exactly as tests/serve_operations_fixture.py does.
That is the difference between the two fixtures that matters to a reviewer: this one has
media and review tools, so with a state file one process is the whole rating fixture -
seeded club, console, review workspace and public board - instead of a console with no
media to review (docs/console-redesign.md SS14.9).
--public-port adds the read-only public board on its own listener, in this process,
exactly as annotator/unified_server.py serves it (docs/public-board.md).
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from annotator.unified_server import Backend, board_prefix, make_handler
# The shared fixture parts: the listener with production's accept backlog, the store-path
# seeding and the board listener. One place knows each of them.
from serve_operations_fixture import FixtureServer, attach_public_board, seed_state


def build_root(fixture):
    """The scratch root: read-only symlinks for media, copied JSON for the annotation state."""
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / 'out').mkdir(parents=True, exist_ok=True)
    # Media stays read-only through symlinks; annotation JSON is copied separately.
    for name in ('annotator', 'data', 'src'):
        link = fixture / name
        if not link.exists():
            link.symlink_to(ROOT / name, target_is_directory=True)
    for folder in ('scan30', 'scan_highlight', 'unlabeled_crops', 'unlabeled_crops2', 'vod30_event_crops'):
        source = ROOT / 'out' / folder
        target = fixture / 'out' / folder
        if not source.is_dir():
            # A worktree starts without the scan outputs (they are gitignored): the media
            # under data/ is what the review workspace needs to decode a frame, and the
            # annotations only add tracks on top of it. Say so instead of failing.
            print(f'No {source.relative_to(ROOT)} in this checkout: served without those annotations', flush=True)
            continue
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
        if (ROOT / 'out' / name).is_file():
            shutil.copy2(ROOT / 'out' / name, fixture / 'out' / name)
    # The hand anchors are a read-only input copied from the real workspace (like the
    # files above), so the fixture exercises the seeded app path - refine, then accept
    # with a drift or refuse with a reason. Zeroing them here would leave the fixture
    # able to reach only the no-seed path, which tests/test_app_path_prior.py covers.
    # If the real file is missing the fixture keeps its old empty-anchors fallback
    # rather than failing; nothing under ROOT/out/ is ever written.
    anchors = ROOT / 'out' / 'pid_anchors_vod30.json'
    if anchors.is_file():
        shutil.copy2(anchors, fixture / 'out' / 'pid_anchors_vod30.json')
    else:
        (fixture / 'out' / 'pid_anchors_vod30.json').write_text(json.dumps({'anchors': {}}))
    (fixture / 'out' / 'pid_seed.json').write_text(json.dumps({'seeds': {}}))
    return fixture


def build_backend(fixture):
    """The fixture backend: production decoding read-only, correction writes in the fixture."""
    backend = Backend(fixture)
    real = Backend(ROOT)
    backend.video = real.video
    backend.frame = real.frame
    backend.frame_jpeg = real.frame_jpeg
    # The live source allowlist resolves data/ through realpath, so the fixture's
    # symlinked data/ fails it. Point the live processor at the real root: live
    # decoding and detection only read media, they never write annotations.
    from annotator.live_processing import LiveProcessor
    from annotator.unified_server import VodReplaySourceMixin
    # Saved Twitch channels are the one exception: the UI saves them into the
    # fixture's own state, so they are looked up there by a processor rooted at the
    # fixture that is never started. Datasets and stages still resolve under ROOT.
    saved_sources = LiveProcessor(fixture)

    class FixtureSources(LiveProcessor):
        def _source_media(self, source):
            if isinstance(source, dict) and source.get('kind') == 'twitch':
                return saved_sources._source_media(source)
            return super()._source_media(source)

    # The server's processor (the vod-replay mixin over LiveProcessor, as built by
    # vod_replay_processor_class) with that one lookup; pointing it at the real root
    # keeps live media resolution working while every annotation write stays in the
    # fixture.
    class FixtureLive(VodReplaySourceMixin, FixtureSources):
        pass

    backend._live = FixtureLive(ROOT)
    return backend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8131,
                        help='the console listener (default: 8131, the port docs/handoff.md documents)')
    parser.add_argument('--public-port', type=int,
                        help='also serve the read-only public board on this loopback port (docs/public-board.md)')
    parser.add_argument('--public-prefix', type=board_prefix, default='', metavar='PATH',
                        help='mount the public board under this path, e.g. /board (default: the root)')
    parser.add_argument('--state', metavar='FILE',
                        help='seed the operations document from this JSON file before serving')
    args = parser.parse_args()
    fixture = build_root(ROOT / 'out' / 'ui-browser-fixture')
    # Seeded before the backend opens the store, so the first GET already answers with
    # the club instead of an empty document.
    if args.state:
        seed_state(fixture, args.state)
    backend = build_backend(fixture)
    server = FixtureServer(('127.0.0.1', args.port), make_handler(backend))
    public = attach_public_board(backend, args.public_port, args.public_prefix) if args.public_port else None
    print(f'Isolated review fixture: http://127.0.0.1:{args.port}/', flush=True)
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
