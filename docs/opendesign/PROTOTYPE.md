# Ops console — interactive prototype

`corner-pocket-ops-console-prototype.html` is the whole operations console as one
self-contained, interactive document. It is not a screenshot of the product and not a
dump of its DOM: it is 24 switchable frames (15 in EN = 9 screens + 6 dialogs, 9 in 中文)
with a deck that drives theme, language and frame, plus the interactions the console
really performs.

Open it straight from disk:

```
xdg-open docs/opendesign/corner-pocket-ops-console-prototype.html
```

## Rebuild

```
cd /home/haoye/projects/pool/docs/opendesign && node build-prototype.mjs
```

Sources it reads:

| Input | What it supplies |
| --- | --- |
| `prototype/chrome.css` | the document chrome: deck, frame cap, sheets, gallery |
| `prototype/proto.js` | the interaction layer: deck state, overlays, scrubber, bracket, clock |
| `prototype/partials.html` | dialogs authored from the real templates (`lateModal`, `sourceModal`, `recordView`, `playerForm`, `appearancePanel`) |
| `prototype/frames-tonight.html` | Tonight states the capture cannot show: bracket states, desk keypad, revival, pairing |
| `.capture/<screen>-<lang>.html` | the real captured markup for the 9 screens, both languages |
| `../annotator/ops.css`, `../annotator/app.css` | the real design tokens and component CSS |

The build renames `#ops-shell` → `.od-shell`, strips `@font-face` (root-relative woff2
would 404 offline), inlines the broadcast stills as data URIs, declares every colour that
sat outside the first `:root{}` as a token inside it, adds the missing letter-spacing on
`text-transform:uppercase` rules, and gives every `<section>` a `data-od-id`.

## Acceptance gate

```
cd /home/haoye/projects/pool
od lint docs/opendesign/corner-pocket-ops-console-prototype.html --json --daemon-url http://127.0.0.1:7457
```

Expect `{"counts":{"p0":0,"p1":0,"p2":0},"findings":[]}` and exit 0. The previous artifact
scored 0/2/1; the two P1s were the raw hexes outside `:root` and one uppercase rule with
`.02em` tracking, and the P2 was 69 unanchored sections.

The `od` CLI defaults to port 7456 — the daemon here is on 7457, so `--daemon-url` is
required or every call fails with ECONNREFUSED. Do not lint
`corner-pocket-ops-console-current.html` (784 KB): it kills the daemon.

## What the prototype performs

* **Deck** — 15 frame buttons, `EN`/`中`, `Dark`/`Light`, `All frames` (a gallery of every
  frame at once). Frame buttons inside a frame (the console's own tab bar) switch the deck
  too, so the deck and the product agree on where you are.
* **Scrubber** (History → one broadcast, and the livestream panel) — dragging the track
  moves the frame index, the facts line, the edge marker, the source label and the row's
  own shot clock. The layer chips and the source label never leave the transport row.
* **Bracket card** — the `Step card` control walks one card through
  `saving… → Racked → On table → Delayed → Bye → Signed`, with the badge, the `won`
  highlight and the side scores following the status.
* **Dialogs** — join-after-the-draw (its teammate fieldset appears only for a doubles
  event; the prototype control on that frame switches the event format), Twitch sources,
  player record, new regular, table appearance.
* **Shot clock** — `Start` / `Reset` / `20 30 45 60` on the timer frame and on the console
  frames that carry a clock.

## Screenshots

`shots/prototype-*.png`, ten of them, all 1680×1050, taken with `agent-browser` at
`set viewport 1680 1050`. They are the browser proof for the interactions above: the
dragged scrubber, the doubles fieldset open, the light + 中文 frame, the gallery.

Note for the next capture run: `agent-browser screenshot <relative path>` writes relative
to the browser process, not the shell — pass an absolute path and copy it in.
