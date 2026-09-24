"""Drive the live pipeline from a Twitch VOD replayed as if it were real time.

Two modes, both honest about what they are:

* **vod** (default): resolve the saved channel's most recent VOD (or ``--vod <id|url>``/
  ``--channel <login>``), then feed ``LiveProcessor`` frames from a ``VodRealtimeCapture``
  — 1x wall-clock pacing, dropping rather than drifting.  The pipeline is untouched: the
  source is injected through the ``resolver``/``capture_factory`` seam it already has.
* **file**: the same 1x pacing over a VOD already on disk.  Used when the Twitch fetch is
  unavailable, so the "VOD as live" *semantics* can still be measured; only the fetch is
  missing in that case, and the output says so (``network: file``).

``--probe`` skips the pipeline and prints the raw, redacted reachability evidence only.

Run: PYTHONPATH=. .venv/bin/python -B tests/twitch_vod_realtime_run.py --probe
     PYTHONPATH=. .venv/bin/python -B tests/twitch_vod_realtime_run.py --seconds 200
     PYTHONPATH=. .venv/bin/python -B tests/twitch_vod_realtime_run.py --file data/vod_30min_260815.mp4 --seconds 200
No production state is written: the vod mode reads the saved channel from state.json, and
the file mode gets its own TempDir root.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from annotator import twitch_vod_source as vod  # noqa: E402

SAVED_CHANNEL_ID = '77777777777777777777777777777777'   # out/corner-pocket/state.json
SAVED_CHANNEL_LOGIN = 'examplechannel'


class BallStandIn:
    """The ball detector that does not exist yet: N ms of work when it runs."""

    name = 'ball'
    budget_ms = None

    def __init__(self, ms=15.0, every_n_frames=1):
        self.ms = ms
        self.every_n_frames = every_n_frames

    def process(self, frame, context):
        time.sleep(self.ms / 1000.0)
        return {'boxes': []}


def stages_for(spec, root):
    from annotator.pipeline_stages import PersonStage, TableStage
    stages = []
    for item in spec.split(','):
        name, _, cadence = item.partition('@')
        if name == 'table':
            stages.append(TableStage(root, dataset='vod30'))
        elif name == 'person':
            stages.append(PersonStage(root))
        elif name == 'ball':
            stages.append(BallStandIn(every_n_frames=int(cadence) if cadence else 1))
        else:
            raise SystemExit('unknown stage: ' + item)
    return stages


def probe(channel, vod_id=None):
    """The raw reachability evidence, redacted: statuses and shapes, never tokens."""
    steps = []
    try:
        vods = vod.channel_recent_vods(channel, 3) if channel else []
        steps.append({'step': 'channel_videos', 'channel': channel, 'status': 200, 'vods': vods})
    except vod.TwitchVodError as error:
        steps.append({'step': 'channel_videos', 'channel': channel, 'error': str(error)})
        vods = []
    target = vod_id or (vods[0]['id'] if vods else None)
    if target is None:
        return {'probe': steps, 'vod_id': None, 'note': 'no VOD id to probe'}
    token = vod.vod_token(target, strict=False)
    steps.append({'step': 'vod_playback_token', **vod.evidence(token)})
    try:
        resolved = vod.resolve_vod(target)
        steps.append({'step': 'usher_and_media_playlist', **vod.evidence(resolved)})
    except vod.TwitchVodError as error:
        steps.append({'step': 'usher_and_media_playlist', 'vod_id': target, 'error': str(error)})
        resolved = None
    return {'probe': steps, 'vod_id': target, 'resolved': resolved is not None}


def run(args):
    from annotator.live_processing import LiveProcessor

    identity = None
    temp_root = None
    if args.file:
        media = str(Path(args.file).resolve())
        temp_root = tempfile.TemporaryDirectory(prefix='.vod-as-live-', dir=ROOT)
        root = Path(temp_root.name)
        (root / 'out/corner-pocket').mkdir(parents=True)
        (root / 'out/corner-pocket/state.json').write_text(json.dumps({'sources': [
            dict(id=SAVED_CHANNEL_ID, kind='channel', channel=SAVED_CHANNEL_LOGIN,
                 url='https://www.twitch.tv/' + SAVED_CHANNEL_LOGIN)]}))
        os.symlink(ROOT / 'yolov8n.pt', root / 'yolov8n.pt')
        # Same reference the live VOD path resolves, so only the fetch differs.
        if (ROOT / 'out/calib_vod30_segments.json').is_file():
            os.symlink(ROOT / 'out/calib_vod30_segments.json',
                       root / 'out/calib_vod30_segments.json')
        source_label, network = 'file-as-live', 'file'
        def resolver(canonical_url):
            return media
    else:
        root = ROOT
        vod_id = args.vod or None
        if vod_id is None:
            recent = vod.channel_recent_vods(args.channel or SAVED_CHANNEL_LOGIN, 1)
            if not recent:
                raise SystemExit('channel has no archived broadcast to replay')
            vod_id = recent[0]['id']
        identity = vod.vod_info(vod_id, strict=False)
        resolved = vod.resolve_vod(vod_id, max_height=args.max_height)
        media = resolved['media_url']
        identity.update({'variant': resolved['variant'], 'playlist': resolved['playlist'],
                         'media_url_host': vod.evidence(resolved)['media_url_host']})
        source_label, network = 'twitch-vod-as-live', 'hls'
        def resolver(canonical_url):
            return media

    holder = {}
    def capture_factory(capture_media):
        capture = vod.VodRealtimeCapture(capture_media, vod_id=identity and identity['vod_id'],
                                         rate=args.rate, start_s=args.start, network=network,
                                         max_catchup_s=args.max_catchup)
        holder['capture'] = capture
        return capture

    def one_run(seconds, label):
        """One processor + one paced capture, run for ``seconds`` of wall clock."""
        processor = LiveProcessor(root, stages=stages_for(args.stages, root),
                                  resolver=resolver, capture_factory=capture_factory)
        started = time.monotonic()
        processor.start(dict(kind='twitch', source_id=SAVED_CHANNEL_ID))
        # Wait for the first frame before starting the window: opening an HLS VOD (and
        # seeking into it) is a one-off, not part of the steady-state rate.
        deadline = started + args.open_timeout
        while processor.status()['frames_received'] < 1 and time.monotonic() < deadline:
            time.sleep(.05)
        opened_after_s = time.monotonic() - started
        window_start = time.monotonic()
        samples = []
        while time.monotonic() - window_start < seconds:
            time.sleep(args.sample_every)
            snapshot = processor.status()
            capture = holder.get('capture')
            samples.append({'t': round(time.monotonic() - window_start, 2),
                            'received': snapshot['frames_received'],
                            'processed': snapshot['frames_processed'],
                            'dropped': sum(snapshot['drop_reasons'].values()),
                            'state': capture.state() if capture else None})
        status = processor.stop()
        hard = time.monotonic() + 300.0
        while time.monotonic() < hard:
            status = processor.status()
            if not status['decoder_alive'] and not status['worker_alive']:
                break
            time.sleep(.05)
        capture = holder.get('capture')
        return {'status': status, 'wall_s': time.monotonic() - window_start,
                'opened_after_s': opened_after_s, 'label': label,
                'pacing': capture.state() if capture else {}, 'samples': samples}

    if args.warmup_seconds > 0:
        # The person model loads once per process (module-level cache in
        # src/frame_inference). Loading it inside the measured window would measure the
        # model's cold start - and its GIL-heavy load starves the decoder thread, which
        # shows up as a pacing failure that has nothing to do with pacing.
        warm = one_run(args.warmup_seconds, 'warmup')
        warmup = {'seconds': args.warmup_seconds, 'frames_processed': warm['status']['frames_processed'],
                  'person_first_call_ms': max((entry['max_ms'] or 0 for entry in warm['status']['stages']),
                                              default=None)}
    else:
        warmup = None
    measured = one_run(args.seconds, 'measured')
    status, wall_s, pacing, samples = (measured['status'], measured['wall_s'],
                                       measured['pacing'], measured['samples'])
    latency = status['latency_ms']
    partitioned = status['frames_processed'] + sum(status['drop_reasons'].values())
    if temp_root is not None:
        temp_root.cleanup()
    return {
        'source': source_label, 'network': network, 'vod_id': (identity or {}).get('vod_id'),
        'vod': {key: value for key, value in (identity or {}).items()
                if key in ('title', 'channel', 'length_s', 'created_at', 'variant', 'playlist',
                           'media_url_host', 'status', 'errors')},
        'pipeline': {'state': status['state'], 'error': status['error'],
                     'detectors': status['detectors'], 'source_fps': status['source_fps'],
                     'frame_budget_ms': status['frame_budget_ms'],
                     'budget_enforcement': status['budget_enforcement']},
        'host': {'loadavg': [round(value, 2) for value in os.getloadavg()], 'cores': os.cpu_count()},
        'warmup': warmup, 'opened_after_s': round(measured['opened_after_s'], 2),
        'window_s': round(wall_s, 2),
        'frames_received': status['frames_received'], 'frames_processed': status['frames_processed'],
        'received_fps': round(status['frames_received'] / wall_s, 2),
        'processed_fps': round(status['frames_processed'] / wall_s, 2),
        'drops': status['drop_reasons'], 'last_drop': status['last_drop'],
        'invariant_holds': partitioned == status['frames_received'],
        'pacing': {'wall_s': round(wall_s, 2), 'start_s': pacing.get('start_s'),
                   'video_s': pacing.get('video_s'),
                   'video_consumed_s': (round((pacing.get('video_s') or 0) - (pacing.get('start_s') or 0), 2)
                                        if pacing.get('video_s') is not None else None),
                   # Consumed video per wall second: the start offset is not consumption.
                   'video_per_wall': (round(((pacing.get('video_s') or 0) - (pacing.get('start_s') or 0)) / wall_s, 4)
                                      if wall_s else None),
                   'drift_s': pacing.get('drift_s'), 'rate': pacing.get('rate'),
                   'kind': pacing.get('kind'), 'live': pacing.get('live'),
                   'frames_served': pacing.get('frames_served'),
                   'frames_dropped_by_pacer': pacing.get('frames_dropped'),
                   'read_failures': pacing.get('read_failures'),
                   'max_abs_drift_s': max((abs(s['state']['drift_s']) for s in samples if s['state']), default=None),
                   'samples': len(samples)},
        'stages': [{'name': entry['name'], 'every_n_frames': entry['every_n_frames'],
                    'runs': entry['runs'], 'skips': entry['skips'],
                    'count': entry['count'], 'p50_ms': entry['p50_ms'], 'p95_ms': entry['p95_ms'],
                    'max_ms': entry['max_ms'], 'evidence': entry['evidence']}
                   for entry in status['stages']],
        'latency_ms': {name: latency[name] for name in latency},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--probe', action='store_true', help='print redacted reachability evidence only')
    parser.add_argument('--vod', default='', help='VOD id or https://www.twitch.tv/videos/<id>')
    parser.add_argument('--channel', default='', help='channel login whose newest VOD to replay')
    parser.add_argument('--file', default='', help='local VOD file to replay as if it were live')
    parser.add_argument('--seconds', type=float, default=200.0, help='measured wall-clock window')
    parser.add_argument('--warmup-seconds', type=float, default=15.0,
                        help='warm-up window that pays the one-time model load (0 to disable)')
    parser.add_argument('--start', type=float, default=0.0,
                        help='seconds into the VOD to start (an HLS seek costs one long read)')
    parser.add_argument('--rate', type=float, default=1.0)
    parser.add_argument('--max-catchup', type=float, default=1.0)
    parser.add_argument('--max-height', type=int, default=720)
    parser.add_argument('--stages', default='table,person')
    parser.add_argument('--sample-every', type=float, default=0.25)
    parser.add_argument('--open-timeout', type=float, default=120.0)
    parser.add_argument('--output', default='')
    args = parser.parse_args()

    if args.probe:
        report = probe(args.channel or SAVED_CHANNEL_LOGIN, args.vod or None)
        print(json.dumps(report, indent=2, sort_keys=True))
        if args.output:
            Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True))
        return
    report = run(args)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True))
    print('\n%s on %s (%s), wall %.1f s' % (report['source'], report['vod_id'] or '-',
                                            report['network'], report['window_s']))
    print('  host: loadavg %s on %s cores | VOD opened after %.1f s%s'
          % (report['host']['loadavg'], report['host']['cores'], report['opened_after_s'],
             '' if not report['warmup'] else ' | warm-up %ss'
             % report['warmup']['seconds']))
    print('  frames: received %d (%.2f fps), processed %d (%.2f fps), invariant %s'
          % (report['frames_received'], report['received_fps'], report['frames_processed'],
             report['processed_fps'], report['invariant_holds']))
    print('  drops: %s' % json.dumps(report['drops'], sort_keys=True))
    print('  pacing: wall %.2f s, video consumed %.2f s (%.4f x wall), drift %.2f s, max |drift| %.2f s, '
          'pacer-dropped %s' % (report['pacing']['wall_s'], report['pacing']['video_consumed_s'] or 0,
                                report['pacing']['video_per_wall'] or 0, report['pacing']['drift_s'] or 0,
                                report['pacing']['max_abs_drift_s'] or 0,
                                report['pacing']['frames_dropped_by_pacer']))
    for stage in report['stages']:
        print('  stage %-7s @%d  runs %-3d skips %-3d  p50 %-7s p95 %-7s max %-7s  %s'
              % (stage['name'], stage['every_n_frames'], stage['runs'], stage['skips'],
                 stage['p50_ms'], stage['p95_ms'], stage['max_ms'], json.dumps(stage['evidence'])))
    for name in ('decode', 'resize', 'encode', 'receive_to_result', 'inter_frame'):
        entry = report['latency_ms'].get(name)
        if entry:
            print('  step  %-17s count %-4d p50 %-7s p95 %-7s max %s'
                  % (name, entry['count'], entry['p50_ms'], entry['p95_ms'], entry['max_ms']))


if __name__ == '__main__':
    main()
