"""Scraper for Gemeinde Bürglen — same ICMS platform as Altdorf.

Extracts events from the embedded JSON data-entities attribute, then
fetches detail pages in parallel to resolve times and descriptions.
"""

import html
import json
import logging
import re
import requests
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger(__name__)

URL = "https://www.buerglen.ch/anlaesseaktuelles"
DETAIL_BASE = "https://www.buerglen.ch"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}
STRIP_TAGS = re.compile(r'<[^>]+>')


def _extract_title(name_html: str) -> str:
    return STRIP_TAGS.sub('', html.unescape(name_html)).strip()


def _extract_href(name_html: str) -> Optional[str]:
    m = re.search(r'href="([^"]+)"', name_html)
    return m.group(1) if m else None


def _parse_time(time_str: str) -> Optional[str]:
    """Extract HH:MM from strings like '13.00 Uhr' or '13:00'."""
    m = re.search(r'(\d{1,2})[.:](\d{2})', time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def _fetch_detail(detail_url: str) -> dict:
    """Fetch detail page, extract time and description from icms-lead-container."""
    result = {"start_time": None, "end_time": None, "description": ""}
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return result

        # Extract time from icms-lead-container (format: "Venue<br>Town<br>15. Apr. 2026, 13.00 Uhr - 17.00 Uhr")
        lead_match = re.search(
            r'<div[^>]+class="[^"]*icms-lead-container[^"]*"[^>]*>(.*?)</div>',
            resp.text, re.DOTALL
        )
        if lead_match:
            lead_text = STRIP_TAGS.sub(' ', lead_match.group(1)).strip()
            # Look for time pattern: "13.00 Uhr - 17.00 Uhr" or "13.00 Uhr"
            time_match = re.search(r'(\d{1,2}[.:]\d{2})\s*Uhr\s*(?:-\s*(\d{1,2}[.:]\d{2})\s*Uhr)?', lead_text)
            if time_match:
                result["start_time"] = _parse_time(time_match.group(1))
                if time_match.group(2):
                    result["end_time"] = _parse_time(time_match.group(2))

        # Extract description
        desc_match = re.search(
            r'<div[^>]+class="[^"]*icms-detail-text[^"]*"[^>]*>(.*?)</div>',
            resp.text, re.DOTALL
        )
        if desc_match:
            text = re.sub(r'<br\s*/?>', '\n', desc_match.group(1))
            text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', text)
            text = STRIP_TAGS.sub('', text)
            text = html.unescape(text).replace('\xa0', ' ').strip()
            text = re.sub(r'\n{3,}', '\n\n', text)
            if text:
                result["description"] = text

    except Exception as e:
        log.warning("error fetching detail %s: %s", detail_url, e)
    return result


def fetch_events() -> list:
    """Fetch all events from buerglen.ch/anlaesseaktuelles."""
    log.info("fetching %s", URL)
    resp = requests.get(URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    # Parse the embedded JSON from data-entities attribute
    match = re.search(r'id="anlassList"[^>]*data-entities="([^"]+)"', resp.text)
    if not match:
        log.warning("could not find anlassList data-entities")
        return []

    raw_json = html.unescape(match.group(1))
    try:
        entities = json.loads(raw_json)
    except json.JSONDecodeError as e:
        log.error("JSON parse error: %s", e)
        return []

    events = []
    for item in entities.get("data", []):
        event_id = item.get("id", "")
        name_html = item.get("name", "")
        title = _extract_title(name_html)
        href = _extract_href(name_html)
        detail_url = f"{DETAIL_BASE}{href}" if href else f"{DETAIL_BASE}/anlaesseaktuelles/{event_id}"

        start_date = item.get("_datumVon")
        end_date = item.get("_datumBis")
        location_venue = item.get("lokalitaet", "").strip()
        location_city = item.get("ort", "").strip()
        location = ", ".join(filter(None, [location_venue, location_city])) or None

        if not title or not start_date:
            continue

        events.append({
            "id": event_id,
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "location": location,
            "detail_url": detail_url,
        })

    log.info("found %d events, fetching details in parallel", len(events))

    # Fetch detail pages for times and descriptions
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_event = {
            executor.submit(_fetch_detail, event["detail_url"]): event
            for event in events
        }
        for future in as_completed(future_to_event):
            event = future_to_event[future]
            detail = future.result()
            event["start_time"] = detail["start_time"]
            event["end_time"] = detail["end_time"]
            event["description"] = detail["description"]

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    end_dt = None
    if event.get("end_time") and event.get("start_date"):
        end_dt = f"{event['start_date']}T{event['end_time']}"
    elif event.get("end_date") and event["end_date"] != event["start_date"]:
        end_dt = f"{event['end_date']}T00:00:00"

    return {
        "source_url": event["detail_url"],
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event.get("start_time"),
        "end_datetime": end_dt,
        "location": event["location"],
        "description": event.get("description", ""),
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json as json_mod
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    formatted = [_to_template(e, extracted_at) for e in events]
    print(json_mod.dumps(formatted, ensure_ascii=False, indent=2))
