#!/usr/bin/env python3
"""PID-6: minimal pocket-anchor click UI for the HOM-1 calibration bar.

Person clicks the 6 pocket anchors (4 corners + 2 side pockets) on chosen
frames of vod30. Clicks are stored in out/pid_anchors_vod30.json and later
replaced by person input in the PnP calibration (calib_vod30 currently uses
auto-detected anchors).

Server: GET /            -> UI
        GET /frame?t=70  -> JPEG with current anchors drawn
        GET /api/anchors -> {"anchors": {t: [[x,y]x6]}}
        POST /api/anchors-> {"t": 70, "pts": [[x,y]x6]}

Usage: python3 pid_anchor_ui.py [port]   (default 8126)
"""
import io
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from calibrate import OBJECT_MM, project  # noqa

VIDEO = ROOT.parent / "data" / "vod_30min_260815.mp4"
OUT = ROOT.parent / "out" / "pid_anchors_vod30.json"
CALIB = ROOT.parent / "out" / "calib_vod30.json"
SUGGESTED = [70, 200, 350]

H = np.array(json.load(open(CALIB))["H"])
cap = cv2.VideoCapture(str(VIDEO))

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Pocket anchors — vod30</title><style>
body{font-family:system-ui;margin:0;background:#16181d;color:#eee}
header{padding:10px 16px;border-bottom:1px solid #333;display:flex;gap:12px;align-items:center}
canvas{display:block;margin:12px auto;border:1px solid #444;cursor:crosshair}
button,input{font-size:14px;padding:6px 10px}
#status{margin-left:auto;font-size:13px;color:#9f9}
#hint{max-width:900px;margin:0 auto 8px;font-size:13px;color:#bbb}
</style></head><body>
<header>
 <b>pocket anchors</b>
 <label>t=<input id="t" type="number" value="70" step="0.5" style="width:70px"></label>
 <button id="load">load frame</button>
 <button id="prev">◀ prev</button><button id="next">next ▶</button>
 <button id="reset">reset to auto</button>
 <button id="save">💾 save anchors</button>
 <span id="status"></span>
</header>
<div id="hint">Drag a circle to move that anchor. Click near a circle then use arrow keys to
nudge (1 px; with Shift 5 px). Keys 1–6 select an anchor. Circles: 0 TL, 1 TR, 2 BR, 3 BL,
4 left-side, 5 right-side (pocket jaws at the cushion line).</div>
<canvas id="cv" width="1280" height="720"></canvas>
<script>
let t = 70, sel = -1;
const pts = [[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]];
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const img = new Image();
const SUG = [70, 200, 350];
function status(s, err){ const el = document.getElementById('status');
  el.textContent = s; el.style.color = err ? '#f99' : '#9f9'; }
async function loadAnchors(){
  const r = await fetch('/api/anchors'); const j = await r.json();
  if (j.anchors[String(t)]) { for (let i=0;i<6;i++) pts[i] = j.anchors[String(t)][i].slice(); }
  else await fetch('/api/auto?t='+t).then(r=>r.json()).then(j=>{ for (let i=0;i<6;i++) pts[i]=j.pts[i].slice(); });
}
function draw(){
  ctx.drawImage(img, 0, 0, cv.width, cv.height);
  const names = ['TL','TR','BR','BL','L-side','R-side'];
  pts.forEach((p,i)=>{ ctx.beginPath(); ctx.arc(p[0],p[1],9,0,7);
    ctx.strokeStyle = i===sel ? '#ffd400' : '#ff3355'; ctx.lineWidth = i===sel?3:2;
    ctx.stroke(); ctx.fillStyle = i===sel ? '#ffd400' : '#ff3355';
    ctx.font = 'bold 13px system-ui'; ctx.fillText(i+' '+names[i], p[0]+12, p[1]-10); });
}
img.onload = draw;
async function reload(){ await loadAnchors();
  img.src = '/frame?t='+t+'&v='+Date.now(); status('frame t='+t); }
document.getElementById('load').onclick = async ()=>{ t = parseFloat(document.getElementById('t').value)||70; await reload(); };
document.getElementById('prev').onclick = async ()=>{ t = SUG[(SUG.indexOf(t)+SUG.length-1)%SUG.length] ?? t-1;
  document.getElementById('t').value = t; await reload(); };
document.getElementById('next').onclick = async ()=>{ t = SUG[(SUG.indexOf(t)+1)%SUG.length] ?? t+1;
  document.getElementById('t').value = t; await reload(); };
document.getElementById('reset').onclick = async ()=>{
  const j = await fetch('/api/auto?t='+t).then(r=>r.json());
  for (let i=0;i<6;i++) pts[i]=j.pts[i].slice(); draw(); status('reset to auto'); };
document.getElementById('save').onclick = async ()=>{
  const r = await fetch('/api/anchors',{method:'POST',headers:{'Content-Type':'application/json'},
    body: JSON.stringify({t, pts})});
  status(r.ok ? 'saved t='+t : 'save failed', !r.ok); };
let drag = -1;
function nearest(x,y){ let b=-1,bd=1e9; pts.forEach((p,i)=>{ const d=(p[0]-x)**2+(p[1]-y)**2;
  if (d<bd){bd=d;b=i;} }); return bd<35*35 ? b : -1; }
cv.onmousedown = e=>{ const r=cv.getBoundingClientRect();
  const x=(e.clientX-r.left)*cv.width/r.width, y=(e.clientY-r.top)*cv.height/r.height;
  drag = nearest(x,y); sel = drag; draw(); };
cv.onmousemove = e=>{ if(drag<0) return; const r=cv.getBoundingClientRect();
  pts[drag]=[ (e.clientX-r.left)*cv.width/r.width, (e.clientY-r.top)*cv.height/r.height ]; draw(); };
window.onmouseup = ()=>{ drag=-1; };
window.onkeydown = e=>{ if(e.key>='1'&&e.key<='6'){ sel=+e.key-1; draw(); return; }
  const step = e.shiftKey?5:1;
  const mv = {ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]}[e.key];
  if (mv && sel>=0){ pts[sel]=[pts[sel][0]+mv[0], pts[sel][1]+mv[1]]; draw(); e.preventDefault(); } };
reload();
</script></body></html>"""


def frame_with_anchors(t, pts):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, bgr = cap.read()
    if not ok:
        return None
    if pts:
        names = ["TL", "TR", "BR", "BL", "L", "R"]
        for i, (x, y) in enumerate(pts):
            cv2.circle(bgr, (int(x), int(y)), 9, (0, 60, 255), 2)
            cv2.putText(bgr, f"{i}{names[i]}", (int(x) + 12, int(y) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 60, 255), 2)
    ok2, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return buf.tobytes() if ok2 else None


def auto_anchors():
    p = project(H, OBJECT_MM)
    return [[float(x), float(y)] for x, y in p]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path.startswith("/frame"):
            q = dict(p.split("=", 1) for p in self.path.split("?")[1].split("&")) if "?" in self.path else {}
            t = float(q.get("t", 70))
            anchors = json.loads(OUT.read_text())["anchors"] if OUT.exists() else {}
            pts = anchors.get(str(int(t)) if t == int(t) else str(t)) or auto_anchors()
            jpg = frame_with_anchors(t, pts)
            if jpg is None:
                return self._send(404, b"frame decode failed")
            return self._send(200, jpg, "image/jpeg")
        if self.path.startswith("/api/auto"):
            q = dict(p.split("=", 1) for p in self.path.split("?")[1].split("&")) if "?" in self.path else {}
            _ = float(q.get("t", 70))
            return self._send(200, json.dumps({"pts": auto_anchors()}).encode())
        if self.path == "/api/anchors":
            data = json.loads(OUT.read_text()) if OUT.exists() else {"anchors": {}}
            return self._send(200, json.dumps(data).encode())
        return self._send(404, b"not found")

    def do_POST(self):
        if self.path != "/api/anchors":
            return self._send(404, b"not found")
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, b'{"error":"bad json"}')
        t = payload.get("t")
        pts = payload.get("pts")
        if t is None or not pts or len(pts) != 6:
            return self._send(400, b'{"error":"t and 6 pts required"}')
        data = json.loads(OUT.read_text()) if OUT.exists() else {"anchors": {}}
        data["anchors"][str(t)] = [[float(x), float(y)] for x, y in pts]
        OUT.write_text(json.dumps(data, indent=1))
        return self._send(200, b'{"ok":true}')


if __name__ == "__main__":
    # legacy anchor UI: writes out/pid_anchors_vod30.json directly
    sys.path.insert(0, str(ROOT.parent))
    from src.store import refuse_file_writes_under_postgres
    refuse_file_writes_under_postgres("src/pid_anchor_ui.py")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8126
    print(f"serving on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
