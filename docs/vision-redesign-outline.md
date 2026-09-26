# Vision tab — redesign outline

**Status:** design artifact. No product code changed, no commits. Companion mockup: `out/vision-redesign/mockup.html`; screenshots in `out/vision-redesign/*.png`.
**Workspace:** `<repo>`. **Audit this redesign answers:** `docs/vision-audit.md` (2026-09-21).
**Visual language:** tokens, palette and type copied from `annotator/ops.css` `:root` and `annotator/app.css` (brass `#c9a227` / cream `#f6f1e6` / brown `#14110f`), reference `design/corner-pocket/Corner Pocket Ops.html` (2 px radius, `.14–.18em` tracking on 10 px mono labels, Zilla Slab headings, Barlow body, DM Mono numerals).

---

## 1. Problem summary

Six subtabs, none of them a job. Measured facts from the audit:

| # | Finding | Evidence |
|---|---|---|
| 1 | ~1 viewport of dead space before any evidence: shell 0–759 px, `#content` at document-y **932** | `01-vision-1280.png`, §4.1 |
| 2 | Four of six sub-views unreachable by mouse: `app.css:4-5` hides `nav` under `[data-embedded]`, `visionNavigation()` (`ops.js:24`) is dead code, so `visionTab` is permanently `'stream'` | §2.3, §2.4 |
| 3 | Two stacked chrome blocks — shell 0–759 px, partial review header 759–920 px | §4.3 |
| 4 | The same frame is on screen twice side by side (`Local VOD player` + `Frozen frame inspector`, both frame 150, 567×319) and the two copies **disagree about its timecode** (`0:04` vs `FRAME 150 · 0:05.0`); overlays land async at **0.36 s / 1.59 s / 7.55 s** | `08-timeline-frozen-1280.png`, §4.4, §5 |
| 5 | Six surfaces render "a frame" of one video (live canvas, Twitch iframe, VOD `<video>`, frozen `<img>`, calibration/players `<img>`, event clip + fallback + nested video) | §4.5 |
| 6 | Event candidate → labelled costs a 932 px scroll plus a mode switch; scrub marks only seek, they never lead to a verdict | §4.6 |
| 7 | Save confirmation is generic and unlabelled: "Saved to the review dataset." for every artifact | `14-event-save-confirmed-1280.png` |
| 8 | Keyboard is thin and collides with the native `<video>`: `<video>` is not in the early-return selector list, so arrows can be consumed twice; no key reaches shell tabs or review modes | §4.8, §7.1 |
| 9 | Mobile 390×844 is a blank screen: shell occupies 0–903 px of an 844 px viewport; first evidence at y=1088 | `11-mobile-390-vision-landing.png` |
| 10 | Density: 72 visible controls on the Vision landing vs 19 on the Floor baseline | §4.10 |

The **live** half of the tab is also dishonest: the panel is titled *Native live processing* while its default source is a recording; the facts line reads `OVERLAYS: none` while 19 overlay nodes are drawn; a failed `Start` surfaces only in a toast at the far side of the shell while the panel keeps saying `idle` (`13-live-start-error-1280.png`).

---

## 2. The design: one stage, two rails, zero subtabs

Desktop ≥1100 px:

```
┌ shell chrome (existing, unchanged) ─────────────────────────────────────────────┐
├ source chip row ── VOD × 2 · live channel · chat docked … freshness · shortcuts  ┤
├───────────────────┬─────────────────────────────────────┬───────────────────────┤
│ CUES RAIL  280px  │ STAGE (flex, dominant, 16:9)        │ INSPECTOR  320px      │
│ event candidates  │  exactly ONE frame surface:         │ content follows the   │
│ ball-label queue  │  live edge OR frozen VOD frame      │ current selection     │
│ person tracks     │  layer chips toggle overlays        │                       │
│                   │  overlays are dragged on imagery    │                       │
├───────────────────┴─────────────────────────────────────┴───────────────────────┤
│ SCRUB STRIP: frame index · ±1 · freeze · event ticks · live-edge marker · facts │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Three rules carry the whole design:

1. **The rails hold the queues; the stage holds the evidence; the inspector holds the decision.** Selecting a cue seeks + freezes + zooms the stage. It never navigates away, because there is nowhere to navigate to.
2. **There is exactly one frame surface.** Live edge and VOD frame are the same element fed by different sources. A Twitch channel renders *in* that stage, and its chat docks in the inspector column — it is not a second 540 px iframe.
3. **Nothing is a mode.** Overlays are layer chips. Calibration is a layer. Ball labelling is a click on the imagery. Identity is a click on a person box. Event review is a cue card plus the inspector's verdict block.

Mobile 390 px: the same DOM. The stage keeps 16:9 at the top (y≈90–300), the source chips collapse to one row, the rails become a **bottom sheet** with a Cues / Inspector tab pair, and there is a single transport row. First evidence at **y≈88** instead of y=903.

---

## 3. Consolidation map

| Old sub-tab (unreachable or duplicated) | New home | Notes |
|---|---|---|
| `stream` / sources (`ops.js:48`) | source chip row + Source inspector | dataset chips, live start/stop, detector toggles, saved channels; chat docks in the inspector |
| `events` (Event review) | cues rail + inspector verdict block | verdict verbs on the card, verdict + shooter + note in the inspector, `V`/`1` commit from the stage |
| `balls` (Ball labels) | stage click / keyboard | label popover on the ball, 0–9 / U / C keys, per-crop saved line |
| `calibration` (Table calibration) | Anchors layer | the six anchors are drawn on the one stage and dragged there; numbers live in the inspector |
| `players` (Player identities) | person boxes on the stage | A / B / Ignore / regular name chips on the box's identity row |
| `timeline` (Unified viewer) | the scrub strip | the only timeline; frame index, ±1, freeze, event ticks, live-edge marker |
| Twitch embed (`ops.js:47`) | the stage itself, when the source is a live channel | one frame surface, chat in the inspector column |
| Review header + `ops-header` (`app.html:17`) | deleted | the source chip row carries the dataset choice |
| Dead `#vision-host-host` (`ops.js:48`) | deleted | `#vision-host` is the real host (§2.1) |

---

## 4. WYSIWYG rules

1. **Overlays are drawn on the imagery, in the imagery's coordinate system.** The stage renders one `<img>`/frame plus one SVG layer whose `viewBox` is the source frame (1280×720 for `vod30`). Everything the operator drags is the thing that is annotated; everything that is annotated is visible.
2. **Drag targets are the objects**: cloth polygon corners, the six calibration anchors, ball circles, person boxes. Each carries a visible grab affordance (handle dots, a drag cross on the selected anchor) and a hover cursor.
3. **Selection is legible**: the selected ball, person, anchor or cue is brass-filled and the rest stay neutral; a ball selection dims the frame slightly around it so the popover reads as attached to the object, not floating over the page.
4. **The inspector echoes the selection** and never shows two subjects at once. Nothing selected → the Source block.
5. **One place prints numbers.** The facts line is the single status surface: `frame 8100 · t 270.0 s · cloth 1 · balls 4 · persons 3 · pockets 6 · anchors 0 · overlays ON`. No second copy in a header, a badge, and a tooltip that can disagree.

---

## 5. Honest-liveness rules

1. **The facts line is derived from layer state, never hand-written.** `OVERLAYS: none` while nodes are drawn is structurally impossible: the count and the word come from the same render.
2. **Every source says what it is.** `vod30 · 1800 s · 30 fps` for a recording, `● live · twitch <channel>` for a live source, and the chip keeps the *attempted* source when a start fails, so chip and panel never contradict.
3. **Latency is stated where it is measured.** Live edge shows `frame age 240 ms` and the note "receive-to-result is local processing latency, not glass-to-glass"; `STALE 4.2 s` replaces the age chip when frames stop, and the stage keeps the last good frame marked stale instead of pretending to be live.
4. **A failure is stated in the panel that owns the action**, three times in one place: the stage line, the inspector `Start attempt` block (HTTP code + cause + remedy + Retry), and the strip chip. Never a distant toast that auto-clears.
5. **Async work is visible.** An overlay fetch in flight renders a skeleton segment in the strip and `overlays LOADING (1.6 s)` in the facts line, with the last painted layers kept visible and flagged stale. Requests are bounded: one in-flight fetch per frame, stale responses dropped by frame token.
6. **A save is acknowledged per artifact**: `✓ Saved · cue #29 pot @ frame 8100 · 1.2 s ago`, `✓ Saved · crop 18 ball 4 = C`, `✓ Saved · 6 anchors @ t 70.0`. A pending write shows a dim `·`, never a success word.
7. **Capability gating is visible**: controls a source cannot honour (anchors on a live channel, ball labels without the SAM3 detector) are hidden or disabled with the reason printed, never rendered as dead buttons.

---

## 6. Taste rules

| Rule | Why |
|---|---|
| **Layer chips, not panels.** Cloth / Balls / Persons / Pockets / Anchors / Events as chips above the stage. | The old design used four full panels for the same state; chips cost one row and remove the mode switch entirely. |
| **Hide what the source cannot do.** | Anchor calibration is `vod30`-only (`app.js:38`, `unified_server.py:667-668`); showing it on a live source is a lie with a button on it. |
| **Keyboard-first.** `space` play/freeze · `←/→` ±1 frame (Shift ±10) · `0–9` label · `U` unknown · `C` cue · `A`/`B` identity · `V` cycle verdict · `Tab` next detection · `⏎` commit. | The audit found no key reaches modes or tabs, and that `<video>` can eat the arrows. The strip prints the map so it is discoverable. |
| **One mono status line for all numbers.** | Numbers in Zilla Slab and Barlow had no tabular alignment and drifted between panels. |
| **EN / 中 parity for every new string.** | The Vision tab is bilingual; the audit's `15-zh-timeline-1280.png` shows `Unified viewer` untranslated and a mixed `["球","Pockets","Persons","Identity"]` overlay set. Every string added by this design ships in both languages (`Cues · 线索`, `Verdict · 判定`, `Start failed · 启动失败`, …). |
| **390 px = rails as a bottom sheet.** | Two sheets (Cues, Inspector) with a tab pair, stage pinned at the top at 16:9. No blank band above the fold. |
| **2 px radius, hairline borders, brass only for the active/primary thing.** | Matches the ops shell; keeps a dense screen readable at 72 controls. |

---

## 7. Engine decision

**Keep `annotator/app.js` as the single stage engine. Do not write a second one.**

`app.js` already owns the paths that matter and are tested:

- the **verified dirty/frame-request guard** (`state.dirty`, `state.busy`, `state.frame` token) that stops a late overlay response from painting over a newer frame — exactly the 0.36–7.55 s async hazard in finding 4;
- the **16 timeline tests** in `tests/test_app_timeline.js` (request contract, required labels, `data-mode="timeline"`, `app.html`/`app.css` assertions) that pin the request contract.

The redesign therefore:

1. **Deletes** `app.js`'s inner nav (`app.html:42-46`) and the `app.css:4-5` `[data-embedded] nav` rule, plus `visionNavigation()` and the dead `#vision-host-host` in `ops.js`.
2. **Adds a thin adapter** (`vision-stage`): a small module that renders the cues rail, layer chips and inspector from state, and calls the existing engine entry points (`activate('timeline')` semantics → `seek(frame)`, `freeze()`, `setOverlay(kind, on)`, `labelBall(k)`, `setSeed(track, role)`, `saveVerdict(...)`). The adapter owns no frame state and no fetch; it reads the engine's state and re-renders on change.
3. **Extends two engine behaviours**: an explicit `loading` state per overlay request (for the skeleton), and a per-artifact save receipt (`{kind, id, value, at}`) returned by the existing save paths (`POST /api/vod30/annotate`, `POST /api/balls/<set>/label`, `POST /api/vod30/anchors`, `POST /api/vod30/seeds`) so the inspector can print it.
4. **Retires** the duplicate overlay painter: live overlays (`ops.js:14`, green canvas rects from `X-Live-Metadata`) and frozen overlays (`app.js:271-295`, brass/red SVG from `/api/unified`) become one renderer fed by whichever source is active.

One engine, one stage, one coordinate system, one status line.

---

## 8. The eight audit findings and how each is resolved

*(These are the eight pins ①–⑧ on the mockup; the legend under the mockup carries the same mapping.)*

| Pin | Finding | Resolution |
|---|---|---|
| **①** | **Dead space / blank mobile landing** (§4.1, §4.9): ≈524 px blank band; `#content` at y=932; mobile first evidence at y=903 of an 844 px viewport | No landing screen, no second chrome block. The source chip row is the top of the Vision surface and the Cues rail is its first column: evidence at y≈88 both at 1280 px and at 390 px. |
| **②** | **Hidden-nav unreachability** (§2.3, §2.4): four of six sub-views need a devtools console | No subtabs to hide. Six modes become rails, layers and inspector states; every destination is a visible control. The `[data-embedded] nav` rule and `visionNavigation()` are deleted. |
| **③** | **Duplicate frame surfaces** (§4.4, §5): two copies of frame 150, disagreeing timecodes | Exactly one stage surface. One frame index printed in the stage chip and the facts line from one state field. |
| **④** | **Invisible live errors** (`13-live-start-error-1280.png`): failed `Start` shows only in a distant toast while the panel says `idle` | Failure stated in the owning panel: stage error line, inspector `Start attempt` block with HTTP code, cause, remedy and Retry, and the strip chip. |
| **⑤** | **False `OVERLAYS: none`** (`08-timeline-frozen-overlays-1280.png`): 19 nodes drawn, status says none | Status derived from layer state: `cloth 1 · balls 4 · persons 3 · pockets 6 · anchors 0 · overlays ON`. Hiding a layer changes the numbers and the word in the same render. |
| **⑥** | **No keyboard path** (§4.8, §7.1): no key reaches tabs or modes; `<video>` can double-consume arrows | One stage root owns every key; the stage uses no native `controls`, so nothing competes. Full map printed in the strip and the inspector. |
| **⑦** | **Async overlay latency** (§4.4): 0.36 s / 1.59 s / 7.55 s with no loading state | Skeleton segment in the strip, `overlays LOADING (1.6 s)` in the facts line, last painted layers kept and flagged stale, one in-flight fetch per frame with a frame token. |
| **⑧** | **No visible save confirmation** (finding 7): one generic string for every artifact | Per-artifact receipts with id, value and age; pending writes are dim, never a success word. |

*(Findings 3, 5, 6 and 10 from §1 are structural and are resolved by the layout itself: the review header is deleted (§3), six frame surfaces collapse to one (§2, rule 2), the event path is a cue card plus the inspector (§3, §6), and control density drops because the modes that produced it no longer exist. The mockup's annex lists all eight pinned findings with their evidence files.)*

---

## 9. Artifacts and how they were produced

| File | What |
|---|---|
| `out/vision-redesign/mockup.html` | Single self-contained static file: inline CSS, no CDN, no JS required. Loaded over `http://127.0.0.1:8143/` so the relative `<img src="../../out/scan30/evidence_t0*.jpg">` paths resolve. |
| `out/vision-redesign/desktop-A-vod-event.png` … `mobile-E-inspector.png` | 7 screenshots at 1280×900 (desktop) and 390×844 (mobile), captured with `agent-browser` 0.38.1. |
| `out/scan30/evidence_t00070.png` | Frame 2100 (t=70.0 s) extracted from `data/vod_30min_260815.mp4` for the Anchors state, because the six saved anchors in `out/pid_anchors_vod30.json` are stored for t=70 and line up exactly with that frame's pockets and cloth edges. |

Overlay geometry in the mockup is measured, not eyeballed: the cloth quad `532,323 → 800,324 → 997,569 → 384,563` is the calibrated pocket-anchor set, and every ball/person/event mark was placed by reading a coordinate grid over the actual frames. Screenshot command:

```bash
export PATH="$HOME/.local/share/npm/bin:$PATH"
export AGENT_BROWSER_SESSION="$(agent-browser session id --scope worktree --prefix vision-mockup)"
agent-browser set viewport 1280 900
agent-browser open "http://127.0.0.1:8143/out/vision-redesign/mockup.html"
agent-browser eval "(()=>{const v=document.querySelector('#A .viewport').getBoundingClientRect();window.scrollTo(0,v.top+window.scrollY-1);return 1})()"
agent-browser screenshot out/vision-redesign/desktop-A-vod-event.png   # state = A | B | B2 | C | D
agent-browser set viewport 390 844
# E1 = '#E .viewport'[0], E2 = '#E .viewport'[1]
```
