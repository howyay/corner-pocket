"""The single home of the SAM3 ball admission gate.

The gate decides which SAM3 detections count as balls.  Three bars decide: one
score cut, one area window and one radius band.  Nine modules applied the gate
before this module existed, and each module spelled the score and area numbers
itself; four of those modules also spelled the radius band itself.  Two area caps
disagreed, and no file in the repository said why.  This module is now the only
definition site.

Nothing here imports cv2, torch or SAM3.  A module that needs a gate value can
import it without loading a detector.

The score cut
    :data:`SAM3_BALL_MIN_SCORE` is the score cut.  SAM3 returns one confidence
    score per instance (``src/pipeline.py:157``).  An instance below the cut is
    not a ball.  The gate drops it and never measures it.  All nine gate sites
    used this same cut, so this value has one meaning and one home.

The lower area cap
    :data:`SAM3_BALL_MIN_AREA_PX` is the lower cap of the area window.  The area
    is ``float(mask.sum())``: the number of pixels the instance mask covers
    (``src/pipeline.py:165``, ``src/scan_events.py:140``).  A mask below this cap
    is noise, not a ball.  The unit is a pixel of the frame that SAM3 saw, not a
    millimetre of the table.

The upper area cap, and the disagreement
    :data:`SAM3_BALL_MAX_AREA_PX` is 9000.  :data:`POC_PIPELINE_BALL_MAX_AREA_PX`
    is 6000.  Both values gate the same measurement: the mask of one SAM3
    instance on one whole video frame, directly after
    ``set_text_prompt("billiard ball")``.  The two values therefore contradict
    each other.

    Measurements that rule out the friendly explanation ("two frames, two
    caps"):

    * SAM3 sees the source frame, not the canonical frame.  ``extract_frame``
      reads one frame and never resizes it (``src/pipeline.py:55-58``).  The
      caller passes that same frame to SAM3 (``src/pipeline.py:253``,
      ``src/pipeline.py:267-268``).  The warp to the canonical 1270x2540 mm
      frame happens later and uses a different array (``src/pipeline.py:207``).
      ``src/scan_events.py:121-126`` and ``src/sam3_ball_cache.py:152-154`` read
      their frames the same way, with no resize.
    * That source frame is the 1280x720 VOD tier (``src/tiny_ball_net.py:57``,
      ``src/motion_scan.py:69``, ``src/dense_queue.py:69``).  Both caps are
      therefore in 1280x720 pixels.
    * Both caps sit in the same statement family of the same function.  The
      score cut and the area window of one instance are neighbours
      (``src/pipeline.py:162-166``).
    * No comment, docstring or test in the repository explains the 6000.
      ``grep -rn "6000" src/`` returns this one gate line plus two unrelated
      uses: a pocket-hole window (``src/calibrate.py:41``) and a progress print
      (``src/motion_scan.py:711``).

    Ruling: one stage, two values, no measured reason.  These two values
    contradict each other.  This round does not change behaviour.  No value
    changes.  ``src/pipeline.py`` (and ``src/frame_inference.py:201``, which
    imports its filter) reads the 6000.  The other five area sites read the
    9000.  A later round must measure which cap is right before it unifies them.

The classical cap, a different decision
    :data:`CLASSICAL_BALL_MAX_AREA_960X540_PX` is 4200.  It is *not* part of the
    SAM3 gate.  It caps the classical colour-blob detector
    (``src/ball_detect.py:28-34``) on a 960x540 resize
    (``src/scan_events.py:75``, inside ``classical_scan`` at
    ``src/scan_events.py:61``).  That detector reports a contour area, not a
    SAM3 mask area, and its lower cap is 14.0 px, not 60.  It therefore keeps
    its own name here.

The radius band, the third bar
    :data:`SAM3_BALL_MIN_RADIUS_PX` and :data:`SAM3_BALL_MAX_RADIUS_PX` are the
    radius band.  The radius is the equivalent radius of one instance mask,
    ``ball_center(mask)``, in pixels of the same source frame
    (``src/pipeline.py:168``, ``src/sam3_ball_cache.py:174``).  Four sites
    spelled the pair ``4.0, 60.0`` themselves; these are the line numbers as
    they were before this round: ``src/pipeline.py:177``,
    ``src/scan_events.py:147``, ``src/sam3_ball_cache.py:52`` and
    ``src/ball_fp_audit.py:103``.  All four applied the same pair to the same
    measurement, so this bar has one meaning.  Only its home was missing.

    The radius 60 is *not* the area 60.  A length in pixels and a count of
    pixels are different quantities, so the two keep two names and no caller
    may pass one for the other.
"""

__all__ = [
    "CLASSICAL_BALL_MAX_AREA_960X540_PX",
    "POC_PIPELINE_BALL_MAX_AREA_PX",
    "SAM3_BALL_MAX_AREA_PX",
    "SAM3_BALL_MAX_RADIUS_PX",
    "SAM3_BALL_MIN_AREA_PX",
    "SAM3_BALL_MIN_RADIUS_PX",
    "SAM3_BALL_MIN_SCORE",
]

#: The score cut of the SAM3 gate: an instance below this score is not a ball.
#: Readers: src/ball_census.py, src/ball_fp_audit.py, src/collect2.py,
#: src/fast_ball_labels.py, src/pipeline.py, src/recut_crops.py,
#: src/sam3_ball_cache.py, src/scan_events.py, src/tiny_ball_net.py.
SAM3_BALL_MIN_SCORE = 0.62

#: The lower cap of the SAM3 gate area window, in pixels of the source frame.
SAM3_BALL_MIN_AREA_PX = 60

#: The upper cap of the SAM3 gate area window, in pixels of the source frame.
#: Readers: src/ball_fp_audit.py, src/collect2.py, src/recut_crops.py,
#: src/sam3_ball_cache.py, src/scan_events.py.  See the module docstring for the
#: disagreement with :data:`POC_PIPELINE_BALL_MAX_AREA_PX`.
SAM3_BALL_MAX_AREA_PX = 9000

#: The upper cap that src/pipeline.py applies instead of
#: :data:`SAM3_BALL_MAX_AREA_PX`.  Same stage, same measurement, different value,
#: and the repository holds no reason for the difference.  Both values are kept
#: so that behaviour does not change in this round.
POC_PIPELINE_BALL_MAX_AREA_PX = 6000

#: The upper cap of the classical colour-blob detector on a 960x540 frame.
#: A different detector and a different measurement; see the module docstring.
CLASSICAL_BALL_MAX_AREA_960X540_PX = 4200.0

#: The lower cap of the radius band, in pixels of the source frame.  ``r`` is
#: the equivalent radius of the instance mask, ``ball_center(mask)``.
#: Readers: src/ball_fp_audit.py, src/pipeline.py, src/sam3_ball_cache.py,
#: src/scan_events.py.
SAM3_BALL_MIN_RADIUS_PX = 4.0

#: The upper cap of the radius band, in pixels of the source frame.  This 60 is
#: a length, not the pixel count :data:`SAM3_BALL_MIN_AREA_PX` holds.
SAM3_BALL_MAX_RADIUS_PX = 60.0
