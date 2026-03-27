import json
import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from same directory as this script
load_dotenv(dotenv_path=Path(__file__).parent / '.env')


def get_db_connection():
    try:
        print("hi3")
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
    # Resolve path relative to this script
    json_path = Path(__file__).parent / json_file
 
    with open(json_path, "r") as f:
        events = json.load(f)
 
    if not isinstance(events, list):
        raise ValueError("Expected a JSON array of event objects.")
 
    conn = get_db_connection()
    cur = conn.cursor()
    
    print("hi2")

    inserted = 0
    skipped = 0
 
    for event in events:
        try:
            source_url = event.get("source_url")
 
            # 1. Upsert source, get back source_id
            cur.execute(
                """
                INSERT INTO sources (base_url)
                VALUES (%s)
                ON CONFLICT (base_url) DO UPDATE SET base_url = EXCLUDED.base_url
                RETURNING source_id
                """,
                (source_url,)
            )
            source_id = cur.fetchone()[0]
 
            # 2. Insert event
            cur.execute(
                """
                INSERT INTO events (
                    source_id,
                    event_title,
                    start_datetime,
                    end_datetime,
                    location,
                    description,
                    category,
                    extracted_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    source_id,
                    event.get("event_title"),
                    event.get("start_datetime"),
                    event.get("end_datetime"),
                    event.get("location"),
                    event.get("description"),
                    event.get("category"),
                    event.get("extracted_at"),
                )
            )
            inserted += 1
        except psycopg2.Error as e:
            print(f"Skipping event due to error: {e}")
            conn.rollback()
            skipped += 1
            continue
 
    conn.commit()
    cur.close()
    conn.close()
 
    print(f"Done. Inserted: {inserted}, Skipped: {skipped}")
 
 
if __name__ == "__main__":
    print("hi")
    ingest_events("data.json")