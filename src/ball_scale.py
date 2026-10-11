"""One home for the ball's size: the millimetre width and the measured pixels.

Why this module exists
----------------------
Two modules stated the ball's pixel size and they disagreed.  ``src/motion_scan.py``
said 18.9 px at the native frame.  ``src/shot_pot_gate.py`` said 18.4 px, and 18.4
matches no file in this tree.  Two more modules stated the ball's width as a
rounded guess (about 20 px, about 8 px) against a measurement of 14.2 px at the
working size.  Every length bar of the gate is a multiple of this one number, so
one home is the only way the gate and the scan can agree.

This module is a leaf: it imports ``math`` and nothing else.  ``src/motion_scan.py``
costs 1.063 s to import (cv2, numpy, torch), so a length constant must not live
there.

The measured value at the native frame
--------------------------------------
The measurement is the SAM3 ball radii of ``out/scan30/sam3_results.json``: 270
radii over 56 frames of the vod30 native 1280x720 recording.  The exact command:

    cd /home/haoye/projects/pool
    PYTHONPATH=. .venv/bin/python -c "
    import json, statistics as st
    d = json.load(open('out/scan30/sam3_results.json'))
    rs = sorted(float(b['r']) for frame in d.values() for b in frame)
    n = len(rs)
    print('frames', len(d), 'radii', n)
    print('median r %.3f -> diameter %.2f' % (st.median(rs), 2*st.median(rs)))"

Answer: ``frames 56 radii 270``, ``median r 9.450``, diameter ``18.90`` px.

The quantile rule of this module
--------------------------------
A quantile here is the nearest-rank order statistic of the sorted radii::

    p in [0, 1];  k = max(1, ceil(p * n));  radius = radii[k - 1]

That rule answers radius 6.9 px at p10 (diameter 13.8 px) and radius 12.4 px at
p90 (diameter 24.8 px).  Two other rules answer the p90 radius differently:
the index ``int(0.9 * n)`` answers 12.5 px (24.99 px), and linear interpolation
answers 12.41 px (24.82 px).  The difference between the rules is one sample of
270, and it is not worth a decision: the p90 ball is a sensitivity footprint in
``src/motion_scan.py``, never a gate bar.  One rule, stated here, is what matters.

The one owner of the working frame
-----------------------------------
Twelve modules bound the working size 960x540 again, under six names, and two
comments named a module that is not this one.  The frame the pipeline works in
is this module's fact, because the ball's pixel size scales with it.  A reader
now binds ``WORKING_FRAME`` or derives its two integers from it.  The scan
resize, the census, the dense queue, the trained net's production size and the
annotator's ball stage all read this name.

The second run is a different view
----------------------------------
``out/scan_highlight/sam3_results.json`` holds 157 radii with a median diameter
of 30.80 px.  Its dataset is the highlight clip, not vod30, and its camera is
closer to the table.  Do not mix the two runs.

The cloth scale is not this quantity
------------------------------------
The cloth's local scale is a different number in each region of the image: the
reference quad of ``src/shot_pot_gate.py`` spans 0.129 to 0.388 px/mm, so the
cloth runs from 2.58 to 7.75 mm/px across the cloth.  This module states the
ball's size only.  It does not own a cloth scale.
"""
from __future__ import annotations

import math

# --------------------------------------------------------------------------- facts

#: The rule of the sport.  A pool ball is 57.15 mm (2.25 in) wide, so its radius
#: is 28.575 mm.  This is the one value that is not a measurement from the video.
BALL_WIDTH_MM = 57.15

#: The frame the radii were measured in, and the pipeline's working size.
NATIVE_FRAME = (1280, 720)
WORKING_FRAME = (960, 540)

#: The measured ball diameters at :data:`NATIVE_FRAME`, in pixels.
#: median 9.45 px radius, p10 6.9 px, p90 12.4 px (see the quantile rule above).
DIAMETER_NATIVE_PX = 18.9
DIAMETER_P10_NATIVE_PX = 13.8
DIAMETER_P90_NATIVE_PX = 24.8

#: The same measurement as a radius.  ``src/motion_scan.py`` reads this name for
#: its ``REF_BALL_RADIUS``.
RADIUS_NATIVE_PX = 9.45

#: Pixels per millimetre at the native frame, from the measured diameter.
NATIVE_PX_PER_MM = DIAMETER_NATIVE_PX / BALL_WIDTH_MM


# --------------------------------------------------------------------- conversion

def scale_between(from_frame: tuple[float, float],
                  to_frame: tuple[float, float]) -> float:
    """The linear scale from one frame size to another, by width.

    ``scale_between(NATIVE_FRAME, WORKING_FRAME)`` is 0.75.  A frame size is
    ``(width, height)`` in pixels, and the width alone carries the scale: a
    960x540 frame is the native frame at 0.75x on both axes.
    """
    return float(to_frame[0]) / float(from_frame[0])


def diameter_px(frame: tuple[float, float] = NATIVE_FRAME) -> float:
    """The measured ball diameter in one frame's pixels.

    ``diameter_px()`` is 18.9 px.  ``diameter_px(WORKING_FRAME)`` is 14.175 px,
    the number the scan and the census work at.
    """
    return DIAMETER_NATIVE_PX * scale_between(NATIVE_FRAME, frame)


def radius_px(frame: tuple[float, float] = NATIVE_FRAME) -> float:
    """The measured ball radius in one frame's pixels: half of :func:`diameter_px`."""
    return diameter_px(frame) / 2.0


def area_px2(frame: tuple[float, float] = NATIVE_FRAME) -> float:
    """The area one ball covers in one frame's pixels: ``pi * r ** 2``.

    This is 280.55 px^2 at the native frame and 157.81 px^2 at the working frame.
    The old dead constant in ``src/motion_scan.py`` said 266.0, the area of the
    18.4 px ball that no file in this tree holds.
    """
    return math.pi * radius_px(frame) ** 2


def millimetres_per_pixel(frame: tuple[float, float] = NATIVE_FRAME) -> float:
    """The ball's own image scale: the millimetres one pixel carries.

    This is 3.02 mm/px at the native frame, from the measured diameter.  It is
    the ball's scale and not the cloth's.  No module of this tree states a cloth
    scale in those units, so this docstring names no module for one.  Two places
    hold a number of the cloth: the guarded copy in ``src/eval_table_detect.py``
    repeats one value of the console, and the comment in ``src/timing_verify.py``
    divides the table length by a span it measured.
    """
    return BALL_WIDTH_MM / diameter_px(frame)


def formatted_width(mm: float = BALL_WIDTH_MM) -> str:
    """One width in millimetres as a short string, e.g. ``"57.2mm"`` or ``"28.6mm"``.

    A comment that states a width holds this string, so the number has one home
    and the comment cannot drift from it.  The rounding is a half-up round to one
    decimal place through integer tenths, so ``round`` of a binary float cannot
    answer 57.1 for 57.15.
    """
    tenths = int(mm * 10.0 + 0.5)
    return f"{tenths // 10}.{tenths % 10}mm"
