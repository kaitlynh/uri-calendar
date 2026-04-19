"""Scraper for Gemeinde Seedorf — DPCalendar JSON API.

Similar to Flüelen (same CMS), but with additional dedup filters for
OL and RHC events that are scraped from their primary sources.
"""

import logging
import re
import requests
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

# OL events — scraped directly from olg-ktv-altdorf.ch
_SKIP_OL_RE = re.compile(r"(?i)OL-Cup|OLG\b|Orientierungslauf")
# RHC events — scraped directly from rhc-uri.ch
_SKIP_RHC_RE = re.compile(r"(?i)\bRHC\b")

log = logging.getLogger(__name__)

API_URL = "https://www.seedorf-uri.ch/index.php?option=com_dpcalendar&view=events&format=raw&limit=0&Itemid=175"
DETAIL_BASE = "https://www.seedorf-uri.ch"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}


def _parse_time_from_title(title: str) -> Optional[str]:
    """Extract time like '19.00 Uhr' or '9.30 Uhr' from title text."""
    m = re.search(r'(\d{1,2})[.:](\d{2})\s*Uhr', title)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def _parse_location_from_title(title: str) -> Optional[str]:
    """Extract location from after the last 'Uhr' mention.

    Common patterns:
      "Event, 19.00 Uhr, Feuerwehrlokal"  → Feuerwehrlokal
      "Event, 17.30 - 19.30 Uhr, Schützenhaus Seedorf"  → Schützenhaus Seedorf
      "Event: 09.30 Uhr, Description, Pfarrkirche Seedorf"  → Pfarrkirche Seedorf
    """
    # Find the last occurrence of "Uhr" and take everything after it
    m = re.search(r'\d{1,2}[.:]\d{2}\s*Uhr(?:\s*,\s*|\s+)(.+)$', title)
    if not m:
        return None
    after_uhr = m.group(1).strip().rstrip()
    if not after_uhr:
        return None
    # The location is the last comma-separated segment
    parts = [p.strip() for p in after_uhr.split(',')]
    location = parts[-1].strip()
    # Skip if it looks like a description rather than a location (too long)
    if not location or len(location) > 60:
        return None
    return location or None


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
    resp = requests.get(API_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    raw = resp.json()
    data = raw.get("data", raw) if isinstance(raw, dict) else raw

    log.info("found %d raw events", len(data))

    # Filter out OL events (scraped directly from olg-ktv-altdorf.ch)
    before = len(data)
    data = [item for item in data if not _SKIP_OL_RE.search(item.get("title", ""))]
    skipped_ol = before - len(data)
    if skipped_ol:
        log.info("skipped %d OL events (scraped from olg-ktv-altdorf.ch)", skipped_ol)

    # Filter out RHC events (scraped directly from rhc-uri.ch)
    before = len(data)
    data = [item for item in data if not _SKIP_RHC_RE.search(item.get("title", ""))]
    skipped_rhc = before - len(data)
    if skipped_rhc:
        log.info("skipped %d RHC events (scraped from rhc-uri.ch)", skipped_rhc)

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
        if end and not all_day and len(end) >= 16:
            end_datetime = end[:10] + "T" + end[11:19]
            if len(end_datetime) < 19:
                end_datetime += ":00"

        detail_url = f"{DETAIL_BASE}{url}" if url and url.startswith("/") else url
        description = _parse_description(desc_html)

        location = _parse_location_from_title(title)

        events.append({
            "title": title,
            "start_date": start_date,
            "start_time": start_time,
            "end_datetime": end_datetime,
            "detail_url": detail_url or None,
            "description": description,
            "location": location,
        })

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_url": event["detail_url"] or API_URL,
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event["start_time"],
        "end_datetime": event["end_datetime"],
        "location": event.get("location"),
        "description": event["description"],
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    formatted = [_to_template(e, extracted_at) for e in events]
    print(json.dumps(formatted, ensure_ascii=False, indent=2))
