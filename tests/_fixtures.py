"""The three fixture families that two pairs of test modules held twice.

Round 90 measured two rows of this tree, and each row was one body under two
names or two homes.  This module is the one home of both rows.

1. **The operations fixture.**  ``tests/test_console_service_bounds.py`` and
   ``tests/test_ops_bounds.py`` held three methods with the same body each,
   byte for byte: ``setUp`` (body key ``c701e96a088c``), ``layer``
   (``1266ab335704``) and ``call`` (``1680d410a170``).  Both modules build one
   operations layer over a temporary directory, so both need the same three
   methods, and a change to one copy changed one module alone.  The two classes
   read ``OpsLayerFixture`` below now.  The class owns no case of its own: it
   is a mixin, and each module keeps its own cases, its own frozen numbers and
   its own ``teams`` method.

2. **The live harness.**  ``tests/test_live_processing.py`` held ``wait_for``
   three times, and ``tests/test_live_processing_stages.py`` held the body of
   the third one again at its own ``wait_for``, so the body stood twice in the
   tree under two different wording of the same argument.  The two copies that
   stated no deadline wrote ``time.monotonic() + 3``, and the two copies that
   took a ``timeout`` wrote ``timeout=5``.  One method with a ``timeout``
   argument answers all four callers, and its default is the wider of the two
   fixed deadlines, so no case of the four reads a tighter deadline than the
   method it read before.  ``LiveHarness`` below is the home of that method.

3. **The capture fake.**  The two live modules held one ``Capture`` body twice.
   ``tests/test_live_processing.py`` held the body with the default
   ``fps=200`` and a working frame of 16x16; the stages module held it with
   ``fps=30``, a working frame of 32x32, and a ``get`` that answers the media
   position of the reader on top of it.  The two ``get`` bodies are two
   questions (``63c4a16f8e97`` against ``d37960677dbb``), so they stay two
   methods of one class.  The class below takes the frame rate, the size of the
   working frame and the rest as arguments, and each module states the defaults
   of its own fixtures at the call site.  The difference between the two
   original classes is therefore readable in one screen, and no longer hidden
   in two copies that drifted apart.

   * ``tests/test_live_processing.py`` keeps a fake source of 200 frames per
     second, so its default is ``fps=200`` and its working frame is 16x16.
   * ``tests/test_live_processing_stages.py`` keeps a source of 30 frames per
     second - the derived frame budget case reads that rate - and its working
     frame is 32x32, so its default is ``fps=30`` and ``shape=(32, 32, 3)``.

4. **The two live readers.**  ``infer`` and ``status_finished`` stood once
   each, at the head of ``tests/test_live_processing.py``.  Only one caller
   used them, so this module is not the home of a duplicate: the two bodies do
   not move.  They join this home when a second module needs the same answer,
   and not before.

The guard of rows 1 to 3 is ``tests/test_console_service_bounds.py``.  Its two
cases read the bodies of every ``tests/*.py`` file and report a second home of
one of the fingerprints above, with the file and the line.  A copy under
another name is reported too: the walk reads the body and not the name.  The
keys were measured with ``tests/_shipped.py``'s ``body_fingerprint``, which
drops the docstring of a function, unparses the statements that remain and
hashes them, so the docstrings of the copies below do not move a key.

The name starts with an underscore on purpose.  Discovery reads ``test_*.py``
files only, so this module is a helper and not a suite.  The modules read it by
its bare name, the way ``tests/test_one_shipped_tree.py`` reads ``_shipped``.

Run: ``./scripts/pool-test.sh python test_console_service_bounds``
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import time

import cv2
import numpy as np

from annotator.operations import Operations

#: The module name discovery must never read as a suite, and the name a fault
#: message of the guard uses.
SELF = Path(__file__).stem


class OpsLayerFixture:
    """One operations layer over a temporary directory, for the case that needs it.

    The caller adds the class before ``unittest.TestCase`` in its own bases, so
    the three methods below answer on the instance and no module states them
    again.  ``setUp`` and ``layer`` are two methods and not one because a case
    asks for a layer first and then posts to it, and both calls read the same
    ``self.ops``.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ops = None

    def layer(self, name):
        """Open one operations layer over its own directory and keep it for the case."""
        self.ops = Operations(self.root / name)
        return self.ops

    def call(self, action, **fields):
        """One request on the open layer, at the revision the layer reports now."""
        return self.ops.post(dict(action=action, revision=self.ops.get()['revision'], **fields))


class LiveHarness:
    """The two helpers every live-processing suite of this tree waits with.

    ``processor``-owning classes were the callers before round 90: three
    ``wait_for`` methods of ``tests/test_live_processing.py`` and one of
    ``tests/test_live_processing_stages.py``.  One method answers all four, and
    its default is the wider of the two fixed deadlines the copies wrote.
    """

    def wait_for(self, processor, predicate, timeout=5):
        """The first status that satisfies ``predicate``, or a failure that names the last one.

        The two methods of ``tests/test_live_processing.py`` that stated ``3`` by
        hand read this default, and so do the two that stated ``5``: five seconds
        is the longer of the two fixed deadlines and no case of the four reads a
        timeout it does not pass.  The deadline of the long cases is the
        ``timeout`` they pass.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = processor.status()
            if predicate(status):
                return status
            time.sleep(.002)
        self.fail('Timed out: ' + repr(processor.status()))


class Capture:
    """A fake video source that answers ``count`` frames at a chosen rate.

    ``tests/test_live_processing.py`` builds it as ``fps=200`` over a 16x16
    working frame; ``tests/test_live_processing_stages.py`` builds it as
    ``fps=30`` over a 32x32 frame.  Those two defaults are the two defaults of
    the two classes this one replaces, and each caller states its own.

    ``shape`` is the working frame the module expects to be published.  The
    first copy answered 16x16 pixels of one colour channel and the second
    answered 32x32, so the size is a fixture of the caller and not of the fake.
    """

    def __init__(self, count=5, fps=200, opened=True, shape=(16, 16, 3)):
        self.count, self.fps, self.opened = count, fps, opened
        self.shape = shape
        self.index = 0
        self.released = False

    def isOpened(self):
        return self.opened

    def get(self, prop):
        """The frame rate of this fake source, and the frame index for any other property."""
        return self.fps if prop == cv2.CAP_PROP_FPS else self.index

    def read(self):
        if self.index >= self.count:
            return False, None
        self.index += 1
        return True, np.full(self.shape, self.index, dtype=np.uint8)

    def release(self):
        self.released = True


class PositionCapture(Capture):
    """The same fake source, with a real media position, like a decoder over a file.

    Its two copies differed more than the two ``Capture`` copies did: the one in
    ``tests/test_live_processing_stages.py`` read the frame itself instead of
    calling ``Capture.read``, so that it could place the frame at ``self.start``
    and answer ``CAP_PROP_POS_FRAMES``.  The frame body of the two was one body,
    so the subclass below keeps the ``get`` of the stages copy and no ``read``.
    """

    def __init__(self, count=3, fps=30, start=0, shape=(32, 32, 3)):
        super().__init__(count=count, fps=fps, shape=shape)
        self.start = start

    def get(self, prop):
        """The position of the *next* frame, and the answers of the fake source for the rest."""
        if prop == cv2.CAP_PROP_POS_FRAMES:
            return self.start + self.index
        return super().get(prop)
