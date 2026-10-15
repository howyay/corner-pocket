"""One home of the refusal sentence `unknown ball set: <set>`, and no fourth writer.

The sentence has one home: `unknown_ball_set` in `src/store_rules.py`, beside the
`unknown_record_set` of round 107 and the `unknown_dataset` of round 108.  Three
writers build the message from that home: `JsonStore._labels_path` in `src/store.py`,
`crops_dir` in `src/store_files.py`, and `PostgresStore._crop_set` in `src/store_pg.py`.
Before round 116 every one of the three held its own f-string, so one wording change had
to land in three files.

Each writer binds the home by name and calls it.  The cases below read the home, pin its
line by number and text, pin the three writer sites as `path:line` with their text, read
the binding and the call site of each writer, prove that each live writer raises the
home's sentence, and walk `src/**/*.py` and `annotator/*.py` for a second spelling.
The walk names the path, the line, and the text of every site it finds.

The wire refusal `raise APIError("unknown ball set", 404)` of
`annotator/unified_server.py:1880` is a different fact: it holds four words and no name,
and a case below holds it where it stands.  `annotator/refusals.py:214` keeps the same
four words as the key of the wire refusal, and that line stays too.

Run: ``./scripts/pool-test.sh python test_unknown_ball_set_owner``
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from src.store import JsonStore  # noqa: E402
from src.store_files import crops_dir  # noqa: E402
from src.store_pg import PostgresStore  # noqa: E402
from src.store_rules import unknown_ball_set  # noqa: E402

#: The home of the sentence, as a path under the repository root.
HOME_FILE = "src/store_rules.py"
#: The name of the home.
HOME_NAME = "unknown_ball_set"
#: The module that holds the home.
HOME_MODULE = "src.store_rules"
#: The line of the home that answers the sentence, pinned by number and by text.
HOME_LINE = 154
HOME_FORM = 'return f"unknown ball set: {crop_set}"'
#: The three writers that raise the sentence.  Each binds the home and calls it once.
WRITERS = ("src/store.py", "src/store_files.py", "src/store_pg.py")
#: Every live site of the writer set, as `path:line`, with the text of that line.  The
#: import line of each writer keeps its number: the home joined an existing import, so
#: no line moved and every pinned number of every other guard stays alive.
SITES = {
    "src/store.py": {75: "from src.store_rules import unknown_ball_set, "
                         "unknown_dataset, unknown_record_set  # noqa: E402",
                     342: "raise ValueError(unknown_ball_set(crop_set))"},
    "src/store_files.py": {36: "from src.store_rules import unknown_ball_set, unknown_dataset",
                           286: "raise ValueError(unknown_ball_set(set_name))"},
    "src/store_pg.py": {53: "from src.store_rules import unknown_ball_set, "
                            "unknown_dataset, unknown_record_set  # refusals: one home",
                        344: "raise ValueError(unknown_ball_set(crop_set))"},
}
#: The fixed part of the sentence.  The home spells this text.
SENTENCE = "unknown ball set: "
#: The sentence of the two rows that answer for a store.  `HomeTests` counts them.
ANSWER_SENTENCE = 'return f"unknown ball set: {'
#: The ball set of the probes below.  No store keeps it.
PROBE = "no-such-set"
#: The number of sites that spell the fixed part of the sentence: the home alone.
SENTENCE_SITE_COUNT = 1
#: The number of binding sites, and of call sites, of the home in one writer.
BINDING_SITE_COUNT = 1
CALL_SITE_COUNT = 1
#: The database store connects on first use, not at construction.  `_crop_set` reads the
#: registry under `root` alone, so the case below builds the store without a database.
UNUSED_URL = "postgresql:///unused"
#: The wire refusal of the console route, and the fail-closed row of the refusal table.
#: Both name the four words of the wire, and neither names a set.
WIRE_FILE = "annotator/unified_server.py"
WIRE_LINE = 1880
WIRE_REFUSAL = 'raise APIError("unknown ball set", 404)'
TABLE_FILE = "annotator/refusals.py"
TABLE_LINE = 214
TABLE_ROW = "'unknown ball set':"
#: The trees the walk reads, the subtree it skips, and the floor that keeps a walk that
#: read nothing from passing in silence.
WALKED = ("src/**/*.py", "annotator/*.py")
SKIP = ("src/sam3",)
FILE_FLOOR = 200

BINDING = re.compile(r"^\s*from\s+%s\s+import\b.*\b%s\b"
                     % (re.escape(HOME_MODULE), HOME_NAME))
CALL = re.compile(r"(?<![\w.])%s\s*\(" % HOME_NAME)
#: The shape of a second spelling: the sentence inside an f-string, and not the call of
#: the home.  The two writers of `src/store.py` and `src/store_pg.py` hold one variable
#: name and the writer of `src/store_files.py` holds another.
BARE = re.compile(r'f"unknown ball set: \{')


def text_of(relative: str) -> str:
    """The text of one file, as a path under the repository root."""
    return (ROOT / relative).read_text(encoding="utf-8")


def report(relative: str, number: int, line: str, why: str) -> str:
    """The message of one site: the path, the line, the text, and the reason."""
    return f"{relative}:{number}: {line.strip()}\n  {why}"


def sites_of(relative: str, pattern: re.Pattern, why: str) -> list:
    """The sites of one file whose line matches the pattern."""
    return [report(relative, number, line, why) for number, line in
            enumerate(text_of(relative).splitlines(), 1) if pattern.search(line)]


def bare_sites(relative: str, text: str | None = None) -> list:
    """The sites of one file that spell the sentence again, in place of the home call."""
    body = text if text is not None else text_of(relative)
    why = (f'the sentence spells "{SENTENCE}" in place of {HOME_FILE}.{HOME_NAME};'
           " read the owner's name")
    return [report(relative, number, line, why) for number, line in
            enumerate(body.splitlines(), 1) if BARE.search(line)]


def walked_files() -> list:
    """Every walked python file of the shipped tree, the generated subtree left out."""
    return sorted(path for pattern in WALKED for path in ROOT.glob(pattern)
                  if "__pycache__" not in path.parts
                  and not any(part in SKIP for part in path.relative_to(ROOT).parts))


def writer_sites() -> list:
    """The reported live writers of the sentence: every walked site but the home."""
    return [line for path in walked_files()
            if (relative := path.relative_to(ROOT).as_posix()) != HOME_FILE
            for line in bare_sites(relative)]


def answer_lines() -> list:
    """The lines of the home that answer a refusal, as `path:number: text`.

    The case that counts the sites reads them: when the home no longer spells the
    sentence, the failure names the line of the home and the text it answers today.
    """
    return [f"{HOME_FILE}:{number}: {line.strip()}" for number, line in
            enumerate(text_of(HOME_FILE).splitlines(), 1)
            if line.strip().startswith("return f")]


class HomeTests(unittest.TestCase):
    """The home answers the sentence, and its line is pinned."""

    def test_the_home_answers_the_sentence(self):
        self.assertTrue(callable(unknown_ball_set), "the home must be a function")
        self.assertEqual(SENTENCE + PROBE, unknown_ball_set(PROBE),
                         "the home must answer the sentence of one ball set")
        self.assertIn(HOME_NAME, text_of(HOME_FILE),
                      "the home must stand in its own module")

    def test_the_home_line_is_pinned_by_number_and_text(self):
        line = text_of(HOME_FILE).splitlines()[HOME_LINE - 1]
        self.assertEqual(HOME_FORM, line.strip(),
                         f"{HOME_FILE}:{HOME_LINE} no longer answers the sentence")

    def test_the_home_answers_a_refusal_of_two_rows(self):
        answers = [line for line in answer_lines() if ANSWER_SENTENCE in line]
        self.assertEqual(1, len(answers),
                         "the home must answer the sentence of one ball set:\n"
                         + "\n".join("  " + line for line in answer_lines()))
        self.assertIn(f"{HOME_FILE}:{HOME_LINE}: {HOME_FORM}", answers[0])

    def test_the_sentence_stands_once_in_the_shipped_tree(self):
        found = {}
        for path in walked_files():
            sites = bare_sites(path.relative_to(ROOT).as_posix())
            if sites:
                found[path.relative_to(ROOT).as_posix()] = sites
        total = sum(len(sites) for sites in found.values())
        self.assertEqual(SENTENCE_SITE_COUNT, total,
                         "the sentence must stand one time, and it stands in"
                         f" {sorted(found)}: {found}\n  the home answers of today:\n"
                         + "\n".join("  " + line for line in answer_lines()))
        self.assertEqual([HOME_FILE], sorted(found),
                         "the owner of the sentence must be the only file that spells it")


class WriterTests(unittest.TestCase):
    """Three writers read the home, and each one raises its sentence."""

    def test_every_writer_reads_the_home_and_calls_it(self):
        for relative in WRITERS:
            with self.subTest(writer=relative):
                self.assertEqual([], bare_sites(relative),
                                 "a writer must not spell the sentence again")
                bound = sites_of(relative, BINDING,
                                 f"this line binds {HOME_NAME} from {HOME_MODULE}")
                self.assertEqual(BINDING_SITE_COUNT, len(bound),
                                 "a writer must bind the home once:\n" + "\n".join(bound))
                called = sites_of(relative, CALL,
                                  f"this line builds the message from {HOME_NAME}")
                self.assertEqual(CALL_SITE_COUNT, len(called),
                                 "a writer must call the home once:\n" + "\n".join(called))

    def test_every_writer_site_is_pinned_by_number_and_text(self):
        for relative, pinned in SITES.items():
            with self.subTest(writer=relative):
                lines = text_of(relative).splitlines()
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer reads the home")

    def test_the_json_store_raises_the_home_sentence(self):
        with tempfile.TemporaryDirectory() as folder:
            store = JsonStore(folder)
            with self.assertRaises(ValueError) as caught:
                store.labels_get(PROBE)
        self.assertEqual(unknown_ball_set(PROBE), str(caught.exception),
                         "the file store must raise the sentence of the home")

    def test_the_files_helper_raises_the_home_sentence(self):
        with self.assertRaises(ValueError) as caught:
            crops_dir(PROBE)
        self.assertEqual(unknown_ball_set(PROBE), str(caught.exception),
                         "src/store_files.crops_dir must raise the sentence of the home")

    def test_the_postgres_store_raises_the_home_sentence(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PostgresStore(folder, url=UNUSED_URL)
            with self.assertRaises(ValueError) as caught:
                store._crop_set(PROBE)
        self.assertEqual(unknown_ball_set(PROBE), str(caught.exception),
                         "the database store must raise the sentence of the home")


class WalkTests(unittest.TestCase):
    """The walk names every second spelling, and the wire refusal stays."""

    def test_no_fourth_writer_of_the_sentence_stands_in_the_tree(self):
        found = writer_sites()
        self.assertEqual([], found,
                         "the sentence must stand in %s alone; the other writer sites"
                         " are\n%s" % (HOME_FILE, "\n".join(found)))

    def test_the_walk_reads_the_shipped_tree(self):
        """A walk that read no file would pass the case above for no reason."""
        read = [path.relative_to(ROOT).as_posix() for path in walked_files()]
        self.assertGreaterEqual(len(read), FILE_FLOOR, f"the walk read {len(read)} files")
        self.assertIn(HOME_FILE, read, "the walk must read the home")
        self.assertNotIn("src/sam3/model.py", read, "the walk must skip src/sam3")

    def test_a_planted_copy_is_reported_with_its_file_and_line(self):
        original = text_of(WRITERS[1])
        live = f"{HOME_NAME}(set_name)"
        self.assertIn(live, original, f"the live writer must call {live}")
        planted_text = original.replace(live, f'f"unknown ball set: {{set_name}}"')
        self.assertNotEqual(original, planted_text, "the plant must change the text")
        number = next(number for number, line in
                      enumerate(planted_text.splitlines(), 1) if SENTENCE in line)
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_store_files.py"
            planted.write_text(planted_text, encoding="utf-8")
            found = bare_sites(str(planted), planted_text)
        self.assertEqual(1, len(found), found)
        self.assertIn(f'{planted}:{number}: raise ValueError(f"{SENTENCE}{{set_name}}")', found[0])
        self.assertIn(f"{HOME_FILE}.{HOME_NAME}", found[0])

    def test_the_wire_refusal_and_its_table_row_stay(self):
        wire = text_of(WIRE_FILE).splitlines()
        self.assertEqual(WIRE_REFUSAL, wire[WIRE_LINE - 1].strip(),
                         f"the wire refusal of {WIRE_FILE}:{WIRE_LINE} moved")
        table = text_of(TABLE_FILE).splitlines()
        self.assertIn(TABLE_ROW, table[TABLE_LINE - 1],
                      f"the table row of {TABLE_FILE}:{TABLE_LINE} moved")
        self.assertNotIn(WIRE_REFUSAL, text_of(HOME_FILE),
                         "the home answers a store refusal, not the wire refusal")


if __name__ == "__main__":
    unittest.main()
