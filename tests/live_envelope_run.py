"""Opt-in envelope measurement: per-stage ms, achieved fps, why frames went.

Real decoder, real YOLOv8n person stage, real clock, real 30 fps VOD pacing - no
mocks.  Each case is measured twice: a short warm-up run whose numbers are
discarded (it pays YOLO's one-time model load, which is a module-level cache), then
a fresh processor for the reported run, so the reported window is warm.

The `ball` case is the ball detector that does not exist yet: a stage that sleeps
15 ms, the expected cost, so the table answers "is 30 fps met with headroom for one
more stage" before that detector lands.

Run: PYTHONPATH=. .venv/bin/python -B tests/live_envelope_run.py --frames 60
     PYTHONPATH=. .venv/bin/python -B tests/live_envelope_run.py --twitch-channel ttp0olfriday
No production state is written; the Twitch case gets its own TempDir root.
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

FRAME_BUDGET_MS = 1000.0 / 30


class BallStandIn:
    """The ball detector's expected price: 15 ms of work per frame, no result."""

    name = 'ball'
    budget_ms = None

    def __init__(self, ms=15.0):
        self.ms = ms

    def process(self, frame, context):
        time.sleep(self.ms / 1000.0)
        return {'boxes': []}


class TableEveryN:
    """Table stage that recomputes the cloth polygon every N frames and caches it.

    The cloth is static - the camera does not move - so paying 8-11 ms on every frame
    for a polygon that only changes when the table is re-covered is avoidable. This
    stand-in measures the pipeline with that fixed, using only the public contract.
    """

    name = 'table'
    budget_ms = None

    def __init__(self, every=30):
        from annotator.pipeline_stages import TableStage
        self.every = every
        self.count = 0
        self.inner = TableStage(ROOT)
        self.cached = None

    def process(self, frame, context):
        if self.cached is None or self.count % self.every == 0:
            self.cached = self.inner.process(frame, context)
        self.count += 1
        return self.cached


def seek_capture(media, start_frame):
    """Default capture factory plus a seek, so a case can start mid-match."""
    from annotator.live_processing import _capture
    capture = _capture(media)
    if start_frame:
        capture.set(3, start_frame)  # cv2.CAP_PROP_POS_FRAMES
    return capture


def stages_for(names):
    """Registry for a case: the built-in detector stages plus the ball stand-in.

    The pipeline's ``detectors`` argument is the app's allowlist (table/person), so
    the ball stand-in is registered as a stage only - which is exactly the seam a
    real ball detector will use.
    """
    from annotator.pipeline_stages import PersonStage, TableStage
    factories = {'table': lambda: TableStage(ROOT), 'tablecache': lambda: TableEveryN(30),
                 'person': lambda: PersonStage(ROOT), 'ball': lambda: BallStandIn()}
    return [factories[name]() for name in names]


def measure(case, names, detectors, frames, start_frame, warmup):
    from annotator.live_processing import LiveProcessor

    def run(count, timeout):
        processor = LiveProcessor(ROOT, stages=stages_for(names),
                                  capture_factory=lambda media: seek_capture(media, start_frame))
        processor.start(dict(kind='dataset', dataset='vod30'), detectors)
        deadline = time.monotonic() + timeout
        # The reported window starts when the decoder has produced its first frame:
        # opening the file and seeking is a one-off, not the steady-state rate. It
        # closes once the requested frames are *accounted* (published or dropped) -
        # waiting for a fully drained pipeline would never close, because the frame
        # the worker is holding is always one behind the decoder.
        while processor.status()['frames_received'] < 1 and time.monotonic() < deadline:
            time.sleep(.005)
        started = time.monotonic()
        while time.monotonic() < deadline:
            status = processor.status()
            accounted = status['frames_processed'] + sum(status['drop_reasons'].values())
            if status['frames_received'] >= count and accounted >= count:
                break
            time.sleep(.01)
        elapsed = time.monotonic() - started
        status = processor.stop()
        # stop() only waits stop_timeout; a stage still inside a cold model load keeps
        # the module-level person model lock. Never let the next case start on top of
        # that: wait for the threads to actually exit.
        hard = time.monotonic() + 300.0
        while time.monotonic() < hard:
            status = processor.status()
            if not status['decoder_alive'] and not status['worker_alive']:
                break
            time.sleep(.05)
        return status, elapsed

    cold, _ = run(warmup, max(300.0, warmup / 30.0 + 30.0))
    warmed = [entry['name'] for entry in cold['stages'] if entry['count'] >= 1]
    status, elapsed = run(frames, max(180.0, frames / 30.0 + 120.0))
    if status['frames_received'] < frames * 0.5:
        # Another tenant stalled the decoder (this host is shared); retry once rather
        # than reporting a number that measures the neighbour.
        status, elapsed = run(frames, max(180.0, frames / 30.0 + 120.0))
    stalled = status['frames_received'] < frames * 0.5
    latency = status['latency_ms']
    def p50(name):
        return latency.get(name, {}).get('p50_ms') or 0.0
    def p95(name):
        return latency.get(name, {}).get('p95_ms') or 0.0
    stage_names = [stage['name'] for stage in status['stages']]
    envelope_p50 = p50('decode') + p50('resize') + p50('encode') + sum(p50(name) for name in stage_names)
    envelope_p95 = p95('decode') + p95('resize') + p95('encode') + sum(p95(name) for name in stage_names)
    return dict(
        case=case, frames_requested=frames, frames_received=status['frames_received'],
        frames_processed=status['frames_processed'], drops=status['drop_reasons'],
        last_drop=status['last_drop'], budget_ms=status['frame_budget_ms'],
        wall_s=round(elapsed, 3),
        achieved_fps=round(status['frames_processed'] / elapsed, 2),
        received_fps=round(status['frames_received'] / elapsed, 2),
        envelope_p50_ms=round(envelope_p50, 2), envelope_p95_ms=round(envelope_p95, 2),
        fits_30fps_p50=envelope_p50 <= FRAME_BUDGET_MS, fits_30fps_p95=envelope_p95 <= FRAME_BUDGET_MS,
        cold_first_result_ms=round(cold['latency_ms'].get('receive_to_result', {}).get('max_ms') or 0.0, 1),
        warm_stages=warmed, warm=all(entry['count'] >= 1 for entry in cold['stages']),
        stalled=stalled,
        loadavg=[round(value, 1) for value in os.getloadavg()],
        steps={name: latency[name] for name in
               ('decode', 'resize', 'encode', 'receive_to_process', 'receive_to_result', 'inter_frame')
               + tuple(stage_names) if name in latency},
    )


def twitch_case(channel, frames, warmup):
    from annotator.live_processing import LiveProcessor
    from annotator.twitch_source import TwitchSourceError, resolve_twitch

    url = 'https://www.twitch.tv/' + channel
    try:
        media = resolve_twitch(url)
    except TwitchSourceError as error:
        return dict(case='twitch', channel=channel, reachable=False, reason=str(error))
    try:
        with tempfile.TemporaryDirectory(prefix='.live-envelope-', dir=ROOT) as directory:
            root = Path(directory)
            (root / 'out/corner-pocket').mkdir(parents=True)
            (root / 'out/corner-pocket/state.json').write_text(json.dumps({'sources': [
                dict(id='harness', kind='channel', channel=channel, url=url)]}))
            os.symlink(ROOT / 'yolov8n.pt', root / 'yolov8n.pt')
            from annotator.pipeline_stages import default_stages

            def run(count, timeout):
                processor = LiveProcessor(root, stages=default_stages(['table', 'person'], root))
                processor.start(dict(kind='twitch', source_id='harness'), ['table', 'person'])
                deadline = time.monotonic() + timeout
                while processor.status()['frames_received'] < 1 and time.monotonic() < deadline:
                    time.sleep(.02)
                started = time.monotonic()
                while time.monotonic() < deadline:
                    status = processor.status()
                    accounted = status['frames_processed'] + sum(status['drop_reasons'].values())
                    if status['frames_received'] >= count and accounted >= count:
                        break
                    time.sleep(.02)
                elapsed = time.monotonic() - started
                status = processor.stop()
                hard = time.monotonic() + 300.0
                while time.monotonic() < hard:
                    status = processor.status()
                    if not status['decoder_alive'] and not status['worker_alive']:
                        break
                    time.sleep(.05)
                return status, elapsed

            cold, _ = run(warmup, 300.0)
            status, elapsed = run(frames, max(120.0, frames / 15.0 + 60.0))
    except TwitchSourceError as error:
        return dict(case='twitch', channel=channel, reachable=False, reason=str(error))
    latency, stage_names = status['latency_ms'], [stage['name'] for stage in status['stages']]
    envelope = (latency.get('decode', {}).get('p50_ms') or 0) + (latency.get('resize', {}).get('p50_ms') or 0) \
        + (latency.get('encode', {}).get('p50_ms') or 0) \
        + sum((latency.get(name, {}).get('p50_ms') or 0) for name in stage_names)
    return dict(case='twitch', channel=channel, reachable=True, state=status['state'],
                error=status['error'], frames_received=status['frames_received'],
                frames_processed=status['frames_processed'], drops=status['drop_reasons'],
                wall_s=round(elapsed, 3), achieved_fps=round(status['frames_processed'] / elapsed, 2),
                received_fps=round(status['frames_received'] / elapsed, 2),
                envelope_p50_ms=round(envelope, 2), fits_30fps_p50=envelope <= FRAME_BUDGET_MS,
                cold_first_result_ms=round(cold['latency_ms'].get('receive_to_result', {}).get('max_ms') or 0.0, 1),
                loadavg=[round(value, 1) for value in os.getloadavg()],
                steps={name: latency[name] for name in latency})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=int, default=60)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--start', type=int, default=8000)
    parser.add_argument('--cases', default='decode,person,table+person,person+ball,tablecached+person+ball,ball')
    parser.add_argument('--twitch-channel', default='')
    parser.add_argument('--output', default='')
    args = parser.parse_args()

    cases = {
        # case -> (stage names in order, the detectors list the app may ask for)
        'decode': ([], ['person']),
        'table': (['table'], ['table']),
        'person': (['person'], ['person']),
        'table+person': (['table', 'person'], ['table', 'person']),
        'person+ball': (['person', 'ball'], ['person']),
        'tablecached+person+ball': (['tablecache', 'person', 'ball'], ['table', 'person']),
        'ball': (['table', 'person', 'ball'], ['table', 'person']),
    }
    results = []
    for name in args.cases.split(','):
        if name not in cases:
            raise SystemExit('unknown case: ' + name)
        names, detectors = cases[name]
        result = measure(name, names, detectors, args.frames, args.start, args.warmup)
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    if args.twitch_channel:
        result = twitch_case(args.twitch_channel, args.frames * 5, 3)
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2, sort_keys=True))

    print('\n%-14s %7s %6s %6s %6s %7s %7s %9s %7s  %s' %
          ('case', 'dec', 'resize', 'enc', 'fps', 'env-p50', 'env-p95', 'recv2res', 'proc', 'drops'))
    for result in results:
        if not result.get('reachable', True):
            print('%-14s UNREACHABLE: %s' % (result['case'], result.get('reason')))
            continue
        steps = result['steps']
        def value(name, key='p50_ms'):
            return steps.get(name, {}).get(key) or 0.0
        print('%-14s %7.2f %6.2f %6.2f %6.2f %7.2f %7.2f %9.2f %7d  %s' % (
            result['case'], value('decode'), value('resize'), value('encode'), result['achieved_fps'],
            result['envelope_p50_ms'], result['envelope_p95_ms'], value('receive_to_result'),
            result['frames_processed'], json.dumps(result['drops'], sort_keys=True)))
    for result in results:
        print('%-14s fits 33.33 ms: p50=%s p95=%s' % (result['case'], result.get('fits_30fps_p50'),
                                                      result.get('fits_30fps_p95')))


if __name__ == '__main__':
    main()
