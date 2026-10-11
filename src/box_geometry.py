"""One home for overlap of two boxes: the intersection over union rule.

Four modules of src/ used to define this rule themselves, in two spellings that
compute the same number.  A fifth, ``src/person_pipeline.py``, held a third copy
of the first spelling under the name ``_iou``.  A sixth, ``src/recut_crops.py``,
wrote the arithmetic inline in a loop.  A reader of one copy could not see the
other copies.  This module owns the rule now, and the six modules import it.

The module imports nothing from this project and nothing from a third party, so a
heavy module can import it cheaply and a test can import it without a model.

``tests/test_box_geometry.py`` holds the home in two ways.  No other module of
src/ may define a module-level function named ``iou``.  No other module of src/
may hold a module-level body equal to this one, whatever the name of that
function is.  The near miss ``face_area_iou`` in ``src/enroll_from_tracklet.py``
has a different body, so the rule does not flag it.
"""


def iou(a, b) -> float:
    """Intersection over union of the boxes a and b, each (x0, y0, x1, y1)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
