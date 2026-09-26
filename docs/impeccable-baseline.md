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
- **After `git merge main` (`90438ac`) and the fixture fix (`ede4052`), at `541fac5`:**
  unittest **944 tests, OK (skipped=13)**; `test_ops.js` **35 / 35 pass**;
  `test_app_timeline.js` **65 passed, 0 failed**. The 5 new skips are
  `test_db.Database` ("POOL_DATABASE_URL is not set"), which arrived with main; the
  other 8 are the ones above. Every polish commit is held to these counts or higher.
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
- Process: the transient systemd user unit `impeccable-fixture-8137`, started with
  `systemd-run --user --collect` (DSH kills `setsid` children when a session ends; a
  unit survives). pid in `out/impeccable/fixture.pid`, log in `out/impeccable/fixture.log`.
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
5. Starts the wrapper on `:8137` as `systemd-run --user --collect --unit=impeccable-fixture-8137`
   (step 2 stops that unit first), then waits for HTTP 200.
6. Places `yolov8n.pt` in the fixture root: temp copy, md5 check, `mv -n`.
7. Verifies:
   - served `/app.js` sha256 equals the worktree's `annotator/app.js`;
   - the five production md5s are the same before and after the reset;
   - the scratch tree has no symlinks;
   - the fixture's `events.json` is byte-identical to the snapshot's.

Run it: `bash /home/operator/projects/pool-impeccable/out/impeccable/reset_fixture.sh`.
The last line prints the URL, pid, `app.js` sha256 and the `events.json` md5 prefix,
and a success line is appended to `out/impeccable/reset.log`.

## Saved Twitch channels in the fixture (fixed in `ede4052`)

Round 0 could not start a Twitch channel saved in the fixture ("Saved Twitch channel is
unavailable"): the live processor was rooted at `ROOT` and read saved channels from
`ROOT/out/corner-pocket/state.json`, while the UI saves them into the fixture's own
state. Commit `ede4052` keeps the processor at `ROOT`, so dataset media still resolves,
and looks a `{kind:'twitch'}` source up in the fixture's state. Checked on a throwaway
fixture on `:8141` (`out/impeccable/verify_fixture_channel.sh`): the vod30 replay
reaches `running`, and a channel saved through `#source-form` resolves; its start then
fails only at Twitch ("Twitch channel is offline or has no public playable stream").

## Screenshots

Script `out/impeccable/shoot_baseline.sh` (untracked, read-only: it opens tabs and
panels and never POSTs), run against a freshly reset fixture. Per language and
viewport (1280×900 and 390×844, EN and 中): Floor, Setup, Matches, Players, the
new-player modal, Status, Vision settled, Vision with the first cue selected, the Vision
source panel, the 390 px bottom-sheet cues and inspector, and Floor and Vision in the
light theme. A full-page capture is added whenever the page is taller than the viewport.

| Set | Files | Horizontal overflow | Page errors | Console lines | Web fonts loaded |
|---|---|---|---|---|---|
| Online, `out/impeccable/baseline/` | 66 PNG (48 viewport + 18 full-page) | 0 of 48 | 0 | 0 | Barlow, DM Mono, Noto Sans SC, Noto Serif SC, Zilla Slab |
| Offline, `out/impeccable/baseline/offline/` (`OFFLINE=1`: `fonts.googleapis.com` and `fonts.gstatic.com` aborted) | 66 PNG (48 + 18) | 0 of 48 | 0 | 0 | none |

- Overflow is `scrollWidth > clientWidth` on the document, recorded per viewport shot in
  `checks.tsv`. Page errors and console lines are in `page-errors.txt` and `console.txt`.
- Online, all 8 Google Fonts stylesheet requests (one per page load) and 236 font-file
  requests returned 200 (`font-requests.txt`). Offline, the 8 stylesheet requests were
  aborted, no font file was requested, and no web font loaded.
- Offline, the stacks fall back to fontconfig matches: `--body` (Barlow, …, Arial) to
  Liberation Sans, `--display` (Zilla Slab, …, Georgia) to DejaVu Serif, `--mono`
  (DM Mono, …, monospace) to DejaVu Sans Mono. This is what a club machine without
  internet renders today; the typeset step self-hosts the fonts.
- The Vision facts line settled (identical across 4 reads 1.5 s apart) in every shot;
  `facts.tsv` holds the settled text.
