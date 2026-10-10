"""The one owner of the retention bound of the operations event log.

The operations log is kept twice over: as a document
(`out/corner-pocket/state.json`, and the same document text in the `json_documents`
table when Postgres is the store) and as one row per event in the `ops_events` table.
The two sides hold different history on purpose:

  * the document shows the newest `MAX_EVENTS` rows, so the file a browser downloads
    and the document the database stores stay small;
  * the table keeps every row ever written, so the club's audit trail is complete.

`MAX_EVENTS` is the bound of the document side.  Three writers trim to it and one
reader asks the database for it:

  * `annotator/operations.py` (`Operations._commit`): the file the annotator writes;
  * `src/store_pg.py` (`PostgresStore._save`): the same commit path on Postgres;
  * `src/enroll_from_tracklet.py` (`_roster_payload`): the roster a caller writes;
  * `src/store_import.py` (`OperationsSet.render`): the table read back as a document,
    through `LIMIT %s` with this value as the parameter.

`trim(events)` answers the rows the document shows: the newest `MAX_EVENTS`, oldest
first.  It returns a new list and changes no row, because every writer spliced a new
list before this module existed; a log shorter than the bound is returned whole.

`src/events_document.py` is not this owner.  It owns the scan-event documents
(`events.json`, `events_v2.json`), whose rows carry `t` and `type`; its own scope says
"it does not decide which rows are events, and it does not delete a row"
(`src/events_document.py:37`), and an operations event carries `revision`, `action` and
`context` and no `type`, so `events_document.write` refuses it.

The `ops_events` table is not bounded here: `src/store_import.py:220-224` inserts every
row of the document.  `src/store_check.py:65-66` still spells the number next to the
live table, inside a `LIMIT`; that file is outside this change, and
`tests/test_event_retention.py` records the spelling instead of hiding it.
"""
from __future__ import annotations

__all__ = ["MAX_EVENTS", "trim"]

#: How many of the newest events the operations document shows.  The log is
#: append-only in the `ops_events` table; the document is the bounded view of it.
MAX_EVENTS = 500


def trim(events) -> list:
    """The rows the operations document shows: the newest `MAX_EVENTS`, oldest first."""
    return list(events)[-MAX_EVENTS:]
