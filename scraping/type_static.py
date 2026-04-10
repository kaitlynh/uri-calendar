"""Scraper type: static HTML — CSS selector-based extraction.

Used for server-rendered pages where event data lives in predictable
DOM elements.  Selectors are configured per-source in sources.json:

    "selectors": {
        "container": ".event-card",
        "title": "h3",
        "date": "time",
        "location": ".venue",
        "description": ".summary",
        "link": "a"
    }

Falls back to sensible defaults (.event, h3, time, etc.) when selectors
are not specified.
"""

import requests
from bs4 import BeautifulSoup


def scrape(source: dict, extracted_at: str) -> list:
    from scraping import Event

    sel = source.get("selectors", {})
    headers = source.get("headers", {"User-Agent": "Mozilla/5.0"})
    res = requests.get(source["url"], headers=headers, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")

    source_name = source.get("source_name") or source.get("name")
    base_url = source.get("base_url") or source["url"]

    events = []
    for item in soup.select(sel.get("container", ".event")):
        title_el = item.select_one(sel.get("title", "h3"))
        date_el = item.select_one(sel.get("date", "time"))
        loc_el = item.select_one(sel.get("location", ".location"))
        desc_el = item.select_one(sel.get("description", ".description"))
        link_el = item.select_one(sel.get("link", "a"))

        events.append(
            Event(
                source_name=source_name,
                source_url=link_el["href"] if link_el else source["url"],
                base_url=base_url,
                event_title=title_el.text.strip() if title_el else "",
                start_date=(
                    date_el.get("datetime", date_el.text.strip()) if date_el else None
                ),
                start_time=None,
                end_datetime=None,
                location=loc_el.text.strip() if loc_el else None,
                description=desc_el.text.strip() if desc_el else None,
                extracted_at=extracted_at,
                priority=source["priority"],
            )
        )
    return events
