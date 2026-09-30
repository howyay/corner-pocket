# The public board — runbook

*The read-only scoreboard for the hall's TV and the players' phones. It is the one part
of Corner Pocket that is meant to be reachable **without** Cloudflare Access, so this
document covers two things that must not be confused: what the code already does (shipped
in `annotator/unified_server.py`, `annotator/board.{html,css,js}`) and the exposure change
on the Cloudflare side, which is **prepared here and not applied**.*

> **Status.** The listener, the page and `GET /api/board` are in the repository. The
> tunnel ingress rule, the DNS record and the Access exemption below are **proposals**:
> nothing in this file has been installed, and no Cloudflare, DNS, systemd or production
> state was touched. Applying them is the owner's decision and is a separate, explicit
> step (§4, §5).

| | |
|---|---|
| code | `annotator/unified_server.py` (`PublicBoardServer`, `make_public_handler`, `BOARD_FILES`, `BOARD_FONTS`, `BOARD_CSP`), `annotator/public_board.py`, `annotator/board.html`, `annotator/board.css`, `annotator/board.js` |
| switch | `--public-port <port>` (default: not served at all) |
| reach | loopback only, same `--host` as the console (default `127.0.0.1`) |
| serves | `/`, `/board.js`, `/board.css`, `/favicon.{svg,ico}`, `/favicon-32.png`, `/favicon-16.png`, `/fonts/<the five BOARD_FONTS>`, `GET|HEAD /api/board` |
| refuses | every other path (404), every other method (405), and HTTP/0.9 |
| auth | **none** — the whitelist is the whole boundary |
| tests | `tests/test_public_board.py`, `tests/test_board_api.py`, `node --test tests/test_board.js` |

## 1. What the public port is

One extra listener in the same process as the console, started only when `--public-port`
is given:

```
.venv/bin/python annotator/unified_server.py --port 8130 --public-port 8132
```

`--host` applies to both listeners. `PublicBoardServer` reuses `BoundedHTTPServer` with a
deliberately smaller pool (`max_handlers = 16`, `request_queue_size = 16`): however many
phones poll the board, they cannot take the operator console's slots. The handler is
`HTTP/1.0` (one request per connection, nothing pipelined rides along), drops an idle or
trickling client after 10 s, and logs only refusals — a 3 s poller would otherwise fill the
journal.

`make_public_handler` shares **no** dispatch code with `make_handler`. Paths are compared
exactly as sent, before any decoding or normalisation, so an encoded, doubled or traversing
spelling of a public path is just another unknown path: 404. The query string is never read.

### Why a second port rather than a path on `:8130`

Everything on `:8130`, every path and every method, is behind the Access application for
`pool.example.com` (`docs/private-audit.md`, area A). A phone in the hall cannot log in, and a
path-scoped Access bypass on the console's own hostname would put the console and an
unauthenticated surface one routing mistake apart. A separate listener on a separate
hostname keeps the unauthenticated surface to code that can only read.

## 2. The API and the page

### `GET /api/board`

Built by `annotator/public_board.py` from `Backend.operations().get()` — the operations
document **through the store**, whichever store is configured. Nothing here reads
`out/corner-pocket/state.json` directly, so the board follows the console across the JSON →
PostgreSQL cutover (`docs/postgres.md`) with no code change. The board never writes.

It carries tonight only: the event name, format, race-to and phase; the matches on a table
right now (with their table number and how long they have been on it); what is next up; the
bracket; and tonight's table (W/L/played). It carries **no** internal ids, notes, audit log,
sources, roster, ratings, faces or biometrics, Vision or identity data, archived history,
other settings, or error internals.

| | |
|---|---|
| shape | `{"board":"on", "revision", "event", "tables", "next", "bracket", "standings", "served_at"}` |
| caching | built at most once a second, however many screens poll; one builder at a time |
| ETag | `W/"<revision>-<sha256 of everything but served_at>"`; `If-None-Match` → `304` |
| `Cache-Control` | `no-cache` (revalidate every time) |
| failure | `503 {"error":"unavailable"}` + `Retry-After: 3`, internals logged not sent |
| traces | one entry per match left on a table: `"since"` on a live match, for the "28 min" footer |

### The page

`board.html` is static and loads `/board.css` and `/board.js`; there is no inline script or
style, because the board's CSP has no `unsafe-inline`. `board.js` polls every 3 s with the
last ETag, and keeps its own honest age: `Updated just now` / `Updated N s ago`, and after
15 s without a good answer it says `Reconnecting — showing the last known board` while the
last board stays on screen, visibly faded. It never looks fresher than its last answer.

`?lang=en|zh` picks the language, the browser's own language is the fallback, and the single
control on the page toggles between them. A match's time on its table is computed from the
server's `served_at` plus the time since that answer, so a device with a wrong clock still
shows the right duration.

### Board off

`settings.publicBoard` false makes `GET /api/board` return `{"board":"off"}` and nothing
else; the page then says `The board is off tonight` / `今晚记分板已关闭`. The console switch
that flips it lives in the operator UI, not here.

### Headers

`BOARD_CSP` is
`default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'`,
on top of the shared `SECURITY_HEADERS`, plus `X-Robots-Tag: noindex, nofollow` — the board
shows players' names and has no business in a search index.

## 3. The font subset

Only the five files in `BOARD_FONTS` are reachable, whichever faces `board.css` declares.
`annotator/fonts/` holds many more (every weight of Barlow, DM Mono, Zilla Slab, Noto Serif
SC, plus the full CJK subsets); they stay off the public port. Adding a face to the page
means adding its file to `BOARD_FONTS` in `annotator/unified_server.py` in the same commit.
Fonts and favicons are served `public, max-age=86400`; the page and the API are `no-cache`.

## 4. Deploy: the systemd drop-in (prepared, not installed)

The unit is not in this repository (it is generated/hand-maintained under
`~/.config/systemd/user/`). The change is a drop-in, checked in here for review as
`deploy/systemd/pool-workbench.service.d/40-public-board.conf`, mirroring how
`20-postgres.conf` is delivered:

```ini
[Service]
# An ExecStart override must first clear the inherited list: systemd appends to it.
ExecStart=
ExecStart=/home/operator/projects/pool/.venv/bin/python /home/operator/projects/pool/annotator/unified_server.py --port 8130 --public-port 8132
```

Two things about that file:

- **The empty `ExecStart=` is not optional.** Without it systemd appends the second
  `ExecStart=` to the unit's own, and the service tries to start twice.
- **The whole command line must be repeated, and it must match the unit's.** The line above
  is the unit's own `ExecStart` as it stood when this was written (absolute interpreter and
  absolute script, `/home/operator/projects/pool`, so it is the deployed tree and not a lane
  worktree); only `--public-port 8132` is new. `WorkingDirectory`, `UMask=0077`,
  `EnvironmentFile` (including `POOL_DATABASE_URL`) and the rest still come from the unit
  and the other drop-ins. Re-read `systemctl --user cat pool-workbench.service` and copy the
  current line before installing — if the unit moves, this file must move with it.

Install (owner, on the host — **not** done by this repository):

```
install -Dm644 deploy/systemd/pool-workbench.service.d/40-public-board.conf \
  ~/.config/systemd/user/pool-workbench.service.d/40-public-board.conf
systemctl --user daemon-reload
systemctl --user restart pool-workbench.service      # this is the one disruptive step
systemctl --user show pool-workbench.service -p ExecStart   # confirm exactly one start command
```

Pick `<port>` deliberately: it must be free on the host, loopback-bound, and **not** a
fixture range (`8230-8239` belong to lane fixtures). `8132` was free when this was written.

## 5. Cloudflare: the prepared change (not applied)

Today one tunnel ingress rule reaches the console — `pool.example.com → http://127.0.0.1:8130`
in tunnel `pool-tunnel` — and the Access application for that hostname covers **every** path and
method (`docs/private-audit.md`, areas A and A.6). The public board needs the opposite:
a hostname that resolves, reaches the public port, and has **no** Access application.

Prepared, to be applied by the owner only:

1. **Tunnel ingress.** In the `pool-tunnel` tunnel's configuration, add a rule
   `board.example.com → http://127.0.0.1:8132` **above** the catch-all
   (`service: http_status:404`). Ingress rules are matched in order; below the catch-all it
   would never be reached. Do not touch the existing `pool.example.com` rule.
2. **DNS.** A proxied `CNAME` (or the dashboard's "add a public hostname" flow, which
   writes both) for `board.example.com` → `<tunnel-id>.cfargotunnel.com`. The hostname choice is
   the owner's; `board.example.com` matches the `pool./hass./me.example.com` convention already in
   use.
3. **Access.** **No** Access application for `board.example.com`, and no "public hostname"
   checkbox left unticked. Verify by hand that
   `curl -sS -o /dev/null -w '%{http_code}\n' https://board.example.com/api/board` returns `200`
   from a network that is not the host — not a `302` to
   `team.cloudflareaccess.com`.
4. **Origin reach.** Confirm the public port is loopback-only:
   `ss -ltn 'sport = :8132'` must show `127.0.0.1:8132` and nothing else. `--host 0.0.0.0`
   would expose the board to the LAN and is not what this is for.

### Pre-flight, before any of the above

Run these against the fixture first (`tests/serve_workbench_fixture.py`, copied to an
untracked `tests/_b7_*_fixture.py` on a free port — never `:8130`):

```
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*board*.py' -q
node --test tests/test_board.js
```

Then the load the hall will actually produce: 50 concurrent pollers at 3 s for two minutes,
recording the public port's CPU, the p95 of `GET /api/board`, and — the number that matters —
the p95 of `GET /api/operations` on the console port during that window, which must stay
unaffected. Record the figures in this file before flipping DNS.

## 6. Rollback

| stop | how |
|---|---|
| the board page only | console switch `Public board: on/off` → `/api/board` returns `{"board":"off"}` and the page says so; the port stays up and serves nothing useful |
| the public port | remove `40-public-board.conf`, `daemon-reload`, restart the service |
| the hostname | delete the `board.example.com` ingress rule and DNS record; the console's `pool.example.com` rule is untouched by all of this |

The console is not affected by any of them: the public listener has its own pool, its own
handler and no shared dispatch, and the board never writes.
