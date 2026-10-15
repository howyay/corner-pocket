#!/usr/bin/env python3
"""Tiny review server for the pool-shot/pot event annotator.

Serves the static app (index.html) plus six API endpoints:
  GET  /api/events      -> the events.json produced by scan_events.py
  POST /api/annotate    -> {event_id, verdict: "correct"|"wrong"|"unsure", note}
                           appended to annotations.json (persisted)
  GET  /api/annotations -> the annotations.json this server wrote
  GET  /api/actors      -> the actor index of the scan folder
  GET  /api/crops       -> the crop files of one ball set
  POST /api/ball_label  -> {crop, label} written to the labels.json of that set
Usage: python3 server.py [events.json] [port]
"""
import json
import mimetypes
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
# The rule for one reply body has one owner, src/reply_body.py. The two pid_*_ui
# servers call the same function. Before this module called it, the three Handler
# classes held three copies of that rule and no test compared them.
from src.reply_body import write_reply  # noqa: E402
# The rule for the file a route may read has one owner, src/served_files.py. The review
# API (annotator/unified_server.py) calls the same two functions. Before this module
# called them, its three file routes held three copies of that rule and the /ctx/ route
# held none, so a request with ".." in it read any file the user could read.
from src.served_files import file_under, relative_under  # noqa: E402
# The rule that joins an event to its actor has one owner, src/events_actors.py. The
# review API (annotator/unified_server.py) calls the same function. Before this module
# called it, the two servers held two tolerances for one file: this route rounded both
# times to a tenth of a second and the API compared them within 0.01 s, so one actor row
# joined an event here and joined no event there.
from src.events_actors import join_events_to_actors  # noqa: E402
# The crop-set vocabulary has one owner, src/store_files.py. The three offline tools
# read BALL_SETS from it. Before this module read it, the default of its third
# argument spelled the first crop-set name a second time. The two documents this
# server serves (the verdicts file beside events.json and the labels file of the crop
# base) are the documents the store reads; document_name answers both from that home.
from src.store_files import CTX_DOCUMENT, META_DOCUMENT, crops_dir  # noqa: E402
from src.store_files import BALL_SETS, document_name  # noqa: E402
from src.store import SHARED_ARTIFACTS  # noqa: E402
EVENTS_FILE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "events.json"
STATIC_ROOT = EVENTS_FILE.parent  # evidence images live next to events.json
ANNOT_FILE = STATIC_ROOT / document_name("verdicts")
# optional third arg: crop-set base dir (defaults to the first label set)
CROP_BASE = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else \
    ROOT.parent / crops_dir(BALL_SETS[0])
LABEL_META = CROP_BASE / META_DOCUMENT
LABELS_FILE = CROP_BASE / document_name("labels")
CROP_DIR = CROP_BASE
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8123


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quieter
        pass

    def _send(self, code, body, ctype="application/json"):
        return write_reply(self, code, body, ctype)

    def do_GET(self):
        if self.path == "/api/events":
            if not EVENTS_FILE.exists():
                return self._send(404, b'{"error":"events.json not found"}')
            data = EVENTS_FILE.read_bytes()
            return self._send(200, data)
        if self.path == "/api/annotations":
            if not ANNOT_FILE.exists():
                return self._send(200, b"{}")
            return self._send(200, ANNOT_FILE.read_bytes())
        if self.path == "/api/actors":
            f = ROOT.parent / "out" / SHARED_ARTIFACTS["event_actors"]
            if not f.exists():
                return self._send(200, b"{}")
            # map by event id: events_actors.json entries carry t; events carry id+t
            try:
                ev = json.loads(EVENTS_FILE.read_bytes())
                acts = json.loads(f.read_text())
                out = join_events_to_actors(ev, acts)
                return self._send(200, json.dumps(out).encode())
            except Exception:
                return self._send(200, b"{}")
        if self.path == "/label":
            body = (ROOT / "label.html").read_bytes()
            return self._send(200, body, "text/html; charset=utf-8")
        if self.path == "/api/crops":
            if not LABEL_META.exists():
                return self._send(404, b'{"error":"no crops collected yet"}')
            labels = {}
            if LABELS_FILE.exists():
                labels = json.loads(LABELS_FILE.read_text())
            meta = json.loads(LABEL_META.read_text())
            ctx = {}
            ctx_file = CROP_DIR / CTX_DOCUMENT
            if ctx_file.exists():
                ctx = json.loads(ctx_file.read_text())
            for row in meta:
                row["label"] = labels.get(row["file"])
                c = ctx.get(row["file"])
                row["ctx"] = Path(c).name if c else None
            return self._send(200, json.dumps(meta).encode())
        if self.path.startswith("/ctx/"):
            p = file_under(CROP_DIR / "ctx", self.path[len("/ctx/"):])
            if p:
                return self._send(200, p.read_bytes(), "image/png")
        if self.path.startswith("/crops/"):
            p = file_under(CROP_DIR, self.path[len("/crops/"):])
            if p:
                return self._send(200, p.read_bytes(), "image/jpeg")
        if self.path == "/label.html":
            body = (ROOT / "label.html").read_bytes()
            return self._send(200, body, "text/html; charset=utf-8")
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            return self._send(200, body, "text/html; charset=utf-8")
        # evidence images and other static files (served from the events dir). A static
        # path may carry subdirectories, so this route uses the wider shape of the rule.
        p = relative_under(STATIC_ROOT, self.path.lstrip("/"))
        if p:
            ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            return self._send(200, p.read_bytes(), ctype)
        return self._send(404, b"not found")

    def do_POST(self):
        if self.path == "/api/ball_label":
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n) or b"{}")
            labels = {}
            if LABELS_FILE.exists():
                labels = json.loads(LABELS_FILE.read_text())
            file = payload.get("file")
            label = payload.get("label")  # 0..15, "u"=unsure, "clear"=remove
            if label == "clear":
                labels.pop(file, None)
            elif file and label is not None:
                labels[file] = label
            LABELS_FILE.write_text(json.dumps(labels, indent=1))
            return self._send(200, json.dumps({"ok": True}).encode())
        if self.path != "/api/annotate":
            return self._send(404, b"not found")
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, b'{"error":"bad json"}')
        event_id = payload.get("event_id")
        if event_id is None:
            return self._send(400, b'{"error":"event_id required"}')
        ann = {}
        if ANNOT_FILE.exists():
            ann = json.loads(ANNOT_FILE.read_text())
        ann[str(event_id)] = {
            "verdict": payload.get("verdict", "unsure"),
            "note": payload.get("note", ""),
            "shooter": payload.get("shooter", ""),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        ANNOT_FILE.write_text(json.dumps(ann, indent=1))
        return self._send(200, json.dumps({"ok": True}).encode())


if __name__ == "__main__":
    # legacy single-page annotator: writes annotations.json / labels.json directly
    from src.store import refuse_file_writes_under_postgres
    refuse_file_writes_under_postgres("annotator/server.py")
    print(f"annotator: open http://127.0.0.1:{PORT}  (events: {EVENTS_FILE})")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
