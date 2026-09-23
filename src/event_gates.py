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
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable

# canonical table geometry, same frame the scan uses
CANON_W, CANON_H = 1270.0, 2540.0
POCKETS_MM = {
    "head-left": (0.0, 0.0),
    "head-right": (CANON_W, 0.0),
    "foot-right": (CANON_W, CANON_H),
    "foot-left": (0.0, CANON_H),
    "left-side": (0.0, CANON_H / 2),
    "right-side": (CANON_W, CANON_H / 2),
}


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
    # Below this the reference cloth quad covers partly non-cloth pixels at the
    # event frame -- the VOD changes framing (sampled: 0.38-0.82 at t=450/483/
    # 1120 s against 0.85-1.00 in the calibrated segment).  Occlusion lowers it
    # too, so this is reported as a warning, never as a verdict.
    calibration_warn_fraction: float = 0.80


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
        "pocket": _pocket_name(event.get("nearest_pocket")),
        "raw": event,
    }


def _pocket_name(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    name = text.split("(")[0].strip()
    if name in POCKETS_MM:
        return name
    tail = text.rsplit(" from ", 1)
    if len(tail) == 2 and tail[1].strip() in POCKETS_MM:
        return tail[1].strip()
    return None


def nearest_pocket(x_mm: float, y_mm: float) -> tuple:
    name, best = None, float("inf")
    for pocket, (px, py) in POCKETS_MM.items():
        distance = math.hypot(x_mm - px, y_mm - py)
        if distance < best:
            name, best = pocket, distance
    return name, best


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


@dataclass
class ShotEvidence:
    """Measured between sharp frames around the event; see eval_events.probe_shot."""
    available: bool = False
    note: str | None = None
    disp_mm: float | None = None
    disp_color: str | None = None
    start_px: list | None = None
    geometry_gap_px: float | None = None
    window_motion: float | None = None
    from_in_cloth_px: float | None = None
    to_in_cloth_px: float | None = None
    start_hits: int | None = None      # independent sightings of the ball at the start
    end_hits: int | None = None        # ... and at the destination, before/after
    observations_needed: int = 2      # the ball must be sighted twice at each end
    stable_hits: int | None = None    # anchors (±0.1 s) that corroborate the same pair
    anchor_tries: int | None = None
    calibration_frac: float | None = None     # cloth pixels inside the reference quad


# --------------------------------------------------------------------- gates

def pot_gate(claim: dict, evidence: PotEvidence, cfg: GateConfig = GateConfig()) -> GateResult:
    """A pot needs a census drop that stays down, and the vanished ball at a pocket."""
    numbers = {"census_pre": evidence.census_pre, "census_post": evidence.census_post,
               "census_post_max": evidence.census_post_max, "motion_max": evidence.motion_max,
               "calibration_frac": evidence.calibration_frac}
    if not evidence.available:
        return GateResult("unconfirmed", "probe", [evidence.note or "no probe evidence"], numbers=numbers)
    if evidence.census_pre is None or evidence.census_post is None:
        return GateResult("unconfirmed", "census", ["no cloth census measured"], numbers=numbers)
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
                if not (claim["color"] and v.get("color") and claim["color"] != v["color"])]
    if not eligible:
        return GateResult("unconfirmed", "vanish", ["no_vanished_ball_measured"], numbers=numbers)
    best = min(eligible, key=lambda v: v.get("dist_mm", float("inf")))
    numbers.update({"vanish_color": best.get("color"), "vanish_mm": best.get("mm"),
                    "vanish_pocket": best.get("pocket"), "vanish_dist_mm": best.get("dist_mm"),
                    "vanish_pre_hits": best.get("pre_hits"), "approach_mm": best.get("approach_mm")})
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
               "geometry_gap_px": evidence.geometry_gap_px, "window_motion": evidence.window_motion,
               "from_in_cloth_px": evidence.from_in_cloth_px, "to_in_cloth_px": evidence.to_in_cloth_px,
               "start_hits": evidence.start_hits, "end_hits": evidence.end_hits,
               "stable_hits": evidence.stable_hits, "anchor_tries": evidence.anchor_tries,
               "calibration_frac": evidence.calibration_frac}
    if not evidence.available:
        return GateResult("unconfirmed", "probe", [evidence.note or "no probe evidence"], numbers=numbers)
    if evidence.from_in_cloth_px is None or evidence.to_in_cloth_px is None:
        return GateResult("unconfirmed", "geometry", ["claim_not_projectable"], numbers=numbers)
    numbers["min_in_cloth_px"] = round(min(evidence.from_in_cloth_px, evidence.to_in_cloth_px), 1)
    if min(evidence.from_in_cloth_px, evidence.to_in_cloth_px) < cfg.off_cloth_tol_px:
        return GateResult("rejected", "geometry", ["off_cloth"], numbers=numbers)
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


def _warn_calibration(evidence, cfg: GateConfig, reasons: list) -> None:
    """Flag a frame where the reference quad covers non-cloth pixels.

    Reported, never a verdict: occlusion lowers this number exactly when a
    player leans over the table, which is when shots happen.
    """
    frac = getattr(evidence, "calibration_frac", None)
    if frac is not None and frac < cfg.calibration_warn_fraction:
        reasons.append("calibration_weak_at_time")


def judge(claim: dict, evidence, cfg: GateConfig = GateConfig()) -> GateResult:
    """Dispatch on the claim's kind; unknown kinds are left untouched."""
    if claim["kind"] == "pot":
        return pot_gate(claim, evidence, cfg)
    if claim["kind"] == "shot":
        return shot_gate(claim, evidence, cfg)
    return GateResult("unconfirmed", "kind", [f"unknown kind {claim['kind']!r}"])
