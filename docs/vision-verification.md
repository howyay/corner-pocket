# Vision tab — independent re-verification (round 2)

Date: 2026-02-14 · verifier: independent worker (no product code edited)
Fixture: `PYTHONPATH=. .venv/bin/python tests/serve_workbench_fixture.py` → `http://127.0.0.1:8131` (copied data, loopback)
Browser: `agent-browser session id --scope worktree --prefix vision-reverify` → `vision-reverify-521027f9b1ad`, viewport 1440×1000 (automated clicks need it; see note 4)
Commits under test: `a4738ba`, `6ef2e2c`, `50e3ae7` (rebuild) + `f101d67`, `d77d4df` (fixes)
Baseline: `docs/vision-redesign-outline.md` · prior audit: `docs/vision-audit.md`
Purpose: test the implementer's claims rather than accept them. Four checks, measured values only.

## Measured results

| # | Check | Claim | Measured | Verdict |
|---|-------|-------|----------|---------|
| 1 | Console clean while driving Vision (load → layer chips → start live → stop live → click a cue) | 0 | **0 errors, 0 warnings, 0 page errors** in one full drive; **0/0** again on a second clean load + 2 language switches. Capture proven live (a deliberate `console.warn`/`console.error` probe showed up as `[warning]`/`[error]`, then cleared) | PASS |
| 2 | Real key presses: Space, ←, →, 0, U, C, A, B, V | all bound, arrows not double-consumed | Space = play⇄pause (frame 197→200 while playing, 0 drift when paused). ←/→ = exactly −1/+1 when paused (199→200→199). 0/U/C, A/B, V = no visible change in the states reachable; each prints a precondition notice (中: `请先选择球或裁剪图。` for 0/U/C, `请先选择可见的轨迹。` for A/B). Arrows while an input owns focus: frame did **not** move (`#vs-scrub` 50→50→50, `#vs-frame-index` 50→50→50); when focus is on `#vs-cues` / `#review-root` / body: ±1 exactly. No double consumption | PASS (with one gap, below) |
| 3 | 中 mode Latin state-word residue + `⏎ 保存` glyph | 0 hits, U+23CE | `#vision-surface` innerText 3 544 chars, regex `idle\|starting\|running\|stopping\|stopped\|eos\|error\|failed\|completed` (case-insensitive) = **0 hits**. Live states render 运行中 / 已停止. Glyph after `·` is `⏎` = **U+23CE** (verified by codepoint, not by eye) | PASS |
| 4 | Facts-line provenance vs SVG nodes, on a frame with a manual correction | `cloth 1 (+1 manual) · balls 6 (+10 manual) · persons 4 (+4 manual)`, 14 manual boxes + polygon | Facts line (frame 0): **`cloth 1 (+1 manual) · balls 6 (+10 manual) · persons 4 (+4 manual) · pockets 6 · anchors 0 · events 0`**. SVG: solid/manual = `g.t-box` **14** + `polygon.t-poly` **1** = **15**; dashed/auto = `polygon.u-cloth` **1** + `g.u-ball` **6** + `g.u-person` **4** + `g.u-pocket` **6** = **17**. Manual 15 = 1+10+4 ✓; model 17 = 1+6+4+6 ✓. Reproduced twice (EN and 中, after two independent loads). Provenance split confirmed by computed style: `t-*` `stroke-dasharray: none` (solid, `data-boxes="manual"`), `u-*` dashed (7px 6px / 10px 7px / 12px 8px) | PASS |

Overlays take **~25 s** to reach `overlays ON` on a fresh load (`overlays LOADING (23.1 s)` observed); the earlier frames of that window are not failures.

## Verdicts

1. **Console — PASS.** Zero real console output and zero page errors across a full Vision drive and a second clean load. The counter is trustworthy: an injected `console.warn`/`console.error` pair was captured, then cleared before the measured session.
2. **Keyboard — PASS on the parts that matter, one gap.** Space and ←/→ are genuinely bound and correct; the audit's double-consumption bug is **not reproducible**: with focus inside `#vs-scrub` or `#vs-frame-index` the frame index does not move at all, and with focus on the rail/root the app steps exactly one frame. Note the Vision stage is an `<img id="t-img">`, not a `<video>`, so the exact old failure path (a `<video>` swallowing arrows) no longer exists in this DOM. **Gap:** I could not reach a state with a ball/crop or track selected (the crop queue sits at y≈3006, below the inspector's scroll fold), so whether 0/U/C/A/B/V *act* versus merely print a precondition notice is untested — what I measured is that they never act silently.
3. **中 mode — PASS with one residue.** The live-state vocabulary is fully translated (运行中 / 已停止) and the regex scan is clean. The only untranslated English that is not an identifier is a **stale notice string that survives a language switch**: press A in EN (`Select a visible track first.`), switch to 中 — the notice still reads English (`.vs-notice.error`, visible). Fresh notices in 中 are Chinese, so the dictionary is correct; the already-rendered string is not re-localized. See `verify2-zh-stale-notice.png`.
4. **Facts-line provenance — PASS.** The numbers agree with the DOM exactly, in both directions, and the solid/dashed split is a real style rule, not a coincidence of counts. Claim reproduced verbatim.

## Other English left in 中 mode (classified)

Legitimate — dataset ids `vod30`, `highlight`; platform/channel `twitch`, `examplechannel`; units `VOD30`, `S`, `FPS`, `mm`, `t`/`s` in the frame line; keycap glyphs `U C A B V` (they are keys, not words); pocket names `foot-right`, `left-side`, `head-left`, `head-right`, `foot-left`, `right-side`; 79 crop filenames `t00005_b00.jpg` ….

Genuine — exactly one: the stale notice described in verdict 3.

## Observed but outside the four checks

- `#vs-scrub` is `<input type="range" min="0" max="0" value="0">` and **never tracks the frame** (`max="0"` measured while the stage sat at frame 51; value unchanged during playback). It is wired to `seek()` on change, but with `max=0` it can never move — a dead control next to a working `#vs-frame-index`.
- After a live start/stop cycle the model layer does **not** come back when the VOD dataset is re-picked: frame 0 then reads `balls 0 (+10 manual) · persons 0 (+4 manual)` while the SVG keeps `u-pocket`/`u-cloth` only. A page reload restores `balls 6 · persons 4`. Measured twice, before and after the live run.
- Starting from the saved Twitch chip returns `400 Select a saved canonical Twitch channel` (fixture has no canonical Twitch source). The failure is surfaced (`.vs-error-block` + toast + retry button), but the status line simultaneously reads `idle` rather than a failed state.
- At 1280×599 the live panel's Start button lies below the inspector's scroll fold; a bare click at its centre lands on `.vs-grid`. Scrolling (or a taller viewport) fixes it — a reachability artefact of the short viewport, not a product defect.

## Not tested

- Whether 0 / U / C / A / B / V mutate data once their preconditions (selected ball or crop, selected track, selected event) are met — see verdict 2. Everything I could reach produced only a precondition notice; I did not observe a wrong write.
- Mobile/sheet layout, the anchors flow, verdict saving to the API, and any Twitch path that needs a real stream.
- The implementer's claimed test suites (python 168, timeline 21, ops 21) — this round is browser-side only; CI/test numbers are their claim, not re-run here.

## Evidence

`out/vision-redesign/verify2-provenance.png` (first read) · `verify2-en-provenance.png`, `verify2-zh-provenance.png` (facts line + stage at 1440×1000, EN and 中) · `verify2-zh-surface.png` (中 surface) · `verify2-zh-stale-notice.png` (stale English notice in 中).
