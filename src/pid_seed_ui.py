#!/usr/bin/env python3
"""PID-6 player seed UI (port 8127): person clicks the player for one track
per frame; then embedding prototypes are rebuilt from the clicked person and
propagated through all tracklets (out/pid_seed_protos.json + track map).

Serves:
  GET  /                     -> UI (click a person circle in the preview)
  GET  /tracklets            -> list of windows & track ids w/ sample counts
  GET  /frame?win=68-94&t=68 -> JPEG with ALL track boxes drawn (labelled)
  POST /seed                 -> {"win","t","track_id"} records the click
  GET  /api/seed             -> current seeds
  POST /rebuild              -> rebuild prototypes + per-track identity map
                                (runs async, pid_seed_rebuild.py logic inline)

Usage: python3 pid_seed_ui.py [port]
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
VIDEO = ROOT.parent / "data" / "vod_30min_260815.mp4"
TR = ROOT.parent / "out" / "pid2_tracklets.json"
SEED = ROOT.parent / "out" / "pid_seed.json"
PROTO = ROOT.parent / "out" / "pid_seed_protos.json"
TRK = ROOT.parent / "out" / "pid_seed_tracks.json"

tr = json.load(open(TR))
cap = cv2.VideoCapture(str(VIDEO))
_state = {"rebuilding": False}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>player seeds</title>
<style>body{font-family:system-ui;margin:0;background:#16181d;color:#eee}
header{padding:10px 16px;border-bottom:1px solid #333;display:flex;gap:10px;align-items:center}
button{font-size:14px;padding:6px 12px}
#wrap{position:relative;width:1280px;margin:10px auto}
canvas{display:block;border:1px solid #444}
#ov{position:absolute;inset:0}
#status{margin-left:auto;color:#9f9}
#hint{max-width:1280px;margin:0 auto;font-size:13px;color:#bbb;padding:4px 16px}
select,input{font-size:14px;padding:4px 6px;background:#23262d;color:#eee;border:1px solid #3a3f48}
</style></head><body>
<header>
 <select id="win"></select>
 <label>t <input id="t" type="number" step="0.5" style="width:70px"></label>
 <button id="load">load</button><button id="prev">◀</button><button id="next">▶</button>
 <button id="save">💾 save seed (click first)</button>
 <button id="rebuild" style="background:#2563eb;color:#fff">⚡ rebuild prototypes</button>
 <span id="status"></span>
</header>
<div id="hint">Pick the window &amp; a track time, click INSIDE the box of the person who is
player A (light top) — the other long track is B. Keys: ←/→ step 1 s.</div>
<div id="wrap"><canvas id="cv" width="1280" height="720"></canvas>
<canvas id="ov" width="1280" height="720"></canvas></div>
<script>
const windows = Object.keys(TRACKLETS);
let win = windows[0], sel = null, drawn = [];
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const ov = document.getElementById('ov'), octx = ov.getContext('2d');
const img = new Image();
img.onload = ()=>{ ctx.drawImage(img,0,0); octx.clearRect(0,0,1280,720); };
function status(s,err){const el=document.getElementById('status');el.textContent=s;el.style.color=err?'#f99':'#9f9';}
async function load(){
  const r = await fetch(`/frame?win=${win}&t=${t}`); if(!r.ok){status('frame failed',1);return;}
  const j = await r.json(); drawn = j.boxes;
  img.src = 'data:image/jpeg;base64,'+j.jpg;
}
octx.parent = cv;
ov.onmousedown = e=>{
  const r = ov.getBoundingClientRect();
  const x = (e.clientX-r.left)*1280/r.width, y = (e.clientY-r.top)*720/r.height;
  let best=null,bd=1e12;
  drawn.forEach(b=>{ const cx=(b.box[0]+b.box[2])/2, cy=(b.box[1]+b.box[3])/2;
    const d=(cx-x)**2+(cy-y)**2; if(d<bd){bd=d;best=b;} });
  if(best){ sel=best.track_id; status('selected track '+best.track_id+' — click 💾 save'); drawOv(); }
};
function drawOv(){
  octx.clearRect(0,0,1280,720);
  drawn.forEach(b=>{
    octx.strokeStyle = b.track_id===sel ? '#ffd400' : (b.seed?'#22c55e':'#ff3355');
    octx.lineWidth = b.track_id===sel ? 4 : 2;
    octx.strokeRect(b.box[0],b.box[1],b.box[2]-b.box[0],b.box[3]-b.box[1]);
    octx.font='bold 13px system-ui'; octx.fillStyle=octx.strokeStyle;
    octx.fillText((b.seed?'✔seed ':'')+b.track_id, b.box[0], b.box[1]-4);
  });
}
document.getElementById('win').onchange = e=>{ win=e.target.value; };
document.getElementById('load').onclick = load;
document.getElementById('prev').onclick = ()=>{ t-=1; document.getElementById('t').value=t; load(); };
document.getElementById('next').onclick = ()=>{ t+=1; document.getElementById('t').value=t; load(); };
document.getElementById('save').onclick = async ()=>{
  if(sel==null){status('click a box first',1);return;}
  const r = await fetch('/seed',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({win,t,track_id:sel})});
  status(r.ok?'seed saved':'save failed', !r.ok); load();
};
document.getElementById('rebuild').onclick = async ()=>{
  status('rebuilding prototypes…');
  const r = await fetch('/rebuild',{method:'POST'});
  const j = await r.json();
  status(r.ok ? ('done: '+JSON.stringify(j.map)) : 'rebuild failed', !r.ok);
  drawn.forEach(b=>{ b.seed = (j.map[b.track_id]||'').startsWith(b.track_id+':'); });
  load();
};
window.onkeydown = e=>{ if(e.key==='ArrowLeft'){t-=0.5;document.getElementById('t').value=t;load();}
  if(e.key==='ArrowRight'){t+=0.5;document.getElementById('t').value=t;load();} };
const TRACKLETS = __TRACKLETS__;
const winSel = document.getElementById('win');
windows.forEach(w=>{ const o=document.createElement('option'); o.textContent=w; winSel.appendChild(o); });
let t = TRACKLETS[win][0].samples[0][0];
document.getElementById('t').value = t;
load();
</script></body></html>"""


def find_track(win, tid):
    for t in tr[win]["tracklets"]:
        if t["id"] == tid:
            return t
    return None


def sample_near(win, t):
    """Nearest available sample time in the window's longest tracks."""
    best = None
    for tk in tr[win]["tracklets"]:
        for tt, box in tk["samples"]:
            if best is None or abs(tt - t) < abs(best[0] - t):
                best = (tt, tk["id"], box)
    return best


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
            page = PAGE.replace("__TRACKLETS__", json.dumps(
                {w: [{"id": tk["id"], "dur": tk["dur"], "n": tk["n"],
                      "samples": tk["samples"]} for tk in tr[w]["tracklets"]]
                 for w in tr}))
            return self._send(200, page.encode(), "text/html; charset=utf-8")
        if self.path.startswith("/frame"):
            q = dict(p.split("=", 1) for p in self.path.split("?")[1].split("&"))
            win, t = q["win"], float(q["t"])
            tt, tid, box = sample_near(win, t)
            cap.set(cv2.CAP_PROP_POS_MSEC, tt * 1000)
            ok, bgr = cap.read()
            if not ok:
                return self._send(404, b'{"error":"frame"}')
            boxes = []
            seeds = json.loads(SEED.read_text())["seeds"] if SEED.exists() else {}
            for tk in tr[win]["tracklets"]:
                for s, b in tk["samples"]:
                    if abs(s - tt) < 0.6:
                        boxes.append({"track_id": tk["id"], "box": b,
                                      "seed": f"{tk['id']}:{win}" in seeds})
            ok2, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            import base64
            return self._send(200, json.dumps({
                "jpg": base64.b64encode(buf).decode(), "boxes": boxes,
                "used_t": tt, "used_track": tid}).encode())
        if self.path == "/api/seed":
            data = json.loads(SEED.read_text()) if SEED.exists() else {"seeds": {}}
            return self._send(200, json.dumps(data).encode())
        return self._send(404, b"not found")

    def do_POST(self):
        if self.path == "/seed":
            n = int(self.headers.get("Content-Length", 0))
            try:
                p = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, b'{"error":"bad json"}')
            win, t, tid = p["win"], p["t"], p["track_id"]
            tk = find_track(win, int(tid))
            if tk is None:
                return self._send(404, b'{"error":"track not found"}')
            data = json.loads(SEED.read_text()) if SEED.exists() else {"seeds": {}}
            data["seeds"][f"{tid}:{win}"] = {"win": win, "t": t, "track_id": int(tid)}
            SEED.write_text(json.dumps(data, indent=1))
            return self._send(200, b'{"ok":true}')
        if self.path == "/rebuild":
            if _state["rebuilding"]:
                return self._send(202, b'{"status":"already running"}')
            _state["rebuilding"] = True
            threading.Thread(target=_rebuild, daemon=True).start()
            return self._send(202, b'{"status":"started"}')
        return self._send(404, b"not found")


def _rebuild():
    try:
        sys.path.insert(0, str(ROOT))
        from pid_seed_rebuild import run
        run()
    finally:
        _state["rebuilding"] = False


if __name__ == "__main__":
    # legacy seed UI: writes out/pid_seed.json directly
    sys.path.insert(0, str(ROOT.parent))
    from src.store import refuse_file_writes_under_postgres
    refuse_file_writes_under_postgres("src/pid_seed_ui.py")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8127
    print(f"serving on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
