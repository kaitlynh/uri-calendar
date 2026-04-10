"""Pipeline orchestrator — scrapes all configured sources in parallel.

This is the main entry point for the scraping pipeline.  It reads
sources.json, dispatches each source to the appropriate scraper type
(static HTML, RSS, JS-rendered, ICMS CMS, or a custom module), and
writes the combined results to events/events.json.

Architecture:
    sources.json defines *what* to scrape.  Each entry has a "type" that
    selects the scraper strategy:
        static  — CSS-selector extraction from server-rendered HTML
        rss     — RSS/Atom feed parsing
        js      — Playwright-rendered pages (SPAs, lazy-loaded content)
        icms    — ICMS CMS used by several Uri municipalities
        custom  — a dedicated Python module (e.g. scrape_eventfrog.py)

    Custom scrapers must export fetch_events(**kwargs) → list[dict] and
    _to_template(raw, extracted_at) → dict.  The orchestrator inspects
    the function signature and forwards matching keys from sources.json
    as kwargs (e.g. "weeks" for the Urner Wochenblatt scraper).

    All scrapers run concurrently via ThreadPoolExecutor with automatic
    retry (up to 2 attempts per source).

Usage:
    python scraping/scraping.py                    # from project root
    python scraping/scraping.py --sources alt.json # custom config
"""

import importlib
import inspect
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Ensure scraping/ is importable so custom scraper modules resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Data model ──────────────────────────────────────────────────────────


@dataclass
class Event:
    """Canonical event representation shared by all scraper types.

    Fields map 1:1 to the events.json schema and the database columns.
    """
    source_name: Optional[str]
    base_url: Optional[str]
    source_url: Optional[str]
    event_title: str
    start_date: Optional[str]       # YYYY-MM-DD
    start_time: Optional[str]       # HH:MM:SS or None for all-day
    end_datetime: Optional[str]     # YYYY-MM-DDTHH:MM:SS
    location: Optional[str]
    description: Optional[str]
    extracted_at: str               # ISO 8601 UTC timestamp
    priority: int                   # lower = preferred in dedup
    ai_flag: Optional[bool] = False
    ai_flag_at: Optional[str] = None


def load_sources(path: str = "scraping/sources.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Scraper type registry ──────────────────────────────────────────────
# Each built-in type is a module with a scrape(source, extracted_at) function.

from type_static import scrape as scrape_static
from type_rss import scrape as scrape_rss
from type_js import scrape as scrape_js
from type_icms import scrape as scrape_icms


def scrape_custom(source: dict, extracted_at: str) -> list[Event]:
    """Dynamic loader for custom scraper modules.

    Imports the module named in source["scraper"], calls fetch_events()
    and _to_template(), and wraps results as Event objects.

    source_name and base_url always come from sources.json — the single
    source of truth — overriding whatever the scraper returns.
    """
    module_name = source.get("scraper")
    if not module_name:
        raise ValueError(f"Custom source missing 'scraper' field: {source['name']}")

    mod = importlib.import_module(module_name)

    # Forward source config values that match the function's parameter names
    # (e.g. weeks=4 for the Urner Wochenblatt scraper)
    sig = inspect.signature(mod.fetch_events)
    kwargs = {k: source[k] for k in sig.parameters if k in source}

    raw = mod.fetch_events(**kwargs)

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
    "icms": scrape_icms,
    "custom": scrape_custom,
}

# ── Execution with retry ───────────────────────────────────────────────

MAX_RETRIES = 2
RETRY_DELAY = 5  # seconds


def _run_scraper(
    source: dict, extracted_at: str
) -> tuple[str, list[Event], Optional[str]]:
    """Run a single scraper with retry logic.  Returns (name, events, error)."""
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
                log.info("%-30s  %3d events  (%.1fs, succeeded on attempt %d)",
                         source["name"], len(events), elapsed, attempt)
            else:
                log.info("%-30s  %3d events  (%.1fs)",
                         source["name"], len(events), elapsed)
            return source["name"], events, None
        except Exception as e:
            last_err = e
            elapsed = time.monotonic() - t0
            if attempt < MAX_RETRIES:
                log.warning("%-30s  attempt %d failed (%.1fs): %s — retrying in %ds",
                            source["name"], attempt, elapsed, e, RETRY_DELAY)
                time.sleep(RETRY_DELAY)
            else:
                log.error("%-30s  failed after %d attempts (%.1fs): %s",
                          source["name"], MAX_RETRIES, elapsed, last_err)

    return source["name"], [], f"ERROR: {last_err}"


# ── Main pipeline ──────────────────────────────────────────────────────


def collect_all_events(
    sources_path: str = "scraping/sources.json",
    output_path: str = "events/events.json",
):
    """Scrape all sources in parallel and write combined JSON."""
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
                log.info("progress: %d/%d done — still running: %s",
                         done, total, ", ".join(still_running))
            else:
                log.info("progress: %d/%d done", done, total)
            if not err:
                all_events.extend(events)

    all_events.sort(key=lambda e: e.start_date or "")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([asdict(e) for e in all_events], f, ensure_ascii=False, indent=2)

    elapsed = time.monotonic() - t_start
    log.info("done in %.1fs — %d events written → %s", elapsed, len(all_events), output_path)


if __name__ == "__main__":
    collect_all_events()
