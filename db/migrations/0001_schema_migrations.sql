-- 0001: the migration runner's own ledger (src/db.py migrate()).
-- The application schema waits for the design review (docs/postgres-design.md).
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    integer     PRIMARY KEY CHECK (version > 0),
    name       text        NOT NULL UNIQUE,
    checksum   text        NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
