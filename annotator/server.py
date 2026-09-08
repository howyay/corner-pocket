#!/usr/bin/env python3
"""Tiny review server for the pool-shot/pot event annotator.

Serves the static app (index.html) plus two API endpoints:
  GET  /api/events      -> the events.json produced by scan_events.py
  POST /api/annotate    -> {event_id, verdict: "correct"|"wrong"|"unsure", note}
                           appended to annotations.json (persisted)
Usage: python3 server.py [events.json] [port]
"""
import json
import mimetypes
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVENTS_FILE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "events.json"
STATIC_ROOT = EVENTS_FILE.parent  # evidence images live next to events.json
ANNOT_FILE = STATIC_ROOT / "annotations.json"
# optional third arg: crop-set base dir (defaults to the first label set)
CROP_BASE = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else \
    Path("/home/operator/projects/pool/out/unlabeled_crops")
LABEL_META = CROP_BASE / "meta.json"
LABELS_FILE = CROP_BASE / "labels.json"
CROP_DIR = CROP_BASE
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8123


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quieter
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
            f = ROOT.parent / "out" / "events_actors.json"
            if not f.exists():
                return self._send(200, b"{}")
            # map by event id: events_actors.json entries carry t; events carry id+t
            try:
                ev = json.loads(EVENTS_FILE.read_bytes())
                acts = json.loads(f.read_text())
                by_t = {}
                for a in acts:
                    by_t[round(a["t"], 1)] = a
                out = {}
                for e in ev:
                    a = by_t.get(round(e["t"], 1))
                    if a:
                        out[str(e["id"])] = a
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
            ctx_file = CROP_DIR / "ctx.json"
            if ctx_file.exists():
                ctx = json.loads(ctx_file.read_text())
            for row in meta:
                row["label"] = labels.get(row["file"])
                c = ctx.get(row["file"])
                row["ctx"] = Path(c).name if c else None
            return self._send(200, json.dumps(meta).encode())
        if self.path.startswith("/ctx/"):
            p = (CROP_DIR / "ctx" / self.path[len("/ctx/"):]).resolve()
            if p.is_file():
                return self._send(200, p.read_bytes(), "image/png")
        if self.path.startswith("/crops/"):
            p = (CROP_DIR / self.path[len("/crops/"):]).resolve()
            if p.is_file() and CROP_DIR in p.parents:
                return self._send(200, p.read_bytes(), "image/jpeg")
        if self.path == "/label.html":
            body = (ROOT / "label.html").read_bytes()
            return self._send(200, body, "text/html; charset=utf-8")
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            return self._send(200, body, "text/html; charset=utf-8")
        # evidence images and other static files (served from the events dir)
        p = (STATIC_ROOT / self.path.lstrip("/")).resolve()
        if p.is_file() and STATIC_ROOT in p.parents:
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
    print(f"annotator: open http://127.0.0.1:{PORT}  (events: {EVENTS_FILE})")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
