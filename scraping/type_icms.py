"""Scraper type: ICMS CMS — used by several Uri municipalities.

The ICMS platform (used by Erstfeld, Silenen, and others) renders event
cards with a consistent DOM structure:

    .event
        .tag      → day number ("15")
        .monat    → German month abbreviation ("Apr.")
        .event-titel b → event title
        .uhrzeit  → time, often as "19.30 - 21.00 Uhr"
        .ort      → location/venue

Date and time parsing is delegated to parse_utils (German month names,
Swiss time format with period separator).
"""

import logging

import requests
from bs4 import BeautifulSoup

from parse_utils import parse_german_date, parse_time, parse_end_time

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def scrape(source: dict, extracted_at: str) -> list:
    """Scrape events from an ICMS-based municipality site."""
    from scraping import Event

    url = source["url"]
    source_name = source.get("source_name") or source.get("name")
    base_url = source.get("base_url") or url

    log.info("fetching %s", url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s for %s", resp.status_code, url)
            return []
    except Exception as e:
        log.error("error fetching %s: %s", url, e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select(".event")
    log.info("found %d events on %s", len(cards), source_name)

    events = []
    for card in cards:
        day_el = card.select_one(".tag")
        month_el = card.select_one(".monat")
        title_el = card.select_one(".event-titel b")
        time_el = card.select_one(".uhrzeit")
        location_el = card.select_one(".ort")

        if not day_el or not month_el or not title_el:
            continue

        title = title_el.get_text(strip=True)

        # Append organizer if present (text after <b> in the same <p>)
        p_el = card.select_one(".event-titel p")
        if p_el:
            organizer = p_el.get_text(strip=True).replace(title, "", 1).strip()
            if organizer:
                title = f"{title} | {organizer}"

        time_str = time_el.get_text(strip=True) if time_el else ""
        location = location_el.get_text(strip=True) if location_el else None
        if location and location in ("–", "-"):
            location = None

        day_text = day_el.get_text(strip=True)
        month_text = month_el.get_text(strip=True)
        start_date = parse_german_date(int(day_text), month_text)
        start_time = parse_time(time_str)
        end_time = parse_end_time(time_str)
        end_datetime = f"{start_date}T{end_time}" if start_date and end_time else None

        events.append(
            Event(
                source_name=source_name,
                base_url=base_url,
                source_url=url,
                event_title=title,
                start_date=start_date,
                start_time=start_time,
                end_datetime=end_datetime,
                location=location,
                description=None,
                extracted_at=extracted_at,
                priority=source["priority"],
            )
        )

    return events
