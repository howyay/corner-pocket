"""The enrolment refusal sentence has one English home: the module that sends it.

Round 104 measured the defect.  One refusal sentence stood in two live copies.
The module held it (`Refusal.message()` of `src/enroll_from_tracklet.py`, the two
answers of `EnrollmentTokenError.to_dict()`, and the `preview_expired` answer of
`annotator/unified_server.py`), and the console held a second English copy in the
`ENROL_REASON_COPY` table of `annotator/vision-stage.js`.  Seven of the twelve
console rows had already drifted from the module, and no case read both copies:
`grep -rn "ENROL_REASON_COPY|enrolReasonText" tests/` printed nothing.

The repair gives the sentence one home for each language:

* the module keeps the English sentence, and the wire carries it;
* the console table keeps the Chinese translation only, one row for each code;
* `enrolReasonText` reads the wire message for `en` and for every other language,
  and reads the table for `zh` alone.

The cases below hold that shape by reading the shipped text of the two sides.  The
sentences are not read from a hand-written copy: the module is imported, and each
sentence is the value the module itself builds.  Therefore an f-string that
interpolates `MIN_EYE_PX` or `MIN_DET_SCORE` is compared as the reader sees it.

What a text scan cannot see, and this module therefore does not claim:

* it reads text, not behaviour.  It cannot see what a browser renders;
* a sentence built at run time from parts no literal holds stays invisible to the
  sentence scan.  The code list covers the codes; the sentences cover the text;
* the scan reads `annotator/*.js` and `annotator/*.html`, which is wider than the
  script list of one page.  It says nothing about a sentence in a page that does
  not load the console;
* a Chinese row that is a poor translation passes.  The case checks that a row
  exists, that the row count equals the code count, and that the row carries a CJK
  character.  It cannot judge the meaning;
* the case that locates `enrolReasonText` reads its source text.  A function that
  reads the wire message through another name, and keeps the same order of the two
  branches, passes the shape check.

Run: ``./scripts/pool-test.sh python test_enrol_reason_copy_owner``
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The module that writes the English sentence and sends it on the wire.
MODULE = "src/enroll_from_tracklet.py"

#: The route that answers `preview_expired` with its own sentence.
ROUTE = "annotator/unified_server.py"

#: The console file that holds the translation table.
CONSOLE = "annotator/vision-stage.js"

#: The shipped console text the page can load.  The scan reads all of it, so a
#: second English copy in any console file fails, not only a copy in the table.
CONSOLE_FILES = tuple(sorted(
    path.relative_to(ROOT).as_posix()
    for pattern in ("annotator/*.js", "annotator/*.html")
    for path in ROOT.glob(pattern)
))

#: The code of the route answer above.  The module cannot build it.
ROUTE_CODE = "preview_expired"

#: The literal answer of the route, measured at `annotator/unified_server.py:1208`.
#: The route is not imported: a case that imports the server starts it.
ROUTE_MESSAGE = "this preview is no longer held; preview the track again before confirming"

#: The code count, the row count and the sentence count measured on 2026-10-13.
#: The counts hold the scan open: a scan that reads no file reports zero offenders,
#: and zero offenders must not pass for a clean tree.
CODE_COUNT = 12
ROW_COUNT = 12
SENTENCE_COUNT = 12

#: The console file count and the shortest file, measured on 2026-10-13.
CONSOLE_FILE_COUNT = 11
SHORTEST_CONSOLE_FILE = 500

#: A sentence a console file must not hold.  A shorter value is a token, not a
#: sentence: `ok` and `none` of another map would match half of `annotator/*.js`.
SENTENCE_MINIMUM = 15

#: The `path:line: <text>` shape of every offender this module reports.
LOCATION = re.compile(r"^(?P<path>[^\s:]+):(?P<line>\d+): (?P<text>.*)$")

#: A CJK ideograph, in the blocks the table uses.
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

#: One row of the console table: `code:'sentence'` or `code:['sentence']`.
ROW = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+?),?\s*$")

STRING = re.compile(r"'([^']*)'|\"([^\"]*)\"|`([^`]*)`", re.S)


def read(relative):
    """The text of one file of this checkout, with its line endings kept."""
    return (ROOT / relative).read_text(encoding="utf-8")


def string_values(text):
    """Every string literal in one piece of source text, in the order of the text."""
    found = []
    for match in STRING.finditer(text):
        value = next(group for group in match.groups() if group is not None)
        found.append((match.start(), value))
    return found


def function_span(text, name):
    """The body of `function <name>(...) {...}` in one piece of source text.

    The function is located by its name, never by a line number, so an edit above
    it does not move the case that reads it.
    """
    header = re.search(r"function\s+%s\s*\(" % re.escape(name), text)
    if header is None:
        return None
    opening = text.find("{", header.end())
    if opening < 0:
        return None
    depth = 0
    for index in range(opening, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[opening:index + 1]
    return None


def is_text(node):
    """True when one syntax node builds a text: a literal, or an f-string."""
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)) or isinstance(node, ast.JoinedStr)


def string_dicts(node):
    """Every dict of one syntax node whose keys and values are texts.

    The reader finds the map that pairs a code with a sentence.  A dict that
    carries any other answer of the same function is not that map.  `is_text`
    accepts an f-string, so a sentence that interpolates a gate constant stays in
    the map and is read as the reader of the wire sees it.
    """
    found = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Dict) or not child.keys:
            continue
        if not all(is_text(key) and is_text(value)
                   for key, value in zip(child.keys, child.values)):
            continue
        found.append(child)
    return found


def message_map(text, namespace):
    """The `code: <sentence>` map of `Refusal.message()`, with the line of each code.

    The reader walks the source with `ast`, finds the `message` method of the
    `Refusal` class, and evaluates each value against the names the module itself
    holds.  An f-string is therefore read as the sentence the wire carries.
    """
    tree = ast.parse(text)
    body = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Refusal":
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "message":
                body = item
    if body is None:
        return {}
    found = {}
    for mapping in string_dicts(body):
        for key, value in zip(mapping.keys, mapping.values):
            sentence = eval(compile(ast.Expression(value), "<refusal>", "eval"), {}, namespace)
            found[key.value] = (value.lineno, sentence)
    return found


def token_map(text):
    """The two `code: <sentence>` rows of `EnrollmentTokenError.to_dict()`."""
    tree = ast.parse(text)
    body = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "EnrollmentTokenError":
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "to_dict":
                body = item
    if body is None:
        return {}
    found = {}
    for mapping in string_dicts(body):
        for key, value in zip(mapping.keys, mapping.values):
            found[key.value] = (value.lineno, value.value)
    return found


def route_code(text):
    """The `preview_expired` answer of the route: `(line, code, sentence)` or None.

    The reader finds the branch that answers a plan the route no longer holds, and
    reads its return dict.  The branch is located by the code it answers.
    """
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not node.body:
            continue
        if not isinstance(node.test, ast.Compare) or not isinstance(node.test.ops[0], ast.Is):
            continue
        for child in node.body:
            if not isinstance(child, ast.Return) or not isinstance(child.value, ast.Dict):
                continue
            pairs = {}
            for key, value in zip(child.value.keys, child.value.values):
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    continue
                if not isinstance(value, ast.Constant):
                    continue
                pairs[key.value] = value.value
                if key.value == "reason" and value.value == ROUTE_CODE:
                    reason_line = value.lineno
            if "message" in pairs and pairs.get("reason") == ROUTE_CODE:
                return (reason_line, ROUTE_CODE, pairs["message"])
    return None


def codes_without_rows(code_map, rows):
    """Every code of the server that has no row in the console table.

    Each missing code is reported as `path:line: <text>`, with the line of the
    source file that holds it.
    """
    found = []
    for code in sorted(code_map):
        if code in rows:
            continue
        path, _number, sentence = code_map[code]
        found.append("%s:%d: %s" % (path, code_map[code][1], sentence))
    return found


def server_codes(module_text, route_text, namespace):
    """Every code the server can send, with the line that holds it in its own file.

    The three writers are the nine rows of `Refusal.message()` and the two rows of
    `EnrollmentTokenError.to_dict()` in the module, and the answer of the route.
    Each entry is `(path, line, sentence)`.
    """
    found = {}
    for code, (number, sentence) in message_map(module_text, namespace).items():
        found[code] = (MODULE, number, sentence)
    for code, (number, sentence) in token_map(module_text).items():
        found[code] = (MODULE, number, sentence)
    answer = route_code(route_text)
    if answer is not None:
        number, code, sentence = answer
        found[code] = (ROUTE, number, sentence)
    return found


def table_rows(console_text):
    """The rows of the console table: `(code, value text, line)`.

    The reader takes the text between the `ENROL_REASON_COPY` opening brace and its
    closing brace.  The line of the opening brace is not a row.
    """
    opening = console_text.find("const ENROL_REASON_COPY = {")
    if opening < 0:
        return []
    brace = console_text.find("{", opening)
    end = console_text.find("};", brace)
    if end < 0:
        return []
    first_row = console_text[:brace].count("\n") + 2
    rows = []
    for number, line in enumerate(console_text[:end].splitlines(), start=1):
        if number < first_row:
            continue
        match = ROW.match(line)
        if match is None:
            continue
        rows.append((match.group(1), match.group(2), number))
    return rows


def row_values(value_text):
    """Every string literal of one table value, in the order of the text."""
    return [value for _offset, value in string_values(value_text)]


def copy_offences(text, path, banned):
    """Every line of `text` that carries a banned sentence, as `path:line: <text>`.

    One offending line gives one entry.  An entry repeats the line, so a reader
    sees why the line failed without opening the file.
    """
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for sentence in banned:
            if sentence and sentence in line:
                found.append("%s:%d: %s" % (path, number, line.strip()))
                break
    return found


def banned_sentences(code_map, code):
    """The sentences a console file must not hold for one code.

    The wire message of the code is the sentence the reader sees.  The route answer
    counts with the module rows, because the console printed both.  A value shorter
    than `SENTENCE_MINIMUM` is not a sentence and holds nothing to compare.
    """
    found = {sentence for sentence in (code_map[code][2],)
             if len(sentence) >= SENTENCE_MINIMUM}
    if code == ROUTE_CODE:
        found.add(ROUTE_MESSAGE)
    return sorted(found)


class TheEnrolmentRefusalSentenceHasOneEnglishHome(unittest.TestCase):
    """The module owns the English sentence; the console owns the translation."""

    @classmethod
    def setUpClass(cls):
        # The module is imported once.  It is the owner of every English sentence
        # and of the two gate numbers, so no case states a sentence of its own.
        from src import enroll_from_tracklet as owner
        cls.owner = owner
        cls.namespace = dict(vars(owner))
        cls.module_text = read(MODULE)
        cls.route_text = read(ROUTE)
        cls.console_text = read(CONSOLE)
        cls.code_map = server_codes(cls.module_text, cls.route_text, cls.namespace)
        cls.rows = table_rows(cls.console_text)
        cls.console_texts = {path: read(path) for path in CONSOLE_FILES}

    def test_the_scan_reads_the_shipped_text(self):
        """The counts hold the scan open: a scan that reads nothing cannot pass."""
        self.assertEqual(len(self.code_map), CODE_COUNT,
                         "the server code count moved: %s" % sorted(self.code_map))
        self.assertEqual(len(self.rows), ROW_COUNT,
                         "the console row count moved: %s" % [row[0] for row in self.rows])
        self.assertEqual(len(CONSOLE_FILES), CONSOLE_FILE_COUNT,
                         "the scanned console file count moved: %s" % (CONSOLE_FILES,))
        self.assertIn(CONSOLE, CONSOLE_FILES, "the table file is not in the scanned list")
        self.assertTrue((ROOT / ROUTE).is_file(), "the route file is absent")
        for path, text in self.console_texts.items():
            self.assertGreater(len(text), SHORTEST_CONSOLE_FILE, "%s is almost empty" % path)
        for path, _number, sentence in self.code_map.values():
            self.assertTrue(sentence, "%s holds an empty sentence" % path)

    def test_every_server_code_has_a_chinese_row(self):
        """Each code the server can send has one zh row in the console table."""
        rows = {code for code, _value, _line in self.rows}
        missing = codes_without_rows(self.code_map, rows)
        self.assertEqual(missing, [], "no zh row for: %s" % missing)
        extra = sorted(rows - set(self.code_map))
        self.assertEqual(extra, [],
                         "the console translates codes the server cannot send: %s" % extra)

    def test_the_console_holds_no_english_copy(self):
        """No module sentence stands in the shipped console text."""
        offenders = []
        for code in sorted(self.code_map):
            banned = banned_sentences(self.code_map, code)
            for path, text in self.console_texts.items():
                offenders.extend(copy_offences(text, path, banned))
        self.assertEqual(offenders, [], "the console holds an English copy: %s" % offenders)
        self.assertEqual(len(self.code_map), SENTENCE_COUNT,
                         "the sentence count moved: %d" % len(self.code_map))

    def test_every_table_value_is_chinese(self):
        """Each row holds one value, and that value carries a CJK character."""
        offenders = []
        for code, value_text, line in self.rows:
            values = row_values(value_text)
            if len(values) != 1:
                offenders.append("%s:%d: %s has %d values" % (CONSOLE, line, code, len(values)))
            elif not CJK.search(values[0]):
                offenders.append("%s:%d: %s holds no CJK character: %s" % (CONSOLE, line, code, values[0]))
        self.assertEqual(offenders, [], "a row is not a translation: %s" % offenders)

    def test_enrol_reason_text_reads_the_wire_message(self):
        """The function reads the wire message off `zh`, and the table on `zh`."""
        body = function_span(self.console_text, "enrolReasonText")
        self.assertIsNotNone(body, "the console has no function named enrolReasonText")
        self.assertIn("ENROL_REASON_COPY", body, "the zh branch does not read the table")
        self.assertIn("message", body, "the non-zh branch does not read the wire message")
        self.assertIn("'zh'", body, "the function has no zh branch")
        message_at = body.find("message")
        table_at = body.find("ENROL_REASON_COPY")
        self.assertLess(message_at, table_at,
                        "the wire message must come before the table: %s" % body)

    def test_the_console_text_of_the_defect_reports_the_offender(self):
        """A planted English copy in a text copy is reported as `path:line: <text>`."""
        sentence = self.code_map["track_not_found"][2]
        lines = self.console_text.splitlines()
        planted = "\n".join(lines + [
            "const X_ENROL_REASON_BITE = {",
            "  track_not_found:['" + sentence + "'],",
            "  other:['" + sentence + "']};",
        ]) + "\n"
        offenders = copy_offences(planted, CONSOLE, banned_sentences(self.code_map, "track_not_found"))
        self.assertEqual(len(offenders), 2, "the two planted copies are not reported: %s" % offenders)
        for entry in offenders:
            match = LOCATION.match(entry)
            self.assertIsNotNone(match, "the report shape moved: %s" % entry)
            self.assertEqual(match.group("path"), CONSOLE)
            self.assertIn(sentence, match.group("text"), "the entry hides the sentence: %s" % entry)
        numbers = [int(entry.split(":")[1]) for entry in offenders]
        self.assertEqual(numbers, [len(lines) + 2, len(lines) + 3],
                         "the reported lines moved: %s" % offenders)
        self.assertEqual(len(set(numbers)), 2, "the two copies share one report: %s" % offenders)

    def test_a_new_server_code_without_a_row_fails(self):
        """A code the console cannot translate is named, with its own line."""
        anchor = "        }[self.reason]"
        self.assertEqual(self.module_text.count(anchor), 1, "the map close moved in the module")
        grown = self.module_text.replace(
            anchor,
            '            "track_not_found_x": "a new sentence the console cannot translate",\n' + anchor)
        self.assertNotEqual(grown, self.module_text, "the planted code did not land")
        grown_map = server_codes(grown, self.route_text, self.namespace)
        rows = {code for code, _value, _line in self.rows}
        missing = codes_without_rows(grown_map, rows)
        planted = [entry for entry in missing if entry.startswith("%s:" % MODULE)]
        self.assertIn("track_not_found_x", grown_map, "the planted code is not read: %s" % sorted(grown_map))
        path, number, sentence = grown_map["track_not_found_x"]
        self.assertEqual(path, MODULE)
        self.assertIn("%s:%d: a new sentence the console cannot translate" % (path, number), planted,
                      "the report does not name the line of the code: %s" % missing)
        self.assertIn("track_not_found_x", grown.splitlines()[number - 1],
                      "the reported line does not hold the code")
        self.assertEqual(sentence, "a new sentence the console cannot translate")


if __name__ == "__main__":
    unittest.main()
