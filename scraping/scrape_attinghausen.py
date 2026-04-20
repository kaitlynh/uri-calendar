# Attinghausen publishes their event calendar as PDFs (typically one per half-year).
# These PDFs vary in format (some are image-based, some text-based) so we don't
# attempt to auto-parse them. Instead:
#
# 1. This scraper checks the page for PDFs and compares hashes against a processing log.
# 2. If a new/changed PDF is detected, the scraper logs an ERROR (which creates a
#    GitHub Issue via the pipeline), and we handle it manually.
# 3. To process a new PDF: download it (or have the user attach it) and read it
#    directly — Claude can read PDFs natively without any extra libraries.
#    Then add the extracted events to .attinghausen_processed.json with the
#    PDF's SHA256 hash.
#
# IMPORTANT for agents processing new PDFs:
# - The PDFs change format between releases. Do NOT assume the format — look at
#   the actual PDF and ASK THE USER how they want titles formatted before extracting.
# - Known formats so far:
#   1. Word-style with comma-separated lines (e.g. "Feuerwehr, Probe, Feuerwehrlokal")
#      → Copy the full line verbatim as the title.
#   2. Spreadsheet with Verein/Veranstaltung/Ort columns
#      → Title = "Veranstaltung | Verein" (e.g. "Probe | Feuerwehr"), Ort → location field.
# - Put venue/location info into the "location" field, not into the title.
# - If the PDF includes start times, include them as "start_time" in HH:MM format
#   (e.g. "19:00"). Omit the field if no time is given for an event.
# - See existing entries in .attinghausen_processed.json for reference.

import hashlib
import json as json_mod
import logging
import os
import requests

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

PAGE_URL = "https://www.attinghausen.ch/index.php/portrait/terminkalender"
BASE_URL = "https://www.attinghausen.ch"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}
LOG_FILE = os.path.join(os.path.dirname(__file__), ".attinghausen_processed.json")


def _find_pdf_links(html: str) -> list[dict]:
    """Find all PDF links on the page."""
    soup = BeautifulSoup(html, "html.parser")
    pdfs = []
    for a in soup.select("a[href$='.pdf']"):
        href = a.get("href", "")
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        filename = href.rsplit("/", 1)[-1]
        pdfs.append({"url": url, "filename": filename})
    return pdfs


def _load_log() -> dict:
    """Load the processing log (filename → {hash, extracted_at, events})."""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE) as f:
                return json_mod.load(f)
        except Exception:
            pass
    return {}


def _save_log(data: dict):
    with open(LOG_FILE, "w") as f:
        json_mod.dump(data, f, ensure_ascii=False, indent=2)


def fetch_events() -> list:
    """Fetch events from Attinghausen PDF calendars.

    Checks the page for PDFs, compares hashes against the processing log.
    - Known hash → return cached events
    - New/changed PDF → add to log with empty events, log ERROR (triggers alert)
    - Events are manually added to the log after human review of each PDF
    """
    log.info("fetching %s", PAGE_URL)
    try:
        resp = requests.get(PAGE_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s", resp.status_code)
            return []
    except Exception as e:
        log.error("error fetching page: %s", e)
        return []

    pdfs = _find_pdf_links(resp.text)
    log.info("found %d PDF links", len(pdfs))

    if not pdfs:
        log.error("no PDFs found on page")
        return []

    processing_log = _load_log()
    all_events = []
    log_changed = False

    for pdf_info in pdfs:
        filename = pdf_info["filename"]
        log.info("checking PDF: %s", filename)

        try:
            pdf_resp = requests.get(pdf_info["url"], headers=HEADERS, timeout=30)
            if pdf_resp.status_code != 200:
                log.warning("HTTP %s for %s", pdf_resp.status_code, filename)
                continue

            pdf_hash = hashlib.sha256(pdf_resp.content).hexdigest()

            entry = processing_log.get(filename)

            if entry and entry["hash"] == pdf_hash and entry.get("events"):
                # Already processed with events — return them
                pdf_extracted_at = entry.get("extracted_at")
                events = entry["events"]
                if pdf_extracted_at:
                    for e in events:
                        e["extracted_at"] = pdf_extracted_at
                log.info("  known PDF, %d events", len(events))
                all_events.extend(events)
            else:
                # New/changed PDF, or known but not yet processed
                is_new = not entry or entry["hash"] != pdf_hash
                if is_new:
                    log.error("  NEW PDF detected on Attinghausen Gemeinde site: %s — extract events with an AI agent and add to .attinghausen_processed.json. See instructions in scraping/scrape_attinghausen.py", filename)
                    processing_log[filename] = {
                        "hash": pdf_hash,
                        "extracted_at": None,
                        "events": [],
                    }
                    log_changed = True
                else:
                    log.warning("  WAITING: PDF on Attinghausen Gemeinde site still needs event extraction: %s — see instructions in scraping/scrape_attinghausen.py", filename)

        except Exception as e:
            log.error("error checking %s: %s", filename, e)

    if log_changed:
        _save_log(processing_log)

    return all_events


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "source_url": PAGE_URL,
        "event_title": event["title"],
        "start_date": event["start_date"],
        "start_time": event.get("start_time"),
        "end_datetime": event.get("end_datetime"),
        "location": event.get("location"),
        "description": event.get("description"),
        "extracted_at": event.get("extracted_at", extracted_at),
        "ai_flag": True,
    }


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    formatted = [_to_template(e, extracted_at) for e in events]
    print(json.dumps(formatted, ensure_ascii=False, indent=2))
