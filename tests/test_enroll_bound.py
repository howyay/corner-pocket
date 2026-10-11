"""One enrollment size bound, held to its one owner on four surfaces.

``annotator/unified_server.py`` is the owner.  ``_MAX_ENROLL_BYTES`` is the named
fact: the decoded image of one enrollment is at most 8 MiB.
``_MAX_ENROLL_BODY_BYTES`` derives from it, and the enroll branch of the dispatch
reads the derived name.  Two more statements of the same bound stand outside
python: the photo guard of ``annotator/ops.js`` (``photo.size > 8 * 1024 * 1024``,
with the operator sentence in both languages beside it) and one row of each of two
documents.  Until round 60 the dispatch cap was its own literal, free to disagree
with the decoded cap, and no case read the console or either document.

Six rules, one pass over four files:

1. **owner rule** - the derived cap is the base64 form of the decoded cap (4 bytes
   for every 3, rounded up) plus one stated margin, and the two frozen sizes of
   today stand: 8388608 bytes decode, 12582912 bytes reach the route.
2. **boundary rules** - an image of exactly 8 MiB passes the decoded guard, and one
   byte more is refused with the sentence of the guard.  A body of exactly 12 MiB
   reaches the route, and one byte more is refused before the payload is read.
3. **console rule** - the guard of ``annotator/ops.js`` and its two operator
   sentences state the owner's number.  This case reads the other language's source
   text, the way ``tests/test_app_quad_contract.py`` reads ``annotator/app.js``.  It
   never edits that file.
4. **document rule** - the row that names the enroll form in
   ``docs/form-contract-audit.md`` and the row that names the enroll route in
   ``docs/face-identification-assessment.md`` state one size each, and it is the
   owner's size.

What this case does not see
---------------------------
* it reads the four surfaces **by name**.  A fifth statement of the bound - a third
  document, a second console guard - is invisible to it;
* it reads text and not meaning.  A document row can hold the owner's number in an
  unrelated sentence and pass, and a row that states the bound in other words is
  outside the rule;
* it does not measure the enroll models.  ``tests/test_unified_server.py`` holds the
  pipeline seam, and the boundary cases here stop at the decode step;
* the console sentences say ``8 MB``, the operator spelling of the owner's 8 MiB.
  This case compares the two numbers, not the two units;
* it pins today's sizes and not the reason for them.  A later round that raises the
  decoded cap must raise the frozen sizes here in the same change.
"""
import base64
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from annotator.unified_server import (Backend, _MAX_ENROLL_BODY_BYTES, _MAX_ENROLL_BYTES,
                                      make_handler)

ROOT = Path(__file__).resolve().parents[1]

#: The two sizes the bound holds today.  The cases freeze them: 8 MiB decodes and
#: 12 MiB arrives, so a reader can follow the ground of round 60.
IMAGE_CAP_TODAY = 8 * 1024 * 1024
BODY_CAP_TODAY = 12 * 1024 * 1024

#: The sentence the decoded guard raises, read back from the module that raises it.
BOUND_REFUSAL = 'image_base64 decodes past the 8MB limit'

#: The surfaces beside the owner.
CONSOLE = ROOT / 'annotator' / 'ops.js'
OWNER = ROOT / 'annotator' / 'unified_server.py'
CONSOLE_TEXT = CONSOLE.read_text(encoding='utf-8')
OWNER_TEXT = OWNER.read_text(encoding='utf-8')

#: The enroll branch of the dispatch: the name the route reads as its limit.
DISPATCH_LIMIT = re.compile(r'limit = (\S+) if parts\[:3\] == \["api", "identity", "enroll"\] else')

#: The console guard: the byte count a photo must not pass.
CONSOLE_GUARD = re.compile(r'photo\.size\s*>\s*([0-9*\s]+?)\s*\?')

#: The console row: the one sentence pair the operator reads under the file input.
CONSOLE_WORD = re.compile(r'photoSize:\[([^\]]*)\]')

#: One row per document, with the needles that find it.  Each needle pair must match
#: exactly one line, or the case fails and names the document.
DOC_ROWS = (
    (ROOT / 'docs' / 'form-contract-audit.md', ('enroll-form', 'cap')),
    (ROOT / 'docs' / 'face-identification-assessment.md', ('identity/enroll', 'cap')),
)


def product(text):
    """The value of a javascript product such as ``8*1024*1024``, from source text."""
    parts = [part.strip() for part in text.split('*')]
    if not parts or not all(part.isdigit() for part in parts):
        raise AssertionError(f'{text!r} is not a product of integers')
    value = 1
    for part in parts:
        value *= int(part)
    return value


def doc_row(path, needles):
    """The one line of ``path`` that holds every needle."""
    rows = [line for line in path.read_text(encoding='utf-8').splitlines()
            if all(needle in line for needle in needles)]
    if len(rows) != 1:
        raise AssertionError(f'{path.name} holds {len(rows)} rows that name the enroll cap; '
                             f'the case needs one')
    return rows[0]


class EnrollBound(unittest.TestCase):
    """The size bound of one enrollment, on the four surfaces that state it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backend = Backend(Path(self.temp.name))

    def handler(self, path, body=b"", headers=None):
        """A handler over a memory file, the shape tests/test_unified_server.py uses."""
        handler = make_handler(self.backend).__new__(make_handler(self.backend))
        handler.path = path
        handler.headers = headers or {}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.send_response = lambda status: setattr(handler, 'status', status)
        handler.response_headers = {}
        handler.send_header = lambda key, value: handler.response_headers.update({key: value})
        handler.end_headers = lambda: None
        return handler

    def post(self, path, body):
        """Dispatch one POST body and return the status and the answer bytes."""
        headers = {'Host': '127.0.0.1:8130', 'Origin': 'http://127.0.0.1:8130',
                   'Content-Type': 'application/json', 'Content-Length': str(len(body))}
        handler = self.handler(path, body, headers)
        handler.dispatch(post=True)
        return handler.status, handler.wfile.getvalue()

    def enroll_body(self, image):
        """The JSON body of one enrollment whose image decodes to ``image``."""
        return json.dumps({'player_id': 'P',
                           'image_base64': base64.b64encode(image).decode('ascii')}).encode()

    def assert_owner_size(self, row):
        """The row states one size, and it is the owner's size in the owner's unit."""
        stated = re.findall(r'(\d+)\s*(MiB|MB)', row)
        self.assertEqual(stated, [(str(_MAX_ENROLL_BYTES // (1024 * 1024)), 'MiB')],
                         f'the row must state the owner cap and no other size:\n{row}')

    def test_the_derived_cap_holds_the_sizes_of_today(self):
        """One owner: the decoded 8 MiB, and the 12 MiB body derived from it."""
        self.assertEqual(_MAX_ENROLL_BYTES, IMAGE_CAP_TODAY)
        self.assertEqual(_MAX_ENROLL_BODY_BYTES, BODY_CAP_TODAY)
        encoded = (IMAGE_CAP_TODAY + 2) // 3 * 4     # the base64 form of the decoded cap
        self.assertLess(encoded, _MAX_ENROLL_BODY_BYTES,
                        'the derived cap must hold the base64 form of the decoded cap')

    def test_the_enroll_branch_reads_the_derived_name(self):
        """The route holds no size of its own; it reads the name the owner gives it."""
        # The branch reads the two names, so the tree decides and not the layout:
        # round 66 split the assignment over two lines when the default arm got its
        # own name, and a line-shaped check would refuse that.
        import ast
        arms = [node for node in ast.walk(ast.parse(OWNER_TEXT))
                if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.IfExp)
                and any(isinstance(target, ast.Name) and target.id == 'limit'
                        for target in node.targets)]
        self.assertEqual(len(arms), 1,
                         f'the enroll branch of {OWNER} changed shape: one limit assignment')
        branch = arms[0].value
        self.assertIsInstance(branch.body, ast.Name)
        self.assertEqual(branch.body.id, '_MAX_ENROLL_BODY_BYTES')
        self.assertIsInstance(branch.orelse, ast.Name,
                              'the default arm must read a named constant and no number')
        # A filler is not JSON, so the dispatch answers 400 - and never 413 - when it
        # takes the body, and the payload never reaches a decode.
        filler = b'A' * _MAX_ENROLL_BODY_BYTES
        self.assertEqual(self.post('/api/identity/enroll', filler)[0], 400)
        self.assertEqual(self.post('/api/identity/enroll', filler + b'A')[0], 413)
        # The 64 KB default of every other route stands.
        self.assertEqual(self.post('/api/operations', filler)[0], 413)

    def test_an_image_of_exactly_the_decoded_cap_passes_the_bound(self):
        """Exactly 8 MiB decodes, so the guard hands it to the decoder."""
        body = self.enroll_body(b'\0' * _MAX_ENROLL_BYTES)
        self.assertLessEqual(len(body), _MAX_ENROLL_BODY_BYTES, 'the body must fit the dispatch cap')
        status, answer = self.post('/api/identity/enroll', body)
        message = json.loads(answer)['error']
        self.assertEqual(status, 400)
        self.assertNotEqual(message, BOUND_REFUSAL, 'exactly the cap must pass the decoded guard')
        self.assertEqual(message, 'image_base64 is not a decodable image')

    def test_one_byte_more_than_the_decoded_cap_is_refused(self):
        """One byte past 8 MiB meets the guard, and its sentence names the bound."""
        body = self.enroll_body(b'\0' * (_MAX_ENROLL_BYTES + 1))
        self.assertLessEqual(len(body), _MAX_ENROLL_BODY_BYTES, 'the body must fit the dispatch cap')
        status, answer = self.post('/api/identity/enroll', body)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(answer)['error'], BOUND_REFUSAL)

    def test_the_console_number_is_the_owner_number(self):
        """The photo guard and its two sentences state the owner's number."""
        hit = CONSOLE_GUARD.search(CONSOLE_TEXT)
        self.assertIsNotNone(hit, f'the photo guard of {CONSOLE} changed shape: '
                                  f'{CONSOLE_GUARD.pattern}')
        self.assertEqual(product(hit.group(1)), _MAX_ENROLL_BYTES,
                         'the console guard and the python owner must hold one number')
        row = CONSOLE_WORD.search(CONSOLE_TEXT)
        self.assertIsNotNone(row, f'the photoSize sentence pair left {CONSOLE}')
        stated = [int(number) for number in re.findall(r'(\d+)\s*MB', row.group(1))]
        self.assertEqual(stated, [_MAX_ENROLL_BYTES // (1024 * 1024)] * 2,
                         'the English sentence and the Chinese sentence must state the owner size')

    def test_the_form_contract_document_states_the_owner_cap(self):
        """The enroll row of the form contract states one size, the owner's."""
        self.assert_owner_size(doc_row(*DOC_ROWS[0]))

    def test_the_face_document_states_the_owner_cap(self):
        """The enroll row of the face assessment states one size, the owner's."""
        self.assert_owner_size(doc_row(*DOC_ROWS[1]))
