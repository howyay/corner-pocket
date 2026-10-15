"""Pins for the per-segment calibration reference.

Two things must hold for a per-segment reference to be safer than the single ``H``
it replaces:

1. **a frame resolves to exactly one segment** - a lookup that can return two
   references, or none, is worse than the status quo it fixes;
2. **an out-of-range frame falls back cleanly** - a time before the first segment,
   after the last, or absent entirely gets a defined reference and a flag, never
   an exception and never silence.

The artifact's shape is pinned too: the consumers (``src/table_refine.prior_for``,
the server's event geometry) read named fields, so a producer that renames or
drops one must fail here rather than silently disable per-segment projection.
"""
import ast
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import calib_segments as cs  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from _shipped import code_strings, shipped_modules  # noqa: E402

ARTIFACT = ROOT / "out" / "calib_vod30_segments.json"
TEMPLATE = cs.ARTIFACT
MARKER_NAME = "calib_vod30_segments.json"


def write_artifact(out, segments, verdict="split_supported"):
    out.mkdir(parents=True, exist_ok=True)
    payload = {"dataset": "vod30", "segmentation_verdict": verdict, "segments": segments}
    (out / "calib_vod30_segments.json").write_text(json.dumps(payload))
    return payload


def seg(seg_id, t_start, t_end, x=100.0, source="human_anchors"):
    return {"id": seg_id, "t_start": t_start, "t_end": t_end, "source": source,
            "quad_px": [[x, 100.0], [x + 500, 110.0], [x + 520, 500.0], [x - 20, 490.0]],
            "coverage": {"median": 0.99}, "evidence": {"trusted_for_mm": True}}


class SegmentLookupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_artifact(self.root / "out", [seg("a", 0.0, 600.0),
                                            seg("b", 600.001, 1800.0, x=80.0, source="derived")])
        self.model = cs.load("vod30", root=self.root, use_cache=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_frame_resolves_to_exactly_one_segment(self):
        for t in (0.0, 1.0, 599.9, 600.0, 600.001, 1200.0, 1800.0):
            seg = self.model.resolve(t)
            self.assertIsNotNone(seg, t)
            matches = [s for s in self.model.segments if s.t_start <= t <= s.t_end]
            self.assertEqual(len(matches), 1, f"t={t} matches {len(matches)} segments")
            self.assertEqual(seg.id, matches[0].id)
            self.assertFalse(seg.clamped, t)
        self.assertEqual(self.model.resolve(300.0).id, "a")
        self.assertEqual(self.model.resolve(300.0).source, "human_anchors")
        self.assertEqual(self.model.resolve(1200.0).id, "b")
        self.assertTrue(self.model.resolve(1200.0).human is False)
        self.assertEqual(self.model.resolve(1200.0).source, "derived")

    def test_out_of_range_frame_falls_back_cleanly(self):
        for t, expected in ((-5.0, "a"), (1800.001, "b"), (1e9, "b")):
            seg = self.model.resolve(t)
            self.assertEqual(seg.id, expected, t)
            self.assertTrue(seg.clamped, t)
            self.assertEqual(seg.clamp_reason, "outside_all_segments")
            self.assertFalse(self.model.in_range(t), t)
            self.assertEqual(len(seg.quad), 4, "a clamped lookup still returns usable geometry")
        for t in (None, float("nan"), "not-a-time"):
            seg = self.model.resolve(t)
            self.assertEqual(seg.id, "a")
            self.assertTrue(seg.clamped)
            self.assertEqual(seg.clamp_reason, "no_time")

    def test_in_range_is_exact_and_clamping_does_not_mutate_the_model(self):
        self.assertTrue(self.model.in_range(300.0))
        self.assertTrue(self.model.in_range(1800.0))
        self.assertFalse(self.model.in_range(1800.5))
        self.assertFalse(self.model.in_range(None))
        before = [s.as_dict() for s in self.model.segments]
        self.model.resolve(99999)
        self.model.resolve(None)
        self.assertEqual([s.as_dict() for s in self.model.segments], before)

    def test_homography_tracks_the_segment_and_round_trips(self):
        forward_a, inverse_a, seg_a = self.model.homographies(10.0)
        forward_b, inverse_b, seg_b = self.model.homographies(1000.0)
        self.assertEqual((seg_a.id, seg_b.id), ("a", "b"))
        for forward, inverse in ((forward_a, inverse_a), (forward_b, inverse_b)):
            px = np.array([300.0, 250.0, 1.0])
            mm = forward @ px
            mm = mm[:2] / mm[2]
            back = inverse @ np.array([mm[0], mm[1], 1.0])
            back = back[:2] / back[2]
            self.assertTrue(np.allclose(back, px[:2], atol=0.5))
        self.assertLess(abs(forward_a[0][2] - forward_b[0][2]), 1e9)
        self.assertNotEqual(self.model.quad_for(10.0).tolist(), self.model.quad_for(1000.0).tolist())

    def test_overlapping_segments_are_reported_and_first_wins(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_artifact(root / "out", [seg("a", 0.0, 700.0), seg("b", 600.0, 1800.0, x=80.0)])
            model = cs.load("vod30", root=root, use_cache=False)
            self.assertTrue(model.warnings, "an overlap must be reported, not silently resolved")
            self.assertTrue(any("overlap" in w for w in model.warnings))
            self.assertEqual(model.resolve(650.0).id, "a")
            self.assertTrue(model.resolve(1000.0).id == "b")

    def test_missing_or_broken_artifact_is_not_an_error(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(cs.load("vod30", root=root, use_cache=False))
            (root / "out").mkdir(parents=True)
            (root / "out" / "calib_vod30_segments.json").write_text("{not json")
            self.assertIsNone(cs.load("vod30", root=root, use_cache=False))
            write_artifact(root / "out", [])
            self.assertIsNone(cs.load("vod30", root=root, use_cache=False),
                              "an artifact with no segments is not a reference")
            write_artifact(root / "out", [{"id": "x", "t_start": 0, "t_end": 10,
                                           "quad_px": [[0, 0], [1, 1]]}])
            self.assertIsNone(cs.load("vod30", root=root, use_cache=False),
                              "a malformed quad must be dropped, not raised")

    def test_gaps_are_reported(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_artifact(root / "out", [seg("a", 0.0, 100.0), seg("b", 200.0, 300.0, x=80.0)])
            model = cs.load("vod30", root=root, use_cache=False)
            self.assertEqual(model.gaps(), [(100.0, 200.0)])
            self.assertEqual(model.resolve(150.0).id, "a", "a gap clamps to the nearest segment")
            self.assertTrue(model.resolve(150.0).clamped)

    def test_prior_for_uses_the_segment_when_one_exists(self):
        from src import table_refine
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_artifact(root / "out", [seg("a", 0.0, 600.0), seg("b", 600.001, 1800.0, x=80.0)])
            (root / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
                {"anchors": {"70.0": [[10, 10], [20, 10], [20, 20], [10, 20], [1, 1], [2, 2]]}}))
            early = table_refine.prior_for("vod30", 100.0, root=root)
            late = table_refine.prior_for("vod30", 1500.0, root=root)
            self.assertIsNotNone(early)
            self.assertIsNotNone(late)
            self.assertNotEqual(np.asarray(early).tolist(), np.asarray(late).tolist(),
                                "the late segment must not reuse the early reference")
            prov = table_refine.prior_provenance("vod30", 1500.0, root=root)
            self.assertEqual((prov["kind"], prov["id"]), ("segment", "b"))
            # ...and without the artifact the saved prior answers exactly as before.
            bare = Path(tmp) / "bare"
            (bare / "out").mkdir(parents=True)
            (bare / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
                {"anchors": {"70.0": [[10, 10], [20, 10], [20, 20], [10, 20], [1, 1], [2, 2]]}}))
            self.assertEqual(np.asarray(table_refine.prior_for("vod30", 1500.0, root=bare)).shape, (4, 2))
            self.assertEqual(table_refine.prior_provenance("vod30", 1500.0, root=bare)["kind"],
                             "saved_prior")


class CalibrationNameOwnerTest(unittest.TestCase):
    """The name of the calibration document has one home: ``src/calib_segments.py``.

    ``calib_vod30.json`` stood four times: the template of ``src/store.py``, the
    tool that writes the document, and two readers.  A rename that moved three of
    the four left the fourth reading a file that does not exist.  The owner
    answers the name, and each reader reads that answer.

    The store reads the name as a row of its kind -> file map, as it reads
    ``ARTIFACT`` for the segments document.  ``test_the_kind_map_reads_the_owner``
    is the model of the two cases below, and
    ``test_the_calibration_row_reads_the_owner`` holds the second row to it.
    """
    #: The source of the owner, and the declaration that holds the template.
    OWNER_MODULE = "src/calib_segments.py"
    OWNER_DECLARATION = "CALIBRATION"
    OWNER_READER = "calibration_name"
    #: The tool that writes one document, and the two readers of one document.
    DOCUMENT_READERS = {
        "src/calib_vod30.py": "calibration_name",
        "src/pid_anchor_ui.py": "calibration_name",
        "src/pid_shooter.py": "calibration_name",
    }
    #: The map of ``src/store.py``, and the row this round moved to the owner.
    MAP_MODULE = "src/store.py"
    MAP_NAME = "ARTIFACTS"
    MAP_ROW = "calibration"
    #: The one dataset this repository builds, and the document name of it.
    DATASET = "vod30"
    DOC_NAME = "calib_vod30.json"
    #: The owner's keyword, and the placeholder of the map's rows.
    FORMATTING_KEYS = ("ds", "dataset")

    def shipped_files(self):
        """The shipped modules, as (repository-relative name, tree)."""
        out = []
        for path in shipped_modules():
            name = path.relative_to(ROOT).as_posix()
            out.append((name, ast.parse(path.read_text(encoding="utf-8"))))
        return out

    def doc_literals(self, tree):
        """(line, text) for the literals of one tree that hold the document name.

        Three shapes carry the name: the whole text of one dataset, the template
        with the owner's keyword, and the map's spelling ``calib_{ds}.json``.
        """
        out = []
        for line, text in code_strings(tree):
            if "calib_" not in text or not text.endswith(".json"):
                continue
            if text == self.DOC_NAME or any(key in text for key in self.FORMATTING_KEYS):
                out.append((line, text))
        return out

    def known_reader(self, name, text):
        """True when one shipped module reads the owner, or is the owner itself."""
        return name == self.OWNER_MODULE or self.OWNER_READER in text

    def test_the_calibration_row_reads_the_owner(self):
        """The row of ``src/store.py`` reads the owner, and does not spell the name.

        The row stood as the literal ``"calib_{ds}.json"``.  The segments row of
        the same map already reads the owner, and this row was the copy the owner
        could not move.  A row that spells the text again fails here, and the
        failure names the row and not the file that holds the map.
        """
        from src import store

        tree = ast.parse((ROOT / self.MAP_MODULE).read_text(encoding="utf-8"))
        rows = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if self.MAP_NAME not in targets or not isinstance(node.value, ast.Dict):
                continue
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    rows[key.value] = value
        self.assertIn(self.MAP_ROW, rows, f"the map must keep the {self.MAP_ROW} row")
        row = rows[self.MAP_ROW]
        self.assertNotIsInstance(row, ast.Constant,
                                 "the row spells the file name again; it must read the owner")
        self.assertEqual(ast.unparse(row), self.OWNER_DECLARATION,
                         "the row must read the owner's CALIBRATION")
        self.assertEqual(store.ARTIFACTS.get(self.MAP_ROW), cs.CALIBRATION,
                         "the row must hold the owner's template, not a second text")
        # The row's own placeholder is the owner's keyword, so the format call of
        # artifact() fills it.
        self.assertIn("{dataset}", store.ARTIFACTS[self.MAP_ROW],
                      "the row must carry the owner's keyword")

    def test_every_known_reader_of_the_document_reads_the_owner(self):
        """The three sites that name the document read the owner's answer.

        The name stood at ``src/calib_vod30.py:157``, ``src/pid_anchor_ui.py:39``
        and ``src/pid_shooter.py:44``.  Each site resolves the same path after the
        move: ``calibration_name`` answers the text the literal held.
        """
        files = dict(self.shipped_files())
        for name in self.DOCUMENT_READERS:
            found = self.doc_literals(files[name])
            shapes = [(line, text) for line, text in found if text == self.DOC_NAME]
            read = any(
                (isinstance(node, ast.Call) and ast.unparse(node.func) == self.OWNER_READER)
                for node in ast.walk(files[name]))
            self.assertEqual(shapes, [],
                             f"{name} spells the whole file name: {shapes}")
            self.assertTrue(read,
                            f"{name} must call {self.OWNER_READER}, and it does not")

    def test_the_document_name_stands_once_in_the_shipped_tree(self):
        """One shipped reader still holds the whole name, and the owner holds the rest.

        ``annotator/unified_server.py:2149`` reads ``self.out / "calib_vod30.json"``
        in ``anchor_info``.  That file belongs to another writer this round, so the
        list holds the owner and that one site.  A third site fails here, and the
        failure names it.
        """
        offenders = {}
        for name, tree in self.shipped_files():
            if name == self.OWNER_MODULE:
                continue
            text = ast.unparse(tree)
            found = self.doc_literals(tree)
            if found and not self.known_reader(name, text):
                offenders[name] = found
        self.assertEqual(sorted(offenders), ["annotator/unified_server.py"],
                         f"the reader that holds the whole name changed: {offenders}")
        self.assertEqual([text for _, text in offenders["annotator/unified_server.py"]],
                         [self.DOC_NAME],
                         "the row must hold the text of one dataset and nothing else")

    def test_the_reader_answers_the_name_of_one_dataset(self):
        """The owner's reader answers the text, and no known reader holds it."""
        self.assertEqual(cs.calibration_name(self.DATASET), self.DOC_NAME,
                         "the reader must answer the document name of the dataset")
        self.assertIn("{dataset}", cs.CALIBRATION,
                      "the owner's template must carry the keyword of the format call")
        files = dict(self.shipped_files())
        owner = ast.unparse(files[self.OWNER_MODULE])
        self.assertIn(repr(cs.CALIBRATION), owner,
                      "the owner holds the one template of the document name")
        for name in sorted(self.DOCUMENT_READERS):
            found = [f for f in self.doc_literals(files[name]) if f[1] == self.DOC_NAME]
            self.assertEqual(found, [], f"{name} spells the whole file name again: {found}")

    def test_the_scan_sees_a_bitten_module(self):
        """The case above has teeth: a planted literal fails it.

        A guard that reads no literal passes on a tree that spells the name
        everywhere.  This case plants one module and holds its answer, so a later
        edit that flattens the scan fails here.
        """
        planted = ast.parse(
            "import json\n"
            "def dump(out, root):\n"
            '    path = root / "out" / "calib_vod30.json"\n'
            "    path.write_text(json.dumps(out))\n")
        found = self.doc_literals(planted)
        self.assertEqual([text for _, text in found], [self.DOC_NAME],
                         "the scan must see the planted name")
        offender = {"src/planted.py": found}
        self.assertNotEqual(offender, {}, "the guard must fail on a second home")
        self.assertFalse(self.known_reader("src/planted.py", ast.unparse(planted)),
                         "the planted module reads no owner, so it must fail")


class ArtifactShapeTest(unittest.TestCase):
    """The shipped artifact must carry every field the consumers read."""

    @classmethod
    def setUpClass(cls):
        if not ARTIFACT.is_file():
            raise unittest.SkipTest("out/calib_vod30_segments.json not built")
        cls.payload = json.loads(ARTIFACT.read_text())
        cls.model = cs.load("vod30", path=ARTIFACT, use_cache=False)

    def test_top_level_fields(self):
        for key in ("dataset", "video", "frame_size", "canonical_mm", "segmentation_verdict",
                    "verdict_reason", "framing_test", "segments", "boundary_candidates",
                    "late_window_alternative", "notes"):
            self.assertIn(key, self.payload, key)
        self.assertEqual(self.payload["dataset"], "vod30")
        self.assertEqual(self.payload["frame_size"], [1280, 720])
        self.assertEqual(self.payload["canonical_mm"], {"w": 1270.0, "h": 2540.0})
        self.assertIn(self.payload["segmentation_verdict"], ("single_segment", "split_supported"))

    def test_every_segment_carries_the_required_fields(self):
        self.assertTrue(self.payload["segments"])
        for segment in self.payload["segments"]:
            for key in ("id", "t_start", "t_end", "quad_px", "source", "coverage", "evidence"):
                self.assertIn(key, segment, key)
            self.assertIn(segment["source"], cs.SOURCES)
            self.assertLess(segment["t_start"], segment["t_end"])
            quad = np.asarray(segment["quad_px"], float)
            self.assertEqual(quad.shape, (4, 2))
            self.assertTrue(0 <= quad[:, 0].max() <= 1280 and 0 <= quad[:, 1].max() <= 720)
            self.assertIn("metric", segment["coverage"])
            self.assertIn("median", segment["coverage"])
            self.assertIn("frames_below_gate", segment["coverage"])
            evidence = segment["evidence"]
            self.assertIn("phase_shift_max_px", evidence)
            self.assertIn("per_side_offset_px", evidence)
            self.assertIn("verified_samples", evidence)
            self.assertIn("frames_all_four_sides_verified", evidence)

    def test_the_segment_covers_every_sampled_time(self):
        seg = self.payload["segments"][0]
        sampled = [s["t"] for s in self.payload["framing_test"]["samples"]]
        self.assertTrue(sampled)
        self.assertLessEqual(seg["t_start"], min(sampled))
        self.assertGreaterEqual(seg["t_end"], max(sampled))
        for t in sampled:
            self.assertTrue(self.model.in_range(t), t)

    def test_the_framing_test_did_not_fire_where_coverage_dropped(self):
        """A coverage dip is not a framing change - the whole point of the artifact."""
        below = [b for b in self.payload["boundary_candidates"]
                 if b["cause"] != "coverage_above_gate"]
        self.assertTrue(below, "the measured times the gate flagged must be recorded")
        for boundary in below:
            self.assertIn("framing_change", boundary)
            self.assertIn("coverage", boundary)
            if self.payload["segmentation_verdict"] == "single_segment":
                self.assertFalse(boundary["framing_change"],
                                 f"t={boundary['t']} was called a framing change under a "
                                 f"single-segment verdict")

    def test_late_alternative_is_counterfactual_and_recorded_as_derived(self):
        alt = self.payload["late_window_alternative"]
        self.assertIsNotNone(alt)
        self.assertFalse(alt["used"], "an unsupported split must not be in use")
        self.assertEqual(alt["source"], "derived")
        self.assertEqual(np.asarray(alt["quad_px"], float).shape, (4, 2))
        self.assertIn("agreement_with_segments", alt)
        self.assertIn("max_mm", alt["agreement_with_segments"])
        self.assertIn("per_side_evidence_gate", alt)
        self.assertIn("passed", alt["per_side_evidence_gate"])

    def test_human_source_is_never_claimed_by_a_derived_quad(self):
        for segment in self.payload["segments"]:
            if segment["source"] == "human_anchors":
                self.assertIn("pid_anchors", json.dumps(segment["source_detail"]))


class EventProjectionWiringTest(unittest.TestCase):
    """The server projects an event through its own segment - when there is one.

    Two pins, and the second is the more important one:

    * a ``split_supported`` artifact routes each event through the segment that
      owns its time, so a late-segment event is NOT drawn with the early reference;
    * a ``single_segment`` artifact changes **no pixels** - it only records which
      segment owns the time.  Swapping the drawn geometry there would replace the
      scan's self-consistent mapping with the cloth-quad calibration on evidence
      that says nothing about which the reviewer wants, and on vod30 those two
      disagree by up to 93 px at the head rail.
    """

    QUAD = [[100, 100], [1100, 120], [1120, 620], [90, 600]]
    EVENTS = [
        {"id": 7, "t": 5.6, "type": "pot", "last_mm": [5.0, 1270.0],
         "nearest_pocket": "left-side (5mm)"},
        {"id": 8, "t": 1400.0, "type": "shot", "disp_mm": 172, "ball_from": [100.0, 200.0],
         "ball_to": [300.0, 400.0]},
    ]

    def backend(self, temp, artifact=None):
        from annotator.unified_server import Backend, ReadQuery, atomic_save
        out = Path(temp) / "out"
        atomic_save(out / "scan30" / "corners.json", {"corners": self.QUAD})
        atomic_save(out / "scan30" / "events.json", self.EVENTS)
        if artifact is not None:
            atomic_save(out / "calib_vod30_segments.json", artifact)
        return Backend(temp)

    @staticmethod
    def pixels(payload):
        return {event["id"]: (event["type"], event.get("px_source"), event.get("px_segment"),
                              event.get("last_px"), event.get("from_px"), event.get("to_px"))
                for event in payload["events"]}

    def test_single_segment_records_the_segment_without_moving_pixels(self):
        from annotator.unified_server import ReadQuery
        with TemporaryDirectory() as tmp_bare, TemporaryDirectory() as tmp_seg:
            bare = self.backend(tmp_bare)
            write_artifact(Path(tmp_seg) / "out", [seg("s1", 0.0, 1800.0, x=100.0)],
                           verdict="single_segment")
            with_seg = self.backend(tmp_seg, json.loads(
                (Path(tmp_seg) / "out" / "calib_vod30_segments.json").read_text()))
            before = bare.get(["api", "vod30", "events"], ReadQuery())
            after = with_seg.get(["api", "vod30", "events"], ReadQuery())
            self.assertEqual(before["geometry"], after["geometry"])
            self.assertEqual(set(self.pixels(before)), set(self.pixels(after)))
            for event_id, cell in self.pixels(before).items():
                drawn = self.pixels(after)[event_id]
                self.assertEqual(drawn[1], cell[1],
                                 "a single-segment artifact must not move an event's pixels")
                self.assertEqual((drawn[3], drawn[4], drawn[5]), (cell[3], cell[4], cell[5]),
                                 event_id)
                self.assertEqual(drawn[2], "s1",
                                 "the segment that owns the time is still recorded")

    def test_split_artifact_projects_a_late_event_with_its_own_segment(self):
        from annotator.unified_server import ReadQuery
        with TemporaryDirectory() as tmp:
            late = seg("late", 600.001, 1800.0, x=400.0, source="derived")
            write_artifact(Path(tmp) / "out", [seg("early", 0.0, 600.0, x=100.0), late])
            backend = self.backend(tmp, json.loads(
                (Path(tmp) / "out" / "calib_vod30_segments.json").read_text()))
            payload = backend.get(["api", "vod30", "events"], ReadQuery())
            early, late_event = self.pixels(payload)[7], self.pixels(payload)[8]
            self.assertEqual(early[2], "early")
            self.assertEqual(late_event[2], "late")
            self.assertTrue(late_event[1].startswith("segment late"), late_event[1])
            self.assertTrue(late_event[4] and late_event[5])
            # The late event really is projected through the late quad: canonical
            # (100, 200) must land where that quad puts it.
            from src.pipeline import homography_to_canonical
            inverse = np.linalg.inv(homography_to_canonical(
                np.asarray(late["quad_px"], np.float32)))
            x, y, w = inverse @ np.array([100.0, 200.0, 1.0])
            self.assertAlmostEqual(late_event[4][0], round(float(x / w), 1), places=1)
            self.assertAlmostEqual(late_event[4][1], round(float(y / w), 1), places=1)


class ReferenceSeamTest(unittest.TestCase):
    """The seam answers with the quad *and* the file and entry it came from.

    A reader must be able to log where its reference came from without opening a
    file again, so the provenance is checked as a value, not as a file read.
    """

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_artifact(self.root / "out", [seg("a", 0.0, 600.0),
                                          seg("b", 600.001, 1800.0, x=80.0, source="derived")])
        (self.root / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
            {"anchors": {"70.0": [[10, 10], [20, 10], [20, 20], [10, 20], [1, 1], [2, 2]]}}))
        (self.root / "out" / "fixed_corners.json").write_text(json.dumps(
            {"corners": [[100, 100], [900, 100], [900, 500], [100, 500]]}))

    def tearDown(self):
        self.tmp.cleanup()

    def reference(self, dataset="vod30", **kwargs):
        return cs.resolve(dataset, root=self.root, use_cache=False, **kwargs)

    def test_the_seam_returns_the_quad_and_the_entry_that_owns_the_time(self):
        reference = self.reference(t=1500.0)
        self.assertTrue(reference.found)
        self.assertEqual(reference.kind, "segment")
        self.assertTrue(reference.per_time, "a segment artifact is a per-time reference")
        self.assertTrue(reference.artifact.endswith("calib_vod30_segments.json"))
        self.assertEqual(reference.entry, "b")
        self.assertEqual(reference.source, "derived")
        self.assertEqual((reference.t_start, reference.t_end), (600.001, 1800.0))
        self.assertFalse(reference.clamped)
        self.assertEqual(reference.quad.tolist(), seg("b", 600.001, 1800.0, x=80.0)["quad_px"])
        logged = reference.as_dict()
        self.assertEqual((logged["artifact"], logged["entry"], logged["per_time"]),
                         (reference.artifact, "b", True))
        self.assertEqual(logged["quad_px"], reference.quad.tolist())
        json.dumps(logged)                      # a reader can log it as it stands

    def test_an_unknown_time_takes_the_entry_the_per_time_rule_names(self):
        reference = self.reference()
        self.assertEqual(reference.entry, "a", "no time takes the first segment")
        self.assertTrue(reference.clamped)
        self.assertEqual(reference.clamp_reason, "no_time")
        self.assertIn("using the first", reference.note)
        self.assertIn("2 segments", reference.note)

    def test_a_saved_reference_file_is_one_static_reference(self):
        reference = self.reference("highlight")
        self.assertTrue(reference.found)
        self.assertEqual(reference.kind, "static")
        self.assertFalse(reference.per_time)
        self.assertTrue(reference.artifact.endswith("fixed_corners.json"))
        self.assertEqual(reference.entry, "corners")
        self.assertEqual(reference.quad.tolist(), [[100.0, 100.0], [900.0, 100.0],
                                                   [900.0, 500.0], [100.0, 500.0]])

    def test_the_hand_anchors_are_named_by_their_own_time_key(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir(parents=True)
            (root / "out" / "pid_anchors_vod30.json").write_text(json.dumps(
                {"anchors": {"70.0": [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12]]}}))
            reference = cs.resolve("vod30", 1500.0, root=root, use_cache=False)
            self.assertEqual(reference.kind, "static")
            self.assertEqual(reference.entry, "70.0", "the anchor key is the entry")
            self.assertEqual(reference.evidence, "hand anchors")
            self.assertEqual(reference.origin,
                             str(root / "out" / "pid_anchors_vod30.json"))

    def test_the_provenance_survives_the_artifact(self):
        reference = self.reference(t=10.0)
        (self.root / "out" / "calib_vod30_segments.json").unlink()
        logged = json.dumps(reference.as_dict())
        self.assertIn("calib_vod30_segments.json", logged)
        self.assertIn('"entry": "a"', logged)

    def test_the_refused_reference_is_never_selected(self):
        refused = self.root / "out" / "corners_30min_v2.json"
        refused.write_text(json.dumps({"corners": [[1, 1], [2, 1], [2, 2], [1, 2]]}))
        reference = self.reference(t=10.0, quad_file=refused)
        self.assertTrue(reference.found)
        self.assertNotIn(cs.REFUSED, reference.artifact or "")
        self.assertEqual(reference.artifact,
                         str(self.root / "out" / "calib_vod30_segments.json"))
        self.assertTrue(any("app-path-refusal.md" in line for line in reference.rejected),
                        "the refusal must be visible to the caller")
        for kind in cs.KINDS:
            self.assertNotIn(cs.REFUSED,
                             self.reference(t=10.0, kinds=(kind,)).artifact or "",
                             f"the {kind} step selected the refused reference")


class ReferenceTableTest(unittest.TestCase):
    """The (file, key) pair of a dataset has one home, and both readers read it.

    ``src/calib_segments.py`` ``STATIC_REFERENCES`` owns the pair.
    ``src/table_refine.py`` ``_DATASET_PRIOR`` reads that home through
    ``prior_spec``, so the two tables answer together.  The two datasets agreed
    before round 67 and the pair stood in both modules, so an edit of one copy was
    silent.  ``git grep -n "STATIC_REFERENCES" -- 'tests/*.py'`` answered 0 then, and
    this class is the guard it named.
    """

    #: The two readers of the pair, and the name each one reports for itself.
    READERS = ("src/calib_segments.py", "src/table_refine.py")

    def test_each_dataset_has_one_file_and_key_pair(self):
        """Both tables give a dataset one pair, and the pair is the owner's."""
        from src import table_refine as tr

        self.assertEqual(set(cs.STATIC_REFERENCES), set(tr._DATASET_PRIOR),
                         'the two tables hold different datasets')
        for dataset, owned in cs.STATIC_REFERENCES.items():
            with self.subTest(dataset=dataset):
                spec = tr.prior_spec(dataset)
                self.assertEqual((spec["file"], spec["key"]), (owned["file"], owned["key"]),
                                 f'{dataset}: the two tables name two reference files')
                self.assertIs(cs.reference_spec(dataset), owned,
                              f'{dataset}: the lookup must answer the owner entry itself')

    def test_the_pair_is_spelled_in_one_module_only(self):
        """src/table_refine.py holds no copy of the pair, so one edit moves both."""
        source = (ROOT / "src" / "table_refine.py").read_text()
        for owned in cs.STATIC_REFERENCES.values():
            with self.subTest(file=owned["file"]):
                self.assertNotIn(f'"{owned["file"]}"', source,
                                 'the pair stands in src/table_refine.py as well')

    def test_an_unknown_dataset_gets_no_reference_from_either_reader(self):
        """An unknown name takes no fallback: both readers answer None for it.

        The table served ``fixed_corners.json`` for any unknown name before round 67,
        while ``src/table_refine.py`` answered None.  The file belongs to the
        ``highlight`` entry alone, so the fallback gave an unknown dataset the
        geometry of another dataset in silence.
        """
        from src import table_refine as tr

        unknown = "a_dataset_neither_table_names"
        self.assertNotIn(unknown, cs.STATIC_REFERENCES)
        self.assertIsNone(cs.reference_spec(unknown))
        self.assertIsNone(tr.prior_spec(unknown))
        # The reader of the table answers a not-found reference, not the highlight file.
        reference = cs.static_reference(unknown)
        self.assertFalse(reference.found)
        self.assertIsNone(reference.quad)
        self.assertEqual(reference.artifact, None)
        self.assertNotIn("fixed_corners.json", json.dumps(reference.as_dict()))
        # The other reader answers nothing at all.
        self.assertIsNone(tr.prior_for(unknown))
        self.assertEqual(tr.prior_provenance(unknown)["kind"], "none")


class OldPathEquivalenceTest(unittest.TestCase):
    """The seam returns the array the old private loaders returned.

    The old rule is rebuilt here from the artifacts themselves: a test may read a
    file, and that is the point -- the readers no longer do.
    """

    @staticmethod
    def old_motion_scan_quad(artifact):
        """What ``motion_scan.load_quad`` returned for a segment artifact."""
        payload = json.loads(Path(artifact).read_text())
        quad = np.asarray(payload["segments"][0]["quad_px"], np.float64)
        return quad[:4].round(3).tolist()

    def test_the_real_artifact_answers_the_same_quad(self):
        if not ARTIFACT.is_file():
            self.skipTest("out/calib_vod30_segments.json not built")
        from src.motion_scan import load_quad
        quad = load_quad("vod30")
        self.assertEqual(quad["quad_px"], self.old_motion_scan_quad(ARTIFACT))
        self.assertEqual(quad["source"], str(ARTIFACT))
        self.assertTrue(quad["verified"])
        self.assertEqual(quad["rejected"], [])

    def test_a_missing_artifact_keeps_the_saved_reference(self):
        from src.motion_scan import load_quad
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            anchors = root / "out" / "pid_anchors_vod30.json"
            anchors.write_text(json.dumps(
                {"anchors": {"70.0": [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12]]}}))
            quad = load_quad("vod30", root=root)
            self.assertEqual(quad["quad_px"], [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
            self.assertEqual(quad["source"], str(anchors))
            self.assertEqual(quad["evidence"], "hand anchors")

    def test_a_quad_from_the_wrong_frame_size_is_still_refused(self):
        from src.motion_scan import load_quad
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "fixed_corners.json").write_text(json.dumps(
                {"corners": [[722, 452], [1177, 449], [1433, 844], [467, 849]]}))
            self.assertIsNotNone(load_quad("highlight", root=root,
                                           frame_size=(1920, 1080))["quad_px"])
            wrong = load_quad("highlight", root=root, frame_size=(1280, 720))
            self.assertIsNone(wrong["quad_px"])
            self.assertTrue(any("does not fit" in line for line in wrong["rejected"]))

    def test_timing_verify_reads_the_same_scan_quad(self):
        from src.timing_verify import load_quad as timing_load_quad
        path = ROOT / "out" / "scan30" / "corners.json"
        if not path.is_file():
            self.skipTest("out/scan30/corners.json is not present")
        old = np.asarray(json.loads(path.read_text())["corners"], np.float32)
        np.testing.assert_array_equal(timing_load_quad(str(path)), old)
        self.assertIsNone(timing_load_quad(None, str(path)),
                          "a corners file carries no anchors entry")

    def test_claim_calibration_projects_the_same_scan_frame(self):
        from src.eval_events import claim_calibration
        from src.pipeline import homography_to_canonical
        path = ROOT / "out" / "scan30" / "corners.json"
        if not path.is_file():
            self.skipTest("out/scan30/corners.json is not present")
        old = np.asarray(json.loads(path.read_text())["corners"], np.float32)
        inverse, label = claim_calibration(str(path))
        np.testing.assert_allclose(inverse, np.linalg.inv(homography_to_canonical(old)))
        self.assertEqual(label, f"scan claim frame ({path})")

    def test_reference_calibration_keeps_the_hand_anchor_mapping(self):
        from src.eval_events import reference_calibration
        from src.pipeline import homography_to_canonical
        anchors = ROOT / "out" / "pid_anchors_vod30.json"
        scan = ROOT / "out" / "scan30" / "corners.json"
        if not (anchors.is_file() and scan.is_file()):
            self.skipTest("the vod30 anchors or the scan quad are not present")
        first = next(iter(json.loads(anchors.read_text())["anchors"].values()))
        old = np.asarray(first[:4], np.float32)
        forward, inverse, label = reference_calibration(str(anchors), str(scan))
        np.testing.assert_allclose(forward, homography_to_canonical(old))
        self.assertEqual(label, "hand anchors on the cloth")

    def test_the_mapping_audit_keeps_its_old_quad_pair(self):
        from src.calib_mapping_audit import load_mappings
        from src.table_detect import _order_corners
        anchors = ROOT / "out" / "pid_anchors_vod30.json"
        scan = ROOT / "out" / "scan30" / "corners.json"
        if not (anchors.is_file() and scan.is_file()):
            self.skipTest("the vod30 anchors or the scan quad are not present")
        first = next(iter(json.loads(anchors.read_text())["anchors"].values()))
        old_a = _order_corners(np.asarray(first[:4], np.float32))
        old_b = np.asarray(json.loads(scan.read_text())["corners"], np.float32)
        _ha, _hb, quad_a, quad_b, pockets = load_mappings()
        np.testing.assert_array_equal(quad_a, old_a)
        np.testing.assert_array_equal(quad_b, old_b)
        self.assertEqual(len(pockets), 2, "the six anchors carry two pocket points")


class ReaderUsesTheSeamTest(unittest.TestCase):
    """Every reader gets its quad from the seam, not from a loader of its own."""

    QUAD = np.array([[100.0, 100.0], [900.0, 110.0], [910.0, 500.0], [90.0, 490.0]],
                    np.float32)

    def test_motion_scan_takes_its_quad_from_the_seam(self):
        from src import calib_segments, motion_scan
        sentinel = calib_segments.Reference(quad=self.QUAD, kind="segment",
                                            origin="sentinel", artifact="sentinel.json",
                                            entry="s1", per_time=True,
                                            note="from the seam", evidence="test")
        seen = {}
        original = calib_segments.resolve

        def fake_resolve(dataset="vod30", t=None, **kwargs):
            seen.update({"dataset": dataset, "t": t}, **kwargs)
            return sentinel

        calib_segments.resolve = fake_resolve
        try:
            quad = motion_scan.load_quad("vod30", root=Path("."), frame_size=(1280, 720), t=5.0)
        finally:
            calib_segments.resolve = original
        self.assertEqual(quad["quad_px"], self.QUAD.tolist())
        self.assertEqual(quad["source"], "sentinel")
        self.assertEqual(quad["note"], "from the seam")
        self.assertTrue(quad["verified"])
        self.assertEqual(seen["dataset"], "vod30")
        self.assertEqual(seen["t"], 5.0)
        self.assertEqual(seen["frame_size"], (1280, 720))

    def test_claim_calibration_takes_its_quad_from_the_seam(self):
        from src import calib_segments
        from src.eval_events import claim_calibration
        from src.pipeline import homography_to_canonical
        seen = {}
        original = calib_segments.read

        def fake_read(path, key=None, **kwargs):
            seen.update({"path": path, "key": key}, **kwargs)
            return calib_segments.Reference(quad=self.QUAD, kind="static", artifact=str(path),
                                            entry=key, origin=str(path))

        calib_segments.read = fake_read
        try:
            inverse, label = claim_calibration("out/scan30/corners.json")
        finally:
            calib_segments.read = original
        self.assertEqual((seen["path"], seen["key"]), ("out/scan30/corners.json", "corners"))
        np.testing.assert_allclose(inverse, np.linalg.inv(homography_to_canonical(self.QUAD)))
        self.assertEqual(label, "scan claim frame (out/scan30/corners.json)")


class NoPrivateLoaderTest(unittest.TestCase):
    """No reader parses a calibration artifact; the source text says so.

    The AST check is the durable half of the seam: a later edit that puts a
    ``json.loads`` back into one of these functions fails here, whatever the
    artifacts on disk happen to hold.
    """

    #: (module, functions that answer "which quad") -- each must call the seam.
    READERS = {
        "src/motion_scan.py": ("load_quad",),
        "src/timing_verify.py": ("load_quad",),
        "src/eval_events.py": ("reference_calibration", "claim_calibration"),
        "src/calib_mapping_audit.py": ("load_mappings", "highlight_reference_check"),
        "src/calib_segment_measure.py": ("anchors_quad", "scan_quad"),
        "src/sam3_frame_audit.py": ("reference_quad",),
        "src/sam3_ball_cache.py": ("reference_quad",),
    }
    #: loaders that rebuilt the chain and must stay deleted.
    GONE = {
        "src/eval_events.py": ("load_quad", "load_segments"),
        "src/calib_mapping_audit.py": ("_load_anchors",),
    }

    @staticmethod
    def functions(path):
        tree = ast.parse((ROOT / path).read_text())
        return {node.name: node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)}

    def test_every_reader_asks_the_seam_and_reads_no_file(self):
        for path, names in self.READERS.items():
            defined = self.functions(path)
            for name in names:
                self.assertIn(name, defined, f"{path}: {name} must stay")
                calls = [ast.unparse(node.func) for node in ast.walk(defined[name])
                         if isinstance(node, ast.Call)]
                self.assertTrue([call for call in calls
                                 if call.startswith("calib_segments.")],
                                f"{path}.{name} no longer calls the seam")
                for banned in ("json.loads", "read_text"):
                    self.assertFalse([call for call in calls if call.endswith(banned)],
                                     f"{path}.{name} parses a file itself: {banned}")

    def test_the_private_loaders_stay_deleted(self):
        for path, names in self.GONE.items():
            defined = self.functions(path)
            for name in names:
                self.assertNotIn(name, defined, f"{path}.{name} must not come back")

    def test_the_report_build_names_the_artifact_once(self):
        build = self.functions("src/segment_calib_report.py")["build"]
        text = ast.unparse(build)
        self.assertIn("calib_segments.resolve", text)
        self.assertNotIn('["segments"]', text, "the payload layout stays in the seam")
        loads = [node for node in ast.walk(build) if isinstance(node, ast.Call)
                 and ast.unparse(node.func).endswith("json.loads")]
        for node in loads:
            self.assertNotIn("args.artifact", ast.unparse(node),
                             "the artifact is read once, by the seam")

    # The segment artifact name has one owner, ``src/calib_segments.py``.  Round 88
    # measured the name spelled at three sites outside the owner: the tool that
    # writes the artifact, the report build, and two f-strings of the server.  Each
    # of them now reads the owner, so a rename of the file name moves them all.
    #
    # The last copy stood at ``src/store.py``, in the kind -> file map
    # (``ARTIFACTS``).  Round 89 made that row read the owner, so no known copy
    # stays and the list above holds the owner alone.  Nothing there is a licence
    # for a new copy: a case that adds a row must first make the row read the owner.
    #
    # The map has a shape a guard cannot see from the values: a row is read as a
    # ``str.format`` template, and the owner's keyword is ``{dataset}``.  A second
    # spelling of the template text is still possible, so
    # ``test_the_kind_map_reads_the_owner`` walks the AST of ``src/store.py`` and
    # fails on a row that spells the text again.
    OWNER_MODULE = "src/calib_segments.py"
    #: The name of the owner's template, as both files read it.
    ARTIFACT_TEMPLATE = "ARTIFACT"
    #: The map of ``src/store.py``, and the row this round moved to the owner.
    MAP_MODULE = "src/store.py"
    MAP_NAME = "ARTIFACTS"
    MAP_ROW = "calibration_segments"
    #: The two rows of ``src/store.py`` carry their own dataset placeholder ``{ds}``.
    FORMATTING_KEYS = ("ds", "dataset")
    #: The readers of the name, and the call each one makes to the owner.
    NAME_READERS = {
        "src/calib_segment_fit.py": "segment_artifact_path",
        "src/segment_calib_report.py": "segment_artifact_path",
        "annotator/unified_server.py": "SEGMENT_ARTIFACT",
    }

    def shipped_files(self):
        """The shipped modules, as (repository-relative name, tree)."""
        out = []
        for path in shipped_modules():
            name = path.relative_to(ROOT).as_posix()
            out.append((name, ast.parse(path.read_text(encoding="utf-8"))))
        return out

    def functions_of(self, tree):
        """{name: node} for every function and class of one tree."""
        out = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.setdefault(node.name, node)
        return out

    def spelled_name(self, tree):
        """The sites of one tree that build the whole name: an f-string, or ``.format``.

        A build is the shape a second reader takes when it joins the folder and the
        name itself.  A call of the owner's helper is not a build, and a plain
        literal of a registry row is judged by ``name_literals``.
        """
        out = []
        for node in ast.walk(tree):
            text = ""
            if isinstance(node, ast.JoinedStr):
                text = ast.unparse(node)
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "format"):
                text = ast.unparse(node)
            if "calib_" in text and "segments" in text and "json" in text:
                out.append((node.lineno, text))
        return out

    def name_literals(self, tree):
        """The string literals of one tree that carry the name or its template."""
        out = []
        for line, text in code_strings(tree):
            if "calib_" not in text or "segments" not in text:
                continue
            if not text.endswith(".json") and not text.endswith("_segments.json"):
                continue
            if any(key in text for key in self.FORMATTING_KEYS):
                out.append((line, text))
            elif text == MARKER_NAME:
                out.append((line, text))
        return out

    def test_the_artifact_name_stands_once_in_the_shipped_tree(self):
        """Only the owner names the artifact, in any shape."""
        offenders = {}
        for name, tree in self.shipped_files():
            if name == self.OWNER_MODULE:
                continue
            found = self.spelled_name(tree) + self.name_literals(tree)
            if found:
                offenders[name] = found
        self.assertEqual(offenders, {},
                         f"a module names the segment artifact itself: {offenders}")

    def test_the_artifact_name_stands_once_as_a_literal(self):
        """One file holds the whole name as text: the owner."""
        copies = {}
        for name, tree in self.shipped_files():
            found = self.name_literals(tree)
            if found:
                copies[name] = found
        self.assertEqual(sorted(copies), [self.OWNER_MODULE],
                         f"a module holds the segment artifact name as text: {copies}")

    def map_rows(self, tree):
        """{key: value node} for the kind -> file map of one tree."""
        rows = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if self.MAP_NAME not in targets or not isinstance(node.value, ast.Dict):
                continue
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    rows[key.value] = value
        return rows

    def test_the_kind_map_reads_the_owner(self):
        """The row of ``src/store.py`` reads the owner, and does not spell the name.

        The row stood as the literal ``"calib_{ds}_segments.json"``, a second
        spelling that moved with no owner.  A later reader that writes the text
        again fails here, and not in the file that holds the map.
        """
        from src import store

        tree = ast.parse((ROOT / self.MAP_MODULE).read_text(encoding="utf-8"))
        rows = self.map_rows(tree)
        self.assertIn(self.MAP_ROW, rows, f"the map must keep the {self.MAP_ROW} row")
        row = rows[self.MAP_ROW]
        self.assertNotIsInstance(row, ast.Constant,
                                 "the row spells the template text again; it must read the owner")
        self.assertEqual(ast.unparse(row), self.ARTIFACT_TEMPLATE,
                         "the row must read the owner's ARTIFACT")
        self.assertEqual(store.ARTIFACTS.get(self.MAP_ROW), TEMPLATE,
                         "the row must hold the owner's template, not a second text")
        # The row's own placeholder is the owner's keyword, so the format call of
        # artifact() fills it.
        self.assertIn("{dataset}", store.ARTIFACTS[self.MAP_ROW],
                      "the row must carry the owner's keyword")

    def test_the_scan_sees_a_bitten_module(self):
        """The guard answers red when a shipped module spells the name again."""
        source = ("def stamp(dataset):\n"
                  "    return f'calib_{dataset}_segments.json'\n"
                  "def other():\n"
                  "    return 'calib_vod30_segments.json'\n")
        tree = ast.parse(source)
        self.assertTrue(self.spelled_name(tree), "the scan must see the f-string")
        self.assertTrue(self.name_literals(tree), "the scan must see the literal")

    def test_the_owner_answers_the_name_and_the_path(self):
        owner = dict(self.shipped_files())[self.OWNER_MODULE]
        module = {}
        for node in owner.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    module[target.id] = node.value.value
        self.assertEqual(module.get("ARTIFACT"), TEMPLATE,
                         "src/calib_segments.py must state the template once")
        helpers = self.functions_of(owner)
        self.assertIn("segment_artifact_path", helpers,
                      "the owner must answer the path of one dataset")
        text = ast.unparse(helpers["segment_artifact_path"])
        self.assertIn("ARTIFACT", text, "the helper joins the owner's own template")
        self.assertIn('.format(dataset=', text, "the helper fills the dataset")

    def test_every_site_that_names_the_artifact_reads_the_owner(self):
        for name, want in self.NAME_READERS.items():
            tree = dict(self.shipped_files())[name]
            text = ast.unparse(tree)
            if want == "SEGMENT_ARTIFACT":
                self.assertIn("SEGMENT_ARTIFACT", text,
                              f"{name} must read the owner's template")
            else:
                self.assertIn(f"segment_artifact_path(", text,
                              f"{name} must read the owner's path")
                self.assertIn(f"from src.calib_segments import", text,
                              f"{name} must import the owner")

    def test_the_map_row_is_not_a_second_reader_of_the_name(self):
        """The map reads the owner's template; it calls no path helper of its own."""
        source = (ROOT / self.MAP_MODULE).read_text(encoding="utf-8")
        self.assertNotIn("segment_artifact_path", source,
                         "the map reads the owner's template, not a second reader")


if __name__ == "__main__":
    unittest.main()
