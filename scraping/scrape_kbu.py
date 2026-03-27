import requests
import re
import json
import urllib3
from datetime import datetime
from typing import Optional

urllib3.disable_warnings()

BASE_URL = "https://www.kbu.ch/treffpunkt/veranstaltungen/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
STRIP_TAGS = re.compile(r'<[^>]+>')
ISO_FMT = "%Y-%m-%dT%H:%M:%S"

CATEGORY_MAP = {
    "gelb-kinder": "Kinder",
    "rot-jugendliche": "Jugendliche",
    "hellblau-erwachsene": "Erwachsene",
    "blau-digitale-sprechstunde": "alle Altersgruppen",
}


def _parse_iso_datetime(date_str: str, time_str: str) -> Optional[str]:
    """Parse 'Do, 02.04.2026' + '16:00 Uhr' into ISO8601."""
    try:
        # Strip day abbreviation like 'Sa, '
        date_clean = re.sub(r'^[A-Za-z]+,\s*', '', date_str.strip())
        dt = datetime.strptime(date_clean, "%d.%m.%Y")
        if time_str:
            time_clean = time_str.replace("Uhr", "").strip()
            parts = time_clean.split(":")
            dt = dt.replace(hour=int(parts[0]), minute=int(parts[1]))
        return dt.strftime(ISO_FMT)
    except Exception:
        return None


def _parse_categories(tag_html: str) -> list[str]:
    """Extract audience categories from <hr class='...'> tags."""
    classes = re.findall(r'<hr class="([^"]+)">', tag_html)
    return [CATEGORY_MAP[c] for c in classes if c in CATEGORY_MAP]


def _fetch_detail_description(detail_url: str) -> str:
    """Fetch an event detail page and extract the description text."""
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code != 200:
            return ""
        match = re.search(
            r'<div class="news-text-wrap"[^>]*>(.*?)</div>\s*(?:<!--|\s*<div class="news-backlink)',
            resp.text, re.DOTALL
        )
        if not match:
            return ""
        raw = match.group(1)
        # Replace <br> and </p> with newlines, then strip tags
        text = re.sub(r'<br\s*/?>', '\n', raw)
        text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', text)
        text = STRIP_TAGS.sub('', text)
        text = text.replace('\xa0', ' ').replace('&nbsp;', ' ')
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    except Exception as e:
        print(f"  Error fetching detail: {e}")
        return ""


def parse_events_from_html(html: str) -> list[dict]:
    """Parse the KBU event listing page."""
    # Find the event list container
    match = re.search(r'<div class="row vk-list">(.*?)</div><!--TYPO3SEARCH_begin-->', html, re.DOTALL)
    if not match:
        return []
    content = match.group(1)

    events = []
    # Each event is an <a> block with title, date, time, and tags
    event_pattern = re.compile(
        r'<a\s+title="([^"]*?)"\s+href="([^"]*?)">'
        r'.*?<div class="news-latest-date">\s*(.*?)\s*</div>'
        r'.*?<div class="news-latest-time"><span>(.*?)</span></div>'
        r'.*?<h5>(.*?)</h5>'
        r'.*?<span class="news-list-tags"[^>]*>(.*?)</span>',
        re.DOTALL
    )

    for m in event_pattern.finditer(content):
        full_title = m.group(1).strip()
        detail_path = m.group(2).strip()
        date_str = m.group(3).strip()
        time_str = m.group(4).strip()
        categories = _parse_categories(m.group(6))

        # Extract news ID from URL for dedup
        id_match = re.search(r'news%5D=(\d+)', detail_path)
        event_id = id_match.group(1) if id_match else full_title

        detail_url = f"https://www.kbu.ch{detail_path.replace('&amp;', '&')}"

        events.append({
            "id": event_id,
            "title": full_title,
            "date": date_str,
            "time": time_str,
            "detail_url": detail_url,
            "categories": categories,
            "source": "kbu.ch",
        })

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "event_id": f"kbu-{event['id']}",
        "source_name": "kbu.ch",
        "source_url": event["detail_url"],
        "event_title": event["title"],
        "start_datetime": _parse_iso_datetime(event["date"], event["time"]),
        "end_datetime": None,
        "location": "Kantonsbibliothek Uri, Bahnhofstrasse 13, 6460 Altdorf",
        "description": event["description"],
        "category": None,
        "extracted_at": extracted_at,
    }


def fetch_events() -> list[dict]:
    """Fetch all events from kbu.ch."""
    print(f"Fetching: {BASE_URL}")
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}")
            return []
    except Exception as e:
        print(f"  Error: {e}")
        return []

    events = parse_events_from_html(resp.text)
    print(f"  Found {len(events)} events")

    # Fetch descriptions from detail pages
    for event in events:
        print(f"  Fetching detail: {event['title']}")
        event["description"] = _fetch_detail_description(event["detail_url"])

    return events


if __name__ == "__main__":
    events = fetch_events()
    extracted_at = datetime.utcnow().strftime(ISO_FMT)
    formatted = [_to_template(e, extracted_at) for e in events]
    print(f"\nTotal events: {len(formatted)}")
    output_path = "kbu_events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    print(f"Events saved to {output_path}")
