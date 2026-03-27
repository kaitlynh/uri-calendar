import json
import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

# Load .env from same directory as this script
load_dotenv(dotenv_path=Path(__file__).parent / '.env')


def get_db_connection():
    try:
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


def parse_start_datetime(value):
    """Split ISO8601 datetime string into (date, time) or (None, None)."""
    if not value:
        return None, None
    try:
        dt = datetime.fromisoformat(value)
        return dt.date(), dt.time()
    except ValueError:
        print(f"Could not parse start_datetime: {value}")
        return None, None


def ingest_events(json_file: str):
    json_path = Path(__file__).parent / json_file

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
            # Mapping from JSON - Adjust these keys if your JSON uses different names
            base_url = event.get("base_url") 
            source_url = event.get("source_url") # The specific URL for this event
            source_name = event.get("source_name")

            # 1. Upsert source (using base_url as the unique identifier)
            cur.execute(
                """
                INSERT INTO sources (source_name, base_url)
                VALUES (%s, %s)
                ON CONFLICT (base_url) DO UPDATE SET source_name = EXCLUDED.source_name
                RETURNING source_id
                """,
                (source_name, base_url)
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
                    extracted_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                )
            )
            inserted += 1

        except psycopg2.Error as e:
            print(f"Skipping event '{event.get('event_title')}' due to error: {e}")
            conn.rollback() # Important to rollback the transaction on error
            skipped += 1
            continue

    conn.commit()
    cur.close()
    conn.close()

    print(f"Done. Inserted: {inserted}, Skipped: {skipped}")

if __name__ == "__main__":
    ingest_events("data.json")