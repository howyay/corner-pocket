# Vision tab — factual audit

**Scope:** the Vision tab of the Corner Pocket operations/review app. Audit only; no product code was changed.
**Workspace:** `/home/operator/projects/pool`. **Date of capture:** 2026-09-21 (local, PDT).
**Evidence convention:** every claim is backed by `file:line` quoted from the working tree, or by a screenshot in `out/vision-audit/` that was captured in this audit.

> Line-number caveat: `annotator/ops.html` is 2 physical lines and `annotator/ops.js` is 64 physical lines of semi-minified code. Line numbers below are physical lines in the current file; the `function`/`identifier` name is given with each one so it survives reformatting.

---

## 0. How the evidence was produced

1. Fixture server (copied data, no production writes):
   `PYTHONPATH=. .venv/bin/python tests/serve_workbench_fixture.py` → `http://127.0.0.1:8131` (`tests/serve_workbench_fixture.py:12-45`). It symlinks `annotator/`, `data/`, `src/` read-only and copies only JSON/annotation state into `out/ui-browser-fixture/`.
2. Browser: `agent-browser` 0.38.1 (Chrome 153.0.8010.52), named session, viewports 1280×900 and 390×844.
3. Console + page-error buffers were read at the end of the run: **0 console messages, 0 page errors** (recorded in §6).
4. Tests were run to confirm the current baseline: `node tests/test_app_timeline.js` → `16 passed, 0 failed`; `node tests/test_ops.js` → pass (node test runner, 0 failed).

---

## 1. Sub-view inventory

Six sub-view names exist in the code (`reviewModes`, `ops.js:7`), plus the ops shell's own Vision screen. Only **two of them are reachable by a mouse/touch user**: `stream` (the collapsed shell `<details>`) and `timeline` (the review's default mode). The other four render correctly but their navigation is hidden — see §2.

| # | Sub-view | Renderer | DOM host | Endpoints called (measured) | State it owns |
|---|---|---|---|---|---|
| 1 | **Stream / sources** (`visionTab='stream'`) | `ops.js:48 visionScreenUnified()` → `ops.js:11 livePanel()` + `ops.js:47 twitchEmbed()` + inline `#source-form` | `#ops-shell > main#main > .stack > details.stream-panel` | `GET /api/live`, `GET /api/live/frame`, `POST /api/live` (start/stop) | `liveChoice`, `liveDetectors`, `liveTimer`/`liveGeneration`, `sourceId`, `chat` (`ops.js:6,8`) |
| 2 | **Event review** (`events`) | `app.js:53 renderEvents()` | `#vision-host > #review-root > #content` | `GET /api/vod30/events`, `GET /api/clip?dataset=vod30&t=…`, `POST /api/vod30/annotate`, evidence `GET /media/vod30/event-frame/<id>` | `state.index`, `state.filter`, `state.dirty`, `state.data.annotations` (`app.js:8,52-70`) |
| 3 | **Ball labels** (`balls`) | `app.js:98 renderBalls()` | same `#content` | `GET /api/balls/<set>/meta`, `POST /api/balls/<set>/label`, `GET /media/balls/<set>/<file>` + `/ctx/<ctx>` | `state.set`, `state.index`, `state.filter`, `state.data.labels` (`app.js:97-108`) |
| 4 | **Table calibration** (`calibration`) | `app.js:113 renderCalibration()` | same `#content` | `GET /api/vod30/anchors?t=<t>`, `POST /api/vod30/anchors`, `GET /media/vod30/frame?t=<t>` | `state.pts` (6 anchors), `state.anchor`, `state.t`, `state.dirty` (`app.js:113-133`) |
| 5 | **Player identities** (`players`) | `app.js:134 renderPlayers()` | same `#content` | `GET /api/vod30/tracklets`, `GET /api/vod30/tracks?win=&t=`, `GET /api/vod30/seeds`, `GET /api/vod30/rebuild`, `POST /api/vod30/rebuild`, `POST /api/vod30/seeds`, `GET /api/identity/status`, `GET /media/vod30/frame?t=` | `state.win`, `state.track`, `state.tracks`, `state.seeds`, `rebuildTimer` (`app.js:134-166`) |
| 6 | **Video timeline / "Unified viewer"** (`timeline`) | `app.js:187 renderTimeline()` | same `#content` | `GET /api/video?dataset=`, `GET /api/vod30/events`, `GET /media/vod30/video`, `GET /api/frame?dataset=&frame=`, `GET /api/frame-result?dataset=&frame=`, `GET /api/unified?dataset=&frame=`, `POST /api/inference`, `POST /api/frame-correction` | `state.vmeta`, `state.frame`, `state.fresult`, `state.unified`, `state.boxes`, `state.polygon`, `state.sel`, `state.tool`, `state.overlay`, `state.dirty`, `state.busy` (`app.js:8,187-407`) |

### 1.1 Per-sub-view detail

**Stream / sources** — a single collapsed `<details class="stream-panel">` whose `<summary>` is the only thing visible on landing: `Vision · Stream / sources 直播与来源` (`ops.js:48`). Expanded it contains the live-processing panel (source `<select>`, `Table`/`Person` checkboxes, `Start`/`Stop`), a **Twitch player `<iframe>` plus a Twitch chat `<iframe>`** (both 540 px tall, measured), and a Twitch-source add/remove form. Measured expanded height of `#main`: **1385 px**; it pushes the review host to document-y **1559**.
**Event review** — `<div class="review-grid">` = a `.queue` list of candidates on the left and `#event-detail` on the right (`app.js:56-69`). Detail = one looping `<video>` clip around the event (`/api/clip`, ±1.5 s / +2.5 s), a facts strip, `Verdict` + `Shooter` selects, a note textarea, `Save review`, `Next candidate →`, and a `<details>` holding a full-VOD `<video>` seeked to the event time. 38 visible controls in `#content`.
**Ball labels** — crop image + optional context crop, a 0–15 grid (`CUE`, `SOLID`, `EIGHT`, `STRIPE`), `Unknown`, `Clear label`, and prev/next crop. Each label button posts immediately (`app.js:106`). 22 visible controls.
**Table calibration** — `timeToolbar()` (frame-time number input + `Load frame`) + a 6-anchor SVG overlay on `/media/vod30/frame?t=`, an anchor list, a 4-button nudge pad, `Save six anchors`. 13 visible controls. Gated to the `vod30` dataset only (`app.js:38`, `unified_server.py:667-668`).
**Player identities** — track-window `<select>`, identity-status panel, frame with track boxes, track list, seed buttons (`Player A` / `Player B` / `Ignore` / `Clear seed`), plus an identity-rebuild block. 13 visible controls. Seeding is explicitly two-step: saving a seed does **not** rebuild predictions (`app.js:139` hint, `app.js:165-166`).
**Video timeline ("Unified viewer")** — toolbar (4 overlay checkboxes, jump-to-frame, jump-to-time), then a `.timeline-grid` of three panels: `Local VOD player` (`<video id="vod">` + transport + scrub bar with event ticks), `Frozen frame inspector` (`#t-img` + `#t-overlay` SVG), and `Frame inference` + `Correction editor`. 52 visible controls in `#content`, the largest surface in the app.

---

## 2. Mount plumbing — verdict

**Verdict: the review *does* mount, but into `#vision-host`, not into `#vision-host-host`. `#vision-host-host` exists only at runtime as an empty div inside a discarded shell template. `visionNavigation()` is dead code, so `visionTab` never leaves its initial value `'stream'`. `/api/review-template` is still the only mount path, and `/app.html` is unreachable because it 308-redirects to `/`.**

### 2.1 Which element exists

`ops.html` (physical line 2, after `</div></div></main>`) declares **only** `#vision-host`, outside `#ops-shell`:

```html
</div></div><section id="vision-host" hidden aria-label="Vision review"></section></body></html>
```

`ops.js:48` (`visionScreenUnified`) emits a **different, empty** element into the shell's `<main>`:

```js
...<div id="vision-host-host"></div></section>`}
```

Measured at runtime (1280×900, Vision tab active):
- `#vision-host` → exists, `hidden === false`, parent `body`, height 1559 px, document-y 759.
- `#vision-host-host` → exists, **height 0 px, 0 children**. Nothing in `ops.js`/`app.js` ever queries it (grep: 1 occurrence in the tree, its own literal).
- `#review-root` → exists, `parentElement.id === 'vision-host'`, `dataset.embedded === 'true'`.

`#vision-host-host` is a dead placeholder; `#vision-host` is the real host.

### 2.2 The actual mount path

`showReview()` (`ops.js:23`) is called from `render()` (`ops.js:34`, tail: `...showReview();syncLivePolling();...`) on every shell render:

```js
async function showReview(){const host=$('#vision-host');if(!host)return;const active=tab==='vision';host.hidden=!active;
if(!active){review()?.deactivate();return}
try{if(!reviewPromise)reviewPromise=(async()=>{const response=await fetch('/api/review-template');
if(!response.ok)throw Error(`HTTP ${response.status}`);
const parsed=new DOMParser().parseFromString((await response.json()).html,'text/html');
const root=parsed.querySelector('#review-root');if(!root)throw Error('Review markup is unavailable');
root.dataset.embedded='true';if(!host.querySelector('#review-root'))host.appendChild(document.importNode(root,true));
const mounting=review().mount(host.querySelector('#review-root'));
if(tab==='vision'&&visionTab!=='stream')review().activate('timeline');await mounting})();
await reviewPromise;if(tab==='vision'){review().setAppearance(lang,theme);review().activate('timeline')}}
catch(error){reviewPromise=null;message(`${t('error')}: ${error.message}`,true)}}
```

Server side (`unified_server.py:930-931`):

```python
if path == '/api/review-template':
    return self.json(200, {'html': (backend.root / 'annotator' / 'app.html').read_text()})
```

So the "review client" is `annotator/app.html` injected as raw text (no iframe), and `app.js:430-432` accepts it only when `host.id === 'review-root'`:

```js
function mount(host) {
  if (root) return root === host ? mounting : false;
  if (!host || host.id !== 'review-root') return false;
```

`app.js:626-627` auto-mounts a standalone `#review-root`; on `ops.html` that node does not exist at script-evaluation time (`app.js` is deferred and runs before `ops.js`), so the standalone branch is inert and `ops.js` drives the mount. Measured: at the floor landing, `#review-root` count = 0, `#vision-host.hidden` = true; after clicking Vision, both flip. The mounted `#review-root` node persists across tab switches (audit marker survived a Vision → Floor → Vision round trip; `#vision-host.innerHTML` stayed at 12337 chars and the mode stayed `timeline`).

### 2.3 Is the review navigation usable?

`showReview()` sets `root.dataset.embedded='true'`, and `app.css:4-5` hides the review's own navigation in that state:

```css
&[data-embedded] .brand, &[data-embedded] .feed-pill, &[data-embedded] .chip-group,
&[data-embedded] nav, &[data-embedded] .ops-strip, &[data-embedded] .bottom-bar { display: none !important; }
```

Measured computed styles inside the embedded review: `nav[aria-label="Workbench modes"]` → `display: none`; its five `data-mode` buttons (`events`, `balls`, `calibration`, `players`, `timeline`, declared `app.html:42-46`) are therefore unrendered/unclickable. `.brand`, `.feed-pill`, `.chip-group`, `.ops-strip`, `.bottom-bar` are all `display: none` as well.

**Consequence: `Event review`, `Ball labels`, `Table calibration` and `Player identities` are not reachable through the UI in the Vision tab.** They only render if `window.CornerPocketReview.activate('<mode>')` is called from the console (which is how §6 captured them). The reachable Vision surface is `stream` + `timeline`.

### 2.4 `visionTab` / `visionNavigation()`

`visionNavigation()` (`ops.js:24`) renders the six `data-vision` buttons:

```js
function visionNavigation(){return `<nav class="vision-tabs" aria-label="Vision sections">${Object.entries(reviewModes).map(([key,label])=>`<button data-vision="${key}" ...`)}</nav>`}
```

- Call sites of `visionNavigation` in the tree: **1 — its own definition.** It is dead.
- Measured at runtime: `document.querySelectorAll('nav.vision-tabs').length === 0`, `document.querySelectorAll('[data-vision]').length === 0`.
- The only writer of `visionTab` is the click branch `if(b.dataset.vision){...visionTab=b.dataset.vision;render()...}` (`ops.js:56`), which requires a `data-vision` button that is never rendered. `visionTab` is therefore permanently `'stream'` (`ops.js:6`).
- Knock-on effects: `ops.js:23`'s `if(tab==='vision'&&visionTab!=='stream')review().activate('timeline')` never fires; `ops.js:34`'s `$('#main').classList.toggle('short',tab==='vision'&&visionTab!=='stream')` never applies; measured `#main` `classList.contains('short') === false` while Vision is active.

### 2.5 `/app.html` and `/ops.html` redirects

```python
if path in ('/app.html', '/ops.html'):
    return self.send(308, b'', 'text/plain', {'Location': '/'})
```

(`unified_server.py:928-929`.) Verified: `GET /app.html` → `308 → http://127.0.0.1:8131/`; `GET /ops.html` → `308 → http://127.0.0.1:8131/`; `GET /` serves `ops.html` (`unified_server.py:957-958`). There is **no standalone review URL anymore** — `/api/review-template` + `showReview()` is the only way to obtain and mount the review client. The mounted markup still contains `<a class="brand" href="/ops.html">` (`app.html:17`), so the review's own brand link is a redirect back to the root that resets the shell to the Floor tab (`ops.js:6` initializes `tab='floor'`).

---

## 3. Dead / duplicated / contradictory code

### 3.1 Byte-identical duplicate definitions (`ops.js`)

Each of these three functions is defined twice with **identical bytes** (verified by string equality of the source lines). JavaScript hoisting means the *second* definition wins and the first is dead code, but a reader/editor can easily change the wrong one:

| Identifier | First (dead) | Second (effective) |
|---|---|---|
| `playersScreen()` | `ops.js:44` (3209 b) | `ops.js:49` (3209 b) |
| `playerForm(p)` | `ops.js:45` (772 b) | `ops.js:50` (772 b) |
| `parseSource(value)` | `ops.js:46` (624 b) | `ops.js:51` (624 b) |

### 3.2 Dead functions

| Identifier | Where | Proof |
|---|---|---|
| `visionNavigation()` | `ops.js:24` | 1 occurrence in the file (its definition). Runtime: 0 `nav.vision-tabs`, 0 `[data-vision]`. |
| `visionScreen()` | `ops.js:52` (1973 b) | Not referenced by the screen map at `ops.js:34` (`vision:()=>visionScreenUnified()`). It is a full earlier Vision screen (Twitch iframe + chat + chat toggle + tiles) now unreachable. |
| `vision-host-host` `<div>` | emitted by `ops.js:48` | Empty at runtime (height 0, 0 children); no code reads it. |

### 3.3 Unused `reviewModes` keys and their knock-ons

`reviewModes` (`ops.js:7`) has six keys:

```js
const reviewModes={stream:['Stream / sources','直播 / 视频源'],events:['Event review','事件审核'],balls:['Ball labels','球标注'],calibration:['Table calibration','球台校准'],players:['Player identities','球员身份'],timeline:['Video timeline','视频时间线']};
```

- `reviewModes` is consumed **only** by the dead `visionNavigation()`. A zh label table for controls that never render.
- `stream` has **no counterpart** in the review client: `app.js:9`'s `modes` has only `events|balls|calibration|players|timeline`. `CornerPocketReview.activate('stream')` would return `false` (`app.js:422-424`, `Object.hasOwn(modes,'stream')` is false).
- `reviewModes.timeline` says **"Video timeline"**, while the review's own mode name is **"Unified viewer"** (`app.js:9`). Two names for one sub-view; `app.html:46` still carries the old one.

### 3.4 Unused translation entries (labels that can never appear)

- **45 `editorCopy` keys** (`app.js:459-518`) never occur in `app.html` or in the UI-rendering code (lines 1-449 and 559-628). Examples that name features that do not exist in the current UI: `"Correction tools"`, `"Add cue"`, `"Ball 1–15"`, `"Apply box edit"`, `"Correction note"`, `"Clear all boxes"`, `"Auto-run after scrub"`, `"Show table"`, `"Show persons"`, `"Show balls"`, `"Overlay layers"`, `"Table model"`, `"Person model"`, `"Ball model (optional)"`, `"Run detectors"`, `"Preview paused"`, `"Preview unavailable"`, `"Source video unavailable"`, `"Save anchors"` (the rendered button is `"Save six anchors"`, `app.js:118`), `"Next →"` (rendered: `"Next candidate →"`, `app.js:65`), `"Run rebuild"` (rendered: `"Rebuild assignments"`, `app.js:139`), `"Select a candidate."`, `"Loading…"`.
- **`app.js:583`** (`translateEditor`) queries `#play-state`, an element that is never rendered (`"play-state"` appears exactly once in `app.js` — in that selector list). Same selector list also queries `#t-save-state`, which is also never rendered (the timeline uses `#save-state`).
- **4 rendered strings have no zh translation at all**, verified in-browser with `lang=zh`: the timeline title stays `"Unified viewer"`, the timeline subtitle stays the English `"Scrub the local VOD and inspect balls, pockets, cloth, persons, and identity overlays on one canvas."`, and 3 of the 4 overlay checkboxes stay English — measured label texts: `["球","Pockets","Persons","Identity"]` (`"Balls"` translates, the rest do not; only `"Balls"`/`"Table"`/`"Person"` exist in `editorCopy`).
- **`ops.js` `words`**: 12 keys are never read by any code path — `reviewNote`, `openReview`, `loadReview` (leftovers from an earlier "open the review workbench" design), plus `loading`, `finished`, `pick`, `winner`, `Prospect`, `editPlayer`, `joined`, `notMeasured`, `serviceError`.

### 3.5 Controls / surfaces that render but can be misread or do nothing

| Item | Evidence |
|---|---|
| Review mode `nav` renders but is `display:none` | `app.css:4-5` + measured computed style. 5 buttons × 2 lines of label each are dead weight. |
| `Start` on the live panel can fail with no in-panel feedback | Measured: `POST /api/live {"action":"start",...}` → `400 {"error":"Allowlisted dataset media is unavailable"}` (fixture has no media for the live decoder). `#live-status` still reads `idle · Receive-to-result: — ms · …`; the error appears only in the shell's `#message` at document-y 835 (≈560 px away from the button) and auto-clears after 12 s (`ops.js:15,30`). See `out/vision-audit/13-live-start-error-1280.png`. |
| `OVERLAYS: none` label lies | Frozen frame at frame 150: `#frame-facts` reads `RAW DECODED FRAME · vod30 · frame 150 · nominal 0:05.0s (nominal_cfr) · OVERLAYS: none`, while `#t-overlay` renders **19** overlay nodes — measured breakdown: 6 `u-pocket` + 4 `u-person` + 7 `u-ball` + 1 `u-cloth` polygon + 1 `u-pot-pulse`, all from `/api/unified`. The facts line only reflects `frame-result` (correction/inference), never `state.unified` (`app.js:263` vs `app.js:271-295`). See `out/vision-audit/08-timeline-frozen-overlays-1280.png`. |
| `Stop` when idle | `ops.js:11,15` always renders both buttons; `Stop` posts `{"action":"stop"}` and returns the unchanged `idle` payload. No disabled state, no feedback. |
| `.stream-panel` open state is destroyed by any shell render | Measured: expand `.stream-panel`, click a theme button (shell render) → `details.open === false`. `render()` rebuilds `#main.innerHTML` (`ops.js:34`). Consequence: live polling stops (`pollLive` continues only when `document.querySelector('.stream-panel')?.open`, `ops.js:14`). |
| `#live-frame` canvas exists but stays `hidden`, 300×150 | `ops.js:11,14`; measured `hidden:true`, `width:300, height:150`, `display:none` after a failed start. |
| Two independent confirmation channels | Review writes `#notice`/`#save-state` inside `#vision-host` (`app.js:11,19`); the shell writes `#message` inside `#ops-shell` (`ops.js:30`). Both were visible simultaneously during this audit. |

---

## 4. UX friction inventory (Vision tab only)

Measured at 1280×900 unless stated. "Cost" = operator-visible steps or pixels.

1. **~1 full viewport of dead space before any review content.** `#ops-shell` height 759 px; its `#main` is 585 px tall but contains only a 23 px `<details>` summary at y=196 and the 0-height `#vision-host-host` at y=235 — i.e. ≈524 px of blank band. `#vision-host` starts at document-y 759, `#review-root` header at 759, `.page-heading` at 836, `#content` at **932 px** (measured `scrollDepthToContentTop = 932` for every sub-view). The page scroll height is 2318 px at a 900 px viewport. See `out/vision-audit/01-vision-1280.png`, `02-review-top-1280.png`.
2. **The sub-view navigation is invisible.** Mode switching costs the operator a devtools console (`CornerPocketReview.activate(...)`), because `#review-root[data-embedded] nav {display:none!important}` removes the only mode switcher, and `visionNavigation()` never renders. Four of six sub-views are unreachable by design accident.
3. **Two stacked chrome blocks.** The shell header (brand, EN/中 + theme chips, 6-tab nav, shot-clock strip) plus the review's own `ops-header` bar with its dataset `<select>` (the only VOD dataset control in the app), then the review's `THE REVIEW DESK / Unified viewer` heading with its `INSPECT · LABEL VERIFY` stamp. The review's `.brand`, `.feed-pill`, `.chip-group`, `.nav`, `.ops-strip`, `.bottom-bar` are hidden (`app.css:4-5`), so what survives is a partial second header. Measured: shell occupies 0–759 px; the review's own header band is 759–920 px. See `02-review-top-1280.png`, `05-timeline-1280.png`.
4. **The same frame is on screen twice, side by side.** `out/vision-audit/08-timeline-frozen-1280.png` shows `Local VOD player` and `Frozen frame inspector` displaying *the same frame 150* (both 567×319, identical content); `/media/vod30/video` and `/api/frame` are two different byte sources for that one moment. Frozen-frame overlays then land **asynchronously** (measured `/api/unified`: 0.36 s at frame 150, 1.59 s at frame 900, **7.55 s** at frame 3000) so the annotated image visibly lags the bare one.
5. **Six surfaces show "a frame" of the same video.** (a) `#live-frame` canvas, `ops.js:14`; (b) Twitch player `<iframe>`, `ops.js:47`; (c) `<video id="vod">`, `app.js:191`; (d) `#t-img` frozen decoded frame, `app.js:256-259`; (e) `.frame > img` raw frame in calibration *and* players, `app.js:110`; (f) event evidence `<video src="/api/clip?…">` + `event-frame` fallback + a nested full-VOD `<video>`, `app.js:61-66`. Surfaces (c)–(f) are all the same local VOD frame reached through three different endpoints (`/media/<ds>/video`, `/api/frame`, `/media/<ds>/frame`, `/api/clip`, `/media/<ds>/event-frame/<id>`); (a) shows whatever the live source is — which is that same VOD only when the source is `dataset:vod30`.
6. **Event candidate → labelled, the honest click path (when `events` is reachable at all):** (1) scroll ~932 px past the shell; (2) click a queue row in `.queue` (no keyboard list navigation); (3) `Verdict` select; (4) `Shooter` select; (5) optional note; (6) `Save review`. There is no "label the event I am looking at from the timeline" affordance — the timeline's scrub markers (`app.js:191`) are not clickable through to a verdict, they only seek.
7. **Save confirmation exists but is generic and unlabelled.** Verified live: choose event #5, set `unsure`, type a note, click `Save review` → `#save-state` becomes `"Saved"`, `#notice` shows `"Saved to the review dataset."`, and the queue row updates to `pot0:17#5 · unsure`. Every save yields the same generic string; there is no per-artifact confirmation. See `out/vision-audit/14-event-save-confirmed-1280.png`.
8. **Keyboard support is thin and collides with the native video element.** `app.js:418-420` binds `onKeydown` on `#review-root`, gated on `active`, and returns early only for `input,textarea,select,button,[contenteditable]` — `<video>` is **not** excluded. In timeline mode `ArrowLeft/Right/Up/Down` nudge the selected box (`app.js:419`), and Chrome's native media controls also respond to ArrowLeft/ArrowRight when the focused element is the `<video controls>` (`app.js:191`), so one keypress can be consumed by both. `,` / `.` are intercepted with `preventDefault()` and step exactly one frame. `ops.js` registers **no** keydown handler at all, so there is no keyboard way to switch shell tabs or review modes (and the mode nav is hidden anyway). Verified part of this: `video` is absent from the early-return selector list; the double-consumption itself was **not** reproduced in-browser (see §7).
9. **Mobile 390×844 is a blank screen.** `#ops-shell` occupies **0–903 px** (i.e. more than the 844 px viewport: header is `position:static` and wraps). Vision landing shows only the `▶ Vision · Stream / sources` summary at y=387 and nothing else; the review starts at document-y 903 and `#content` at y=1088. Document scroll height 3219 px. No horizontal overflow (`scrollWidth === 390`). The review grid correctly collapses to one column (`grid-template-columns: 298px`), and the timeline's three panels stack (634 px / 356 px / 834 px), but the operator must scroll ~1.3 viewports before seeing any evidence. See `out/vision-audit/11-mobile-390-vision-landing.png`, `12-mobile-390-events.png`.
10. **Control density.** User-visible interactive controls (buttons/inputs/selects/videos/summaries; elements inside a closed `<details>`, inside `[hidden]`, or with zero rendered size are excluded). Whole-page totals at 1280×900: **events 58, balls 42, calibration 33, players 33, timeline 72, Vision landing 72**, versus **19** on the Floor landing baseline. Of the 72 on the timeline, **19 belong to the always-present ops shell** (11 chrome + 7 shot-clock/`#strip` + 1 stream summary) and 53 to the review. The Vision tab is by far the densest screen in the app.

---

## 5. Live vs VOD overlap

**What is genuinely live-capable:** only the Twitch path. `annotator/live_processing.py:1-5` documents the accepted sources as `{'kind':'dataset','dataset':'vod30'|'highlight'}` or `{'kind':'twitch','source_id':<saved Operations channel id>}` — no arbitrary URLs, files, stream credentials or detector models. `POST /api/live` is handled in `unified_server.py:923-926,123-136`. A `dataset` source is a recorded file fed through the live pipeline; a `twitch` source is the only genuinely live input.

**How the four live/VOD surfaces relate:**

| Surface | Implementation | Data source | Live? |
|---|---|---|---|
| Live processing panel (`#live-panel`, `Start`/`Stop`, detectors) | `ops.js:11,15,17`; canvas painted in `ops.js:14` | `POST/GET /api/live`, `GET /api/live/frame` (JPEG + `X-Live-Metadata` boxes/polygon) | Replay (`dataset:vod30`/`highlight`) or Twitch |
| Twitch embed + chat (`ops.js:47 twitchEmbed()`) | two `<iframe>`s (`player.twitch.tv`, `twitch.tv/embed/<ch>/chat`) | external Twitch origin | Whatever Twitch has; the label is honest: `TWITCH CHANNEL · LIVE STATUS UNVERIFIED` (`ops.js:4 vodLabel/liveLabel`) |
| Video timeline (`app.js:187-218`) | `<video src="/media/<dataset>/video">` + scrubber over decoded frame indexes | `GET /api/video`, `GET /media/<ds>/video` | Replay only; the toolbar chip states it: `LOCAL INGESTED VOD ONLY · NO LIVE SOURCES` (`app.js:191`) |
| Frozen frame inspector (`app.js:256-295`) | `#t-img` from `GET /api/frame` + SVG overlay from `GET /api/unified` | same local VOD, one decoded frame | Replay only |

**Where the same frame is displayed twice:** the timeline shows the identical frame in the `Local VOD player` (`<video>`, scrubbed to frame 150) *and* in the `Frozen frame inspector` (`<img>` from `/api/frame`, frame 150) — both 567×319 px, both the same pool-table image, side by side. Screenshot: `out/vision-audit/08-timeline-frozen-1280.png`. The player copy is bare; the inspector copy carries overlays. The two panels even disagree about *when* the frame is: the player transport reads `0:04 / 30:00` while the inspector badge reads `FRAME 150 · 0:05.0 · VOD30`, for the same image (frame 150 ÷ 30 fps = 5.0 s). The inspector copy also appears **after** the player copy (measured `/api/frame` 0.13–0.38 s, `/api/unified` 0.36–7.55 s), so the two are not even simultaneous.

**Live/replay contradictions in the copy:**
- The panel is titled `Native live processing` and its default source option is `Local replay · 30 min` — a "live" panel whose default input is a recording.
- Its own note disclaims latency: `Twitch upstream delay: UNKNOWN. Receive-to-result is local processing latency, not glass-to-glass latency.` (`ops.js:11`).
- The live overlay painting (`ops.js:14`, green `#7fc39a` rects on a canvas) and the frozen-frame overlay painting (`app.js:271-295`, SVG with brass/red strokes) are two independent implementations of the same concept, with different geometry sources (`X-Live-Metadata` vs `/api/unified`) and different visual languages. Nothing shares code between them.
- `#live-status` is the only live surface that reports `frame_age_ms` / `STALE` / `Dropped`; the VOD surfaces have no equivalent health readout.

---

## 6. Current-state evidence (screenshots, console, control counts)

Captured against the fixture server on 127.0.0.1:8131 with agent-browser (Chrome 153). **Console messages: 0. Page errors: 0.** All files are in `out/vision-audit/`.

| File | Viewport | What it shows |
|---|---|---|
| `00-landing-1280.png` | 1280×900 | Landing state on the Floor tab (baseline for the shell chrome). |
| `01-vision-1280.png` | 1280×900 | Vision tab landing, scrolled to top: only the collapsed `Vision · Stream / sources` summary; ≈525 px blank band; review content below the fold. |
| `02-review-top-1280.png` | 1280×900 | Vision tab scrolled to `#review-root` top: partial second header, `VOD dataset` bar, `THE REVIEW DESK / Unified viewer`. No mode nav anywhere. |
| `03-timeline-1280.png` | 1280×900 | Timeline sub-view scrolled: transport, scrub bar with event ticks, `Frame inference` + `Correction editor`; the grid's 4th cell (right of `Frame inference`) is empty. |
| `04-stream-sources-1280.png` | 1280×900 | Stream/sources sub-view expanded: live panel, Start/Stop, Twitch player showing `examplechannel is offline`, Twitch consent + chat iframes. |
| `05-events-1280.png` | 1280×900 | Event review sub-view (queue + detail). Reachable only via console. |
| `05-balls-1280.png` | 1280×900 | Ball labels sub-view. Reachable only via console. |
| `05-calibration-1280.png` | 1280×900 | Table calibration sub-view (6 anchors + nudge pad). Reachable only via console. |
| `05-players-1280.png` | 1280×900 | Player identities sub-view (track window, track list, seed buttons, rebuild). Reachable only via console. |
| `05-timeline-1280.png` | 1280×900 | Video timeline / "Unified viewer" sub-view (default reachable mode). |
| `06-event-review-detail-1280.png` | 1280×900 | Event detail: looping `/api/clip` video + facts strip. |
| `06b-event-review-decision-1280.png` | 1280×900 | Event decision form: Verdict, Shooter, note, `Save review`, `Next candidate →`, `Saved review` state, `Open source video at 0:05`. |
| `07-events-fullpage-1280.png` | 1280×900 (full scroll) | Full-height capture of the events sub-view. |
| `08-timeline-frozen-1280.png` | 1280×900 | **The duplicate frame**: `Local VOD player` (transport reads `0:04 / 30:00`) and `Frozen frame inspector` (`FRAME 150 · 0:05.0 · VOD30`) showing the same image side by side — and even disagreeing about its time. |
| `08-timeline-frozen-overlays-1280.png` | 1280×900 | Same, after `/api/unified` resolved: pocket circles, 7 ball circles, 4 `track N` person boxes — while the facts line still reads `OVERLAYS: none`. |
| `09-vision-fullpage-1280.png` | full page | Full-page Vision tab (2318 px of document for a 900 px viewport). |
| `10-mobile-390-landing.png` | 390×844 | Floor landing on mobile. |
| `10-mobile-390-timeline.png` | 390×844 | Vision/timeline on mobile. |
| `11-mobile-390-vision-landing.png` | 390×844 | **Mobile Vision landing: essentially blank** (shell occupies 903 px of an 844 px viewport). |
| `12-mobile-390-review-top.png` | 390×844 | Mobile, scrolled to the review header (blank band above it). |
| `12-mobile-390-events.png` | 390×844 | Mobile events sub-view, queue stacked above detail. |
| `12b-mobile-390-events-detail.png` | 390×844 | Mobile event detail scrolled. |
| `13-live-start-error-1280.png` | 1280×900 | `Start` failure: live panel still says `idle`, red `#message` `Allowlisted dataset media is unavailable` at the far side of the shell. |
| `14-event-save-confirmed-1280.png` | 1280×900 | Save confirmation: `#save-state` = `Saved`, `#notice` = `Saved to the review dataset.`, queue row = `pot0:17#5 · unsure`. |
| `15-zh-timeline-1280.png` | 1280×900 | Chinese locale: title still `Unified viewer`, overlay labels `["球","Pockets","Persons","Identity"]`. |

**Interactive-control counts** — user-visible only (elements inside a closed `<details>`, inside `[hidden]`, or with zero rendered size are excluded), 1280×900:

| Sub-view | review `#content` | review total | ops shell (incl. `#main`) | Shell `#strip`+chrome | page total |
|---|---|---|---|---|---|
| Vision landing (`visionTab='stream'`, details collapsed) | 52 (timeline default) | 53 | 19 | 18 + 1 summary | 72 |
| events | 38 | 39 | 19 | 18 + 1 summary | 58 |
| balls | 22 | 23 | 19 | 18 + 1 summary | 42 |
| calibration | 13 | 14 | 19 | 18 + 1 summary | 33 |
| players | 13 | 14 | 19 | 18 + 1 summary | 33 |
| timeline | 52 | 53 | 19 | 18 + 1 summary | 72 |
| Stream panel expanded | 53 | 53 | 32 | 18 + 14 in `#main` | 85 |
| (Floor landing baseline) | – | – | 19 | 11 + 8 in `#main` | 19 |

Backing details: `#main` holds only 1 visible control (the `<details>` summary) while the stream panel is collapsed; expanding it puts 14 controls in `#main` (1 summary + 5 live-panel + 2 Twitch-embed + 2 source-form + 4 source-row `Select…`/`Remove`) and grows `#main` to 1385 px tall. On the Floor tab `#strip` is emptied (`ops.js:34`), which is why the shell's chrome count drops from 18 to 11 there.

**Endpoints per sub-view** (observed traffic, deduplicated):
- stream/sources: `GET /api/live`, `POST /api/live`, `GET /api/live/frame`
- events: `GET /api/vod30/events`, `GET /api/clip?dataset=vod30&t=…`, `POST /api/vod30/annotate`
- balls: `GET /api/balls/unlabeled_crops/meta`, `POST /api/balls/<set>/label`
- calibration: `GET /api/vod30/anchors?t=70`, `POST /api/vod30/anchors`
- players: `GET /api/vod30/tracklets`, `GET /api/vod30/tracks?win=68-94&t=70`, `GET /api/vod30/seeds`, `GET/POST /api/vod30/rebuild`, `POST /api/vod30/seeds`, `GET /api/identity/status`
- timeline (freeze at frame 150): `/api/frame`, `/api/frame-result`, `/api/unified`, `/media/vod30/video`, then `POST /api/inference` / `POST /api/frame-correction` on demand
- mount sequence on opening Vision: `GET /api/operations` → click Vision → `GET /api/review-template` → `GET /api/live` → `GET /api/datasets` → `GET /api/vod30/events` → `GET /media/vod30/event-frame/1` → `GET /api/vod30/events` (**again**) → `GET /api/video?dataset=vod30` → `GET /api/clip?dataset=vod30&t=5.6` → `GET /media/vod30/video`. The events render is produced and thrown away before `activate('timeline')` runs (`ops.js:23` awaits `mounting`, then activates), costing one redundant `events` fetch plus a discarded evidence image on every cold mount.

**What the front-end tests do and do not cover** (`tests/test_app_timeline.js`, 16 assertions passing; `tests/test_ops.js`, passing):
- `tests/test_app_timeline.js:171-178` pins the app.js request contract and required labels; `:180-184` asserts `app.html` contains `data-mode="timeline"` and `Video timeline`; `:186-191` asserts `app.css` contains `.timeline-grid`, `.scrub-mark`, `.scrub-marks`, `.transport`, `.draw-preview`, `.t-poly`, `.center-dot`. Nothing asserts `/api/review-template`, `#vision-host`, or `data-embedded`.
- `tests/test_ops.js:73` asserts `Object.keys(reviewModes)` equals `['stream','events','balls','calibration','players','timeline']`, and `:82-84` simulates a click on `{vision:'balls'}` — a control that is never rendered. These assertions pass while `visionNavigation()` is dead, so the test suite cannot detect the missing sub-tab navigation.
- `tests/test_ops.js:96` asserts `html.indexOf('</main>') < html.indexOf('id="vision-host"')` — it pins that the host is outside `<main>` but never pins `#review-root`'s absence from `ops.html`, which is exactly why the stray `#vision-host-host` survived.
- Neither suite executes `showReview()` or the DOM import, so the `[data-embedded] nav {display:none}` consequence is untested.

---

## 7. Could not determine / not reproduced

1. **Arrow-key double consumption on the focused `<video>`.** The code path is unambiguous (`app.js:418-419` does not exclude `video`, and Chrome's native controls consume ArrowLeft/ArrowRight when the media element is focused), but reproducing it required a selected box, and no frame in the fixture had saved corrections or inference, so no box could be selected. Not verified in-browser.
2. **Live processing end-to-end (canvas painting, `STALE`, `Dropped`, `frame_age_ms`).** `POST /api/live` cannot start in the fixture — the fixture root has no allowlisted dataset media (`400 Allowlisted dataset media is unavailable`), and `examplechannel` is offline. The live overlay path (`ops.js:14`) was therefore read from code, not observed.
3. **Ball-label and calibration write paths.** Not exercised (would write to the fixture's copied annotation files, which is permitted, but the reads already established the endpoints and control sets).
4. **`POST /api/inference`.** Not run: `Balls · SAM3 on CPU (slow)` is an explicit opt-in and the person/table models were not warmed. The frozen-frame overlay path was verified via `/api/unified` instead.
5. **Native `<select>` dropdown interiors** are not captured in the screenshots (headless Chromium screenshots omit open native popups). Option lists were read from the DOM instead (e.g. the review `#dataset` select offers exactly `vod30`, `highlight`; `liveDetectors` checkboxes are both checked by default).
6. **Whether any external consumer depends on `/app.html`.** The redirect at `unified_server.py:928-929` makes the standalone review page unreachable in this server; whether a second server (`annotator/server.py`) or an operator bookmark still expects it was not traced.
