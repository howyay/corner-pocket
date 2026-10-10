"""One owner per command-line knob of src/multiplex_demo.py.

`main()` declares seven arguments, and every one of them has a reader.  An
earlier round declared an eighth, `--frames` at `src/multiplex_demo.py:162`.
No line read it, so `--frames 10` ran the whole clip and printed no warning: the
knob did nothing.  The flag is gone from the source, and the rule stops the next
one.  The effective control is `--max-frames` at `:160`, read at `:219` as
`max_frames=(args.max_frames if args.max_frames > 0 else None)` and handed to
`propagate` (`:61`, `:69-70`).

The repository rule in `tests/arg_contract.py` owns the scan; this module holds
no scanner of its own.  It states the two facts of the contract for this one
file:

* no flag that `main()` declares goes unread (`arg_contract.unread_arguments`);
* no line reads an argument that `main()` never declares
  (`arg_contract.undeclared_reads`).  Such a read stops the run with
  `AttributeError`, because the namespace has no such attribute.

The module is not imported.  `src/multiplex_demo.py` needs the SAM3 weights at
`/tmp/sam3.1_multiplex_fp16.safetensors` and a GPU, so an import here would test
the machine and not the source.  The rule reads the source text with `ast`
instead.

A scan that finds nothing is green, and a broken scan finds nothing.  The third
case feeds a small source with one dead flag and one undeclared read to the same
rule, so the green run of the first two cases has a meaning.

The limits of the rule are in the docstring of `tests/arg_contract.py`.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import arg_contract

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "src" / "multiplex_demo.py"
#: The path as a report writes it, so a failure text is usable as it stands.
DEMO_NAME = "src/multiplex_demo.py"

#: A source with one dead flag and one undeclared read, for the rule itself.
SAMPLE = '''\
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", default="data/clip")
    ap.add_argument("--prompt-frame", type=int, default=0)
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--frames", type=int, default=0)
    args = ap.parse_args()
    clip = args.clip
    frame = args.prompt_frame
    limit = args.max_frames
    ghost = args.ghost
    return clip, frame, limit, ghost
'''

#: A source that proves the mapping of a dashed flag to an underscore name.
MAPPING_SOURCE = '''\
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-frame", type=int, default=0)
    args = ap.parse_args()
    return args.prompt_frame
'''

#: The line of the dead `--frames` flag in SAMPLE.
DEAD_LINE = 9
#: The line of the `args.prompt_frame` read: the dashed-name mapping.
FRAME_LINE = 12
#: The line of the undeclared `args.ghost` read in SAMPLE.
GHOST_LINE = 14


class MultiplexDemoArguments(unittest.TestCase):
    """Both directions of the argument contract for src/multiplex_demo.py."""

    def test_a_declared_argument_that_no_line_reads_is_a_knob_that_does_nothing(self):
        """The parser accepts it, the code ignores it, and no message says so."""
        self.assertEqual(
            [],
            arg_contract.unread_arguments(DEMO),
            "a declared argument that no line reads is a knob that does nothing: "
            "the run accepts the flag, the code ignores the value, and no message "
            "says so. Delete the argument, or read it.",
        )

    def test_a_read_argument_that_main_never_declares_is_a_crash(self):
        """`args.<name>` with no matching flag is an AttributeError at run time."""
        self.assertEqual(
            [],
            arg_contract.undeclared_reads(DEMO),
            "a read of an argument that main() never declares stops the run with "
            "AttributeError, because the namespace has no such attribute. Declare "
            "the argument, or delete the read.",
        )

    def test_the_rule_reports_the_dead_flag_and_the_undeclared_read_of_a_sample(self):
        """A sample with one dead flag and one undeclared read proves the rule."""
        # `--prompt-frame` writes `args.prompt_frame`.  The rule finds a reader
        # for the dashed flag, and a declaration for the read name.
        self.assertEqual([], arg_contract.unread_arguments_in(MAPPING_SOURCE, DEMO_NAME))
        self.assertEqual([], arg_contract.undeclared_reads_in(MAPPING_SOURCE, DEMO_NAME))
        # The same mapping holds inside SAMPLE: only the dead flag is reported.
        self.assertNotIn(f"{DEMO_NAME}:{FRAME_LINE} args.prompt_frame",
                         arg_contract.undeclared_reads_in(SAMPLE, DEMO_NAME))
        self.assertEqual([f"{DEMO_NAME}:{DEAD_LINE} --frames"],
                         arg_contract.unread_arguments_in(SAMPLE, DEMO_NAME))
        self.assertEqual([f"{DEMO_NAME}:{GHOST_LINE} args.ghost"],
                         arg_contract.undeclared_reads_in(SAMPLE, DEMO_NAME))


if __name__ == "__main__":
    unittest.main()
