"""One owner for the pocket name a text states.

The events document holds the pocket a pot names, in the field
``nearest_pocket``. Stored documents spell that field in three ways:

    right-side                 a bare name
    right-side (148 +- 54mm)   the name with the distance the scan measured
    148 mm from right-side     the millimetre form

Two modules answered this question with a rule each, and the two rules
disagreed. The gate of src/event_gates.py accepted a bare name. The console
backend of annotator/unified_server.py accepted only the other two spellings
and then answered the geometrically nearest pocket, so for a bare name the
console showed a name the document does not hold.

Every answer of this module is a member of ``POCKETS_MM``, the six pockets of
src/table_geometry.py.
"""
from __future__ import annotations

from typing import Any

from src.table_geometry import POCKETS_MM


def pocket_from_text(text: Any) -> str | None:
    """The pocket name this text states, or None.

    A bare name, a name before a parenthesis and a name after `` from `` are
    accepted. Any other text answers None, and the caller decides what to do
    with a pot that names no pocket.
    """
    words = str(text or "").strip()
    if not words:
        return None
    name = words.split("(")[0].strip()
    if name in POCKETS_MM:
        return name
    tail = words.rsplit(" from ", 1)
    if len(tail) == 2 and tail[1].strip() in POCKETS_MM:
        return tail[1].strip()
    return None
