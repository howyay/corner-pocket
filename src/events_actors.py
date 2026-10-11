"""One rule joins an event to its actor: the file out/events_actors.json.

The re-identification pass writes one row per sampled time, and the event scan
writes its own times.  The two readers of the file - the review API
(annotator/unified_server.py) and the legacy review server (annotator/server.py) -
held two rules for that join: one compared the times with a 0.01 s tolerance, and
the other rounded both times to one decimal place and matched the buckets.  The
two rules answer the same way for a row that sits on its event, and differ for a
row that sits between two of them.

ACTOR_MATCH_TOLERANCE is the one tolerance now.  It is the old bucket width of the
legacy server, in seconds, because that server keeps its answer for the records
that exist today: the two rules hold the same answer for all 57 rows of
out/events_actors.json, and on the events of out/scan30/events.json that answer is
no join at all.  The tolerance is measured on both sides of one boundary in
tests/test_unified_server.py.

The entry point is join_events_to_actors.  It takes the events and the actor rows,
and it answers {event id as a string: the actor row}.  Both readers call it, so
one event gets one actor on both routes.
"""
ACTOR_MATCH_TOLERANCE = 0.1


def join_events_to_actors(events, rows):
    """Map each event id to the actor row within ACTOR_MATCH_TOLERANCE seconds.

    A row matches the first event whose time is inside the tolerance, in the order
    of ``events``.  An event with no row inside the tolerance is absent from the
    answer, and the routes above report no actor for it.
    """
    joined = {}
    for event in events or []:
        match = next((row for row in rows or [] if abs(row['t'] - event['t']) <= ACTOR_MATCH_TOLERANCE), None)
        if match:
            joined[str(event['id'])] = match
    return joined
