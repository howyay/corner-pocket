"""The one owner of the seconds that are read either side of an event time.

An event time is a claim about *when* the ball moved.  Three spans are read around
such a time, and they are different numbers on purpose:

  * the **served window**: :data:`EVENT_BEFORE_S` = 1.5 s before the time and
    :data:`EVENT_AFTER_S` = 2.5 s after it.  It is asymmetric and 4.0 s wide.  The
    console clips exactly this span (``annotator/app.js`` holds
    ``CLIP_BEFORE_S``/``CLIP_AFTER_S`` for it), so it is the span a viewer of a
    served event really sees.  Three modules judge a reading over it:
    ``src/motion_scan.py`` (the report window), ``src/timing_verify.py`` (the motion
    proxy per event) and ``src/eval_events.py`` (the census around a potential
    shot).  ``src/timing_verify.py`` keeps its own two names, because
    ``tests/test_timing_verify.py`` holds ``annotator/app.js`` to them; both names
    read this module now.  ``annotator/unified_server.py`` answers ``/api/clip`` with
    this span: a caller that names no window gets these two numbers, and a window a
    caller does name is clamped to ``[CLIP_MIN_S, CLIP_MAX_S]`` - a bound on what a
    request may ask for, which is a different decision from the span itself.

  * the **symmetric calibration half**: :data:`CONTROL_HALF_S` = 2.5 s.  The
    calibration reads ``[t - half, t + half]`` around each control time, so a
    control window carries the same amount of data on each side of its own time.
    It is 5.0 s wide, not 4.0 s.  The help text of ``--control-half-s`` says as much
    out loud, because a reader who takes this half for the judged window builds the
    floor from the wrong data.

  * the **tolerance**: :data:`AT_TOL_S` = 0.5 s.  A peak inside this many seconds of
    the served time is called "at the served time"; a peak further away is called
    "only elsewhere".  A tolerance is compared against an offset and is never
    decoded, so it is not a window of frames.

:data:`CONTROL_HALF_S` and :data:`EVENT_AFTER_S` are both 2.5 s in this checkout.
That is a coincidence, not a shared decision: a change to the served window must not
move the calibration, and a change to the calibration must not move the served
window.

Three numbers in the same modules are **not** owned here.  A later reader must not
merge them into the three above:

  * ``--event-half-s`` = 0.5 s (``src/motion_scan.py``, the ``channels``
    sub-command) is the half of the probe window a candidate onset is measured in.
    It equals :data:`AT_TOL_S` today and answers a different question.
  * ``decay_shape(window_s=1.5)`` (``src/motion_scan.py``) is the span *after* an
    onset over which the raw signal's decay is described.  It looks forward only.
  * ``prediction_residuals(max_gap_s=2.5)`` (``src/ball_association_audit.py``) is
    the largest gap two predictions may have and still be paired.

One repair stands behind this module, and it is already in the tree: until
``b87e47e`` (2026-10-09) the control profile read a hard-coded ``2.5, 2.5`` while
the event profile read ``--before``/``--after`` (1.5/2.5), so a control was judged
over 1.0 s more data on its left than the event it judged.  ``judge_window()`` in
``src/motion_scan.py`` hands one pair to both now, and ``control_row()`` takes that
pair as an argument.  This module gives the pair a name; it does not repeat the
repair.
"""
from __future__ import annotations

__all__ = ["EVENT_BEFORE_S", "EVENT_AFTER_S", "CONTROL_HALF_S", "AT_TOL_S"]

#: Seconds of window before an event time, in the served window.  ``annotator/app.js``
#: clips the same span, so this number is part of the console contract as well.
EVENT_BEFORE_S = 1.5

#: Seconds of window after an event time, in the served window.
EVENT_AFTER_S = 2.5

#: Half of the symmetric window a calibration reads around one control time.  It is
#: not the judged window: the judged window is served and asymmetric.
CONTROL_HALF_S = 2.5

#: How near the peak of a window may sit to the served time and still count as
#: "at the served time".
AT_TOL_S = 0.5
