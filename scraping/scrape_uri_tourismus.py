from __future__ import annotations

import logging
import requests
from datetime import datetime

log = logging.getLogger(__name__)

API_URL = "https://uri.swiss/api/filter"
BASE_URL = "https://uri.swiss"
SOURCE_NAME = "uri.swiss"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://uri.swiss",
    "Referer": "https://uri.swiss/veranstaltungen",
}
PAGE_SIZE = 50
# OData filter: events within Canton Uri (OSM relation 1693971)
FILTER = (
    "containedInPlace/any(item: search.in(item/id, 'osm_1693971'))"
    " and combinedTypeTree/any(item: search.in(item, 'Thing|Event'))"
)


def fetch_events() -> list[dict]:
    all_events = []
    page = 1

    while True:
        body = {
            "filters": FILTER,
            "type": "Event",
            "pagination": {"currentPage": page, "resultsPerPage": PAGE_SIZE},
            "project": "szt-utag",
            "locale": "de",
            "requestedByUrl": "https://uri.swiss/veranstaltungen",
        }

        try:
            resp = requests.post(API_URL, json=body, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            log.error("error fetching page %d: %s", page, e)
            break

        data = resp.json()
        values = data.get("values") or []
        total = data.get("count", 0)

        all_events.extend(values)
        log.info("page %d: got %d events (%d/%d total)", page, len(values), len(all_events), total)

        if len(all_events) >= total or not values:
            break
        page += 1

    log.info("done: %d events from uri.swiss", len(all_events))
    return all_events


def _parse_datetime(dt_str: str | None) -> tuple[str | None, str | None]:
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
    title = event.get("name") or ""
    occurrence = event.get("nextOccurrence")
    start_date, start_time = _parse_datetime(occurrence)

    location = None
    address = event.get("address") or {}
    if isinstance(address, dict):
        location = address.get("addressLocality")

    desc = event.get("disambiguatingDescription") or ""

    slug = event.get("slug") or ""
    source_url = f"{BASE_URL}{slug}" if slug else BASE_URL

    return {
        "source_name": SOURCE_NAME,
        "base_url": BASE_URL,
        "source_url": source_url,
        "event_title": title,
        "start_date": start_date,
        "start_time": start_time,
        "end_datetime": None,
        "location": location,
        "description": desc,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.utcnow().isoformat()
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    with open("../events/uri_tourismus_events.json", "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("saved to ../events/uri_tourismus_events.json")
