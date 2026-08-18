"""Scraper for Cinema Leuzinger, Altdorf.

The programme page lists every currently scheduled film as a card carrying
both the film's metadata and all of its showtimes, so a single request
covers the whole programme — no per-film detail fetches needed.

    .program-movie-card
        .program-movie-title  → title + link to /film/<slug>
        .program-meta span    → genre, language, age rating, duration
        .program-desc         → synopsis
        .program-showtime     → one per showing; the ticket link carries
                                the full date and time

Film metadata is read from the page's schema.org ItemList (explicit keys)
and falls back to the meta spans, which are classified by pattern rather
than position — "demnächst" cards omit language and age rating.

Source: https://cinema-leuzinger.ch/programm
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL = "https://cinema-leuzinger.ch"
PROGRAM_URL = f"{BASE_URL}/programm"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}
LOCATION = "Cinema Leuzinger, Altdorf"

# "/ticketreservation#!/Seats/id:876/date:19.08.2026/time:15:30"
TICKET_RE = re.compile(r"date:(\d{2})\.(\d{2})\.(\d{4}).*?time:(\d{1,2}):(\d{2})")
DURATION_RE = re.compile(r"^\d+\s*Min", re.IGNORECASE)
AGE_RATING_RE = re.compile(r"^(ab\s*)?\d+\s*Jahre|^ohne\s+alters", re.IGNORECASE)


def _film_metadata(soup: BeautifulSoup) -> dict:
    """Map film URL → schema.org Movie fields from the page's JSON-LD."""
    metadata = {}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if data.get("@type") != "ItemList":
            continue
        for entry in data.get("itemListElement", []):
            movie = entry.get("item", {})
            url = movie.get("url")
            if url:
                metadata[url.rstrip("/")] = movie
    return metadata


def _classify_meta(spans: list[str], language: str | None) -> dict:
    """Sort the meta spans into genre / language / age rating / duration.

    Classified by pattern, not position: cards for films without a
    scheduled run carry only a subset of the fields.
    """
    fields = {}
    rest = []
    for span in spans:
        if DURATION_RE.match(span):
            fields["duration"] = span
        elif AGE_RATING_RE.match(span):
            fields["age_rating"] = span
        elif language and span == language:
            fields["language"] = span
        else:
            rest.append(span)

    # Whatever is left is the genre, plus the language when JSON-LD had none
    if rest:
        fields["genre"] = rest[0]
    if "language" not in fields and len(rest) > 1:
        fields["language"] = rest[1]
    return fields


def _showtime(link, fallback_year: int) -> tuple[str, str] | None:
    """Read (date, time) off a showtime link, or None if it can't be dated.

    The ticket link carries an unambiguous DD.MM.YYYY; the visible label
    ("Mi, 19.08." / "15:30") is the fallback and needs a year inferred.
    """
    m = TICKET_RE.search(link.get("href") or "")
    if m:
        day, month, year, hour, minute = m.groups()
        return f"{year}-{month}-{day}", f"{int(hour):02d}:{minute}:00"

    date_el = link.select_one(".program-showtime-date")
    hour_el = link.select_one(".program-showtime-hour")
    if not date_el or not hour_el:
        return None

    date_m = re.search(r"(\d{1,2})\.(\d{1,2})\.", date_el.get_text(strip=True))
    hour_m = re.search(r"(\d{1,2}):(\d{2})", hour_el.get_text(strip=True))
    if not date_m or not hour_m:
        return None

    day, month = int(date_m.group(1)), int(date_m.group(2))
    try:
        # A month already past belongs to next year's programme
        year = fallback_year + 1 if month < date.today().month else fallback_year
        return (
            date(year, month, day).isoformat(),
            f"{int(hour_m.group(1)):02d}:{hour_m.group(2)}:00",
        )
    except ValueError:
        return None


def fetch_events() -> list[dict]:
    """Fetch every scheduled showing from the programme page."""
    log.info("fetching %s", PROGRAM_URL)
    resp = requests.get(PROGRAM_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    metadata = _film_metadata(soup)
    this_year = date.today().year

    showings = []
    for card in soup.select(".program-movie-card"):
        title_el = card.select_one(".program-movie-title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        # The CMS stores titles in ALL CAPS — convert to title case, checking
        # the words outside parentheses so mixed-case suffixes survive
        # (e.g. "... (Vorpremiere)").
        core = re.sub(r"\([^)]*\)", "", title).strip()
        if core and core == core.upper():
            title = title.title()

        link = title_el.get("href", "")
        film = metadata.get(f"{BASE_URL}{link}".rstrip("/"), {})

        details = _classify_meta(
            [s.get_text(strip=True) for s in card.select(".program-meta span")],
            film.get("inLanguage"),
        )
        desc_el = card.select_one(".program-desc")
        details["description"] = film.get("description") or (
            desc_el.get_text(strip=True) if desc_el else ""
        )

        times = card.select(".program-showtime")
        for showtime_link in times:
            parsed = _showtime(showtime_link, this_year)
            if not parsed:
                log.warning("undatable showtime for %s — skipped", title)
                continue
            start_date, start_time = parsed
            showings.append({
                "title": title,
                "link": link,
                "start_date": start_date,
                "start_time": start_time,
                "details": details,
            })

        log.info("%s: %d showings", title, len(times))

    log.info("total showings: %d", len(showings))
    return showings


def _to_template(event: dict, extracted_at: str) -> dict:
    details = event.get("details", {})

    # Build description from film metadata
    desc_lines = []
    for key in ("genre", "language", "duration"):
        if details.get(key):
            desc_lines.append(details[key])
    if details.get("age_rating"):
        desc_lines.append(details["age_rating"])

    story = details.get("description", "")
    if story:
        desc_lines.append("")  # blank line before story
        desc_lines.append(story)
    description = "\n".join(desc_lines)

    source_url = f"{BASE_URL}{event['link']}" if event.get("link") else BASE_URL

    return {
        "source_url": source_url,
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event["start_time"],
        "end_datetime": None,
        "location": LOCATION,
        "description": description,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).isoformat()
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    with open("../events/cinema_leuzinger_events.json", "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("saved to ../events/cinema_leuzinger_events.json")
