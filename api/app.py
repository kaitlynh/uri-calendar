"""
Events API for the Uri Calendar.

Endpoints:

    GET /api/events?date=2026-03-28   — events for a given date
    GET /api/sources                  — list all event sources

See template_data.json for the event response shape.
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
    """Convert a DB row to JSON matching template_data.json.

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
    }


@app.route("/api/events")
def get_events():
    """Fetch all events for a given date.

    Query params:
        date (required): YYYY-MM-DD

    Returns:
        200: JSON array of events (may be empty)
        400: missing or invalid date
    """
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Missing required parameter: date (YYYY-MM-DD)"}), 400

    try:
        query_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Join with sources to include source_name/base_url in the response.
            # NULLS FIRST so all-day events appear before timed events.
            cur.execute(
                """
                SELECT e.event_id, e.event_title, e.start_date, e.start_time,
                       e.end_datetime, e.location, e.description, e.extracted_at,
                       e.source_url,
                       s.source_name, s.base_url
                FROM events e
                JOIN sources s ON e.source_id = s.source_id
                WHERE e.start_date = %s
                ORDER BY e.start_time ASC NULLS FIRST
                """,
                (query_date,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return jsonify([serialize_event(r) for r in rows])


@app.route("/api/sources")
def get_sources():
    """List all event sources (websites we scrape from)."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT source_id, source_name, base_url, created_at
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
