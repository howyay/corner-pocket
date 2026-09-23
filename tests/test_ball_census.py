"""Fused-census tests: association, colour stability, fallback, report shape.

No video, no model: ``src.ball_census`` is pure and the gates are pure, so every
rule is exercised on synthetic observations and synthetic evidence.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.ball_census import (CENSUS_VERSION, MIN_CENSUS_BALLS, Observation,  # noqa: E402
                             TRACK_MATCH_PX, UNKNOWN, associate, build_census,
                             color_presence, displacement_measure, normalize_color,
                             observations_from_classical, observations_from_sam3,
                             window_summary)
from src.event_gates import (GateConfig, GateResult, PotEvidence, ShotEvidence,  # noqa: E402
                             census_shot_corroborated, judge)

# A tiny canonical-frame projector: 1 px = 10 mm on both axes, so distances in
# the tests read directly in millimetres.
MM_FN = lambda cx, cy, t=None: [cx * 10.0, cy * 10.0]  # noqa: E731
FOOT_RIGHT_MM = (1270.0, 2540.0)               # frame px (127.0, 254.0)


def obs(t, color, cx, cy, source="classical", score=None):
    return Observation(t=t, color=color, cx=float(cx), cy=float(cy), r=8.0,
                       source=source, score=score)


def rack_frame(t, count, color="white", source="classical", spread=40.0, offset=0):
    """``count`` balls in a row, one every ``spread`` px, at time ``t``."""
    return [obs(t, color, 50 + index * spread + offset, 100, source=source,
                score=0.9 if source == "sam3" else None) for index in range(count)]


def report(observations, frame_times=None, sam3_times=None):
    return build_census(observations, table_mm_fn=MM_FN, frame_times=frame_times,
                        sam3_times=sam3_times)


class ColorNormalisationTests(unittest.TestCase):
    def test_hue_wraparound_red_is_one_colour(self):
        self.assertEqual(normalize_color("red2"), "red")
        self.assertEqual(normalize_color("RED"), "red")
        self.assertEqual(normalize_color(None), UNKNOWN)


class AssociationTests(unittest.TestCase):
    def test_same_ball_across_frames_is_one_identity(self):
        census = report([obs(0.0, "white", 100, 100), obs(0.25, "white", 106, 100),
                         obs(0.5, "white", 112, 100)])
        self.assertEqual(len(census["tracks"]), 1)
        self.assertEqual(census["tracks"][0]["hits"], 3)
        self.assertTrue(census["tracks"][0]["stable"])
        for frame in census["frames"]:
            self.assertEqual(frame["count"], 1)

    def test_two_balls_of_the_same_colour_stay_apart(self):
        census = report([obs(0.0, "red", 100, 100), obs(0.0, "red", 300, 100),
                         obs(0.25, "red", 102, 100), obs(0.25, "red", 298, 100)])
        self.assertEqual(len(census["tracks"]), 2)
        self.assertEqual([frame["count"] for frame in census["frames"]], [2, 2])
        for track in census["tracks"]:
            self.assertEqual(track["hits"], 2)

    def test_a_ball_seen_once_is_not_an_identity(self):
        census = report(rack_frame(0.0, 3))
        self.assertEqual(len(census["tracks"]), 3)
        self.assertFalse(any(track["stable"] for track in census["tracks"]))
        self.assertEqual(census["frames"][0]["fresh_count"], 3)
        self.assertEqual(census["frames"][0]["stable_count"], 0)

    def test_association_respects_the_gap(self):
        # Same place, same colour, but 5 s apart: a new sighting, not the same
        # ball -- balls move while nobody is looking.
        census = report([obs(0.0, "white", 100, 100), obs(5.0, "white", 100, 100)])
        self.assertEqual(len(census["tracks"]), 2)

    def test_a_far_match_is_a_new_identity(self):
        census = report([obs(0.0, "blue", 100, 100), obs(0.25, "blue", 100 + TRACK_MATCH_PX + 20, 100)])
        self.assertEqual(len(census["tracks"]), 2)

    def test_colour_flicker_wraps_into_one_identity(self):
        census = report([obs(0.0, "red", 100, 100), obs(0.25, "red2", 103, 100)])
        self.assertEqual(len(census["tracks"]), 1)
        self.assertEqual(census["tracks"][0]["color"], "red")
        self.assertEqual(census["tracks"][0]["conflicts"], 0)


class ColourStabilityTests(unittest.TestCase):
    def test_majority_colour_wins_and_the_disagreement_is_counted(self):
        # An unestablished identity absorbs one disagreeing colour, then keeps
        # the majority: a stripe misread as yellow/green does not become two
        # balls, and the conflict is visible in the report.
        census = report([obs(0.0, "yellow", 100, 100), obs(0.25, "green", 101, 100),
                         obs(0.5, "yellow", 102, 100), obs(0.75, "yellow", 103, 100)])
        self.assertEqual(len(census["tracks"]), 1)
        track = census["tracks"][0]
        self.assertEqual(track["color"], "yellow")
        self.assertEqual(track["hits"], 4)
        self.assertEqual(track["conflicts"], 1)
        self.assertLess(track["confidence"], 1.0)

    def test_an_established_identity_refuses_a_new_colour(self):
        other = [obs(1.0, "green", 101, 100), obs(1.25, "green", 101, 100)]
        census = report([obs(0.0, "yellow", 100, 100), obs(0.25, "yellow", 100, 100)] + other)
        self.assertEqual(len(census["tracks"]), 2)
        colors = sorted(track["color"] for track in census["tracks"])
        self.assertEqual(colors, ["green", "yellow"])


class FusionTests(unittest.TestCase):
    def test_one_ball_seen_by_both_detectors_counts_once(self):
        observations = observations_from_classical(0.0, [{"color": "white", "cx": 100, "cy": 100, "r": 8}])
        observations += observations_from_sam3(0.0, [{"score": 0.9, "img": [100.6, 100.4], "r": 8,
                                                     "color": "white"}])
        census = report(observations)
        self.assertEqual(census["frames"][0]["count"], 1)
        self.assertEqual(census["frames"][0]["classical_count"], 1)
        self.assertEqual(census["frames"][0]["sam3_count"], 1)

    def test_sam3_observations_scale_and_keep_their_score(self):
        observations = observations_from_sam3(1.0, [{"score": 0.95, "img": [640.0, 360.0], "r": 16.0,
                                                     "color": "black"}], scale=0.75)
        self.assertAlmostEqual(observations[0].cx, 480.0)
        self.assertAlmostEqual(observations[0].r, 12.0)
        self.assertEqual(observations[0].confidence, 0.9)

    def test_sam3_colour_is_sampled_when_the_cache_has_none(self):
        calls = []

        def color_fn(cx, cy, r):
            calls.append((cx, cy, r))
            return "blue"

        observations = observations_from_sam3(1.0, [{"score": 0.9, "img": [80.0, 40.0], "r": 10.0,
                                                     "color": "unknown"}], scale=1.0,
                                              color_fn=color_fn)
        self.assertEqual(observations[0].color, "blue")
        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(calls[0][2], 5.0)      # sampled from the ball's core

    def test_a_weak_sam3_score_is_not_a_measurement(self):
        observations = observations_from_sam3(1.0, [{"score": 0.31, "img": [10, 10], "r": 8}])
        self.assertEqual(observations, [])


class FrameReportShapeTests(unittest.TestCase):
    """The per-frame report is a contract: pin its keys and their types."""

    def test_frame_row_keys(self):
        census = report(rack_frame(0.0, 2) + rack_frame(0.5, 2))
        self.assertEqual(set(census), {"version", "frames", "tracks", "observations"})
        self.assertEqual(census["version"], CENSUS_VERSION)
        frame = census["frames"][0]
        self.assertEqual(set(frame), {"t", "count", "classical_count", "sam3_count",
                                      "stable_count", "fresh_count", "sam3_frame", "balls"})
        for key in ("count", "classical_count", "sam3_count", "stable_count", "fresh_count"):
            self.assertIsInstance(frame[key], int)
        self.assertIsInstance(frame["sam3_frame"], bool)
        ball = frame["balls"][0]
        self.assertEqual(set(ball), {"tid", "color", "color_source", "source", "cx", "cy", "r",
                                     "score", "hits", "stable", "confidence", "table_mm"})
        self.assertIsInstance(ball["hits"], int)
        self.assertIsInstance(ball["stable"], bool)
        self.assertIsInstance(ball["table_mm"], list)

    def test_track_row_keys(self):
        census = report(rack_frame(0.0, 1))
        track = census["tracks"][0]
        self.assertEqual(set(track), {"tid", "color", "hits", "stable", "first_t", "last_t",
                                      "confidence", "conflicts", "sources", "table_mm"})


class WindowSummaryTests(unittest.TestCase):
    def test_classical_only_fallback_keeps_the_old_formula(self):
        # No SAM3 frame anywhere: the summary is the classical median/max, the
        # window stays comparable, and nothing is dropped for occlusion.
        observations = []
        for index, t in enumerate((0.0, 0.25, 0.5)):
            observations += rack_frame(t, 3)
        for t in (1.5, 1.75, 2.0):
            observations += rack_frame(t, 2)
        summary = window_summary(report(observations), pre_times=[0.0, 0.25, 0.5],
                                 post_times=[1.5, 1.75, 2.0])
        self.assertEqual(summary["source"], "classical")
        self.assertTrue(summary["census_comparable"])
        self.assertTrue(summary["census_stable"])
        self.assertEqual(summary["census_pre"], 3.0)
        self.assertEqual(summary["census_post"], 2.0)
        self.assertEqual(summary["census_post_max"], 2.0)
        self.assertEqual(summary["census_drop"], 1.0)
        self.assertEqual(summary["dropped_pre"], [])

    def test_sam3_sides_are_counted_by_sam3(self):
        observations = []
        for t in (0.0, 0.25):
            observations += rack_frame(t, 10, source="sam3")
        for t in (1.5, 1.75):
            observations += rack_frame(t, 9, source="sam3")
        # The classical layer also saw the frames, with its usual low recall.
        for t in (0.0, 0.25, 1.5, 1.75):
            observations += rack_frame(t, 2)
        summary = window_summary(report(observations), pre_times=[0.0, 0.25],
                                 post_times=[1.5, 1.75])
        self.assertEqual(summary["source"], "sam3")
        self.assertEqual(summary["sam3_frames_pre"], 2)
        self.assertEqual(summary["census_pre"], 10.0)
        self.assertEqual(summary["census_post"], 9.0)
        self.assertEqual(summary["census_drop"], 1.0)
        self.assertTrue(summary["census_stable"])

    def test_one_sided_sam3_is_not_comparable(self):
        observations = []
        for t in (0.0, 0.25):
            observations += rack_frame(t, 10, source="sam3")
        for t in (1.5, 1.75):
            observations += rack_frame(t, 2)
        summary = window_summary(report(observations), pre_times=[0.0, 0.25],
                                 post_times=[1.5, 1.75])
        self.assertFalse(summary["census_comparable"])

    def test_occluded_frame_is_dropped_and_the_side_is_unstable(self):
        observations = []
        for t, count in ((0.25, 4), (0.5, 10)):
            observations += rack_frame(t, count, source="sam3")
        for t, count in ((1.5, 10), (1.75, 10)):
            observations += rack_frame(t, count, source="sam3")
        census = report(observations, frame_times=[0.0, 0.25, 0.5, 1.5, 1.75],
                        sam3_times=[0.0, 0.25, 0.5, 1.5, 1.75])
        self.assertEqual(census["frames"][0]["count"], 0)   # empty, not missing
        summary = window_summary(census, pre_times=[0.0, 0.25, 0.5], post_times=[1.5, 1.75])
        self.assertEqual(summary["dropped_pre"], [0.0])
        self.assertFalse(summary["census_stable"])
        self.assertEqual(summary["sam3_frames_pre"], 3)     # still reported as measured

    def test_a_one_ball_drop_is_detectable(self):
        # 10 balls racked, one of them 60 mm from foot-right before the event and
        # gone after it: the whole point of the census upgrade.
        observations = []
        for t in (0.0, 0.25, 0.5):
            observations += rack_frame(t, 9, source="sam3")
            observations.append(obs(t, "black", 127.0, 254.0, source="sam3", score=0.9))
        for t in (1.5, 1.75, 2.0):
            observations += rack_frame(t, 9, source="sam3")
        summary = window_summary(report(observations), pre_times=[0.0, 0.25, 0.5],
                                 post_times=[1.5, 1.75, 2.0], claim_color="black")
        self.assertEqual(summary["census_pre"], 10.0)
        self.assertEqual(summary["census_post"], 9.0)
        self.assertEqual(summary["census_drop"], 1.0)
        self.assertEqual(summary["identity_drop"], 1)
        vanished = summary["vanished"][0]
        self.assertEqual(vanished["color"], "black")
        self.assertEqual(vanished["hits"], 3)
        self.assertEqual(vanished["pocket"], "foot-right")
        self.assertEqual(vanished["dist_mm"], 0)
        self.assertEqual(vanished["approach_mm"], 0.0)
        self.assertFalse(summary["claim_color_present"])
        self.assertEqual(summary["identity_drop"], 1)

    def test_vanished_row_needs_two_sightings(self):
        observations = [obs(0.0, "black", 127.0, 254.0, source="sam3", score=0.9)]
        for t in (1.5, 1.75):
            observations += rack_frame(t, 9, source="sam3")
        summary = window_summary(report(observations), pre_times=[0.0], post_times=[1.5, 1.75])
        self.assertEqual(summary["vanished"], [])

    def test_presence_needs_a_scored_or_repeated_sighting(self):
        report_one = report([obs(1.5, "black", 127.0, 254.0)])
        single = color_presence(report_one, "black", [1.5])
        self.assertTrue(single["present"])
        self.assertFalse(single["measured"])          # one colour blob is not enough
        report_two = report([obs(1.5, "black", 127.0, 254.0), obs(1.75, "black", 128.0, 254.0)])
        self.assertTrue(color_presence(report_two, "black", [1.5, 1.75])["measured"])
        scored = report([obs(1.5, "black", 127.0, 254.0, source="sam3", score=0.9)])
        self.assertTrue(color_presence(scored, "black", [1.5])["measured"])


class EndgameCensusTests(unittest.TestCase):
    def test_an_endgame_side_is_low_not_occluded(self):
        # Two balls on the cloth before, one after: the whole side is below the
        # floor, and dropping it would hide exactly the drop that ends a game.
        observations = []
        for t in (0.0, 0.25):
            observations += rack_frame(t, 1, source="sam3")
            observations.append(obs(t, "black", 120.0, 200.0, source="sam3", score=0.9))
        for t in (1.5, 1.75):
            observations += rack_frame(t, 1, source="sam3")
        summary = window_summary(report(observations), pre_times=[0.0, 0.25],
                                 post_times=[1.5, 1.75])
        # Two balls is the floor itself: counted, not flagged.  One ball is
        # below it, and the whole side is low, so it is kept and flagged.
        self.assertFalse(summary["low_census_pre"])
        self.assertTrue(summary["low_census_post"])
        self.assertEqual(summary["census_pre"], 2.0)
        self.assertEqual(summary["census_post"], 1.0)
        self.assertEqual(summary["census_drop"], 1.0)
        self.assertEqual(summary["dropped_pre"], [])
        self.assertEqual(summary["dropped_post"], [])

    def test_a_dropout_inside_a_populated_side_is_occlusion(self):
        observations = []
        for t, count in ((0.0, 10), (0.3, 1)):
            observations += rack_frame(t, count, source="sam3")
        for t in (1.5, 1.8):
            observations += rack_frame(t, 10, source="sam3")
        summary = window_summary(report(observations), pre_times=[0.0, 0.3],
                                 post_times=[1.5, 1.8])
        self.assertFalse(summary["low_census_pre"])
        self.assertEqual(summary["dropped_pre"], [0.3])
        self.assertEqual(summary["census_pre"], 10.0)
        self.assertFalse(summary["census_stable"])


class DisplacementMeasureTests(unittest.TestCase):
    def test_one_ball_moved_and_the_others_stayed(self):
        # Nine balls at rest, one 800 mm away after the event: the pairing finds
        # the moved ball even though its identity was reborn on the far side.
        observations = []
        resting = [(x, 200) for x in range(1, 10)]
        for t in (0.0, 0.1):
            for x, y in resting:
                observations.append(obs(t, "blue", x * 10.0, y * 10.0, source="sam3", score=0.9))
            observations.append(obs(t, "white", 100.0, 300.0, source="sam3", score=0.9))
        for t in (1.0, 1.1):
            for x, y in resting:
                observations.append(obs(t, "blue", x * 10.0, y * 10.0, source="sam3", score=0.9))
            observations.append(obs(t, "white", 180.0, 300.0, source="sam3", score=0.9))
        move = displacement_measure(report(observations), 0.5, claim_color="white")
        self.assertEqual(move["disp_mm"], 800)       # 80 px at 10 mm/px
        self.assertEqual(move["color"], "white")
        self.assertEqual(move["start_hits"], 2)
        self.assertEqual(move["end_hits"], 2)
        self.assertEqual(move["tracks_moved"], 1)
        self.assertEqual(move["still"], 9)
        self.assertTrue(move["claim_color_measured"])

    def test_nothing_moved_is_not_a_shot(self):
        observations = []
        for t in (0.0, 0.1, 1.0, 1.1):
            for index in range(5):
                observations.append(obs(t, "blue", 100.0 + index * 40, 200.0,
                                        source="sam3", score=0.9))
        move = displacement_measure(report(observations), 0.5)
        self.assertIsNone(move["disp_mm"])
        self.assertEqual(move["tracks_moved"], 0)
        self.assertEqual(move["still"], 5)

    def test_the_classical_layer_alone_measures_nothing(self):
        # Positions worth measuring come from scored masks; a window with only
        # colour blobs leaves the census path silent (the classical path decides).
        observations = rack_frame(0.0, 4) + rack_frame(1.0, 4)
        move = displacement_measure(report(observations), 0.5)
        self.assertIsNone(move["disp_mm"])
        self.assertEqual(move["identities_pre"], 0)


class PotGateTests(unittest.TestCase):
    def test_a_unique_ball_still_on_the_cloth_rejects_the_pot(self):
        evidence = PotEvidence(available=True, census_pre=10.0, census_post=10.0,
                               census_post_max=10.0, claim_color="black",
                               claim_color_present=True, claim_color_present_measured=True,
                               claim_color_present_hits=2, claim_color_unique=True)
        result = judge({"kind": "pot", "color": "black", "t": 27.7, "last_mm": [1210, 2421]}, evidence)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reasons, ["vanished_ball_still_on_cloth"])

    def test_a_lone_blob_does_not_reject_the_pot(self):
        evidence = PotEvidence(available=True, census_pre=10.0, census_post=9.0,
                               census_post_max=9.0, claim_color="black",
                               claim_color_present=True, claim_color_present_measured=False,
                               claim_color_present_hits=1, claim_color_unique=True,
                               vanish=[{"color": "black", "mm": [1210, 2421], "pocket": "foot-right",
                                        "dist_mm": 60, "pre_hits": 3, "approach_mm": 120}])
        result = judge({"kind": "pot", "color": "black", "t": 27.7, "last_mm": [1210, 2421]}, evidence)
        self.assertEqual(result.status, "confirmed")

    def test_a_mixed_source_window_cannot_claim_a_drop(self):
        evidence = PotEvidence(available=True, census_pre=10.0, census_post=2.0,
                               census_post_max=2.0, census_comparable=False)
        result = judge({"kind": "pot", "color": "white", "t": 45.6, "last_mm": [1200, 2400]}, evidence)
        self.assertEqual(result.status, "unconfirmed")
        self.assertEqual(result.reasons, ["census_source_mismatch"])

    def test_the_classical_verdict_is_unchanged_without_census_fields(self):
        evidence = PotEvidence(available=True, census_pre=3.0, census_post=2.0, census_post_max=3.0)
        result = judge({"kind": "pot", "color": "blue", "t": 5.6, "last_mm": [100, 100]}, evidence)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reasons, ["census_recovered"])

    def test_a_measured_drop_with_the_ball_at_the_pocket_confirms(self):
        evidence = PotEvidence(available=True, census_pre=10.0, census_post=9.0, census_post_max=9.0,
                               census_source="sam3", census_comparable=True,
                               vanish=[{"color": "black", "mm": [1240, 2490], "pocket": "foot-right",
                                        "dist_mm": 57, "pre_hits": 3, "approach_mm": 140,
                                        "tid": 7, "sources": {"sam3": 3}, "confidence": 0.9}])
        result = judge({"kind": "pot", "color": "black", "t": 45.6, "last_mm": [1240, 2490]}, evidence)
        self.assertEqual(result.status, "confirmed")
        self.assertIn("vanished_ball_at_pocket", result.reasons)
        self.assertEqual(result.numbers["vanish_tid"], 7)


class ShotGateTests(unittest.TestCase):
    def test_census_corroborates_a_blurred_shot(self):
        evidence = ShotEvidence(available=True, disp_mm=5, from_in_cloth_px=30.0, to_in_cloth_px=40.0,
                                census_disp_mm=1030, census_disp_color="white",
                                census_start_hits=2, census_end_hits=3, census_tracks_moved=1,
                                census_geometry_gap_px=20.0)
        self.assertTrue(census_shot_corroborated(evidence))
        result = judge({"kind": "shot", "color": "white", "t": 45.17,
                        "from_mm": [400, 600], "to_mm": [900, 1800]}, evidence)
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.tier, "census")
        self.assertEqual(result.reasons, ["census_displacement_corroborated"])

    def test_the_classical_verdict_is_unchanged_without_census_fields(self):
        evidence = ShotEvidence(available=True, disp_mm=5, from_in_cloth_px=30.0, to_in_cloth_px=40.0,
                                start_hits=9, end_hits=9, stable_hits=0, anchor_tries=3)
        result = judge({"kind": "shot", "color": "blue", "t": 6.03,
                        "from_mm": [400, 600], "to_mm": [900, 1800]}, evidence)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reasons, ["displacement_not_corroborated"])

    def test_off_cloth_still_beats_the_census(self):
        evidence = ShotEvidence(available=True, disp_mm=5, from_in_cloth_px=30.0, to_in_cloth_px=-9.0,
                                census_disp_mm=1500, census_start_hits=3, census_end_hits=3,
                                census_tracks_moved=1, census_geometry_gap_px=5.0)
        result = judge({"kind": "shot", "color": "blue", "t": 6.03,
                        "from_mm": [400, 600], "to_mm": [2000, 2900]}, evidence)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reasons, ["off_cloth"])

    def test_a_single_sighting_at_an_end_is_not_corroboration(self):
        evidence = ShotEvidence(available=True, from_in_cloth_px=30.0, to_in_cloth_px=40.0,
                                census_disp_mm=900, census_start_hits=1, census_end_hits=3,
                                census_tracks_moved=1, census_geometry_gap_px=10.0)
        self.assertFalse(census_shot_corroborated(evidence))

    def test_a_far_claim_start_is_not_corroboration(self):
        evidence = ShotEvidence(available=True, from_in_cloth_px=30.0, to_in_cloth_px=40.0,
                                census_disp_mm=900, census_start_hits=3, census_end_hits=3,
                                census_tracks_moved=1, census_geometry_gap_px=200.0)
        self.assertFalse(census_shot_corroborated(evidence))


class SourceHelperTests(unittest.TestCase):
    def test_associate_returns_tracks_and_frames(self):
        tracks, frames = associate([obs(0.0, "white", 10, 10), obs(0.25, "white", 12, 10)])
        self.assertEqual(len(tracks), 1)
        self.assertEqual(sum(len(pairs) for pairs in frames.values()), 2)

    def test_min_census_floor_is_above_one(self):
        self.assertGreaterEqual(MIN_CENSUS_BALLS, 2)


if __name__ == "__main__":
    unittest.main()
