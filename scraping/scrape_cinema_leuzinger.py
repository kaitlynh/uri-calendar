"""Scraper for Cinema Leuzinger, Altdorf.

Scrapes the kinoprogramm listing page for all upcoming showings, then fetches
unique movie detail pages for genre, duration, language, and description.

Source: https://www.cinema-leuzinger.ch/index.php/kinoprogramm
"""
from __future__ import annotations

import logging
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

log = logging.getLogger(__name__)

LISTING_URL = "https://www.cinema-leuzinger.ch/index.php/kinoprogramm"
BASE_URL = "https://www.cinema-leuzinger.ch"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}
ITEMS_PER_PAGE = 14
LOCATION = "Cinema Leuzinger, Altdorf"


def _parse_listing_page(html: str) -> list[dict]:
    """Parse showings from a kinoprogramm listing page."""
    items = re.findall(
        r'<article class="item-view blog-view">(.*?)</article>',
        html, re.DOTALL,
    )
    showings = []
    for item in items:
        title_m = re.search(r'class="item-title"[^>]*>\s*<a[^>]*>(.*?)</a>', item, re.DOTALL)
        time_m = re.search(r'<time datetime="([^"]+)"', item)
        link_m = re.search(r'class="item-title"[^>]*>\s*<a href="([^"]+)"', item)

        if not title_m or not time_m:
            continue

        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        # Cinema CMS stores titles in ALL CAPS — convert to title case.
        # Some titles have mixed-case suffixes in parens (e.g. "Vorpremiere")
        # so we check the words outside parentheses.
        core = re.sub(r'\([^)]*\)', '', title).strip()
        if core and core == core.upper():
            title = title.title()
        # datetime attribute has +00:00 but values are actually local Zurich time (CMS bug)
        dt_str = time_m.group(1)
        link = link_m.group(1) if link_m else ""

        # Extract the movie slug for grouping (e.g. "hoppers" from "13821-hoppers")
        slug_m = re.search(r'/item/\d+-(.+)$', link)
        movie_slug = slug_m.group(1) if slug_m else title.lower()

        showings.append({
            "title": title,
            "datetime_raw": dt_str,
            "link": link,
            "movie_slug": movie_slug,
        })

    return showings


def _parse_datetime(dt_str: str) -> tuple[str | None, str | None]:
    """Parse the datetime attribute into (date, time).

    The +00:00 offset is a CMS bug — times are actually local Zurich time.
    We strip the offset and use the time value as-is.
    """
    # "2026-04-03T16:00:00+00:00" -> date=2026-04-03, time=16:00:00
    if "T" not in dt_str:
        return dt_str[:10], None
    date_part, rest = dt_str.split("T", 1)
    # Strip timezone offset
    time_part = re.sub(r'[+-]\d{2}:\d{2}$', '', rest)[:8]
    return date_part, time_part


def _fetch_movie_details(detail_path: str) -> dict:
    """Fetch a movie detail page for genre, duration, language, and description."""
    url = f"{BASE_URL}{detail_path}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
    except Exception as e:
        log.warning("error fetching detail %s: %s", url, e)
        return {}

    html = resp.text
    details = {}

    # Extra fields: <dt>Genre:</dt><dd>...</dd>
    pairs = re.findall(r'<dt>(.*?)</dt>\s*<dd>(.*?)</dd>', html, re.DOTALL)
    for dt, dd in pairs:
        key = re.sub(r'<[^>]+>', '', dt).strip().rstrip(':')
        val = re.sub(r'<[^>]+>', '', dd).strip()
        if key == "Genre":
            details["genre"] = val
        elif key == "Dauer":
            details["duration"] = val
        elif key == "Sprache":
            details["language"] = val
        elif key == "Story":
            details["description"] = val
        elif key == "Altersfreigabe":
            details["age_rating"] = val

    return details


def fetch_events() -> list[dict]:
    """Fetch all showings from the kinoprogramm listing, with movie details."""
    all_showings = []
    start = 0

    # Paginate through listing
    while True:
        url = LISTING_URL if start == 0 else f"{LISTING_URL}/itemlist?start={start}"
        log.info("fetching %s", url)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                log.warning("HTTP %s for %s", resp.status_code, url)
                break
        except Exception as e:
            log.error("error: %s", e)
            break

        showings = _parse_listing_page(resp.text)
        if not showings:
            break

        all_showings.extend(showings)
        log.info("page at start=%d: %d showings", start, len(showings))

        # Check for next page
        has_next = f"start={start + ITEMS_PER_PAGE}" in resp.text
        if not has_next:
            break
        start += ITEMS_PER_PAGE

    log.info("total showings: %d", len(all_showings))

    # Fetch movie details for unique movies (concurrent)
    unique_movies = {}  # movie_slug -> first link
    for s in all_showings:
        if s["movie_slug"] not in unique_movies:
            unique_movies[s["movie_slug"]] = s["link"]

    log.info("fetching details for %d unique movies", len(unique_movies))
    movie_details = {}  # movie_slug -> details dict
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_slug = {
            executor.submit(_fetch_movie_details, link): slug
            for slug, link in unique_movies.items()
        }
        for future in as_completed(future_to_slug):
            slug = future_to_slug[future]
            movie_details[slug] = future.result()

    # Attach details to showings
    for s in all_showings:
        s["details"] = movie_details.get(s["movie_slug"], {})

    return all_showings


def _to_template(event: dict, extracted_at: str) -> dict:
    start_date, start_time = _parse_datetime(event["datetime_raw"])
    details = event.get("details", {})

    # Build description from movie metadata
    desc_lines = []
    if details.get("genre"):
        desc_lines.append(details["genre"])
    if details.get("language"):
        desc_lines.append(details["language"])
    if details.get("duration"):
        desc_lines.append(details["duration"])
    if details.get("age_rating"):
        desc_lines.append(f"Ab {details['age_rating']}")

    story = details.get("description", "")
    if story:
        desc_lines.append("")  # blank line before story
        desc_lines.append(story)
    description = "\n".join(desc_lines)

    source_url = f"{BASE_URL}{event['link']}" if event.get("link") else BASE_URL

    return {
        "source_url": source_url,
        "event_title": event["title"],
        "start_date": start_date,
        "start_time": start_time,
        "end_datetime": None,
        "location": LOCATION,
        "description": description,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).isoformat()
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    with open("../events/cinema_leuzinger_events.json", "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("saved to ../events/cinema_leuzinger_events.json")
