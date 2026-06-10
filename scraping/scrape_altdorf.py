"""Scraper for Gemeinde Altdorf — the cantonal capital.

Altdorf relaunched their website in May 2026 (Craft CMS, apex domain
without www).  Events are server-rendered as cards on a single listing
page, one card per occurrence — recurring events repeat with different
dates but share a detail page.  We parse the cards, then fetch each
unique detail page in parallel for start times, venue addresses, and
descriptions.

Like other aggregator scrapers, we filter out events that belong to
sources we scrape directly (Cinema Leuzinger, KBU, OL, Theater Uri).
"""

import html
import logging
import re
import requests
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

BASE_URL = "https://altdorf.ch/aktuelles/veranstaltungen"
DETAIL_BASE = "https://altdorf.ch"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}
STRIP_TAGS = re.compile(r'<[^>]+>')
ISO_FMT = "%Y-%m-%dT%H:%M:%S"

# German month names (cards use full names, teasers abbreviate) → month number
MONTHS = {
    "jan": 1, "feb": 2, "mär": 3, "maer": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12,
}

# One listing card per occurrence: class attr, then data-* attrs, then body
CARD_RE = re.compile(
    r'<div\s+class="grid\s+col cols-1 event-item'
    r'.*?(?=<div\s+class="grid\s+col cols-1 event-item|$)',
    re.DOTALL,
)
DATE_SPAN_RE = re.compile(r'<span class="(day|month|year)">\s*([^<]+?)\s*</span>')
TIME_RE = re.compile(r'<span class="time">\s*(\d{1,2})[:.](\d{2})')


def _parse_german_date(day: str, month: str, year: str) -> Optional[str]:
    """Convert e.g. ('12.', 'Juni', '2026') to '2026-06-12'."""
    month_num = MONTHS.get(month.strip(". ").lower()[:3])
    if not month_num:
        return None
    try:
        return f"{int(year):04d}-{month_num:02d}-{int(day.strip('. ')):02d}"
    except ValueError:
        return None


def _clean_text(raw: str) -> str:
    """Strip tags from an HTML fragment, keeping paragraph breaks."""
    text = re.sub(r'<br\s*/?>', '\n', raw)
    text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', text)
    text = STRIP_TAGS.sub('', text)
    text = html.unescape(text).replace('\xa0', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _fetch_detail_info(detail_url: str) -> dict:
    """Fetch an event detail page and extract time, location, and description."""
    result = {"description": "", "start_time": None, "location": None}
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return result

        # Start time sits in the large date block (not in related-event teasers)
        datum_match = re.search(
            r'<div class="event-detail-datum">(.*?)</div>\s*</div>',
            resp.text, re.DOTALL
        )
        if datum_match:
            time_match = TIME_RE.search(datum_match.group(1))
            if time_match:
                result["start_time"] = f"{int(time_match.group(1)):02d}:{time_match.group(2)}:00"

        # "Ort" block: <p>Venue</p> <p>Street</p> <p>ZIP [Town]</p>
        ort_match = re.search(
            r'class="[^"]*\bort\b[^"]*"[^>]*>\s*<div[^>]*>(.*?)</div>',
            resp.text, re.DOTALL
        )
        if ort_match:
            paragraphs = [_clean_text(p) for p in re.findall(r'<p[^>]*>(.*?)</p>', ort_match.group(1), re.DOTALL)]
            paragraphs = [p for p in paragraphs if p]
            venue = paragraphs[0] if paragraphs else None
            town = None
            for p in paragraphs[1:]:
                zip_match = re.match(r'(\d{4})\s*(.*)', p)
                if zip_match:
                    town = zip_match.group(2).strip() or ("Altdorf" if zip_match.group(1) == "6460" else None)
            if venue and town:
                result["location"] = f"{venue}, {town}"
            else:
                result["location"] = venue

        desc_match = re.search(
            r'<div class="event-description[^"]*">\s*<h3[^>]*>[^<]*</h3>(.*?)</div>',
            resp.text, re.DOTALL
        )
        if desc_match:
            result["description"] = _clean_text(desc_match.group(1))

        return result
    except Exception as e:
        log.warning("error fetching detail %s: %s", detail_url, e)
        return result


def parse_events_from_html(page_html: str) -> list[dict]:
    """Parse occurrence cards from the altdorf.ch events listing page."""
    cards = CARD_RE.findall(page_html)
    if not cards:
        log.warning("could not find any event-item cards")
        return []

    events = []
    for card in cards:
        section_m = re.search(r'data-section="([^"]*)"', card)
        if section_m and section_m.group(1) != "veranstaltungen":
            continue

        title_m = re.search(r'data-title="([^"]*)"', card)
        title = html.unescape(title_m.group(1)).strip() if title_m else ""

        href_m = re.search(r'<a href="([^"]+)"[^>]*class="overall-link"', card)
        detail_url = href_m.group(1).split("?")[0] if href_m else None

        date_parts = dict(DATE_SPAN_RE.findall(card))
        start_date = None
        if {"day", "month", "year"} <= date_parts.keys():
            start_date = _parse_german_date(date_parts["day"], date_parts["month"], date_parts["year"])

        venue_m = re.search(r'<p class="small mt-0-5">\s*([^<]*?)\s*</p>', card)
        venue = html.unescape(venue_m.group(1)) if venue_m else ""

        teaser_m = re.search(r'data-content="([^"]*)"', card)
        teaser = html.unescape(teaser_m.group(1)).strip() if teaser_m else ""

        if not title or not start_date or not detail_url:
            continue

        events.append({
            "title": title,
            "start_date": start_date,
            "location": venue or None,
            "detail_url": detail_url,
            "teaser": teaser,
        })

    return events


def _is_kino(event: dict) -> bool:
    """Detect cinema listings — these are scraped directly from cinema-leuzinger.ch."""
    title = event.get("title", "")
    if title.startswith("Kino:") or title.startswith("Kino "):
        return True
    location = event.get("location") or ""
    if re.search(r"(?i)cinema\s+leuzinger|kino\s+leuzinger", location):
        return True
    return False


def _is_kbu(event: dict) -> bool:
    """Detect library events — these are scraped directly from kbu.ch."""
    location = event.get("location") or ""
    return bool(re.search(r"(?i)kantonsbibliothek", location))


def _is_ol(event: dict) -> bool:
    """Detect OL events — these are scraped directly from olg-ktv-altdorf.ch."""
    title = event.get("title", "")
    return bool(re.search(r"(?i)OL-Cup|OLG\b|Orientierungslauf", title))


def _is_theater_uri(event: dict) -> bool:
    """Detect Theater Uri events — these are scraped directly from theater-uri.ch."""
    location = event.get("location") or ""
    title = event.get("title", "")
    return bool(re.search(r"(?i)theater\s+uri", location) or
                re.search(r"(?i)theater\s+uri", title))


def _to_template(event: dict, extracted_at: str) -> dict:
    slug = event["detail_url"].rstrip("/").rsplit("/", 1)[-1]
    return {
        "event_id": f"altdorf-{slug}-{event['start_date']}",
        "source_name": "altdorf.ch",
        "base_url": BASE_URL,
        "source_url": event["detail_url"],
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event.get("start_time"),
        "end_datetime": None,
        "location": event["location"],
        "description": event.get("description") or event.get("teaser", ""),
        "extracted_at": extracted_at,
    }


def fetch_events() -> list[dict]:
    """Fetch all events from altdorf.ch."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    log.info("fetching %s", BASE_URL)
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    events = parse_events_from_html(resp.text)
    log.info("parsed %d occurrence cards", len(events))

    # Fetch unique detail pages in parallel for time, address, description
    detail_urls = sorted({e["detail_url"] for e in events})
    log.info("fetching %d detail pages in parallel", len(detail_urls))
    details = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_url = {
            executor.submit(_fetch_detail_info, url): url
            for url in detail_urls
        }
        for future in as_completed(future_to_url):
            details[future_to_url[future]] = future.result()

    for event in events:
        info = details.get(event["detail_url"], {})
        event["start_time"] = info.get("start_time")
        event["description"] = info.get("description", "")
        # Detail-page location includes the town; fall back to the card venue
        if info.get("location"):
            event["location"] = info["location"]

    # Filter out events scraped from direct sources
    before = len(events)
    events = [e for e in events if not _is_kino(e)]
    skipped_kino = before - len(events)
    if skipped_kino:
        log.info("skipped %d kino events (scraped from cinema-leuzinger.ch)", skipped_kino)
    before = len(events)
    events = [e for e in events if not _is_kbu(e)]
    skipped_kbu = before - len(events)
    if skipped_kbu:
        log.info("skipped %d KBU events (scraped from kbu.ch)", skipped_kbu)
    before = len(events)
    events = [e for e in events if not _is_ol(e)]
    skipped_ol = before - len(events)
    if skipped_ol:
        log.info("skipped %d OL events (scraped from olg-ktv-altdorf.ch)", skipped_ol)
    before = len(events)
    events = [e for e in events if not _is_theater_uri(e)]
    skipped_theater = before - len(events)
    if skipped_theater:
        log.info("skipped %d Theater Uri events (scraped from theater-uri.ch)", skipped_theater)

    log.info("done: %d events from altdorf.ch", len(events))
    return events


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).strftime(ISO_FMT)
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    output_path = "../events/altdorf_events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("events saved to %s", output_path)
