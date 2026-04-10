-- URI Calendar database schema
-- Usage: psql -U uri_calendar -d uri_calendar -f db/schema.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Sources: one row per scraped website
CREATE TABLE IF NOT EXISTS sources (
    source_id    uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    source_name  text UNIQUE,                -- bare domain, e.g. "kbu.ch"
    base_url     text NOT NULL,              -- full URL to events listing page
    priority     integer NOT NULL DEFAULT 67, -- lower = preferred in dedup
    display_name text,                       -- human-friendly name (set manually)
    icon_filename text,                      -- filename in frontend/public/source-icons/ (set manually)
    category     text,                       -- filter group: Gemeinden, Schulen, Organisationen (set manually)
    created_at   timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

-- Events: one row per event showing
CREATE TABLE IF NOT EXISTS events (
    event_id     uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    source_id    uuid NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    source_url   text NOT NULL,              -- direct link to the event page
    event_title  text,
    start_date   date NOT NULL,
    start_time   time without time zone,     -- HH:MM:SS, null for all-day events
    end_datetime timestamp without time zone, -- YYYY-MM-DDTHH:MM:SS, no timezone
    location     text,
    description  text,
    ai_flag      boolean DEFAULT false,
    ai_flag_at   timestamp with time zone,    -- when AI enrichment happened
    extracted_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at   timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

-- Dedup: same title + date + time = same event (NULL time treated as 00:00:00)
CREATE UNIQUE INDEX IF NOT EXISTS unique_title_date_time
    ON events (event_title, start_date, COALESCE(start_time, '00:00:00'));
