"""The one home of the summary of one list of numbers.

Round 60 measured four local summaries of "the median and a high percentile of
this list".  Two of them were one body: ``src/enroll_from_tracklet.py stats`` and
``src/eval_faces.py pair_stats``.  ``tests/test_duplicate_bodies.py`` recorded
that pair as a body that stays apart, because round 51 wrote both files outside
its write scope.  The other two were ``src/calib_mapping_audit.py _stats`` and
``src/eval_table_detect.py _stats``.  They held fewer keys and a smaller
precision than the first two, so four answers came from four bodies.

This module is the one owner.  ``summary`` answers the six keys of the first
pair and the two further keys the other pair held: ``n``, ``min``, ``p05``,
``p10``, ``median``, ``p90``, ``p95`` and ``max``.  Two named arguments hold
every difference of the four old bodies:

* ``keys`` names the keys the caller reads.  A key the caller does not name is
  not in the answer.
* ``digits`` is the precision of every number in the answer.

The empty list gets one answer: ``n`` is 0 and every other key is ``None``.
The numbers are not rounded when the list is empty.

A key that is not a number, for example ``nan``, passes through the answer as
it comes from numpy.  The old bodies did the same.

The readers of this module, and the arguments each one passes, follow:

* ``src/enroll_from_tracklet.py`` reads the six keys of ``PAIR_KEYS`` at four
  digits, under the name ``stats``;
* ``src/eval_faces.py`` reads the same six keys at four digits, under the name
  ``pair_stats``, because its callers already use that name;
* ``src/calib_mapping_audit.py`` reads ``n``, ``median``, ``p10``, ``p90``,
  ``min`` and ``max`` at two digits, and it answers ``{"n": 0}`` for an empty
  list, because its document held that answer before round 60;
* ``src/eval_table_detect.py`` reads ``n``, ``median``, ``p90``, ``min`` and
  ``max`` at two digits, and it answers ``None`` for an empty list, for the
  same reason.

Each reader holds its own tuple of keys, because each tuple is the record of
what that reader writes.  This module holds the two keys of ``read_pair``, and
it cannot hold the keys of the two audits: the readers import this module, so
this module cannot import them.

The import direction is one way.  This module reads numpy and nothing of
``src/``.  The four readers read this module.  So no cycle exists.

Run the guard: ``./scripts/pool-test.sh python test_stats``
"""
from __future__ import annotations

import numpy as np

#: The keys of the summary, in the order the answer holds them.
SUMMARY_KEYS = ('n', 'min', 'p05', 'p10', 'median', 'p90', 'p95', 'max')

#: The keys of the pair that held one body before round 60: the summary of one
#: list of cosines.  It holds no p10 and no p90, and the answer keeps that shape.
PAIR_KEYS = ('n', 'min', 'p05', 'median', 'p95', 'max')

_KEYS = frozenset(SUMMARY_KEYS)

#: The keys that are a quantile of the list, and the fraction of each one.
_QUANTILES = {'p05': 5.0, 'p10': 10.0, 'median': 50.0, 'p90': 90.0, 'p95': 95.0}


def summary(values, keys=SUMMARY_KEYS, digits=4) -> dict:
    """The summary of one list of numbers: n, min, quantiles, median and max.

    ``keys`` is the set of keys the caller reads, and it must be a subset of
    ``SUMMARY_KEYS``.  ``digits`` is the precision of every number.  An empty
    list answers n = 0 and None for every other key.
    """
    unknown = sorted(set(keys) - _KEYS)
    if unknown:
        raise ValueError('no such key of the summary: %s' % ', '.join(unknown))
    values = [float(value) for value in values]
    if not values:
        return {key: (0 if key == 'n' else None) for key in keys}
    arr = np.asarray(values, np.float64)
    answer = {'n': len(values), 'min': float(arr.min()), 'max': float(arr.max())}
    for key, fraction in _QUANTILES.items():
        answer[key] = float(np.percentile(arr, fraction))
    return {key: answer[key] if key == 'n' else round(answer[key], digits)
            for key in keys}


def read_pair(values) -> dict:
    """The six keys of the pair that held one body: n / min / p05 / median / p95 / max.

    ``src/enroll_from_tracklet.py stats`` and ``src/eval_faces.py pair_stats``
    bind this name, so neither module holds a body of the summary and neither
    module holds a wrapper around it.
    """
    return summary(values, keys=PAIR_KEYS, digits=4)
