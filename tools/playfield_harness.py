"""How the playfield audit tools open a recording and drive the served pipeline.

Both audit tools measure the same thing on historical VODs: the table stage that the
console falls back to when a dataset has no saved calibration.  Each tool carried its own
copy of the same five steps - open the container, take the frame at a fraction of the
recording, build one stage per event, build that frame's context, name the cadence - and
the copies drifted.  Each spelled the measurement cadence and the frame-rate fallback
again, so a change to the served pipeline moved the live path and left the audits
measuring an older configuration while their own notes still said "measure, like live".

This module owns that reading.  It asks the pipeline for the cadence
(:data:`annotator.pipeline_stages.TABLE_MEASURE_EVERY_N`) instead of restating it, so a
change there moves the audits with the served path, and
``tests/test_playfield_harness.py`` holds both facts: one owner for the cadence, and one
place in ``tools`` that spells it.

A stage carries its measurement, so one stage per recording is required: a reused stage
reported the same quad for ten picks, and an earlier run claimed 42 passes where the
measured number is 24.  :func:`new_stage` builds a fresh stage, and the callers call it
inside their recording loop rather than hoisting it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from annotator.pipeline_stages import (TABLE_MEASURE_EVERY_N, StageContext,
                                       TableStage)

#: The frame rate a container that does not report one is read at.  Written once: a
#: second copy is a second answer to "what rate was this measured at".
FPS_FALLBACK = 30.0


class Recording:
    """A VOD opened for measurement: its length, its rate, and its frames at a fraction.

    A container that cannot be opened raises ``OSError`` instead of reporting an empty
    recording: a recording that was not read is not evidence that no table is there.
    """

    def __init__(self, path):
        import cv2
        self.path = Path(path)
        self._cv2 = cv2
        self.capture = cv2.VideoCapture(str(self.path))
        if not self.capture.isOpened():
            raise OSError('cannot open %s: no frame can be read from it' % self.path)
        # A frame count of 0 is a container that does not report one; the picks then fall on
        # frame 0, which is still a real frame of a real recording.
        self.frame_count = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.fps = float(self.capture.get(cv2.CAP_PROP_FPS) or 0) or FPS_FALLBACK

    def frame_at(self, fraction):
        """The frame at ``fraction`` of the recording and its index; frame None if unreadable."""
        index = int(self.frame_count * fraction)
        self.capture.set(self._cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self.capture.read()
        return index, (frame if ok else None)

    def close(self):
        self.capture.release()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False


def new_stage(root, dataset=None):
    """One table stage for one recording, on the cadence the served pipeline measures with.

    ``dataset`` stays None for an audit: the historical ``tw-*`` events have no saved
    calibration, so the stage measures from pixels the way the console does for a live
    stream with no artifact.
    """
    return TableStage(root, dataset=dataset, measure_every_n=TABLE_MEASURE_EVERY_N)


def frame_context(index, fps):
    """The context of a frame measured from a recording: no earlier results, its own position."""
    return StageContext({}, frame_number=index, frame_index=index, time_s=index / fps)
