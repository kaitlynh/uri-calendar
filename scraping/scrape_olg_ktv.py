import logging
import re
import requests
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Two event pages under the same source
URL_VEREINSTERMINE = "https://olg-ktv-altdorf.ch/?b=100679&c=EL&s=djEtkrJnjCNrDOvXomfStWZErXne_tZfQj511si9KPLGr48="
URL_NACHWUCHS = "https://olg-ktv-altdorf.ch/?b=100407&c=EL&s=djEtCISATqYRa76C382Hl6w-P-C4e79Jo9gNoxgbgjfnwyI="
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


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


def _scrape_vereinstermine() -> list:
    """Scrape the Vereinstermine page. Date+time are in the subheading."""
    log.info("fetching Vereinstermine: %s", URL_VEREINSTERMINE)
    try:
        resp = requests.get(URL_VEREINSTERMINE, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s for Vereinstermine", resp.status_code)
            return []
    except Exception as e:
        log.error("error fetching Vereinstermine: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    tiles = soup.select(".cd-tile-h-box")
    log.info("Vereinstermine: %d tiles", len(tiles))

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


def _scrape_nachwuchs() -> list:
    """Scrape the Nachwuchstrainings page. Dates are in <h3> headers above tiles."""
    log.info("fetching Nachwuchstrainings: %s", URL_NACHWUCHS)
    try:
        resp = requests.get(URL_NACHWUCHS, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s for Nachwuchs", resp.status_code)
            return []
    except Exception as e:
        log.error("error fetching Nachwuchs: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

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
    vereins = _scrape_vereinstermine()
    nachwuchs = _scrape_nachwuchs()

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
