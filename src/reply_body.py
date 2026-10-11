"""The only module in this repository that writes one HTTP reply body.

Three handlers in this repository answer a request the same way: the review server
`annotator/server.py`, the pocket-anchor UI `src/pid_anchor_ui.py`, and the player-seed
UI `src/pid_seed_ui.py`. Before round 55 each of the three held its own `_send` method.
The three bodies were the same statements, so a change of the reply shape had to land in
three files, and no test compared them. The walk of `tests/test_duplicate_bodies.py`
reads the top level of a module only, so it never saw the three copies.

`write_reply(handler, code, body, ctype)` writes one reply on the socket of one handler:
the status line, the content type, the content length, the empty line, and the body
bytes. `len(body)` states the content length, so the count is the count of the bytes
that follow, and the count stays correct for any bytes object.

The rule needs a handler object only. The object supplies `send_response`,
`send_header`, `end_headers`, and `wfile`. The three callers pass `self` from a method of
a `BaseHTTPRequestHandler` subclass. The function does not import one.

What this function does not do:
  * It does not encode a string. `body` must be a bytes object. A text body is the job of
    the caller, because the caller knows the charset.
  * It does not hold the connection open, and it does not flush. The server does that.
  * It does not pick the status code. The caller gives the status code, and the default
    content type is `application/json`.

The module imports no module of this repository, so every caller can import it without a
second import path.
"""
from __future__ import annotations

__all__ = ["write_reply"]


def write_reply(handler, code, body, ctype="application/json") -> None:
    """Write one reply for one handler: status line, headers, and body bytes.

    `code` is the HTTP status code, `body` is the body as a bytes object, and `ctype` is
    the content type of the body. The default content type is `application/json`. The
    function writes the content length as `len(body)`, so it needs no second count of the
    body.
    """
    handler.send_response(code)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
