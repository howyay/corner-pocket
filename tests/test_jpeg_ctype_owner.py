"""One home of the content type of a JPEG reply, and no second spelling.

The content type of a JPEG reply is one fact, and it has one home: ``JPEG_CTYPE`` in
``src/reply_body.py``, the module that already owns ``JSON_CTYPE`` and states the whole
reply-content-type fact in its docstring.  Six call sites sent a JPEG reply before round
119 and every one of them spelled ``"image/jpeg"`` on its own line: the ``/crops/`` route
of ``annotator/server.py:114``, the frame route of ``src/pid_anchor_ui.py:160``, and four
replies of ``annotator/unified_server.py`` at ``:3008``, ``:3021``, ``:3042`` and
``:3044``.  One change of the content type had to land in three files.

The home stands at the end of ``src/reply_body.py``, below the reply writer.  No ``def``
default reads it, so the position that would raise ``NameError`` for the JSON home
(``src/reply_body.py:33``, above the writer at ``src/reply_body.py:34``) is allowed here,
and the append moved no pinned number.  The three readers joined an existing import line,
so no module gained a line either, and the file counts of the round hold.

Three facts that spell a longer or an equal string stay where they stand.  The two
data-URL sites -- ``src/enroll_from_tracklet.py:812`` and ``src/pid_seed_ui.py:87`` --
hold a constant that *contains* the type, so the whole-constant read below never sees
them, and the case ``test_the_data_urls_are_not_whole_constants`` holds both lines.
``annotator/twitch_vod_source.py:219`` states the picture type of an upstream response,
read by ``tests/test_vod_import.py:637``; it is a listed exception of this guard, and the
case ``test_the_listed_exception_stays_silent`` holds it.

The walk below reads every python file of ``src/`` and ``annotator/``, skips ``src/sam3/``,
drops the string node of a module, class or function docstring, and answers every code
constant equal to ``"image/jpeg"`` that is neither the home nor the listed exception.  A
floor keeps a walk that read nothing from passing in silence.

Run: ``./scripts/pool-test.sh python test_jpeg_ctype_owner``
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from _shipped import code_strings  # noqa: E402
from src.reply_body import JPEG_CTYPE  # noqa: E402

#: The home of the content type, as a path under the repository root, and its name.
HOME_FILE = "src/reply_body.py"
HOME_NAME = "JPEG_CTYPE"
HOME_MODULE = "src.reply_body"
HOME_VALUE = "image/jpeg"
#: The line of the home, pinned by number and by text.
HOME_LINE = 49
HOME_FORM = 'JPEG_CTYPE = "image/jpeg"'
#: The JSON home and the reply writer of the same module.  The JPEG home was appended
#: below both, so both keep the number they had.
JSON_LINE = 33
JSON_FORM = 'JSON_CTYPE = "application/json"'
WRITER_LINE = 34
WRITER_FORM = "def write_reply(handler, code, body, ctype=JSON_CTYPE) -> None:"
#: Every call site that sends a JPEG reply through the home, as `path:line`, with the
#: text of that line.
SITES = {
    "annotator/server.py": {114: "return self._send(200, p.read_bytes(), JPEG_CTYPE)"},
    "src/pid_anchor_ui.py": {160: "return self._send(200, jpg, JPEG_CTYPE)"},
    "annotator/unified_server.py": {
        3008: "return self.send(200, raw, JPEG_CTYPE, {",
        3021: "return self.send(200, raw, JPEG_CTYPE, {",
        3042: "return self.send(200, backend.event_frame(parts[1], parts[3]), JPEG_CTYPE)",
        3044: "return self.send(200, backend.frame_jpeg(query.text(\"t\"), parts[1]),"
              " JPEG_CTYPE)",
    },
}
#: Every import line that binds the home, as `path:line`, with the text of that line.  The
#: home joined an existing import line in each module, so every number stays alive.
BINDINGS = {
    "annotator/server.py": {27: "from src.reply_body import JPEG_CTYPE, JSON_CTYPE,"
                                " write_reply  # noqa: E402"},
    "src/pid_anchor_ui.py": {35: "from src.reply_body import JPEG_CTYPE, JSON_CTYPE,"
                                 " write_reply  # noqa"},
    "annotator/unified_server.py": {218: "from src.reply_body import JPEG_CTYPE,"
                                         " JSON_CTYPE  # noqa: E402"},
}
#: The modules that read the home: the owner module itself, and the three readers.
READERS = ("src/reply_body.py", "annotator/server.py", "src/pid_anchor_ui.py",
           "annotator/unified_server.py")
#: The test that reads the fact on the wire, pinned by number and text.
READER_TEST = "tests/test_unified_server.py"
READER_TEST_LINE = 627
READER_TEST_FORM = "self.assertEqual(handler.response_headers['Content-Type'], 'image/jpeg')"
#: The one live site of the same string that is a DIFFERENT fact: the picture type of an
#: upstream response, read by tests/test_vod_import.py:637.  It stays, and it is silent.
EXCEPTIONS = {
    "annotator/twitch_vod_source.py": {219: "return 'image/jpeg', bytes(body)"},
}
#: The two data-URL sites of the type.  The constant holds more than the type, so a read of
#: whole code constants never flags them -- a substring match would flag both.
DATA_URLS = {
    "src/enroll_from_tracklet.py": {
        812: 'return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")',
    },
    "src/pid_seed_ui.py": {87: "img.src = 'data:image/jpeg;base64,'+j.jpg;"},
}
#: The trees the walk reads, the subtree it skips, and the floor that keeps a walk that
#: read nothing from passing in silence.  With `src/sam3` left out the tree holds 113
#: python modules, so the floor stands below that count and far above a walk that broke.
WALKED = ("src/**/*.py", "annotator/*.py")
SKIP = ("src/sam3",)
FILE_FLOOR = 100
#: The planted modules of the honesty cases.
PLANTED = "src/planted_jpeg.py"
PLANTED_LINE = 6
PLANTED_TEXT = ('"""A planted module that spells the JPEG content type."""\n'
                "\n"
                "\n"
                "def row():\n"
                '    """The docstring names image/jpeg, which is no code constant."""\n'
                '    return "%s"\n' % HOME_VALUE)
QUIET = "src/quiet_jpeg.py"
QUIET_TEXT = ('"""A planted module that names the type in prose and in a data URL."""\n'
              "\n"
              "\n"
              "def row():\n"
              '    """The docstring names image/jpeg, which is no code constant."""\n'
              '    return "data:image/jpeg;base64," + payload\n')


def text_of(relative: str) -> str:
    """The text of one file of this repository."""
    return (ROOT / relative).read_text(encoding="utf-8")


def source_lines(relative: str) -> list:
    """The lines of one file of this repository."""
    return text_of(relative).splitlines()


def walked_files() -> list:
    """Every walked python file, the generated subtree left out."""
    found = []
    for path in sorted(one for pattern in WALKED for one in ROOT.glob(pattern)):
        relative = path.relative_to(ROOT).as_posix()
        if "__pycache__" in path.parts or relative.startswith(SKIP):
            continue
        found.append(path)
    return found


def live_sites() -> dict:
    """Every walked code constant equal to the content type, by path and by line."""
    found = {}
    for path in walked_files():
        relative = path.relative_to(ROOT).as_posix()
        lines = source_lines(relative)
        sites = {line: lines[line - 1].strip()
                 for line, value in code_strings(ast.parse(text_of(relative)))
                 if value == HOME_VALUE}
        if sites:
            found[relative] = sites
    return found


def analyze() -> list:
    """Every walked code constant of the type that is no home and no listed exception."""
    offenders = []
    for relative, sites in sorted(live_sites().items()):
        for line in sorted(sites):
            if relative == HOME_FILE and line == HOME_LINE:
                continue
            if line in EXCEPTIONS.get(relative, ()):
                continue
            offenders.append("%s:%d: 'image/jpeg' spells the content type; read %s.%s"
                             % (relative, line, HOME_MODULE, HOME_NAME))
    return offenders


def planted_copy(relative: str, text: str) -> list:
    """Write one planted module, run the walk, and remove the module."""
    path = ROOT / relative
    path.write_text(text, encoding="utf-8")
    try:
        return analyze()
    finally:
        path.unlink()


class HomeTests(unittest.TestCase):
    """The home answers the content type, and its line is pinned."""

    def test_the_home_answers_the_content_type(self):
        self.assertEqual(HOME_VALUE, JPEG_CTYPE,
                         f"{HOME_FILE}.{HOME_NAME} must answer the content type of a"
                         " JPEG reply")
        self.assertIn(HOME_NAME, text_of(HOME_FILE),
                      "the home must stand in its own module")
        self.assertIn(HOME_NAME, __import__(HOME_MODULE, fromlist=["*"]).__all__,
                      f"{HOME_MODULE} must export the home to its readers")

    def test_the_home_line_is_pinned_by_number_and_text(self):
        line = source_lines(HOME_FILE)[HOME_LINE - 1]
        self.assertEqual(HOME_FORM, line.strip(),
                         f"{HOME_FILE}:{HOME_LINE} no longer holds the home; it reads"
                         f" {line.strip()!r}")

    def test_the_append_moved_no_pinned_number(self):
        """No default reads this home, so it stands below the writer and moves nothing."""
        lines = source_lines(HOME_FILE)
        self.assertEqual(JSON_FORM, lines[JSON_LINE - 1].strip(),
                         f"{HOME_FILE}:{JSON_LINE} must keep the JSON home")
        self.assertEqual(WRITER_FORM, lines[WRITER_LINE - 1].strip(),
                         f"{HOME_FILE}:{WRITER_LINE} must keep the reply writer")
        self.assertGreater(HOME_LINE, WRITER_LINE,
                           f"{HOME_FILE}:{HOME_LINE} stands below the writer, which reads"
                           f" no default of {HOME_NAME}")


class SiteTests(unittest.TestCase):
    """Every call site and every import line keeps its number and its text."""

    def test_every_site_is_pinned_by_number_and_text(self):
        for relative, pinned in SITES.items():
            with self.subTest(reader=relative):
                lines = source_lines(relative)
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer reads the home")

    def test_every_import_line_keeps_its_number(self):
        for relative, pinned in BINDINGS.items():
            with self.subTest(reader=relative):
                lines = source_lines(relative)
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer binds the home")

    def test_every_reader_reads_the_home(self):
        for relative in READERS:
            with self.subTest(reader=relative):
                self.assertIn(HOME_NAME, text_of(relative),
                              f"{relative} no longer reads {HOME_FILE}.{HOME_NAME}")

    def test_the_reader_test_keeps_its_line(self):
        line = source_lines(READER_TEST)[READER_TEST_LINE - 1]
        self.assertEqual(READER_TEST_FORM, line.strip(),
                         f"{READER_TEST}:{READER_TEST_LINE} no longer reads the reply type"
                         " on the wire")


class WalkTests(unittest.TestCase):
    """The walk names every second home, and the other facts stay silent."""

    def test_no_second_spelling_stands_in_the_tree(self):
        offenders = analyze()
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_the_walk_reads_the_shipped_tree(self):
        """A walk that read no file would pass the case above for no reason."""
        read = [path.relative_to(ROOT).as_posix() for path in walked_files()]
        self.assertGreaterEqual(len(read), FILE_FLOOR, f"the walk read {len(read)} files")
        self.assertIn(HOME_FILE, read, "the walk must read the home")
        self.assertEqual([], [one for one in read if one.startswith("src/sam3")],
                         "the walk must skip src/sam3")

    def test_the_live_sites_are_the_home_and_the_listed_exception(self):
        expected = {HOME_FILE: {HOME_LINE: HOME_FORM}, **EXCEPTIONS}
        found = live_sites()
        self.assertEqual(expected, found,
                         "the string must stand in the home and in the listed exception"
                         " alone:\n" + "\n".join(f"  {relative}:{number}: {text}"
                                                 for relative, sites in sorted(found.items())
                                                 for number, text in sorted(sites.items())))

    def test_the_listed_exception_stays_silent(self):
        """The upstream picture type is no reply of this repository, so the walk skips it."""
        read = [path.relative_to(ROOT).as_posix() for path in walked_files()]
        for relative, pinned in EXCEPTIONS.items():
            with self.subTest(exception=relative):
                self.assertIn(relative, read, "a listed exception must be walked")
                self.assertEqual([], [one for one in analyze() if one.startswith(relative)],
                                 f"{relative} is a listed exception of the walk")

    def test_the_data_urls_are_not_whole_constants(self):
        """The constant of a data URL holds more than the type, so the read never fires."""
        found = live_sites()
        for relative, pinned in DATA_URLS.items():
            with self.subTest(data_url=relative):
                lines = source_lines(relative)
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer holds its data URL")
                self.assertNotIn(relative, found,
                                 f"{relative} must not be read as a whole constant")

    def test_the_walk_finds_a_planted_copy(self):
        offenders = planted_copy(PLANTED, PLANTED_TEXT)
        self.assertEqual(1, len(offenders), offenders)
        self.assertTrue(offenders[0].startswith("%s:%d" % (PLANTED, PLANTED_LINE)),
                        offenders[0])

    def test_the_walk_ignores_prose_and_a_data_url(self):
        self.assertEqual([], planted_copy(QUIET, QUIET_TEXT))


if __name__ == "__main__":
    unittest.main()
