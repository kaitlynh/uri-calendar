"""Scraper for Kantonsbibliothek Uri (KBU), the cantonal library.

kbu.ch moved from TYPO3 to a Nuxt site in August 2026.  Every page embeds
its data as a devalue-encoded JSON payload in <script id="__NUXT_DATA__">,
so this scraper decodes that payload instead of parsing markup.

The listing payload gives date, title, audience and link for each event.
The detail page payload gives the description as CMS content blocks, plus
free-text "Wo:" and time lines that we pull the location and start time
from.  Times are only published as prose ("Zeit: 18 Uhr", "von 9 – 11 Uhr",
"Durchführung: 14.15 – 14.45 Uhr"), so we take the first clock time in the
Informationen section.
"""

import html as htmllib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)

SITE = "https://www.kbu.ch"
BASE_URL = f"{SITE}/veranstaltungen"
LIBRARY_LOCATION = "Kantonsbibliothek Uri, Altdorf"
# Venues the library uses off-site, spelled the way their own scrapers do.
KNOWN_VENUES = {"theater uri": "Theater Uri, Altdorf"}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}
ISO_FMT = "%Y-%m-%dT%H:%M:%S"

PAYLOAD_RE = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
STRIP_TAGS = re.compile(r"<[^>]+>")
# A clock time that is followed by "Uhr", either directly ("18 Uhr",
# "13.30 Uhr") or via a range ("9 – 11 Uhr", "14.15 – 14.45 Uhr",
# "9.30 Uhr oder 10.30 Uhr").  The lookbehind keeps "2026" and "15." out.
TIME_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?:[.:](\d{2}))?\s*"
    r"(?:Uhr|(?:[–—-]|bis|oder)\s*\d{1,2}(?:[.:]\d{2})?\s*Uhr)"
)
TIME_LABELS = re.compile(r"^(Zeit|Uhrzeit|Beginn|Wann|Durchführung|Blockzeiten?)\s*:", re.I)
LOCATION_LABELS = re.compile(r"^(Wo|Ort)\s*:\s*(.+)$", re.I)
MEDIA_BLOCKS = {"Image", "Download", "Video", "Gallery"}


# ── Nuxt payload decoding ──────────────────────────────────────────────


def _devalue(arr: list):
    """Decode a devalue flat array (Nuxt's payload format) into Python objects.

    Every value lives at an index; objects and arrays hold indices of their
    members.  Wrapper forms like ["Reactive", 5] point at another index.
    """
    cache: dict = {}

    def rec(i):
        if not isinstance(i, int) or i < 0:
            return None  # devalue's undefined / NaN / hole sentinels
        if i in cache:
            return cache[i]
        v = arr[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str):
                # wrapper form: ["ShallowReactive", idx], ["Date", iso], ...
                kind = v[0]
                if kind in ("Set", "Map"):
                    out = [rec(x) for x in v[1:]]
                elif kind == "Date":
                    out = v[1] if len(v) > 1 else None
                elif len(v) > 1:
                    out = rec(v[1])
                else:
                    out = None
                cache[i] = out
                return out
            out = []
            cache[i] = out  # register first so cycles resolve
            out.extend(rec(x) for x in v)
            return out
        if isinstance(v, dict):
            out = {}
            cache[i] = out
            for k, x in v.items():
                out[k] = rec(x)
            return out
        cache[i] = v
        return v

    return rec(0)


def _decode_payload(page_html: str) -> dict:
    match = PAYLOAD_RE.search(page_html)
    if not match:
        snippet = re.sub(r"\s+", " ", page_html).strip()[:200]
        raise ValueError(f"no __NUXT_DATA__ payload ({len(page_html)} bytes): {snippet!r}")
    return _devalue(json.loads(match.group(1)))


# ── Listing ────────────────────────────────────────────────────────────


def parse_listing(page_html: str) -> list[dict]:
    """Extract the event list from the /veranstaltungen page payload."""
    payload = _decode_payload(page_html)
    state = payload.get("state") or {}
    entries = state.get("$sveranstaltungen")
    if not isinstance(entries, list):
        # Fall back to the page's async data, whose key is a build-specific hash
        entries = next(
            (v for v in (payload.get("data") or {}).values()
             if isinstance(v, list) and v and isinstance(v[0], dict) and "date" in v[0]),
            [],
        )

    events = []
    for e in entries:
        if not isinstance(e, dict) or e.get("isDeleted"):
            continue
        link = e.get("link") or {}
        href = (link.get("href") or "").strip()
        title = (e.get("title") or link.get("title") or "").strip()
        if not href or not e.get("date"):
            log.warning("skipping listing entry without href/date: %r", title)
            continue
        events.append({
            "id": e.get("_id") or href.rsplit("/", 1)[-1],
            "title": title,
            "date": e["date"][:10],
            "path": href,
            "detail_url": f"{SITE}{href}",
            "audience": e.get("type"),
            "source": "kbu.ch",
        })
    return events


# ── Detail page ────────────────────────────────────────────────────────


def _html_to_text(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw or "")
    text = STRIP_TAGS.sub("", text)
    text = htmllib.unescape(text).replace("\xa0", " ")
    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    return text.strip()


def _flatten_blocks(block, chunks: list[str]) -> None:
    """Walk the CMS block tree, collecting text chunks in reading order.

    A List block becomes one chunk with its items on separate lines; every
    other text-bearing block becomes its own chunk.
    """
    if isinstance(block, list):
        for b in block:
            _flatten_blocks(b, chunks)
        return
    if not isinstance(block, dict):
        return
    kind = block.get("type")
    if kind in MEDIA_BLOCKS:
        return
    if kind == "List":
        items: list[str] = []
        for child in block.get("blocks") or []:
            sub: list[str] = []
            _flatten_blocks(child, sub)
            items.extend(sub)
        if items:
            chunks.append("\n".join(items))
        return
    text = _html_to_text(block.get("content") or "")
    if text:
        chunks.append(text)
    _flatten_blocks(block.get("blocks") or [], chunks)


def _info_lines(lines: list[str]) -> list[str]:
    """Lines from the 'Informationen' section onward, or all lines if absent."""
    for i, line in enumerate(lines):
        if re.match(r"^Informationen\b", line, re.I):
            return lines[i + 1:]
    return lines


def _parse_time(lines: list[str]) -> Optional[str]:
    """First clock time in the info section, preferring labelled lines."""
    info = _info_lines(lines)
    candidates = [l for l in info if TIME_LABELS.match(l)] + info + lines
    for line in candidates:
        m = TIME_RE.search(line)
        if not m:
            continue
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if hour < 24 and minute < 60:
            return f"{hour:02d}:{minute:02d}:00"
    return None


def _parse_location(lines: list[str]) -> str:
    """Venue from the 'Wo:' line, as "Venue, Town" like the other scrapers.

    The room name ("Veranstaltungsraum") stays in the description only.
    """
    for line in _info_lines(lines):
        m = LOCATION_LABELS.match(line)
        if m:
            venue = m.group(2).strip().rstrip(".")
            if "kantonsbibliothek" in venue.lower():
                return LIBRARY_LOCATION
            key = re.sub(r"\s*\(.*?\)", "", venue).strip().lower()
            return KNOWN_VENUES.get(key, venue)
    return LIBRARY_LOCATION


def parse_detail(page_html: str, path: str) -> dict:
    """Extract description, location and start time from an event page."""
    payload = _decode_payload(page_html)
    pages = ((payload.get("state") or {}).get("$spages") or {}).get("pages") or {}
    page = pages.get(path)
    if not page:
        raise ValueError(f"page {path} not in payload (has {len(pages)} pages)")

    chunks: list[str] = []
    _flatten_blocks((page.get("content") or {}).get("editorContent"), chunks)
    lines = [l for chunk in chunks for l in chunk.split("\n") if l.strip()]

    return {
        "page_title": (page.get("title") or "").strip(),
        "description": "\n\n".join(chunks),
        "location": _parse_location(lines),
        "time": _parse_time(lines),
    }


def _fetch_detail(event: dict) -> dict:
    try:
        resp = requests.get(event["detail_url"], headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("HTTP %s for %s", resp.status_code, event["detail_url"])
            return {}
        return parse_detail(resp.text, event["path"])
    except Exception as e:
        log.warning("error fetching detail %s: %s", event["detail_url"], e)
        return {}


# ── Public API ─────────────────────────────────────────────────────────


def _to_template(event: dict, extracted_at: str) -> dict:
    return {
        "event_id": f"kbu-{event['id']}",
        "source_name": "kbu.ch",
        "base_url": BASE_URL,
        "source_url": event["detail_url"],
        "event_title": event["title"],
        "start_date": event["date"],
        "start_time": event.get("time"),
        "end_datetime": None,
        "location": event.get("location") or LIBRARY_LOCATION,
        "description": event.get("description") or "",
        "extracted_at": extracted_at,
    }


def fetch_events() -> list[dict]:
    """Fetch all events from kbu.ch."""
    log.info("fetching %s", BASE_URL)
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        raise ValueError(f"HTTP {resp.status_code} for {BASE_URL}")

    events = parse_listing(resp.text)
    if not events:
        # The library always has upcoming events, so an empty list means the
        # payload shape changed or the page came back incomplete.  Raise so
        # the orchestrator retries instead of recording a clean zero.
        raise ValueError(f"no events in listing payload ({len(resp.text)} bytes)")
    log.info("found %d events", len(events))

    for event in events:
        log.debug("fetching detail: %s", event["title"])
        detail = _fetch_detail(event)
        event["description"] = detail.get("description", "")
        event["location"] = detail.get("location")
        event["time"] = detail.get("time")
        if not event["title"]:
            event["title"] = detail.get("page_title", "")

    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    events = fetch_events()
    extracted_at = datetime.now(timezone.utc).strftime(ISO_FMT)
    formatted = [_to_template(e, extracted_at) for e in events]
    log.info("total events: %d", len(formatted))
    output_path = "../events/kbu_events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    log.info("events saved to %s", output_path)
