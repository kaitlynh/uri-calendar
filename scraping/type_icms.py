"""ICMS CMS scraper type — used by municipalities running the ICMS platform.

Parses event cards with CSS classes: .event, .tag, .monat, .event-titel,
.uhrzeit, .ort. Handles German month abbreviations and Swiss time formats.
"""

import logging
import re
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

MONTHS_DE = {
    "Jan.": 1, "Feb.": 2, "Marz": 3, "März": 3, "Apr.": 4,
    "Mai": 5, "Juni": 6, "Juli": 7, "Aug.": 8,
    "Sep.": 9, "Sept.": 9, "Okt.": 10, "Nov.": 11, "Dez.": 12,
}


def _parse_date(day_str: str, month_str: str) -> Optional[str]:
    """Parse day + German month abbreviation into YYYY-MM-DD, inferring year."""
    try:
        day = int(day_str.strip())
        month = MONTHS_DE.get(month_str.strip())
        if not month:
            return None
        today = date.today()
        year = today.year
        if date(year, month, day) < today.replace(day=1):
            year += 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        return None


def _parse_time(time_str: str) -> Optional[str]:
    """Extract start time from '13.30 - 14.15 Uhr' or '19.00 Uhr'."""
    if not time_str or time_str.strip() in ("–", "-", ""):
        return None
    m = re.search(r"(\d{1,2})[.:](\d{2})", time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


def _parse_end_time(time_str: str) -> Optional[str]:
    """Extract end time from '13.30 - 14.15 Uhr'."""
    if not time_str:
        return None
    m = re.search(r"\d{1,2}[.:]\d{2}\s*-\s*(\d{1,2})[.:](\d{2})", time_str)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}:00"
    return None


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

        start_date = _parse_date(day_el.get_text(strip=True), month_el.get_text(strip=True))
        start_time = _parse_time(time_str)
        end_time = _parse_end_time(time_str)
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
