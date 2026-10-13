"""Scraper for OLG KTV Altdorf — orienteering club.

Scrapes two separate ClubDesk pages (Vereinstermine and Nachwuchstrainings),
deduplicates across them, and merges missing fields when the same event
appears on both pages with different detail levels.
"""

import logging
import re
import requests
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Two event pages under the same source
URL_VEREINSTERMINE = "https://olg-ktv-altdorf.ch/?b=100679&c=EL&s=djEtkrJnjCNrDOvXomfStWZErXne_tZfQj511si9KPLGr48="
URL_NACHWUCHS = "https://olg-ktv-altdorf.ch/?b=100407&c=EL&s=djEtCISATqYRa76C382Hl6w-P-C4e79Jo9gNoxgbgjfnwyI="
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}


def _parse_date_dmy(date_str: str) -> Optional[str]:
    """Parse 'DD.MM.YYYY' into 'YYYY-MM-DD'."""
    m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
    if m:
        return "%s-%s-%s" % (m.group(3), m.group(2), m.group(1))
    return None


def _parse_time_range(time_str: str) -> tuple:
    """Parse time from subheading. Returns (start_time, end_time) as HH:MM:SS or None."""
    if not time_str:
        return None, None
    # "ganztägig" or "Mehrtägig" = all-day
    if "ganztägig" in time_str.lower() or "mehrtägig" in time_str.lower():
        return None, None
    times = re.findall(r'(\d{1,2}):(\d{2})', time_str)
    start = "%02d:%s:00" % (int(times[0][0]), times[0][1]) if len(times) >= 1 else None
    end = "%02d:%s:00" % (int(times[1][0]), times[1][1]) if len(times) >= 2 else None
    return start, end


def _fetch(name: str, url: str) -> tuple[BeautifulSoup, int, str]:
    """GET one ClubDesk page.

    Network errors and non-200s propagate so the orchestrator retries
    (swallowing them turned a transient ClubDesk error into a filed issue).
    Returns the parsed page, its event tile count and a body snippet.
    """
    log.info("fetching %s: %s", name, url)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tiles = len(soup.select(".cd-tile-h-box"))
    log.info("%s: %d tiles", name, tiles)
    return soup, tiles, resp.text[:200].replace("\n", " ")


def _scrape_vereinstermine(soup: BeautifulSoup) -> list:
    """Parse the Vereinstermine page. Date+time are in the subheading."""
    tiles = soup.select(".cd-tile-h-box")

    events = []
    for tile in tiles:
        heading = tile.select_one(".cd-tile-h-main-heading")
        sub = tile.select_one(".cd-tile-h-main-subheading")
        title = heading.text.strip() if heading else ""
        sub_text = sub.text.strip() if sub else ""
        if not title:
            continue

        # Subheading format: "Mi 08.04.2026 16:30 - 19:00" or "Sa 18.04.2026 (ganztägig)"
        date = _parse_date_dmy(sub_text)
        start_time, end_time = _parse_time_range(sub_text)

        # Detail link from onclick (but detail pages 404, so just for source_url)
        onclick = tile.get("onclick", "")
        m = re.search(r"window\.location\.href='([^']+)'", onclick)
        detail_path = m.group(1) if m else ""
        detail_url = "https://olg-ktv-altdorf.ch%s" % detail_path if detail_path else URL_VEREINSTERMINE

        events.append({
            "title": title,
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "location": None,  # Page 1 doesn't have locations
            "detail_url": detail_url,
            "source_page": "vereinstermine",
        })

    return events


def _scrape_nachwuchs(soup: BeautifulSoup) -> list:
    """Parse the Nachwuchstrainings page. Dates are in <h3> headers above tiles."""
    # Walk through h3 (date headers) and tiles in document order
    events = []
    current_date = None
    for el in soup.find_all(["h3", "div"]):
        if el.name == "h3":
            # e.g. "Mittwoch 01.04.2026"
            current_date = _parse_date_dmy(el.text.strip())
            continue
        if "cd-tile-h-box" not in el.get("class", []):
            continue

        heading = el.select_one(".cd-tile-h-main-heading")
        sub = el.select_one(".cd-tile-h-main-subheading")
        loc_el = el.select_one(".cd-tile-h-detail-value")
        title = heading.text.strip() if heading else ""
        sub_text = sub.text.strip() if sub else ""
        location = loc_el.text.strip() if loc_el else None
        if not title:
            continue

        start_time, end_time = _parse_time_range(sub_text)

        onclick = el.get("onclick", "")
        m = re.search(r"window\.location\.href='([^']+)'", onclick)
        detail_path = m.group(1) if m else ""
        detail_url = "https://olg-ktv-altdorf.ch%s" % detail_path if detail_path else URL_NACHWUCHS

        events.append({
            "title": "%s (Nachwuchstrainings)" % title,
            "date": current_date,
            "start_time": start_time,
            "end_time": end_time,
            "location": location,
            "detail_url": detail_url,
            "source_page": "nachwuchs",
        })

    return events


def _dedup_key(event: dict) -> str:
    """Key for matching duplicates across pages: lowercase title root + date."""
    # Strip the (Nachwuchstrainings) suffix for matching
    title = re.sub(r'\s*\(Nachwuchstrainings\)\s*$', '', event["title"])
    return "%s|%s" % (title.lower().strip(), event.get("date") or "")


def fetch_events() -> list:
    """Fetch events from both pages, deduplicate, merge missing info."""
    v_soup, v_tiles, v_snippet = _fetch("Vereinstermine", URL_VEREINSTERMINE)
    n_soup, n_tiles, _ = _fetch("Nachwuchstrainings", URL_NACHWUCHS)

    # On 2026-06-17 ClubDesk served both pages as 200 without a single tile
    # while its calendar feed was answering 500.  Both pages empty is not a
    # real zero: fail so the orchestrator retries, with the page in the log.
    # One empty page on its own is fine (the trainings page has off-seasons).
    if v_tiles == 0 and n_tiles == 0:
        raise ValueError(f"no event tiles on either page: {v_snippet!r}")

    vereins = _scrape_vereinstermine(v_soup)
    nachwuchs = _scrape_nachwuchs(n_soup)

    # Index Vereinstermine events by dedup key — these are the base
    merged = {}
    for ev in vereins:
        key = _dedup_key(ev)
        merged[key] = ev

    # Add Nachwuchs events, merging info into Vereinstermine dupes
    for ev in nachwuchs:
        key = _dedup_key(ev)
        if key in merged:
            # Duplicate — fill in missing fields from Nachwuchs
            base = merged[key]
            if not base["location"] and ev["location"]:
                base["location"] = ev["location"]
            if not base["start_time"] and ev["start_time"]:
                base["start_time"] = ev["start_time"]
            if not base["end_time"] and ev["end_time"]:
                base["end_time"] = ev["end_time"]
            # Keep Vereinstermine title and detail_url
        else:
            # Unique to Nachwuchs — add with suffix
            merged[key] = ev

    result = list(merged.values())
    log.info("merged: %d events (%d vereins + %d nachwuchs, %d after dedup)",
             len(result), len(vereins), len(nachwuchs), len(result))
    return result


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_url": event["detail_url"],
        "event_title": event["title"],
        "start_date": event["date"],
        "start_time": event["start_time"],
        "end_datetime": None,
        "location": event["location"],
        "description": None,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    formatted = [_to_template(e, extracted_at) for e in events]
    print(json.dumps(formatted, ensure_ascii=False, indent=2))
