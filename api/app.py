"""
Events API for the Uri Calendar.

Endpoints:

    GET /api/events?date=2026-03-28   — events for a given date
    GET /api/sources                  — list all event sources

See docs/event-schema.json for the event response shape.
Events without a start_time (all-day events) appear first.

Setup:
    pip install -r requirements.txt
    python app.py
"""

import os
from datetime import date

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

app = Flask(__name__)


def get_db():
    """Connect using the DB_CONNECTION_STRING env var (see .env)."""
    return psycopg2.connect(os.environ["DB_CONNECTION_STRING"])


def serialize_event(row):
    """Convert a DB row to JSON matching docs/event-schema.json.

    Dates become "YYYY-MM-DD", times become "HH:MM:SS", and nulls stay null
    (e.g. start_time is null for all-day events).
    """
    return {
        "event_id": str(row["event_id"]),
        "source_name": row["source_name"],
        "source_url": row["source_url"],
        "base_url": row["base_url"],
        "event_title": row["event_title"],
        "start_date": row["start_date"].isoformat() if row["start_date"] else None,
        "start_time": row["start_time"].strftime("%H:%M:%S") if row["start_time"] else None,
        "end_datetime": row["end_datetime"].isoformat() if row["end_datetime"] else None,
        "location": row["location"],
        "description": row["description"],
        "extracted_at": row["extracted_at"].isoformat() if row["extracted_at"] else None,
        "ai_flag": row["ai_flag"],
        "display_name": row.get("display_name"),
        "icon_filename": row.get("icon_filename"),
    }


@app.route("/api/events")
def get_events():
    """Fetch events for a single date or a date range.

    Query params (option A — single date):
        date (required): YYYY-MM-DD

    Query params (option B — date range):
        start_date (required): YYYY-MM-DD
        end_date   (required): YYYY-MM-DD

    Returns:
        200: JSON array of events (may be empty)
        400: missing or invalid parameters
    """
    date_str = request.args.get("date")
    start_str = request.args.get("start_date")
    end_str = request.args.get("end_date")

    if date_str:
        # Single date mode (backwards compatible)
        try:
            query_date = date.fromisoformat(date_str)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
        start_date_val = query_date
        end_date_val = query_date
    elif start_str and end_str:
        # Date range mode
        try:
            start_date_val = date.fromisoformat(start_str)
            end_date_val = date.fromisoformat(end_str)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    else:
        return jsonify({"error": "Provide either 'date' or both 'start_date' and 'end_date'"}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT e.event_id, e.event_title, e.start_date, e.start_time,
                       e.end_datetime, e.location, e.description, e.extracted_at,
                       e.source_url, e.ai_flag,
                       s.source_name, s.base_url, s.display_name, s.icon_filename, s.category
                FROM events e
                JOIN sources s ON e.source_id = s.source_id
                WHERE e.start_date BETWEEN %s AND %s
                ORDER BY e.start_date ASC, e.start_time ASC NULLS FIRST
                """,
                (start_date_val, end_date_val),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return jsonify([serialize_event(r) for r in rows])


@app.route("/api/events/search")
def search_events():
    """Search future events by title, description, or location.

    Query params:
        q (required): search term (min 2 chars)

    Returns events in two groups via match_type:
        "title"  — query matched in event_title
        "detail" — query matched in description or location only
    Sorted by start_date ASC within each group, limited to 50 results.
    """
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"error": "Search query must be at least 2 characters."}), 400

    pattern = f"%{q}%"
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT e.event_id, e.event_title, e.start_date, e.start_time,
                       e.end_datetime, e.location, e.description, e.extracted_at,
                       e.source_url, e.ai_flag,
                       s.source_name, s.base_url, s.display_name, s.icon_filename, s.category,
                       CASE WHEN e.event_title ILIKE %s THEN 'title' ELSE 'detail' END AS match_type
                FROM events e
                JOIN sources s ON e.source_id = s.source_id
                WHERE e.start_date >= CURRENT_DATE
                  AND (e.event_title ILIKE %s
                       OR e.description ILIKE %s
                       OR e.location ILIKE %s)
                ORDER BY
                    CASE WHEN e.event_title ILIKE %s THEN 0 ELSE 1 END,
                    e.start_date ASC,
                    e.start_time ASC NULLS FIRST
                LIMIT 50
                """,
                (pattern, pattern, pattern, pattern, pattern),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    results = []
    for r in rows:
        event = serialize_event(r)
        event["match_type"] = r["match_type"]
        results.append(event)

    return jsonify(results)


@app.route("/api/admin/scraping-status", methods=["GET"])
def get_scraping_status():
    """Per-source scraping stats for the admin dashboard."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT s.source_name, s.base_url,
                       COUNT(e.event_id)        AS event_count,
                       MAX(e.extracted_at)      AS last_extracted_at,
                       MIN(e.start_date)::text  AS earliest_event_date,
                       MAX(e.start_date)::text  AS latest_event_date
                FROM sources s
                LEFT JOIN events e ON e.source_id = s.source_id
                GROUP BY s.source_id, s.source_name, s.base_url
                ORDER BY s.source_name ASC
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return jsonify([
        {
            "source_name": r["source_name"],
            "base_url": r["base_url"],
            "event_count": r["event_count"],
            "last_extracted_at": r["last_extracted_at"].isoformat() if r["last_extracted_at"] else None,
            "earliest_event_date": r["earliest_event_date"],
            "latest_event_date": r["latest_event_date"],
        }
        for r in rows
    ])


@app.route("/api/sources")
def get_sources():
    """List all event sources (websites we scrape from)."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT source_id, source_name, base_url, created_at, display_name, icon_filename, category
                FROM sources
                ORDER BY source_name ASC
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return jsonify([
        {
            "source_id": str(r["source_id"]),
            "source_name": r["source_name"],
            "base_url": r["base_url"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "display_name": r["display_name"],
            "icon_filename": r["icon_filename"],
            "category": r["category"],
        }
        for r in rows
    ])


@app.after_request
def add_cors_headers(response):
    """Allow cross-origin requests so the frontend can call us during dev."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


if __name__ == "__main__":
    app.run(debug=True, port=5000)
