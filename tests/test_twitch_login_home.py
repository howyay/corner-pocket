"""The Twitch channel login has one home: ``TWITCH_LOGIN`` in annotator/twitch_source.py.

Round 69, Strong 1.  The shape of a canonical Twitch channel login stood in full in six
sites of four python modules, under three different refusal sentences, and the console
rule ``parseSource`` (annotator/ops.js) spelled the same shape once more.  No case read
the shape, so a fifth site, a widened alphabet or a changed ceiling could drift in
silence.

``TWITCH_LOGIN`` is the one home of the shape now, and every python site of a login
reads that name.  The console cannot import a python name, so it states its own copy of
the shape; two cases outside this module hold that copy: the shape parity in
``tests/test_source_url_parity.py``, and the ceiling and the copy rule in
``tests/test_console_service_bounds.py``.

The three checks here read three different things on purpose:

1. the value of the name, and the logins it accepts and refuses;
2. the source text of the shipped tree, through an ``ast`` walk that names every
   ``file:line`` site that spells a login class again;
3. a planted copy, which proves that the walk of check 2 reports a second spelling
   instead of passing in silence.

A test of this tree spells the shape as an independent fact: it holds the owner to the
shape, and a test that read the shape from the owner alone could agree with a widened
alphabet.  So the walk below reads the shipped packages (tests/_shipped.py) and never
the test tree.

Run: ``./scripts/pool-test.sh python test_twitch_login_home``
"""
from __future__ import annotations

import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from _shipped import shipped_modules  # noqa: E402

from annotator.twitch_source import TWITCH_LOGIN  # noqa: E402

#: The owner module of the name, and its assignment line, ``TWITCH_LOGIN = ...``.
OWNER = "annotator/twitch_source.py"
ASSIGNMENT = "TWITCH_LOGIN ="

#: The four modules that read a login today.  Three import the name in full; the VOD
#: source reads ``live.TWITCH_LOGIN``, because it already holds the alias ``live`` for
#: the owner module (``from annotator import twitch_source as live``).
READERS = ("annotator/live_processing.py", "annotator/operations.py",
           "annotator/twitch_vod_source.py", "annotator/vod_import.py")

#: The shape one string must hold to count as a second copy: a character class of
#: letters, digits, ``_`` and ``-`` with a bounded repeat after it.  The walk reads the
#: shape and not the number, so a copy with another ceiling is a site too.
LOGIN_CLASS = re.compile(r"\[[A-Za-z0-9_-]*[A-Za-z][A-Za-z0-9_-]*\]\{\d+,\d+\}")

#: The shape the owner must hold, as an independent fact of this test.
CANONICAL = "[a-z0-9_]{1,25}"

#: A login the name must accept: the lowest case of a real channel.
GOOD_LOGIN = "examplechannel"

#: Logins the name must refuse: the two edges, a space, an upper case letter, a hyphen.
BAD_LOGINS = ("", "x" * 26, "Not A Channel", "ExampleChannel", "example-channel")


def string_value(node: ast.AST) -> str | None:
    """The text of one string expression: a literal, or literals added together."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = string_value(node.left), string_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def spelling_sites(paths) -> list[str]:
    """One ``path:line`` entry for every string of ``paths`` that spells a login class.

    The walk reads a literal and a sum of literals.  A pattern a module builds at run
    time - a name, a join, a formatted string - spells no such text, and the case below
    states that limit instead of hiding it.
    """
    found = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        sites = {(node.lineno, text) for node in ast.walk(tree)
                 if (text := string_value(node)) and LOGIN_CLASS.search(text)}
        found.extend(f"{path}:{number}" for number, _ in sorted(sites))
    return sorted(found)


def shipped_sites() -> list[str]:
    """The same entries over the shipped tree, under the repository root."""
    return [site.replace(str(ROOT) + "/", "") for site in spelling_sites(shipped_modules())]


def assignment_line() -> int:
    """The line of the owner module that assigns the name, whatever its number.

    The check reads the line from the assignment itself, so a comment above the name
    moves no expectation, and a second spelling still fails the case.
    """
    lines = (ROOT / OWNER).read_text(encoding="utf-8").splitlines()
    found = [number for number, line in enumerate(lines, 1) if line.startswith(f"{ASSIGNMENT} ")]
    if len(found) != 1:
        raise AssertionError(f"{OWNER}: the assignment must stand once, and it stands {len(found)} times")
    return found[0]


def imports_the_owner(tree: ast.AST) -> bool:
    """True when one file imports the owner name, or the owner module under an alias."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        names = {alias.name for alias in node.names}
        if node.module == "annotator.twitch_source" and "TWITCH_LOGIN" in names:
            return True
        if node.module == "annotator" and "twitch_source" in names:
            return True
    return False


class TwitchLoginHomeTest(unittest.TestCase):
    """One login shape, one name, and one ``file:line`` site in the shipped tree."""

    def test_the_owner_holds_the_login(self):
        """The value, the two edges of the ceiling, and the logins the name refuses."""
        self.assertEqual(CANONICAL, TWITCH_LOGIN, f"{OWNER}: the owner must hold the login shape")
        for login in (GOOD_LOGIN, "x" * 25):
            with self.subTest(login=login):
                self.assertIsNotNone(re.fullmatch(TWITCH_LOGIN, login),
                                     f"the login shape must accept {login!r}")
        for login in BAD_LOGINS:
            with self.subTest(login=login):
                self.assertIsNone(re.fullmatch(TWITCH_LOGIN, login),
                                  f"the login shape must refuse {login!r}")

    def test_every_reader_imports_the_name(self):
        """Each reader imports the name, and no reader spells the class again."""
        for name in READERS:
            path = ROOT / name
            self.assertTrue(path.is_file(), f"the reader of the login must exist: {name}")
            text = path.read_text(encoding="utf-8")
            sites = [site.replace(str(ROOT) + "/", "") for site in spelling_sites([path])]
            self.assertEqual([], sites,
                             f"{name} must read TWITCH_LOGIN, and it spells the login class at: "
                             + "; ".join(sites))
            self.assertIn("TWITCH_LOGIN", text, f"{name} must read the name of the one home")
            self.assertTrue(imports_the_owner(ast.parse(text, filename=str(path))),
                            f"{name} must import TWITCH_LOGIN from {OWNER}, or the owner module itself")

    def test_no_shipped_module_spells_the_login_again(self):
        """The walk of the shipped packages names the owner line and no other site."""
        readers = {ROOT / name for name in READERS}
        self.assertTrue(readers <= set(shipped_modules()),
                        "the walk must hold every reader of the name in its scope")
        sites = shipped_sites()
        expected = f"{OWNER}:{assignment_line()}"
        self.assertEqual([expected], sites,
                         "the login shape has one home, " + OWNER + "; import TWITCH_LOGIN from it: "
                         + "; ".join(sites))

    def test_the_walk_reports_a_planted_copy(self):
        """A copy must answer its own site, and the walk must state the shape it cannot see."""
        planted = ("def thumb_path(channel, vod):\n"
                   "    if not re.fullmatch(r'[a-z0-9_]{1,25}', channel or ''):\n"
                   "        return ''\n")
        widened = ("def channel_of(path):\n"
                   "    return re.fullmatch(r'/([A-Za-z0-9_]{1,30})', path)\n")
        built = ("LOGIN_CLASS = '[a-z0-9_]'\n"
                 "def channel_of(path):\n"
                 "    return re.fullmatch(LOGIN_CLASS + '{1,25}', path)\n")
        with tempfile.TemporaryDirectory() as folder:
            for text in (planted, widened):
                path = Path(folder) / "planted.py"
                path.write_text(text, encoding="utf-8")
                self.assertEqual([f"{path}:2"], spelling_sites([path]),
                                 "the walk must name the line of a planted copy")
            path = Path(folder) / "built.py"
            path.write_text(built, encoding="utf-8")
            self.assertEqual([], spelling_sites([path]),
                             "the walk cannot see a class a module builds at run time, and it says so")


if __name__ == "__main__":
    unittest.main()
