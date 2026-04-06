import importlib
import inspect
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import feedparser
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Ensure scraping/ is on the import path so custom scraper modules resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    priority: int
    ai_updated: Optional[bool] = False
    ai_updated_at: Optional[str] = None


def load_sources(path: str = "scraping/sources.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


########################
# Built-in Scrapers
########################


def scrape_static(source: dict, extracted_at: str) -> list[Event]:
    sel = source.get("selectors", {})
    headers = source.get("headers", {"User-Agent": "Mozilla/5.0"})
    res = requests.get(source["url"], headers=headers, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    events = []

    source_name = source.get("source_name") or source.get("name")
    base_url = source.get("base_url") or source["url"]

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
                start_date=date_el.get("datetime", date_el.text.strip())
                if date_el
                else None,
                start_time=None,
                end_datetime=None,
                location=loc_el.text.strip() if loc_el else None,
                description=desc_el.text.strip() if desc_el else None,
                extracted_at=extracted_at,
                priority=source["priority"],
            )
        )
    return events


def scrape_rss(source: dict, extracted_at: str) -> list[Event]:
    feed = feedparser.parse(source["url"])
    events = []

    source_name = source.get("source_name") or urlsplit(source["url"]).netloc
    base_url = source.get("base_url") or source["url"]

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


def scrape_js(source: dict, extracted_at: str) -> list[Event]:
    from playwright.sync_api import sync_playwright

    sel = source.get("selectors", {})
    events = []

    source_name = source.get("source_name") or source.get("name")
    base_url = source.get("base_url") or source["url"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(source["url"], wait_until="networkidle")
        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

    for item in soup.select(sel.get("container", ".event")):
        title_el = item.select_one(sel.get("title", "h3"))
        date_el = item.select_one(sel.get("date", "time"))
        loc_el = item.select_one(sel.get("location", ".location"))
        link_el = item.select_one(sel.get("link", "a"))

        events.append(
            Event(
                source_name=source_name,
                source_url=link_el["href"] if link_el else source["url"],
                base_url=base_url,
                event_title=title_el.text.strip() if title_el else "",
                start_date=date_el.get("datetime", date_el.text.strip())
                if date_el
                else None,
                start_time=None,
                end_datetime=None,
                location=loc_el.text.strip() if loc_el else None,
                description=None,
                extracted_at=extracted_at,
                priority=source["priority"],
            )
        )
    return events


########################
# Custom Scraper Loader
########################


def scrape_custom(source: dict, extracted_at: str) -> list[Event]:
    """
    Generic loader for custom scraper modules.

    Imports the module named in source["scraper"], calls its fetch_events()
    and _to_template() functions, and builds Event objects.

    source_name and base_url come from sources.json (the single source of
    truth), overriding whatever the scraper module may return.

    Any extra fields in the source config (e.g. "weeks") are passed as
    kwargs to fetch_events() if the function signature accepts them.
    """
    module_name = source.get("scraper")
    if not module_name:
        raise ValueError(f"Custom source missing 'scraper' field: {source['name']}")

    mod = importlib.import_module(module_name)

    # Build kwargs: pass source config values that match fetch_events() params
    sig = inspect.signature(mod.fetch_events)
    kwargs = {}
    for param_name in sig.parameters:
        if param_name in source:
            kwargs[param_name] = source[param_name]

    raw = mod.fetch_events(**kwargs)

    # source_name and base_url from config — single source of truth
    source_name = source["source_name"]
    base_url = source["base_url"]

    events = []
    for e in raw:
        t = mod._to_template(e, extracted_at)
        events.append(
            Event(
                source_name=source_name,
                base_url=base_url,
                source_url=t.get("source_url", base_url),
                event_title=t.get("event_title", ""),
                start_date=t.get("start_date"),
                start_time=t.get("start_time"),
                end_datetime=t.get("end_datetime"),
                location=t.get("location"),
                description=t.get("description"),
                extracted_at=t.get("extracted_at", extracted_at),
                priority=source["priority"],
            )
        )
    return events


SCRAPERS = {
    "static": scrape_static,
    "rss": scrape_rss,
    "js": scrape_js,
    "custom": scrape_custom,
}


MAX_RETRIES = 2
RETRY_DELAY = 5  # seconds


def _run_scraper(
    source: dict, extracted_at: str
) -> tuple[str, list[Event], Optional[str]]:
    import time

    scraper_type = source.get("type", "static")
    scraper_fn = SCRAPERS.get(scraper_type)
    if not scraper_fn:
        log.warning("%-30s  unknown type '%s' — skipped", source["name"], scraper_type)
        return source["name"], [], f"unknown type '{scraper_type}' — skipped"
    log.info("%-30s  starting", source["name"])
    t0 = time.monotonic()
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            events = scraper_fn(source, extracted_at)
            elapsed = time.monotonic() - t0
            if attempt > 1:
                log.info("%-30s  %3d events  (%.1fs, succeeded on attempt %d)", source["name"], len(events), elapsed, attempt)
            else:
                log.info("%-30s  %3d events  (%.1fs)", source["name"], len(events), elapsed)
            return source["name"], events, None
        except Exception as e:
            last_err = e
            elapsed = time.monotonic() - t0
            if attempt < MAX_RETRIES:
                log.warning("%-30s  attempt %d failed (%.1fs): %s — retrying in %ds", source["name"], attempt, elapsed, e, RETRY_DELAY)
                time.sleep(RETRY_DELAY)
            else:
                log.error("%-30s  failed after %d attempts (%.1fs): %s", source["name"], MAX_RETRIES, elapsed, last_err)
    return source["name"], [], f"ERROR: {last_err}"


def collect_all_events(
    sources_path: str = "scraping/sources.json", output_path: str = "events/events.json"
):
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    sources = load_sources(sources_path)
    extracted_at = datetime.now(timezone.utc).isoformat()
    all_events: list[Event] = []

    log.info("starting %d sources in parallel", len(sources))
    t_start = time.monotonic()

    with ThreadPoolExecutor() as executor:
        future_to_name = {
            executor.submit(_run_scraper, s, extracted_at): s["name"] for s in sources
        }
        total = len(future_to_name)
        done = 0
        for future in as_completed(future_to_name):
            _, events, err = future.result()
            done += 1
            still_running = [n for f, n in future_to_name.items() if not f.done()]
            if still_running:
                log.info(
                    "progress: %d/%d done — still running: %s",
                    done,
                    total,
                    ", ".join(still_running),
                )
            else:
                log.info("progress: %d/%d done", done, total)
            if not err:
                all_events.extend(events)

    all_events.sort(key=lambda e: e.start_date or "")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            [asdict(e) for e in all_events],
            f,
            ensure_ascii=False,
            indent=2,
        )

    elapsed = time.monotonic() - t_start
    log.info(
        "done in %.1fs — %d events written → %s",
        elapsed,
        len(all_events),
        output_path,
    )


if __name__ == "__main__":
    collect_all_events()
