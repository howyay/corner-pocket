"""The one module that owns the document stamp protocol.

`src/sam3_artifact.py` stamps the ball rows of `sam3_results.json`.
`src/events_document.py` stamps the rows of `events.json`.  The two documents
hold different rows, and one row shape differs from the other.  The two of them
still carry one stamp, and both readers must answer one question in one way.

Before this module, each reader held its own copy of the protocol, and the two
copies drifted.  One row stamped `{"document": {"version": 1, "producer":
"src/gone.py"}}` read `mixed` with no producer in `src/sam3_artifact.py`.  The
same stamp read `stamped` with the producer `src/gone.py` in
`src/events_document.py`, though its own table did not hold that name.

The protocol is small:

  * `STAMP` is the row key that holds the stamp of a row,
  * the stamp is an object with the keys `version` and `producer`,
  * `VERSION` is the version of the stamp shape,
  * `PRODUCERS` maps each producer name to the rule set of that name.

The rule, in one sentence: a row is *named* only when its stamp is an object,
its version is `VERSION`, and its producer is a name of the producer set of the
document.

`classify` applies that rule to one stamp, and it returns `NAMED`, `UNSTAMPED`
or `FOREIGN`.  `status` applies that rule to the counts of a whole document.  A
document is `STAMPED` only when every row is named and every row names the same
producer.  A missing name, a name outside the set, and another version are
`FOREIGN`, so the document reads `MIXED` and its producer stays unknown.  A
reader never guesses a producer.

This module is a leaf.  It imports nothing from `src/`, so both readers import
it without a cycle.

What this module does not own:

  * the row keys of a document: `ROW_KEYS` stays in each reader, because the
    two documents name a row in different ways,
  * the document file names, the paths, and the shape of a row or of a list of
    rows,
  * the exception type of a reader for a version that is newer than `VERSION`.

`tests/test_document_stamp.py` holds both readers to this module, and it refuses
a second definition of a protocol name under `src/`.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

__all__ = [
    "VERSION", "STAMP", "STAMPED", "MIXED", "UNSTAMPED", "NAMED", "FOREIGN",
    "SCAN_EVENTS", "REBUILD_CALIBRATED", "REBUILD_V2", "DENSE_QUEUE", "EVAL_EVENTS",
    "PRODUCERS", "BALL_ROW_PRODUCERS",
    "is_producer", "is_newer", "classify", "status",
]

#: The version of the stamp shape.  Raise it when a reader of the old shape
#: would read the new file wrong, not when a row gains a key.
VERSION = 1

#: The row key that holds the stamp of a row.
STAMP = "document"

#: The status of a document that a reader read.
STAMPED = "stamped"        # every row is named, and every row names one producer
MIXED = "mixed"            # a foreign stamp, a stray row, or more than one producer
UNSTAMPED = "unstamped"    # no row carries a stamp, so the producer is unknown

#: The verdict of one row stamp.
NAMED = "named"            # an object, at VERSION, with a producer of the document
FOREIGN = "foreign"        # any other stamp object: the reader cannot name the row
#: A row with no stamp object is `UNSTAMPED`, the third verdict of `classify`.

#: The producers, one for each module that writes stamped rows.  A writer passes
#: its own constant, and a write refuses a producer that is not here: a writer
#: cannot write rows it cannot name.  The value names the rule set of the name.
SCAN_EVENTS = "src/scan_events.py"
REBUILD_CALIBRATED = "src/rebuild_events_calibrated.py"
REBUILD_V2 = "src/rebuild_events_v2.py"
DENSE_QUEUE = "src/dense_queue.py"
EVAL_EVENTS = "src/eval_events.py"
PRODUCERS = {
    SCAN_EVENTS: "phase-1 motion >= 4.5, then SAM3 confirmation; a ball row carries the "
                 "homography of the scan's own corners.json",
    REBUILD_CALIBRATED: "motion peaks >= 15.0 merged within 6 s, a shot is verified at "
                        ">= 300 mm; a ball row recomputes table_mm from out/calib_final.json",
    REBUILD_V2: "the same peaks on the vod30 segment homography, pots against the monotone hull",
    DENSE_QUEUE: "the dense-track gate output; ids from 9001, stable by provenance.ball_id",
    EVAL_EVENTS: "post-hoc gating of the scan candidates; a confirmed candidate is served",
}

#: The producers that write ball rows into the SAM3 artifact.  The other three
#: producers write event rows only, so `src/sam3_artifact.py` refuses them.
BALL_ROW_PRODUCERS = (SCAN_EVENTS, REBUILD_CALIBRATED)


def is_producer(name, known: Iterable[str] = PRODUCERS) -> bool:
    """True when `name` is a producer name of `known`."""
    return isinstance(name, str) and name in known


def is_newer(version) -> bool:
    """True when `version` is an integer newer than `VERSION`.

    A reader stops on a newer stamp, and it keeps its own exception type for
    that stop.
    """
    return isinstance(version, int) and version > VERSION


def classify(entry, known: Iterable[str] = PRODUCERS) -> str:
    """The verdict of one row stamp: `NAMED`, `UNSTAMPED` or `FOREIGN`.

    `entry` is the value of the `STAMP` key of the row, or None when the row
    holds no stamp.  Only a stamp that passes the whole rule is `NAMED`.
    """
    if not isinstance(entry, Mapping):
        return UNSTAMPED
    if entry.get("version") != VERSION:
        return FOREIGN
    name = entry.get("producer")
    if not is_producer(name, known):
        return FOREIGN
    return NAMED


def status(producers: Iterable[str], *, unstamped: int, foreign: int) -> tuple[str, str | None]:
    """The status of a document, and its producer when it names one.

    `producers` holds the names that `classify` called `NAMED`, `unstamped`
    counts the rows with no stamp, and `foreign` counts the rows with a stamp
    that the reader cannot name.  The producer is None unless the status is
    `STAMPED`.
    """
    names = {name for name in producers if is_producer(name)}
    if names and not unstamped and not foreign and len(names) == 1:
        return STAMPED, next(iter(names))
    if not names and not foreign:
        return UNSTAMPED, None
    return MIXED, None
