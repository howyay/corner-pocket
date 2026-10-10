/* The one owner of the console duration text: the H:MM:SS form (`0:00:00`).
 *
 * Three page scripts used to hold one copy each (annotator/app.js:2035,
 * annotator/ops.js:104, annotator/vision-stage.js:930).  The three copies
 * disagreed on seven of the nineteen values the Lead's grid measures.  This
 * file replaces all three copies (the three seams now read
 * `window.Duration.hms` at annotator/app.js:2036, annotator/ops.js:104 and
 * annotator/vision-stage.js:930).
 *
 * THE RULE
 * Clamp the value at zero.  Truncate it toward zero.  Then format it as H:MM:SS.
 * No value is negative and nothing rounds up.
 *
 * WHY TRUNCATION WINS - MEASURED, NOT A PREFERENCE
 * 1. Every duration on disk is a whole number of seconds.  Under out/ the keys
 *    length_s (21 values), start_s (28 values) and end_s (20 values) hold
 *    integers only.  annotator/live_processing.py:101 builds at_s from the
 *    `\d+` anchors at :83, so at_s is a non-negative integer as well.
 * 2. The one fractional input is a frame time.  annotator/vision-stage.js calls
 *    this rule with `start_s + frame.t`, and frame.t is a float
 *    (annotator/unified_server.py:1788 `timestamp_seconds=value / fps`).
 *    Truncation names the second that CONTAINS the frame: 59.6 belongs to the
 *    second that starts at 59.  Rounding names the second that starts at 60, and
 *    that second holds no part of the frame.  At 30 fps this changes half of all
 *    frames.
 * 3. A value that is not a number of seconds prints `0:00:00`.  That covers NaN,
 *    a missing value, a non-numeric string and +-Infinity.  One invalid value
 *    must not print `Infinity:NaN:NaN` while another prints zero.
 *    annotator/app.js:111 guards its own time formatter the same way.
 *
 * THE SHOT CLOCK IS NOT THIS RULE
 * annotator/ops.js `clockText()` counts the time LEFT and rounds up on purpose.
 * That is a different question, and it keeps its own function.
 *
 * NO GLOBAL NAME
 * A classic script shares one global lexical scope with every other classic
 * script on the page, so a top-level `const` in this file can collide with the
 * same name in another file.  Measured in chromium: a first version of this file
 * declared a top-level `const api`, and annotator/clock-sync.js then failed to
 * load at all with `Uncaught SyntaxError: Identifier 'api' has already been
 * declared`.  The function below keeps every name inside this file.
 *
 * LOAD ORDER
 * Read `window.Duration` at call time, as annotator/clock-sync.js reads
 * `window.OpsClock`.  The two pages still load this file first, so the seam is
 * always there: annotator/ops.html and annotator/app.html carry it as their
 * first `defer` script.
 */
(() => {
  'use strict';

  // The seconds-per-hour divisor.  This file is the only file under annotator/
  // that may hold this number; tests/test_ops.js fails and names the file and the
  // line when a second copy appears.
  const SECONDS_PER_HOUR = 3600;
  const SECONDS_PER_MINUTE = 60;

  function hms(value) {
    const seconds = Number(value);
    // An invalid value and a negative value both print 0:00:00.  The editor reads a
    // duration that never runs backwards, so a negative one is a bad reading.
    const whole = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
    const hours = Math.floor(whole / SECONDS_PER_HOUR);
    const minutes = String(Math.floor(whole % SECONDS_PER_HOUR / SECONDS_PER_MINUTE)).padStart(2, '0');
    const rest = String(whole % SECONDS_PER_MINUTE).padStart(2, '0');
    return `${hours}:${minutes}:${rest}`;
  }

  const api = {
    hms: hms
  };

  if (typeof module === 'object' && module.exports) module.exports = api;
  if (typeof window !== 'undefined' && window) window.Duration = api;
})();
