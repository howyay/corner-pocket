"""The "no detection" state token has one owner, in Python and in the app.

The walk of round 108 found the token ``no detection`` in two languages:

  * ``src/eval_table_detect.py`` owns the fact.  It writes the token into the
    ``state`` entry of the reference verdict for a frame whose detector found no
    quad, and its module docstring calls that check a reproduction of the app's
    Vision stage.
  * ``src/check_app_quad.py`` read the same words twice: once as the verdict of
    a frame with no corners, once as the count ``no_detection`` of the summary.
  * ``annotator/app.js`` holds the browser copy.  ``noClothVerdict`` answers it
    as the default reason of a frame whose detector found no quad, and the app
    serves that state to the same reader.

Two languages hold one fact, so a change in one leaves the other.  This module
holds the python side to one owner, ``src.eval_table_detect.STATE_NO_DETECTION``,
and holds the javascript side to one name, ``STATE_NO_DETECTION`` of
``annotator/app.js``, with the two values equal:

  * the value and the line of the owner, read from the imported module and from
    the text of the owner module,
  * the line of every reader, so the report names the reader that spells the
    token itself,
  * every string literal of a reader, read from the syntax tree, so a quoted
    spelling fails with ``path:line`` and the text of that line,
  * a walk over the .py files of the shipped packages, so no third module holds
    a literal copy of the token,
  * the app's default-argument line, so the app answers one named constant and
    not a second copy of the words,
  * and the agreement of the two values, so the browser and the reference write
    one token.

The owner is ``src/eval_table_detect.py`` because that module writes the state
of every reference verdict and holds ``OUT_DIR``, the sample and the contract
with the app.  A reader holds no copy.

Run: ``./scripts/pool-test.sh python test_app_verdict_token_owner``

What this case does not see
--------------------------
* it reads the text of a string literal, not the value a name holds at run
  time.  The agreement case below reads both values from the two languages;
* a document or a console script quotes the token as prose.  Those files are no
  module of the shipped packages, so this walk does not read them;
* it does not run the detector.  ``STATE_NO_DETECTION`` is the state a frame
  with no quad takes, so the write case needs no frame.

Do not weaken a check to make a change pass.
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import eval_table_detect  # noqa: E402

#: The owner module, as a path from the repository root.
OWNER = "src/eval_table_detect.py"
#: The owner name, read from the imported module and from no copy of the text.
OWNER_NAME = "STATE_NO_DETECTION"
#: The token the readers compare.  The app serves the same word, so a later
#: round may move it, and case 1 reports that move with its line.
TOKEN = "no detection"
#: The one home of the token in the shipped tree, as ``relative:line``.
HOME = "src/eval_table_detect.py:84"
#: Every reader of the token: its module and the line that compares it.
READERS = (
    ("src/check_app_quad.py", 69),
    ("src/check_app_quad.py", 138),
)
#: The app module that holds the browser copy of the fact.
APP = "annotator/app.js"
#: The shape of the line that defines the owner name in a module of either
#: language.
NAME_RE = re.compile(rf"^\s*(?:const\s+)?{OWNER_NAME}\s*=")
#: The shape of the line that holds the default reason of a frame with no quad.
DEFAULT_RE = re.compile(r"function\s+noClothVerdict\s*\(\s*reason\s*=")
#: The shipped packages the home walk reads.
WALK_DIRS = ("src", "annotator", "tools", "scripts")
#: The floor that fails a home walk which reads no file at all.
MIN_WALK_FILES = 250
#: The javascript files the app walk reads.
JS_SUFFIX = ".js"


def source_text(relative: str) -> str:
    """The text of one source file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one source file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(relative: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return f"{relative}:{line}: {text.strip()}  <- {why}"


def owner_sites() -> list:
    """Every line of the owner module that defines the owner name."""
    return [(number, text) for number, text in enumerate(source_lines(OWNER), start=1)
            if NAME_RE.match(text)]


def app_sites() -> list:
    """Every line of the app that defines its name for the same token."""
    return [(number, text) for number, text in enumerate(source_lines(APP), start=1)
            if NAME_RE.match(text)]


def owner_token() -> str:
    """The token the owner answers, read from the imported module.

    The module read is deliberate.  ``getattr`` answers the value of the module
    that is loaded now, so a guard that plants a new value in
    ``eval_table_detect.STATE_NO_DETECTION`` is answered by that value.
    """
    value = getattr(eval_table_detect, OWNER_NAME, None)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{OWNER}:{OWNER_NAME} is not a non-empty string: {value!r}")
    return value


def token_literal_sites(text: str, where: str) -> list:
    """Every string literal that holds the token, as (line, written).

    The walk reads the syntax tree, so a comment that quotes the token is no
    site of it.  A part of an f-string is a literal too.
    """
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value == TOKEN:
            found.append((node.lineno, ast.unparse(node)))
    return sorted(found)


def js_token_literal_sites(text: str) -> list:
    """Every line of a javascript module that holds the token as a string.

    The python walk above reads the syntax tree of a .py file.  The app is
    javascript, so this walk reads the quoted form of the token in a line of
    either quoting style, and a comment that quotes the token is a site of it:
    the app holds no syntax tree this module can read.
    """
    quote_forms = (f"'{TOKEN}'", f'"{TOKEN}"')
    return [(number, line.strip()) for number, line in enumerate(text.splitlines(), start=1)
            if any(form in line for form in quote_forms)]


def literal_offences(relative: str, text: str) -> list:
    """Every report line for a quoted spelling of the token in one module."""
    lines = text.splitlines()
    return [report(relative, line, lines[line - 1],
                   f"{written} is a quoted spelling of the token; write {OWNER_NAME} "
                   f"of {OWNER} instead")
            for line, written in token_literal_sites(text, relative)]


def source_files() -> list:
    """The .py files of the shipped packages, as paths from the root."""
    found = []
    for base in WALK_DIRS:
        for path in sorted((ROOT / base).rglob("*.py")):
            if any(part == "__pycache__" or part.startswith(".") for part in path.parts):
                continue
            found.append(path.relative_to(ROOT).as_posix())
    return found


def app_files() -> list:
    """The .js files of the shipped app, as paths from the root."""
    found = []
    for path in sorted((ROOT / APP).parent.rglob(f"*{JS_SUFFIX}")):
        if any(part == "node_modules" or part.startswith(".") for part in path.parts):
            continue
        found.append(path.relative_to(ROOT).as_posix())
    return found


def literal_homes() -> list:
    """Every module of the shipped tree that holds the token as a literal."""
    return [offence for relative in source_files()
            for offence in literal_offences(relative, source_text(relative))]


def python_token() -> str:
    """The token of the owner, as a value the readers compare."""
    return owner_token()


def app_token() -> str:
    """The token of the app, read from the default of ``noClothVerdict``.

    The default is the run-time answer for a frame whose detector found no
    quad, so the value of that line is the value the browser serves.
    """
    sites = app_sites()
    if not sites:
        raise AssertionError(f"{APP} defines no {OWNER_NAME}")
    number, written = sites[0][0], _literal_strings(source_lines(APP)[sites[0][0] - 1],
                                                   APP)
    if len(written) != 1:
        raise AssertionError(report(APP, number, source_lines(APP)[number - 1],
                                    f"the line holds {len(written)} string literals: "
                                    f"{written}"))
    return written[0]


def _literal_strings(text: str, where: str) -> list:
    """Every string literal of one snippet of source, in source order."""
    try:
        tree = ast.parse(text, filename=where)
    except SyntaxError:
        return re.findall(r"'([^']*)'|\"([^\"]*)\"", text)[0:1] and \
            [one or two for one, two in re.findall(r"'([^']*)'|\"([^\"]*)\"", text)]
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


class OwnerTests(unittest.TestCase):
    """The owner name, its value and the line of the module that holds it."""

    def test_the_owner_answers_the_shipped_token(self):
        sites = owner_sites()
        self.assertEqual(1, len(sites),
                         f"{OWNER} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
        number, text = sites[0]
        self.assertEqual(TOKEN, owner_token(),
                         report(OWNER, number, text,
                                f"{OWNER_NAME} moved away from the shipped token "
                                f"{TOKEN!r}, which the reference writes and the app serves"))

    def test_the_owner_line_of_the_module_carries_the_shipped_token(self):
        """The line of the owner module that holds the value, with its number.

        This case pins the token at ``path:line``.  The value the module answers
        and the value the text of the module shows must be one token, so a
        reader of the report can open that line and see it.
        """
        number, text = owner_sites()[0]
        self.assertIn(f'{OWNER_NAME} = "{owner_token()}"', text,
                      report(OWNER, number, text,
                             f"the line does not assign {owner_token()!r} to {OWNER_NAME}"))

    def test_the_token_is_a_sentence_of_text(self):
        value = owner_token()
        self.assertEqual(value, value.strip(), f"{OWNER}:{OWNER_NAME} = {value!r}")
        self.assertEqual(value, value.lower(), f"{OWNER}:{OWNER_NAME} = {value!r}")


class ReaderTests(unittest.TestCase):
    """Every reader reads the owner name, and it holds no copy of the token."""

    def test_every_reader_reads_the_owner_name(self):
        """The anti-vacuity case: each reader line must name the owner.

        A line that holds the literal, and a line that reads the name, satisfy
        the ban below in the same way.  This case holds every reader line to the
        owner name, so the ban has a real site to protect.
        """
        offenders = []
        for relative, number in READERS:
            text = source_lines(relative)[number - 1]
            if OWNER_NAME not in text:
                offenders.append(report(relative, number, text,
                                        f"the line does not read {OWNER_NAME} of {OWNER}"))
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_no_reader_spells_the_token_as_a_literal(self):
        """A string that holds the token is a second home of the fact.

        The agreement case above holds each reader to the owner *name*.  A plain
        literal earns that case whenever its value equals the owner value today,
        and the same literal is a second home tomorrow: the owner moves, this
        string stays, and no case reads both.  So this case holds the token to
        the owner *name*.
        """
        sites = sorted({relative for relative, _ in READERS})
        offenders = [offence for relative in sites
                     for offence in literal_offences(relative, source_text(relative))]
        self.assertEqual([], offenders,
                         "a reader spells the token as a literal outside its "
                         "owner:\n" + "\n".join(offenders))

    def test_a_planted_literal_in_a_reader_is_reported(self):
        """A planted literal is reported as ``path:line`` with the text of that line."""
        planted = ("def probe(states):\n"
                   f'    return [s for s in states if s == "{TOKEN}"]\n')
        offenders = literal_offences(READERS[1][0], planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith(f"{READERS[1][0]}:2: "), offenders[0])
        self.assertIn(f'"{TOKEN}"', offenders[0])
        self.assertIn(OWNER_NAME, offenders[0])


class HomeWalkTests(unittest.TestCase):
    """One module of the shipped tree holds the token as a literal."""

    def test_the_walk_reads_the_source_tree(self):
        files = source_files()
        self.assertGreaterEqual(len(files), MIN_WALK_FILES,
                                f"the home walk read {len(files)} .py files")

    def test_the_token_has_one_live_home(self):
        """The owner line is the only literal of the token in the tree."""
        homes = literal_homes()
        self.assertEqual(1, len(homes),
                         "the token has more than one home:\n" + "\n".join(homes))
        self.assertTrue(homes[0].startswith(f"{HOME}: "),
                        f"the one home is not the owner line {HOME}: {homes[0]}")

    def test_the_walk_reports_a_planted_second_home(self):
        """A second module with the literal is reported with its file and line."""
        planted = ("def probe(frame):\n"
                   f'    state = "{TOKEN}"\n')
        offenders = literal_offences(READERS[0][0], planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith(f"{READERS[0][0]}:2: "), offenders[0])
        self.assertIn(TOKEN, offenders[0])


class AppTests(unittest.TestCase):
    """The app holds one named constant for the same state."""

    def test_the_app_names_the_token_once(self):
        """One ``const STATE_NO_DETECTION`` in the app, and it holds the token."""
        files = [relative for relative in app_files()
                 if any(NAME_RE.match(line) for line in source_lines(relative))]
        self.assertEqual([APP], files,
                         f"these modules define {OWNER_NAME}: {files}")
        sites = app_sites()
        self.assertEqual(1, len(sites),
                         f"{APP} holds {len(sites)} definitions of {OWNER_NAME}: {sites}")
        number, text = sites[0]
        self.assertIn(f"{OWNER_NAME} = '{TOKEN}'", text.replace('"', "'"),
                      report(APP, number, text,
                             f"the line does not assign {TOKEN!r} to {OWNER_NAME}"))

    def test_the_app_default_reads_the_name_and_not_a_copy(self):
        """The default reason of a frame with no quad is the named constant."""
        sites = app_sites()
        number, text = sites[0]
        offenders = [report(relative, line, source_lines(relative)[line - 1],
                            f"the default of {OWNER_NAME} holds no name of the token; "
                            f"write {OWNER_NAME} of {APP}")
                     for relative, line in _default_lines(source_text(APP), APP)
                     if OWNER_NAME not in source_lines(relative)[line - 1]]
        self.assertEqual([], offenders,
                         "the app answers the token through no name:\n" + "\n".join(offenders))

    def test_the_app_tree_holds_one_token_literal(self):
        """The token stands in one .js line of the app tree."""
        lines = [report(relative, number, source_lines(relative)[number - 1],
                        f"the .js file holds a second copy of the token; write {OWNER_NAME} "
                        f"of {APP}")
                 for relative in app_files()
                 for number, written in js_token_literal_sites(source_text(relative))]
        self.assertEqual(1, len(lines), "\n".join(lines) or "the app holds no token")
        self.assertTrue(lines[0].startswith(f"{APP}:{app_sites()[0][0]}: "),
                        f"the one token literal is not the app constant {APP}: "
                        f"{lines[0]}")


def _default_lines(text: str, where: str) -> list:
    """Every line that holds the default argument of the app verdict call."""
    return [(where, number) for number, line in enumerate(text.splitlines(), start=1)
            if DEFAULT_RE.search(line)]


class AgreementTests(unittest.TestCase):
    """The two languages write one token."""

    def test_the_app_and_the_reference_write_one_token(self):
        """The javascript constant and the python owner hold one word.

        One fact in two languages drifts in silence.  This case reads both
        values and holds them equal, so a change in one language fails here.
        """
        number, text = owner_sites()[0]
        self.assertEqual(python_token(), app_token(),
                         report(OWNER, number, text,
                                f"the reference writes {python_token()!r} and the app "
                                f"answers {app_token()!r} for the same state"))


if __name__ == "__main__":
    unittest.main()
