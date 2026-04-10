"""Scraper for Uri Tourismus (uri.swiss) — the official tourism board.

Fetches events via a POST-based filter API with OData-style queries.
Event times arrive in UTC and must be converted to Europe/Zurich local
time (CET/CEST) — we compute the offset manually to avoid adding a
pytz/dateutil dependency.  Venue names are resolved by fetching each
event's detail page concurrently.

Like other aggregator sources, cinema, KBU, OL, and Theater Uri events
are filtered out to avoid duplicates.
"""

from __future__ import annotations

import logging
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

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

# UTC+1 (CET) / UTC+2 (CEST) — we approximate with dateutil or manual offset.
# Europe/Zurich switches to CEST (UTC+2) on last Sunday of March, back on last Sunday of October.
ZURICH_CET = timezone(timedelta(hours=1))
ZURICH_CEST = timezone(timedelta(hours=2))

# Skip cinema events — these are scraped directly from cinema-leuzinger.ch
SKIP_TYPES = {"CinemaScreening"}

# OL events — scraped directly from olg-ktv-altdorf.ch
_SKIP_OL_RE = re.compile(r"(?i)OL-Cup|OLG\b|Orientierungslauf")


def _is_cest(dt: datetime) -> bool:
    """Check if a UTC datetime falls within CEST (Central European Summer Time).

    CEST runs from last Sunday of March 01:00 UTC to last Sunday of October 01:00 UTC.
    """
    year = dt.year
    # Last Sunday of March
    mar31 = datetime(year, 3, 31, tzinfo=timezone.utc)
    cest_start = mar31 - timedelta(days=(mar31.weekday() + 1) % 7)
    cest_start = cest_start.replace(hour=1, minute=0, second=0)
    # Last Sunday of October
    oct31 = datetime(year, 10, 31, tzinfo=timezone.utc)
    cest_end = oct31 - timedelta(days=(oct31.weekday() + 1) % 7)
    cest_end = cest_end.replace(hour=1, minute=0, second=0)
    return cest_start <= dt < cest_end


def _utc_to_zurich(dt_str: str | None) -> tuple[str | None, str | None]:
    """Convert a UTC ISO datetime string to Europe/Zurich local date + time."""
    if not dt_str:
        return None, None
    try:
        # Parse ISO format: "2026-04-15T14:30:00.000Z" or "2026-04-15T14:30:00Z"
        clean = dt_str.replace(".000Z", "Z").replace("Z", "+00:00")
        if "T" not in clean:
            return clean[:10], None
        dt = datetime.fromisoformat(clean)
        # Convert to Zurich time
        offset = ZURICH_CEST if _is_cest(dt) else ZURICH_CET
        local = dt.astimezone(offset)
        return local.strftime("%Y-%m-%d"), local.strftime("%H:%M:%S")
    except (ValueError, IndexError):
        # Fallback: naive split
        if "T" in dt_str:
            parts = dt_str.split("T")
            return parts[0], parts[1][:8] if len(parts) > 1 else None
        return dt_str[:10], None


def _fetch_venue(slug: str) -> str | None:
    """Fetch an event detail page and extract the venue name from the address block."""
    if not slug:
        return None
    url = f"{BASE_URL}{slug}"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if resp.status_code != 200:
            return None
        # Structure: <span class="text-large-700"> Adresse </span> ...
        #   <div class="flex flex-col gap-1 text-regular-400">
        #     <span>Venue Name</span> <span>Street</span> <span>ZIP City</span>
        match = re.search(
            r'Adresse\s*</span>.*?'
            r'<div[^>]*class="[^"]*text-regular-400[^"]*"[^>]*>\s*'
            r'<span>([^<]+)</span>',
            resp.text, re.DOTALL
        )
        if match:
            return match.group(1).strip()
    except Exception as e:
        log.debug("error fetching venue for %s: %s", slug, e)
    return None


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

    # Filter out cinema events (scraped directly from cinema-leuzinger.ch)
    before = len(all_events)
    all_events = [e for e in all_events if e.get("additionalType") not in SKIP_TYPES]
    skipped_kino = before - len(all_events)
    if skipped_kino:
        log.info("skipped %d CinemaScreening events (scraped from cinema-leuzinger.ch)", skipped_kino)

    # Filter out OL events (scraped directly from olg-ktv-altdorf.ch)
    before = len(all_events)
    all_events = [e for e in all_events if not _SKIP_OL_RE.search(e.get("name") or "")]
    skipped_ol = before - len(all_events)
    if skipped_ol:
        log.info("skipped %d OL events (scraped from olg-ktv-altdorf.ch)", skipped_ol)

    # Fetch venue names from detail pages (concurrent)
    log.info("fetching venue names for %d events", len(all_events))
    venues = {}  # slug -> venue name
    slugs = list({e.get("slug") or "" for e in all_events if e.get("slug")})
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_slug = {executor.submit(_fetch_venue, s): s for s in slugs}
        for future in as_completed(future_to_slug):
            slug = future_to_slug[future]
            venue = future.result()
            if venue:
                venues[slug] = venue
    log.info("resolved %d/%d venue names", len(venues), len(slugs))

    # Attach venue info to events
    for event in all_events:
        event["_venue"] = venues.get(event.get("slug") or "")

    # Filter out KBU events after venue resolution (scraped directly from kbu.ch)
    before = len(all_events)
    all_events = [e for e in all_events
                  if not re.search(r"(?i)kantonsbibliothek", e.get("_venue") or "")]
    skipped_kbu = before - len(all_events)
    if skipped_kbu:
        log.info("skipped %d KBU events (scraped from kbu.ch)", skipped_kbu)

    # Filter out Theater Uri events (scraped directly from theater-uri.ch)
    before = len(all_events)
    all_events = [e for e in all_events
                  if not (re.search(r"(?i)theater\s+uri", e.get("_venue") or "") or
                          re.search(r"(?i)theater\s+uri", e.get("name") or ""))]
    skipped_theater = before - len(all_events)
    if skipped_theater:
        log.info("skipped %d Theater Uri events (scraped from theater-uri.ch)", skipped_theater)

    log.info("done: %d events from uri.swiss", len(all_events))
    return all_events


def _to_template(event: dict, extracted_at: str) -> dict:
    title = event.get("name") or ""
    occurrence = event.get("nextOccurrence")
    start_date, start_time = _utc_to_zurich(occurrence)

    # Build location: "Venue, Town" or just "Town"
    town = None
    address = event.get("address") or {}
    if isinstance(address, dict):
        town = address.get("addressLocality")
    venue = event.get("_venue")
    if venue and town:
        location = f"{venue}, {town}"
    else:
        location = venue or town

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
    extracted_at = datetime.now(timezone.utc).isoformat()
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    with open("../events/uri_tourismus_events.json", "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("saved to ../events/uri_tourismus_events.json")
