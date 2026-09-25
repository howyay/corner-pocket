# Impeccable polish — baseline (Phase 0)

What the app measures as on branch `impeccable-polish` before any Impeccable command
is applied. Every later round is compared against these numbers and screenshots.
Worktree: `/home/operator/projects/pool-impeccable`; the app code under test is
`annotator/` at worktree base `da6d5ac` (the polish has changed nothing yet).

## Suites (run from the worktree root, 2026-09-25)

| Command | Result |
|---|---|
| `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | **924 tests, OK (skipped=8)**, 43 s |
| `node --test tests/test_ops.js` | **23 / 23 pass**, 0 fail |
| `node tests/test_app_timeline.js` | **60 passed, 0 failed** |

- The 8 skips depend on the environment and are expected: 5 × `test_ball_fp_audit.FrozenEvidenceTest`
  ("the audit has not been run in this checkout"), 2 × `test_body_calibration.RealFootageCalibrationTest`
  (needs `POOL_BODY_CALIBRATION=1`), 1 × `test_queue_decision.QueueArtifactShape`
  ("the queue is not empty in this tree"; the snapshot's `events.json` holds 4 candidates).
- The first unittest run gave 2 failures and 9 errors (`test_eval_table_detect` ×8,
  `test_calib_mapping_audit` ×2, `test_motion_scan` ×1). All 11 had one cause: the
  worktree lacked the read-only input `out/fixed_corners.json`. After it was linked in,
  the full rerun was green. They were a gap in how the worktree was set up; the code
  was not at fault.
- Logs (untracked): `out/impeccable/suites/{unittest,node-test-ops,app-timeline}.log`,
  and `unittest.run1-missing-fixed_corners.log` for the first run.
- The five production files (main checkout: `out/corner-pocket/state.json`,
  `out/pid_seed.json`, `out/scan30/annotations.json`, `out/identity/clusters.json`,
  `out/scan30/events.json`) had the same md5 before and after the suites.

## Worktree data layout

`data/` and `out/` are gitignored, and only the main checkout has them. The worktree
has its own real directories; no symlink anywhere points at a directory.

- `data/vod_30min_260815.mp4` and `data/vod_highlight.mp4` are `cp --reflink=always`
  copies (btrfs CoW; 690,007,244 + 286,360,173 bytes; own inodes, no hardlink). They
  are real files because the live processor resolves `data/` through `realpath` and
  would refuse a symlink with "Allowlisted dataset media is unavailable".
  `data/sam3.safetensors` is the same symlink main has.
- `.venv` is a symlink to main's venv. `git status` shows it as `?? .venv` because the
  `.venv/` ignore rule does not match a symlink. Never stage it.
- The read inputs point at a frozen snapshot, `out/impeccable/inputs-r0/`: a reflink
  copy of main's inputs taken 2026-09-25 05:28 PDT (main at `f800c4f`). It holds 1092
  files, with a md5 manifest in `out/impeccable/inputs-r0.md5`; `scan30/events.json` is
  `77777777777777777777777777777777…` (the 4-candidate queue). Every round reads the same data even while
  other workers regenerate main's `out/`.
  - `out/{scan30,scan_highlight,unlabeled_crops,unlabeled_crops2,vod30_event_crops}` are
    real directories of per-file links (`cp -rs`).
  - `out/{pid2_tracklets,calib_vod30,events_actors,pid_anchors_vod30,calib_vod30_segments,calib_mapping_audit,corners_30min_v2,fixed_corners}.json`
    and `out/tiny_ball_probe/{960x540-scratch.pt,report_960x540.json}` are file links.
  - `out/identity/clusters.json` is a real copy, because the live person stage may write it.
- Round 0 read main's `out/` directly (same content: nothing under main's inputs
  changed between the fixture start at 05:13 and the snapshot). The reset script
  switches the links to the snapshot.

## Browser fixture

- URL: **`http://127.0.0.1:8137/`** (loopback only). `/` serves `ops.html`, and
  `/ops.html` 308-redirects to `/`, as designed.
- Wrapper: `out/impeccable/serve_fixture.py` (untracked). It runs the tracked
  `tests/serve_workbench_fixture.py` unchanged except for the port. That file hardcodes
  `:8131`, the port main's own fixture uses; the wrapper asserts that `8131` appears
  exactly twice before replacing it. `__file__` is the worktree copy, so `ROOT` is the
  worktree and the scratch tree is `pool-impeccable/out/ui-browser-fixture`.
- Process: started with `setsid nohup … &`. pid in `out/impeccable/fixture.pid`, log in
  `out/impeccable/fixture.log`.
- Checks run at start: served `/app.js` sha256 `77777777777777777777777777777777…294364e` equals the worktree's
  `annotator/app.js` (and main's); `ops.js`, `ops.css`, `app.css`, `vision-stage.js` and
  `ops.html` (served at `/`) also match; the scratch tree has 1086 real files and 0
  symlinks; the five production md5s, sizes and mtimes did not change.
- Operations state starts empty (an empty club at the registration stage), because the
  tracked fixture never copies `out/corner-pocket/state.json`.
- `yolov8n.pt`: the tracked fixture does not place the person-detector weights in its
  root, so Vision's default inference (`app.js` detectors `{table, person}`) failed with
  "Local yolov8n.pt is missing; downloads are disabled". During round 0 the tracked
  `yolov8n.pt` (md5 `77777777777777777777777777777777…`) was moved in atomically at **2026-09-25T12:30:18.717Z**
  (`out/impeccable/yolov8n-placed.txt`). An inference failure before that time is a
  fixture gap and does not count against the product. The reset script places the file
  on every later round.

## Reset procedure (before every rating round)

Script: `out/impeccable/reset_fixture.sh` (untracked; `PORT` defaults to 8137). It runs
these steps in order and aborts on any failed check:

1. Verifies that `inputs-r0/` still matches its md5 manifest.
2. Stops the fixture: `kill $(cat out/impeccable/fixture.pid)`, then waits for the port to free.
3. Removes the scratch tree `pool-impeccable/out/ui-browser-fixture`, after confirming
   the path resolves inside the worktree.
4. Re-points the worktree inputs at `inputs-r0/`, copies `identity/clusters.json`
   (deleting any link there first, so the copy can never write through), and checks
   that every input link resolves into the snapshot and that no directory symlink exists.
5. Starts the wrapper detached on `:8137` with `setsid nohup`, then waits for HTTP 200.
6. Places `yolov8n.pt` in the fixture root: temp copy, md5 check, `mv -n`.
7. Verifies:
   - served `/app.js` sha256 equals the worktree's `annotator/app.js`;
   - the five production md5s are the same before and after the reset;
   - the scratch tree has no symlinks;
   - the fixture's `events.json` is byte-identical to the snapshot's.

Run it: `bash /home/operator/projects/pool-impeccable/out/impeccable/reset_fixture.sh`.
The last line prints the URL, pid, `app.js` sha256 and the `events.json` md5 prefix,
and a success line is appended to `out/impeccable/reset.log`.

## Known fixture limitation (not a product defect)

A Twitch channel saved in the fixture cannot be started. The attempt fails with "Saved
Twitch channel is unavailable" because the tracked fixture points the live processor
at `ROOT` (`serve_workbench_fixture.py:62`), which reads saved channels from
`ROOT/out/corner-pocket/state.json`, while the UI saves channels into the fixture's own
state. In production, the processor and the saved channels share one root. The fix is
scheduled as a separate commit to `tests/serve_workbench_fixture.py` after round 0.

## Screenshots

Pending. They are taken after round 0, from a freshly reset fixture:
1280×900 and 390×844, EN and 中, into `out/impeccable/baseline/`.
