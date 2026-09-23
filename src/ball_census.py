"""Fused ball census: classical detections + SAM3 + temporal association.

The info-complete scan measures a census of 1-3 classical ball detections per
sampled frame, so one ball leaving the cloth is unmeasurable: the frame count
drops by one whether a ball was potted or the colour blob detector missed it,
and nothing in the scan tells the two apart.  ``out/scan30/sam3_results.json``
already holds SAM3-verified ball positions for 56 frames (10 balls on a full
rack), and ``out/scan30/sam3_census.json`` holds the frames this round added on
demand; neither is used by the scan's own census.

This module fuses them into one census:

* every measurement is an :class:`Observation` carrying its source, a
  normalised colour and a table position in millimetres;
* observations at the same time and place are *one ball*, never two, so a
  classical blob and an SAM3 mask on the same ball do not double the count;
* a ball seen in >= 2 frames becomes a stable *identity* (:class:`Track`), with
  a majority colour and a hit count, so "the same ball" is not re-guessed per
  frame -- a two-frame flicker is an identity, a one-frame blob is not;
* each per-frame report keeps the two source counts visible, so a window whose
  two sides were measured by different detectors can never be read as a drop it
  did not measure (``census_comparable``).

Deliberate asymmetry, borrowed from the scan: a *presence* refutes a vanish
(SAM3 sees the ball, so it did not go in the pocket); an *absence* only counts
where both sides are covered.  Extra detections are shadows and never hide the
truth; a missing detection may just be a missing measurement.

Nothing here touches the video: the caller hands in observations and a
projector, so the fusion is testable without a VOD.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable

CENSUS_VERSION = 1

# Same-ball thresholds between two observations (960x540 frame pixels; the
# cloth is ~2.8 mm/px, so a ball is ~20 px across and a racked ball ~20 px from
# its neighbour).  30 px is a ball and a half: enough for a slow roll between
# samples, small enough that a racked neighbour is never "the same ball".
TRACK_MATCH_PX = 30.0
# A colour misread on the same ball (a stripe's band vs its white area) shows up
# within a few pixels; anything further is another ball.
COLOR_FLICKER_PX = 14.0
# An identity a brief occlusion split re-joins across a short gap if the ball
# comes back near where it left; a potted ball does not come back.
STITCH_GAP_S = 1.0
STITCH_PX = 45.0
# A track survives this long without an observation before it is closed.
TRACK_GAP_S = 2.0
# Observations this close in time are the same frame (30 fps = 0.033 s).
TIME_BUCKET_S = 0.02
# Extrapolating a rolling ball's position is only safe over a short lead.
MAX_PREDICT_S = 0.5

UNKNOWN = "unknown"
# Colours whose detector class holds exactly one physical ball on a rack: a
# detection of that colour after a claimed pot disproves the pot.  "white" is
# NOT unique (cue ball + stripe whites share the class) and the solid colours
# occur four times each.
UNIQUE_COLORS = frozenset({"black"})
# The detector reports the hue-wraparound red band as a second colour name.
COLOR_ALIASES = {"red2": "red", "red1": "red"}

# SAM3 detections below this score were already dropped upstream (see
# src/scan_events.sam3_confirm); mirrored here so a caller cannot smuggle in a
# weaker detection and call it a measurement.
SAM3_MIN_SCORE = 0.62
# A settled table with a rack on it holds at least this many balls: a frame
# whose measured count is below it measured occlusion or a bad exposure, not an
# empty table.  Applied to SAM3-covered sides only (the classical detector's
# recall is too low for the rule to mean anything there).
MIN_CENSUS_BALLS = 2
# Per-side spread above this means the detector's recall moved with the player,
# not with the table: the side cannot be compared with the other one.
MAX_CENSUS_SPREAD = 4


def normalize_color(value: Any) -> str:
    """Detector colour name -> census colour name (red/red2 are one colour)."""
    text = str(value or "").strip().lower()
    if not text:
        return UNKNOWN
    return COLOR_ALIASES.get(text, text)


def _num(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


# --------------------------------------------------------------- observations

@dataclass
class Observation:
    """One ball seen at one time by one detector."""
    t: float
    color: str
    cx: float
    cy: float
    r: float = 8.0
    source: str = "classical"
    score: float | None = None
    table_mm: tuple | None = None
    color_raw: str | None = None

    def __post_init__(self):
        if self.color_raw is None:
            self.color_raw = self.color
        self.color = normalize_color(self.color)
        self.t = float(self.t)

    @property
    def confidence(self) -> float:
        """How much this single measurement is worth, 0..1.

        Classical detections carry no score: a colour blob is a 0.5 observation.
        SAM3 carries a mask score, mapped from the threshold band (0.62 -> 0.24)
        to certainty (1.00 -> 1.00).
        """
        if self.source == "sam3" and self.score is not None:
            return round(min(1.0, max(0.0, (float(self.score) - 0.5) / 0.5)), 3)
        return 0.5

    def as_dict(self) -> dict:
        return {"t": round(self.t, 3), "color": self.color, "color_raw": self.color_raw,
                "cx": round(self.cx, 1), "cy": round(self.cy, 1), "r": round(self.r, 1),
                "source": self.source, "score": self.score,
                "confidence": self.confidence,
                "table_mm": [round(v, 1) for v in self.table_mm] if self.table_mm else None}


def observations_from_classical(t: float, cands: Iterable[dict]) -> list[Observation]:
    """Classical detector output at one time -> observations."""
    out = []
    for cand in cands:
        out.append(Observation(t=float(t), color=cand.get("color"), cx=float(cand["cx"]),
                               cy=float(cand["cy"]), r=float(cand.get("r") or 8.0),
                               source="classical"))
    return out


def observations_from_sam3(t: float, balls: Iterable[dict], scale: float = 1.0,
                           color_fn=None, use_stored_mm: bool = False) -> list[Observation]:
    """SAM3 frame entry -> observations.

    ``balls`` are the stored rows (``score``/``img``/``r``, optionally
    ``table_mm`` and ``color``); ``img`` is in full-frame pixels and is scaled to
    the census frame with ``scale`` (960/1280 for the 720p VOD).  SAM3 has no
    colour class, so ``color_fn(cx, cy, r) -> str`` -- supplied by the caller that
    has the frame -- assigns one; a colour stored in the cache is only a hint and
    is used when no caller can sample, so a better classifier never needs the
    frames re-measured.  Without either the ball is an ``unknown`` colour, which
    still counts, associates and refutes nothing.

    ``table_mm`` stored in the cache is *not* used by default: it was projected
    with the scan's own naive quad, which is 5-50 mm off against the reference
    calibration, and a caller that has the reference projects the pixels itself.
    ``use_stored_mm=True`` keeps the cached value for callers without one.
    """
    out = []
    for ball in balls:
        score = _num(ball.get("score"))
        if score is not None and score < SAM3_MIN_SCORE:
            continue
        img = ball.get("img") or [ball.get("cx"), ball.get("cy")]
        if not img or img[0] is None:
            continue
        cx, cy = float(img[0]) * scale, float(img[1]) * scale
        radius = float(ball.get("r") or 8.0) * scale
        color = UNKNOWN
        if color_fn is not None:
            # The caller's classifier wins over the cached hint: the cache may
            # predate a colour fix, and re-running SAM3 for a colour would be a
            # waste of the most expensive measurement in the pipeline.
            color = normalize_color(color_fn(cx, cy, max(radius * 0.5, 2.5)))
        else:
            color = normalize_color(ball.get("color"))
        stored = ball.get("table_mm") if use_stored_mm else None
        out.append(Observation(t=float(t), color=color, cx=cx, cy=cy, r=radius,
                               source="sam3", score=score,
                               table_mm=tuple(stored) if stored else None))
    return out


# --------------------------------------------------------------------- tracks

def classify_ball_color(bgr, cx: float, cy: float, r: float) -> str:
    """Colour of the ball at ``(cx, cy)``, using the classical detector's ranges.

    SAM3 segments balls but has no colour class.  Sampling the disc with the
    *same* ``BALL_COLORS`` ranges the classical detector uses keeps the two
    sources' colour names comparable, which is what association needs.  Returns
    ``unknown`` when no range covers enough of the disc.
    """
    import cv2
    import numpy as np

    from src.ball_detect import BALL_COLORS

    x0, x1 = int(max(0, cx - r)), int(min(bgr.shape[1], cx + r))
    y0, y1 = int(max(0, cy - r)), int(min(bgr.shape[0], cy + r))
    if x1 <= x0 or y1 <= y0:
        return UNKNOWN
    from_hsv = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    total = float(from_hsv.shape[0] * from_hsv.shape[1])
    votes = {}
    for name, (lo, hi) in BALL_COLORS.items():
        mask = cv2.inRange(from_hsv, lo, hi)
        votes[normalize_color(name)] = votes.get(normalize_color(name), 0) + int(mask.sum()) / 255.0
    if not votes:
        return UNKNOWN
    best = max(votes, key=lambda name: votes[name])
    if not votes[best] >= 0.25 * total:
        return UNKNOWN
    # A stripe ball is mostly white with a coloured band; without this it reads
    # as white, "white" stops meaning "the cue ball", and the colour is no
    # longer unique enough to measure a shot with.  The band decides.
    if best == "white":
        band = max((name for name in votes if name not in ("white", UNKNOWN)),
                   key=lambda name: votes[name], default=None)
        if band is not None and votes[band] >= 0.15 * total:
            return band
    return best


# --------------------------------------------------------------------- tracks

@dataclass
class Track:
    """A ball identity: >= 1 observation of one colour, in time order."""
    tid: int
    obs: list = field(default_factory=list)

    # -- identity --------------------------------------------------------
    def add(self, observation: Observation) -> None:
        self.obs.append(observation)
        self.obs.sort(key=lambda o: o.t)

    @property
    def hits(self) -> int:
        return len(self.obs)

    @property
    def stable(self) -> bool:
        """Seen in >= 2 frames: an identity, not a fresh detection."""
        return len(self.obs) >= 2

    @property
    def first_t(self) -> float:
        return self.obs[0].t

    @property
    def last_t(self) -> float:
        return self.obs[-1].t

    @property
    def color_votes(self) -> dict:
        votes: dict = {}
        for observation in self.obs:
            if observation.color == UNKNOWN:
                continue
            votes[observation.color] = votes.get(observation.color, 0) + 1
        return votes

    @property
    def color(self) -> str:
        """Majority colour over the identity's observations (ties: first seen)."""
        votes = self.color_votes
        if not votes:
            return UNKNOWN
        order = {observation.color: index for index, observation in enumerate(self.obs)}
        return max(votes, key=lambda name: (votes[name], -order.get(name, 0)))

    @property
    def conflicts(self) -> int:
        """Observations whose colour disagrees with the identity's colour."""
        color = self.color
        return sum(1 for observation in self.obs if observation.color not in (color, UNKNOWN))

    @property
    def sources(self) -> dict:
        out: dict = {}
        for observation in self.obs:
            out[observation.source] = out.get(observation.source, 0) + 1
        return out

    @property
    def confidence(self) -> float:
        """Mean measurement confidence plus a small bonus per extra sighting."""
        base = sum(o.confidence for o in self.obs) / len(self.obs)
        bonus = min(0.25, 0.1 * (self.hits - 1))
        return round(min(1.0, max(0.0, base + bonus - (0.15 if self.conflicts else 0.0))), 3)

    # -- geometry --------------------------------------------------------
    def position(self, t: float | None = None) -> tuple[float, float]:
        """Pixel position at ``t`` (default: the latest observation)."""
        nearest = self.obs[-1] if t is None else min(self.obs, key=lambda o: abs(o.t - t))
        return nearest.cx, nearest.cy

    def velocity(self) -> tuple[float, float]:
        """Pixels per second from the two latest observations (0, 0 if unknown)."""
        if len(self.obs) < 2:
            return 0.0, 0.0
        a, b = self.obs[-2], self.obs[-1]
        dt = b.t - a.t
        if dt <= 1e-6:
            return 0.0, 0.0
        return (b.cx - a.cx) / dt, (b.cy - a.cy) / dt

    def predict(self, t: float) -> tuple[float, float]:
        last = self.obs[-1]
        vx, vy = self.velocity()
        lead = min(MAX_PREDICT_S, max(0.0, t - last.t))
        return last.cx + vx * lead, last.cy + vy * lead

    def table_position(self) -> list | None:
        for observation in reversed(self.obs):
            if observation.table_mm:
                return [round(observation.table_mm[0], 1), round(observation.table_mm[1], 1)]
        return None

    def as_dict(self) -> dict:
        return {"tid": self.tid, "color": self.color, "hits": self.hits,
                "stable": self.stable, "first_t": round(self.first_t, 2),
                "last_t": round(self.last_t, 2), "confidence": self.confidence,
                "conflicts": self.conflicts, "sources": self.sources,
                "table_mm": self.table_position()}


def _color_compatible(track: Track, observation: Observation, distance: float) -> bool:
    """May this observation continue this identity?

    Same colour continues.  ``unknown`` on either side continues (SAM3 without a
    frame to sample has no colour).  A different colour is only absorbed while
    the identity is unestablished *and at the same spot*: that is detector
    flicker on a newly sighted ball (a stripe read as its solid colour), and the
    majority vote still reports the stable colour afterwards with the
    disagreement counted as a conflict.  Two racked balls 20 px apart are not
    that, so they stay two identities, and neither is the same ball read by two
    detectors: a colour disagreement *between sources* is two measurements, not
    one flicker.
    """
    color = track.color
    if color == UNKNOWN or observation.color == UNKNOWN:
        return True
    if color == observation.color:
        return True
    same_detector = bool(track.obs) and track.obs[-1].source == observation.source
    return track.hits < 2 and same_detector and distance <= COLOR_FLICKER_PX


def _bucket(t: float) -> float:
    return round(round(float(t) / TIME_BUCKET_S) * TIME_BUCKET_S, 3)


def associate(observations: Iterable[Observation], match_px: float = TRACK_MATCH_PX,
              gap_s: float = TRACK_GAP_S) -> tuple[list[Track], dict]:
    """Temporal association: observations -> stable identities.

    Observations are walked in time order, grouped into frames; each frame is
    matched to open identities by predicted position (colour-compatible, within
    ``match_px``), closest first.  Unmatched observations open a new identity.
    Returns ``(tracks, frames)`` where ``frames`` maps a bucketed time to the
    ``(observation, track)`` pairs seen at it.
    """
    items = sorted(observations, key=lambda o: (_bucket(o.t), o.source, o.color, o.cx))
    tracks: list[Track] = []
    frames: dict = {}
    used: dict = {}                      # (bucket, tid, source) already seen
    for observation in items:
        key = _bucket(observation.t)
        pairs = frames.setdefault(key, [])
        best = None
        for track in tracks:
            # A detector reports each ball once per frame, but the two
            # detectors reporting the same ball is the fusion's whole point:
            # they must land on one identity, not two.
            if (key, track.tid, observation.source) in used:
                continue
            if observation.t - track.last_t > gap_s:
                continue
            px, py = track.predict(observation.t)
            d = math.hypot(px - observation.cx, py - observation.cy)
            if d > match_px:
                continue
            if not _color_compatible(track, observation, d):
                continue
            if best is None or d < best[0]:
                best = (d, track)
        if best is None:
            track = Track(tid=len(tracks) + 1)
            tracks.append(track)
        else:
            track = best[1]
        track.add(observation)
        used[(key, track.tid, observation.source)] = True
        pairs.append((observation, track))
    return _stitch(tracks, frames)


def _stitch(tracks: list[Track], frames: dict) -> tuple[list[Track], dict]:
    """Re-join identities a brief occlusion split.

    A player crossing the cloth hides a ball for a second or two; it comes back
    where it was, and without this pass the census would report one ball
    vanishing and another appearing.  Two identities re-join when the later one
    starts in a *later frame* within ``STITCH_GAP_S`` and ``STITCH_PX`` of where
    the earlier one ended, in the same colour -- two balls visible in one frame
    are two balls, so a frame count is never touched by this pass.  A potted
    ball does not come back, so a vanish survives it.
    """
    merged = True
    while merged:
        merged = False
        for older in sorted(tracks, key=lambda track: track.last_t):
            if older not in tracks:
                continue
            for newer in sorted(tracks, key=lambda track: track.first_t):
                if newer is older or newer not in tracks or newer.tid == older.tid:
                    continue
                if newer.first_t - older.last_t < TIME_BUCKET_S:
                    continue      # same frame: two balls, not one returning
                if newer.first_t - older.last_t > STITCH_GAP_S:
                    continue
                if older.color != UNKNOWN and newer.color != UNKNOWN and older.color != newer.color:
                    continue
                px, py = older.obs[-1].cx, older.obs[-1].cy
                qx, qy = newer.obs[0].cx, newer.obs[0].cy
                if math.hypot(px - qx, py - qy) > STITCH_PX:
                    continue
                for observation in newer.obs:
                    older.add(observation)
                tracks.remove(newer)
                for key, pairs in frames.items():
                    frames[key] = [(o, older if t is newer else t) for o, t in pairs]
                merged = True
                break
            if merged:
                break
    return tracks, frames


# --------------------------------------------------------------- frame report

def build_census(observations: Iterable[Observation], table_mm_fn=None,
                 match_px: float = TRACK_MATCH_PX, gap_s: float = TRACK_GAP_S,
                 frame_times: Iterable[float] | None = None,
                 sam3_times: Iterable[float] | None = None) -> dict:
    """Fuse observations into a per-frame census plus the identity list.

    Returns ``{"version", "frames": [...], "tracks": [...]}``.  Every frame row
    carries ``count`` (distinct identities seen at that time, i.e. classical and
    SAM3 on the same ball counted once), the two source counts, how many of the
    balls were already stable identities, and the per-ball rows.
    ``table_mm_fn(cx, cy, t) -> [x, y] | None`` fills the millimetres, with the
    observation's own time so a per-segment reference quad is honoured.

    ``frame_times`` names frames that must appear even with no detections: an
    empty frame is a measurement of an empty cloth, and leaving it out would
    quietly raise every median computed over the window.
    """
    observations = list(observations)
    if table_mm_fn is not None:
        for observation in observations:
            if observation.table_mm is None:
                # The projector takes the observation's own time: the reference
                # quad can change per segment, and a millimetre measured against
                # another segment's quad is worse than no millimetre at all.
                mm = table_mm_fn(observation.cx, observation.cy, observation.t)
                observation.table_mm = tuple(mm) if mm else None
    tracks, frames = associate(observations, match_px=match_px, gap_s=gap_s)
    for t in frame_times or ():
        frames.setdefault(_bucket(t), [])
    # Which frames an SAM3 measurement exists for -- including the ones where it
    # saw nothing, which are measurements of an occluded cloth, not of an empty
    # table.  A frame the caller names is covered; a frame with SAM3 balls in it
    # is covered by definition.
    sam3_buckets = {_bucket(t) for t in (sam3_times or ())}
    rows = []
    for key in sorted(frames):
        pairs = frames[key]
        balls = []
        for observation, track in pairs:
            balls.append({"tid": track.tid, "color": track.color,
                          "color_source": observation.color, "source": observation.source,
                          "cx": round(observation.cx, 1), "cy": round(observation.cy, 1),
                          "r": round(observation.r, 1), "score": observation.score,
                          "hits": track.hits, "stable": track.stable,
                          "confidence": observation.confidence,
                          "table_mm": ([round(v, 1) for v in observation.table_mm]
                                       if observation.table_mm else None)})
        sam3_count = len({ball["tid"] for ball in balls if ball["source"] == "sam3"})
        classical_count = len({ball["tid"] for ball in balls if ball["source"] == "classical"})
        sam3_frame = _bucket(key) in sam3_buckets or sam3_count > 0
        rows.append({
            "t": key,
            # One detector per frame: a frame SAM3 measured is counted by SAM3.
            # Adding the colour blobs to an SAM3 frame counts shadows on top of
            # balls -- measured at t=27.2 s of the reference VOD that is 13 balls
            # on a 10-ball table -- and it makes frames incomparable again.
            "count": sam3_count if sam3_frame else classical_count,
            "classical_count": classical_count,
            "sam3_count": sam3_count,
            "stable_count": len({ball["tid"] for ball in balls
                                 if ball["stable"]
                                 and (ball["source"] == "sam3") == sam3_frame}),
            "fresh_count": len({ball["tid"] for ball in balls
                                if ball["hits"] == 1
                                and (ball["source"] == "sam3") == sam3_frame}),
            "sam3_frame": sam3_frame,
            "balls": balls,
        })
    return {"version": CENSUS_VERSION, "frames": rows,
            "tracks": [track.as_dict() for track in tracks],
            "observations": len(observations)}


def frames_in(report: dict, times: Iterable[float], tol: float = TIME_BUCKET_S) -> list[dict]:
    """Frame rows inside the time range ``times`` spans.

    A range, not a set of exact times: the SAM3 frames inside a window sit on
    their own timestamps (they were measured because the event needed them), and
    requiring them to land on the caller's sampling grid would silently drop the
    better detector from the very window it was paid for.
    """
    times = list(times)
    if not times:
        return []
    lo, hi = min(times) - tol, max(times) + tol
    return [row for row in report.get("frames", []) if lo <= row["t"] <= hi]


def _median(values: Iterable[float]) -> float | None:
    values = sorted(values)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return float(values[middle])
    return (float(values[middle - 1]) + float(values[middle])) / 2.0


def window_summary(report: dict, pre_times: Iterable[float], post_times: Iterable[float],
                   claim_color: str | None = None, mm_fn=None) -> dict:
    """Census before/after one event, plus the identities that vanished.

    Like-for-like only: when both windows carry SAM3 frames the summary counts
    SAM3 frames, otherwise it counts classical frames -- mixing a 10-ball SAM3
    side with a 2-ball classical side would manufacture a drop that no detector
    measured.  ``census_comparable`` is False when only one side has SAM3, and
    the caller must then treat the drop as unmeasured.

    On SAM3 sides a frame whose count falls below ``MIN_CENSUS_BALLS`` *and*
    below what its own side shows is reported in ``dropped_pre``/``dropped_post``
    and left out of the comparison: at t=26-28 s of the reference VOD a player
    stands at the table and SAM3 sees 0-4 of the 10 balls, which is a measurement
    of the occlusion, not of the table.  A side that is uniformly below the floor
    is a *low* side, not a broken one -- the late segment of the reference VOD
    holds 2 balls, and dropping those frames would throw away exactly the
    one-ball drop that ends a game -- so the side is kept and flagged
    ``low_census_pre``/``low_census_post``.  A side whose retained counts still
    swing by more than ``MAX_CENSUS_SPREAD`` is not stable either; both cases set
    ``census_stable`` False.  The classical numbers keep the formula they had
    before the fusion, so a window without SAM3 coverage behaves exactly as it
    did.

    ``mm_fn(cx, cy, t)`` projects a pixel position to table millimetres; without
    it the vanish rows carry pixels only.
    """
    pre_times, post_times = list(pre_times), list(post_times)
    pre_frames = frames_in(report, pre_times)
    post_frames = [row for row in frames_in(report, post_times + pre_times)
                   if row["t"] >= min(post_times) - TIME_BUCKET_S] if post_times else []
    sam3_pre = [row for row in pre_frames if row.get("sam3_frame")]
    sam3_post = [row for row in post_frames if row.get("sam3_frame")]
    low_pre = low_post = False
    if sam3_pre and sam3_post:
        source, pre_use, post_use = "sam3", sam3_pre, sam3_post
        floor = MIN_CENSUS_BALLS
        low_pre = max(row["count"] for row in pre_use) < floor
        low_post = max(row["count"] for row in post_use) < floor
        dropped_pre = [round(row["t"], 2) for row in pre_use
                       if row["count"] < floor and not low_pre]
        dropped_post = [round(row["t"], 2) for row in post_use
                        if row["count"] < floor and not low_post]
        pre_use = [row for row in pre_use if row["count"] >= floor or low_pre]
        post_use = [row for row in post_use if row["count"] >= floor or low_post]
    else:
        # No SAM3 on both sides: the classical numbers keep the formula they
        # had before the fusion, and SAM3-only frames stay out of them (their
        # classical count is zero and would drag the median down for no reason).
        source = "classical"
        pre_use = [row for row in pre_frames if not row.get("sam3_frame")]
        post_use = [row for row in post_frames if not row.get("sam3_frame")]
        dropped_pre, dropped_post = [], []
    counts_pre = [row["classical_count"] if source == "classical" else row["count"]
                  for row in pre_use]
    counts_post = [row["classical_count"] if source == "classical" else row["count"]
                   for row in post_use]
    census_pre = _median(counts_pre)
    census_post = _median(counts_post)
    summary = {
        "version": report.get("version"),
        "source": source,
        "census_comparable": bool(sam3_pre) == bool(sam3_post) or not (sam3_pre or sam3_post),
        "frames_pre": len(pre_use), "frames_post": len(post_use),
        "sam3_frames_pre": len(sam3_pre), "sam3_frames_post": len(sam3_post),
        "counts_pre": counts_pre, "counts_post": counts_post,
        "census_pre": census_pre, "census_post": census_post,
        "census_post_max": max(counts_post) if counts_post else None,
        "census_pre_min": min(counts_pre) if counts_pre else None,
        "spread_pre": (max(counts_pre) - min(counts_pre)) if counts_pre else None,
        "spread_post": (max(counts_post) - min(counts_post)) if counts_post else None,
        "stable_pre": _median([row["stable_count"] for row in pre_use]),
        "stable_post": _median([row["stable_count"] for row in post_use]),
        "dropped_pre": dropped_pre, "dropped_post": dropped_post,
        "low_census_pre": low_pre, "low_census_post": low_post,
        "census_stable": (source != "sam3" or (
            not dropped_pre and not dropped_post and counts_pre and counts_post
            and max(counts_pre) - min(counts_pre) <= MAX_CENSUS_SPREAD
            and max(counts_post) - min(counts_post) <= MAX_CENSUS_SPREAD)),
    }
    if census_pre is not None and census_post is not None:
        summary["census_drop"] = round(census_pre - census_post, 2)
    else:
        summary["census_drop"] = None

    # -- identity-level view: which ball is gone, not just how many --------
    pre_end = max(pre_times) if pre_times else None
    post_start = min(post_times) if post_times else None
    vanished, alive_pre, alive_post = [], 0, 0
    for track in _tracks_of(report):
        hits_pre = [o for o in track.obs if pre_end is None or o.t <= pre_end + TIME_BUCKET_S]
        hits_post = [o for o in track.obs if post_start is None or o.t >= post_start - TIME_BUCKET_S]
        if hits_pre:
            alive_pre += 1
        if hits_post:
            alive_post += 1
        if hits_pre and not hits_post and len(hits_pre) >= 2:
            # >= 2 sightings before it left: an identity, not a fresh blob, so a
            # split track cannot report a ball that never existed.
            last = hits_pre[-1]
            row = {"tid": track.tid, "color": track.color, "hits": len(hits_pre),
                   "total_hits": track.hits, "stable": track.stable,
                   "sources": _source_counts(hits_pre), "last_t": round(last.t, 2),
                   "confidence": track.confidence,
                   "cx": round(last.cx, 1), "cy": round(last.cy, 1), "table_mm": None,
                   "pocket": None, "dist_mm": None, "approach_mm": None}
            from src.event_gates import nearest_pocket
            mm = last.table_mm or (mm_fn(last.cx, last.cy, last.t) if mm_fn else None)
            if mm is not None:
                row["table_mm"] = [round(mm[0], 1), round(mm[1], 1)]
                pocket, distance = nearest_pocket(mm[0], mm[1])
                row["pocket"], row["dist_mm"] = pocket, round(distance)
                first = hits_pre[0]
                first_mm = first.table_mm or (mm_fn(first.cx, first.cy, first.t) if mm_fn else None)
                if first_mm is not None:
                    row["approach_mm"] = round(
                        nearest_pocket(first_mm[0], first_mm[1])[1] - distance, 1)
            vanished.append(row)
    summary["identities_pre"] = alive_pre
    summary["identities_post"] = alive_post
    summary["identity_drop"] = alive_pre - alive_post
    summary["vanished"] = sorted(vanished, key=lambda v: (v["dist_mm"] is None, v["dist_mm"]))
    if claim_color:
        presence = color_presence(report, claim_color, post_times)
        summary["claim_color"] = presence["color"]
        summary["claim_color_present"] = presence["present"]
        summary["claim_color_present_measured"] = presence["measured"]
        summary["claim_color_present_hits"] = presence["hits"]
        summary["claim_color_present_sources"] = presence["sources"]
        summary["claim_color_unique"] = presence["color"] in UNIQUE_COLORS
    return summary


def _tracks_of(report: dict) -> list[Track]:
    """Rebuild Track objects from a report's frame rows.

    Ids are not renumbered (a stitched identity keeps the id it was born with),
    so the view is built from the ids the frames carry.
    """
    tracks: dict = {}
    for row in report.get("frames", []):
        for ball in row["balls"]:
            track = tracks.get(ball["tid"])
            if track is None:
                track = Track(tid=ball["tid"])
                tracks[ball["tid"]] = track
            track.add(Observation(t=row["t"], color=ball["color_source"], cx=ball["cx"],
                                  cy=ball["cy"], r=ball["r"], source=ball["source"],
                                  score=ball["score"],
                                  table_mm=tuple(ball["table_mm"]) if ball["table_mm"] else None))
    return [tracks[tid] for tid in sorted(tracks)]


def displacement_measure(report: dict, anchor: float, claim_color: str | None = None,
                         margin_s: float = 0.3, min_disp_mm: float = 300.0,
                         still_mm: float = 60.0) -> dict:
    """The move a ball made across the event, from the SAM3 ball *set*.

    A ball a shot sends across the table cannot be followed by proximity -- it
    jumps, so its pre-event and post-event identities are two different tracks.
    What survives is the set: one ball left where it was and arrived somewhere
    else while the others stayed put.  Pairing the pre-event positions with the
    post-event positions nearest-first finds exactly that pair (everything else
    pairs at ~0 mm distance), and the distance of the unpaired pair is the shot.

    Only SAM3 observations are used: a scored mask is a position worth measuring,
    and the classical layer's duplicate blobs would add phantom positions that
    do not exist on the table.  Returns the best move (the claim's colour
    preferred when it is one of the two ends), the sightings behind each end and
    how many balls moved at all.
    """
    pre = _side_positions(report, anchor, margin_s, before=True)
    post = _side_positions(report, anchor, margin_s, before=False)
    if not pre or not post:
        return {"measured_colors": 0, "tracks_moved": 0, "moves": [], "best": None,
                "claim_color_measured": False, "color": None, "disp_mm": None,
                "start_px": None, "end_px": None, "start_hits": 0, "end_hits": 0,
                "start_mm": None, "end_mm": None, "still": None, "identities_pre": len(pre),
                "identities_post": len(post)}
    pairs = []
    for tid, before in pre.items():
        for other, after in post.items():
            distance = math.hypot(before["mm"][0] - after["mm"][0], before["mm"][1] - after["mm"][1])
            pairs.append((distance, tid, other))
    used_pre, used_post, matched = set(), set(), []
    for distance, tid, other in sorted(pairs, key=lambda item: item[0]):
        if tid in used_pre or other in used_post:
            continue
        used_pre.add(tid)
        used_post.add(other)
        matched.append({"dist_mm": round(distance), "start_tid": tid, "end_tid": other,
                        "start_mm": [round(v, 1) for v in pre[tid]["mm"]],
                        "end_mm": [round(v, 1) for v in post[other]["mm"]],
                        "start_px": pre[tid]["px"], "end_px": post[other]["px"],
                        "start_hits": pre[tid]["hits"], "end_hits": post[other]["hits"],
                        "start_color": pre[tid]["color"], "end_color": post[other]["color"]})
    wanted = normalize_color(claim_color) if claim_color else None
    moved = [move for move in matched if move["dist_mm"] >= min_disp_mm]
    claimed = [move for move in moved
               if wanted and wanted in (move["start_color"], move["end_color"])]
    best = max(claimed, key=lambda move: move["dist_mm"]) if claimed else (
        max(moved, key=lambda move: move["dist_mm"]) if moved else None)
    out = {"measured_colors": len(matched), "tracks_moved": len(moved), "moves": matched,
           "best": best, "claim_color_measured": bool(claimed),
           "still": sum(1 for move in matched if move["dist_mm"] <= still_mm),
           "identities_pre": len(pre), "identities_post": len(post)}
    if best is None:
        out.update({"color": None, "disp_mm": None, "start_px": None, "end_px": None,
                    "start_hits": 0, "end_hits": 0, "start_mm": None, "end_mm": None})
    else:
        out.update({"color": best["start_color"] if best["start_color"] != UNKNOWN
                    else best["end_color"], "disp_mm": best["dist_mm"],
                    "start_px": best["start_px"], "end_px": best["end_px"],
                    "start_hits": best["start_hits"], "end_hits": best["end_hits"],
                    "start_mm": best["start_mm"], "end_mm": best["end_mm"]})
    return out


def _side_positions(report: dict, anchor: float, margin_s: float, before: bool) -> dict:
    """One row per SAM3 identity on one side of the anchor: mm, px, sightings."""
    sides: dict = {}
    for row in report.get("frames", []):
        if before and row["t"] > anchor - margin_s:
            continue
        if not before and row["t"] < anchor + margin_s:
            continue
        for ball in row["balls"]:
            if ball["source"] != "sam3" or not ball.get("table_mm"):
                continue
            entry = sides.setdefault(ball["tid"], {"mm": [], "px": [], "hits": 0, "color": UNKNOWN})
            entry["mm"].append((float(ball["table_mm"][0]), float(ball["table_mm"][1])))
            entry["px"].append((ball["cx"], ball["cy"]))
            entry["hits"] += 1
            if entry["color"] == UNKNOWN and ball["color"] != UNKNOWN:
                entry["color"] = ball["color"]
    out = {}
    for tid, entry in sides.items():
        out[tid] = {"mm": (sum(x for x, _ in entry["mm"]) / len(entry["mm"]),
                           sum(y for _, y in entry["mm"]) / len(entry["mm"])),
                    "px": [round(sum(x for x, _ in entry["px"]) / len(entry["px"]), 1),
                           round(sum(y for _, y in entry["px"]) / len(entry["px"]), 1)],
                    "hits": entry["hits"], "color": entry["color"]}
    return out


def _source_counts(observations: Iterable[Observation]) -> dict:
    out: dict = {}
    for observation in observations:
        out[observation.source] = out.get(observation.source, 0) + 1
    return out


def color_presence(report: dict, color: str, times: Iterable[float]) -> dict:
    """Was the claimed colour measured on the cloth during ``times``?

    Presence is a measurement even from one sighting, but its *strength* is
    kept: an SAM3 sighting is a scored mask, the classical colour blob needs two
    sightings (or one on a stable identity) before it counts as one.  The pot
    gate reads ``present``/``measured``, and only a unique colour refutes.
    """
    color = normalize_color(color)
    window = {_bucket(t) for t in times}
    hits, sources, tids, seen = 0, {}, set(), set()
    for row in report.get("frames", []):
        if _bucket(row["t"]) not in window:
            continue
        for ball in row["balls"]:
            if ball["color"] != color:
                continue
            hits += 1
            sources[ball["source"]] = sources.get(ball["source"], 0) + 1
            tids.add(ball["tid"])
            seen.add(_bucket(row["t"]))
    # "Seen twice" means two frames: two detections in one frame are one sighting.
    strong = sources.get("sam3", 0) >= 1 or len(seen) >= 2
    return {"color": color, "present": hits > 0, "measured": strong,
            "hits": len(seen), "detections": hits, "sources": sources, "tids": sorted(tids)}
