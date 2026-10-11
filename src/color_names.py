"""One home for the detector colour vocabulary.

``row.src.ball_detect`` reports the hue-wraparound red band under a second name
(``red2``).  The census and the gate compare colour names, and the same
physical ball must compare equal on both sides.  Until round 56 each module held
its own copy of the alias table and its own lookup, so one table edit moved one
reader only.  This module holds the one table and the one canonical lookup.

The blank-value decision
------------------------

A blank value answers ``''`` here.  That answer is the canonical one, because
the alias rule is a mapping and an unmapped input keeps its own text.

The two callers need different answers for the same blank input, and each caller
holds its own documented step:

* ``src/ball_census.py normalize_color`` answers ``UNKNOWN`` for a blank value.
  A census colour is a name that a later report prints, so the empty string is
  not a name.
* ``src/event_gates.py color_key`` answers ``''`` for a blank value.  A key
  compares one claim with one measurement, and two blank values must compare
  equal.

One table holds the rule.  A key is a spelling the detector reports.  ``color_key``
strips the input and folds its case before the lookup, so a reader reaches the
rule through ``color_key`` and not through a direct read of ``COLOR_ALIASES``.

One home: ``tests/test_color_names.py`` walks the module constants of
``src/*.py`` and fails if a second colour alias table appears.
"""
from __future__ import annotations

from typing import Any

#: The detector colour vocabulary.  The key is a spelling that the detector
#: reports.  The value is the canonical colour name.  Every key is lowercase,
#: because ``color_key`` folds the case of the input before the lookup.
COLOR_ALIASES = {"red1": "red", "red2": "red"}


def color_key(value: Any) -> str:
    """Detector colour name -> comparable colour name.

    One home for the alias rule.  A blank value answers ``''``, and an unknown
    name answers its own text, because the rule is a mapping.
    """
    text = str(value or "").strip().lower()
    return COLOR_ALIASES.get(text, text)
