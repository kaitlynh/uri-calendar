"""Scraper for Gemeinde Schattdorf — municipality event listing."""

import logging
import requests

from bs4 import BeautifulSoup

from parse_utils import parse_german_date_string, parse_time

log = logging.getLogger(__name__)

URL = "https://schattdorf.ch/erleben/veranstaltungen"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch_events() -> list:
    """Fetch all events from schattdorf.ch/erleben/veranstaltungen."""
    log.info("fetching %s", URL)
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s", resp.status_code)
            return []
    except Exception as e:
        log.error("error: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("div.event")
    log.info("found %d events", len(cards))

    events = []
    for card in cards:
        title_el = card.select_one(".event__title h4")
        date_el = card.select_one(".event__date p.text--bold")
        time_els = card.select(".event__date p.text__base:not(.text--bold)")
        location_el = card.select_one(".event__location p")

        title = title_el.get_text(strip=True) if title_el else ""
        date_str = date_el.get_text(strip=True) if date_el else ""
        time_str = time_els[0].get_text(strip=True) if time_els else ""
        location = location_el.get_text(strip=True) if location_el else None

        if not title:
            continue

        events.append({
            "title": title,
            "date": date_str,
            "time": time_str,
            "location": location,
        })

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_url": URL,
        "event_title": event["title"],
        "start_date": parse_german_date_string(event["date"]),
        "start_time": parse_time(event.get("time", "").replace('\xa0', ' ')),
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
