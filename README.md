# Corner Pocket

Corner Pocket is a workbench for a pool hall. It has two halves:

- **Operations**: players, events and entrants, match draws, table assignment,
  a shot clock, and each regular's profile. It runs in the browser.
- **Vision**: analysis of video from one fixed camera over a pool table. It
  calibrates the table, projects everything onto a top-down 2D table in
  millimetres, detects balls, shots and pots, and attributes each shot to the
  player who made it. Detector output stays a candidate until a person reviews
  it.

It is a working research tool, not a finished product. The measured accuracy
of each part, and what is still unvalidated, is in `docs/`.

## Architecture

- `annotator/unified_server.py`: one stdlib HTTP server. It serves the web app
  (`ops.html`, `app.html`) and a JSON API.
- `annotator/*.js`, `*.css`: the browser UI, plain JavaScript with no build
  step.
- `src/`: the vision pipeline: table detection and calibration, ball
  detection, shot and pot events, and player identity (YOLOv8n person
  detection, OSNet body re-identification, InsightFace faces).
- `annotator/live_processing.py`: runs the same pipeline stages on a live
  video source, one decoded frame at a time.
- State lives in JSON files under `out/` (ignored by git); an optional Postgres
  store is in `src/db.py`.

## Setup

You need Python 3.12 or newer (3.14 is tested), Node.js 20 or newer for the
UI tests, and FFmpeg if you want event clips.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_weights.py
```

- `requirements.txt` explains how to pick a CPU-only or ROCm build of torch.
- `scripts/fetch_weights.py` downloads the two model files the code expects,
  `yolov8n.pt` and `src/reid/weights/osnet_x0_25_msmt17.pth`, and checks their
  pinned SHA-256. Re-running it is safe; it skips files that are already
  correct.
- InsightFace downloads its `buffalo_l` models into `~/.insightface` the first
  time face identification runs.
- **SAM 3 is optional.** Only the SAM-based ball detector and labelling tools
  use it. To use them, install the `sam3` package from a clone of
  <https://github.com/facebookresearch/sam3>, request access to the gated
  checkpoint at <https://huggingface.co/facebook/sam3>, and save it as
  `data/sam3.safetensors`.

**Pulling into an existing checkout.** Model weights used to be committed; they
are now ignored by git. When you pull the commit that untracked them, git
deletes `yolov8n.pt` and `src/reid/weights/osnet_x0_25_msmt17.pth` from your
working tree. Run `.venv/bin/python scripts/fetch_weights.py` to get them back.

## Running

From the repository root:

```sh
.venv/bin/python annotator/unified_server.py --port 8130
```

Open <http://127.0.0.1:8130/>. The server listens on `127.0.0.1` by default
and has **no built-in authentication**. Do not expose it to a network without
an authenticating reverse proxy in front of it (see [SECURITY.md](SECURITY.md)).

Two fixtures run the same UI on scratch copies, so trying things out never
changes real state:

```sh
# the operations app with an empty club; its state is deleted on exit
PYTHONPATH=. .venv/bin/python tests/serve_operations_fixture.py   # :8150
# the review workbench on a copy of your own review data: it needs video in
# data/ and scan output in out/, which a fresh clone does not have
PYTHONPATH=. .venv/bin/python tests/serve_workbench_fixture.py    # :8131
```

## Tests

```sh
scripts/pool-test.sh          # the python suite and the three javascript suites
scripts/pool-test.sh python   # PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
scripts/pool-test.sh python test_operations   # one python module, by the bare name of its file
scripts/pool-test.sh js       # node tests/test_ops.js, tests/test_board.js, tests/test_app_timeline.js
```

Name one file directly when you work on it (`node tests/test_board.js`,
`scripts/pool-test.sh python test_operations`).  The dotted spelling
`python -m unittest tests.test_operations` cannot work in this checkout: the name `tests`
answers `.venv/lib/python3.14/site-packages/tests`, which is another package, so the loader
reports `ModuleNotFoundError` for a file that is present.  The script runs the module from
inside `tests/` instead, and it refuses a dotted name and says why.
A bare `node --test` is not a test command here: no file name matches the node
default patterns (`*.test.js`, `test-*.js`), so it collects 0 tests and exits 0.

Tests that need SAM 3 or a local recording skip themselves when it is missing,
so a fresh clone runs green: `OK (skipped=147)`, no failures. The skips are the
tests that expect the maintainers' own recordings under `data/` and scan output
under `out/` (both ignored by git); put those fixtures in place and they run.

## Video sources and Twitch

The pipeline reads any video that OpenCV/FFmpeg can open: a file under `data/`,
or a stream URL.

The Twitch ingest (`annotator/twitch_source.py`,
`annotator/twitch_vod_source.py`) uses Twitch's **unofficial web-player
endpoints** (`gql.twitch.tv`, `usher.ttvnw.net`). Use it **only for streams
you own**. It **may break at any time**, and automated access may **conflict
with Twitch's Terms of Service**. The official alternative is to capture your
own camera or encoder feed (RTSP, OBS or NDI output) before it goes to Twitch.
Configure the channel yourself; none is built in.

The Twitch chat panel in the UI uses Twitch's official embed.

## Face identification: non-commercial models

Face identification uses InsightFace's `buffalo_l` models. The InsightFace
library is MIT, but its pretrained models are licensed **"for non-commercial
research only"**. This project uses them non-commercially. If you use Corner
Pocket commercially, replace the face model or get a commercial licence from
InsightFace first.

The app stores face and body embeddings of the people it identifies under
`out/`. Check the biometric-privacy law where you run it (for example GDPR,
BIPA or CCPA), and tell the people on camera. A regular's profile can delete
their face data.

## Licence

Our own code is dedicated to the public domain under **CC0-1.0**
([LICENSE](LICENSE)).

- [NOTICE](NOTICE) lists every third-party component and its licence.
- `src/reid/osnet.py` is copied from torchreid and stays under the **MIT**
  licence in its header.
- **AGPL caveat:** the program imports `ultralytics`, which is
  **AGPL-3.0** ([LICENSE-AGPL-3.0.txt](LICENSE-AGPL-3.0.txt)). CC0 does not remove the AGPL from
  the combined program. If you convey it, or run a modified version as a
  network service, the AGPL applies to the whole program, including section
  13: users who interact with it over the network must be offered its
  complete source.
- The model weights are not in this repository and have their own terms:
  `yolov8n.pt` is AGPL-3.0; the OSNet weights were trained on MSMT17, whose
  terms are academic and non-commercial; `buffalo_l` is non-commercial
  research only; SAM 3 is under Meta's SAM License. Details are in
  [NOTICE](NOTICE).
