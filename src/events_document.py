"""The one module that owns the events documents of a scan.

The served document is the file `events.json` in a scan's output directory
(`out/scan30` for the vod30 scan).  The review rail, the annotator and
`src/store.py` read it, and five modules used to write it.  The file carried no
producer and no version, so a reader could not tell which rule set produced the
rows it read.

This module owns four things, and nothing else:

  * the names of the two documents (`SERVED`, `V2`) and their paths,
  * the shape of a row: an object with a `t` and a `type`,
  * the producer stamp that `write` puts on every row it writes,
  * the version of the document shape.

`write(path, rows, producer=...)` stamps every row with
`{STAMP: {"version": VERSION, "producer": producer}}` and writes a JSON list,
because every reader reads a list.  `read(path)` returns the rows, the status and
the stamp.  A document with no stamp reads as `UNSTAMPED`; a document with more
than one producer, or with a version this module does not write, reads as `MIXED`.
In both cases the producer is *unknown*: this module never guesses it.  An empty
document is `UNSTAMPED`, because a file with no rows has nothing to name.

This module refuses, with a message that says why:

  * a write by a producer that is not a key of `PRODUCERS`,
  * a write of a row that is not an object,
  * a write of a row with no `t` or no `type`,
  * a write of a row that another producer already stamped or that carries a
    newer version,
  * a read of a document that is not a JSON list of rows,
  * a read of a document whose version is newer than `VERSION`.

What this module does not do:

  * it does not change a row value, a detection rule or a threshold,
  * it does not decide which rows are events, and it does not delete a row,
  * it does not serialize a document in one atomic step (`src/atomic_write.py`
    owns that, and the callers here still write in one `open`),
  * it does not make the parent directory of the target,
  * it does not stop a module outside its callers from writing the same path.
    `tests/test_events_document.py` holds the modules in its scope to this
    module; `src/motion_scan.py`, `src/store.py`, `annotator/` and `tests/` still
    name the file themselves.

The callers, one producer each:

  * `src/scan_events.py` (`SCAN_EVENTS`): the coarse phase-1 motion scan
    (`MOTION_THRESH = 4.5`), then SAM3 confirmation of each cluster.
  * `src/rebuild_events_calibrated.py` (`REBUILD_CALIBRATED`): motion peaks
    >= 15.0 merged within 6 s, a SAM3 displacement >= 300 mm verifies a shot.
  * `src/rebuild_events_v2.py` (`REBUILD_V2`): the same peaks on the vod30
    segment homography, and pot counts against their monotone hull.
  * `src/dense_queue.py` (`DENSE_QUEUE`): the dense-track gate output, with ids
    from 9001 that are stable by `provenance.ball_id`.
  * `src/eval_events.py` (`EVAL_EVENTS`): post-hoc gating of the scan
    candidates; only a confirmed candidate is served, and an id the owner saw is
    inherited.

`src/motion_scan.py` names the same documents for the other datasets and does not
import this module.  Its `events_for` (`src/motion_scan.py:2289-2292`) tries
`out/scan30/events.json` for vod30, then `out/scan_<dataset>/events.json`, then
`out/scan<dataset>/events.json`, and falls back to `scan_<dataset>`.  `scan_dir`
follows the same name rule through `src/datasets.py:STATIC_OUT`, so this module
names the document of every dataset without a second table.  The fallback
`scan<dataset>` is a discovery name, not a name rule, and this module does not
use it.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path

try:                                   # `from src import events_document`
    from src.datasets import STATIC_OUT
except ImportError:                    # a script that put src/ itself on the path
    from datasets import STATIC_OUT

__all__ = [
    "VERSION", "STAMP", "ROW_KEYS", "SERVED", "V2", "DOCUMENTS",
    "SCAN_EVENTS", "REBUILD_CALIBRATED", "REBUILD_V2", "DENSE_QUEUE", "EVAL_EVENTS",
    "PRODUCERS", "STAMPED", "MIXED", "UNSTAMPED",
    "Document", "DocumentVersionError", "DocumentShapeError",
    "scan_dir", "document_path", "document_in", "write", "read",
]

ROOT = Path(__file__).resolve().parents[1]

#: The version of the document shape.  Raise it when a reader of the old shape
#: would read the new file wrong, not when a row gains a key.
VERSION = 1
#: The row key that names the document.  No row in this repository uses it.
STAMP = "document"
#: A row is named by its time and by its type.  Every writer in this repository
#: writes both, so a row without one of them is not an event row.
ROW_KEYS = ("t", "type")

#: The served document: what the rail, the annotator and `src/store.py` read.
SERVED = "events.json"
#: The vod30 rebuild document.  Three modules read it (`src/pid_shooter.py`,
#: `src/pid_shooter2.py`, `src/pid_associate.py`); the served document is not it.
V2 = "events_v2.json"
DOCUMENTS = (SERVED, V2)

#: The producers, one for each module that writes rows.  A writer passes its own
#: constant, and `write` refuses a producer that is not here: a writer cannot
#: write rows it cannot name.  The value names the rule set that built the rows.
SCAN_EVENTS = "src/scan_events.py"
REBUILD_CALIBRATED = "src/rebuild_events_calibrated.py"
REBUILD_V2 = "src/rebuild_events_v2.py"
DENSE_QUEUE = "src/dense_queue.py"
EVAL_EVENTS = "src/eval_events.py"
PRODUCERS = {
    SCAN_EVENTS: "phase-1 motion >= 4.5, then SAM3 confirmation of each cluster",
    REBUILD_CALIBRATED: "motion peaks >= 15.0 merged within 6 s, a shot is verified at >= 300 mm",
    REBUILD_V2: "the same peaks on the vod30 segment homography, pots against the monotone hull",
    DENSE_QUEUE: "the dense-track gate output; ids from 9001, stable by provenance.ball_id",
    EVAL_EVENTS: "post-hoc gating of the scan candidates; a confirmed candidate is served",
}

#: The status of a document this module read.
STAMPED = "stamped"        # every row names one producer and the current version
MIXED = "mixed"            # more than one producer, or a version this module does not write
UNSTAMPED = "unstamped"    # no row names a producer, so the producer is unknown


class DocumentShapeError(ValueError):
    """The file is not a JSON list of rows.  It is a ValueError: a caller that
    already tolerates a damaged file keeps tolerating one."""


class DocumentVersionError(Exception):
    """The file is newer than this module.  It is not a ValueError, so a caller
    that swallows a damaged file still stops on a contract it cannot read."""


@dataclass(frozen=True)
class Document:
    """The rows of one document, and who wrote them.

    `status` is `STAMPED`, `MIXED` or `UNSTAMPED`.  `version` and `producer` are
    set only when `status` is `STAMPED`; otherwise the producer is unknown and
    the caller must not guess it.  `producers` lists every producer named in the
    file and `unstamped` counts the rows that name none, so a mixed file says
    what it is mixed of.
    """
    path: Path
    rows: list
    status: str
    version: int | None = None
    producer: str | None = None
    producers: tuple[str, ...] = field(default_factory=tuple)
    unstamped: int = 0

    @property
    def named(self) -> bool:
        """True when every row names one producer and the current version."""
        return self.status == STAMPED

    def describe(self) -> str:
        """One line for a log or a report."""
        if self.status == STAMPED:
            return (f"{self.path}: {len(self.rows)} rows, version {self.version}, "
                    f"producer {self.producer}")
        if self.status == MIXED:
            return (f"{self.path}: {len(self.rows)} rows, MIXED producers "
                    f"{list(self.producers)} and {self.unstamped} unstamped row(s); "
                    f"the producer is unknown")
        return f"{self.path}: {len(self.rows)} rows, no stamp; the producer is unknown"


def _check_name(name: str) -> None:
    if name not in DOCUMENTS:
        raise ValueError(f"{name!r} is not an events document of this module; "
                         f"the documents are {list(DOCUMENTS)}")


def scan_dir(dataset: str = "vod30", root=None) -> Path:
    """The output directory of `dataset`'s scan: `out/scan30` for vod30.

    The folder name comes from `src/datasets.py:STATIC_OUT`, which is the table
    the rest of the project reads; an unknown dataset keeps the
    `scan_<dataset>` name that `src/motion_scan.py` uses for its own scans.
    """
    folder = STATIC_OUT.get(dataset) or f"scan_{dataset}"
    base = ROOT if root is None else Path(root)
    return base / "out" / folder


def document_path(name: str = SERVED, dataset: str = "vod30", root=None) -> Path:
    """The path of the `name` document of `dataset`'s scan.

    `root=None` is the repository root, so the default call is the served
    document.  Give `root` to name the same document under another tree, as
    `src/eval_events.py` does for the browser fixture.
    """
    _check_name(name)
    return scan_dir(dataset, root) / name


def document_in(directory, name: str = SERVED) -> Path:
    """The path of the `name` document inside `directory`.

    Use this when the scan directory is not this repository's default, as for
    `src/scan_events.py --out`.
    """
    _check_name(name)
    return Path(directory) / name


def write(document, rows: Iterable[Mapping], *, producer: str, indent: int = 1) -> Path:
    """Write `rows` to `document` as a JSON list, with every row stamped.

    `producer` is the module that built the rows: one of `PRODUCERS`.  The call
    refuses a producer this module does not know, a row that is not an object, a
    row with no `t` or no `type`, and a row that another producer stamped.

    The rows are copied, not changed: every key and every value the caller wrote
    is written back unchanged, and the stamp is added.  The parent directory of
    `document` must exist.  Returns the path.
    """
    if producer not in PRODUCERS:
        raise ValueError(
            f"{producer!r} is not a producer of the events document; this module knows "
            f"{sorted(PRODUCERS)}.  A writer cannot write rows it cannot name.")
    path = Path(document)
    stamped = _stamped_rows(rows, producer)
    with open(path, "w") as stream:
        json.dump(stamped, stream, indent=indent)
    return path


def _stamped_rows(rows: Iterable[Mapping], producer: str) -> list:
    """The rows with their stamp, or a ValueError that names the first bad row."""
    try:
        rows = list(rows)
    except TypeError:
        raise ValueError(f"the rows of a document are a sequence of objects, not "
                         f"{type(rows).__name__}") from None
    stamped = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"row {index} is a {type(row).__name__}, not an object, "
                             f"so the document cannot name it: {row!r}")
        missing = [key for key in ROW_KEYS if key not in row]
        if missing:
            raise ValueError(f"row {index} has no {', '.join(missing)}: a row is named by "
                             f"its time and its type.  Keys: {sorted(row)}")
        old = row.get(STAMP)
        if isinstance(old, Mapping):
            writer = old.get("producer")
            if writer != producer:
                raise ValueError(f"row {index} is stamped by {writer!r}; {producer!r} cannot "
                                 f"name a row another producer built")
            version = old.get("version")
            if isinstance(version, int) and version > VERSION:
                raise ValueError(f"row {index} is stamped version {version}, newer than "
                                 f"{VERSION}: this module cannot write it")
        named = dict(row)
        named[STAMP] = {"version": VERSION, "producer": producer}
        stamped.append(named)
    return stamped


def read(document) -> Document:
    """The rows of `document` and the stamp on them.

    Raises `DocumentShapeError` when the file is not a JSON list, and
    `DocumentVersionError` when a row names a version newer than `VERSION`.  A
    row with no stamp, and a row that is not an object, are returned as they are:
    the status of the document says that they name no producer.
    """
    path = Path(document)
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise DocumentShapeError(
            f"{path}: an events document is a JSON list of rows; this file holds a "
            f"{type(data).__name__}")
    versions, producers, unstamped = set(), set(), 0
    for index, row in enumerate(data):
        stamp = row.get(STAMP) if isinstance(row, Mapping) else None
        if not isinstance(stamp, Mapping):
            unstamped += 1
            continue
        version = stamp.get("version")
        if isinstance(version, int) and version > VERSION:
            raise DocumentVersionError(
                f"{path}: row {index} is stamped document version {version}, newer than this "
                f"module knows ({VERSION}); update src/events_document.py before reading it")
        versions.add(version)
        producers.add(stamp.get("producer"))
    if not producers:
        status = UNSTAMPED
    elif unstamped == 0 and len(producers) == 1 and versions == {VERSION}:
        status = STAMPED
    else:
        status = MIXED
    single = status == STAMPED
    return Document(path=path, rows=data, status=status,
                    version=VERSION if single else None,
                    producer=next(iter(producers)) if single else None,
                    producers=tuple(sorted(str(name) for name in producers)),
                    unstamped=unstamped)
