# Impeccable: the 24 commands

This is the command list the polish work is held to. It was read from the Impeccable repository, not from memory.

- Repository: https://github.com/pbakaus/impeccable. It was cloned to `/tmp/impeccable`, outside this repo.
- Commit: `9d715cc4f5564a990ca8345abfdd5df6dc9b41c8` (2026-09-24, "Keep skill-behavior advice checks from splitting sentences at filenames (#855)").
- Skill used: the DSH-native build `/tmp/impeccable/.dsh/skills/impeccable/SKILL.md`, `version: 4.4.0`, engine `scripts/VERSION` `0.1.6`.
- Source of truth: the `## Commands` table in that `SKILL.md`, lines 45–68. The table has **24 rows**.
- Cross-checks, all agreeing on the same 24 names:
  - `scripts/command-metadata.json` has 24 keys.
  - The upstream source `skill/SKILL.src.md` has the same 24 rows.
  - `README.md` has a section headed "### 24 Commands".

In the table, "Defined in" is the command's reference playbook. Its path is relative to `/tmp/impeccable/.dsh/skills/impeccable/`. Each row of the `SKILL.md` table links to that file, and the command's behaviour lives there.

| # | Command (as written in SKILL.md) | Category | One-line purpose (verbatim from SKILL.md) | Defined in |
|---|---|---|---|---|
| 1 | `craft [feature]` | Build | Deprecated alias for an ordinary new-work request | `reference/craft.md` |
| 2 | `shape [feature]` | Build | Plan UX/UI before writing code | `reference/shape.md` |
| 3 | `init` | Build | Capture durable product context in PRODUCT.md | `reference/init.md` |
| 4 | `document` | Build | Generate DESIGN.md from existing project code | `reference/document.md` |
| 5 | `extract [target]` | Build | Pull reusable tokens and components into design system | `reference/extract.md` |
| 6 | `critique [target]` | Evaluate | UX design review with heuristic scoring | `reference/critique.md` |
| 7 | `audit [target]` | Evaluate | Technical quality checks (a11y, perf, responsive) | `reference/audit.md` (native: `reference/audit.native.md`) |
| 8 | `polish [target]` | Refine | Final quality pass before shipping | `reference/polish.md` |
| 9 | `bolder [target]` | Refine | Amplify safe or bland designs | `reference/bolder.md` |
| 10 | `quieter [target]` | Refine | Tone down aggressive or overstimulating designs | `reference/quieter.md` |
| 11 | `distill [target]` | Refine | Strip to essence, remove complexity | `reference/distill.md` |
| 12 | `harden [target]` | Refine | Production-ready: errors, i18n, edge cases | `reference/harden.md` |
| 13 | `onboard [target]` | Refine | Design first-run flows, empty states, activation | `reference/onboard.md` |
| 14 | `animate [target]` | Enhance | Add purposeful animations and motion | `reference/animate.md` |
| 15 | `colorize [target]` | Enhance | Add strategic color to monochromatic UIs | `reference/colorize.md` |
| 16 | `typeset [target]` | Enhance | Improve typography hierarchy and fonts | `reference/typeset.md` |
| 17 | `layout [target]` | Enhance | Fix spacing, rhythm, and visual hierarchy | `reference/layout.md` |
| 18 | `delight [target]` | Enhance | Add personality and memorable touches | `reference/delight.md` |
| 19 | `overdrive [target]` | Enhance | Push past conventional limits | `reference/overdrive.md` |
| 20 | `clarify [target]` | Fix | Improve UX copy, labels, and error messages | `reference/clarify.md` |
| 21 | `adapt [target]` | Fix | Adapt for different devices and screen sizes | `reference/adapt.md` (native: `reference/adapt.native.md`) |
| 22 | `optimize [target]` | Fix | Diagnose and fix UI performance | `reference/optimize.md` |
| 23 | `live` | Iterate | Visual variant mode: pick elements in the browser, iterate on alternatives | `reference/live.md` |
| 24 | `generate [n] [action] [element]` | Iterate | Variants, versions, or alternatives of a named element to choose from in the live browser; no manual picking | `reference/generate.md` |

## Aliases and non-command verbs

These come from `SKILL.md` lines 70–85.

- **`teach` is an alias of `init`.** Line 76 says: "`teach` aliases `init`." The directive's "teach" context step is therefore `init`, which writes `PRODUCT.md`.
- **`craft` is deprecated.** Line 76 says: "`craft` is a deprecated alias for ordinary new-work and adds nothing." Its reference, `reference/craft.md`, is 5 lines long and points to `reference/new-work.md`. The ledger records `craft` as mapped to the new-work path.
- **`shape`**, per line 76, "owns task discovery, then enters new-work only for visual-world and surface-concept decisions."
- **Not among the 24:** `pin`/`unpin`, `hooks` and `doctor`. These are housekeeping verbs, on lines 80, 82 and 84. They are not rows of the Commands table.
- **Setup is not a command.** Setup (`SKILL.md` line 20) says to run `scripts/impeccable context` once per session. It loads `PRODUCT.md`, `DESIGN.md` and the surface brief. Then, before any UI edit, it says to read `reference/craft-floor.md`, the quality floor.

## How "all 24 used" is evidenced

`docs/impeccable-ledger.md` has one row per command. Each row records:

- what the command inspected;
- what it decided;
- the commit(s) it produced, or `no-op` with a reason;
- before and after screenshots.

There are three special cases:

- **Contradictory pairs are both run as diagnoses.** For `bolder` and `quieter`, the ledger says where each one applied.
- **`live` and `generate`** run against the loopback fixture if their scripts work here. If not, the ledger records the exact error and the equivalent manual variants.
- **`critique` and `audit`** also run as a self-check before every blind-rating round. Their outputs are saved.
