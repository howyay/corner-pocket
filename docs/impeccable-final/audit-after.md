# Audit — Corner Pocket front-end (`annotator/`), after the polish (step 4)

Branch `impeccable-polish` at `5db710d` (main `d527160` merged). Same method as `audit-before.md`:
source, rendered contrast, focus, names, payload, detector. Every number below was measured on
the fixture at `http://127.0.0.1:8137` (or a throwaway port where stated) on this commit.

## Audit Health Score

| # | Dimension | Before | After | Evidence |
|---|-----------|--------|-------|----------|
| 1 | Accessibility | 2 | **4** | Rendered contrast: 16 page×theme scans, 1,560 text elements, **0 below AA**, lowest 4.91:1 (was 15 sub-AA token pairs). Focus: **0** focusable elements without visible focus on 9 surfaces (was 17; the `a.brand` hit is a probe artefact, a real Tab outlines it). Names: 0 English-only accessible names in 中 (was 7 + glyph names); `role=tab`/`aria-selected`, `aria-pressed` on every toggle. Reduced motion measured. |
| 2 | Performance | 3 | **4** | Cold load vs pre-polish (`optimize/payload-summary.tsv`): EN Floor 878,789 → 516,955 B, EN Vision 1,183,338 → 841,269 B; third-party requests 11 → 0; `ops.css` 41,142 → 51,368 B (tokens, `@font-face` rules, the first-run and main's R-series rules), no per-glyph range. The one animated property is `transform` (was `width`). Not 4+: 3 unminified JS files (~276 KB), by the directive's no-reformat rule. |
| 3 | Responsive design | 2 | **4** | 0 horizontal overflow in all 180 final shots (1280/390 × EN/中 × dark/light). 390: the strip sits above the tab bar and the sheet above the strip (`--vs-strip-h` measured), the stagebar scrolls with an end fade; the first-run guide and overlay tags fit. |
| 4 | Theming | 2 | **4** | One token source (`ops.css :root` + `[data-theme=light]`), `color-scheme` per theme, 0 palette blocks in `app.css`; the stage keeps its own dark plate on purpose. Gated by `tests/test_palette_contrast.py` (5 tests). |
| 5 | Implementation integrity | 2 | **3** | `#ops-footer` selectors 219 → 0; conflicting redeclarations 13 → 0 (pixel-proven); dead tokens and empty rules gone; P-6 zip-derived hex 40 → 0. Still: 21 inline `style=` in `ops.js` (16 + 5 from main), one magic `max-height`. |
| **Total** | | **11/20** | **19/20** | **Excellent** |

## Detector (CLI, same four files)

27 → 16 findings (`detect-compare.txt`). Gone: `undersized-ui-text` (1), 8 `design-system-color`,
3 `design-system-font-size`, 1 `side-tab`. Remaining, each classified (none is a defect):

- `side-tab` ×6, `border-accent-on-rounded`: the provenance/live-note edges and the panel's brass top
  edge are DESIGN.md's own devices (recorded as false positives in step 1).
- `design-system-color` ×4: `#fff`/`#000`/`#999` in the **print** results sheet (main's R10, black on
  white is the point), the nav ball's highlight gradient, and `html` white **before CSS loads**.
- `low-contrast` ×1 (new): `#bdb0a1` on `#ffffff` is the loading line read before the stylesheet
  applies. With CSS the same line is `#bdb0a1` on `#16120f` (≈ 9:1) — measured in the browser.
- `design-system-font-size` ×2: the 9 px ball numeral; the dim 44 px end of the empty-board clamp
  (live/generate variant A), which is a display size, not a ramp step.
- `gpt-thin-border-wide-shadow` (`#message` floats; theme-aware `--shadow`), `monotonous-spacing`
  (measured on the unhydrated shell).

## Findings by severity (after)

- **P0**: none. **P1**: none.
- **P2**: 21 inline `style=` strings in `ops.js` (`ops.js` is edited only by unique anchors, never
  reformatted); `.vs-rail`/`.vs-inspector` `max-height: min(calc(100vh - 356px), 620px)`.
- **P3**: amber means *live/delayed* on club badges and *stale/CALIB* on Vision (a product decision,
  recorded in DESIGN.md); 4 user-typed rare hanzi (e.g. 鑫) outside the 3,500 common set still draw
  in a system CJK face (measured 28/32 web-only).

## Suites at this commit

`unittest` 1045 OK (skipped 36; 23 are Postgres tests, no `POOL_DATABASE_URL`), `node --test
tests/test_ops.js` 52/52, `node tests/test_app_timeline.js` 71 passed.
