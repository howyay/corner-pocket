#!/usr/bin/env node
/**
 * Build the CURRENT ops-console design artifact for OpenDesign.
 *
 * Input  : docs/opendesign/.capture/<screen>-<lang>.html  (real rendered DOM, see capture-current.sh)
 *          annotator/ops.css + annotator/app.css           (the console's real stylesheet, byte-for-byte
 *                                                           except one mechanical rename: #ops-shell -> .od-shell,
 *                                                           so fourteen real frames can share one document)
 * Output : docs/opendesign/corner-pocket-ops-console-current.html
 *
 * The page carries its own EN/中 and dark/light controls. The theme control only sets
 * <html data-theme="..."> - exactly the attribute the console's own stylesheet keys on - so both themes
 * are the real themes, not a re-implementation.
 *
 * Usage: node docs/opendesign/build-current.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const CAP = path.join(HERE, '.capture');
const OUT = path.join(HERE, 'corner-pocket-ops-console-current.html');
const CONSOLE = 'http://127.0.0.1:8130';

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const md5 = f => crypto.createHash('md5').update(fs.readFileSync(f)).digest('hex');

// ---- the real stylesheet, with the one mechanical rename -------------------------------------------
const readCss = f => {
  const raw = fs.readFileSync(path.join(ROOT, f), 'utf8');
  const n = (raw.match(/#ops-shell/g) || []).length;
  return { css: raw.replaceAll('#ops-shell', '.od-shell'), renamed: n, bytes: raw.length, md5: md5(path.join(ROOT, f)) };
};
const ops = readCss('annotator/ops.css');
const app = readCss('annotator/app.css');

// ---- the real frames -------------------------------------------------------------------------------
const SCREENS = [
  ['tonight', 'Tonight', 'The tournament board: event head, bracket, entrants, and the join-after-the-draw slot.', '#/tonight'],
  ['records', 'History', 'Events and broadcasts under one head, with the per-event row of actions.', '#/records'],
  ['records-review', 'History — one broadcast\u2019s review', 'The recorded-broadcast review: ball queue, event rail, the frozen frame, and the overlay bar.', '#/records/review/2890514774'],
  ['vision', 'Livestream', 'The live panel in its idle state: source chip, Start, Sources, Debug workbench.', '#/vision'],
  ['clock', 'Shot timer', 'The always-mounted shot clock and its presets.', '#/clock'],
  ['regulars', 'Regulars', 'The roster, each row\u2019s standing, and the player-detail panel.', '#/regulars'],
  ['backroom', 'Back room', 'The maintainer surface: table appearance, operator notes, system status.', '#/backroom'],
];
const LANGS = [['en', 'EN'], ['zh', '中']];

const frames = [];
for (const [id, title, note, route] of SCREENS) {
  for (const [lang] of LANGS) {
    const file = path.join(CAP, `${id}-${lang}.html`);
    if (!fs.existsSync(file)) throw new Error(`missing capture: ${file} - run docs/opendesign/capture-current.sh first`);
    const raw = fs.readFileSync(file, 'utf8');
    // A stray open modal is position:fixed: inside a frame it would escape and cover the page.
    if (/class="modal-backdrop"/.test(raw)) throw new Error(`stray open modal in ${file} - re-run docs/opendesign/capture-current.sh`);
    // The console serves these thumbnails from its own root; keep them live instead of broken.
    const live = raw.replace(/(src|href)="\/(?!\/)/g, `$1="${CONSOLE}/`);
    frames.push({ id, lang, title, note, route, raw, live, bytes: raw.length });
  }
}

// ---- the real tokens, read out of the stylesheet ----------------------------------------------------
const tokensOf = selector => {
  const m = ops.css.match(new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\{([^}]*)\\}'));
  if (!m) return {};
  const out = {};
  for (const decl of m[1].split(';')) {
    const i = decl.indexOf(':');
    if (i < 0) continue;
    const k = decl.slice(0, i).trim();
    const v = decl.slice(i + 1).trim();
    if (k.startsWith('--') && /^#[0-9a-fA-F]{3,8}$/.test(v)) out[k] = v;
  }
  return out;
};
const dark = tokensOf(':root');
const light = tokensOf(':root[data-theme=light]');
const TOKEN_ORDER = ['--bg', '--panel', '--panel2', '--line', '--ink-hi', '--ink', '--ink-mid', '--brass', '--brass-hi', '--green', '--blue', '--amber', '--red', '--ball', '--rail-wood', '--diamond'];
const swatches = TOKEN_ORDER.filter(k => dark[k]).map(k => {
  const dv = dark[k], lv = light[k] || dv;
  return `<tr><td class="tok">${esc(k)}</td><td><span class="sw" style="background:${esc(dv)}"></span><code>${esc(dv)}</code></td><td><span class="sw" style="background:${esc(lv)}"></span><code>${esc(lv)}</code></td></tr>`;
}).join('\n');

// ---- the real console, downscaled, so the artifact carries its own visual reference -----------------
const SHOTS = [['tonight', 'Tonight — the tournament board'], ['records', 'History — the archive'], ['vision-workbench', 'History — a broadcast\u2019s review']];
const shots = SHOTS.map(([id, label]) => {
  const f = path.join(CAP, `embed-${id}.jpg`);
  if (!fs.existsSync(f)) return '';
  return `<figure class="shot"><img alt="${esc(label)}" src="data:image/jpeg;base64,${fs.readFileSync(f).toString('base64')}"><figcaption>${esc(label)} · live capture ${esc(CONSOLE)}</figcaption></figure>`;
}).join('\n');

// ---- assemble ---------------------------------------------------------------------------------------
const frameHtml = SCREENS.map(([id, title, note, route]) => `
<section class="odc-screen" id="screen-${esc(id)}" data-od-id="screen-${esc(id)}" data-screen-label="${esc(title)}">
  <div class="odc-screen-head">
    <h2>${esc(title)}</h2>
    <p>${esc(note)}</p>
    <p class="odc-route"><code>${esc(route)}</code>${LANGS.map(([l]) => {
      const f = frames.find(x => x.id === id && x.lang === l);
      return ` · <span class="odc-bytes">${esc(l)} ${f.bytes} B</span>`;
    }).join('')}</p>
  </div>
  <div class="odc-frames">
${LANGS.map(([l, label]) => `    <div class="odc-frame" data-frame-lang="${esc(l)}"><span class="odc-tag">${esc(label)}</span><div class="od-shell">${frames.find(x => x.id === id && x.lang === l).live}</div></div>`).join('\n')}
  </div>
</section>`).join('\n');

const totalBytes = frames.reduce((n, f) => n + f.bytes, 0);
const page = `<!doctype html>
<html lang="en" data-theme="dark" data-capture-lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corner Pocket — Operations console (current UI)</title>
<style>
/* ============================================================================
   The console's real stylesheet, inlined byte-for-byte from annotator/ops.css
   and annotator/app.css, with one mechanical rename: #ops-shell -> .od-shell
   (ops.css ${ops.renamed} occurrences, app.css ${app.renamed}) so the frames below can
   share one document without duplicating an id.
   ops.css md5 ${esc(ops.md5)} (${ops.bytes} B) · app.css md5 ${esc(app.md5)} (${app.bytes} B)
   ============================================================================ */
${ops.css}
${app.css}

/* ===== board chrome — this artifact only, never part of the console ===== */
.odc-head{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:var(--sp-4) var(--sp-5)}
.odc-head h1{font-family:var(--display);font-size:var(--fs-xl);margin:0 0 2px}
.odc-head p{margin:0;color:var(--ink-mid);font-size:var(--fs-sm);max-width:var(--measure)}
.odc-ctl{display:flex;gap:var(--sp-4);flex-wrap:wrap;margin-top:var(--sp-3)}
.odc-ctl .grp{display:flex;align-items:center;gap:var(--sp-2);font-size:var(--fs-xs);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-dim)}
.odc-ctl button{font:inherit;font-family:var(--mono);font-size:var(--fs-sm);background:var(--panel2);color:var(--ink);border:1px solid var(--btn-line);padding:4px 12px;cursor:pointer}
.odc-ctl button[aria-pressed="true"]{background:var(--brass);color:var(--brass-fg);border-color:var(--brass)}
.odc-wrap{max-width:var(--page-max);margin:0 auto;padding:var(--sp-5)}
.odc-sec{margin:0 0 var(--sp-6);border:1px solid var(--line);background:var(--panel);padding:var(--sp-5)}
.odc-sec>h2{font-family:var(--display);font-size:var(--fs-lg);margin:0 0 var(--sp-2)}
.odc-sec>p{margin:0 0 var(--sp-4);color:var(--ink-mid);font-size:var(--fs-sm);max-width:var(--measure)}
table.tok{width:100%;border-collapse:collapse;font-size:var(--fs-sm)}
table.tok th,table.tok td{text-align:left;padding:3px 10px 3px 0;border-bottom:1px solid var(--line2)}
table.tok th{color:var(--ink-dim);font-weight:500;font-size:var(--fs-xs);text-transform:uppercase;letter-spacing:.08em}
table.tok td.tok{font-family:var(--mono);color:var(--ink-mid)}
table.tok code{font-family:var(--mono);color:var(--ink-dim);font-size:var(--fs-xs)}
.sw{display:inline-block;width:16px;height:16px;border:1px solid var(--line);vertical-align:-3px;margin-right:8px}
.shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:var(--sp-4)}
.shot{margin:0}
.shot img{width:100%;display:block;border:1px solid var(--line)}
.shot figcaption{font-size:var(--fs-xs);color:var(--ink-dim);font-family:var(--mono);padding-top:6px}
.odc-screen{margin:0 0 var(--sp-6)}
.odc-screen-head{border-left:3px solid var(--brass);padding-left:var(--sp-3);margin-bottom:var(--sp-3)}
.odc-screen-head h2{font-family:var(--display);font-size:var(--fs-lg);margin:0}
.odc-screen-head p{margin:2px 0 0;color:var(--ink-mid);font-size:var(--fs-sm);max-width:var(--measure)}
.odc-route{font-size:var(--fs-xs)!important;color:var(--ink-dim)!important}
.odc-route code{font-family:var(--mono)}
.odc-bytes{font-family:var(--mono)}
.odc-frame{position:relative;border:1px solid var(--line);overflow:hidden;margin-bottom:var(--sp-4)}
.odc-tag{position:absolute;top:0;right:0;z-index:5;font-family:var(--mono);font-size:var(--fs-xs);background:var(--brass);color:var(--brass-fg);padding:1px 8px}
html[data-capture-lang="en"] .odc-frame[data-frame-lang="zh"]{display:none}
html[data-capture-lang="zh"] .odc-frame[data-frame-lang="en"]{display:none}
.od-shell{display:block;background:var(--bg)}
.odc-note{font-size:var(--fs-xs);color:var(--ink-dim);font-family:var(--mono)}
</style>
</head>
<body>
<header class="odc-head">
  <h1>Corner Pocket — Operations console</h1>
  <p>The current shipped UI, captured from the running console at <code>${esc(CONSOLE)}</code>. Every frame below is the real rendered DOM; the stylesheet above is the real <code>annotator/ops.css</code>.</p>
  <div class="odc-ctl">
    <span class="grp">Language
      <button type="button" data-set-lang="en" aria-pressed="true">EN</button>
      <button type="button" data-set-lang="zh" aria-pressed="false">中</button>
    </span>
    <span class="grp">Theme
      <button type="button" data-set-theme="dark" aria-pressed="true">Dark</button>
      <button type="button" data-set-theme="light" aria-pressed="false">Light</button>
    </span>
  </div>
</header>
<div class="odc-wrap">

<section class="odc-sec" data-od-id="what-this-is">
  <h2>What this is</h2>
  <p>Fourteen frames — seven screens in both languages — taken from the live console. ${frames.length} frames · ${totalBytes} bytes of real markup · unmodified except that root-relative image URLs were pointed at ${esc(CONSOLE)} so the thumbnails stay live. Theme is <code>&lt;html data-theme&gt;</code>, the same attribute the console's stylesheet keys on.</p>
  <p class="odc-note">Palette dark: ${TOKEN_ORDER.filter(k => dark[k]).length} colour tokens · light overrides: ${TOKEN_ORDER.filter(k => light[k]).length}</p>
</section>

<section class="odc-sec" data-od-id="tokens">
  <h2>Tokens</h2>
  <p>The real custom properties from <code>annotator/ops.css</code> — the dark block at <code>:root</code>, and the light override at <code>:root[data-theme=light]</code>.</p>
  <table class="tok"><thead><tr><th>Token</th><th>Dark</th><th>Light</th></tr></thead><tbody>
${swatches}
  </tbody></table>
</section>

<section class="odc-sec" data-od-id="screens">
  <h2>Screens, as the console renders them</h2>
  <p>Live capture · ${esc(new Date().toISOString())}</p>
  <div class="shots">
${shots}
  </div>
</section>

${frameHtml}

</div>
<script>
(() => {
  const root = document.documentElement;
  const paint = () => {
    document.querySelectorAll('[data-set-lang]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.setLang === root.dataset.captureLang)));
    document.querySelectorAll('[data-set-theme]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.setTheme === (root.dataset.theme || 'dark'))));
  };
  document.querySelectorAll('[data-set-lang]').forEach(b => b.addEventListener('click', () => { root.dataset.captureLang = b.dataset.setLang; root.lang = b.dataset.setLang === 'zh' ? 'zh-CN' : 'en'; paint(); }));
  document.querySelectorAll('[data-set-theme]').forEach(b => b.addEventListener('click', () => { root.dataset.theme = b.dataset.setTheme; paint(); }));
  paint();
})();
</script>
</body>
</html>
`;

fs.writeFileSync(OUT, page);
console.log(JSON.stringify({
  target: OUT,
  bytes: page.length,
  frames: frames.length,
  screens: SCREENS.length,
  cssBytes: ops.css.length + app.css.length,
  renamed: { ops: ops.renamed, app: app.renamed },
  md5: { ops: ops.md5, app: app.md5 },
  embeddedShots: SHOTS.filter(([id]) => fs.existsSync(path.join(CAP, `embed-${id}.jpg`))).length,
}, null, 1));
