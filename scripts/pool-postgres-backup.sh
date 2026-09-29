#!/usr/bin/env bash
# Corner Pocket PostgreSQL backup (docs/postgres.md "Scheduled backups").
#
#   pool-postgres-backup.sh dump    # pg_dump -Fc of `pool`, verified, then prune > KEEP_DAYS
#   pool-postgres-backup.sh verify  # pg_restore --list of the newest dump (weekly sanity read)
#
# Run by pool-postgres-backup.service (daily) and pool-postgres-verify.service (weekly).
# Every failure exits non-zero with a line on stderr, so the journal shows it and the
# unit enters the failed state (systemctl --user --failed lists it).
set -euo pipefail
umask 077

DIR="${POOL_BACKUP_DIR:-$POOL_PG_ROOT/pool-postgres/backups}"
KEEP_DAYS="${POOL_BACKUP_KEEP_DAYS:-14}"
CONTAINER="${POOL_BACKUP_CONTAINER:-pool-postgres}"
PODMAN="${PODMAN:-podman}"

fail() { echo "pool-postgres-backup: FAILED: $*" >&2; exit 1; }

[ -d "$DIR" ] || fail "backup directory $DIR does not exist"
[ "$(stat -c %a "$DIR")" = 700 ] || fail "backup directory $DIR must be mode 700 (is $(stat -c %a "$DIR"))"

case "${1:-}" in
dump)
    ts=$(date +%Y%m%d-%H%M%S)
    final="$DIR/pool-$ts.dump"
    tmp="$DIR/.pool-$ts.dump.partial"
    trap 'rm -f "$tmp"' EXIT
    "$PODMAN" exec "$CONTAINER" pg_isready -h 127.0.0.1 -p 5432 -U pool -d pool >/dev/null \
        || fail "the database is not accepting connections"
    "$PODMAN" exec "$CONTAINER" pg_dump -U pool -d pool -Fc -Z 6 > "$tmp" || fail "pg_dump exited $?"
    [ -s "$tmp" ] || fail "pg_dump wrote an empty file"
    # the archive must read back before it replaces anything
    entries=$("$PODMAN" exec -i "$CONTAINER" pg_restore --list < "$tmp" | grep -c ' TABLE DATA ') \
        || fail "pg_restore --list cannot read the new dump"
    [ "$entries" -gt 0 ] || fail "the new dump lists no table data"
    mv "$tmp" "$final"
    trap - EXIT
    # prune only after a good dump, and never the newest one
    find "$DIR" -maxdepth 1 -name 'pool-*.dump' -type f -mtime +"$KEEP_DAYS" ! -samefile "$final" -print -delete \
        | sed 's/^/pool-postgres-backup: pruned /'
    echo "pool-postgres-backup: ok $final ($(stat -c %s "$final") bytes, $entries tables with data)"
    ;;
verify)
    newest=$(find "$DIR" -maxdepth 1 -name 'pool-*.dump' -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
    [ -n "$newest" ] || fail "no dump in $DIR"
    age_h=$(( ($(date +%s) - $(stat -c %Y "$newest")) / 3600 ))
    [ "$age_h" -le 48 ] || fail "the newest dump $newest is ${age_h}h old: the daily backup is not running"
    entries=$("$PODMAN" exec -i "$CONTAINER" pg_restore --list < "$newest" | grep -c ' TABLE DATA ') \
        || fail "pg_restore --list cannot read $newest"
    [ "$entries" -gt 0 ] || fail "$newest lists no table data"
    echo "pool-postgres-backup: verified $newest (${age_h}h old, $entries tables with data)"
    ;;
*)
    fail "usage: $0 dump|verify"
    ;;
esac
