"""Argument contract: the rule that a file declares the arguments it reads.

A flag that no line reads is a silent lie.  The user passes it, the tool ignores
it, and nothing says so.  A read of a name that no line declares is a stop: the
namespace has no such attribute, and the run raises ``AttributeError``.

The scanner below parses the source with ``ast``: it never imports a scanned
module, because some of them need SAM3 weights, a VOD or a display at import
time.

The rule resolves the four ways this repository names an argument: an explicit
``dest=``, ``args.<name>``, ``getattr(args, key)`` over a literal key tuple, and
``parse_args().<name>``.  The three look-alikes in the test module
``test_arg_contract`` are the reason each of those four paths is needed.

One scanner serves both directions:

* ``unread_arguments()`` reports a declared flag that no line reads;
* ``undeclared_reads()`` reports a read of a name that no declaration covers.

The scan has limits.  It reads string literals only, so a flag built from a
variable, from ``*flags`` or from ``**kwargs`` stays invisible.  It counts every
``args.<name>`` attribute of the file, so a local name ``args`` that does not
hold the namespace counts as a read.  It follows the namespace into a helper of
the same file only.  It skips the vendored ``src/sam3`` clone.

Run: ``./scripts/pool-test.sh python test_arg_contract``
"""
import ast
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


def _read_destination_rows(tree):
    """Every (line, name) the code reads off a parse_args() result."""
    holders = _holder_names(tree)
    loops = _literal_key_loops(tree)

    def is_holder(node):
        return (isinstance(node, ast.Name) and node.id in holders) or _is_parse_args_call(node)

    rows = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and is_holder(node.value):
            rows.add((node.lineno, node.attr))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "getattr" and len(node.args) >= 2 and is_holder(node.args[0]):
            text = _constant_string(node.args[1])
            if text is not None:
                rows.add((node.lineno, text))
            elif isinstance(node.args[1], ast.Name) and node.args[1].id in loops:
                rows.update((node.lineno, name) for name in loops[node.args[1].id])
    return rows


def _read_destinations(tree):
    """Every destination the code reads off a parse_args() result."""
    return {name for _line, name in _read_destination_rows(tree)}


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


def _positional_destination(call):
    """The attribute a positional argument lands on: dest= wins, then its name."""
    for keyword in call.keywords:
        if keyword.arg == "dest":
            return _constant_string(keyword.value)
    for argument in call.args:
        text = _constant_string(argument)
        if text is not None and not text.startswith("-"):
            return text.replace("-", "_")
    return None


def _declared_destinations(tree):
    """Every destination an add_argument call of the file declares."""
    declared = set()
    for call in _add_argument_calls(tree):
        options = _flag_options(call)
        name = _destination(call, options) if options else _positional_destination(call)
        if name:
            declared.add(name)
    return declared


def undeclared_reads_in(source, label="<string>"):
    """The reads of an undeclared name in one source text, as ``<label>:<line> args.<name>``.

    A read of an argument that nothing declares stops a run with
    ``AttributeError``: the namespace has no such attribute.
    """
    tree = ast.parse(source)
    declared = _declared_destinations(tree)
    found = [(line, f"{label}:{line} args.{name}")
             for line, name in _read_destination_rows(tree) if name not in declared]
    return [text for _line, text in sorted(found)]


def undeclared_reads(path):
    """The reads of an undeclared name in one python file, as ``<path>:<line> args.<name>``.

    A read of an argument that nothing declares stops a run with
    ``AttributeError``: the namespace has no such attribute.
    """
    path = Path(path)
    return undeclared_reads_in(path.read_text(encoding="utf-8"), _label(path))


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
