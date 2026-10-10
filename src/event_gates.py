"""Explicit gates that decide whether a scan candidate is corroborated.

The queue shipped by the info-complete scan is a list of *claims*: "a ball of
colour C moved 300 mm here", "a ball of colour C vanished next to this pocket".
Nothing in the claim is evidence; the gates below re-check the claim against
measurements and return one of three statuses:

  ``confirmed``    every required gate passed with measured evidence;
  ``rejected``     a measured signal contradicts the claim;
  ``unconfirmed``  a required signal could not be measured (no detections, no
                   video).  This is *not* a proof of a false positive; the
                   report says why the measurement was unavailable.

Pure functions only: no video, no OpenCV, no file IO.  ``src/eval_events.py``
does the measuring and hands the numbers in, so every rule here is testable
without a VOD.

Thresholds and where they come from (measured on vod30, 2026-09-23):

* ``dedup_window_s = 2.0``      the t=5.6/5.67/5.87 trio is one pre-break moment
                                0.27 s wide; the old rule (same type within
                                4 s) also swallowed genuinely distinct acts.
* ``dedup_position_mm = 200``   a ball is 57 mm wide; two same-act claims put
                                the vanished ball in the same spot.
* ``pot_pocket_r_mm = 100``     re-measured vanished-ball distances cluster at
                                39-86 mm (pocket mouth) and then jump to
                                >=110 mm (ball still on the cloth).
* ``pot_census_drop = 1``       a pot removes exactly one ball from the cloth.
* ``shot_min_disp_mm = 300``    re-measured sharp-frame displacements for the
                                two shots a human can confirm (t=483.4, t=1120.2)
                                are 471 mm and 1345 mm; every dead window stays
                                <=112 mm.
* ``shot_geometry_tol_px = 60`` the reference calibration's own scatter plus a
                                ball's worth of mm ambiguity.
* ``off_cloth_tol_px = -2``     the claimed position must be inside the cloth
                                quad, not on the rail or the wall behind it.

Round 2 -- the fused census (2026-09-23).  The probe now measures the census
from the fused classical + SAM3 + temporal-association report
(``src.ball_census``), so a frame count is no longer a 1-3 ball sample and a
single ball leaving the cloth is measurable.  Three rules were added; none is a
loosening, each replaces "unmeasurable" with a measurement:

* ``vanished_ball_still_on_cloth`` the claim's colour is one a rack holds
  exactly once (``black``) and a *scored* sighting of it exists after the event.
  Presence is a measurement, absence is not; the asymmetry is deliberate.
* ``census_source_mismatch``       the two sides of the window were measured by
  different detectors (SAM3 on one side only), so their counts are not
  comparable and no drop may be inferred.  Unconfirmed, never a drop.
* ``census_displacement_corroborated`` a shot the colour-blob detector cannot
  re-measure (motion blur) but a stable fused identity can, sighted at least
  twice at each end of the window and within ``shot_geometry_tol_px`` of the
  claim.  It is only reached after the classical path has failed.

Round 3 -- calibration truth (2026-09-24).  Two long-open geometry defects were
measured and closed:

* **which px<->mm mapping is authoritative.**  The hand anchors are the physical
  reference: the frame's own rail boundaries verify all four sides against them
  on every sampled frame, the scan quad's corners sit 9-91 px outside them
  (3 of 4 outside), and the scan quad's two *held-out* side-pocket clicks land
  166-236 mm off against 18-24 mm here (``out/calib_mapping_audit.json``).
  ``src.eval_events`` now keeps the two apart explicitly: measured millimetres
  use the reference mapping, while a *claim's* stored millimetres -- written by
  the scan through its own quad -- are projected back to pixels through that
  same quad (``Probe.claim_px``), which moves the served samples by up to 61 px.
* ``calibration_weak_at_time`` **is gone as a trigger.**  Coverage
  (``calibration_frac``) falls on occlusion and shading exactly like a camera
  move, and it warned on frames the frame itself verifies.  The warning now
  comes from the per-side rail evidence: ``calibration_rail_unverified_at_time``
  when a side of the reference has no boundary evidence on this frame, and
  ``calibration_reference_contradicted_at_time`` when a side's boundary is
  demonstrably somewhere else.  Coverage stays in ``numbers`` as a reported
  signal only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable

# src/table_geometry.py is the single definition site of the canonical frame and
# of the pocket table, so the gates judge on the same frame as the scan. The three
# names stay a re-export: tests/test_table_geometry.py binds every importer of the
# frame to the one table object, and src/calib_mapping_audit.py reads them here.
from src.table_geometry import CANON_H, CANON_W, POCKETS_MM, nearest_pocket
# The pocket name a text states has one owner, src/pocket_names.py. This gate and
# the console backend answered the bare spelling in two different ways.
from src.pocket_names import pocket_from_text


@dataclass
class GateConfig:
    dedup_window_s: float = 2.0
    dedup_strict_s: float = 0.5
    dedup_position_mm: float = 200.0
    pot_pocket_r_mm: float = 100.0
    pot_census_drop: int = 1
    pot_min_pre_hits: int = 1
    pot_min_census: float = 2.0      # below this the census cannot decide anything
    shot_min_disp_mm: float = 300.0
    shot_geometry_tol_px: float = 60.0
    shot_stable_anchors: int = 2     # of 3 anchor offsets (t, t-0.1, t+0.1)
    off_cloth_tol_px: float = -2.0
    # Calibration health is decided by the per-side rail evidence, never by
    # coverage (see ``calibration_warning``).  ``calibration_frac`` below is kept
    # only as a reported number: it collapses onto the wall panels when a player
    # stands on the cloth, which is exactly when shots happen (measured at
    # t=483.4 / 1120.2: coverage 0.777 / 0.800 with all four rails verified).
    calibration_warn_fraction: float = 0.80      # reporting only; not a trigger
    # Every side of the reference quad must be supported by the frame's own
    # boundary evidence -- verified with the dark-rail/bright-cloth signature or
    # explicitly inherited from the prior, never unverified.  That is the same
    # rule ``src.calib_segment_fit`` uses to call a sample framed-consistently.
    calibration_min_supported_sides: int = 4
    # ... but a *warning* needs more than one unmeasurable side; see
    # ``calibration_warning``.  Two sides with no boundary evidence at all is
    # the reference-does-not-fit signature (measured: 2-3 on the 90 px-off scan
    # quad, 0-1 on every occluded frame of the calibrated VOD).
    calibration_min_unsupported_sides: int = 2


@dataclass
class GateResult:
    status: str                       # confirmed | rejected | unconfirmed
    gate: str                         # the gate that decided it
    reasons: list = field(default_factory=list)
    tier: str | None = None           # confirmed: geometry | window
    numbers: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        out = {"status": self.status, "gate": self.gate, "reasons": list(self.reasons)}
        if self.tier:
            out["tier"] = self.tier
        out["numbers"] = dict(self.numbers)
        return out


# ---------------------------------------------------------------- normalising

def _num(value: Any):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


COLOR_ALIASES = {"red2": "red", "red1": "red"}


def color_key(value: Any) -> str:
    """Detector colour name -> comparable colour name.

    ``row.src.ball_detect`` reports the hue-wraparound red band under a second
    name (``red2``); a claim and a measurement of the same physical ball must
    compare equal, so both sides go through this.
    """
    text = str(value or "").strip().lower()
    return COLOR_ALIASES.get(text, text)


def normalize(raw: Any) -> dict:
    """Accept both shipped schemas (scan candidates and the served queue).

    Scan candidates carry ``from_mm``/``to_mm``/``last_mm``/``from_frame``;
    the queue artifact carries ``ball_from``/``ball_to``/``last_mm`` and
    ``window_s``.  Nothing is renamed in either file; this is a read view.
    """
    event = dict(raw) if isinstance(raw, dict) else {}
    kind = str(event.get("type") or "")
    window = event.get("window_s")
    window = [float(w) for w in window] if isinstance(window, (list, tuple)) and len(window) == 2 else None
    return {
        "id": event.get("id"),
        "kind": kind,
        "t": _num(event.get("t")),
        "color": event.get("color"),
        "from_mm": event.get("from_mm") or event.get("ball_from"),
        "to_mm": event.get("to_mm") or event.get("ball_to"),
        "last_mm": event.get("last_mm") or event.get("ball_table_mm"),
        "gap_s": _num(event.get("gap_s")),
        "from_frame": event.get("from_frame"),
        "to_frame": event.get("to_frame"),
        "last_frame": event.get("last_frame"),
        "window_s": window,
        "pocket": pocket_from_text(event.get("nearest_pocket")),
        "raw": event,
    }


# --------------------------------------------------------------------- dedup

def _position(point):
    if isinstance(point, (list, tuple)) and len(point) == 2:
        x, y = _num(point[0]), _num(point[1])
        return None if x is None or y is None else (x, y)
    return None


def _same_act(a: dict, b: dict, cfg: GateConfig) -> bool:
    """True when two candidates describe the same physical act.

    Same kind and close in time, and either the same ball colour at the same
    pocket, or the same claimed ball position.  A different ball colour is a
    different act unless the two are within ``dedup_strict_s`` and share a
    position/pocket -- the scan reports the fastest matched pair per sampled
    frame pair, so a single shot can surface under more than one colour.
    """
    if a["kind"] != b["kind"] or a["t"] is None or b["t"] is None:
        return False
    dt = abs(a["t"] - b["t"])
    if dt > cfg.dedup_window_s:
        return False
    same_color = a["color"] and b["color"] and a["color"] == b["color"]
    same_pocket = a["pocket"] and a["pocket"] == b["pocket"]
    pa, pb = _position(a["last_mm"] or a["from_mm"]), _position(b["last_mm"] or b["from_mm"])
    same_pos = (pa is not None and pb is not None
                and math.hypot(pa[0] - pb[0], pa[1] - pb[1]) <= cfg.dedup_position_mm)
    if same_color and (same_pocket or same_pos or dt <= cfg.dedup_strict_s):
        return True
    return dt <= cfg.dedup_strict_s and (same_pocket or same_pos)


def dedupe(candidates: Iterable[dict], cfg: GateConfig = GateConfig()) -> list:
    """Collapse same-act candidates; keep the earliest time and count the rest.

    Returns a list of groups, each ``{'event': first, 'dups': [...], 'count': n}``
    in time order.  The first candidate of a group is the one the queue keeps,
    so an event that already had an id in the served queue keeps that id.
    """
    groups: list = []
    for candidate in sorted((normalize(c) for c in candidates), key=lambda c: (c["t"] is None, c["t"])):
        placed = False
        for group in groups:
            if any(_same_act(member, candidate, cfg) for member in group["dups"] + [group["event"]]):
                group["dups"].append(candidate)
                placed = True
                break
        if not placed:
            groups.append({"event": candidate, "dups": [], "count": 1})
    for group in groups:
        group["count"] = 1 + len(group["dups"])
        group["colors"] = sorted({c["color"] for c in [group["event"]] + group["dups"] if c["color"]})
    return groups


# ----------------------------------------------------------------- evidence

@dataclass
class PotEvidence:
    """Measured in the event window by the probe; see eval_events.probe_pot."""
    available: bool = False
    note: str | None = None
    census_pre: float | None = None
    census_post: float | None = None
    census_post_max: float | None = None
    color_census_pre: float | None = None     # the claimed colour only
    color_census_post: float | None = None
    vanish: list = field(default_factory=list)   # {color, mm, pocket, dist_mm, pre_hits, approach_mm}
    motion_max: float | None = None
    calibration_frac: float | None = None     # cloth pixels inside the reference quad
    # Per-side rail evidence; see ``ShotEvidence.rail_evidence``.
    rail_evidence: dict | None = None
    # -- fused-census additions (all Optional: absent means "not measured",
    #    and every consumer falls back to the classical numbers above) -------
    census_version: int | None = None
    census_source: str | None = None          # sam3 | classical | None
    census_comparable: bool | None = None     # both sides measured by one detector
    census_counts_pre: list | None = None     # per-frame counts, so a human sees the spread
    census_counts_post: list | None = None
    census_spread_pre: float | None = None
    census_spread_post: float | None = None
    census_low_pre: bool | None = None        # a side below the floor as a whole
    census_low_post: bool | None = None       # (an endgame, not an occlusion)
    sam3_frames_pre: int | None = None
    sam3_frames_post: int | None = None
    stable_pre: float | None = None           # balls seen in >= 2 frames
    stable_post: float | None = None
    identity_drop: int | None = None          # stable identities lost across the event
    claim_color: str | None = None
    claim_color_present: bool | None = None   # measured on the cloth after the event
    claim_color_present_measured: bool | None = None
    claim_color_present_hits: int | None = None
    claim_color_present_sources: dict | None = None
    claim_color_unique: bool | None = None    # a rack holds one ball of this colour


@dataclass
class ShotEvidence:
    """Measured between sharp frames around the event; see eval_events.probe_shot."""
    available: bool = False
    note: str | None = None
    disp_mm: float | None = None
    disp_color: str | None = None
    start_px: list | None = None
    geometry_gap_px: float | None = None
    # The same gap measured by projecting the claim's scan-frame millimetres
    # through the *physical* reference instead of the frame that wrote them: the
    # before/after of the 2026-09-24 mapping fix, reported, never judged.
    geometry_gap_px_ref_frame: float | None = None
    window_motion: float | None = None
    from_in_cloth_px: float | None = None
    to_in_cloth_px: float | None = None
    start_hits: int | None = None      # independent sightings of the ball at the start
    end_hits: int | None = None        # ... and at the destination, before/after
    observations_needed: int = 2      # the ball must be sighted twice at each end
    stable_hits: int | None = None    # anchors (±0.1 s) that corroborate the same pair
    anchor_tries: int | None = None
    calibration_frac: float | None = None     # cloth pixels inside the reference quad
    # Per-side rail evidence for the reference quad at the event time, measured
    # by ``src.eval_events`` with ``src.table_refine.refine_quad_edges``:
    # ``{verified_sides, inherited_sides, unverified: {side: reason},
    #   supported_sides, reason, quad_moved_max_px}``.  Absent (None) means the
    # frame could not be measured, which is never reported as a bad frame.
    rail_evidence: dict | None = None
    # -- fused-census additions (absent = not measured; see PotEvidence) ------
    census_version: int | None = None
    census_source: str | None = None
    census_disp_mm: float | None = None       # largest same-identity move across the event
    census_disp_color: str | None = None
    census_start_hits: int | None = None      # sightings of that identity before the event
    census_end_hits: int | None = None        # ... and after it
    census_tracks_moved: int | None = None    # identities that moved >= shot_min_disp_mm
    census_geometry_gap_px: float | None = None   # claim start vs the identity's start
    census_frames: int | None = None
    census_sam3_frames: int | None = None


# --------------------------------------------------------------------- gates

def pot_gate(claim: dict, evidence: PotEvidence, cfg: GateConfig = GateConfig()) -> GateResult:
    """A pot needs a census drop that stays down, and the vanished ball at a pocket."""
    numbers = {"census_pre": evidence.census_pre, "census_post": evidence.census_post,
               "census_post_max": evidence.census_post_max, "motion_max": evidence.motion_max,
               "calibration_frac": evidence.calibration_frac,
               "rail_evidence": evidence.rail_evidence,
               "census_source": evidence.census_source,
               "census_comparable": evidence.census_comparable,
               "census_counts_pre": evidence.census_counts_pre,
               "census_counts_post": evidence.census_counts_post,
               "census_spread_pre": evidence.census_spread_pre,
               "census_spread_post": evidence.census_spread_post,
               "census_low_pre": evidence.census_low_pre,
               "census_low_post": evidence.census_low_post,
               "sam3_frames_pre": evidence.sam3_frames_pre,
               "sam3_frames_post": evidence.sam3_frames_post,
               "stable_pre": evidence.stable_pre, "stable_post": evidence.stable_post,
               "identity_drop": evidence.identity_drop,
               "claim_color_present": evidence.claim_color_present,
               "claim_color_present_measured": evidence.claim_color_present_measured,
               "claim_color_present_hits": evidence.claim_color_present_hits,
               "claim_color_present_sources": evidence.claim_color_present_sources,
               "claim_color_unique": evidence.claim_color_unique}
    if not evidence.available:
        return GateResult("unconfirmed", "probe", [evidence.note or "no probe evidence"], numbers=numbers)
    if evidence.claim_color_unique and evidence.claim_color_present_measured \
            and evidence.claim_color_present:
        # A colour a rack holds once was measured on the cloth after the event:
        # whatever the count did, that ball did not go in.  Presence needs a
        # scored SAM3 sighting or two independent sightings; a lone colour blob
        # is not enough to call a pot false.
        return GateResult("rejected", "vanish", ["vanished_ball_still_on_cloth"], numbers=numbers)
    if evidence.census_pre is None or evidence.census_post is None:
        return GateResult("unconfirmed", "census", ["no cloth census measured"], numbers=numbers)
    if evidence.census_comparable is False:
        # One side measured by SAM3 (10 balls), the other by the colour blobs
        # (1-3): the difference between them is the detector, not the table.
        return GateResult("unconfirmed", "census", ["census_source_mismatch"], numbers=numbers)
    if evidence.census_pre < cfg.pot_min_census:
        # One or two detections cannot show a one-ball drop: the classical
        # detector sees a fraction of the balls, so a missing drop here is a
        # missing measurement, not a contradiction.  Say so instead of calling
        # the claim false.
        return GateResult("unconfirmed", "census", ["census_too_sparse"], numbers=numbers)
    drop = evidence.census_pre - evidence.census_post
    numbers["census_drop"] = round(drop, 2)
    if drop < cfg.pot_census_drop:
        return GateResult("rejected", "census", ["census_did_not_drop"], numbers=numbers)
    if evidence.census_post_max is not None and evidence.census_post_max > evidence.census_pre - cfg.pot_census_drop:
        return GateResult("rejected", "census", ["census_recovered"], numbers=numbers)

    eligible = [v for v in evidence.vanish
                if not (claim["color"] and v.get("color")
                        and color_key(claim["color"]) != color_key(v["color"]))]
    if not eligible:
        return GateResult("unconfirmed", "vanish", ["no_vanished_ball_measured"], numbers=numbers)
    best = min(eligible, key=lambda v: v.get("dist_mm", float("inf")))
    numbers.update({"vanish_color": best.get("color"), "vanish_mm": best.get("mm"),
                    "vanish_pocket": best.get("pocket"), "vanish_dist_mm": best.get("dist_mm"),
                    "vanish_pre_hits": best.get("pre_hits"), "approach_mm": best.get("approach_mm"),
                    "vanish_tid": best.get("tid"), "vanish_sources": best.get("sources"),
                    "vanish_confidence": best.get("confidence")})
    if best.get("dist_mm") is None or best["dist_mm"] > cfg.pot_pocket_r_mm:
        return GateResult("rejected", "pocket", ["vanished_ball_not_at_pocket"], numbers=numbers)
    if (best.get("pre_hits") or 0) < cfg.pot_min_pre_hits:
        return GateResult("unconfirmed", "vanish", ["vanished_ball_not_established"], numbers=numbers)
    approach = best.get("approach_mm")
    if approach is not None and approach <= 0:
        return GateResult("rejected", "approach", ["no_approach_to_pocket"], numbers=numbers)
    reasons = ["census_drop", "vanished_ball_at_pocket"]
    _warn_calibration(evidence, cfg, reasons)
    return GateResult("confirmed", "pot", reasons, tier="geometry", numbers=numbers)


def shot_gate(claim: dict, evidence: ShotEvidence, cfg: GateConfig = GateConfig()) -> GateResult:
    """A shot needs on-cloth geometry and a re-measured displacement of the ball."""
    numbers = {"disp_mm": evidence.disp_mm, "disp_color": evidence.disp_color,
               "geometry_gap_px": evidence.geometry_gap_px,
               "geometry_gap_px_ref_frame": evidence.geometry_gap_px_ref_frame,
               "window_motion": evidence.window_motion,
               "from_in_cloth_px": evidence.from_in_cloth_px, "to_in_cloth_px": evidence.to_in_cloth_px,
               "start_hits": evidence.start_hits, "end_hits": evidence.end_hits,
               "stable_hits": evidence.stable_hits, "anchor_tries": evidence.anchor_tries,
               "calibration_frac": evidence.calibration_frac,
               "rail_evidence": evidence.rail_evidence,
               "census_source": evidence.census_source, "census_disp_mm": evidence.census_disp_mm,
               "census_disp_color": evidence.census_disp_color,
               "census_start_hits": evidence.census_start_hits,
               "census_end_hits": evidence.census_end_hits,
               "census_tracks_moved": evidence.census_tracks_moved,
               "census_geometry_gap_px": evidence.census_geometry_gap_px,
               "census_frames": evidence.census_frames,
               "census_sam3_frames": evidence.census_sam3_frames}
    if not evidence.available:
        return GateResult("unconfirmed", "probe", [evidence.note or "no probe evidence"], numbers=numbers)
    if evidence.from_in_cloth_px is None or evidence.to_in_cloth_px is None:
        return GateResult("unconfirmed", "geometry", ["claim_not_projectable"], numbers=numbers)
    numbers["min_in_cloth_px"] = round(min(evidence.from_in_cloth_px, evidence.to_in_cloth_px), 1)
    if min(evidence.from_in_cloth_px, evidence.to_in_cloth_px) < cfg.off_cloth_tol_px:
        return GateResult("rejected", "geometry", ["off_cloth"], numbers=numbers)
    if census_shot_corroborated(evidence, cfg):
        reasons = ["census_displacement_corroborated"]
        _warn_calibration(evidence, cfg, reasons)
        return GateResult("confirmed", "displacement", reasons, tier="census", numbers=numbers)
    if evidence.disp_mm is None:
        return GateResult("unconfirmed", "displacement", ["no_matched_ball_measured"], numbers=numbers)
    if evidence.disp_mm < cfg.shot_min_disp_mm:
        return GateResult("rejected", "displacement", ["displacement_not_corroborated"], numbers=numbers)
    if (evidence.start_hits is not None and evidence.start_hits < evidence.observations_needed) \
            or (evidence.end_hits is not None and evidence.end_hits < evidence.observations_needed):
        return GateResult("rejected", "observation", ["displacement_unobserved_elsewhere"],
                          numbers=numbers)
    if evidence.stable_hits is not None and evidence.anchor_tries \
            and evidence.stable_hits < cfg.shot_stable_anchors:
        # The same claim measured 0.1 s either side must corroborate too: the
        # classical detector's recall moves frame to frame, and a verdict that
        # flips on a 40 ms shift is not a verdict.
        return GateResult("unconfirmed", "stability", ["displacement_not_stable"],
                          numbers=numbers)
    if evidence.geometry_gap_px is not None and evidence.geometry_gap_px > cfg.shot_geometry_tol_px:
        reasons = ["displacement_corroborated", "geometry_mismatch"]
        _warn_calibration(evidence, cfg, reasons)
        return GateResult("confirmed", "displacement", reasons, tier="window", numbers=numbers)
    reasons = ["displacement_corroborated"]
    _warn_calibration(evidence, cfg, reasons)
    return GateResult("confirmed", "displacement", reasons, tier="geometry", numbers=numbers)


def census_shot_corroborated(evidence: ShotEvidence, cfg: GateConfig = GateConfig()) -> bool:
    """Does the fused census corroborate a displacement the blob detector could not?

    The colour-blob detector cannot see a fast ball (motion blur), which is why
    most shots end as "displacement_not_corroborated".  A stable fused identity
    (>= 2 sightings at each end, so a single mis-detection cannot make a ball
    "move") that travelled at least ``shot_min_disp_mm`` and whose start sits
    within ``shot_geometry_tol_px`` of the claim is a measurement of the same
    claim by other means.

    Every field is optional: without SAM3 coverage they are None, this returns
    False, and the classical path runs exactly as before.
    """
    if evidence.census_disp_mm is None or evidence.census_disp_mm < cfg.shot_min_disp_mm:
        return False
    if (evidence.census_start_hits or 0) < evidence.observations_needed:
        return False
    if (evidence.census_end_hits or 0) < evidence.observations_needed:
        return False
    if (evidence.census_tracks_moved or 0) < 1:
        return False
    if evidence.census_geometry_gap_px is not None \
            and evidence.census_geometry_gap_px > cfg.shot_geometry_tol_px:
        return False
    return True


# A side reason that says the frame put the boundary *somewhere else*: that is a
# contradiction of the reference quad, not a weak measurement.
CALIBRATION_REFUTE_REASONS = ("boundary_outside_band", "prior_disagreement")
# The reason a side gets when the search found no boundary with the rail
# signature anywhere in its band.  One such side is what occlusion looks like (a
# body covers the rail, so nothing is measurable there); two or more is the
# reference-not-fitting signature -- measured on the 90 px-off scan quad (2-3
# such sides at t=0/70/1120.2/1800) against 0-1 on every occluded frame of the
# calibrated VOD (t=484.1 has one; t=1661.0 and t=1799.1 have none at all).
CALIBRATION_NO_EVIDENCE_REASON = "no_boundary_evidence"


def calibration_warning(rail, cfg: GateConfig = GateConfig()) -> str | None:
    """The reason this frame's own rail evidence does not support the reference.

    ``rail`` is the measured per-side evidence (``src.eval_events.Probe.rail_evidence``,
    built on ``src.table_refine.refine_quad_edges``); ``None`` means the frame
    could not be measured at all, which is not a bad frame and warns about
    nothing.  Coverage is deliberately not consulted here: it is a proxy that
    occlusion and shading move exactly like a camera move, and it fired on
    frames whose four rails the frame itself verifies.

    Two things warn, both about the *reference*, never about the event:

    * a side whose boundary is demonstrably somewhere else;
    * ``calibration_min_unsupported_sides`` (2) or more sides with no boundary
      evidence at all -- the reference does not fit this frame.

    One unmeasurable side does not warn: a player standing on the cloth covers a
    rail, and an unmeasurable side is not a contradicted one.  A frame where
    nothing could be measured at all is unmeasurable, never bad.
    """
    if not rail:
        return None
    unverified = rail.get("unverified") or {}
    if not unverified:
        if rail.get("verified_sides") is None:
            return None                      # nothing measurable at all: not bad
        supported = rail.get("supported_sides")
        if supported is not None and supported < cfg.calibration_min_supported_sides:
            return "calibration_rail_unverified_at_time"
        return None
    reasons = {str(value) for value in unverified.values()}
    if reasons & set(CALIBRATION_REFUTE_REASONS):
        return "calibration_reference_contradicted_at_time"
    blind = sum(1 for value in unverified.values()
                if str(value) == CALIBRATION_NO_EVIDENCE_REASON)
    if blind >= cfg.calibration_min_unsupported_sides:
        return "calibration_rail_unverified_at_time"
    return None


def _warn_calibration(evidence, cfg: GateConfig, reasons: list) -> None:
    """Flag a frame whose rail evidence does not support the reference quad.

    Reported, never a verdict.  A side the frame cannot measure is not a side
    the frame contradicts, so the two cases get different reasons.
    """
    reason = calibration_warning(getattr(evidence, "rail_evidence", None), cfg)
    if reason:
        reasons.append(reason)


def judge(claim: dict, evidence, cfg: GateConfig = GateConfig()) -> GateResult:
    """Dispatch on the claim's kind; unknown kinds are left untouched."""
    if claim["kind"] == "pot":
        return pot_gate(claim, evidence, cfg)
    if claim["kind"] == "shot":
        return shot_gate(claim, evidence, cfg)
    return GateResult("unconfirmed", "kind", [f"unknown kind {claim['kind']!r}"])
