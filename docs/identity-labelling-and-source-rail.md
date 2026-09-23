# Identity labelling and the source panel (Vision rail, 2026-09-23)

Two owner requests, both in the Vision tab:

1. a human track is labelled as **one regular** (dropdown) **or one guest name** (textbox);
2. the **source settings leave the right rail** and open from the **Source chip** in the chip row.

## What the rail offers for a selected person track

`annotator/vision-stage.js` (`personBlock` + `bindingLine` + `actionsHTML`):

| choice | UI | write path | endpoint |
|---|---|---|---|
| a regular | `Which regular?` dropdown (roster: name · rating, plus the shell-language status word when not Active) | `CornerPocketReview.seedIdentity()` → `identity_pipeline().explicit_seed(cluster_id, player_id)` | `POST /api/identity/seed` `{cluster_id, player_id}` |
| a guest | `Guest name` textbox (enabled only while the guest option is chosen) | `CornerPocketReview.setSeed(button, name)` | `POST /api/vod30/seeds` `{win, t, track_id, label:<name>}` |
| neither | `Save` refuses before any write (`Type a guest name or choose a regular before saving.`) | — | — |
| unbind | `Clear` (footer) | `CornerPocketReview.clearIdentity()` | seeds clear (`label: null`) and/or `POST /api/identity/unbind` `{cluster_id}` |

`Which regular?` requires an identity cluster (that is what the face/body path binds). A rail pick
resolves the cluster from the same `/api/unified` payload the stage overlay already holds
(`trackIdentity()` in `app.js`); when the track has no cluster the rail says so (`noCluster`) instead of
failing silently.

**Spectators stay excludable**: `Ignore (not a player)` is a quiet dashed block under the two labelling
options. It writes the legacy `ignore` seed (the pipeline's own "do not assign" value).

## Legacy A/B values

The A/B buttons are gone from the primary UI; the values are not. `label` in
`out/pid_seed.json` stays a single slot with two accepted shapes:

- the three role words `A` / `B` / `ignore` — still the only values `src/pid_seed_rebuild.py`
  (`explicit_seeds`) trains from, so the identity pipeline and every previously recorded
  verdict/annotation keep working;
- any other string up to 60 characters — a guest name, stored, displayed and **never** trained on
  (the rebuild's `seed_labels` filter ignores it, so it cannot make a stored prediction look current).

Read back: a stored `A` renders as `Player A` (rail tag, stagebar, binding line) with the origin named
(`legacy A/B seed`); a guest name renders as itself (not upper-cased); `ignore` renders as `Ignore`.
The keyboard `A`/`B` seeds remain reachable in `app.js`, so the pipeline's two-role contract is still
writable by hand.

## Where the source settings went

`chipsHTML()` renders a `Source` chip as the **first** chip of the stage's chip row; one click opens
`#vs-source-panel` (absolutely positioned under the chip row, `max-height: min(72vh, 560px)`, internal
scroll) holding exactly what the rail used to: dataset chips, live state row, **live start/stop**,
live detector toggles, frame detectors, saved channels, the Twitch URL form and the latency caveat.
The rail's nothing-selected state is now `Nothing selected` + `Select a cue, a ball, a person or an
anchor to label it.` + the cue hint, then a clearly separated **`This frame`** heading with the frame
tools (Select/Draw, Add table polygon / Clear polygon, Run inference, Save corrections when dirty) —
those are frame tools, not source settings, and a cold frame must still be annotatable without
opening a settings panel.

## Verification (2026-09-23)

- `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q` → **Ran 325 tests … OK (skipped=2)** (was 322/2).
- `node tests/test_app_timeline.js` → **50 passed, 0 failed** (was 46; +4 pins: labelling options and endpoints, legacy rendering, source-panel separation, EN/中 copy).
- `node --test tests/test_ops.js` → **21 pass, 0 fail** (roster now carries rating + status).
- Fixture (`tests/serve_workbench_fixture.py`, :8131), agent-browser: cold `LOADING` awaited, then
  1280 and 390 — console messages 0, `documentElement.scrollWidth` == viewport at both widths, the
  source panel inside the viewport (390: left 8 / right 382), `#vs-live-status` still reading
  `idle · frame age — · receive-to-result — · dropped 0`.
- Writes exercised against the fixture only: guest name → `out/ui-browser-fixture/out/pid_seed.json`
  (`1:68-94` = `Minh (guest)`), legacy `A`/`ignore` hand-written into the same fixture file, identity
  seed + unbind against the fixture's own identity index. Production `out/corner-pocket/state.json`
  md5 `77777777777777777777777777777777` and `out/pid_seed.json` md5
  `77777777777777777777777777777777` (mtime 2026-09-12) are unchanged.
