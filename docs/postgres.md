# PostgreSQL for Corner Pocket — runbook

*Phase A (infrastructure only).  The application still reads and writes its JSON files;
nothing in `annotator/` uses the database yet.  The schema and the cutover are designed in
`docs/postgres-design.md` and wait for review.*

| | |
|---|---|
| container | `pool-postgres` (rootless podman, user `operator`) |
| unit | `pool-postgres.service` (systemd **--user**), generated from the quadlet `~/.config/containers/systemd/pool-postgres.container` |
| image | `docker.io/library/postgres:17.11-bookworm` pinned by digest `sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652` (manifest list; linux/amd64 manifest `sha256:91eb910c44c7ed13f7f1a4ccadaa9ca72ef14cddc04cacb6e070e48eb44731a3`) — PostgreSQL 17.11 |
| address | `127.0.0.1:5434` only (5432 is the host's system PostgreSQL 15, 5433 is kaneo's container) |
| database / role | `pool` / `pool` (the image's superuser for this cluster), `scram-sha-256` |
| data | `$POOL_PG_ROOT/pool-postgres/data` (bind mount, `PGDATA`) |
| backups | `$POOL_PG_ROOT/pool-postgres/backups` (mode 700) |
| connection string | `~/.config/pool/postgres.env` (mode 600): `POOL_DATABASE_URL=postgresql://pool:<password>@127.0.0.1:5434/pool` |
| password | podman secret `pool-postgres-password` (mounted at `/run/secrets/pool-postgres-password`, read once by the image at init) and the env file above — nowhere else |
| driver | `psycopg[binary]==3.3.6` in `.venv` (installed with `uv pip install --python .venv/bin/python`; the venv is uv-managed and has no pip) |
| code | `src/db.py` (connection + migration runner), `db/migrations/NNNN_name.sql`, `tests/test_db.py` |

## Network exposure

The container publishes **only** `127.0.0.1:5434`; nothing listens on another address
(`ss -ltn 'sport = :5434'` shows `127.0.0.1:5434` alone).  It is **not exposed through
Cloudflare**: the host's tunnel (`cloudflared-tunnel-pool.service`) routes HTTP
hostnames only and has no TCP ingress for this port; do not add one.  Remote access,
when needed, goes through SSH (`ssh -L 5434:127.0.0.1:5434 …`).

Authentication: the image's `initdb` writes `trust` for TCP from `127.0.0.1`/`::1` *inside
the container*.  Those `host` lines were changed to `scram-sha-256` after initialisation
(`pg_hba.conf` lives in the data directory, so the change persists), so every TCP
connection needs the password; only the container's own Unix socket stays `trust`, and
that is reachable only through `podman exec` as `operator`.  Check with
`podman exec pool-postgres psql -U pool -d pool -c 'TABLE pg_hba_file_rules'`.  A cluster
re-initialised on an empty directory needs the same edit:
`podman exec -u postgres pool-postgres sed -i -E '/^host[[:space:]]/ s/trust$/scram-sha-256/' /var/lib/postgresql/data/pg_hba.conf`
then `SELECT pg_reload_conf()`.

The system PostgreSQL
(`postgresql.service`, `/var/lib/postgresql/15`, port 5432) is a separate cluster and is
never touched by anything here.

## Start, stop, status

```sh
systemctl --user start   pool-postgres        # waits until the container reports healthy
systemctl --user stop    pool-postgres        # clean shutdown (SIGINT, 60 s grace), container removed
systemctl --user restart pool-postgres
systemctl --user status  pool-postgres
journalctl --user -u pool-postgres -n 100     # server log (log driver: journald)
podman ps --filter name=pool-postgres         # "Up … (healthy)  127.0.0.1:5434->5432/tcp"
podman exec pool-postgres pg_isready -h 127.0.0.1 -p 5432 -U pool -d pool
podman exec -it pool-postgres psql -U pool -d pool     # admin shell (socket, no password)
```

A quadlet unit is *generated*: `systemctl --user enable` does not apply.  The
`[Install] WantedBy=default.target` section makes the generator link it into
`default.target.wants` on every `daemon-reload`, and lingering is on for `operator`, so it
starts at boot without a login.  After editing the `.container` file:
`systemctl --user daemon-reload && systemctl --user restart pool-postgres`.

The container is disposable (`--rm --replace`); the state is the data directory.  From the
host the files are owned by a subuid (container uid 999 → host uid 100998), so inspect
them with `podman unshare ls -ln $POOL_PG_ROOT/pool-postgres/data`.

## Using it from Python

```sh
cd /home/operator/projects/pool
set -a; . ~/.config/pool/postgres.env; set +a
PYTHONPATH=. .venv/bin/python -m src.db       # apply pending migrations, list the ledger
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -p test_db.py -v
```

```python
from src import db
with db.transaction() as conn:            # commits at the end, rolls back on an exception
    conn.execute("SELECT 1")
```

`src/db.py` refuses to run without `POOL_DATABASE_URL` (`DatabaseNotConfigured`), never
formats the URL into a message, and `tests/test_db.py` skips its database tests when the
variable is unset, so the default suite needs no database.

### Migrations

* Files are `db/migrations/NNNN_name.sql` (four digits, lower-case name), applied in
  version order.  `0001_schema_migrations.sql` creates the ledger itself; the application
  schema arrives in later files after the design review.
* `migrate()` takes a transaction-level advisory lock and applies **all** pending files in
  **one** transaction: concurrent runs serialise, a failing file leaves the database
  exactly as it was, and a second run applies nothing.
* A file must not contain `BEGIN`/`COMMIT`.  Never edit an applied file: its SHA-256 is
  in `schema_migrations.checksum` and a changed file is refused.  Fix forward with a new
  file.  (`CREATE INDEX CONCURRENTLY` cannot run inside the transaction; when one is
  needed, run it by hand and record it in a follow-up migration that uses `IF NOT EXISTS`.)

## Backup

Logical dumps, custom format, taken from inside the container (the dump tool then always
matches the server version) and written on the host:

```sh
ts=$(date +%Y%m%d-%H%M%S)
podman exec pool-postgres pg_dump -U pool -d pool -Fc -Z 6 \
  > $POOL_PG_ROOT/pool-postgres/backups/pool-$ts.dump
podman exec -i pool-postgres pg_restore --list \
  < $POOL_PG_ROOT/pool-postgres/backups/pool-$ts.dump | head     # proves the archive reads back
```

Roles and the password are not in a `pg_dump`; they come from the env file and the
secret.  Until cutover the JSON files in `out/` are the system of record, so a dump is a
copy of imported data, not the only copy.  After cutover, schedule the dump (a user
timer) and keep the files from the last import as the cold backup.

A file-level copy of `$POOL_PG_ROOT/pool-postgres/data` is only consistent with the unit
**stopped** (`systemctl --user stop pool-postgres`, copy with `podman unshare cp -a …`,
start again).

## Restore

Into a scratch database first, verify, then swap:

```sh
f=$POOL_PG_ROOT/pool-postgres/backups/pool-<ts>.dump
podman exec pool-postgres createdb -U pool pool_restore
podman exec -i pool-postgres pg_restore -U pool -d pool_restore --no-owner --exit-on-error < "$f"
podman exec pool-postgres psql -U pool -d pool_restore -c 'SELECT version, name FROM schema_migrations ORDER BY 1'
```

To replace `pool` itself (stop every client first — the workbench too, once it uses the
database):

```sh
podman exec pool-postgres dropdb -U pool --if-exists pool
podman exec pool-postgres createdb -U pool pool
podman exec -i pool-postgres pg_restore -U pool -d pool --no-owner --exit-on-error < "$f"
podman exec pool-postgres dropdb -U pool --if-exists pool_restore
```

(The `-U pool` commands connect to the maintenance database `postgres`, not to `pool`,
when they create or drop `pool`.)

## Password rotation

The image reads `POSTGRES_PASSWORD_FILE` only when it initialises an empty data
directory, so a rotation is two changes that must agree — the role in the database and
the connection string on disk — plus the secret for future re-initialisation.  Nothing is
echoed:

```sh
umask 077
new=$(/home/operator/projects/pool/.venv/bin/python -c 'import secrets; print(secrets.token_hex(24))')
printf "ALTER ROLE pool PASSWORD '%s';\n" "$new" | podman exec -i pool-postgres psql -q -U pool -d pool
printf 'POOL_DATABASE_URL=postgresql://pool:%s@127.0.0.1:5434/pool\n' "$new" > ~/.config/pool/postgres.env
printf '%s' "$new" | podman secret create --replace pool-postgres-password -
unset new
chmod 600 ~/.config/pool/postgres.env
```

The `ALTER ROLE` statement travels on stdin through the local socket, so it is not in
`ps` output or shell history.  Postgres does not log it at the default settings
(`log_statement = none`); do not run it while statement logging is turned up.  Then
restart every client that holds the old URL (once cut over:
`systemctl --user restart pool-workbench`) and check with
`PYTHONPATH=. .venv/bin/python -m src.db`.

## The unit file

`~/.config/containers/systemd/pool-postgres.container` (outside the repo; this is its
content):

```ini
# Corner Pocket PostgreSQL - rootless podman quadlet.
# The generator turns this file into the user unit pool-postgres.service.
# Runbook: /home/operator/projects/pool/docs/postgres.md
[Unit]
Description=Corner Pocket PostgreSQL (podman, loopback 127.0.0.1:5434)
Wants=network-online.target
After=network-online.target

[Container]
ContainerName=pool-postgres
# postgres:17.11-bookworm pinned by its manifest-list digest (amd64 manifest sha256:91eb910c...)
Image=docker.io/library/postgres:17.11-bookworm@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652
# loopback only: never 0.0.0.0, never routed through the Cloudflare tunnel
PublishPort=127.0.0.1:5434:5432
Volume=$POOL_PG_ROOT/pool-postgres/data:/var/lib/postgresql/data
# the password lives in the podman secret and in ~/.config/pool/postgres.env, never here
Secret=pool-postgres-password
Environment=POSTGRES_USER=pool POSTGRES_DB=pool POSTGRES_PASSWORD_FILE=/run/secrets/pool-postgres-password
ShmSize=256m
StopTimeout=60
# TCP probe: the init-time temporary server listens on the socket only, so this passes
# only once the real server accepts connections
HealthCmd=pg_isready -h 127.0.0.1 -p 5432 -U pool -d pool
HealthInterval=10s
HealthTimeout=5s
HealthRetries=3
HealthStartPeriod=60s
Notify=healthy

[Service]
Restart=on-failure
RestartSec=5
TimeoutStartSec=180
TimeoutStopSec=90

[Install]
WantedBy=default.target
```

`Notify=healthy` makes `systemctl --user start` return only after `pg_isready` passes, so
a dependent unit (`After=`/`Requires=pool-postgres.service`) starts against a server that
accepts connections.  The generated unit runs
`podman run --name pool-postgres --replace --rm --sdnotify=healthy … --publish 127.0.0.1:5434:5432 …`;
see it with `systemctl --user cat pool-postgres`.

### Upgrading the image

* **Minor** (17.x → 17.y): pull the new tag, record its digest, change `Image=`,
  `daemon-reload`, restart.  Same data directory.
* **Major** (17 → 18): the data directory is not compatible.  Dump, start a fresh
  container on an empty directory, restore, verify, then switch the unit over.  Never
  point a new major at the old directory.

## Setup record (2026-09-25)

* No postgres image existed locally; pulled `postgres:17.11-bookworm` (the only
  PostgreSQL containers on the host were kaneo's `postgres:16-alpine` via compose and
  mergecrew's `pgvector/pgvector:pg16`).
* Port 5434 was free and referenced by no other stack's configuration.
* `$POOL_PG_ROOT` had 501 GB free; a fresh cluster is 46 MB.
* The password was generated with `secrets.token_hex(24)` and written only to the
  podman secret and the env file.
* Restart proof: a row written before `systemctl --user restart pool-postgres` was read
  back after it from a new container (`3e825ae87c11` → `236eb3b87723`), then dropped.
