import logging
import re
import requests
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL = "https://volleyuri.ch/veranstaltungen"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def _parse_date(date_str: str) -> Optional[str]:
    """Parse '01.02.2026' or '01.02.2026, ' into 'YYYY-MM-DD'."""
    try:
        cleaned = re.sub(r'[,\s]+$', '', date_str.strip())
        dt = datetime.strptime(cleaned, "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def _parse_time(time_str: str) -> Optional[str]:
    """Extract first HH:MM from strings like '19:00 Uhr' or 'ca. ab 18:00 Uhr'."""
    if not time_str:
        return None
    match = re.search(r'(\d{1,2}):(\d{2})', time_str)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}:00"
    return None


def _fetch_description(detail_url: str) -> Optional[str]:
    """Fetch a detail page and extract the description paragraph."""
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        section = soup.select_one("section.section_events_main")
        if not section:
            return None
        # The description is in a <div> after the detail-wrap elements
        for div in section.find_all("div"):
            # Skip the detail-wrap divs (date, location)
            if "detail-wrap" in div.get("class", []):
                continue
            # Find divs with <p> content that aren't wrappers
            p = div.find("p")
            if p and len(p.get_text(strip=True)) > 10:
                return p.get_text(strip=True)
        return None
    except Exception as e:
        log.warning("error fetching detail %s: %s", detail_url, e)
        return None


def fetch_events() -> list:
    """Fetch all events from volleyuri.ch/veranstaltungen."""
    log.info("fetching %s", BASE_URL)
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s", resp.status_code)
            return []
    except Exception as e:
        log.error("error: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("a.event_card")
    log.info("found %d events", len(cards))

    events = []
    for card in cards:
        title_el = card.select_one("h5")
        date_spans = card.select("p.dates span")
        location_el = card.select("div.calendar_item > p.col:not(.dates)")
        link = card.get("href", "")

        title = title_el.get_text(strip=True) if title_el else ""
        date_str = date_spans[0].get_text(strip=True) if date_spans else ""
        time_str = date_spans[1].get_text(strip=True) if len(date_spans) > 1 else ""
        location = location_el[0].get_text(strip=True) if location_el else None

        detail_url = f"https://volleyuri.ch{link}" if link.startswith("/") else link
        description = _fetch_description(detail_url)

        events.append({
            "title": title,
            "date": date_str,
            "time": time_str,
            "location": location,
            "detail_url": detail_url,
            "description": description,
        })

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_url": event["detail_url"],
        "event_title": event["title"],
        "start_date": _parse_date(event["date"]),
        "start_time": _parse_time(event.get("time", "")),
        "end_datetime": None,
        "location": event["location"],
        "description": event["description"],
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    formatted = [_to_template(e, extracted_at) for e in events]
    print(json.dumps(formatted, ensure_ascii=False, indent=2))
