"""The frame rate a recording is read at when its container reports no rate.

Why this module exists
----------------------
The name ``FPS_FALLBACK`` stood in ``tools/playfield_harness.py``.  Twenty-four
other sites then spelled the same number again:

* the ``or`` tail with the float spelling, sixteen sites in ten ``src/`` modules;
* the ``or`` tail with the integer spelling, five sites in four ``src/`` modules;
* the ``else`` tail of a rate refusal, two sites in the two served
  ``annotator/`` modules;
* one plain default assignment, in ``src/eval_events.py``.

A tool module holds no reading that a served module may import.  The number moved
to this module, and every reader imports the one name.

This module imports nothing, and it reads no container, no dataset and no report.
So every module of ``src/`` and ``annotator/`` can import it, and no import cycle
starts.

What this number is not
-----------------------
A site that means another number keeps its own literal and its own comment:

* the measured rate of the ``vod30`` clips;
* ``FPS_BAR`` in ``src/tiny_ball_net.py``, a latency bar and not a rate of a file;
* a number of seconds, for example a duration or a sample step;
* a number of pixels, for example a match threshold or a pose speed.

The guard of this rule is ``tests/test_playfield_harness.py``.  It walks the
source of the four shipped packages with ``ast`` and names every site that spells
the fallback inline.

The one spelling of the value in this file is the definition below.
"""

#: The frame rate a container that reports no rate is read at.  One home: a second
#: copy is a second answer to the question "at what rate was this measured".
FPS_FALLBACK = 30.0
