#!/usr/bin/env node
/**
 * Capture the entire ops console UI into one OpenDesign board.
 *
 * Every frame is the real markup the shipped app renders: the console is booted in the test suite's own
 * vm harness (tests/test_ops.js, which already renders every state without a DOM), and each screen is
 * captured by calling the same function the browser calls. The stylesheet is inlined byte-for-byte with
 * one mechanical rename (#ops-shell -> .od-shell) so each frame is scoped and no id is duplicated.
 *
 * Usage: node docs/opendesign/capture.mjs   ->  docs/opendesign/corner-pocket-ops-console.html
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const TMP = path.join(ROOT, 'out', 'r14', 'od-capture');
fs.mkdirSync(TMP, { recursive: true });

// ---- 1. the suite's helpers, exported: the file is copied, its remote imports are stubbed, and the
//         relative paths are rewritten to the repo's own files (a mechanical edit, recorded here).
const suite = fs.readFileSync(path.join(ROOT, 'tests', 'test_ops.js'), 'utf8')
  .replace("const test = require('node:test');", 'const test = () => {};')
  .replaceAll("path.join(__dirname, '../", `path.join('${ROOT}/`)
  .replace("require('../annotator/clock-sync.js')", `require('${ROOT}/annotator/clock-sync.js')`) +
  "\nmodule.exports = { harness, recordsNight, tonightNight, archiveHistory, linkHistory, opsCss, opsHtml };\n";
const suiteCopy = path.join(TMP, 'helpers.cjs');
fs.writeFileSync(suiteCopy, suite);
const { harness, recordsNight, tonightNight, archiveHistory, linkHistory, opsCss, opsHtml } = require(suiteCopy);

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const frames = [];
const take = (screen, state, lang, html, note) => frames.push({ screen, state, lang, note, html });

const boot = (setup, lang = 'en') => {
  const h = harness();
  h.evaluate("render=()=>{};reviewId=null;sheetId=null;setupOpen=false;sourceOpen=false");
  if (setup) h.evaluate(setup);
  if (lang !== 'en') h.evaluate(`lang='${lang}'`);
  return h;
};
const LIVE = `data.tournament=Object.assign(data.tournament,{matches:data.tournament.matches.concat([{id:'mL',round:1,sides:['b','g'],score:[2,1],status:'live',table:2,absent:[]}])})`;

// ---- Tonight: every state the tab can be in
take('Tonight', 'idle — the club has no night yet', 'en', boot(`data.tournament={id:'',name:'',format:'singles',raceTo:1,tables:1,status:'registration',entrants:[],matches:[]}`).evaluate('tonightScreen()'));
take('Tonight', 'registration — entrants signed, no draw', 'en', (() => { const h = boot(); tonightNight(h, null); return h.evaluate('tonightScreen()'); })());
take('Tonight', 'active — a match on table 2', 'en', (() => { const h = boot(); tonightNight(h, 'drawn'); h.evaluate(LIVE); return h.evaluate('tonightScreen()'); })());
take('Tonight', 'complete — every result signed', 'en', (() => { const h = boot(); tonightNight(h, 'done'); return h.evaluate('tonightScreen()'); })());
take('Tonight', 'the results sheet (read-only, printable)', 'en', (() => { const h = boot(); tonightNight(h, 'done'); h.evaluate("sheetId='t0'"); return h.evaluate('tonightScreen()'); })());
take('Tonight', 'event settings — the locked dialog', 'en', (() => { const h = boot(); tonightNight(h, 'drawn'); h.evaluate('setupOpen=true'); return h.evaluate('tonightScreen()'); })());
take('Tonight', 'the first-run dialog (a night with no name)', 'en', boot(`data.tournament={id:'',name:'',format:'singles',raceTo:7,tables:4,status:'registration',entrants:[],matches:[]}`).evaluate('startModal(false)'));
take('Tonight', 'the second chance (random draw, undoable)', 'en', (() => { const h = boot(); tonightNight(h, 'drawn'); h.evaluate("data.tournament.revival={entrant:'g',seed:424242,attempt:1,signed:4,pool:['a','b','g'],drawnAt:'2026-10-04T05:10:00Z'}"); return h.evaluate('tonightScreen()'); })());
take('Tonight', 'active — 中文', 'zh', (() => { const h = boot(); tonightNight(h, 'drawn'); h.evaluate(LIVE); return h.evaluate("lang='zh';tonightScreen()"); })());

// ---- History: list, empties, both kinds of review
take('History', 'the list — nights and broadcasts under one head', 'en', (() => {
  const h = boot(); h.evaluate(archiveHistory); return h.evaluate('recordsScreen()');
})(), 'the archive window is the test fixture, not the club');
take('History', 'empty — nothing has been built or linked yet', 'en', boot("data.players=[];data.history=[];data.events=[];data.vods=[];data.links=[]").evaluate('recordsScreen()'));
take('History', 'a night\'s review (read-only, from its row)', 'en', (() => {
  const h = boot(); h.evaluate(archiveHistory); h.evaluate("reviewId='h1';sheetId=null"); return h.evaluate('recordsScreen()');
})());
take('History', 'the list — 中文', 'zh', (() => { const h = boot(); h.evaluate(archiveHistory); recordsNight(h); return h.evaluate("lang='zh';recordsScreen()"); })());

// ---- Regulars, Back room, the timer
take('Regulars', 'the roster, with each row\'s standing', 'en', (() => { const h = boot(); recordsNight(h); return h.evaluate('playersScreen()'); })());
take('Regulars', 'one player\'s record (read-only modal)', 'en', (() => { const h = boot(); recordsNight(h); return h.evaluate('playerForm(data.players[0])'); })());
take('Back room', 'notes, appearance, and the maintainers fold', 'en', (() => { const h = boot(); recordsNight(h); return h.evaluate('statusScreen()'); })());
take('Back room', 'notes and maintainers — 中文', 'zh', (() => { const h = boot(); recordsNight(h); return h.evaluate("lang='zh';statusScreen()"); })());
take('Shot timer', 'the timer page, with the match it follows', 'en', (() => { const h = boot(); tonightNight(h, 'drawn'); h.evaluate(LIVE); return h.evaluate('clockScreen()'); })());
take('Shell chrome', 'the destinations, the phone bar and the clock', 'en', boot("data.players=[];data.history=[]").evaluate("tabbarHTML()+clockHTML()"), 'tabbarHTML() + clockHTML()');
take('Shell chrome', 'the printed header of ops.html', 'en', (opsHtml.match(/<header>[\s\S]*?<\/header>/) || [''])[0], 'the real bytes of annotator/ops.html');

// ---- Vision: the live panel, the workbench, the recorded review
take('Vision', 'the live panel — one action, nothing running', 'en', boot().evaluate('livePanelScreen()'));
take('Vision', 'the live panel — 中文', 'zh', boot("data.sources=[{id:'s1',url:'https://www.twitch.tv/ttpoolfriday'}]", 'zh').evaluate('livePanelScreen()'));
take('Vision', 'the live workbench (the adapter fills it at runtime)', 'en', boot().evaluate('visionSurface()'));
take('Vision', 'the recorded review workbench', 'en', boot("reviewId='n1'").evaluate('visionSurface()'), 'reviewHosted() \u2192 the same surface, hosted by a night');
take('Vision', 'the Twitch sources configurator', 'en', boot("data.sources=[{id:'s1',url:'https://www.twitch.tv/ttpoolfriday'},{id:'s2',url:'https://www.twitch.tv/videos/2890514774'}]").evaluate('sourceModal()'));

// ---- the states that only exist mid-write
take('Tonight', 'a score on its way to the server (pending)', 'en', (() => {
  const h = boot(); tonightNight(h, 'drawn'); h.evaluate(LIVE + ";pendingMatches.set('mL',1)"); return h.evaluate('scoreboardScreen()');
})(), 'the pending board, not the empty one');

// ---- 2. the board
const boardCss = `
.od-board{background:var(--bg);color:var(--ink);font:var(--fs-body)/1.5 var(--body);padding:var(--sp-5);margin:0}
.od-board h1{font:600 34px/1.15 var(--display);margin:0 0 var(--sp-2)}
.od-board h2{font:600 var(--fs-xl)/1.2 var(--display);margin:var(--sp-5) 0 var(--sp-2);border-bottom:1px solid var(--line);padding-bottom:var(--sp-1)}
.od-board p{color:var(--ink-mid);max-width:96ch}
.od-board code,.od-board small{font:var(--fs-sm) var(--mono);color:var(--ink-dim)}
.od-note{background:var(--panel2);border:1px solid var(--line);border-left:3px solid var(--brass);padding:var(--sp-3) var(--sp-4);margin:var(--sp-4) 0}
.od-grid{display:grid;gap:var(--sp-5);grid-template-columns:repeat(auto-fit,minmax(min(100%,560px),1fr))}
.od-state{border:1px solid var(--line);background:var(--panel);display:flex;flex-direction:column;min-width:0}
.od-state>header{display:flex;align-items:baseline;justify-content:space-between;gap:var(--sp-2);padding:var(--sp-2) var(--sp-3);background:var(--panel2);border-bottom:1px solid var(--line);flex-wrap:wrap}
.od-state>header h4{margin:0;font:600 var(--fs-lg)/1.2 var(--display)}
.od-state>header span{font:var(--fs-xs) var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-dim)}
.od-canvas{overflow:auto;background:var(--bg);padding:var(--sp-3);min-width:0;position:relative}
/* the app's dialog backdrops are position:fixed and would cover the whole board; inside a frame they
   cover the frame, which is what a frame of a dialog should show */
.od-canvas .modal-backdrop{position:absolute;inset:0}
.od-device{max-width:1100px;margin:0 auto}
.od-note-inline{margin:0;padding:var(--sp-2) var(--sp-3);border-top:1px solid var(--line);font:var(--fs-sm) var(--mono);color:var(--ink-dim)}
.od-swatches{display:grid;gap:var(--sp-2);grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr))}
.od-sw{display:flex;align-items:center;gap:var(--sp-2)}
.od-sw i{width:26px;height:26px;border:1px solid var(--line);border-radius:2px;flex:none}
`;

const css = opsCss.replaceAll('#ops-shell', '.od-shell');
const renamed = (opsCss.match(/#ops-shell/g) || []).length;
const groups = [...new Set(frames.map(f => f.screen))];
const frameHtml = groups.map(screen => `
<h2>${esc(screen)}</h2>
<div class="od-grid">
${frames.filter(f => f.screen === screen).map(f => `  <section class="od-state">
    <header><h4>${esc(f.state)}</h4><span>${esc(f.lang === 'zh' ? '中文' : 'EN')}</span></header>
    <div class="od-canvas"><div class="od-shell od-device" data-tab="${esc(screen === 'Tonight' ? 'tonight' : screen === 'History' ? 'records' : screen === 'Vision' ? 'vision' : screen === 'Regulars' ? 'players' : screen === 'Back room' ? 'status' : 'clock')}">${f.html}</div></div>
    ${f.note ? `<p class="od-note-inline">${esc(f.note)}</p>` : ''}
  </section>`).join('\n')}
</div>`).join('\n');

const tokens = [...opsCss.matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;/g)].slice(0, 40);
const commit = fs.existsSync(path.join(ROOT, '.git')) ? '' : '';

const markupBytes = frames.reduce((n, f) => n + f.html.length, 0);
const board = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corner Pocket · Operations console — the whole UI</title>
<style>
/* Inlined from annotator/ops.css, one mechanical rename: #ops-shell -> .od-shell (${renamed} occurrences),
   so every frame below is scoped and no id is repeated. No other edit. */
${css}
${boardCss}
</style></head><body class="od-board">

<h1>Corner Pocket · Operations console — the whole UI</h1>
<p><code>${esc(frames.length)} states · ${esc(groups.length)} screens · ${esc(new Set(frames.map(f => f.lang)).size)} languages · EN + 中文</code></p>
<div class="od-note">
<strong>What this is.</strong> Every frame below is the markup the shipped console renders, taken from the
same code the browser runs (the app is booted in the test suite's own sandbox and each screen is called
directly). Nothing here is redrawn: if a frame looks wrong, the app looks wrong. The stylesheet is inlined
from <code>annotator/ops.css</code> with <code>#ops-shell</code> renamed to <code>.od-shell</code>, so the
phone rules still fire when a frame's width drops below 750 px — narrow this window to check them.
<br><strong>How to annotate.</strong> Edit anything in place, or draw on it; then the repo picks it up:
<code>~/projects/opendesign-sync/bin/odsync pull corner-pocket</code> mirrors this project into
<code>.od-sync/design/</code> with <code>DESIGN-HANDOFF.md</code>, I implement it, and
<code>odsync push corner-pocket</code> puts the built result back beside the design.
<br><strong>Not here:</strong> the app's data (every list is the test fixture), the live Vision stage's
pixels (the adapter fills that surface at runtime), and the server-side states (offline, 409, 503), which
are behaviour rather than layout.
</div>

<h2>Tokens</h2>
<div class="od-swatches">
${tokens.map(([, k, v]) => `<div class="od-sw"><i style="background:${v}"></i><code>${esc(k)}</code><small>${esc(v)}</small></div>`).join('\n')}
</div>

<h2>Rules a redesign has to keep</h2>
<p>One page, four screens (Tournament, History, Vision, Back room) plus the timer and the shells for Regulars
and the Back room; two languages, one word per concept; no sideways scroll at 390 px; words before icons; one
primary action per surface; and the console writes only through <code>/api/operations</code>.</p>
${frameHtml}

<p><small>Generated by <code>docs/opendesign/capture.mjs</code> · ${esc(opsCss.length)} bytes of stylesheet ·
${esc(frames.length)} frames · ${esc(Math.round(markupBytes))} bytes of captured markup.</small></p>
</body></html>
`;

const finalHtml = board;
const target = path.join(HERE, 'corner-pocket-ops-console.html');
fs.writeFileSync(target, finalHtml);
// ---- 3. optionally hand the board to OpenDesign (the same artifact, in place) and re-mirror it
const OD = { url: 'http://127.0.0.1:7457', project: 'corner-pocket-ops-console' };
if (process.argv.includes('--push')) {
  const file = path.basename(target);
  const r = await fetch(`${OD.url}/api/projects/${OD.project}/files`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: file, content: finalHtml }),
  });
  const pushed = await r.json().catch(() => ({}));
  console.log(JSON.stringify({ pushed: r.status, file: pushed.file?.name, size: pushed.file?.size }));
}

console.log(JSON.stringify({
  target, bytes: finalHtml.length, frames: frames.length, screens: groups.length,
  cssBytes: css.length, renamedOccurrences: renamed,
  biggest: frames.map(f => [f.state, f.html.length]).sort((a, b) => b[1] - a[1]).slice(0, 3),
}, null, 1));
