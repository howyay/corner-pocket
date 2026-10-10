"""One owner per command-line knob of src/multiplex_demo.py.

`main()` declares eight arguments, and seven lines read them.  The eighth,
`--frames` at `src/multiplex_demo.py:162`, has no reader in the module, so
`--frames 10` runs the whole clip and prints no warning: the knob does nothing.
The effective control is `--max-frames` at `:160`, read at `:220` as
`max_frames=(args.max_frames if args.max_frames > 0 else None)` and handed to
`propagate` (`:61`, `:69-70`).

The case below states the rule that removes the class, and not one instance: a
declared argument that no line reads is a knob that does nothing.  It reads the
source with `ast` and compares two sets, so the next argument added without a
reader fails here too.  The two sets are:

* the arguments `main()` declares, `add_argument("--name")`, with the dashes
  written as the underscores that argparse uses (`--prompt-frame` becomes
  `prompt_frame`);
* the arguments some line reads, `args.<name>`.

The module is not imported.  `src/multiplex_demo.py` needs the SAM3 weights at
`/tmp/sam3.1_multiplex_fp16.safetensors` and a GPU, so an import here would test
the machine and not the source.  The case parses the file instead.

A scan that finds nothing is green, and a broken scan finds nothing.  The third
case feeds a small source with one dead argument to the same helpers, so the
green run of the first case has a meaning.

`tests/test_arg_contract.py` holds the same rule for the whole repository, over
`src/`, `tools/` and `scripts/`.  Its `unread_arguments()` reported
`src/multiplex_demo.py:162 --frames` for the HEAD source of this round, so this
module is the second guard on that one file.  This module adds two things the
repository case does not have: the line number inside one file, and the other
half of the set match, a read of an argument that `main()` never declares.

What the scan cannot see, and therefore cannot state:

* a parser that a helper builds outside `main()`, and a flag list passed as
  `*flags` or `**kwargs`: the scan reads the string literals of `add_argument`
  calls inside `main()` only;
* a name `args` that is not the argparse namespace: the scan counts every
  `args.<name>` attribute read in the module, and this module has one such name.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "src" / "multiplex_demo.py"
#: The path as a report writes it, so a failure text is usable as it stands.
DEMO_NAME = "src/multiplex_demo.py"
#: The function that builds the parser and reads the namespace.
ENTRY = "main"

#: A source with one dead argument, for the scan itself.
SAMPLE = '''\
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", default="data/clip")
    ap.add_argument("--prompt-frame", type=int, default=0)
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--frames", type=int, default=0)
    args = ap.parse_args()
    return args.clip, args.prompt_frame, args.max_frames
'''


def parse(source=None):
    """The module tree of src/multiplex_demo.py, or of a given source text."""
    text = DEMO.read_text(encoding="utf-8") if source is None else source
    return ast.parse(text, filename=DEMO_NAME)


def entry_function(tree):
    """The `main` node of a module tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == ENTRY:
            return node
    raise AssertionError(f"{DEMO_NAME}: no function {ENTRY}() to scan")


def dest(flag):
    """The attribute name that argparse makes from one long flag."""
    return flag.lstrip("-").replace("-", "_")


def declared_arguments(tree):
    """[(line, dest)] for every `add_argument("--name")` call inside main()."""
    found = []
    for node in ast.walk(entry_function(tree)):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value.startswith("--"):
                    found.append((node.lineno, dest(arg.value)))
    return found


def read_arguments(tree):
    """[(line, name)] for every `args.<name>` read in the module."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if isinstance(node.value, ast.Name) and node.value.id == "args":
            found.append((node.lineno, node.attr))
    return found


def only_in(first, second):
    """The rows of `first` whose name is absent from `second`."""
    names = {name for _, name in second}
    return [(line, name) for line, name in first if name not in names]


def report(rows, prefix):
    """One `file:line` line per row, the shape a terminal reader can use."""
    return [f"{DEMO_NAME}:{line} {prefix}{name}" for line, name in rows]


class MultiplexDemoArguments(unittest.TestCase):
    def test_a_declared_argument_that_no_line_reads_is_a_knob_that_does_nothing(self):
        """The parser accepts it, the code ignores it, and no message says so."""
        tree = parse()
        declared = declared_arguments(tree)
        read = read_arguments(tree)
        self.assertNotEqual([], declared, f"{DEMO_NAME}: no argument declared in {ENTRY}()")
        self.assertNotEqual([], read, f"{DEMO_NAME}: no args.<name> read in the module")
        self.assertEqual(
            [],
            report(only_in(declared, read), "--"),
            "a declared argument that no line reads is a knob that does nothing: "
            "the run accepts the flag, the code ignores the value, and no message "
            "says so. Delete the argument, or read it. Offenders:\n"
            + "\n".join(report(only_in(declared, read), "--")),
        )

    def test_a_read_argument_that_main_never_declares_is_a_crash(self):
        """`args.<name>` with no matching flag is an AttributeError at run time."""
        tree = parse()
        declared = declared_arguments(tree)
        read = read_arguments(tree)
        self.assertEqual(
            [],
            report(only_in(read, declared), "args."),
            "a read of an argument that main() never declares stops the run with "
            "AttributeError, because the namespace has no such attribute. Declare "
            "the argument, or delete the read. Offenders:\n"
            + "\n".join(report(only_in(read, declared), "args.")),
        )

    def test_the_scan_reports_the_dead_argument_of_a_sample_source(self):
        """A sample with one dead argument and one dashed flag proves the scan."""
        tree = parse(SAMPLE)
        declared = declared_arguments(tree)
        read = read_arguments(tree)
        # The dashed flag must map to the underscore name that the source reads.
        self.assertIn("prompt_frame", {name for _, name in declared})
        self.assertIn("prompt_frame", {name for _, name in read})
        dead = only_in(declared, read)
        self.assertEqual(["frames"], [name for _, name in dead])
        line = dead[0][0]
        self.assertIn("--frames", SAMPLE.splitlines()[line - 1])
        self.assertEqual([f"{DEMO_NAME}:{line} --frames"], report(dead, "--"))


if __name__ == "__main__":
    unittest.main()
