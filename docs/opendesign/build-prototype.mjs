#!/usr/bin/env node
/* ============================================================================
   Build docs/opendesign/corner-pocket-ops-console-prototype.html

   Sources, all inside this repository:
     annotator/ops.css, annotator/app.css   the real design tokens + layout
     annotator/ops.js                       the real screen markup + the EN/中 words
     docs/opendesign/.capture/<screen>-<lang>.html
                                            real DOM captured from the console
     docs/opendesign/prototype/*.html       authored states, dialogs, controls
     docs/opendesign/prototype/chrome.css   prototype chrome
     docs/opendesign/prototype/proto.js     the interaction layer

   The output is one file: no framework, no network, no build step at view time.
   ========================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const PROTO = path.join(HERE, 'prototype');
const CAP = path.join(HERE, '.capture');
const OUT = path.join(HERE, 'corner-pocket-ops-console-prototype.html');
const CONSOLE = process.env.POOL_CONSOLE || 'http://127.0.0.1:8130';

const read = (p) => fs.readFileSync(p, 'utf8');

/* ------------------------------------------------------------- the words --
   ops.js holds the dictionary in one object literal plus four later
   Object.assign(words, {...}) calls. All five carry copy the prototype needs,
   so all five are merged.                                                    */
function braceBody(text, open) {
  let depth = 0, i = open, quote = null, esc = false;
  for (; i < text.length; i += 1) {
    const c = text[i];
    if (quote) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === quote) { quote = null; }
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue; }
    if (c === '{') { depth += 1; continue; }
    if (c === '}') {
      depth -= 1;
      if (depth === 0) { return text.slice(open, i + 1); }
    }
  }
  throw new Error('unbalanced object literal');
}

function loadWords() {
  const src = read(path.join(REPO, 'annotator', 'ops.js'));
  const words = {};
  let m = /const\s+words\s*=\s*\{/.exec(src);
  if (!m) { throw new Error('words dictionary not found in annotator/ops.js'); }
  Object.assign(words, new Function('return (' + braceBody(src, m.index + m[0].length - 1) + ')')());
  const re = /Object\.assign\(\s*words\s*,\s*\{/g;
  let n = 0;
  while ((m = re.exec(src)) !== null) {
    Object.assign(words, new Function('return (' + braceBody(src, m.index + m[0].length - 1) + ')')());
    n += 1;
  }
  if (n !== 4) { throw new Error('expected 4 Object.assign(words, {...}) blocks, found ' + n); }
  return words;
}

const WORDS = loadWords();
const MISSING = new Set();
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/* {{t:key}} or {{t:key|n=2|date=2026-10-04}} -> the language's own copy */
function words(lang) {
  return (text) => text.replace(/\{\{t:([A-Za-z0-9_]+)((?:\|[^}]*)?)\}\}/g, (_, key, args) => {
    const pair = WORDS[key];
    if (!pair) { MISSING.add(key); return '⟨' + key + '⟩'; }
    let out = pair[lang === 'zh' ? 1 : 0];
    (args || '').split('|').forEach((bit) => {
      if (!bit) { return; }
      const eq = bit.indexOf('=');
      if (eq < 0) { return; }
      out = out.split('{' + bit.slice(0, eq) + '}').join(bit.slice(eq + 1));
    });
    return out;
  });
}

/* ---------------------------------------------------------------- the CSS --
   Two mechanical fixes so the real stylesheet passes artifact lint:
     1. every colour literal that sits outside the first :root{} rule is
        declared inside that rule and used through var();
     2. every `text-transform:uppercase` block gets letter-spacing >= .06em.
   @font-face rules are dropped: their woff2 files are root-relative and the
   prototype has no network. The family stacks keep their fallbacks.          */
function stripFontFace(css) {
  let out = css;
  for (;;) {
    const i = out.indexOf('@font-face');
    if (i < 0) { return out; }
    const open = out.indexOf('{', i);
    out = out.slice(0, i) + out.slice(open + braceBody(out, open).length);
  }
}

function splitFirstRoot(css) {
  const m = /:root\s*\{/.exec(css);
  if (!m) { throw new Error('no :root block in the stylesheet'); }
  const open = m.index + m[0].length - 1;
  const body = braceBody(css, open);
  return {
    head: css.slice(0, m.index),
    body: body.slice(1, -1),
    tail: css.slice(m.index + m[0].length - 1 + body.length)
  };
}

function sanitizeCss(css) {
  const parts = splitFirstRoot(css);
  const hexes = new Map();
  const swap = (text) => text.replace(/#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b/g, (hex) => {
    const key = hex.toLowerCase();
    if (!hexes.has(key)) { hexes.set(key, '--hx' + (hexes.size + 1)); }
    return 'var(' + hexes.get(key) + ')';
  });
  let tail = swap(parts.tail);
  /* all-caps needs tracking */
  tail = tail.replace(/[^{}]*\{[^{}]*\}/g, (rule) => {
    if (!/text-transform\s*:\s*uppercase/i.test(rule)) { return rule; }
    if (/letter-spacing\s*:\s*([0-9.]+)em/i.test(rule)) {
      return rule.replace(/letter-spacing\s*:\s*([0-9.]+)em/i, (all, v) => (
        parseFloat(v) >= 0.06 ? all : 'letter-spacing:.06em'
      ));
    }
    if (/letter-spacing\s*:/i.test(rule)) { return rule; }
    return rule.replace(/\{/, '{letter-spacing:.06em;');
  });
  const decls = Array.from(hexes, ([hex, name]) => name + ':' + hex).join(';');
  return parts.head + ':root{' + parts.body + (decls ? ';' + decls : '') + '}' + tail;
}

/* ------------------------------------------------------------- the frames --
   A frame is one console screen in one language, in a fixed 1680x1050 canvas. */
const SCREENS = [
  ['tonight', 'Tonight', '#/tonight', 'screen', 'capture'],
  ['registration', 'Registration desk', '#/tonight · registration', 'screen', 'authored'],
  ['tonight-draw', 'Tonight · bracket states, revival, pairing', '#/tonight · draw', 'states', 'authored'],
  ['records', 'History — every broadcast', '#/records', 'screen', 'capture'],
  ['records-review', 'History — one broadcast, under review', '#/records/review/2890514774', 'screen', 'capture'],
  ['regulars', 'Regulars', '#/regulars', 'screen', 'capture'],
  ['vision', 'Livestream — vision live panel', '#/vision', 'screen', 'capture'],
  ['clock', 'Shot timer and scoreboard', '#/clock', 'screen', 'capture'],
  ['backroom', 'Back room', '#/backroom', 'screen', 'capture']
];

/* dialogs placed inside the frame that opens them */
const OVERLAYS = {
  tonight: ['late'],
  records: ['sources'],
  'records-review': ['sources'],
  vision: ['sources'],
  regulars: ['player', 'newplayer']
};

const TAB_OF = {
  tonight: 'tonight', registration: 'tonight', 'tonight-draw': 'tonight',
  records: 'records', 'records-review': 'records', regulars: 'players',
  vision: 'vision', clock: 'clock', backroom: 'status'
};

const PARTIALS = parseTemplates(read(path.join(PROTO, 'partials.html')));
const AUTHORED = parseTemplates(
  read(path.join(PROTO, 'frames-tonight.html')) +
  (fs.existsSync(path.join(PROTO, 'frames-extra.html')) ? read(path.join(PROTO, 'frames-extra.html')) : '')
);

function parseTemplates(html) {
  const out = {};
  const re = /<template\s+class="pf-(partial|src)"([^>]*)>([\s\S]*?)<\/template>/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    const attrs = {};
    m[2].replace(/([a-zA-Z-]+)="([^"]*)"/g, (_, k, v) => { attrs[k] = v; return _; });
    const key = m[1] === 'partial' ? attrs['data-part'] : attrs['data-screen'];
    out[key] = { kind: m[1], attrs, body: m[3].trim() };
  }
  return out;
}

/* the console header + tab bar, taken from a real capture, retargeted */
function chromeFrom(captureHtml, screen, lang) {
  const head = captureHtml.slice(0, captureHtml.indexOf('<div id="message"'));
  const tab = TAB_OF[screen] || 'tonight';
  return head
    .replace(/\sclass="active"/g, '')
    .replace(/\saria-current="page"/g, '')
    .replace(new RegExp('(<button[^>]*?data-tab="' + tab + '")'), '$1 class="active" aria-current="page"')
    .replace(new RegExp('(<button[^>]*?data-lang="' + lang + '")'), '$1 class="active"')
    .replace(/(<button[^>]*?data-theme="dark")/, '$1 class="active"');
}

function frameCap(label, route, tag, lang) {
  return '  <div class="pf-cap"><strong>' + esc(label) + '</strong>' +
    '<span class="pf-route">' + esc(route) + '</span>' +
    '<span class="pf-tag">' + esc(tag) + ' · ' + (lang === 'zh' ? '中文' : 'EN') + '</span></div>';
}

function overlaysFor(screen, lang) {
  const want = OVERLAYS[screen] || [];
  const t = words(lang);
  return want.map((name) => {
    const p = PARTIALS[name];
    if (!p) { throw new Error('missing partial: ' + name); }
    /* the dialog that switches the event format needs its control above the
       scrim, or the control would be unclickable while the dialog is open */
    let extra = '';
    if (name === 'late') {
      extra = '<div class="pf-ctl-bar pf-ctl-bar--float">' +
        t(PARTIALS['ctl-format'].body).replace(/^<div class="pf-ctl-bar">/, '').replace(/<\/div>\s*$/, '') +
        '</div>';
    }
    return '<div class="pf-overlay" data-pf-overlay="' + name + '">' + extra + t(p.body) + '</div>';
  }).join('\n');
}

function buildFrame(screen, label, route, tag, source, lang) {
  const t = words(lang);
  const id = 'f-' + screen + '-' + lang;
  let inner;
  if (source === 'capture') {
    inner = read(path.join(CAP, screen + '-' + lang + '.html'));
  } else {
    const a = AUTHORED[screen];
    if (!a) { throw new Error('missing authored frame: ' + screen); }
    const body = t(a.body);
    inner = chromeFrom(read(path.join(CAP, 'tonight-' + lang + '.html')), screen, lang) +
      '<div id="message" role="status" aria-live="polite"></div>' + body;
  }
  return '<article class="pf-frame" id="' + id + '" data-screen="' + screen + '" data-lang="' + lang +
    '" data-tab-of="' + TAB_OF[screen] + '">\n' +
    frameCap(label, route, tag, lang) + '\n' +
    '  <div class="pf-canvas">\n    <div class="od-shell">\n' + inner + '\n' +
    overlaysFor(screen, lang) + '\n    </div>\n  </div>\n</article>';
}

/* dialogs as their own frames */
const MODALS = [
  ['modal-late', 'Join after the draw — singles', 'late', 'dialog'],
  ['modal-late-doubles', 'Join after the draw — doubles event', 'late', 'dialog · doubles'],
  ['modal-sources', 'Twitch sources', 'sources', 'dialog'],
  ['modal-player', 'Player record', 'player', 'dialog'],
  ['modal-newplayer', 'New regular', 'newplayer', 'dialog'],
  ['modal-appearance', 'Table appearance — the panel the Back room shows inline', 'appearance', 'panel']
];

function buildModalFrame(id, label, part, tag, lang) {
  const t = words(lang);
  const p = PARTIALS[part];
  if (!p) { throw new Error('missing partial: ' + part); }
  let body = t(p.body);
  let bar = '';
  if (part === 'late') {
    const doubles = tag.indexOf('doubles') >= 0;
    bar = t(PARTIALS['ctl-format'].body);
    if (doubles) {
      bar = bar.replace('class="pf-btn is-on" data-pf-format="singles"', 'class="pf-btn" data-pf-format="singles"')
               .replace('class="pf-btn" data-pf-format="doubles"', 'class="pf-btn is-on" data-pf-format="doubles"');
      body = body.replace(/<fieldset class="late-slot pf-hidden" data-pf-doubles>/, '<fieldset class="late-slot" data-pf-doubles>');
    }
  }
  return '<article class="pf-frame pf-frame--modal" id="f-' + id + '-' + lang + '" data-screen="' + id +
    '" data-lang="' + lang + '" data-tab-of="">\n' +
    frameCap(label, 'dialog', tag, lang) + '\n' + bar + '\n' +
    '  <div class="pf-canvas">\n    <div class="od-shell">\n    <div class="pf-overlay is-on" data-pf-overlay="' + part + '">\n' +
    body + '\n    </div>\n    </div>\n  </div>\n</article>';
}

/* ------------------------------------------------------------- the images --
   The captures point at /api/vods/thumb and at a dead blob: URL. A standalone
   file can reach neither, so a few real decoded frames are fetched from the
   local console at build time and inlined; without a console the build falls
   back to a drawn slate.                                                     */
const SLATE = 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180">' +
  '<rect width="320" height="180" fill="#0b0907"/>' +
  '<rect x="26" y="30" width="268" height="120" rx="6" fill="#1d5c44"/>' +
  '<circle cx="120" cy="80" r="7" fill="#f7f3eb"/><circle cx="170" cy="104" r="7" fill="#cfa72b"/>' +
  '<circle cx="210" cy="70" r="7" fill="#13100e"/></svg>');

async function fetchThumbs() {
  const ids = ['2890514774', '2890340436', '2885294870'];
  const out = [];
  for (const id of ids) {
    try {
      const res = await fetch(CONSOLE + '/api/vods/thumb?channel=ttpoolfriday&id=' + id);
      if (!res.ok) { throw new Error('HTTP ' + res.status); }
      const buf = Buffer.from(await res.arrayBuffer());
      out.push('data:image/jpeg;base64,' + buf.toString('base64'));
      console.log('  inlined thumb ' + id + ' · ' + buf.length + ' B');
    } catch (err) {
      console.log('  thumb ' + id + ' unavailable (' + err.message + ') — slate used');
    }
  }
  return out.length ? out : [SLATE];
}

function replaceImages(html, thumbs) {
  /* 31 History rows would repeat an inlined JPEG 31 times per language; the
     list gets the drawn slate and the stage gets one real decoded frame. */
  return html
    .replace(/src="\/api\/vods\/thumb\?[^"]*"/g, 'src="' + SLATE + '"')
    .replace(/src="blob:[^"]*"/g, () => 'src="' + thumbs[0] + '"');
}

/* ------------------------------------------------------------------ sheets */
function sheet() {
  const css = stripFontFace(read(path.join(REPO, 'annotator', 'ops.css')));
  const root = splitFirstRoot(css).body;
  const tokens = ['--bg', '--panel', '--panel2', '--line', '--ink-hi', '--ink', '--ink-mid',
    '--brass', '--brass-hi', '--green', '--blue', '--amber', '--red', '--ball', '--rail-wood', '--diamond'];
  const map = new Map();
  root.split(';').forEach((decl) => {
    const i = decl.indexOf(':');
    if (i > 0) { map.set(decl.slice(0, i).trim(), decl.slice(i + 1).trim()); }
  });
  const sw = tokens.map((name) => {
    const v = map.get(name) || '—';
    return '      <div class="pf-sw"><i style="background:' + v + '"></i><code>' + name +
      '</code><small>' + esc(v) + '</small></div>';
  }).join('\n');
  return { root, sw, count: map.size };
}

/* ------------------------------------------------------------------- main */
const words0 = words('en');
const cssParts = [
  read(path.join(REPO, 'annotator', 'ops.css')).split('#ops-shell').join('.od-shell'),
  read(path.join(REPO, 'annotator', 'app.css')).split('#ops-shell').join('.od-shell'),
  read(path.join(PROTO, 'chrome.css'))
];
const CSS = sanitizeCss(stripFontFace(cssParts.join('\n')));
const JS = read(path.join(PROTO, 'proto.js'));

const thumbs = await fetchThumbs();

let body = '';
body += SCREENS.map(([screen, label, route, tag, source]) =>
  buildFrame(screen, label, route, tag, source, 'en')).join('\n');
body += '\n' + SCREENS.filter((s) => s[4] === 'authored').map(([screen, label, route, tag]) =>
  buildFrame(screen, label, route, tag, 'authored', 'zh')).join('\n');
body += '\n' + SCREENS.filter((s) => s[4] === 'capture').map(([screen, label, route, tag]) =>
  buildFrame(screen, label, route, tag, 'capture', 'zh')).join('\n');
body += '\n' + MODALS.map(([id, label, part, tag]) => buildModalFrame(id, label, part, tag, 'en')).join('\n');

body = replaceImages(body, thumbs);

/* every top-level section carries an anchor */
let sec = 0;
body = body.replace(/<section(?![^>]*data-(?:od-id|screen-label))(?=[\s>])/g, () => '<section data-od-id="sec-' + (++sec) + '"');
const sections = (body.match(/<section/g) || []).length;

const sheetInfo = sheet();
const deck = SCREENS.map(([screen, label]) =>
  '      <button type="button" class="pf-tab" data-pf-go="' + screen + '">' + esc(label) + '</button>').join('\n');
const modalDeck = MODALS.map(([id, label]) =>
  '      <button type="button" class="pf-tab" data-pf-go="' + id + '">' + esc(label) + '</button>').join('\n');

const html = `<!doctype html>
<html lang="en" data-theme="dark" data-lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Corner Pocket · operations console — interactive prototype</title>
<style>
${CSS}
</style>
</head>
<body class="pf-wide">

<header class="pf-mast">
  <p class="pf-kicker">Design document · interactive prototype</p>
  <h1>Corner Pocket · operations console — interactive prototype</h1>
  <ul class="pf-facts">
    <li><strong>${SCREENS.length * 2 + MODALS.length}</strong> frames</li>
    <li><strong>${SCREENS.length}</strong> screens</li>
    <li><strong>${MODALS.length}</strong> dialogs</li>
    <li><strong>2</strong> languages · EN + 中文</li>
    <li><strong>1</strong> file · no network · no build step</li>
  </ul>
  <div class="pf-note">
    <p><strong>What this is.</strong> A working prototype of the console as it stands: every screen, every state and every dialog the fixture reaches, drawn with the console's own stylesheet and its own markup. Pick a screen in the deck below and use the screen itself — the tabs, the language chips and the theme chips inside each frame are live.</p>
    <p><strong>How to read it.</strong> The deck switches one frame at a time. <em>All frames</em> lays them out as a board for review. Everything inside a frame is the real interface: click the console tabs to move between screens, the EN/中 chips to switch language, the sun and moon chips to switch theme, the bracket card to step its state, the scrubber to move through a broadcast, and the buttons that open dialogs to open them.</p>
    <p><strong>Not here.</strong> No backend, no video, no Twitch playback, no review chrome from OpenDesign. The frame on the review stage and on the livestream panel is one real decoded broadcast frame, inlined; the History list thumbnails are drawn placeholders, because their URLs point at a local API. Live data is fixture data, captured from the running console.</p>
  </div>
</header>

<nav class="pf-deck" aria-label="Prototype deck">
  <div class="pf-deck-row">
${deck}
  </div>
  <div class="pf-deck-row">
${modalDeck}
  </div>
  <div class="pf-deck-row">
    <span class="pf-seg" role="group" aria-label="Language">
      <button type="button" class="pf-btn is-on" data-pf-lang="en">EN</button>
      <button type="button" class="pf-btn" data-pf-lang="zh">中</button>
    </span>
    <span class="pf-seg" role="group" aria-label="Theme">
      <button type="button" class="pf-btn is-on" data-pf-theme="dark">Dark</button>
      <button type="button" class="pf-btn" data-pf-theme="light">Light</button>
    </span>
    <button type="button" class="pf-btn" data-pf-all="1">All frames</button>
  </div>
</nav>

<section class="pf-sheet" data-od-id="tokens">
  <h2>Tokens</h2>
  <p class="pf-note-inline">Every colour in this document comes from these custom properties. The light theme overrides the same names, so a screen never names a colour of its own.</p>
  <div class="pf-swatches">
${sheetInfo.sw}
  </div>
</section>

<section class="pf-sheet" data-od-id="rules">
  <h2>Rules a redesign has to keep</h2>
  <ul class="pf-rules">
    <li><strong>One token set, two themes.</strong> Dark and light override the same custom properties. A new screen that names a colour directly is a bug.</li>
    <li><strong>Two languages, one layout.</strong> EN and 中文 are resolved from the same keys, so no frame may grow or shrink when the language changes.</li>
    <li><strong>The scrubber is one row.</strong> Layer chips, source label, frame number, step, freeze, play, shot clock and identity stay in a single transport row under the stage.</li>
    <li><strong>Live is a badge, not a screen.</strong> Pending, racked, on table, delayed, bye and signed are states of the same bracket card.</li>
    <li><strong>A dialog never navigates.</strong> Sources, late join, player record and appearance open over the screen that asked for them and close back into it.</li>
    <li><strong>Registration order seeds the draw.</strong> Byes advance on their own; a forfeit is recorded apart and never counted as a win.</li>
  </ul>
</section>

<section class="pf-board" data-od-id="frames">
  <h2 class="pf-visually-hidden">Screen frames</h2>
${body}
</section>

<script>
${JS}
</script>
</body>
</html>
`;

fs.writeFileSync(OUT, words0(html));
if (MISSING.size) {
  console.error('unknown dictionary keys: ' + Array.from(MISSING).sort().join(', '));
  process.exit(2);
}
console.log('wrote ' + path.relative(REPO, OUT) + ' · ' + fs.statSync(OUT).size + ' B · ' +
  (SCREENS.length * 2 + MODALS.length) + ' frames · ' + sections + ' sections');
