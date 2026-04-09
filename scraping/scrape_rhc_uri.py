import logging
import re
import requests
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

ICAL_URL = "https://calendar.clubdesk.com/clubdesk/ical/63505/1000321/djEtghYihgJmXrDqwgFBmjVXdjKnO-vsfvBfY47oKLgOr7I=/basic.ics"
BASE_URL = "https://www.rhc-uri.ch/unser_verein/spiel-saisonplaene"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
HOME_VENUE = "Sporthalle Seedorf"


def _parse_ical(text: str) -> list:
    """Parse iCal text into a list of event dicts."""
    events = []
    current = None
    for line in text.splitlines():
        # Handle line folding (continuation lines start with space/tab)
        if current is not None and line.startswith((" ", "\t")):
            current[current["_last_key"]] += line[1:]
            continue

        if line == "BEGIN:VEVENT":
            current = {"_last_key": ""}
            continue
        if line == "END:VEVENT":
            if current:
                events.append(current)
            current = None
            continue
        if current is None:
            continue

        if ":" in line:
            key, _, value = line.partition(":")
            # Strip parameters (e.g. DTSTART;TZID=Europe/Berlin)
            base_key = key.split(";")[0]
            current[base_key] = value
            current["_last_key"] = base_key
            # Preserve full key for date type detection
            current[f"_raw_{base_key}"] = key

    return events


def _parse_dt(event: dict, field: str) -> tuple:
    """Parse DTSTART or DTEND. Returns (date_str, time_str) or (date_str, None) for all-day."""
    value = event.get(field, "")
    raw_key = event.get(f"_raw_{field}", "")

    if not value:
        return (None, None)

    # All-day event: VALUE=DATE with format YYYYMMDD
    if "VALUE=DATE" in raw_key:
        try:
            dt = datetime.strptime(value, "%Y%m%d")
            return (dt.strftime("%Y-%m-%d"), None)
        except ValueError:
            return (None, None)

    # Date-time: YYYYMMDDTHHMMSS (timezone is Europe/Berlin which matches Zurich)
    try:
        dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
        return (dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S"))
    except ValueError:
        return (None, None)


def _clean_description(desc: str) -> Optional[str]:
    """Clean iCal description field."""
    if not desc:
        return None
    # Unescape iCal escapes
    desc = desc.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")
    desc = desc.strip()
    return desc if desc else None


def fetch_events() -> list:
    """Fetch all events from RHC Uri iCal feed."""
    log.info("fetching %s", ICAL_URL)
    try:
        resp = requests.get(ICAL_URL, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            log.warning("HTTP %s", resp.status_code)
            return []
    except Exception as e:
        log.error("error: %s", e)
        return []

    raw_events = _parse_ical(resp.text)
    log.info("parsed %d events from iCal", len(raw_events))

    events = []
    for ev in raw_events:
        start_date, start_time = _parse_dt(ev, "DTSTART")
        end_date, end_time = _parse_dt(ev, "DTEND")

        if not start_date:
            continue

        summary = ev.get("SUMMARY", "").strip()
        if not summary:
            continue

        # Build end_datetime ISO string if we have date+time
        end_datetime = None
        if end_date and end_time:
            end_datetime = f"{end_date}T{end_time}"

        description = _clean_description(ev.get("DESCRIPTION", ""))
        raw_location = ev.get("LOCATION", "").strip()

        # Enrich location: "Seedorf" (+ typo "Seeedorf" in feed) = home venue
        if re.match(r"^se+dorf$", raw_location.strip(), re.IGNORECASE):
            location = HOME_VENUE
        elif not raw_location and "heimspiel" in summary.lower():
            location = HOME_VENUE
        else:
            location = raw_location or None

        # Enrich short titles (e.g. "NLB" or "Damen") with opponent from description
        title = summary
        if len(summary) < 15 and description and description.startswith("vs."):
            title = f"RHC Uri {summary} {description}"
        elif len(summary) < 15 and not description:
            title = f"RHC Uri {summary}"
        # Prefix "RHC Uri" if not already present for clarity on the calendar
        if not title.startswith("RHC Uri") and "RHC Uri" not in title:
            title = f"RHC Uri: {title}"

        events.append({
            "title": title,
            "start_date": start_date,
            "start_time": start_time,
            "end_datetime": end_datetime,
            "location": location,
            "description": description,
        })

    return events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_url": BASE_URL,
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event["start_time"],
        "end_datetime": event["end_datetime"],
        "location": event["location"],
        "description": event["description"],
        "extracted_at": extracted_at,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    formatted = [_to_template(e, extracted_at) for e in events]
    print(json.dumps(formatted, ensure_ascii=False, indent=2))
