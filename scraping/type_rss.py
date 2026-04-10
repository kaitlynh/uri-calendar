"""Scraper type: RSS/Atom feed parsing.

Uses feedparser to extract events from standard RSS or Atom feeds.
The published date is split into start_date and start_time.
"""

from datetime import datetime
from urllib.parse import urlsplit

import feedparser


def scrape(source: dict, extracted_at: str) -> list:
    from scraping import Event

    feed = feedparser.parse(source["url"])

    source_name = source.get("source_name") or urlsplit(source["url"]).netloc
    base_url = source.get("base_url") or source["url"]

    events = []
    for entry in feed.entries:
        date_str = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            date_str = datetime(*entry.published_parsed[:6]).isoformat()

        events.append(
            Event(
                source_name=source_name,
                base_url=base_url,
                source_url=entry.get("link", source["url"]),
                event_title=entry.get("title", ""),
                start_date=date_str.split("T")[0] if date_str else None,
                start_time=date_str.split("T")[1].split(".")[0] if date_str else None,
                end_datetime=None,
                location=entry.get("location", None),
                description=entry.get("summary", None),
                extracted_at=extracted_at,
                priority=source["priority"],
            )
        )
    return events
