-- 0003: the user-data JSON files as documents, so the export is byte-exact.
--
-- Measured while building the export (design 7.4): the 0002 rows hold every value
-- but not the files' layout, so state.json could not be rebuilt byte for byte.
--   * jsonb keeps object keys in its own order: settings came back lampGlow-first
--     instead of shotClock-first;
--   * a record's key order is the order the application added its keys, and that
--     differs by code path (player_save gives {id, joinedAt, rating, status, name},
--     an enrolment {joinedAt, rating, status, id, name}; a merged verdict keeps its
--     first keys first), while new tournament keys (pool, pairing, revival,
--     revival_draws, hidden) arrive with every feature.
-- A json (not jsonb) value is stored as the exact text it was given - key order,
-- number spelling, whitespace, the trailing newline (measured) - so a file written
-- here comes back byte for byte.
--
-- Each operations / operator-record file is therefore one document: the source of
-- truth for reads and for the export, stored in the writer's exact format (indent,
-- trailing newline). The 0002 rows become a projection rewritten from it in the
-- same transaction, so their constraints and foreign keys still check every write.
-- The identity index and the face store stay rows only: their writers emit a fixed
-- key order, and the biometrics keep their own table, foreign key and per-person
-- delete (design 3).
CREATE TABLE json_documents (
    path       text PRIMARY KEY CHECK (path LIKE 'out/%' AND path NOT LIKE '%..%'),
    document   json NOT NULL,        -- the file's text exactly as its writer formats it
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- clusters.json written before the face-samples change (production today) has no
-- "face_samples" key at all; the current IdentityIndex.save always writes one. The
-- flag keeps "absent" and "[]" apart so an older file exports byte for byte.
ALTER TABLE identity_clusters ADD COLUMN has_face_samples boolean NOT NULL DEFAULT true;
