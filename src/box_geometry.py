"""One home for overlap of two boxes: the intersection over union rule.

Four modules of src/ used to define this rule themselves, in two spellings that
compute the same number.  A reader of one copy could not see the other three.
This module owns the rule now, and the four modules import it.

The module imports nothing from this project and nothing from a third party, so a
heavy module can import it cheaply and a test can import it without a model.
"""


def iou(a, b) -> float:
    """Intersection over union of the boxes a and b, each (x0, y0, x1, y1)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
