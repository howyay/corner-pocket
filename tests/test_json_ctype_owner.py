"""One home of the default content type of a JSON reply, and no second spelling.

The content type of a JSON reply is one fact, and it has one home: `JSON_CTYPE` in
`src/reply_body.py`, on the line above the reply writer that reads it.  Five writers send
a reply with that type: `write_reply` in `src/reply_body.py`, `Handler._send` in
`annotator/server.py`, in `src/pid_anchor_ui.py` and in `src/pid_seed_ui.py`, and the
nested `send` of `annotator/unified_server.py`.  Before round 117 every one of the five
spelled `"application/json"` in its own signature, so one change of the content type had
to land in five files.

The home stands *above* the writer at `src/reply_body.py:34`, not at the end of the file.
The default of a `def` is evaluated when the `def` statement runs, so a home placed after
the writer would raise `NameError` at the import of `src/reply_body` -- the module that
`annotator/server.py`, `src/pid_anchor_ui.py` and `src/pid_seed_ui.py` all import.  The
module keeps its 46 lines and the writer keeps its line, which is the purpose the round
stated.

Each writer binds the home by name and reads it in the default of its signature.  The
cases below read the home, pin its line by number and text, prove that the home stands
above the writer that reads it, prove that the default of every reachable writer *is* the
home object, pin the five writer sites and the four import lines as `path:line` with their
text, and walk `src/**/*.py` and `annotator/*.py` for a second spelling: an argument
default that holds the string.  The walk names the path, the line, and the text of every
site it finds.

Three facts that spell the same string are *different* facts, and each one stays where it
stands.  A client request header -- `src/eval_faces.py:1036`,
`annotator/twitch_source.py:208`, `annotator/twitch_vod_source.py:154` -- states the type
of the body a client sends.  An explicit positional argument --
`annotator/unified_server.py:2849`, `:2857` and `:2958` -- states the type of one reply at
its call.  And the page half -- the JavaScript inside the two pid modules, plus
`annotator/index.html`, `annotator/label.html`, `annotator/app.js` and
`annotator/clock-sync.js` -- sends a request of its own and cannot read a python name.

Run: ``./scripts/pool-test.sh python test_json_ctype_owner``
"""
from __future__ import annotations

import ast
import importlib
import io
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

from _shipped import code_strings, shipped_modules  # noqa: E402
from src.reply_body import JSON_CTYPE, write_reply  # noqa: E402

#: The home of the content type, as a path under the repository root.
HOME_FILE = "src/reply_body.py"
#: The name of the home.
HOME_NAME = "JSON_CTYPE"
#: The module that holds the home.
HOME_MODULE = "src.reply_body"
#: The value the home answers.
HOME_VALUE = "application/json"
#: The line of the home, pinned by number and by text.
HOME_LINE = 33
HOME_FORM = 'JSON_CTYPE = "application/json"'
#: The writer of the home module itself, and the line that reads the home.
OWNER_WRITER = "write_reply"
OWNER_LINE = 34
#: The five writers that send a reply with the home's type.  The home joined an existing
#: import line in three modules, and traded one blank line for a new import line in the
#: fourth, so no line of any module moved and every pinned number stays alive.
WRITERS = ("src/reply_body.py", "annotator/server.py", "src/pid_anchor_ui.py",
           "src/pid_seed_ui.py", "annotator/unified_server.py")
#: The four modules that bind the home by name, and the three of them whose `_send` is
#: reachable at run time.  The nested `send` of `annotator/unified_server.py` stands inside
#: a class of a long module that binds a port at import, so its default is held by the
#: pinned text of its line alone.
BINDING_FILES = ("annotator/server.py", "src/pid_anchor_ui.py", "src/pid_seed_ui.py",
                 "annotator/unified_server.py")
READERS = ("annotator/server.py", "src/pid_anchor_ui.py", "src/pid_seed_ui.py")
READER_MODULES = {"annotator/server.py": "annotator.server",
                  "src/pid_anchor_ui.py": "src.pid_anchor_ui",
                  "src/pid_seed_ui.py": "src.pid_seed_ui"}
#: The class and the method each reader sends a reply through.
HANDLER_CLASS = "Handler"
SEND_METHOD = "_send"
#: Every live site of the writer set, as `path:line`, with the text of that line.
SITES = {
    "src/reply_body.py": {34: "def write_reply(handler, code, body, ctype=JSON_CTYPE) -> None:"},
    "annotator/server.py": {63: "def _send(self, code, body, ctype=JSON_CTYPE):"},
    "src/pid_anchor_ui.py": {145: "def _send(self, code, body, ctype=JSON_CTYPE):"},
    "src/pid_seed_ui.py": {158: "def _send(self, code, body, ctype=JSON_CTYPE):"},
    "annotator/unified_server.py": {
        2885: "def send(self, status, body, content_type=JSON_CTYPE, headers=None):"},
}
#: Every import line that binds the home, as `path:line`, with the text of that line.
BINDINGS = {
    "annotator/server.py": {27: "from src.reply_body import JSON_CTYPE, write_reply  "
                                "# noqa: E402"},
    "src/pid_anchor_ui.py": {35: "from src.reply_body import JSON_CTYPE, write_reply  # noqa"},
    "src/pid_seed_ui.py": {35: "from src.reply_body import JSON_CTYPE, write_reply  "
                               "# noqa: E402"},
    "annotator/unified_server.py": {218: "from src.reply_body import JSON_CTYPE  # noqa: E402"},
}
#: The line count of every module this round touched.  The home stands inside its module
#: and the four call sites read it without adding a line, so every count holds.
LINE_COUNTS = {
    HOME_FILE: 46,
    "annotator/server.py": 172,
    "src/pid_anchor_ui.py": 191,
    "src/pid_seed_ui.py": 230,
    "annotator/unified_server.py": 3126,
}
#: The number of binding sites of the home in one reader, and of the argument the four
#: writers of a `_send` hold their type in.
BINDING_SITE_COUNT = 1
CTYPE_ARGUMENT = "ctype"
#: The reply the recorder case sends, and the handler that answers for a writer.
REPLY_BODY = b'{"ok":true}'
REPLY_CODE = 200
#: The python sites of the same string that are DIFFERENT facts.  A client header states
#: the type of the body a client sends, and an explicit positional argument states the type
#: of one reply at its call.  Every one of them stays where it stands.
HELD_FACTS = {
    "src/eval_faces.py": {1036: 'headers={"Content-Type": "application/json"}, '
                                'method="POST")'},
    "annotator/twitch_source.py": {208: "headers.update({'Client-ID': _CLIENT_ID, "
                                         "'Content-Type': 'application/json'})"},
    "annotator/twitch_vod_source.py": {154: "headers.update({'Client-ID': live._CLIENT_ID, "
                                               "'Content-Type': 'application/json'})"},
    "annotator/unified_server.py": {
        2849: "return self.send(503, b'{\"error\":\"unavailable\"}', \"application/json\",",
        2857: "self.send(200, body, \"application/json\", ((\"ETag\", etag), "
              "(\"Cache-Control\", \"no-cache\")))",
        2958: "return self.send(503, b'{\"error\":\"unavailable\"}', \"application/json\",",
    },
}
#: The client request headers of the held facts: a request of a client, never a reply.
HEADER_FILES = ("src/eval_faces.py", "annotator/twitch_source.py",
                "annotator/twitch_vod_source.py")
#: The page half of the same string: the JavaScript inside the two pid modules and the four
#: page files.  A page cannot read a python name, so every one of these lines stays.
PAGE_FACTS = {
    "src/pid_anchor_ui.py": {101: "const r = await fetch('/api/anchors',{method:'POST',"
                                  "headers:{'Content-Type':'application/json'},"},
    "src/pid_seed_ui.py": {114: "const r = await fetch('/seed',{method:'POST',"
                                "headers:{'Content-Type':'application/json'},"},
    "annotator/index.html": {132: "await fetch('/api/annotate', { method: 'POST', "
                                  "headers: {'Content-Type':'application/json'},",
                             138: "await fetch('/api/annotate', { method: 'POST', "
                                  "headers: {'Content-Type':'application/json'},",
                             143: "await fetch('/api/annotate', { method: 'POST', "
                                  "headers: {'Content-Type':'application/json'},"},
    "annotator/label.html": {106: "await fetch('/api/ball_label', { method: 'POST', "
                                  "headers: {'Content-Type':'application/json'},"},
    "annotator/app.js": {21: "const JSON_HEADERS = Object.freeze({'Content-Type': "
                             "'application/json'});"},
    "annotator/clock-sync.js": {75: "const NO_PAGE_HEADERS = {'Content-Type': "
                                    "'application/json'};"},
}
#: The trees the walk reads, the subtree it skips, and the floor that keeps a walk that
#: read nothing from passing in silence.  With `src/sam3` left out the tree holds 113
#: python modules, so the floor stands below that count and far above a walk that broke.
WALKED = ("src/**/*.py", "annotator/*.py")
SKIP = ("src/sam3",)
FILE_FLOOR = 100

#: The shape of a binding: the import of the home by name, from its own module.
BINDING = re.compile(r"^\s*from\s+%s\s+import\b.*\b%s\b"
                     % (re.escape(HOME_MODULE), HOME_NAME))


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


def default_sites(relative: str, text: str | None = None) -> list:
    """The sites of one module that spell the content type in an argument default.

    A default is evaluated where its `def` statement runs, so a module that spells the
    string in a default is a second home of the fact: one change of the content type would
    land in two files.  The answer names the path, the line, and the text of the site.
    """
    body = text if text is not None else text_of(relative)
    why = (f'the content type spells "{HOME_VALUE}" in place of {HOME_FILE}.{HOME_NAME};'
           " read the owner's name")
    lines = body.splitlines()
    found = []
    for node in ast.walk(ast.parse(body)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        defaults = list(node.args.defaults) + [one for one in node.args.kw_defaults if one]
        for default in defaults:
            if isinstance(default, ast.Constant) and default.value == HOME_VALUE:
                found.append(report(relative, default.lineno, lines[default.lineno - 1], why))
    return sorted(found)


def in_skipped(relative: str) -> bool:
    """Whether one path lies in a subtree the walk leaves out."""
    return any(relative == skip or relative.startswith(skip + "/") for skip in SKIP)


def walked_files() -> list:
    """Every walked python module of the shipped tree, `src/sam3` left out.

    The trees are the two the round names: `src/**/*.py` at any depth, and the top level of
    `annotator/`.  `tests/_shipped.shipped_modules` walks the shipped trees once, so this
    guard and its siblings read the same modules.
    """
    read = []
    for path in shipped_modules():
        relative = path.relative_to(ROOT).as_posix()
        parts = Path(relative).parts
        if in_skipped(relative):
            continue
        if parts[0] == "src" or (parts[0] == "annotator" and len(parts) == 2):
            read.append(path)
    return sorted(read)


def spelled_sites() -> list:
    """Every walked argument default that spells the content type: the second home."""
    return [site for path in walked_files()
            for site in default_sites(path.relative_to(ROOT).as_posix())]


def literal_sites(relative: str) -> dict:
    """The line and the text of every string literal of one module that is the type.

    `code_strings` drops the docstring of a module, of a class, and of a function, so the
    prose of `src/reply_body.py` that names the content type is not a site.
    """
    lines = text_of(relative).splitlines()
    return {number: lines[number - 1].strip()
            for number, value in code_strings(ast.parse(text_of(relative)))
            if value == HOME_VALUE}


def live_literal_sites() -> dict:
    """Every site of the string in the walked tree: the home and the held facts."""
    found = {}
    for path in walked_files():
        relative = path.relative_to(ROOT).as_posix()
        sites = literal_sites(relative)
        if sites:
            found[relative] = sites
    return found


class Recorder:
    """A handler that records the reply one writer sends, and writes no socket."""

    def __init__(self):
        self.headers = []
        self.wfile = io.BytesIO()

    def send_response(self, code):
        """Record the status line of the reply."""
        self.code = code

    def send_header(self, key, value):
        """Record one header of the reply."""
        self.headers.append((key, value))

    def end_headers(self):
        """Record the end of the header block."""

    def content_type(self):
        """The content type the reply carried, or None."""
        found = [value for key, value in self.headers if key == "Content-Type"]
        return found[0] if len(found) == 1 else None


class HomeTests(unittest.TestCase):
    """The home answers the content type, and its line is pinned."""

    def test_the_home_answers_the_content_type(self):
        self.assertEqual(HOME_VALUE, JSON_CTYPE,
                         f"{HOME_FILE}.{HOME_NAME} must answer the content type of a"
                         " JSON reply")
        self.assertIn(HOME_NAME, text_of(HOME_FILE),
                      "the home must stand in its own module")
        self.assertIn(HOME_NAME, __import__(HOME_MODULE, fromlist=["*"]).__all__,
                      f"{HOME_MODULE} must export the home to its readers")

    def test_the_home_line_is_pinned_by_number_and_text(self):
        line = text_of(HOME_FILE).splitlines()[HOME_LINE - 1]
        self.assertEqual(HOME_FORM, line.strip(),
                         f"{HOME_FILE}:{HOME_LINE} no longer holds the home; it reads"
                         f" {line.strip()!r}")

    def test_the_home_stands_above_the_writer_that_reads_it(self):
        """A default is read where its `def` runs, so the home cannot stand below it."""
        self.assertLess(HOME_LINE, OWNER_LINE,
                        f"{HOME_FILE}:{HOME_LINE} must stand above the writer that reads"
                        f" it, {HOME_FILE}:{OWNER_LINE}")
        later = [number for number, line in enumerate(text_of(HOME_FILE).splitlines(), 1)
                 if line.startswith(HOME_NAME) and number != HOME_LINE]
        self.assertEqual([], later,
                         f"{HOME_NAME} must have one assignment, at"
                         f" {HOME_FILE}:{HOME_LINE}")

    def test_every_module_of_the_writers_keeps_its_line_count(self):
        for relative, count in LINE_COUNTS.items():
            with self.subTest(module=relative):
                self.assertEqual(count, len(text_of(relative).splitlines()),
                                 f"{relative} must keep its {count} lines: the home joined"
                                 " an existing import line in three modules, and the import"
                                 " line of annotator/unified_server.py traded one blank line")


class WriterTests(unittest.TestCase):
    """Five writers read the home, and each one reads it in a default."""

    def test_every_writer_reads_the_home_in_the_default_of_its_signature(self):
        for relative in BINDING_FILES:
            with self.subTest(writer=relative):
                spelled = default_sites(relative)
                self.assertEqual([], spelled,
                                 "a writer must not spell the content type again:\n"
                                 + "\n".join(spelled))
                bound = sites_of(relative, BINDING,
                                 f"this line binds {HOME_NAME} from {HOME_MODULE}")
                self.assertEqual(BINDING_SITE_COUNT, len(bound),
                                 "a writer must bind the home once:\n" + "\n".join(bound))

    def test_every_writer_site_is_pinned_by_number_and_text(self):
        self.assertEqual(sorted(WRITERS), sorted(SITES),
                         "the pinned sites must cover every writer of the reply")
        for relative, pinned in SITES.items():
            with self.subTest(writer=relative):
                lines = text_of(relative).splitlines()
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer reads the home")

    def test_every_import_line_keeps_its_number(self):
        self.assertEqual(sorted(BINDING_FILES), sorted(BINDINGS),
                         "the pinned imports must cover every reader of the home")
        for relative, pinned in BINDINGS.items():
            with self.subTest(reader=relative):
                lines = text_of(relative).splitlines()
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer binds the home")

    def test_every_reachable_writer_default_is_the_home_object(self):
        self.assertIs(JSON_CTYPE, write_reply.__defaults__[-1],
                      f"the default of {HOME_FILE}.{OWNER_WRITER} must be the home itself")
        patched, sys.argv = sys.argv, [str(ROOT / "annotator" / "server.py")]
        try:
            modules = {relative: importlib.import_module(READER_MODULES[relative])
                       for relative in READERS}
        finally:
            sys.argv = patched
        for relative, module in modules.items():
            with self.subTest(reader=relative):
                handler = getattr(module, HANDLER_CLASS)
                send = getattr(handler, SEND_METHOD)
                self.assertIs(JSON_CTYPE, send.__defaults__[-1],
                              f"the default of {relative}:{SEND_METHOD} must be the"
                              f" {HOME_NAME} of {HOME_MODULE}")

    def test_a_default_reply_carries_the_home_value(self):
        handler = Recorder()
        write_reply(handler, REPLY_CODE, REPLY_BODY)
        self.assertEqual(REPLY_CODE, handler.code, "the reply must carry the status given")
        self.assertEqual(HOME_VALUE, handler.content_type(),
                         f"a default reply of {HOME_FILE} must carry the home's type")
        self.assertEqual(REPLY_BODY, handler.wfile.getvalue(),
                         "the reply must carry the body given")


class WalkTests(unittest.TestCase):
    """The walk names every second spelling, and the other facts stay."""

    def test_no_second_spelling_of_the_content_type_stands_in_the_tree(self):
        found = spelled_sites()
        self.assertEqual([], found,
                         "an argument default must read %s.%s; the sites that spell"
                         ' "%s" are\n%s' % (HOME_FILE, HOME_NAME, HOME_VALUE,
                                            "\n".join(found)))

    def test_the_walk_reads_the_shipped_tree(self):
        """A walk that read no file would pass the case above for no reason."""
        read = [path.relative_to(ROOT).as_posix() for path in walked_files()]
        self.assertGreaterEqual(len(read), FILE_FLOOR, f"the walk read {len(read)} files")
        self.assertIn(HOME_FILE, read, "the walk must read the home")
        self.assertIn("annotator/server.py", read, "the walk must read the annotator tree")
        self.assertEqual([], [one for one in read if one.startswith("src/sam3/")],
                         "the walk must skip src/sam3")

    def test_the_live_sites_of_the_string_are_the_home_and_the_held_facts(self):
        expected = {HOME_FILE: {HOME_LINE: HOME_FORM}, **HELD_FACTS}
        found = live_literal_sites()
        self.assertEqual(expected, found,
                         'the string "%s" must stand in %s:%s and in the held facts alone:'
                         "\n%s" % (HOME_VALUE, HOME_FILE, HOME_LINE,
                                   "\n".join(f"  {relative}:{number}: {text}"
                                             for relative, sites in sorted(found.items())
                                             for number, text in sorted(sites.items()))))

    def test_the_client_headers_and_the_page_half_are_not_defaults(self):
        """A request of a client and a fetch of a page are not a reply of a writer."""
        read = [path.relative_to(ROOT).as_posix() for path in walked_files()]
        for relative in HEADER_FILES:
            with self.subTest(header=relative):
                self.assertEqual([], default_sites(relative),
                                 "a client request header must not become a reply default")
        for relative, pinned in PAGE_FACTS.items():
            with self.subTest(fact=relative):
                lines = text_of(relative).splitlines()
                for number, form in sorted(pinned.items()):
                    self.assertEqual(form, lines[number - 1].strip(),
                                     f"{relative}:{number} no longer holds its own fact")
                if relative.endswith(".py"):
                    self.assertIn(relative, read, "a pid module is a python module")
                    self.assertEqual([], default_sites(relative),
                                     "the page of a pid module must not become a default")
                else:
                    self.assertNotIn(relative, read,
                                     "a page file is not a python module of the walk")

    def test_a_planted_default_is_reported_with_its_file_and_line(self):
        original = text_of(BINDING_FILES[0])
        live = f"{CTYPE_ARGUMENT}={HOME_NAME}"
        self.assertIn(live, original, f"the live writer must read {live}")
        planted_text = original.replace(live, f'{CTYPE_ARGUMENT}="{HOME_VALUE}"')
        self.assertNotEqual(original, planted_text, "the plant must change the text")
        planted_line = f'{CTYPE_ARGUMENT}="{HOME_VALUE}"'
        number = next(number for number, line in
                      enumerate(planted_text.splitlines(), 1) if planted_line in line)
        with tempfile.TemporaryDirectory() as folder:
            planted = Path(folder) / "planted_server.py"
            planted.write_text(planted_text, encoding="utf-8")
            found = default_sites(str(planted), planted_text)
        self.assertEqual(1, len(found), found)
        self.assertIn(f"{planted}:{number}: def _send(self, code, body,"
                      f' ctype="{HOME_VALUE}"):', found[0])
        self.assertIn(f"{HOME_FILE}.{HOME_NAME}", found[0])


if __name__ == "__main__":
    unittest.main()
