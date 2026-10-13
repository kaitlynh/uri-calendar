"""Ingest scraped events from events.json into the PostgreSQL database.

This script is the bridge between the scraping pipeline (which produces a
flat JSON file) and the live database that the API serves from.  It runs
as the "ingest" step in the GitHub Actions workflow.

Key design decisions:
  - Sources are upserted by source_name (bare domain), so the scraper
    config in sources.json is the single source of truth for metadata.
  - Events are deduplicated on (normalized title, date, time).  Titles are
    normalized (lowercase, punctuation stripped, words sorted) so that
    "Musikschule Uri – Vortragsübung" matches "Vortragsübung Musikschule Uri".
    When a duplicate is found, the existing row is updated only if the
    incoming data is *better*: higher-priority source, more recent scrape,
    or fewer nulls.
  - Each event is wrapped in a SAVEPOINT so one bad record doesn't abort
    the entire batch.
  - The batch is one transaction, committed at the end.  If the server
    closes the connection mid-way (seen twice, both times in the early
    morning window where the server runs its package updates), nothing has
    been committed, so the script reconnects and runs the whole batch once
    more.  Every statement is an upsert, so running it twice is harmless.
"""

import json
import os
import re
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# ── Database ────────────────────────────────────────────────────────────


RECONNECT_TRIES = 6
RECONNECT_DELAY = 10  # seconds; a PostgreSQL restart is over well within a minute


class ConnectionLost(Exception):
    """The database connection died mid-batch."""

    def __init__(self, inserted: int, title, cause: Exception):
        self.inserted = inserted
        self.title = title
        self.cause = cause
        super().__init__(f"Database connection lost after {inserted} events (at '{title}'): {cause}")


def get_db_connection():
    """Connect using DB_CONNECTION_STRING, falling back to individual vars."""
    dsn = os.getenv("DB_CONNECTION_STRING")
    if dsn:
        conn = psycopg2.connect(dsn)
    else:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
        )
    print("Connected to DB successfully.")
    return conn


def reconnect():
    """Retry get_db_connection for up to a minute, then give up loudly."""
    for attempt in range(1, RECONNECT_TRIES + 1):
        try:
            return get_db_connection()
        except psycopg2.OperationalError as e:
            if attempt == RECONNECT_TRIES:
                raise RuntimeError(
                    f"Could not reconnect to the database after {RECONNECT_TRIES} tries: {e}"
                ) from e
            print(f"Reconnect attempt {attempt} failed ({e}); retrying in {RECONNECT_DELAY}s")
            time.sleep(RECONNECT_DELAY)


# ── Title normalization ────────────────────────────────────────────────


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, sort words — for dedup comparison only."""
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    words = sorted(t.split())
    return " ".join(words)


# ── Ingestion ───────────────────────────────────────────────────────────


def ingest_events(json_path=None):
    """Read events/events.json and upsert every event into the database."""
    if json_path is None:
        json_path = Path(__file__).parent.parent / "events" / "events.json"

    with open(json_path, "r") as f:
        events = json.load(f)

    if not isinstance(events, list):
        raise ValueError("Expected a JSON array of event objects.")

    conn = get_db_connection()
    try:
        inserted, skipped = upsert_all(conn, events)
    except ConnectionLost as lost:
        # Nothing is committed until the end, so the batch starts over.
        print(f"{lost}. Reconnecting and running the batch again.")
        try:
            conn.close()
        except Exception:
            pass
        conn = reconnect()
        try:
            inserted, skipped = upsert_all(conn, events)
        except ConnectionLost as again:
            raise RuntimeError(
                f"Database connection lost twice; giving up. "
                f"First: {lost.cause}. Second: {again.cause}"
            ) from again

    conn.commit()
    conn.close()

    print(f"Done. Inserted/updated: {inserted}, Skipped: {skipped}")


def upsert_all(conn, events) -> tuple[int, int]:
    """Upsert every event on conn.  Raises ConnectionLost if conn dies."""
    cur = conn.cursor()

    inserted = 0
    skipped = 0

    for event in events:
        try:
            cur.execute("SAVEPOINT ev")

            source_name = event.get("source_name")
            base_url = event.get("base_url")
            source_url = event.get("source_url")
            priority = event.get("priority") or 67  # 67 = safe fallback (see schema.sql)

            # 1. Upsert source — source_name is the natural key
            cur.execute(
                """
                INSERT INTO sources (source_name, base_url, priority)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_name) DO UPDATE SET
                    base_url = EXCLUDED.base_url,
                    priority = EXCLUDED.priority
                RETURNING source_id
                """,
                (source_name, base_url, priority),
            )
            source_id = cur.fetchone()[0]

            # 2. Upsert event — the ON CONFLICT … DO UPDATE WHERE clause
            #    ensures we only overwrite an existing row when the new data
            #    is actually *better*, not just newer.  "Better" means:
            #      a) from a higher-priority source (lower number wins), OR
            #      b) a more recent scrape (extracted_at), OR
            #      c) the new row has fewer NULLs (more complete data).
            title = event.get("event_title")
            title_norm = normalize_title(title) if title else None

            cur.execute(
                """
                INSERT INTO events (
                    source_id, source_url, event_title, title_normalized,
                    start_date, start_time, end_datetime,
                    location, description, extracted_at,
                    ai_flag, ai_flag_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (title_normalized, start_date, COALESCE(start_time, '00:00:00'))
                DO UPDATE SET
                    source_id    = EXCLUDED.source_id,
                    event_title  = EXCLUDED.event_title,
                    title_normalized = EXCLUDED.title_normalized,
                    start_date   = EXCLUDED.start_date,
                    start_time   = EXCLUDED.start_time,
                    end_datetime = EXCLUDED.end_datetime,
                    location     = EXCLUDED.location,
                    description  = EXCLUDED.description,
                    extracted_at = EXCLUDED.extracted_at,
                    source_url   = EXCLUDED.source_url,
                    ai_flag      = EXCLUDED.ai_flag,
                    ai_flag_at   = EXCLUDED.ai_flag_at
                WHERE
                    -- (a) Incoming source has higher priority (lower number)
                    (SELECT s.priority FROM sources s WHERE s.source_id = EXCLUDED.source_id)
                        < (SELECT s.priority FROM sources s WHERE s.source_id = events.source_id)
                    -- (b) More recent extraction (only if priority is equal or better)
                    OR (
                        EXCLUDED.extracted_at > events.extracted_at
                        AND (SELECT s.priority FROM sources s WHERE s.source_id = EXCLUDED.source_id)
                            <= (SELECT s.priority FROM sources s WHERE s.source_id = events.source_id)
                    )
                    -- (c) Incoming row has more non-null fields
                    OR (
                        (EXCLUDED.event_title IS NOT NULL)::int
                        + (EXCLUDED.start_time IS NOT NULL)::int
                        + (EXCLUDED.end_datetime IS NOT NULL)::int
                        + (EXCLUDED.location IS NOT NULL)::int
                        + (EXCLUDED.description IS NOT NULL)::int
                    ) > (
                        (events.event_title IS NOT NULL)::int
                        + (events.start_time IS NOT NULL)::int
                        + (events.end_datetime IS NOT NULL)::int
                        + (events.location IS NOT NULL)::int
                        + (events.description IS NOT NULL)::int
                    )
                    -- (d) Same priority & completeness — prefer more content
                    OR (
                        (SELECT s.priority FROM sources s WHERE s.source_id = EXCLUDED.source_id)
                            = (SELECT s.priority FROM sources s WHERE s.source_id = events.source_id)
                        AND COALESCE(length(EXCLUDED.description), 0)
                            + COALESCE(length(EXCLUDED.location), 0)
                            > COALESCE(length(events.description), 0)
                            + COALESCE(length(events.location), 0)
                    )
                """,
                (
                    source_id,
                    source_url,
                    title,
                    title_norm,
                    event.get("start_date"),
                    event.get("start_time"),
                    event.get("end_datetime"),
                    event.get("location"),
                    event.get("description"),
                    event.get("extracted_at"),
                    event.get("ai_flag"),
                    event.get("ai_flag_at"),
                ),
            )
            cur.execute("RELEASE SAVEPOINT ev")
            inserted += 1

        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # If the connection itself is gone, every remaining event would
            # fail identically and the savepoint rollback below cannot run
            # on a dead cursor.  Hand the real cause to the caller.  (A
            # cancelled or timed-out statement is also an OperationalError,
            # but leaves the connection open; that one is just skipped.)
            if conn.closed:
                raise ConnectionLost(inserted, event.get("event_title"), e) from e
            print(f"Skipping event '{event.get('event_title')}' due to error: {e}")
            cur.execute("ROLLBACK TO SAVEPOINT ev")
            skipped += 1

        except psycopg2.Error as e:
            print(f"Skipping event '{event.get('event_title')}' due to error: {e}")
            cur.execute("ROLLBACK TO SAVEPOINT ev")
            skipped += 1

    cur.close()
    return inserted, skipped


if __name__ == "__main__":
    ingest_events()
