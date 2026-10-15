"""The one sentence of a video that cannot be opened.

Why this module exists
----------------------
The words of a failed open stood in seven ``src/`` modules, at fifteen code sites,
and every site wrote the sentence itself:

* ``src/calib_mapping_audit.py:258``, ``:447`` and ``:451`` answer the words in a
  dict, beside the keys of the caller;
* ``src/calib_segment_measure.py:296``, ``src/segment_calib_report.py:142`` and
  ``:184`` raise ``SystemExit``;
* ``src/enroll_from_tracklet.py:518``, ``:786`` and ``:1390``,
  ``src/eval_faces.py:602`` and ``src/eval_table_detect.py:345`` raise
  ``RuntimeError``;
* ``src/motion_scan.py:367``, ``:535``, ``:700`` and ``:1726`` raise ``OSError``.

The brief of round 113 counted twelve sites in eight modules.  The measurement at
HEAD answered fifteen sites in seven modules.  The class and the payload stay at
the site; this module owns the words alone, so one edit answers a change of the
sentence for every site.

Three wordings are different sentences, and they stay as they are:

* ``annotator/refusals.py:215`` and ``annotator/unified_server.py:1892`` hold the
  refusal subject ``cannot open VOD`` of the served API: it is a key of the refusal
  table, and not a message built from a path;
* ``src/timing_verify.py:161`` holds the second wording ``cannot open video:
  <path>``;
* ``tools/playfield_harness.py:47`` holds the wording of the harness,
  ``cannot open <path>: no frame can be read from it``, which
  ``tests/test_playfield_harness.py:246`` reads.

This module imports nothing of the tree, so no import cycle starts at it.  The
guard of the rule is ``tests/test_cannot_open_owner.py``.

The one spelling of the sentence in code is the function below.
"""

from __future__ import annotations

__all__ = ["cannot_open"]


def cannot_open(path) -> str:
    """Answer the sentence of one video that cannot be opened.

    ``path`` is a string or a path object.  The caller keeps its own exception
    class and its own payload: it raises ``OSError``, ``RuntimeError`` or
    ``SystemExit`` with the answer, or it puts the answer under the ``error`` key
    of its dict.
    """
    return f"cannot open {path}"
