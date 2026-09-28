---
target: Corner Pocket shell (ops.html)
total_score: 27
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:/home/operator/projects/pool-impeccable/annotator/ops.html"
target_fingerprint: "sha256:82f3e7b2c899591b7cc3b0eedd35201cf788e1d479e741580b7352c5fea3082a"
target_path: /home/operator/projects/pool-impeccable/annotator/ops.html
timestamp: 2026-09-26T02-11-10Z
slug: annotator-ops-html
---
⚠️ DEGRADED: single-context (no sub-agent tool is exposed to this PM worker; Assessment A was written from the baseline screenshots and source before the detector output was read, then Assessment B ran)

# Critique — Corner Pocket (`annotator/ops.html`, served at http://127.0.0.1:8137/), before the polish

Target: the whole shell (Floor, Set up, Matches, Vision, Regulars, Back room) at 1280×900 and 390×844, EN and 中, dark and light. Evidence: `out/impeccable/baseline/` (66 PNG online, 66 offline), `detect-before.json` (CLI, 27 findings), `browser-before/` (in-page overlay, 440 findings across 12 tab×viewport scans).

## Design Health Score

| # | Heuristic | Score | Key issue |
|---|-----------|-------|-----------|
| 1 | Visibility of system status | 3 | Status is everywhere and honest (LOCAL · SAVED · 0, NOT REVIEWED, stored-inference timestamp, facts line), but it is 9.5–10.5px mono in `--ink-dim`/`--ink-faint` (2.9–4.3:1), so it is present and hard to read. |
| 2 | Match system / real world | 3 | Pool vocabulary is right (frame, rack, pocket, cue ball numbers on the tabs). Pipeline jargon leaks into the operator's cards: "dense-track · trained 960×540 net @ ball@2", "quad drift vs saved corners 5.7 px (tol 40 px)", gate names like `cloth_occluded_at_disappearance`. |
| 3 | User control and freedom | 3 | Undo exists for club actions; a replay can be stopped; the cue verdict is a three-way choice with Save separate. Mobile sheet hides the frame strip, so the operator loses the scrubber while reviewing. |
| 4 | Consistency and standards | 2 | Two palettes (`ops.css` / `app.css`) that already drifted; 14 font sizes and 13 trackings; amber means "live" on Matches and "stale" on Vision; focus treatment split three ways; the fidelity-pass overrides re-declare 8 selectors. |
| 5 | Error prevention | 3 | Explicit confirms for destructive club actions; a GET never writes; forms validate "spaces alone don't count". The `.vs-field` inputs show no focus, so a keyboard user can type into the wrong field. |
| 6 | Recognition rather than recall | 3 | Tabs are numbered balls with labels; shortcuts are printed (SPACE play · ←/→ step…). The Vision layer chips (CLOTH BALLS PERSONS…) scroll off at 390px with no affordance, so the sixth is invisible. |
| 7 | Flexibility and efficiency | 3 | Keyboard shortcuts for review, chip filters, next-candidate. No density or text-size control for the 9–10px labels. |
| 8 | Aesthetic and minimalist design | 2 | The room-at-night look is specific and good; the Floor scoreboard is striking. But every label is uppercase tracked mono (all-caps-body flagged on 12/12 scans), the Vision rail repeats "machine-produced candidate; no human has confirmed it" on every card, and one pocket is named three ways on one card (right-middle, right-side, 148 mm right-side). |
| 9 | Help users recover from errors | 3 | Start failures show a block with the attempted source, the service's own sentence, a remedy and Retry. Remedy copy is generic ("Check that the source is a saved canonical Twitch channel, or that the allowlisted dataset media exists") even when the cause is known (channel offline). |
| 10 | Help and documentation | 2 | An empty club lands on Floor showing "Tables open" twice and 0/0, with no first step. There is no route from the empty state to Set up. |
| **Total** | | **27/40** | Good bones, significant consistency and legibility debt. |

## Design specificity verdict

**Specific.** Numbered pool-ball tabs, the slab-serif scoreboard, brass-on-walnut, the shot clock with its honesty caption ("local timer, not shared"), the MODEL / YOURS / CALIB provenance tags and the dashed "motion window only" cards could not be lifted into another product unchanged. The risk is not genericness; it is that the specific voice is rendered at sizes and contrasts that make it hard to read on a club floor.

## Overall impression

A distinctive, honest tool whose care shows in the copy (it never calls a replay live, never hides that a candidate is unconfirmed). It is let down by micro-type: 302 undersized-text findings, 60 low-contrast findings, and a mobile Vision layout that puts the review sheet over the scrubber. The fix is systemic (one type scale, one token source, AA inks), not a redesign.

## What's working

1. **Honesty as a design material.** Provenance is encoded in line style (dashed = model / motion-only, solid = confirmed) and in words; "Shot clock · local timer, not shared" and "Decorative table preview only — not a camera observation" are exemplary.
2. **The Floor scoreboard.** One huge slab headline per side, a brass shot-clock bar, and a quiet summary row; it reads across a room.
3. **Numbered ball navigation.** The six tabs are real pool balls in their real colours, so position and colour both carry meaning.

## Priority issues

1. **[P1] Micro-type everywhere.** What: 14 font sizes from 9 to 24px; functional labels at 9–10.5px (e.g. "POOL HALL OPERATIONS" 10.5px, "LOCAL · SAVED · 0" 10px, cue ids "#3"…"#12" 10px). Why: floor staff read this at arm's length under club lighting; the detector counts 302 undersized-text and 32 tiny-text instances. Fix: a 6-step type scale with an 11px floor for functional text and 12px for mono labels. Command: `typeset`.
2. **[P1] Inks below AA.** What: `--ink-dim` on panel 4.34:1 and on rail 3.97:1; `--ink-faint` 2.67–3.12:1 in dark and 2.52–3.25:1 in light; light `--brass` on bg 4.08:1. 15 of 96 token pairs fail. Why: these inks carry the status text (NOT REVIEWED, stored-inference time, placeholders). Fix: retune the ramps so every text/background pair is ≥4.5:1, and give the light theme its own complete set. Command: `colorize` + `extract`.
3. **[P1] Mobile Vision loses the scrubber.** What: at 390px the bottom sheet (Cues / Inspector) covers the frame strip; the layer chips run off the right edge with no scroll affordance. Why: the operator cannot step frames while reviewing on a phone. Command: `layout` + `adapt`.
4. **[P2] No visible focus in the inspector.** What: `.vs-field` inputs/selects have neither outline nor border change on focus (`ops.css:179` + `:309`). Why: keyboard review is a core flow. Command: `harden`.
5. **[P2] One pocket, three names; jargon on cards.** What: "right-middle (148 ± 54mm)", "148 mm right-side" and "right-side" on one card; "@ ball@2"; the facts line reads like a log. Command: `clarify`.

## Persona red flags

- **Floor staff, first night, empty club:** lands on Floor, sees "Tables open" twice and 0/0, and no hint that Set up comes first. (`onboard`)
- **Operator on a phone:** opens Vision, the sheet covers the frame strip; the sixth layer chip ("EVENTS") is cut off at the right edge. (`adapt`)
- **Keyboard-only operator:** tabs into the inspector and loses the caret; the EN|中 and ☾|☀ toggles do not announce their pressed state. (`harden`)
- **Club machine without internet:** web fonts never load; the slab scoreboard falls back to DejaVu Serif and the mono labels to DejaVu Sans Mono (baseline offline set). (`typeset`)

## Minor observations

- The Floor summary numbers use old-style figures ("0/0", "0") beside lining mono digits in the clock.
- The Vision source row at 390px wraps "live · twitch examplechannel" into two lines inside a chip.
- `radial-spotlight-glow` on the scoreboard is subtle and on-theme (lamp over the table); keep it.
- `gpt-thin-border-wide-shadow` on `#message` is a leftover of the fidelity pass (old `0 5px 30px` shadow survives).

## Questions to consider

- Could the Vision cue card lead with the one fact the operator decides on (pocket + time) and fold the pipeline provenance into a single line?
- Should the empty club open on Set up instead of Floor?
- What should the scoreboard say when no match is on the table, instead of "Tables open" twice?

Questions skipped: this critique runs inside a delegated PM worker with no user in the loop; the director's directive already fixes the command order.
