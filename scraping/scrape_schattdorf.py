import logging
import re
import requests
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

URL = "https://schattdorf.ch/erleben/veranstaltungen"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

MONTHS_DE = {
    "Januar": 1, "Februar": 2, "März": 3, "April": 4,
    "Mai": 5, "Juni": 6, "Juli": 7, "August": 8,
    "September": 9, "Oktober": 10, "November": 11, "Dezember": 12,
}


def _parse_date(date_str: str) -> Optional[str]:
    """Parse '2. April 2026' into 'YYYY-MM-DD'."""
    try:
        cleaned = date_str.strip()
        match = re.match(r'(\d{1,2})\.\s*(\w+)\s+(\d{4})', cleaned)
        if not match:
            return None
        day = int(match.group(1))
        month = MONTHS_DE.get(match.group(2))
        year = int(match.group(3))
        if not month:
            return None
        return f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        return None


def _parse_time(time_str: str) -> Optional[str]:
    """Parse '17.30 Uhr' or '17.30\xa0Uhr' into 'HH:MM:00'."""
    if not time_str:
        return None
    cleaned = time_str.replace('\xa0', ' ').strip()
    match = re.search(r'(\d{1,2})[.:](\d{2})', cleaned)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}:00"
    return None


def fetch_events() -> list:
    """Fetch all events from schattdorf.ch/erleben/veranstaltungen."""
    log.info("fetching %s", URL)
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s", resp.status_code)
            return []
    except Exception as e:
        log.error("error: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("div.event")
    log.info("found %d events", len(cards))

    events = []
    for card in cards:
        title_el = card.select_one(".event__title h4")
        date_el = card.select_one(".event__date p.text--bold")
        time_els = card.select(".event__date p.text__base:not(.text--bold)")
        location_el = card.select_one(".event__location p")

        title = title_el.get_text(strip=True) if title_el else ""
        date_str = date_el.get_text(strip=True) if date_el else ""
        time_str = time_els[0].get_text(strip=True) if time_els else ""
        location = location_el.get_text(strip=True) if location_el else None

        if not title:
            continue

        events.append({
            "title": title,
            "date": date_str,
            "time": time_str,
            "location": location,
        })

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_url": URL,
        "event_title": event["title"],
        "start_date": _parse_date(event["date"]),
        "start_time": _parse_time(event.get("time", "")),
        "end_datetime": None,
        "location": event["location"],
        "description": None,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    formatted = [_to_template(e, extracted_at) for e in events]
    print(json.dumps(formatted, ensure_ascii=False, indent=2))
