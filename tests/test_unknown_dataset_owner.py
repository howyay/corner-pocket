"""One home of the refusal sentence `unknown dataset: <dataset>`, and no fourth writer.

The sentence has one home: `unknown_dataset` in `src/store_rules.py`, beside the
`unknown_record_set` of round 107.  Three stores build the message from that home:
`JsonStore._scan` in `src/store.py`, `dataset_dir` in `src/store_files.py`, and
`PostgresStore._dataset` in `src/store_pg.py`.  Before round 108 every one of the three
held its own f-string, so one wording change had to land in three files.

Each store binds the home by name and calls it.  The cases below read the home, count the
sites of the sentence under `src/`, read the binding and the call site of each store, prove
that each live store raises the home's sentence, and walk the tree for a fourth writer.
The walk names the path, the line, and the text of every site it finds.

Run: ``./scripts/pool-test.sh python test_unknown_dataset_owner``
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.store import JsonStore  # noqa: E402
from src.store_files import dataset_dir  # noqa: E402
from src.store_pg import PostgresStore  # noqa: E402
from src.store_rules import unknown_dataset  # noqa: E402

#: The home of the sentence, as a path under the repository root.
HOME_FILE = "src/store_rules.py"
#: The name of the home.
HOME_NAME = "unknown_dataset"
#: The module that holds the home.
HOME_MODULE = "src.store_rules"
#: The three stores that raise the sentence.  Each binds the home and calls it once.
STORES = ("src/store.py", "src/store_files.py", "src/store_pg.py")
#: The fixed part of the sentence.  A live writer spells this text.
SENTENCE = "unknown dataset: "
#: The dataset of the probes below.  No store keeps it.
PROBE = "no-such-dataset"
#: The number of sites under src/ that hold the fixed part of the sentence.
SENTENCE_SITE_COUNT = 1
#: The number of binding sites, and of call sites, of the home in one store.
BINDING_SITE_COUNT = 1
CALL_SITE_COUNT = 1
#: The database store connects on first use, not at construction.  `_dataset` reads the
#: registry under `root` alone, so the case below builds the store without a database.
UNUSED_URL = "postgresql:///unused"
#: The directories that hold no project source.  A guard under tests/ names the sentence
#: to hold it, so that directory is not walked.
TREE_SKIPPED = (".git", ".venv", "node_modules", "out", "tests", "__pycache__")

BINDING = re.compile(r"^\s*from\s+%s\s+import\b.*\b%s\b"
                     % (re.escape(HOME_MODULE), HOME_NAME))
CALL = re.compile(r"(?<![\w.])%s\s*\(" % HOME_NAME)


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


def answer_lines() -> list[str]:
    """The lines of the home that answer a refusal, as `path:number: text`.

    The case that counts the sites reads them: when the home no longer spells the sentence,
    the failure names the line of the home and the text that line answers today.
    """
    return [f"{HOME_FILE}:{number}: {line.strip()}" for number, line in
            enumerate(text_of(HOME_FILE).splitlines(), 1)
            if line.strip().startswith('return f"')]


@lru_cache(maxsize=None)
def repository_sources() -> tuple:
    """Every `*.py` file of the project outside tests/, sorted: ((path, text), ...).

    The virtual environment, the git object store, the generated `out/` tree, and the
    guards under `tests/` are not project source, so the walk reads none of them.
    """
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT)
        if relative.parts[0] in TREE_SKIPPED:
            continue
        found.append((relative.as_posix(), path.read_text(encoding="utf-8", errors="replace")))
    return tuple(found)


def writer_sites() -> list[str]:
    """The reported live writers of the sentence: every site of the tree but the home."""
    return [line for relative, text in repository_sources() if relative != HOME_FILE
            for line in sentence_sites(relative, text)]


class UnknownDatasetOwner(unittest.TestCase):
    """One home of the sentence, three readers, and no fourth writer."""

    def test_the_home_answers_the_sentence(self):
        self.assertTrue(callable(unknown_dataset), "the home must be a function")
        self.assertEqual(SENTENCE + PROBE, unknown_dataset(PROBE),
                         "the home must answer the sentence of one dataset")
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
                         f" {sorted(found)}: {found}\n  the home answers of today:\n"
                         + "\n".join("  " + line for line in answer_lines()))
        self.assertEqual([HOME_FILE], sorted(found),
                         "the owner of the sentence must be the only file that spells it")

    def test_every_store_builds_the_message_from_the_home(self):
        for relative in STORES:
            with self.subTest(store=relative):
                self.assertEqual([], sentence_sites(relative),
                                 "a store must not spell the sentence again")
                bound = sites_of(relative, BINDING,
                                 f"this line binds {HOME_NAME} from {HOME_MODULE}")
                self.assertEqual(BINDING_SITE_COUNT, len(bound),
                                 "a store must bind the home once:\n" + "\n".join(bound))
                called = sites_of(relative, CALL,
                                  f"this line builds the message from {HOME_NAME}")
                self.assertEqual(CALL_SITE_COUNT, len(called),
                                 "a store must call the home once:\n" + "\n".join(called))

    def test_the_json_store_raises_the_home_sentence(self):
        with tempfile.TemporaryDirectory() as folder:
            store = JsonStore(folder)
            with self.assertRaises(ValueError) as caught:
                store.correction_get(PROBE, 1)
        self.assertEqual(unknown_dataset(PROBE), str(caught.exception),
                         "the file store must raise the sentence of the home")

    def test_the_files_helper_raises_the_home_sentence(self):
        with self.assertRaises(ValueError) as caught:
            dataset_dir(PROBE)
        self.assertEqual(unknown_dataset(PROBE), str(caught.exception),
                         "src/store_files.dataset_dir must raise the sentence of the home")

    def test_the_postgres_store_raises_the_home_sentence(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PostgresStore(folder, url=UNUSED_URL)
            with self.assertRaises(ValueError) as caught:
                store._dataset(PROBE)
        self.assertEqual(unknown_dataset(PROBE), str(caught.exception),
                         "the database store must raise the sentence of the home")

    def test_no_fourth_writer_of_the_sentence_stands_in_the_tree(self):
        found = writer_sites()
        self.assertEqual([], found,
                         "the sentence must stand in %s alone; the other writer sites"
                         " are\n%s" % (HOME_FILE, "\n".join(found)))

    def test_the_walk_reads_the_tree(self):
        """A walk that read no file would pass the case above for no reason."""
        read = [relative for relative, _text in repository_sources()]
        self.assertGreater(len(read), 20, f"the walk read {len(read)} files")
        self.assertIn(HOME_FILE, read, "the walk must read the home")

    def test_a_planted_copy_is_reported_with_its_file_and_line(self):
        original = text_of(STORES[1])
        live = f"{HOME_NAME}(dataset)"
        self.assertIn(live, original, f"the live store must call {live}")
        planted_text = original.replace(live, f'f"{SENTENCE}{{dataset}}"')
        self.assertNotEqual(original, planted_text, "the plant must change the text")
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_store_files.py"
            planted.write_text(planted_text, encoding="utf-8")
            number = next(number for number, line in
                          enumerate(planted_text.splitlines(), 1) if SENTENCE in line)
            found = sentence_sites(str(planted), planted_text)
        self.assertEqual(1, len(found), found)
        self.assertIn(f'{planted}:{number}: raise ValueError(f"{SENTENCE}{{dataset}}")', found[0])
        self.assertIn(f"{HOME_FILE}.{HOME_NAME}", found[0])


if __name__ == "__main__":
    unittest.main()
