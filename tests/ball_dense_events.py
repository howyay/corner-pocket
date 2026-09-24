"""Dense tracks -> real shot/pot events: the gate's first non-census input.

Every event detector in this repo so far decided from a sparse ball census (1-3
classical detections per sampled frame, ~0.9 s apart).  `src/shot_pot_gate.py` was
written and tested for *dense* per-frame tracks before any existed; the trained
ball detector now exists, so this runs the whole chain on real footage:

    VOD segment -> the production stage registry  (table, person, ball - the same
                   list ``LiveProcessor.start(..., ['table','person','ball'])``
                   builds, with the ball stage at cadence N)
                -> colour + score per ball            (src/ball_census)
                -> association into identities        (src/ball_census.associate)
                -> occlusion per frame                (src/motion_scan.probe_pair)
                -> shot / pot / break rules           (src/shot_pot_gate.classify)

Nothing here is a new algorithm: it is the pipeline's own stages, the census's own
associator and the gate's own rules, wired together.

**This run is load-diagnosable on purpose.**  The box is shared and heavily loaded,
so the report carries the host load at start and end, how many frames were decoded
versus how many ran the ball stage, the per-stage millisecond distribution, and the
budget partition.  Two different sparsities have to be told apart:

* **cadence decay** - the ball stage runs on 1 frame in N.  That is decided by
  ``--cadence`` and is independent of load; the report names it
  (``samples.expected_ball_runs`` vs ``samples.ball_runs``).
* **budget drops** - frames a *live* pipeline would have dropped for exceeding the
  frame budget.  This offline pass does not drop them (the registry only reports the
  overrun), so the tracks below are NOT load-degraded even when the host is: only
  the wall clock is.  ``budget.frames_over_budget`` is that number anyway, so the
  reader can see whether a live run of the same configuration would have published
  anything at all.

The segment is stated on the command line and in the report.  The detector's
accuracy on it is NOT held-out (the segment lies inside the training time range,
and t=1363-1366, 1530, 1650 of it are held-out frames): quote the held-out F1 for
accuracy, this run for behaviour.

Run:
  PYTHONPATH=. .venv/bin/python -B tests/ball_dense_events.py --start 1350 --seconds 300
Writes out/dense-events/segment-<start>-<end>.json (out/ is gitignored).
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

WORK_SIZE = (960, 540)
NATIVE = (1280, 720)
#: src/motion_scan.PERSON_SHARE_MAX - the share of the cloth one person box must
#: cover to be called "a person on the cloth" rather than a bystander at the edge.
PERSON_ON_CLOTH = 0.02


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1, int(fraction * (len(ordered) - 1))))], 3)


def segment_report(args):
    """Decode once; feed the production stages, the census, the occlusion probe and the gate."""
    import cv2
    import numpy as np
    from annotator.pipeline_stages import StageRegistry, default_stages
    from src import ball_census as bc
    from src import motion_scan as ms
    from src import shot_pot_gate as gate

    video = ms.video_for(args.dataset, ROOT)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit('cannot open %s' % video)
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    start_frame = int(round(args.start * fps))
    expected = int(round(args.seconds * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    quad_native = ms.load_quad(args.dataset, ROOT)['quad_px']
    scale = WORK_SIZE[0] / float(NATIVE[0])
    quad_work = tuple((round(x * scale, 2), round(y * scale, 2)) for x, y in quad_native)
    cfg = ms.config_for(video, dataset=args.dataset, root=ROOT)
    ctx = ms.cloth_context(quad_native, cfg)
    measured_r = ms.sam3_ball_radius(args.dataset, ROOT)
    radius_work = round((measured_r['radius'] or 8.0) * scale, 2)

    detectors = ['table'] + (['person'] if args.person else []) + ['ball']
    stages = default_stages(detectors, ROOT, dataset=args.dataset, ball_every_n=args.cadence)
    registry = StageRegistry(stages)
    observations = []
    occ_times, occ_shares = [], []
    person_shares = []
    timings = {name: [] for name in ('decode', 'resize', 'occlusion') + tuple(s.name for s in stages)}
    runs = Counter()
    skips = Counter()
    over_budget = 0
    over_budget_stage = Counter()
    prev_native = None
    frames_read = 0
    balls_seen = 0
    load_start = os.getloadavg()
    started = time.perf_counter()
    try:
        for index in range(expected):
            stamp = time.perf_counter()
            ok, native = cap.read()
            if not ok:
                break
            decoded = time.perf_counter()
            work = cv2.resize(native, WORK_SIZE, interpolation=cv2.INTER_AREA)
            resized = time.perf_counter()
            t = (start_frame + index) / fps
            if prev_native is not None:
                probe = ms.probe_pair(prev_native, native, ctx, cfg)
                occ_times.append(round(t, 4))
                occ_shares.append(float(probe['occ_dense']))
            probed = time.perf_counter()
            prev_native = native
            run = registry.run(work, elapsed_ms=0.0, frame_budget_ms=args.budget_ms,
                               frame_index=start_frame + index, time_s=t)
            frames_read += 1
            timings['decode'].append((decoded - stamp) * 1000)
            timings['resize'].append((resized - decoded) * 1000)
            timings['occlusion'].append((probed - resized) * 1000)
            for name, elapsed in run.timings_ms.items():
                timings.setdefault(name, []).append(elapsed)
            for name in run.ran:
                runs[name] += 1
            for name in run.skipped:
                skips[name] += 1
            if run.overrun_stage is not None:
                over_budget += 1
                over_budget_stage[run.overrun_stage] += 1
            person = run.results.get('person')
            if person is not None:
                boxes = [box.get('bbox') or box.get('box') for box in person.get('boxes') or []]
                boxes = [box for box in boxes if box]
                person_shares.append(ms.person_overlap(boxes, quad_native) if boxes else 0.0)
            result = run.results.get('ball')
            if result is None:
                continue                    # cadence skipped it: no ball fact for this frame
            for ball in result['balls']:
                color = bc.classify_ball_color(work, ball['x'], ball['y'],
                                               max(radius_work * 0.5, 2.5))
                observations.append(bc.Observation(
                    t=t, color=color, cx=ball['x'], cy=ball['y'], r=radius_work,
                    source='tiny_ball_net', score=ball['score']))
                balls_seen += 1
    finally:
        cap.release()
    wall = time.perf_counter() - started
    load_end = os.getloadavg()

    tracks, _frames = bc.associate(observations, match_px=bc.TRACK_MATCH_PX,
                                   gap_s=bc.TRACK_GAP_S)
    occ_flag = {round(t, 4): share >= gate.OCC_DENSE_MIN
                for t, share in zip(occ_times, occ_shares)}
    gate_tracks = []
    for track in tracks:
        rows = []
        for obs in track.obs:
            index = int(round(obs.t * fps))
            rows.append((index, obs.t, obs.cx, obs.cy, float(obs.score or 0.0),
                         occ_flag.get(round(obs.t, 4), False)))
        gate_tracks.append(gate.Track.from_rows('t%03d-%s' % (track.tid, track.color), rows))
    occlusion = gate.Occlusion.from_shares(occ_times, occ_shares,
                                           threshold=gate.OCC_DENSE_MIN,
                                           source='motion_scan.probe_pair occ_dense')
    thresholds = gate.GateThresholds(frame_size=list(WORK_SIZE), cloth_quad=list(quad_work))
    until = (start_frame + frames_read - 1) / fps
    report = gate.classify(gate_tracks, occlusion=occlusion, thresholds=thresholds,
                           observed_until_t=until)

    intervals = [iv for track in gate_tracks for iv in _speeds(track.samples)]
    spacing = [dt for track in gate_tracks for dt in _spacings(track.samples)]
    hits = [len(track.samples) for track in gate_tracks]
    durations = [float(track.samples[-1].t) - float(track.samples[0].t) for track in gate_tracks]
    accounted = sum(sum(values) for values in timings.values())
    return dict(
        segment=dict(dataset=args.dataset, video=str(video.name), start_s=args.start,
                     seconds=args.seconds, frames_expected=expected, frames_decoded=frames_read,
                     fps=round(fps, 4), first_frame=start_frame,
                     window=[round(start_frame / fps, 2), round(until, 2)],
                     note='inside the detector training time range; t 1363-1366, 1530, 1650 '
                          'are held-out frames'),
        load=dict(start=[round(v, 2) for v in load_start], end=[round(v, 2) for v in load_end],
                  note='shared host; the offline pass discards no frame, so track shape is '
                       'load-independent even though the wall clock is not'),
        stages=dict(names=registry.names(), cadence={s.name: getattr(s, 'every_n_frames', 1)
                                                     for s in stages},
                    detectors=detectors),
        samples=dict(balls=balls_seen, ball_runs=runs.get('ball', 0), ball_skips=skips.get('ball', 0),
                     expected_ball_runs=len(range(0, frames_read, args.cadence)),
                     per_sampled_frame=round(balls_seen / max(1, runs.get('ball', 0)), 2),
                     person_frames=runs.get('person', 0)),
        budget=dict(frames_over_budget=over_budget, first_overrun_stage=dict(over_budget_stage),
                    budget_ms=args.budget_ms,
                    note='offline: an overrun is counted, not dropped, so the tracks below '
                         'include every frame a live run would have thrown away'),
        cost=dict(wall_s=round(wall, 2), frames_per_s=round(frames_read / wall, 2),
                  accounted_ms=round(accounted, 1),
                  unaccounted_ms=round(wall * 1000 - accounted, 1),
                  ms={name: dict(n=len(values), p50=percentile(values, .5), p95=percentile(values, .95),
                                 max=round(max(values), 2) if values else None)
                      for name, values in timings.items() if values}),
        person=dict(frames=len(person_shares),
                    frames_with_a_box=sum(1 for share in person_shares if share > 0),
                    frames_on_cloth=sum(1 for share in person_shares if share >= PERSON_ON_CLOTH),
                    share_on_cloth=round(sum(1 for share in person_shares
                                             if share >= PERSON_ON_CLOTH) / max(1, len(person_shares)), 4),
                    max_cloth_share=round(max(person_shares), 4) if person_shares else None),
        tracks=dict(n=len(tracks), samples_total=len(observations),
                    median_samples=statistics.median(hits) if hits else 0,
                    stable_2plus=sum(1 for count in hits if count >= 2),
                    single_sample=sum(1 for count in hits if count == 1),
                    max_samples=max(hits) if hits else 0,
                    median_seconds=round(statistics.median(durations), 2) if durations else None,
                    max_seconds=round(max(durations), 2) if durations else None,
                    gated=len(gate_tracks),
                    median_dt_s=round(statistics.median(spacing), 4) if spacing else None),
        motion=dict(median_interval_px_s=round(statistics.median(intervals), 1) if intervals else None,
                    p90_interval_px_s=percentile(intervals, .9),
                    max_interval_px_s=round(max(intervals), 1) if intervals else None,
                    above_motion_bar=sum(1 for v in intervals if v > thresholds.motion_speed_px_s),
                    at_or_below_rest_bar=sum(1 for v in intervals
                                             if v <= thresholds.rest_speed_px_s),
                    intervals=len(intervals)),
        occlusion=dict(source='motion_scan.probe_pair occ_dense',
                       threshold=gate.OCC_DENSE_MIN, frames=len(occ_times),
                       p50=percentile(occ_shares, .5), p90=percentile(occ_shares, .9),
                       max=round(max(occ_shares), 3) if occ_shares else None,
                       share_occluded=round(sum(occ_flag.values()) / max(1, len(occ_flag)), 4)),
        thresholds=thresholds.as_dict(),
        gate=report.as_dict(),
        rejection_codes=dict(sorted(Counter(record.code for record in report.rejections).items())),
    )


def _speeds(samples):
    out = []
    for a, b in zip(samples, samples[1:]):
        dt = float(b.t) - float(a.t)
        if dt > 0:
            out.append(((b.x - a.x) ** 2 + (b.y - a.y) ** 2) ** .5 / dt)
    return out


def _spacings(samples):
    return [float(b.t) - float(a.t) for a, b in zip(samples, samples[1:])
            if float(b.t) - float(a.t) > 0]


def summarise(result):
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('gate', 'thresholds')}, indent=1))
    counts = result['gate']['counts']
    real_breaks = sum(1 for group in result['gate']['breaks'] if group.get('is_break'))
    print('\nGATE: %d shots, %d pots, %d unknowns, %d rejections, %d onset group(s) of which '
          '%d break(s) (of %d tracks)'
          % (counts['shots'], counts['pots'], counts['unknowns'], counts['rejections'],
             counts['breaks'], real_breaks, counts['tracks']))
    print('rejection codes:', json.dumps(result['rejection_codes']))
    for shot in result['gate']['shots'][:10]:
        print('  SHOT  t=%7.2f  %s  peak %.0f px/s  %.2f s  %d samples  rest %.2f s'
              % (shot['onset_t'], shot['ball_id'], shot.get('peak_speed_px_s') or 0,
                 shot.get('duration_s') or 0, len(shot.get('samples_used') or []),
                 shot.get('rest_window_measured_s') or 0))
    for pot in result['gate']['pots'][:10]:
        print('  %-7s t=%7.2f  %s  pocket %s  %.0f px from centre  %s'
              % (pot['verdict'].upper(), pot['last_t'], pot['ball_id'],
                 pot.get('pocket') or '-', pot.get('pocket_distance_px') or -1,
                 pot.get('reason') or ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--start', type=float, default=1350.0)
    parser.add_argument('--seconds', type=float, default=300.0)
    parser.add_argument('--cadence', type=int, default=2)
    parser.add_argument('--threshold', type=float, default=0.425)
    parser.add_argument('--device', default='auto')
    parser.add_argument('--dataset', default='vod30')
    parser.add_argument('--person', dest='person', action='store_true', default=True)
    parser.add_argument('--no-person', dest='person', action='store_false')
    parser.add_argument('--budget-ms', type=float, default=1000.0 / 30)
    parser.add_argument('--output', default='')
    args = parser.parse_args()
    result = segment_report(args)
    output = args.output or str(ROOT / 'out/dense-events/segment-%d-%d.json'
                                % (args.start, args.start + args.seconds))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, indent=1))
    summarise(result)
    print('\nwrote', output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
