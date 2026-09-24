"""enroll_from_tracklet tests: synthetic observations only, no models, no network."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.enroll_from_tracklet import (  # noqa: E402
    CONSISTENCY_COSINE,
    CROP_MAX_BYTES,
    EnrollmentTokenError,
    PURITY_DEFAULT,
    PURITY_PROBES_MIN,
    DEFAULT_FACE_STORE,
    DEFAULT_STATE,
    MIN_KEPT_DEFAULT,
    REFUSAL_REASONS,
    Candidate,
    Enrollment,
    Refusal,
    center_inside,
    collect_face_candidates,
    face_area_iou,
    iou,
    load_state,
    md5,
    persistent_tracks,
    plan_enrollment,
    plan_for_selection,
    plan_for_track,
    preview_payload,
    rank_score,
    enrollment_token,
    confirm_enrollment,
    Selection,
    scan_frames,
    scan_track,
    write_enrollment,
)

DIM = 512
PERSON = [100.0, 100.0, 300.0, 600.0]          # box the faces live in
OTHER_PERSON = [700.0, 100.0, 900.0, 600.0]


def unit(seed=1):
    rng = np.random.RandomState(seed)
    v = rng.standard_normal(DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def at(base, sim, seed=2):
    """Unit vector whose cosine with base is `sim`."""
    rng = np.random.RandomState(seed)
    other = rng.standard_normal(DIM).astype(np.float32)
    other -= base * float(np.dot(base, other))
    other /= np.linalg.norm(other)
    return (base * sim + other * math.sqrt(max(0.0, 1.0 - sim * sim))).astype(np.float32)


def face(bbox, eye=12.0, det=0.8, embedding=None):
    return {"bbox": list(bbox), "eye_px": eye, "det_score": det,
            "embedding": (unit(1) if embedding is None else np.asarray(embedding, np.float32)).tolist()}


def observation(frame_index, persons, faces, t=None):
    return {"frame_index": frame_index, "t": float(frame_index) if t is None else t,
            "persons": persons, "faces": faces}


def person(track_id=1, bbox=None):
    return {"track_id": track_id, "bbox": list(bbox or PERSON), "conf": 0.9}


def series(count=6, *, sims=None, eye=12.0, det=0.8, track_id=1, step=15, seed=7):
    """`count` observations, one person, one face per frame."""
    base = unit(seed)
    rows = []
    for index in range(count):
        sim = 0.9 - 0.02 * index if sims is None else sims[index]
        rows.append(observation(
            index * step,
            [person(track_id)],
            [face([150, 150, 190, 200], eye=eye + index * 0.1, det=det, embedding=at(base, sim, 100 + index))],
            ))
    return rows


def state_with(players=(), revision=4):
    return {"revision": revision, "players": list(players), "events": [],
            "tournament": {"entrants": []}, "settings": {}}


class GeometryTest(unittest.TestCase):
    def test_iou_identity_and_disjoint(self):
        self.assertAlmostEqual(iou([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)
        self.assertEqual(iou([0, 0, 10, 10], [50, 50, 60, 60]), 0.0)

    def test_center_inside_is_the_association_rule(self):
        self.assertTrue(center_inside([150, 150, 190, 200], PERSON))
        self.assertFalse(center_inside([650, 150, 690, 200], PERSON))

    def test_face_area_iou(self):
        self.assertAlmostEqual(face_area_iou([150, 150, 190, 200], PERSON), 1.0)
        self.assertAlmostEqual(face_area_iou([80, 150, 120, 190], PERSON), 0.5)
        self.assertEqual(face_area_iou([10, 10, 10, 20], PERSON), 0.0)

    def test_rank_score_is_det_times_eye(self):
        self.assertAlmostEqual(rank_score(0.8, 12.0), 9.6)
        self.assertEqual(rank_score(0.9, None), 0.0)


class ScanTrackTest(unittest.TestCase):
    def test_counts_per_gate(self):
        observations = [
            observation(0, [person()], [face([150, 150, 190, 200])]),                  # usable
            observation(15, [person()], [face([150, 150, 190, 200], eye=5.0)]),        # eye gate
            observation(30, [person()], [face([150, 150, 190, 200], det=0.2)]),        # det gate
            observation(45, [person()], [face([650, 150, 690, 200])]),                 # other box
            observation(60, [], []),                                                   # person gone
        ]
        scan = scan_track(observations, 1)
        self.assertEqual(scan["frames_with_track"], 4)
        self.assertEqual(scan["faces_associated"], 3)
        self.assertEqual(scan["gated_eye"], 1)
        self.assertEqual(scan["gated_det"], 1)

    def test_a_face_claimed_by_two_boxes_is_ambiguous(self):
        observations = [observation(0, [person(), person(2, [-50, -50, 350, 650])],
                                    [face([150, 150, 190, 200])])]
        scan = scan_track(observations, 1)
        self.assertEqual(scan["ambiguous"], 1)
        self.assertEqual(scan["faces_associated"], 0)

    def test_unknown_track_counts_nothing(self):
        self.assertEqual(scan_track(series(3), 99)["frames_with_track"], 0)


class CollectTest(unittest.TestCase):
    def test_candidates_are_ranked_by_det_times_eye(self):
        observations = [
            observation(0, [person()], [face([150, 150, 190, 200], eye=20.0, det=0.5)]),  # 10.0
            observation(15, [person()], [face([150, 150, 190, 200], eye=9.0, det=0.9)]),  # 8.1
            observation(30, [person()], [face([150, 150, 190, 200], eye=30.0, det=0.9)]),  # 27.0
        ]
        candidates = collect_face_candidates(observations, 1)
        self.assertEqual([candidate.frame_index for candidate in candidates], [30, 0, 15])
        self.assertTrue(all(isinstance(candidate, Candidate) for candidate in candidates))

    def test_gates_and_ambiguity_filter_candidates(self):
        observations = [
            observation(0, [person()], [face([150, 150, 190, 200])]),
            observation(15, [person()], [face([150, 150, 190, 200], eye=None)]),
            observation(30, [person()], [face([150, 150, 190, 200], det=0.39)]),
            observation(45, [person(), person(2, [-50, -50, 350, 650])], [face([150, 150, 190, 200])]),
            observation(60, [person()], [face([650, 150, 690, 200])]),
        ]
        candidates = collect_face_candidates(observations, 1)
        self.assertEqual([candidate.frame_index for candidate in candidates], [0])

    def test_face_iou_is_recorded_as_evidence(self):
        observations = [observation(0, [person()], [face([150, 150, 190, 200])])]
        self.assertEqual(collect_face_candidates(observations, 1)[0].face_iou, 1.0)

    def test_unknown_track_has_no_candidates(self):
        self.assertEqual(collect_face_candidates(series(3), 99), [])


class RefusalTest(unittest.TestCase):
    """Every refusal reason is reachable and typed."""

    def test_track_not_found(self):
        refusal = plan_for_track(series(3), 99, player_name="Alice")
        self.assertIsInstance(refusal, Refusal)
        self.assertFalse(refusal.ok)
        self.assertEqual(refusal.reason, "track_not_found")

    def test_no_face_in_track(self):
        observations = [observation(0, [person()], []), observation(15, [person()], [])]
        refusal = plan_for_track(observations, 1, player_name="Alice")
        self.assertEqual(refusal.reason, "no_face_in_track")

    def test_no_face_when_box_never_contains_a_face(self):
        observations = [observation(0, [person()], [face([650, 150, 690, 200])])]
        self.assertEqual(plan_for_track(observations, 1, player_name="Alice").reason,
                         "no_face_in_track")

    def test_ambiguous_only_is_reported_as_no_face_with_a_note(self):
        observations = series(3)
        for row in observations:
            row["persons"].append(person(2, [-50, -50, 350, 650]))
        refusal = plan_for_track(observations, 1, player_name="Alice")
        self.assertEqual(refusal.reason, "no_face_in_track")
        self.assertIn("two person boxes", refusal.detail["note"])

    def test_face_too_small(self):
        observations = series(4, eye=3.0)
        refusal = plan_for_track(observations, 1, player_name="Alice")
        self.assertEqual(refusal.reason, "face_too_small")
        self.assertEqual(refusal.detail["gated_eye"], 4)

    def test_face_low_detection(self):
        observations = series(4, det=0.2)
        refusal = plan_for_track(observations, 1, player_name="Alice")
        self.assertEqual(refusal.reason, "face_low_detection")
        self.assertEqual(refusal.detail["gated_det"], 4)

    def test_single_face_only(self):
        refusal = plan_for_track(series(1), 1, player_name="Alice")
        self.assertEqual(refusal.reason, "single_face_only")
        self.assertEqual(refusal.detail["usable_faces"], 1)
        self.assertEqual(refusal.detail["min_kept"], MIN_KEPT_DEFAULT)

    def test_two_faces_of_two_people_are_inconsistent(self):
        base = unit(11)
        observations = [
            observation(0, [person()], [face([150, 150, 190, 200], embedding=base)]),
            observation(15, [person()], [face([150, 150, 190, 200], embedding=unit(12))]),
        ]
        refusal = plan_for_track(observations, 1, player_name="Alice")
        self.assertEqual(refusal.reason, "inconsistent_faces")
        self.assertEqual(refusal.detail["kept"], 1)
        self.assertEqual(refusal.detail["consistency_cosine"], CONSISTENCY_COSINE)

    def test_mixed_track_is_refused_when_the_best_faces_leave_the_track_behind(self):
        """The measured failure: two mutually consistent faces of person A while the
        rest of the track is person B (an IoU tracker switching people)."""
        base_a, base_b = unit(51), unit(52)
        candidates = [
            Candidate(0, 0.0, [1, 1, 2, 2], PERSON, 0.9, 20.0, base_a),
            Candidate(15, 0.5, [1, 1, 2, 2], PERSON, 0.9, 19.0, at(base_a, 0.9, 53)),
            Candidate(30, 1.0, [1, 1, 2, 2], PERSON, 0.9, 18.0, base_b),
            Candidate(45, 1.5, [1, 1, 2, 2], PERSON, 0.9, 17.0, at(base_b, 0.95, 54)),
        ]
        refusal = plan_enrollment(candidates, track_id=1, player_name="Alice",
                                  state=state_with())
        self.assertIsInstance(refusal, Refusal)
        self.assertEqual(refusal.reason, "mixed_track")
        self.assertEqual(refusal.detail["kept"], 2)
        self.assertEqual(refusal.detail["purity"], 0.0)
        self.assertEqual(refusal.detail["purity_probes"], 2)
        self.assertEqual(refusal.detail["min_purity"], PURITY_DEFAULT)

    def test_a_consistent_track_passes_the_purity_gate(self):
        candidates = collect_face_candidates(series(8), 1)   # 5 kept, 3 other faces
        enrollment = plan_enrollment(candidates, track_id=1, player_name="Alice",
                                     state=state_with())
        self.assertIsInstance(enrollment, Enrollment)
        self.assertEqual(enrollment.evidence["purity"], 1.0)
        self.assertEqual(enrollment.evidence["purity_probes"], 3)
        self.assertTrue(enrollment.evidence["purity_decisive"])
        self.assertEqual(enrollment.evidence["min_purity"], PURITY_DEFAULT)

    def test_a_single_other_face_does_not_veto_an_otherwise_consistent_pair(self):
        """Purity over one probe is a 0/1 vote; the consistency gate already
        dropped the intruder, so the pair is enrolled (PURITY_PROBES_MIN)."""
        base = unit(61)
        candidates = [
            Candidate(0, 0.0, [1, 1, 2, 2], PERSON, 0.9, 20.0, base),
            Candidate(15, 0.5, [1, 1, 2, 2], PERSON, 0.9, 19.0, at(base, 0.9, 62)),
            Candidate(30, 1.0, [1, 1, 2, 2], PERSON, 0.9, 18.0, unit(63)),
        ]
        enrollment = plan_enrollment(candidates, track_id=1, player_name="Alice",
                                     state=state_with())
        self.assertIsInstance(enrollment, Enrollment)
        self.assertEqual(enrollment.evidence["purity_probes"], 1)
        self.assertFalse(enrollment.evidence["purity_decisive"])
        self.assertEqual(len(enrollment.dropped), 1)
        self.assertEqual(PURITY_PROBES_MIN, 2)

    def test_purity_is_not_measured_without_other_faces(self):
        candidates = collect_face_candidates(series(2), 1)
        enrollment = plan_enrollment(candidates, track_id=1, player_name="Alice",
                                     state=state_with())
        self.assertIsInstance(enrollment, Enrollment)
        self.assertIsNone(enrollment.evidence["purity"])
        self.assertEqual(enrollment.evidence["purity_probes"], 0)

    def test_every_reason_is_declared_and_has_a_message(self):
        for reason in REFUSAL_REASONS:
            refusal = Refusal(reason)
            self.assertTrue(refusal.message())
            self.assertFalse(refusal.to_dict()["ok"])
        with self.assertRaises(ValueError):
            Refusal("something_else")

    def test_refusal_never_returns_an_empty_result(self):
        """Every path returns a typed Refusal or a full Enrollment, never []."""
        samples = [series(3), series(3, eye=2.0), series(3, det=0.1), series(1), []]
        for observations in samples:
            result = plan_for_track(observations, 1, player_name="Alice")
            self.assertIsInstance(result, (Refusal, Enrollment))
            self.assertFalse(isinstance(result, list))


class PlanTest(unittest.TestCase):
    def test_keeps_at_most_k_consistent_faces(self):
        candidates = collect_face_candidates(series(8), 1)
        enrollment = plan_enrollment(candidates, track_id=1, player_name="Alice", k=3,
                                     state=state_with())
        self.assertIsInstance(enrollment, Enrollment)
        self.assertEqual(len(enrollment.crops), 3)
        self.assertEqual(enrollment.evidence["usable_faces"], 8)
        self.assertEqual(enrollment.evidence["dropped"], 0)
        self.assertEqual(enrollment.evidence["skipped_by_k"], 5)  # 8 usable, 3 kept, 5 past k
        self.assertGreaterEqual(enrollment.evidence["pairwise_cosine"]["min"], CONSISTENCY_COSINE)

    def test_inconsistent_candidate_is_dropped_with_its_cosine(self):
        base = unit(21)
        candidates = [
            Candidate(0, 0.0, [1, 1, 2, 2], PERSON, 0.9, 20.0, base),
            Candidate(15, 0.5, [1, 1, 2, 2], PERSON, 0.9, 19.0, at(base, 0.9, 22)),
            Candidate(30, 1.0, [1, 1, 2, 2], PERSON, 0.9, 18.0, unit(23)),
        ]
        enrollment = plan_enrollment(candidates, track_id=1, player_name="Alice", state=state_with())
        self.assertEqual(len(enrollment.crops), 2)
        self.assertEqual(len(enrollment.dropped), 1)
        self.assertEqual(enrollment.dropped[0]["reason"], "inconsistent_with_kept")
        self.assertLess(enrollment.dropped[0]["worst_kept_cosine"], CONSISTENCY_COSINE)

    def test_a_mixed_track_with_no_consensus_is_refused_not_averaged(self):
        candidates = [
            Candidate(0, 0.0, [1, 1, 2, 2], PERSON, 0.9, 20.0, unit(31)),
            Candidate(15, 0.5, [1, 1, 2, 2], PERSON, 0.9, 19.0, unit(32)),
            Candidate(30, 1.0, [1, 1, 2, 2], PERSON, 0.9, 18.0, unit(33)),
        ]
        refusal = plan_enrollment(candidates, track_id=1, player_name="Alice",
                                  consistency=0.9, state=state_with())
        self.assertIsInstance(refusal, Refusal)
        self.assertEqual(refusal.reason, "inconsistent_faces")
        self.assertEqual(refusal.detail["kept"], 1)
        self.assertEqual(len(refusal.candidates), 3)

    def test_store_json_matches_the_face_store_row_shape(self):
        enrollment = plan_enrollment(collect_face_candidates(series(4), 1), track_id=7,
                                     player_name="Alice", state=state_with(),
                                     created_at="2026-09-24T00:00:00+00:00")
        player_id = enrollment.player_id
        self.assertEqual(list(enrollment.store_json), [player_id])
        rows = enrollment.store_json[player_id]
        self.assertEqual(len(rows), 4, "one row per kept face")
        for row in rows:
            self.assertEqual(sorted(row), ["created_at", "det_score", "embedding", "eye_px", "source"])
            self.assertEqual(len(row["embedding"]), DIM)
            self.assertEqual(row["created_at"], "2026-09-24T00:00:00+00:00")
            self.assertEqual(row["source"], "7")

    def test_roster_json_adds_a_player_bumps_revision_and_logs_the_event(self):
        state = state_with()
        enrollment = plan_enrollment(collect_face_candidates(series(4), 1), track_id=7,
                                     player_name="Alice", state=state)
        roster = enrollment.roster_json
        self.assertEqual(roster["revision"], 5)
        self.assertEqual([player["name"] for player in roster["players"]], ["Alice"])
        self.assertEqual(roster["players"][0]["status"], "Active")
        self.assertEqual(roster["events"][-1]["action"], "player_enroll_from_tracklet")
        self.assertEqual(roster["events"][-1]["context"]["track_id"], 7)
        self.assertEqual(state["revision"], 4, "the caller's state is never mutated")
        self.assertEqual(state["players"], [])

    def test_an_existing_name_reuses_the_player_id(self):
        state = state_with([{"id": "p1", "name": "alice", "rating": 0, "status": "Active"}])
        enrollment = plan_enrollment(collect_face_candidates(series(4), 1), track_id=1,
                                     player_name="Alice", state=state)
        self.assertEqual(enrollment.player_id, "p1")
        self.assertTrue(enrollment.evidence["existing_player"])
        self.assertEqual(len(enrollment.roster_json["players"]), 1)

    def test_roster_json_is_none_without_state(self):
        enrollment = plan_enrollment(collect_face_candidates(series(4), 1), track_id=1,
                                     player_name="Alice")
        self.assertIsNone(enrollment.roster_json)

    def test_enrollment_dict_is_json_serialisable(self):
        enrollment = plan_enrollment(collect_face_candidates(series(4), 1), track_id=1,
                                     player_name="Alice", state=state_with())
        self.assertIn("store_json", json.loads(json.dumps(enrollment.to_dict())))


class WriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scratch = self.root / "scratch"
        self.source = self.root / "production"
        (self.source / DEFAULT_STATE).parent.mkdir(parents=True)
        (self.source / DEFAULT_STATE).write_text(json.dumps(state_with()), encoding="utf-8")
        self.production_state = md5(self.source / DEFAULT_STATE)

    def test_writes_only_under_the_scratch_root(self):
        enrollment = plan_enrollment(collect_face_candidates(series(4), 1), track_id=1,
                                     player_name="Alice", state=state_with())
        written = write_enrollment(self.scratch, enrollment, source_root=self.source)
        self.assertTrue(Path(written["state"]).is_relative_to(self.scratch))
        self.assertTrue(Path(written["store"]).is_relative_to(self.scratch))
        self.assertEqual(json.loads(Path(written["store"]).read_text()), enrollment.store_json)
        self.assertEqual(json.loads(Path(written["state"]).read_text()), enrollment.roster_json)
        self.assertEqual(md5(self.source / DEFAULT_STATE), self.production_state,
                         "production roster is byte-identical")
        self.assertIsNone(md5(self.source / DEFAULT_FACE_STORE))

    def test_copies_the_source_state_when_no_roster_payload_is_given(self):
        enrollment = plan_enrollment(collect_face_candidates(series(4), 1), track_id=1,
                                     player_name="Alice")
        written = write_enrollment(self.scratch, enrollment, source_root=self.source)
        self.assertEqual(json.loads(Path(written["state"]).read_text()),
                         json.loads((self.source / DEFAULT_STATE).read_text()))
        self.assertEqual(md5(self.source / DEFAULT_STATE), self.production_state)

    def test_refuses_a_scratch_root_that_contains_production(self):
        enrollment = plan_enrollment(collect_face_candidates(series(4), 1), track_id=1,
                                     player_name="Alice", state=state_with())
        with self.assertRaises(ValueError):
            write_enrollment(self.source, enrollment, source_root=self.source)

    def test_a_second_enrolment_appends_to_the_scratch_store(self):
        first = plan_enrollment(collect_face_candidates(series(4), 1), track_id=1,
                                player_name="Alice", state=load_state(self.source))
        write_enrollment(self.scratch, first, source_root=self.source)
        second = plan_enrollment(collect_face_candidates(series(4, seed=8), 1), track_id=1,
                                 player_name="Bob", state=first.roster_json)
        written = write_enrollment(self.scratch, second, source_root=self.source)
        self.assertEqual([player["name"] for player in
                          json.loads(Path(written["state"]).read_text())["players"]],
                         ["Alice", "Bob"])


class PersistentTracksTest(unittest.TestCase):
    def test_ranking_by_appearances(self):
        observations = [
            observation(0, [person(1), person(2, OTHER_PERSON)], []),
            observation(15, [person(1), person(2, OTHER_PERSON)], []),
            observation(30, [person(2, OTHER_PERSON)], []),
        ]
        rows = persistent_tracks(observations)
        self.assertEqual([row["track_id"] for row in rows], [2, 1])
        self.assertEqual(rows[0]["frames"], 3)
        self.assertEqual(rows[1]["frames"], 2)
        self.assertEqual(persistent_tracks(observations, limit=1)[0]["track_id"], 2)


class ScanFramesTest(unittest.TestCase):
    """The real adapter, with injected detector/engine: decode + tracking only."""

    VIDEO = Path(__file__).resolve().parents[1] / "data" / "vod_30min_260815.mp4"

    class _Detector:
        def __init__(self):
            self.calls = 0

        def __call__(self, frame):
            self.calls += 1
            return [{"bbox": [100.0, 100.0, 300.0, 600.0], "conf": 0.9},
                    {"bbox": [700.0, 100.0, 900.0, 600.0], "conf": 0.8}]

    class _Engine:
        def analyze(self, frame):
            return [{"bbox": [150.0, 150.0, 190.0, 200.0], "eye_px": 12.5, "det_score": 0.8,
                     "embedding": unit(41)},
                    {"bbox": [650.0, 150.0, 690.0, 200.0], "eye_px": 9.0, "det_score": 0.3,
                     "embedding": unit(42)}]

    @unittest.skipUnless(VIDEO.is_file(), "the vod30 recording is not present")
    def test_scan_links_tracks_and_stores_embeddings_above_the_gate(self):
        detector, engine = self._Detector(), self._Engine()
        observations = scan_frames(self.VIDEO.parent, "vod30", 0, 90, stride=30,
                                   detector=detector, engine=engine, log=lambda *a, **k: None)
        self.assertEqual([row["frame_index"] for row in observations], [0, 30, 60])
        self.assertEqual(detector.calls, 3)
        first = observations[0]
        self.assertEqual([p["track_id"] for p in first["persons"]], [1, 2])
        self.assertEqual([p["track_id"] for p in observations[1]["persons"]], [1, 2],
                         "the same boxes keep their track across frames")
        faces = first["faces"]
        self.assertEqual(faces[0]["embedding"] is not None, True)
        self.assertIsNone(faces[1]["embedding"], "below the detection gate: no embedding stored")
        self.assertEqual(first["t"], 0.0)

    @unittest.skipUnless(VIDEO.is_file(), "the vod30 recording is not present")
    def test_scan_of_an_empty_range_is_empty(self):
        rows = scan_frames(self.VIDEO.parent, "vod30", 10, 10, stride=30,
                           detector=self._Detector(), engine=self._Engine(),
                           log=lambda *a, **k: None)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless((Path(__file__).resolve().parents[1] / "data" / "vod_30min_260815.mp4").is_file(),
                     "the vod30 recording is not present")
class SelectionSeamTest(unittest.TestCase):
    """plan_for_selection -> preview_payload -> confirm_enrollment, with a fake scan.

    The crops are rendered from the real recording (a few frame seeks), through a
    symlinked data/ so the temp root stays a workspace root.
    """

    VIDEO = Path(__file__).resolve().parents[1] / "data" / "vod_30min_260815.mp4"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").symlink_to(Path(__file__).resolve().parents[1] / "data")
        (self.root / "out" / "corner-pocket").mkdir(parents=True)
        (self.root / "out" / "corner-pocket" / "state.json").write_text(
            json.dumps(state_with()), encoding="utf-8")
        self.base = unit(71)
        self.other_base = unit(171)
        self.observations = []
        for index in range(6):
            self.observations.append(observation(
                index * 30,
                [person(1, [100, 100, 300, 600]), person(2, OTHER_PERSON)],
                [face([150, 150, 190, 200], embedding=at(self.base, 0.9 - 0.01 * index, 200 + index)),
                 face([750, 150, 790, 200],
                      embedding=at(self.other_base, 0.9 - 0.01 * index, 300 + index))]))

    def _plan(self, **kwargs):
        return plan_for_selection(self.root, "vod30", 0, [100, 100, 300, 600],
                                  observations=self.observations, **kwargs)

    def test_clicks_lock_onto_the_best_overlapping_track(self):
        selection = self._plan()
        self.assertIsInstance(selection, Selection)
        self.assertEqual(selection.track_id, 1)
        self.assertAlmostEqual(selection.selection_iou, 1.0, places=4)
        self.assertEqual(selection.frames_seen, 6)
        self.assertEqual(selection.frame_index, 0)

    def test_a_click_on_the_other_person_locks_onto_the_other_track(self):
        selection = plan_for_selection(self.root, "vod30", 30, [700, 100, 900, 600],
                                       observations=self.observations)
        self.assertEqual(selection.track_id, 2)
        self.assertNotEqual(selection.enrollment.evidence["track_id"], 1)

    def test_selection_not_matched_when_nothing_overlaps(self):
        refusal = plan_for_selection(self.root, "vod30", 0, [900, 500, 1000, 600],
                                     observations=self.observations)
        self.assertIsInstance(refusal, Refusal)
        self.assertEqual(refusal.reason, "selection_not_matched")
        self.assertIn("best_overlap", refusal.detail)

    def test_selection_not_matched_when_the_frame_is_outside_the_scan(self):
        refusal = plan_for_selection(self.root, "vod30", 99999, [100, 100, 300, 600],
                                     observations=self.observations)
        self.assertEqual(refusal.reason, "selection_not_matched")
        self.assertIn("outside the scanned range", refusal.detail["detail"])

    def test_a_refused_track_keeps_the_selection_evidence(self):
        observations = [observation(index * 30, [person(1)], [])
                        for index in range(3)]
        refusal = plan_for_selection(self.root, "vod30", 0, [100, 100, 300, 600],
                                     observations=observations)
        self.assertEqual(refusal.reason, "no_face_in_track")
        self.assertEqual(refusal.detail["track_id"], 1)
        self.assertEqual(refusal.detail["frames_seen"], 3)
        self.assertIn("selection_iou", refusal.detail)


class PreviewPayloadTest(SelectionSeamTest):
    """Preview is JSON-safe and never writes."""

    def test_a_selection_preview_payload_is_json_round_trippable(self):
        payload = preview_payload(self._plan(), root=self.root)
        again = json.loads(json.dumps(payload))
        self.assertEqual(again, payload)

    def test_preview_shape_matches_the_contract(self):
        payload = preview_payload(self._plan(), root=self.root)
        for key in ("ok", "dataset", "frame_index", "track_id", "selection_iou", "frames_seen",
                    "crops", "purity", "quality", "token"):
            self.assertIn(key, payload)
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["track_id"], 1)
        self.assertEqual(len(payload["token"]), 64)
        self.assertGreaterEqual(len(payload["crops"]), 1)

    def test_crops_carry_a_data_url_and_are_small(self):
        payload = preview_payload(self._plan(), root=self.root)
        for crop in payload["crops"]:
            self.assertTrue(crop["jpeg_data_url"].startswith("data:image/jpeg;base64,"))
            self.assertEqual(sorted(crop), ["det_score", "eye_px", "frame_index", "index",
                                            "jpeg_data_url", "t"])
            self.assertLess(len(crop["jpeg_data_url"]), CROP_MAX_BYTES,
                            "the data URL stays inside the per-crop budget")

    def test_payload_has_no_non_json_types(self):
        payload = preview_payload(self._plan(), root=self.root)
        stack = [payload]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                self.assertTrue(all(isinstance(key, str) for key in value))
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
            else:
                self.assertNotIsInstance(value, (np.generic, np.ndarray, Path, bytes))

    def test_preview_writes_nothing(self):
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        preview_payload(self._plan(), root=self.root)
        self.assertEqual(sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")),
                         before)

    def test_a_refusal_preview_carries_the_faces_it_saw(self):
        observations = [observation(index * 30, [person(1)],
                                    [face([150, 150, 190, 200], eye=3.0)])
                        for index in range(3)]
        refusal = plan_for_selection(self.root, "vod30", 0, [100, 100, 300, 600],
                                     observations=observations)
        self.assertEqual(refusal.reason, "face_too_small")
        payload = preview_payload(refusal, root=self.root, dataset="vod30")
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["reason"], "face_too_small")
        self.assertTrue(payload["message"])
        self.assertEqual(len(payload["crops"]), 3, "the faces we saw are shown, gated or not")
        self.assertTrue(payload["crops"][0]["jpeg_data_url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("token", payload)

    def test_a_refusal_preview_without_observations_is_still_json(self):
        payload = preview_payload(Refusal("no_face_in_track", {"track_id": 5}),
                                  root=self.root, dataset="vod30")
        self.assertEqual(payload["crops"], [])
        self.assertEqual(json.loads(json.dumps(payload))["reason"], "no_face_in_track")


class TokenTest(SelectionSeamTest):
    def test_token_is_stable_for_the_same_crops(self):
        payload = preview_payload(self._plan(), root=self.root)
        again = enrollment_token("vod30", 1, payload["crops"])
        self.assertEqual(again, payload["token"])

    def test_token_accepts_bytes_or_data_urls(self):
        payload = preview_payload(self._plan(), root=self.root)
        from_bytes = enrollment_token("vod30", 1, payload["crops"])
        from_urls = enrollment_token("vod30", 1, [{"frame_index": crop["frame_index"],
                                                   "jpeg_data_url": crop["jpeg_data_url"]}
                                                  for crop in payload["crops"]])
        self.assertEqual(from_bytes, from_urls)

    def test_swapping_a_crop_changes_the_token(self):
        payload = preview_payload(self._plan(), root=self.root)
        moved = [dict(crop) for crop in payload["crops"]]
        moved[0]["frame_index"] += 1
        self.assertNotEqual(enrollment_token("vod30", 1, moved), payload["token"])

    def test_track_and_dataset_are_part_of_the_token(self):
        payload = preview_payload(self._plan(), root=self.root)
        self.assertNotEqual(enrollment_token("vod30", 2, payload["crops"]), payload["token"])
        self.assertNotEqual(enrollment_token("highlight", 1, payload["crops"]), payload["token"])

    def test_a_crop_without_bytes_is_rejected(self):
        with self.assertRaises(ValueError):
            enrollment_token("vod30", 1, [{"frame_index": 0}])


class ConfirmTest(SelectionSeamTest):
    def _scratch(self):
        return self.root / "scratch"

    def test_confirm_writes_the_roster_and_the_face_store(self):
        selection = self._plan()
        payload = preview_payload(selection, root=self.root)
        result = confirm_enrollment(self.root, selection, payload["token"], "Alice",
                                    scratch_root=self._scratch())
        self.assertTrue(result["ok"])
        self.assertEqual(result["embeddings"], 5)
        self.assertEqual(result["event"], "player_enroll_from_tracklet")
        self.assertEqual(result["revision"], 5)
        state = json.loads((self._scratch() / DEFAULT_STATE).read_text())
        self.assertEqual([player["name"] for player in state["players"]], ["Alice"])
        store = json.loads((self._scratch() / DEFAULT_FACE_STORE).read_text())
        self.assertEqual(len(list(store.values())[0]), 5)
        self.assertEqual(md5(self.root / DEFAULT_STATE), self.source_state_md5())

    def source_state_md5(self):
        return md5(self.root / "out" / "corner-pocket" / "state.json")

    def test_a_stale_token_is_refused_and_nothing_is_written(self):
        selection = self._plan()
        payload = preview_payload(selection, root=self.root)
        other = plan_for_selection(self.root, "vod30", 30, [700, 100, 900, 600],
                                   observations=self.observations)
        stale = preview_payload(other, root=self.root)["token"]
        with self.assertRaises(EnrollmentTokenError) as ctx:
            confirm_enrollment(self.root, selection, stale, "Alice", scratch_root=self._scratch())
        self.assertEqual(ctx.exception.reason, "token_mismatch")
        self.assertEqual(ctx.exception.to_dict()["ok"], False)
        self.assertFalse(self._scratch().exists(), "a refused confirmation writes nothing")
        self.assertEqual(md5(self.root / DEFAULT_STATE), self.source_state_md5())

    def test_a_tampered_token_is_refused(self):
        selection = self._plan()
        token = preview_payload(selection, root=self.root)["token"]
        for bad in (token[:-1] + ("0" if token[-1] != "0" else "1"), "", None, 12345):
            with self.assertRaises(EnrollmentTokenError):
                confirm_enrollment(self.root, selection, bad, "Alice", scratch_root=self._scratch())
        self.assertFalse(self._scratch().exists())

    def test_a_missing_name_is_refused(self):
        selection = self._plan()
        token = preview_payload(selection, root=self.root)["token"]
        with self.assertRaises(EnrollmentTokenError) as ctx:
            confirm_enrollment(self.root, selection, token, "   ", scratch_root=self._scratch())
        self.assertEqual(ctx.exception.reason, "player_name_required")
        self.assertFalse(self._scratch().exists())

    def test_confirm_needs_a_selection(self):
        with self.assertRaises(ValueError):
            confirm_enrollment(self.root, Refusal("no_face_in_track"), "x", "Alice")

    def test_the_roster_revision_advances_from_the_existing_state(self):
        selection = self._plan()
        token = preview_payload(selection, root=self.root)["token"]
        first = confirm_enrollment(self.root, selection, token, "Alice", scratch_root=self._scratch())
        second = plan_for_selection(self.root, "vod30", 0, [700, 100, 900, 600],
                                    observations=self.observations)
        token2 = preview_payload(second, root=self.root)["token"]
        result = confirm_enrollment(self.root, second, token2, "Bob",
                                    scratch_root=self._scratch(),
                                    state=load_state(self._scratch()))
        self.assertEqual(first["revision"], 5)
        self.assertEqual(result["revision"], 6)
        names = [player["name"] for player in
                 json.loads((self._scratch() / DEFAULT_STATE).read_text())["players"]]
        self.assertEqual(names, ["Alice", "Bob"])
