"""Scraper for uri.ch (UriAgenda) — Guidle-powered events portal for Canton Uri.

API: GET https://www.uri.ch/api/rest/2.0/portals/search-offers/1089644949
  ?portalName=uriagenda&pageOfferId=1083742529&sectionId=349
  &currentPageNumber={page}&language=de

No auth required. Returns events grouped by date, paginated via moreExists flag.
Detail pages are server-rendered HTML at the url field of each offer.

Skips:
  - Cinema Leuzinger events (textLine2 contains "Cinema Leuzinger") — scraped from cinema-leuzinger.ch
  - Kantonsbibliothek Uri events (textLine2 contains "Kantonsbibliothek Uri") — scraped from kbu.ch
  - OL events (title contains "OL-Cup", "OLG", or "Orientierungslauf") — scraped from olg-ktv-altdorf.ch
"""

import logging
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

LIST_URL = "https://www.uri.ch/api/rest/2.0/portals/search-offers/1089644949"
LIST_PARAMS = {
    "portalName": "uriagenda",
    "pageOfferId": "1083742529",
    "sectionId": "349",
    "language": "de",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Patterns for events scraped from direct sources
_SKIP_VENUE_RE = re.compile(r"(?i)cinema\s+leuzinger|kantonsbibliothek\s+uri")
_SKIP_OL_RE = re.compile(r"(?i)OL-Cup|OLG\b|Orientierungslauf")


def _should_skip(offer: dict) -> bool:
    """Return True if this event is scraped from a direct source."""
    venue = offer.get("textLine2") or ""
    if _SKIP_VENUE_RE.search(venue):
        return True
    title = offer.get("title") or ""
    if _SKIP_OL_RE.search(title):
        return True
    return False


def _parse_time(schedule: str) -> Optional[str]:
    """Parse '08:00 Uhr' or '19:30 Uhr' into 'HH:MM:00'."""
    if not schedule:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})\s*Uhr", schedule)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def _fetch_description(url: str) -> Optional[str]:
    """Fetch a detail page and extract the description text."""
    if not url:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")

        # The detail page structure:
        #   <h2>Category</h2>
        #   <h1>Title</h1>
        #   <h3>Location</h3>
        #   <div/p>Description text</div/p>
        # The description is in the main content area after the headings.
        # Look for the Vue-rendered offer detail section.

        # Strategy: find the title heading, then get text content after it
        # that isn't part of sidebar/navigation
        main = soup.select_one("main") or soup
        # Remove sidebar, nav, forms, scripts
        for tag in main.select("nav, form, script, style, .sidebar, [class*='reminder'], [class*='contact']"):
            tag.decompose()

        # Find all text blocks in the main content
        # The description typically appears as paragraph text after the location heading
        text_blocks = []
        for el in main.find_all(["p", "div"], recursive=True):
            # Skip elements with many children (containers)
            if len(el.find_all(["p", "div", "h1", "h2", "h3"])) > 0:
                continue
            text = el.get_text(strip=True)
            if text and len(text) > 30 and not text.startswith("Cookie"):
                text_blocks.append(text)

        if text_blocks:
            # Return the longest text block as the description
            return max(text_blocks, key=len)
        return None
    except Exception as e:
        log.debug("error fetching description %s: %s", url, e)
        return None


def fetch_events() -> list[dict]:
    """Fetch all events from uri.ch API, with descriptions from detail pages."""
    all_offers = []
    page = 1

    while True:
        params = {**LIST_PARAMS, "currentPageNumber": str(page)}
        log.info("fetching page %d", page)
        try:
            resp = requests.get(LIST_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            log.error("error fetching page %d: %s", page, e)
            break

        data = resp.json()
        groups = data.get("groups") or []
        for group in groups:
            for offer in group.get("offers", []):
                offer["_group_date"] = group.get("label", "")
                all_offers.append(offer)

        more = data.get("moreExists", False)
        log.info("page %d: %d groups, moreExists=%s (total offers so far: %d)",
                 page, len(groups), more, len(all_offers))
        if not more:
            break
        page += 1

    # Filter out events from direct sources
    before = len(all_offers)
    skipped_kino = 0
    skipped_kbu = 0
    skipped_ol = 0
    filtered = []
    for o in all_offers:
        venue = o.get("textLine2") or ""
        title = o.get("title") or ""
        if re.search(r"(?i)cinema\s+leuzinger", venue):
            skipped_kino += 1
        elif re.search(r"(?i)kantonsbibliothek\s+uri", venue):
            skipped_kbu += 1
        elif _SKIP_OL_RE.search(title):
            skipped_ol += 1
        else:
            filtered.append(o)
    if skipped_kino:
        log.info("skipped %d kino events (scraped from cinema-leuzinger.ch)", skipped_kino)
    if skipped_kbu:
        log.info("skipped %d KBU events (scraped from kbu.ch)", skipped_kbu)
    if skipped_ol:
        log.info("skipped %d OL events (scraped from olg-ktv-altdorf.ch)", skipped_ol)

    # Fetch descriptions from detail pages concurrently
    log.info("fetching descriptions for %d events", len(filtered))
    urls = list({o.get("url") or "" for o in filtered if o.get("url")})
    descriptions = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(_fetch_description, u): u for u in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            desc = future.result()
            if desc:
                descriptions[url] = desc
    log.info("resolved %d/%d descriptions", len(descriptions), len(urls))

    for o in filtered:
        o["_description"] = descriptions.get(o.get("url") or "")

    log.info("done: %d events from uri.ch (skipped %d total)", len(filtered), before - len(filtered))
    return filtered


def _to_template(event: dict, extracted_at: str) -> dict:
    title = event.get("title") or ""
    first_show = event.get("firstShow")  # YYYY-MM-DD
    schedule = event.get("schedule") or ""
    start_time = _parse_time(schedule)

    # Location: "City - Venue" in textLine2
    text_line2 = event.get("textLine2") or ""
    city = event.get("city") or ""
    if " - " in text_line2:
        parts = text_line2.split(" - ", 1)
        location = f"{parts[1].strip()}, {parts[0].strip()}"
    elif city:
        location = city
    else:
        location = text_line2 or None

    source_url = event.get("url") or ""
    description = event.get("_description") or ""

    return {
        "source_url": source_url,
        "event_title": title,
        "start_date": first_show,
        "start_time": start_time,
        "end_datetime": None,
        "location": location,
        "description": description,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    import os
    output_path = os.path.join(os.path.dirname(__file__), "..", "events", "uri_agenda_events.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("saved to %s", output_path)
