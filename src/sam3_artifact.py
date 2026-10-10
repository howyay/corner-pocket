"""The one module that owns the SAM3 ball artifact of a scan.

The artifact is the file `sam3_results.json` in the output directory of a scan:
`out/scan30/sam3_results.json` for the vod30 scan.  The file is a JSON object
that maps a time to the list of the balls SAM3 found in that frame.  A ball row
is a JSON object with the keys `img`, `r`, `score` and `table_mm`.

Two modules built the file, and the file named neither of them:

  * `src/scan_events.py` measured a frame with the camera model and wrote the
    table position through the homography of the scan's own `corners.json`;
  * `src/rebuild_events_calibrated.py` kept the pixels and the scores, and
    recomputed every `table_mm` from the calibrated homography in
    `out/calib_final.json`.

`src/sam3_ball_cache.py:40` and `src/eval_events.py:150` therefore declared the
file read-only, while those two modules rewrote it in place.  A reader could not
tell a millimetre value that the camera model measured from one that a
calibration recomputed.  Measured on the file of 2026-09-03: all 270 rows equal
the value that `out/calib_final.json` recomputes, so the camera model did not
write the millimetres of that file.

This module owns the name, the shape, the version and the producers.  A writer
calls `write`, which stamps the rows and writes them through
`src/atomic_write.py`, and which refuses a row it cannot name.  A reader calls
`read`, which returns the frames unchanged and reports the producers that the
rows name.

The stamp of a ball row is `{"document": {"version": 1, "producer": "src/..."}}`.
The stamp is inside the row, not beside it: six of the eight readers iterate the
top-level object and call `float(key)` on every key, so a top-level stamp key
would stop them.  A frame with no ball row carries no stamp.  It holds no
`table_mm`, so it names no producer, and it is not a lie about who measured it.

This module does not make the parent directory of `document`.  It also does not
stop a module outside the four callers from naming the same path:
`src/ball_fp_audit.py`, `src/tiny_ball_net.py`, `src/fast_ball_labels.py`,
`src/motion_scan.py`, `src/rebuild_events_v2.py` and `annotator/unified_server.py`
still read the file by name.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path

try:                                   # `from src import sam3_artifact`
    from src.datasets import STATIC_OUT
except ImportError:                    # a script that put src/ itself on the path
    from datasets import STATIC_OUT

try:                                   # `from src import sam3_artifact`
    from src.atomic_write import write_atomic
except ImportError:                    # a script that put src/ itself on the path
    from atomic_write import write_atomic

__all__ = [
    "VERSION", "STAMP", "ROW_KEYS", "ARTIFACT",
    "CAMERA_MODEL", "REBUILD_CALIBRATED", "PRODUCERS",
    "STAMPED", "MIXED", "UNSTAMPED",
    "Artifact", "ArtifactVersionError", "ArtifactShapeError",
    "artifact_path", "artifact_in", "owns", "write", "stamp", "read",
]

ROOT = Path(__file__).resolve().parents[1]

#: The version of the artifact shape.  Raise it when a reader of the old shape
#: would read the new file wrong, not when a ball row gains a key.
VERSION = 1

#: The row key that names the producer of the row.  No ball row of this
#: repository used it before this module.
STAMP = "document"

#: A ball row is named by its pixel position and by its table position.  The
#: camera model writes both, and the calibrated rebuild recomputes the second,
#: so a row that carries one of them without the other is not a ball row.
ROW_KEYS = ("img", "table_mm")

#: The artifact file name, inside the output directory of a scan.
ARTIFACT = "sam3_results.json"

#: The producers, one for each module that writes ball rows.  A writer passes its
#: own constant, and `write` refuses a producer that is not here: a writer cannot
#: write rows it cannot name.  The value names the rule set that built the rows.
CAMERA_MODEL = "src/scan_events.py"
REBUILD_CALIBRATED = "src/rebuild_events_calibrated.py"
PRODUCERS = {
    CAMERA_MODEL: "SAM3 masks under the homography of the scan's own corners.json; "
                  "table_mm is that homography applied to the mask centre",
    REBUILD_CALIBRATED: "table_mm recomputed from out/calib_final.json (H_mm_to_px, "
                        "inverted); the pixels and the scores stay as SAM3 measured them",
}

#: The status of an artifact this module read.
STAMPED = "stamped"        # every ball row names one producer and the current version
MIXED = "mixed"            # more than one producer, a foreign stamp, or a stray row
UNSTAMPED = "unstamped"    # no ball row names a producer, so the producer is unknown


class ArtifactShapeError(ValueError):
    """The file is not a JSON object of frame lists.  It is a ValueError: a caller
    that already tolerates a damaged cache keeps tolerating one."""


class ArtifactVersionError(Exception):
    """The file is newer than this module.  It is not a ValueError, so a caller
    that swallows a damaged cache still stops on a shape it cannot read."""


@dataclass(frozen=True)
class Artifact:
    """The frames of one artifact, and who wrote the ball rows.

    `frames` is the frame map exactly as the file holds it: the keys stay the
    strings of the file, and every ball row keeps every key and every value,
    including its stamp.  `status` is `STAMPED`, `MIXED` or `UNSTAMPED`.
    `version` and `producer` are set only when `status` is `STAMPED`; otherwise
    the producer of the file is unknown and a caller must not guess it.
    `empty` counts the frames that hold no ball row, so they name no producer.
    `unstamped` counts the ball rows that name no producer, and `foreign` counts
    the ball rows that carry a stamp this module does not know.
    """
    path: Path
    frames: dict
    status: str
    balls: int = 0
    version: int | None = None
    producer: str | None = None
    producers: tuple = field(default_factory=tuple)
    empty: int = 0
    unstamped: int = 0
    foreign: int = 0

    @property
    def named(self) -> bool:
        """True when every ball row names one producer at the current version."""
        return self.status == STAMPED

    def describe(self) -> str:
        """One line for a log or a report."""
        head = (f"{self.path}: {self.balls} ball rows in {len(self.frames)} frames "
                f"({self.empty} empty)")
        if self.status == STAMPED:
            return f"{head}, version {self.version}, producer {self.producer}"
        if self.status == MIXED:
            parts = []
            if self.producers:
                parts.append(f"producers {sorted(self.producers)}")
            if self.unstamped:
                parts.append(f"{self.unstamped} ball row(s) with no stamp")
            if self.foreign:
                parts.append(f"{self.foreign} ball row(s) with a stamp this module does not know")
            return f"{head}, " + ", ".join(parts) + "; read a row's own stamp"
        return f"{head}, no stamp; the producer is unknown"


def artifact_path(dataset: str = "vod30", root=None) -> Path:
    """The path of `dataset`'s artifact: `out/scan30/sam3_results.json` for vod30.

    The folder name comes from `src/datasets.py:STATIC_OUT`, which is the table
    the rest of the project reads; an unknown dataset keeps the `scan_<dataset>`
    name that `src/motion_scan.py` uses for its own scans.
    """
    folder = STATIC_OUT.get(dataset) or f"scan_{dataset}"
    base = ROOT if root is None else Path(root)
    return base / "out" / folder / ARTIFACT


def artifact_in(directory) -> Path:
    """The path of the artifact inside `directory`.

    Use this when the scan directory is not this repository's default, as for
    `src/scan_events.py --out`.
    """
    return Path(directory) / ARTIFACT


def owns(path) -> bool:
    """True when `path` names this artifact, so a reader reads it through here.

    The test is the file name alone.  A reader holds a path from a command line
    or from `src/datasets.py`, and this module is the only owner of that name.
    """
    return Path(path).name == ARTIFACT


def _check_producer(producer: str) -> None:
    if producer not in PRODUCERS:
        raise ValueError(
            f"{producer!r} is not a producer of the SAM3 artifact; this module knows "
            f"{sorted(PRODUCERS)}.  A writer cannot write rows it cannot name.")


def _check_row(ball, where: str):
    """One ball row, checked.  Returns its stamp when it carries one."""
    if not isinstance(ball, Mapping):
        raise ValueError(f"{where} is a {type(ball).__name__}, not a ball row object")
    for key in ROW_KEYS:
        if key not in ball:
            raise ValueError(
                f"{where} has no {key!r}; a ball row of {ARTIFACT} is a pixel position "
                f"and a table position, so it needs {list(ROW_KEYS)}")
    entry = ball.get(STAMP)
    if entry is not None and not isinstance(entry, Mapping):
        raise ValueError(
            f"{where} carries a {type(entry).__name__} as its {STAMP!r} stamp, not an object")
    return entry


def _checked_frames(frames: Mapping, producer: str, keep_stamps: bool) -> dict:
    """The frames with the stamps that `write` must put on them."""
    if not isinstance(frames, Mapping):
        raise ValueError(
            f"the frames of {ARTIFACT} are a JSON object of frame lists, not a "
            f"{type(frames).__name__}")
    out = {}
    for key, balls in frames.items():
        try:
            float(key)
        except (TypeError, ValueError):
            raise ValueError(
                f"frame key {key!r} is not a time; the keys of {ARTIFACT} are the times "
                f"of the measured frames, and `float(key)` must read one") from None
        if not isinstance(balls, list):
            raise ValueError(f"frame {key!r} holds a {type(balls).__name__}, not a list "
                             f"of ball rows")
        rows = []
        for index, ball in enumerate(balls):
            where = f"row {index} of frame {key!r}"
            entry = _check_row(ball, where)
            if not keep_stamps:
                rows.append({**ball, STAMP: {"version": VERSION, "producer": producer}})
                continue
            if entry is None:
                rows.append(dict(ball))
                continue
            version = entry.get("version")
            if isinstance(version, int) and version > VERSION:
                raise ArtifactVersionError(
                    f"{where} names version {version}, and this module writes version "
                    f"{VERSION}; a newer file needs a newer writer")
            name = entry.get("producer")
            if version != VERSION or name not in PRODUCERS:
                raise ValueError(
                    f"{where} is stamped {dict(entry)!r}, and this module writes version "
                    f"{VERSION} for {sorted(PRODUCERS)}.  A caller that copies a row it "
                    f"did not build must read it through `read` first.")
            rows.append(dict(ball))
        out[key] = rows
    return out


def write(document, frames: Mapping, *, producer: str, keep_stamps: bool = False,
          indent: int | None = 1) -> Path:
    """Write `frames` to `document` as a JSON object of frame lists.

    `producer` is the module that built the rows: one of `PRODUCERS`.  The call
    refuses a producer this module does not know, a frame map that is not an
    object, a frame key that is not a time, a frame that is not a list, a ball row
    that is not an object, a ball row with no `img` or no `table_mm`, and a stamp
    that is not an object or that names a version this module does not write.

    Every ball row is copied, not changed: every key and every value the caller
    wrote is written back unchanged.

    The default stamps every ball row with `producer`.  Use the default when the
    call built or recomputed every value it writes, as
    `src/rebuild_events_calibrated.py` does.

    `keep_stamps=True` keeps the stamp of every ball row as the caller passes it,
    and leaves a row that carries none without one.  Use it when the call also
    copies a row it did not build, as `src/scan_events.py` does: stamp the rows
    of this call with `stamp(rows, producer)` first, and pass every copied row
    exactly as `read` returned it.  A copied row that carries no stamp stays
    without one, because this module never guesses the producer of a value it did
    not build.  `producer` still names the caller here: the call refuses a
    builder this module does not know, and a stamp this module cannot read.

    The parent directory of `document` must exist.  The bytes reach the file in
    one atomic step, because `src/atomic_write.py` owns that step: a write that
    fails leaves the old file in place and removes its temporary file.  Returns
    the path.  `indent=None` writes the compact form that `src/scan_events.py`
    wrote before this module existed; `indent=1` writes the form of
    `src/rebuild_events_calibrated.py`.
    """
    _check_producer(producer)
    path = Path(document)
    stamped = _checked_frames(frames, producer, keep_stamps)
    write_atomic(path, lambda stream: json.dump(stamped, stream, indent=indent))
    return path


def stamp(rows: Iterable[Mapping], producer: str) -> list:
    """`rows` with the stamp of `producer`, for a caller that built new rows.

    Use this for the rows of one call, then pass the whole frame map to `write`
    with `keep_stamps=True`.  Every row is copied, not changed.

    The call refuses a producer this module does not know, a row that is not an
    object, a row with no `img` or no `table_mm`, and a row that already carries
    the stamp of another producer, because a new row cannot be the work of a
    module that did not build it.
    """
    _check_producer(producer)
    out = []
    for index, ball in enumerate(rows):
        where = f"row {index}"
        entry = _check_row(ball, where)
        if entry is not None and entry.get("producer") not in (None, producer):
            raise ValueError(
                f"{where} is stamped {entry.get('producer')!r}, and {producer!r} cannot "
                f"stamp a row that another producer built")
        out.append({**ball, STAMP: {"version": VERSION, "producer": producer}})
    return out


def read(document) -> Artifact:
    """The frames of `document`, with the producers that the ball rows name.

    The frames are returned unchanged: a caller that writes them back writes the
    same bytes, and a caller that reads a value reads the value in the file.  The
    call refuses a file that is not a JSON object of frame lists, a frame that is
    not a list, and a ball row that names a version newer than `VERSION`.

    A frame with no ball row counts in `empty`.  A ball row with no stamp counts
    in `unstamped`.  A ball row whose stamp this module does not know counts in
    `foreign`.  This module never guesses a producer.
    """
    path = Path(document)
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ArtifactShapeError(
            f"{path}: the frames of {ARTIFACT} are a JSON object of frame lists, not a "
            f"{type(data).__name__}")
    producers: set[str] = set()
    balls = empty = unstamped = foreign = 0
    for key, rows in data.items():
        if not isinstance(rows, list):
            raise ArtifactShapeError(
                f"{path}: frame {key!r} holds a {type(rows).__name__}, not a list of "
                f"ball rows")
        if not rows:
            empty += 1
            continue
        for index, ball in enumerate(rows):
            balls += 1
            entry = ball.get(STAMP) if isinstance(ball, Mapping) else None
            if not isinstance(entry, Mapping):
                unstamped += 1
                continue
            version, name = entry.get("version"), entry.get("producer")
            if isinstance(version, int) and version > VERSION:
                raise ArtifactVersionError(
                    f"{path}: row {index} of frame {key!r} names version {version}, and "
                    f"this module reads version {VERSION}; a newer file needs a newer "
                    f"reader")
            if version == VERSION and name in PRODUCERS:
                producers.add(name)
            else:
                foreign += 1
    if producers and not unstamped and not foreign and len(producers) == 1:
        status, producer = STAMPED, next(iter(producers))
    elif not producers and not foreign:
        status, producer = UNSTAMPED, None
    else:
        status, producer = MIXED, None
    return Artifact(path=path, frames=data, status=status, balls=balls,
                    version=VERSION if status == STAMPED else None, producer=producer,
                    producers=tuple(sorted(producers)), empty=empty,
                    unstamped=unstamped, foreign=foreign)
