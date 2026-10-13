"""The one home of the tiny-ball probe directory and the four artifact names in it.

Five live readers built the probe path themselves: the pipeline stage
(``annotator/pipeline_stages.py``), the trainer (``src/tiny_ball_net.py``), the
labeller (``src/fast_ball_labels.py``), the false-positive audit
(``src/ball_fp_audit.py``) and the held-out stack probe (``tests/ball_stack_ab.py``).
Each held its own spelling of ``out/tiny_ball_probe``, of the checkpoint name
``960x540-scratch.pt`` and of the frozen held-out name ``held_frozen.json``.  A fourth
name, the labeller output ``new_labels.json``, stood in two files at once.  One rename
of an artifact, or one moved directory, would then have to land in five files at once.

This module holds the four names.  A reader that needs an absolute path joins
these names to its own root, so the file system root stays local to each reader and
this module states no root of its own.

The module imports only ``pathlib``.  A light module (``annotator/pipeline_stages.py``)
can therefore read it without making ``cv2``, ``numpy`` or ``torch`` a dependency,
and the trainer can read it without a cycle.

Run: ``./scripts/pool-test.sh python test_tiny_ball_probe_path_owner``
"""
from pathlib import Path

#: The probe directory, relative to the repository root: ``out/tiny_ball_probe``.
#: It is a relative path for one reason: the root belongs to the reader.  The
#: pipeline names it relative to the pipeline root, and the other readers join it
#: to the repository root.
PROBE_DIR_NAME = Path("out/tiny_ball_probe")

#: The trained checkpoint of the ``960x540-scratch`` round, the file inside the
#: probe directory above.  ``annotator.pipeline_stages.BALL_CHECKPOINT`` spells the
#: same file relative to the pipeline root.
CHECKPOINT_NAME = "960x540-scratch.pt"

#: The frozen held-out time set.  ``src/tiny_ball_net.py`` writes the file and the
#: three readers of a held-out score read it; a rename here moves all four.
HELD_FROZEN_NAME = "held_frozen.json"

#: The labeller's output file inside the probe directory.  ``src/fast_ball_labels.py``
#: writes it and ``src/tiny_ball_net.py`` reads it as teacher labels, so one rename
#: moves both readers.
LABELS_NAME = "new_labels.json"
