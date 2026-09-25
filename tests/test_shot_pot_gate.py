"""Shot/pot gate contract: the rules over a dense track, and every refusal.

``src/shot_pot_gate.py`` is pure, so this file is synthetic almost everywhere and
can be exhaustive about ground truth: a stationary ball, a break, a single shot, a
pot into each of the six pockets, a vanish under the occlusion flag, a ball leaving
the frame, a ball that comes back, jitter below the bar.  One test is built from
real data - the SAM3 census frame-times (``out/scan30/sam3_census.json``) - and pins
what the gate actually produces on it, which is nothing, with the reason measured.

The thresholds the gate uses are geometry (a ball is 3.7-11.1 px here), the
detector's frame period and the repo's own measured pot radius; none of them is
tuned against the 25 known movers or the emptied event queue.  These tests pin the
*bars* as much as the outcomes, so a later "fix" that moves one has to say so.

Beware one geometry trap in these fixtures: the left-side pocket centre is
(486.8, 396.3) with a 19.3 px radius, so a ball parked at (500, 400) is *inside a
pocket* - a rest fixture belongs at :data:`OPEN`, which is 163 px from the nearest
pocket.
"""
import json
import math
import unittest
from collections import Counter
from pathlib import Path

from src.shot_pot_gate import (BALL_DIAMETER_NATIVE_PX, CANON_H, CANON_W, OCC_DENSE_MIN,
                               POCKETS_MM, POCKET_R_MM, VOD30_POCKETS_PX, VOD30_REFERENCE_QUAD,
                               BreakGroup, GateThresholds, Occlusion, PotEvent, Rejection, Sample,
                               ShotEvent, Track, classify, default_pocket_model, homography,
                               pocket_pixels, project, track_events)

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "out" / "scan30" / "sam3_census.json"
SEGMENTS = ROOT / "out" / "calib_vod30_segments.json"
ANCHORS = ROOT / "out" / "pid_anchors_vod30.json"

FPS = 30.0
DT = 1.0 / FPS
PERSIST = 1.5                          # observation after a disappearance, > persistence_s
OPEN = (690.0, 445.0)                  # open cloth: 163 px from the nearest pocket centre
ONSET_TOL = 3.0                        # px/s slack on an expected interval speed
#: the dense run's cloth quad in its own 960x540 frame (out/dense-events/segment-1350-1650.json,
#: ``thresholds.cloth_quad`` = the native reference quad x 0.75)
WORK_SIZE = (960, 540)
WORK_QUAD = ((399.0, 242.25), (600.0, 243.0), (747.75, 426.75), (288.0, 422.25))
POT_MAX_TRAVEL_PX = 400.0              # a pot track's walk stays inside the frame


# --------------------------------------------------------------- track builders

def sample(i: int, x: float, y: float, occluded: bool = False, conf: float = 0.9,
           t: float | None = None) -> Sample:
    return Sample(i, i * DT if t is None else t, x, y, conf, occluded)


def still(x: float, y: float, n: int, start: int = 0, occluded: bool = False) -> list[Sample]:
    """``n`` samples of a ball that does not move."""
    return [sample(start + k, x, y, occluded) for k in range(n)]


def moving(x: float, y: float, dx: float, dy: float, n: int, start: int,
           px: float = 4.0, occluded: bool = False) -> list[Sample]:
    """``n`` samples along the unit direction ``(dx, dy)``, ``px`` pixels apart."""
    return [sample(start + k, x + dx * px * k, y + dy * px * k, occluded) for k in range(n)]


def approach(pocket, x0: float, y0: float, start: int, n: int = 25,
             finish: float = 0.95) -> list[Sample]:
    """Samples walking from ``(x0, y0)`` to just inside the pocket radius.

    ``pocket`` may be a :class:`Pocket` or any ``(x, y)`` pair, so a test can also
    aim at a point outside the pocket (the pixel-radius-but-not-millimetre case).
    """
    tx, ty = (pocket.x, pocket.y) if hasattr(pocket, "x") else (pocket[0], pocket[1])
    ex = x0 + (tx - x0) * finish
    ey = y0 + (ty - y0) * finish
    return [sample(start + k, x0 + (ex - x0) * k / n, y0 + (ey - y0) * k / n)
            for k in range(1, n + 1)]


#: a pot fixture starts here in canonical millimetres: the middle of the table
TABLE_MIDDLE_MM = (CANON_W / 2.0, CANON_H / 2.0)
#: ... and stops this far from the pocket centre, well inside the 100 mm gate in
#: every direction (the repo's measured vanished-ball cluster is 39-86 mm)
POT_END_MM = 40.0


def mm_walk(model, pocket_name: str, end_mm: float = POT_END_MM,
            start_mm: tuple[float, float] = TABLE_MIDDLE_MM, start: int = 20,
            n: int = 25) -> list[Sample]:
    """A straight walk in canonical millimetres, sampled in the model's pixels.

    Pot fixtures are built in the frame the rule is stated in (millimetres), so the
    final position is inside the gate whatever direction it comes from - a walk
    aimed in *pixels* at a corner pocket can end 250 mm away.
    """
    pocket = model.by_name(pocket_name)
    sx, sy = start_mm
    cx, cy = pocket.mm
    distance = math.hypot(cx - sx, cy - sy)
    ux, uy = (cx - sx) / distance, (cy - sy) / distance
    ex, ey = cx - ux * end_mm, cy - uy * end_mm
    points = [project(model.mm_to_px, (sx + (ex - sx) * k / n, sy + (ey - sy) * k / n))
              for k in range(1, n + 1)]
    return [sample(start + k, x, y) for k, (x, y) in enumerate(points)]


def pot_track(name: str, pocket_name: str, model=None, rest: int = 20,
              end_mm: float = POT_END_MM) -> Track:
    """A ball that sits still and then rolls into a pocket (in millimetres)."""
    model = model or default_pocket_model()
    start_px = project(model.mm_to_px, TABLE_MIDDLE_MM)
    walk = mm_walk(model, pocket_name, end_mm=end_mm, start=rest)
    rows = still(start_px[0], start_px[1], walk[0].frame_index) + walk
    return Track(name, tuple(rows))


def report_for(track: Track, **kw):
    """Classify one track with an observation window that outlives it."""
    kw.setdefault("observed_until_t",
                  (track.samples[-1].t if track.samples else 0.0) + PERSIST)
    return classify([track], **kw)


def codes(records) -> set[str]:
    return {r.code for r in records}


# --------------------------------------------------------------- shared checks

class GateTestCase(unittest.TestCase):
    """Shared assertions: nothing an examined track produces may be silent."""

    def assert_evidence_complete(self, report) -> None:
        for shot in report.shots:
            self.assertIsInstance(shot, ShotEvent)
            self.assertTrue(shot.samples_used, f"shot {shot.ball_id} carries no samples")
            self.assertTrue(shot.thresholds, f"shot {shot.ball_id} carries no thresholds")
        for rec in list(report.pots) + list(report.rejections):
            self.assertIsInstance(rec, PotEvent if rec.kind == "pot" else Rejection)
            self.assertTrue(rec.samples_used, f"{rec.kind} {rec.ball_id} carries no samples")
            self.assertTrue(rec.thresholds, f"{rec.kind} {rec.ball_id} carries no thresholds")
            self.assertTrue(rec.reason, f"{rec.kind} {rec.ball_id} carries no reason")

    def assert_json_safe(self, report) -> None:
        json.dumps(report.as_dict(), allow_nan=False)


# ------------------------------------------------------------------- geometry

class PocketGeometryTests(GateTestCase):
    """The pocket model is the verified reference geometry, re-derived, not invented."""

    def test_pinned_table_reproduces_from_the_reference_quad(self):
        derived = pocket_pixels(VOD30_REFERENCE_QUAD)
        self.assertEqual(set(derived), set(POCKETS_MM))
        for name, row in VOD30_POCKETS_PX.items():
            px, py = derived[name]["px"]
            self.assertAlmostEqual(px, row["px"][0], delta=0.05, msg=name)
            self.assertAlmostEqual(py, row["px"][1], delta=0.05, msg=name)
            self.assertAlmostEqual(derived[name]["px_per_mm"], row["px_per_mm"], delta=1e-4, msg=name)

    def test_homography_round_trips_the_cloth_corners(self):
        h = homography([(0.0, 0.0), (CANON_W - 1, 0.0), (CANON_W - 1, CANON_H - 1),
                        (0.0, CANON_H - 1)], VOD30_REFERENCE_QUAD)
        for corner, want in zip([(0.0, 0.0), (CANON_W - 1, 0.0), (CANON_W - 1, CANON_H - 1),
                                 (0.0, CANON_H - 1)], VOD30_REFERENCE_QUAD):
            got = project(h, corner)
            self.assertAlmostEqual(got[0], want[0], delta=1e-6)
            self.assertAlmostEqual(got[1], want[1], delta=1e-6)

    def test_reference_quad_is_the_measured_segment_quad(self):
        if not SEGMENTS.is_file():
            self.skipTest("no segment artifact in this tree")
        payload = json.loads(SEGMENTS.read_text())
        segment = payload["segments"][0]
        self.assertEqual(segment["source"], "human_anchors")
        for got, want in zip(tuple(map(tuple, segment["quad_px"])), VOD30_REFERENCE_QUAD):
            self.assertAlmostEqual(got[0], want[0], delta=0.01)
            self.assertAlmostEqual(got[1], want[1], delta=0.01)

    def test_derived_pockets_agree_with_the_independent_hand_anchors(self):
        """Two independent human measurements must land on the same six places."""
        if not ANCHORS.is_file():
            self.skipTest("no hand anchors in this tree")
        anchors = [tuple(map(float, p)) for p in json.loads(ANCHORS.read_text())["anchors"]["70.0"]]
        order = ["head-left", "head-right", "foot-right", "foot-left", "left-side", "right-side"]
        model = default_pocket_model()
        distances = [math.dist((model.by_name(n).x, model.by_name(n).y), a)
                     for n, a in zip(order, anchors)]
        self.assertLess(max(distances[:4]), 1.0, "corner pockets must sit on the anchors")
        self.assertLess(max(distances[4:]), 8.0, "side pockets must sit near the anchors")
        # the documented cross-check: 0.0-0.7 px corners, 6.8/4.9 px side pockets
        self.assertAlmostEqual(distances[4], 6.8, delta=0.3)
        self.assertAlmostEqual(distances[5], 4.9, delta=0.3)

    def test_radius_is_local_because_the_far_end_is_foreshortened(self):
        model = default_pocket_model()
        head = model.by_name("head-left").radius_px
        foot = model.by_name("foot-right").radius_px
        self.assertGreater(foot, 2.5 * head, "one global pixel radius would be wrong at both ends")
        for pocket in model.pockets:
            self.assertAlmostEqual(pocket.radius_px,
                                   POCKET_R_MM * VOD30_POCKETS_PX[pocket.name]["px_per_mm"],
                                   delta=0.01)
        # the measured mm values are what the repo measured: 12.9 px head, 38.8 px foot
        self.assertAlmostEqual(head, 12.93, delta=0.05)
        self.assertAlmostEqual(foot, 38.78, delta=0.05)

    def test_pocket_names_and_places_match_event_gates(self):
        from src.event_gates import POCKETS_MM as OTHER
        self.assertEqual(set(POCKETS_MM), set(OTHER))
        for name, mm in POCKETS_MM.items():
            self.assertAlmostEqual(mm[0], OTHER[name][0])
            self.assertAlmostEqual(mm[1], OTHER[name][1])

    def test_nearest_and_inside_disagree_outside_the_radius(self):
        model = default_pocket_model()
        pocket, dist = model.nearest(*OPEN)
        self.assertIsNotNone(pocket)
        inside, _ = model.inside(*OPEN)
        self.assertIsNone(inside)
        self.assertGreater(dist, pocket.radius_px)

    def test_a_second_quad_is_projected_not_reused(self):
        quad = [(600.0, 400.0), (700.0, 400.0), (700.0, 600.0), (600.0, 600.0)]
        model = default_pocket_model(quad=quad, pocket_r_mm=100.0)
        # the canonical destination is CANON_W-1 / CANON_H-1, so the far corners land
        # a fraction of a pixel past the given corner - that is a projection, not a copy
        self.assertAlmostEqual(model.by_name("head-left").x, 600.0, delta=0.2)
        self.assertAlmostEqual(model.by_name("head-left").y, 400.0, delta=0.2)
        self.assertAlmostEqual(model.by_name("head-right").x, 700.0, delta=0.2)
        self.assertAlmostEqual(model.by_name("foot-right").y, 600.0, delta=0.2)
        self.assertNotAlmostEqual(model.by_name("head-left").x, VOD30_POCKETS_PX["head-left"]["px"][0])


class OcclusionContractTests(GateTestCase):
    """The channel is an input; flags and a distribution answer different questions."""

    def test_threshold_is_the_bar_motion_scan_uses(self):
        from src.motion_scan import OCC_DENSE_MIN as MEASURED
        self.assertEqual(OCC_DENSE_MIN, MEASURED)

    def test_shares_become_flags_at_the_threshold(self):
        occ = Occlusion.from_shares([1.0, 2.0], [0.29, 0.30])
        self.assertEqual(occ.mode, "series")
        self.assertEqual(occ.readings(1.0, 2.0), [False, True])

    def test_no_reading_is_silent_not_clear(self):
        self.assertEqual(Occlusion.none().status(0.0, 1.0), "silent")
        occ = Occlusion.from_flags([5.0], [False])
        self.assertEqual(occ.status(0.0, 1.0), "silent")
        self.assertEqual(occ.status(5.0, 5.0), "clear")

    def test_flags_judge_the_last_sighting_and_a_series_the_whole_window(self):
        flagged = Occlusion.from_flags([10.0], [False])
        self.assertEqual(flagged.status_at_disappearance(10.0, 11.5), "clear")
        series = Occlusion.from_shares([11.0], [0.9])
        self.assertEqual(series.status_at_disappearance(10.0, 11.5), "occluded")
        series_gap = Occlusion.from_shares([5.0], [0.9])
        self.assertEqual(series_gap.status_at_disappearance(10.0, 11.5), "silent")

    def test_a_flag_built_from_samples_carries_the_sample_times(self):
        occ = Occlusion.from_samples([sample(0, 1.0, 1.0), sample(1, 1.0, 1.0, occluded=True)])
        self.assertEqual(occ.times, (0.0, DT))
        self.assertEqual(occ.covered, (False, True))
        self.assertEqual(occ.source, "track_flags")


# ------------------------------------------------------------------ shot rule

class ShotRuleTests(GateTestCase):
    """Onset, direction, peak speed, duration - and the refusals that look like one."""

    def test_a_single_shot_reports_onset_direction_peak_and_duration(self):
        # ball still for 0.63 s, then 25 intervals of a straight walk in mm from the
        # middle of the table towards the head-left pocket (155.8 px of travel)
        track = pot_track("cue", "head-left")
        run = track.samples[19:]                       # the last still sample, then the walk
        measured = [math.dist((a.x, a.y), (b.x, b.y)) / (b.t - a.t)
                    for a, b in zip(run, run[1:])]
        report = report_for(track)
        self.assertEqual(len(report.shots), 1)
        shot = report.shots[0]
        self.assertEqual(shot.kind, "shot")
        self.assertEqual(shot.ball_id, "cue")
        self.assertAlmostEqual(shot.onset_t, 19 * DT, delta=DT)          # the last still sample
        self.assertEqual(shot.onset_frame_index, 19)
        self.assertAlmostEqual(shot.direction_deg, 207.9, delta=1.0)     # left and up, image space
        self.assertAlmostEqual(shot.peak_speed_px_s, max(measured), delta=ONSET_TOL)
        self.assertGreater(shot.duration_s, 0.5)
        self.assertGreater(shot.net_displacement_px, 100.0)
        self.assertLessEqual(shot.path_length_px, shot.net_displacement_px * 1.05)
        self.assertGreaterEqual(shot.rest_window_measured_s, GateThresholds().rest_window_s)
        self.assertGreaterEqual(shot.rest_intervals, GateThresholds().rest_min_intervals)
        self.assertLessEqual(shot.max_rest_speed_px_s, GateThresholds().rest_speed_px_s)
        self.assertTrue(shot.ends_in_pocket)
        self.assertEqual(shot.end_pocket, "head-left")
        self.assertFalse(shot.endless_roll)
        self.assertIn("motion_speed_px_s", shot.thresholds)
        self.assertIn("onset_intervals", shot.thresholds)
        # the evidence is the still stretch plus the run, in order
        used = [s.frame_index for s in shot.samples_used]
        self.assertEqual(used, sorted(used))
        self.assertIn(19, used)
        self.assertEqual(used[-1], track.samples[-1].frame_index)
        self.assert_evidence_complete(report)
        self.assert_json_safe(report)

    def test_direction_is_image_space_x_right_y_down(self):
        for dx, dy, want in [(1, 0, 0.0), (0, 1, 90.0), (-1, 0, 180.0), (0, -1, 270.0)]:
            # 15 intervals of 4 px = 60 px of net travel, past the 2-diameter bar
            track = Track("b", tuple(still(*OPEN, 20) + moving(OPEN[0], OPEN[1], dx, dy, 16, 20)))
            report = report_for(track)
            self.assertEqual(len(report.shots), 1)
            self.assertAlmostEqual(report.shots[0].direction_deg, want, delta=1e-6)

    def test_a_stationary_ball_produces_no_shot_and_says_so(self):
        report = report_for(Track("b", tuple(still(*OPEN, 60))))
        self.assertEqual(report.shots, [])
        self.assertEqual(report.pots, [])
        self.assertIn("no_motion_onset", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "no_motion_onset"][0]
        self.assertLessEqual(record.numbers["max_interval_speed_px_s"],
                             GateThresholds().motion_speed_px_s)
        self.assert_evidence_complete(report)
        # with no observation window the end of the track is refused by name too
        closed = classify([Track("b", tuple(still(*OPEN, 60)))])
        self.assertEqual(codes(closed.rejections), {"no_motion_onset", "track_ends_at_window_end"})

    def test_jitter_below_the_bar_produces_nothing(self):
        # +-0.4 px per frame: 12 px/s against a 40 px/s bar, six times over
        rows = [sample(i, OPEN[0] + (0.4 if i % 2 else -0.4), OPEN[1] + (0.4 if i % 3 else -0.4))
                for i in range(90)]
        report = report_for(Track("b", tuple(rows)))
        self.assertEqual(report.shots, [])
        self.assertEqual(report.pots, [])
        self.assertIn("no_motion_onset", codes(report.rejections))
        self.assertTrue(codes(report.rejections) <=
                        {"no_motion_onset", "disappeared_outside_pocket", "track_ends_at_window_end"})
        record = [r for r in report.rejections if r.code == "no_motion_onset"][0]
        self.assertLess(record.numbers["max_interval_speed_px_s"],
                        GateThresholds().motion_speed_px_s)
        self.assert_json_safe(report)

    def test_a_single_frame_jump_is_not_a_sustained_onset(self):
        # two above-bar intervals only: the shape of an identity jump
        rows = still(*OPEN, 20) + [sample(20, OPEN[0] + 20, OPEN[1]),
                                   sample(21, OPEN[0] + 60, OPEN[1])]
        report = report_for(Track("b", tuple(rows)))
        self.assertEqual(report.shots, [])
        self.assertIn("motion_too_short", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "motion_too_short"][0]
        self.assertEqual(record.numbers["burst_intervals"], 2)
        self.assertLess(record.numbers["burst_intervals"], GateThresholds().onset_intervals)

    def test_sustained_motion_needs_consecutive_intervals_not_one_long_jump(self):
        # one interval of 30 px (900 px/s) then nothing: a jump, not motion
        rows = still(*OPEN, 20) + [sample(20, OPEN[0] + 30, OPEN[1])]
        report = report_for(Track("b", tuple(rows)))
        self.assertEqual(report.shots, [])
        self.assertIn("motion_too_short", codes(report.rejections))

    def test_a_track_that_starts_already_moving_is_not_a_shot(self):
        track = Track("b", tuple(sample(k, 600 + 6 * k, 430) for k in range(20)))
        report = report_for(track)
        self.assertEqual(report.shots, [])
        self.assertIn("no_still_stretch", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "no_still_stretch"][0]
        self.assertLess(record.numbers["rest_window_measured_s"],
                        GateThresholds().rest_window_s)

    def test_too_short_a_rest_is_not_a_shot(self):
        # the move itself is real (80 px net), so the rest stretch is what fails
        rows = still(*OPEN, 5) + moving(OPEN[0], OPEN[1], 1, 0, 17, 5, px=5.0)
        report = report_for(Track("b", tuple(rows)))
        self.assertEqual(report.shots, [])
        self.assertIn("no_still_stretch", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "no_still_stretch"][0]
        # the window is what fails here, not the interval count
        self.assertLess(record.numbers["rest_window_measured_s"], GateThresholds().rest_window_s)
        self.assertGreaterEqual(record.numbers["rest_intervals"], GateThresholds().rest_min_intervals)

    def test_a_gap_breaks_a_run(self):
        # 2 hot intervals, a 0.39 s gap, 2 hot intervals: neither burst is sustained
        rows = still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 3, 20, px=12.0)
        rows += [sample(32 + k, OPEN[0] + 150 + 12 * k, OPEN[1], t=(32 + k) * DT + 0.2)
                 for k in range(3)]
        report = report_for(Track("b", tuple(rows)))
        self.assertEqual(report.shots, [])
        self.assertEqual([r.numbers["burst_intervals"] for r in report.rejections
                          if r.code == "motion_too_short"], [2, 2])

    def test_a_rolling_ball_that_never_reaches_a_pocket_is_a_shot_but_never_a_pot(self):
        rows = still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 20, 20, px=6.0)
        report = report_for(Track("b", tuple(rows)))
        self.assertEqual(len(report.shots), 1)
        self.assertTrue(report.shots[0].endless_roll)
        self.assertFalse(report.shots[0].ends_in_pocket)
        self.assertEqual(report.pots, [])
        self.assertIn("roll_without_pocket", codes(report.rejections))

    def test_thresholds_are_parameters_with_the_documented_defaults(self):
        th = GateThresholds()
        self.assertEqual(th.rest_speed_px_s, 6.0)
        self.assertEqual(th.rest_window_s, 0.5)
        self.assertEqual(th.rest_min_intervals, 2)
        self.assertEqual(th.motion_speed_px_s, 40.0)
        self.assertEqual(th.onset_intervals, 3)
        self.assertEqual(th.max_gap_s, 0.25)
        self.assertEqual(th.pocket_r_mm, POCKET_R_MM)
        self.assertEqual(th.persistence_s, 1.0)
        self.assertEqual(th.vanish_min_s, 0.4)
        self.assertEqual(th.vanish_cadence_multiple, 4.0)
        self.assertEqual(th.break_min_balls, 3)
        self.assertEqual(th.simultaneous_window_s, 0.15)
        self.assertEqual(th.edge_margin_px, 20.0)
        self.assertEqual(th.min_net_displacement_diameters, 2.0)
        self.assertIsNone(th.ball_diameter_px)
        self.assertEqual(th.frame_scale, 1.0)
        self.assertIsNone(th.frame_size)
        self.assertIsNone(th.cloth_quad)
        self.assertEqual(th.min_confidence, 0.0)
        # the ball's size is resolved in the frame the track is given in
        self.assertEqual(GateThresholds().ball_diameter(), BALL_DIAMETER_NATIVE_PX)
        self.assertAlmostEqual(GateThresholds(frame_scale=0.75).ball_diameter(), 13.8, delta=1e-9)
        self.assertAlmostEqual(GateThresholds(frame_size=(960, 540)).ball_diameter(), 13.8,
                               delta=1e-9)
        self.assertEqual(GateThresholds(ball_diameter_px=11.0).ball_diameter(), 11.0)
        self.assertEqual(GateThresholds(ball_diameter_px=11.0).min_net_displacement_px(), 22.0)
        self.assertAlmostEqual(GateThresholds(frame_size=(960, 540)).min_net_displacement_px(),
                               27.6, delta=1e-9)
        # a raised bar really is used
        strict = GateThresholds(motion_speed_px_s=500.0)
        rows = still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 20, 20, px=4.0)
        self.assertEqual(report_for(Track("b", tuple(rows)), thresholds=strict).shots, [])
        self.assertEqual(len(report_for(Track("b", tuple(rows))).shots), 1)

    def test_motion_that_returns_to_its_start_is_an_oscillation_not_a_shot(self):
        """A run that ends where it began did not go anywhere, whatever its speed."""
        rows = (still(*OPEN, 20)
                + [sample(20, OPEN[0] + 8, OPEN[1]), sample(21, OPEN[0] + 12, OPEN[1]),
                   sample(22, OPEN[0] + 4, OPEN[1]), sample(23, OPEN[0], OPEN[1])])
        report = report_for(Track("b", tuple(rows)))
        self.assertEqual(report.shots, [])
        self.assertIn("oscillation_no_net_travel", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "oscillation_no_net_travel"][0]
        self.assertEqual(record.numbers["net_displacement_px"], 0.0)
        self.assertGreater(record.numbers["path_length_px"], 0.0)
        self.assert_json_safe(report)

    def test_an_identity_that_jitters_inside_its_own_footprint_is_not_a_shot(self):
        """The two shapes the served queue carried, at the dense run's 960x540 frame.

        Both exceed the speed rule on every interval; neither goes anywhere.  The bar
        is 2 ball diameters and the frame resolves a ball to 18.4 x 960/1280 = 13.8 px,
        so 27.6 px of net travel is required and neither shape comes close.
        """
        thresholds = GateThresholds(frame_size=(960, 540))
        self.assertAlmostEqual(thresholds.ball_diameter(), 13.8, delta=0.01)
        self.assertAlmostEqual(thresholds.min_net_displacement_px(), 27.6, delta=0.02)
        # shape of the served white id 9001: peak 303.6 px/s, path 80.6 px, net 0.2 px
        jitter = still(*OPEN, 20)
        x = OPEN[0]
        for k in range(28):
            x += 2.0 if k % 2 == 0 else -2.0
            jitter.append(sample(20 + k, x, OPEN[1]))
        report = report_for(Track("white", tuple(jitter)), thresholds=thresholds)
        self.assertEqual(report.shots, [])
        record = [r for r in report.rejections if r.code == "oscillation_no_net_travel"][0]
        self.assertLessEqual(record.numbers["net_displacement_px"], 2.0)
        self.assertGreater(record.numbers["path_length_px"], 50.0)
        self.assertLess(record.numbers["net_displacement_diameters"], 2.0)
        self.assertGreater(record.numbers["peak_speed_px_s"], thresholds.motion_speed_px_s)
        self.assertEqual(record.numbers["net_over_path"], 0.0)
        self.assertIsNone(record.numbers["path_over_net"])   # no ratio when net is 0
        # shape of the served blue id 9003: path 59.9 px, net 19.7 px = 1.43 diameters
        drift = still(*OPEN, 20)
        x, y = OPEN
        for k in range(15):
            x += 4.0 if k % 2 == 0 else -3.5
            y += 1.4
            drift.append(sample(20 + k, x, y))
        report2 = report_for(Track("blue", tuple(drift)), thresholds=thresholds)
        self.assertEqual(report2.shots, [])
        record2 = [r for r in report2.rejections if r.code == "oscillation_no_net_travel"][0]
        self.assertLess(record2.numbers["net_displacement_px"],
                        thresholds.min_net_displacement_px())
        self.assertGreater(record2.numbers["path_length_px"], 50.0)
        # ... and the real move of the same run (net 159.1 px over a 159.9 px path)
        real = still(*OPEN, 291) + moving(OPEN[0], OPEN[1], 1, 0, 23, 291, px=7.2)
        report3 = report_for(Track("blue", tuple(real)), thresholds=thresholds)
        self.assertEqual(len(report3.shots), 1)
        self.assertGreater(report3.shots[0].net_displacement_px, 4 * thresholds.ball_diameter())
        for name, rep in (("white", report), ("blue", report2), ("real move", report3)):
            with self.subTest(shape=name):
                self.assert_evidence_complete(rep)
                self.assert_json_safe(rep)
        self.assertIn("oscillation_no_net_travel", codes(report.rejections))
        self.assertIn("oscillation_no_net_travel", codes(report2.rejections))


# ------------------------------------------------------------------- pot rule

class PotRuleTests(GateTestCase):
    """Termination inside a pocket radius is a pot only with full evidence."""

    def test_a_pot_into_each_of_the_six_pockets(self):
        model = default_pocket_model()
        for name in POCKETS_MM:
            with self.subTest(pocket=name):
                pocket = model.by_name(name)
                report = report_for(pot_track("obj", pocket.name))
                pots = [p for p in report.pots if p.is_pot]
                self.assertEqual(len(pots), 1,
                                 f"{name}: {[(p.verdict, p.reason) for p in report.pots]}")
                pot = pots[0]
                self.assertEqual(pot.pocket, name)
                self.assertEqual(pot.verdict, "pot")
                self.assertEqual(pot.reason, "inside_pocket_persistence_clear")
                self.assertLessEqual(pot.distance_px, pot.radius_px)
                # both units are reported, and the millimetre test is the authority
                self.assertEqual(pot.pocket_test, "mm")
                self.assertLessEqual(pot.distance_mm, pot.radius_mm)
                self.assertAlmostEqual(pot.radius_mm, POCKET_R_MM)
                self.assertTrue(pot.inside_mm)
                self.assertTrue(pot.inside_px)
                self.assertFalse(pot.pocket_test_disagrees)
                self.assertIsNotNone(pot.last_mm)
                self.assertEqual(tuple(pot.pocket_px), (pocket.x, pocket.y))
                self.assertAlmostEqual(pot.persistence_s, GateThresholds().persistence_s)
                self.assertGreaterEqual(pot.gap_s, pot.persistence_s)
                self.assertFalse(pot.internal_gap)
                self.assertEqual(pot.occlusion_status, "clear")
                self.assertEqual(pot.occlusion_source, "track_flags")
                self.assertFalse(pot.parked_in_jaws_possible)
                self.assertIn("pocket_r_mm", pot.thresholds)
                self.assertIn("vanish_gap_s", pot.thresholds)
                self.assert_evidence_complete(report)
                self.assert_json_safe(report)

    def test_a_ball_ending_inside_the_pixel_radius_but_outside_the_millimetre_gate(self):
        """The served candidate: 9.62 px from the centre, 148 mm against a 100 mm gate.

        The pixel radius cannot follow this projection, so the millimetre test is the
        authority and the disagreement is the reason - not a pot-shaped candidate.
        """
        model = default_pocket_model(quad=WORK_QUAD, pocket_r_mm=POCKET_R_MM)
        pocket = model.by_name("left-side")
        self.assertAlmostEqual(pocket.radius_px, 14.46, delta=0.02)
        target = (pocket.x + 3.2, pocket.y + 9.08)      # 9.62 px from the centre
        rows = (still(*OPEN, 20)
                + approach(target, OPEN[0], OPEN[1], 20, n=25, finish=1.0))
        report = report_for(Track("t265-blue", tuple(rows)),
                            thresholds=GateThresholds(frame_size=list(WORK_SIZE),
                                                      cloth_quad=list(WORK_QUAD)))
        self.assertEqual(report.pots, [], "a pocket-shaped candidate must not survive the mm test")
        self.assertIn("pocket_test_disagrees_px_vs_mm", codes(report.rejections))
        record = [r for r in report.rejections
                  if r.code == "pocket_test_disagrees_px_vs_mm"][0]
        self.assertAlmostEqual(record.numbers["distance_px"], 9.62, delta=0.05)
        self.assertAlmostEqual(record.numbers["radius_px"], 14.46, delta=0.02)
        self.assertAlmostEqual(record.numbers["distance_mm"], 148.0, delta=1.5)
        self.assertEqual(record.numbers["radius_mm"], 100.0)
        self.assertTrue(record.numbers["inside_px"])
        self.assertFalse(record.numbers["inside_mm"])
        self.assertFalse(record.numbers["inside"])
        self.assertEqual(record.numbers["pocket"], "left-side")
        self.assertAlmostEqual(record.numbers["ppx_vs_mm_ratio"], 1.485, delta=0.02)
        self.assert_evidence_complete(report)
        self.assert_json_safe(report)

    def test_the_same_track_inside_the_millimetre_gate_is_a_pot_candidate_again(self):
        """Half a radius towards the rail is 74 mm: inside, and both tests agree."""
        model = default_pocket_model(quad=WORK_QUAD, pocket_r_mm=POCKET_R_MM)
        pocket = model.by_name("left-side")
        target = (pocket.x + 1.6, pocket.y + 4.54)      # 4.81 px = half the pixel radius
        rows = (still(*OPEN, 20)
                + approach(target, OPEN[0], OPEN[1], 20, n=25, finish=1.0))
        report = report_for(Track("obj", tuple(rows)),
                            thresholds=GateThresholds(frame_size=list(WORK_SIZE),
                                                      cloth_quad=list(WORK_QUAD)))
        self.assertEqual([p.verdict for p in report.pots], ["pot"])
        pot = report.pots[0]
        self.assertEqual(pot.pocket_test, "mm")
        self.assertLessEqual(pot.distance_mm, pot.radius_mm)
        self.assertTrue(pot.inside_px)
        self.assertFalse(pot.pocket_test_disagrees)

    def test_a_foot_rail_pocket_radius_agrees_with_the_millimetre_test(self):
        """The foot pockets are where the projection compresses mm/px the most.

        A single scalar pixel radius cannot be the image of the 100 mm disc: the true
        footprint is an ellipse whose axes differ by ~2.5x here.  What must hold is
        that the millimetre test is exact - every canonical point at 100 mm from the
        pocket centre measures 100 mm, whatever its direction - and that the scalar
        radius is reported next to it rather than deciding.
        """
        model = default_pocket_model(quad=WORK_QUAD, pocket_r_mm=POCKET_R_MM)
        foot = model.by_name("foot-right")
        head = model.by_name("head-left")
        long_axis, short_axis = foot.radius_px_axes()
        self.assertAlmostEqual(foot.radius_px, 29.09, delta=0.02)     # 100 mm at the mean scale
        self.assertAlmostEqual(long_axis, 39.72, delta=0.05)
        self.assertAlmostEqual(short_axis, 15.30, delta=0.05)
        self.assertGreater(long_axis / short_axis, 2.4)
        self.assertGreater(head.radius_px_axes()[0] / head.radius_px_axes()[1], 4.0)
        # the mean scale itself changes ~3x between the rails (the reported reason)
        self.assertAlmostEqual(foot.radius_px / head.radius_px, 3.0, delta=0.05)
        read_inside, read_outside, scalar_agrees = 0, 0, 0
        for step in range(72):
            angle = 2.0 * math.pi * step / 72.0
            mm = (foot.mm[0] + 0.99 * POCKET_R_MM * math.cos(angle),
                  foot.mm[1] + 0.99 * POCKET_R_MM * math.sin(angle))
            px = project(model.mm_to_px, mm)
            measured = model.measure(*px)
            self.assertAlmostEqual(measured.distance_mm, 0.99 * POCKET_R_MM, delta=0.5,
                                   msg=f"angle {step}: the mm test must be exact")
            self.assertTrue(measured.inside_mm)
            self.assertEqual(measured.pocket.name, "foot-right")
            read_inside += 1 if measured.inside_px else 0
            scalar_agrees += 1 if measured.inside_px == measured.inside_mm else 0
        # the scalar radius calls some of these inside and some outside: it is a
        # diagnostic, and the millimetre test is what decides
        self.assertTrue(0 < read_inside < 72)
        self.assertLess(scalar_agrees, 72)
        outside_mm = project(model.mm_to_px,
                             (foot.mm[0] - 1.05 * POCKET_R_MM, foot.mm[1]))
        self.assertFalse(model.measure(*outside_mm).inside)
        self.assertFalse(model.measure(*outside_mm).inside_mm)

    def test_a_ball_vanishing_under_the_occlusion_flag_is_unknown_never_a_pot(self):
        rows = list(pot_track("obj", "head-left").samples)   # ends 40 mm inside the gate
        last = rows[-1]
        rows[-1] = Sample(last.frame_index, last.t, last.x, last.y, last.confidence, True)
        report = report_for(Track("obj", tuple(rows)))
        self.assertEqual([p for p in report.pots if p.is_pot], [])
        self.assertEqual(len(report.pots), 1)
        pot = report.pots[0]
        self.assertEqual(pot.verdict, "unknown")
        self.assertEqual(pot.reason, "cloth_occluded_at_disappearance")
        self.assertEqual(pot.occlusion_status, "occluded")
        self.assertEqual(pot.pocket, "head-left")
        self.assertEqual(pot.occlusion_source, "track_flags")
        self.assertTrue(pot.inside_mm)                    # it was in the pocket in mm ...
        self.assertIn("occlusion_mode", pot.thresholds)
        self.assert_evidence_complete(report)

    def test_an_occlusion_series_over_the_persistence_window_blocks_a_pot(self):
        pocket = default_pocket_model().by_name("head-left")
        track = pot_track("obj", pocket.name)
        series = Occlusion.from_shares([track.samples[-1].t + 0.4], [0.55])
        report = report_for(track, occlusion=series)
        self.assertEqual([p for p in report.pots if p.is_pot], [])
        self.assertEqual(report.pots[0].verdict, "unknown")
        self.assertEqual(report.pots[0].reason, "cloth_occluded_at_disappearance")
        self.assertEqual(report.pots[0].occlusion_status, "occluded")
        self.assertEqual(report.pots[0].occlusion_source, "series")

    def test_a_clear_series_still_gives_a_pot(self):
        pocket = default_pocket_model().by_name("foot-right")
        track = pot_track("obj", pocket.name)
        series = Occlusion.from_shares([track.samples[-1].t + 0.3, track.samples[-1].t + 1.1],
                                       [0.04, 0.09])
        report = report_for(track, occlusion=series)
        self.assertEqual([p.verdict for p in report.pots], ["pot"])
        self.assertEqual(report.pots[0].occlusion_status, "clear")

    def test_a_silent_occlusion_channel_is_unknown_not_a_pot(self):
        pocket = default_pocket_model().by_name("head-right")
        track = pot_track("obj", pocket.name)
        report = report_for(track, occlusion=Occlusion.none())
        self.assertEqual([p.verdict for p in report.pots], ["unknown"])
        self.assertEqual(report.pots[0].reason, "occlusion_channel_silent")
        self.assertEqual(report.pots[0].occlusion_status, "silent")

    def test_a_persistence_window_the_caller_did_not_state_is_unknown(self):
        pocket = default_pocket_model().by_name("head-left")
        track = pot_track("obj", pocket.name)
        report = classify([track])                     # observation ends with the track
        self.assertEqual([p for p in report.pots if p.is_pot], [])
        self.assertIn("track_ends_at_window_end", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "track_ends_at_window_end"][0]
        self.assertTrue(record.numbers["inside_pocket"])
        self.assertEqual(record.numbers["pocket"], "head-left")
        # ... and an explicit short window is refused for the same reason
        short = classify([track], observed_until_t=track.samples[-1].t + 0.5)
        self.assertEqual([p.verdict for p in short.pots], ["unknown"])
        self.assertEqual(short.pots[0].reason, "no_persistence_window")

    def test_a_ball_leaving_the_frame_edge_is_not_a_pot(self):
        rows = still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 25, 20, px=24.0)
        track = Track("obj", tuple(rows))              # last x = 1266, inside 20 px of 1280
        report = report_for(track, thresholds=GateThresholds(frame_size=(1280, 720)))
        self.assertEqual(report.pots, [])
        self.assertIn("left_frame_edge", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "left_frame_edge"][0]
        self.assertEqual(record.numbers["frame_size"], [1280, 720])
        self.assertGreater(record.numbers["last_xy"][0], 1280 - GateThresholds().edge_margin_px)

    def test_a_ball_leaving_the_cloth_is_not_a_pot(self):
        rows = still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 20, 20, px=48.0)
        track = Track("obj", tuple(rows))
        report = report_for(track, thresholds=GateThresholds(cloth_quad=VOD30_REFERENCE_QUAD))
        self.assertEqual(report.pots, [])
        self.assertIn("left_cloth", codes(report.rejections))

    def test_a_corner_pot_is_not_called_leaving_the_cloth(self):
        """A corner pocket sits *on* the cloth boundary: the pocket wins."""
        pocket = default_pocket_model().by_name("foot-right")
        report = report_for(pot_track("obj", pocket.name),
                            thresholds=GateThresholds(cloth_quad=VOD30_REFERENCE_QUAD,
                                                      frame_size=(1280, 720)))
        self.assertEqual([p.verdict for p in report.pots], ["pot"])
        self.assertNotIn("left_cloth", codes(report.rejections))
        self.assertNotIn("left_frame_edge", codes(report.rejections))

    def test_a_disappearance_on_open_cloth_is_a_rejection(self):
        rows = still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 12, 20, px=8.0)
        report = report_for(Track("obj", tuple(rows)))
        self.assertEqual(report.pots, [])
        self.assertIn("disappeared_outside_pocket", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "disappeared_outside_pocket"][0]
        self.assertGreater(record.numbers["distance_px"], record.numbers["radius_px"])
        self.assertIn(record.numbers["nearest_pocket"], POCKETS_MM)

    def test_a_ball_that_disappears_and_reappears_is_a_gap_not_a_pot(self):
        rows = (still(*OPEN, 20) + moving(OPEN[0], OPEN[1], -1, 0, 25, 20, px=4.0)
                + still(OPEN[0] - 100, OPEN[1], 15, start=60))
        report = report_for(Track("obj", tuple(rows)))
        self.assertEqual(report.pots, [])
        self.assertIn("reappeared_after_gap", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "reappeared_after_gap"][0]
        self.assertGreaterEqual(record.numbers["gap_s"], GateThresholds().vanish_min_s)
        self.assertFalse(record.numbers["identity_swap_suspected"])

    def test_an_identity_swap_inside_a_pocket_radius_is_unknown_not_a_pot(self):
        pocket = default_pocket_model().by_name("foot-right")
        rows = still(700.0, 400.0, 20) + approach(pocket, 700.0, 400.0, 20)
        last = rows[-1]
        rows = rows + [Sample(last.frame_index + 45, last.t + 1.5, last.x + 30, last.y + 20,
                              last.confidence, False)]
        report = report_for(Track("obj", tuple(rows)))
        self.assertEqual([p for p in report.pots if p.is_pot], [])
        reasons = [p.reason for p in report.pots]
        self.assertIn("reappeared_after_gap_inside_pocket", reasons)
        self.assertIn("prior_identity_swap_inside_pocket", reasons)
        self.assertTrue(all(p.identity_swap_suspected for p in report.pots))
        self.assertIn("reappeared_after_gap", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "reappeared_after_gap"][0]
        self.assertTrue(record.numbers["identity_swap_suspected"])

    def test_a_ball_parked_in_the_jaws_is_flagged_and_never_a_pot(self):
        pocket = default_pocket_model().by_name("left-side")
        rows = still(700.0, 400.0, 20) + approach(pocket, 700.0, 400.0, 20)
        rows = rows + still(rows[-1].x, rows[-1].y, 6, start=rows[-1].frame_index + 1)
        report = report_for(Track("obj", tuple(rows)))
        self.assertEqual([p for p in report.pots if p.is_pot], [])
        self.assertEqual([p.verdict for p in report.pots], ["unknown"])
        self.assertEqual(report.pots[0].reason, "at_rest_inside_pocket_radius")
        self.assertTrue(report.pots[0].parked_in_jaws_possible)
        self.assertLessEqual(report.pots[0].distance_px, report.pots[0].radius_px)
        self.assertEqual(report.pots[0].occlusion_status, "clear")
        self.assert_evidence_complete(report)

    def test_a_gap_shorter_than_the_vanish_bar_is_not_a_disappearance(self):
        pocket = default_pocket_model().by_name("head-left")
        rows = still(700.0, 400.0, 20) + approach(pocket, 700.0, 400.0, 20)
        last = rows[-1]
        rows = rows + [Sample(last.frame_index + 3, last.t + 0.1, last.x, last.y, 0.9, False)]
        report = report_for(Track("obj", tuple(rows)))
        self.assertEqual([p for p in report.pots if p.is_pot], [])
        self.assertNotIn("reappeared_after_gap", codes(report.rejections))

    def test_a_sparse_track_is_not_read_as_vanishing_between_two_samples(self):
        """0.5 s cadence: the vanish gap scales with the track's own cadence."""
        rows = [Sample(0, 0.0, 700.0, 400.0), Sample(15, 0.5, 690.0, 400.0),
                Sample(30, 1.0, 672.0, 396.0), Sample(45, 1.5, 646.0, 388.0),
                Sample(60, 2.0, 620.0, 380.0)]
        report = classify([Track("obj", tuple(rows))], observed_until_t=4.0)
        self.assertEqual([p for p in report.pots if p.is_pot], [])
        self.assertNotIn("reappeared_after_gap", codes(report.rejections))
        record = [r for r in report.rejections if r.code == "disappeared_outside_pocket"][0]
        self.assertAlmostEqual(record.thresholds["vanish_gap_s"], 4.0 * 0.5, delta=1e-6)
        self.assert_evidence_complete(report)

    def test_track_too_short_to_judge_is_a_named_rejection(self):
        report = report_for(Track("obj", tuple(still(*OPEN, 2))))
        self.assertEqual(report.pots, [])
        self.assertEqual(codes(report.rejections), {"track_too_short"})
        self.assertEqual(report.rejections[0].numbers["samples"], 2)
        self.assertEqual(report_for(Track("obj", ())).rejections[0].code, "empty_track")

    def test_duplicate_frames_are_collapsed_and_counted(self):
        rows = list(pot_track("obj", "head-left").samples)
        rows.append(Sample(rows[-2].frame_index, rows[-2].t, 0.0, 0.0, 0.5, False))
        track = Track("obj", tuple(rows))
        self.assertEqual(track.duplicates(), 1)
        self.assertEqual(len(track.ordered().samples), len(rows) - 1)
        report = report_for(track)
        self.assertEqual([p.verdict for p in report.pots], ["pot"])

    def test_the_confidence_floor_is_a_parameter(self):
        rows = [Sample(s.frame_index, s.t, s.x, s.y, 0.1, s.occluded)
                for s in pot_track("obj", "head-left").samples]
        report = report_for(Track("obj", tuple(rows)), thresholds=GateThresholds(min_confidence=0.5))
        self.assertEqual(report.shots, [])
        self.assertEqual(report.pots, [])
        self.assertEqual(codes(report.rejections), {"below_confidence_floor"})
        # the default floor keeps every sample, and then the same track is a shot and
        # a pot - which is what proves the floor, not the geometry, decided the refusal
        default = report_for(Track("obj", tuple(rows)))
        self.assertEqual([p.verdict for p in default.pots], ["pot"])
        self.assertEqual(len(default.shots), 1)


# -------------------------------------------------------------------- breaks

class BreakTests(GateTestCase):
    """A break is N shot events in one flagged group, never a silent merge."""

    def break_tracks(self, n: int) -> list[Track]:
        return [Track(f"obj{i}", tuple(still(OPEN[0] + 40 * i - 60, OPEN[1] - 20, 20)
                                       + moving(OPEN[0] + 40 * i - 60, OPEN[1] - 20, 0, 1, 20, 20)))
                for i in range(n)]

    def test_a_break_is_n_shots_in_one_flagged_group(self):
        report = classify(self.break_tracks(4))
        self.assertEqual(len(report.shots), 4)
        self.assertEqual(len({s.group_id for s in report.shots}), 1)
        self.assertTrue(all(s.is_break for s in report.shots))
        self.assertEqual(len(report.breaks), 1)
        group = report.breaks[0]
        self.assertIsInstance(group, BreakGroup)
        self.assertTrue(group.is_break)
        self.assertEqual(group.n_balls, 4)
        self.assertEqual(set(group.ball_ids), {"obj0", "obj1", "obj2", "obj3"})
        self.assertEqual(group.group_id, report.shots[0].group_id)
        # every member keeps its own evidence
        for shot in report.shots:
            self.assertTrue(shot.samples_used)
            self.assertGreater(shot.peak_speed_px_s, GateThresholds().motion_speed_px_s)
        self.assert_evidence_complete(report)
        self.assert_json_safe(report)

    def test_two_movers_are_a_contact_not_a_break(self):
        report = classify(self.break_tracks(2))
        self.assertEqual(len(report.shots), 2)
        self.assertEqual(len({s.group_id for s in report.shots}), 1)
        self.assertFalse(any(s.is_break for s in report.shots))
        self.assertEqual([g.is_break for g in report.breaks], [False])

    def test_onsets_far_apart_are_separate_groups_and_no_break(self):
        tracks = [Track("a", tuple(still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 20, 20))),
                  Track("b", tuple(still(OPEN[0], OPEN[1] + 30, 60)
                                   + moving(OPEN[0], OPEN[1] + 30, 1, 0, 20, 60)))]
        report = classify(tracks)
        self.assertEqual(len(report.shots), 2)
        self.assertEqual(len({s.group_id for s in report.shots}), 2)
        self.assertEqual([g.is_break for g in report.breaks], [False, False])
        self.assertGreater(abs(report.shots[0].onset_t - report.shots[1].onset_t),
                           GateThresholds().simultaneous_window_s)

    def test_the_break_bar_is_a_parameter(self):
        report = classify(self.break_tracks(2), thresholds=GateThresholds(break_min_balls=2))
        self.assertTrue(all(s.is_break for s in report.shots))
        self.assertTrue(report.breaks[0].is_break)


# ------------------------------------------------- batch, evidence and honesty

class ReportTests(GateTestCase):
    """The report is a complete account: every track, every refusal, JSON-safe."""

    def mixed_tracks(self) -> list[Track]:
        return [pot_track("a", "head-left"),
                Track("b", tuple(still(*OPEN, 40))),
                Track("c", tuple(still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 20, 20)))]

    def test_counts_and_ordering(self):
        report = classify(self.mixed_tracks())
        self.assertEqual(report.tracks_in, 3)
        counts = report.as_dict()["counts"]
        self.assertEqual(counts["tracks"], 3)
        self.assertEqual(counts["shots"], len(report.shots))
        self.assertEqual(counts["pots"], sum(1 for p in report.pots if p.is_pot))
        self.assertEqual(counts["unknowns"], sum(1 for p in report.pots if not p.is_pot))
        self.assertEqual(counts["rejections"], len(report.rejections))
        self.assertEqual([s.onset_t for s in report.shots], sorted(s.onset_t for s in report.shots))
        self.assertEqual([r.t for r in report.rejections if r.t is not None],
                         sorted(r.t for r in report.rejections if r.t is not None))
        self.assertTrue(any("shot(s)" in n for n in report.notes))
        self.assert_evidence_complete(report)
        self.assert_json_safe(report)

    def test_every_track_gets_at_least_one_record(self):
        tracks = [Track(f"t{i}", tuple(still(OPEN[0] + i, OPEN[1], 40))) for i in range(5)]
        report = classify(tracks)
        by_ball = Counter(r.ball_id for r in report.rejections)
        self.assertEqual(set(by_ball), {f"t{i}" for i in range(5)})
        for ball_id, count in by_ball.items():
            self.assertGreaterEqual(count, 1)

    def test_the_observation_window_defaults_to_the_last_sample_in_the_batch(self):
        a = pot_track("a", "head-left")
        b = Track("b", tuple(still(*OPEN, 20) + [sample(40, OPEN[0], OPEN[1], t=10.0)]))
        report = classify([a, b])
        self.assertEqual(report.observed_until_t, 10.0)
        self.assertEqual([p.verdict for p in report.pots if p.ball_id == "a"], ["pot"])

    def test_rejection_codes_are_the_documented_vocabulary(self):
        expected = {"empty_track", "track_too_short", "below_confidence_floor",
                    "no_motion_onset", "no_still_stretch", "motion_too_short",
                    "oscillation_no_net_travel", "roll_without_pocket", "reappeared_after_gap",
                    "disappeared_outside_pocket", "pocket_test_disagrees_px_vs_mm",
                    "left_frame_edge", "left_cloth", "track_ends_at_window_end"}
        scenarios = [
            (Track("a", ()), {}),
            (Track("b", tuple(still(*OPEN, 2))), {}),
            (Track("c", tuple(still(*OPEN, 40))), {}),
            (Track("d", tuple(sample(k, 600 + 6 * k, 430) for k in range(20))), {}),
            (Track("e", tuple(still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 20, 20, px=6.0))),
             {}),
            (Track("f", tuple(still(*OPEN, 20) + [sample(20, OPEN[0] + 20, OPEN[1]),
                                                sample(21, OPEN[0] + 60, OPEN[1])])), {}),
            (Track("g", tuple(still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 25, 20, px=24.0))),
             {"thresholds": GateThresholds(frame_size=(1280, 720))}),
            (Track("h", tuple(still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 20, 20, px=48.0))),
             {"thresholds": GateThresholds(cloth_quad=VOD30_REFERENCE_QUAD)}),
            (Track("i", tuple(still(*OPEN, 20) + moving(OPEN[0], OPEN[1], 1, 0, 12, 20, px=8.0))),
             {}),
            (Track("j", tuple(Sample(k, k * DT, OPEN[0], OPEN[1], 0.05, False)
                              for k in range(30))),
             {"thresholds": GateThresholds(min_confidence=0.5)}),
            (Track("k", tuple(still(*OPEN, 20) + moving(OPEN[0], OPEN[1], -1, 0, 25, 20, px=4.0)
                              + still(OPEN[0] - 100, OPEN[1], 15, start=60))), {}),
            (pot_track("l", "head-left"),
             {"observed_until_t": None}),
            # a run that jitters inside its own footprint: oscillation, not a shot
            (Track("m", tuple(still(*OPEN, 20) + [sample(20, OPEN[0] + 8, OPEN[1]),
                                                 sample(21, OPEN[0] + 12, OPEN[1]),
                                                 sample(22, OPEN[0] + 4, OPEN[1]),
                                                 sample(23, OPEN[0], OPEN[1])])), {}),
            # a ball inside the pixel radius but outside the millimetre gate
            (Track("n", tuple(still(*OPEN, 20)
                              + approach((default_pocket_model(quad=WORK_QUAD).by_name("left-side").x + 3.2,
                                          default_pocket_model(quad=WORK_QUAD).by_name("left-side").y + 9.08),
                                         OPEN[0], OPEN[1], 20, n=25, finish=1.0))),
             {"thresholds": GateThresholds(frame_size=list(WORK_SIZE),
                                           cloth_quad=list(WORK_QUAD))}),
        ]
        seen = set()
        for track, kw in scenarios:
            report = report_for(track, **kw)
            seen |= codes(report.rejections)
        self.assertTrue(seen <= expected, seen - expected)
        self.assertEqual(seen, expected, expected - seen)

    def test_track_events_can_be_called_directly_on_one_track(self):
        track = pot_track("obj", "foot-left")
        shots, pots, rejections = track_events(track, default_pocket_model(),
                                               observed_until_t=track.samples[-1].t + PERSIST)
        self.assertEqual(len(shots), 1)
        self.assertEqual([p.verdict for p in pots], ["pot"])
        self.assertEqual(rejections, [])

    def test_every_record_is_a_plain_dict_after_as_dict(self):
        report = classify([pot_track("obj", "right-side")])
        payload = report.as_dict()
        self.assertEqual(set(payload), {"shots", "pots", "rejections", "breaks", "counts",
                                        "observed_until_t", "notes"})
        for shot in payload["shots"]:
            self.assertEqual(shot["kind"], "shot")
            self.assertTrue(shot["samples_used"] and shot["thresholds"])
        for pot in payload["pots"]:
            self.assertEqual(pot["kind"], "pot")
            self.assertIn(pot["verdict"], {"pot", "unknown"})
        self.assertTrue(all(r["kind"] == "rejection" and r["reason"] for r in payload["rejections"]))


# ------------------------------------------------------- real data: SAM3 census

def census_tracks(frames: dict, max_dt: float = 1.0, max_px: float = 60.0) -> list[Track]:
    """Chain the census detections into short tracks: same colour, nearest, <= 60 px.

    A census frame lists every ball sighting with no identity, so the only identity
    signal available is the colour label plus nearest-neighbour continuity.  Each
    sighting is matched to at most one sighting of the previous sampled time and
    vice versa, which is the honest bound on what these frame-times can support.
    """
    times = sorted(frames)
    chains: list[list[Sample]] = []
    owner: dict[tuple[float, int], int] = {}
    for i, t in enumerate(times):
        rows = sorted(frames[t], key=lambda b: (str(b.get("color")), b["img"][0], b["img"][1]))
        taken: set[int] = set()
        prev = (sorted(frames[times[i - 1]],
                       key=lambda b: (str(b.get("color")), b["img"][0], b["img"][1]))
                if i > 0 and t - times[i - 1] <= max_dt else None)
        for k, ball in enumerate(rows):
            colour = str(ball.get("color"))
            best_index, best_distance = None, max_px
            for j, other in enumerate(prev or ()):
                if j in taken or str(other.get("color")) != colour:
                    continue
                distance = math.dist(other["img"], ball["img"])
                if distance < best_distance:
                    best_index, best_distance = j, distance
            point = sample(i, ball["img"][0], ball["img"][1], t=t,
                           conf=float(ball.get("score", 1.0)))
            if best_index is not None:
                taken.add(best_index)
                chain = owner[(times[i - 1], best_index)]
                chains[chain].append(point)
                owner[(t, k)] = chain
            else:
                chains.append([point])
                owner[(t, k)] = len(chains) - 1
    return [Track(f"{c[0].frame_index}-{i}", tuple(c)) for i, c in enumerate(chains)]


@unittest.skipUnless(CENSUS.is_file(), "no SAM3 census in this tree (out/ is gitignored)")
class Sam3CensusTests(GateTestCase):
    """The only real ball data in the repo: sparse frame-times, honest outcome."""

    @classmethod
    def setUpClass(cls):
        payload = json.loads(CENSUS.read_text())
        cls.frames = {float(t): v for t, v in payload["frames"].items()}
        cls.times = sorted(cls.frames)
        cls.tracks = census_tracks(cls.frames)
        cls.report = classify(cls.tracks, observed_until_t=max(cls.times))

    def test_the_census_is_too_sparse_for_a_sustained_onset(self):
        """Pinned: these samples cannot support the shot rule, and here is the number."""
        spacings = [b - a for a, b in zip(self.times, self.times[1:])]
        self.assertEqual(len(self.times), 138)
        self.assertGreater(sorted(spacings)[len(spacings) // 2], GateThresholds().max_gap_s)
        self.assertGreater(min(spacings), 0.0)
        # every above-bar burst in the whole census is shorter than the onset bar
        bursts = [r.numbers["burst_intervals"] for r in self.report.rejections
                  if r.code == "motion_too_short"]
        self.assertTrue(bursts)
        self.assertLess(max(bursts), GateThresholds().onset_intervals)

    def test_nothing_is_called_a_shot_or_a_pot(self):
        self.assertEqual(self.report.shots, [])
        self.assertEqual(self.report.pots, [])
        self.assertEqual(self.report.breaks, [])
        counts = self.report.as_dict()["counts"]
        self.assertEqual(counts["shots"], 0)
        self.assertEqual(counts["pots"], 0)
        self.assertEqual(counts["tracks"], len(self.tracks))

    def test_every_census_track_still_produces_a_named_reason(self):
        """Not one track is dropped in silence, whatever the sparsity."""
        self.assertGreaterEqual(len(self.report.rejections), self.report.tracks_in)
        by_ball = Counter(r.ball_id for r in self.report.rejections)
        self.assertEqual({t.ball_id for t in self.tracks} - set(by_ball), set())
        self.assertTrue({r.code for r in self.report.rejections} <=
                        {"track_too_short", "no_motion_onset", "motion_too_short",
                         "disappeared_outside_pocket", "reappeared_after_gap",
                         "track_ends_at_window_end", "no_still_stretch",
                         "roll_without_pocket", "left_frame_edge", "left_cloth",
                         "empty_track", "below_confidence_floor"})
        self.assert_evidence_complete(self.report)
        self.assert_json_safe(self.report)

    def test_the_census_tracks_are_short_and_that_is_the_whole_reason(self):
        lengths = [len(t.samples) for t in self.tracks]
        self.assertEqual(len(self.tracks), 364)
        self.assertEqual(max(lengths), 9)
        self.assertEqual(sum(1 for n in lengths if n >= 3), 70)
        codes_seen = Counter(r.code for r in self.report.rejections)
        self.assertEqual(codes_seen["track_too_short"], 294)
        self.assertEqual(codes_seen["no_motion_onset"], 66)
        self.assertEqual(codes_seen["motion_too_short"], 4)
        self.assertEqual(codes_seen["disappeared_outside_pocket"], 69)


if __name__ == "__main__":
    unittest.main()
