"""Resolve a frame time to the reference quad its millimetres were measured against.

``docs/state.md`` has warned since the start that calibration is **per segment**:
the highlight VOD and vod30 have different framing, and a single ``H`` must not be
reused across a camera move.  This module is the one place that answers "which
reference belongs to this time?", reading ``out/calib_vod30_segments.json`` (built
by ``src/calib_segment_fit.py`` from the measurement of
``src/calib_segment_measure.py``).

Contract, deliberately small:

* :func:`load` - the artifact for a dataset, or ``None``.  A missing or broken
  artifact is not an error: every caller keeps whatever reference it had.
* :func:`resolve` - **exactly one** segment for a time.  A time inside a segment
  returns that segment; a time outside every segment returns the nearest one with
  ``clamped=True``; a missing or non-finite time returns the first segment with
  ``clamped=True`` and ``reason="no_time"``.  It never raises and never returns
  ``None`` for a non-empty artifact, so an out-of-range frame has a defined
  reference instead of an exception.
* :func:`quad_for` / :func:`homographies` - the pixels and the
  pixels<->canonical-millimetre pair for that time.

The lookup is a pure function of the artifact, so a later measured split is a data
change, not a code change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACT = "calib_{dataset}_segments.json"
SOURCES = ("human_anchors", "refined", "derived")


@dataclass
class Segment:
    """One time range with the reference quad its events are measured against."""
    id: str
    t_start: float
    t_end: float
    quad: np.ndarray
    source: str = "unknown"
    coverage: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    source_detail: str | None = None
    clamped: bool = False
    clamp_reason: str | None = None

    @property
    def human(self) -> bool:
        """True when the quad is human geometry, not a derived refinement."""
        return self.source == "human_anchors"

    def as_dict(self) -> dict:
        return {"id": self.id, "t_start": self.t_start, "t_end": self.t_end,
                "source": self.source, "quad_px": np.round(self.quad, 2).tolist(),
                "clamped": self.clamped, "clamp_reason": self.clamp_reason}


class Segments:
    """A loaded segment artifact: ordered, non-overlapping, time-resolvable."""

    def __init__(self, payload: dict, dataset: str | None = None, path=None):
        self.payload = payload or {}
        self.dataset = dataset or self.payload.get("dataset")
        self.path = Path(path) if path is not None else None
        self.warnings: list[str] = []
        self.segments: list[Segment] = []
        for raw in self.payload.get("segments") or []:
            seg = self._segment(raw)
            if seg is not None:
                self.segments.append(seg)
        self.segments.sort(key=lambda s: (s.t_start, s.t_end))
        self._check_overlaps()

    @staticmethod
    def _segment(raw: dict) -> Segment | None:
        try:
            quad = np.asarray(raw["quad_px"], np.float32).reshape(4, 2)
            t_start, t_end = float(raw["t_start"]), float(raw["t_end"])
        except (KeyError, TypeError, ValueError):
            return None
        if not np.isfinite(quad).all():
            return None
        source = str(raw.get("source") or "unknown")
        return Segment(id=str(raw.get("id") or f"s{t_start:g}-{t_end:g}"),
                       t_start=t_start, t_end=t_end, quad=quad, source=source,
                       coverage=raw.get("coverage") or {}, evidence=raw.get("evidence") or {},
                       source_detail=raw.get("source_detail"))

    def _check_overlaps(self):
        for prev, cur in zip(self.segments, self.segments[1:]):
            if cur.t_start < prev.t_end:
                self.warnings.append(
                    f"segments {prev.id} and {cur.id} overlap at t={cur.t_start}; "
                    f"{prev.id} wins because it sorts first")

    @property
    def verdict(self) -> str:
        return str(self.payload.get("segmentation_verdict") or "unknown")

    def in_range(self, t) -> bool:
        """True only when ``t`` lies inside a segment - no clamping, no guess."""
        value = _time(t)
        if value is None:
            return False
        return any(s.t_start <= value <= s.t_end for s in self.segments)

    def resolve(self, t) -> Segment | None:
        """The single segment for ``t``; nearest (flagged) when out of range."""
        if not self.segments:
            return None
        value = _time(t)
        if value is None:
            return self._clamp(self.segments[0], "no_time")
        for seg in self.segments:                       # sorted; first match wins
            if seg.t_start <= value <= seg.t_end:
                return seg
        nearest = min(self.segments, key=lambda s: min(abs(value - s.t_start), abs(value - s.t_end)))
        return self._clamp(nearest, "outside_all_segments")

    @staticmethod
    def _clamp(seg: Segment, reason: str) -> Segment:
        return Segment(id=seg.id, t_start=seg.t_start, t_end=seg.t_end, quad=seg.quad,
                       source=seg.source, coverage=seg.coverage, evidence=seg.evidence,
                       source_detail=seg.source_detail, clamped=True, clamp_reason=reason)

    def quad_for(self, t) -> np.ndarray | None:
        seg = self.resolve(t)
        return None if seg is None else seg.quad

    def homographies(self, t):
        """``(forward, inverse, segment)``: pixels -> canonical mm and back."""
        seg = self.resolve(t)
        if seg is None:
            return None, None, None
        from src.table_geometry import homography_to_canonical
        try:
            forward = homography_to_canonical(seg.quad)
            return forward, np.linalg.inv(forward), seg
        except Exception:
            return None, None, seg

    def gaps(self) -> list[tuple[float, float]]:
        """Time ranges no segment covers, so a caller can see the holes."""
        return [(a.t_end, b.t_start) for a, b in zip(self.segments, self.segments[1:])
                if b.t_start > a.t_end]


def _time(t):
    try:
        value = float(t)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


_CACHE: dict = {}


def load(dataset: str = "vod30", path=None, root=None, use_cache: bool = True) -> Segments | None:
    """The segment artifact for ``dataset``, or ``None`` when there is none.

    ``root`` (the checkout or the server's tree) keeps a caller pointed at its own
    artifacts; a fixture tree without the file simply gets ``None`` and keeps the
    reference it already had.  A malformed file is reported as ``None`` with a
    warning on the returned object only if it parses; a JSON error is swallowed
    the same way, because a broken calibration artifact must not take the caller
    down.
    """
    base = Path(root) if root is not None else ROOT
    target = Path(path) if path is not None else base / "out" / ARTIFACT.format(dataset=dataset)
    key = (str(target), target.stat().st_mtime_ns if target.is_file() else None)
    if use_cache and key in _CACHE:
        return _CACHE[key]
    result = None
    if target.is_file():
        try:
            result = Segments(json.loads(target.read_text()), dataset=dataset, path=target)
        except (OSError, ValueError):
            result = None
        if result is not None and not result.segments:
            result = None
    if use_cache:
        _CACHE[key] = result
        if len(_CACHE) > 32:
            _CACHE.clear()
    return result
