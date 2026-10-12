"""One ball label table, and one clip floor, each held to one home in the console and one in the service.

Round 68, two rows of the walk of this round.

* **The ball label table.**  ``annotator/unified_server.py`` owns what the store holds: the
  wire value ``-1`` is the word ``"u"`` (unknown), and ``None``, ``"clear"`` and ``-2`` delete
  the row.  ``annotator/app.js`` owns the echo the panel reads before the service answers.
  Until round 68 it stated the pair as a literal of its own - ``label === -1 ? 'u' : label`` -
  so the operator saw the number ``-2`` where the store held no row, and the word ``"u"`` went
  back to the service as a clear.  Each realm now states the table once.  The service holds it
  in three module names, and the console holds it in three ``const`` lines.
* **The 0.2 s clip floor.**  ``annotator/app.js`` holds the shortest window the console clips
  and plays.  ``annotator/unified_server.py`` holds the shortest window the encoder is asked
  for: a shorter window at the end of a video is one frame, so the route refuses it.  Until
  round 68 both stated the number as a bare literal (``annotator/app.js:740`` and
  ``annotator/unified_server.py:1952``), and no case named either.  The floor is **not** the
  named clamp ``CLIP_MIN_S = 0.25`` / ``CLIP_MAX_S = 5.0``.  That clamp bounds the window a
  caller may *name*, and round 40 closed it.

The shape of the console rule.  The console is one static file.  It reads no schema of the
server.  It draws its panel before any request returns.  A table the service publishes costs
a route and a fetch for a label verb the panel already holds, and the answer arrives after the
operator clicked.  The console therefore holds its own names, and this module holds the
statements equal.  It reads the source text of ``annotator/app.js``, the way
``tests/test_console_service_bounds.py`` reads ``annotator/ops.js`` for the replay rate bound.
Round 85 adds the two served readers of the same table: the stage of ``annotator/vision-stage.js``
and the review page of ``annotator/label.html``.  This module reads the three files and holds
them equal.  It never edits those files.

Why a new module, and not ``tests/test_console_service_bounds.py``: that module holds the
replay rate bound and the race-to set of round 64, and its docstring states that scope.  This
module holds the two rules of round 68, and the two write scopes stay apart.

Seven rules, one pass over three files:

1. **home rule, console** - the pair, the clearing picks and the clearing wire value stand on
   three lines of ``annotator/app.js``, and the write and the window read them by name.
2. **home rule, service** - each of the three table names of ``annotator/unified_server.py``
   stands once, and the gate and the stored mapping read them by name.
3. **label rule** - the two tables are one table.  The wire value ``-1`` stores the word
   ``"u"``.  Every clearing value of the service is a value the console holds.  The service is
   driven over every row.
4. **floor rule** - the two floor names stand once per realm, the two values are equal, and
   the window site and the refusal site both read the name.
5. **meaning rule** - the floor is the length the service refuses under.  At the console's own
   floor the route encodes a window of that length, and a little under it the route refuses.
6. **copy rule** - a planted second statement of either rule is reported, with its line.
7. **reader rule** - each served reader of the table holds the two owner values, and no reader
   holds a value of its own.

What this case does not see
---------------------------
* It reads the console by one regex per statement.  A third statement of the table in a form
  this module does not match - a label built at run time, a second panel - is invisible to it.
* It reads text and not meaning on the console side.  The rows of the console are driven in
  ``tests/test_app_timeline.js``, which is the case that holds the wire value and the echo.
* It holds the readers to the pattern of today.  A later round that moves a comparison or a
  button attribute must move the pattern here in the same change.  The three sites are
  ``annotator/vision-stage.js:347`` (``labelText``), ``annotator/vision-stage.js:1334`` (the
  number the unknown button posts) and ``annotator/label.html:61`` (the state of a crop).
  The page compares the stored word a second time at line 101 of the same file, and this
  module holds that line by the same rule.
* It pins the numbers of today and not the reason for them.  A later round that raises the
  floor must raise the frozen pair here in the same change.
* It holds the floor equal in value and in meaning at the end of a video.  Which window the
  operator should see for a very short video is a product decision.
"""
import re
import tempfile
import unittest
from pathlib import Path

from annotator.unified_server import APIError, Backend, atomic_save, load

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / 'annotator' / 'app.js'
SERVICE = ROOT / 'annotator' / 'unified_server.py'
CONSOLE_TEXT = CONSOLE.read_text(encoding='utf-8')
SERVICE_TEXT = SERVICE.read_text(encoding='utf-8')

#: The two served readers of the table, outside the console and the service.  The stage draws
#: the unknown button and names the unknown row.  The review page reads the stored word for
#: the state of a crop.  Each file is read once, by its own path.
VISION = ROOT / 'annotator' / 'vision-stage.js'
LABEL_PAGE = ROOT / 'annotator' / 'label.html'
READER_PATHS = (VISION, LABEL_PAGE)

#: The table and the floor as they stand today.  The cases freeze them, so a reader can
#: follow the ground of round 68.
LABEL_TODAY = {'wire': -1, 'stored': 'u', 'cleared': (None, 'clear', -2), 'picks': ('clear', -2)}
FLOOR_TODAY = 0.2

#: The one line of the console that states the pair, and the one line of the service that
#: states each half of it.
CONSOLE_PAIR_HOME = re.compile(
    r"^const BALL_LABEL_UNKNOWN_WIRE = (-?\d+), BALL_LABEL_UNKNOWN_STORED = '([^']+)';$", re.MULTILINE)
SERVICE_WIRE_HOME = re.compile(r"^BALL_LABEL_UNKNOWN_WIRE = (-?\d+)$", re.MULTILINE)
SERVICE_STORED_HOME = re.compile(r"^BALL_LABEL_UNKNOWN_STORED = '([^']+)'$", re.MULTILINE)

#: The one line of each realm that states the clearing values.  The console names the two
#: picks the panel and the keyboard make, and the wire value it sends for them.  The service
#: names the three wire values it clears the row on.
CONSOLE_PICKS_HOME = re.compile(r"^const BALL_LABEL_CLEAR_PICKS = \[([^\]]+)\];$", re.MULTILINE)
CONSOLE_CLEARED_HOME = re.compile(r"^const BALL_LABEL_CLEARED_WIRE = ([^;]+);$", re.MULTILINE)
SERVICE_CLEARED_HOME = re.compile(r"^BALL_LABEL_CLEARED_WIRE = \(([^)]+)\)$", re.MULTILINE)

#: The one line of each realm that states the floor.
CONSOLE_FLOOR_HOME = re.compile(r"^const CLIP_FLOOR_S = ([0-9.]+);$", re.MULTILINE)
SERVICE_FLOOR_HOME = re.compile(r"^CLIP_FLOOR_S = ([0-9.]+)$", re.MULTILINE)

#: The console sites that must read the table by name: the wire value of the write, the
#: stored value of the echo, the echo itself, the receipt of the click, and the window.
CONSOLE_WIRE_READ = re.compile(r"^  const label = ballLabelWire\(value\);$", re.MULTILINE)
CONSOLE_STORED_READ = re.compile(r"^  const stored = ballLabelStored\(value\);$", re.MULTILINE)
CONSOLE_ECHO_READ = re.compile(
    r"^    if \(stored === null\) delete state\.balls\.labels\[file\]; else state\.balls\.labels\[file\] = stored;$",
    re.MULTILINE)
CONSOLE_RECEIPT_READ = re.compile(r"text\(labelValueText\(stored\)\)")
CONSOLE_WINDOW_READ = re.compile(r"Math\.max\(from \+ CLIP_FLOOR_S, to\)")

#: The service sites that must read the table by name: the gate of the route, the stored
#: mapping, and the refusal of a window under the floor.
SERVICE_GATE_READ = re.compile(
    r"^        if isinstance\(label, bool\) or not \(label in BALL_LABEL_CLEARED_WIRE$", re.MULTILINE)
SERVICE_MAP_READ = re.compile(
    r"^        stored = None if label in BALL_LABEL_CLEARED_WIRE else "
    r"\(BALL_LABEL_UNKNOWN_STORED if label == BALL_LABEL_UNKNOWN_WIRE else label\)$", re.MULTILINE)
SERVICE_FLOOR_READ = re.compile(r"^        if duration < CLIP_FLOOR_S:$", re.MULTILINE)

#: The one route the review page posts a label to.  The route carries the stored word of the
#: owner, so the page and the stage speak of one vocabulary.
LABEL_ROUTE_READ = re.compile(r"fetch\('/api/ball_label'")


def lines_of(text):
    """The lines of one file, with the number a reader counts.

    A newline alone does not always end a line: the stage holds template strings with the
    exotic line separators that ``str.splitlines`` breaks on.  One line then carries two
    of the numbers a reader counts, and the number of an edit shifts by one.  Every count
    here uses ``splitlines``, the reader that agrees with the source editor.
    """
    return list(enumerate(text.splitlines(), 1))


def statements(text):
    """Every line of one source file that is not a whole-line comment, with its number."""
    return [(number, line) for number, line in lines_of(text)
            if not line.lstrip().startswith(('//', '#'))]


def pair_copies(text):
    """The lines that state the pair with literals, outside the one home line."""
    return [(number, line.strip()) for number, line in statements(text)
            if '-1' in line and ("'u'" in line or '"u"' in line) and not CONSOLE_PAIR_HOME.match(line)]


def clear_copies(text):
    """The lines that state the clearing values with literals, outside the two home lines."""
    return [(number, line.strip()) for number, line in statements(text)
            if 'clear' in line and '-2' in line
            and not CONSOLE_PICKS_HOME.match(line) and not SERVICE_CLEARED_HOME.match(line)]


def floor_copies(text):
    """The lines that state the floor as the literal 0.2, outside the two home lines."""
    return [(number, line.strip()) for number, line in statements(text)
            if re.search(r'0\.2(?![0-9])', line)
            and not CONSOLE_FLOOR_HOME.match(line) and not SERVICE_FLOOR_HOME.match(line)]


def literal(token):
    """One value of a home line: the python or the javascript spelling, resolved."""
    token = token.strip()
    if token.startswith(("'", '"')):
        return token.strip("'\"")
    if token in ('None', 'null'):
        return None
    return int(token) if token.lstrip('-').isdigit() else float(token)


def home(pattern, text, name):
    """The one line of a file that states a rule, or a failure that names the file."""
    hit = pattern.search(text)
    assert hit is not None, f'{name} must state this rule on one line'
    return hit


def reader_text(path):
    """The whole source text of one served reader."""
    return path.read_text(encoding='utf-8')


def owner_pair():
    """The two owner values of the pair: the service states both, and one home line holds both."""
    wire = int(home(SERVICE_WIRE_HOME, SERVICE_TEXT, SERVICE.name).group(1))
    stored = home(SERVICE_STORED_HOME, SERVICE_TEXT, SERVICE.name).group(1)
    pair = home(CONSOLE_PAIR_HOME, CONSOLE_TEXT, CONSOLE.name)
    return wire, stored, (int(pair.group(1)), pair.group(2))


def wire_spelling(wire):
    """The owner value as a javascript reader spells the number."""
    return str(wire)


def stored_spelling(stored):
    """The owner value as a javascript reader spells the word between single quotes."""
    return "'%s'" % stored


def line_at(text, number):
    """The text of one line, by the number this module counts."""
    found = dict(lines_of(text))
    return found.get(number, '')


def holds(pattern, text):
    """A pattern and the line number it finds, or ``None``."""
    for number, line in lines_of(text):
        if pattern.search(line):
            return number
    return None


def vision_label_pattern(wire, stored):
    """The one test of an unknown row, built from the two owner values."""
    return re.compile(r"label\s*===\s*%s\s*\|\|\s*label\s*===\s*%s"
                      % (re.escape(stored_spelling(stored)), re.escape(wire_spelling(wire))))


def vision_button_pattern(wire):
    """The markup that posts the wire value of the owner, built from that value.

    The pattern holds the whole attribute of a button value.  A shorter pattern also
    matches the inside of a template string, where the markup is not a button yet.
    """
    return re.compile(r'data-vs-value="%s"' % re.escape(wire_spelling(wire)))


def vision_unknown_button_pattern(wire):
    """The one button of the stage that labels an unknown crop, built from the owner value.

    The action of the unknown button and the wire value both stand on the line.  The
    pattern holds the two together, so it cannot match another button that posts the
    same number.  The case builds the pattern from the owner value and not from text.
    """
    action = re.escape('label' + '-' + 'ball')
    return re.compile(r'data-vs-action="%s"\s+data-vs-value="%s"'
                      % (action, re.escape(wire_spelling(wire))))


def vision_label_site():
    """The action of the unknown button of the stage, as a pattern.

    The line of that action is the site.  The case finds the site by the action instead
    of a line number, so the guard keeps no second owner of the pair.
    """
    return re.compile(r'data-vs-action="%s"' % re.escape('label' + '-' + 'ball'))


def vision_button_site():
    """The piece of markup that carries a button value in the stage, as a pattern."""
    return re.compile(r'data-vs-value=')


def vision_label_lines(text):
    """Every line of the stage that holds the action of the unknown button."""
    return [number for number, body in statements(text) if vision_label_site().search(body)]


def stored_test_pattern(stored):
    """The one test of the stored word in a reader, built from the owner stored value."""
    return re.compile(r"===\s*%s" % re.escape(stored_spelling(stored)))


def reader_sites():
    """Each served reader with the name and the pattern of every site this module holds.

    Every pattern is built from the owner values, so the two owner homes stay the one
    source of the pair.  The name of a site tells the reader what the site does.
    """
    wire, stored, _ = owner_pair()
    return (
        (VISION, (
            ('the row name test of the stage', vision_label_pattern(wire, stored)),
            ('the unknown button of the stage', vision_unknown_button_pattern(wire)),
        )),
        (LABEL_PAGE, (
            ('a test of the stored word', stored_test_pattern(stored)),
        )),
    )


class ConsoleServiceAgreement(unittest.TestCase):
    """The ball label table and the clip floor, across the console and the service."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def crop(self, name):
        """A backend over one directory, with the one crop the label route reads."""
        backend = Backend(self.root / name)
        folder = self.root / name / 'out' / 'unlabeled_crops'
        atomic_save(folder / 'meta.json', [{'file': str(folder / 'crop.jpg'), 't': 70}])
        (folder / 'crop.jpg').write_bytes(b'crop')
        return backend, folder

    def test_the_ball_label_table_stands_once_in_the_console(self):
        """Three console lines state the table, and the write reads them by name."""
        pair = home(CONSOLE_PAIR_HOME, CONSOLE_TEXT, CONSOLE.name)
        self.assertEqual(len(CONSOLE_PAIR_HOME.findall(CONSOLE_TEXT)), 1,
                         f'{CONSOLE.name} must state the pair on one line')
        self.assertEqual((int(pair.group(1)), pair.group(2)),
                         (LABEL_TODAY['wire'], LABEL_TODAY['stored']),
                         f'the pair of {CONSOLE.name} today')
        picks = home(CONSOLE_PICKS_HOME, CONSOLE_TEXT, CONSOLE.name)
        self.assertEqual(tuple(literal(pick) for pick in picks.group(1).split(',')),
                         LABEL_TODAY['picks'], f'the clearing picks of {CONSOLE.name} today')
        cleared = home(CONSOLE_CLEARED_HOME, CONSOLE_TEXT, CONSOLE.name)
        self.assertEqual(literal(cleared.group(1)), None,
                         f'the wire value of a clear in {CONSOLE.name} today')
        for pattern, why in ((CONSOLE_WIRE_READ, 'the write must take its wire value from the table'),
                             (CONSOLE_STORED_READ, 'the echo must take its stored value from the table'),
                             (CONSOLE_ECHO_READ, 'the echo must write the stored value and delete on a clear'),
                             (CONSOLE_RECEIPT_READ, 'the receipt must name the stored value'),
                             (CONSOLE_WINDOW_READ, 'the event window must read the floor by name')):
            self.assertIsNotNone(pattern.search(CONSOLE_TEXT), f'{CONSOLE.name}: {why}')
        copies = pair_copies(CONSOLE_TEXT)
        self.assertEqual(copies, [], f'{CONSOLE.name} must state the pair once: {copies}')
        copies = clear_copies(CONSOLE_TEXT)
        self.assertEqual(copies, [], f'{CONSOLE.name} must state the clearing values once: {copies}')

    def test_the_ball_label_table_stands_once_in_the_service(self):
        """Each service name stands once, and the route reads the table by name."""
        for pattern, count, why in ((SERVICE_WIRE_HOME, 1, 'the wire value of the word'),
                                    (SERVICE_STORED_HOME, 1, 'the word the store holds'),
                                    (SERVICE_CLEARED_HOME, 1, 'the three clearing values')):
            with self.subTest(name=pattern.pattern):
                self.assertEqual(len(pattern.findall(SERVICE_TEXT)), count,
                                 f'{SERVICE.name} must state {why} once')
        home(SERVICE_GATE_READ, SERVICE_TEXT, SERVICE.name)
        self.assertEqual(len(SERVICE_GATE_READ.findall(SERVICE_TEXT)), 1,
                         f'{SERVICE.name} must read the clearing values in one gate')
        home(SERVICE_MAP_READ, SERVICE_TEXT, SERVICE.name)
        self.assertEqual(len(SERVICE_MAP_READ.findall(SERVICE_TEXT)), 1,
                         f'{SERVICE.name} must read the table once in the stored mapping')
        copies = pair_copies(SERVICE_TEXT)
        self.assertEqual(copies, [], f'{SERVICE.name} must state the pair once: {copies}')
        copies = clear_copies(SERVICE_TEXT)
        self.assertEqual(copies, [], f'{SERVICE.name} must state the clearing values once: {copies}')

    def test_the_two_tables_are_one_table(self):
        """The console holds every clearing value of the service, and the service stores the pair."""
        pair = home(CONSOLE_PAIR_HOME, CONSOLE_TEXT, CONSOLE.name)
        picks = home(CONSOLE_PICKS_HOME, CONSOLE_TEXT, CONSOLE.name)
        cleared = home(CONSOLE_CLEARED_HOME, CONSOLE_TEXT, CONSOLE.name)
        console = {literal(pick) for pick in picks.group(1).split(',')} | {literal(cleared.group(1))}
        service = {literal(item) for item in
                   home(SERVICE_CLEARED_HOME, SERVICE_TEXT, SERVICE.name).group(1).split(',')}
        self.assertEqual(console, service,
                         'every value that clears a row in one realm must clear it in the other')
        self.assertEqual(service, set(LABEL_TODAY['cleared']), 'the clearing values today')
        self.assertEqual(int(pair.group(1)),
                         int(home(SERVICE_WIRE_HOME, SERVICE_TEXT, SERVICE.name).group(1)),
                         'the two realms must name the same wire value')
        self.assertEqual(pair.group(2),
                         home(SERVICE_STORED_HOME, SERVICE_TEXT, SERVICE.name).group(1),
                         'the two realms must name the same stored word')
        # The service is driven over every row of that table, and the store answers the table.
        backend, folder = self.crop('labels')
        route = ['api', 'balls', 'unlabeled_crops', 'label']
        original = str(folder / 'crop.jpg')
        rows = [(LABEL_TODAY['wire'], LABEL_TODAY['stored'])]
        rows += [(value, None) for value in LABEL_TODAY['cleared']]
        rows += [(0, 0), (15, 15)]
        for wire, stored in rows:
            with self.subTest(wire=wire):
                atomic_save(folder / 'labels.json', {original: 4})
                backend.post(route, {'file': 'crop.jpg', 'label': wire})
                labels = load(folder / 'labels.json')
                if stored is None:
                    self.assertEqual(labels, {}, f'the wire value {wire!r} must delete the row')
                else:
                    self.assertEqual(labels[original], stored,
                                     f'the wire value {wire!r} must reach the store as {stored!r}')

    def test_the_served_readers_hold_the_pair_of_the_owner(self):
        """Each served reader states the two owner values, and both realms name one pair."""
        wire, stored, console = owner_pair()
        self.assertEqual(console, (wire, stored),
                         'the console and the service must name the pair of the owner')
        for path, sites in reader_sites():
            text = reader_text(path)
            for name, pattern in sites:
                with self.subTest(file=path.name, site=name):
                    self.assertIsNotNone(pattern.search(text),
                                         f'{path.name} must hold {name} with the owner values')

    def test_the_stage_names_the_unknown_row_with_the_pair_of_the_owner(self):
        """The row name test of the stage holds the wire value and the stored word of the owner."""
        wire, stored, _ = owner_pair()
        text = reader_text(VISION)
        pattern = vision_label_pattern(wire, stored)
        line = holds(pattern, text)
        self.assertIsNotNone(line,
                             f'{VISION.name} must name the unknown row with the pair of the owner')
        lines = [number for number, body in statements(text) if pattern.search(body)]
        self.assertEqual(lines, [line],
                         f'{VISION.name} must state the pair of the owner on one line')

    def test_the_stage_posts_the_wire_value_of_the_owner(self):
        """The label action of the stage posts the wire value of the owner."""
        wire, _, _ = owner_pair()
        text = reader_text(VISION)
        value = vision_button_pattern(wire)
        lines = [number for number in vision_label_lines(text)
                 if value.search(line_at(text, number))]
        self.assertEqual(len(lines), 1,
                         f'{VISION.name} must post the wire value of the owner as a button value')
        for number in vision_label_lines(text):
            body = line_at(text, number)
            self.assertIsNotNone(vision_button_site().search(body),
                                 f'{VISION.name}:{number} must post the value as button markup')

    def test_the_review_page_reads_the_stored_word_of_the_owner(self):
        """The review page compares the stored word of the owner, and posts to the label route."""
        _, stored, _ = owner_pair()
        text = reader_text(LABEL_PAGE)
        pattern = stored_test_pattern(stored)
        lines = [number for number, body in statements(text) if pattern.search(body)]
        self.assertGreaterEqual(len(lines), 1,
                                f'{LABEL_PAGE.name} must read the stored word of the owner')
        self.assertIsNotNone(LABEL_ROUTE_READ.search(text),
                             f'{LABEL_PAGE.name} must post a label to the route of the service')

    def test_the_copy_rule_reports_a_second_statement_of_the_pair(self):
        """The detector reports a second statement of the pair.  A stored word alone is no copy."""
        wire, stored, _ = owner_pair()
        planted = "        stored = %s if label === %s else label;\n" % (
            stored_spelling(stored), wire_spelling(wire))
        self.assertEqual(pair_copies(planted), [(1, planted.strip())],
                         'a reader that spells the pair again is a copy')
        self.assertEqual(pair_copies(stored_spelling(stored)), [],
                         'the stored word alone is not a copy of the pair')

    def test_the_readers_report_every_statement_of_the_pair_with_its_line(self):
        """The detector names each line of a reader that spells the pair.  Sight is not a copy."""
        wire, stored, _ = owner_pair()
        lines = []
        for path, sites in reader_sites():
            text = reader_text(path)
            for name, pattern in sites:
                with self.subTest(file=path.name, site=name):
                    numbers = [number for number, body in statements(text) if pattern.search(body)]
                    hits = len(numbers)
                    self.assertGreaterEqual(hits, 1,
                                            f'{path.name} must hold {name} with the owner values')
                    lines.extend((path, number) for number in numbers)
        for path, number in lines:
            with self.subTest(file=path.name, line=number):
                self.assertIn(stored_spelling(stored), line_at(reader_text(path), number),
                              f'{path.name}:{number} must spell the stored word of the owner')
        found = pair_copies(reader_text(VISION))
        expected = [(number, body.strip()) for number, body in statements(reader_text(VISION))
                    for name, pattern in reader_sites()[0][1] if pattern.search(body)]
        self.assertEqual(found, expected,
                         f'{VISION.name} must report each statement of the pair with its line')
        self.assertEqual(pair_copies(reader_text(LABEL_PAGE)), [],
                         f'{LABEL_PAGE.name} reads the word alone, so it states no pair')
        self.assertEqual(pair_copies(reader_text(VISION))[0][0],
                         holds(vision_label_pattern(wire, stored), reader_text(VISION)),
                      f'{VISION.name} must report the line the pair stands on')

    def test_the_clip_floor_stands_once_in_each_realm(self):
        """Two floor names, one number, and both sites read the name."""
        console = home(CONSOLE_FLOOR_HOME, CONSOLE_TEXT, CONSOLE.name).group(1)
        service = home(SERVICE_FLOOR_HOME, SERVICE_TEXT, SERVICE.name).group(1)
        self.assertEqual(len(CONSOLE_FLOOR_HOME.findall(CONSOLE_TEXT)), 1,
                         f'{CONSOLE.name} must state the floor once')
        self.assertEqual(len(SERVICE_FLOOR_HOME.findall(SERVICE_TEXT)), 1,
                         f'{SERVICE.name} must state the floor once')
        self.assertEqual(float(console), float(service), 'the two floors must be one number')
        self.assertEqual(float(console), FLOOR_TODAY, 'the floor today')
        self.assertIsNotNone(SERVICE_FLOOR_READ.search(SERVICE_TEXT),
                             f'{SERVICE.name} must refuse a window through the name, not the number')
        copies = floor_copies(CONSOLE_TEXT)
        self.assertEqual(copies, [], f'{CONSOLE.name} must state the floor once: {copies}')
        copies = floor_copies(SERVICE_TEXT)
        self.assertEqual(copies, [], f'{SERVICE.name} must state the floor once: {copies}')

    def test_the_floor_is_the_length_the_service_refuses_under(self):
        """The console floor is a window the service encodes, and a little under it is a refusal."""
        floor = float(home(CONSOLE_FLOOR_HOME, CONSOLE_TEXT, CONSOLE.name).group(1))
        backend, _ = self.crop('floor')
        encoded = []

        def fake_encode(ffmpeg, source, destination, t0, duration):
            encoded.append(round(duration, 6))
            destination.write_bytes(b'fake-mp4')

        backend._encode_clip = fake_encode
        backend.video = lambda dataset: self.root / 'floor' / 'short.mp4'
        frame = dict(fps=30.0, frame_count=6, width=1280, height=720, timestamp_kind='nominal_cfr')
        # The video ends at the floor, so the end of the video and the floor are one length.
        backend.video_metadata = lambda dataset: dict(dataset=dataset, duration=floor, **frame)
        clip = backend.event_clip('vod30', 0.0, 1.5, 2.5)
        self.assertEqual([floor], encoded, 'the console floor is a window the service encodes')
        self.assertEqual(clip.read_bytes(), b'fake-mp4')
        backend.video_metadata = lambda dataset: dict(dataset=dataset, duration=floor - 0.01, **frame)
        with self.assertRaisesRegex(APIError, '^clip window is empty at the end of the video$'):
            backend.event_clip('vod30', 0.0, 1.5, 2.5)
        self.assertEqual([floor], encoded, 'the refused window encodes nothing')

    def test_a_planted_second_statement_of_either_rule_is_reported(self):
        """The detectors report a second statement of the rule, with its line."""
        planted_pair = "  else state.balls.labels[file] = label === -1 ? 'u' : label;\n"
        self.assertEqual(pair_copies(planted_pair), [(1, planted_pair.strip())],
                         'the shape round 68 removed is a copy')
        self.assertEqual(pair_copies(CONSOLE_TEXT), [], 'the live console reads its own names')
        planted_store = '        stored = None if label in (None, "clear", -2) else ("u" if label == -1 else label)\n'
        self.assertEqual(pair_copies(planted_store), [(1, planted_store.strip())])
        self.assertEqual(pair_copies(SERVICE_TEXT), [], 'the live service reads its own names')
        planted_clear = "const picks = ['clear', -2];\n"
        self.assertEqual(clear_copies(planted_clear), [(1, planted_clear.strip())])
        self.assertEqual(clear_copies(CONSOLE_TEXT), [])
        self.assertEqual(clear_copies(SERVICE_TEXT), [])
        planted_floor = '        if duration < 0.2:\n'
        self.assertEqual(floor_copies(planted_floor), [(1, planted_floor.strip())])
        self.assertEqual(floor_copies(CONSOLE_TEXT), [], 'the live console reads the floor name')
        self.assertEqual(floor_copies(SERVICE_TEXT), [], 'the live service reads the floor name')
