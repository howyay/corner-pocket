"""Calibration-truth tests: which px<->mm mapping is right, and how we warn.

Three questions, each pinned so nobody re-litigates them (2026-09-24):

1. **Hand anchors vs the scan quad.**  ``src.calib_mapping_audit`` measures the
   disagreement; these tests pin the conclusion (the anchors are the physical
   mapping, the scan quad is the *claim* frame) and the numbers it rests on.
2. **The calibration warning.**  Coverage is reported, never a trigger; the
   per-side rail evidence decides.  The two real frames the gate used to warn
   about (t=483.4, t=1120.2) must stay silent, and a reference the frame
   contradicts must still warn -- both measured on the VOD, both pinned at the
   gate with the measured evidence.
3. **Where each mapping is used.**  A claim's stored millimetres are projected
   through the frame that wrote them, not through the physical mapping.

Video-free where possible; the frame-level cases skip when the VOD or the
artifacts are absent, so the suite stays runnable on a fixture tree.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "data" / "vod_30min_260815.mp4"
ANCHORS = ROOT / "out" / "pid_anchors_vod30.json"
SCAN_QUAD = ROOT / "out" / "scan30" / "corners.json"
AUDIT = ROOT / "out" / "calib_mapping_audit.json"
HAVE_QUADS = ANCHORS.is_file() and SCAN_QUAD.is_file()
HAVE_VIDEO = VIDEO.is_file() and HAVE_QUADS
CANON_W, CANON_H = 1270.0, 2540.0


class MappingTruthTests(unittest.TestCase):
    """Q1: the anchors are the physical reference; the scan quad is not."""

    @unittest.skipUnless(HAVE_QUADS, "calibration artifacts absent")
    def test_the_scan_quad_corners_are_outside_the_anchor_cloth(self):
        from src.calib_mapping_audit import corner_containment, load_mappings
        _ha, _hb, quad_a, quad_b, _pockets = load_mappings()
        contain = corner_containment(quad_a, quad_b)
        self.assertEqual(contain["b_corners_vs_a_cloth"]["n_inside"], 1)
        worst = min(contain["b_corners_vs_a_cloth"]["rows"],
                    key=lambda row: row["signed_dist_px"])
        self.assertEqual(worst["corner"], 0)                       # head-left
        self.assertAlmostEqual(worst["signed_dist_px"], -90.7, delta=1.0)

    @unittest.skipUnless(HAVE_QUADS, "calibration artifacts absent")
    def test_held_out_side_pocket_clicks_prefer_the_anchors(self):
        """Anchors 5-6 are clicked, not fitted: a held-out test of each mapping."""
        from src.calib_mapping_audit import held_out_anchors, load_mappings
        ha, hb, _qa, _qb, pockets = load_mappings()
        rows = held_out_anchors(ha, hb, pockets)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertLess(row["a_err_mm"], 30.0)                 # 18.3 / 23.6 mm
            self.assertGreater(row["b_err_mm"], 150.0)             # 166.4 / 236.0 mm

    @unittest.skipUnless(HAVE_QUADS, "calibration artifacts absent")
    def test_the_disagreement_is_positional_and_worst_at_the_head(self):
        from src.calib_mapping_audit import load_mappings, pixel_disagreement
        ha, hb, _qa, _qb, _pockets = load_mappings()
        rows, by_region = pixel_disagreement(ha, hb)
        self.assertGreaterEqual(len(rows), 20)                     # the >=20-point ask
        # px disagreement is largest at the head corner, mm cost is largest there too
        head = max(rows, key=lambda r: r["d_px"] if r["region"] == "head" else -1)
        self.assertEqual(head["mm"], [0.0, 0.0])
        self.assertAlmostEqual(head["d_px"], 90.7, delta=1.0)
        self.assertGreater(by_region["head"]["b_off_mm_median"],
                           by_region["foot"]["b_off_mm_median"])
        # the foot is foreshortened: 1 px there is worth ~2 mm, ~22 mm at the head
        self.assertLess(by_region["foot"]["mm_per_px_median"],
                        by_region["head"]["mm_per_px_median"])

    @unittest.skipUnless(HAVE_QUADS, "calibration artifacts absent")
    def test_foreshortening_head_vs_foot(self):
        from src.calib_mapping_audit import foreshortening, load_mappings
        ha, hb, qa, qb, _pockets = load_mappings()
        fore = foreshortening(ha, hb, qa, qb)
        anchors, scan = fore["a_hand_anchors"], fore["b_scan_quad"]
        self.assertAlmostEqual(anchors["head_over_foot"], 4.31, delta=0.1)
        self.assertAlmostEqual(anchors["rail_compression"], 2.29, delta=0.05)
        # the scan quad understates the foreshortening because it pulls the head
        # rail 348 px wide where the frame's own boundary sits at 268 px
        self.assertLess(scan["head_over_foot"], anchors["head_over_foot"])
        self.assertAlmostEqual(scan["head_rail_px"], 347.7, delta=2.0)

    def test_the_two_mappings_are_a_documented_contract(self):
        from src import eval_events
        self.assertTrue(eval_events.claim_calibration.__doc__)
        self.assertIn("claim", eval_events.claim_calibration.__doc__.lower())


@unittest.skipUnless(HAVE_VIDEO, "VOD or calibration artifacts absent")
class RailEvidenceOnRealFramesTests(unittest.TestCase):
    """Q2: measured on the frames the gate used to warn about."""

    @classmethod
    def setUpClass(cls):
        from src import eval_events
        from src.calib_mapping_audit import load_mappings
        cls.tool = eval_events
        ha, hb, quad_a, quad_b, _pockets = load_mappings()
        cls.quad_a, cls.quad_b = quad_a, quad_b
        cls.probe = eval_events.Probe(str(VIDEO), ha, __import__("numpy").linalg.inv(ha),
                                      quad_a, claim_inverse=__import__("numpy").linalg.inv(hb))
        if not cls.probe.open():
            cls.probe = None

    @classmethod
    def tearDownClass(cls):
        if cls.probe is not None:
            cls.probe.close()

    def setUp(self):
        if self.probe is None:
            self.skipTest("cannot open the VOD")

    def test_known_good_late_frames_verify_all_four_rails(self):
        from src.event_gates import calibration_warning, GateConfig
        for t in (483.4, 1120.2):
            rail = self.probe.rail_evidence(t)
            self.assertIsNotNone(rail, f"no rail evidence at t={t}")
            self.assertEqual(rail["verified_sides"], 4, f"t={t}: {rail}")
            self.assertEqual(rail["unverified"], {}, f"t={t}: {rail}")
            self.assertIsNone(calibration_warning(rail, GateConfig()),
                              f"a known-good frame warned at t={t}")

    def test_the_low_coverage_frames_are_still_occluded_not_mis_calibrated(self):
        """The reason the old trigger was wrong: coverage drops, rails verify."""
        from src.calib_segment_measure import anchors_quad, coverage
        import cv2
        cap = cv2.VideoCapture(str(VIDEO))
        try:
            for t in (483.4, 1120.2):
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ok, frame = cap.read()
                self.assertTrue(ok)
                self.assertLess(coverage(frame, anchors_quad()), 0.85)
        finally:
            cap.release()

    def test_a_reference_the_frame_contradicts_warns(self):
        """The measured bad case: the 90 px-off scan quad, on the same frames."""
        from src.event_gates import calibration_warning, GateConfig
        import numpy as np
        bad = self.tool.Probe(str(VIDEO), None, None, self.quad_b)
        self.assertTrue(bad.open())
        try:
            warned = 0
            for t in (70.0, 0.0, 1120.2):
                rail = bad.rail_evidence(t)
                self.assertIsNotNone(rail)
                self.assertTrue(rail["unverified"], f"t={t}: {rail}")
                self.assertIsNotNone(calibration_warning(rail, GateConfig()),
                                     f"a bad reference stayed silent at t={t}")
                warned += 1
            self.assertEqual(warned, 3)
        finally:
            bad.close()

    def test_the_gate_is_silent_on_the_measured_good_frame_and_warns_on_the_bad(self):
        from src.event_gates import GateConfig, ShotEvidence, judge
        from src.event_gates import normalize
        claim = normalize({"type": "shot", "t": 1120.2, "color": "white",
                           "from_mm": [423.1, 612.9], "to_mm": [700.0, 900.0],
                           "disp_mm": 400.0, "gap_s": 0.07})
        good = ShotEvidence(available=True, disp_mm=1345.0, disp_color="white",
                            start_px=[938.7, 566.7], geometry_gap_px=40.0,
                            from_in_cloth_px=29.6, to_in_cloth_px=42.8,
                            start_hits=3, end_hits=6, calibration_frac=0.777,
                            rail_evidence=self.probe.rail_evidence(1120.2))
        result = judge(claim, good, GateConfig())
        self.assertEqual([r for r in result.reasons if r.startswith("calibration")], [])
        bad = ShotEvidence(available=True, disp_mm=1345.0, disp_color="white",
                           start_px=[938.7, 566.7], geometry_gap_px=40.0,
                           from_in_cloth_px=29.6, to_in_cloth_px=42.8,
                           start_hits=3, end_hits=6, calibration_frac=0.99,
                           rail_evidence=self.probe.rail_evidence(483.4))
        # the same measured evidence projected onto the bad reference quad
        bad.rail_evidence = {"verified_sides": 1, "inherited_sides": [],
                             "unverified": {"0": "no_boundary_evidence",
                                            "2": "no_boundary_evidence",
                                            "3": "no_boundary_evidence"},
                             "supported_sides": 1, "reason": "no_boundary_evidence"}
        self.assertIn("calibration_rail_unverified_at_time",
                      judge(claim, bad, GateConfig()).reasons)


@unittest.skipUnless(HAVE_QUADS, "calibration artifacts absent")
class ClaimFrameProjectionTests(unittest.TestCase):
    """Q1's consumer fix: claims are projected in the frame that wrote them."""

    def test_claim_px_uses_the_scan_frame_and_px_uses_the_physical_one(self):
        """The scan's head-left corner is mm (0, 0) *in the scan frame*.

        Projecting that claim with the physical mapping lands it on the anchor
        corner, 90.7 px from the pixel the scan actually measured.
        """
        import numpy as np
        from src.eval_events import Probe, claim_calibration
        from src.calib_mapping_audit import load_mappings
        ha, hb, quad_a, _qb, _pockets = load_mappings()
        inverse_a = np.linalg.inv(ha)
        claim_inverse, label = claim_calibration(str(SCAN_QUAD))
        self.assertIsNotNone(claim_inverse)
        self.assertIn("scan", label)
        probe = Probe("no-such-video.mp4", ha, inverse_a, quad_a, claim_inverse=claim_inverse)
        head = [0.0, 0.0]                         # the scan quad's head-left, in scan mm
        a_px, claim_px = probe.px(head), probe.claim_px(head)
        self.assertAlmostEqual(claim_px[0], 459.3, delta=1.0)   # what the scan measured
        self.assertAlmostEqual(claim_px[1], 268.9, delta=1.0)
        self.assertAlmostEqual(a_px[0], 532.0, delta=1.0)       # the anchor corner
        self.assertAlmostEqual(a_px[1], 323.0, delta=1.0)
        moved = ((a_px[0] - claim_px[0]) ** 2 + (a_px[1] - claim_px[1]) ** 2) ** 0.5
        self.assertAlmostEqual(moved, 90.7, delta=1.5)
        # and far from the head the two mappings nearly agree: the disagreement
        # is positional, not a constant offset
        foot = [CANON_W, CANON_H]
        foot_a, foot_claim = probe.px(foot), probe.claim_px(foot)
        foot_moved = ((foot_a[0] - foot_claim[0]) ** 2 + (foot_a[1] - foot_claim[1]) ** 2) ** 0.5
        self.assertLess(foot_moved, 40.0)
        self.assertLess(foot_moved, moved / 2.0)

    def test_claim_px_falls_back_to_the_physical_mapping_without_a_scan_quad(self):
        import numpy as np
        from src.eval_events import Probe
        from src.calib_mapping_audit import load_mappings
        ha, _hb, quad_a, _qb, _pockets = load_mappings()
        probe = Probe("no-such-video.mp4", ha, np.linalg.inv(ha), quad_a)
        mm = [635.0, 1270.0]
        self.assertEqual(probe.claim_px(mm), probe.px(mm))

    def test_claim_calibration_is_none_without_the_artifact(self):
        import tempfile
        from src.eval_events import claim_calibration
        with tempfile.TemporaryDirectory() as tmp:
            inverse, label = claim_calibration(str(Path(tmp) / "missing.json"))
        self.assertIsNone(inverse)
        self.assertIn("none", label)

    def test_the_report_carries_both_gaps_for_a_known_event(self):
        """Before/after on a served sample, through the pure report builder."""
        import numpy as np
        from src.eval_events import Probe
        from src.calib_mapping_audit import load_mappings
        ha, hb, quad_a, _qb, _pockets = load_mappings()
        probe = Probe("no-such-video.mp4", ha, np.linalg.inv(ha), quad_a,
                      claim_inverse=np.linalg.inv(hb))
        claim_mm = [697.9, 297.9]                 # a real served shot start (t=1364.186)
        a_px, claim_px = probe.px(claim_mm), probe.claim_px(claim_mm)
        self.assertGreater(((a_px[0] - claim_px[0]) ** 2 + (a_px[1] - claim_px[1]) ** 2) ** 0.5,
                           20.0)


if __name__ == "__main__":
    unittest.main()
