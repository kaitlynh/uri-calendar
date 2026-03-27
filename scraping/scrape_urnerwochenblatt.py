import requests
import re
import json
import urllib3
from datetime import datetime, timedelta, timezone
from typing import Optional

urllib3.disable_warnings()

BASE_URL = "https://www.urnerwochenblatt.ch/veranstaltungen/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
STRIP_TAGS = re.compile(r'<[^>]+>')
ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def _parse_iso_datetime(date_str: str, time_part: str) -> Optional[str]:
    """Parse 'DD.MM.YYYY' and 'HH.MM Uhr' (or 'HH.MM–HH.MM Uhr') into ISO8601."""
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        if time_part:
            # Take only the start time before any '–'
            start = time_part.split("–")[0].replace("Uhr", "").strip()
            h, m = start.split(".")
            dt = dt.replace(hour=int(h), minute=int(m))
        return dt.strftime(ISO_FMT)
    except Exception:
        return None


def _parse_end_datetime(date_str: str, time_str: str) -> Optional[str]:
    """Parse end time from 'HH.MM–HH.MM Uhr' range."""
    if "–" not in time_str:
        return None
    try:
        end_part = time_str.split("–")[1].replace("Uhr", "").strip()
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        h, m = end_part.split(".")
        dt = dt.replace(hour=int(h), minute=int(m))
        return dt.strftime(ISO_FMT)
    except Exception:
        return None


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_url": event["website"] or BASE_URL,
        "event_title": event["title"],
        "start_datetime": _parse_iso_datetime(event["date"], event["time"]),
        "end_datetime": _parse_end_datetime(event["date"], event["time"]),
        "location": event["location"],
        "description": event["description"],
        "category": None,
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


def fetch_events(start_date: str = None, weeks: int = 4) -> list[dict]:
    """
    Fetch events from urnerwochenblatt.ch.
    start_date: DD.MM.YYYY format, defaults to today
    weeks: how many weeks ahead to fetch
    """
    if start_date is None:
        start_date = datetime.today().strftime("%d.%m.%Y")

    all_events = {}  # keyed by id to deduplicate

    current = datetime.strptime(start_date, "%d.%m.%Y")
    for _ in range(weeks):
        date_str = current.strftime("%d.%m.%Y")
        url = f"{BASE_URL}?d={date_str}&s="
        print(f"Fetching: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
            if resp.status_code == 200:
                events = parse_events_from_html(resp.text)
                for event in events:
                    all_events[event["id"]] = event
                print(f"  Found {len(events)} events")
            else:
                print(f"  HTTP {resp.status_code}")
        except Exception as e:
            print(f"  Error: {e}")
        current += timedelta(weeks=1)

    return list(all_events.values())


if __name__ == "__main__":
    events = fetch_events(weeks=4)
    extracted_at = datetime.utcnow().strftime(ISO_FMT)
    formatted = [_to_template(e, extracted_at) for e in events]
    print(f"\nTotal unique events: {len(formatted)}")
    output_path = "urnerwochenblatt_events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    print(f"Events saved to {output_path}")
    
