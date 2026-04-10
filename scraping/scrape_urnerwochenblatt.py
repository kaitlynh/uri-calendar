import logging
import requests
import re
import json
import urllib3
from datetime import datetime, timedelta, timezone
from typing import Optional

urllib3.disable_warnings()

log = logging.getLogger(__name__)

BASE_URL = "https://www.urnerwochenblatt.ch/veranstaltungen/"  # Events listing page — used for fetching and as base_url in output
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
STRIP_TAGS = re.compile(r'<[^>]+>')
ISO_FMT = "%Y-%m-%dT%H:%M:%S"

from parse_utils import parse_german_date_string, parse_time


def _parse_start_time(time_part: str) -> Optional[str]:
    """Extract start time from 'HH.MM–HH.MM Uhr' or 'HH.MM Uhr'."""
    if not time_part:
        return None
    start = time_part.split("–")[0].replace("Uhr", "").strip()
    return parse_time(start)


def _parse_end_datetime(start_date: Optional[str], time_str: str) -> Optional[str]:
    """Build end ISO datetime from end time in 'HH.MM–HH.MM Uhr' range."""
    if not start_date or "–" not in time_str:
        return None
    try:
        end_part = time_str.split("–")[1].replace("Uhr", "").strip()
        end_time = parse_time(end_part)
        if end_time:
            return f"{start_date}T{end_time}"
    except Exception:
        pass
    return None


def _is_kino(event: dict) -> bool:
    """Detect cinema listings — these are scraped directly from cinema-leuzinger.ch."""
    title = event.get("title", "")
    return title.startswith("Kino")


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
    start_date = parse_german_date_string(event["date"])
    return {
        "source_url": event["website"] or BASE_URL,
        "event_title": event["title"],
        "start_date": start_date,
        "start_time": _parse_start_time(event["time"]),
        "end_datetime": _parse_end_datetime(start_date, event["time"]),
        "location": event["location"],
        "description": event["description"],
        "extracted_at": extracted_at,
    }


def _parse_zeitort(zeitort: str) -> tuple[str, str]:
    """Split 'HH.MM–HH.MM Uhr, Location' into (time, location)."""
    if "Uhr," in zeitort:
        parts = zeitort.split("Uhr,", 1)
        return (parts[0] + "Uhr").strip(), parts[1].strip()
    return "", zeitort


def _parse_item(event_id: str, item_html: str, fallback_date: str) -> dict:
    title_match = re.search(r'<h3 class="titel">(.*?)</h3>', item_html)
    datum_match = re.search(r'<span class="datum">(.*?)</span>', item_html)
    zeitort_match = re.search(r'<span class="datumzeitort">(.*?)</span>', item_html, re.DOTALL)
    link_match = re.search(r'<a href="(https?://[^"]+)"[^>]*target="_blank"', item_html)

    desc = ""
    if zeitort_match:
        after = item_html[zeitort_match.end():]
        desc_match = re.search(r'^\s*(.*?)(?:<br>|<a |</div>)', after, re.DOTALL)
        if desc_match:
            desc = STRIP_TAGS.sub('', desc_match.group(1)).strip()

    title = STRIP_TAGS.sub('', title_match.group(1)).strip() if title_match else ""
    datum = STRIP_TAGS.sub('', datum_match.group(1)).strip() if datum_match else fallback_date
    zeitort_raw = re.sub(r'\s+', ' ', STRIP_TAGS.sub('', zeitort_match.group(1))).strip() if zeitort_match else ""
    time_str, location = _parse_zeitort(zeitort_raw)

    return {
        "id": event_id,
        "title": title,
        "date": datum,
        "time": time_str,
        "location": location,
        "description": desc,
        "website": link_match.group(1) if link_match else "",
        "source": "urnerwochenblatt.ch",
    }


def parse_events_from_html(html: str) -> list[dict]:
    start = html.find('<div id="accord"')
    end = html.find('<div class="col-lg', start) if start != -1 else -1
    if start == -1 or end == -1:
        return []
    accord_match_group_0 = html[start:end]
    if not accord_match_group_0:
        return []

    events = []
    sections = re.split(r'<h2 class="mt-3 mb-3">(.*?)</h2>', accord_match_group_0)
    i = 1
    while i < len(sections) - 1:
        current_date = sections[i].strip()
        content = sections[i + 1]
        i += 2

        item_ids = re.findall(r'<div class="item"[^>]*id="heading(\d+)"', content)
        item_htmls = re.split(r'<div class="item"[^>]*id="heading\d+"[^>]*>', content)[1:]

        for event_id, item_html in zip(item_ids, item_htmls):
            events.append(_parse_item(event_id, item_html, current_date))

    return events


def fetch_events(url: str = BASE_URL, weeks: int = 4) -> list[dict]:
    """
    Fetch events from urnerwochenblatt.ch, iterating week by week.
    weeks: how many weeks ahead to fetch
    """
    start_date = datetime.today().strftime("%d.%m.%Y")
    all_events = {}  # keyed by id to deduplicate

    current = datetime.strptime(start_date, "%d.%m.%Y")
    for _ in range(weeks):
        date_str = current.strftime("%d.%m.%Y")
        fetch_url = f"{url}?d={date_str}&s="
        log.info("fetching %s", fetch_url)
        try:
            resp = requests.get(fetch_url, headers=HEADERS, timeout=15, verify=False)
            if resp.status_code == 200:
                events = parse_events_from_html(resp.text)
                for event in events:
                    all_events[event["id"]] = event
                log.info("found %d events", len(events))
            else:
                log.warning("HTTP %s", resp.status_code)
        except Exception as e:
            log.error("error: %s", e)
        current += timedelta(weeks=1)

    events = list(all_events.values())
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
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events(weeks=4)
    extracted_at = datetime.utcnow().strftime(ISO_FMT)
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total unique events: %d", len(formatted))
    output_path = "urnerwochenblatt_events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("events saved to %s", output_path)
    
