"""Resolve a frame time to the reference quad its millimetres were measured against.

``docs/state.md`` has warned since the start that calibration is **per segment**:
the highlight VOD and vod30 have different framing, and a single ``H`` must not be
reused across a camera move.  This module is the one place that answers "which
reference belongs to this time?", reading ``out/calib_vod30_segments.json`` (built
by ``src/calib_segment_fit.py`` from the measurement of
``src/calib_segment_measure.py``).

Contract, deliberately small:

* :func:`read` - one named calibration file, and the entry inside it.  This is the
  only place that parses the artifact layout, so no reader holds a second copy of
  it.
* :func:`resolve` - **the one reference for a dataset at a time**, as a
  :class:`Reference`: the quad, the file it came from, the entry inside that file,
  and whether the reference is per-time or one static reference for the dataset.
  The chain is the caller's ``quad_file``, the segment artifact for the time, the
  dataset's saved reference file, then the ``table_refine`` prior.  The reference
  that ``docs/app-path-refusal.md`` refuses is never selected here.
* :func:`load` - the artifact for a dataset, or ``None``.  A missing or broken
  artifact is not an error: every caller keeps whatever reference it had.
* :meth:`Segments.resolve` - **exactly one** segment for a time, inside one
  artifact.  A time inside a segment returns that segment; a time outside every
  segment returns the nearest one with ``clamped=True``; a missing or non-finite
  time returns the first segment with ``clamped=True`` and ``reason="no_time"``.
  It never raises and never returns ``None`` for a non-empty artifact, so an
  out-of-range frame has a defined reference instead of an exception.
* :func:`quad_for` / :func:`homographies` - the pixels and the
  pixels<->canonical-millimetre pair for that time.
* :func:`verified_cloth_quad` - **the verified cloth quad of one dataset**, as a
  :class:`Reference`.  This is the only owner of that rule.  It reads the human
  calibration segment of the dataset, then the hand anchors of that dataset, then
  the scan corners.  It derives the anchors path from the dataset, so no caller
  can freeze one dataset into a signature default.  :func:`anchors_reference_path`
  and :func:`anchors_reference_name` name that file, and no other module of the
  shipped tree spells the name: every reader reads one of them, or one of the two
  ends ``ANCHORS_HEAD`` and ``ANCHORS_SUFFIX``.  Two CLI defaults keep the text as a
  frozen literal, because argparse prints a default in ``--help`` and a recorded
  command line holds it; tests/test_anchor_name_owner.py holds the two equal to the
  text below.

The document name ``CALIBRATION`` has one home here too, and the reader
:func:`calibration_name` answers the file name of one dataset.  ``docs/console-redesign.md``
records that name.  A reader that writes the text again makes a later rename read a
file that does not exist.  tests/test_calib_segments.py tells you.

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

# The calibration document of one dataset.  The store reads this text as a row of
# its kind -> file map, and the three readers of the document read the file name
# below.  A reader that writes the text again holds a second home, and a rename
# then moves one home alone.
CALIBRATION = "calib_{dataset}.json"


def calibration_name(dataset: str) -> str:
    """The file name alone of the calibration document of one dataset.

    The dataset argument names the file, as the argument of
    :func:`anchors_reference_path` does.  A caller that joins a folder and this
    name keeps its own root, so the path of the document cannot drift from the
    path the store resolves.
    """
    return CALIBRATION.format(dataset=dataset)


def segment_artifact_path(dataset: str, root=None) -> Path:
    """The segment artifact of one dataset, under the out/ root of a tree.

    ``ARTIFACT`` is the one spelling of the file name, so a caller that joins a
    directory and the name reads this function or the template.  ``root`` (the
    checkout or the server's own tree) keeps the caller pointed at its artifacts,
    as ``load`` does.  A caller that holds the bytes of an older artifact carries
    its own path, because its document is not this document.
    """
    base = Path(root) if root is not None else ROOT
    return base / "out" / ARTIFACT.format(dataset=dataset)


# The corners v2 file of the strip refinement, as a format for its tag.  This
# text is the one home of the name.  Six modules read the file and one module
# writes it, and every one of them reads this text or the two functions below.
# tests/test_vod30_corners.py and tests/test_table_refine.py hold that rule.
CORNERS_V2 = "out/corners_{tag}_v2.json"
CORNERS_V2_PATH_HEAD, _, CORNERS_V2_SUFFIX = CORNERS_V2.partition("{tag}")
CORNERS_V2_HEAD = CORNERS_V2_PATH_HEAD.rpartition("/")[2]

# The tag of the shipped artifact.  src/make_segment_corners.py writes this tag
# when the command line names no other one.
CORNERS_V2_TAG = "30min"


def corners_v2_name(tag: str = CORNERS_V2_TAG) -> str:
    """The file name alone of the corners v2 file of one tag.

    ``corners_v2_path`` answers the path under the out/ root.  A reader that
    matches a stored name, as ``REFUSED`` does, reads this function or the head
    and the suffix above.
    """
    return f"{CORNERS_V2_HEAD}{tag}{CORNERS_V2_SUFFIX}"


def corners_v2_path(tag: str = CORNERS_V2_TAG, root=None) -> Path:
    """The corners v2 file of one tag, under the out/ root of one tree.

    ``CORNERS_V2`` is the one spelling of the name, so a caller that joins a
    directory and the name reads this function or the template.  ``root`` (the
    checkout or the server's own tree) keeps the caller pointed at its own
    artifacts, as ``segment_artifact_path`` does.
    """
    base = Path(root) if root is not None else ROOT
    return base / CORNERS_V2.format(tag=tag)


SOURCES = ("human_anchors", "refined", "derived")

# The layout of a calibration file, in the order a caller-supplied file is read.
QUAD_KEYS = ("quad_px", "corners", "anchors")

# The one reference ``docs/app-path-refusal.md`` refuses.  Its left rail is about
# 70 px outside the cloth at the top and about 70 px inside at the bottom, so a
# detector seeded from it searched the carpet.  No chain below selects it.  A
# reader may still read it by name for a comparison, and it then says why.
REFUSED = corners_v2_name()

# The time the vod30 hand anchors were clicked.  The file keys its six pocket
# anchors by time; the first four points are the cloth quad.
ANCHOR_T = 70.0

# The anchor file name of a dataset, as a format for that dataset.  The one
# derivation.  A caller may override the name, but the dataset it names must
# still come from the dataset argument, never from a default of that caller.
# The two ends of that format and the head of the file name come from this one
# text: a reader that joins a directory and a file name, or that asks whether a
# stored name is an anchor file, reads one of these three names, and a change of
# the text moves every reader at once.  Two CLI defaults keep the text as a frozen
# literal, because argparse prints a default in ``--help`` and a recorded command
# line holds it; tests/test_anchor_name_owner.py holds the two equal to this text.
ANCHORS_REFERENCE = "out/pid_anchors_{dataset}.json"
ANCHORS_PATH_HEAD, _, ANCHORS_SUFFIX = ANCHORS_REFERENCE.partition("{dataset}")
ANCHORS_HEAD = ANCHORS_PATH_HEAD.rpartition("/")[2]


def anchors_reference_name(dataset: str = "vod30") -> str:
    """The file name alone of the anchor file of one dataset.

    ``anchors_reference_path`` answers the path from the out/ root.  A reader that
    joins a directory of its own and a file name, or that matches a stored name,
    reads this function or the two ends above.  Both answers come from the one text
    ``ANCHORS_REFERENCE``, so no reader holds a second spelling of the name.
    """
    return f"{ANCHORS_HEAD}{dataset}{ANCHORS_SUFFIX}"


# The saved reference file of a dataset.  A file marked ``table`` keys its points
# by time, and the entry nearest the requested time then wins.  A dataset without
# a table entry uses its reference corners file, as the readers did before.
#
# The name of that file has one home, the ``file`` entry below.  A reader that
# joins a directory of its own reads ``CORNERS_SPEC["file"]`` and holds no second
# spelling of the name.  Round 108 moved the readers in src/eval_table_detect.py,
# src/audit_calib.py, src/quad_fit.py, src/quad_fit_lines.py and
# src/calib_mapping_audit.py onto this entry.
CORNERS_SPEC = {"file": "fixed_corners.json", "key": "corners", "table": False}
STATIC_REFERENCES = {
    "vod30": {"file": anchors_reference_name("vod30"), "key": "anchors", "table": True},
    "highlight": CORNERS_SPEC,
}

# The reason the highlight reference file may be trusted for millimetres.
EVIDENCE_HIGHLIGHT = ("src/table_refine.py _DATASET_PRIOR documents this file at "
                      "2.0 px median against the cloth quad")


def reference_spec(dataset):
    """The saved reference entry of one dataset, or None for a name not in the table.

    This table is the one owner of the (file, key) pair of a dataset.
    ``src/table_refine.py`` builds its own prior table from this function, so the two
    readers cannot hold two answers.

    An unknown name answers None.  No unknown name takes a fallback.  The table
    named an unknown dataset before round 67 and served it ``fixed_corners.json``,
    the file of the highlight dataset.  That file is the reference of ``highlight``
    alone, so an unknown name took the geometry of another dataset in silence.
    ``src/table_refine.py prior_for`` answers None for that name too, and the two
    readers now agree."""
    return STATIC_REFERENCES.get(str(dataset))

# The steps of the chain, in order.  ``resolve`` walks them in this order.
KINDS = ("supplied", "segment", "static", "prior")

# The steps of :func:`verified_cloth_quad`, in order.  The first step with a quad
# wins.  "human segment" is the human calibration segment of one dataset, "hand
# anchors" is the anchor file of that dataset, and "scan corners" is the scan's
# own naive corners.  This tuple IS the resolution order; a reader that states
# the order again holds a second copy of the rule.
CLOTH_STEPS = ("human_segment", "hand_anchors", "scan_corners")

# The scan's own corners file.  It is one path for the checkout, so it carries no
# dataset name.  The loader takes the root from ``verified_cloth_quad``.
SCAN_CORNERS = "out/scan30/corners.json"

# The two frames a person verified against the reference quad, and the coverage
# each one measured.  ``docs/calibration-truth.md`` states the same pair.  The
# audit, the measure tool, the fit and the report read these names, so one edit
# moves all four readers together.  A module that writes one of the two times as a
# number holds a second copy of this fact.
VERIFIED_FRAME_LOW = 483.4
VERIFIED_FRAME_HIGH = 1120.2
VERIFIED_FRAMES = (VERIFIED_FRAME_LOW, VERIFIED_FRAME_HIGH)

# Prose strings for one owner only.  Both readers write one of these next to the
# quad, so a reader may report the rule without stating it again.
CLOTH_LABELS = {"human_segment": "human calibration segment",
                "hand_anchors": "hand anchors",
                "scan_corners": "scan corners"}


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

    @property
    def alternative(self) -> dict:
        """The counterfactual late-window reference the artifact records, if any."""
        return self.payload.get("late_window_alternative") or {}

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


# The note of a frame whose search found no verified quad.  The console and the
# served documents carry this sentence, so one edit moves both readers of it.
# ``resolve`` writes it beside the ``Reference`` it answers, and
# ``src.motion_scan.load_quad`` reads this name for the same state.
NOTE_NO_QUAD = "no quad found"

# The refusal of a quad of the wrong shape, one wording for the two raises below
# and for ``src.motion_scan.load_quad``.  The value is the prefix of the message
# alone: each raise appends the shape it received, so the text the caller reads is
# the sentence the callers read before round 108.
QUAD_SHAPE_ERROR = "expected a 4x2 quad, got "

# The calibration side-mapping keys.  A refinement reports the boundary of each
# side of the quad, and these four keys carry that report into the segment
# recording.  Four live modules wrote the words themselves: ``table_refine``
# writes them, and ``calib_segment_measure``, ``calib_segment_fit`` and
# ``calib_mapping_audit`` read them back.  The home holds the words once, so one
# edit of a key moves every writer and every reader with it.
#
# The served contract does not change.  The key of a row on disk stays the value
# of the constant, so the documents and the page that read them keep their bytes:
# ``annotator/app.js:1167`` and ``annotator/vision-stage.js:328`` read
# ``verified_sides`` of a quad of the page, and no python name reaches them.  The
# guard ``tests/test_calib_mapping_keys_owner.py`` holds both lines.
#
# ``supported_sides`` and the per-side keys (``side``, ``reason``, ``state``) are
# no part of this home.  One writer alone builds them, so a second spelling of
# them has nothing to collide with.
VERIFIED_SIDES_KEY = "verified_sides"
UNVERIFIED_SIDES_KEY = "unverified_sides"
INHERITED_SIDES_KEY = "inherited_sides"
MASK_OFFSET_PX_KEY = "mask_offset_px"


@dataclass
class Reference:
    """One calibration reference: the quad and where it came from.

    ``artifact`` names the file, ``entry`` names the segment or the key inside that
    file.  ``per_time`` is True only for a segment artifact, where the frame time
    selects the reference; every other reference is one static quad for the
    dataset.  ``origin`` is the string a reader reports as the source of the quad.
    ``model`` carries the loaded :class:`Segments` when the reference is per-time,
    so a reader that needs the whole time-resolved model gets it from the same
    call.  :meth:`as_dict` reads no file and is safe to log.
    """
    dataset: str | None = None
    quad: np.ndarray | None = None
    kind: str = "none"
    artifact: str | None = None
    entry: str | None = None
    per_time: bool = False
    source: str | None = None
    detail: str | None = None
    note: str | None = None
    evidence: str | None = None
    origin: str = "none"
    clamped: bool = False
    clamp_reason: str | None = None
    t_start: float | None = None
    t_end: float | None = None
    points: np.ndarray | None = None
    model: Segments | None = None
    declared: dict = field(default_factory=dict)
    rejected: list = field(default_factory=list)

    @property
    def found(self) -> bool:
        """True when a quad was resolved."""
        return self.quad is not None

    @property
    def verified(self) -> bool:
        """True when the reference states a reason to trust it for millimetres."""
        return bool(self.evidence)

    def as_dict(self) -> dict:
        """The provenance a reader can log.  It reads no file."""
        return {"dataset": self.dataset, "kind": self.kind, "per_time": self.per_time,
                "artifact": self.artifact, "entry": self.entry, "source": self.source,
                "origin": self.origin, "clamped": self.clamped,
                "clamp_reason": self.clamp_reason, "t_start": self.t_start,
                "t_end": self.t_end, "verified": self.verified,
                "evidence": self.evidence, "note": self.note,
                "quad_px": None if self.quad is None else np.round(self.quad, 3).tolist(),
                "rejected": list(self.rejected)}

    def __str__(self) -> str:
        where = self.artifact or "none"
        entry = f" entry={self.entry}" if self.entry else ""
        return f"Reference({self.kind} {where}{entry} verified={self.verified})"


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
    target = Path(path) if path is not None else segment_artifact_path(dataset, base)
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


def _nearest_key(table: dict, t) -> str | None:
    """The time key of ``table`` nearest ``t``; the first key when no time is known."""
    times = {}
    for name in table:
        value = _time(name)
        if value is not None:
            times[name] = value
    if not times:
        return next(iter(table), None)
    target = _time(t)
    if target is None:
        return next(iter(times), None)
    return min(times, key=lambda name: (abs(times[name] - target), times[name]))


def read(path, key: str | None = None, t=None, order: bool = False,
         strict: bool = False) -> Reference:
    """One named calibration file, read here so that no reader parses the layout.

    ``key`` selects the entry: ``quad_px``, ``corners`` or ``anchors``.  Without a
    key the first of those that the file carries wins.  An ``anchors`` entry is a
    table keyed by time; the key nearest ``t`` wins, and the first key wins when
    ``t`` is unknown.  ``order`` orders the four corners clockwise from the top
    left, for a caller that compares pixel geometry.

    A missing file, a broken file, or an entry with fewer than four points returns
    a not-found reference, so that a caller keeps whatever reference it had.
    ``strict`` raises instead: a caller-supplied path must not be ignored in
    silence.  The refused reference IS readable by name here, because a comparison
    may need it; only the chain in :func:`resolve` must not select it.
    """
    if path is None or str(path) == "":
        return Reference(note="no path given")
    target = str(path)
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        if strict:
            raise
        return Reference(artifact=target, note="file not read")
    if not isinstance(data, dict):
        if strict:
            raise ValueError(f"{target}: expected a JSON object")
        return Reference(artifact=target, note="not a JSON object")
    names = (key,) if key else QUAD_KEYS
    value, entry = None, None
    for name in names:
        found = data.get(name)
        if found:
            value, entry = found, name
            break
    if entry is None:
        return Reference(artifact=target, note="no quad entry in the file")
    if isinstance(value, dict):
        chosen = _nearest_key(value, ANCHOR_T if t is None else t)
        if chosen is None:
            return Reference(artifact=target, entry=entry, note="empty anchor table")
        value, entry = value[chosen], chosen
    try:
        points = np.asarray(value, np.float32).reshape(-1, 2)
    except (TypeError, ValueError):
        if strict:
            raise ValueError(f"{QUAD_SHAPE_ERROR}{np.shape(value)}")
        points = np.empty((0, 2), np.float32)
    if points.shape[0] < 4:
        if strict:
            raise ValueError(f"{QUAD_SHAPE_ERROR}{points.shape}")
        return Reference(artifact=target, entry=entry, note="fewer than four points")
    quad = points[:4]
    if order:
        from src.table_detect import _order_corners
        quad = _order_corners(quad)
    note = str(data.get("note")) if data.get("note") else None
    return Reference(quad=quad, kind="static", artifact=target, entry=entry,
                     source=entry, origin=target, note=note, points=points,
                     declared={"verified": bool(data.get("verified"))})


def static_reference(dataset: str = "vod30", t=None, root=None,
                     order: bool = False) -> Reference:
    """The saved reference file of a dataset, or a not-found reference.

    vod30 carries the hand anchors: six clicked pocket points at t=70, and the
    first four are the cloth quad.  Every other dataset carries its own reference
    corners.  The file is one static reference for the dataset; a time only selects
    which recorded anchor entry is used.
    """
    base = Path(root) if root is not None else ROOT
    spec = reference_spec(dataset)
    if spec is None:
        return Reference(kind="none", origin="none", note="no saved reference file",
                         dataset=dataset, rejected=[f"no static reference for {dataset!r}"])
    reference = read(base / "out" / spec["file"], spec["key"],
                     t=ANCHOR_T if t is None else t, order=order)
    reference.dataset = dataset
    if not reference.found:
        return reference
    if str(dataset) == "vod30":
        reference.note = f"hand pocket anchors at t={reference.entry} (first four)"
        reference.evidence = "hand anchors"
    else:
        reference.note = "dataset reference corners"
        reference.evidence = EVIDENCE_HIGHLIGHT if str(dataset) == "highlight" else None
    return reference


def _fits(quad, origin: str, frame_size) -> str | None:
    """``None`` when the quad fits the frame, else the rejection line."""
    if frame_size is None:
        return None
    w, h = float(frame_size[0]), float(frame_size[1])
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    if max(xs) > w or max(ys) > h or min(xs) < 0 or min(ys) < 0:
        shown = np.round(np.asarray(quad, np.float64), 3).tolist()
        return f"{origin}: quad {shown} does not fit {w:g}x{h:g}"
    return None


def _checked(reference: Reference | None, frame_size, rejected: list) -> Reference | None:
    """The reference when it has a quad that fits ``frame_size``, else ``None``."""
    if reference is None or not reference.found:
        return None
    line = _fits(reference.quad, reference.origin, frame_size)
    if line is None:
        return reference
    rejected.append(line)
    return None


def _supplied_reference(quad_file, rejected: list) -> Reference | None:
    """The caller's own quad file.  The refused reference is not accepted here."""
    path = Path(quad_file)
    if path.name == REFUSED:
        rejected.append(f"{path}: refused by docs/app-path-refusal.md as a "
                        "calibration reference")
        return None
    reference = read(path, strict=True)
    reference.kind = "supplied"
    reference.origin = str(quad_file)
    reference.note = reference.note or "caller-supplied quad"
    if reference.declared.get("verified"):
        reference.evidence = "caller-supplied"
    return reference


def _segment_reference(dataset, t, base, artifact, prefer_human: bool,
                       use_cache: bool) -> Reference | None:
    """The segment artifact's reference for ``t``, or ``None`` without one."""
    if artifact is None:
        model = load(dataset, root=base, use_cache=use_cache)
    else:
        model = load(dataset, path=artifact, use_cache=use_cache)
    if model is None or not model.segments:
        return None
    if prefer_human:
        seg = next((s for s in model.segments if s.human), None)
    else:
        seg = model.resolve(t)
    if seg is None:
        return None
    note = seg.source_detail or seg.source
    if not prefer_human and _time(t) is None and len(model.segments) > 1:
        note = (f"{len(model.segments)} segments; using the first -- per-time segment "
                "lookup belongs to the calibration, not to this measurement")
    evidence = seg.evidence or {}
    origin = str(model.path) if model.path is not None else "none"
    return Reference(dataset=dataset, quad=seg.quad, kind="segment", artifact=origin,
                     entry=seg.id, per_time=True, source=seg.source,
                     detail=seg.source_detail, note=note,
                     evidence=(evidence.get("trust_reason")
                               if evidence.get("trusted_for_mm") else None),
                     origin=origin, clamped=seg.clamped, clamp_reason=seg.clamp_reason,
                     t_start=seg.t_start, t_end=seg.t_end, model=model)


def _prior_reference(dataset, t, base, rejected: list) -> Reference | None:
    """The ``table_refine`` search-centre prior, the last resort in the chain."""
    try:
        from src.table_refine import prior_for
        prior = prior_for(dataset, t, root=base)
    except Exception as exc:
        rejected.append(f"table_refine prior: {exc}")
        return None
    if prior is None:
        return None
    quad = np.asarray(prior, np.float32)
    if quad.shape != (4, 2):
        return None
    return Reference(dataset=dataset, quad=quad, kind="prior",
                     origin="src.table_refine.prior_for",
                     note="search-centre prior, not a verified quad")


def resolve(dataset: str = "vod30", t=None, root=None, artifact=None, quad_file=None,
            frame_size=None, prefer_human: bool = False, kinds=KINDS,
            use_cache: bool = True) -> Reference:
    """The one calibration reference for ``dataset`` at time ``t``, and its origin.

    The chain, in the order of ``kinds``:

    1. ``quad_file`` - the caller's own quad, which must not be ignored in silence.
    2. the segment artifact - the reference that the per-time rule names for ``t``.
    3. the saved reference file of the dataset - the hand anchors for vod30.
    4. the ``table_refine`` prior - a search centre, not a verified quad.

    The first candidate with a quad that fits ``frame_size`` wins, and every
    candidate that did not is listed in ``rejected``.  The reference that
    ``docs/app-path-refusal.md`` refuses is never selected.  A caller that needs the
    whole time-resolved model takes ``reference.model``.

    ``t`` selects the segment that owns the frame time.  An unknown time takes the
    first segment and says so in ``note``.  ``prefer_human`` takes the artifact's
    own human segment instead, for an audit of one geometry rather than of one time.
    """
    base = Path(root) if root is not None else ROOT
    rejected: list = []
    for kind in kinds:
        if kind == "supplied":
            if quad_file is None:
                continue
            candidate = _checked(_supplied_reference(quad_file, rejected),
                                 frame_size, rejected)
        elif kind == "segment":
            candidate = _checked(_segment_reference(dataset, t, base, artifact,
                                                    prefer_human, use_cache),
                                 frame_size, rejected)
        elif kind == "static":
            candidate = _checked(static_reference(dataset, t, root=base),
                                 frame_size, rejected)
        elif kind == "prior":
            candidate = _checked(_prior_reference(dataset, t, base, rejected),
                                 frame_size, rejected)
        else:
            raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
        if candidate is not None and candidate.found:
            candidate.rejected = list(rejected)
            return candidate
    return Reference(dataset=dataset, kind="none", origin="none", note=NOTE_NO_QUAD,
                     rejected=list(rejected))


def anchors_reference_path(dataset: str = "vod30", path=None) -> str:
    """The anchor file of one dataset.  The only derivation of that name.

    The dataset argument names the file.  A caller may give a different name in
    ``path``, which is an override for a test or for a comparison.  A caller with
    a default of its own can freeze one dataset into that default; this function
    cannot, because the dataset argument is always a value the caller passes.
    """
    if path is not None and str(path) != "":
        try:
            return str(path).format(dataset=dataset)
        except (IndexError, KeyError, ValueError):
            return str(path)
    return ANCHORS_REFERENCE.format(dataset=dataset)


def _resolve_input(where, base: Path) -> Path:
    """``where`` as a path.  A relative path resolves against ``base``."""
    where = Path(where)
    return where if where.is_absolute() else base / where


def _anchors_reference(path, dataset: str, t) -> Reference:
    """The hand anchors of ``dataset``, read as one file of that dataset."""
    reference = read(path, "anchors", t=t)
    reference.dataset = dataset
    reference.kind = "hand_anchors"
    if reference.found:
        reference.note = f"saved hand anchors of {dataset} at t={reference.entry} (first four)"
        reference.evidence = CLOTH_LABELS["hand_anchors"]
    return reference


def _scan_corners_reference(path, dataset: str) -> Reference:
    """The scan's own naive corners, the last step of the rule."""
    reference = read(path, "corners")
    reference.dataset = dataset
    reference.kind = "scan_corners"
    if reference.found:
        reference.note = "scan corners, the last step of the rule"
        reference.evidence = CLOTH_LABELS["scan_corners"]
    return reference


def verified_cloth_quad(dataset: str = "vod30", t=None, root=None, anchors_path=None,
                        scan_corners_path=None) -> Reference:
    """The verified cloth quad of one dataset: the one owner of that rule.

    The order, in the steps of :data:`CLOTH_STEPS`:

    1. the human calibration segment of that dataset - the artifact's own human
       segment, not the segment that owns a time.  One quad weighs every frame
       against one geometry.  A derived or refined segment must not replace a
       human one, so this step asks for the human segment only;
    2. the hand anchors of that dataset - a table keyed by time, and the entry
       nearest ``t`` wins;
    3. the scan corners - the scan's own geometry, the last resort.

    The first step with a quad wins.  Every step that did not answer is listed in
    ``rejected``.

    The return shape is a :class:`Reference`.  ``kind`` is the step that won:
    ``"human_segment"``, ``"hand_anchors"``, ``"scan_corners"``, or ``"none"``.
    ``quad`` is the 4x2 float32 array, and it is ``None`` when no step answered.
    ``origin`` is the file the quad came from and ``entry`` is the segment or the
    key inside it.  ``evidence`` is the :data:`CLOTH_LABELS` string of the step.

    ``dataset`` always names the anchor file, through
    :func:`anchors_reference_path`.  ``anchors_path`` and ``scan_corners_path``
    are overrides for a test or for a comparison; neither one is needed for the
    rule, and a default of a caller cannot freeze a dataset here.  A relative
    ``root`` resolves against this checkout; a relative override path resolves
    against ``root``.

    The two callers keep two differences, and neither difference is the rule.
    ``src.sam3_frame_audit.reference_quad`` reports a label, so it takes
    ``origin``, ``kind``, ``entry`` and ``source`` from the answer.
    ``src.sam3_ball_cache.reference_quad`` answers a bare array or ``None``, so
    it takes ``quad`` from the same answer.
    """
    base = Path(root) if root is not None else ROOT
    rejected: list = []
    step = None
    for step in CLOTH_STEPS:
        if step == "human_segment":
            reference = _segment_reference(dataset, t, base, None, True, True)
        elif step == "hand_anchors":
            path = _resolve_input(anchors_reference_path(dataset, anchors_path), base)
            reference = _anchors_reference(path, dataset, t)
        else:
            path = _resolve_input(scan_corners_path or SCAN_CORNERS, base)
            reference = _scan_corners_reference(path, dataset)
        if reference is not None and reference.found:
            reference.dataset = dataset
            # The step name of ``CLOTH_STEPS`` is the kind of the answer.  The
            # reader that produced the quad names it in ``source`` and ``entry``,
            # so the provenance is still there.
            reference.source = reference.source or reference.kind
            reference.kind = step
            reference.per_time = step == "human_segment"
            reference.rejected = list(rejected)
            return reference
        rejected.append(f"{step}: no quad in {reference.origin if reference else 'none'}")
    return Reference(dataset=dataset, kind="none", origin="none", rejected=rejected,
                     note=f"no verified cloth quad for {dataset}; the steps asked in the "
                          f"order {', '.join(CLOTH_STEPS)} answered nothing")
