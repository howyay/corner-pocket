---
target: Corner Pocket shell (ops.html), after the polish
total_score: 37
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 0
target_identity: "file:/home/operator/projects/pool-impeccable/annotator/ops.html"
target_fingerprint: "sha256:faf6b69b621d6d9a8d32344b4824279591fda0efb037d8646c46b603a5c3803f"
target_path: /home/operator/projects/pool-impeccable/annotator/ops.html
timestamp: 2026-09-26T08-55-47Z
slug: annotator-ops-html
---
⚠️ DEGRADED: single-context (no sub-agent tool is exposed to this PM worker; Assessment A was written from the final screenshot set before the detector output was re-read, then Assessment B compared the measurements)

# Critique — Corner Pocket (`annotator/ops.html`, served at http://127.0.0.1:8137/), after the polish

Target: the whole shell (Floor, Set up, Matches, Vision, Regulars, Back room) at 1280×900 and 390×844, EN and 中, dark and light, on branch `impeccable-polish` at `5f13a8c` (main `d527160` merged). Evidence: `out/impeccable/final/{dark,light}/` (180 PNG, 0 horizontal overflow), rendered contrast (16 scans, 1,560 text elements, 0 below AA, lowest 4.91:1), focus probe (0 focusable elements without visible focus on 9 surfaces), CLI detector 27 → 16 findings (`ledger/audit/detect-compare.txt`), overlay tags 25 overlapping pairs → 0, cold payload EN Floor 878,789 → 516,955 B with 0 third-party requests.

## Design Health Score

| # | Heuristic | Before | After | Key issue now |
|---|-----------|--------|-------|---------------|
| 1 | Visibility of system status | 3 | 4 | Status is honest and now legible: every status line is ≥ 11 px at AA; the clock turns red in its last 5 s and the bar follows it; messages arrive where they are seen; the Anchors chip says what is drawn. |
| 2 | Match system / real world | 3 | 4 | One pocket vocabulary (`148 ± 54 mm · right-middle`, 中 `右中`), gate reasons in words with their code kept as evidence, colours as words, the frame time in the cards' m:ss.d. The detector name (`dense-track · trained 960×540 net @ ball@2`) is still machine language, by design (provenance). |
| 3 | User control and freedom | 3 | 4 | On a phone the scrub strip is above the tabs and the sheet stops at the stage; saved VODs can be removed; the empty-id VOD click says what to do. |
| 4 | Consistency and standards | 2 | 4 | One token source, six type sizes, a seven-step spacing scale, one focus treatment, one pocket name. Open on purpose: amber means *live/delayed* on club badges and *stale/CALIB* on Vision. |
| 5 | Error prevention | 3 | 4 | Every field shows focus; the arrow keys nudge only a selected box or anchor; nothing starts on its own (a saved VOD fills the form, the operator starts it). |
| 6 | Recognition rather than recall | 3 | 4 | The key map lists every working shortcut; the layer chips show state as shape (pip + underline) and the row signals that it scrolls; the empty club sees its three steps. |
| 7 | Flexibility and efficiency | 3 | 3 | Shortcuts are complete and listed; still no density or text-size control, and the phone has no key map (no hardware keyboard). |
| 8 | Aesthetic and minimalist design | 2 | 3 | The room-at-night look is intact and quieter where it shouted (empty rounds, empty board placeholder); overlay tags no longer overprint. Still dense: the per-card provenance line repeats on every card, which is the product's honesty rule. |
| 9 | Help users recover from errors | 3 | 3 | Refusals are bilingual and specific; the start-failure remedy is still generic when the cause is known (channel offline). |
| 10 | Help and documentation | 2 | 4 | A first-run guide on the Floor from real state (steps tick, the guide leaves once the draw exists); the key map is complete; DESIGN.md and PRODUCT.md are re-documented from the shipped code. |
| **Total** | | **27/40** | **37/40** | Good bones, now consistent and legible. |

## Design specificity verdict

**Specific, and more so.** The numbered pool-ball tabs, the slab scoreboard, brass on walnut, the honest shot-clock caption and the MODEL/YOURS/CALIB provenance all survive; the polish removed noise and drift rather than adding a style. Nothing reads as a template.

## What's working

1. **Honesty is now also legible.** The provenance rules (dashed MODEL, solid YOURS, CALIB, replay never "live") were right before; now their text meets AA in both themes and never overprints.
2. **The Floor on a first night.** The guide turns an empty board into three concrete steps, and the board's placeholder no longer shouts "Tables open" twice at 80 px.
3. **The phone review loop.** Stage, sheet, scrub strip and tabs stack without covering each other (0 px overlap measured), in EN and 中.

## Priority issues

1. **[P2] Inline one-offs in `ops.js`.** 21 `style=` strings (16 + 5 from main's R-series) and the `min(calc(100vh - 356px), 620px)` rail height. Why: they escape the spacing scale. Fix: move them into `ops.css` classes when `ops.js` is next refactored (the polish edits it by unique anchors only). Command: `layout`.
2. **[P3] Start-failure remedy is generic.** Why: when the cause is known (channel offline), the remedy should name it. Command: `clarify`.
3. **[P3] Amber has two meanings.** A product decision (PRODUCT.md), not a polish; recorded in DESIGN.md.
4. **[P3] Rare user-typed hanzi.** 4 of 32 measured elements with user CJK (e.g. 鑫) fall back to a system CJK face for that glyph. Fix, if it matters: a per-event subset or a fuller third file. Command: `typeset`.

## Persona red flags (re-checked)

- **Floor staff, first night:** resolved — the guide names the three steps and ticks them.
- **Operator on a phone:** resolved — strip and stage visible with either sheet open; the layer row fades its clipped end.
- **Keyboard-only operator:** resolved — visible focus everywhere, pressed/selected states announced, bilingual names.
- **Club machine without internet:** resolved — self-hosted fonts; 0 third-party requests.

## Minor observations

- The per-card provenance sentence (`machine-produced candidate; no human has confirmed it`) repeats on every card; it is the product's honesty rule, so it stays, but it is the densest line on the rail.
- `overdrive` was not built: its playbook needs the user's pick among three recorded directions.

## Questions to consider

- Should the Floor clock move to main's shared server clock (`annotator/shot_clock.py`) now that it exists?
- Which overdrive direction, if any: instant optimistic bracket (recommended), View-Transitions cue → stage, or a whole-night density scrub?
