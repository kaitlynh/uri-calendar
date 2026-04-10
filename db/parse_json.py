import json
import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')


def get_db_connection():
    try:
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
    except psycopg2.OperationalError as e:
        print(f"Connection failed: {e}")
        raise


def ingest_events(json_file: str):
    json_path = Path(__file__).parent.parent / "events" / "events.json"

    with open(json_path, "r") as f:
        events = json.load(f)

    if not isinstance(events, list):
        raise ValueError("Expected a JSON array of event objects.")

    conn = get_db_connection()
    cur = conn.cursor()

    inserted = 0
    skipped = 0

    for event in events:
        try:
            cur.execute("SAVEPOINT ev")

            # Mapping from JSON - Adjust these keys if your JSON uses different names
            base_url = event.get("base_url")
            source_url = event.get("source_url") # The specific URL for this event
            source_name = event.get("source_name")
            priority = event.get("priority") or 67

            # 1. Upsert source (using source_name as the unique identifier)
            cur.execute(
                """
                INSERT INTO sources (source_name, base_url, priority)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_name) DO UPDATE SET
                    base_url = EXCLUDED.base_url,
                    priority = EXCLUDED.priority
                RETURNING source_id
                """,
                (source_name, base_url, priority)
            )
            source_id = cur.fetchone()[0]

            # 2. Extract Date/Time
            start_date = event.get("start_date")
            start_time = event.get("start_time")

            # 3. Insert event (now including source_url)
            cur.execute(
                """
                INSERT INTO events (
                    source_id,
                    source_url,
                    event_title,
                    start_date,
                    start_time,
                    end_datetime,
                    location,
                    description,
                    extracted_at,
                    ai_flag,
                    ai_flag_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_title, start_date, COALESCE(start_time, '00:00:00'))
                DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    event_title = EXCLUDED.event_title,
                    start_date = EXCLUDED.start_date,
                    start_time = EXCLUDED.start_time,
                    end_datetime = EXCLUDED.end_datetime,
                    location = EXCLUDED.location,
                    description = EXCLUDED.description,
                    extracted_at = EXCLUDED.extracted_at,
                    source_url = EXCLUDED.source_url,
                    ai_flag = EXCLUDED.ai_flag,
                    ai_flag_at = EXCLUDED.ai_flag_at
                WHERE (
                    -- 1. Lower priority (Note: We join the priority from the sources table)
                    (SELECT s.priority FROM sources s WHERE s.source_id = EXCLUDED.source_id) < 
                    (SELECT s.priority FROM sources s WHERE s.source_id = events.source_id)
                ) OR (
                    -- 2. More recent extracted_at
                    EXCLUDED.extracted_at > events.extracted_at
                ) OR (
                    -- 3. The new data has fewer NULLs than the old data
                    (
                        (EXCLUDED.event_title IS NOT NULL)::int + 
                        (EXCLUDED.start_time IS NOT NULL)::int + 
                        (EXCLUDED.end_datetime IS NOT NULL)::int + 
                        (EXCLUDED.location IS NOT NULL)::int + 
                        (EXCLUDED.description IS NOT NULL)::int
                    ) > (
                        (events.event_title IS NOT NULL)::int + 
                        (events.start_time IS NOT NULL)::int + 
                        (events.end_datetime IS NOT NULL)::int + 
                        (events.location IS NOT NULL)::int + 
                        (events.description IS NOT NULL)::int
                    )
                );
                """,
                (
                    source_id,
                    source_url, # Added this
                    event.get("event_title"),
                    start_date,
                    start_time,
                    event.get("end_datetime"),
                    event.get("location"),
                    event.get("description"),
                    event.get("extracted_at"),
                    event.get("ai_flag"),
                    event.get("ai_flag_at"),
                )
            )
            cur.execute("RELEASE SAVEPOINT ev")
            inserted += 1

        except psycopg2.Error as e:
            print(f"Skipping event '{event.get('event_title')}' due to error: {e}")
            cur.execute("ROLLBACK TO SAVEPOINT ev")
            skipped += 1
            continue

    conn.commit()
    cur.close()
    conn.close()

    print(f"Done. Inserted: {inserted}, Skipped: {skipped}")

if __name__ == "__main__":
    ingest_events("data.json")