# Current ops-console UI → OpenDesign

How the **current** operations console was captured and published to the OpenDesign project
`corner-pocket-ops-console`. Regenerate everything with the two commands at the bottom.

The historical export (`corner-pocket-ops-console.html`, 195851 B, 2026-10-04) is untouched.

## What is published

| | |
|---|---|
| artifact | `corner-pocket-ops-console-current.html` |
| project | `corner-pocket-ops-console` — "Sync Current Design Opendesign Workspace" |
| size | 784424 B (in the project), 775837 B on disk before the daemon re-encoded it |
| project dir | `/home/haoye/.od/projects/corner-pocket-ops-console/` |
| served bytes | `http://127.0.0.1:7457/api/projects/corner-pocket-ops-console/files/corner-pocket-ops-console-current.html` → HTTP 200 |
| OD page | `http://127.0.0.1:5174/projects/corner-pocket-ops-console` · public `https://design.yay.how/projects/corner-pocket-ops-console` |
| odsync | link `corner-pocket`, `od=0f44d18f mirror=0f44d18f` |

## What the artifact contains

- **Fourteen frames of real rendered DOM** — seven screens × EN/中 — taken with
  `agent-browser get html "#ops-shell"` from the console running at `http://127.0.0.1:8130`.
  Screens: `tonight`, `records`, `records-review`, `vision`, `clock`, `regulars`, `backroom`.
  Frames are unmodified except that root-relative image URLs were pointed at the console
  (absolute) so the thumbnails stay live.
- **The console's real stylesheet**, inlined byte-for-byte from `annotator/ops.css`
  (md5 `59ac303a5fdb2f4ec815f54f3271b260`, 121012 B) and `annotator/app.css`
  (md5 `964bc7c6c4c6b2bf3b2584de76ef666b`, 12834 B), with one mechanical rename:
  `#ops-shell` → `.od-shell` (843 + 1 occurrences) so fourteen frames can share one document
  without duplicating an id. Verified byte-identical to what the console serves.
- **Both themes and both languages** as real state, not lookalikes: the page's own EN/中 and
  Dark/Light controls set `data-capture-lang` and `<html data-theme>` — the same attribute the
  console's stylesheet keys on.
- The real token table read out of the stylesheet (16 colour tokens at `:root`, 13 light
  overrides at `:root[data-theme=light]`), and three live captures embedded as JPEG.

## Files

| file | what |
|---|---|
| `capture-current.sh` | drives a browser over the 7 routes × 2 languages, writes `.capture/<screen>-<lang>.html` |
| `build-current.mjs` | assembles the artifact from `.capture/` + the two stylesheets |
| `corner-pocket-ops-console-current.html` | the artifact |
| `shots/current-*.png` | eight real screenshots at 1680 px wide |
| `.capture/` | working captures (kept so the artifact can be rebuilt without a browser) |

## Two traps, both hit and both now guarded

1. **The console remembers the language in `localStorage`.** An "en" capture silently inherits a
   previously selected `zh`. `capture-current.sh` presses the wanted chip and asserts
   `document.documentElement.lang` before reading markup.
2. **A modal is `position:fixed`.** An open modal inside a frame escapes its container and covers
   the whole page. The first Regulars capture shipped with the player-detail modal open; the
   script now dismisses any `.modal-backdrop`, refuses to write a capture while a `.modal` is
   open, and `build-current.mjs` throws on a capture that still contains one.

## Lint

`od lint docs/opendesign/corner-pocket-ops-console-current.html --daemon-url http://127.0.0.1:7457 --json`

```
p0: 0   p1: 2   p2: 1
```

All three findings are in the console's own stylesheet, not in the capture: one
`text-transform:uppercase` without tracking (`.vs-source-head strong`), 46 raw hex values outside
`:root`, and `<section>`s without `data-od-id`. They are reported rather than fixed — fixing them
would stop the artifact representing the shipped UI. The artifact's own wrapper sections do carry
`data-od-id`.

## Regenerate

```bash
bash docs/opendesign/capture-current.sh      # needs the console on :8130 and agent-browser
node docs/opendesign/build-current.mjs
od artifacts create --name corner-pocket-ops-console-current.html \
  --input docs/opendesign/corner-pocket-ops-console-current.html \
  --project corner-pocket-ops-console --daemon-url http://127.0.0.1:7457
/home/haoye/projects/opendesign-sync/bin/odsync pull corner-pocket
```

`od` defaults to port **7456**; this host's daemon is on **7457**, so `--daemon-url` is required.
`od artifacts create` rejects an existing target path (`409 FILE_EXISTS`), so a re-publish needs a
new `--name` or the old file removed first. `odsync pull` writes the gitignored
`.od-sync/design/` mirror.
