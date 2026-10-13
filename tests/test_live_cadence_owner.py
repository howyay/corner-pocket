"""Round 102: one home for the live cadence key of a stage dict.

The console page reads the cadence of each live pipeline stage from the payload key
``every_n_frames``.  One fact stood in two homes and no reader held the two equal:

* The producer.  ``RallyProcessor.status`` (``annotator/live_processing.py:736``) builds the stage
  dict of the live snapshot; before this round one field of that dict was the literal
  ``annotator/live_processing.py:769`` -
  ``                     **{STAGE_CADENCE_KEY: getattr(stage, STAGE_CADENCE_KEY, 1) or 1},`` -
  which now writes the owner constant.
* The reader.  ``annotator/vision-stage.js:938`` held
  ``    const cadence = Number(stage.every_n_frames) > 1`` and now reads
  ``    const cadence = Number(stage['every_n_frames']) > 1`` - inside ``liveStageLine``
  (``annotator/vision-stage.js:934``), which the panel calls at ``annotator/vision-stage.js:1079``.
  The same key was read again at ``annotator/vision-stage.js:939``.

Drift: a rename at the producer with a static reader in the page left the page reading a key that
the payload no longer carried.  The page then printed ``every 1 frame`` for every stage and stated
a cadence that no stage had, and no case failed.  A rename at the reader alone left the served key
unread, with the same silent line and a green suite.

* ``tests/test_pipeline_stages.py:192`` - ``        stage.every_n_frames = 3`` - sets a python
  attribute on a test object.  It never reads the served payload key.
* ``tests/test_app_timeline.js:2512`` - ``    stages:[{name:'table', every_n_frames:30, ...`` -
  the page case builds its own fixture key, so the fixture agrees with itself.

The decision of this round is one home for the key name.  ``annotator/live_processing.py`` owns the
constant ``STAGE_CADENCE_KEY`` (``annotator/live_processing.py:43``), and the stage dict of the live
snapshot is built with that constant.  The wire format did not change: the key is still the word
``every_n_frames``, so every reader of the panel keeps working.  The page reads the key from the
stage object as data - ``annotator/vision-stage.js:938`` now reads ``stage['every_n_frames']`` - and
the bracket form makes the key of the page a value, which this guard holds to the owner constant.
A value that moves in one half alone goes red here.

What this module reads, and what it does not:

* It reads the owner constant from the imported module, not from a copy of the file text, and it
  reads the text of ``annotator/vision-stage.js`` one line at a time.
* It never writes a source file.  The planted case replaces a string in a dict in this process, and
  that copy dies with the process.
* Its key detector holds two static spellings of one read: ``stage.<key>`` and ``stage['<key>']``.
  A comment that names the key, a string of another key, and a computed read such as
  ``stage['every' + '_n_frames']`` are invisible to it.
* It builds one real ``LiveProcessor`` with one real stage and reads the stage dict of that
  processor's own live snapshot.  The payload case states the value 3, which is the value it sets on
  the stage object, and it reads the wire field with the owner constant.
* It does not read ``tests/test_pipeline_stages.py``, ``tests/test_app_timeline.js`` or
  ``docs/live-processing-verification.md``.  Those keep the cases and the prose they had.
* It has no skip site: a skip would hide the defect this module exists to catch.
"""

from __future__ import annotations

import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
for _path in (str(ROOT), str(TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from annotator.live_processing import STAGE_CADENCE_KEY, LiveProcessor  # noqa: E402
from annotator.pipeline_stages import CallableStage  # noqa: E402
from _fixtures import Capture  # noqa: E402

CONSOLE = ROOT / 'annotator' / 'vision-stage.js'
OWNER = ROOT / 'annotator' / 'live_processing.py'

#: The two static spellings of one read of the cadence key on a stage object.  The dotted form
#: reads a member name; the bracket form reads data.  Both name one key.
STAGE_READ = (re.compile(r'\.' + re.escape(STAGE_CADENCE_KEY) + r'\b'),
              re.compile(r'\[\s*[\'"]' + re.escape(STAGE_CADENCE_KEY) + r'[\'"]\s*\]'))

#: The wire key of this round.  A rename of the owner constant is a wire change, and the guard
#: holds the shipped word so that rename cannot pass in silence.
SHIPPED_WIRE_KEY = 'every_n_frames'

#: The shipped text of the page read and of the producer field, with one key left out.  The page
#: shape takes the wire word, because the page holds a value; the producer shape takes the name of
#: the owner constant, because the producer writes the constant.
STAGE_READ_SHAPE = "const cadence = Number(stage['{}']) > 1"
SHIPPED_READ = "Number(stage['{}'])"
PRODUCER_CONSTANT = 'STAGE_CADENCE_KEY'
PRODUCER_SHAPE = '{}: getattr(stage, {}, 1)'
#: The plant of the planted case: the same read under another name.
MOVED_WIRE_KEY = 'frame_cadence'

#: The cadence this module sets on its one stage, and the value the payload must then carry.
CADENCE = 3

OWNER_FAILURE = ('the cadence key of a live stage dict has one home, '
                 'annotator/live_processing.py:43, and the console page must read that one key')
PAYLOAD_FAILURE = (
    'the live snapshot must carry the owner key {!r}: the producer writes that key and the console '
    'page reads it, so one edit must move the two halves together.'.format(STAGE_CADENCE_KEY))


def setUpModule():
    """No case here reaches Twitch: a Twitch source starts the live-edge probe, whose playlist
    fetch would go to the network.  The pattern and the reason are the ones of
    ``tests/test_live_processing.py:33``."""
    blocked = patch('annotator.live_processing._fetch_playlist',
                    side_effect=RuntimeError('network is not available in unit tests'))
    blocked.start()
    unittest.addModuleCleanup(blocked.stop)


def owner_text():
    """Return the source text of the module that owns the cadence key."""
    return OWNER.read_text(encoding='utf-8')


def console_text():
    """Return the source text of the page that reads the cadence key."""
    return CONSOLE.read_text(encoding='utf-8')


def key_sites(text):
    """Return ``(line number, line text)`` of every line that reads a key on a stage object.

    One entry for each matching line, in source order.  The caller names the file.
    """
    return [(number, line)
            for number, line in enumerate(text.splitlines(), start=1)
            if any(pattern.search(line) for pattern in STAGE_READ)]


def moved_sites(text, key):
    """Return ``(line number, line text)`` of every line that reads ``key`` in the shipped shape."""
    return [(number, line) for number, line in enumerate(text.splitlines(), start=1)
            if SHIPPED_READ.format(key) in line]


def shipped_reads(text, key=SHIPPED_WIRE_KEY):
    """Return ``(line number, line text)`` of every line that reads ``key`` in the shipped shape."""
    needle = SHIPPED_READ.format(key)
    return [(number, line) for number, line in enumerate(text.splitlines(), start=1)
            if needle in line]


def lines_with(text, needle):
    """Return the 1-based numbers of every line of ``text`` that holds ``needle``."""
    return [number for number, line in enumerate(text.splitlines(), start=1) if needle in line]


def read_line_numbers(text, key):
    """Return the 1-based numbers of every line that reads ``key`` in the shipped page shape."""
    return lines_with(text, SHIPPED_READ.format(key))


def describe(name, sites):
    """Return one line for each site, as ``path:line  text``, or a note that the scan found none."""
    if not sites:
        return f'  {name}: no line reads a key on a stage object'
    return '\n'.join(f'  {name}:{number}  {line.strip()}' for number, line in sites)


def infer(frame, detectors, root):
    """The one-callable stage body: a small measured answer, as the live suites use."""
    return {'pixel': int(frame[0, 0, 0])}


def live_session(cadence=CADENCE):
    """Return a processor with one real stage, the stage name, and the temporary root.

    The pattern is the one ``tests/test_live_processing.py:181`` and
    ``tests/test_live_processing.py:985`` use: a ``CallableStage`` over a temporary root, a
    ``Capture`` fake source, and no budget enforcement.  The caller starts this processor: the live
    snapshot reads the registry that ``start()`` builds, so the stages of an unstarted processor are
    empty (measured, and asserted by the payload case).
    """
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    (root / 'data').mkdir()
    (root / 'data/vod_30min_260815.mp4').touch()
    stage = CallableStage('table', infer, ['table'], root)
    stage.every_n_frames = cadence
    processor = LiveProcessor(root, stages=[stage], capture_factory=lambda _: Capture(count=2),
                              budget_enforcement=False)
    return processor, stage.name, temporary


class LiveCadenceOwnerTest(unittest.TestCase):
    """Hold the cadence key of a live stage dict to one owner in the python module."""

    def test_the_owner_constant_is_the_shipped_wire_key(self):
        """The constant holds the shipped word, so a rename of the payload key reads as a change."""
        self.assertEqual(STAGE_CADENCE_KEY, SHIPPED_WIRE_KEY,
                         OWNER_FAILURE + '.  A new value is a wire change, and the console page must '
                         'move in the same edit.')
        self.assertIn(f'STAGE_CADENCE_KEY = {SHIPPED_WIRE_KEY!r}', owner_text(),
                      'the constant must carry the shipped wire key as a literal, so this guard '
                      'reads one definition and not a third spelling.')

    def test_the_producer_builds_the_stage_dict_with_the_owner(self):
        """The producer field of the stage dict must name the owner constant."""
        field = PRODUCER_SHAPE.format(PRODUCER_CONSTANT, PRODUCER_CONSTANT)
        sites = lines_with(owner_text(), field)
        self.assertEqual(len(sites), 1,
                         'the stage dict that RallyProcessor.status builds must write the cadence '
                         'field with the owner constant STAGE_CADENCE_KEY.  One line must hold:\n'
                         f'  {field}\n'
                         'and this many lines hold it: ' + str(len(sites)))

    def test_the_page_reads_the_key_the_owner_holds(self):
        """The page must read the owner key as data, so its key is a value and not an identifier."""
        text = console_text()
        shipped = shipped_reads(text, SHIPPED_WIRE_KEY)
        self.assertEqual(len(shipped), 2,
                         'annotator/vision-stage.js must read the shipped wire key at the two read '
                         'sites of liveStageLine:\n' + describe('annotator/vision-stage.js', shipped))
        read = shipped_reads(text, STAGE_CADENCE_KEY)
        self.assertEqual(read, shipped,
                         'the page must read the key the owner holds.  The owner key is {!r}, and the '
                         'page reads it at these lines:\n{}'.format(
                             STAGE_CADENCE_KEY, describe('annotator/vision-stage.js', read)))
        self.assertEqual(len(key_sites(text)), 2,
                         'the two reads of the cadence key on one stage object must both be found:\n'
                         + describe('annotator/vision-stage.js', key_sites(text)))

    def test_a_stage_key_under_another_name_is_reported(self):
        """A planted read of the moved key is an offender, named by file and line."""
        text = console_text()
        shipped = STAGE_READ_SHAPE.format(SHIPPED_WIRE_KEY)
        self.assertIn(shipped, text,
                      f'annotator/vision-stage.js does not hold the shipped line {shipped}')
        planted = text.replace(shipped, STAGE_READ_SHAPE.format(MOVED_WIRE_KEY))
        self.assertNotEqual(planted, text, 'the plant of the moved key must change the page text')
        # The plant replaced one line.  The read of the moved key on that line is the offender.
        target = read_line_numbers(text, SHIPPED_WIRE_KEY)[0]
        sites = moved_sites(planted, MOVED_WIRE_KEY)
        self.assertEqual(len(sites), 1,
                         'one read of the moved key must be reported as the offender:\n'
                         + describe('annotator/vision-stage.js', sites))
        number, line = sites[0]
        self.assertEqual(number, target,
                         'the report must name the line that reads the moved key.  The offender is '
                         'the line the plant replaced.')
        self.assertEqual(line.strip(), STAGE_READ_SHAPE.format(MOVED_WIRE_KEY),
                         'the report must carry the text of the offender line, so a reader can '
                         'find the line without a second search')

    def test_an_empty_scan_cannot_pass(self):
        """Anti-vacuity: the shipped page must hold a read of the owner key.

        A detector that matches no line would pass the planted case above for the wrong reason.
        """
        text = console_text()
        read = shipped_reads(text, STAGE_CADENCE_KEY)
        self.assertEqual(len(key_sites(text)), len(read),
                         'the scan of annotator/vision-stage.js must find every read of the owner '
                         'key.  An empty scan must not pass this module, and a scan that misses one '
                         'of the two reads of liveStageLine must not pass it either.')
        self.assertGreaterEqual(len(read), 1,
                                'the shipped page must read the owner key at one line at least:\n'
                                + describe('annotator/vision-stage.js', read))
        self.assertEqual(read[0][0], read_line_numbers(text, SHIPPED_WIRE_KEY)[0],
                         'the first read of the owner key must be the shipped read line:\n'
                         + describe('annotator/vision-stage.js', read))

    def test_the_live_snapshot_carries_the_owner_key(self):
        """A real processor with one stage serves that stage under the owner key."""
        processor, name, temporary = live_session()
        self.addCleanup(processor.stop)
        self.addCleanup(temporary.cleanup)
        self.assertEqual([stage['name'] for stage in processor.status()['stages']], [],
                         'the stages of an unstarted processor are empty: the snapshot reads the '
                         'registry that start() builds')
        processor.start(dict(kind='dataset', dataset='vod30'))
        deadline = time.monotonic() + 5
        stages = processor.status()['stages']
        while not stages and time.monotonic() < deadline:
            time.sleep(.002)
            stages = processor.status()['stages']
        self.assertEqual([stage['name'] for stage in stages], [name], PAYLOAD_FAILURE)
        stage = stages[0]
        self.assertIn(STAGE_CADENCE_KEY, stage,
                      PAYLOAD_FAILURE + '  The payload carries: ' + repr(sorted(stage)))
        self.assertEqual(stage[STAGE_CADENCE_KEY], CADENCE, PAYLOAD_FAILURE)


if __name__ == '__main__':
    unittest.main()
