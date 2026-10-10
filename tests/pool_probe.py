"""How these tests wait for a server to settle, and what they grade when they do.

``BoundedHTTPServer`` publishes its own accounting: ``pool_state()``
(``annotator/unified_server.py:2396``, ``pool_state()``) reports how many connections each of the two
budgets is holding right now.  A test about those budgets can assert that
directly, and this module is the one place the suite says how it waits for it.

Two instruments are deliberately absent from it.

A wall clock around a request grades the host, not the server.  This suite runs
on shared machines, and the listener makes a funding promise - which budget a
connection spends - not a latency promise.  A call that does queue behind a
budget that never frees does not answer slowly, it does not answer at all, so
the client's own timeout is the whole deadline a test needs, and it fails by
naming the path.

A fixed ``time.sleep`` as "settle time" grades nothing.  It is either longer
than the machine needed - every run pays it - or shorter, and then a correct
server fails on a busy host.  Polling for the state the test is about to assert
costs the machine's real settling time and no more.
"""
import threading
import time

#: How long a settled state is given to arrive before the caller is shown what it got.
SETTLE_TIMEOUT = 5.0

#: How often the state is re-read while it is still moving.
SETTLE_STEP = 0.02


def settled(server, expected, timeout=SETTLE_TIMEOUT):
    """Poll ``server.pool_state()`` until it is exactly ``expected``; return the last read.

    Returning the last state read - which is ``expected`` when it arrived - lets
    the caller assert on it and so name the state that never came.
    """
    deadline = time.monotonic() + timeout
    state = server.pool_state()
    while state != expected and time.monotonic() < deadline:
        time.sleep(SETTLE_STEP)
        state = server.pool_state()
    return state


def settled_count(read, timeout=SETTLE_TIMEOUT, repeats=3):
    """Poll ``read()`` until it repeats ``repeats`` times; return that value.

    A count that is still moving has not settled yet, and one sleep cannot tell a
    settled count from a climbing one.  A count that climbs and then stops - the
    shape of a leak - settles at the wrong number, which is the number the caller
    then asserts on.
    """
    deadline = time.monotonic() + timeout
    previous = None
    seen = 0
    while time.monotonic() < deadline:
        current = read()
        seen = seen + 1 if current == previous else 1
        if seen >= repeats:
            return current
        previous = current
        time.sleep(SETTLE_STEP)
    return read() if previous is None else previous


def handler_threads():
    """The live handler threads, by the name ``ThreadingMixIn`` gives them.

    ``threading.active_count()`` counts every thread in the interpreter, so any
    unrelated thread that starts or dies moves the number - either way, with
    nothing to do with this server.  Counting handler threads by name is what
    tests/test_clock_api.py:252 already does to watch the same pool.
    """
    return [thread for thread in threading.enumerate()
            if 'process_request_thread' in thread.name and thread.is_alive()]
