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
| 5 | `extract` | — | — | pending (step 2, with colorize) | `extract/` |
| 6 | `critique` | Whole shell, 1280×900 + 390×844, EN/中, dark/light; baseline sets; source; detector CLI + in-page overlay on 12 tab×viewport scans. | **27/40** (Nielsen). Specific, not generic; debt is micro-type (302 undersized-text), sub-AA inks, mobile Vision sheet over the scrubber, invisible inspector focus, three pocket names per card. Degraded single-context run (no sub-agent tool), declared in the report. | Read-only. Report `out/impeccable/ledger/critique/critique-before.md`; snapshot `.impeccable/critique/2026-09-26T02-11-10Z__annotator-ops-html.md` (this commit). Re-run in step 4. | `critique/before-*`, `critique/browser-before/` |
| 7 | `audit` | Source (`annotator/*.css,*.js,*.html`), token contrast (96 pairs, both themes), served payload, detector findings. | **11/20** (Acceptable). P0 0 · P1 5 · P2 6 · P3 4. P1: 15 sub-AA token pairs, `.vs-field` no focus, duplicated drifting palette, Google Fonts dependency, mobile scrubber hidden. | Read-only. Report `out/impeccable/ledger/audit/audit-before.md`, `contrast-before.tsv`, `facts-before.txt`. Re-run in step 4. | `audit/before-*` |
| 8 | `polish` | — | — | pending (step 3) | `polish/` |
| 9 | `bolder` | — | — | pending (step 2, per surface with quieter) | `bolder/` |
| 10 | `quieter` | — | — | pending (step 2, per surface with bolder) | `quieter/` |
| 11 | `distill` | — | — | pending (step 2) | `distill/` |
| 12 | `harden` | — | — | pending (step 2) | `harden/` |
| 13 | `onboard` | — | — | pending (step 3) | `onboard/` |
| 14 | `animate` | — | — | pending (step 2, with delight) | `animate/` |
| 15 | `colorize` | — | — | pending (step 2, with extract) | `colorize/` |
| 16 | `typeset` | — | — | pending (step 2) | `typeset/` |
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
