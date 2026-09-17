"""Opt-in real VOD/HTTP HLS verification; no downloads or production state writes.
Run: .venv/bin/python -B tests/live_processing_e2e.py --ffmpeg /path/to/ffmpeg
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--outputs', type=int, default=4)
    args = parser.parse_args()
    assert args.outputs >= 2
    with tempfile.TemporaryDirectory(prefix='.live-e2e-', dir=ROOT) as directory:
        root = Path(directory)
        for key in ('TMPDIR', 'YOLO_CONFIG_DIR', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'MPLCONFIGDIR', 'TORCH_HOME'):
            os.environ[key] = str(root / key.lower())
            Path(os.environ[key]).mkdir()
        tempfile.tempdir = str(root)
        import cv2
        import numpy as np
        from annotator.live_processing import LiveProcessor

        def emit(name, **values):
            print(json.dumps({'case': name, **values}, sort_keys=True), flush=True)

        def observe(processor, name, terminal=None, minimum=0, timeout=45):
            deadline = time.monotonic() + timeout
            sequences = []
            while time.monotonic() < deadline:
                status = processor.status()
                pair = processor.latest_jpeg()
                if pair is not None:
                    jpeg, meta = pair
                    if meta['seq'] not in sequences:
                        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        assert image is not None and image.shape[:2] == (meta['height'], meta['width'])
                        source_width, source_height = meta['source_width'], meta['source_height']
                        assert (source_width, source_height) == ((1280, 720) if name == 'real-vod' else (640, 360))
                        scale = min(1.0, 960 / source_width, 540 / source_height)
                        assert (meta['width'], meta['height']) == (round(source_width * scale), round(source_height * scale))
                        detections = meta['detections']
                        assert status['detectors'] == ['table', 'person']
                        assert isinstance(detections['boxes'], list)
                        assert all(box['label'] == 'person' for box in detections['boxes'])
                        assert meta['receive_to_result_ms'] >= meta['inference_ms'] >= 0
                        assert meta['upstream_delay_ms'] is None
                        assert not sequences or meta['seq'] > sequences[-1]
                        sequences.append(meta['seq'])
                        emit(name + ':output', sequence=meta['seq'], jpeg_bytes=len(jpeg),
                             dimensions=[meta['width'], meta['height']],
                             source_dimensions=[source_width, source_height], persons=len(detections['boxes']),
                             table=detections['table_polygon'] is not None,
                             received=status['frames_received'], processed=status['frames_processed'],
                             skipped=status['frames_skipped'], frame_age_ms=status['frame_age_ms'],
                             inference_ms=meta['inference_ms'],
                             receive_to_result_ms=meta['receive_to_result_ms'])
                if terminal and status['state'] in ('eos', 'error', 'stopped'):
                    assert status['state'] == terminal, status
                    assert len(sequences) >= minimum, sequences
                    emit(name + ':terminal', status=status, observed_sequences=sequences)
                    return
                if not terminal and len(sequences) >= minimum:
                    emit(name + ':sample', status=status, observed_sequences=sequences)
                    return
                if not terminal and status['state'] in ('error', 'eos'):
                    raise AssertionError(status)
                time.sleep(.02)
            raise AssertionError({'timeout': name, 'status': processor.status(), 'sequences': sequences})

        def stop(processor, name):
            before = time.monotonic()
            status = processor.stop()
            elapsed = time.monotonic() - before
            emit(name + ':stop', elapsed_seconds=elapsed, status=status)
            assert elapsed < 3.5 and status['state'] == 'stopped', status

        # Production ROOT is read only: dataset mode never touches Operations state.
        processor = LiveProcessor(ROOT)
        try:
            processor.start({'kind': 'dataset', 'dataset': 'vod30'}, ['table', 'person'])
            observe(processor, 'real-vod', minimum=args.outputs)
        finally:
            stop(processor, 'real-vod')

        (root / 'data').mkdir()
        (root / 'yolov8n.pt').symlink_to(ROOT / 'yolov8n.pt')
        fixture = root / 'data/vod_30min_260815.mp4'
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                        '-i', str(ROOT / 'data/vod_30min_260815.mp4'), '-t', '12', '-an',
                        '-vf', 'scale=640:-2', '-r', '15', '-c:v', 'libx264', '-preset', 'ultrafast',
                        '-g', '30', '-pix_fmt', 'yuv420p', str(fixture)], check=True, timeout=60)
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(fixture),
                        '-c', 'copy', '-f', 'hls', '-hls_time', '2', '-hls_list_size', '0',
                        '-hls_playlist_type', 'vod', str(root / 'fixture.m3u8')], check=True, timeout=30)
        state = root / 'out/corner-pocket/state.json'
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({'sources': [{'id': 'fixture-examplechannel', 'kind': 'channel',
                                                'channel': 'examplechannel',
                                                'url': 'https://www.twitch.tv/examplechannel'}]}))
        saved_state = state.read_bytes()
        processor = LiveProcessor(root)
        try:
            processor.start({'kind': 'dataset', 'dataset': 'vod30'}, ['table', 'person'])
            observe(processor, 'short-vod-eof', terminal='eos', minimum=args.outputs)
        finally:
            stop(processor, 'short-vod-eof')

        requests = []

        class Handler(SimpleHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                # Finite HLS is otherwise decoded as fast as possible. Pace segment delivery,
                # not capture/inference; this is a local transport fixture, not actual Twitch.
                if self.path.endswith('.ts'):
                    time.sleep(1)
                super().do_GET()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, name='live-e2e-http', daemon=True)
        thread.start()
        resolved = []
        base = 'http://127.0.0.1:' + str(server.server_port)

        def resolver(canonical):
            assert canonical == 'https://www.twitch.tv/examplechannel'
            resolved.append(canonical)
            return base + '/fixture.m3u8'

        try:
            processor = LiveProcessor(root, resolver=resolver)
            try:
                processor.start({'kind': 'twitch', 'source_id': 'fixture-examplechannel'}, ['table', 'person'])
                observe(processor, 'local-http-hls-not-twitch', terminal='error', minimum=args.outputs)
                assert processor.status()['error'] == 'Live stream ended or read timed out; restart to reconnect'
                assert resolved == ['https://www.twitch.tv/examplechannel']
                assert '/fixture.m3u8' in requests and any(path.endswith('.ts') for path in requests)
                emit('http-evidence', canonical_resolver_calls=resolved, requests=requests,
                     actual_twitch=False)
            finally:
                stop(processor, 'local-http-hls-not-twitch')
            processor = LiveProcessor(root, resolver=resolver)
            try:
                processor.start({'kind': 'twitch', 'source_id': 'fixture-examplechannel'}, ['table', 'person'])
                observe(processor, 'active-http-hls-stop', minimum=args.outputs)
            finally:
                stop(processor, 'active-http-hls-stop')
            processor = LiveProcessor(root, resolver=lambda canonical: base + '/missing.m3u8')
            try:
                processor.start({'kind': 'twitch', 'source_id': 'fixture-examplechannel'}, ['table', 'person'])
                observe(processor, 'http-404', terminal='error')
                assert processor.status()['frames_received'] == 0
                assert processor.latest_jpeg() is None
                assert processor.status()['error'] == 'Could not open the selected media source'
            finally:
                stop(processor, 'http-404')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            assert not thread.is_alive()
        assert state.read_bytes() == saved_state
        emit('success', fixture_seconds=12, http_server_stopped=True, operations_fixture_unchanged=True)


if __name__ == '__main__':
    main()
