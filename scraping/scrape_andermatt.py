import logging
import requests
import re
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

BASE_URL = "https://www.gemeinde-andermatt.ch/dorfleben/freizeit-kultur/veranstaltungen.html/131"  # Events listing page — used for fetching and as base_url in output
DETAIL_BASE = "https://www.gemeinde-andermatt.ch"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def _page_url(page: int) -> str:
    if page == 1:
        return BASE_URL
    return f"{BASE_URL}/eventsjsRequest/0/eventspage/{page}"


def _parse_time(time_str: Optional[str]) -> Optional[str]:
    """Normalize 'HH:MM' or 'HH:MM Uhr' to 'HH:MM:SS'."""
    if not time_str:
        return None
    m = re.search(r'(\d{1,2}):(\d{2})', time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def _parse_page(page_html: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "html.parser")
    events = []

    for item in soup.select("li.event-item"):
        title_el = item.select_one("h2.event-title a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        detail_url = href if href.startswith("http") else f"{DETAIL_BASE}{href}"

        dtstart = item.select_one("time.dtstart")
        start_date = dtstart.get("datetime") if dtstart else None

        time_from_el = item.select_one("span.event-time-from span.event-time")
        start_time = _parse_time(time_from_el.get_text() if time_from_el else None)

        time_to_el = item.select_one("span.event-time-to span.event-time")
        end_time_raw = time_to_el.get_text() if time_to_el else None
        end_datetime = None
        if start_date and end_time_raw:
            end_time = _parse_time(end_time_raw)
            if end_time:
                end_datetime = f"{start_date}T{end_time}"

        desc_el = item.select_one("p.event-desc")
        description = desc_el.get_text(strip=True) if desc_el else None

        if not title or not start_date:
            continue

        events.append({
            "title": title,
            "start_date": start_date,
            "start_time": start_time,
            "end_datetime": end_datetime,
            "description": description,
            "detail_url": detail_url,
        })

    return events


def _get_total_pages(page_html: str) -> int:
    m = re.search(r"total:\s*parseInt\('(\d+)'", page_html)
    if m:
        return int(m.group(1))
    return 1


def _fetch_location(session: requests.Session, detail_url: str) -> Optional[str]:
    """Fetch a detail page and extract venue name from p.location."""
    try:
        resp = session.get(detail_url, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        loc_el = soup.select_one("p.location")
        if not loc_el:
            return None
        first_text = loc_el.find(string=True, recursive=False)
        if first_text:
            return first_text.strip() or None
    except Exception as e:
        log.debug("error fetching location for %s: %s", detail_url, e)
    return None


def fetch_events() -> list[dict]:
    session = requests.Session()
    session.headers.update(HEADERS)

    log.info("fetching %s", BASE_URL)
    try:
        resp = session.get(_page_url(1), timeout=15)
        resp.raise_for_status()
    except Exception as e:
        log.error("error: %s", e)
        return []

    total_pages = _get_total_pages(resp.text)
    log.info("total pages: %d", total_pages)
    all_events = _parse_page(resp.text)

    for page in range(2, total_pages + 1):
        url = _page_url(page)
        log.info("fetching page %d: %s", page, url)
        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
            all_events.extend(_parse_page(r.text))
        except Exception as e:
            log.error("error on page %d: %s", page, e)

    # Fetch locations from detail pages (session cookies required by site)
    import time
    log.info("fetching locations for %d events", len(all_events))
    for e in all_events:
        e["location"] = _fetch_location(session, e["detail_url"])
        time.sleep(0.3)
    # Retry failures — site rate-limits after ~43 requests, wait for reset
    missing = [e for e in all_events if not e.get("location")]
    if missing:
        log.info("retrying %d events after 60s cooldown", len(missing))
        time.sleep(60)
        session2 = requests.Session()
        session2.headers.update(HEADERS)
        session2.get(_page_url(1), timeout=15)
        for e in missing:
            e["location"] = _fetch_location(session2, e["detail_url"])
            time.sleep(1)
    resolved = sum(1 for e in all_events if e.get("location"))
    log.info("resolved %d/%d locations", resolved, len(all_events))

    log.info("found %d events total", len(all_events))
    return all_events


def _to_template(event: dict, extracted_at: str) -> dict:
    start_iso = event["start_date"]
    if event.get("start_time"):
        start_iso = f"{event['start_date']}T{event['start_time']}"

    return {
        "event_id": f"andermatt-{re.sub(r'[^a-z0-9]', '-', event['title'].lower())}-{event['start_date']}",
        "source_name": "gemeinde-andermatt.ch",
        "base_url": BASE_URL,
        "source_url": event["detail_url"],
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event.get("start_time"),
        "end_datetime": event.get("end_datetime"),
        "location": event.get("location"),
        "description": event.get("description", ""),
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).strftime(ISO_FMT)
    import json
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    output_path = "../events/andermatt_events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("events saved to %s", output_path)
