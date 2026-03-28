import logging
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from typing import Optional

log = logging.getLogger(__name__)

BASE_URL = "http://www.floorballuri.ch"
SOURCE_NAME = "floorballuri.ch"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# DD.MM.YYYY at the start of a <strong> tag
DATE_RE = re.compile(r'^(\d{2})\.(\d{2})\.(\d{4})')
# HH:MM Uhr
TIME_RE = re.compile(r'(\d{1,2}):(\d{2})\s*Uhr')
# Score like 9:5 or 3:2 (past game — skip)
SCORE_RE = re.compile(r'\b\d+:\d+\b')


def _parse_date(text: str) -> Optional[str]:
    m = DATE_RE.match(text.strip())
    if not m:
        return None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def _parse_time(text: str) -> Optional[str]:
    m = TIME_RE.search(text)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}:00"


def _fetch_page(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log.warning("fetch failed %s: %s", url, e)
        return None


def _parse_games(page_html: str, page_url: str) -> list[dict]:
    """Extract upcoming games from a meisterschaft page."""
    soup = BeautifulSoup(page_html, "html.parser")
    today = date.today()
    events = []

    for p in soup.find_all("p"):
        strong = p.find("strong")
        if not strong:
            continue

        start_date = _parse_date(strong.get_text())
        if not start_date:
            continue

        # Skip past games (they contain a score like "9:5")
        p_text = p.get_text(" ", strip=True)
        if SCORE_RE.search(p_text):
            continue

        # Skip dates in the past
        try:
            if datetime.strptime(start_date, "%Y-%m-%d").date() < today:
                continue
        except ValueError:
            continue

        # Title: everything after the date+competition label in <strong>
        strong_text = strong.get_text(" ", strip=True)
        # The <strong> contains "DD.MM.YYYY Competition label" — strip the date portion
        title_label = DATE_RE.sub("", strong_text).strip(" –-/")

        # Team matchup is the next text node / line after <strong>
        lines = [ln.strip() for ln in p_text.splitlines() if ln.strip()]
        matchup = None
        for line in lines:
            if DATE_RE.match(line) or line == strong_text:
                continue
            if TIME_RE.search(line):
                break
            matchup = line
            break

        title = matchup or title_label or "Floorball Uri"

        start_time = _parse_time(p_text)

        # Location: text after "|" on the time line
        location = None
        time_line_m = re.search(r'\d{1,2}:\d{2}\s*Uhr\s*\|?\s*(.+)', p_text)
        if time_line_m:
            location = time_line_m.group(1).strip().rstrip(".")

        # Detail link
        link_el = p.find("a", href=True)
        if link_el:
            href = link_el["href"]
            detail_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        else:
            detail_url = page_url

        events.append({
            "title": title,
            "start_date": start_date,
            "start_time": start_time,
            "end_datetime": None,
            "location": location,
            "detail_url": detail_url,
        })

    return events


def fetch_events(url: str = f"{BASE_URL}/meisterschaft-2025-26") -> list[dict]:
    log.info("fetching %s", url)
    html = _fetch_page(url)
    if not html:
        return []

    events = _parse_games(html, url)
    log.info("found %d upcoming games", len(events))
    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_name": SOURCE_NAME,
        "base_url": BASE_URL,
        "source_url": event["detail_url"],
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event["start_time"],
        "end_datetime": event["end_datetime"],
        "location": event["location"],
        "description": None,
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    extracted_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    raw = fetch_events()
    formatted = [_to_template(e, extracted_at) for e in raw]
    log.info("total events: %d", len(formatted))
    print(json.dumps(formatted, ensure_ascii=False, indent=2))
