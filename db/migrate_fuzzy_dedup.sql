-- Migration: fuzzy title dedup
-- Adds title_normalized column and replaces the unique index so that
-- "Musikschule Uri – Vortragsübung" and "Vortragsübung Musikschule Uri"
-- are recognized as the same event.

-- 1. Add the column
ALTER TABLE events ADD COLUMN IF NOT EXISTS title_normalized text;

-- 2. Backfill existing rows: lowercase, strip non-word/non-space, sort words
UPDATE events
SET title_normalized = (
    SELECT string_agg(w, ' ' ORDER BY w)
    FROM unnest(
        regexp_split_to_array(
            regexp_replace(lower(event_title), '[^\w\s]', ' ', 'g'),
            '\s+'
        )
    ) AS w
    WHERE w <> ''
)
WHERE title_normalized IS NULL;

-- 3. Drop the old index and create the new one
DROP INDEX IF EXISTS unique_title_date_time;
CREATE UNIQUE INDEX unique_title_date_time
    ON events (title_normalized, start_date, COALESCE(start_time, '00:00:00'));
