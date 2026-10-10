"""Argument contract: every argparse flag must be read by the code that declares it.

A flag that no line reads is a silent lie.  The user passes it, the tool ignores
it, and nothing says so.  The scanner below parses the source with ``ast``: it
never imports a scanned module, because some of them need SAM3 weights, a VOD or
a display at import time.

The rule resolves the four ways this repository names an argument: an explicit
``dest=``, ``args.<name>``, ``getattr(args, key)`` over a literal key tuple, and
``parse_args().<name>``.  The three look-alikes in LookAlikeTests are the reason
each of those four paths is needed.

Run: ``./scripts/pool-test.sh python test_arg_contract``
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = ("src", "tools", "scripts")
VENDORED = "src/sam3"          # the vendored SAM3 clone obeys its own contract


def _constant_string(node):
    """The text behind one literal node, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _iterable_strings(node):
    """Every string in one literal tuple, list or set."""
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [text for text in (_constant_string(item) for item in node.elts) if text is not None]
    return []


def _add_argument_calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument":
            yield node


def _flag_options(call):
    """The option strings of one add_argument call: the ones that start with '-'."""
    options = []
    for argument in call.args:
        text = _constant_string(argument)
        if text is not None and text.startswith("-"):
            options.append(text)
    return options


def _destination(call, options):
    """The attribute an option lands on: dest= wins, then the first long option."""
    for keyword in call.keywords:
        if keyword.arg == "dest":
            return _constant_string(keyword.value)
    for option in options:
        if option.startswith("--"):
            return option[2:].replace("-", "_")
    return options[0][1:].replace("-", "_") if options else None


def _reported_flag(options):
    """The name a user types: the first long option, else the first option."""
    for option in options:
        if option.startswith("--"):
            return option
    return options[0]


def _is_parse_args_call(node):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
        and node.func.attr in ("parse_args", "parse_known_args")


def _arguments_names(tree):
    """The variables that hold a parse_args() result."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value, targets = node.value, node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            value, targets = node.value, [node.target]
        else:
            continue
        if _is_parse_args_call(value):
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _function_definitions(tree):
    """Every function of the module, by name."""
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _parameter_name(definition, index, keyword=None):
    """The parameter a call at `index`, or at `keyword`, fills."""
    positional = [argument.arg for argument in
                  list(definition.args.posonlyargs) + list(definition.args.args)]
    if keyword is not None:
        named = positional + [argument.arg for argument in definition.args.kwonlyargs]
        return keyword if keyword in named else None
    return positional[index] if index < len(positional) else None


def _holder_names(tree):
    """Every name that holds a parse_args() result, directly or as a parameter.

    ``return build(ap.parse_args(argv))`` passes the namespace into `build`, and
    `build` reads ``args.out``.  The loop below follows that flow: the parameter
    of the callee holds the same namespace, so its reads count as reads.
    """
    definitions = _function_definitions(tree)
    holders = _arguments_names(tree)

    def holds(node):
        return (isinstance(node, ast.Name) and node.id in holders) or _is_parse_args_call(node)

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            definition = definitions.get(node.func.id)
            if definition is None:
                continue
            pairs = [(index, None, argument) for index, argument in enumerate(node.args)]
            pairs += [(None, keyword.arg, keyword.value) for keyword in node.keywords if keyword.arg]
            for index, keyword, argument in pairs:
                if not holds(argument):
                    continue
                name = _parameter_name(definition, index, keyword=keyword)
                if name and name not in holders:
                    holders.add(name)
                    changed = True
    return holders


def _literal_key_loops(tree):
    """The loop variables that range over a literal tuple of strings."""
    loops = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            texts = _iterable_strings(node.iter)
            if texts:
                loops.setdefault(node.target.id, set()).update(texts)
    return loops


def _read_destinations(tree):
    """Every destination the code reads off a parse_args() result."""
    holders = _holder_names(tree)
    loops = _literal_key_loops(tree)

    def is_holder(node):
        return (isinstance(node, ast.Name) and node.id in holders) or _is_parse_args_call(node)

    read = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and is_holder(node.value):
            read.add(node.attr)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "getattr" and len(node.args) >= 2 and is_holder(node.args[0]):
            text = _constant_string(node.args[1])
            if text is not None:
                read.add(text)
            elif isinstance(node.args[1], ast.Name) and node.args[1].id in loops:
                read.update(loops[node.args[1].id])
    return read


def _label(path):
    """The report label: the repository-relative path when the file is inside it."""
    path = Path(path)
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def unread_arguments_in(source, label="<string>"):
    """The flags no line reads in one source text, as ``<label>:<line> <flag>``."""
    tree = ast.parse(source)
    read = _read_destinations(tree)
    found = []
    for call in _add_argument_calls(tree):
        options = _flag_options(call)
        if not options:
            continue                  # a positional argument is not a flag
        destination = _destination(call, options)
        if destination is None or destination in read:
            continue
        found.append((call.lineno, f"{label}:{call.lineno} {_reported_flag(options)}"))
    return [text for _line, text in sorted(found)]


def unread_arguments(path):
    """The flags no line reads in one python file, as ``<path>:<line> <flag>``."""
    path = Path(path)
    return unread_arguments_in(path.read_text(encoding="utf-8"), _label(path))


def scanned_files():
    """Every python file under the scanned roots, as repository-relative labels."""
    labels = []
    for root in SCANNED:
        for path in sorted((ROOT / root).rglob("*.py")):
            label = path.relative_to(ROOT).as_posix()
            if label == VENDORED or label.startswith(VENDORED + "/"):
                continue
            labels.append(label)
    return labels


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
