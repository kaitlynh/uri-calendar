import logging
import re
import requests
from datetime import datetime, date
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

URL = "https://erstfeld.ch/portrait/veranstaltungen"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

MONTHS_DE = {
    "Jan.": 1, "Feb.": 2, "Marz": 3, "März": 3, "Apr.": 4,
    "Mai": 5, "Juni": 6, "Juli": 7, "Aug.": 8,
    "Sep.": 9, "Sept.": 9, "Okt.": 10, "Nov.": 11, "Dez.": 12,
}


def _parse_date(day_str: str, month_str: str) -> Optional[str]:
    """Parse day + German month abbreviation into YYYY-MM-DD, inferring year."""
    try:
        day = int(day_str.strip())
        month = MONTHS_DE.get(month_str.strip())
        if not month:
            return None
        # Infer year: if month is before current month, assume next year
        today = date.today()
        year = today.year
        candidate = date(year, month, day)
        if candidate < today.replace(day=1):
            year += 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        return None


def _parse_time(time_str: str) -> Optional[str]:
    """Parse '13.30 - 14.15 Uhr' or '19.00 Uhr' into start time HH:MM:00."""
    if not time_str or time_str.strip() in ('–', '-', ''):
        return None
    m = re.search(r'(\d{1,2})[.:](\d{2})', time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def _parse_end_time(time_str: str) -> Optional[str]:
    """Parse end time from '13.30 - 14.15 Uhr'."""
    if not time_str:
        return None
    m = re.search(r'\d{1,2}[.:]\d{2}\s*-\s*(\d{1,2})[.:](\d{2})', time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def fetch_events() -> list:
    """Fetch all events from erstfeld.ch/portrait/veranstaltungen."""
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
    cards = soup.select(".event")
    log.info("found %d events", len(cards))

    events = []
    for card in cards:
        day_el = card.select_one(".tag")
        month_el = card.select_one(".monat")
        title_el = card.select_one(".event-titel b")
        time_el = card.select_one(".uhrzeit")
        location_el = card.select_one(".ort")

        if not day_el or not month_el or not title_el:
            continue

        title = title_el.get_text(strip=True)
        # Organizer is the text after <br> in the same <p>
        p_el = card.select_one(".event-titel p")
        if p_el:
            # Get all text nodes after the <b> tag
            organizer = p_el.get_text(strip=True).replace(title, '', 1).strip()
            if organizer:
                title = f"{title} | {organizer}"
        day_str = day_el.get_text(strip=True)
        month_str = month_el.get_text(strip=True)
        time_str = time_el.get_text(strip=True) if time_el else ""
        location = location_el.get_text(strip=True) if location_el else None

        # Clean up dash placeholders
        if location and location in ('–', '-'):
            location = None

        events.append({
            "title": title,
            "day": day_str,
            "month": month_str,
            "time_str": time_str,
            "location": location,
        })

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    start_date = _parse_date(event["day"], event["month"])
    start_time = _parse_time(event.get("time_str", ""))
    end_time = _parse_end_time(event.get("time_str", ""))

    end_datetime = None
    if start_date and end_time:
        end_datetime = f"{start_date}T{end_time}"

    return {
        "source_url": URL,
        "event_title": event["title"],
        "start_date": start_date,
        "start_time": start_time,
        "end_datetime": end_datetime,
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
