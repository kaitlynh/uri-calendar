import logging
import re
import requests
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

API_URL = "https://www.seedorf-uri.ch/index.php?option=com_dpcalendar&view=events&format=raw&limit=0&Itemid=175"
DETAIL_BASE = "https://www.seedorf-uri.ch"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def _parse_time_from_title(title: str) -> Optional[str]:
    """Extract time like '19.00 Uhr' or '9.30 Uhr' from title text."""
    m = re.search(r'(\d{1,2})[.:](\d{2})\s*Uhr', title)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def _parse_description(desc_html: str) -> Optional[str]:
    """Extract description text from the DPCalendar tooltip HTML."""
    if not desc_html:
        return None
    soup = BeautifulSoup(desc_html, "html.parser")
    desc_el = soup.select_one(".dp-event-tooltip__description")
    if desc_el:
        text = desc_el.get_text(separator=" ", strip=True)
        if text:
            return text
    return None


def fetch_events() -> list:
    """Fetch all events from the DPCalendar JSON API."""
    log.info("fetching %s", API_URL)
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s", resp.status_code)
            return []
        raw = resp.json()
        data = raw.get("data", raw) if isinstance(raw, dict) else raw
    except Exception as e:
        log.error("error: %s", e)
        return []

    log.info("found %d events", len(data))

    events = []
    for item in data:
        title = item.get("title", "").strip()
        if not title:
            continue

        start = item.get("start", "")
        end = item.get("end")
        all_day = item.get("allDay", False)
        url = item.get("url", "")
        desc_html = item.get("description", "")

        # Parse start date from ISO string
        start_date = start[:10] if start else None

        # Try to extract time from structured field first, fall back to title
        start_time = None
        if not all_day and start and len(start) > 10:
            start_time = start[11:]
            if len(start_time) == 5:
                start_time += ":00"
        if not start_time:
            start_time = _parse_time_from_title(title)

        end_datetime = None
        if end and not all_day and len(end) > 10:
            end_datetime = end

        detail_url = f"{DETAIL_BASE}{url}" if url and url.startswith("/") else url
        description = _parse_description(desc_html)

        events.append({
            "title": title,
            "start_date": start_date,
            "start_time": start_time,
            "end_datetime": end_datetime,
            "detail_url": detail_url or None,
            "description": description,
        })

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_url": event["detail_url"] or API_URL,
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event["start_time"],
        "end_datetime": event["end_datetime"],
        "location": None,
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
