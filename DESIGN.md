---
version: alpha
name: Corner Pocket
description: "Pool hall operations and vision review: one dark walnut-and-brass instrument, bilingual EN / 中."
colors:
  # One token source: annotator/ops.css `:root` (dark, the default) and
  # `:root[data-theme=light]`, OKLCH-derived and gated for contrast by
  # tests/test_palette_contrast.py. app.css holds no palette: the stage remaps
  # these under #t-overlay. Values below are the dark theme; each comment gives
  # the token and its light value (stage-* and ball* are the same in both themes).
  walnut-night: "#16120f"             # --bg; light #eee7dc
  felt-panel: "#1c1814"               # --panel; light #faf6ef
  pocket-well: "#110e0b"              # --panel2; light #fefcf8
  rail-wood: "#251f1b"                # --rail; light #e9e2d6
  seam: "#2f2923"                     # --line; light #d5cbbb
  seam-soft: "#29231f"                # --line2; light #e0d8cb
  button-rim: "#73665b"               # --btn-line; light #938470
  chalk-bright: "#f6f3ec"             # --ink-hi; light #1a120a
  chalk: "#efe9de"                    # --ink; light #251e15
  cue-shaft: "#bdb0a1"                # --ink-mid; light #564b3e
  worn-leather: "#a6998a"             # --ink-dim; light #665a4d
  old-varnish: "#968a7d"              # --ink-faint; light #6d6153
  rail-brass: "#cca632"               # --brass; light #755706
  polished-brass: "#e3cb7e"           # --brass-hi; light #624902
  brass-hover: "#dbb64c"              # --brass-hover; light #866617
  brass-ink: "#15110c"                # --brass-fg; light #fcfaf4
  pip-off: "#312a24"                  # --pip-off; light #d9d0c1
  baize-green: "#85ca9d"              # --green; light #296944
  baize-green-bg: "#122219"           # --green-bg; light #daebdf
  baize-green-line: "#355643"         # --green-line; light #a5c4ae
  chalk-blue: "#90b8d5"               # --blue; light #255b7d
  chalk-blue-bg: "#151e25"            # --blue-bg; light #dce8f1
  chalk-blue-line: "#354d61"          # --blue-line; light #a7becf
  lamp-amber: "#ebae51"               # --amber; light #804d0c
  lamp-amber-bg: "#291e10"            # --amber-bg; light #f8e9d2
  lamp-amber-line: "#684d21"          # --amber-line; light #d6b98a
  red-ball: "#e87a69"                 # --red; light #9a3326
  error-wash: "#361a16"               # --red-bg; light #fde3de
  error-ink: "#fdcac0"                # --red-ink; light #7c271c
  live-glow-bg: "#251c11"             # --live-bg; light #f6ecd7
  neutral-bg: "#181411"               # --neutral-bg; light #efeae2
  lamp-haze: "rgba(240,214,150,.08)"  # --lamp; light rgba(255,206,110,.2)
  scroll-track: "var(--panel2)"       # --track; same in both themes
  scroll-thumb: "var(--btn-line)"     # --thumb; same in both themes
  drop-shadow: "rgba(0,0,0,.45)"      # --shadow; light rgba(60,40,15,.18)
  modal-scrim: "rgba(8,6,4,.62)"      # --scrim; light rgba(40,30,18,.45)
  stage-bg: "#0b0907"                 # --stage-bg; same in both themes
  stage-plate: "#100c0acc"            # --stage-plate; same in both themes
  stage-note: "#100c0aee"             # --stage-note; same in both themes
  stage-ink: "#faf1dc"                # --stage-ink; same in both themes
  stage-ink-hi: "#fbedb8"             # --stage-ink-hi; same in both themes
  stage-mark: "#1f160f"               # --stage-mark; same in both themes
  stage-event: "#f2b7ad"              # --stage-event; same in both themes
  stage-bound: "#9bdcb1"              # --stage-bound; same in both themes
  stage-halo: "#0b090799"             # --stage-halo; same in both themes
  stage-brass: "#cca632"              # --stage-brass; same in both themes
  stage-brass-hi: "#e3cb7e"           # --stage-brass-hi; same in both themes
  stage-green: "#85ca9d"              # --stage-green; same in both themes
  stage-amber: "#ebae51"              # --stage-amber; same in both themes
  stage-red: "#e87a69"                # --stage-red; same in both themes
  ball: "#cfa72b"                     # --ball; same in both themes
  ball-hi: "#eed780"                  # --ball-hi; same in both themes
  ball-edge: "rgba(0,0,0,.4)"         # --ball-edge; same in both themes
  ball-face: "#f7f3eb"                # --ball-face; same in both themes
  ball-num: "#15110c"                 # --ball-num; same in both themes
  ball-black: "#13100e"               # --ball-black; same in both themes
  ball-black-hi: "#47413c"            # --ball-black-hi; same in both themes
  preview-rail-wood: "#552d1b"        # --rail-wood; same in both themes
  diamond: "#e4cc84"                  # --diamond; same in both themes
typography:
  # The UI type ramp (annotator/ops.css :root): --fs-xs 11px, --fs-sm 12px, --fs-md 13px,
  # --fs-body 15px, --fs-lg 17px, --fs-xl 20px; display sizes are clamp()s below.
  display:
    fontFamily: "Zilla Slab, Noto Serif SC, Georgia, serif"
    fontSize: "clamp(34px, 5.8vw, 80px)"
    fontWeight: 500
    lineHeight: 1.02
    letterSpacing: "-0.01em"
  numeral:
    fontFamily: "Zilla Slab, Noto Serif SC, Georgia, serif"
    fontSize: "clamp(52px, 7.2vw, 110px)"
    fontWeight: 500
    lineHeight: 0.9
  clock:
    fontFamily: "DM Mono, Noto Sans SC, monospace"
    fontSize: "clamp(36px, 4.4vw, 60px)"
    fontWeight: 500
    lineHeight: 1
    fontFeature: "tnum"
  headline:
    fontFamily: "Zilla Slab, Noto Serif SC, Georgia, serif"
    fontSize: "clamp(28px, 3.2vw, 38px)"
    fontWeight: 400
    lineHeight: 1.1
  title:
    fontFamily: "Zilla Slab, Noto Serif SC, Georgia, serif"
    fontSize: "20px"
    fontWeight: 600
  panel-heading:
    fontFamily: "Zilla Slab, Noto Serif SC, Georgia, serif"
    fontSize: "13.5px"
    fontWeight: 600
    letterSpacing: "0.02em"
  body:
    fontFamily: "Barlow, Noto Sans SC, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  body-compact:
    fontFamily: "Barlow, Noto Sans SC, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 400
  data:
    fontFamily: "DM Mono, Noto Sans SC, monospace"
    fontSize: "11px"
    fontWeight: 400
    letterSpacing: "0.04em"
  label:
    fontFamily: "DM Mono, Noto Sans SC, monospace"
    fontSize: "10px"
    fontWeight: 400
    letterSpacing: "0.14em"
  overlay-tag:
    fontFamily: "DM Mono, Noto Sans SC, monospace"
    fontSize: "14px"
    fontWeight: 700
    letterSpacing: "0.08em"
rounded:
  none: "0px"
  hairline: "1px"
  sm: "2px"
  md: "3px"
  cloth: "12px"
spacing:
  # annotator/ops.css :root, the step-2 layout scale (every margin, padding and gap uses it).
  sp-1: "4px"
  sp-1h: "6px"
  sp-2: "8px"
  sp-3: "12px"
  sp-4: "16px"
  sp-5: "24px"
  sp-6: "32px"
  gutter: "clamp(var(--sp-3), 2.4vw, var(--sp-6))"
components:
  button:
    backgroundColor: "transparent"
    textColor: "{colors.chalk}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "40px"
  button-hover:
    backgroundColor: "{colors.rail-wood}"
  button-primary:
    backgroundColor: "{colors.rail-brass}"
    textColor: "{colors.brass-ink}"
    rounded: "{rounded.sm}"
  button-primary-hover:
    backgroundColor: "{colors.brass-hover}"
  button-danger:
    textColor: "{colors.red-ball}"
  button-compact:
    padding: "0 10px"
    height: "30px"
  chip-group-button:
    backgroundColor: "{colors.pocket-well}"
    textColor: "{colors.worn-leather}"
    typography: "{typography.data}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "34px"
  chip-group-button-active:
    backgroundColor: "{colors.rail-brass}"
    textColor: "{colors.brass-ink}"
  source-chip:
    backgroundColor: "{colors.pocket-well}"
    textColor: "{colors.cue-shaft}"
    typography: "{typography.data}"
    rounded: "{rounded.sm}"
    padding: "5px 10px"
    height: "32px"
  source-chip-active:
    backgroundColor: "{colors.rail-brass}"
    textColor: "{colors.brass-ink}"
  layer-toggle:
    backgroundColor: "transparent"
    textColor: "{colors.worn-leather}"
    rounded: "{rounded.sm}"
    padding: "4px 10px"
    height: "28px"
  layer-toggle-on:
    backgroundColor: "{colors.rail-wood}"
    textColor: "{colors.chalk-bright}"
  badge:
    backgroundColor: "{colors.pocket-well}"
    textColor: "{colors.worn-leather}"
    typography: "{typography.label}"
    padding: "4px 9px"
  badge-live:
    backgroundColor: "{colors.lamp-amber-bg}"
    textColor: "{colors.lamp-amber}"
  badge-complete:
    backgroundColor: "{colors.baize-green-bg}"
    textColor: "{colors.baize-green}"
  badge-scheduled:
    backgroundColor: "{colors.chalk-blue-bg}"
    textColor: "{colors.chalk-blue}"
  panel:
    backgroundColor: "{colors.felt-panel}"
    padding: "18px"
  entry:
    backgroundColor: "{colors.pocket-well}"
    padding: "12px"
  cue-card:
    backgroundColor: "{colors.pocket-well}"
    padding: "8px"
  input:
    backgroundColor: "{colors.pocket-well}"
    textColor: "{colors.chalk}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "42px"
  sheet-tab:
    backgroundColor: "transparent"
    textColor: "{colors.worn-leather}"
    typography: "{typography.data}"
    rounded: "{rounded.none}"
    height: "44px"
  sheet-tab-active:
    backgroundColor: "{colors.rail-wood}"
    textColor: "{colors.polished-brass}"
  stage-popover:
    backgroundColor: "{colors.felt-panel}"
    rounded: "{rounded.sm}"
    padding: "8px"
    width: "168px"
---

# Design System: Corner Pocket

> **How this file was made.** Generated by the Impeccable `document` command (v4.4.0, scan mode) from the code in `annotator/` on branch `impeccable-polish` (at `f2f0e45`). Every value, token, selector and line reference below comes from `ops.css`, `app.css`, `ops.html`, `app.html`, `ops.js`, `app.js` and `vision-stage.js` as they are now. Nothing here is a proposal. The qualitative wording (the North Star, the descriptive colour names, the named rules) is **inferred from the code**, because the interview step could not reach a human in this delegated run. Treat those names as provisional, and change them freely. Line numbers such as `ops.css:223` refer to that commit. **Re-documented after the polish** (step 3 of the Impeccable pass): the frontmatter colours, type ramp and spacing scale are regenerated from the shipped `ops.css` tokens (`out/impeccable/redocument_colors.js`), Motion is rewritten, and the final section records the status of each inconsistency. Body sections that were not re-measured keep their original wording; `docs/impeccable-ledger.md` is the per-change record.

## Overview

**Creative North Star: "The Lamp-Lit Scoreboard"** *(inferred)*

Corner Pocket looks like the back room of a pool hall at night. The ground is dark walnut (`#14110f`) under a faint warm lamp haze (`--lamp`, a radial gradient over the scoreboard). The text is chalk. One metal accent, rail brass (`#c9a227`), marks whatever is current, chosen or primary. The mark is a real 8-ball. Each tab in the nav carries a numbered, coloured pool ball (1 yellow, 2 blue, 3 red, 4 purple, 5 orange, 6 green). The one signature illustration, the cloth preview, is drawn as a table: an 18 px walnut rail around the cloth colour. The club side of the product (Floor, Set up, Matches, Regulars, Back room) uses this material language at full size. Player names and scores are set in Zilla Slab at up to 80 px and 110 px.

The Vision side is the same room with a different job, and a much denser type scale. It is a review instrument in three columns: a cues rail, a 16:9 stage and an inspector. Every panel wears the same 3 px brass top edge. Most text is DM Mono at 10–12.5 px, uppercase and tracked. The design has one moral axis: **who said this**. Machine output is drawn dashed and dimmed. The operator's own work is drawn solid. Calibration is labelled as calibration. A small source tag (MODEL / YOURS / CALIB, 模型 / 人工 / 标定) sits beside every drawn shape. Status is a word inside a bordered chip, never colour alone. The facts line spells out what is on the stage in one ` · `-joined sentence.

The system is flat. Depth comes from four tonal steps (`pocket-well` < `walnut-night` < `felt-panel` < `rail-wood`) and from 1 px seams. Shadows appear only on things that float: toasts, modals, the source panel and the stage popover. Corners are nearly square (2 px). Motion is effectively absent. Both themes and both languages are first-class. Dark/EN is the default. Light is a warm-paper swap of every colour token.

**Key Characteristics:**
- Warm near-black walnut ground with chalk ink; one brass accent for *current / selected / primary*.
- Three voices: Zilla Slab for names, headings and big numerals; Barlow for body text; DM Mono for every label, readout and status word (uppercase, tracked .1–.18em).
- Square-ish: 2 px radius almost everywhere; 50% only for balls and pips.
- Flat tonal layering plus 1 px seams; a 3 px brass top edge marks a working panel.
- Provenance is encoded in stroke: dashed = machine / reference, solid = human / under review.
- Status = word + tinted chip (green complete / amber live-or-stale / blue scheduled / red error).
- Bilingual EN / 中 everywhere, including SVG overlay tags; the Noto SC families sit inside every font stack.

## Colors

A warm, low-chroma walnut-and-chalk neutral ladder, one brass accent, and four signal hues, each given as a text / background / border triplet. Dark is canonical (`ops.css:2`). `:root[data-theme=light]` (`ops.css:3`, `:116`) swaps every value under the same names.

### Primary
- **Rail Brass** (`#c9a227`, light `#8a6a12`, `--brass`): the only accent. Used for active nav and chip states, primary buttons (Freeze, Save), the 3 px top edge of every Vision panel and the scoreboard, `:focus-visible` outlines, selected cards and items, `::selection`, `accent-color` on range and checkbox, scrub-window edges, and model overlay strokes on the stage. It is the most-used colour in the code (67 `var(--brass)` references).
- **Polished Brass** (`#e3c877`, light `#6d5210`, `--brass-hi`): brass as *text*. Links, the shot clock digits, active sheet-tab and sub-label text, the Source chip label, the MODEL tag text and focused group headings.
- **Brass Hover** (`#dcbb46`, light `#a07d18`, `--brass-hover`): used once, as the hover state of the clock-toggle button (`ops.css:156`).
- **Brass Ink** (`#17120c`, light `#fdf8ee`, `--brass-fg`): text on a brass fill. Contrast is 7.7:1 dark and 4.8:1 light.

### Signal hues (text / background / border triplets)
- **Baize Green** (`#7fc39a` / `#16241c` / `#3d5f4c`; light `#256a45` / `#dfeade` / `#a6c2ac`): complete, confirmed, live-edge-on, pot, geometry-verified tier, YOURS tags, receipts and notices, the editable cloth polygon.
- **Lamp Amber** (`#dfa93a` / `#2a2013` / `#5c4a1e`; light `#8a5307` / `#f6e9cf` / `#d6bd8a`): the `live` and `delayed` status badges, **stale** freshness, paused playback, stage notes, error blocks with cause and remedy, and CALIB tags. Amber therefore means both "live" (club status) and "stale" (vision freshness). See *Recorded inconsistencies*.
- **Chalk Blue** (`#8fb4cf` / `#171f26` / `#31495b`; light `#25587c` / `#dde7ef` / `#a8bfd2`): the `scheduled` status and shot marks on the scrub strip. It is defined only in `ops.css`, so the `app.css` stage scope does not have it.
- **Red Ball** (`#cf5b4d`, light `#a4382b`, `--red`): errors, the danger button, a low shot clock, and the event cue line, pocket ring, pot pulse and scrub cue marker. It has no `-bg` / `-line` pair. Error washes are hard-coded instead (`#3d231d` / `#ffd0c5`, dark values in both themes).

### Neutral
- **Walnut Night** (`#14110f`, light `#eee6d8`, `--bg`): page ground.
- **Felt Panel** (`#1a1613`, light `#faf6ee`, `--panel`): header, articles and `.panel`, rails, inspector, modal, popover.
- **Pocket Well** (`#100e0c`, light `#fffdf8`, `--panel2`): the recessed layer. Holds inputs, entries, cue cards, chip-group buttons, score top and foot bars, the strip, sheet tabs, and the inspector action footer. In the light theme it is the *brightest* surface (near-white), so "recessed" becomes "raised paper".
- **Rail Wood** (`#241e19`, light `#e9e0d0`, `--rail`): the hover and selected fill. Also the active nav button, a layer toggled on, the active sheet tab, and the toast background.
- **Seam** (`#2e2620`, light `#d8cbb6`, `--line`): the default 1 px border and divider. It also shows through the 1 px gaps of `.tiles` and `.chip-group`.
- **Seam Soft** (`#262019`, light `#e3d9c7`, `--line2`): borders on entries, cue cards, items and the crop box.
- **Button Rim** (`#4a3f33`, light `#c2b299`, `--btn-line`): the default button border, the layer toggle border, the link underline and `.vs-badge` borders.
- **Chalk Bright / Chalk / Cue Shaft / Worn Leather / Old Varnish** (`--ink-hi` `#f6f1e6`, `--ink` `#f2e9dd`, `--ink-mid` `#b6a693`, `--ink-dim` `#8a7a68`, `--ink-faint` `#6d5f51`; light `#171208` / `#241c12` / `#5b4f41` / `#7c6d5b` / `#9b8b77`): five text steps. Headings use `ink-hi`, body `ink`, paragraphs `ink-mid`, labels and meta `ink-dim`, footnotes and placeholders `ink-faint`. On `--panel`, `ink-dim` measures 4.3:1 (dark) and 4.6:1 (light). `ink-faint` measures 2.9:1 and 3.1:1, below 4.5:1, and it is used for 9.5–10.5 px text (nav sub-labels, `.vs-prov`, `.vs-tag`, `.vs-rate`).
- **Supporting tokens:** `--pip-off` (`#2b241d`, an unlit rack pip), `--live-bg` (`#221a10`, the "leading side" and selected-entry wash), `--neutral-bg` (`#17130f`, used once as the live-edge marker border), `--lamp` (`rgba(240,214,150,.08)` dark / `rgba(255,206,110,.2)` light, the scoreboard glow), `--track` / `--thumb` (scrollbars).
- **Stage Black** (`#090806`, literal): the stage and frame letterbox, identical in both themes. Video is always framed in near-black.

### Named Rules
**The One Brass Rule.** Brass means *current, selected or primary*, and nothing else is brass. When two things on screen are brass, one of them is the active state of the other.

**The Word-Not-Colour Rule.** Every status colour ships with its word (`LIVE`, `STALE`, `COMPLETE`, `geometry-verified`, `CALIB`) inside a bordered chip or tag. The hue only reinforces the word.

**The Triplet Rule.** A signal hue is used as text + tinted background + darker border together (`--green` / `--green-bg` / `--green-line`), never as a bare fill.

## Typography

**Display Font:** Zilla Slab (with Noto Serif SC, Georgia, serif)
**Body Font:** Barlow (with Noto Sans SC, Arial, sans-serif; `app.css` adds Helvetica Neue)
**Label/Mono Font:** DM Mono (with Noto Sans SC, monospace; `app.css` adds ui-monospace)

**Character:** A slab serif with a scoreboard and chalk-sign feel, set against a plain grotesque. The monospace carries every label, number and status word, which gives the instrument feel. The Chinese fallbacks are built into each stack. The display face falls back to Noto *Serif* SC and the body and mono faces to Noto *Sans* SC, so 中 text inherits the same role split. All three families load from Google Fonts in one request (`ops.html:2`, `app.html:8`; weights: Zilla Slab 400/500/600/700 plus italic 400/500, Barlow 300–600, DM Mono 400/500, Noto Sans SC 300–500, Noto Serif SC 400/500/700). The only numeric-feature rule is `font-variant-numeric: tabular-nums` on `.clock` (`ops.css:56`).

### Hierarchy
- **Display** (500, `clamp(34px,5.8vw,80px)`, lh 1.02, −.01em): player names on the scoreboard (`.name`).
- **Numeral** (500, `clamp(52px,7.2vw,110px)`, lh .9): the score digits (`.digits`).
- **Clock** (DM Mono 500, `clamp(36px,4.4vw,60px)`, tabular): the shot clock. It is 22 px in the strip and 13 px in the mobile Vision stagebar.
- **Headline** (400, `clamp(28px,3.2vw,38px)`, lh 1.1): `h2`. Only the offline and error screen uses one.
- **Title** (600, 20px): `h3`, the article and card heads (16 in `ops.js`). The modal head is 600 19px, −.01em. `.tile strong` is 500 22px.
- **Brand** (500, 21px, lh 1.1): the "Corner Pocket" wordmark.
- **Panel heading** (600, 13.5px, .02em, UPPERCASE): Vision rail and inspector group heads and the Source panel head. The inspector's own `h3` goes back to 15px, mixed case.
- **Body** (400, 15px, lh 1.5): the document default. Paragraphs are `ink-mid` with `text-wrap: pretty`. Nav buttons are 14.5px (.01em). Vision items are 12px. The body face in inputs is 13px (`.vs-field`).
- **Data** (DM Mono, 11–12.5px, .04–.08em): the facts line, identity line, source chips, channel IDs, the ball grid (13px), transport inputs (12.5px) and verbs (12px).
- **Label** (DM Mono, 10px, .14em, UPPERCASE, `ink-dim`): `small`, `.kicker`, `.badge`, `label > span`, `th`, inspector `h4`, and the frame-input label. The same role also appears at 9.5, 10.5 and 11px, with tracking from .1 to .18em. See *Recorded inconsistencies*.
- **Overlay tag** (DM Mono 700, 14px, .08em): the SVG source tags. Overlay labels are DM Mono 500 14px, and anchor numerals are 700 16px. These sizes are in *frame pixels* (the SVG `viewBox` is the frame's own `w × h`), so on screen they scale with the stage.

### Named Rules
**The Mono-Means-Machine Rule.** Measured values, identifiers, counts, times and state words are set in DM Mono. Prose and editable names are not.

**The Uppercase-Label Rule.** Labels are small, uppercase and tracked (≥ .1em). Content (names, notes, guest names, via `.vs-tag.guest`) is never uppercased.

## Layout

**Shell.** The header is sticky (`z-index: 10`). The bar holds the brand, the connection badge, the EN|中 chip group and the ☾|☀ chip group. Below it are the nav (six numbered-ball tab buttons) and `#strip` (the shot clock plus the live score button, hidden on Floor). The `.bar`, `nav`, `main` and `footer` all cap at `max-width: 1560px`, centred, with a fluid gutter of `clamp(14px, 2.4vw, 30px)`. `main` pads 22px top and 34px bottom with `min-height: 65vh`. Rows (`.bar`, `.tools`, `nav`, `.row`, `.heading`, `.actions`) are wrapping flex rows with a 10px gap. Anchored scrolling reserves the sticky header: `scroll-padding-top: 270px` and `scroll-margin-top: 270px` on controls, which drop to 16px at ≤750px.

**Grids.** `.grid` is `repeat(auto-fit, minmax(min(100%,340px),1fr))`, gap 16px. `.fields` is `minmax(min(100%,190px),1fr)`, gap 14px × 20px. `.tiles` is `minmax(168px,1fr)`, with 1px gaps over a `--line` background, so the gaps draw hairline dividers. `.stream-grid` is `minmax(0,1fr) 320px`. `.rounds` is a horizontal scroller of 260px-min columns.

**Vision surface.** `.vs-grid` is `280px minmax(0,1fr) 320px` with a 12px gap: rail, stage, inspector. The rail and inspector cap at `max-height: min(calc(100vh - 356px), 620px)`. The stage column stacks the stagebar (layer toggles, the mobile clock, identity) and the 16:9 `.vs-frame`. Below the three columns, `.vs-strip` (transport, scrub track with marks, the facts line) runs the full width of `.vision-surface`, a flex column with a 10px gap: chips, grid, sheet tabs, strip. The inspector is a flex column. Its scroll region reserves the measured footer height (`--vs-footer-h`, set by `syncFooterHeight()`), so no row can hide under the action band.

**Breakpoints** (all `max-width`; there are no min-width queries):
- **≤1100px** (`ops.css:358`): `.vs-grid` becomes one column, and the rail and inspector lose their max-height.
- **≤750px** (`ops.css:99`, `:362`): the header becomes static and the stream grid a single column. On the Vision tab the nav and `#strip` are hidden, the brand tagline is hidden, `main` pads `3px 8px 118px`, and the chips and layers become single-row horizontal scrollers. The shot clock moves into the stagebar (`.vs-clock`).
- **The 390px mobile bottom sheet** (inside the ≤750px block): the rail and inspector become **fixed bottom sheets** (`left:0; right:0; bottom:44px; max-height:44vh; z-index:30`, side borders removed, brass top edge kept). A fixed **sheet-tab bar** (`.vs-sheettabs`, 44px, `z-index:31`, `--panel2`, two mono-uppercase tabs *Cues | Inspector* / *线索 | 检查器*) switches which sheet shows through `.vs-grid[data-sheet=cues|inspector]`. The `.vs-strip` sticks at `bottom: 44px`. The Source panel caps at `72vh`. The 390px pass is recorded in `docs/vision-verification.md` (`scrollWidth` = 390, no horizontal overflow).

**Spacing rhythm.** In practice this is a 2px-granular scale, not a 4 or 8 grid. The most-used values are 8px (47×), 6px (32×), 10px (27×), 4px (23×), 12px (22×) and 14px (15×), with 1, 3, 5, 7, 9, 11, 15 and 18px also present. Panels pad 18px (club) or 12px (Vision). Fluid `clamp()` padding is used only on the scoreboard and the shell gutter.

## Elevation & Depth

The system is flat. Depth comes from tonal layering (well → ground → panel → rail) plus 1px seams, and from the **3px brass top edge**. That edge marks a working surface: `.scoreboard`, `.modal`, `.vs-source-panel`, `.vs-rail`, `.vs-inspector` and `.vs-strip`. A 3px **left** edge marks a callout: `.note`, `#message`, `.rounds .empty` and `.vs-receipt` / `.vs-notice` (green, red on error), plus the tier-marked `.vs-card`. The scoreboard adds a lamp glow (`radial-gradient(120% 150% at 50% -30%, var(--lamp), transparent 62%)`) as its one piece of atmosphere. Shadows exist only on elements that float over other content.

### Shadow Vocabulary
- **Toast** (`box-shadow: 0 5px 30px #0005`): `#message`, bottom-right. `ops.css:92` declares it. The later `ops.css:181` rule restyles the toast but does not override this shadow.
- **Modal** (`box-shadow: 0 14px 44px rgba(0,0,0,.5)`): `.modal` over a `rgba(10,8,6,.62)` backdrop.
- **Source panel** (`box-shadow: 0 16px 48px rgba(0,0,0,.55)`): `.vs-source-panel`, which drops down from the chip row.
- **Stage popover** (`box-shadow: 0 6px 26px #0009`): `.stage-popover` on the frame.
- **Ball bevel** (`inset 0 0 0 1px` at `#0006`, `rgba(0,0,0,.45)` or `.3`; the 8-ball adds `0 2px 6px rgba(0,0,0,.35)`): the pool-ball icons and pips. This is skeuomorphic detail, not elevation.

### Z-index layers
`.stage-popover` 5 (inside the stage) · `.vs-chat-toggle` 2 (sticky) · header 10 · `.vs-source-panel` 24 · mobile sheets 30 · mobile sheet tabs 31 · `#message` 50 · `.modal-backdrop` 60.

### Named Rules
**The Flat-Until-It-Floats Rule.** Resting surfaces never cast shadows. A shadow means the element sits on top of other content and can be dismissed.

**The Brass-Lintel Rule.** A surface you work *in* gets a 3px brass top edge. A message you *read* gets a 3px left edge.

## Shapes

The shapes are nearly square. `border-radius: 2px` appears 22 times: buttons, inputs, chips, chip groups, layer toggles, filters, verbs, items, badges, stage chips and the popover. The others are rare: 3px on `.modal` and `.rounds .empty` (and `rx="3"` on SVG source tags), 1px on scrub marks, 0 on the mobile sheet tabs, 12px only on `.cloth-preview` (a pool table's rounded rail), and 50% only on balls and pips. Borders are 1px solid in `--line`, `--line2` or `--btn-line`. A dashed 1px `--line` border means *empty / nothing here yet* (`.empty` inside the stage scope, `.vs-empty`) or *quiet and secondary* (the `.vs-quiet` divider above "not a player"). The one dashed coloured border is the brass **motion-window** tier (`.vs-badge.tier-window`, `.vs-card.tier-window` with a 3px dashed left edge). Inputs have a 2px bottom border that turns brass on focus. The custom `select` chevron is drawn with two linear gradients (45° and 135°).

## Components

### Buttons
*Rectangular, quiet until touched; brass only when it is the thing to press.*
- **Shape:** 2px radius, 1px `--btn-line` border, transparent fill, `--ink` text. Minimum height 40px (`ops.css:10`), 44px in the nav.
- **Primary / active:** `.primary` or `.active` fills brass with brass-ink text and a brass border. There is no separate secondary style: the default *is* the secondary.
- **Hover:** border turns brass and the fill becomes `--rail`. The clock toggle alone uses `--brass-hover`.
- **Focus:** `:focus-visible` gets a 2px solid brass outline, 3px offset (shell-wide).
- **Disabled:** opacity .45 and `not-allowed` (layer toggles .4; `.pop-grid` .4).
- **Danger:** `.danger` sets red text only. The fill and border stay the same.
- **Score ±:** 54px-wide stacked buttons (`+` primary brass, `−` default), DM Mono 20px, with an `aria-label` naming the player ("<name> +1").
- **Sizes in use:** 46 (score ±), 44 (nav, clock toggle), 40 (default), 36 (strip floor button, modal close), 34 (chip groups, inspector footer, ball grid), 32, 30 (transport, `.vs-row`, strip), 28, 26 (verbs, chat toggle, channel). The control heights come from about 13 distinct `min-height` values. See *Recorded inconsistencies*.

### Chips
- **Chip group** (EN|中, ☾|☀, and the shot-clock presets 20 · 30 · 45 · 60): 1px-gap segmented control on a `--line` ground. Segments are `--panel2`, DM Mono 11px, .08em, `ink-dim`. The active segment is brass-filled. The ☾ and ☀ segments are 40px square, with a 16px stroke SVG icon (stroke-width 1.7) and a bilingual `aria-label` ("Dark / 暗色").
- **Source chip row** (`.vs-chip`): 32px, 2px radius, `--panel2`, `ink-mid`, DM Mono 11px. Hover and active behave like buttons. The live channel chip gets a leading `● `. The **Source** chip itself is outlined in brass, with brass-hi uppercase text and a ` ▾` / ` ▴` disclosure glyph. It opens the absolutely positioned `.vs-source-panel` (brass top edge, shadow, `min(72vh,560px)`).
- **Layer toggles** (`.vs-layer`): cloth, balls, persons, pockets, anchors, events. 28px, transparent, `--btn-line`, 10.5px uppercase mono. When on: `--rail` fill, brass border, `ink-hi` text. Anchors are *disabled* (with a reason in the `title`) outside the vod30 dataset.
- **Filters** (`.vs-filter`): all · geometry-verified · motion window · shots · pots · unreviewed. 26px, 10px uppercase mono. When active: brass border and `--rail`.
- **Chip meta** (`.vs-chipmeta`, 10.5px mono `ink-dim`, right of the chips, hidden at ≤750px): freshness (`.vs-fresh`: `live · frame age 1.2 s` uppercased in a bordered chip, amber when stale, or the VOD source label) plus the keyboard legend (`.vs-keys`, `ink-faint`: `SPACE play · ←/→ step · 0–9/U/C label · A/B identity · V verdict · ⏎ save`).

### Badges and tags
- **Status badge** (`.badge` plus a status class): 10px mono uppercase, .16em, 1px border, `--panel2`. `live` and `delayed` are amber, `complete` is green, `scheduled` is blue. The connection badge reads `LOCAL · SAVED · <revision>` (`本地 · 已保存 · <revision>`).
- **Vision badge** (`.vs-badge`): Shots / Pots type, brass-hi on a `--btn-line` border. Pots are green.
- **Tier badge:** `tier-geometry` is solid green; `tier-window` is a *dashed* brass border. It appears only when the gate recorded a tier, so an unlabelled event never reads as verified.
- **Provenance footnote** (`.vs-prov`): *not* a badge. 10px mono `ink-faint`, green when a person has confirmed it. The copy is literal: "machine-produced candidate; no human has confirmed it" / "机器产出，未经人工确认".
- **Item tag** (`.vs-tag`): right-aligned 10px mono. `done` is green, and `guest` is mixed-case.

### Cards / Containers
- **Club article / panel:** `--panel`, 1px `--line`, 18px padding, square corners. The `.scoreboard` variant has no padding, a brass top edge, the lamp glow, top and foot bars in `--panel2`, and `.side` rows with a 4px left edge (brass plus `--live-bg` when `.leading`). `.tiles` is a hairline-divided stat grid (tile 12px × 15px, min-height 78px, `strong` 22px slab).
- **Entry** (`.entry`): `--panel2`, 1px `--line2`, 12px padding, 8px stacking. When selected: brass border plus `--live-bg`.
- **Cue card** (`.vs-card`): `--panel2`, 1px `--line2`, 8px padding, 6px apart. When selected the border is brass. A tier sets the left edge: 3px solid green or 3px dashed brass. Row: type badge · tier badge · timecode · `#id` · pocket tag, then gate evidence, provenance, and the verdict verbs (✓ ✗ ? buttons, 26px, bilingual `aria-label` / `title`, brass when chosen, and a right-aligned 10px uppercase label).
- **Rail / inspector** (`.vs-rail`, `.vs-inspector`): `--panel`, 1px `--line`, brass top edge, 12px padding. The inspector has a scroll body plus a fixed `--panel2` action footer (buttons 34px). Blocks inside are separated by a 1px `--line` top rule (`.vs-block`). Group heads use the 13.5px uppercase slab. Block heads (`h4`) use the 10px uppercase mono label.
- **Modal:** `--panel`, brass top edge, 3px radius, `min(540px, 100vw−32px)`, 20px × 22px padding, 600 19px slab head, a 36px close button.
- **Toast** (`#message`, `role=status`, `aria-live=polite`): fixed bottom-right, `--rail`, 1px `--line`, 3px brass left edge (red on error), 14px text, max `min(400px, 100vw−40px)`.

### Inputs / Fields
- **Style:** `--panel2` fill, 1px `--line`, 2px radius, 42px min height, 12px side padding, and a **2px bottom border** (`--line`). Labels stack above as a 9.5px uppercase mono `span` with 6px gap. Placeholders use `ink-faint`.
- **Focus:** the outline is removed (`outline: none`) and the bottom border turns brass. This is the one place that does not show the shell's brass focus ring. The Vision inspector's `.vs-field` controls lose the brass bottom border too, so they show no focus indicator at all (see *Recorded inconsistencies*).
- **Select:** native appearance removed, with a gradient-drawn chevron in `ink-dim`.
- **Range / checkbox:** `accent-color: var(--brass)`.
- **Vision fields** (`.vs-field`): a 10px uppercase mono label over a 32px control, 13px Barlow, full width. The guest box dims to .5 when a regular is chosen (`.vs-guest-off`).

### Navigation
- **Tabs:** six buttons, 44px, each with a numbered pool-ball icon (26px ball, 15px cream numeral, colours `#e3b52a` `#23527c` `#b23a2f` `#5d4083` `#cf7326` `#1f6b48` in `ops.js:40`, plus a highlight `::before`) and a count sub-label (9.5px mono, `ink-faint`, brass-hi when active). The tab text is 14.5px Barlow. When active: `--rail` fill, brass border, `ink-hi` text, `aria-current="page"`. The order is binding: Floor · Set up · Matches · Vision · Regulars · Back room.
- **Mobile (≤750px):** the sub-labels are hidden. On Vision the whole nav and strip are hidden, and the two-tab bottom sheet bar takes over.

### Stage and overlay (signature component)
*One frame surface: video, still and SVG overlay share one coordinate system.*
- `.stage` (in `app.css`, scoped to `#review-root`): `#090806`, with `<img>` or `<video>` at full width and an absolutely positioned SVG whose `viewBox` is `0 0 w h` in frame pixels. Exactly one of the video or the still is visible.
- **Stage chips** (DM Mono 10.5px uppercase, 2px radius, 4px × 8px): `.stage-live` sits top-left (green on `--panel2`, amber when stale). `.stage-play` sits bottom-left (brass-hi on a fixed `#0b0a08cc`, amber when paused). `.stage-note` sits along the top edge (amber on a fixed `#14110fee`, 11.5px, lh 1.45). It steps down to 42px when the live chip is showing and turns red on error.
- **Provenance strokes:**
  - *Model / reference* is **dashed and dimmed**. Cloth `12 8` at .55, pockets `7 6` at .5, balls `7 6` at .6, persons `10 7` at .6, model boxes `10 7` at .6, and a model box already covered by a manual one `6 6` at .32.
  - *Operator (YOURS)* is **solid**: manual boxes at opacity 1 (brass stroke 3, `#c9a22722` fill, 5px `#fff2bd` stroke when selected, brass-hi handles), the cloth polygon (green, 3px), and anchors (vod30 only: `#20160d` fill, brass-hi ring, a `grab` cursor, a 700 16px cream numeral, and a single YOURS tag for the set).
  - *The cue under review* is **red and emphatic**: a dashed cue line `10 6` at .9, a solid pocket ring 3.5px at .95, an arrowhead (`.u-cue-head`), a cream cue ball `#fff4d5`, and a dashed cream take-off mark `6 4`. Detected pots also get a dashed red pulse ring (`6 5` at .6) on their pocket.
  - *Interaction:* hovering a model ball removes its dash and restores full opacity. Hovering a person raises it to opacity 1. Selecting a person makes the stroke solid at 4px.
- **Source tags** (`sourceTag()` in `app.js:283`): a group beside the shape, never inside it, so it cannot inherit editable styling. It is a `rect` (height 18, `rx=3`, fill `#0b0a08cc`, 1.5px stroke) plus a 700 14px mono label, laid out by a glyph-width estimate (CJK = 1em, Latin = .62em).
  - **MODEL / 模型**: brass stroke, brass-hi text.
  - **YOURS / 人工**: green stroke and text.
  - **CALIB / 标定**: amber stroke and text. It marks the saved calibration's cloth and pockets: trusted, but not a detection on this frame.
  - **EVENT / 事件**: red stroke, `#f3b3aa` text.
  - The group's own label (`.o-label`, 500 14px, cream) shares the tag's line through `tagRow()`.
  - Person boxes are pale green (`#8fd6a8`, 2px, a literal in `app.js:785`), with a MODEL tag and an identity chip (`.u-chip`, green, turning `#8fd6a8` at opacity 1 once bound to a player).
- **Stage popover** (`.stage-popover`): `--panel` with a brass border, 2px radius, shadow, min width 168px. Holds a 5-column ball grid (30px buttons) plus a row of actions (28px), a 10px uppercase brass-hi head and a 10.5px `ink-dim` note.

### Facts line and scrub strip
- **Facts line** (`#vs-facts`, `role=status`, DM Mono 11px, `ink-mid`): one sentence joined by ` · ` and derived from what the painter drew. In live mode: `live · seq N · frame age 1.2 s · receive-to-result 300 ms · …`. In VOD mode: `frame 1234 · t 41.1 s · …`. Per-layer counts read `balls 10 (+2 manual)`, where the first number is model-drawn and the second is operator-drawn. The line ends in `overlays ON`, `overlays none` or `overlays LOADING (1.2 s)`. Ages print as `ms` below 1 s and as `x.x s` above it. `title` carries the quad detail.
- **Scrub strip** (`.vs-strip`, brass top edge): transport (◀ ▶, **Freeze** primary, ▶ Play / ❚❚ Pause, 30px), a frame-number input (96px, 12.5px mono), and a range track with marks above it. Marks: `.scrub-mark.shot` blue and `.pot` green (4 × 14px, 1px radius). `.scrub-window` is brass at 28% `color-mix` with brass edges. `.scrub-cue` is a 2px red line. `.scrub-loop` is a brass-hi counter chip, amber when paused. `.vs-edge` is the live-edge marker (3px, green when live). In live mode the track dims to .35 and the transport to .55, and step, freeze and play are disabled.

### Source panel
The panel drops down from the Source chip (`.vs-source-panel`, `z-index: 24`, brass top edge, 16/48 shadow, 12px × 14px padding). Its head is a 13.5px uppercase slab with a 28px close ✕. It holds the Twitch live channels, the Twitch VOD replay form and saved channels (`.vs-channel` rows, 26px buttons), plus `.vs-error-block` (amber box, uppercase `h4`, cause and remedy). On mobile it caps at 72vh with 10px padding. Live chat is not in this panel. It sits at the top of the inspector while a live channel plays (`.vs-chat`, a 260px Twitch iframe, with a sticky show/hide toggle).

### Receipts and notices
`.vs-receipt` and `.vs-notice` use a 3px left edge in green on `--green-bg` with green mono text. `.error` switches to a red edge on the hard-coded `#3d231d` / `#ffd0c5`, and `.pending` to an `ink-faint` edge on `--panel2`. Receipts age live (a `setInterval` re-renders the "… s saved" age every second). A pending write never shows a success word.

### Motion
The clock is the one moving thing. Its bar follows the 200 ms tick with a 0.2 s linear `transform: scaleX()` transition (composited, no layout) and turns red with the digits in the last 5 s (`:has(.clock.low)`). `#message` rises 8 px into place in 0.22 s. On narrow screens the stagebar fades its clipped end with a scroll-driven mask (`vs-row-end`). Nothing animates on load; there are no hover lifts or scroll reveals. **Reduced motion**: transitions become instant and animations run 0 s (state changes such as the red low clock stay), except the stagebar fade, which only follows the user's own scroll.

### Bilingual copy conventions (EN / 中)
- **Mechanism, three dictionaries:** `ops.js` has `words` (131 keys, key → `[en, zh]`, `t()`, persisted `cp-ops-lang` and `cp-ops-theme`). `vision-stage.js` has `COPY.en` and `COPY.zh` objects (251 EN keys) through `t(key)`. `app.js` has `text(copy)`, an English-source-string → Chinese map (`editorCopy`) plus regex `editorTemplates` for composed strings. The shell pushes its choice into the engine with `review().setAppearance(lang, theme)`, which also writes `corner-pocket-lang` and `corner-pocket-theme`. The toggle sets `<html lang>` to `en` or `zh-CN`.
- **Casing:** EN chips and labels are *written* in sentence or lower case (`Cues`, `Unreviewed`, `live`, `geometry-verified`) and are uppercased by CSS `text-transform`. Only a few strings are authored in capitals: `POOL HALL OPERATIONS`, `LOCAL · SAVED`, `UNAVAILABLE`, `TWITCH CHANNEL · LIVE STATUS UNVERIFIED` and `TWITCH VOD · RECORDED VIDEO` in `ops.js`; `LOADING` and `STALE` in `vision-stage.js`; and the `MODEL` / `YOURS` / `CALIB` / `EVENT` tags in `app.js`. The two Vision dictionaries have exactly matching key sets (251 EN = 251 中). 中 is never transformed. Letter-spacing still applies to CJK.
- **Separators:** ` · ` (U+00B7 with spaces) joins every composed readout, in both languages (`LOCAL · SAVED` / `本地 · 已保存`, keyboard hints `SPACE play · ←/→ step · …` / `空格 播放 · ←/→ 步进 · …`). 中 copy uses full-width punctuation (`，` `：` `（）` `——`).
- **Units and numbers stay Latin inside 中:** `557mm`, `1.2 s`, `4/4`, `seq`, `#id`, timecodes.
- **Accessible names are bilingual in one string** where the control has no text: `aria-label="Language / 语言"`, `"Dark / 暗色"`, `"Light / 亮色"`. The loading copy is bilingual too: `Loading operations / 正在读取运营数据…`.
- **Voice** (from `PRODUCT.md` Brand Commitments): pool-hall vernacular on the club side, plain measured statements on the machine side. Missing data reads *Not measured* / *尚未采集*.

## Do's and Don'ts

### Do:
- **Do** take every colour from the `--*` tokens so both themes follow. A new status needs its `-bg` / `-line` pair in both `:root` blocks, and `app.css` must mirror it (see *Recorded inconsistencies*).
- **Do** keep brass for current / selected / primary only. Put the 3px brass top edge on any new working panel and the 3px left edge on any new callout.
- **Do** draw machine output dashed and dimmed and operator output solid. Put a MODEL / YOURS / CALIB tag beside every drawn geometry group (not inside it), and keep the tag bilingual (模型 / 人工 / 标定).
- **Do** set measured values, IDs, counts and state words in DM Mono. Labels go 10px uppercase with ≥ .1em tracking. Names go in Zilla Slab, and prose in Barlow 15/1.5.
- **Do** ship every string in EN and 中, join readouts with ` · `, keep units Latin, and give icon-only controls a bilingual `aria-label`.
- **Do** keep 2px corners, 1px seams and flat tonal layers. Use a shadow only on floating, dismissable layers, and follow the existing z-index ladder (10 / 24 / 30 / 31 / 50 / 60).
- **Do** keep controls ≥ 44px wherever they are the primary touch target on mobile (nav, sheet tabs, clock toggle).

### Don't:
- **Don't** add a second accent hue, gradients on UI chrome, or brass as decoration. The lamp glow on the scoreboard and the ball icons are the only atmosphere.
- **Don't** show status by colour alone, and don't let a pending write show a success word.
- **Don't** call a replay "live", show a machine candidate as confirmed, or show an unlabelled event as verified. Provenance must read correctly in the overlay, the rail and the facts line.
- **Don't** add `transition` or `@keyframes` for decoration. The instrument has no motion today, and the reduced-motion guards assume that.
- **Don't** hard-code theme-dependent colours in CSS or in template strings (see *Recorded inconsistencies* for the existing ones). The stage letterbox `#090806` is the one intentional theme-invariant colour.
- **Don't** use rounded pills or large radii. 12px belongs to the pool-table illustration and 50% to balls and pips.

## Recorded inconsistencies: status after the polish (branch `impeccable-polish`)

The nine items the first documentation pass recorded, with the commit that settled each, or why it stays.
The per-command record is `docs/impeccable-ledger.md`.

1. **Two copies of the palette: resolved** (`85ea701`). One OKLCH token source in `ops.css` `:root` / `:root[data-theme=light]`; `app.css` holds no palette and remaps the stage tokens under `#t-overlay`. Gated by `tests/test_palette_contrast.py` (AA text pairs, 3:1 controls, one token source).
2. **Fidelity-pass overrides: resolved** (`485b70a`). The 14 dead early declarations are gone; the values that rendered stay. Pixel diff before/after: 20/20 identical.
3. **Near-continuous type and spacing scales: resolved** (`82db63f`, `079e983`). Six UI sizes (`--fs-xs` 11 … `--fs-xl` 20) plus the display clamps, and a seven-step spacing scale (`--sp-1` 4 … `--sp-6` 32). The 9 px number inside a nav ball is a ball numeral, not text, and stays.
4. **Incomplete light theme: resolved** (`85ea701`). Every former dark literal is a token; the stage keeps its own dark plate in both themes on purpose (`--stage-*`), because it sits on video.
5. **Tokens and styles that do nothing: resolved** (`85ea701`, `485b70a`, `b6e0c9a`). `--code-*`, `--stage-dim`, the `#ops-footer` scope (222 selectors), the `footer` rules and the empty rules are gone.
6. **Amber carries two meanings: open, on purpose.** Club badges keep amber for `live` / `delayed` (a match waiting on people); Vision keeps green for a live feed and amber for stale / CALIB. Changing either is a product decision (PRODUCT.md), not a polish.
7. **Focus treatment is split: resolved** (`01c598e`). Fields use a brass border plus a `box-shadow` ring that a later `border` shorthand cannot remove; checkboxes and ranges use the shell's 2 px outline. Measured: 0 focusable elements without visible focus on nine surfaces.
8. **Accessible names partly bilingual: resolved** (`01c598e`, `b761265`). Region, frame, step and close names follow the language toggle (`data-vs-aria`, `closeLabel`); the sheet tabs are `role=tab` with `aria-selected`; EN|中, ☾|☀ and the layer chips carry `aria-pressed`.
9. **Scattered one-offs: partly open.** The `var(--x,#fallback)` literals are gone and radius is 2 px except `.modal` (3 px, a raised surface). Still open: 21 inline `style=` strings in `ops.js` (16 before, +5 from main's R-series; `ops.js` is edited by unique anchors only, never reformatted) and the `.vs-rail` / `.vs-inspector` `max-height: min(calc(100vh - 356px), 620px)`.

**New since the first pass** (each recorded in the ledger): self-hosted fonts with CJK subsets and a common-hanzi file per face (no CDN); overlay tag rows are placed without overprinting (`placeTags()`); the person chip's colour rule now matches; the clock bar scales (`transform`) instead of resizing; the Floor has a first-run guide until the draw exists; the empty board's placeholder names are dim.
