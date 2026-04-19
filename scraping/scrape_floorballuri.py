"""Scraper for Floorball Uri — unihockey club match schedule.

Parses the meisterschaft page for upcoming game cards with teams,
dates, times, and venues.  Past games are filtered out.
"""

import logging
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from typing import Optional

log = logging.getLogger(__name__)

BASE_URL = "https://www.floorballuri.ch/meisterschaft-2025-26"
SOURCE_NAME = "floorballuri.ch"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}

# DD.MM.YYYY at the start of a <strong> tag
DATE_RE = re.compile(r'^(\d{2})\.(\d{2})\.(\d{4})')
# HH:MM Uhr
TIME_RE = re.compile(r'(\d{1,2}):(\d{2})\s*Uhr')


def _parse_date(text: str) -> Optional[str]:
    m = DATE_RE.match(text.strip())
    if not m:
        return None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def _parse_time(text: str) -> Optional[str]:
    m = TIME_RE.search(text)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}:00"


def _fetch_page(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log.warning("fetch failed %s: %s", url, e)
        return None


def _parse_games(page_html: str, page_url: str) -> list[dict]:
    """Extract upcoming games from a meisterschaft page."""
    soup = BeautifulSoup(page_html, "html.parser")
    today = date.today()
    events = []

    for game in soup.select("div.game"):
        date_el = game.select_one("span.date")
        if not date_el:
            continue

        start_date = _parse_date(date_el.get_text())
        if not start_date:
            continue

        # Skip dates in the past
        try:
            if datetime.strptime(start_date, "%Y-%m-%d").date() < today:
                continue
        except ValueError:
            continue

        # Teams: "Heim – Gast"
        teams_el = game.select_one("div.teams")
        title = teams_el.get_text(" ", strip=True).replace("\xa0", " ") if teams_el else "Floorball Uri"

        # Time
        zeit_el = game.select_one("span.zeit")
        start_time = _parse_time(zeit_el.get_text()) if zeit_el else None

        # Location
        ort_el = game.select_one("span.ort")
        location = ort_el.get_text(strip=True) if ort_el else None

        events.append({
            "title": title,
            "start_date": start_date,
            "start_time": start_time,
            "end_datetime": None,
            "location": location,
            "detail_url": page_url,
        })

    return events


def fetch_events(url: str = f"{BASE_URL}/meisterschaft-2025-26") -> list[dict]:
    log.info("fetching %s", url)
    html = _fetch_page(url)
    if not html:
        return []

    events = _parse_games(html, url)
    log.info("found %d upcoming games", len(events))
    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_name": SOURCE_NAME,
        "base_url": BASE_URL,
        "source_url": event["detail_url"],
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event["start_time"],
        "end_datetime": event["end_datetime"],
        "location": event["location"],
        "description": None,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    raw = fetch_events()
    formatted = [_to_template(e, extracted_at) for e in raw]
    log.info("total events: %d", len(formatted))
    print(json.dumps(formatted, ensure_ascii=False, indent=2))
