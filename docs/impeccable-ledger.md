# Impeccable ledger — Corner Pocket polish

One row per Impeccable command (v4.4.0 @ `9d715cc`, `docs/impeccable-commands.md`). Each row says
what the command inspected, what it decided, and the commit(s) it produced or why it was a no-op.
Screenshots for a row live in `out/impeccable/ledger/<cmd>/` (untracked; `out/` is gitignored):
`before-*` from the baseline or the state before the command, `after-*` from the fixture after it.

Worktree `/home/operator/projects/pool-impeccable`, branch `impeccable-polish`. Fixture
`http://127.0.0.1:8137/` (systemd user unit `impeccable-fixture-8137`). Every commit keeps the
three suites at or above the post-merge floor: unittest 944 OK (skipped=13), `test_ops.js`
35/35, `test_app_timeline.js` 65/0.

## Pre-polish record (step 0)

| Commit | What |
|---|---|
| `90438ac` | `git merge main` (main `5425404`, 36 commits: D1–D10, rating fix, form fixes D2–D4d) |
| `ede4052` | Fixture resolves saved Twitch channels from its own state (throwaway `:8141` check) |
| `541fac5` | Baseline doc: online/offline screenshot sets (66 + 66 PNG, 0 overflow, 0 errors) |
| `e383d37` | Baseline doc: suite counts after the merge (944/35/65) |

## Commands

| # | Command | Inspected | Decided | Commit(s) / no-op reason | Shots |
|---|---|---|---|---|---|
| 1 | `craft` | — | Deprecated alias for new-work (SKILL.md l.76); nothing to build that the other rows do not cover. | pending (step 3) | `craft/` |
| 2 | `shape` | — | — | pending (step 3) | `shape/` |
| 3 | `init` | `PRODUCT.md` (committed `f2f0e45` before this ledger) | Product context exists; step 3 records whether any fact changed. | pending (step 3) | `init/` |
| 4 | `document` | `DESIGN.md` + `.impeccable/design.json` (`aa2ed2d`…`7bcfd72`) | Design system recorded as-is; its "Recorded inconsistencies" drive step 2. | pending (step 3: re-document after the polish) | `document/` |
| 5 | `extract` | Token sources: `ops.css` `:root` (2 blocks) + a second "fidelity pass" `:root` pair (`--code-*`, `--track`, `--thumb`) + `app.css` `#review-root` (a full duplicate palette, both themes, already drifted: no `--blue*`, `--live-bg`, `--neutral-bg`; its own `color-scheme`; themed by a separate attribute). 40 rules with literal colours (`literals-before.tsv`). | **One token source**: `ops.css` `:root` / `:root[data-theme=light]`. `app.css` keeps no palette (its 27 token lines removed; `#review-root` inherits). The second `:root` pair is removed (`--code-*` were unused; `--track`/`--thumb` now alias `--panel2`/`--btn-line`). New semantic roles instead of literals: `--red-bg`/`--red-ink` (error receipts), `--shadow`, `--scrim`, the `--stage-*` set for everything drawn on the always-dark video frame, and object colours `--ball*`, `--rail-wood`, `--diamond` (depictions of physical things, theme-independent). 0 colour literals left in `app.css`; in `ops.css` only the token blocks and one white highlight gradient on the nav balls. Also: `color-scheme` now on `:root` in both themes (was only on `#review-root`). | this commit (with colorize) | `colorize/` (shared) |
| 6 | `critique` | Whole shell, 1280×900 + 390×844, EN/中, dark/light; baseline sets; source; detector CLI + in-page overlay on 12 tab×viewport scans. | **27/40** (Nielsen). Specific, not generic; debt is micro-type (302 undersized-text), sub-AA inks, mobile Vision sheet over the scrubber, invisible inspector focus, three pocket names per card. Degraded single-context run (no sub-agent tool), declared in the report. | Read-only. Report `out/impeccable/ledger/critique/critique-before.md`; snapshot `.impeccable/critique/2026-09-26T02-11-10Z__annotator-ops-html.md` (this commit). Re-run in step 4. | `critique/before-*`, `critique/browser-before/` |
| 7 | `audit` | Source (`annotator/*.css,*.js,*.html`), token contrast (96 pairs, both themes), served payload, detector findings. | **11/20** (Acceptable). P0 0 · P1 5 · P2 6 · P3 4. P1: 15 sub-AA token pairs, `.vs-field` no focus, duplicated drifting palette, Google Fonts dependency, mobile scrubber hidden. | Read-only. Report `out/impeccable/ledger/audit/audit-before.md`, `contrast-before.tsv`, `facts-before.txt`. Re-run in step 4. | `audit/before-*` |
| 8 | `polish` | — | — | pending (step 3) | `polish/` |
| 9 | `bolder` | — | — | pending (step 2, per surface with quieter) | `bolder/` |
| 10 | `quieter` | — | — | pending (step 2, per surface with bolder) | `quieter/` |
| 11 | `distill` | — | — | pending (step 2) | `distill/` |
| 12 | `harden` | — | — | pending (step 2) | `harden/` |
| 13 | `onboard` | — | — | pending (step 3) | `onboard/` |
| 14 | `animate` | — | — | pending (step 2, with delight) | `animate/` |
| 15 | `colorize` | Palette roles and contrast: 15 of 96 token text/surface pairs below 4.5:1 (`audit/contrast-before.tsv`); light theme incomplete (theme-aware inks on fixed dark stage plates at ~2.7–3.1:1, hard-coded dark error receipts); 40 hex values from the redesign zip (security audit **P-6**). | **Own palette, derived in OKLCH** (`out/impeccable/palette.js`): walnut neutrals h≈60, brass h≈88, felt green h≈155, chalk blue h≈240, amber h≈70, red h≈30; light = daylight on the same wood, not an inversion. Restrained dosage: brass stays the one action/selection colour; status hues only on status. **P-6:** `git grep -niFf <40 values> -- annotator/` → **0** (the last one was the SVG favicon background). **Contrast, measured:** token gate 165 pairs, 0 fails (text ≥4.5:1 in both themes, control borders and focus ≥3:1, stage labels 6.9–17.7:1) → `contrast-after.tsv`; **rendered in the browser**, every visible text element on every tab + modal + Vision panels, dark and light: 1,562 elements, **0 below AA**, minimum 4.91:1 → `rendered-after/`. Stage: inside `#t-overlay` the accent tokens resolve to the dark-frame accents, so light theme never draws dark brass/red on the picture. | this commit | `colorize/after/` (dark), `colorize/after-light/` |
| 16 | `typeset` | Faces the browser loads (`document.fonts`, every tab, EN + 中): Zilla Slab 400/400i/500/600, Barlow 400/500, DM Mono 400/500, Noto Sans SC 400/500, Noto Serif SC 400/500/700 (中 only). 94 font-size declarations, 19 px values 9–24 (`font-decls-before.tsv`). Offline baseline: every face fell back to DejaVu/Liberation. | **Self-host** the used faces plus Barlow 600/700 (plain `<strong>` in rosters and match rows, unseen in the empty fixture) as 15 woff2 in `annotator/fonts/`: 722,720 B total (Latin 8–15 KB each; CJK 100–132 KB each, subset to 853 code points = the Chinese copy of `ops.js`, `vision-stage.js`, `app.js`, both HTML files, plus the arrows/symbols Barlow and DM Mono lack). Regenerate: `annotator/fonts/build_fonts.py` (sources pinned to google/fonts `23e54b5`). OFL texts `OFL-*.txt` alongside; Noto Sans SC's RFN "Source" is not used in any font name. All `fonts.googleapis.com`/`gstatic` links removed (`ops.html`; `app.html`'s head link never loaded, the page is only parsed for `#review-root`). `ops.html` preloads Barlow 400 + DM Mono 400. **Type scale** `--fs-xs 11 / sm 12 / md 13 / body 15 / lg 17 / xl 20` (+ the fluid scoreboard clamps): 11px functional floor, tracked uppercase mono labels at 12. 79 of 94 declarations now use a token; the 15 left are fluid `clamp()`s, the ball numerals (glyphs in a 15–16px disc) and the SVG overlay text (viewBox units). **Server:** `unified_server.py` gains one route, `/fonts/<name>.woff2|.txt`, through `safe_file` (flat directory; `.py`, unknown and nested names 404); test added. | this commit | `typeset/before-*`, `typeset/after-*`, `typeset/after/` (70 PNG, 0 overflow, 0 errors) |
| 17 | `layout` | — | — | pending (step 2, with adapt) | `layout/` |
| 18 | `delight` | — | — | pending (step 2, with animate) | `delight/` |
| 19 | `overdrive` | — | — | pending (step 3) | `overdrive/` |
| 20 | `clarify` | — | — | pending (step 3) | `clarify/` |
| 21 | `adapt` | — | — | pending (step 2, with layout) | `adapt/` |
| 22 | `optimize` | — | — | pending (step 2) | `optimize/` |
| 23 | `live` | — | — | pending (step 3) | `live/` |
| 24 | `generate` | — | — | pending (step 3) | `generate/` |

## Step 1 detail: what critique and audit hand to the later commands

| Finding (source) | Owner command |
|---|---|
| 14 font sizes 9–24px, 302 in-page undersized-text; fonts from `fonts.googleapis.com` (offline → DejaVu/Liberation) | `typeset` |
| 15/96 token pairs < 4.5:1; two drifting palettes; light theme incomplete; 40 zip-derived hex (P-6) | `colorize` + `extract` |
| 390px: sheet covers the frame strip; layer chips overflow without affordance; spacing steps by 1–2px | `layout` + `adapt` |
| `.vs-field` no focus (`ops.css:179`, `:309`); no `role=tab`/`aria-pressed`; 7 English-only names; global motion kill | `harden` |
| 219 dead `#ops-footer` selectors; unused `--code-*`; 13 fidelity-pass overrides; `#message` stale shadow | `distill` |
| 7 `border-left` accents (some provenance, some decoration); scoreboard glow | `bolder` / `quieter` |
| Reduced motion kills state-bearing motion (clock bar, playing badge) | `animate` / `delight` |
| 331 KB unminified JS/CSS + 236 font requests | `optimize` |
| Three pocket names per card; pipeline jargon; facts-line wording; empty club lands on "Tables open" ×2 | `clarify`, `onboard` |

Detector false positives kept as-is (recorded in the audit report): cloth swatches and rail colour
(physical depictions), dashed/solid provenance edges (`side-tab`), scoreboard lamp glow.
