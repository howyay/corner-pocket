"""Measure the shot/pot queue and decide each candidate with explicit gates.

Two jobs, one tool:

1. **Measurement** (default): for every candidate behind the served queue, report
   its geometry plus the corroborating signals that can be recovered from
   cached scan data and a bounded frame probe:
     * the cloth census per sampled frame, before/after the event;
     * the vanished ball's last measured position and its distance to a pocket;
     * the re-measured displacement of the same ball between sharp frames;
     * the claimed positions' containment in the cloth quad under a reference
       calibration (the *hand anchors*, which sit on the cloth; the scan's own
       naive quad is 55-120 px off on sampled frames and is not trusted).
   Then classify with ``src.event_gates`` (confirmed / rejected / unconfirmed)
   and aggregate, and report agreement with the verdicts the review UI recorded
   (read-only).

2. **Regeneration** (``--write-queue``): post-hoc filtering, no re-scan.  The
   scan candidate file is deduped, gated, and converted back to the queue
   schema with the measured numbers attached.  Existing queue ids are inherited
   so a verdict recorded against an id keeps pointing at the same act; human
   verdict files are only ever read.

Cost: a probe decodes only the frames around each candidate -- measured at
~0.4-1.1 s per candidate on this machine (41 candidates: 44 s) -- against 591 s
for the full info-complete scan.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.event_gates import (CANON_H, CANON_W, GateConfig, PotEvidence,  # noqa: E402
                             ShotEvidence, dedupe, judge, nearest_pocket,
                             normalize)
from src.ball_census import (CENSUS_VERSION, build_census, classify_ball_color,  # noqa: E402
                             displacement_measure, observations_from_classical,
                             observations_from_sam3, window_summary)
from src.ball_detect import detect_ball_candidates  # noqa: E402
from src.info_complete_scan import match_balls, to_table_mm  # noqa: E402
from src.sam3_ball_cache import APP_CACHE, OWN_CACHE, load_cache  # noqa: E402

SMALL_W, SMALL_H = 960, 540
MIN_BALL_AREA, MAX_BALL_AREA = 14.0, 9000.0
# The probe cache is keyed by (kind, t, colour) and carries this version: a
# measurement change must invalidate old payloads, or a stale cache would
# silently weaken the gates (missing fields default to "not measured").
CACHE_VERSION = 7
CENSUS_STEP_S = 0.25          # window sampling
POT_PRE_S, POT_POST_S = 1.5, 2.5
SHOT_INTERVALS_S = (0.3, 0.45, 0.6)   # sharp frames either side of the shot
SHOT_CENSUS_S = 2.0           # fused-census reach around a shot anchor
MATCH_PX = 40.0               # same ball between samples, 960x540 pixels
OBS_PX = 60.0                 # a ball re-sighted at the same spot, frame pixels
GEOMETRY_MARGIN_MM = 20.0     # a measured ball must be on the cloth
# SAM3 frames are stored in 1280x720 pixels; the census works in 960x540.
SAM3_SCALE = SMALL_W / 1280.0
HUMAN_VERDICT_FILES = ("out/scan30/annotations.json",
                       "out/ui-browser-fixture/out/scan30/annotations.json")


# ------------------------------------------------------------------- geometry

def load_segments(dataset="vod30"):
    """The per-segment reference quads, or None when the artifact is absent.

    Read-only: the segmentation is produced elsewhere (`src.calib_segments`); a
    missing or broken artifact leaves the tool on the single reference quad it
    has always used, and says so in the report.
    """
    try:
        from src.calib_segments import load
        return load(dataset)
    except Exception:
        return None


def load_quad(path, key="corners"):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if key == "anchors":
        anchors = data.get("anchors") or {}
        first = next(iter(anchors.values()), None)
        return np.array(first[:4], np.float32) if first else None
    corners = data.get(key)
    return np.array(corners, np.float32) if corners else None


def reference_calibration(anchors_path, quad_path):
    """(forward, inverse, label): frame pixels -> canonical mm, and back.

    The hand anchors are the reference: they were clicked on the cloth, the
    camera is static (the cloth centroid moves <0.2 px across 0-1800 s), and
    the scan's own naive quad is demonstrably off.  The scan quad is only a
    fallback so the tool still runs on a dataset without anchors.
    """
    from src.pipeline import homography_to_canonical

    quad = load_quad(anchors_path, "anchors")
    label = "hand anchors on the cloth"
    if quad is None:
        quad = load_quad(quad_path)
        label = "scan quad (fallback, known biased)"
    if quad is None:
        return None, None, "none: no calibration available"
    try:
        forward = homography_to_canonical(quad)
        return forward, np.linalg.inv(forward), label
    except Exception:
        return None, None, "none: calibration unusable"


class SAM3Store:
    """Ball positions SAM3 measured on named frames (app cache + this round's).

    Both files are read; the app's ``sam3_results.json`` is never written.
    Positions are full-frame pixels and are scaled to the census frame when they
    are turned into observations.
    """

    def __init__(self, paths=(APP_CACHE, OWN_CACHE)):
        self.frames = {}
        self.paths = []
        for path in paths:
            loaded = load_cache(path)
            if loaded:
                self.paths.append(str(path))
            self.frames.update(loaded)

    def within(self, lo: float, hi: float, tol: float = 0.03) -> list:
        """[(t, balls)] for the cached frames inside ``[lo, hi]``, in time order."""
        return sorted((t, balls) for t, balls in self.frames.items()
                      if lo - tol <= t <= hi + tol)

    def __len__(self):
        return len(self.frames)


class Probe:
    """Bounded frame probe: decodes only around the candidates, never the VOD."""

    def __init__(self, video, forward, inverse, quad, sam3=None, segments=None):
        self.video = Path(video)
        self.forward, self.inverse = forward, inverse
        self.quad = quad
        self.segments = segments
        self.sam3 = sam3 if sam3 is not None else SAM3Store()
        self.cap = None
        self.fps = 30.0
        self.cloth = None
        self.frames = 0
        self.seconds = 0.0
        self.sam3_frames_decoded = 0
        self._frame_cache = {}
        self._segment_cache = {}

    def open(self):
        self.cap = cv2.VideoCapture(str(self.video))
        if not self.cap.isOpened():
            self.cap = None
            return False
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        small_quad = (self.quad * (SMALL_W / 1280.0)).astype(np.float32)
        self.cloth = np.zeros((SMALL_H, SMALL_W), np.uint8)
        cv2.fillPoly(self.cloth, [np.round(small_quad).astype(np.int32)], 1)
        return True

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    # -- decode ----------------------------------------------------------
    def _read_seek(self, time_s):
        self.cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, time_s) * 1000.0)
        ok, frame = self.cap.read()
        if not ok:
            return None
        self.frames += 1
        return cv2.resize(frame, (SMALL_W, SMALL_H))

    def sample(self, times):
        """[(t, cands, gray)] at the requested times, in order."""
        started = time.time()
        out = []
        for t in times:
            small = self._read_seek(t)
            if small is None:
                continue
            cands = detect_ball_candidates(small, self.cloth, MIN_BALL_AREA, MAX_BALL_AREA)
            out.append((float(t), cands, cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)))
        self.seconds += time.time() - started
        return out

    # -- fused census ----------------------------------------------------
    def color_at(self, t, cx, cy, r):
        """Colour of a stored SAM3 ball, sampled from the frame at ``t``.

        SAM3 segments balls but has no colour class; the frame is decoded once
        per timestamp and cached, because the app's own cache predates colour
        sampling.
        """
        key = round(float(t), 3)
        frame = self._frame_cache.get(key)
        if frame is None:
            if len(self._frame_cache) > 400:
                self._frame_cache.clear()
            started = time.time()
            frame = self._read_seek(t)
            self.seconds += time.time() - started
            self._frame_cache[key] = frame
            self.sam3_frames_decoded += 1
        if frame is None:
            return "unknown"
        return classify_ball_color(frame, cx, cy, r)

    def census(self, samples, times):
        """Fused census over the sampled frames and the SAM3 frames in range.

        ``samples`` comes from :meth:`sample`; ``times`` are the times the
        caller asked for, so only SAM3 frames inside this window join it.  The
        report is ``src.ball_census.build_census``: one row per frame with the
        fused count, the two source counts and the per-ball identity.
        """
        if not samples or not times:
            return {"version": CENSUS_VERSION, "frames": [], "tracks": [], "observations": 0}
        lo, hi = min(times), max(times)
        observations = []
        for t, cands, _ in samples:
            observations += observations_from_classical(t, cands)
        sam3_frames = self.sam3.within(lo, hi)
        for t, balls in sam3_frames:
            observations += observations_from_sam3(
                t, balls, scale=SAM3_SCALE,
                color_fn=lambda cx, cy, r, at=t: self.color_at(at, cx, cy, r))
        # A frame with no detections at all is still a frame: it is a measurement
        # of an empty cloth, and dropping it would raise every median.
        report = build_census(observations, table_mm_fn=self.mm,
                              frame_times=list(times) + [t for t, _ in sam3_frames],
                              sam3_times=[t for t, _ in sam3_frames])
        report["sam3_frames"] = [round(t, 2) for t, _ in sam3_frames]
        report["classical_frames"] = [round(t, 2) for t, _, _ in samples]
        return report

    # -- geometry helpers ------------------------------------------------
    def homographies(self, t=None):
        """``(forward, inverse, segment)`` for that time's calibration segment.

        The reference quad can differ per segment (the VOD re-frames), so every
        millimetre this probe reports is measured against the segment the event
        is in.  Without a segment artifact the single reference quad is used.
        """
        if self.segments is None or t is None:
            return self.forward, self.inverse, None
        key = round(float(t), 1)
        if key not in self._segment_cache:
            forward, inverse, segment = self.segments.homographies(t)
            self._segment_cache[key] = (self.forward if forward is None else forward,
                                        self.inverse if inverse is None else inverse,
                                        segment)
        return self._segment_cache[key]

    def quad_for(self, t=None):
        _, _, segment = self.homographies(t)
        return self.quad if segment is None else segment.quad

    def mm(self, cx, cy, t=None):
        forward, _, _ = self.homographies(t)
        return to_table_mm(forward, cx * 1280.0 / SMALL_W, cy * 720.0 / SMALL_H)

    def px(self, mm, t=None):
        _, inverse, _ = self.homographies(t)
        if inverse is None or not mm:
            return None
        x, y, w = inverse @ np.array([float(mm[0]), float(mm[1]), 1.0])
        if not math.isfinite(w) or abs(w) < 1e-9:
            return None
        return [round(float(x) / float(w), 1), round(float(y) / float(w), 1)]

    def in_cloth(self, px, t=None):
        quad = self.quad_for(t)
        if px is None or quad is None:
            return None
        return float(cv2.pointPolygonTest(quad.astype(np.float32),
                                          (float(px[0]), float(px[1])), True))

    def cloth_fraction(self, t):
        """Share of the reference quad that is cloth-hued at ``t``.

        1.0 when the quad really sits on the playing surface; below the gate
        threshold the frame's framing differs from the calibrated segment, so
        every millimetre-derived number for this event is unusable.
        """
        from src.table_detect import detect_cloth_mask
        small = self._read_seek(t)
        if small is None or self.cloth is None:
            return None
        mask = detect_cloth_mask(small)
        total = int((self.cloth > 0).sum())
        return round(float(((mask > 0) & (self.cloth > 0)).sum()) / max(1, total), 3)


# -------------------------------------------------------------------- probes

def _motion(a_gray, b_gray, cloth):
    diff = np.abs(a_gray.astype(np.int16) - b_gray.astype(np.int16))
    return float(diff[cloth > 0].mean())


def _on_cloth(mm):
    return mm is not None and (-GEOMETRY_MARGIN_MM <= mm[0] <= CANON_W + GEOMETRY_MARGIN_MM
                               and -GEOMETRY_MARGIN_MM <= mm[1] <= CANON_H + GEOMETRY_MARGIN_MM)


def _sightings(samples, color, px, exclude=()):
    """How many probe samples show a same-colour ball at ``px`` (pixels, 720p)."""
    if not color or px is None:
        return 0
    count = 0
    for t, cands, _ in samples:
        if t in exclude:
            continue
        for ball in cands:
            if ball.get("color") != color:
                continue
            spot = (ball["cx"] * 1280.0 / SMALL_W, ball["cy"] * 720.0 / SMALL_H)
            if math.hypot(spot[0] - px[0], spot[1] - px[1]) <= OBS_PX:
                count += 1
                break
    return count


def _sighted(samples, color, px, exclude=()):
    return _sightings(samples, color, px, exclude) >= 1


def probe_shot(claim, probe):
    """Sharp-frame displacement + window motion for one shot claim.

    The scan brackets a shot with two frames 0.07 s apart, where a fast ball is
    motion-blurred and the classical detector cannot see it.  This probe instead
    compares *sharp* frames 0.6-2.4 s apart: the ball is seen at rest before the
    shot and again after it.  A matched pair only counts as a shot when the ball
    was also sighted at the start position in another before-sample and at the
    destination in another after-sample -- a single sighting is how the scan
    paired two different balls.
    """
    offsets = [o for dt in SHOT_INTERVALS_S for o in (-dt, dt)] + [-0.9, -1.2, 0.9, 1.2]
    anchor = _anchor(claim)
    # Measure around three anchors 0.1 s apart: the detector's recall moves frame
    # to frame, so a corroboration that shows up at one anchor only is not one.
    anchors = [round(anchor + delta, 1) for delta in (-0.1, 0.0, 0.1)]
    times = sorted({round(a + off, 3) for a in anchors for off in offsets if a + off >= 0})
    samples = probe.sample(times)
    if not samples:
        return ShotEvidence(available=False, note="no probe frames")
    evidence = ShotEvidence(available=True, anchor_tries=len(anchors), stable_hits=0)
    evidence.calibration_frac = probe.cloth_fraction(anchor)
    claimed_color = claim["color"]
    per_anchor, best_claimed, best_any = [], None, None
    for a in anchors:
        anchor_best = None
        for dt in SHOT_INTERVALS_S:
            pair = [s for s in samples if abs(abs(s[0] - a) - dt) < 1e-6]
            if len(pair) != 2:
                continue
            (before_t, before, _), (after_t, after, _) = pair
            radius = 3.0 * max([c["r"] for c in before + after] or [10.0])
            matched, _, _ = match_balls(before, after, radius)
            for prev, cur, _ in matched:
                a_mm, b_mm = probe.mm(prev["cx"], prev["cy"], a), probe.mm(cur["cx"], cur["cy"], a)
                if not _on_cloth(a_mm) or not _on_cloth(b_mm):
                    continue
                start_px = [round(prev["cx"] * 1280.0 / SMALL_W, 1), round(prev["cy"] * 720.0 / SMALL_H, 1)]
                end_px = [round(cur["cx"] * 1280.0 / SMALL_W, 1), round(cur["cy"] * 720.0 / SMALL_H, 1)]
                if not _sighted(samples, prev.get("color"), start_px, exclude=(before_t, after_t)):
                    continue
                if not _sighted(samples, cur.get("color"), end_px, exclude=(before_t, after_t)):
                    continue
                disp = math.hypot(a_mm[0] - b_mm[0], a_mm[1] - b_mm[1])
                record = (disp, prev.get("color"), start_px, end_px,
                          _sightings(samples, prev.get("color"), start_px),
                          _sightings(samples, cur.get("color"), end_px))
                if anchor_best is None or disp > anchor_best[0]:
                    anchor_best = record
                if claimed_color and claimed_color in (prev.get("color"), cur.get("color")):
                    if best_claimed is None or disp > best_claimed[0]:
                        best_claimed = record
                if best_any is None or disp > best_any[0]:
                    best_any = record
        if anchor_best is not None and anchor_best[0] >= GateConfig().shot_min_disp_mm:
            per_anchor.append(anchor_best)
    evidence.stable_hits = len(per_anchor)
    chosen = best_claimed or best_any
    if chosen is not None:
        evidence.disp_mm = round(chosen[0])
        evidence.disp_color = chosen[1]
        evidence.start_px = chosen[2]
        evidence.start_hits = chosen[4]
        evidence.end_hits = chosen[5]
        claimed_px = probe.px(claim["from_mm"], anchor)
        if claimed_px is not None:
            evidence.geometry_gap_px = round(math.hypot(claimed_px[0] - chosen[2][0],
                                                        claimed_px[1] - chosen[2][1]), 1)
    evidence.from_in_cloth_px = probe.in_cloth(probe.px(claim["from_mm"], anchor), anchor)
    evidence.to_in_cloth_px = probe.in_cloth(probe.px(claim["to_mm"], anchor), anchor)
    # The fused census measures the same event by other means: SAM3 sees the
    # balls the colour blobs lose to motion blur, and the temporal association
    # keeps them apart, so a fast ball is measurable again.
    census = probe.census(samples, [anchor - SHOT_CENSUS_S, anchor + SHOT_CENSUS_S])
    move = displacement_measure(census, anchor, claim_color=claimed_color,
                                min_disp_mm=GateConfig().shot_min_disp_mm)
    evidence.census_version = CENSUS_VERSION
    evidence.census_frames = len(census["frames"])
    evidence.census_sam3_frames = len(census.get("sam3_frames", []))
    evidence.census_source = "sam3" if evidence.census_sam3_frames else "classical"
    evidence.census_disp_mm = move["disp_mm"]
    evidence.census_disp_color = move["color"]
    evidence.census_start_hits = move["start_hits"]
    evidence.census_end_hits = move["end_hits"]
    evidence.census_tracks_moved = move["tracks_moved"]
    claimed_px = probe.px(claim["from_mm"], anchor)
    if move["start_px"] is not None and claimed_px is not None:
        start_px = [move["start_px"][0] * 1280.0 / SMALL_W, move["start_px"][1] * 720.0 / SMALL_H]
        evidence.census_geometry_gap_px = round(math.hypot(claimed_px[0] - start_px[0],
                                                           claimed_px[1] - start_px[1]), 1)
    window = probe.sample([t for t in (anchor + off for off in (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0))
                           if t >= 0])
    motions = [_motion(window[i][2], window[i + 1][2], probe.cloth) for i in range(len(window) - 1)]
    evidence.window_motion = round(max(motions), 2) if motions else None
    return evidence


def probe_pot(claim, probe):
    """Census before/after plus the measured vanished ball for one pot claim.

    The census is the fused one (classical + SAM3 + temporal association), so a
    single ball leaving the cloth is measurable; the vanished ball is an
    *identity* with a sighting history rather than one frame's blob, and its
    distance to the pocket is measured from the identity's own last position.
    """
    anchor = _anchor(claim)
    times = sorted({round(anchor + offset, 3) for offset in
                    np.arange(-POT_PRE_S, POT_POST_S + 1e-6, CENSUS_STEP_S) if anchor + offset >= 0})
    samples = probe.sample(times)
    if not samples:
        return PotEvidence(available=False, note="no probe frames")
    pre_times = [t for t in times if t <= anchor - CENSUS_STEP_S + 1e-6]
    post_times = [t for t in times if t >= anchor + 3 * CENSUS_STEP_S - 1e-6]
    if not pre_times or not post_times:
        return PotEvidence(available=False, note="window too short for a census")
    census = probe.census(samples, times)
    summary = window_summary(census, pre_times, post_times, claim_color=claim["color"],
                             mm_fn=probe.mm)
    evidence = PotEvidence(available=True, census_version=CENSUS_VERSION,
                           census_source=summary["source"],
                           census_comparable=summary["census_comparable"],
                           census_counts_pre=summary["counts_pre"],
                           census_counts_post=summary["counts_post"],
                           census_spread_pre=summary["spread_pre"],
                           census_spread_post=summary["spread_post"],
                           census_low_pre=summary.get("low_census_pre"),
                           census_low_post=summary.get("low_census_post"),
                           sam3_frames_pre=summary["sam3_frames_pre"],
                           sam3_frames_post=summary["sam3_frames_post"],
                           stable_pre=summary["stable_pre"], stable_post=summary["stable_post"],
                           identity_drop=summary["identity_drop"],
                           claim_color=summary.get("claim_color"),
                           claim_color_present=summary.get("claim_color_present"),
                           claim_color_present_measured=summary.get("claim_color_present_measured"),
                           claim_color_present_hits=summary.get("claim_color_present_hits"),
                           claim_color_present_sources=summary.get("claim_color_present_sources"),
                           claim_color_unique=summary.get("claim_color_unique"))
    if summary["census_pre"] is not None and summary["census_post"] is not None:
        evidence.census_pre = summary["census_pre"]
        evidence.census_post = summary["census_post"]
        evidence.census_post_max = summary["census_post_max"]
    else:
        # No usable fused frames: keep the pre-fusion formula and say so.
        pre = [s for s in samples if s[0] <= anchor - CENSUS_STEP_S + 1e-6]
        post = [s for s in samples if s[0] >= anchor + 3 * CENSUS_STEP_S - 1e-6]
        evidence.census_pre = float(np.median([len(s[1]) for s in pre])) if pre else None
        evidence.census_post = float(np.median([len(s[1]) for s in post])) if post else None
        evidence.census_post_max = float(max(len(s[1]) for s in post)) if post else None
        evidence.census_counts_pre = [len(s[1]) for s in pre]
        evidence.census_counts_post = [len(s[1]) for s in post]
        evidence.census_source = "classical"
    if claim["color"]:
        evidence.color_census_pre = float(np.median([sum(1 for b in s[1] if b.get("color") == claim["color"])
                                                     for s in samples if s[0] in pre_times] or [0]))
        evidence.color_census_post = float(np.median([sum(1 for b in s[1] if b.get("color") == claim["color"])
                                                      for s in samples if s[0] in post_times] or [0]))
    motions = [_motion(samples[i][2], samples[i + 1][2], probe.cloth) for i in range(len(samples) - 1)]
    evidence.motion_max = round(max(motions), 2) if motions else None
    evidence.calibration_frac = probe.cloth_fraction(anchor)
    # The clicked vanish candidates stay: they are the position-level view, and
    # the identity rows below are the same measurement with a sighting history.
    vanish = list(_classical_vanish(samples, probe, anchor))
    vanished_tids = {row.get("tid") for row in vanish if row.get("tid")}
    for row in summary["vanished"]:
        if row.get("tid") in vanished_tids:
            continue
        vanish.append({"color": row["color"], "mm": row["table_mm"], "pocket": row["pocket"],
                       "dist_mm": row["dist_mm"], "pre_hits": row["hits"],
                       "approach_mm": row["approach_mm"], "tid": row["tid"],
                       "hits": row["hits"], "total_hits": row["total_hits"],
                       "stable": row["stable"], "sources": row["sources"],
                       "confidence": row["confidence"], "last_t": row["last_t"],
                       "last_px": [row["cx"], row["cy"]]})
    evidence.vanish = _consolidate([row for row in vanish if row.get("mm")])
    return evidence


def _classical_vanish(samples, probe, anchor):
    """Position-level vanish candidates from the classical samples (pre-fusion).

    Kept as the fallback: without SAM3 coverage this is the only measurement,
    and with it the rows still show where the colour blobs last saw the ball.
    """
    pre = [s for s in samples if s[0] <= anchor - CENSUS_STEP_S + 1e-6]
    post = [s for s in samples if s[0] >= anchor + 3 * CENSUS_STEP_S - 1e-6]
    pre_cands = [(s[0], c) for s in pre for c in s[1]]
    post_cands = [c for s in post for c in s[1]]
    vanish = []
    for seen_t, ball in pre_cands:
        if any(other.get("color") == ball.get("color")
               and math.hypot(other["cx"] - ball["cx"], other["cy"] - ball["cy"]) <= MATCH_PX
               for other in post_cands):
            continue                      # still on the cloth: not a pot
        hits = [b for _, b in pre_cands if b.get("color") == ball.get("color")
                and math.hypot(b["cx"] - ball["cx"], b["cy"] - ball["cy"]) <= MATCH_PX]
        mm = probe.mm(ball["cx"], ball["cy"], seen_t)
        if not _on_cloth(mm):
            continue
        pocket, distance = nearest_pocket(mm[0], mm[1])
        trajectory = []
        for t, other in pre_cands:
            if other.get("color") != ball.get("color"):
                continue
            if math.hypot(other["cx"] - ball["cx"], other["cy"] - ball["cy"]) > 3 * MATCH_PX:
                continue
            spot = probe.mm(other["cx"], other["cy"], t)
            if spot is not None:
                trajectory.append((t, spot))
        approach = None
        if len(trajectory) >= 2:
            trajectory.sort(key=lambda item: item[0])
            approach = round(nearest_pocket(*trajectory[0][1])[1]
                             - nearest_pocket(*trajectory[-1][1])[1], 1)
        vanish.append({"color": ball.get("color"), "mm": [round(mm[0]), round(mm[1])],
                       "pocket": pocket, "dist_mm": round(distance), "pre_hits": len(hits),
                       "approach_mm": approach, "tid": None, "hits": len(hits),
                       "stable": len(hits) >= 2, "sources": {"classical": len(hits)},
                       "confidence": None, "last_t": None})
    return vanish


def _consolidate(vanish):
    """One row per vanished ball: near-duplicate rows collapse, identity wins.

    Two measurements can describe the same vanished ball: a position-level row
    (colour blobs) and an identity row (the fused census, with a sighting
    history and a better position).  The identity row replaces the blob row for
    the same ball; hit counts and source mixes merge, so nothing measured is
    dropped.
    """
    kept = []
    for item in sorted(vanish, key=lambda v: ((v.get("dist_mm") is None), v.get("dist_mm") or 0.0)):
        same = next((k for k in kept if k["color"] == item["color"]
                     and k["mm"] and item["mm"]
                     and math.hypot(k["mm"][0] - item["mm"][0], k["mm"][1] - item["mm"][1])
                     <= GateConfig().dedup_position_mm), None)
        if same is None:
            kept.append(dict(item))
            continue
        same["pre_hits"] = max(same.get("pre_hits") or 0, item.get("pre_hits") or 0)
        same["hits"] = max(same.get("hits") or 0, item.get("hits") or 0)
        same["stable"] = bool(same.get("stable") or item.get("stable"))
        sources = dict(same.get("sources") or {})
        for name, count in (item.get("sources") or {}).items():
            sources[name] = max(sources.get(name, 0), count)
        same["sources"] = sources
        for key in ("tid", "approach_mm", "confidence", "last_t", "total_hits"):
            if same.get(key) is None and item.get(key) is not None:
                same[key] = item[key]
    return kept


# ------------------------------------------------------------------ measuring

def _key(claim):
    """Cache identity: the 0.1 s the queue stores, so raw and served agree."""
    return f"{claim['kind']}:{round(claim['t'] or 0.0, 1)}:{claim['color']}"


def _anchor(claim):
    """Quantized event time: a 40 ms difference must not change a verdict."""
    return round(float(claim["t"] or 0.0), 1)


def _evidence(kind, payload):
    fields = ShotEvidence if kind == "shot" else PotEvidence
    return fields(**{k: v for k, v in payload.items() if k in fields.__dataclass_fields__})


def measure(candidates_path, probe, cfg, limit=None, cache_path=None, use_cache=True):
    """Dedupe the candidates and judge each group; returns (rows, seconds)."""
    raw = json.loads(Path(candidates_path).read_text()) if candidates_path else []
    if limit:
        raw = raw[:limit]
    groups = dedupe(raw, cfg)
    cached = {}
    if use_cache and cache_path and Path(cache_path).exists():
        stored = json.loads(Path(cache_path).read_text())
        if isinstance(stored, dict) and stored.get("version") == CACHE_VERSION:
            cached = stored.get("payloads", {})
    fresh = {}
    started = time.time()
    for group in groups:
        claim = group["event"]
        key = _key(claim)
        if key in cached:
            payload = cached[key]
        elif probe is not None and claim["kind"] == "shot" and not (claim["from_mm"] and claim["to_mm"]):
            payload = asdict(ShotEvidence(available=False, note="claim carries no bracketing geometry"))
        elif probe is not None:
            payload = asdict(probe_shot(claim, probe) if claim["kind"] == "shot" else probe_pot(claim, probe))
            fresh[key] = payload
        else:
            fields = ShotEvidence if claim["kind"] == "shot" else PotEvidence
            payload = asdict(fields(available=False, note="no video probe available"))
        group["evidence"] = payload
        group["verdict"] = judge(claim, _evidence(claim["kind"], payload), cfg).as_dict()
    if fresh and cache_path:
        merged = dict(cached)
        merged.update(fresh)
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(json.dumps({"version": CACHE_VERSION, "payloads": merged}, indent=1))
    return groups, round(time.time() - started, 1)


def queue_id_map(*queue_paths):
    """kind + rounded time -> id, so regenerated events keep the owner's ids.

    The pre-gate backup and the browser fixture are read too: once the queue is
    regenerated its original ids only survive there, and an owner verdict
    recorded against an id must keep matching the same act.
    """
    mapping = {}
    for queue_path in queue_paths:
        try:
            events = json.loads(Path(queue_path).read_text())
        except (OSError, ValueError, TypeError):
            continue
        for event in events:
            claim = normalize(event)
            if claim["t"] is not None and claim["id"] is not None:
                mapping.setdefault((claim["kind"], round(claim["t"], 1)), claim["id"])
    return mapping


def to_queue_event(group, previous_ids):
    """Queue-schema event for a group; stored fields stay untouched."""
    claim = group["event"]
    raw = dict(claim["raw"])
    event_id = claim["id"]
    if event_id is None:
        event_id = previous_ids.get((claim["kind"], round(claim["t"] or 0.0, 1)))
    event = {
        "id": event_id,
        "t": round(claim["t"], 1),
        "type": claim["kind"],
        "verified": bool(raw.get("verified", False)),
        "source": raw.get("source") or "info-complete",
        "window_s": raw.get("window_s") or [round(claim["t"] - 1.0, 1), round(claim["t"] + 3.0, 1)],
    }
    for key in ("disp_mm", "speed_mm_s", "from_mm", "to_mm", "last_mm", "gap_s", "color",
                "origin"):
        if key in raw:
            event[key] = raw[key]
    if claim["kind"] == "shot":
        event.setdefault("speed_m_s", round((raw.get("speed_mm_s") or 0) / 1000.0, 1))
        event["ball_from"] = raw.get("from_mm")
        event["ball_to"] = raw.get("to_mm")
    elif claim["last_mm"]:
        pocket, distance = nearest_pocket(float(claim["last_mm"][0]), float(claim["last_mm"][1]))
        event.setdefault("nearest_pocket", f"{pocket} ({round(distance)}mm)")
    event["dup_count"] = group["count"]
    event["gate"] = {**group["verdict"], "dup_count": group["count"],
                     "colors_merged": group["colors"]}
    # Additive, read by the review rail: the tier the event was confirmed at
    # ("geometry" = the measured motion matches the claim's geometry, "window" =
    # a ball moved but not the one or where the claim said), and whether the
    # claim's own geometry survived the re-measurement.  Nothing is rewritten --
    # the stored from_mm/to_mm stay exactly as the scan wrote them.
    numbers = event["gate"].get("numbers") or {}
    event["tier"] = event["gate"].get("tier")
    if claim["kind"] == "shot":
        gap = numbers.get("geometry_gap_px")
        tolerance = GateConfig().shot_geometry_tol_px
        event["geometry_check"] = {
            "claim_start_mm": raw.get("from_mm"), "claim_end_mm": raw.get("to_mm"),
            "measured_disp_mm": numbers.get("disp_mm"),
            "measured_disp_color": numbers.get("disp_color"),
            "gap_px": gap, "tol_px": tolerance,
            "matches": None if gap is None else bool(gap <= tolerance),
            "calibration_frac": numbers.get("calibration_frac"),
        }
    return event


def owner_verdicts(paths):
    """Read-only view of the verdicts the review UI recorded (never written)."""
    found = {}
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except ValueError:
            continue
        for key, record in data.items():
            if isinstance(record, dict) and record.get("verdict"):
                found.setdefault(key, {"verdict": record["verdict"], "note": record.get("note"),
                                       "updated_at": record.get("updated_at"), "file": str(path)})
    return found


def agreement(rows, verdicts):
    """Automated status against each recorded verdict; owner truth stays labelled.

    ``rows`` carries every measured candidate (not just the kept queue), so a
    verdict on an event the gates rejected still counts in the comparison.
    """
    by_id = {str(row["id"]): row for row in rows}
    out = []
    for event_id, record in sorted(verdicts.items(), key=lambda kv: float(kv[0])):
        gate = (by_id.get(str(event_id)) or {}).get("verdict", {})
        status = gate.get("status", "not-in-queue")
        verdict = record["verdict"]
        # "unsure" is not a claim about the event, so it stays out of the
        # agreement ratio; it is reported separately instead.
        agrees = {"wrong": status == "rejected", "correct": status == "confirmed",
                  "unsure": None}.get(verdict)
        out.append({"id": event_id, "owner_verdict": verdict, "gate_status": status,
                    "gate_reasons": gate.get("reasons", []), "agrees": agrees,
                    "note": record.get("note"), "file": record.get("file")})
    comparable = [r for r in out if r["agrees"] is not None]
    return {"rows": out, "reported": len(out),
            "agreement": sum(1 for r in comparable if r["agrees"]), "comparable": len(comparable),
            "unsure_rejected_by_gates": sum(1 for r in out
                                            if r["owner_verdict"] == "unsure" and r["gate_status"] == "rejected"),
            "source": "verdicts recorded by the review UI; this tool only reads them",
            "caveat": "the recorded sample lives in the browser fixture (audit probes), "
                      "not in out/scan30/annotations.json"}


def summarize(rows):
    counts = {"confirmed": 0, "rejected": 0, "unconfirmed": 0}
    reasons, krites = {}, {}
    duplicates = 0
    for row in rows:
        status = row["verdict"]["status"]
        counts[status] += 1
        duplicates += row["dup_count"] - 1
        for reason in row["verdict"]["reasons"]:
            reasons[reason] = reasons.get(reason, 0) + 1
        kind = row["kind"]
        krites.setdefault(kind, {"total": 0, "confirmed": 0, "rejected": 0, "unconfirmed": 0})
        krites[kind]["total"] += 1
        krites[kind][status] += 1
    confirmed = counts["confirmed"]
    geometry_tier = sum(1 for row in rows if row["verdict"]["status"] == "confirmed"
                        and row["verdict"].get("tier") == "geometry")
    return {"total_candidates": len(rows), "shots": krites.get("shot", {}).get("total", 0),
            "pots": krites.get("pot", {}).get("total", 0),
            "duplicates_collapsed": duplicates, "confirmed": confirmed,
            "rejected": counts["rejected"], "unconfirmed": counts["unconfirmed"],
            "no_corroboration": counts["unconfirmed"],
            "confirmed_with_geometry_evidence": geometry_tier,
            "gate_precision_estimate": (round(geometry_tier / confirmed, 2) if confirmed else None),
            "precision_note": "gate strictness proxy (share of kept events whose strongest gate "
                              "is geometry-corroborated); it is not human-verified precision",
            "reject_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
            "per_kind": krites, "near_misses": near_misses(rows)}


def near_misses(rows, limit=5):
    """Not-confirmed candidates whose measured evidence is strong enough to look at.

    The gates are deliberately conservative: a weak detector cannot corroborate
    a fast ball, so some real events end up here instead of in the queue.  Each
    row carries the numbers, and a human decides in seconds.
    """
    scored = []
    for row in rows:
        if row["verdict"]["status"] == "confirmed":
            continue
        evidence = row["evidence"]
        score, why = 0.0, []
        for vanish in evidence.get("vanish", []):
            if vanish.get("dist_mm") is not None and vanish["dist_mm"] <= 150 and (vanish.get("pre_hits") or 0) >= 2:
                score += 2
                why.append(f"{vanish['color']} vanished {vanish['dist_mm']}mm from "
                           f"{vanish['pocket']} (seen {vanish['pre_hits']}x, approach "
                           f"{vanish.get('approach_mm')}mm)")
        drop = evidence.get("census_pre"), evidence.get("census_post")
        if all(isinstance(v, (int, float)) for v in drop) and drop[0] - drop[1] >= 1:
            score += 1
            why.append(f"census {drop[0]:g}->{drop[1]:g}")
        if (evidence.get("disp_mm") or 0) >= 150:
            score += 1
            why.append(f"ball moved {evidence['disp_mm']}mm ({evidence.get('disp_color')})")
        if (evidence.get("census_disp_mm") or 0) >= 150:
            score += 1
            why.append(f"fused census: a ball moved {evidence['census_disp_mm']}mm "
                       f"({evidence.get('census_disp_color')}) with "
                       f"{evidence.get('census_start_hits')}/{evidence.get('census_end_hits')} sightings")
        if (evidence.get("window_motion") or 0) >= 20:
            score += 0.5
            why.append(f"window motion {evidence['window_motion']}")
        if why:
            scored.append({"score": score, "id": row["id"], "kind": row["kind"], "t": row["t"],
                           "color": row["color"], "why": why,
                           "gate": row["verdict"]["reasons"]})
    scored.sort(key=lambda item: (-item["score"], item["t"] or 0))
    return scored[:limit]


def build_rows(groups, previous_ids):
    """One reporting row per group, with the queue id it would carry."""
    rows = []
    for group in groups:
        event = to_queue_event(group, previous_ids)
        rows.append({"id": event["id"], "kind": group["event"]["kind"], "t": group["event"]["t"],
                     "color": group["event"]["color"], "dup_count": group["count"],
                     "measured": group["event"]["raw"].get("measured"),
                     "pocket": event.get("nearest_pocket") or next(
                         (v.get("pocket") for v in group["evidence"].get("vanish", [])), None),
                     "verdict": group["verdict"], "evidence": group["evidence"],
                     "event": event})
    return rows


def _census_line(row):
    """One line an owner can check in seconds: census, vanish, motion, verdict."""
    numbers = row["verdict"].get("numbers") or {}
    if row["kind"] == "pot":
        source = numbers.get("census_source") or "-"
        vanish = "no vanished ball measured"
        if numbers.get("vanish_color"):
            vanish = (f"{numbers['vanish_color']} vanished {numbers.get('vanish_dist_mm')}mm "
                      f"from {numbers.get('vanish_pocket')} (seen {numbers.get('vanish_pre_hits')}x, "
                      f"approach {numbers.get('approach_mm')}mm)")
        present = ""
        if numbers.get("claim_color_present"):
            present = f" | claim colour still on the cloth: {numbers.get('claim_color_present_sources')}"
        return (f"census {source} {numbers.get('census_pre')}->{numbers.get('census_post')} "
                f"(max {numbers.get('census_post_max')}, sam3 frames "
                f"{numbers.get('sam3_frames_pre')}/{numbers.get('sam3_frames_post')}) | {vanish} | "
                f"motion {numbers.get('motion_max')}{present}")
    return (f"census disp {numbers.get('census_disp_mm')}mm {numbers.get('census_disp_color') or ''} "
            f"(hits {numbers.get('census_start_hits')}/{numbers.get('census_end_hits')}, "
            f"moved {numbers.get('census_tracks_moved')}, gap {numbers.get('census_geometry_gap_px')}px), "
            f"classical disp {numbers.get('disp_mm')}mm {numbers.get('disp_color') or ''} "
            f"(stable {numbers.get('stable_hits')}/{numbers.get('anchor_tries')}) | "
            f"motion {numbers.get('window_motion')}")


def print_report(rows, summary, agree, calibration, seconds, probe_seconds, previous_count):
    print(f"calibration: {calibration}")
    print("caveat: the VOD changes framing (the reference quad covers 0.38-0.82 cloth-hued "
          "pixels at t=450/483/1120 s against 0.85-1.00 in the calibrated segment), so "
          "millimetres and pocket distances are approximate outside that segment; "
          "occlusion lowers the same number, so it is reported per event, not gated on.")
    print(f"probe: {probe_seconds}s video decode inside {seconds}s wall "
          f"(queue had {previous_count} events)")
    print("id | kind |    t | color  | dup | status      | gate         | reasons")
    for row in rows:
        gate = row["verdict"]
        print(f"{str(row['id'] if row['id'] is not None else '-'):>2} | {row['kind']:4} | {row['t']:6.1f} | "
              f"{str(row['color'] or '-'):6} | {row['dup_count']:3} | {gate['status']:11} | "
              f"{gate['gate']:12} | {','.join(gate['reasons'])}")
        print(f"     {_census_line(row)}")
    print("aggregate:", json.dumps({k: v for k, v in summary.items() if k != "near_misses"}))
    for miss in summary["near_misses"]:
        print(f"near miss: id={miss['id']} {miss['kind']} t={miss['t']} ({miss['color']}) "
              f"score={miss['score']} -- {'; '.join(miss['why'])} | gate={miss['gate']}")
    if agree["reported"]:
        print(f"owner verdicts: {agree['reported']} recorded, {agree['agreement']}/{agree['comparable']} "
              f"agree with the gates ({agree['unsure_rejected_by_gates']} recorded 'unsure' also rejected)")
        for row in agree["rows"]:
            print(f"  id={row['id']} owner={row['owner_verdict']} gate={row['gate_status']} "
                  f"agrees={row['agrees']} reasons={row['gate_reasons']}")
    else:
        print("owner verdicts: none found (out/scan30/annotations.json is absent)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queue", default="out/scan30/events.json", help="served queue artifact")
    ap.add_argument("--candidates", default="out/scan-ic/events.json",
                    help="scan candidates the queue was built from (default) or the queue itself")
    ap.add_argument("--video", default="data/vod_30min_260815.mp4")
    ap.add_argument("--anchors", default="out/pid_anchors_vod30.json")
    ap.add_argument("--scan-quad", default="out/scan30/corners.json")
    ap.add_argument("--dataset", default="vod30",
                    help="calibration segment artifact to resolve the reference quad per event")
    ap.add_argument("--report", default="out/scan30/eval_events.json")
    ap.add_argument("--cache", default="out/scan30/probe_events.json")
    ap.add_argument("--no-probe", action="store_true", help="cached measurements only")
    ap.add_argument("--write-queue", action="store_true",
                    help="rewrite --queue with confirmed candidates (backup kept)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    cfg = GateConfig()
    forward, inverse, label = reference_calibration(args.anchors, args.scan_quad)
    quad = load_quad(args.anchors, "anchors") if inverse is not None else None
    if quad is None:
        quad = load_quad(args.scan_quad)
    segments = load_segments(args.dataset)
    if segments is not None:
        label = f"{label}; per segment: {segments.verdict} ({len(segments.segments)} segment(s))"
    probe = None
    if not args.no_probe and inverse is not None and Path(args.video).exists():
        probe = Probe(args.video, forward, inverse, quad, segments=segments)
        if not probe.open():
            probe = None
    candidates = Path(args.candidates)
    if not candidates.exists():
        candidates = Path(args.queue)
    groups, seconds = measure(candidates, probe, cfg, limit=args.limit,
                              cache_path=Path(args.cache), use_cache=True)
    probe_seconds = round(probe.seconds, 1) if probe else 0.0
    if probe:
        probe.close()

    target = Path(args.queue)
    backup = target.with_name("events.pre-gate.json")
    fixture_queue = Path("out/ui-browser-fixture/out/scan30/events.json")
    # The ids the owner saw come from the pre-gate backup and the fixture first:
    # the queue itself has already been rewritten by an earlier pass.
    previous_ids = queue_id_map(backup, fixture_queue, target)
    rows = build_rows(groups, previous_ids)
    queue = [row["event"] for row in rows if row["verdict"]["status"] == "confirmed"
             and row["event"]["id"] is not None]
    if any(row["verdict"]["status"] == "confirmed" and row["event"]["id"] is None for row in rows):
        next_id = max([int(v) for v in previous_ids.values() if str(v).isdigit()] or [0]) + 1
        for row in rows:
            if row["verdict"]["status"] == "confirmed" and row["event"]["id"] is None:
                row["event"]["id"] = next_id
                next_id += 1
    queue = [row["event"] for row in rows if row["verdict"]["status"] == "confirmed"]
    queue.sort(key=lambda event: event["t"])
    summary = summarize(rows)
    agree = agreement(rows, owner_verdicts([Path(p) for p in HUMAN_VERDICT_FILES]))
    # The delta the owner cares about is the queue as it was served before this
    # tool first ran, which the backup preserves.
    before = backup if backup.exists() else target
    previous_count = len(json.loads(before.read_text())) if before.exists() else 0
    report = {"generated_from": {"queue": args.queue, "candidates": str(candidates),
                                 "video": args.video if probe else None, "calibration": label,
                                 "human_verdicts": "read-only"},
              "thresholds": asdict(cfg), "aggregates": summary, "owner_verdicts": agree,
              "seconds": seconds, "probe_seconds": probe_seconds,
              "previous_queue_size": previous_count, "queue_size": len(queue),
              "events": [{"id": row["id"], "kind": row["kind"], "t": row["t"], "color": row["color"],
                          "dup_count": row["dup_count"], "measured": row.get("measured"),
                          "verdict": row["verdict"],
                          "evidence": row["evidence"]} for row in rows]}
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=1))
    print_report(rows, summary, agree, label, seconds, probe_seconds, previous_count)
    print(f"{previous_count} -> {len(queue)} events; report -> {args.report}")

    if args.write_queue:
        target = Path(args.queue)
        if target.exists():
            backup = target.with_name("events.pre-gate.json")
            if not backup.exists():
                backup.write_text(target.read_text())
        target.write_text(json.dumps(queue, indent=1))
        sidecar = target.parent / "gate_report.json"
        sidecar.write_text(json.dumps({
            "aggregates": summary, "owner_verdicts": agree, "previous_queue_size": previous_count,
            "not_confirmed": [{"id": row["id"], "kind": row["kind"], "t": row["t"],
                               "color": row["color"], "dup_count": row["dup_count"],
                               "verdict": row["verdict"], "evidence": row["evidence"]}
                              for row in rows if row["verdict"]["status"] != "confirmed"]}, indent=1))
        print(f"queue -> {target} ({len(queue)} events), not-confirmed -> {sidecar}")


if __name__ == "__main__":
    main()
