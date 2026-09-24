"""Opt-in envelope measurement: per-stage ms, achieved fps, why frames went.

Real decoder, real YOLOv8n person stage, real clock, real 30 fps VOD pacing - no
mocks.  Each case is measured twice: a short warm-up run whose numbers are
discarded (it pays YOLO's one-time model load, which is a module-level cache), then
a fresh processor for the reported run, so the reported window is warm.

The `ball` stage is the trained detector (`annotator.pipeline_stages.BallStage`,
`out/tiny_ball_probe/960x540-scratch.pt`, 960x540, threshold 0.425).  `--ball
standin` swaps the 15 ms `BallStandIn` back in, which is how the previous matrix
was measured and how the two are compared.  `table` is the shipped table stage
serving the saved per-segment reference for vod30; `person` is the real GPU
detector on the scaled frame.

The whole `{table cached} x {person@1} x {ball@1,@2,@3}` matrix at 90 frames/case
is the default; the person-only cases stay available through `--cases`.

Run: PYTHONPATH=. .venv/bin/python -B tests/live_envelope_run.py --frames 90
     PYTHONPATH=. .venv/bin/python -B tests/live_envelope_run.py --ball standin
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
BALL_MS = 15.0
#: `src/shot_pot_gate.py` GateThresholds: a shot needs this many consecutive
#: above-bar intervals, so the first three of them exist 3 x dt after the ball
#: actually started moving.
GATE_ONSET_INTERVALS = 3


class BallStandIn:
    """The ball detector's old placeholder: 15 ms of work when it runs, no result."""

    name = 'ball'
    budget_ms = None
    every_n_frames = 1

    def __init__(self, ms=BALL_MS, every_n_frames=1):
        self.ms = ms
        self.every_n_frames = every_n_frames

    def process(self, frame, context):
        time.sleep(self.ms / 1000.0)
        return {'boxes': []}


def seek_capture(media, start_frame):
    """Default capture factory plus a seek, so a case can start mid-match."""
    from annotator.live_processing import _capture
    capture = _capture(media)
    if start_frame:
        capture.set(3, start_frame)  # cv2.CAP_PROP_POS_FRAMES
    return capture


def stages_for(names, ball='real', device='auto'):
    """Registry for a case: the built-in detector stages plus the ball stage.

    The pipeline's ``detectors`` argument is the app's allowlist (table/person), so
    the ball stage is registered as a stage only - which is exactly the seam a real
    ball detector uses.  ``ball='standin'`` restores the 15 ms placeholder the
    previous matrix was measured with, for the same-shape comparison.
    """
    from annotator.pipeline_stages import BallStage, PersonStage, TableStage
    stages = []
    for spec in names:
        name, _, cadence = spec.partition('@')
        if name == 'table':
            # The shipped static-table path: the saved per-segment reference, no detection.
            stages.append(TableStage(ROOT, dataset='vod30'))
        elif name == 'person':
            stages.append(PersonStage(ROOT))
        elif name == 'ball':
            every = int(cadence) if cadence else 1
            if ball == 'real':
                stages.append(BallStage(ROOT, device=device, every_n_frames=every))
            else:
                stages.append(BallStandIn(every_n_frames=every))
        else:
            raise SystemExit('unknown stage: ' + spec)
    return stages


def onset_latency(cadence, frame_period_ms, ball_p50_ms, ball_p95_ms):
    """Shot onset -> the gate can call it, from the measured per-frame cost.

    The gate needs ``GATE_ONSET_INTERVALS`` consecutive above-bar intervals, each at
    most ``max_gap_s`` long; at cadence N the ball samples are N frame periods
    apart.  The sampling phase is how long after the onset the first sample lands
    (N/2 frames on average, N in the worst case), and the last frame still has to be
    processed.  Every term is measured, none is assumed.
    """
    interval = cadence * frame_period_ms
    mean = GATE_ONSET_INTERVALS * interval + interval / 2.0 + ball_p50_ms
    worst = GATE_ONSET_INTERVALS * interval + interval + ball_p95_ms
    return dict(cadence=cadence, interval_ms=round(interval, 2),
                motion_ms=round(GATE_ONSET_INTERVALS * interval, 2),
                phase_mean_ms=round(interval / 2.0, 2),
                processing_p50_ms=round(ball_p50_ms, 2),
                processing_p95_ms=round(ball_p95_ms, 2),
                mean_call_ms=round(mean, 1), worst_call_ms=round(worst, 1))


def measure(case, names, detectors, frames, start_frame, warmup, ball='real', device='auto'):
    from annotator.live_processing import LiveProcessor

    def run(count, timeout):
        processor = LiveProcessor(ROOT, stages=stages_for(names, ball=ball, device=device),
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
    cadence = {stage['name']: stage['every_n_frames'] for stage in status['stages']}
    # A frame that runs `ball@3` pays the whole 15 ms; the *amortised* cost over three
    # frames is a third of it. Both numbers matter: the frame cost decides the budget
    # (and therefore the drops), the amortised cost decides the sustained rate.
    envelope_p50 = p50('decode') + p50('resize') + p50('encode') + sum(p50(name) for name in stage_names)
    envelope_p95 = p95('decode') + p95('resize') + p95('encode') + sum(p95(name) for name in stage_names)
    amortised_p50 = p50('decode') + p50('resize') + p50('encode') + \
        sum(p50(name) / cadence.get(name, 1) for name in stage_names)
    source_fps = status.get('source_fps') or 30.0
    onset = (onset_latency(cadence['ball'], 1000.0 / source_fps, p50('ball'), p95('ball'))
             if 'ball' in cadence else None)
    return dict(
        case=case, ball=ball,
        stages=[dict(name=entry['name'], every_n_frames=entry['every_n_frames'],
                     runs=entry['runs'], skips=entry['skips'], p50_ms=entry['p50_ms'],
                     p95_ms=entry['p95_ms'], evidence=entry['evidence'])
                for entry in status['stages']],
        frames_requested=frames, frames_received=status['frames_received'],
        frames_processed=status['frames_processed'], drops=status['drop_reasons'],
        last_drop=status['last_drop'], budget_ms=status['frame_budget_ms'],
        wall_s=round(elapsed, 3),
        achieved_fps=round(status['frames_processed'] / elapsed, 2),
        received_fps=round(status['frames_received'] / elapsed, 2),
        published_of_requested=round(status['frames_processed'] / frames, 3),
        envelope_p50_ms=round(envelope_p50, 2), envelope_p95_ms=round(envelope_p95, 2),
        amortised_p50_ms=round(amortised_p50, 2),
        result_p50_ms=p50('receive_to_result'), result_p95_ms=p95('receive_to_result'),
        source_fps=round(source_fps, 4), onset=onset,
        fits_30fps_p50=envelope_p50 <= FRAME_BUDGET_MS, fits_30fps_p95=envelope_p95 <= FRAME_BUDGET_MS,
        fits_30fps_amortised=amortised_p50 <= FRAME_BUDGET_MS,
        fits_15fps_p50=envelope_p50 <= 2 * FRAME_BUDGET_MS,
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
    parser.add_argument('--frames', type=int, default=90)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--start', type=int, default=8000)
    parser.add_argument('--ball', choices=('real', 'standin'), default='real',
                        help='the trained detector (default) or the old 15 ms stand-in')
    parser.add_argument('--device', default='auto')
    parser.add_argument('--cases', default='decode,table+person,'
                                            'table+person+ball@1,table+person+ball@2,'
                                            'table+person+ball@3')
    parser.add_argument('--twitch-channel', default='')
    parser.add_argument('--output', default='')
    args = parser.parse_args()

    cases = {
        # case -> (stage names in order, the detectors list the app may ask for)
        'decode': ([], ['person']),
        'person': (['person'], ['person']),
        'table+person': (['table', 'person'], ['table', 'person']),
        'table+person+ball@1': (['table', 'person', 'ball@1'], ['table', 'person']),
        'table+person+ball@2': (['table', 'person', 'ball@2'], ['table', 'person']),
        'table+person+ball@3': (['table', 'person', 'ball@3'], ['table', 'person']),
        'person+ball@1': (['person', 'ball@1'], ['person']),
        'person+ball@2': (['person', 'ball@2'], ['person']),
        'person+ball@3': (['person', 'ball@3'], ['person']),
    }
    results = []
    for name in args.cases.split(','):
        if name not in cases:
            raise SystemExit('unknown case: ' + name)
        names, detectors = cases[name]
        result = measure(name, names, detectors, args.frames, args.start, args.warmup,
                         ball=args.ball, device=args.device)
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    if args.twitch_channel:
        result = twitch_case(args.twitch_channel, args.frames * 5, 3)
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2, sort_keys=True))

    print('\n%-22s %7s %6s %6s %6s %7s %8s %9s %6s %9s  %s' %
          ('case', 'dec', 'resize', 'enc', 'fps', 'env-p50', 'amort-p50', 'recv2res',
           'pub/90', 'ball p50/95', 'drops'))
    for result in results:
        if not result.get('reachable', True):
            print('%-22s UNREACHABLE: %s' % (result['case'], result.get('reason')))
            continue
        steps = result['steps']
        def value(name, key='p50_ms'):
            return steps.get(name, {}).get(key) or 0.0
        print('%-22s %7.2f %6.2f %6.2f %6.2f %7.2f %8.2f %9.2f %6d %9s  %s' % (
            result['case'], value('decode'), value('resize'), value('encode'), result['achieved_fps'],
            result['envelope_p50_ms'], result['amortised_p50_ms'], value('receive_to_result'),
            result['frames_processed'], '%.1f/%.1f' % (value('ball'), value('ball', 'p95_ms')),
            json.dumps(result['drops'], sort_keys=True)))
    for result in results:
        print('%-22s load=%-5s fits 33.33: p50=%-5s amort=%-5s | fits 66.7: %-5s | result p50/p95 %s/%s ms' % (
            result['case'], result['loadavg'][0], result.get('fits_30fps_p50'),
            result.get('fits_30fps_amortised'), result.get('fits_15fps_p50'),
            result.get('result_p50_ms'), result.get('result_p95_ms')))
        if result.get('onset'):
            print('%-22s onset: mean %.0f ms (motion %.0f + phase %.0f + ball %.1f), worst %.0f ms, '
                  'interval %.1f ms' % (
                      result['case'], result['onset']['mean_call_ms'], result['onset']['motion_ms'],
                      result['onset']['phase_mean_ms'], result['onset']['processing_p50_ms'],
                      result['onset']['worst_call_ms'], result['onset']['interval_ms']))
    for result in results:
        for entry in result.get('stages', []):
            if entry['name'] == 'ball':
                print('%-22s ball stage: runs=%d skips=%d evidence=%s' % (
                    result['case'], entry['runs'], entry['skips'], json.dumps(entry['evidence'])))


if __name__ == '__main__':
    main()
