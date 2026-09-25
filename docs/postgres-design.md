# PostgreSQL backend — design (for review; nothing here is built yet)

*2026-09-25 · Phase B of the Postgres assignment · infrastructure is `docs/postgres.md`
(commit `d067cb7`).  Every structure below was read from the code and the production files
on this date; line numbers are `main` at `d067cb7` (`git show d067cb7:<path>`; the only later
change to a cited file, `258acd8`, adds two lines to `annotator/operations.py` after `:281`).
No schema, no import, no cutover happens until this document is reviewed.*

## 0. Decisions this document asks for

1. **Scope of the first cutover** — the *user data* (§2–§4: operations, identity index, face
   store, seeds, verdicts, labels) moves first.  Precomputed visual data (§5–§6) follows as
   separate steps; `frame_detections` is new (it replaces a per-request computation), not a
   migration.
2. **Operations keeps its revisioned-document contract exactly** (`GET` returns the whole
   state with `revision`; `POST` carries the `revision` it read; mismatch = `409`).  The
   database stores the document *normalised* but reassembles the identical JSON.  Section 2.3
   is the concrete mapping; approve or send it back.
3. **Two pre-existing defects** found while reading (§2.4, §3.3) are fixed *by* the store
   layer, not preserved.  Both lose data today.  Confirm that they may be fixed there.
4. **Biometric data** (face embeddings) gets its own table and its own delete path; it
   stays out of the operations event log, as today (`src/face_id.py:5-7`).

## 1. Inventory — every data set, its size today, and who touches it

Production sizes measured 2026-09-25 (md5s of the five tracked files are in the Phase A
report and did not change).

| Data set | File | Size now | Written at request time? |
|---|---|---|---|
| Operations (players, entrants, tables, matches, results, notes, sources, settings, event log) | `out/corner-pocket/state.json` | 1.9 kB, `revision` 5 (an operator's `entrant_remove` at 14:31 PDT), 0 players, 0 entrants, 5 events | yes — `POST /api/operations`, enrolment confirm |
| Identity index (person clusters) | `out/identity/clusters.json` | 682 kB, 48 clusters, 0 bound, body dim 128 | yes — seed / unbind / face bind |
| Face store (biometric gallery) | `out/corner-pocket/face_embeddings.json` | **absent** | yes — enrol photo, enrolment confirm |
| Track seeds | `out/pid_seed.json` | 18 B, 0 seeds | yes — `POST /api/vod30/seeds` |
| Operator verdicts | `out/scan30/annotations.json` | 131 B, 1 verdict (id 16) | yes — `POST /api/<ds>/annotate` |
| Ball labels | `out/<set>/labels.json` (3 sets) | 76 labels in `unlabeled_crops`; 0 in the other two | yes — `POST /api/balls/<set>/label` |
| Frame corrections | `out/scan30/frame_results/<frame>/correction.json` | 0 files | yes — `POST /api/frame-correction` |
| Review queue | `out/scan30/events.json` (+ `scan_highlight/events.json`) | 4 events (vod30), 9 (highlight) | no — batch (`src/dense_queue.py`) |
| Queue report + retired-id ledger | `out/scan30/dense_queue_report.json`, `dense_queue_retired.json` | 25 kB, 1.2 kB | no — batch |
| Stored frame inference | `out/scan30/frame_results/<frame>/inference.json` | 2 files (frames 0, 2100), 10 kB | no (legacy; the endpoint no longer writes) |
| Calibration | `out/calib_vod30_segments.json`, `out/calib_vod30.json` | 24 kB, 0.7 kB | no — batch |
| Pocket anchors | `out/pid_anchors_vod30.json` | 318 B, 1 anchor set (t=70.0) | yes — `POST /api/vod30/anchors` |
| Tracklets + seed propagation | `out/pid2_tracklets.json`, `pid_seed_tracks.json`, `pid_seed_protos.json`, `events_actors.json` | 25 kB (4 windows, 21 tracklets, 252 samples), 2 kB, –, 8 kB | propagation: yes (`POST /api/vod30/rebuild` runs a subprocess) |

No production JSON contains `NaN`, `Infinity` or `\u0000` (checked with a strict parser), so
every document fits `jsonb` unchanged.

The SQL in this document is a draft for review, but it is not unchecked: all 29 statements
(24 tables) were applied to a scratch schema on the `pool-postgres` instance
(PostgreSQL 17.11) and the schema was dropped.  Nothing was added to `db/migrations/`.

### 1.1 Concurrency today → in Postgres

The server is a `ThreadingHTTPServer` (`unified_server.py:23,1643`): requests run
concurrently in one process.  Every file write is a whole-file read–modify–write, safe only
because of an in-process lock; nothing protects against a second process (a CLI tool, the
legacy servers, a second server instance).

| Data set | Serialised today by | Lost-update risk today | In Postgres |
|---|---|---|---|
| Operations | `Operations.lock` (per-path `RLock`, `operations.py:52-58`) + `revision` check | the enrolment promotion bypasses both (§2.4); any second process | `SELECT … FOR UPDATE` on `ops_meta` + the same `revision` check (§2.3) |
| Identity index | `Backend._identity_lock` (`unified_server.py:278`) around the pipeline | whole-file rewrite by any second `IdentityIndex` on the same path | one transaction per save, upsert of the dirty clusters only; last writer wins **per cluster** |
| Face store | `_identity_lock` for `enroll`; **no lock** for the confirm promotion (`:516`) | the promotion replaces the whole gallery (§3.3) | append-only rows per player; no read–modify–write |
| Seeds, verdicts, labels, anchors, corrections | `Backend.lock` around all of `_post` (`:1367-1368`, `:1145`) | a second process; seeds are refused during a rebuild (`:1431`) | one row per key, `INSERT … ON CONFLICT DO UPDATE`: two writers to *different* keys never clobber each other; same key = last write wins, as today |
| Precomputed artifacts | none (batch tools write with `write_text`, `dense_queue.py:637,709`) | a reader can see the new queue with the old report | new version + `artifact_current` flip in one transaction (§5) |

**What stays on disk, always:** the videos (`data/*.mp4`, vod30 = 690 MB), decoded frames,
crops (`out/<set>/*.png`), evidence JPEGs, the clip cache, model weights, and the batch
artifacts the server never reads (`out/dense-events/*.json`, eval reports, logs).  The
database stores *paths relative to the repo root* for those (`data/vod_30min_260815.mp4`,
`out/unlabeled_crops/…png`), never bytes.

## 2. Operations state — the revisioned document

### 2.1 Today

* Store: `annotator/operations.py` `Operations` — path `:56`, per-path process-wide `RLock`
  `:52-58`, `_load` `:60-67` (missing file → default document with one Twitch source),
  `get` `:69-71`, `post` `:73-101`.
* `post` = one read–check–apply–write under the lock: integer `revision` required `:78`,
  `payload.revision != state.revision` → `ConflictError` `:80-81` (`409` at
  `unified_server.py:1349`), whitelisted event context before and after `:82-85`
  (`_event_context` `:104-134` — never note or request contents), `revision += 1` `:86`,
  one event `{id, createdAt, revision, action, context}` appended and the log **truncated to
  the last 500** `:87-88`, then temp file + `fsync` + `os.replace` `:89-100`.
* Actions (`_apply` `:165-377`): `player_save` `:168`, `guest_promote` `:183`,
  `player_delete` `:195` (refused when any tournament — current or archived — references
  the player `:197`), `tournament_setup` `:200`, `entrant_add|remove|absence` `:212`,
  `tournament_start` `:250` (builds the whole single-elimination bracket; `sources` link each
  match to its two feeder matches), `match_schedule|unschedule|score|complete|absence|forfeit`
  `:275`, `tournament_new` `:324` (deep-copies the tournament into `history[]` with
  `archivedAt`, when it had entrants or matches), `source_add|delete` `:332/:349`,
  `settings_update` `:352`, `note_add|delete` `:372/:374`.
* Readers: `unified_server.py:1267-1268` (`GET /api/operations`),
  `annotator/live_processing.py:161` (reads `sources[]` to resolve a saved Twitch channel),
  `src/enroll_from_tracklet.py:160-162` `load_state` (roster for enrolment planning),
  `src/eval_faces.py:78` (offline evaluation).
* Writers: `Operations.post` (above) **and** the enrolment promotion —
  `enroll_from_tracklet.py:424-437` `_roster_payload` builds a whole new document (player
  appended, `revision + 1`, event `player_enroll_from_tracklet` with context
  `{player_id, name, track_id, faces, frames}`), `write_enrollment` `:558-576` writes it to a
  scratch root, and `unified_server.py:521-540` `_promote_enrollment` copies it over
  `state.json` with `atomic_save`.

### 2.2 Tables

```sql
CREATE TABLE ops_meta (                 -- exactly one row: the document header
    id          boolean PRIMARY KEY DEFAULT true CHECK (id),
    revision    integer NOT NULL CHECK (revision >= 0),
    settings    jsonb   NOT NULL         -- {shotClock, autoFrame, clothColor, lampGlow, showDiamonds}
);                                       -- the current tournament = the one with archived_at IS NULL
CREATE TABLE players (
    id         text PRIMARY KEY,         -- uuid4().hex today; kept verbatim
    name       text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    status     text NOT NULL CHECK (status IN ('Active','Visitor','Prospect','Inactive')),
    rating     integer NOT NULL CHECK (rating BETWEEN 0 AND 1000),
    joined_at  text NOT NULL,            -- the ISO string as written (round-trip exact)
    notes      text CHECK (length(notes) <= 4000),
    position   integer NOT NULL,         -- array order in state.players
    extra      jsonb NOT NULL DEFAULT '{}'   -- any key not modelled above, preserved
);
CREATE UNIQUE INDEX players_name_ci ON players (lower(name));   -- backstop for the casefold rule at :170
                                         -- (lower() is weaker than casefold(): the app check stays authoritative)
CREATE TABLE tournaments (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    format      text NOT NULL CHECK (format IN ('singles','doubles')),
    tables      integer NOT NULL CHECK (tables BETWEEN 1 AND 32),
    race_to     integer NOT NULL CHECK (race_to BETWEEN 1 AND 99),
    status      text NOT NULL CHECK (status IN ('registration','active','complete')),
    archived_at text,                    -- NULL = current, set = history[]
    position    integer                  -- order within history[]
);
CREATE UNIQUE INDEX one_current_tournament ON tournaments ((true)) WHERE archived_at IS NULL;
CREATE TABLE entrants (
    id            text PRIMARY KEY,
    tournament_id text NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    position      integer NOT NULL,
    absent        boolean,               -- NULL = key absent in the JSON (it is optional)
    UNIQUE (tournament_id, position)
);
CREATE TABLE entrant_members (           -- a regular (player_id) or a guest (name only)
    entrant_id text NOT NULL REFERENCES entrants(id) ON DELETE CASCADE,
    position   integer NOT NULL,
    player_id  text REFERENCES players(id),  -- RESTRICT: the "has history, mark Inactive" rule at :197
    name       text NOT NULL,
    PRIMARY KEY (entrant_id, position)
);
CREATE TABLE matches (
    id            text PRIMARY KEY,
    tournament_id text NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    position      integer NOT NULL,
    round         integer NOT NULL,
    side_a        text REFERENCES entrants(id), side_b text REFERENCES entrants(id),
    score_a       integer NOT NULL, score_b integer NOT NULL,
    table_no      integer,
    status        text NOT NULL CHECK (status IN ('pending','scheduled','delayed','live','complete')),
    winner_id     text REFERENCES entrants(id),
    result        text CHECK (result IN ('played','forfeit','bye')),
    completed_at  text,
    source_a      text REFERENCES matches(id), source_b text REFERENCES matches(id),
    absent        text[] NOT NULL DEFAULT '{}',
    UNIQUE (tournament_id, position)
);
CREATE UNIQUE INDEX one_match_per_live_table ON matches (tournament_id, table_no) WHERE status = 'live';
CREATE TABLE notes   (id text PRIMARY KEY, text text NOT NULL, created_at text NOT NULL, position integer NOT NULL);
CREATE TABLE sources (id text PRIMARY KEY, url text NOT NULL UNIQUE, kind text NOT NULL CHECK (kind IN ('channel','video')),
                      channel text, video text, position integer NOT NULL);
CREATE TABLE ops_events (                -- the event log, never truncated in the database
    revision   integer PRIMARY KEY,      -- one event per revision
    id         text NOT NULL UNIQUE,
    created_at text NOT NULL,
    action     text NOT NULL,
    context    jsonb NOT NULL
);
```

Notes on the choices:

* **Timestamps stay `text`.**  The application compares, sorts and returns them as the ISO
  strings it wrote (`timestamp()` `:23`); a `timestamptz` would re-render them
  (`+00:00` vs `Z`, precision) and break the byte-for-byte round trip that §7.3 verifies.
  `created_at` of rows that only the database writes (`schema_migrations`, `computed_at`)
  is `timestamptz`.
* **`position` columns** keep array order.  The UI and `_event_context` (`:127-128`,
  "no id → last item") depend on it.
* **`extra jsonb`** on players keeps unknown keys, so the store never drops a field a later
  worker adds to the JSON before the schema learns it.
* **The 500-event cap** (`:88`) is a *view* concern in the database: `get()` returns the
  last 500 events so the document is unchanged, the table keeps all of them (the audit
  record the cap was only protecting the file size from).
* **Constraints encode what `_apply` already enforces** (name uniqueness, one live match per
  table, status vocabularies, ranges).  `_apply` keeps enforcing them first — its error
  messages are the API — and the constraint is the backstop that makes a bug fail loudly
  instead of corrupting the roster.

### 2.3 How revisions and conflict detection survive

The contract stays exactly *read revision N → post with N → 409 if the store is no longer
at N*.  In Postgres:

```
BEGIN;
SELECT revision FROM ops_meta FOR UPDATE;          -- the row lock replaces the file RLock
-- revision != payload.revision  -> ROLLBACK, ConflictError  (409, same message)
-- load the document (same transaction), run the unchanged _apply() on the dict,
-- diff old vs new document -> INSERT/UPDATE/DELETE only the rows that changed
UPDATE ops_meta SET revision = revision + 1 ...;
INSERT INTO ops_events (revision, id, created_at, action, context) VALUES (N+1, ...);
COMMIT;
```

* **`_apply` is not rewritten.**  The Postgres store loads the document into the same dict
  shape, runs the same `_apply`/`_propagate`/`_event_context`, and persists the difference.
  All ~200 lines of tournament logic and their tests stay the single implementation.
* **The row lock serialises writers across processes**, which the file store cannot do
  (its `RLock` is per process; a second server or a CLI writing `state.json` races it).
* **`ops_events.revision` is the primary key**, so two writers that both passed the check
  (impossible under `FOR UPDATE`, but defended anyway) cannot both commit revision N+1.
* **Crash safety** is the transaction: either the new revision, its rows and its event are
  all visible, or none is — the property `mkstemp`+`fsync`+`os.replace` gives the file today.

### 2.4 Defect to fix: the enrolment promotion bypasses the revision check

`_promote_enrollment` (`unified_server.py:521-540`) overwrites `state.json` with a document
built from a roster read **earlier and outside the `Operations` lock**
(`confirm_enrollment` → `load_state`, `enroll_from_tracklet.py:934`).  Any
`POST /api/operations` accepted between the preview and the confirm (a score, a new
entrant) is silently lost, and the revision does not detect it because the promoted
document carries `old + 1`.  In the store layer the promotion becomes one store operation,
`enroll_player(player, event_context, faces)`, that runs inside the same
`FOR UPDATE` transaction as any other mutation: it re-reads the current roster, applies the
append, bumps the revision and writes the event.  The file implementation gets the same
method (under `Operations.lock`), so the fix lands for both backends.

## 3. Identity and enrolment

### 3.1 Identity index — `out/identity/clusters.json`

* Code: `src/person_identity.py` `IdentityIndex` — path `:73`, `save` `:368-390` (whole
  file, `os.replace`), `_load` `:392-421`.  Persisted per cluster: `player_id`, `body_bank`
  (last 8 of a 32-deep bank, 128-d), `face` (512-d or null), `face_samples` (top 3,
  4-dp rounded), `last_seen_frame`.  Not persisted: `evidence` (`:400`), the
  track→cluster map, the full bank.
* Writes happen only on durable decisions: `explicit_assign` `:281-286` (seed, and unbind
  with `player_id=None`), `bind_face` `:288-325`.  Observation (`update`, `register`,
  `record_face_sample`) stays in memory — `tests/test_unified_server.py:791`
  (`test_identity_frame_read_leaves_the_index_file_untouched`) pins that a GET never writes.
* Callers: `src/person_pipeline.py:61` (constructs it), `unified_server.py:407-436`
  (`/api/identity/seed`, `/unbind`), `:393-405` (status), `:682-691` (every unified
  frame runs `process_frame`, which may `bind_face` → a **write during `GET /api/unified`**
  when a face matches; see §8.2), `src/enroll_from_tracklet.py:1152-1159` (reads it).

```sql
CREATE TABLE identity_clusters (
    cluster_id      integer PRIMARY KEY,
    player_id       text REFERENCES players(id) ON DELETE SET NULL,
    body_bank       real[] NOT NULL,         -- up to 8 x 128, flattened; dim in body_dim
    body_dim        integer CHECK (body_dim IN (128)),
    face            real[],                  -- 512 or NULL
    last_seen_frame integer,
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE identity_face_samples (
    cluster_id  integer NOT NULL REFERENCES identity_clusters(cluster_id) ON DELETE CASCADE,
    rank        integer NOT NULL CHECK (rank BETWEEN 0 AND 2),  -- PERSIST_FACES = 3
    embedding   real[] NOT NULL, eye_px real, det_score real, bbox real[], frame_index integer,
    PRIMARY KEY (cluster_id, rank)
);
```

`save()` today rewrites all clusters; the Postgres implementation upserts only the
clusters marked dirty since the last save (in one transaction), so a bind no longer rewrites
682 kB.  `player_id` gains a foreign key: an id that is not in the roster can no longer be
assigned (today a typo in `/api/identity/seed` is stored).  **Open point:** the seed
endpoint also accepts legacy role ids; if the owner wants to keep binding to ids that are not
roster players, the FK is dropped and a `CHECK` on format is kept instead.

`real[]` rather than `pgvector`: the matching runs in NumPy against a gallery of a few dozen
vectors (`src/face_id.py:209-252`); nothing queries by vector distance in SQL.  If a later
feature needs nearest-neighbour search in the database, `pgvector` is a separate decision
(it is not in the official image).

### 3.2 Face store — `out/corner-pocket/face_embeddings.json`

* Code: `src/face_id.py` `DEFAULT_FACE_STORE` `:52`, `store_faces` `:291-315` (whole file,
  4-dp rounding, `created_at` filled), `load_faces` `:318-326` (`{}` on missing/corrupt).
* Writers: `src/person_pipeline.py:267-275` `enroll_face` (`POST /api/identity/enroll`,
  `unified_server.py:367-391`), and the enrolment promotion (`unified_server.py:530-538`).
* Readers: `person_pipeline.py:262-265` (`_gallery_data`, cached for the pipeline's life),
  `src/eval_faces.py:1015`.

```sql
CREATE TABLE face_embeddings (           -- biometric: separate table, separate deletion
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id   text NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    embedding   real[] NOT NULL CHECK (array_length(embedding, 1) = 512),
    eye_px      real, det_score real,
    created_at  text NOT NULL,
    source      text,                    -- image path or "<track_id>"; a path, never bytes
    position    integer NOT NULL,
    UNIQUE (player_id, position)
);
```

`ON DELETE CASCADE` makes "delete this player" also delete their biometrics — the privacy
property the separate file only implied.  Embeddings are stored at the 4-dp precision the
file uses (`real` holds that exactly enough for the round trip; §7.3 compares after the same
rounding).

### 3.3 Defect to fix: a confirmed enrolment replaces the whole face gallery

`plan_enrollment` builds `store_json = {new_player_id: [...]}` only
(`enroll_from_tracklet.py:416-417`); `write_enrollment` writes exactly that
(`:574-575`); `_promote_enrollment` then `atomic_save`s it over
`out/corner-pocket/face_embeddings.json` (`unified_server.py:530-538`).  Every previously
enrolled player's faces are deleted by the next confirmed enrolment.  (The existing test
`test_a_second_enrolment_appends_to_the_scratch_store`, `tests/test_enroll_from_tracklet.py:429`,
checks the *roster*, not the store.)  It has not bitten yet only because the store is absent
in production.  Also, `PersonPipeline._gallery` caches the gallery (`person_pipeline.py:263`)
and nothing invalidates it after a promotion, so a confirmed enrolment is not matched until a
restart.  The store operation `enroll_player(...)` (§2.4) appends rows and bumps a
`gallery_version` the pipeline checks; the file implementation merges instead of replacing.

### 3.4 Track seeds — `out/pid_seed.json`

* Shape: `{"seeds": {"<track_id>:<window>": {win, t, track_id, label}}}`; label is `A`,
  `B`, `ignore` or a guest name ≤ 60 chars (`unified_server.py:1245-1265`).
* Writer: `POST /api/vod30/seeds` `unified_server.py:1430-1453` (refused while a rebuild
  runs `:1431`).  Also `src/pid_seed_ui.py:192-194` (standalone legacy UI, plain
  `write_text`).
* Readers: `unified_server.py:1242-1243` `seeds()` (used by `/tracklets`, `/tracks`,
  `predictions()` `:1229-1237`), `src/pid_seed_rebuild.py:28-29` (subprocess),
  `src/pid_seed_ui.py:165-192`, `src/eval_faces.py:79`, `tests/live_identity_validation.py`.

```sql
CREATE TABLE track_seeds (
    dataset  text    NOT NULL DEFAULT 'vod30',
    win      text    NOT NULL,           -- "68-94"
    track_id integer NOT NULL,
    t        double precision NOT NULL,
    label    text    NOT NULL CHECK (label IN ('A','B','ignore') OR length(label) BETWEEN 1 AND 60),
    extra    jsonb   NOT NULL DEFAULT '{}',
    PRIMARY KEY (dataset, win, track_id)
);
```

The rebuild subprocess (`_rebuild` `unified_server.py:1462-1472`) reads seeds from the
store (same `POOL_DATABASE_URL` inherited through the environment) and writes its
propagation result to `seed_propagation` (§5.5).  The "stale" rule
(`predictions()` compares `seed_labels` with the live seeds `:1234`) is unchanged.

## 4. Operator verdicts, ball labels, frame corrections

### 4.1 Verdicts — `out/scan30/annotations.json`

* Shape: `{"<event id>": {verdict, note, shooter, updated_at}}`; verdict ∈
  `correct|wrong|unsure`, shooter ∈ `A|B|?|""`, note ≤ 10 000 chars.
* Writer: `POST /api/<dataset>/annotate` `unified_server.py:1395-1411` (event must exist in
  that dataset's `events.json` `:1397`; merge-update of the record).  Legacy
  `annotator/server.py:136-144` (old single-page annotator, plain `write_text`; it writes
  `annotations.json` next to whatever `events.json` its first argument names, `:18-20`).
* Readers: `GET /api/<dataset>/events` `:1309`, `src/dense_queue.py:71` (only its md5;
  "never opened for writing" `:45-46`), `src/eval_events.py:73-74`, `src/eval_faces.py:80`.

```sql
CREATE TABLE event_verdicts (
    dataset    text    NOT NULL,
    event_id   integer NOT NULL,         -- queue ids are ints (vod30 4/4); stable, retired ids never reused
    verdict    text CHECK (verdict IN ('correct','wrong','unsure')),
    shooter    text CHECK (shooter IN ('A','B','?','')),
    note       text CHECK (length(note) <= 10000),
    updated_at text NOT NULL,
    extra      jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (dataset, event_id)
);
```

No foreign key to `queue_events`: a verdict must survive its event leaving the queue — the
retired-id ledger exists precisely so a verdict keeps pointing at the ball it was given for
(`dense_queue.py:40-46`).  `event_id` stays text-compatible in the API (`str(e["id"])`).

### 4.2 Ball labels — `out/<set>/labels.json`

* Shape: `{"<absolute crop path>": 0..15 | "u"}`; sets `unlabeled_crops` (76 labels, keys are
  absolute paths), `unlabeled_crops2`, `vod30_event_crops` (no label file yet).
* Writer: `POST /api/balls/<set>/label` `unified_server.py:1371-1390`; legacy
  `annotator/server.py:123`; `src/merge_sets.py:44` (offline).
* Readers: `GET /api/balls/<set>/meta` `:1286-1295`, training/offline tools
  (`src/train_ball_id.py:61-64`, `src/confusion.py:18`, `src/merge_sets.py:21`).

```sql
CREATE TABLE ball_labels (
    crop_set  text NOT NULL CHECK (crop_set IN ('unlabeled_crops','unlabeled_crops2','vod30_event_crops')),
    crop_file text NOT NULL,             -- basename (the API already matches on Path(k).name)
    crop_key  text NOT NULL,             -- the original key verbatim, for an exact round trip
    label     text NOT NULL CHECK (label = 'u' OR label ~ '^(1[0-5]|[0-9])$'),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (crop_set, crop_file)
);
```

The offline training tools keep reading `labels.json`; the store offers an `export` that
writes the file from the table (§7.4), so they need no change.

### 4.3 Frame corrections — `frame_results/<frame>/correction.json`

* Writer: `POST /api/frame-correction` `unified_server.py:1117-1147`; reader
  `frame_result()` `:1104-1115`; path `frame_path()` `:1043-1044`.  Zero exist today
  (one `correction.superseded.json` at frame 2100 is read by nothing).

```sql
CREATE TABLE frame_corrections (
    dataset text NOT NULL, frame_index integer NOT NULL,
    payload jsonb NOT NULL,                  -- {boxes, table_polygon, source, saved_at, + frame meta}
    saved_at text NOT NULL,
    PRIMARY KEY (dataset, frame_index)
);
```

Last write wins, as today; the whole payload is a document the UI reads back verbatim.

## 5. Precomputed visual data the server reads at request time

These are **batch outputs**.  The server only reads them; batch tools produce them.  In
the database each becomes an immutable, versioned row — a new run inserts a new version and
flips a "current" pointer in the same transaction, so a reader sees the old or the new
artifact, never a mix (today a reader can catch `dense_queue.py` between writing
`events.json` `:637` and the report `:709`, which are two separate non-atomic
`write_text` calls).

```sql
CREATE TABLE artifacts (                 -- one row per produced version of one artifact
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind        text NOT NULL,           -- 'queue_report','queue_retired','calibration_segments',
                                         -- 'calibration','pocket_anchors','tracklets',
                                         -- 'seed_propagation','seed_prototypes','event_actors',
                                         -- 'frame_inference'
    dataset     text NOT NULL,
    key         text NOT NULL DEFAULT '', -- e.g. frame index for 'frame_inference'
    payload     jsonb NOT NULL,          -- the file's JSON, verbatim
    source_path text,                    -- the file it was imported from / exported to
    source_md5  text,
    produced_by text,                    -- tool + git sha
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE artifact_current (
    kind text NOT NULL, dataset text NOT NULL, key text NOT NULL DEFAULT '',
    artifact_id bigint NOT NULL REFERENCES artifacts(id),
    PRIMARY KEY (kind, dataset, key)
);
```

A document table is deliberate for these: each is read whole, by one reader, and its inner
structure is owned by the tool that wrote it (the queue report alone has nine top-level
sections that change shape between tool versions).  Normalising them would couple the schema
to every batch tool.  The two that are *queried* rather than read whole get real tables:

### 5.1 Review queue — `out/<scan>/events.json`

* Writers (batch only): `src/dense_queue.py:587-637` (`build`, the served queue),
  `src/scan_events.py:338-342`, `src/info_complete_scan.py:413`,
  `src/rebuild_events_calibrated.py:142`.  Readers: `unified_server.py:1300-1310`
  (`GET /api/<ds>/events`), `:1397` (annotate validation), `:696` (`_unified_events`, every
  unified frame), `:1223` (`event_frame`), `src/motion_scan.py:2328-2340`,
  `src/candidate_scan.py:598-602`, `src/eval_events.py`, `src/timing_verify.py:777`.

```sql
CREATE TABLE queue_events (
    artifact_id bigint  NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,  -- the queue version
    dataset     text    NOT NULL,
    event_id    integer NOT NULL,
    t           double precision NOT NULL,
    type        text    NOT NULL,        -- 'pot' | 'shot' | ...
    position    integer NOT NULL,        -- served order
    payload     jsonb   NOT NULL,        -- the whole event object, verbatim
    PRIMARY KEY (artifact_id, event_id)
);
CREATE INDEX queue_events_t ON queue_events (artifact_id, t);   -- the ±3 s window per frame
CREATE TABLE retired_event_ids (                                 -- dense_queue_retired.json
    dataset text NOT NULL, ball_id text NOT NULL,
    event_id integer NOT NULL, detail jsonb NOT NULL,
    PRIMARY KEY (dataset, ball_id), UNIQUE (dataset, event_id)
);
```

`UNIQUE (dataset, event_id)` on the ledger is the "a retired id is dead for good" rule
(`dense_queue.py:377-400`) as a constraint.  The report stays an `artifacts` row
(`kind='queue_report'`).  `_unified_events` then asks for `t BETWEEN ts-3 AND ts+3` instead of
loading and scanning the whole queue per frame.

### 5.2 Stored frame inference — `frame_results/<frame>/inference.json`

Two legacy files; `GET /api/frame-result` still returns them labelled `stored_inference`
(`unified_server.py:1107-1115`).  They import as `artifacts(kind='frame_inference',
key='<frame>')`.  Nothing new writes this kind — the endpoint stopped writing it
(`:1181-1184`); `frame_detections` (§6) is its successor.

### 5.3 Calibration and anchors

* `out/calib_vod30_segments.json` — writer `src/calib_segment_fit.py:322`; readers
  `unified_server.py:723-748` (`_segments`, via `src/calib_segments.py:170-196` which caches
  on file mtime), `src/shot_pot_gate.py:15,105`, `src/tiny_ball_net.py:46`,
  `src/calib_mapping_audit.py`.  → `artifacts(kind='calibration_segments')`.
* `out/calib_vod30.json` — reader `unified_server.py:1211` (suggested anchor points).
  → `artifacts(kind='calibration')`.
* `out/pid_anchors_vod30.json` — **operator-written** (`POST /api/vod30/anchors`,
  `unified_server.py:1414-1429`), read by `anchor_info` `:1208` and, importantly, by
  `src/frame_inference.py:40-60` (`app_prior_for`: the static-camera prior every table
  detection searches around).  Because an operator writes it, it gets a table, not an
  artifact:

```sql
CREATE TABLE pocket_anchors (
    dataset text NOT NULL, t double precision NOT NULL,
    t_key   text NOT NULL,                   -- the JSON key as written ("70.0")
    pts     jsonb NOT NULL CHECK (jsonb_array_length(pts) = 6),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset, t)
);
```

The mtime-keyed caches (`calib_segments._CACHE`, `_unified_cache`) key on
`artifact_current.artifact_id` instead of `st_mtime_ns`.

### 5.4 Tracklets — `out/pid2_tracklets.json`

Writer `src/yolo_track.py:128` (batch); readers `unified_server.py:1239-1240` (`tracks()`,
used by `/tracklets`, `/tracks`, seed validation `:1436`), `src/pid_seed_rebuild.py:27`,
`src/pid_seed_ui.py:28`.  Shape: `{window: {n_tracklets, runtime_s, tracklets:[{id, dur, n,
samples:[[t, [x1,y1,x2,y2]], …]}]}}` — 4 windows, 21 tracklets, 252 samples.

```sql
CREATE TABLE tracklets (
    artifact_id bigint NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    dataset text NOT NULL, win text NOT NULL, track_id integer NOT NULL,
    dur double precision, n integer,
    samples jsonb NOT NULL,                  -- [[t, box], ...] verbatim
    PRIMARY KEY (artifact_id, win, track_id)
);
```

A table (not just an artifact) because `/tracks` asks "which tracks have a sample near t in
window w" and the seed write validates one `(win, track_id)`.  The window header
(`n_tracklets`, `runtime_s`) stays in the artifact payload.

### 5.5 Seed propagation and shooter attribution

`out/pid_seed_tracks.json` + `pid_seed_protos.json` (writer `src/pid_seed_rebuild.py:34-35,
100-101, 123-124`, readers `unified_server.py:1233`, `src/pid_seed_ui.py:30-31`) and
`out/events_actors.json` (writers `src/pid_shooter.py:111`, `src/pid_shooter2.py:119`; reader
`unified_server.py:1304`) → `artifacts` kinds `seed_propagation`, `seed_prototypes`,
`event_actors`.  Read whole, small, batch-written.

## 6. `frame_detections` — per-frame overlays, precomputed

### 6.1 Why

`GET /api/unified` (`unified_server.py:546-567`) decodes the frame and runs table detection
+ ball candidates (`_unified_detection` `:594-649`, a 24-entry in-memory LRU `:544`) and the
full person/identity pipeline (`_unified_persons` `:682-691`: YOLO + OSNet + face) on every
uncached request — ~0.2–2.3 s warm, ~100 s cold with model load (the directive's figures;
`docs/state.md:295` records the same 0.2–2.3 s budget).  The table+ball half alone
measured **43–128 ms, median 81 ms** per frame on 8 vod30 frames today (CPU, standalone
script, not through the server); the rest is person/identity and decode.

### 6.2 Table

```sql
CREATE TABLE frame_detections (
    dataset          text    NOT NULL,
    frame_index      integer NOT NULL CHECK (frame_index >= 0),
    detector         text    NOT NULL CHECK (detector IN ('table','balls','persons')),
    detector_version text    NOT NULL,   -- e.g. 'table@<git sha>+prior:<anchors artifact id>'
    payload          jsonb   NOT NULL,   -- exactly the slice /api/unified returns for it
    computed_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset, frame_index, detector, detector_version)
);
CREATE TABLE detector_versions (         -- which version the server serves
    dataset text NOT NULL, detector text NOT NULL, detector_version text NOT NULL,
    frames_expected integer NOT NULL, frames_done integer NOT NULL DEFAULT 0,
    is_current boolean NOT NULL DEFAULT false,
    notes jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (dataset, detector, detector_version)
);
CREATE UNIQUE INDEX one_current_version ON detector_versions (dataset, detector) WHERE is_current;
```

* **Key order is measured, not guessed.**  With the key `(dataset, detector,
  detector_version, frame_index)` a per-frame lookup of all detectors took **17.4 ms** (the
  index cannot seek past the leading `detector`; PostgreSQL 17 has no skip scan).  With
  `(dataset, frame_index, detector, detector_version)` it is **0.009 ms** (Index Scan), and a
  300-frame range for one detector **0.079 ms** — the Vision tab's two access patterns
  (one frame; scrub a window).
* **`detector_version` includes the inputs**, not only the code: the table detector's output
  depends on the saved pocket anchors (`app_prior_for`), so a changed anchor set is a new
  version, and the server never serves an overlay computed against old geometry.
* **Identity is not frozen into the precompute.**  `persons` rows hold boxes, `track_id`,
  `cluster_id` and face-quality fields; `player_id` is joined at request time from
  `identity_clusters`, so binding a player does not invalidate 54 k rows.
* **Serving rule**: `/api/unified` returns the precomputed slice when the current version
  has the frame, and falls back to today's live computation (and says so, e.g.
  `"source": "live"`) when it does not.  The GET still never writes.

### 6.3 Size for `vod30`

`vod30` = **54,206** frames by the container index at 30.0003 fps, 1280×720 (the
directive's 54,202 is within the decoder's end-of-stream slack; the batch job records the
frames it actually decoded in `detector_versions.frames_expected`).

Measured by loading synthetic rows shaped like the real payloads (8 sampled vod30 frames:
table+balls payload median 135 B, max 426 B; 0–7 balls) into a scratch schema on the
`pool-postgres` instance, then dropping it:

| Scenario (3 detectors × 54,202 frames = 162,606 rows) | JSON text | heap | index | total | per frame |
|---|---|---|---|---|---|
| typical (measured ball counts, 2 persons) | 20.8 MB | 51–56 MB | 15 MB | **66–70 MB** | ~1.3 kB |
| heavy (16 balls, 4 persons on every frame) | 65.9 MB | 148 MB | 15 MB | **163 MB** | ~3.0 kB |

So one detector version of `vod30` costs 70–160 MB; keeping three versions side by side is
< 0.5 GB on a disk with 501 GB free.  Batch cost: the offline dense pass already runs
table + person boxes + balls at **27 frames/s** (`out/dense-events/segment-1350-1650.gate2.json`,
`cost.frames_per_s` 27.24, ball stage every 2nd frame) → ~33 min for the table and ball
detectors over all of vod30 on this host.  The `persons` detector also needs the OSNet and
face embeddings per box, which that pass does not run; its cost is not measured here and
decides whether `persons` is precomputed for every frame or at a cadence.  The job writes
with `COPY` in 1,000-frame batches and is resumable (`frames_done`, idempotent
`INSERT … ON CONFLICT DO NOTHING`).

## 7. Storage layer

### 7.1 The `Store` interface

One module, `src/store.py`, with a `Store` protocol and two implementations:

```python
class Store(Protocol):
    # operations (§2)
    def ops_get(self) -> dict: ...                              # the document, as today
    def ops_post(self, payload: dict) -> dict: ...              # ConflictError on stale revision
    def enroll_player(self, player: dict, context: dict, faces: list[dict]) -> dict: ...
    # identity (§3)
    def identity_load(self) -> dict: ...; def identity_save(self, clusters: dict, dirty: set[int]) -> None: ...
    def faces_load(self) -> dict: ...;    def faces_append(self, player_id: str, rows: list[dict]) -> None: ...
    def seeds_get(self, dataset: str) -> dict: ...; def seed_put(self, dataset, key, record | None) -> dict: ...
    # operator records (§4)
    def verdicts_get(self, dataset) -> dict: ...; def verdict_put(self, dataset, event_id, record) -> dict: ...
    def labels_get(self, crop_set) -> dict: ...;  def label_put(self, crop_set, crop_key, label | None) -> None: ...
    def correction_get(self, dataset, frame) -> dict | None: ...; def correction_put(...) -> None: ...
    def anchors_get(self, dataset) -> dict: ...;  def anchors_put(self, dataset, t_key, pts) -> None: ...
    # precomputed (§5, §6) — read-only for the server
    def artifact(self, kind, dataset, key='') -> dict | None: ...
    def queue(self, dataset) -> list[dict]: ...; def queue_window(self, dataset, t0, t1) -> list[dict]: ...
    def tracklets(self, dataset) -> dict: ...
    def frame_detections(self, dataset, frame_index) -> dict | None: ...

def open_store(root) -> Store:
    return PostgresStore() if os.environ.get("POOL_DATABASE_URL") else JsonStore(root)
```

* **`JsonStore` is the default** and is today's code moved behind the interface — the same
  paths, the same `atomic_save`, the same `Operations` class.  No test changes: the ~935
  existing tests (944 run on `d067cb7`, 8 skipped) construct backends on temp roots
  without the variable and keep exercising JSON.
* **`PostgresStore`** uses `src/db.py` (one short-lived connection per call, or a small
  pool later); every mutating method is one transaction.
* **One contract test suite, two runs**: `tests/test_store_contract.py` runs the same cases
  against `JsonStore(tmpdir)` always and against `PostgresStore` (scratch schema, as in
  `tests/test_db.py`) when `POOL_DATABASE_URL` is set.
* **Callers change once each**: `Backend.__init__` gets `self.store = open_store(root)`, and
  the `load(...)`/`atomic_save(...)` call sites listed in §2–§5 go through it.
  `Operations`, `IdentityIndex` and the face functions take the store instead of a path.
  Batch tools keep writing files; the import (§7.3) moves them in.

### 7.2 The read-only contract (a GET never writes)

Both implementations must hold it, and it is tested, not assumed:

* `JsonStore`: the existing md5/`file_stamp` tests stay
  (`tests/test_unified_server.py:791`, `docs/face-identification-assessment.md:159`).
* `PostgresStore`: every GET handler runs in a **`READ ONLY` transaction**
  (`SET TRANSACTION READ ONLY`); a write attempt raises instead of committing.  The contract
  suite also snapshots `pg_stat_user_tables.n_tup_ins/upd/del` around a full GET sweep and
  asserts zero change.
* **Known exception to resolve first** (§3.1): a face match inside `GET /api/unified` /
  `GET /api/identity/frame` calls `bind_face`, which saves.  Under the read-only transaction
  that would fail.  Proposal: the GET returns the proposed bind (`bind` event, as today) and
  the save is queued to a separate write (`POST /api/identity/bind` issued by the page, or a
  background writer outside the request) — the same "the write belongs to the binding"
  principle the 2026-09-23 fix applied to observation.  This needs the owner's decision
  because it changes when a bind becomes durable.

### 7.3 Import (files → Postgres), idempotent and verified

`python -m src.store import [--dry-run] [--only operations,identity,…]`:

1. Records the md5 of every source file, **opens them read-only**, and never writes under
   `out/` (the files are the backup and stay the fallback).
2. Loads each data set in its own transaction with `INSERT … ON CONFLICT (pk) DO UPDATE`
   (user data) or "insert a new artifact version only if `source_md5` differs"
   (precomputed).  Running it twice changes nothing the second time (reported as
   `unchanged`).
3. **Operations import refuses a non-empty database whose revision differs from the file's**
   unless `--replace` is given: the database may already be the live store.
4. **Verification per data set**: row counts equal the file's record counts, and a
   **round trip per record** — `PostgresStore` renders each record back to its JSON shape and
   it must equal the file's record exactly (`==` on parsed JSON; embeddings after the same
   4-dp rounding).  For operations the whole reassembled document is compared, including key
   order of arrays.  Any mismatch aborts that data set's transaction and prints the first
   differing path.
5. Prints a report (counts, md5 before/after — which must be identical) and exits non-zero
   on any mismatch.

### 7.4 Export (Postgres → files)

`python -m src.store export --to <dir>` writes every data set back in the exact file
format (`json.dump(indent=2)`, trailing newline, where the writer used it).  Uses: the
offline tools that read files (`src/train_ball_id.py`, `src/eval_*`), and **rollback after
the database has taken writes** (§7.6).

### 7.5 Cutover

1. `python -m src.store import` → verified, report archived.
2. `pg_dump` (runbook) → first backup.
3. Edit `~/.config/systemd/user/pool-workbench.service`:
   ```ini
   [Unit]
   After=network.target pool-postgres.service
   Requires=pool-postgres.service
   [Service]
   EnvironmentFile=%h/.config/pool/postgres.env
   ```
4. `systemctl --user daemon-reload && systemctl --user restart pool-workbench`.
5. Check: `GET /api/operations` revision equals the file's; one harmless write (a note
   add + delete, or a verdict re-save) lands in the database and **not** in the file.

### 7.6 Rollback

* **Before any write through Postgres**: remove the `EnvironmentFile=` line (and the
  `Requires=`), `daemon-reload`, restart.  The server is back on the untouched files.
* **After writes through Postgres**: first `python -m src.store export --to out/` (with a
  copy of the current `out/` JSON files taken beforehand), then the same unit edit and
  restart.  Without the export, writes made while on Postgres are not in the files.

## 8. Implementation steps (each separately committable and reviewable)

| # | Step | Touches | Done when |
|---|---|---|---|
| 1 | `JsonStore` + `Store` protocol, today's code moved behind it; no behaviour change | `src/store.py`, `annotator/operations.py`, `unified_server.py` call sites | full suite green, md5 of production files unchanged by a GET sweep |
| 2 | Fix §2.4 + §3.3 in `JsonStore` (enrolment as one store operation; gallery merge + invalidation) | `src/store.py`, `enroll_from_tracklet.py`, `unified_server.py:521-540`, `person_pipeline.py` | new tests: a mutation between preview and confirm survives; a second enrolment keeps the first player's faces |
| 3 | Migration `0002_user_data.sql` (§2.2, §3, §4 tables) | `db/migrations/` | `python -m src.db` applies it; re-run is a no-op |
| 4 | `PostgresStore` for user data + contract suite | `src/store.py`, `tests/test_store_contract.py` | contract suite passes on both backends |
| 5 | Import/export for user data with verification | `src/store.py` | import twice = no change; round trip exact on the production files (copied) |
| 6 | Resolve the GET-bind exception (§7.2) — owner decision first | `unified_server.py`, `person_pipeline.py` | read-only transaction on every GET passes the sweep |
| 7 | **Cutover of user data** (§7.5) — owner go-ahead | unit file only | checks in §7.5.5 pass |
| 8 | Migration `0003_artifacts.sql` (§5) + import of precomputed artifacts; server reads them via the store | `db/migrations/`, `src/store.py`, `unified_server.py` | queue/report/calibration/tracklets served from Postgres; batch tools still write files and are imported |
| 9 | Batch tools write through the store (`dense_queue.py` first: queue + report + ledger in one transaction) | `src/dense_queue.py`, … | the two-file non-atomic write is gone |
| 10 | Migration `0004_frame_detections.sql` + batch job `src/precompute_frames.py` (resumable, `COPY`) | new files | vod30 current version complete; `/api/unified` serves it with `live` fallback |

Steps 1–2 are useful even if the database is never cut over; 3–5 can be reviewed without
touching production; 7 is the only step that changes the running service.

## 9. Not in scope / explicitly left on disk

* Media (videos, frames, crops, evidence images, clip cache) and model weights.
* Offline evaluation artifacts and logs (`out/dense-events/`, `out/*eval*`, `*.log`) — they
  are inputs/outputs of batch tools nobody serves; importing them adds nothing.
* The legacy single-purpose servers (`annotator/server.py`, `src/pid_seed_ui.py`) keep
  their file I/O; they are not part of the workbench service.  They must not be run against
  the same `out/` after cutover (they would write files the service no longer reads).
* `pgvector`, replication, remote access, connection pooling — not needed at this size.
