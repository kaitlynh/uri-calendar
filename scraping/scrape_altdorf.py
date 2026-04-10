import logging
import requests
import re
import json
import html
import urllib3
from datetime import datetime
from typing import Optional

urllib3.disable_warnings()

log = logging.getLogger(__name__)

BASE_URL = "https://www.altdorf.ch/anlaesseaktuelles"  # Events listing page — used for fetching and as base_url in output
DETAIL_BASE = "https://www.altdorf.ch"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
STRIP_TAGS = re.compile(r'<[^>]+>')
ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def _extract_title(name_html: str) -> str:
    """Extract plain text title from HTML link e.g. '<a href="...">Title</a>'."""
    return STRIP_TAGS.sub('', html.unescape(name_html)).strip()


def _extract_href(name_html: str) -> Optional[str]:
    """Extract the href from an HTML link."""
    m = re.search(r'href="([^"]+)"', name_html)
    if m:
        return m.group(1)
    return None


def _parse_time_from_lead(lead_text: str) -> Optional[str]:
    """Extract start time from the icms-lead-container text.

    Formats seen:
      "25. Apr. 2026, 9.30 Uhr - 10.30 Uhr"
      "16. Apr. 2026, 19:00 Uhr"
      "18.00 Uhr*"
      "ganztägig"  -> None
      no time at all -> None
    """
    if not lead_text or "ganztägig" in lead_text.lower():
        return None
    # Match time like "9.30 Uhr" or "19:00 Uhr" (first occurrence = start time)
    m = re.search(r'(\d{1,2})[.:](\d{2})\s*Uhr', lead_text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def _fetch_detail_info(detail_url: str) -> dict:
    """Fetch an event detail page and extract description and start time."""
    result = {"description": "", "start_time": None}
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code != 200:
            return result

        # Extract time from icms-lead-container
        lead_match = re.search(
            r'<div[^>]+class="[^"]*icms-lead-container[^"]*"[^>]*>(.*?)</div>',
            resp.text, re.DOTALL
        )
        if lead_match:
            lead_text = STRIP_TAGS.sub(' ', lead_match.group(1))
            lead_text = html.unescape(lead_text).replace('\xa0', ' ')
            result["start_time"] = _parse_time_from_lead(lead_text)

        # Extract description from main content area
        match = re.search(
            r'<div[^>]+class="[^"]*icms-detail-text[^"]*"[^>]*>(.*?)</div>',
            resp.text, re.DOTALL
        )
        if not match:
            match = re.search(
                r'<div[^>]+class="[^"]*content-area[^"]*"[^>]*>(.*?)</div>\s*</div>',
                resp.text, re.DOTALL
            )
        if match:
            raw = match.group(1)
            text = re.sub(r'<br\s*/?>', '\n', raw)
            text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', text)
            text = STRIP_TAGS.sub('', text)
            text = html.unescape(text).replace('\xa0', ' ')
            text = re.sub(r'\n{3,}', '\n\n', text)
            result["description"] = text.strip()

        return result
    except Exception as e:
        log.warning("error fetching detail %s: %s", detail_url, e)
        return result


def parse_events_from_html(page_html: str) -> list[dict]:
    """Parse events from the altdorf.ch events page."""
    # The table embeds all events as JSON in data-entities attribute
    match = re.search(r'id="anlassList"[^>]*data-entities="([^"]+)"', page_html)
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
        detail_url = f"{DETAIL_BASE}{href}" if href else f"{DETAIL_BASE}/_rte/anlass/{event_id}"

        start_date = item.get("_datumVon")
        end_date = item.get("_datumBis")
        location_venue = item.get("lokalitaet", "")
        location_city = item.get("ort", "")
        location = ", ".join(filter(None, [location_venue, location_city])) or None
        organisator = item.get("organisator", "")

        if not title or not start_date:
            continue

        events.append({
            "id": event_id,
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "location": location,
            "organisator": organisator,
            "detail_url": detail_url,
        })

    return events


def _is_kino(event: dict) -> bool:
    """Detect cinema listings — these are scraped directly from cinema-leuzinger.ch."""
    title = event.get("title", "")
    if title.startswith("Kino:") or title.startswith("Kino "):
        return True
    location = event.get("location") or ""
    if re.search(r"(?i)cinema\s+leuzinger|kino\s+leuzinger", location):
        return True
    return False


def _is_kbu(event: dict) -> bool:
    """Detect library events — these are scraped directly from kbu.ch."""
    location = event.get("location") or ""
    return bool(re.search(r"(?i)kantonsbibliothek", location))


def _is_ol(event: dict) -> bool:
    """Detect OL events — these are scraped directly from olg-ktv-altdorf.ch."""
    title = event.get("title", "")
    return bool(re.search(r"(?i)OL-Cup|OLG\b|Orientierungslauf", title))


def _is_theater_uri(event: dict) -> bool:
    """Detect Theater Uri events — these are scraped directly from theater-uri.ch."""
    location = event.get("location") or ""
    title = event.get("title", "")
    return bool(re.search(r"(?i)theater\s+uri", location) or
                re.search(r"(?i)theater\s+uri", title))


def _to_template(event: dict, extracted_at: str) -> dict:
    end_dt = None
    if event.get("end_date") and event["end_date"] != event["start_date"]:
        end_dt = f"{event['end_date']}T00:00:00"

    title = event["title"]
    if event.get("organisator"):
        title = f"{title} | {event['organisator']}"

    return {
        "event_id": f"altdorf-{event['id']}",
        "source_name": "altdorf.ch",
        "base_url": BASE_URL,
        "source_url": event["detail_url"],
        "event_title": title,
        "start_date": event["start_date"],
        "start_time": event.get("start_time"),
        "end_datetime": end_dt,
        "location": event["location"],
        "description": event.get("description", ""),
        "extracted_at": extracted_at,
    }


def fetch_events() -> list[dict]:
    """Fetch all events from altdorf.ch."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    log.info("fetching %s", BASE_URL)
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code != 200:
            log.warning("HTTP %s", resp.status_code)
            return []
    except Exception as e:
        log.error("error: %s", e)
        return []

    events = parse_events_from_html(resp.text)
    # Filter out events scraped from direct sources
    before = len(events)
    events = [e for e in events if not _is_kino(e)]
    skipped_kino = before - len(events)
    if skipped_kino:
        log.info("skipped %d kino events (scraped from cinema-leuzinger.ch)", skipped_kino)
    before = len(events)
    events = [e for e in events if not _is_kbu(e)]
    skipped_kbu = before - len(events)
    if skipped_kbu:
        log.info("skipped %d KBU events (scraped from kbu.ch)", skipped_kbu)
    before = len(events)
    events = [e for e in events if not _is_ol(e)]
    skipped_ol = before - len(events)
    if skipped_ol:
        log.info("skipped %d OL events (scraped from olg-ktv-altdorf.ch)", skipped_ol)
    before = len(events)
    events = [e for e in events if not _is_theater_uri(e)]
    skipped_theater = before - len(events)
    if skipped_theater:
        log.info("skipped %d Theater Uri events (scraped from theater-uri.ch)", skipped_theater)
    log.info("found %d events, fetching details in parallel", len(events))

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_event = {
            executor.submit(_fetch_detail_info, event["detail_url"]): event
            for event in events
        }
        for future in as_completed(future_to_event):
            info = future.result()
            event = future_to_event[future]
            event["description"] = info["description"]
            event["start_time"] = info["start_time"]

    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.utcnow().strftime(ISO_FMT)
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    output_path = "../events/altdorf_events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("events saved to %s", output_path)
