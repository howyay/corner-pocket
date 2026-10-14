"""The four command-line options that the two move-scan tools share.

Why this module exists
----------------------
``src/motion_scan.py`` and ``src/track_before_detect.py`` read one measurement.
Each tool declared the same four options -- ``--video``, ``--dataset``,
``--out-dir`` and ``--quad`` -- in a nested helper of ``main()``.  The round-58
walk measured the two bodies: the same four calls, the same four defaults, one
fingerprint (``0742717844dd``).  The duplicate-body walk of
``tests/test_duplicate_bodies.py`` reads module-level ``def`` s only, so it did
not read that pair.  One edit in one tool changed one tool only.

The four options have one home here.  ``tests/test_scan_args.py`` holds the home
two ways: one walk reads the source of the three modules, and one case builds the
command line of both tools and compares the four names and the four defaults.

This module reads no video, no report and no dataset.  It writes a command line
only, so both tools can import it and no import cycle starts.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from src.datasets import BUILT_IN_DATASET

ROOT = Path(__file__).resolve().parents[1]


def add_scan_options(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add the four options of one move-scan subcommand to ``p``, and answer ``p``.

    Each default is the default the two tools answered before this module
    existed.  This file sits in ``src/``, so ``ROOT`` is the repository root and
    the ``--out-dir`` default keeps the same bytes.
    """
    p.add_argument("--video", default=None)
    p.add_argument("--dataset", default=BUILT_IN_DATASET)
    p.add_argument("--out-dir", default=str(ROOT / "out" / "motion_scan"))
    p.add_argument("--quad", default=None)
    return p
