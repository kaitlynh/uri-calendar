import requests
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from typing import Optional
import feedparser

########################
# Data Classes
########################

@dataclass
class Event:
    source_name: Optional[str]
    base_url: Optional[str]
    source_url: Optional[str]
    event_title: str
    start_date: Optional[str]
    start_time: Optional[str]
    end_datetime: Optional[str]
    location: Optional[str]
    description: Optional[str]
    extracted_at: str

def load_sources(path: str = "scraping/sources.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

########################
# Scrapers
########################

def scrape_static(source: dict, extracted_at: str) -> list[Event]:
    sel = source.get("selectors", {})
    headers = source.get("headers", {"User-Agent": "Mozilla/5.0"})
    res = requests.get(source["url"], headers=headers, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    events = []

    for item in soup.select(sel.get("container", ".event")):
        title_el = item.select_one(sel.get("title", "h3"))
        date_el  = item.select_one(sel.get("date", "time"))
        loc_el   = item.select_one(sel.get("location", ".location"))
        desc_el  = item.select_one(sel.get("description", ".description"))
        link_el  = item.select_one(sel.get("link", "a"))

        events.append(Event(
            source_name    = source.get("name"),
            source_url     = link_el["href"] if link_el else source["url"],
            base_url       = source["url"],
            event_title    = title_el.text.strip() if title_el else "",
            start_date     = date_el.get("datetime", date_el.text.strip()) if date_el else None,
            start_time     = None,
            end_datetime   = None,
            location       = loc_el.text.strip() if loc_el else None,
            description    = desc_el.text.strip() if desc_el else None,
            extracted_at   = extracted_at,
        ))
    return events

def scrape_rss(source: dict, extracted_at: str) -> list[Event]:
    feed = feedparser.parse(source["url"])
    events = []

    for entry in feed.entries:
        date_str = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            date_str = datetime(*entry.published_parsed[:6]).isoformat()

        events.append(Event(
            source_name    = urlsplit(source["url"]).netloc,
            base_url       = source["url"],
            source_url     = entry.get("link", source["url"]),
            event_title    = entry.get("title", ""),
            start_date     = date_str.split("T")[0] if date_str else None,
            start_time     = date_str.split("T")[1].split(".")[0] if date_str else None,
            end_datetime   = None,
            location       = entry.get("location", None),
            description    = entry.get("summary", None),
            extracted_at   = extracted_at,
        ))
    return events

def scrape_js(source: dict, extracted_at: str) -> list[Event]:
    from playwright.sync_api import sync_playwright
    sel = source.get("selectors", {})
    events = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(source["url"], wait_until="networkidle")
        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

    for item in soup.select(sel.get("container", ".event")):
        title_el = item.select_one(sel.get("title", "h3"))
        date_el  = item.select_one(sel.get("date", "time"))
        loc_el   = item.select_one(sel.get("location", ".location"))
        link_el  = item.select_one(sel.get("link", "a"))

        events.append(Event(
            source_name    = source.get("name"),
            source_url     = link_el["href"] if link_el else source["url"],
            base_url         = source["url"],
            event_title    = title_el.text.strip() if title_el else "",
            start_date     = date_el.get("datetime", date_el.text.strip()) if date_el else None,
            start_time     = None,
            end_datetime   = None,
            location       = loc_el.text.strip() if loc_el else None,
            description    = None,
            extracted_at   = extracted_at,
        ))
    return events

def scrape_kbu(source: dict, extracted_at: str) -> list[Event]:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from scrape_kbu import fetch_events, _to_template as kbu_to_template

    raw = fetch_events()
    events = []
    for e in raw:
        t = kbu_to_template(e, extracted_at)
        events.append(Event(
            source_name  = t["source_name"],
            base_url     =  "kbu.ch",
            source_url   = t["source_url"],
            event_title  = t["event_title"],
            start_date   = t["start_date"],
            start_time   = t["start_time"],
            end_datetime = t["end_datetime"],
            location     = t["location"],
            description  = t["description"],
            extracted_at = t["extracted_at"],
        ))
    return events

def scrape_musikschule(source: dict, extracted_at: str) -> list[Event]:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from scrape_musikschule import fetch_events, _to_template as ms_to_template

    raw = fetch_events()
    events = []
    for e in raw:
        t = ms_to_template(e, extracted_at)
        events.append(Event(
            source_name  = t["source_name"],
            base_url     = "www.musikschule-uri.ch",
            source_url   = t["source_url"],
            event_title  = t["event_title"],
            start_date   = t["start_date"],
            start_time   = t["start_time"],
            end_datetime = t["end_datetime"],
            location     = t["location"],
            description  = t["description"],
            extracted_at = t["extracted_at"],
        ))
    return events

def scrape_altdorf(source: dict, extracted_at: str) -> list[Event]:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from scrape_altdorf import fetch_events, _to_template as altdorf_to_template

    raw = fetch_events()
    events = []
    for e in raw:
        t = altdorf_to_template(e, extracted_at)
        events.append(Event(
            source_name  = t["source_name"],
            base_url      = "www.altdorf.ch",
            source_url   = t["source_url"],
            event_title  = t["event_title"],
            start_date   = t["start_date"],
            start_time   = t["start_time"],
            end_datetime = t["end_datetime"],
            location     = t["location"],
            description  = t["description"],
            extracted_at = t["extracted_at"],
        ))
    return events

def scrape_urnerwochenblatt(source: dict, extracted_at: str) -> list[Event]:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from scrape_urnerwochenblatt import fetch_events, _to_template as uw_to_template

    raw = fetch_events(base_url=source["url"], weeks=source.get("weeks", 4))
    events = []
    for e in raw:
        t = uw_to_template(e, extracted_at)
        events.append(Event(
            source_name  = "urnerwochenblatt.ch",
            base_url       = "urnerwochenblatt.ch",
            source_url   = t["source_url"],
            event_title  = t["event_title"],
            start_date   = t["start_date"],
            start_time   = t["start_time"],
            end_datetime = t["end_datetime"],
            location     = t["location"],
            description  = t["description"],
            extracted_at = t["extracted_at"],
        ))
    return events

def scrape_andermatt(source: dict, extracted_at: str) -> list[Event]:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from scrape_andermatt import fetch_events, _to_template as andermatt_to_template

    raw = fetch_events()
    events = []
    for e in raw:
        t = andermatt_to_template(e, extracted_at)
        events.append(Event(
            source_name  = t["source_name"],
            base_url       = "www.gemeinde-andermatt.ch",
            source_url   = t["source_url"],
            event_title  = t["event_title"],
            start_date   = t["start_date"],
            start_time   = t["start_time"],
            end_datetime = t["end_datetime"],
            location     = t["location"],
            description  = t["description"],
            extracted_at = t["extracted_at"],
        ))
    return events


SCRAPERS = {
    "static":            scrape_static,
    "rss":               scrape_rss,
    "js":                scrape_js,
    "urnerwochenblatt":  scrape_urnerwochenblatt,
    "kbu":               scrape_kbu,
    "musikschule":       scrape_musikschule,
    "altdorf":           scrape_altdorf,
    "andermatt":         scrape_andermatt,
}

def collect_all_events(sources_path: str = "scraping/sources.json", output_path: str = "events/events.json"):
    sources = load_sources(sources_path)
    extracted_at = datetime.now(timezone.utc).isoformat()
    all_events: list[Event] = []

    for source in sources:
        scraper_type = source.get("type", "static")
        scraper_fn = SCRAPERS.get(scraper_type)

        if not scraper_fn:
            print(f"  Unbekannter Typ '{scraper_type}' für {source['name']} — übersprungen")
            continue

        try:
            events = scraper_fn(source, extracted_at)
            all_events.extend(events)
            print(f"  {len(events):3d} Events  ←  {source['name']}")
        except Exception as e:
            print(f"  FEHLER bei {source['name']}: {e}")

    # Deduplizieren nach Titel + Datum
    seen = set()
    unique: list[Event] = []
    for ev in all_events:
        key = (ev.event_title.lower().strip(), (ev.start_date or "")[:10], ev.start_time or "")
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    unique.sort(key=lambda e: e.start_date or "")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            [asdict(e) for e in unique],
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\n  {len(unique)} Events total → {output_path}")

if __name__ == "__main__":
    collect_all_events()