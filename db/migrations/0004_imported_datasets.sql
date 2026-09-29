-- 0004: operator records for imported VODs (src/datasets.py).
--
-- The VOD selector added imported Twitch broadcasts next to the two built-in
-- recordings: ids "tw-<vod>" or "tw-<vod>-<start>-<end>", data under out/vods/<id>/.
-- 0002 allowed only 'vod30' and 'highlight' in event_verdicts and frame_corrections,
-- so a correction or verdict on an imported VOD was refused under Postgres while
-- the JSON store accepted it.
--
-- The dataset columns now check the id's FORMAT, exactly the rule of
-- src.datasets.parse_imported_id (canonical: no leading zeros, a VOD id of at most
-- 12 digits and not 0, whole-second start < end, at most 64 characters, no trailing
-- newline - measured equal on 25 edge cases). Whether the VOD is currently imported
-- is the store's check (src.datasets.lookup, which reads out/vods/index.json): a
-- deleted VOD's records stay, as its files stay under out/vods/<id>/.
--
-- Every dataset column, with what it holds:
--   event_verdicts.dataset     verdicts        - was IN ('vod30','highlight'); now the format
--   frame_corrections.dataset  corrections     - was IN ('vod30','highlight'); now the format
--   pocket_anchors.dataset     pocket anchors  - had no check; now the format (the server
--                                                still serves anchors for vod30 only)
--   track_seeds.dataset        seeds           - had no check; now the format (seeds exist
--                                                for vod30 only; the store refuses others)
-- json_documents.path already accepts out/vods/<id>/... (its rule is out/% and no '..').
CREATE FUNCTION dataset_id_ok(d text) RETURNS boolean
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT d IN ('vod30', 'highlight')
        OR (length(d) <= 64
            AND d ~ '^tw-[1-9][0-9]{0,11}(-(0|[1-9][0-9]*)-(0|[1-9][0-9]*))?$'
            AND (d !~ '^tw-[0-9]+-'
                 OR split_part(d, '-', 3)::numeric < split_part(d, '-', 4)::numeric))
$$;

ALTER TABLE event_verdicts    DROP CONSTRAINT event_verdicts_dataset_check;
ALTER TABLE frame_corrections DROP CONSTRAINT frame_corrections_dataset_check;
ALTER TABLE event_verdicts    ADD CONSTRAINT event_verdicts_dataset_check    CHECK (dataset_id_ok(dataset));
ALTER TABLE frame_corrections ADD CONSTRAINT frame_corrections_dataset_check CHECK (dataset_id_ok(dataset));
ALTER TABLE pocket_anchors    ADD CONSTRAINT pocket_anchors_dataset_check    CHECK (dataset_id_ok(dataset));
ALTER TABLE track_seeds       ADD CONSTRAINT track_seeds_dataset_check       CHECK (dataset_id_ok(dataset));
