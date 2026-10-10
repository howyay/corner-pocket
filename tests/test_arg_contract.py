"""The repository cases for the argument-contract rule.

The rule lives in ``tests/arg_contract.py``; that module owns the scan and its
limits.  This module states the cases only:

* three look-alikes, one for each naming path of the rule;
* one dead flag, the proof that the forward direction is not vacuous;
* one undeclared read, the proof that the reverse direction is not vacuous.

Run: ``./scripts/pool-test.sh python test_arg_contract``
"""
import unittest

from arg_contract import (
    ROOT,
    scanned_files,
    undeclared_reads_in,
    unread_arguments,
    unread_arguments_in,
)

TINY_BALL_NET_LOOK_ALIKE = '''
import argparse


def build(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command")
    p = sub.add_parser("report")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--dir", dest="overlay_dir", default="out/overlays2")
    p.set_defaults(func=cmd_report)
    p = sub.add_parser("overlays")
    p.add_argument("--dir", dest="overlay_dir", default="out/overlays2")
    p.set_defaults(func=cmd_overlays)
    args = ap.parse_args(argv)
    return args.func(args)


def cmd_report(args):
    return args.count


def cmd_overlays(args):
    return args.overlay_dir
'''

PID_SEED_REBUILD_LOOK_ALIKE = '''
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(root):
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    run(parser.parse_args().root)
'''

EVAL_FACES_LOOK_ALIKE = '''
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description="synthetic")
    parser.add_argument("command", choices=("measure", "analyse"))
    parser.add_argument("--anchors", type=int, default=None)
    parser.add_argument("--burst", type=int, default=None)
    parser.add_argument("--spacing", type=int, default=None)
    args = parser.parse_args(argv)
    plan = {"vod30": {"anchors": 4}}
    for name, cfg in plan.items():
        for key in ("anchors", "burst", "spacing"):
            value = getattr(args, key)
            if value is not None:
                cfg[key] = value
    return plan
'''

DEAD_FLAG_SOURCE = '''
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description="synthetic")
    parser.add_argument("--video", default="data/vod.mp4")
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args(argv)
    return args.video
'''

UNDECLARED_READ_SOURCE = '''
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description="synthetic")
    parser.add_argument("--video", default="data/vod.mp4")
    args = parser.parse_args(argv)
    return args.video, args.ghost
'''


class LookAlikeTests(unittest.TestCase):
    """The rule must resolve the three look-alikes the Lead measured."""

    def test_a_shared_dest_is_read_under_that_dest(self):
        """tiny_ball_net.py: two ``--dir`` flags, both ``dest="overlay_dir"``, read."""
        self.assertEqual(unread_arguments_in(TINY_BALL_NET_LOOK_ALIKE, "look-alike"), [])

    def test_a_flag_read_off_the_parse_args_call_is_read(self):
        """pid_seed_rebuild.py: ``--root`` is read as ``parse_args().root``."""
        self.assertEqual(unread_arguments_in(PID_SEED_REBUILD_LOOK_ALIKE, "look-alike"), [])

    def test_getattr_over_a_literal_key_tuple_is_read(self):
        """eval_faces.py: ``getattr(args, key)`` reads "anchors", "burst", "spacing"."""
        self.assertEqual(unread_arguments_in(EVAL_FACES_LOOK_ALIKE, "look-alike"), [])

    def test_the_rule_still_reports_a_flag_nobody_reads(self):
        """The proof that the three cases above are not vacuous."""
        self.assertEqual(unread_arguments_in(DEAD_FLAG_SOURCE, "dead.py"), ["dead.py:8 --frames"])


class UndeclaredReadTests(unittest.TestCase):
    """The rule must also report a read that no declaration covers."""

    def test_the_rule_reports_a_read_of_an_undeclared_name(self):
        """The proof that the reverse direction is not vacuous."""
        self.assertEqual(unread_arguments_in(UNDECLARED_READ_SOURCE, "ghost.py"), [])
        self.assertEqual(undeclared_reads_in(UNDECLARED_READ_SOURCE, "ghost.py"),
                         ["ghost.py:9 args.ghost"])


class RepositoryContractTests(unittest.TestCase):
    """No flag under src/, tools/ and scripts/ may be unread (src/sam3/ excluded)."""

    def test_no_flag_in_the_repository_is_unread(self):
        labels = scanned_files()
        self.assertIn("src/timing_verify.py", labels)
        self.assertNotIn("src/sam3/model.py", labels)
        offenders = []
        for label in labels:
            offenders.extend(unread_arguments(ROOT / label))
        self.assertEqual([], offenders,
                         "these flags are declared and never read:\n  " + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
