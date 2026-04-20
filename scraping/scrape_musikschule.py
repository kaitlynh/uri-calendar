"""Scraper for Musikschule Uri — the cantonal music school.

Parses concert and recital listings from the school's events page.
Uses parse_utils for Swiss German date/time formats.
"""

import logging
import re
import json
import urllib3
import requests
from datetime import datetime, timezone
from typing import Optional

urllib3.disable_warnings()

from parse_utils import parse_german_date_string, parse_time

log = logging.getLogger(__name__)

BASE_URL = "https://www.musikschule-uri.ch/events-news/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}
STRIP_TAGS = re.compile(r'<[^>]+>')
ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def _extract_location(h3_text: str) -> str:
    """Extract location from the h3 subtitle (usually the second line)."""
    lines = [l.strip() for l in h3_text.split('\n') if l.strip()]
    # Location is typically the line without a date
    for line in lines:
        if not re.search(r'\d{1,2}[.:]\d{2}[.:]\d{4}|\d{1,2}\.\s*[A-Z].*\d{4}|\d{1,2}:\d{2}\s*Uhr', line):
            # Strip day names
            line = re.sub(r'^(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),?\s*', '', line)
            if line and not re.match(r'^\d', line):
                return line
    return "Musikschule Uri, Bahnhofstrasse 27, 6460 Altdorf"


def parse_events_from_html(html: str) -> list[dict]:
    """Parse events from the Musikschule Uri events page."""
    events = []

    # Each event is an <article> with a post ID
    articles = re.finditer(
        r'<article class="[^"]*post-entry-type-standard[^"]*".*?</article>',
        html, re.DOTALL
    )

    for article_match in articles:
        article_html = article_match.group(0)
        # Extract post ID
        id_match = re.search(r'post-entry-(\d+)', article_html)
        post_id = id_match.group(1) if id_match else ""

        # Find the text block with event details
        textblock = re.search(
            r'<div class="avia_textblock\s*"\s*itemprop="text">(.*?)</div></section>',
            article_html, re.DOTALL
        )
        if not textblock:
            continue

        content = textblock.group(1)

        # Title from <h2>
        title_match = re.search(r'<h2>(.*?)</h2>', content)
        title = STRIP_TAGS.sub('', title_match.group(1)).strip() if title_match else ""

        # Date/time/location from <h3>
        h3_match = re.search(r'<h3>(.*?)</h3>', content, re.DOTALL)
        h3_text = ""
        if h3_match:
            h3_text = STRIP_TAGS.sub('', h3_match.group(1).replace('<br />', '\n').replace('<br>', '\n')).strip()

        start_date = parse_german_date_string(h3_text)
        start_time = parse_time(h3_text)
        location = _extract_location(h3_text)

        # Description from <p> tags (skip download links)
        desc_parts = []
        for p_match in re.finditer(r'<p>(.*?)</p>', content, re.DOTALL):
            p_text = STRIP_TAGS.sub('', p_match.group(1)).strip()
            p_text = p_text.replace('\xa0', ' ').replace('&nbsp;', ' ')
            if p_text and 'link-icon-download' not in p_match.group(1):
                desc_parts.append(p_text)
        description = '\n\n'.join(desc_parts)

        # Skip past events (no future date found)
        if not start_date:
            continue

        # Skip events in the past
        try:
            event_date = datetime.strptime(start_date, "%Y-%m-%d")
            if event_date < datetime.today().replace(hour=0, minute=0, second=0, microsecond=0):
                continue
        except Exception:
            pass

        events.append({
            "id": post_id,
            "title": title,
            "start_date": start_date,
            "start_time": start_time,
            "location": location,
            "description": description,
            "source": "musikschule-uri.ch",
        })

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "event_id": f"musikschule-{event['id']}",
        "source_name": "musikschule-uri.ch",
        "base_url": BASE_URL,
        "source_url": BASE_URL,
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event["start_time"],
        "end_datetime": None,
        "location": event["location"],
        "description": event["description"],
        "extracted_at": extracted_at,
    }


def fetch_events() -> list[dict]:
    """Fetch all events from musikschule-uri.ch."""
    log.info("fetching %s", BASE_URL)
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code != 200:
            log.warning("HTTP %s", resp.status_code)
            return []
    except Exception as e:
        log.error("error: %s", e)
        return []

    events = parse_events_from_html(resp.text)
    log.info("found %d upcoming events", len(events))
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).strftime(ISO_FMT)
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    output_path = "../events/musikschule_events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("events saved to %s", output_path)
