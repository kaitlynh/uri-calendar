"""Scraper for Eventfrog — Switzerland's largest event platform.

Eventfrog exposes a proper REST API, so instead of scraping HTML we
query it directly with all Canton Uri ZIP codes as filters.  Since
Eventfrog aggregates events from many sources, we filter out events
that are scraped directly from their primary source (KBU, OL, Theater Uri)
to avoid duplicates with lower-quality metadata.
"""

import json
import logging
import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

log = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API_URL = "https://api.eventfrog.net/public/v1/events"
BASE_URL = "https://eventfrog.ch/de/events.html?searchTerm=uri"
SOURCE_NAME = "eventfrog.ch"

# Every ZIP code in Canton Uri — used as the geographic filter
URI_ZIPS = [
    "6452",  # Sisikon
    "6454",  # Flüelen
    "6460",  # Altdorf
    "6461",  # Isenthal
    "6462",  # Seedorf UR
    "6463",  # Bürglen UR
    "6464",  # Spiringen
    "6465",  # Unterschächen
    "6466",  # Bauen
    "6467",  # Schattdorf
    "6468",  # Attinghausen
    "6472",  # Erstfeld
    "6473",  # Silenen
    "6474",  # Amsteg
    "6475",  # Bristen
    "6476",  # Intschi
    "6478",  # Gurtnellen
    "6484",  # Wassen UR
    "6485",  # Meien
    "6487",  # Göschenen
    "6490",  # Andermatt
    "6491",  # Realp
    "6492",  # Hospental
]


def _get_api_key() -> Optional[str]:
    """Read the Eventfrog API key from EVENTFROG_API_KEY (or .env via python-dotenv)."""
    return os.environ.get("EVENTFROG_API_KEY")


def _de(field) -> Optional[str]:
    """Extract German text from a multilingual field dict."""
    if not field:
        return None
    if isinstance(field, dict):
        return field.get("de") or field.get("en") or next(iter(field.values()), None)
    return str(field)


def _parse_dt(iso: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Split ISO 8601 datetime into (date, time) strings."""
    if not iso:
        return None, None
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")
    except ValueError:
        return iso[:10] if len(iso) >= 10 else None, None


def _resolved_location(event: dict) -> str:
    """Return the best known location: API locationAlias, or detail-page fallback."""
    return _de(event.get("locationAlias")) or event.get("_scraped_location") or ""


def fetch_events() -> list[dict]:
    """Page through the Eventfrog API for all Canton Uri ZIPs, resolve missing
    locations from detail pages, then filter out categories scraped directly."""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "EVENTFROG_API_KEY environment variable not set. "
            "Get an API key at https://www.eventfrog.net"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
    }

    # Build base params with all Uri zip codes
    base_params = [("zip", z) for z in URI_ZIPS]
    base_params += [("country", "CH"), ("perPage", "1000")]

    all_events = []
    page = 1

    while True:
        params = base_params + [("page", str(page))]
        log.info("fetching page %d (%d zip codes, CH)", page, len(URI_ZIPS))
        try:
            resp = requests.get(API_URL, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
        except requests.HTTPError as e:
            log.error("HTTP error: %s", e)
            break
        except Exception as e:
            log.error("error: %s", e)
            break

        data = resp.json()
        events = data.get("events", [])
        total = data.get("totalNumberOfResources", 0)

        all_events.extend(events)
        log.info("page %d: got %d events (total: %d)", page, len(events), total)

        if len(all_events) >= total or len(events) == 0:
            break
        page += 1

    # Fetch locations from detail pages for events missing locationAlias.
    # Must happen BEFORE the venue-based filters below: the API omits
    # locationAlias for many events, but the detail page's JSON-LD usually
    # carries the venue name — and without that, KBU/Theater Uri events
    # hosted at cross-listed venues slip past the filter.
    missing = [e for e in all_events if not _de(e.get("locationAlias"))]
    if missing:
        log.info("fetching locations from %d detail pages", len(missing))
        urls = [e.get("url") for e in missing]
        with ThreadPoolExecutor(max_workers=5) as pool:
            locations = list(pool.map(_scrape_detail_location, urls))
        for event, loc in zip(missing, locations):
            if loc:
                event["_scraped_location"] = loc

    # Filter out KBU events (scraped directly from kbu.ch)
    before = len(all_events)
    all_events = [e for e in all_events
                  if not re.search(r"(?i)kantonsbibliothek", _resolved_location(e))]
    skipped_kbu = before - len(all_events)
    if skipped_kbu:
        log.info("skipped %d KBU events (scraped from kbu.ch)", skipped_kbu)

    # Filter out OL events (scraped directly from olg-ktv-altdorf.ch)
    before = len(all_events)
    all_events = [e for e in all_events
                  if not re.search(r"(?i)OL-Cup|OLG\b|Orientierungslauf",
                                   _de(e.get("title")) or "")]
    skipped_ol = before - len(all_events)
    if skipped_ol:
        log.info("skipped %d OL events (scraped from olg-ktv-altdorf.ch)", skipped_ol)

    # Filter out Theater Uri events (scraped directly from theater-uri.ch)
    before = len(all_events)
    all_events = [e for e in all_events
                  if not (re.search(r"(?i)theater\s+uri", _resolved_location(e)) or
                          re.search(r"(?i)theater\s+uri",
                                    _de(e.get("title")) or ""))]
    skipped_theater = before - len(all_events)
    if skipped_theater:
        log.info("skipped %d Theater Uri events (scraped from theater-uri.ch)", skipped_theater)

    return all_events


def _scrape_detail_location(url: str) -> Optional[str]:
    """Scrape location from an eventfrog detail page via JSON-LD structured data."""
    if not url:
        return None
    detail_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(url, headers=detail_headers, timeout=15)
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    # Extract location from JSON-LD
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                         resp.text, re.DOTALL):
        try:
            ld = json.loads(m.group(1))
            # JSON-LD can be a single object or an array
            items = ld if isinstance(ld, list) else [ld]
            loc = None
            for item in items:
                if isinstance(item, dict) and item.get("location"):
                    loc = item["location"]
                    break
            if not loc:
                continue
            name = loc.get("name", "")
            addr = loc.get("address", {})
            street = addr.get("streetAddress", "")
            city = addr.get("addressLocality", "")
            postal = addr.get("postalCode", "")
            # Build location string, avoiding duplicate name/street
            parts = []
            if name and name != street:
                parts.append(name)
            if street:
                parts.append(street)
            if postal and city:
                parts.append(f"{postal} {city}")
            elif city:
                parts.append(city)
            if parts:
                return ", ".join(parts)
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def _to_template(event: dict, extracted_at: str) -> dict:
    event_id = str(event.get("id", ""))
    title = _de(event.get("title")) or ""
    url = event.get("url") or f"https://www.eventfrog.ch/de/p/event-{event_id}"

    start_date, start_time = _parse_dt(event.get("begin"))
    end_iso = event.get("end")
    end_datetime = None
    if end_iso:
        try:
            end_dt = datetime.fromisoformat(end_iso)
            end_datetime = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            end_datetime = None

    location = _de(event.get("locationAlias")) or event.get("_scraped_location")
    description = _de(event.get("shortDescription"))

    return {
        "source_name": SOURCE_NAME,
        "base_url": BASE_URL,
        "source_url": url,
        "event_title": title,
        "start_date": start_date,
        "start_time": start_time,
        "end_datetime": end_datetime,
        "location": location,
        "description": description,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    raw = fetch_events()
    formatted = [_to_template(e, extracted_at) for e in raw]
    log.info("total events: %d", len(formatted))
    output_path = "../events/eventfrog_events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("events saved to %s", output_path)
