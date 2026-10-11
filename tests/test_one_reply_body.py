"""One body writes the reply of three HTTP handlers, and the source shows it.

Round 55 measured one method body in three class bodies:

* ``annotator/server.py Handler._send``
* ``src/pid_anchor_ui.py Handler._send``
* ``src/pid_seed_ui.py Handler._send``

The three bodies were the same five statements, so a change of the reply shape had to
land in three files and no test compared them. The walk of
``tests/test_duplicate_bodies.py`` reads the top level of a module only, so it never saw
the three copies. Each body now holds one call of ``src/reply_body.write_reply``, and the
three calls name one function object.

The cases below prove the claim in four ways:

* the three ``_send`` bodies hold one statement each, that statement is one call of the
  owner, and the three source bodies are one call when the layout and the comments are
  removed;
* each of the three modules binds the owner function, and the bound object is the object
  ``src/reply_body.py`` holds at run time;
* the owner writes the exact bytes, so the three callers keep the status code, the
  default content type, the ``Content-Length`` header, and the byte count;
* a walk of the class body of the annotator server finds one site of the method, so a
  second copy of the reply body in that module fails there.

The second case also uses the owner and does not copy it: a test that names the owner and
reads it at run time fails when a copy of the owner appears in a caller module, because
the copy is not the object that the case compares.  The case reads the name
``write_reply`` in each caller module, and it does not read the name of the import
statement, because the two spellings of the import give different module attributes.

``annotator/server.py`` reads the name through the dotted module ``src.reply_body``, and
the two ``src/pid_*_ui.py`` modules read the same name through a relative import.  The
three modules bind the one function object, and the cases below read the bound name in
each module.

The last case walks the class body of the annotator server. That walk is the wide form of
the guard in ``tests/test_duplicate_bodies.py``, and it decides the question for a class
body, where the three copies sat. The two ``src/pid_*_ui.py`` modules hold the same body,
and ``test_the_three_source_bodies_are_one_text`` above states all three sites.

Run: ``./scripts/pool-test.sh python test_one_reply_body``
"""
from __future__ import annotations

import ast
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The one module that owns the reply body.
OWNER_MODULE = "reply_body"

#: The one function that writes a reply.
OWNER_NAME = "write_reply"

#: The class method that each handler keeps, and the one call it must hold.
SEND_METHOD = "_send"
OWNER_CALL = "reply_body." + OWNER_NAME

#: The three modules of this repository that answer one HTTP request with one body.
HANDLER_FILES = ("annotator/server.py", "src/pid_anchor_ui.py", "src/pid_seed_ui.py")

#: The module and the name that each of the three modules imports.
OWNER_IMPORT = "src." + OWNER_MODULE


def module_tree(relative):
    """The syntax tree of one module of this repository, read from its file."""
    path = ROOT / relative
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def owner_tree():
    """The syntax tree of the owner module under src/."""
    return module_tree("src/%s.py" % OWNER_MODULE)


def class_node(tree, class_name="Handler"):
    """The class body with one name, read from a module tree."""
    return next((node for node in tree.body
                 if isinstance(node, ast.ClassDef) and node.name == class_name), None)


def method_node(tree, method_name=SEND_METHOD, class_name="Handler"):
    """One method of one class body, or None when the module does not hold it."""
    klass = class_node(tree, class_name)
    if klass is None:
        return None
    return next((node for node in klass.body
                 if isinstance(node, ast.FunctionDef) and node.name == method_name), None)


def own_method_sites(relative, method_name=SEND_METHOD):
    """Every function with one name in one module, as ``module:line Class.method``.

    The walk reads the whole tree, so it reaches a method inside a class body. The
    module-level walk of ``tests/test_duplicate_bodies.py`` does not.
    """
    tree = module_tree(relative)
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != method_name:
            continue
        holder = next((owner.name for owner in tree.body
                       if isinstance(owner, ast.ClassDef)
                       and any(child is node for child in owner.body)), None)
        sites.append("%s:%d %s" % (relative, node.lineno,
                                   "%s.%s" % (holder, node.name) if holder else node.name))
    return sorted(sites, key=lambda site: int(site.split(":")[1].split()[0]))


def imports_from(tree, owner):
    """The names that one module tree imports from one owner module."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == owner:
            found.update(alias.asname or alias.name for alias in node.names)
    return found


def called_call(node):
    """The call of one return statement, as ``the.name(...)`` with the receiver removed.

    A module binds the owner in one of two ways: ``from src.reply_body import
    write_reply`` gives the bare name, and ``from src import reply_body`` gives the module
    attribute.  Both names hold the one function object, so the case below reads the last
    part of the name and not the whole one.
    """
    func = node.value.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id
    return "%s(%s)" % (name, ", ".join(ast.unparse(arg) for arg in node.value.args))


class FakeHandler(BaseHTTPRequestHandler):
    """One handler that records the four calls of one reply and opens no socket."""

    def __init__(self):
        self.status = None
        self.headers = []
        self.written = []
        self.wfile = self

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, keyword, value):
        self.headers.append((keyword, value))

    def end_headers(self):
        self.headers.append(("", ""))

    def write(self, data):
        self.written.append(data)


class OneReplyBodyTest(unittest.TestCase):
    """Three handlers answer one request through one function, and the source shows it."""

    @classmethod
    def setUpClass(cls):
        """Load the three handler modules once. The cases below read the same objects.

        The test runner puts its own arguments in ``sys.argv``. ``annotator/server.py``
        reads ``sys.argv`` while it loads, so this class loads it with one argument, as a
        person who starts the file does.
        """
        import importlib
        import sys

        from src import reply_body

        cls.reply_body = reply_body
        cls.trees = {relative: module_tree(relative) for relative in HANDLER_FILES}
        cls.texts = {relative: (ROOT / relative).read_text(encoding="utf-8")
                     for relative in HANDLER_FILES}
        saved = sys.argv
        sys.argv = [str(ROOT / "annotator" / "server.py")]
        try:
            cls.modules = {relative: importlib.import_module(relative[:-3].replace("/", "."))
                           for relative in HANDLER_FILES}
        finally:
            sys.argv = saved

    def methods(self):
        """The three ``_send`` methods of the three handler classes, by module."""
        return {relative: method_node(tree) for relative, tree in self.trees.items()}

    def test_the_three_source_bodies_are_one_text(self):
        """One call in three files: a body that drifts from the owner fails here."""
        methods = self.methods()
        for relative, method in methods.items():
            with self.subTest(module=relative):
                self.assertIsNotNone(
                    method, "%s holds a class body Handler, and that class holds no %s"
                    % (relative, SEND_METHOD))
                self.assertEqual(
                    1, len(method.body),
                    "%s Handler.%s holds %d statements, so it holds a rule of its own"
                    % (relative, SEND_METHOD, len(method.body)))
                self.assertIsInstance(
                    method.body[0], ast.Return,
                    "%s Handler.%s must return the answer of the one owner" % (relative, SEND_METHOD))
                self.assertEqual(
                    "%s(self, code, body, ctype)" % OWNER_NAME,
                    called_call(method.body[0]),
                    "%s Handler.%s must call %s and pass self, the code, the body, and the type"
                    % (relative, SEND_METHOD, OWNER_CALL))
        bodies = {relative: ast.dump(method.body[0]) for relative, method in methods.items()}
        self.assertEqual(
            1, len(set(bodies.values())),
            "the three %s bodies differ by statement, so one of them is a second copy: %s"
            % (SEND_METHOD, bodies))
        rule_lines = {relative: [line.strip() for line
                                 in ast.get_source_segment(self.texts[relative], method).splitlines()
                                 if line.strip() and not line.strip().startswith("#")]
                      for relative, method in methods.items()}
        for relative, lines in rule_lines.items():
            with self.subTest(module=relative):
                self.assertEqual(
                    2, len(lines),
                    "%s Handler.%s writes the reply in %d lines, and it must hold the signature "
                    "and one call: %s" % (relative, SEND_METHOD, len(lines), lines))
                self.assertIn(
                    "write_reply(", lines[1],
                    "%s Handler.%s holds %s, and it must call the one owner"
                    % (relative, SEND_METHOD, lines[1]))
        self.assertEqual(
            1, len({tuple(lines) for lines in rule_lines.values()}),
            "the three %s bodies are not one call when the layout and the comments are removed, "
            "so one of them holds a second rule: %s" % (SEND_METHOD, rule_lines))

    def test_the_three_classes_call_the_one_owner(self):
        """Each class reads one function object, and that object is src.reply_body.write_reply."""
        owners = [node.name for node in owner_tree().body if isinstance(node, ast.FunctionDef)]
        self.assertEqual(
            [OWNER_NAME], owners,
            "src/%s.py holds %s, and its one function is %s"
            % (OWNER_MODULE, owners or "no function", OWNER_NAME))
        self.assertIs(
            self.reply_body.write_reply, getattr(self.reply_body, OWNER_NAME),
            "src/%s.py does not hold %s" % (OWNER_MODULE, OWNER_NAME))
        for relative, tree in self.trees.items():
            with self.subTest(module=relative):
                self.assertIn(
                    OWNER_NAME, imports_from(tree, OWNER_IMPORT),
                    "%s does not import %s from %s" % (relative, OWNER_NAME, OWNER_IMPORT))
                module = self.modules[relative]
                self.assertIs(
                    module.write_reply, self.reply_body.write_reply,
                    "%s holds a second body named %s, not the owner function"
                    % (relative, OWNER_NAME))
                self.assertEqual(
                    1, len(method_node(tree).body),
                    "%s Handler.%s holds %d statements, so it holds a rule of its own"
                    % (relative, SEND_METHOD, len(method_node(tree).body)))

    def test_the_owner_writes_the_exact_reply(self):
        """The bytes, the content type, and the content length of one reply."""
        handler = FakeHandler()
        self.reply_body.write_reply(handler, 201, b'{"ok":true}')
        self.assertEqual(201, handler.status, "the owner must write the status code it is given")
        self.assertEqual(
            [("Content-Type", "application/json"), ("Content-Length", "11"), ("", "")],
            handler.headers,
            "the owner must write the content type, the byte count, and the empty line")
        self.assertEqual(
            [b'{"ok":true}'], handler.written,
            "the owner must write the body bytes once, and write nothing else")
        self.assertEqual(
            len(b'{"ok":true}'), int(handler.headers[1][1]),
            "the content length must be the count of the bytes that follow")
        jpeg = FakeHandler()
        self.reply_body.write_reply(jpeg, 200, b"\xff\xd8\xff", "image/jpeg")
        self.assertEqual(
            [("Content-Type", "image/jpeg"), ("Content-Length", "3"), ("", "")], jpeg.headers,
            "a caller with a second content type must get that content type, not the default")
        self.assertEqual(
            [b"\xff\xd8\xff"], jpeg.written,
            "the content length of a JPEG reply must be the count of those bytes too")

    def test_the_reply_body_has_one_site_in_the_annotator_server(self):
        """A class body walk: a second copy of the method in that module fails here.

        The walk of ``tests/test_duplicate_bodies.py`` reads the top level of a module, so
        it cannot see a method body. This case walks into the class body of the annotator
        server, where one of the three copies sat, and it refuses a second copy.
        """
        sites = own_method_sites("annotator/server.py")
        self.assertEqual(
            1, len(sites),
            "annotator/server.py holds %d sites of the reply method: %s. One site is the "
            "call of %s, and a second site is a copy of the reply body."
            % (len(sites), ", ".join(sites) or "nowhere", OWNER_CALL))
        self.assertTrue(
            sites[0].startswith("annotator/server.py:") and sites[0].endswith("Handler._send"),
            "the one site of the reply method is %s, and it must be a method of Handler"
            % sites[0])
