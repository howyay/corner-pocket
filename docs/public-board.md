# The public board — runbook

*The read-only scoreboard for the hall's TV and the players' phones. It is the one part
of Corner Pocket that is meant to be reachable **without** Cloudflare Access, so this
document covers two things that must not be confused: what the code already does (shipped
in `annotator/unified_server.py`, `annotator/board.{html,css,js}`) and the exposure change
on the Cloudflare side, which is **applied** — the board is live at
`https://pool.example.com/board/`.*

> **Status.** The listener, the page, `GET /api/board`, the path prefix
> (`--public-prefix`) and the bare-prefix redirect are in the repository **and installed**:
> the drop-in, the tunnel ingress rule and the Access exemption were applied on 2026-09-30
> (§4, §5). The board answers on `https://pool.example.com/board/` without a login, the console
> on the same hostname still asks for one, and `https://pool.example.com/board/api/operations`
> is a `404`. Still owed: the 50-poller load test in §5's pre-flight.

| | |
|---|---|
| code | `annotator/unified_server.py` (`PublicBoardServer`, `make_public_handler`, `board_prefix`, `BOARD_FILES`, `BOARD_FONTS`, `BOARD_CSP`), `annotator/public_board.py`, `annotator/board.html`, `annotator/board.css`, `annotator/board.js` |
| switch | `--public-port <port>` (default: not served at all) and `--public-prefix <path>` (default: empty, the root — the behaviour above) |
| mount | with `--public-prefix /board` the whole surface moves under it: `GET /board/`, `/board/board.js`, `/board/board.css`, `/board/favicon.{svg,ico}`, `/board/favicon-32.png`, `/board/favicon-16.png`, `/board/fonts/<the five BOARD_FONTS>`, `GET\|HEAD /board/api/board` — and the bare `GET\|HEAD /board` answers **308** to `/board/` |
| reach | loopback only, same `--host` as the console (default `127.0.0.1`) |
| refuses | every other path (404) — including, with a prefix set, the whole root mount (`/`, `/board.js`, `/api/board`) — every other method (405), and HTTP/0.9 |
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
spelling of a public path is just another unknown path: 404. The query string is never read —
the one place it appears at all is the bare-prefix redirect below, which carries it into
`Location` byte for byte without parsing it.

### The prefix

`--public-prefix <path>` mounts that same surface under one path, with a prefix of `""`
(the default) meaning the root, exactly as before:

```
.venv/bin/python annotator/unified_server.py --port 8130 --public-port 8132 --public-prefix /board
```

Then only `GET /board/` (which serves `board.html`) and the paths under `/board/` are served;
the root mount is **closed** — `/`, `/board.js` and `/api/board` on that port are 404 — because
the prefix is the whole mount rather than an extra one. The bare `GET`/`HEAD /board` is the one
spelling that is not the page: it answers **308** with `Location: /board/`, because the page's
asset URLs are relative and a document whose URL is `/board` would ask for `/board.js`, which
the prefixed listener refuses. A query rides along as the same bytes (`/board?lang=zh` →
`/board/?lang=zh`) — carried, not parsed, and it still cannot pick a route. The prefix is matched
as a plain string with a `/` boundary, before any decoding or normalisation: `/board` and
`/board/...` match, `/boardx` does not, and `//board/board.js`, `/%62oard/board.js`,
`/board/../api/operations` or `/board//api/board` are all just unknown paths (404), exactly
as they would be without a prefix — none of those spellings redirects either. `board_prefix()`
rejects a bad `--public-prefix` at startup (padded, encoded or relative values, `//`, or a
`.`/`..` segment) rather than trusting a mangled one at request time.

`board.html`, `board.js` and `board.css` reference everything **relatively** (`./board.js`,
`./api/board`, `url(fonts/...)`), and `board.js` builds its API URL from the URL of its own
`<script>` tag, not from the document URL: one file therefore works at `/`, at `/board/`
and at the console's own `/display` mount, with no build step and no per-mount copy. **Publish
the trailing-slash form**, `https://pool.example.com/board/` (what §5 bypasses): that is the URL for
the TV, the phones and any QR code. The bare `https://pool.example.com/board` is not a broken page
for a player who types or shares it — the listener answers 308 to the trailing-slash form, so
the browser lands on the page that resolves `./board.js` inside the mount.

### Why a path on the console's hostname, and not a second hostname

The board is meant to be one URL the hall already knows, on the hostname the console uses:
`https://pool.example.com/board/`. A second hostname (`board.example.com`) would mean a second DNS
record, a second ingress rule and a second certificate to keep in step with the first — more
moving parts, and one more place for the console's own rule to drift. The unauthenticated
surface stays exactly what it was: a **separate listener** (`PublicBoardServer`, its own
pool, its own handler, not one line of `make_handler`'s dispatch) that can only read. What
the console serves on `pool.example.com` is unchanged; only `/board*` is routed elsewhere (§5).

Two hazards are what make that safe, and both are outside the code:

1. **The ingress path rule must sit above the console's rule.** An Access bypass is
   path-scoped; the bypassed path must therefore be routed *away* from the console. If
   `/board*` fell through to `127.0.0.1:8130`, the console would answer it — behind the very
   path-scoped bypass the board needs, i.e. unauthenticated. Ingress rules are matched in
   order, so a rule below `pool.example.com → 127.0.0.1:8130` is never reached. The order of those
   two rules is the whole defence.
2. **The listener's whitelist is what keeps the bypassed prefix read-only.** `/board*` becomes
   the only unauthenticated surface on the hostname: everything the whitelist does not name —
   `/board/api/operations` included — is a 404 there, and no method but `GET`/`HEAD` is
   answered at all. Being inside the bypassed prefix therefore buys a request the board and
   nothing else, including through a traversing or encoded spelling: the prefix is matched,
   not normalised, so there is no spelling that lands outside it.

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

`board.html` is static and loads `./board.css` and `./board.js` — **relatively**, so the same
page works at the root and under a prefix — and there is no inline script or
style, because the board's CSP has no `unsafe-inline`. `board.js` polls `api/board` beside the
page (resolved from its own script URL, §1) every 3 s with the
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

## 4. Deploy: the systemd drop-in (installed 2026-09-30)

The unit is not in this repository (it is generated/hand-maintained under
`~/.config/systemd/user/`). The change is a drop-in, deployed from
`deploy/systemd/pool-workbench.service.d/40-public-board.conf`, mirroring how
`20-postgres.conf` is delivered:

```ini
[Service]
# An ExecStart override must first clear the inherited list: systemd appends to it.
ExecStart=
ExecStart=/home/operator/projects/pool/.venv/bin/python /home/operator/projects/pool/annotator/unified_server.py --port 8130 --public-port 8132 --public-prefix /board
```

Two things about that file:

- **The empty `ExecStart=` is not optional.** Without it systemd appends the second
  `ExecStart=` to the unit's own, and the service tries to start twice.
- **The whole command line must be repeated, and it must match the unit's.** The line above
  is the unit's own `ExecStart` as it stood when this was written (absolute interpreter and
  absolute script, `/home/operator/projects/pool`, so it is the deployed tree and not a lane
  worktree); only `--public-port 8132 --public-prefix /board` is new. `WorkingDirectory`, `UMask=0077`,
  `EnvironmentFile` (including `POOL_DATABASE_URL`) and the rest still come from the unit
  and the other drop-ins. Re-read `systemctl --user cat pool-workbench.service` and copy the
  current line before installing — if the unit moves, this file must move with it.

Installed by the owner on the host on 2026-09-30 (this repository never restarts the
service itself):

```
install -Dm644 deploy/systemd/pool-workbench.service.d/40-public-board.conf \
  ~/.config/systemd/user/pool-workbench.service.d/40-public-board.conf
systemctl --user daemon-reload
systemctl --user restart pool-workbench.service      # this is the one disruptive step
systemctl --user show pool-workbench.service -p ExecStart   # confirm exactly one start command
```

As installed: the drop-in directory holds `10-umask.conf`, `20-postgres.conf`,
`30-ffmpeg.conf` and `40-public-board.conf`; `ExecStart` is a single start command carrying
`--port 8130 --public-port 8132 --public-prefix /board`, and the process listens on
`127.0.0.1:8130` and `127.0.0.1:8132` only. The one restart wrote nothing: `state.json`
kept its md5 `77777777777777777777777777777777`, `out/identity/clusters.json` kept
`77777777777777777777777777777777`, and no `out/corner-pocket/clock.json` appeared.

Pick `<port>` deliberately: it must be free on the host, loopback-bound, and **not** a
fixture range (`8230-8239` belong to lane fixtures). `8132` was free when this was written.

## 5. Cloudflare: the applied change (2026-09-30)

Today one tunnel ingress rule reaches the console — `pool.example.com → http://127.0.0.1:8130`
in tunnel `pool-tunnel` — and the Access application for that hostname covers **every** path and
method (`docs/private-audit.md`, areas A and A.6). The board needs one path of that same
hostname to reach the public port instead, with no Access application in front of it. There
is **no new hostname and no DNS record** in this change: the hostname already resolves and
already routes to the tunnel.

Applied on 2026-09-30 under the owner's standing release authorization. What was done, and
what it returns now:

1. **Tunnel ingress — a path rule, above the console's rule.** In the `pool-tunnel` tunnel's
   configuration, add `pool.example.com/board* → http://127.0.0.1:8132` **above** the existing
   `pool.example.com → http://127.0.0.1:8130` rule. Ingress rules are matched in order: below it,
   the path rule is never reached and `/board*` goes to the console — which is exactly the
   failure §1 warns about, because the bypass (§2) is path-scoped and would still be in
   force. Do not touch any other rule.
2. **Access — a path-scoped bypass on the existing application.** Add a `Bypass` policy with
   path `/board` and `/board*` to the Access application for `pool.example.com`; leave the
   console's own policy as it is. It must be a path rule on that application, not a second
   application and not a "public hostname" checkbox. Verify by hand from a network that is
   not the host: `curl -sS -o /dev/null -w '%{http_code}\n' https://pool.example.com/board/api/board`
   returns `200` — not a `302` to `team.cloudflareaccess.com` — while
   `curl -sS -o /dev/null -w '%{http_code}\n' https://pool.example.com/api/operations` still
   returns a `302` to that login. The bare form must land on the mount through the tunnel too:
   `curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' https://pool.example.com/board` gives
   `308 https://pool.example.com/board/` — the redirect is the listener's own answer.
3. **The bypassed path is read-only — verify it that way.** Every path the whitelist does not
   name must 404 through the tunnel, not answer with console data:
   `https://pool.example.com/board/api/operations` → `404`, and so do the encoded and traversing
   spellings (`/board/../api/operations`, `/%62oard/board.js`, `//board/board.js`,
   `/board//api/board`). `POST` to any `/board*` path → `405`.
4. **Origin reach.** Confirm the public port is loopback-only:
   `ss -ltn 'sport = :8132'` must show `127.0.0.1:8132` and nothing else. `--host 0.0.0.0`
   would expose the board to the LAN and is not what this is for.

Three notes against the plan above, recorded because the deployment differs from it:

- **The bypass is a second Access application, not a path policy on the console's.** The new
  self-hosted application *Corner Pocket board bypass* (`33333333-3333-3333-3333-333333333333`)
  carries the domain `pool.example.com/board*`, a 24 h session and one policy `bypass-everyone`
  (decision `bypass`, include `everyone`). The console's application *Corner Pocket*
  (`22222222-2222-2222-2222-222222222222`, domain `pool.example.com`, 168 h, policy
  `<owner>_pocket-id`) is untouched. This matches the three bypasses already on this account —
  `paperless.example.com/api/*` `2702a474-e52c-4739-bbbc-356afdf39020`, `ai.example.com/v1*`
  `abcea54d-47f4-490c-9f3b-dc00dabb2280`, `sona.example.com/phone/*`
  `894064ab-ee68-4890-a40c-cc1ad9aadd9d` — which are all separate applications with
  path-carrying domains.
- **The ingress rule is in place.** Tunnel `pool-tunnel` (`11111111-1111-1111-1111-111111111111`)
  now holds 53 rules: `pool.example.com` + `^/board` → `http://127.0.0.1:8132` sits immediately
  above the hostname-only `pool.example.com` → `http://127.0.0.1:8130` rule, and the
  `http_status:404` catch-all is still last. No other rule was touched.
- **The 50-poller load test was not run.** The figures the pre-flight below asks for — the
  public port's CPU, the p95 of `GET /api/board`, and the p95 of `GET /api/operations` during
  the load — are still owed. The board went live without them.

Measured from the host through the public internet on 2026-09-30, after the change:

| request | answer |
|---|---|
| `https://pool.example.com/board` | `308` → `https://pool.example.com/board/` |
| `https://pool.example.com/board/` | `200 text/html`, `<title>Corner Pocket · Tonight</title>`, no login |
| `https://pool.example.com/board/api/board` | `200 application/json` |
| `https://pool.example.com/board/board.js` | `200` |
| `https://pool.example.com/board/api/operations` | `404` |
| `https://pool.example.com/boardx/board.js` | `404` |
| `https://pool.example.com/` | `302` → `team.cloudflareaccess.com/…/login/pool.example.com` |
| `https://pool.example.com/api/operations` | `302` → the same login |

`/board/../api/operations` answers `302` as well, because Cloudflare normalises the path to
`/api/operations` before ingress matching: it lands on the console's rule and its login. That
is not a leak of console data, and it is not a 404 either.

The page's own headers through the edge keep the board's CSP
(`default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; …`),
`x-robots-tag: noindex, nofollow`, `x-content-type-options: nosniff` and `cache-control: no-cache`.

### Pre-flight, before any of the above

Run these against the fixture first (`tests/serve_workbench_fixture.py`, copied to an
untracked `tests/_b7_*_fixture.py` on a free port — never `:8130`), with the public listener
started **as it will be deployed** (`--public-port <p> --public-prefix /board`, and
`http://127.0.0.1:<p>/board/` opened in a browser: the page, its font and its 3 s poll must
all work through the prefix):

```
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p 'test_*board*.py' -q
node --test tests/test_board.js
```

Then the load the hall will actually produce: 50 concurrent pollers at 3 s for two minutes,
recording the public port's CPU, the p95 of `GET /api/board`, and — the number that matters —
the p95 of `GET /api/operations` on the console port during that window, which must stay
unaffected. Record the figures in this file before flipping DNS — the board is live in
production now, so run them anyway and record them here.

## 6. Rollback

| stop | how |
|---|---|
| the board page only | console switch `Public board: on/off` → `/api/board` returns `{"board":"off"}` and the page says so; the port and the prefix stay up and serve nothing useful |
| the public port | remove `40-public-board.conf`, `daemon-reload`, restart the service; the `:8132` listener goes with it (dropping only `--public-prefix /board` puts the surface back at the root of that port instead) |
| the bypassed path | remove the Access bypass **first**, then the `/board*` ingress rule — in that order. Removing the rule first would send `/board*` to the console while the bypass is still in force: an unauthenticated path on the console's own rule. Removing the bypass first only makes `/board*` ask for a login |
| the whole exposure | as above, then the console's `pool.example.com → 127.0.0.1:8130` rule and the Access application are exactly as they were — neither was edited by this change |

The console is not affected by any of them: the public listener has its own pool, its own
handler and no shared dispatch, and the board never writes.
