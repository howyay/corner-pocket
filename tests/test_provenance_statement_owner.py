"""The machine provenance sentence has one home, and the console reads the flags.

Round 104 measured the defect.  One sentence stood in two live copies, and no case
read both of them.  The writer was `src/dense_queue.py:371`, inside
`def provenance(artifact, extra: dict) -> dict:`, and the reader was the console
`provenanceLine` of `annotator/vision-stage.js`.  The console held a second copy
in the `provenanceMachineLegacy` row of its two COPY tables and matched that row
against the stored sentence, in this shape:

* `const statement = p.statement ? String(p.statement) : (...)`; then
* `const known = [COPY.en.provenanceMachine, COPY.zh.provenanceMachine,
  COPY.en.provenanceMachineLegacy, COPY.zh.provenanceMachineLegacy].includes(statement)`.

The match made the sentence TEXT a recognition key.  A reworded sentence in the
module switched the key off, and a 中文 console then printed the raw English text.
The tree-wide search for the sentence returned exactly four lines
(`annotator/vision-stage.js:158`, `src/dense_queue.py:371`, and two lines of
`tests/test_app_timeline.js`), and `grep -c dense_queue tests/test_app_timeline.js`
answered `0`, so the only case that spelled the sentence never opened the module
that writes it.

The repair gives the sentence one home: the module.  The two flags are the
contract.  `provenanceLine` reads `p.machine_produced` and `p.human_confirmed`,
prints the translated label for a machine candidate whatever the sentence says,
and prints a stored sentence verbatim only when no flag claims it.  The legacy
COPY rows are gone from both tables.  The stored sentence stays reachable: the
`title` of the provenance div still carries `p.statement`.

The cases below hold that shape by reading the shipped text of the two sides.  The
sentence is not spelled by hand here: it is the value the writer itself holds, read
with `ast` and located by the function name `provenance`.

What a text scan cannot see, and this module therefore does not claim:

* it reads text, not behaviour, and not a browser.  The behaviour of the two
  branches is held by `tests/test_app_timeline.js`;
* a value built at run time from parts no literal holds stays invisible to every
  scan here.  A key built as `"state" + "ment"`, or a sentence assembled from two
  literals, is not found;
* the flag case reads the source text of `provenanceLine` in one window.  A
  function that reads the flags through another name, and keeps the same order of
  two branches, passes that shape check;
* the console scope is `annotator/*.js` and `annotator/*.html`, which is wider
  than the script list of one page but narrower than the repository: it says
  nothing about an untracked demo page under `viz/`, and nothing about a JSON or
  markdown copy of the sentence.

Run: ``./scripts/pool-test.sh python test_provenance_statement_owner``
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The module that writes the sentence and the two flags.  It is the one home.
MODULE = "src/dense_queue.py"

#: The function of the module that builds the provenance payload.
MODULE_FUNCTION = "provenance"

#: The console file that holds the provenance line and the two COPY tables.
CONSOLE = "annotator/vision-stage.js"

#: The function of the console that decides what the operator reads.
CONSOLE_FUNCTION = "provenanceLine"

#: The key of the sentence, and the two flags that are the contract.  A scan reads
#: these three names, so no case below spells the sentence itself.
STATEMENT_KEY = "statement"
FLAG_KEYS = ("machine_produced", "human_confirmed")

#: The shipped console text the page can load.  The scan reads all of it, so a
#: copy in any console file fails, and not only a copy in the two COPY tables.
CONSOLE_FILES = tuple(sorted(
    path.relative_to(ROOT).as_posix()
    for pattern in ("annotator/*.js", "annotator/*.html")
    for path in ROOT.glob(pattern)
))

#: Every shipped python module of the two packages that can write a payload.  The
#: test tree is not shipped code, and `.venv` is a third-party tree.
MODULE_FILES = tuple(sorted(
    path.relative_to(ROOT).as_posix()
    for package in ("src", "annotator")
    for path in (ROOT / package).rglob("*.py")
    if "__pycache__" not in path.parts
))

#: The statement text, the two line numbers and the key count measured in
#: `src/dense_queue.py` on 2026-10-13, at commit `9aa5cbb`.  These four values pin
#: the scan open: a scan that reads no file reports no offender, and no offender
#: must not pass for a clean tree.
STATEMENT_TEXT = "machine-produced candidate; no human has confirmed it"
STATEMENT_LINE = 371
FLAG_LINES = (369, 370)
STATEMENT_KEY_COUNT = 1

#: The console file count, the module file count and the shortest console file
#: measured on the same day.  The module count covers the two packages of
#: `MODULE_FILES` only, so it is lower than a count that also reads `tools/` and
#: `scripts/`.  Round 105 added `src/tiny_ball_probe.py`, so that count moved
#: 284 -> 285.
CONSOLE_FILE_COUNT = 11
MODULE_FILE_COUNT = 285
SHORTEST_CONSOLE_FILE = 500

#: A fragment of the sentence that no console file may hold.  It is the marker of
#: the second copy: the two spellings of the deleted key, the sentence itself, and
#: a prefix of it that a shortened copy would keep.
FORBIDDEN_FRAGMENTS = (
    "provenanceMachineLegacy",
    "machine-produced candidate",
    "no human has confirmed it",
)

#: The label a machine candidate prints, in the two languages.  The two values pin
#: the words the operator reads, so a silent edit of a COPY table fails here.
MACHINE_LABEL_EN = "suggested by the computer · not yet confirmed by a person"
MACHINE_LABEL_ZH = "电脑识别的候选 · 尚未经人工确认"

#: The `path:line: <text>` shape of every offender this module reports.
LOCATION = re.compile(r"^(?P<path>[^\s:]+):(?P<line>\d+): (?P<text>.*)$")

#: One string literal of a source text, with its opening quote of three kinds.
STRING = re.compile(r"'([^'\n]*)'|\"([^\"\n]*)\"")


def read(relative):
    """The text of one file of this checkout."""
    return (ROOT / relative).read_text(encoding="utf-8")


def function_span(text, name):
    """The body of `function <name>(...) {...}` in one piece of source text.

    The function is located by its name, never by a line number, so an edit above
    it does not move the cases that read it.
    """
    header = re.search(r"function\s+%s\s*\(" % re.escape(name), text)
    if header is None:
        return None, None
    opening = text.find("{", header.end())
    if opening < 0:
        return None, None
    depth = 0
    for index in range(opening, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[opening:index + 1], opening
    return None, None


def string_values(text):
    """Every string literal in one piece of source text, in the order of the text."""
    found = []
    for match in STRING.finditer(text):
        value = next(group for group in match.groups() if group is not None)
        found.append((match.start(), value))
    return found


def dictionary_keys(tree):
    """Every string key of every dictionary literal of a syntax tree.

    Each answer is `(key, line)`.  A key that is built at run time is not a
    literal and stays invisible here.
    """
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                found.append((key.value, key.lineno))
    return found


def function_of(tree, name):
    """The first function of one syntax tree with this name, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def payload(body):
    """The key, the line and the value of the sentence of the writer.

    The reader finds `def provenance(...)` by its name, reads the dictionary it
    returns, and takes the one key whose name is `statement`.  The value is the
    sentence the module writes, so no case below spells it by hand.
    """
    for node in ast.walk(body):
        if not isinstance(node, ast.Dict):
            continue
        found = {}
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            if not isinstance(value, ast.Constant):
                continue
            found[key.value] = (key.lineno, value.value)
        if STATEMENT_KEY in found:
            return found
    return {}


def offenders(text, path, fragments):
    """Every line of one text that carries a forbidden fragment.

    One offending line gives one entry, and the entry repeats the line, so a
    reader sees why the line failed without opening the file.
    """
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        if any(fragment in line for fragment in fragments if fragment):
            found.append("%s:%d: %s" % (path, number, line.strip()))
    return found


def statement_sites():
    """Every shipped python module that writes a `"statement"` key, with its lines.

    The answer is a sorted list of `(path, line)`, one entry for each literal key
    of each module of `MODULE_FILES`.
    """
    found = []
    for path in MODULE_FILES:
        tree = ast.parse(read(path), filename=path)
        for key, number in dictionary_keys(tree):
            if key == STATEMENT_KEY:
                found.append((path, number))
    return sorted(found)


def fragments_of(text, fragments):
    """The fragments of one list that one text holds, in the order of the list."""
    return [fragment for fragment in fragments if fragment in text]


def conditions_reading(body_text, name):
    """Every line of a function body whose condition reads one name.

    The reader is deliberately shallow: it reads the text of each statement of
    the function, and it names the statement when the name stands in a test of
    that statement.  A condition kept in a local variable is then visible on the
    line that binds the variable.
    """
    found = []
    for line in body_text.splitlines():
        if name not in line:
            continue
        if "if " in line or "?" in line or "=" in line:
            found.append(line.strip())
    return found


class TheMachineProvenanceSentenceHasOneHome(unittest.TestCase):
    """The module owns the sentence; the console decides from the two flags."""

    @classmethod
    def setUpClass(cls):
        cls.module_text = read(MODULE)
        cls.console_text = read(CONSOLE)
        cls.console_texts = {path: read(path) for path in CONSOLE_FILES}
        cls.tree = ast.parse(cls.module_text, filename=MODULE)
        cls.owner = function_of(cls.tree, MODULE_FUNCTION)
        cls.payload = payload(cls.owner) if cls.owner is not None else {}
        cls.body = function_span(cls.console_text, CONSOLE_FUNCTION)[0]
        cls.sites = statement_sites()

    def test_the_scan_reads_the_shipped_text(self):
        """The counts hold the scan open: a scan that reads nothing cannot pass."""
        self.assertIsNotNone(self.owner, "the module has no function named %s" % MODULE_FUNCTION)
        self.assertIn(STATEMENT_KEY, self.payload,
                      "the writer holds no %r key: %s" % (STATEMENT_KEY, sorted(self.payload)))
        self.assertEqual(len(self.sites), STATEMENT_KEY_COUNT,
                         "the writer count moved: %s" % (self.sites,))
        self.assertEqual(self.payload[STATEMENT_KEY][0], STATEMENT_LINE,
                         "the sentence line moved: %s" % (self.payload[STATEMENT_KEY],))
        self.assertEqual(len(MODULE_FILES), MODULE_FILE_COUNT,
                         "the scanned module count moved: %d" % len(MODULE_FILES))
        self.assertEqual(len(CONSOLE_FILES), CONSOLE_FILE_COUNT,
                         "the scanned console file count moved: %s" % (CONSOLE_FILES,))
        self.assertIn(CONSOLE, CONSOLE_FILES, "the console file is not in the scanned list")
        self.assertIn(MODULE, MODULE_FILES, "the writer is not in the scanned list")
        for path, text in self.console_texts.items():
            self.assertGreater(len(text), SHORTEST_CONSOLE_FILE, "%s is almost empty" % path)
        for path, _number in self.sites:
            self.assertTrue(read(path).strip(), "%s is empty" % path)
        self.assertEqual(FORBIDDEN_FRAGMENTS,
                         ("provenanceMachineLegacy", "machine-produced candidate",
                          "no human has confirmed it"),
                         "the fragment list moved, so the scan reads less than it says")
        self.assertEqual(self.console_text.count("provenanceMachine:'"), 2,
                         "the two COPY tables no longer hold the machine label")
        self.assertIn(MACHINE_LABEL_EN, self.console_text,
                      "the English label is gone, so the machine row prints a raw sentence")
        self.assertIn(MACHINE_LABEL_ZH, self.console_text,
                      "the Chinese label is gone, so a Chinese operator reads English")

    def test_the_flags_stand_beside_the_sentence(self):
        """The two flags and the sentence are three literal keys of one payload."""
        self.assertEqual(self.payload[STATEMENT_KEY][1], STATEMENT_TEXT,
                         "the sentence moved: %r" % (self.payload[STATEMENT_KEY][1],))
        for key, expected in zip(FLAG_KEYS, (True, False)):
            self.assertIn(key, self.payload, "the payload holds no %r key: %s" % (key, sorted(self.payload)))
            self.assertIs(self.payload[key][1], expected, "the value of %r moved" % key)
        self.assertEqual(tuple(self.payload[key][0] for key in FLAG_KEYS), FLAG_LINES,
                         "the flag lines moved: %s" % ({key: self.payload[key][0] for key in FLAG_KEYS},))
        for key in FLAG_KEYS:
            self.assertIn(key, [name for name, _number in dictionary_keys(self.tree)],
                          "the name %r is not a literal key of the module" % key)

    def test_one_shipped_module_writes_the_key(self):
        """The one site of the sentence key is the writer of this rule."""
        self.assertEqual([path for path, _number in self.sites], [MODULE],
                         "a second module writes the key: %s" % (self.sites,))
        for path, number in self.sites:
            self.assertIn('"%s"' % STATEMENT_KEY, read(path).splitlines()[number - 1],
                          "the reported line does not hold the key: %s:%d" % (path, number))

    def test_no_console_file_holds_the_sentence(self):
        """No shipped console file holds the sentence or the deleted key name."""
        found = []
        for path, text in self.console_texts.items():
            found.extend(offenders(text, path, FORBIDDEN_FRAGMENTS))
        self.assertEqual(found, [], "the console holds a copy: %s" % found)

    def test_the_statement_fragment_has_one_source(self):
        """The sentence fragment answers one count, and it is the writer alone."""
        module_hits = offences_in_one_text(self.module_text, MODULE)
        self.assertEqual(len(module_hits), 1,
                         "the writer holds the sentence %d times: %s" % (len(module_hits), module_hits))
        self.assertIn(FORBIDDEN_FRAGMENTS[1], module_hits[0], "the one site is not the sentence")

    def test_provenance_line_reads_the_flags(self):
        """The console decides from the two flags, and never from the sentence."""
        self.assertIsNotNone(self.body, "the console has no function named %s" % CONSOLE_FUNCTION)
        self.assertIn("p.machine_produced", self.body, "the machine flag decides the label")
        self.assertIn("p.human_confirmed", self.body, "the human flag decides the label")
        for line in conditions_reading(self.body, "machine_produced"):
            self.assertIn("human_confirmed", line,
                          "a condition reads the machine flag alone, so a confirmed row reads as a machine row: %s" % line)
        self.assertNotIn("provenanceMachineLegacy", self.body, "the deleted key is back in the function")
        self.assertNotIn("COPY", self.body, "the function reads a COPY table again")
        self.assertNotIn(".includes(", self.body, "the function matches the sentence text again")
        for _position, literal in string_values(self.body):
            self.assertEqual(fragments_of(literal, FORBIDDEN_FRAGMENTS), [],
                             "a forbidden sentence stands in the function body: %r" % literal)

    def test_the_title_keeps_the_stored_sentence(self):
        """The provenance div still hands the stored sentence to the operator."""
        self.assertIsNotNone(self.body, "the console has no function named %s" % CONSOLE_FUNCTION)
        self.assertIn("title=", self.body, "the provenance div has no title")
        self.assertIn("p.statement", self.body, "the title no longer carries the stored sentence")
        self.assertIn("<div class=\"vs-prov", self.body, "the provenance div is gone")

    def test_a_planted_sentence_in_the_console_text_is_reported(self):
        """A planted copy in a text copy is reported as `path:line: <text>`."""
        lines = self.console_text.splitlines()
        planted = "\n".join(lines + [
            "const X_PROVENANCE_BITE = {",
            "  provenanceMachineLegacy:'" + STATEMENT_TEXT + "',",
            "  other:'" + STATEMENT_TEXT + "'};",
        ]) + "\n"
        found = offenders(planted, CONSOLE, FORBIDDEN_FRAGMENTS)
        self.assertEqual(len(found), 2, "the two planted copies are not reported: %s" % found)
        for entry in found:
            match = LOCATION.match(entry)
            self.assertIsNotNone(match, "the report shape moved: %s" % entry)
            self.assertEqual(match.group("path"), CONSOLE)
            self.assertIn(STATEMENT_TEXT, match.group("text"), "the entry hides the sentence: %s" % entry)
        numbers = [int(entry.split(":")[1]) for entry in found]
        self.assertEqual(numbers, [len(lines) + 2, len(lines) + 3],
                         "the reported lines moved: %s" % found)
        self.assertEqual(len(set(numbers)), 2, "the two copies share one report: %s" % found)


def offences_in_one_text(text, path):
    """Every `path:line: <text>` report of the sentence fragment in one text."""
    return offenders(text, path, FORBIDDEN_FRAGMENTS[1:])


if __name__ == "__main__":
    unittest.main()
