"""Scraper for theater-uri.ch — Theater Uri Spielplan.

The Spielplan page embeds JSON-LD (schema.org/Event) in <script type="application/ld+json">
tags. Each event has name, startDate, endDate, description, url, and image.
"""

import json
import logging
import re
import requests
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}


def _parse_datetime(raw: str) -> Optional[datetime]:
    """Parse non-standard ISO datetimes like '2026-4-11T19:30+2:00' or '2026-6-12'."""
    # Normalize: pad month/day, expand short timezone offset
    # e.g. "2026-4-11T19:30+2:00" → "2026-04-11T19:30:00+02:00"
    m = re.match(
        r"(\d{4})-(\d{1,2})-(\d{1,2})"          # date
        r"(?:T(\d{1,2}):(\d{2})(?::(\d{2}))?)?"  # optional time
        r"([+-]\d{1,2}:\d{2})?$",                 # optional tz offset
        raw,
    )
    if not m:
        return None
    year, month, day = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
    hour = (m.group(4) or "00").zfill(2)
    minute = m.group(5) or "00"
    second = m.group(6) or "00"
    tz = m.group(7) or "+00:00"
    # Pad timezone hour: "+2:00" → "+02:00"
    tz = re.sub(r"([+-])(\d):", r"\g<1>0\2:", tz)
    iso = f"{year}-{month}-{day}T{hour}:{minute}:{second}{tz}"
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def fetch_events(**kwargs) -> list[dict]:
    """Fetch events from the Theater Uri Spielplan page via JSON-LD."""
    url = kwargs.get("url", "https://www.theater-uri.ch/spielplan/")
    log.info("fetching %s", url)

    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    events = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle both single objects and arrays
        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") == "Event":
                events.append(item)

    log.info("found %d events", len(events))
    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    title = event.get("name") or ""
    source_url = event.get("url") or ""

    # Parse startDate — site uses non-standard ISO like "2026-4-11T19:30+2:00"
    start_date = None
    start_time = None
    start_raw = event.get("startDate") or ""
    if start_raw:
        dt = _parse_datetime(start_raw)
        if dt:
            start_date = dt.strftime("%Y-%m-%d")
            start_time = dt.strftime("%H:%M:%S")
        else:
            log.warning("unparseable startDate: %s", start_raw)

    # Parse endDate
    end_datetime = None
    end_raw = event.get("endDate") or ""
    if end_raw:
        dt = _parse_datetime(end_raw)
        if dt:
            end_datetime = dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Description — strip HTML
    description = ""
    desc_raw = event.get("description") or ""
    if desc_raw:
        description = _strip_html(desc_raw)

    location = "Theater Uri, Altdorf"

    return {
        "source_url": source_url,
        "event_title": title,
        "start_date": start_date,
        "start_time": start_time,
        "end_datetime": end_datetime,
        "location": location,
        "description": description,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    output_path = os.path.join(os.path.dirname(__file__), "..", "events", "theater_uri_events.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("saved to %s", output_path)
