-- 0002: user data - operations, identity and enrolment, operator records.
-- The schema of docs/postgres-design.md sections 2-4 as reviewed, with one
-- measured change: embeddings and face scores are double precision, not real.
-- real (float4) returns 0.912 as 0.9120000004768372, so the file -> database ->
-- file round trip the import verifies could not be exact; double precision
-- returns every value the JSON files hold unchanged.
-- Nothing reads these tables yet: the JSON files stay the store until cutover.

-- operations (section 2): the revisioned document, normalised --------------
CREATE TABLE ops_meta (                  -- exactly one row: the document header
    id          boolean PRIMARY KEY DEFAULT true CHECK (id),
    revision    integer NOT NULL CHECK (revision >= 0),
    settings    jsonb   NOT NULL,        -- {shotClock, autoFrame, clothColor, lampGlow, showDiamonds}
    extra       jsonb   NOT NULL DEFAULT '{}'   -- top-level keys not modelled here, preserved
);                                       -- the current tournament = the one with archived_at IS NULL

CREATE TABLE players (
    id         text PRIMARY KEY,         -- uuid4().hex today; kept verbatim
    name       text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    status     text NOT NULL CHECK (status IN ('Active','Visitor','Prospect','Inactive')),
    rating     integer NOT NULL CHECK (rating BETWEEN 0 AND 1000),
    joined_at  text,                     -- the ISO string as written (round-trip exact)
    notes      text CHECK (length(notes) <= 4000),
    position   integer NOT NULL UNIQUE,  -- array order in state.players
    extra      jsonb NOT NULL DEFAULT '{}',  -- any key not modelled above, preserved
    -- annotator.operations.name_key(name): the application's own "same name" rule
    -- (casefold of the trimmed name), written by the store. PostgreSQL's lower() is a
    -- different rule (it folds 'İ' to 'i', and not 'ß' to 'ss'), so a unique index on
    -- lower(name) refused names the JSON store accepts; this one never disagrees.
    name_key   text NOT NULL CHECK (name_key <> '')
);
CREATE UNIQUE INDEX players_name_key ON players (name_key);

CREATE TABLE tournaments (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    format      text NOT NULL CHECK (format IN ('singles','doubles')),
    tables      integer NOT NULL CHECK (tables BETWEEN 1 AND 32),
    race_to     integer NOT NULL CHECK (race_to BETWEEN 1 AND 99),
    status      text NOT NULL CHECK (status IN ('registration','active','complete')),
    archived_at text,                    -- NULL = the current tournament, set = history[]
    position    integer,                 -- order within history[]
    extra       jsonb NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX one_current_tournament ON tournaments ((true)) WHERE archived_at IS NULL;

CREATE TABLE entrants (
    id            text PRIMARY KEY,
    tournament_id text NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    position      integer NOT NULL,
    absent        boolean,               -- NULL = key absent in the JSON (it is optional)
    extra         jsonb NOT NULL DEFAULT '{}',
    UNIQUE (tournament_id, position)
);

CREATE TABLE entrant_members (           -- a regular (player_id) or a guest (name only)
    entrant_id text NOT NULL REFERENCES entrants(id) ON DELETE CASCADE,
    position   integer NOT NULL,
    player_id  text REFERENCES players(id),  -- RESTRICT: a player with history is marked Inactive, not deleted
    name       text NOT NULL,
    PRIMARY KEY (entrant_id, position)
);

CREATE TABLE matches (
    id            text PRIMARY KEY,
    tournament_id text NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    position      integer NOT NULL,
    round         integer NOT NULL,
    side_a        text REFERENCES entrants(id),
    side_b        text REFERENCES entrants(id),
    score_a       integer NOT NULL,
    score_b       integer NOT NULL,
    table_no      integer,
    status        text NOT NULL CHECK (status IN ('pending','scheduled','delayed','live','complete')),
    winner_id     text REFERENCES entrants(id),
    result        text CHECK (result IN ('played','forfeit','bye')),
    completed_at  text,
    source_a      text REFERENCES matches(id) DEFERRABLE INITIALLY DEFERRED,
    source_b      text REFERENCES matches(id) DEFERRABLE INITIALLY DEFERRED,
    absent        text[] NOT NULL DEFAULT '{}',
    extra         jsonb NOT NULL DEFAULT '{}',
    UNIQUE (tournament_id, position)
);
CREATE UNIQUE INDEX one_match_per_live_table ON matches (tournament_id, table_no) WHERE status = 'live';

CREATE TABLE notes (
    id         text PRIMARY KEY,
    text       text NOT NULL,
    created_at text NOT NULL,
    position   integer NOT NULL UNIQUE
);

CREATE TABLE sources (
    id       text PRIMARY KEY,
    url      text NOT NULL UNIQUE,
    kind     text NOT NULL CHECK (kind IN ('channel','video')),
    channel  text,
    video    text,
    position integer NOT NULL UNIQUE
);

CREATE TABLE ops_events (                -- the event log, never truncated in the database
    revision   integer PRIMARY KEY,      -- one event per revision
    id         text NOT NULL UNIQUE,
    created_at text NOT NULL,
    action     text NOT NULL,
    context    jsonb NOT NULL
);

-- identity and enrolment (section 3) -----------------------------------------
CREATE TABLE identity_clusters (
    cluster_id      integer PRIMARY KEY,
    -- reviewed decision: an assignment must name a roster player; deleting the
    -- player unbinds the cluster
    player_id       text REFERENCES players(id) ON DELETE SET NULL,
    body_bank       double precision[] NOT NULL,   -- up to 8 x body_dim, flattened in order
    body_dim        integer CHECK (body_dim IN (128)),
    face            double precision[],            -- 512 or NULL
    last_seen_frame integer,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (body_dim IS NOT NULL OR cardinality(body_bank) = 0),
    CHECK (face IS NULL OR cardinality(face) = 512)
);

CREATE TABLE identity_face_samples (
    cluster_id  integer NOT NULL REFERENCES identity_clusters(cluster_id) ON DELETE CASCADE,
    rank        integer NOT NULL CHECK (rank BETWEEN 0 AND 2),   -- PERSIST_FACES = 3
    embedding   double precision[] NOT NULL CHECK (cardinality(embedding) = 512),
    eye_px      double precision,
    det_score   double precision,
    bbox        double precision[],
    frame_index integer,
    PRIMARY KEY (cluster_id, rank)
);

CREATE TABLE face_embeddings (           -- biometric: its own table, its own deletion
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id   text NOT NULL,           -- no FK: the file store may hold ids the roster lost
    embedding   double precision[] NOT NULL CHECK (cardinality(embedding) = 512),
    eye_px      double precision,
    det_score   double precision,
    created_at  text NOT NULL,
    source      text,                    -- image path or "<track_id>"; a path, never bytes
    position    integer NOT NULL,
    UNIQUE (player_id, position)
);
CREATE INDEX face_embeddings_player ON face_embeddings (player_id);

CREATE TABLE track_seeds (
    dataset  text    NOT NULL DEFAULT 'vod30',
    win      text    NOT NULL,           -- "68-94"
    track_id integer NOT NULL,
    t        double precision,
    label    text    NOT NULL CHECK (label IN ('A','B','ignore') OR length(label) BETWEEN 1 AND 60),
    seed_key text    NOT NULL,           -- the JSON key as written ("<track_id>:<win>")
    extra    jsonb   NOT NULL DEFAULT '{}',
    PRIMARY KEY (dataset, win, track_id),
    UNIQUE (dataset, seed_key)
);

-- operator records (section 4) -------------------------------------------------
CREATE TABLE event_verdicts (
    dataset    text NOT NULL CHECK (dataset IN ('vod30','highlight')),
    event_id   text NOT NULL,            -- the JSON key as written (queue ids, stable, never reused)
    verdict    text CHECK (verdict IN ('correct','wrong','unsure')),
    shooter    text CHECK (shooter IN ('A','B','?','')),
    note       text CHECK (length(note) <= 10000),
    updated_at text,
    extra      jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (dataset, event_id)
);

CREATE TABLE ball_labels (
    crop_set  text NOT NULL CHECK (crop_set IN ('unlabeled_crops','unlabeled_crops2','vod30_event_crops')),
    crop_key  text NOT NULL,             -- the original key verbatim (often an absolute path)
    crop_file text NOT NULL,             -- its basename: the API matches on it
    label     jsonb NOT NULL CHECK (label = '"u"'::jsonb
                                    OR (jsonb_typeof(label) = 'number' AND (label)::text ~ '^(1[0-5]|[0-9])$')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (crop_set, crop_key)
);
CREATE INDEX ball_labels_file ON ball_labels (crop_set, crop_file);

CREATE TABLE frame_corrections (
    dataset     text    NOT NULL CHECK (dataset IN ('vod30','highlight')),
    frame_index integer NOT NULL CHECK (frame_index >= 0),
    payload     jsonb   NOT NULL,        -- {boxes, table_polygon, source, saved_at, + frame meta}
    saved_at    text,
    PRIMARY KEY (dataset, frame_index)
);

CREATE TABLE pocket_anchors (            -- operator-written (POST /api/vod30/anchors)
    dataset    text NOT NULL,
    t_key      text NOT NULL,            -- the JSON key as written ("70.0")
    t          double precision NOT NULL,
    pts        jsonb NOT NULL CHECK (jsonb_array_length(pts) = 6),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset, t)
);
