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

### Importing the JSON files (not done yet — the files are still the live store)

```sh
PYTHONPATH=. .venv/bin/python -m src.db                       # 0001 + 0002
PYTHONPATH=. .venv/bin/python -m src.store_import --dry-run   # import + verify, roll back
PYTHONPATH=. .venv/bin/python -m src.store_import             # import for real
```

`src/store_import.py` reads each file once (read-only, md5 reported), imports each data
set in its own transaction, and commits only when the row counts match and every record
renders back to exactly the file's JSON.  A second run reports `unchanged` and writes
nothing.  Data the database already holds that differs from the files is `refused` unless
`--replace` (after cutover the database is the live store).  Exit code 0 only when every
set is `imported`/`unchanged`/`absent` (`verified` in a dry run) and no file changed.
Dry run against a copy of production on 2026-09-25: operations (revision 5, 1 source, 5
events), 48 identity clusters, 1 verdict, 76 ball labels, 1 anchor set verified; face
store absent; seeds and corrections empty.

`python -m src.store_export --to DIR [--compare ROOT]` writes every user-data file back,
byte-exact (proven on a production copy), and `python -m src.store_check` confirms the
0002 row projection equals the stored documents (exit 1 and `MISMATCH` lines otherwise).

### Who reads and writes the user-data files

Every reader and writer in the repository of `state.json`, `clusters.json`,
`face_embeddings.json`, `pid_seed.json`, `pid_anchors_<ds>.json`, `annotations.json`,
`labels.json` and `frame_results/*/correction.json`, with its decision for the Postgres
cutover (audit of 2026-09-26; `tests/*` use temp roots and are not listed):

| Code | Data | Decision |
|---|---|---|
| `annotator/unified_server.py` (the service) | all of them | **store** — every read/write via `Backend.store()` (switches `1d4af9f`…`7592ef6`) |
| `annotator/operations.py` | state | **store** — it is `JsonStore`'s operations implementation |
| `src/person_identity.py`, `src/person_pipeline.py` | clusters, faces | **store** — `store=` parameter; the server passes its store (`8fed832`) |
| `src/face_id.py` | faces | **store** — `add_faces`/`remove_faces`/`load_faces` are `JsonStore`'s face store |
| `annotator/live_processing.py` | state (saved channel) | **store** — `operations_document` set by the server (`7592ef6`) |
| `src/enroll_from_tracklet.py` | state, faces, clusters | **store** for the confirm (`load_state(store=)`, `e15396a`); its scratch writes go to `out/enroll-eval/scratch` (a working dir), the offline harness reads files |
| `src/frame_inference.py` | anchors | **store** for the server (`anchor_quad`, `6c41f6b`); `app_prior_for(root=)` stays a file read for the batch tools below |
| `src/pid_seed_rebuild.py` | seeds | **store** — the rebuild the server starts reads seeds via `open_store` (`f07dd42`) |
| `annotator/server.py`, `src/pid_seed_ui.py`, `src/pid_anchor_ui.py` | verdicts, labels, seeds, anchors (**write**) | **refuse** with a clear error when `POOL_DATABASE_URL` is set (`f07dd42`) |
| `src/merge_sets.py` | labels (**write**, new dir) | **refuse** likewise (`f07dd42`) |
| `src/dense_queue.py` | verdicts (md5 only) | **batch, read-only** — records the verdict file's md5; after cutover export first |
| `src/eval_events.py` | verdicts, anchors | **batch, read-only** — offline evaluation; after cutover run `src.store_export --to DIR` and point it at `DIR` |
| `src/eval_faces.py` | state, clusters, faces, seeds, verdicts | **batch, read-only** — offline evaluation (it records their md5s); after cutover export first |
| `src/eval_table_detect.py`, `src/check_app_quad.py`, `src/table_refine.py`, `src/motion_scan.py`, `src/shot_pot_gate.py`, `src/timing_verify.py`, `src/calib_mapping_audit.py`, `src/calib_segment_fit.py`, `src/calib_segment_measure.py`, `src/sam3_ball_cache.py`, `src/sam3_frame_audit.py` | anchors | **batch, read-only** — read `pid_anchors_<ds>.json` via `app_prior_for`/directly; after cutover export first |
| `src/train_ball_id.py`, `src/confusion.py`, `src/tiny_ball_net.py`, `src/recut_crops.py`, `src/fast_ball_labels.py` | labels | **batch, read-only** — training/analysis inputs (`recut_crops` rewrites crop `meta.json`/`ctx.json`, not labels); after cutover export first |

"Export first" is one command: `PYTHONPATH=. .venv/bin/python -m src.store_export --to
/tmp/pool-export-$(date +%F)`, then pass that directory as the tool's root.  The shot clock
(`annotator/shot_clock.py`) is not user data and stays a file (design §9).

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

## Cutover runbook (files → Postgres) — needs the owner's go-ahead

Approved as a draft on 2026-09-26; nothing here has been run against the live `pool`
database.  Preconditions: the caller switch has landed (`1d4af9f`…`f07dd42`), the suites
are green, the owner has said go, and no operator is mid-night.  All commands run from
the repository; `$ts` names this cutover's artifacts.

```sh
cd /home/operator/projects/pool
ts=$(date +%Y%m%d-%H%M%S); B=$POOL_PG_ROOT/pool-postgres/backups
set -a; . ~/.config/pool/postgres.env; set +a
```

**0. Pre-flight** — the database is up, the backup restores, the files are saved.

```sh
systemctl --user is-active pool-postgres                                   # active
podman exec pool-postgres pg_isready -h 127.0.0.1 -p 5432 -U pool -d pool  # accepting connections
podman exec pool-postgres pg_dump -U pool -d pool -Fc -Z 6 > $B/pool-pre-cutover-$ts.dump
podman exec pool-postgres createdb -U pool pool_restore_check              # restore test, scratch db
podman exec -i pool-postgres pg_restore -U pool -d pool_restore_check --no-owner --exit-on-error \
  < $B/pool-pre-cutover-$ts.dump
podman exec pool-postgres psql -U pool -d pool_restore_check -tAc \
  "SELECT string_agg(name, ',' ORDER BY version) FROM schema_migrations"   # same list as pool
podman exec pool-postgres dropdb -U pool pool_restore_check
mkdir -p ~/pool-cutover-$ts && cp -a --parents out/corner-pocket out/identity out/pid_seed.json \
  out/pid_anchors_vod30.json out/scan30/annotations.json out/unlabeled_crops/labels.json ~/pool-cutover-$ts/
(cd ~/pool-cutover-$ts && find . -type f -exec md5sum {} + > MD5SUMS)
```

(The restore test was exercised on 2026-09-26 against a scratch database: dump, restore,
the migration list matched, the scratch database dropped; `pool` itself was only read.)

**1. Migrate** — `PYTHONPATH=. .venv/bin/python -m src.db` (applies 0002 and 0003).

**2. Stop the writer** — `systemctl --user stop pool-workbench`.  Every user-data write
goes through the service (the legacy writers refuse to run once the variable is set), so
the files are frozen from here.

**3. Import and verify** — each must exit 0:

```sh
PYTHONPATH=. .venv/bin/python -m src.store_import --dry-run
PYTHONPATH=. .venv/bin/python -m src.store_import                       # imported/unchanged/absent
PYTHONPATH=. .venv/bin/python -m src.store_export --to /tmp/pool-verify-$ts --compare .   # all identical
PYTHONPATH=. .venv/bin/python -m src.store_check                        # projection consistent
```

**4. Point the service at the database** — a drop-in, so the unit file itself is untouched:

```sh
cat > ~/.config/systemd/user/pool-workbench.service.d/20-postgres.conf <<'EOF'
[Unit]
Requires=pool-postgres.service
After=pool-postgres.service

[Service]
EnvironmentFile=%h/.config/pool/postgres.env
EOF
systemctl --user daemon-reload && systemctl --user start pool-workbench
```

**5. Post-cutover checks**

- a. `systemctl --user is-active pool-postgres pool-workbench` → `active` twice;
  `journalctl --user -u pool-workbench -n 50` shows no traceback.
- b. `GET http://127.0.0.1:8130/api/operations` returns the `revision` the file had
  (`python3 -c 'import json;print(json.load(open("out/corner-pocket/state.json"))["revision"])'`).
- c. One harmless write, then its removal.  First
  `md5sum out/corner-pocket/state.json > /tmp/pool-5c-$ts.md5`.  In Operations → Notes add
  the note **`cutover check — delete me`**, then delete that same note (its × button).  Then:
  `md5sum -c /tmp/pool-5c-$ts.md5` → `OK` (the file was not written), and
  `GET /api/operations` shows `revision` = the value from b + 2 and no note with that text
  (the add and the delete are both in the database's event log).
- d. `PYTHONPATH=. .venv/bin/python -m src.store_check` → consistent.
- e. Open Floor, Matches and Vision once; `md5sum -c ~/pool-cutover-$ts/MD5SUMS` from
  `~/pool-cutover-$ts` still matches the untouched files in `out/` (nothing writes them).

**6. Rollback** (design §7.6)

- *Before any write through Postgres*: `rm ~/.config/systemd/user/pool-workbench.service.d/20-postgres.conf
  && systemctl --user daemon-reload && systemctl --user restart pool-workbench` — the
  untouched files take over.
- *After writes through Postgres* (5c counts): stop the service, then
  `PYTHONPATH=. .venv/bin/python -m src.store_export --to . --prune` writes every user-data
  file back byte-exact over `out/` and deletes the ones the database holds nothing for
  (so deleted face data cannot come back from the old file); review `git status`/`diff -r`
  against `~/pool-cutover-$ts`, then remove the drop-in, `daemon-reload`, start.

Not covered by the database: the shot clock (`annotator/shot_clock.py`) keeps its own
file (design §9); it needs nothing at cutover.

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
