"""Shot and pot rules over a *dense* per-frame ball track.

Every event detector this repo has built so far decided events from a sparse ball
census (1-3 classical detections per sampled frame), and the measurements showed
what that costs: 24 of 30 served events were false and all 16 pots were refuted.
The GPU ball detector being trained now (204k params, 15.5 ms/frame) will hand us
dense per-frame tracks, so the rules are written and tested *before* it lands:
the first real track can be judged the moment it exists.

Contract
--------
* one **track** = the ordered samples of ONE ball identity,
  ``(frame_index, t, x, y, confidence, occluded_flag)`` in source pixels;
* one **pocket model** = the six pocket centres in source pixels, derived from the
  verified reference geometry (``out/calib_vod30_segments.json``, source
  ``human_anchors``) - no new calibration is invented here;
* the **occlusion channel is an input**: per-sample flags or a per-frame
  distribution (``occ_share``/``occ_dense`` from :mod:`src.motion_scan`).  This
  module never recomputes it and needs no video, no OpenCV, no numpy, no torch:
  stdlib only, so it imports and runs anywhere.

Rules
-----
**Shot** - a motion *onset*: a ball still for ``rest_window_s`` (every interval in
the window at or below ``rest_speed_px_s``, at least ``rest_min_intervals``
intervals, no gap longer than ``max_gap_s``), then ``onset_intervals`` consecutive
intervals above ``motion_speed_px_s``.  The event reports the onset time (the
first sample of the sustained run, i.e. the last measured still position), the
direction, the peak speed and the duration.

**Pot** - the track terminates within a pocket radius, does not reappear for
``persistence_s``, and the occlusion channel is clear for that stretch.  A ball
that is covered by a person when it vanishes is **unknown, never potted**.

**Break** - N shot events (one per moving identity, each with its own evidence),
all sharing ``group_id``, plus one :class:`BreakGroup` record per simultaneous
cluster, flagged ``is_break`` when ``break_min_balls`` or more identities start
within ``simultaneous_window_s``.  One merged event would throw away the per-ball
directions and speeds a reviewer needs; one ungrouped event per ball would hide
that it was one physical act.  The group is additive, so a consumer can present
either one cue or N.

Nothing is silent: every disappearance, motion run, rest-only track and frame-edge
exit the gate examines is emitted as a record with its reason, the samples used
and the thresholds that decided it (:class:`Rejection` for non-events,
:class:`PotEvent` with ``verdict="unknown"`` for the occluded cases).

What the gate cannot do (stated, not hidden)
--------------------------------------------
* it cannot attribute a shot to a player - a track has no actor;
* it cannot tell a pot from a ball *parked in the jaws* of a pocket: both end
  inside the pocket radius and stop.  ``PotEvent.parked_in_jaws_possible`` flags
  the case (the last sighting is at rest) and never decides it;
* it cannot tell a pot from an identity swap: the pot rule is only as good as the
  detector's identity persistence.  A track that reappears after a
  ``persistence_s`` gap inside a pocket radius is reported as
  ``reappeared_after_gap`` with ``identity_swap_suspected``, and once an identity
  has done that none of its later disappearances is called a pot either
  (``prior_identity_swap_inside_pocket``), because its persistence has been shown
  to be unreliable;
* it cannot judge anything a track does not contain: a track that starts already
  in motion has no still stretch and yields a rejection, not a shot, so the
  associator must deliver the rest before the shot;
* it cannot see the cloth: a pocket is geometry, so a ball that vanishes near the
  rail with no pocket there is ``disappeared_outside_pocket``, not a pot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from statistics import median
from typing import Any, Iterable, NamedTuple, Sequence

# ---------------------------------------------------------------------------
# reference geometry (verified; reused, not re-derived)
# ---------------------------------------------------------------------------

#: canonical playing surface, millimetres - same frame as src/pipeline.py and
#: src/event_gates.py (portrait: x = width 1270, y = length 2540, head at top).
CANON_W, CANON_H = 1270.0, 2540.0

#: the repo's canonical pocket positions (identical to src.event_gates.POCKETS_MM,
#: so a pocket name means the same place in both modules).
POCKETS_MM: dict[str, tuple[float, float]] = {
    "head-left": (0.0, 0.0),
    "head-right": (CANON_W, 0.0),
    "foot-right": (CANON_W, CANON_H),
    "foot-left": (0.0, CANON_H),
    "left-side": (0.0, CANON_H / 2),
    "right-side": (CANON_W, CANON_H / 2),
}

#: verified reference cloth quad, source pixels, order [TL, TR, BR, BL].
#: Provenance: out/calib_vod30_segments.json -> segments[0].quad_px (t 0..1800 s,
#: source "human_anchors", built from out/pid_anchors_vod30.json anchors["70.0"][:4]).
VOD30_REFERENCE_QUAD: tuple[tuple[float, float], ...] = (
    (532.0, 323.0), (800.0, 324.0), (997.0, 569.0), (384.0, 563.0),
)

#: pixel centres of the six pockets *projected through the verified reference quad*
#: (canonical mm -> px), and the local pixel-per-millimetre scale at each centre.
#: Independent cross-check: the same file's hand pocket anchors
#: (out/pid_anchors_vod30.json anchors["70.0"], points 5 and 6) sit 4.9 px and
#: 6.8 px from these side-pocket centres, and 0.0-0.7 px from the corners - the
#: quad and the hand anchors are two independent human measurements that agree.
#: ``tests/test_shot_pot_gate.py`` re-derives every number below from
#: ``VOD30_REFERENCE_QUAD`` and fails if this table drifts.
VOD30_POCKETS_PX: dict[str, dict[str, float | tuple[float, float]]] = {
    "head-left": {"px": (532.0000, 323.0000), "px_per_mm": 0.12929},
    "head-right": {"px": (800.2126, 324.0008), "px_per_mm": 0.13329},
    "foot-right": {"px": (997.6690, 569.2265), "px_per_mm": 0.38784},
    "foot-left": {"px": (383.8673, 563.2153), "px_per_mm": 0.36457},
    "left-side": {"px": (486.8002, 396.2970), "px_per_mm": 0.19274},
    "right-side": {"px": (860.1019, 398.3787), "px_per_mm": 0.20075},
}

#: the repo's measured pot radius, ``src.event_gates.GateConfig.pot_pocket_r_mm``:
#: re-measured vanished-ball distances cluster at 39-86 mm (pocket mouth) and then
#: jump to >= 110 mm (ball still on the cloth).  In pixels this is 12.9 px at the
#: head pockets and 38.8 px at the foot pockets, because the far end of the table
#: is foreshortened ~3x - a single pixel radius would be wrong at both ends.
POCKET_R_MM = 100.0

#: ``src.motion_scan.OCC_DENSE_MIN``: share of the 61x61 px occlusion window that
#: changed, above which a person explains the motion.  Its own justification (from
#: motion_scan): a single ball changes at most ~0.14 of that window (2 x its area
#: against 61x61 at the reference), a torso changes 0.5-1.0, so 0.30 is above
#: anything one ball can reach and below anything a body reaches.  Kept equal by a
#: test, not by hope.
OCC_DENSE_MIN = 0.30


# ---------------------------------------------------------------------------
# types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Sample:
    """One sighting of one ball identity.

    ``occluded`` is the *input* occlusion flag for this frame (a person or the cue
    is over the cloth here); the gate never measures it.  Confidence is carried
    through to the evidence and not used as a gate by default (see
    ``GateThresholds.min_confidence``).
    """

    frame_index: int
    t: float
    x: float
    y: float
    confidence: float = 1.0
    occluded: bool = False

    def as_dict(self) -> dict:
        return {"frame_index": int(self.frame_index), "t": round(float(self.t), 6),
                "x": round(float(self.x), 3), "y": round(float(self.y), 3),
                "confidence": round(float(self.confidence), 4),
                "occluded": bool(self.occluded)}


@dataclass(frozen=True)
class Track:
    """Ordered samples of ONE ball identity."""

    ball_id: str
    samples: tuple[Sample, ...]

    @classmethod
    def from_rows(cls, ball_id: str, rows: Iterable[Any]) -> "Track":
        """Build from tuples ``(frame_index, t, x, y[, conf[, occluded]])`` or dicts."""
        out = []
        for row in rows:
            if isinstance(row, Sample):
                out.append(row)
                continue
            if isinstance(row, dict):
                out.append(Sample(int(row["frame_index"]), float(row["t"]), float(row["x"]),
                                  float(row["y"]), float(row.get("confidence", 1.0)),
                                  bool(row.get("occluded", False))))
                continue
            frame_index, t, x, y = row[0], row[1], row[2], row[3]
            conf = float(row[4]) if len(row) > 4 else 1.0
            occ = bool(row[5]) if len(row) > 5 else False
            out.append(Sample(int(frame_index), float(t), float(x), float(y), conf, occ))
        return cls(str(ball_id), tuple(out))

    def ordered(self) -> "Track":
        """Sort by time and drop duplicate frames (highest confidence wins).

        Two samples of one identity in one frame is an associator bug, not motion;
        keeping one keeps every interval positive, and the count of dropped
        duplicates is reported in the track evidence.
        """
        rows = sorted(self.samples, key=lambda s: (float(s.t), int(s.frame_index)))
        kept: list[Sample] = []
        seen: dict[int, int] = {}
        for s in rows:
            if s.frame_index in seen:
                i = seen[s.frame_index]
                if s.confidence > kept[i].confidence:
                    kept[i] = s
                continue
            seen[s.frame_index] = len(kept)
            kept.append(s)
        return Track(self.ball_id, tuple(kept))

    def duplicates(self) -> int:
        frames = [s.frame_index for s in self.samples]
        return len(frames) - len(set(frames))


@dataclass(frozen=True)
class Pocket:
    name: str
    x: float
    y: float
    radius_px: float
    r_mm: float

    def distance(self, x: float, y: float) -> float:
        return math.hypot(x - self.x, y - self.y)

    def contains(self, x: float, y: float) -> bool:
        return self.distance(x, y) <= self.radius_px

    def as_dict(self) -> dict:
        return {"name": self.name, "x": round(self.x, 2), "y": round(self.y, 2),
                "radius_px": round(self.radius_px, 2), "radius_mm": self.r_mm}


@dataclass(frozen=True)
class PocketModel:
    """The six pocket centres in source pixels with a per-pocket radius."""

    pockets: tuple[Pocket, ...]

    def nearest(self, x: float, y: float) -> tuple[Pocket | None, float]:
        best, dist = None, float("inf")
        for p in self.pockets:
            d = p.distance(x, y)
            if d < dist:
                best, dist = p, d
        return best, dist

    def inside(self, x: float, y: float) -> tuple[Pocket | None, float]:
        """The pocket whose radius contains ``(x, y)``, nearest first."""
        best, dist = self.nearest(x, y)
        if best is not None and dist <= best.radius_px:
            return best, dist
        return None, dist

    def by_name(self, name: str) -> Pocket:
        for p in self.pockets:
            if p.name == name:
                return p
        raise KeyError(name)

    def as_dict(self) -> dict:
        return {"pockets": [p.as_dict() for p in self.pockets]}


# ---------------------------------------------------------------------------
# geometry helpers (pure python, no numpy)
# ---------------------------------------------------------------------------

def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gauss-Jordan with partial pivoting for a small dense system."""
    n = len(matrix)
    m = [list(matrix[i]) + [rhs[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("singular system in the 4-point homography")
        m[col], m[pivot] = m[pivot], m[col]
        for row in range(n):
            if row == col or m[row][col] == 0.0:
                continue
            factor = m[row][col] / m[col][col]
            for k in range(col, n + 1):
                m[row][k] -= factor * m[col][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def homography(src: Sequence[Sequence[float]], dst: Sequence[Sequence[float]]) -> list[float]:
    """The 3x3 projective map ``src -> dst`` as a flat 9-list, h[8] == 1.

    A plain 4-point DLT, the same algebra ``cv2.getPerspectiveTransform`` runs, so
    this module stays stdlib-only and still projects the *same* reference geometry.
    """
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        b.append(u)
        a.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        b.append(v)
    return _solve(a, b) + [1.0]


def project(h: Sequence[float], point: Sequence[float]) -> tuple[float, float]:
    x, y = float(point[0]), float(point[1])
    w = h[6] * x + h[7] * y + h[8]
    if abs(w) < 1e-12:
        raise ValueError("point maps to infinity")
    return ((h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w)


def _canonical_dst() -> list[list[float]]:
    # the same destination convention as src.pipeline.homography_to_canonical
    return [[0.0, 0.0], [CANON_W - 1, 0.0], [CANON_W - 1, CANON_H - 1], [0.0, CANON_H - 1]]


def pocket_pixels(quad: Sequence[Sequence[float]] = VOD30_REFERENCE_QUAD,
                  pocket_r_mm: float = POCKET_R_MM) -> dict[str, dict]:
    """Pocket centres and radii in source pixels for a cloth quad.

    ``quad`` is [TL, TR, BR, BL] in source pixels; the canonical destination is the
    cloth rectangle, so the four corners land on the four corner pockets and the
    two side pockets land on the long rails' midpoints.  The radius is the mm
    threshold times the *local* pixel-per-mm scale at that pocket, because the far
    end of the table is foreshortened ~3x.
    """
    h = homography(_canonical_dst(), quad)
    out: dict[str, dict] = {}
    for name, (mx, my) in POCKETS_MM.items():
        centre = project(h, (mx, my))
        sx = math.dist(project(h, (mx + 1.0, my)), centre)
        sy = math.dist(project(h, (mx, my + 1.0)), centre)
        scale = (sx + sy) / 2.0
        out[name] = {"px": centre, "px_per_mm": scale, "radius_px": pocket_r_mm * scale}
    return out


def default_pocket_model(quad: Sequence[Sequence[float]] = VOD30_REFERENCE_QUAD,
                         pocket_r_mm: float = POCKET_R_MM) -> PocketModel:
    """The verified vod30 pocket model, or one derived from any other quad.

    With the reference quad the pinned :data:`VOD30_POCKETS_PX` table is used (so the
    model a reviewer reads in the source is the model the gate uses); any other quad
    is projected here.  No file is read: the reference geometry is data.
    """
    if tuple(map(tuple, quad)) == VOD30_REFERENCE_QUAD:
        derived = {n: (VOD30_POCKETS_PX[n]["px"], VOD30_POCKETS_PX[n]["px_per_mm"])
                   for n in VOD30_POCKETS_PX}
    else:
        table = pocket_pixels(quad, pocket_r_mm)
        derived = {n: (table[n]["px"], table[n]["px_per_mm"]) for n in table}
    pockets = tuple(
        Pocket(name, centre[0], centre[1], pocket_r_mm * scale, pocket_r_mm)
        for name, (centre, scale) in derived.items()
    )
    return PocketModel(pockets)


# ---------------------------------------------------------------------------
# the occlusion channel (input, never recomputed)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Occlusion:
    """The occlusion channel for a stretch of time, supplied by the caller.

    Two input shapes, and they answer different questions - the difference is
    deliberate and is what keeps a sparse track honest:

    * ``from_shares`` (a per-frame **distribution**, e.g. ``occ_dense`` from
      ``src.motion_scan``): the whole stretch from the last sighting to the end of
      the observation window is judged.  This is the strong form.
    * ``from_flags`` / ``from_samples`` (a per-frame **flag**): only the ball's own
      last sighting is judged, because a track that ended has no readings after
      it.  A frame where the flag is set can never be a pot.
    """

    times: tuple[float, ...] = ()
    covered: tuple[bool, ...] = ()
    mode: str = "none"                       # "none" | "flags" | "series"
    threshold: float | None = None
    source: str = "none"

    @classmethod
    def none(cls) -> "Occlusion":
        return cls((), (), "none", None, "none")

    @classmethod
    def from_flags(cls, times: Iterable[float], flags: Iterable[bool],
                   source: str = "flags") -> "Occlusion":
        return cls(tuple(float(t) for t in times), tuple(bool(f) for f in flags),
                   "flags", None, source)

    @classmethod
    def from_samples(cls, samples: Iterable[Sample]) -> "Occlusion":
        ss = list(samples)
        return cls.from_flags([s.t for s in ss], [s.occluded for s in ss], source="track_flags")

    @classmethod
    def from_shares(cls, times: Iterable[float], shares: Iterable[float],
                    threshold: float = OCC_DENSE_MIN, source: str = "series") -> "Occlusion":
        values = tuple(float(v) for v in shares)
        return cls(tuple(float(t) for t in times), tuple(v >= threshold for v in values),
                   "series", float(threshold), source)

    def readings(self, t0: float, t1: float) -> list[bool]:
        lo, hi = (t0, t1) if t0 <= t1 else (t1, t0)
        return [flag for t, flag in zip(self.times, self.covered) if lo <= t <= hi]

    def status(self, t0: float, t1: float) -> str:
        """``"clear"`` | ``"occluded"`` | ``"silent"`` over ``[t0, t1]``.

        ``silent`` is not ``clear``: no reading is no evidence, and the pot rule
        treats it as unknown.
        """
        if self.mode == "none":
            return "silent"
        rows = self.readings(t0, t1)
        if not rows:
            return "silent"
        return "occluded" if any(rows) else "clear"

    def status_at_disappearance(self, last_t: float, until_t: float) -> str:
        """The occlusion verdict for a disappearance.

        Flags judge the last sighting (a point window), a series judges the whole
        persistence window - see the class docstring.
        """
        if self.mode == "series":
            return self.status(last_t, until_t)
        if self.mode == "flags":
            window = 1e-9
            return self.status(last_t - window, last_t + window)
        return "silent"

    def as_dict(self) -> dict:
        return {"mode": self.mode, "source": self.source, "threshold": self.threshold,
                "n_readings": len(self.times)}


# ---------------------------------------------------------------------------
# thresholds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateThresholds:
    """Every bar the gate uses, with the reason it has that value.

    The bars are set from geometry and from the detector's own frame period, not
    from the emptied event queue (there is none) and not from the 25 known movers
    (that set belongs to another worker).  A ball's pixel radius on vod30 is
    3.7-11.1 px (28.6 mm x the reference quad's 0.129-0.388 px/mm), so the numbers
    below are all stated in fractions of a ball.
    """

    # --- still and motion (a ball is 57.15 mm wide, i.e. 3.7-11.1 px here) ------
    #: a ball is "at rest" if nothing moves faster than this.  6 px/s = 0.2 px per
    #: 30 fps frame: below the detector's own positional noise floor and below 6%
    #: of the smallest ball radius, so a resting ball cannot trip it, while a ball
    #: genuinely on its way to a pocket (>=100 px of travel) is not called still.
    rest_speed_px_s: float = 6.0
    #: the still stretch must last this long.  0.5 s = 15 dense frames, and a ball
    #: moving at the motion bar below covers 20 px (2-5 ball diameters) in that
    #: time - so "still for 0.5 s" cannot be satisfied by a ball in motion.
    rest_window_s: float = 0.5
    #: ... and must contain at least this many intervals, so two samples cannot
    #: define rest (a 3-sample minimum in the still stretch).
    rest_min_intervals: int = 2
    #: "moving" bar: 40 px/s = 1.3 px per 30 fps frame, 12-36% of a ball radius per
    #: frame and 6.7x the rest bar.  A single-frame detector jump of a whole ball
    #: radius cannot hold it for 3 consecutive frames; a soft shot crossing 300 px
    #: in 1 s (300 px/s) exceeds it 7.5x.
    motion_speed_px_s: float = 40.0
    #: sustained motion: 3 consecutive above-bar intervals = >= 0.1 s of commitment
    #: at 30 fps.  1-2 frames is exactly the regime of identity flicker and label
    #: swaps, so the onset must outlast it.
    onset_intervals: int = 3
    #: an interval longer than this breaks a run: at 30 fps that is 7-8 missing
    #: frames, and "sustained" cannot be claimed across a stretch the ball was not
    #: seen in.  Also the reason a sparse (0.5 s) census can never form a run.
    max_gap_s: float = 0.25

    # --- pot ------------------------------------------------------------------
    #: the repo's measured pot radius: src.event_gates.GateConfig.pot_pocket_r_mm.
    pocket_r_mm: float = POCKET_R_MM
    #: a potted ball is gone for good: 1.0 s = 30 dense frames of absence, ~100x the
    #: frame period and far longer than a one-frame dropout, while the ball's last
    #: ~40 px into the pocket take <=0.2 s at a modest 200 px/s.
    persistence_s: float = 1.0
    #: a disappearance must be at least this long ...
    vanish_min_s: float = 0.4
    #: ... and at least this many of the track's *own* intervals, so a track sampled
    #: every 0.5 s is not read as vanishing between two normal samples.  Dense 30 fps
    #: tracks keep the 0.4 s floor (4 x 0.033 s = 0.13 s).
    vanish_cadence_multiple: float = 4.0

    # --- frame and cloth ------------------------------------------------------
    #: (width, height) in pixels.  None skips the frame-edge test and the gate then
    #: reports it as not measured rather than passing it.
    frame_size: tuple[int, int] | None = None
    #: a ball whose last sighting is this close to the image border is leaving the
    #: frame, not entering a pocket.  20 px is ~2-5 ball radii.
    edge_margin_px: float = 20.0
    #: the reference cloth quad [TL, TR, BR, BL] in pixels.  None skips the
    #: off-cloth test (a corner pocket sits *on* the cloth boundary, so the cloth
    #: test only ever rejects a disappearance that is not inside a pocket radius).
    cloth_quad: tuple[tuple[float, float], ...] | None = None

    # --- grouping (breaks) ----------------------------------------------------
    #: onset times within this of each other are one physical act.  0.15 s is ~4
    #: dense frames: a cue ball reaches the rack in one frame only at 15 m/s, so a
    #: real rack contact starts its neighbours inside one or two frames.
    simultaneous_window_s: float = 0.15
    #: a break scatters >= 3 identities.  2 movers is a cue ball plus the one ball
    #: it contacted (a normal shot); one contact cannot start 3 identities at once.
    break_min_balls: int = 3

    # --- evidence -------------------------------------------------------------
    #: samples below this are recorded but do not vote.  0.0 = keep everything:
    #: identity/confidence filtering belongs to the associator (src.ball_census),
    #: not to the event rule, and the floor the track actually reached is reported.
    min_confidence: float = 0.0
    #: how many of the ball's last samples a pot/unknown record carries as evidence.
    evidence_samples: int = 6

    def as_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# event records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShotEvent:
    """A motion onset with the evidence that produced it."""

    kind: str
    ball_id: str
    onset_frame_index: int
    onset_t: float
    onset_x: float
    onset_y: float
    direction_deg: float | None          # image space: 0 = +x (right), 90 = +y (down)
    direction_x: float
    direction_y: float
    peak_speed_px_s: float
    peak_t: float
    duration_s: float
    path_length_px: float
    net_displacement_px: float
    rest_window_measured_s: float
    rest_intervals: int
    max_rest_speed_px_s: float
    ends_in_pocket: bool
    end_pocket: str | None
    end_distance_px: float
    endless_roll: bool
    group_id: str | None
    is_break: bool
    samples_used: tuple[Sample, ...]
    thresholds: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "ball_id": self.ball_id,
                "onset_frame_index": int(self.onset_frame_index),
                "onset_t": round(self.onset_t, 6),
                "onset": [round(self.onset_x, 2), round(self.onset_y, 2)],
                "direction_deg": None if self.direction_deg is None else round(self.direction_deg, 2),
                "direction": [round(self.direction_x, 4), round(self.direction_y, 4)],
                "peak_speed_px_s": round(self.peak_speed_px_s, 2),
                "peak_t": round(self.peak_t, 6),
                "duration_s": round(self.duration_s, 6),
                "path_length_px": round(self.path_length_px, 2),
                "net_displacement_px": round(self.net_displacement_px, 2),
                "rest_window_measured_s": round(self.rest_window_measured_s, 6),
                "rest_intervals": int(self.rest_intervals),
                "max_rest_speed_px_s": round(self.max_rest_speed_px_s, 3),
                "ends_in_pocket": bool(self.ends_in_pocket), "end_pocket": self.end_pocket,
                "end_distance_px": round(self.end_distance_px, 2),
                "endless_roll": bool(self.endless_roll),
                "group_id": self.group_id, "is_break": bool(self.is_break),
                "samples_used": [s.as_dict() for s in self.samples_used],
                "thresholds": dict(self.thresholds)}


@dataclass(frozen=True)
class PotEvent:
    """A disappearance judged against a pocket: verdict ``pot`` or ``unknown``.

    ``unknown`` is the verdict whenever the evidence is missing or contradicted -
    a person over the cloth, a silent occlusion channel, no observation window
    after the disappearance.  It is never silently a pot.
    """

    kind: str
    ball_id: str
    verdict: str                         # "pot" | "unknown"
    reason: str
    pocket: str | None
    pocket_px: tuple[float, float] | None
    radius_px: float | None
    distance_px: float | None
    last_frame_index: int
    last_t: float
    last_x: float
    last_y: float
    last_speed_px_s: float
    parked_in_jaws_possible: bool
    observed_until_t: float
    persistence_s: float
    gap_s: float
    internal_gap: bool
    identity_swap_suspected: bool
    occlusion_status: str
    occlusion_source: str
    samples_used: tuple[Sample, ...]
    thresholds: dict = field(default_factory=dict)

    @property
    def is_pot(self) -> bool:
        return self.verdict == "pot"

    def as_dict(self) -> dict:
        return {"kind": self.kind, "ball_id": self.ball_id, "verdict": self.verdict,
                "reason": self.reason, "pocket": self.pocket,
                "pocket_px": None if self.pocket_px is None else [round(c, 2) for c in self.pocket_px],
                "radius_px": None if self.radius_px is None else round(self.radius_px, 2),
                "distance_px": None if self.distance_px is None else round(self.distance_px, 2),
                "last_frame_index": int(self.last_frame_index),
                "last_t": round(self.last_t, 6),
                "last": [round(self.last_x, 2), round(self.last_y, 2)],
                "last_speed_px_s": round(self.last_speed_px_s, 2),
                "parked_in_jaws_possible": bool(self.parked_in_jaws_possible),
                "observed_until_t": round(self.observed_until_t, 6),
                "persistence_s": round(self.persistence_s, 6),
                "gap_s": round(self.gap_s, 6),
                "internal_gap": bool(self.internal_gap),
                "identity_swap_suspected": bool(self.identity_swap_suspected),
                "occlusion_status": self.occlusion_status,
                "occlusion_source": self.occlusion_source,
                "samples_used": [s.as_dict() for s in self.samples_used],
                "thresholds": dict(self.thresholds)}


@dataclass(frozen=True)
class Rejection:
    """A non-event the gate looked at and refused, with its reason."""

    kind: str                            # always "rejection"
    code: str
    ball_id: str
    reason: str
    t: float | None
    frame_index: int | None
    numbers: dict = field(default_factory=dict)
    samples_used: tuple[Sample, ...] = ()
    thresholds: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "code": self.code, "ball_id": self.ball_id,
                "reason": self.reason,
                "t": None if self.t is None else round(self.t, 6),
                "frame_index": None if self.frame_index is None else int(self.frame_index),
                "numbers": dict(self.numbers),
                "samples_used": [s.as_dict() for s in self.samples_used],
                "thresholds": dict(self.thresholds)}


@dataclass(frozen=True)
class BreakGroup:
    """The group record for simultaneous onsets - see the module docstring."""

    kind: str
    group_id: str
    ball_ids: tuple[str, ...]
    t_start: float
    t_end: float
    n_balls: int
    is_break: bool

    def as_dict(self) -> dict:
        return {"kind": self.kind, "group_id": self.group_id,
                "ball_ids": list(self.ball_ids), "t_start": round(self.t_start, 6),
                "t_end": round(self.t_end, 6), "n_balls": int(self.n_balls),
                "is_break": bool(self.is_break)}


@dataclass
class GateReport:
    """Everything the gate found, and everything it refused to call an event."""

    shots: list[ShotEvent] = field(default_factory=list)
    pots: list[PotEvent] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    breaks: list[BreakGroup] = field(default_factory=list)
    tracks_in: int = 0
    observed_until_t: float | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"shots": [s.as_dict() for s in self.shots],
                "pots": [p.as_dict() for p in self.pots],
                "rejections": [r.as_dict() for r in self.rejections],
                "breaks": [b.as_dict() for b in self.breaks],
                "counts": {"tracks": self.tracks_in, "shots": len(self.shots),
                           "pots": sum(1 for p in self.pots if p.is_pot),
                           "unknowns": sum(1 for p in self.pots if not p.is_pot),
                           "rejections": len(self.rejections), "breaks": len(self.breaks)},
                "observed_until_t": self.observed_until_t,
                "notes": list(self.notes)}


# ---------------------------------------------------------------------------
# the rules
# ---------------------------------------------------------------------------

class _Iv(NamedTuple):
    """One interval between consecutive samples, by index."""

    ia: int
    ib: int
    dt: float
    dist: float
    speed: float


def _intervals(samples: Sequence[Sample]) -> list[_Iv]:
    """Intervals between consecutive samples with a positive dt, indexed."""
    out = []
    for i in range(len(samples) - 1):
        a, b = samples[i], samples[i + 1]
        dt = float(b.t) - float(a.t)
        if dt <= 0.0:
            continue
        dist = math.hypot(b.x - a.x, b.y - a.y)
        out.append(_Iv(i, i + 1, dt, dist, dist / dt))
    return out


def _still_stretch(samples: Sequence[Sample], onset_index: int,
                   th: GateThresholds) -> tuple[int, float, int, float]:
    """How much rest precedes ``samples[onset_index]``.

    Returns ``(first_still_index, measured_window_s, intervals, max_speed)`` - the
    stretch of consecutive intervals ending at the onset sample whose speed is at
    or below the rest bar and whose gap is at or below the motion gap bar.
    """
    intervals = [iv for iv in _intervals(samples) if iv.ib <= onset_index]
    first = onset_index
    max_speed = 0.0
    n = 0
    for iv in reversed(intervals):
        if iv.dt > th.max_gap_s or iv.speed > th.rest_speed_px_s:
            break
        max_speed = max(max_speed, iv.speed)
        n += 1
        first = iv.ia
    window = 0.0 if n == 0 else float(samples[onset_index].t) - float(samples[first].t)
    return first, window, n, max_speed


def _motion_runs(samples: Sequence[Sample], th: GateThresholds) -> list[tuple[int, int]]:
    """Maximal (start_index, end_index) runs of consecutive above-bar intervals."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, iv in enumerate(_intervals(samples)):
        hot = iv.speed > th.motion_speed_px_s and iv.dt <= th.max_gap_s
        if hot and start is None:
            start = i
        elif not hot and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(samples) - 1))
    return runs


def _vanishing_candidates(samples: Sequence[Sample], until_t: float,
                          th: GateThresholds) -> tuple[float, list[tuple[int, int, float]]]:
    """Every disappearance in the track: internal gaps plus the trailing one.

    A gap counts as a disappearance only if it is at least ``vanish_min_s`` *and*
    at least ``vanish_cadence_multiple`` x the track's own median interval: a
    track sampled every 0.5 s must not read its normal cadence as vanishing.
    Returns ``(vanish_gap_s, [(start_index, end_index, gap_s), ...])`` where
    ``end_index == -1`` marks the trailing disappearance after the last sample.
    """
    intervals = _intervals(samples)
    cadence = median([iv.dt for iv in intervals]) if intervals else 0.0
    vanish_gap = max(th.vanish_min_s, th.vanish_cadence_multiple * cadence)
    out = [(iv.ia, iv.ib, iv.dt) for iv in intervals if iv.dt >= vanish_gap]
    if samples and until_t > float(samples[-1].t):
        trailing = until_t - float(samples[-1].t)
        if trailing >= vanish_gap:
            out.append((len(samples) - 1, -1, trailing))
    return vanish_gap, out


def _inside_frame(x: float, y: float, th: GateThresholds) -> bool | None:
    if th.frame_size is None:
        return None
    w, h = float(th.frame_size[0]), float(th.frame_size[1])
    m = th.edge_margin_px
    return (m <= x <= w - m) and (m <= y <= h - m)


def _inside_quad(x: float, y: float, quad: Sequence[Sequence[float]] | None) -> bool | None:
    """Point-in-convex-quad by consistent cross-product sign; None when no quad."""
    if not quad:
        return None
    pts = [(float(p[0]), float(p[1])) for p in quad]
    signs = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        signs.append((bx - ax) * (y - ay) - (by - ay) * (x - ax))
    return all(s >= 0 for s in signs) or all(s <= 0 for s in signs)


def track_events(track: Track, pockets: PocketModel,
                 occlusion: Occlusion | None = None,
                 thresholds: GateThresholds = GateThresholds(),
                 observed_until_t: float | None = None,
                 group_ids: dict[str, str] | None = None) -> tuple[list[ShotEvent],
                                                                   list[PotEvent], list[Rejection]]:
    """Shots, pot verdicts and rejections for ONE ball identity.

    ``observed_until_t`` is the last time the analyser watched: a track that ends at
    that time can never satisfy the persistence window, and the gate then says
    ``unknown / no_persistence_window`` instead of guessing a pot.
    """
    th = thresholds
    t = track.ordered()
    samples = list(t.samples)
    shots: list[ShotEvent] = []
    pots: list[PotEvent] = []
    rejections: list[Rejection] = []
    occ = occlusion if occlusion is not None else Occlusion.from_samples(samples)
    if not samples:
        rejections.append(Rejection("rejection", "empty_track", t.ball_id, "no samples",
                                    None, None, {"samples": 0},
                                    thresholds={"min_samples": 3}))
        return shots, pots, rejections
    if len(samples) < 3:
        rejections.append(Rejection(
            "rejection", "track_too_short", t.ball_id,
            "fewer than 3 samples: no interval pair can establish still-then-moving",
            float(samples[-1].t), int(samples[-1].frame_index),
            {"samples": len(samples), "duplicates": t.duplicates()},
            tuple(samples), thresholds={"min_samples": 3}))
        return shots, pots, rejections

    kept = [s for s in samples if s.confidence >= th.min_confidence]
    if len(kept) < 3:
        rejections.append(Rejection(
            "rejection", "below_confidence_floor", t.ball_id,
            f"only {len(kept)} of {len(samples)} samples reach the "
            f"{th.min_confidence:.3f} confidence floor: too few samples are left to measure "
            "still-then-moving (the floor is a caller setting, not a verdict)",
            float(samples[-1].t), int(samples[-1].frame_index),
            {"samples": len(samples), "kept": len(kept),
             "max_confidence": round(max(s.confidence for s in samples), 4)},
            tuple(samples), thresholds={"min_confidence": th.min_confidence,
                                        "min_samples": 3}))
        return shots, pots, rejections
    samples = kept
    min_conf = min(s.confidence for s in samples)

    # ---- shot rule ---------------------------------------------------------
    runs = _motion_runs(samples, th)
    rest_thresholds = {"rest_speed_px_s": th.rest_speed_px_s, "rest_window_s": th.rest_window_s,
                       "rest_min_intervals": th.rest_min_intervals, "max_gap_s": th.max_gap_s,
                       "motion_speed_px_s": th.motion_speed_px_s,
                       "onset_intervals": th.onset_intervals}
    moved = False
    for start, end in runs:
        moved = True
        intervals = [iv for iv in _intervals(samples) if start <= iv.ia and iv.ib <= end]
        if len(intervals) < th.onset_intervals:
            # above the speed bar but not sustained: exactly the shape of a
            # single-frame identity jump.  Refused, and named.
            rejections.append(Rejection(
                "rejection", "motion_too_short", t.ball_id,
                f"a {len(intervals)}-interval burst above the motion bar at "
                f"t={samples[start].t:.3f} is shorter than the {th.onset_intervals} intervals a "
                "sustained onset needs (a detector jump, not a shot)",
                float(samples[start].t), int(samples[start].frame_index),
                {"burst_intervals": len(intervals),
                 "burst_speed_px_s": round(max(iv.speed for iv in intervals), 2),
                 "burst_displacement_px": round(sum(iv.dist for iv in intervals), 2)},
                tuple(samples[start:end + 1]), rest_thresholds))
            continue                            # too short to be a sustained onset
        first_still, window, n_rest, max_rest = _still_stretch(samples, start, th)
        a, b = samples[start], samples[end]
        path = sum(iv.dist for iv in intervals)
        net = math.hypot(b.x - a.x, b.y - a.y)
        if net <= 0:
            direction = (0.0, 0.0)
            deg = None                     # motion that returns to its start has no direction
        else:
            direction = ((b.x - a.x) / net, (b.y - a.y) / net)
            deg = math.degrees(math.atan2(direction[1], direction[0])) % 360.0
        pocket, dist = pockets.inside(b.x, b.y)
        lasts = end == len(samples) - 1
        endless = bool(lasts and pocket is None)
        peak_speed, peak_t = 0.0, float(a.t)
        for iv in intervals:
            if iv.speed > peak_speed:
                peak_speed, peak_t = iv.speed, float(samples[iv.ib].t)
        evidence = tuple(samples[max(0, first_still):end + 1])
        if window + 1e-12 < th.rest_window_s or n_rest < th.rest_min_intervals:
            rejections.append(Rejection(
                "rejection", "no_still_stretch", t.ball_id,
                f"motion onset at t={a.t:.3f} has only {window:.2f} s of rest in "
                f"{n_rest} intervals (needs {th.rest_window_s:.2f} s in "
                f"{th.rest_min_intervals}); a track that starts already moving is not a shot",
                float(a.t), int(a.frame_index),
                {"rest_window_measured_s": round(window, 4), "rest_intervals": n_rest,
                 "max_rest_speed_px_s": round(max_rest, 3),
                 "peak_speed_px_s": round(peak_speed, 2),
                 "net_displacement_px": round(net, 2), "endless_roll": endless},
                evidence, rest_thresholds))
            continue
        gid = (group_ids or {}).get(t.ball_id)
        shots.append(ShotEvent(
            "shot", t.ball_id, int(a.frame_index), float(a.t), float(a.x), float(a.y),
            deg, direction[0], direction[1], peak_speed, peak_t,
            float(b.t) - float(a.t), path, net, window, n_rest, max_rest,
            pocket is not None, None if pocket is None else pocket.name, dist,
            endless, gid, False, evidence, rest_thresholds))
        if endless:
            rejections.append(Rejection(
                "rejection", "roll_without_pocket", t.ball_id,
                "the motion run reaches the end of the track on open cloth: a ball that "
                "rolled and was never seen to stop at a pocket is not a pot",
                float(b.t), int(b.frame_index),
                {"nearest_pocket": None if pocket is None else pocket.name,
                 "distance_px": round(dist, 2),
                 "radius_px": None if pocket is None else round(pocket.radius_px, 2),
                 "last_speed_px_s": round(intervals[-1].speed, 2) if intervals else None},
                tuple(samples[max(0, end - 1):end + 1]), rest_thresholds))
    if not moved:
        speeds = [iv.speed for iv in _intervals(samples)]
        rejections.append(Rejection(
            "rejection", "no_motion_onset", t.ball_id,
            f"no sustained motion: peak interval speed {max(speeds, default=0.0):.2f} px/s is at "
            f"or below the {th.motion_speed_px_s:.1f} px/s bar (a ball at rest, or jitter)",
            float(samples[-1].t), int(samples[-1].frame_index),
            {"max_interval_speed_px_s": round(max(speeds, default=0.0), 3),
             "n_intervals": len(speeds), "samples": len(samples),
             "min_confidence": round(min_conf, 4), "duplicates": t.duplicates()},
            tuple(samples[:th.evidence_samples]), rest_thresholds))

    # ---- pot rule ----------------------------------------------------------
    until = float(observed_until_t) if observed_until_t is not None else float(samples[-1].t)
    vanish_gap, candidates = _vanishing_candidates(samples, until, th)
    pot_thresholds = {"pocket_r_mm": th.pocket_r_mm, "persistence_s": th.persistence_s,
                      "vanish_gap_s": round(vanish_gap, 4),
                      "occlusion_threshold": occ.threshold,
                      "occlusion_mode": occ.mode}
    if not candidates:
        # The track ends where the data ends, or the gap is too short to be a
        # disappearance.  Either way nothing may be said about a pot - and saying
        # nothing at all would be a silent event.
        last0 = samples[-1]
        pocket0, dist0 = pockets.inside(last0.x, last0.y)
        rejections.append(Rejection(
            "rejection", "track_ends_at_window_end", t.ball_id,
            f"the last sighting at t={last0.t:.3f} is not followed by a disappearance longer than "
            f"the {vanish_gap:.2f} s vanish gap (observation ends at t={until:.3f}): a track that "
            "stops with the data cannot be read as a pot",
            float(last0.t), int(last0.frame_index),
            {"observed_until_t": round(until, 4),
             "gap_after_last_s": round(max(0.0, until - float(last0.t)), 4),
             "vanish_gap_s": round(vanish_gap, 4),
             "pocket": None if pocket0 is None else pocket0.name,
             "distance_px": round(dist0, 2),
             "inside_pocket_radius": pocket0 is not None},
            tuple(samples[-th.evidence_samples:]), pot_thresholds))
    swap_seen = False
    for start, end, gap in candidates:
        last = samples[start]
        tail = samples[max(0, start - (th.evidence_samples - 1)):start + 1]
        prev_speed = 0.0
        if start > 0:
            d = math.hypot(last.x - samples[start - 1].x, last.y - samples[start - 1].y)
            dt = float(last.t) - float(samples[start - 1].t)
            prev_speed = d / dt if dt > 0 else 0.0
        internal = end != -1
        pocket, dist = pockets.inside(last.x, last.y)
        span_until = float(samples[end].t) if internal else until
        occ_status = occ.status_at_disappearance(float(last.t), span_until)
        parked = prev_speed <= th.rest_speed_px_s
        common = dict(
            last_frame_index=int(last.frame_index), last_t=float(last.t),
            last_x=float(last.x), last_y=float(last.y), last_speed_px_s=prev_speed,
            parked_in_jaws_possible=parked, observed_until_t=until,
            persistence_s=th.persistence_s, gap_s=gap, internal_gap=internal,
            identity_swap_suspected=False, occlusion_status=occ_status,
            occlusion_source=occ.source, samples_used=tuple(tail),
            thresholds=pot_thresholds)
        if internal:
            # the ball is seen again -> not a pot.  Inside a pocket radius for a whole
            # persistence window this is the signature of an identity swap, which the
            # gate can name but not resolve.
            swap = bool(pocket is not None and gap >= th.persistence_s)
            swap_seen = swap_seen or swap
            rejections.append(Rejection(
                "rejection", "reappeared_after_gap", t.ball_id,
                f"the identity was seen again {gap:.3f} s later at t={samples[end].t:.3f}; a gap "
                "is a gap, not a pot",
                float(last.t), int(last.frame_index),
                {"gap_s": round(gap, 4), "reappeared_t": round(float(samples[end].t), 4),
                 "pocket": None if pocket is None else pocket.name,
                 "distance_px": round(dist, 2),
                 "identity_swap_suspected": swap},
                tuple(tail), pot_thresholds))
            if swap:
                pots.append(PotEvent("pot", t.ball_id, "unknown",
                                     "reappeared_after_gap_inside_pocket",
                                     pocket.name, (pocket.x, pocket.y), pocket.radius_px, dist,
                                     **dict(common, identity_swap_suspected=True)))
            continue
        if _inside_frame(last.x, last.y, th) is False and pocket is None:
            rejections.append(Rejection(
                "rejection", "left_frame_edge", t.ball_id,
                f"the last sighting is within {th.edge_margin_px:.0f} px of the image border, "
                "outside every pocket radius: the ball left the frame, which is not a pocket",
                float(last.t), int(last.frame_index),
                {"last_xy": [round(last.x, 2), round(last.y, 2)],
                 "frame_size": list(th.frame_size) if th.frame_size else None,
                 "nearest_pocket": pockets.nearest(last.x, last.y)[0].name,
                 "distance_px": round(dist, 2),
                 "radius_px": round(pockets.nearest(last.x, last.y)[0].radius_px, 2)},
                tuple(tail), pot_thresholds))
            continue
        if _inside_quad(last.x, last.y, th.cloth_quad) is False and pocket is None:
            rejections.append(Rejection(
                "rejection", "left_cloth", t.ball_id,
                "the last sighting is outside the reference cloth quad and outside every pocket "
                "radius: the ball left the playing surface",
                float(last.t), int(last.frame_index),
                {"last_xy": [round(last.x, 2), round(last.y, 2)],
                 "nearest_pocket": pockets.nearest(last.x, last.y)[0].name,
                 "distance_px": round(dist, 2)},
                tuple(tail), pot_thresholds))
            continue
        if pocket is None:
            near, near_dist = pockets.nearest(last.x, last.y)
            rejections.append(Rejection(
                "rejection", "disappeared_outside_pocket", t.ball_id,
                f"the track ends {dist:.1f} px from the nearest pocket "
                f"({near.name if near else 'none'}, radius "
                f"{near.radius_px if near else float('nan'):.1f} px): a disappearance on open "
                "cloth is a detector dropout, not a pot",
                float(last.t), int(last.frame_index),
                {"nearest_pocket": None if near is None else near.name,
                 "distance_px": round(dist, 2),
                 "nearest_distance_px": round(near_dist, 2),
                 "radius_px": None if near is None else round(near.radius_px, 2),
                 "gap_s": round(gap, 4),
                 "frame_edge": _inside_frame(last.x, last.y, th),
                 "inside_cloth": _inside_quad(last.x, last.y, th.cloth_quad)},
                tuple(tail), pot_thresholds))
            continue
        if gap < th.persistence_s:
            pots.append(PotEvent("pot", t.ball_id, "unknown", "no_persistence_window",
                                 pocket.name, (pocket.x, pocket.y), pocket.radius_px, dist,
                                 **common))
            continue
        if occ_status == "occluded":
            pots.append(PotEvent("pot", t.ball_id, "unknown", "cloth_occluded_at_disappearance",
                                 pocket.name, (pocket.x, pocket.y), pocket.radius_px, dist,
                                 **common))
            continue
        if occ_status == "silent":
            pots.append(PotEvent("pot", t.ball_id, "unknown", "occlusion_channel_silent",
                                 pocket.name, (pocket.x, pocket.y), pocket.radius_px, dist,
                                 **common))
            continue
        if parked:
            # A ball at rest inside the pocket radius is exactly the shape of a ball
            # parked in the jaws of the pocket, and no track fact separates the two.
            pots.append(PotEvent("pot", t.ball_id, "unknown", "at_rest_inside_pocket_radius",
                                 pocket.name, (pocket.x, pocket.y), pocket.radius_px, dist,
                                 **common))
            continue
        if swap_seen:
            # This identity was already seen to reappear after a full persistence
            # window inside a pocket radius: its persistence is not trustworthy, so
            # its next disappearance cannot be called a pot either.
            pots.append(PotEvent("pot", t.ball_id, "unknown", "prior_identity_swap_inside_pocket",
                                 pocket.name, (pocket.x, pocket.y), pocket.radius_px, dist,
                                 **dict(common, identity_swap_suspected=True)))
            continue
        pots.append(PotEvent("pot", t.ball_id, "pot", "inside_pocket_persistence_clear",
                             pocket.name, (pocket.x, pocket.y), pocket.radius_px, dist,
                             **common))
    return shots, pots, rejections


def _group_onsets(shots: list[ShotEvent], th: GateThresholds) -> list[BreakGroup]:
    """Cluster shot onsets by time; label every member, break-emit the big ones."""
    groups: list[BreakGroup] = []
    if not shots:
        return groups
    ordered = sorted(shots, key=lambda s: s.onset_t)
    clusters: list[list[ShotEvent]] = [[ordered[0]]]
    for s in ordered[1:]:
        if s.onset_t - clusters[-1][-1].onset_t <= th.simultaneous_window_s:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    for i, members in enumerate(clusters):
        gid = f"onset-{i}"
        ids = tuple(m.ball_id for m in members)
        is_break = len(ids) >= th.break_min_balls
        for m in members:
            object.__setattr__(m, "group_id", gid)
            object.__setattr__(m, "is_break", is_break)
        groups.append(BreakGroup("break_group", gid, ids, members[0].onset_t,
                                 members[-1].onset_t, len(ids), is_break))
    return groups


def classify(tracks: Iterable[Track], pockets: PocketModel | None = None,
             occlusion: Occlusion | None = None,
             thresholds: GateThresholds = GateThresholds(),
             observed_until_t: float | None = None) -> GateReport:
    """Run the shot, pot and break rules over a batch of tracks.

    ``observed_until_t`` defaults to the latest sample in the batch - the analysed
    window ends where the data ends, and a track that ends there earns
    ``unknown / no_persistence_window`` rather than a free pot.
    """
    tracks = [t.ordered() for t in tracks]
    model = pockets if pockets is not None else default_pocket_model(
        quad=thresholds.cloth_quad or VOD30_REFERENCE_QUAD,
        pocket_r_mm=thresholds.pocket_r_mm)
    if observed_until_t is None:
        last = [float(t.samples[-1].t) for t in tracks if t.samples]
        observed_until_t = max(last) if last else None
    until = observed_until_t
    report = GateReport(tracks_in=len(tracks), observed_until_t=until)
    shots: list[ShotEvent] = []
    for tr in tracks:
        s, p, r = track_events(tr, model, occlusion=occlusion, thresholds=thresholds,
                               observed_until_t=until)
        shots.extend(s)
        report.pots.extend(p)
        report.rejections.extend(r)
    report.breaks = _group_onsets(shots, thresholds)
    shots.sort(key=lambda s: s.onset_t)
    report.shots = shots
    report.pots.sort(key=lambda p: (p.last_t, p.ball_id))
    report.rejections.sort(key=lambda r: (r.t if r.t is not None else -1.0, r.ball_id))
    report.notes.append(
        f"{len(shots)} shot(s), {sum(1 for p in report.pots if p.is_pot)} pot(s), "
        f"{sum(1 for p in report.pots if not p.is_pot)} unknown disappearance(s), "
        f"{len(report.rejections)} rejection(s), {sum(1 for b in report.breaks if b.is_break)} break(s)")
    return report
