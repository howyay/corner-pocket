-- Write fingerprint of every user-data table (docs/postgres.md "Proving a read wrote nothing").
--
--   podman exec -i pool-postgres psql -U pool -d pool -tA -F' ' < scripts/pool-write-fingerprint.sql
--
-- One line per table: name, row count, md5 over every row's xmin and content. xmin is
-- the id of the transaction that last wrote the row, so ANY write changes the line -
-- an INSERT, a DELETE, and even an UPDATE that rewrites identical values - while any
-- number of reads leave it byte-identical. Run it before and after a read-only smoke
-- and compare with diff: no difference means nothing was written.
SELECT 'ops_meta' AS tbl, count(*) AS n, md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) AS fp FROM ops_meta x
UNION ALL SELECT 'players', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM players x
UNION ALL SELECT 'tournaments', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM tournaments x
UNION ALL SELECT 'entrants', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM entrants x
UNION ALL SELECT 'entrant_members', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM entrant_members x
UNION ALL SELECT 'matches', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM matches x
UNION ALL SELECT 'notes', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM notes x
UNION ALL SELECT 'sources', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM sources x
UNION ALL SELECT 'ops_events', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM ops_events x
UNION ALL SELECT 'identity_clusters', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM identity_clusters x
UNION ALL SELECT 'identity_face_samples', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM identity_face_samples x
UNION ALL SELECT 'face_embeddings', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM face_embeddings x
UNION ALL SELECT 'track_seeds', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM track_seeds x
UNION ALL SELECT 'event_verdicts', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM event_verdicts x
UNION ALL SELECT 'ball_labels', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM ball_labels x
UNION ALL SELECT 'frame_corrections', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM frame_corrections x
UNION ALL SELECT 'pocket_anchors', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM pocket_anchors x
UNION ALL SELECT 'json_documents', count(*), md5(coalesce(string_agg(xmin::text || ':' || x::text, ',' ORDER BY x::text), '')) FROM json_documents x
ORDER BY 1;
