#!/usr/bin/env python3
"""Generate the OpenDesign board for the Corner Pocket ops console.

The tokens are read from annotator/ops.css, so the board shows the shipped values, not a copy.
Output: docs/opendesign/corner-pocket-ops-console.html (pushed into OpenDesign by `od artifacts create`).
"""
import re
import subprocess
from pathlib import Path

ROOT = Path('/home/haoye/projects/pool')
CSS = (ROOT / 'annotator' / 'ops.css').read_text()
OUT = ROOT / 'docs' / 'opendesign'
OUT.mkdir(parents=True, exist_ok=True)


def block(selector):
    i = CSS.index(selector)
    return CSS[i:CSS.index('}', i)]


def tokens(selector):
    out = {}
    for name, value in re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', block(selector)):
        out[name] = value.strip()
    return out


dark, light = tokens(':root{'), tokens(':root[data-theme=light]')
COMMIT = subprocess.run(['git', '-C', str(ROOT), 'log', '-1', '--format=%h %s'], capture_output=True, text=True).stdout.strip()

WANT = ['--bg', '--panel', '--panel2', '--rail', '--line', '--line2', '--brass', '--brass-hi', '--brass-fg',
        '--ink', '--ink-mid', '--ink-dim', '--ink-faint', '--red', '--green', '--blue', '--amber', '--live-bg',
        '--display', '--body', '--mono', '--fs-xs', '--fs-sm', '--fs-md', '--fs-lg', '--fs-xl', '--fs-body',
        '--sp-1', '--sp-1h', '--sp-2', '--sp-3', '--sp-4', '--sp-5', '--radius', '--shadow']
pairs = [(k, dark.get(k, ''), light.get(k, '')) for k in WANT if k in dark]
balls = [(k, v) for k, v in sorted(dark.items()) if k.startswith('--ball-')][:16]

swatches = '\n'.join(
    f'<div class="sw"><span style="background:{v}"></span><code>{k}</code><small>{v}</small></div>'
    for k, v, _ in pairs if v.startswith('#'))
ballw = '\n'.join(f'<div class="sw"><span style="background:{v}"></span><code>{k}</code><small>{v}</small></div>' for k, v in balls)
vars_css = '\n'.join(f'  {k}: {v};' for k, v, _ in pairs)

HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Corner Pocket · Operations console — design board</title>
<style>
:root{{
{vars_css}
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:var(--fs-body)/1.5 var(--body);padding:var(--sp-5)}}
h1{{font:600 34px/1.1 var(--display);margin:0 0 var(--sp-2)}}
h2{{font:600 var(--fs-xl)/1.2 var(--display);margin:var(--sp-5) 0 var(--sp-2);border-bottom:1px solid var(--line);padding-bottom:var(--sp-1)}}
h3{{font:600 var(--fs-lg)/1.2 var(--display);margin:var(--sp-4) 0 var(--sp-2)}}
p{{margin:0 0 var(--sp-2);color:var(--ink-mid)}}
code,small{{font:var(--fs-sm) var(--mono);color:var(--ink-dim)}}
.note{{background:var(--panel2);border:1px solid var(--line);border-left:3px solid var(--brass);padding:var(--sp-3) var(--sp-4);margin:var(--sp-4) 0}}
.board{{display:grid;gap:var(--sp-4);grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr))}}
.frame{{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--brass);padding:var(--sp-3);position:relative}}
.frame>h3{{margin-top:0}}
.frame .tag{{position:absolute;top:var(--sp-2);right:var(--sp-2);font:var(--fs-xs) var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--brass-hi)}}
.row{{display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap}}
.heading{{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-2);flex-wrap:wrap}}
button{{font:inherit;min-height:40px;padding:0 var(--sp-3);background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:var(--radius);cursor:pointer}}
button.primary{{background:var(--brass);color:var(--brass-fg);border-color:var(--brass)}}
button.danger{{color:var(--red);border-color:var(--line)}}
button:disabled{{opacity:.45;cursor:not-allowed}}
.badge{{display:inline-flex;align-items:center;gap:var(--sp-1);padding:var(--sp-1) var(--sp-2);border:1px solid var(--line);border-radius:2px;font:var(--fs-xs) var(--mono);letter-spacing:.16em;text-transform:uppercase;color:var(--ink-dim)}}
.badge.live{{border-color:var(--amber);color:var(--amber)}}
.card{{border:1px solid var(--line);background:var(--panel);padding:var(--sp-4)}}
.muted{{color:var(--ink-dim)}}
table{{width:100%;border-collapse:collapse;font:var(--fs-sm) var(--body)}}
td,th{{padding:var(--sp-2);border-bottom:1px solid var(--line);text-align:left}}
.sw{{display:flex;align-items:center;gap:var(--sp-2);margin:2px 0}}
.sw span{{width:26px;height:26px;border:1px solid var(--line);border-radius:2px;flex:none}}
.grid3{{display:grid;gap:var(--sp-2);grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr))}}
/* the console's own components, as they ship */
.scene{{font:var(--fs-sm) var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-dim)}}
.toolbar{{display:flex;flex-wrap:wrap;align-items:center;gap:var(--sp-2);margin-top:var(--sp-3)}}
.toolbar input{{flex:1 1 240px;min-height:42px;background:var(--panel2);border:1px solid var(--line);border-bottom:2px solid var(--line);color:var(--ink);padding:0 var(--sp-3);font:inherit}}
.toolbar-gap{{flex:1 1 auto}}
.rounds{{display:grid;gap:var(--sp-3);grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr))}}
.round h3{{font-size:var(--fs-lg);margin:0 0 var(--sp-2)}}
.entry{{border:1px solid var(--line);background:var(--panel2);padding:var(--sp-1) var(--sp-2);display:flex;flex-direction:column;gap:2px}}
.entry+.entry{{margin-top:var(--sp-1)}}
.entry.live{{border-left:3px solid var(--brass);background:var(--live-bg)}}
.entry.held{{border-left:3px solid var(--amber)}}
.side{{display:flex;align-items:center;gap:var(--sp-1h)}}
.dot{{width:8px;height:8px;border-radius:50%;background:var(--blue);flex:none}}
.entry.live .dot{{background:var(--amber)}}
.table-chip{{font:var(--fs-xs) var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--brass-hi);border:1px solid var(--line);border-radius:2px;padding:0 var(--sp-1h)}}
.scoreboard{{border:1px solid var(--line);border-top:3px solid var(--brass);background:var(--panel)}}
.score-top{{display:flex;align-items:center;gap:var(--sp-2);padding:var(--sp-2) var(--sp-4);background:var(--panel2);border-bottom:1px solid var(--line);font:var(--fs-sm) var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-dim)}}
.side-big{{padding:var(--sp-3) var(--sp-4);display:flex;align-items:center;justify-content:space-between;gap:var(--sp-3)}}
.name{{font:600 clamp(24px,3vw,40px)/1 var(--display)}}
.digits{{font:600 34px var(--display);color:var(--brass-hi)}}
.timer-card{{border:1px solid var(--line);background:var(--panel);padding:var(--sp-5);display:grid;gap:var(--sp-3)}}
.clock{{font:600 76px/1 var(--display);letter-spacing:-.02em}}
.presets button{{min-height:32px}}
.modal{{border:1px solid var(--line);border-top:3px solid var(--brass);background:var(--panel);padding:var(--sp-4) var(--sp-5);max-width:520px}}
.fields{{display:grid;gap:var(--sp-3);grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr))}}
label span{{display:block;font:var(--fs-xs) var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--ink-dim)}}
input,select{{width:100%;min-height:42px;background:var(--panel2);border:1px solid var(--line);border-bottom:2px solid var(--line);color:var(--ink);padding:0 var(--sp-3);font:inherit}}
details.side-panel{{margin-top:var(--sp-3)}}
details.side-panel>summary{{cursor:pointer;font:var(--fs-sm) var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-dim);min-height:40px;display:flex;align-items:center}}
.callout{{display:flex;gap:var(--sp-2);margin:var(--sp-1) 0;align-items:flex-start}}
.callout b{{flex:none;width:22px;height:22px;border:1px solid var(--brass);border-radius:50%;color:var(--brass-hi);font:var(--fs-xs) var(--mono);display:grid;place-items:center}}
</style></head><body>

<h1>Corner Pocket · Operations console</h1>
<p class="scene">Design board · {COMMIT}</p>
<div class="note">
<strong>How this board works.</strong> This is the console that ships: the same tokens, the same components,
the same four screens, rebuilt as live HTML so you can move, delete or restyle anything here. Annotate in
OpenDesign and the change comes back to the repo with
<code>./bin/odsync pull</code> (mirror in <code>.od-sync/design/</code> + <code>DESIGN-HANDOFF.md</code>),
where I implement it and push the built result back with <code>odsync push</code>.
<br>Contract worth knowing while you redesign: the console is <em>one page, four screens</em> (Tonight,
History, Vision, Back room), two languages (EN / 中文) and two themes (dark / light). Every control is a word
plus a keyboard shortcut, the phone layout is the same markup, and no screen may scroll sideways at 390 px.
</div>

<h2>Tokens — dark (shipped)</h2>
<div class="grid3">{swatches}</div>
<h2>Tokens — light theme</h2>
<div class="grid3">{''.join(f'<div class="sw"><span style="background:{v}"></span><code>{k}</code><small>{v}</small></div>' for k, _, v in pairs if v.startswith('#'))}</div>
<h2>The ball palette (nav + bracket + board share it)</h2>
<div class="grid3">{ballw}</div>

<h2>Components</h2>
<div class="board">
  <div class="frame"><span class="tag">buttons</span><h3>Buttons</h3>
    <div class="row"><button>Secondary</button><button class="primary">Primary</button><button class="danger">Danger</button><button disabled>Disabled</button></div>
    <p><small>40 px minimum, 44 px for the send control. One primary per surface.</small></p></div>
  <div class="frame"><span class="tag">badges & chips</span><h3>Badges, chips, table chip</h3>
    <div class="row"><span class="badge">Racked</span><span class="badge live">Live</span><span class="badge">Race to 5</span>
      <span class="table-chip">Table 2</span><span class="badge">— · eac2765c</span></div>
    <p><small>Uppercase mono, 0.16em tracking. The table chip answers "which table" without a hover.</small></p></div>
  <div class="frame"><span class="tag">fold</span><h3>Panel fold (event table)</h3>
    <details class="side-panel" open><summary>Event table</summary>
      <table><thead><tr><th>#</th><th>Name</th><th>W</th><th>P</th><th>%</th></tr></thead>
      <tbody><tr><td>1</td><td>Kenji Watanabe</td><td>4</td><td>5</td><td>80%</td></tr>
      <tr><td>2</td><td>Tomás Ibarra</td><td>3</td><td>5</td><td>60%</td></tr></tbody></table></details></div>
  <div class="frame"><span class="tag">match card</span><h3>Bracket card — idle, live, held</h3>
    <div class="entry"><div class="side"><i class="dot"></i><span class="muted">Waiting</span><span class="muted" style="margin-left:auto">0</span></div>
      <div class="side"><i class="dot"></i><span class="muted">Waiting</span><span class="muted" style="margin-left:auto">0</span></div></div>
    <div class="entry live"><div class="side"><i class="dot"></i><span class="table-chip">Table 1</span><b class="grow">Kenji Watanabe</b><b>3</b></div>
      <div class="side"><i class="dot"></i><b class="grow">Tomás Ibarra</b><b>1</b></div></div>
    <div class="entry held"><div class="side"><i class="dot"></i><span class="table-chip">Table 3</span><b class="grow">吴天成</b><b>0</b></div>
      <div class="side"><i class="dot"></i><b class="grow">Danny Lau</b><b>0</b></div></div></div>
  <div class="frame"><span class="tag">timer</span><h3>Shot timer</h3>
    <div class="timer-card"><strong class="clock">0:30</strong>
      <div class="row"><button class="primary">Start</button><button>Reset</button>
        <span class="row presets"><button>20</button><button class="primary">30</button><button>45</button><button>60</button></span></div></div></div>
  <div class="frame"><span class="tag">dialog</span><h3>Event settings (Save and Close, one row)</h3>
    <div class="modal"><h3 style="margin-top:0">Event settings</h3>
      <div class="fields"><label><span>Event</span><input value="8-Ball Open · Fri 10/2"></label>
        <label><span>Format</span><select><option>Singles</option><option>Doubles</option></select></label>
        <label><span>Race to</span><select><option>5</option></select></label>
        <label><span>Tables</span><input value="6"></label></div>
      <div class="row" style="margin-top:var(--sp-3)"><button class="primary">Save</button><button>Close</button></div></div></div>
</div>

<h2>The four screens</h2>
<div class="board">
  <div class="frame"><span class="tag">1 · tonight</span><h3>Tournament — three elements</h3>
    <p class="scene">Tournament · 8-Ball Open · Fri 10/2 · Singles · Race to 5</p>
    <div class="card" style="margin-top:var(--sp-2)"><div class="heading"><h3 style="margin:0">Event settings</h3></div>
      <div class="row" style="margin-top:var(--sp-2)"><button>Event settings</button><button>Results sheet</button><button>Archive &amp; new event</button><button class="danger" disabled>Delete event</button></div>
      <p class="muted" style="margin-top:var(--sp-2)">Delete is off because a result is signed; archiving keeps the results in the history.</p></div>
    <div class="card" style="margin-top:var(--sp-3)"><div class="heading"><h3 style="margin:0">Bracket</h3><span class="muted">4/15 signed · 3 on table · 1 delayed · 2 to send</span></div>
      <div class="rounds" style="margin-top:var(--sp-2)">
        <div class="round"><h3>Round 1</h3>
          <div class="entry live"><div class="side"><i class="dot"></i><span class="table-chip">Table 1</span><b class="grow">Kenji Watanabe</b><b>3</b></div>
            <div class="side"><i class="dot"></i><b class="grow">Tomás Ibarra</b><b>1</b></div></div>
          <div class="entry"><div class="side"><i class="dot"></i><span class="muted">Waiting</span><span class="muted" style="margin-left:auto">0</span></div>
            <div class="side"><i class="dot"></i><span class="muted">Waiting</span><span class="muted" style="margin-left:auto">0</span></div></div></div>
        <div class="round"><h3>Round 2</h3>
          <div class="entry"><div class="side"><i class="dot"></i><b class="grow">林小满</b><b>0</b></div>
            <div class="side"><i class="dot"></i><b class="grow">赵启明</b><b>0</b></div></div></div>
      </div></div>
    <div class="card" style="margin-top:var(--sp-3)"><div class="heading"><h3 style="margin:0">Entrants</h3><span class="muted">16 · 5 Guests tonight</span></div>
      <div class="row" style="margin-top:var(--sp-2)"><span class="badge">1</span><b>Kenji Watanabe</b><small>Regular</small><span class="badge">2</span><b>Tomás Ibarra</b><small>Regular</small></div>
      <details class="side-panel"><summary>Event table</summary><p class="muted" style="margin:0">The table moved into this card (round 14, item 1).</p></details></div>
    <div class="callout"><b>1</b><span>The three elements in this order: Event settings, Bracket, Entrants. Nothing else belongs on this tab.</span></div>
    <div class="callout"><b>2</b><span>The event card carries the night's end. The Back room does not repeat it.</span></div>
    <div class="callout"><b>3</b><span>One bracket view: a grid of rounds that wraps. No density switch.</span></div>
  </div>

  <div class="frame"><span class="tag">2 · history</span><h3>History — heading, then one toolbar</h3>
    <div class="heading"><h2 style="border:0;margin:0">History</h2><span class="muted">31 broadcasts · 0 linked to an event</span></div>
    <div class="toolbar"><input placeholder="Search names"><button>Show 2 hidden</button><span class="toolbar-gap"></span>
      <button>Sources</button><button>Refresh</button><button class="primary">Backfill a past event from a Twitch VOD…</button></div>
    <p class="muted">Every broadcast the channel keeps, newest first. A row is a built night or a night to build.</p>
    <div class="card" style="margin-top:var(--sp-2)"><div class="row"><b>Friday 8-Ball Open</b><span class="badge">Built</span></div>
      <small>Sat 3 Oct 2026 · 3 nights · 2 broadcasts linked</small></div>
    <div class="callout"><b>4</b><span>The count is information: it lives in the heading, not between the buttons.</span></div>
    <div class="callout"><b>5</b><span>The search leads and grows; the one primary action is last; on a phone the buttons wrap under the search.</span></div>
  </div>

  <div class="frame"><span class="tag">3 · vision</span><h3>Vision — the stream, not a toggle</h3>
    <div class="card"><div class="heading"><h2 style="border:0;margin:0">Live stream</h2><span class="muted">idle · Frame age: — ms · Dropped: 0</span></div>
      <div class="row" style="margin-top:var(--sp-2)"><span class="badge live">● Live · twitch cornerpocket</span><span class="badge">Live · twitch ttpoolsunday</span></div>
      <div class="row" style="margin-top:var(--sp-2)"><label class="row"><input type="checkbox" checked style="width:auto"> Table</label>
        <label class="row"><input type="checkbox" checked style="width:auto"> Person</label>
        <label class="row"><input type="checkbox" checked style="width:auto"> Ball</label></div>
      <div class="row" style="margin-top:var(--sp-2)"><button class="primary">Start</button><button>Sources</button><button>History →</button></div>
      <p class="muted" style="margin-top:var(--sp-2)">Start the stream and this tab becomes the live workbench. Recorded nights are reviewed from their row on History.</p></div>
    <div class="card" style="margin-top:var(--sp-3)"><div class="heading"><h3 style="margin:0">A recorded review (opened from History)</h3><span class="muted">no clip chooser, no source chooser</span></div>
      <p class="muted" style="margin-top:var(--sp-2)">The clip is chosen in the timeline. The workbench then shows the frame, the cues, the queue and the tracks — and no "which clip" chips.</p>
      <div class="scoreboard" style="margin-top:var(--sp-2)"><div class="score-top"><span class="badge live">On table</span><span>Table 1 · eac2765c</span><span style="margin-left:auto" class="badge">Race to 5</span></div>
        <div class="side-big"><span class="name">Kenji Watanabe</span><span class="digits">3</span></div>
        <div class="side-big"><span class="name">Tomás Ibarrra</span><span class="digits">1</span></div></div></div>
    <div class="callout"><b>6</b><span>One action when nothing runs; Stop lives on the running workbench.</span></div>
    <div class="callout"><b>7</b><span>A recorded review offers no source or clip chooser.</span></div>
  </div>

  <div class="frame"><span class="tag">4 · back room</span><h3>Back room</h3>
    <div class="card"><h3 style="margin-top:0">Notes</h3><textarea rows="3" placeholder="A note for the night" style="width:100%;background:var(--panel2);color:var(--ink);border:1px solid var(--line);padding:var(--sp-2);font:inherit"></textarea>
      <div class="row" style="margin-top:var(--sp-2)"><button>Add note</button></div></div>
    <div class="card" style="margin-top:var(--sp-3)"><details class="side-panel"><summary>For maintainers</summary>
      <table><tbody><tr><td>Revision</td><td>51</td></tr><tr><td>Persist</td><td>/api/operations</td></tr><tr><td>Observation</td><td>Not connected</td></tr></tbody></table></details></div>
    <div class="callout"><b>8</b><span>The night's end left this room: it is on the tournament tab.</span></div>
  </div>
</div>

<h2>Rules the redesign has to keep</h2>
<table><tbody>
<tr><td>One page, four screens</td><td>Tonight · History · Vision · Back room. No second-level navigation, no sub-tabs.</td></tr>
<tr><td>Two languages, one word per concept</td><td>Every string exists in EN and 中文; <code>t('key')</code> falls back to the key, so a missing pair shows up as raw text.</td></tr>
<tr><td>No sideways scroll</td><td>390 px and 1280 px are measured after every change; <code>scrollWidth</code> must equal <code>innerWidth</code>.</td></tr>
<tr><td>Words before icons</td><td>A control is named by a word. Balls are decoration with a number, never the only label.</td></tr>
<tr><td>One primary per surface</td><td>One brass button on a screen. Everything else is secondary.</td></tr>
<tr><td>Read-only evidence</td><td>The console writes only through <code>/api/operations</code>; the results sheet and the review never write.</td></tr>
</tbody></table>

<p class="muted">Generated from the shipped stylesheet on {COMMIT} · tokens read from <code>annotator/ops.css</code> · screens measured in <code>out/r14/</code>.</p>
</body></html>
"""

target = OUT / 'corner-pocket-ops-console.html'
target.write_text(HTML)
print('board written: %s (%d bytes, %d tokens, %d ball colours)' % (target, len(HTML), len(pairs), len(balls)))
