"""Scraper for MySwitzerland Open Data API — Switzerland Tourism events.

Fetches events from the opendata.myswitzerland.io API and filters by a
geographic bounding box around Canton Uri.  Uses concurrent requests
with a global rate limiter to stay within API limits.
"""

import logging
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
except ImportError:
    pass

log = logging.getLogger(__name__)

API_URL = "https://opendata.myswitzerland.io/v1/attractions"  # API endpoint for fetching event data
BASE_URL = "https://uri.swiss"  # Events listing page — used as base_url in output and as fallback link
SOURCE_NAME = "uri.swiss"  # Bare domain identifier
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}

# Tight bounding box for Canton Uri — errs on the side of exclusion.
# Confirmed anchor points: Altdorf 46.880/8.644, Andermatt 46.633/8.594,
# Erstfeld 46.826/8.647, Wassen 46.707/8.603, Göschenen 46.671/8.584,
# Seelisberg 46.972/8.584, Sisikon 46.964/8.630, Spiringen 46.880/8.808,
# Unterschächen 46.852/8.815, Isenthal 46.936/8.558, Bauen 46.957/8.569.
# Excluded intentionally: Realp (tight S border), northernmost Schwyz shore.
URI_LAT_MIN, URI_LAT_MAX = 46.62, 46.97
URI_LON_MIN, URI_LON_MAX = 8.54, 8.83


def _in_uri(item: dict) -> bool:
    geo = item.get("geo") or {}
    lat = geo.get("latitude")
    lon = geo.get("longitude")
    if lat is None or lon is None:
        return False
    return URI_LAT_MIN <= lat <= URI_LAT_MAX and URI_LON_MIN <= lon <= URI_LON_MAX


_WORKERS = 8
_rate_lock = threading.Lock()
_last_request_at = 0.0
_REQUEST_INTERVAL = 0.15  # max ~6 req/s globally


def _fetch_page(page: int, req_headers: dict) -> tuple[int, list[dict]]:
    global _last_request_at
    backoff = 2
    for _ in range(5):
        with _rate_lock:
            gap = _REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
            if gap > 0:
                time.sleep(gap)
            _last_request_at = time.monotonic()

        try:
            resp = requests.get(API_URL, params={"lang": "de", "page": page}, headers=req_headers, timeout=15)
        except Exception as e:
            log.error("error fetching page %d: %s", page, e)
            return page, []

        if resp.status_code == 200:
            return page, resp.json().get("data") or []
        if resp.status_code == 429:
            log.warning("429 on page %d — backing off %ds", page, backoff)
            time.sleep(backoff)
            backoff *= 2
            continue
        log.warning("HTTP %s on page %d", resp.status_code, page)
        return page, []

    log.error("page %d failed after retries", page)
    return page, []


def fetch_events() -> list[dict]:
    req_headers = dict(HEADERS)
    resolved_key = os.getenv("MYSWITZERLAND_API_KEY")
    if resolved_key:
        req_headers["x-api-key"] = resolved_key
    else:
        log.warning("no MYSWITZERLAND_API_KEY found — request will likely be rejected")

    # Fetch page 1 to discover total pages
    resp = requests.get(API_URL, params={"lang": "de", "page": 1}, headers=req_headers, timeout=15)
    data1 = resp.json()
    first_items = data1.get("data") or []
    total_pages = data1.get("meta", {}).get("page", {}).get("totalPages", 1)
    log.info("fetching %s (%d pages, %d workers)", API_URL, total_pages, _WORKERS)

    results: dict[int, list[dict]] = {1: first_items}
    uri_total = sum(1 for i in first_items if _in_uri(i))
    pages_done = 1

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {pool.submit(_fetch_page, p, req_headers): p for p in range(2, total_pages + 1)}
        for future in as_completed(futures):
            page, items = future.result()
            results[page] = items
            pages_done += 1
            uri_total += sum(1 for i in items if _in_uri(i))
            log.info("progress: %d/%d pages — %d Uri attractions so far", pages_done, total_pages, uri_total)

    attractions = [item for p in sorted(results) for item in results[p] if _in_uri(item)]
    log.info("done: %d Uri attractions from %d pages", len(attractions), total_pages)
    return attractions


def _parse_date(dt_str: str | None) -> tuple[str | None, str | None]:
    """Return (date_str, time_str) from an ISO datetime string."""
    if not dt_str:
        return None, None
    if "T" in dt_str:
        parts = dt_str.split("T")
        d = parts[0]
        t = parts[1][:8] if len(parts) > 1 else None
        return d, t
    return dt_str[:10], None


def _to_template(event: dict, extracted_at: str) -> dict:
    # Try common field names from MySwitzerland API
    title = (
        event.get("name")
        or event.get("title")
        or event.get("Name")
        or ""
    )
    if isinstance(title, dict):
        title = title.get("de") or next(iter(title.values()), "")

    start_raw = event.get("startDate") or event.get("start_date") or event.get("dateFrom")
    end_raw = event.get("endDate") or event.get("end_date") or event.get("dateTo")
    start_date, start_time = _parse_date(start_raw)
    end_date, _ = _parse_date(end_raw)
    end_datetime = None
    if end_raw and end_raw != start_raw:
        end_d, end_t = _parse_date(end_raw)
        if end_d and end_t:
            end_datetime = f"{end_d}T{end_t}"
        elif end_d:
            end_datetime = f"{end_d}T00:00:00"

    location_obj = event.get("location") or event.get("place") or {}
    if isinstance(location_obj, dict):
        location = location_obj.get("name") or location_obj.get("city") or None
    else:
        location = str(location_obj) if location_obj else None

    desc = event.get("description") or event.get("shortDescription") or ""
    if isinstance(desc, dict):
        desc = desc.get("de") or next(iter(desc.values()), "")

    source_url = event.get("url") or event.get("detailUrl") or event.get("link") or BASE_URL

    return {
        "source_name": SOURCE_NAME,
        "base_url": BASE_URL,
        "source_url": source_url,
        "event_title": title,
        "start_date": start_date,
        "start_time": start_time,
        "end_datetime": end_datetime,
        "location": location,
        "description": desc,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).isoformat()
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    with open("../events/myswitzerland_events.json", "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("saved to ../events/myswitzerland_events.json")
