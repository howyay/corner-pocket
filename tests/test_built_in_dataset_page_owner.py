"""The built-in dataset id has one home on the page, and one word on both sides.

Round 111 found the id ``vod30`` spelled nine times inside code in the two
scripts of the review page:

  * ``annotator/app.js`` - seven bare literals.  One is the home,
    ``annotator/app.js:64 const BUILT_IN_DATASET = 'vod30';``, and six are
    copies: the seed of ``state.dataset`` (:67), the pick of the served dataset
    list (:487, two literals on the one line), the cloth-reference gate (:552),
    the anchors layer gate (:1064) and the anchor selection gate (:1345).
  * ``annotator/vision-stage.js`` - two copies: the anchors layer gate (:745)
    and the calibration panel gate (:1296).

``annotator/app.js`` owns the word for the page.  The comment at :60-63 states
the rule itself: ``src/datasets.py`` owns the word, this console states it once,
and a second copy of the id is the defect.  So the home stands, and every other
bare ``'vod30'`` in code reads the name.

The adapter of the ops page cannot read a constant of the review page: the two
files share one page context and no scope.  The home publishes the word on
``window.ConsoleRules.builtInDataset``, the one published seam of the page
scripts, and the adapter reads that seam - the same shape as
``window.ConsoleRules.esc`` and ``window.ConsoleRules.sizeHint`` before it.
``annotator/ops.html`` loads ``annotator/app.js`` before ``annotator/vision-stage.js``.

A prose line stays.  A comment may name the dataset freely: the walk reads a
line whose trimmed form starts with ``//``, ``*`` or ``/*`` as prose, so the
comments at ``annotator/app.js:60-63``, :256, :258, :289 and :1247 and the two
language rows at ``annotator/vision-stage.js:80`` and :195 are no copy.  A
longer token is a different fact and stays: ``calib_vod30.json``,
``seeds_only_vod30``, ``scan30`` and ``liveChoice='dataset:vod30'``
(``annotator/ops.js:768``, another lane) are not this id.

The cases below hold four statements:

* the four readers of this lane read the home name, each at its pinned line;
* the home stands at ``annotator/app.js:64``, it is the only line of the page
  that spells the id in code, and the walk of every ``.js`` of ``annotator/``
  reports any second spelling as ``path:line`` with the text of that line;
* the word of the page home is the word of the python home,
  ``BUILT_IN_DATASET`` of ``src/datasets.py``, so the pair cannot drift apart;
* a planted copy is an offender, with its file and its line.

The scan reads the text of each file, and one honesty case runs the walk over a
planted copy.  ``annotator/ops.js`` is not read: another lane owns that file.
``tests/`` is skipped, and no case plants a file on disk.

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

#: The two files of the page pair: the home, and the adapter of the ops page.
HOME_FILE = "annotator/app.js"
ADAPTER_FILE = "annotator/vision-stage.js"
PAGE_FILES = (HOME_FILE, ADAPTER_FILE)
#: The name of the home, and the word it holds.
HOME_NAME = "BUILT_IN_DATASET"
DATASET = "vod30"
#: The home line, at the state the home landed in, and its text.
HOME_LINE = 64
HOME_FORM = "const %s = '%s';" % (HOME_NAME, DATASET)
#: The one declaration of the page home: ``const`` NAME ``=`` value ``;``.
HOME_RE = re.compile(r"^\s*const\s+%s\s*=\s*(.+?);\s*$" % HOME_NAME, re.MULTILINE)
#: The line of the imported name, and the line that carries the name of the name.
IMPORT_RE = re.compile(r"\bimport\b")
#: The published seam of the page, and the key the adapter reads on it.
SEAM = "window.ConsoleRules"
SEAM_KEY = "builtInDataset"
#: The python home of the same word: the module, the name and the statement.
PY_HOME = "src/datasets.py"
PY_HOME_NAME = HOME_NAME
PY_HOME_FORM = '%s = "%s"' % (HOME_NAME, DATASET)
#: The four readers of the home name in the page pair, as ``(file, line, kind)``.
#: The home line is no reader: it is the statement the others read.  A moved or a
#: lost site restates itself in :data:`SITES`.
SITES = (
    (HOME_FILE, 67, "state-seed"),
    (HOME_FILE, 487, "dataset-pick"),
    (HOME_FILE, 552, "cloth-gate"),
    (HOME_FILE, 1064, "anchors-gate"),
    (HOME_FILE, 1345, "anchor-select-gate"),
    (ADAPTER_FILE, 750, "layer-gate"),
    (ADAPTER_FILE, 1301, "panel-gate"),
)
#: The two sites of the adapter read the published seam, and not a copy of the id.
SEAM_SITES = (ADAPTER_FILE, ADAPTER_FILE)
#: The published seam itself, the statement that publishes it, and the whitespace
#: that may stand inside its row.
SEAM_READ = "%s()" % SEAM_KEY
SEAM_LINE_FORM = "%s: %s" % (SEAM_KEY, HOME_NAME)
#: The same row without whitespace, because the row stands inside an object
#: literal that may break a line.
SEAM_TIGHT_FORM = "%s:%s" % (SEAM_KEY, HOME_NAME)
EXPORT_RE = re.compile(r"^%s = \{" % re.escape(SEAM))
WHITESPACE = re.compile(r"\s+")
#: The lines of the page that may spell the id, where a line is the home of one
#: file.  The adapter holds no home, so no line of it may spell the id.
HOME_LINES = {HOME_FILE: (HOME_LINE,), ADAPTER_FILE: ()}
#: The javascript files the walk reads, and the floor that keeps a vacuous walk
#: from passing.  ``annotator/*.js`` holds the page scripts; ``tests/`` holds the
#: cases, so the walk skips a path under it for the reason a copy there proves
#: nothing about the shipped page.
JS_WALKED = ("annotator/*.js",)
JS_FILE_FLOOR = 5
#: The line of a one-line comment, and of a block comment.
COMMENT_START = ("//", "*", "/*")
#: The regex of the pinned ``git grep`` of this lane.  The longer tokens of the
#: tree (``calib_vod30.json``, ``seeds_only_vod30``, ``liveChoice='dataset:vod30'``)
#: do not answer this pattern.
BARE = "'%s'" % DATASET


def source_text(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one file, so a report can quote the offender."""
    return source_text(relative).splitlines()


def report(where: str, line: int, text: str, why: str) -> str:
    """One offender, as ``path:line`` with the text of that line."""
    return "%s:%d: %s  <- %s" % (where, line, (text or "").strip(), why)


def is_prose(line: str) -> bool:
    """True when the line is a comment, so it may name the dataset freely."""
    return line.strip().startswith(COMMENT_START)


def bare_sites(text: str, where: str) -> list:
    """Every code site of the bare literal, as ``(line, kind, occurrences)``.

    A comment is prose: it may name the dataset, and the comment above the home
    (:60-63) states the rule of the row itself.  A line of code that spells the
    literal is a copy of the id, and the count of the line is the count of the
    copies on it.
    """
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        bare = line.count(BARE)
        if not bare or is_prose(line):
            continue
        if number in HOME_LINES.get(where, ()):
            found.append((number, "home", bare))
            continue
        if IMPORT_RE.search(line):
            found.append((number, "import", bare))
            continue
        found.append((number, "read", bare))
    return found


def copies(relative: str, text: str, allowed=()) -> list:
    """Every line of one file that spells the id in code outside its home.

    A line of ``allowed`` is the home of that file, so it may spell the id.  A
    comment is no copy.  Every other line that spells the id is a copy, and the
    answer names it with its line and its text.  The text under the report is the
    text this function read, so a planted copy reports the planted line.
    """
    lines = text.splitlines()
    offenders = []
    for line, kind, count in bare_sites(text, relative):
        if kind in ("home", "import") or line in allowed:
            continue
        offenders.append(report(relative, line, lines[line - 1],
                                "%r is a bare copy of the built-in dataset id (%d on this "
                                "line); read %s of %s"
                                % (BARE, count, HOME_NAME, HOME_FILE)))
    return offenders


def file_copies(relative: str) -> list:
    """The copies of the id that stand in one file of this repository."""
    return copies(relative, source_text(relative), HOME_LINES.get(relative, ()))


def home_line() -> tuple:
    """The line and the text of the one declaration of the page home."""
    found = [(number, text)
             for number, text in enumerate(source_lines(HOME_FILE), start=1)
             if HOME_RE.match(text)]
    if len(found) != 1:
        raise AssertionError(
            "%s declares %s on %d lines; the page home is one line: %s"
            % (HOME_FILE, HOME_NAME, len(found),
               [number for number, _ in found] or "none"))
    return found[0]


def page_word() -> str:
    """The word the page home holds, read from the text of its declaration."""
    number, text = home_line()
    match = HOME_RE.match(text)
    if match is None or match.group(1).strip() != "'%s'" % DATASET:
        raise AssertionError(report(HOME_FILE, number, text,
                                    "the home of the page must read %r" % HOME_FORM))
    return DATASET


def py_value_sites() -> list:
    """Every python line of the tree that holds the id as a string constant.

    The walk reads the syntax tree, so a comment and a docstring are no site of
    it.  The line of the python home is the one assignment of the name; the
    lines of the other modules are the readers of that name, and another lane
    owns them.  This guard reports the home, and the fact that the row has no
    second home in the module that owns the word.
    """
    where = PY_HOME
    text = source_text(where)
    lines = text.splitlines()
    found = []
    for node in ast.walk(ast.parse(text, filename=where)):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == PY_HOME_NAME
                for target in node.targets):
            if isinstance(node.value, ast.Constant) and node.value.value == DATASET:
                found.append((node.lineno, "home"))
            continue
        if isinstance(node, ast.Constant) and node.value == DATASET:
            found.append((node.lineno, "value"))
    offenders = []
    homes = [line for line, kind in found if kind == "home"]
    if not homes:
        offenders.append(report(where, 1, lines[0] if lines else "",
                                "no line of %s assigns the string %r to %s"
                                % (where, DATASET, PY_HOME_NAME)))
    for line, kind in sorted(set(found)):
        if kind == "value" and line not in homes:
            offenders.append(report(where, line, lines[line - 1],
                                    "%r stands outside the home %s of %s"
                                    % (BARE, PY_HOME_NAME, where)))
    return offenders


def walked() -> list:
    """Every javascript file of the page walk, as paths from the root.

    The walk reads ``annotator/*.js``.  It skips a cache directory and every
    path under ``tests/``, because a copy in a test case proves nothing about
    the shipped page.
    """
    found = []
    for pattern in JS_WALKED:
        for path in sorted(ROOT.glob(pattern)):
            parts = path.relative_to(ROOT).parts
            if any(part == "__pycache__" or part == ".git" for part in parts):
                continue
            if "tests" in parts:
                continue
            found.append(path.relative_to(ROOT).as_posix())
    return found


#: The identifier of a read of the home name, and of a read of the published seam.
NAME_RE = re.compile(r"\b%s\b" % HOME_NAME)
SEAM_NAME_RE = re.compile(r"\b%s\b" % SEAM_KEY)


def reads_of_the_home(relative: str, number: int) -> list:
    """Every site identifier of one line, as ``(identifier, line)``.

    The page names the home, ``BUILT_IN_DATASET``.  The adapter cannot reach a
    constant of another file, so it reads the published seam,
    ``window.ConsoleRules.builtInDataset``, and the name of that reader is the
    second accepted spelling.  Any other identifier of the same line is the
    offender, and no identifier is a lost site.
    """
    lines = source_lines(relative)
    text = lines[number - 1]
    found = [(name, number) for name in NAME_RE.findall(text)]
    if not found:
        found = [(name, number) for name in SEAM_NAME_RE.findall(text)]
    return found


class HomeTests(unittest.TestCase):
    """The page home: its line, its text and the word it holds."""

    def test_the_home_stands_at_the_pinned_line(self):
        """``annotator/app.js:64`` holds the declaration, byte for byte."""
        number, text = home_line()
        self.assertEqual(HOME_LINE, number,
                         report(HOME_FILE, number, text,
                                "the home of the page lies at %d, not %d"
                                % (number, HOME_LINE)))
        self.assertEqual(HOME_FORM, text.strip(),
                         report(HOME_FILE, number, text,
                                "the home of the page must read %r" % HOME_FORM))

    def test_the_comment_above_the_home_states_the_rule(self):
        """The lines above the home say what the word is and who owns it."""
        lines = source_lines(HOME_FILE)
        text = " ".join(lines[number - 1] for number in (60, 61, 62, 63))
        offenders = [report(HOME_FILE, number, lines[number - 1],
                            "the comment above the home does not say %r; it says %r"
                            % (word, text))
                     for word in ("src/datasets.py", "owns", "second copy")
                     if word not in text]
        offenders.extend(report(HOME_FILE, number, lines[number - 1],
                                "the line above the home is no comment")
                         for number in (60, 61, 62, 63)
                         if not is_prose(lines[number - 1]))
        self.assertEqual([], offenders,
                         "the comment above the page home does not hold:\n"
                         + "\n".join(offenders))

    def test_the_page_home_holds_the_shipped_id(self):
        """The declaration carries the id of the built-in recording."""
        number, text = home_line()
        self.assertEqual(DATASET, page_word(),
                         report(HOME_FILE, number, text,
                                "the page home holds another word than %r" % DATASET))

    def test_the_python_home_holds_the_same_word(self):
        """The pair: ``src/datasets.py`` states the word the page states.

        The page and the module cannot import each other, so each holds one
        line, and this case is the pin that holds the two lines to one word.
        """
        offenders = py_value_sites()
        if offenders:
            self.fail("the python home of the word moved:\n" + "\n".join(offenders))
        text = source_text(PY_HOME)
        if PY_HOME_FORM not in text:
            lines = text.splitlines()
            self.fail(report(PY_HOME, 1, lines[0] if lines else "",
                             "no line of %s defines %s as %r; add %s above STATIC, the "
                             "registry that owns the word, and let STATIC read it"
                             % (PY_HOME, PY_HOME_NAME, DATASET, PY_HOME_FORM)))
        self.assertEqual(DATASET, page_word(),
                         "%s states %s and the page states %r"
                         % (PY_HOME, DATASET, page_word()))


class SiteTests(unittest.TestCase):
    """Every other site of the page pair reads the home name."""

    def test_every_site_reads_the_home_name(self):
        """The nine sites, each at its pinned line, each naming one home."""
        offenders = []
        for where, number, kind in SITES:
            if not reads_of_the_home(where, number):
                offenders.append(report(where, number, source_lines(where)[number - 1],
                                        "the %s site reads no home of the built-in dataset id"
                                        % kind))
        self.assertEqual([], offenders,
                         "a site of the built-in dataset id does not read the home:\n"
                         + "\n".join(offenders))

    def test_the_page_reads_the_home_at_the_pinned_lines(self):
        """The count of the reads of this lane, so a lost site is no silence."""
        pinned = [(where, number) for where, number, _ in SITES]
        self.assertEqual(7, len(pinned),
                         "the lane pins %d read sites, not the 7 outside the home"
                         % len(pinned))
        offenders = []
        for where, number in pinned:
            if not reads_of_the_home(where, number):
                offenders.append(report(where, number, source_lines(where)[number - 1],
                                        "the site moved away from line %d" % number))
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_adapter_reads_the_published_seam(self):
        """The adapter asks ``window.ConsoleRules.builtInDataset``, not a copy."""
        lines = source_lines(ADAPTER_FILE)
        found = [number for number, text in enumerate(lines, start=1)
                 if text.startswith("const %s = " % SEAM_KEY)]
        self.assertEqual(1, len(found),
                         "%s declares %s on %d lines: %r"
                         % (ADAPTER_FILE, SEAM_KEY, len(found), found))
        number = found[0]
        text = lines[number - 1]
        self.assertIn(SEAM, text,
                      report(ADAPTER_FILE, number, text,
                             "the reader of the adapter does not ask %s" % SEAM))
        offenders = []
        for _, site, kind in SITES:
            if kind in ("layer-gate", "panel-gate") and SEAM_READ not in lines[site - 1]:
                offenders.append(report(ADAPTER_FILE, site, lines[site - 1],
                                        "the %s does not read %s()" % (kind, SEAM_READ)))
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_home_publishes_the_seam(self):
        """The seam carries the home name, so the adapter reads one word.

        The published object stands on three lines, so the read is its body and
        not one line: the row lives between the ``window.ConsoleRules = {`` line
        and its ``};`` line.  The report names the line of the row.
        """
        lines = source_lines(HOME_FILE)
        start = next((number for number, line in enumerate(lines, start=1)
                      if EXPORT_RE.match(line)), None)
        if start is None:
            self.fail(report(HOME_FILE, HOME_LINE, lines[HOME_LINE - 1],
                             "the page publishes no %s at all" % SEAM))
        end = next(number for number in range(start, len(lines) + 1)
                   if lines[number - 1].rstrip().endswith("};"))
        body = WHITESPACE.sub("", "".join(lines[start - 1:end]))
        self.assertIn(SEAM_TIGHT_FORM, body,
                      report(HOME_FILE, start, lines[start - 1],
                             "the published seam of the page carries no %r" % SEAM_LINE_FORM))
        rows = [number for number in range(start, end + 1)
                if SEAM_TIGHT_FORM in WHITESPACE.sub("", lines[number - 1])]
        self.assertEqual(1, len(rows),
                         report(HOME_FILE, start, lines[start - 1],
                                "the seam row %r stands on %d lines, not one"
                                % (SEAM_LINE_FORM, len(rows))))


class WalkTests(unittest.TestCase):
    """The anti-copy walk of the page, with its planted proofs."""

    def test_no_other_code_line_of_the_pair_spells_the_id(self):
        """One home on the page, and every other spelling in code is an offender."""
        offenders = []
        for relative in PAGE_FILES:
            allowed = HOME_LINES.get(relative, ())
            offenders.extend(copies(relative, source_text(relative), allowed))
        self.assertEqual([], offenders,
                         "a second home of the built-in dataset id stands on the page:\n"
                         + "\n".join(offenders))

    def test_the_home_is_the_one_spelling_of_the_pair(self):
        """The home line is the only line of the pair that spells the id."""
        sites = [(relative, line, kind, count)
                 for relative in PAGE_FILES
                 for line, kind, count in bare_sites(source_text(relative), relative)]
        homes = [site for site in sites if site[2] == "home"]
        self.assertEqual([(HOME_FILE, HOME_LINE, "home", 1)], homes,
                         "the home of the pair is %r, not %r"
                         % (homes, [(HOME_FILE, HOME_LINE, "home", 1)]))
        others = [site for site in sites if site[2] != "home"]
        self.assertEqual([], others,
                         "the pair spells the id in code outside its home: %r" % (others,))
        self.assertEqual(1, sum(count for _, _, _, count in sites),
                         "the pair spells the id %d times, not once"
                         % sum(count for _, _, _, count in sites))

    def test_the_walk_reads_the_page_tree(self):
        """The walk must read the page scripts, or it proves nothing."""
        files = walked()
        self.assertGreater(len(files), JS_FILE_FLOOR,
                           "the walk read %d javascript files of the page; it is not the "
                           "tree" % len(files))
        for relative in PAGE_FILES:
            self.assertIn(relative, files,
                          "the walk does not read %s" % relative)

    def test_the_walk_reports_a_planted_copy(self):
        """Honesty: a planted copy becomes an offender, named with its line."""
        planted = ("function step(s) {\n"
                   "  const gated = s.dataset !== '%s';\n"
                   "  return gated;\n"
                   "}\n" % DATASET)
        offenders = copies(ADAPTER_FILE, planted)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("%s:2: " % ADAPTER_FILE), offenders[0])
        self.assertIn(BARE, offenders[0])
        self.assertIn("s.dataset", offenders[0])
        self.assertIn(HOME_NAME, offenders[0])

    def test_the_walk_accepts_the_home_spelling(self):
        """The home name is no copy, and a comment may name the dataset."""
        planted = ("// the %s recording is the built-in dataset\n"
                   "function step(s) {\n"
                   "  return s.dataset === %s;\n"
                   "}\n" % (DATASET, HOME_NAME))
        self.assertEqual([], copies(ADAPTER_FILE, planted),
                         "a comment or the home name counts as a bare copy")
        self.assertEqual([], bare_sites(planted, ADAPTER_FILE),
                         "the home name is read as a bare spelling of the id")


if __name__ == "__main__":
    unittest.main()
