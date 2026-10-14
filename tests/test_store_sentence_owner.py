"""One home of the refusal sentence `unknown record set: <kind>`, and no second copy.

The sentence has one home: `unknown_record_set` in `src/store_rules.py`.  Two classes
build the message from that home: `JsonStore.place` in `src/store.py` and
`PostgresStore.place` in `src/store_pg.py`.  Before round 107 each `place` method held
its own copy of the sentence, so one wording change had to land in two files.

Each reader binds the home by name and calls it.  The class walk of
`tests/test_store_merge_rules.py` reads the module-qualified calls of `src.store_rules`
inside the two classes and pins them to the five edit rules of the owner, so the refusal
sentence reaches the class as a bound name and never as a second rule of the module.

The cases below read the home, count the sites of the sentence under `src/`, read the
binding and the call site of each reader, prove the live JsonStore raises the home's
sentence, plant the old copy in the text of one module, and read the report of that
copy.  The report names the path and the line of the copy.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.store import JsonStore  # noqa: E402
from src.store_rules import unknown_record_set  # noqa: E402

#: The home of the sentence, as a path under the repository root.
HOME_FILE = "src/store_rules.py"
#: The name of the home.
HOME_NAME = "unknown_record_set"
#: The module that holds the home, and the alias a reader binds for its edit rules.
HOME_MODULE = "src.store_rules"
HOME_ALIAS = "store_rules"
#: The two classes that build the message.  Each binds the home and calls it once.
READERS = ("src/store.py", "src/store_pg.py")
#: The fixed part of the sentence.  A copy spells this text.
SENTENCE = "unknown record set: "
#: The record set of the probe below.  No store keeps it.
PROBE = "verdicts"
#: The number of sites under src/ that hold the fixed part of the sentence.
SENTENCE_SITE_COUNT = 1
#: The number of binding sites, and of call sites, of the home in one reader.
BINDING_SITE_COUNT = 1
CALL_SITE_COUNT = 1

BINDING = re.compile(r"^\s*from\s+%s\s+import\b.*\b%s\b"
                     % (re.escape(HOME_MODULE), HOME_NAME))
CALL = re.compile(r"(?<![\w.])%s\s*\(" % HOME_NAME)
QUALIFIED = re.compile(r"\b%s\.%s\b" % (HOME_ALIAS, HOME_NAME))


def text_of(relative: str) -> str:
    """The text of one file, as a path under the repository root."""
    return (ROOT / relative).read_text(encoding="utf-8")


def report(relative: str, number: int, line: str, why: str) -> str:
    """The message of one site: the path, the line, the text, and the reason."""
    return f"{relative}:{number}: {line.strip()}\n  {why}"


def sites_of(relative: str, pattern: re.Pattern, why: str) -> list[str]:
    """The sites of one file whose line matches the pattern."""
    return [report(relative, number, line, why) for number, line in
            enumerate(text_of(relative).splitlines(), 1) if pattern.search(line)]


def sentence_sites(relative: str, text: str | None = None) -> list[str]:
    """The sites of one file that spell the fixed part of the sentence."""
    body = text if text is not None else text_of(relative)
    why = (f'the sentence spells "{SENTENCE}" in place of {HOME_FILE}.{HOME_NAME};'
           " read the owner's name")
    return [report(relative, number, line, why) for number, line in
            enumerate(body.splitlines(), 1) if SENTENCE in line]


def binding_sites(relative: str) -> list[str]:
    """The sites of one reader that bind the home by name from its module."""
    return sites_of(relative, BINDING, f"this line binds {HOME_NAME} from {HOME_MODULE}")


def call_sites(relative: str) -> list[str]:
    """The sites of one reader that call the home by name."""
    return sites_of(relative, CALL, f"this line builds the message from {HOME_NAME}")


class StoreSentenceOwner(unittest.TestCase):
    """One home of the sentence, and no second copy."""

    def test_the_home_answers_the_sentence(self):
        self.assertTrue(callable(unknown_record_set), "the home must be a function")
        self.assertEqual(SENTENCE + PROBE, unknown_record_set(PROBE),
                         "the home must answer the sentence of one record set")
        self.assertIn(HOME_NAME, text_of(HOME_FILE),
                      "the home must stand in its own module")

    def test_the_sentence_stands_once_under_src(self):
        found = {}
        for path in sorted((ROOT / "src").glob("*.py")):
            sites = sentence_sites(path.relative_to(ROOT).as_posix())
            if sites:
                found[path.relative_to(ROOT).as_posix()] = sites
        total = sum(len(sites) for sites in found.values())
        self.assertEqual(SENTENCE_SITE_COUNT, total,
                         "the sentence must stand one time under src/, and it stands in"
                         f" {sorted(found)}: {found}")
        self.assertEqual([HOME_FILE], sorted(found),
                         "the owner of the sentence must be the only file that spells it")

    def test_every_reader_builds_the_message_from_the_home(self):
        for relative in READERS:
            with self.subTest(reader=relative):
                self.assertEqual([], sentence_sites(relative),
                                 "a reader must not spell the sentence again")
                bound = binding_sites(relative)
                self.assertEqual(BINDING_SITE_COUNT, len(bound),
                                 "a reader must bind the home once:\n" + "\n".join(bound))
                called = call_sites(relative)
                self.assertEqual(CALL_SITE_COUNT, len(called),
                                 "a reader must call the home once:\n" + "\n".join(called))
                qualified = sites_of(relative, QUALIFIED,
                                     f"{HOME_ALIAS}.{HOME_NAME} is a qualified read")
                self.assertEqual([], qualified,
                                 "a reader must call the home by name: the class walk of"
                                 " tests/test_store_merge_rules.py pins the qualified"
                                 " calls of the five edit rules")

    def test_the_json_store_raises_the_home_sentence(self):
        with tempfile.TemporaryDirectory() as folder:
            store = JsonStore(folder)
            with self.assertRaises(ValueError) as caught:
                store.place(PROBE)
        self.assertEqual(unknown_record_set(PROBE), str(caught.exception),
                         "the live store must raise the sentence of the home")

    def test_a_planted_copy_is_reported_with_its_file_and_line(self):
        original = text_of(READERS[0])
        live = f"{HOME_NAME}(kind)"
        self.assertTrue(live in original, f"the live reader must call {live}")
        planted_text = original.replace(live, f'f"{SENTENCE}{{kind}}"')
        self.assertTrue(planted_text != original, "the plant must change the text")
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_store.py"
            planted.write_text(planted_text, encoding="utf-8")
            number = next(number for number, line in
                          enumerate(planted_text.splitlines(), 1) if SENTENCE in line)
            found = sentence_sites(str(planted), planted_text)
        self.assertEqual(1, len(found), found)
        self.assertIn(f'{planted}:{number}: raise ValueError(f"{SENTENCE}{{kind}}")', found[0])
        self.assertIn(f"{HOME_FILE}.{HOME_NAME}", found[0])


if __name__ == "__main__":
    unittest.main()
